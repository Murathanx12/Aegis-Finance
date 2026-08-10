"""Optimus Portfolio Manager — the engine that answers "what should I do today?"

This is a different product from the research lab, and it is deliberately not
subordinate to it. The lab asks *what evidence do we possess*. This asks *given
this actual book, this cash and this goal, what is the best action right now* —
and it is allowed to use information the lab has not validated, provided every
such number is LABELLED as observational.

Three rules the whole module obeys:

1. **Analyst targets are evidence, not truth.** Every implied upside is passed
   through an explicit haircut (`TARGET_HAIRCUT`) before it reaches a
   probability, and the haircut is printed next to the answer. Consensus targets
   are known to be optimistic on average; pretending otherwise is how a screener
   turns into a wish list.
2. **The LLM never sizes anything.** Sizing here is deterministic arithmetic on
   a return distribution, a correlation assumption and a per-mode cap.
3. **A stretch target is not an expected return.** The engine reports
   P(reach), P(floor breach) and expected drawdown together, always, and refuses
   to print the first without the other two.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import yaml

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


# ─────────────────────────────── the book ──────────────────────────────────

@dataclass
class Position:
    ticker: str
    dollars: float = 0.0
    shares: Optional[float] = None
    cost_basis: Optional[float] = None
    entry_date: Optional[str] = None
    thesis: str = ""
    kill_condition: str = ""
    binary: Optional[bool] = None


@dataclass
class Book:
    account: str
    confirmed: bool
    cash: float
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


def load_book(path: Path | str | None = None) -> Book:
    raw = yaml.safe_load(Path(path or BOOK_PATH).read_text(encoding="utf-8"))
    pos = [Position(**p) for p in raw.get("positions", [])]
    return Book(account=raw.get("account", "unknown"),
                confirmed=bool(raw.get("confirmed", False)),
                cash=float(raw.get("cash", 0.0)),
                sizing_mode=raw.get("sizing_mode", "growth"),
                wealth_targets=raw.get("wealth_targets", {}),
                positions=pos, watchlist=list(raw.get("watchlist", [])),
                closed=list(raw.get("closed", [])),
                as_of=str(raw.get("as_of", "")), source=raw.get("source", ""))


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


def enrich(ticker: str, position: Optional[Position] = None) -> dict:
    """One name's decision-relevant state. Degrades to `available: False`."""
    out: dict[str, Any] = {"ticker": ticker, "available": False,
                           "warnings": []}
    try:
        from backend.services.analyst_intelligence import \
            get_analyst_intelligence
        ai = get_analyst_intelligence(ticker) or {}
    except Exception as e:                      # noqa: BLE001 - fail soft, loud
        out["warnings"].append(f"analyst layer unavailable: {e}")
        ai = {}

    pt = ai.get("price_targets") or {}
    price = pt.get("current_price")
    if price is None:
        try:
            import yfinance as yf
            fi = yf.Ticker(ticker).fast_info
            price = float(fi.get("last_price") or fi.get("lastPrice"))
        except Exception as e:                  # noqa: BLE001
            out["warnings"].append(f"no price: {e}")
    if not price:
        return out

    cons = ai.get("consensus_rating") or {}
    trend = ai.get("recommendation_trend")
    mom = _action_momentum(ai.get("recent_actions"))
    lo, mid, hi = pt.get("low"), pt.get("median") or pt.get("mean"), pt.get("high")

    binary = position.binary if position and position.binary is not None else None
    if binary is None:
        binary = _looks_binary(ticker)

    out.update({
        "available": True,
        "price": float(price),
        "target_low": lo, "target_median": mid, "target_high": hi,
        "target_mean": pt.get("mean"),
        "implied_upside": (float(mid) / float(price) - 1.0) if mid else None,
        "dispersion": ((float(hi) - float(lo)) / float(mid))
        if (lo and hi and mid) else None,
        "n_analysts": cons.get("n_analysts"),
        "consensus_score": cons.get("score"),
        "consensus_label": cons.get("label"),
        "rating_drift_3m": _rating_drift(trend),
        **mom,
        "binary_event_risk": bool(binary),
        "attribution": ai.get("attribution"),
        "evidence_grade": "observational — analyst consensus, not validated "
                          "by the Aegis research lab",
    })
    out["liquidity"] = _liquidity(ticker)
    return out


def _looks_binary(ticker: str) -> bool:
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
    except Exception:                            # noqa: BLE001
        return False
    blob = " ".join(str(info.get(k, "")) for k in
                    ("industry", "sector", "longBusinessSummary")).lower()
    pre_revenue = not (info.get("totalRevenue") or 0)
    return pre_revenue and any(h in blob for h in BINARY_HINTS)


def _liquidity(ticker: str) -> dict:
    """Can a $500-$10,000 ticket move without the spread eating the thesis?"""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="1mo", auto_adjust=False)
        if h is None or h.empty:
            return {"available": False}
        adv = float((h["Close"] * h["Volume"]).median())
        rng = float(((h["High"] - h["Low"]) / h["Close"]).median())
        return {"available": True,
                "adv_dollar": round(adv, 0),
                # a retail ticket against median daily dollar volume
                "ticket_10k_participation": round(10_000 / adv, 6)
                if adv > 0 else None,
                "typical_daily_range_pct": round(rng * 100, 2),
                "tradeable_at_retail_size": adv > 1_000_000}
    except Exception as e:                       # noqa: BLE001
        return {"available": False, "error": str(e)[:120]}


# ────────────────────────────── the scoring ────────────────────────────────

def analyst_alpha(e: dict) -> dict:
    """The signal Murat actually traded, industrialised and penalised.

    Multiplicative in the things that should compound (upside x conviction x
    momentum), additive-penalty in the things that should subtract. Every term
    is in [0, 1] except the upside, so the score is readable.
    """
    if not e.get("available"):
        return {"score": None, "reason": "no data"}
    up = e.get("implied_upside")
    if up is None:
        return {"score": None, "reason": "no consensus target"}

    n = e.get("n_analysts") or 0
    breadth = min(1.0, math.log1p(n) / math.log1p(15))     # saturates near 15
    fresh_days = e.get("days_since_last_action")
    freshness = 1.0 if fresh_days is None else max(
        0.2, math.exp(-(fresh_days / 180.0)))
    drift = e.get("rating_drift_3m") or 0.0
    revision = 1.0 + max(-0.5, min(0.5, drift))            # +-50% at most
    net = e.get("net_90d") or 0
    tape = 1.0 + max(-0.3, min(0.3, 0.06 * net))

    disp = e.get("dispersion")
    disp_pen = 0.0 if disp is None else min(0.40, max(0.0, (disp - 1.0) * 0.20))
    binary_pen = 0.25 if e.get("binary_event_risk") else 0.0
    liq = e.get("liquidity") or {}
    liq_pen = 0.0 if liq.get("tradeable_at_retail_size", True) else 0.30
    penny_pen = 0.20 if e["price"] < 5 else 0.0

    raw = max(0.0, up) * breadth * freshness * revision * tape
    penalty = disp_pen + binary_pen + liq_pen + penny_pen
    score = raw * max(0.0, 1.0 - penalty)
    return {
        "score": round(score, 4),
        "implied_upside": round(up, 4),
        "components": {"breadth": round(breadth, 3),
                       "freshness": round(freshness, 3),
                       "revision": round(revision, 3), "tape": round(tape, 3)},
        "penalties": {"dispersion": round(disp_pen, 3),
                      "binary_event": binary_pen, "liquidity": liq_pen,
                      "sub_5_dollar": penny_pen, "total": round(penalty, 3)},
        "evidence_grade": "observational, unvalidated",
    }


def distribution(e: dict) -> dict:
    """The 12-month return distribution, built ONE way and read consistently.

    The first version of this function mixed two incompatible objects: a
    haircut analyst median for the base case and a raw two-sigma move for the
    bear case. Weighting those together made the expected return negative for
    almost every name in a high-volatility book, and the engine responded by
    recommending that nearly everything be sold. That was an artifact of the
    construction, not a view about the stocks.

    So the distribution is now a single lognormal, and every quoted point comes
    out of it:

      * its **median** 12-month return is `haircut x analyst implied upside`;
      * its **volatility** is the name's own trailing annual volatility;
      * bear / base / bull are the 10th / 50th / 90th percentiles OF THAT
        distribution, clamped by the analyst low/high so the street's own range
        can still tighten it.

    Because it is lognormal the mean sits above the median, which is the right
    shape for a book whose winners are supposed to pay for its losers. The
    haircut remains the single most consequential number here, and it remains an
    assumption rather than a measurement.
    """
    if not e.get("available") or not e.get("target_median"):
        return {"available": False}
    p = e["price"]
    hair = TARGET_HAIRCUT * ((1 - BINARY_EXTRA_HAIRCUT)
                             if e.get("binary_event_risk") else 1.0)
    median = (float(e["target_median"]) / p - 1.0) * hair
    vol = _vol(e["ticker"])
    s = math.sqrt(math.log1p(vol ** 2))          # lognormal log-volatility
    m = math.log1p(max(median, -0.95))

    def q(z: float) -> float:
        return math.exp(m + s * z) - 1.0

    bear, base, bull = q(-1.2816), q(0.0), q(1.2816)
    # the street's own range is allowed to TIGHTEN the tails, never widen them
    lo_t, hi_t = e.get("target_low"), e.get("target_high")
    if lo_t:
        bear = max(bear, min(base, (float(lo_t) / p - 1.0) * hair))
    if hi_t:
        bull = min(bull, max(base, (float(hi_t) / p - 1.0) * hair))
    mean = math.exp(m + 0.5 * s ** 2) - 1.0
    return {
        "available": True, "haircut": round(hair, 3),
        "bear": round(bear, 4), "base": round(base, 4), "bull": round(bull, 4),
        "expected_return": round(mean, 4),
        "annual_vol": round(vol, 4),
        "construction": ("one lognormal: median = haircut x analyst implied "
                         "upside, sigma = trailing annual vol; bear/bull are "
                         "its 10th/90th percentiles, clamped by the street "
                         "range"),
    }


_VOL_CACHE: dict[str, float] = {}


def _vol(ticker: str) -> float:
    if ticker in _VOL_CACHE:
        return _VOL_CACHE[ticker]
    v = FALLBACK_VOL
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
        if h is not None and len(h) > 60:
            v = float(h["Close"].pct_change().std() * math.sqrt(252))
    except Exception:                            # noqa: BLE001
        pass
    _VOL_CACHE[ticker] = v
    return v
