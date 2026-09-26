"""Give an LLM everything we know about 3,000 stocks and let it build a book.

    python -m scripts.llm_portfolio brief          # write the briefing
    python -m scripts.llm_portfolio freeze <file>  # commit a returned portfolio
    python -m scripts.llm_portfolio grade          # NAV every frozen book

WHAT THIS IS FOR (Murat, 2026-09-24)
====================================
> feed an LLM preferably Fable 5.1 ... it skims everything and makes portfolios,
> few of them very aggressive focused at maximizing ROI ... others still make
> portfolios based on beating sp500 ... full freedom, 1m for each paper account,
> no cap on how many stocks and how much to allocate ... timeline day-week-
> month-6months to see how the LLM performs and how the timing works.

The programme has spent five months asking "can I prove this factor works" and
the demonstrated edge is 0%. This asks a different question and it is a fair
one: **given everything we know, can a large model allocate better than the
machinery we built?** It is cheap to ask, it is graded by reality rather than by
a backtest, and a negative answer is as useful as a positive one because it
tells us the bottleneck is the INFORMATION, not the allocator.

THE THREE RULES THAT MAKE IT EVIDENCE INSTEAD OF A DEMO
=======================================================
1. **The briefing is point-in-time.** Every field is computable from data that
   existed at `asof`. If the model can see the future, the exercise measures
   nothing, and it will find the leak faster than we will.
2. **The portfolio is FROZEN before any outcome exists**, content-hashed, with
   the briefing's own hash recorded inside it. A book that gets edited after the
   first week is not a forecast. This is the same discipline the three licences
   impose on a `PRODUCT_EXPERIMENT` contract.
3. **It is graded against SPY and against our own machinery**, at every horizon
   it declared. "Beat the market" is the only claim that matters, and a book
   that returns +8% while SPY returns +11% has lost.

WHAT IS HONESTLY IN THE BRIEFING, AND WHAT IS NOT
=================================================
Murat's description assumed "analyst reviews, price targets and fair price
data". **Those are largely NOT available**: the price-target endpoint is 403 on
the free Finnhub tier (observed again on 2026-09-24 when the funnel rebuilt --
`stock/price-target` returned 403 for every one of 40 tickers), and no
fair-value vendor is provisioned. Saying otherwise inside a prompt would invite
the model to hallucinate the field, which is the failure mode this module is
most exposed to.

What IS real, and it is a lot:

* 24 price/volume features per name (`xs_ranker.FEATURES`) -- momentum at four
  horizons, realised vol, liquidity, Amihud illiquidity, distance from the
  52-week high and the 200-day, residual momentum, beta, drawdown, skew.
* Quarterly revenue growth, gross margin and margin CHANGE per name, from SEC
  filings dated by `filed` (`inflection`), including the fourth quarter that
  XBRL never tags and that nothing in this repo could see before 2026-09-24.
* The liquidity band and its empirical round-trip cost, so the model can be
  told what its own turnover will cost rather than discovering it later.
* Whether the name is currently flagged by the inflection detector, with the
  standing caveat that §63 found that detector has no dose-response.

THE COST MODEL IS NOT OPTIONAL AND IS NOT THE MODEL'S CHOICE
============================================================
`grade()` charges `xs_ranker.round_trip_bps` by liquidity band on entry. A book
of 200 microcaps that looks brilliant gross is a different object once it pays
35 bps a side, and letting the allocator ignore that would reproduce the exact
error that made the fleet lose $46,401 realised.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import numpy as np
import pandas as pd

from backend import config as _config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "llm_portfolio/1"

#: Every book starts here. Declared, not negotiable -- a model that sizes in
#: dollars needs to know the denominator, and comparing books at different
#: capital is comparing two things.
START_CAPITAL = 1_000_000.0

#: The horizons Murat named. Graded at each; a book does not have to "end" at
#: any of them, they are read-outs of the same running NAV.
HORIZON_DAYS = (1, 5, 21, 126)

#: A weight this small is a rounding error wearing a thesis. Not refused --
#: the brief promises "no cap on how many stocks" -- but reported, because a
#: 300-name book at 0.3% each is an index fund with extra steps and the receipt
#: should say so rather than leaving it to be discovered.
TINY_WEIGHT = 0.002


def ledger_dir() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "llm_portfolio"


def briefing_path(day: str | None = None) -> Path:
    return ledger_dir() / f"briefing_{day or date.today()}.json"


def books_path() -> Path:
    return ledger_dir() / "books.jsonl"


def _hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ────────────────────────────── the briefing ────────────────────────────────

def build_briefing(*, asof: Optional[Any] = None, max_names: int = 4000,
                   bars: Optional[pd.DataFrame] = None) -> dict:
    """Everything knowable at `asof`, one compact row per name.

    Rounded hard on purpose. A model reading 3,000 rows does not benefit from
    the ninth decimal of a z-score, and the token budget is better spent on
    coverage than on precision nobody can act on.
    """
    from backend.services import xs_ranker as XR

    asof_ts = pd.Timestamp(asof) if asof is not None else None
    if bars is None:
        bars = XR.load_bars(XR.survivorship_free_paths())
    if asof_ts is not None:
        bars = bars[bars["date"] <= asof_ts]
    panel = XR.build_panel(bars)
    # The LAST row per symbol is the only one an allocator can act on.
    live = (panel[panel["eligible"]].sort_values("date")
            .drop_duplicates("symbol", keep="last"))
    asof_real = str(live["date"].max())[:10]

    # Fundamentals, joined on `filed` so nothing arrives before it was public.
    fund: dict[str, dict] = {}
    try:
        from backend.services import inflection as INF
        q = INF.add_features(INF.quarterly_panel())
        if asof_ts is not None:
            q = q[q["filed"] <= asof_ts]
        q = q[q["sequential_ok"]].sort_values("filed").drop_duplicates(
            "ticker", keep="last")
        fires = set(INF.detect(q, min_acceleration=-9.99)["ticker"])
        for r in q.itertuples():
            fund[r.ticker] = {
                "rev_qoq": _r(r.rev_qoq), "rev_yoy": _r(r.rev_yoy),
                "gross_margin": _r(r.gm), "gross_margin_chg": _r(r.gm_chg),
                "last_filed": str(r.filed)[:10],
                "inflection_flag": r.ticker in fires,
            }
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("briefing: fundamentals unavailable (%s)", exc)

    rows = []
    for r in live.head(max_names).itertuples():
        row = {
            "t": r.symbol,
            "px": _r(r.close, 2),
            "band": XR.liquidity_band(r.median_dollar_vol),
            "cost_bps": round(XR.round_trip_bps(r.median_dollar_vol), 1),
            "dollar_vol_m": _r(r.median_dollar_vol / 1e6, 1),
            "mom_21": _r(r.mom_21), "mom_63": _r(r.mom_63),
            "mom_252_21": _r(r.mom_252_21),
            "vol_63": _r(r.vol_63), "beta_63": _r(r.beta_63),
            "vs_52w_high": _r(r.px_vs_52w_high), "vs_ma200": _r(r.px_vs_ma200),
            "drawdown_63": _r(r.max_drawdown_63), "skew_63": _r(r.skew_63),
            "amihud": _r(r.amihud, 6),
        }
        row.update(fund.get(r.symbol, {}))
        rows.append(row)

    brief = {
        "schema": SCHEMA_VERSION, "kind": "briefing",
        "asof": asof_real,
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "start_capital_usd": START_CAPITAL,
        "n_names": len(rows),
        "field_notes": {
            "mom_21/63/252_21": "trailing total return over that many sessions; 252_21 skips the last month",
            "vol_63": "annualised realised volatility over 63 sessions",
            "vs_52w_high": "fraction below the 52-week high (0 = at the high)",
            "cost_bps": "EMPIRICAL round-trip cost for this name's liquidity band. You pay it.",
            "rev_qoq / gross_margin_chg": "latest SEC quarter, dated by FILING date; Q4 is derived (annual minus Q1-Q3)",
            "inflection_flag": "revenue growing >15% sequentially WITH gross margin up >2pp",
        },
        "what_is_NOT_here": [
            "analyst price targets and consensus estimates -- the vendor endpoint "
            "is 403 on this tier, verified again 2026-09-24. Do not infer them.",
            "fair-value / DCF estimates -- no vendor is provisioned.",
            "news, filings text, transcripts, insider transactions, options data.",
            "sector and industry labels for the full universe.",
        ],
        "standing_findings_you_should_know": [
            "NEGATIVE_RESULTS §59: price/volume alone does not rank this cross-section at 21 sessions; the apparent edge lives in illiquidity and is smaller than the cost of trading it.",
            "§60: a six-ratio fundamental model came LAST of six and was negative at every book size.",
            "§61: extending the holding period to 126 sessions looked positive and was entirely 2025; drop that year and it is +0.12%.",
            "§62: eleven exit rules -- stops, trailing stops, take-profits -- ALL lost to simply holding. A -2% stop is 0.93 daily sigma for the median name and fires on 89% of positions.",
            "§63: the inflection detector above has NO dose-response; a bigger signal does not produce a bigger return. Treat inflection_flag as a description, not a prediction.",
        ],
        "rows": rows,
    }
    brief["briefing_hash"] = _hash(brief["rows"])
    return brief


def _r(v, nd: int = 4):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, nd)


# ───────────────────────────── freezing a book ──────────────────────────────

@dataclass
class Refusal(Exception):
    why: str

    def __str__(self) -> str:                                      # pragma: no cover
        return self.why


#: The kinds a book may declare. `twin` is minted by `twins()` only.
#: `control` (2026-09-26 review of chunks D+E): a book frozen because its rule
#: FAILED the freeze gate -- it accrues forward like any book, under a personal
#: book's constraints, but it is never a headline (name suffix `__control`).
KINDS = ("personal", "competition", "twin", "control")

#: An APPEND-ONLY void row (never an edit or a deletion of a book line). A
#: voided book is skipped by `grade`, the leaderboard, `paper_accounts_roi` and
#: `bridge_report`, and listed under "voided before entry" with its reason.
VOID_SCHEMA = "llm_portfolio/void"

#: A book whose `state` starts with this is a draft awaiting the human edit.
DRAFT_PREFIX = "DRAFT"

#: Draft provenance carried onto the frozen record, outside `book_id`.
PROVENANCE_KEYS = ("supersedes", "dropped_from_v0", "human_edits",
                   "twins_requested", "drafted_at")

#: Ordered keyword -> theme rules for positions that do not declare a `theme`.
#: Used only to pick the `sector_etf` twin's ETF; recorded as `inferred`.
THEME_KEYWORDS: tuple[tuple[str, str], ...] = (
    (r"pdufa|fda|bla\b|nda\b|phase 3|biotech|pharma|clinical|glp-1|obesity|bioprocess", "biotech"),
    (r"quantum", "quantum"),
    (r"uranium|nuclear|haleu|smr\b|reactor", "nuclear"),
    (r"lithium|battery", "lithium"),
    (r"betting|gambling|casino|sportsbook|prediction market|event-contract", "gambling"),
    (r"robot|actuator|humanoid|servo", "robotics"),
    (r"hbm|memory|dram|foundry|wafer|semicap|lithograph|chip|semiconductor|packaging|cowos", "semis"),
    (r"power|grid|turbine|cooling|data[- ]cent|utility", "power_grid"),
    (r"defen[cs]e|missile|rearmament", "defense"),
    (r"rare earth|minerals|mining|copper", "materials"),
    (r"oil|gas\b|lng|energy", "energy"),
)


def infer_theme(text: str) -> Optional[str]:
    import re
    low = (text or "").lower()
    for pat, theme in THEME_KEYWORDS:
        if re.search(pat, low):
            return theme
    return None


def is_etf(ticker: str, declared: Any = None) -> bool:
    if declared is True:
        return True
    t = str(ticker).upper()
    return (t in _config.BOOK_KNOWN_ETFS or t in set(_config.THEME_ETF_MAP.values())
            or t == _config.BOOK_WLS_PROXY)


def _split_falsifier(thesis: str) -> tuple[str, str]:
    """`"... Falsifier: X"` -> (thesis before, X). The draft embeds it that way."""
    import re
    m = re.search(r"\bfalsifier\s*:\s*", thesis or "", flags=re.I)
    if not m:
        return thesis or "", ""
    return thesis[:m.start()].strip(), thesis[m.end():].strip()


def constraints_for(kind: str) -> dict:
    if kind == "competition":
        return {"long_only": True,
                "max_weight": _config.BOOK_COMPETITION_MAX_WEIGHT,
                "min_names": _config.BOOK_COMPETITION_MIN_NAMES,
                "max_cash": _config.BOOK_COMPETITION_MAX_CASH,
                "no_etfs": True,
                "objective_must_name": _config.BOOK_COMPETITION_OBJECTIVE_MUST_NAME,
                "falsifier_required": True,
                "wls_membership_checked": False}
    if kind in ("personal", "control"):
        return {"long_only": True, "max_weight": None, "cash_declared": True,
                "falsifier_required": True}
    return {"long_only": True}


def freeze(book: dict, *, briefing: Optional[dict] = None,
           today: Optional[Any] = None,
           universe: Optional[Iterable[str]] = None,
           resolve: Optional[Callable[[list[str]], set]] = None,
           accept_draft: bool = False) -> dict:
    """Validate and commit a portfolio. After this it is evidence, not a draft.

    Refuses rather than repairs. A book that does not say what it holds, or
    whose weights do not add up, is not a forecast that can be graded, and
    silently normalising it would make the grade meaningless.

    `kind` (2026-09-25): `competition` = long only, <= 10%/name, >= 8 names, no
    ETFs, cash <= 2%, objective names "Relative P&L vs WLS"; `personal` = long
    only, no cap, CASH declared as a row. Both require a falsifier per name. A
    book with no `kind` is the legacy contract (recorded `kind_declared: False`).

    `universe` (the US panel's symbols) turns on the priceability check: a name
    outside it is refused unless `resolve` (normally `global_prices.resolve`)
    prices it. A book on a name nobody prices cannot be graded.

    Unknown top-level keys are ignored. The draft-provenance keys
    (`PROVENANCE_KEYS`: `supersedes`, `dropped_from_v0`, `human_edits`,
    `twins_requested`, `drafted_at`) are carried onto the record but are NOT
    part of `book_id`. A `DRAFT*` state refuses unless `accept_draft=True`, and
    then the record says `draft_accepted_by_override: True` beside that state.
    """
    name = str(book.get("name") or "").strip()
    if not name:
        raise Refusal("REFUSED: the book has no `name`. Books are compared to "
                      "each other and an unnamed one cannot be.")
    objective = str(book.get("objective") or "").strip()
    if not objective:
        raise Refusal("REFUSED: no `objective`. 'Maximise ROI' and 'beat SPY' "
                      "are different books and are graded differently.")
    pos = book.get("positions") or []
    if not pos:
        raise Refusal("REFUSED: no positions. An empty book is a decision to "
                      "hold cash and must say so explicitly as CASH 1.0.")
    state = str(book.get("state") or "")
    if state.upper().startswith(DRAFT_PREFIX) and not accept_draft:
        raise Refusal(f"REFUSED: state is {state!r}. A draft awaits its human "
                      f"edit; set `state` to READY after the edit, then freeze.")
    kind_raw = book.get("kind")
    kind = str(kind_raw or "personal").strip().lower()
    if kind not in KINDS:
        raise Refusal(f"REFUSED: kind {kind_raw!r} is not one of {KINDS}.")
    declared = kind_raw is not None
    if kind == "twin" and not book.get("parent_book_id"):
        raise Refusal("REFUSED: a twin without `parent_book_id` is a book "
                      "compared to nothing.")

    clean, seen = [], set()
    total = 0.0
    for p in pos:
        t = str(p.get("ticker") or "").strip().upper()
        if not t:
            raise Refusal(f"REFUSED: a position has no ticker: {p!r}")
        if t in seen:
            raise Refusal(f"REFUSED: {t} appears twice. Merge it or the weights "
                          f"do not mean what they say.")
        seen.add(t)
        try:
            w = float(p.get("weight"))
        except (TypeError, ValueError):
            raise Refusal(f"REFUSED: {t} has a non-numeric weight {p.get('weight')!r}")
        if not np.isfinite(w) or w < 0:
            raise Refusal(f"REFUSED: {t} weight {w} -- long-only for now; a short "
                          f"needs a borrow model this does not have.")
        total += w
        thesis = str(p.get("thesis") or "")
        falsifier = str(p.get("falsifier") or "").strip()
        if not falsifier:
            thesis, falsifier = _split_falsifier(thesis)
        theme = str(p.get("theme") or "").strip().lower() or None
        theme_src = "declared" if theme else None
        if theme is None and t in _config.BOOK_TICKER_THEMES:
            theme, theme_src = _config.BOOK_TICKER_THEMES[t], "ticker_map"
        if theme is None and t != "CASH":
            theme = infer_theme(thesis + " " + falsifier)
            theme_src = "inferred" if theme else None
        c = {"ticker": t, "weight": w, "thesis": thesis[:600]}
        if falsifier:
            c["falsifier"] = falsifier[:400]
        if theme:
            c["theme"], c["theme_source"] = theme, theme_src
        if p.get("is_etf") is True:
            c["is_etf"] = True
        clean.append(c)
    if not (0.98 <= total <= 1.02):
        raise Refusal(f"REFUSED: weights sum to {total:.4f}, not 1.0. This is "
                      f"not a rounding fix I am willing to make for you -- a "
                      f"book that is 40% cash by accident and 40% by intent are "
                      f"different books.")
    # Normalise the residual only inside the tolerance already accepted.
    for c in clean:
        c["weight"] = c["weight"] / total

    names = [c for c in clean if c["ticker"] != "CASH"]
    cash = sum(c["weight"] for c in clean if c["ticker"] == "CASH")
    cons = constraints_for(kind) if declared else {"long_only": True}
    if declared and cons.get("falsifier_required"):
        bare = [c["ticker"] for c in names if not c.get("falsifier")]
        if bare:
            raise Refusal(f"REFUSED: no falsifier on {bare[:10]}. Every position "
                          f"names the observation that would make it wrong.")
    if kind == "competition":
        mw = cons["max_weight"]
        over = [f"{c['ticker']} {c['weight']:.3f}" for c in names
                if c["weight"] > mw + 1e-6]
        if over:
            raise Refusal(f"REFUSED: competition max_weight is {mw:.2f}; over "
                          f"it: {over[:10]}")
        if len(names) < cons["min_names"]:
            raise Refusal(f"REFUSED: a competition book holds at least "
                          f"{cons['min_names']} names; this one holds {len(names)}.")
        if cash > cons["max_cash"] + 1e-6:
            raise Refusal(f"REFUSED: competition cash {cash:.3f} exceeds "
                          f"{cons['max_cash']:.2f}; cash earns nothing against WLS.")
        etfs = [c["ticker"] for c in names if is_etf(c["ticker"], c.get("is_etf"))]
        if etfs:
            raise Refusal(f"REFUSED: competition books hold no ETF: {etfs}")
        if cons["objective_must_name"].lower() not in objective.lower():
            raise Refusal(f"REFUSED: a competition objective must name "
                          f"{cons['objective_must_name']!r}; got {objective!r}.")
    if kind in ("personal", "control") and declared and not any(
            c["ticker"] == "CASH" for c in clean):
        raise Refusal("REFUSED: a personal book declares its cash as a CASH row "
                      "(weight 0 is a declaration; absence is not).")

    priced_by: dict = {"checked": universe is not None}
    if universe is not None:
        uni = {str(u).upper() for u in universe}
        missing = [c["ticker"] for c in names if c["ticker"] not in uni]
        resolved: set = set()
        if missing and resolve is not None:
            resolved = {str(x).upper() for x in (resolve(missing) or set())}
        still = [t for t in missing if t not in resolved]
        if still:
            raise Refusal(f"REFUSED: nobody prices {still[:15]} -- not in the US "
                          f"panel and not resolved by global_prices. A book on a "
                          f"name nobody prices cannot be graded.")
        priced_by.update({"us_panel": len(names) - len(missing),
                          "global_prices": sorted(resolved & set(missing))})

    parent_kind = book.get("parent_kind")
    bench = book.get("benchmark") or (
        _config.BOOK_WLS_PROXY if "competition" in (kind, parent_kind) else "SPY")
    rec = {
        "schema": SCHEMA_VERSION, "kind": kind if declared else "personal",
        "kind_declared": declared,
        "constraints": cons,
        "name": name, "objective": objective,
        "model": str(book.get("model") or "unknown"),
        "strategy": str(book.get("strategy") or "")[:2000],
        "what_i_did_not_buy": book.get("what_i_did_not_buy") or [],
        "horizon_days": book.get("horizon_days") or list(HORIZON_DAYS),
        "frozen_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asof": str(today or date.today()),
        "start_capital_usd": START_CAPITAL,
        "benchmark": bench,
        "n_positions": len(clean),
        "n_tiny_positions": sum(1 for c in clean if c["weight"] < TINY_WEIGHT),
        "max_weight": max(c["weight"] for c in clean),
        "cash_weight": round(cash, 6),
        "briefing_hash": (briefing or {}).get("briefing_hash"),
        "briefing_asof": (briefing or {}).get("asof"),
        "priced_by": priced_by,
        "positions": clean,
    }
    for k in ("parent_book_id", "parent_kind", "twin", "source", "parse",
              "evidence_hash", "prompt_hash", "freeze_gate") + PROVENANCE_KEYS:
        if book.get(k) is not None:
            rec[k] = book[k]
    if state:
        rec["state"] = state
    if state.upper().startswith(DRAFT_PREFIX):
        rec["draft_accepted_by_override"] = True
    if book.get("max_weight") is not None:
        # The draft's DECLARED cap, beside the realised `max_weight`.
        rec["declared_max_weight"] = book["max_weight"]
    rec["book_id"] = _hash({k: rec[k] for k in ("name", "positions", "asof")})
    return rec


# ───────────────────────────────── twins ────────────────────────────────────

#: A random twin draws only names whose last bar is at most this many calendar
#: days before `asof` -- a name that stopped trading is not a live alternative.
TWIN_LIVE_DAYS = 10


def liquidity_bands(bars: pd.DataFrame, *, asof: Any,
                    window: int = 63) -> dict[str, str]:
    """Band per symbol from the median dollar volume of the `window` sessions
    up to `asof` -- the same bands `xs_ranker.round_trip_bps` charges."""
    from backend.services import xs_ranker as XR
    b = bars[bars["date"] <= pd.Timestamp(asof)]
    if b.empty:
        return {}
    b = b.sort_values(["symbol", "date"]).groupby("symbol").tail(window)
    mdv = (b["close"] * b["volume"]).groupby(b["symbol"]).median()
    return {s: XR.liquidity_band(float(v)) for s, v in mdv.items()}


def _live_pool(bars: pd.DataFrame, asof: Any, exclude: set) -> list[str]:
    from backend.services import xs_ranker as XR
    a = pd.Timestamp(asof)
    b = bars[bars["date"] <= a]
    if b.empty:
        return []
    last = b.sort_values("date").groupby("symbol").tail(1)
    ok = last[(last["date"] >= a - pd.Timedelta(days=TWIN_LIVE_DAYS))
              & (last["close"] >= XR.MIN_PRICE)]
    return sorted(s for s in ok["symbol"]
                  if s not in exclude and s not in XR.INDEX_PROXIES
                  and not is_etf(s) and s != "CASH")


def twins(book: dict, *, asof: Any, seed: int,
          bars: Optional[pd.DataFrame] = None,
          ai_draft: Optional[dict] = None) -> dict[str, dict]:
    """The comparison books a frozen book is graded beside, each frozen.

    * `ew` -- the same non-cash names, equal weight, fully invested.
    * `sector_etf` -- each name's theme ETF (`THEME_ETF_MAP`) at the theme's
      weight, fully invested. Beating it means the PICKS added something.
    * `spy` (personal) / `urth` (competition, the WLS proxy) -- the market.
    * `random_same_band` -- every name replaced one-for-one by a random live
      name from the same liquidity band, SAME weight, same cash. Isolates
      selection from sizing and liquidity. `np.random.default_rng(seed)`.
    * `ai_only` -- only when `ai_draft` is given: the draft's positions exactly.
    """
    if not book.get("book_id"):
        raise Refusal("REFUSED: twins are minted from a FROZEN book (it has no "
                      "book_id). Freeze the parent first.")
    if bars is None:
        raise Refusal("REFUSED: twins need the price panel -- the random twin "
                      "draws from live names in the parent's liquidity bands.")
    parent_kind = book.get("kind")
    competition = parent_kind == "competition"
    names = [p for p in book["positions"] if p["ticker"] != "CASH"]
    cash = [p for p in book["positions"] if p["ticker"] == "CASH"]
    if not names:
        raise Refusal("REFUSED: an all-cash book has nothing to twin.")
    default_etf = (_config.BOOK_WLS_PROXY if competition
                   else _config.THEME_ETF_MAP.get("default", "SPY"))

    def _mk(twin: str, positions: list[dict]) -> dict:
        return freeze({
            "name": f"{book['name']}__{twin}", "kind": "twin", "twin": twin,
            "objective": f"twin of {book['name']}: {book['objective']}",
            "strategy": f"{twin} twin of {book['book_id']}",
            "model": "twin", "parent_book_id": book["book_id"],
            "parent_kind": parent_kind, "benchmark": book.get("benchmark"),
            "horizon_days": book.get("horizon_days"),
            "positions": positions}, today=asof)

    out: dict[str, dict] = {}
    n = len(names)
    out["ew"] = _mk("ew", [{"ticker": p["ticker"], "weight": 1.0 / n,
                            "thesis": "equal weight"} for p in names])

    nw = sum(p["weight"] for p in names)
    etf_w: dict[str, float] = {}
    for p in names:
        theme = p.get("theme") or infer_theme(p.get("thesis", ""))
        etf = (_config.THEME_ETF_MAP.get(theme, default_etf)
               if theme and theme != "default" else default_etf)
        etf_w[etf] = etf_w.get(etf, 0.0) + p["weight"] / nw
    out["sector_etf"] = _mk("sector_etf", [
        {"ticker": e, "weight": w, "thesis": "theme ETF at the theme weight"}
        for e, w in sorted(etf_w.items())])

    bench_key = "urth" if competition else "spy"
    out[bench_key] = _mk(bench_key, [{"ticker": default_etf if competition else "SPY",
                                      "weight": 1.0, "thesis": "the market"}])

    rng = np.random.default_rng(seed)
    bands = liquidity_bands(bars, asof=asof)
    pool = _live_pool(bars, asof, {p["ticker"] for p in names})
    by_band: dict[str, list[str]] = {}
    for s in pool:
        by_band.setdefault(bands.get(s, "small"), []).append(s)
    chosen: set = set()
    rnd = []
    for p in sorted(names, key=lambda x: x["ticker"]):
        cands = [s for s in by_band.get(bands.get(p["ticker"], ""), []) if s not in chosen]
        if not cands:
            cands = [s for s in pool if s not in chosen]
        if not cands:
            raise Refusal("REFUSED: the random twin ran out of live names.")
        pick = str(cands[int(rng.integers(len(cands)))])
        chosen.add(pick)
        rnd.append({"ticker": pick, "weight": p["weight"],
                    "thesis": f"random same-band replacement for {p['ticker']}"})
    rnd += [{"ticker": "CASH", "weight": c["weight"], "thesis": "parent's cash"}
            for c in cash]
    out["random_same_band"] = _mk("random_same_band", rnd)

    if ai_draft is not None:
        out["ai_only"] = _mk("ai_only", [
            {"ticker": p["ticker"], "weight": p["weight"],
             "thesis": p.get("thesis", ""), "falsifier": p.get("falsifier")}
            for p in ai_draft.get("positions", [])])
    return out


def append_book(rec: dict) -> Path:
    p = books_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
    return p


def _read_lines(path: Optional[Path] = None) -> list[dict]:
    p = Path(path) if path else books_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                x = json.loads(line)
            except ValueError:
                continue
            if isinstance(x, dict):
                out.append(x)
    return out


def void_rows(path: Optional[Path] = None) -> dict[str, dict]:
    """book_id -> its (first) void row. A book is voided once; later rows for
    the same id are ignored (and `void` refuses to write them)."""
    out: dict[str, dict] = {}
    for x in _read_lines(path):
        if x.get("schema") == VOID_SCHEMA and x.get("book_id") and x["book_id"] not in out:
            out[x["book_id"]] = x
    return out


def read_books(path: Optional[Path] = None, *, include_voided: bool = False) -> list[dict]:
    """Every frozen book record, in ledger order. Void rows are never books.

    A VOIDED book is left out unless `include_voided`, in which case it comes
    back carrying `void` = its void row. `grade` refuses to grade such a record
    and the leaderboard lists it under `voided_before_entry`.
    """
    lines = _read_lines(path)
    voids: dict[str, dict] = {}
    for x in lines:
        if x.get("schema") == VOID_SCHEMA and x.get("book_id") and x["book_id"] not in voids:
            voids[x["book_id"]] = x
    out = []
    for x in lines:
        if x.get("schema") == VOID_SCHEMA:
            continue
        v = voids.get(x.get("book_id"))
        if v is not None:
            if not include_voided:
                continue
            x = {**x, "void": v}
        out.append(x)
    return out


def voided_before_entry(path: Optional[Path] = None) -> list[dict]:
    """The voided books, one line each: what a report lists instead of grading."""
    return [{"book_id": v["book_id"], "name": v.get("name"), "reason": v.get("reason"),
             "voided_utc": v.get("voided_utc"), "who": v.get("who")}
            for v in void_rows(path).values()]


def void(book_id: str, reason: str, *, who: str, path: Optional[Path] = None,
         now: Optional[datetime] = None, allow_after_entry: bool = False) -> dict:
    """APPEND a void row for `book_id`. Never edits or deletes a line.

    Refuses: an unknown id, a twin (void the parent; its twins stay as the
    controls they are), an id already voided, an empty reason or `who`, and --
    unless `allow_after_entry` -- a book whose entry session (the first weekday
    after `asof`) has already opened: CLAUDE.md rule 5 protects forward
    FAILURES, and voiding a book after it traded would delete one.
    """
    if not str(reason or "").strip() or not str(who or "").strip():
        raise Refusal("REFUSED: a void names its reason and who voided it.")
    lines = _read_lines(path)
    rec = next((x for x in lines if x.get("schema") != VOID_SCHEMA
                and x.get("book_id") == book_id), None)
    if rec is None:
        raise Refusal(f"REFUSED: no book {book_id!r} in the ledger.")
    if rec.get("kind") == "twin" or rec.get("parent_book_id"):
        raise Refusal(f"REFUSED: {rec.get('name')} is a twin; void its parent.")
    if book_id in void_rows(path):
        raise Refusal(f"REFUSED: {rec.get('name')} is already voided.")
    now = now or datetime.now(timezone.utc)
    entry = pd.Timestamp(rec["asof"]) + pd.offsets.BDay(1)
    if not allow_after_entry and pd.Timestamp(now.date()) >= entry:
        raise Refusal(f"REFUSED: {rec.get('name')} entered on {entry.date()}; a book that "
                      f"has traded is graded, not voided.")
    row = {"schema": VOID_SCHEMA, "kind": "void", "book_id": book_id,
           "name": rec.get("name"), "reason": str(reason),
           "voided_utc": now.isoformat(timespec="seconds"), "who": str(who),
           "entry_session": str(entry.date())}
    p = Path(path) if path else books_path()
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")
    return row


# ──────────────────────────────── grading ───────────────────────────────────

def benchmark_of(rec: dict) -> str:
    """SPY for personal books, the WLS proxy for competition books and their
    twins. A benchmark written into the record wins."""
    if rec.get("benchmark"):
        return str(rec["benchmark"])
    if "competition" in (rec.get("kind"), rec.get("parent_kind")):
        return _config.BOOK_WLS_PROXY
    return "SPY"


def _entry_mdv(g: pd.DataFrame, j: int, window: int = 63) -> Optional[float]:
    """Median dollar volume of the `window` sessions BEFORE entry -- what was
    knowable when the order went in. Raw bars carry no such column, and before
    2026-09-25 a missing value fell to the `small` band (35 bps) for every name."""
    if "median_dollar_vol" in g.columns:
        v = g["median_dollar_vol"].iloc[j]
        return float(v) if pd.notna(v) else None
    lo = max(0, j - window)
    if j - lo < 5:
        return None
    dv = (g["close"].iloc[lo:j] * g["volume"].iloc[lo:j]).astype(float)
    m = float(dv.median())
    return m if np.isfinite(m) else None


def grade(rec: dict, bars: pd.DataFrame, *, today: Optional[Any] = None) -> dict:
    """NAV the book forward from its own as-of date, net of entry cost.

    Entry is the OPEN of the session after `asof`, which is the first price the
    book could actually have been filled at. A book priced at the close of its
    own decision date has already been given the day it was deciding on.

    Sessions are counted on the BENCHMARK's calendar when the benchmark is in
    `bars` (SPY, or URTH for competition books): a union of US and Asian
    calendars would count a Taiwan-only session as a US one.
    """
    from backend.services import xs_ranker as XR

    bench_sym = benchmark_of(rec)
    if rec.get("void"):
        v = rec["void"]
        return {"book_id": rec["book_id"], "name": rec["name"], "kind": rec.get("kind"),
                "twin": rec.get("twin"), "parent_book_id": rec.get("parent_book_id"),
                "benchmark": bench_sym, "status": "VOIDED",
                "why": f"voided before entry {v.get('voided_utc')}: {v.get('reason')}"}
    start = pd.Timestamp(rec["asof"])
    px = {s: g.sort_values("date").reset_index(drop=True)
          for s, g in bars.groupby("symbol", sort=False)}
    bench = px.get(bench_sym)
    cal = bench["date"] if bench is not None and len(bench) else bars["date"]
    dates = np.sort(pd.Series(cal).unique()).astype("datetime64[ns]")
    if today is not None:
        dates = dates[dates <= np.datetime64(pd.Timestamp(today), "ns")]
    i0 = int(np.searchsorted(dates, np.datetime64(start, "ns"), side="right"))
    base = {"book_id": rec["book_id"], "name": rec["name"],
            "kind": rec.get("kind"), "twin": rec.get("twin"),
            "parent_book_id": rec.get("parent_book_id"),
            "benchmark": bench_sym}
    if i0 >= len(dates):
        return {**base, "status": "PENDING",
                "why": "no session has opened since it was frozen"}

    held, missing, cost_bps = [], [], 0.0
    for p in rec["positions"]:
        t = p["ticker"]
        if t == "CASH":
            held.append((t, p["weight"], None, None))
            continue
        g = px.get(t)
        if g is None:
            missing.append(t)
            continue
        d = g["date"].values.astype("datetime64[ns]")
        j = int(np.searchsorted(d, dates[i0], side="left"))
        if j >= len(d):
            missing.append(t)
            continue
        o = float(g["open"].iloc[j])
        if not np.isfinite(o) or o <= 0:
            missing.append(t)
            continue
        cost_bps += p["weight"] * XR.round_trip_bps(_entry_mdv(g, j))
        held.append((t, p["weight"], g, j))

    if not held:
        return {**base, "status": "REFUSED",
                "why": f"no position could be priced; missing {missing[:10]}"}

    # A book whose names we cannot price is NOT silently re-weighted onto the
    # ones we can. That would grade a different book than the one frozen.
    priced_w = sum(w for _t, w, _g, _j in held)
    proxy = bench_sym == _config.BOOK_WLS_PROXY
    out = {**base, "objective": rec["objective"], "model": rec.get("model"),
           "asof": rec["asof"], "status": "OK",
           "n_positions": rec["n_positions"],
           "n_unpriceable": len(missing), "unpriceable": missing[:20],
           "weight_priced": round(priced_w, 4),
           # Charged ONCE, on entry, at the empirical band cost. Half of a round
           # trip, because the book has not sold yet.
           "entry_cost_bps": round(cost_bps / 2.0, 1),
           "benchmark_is_proxy": proxy,
           "caveat": _config.BOOK_WLS_PROXY_CAVEAT if proxy else None,
           "horizons": {}}

    def _nav_at(asof_d):
        tot = 0.0
        for _t, w, g, j in held:
            if g is None:                       # CASH earns nothing here
                tot += w
                continue
            d = g["date"].values.astype("datetime64[ns]")
            k = int(np.searchsorted(d, asof_d, side="right")) - 1
            if k < j:
                tot += w                        # no price yet: held flat, not dropped
                continue
            tot += w * float(g["close"].iloc[k]) / float(g["open"].iloc[j])
        gross = tot / priced_w - 1.0 if priced_w else None
        net = gross - (cost_bps / 2.0) / 10_000.0 if gross is not None else None
        b = None
        if bench is not None:
            sd = bench["date"].values.astype("datetime64[ns]")
            a = int(np.searchsorted(sd, dates[i0], side="left"))
            z = int(np.searchsorted(sd, asof_d, side="right")) - 1
            if 0 <= a < len(sd) and a <= z:
                b = float(bench["close"].iloc[z]) / float(bench["open"].iloc[a]) - 1.0
        return gross, net, b

    def _cell(asof_d) -> dict:
        gross, net, b = _nav_at(asof_d)
        vs = (net - b) if (net is not None and b is not None) else None
        return {"status": "OK", "gross": gross, "net": net,
                "nav_usd": round(START_CAPITAL * (1.0 + (net or 0.0)), 2),
                "benchmark_return": b, "vs_benchmark": vs,
                # kept for readers of the 09-24 receipts
                "spy": b if bench_sym == "SPY" else None,
                "vs_spy": vs if bench_sym == "SPY" else None,
                "as_of": str(pd.Timestamp(asof_d))[:10]}

    for h in (rec.get("horizon_days") or HORIZON_DAYS):
        h = int(h)
        i1 = i0 + h - 1
        if i1 > len(dates) - 1:
            out["horizons"][h] = {"status": "PENDING",
                                  "why": f"needs {h} sessions, has {len(dates)-i0}"}
            continue
        out["horizons"][h] = _cell(dates[i1])
    out["to_date"] = {**_cell(dates[-1]), "sessions": len(dates) - i0}
    return out


# ────────────────────────────── the leaderboard ─────────────────────────────

def union_bars(us: Optional[pd.DataFrame], glob: Optional[pd.DataFrame]) -> pd.DataFrame:
    """US panel and global cache, ONE source per symbol: whichever reaches the
    later date (the US panel on a tie). Never interleaves two vendors' rows for
    one symbol, which would splice an adjusted series onto an unadjusted one."""
    cols = ["symbol", "date", "open", "high", "low", "close", "volume"]
    frames = [f[[c for c in cols if c in f.columns]] for f in (us, glob)
              if f is not None and len(f)]
    if not frames:
        return pd.DataFrame(columns=cols)
    if len(frames) == 1:
        return frames[0].reset_index(drop=True)
    u, g = frames
    lu = u.groupby("symbol")["date"].max()
    lg = g.groupby("symbol")["date"].max()
    take_g = {s for s, d in lg.items() if s not in lu.index or d > lu[s]}
    out = pd.concat([u[~u["symbol"].isin(take_g)], g[g["symbol"].isin(take_g)]],
                    ignore_index=True)
    return out.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def book_tickers(books: Iterable[dict]) -> set[str]:
    """Every ticker a set of books (and their benchmarks) needs priced."""
    out: set[str] = set()
    for b in books:
        out.add(benchmark_of(b))
        out.update(p["ticker"] for p in b.get("positions", []) if p["ticker"] != "CASH")
    return out


TWIN_TYPES = ("ew", "sector_etf", "random_same_band", "ai_only")


def leaderboard(books: list[dict], bars: pd.DataFrame, *,
                today: Optional[Any] = None,
                voided: Optional[list[dict]] = None) -> dict:
    """Grade every book and twin; compare each parent to its own twins.

    `vs_<twin>` = parent's to-date net minus that twin's to-date net over the
    same window. Positive means the parent beat the twin.

    A voided book (a record carrying `void`) is not graded; it is listed under
    `voided_before_entry`. `voided` defaults to the ledger's void rows, so a
    caller that read the books without them still gets the list.
    """
    vb = [b for b in books if b.get("void")]
    books = [b for b in books if not b.get("void")]
    if voided is None:
        voided = voided_before_entry()
    seen = {v["book_id"] for v in voided}
    voided = list(voided) + [
        {"book_id": b["book_id"], "name": b.get("name"), "reason": b["void"].get("reason"),
         "voided_utc": b["void"].get("voided_utc"), "who": b["void"].get("who")}
        for b in vb if b["book_id"] not in seen]
    grades = [grade(b, bars, today=today) for b in books]
    twins_of: dict[str, dict] = {}
    for g in grades:
        if g.get("parent_book_id"):
            twins_of.setdefault(g["parent_book_id"], {})[g.get("twin")] = g

    def _td(g: Optional[dict]) -> Optional[float]:
        if not g or g.get("status") != "OK":
            return None
        return (g.get("to_date") or {}).get("net")

    rows = []
    for g in grades:
        td = g.get("to_date") or {}
        row = {"book_id": g["book_id"], "name": g["name"], "kind": g.get("kind"),
               "twin": g.get("twin"), "parent_book_id": g.get("parent_book_id"),
               "status": g.get("status"), "why": g.get("why"),
               "benchmark": g.get("benchmark"),
               "benchmark_is_proxy": g.get("benchmark_is_proxy"),
               "sessions": td.get("sessions"),
               "net_to_date": td.get("net"), "nav_usd": td.get("nav_usd"),
               "benchmark_to_date": td.get("benchmark_return"),
               "vs_benchmark": td.get("vs_benchmark"),
               "n_unpriceable": g.get("n_unpriceable"),
               "entry_cost_bps": g.get("entry_cost_bps")}
        if not g.get("parent_book_id"):
            mine = _td(g)
            for tname in TWIN_TYPES:
                other = _td(twins_of.get(g["book_id"], {}).get(tname))
                row[f"vs_{tname}"] = (mine - other if mine is not None
                                      and other is not None else None)
        rows.append(row)

    by_kind: dict[str, dict] = {}
    for r in rows:
        if r["parent_book_id"]:
            continue
        k = by_kind.setdefault(r["kind"] or "personal",
                               {"n_books": 0, "n_graded": 0, "n_beat_benchmark": 0,
                                "mean_vs_benchmark": None, "_v": []})
        k["n_books"] += 1
        if r["vs_benchmark"] is not None:
            k["n_graded"] += 1
            k["_v"].append(r["vs_benchmark"])
            k["n_beat_benchmark"] += int(r["vs_benchmark"] > 0)
    for k in by_kind.values():
        v = k.pop("_v")
        k["mean_vs_benchmark"] = float(np.mean(v)) if v else None

    return {"schema": SCHEMA_VERSION, "kind": "leaderboard",
            "graded_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bars_through": (str(pd.Timestamp(bars["date"].max()))[:10]
                             if len(bars) else None),
            "n_books": sum(1 for r in rows if not r["parent_book_id"]),
            "n_twins": sum(1 for r in rows if r["parent_book_id"]),
            "by_kind": by_kind, "books": rows, "grades": grades,
            "voided_before_entry": voided,
            "wls_caveat": _config.BOOK_WLS_PROXY_CAVEAT}
