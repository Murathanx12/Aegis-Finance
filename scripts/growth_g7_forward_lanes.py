"""G7 -- THE FORWARD LANES, RE-READ UNDER THE PRODUCT RULER.

`docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §2.2 and
`docs/CONTINUATION_2026-09-07b_GROWTH_BOOK_OPUS_PROMPT.md` G7:

    "For the ten website lanes and the six hack accounts, from whatever
    NAV/equity is readable: beta to SPY over the available window, raw excess,
    leverage-neutral excess, maxDD. One table. This answers 'why do
    conservative-ATR and aggressive beat SPY' with a NUMBER instead of an
    argument."

THE ONE RULE THIS FILE ENFORCES BY CONSTRUCTION
===============================================
**Beta is printed first.** `lane_row()` builds a dict whose FIRST key is
`beta`, the markdown table's FIRST column is beta, and `headline` cannot say
"beats SPY" without beta, maxDD and the cost basis in the same sentence
(`_headline`, and `backend/tests/test_growth_g7_lanes.py` pins all three).
A lane at beta 1.4 in a bull quarter beats SPY by arithmetic; a reader handed
"beat SPY by 6 points" and nothing else has been told the arithmetic and
called it a result.

WHY THE ARITHMETIC IS REUSED AND NOT REWRITTEN
==============================================
Every number below comes from `learner.growth` -- `market_model` (OLS + HAC),
`lever`, `max_drawdown`, `terminal_wealth`, `cagr`, `realized_vol`. Nothing is
reimplemented here. The module was written for MONTHLY series, and this lane
window is ~3 months long, so the finest common frequency is DAILY. Two
consequences are handled explicitly rather than absorbed:

1. `lever()` computes its financing spread as `financing_bps / 10_000 / 12`.
   Handed a daily series that would charge a MONTH of spread every DAY. So the
   caller passes `financing_bps_periodic()` -- 100 bps annual re-expressed in
   the units `lever` will divide by -- and the receipt records both the annual
   rate and the periodic argument. Adjusting the argument is honest; rewriting
   the function to guess its own frequency would put a second implementation of
   the financing convention in the program.
2. `market_model()` labels its intercept `intercept_monthly` and annualises it
   by 12. On a daily series that key means "per DAY" and the annualisation is
   wrong by 252/12. The raw block is kept verbatim under `market_model_raw`
   (with `frequency_note`), and the row's own `intercept_annualised_pct` is
   recomputed at 252. Silently re-labelling somebody else's field is how a
   number changes meaning between two files.

RF RUNS OUT BEFORE THE LANES DO, AND THAT IS SAID OUT LOUD
==========================================================
`learner.benchmark.cash()` is the pinned Fama-French daily T-bill and its
vintage ends 2026-05-29. The forward lane windows are LATER than that. Rather
than silently dropping the uncovered days (which would delete most of the
sample) or interpolating a rate (fabrication), the last observed daily RF is
CARRIED FORWARD, the carry is counted in `rf_extension`, and every row also
carries `lev_neutral_excess_ann_pct_rf_zero` -- the same number computed with
RF = 0 over the carried days. The gap between the two is the reader's bound on
how much the assumption bought. It is measured in basis points.

WHAT A REFUSAL LOOKS LIKE
=========================
A lane whose NAV is absent, unreadable, constant, or shorter than
`MIN_OBS = 20` aligned observations returns a row with `verdict =
"CANNOT DETERMINE"`, a `why` naming the reason, and NO wealth numbers at all.
A refusal is a finding (CLAUDE.md). Nothing is fabricated, nothing is
interpolated, and a lane is never dropped from the table for being unreadable
-- being unreadable is the result for that lane.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                    # so `python scripts/...` works
    sys.path.insert(0, str(ROOT))

from backend.services.receipt_provenance import (InputTracker,  # noqa: E402
                                                 attach, resolve_config)
from learner import benchmark as BM                              # noqa: E402
from learner import growth as G                                  # noqa: E402

# ───────────────────────────────────────────────────────────── the constants

#: Fewer aligned observations than this and the row REFUSES. Twenty trading days
#: is a month; below it a daily beta is a rumour and a drawdown is one bad day.
MIN_OBS: int = 20

#: Daily frequency. Used for annualisation and for re-expressing the financing
#: rate; `learner.growth` defaults to 12 because it was written for months.
TRADING_DAYS: int = 252

#: Borrowed notional is charged at RF + this, annualised (amendment §3).
FINANCING_BPS_ANNUAL: float = G.FINANCING_BPS

#: Gross ceiling on the leverage-neutral rescale (amendment §3).
GROSS_CAP: float = G.GROSS_CAP

#: Newey-West lag for the daily beta regression. ~ one trading week.
HAC_LAG: int = 5

SPY_PINNED = ROOT / "backend" / "data" / "optimus" / "growth_book" / "spy_tr_daily_pinned.csv"
SPY_PINNED_META = SPY_PINNED.with_suffix(".json")

OUT_JSON = ROOT / "backend" / "data" / "optimus" / "growth_book" / "G7_forward_lanes.json"
OUT_MD = ROOT / "backend" / "data" / "optimus" / "growth_book" / "G7_forward_lanes.md"

#: The SEPARATE execution repo (CLAUDE.md, "FOUR REPOSITORIES"). READ ONLY.
#: This script never writes a byte inside it; the hack NAV receipts live there
#: and a hash of each one read is stamped in `_provenance`.
TERMINAL_REPO = Path(r"C:\Users\mrthn\aegis-alpha-terminal")

#: The module constants a caller may override, named out loud so
#: `resolve_config` can tag each key `arg` / `env` / `default`.
_MODULE_DEFAULTS: dict[str, Any] = {
    "min_obs": MIN_OBS,
    "financing_bps": FINANCING_BPS_ANNUAL,
    "gross_cap": GROSS_CAP,
    "hac_lag": HAC_LAG,
    "trading_days": TRADING_DAYS,
    "terminal_repo": str(TERMINAL_REPO),
    "out": str(OUT_JSON),
    "md": str(OUT_MD),
}

#: THE PROVENANCE RECORDER. Recording happens where the file is OPENED, never
#: where the receipt is described -- that inversion is the W4b bug
#: (`backend/services/receipt_provenance.py` docstring).
RUN_INPUTS = InputTracker()


def _track(path: Path | str, *, note: Optional[str] = None) -> Path:
    """Record an input at the point of opening; return it unchanged."""
    RUN_INPUTS.opened(path, note=note)
    return Path(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _r(v: Any, nd: int = 4) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if math.isfinite(f) else None


# ─────────────────────────────────────────────────── frequency bookkeeping

def financing_bps_periodic(annual_bps: float = FINANCING_BPS_ANNUAL,
                           periods_per_year: int = TRADING_DAYS) -> float:
    """The argument to hand `learner.growth.lever` for a DAILY series.

    `lever` charges `financing_bps / 10_000 / 12` per period because it was
    written for monthly books. To charge `annual_bps / 252` per DAY the caller
    must pass `annual_bps * 12 / 252`. The identity is asserted by
    `test_growth_g7_lanes.test_the_daily_financing_argument_charges_the_annual_rate`.
    """
    return float(annual_bps) * 12.0 / float(periods_per_year)


# ─────────────────────────────────────────────────────────── series loading

def returns_from_nav(nav: pd.Series) -> pd.Series:
    """Simple period returns from a NAV/equity LEVEL series.

    Non-positive or missing levels are dropped BEFORE differencing: a zero NAV
    row (a fresh account with `last_equity = 0`, S19) would otherwise produce a
    -100% day and a +infinity day, and both would be believed.
    """
    s = pd.Series(nav, dtype="float64").dropna()
    s = s[s > 0]
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.pct_change().dropna()


#: How far the market has to move on a session before an UNCHANGED lane NAV is
#: read as a carried mark rather than a real flat day. 10 bps on the daily SPY
#: total return. Declared, not inline: a book really can be flat on a flat day,
#: and calling that stale would delete real observations.
STALE_MARK_MARKET_MOVE: float = 0.0010


def mark_freshness(nav: pd.Series, market: pd.Series, *,
                   market_move_floor: float = STALE_MARK_MARKET_MOVE
                   ) -> pd.DataFrame:
    """Per session: was this lane actually RE-MARKED at the official close?

    X2 (2026-09-07). A lane NAV that repeats yesterday's level on a session
    when the market moved was not re-marked; the previous close was carried
    forward. G7 measured what that costs: `conviction` loads **0.6072** on
    today's market and **1.3990** on yesterday's, so its OLS beta of 0.7163 is
    biased toward zero and the Dimson sum is 1.9313. Under the product ruler
    "beta is allowed, hidden beta is not" — and a carried mark hides it, because
    a fabricated zero return on a day the market moved is a real observation of
    zero covariance that never happened.

    Columns: `level`, `repeats_previous`, `market_move`, `stale`.
    `stale` is True where the level repeats and |market move| exceeds the floor.
    """
    s = pd.Series(nav, dtype="float64").dropna()
    s = s[s > 0]
    if not isinstance(s.index, pd.DatetimeIndex) and len(s):
        s.index = pd.to_datetime(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index()

    m = pd.Series(market, dtype="float64").dropna()
    if not isinstance(m.index, pd.DatetimeIndex) and len(m):
        m.index = pd.to_datetime(m.index)
    m = m[~m.index.duplicated(keep="last")].sort_index()

    out = pd.DataFrame({"level": s})
    out["repeats_previous"] = s.eq(s.shift(1)) & s.shift(1).notna()
    out["market_move"] = m.reindex(out.index)
    moved = out["market_move"].abs().gt(market_move_floor)
    out["stale"] = out["repeats_previous"].astype(bool) & moved.fillna(False).astype(bool)
    return out


def admissible_returns_from_nav(nav: pd.Series, market: pd.Series, *,
                                market_move_floor: float = STALE_MARK_MARKET_MOVE
                                ) -> tuple[pd.Series, dict]:
    """Returns from a NAV LEVEL series with every STALE MARK EXCLUDED.

    TWO sessions go, not one, and the second is the one that is easy to miss:

      * the CARRIED session itself, whose return is a fabricated 0.0%;
      * the session AFTER a carried one, whose return spans the gap and is a
        multi-session return being regressed on a one-session market.

    Keeping the second would move the bias rather than remove it — the lag
    loading would simply reappear on the surviving rows. So a return is
    admissible only when BOTH its endpoints are fresh marks. Everything dropped
    is counted and the counts travel on the row: a lane graded on fewer
    observations than its NAV file appears to hold must say so, or the exclusion
    is indistinguishable from a shorter history.
    """
    fresh = mark_freshness(nav, market, market_move_floor=market_move_floor)
    raw = returns_from_nav(fresh["level"]).rename(None)
    flag = fresh["stale"].astype(bool)
    stale_at = fresh.index[flag]
    prev_stale = set(fresh.index[flag.shift(1, fill_value=False).astype(bool)])
    drop = set(stale_at) | prev_stale
    kept = raw[~raw.index.isin(drop)]
    note = {
        "rule": ("a NAV level identical to the previous mark on a session when "
                 f"|SPY TR| > {market_move_floor:.4%} was NOT re-marked at the "
                 "official close; that session and the one after it are "
                 "excluded from every number on this row, including beta"),
        "marks": int(len(fresh)),
        "stale_marks": int(len(stale_at)),
        "share_stale": _r(float(len(stale_at)) / len(fresh), 4) if len(fresh) else None,
        "returns_before_exclusion": int(len(raw)),
        "returns_after_exclusion": int(len(kept)),
        "returns_excluded": int(len(raw) - len(kept)),
        "first_stale_mark": str(stale_at[0].date()) if len(stale_at) else None,
        "last_stale_mark": str(stale_at[-1].date()) if len(stale_at) else None,
        "market_move_floor": market_move_floor,
    }
    return kept, note


def load_spy() -> tuple[pd.Series, dict]:
    """The PINNED SPY total-return tape. Offline; never fetched here."""
    p = _track(SPY_PINNED, note="pinned SPY TR daily (G7 reads, never fetches)")
    df = pd.read_csv(p, parse_dates=["Date"])
    s = df.set_index("Date")["spy_tr"].astype("float64").dropna().sort_index()
    meta: dict = {}
    if SPY_PINNED_META.is_file():
        meta = json.loads(_track(SPY_PINNED_META).read_text(encoding="utf-8"))
    stamp = BM.declare(
        "spy_tr_yf_adjclose",
        construction=("pct_change of auto_adjust=True SPY Close, fetched once "
                      "2026-09-06 and PINNED to "
                      "backend/data/optimus/growth_book/spy_tr_daily_pinned.csv"),
        span=[str(s.index.min().date()), str(s.index.max().date())],
        n_periods=int(len(s)),
        freq="D",
        pinned_sha256=meta.get("sha256"),
        network=False,
    )
    return s, stamp


def load_rf(index: pd.DatetimeIndex) -> tuple[pd.Series, dict]:
    """Daily RF over `index`, with the carry counted rather than hidden.

    The pinned Fama-French vintage ends before the forward lane windows begin.
    The last observed daily rate is held flat across the uncovered days; the
    count, the date of the last real observation and the carried value are all
    returned so the receipt can say how much of the window was assumption.
    """
    bench = BM.cash()
    _track(BM._PINNED_CSV, note="pinned Fama-French daily RF (learner.benchmark.cash)")
    rf = bench.returns.astype("float64").dropna().sort_index()
    last_real = rf.index.max()
    aligned = rf.reindex(index.union(rf.index)).ffill().reindex(index)
    carried = int((index > last_real).sum())
    note = {
        "source_benchmark": "cash_rf_pinned",
        "stamp": bench.stamp(),
        "last_observed": str(last_real.date()),
        "days_covered": int(len(index) - carried),
        "days_carried_forward": carried,
        "carried_daily_rf": _r(float(rf.iloc[-1]), 8),
        "carried_annualised_pct": _r(float(rf.iloc[-1]) * TRADING_DAYS * 100.0, 4),
        "construction": ("the last observed daily T-bill rate is held FLAT over "
                         "days the pinned vintage does not cover; it is never "
                         "interpolated, and every row carries the rf=0 "
                         "sensitivity beside it"),
    }
    return aligned.fillna(0.0), note


# ─────────────────────────────────────────────────────────────── ONE LANE

#: A lagged-market beta at least this large, and larger in absolute size than
#: the contemporaneous one, is treated as evidence of asynchronous marking.
STALE_MARK_LAG_BETA: float = 0.20


def lead_lag_beta(book_excess: pd.Series, mkt_excess: pd.Series,
                  *, hac_lag: int = HAC_LAG) -> dict:
    """Is the contemporaneous beta biased toward zero by ASYNCHRONOUS MARKS?

    WHY THIS IS NOT OPTIONAL HERE. Run on the website lanes' NAV this returns,
    for `conviction`, a contemporaneous beta of 0.66 and a beta on YESTERDAY'S
    market of 1.50. A book cannot respond to the market a day late; a book's
    PRICES can, and these do -- the marks are stale (the program caches prices
    with a TTL, CLAUDE.md "Rules/DO"). The consequence is that the ruler's
    contemporaneous beta UNDERSTATES market exposure, which is the exact
    failure the amendment §2.2 exists to prevent -- "beta is allowed, hidden
    beta is not". A stale mark hides beta, so the diagnostic travels beside
    every beta in this table rather than in a footnote.

    Returns the Dimson (1979) sum over {lead, contemporaneous, lag} from ONE
    joint regression -- `learner.growth.market_model` is univariate and cannot
    express it, so the three-regressor fit is done here and is explicitly a
    DIAGNOSTIC, never the ruler. The univariate beta on the lagged market is
    taken from `market_model` so it arrives with the same HAC standard error
    as everything else.
    """
    y = pd.Series(book_excess, dtype="float64").dropna()
    m = pd.Series(mkt_excess, dtype="float64")
    d = pd.concat([y.rename("y"), m.rename("s0"),
                   m.shift(1).rename("s_lag"),
                   m.shift(-1).rename("s_lead")], axis=1).reindex(y.index).dropna()
    if len(d) < 8 or d["s0"].std(ddof=1) <= 0:
        return {"beta_dimson": None,
                "why": f"only {len(d)} rows with a lead and a lag available"}
    X = np.column_stack([np.ones(len(d)), d["s0"], d["s_lag"], d["s_lead"]])
    c = np.linalg.lstsq(X, d["y"].to_numpy(), rcond=None)[0]
    lag_uni = G.market_model(d["y"], d["s_lag"], lag=hac_lag)
    b0, b_lag, b_lead = float(c[1]), float(c[2]), float(c[3])
    stale = bool(abs(b_lag) > abs(b0) and b_lag > STALE_MARK_LAG_BETA)
    return {
        "beta_dimson": _r(b0 + b_lag + b_lead, 4),
        "beta_contemporaneous_joint": _r(b0, 4),
        "beta_on_lagged_market_joint": _r(b_lag, 4),
        "beta_on_lead_market_joint": _r(b_lead, 4),
        "beta_on_lagged_market_univariate": lag_uni.get("beta"),
        "beta_on_lagged_market_univariate_t_vs_1": lag_uni.get("beta_t_vs_1"),
        "n": int(len(d)),
        "stale_marks_suspected": stale,
        "verdict": (
            "STALE MARKS SUSPECTED -- the book loads more on YESTERDAY'S "
            "market than on today's, so the contemporaneous beta beside it is "
            "biased TOWARD ZERO and understates market exposure. Read "
            "`beta_dimson` as the exposure and the OLS beta as the ruler's "
            "literal number." if stale else
            "no lead-lag asymmetry large enough to suspect asynchronous marks"),
        "construction": ("Dimson (1979) sum of the {lead, contemporaneous, "
                         "lag} market betas from one joint OLS; a DIAGNOSTIC, "
                         "not the ruler"),
    }


def _headline(row: Mapping[str, Any]) -> str:
    """The sentence. It cannot say 'beats SPY' without beta, maxDD and cost.

    The amendment §4: *the word "beats SPY" is never written without "at
    beta = x, maxDD = y, after z bps"*. Enforcing it in the STRING BUILDER
    rather than in a review checklist is the only version that holds.
    """
    verdict = "beats SPY" if row.get("raw_excess_total_pp", 0) and \
        float(row["raw_excess_total_pp"]) > 0 else "trails SPY"
    stale = ""
    if (row.get("stale_mark_diagnostic") or {}).get("stale_marks_suspected"):
        stale = (f" [STALE MARKS: beta on yesterday's market exceeds today's; "
                 f"Dimson beta "
                 f"{row['stale_mark_diagnostic'].get('beta_dimson')} is the "
                 f"exposure, and the vol used for the leverage-neutral rescale "
                 f"is smoothed, so that column flatters this book]")
    return (f"beta {row['beta']} (t vs 1 = {row['beta_t_vs_1']}): "
            f"{row['lane']} {verdict} by {row['raw_excess_total_pp']} pp raw "
            f"over {row['n_obs']} sessions, "
            f"maxDD {row['maxdd_lane_pct']}% vs SPY {row['maxdd_spy_pct']}%, "
            f"cost basis: {row['cost_basis']}; "
            f"LEVERAGE-NEUTRAL excess {row['lev_neutral_excess_total_pp']} pp"
            + stale)


def _refusal(lane: str, source: str, why: str, *,
             cost_basis: str = "n/a (no series)",
             n_obs: Optional[int] = None,
             extra: Optional[Mapping[str, Any]] = None) -> dict:
    """A row that reports nothing but the reason it reports nothing.

    BETA IS STILL THE FIRST KEY -- a refusal that reordered the dict would let
    the ordering test pass on the happy path only, which is the shape of guard
    that has never once caught anything in this program.
    """
    row: dict[str, Any] = {
        "beta": None,
        "beta_t_vs_1": None,
        "beta_dimson": None,
        "stale_marks_suspected": None,
        "stale_marks_excluded": None,
        "beta_admissible_as_exposure": None,
        "r2_vs_spy": None,
        "lane": lane,
        "verdict": "CANNOT DETERMINE",
        "why": why,
        "source": source,
        "n_obs": n_obs,
        "window": None,
        "cost_basis": cost_basis,
        "raw_excess_ann_pct": None,
        "raw_excess_total_pp": None,
        "lev_neutral_excess_ann_pct": None,
        "lev_neutral_excess_total_pp": None,
        "maxdd_lane_pct": None,
        "maxdd_spy_pct": None,
        "headline": f"CANNOT DETERMINE -- {why}",
    }
    if extra:
        row.update(extra)
    return row


def lane_row(lane: str, lane_returns: pd.Series, spy: pd.Series, rf: pd.Series,
             *, source: str, cost_basis: str,
             min_obs: int = MIN_OBS,
             financing_bps_annual: float = FINANCING_BPS_ANNUAL,
             gross_cap: float = GROSS_CAP,
             hac_lag: int = HAC_LAG,
             trading_days: int = TRADING_DAYS,
             rf_zero: Optional[pd.Series] = None,
             mark_note: Optional[Mapping[str, Any]] = None) -> dict:
    """One table row. BETA IS THE FIRST KEY, and that is a load-bearing fact.

    `lane_returns` are the lane's realised period returns (NOT levels; use
    `returns_from_nav`). Everything is aligned on the INTERSECTION of the three
    indexes and the surviving count is reported -- a lane graded on 60 sessions
    against a SPY leg covering 20 is two windows wearing one label.
    """
    b = pd.Series(lane_returns, dtype="float64").dropna()
    if not isinstance(b.index, pd.DatetimeIndex) and len(b):
        b.index = pd.to_datetime(b.index)
    s = pd.Series(spy, dtype="float64").dropna()
    r = pd.Series(rf, dtype="float64").dropna()
    idx = b.index.intersection(s.index).intersection(r.index).sort_values()
    n = int(len(idx))
    if n < min_obs:
        return _refusal(
            lane, source,
            f"only {n} observations aligned with SPY and RF (the source series "
            f"carries {len(b)} returns); the floor is {min_obs}. Not "
            f"interpolated, not extended.",
            cost_basis=cost_basis, n_obs=n,
            extra={"n_source_returns": int(len(b))})
    b, s, r = b.reindex(idx), s.reindex(idx), r.reindex(idx)
    if float(b.std(ddof=1)) <= 0:
        return _refusal(lane, source,
                        f"the lane's {n} returns are constant (zero variance): "
                        "no beta is estimable and no drawdown is meaningful",
                        cost_basis=cost_basis, n_obs=n)

    # ── BETA FIRST. Reused from learner.growth, not reimplemented.
    mm = G.market_model(b - r, s - r, lag=hac_lag)
    if mm.get("beta") is None:
        return _refusal(lane, source,
                        f"beta could not be estimated ({mm.get('why')}); no "
                        "wealth number is reported without one",
                        cost_basis=cost_basis, n_obs=n)

    # ── and IMMEDIATELY beside it: is that beta believable, or is it the
    #    artefact of a stale mark? A beta biased to zero HIDES beta.
    stale_diag = lead_lag_beta(b - r, s - r, hac_lag=hac_lag)

    tw_b, tw_s = G.terminal_wealth(b), G.terminal_wealth(s)
    cagr_b = G.cagr(b, trading_days)
    cagr_s = G.cagr(s, trading_days)
    vol_b = G.realized_vol(b, trading_days)
    vol_s = G.realized_vol(s, trading_days)

    # ── leverage-neutral: the lane re-run at SPY's OWN realized vol, financing
    #    the borrowed notional, parking unused cash at RF. `lever` does both.
    fin_periodic = financing_bps_periodic(financing_bps_annual, trading_days)
    scale_raw = (vol_s / vol_b) if (vol_b and math.isfinite(vol_b) and vol_b > 0) else None
    ln: dict[str, Any] = {}
    if scale_raw is None:
        ln = {"scale": None, "why": "lane volatility is zero or undefined"}
        lev_ann = lev_total = None
    else:
        L = float(min(gross_cap, scale_raw))
        bn = G.lever(b, r, L, financing_bps=fin_periodic)
        lev_ann = G.cagr(bn, trading_days) - cagr_s
        lev_total = (G.terminal_wealth(bn) - tw_s) * 100.0
        ln = {
            "scale": _r(L),
            "scale_uncapped": _r(scale_raw),
            "capped_by_gross": bool(scale_raw > gross_cap),
            "terminal_wealth": _r(G.terminal_wealth(bn), 6),
            "cagr_pct": _r(G.cagr(bn, trading_days) * 100.0, 3),
            "max_drawdown_pct": _r(G.max_drawdown(bn) * 100.0, 3),
            "realized_vol_pct": _r(G.realized_vol(bn, trading_days) * 100.0, 3),
            "construction": (
                "lane scaled to SPY's realized vol over the SAME sessions; "
                f"borrowed notional charged at RF + {financing_bps_annual:.0f} "
                f"bps annualised ({fin_periodic:.4f} passed to learner.growth."
                f"lever, which divides by 12); unused cash earns RF"),
        }
        if stale_diag.get("stale_marks_suspected"):
            # Smoothed marks UNDERSTATE realized vol, so vs/vb -- and therefore
            # the scale -- is an UPPER bound and this column flatters the book.
            # Saying so here costs one field; not saying it turns a marking
            # artefact into a claimed leverage-neutral win.
            ln["caveat"] = (
                "the denominator of this rescale is a volatility measured off "
                "the SAME asynchronous marks; smoothing understates vol, so "
                f"the scale {_r(min(gross_cap, scale_raw))} is an UPPER bound "
                "and the leverage-neutral excess beside it is flattered")

    # ── the same number with RF = 0 over the carried days: the reader's bound
    #    on what the RF forward-carry bought.
    lev_ann_rf0 = None
    if scale_raw is not None and rf_zero is not None:
        r0 = pd.Series(rf_zero, dtype="float64").reindex(idx).fillna(0.0)
        bn0 = G.lever(b, r0, float(min(gross_cap, scale_raw)),
                      financing_bps=fin_periodic)
        lev_ann_rf0 = G.cagr(bn0, trading_days) - cagr_s

    row: dict[str, Any] = {
        # BETA FIRST -- the amendment's §2.2 rule, enforced by key order.
        "beta": mm.get("beta"),
        "beta_t_vs_1": mm.get("beta_t_vs_1"),
        "beta_dimson": stale_diag.get("beta_dimson"),
        "stale_marks_suspected": stale_diag.get("stale_marks_suspected"),
        # X2: how many marks this row THREW AWAY before estimating any of the
        # numbers beside it. `None` means the caller handed returns rather than
        # a NAV level series, so freshness could not be judged -- which is a
        # different statement from "no stale marks" and is not collapsed into it.
        "stale_marks_excluded": (dict(mark_note) if mark_note is not None
                                 else None),
        # X2: carried marks are gone from the series above, and the lead/lag
        # test is re-run on what is LEFT. If the book STILL loads more on
        # yesterday's market than on today's, the marks are stale in a way a
        # level series cannot show -- every mark one session old, so nothing
        # repeats and nothing is droppable -- and `beta` is then not this
        # book's exposure. A consumer gates on this field rather than on a
        # sentence inside `headline`.
        "beta_admissible_as_exposure": (
            not bool(stale_diag.get("stale_marks_suspected"))),
        # How much of this book SPY explains at all. A beta estimated at r2 ~ 0
        # is precise about a relationship that is barely there, and the
        # leverage-neutral rescale is then amplifying idiosyncratic noise to
        # SPY's volatility rather than making two market exposures comparable.
        "r2_vs_spy": _r(float(np.corrcoef(b - r, s - r)[0, 1] ** 2), 4),
        "lane": lane,
        "verdict": "OK",
        "source": source,
        "n_obs": n,
        "window": [str(idx[0].date()), str(idx[-1].date())],
        "cost_basis": cost_basis,
        "raw_excess_ann_pct": _r((cagr_b - cagr_s) * 100.0, 3),
        "raw_excess_total_pp": _r((tw_b - tw_s) * 100.0, 3),
        "lev_neutral_excess_ann_pct": _r((lev_ann or 0.0) * 100.0, 3) if lev_ann is not None else None,
        "lev_neutral_excess_total_pp": _r(lev_total, 3) if lev_total is not None else None,
        "lev_neutral_excess_ann_pct_rf_zero": (
            _r(lev_ann_rf0 * 100.0, 3) if lev_ann_rf0 is not None else None),
        "maxdd_lane_pct": _r(G.max_drawdown(b) * 100.0, 3),
        "maxdd_spy_pct": _r(G.max_drawdown(s) * 100.0, 3),
        "lane_total_return_pct": _r((tw_b - 1.0) * 100.0, 3),
        "spy_total_return_pct": _r((tw_s - 1.0) * 100.0, 3),
        "lane_cagr_pct": _r(cagr_b * 100.0, 3),
        "spy_cagr_pct": _r(cagr_s * 100.0, 3),
        "lane_vol_pct": _r(vol_b * 100.0, 3),
        "spy_vol_pct": _r(vol_s * 100.0, 3),
        "intercept_daily": mm.get("intercept_monthly"),
        "intercept_annualised_pct": _r(
            (mm.get("intercept_monthly") or 0.0) * trading_days * 100.0, 3),
        "intercept_t_hac": mm.get("intercept_t_hac"),
        "leverage_neutral": ln,
        "stale_mark_diagnostic": stale_diag,
        "market_model_raw": {
            **mm,
            "frequency_note": (
                "learner.growth.market_model was written for MONTHLY series: "
                "its `intercept_monthly` here is PER DAY and its "
                "`intercept_annualised_pct` is annualised at 12, not 252. The "
                "row's own `intercept_annualised_pct` is the correct one."),
        },
        "annualisation_note": (
            f"CAGR over {n} sessions is an annualisation of a "
            f"{n / trading_days:.2f}-year window; it is a rate, not a "
            "forecast, and its standard error is large."),
    }
    row["headline"] = _headline(row)
    return row


# ────────────────────────────────────────────── the sources (discovery layer)

def _read_json(path: Path) -> Any:
    return json.loads(_track(path).read_text(encoding="utf-8"))


def website_lane_navs() -> tuple[dict[str, pd.Series], dict]:
    """NAV level series per website paper lane, from LOCAL receipts.

    Two sources are looked at, in this order, and BOTH are reported:

    1. `backend/data/aegis_pi.db` -> `paper_nav`, the CANONICAL store
       (`backend/db.py`: `portfolio_id, date, nav, config_version`). On this
       machine it holds ZERO NAV rows -- the live book is on the Railway
       volume, and the local file is a dev stub. That is recorded as a row
       count, not as an absence: "the canonical table has 0 rows" and "there is
       no canonical table" are different findings and only one of them is true.
    2. `docs/conviction_replay/prod_reads_2026-08-19/track_record_full.json`,
       a verbatim capture of `GET /api/pi/track-record` from production. This
       is the readable ten-lane series and the one the table is built from. It
       is a SNAPSHOT: it ends 2026-08-18, and the window in every row says so.

    Returns `({lane: nav_series}, discovery_note)`. Discovery is reported even
    when it finds nothing, so "no lanes" is never confusable with "never
    looked" -- the S30 lesson, absence of a local object is not evidence.
    """
    note: dict[str, Any] = {"searched": [], "store": None, "lanes_found": 0,
                            "canonical_store": None}
    navs: dict[str, pd.Series] = {}

    for cand in LANE_DB_CANDIDATES:
        p = ROOT / cand
        seen = {"path": str(p), "kind": "sqlite paper_nav (canonical)",
                "exists": p.exists()}
        if p.is_file():
            try:
                rows, from_db = _lane_navs_from_sqlite(p)
                seen["paper_nav_rows"] = rows
                seen["lanes"] = sorted(from_db)
                if from_db:
                    navs, note["store"] = from_db, str(p)
            except Exception as exc:                              # noqa: BLE001
                seen["error"] = f"{type(exc).__name__}: {exc}"
            note["canonical_store"] = str(p)
        note["searched"].append(seen)
        if navs:
            break

    if not navs:
        for cand in LANE_SNAPSHOT_CANDIDATES:
            p = ROOT / cand
            seen = {"path": str(p), "kind": "captured /api/pi/track-record",
                    "exists": p.exists()}
            if p.is_file():
                try:
                    payload = _read_json(p)
                    from_snap = _lane_navs_from_track_record(payload)
                    seen["lanes"] = sorted(from_snap)
                    seen["expected_nav_date"] = payload.get("expected_nav_date")
                    seen["inception_date"] = payload.get("inception_date")
                    if len(from_snap) > len(navs):
                        navs, note["store"] = from_snap, str(p)
                        note["snapshot_expected_nav_date"] = \
                            payload.get("expected_nav_date")
                except Exception as exc:                          # noqa: BLE001
                    seen["error"] = f"{type(exc).__name__}: {exc}"
            note["searched"].append(seen)

    note["lanes_found"] = len(navs)
    if not navs:
        note["why"] = ("no local source carried a dated lane NAV series; "
                       "nothing was fetched and nothing was invented")
    return navs, note


def _lane_navs_from_sqlite(path: Path) -> tuple[int, dict[str, pd.Series]]:
    """`paper_nav` as `(row_count, {lane_id: Series[date -> nav]})`.

    Opened READ-ONLY (`mode=ro`): the paper_nav write path is sacred
    (CANON §5, the `lane-integrity-check` skill) and a reader has no business
    being able to touch it even by accident.
    """
    _track(path, note="canonical website paper lane NAV store (read-only)")
    uri = f"file:{path.as_posix()}?mode=ro"
    out: dict[str, pd.Series] = {}
    with sqlite3.connect(uri, uri=True) as con:
        cols = {r[1] for r in con.execute("PRAGMA table_info(paper_nav)")}
        if not cols:
            return 0, out
        lane_col = next((c for c in ("portfolio_id", "lane_id", "lane",
                                     "book", "lane_name") if c in cols), None)
        date_col = next((c for c in ("date", "asof", "as_of", "nav_date",
                                     "dt") if c in cols), None)
        nav_col = next((c for c in ("nav", "nav_value", "equity", "value",
                                    "total_value") if c in cols), None)
        if not (lane_col and date_col and nav_col):
            raise ValueError(
                f"paper_nav columns {sorted(cols)} carry no recognisable "
                f"(lane, date, nav) triple")
        df = pd.read_sql_query(
            f"SELECT {lane_col} AS lane, {date_col} AS date, {nav_col} AS nav "
            f"FROM paper_nav", con)
    n = int(len(df))
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "nav"])
    for lane, g in df.groupby("lane"):
        s = g.set_index("date")["nav"].astype("float64").sort_index()
        out[str(lane)] = s[~s.index.duplicated(keep="last")]
    return n, out


def _lane_navs_from_track_record(payload: Mapping[str, Any]) -> dict[str, pd.Series]:
    """`{"lanes": {lane_id: [{date, value, config_version}, ...]}}` -> series.

    The endpoint renames the DB's `nav` column to `value`; both spellings are
    accepted so a schema drift on the surface does not silently produce an
    empty lane (the 2026-06-16 class: true in the DB, invisible on the API).
    """
    lanes = payload.get("lanes")
    if not isinstance(lanes, Mapping):
        raise ValueError("payload has no `lanes` object")
    out: dict[str, pd.Series] = {}
    for lane, rows in lanes.items():
        if not isinstance(rows, list) or not rows:
            continue
        recs = [(r.get("date"), r.get("value", r.get("nav")))
                for r in rows if isinstance(r, Mapping)]
        recs = [(d, v) for d, v in recs
                if d is not None and isinstance(v, (int, float))
                and not isinstance(v, bool)]
        if not recs:
            continue
        s = pd.Series([float(v) for _, v in recs],
                      index=pd.to_datetime([d for d, _ in recs], errors="coerce"))
        s = s[~s.index.isna()].sort_index()
        if len(s):
            out[str(lane)] = s[~s.index.duplicated(keep="last")]
    return out


def hack_account_navs(repo: Path = TERMINAL_REPO) -> tuple[dict[str, pd.Series], dict]:
    """Daily equity per hack paper account, from LOCAL receipts in the
    execution repo. READ-ONLY: nothing inside `repo` is created or modified.

    The execution repo caches no NAV series -- `alpha/broker/alpaca.py` pulls
    `portfolio_history` live at report time and does not persist it. The only
    dated series on disk is `accounts.<role>.daily_equity` inside
    `state/benchmark_regret_20260903.json`, and it is SIX sessions long,
    because the six accounts were frozen at genesis on 2026-08-28.

    THE OTHER SOURCES ARE DELIBERATELY NOT MERGED. `state/learning_report/
    <day>.json` carries one more equity per role, but the two derive their
    session label differently (`fromtimestamp(UTC) + ET_OFFSET` versus the
    report's `day`) and DISAGREE: the report dated 2026-09-02 carries the
    benchmark receipt's 2026-09-03 values. Stitching them would add an
    observation by mis-dating one, which is manufacturing a return out of a
    timezone bug. They are listed in `secondary_not_merged` and left there.
    """
    note: dict[str, Any] = {"repo": str(repo), "repo_exists": repo.exists(),
                            "searched": [], "accounts_found": 0,
                            "secondary_not_merged": [], "railway": (
                                "NOT CALLED. A local dated series exists; and "
                                "the venue could not lengthen it either -- the "
                                "accounts are ~6 sessions old, so the binding "
                                "constraint is account AGE, not readability.")}
    navs: dict[str, pd.Series] = {}
    if not repo.is_dir():
        note["why"] = ("the execution repo is not present on this machine; the "
                       "hack accounts' NAV lives there and is not mirrored here")
        return navs, note

    for rel in HACK_NAV_CANDIDATES:
        p = repo / rel
        seen: dict[str, Any] = {"path": str(p), "exists": p.exists()}
        if p.is_file():
            try:
                found = _hack_navs_from_benchmark_regret(_read_json(p))
                seen["accounts"] = {a: int(len(s)) for a, s in found.items()}
                for account, s in found.items():
                    if account not in navs and len(s):
                        navs[account] = s
            except Exception as exc:                              # noqa: BLE001
                seen["error"] = f"{type(exc).__name__}: {exc}"
        note["searched"].append(seen)

    for rel in HACK_SECONDARY_NOT_MERGED:
        p = repo / rel
        note["secondary_not_merged"].append({
            "path": str(p), "exists": p.exists(),
            "why_not_merged": ("its session label is derived differently and "
                               "disagrees with the primary series; merging "
                               "would invent a return from a date bug"),
        })

    note["accounts_found"] = len(navs)
    if not navs:
        note["why"] = ("no local dated equity series for any hack account; "
                       "nothing was fetched and nothing was invented")
    return navs, note


def _hack_navs_from_benchmark_regret(payload: Mapping[str, Any]) -> dict[str, pd.Series]:
    """`{"accounts": {role: {"daily_equity": {date: equity}}}}` -> series."""
    accounts = payload.get("accounts")
    if not isinstance(accounts, Mapping):
        raise ValueError("payload has no `accounts` object")
    out: dict[str, pd.Series] = {}
    for role, blob in accounts.items():
        if not isinstance(blob, Mapping):
            continue
        daily = blob.get("daily_equity")
        if not isinstance(daily, Mapping) or not daily:
            continue
        recs = [(d, v) for d, v in daily.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not recs:
            continue
        s = pd.Series([float(v) for _, v in recs],
                      index=pd.to_datetime([d for d, _ in recs], errors="coerce"))
        s = s[~s.index.isna()].sort_index()
        if len(s):
            out[str(role)] = s[~s.index.duplicated(keep="last")]
    return out


#: The CANONICAL website NAV store. Present locally, and locally EMPTY -- the
#: live book is on the Railway volume. Its row count is reported, not its
#: absence (`backend/db.py` defines the table).
LANE_DB_CANDIDATES: tuple[str, ...] = (
    "backend/data/aegis_pi.db",
)

#: Captured `/api/pi/track-record` payloads, newest first. The FIRST one holds
#: all ten lanes; `.cache/track_record.json` is listed because a reader has to
#: be able to see that it was looked at AND that it is the stale seven-lane
#: copy, rather than wonder which snapshot was used.
LANE_SNAPSHOT_CANDIDATES: tuple[str, ...] = (
    "docs/conviction_replay/prod_reads_2026-08-19/track_record_full.json",
    ".cache/track_record.json",
)

#: The six hack paper accounts (CLAUDE.md, S19: "six accounts / six mandates").
HACK_ACCOUNTS: tuple[str, ...] = ("hack1", "hack2", "hack3", "hack4",
                                  "hack5", "hack6")

#: The only local file in the execution repo carrying a DATED equity series for
#: the hack accounts. Read-only, relative to `TERMINAL_REPO`.
HACK_NAV_CANDIDATES: tuple[str, ...] = (
    "state/benchmark_regret_20260903.json",
)

#: Files that carry an account equity but on an INCOMPATIBLE session label.
#: Named so the reader can see they were found and deliberately not used.
HACK_SECONDARY_NOT_MERGED: tuple[str, ...] = (
    "state/learning_report/2026-09-02.json",
    "state/learning_report/2026-09-03.json",
    "state/learning_report/2026-09-04.json",
    "state/labor_day_lab_2026-09-07/D1_connection_check_terminal.json",
)


# ───────────────────────────────────────────────────────────────── the run

def run(*, min_obs: int = MIN_OBS,
        financing_bps: float = FINANCING_BPS_ANNUAL,
        gross_cap: float = GROSS_CAP,
        hac_lag: int = HAC_LAG,
        trading_days: int = TRADING_DAYS,
        terminal_repo: Path | str = TERMINAL_REPO) -> dict:
    """Build the receipt. Returns the dict; writes nothing."""
    spy, spy_stamp = load_spy()

    lanes, lane_note = website_lane_navs()
    hacks, hack_note = hack_account_navs(Path(terminal_repo))

    all_idx = spy.index
    for s in list(lanes.values()) + list(hacks.values()):
        all_idx = all_idx.union(pd.DatetimeIndex(s.index))
    rf, rf_note = load_rf(pd.DatetimeIndex(all_idx))
    rf_zero = pd.Series(0.0, index=rf.index)

    rows: list[dict] = []

    # EVERY DECLARED BOOK GETS A ROW, found or not. A lane dropped from the
    # table for being unreadable reads as "not a lane"; a lane present and
    # saying CANNOT DETERMINE reads as what it is.
    lane_source = str(lane_note.get("store") or "website paper lane NAV (none found)")
    for lane in list(WEBSITE_LANES) + [x for x in sorted(lanes)
                                       if x not in WEBSITE_LANES]:
        if lane in lanes:
            # X2: the NAV is judged for FRESHNESS before it is differenced. A
            # mark carried from the previous close is not an observation of a
            # flat day, and leaving it in is what put 1.399 of `conviction`'s
            # loading on YESTERDAY'S market.
            lane_ret, lane_marks = admissible_returns_from_nav(lanes[lane], spy)
            rows.append(lane_row(
                lane, lane_ret, spy, rf,
                source=lane_source, cost_basis=LANE_COST_BASIS,
                min_obs=min_obs, financing_bps_annual=financing_bps,
                gross_cap=gross_cap, hac_lag=hac_lag,
                trading_days=trading_days, rf_zero=rf_zero,
                mark_note=lane_marks))
        else:
            rows.append(_refusal(
                lane, lane_source,
                f"no local NAV series for lane {lane!r}; every path looked at "
                "is listed in `discovery.website_lanes.searched`. Nothing was "
                "fetched and nothing was invented.",
                cost_basis=LANE_COST_BASIS))

    hack_source = f"{terminal_repo} state/ local receipt (READ-ONLY)"
    for account in HACK_ACCOUNTS:
        if account in hacks:
            acct_ret, acct_marks = admissible_returns_from_nav(hacks[account], spy)
            rows.append(lane_row(
                account, acct_ret, spy, rf,
                source=hack_source, cost_basis=HACK_COST_BASIS,
                min_obs=min_obs, financing_bps_annual=financing_bps,
                gross_cap=gross_cap, hac_lag=hac_lag,
                trading_days=trading_days, rf_zero=rf_zero,
                mark_note=acct_marks))
        else:
            rows.append(_refusal(
                account, hack_source,
                (f"no readable local dated equity series for {account}; paths "
                 "looked at are in `discovery.hack_accounts`. Railway was not "
                 "called, nothing was fetched, nothing was interpolated."),
                cost_basis=HACK_COST_BASIS))

    readable = [r for r in rows if r["verdict"] == "OK"]
    stale = [r["lane"] for r in readable if r.get("stale_marks_suspected")]
    receipt: dict[str, Any] = {
        "item": "G7",
        "licence": "PRODUCT_EXPERIMENT",
        "title": "Forward lanes re-read under the product ruler (beta first)",
        "mandate": ["docs/ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md",
                    "docs/CONTINUATION_2026-09-07b_GROWTH_BOOK_OPUS_PROMPT.md"],
        "written_utc": _now(),
        "ruler": {
            "beta_first": True,
            "frequency": "daily (the finest common frequency; the lane windows "
                         "are too short for a monthly regression)",
            "min_obs": min_obs,
            "hac_lag": hac_lag,
            "financing_bps_annual_over_rf": financing_bps,
            "financing_bps_passed_to_lever": _r(
                financing_bps_periodic(financing_bps, trading_days), 6),
            "gross_cap": gross_cap,
            "trading_days_per_year": trading_days,
            "leverage_neutral": (
                "the lane's series scaled to SPY's realized vol over the same "
                "sessions, borrowed notional financed at RF + "
                f"{financing_bps:.0f} bps annualised, unused cash earning RF "
                "(learner.growth.lever)"),
            "reused_from": ["learner.growth.market_model", "learner.growth.lever",
                            "learner.growth.max_drawdown",
                            "learner.growth.terminal_wealth",
                            "learner.growth.cagr", "learner.growth.realized_vol"],
            "phrase_rule": ("'beats SPY' is never written without beta, maxDD "
                            "and the cost basis beside it (see `_headline`)"),
        },
        "stale_mark_finding": {
            "lanes_flagged": stale,
            "n_flagged": len(stale),
            "what_it_means": (
                "these books load MORE on yesterday's market than on today's. "
                "A book cannot react to the market a day late; its marks can, "
                "and these do. So the ruler's contemporaneous beta is biased "
                "TOWARD ZERO for them and understates market exposure -- a "
                "stale mark HIDES beta, which is the one thing the amendment "
                "§2.2 forbids. `beta_dimson` is the exposure to read; the OLS "
                "beta is the ruler's literal number. Both are in the table."),
            "second_consequence": (
                "smoothed marks also understate realized volatility, so the "
                "leverage-neutral rescale (SPY vol / book vol) is an UPPER "
                "bound for the flagged books and their leverage-neutral "
                "excess is flattered by an unknown amount."),
            "threshold": STALE_MARK_LAG_BETA,
            "how_to_settle_it": (
                "compare a lane's NAV against the same weights repriced at the "
                "session's official close. That is a mark-to-market question "
                "for the website lane job, not a question this table can "
                "answer, and it is stated as an open item rather than assumed "
                "either way."),
        },
        "market_benchmark": spy_stamp,
        "rf_extension": rf_note,
        "discovery": {"website_lanes": lane_note, "hack_accounts": hack_note},
        "counts": {
            "rows": len(rows),
            "readable": len(readable),
            "cannot_determine": len(rows) - len(readable),
            "website_lanes_expected": len(WEBSITE_LANES),
            "hack_accounts_expected": len(HACK_ACCOUNTS),
        },
        "rows": rows,
    }
    receipt["headline"] = (
        f"{len(readable)} of {len(rows)} forward books carry a readable NAV "
        f"series; {len(rows) - len(readable)} say CANNOT DETERMINE"
        + (f"; {len(stale)} of the readable ones ({', '.join(stale)}) load "
           f"more on YESTERDAY'S market than today's, so their contemporaneous "
           f"beta understates exposure" if stale else "")
        + ". "
        + ("; ".join(r["headline"] for r in readable[:3]) if readable
           else "No forward book was gradeable, so no lane 'beats SPY' here.")
    )
    return receipt


#: The ten website paper lanes, named so the table has a row for each even when
#: the NAV store is not on this machine. A lane missing from the table would
#: read as "not a lane"; a lane in the table saying CANNOT DETERMINE reads as
#: what it is -- an unanswered question with a named reason. The list is
#: assembled at import time in
#: `backend/services/portfolio_intelligence/rules.py` from FIVE separate lane
#: YAMLs (each file's SHA-256 is that group's `config_version`).
WEBSITE_LANES: tuple[str, ...] = (
    "conservative", "balanced", "aggressive", "balanced-ew-control",
    "mirror", "conviction", "conservative-atr", "smallmid-quality",
    "tsmom-overlay", "tsmom-6040-control",
)

#: What the NAV series already contains, in cost terms. Named, never assumed.
LANE_COST_BASIS = ("website paper lane NAV, marked to market from recorded "
                   "weights per the lane YAML; no extra bps applied here")
HACK_COST_BASIS = ("Alpaca PAPER account equity as reported by the venue: "
                   "fills-as-filled, commission-free US equities, so the cost "
                   "basis is realised slippage only and no explicit bps is "
                   "applied on top")


# ──────────────────────────────────────────────────────────────── the table

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("beta", "beta"),
    ("beta_t_vs_1", "t(beta-1)"),
    ("beta_dimson", "beta Dimson"),
    ("r2_vs_spy", "R2 vs SPY"),
    ("lane", "book"),
    ("verdict", "verdict"),
    ("n_obs", "n"),
    ("window", "window"),
    ("raw_excess_ann_pct", "raw exc %/yr"),
    ("raw_excess_total_pp", "raw exc pp"),
    ("lev_neutral_excess_ann_pct", "lev-neutral exc %/yr"),
    ("lev_neutral_excess_total_pp", "lev-neutral exc pp"),
    ("maxdd_lane_pct", "maxDD book %"),
    ("maxdd_spy_pct", "maxDD SPY %"),
    ("cost_basis_tag", "cost basis"),
)

#: The table repeats a cost basis on every row (the mandate: "beats SPY" never
#: without the cost basis beside it), so the CELL is a short tag and the full
#: sentence is printed once in the legend under the table. Abbreviating it away
#: entirely would break the rule; repeating 140 characters sixteen times makes
#: the table unreadable, which breaks it in the other direction.
COST_TAGS: dict[str, str] = {
    LANE_COST_BASIS: "lane YAML marks, no extra bps",
    HACK_COST_BASIS: "venue fills, 0 commission",
}


def _cost_tag(row: Mapping[str, Any]) -> str:
    basis = str(row.get("cost_basis") or "")
    return COST_TAGS.get(basis, basis[:40])


def _cell(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, list):
        return " → ".join(str(x) for x in v)
    if isinstance(v, str):
        return v.replace("|", "/")
    return str(v)


def to_markdown(receipt: Mapping[str, Any]) -> str:
    """The ONE table. Beta is column one, and the rule is printed above it."""
    head = "| " + " | ".join(h for _, h in _COLUMNS) + " |"
    rule = "|" + "|".join("---" for _ in _COLUMNS) + "|"
    body = [
        "| " + " | ".join(
            _cell(_cost_tag(r) if k == "cost_basis_tag" else r.get(k))
            for k, _ in _COLUMNS) + " |"
        for r in receipt.get("rows", [])
    ]
    rf = receipt.get("rf_extension", {})
    disc = receipt.get("discovery", {})
    counts = receipt.get("counts", {})
    lines = [
        "# G7 — the forward lanes under the product ruler",
        "",
        "*`ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md` §2.2 — beta is allowed;",
        "hidden beta is not. **Beta is column one.***",
        "",
        "*The rule, which this line obeys: nothing here says \"beats SPY\" "
        "without beta, maxDD and the cost basis in the same sentence.*",
        "",
        f"- **Rows:** {counts.get('rows')} "
        f"({counts.get('readable')} readable, "
        f"{counts.get('cannot_determine')} CANNOT DETERMINE)",
        f"- **Benchmark:** SPY total return, PINNED offline "
        f"(`{receipt.get('market_benchmark', {}).get('benchmark_id')}`, "
        f"{receipt.get('market_benchmark', {}).get('n_periods')} sessions)",
        f"- **Frequency:** daily · HAC lag "
        f"{receipt.get('ruler', {}).get('hac_lag')} · floor "
        f"{receipt.get('ruler', {}).get('min_obs')} observations",
        f"- **Leverage-neutral:** {receipt.get('ruler', {}).get('leverage_neutral')}",
        f"- **RF:** pinned Fama-French daily, last real observation "
        f"{rf.get('last_observed')}; {rf.get('days_carried_forward')} later "
        f"sessions held flat at {rf.get('carried_annualised_pct')}%/yr "
        f"(each row also carries the rf=0 sensitivity)",
        "",
        head, rule, *body, "",
        "**Cost basis legend** — "
        + " · ".join(f"*{tag}* = {basis}" for basis, tag in COST_TAGS.items()),
        "",
        "**`raw exc %/yr` and `lev-neutral exc %/yr` annualise a window of "
        "40-47 sessions.** They are rates, not forecasts, and their standard "
        "errors are large; the `pp` columns are what actually happened.",
        "",
        "## Readable books, one sentence each",
        "",
    ]
    readable = [r for r in receipt.get("rows", []) if r.get("verdict") == "OK"]
    lines += [f"- {r['headline']}" for r in readable] or \
             ["- (none — no forward book was gradeable)"]
    lines += ["", "## Refusals, and why", ""]
    refused = [r for r in receipt.get("rows", []) if r.get("verdict") != "OK"]
    lines += [f"- **{r['lane']}** — {r['why']}" for r in refused] or \
             ["- (none)"]

    sm = receipt.get("stale_mark_finding", {})
    if sm.get("n_flagged"):
        lines += [
            "",
            "## The beta column has a bias, and it points DOWN",
            "",
            f"**{sm['n_flagged']} readable books load more on YESTERDAY'S "
            f"market than on today's:** {', '.join(sm['lanes_flagged'])}.",
            "",
            f"- {sm['what_it_means']}",
            f"- {sm['second_consequence']}",
            f"- How to settle it: {sm['how_to_settle_it']}",
        ]
    lines += [
        "",
        "## Where the series were looked for",
        "",
        "```json",
        json.dumps(disc, indent=1, default=str)[:4000],
        "```",
        "",
        f"_Receipt: `backend/data/optimus/growth_book/G7_forward_lanes.json`_",
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT_JSON))
    ap.add_argument("--md", default=str(OUT_MD))
    ap.add_argument("--min-obs", type=int, default=MIN_OBS, dest="min_obs")
    ap.add_argument("--financing-bps", type=float, default=FINANCING_BPS_ANNUAL,
                    dest="financing_bps")
    ap.add_argument("--gross-cap", type=float, default=GROSS_CAP, dest="gross_cap")
    ap.add_argument("--hac-lag", type=int, default=HAC_LAG, dest="hac_lag")
    ap.add_argument("--trading-days", type=int, default=TRADING_DAYS,
                    dest="trading_days")
    ap.add_argument("--terminal-repo", default=str(TERMINAL_REPO),
                    dest="terminal_repo")
    args = ap.parse_args(argv)
    cmdline = list(sys.argv) if argv is None else ["growth_g7_forward_lanes", *argv]
    try:
        receipt = run(min_obs=args.min_obs, financing_bps=args.financing_bps,
                      gross_cap=args.gross_cap, hac_lag=args.hac_lag,
                      trading_days=args.trading_days,
                      terminal_repo=args.terminal_repo)
    except Exception:                                             # noqa: BLE001
        receipt = {"item": "G7", "verdict": "FAILED",
                   "headline": "raised -- the traceback IS the receipt",
                   "traceback": traceback.format_exc()[-6000:], "rows": []}
    # THE ONE PLACE PROVENANCE IS WRITTEN -- a failed run gets it too, because
    # what a crashed job opened before it crashed is the useful half.
    attach(receipt, cmdline,
           resolve_config(args, _MODULE_DEFAULTS, argv=cmdline), RUN_INPUTS)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    Path(args.md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.md).write_text(to_markdown(receipt), encoding="utf-8")
    print(receipt.get("headline"))
    print(f"receipt -> {out}")
    print(f"table   -> {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
