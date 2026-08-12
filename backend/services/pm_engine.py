"""Optimus Portfolio Manager — the engine that answers "what should I do today?"

This is a different product from the research lab, and it is deliberately not
subordinate to it. The lab asks *what evidence do we possess*. This asks *given
this actual book, this cash and this goal, what is the best action right now* —
and it is allowed to use information the lab has not validated, provided every
such number is LABELLED as observational.

Four rules the whole module obeys:

1. **Analyst targets are evidence, not truth.** Every implied upside is passed
   through an explicit haircut (`TARGET_HAIRCUT`) and then through a bounded
   reliability discount, and both are printed next to the answer.
2. **The LLM never sizes anything.** Sizing is deterministic arithmetic on a
   return distribution, a correlation assumption and a per-mode cap.
3. **A stretch target is not an expected return.** The engine reports
   P(reach), P(floor breach) and expected drawdown together, always.
4. **Absence of evidence is not evidence of a sale.** (BUILD-1.1.) A held name
   the engine cannot see is REVIEW. There is no path from a missing feed to a
   ticket.

BUILD-1.1 changed three things that were producing confident nonsense:

* **The book marks to market.** v1 read `Position.dollars` — a static number in
  a YAML file — as the live value of a position, so a book could report
  "$45,000" indefinitely while its holdings halved. Shares × live price is now
  the authoritative state for a confirmed position, and a confirmed position
  without a share count is rejected at load.
* **Volatility no longer manufactures expected return.** v1 set the *median* of
  a lognormal to `haircut × upside` and then quoted its *mean*, which is higher
  by `exp(σ²/2)`. Raising a name's volatility raised its expected return, then
  its Kelly weight — the engine paid a premium for being uncertain. The street
  target, after haircut and reliability, is now the **expected value**, and σ
  only widens the distribution around it.
* **Unknown is no longer scored as perfect.** See `pm_evidence`.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import yaml

from backend.services import analyst_ledger, pm_evidence
from backend.services.pm_evidence import is_finite

logger = logging.getLogger(__name__)

BOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "murat_book.yaml"

#: Fraction of an analyst's implied upside carried into the base case.
#: Consensus 12-month targets overshoot realised prices on average, more so in
#: small caps and clinical-stage names. 0.35 is an ASSUMPTION with no in-house
#: validation — it is printed with every result and is the first thing that
#: should be replaced by a measurement once the journal has enough resolved
#: decisions to fit it.
TARGET_HAIRCUT = 0.35
#: Extra haircut for names the engine flags as event-binary (clinical, pre-
#: revenue). Their "consensus target" is a probability-weighted fantasy quoted
#: as a price.
BINARY_EXTRA_HAIRCUT = 0.60
#: Assumed average pairwise correlation of the book's names, used only in the
#: wealth simulation. Small-cap high-beta books cluster hard in drawdowns.
DEFAULT_CORRELATION = 0.35
#: Annualised idiosyncratic vol when history is unavailable.
FALLBACK_VOL = 0.65
#: Risk aversion in the certainty-equivalent used to compare two names.
#: CE = mu - 0.5 * lambda * sigma^2. At lambda = 1 a 60%-vol name gives up 18
#: points of expected return to a riskless one, which is roughly the trade a
#: concentrated retail book is actually making.
RISK_AVERSION = 1.0
#: Round-trip execution cost assumption for a retail ticket, in return units.
#: Commission-free venue, so this is spread + slippage only, and it is a floor:
#: a name whose quoted spread is wider gets charged the wider number.
RETAIL_ROUND_TRIP = 0.004
#: A rating tape older than this marks the analyst evidence `stale`.
STALE_COVERAGE_DAYS = pm_evidence.STALE_COVERAGE_DAYS

#: Sizing modes change RISK, never evidence.
MODES: dict[str, dict] = {
    "growth":      {"max_weight": 0.10, "max_names": 20, "kelly": 0.25,
                    "min_cash": 0.05},
    "high_growth": {"max_weight": 0.15, "max_names": 15, "kelly": 0.40,
                    "min_cash": 0.02},
    "moonshot":    {"max_weight": 0.25, "max_names": 12, "kelly": 0.60,
                    "min_cash": 0.00},
}
#: Don't churn the book for noise. A recommendation must move the weight by at
#: least this much before it becomes an instruction.
REBALANCE_BAND = 0.015
#: Below this dollar amount an instruction is not worth a commission or a click.
MIN_TICKET = 250.0

#: Names whose distribution is dominated by a single binary event. Crude by
#: design and overridable per position in the book file.
BINARY_HINTS = ("biotech", "pharmaceutical", "clinical", "therapeutics",
                "biosciences", "biopharma")

#: Minimum median dollar volume for a retail ticket to be routine.
RETAIL_ADV_FLOOR = 1_000_000.0
#: The ticket sizes the personal execution question is actually about.
RETAIL_TICKETS = (500.0, 10_000.0)


class BookError(ValueError):
    """A book that cannot be trusted to produce a dollar figure."""


# ─────────────────────────────── the book ──────────────────────────────────

@dataclass
class Position:
    """One holding.

    `shares` is the authoritative state of a CONFIRMED book. `dollars` is an
    unconfirmed reconstruction input and historical snapshot metadata only —
    it is never the live value of a confirmed position, because a number in a
    file does not move when the stock does. `cost_basis` is PER SHARE.

    `kill_condition` is a THESIS label for paper/shadow evaluation — never an
    armed exit, never an order path (signal_registry trailing-stop corpse,
    CANON §15). `kill_condition_provenance` says who wrote it:
    "murat_stated" | "auto_adopted_default" | "" (none on record) — see
    `kill_conditions.py`. `murat_override` is the attended slot where Murat
    replaces an auto-adopted default with his own words.
    """
    ticker: str
    shares: Optional[float] = None
    dollars: float = 0.0
    cost_basis: Optional[float] = None
    entry_date: Optional[str] = None
    thesis: str = ""
    kill_condition: str = ""
    kill_condition_provenance: str = ""
    murat_override: str = ""
    binary: Optional[bool] = None
    catalysts: list = field(default_factory=list)


@dataclass
class Book:
    """The account state.

    `cash` is Optional on purpose (NIGHT-13 §0): the YAML's `cash: null` (or an
    absent key) means UNRECOVERABLE, and the engine sweeps it as a sensitivity
    parameter over `config.CASH_SENSITIVITY_GRID` instead of silently equating
    unknown with zero — the house silent-fragility shape.

    `confirmed` is kept for backward compatibility, but it no longer gates
    `actionable`; it GRADES the evidence. See `evidence_grade`.
    """
    account: str
    confirmed: bool
    cash: Optional[float]
    sizing_mode: str
    wealth_targets: dict
    positions: list[Position]
    watchlist: list[str] = field(default_factory=list)
    closed: list[dict] = field(default_factory=list)
    as_of: Optional[str] = None
    source: str = ""

    @property
    def mode(self) -> dict:
        return MODES.get(self.sizing_mode, MODES["growth"])

    @property
    def evidence_grade(self) -> str:
        """How good the book's provenance is — an EVIDENCE axis, not a gate.

        "MURAT_CONFIRMED"          — Murat attested the positions and cash
        "BEST_EVIDENCE_UNCONFIRMED" — reconciled from the repo's own records
                                      (the best evidence available), without
                                      his attestation

        NIGHT-13 §0 retired `confirmed: true` as a BLOCKER: an unconfirmed
        book that loads and validates still prices proposals — they are
        labelled with this grade instead of being refused. Distinct from
        `mark_book`'s valuation_grade (live/reconstructed/degraded), which is
        about today's PRICES, not the book's provenance.
        """
        return "MURAT_CONFIRMED" if self.confirmed \
            else "BEST_EVIDENCE_UNCONFIRMED"


def validate_book(book: Book) -> list[str]:
    """Everything wrong with this book, as text. Empty list = usable.

    A CONFIRMED book is held to the standard of something you would place an
    order from: every open position carries a finite, positive share count, and
    cash is a real number. An unconfirmed book is allowed to be a sketch — it
    just may not produce an actionable ticket.
    """
    problems: list[str] = []
    seen: set[str] = set()
    for p in book.positions:
        t = (p.ticker or "").upper()
        if not t:
            problems.append("a position has no ticker")
            continue
        if t in seen:
            problems.append(f"{t}: duplicated in the book")
        seen.add(t)
        if p.shares is not None:
            if not is_finite(p.shares):
                problems.append(f"{t}: share count is not a finite number "
                                f"({p.shares!r})")
            elif float(p.shares) < 0:
                problems.append(f"{t}: negative share count ({p.shares})")
        if p.cost_basis is not None and not is_finite(p.cost_basis):
            problems.append(f"{t}: cost basis is not a finite number")
        if book.confirmed:
            if p.shares is None:
                problems.append(
                    f"{t}: confirmed book, but no share count. A confirmed "
                    f"position must mark to market; `dollars` cannot do that. "
                    f"Use shares_from_dollars() to convert, then check it.")
            elif is_finite(p.shares) and float(p.shares) == 0:
                problems.append(f"{t}: confirmed position with zero shares — "
                                f"move it to `closed:` instead")
    if book.cash is None:
        # Unknown cash is a declared sensitivity parameter for an unconfirmed
        # book (swept over config.CASH_SENSITIVITY_GRID). A CONFIRMED book is
        # order-ready by definition and must state its cash.
        if book.confirmed:
            problems.append("confirmed book with no cash balance — cash: null "
                            "is a sensitivity parameter for a best-evidence "
                            "book, not for an order-ready one")
    elif not is_finite(book.cash) or float(book.cash) < 0:
        problems.append(f"cash is not a usable number ({book.cash!r})")
    return problems


def load_book(path: Path | str | None = None, *, strict: bool = True) -> Book:
    """Load the book. A CONFIRMED book that fails validation raises.

    `cash: null` (or an absent cash key) loads as None — UNRECOVERABLE, to be
    swept as a sensitivity parameter — never as a silent 0.0. The book's
    `evidence_grade` is derived from `confirmed` here (see Book.evidence_grade).

    Kill-condition provenance: an explicit `kill_condition_provenance` in the
    file wins; a kill condition without one is Murat's own statement
    ("murat_stated") because the book file is his record — auto-adopted
    defaults are always written WITH explicit provenance. A filled
    `murat_override:` supersedes an auto-adopted default and re-grades the
    condition as murat_stated.
    """
    raw = yaml.safe_load(Path(path or BOOK_PATH).read_text(encoding="utf-8"))
    pos = [Position(**p) for p in raw.get("positions", [])]
    for p in pos:
        if p.murat_override:
            p.kill_condition = p.murat_override
            p.kill_condition_provenance = "murat_stated"
        elif p.kill_condition and not p.kill_condition_provenance:
            p.kill_condition_provenance = "murat_stated"
    raw_cash = raw.get("cash", None)
    book = Book(account=raw.get("account", "unknown"),
                confirmed=bool(raw.get("confirmed", False)),
                cash=(None if raw_cash is None else float(raw_cash)),
                sizing_mode=raw.get("sizing_mode", "growth"),
                wealth_targets=raw.get("wealth_targets", {}),
                positions=pos, watchlist=list(raw.get("watchlist", [])),
                closed=list(raw.get("closed", [])),
                as_of=str(raw.get("as_of", "")), source=raw.get("source", ""))
    problems = validate_book(book)
    if problems and book.confirmed and strict:
        raise BookError(
            "this book is marked confirmed: true but cannot be marked to "
            "market:\n  - " + "\n  - ".join(problems))
    if problems:
        logger.warning("book has %d unresolved problem(s): %s",
                       len(problems), "; ".join(problems[:4]))
    return book


def shares_from_dollars(dollars: float, price: float) -> dict:
    """Attended helper: convert a dollar placeholder into a share count.

    Deliberately NOT called anywhere in the decision path. Inferring a share
    count silently is how a placeholder becomes a fact — the conversion is
    printed, and a human types the result into the book file.
    """
    if not is_finite(dollars) or not is_finite(price) or float(price) <= 0:
        raise BookError(f"cannot convert {dollars!r} at price {price!r}")
    sh = float(dollars) / float(price)
    return {"shares": round(sh, 4), "dollars": float(dollars),
            "reference_price": float(price),
            "confirm": ("this is an ESTIMATE from a placeholder dollar amount, "
                        "not a fill. Replace it with the share count from your "
                        "broker before setting confirmed: true.")}


def mark_position(p: Position, price: Optional[float], *,
                  confirmed: bool) -> dict:
    """The live market value of one position, and how honestly it was obtained.

    Precedence, most to least trustworthy:
      1. shares × live price          — the only basis a confirmed book may use
      2. shares × cost basis          — priced=False, the quote is missing
      3. `dollars` placeholder        — unconfirmed books only
    """
    sh = float(p.shares) if (p.shares is not None and is_finite(p.shares)) else None
    px = float(price) if is_finite(price) and float(price or 0) > 0 else None
    if sh is not None and px is not None:
        return {"market_value": sh * px, "shares": sh, "price": px,
                "basis": "shares x live price", "priced": True, "stale": False,
                "gap": None}
    if sh is not None and p.cost_basis and is_finite(p.cost_basis):
        return {"market_value": sh * float(p.cost_basis), "shares": sh,
                "price": None, "basis": "shares x cost basis — NO LIVE PRICE",
                "priced": False, "stale": True, "gap": "no_quote"}
    if not confirmed and p.dollars and is_finite(p.dollars):
        return {"market_value": float(p.dollars), "shares": None, "price": px,
                "basis": "unconfirmed placeholder dollars — does NOT move with "
                         "the price", "priced": False, "stale": True,
                "gap": "no_shares" if px is not None else "no_shares_no_quote"}
    return {"market_value": 0.0, "shares": sh, "price": px,
            "basis": "unvalued — no shares and no placeholder", "priced": False,
            "stale": True, "gap": "no_shares_no_placeholder"}


def cash_sweep(invested: float) -> dict:
    """The NAV/weight consequences of an UNKNOWN cash balance, as a sweep.

    Cash fractions come from `config.CASH_SENSITIVITY_GRID` (fractions of the
    marked equity NAV). This REPORTS the grid and the ranges it implies; it
    never ranks the points and never picks one — a ranking over a convex sweep
    is a theorem, not a finding (counterfactual_replay.INTERPOLATING;
    conviction_replay.measure_mde's grid-report-never-pick pattern).
    """
    from backend.config import CASH_SENSITIVITY_GRID
    grid = tuple(sorted(CASH_SENSITIVITY_GRID))
    points = [{"cash_fraction": f, "cash": round(invested * f, 2),
               "nav": round(invested * (1.0 + f), 2)} for f in grid]
    return {
        "grid": list(grid),
        "unit": "cash as a fraction of the marked equity NAV",
        "points": points,
        "nav_range": {"low": round(invested * (1.0 + grid[0]), 2),
                      "high": round(invested * (1.0 + grid[-1]), 2)},
        "weight_scale_range": {
            # every equity weight scales by 1/(1+f); reported as a factor so
            # the whole sweep is two numbers per position, not a table per name
            "low": round(1.0 / (1.0 + grid[-1]), 4),
            "high": round(1.0 / (1.0 + grid[0]), 4)},
        "note": ("reported, never picked — no point in this sweep is 'best', "
                 "and nothing downstream may select one"),
    }


def mark_book(book: Book, prices: dict[str, Optional[float]]) -> dict:
    """Mark the whole book. NAV = cash + Σ market value.

    When `book.cash` is None (UNRECOVERABLE), the NAV is EQUITY-ONLY and says
    so (`nav_basis: "equity_only"`), and a `cash_sweep` reports what the NAV
    and weights would be across `config.CASH_SENSITIVITY_GRID` — a sensitivity
    report, never a silent `cash = 0`.
    """
    marks, invested = {}, 0.0
    no_quote, no_shares = [], []
    for p in book.positions:
        m = mark_position(p, prices.get(p.ticker), confirmed=book.confirmed)
        marks[p.ticker] = m
        invested += m["market_value"]
        if m["gap"] in ("no_quote", "no_shares_no_quote"):
            no_quote.append(p.ticker)
        if m["gap"] in ("no_shares", "no_shares_no_quote",
                        "no_shares_no_placeholder"):
            no_shares.append(p.ticker)
    stale = sorted(set(no_quote) | set(no_shares))
    cash_known = book.cash is not None
    nav = invested + (float(book.cash) if cash_known else 0.0)
    for t, m in marks.items():
        m["weight"] = (m["market_value"] / nav) if nav > 0 else 0.0
    if not stale:
        basis = "shares x live price"
    elif no_shares and not no_quote:
        basis = ("placeholder dollars — no share counts, so these values do "
                 "NOT move with the price")
    else:
        basis = "MIXED — some positions could not be marked to market"
    out = {"marks": marks, "invested": round(invested, 2),
           "cash": (round(float(book.cash), 2) if cash_known else None),
           "nav": round(nav, 2),
           "nav_basis": ("equity_plus_cash" if cash_known else "equity_only"),
           "unpriced": stale, "no_quote": no_quote, "no_shares": no_shares,
           "nav_complete": not stale,
           "basis": basis,
           # A different axis from Book.evidence_grade: valuation_grade says
           # how well TODAY'S PRICES marked the book (live / reconstructed /
           # degraded); evidence_grade says whose statement the BOOK itself is
           # (MURAT_CONFIRMED / BEST_EVIDENCE_UNCONFIRMED). Both are printed.
           "valuation_grade": ("live" if (book.confirmed and not stale)
                               else "reconstructed" if not book.confirmed
                               else "degraded")}
    if not cash_known:
        out["cash_note"] = ("UNRECOVERABLE — NAV is the marked equity only; "
                            "every weight is a share of that, not of the "
                            "account. See cash_sweep.")
        out["cash_sweep"] = cash_sweep(invested)
    return out


# ───────────────────────────── enrichment ──────────────────────────────────

def _days_since(d: Any) -> Optional[int]:
    if not d:
        return None
    try:
        dt = datetime.fromisoformat(str(d)[:10]).date()
    except ValueError:
        return None
    return (date.today() - dt).days


def _rating_drift(trend: Optional[list]) -> Optional[float]:
    """Change in the mean analyst rating between now and three months ago.

    Yahoo's trend rows are ordered 0m, -1m, -2m, -3m. A NEGATIVE drift on the
    1=strong-buy scale means the street got MORE positive, so the sign is
    flipped: positive output = improving.

    NOT a target revision. It counts ratings. See `analyst_ledger`.
    """
    if not trend or len(trend) < 2:
        return None

    def mean(row: dict) -> Optional[float]:
        w = {"strongBuy": 1, "buy": 2, "hold": 3, "sell": 4, "strongSell": 5}
        n = sum(int(row.get(k, 0) or 0) for k in w)
        if not n:
            return None
        return sum(int(row.get(k, 0) or 0) * v for k, v in w.items()) / n

    now, then = mean(trend[0]), mean(trend[-1])
    if now is None or then is None:
        return None
    return round(then - now, 4)


def _action_momentum(actions: Optional[list], days: int = 90) -> dict:
    """Net upgrades minus downgrades in the window, and how fresh the tape is."""
    up = down = 0
    freshest = None
    for a in actions or []:
        ds = _days_since(a.get("date"))
        if ds is None:
            continue
        freshest = ds if freshest is None else min(freshest, ds)
        if ds > days:
            continue
        act = str(a.get("action", "")).lower()
        if "up" in act:
            up += 1
        elif "down" in act:
            down += 1
    return {"upgrades_90d": up, "downgrades_90d": down, "net_90d": up - down,
            "days_since_last_action": freshest}


def enrich(ticker: str, position: Optional[Position] = None, *,
           record_snapshot: bool = False) -> dict:
    """One name's decision-relevant state, with the state of the EVIDENCE.

    v1 returned a single `available` flag that meant "we got a price". A name
    with a price and no consensus target was therefore `available: True`, got a
    target weight of zero, and was sold. BUILD-1.1 splits the flag into what it
    was always conflating:

      market_data_status   ok | missing
      analyst_data_status  ok | stale | missing | error
      distribution_status  ok | no_target | no_price | non_finite
      decisionable         all three usable -> a ticket is permitted

    `decisionable: False` on a held name can only ever produce REVIEW.
    """
    out: dict[str, Any] = {
        "ticker": ticker, "warnings": [], "missing_reasons": [],
        "market_data_status": "missing", "analyst_data_status": "missing",
        "distribution_status": "no_price", "decisionable": False,
        "source_count": 0,
    }
    try:
        from backend.services.analyst_intelligence import \
            get_analyst_intelligence
        ai = get_analyst_intelligence(ticker) or {}
        out["analyst_data_status"] = "ok" if ai else "missing"
        if not ai:
            out["missing_reasons"].append("analyst layer returned nothing")
    except Exception as e:                      # noqa: BLE001 - fail soft, loud
        out["warnings"].append(f"analyst layer unavailable: {e}")
        out["missing_reasons"].append(f"analyst layer error: {str(e)[:80]}")
        out["analyst_data_status"] = "error"
        ai = {}
    if ai:
        out["source_count"] = 1

    pt = ai.get("price_targets") or {}
    price = pt.get("current_price")
    if not is_finite(price):
        price = _fallback_price(ticker, out)
    if not is_finite(price) or float(price) <= 0:
        out["missing_reasons"].append("no usable current price")
        out["available"] = False
        return out

    out["market_data_status"] = "ok"
    out["available"] = True                      # legacy alias: market data only
    cons = ai.get("consensus_rating") or {}
    trend = ai.get("recommendation_trend")
    mom = _action_momentum(ai.get("recent_actions"))
    lo, mid, hi = pt.get("low"), pt.get("median") or pt.get("mean"), pt.get("high")
    lo = float(lo) if is_finite(lo) else None
    hi = float(hi) if is_finite(hi) else None
    mid = float(mid) if is_finite(mid) else None
    if mid is not None and mid <= 0:
        out["warnings"].append(f"malformed consensus target: {mid!r}")
        out["missing_reasons"].append("consensus target is not a positive price")
        mid = None

    binary = position.binary if position and position.binary is not None else None
    if binary is None:
        binary = _looks_binary(ticker, out)
    else:
        out["binary_check_ran"] = True           # declared in the book file

    ds_action = mom.get("days_since_last_action")
    if out["analyst_data_status"] == "ok" and ds_action is not None \
            and ds_action > STALE_COVERAGE_DAYS:
        out["analyst_data_status"] = "stale"
        out["missing_reasons"].append(
            f"analyst tape stale: {ds_action}d since the last rating action")

    out.update({
        "price": float(price),
        "target_low": lo, "target_median": mid, "target_high": hi,
        "target_mean": pt.get("mean"),
        "implied_upside": (mid / float(price) - 1.0) if mid else None,
        "dispersion": ((hi - lo) / mid) if (lo and hi and mid) else None,
        "n_analysts": cons.get("n_analysts"),
        "consensus_score": cons.get("score"),
        "consensus_label": cons.get("label"),
        "recommendation_counts": (trend[0] if trend else None),
        "rating_drift_3m": _rating_drift(trend),
        "rating_history_present": bool(trend and len(trend) >= 2),
        **mom,
        "binary_event_risk": bool(binary),
        "attribution": ai.get("attribution"),
        "evidence_grade": "observational — analyst consensus, not validated "
                          "by the Aegis research lab",
    })
    out["liquidity"] = _liquidity(ticker, price=float(price))
    out["annual_vol"] = _vol(ticker)             # forces the measurement here
    out["vol_measured"] = vol_is_measured(ticker)
    if not out["vol_measured"]:
        out["warnings"].append(
            f"volatility is the {FALLBACK_VOL:.0%} fallback, not a measurement "
            f"({VOL_FALLBACKS.get(ticker)}) — every weight for this name is "
            f"sized off a guess")

    # our own point-in-time target history, if we have started one for this name
    try:
        if record_snapshot:
            analyst_ledger.snapshot_if_new(ticker, out)
        rev = analyst_ledger.target_revisions(ticker)
    except Exception as e:                       # noqa: BLE001
        out["warnings"].append(f"analyst ledger unavailable: {e}")
        rev = {"history_available": False, "observations": 0}
    out["target_revisions"] = rev
    out["target_history_present"] = bool(rev.get("history_available"))

    if mid is None:
        out["distribution_status"] = "no_target"
        out["missing_reasons"].append("no consensus target -> no return "
                                      "distribution can be built")
    else:
        out["distribution_status"] = "ok"

    out["decisionable"] = (out["market_data_status"] == "ok"
                           and out["distribution_status"] == "ok"
                           and out["analyst_data_status"] in ("ok", "stale"))
    if not out["decisionable"] and not out["missing_reasons"]:
        out["missing_reasons"].append("evidence incomplete")
    out["evidence"] = pm_evidence.evidence_summary(out)
    return out


def _fallback_price(ticker: str, out: Optional[dict] = None) -> Optional[float]:
    """A last price when the analyst payload carries none. Never raises."""
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        return float(fi.get("last_price") or fi.get("lastPrice"))
    except Exception as e:                       # noqa: BLE001
        if out is not None:
            out["warnings"].append(f"no price: {e}")
        return None


def _looks_binary(ticker: str, out: Optional[dict] = None) -> bool:
    """Pre-revenue clinical/regulatory name?

    Silent-fragility audit: a failed fetch used to return `False`, which
    REMOVES the 0.60 extra haircut and therefore makes the position LARGER —
    the failure biased toward risk, in exactly the names where the risk is
    binary. The check now records that it did not run.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception as e:                       # noqa: BLE001
        logger.warning("%s: binary-event check did not run — %s", ticker,
                       str(e)[:80])
        if out is not None:
            out["warnings"].append(
                "binary-event check did not run (fetch failed); this name is "
                "treated as NON-binary, which is the LESS conservative "
                "assumption")
            out["binary_check_ran"] = False
        return False
    if out is not None:
        out["binary_check_ran"] = True
    blob = " ".join(str(info.get(k, "")) for k in
                    ("industry", "sector", "longBusinessSummary")).lower()
    pre_revenue = not (info.get("totalRevenue") or 0)
    return pre_revenue and any(h in blob for h in BINARY_HINTS)


#: A US equity quote wider than this is almost certainly an artifact, not a
#: market. Above it we say we do not know the spread.
MAX_PLAUSIBLE_SPREAD_BPS = 500.0
#: A two-share bid is not a market. One round lot is the minimum evidence that
#: somebody is actually standing there.
MIN_QUOTE_SIZE = 100
#: However bad the name, a round trip that costs more than this is a reason not
#: to trade it, not a number to quietly charge inside a comparison.
MAX_ROUND_TRIP = 0.05


def _quoted_spread(ticker: str) -> dict:
    """The real bid/ask if a source will give us one, else an honest absence.

    Two things had to be defended against here.

    First, v1 displayed the median intraday `(high - low) / close` beside the
    liquidity fields. That is the day's RANGE — routinely 8% for a 60%-vol
    microcap — and it is not a spread.

    Second, and worse, the quote itself lies out of hours. Yahoo returned AARD
    at bid 5.48 / ask 9.60 with a size of **two shares** while the stock last
    traded at 7.50: a 55% "spread" that, charged as a round trip, made every
    replacement comparison involving that name meaningless. A quote is
    therefore accepted only if it looks like a market — it brackets the last
    trade, it is not implausibly wide, and somebody is standing there in size.
    Otherwise the answer is `unavailable`, which is a fact, rather than a
    number, which would not be.
    """
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        bid, ask = info.get("bid"), info.get("ask")
        last = info.get("currentPrice") or info.get("regularMarketPrice")
        bs, as_ = info.get("bidSize"), info.get("askSize")
        if not (is_finite(bid) and is_finite(ask) and float(ask) > float(bid) > 0):
            return {"available": False,
                    "reason": "no usable bid/ask from any entitled source — "
                              "spread UNKNOWN, not assumed"}
        bid, ask = float(bid), float(ask)
        mid = (ask + bid) / 2.0
        bps = (ask - bid) / mid * 1e4
        rejects = []
        if bps > MAX_PLAUSIBLE_SPREAD_BPS:
            rejects.append(f"implausible width {bps:.0f}bps")
        if is_finite(last) and abs(mid - float(last)) / float(last) > 0.01:
            rejects.append(f"quote does not bracket the last trade "
                           f"(mid {mid:.2f} vs last {float(last):.2f})")
        size = min([s for s in (bs, as_) if is_finite(s)] or [0])
        if size < MIN_QUOTE_SIZE:
            rejects.append(f"size {size:g} below one round lot")
        if rejects:
            return {"available": False, "observed_bid": bid, "observed_ask": ask,
                    "observed_spread_bps": round(bps, 1),
                    "reason": "quote rejected as an artifact: "
                              + "; ".join(rejects)}
        return {"available": True, "bid": bid, "ask": ask,
                "spread_bps": round(bps, 1), "size": size,
                "source": "yfinance info bid/ask (delayed; validated against "
                          "the last trade and quote size)"}
    except Exception as e:                       # noqa: BLE001
        return {"available": False, "reason": f"quote fetch failed: {str(e)[:80]}"}


def _liquidity(ticker: str, price: Optional[float] = None) -> dict:
    """Can a $500-$10,000 ticket move without the spread eating the thesis?

    The retail question, not the institutional one. No capacity model, no
    square-root impact — those answer "how much can a fund deploy", which is
    not the question a $45k account asks (CANON §17: an execution number
    carries the model that produced it, and this one carries almost none).
    """
    out: dict[str, Any] = {"available": False}
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="1mo", auto_adjust=False)
        if h is None or h.empty:
            return {"available": False, "reason": "no recent history"}
        adv = float((h["Close"] * h["Volume"]).median())
        rng = float(((h["High"] - h["Low"]) / h["Close"]).median())
        out = {
            "available": True,
            "adv_dollar": round(adv, 0),
            "participation": {f"${int(t):,}": (round(t / adv, 6) if adv > 0 else None)
                              for t in RETAIL_TICKETS},
            # NOT a spread. Named so it cannot be mistaken for one again.
            "intraday_range_pct": round(rng * 100, 2),
            "intraday_range_note": "median (high-low)/close — a RANGE, not a "
                                   "quoted spread, and not a cost",
            "tradeable_at_retail_size": adv > RETAIL_ADV_FLOOR,
        }
    except Exception as e:                       # noqa: BLE001
        return {"available": False, "error": str(e)[:120]}

    q = _quoted_spread(ticker)
    out["quote"] = q
    # A conservative retail slippage assumption, explicitly labelled. If a real
    # spread exists we charge it; if not we charge a floor scaled by how thin
    # the name is, and we say that is what we did.
    if q.get("available"):
        rt = max(RETAIL_ROUND_TRIP, 2.0 * q["spread_bps"] / 1e4)
        basis = "2 x observed quoted spread"
    else:
        thin = 1.0 if out["tradeable_at_retail_size"] else 3.0
        penny = 2.0 if (price is not None and price < 5) else 1.0
        rt = RETAIL_ROUND_TRIP * thin * penny
        basis = ("assumption — no usable quote; floor scaled by ADV and price "
                 "level. Reason: " + str(q.get("reason", ""))[:90])
    capped = min(rt, MAX_ROUND_TRIP)
    out["assumed_round_trip_cost"] = round(capped, 5)
    out["assumed_round_trip_basis"] = basis
    out["round_trip_capped"] = capped < rt
    out["cost_grade"] = "OBSERVED" if q.get("available") else "ASSUMPTION"
    if capped < rt:
        out["cost_note"] = (f"uncapped estimate was {rt:.1%}; a round trip that "
                            f"expensive is a reason not to trade the name, not "
                            f"a number to charge inside a comparison")
    return out


# ────────────────────────────── the scoring ────────────────────────────────

def analyst_alpha(e: dict) -> dict:
    """A readable RANKING score for the analyst evidence on one name.

    Multiplicative in the things that should compound, additive-penalty in the
    things that should subtract.

    **It is not the sizing input.** BUILD-1.1 separated the two on purpose: a
    display score that mixes upside, breadth, freshness, dispersion, liquidity
    and price level into one number is useful for reading a table and is the
    wrong object to multiply a position size by. Sizing goes through
    `distribution()` — where breadth and freshness enter as a bounded
    reliability discount on the expected return, and dispersion and staleness
    do too. Both paths are shown so they can be checked against each other.
    """
    if not e.get("decisionable", e.get("available")):
        return {"score": None, "reason": "not decisionable",
                "missing": e.get("missing_reasons", [])}
    up = e.get("implied_upside")
    if up is None:
        return {"score": None, "reason": "no consensus target"}

    ev = e.get("evidence") or pm_evidence.evidence_summary(e)
    n = e.get("n_analysts")
    breadth, _ = pm_evidence._breadth(n)
    fresh, fresh_known = pm_evidence._freshness(e.get("days_since_last_action"))
    drift = e.get("rating_drift_3m") or 0.0
    revision = 1.0 + max(-0.5, min(0.5, drift))            # +-50% at most
    net = e.get("net_90d") or 0
    tape = 1.0 + max(-0.3, min(0.3, 0.06 * net))

    disp = e.get("dispersion")
    disp_pen = 0.0 if disp is None else min(0.40, max(0.0, (disp - 1.0) * 0.20))
    # unknown dispersion is not a free pass — see pm_evidence
    if disp is None:
        disp_pen = 0.05
    binary_pen = 0.25 if e.get("binary_event_risk") else 0.0
    liq = e.get("liquidity") or {}
    liq_pen = 0.0 if liq.get("tradeable_at_retail_size", True) else 0.30
    penny_pen = 0.20 if e["price"] < 5 else 0.0

    raw = max(0.0, up) * breadth * fresh * revision * tape
    penalty = disp_pen + binary_pen + liq_pen + penny_pen
    score = raw * max(0.0, 1.0 - penalty)
    return {
        "score": round(score, 4),
        "implied_upside": round(up, 4),
        "components": {"breadth": round(breadth, 3),
                       "freshness": round(fresh, 3),
                       "freshness_known": fresh_known,
                       "revision": round(revision, 3), "tape": round(tape, 3)},
        "penalties": {"dispersion": round(disp_pen, 3),
                      "binary_event": binary_pen, "liquidity": liq_pen,
                      "sub_5_dollar": penny_pen, "total": round(penalty, 3)},
        "reliability": ev["reliability"]["multiplier"],
        "is_ranking_only": True,
        "sizing_path": "distribution().expected_return -> target_weight()",
        "evidence_grade": "observational, unvalidated",
    }


def expected_return(e: dict) -> dict:
    """The one number the whole product rests on, built in one place.

        E[R] = haircut x analyst implied upside x reliability x revision tilt

    Every factor is bounded, printed, and labelled. Note what is NOT here:
    volatility. v1 derived the expected return from a lognormal whose *median*
    was the haircut upside, so `E[R] = median x exp(sigma^2/2)` — a 90%-vol
    name got a ~50% larger expected return than a 30%-vol name off the same
    analyst target, and then got a larger Kelly weight for it. Uncertainty is
    not a source of alpha.
    """
    up = e.get("implied_upside")
    if up is None or not is_finite(up):
        return {"available": False, "reason": "no consensus target"}
    hair = TARGET_HAIRCUT * ((1 - BINARY_EXTRA_HAIRCUT)
                             if e.get("binary_event_risk") else 1.0)
    ev = e.get("evidence") or pm_evidence.evidence_summary(e)
    rel = ev["reliability"]["multiplier"]
    tilt = ev["revision_tilt"]["multiplier"]
    mu = float(up) * hair * rel * tilt
    return {"available": True, "mu": mu, "haircut": round(hair, 4),
            "reliability": rel, "revision_tilt": tilt,
            "raw_implied_upside": round(float(up), 4),
            "interpretation": ("the street 12-month target, after haircut and "
                               "reliability, is the EXPECTED VALUE of the "
                               "12-month return — not its median, not a "
                               "scenario"),
            "grade": "OBSERVATIONAL, unvalidated"}


def distribution(e: dict) -> dict:
    """The 12-month return distribution: a fixed mean, and σ only widens it.

    One lognormal, parameterised from the expected return rather than from the
    median:

        E[R] = mu           (from `expected_return`, volatility-free)
        m     = ln(1 + mu) - sigma^2 / 2
        sigma^2 = ln(1 + vol^2)

    so `exp(m + sigma^2/2) - 1 == mu` by construction, for every sigma. Raising
    volatility now pushes the median DOWN and the tails OUT, leaving the mean
    where the evidence put it — which is the correct shape: a more volatile
    name with the same expected return is worse, and Kelly already knows that
    because sigma^2 is in its denominator.

    bear / base / bull are the 10th / 50th / 90th percentiles of that same
    distribution. The street's low/high may TIGHTEN them as scenario markers;
    the clamp is cosmetic and never touches the mean.
    """
    status = e.get("distribution_status")
    if status is None:                    # hand-built state (tests, callers)
        status = "ok" if e.get("target_median") else "no_target"
    if status != "ok" or e.get("price") is None:
        return {"available": False, "reason": status,
                "missing_reasons": e.get("missing_reasons", [])}
    er = expected_return(e)
    if not er.get("available"):
        return {"available": False, "reason": er.get("reason")}
    p = e["price"]
    mu = max(-0.95, float(er["mu"]))
    vol = _vol(e["ticker"])
    s = math.sqrt(math.log1p(vol ** 2))          # lognormal log-volatility
    m = math.log1p(mu) - 0.5 * s ** 2            # <- the fix: mean is pinned

    def q(z: float) -> float:
        return math.exp(m + s * z) - 1.0

    bear, base, bull = q(-1.2816), q(0.0), q(1.2816)
    lo_t, hi_t = e.get("target_low"), e.get("target_high")
    hair = er["haircut"]
    if lo_t:
        bear = max(bear, min(base, (float(lo_t) / p - 1.0) * hair))
    if hi_t:
        bull = min(bull, max(base, (float(hi_t) / p - 1.0) * hair))
    return {
        "available": True, "haircut": hair,
        "reliability": er["reliability"], "revision_tilt": er["revision_tilt"],
        "bear": round(bear, 4), "base": round(base, 4), "bull": round(bull, 4),
        "median_return": round(base, 4),
        "expected_return": round(mu, 4),
        "annual_vol": round(vol, 4),
        "certainty_equivalent": round(certainty_equivalent(mu, vol), 4),
        "construction": ("one lognormal with the MEAN pinned to haircut x "
                         "upside x reliability x tilt; sigma widens the "
                         "distribution and lowers the median but cannot move "
                         "the mean. bear/bull are its 10th/90th percentiles, "
                         "clamped by the street range as scenario markers"),
        "grade": "OBSERVATIONAL, unvalidated",
    }


def certainty_equivalent(mu: float, vol: float,
                         risk_aversion: float = RISK_AVERSION) -> float:
    """Mean-variance CE in expected-return units: mu - λσ²/2.

    The single currency in which a holding and a candidate can be compared to
    each other AND to a trading cost. v1 compared them in "analyst-alpha units"
    and then subtracted 40 basis points from the difference.
    """
    return float(mu) - 0.5 * float(risk_aversion) * float(vol) ** 2


_VOL_CACHE: dict[str, float] = {}
#: Tickers whose volatility is `FALLBACK_VOL` because the fetch failed, not
#: because it was measured. Surfaced in `model_status` — a fabricated sigma
#: changes every Kelly weight (w ∝ mu/sigma²) and must never be silent.
VOL_FALLBACKS: dict[str, str] = {}


def _vol(ticker: str) -> float:
    """Trailing annual volatility, or a LOUD fallback.

    Silent-fragility audit, BUILD-1.1: this used to swallow every exception,
    substitute `FALLBACK_VOL` and cache it forever. A single transient failure
    therefore replaced a measured 30% vol with a fabricated 65% for the life of
    the process, quartering that name's Kelly weight, and nothing anywhere said
    so. A failed fetch is now recorded, reported, and NOT cached — so the next
    call retries instead of inheriting a guess.
    """
    if ticker in _VOL_CACHE:
        return _VOL_CACHE[ticker]
    why = None
    v = None
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
        if h is None or len(h) <= 60:
            why = f"only {0 if h is None else len(h)} daily bars available"
        else:
            v = float(h["Close"].pct_change().std() * math.sqrt(252))
    except Exception as e:                       # noqa: BLE001
        why = f"history fetch failed: {str(e)[:80]}"
    if v is None or not is_finite(v) or v <= 0:
        why = why or f"computed volatility unusable ({v!r})"
        VOL_FALLBACKS[ticker] = why
        logger.warning("%s: using FALLBACK_VOL=%.2f — %s", ticker,
                       FALLBACK_VOL, why)
        return FALLBACK_VOL                      # deliberately NOT cached
    VOL_FALLBACKS.pop(ticker, None)
    _VOL_CACHE[ticker] = v
    return v


def vol_is_measured(ticker: str) -> bool:
    return ticker not in VOL_FALLBACKS
