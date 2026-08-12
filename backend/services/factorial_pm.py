"""FACTORIAL-PM-1 — his claim as a matrix: picks × management.

PREREG: `Aegis module/TRIALS/PREREG_FACTORIAL_PM_1.md` @ c5b81aa (frozen).
The claim under test (Murat, verbatim): "my portfolio with good
timing/management would be a great winner with the stock picks."

DESIGN (frozen before any cell was computed)
============================================
Window 2025-11-07 -> 2026-08-10, prices = the frozen conviction CSV with the
CONVICTION-REPLAY-1 corporate-action machinery (APLT/SLNO). Synthetic names
(reconstructed series, two known points) are EXCLUDED from every daily-path
statistic and INCLUDED in period returns via entry + payout, carried as a
disclosed step path (flat at entry until the deal date, then the cash payout).

Books:  B1 his 13 picks · B2 his 48 non-picks · B3 random-13 from the 61-name
pool (1,000 draws, `np.random.default_rng(20260811)`; the cell is the
DISTRIBUTION, never one draw) · B4 funnel = NOT_EVALUABLE (look-ahead by
construction; forward cell registered from 2026-08-11).

Managements, all mechanical, all parameter-frozen before this run:
  M1  equal-weight buy-and-hold, drifting (the CONVICTION-REPLAY-1 basket).
  M2  vol-target: w_t = min(1, 0.20 / sigma_book(63d ann.)), daily, ONE-DAY
      LAG, cash earns 0, 10 bps one-way on exposure changes. Parameters are
      the `exit_engine` defaults frozen in backend/config.py long before
      tonight (vol_target_annual=0.20, vol_lookback_days=63).
  M3  kill-condition-managed — a checkability audit runs FIRST; a condition
      counts as checkable only if it can be evaluated point-in-time from the
      frozen price CSV. If <50% of a book's names are checkable the cell is
      REFUSED_NOT_MECHANIZABLE. Thesis text is never converted into invented
      rules.
  M4  the mirror lane's frozen rules (book_lanes.yaml mirror block, frozen
      2026-06): monthly HRP, 5% drift trigger, 5 bps + 1 bp costs, max single
      name 25%. The HRP history gate (paper_portfolios.yaml optimizer_params:
      min_observations=252) CANNOT pass on the 197-bar frozen panel, so every
      rebalance runs the lane's frozen loud fallback — equal weight over the
      book's still-trading names. That is reported on the cell, not hidden.

Statistics: paired differences on the SAME price paths (§18), circular
21-trading-day block-bootstrap SE, and a MEASURED 80%-power MDE (planted
effects, mirroring conviction_replay.measure_mde) beside every claim (§19).
No annualization of the 9-month window, anywhere.

WHAT THIS MAY NOT DO: see the prereg §4 — no lane seeding, no skill grading,
no B3 collapse to a point, no cell without its MDE.
"""

from __future__ import annotations

import logging
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services import kill_conditions as KC
from backend.services.conviction_prices import (CORPORATE_ACTIONS, load_prices,
                                                synthetic_names)
from backend.services.conviction_sheets import load_sheet

logger = logging.getLogger(__name__)

TRIAL = "FACTORIAL-PM-1"
PREREG = "Aegis module/TRIALS/PREREG_FACTORIAL_PM_1.md @ c5b81aa"

WINDOW_START = "2025-11-07"
WINDOW_END = "2026-08-10"
WAR_START = "2026-06-04"       # H3 sub-window, frozen in the prereg
WAR_END = "2026-07-29"

SEED = 20260811                # the registered seed for the B3 draws
N_B3 = 1000
BLOCK = 21                     # circular block length, trading days
SIG_Z = 1.96
TARGET_POWER = 0.80

# ── M2: exit_engine defaults, frozen in backend/config.py (lines ~984-985) ──
M2_VOL_TARGET = 0.20
M2_LOOKBACK = 63
M2_COST_ONEWAY = 10.0 / 10_000
M2_TRADING_DAYS = 252

# ── M4: mirror lane frozen rules (backend/data/book_lanes.yaml mirror) ──────
M4_DRIFT_TRIGGER = 0.05
M4_REBALANCE_DAYS = 28          # `should_rebalance` monthly = >= 28 calendar d
M4_COST_RATE = (5.0 + 1.0) / 10_000   # transaction_cost_bps + slippage_bps
M4_MAX_SINGLE_NAME = 0.25

# ── HRP gate: paper_portfolios.yaml optimizer_params (config-v2, frozen) ────
HRP_LOOKBACK = 504
HRP_MIN_OBS = 252
HRP_MIN_NONZERO_FRACTION = 0.5

#: MDE grid in TERMINAL-WEALTH POINTS per $1 (0.05 = 5 pts of the window).
MDE_GRID = (0.0, 0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10,
            0.15, 0.20, 0.30, 0.50, 0.75, 1.00, 1.50, 2.00)


# ═════════════════════════════════════════════════════════════════════════════
# Books
# ═════════════════════════════════════════════════════════════════════════════

def load_books() -> dict:
    """B1/B2/pool from the 2025-11-07 sheet. Sizes are ASSERTED, not assumed."""
    sheet = load_sheet("2025-11-07")
    b1 = sorted(h.ticker for h in sheet.portfolio)
    b2 = sorted(h.ticker for h in sheet.non_picks())
    pool = sorted(set(b1) | set(b2))
    if len(b1) != 13 or len(b2) != 48 or len(pool) != 61:
        raise ValueError(
            f"book sizes changed under the trial: |B1|={len(b1)} |B2|={len(b2)} "
            f"|pool|={len(pool)} — the prereg froze 13/48/61; investigate before "
            f"any number is reported (decision rule: contaminated cell = VOID)")
    return {"B1": b1, "B2": b2, "pool": pool}


def b3_draws(pool: list[str], n_draws: int = N_B3,
             seed: int = SEED) -> list[list[str]]:
    """The registered 1,000 seeded random-13 draws. NEVER one draw."""
    if n_draws < 2:
        raise ValueError(
            "B3 is a DISTRIBUTION cell (prereg §4): it may not be collapsed "
            f"to {n_draws} draw(s)")
    rng = np.random.default_rng(seed)
    arr = np.array(sorted(pool))
    return [sorted(rng.choice(arr, size=13, replace=False).tolist())
            for _ in range(n_draws)]


# ═════════════════════════════════════════════════════════════════════════════
# Prices
# ═════════════════════════════════════════════════════════════════════════════

def load_panel() -> pd.DataFrame:
    """The frozen conviction panel, step-paths filled for terminated names.

    `load_prices()` already carries each terminated name at its cash payout
    from the effective date; the forward-fill here closes the gap between the
    sheet entry and the deal date with a FLAT segment. That segment is a
    disclosed assumption — which is exactly why synthetic names are excluded
    from every daily-path statistic (sigma, MFE/MAE, drawdown attribution)
    while their period return (entry -> payout) is exact.
    """
    return load_prices().ffill()   # leading NaNs (pre-listing) stay NaN


def _norm_window(panel: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Window prices normalized to 1.0 at the window start row."""
    px = panel.loc[WINDOW_START:WINDOW_END, tickers]
    first = px.iloc[0]
    if first.isna().any():
        missing = list(first[first.isna()].index)
        raise ValueError(
            f"{missing} have no price at {WINDOW_START}: a name dropped from "
            f"one side of a cell moves the answer invisibly (APLT corpse)")
    return px / first


# ═════════════════════════════════════════════════════════════════════════════
# Managements — each returns a dict with a daily wealth path and diagnostics
# ═════════════════════════════════════════════════════════════════════════════

def m1_cell(panel: pd.DataFrame, tickers: list[str]) -> dict:
    """M1: equal-weight buy-and-hold, drifting. No costs (entry costs are
    excluded uniformly across ALL cells; only management-induced trading is
    priced)."""
    norm = _norm_window(panel, tickers)
    wealth = norm.mean(axis=1)                       # starts at exactly 1.0
    daily = wealth.pct_change().dropna()
    return {
        "management": "M1", "wealth_path": wealth, "daily_returns": daily,
        "terminal_wealth": float(wealth.iloc[-1]),
        "n_names": len(tickers),
        "synthetic_included_via_step_path": sorted(set(tickers)
                                                   & synthetic_names()),
    }


def _sigma_input_returns(panel: pd.DataFrame, tickers: list[str]) -> pd.Series:
    """Daily returns feeding the M2 vol estimate — synthetic names EXCLUDED.

    Pre-window warm-up (~8 returns): equal-weight daily mean of the names'
    returns. From the window start: the drifting sub-book's own returns.
    The warm-up convention is disclosed; it only affects the first weeks'
    sigma while the 63d window fills.
    """
    non_synth = [t for t in tickers if t not in synthetic_names()]
    if not non_synth:
        raise ValueError("a book of only synthetic names has no daily path "
                         "to estimate volatility from")
    pre = panel.loc[:WINDOW_START, non_synth]
    pre_r = pre.pct_change().iloc[1:].mean(axis=1)          # ends AT the start
    win = _norm_window(panel, non_synth).mean(axis=1)
    win_r = win.pct_change().dropna()
    return pd.concat([pre_r, win_r])


def m2_cell(panel: pd.DataFrame, tickers: list[str]) -> dict:
    """M2: book-level vol target, one-day lag, cash earns 0, 10 bps one-way.

    LEAK GEOMETRY: the exposure applied to the return ending on day t is
    decided from sigma computed on returns ENDING NO LATER THAN day t-1
    (`sigma.shift(1)`). Perturbing day t's return can change exposure from
    day t+1 on, never day t's own. A test asserts this.
    """
    base = m1_cell(panel, tickers)
    r = base["daily_returns"]

    sig_in = _sigma_input_returns(panel, tickers)
    sigma = (sig_in.rolling(M2_LOOKBACK, min_periods=2).std(ddof=1)
             * math.sqrt(M2_TRADING_DAYS))
    w = (M2_VOL_TARGET / sigma.shift(1)).clip(upper=1.0).reindex(r.index)
    n_unmeasurable = int(w.isna().sum())
    if n_unmeasurable:
        # exit_engine convention: can't size what we can't measure -> 0.0.
        # With min_periods=2 and the warm-up this should never fire; if it
        # does, it is COUNTED and reported, never silent.
        logger.warning("M2: %d day(s) with unmeasurable vol -> exposure 0.0",
                       n_unmeasurable)
        w = w.fillna(0.0)
    w = w.clip(lower=0.0)

    dw = w.diff().abs()
    dw.iloc[0] = 0.0            # entry is not an exposure CHANGE (as with M1)
    strat = w * r - M2_COST_ONEWAY * dw
    wealth = (1.0 + strat).cumprod()
    wealth = pd.concat([pd.Series([1.0], index=base["wealth_path"].index[:1]),
                        wealth])
    return {
        "management": "M2", "wealth_path": wealth, "daily_returns": strat,
        "terminal_wealth": float(wealth.iloc[-1]),
        "exposure_path": w,
        "mean_exposure": float(w.mean()), "min_exposure": float(w.min()),
        "days_below_full": int((w < 1.0 - 1e-12).sum()),
        "total_cost_paid_pts": float((M2_COST_ONEWAY * dw).sum() * 100),
        "n_unmeasurable_vol_days": n_unmeasurable,
        "sigma_estimated_on": sorted(set(tickers) - synthetic_names()),
        "params": {"vol_target_annual": M2_VOL_TARGET,
                   "vol_lookback_days": M2_LOOKBACK,
                   "cost_bps_oneway": 10, "lag_days": 1, "cash_earns": 0.0},
    }


def _enforce_single_name_cap(weights: dict[str, float],
                             cap: float) -> dict[str, float]:
    """Waterfill single-name cap — same algorithm as rules.enforce_position_limits
    pass 1 (replicated locally so the runner stays hermetic; the engine module
    is READ-ONLY to this trial). The mirror's sector cap is NOT applied: the
    frozen data carries no point-in-time sector map, and under the equal-weight
    fallback it could bind only if >=8 of 13 drawn names shared one sector
    (~3% of B3 draws at most). Disclosed, not silent."""
    result = dict(weights)
    frozen: set[str] = set()
    for _ in range(len(result)):
        excess, newly = 0.0, []
        for t, wgt in result.items():
            if t in frozen:
                continue
            if wgt > cap + 1e-10:
                excess += wgt - cap
                result[t] = cap
                newly.append(t)
        if excess <= 1e-10:
            break
        frozen.update(newly)
        unfrozen = [t for t in result if t not in frozen]
        tot = sum(result[t] for t in unfrozen)
        if tot > 0:
            for t in unfrozen:
                result[t] += excess * (result[t] / tot)
        elif unfrozen:
            for t in unfrozen:
                result[t] += excess / len(unfrozen)
    return result


def _m4_targets(panel: pd.DataFrame, tickers: list[str],
                as_of: pd.Timestamp) -> tuple[dict[str, float], str]:
    """Mirror-lane target weights as of a date, with the frozen HRP gate.

    Names terminated on/before `as_of` leave the target universe (their cash
    payout is redistributed at the next rebalance — that IS the PM action).
    The HRP gate is run honestly; on this 197-bar panel it always fails
    min_observations=252 and the lane's frozen fallback (equal weight over
    priced names) governs. The reason string is recorded per rebalance.
    """
    active = [t for t in tickers
              if not (t in CORPORATE_ACTIONS
                      and as_of >= pd.Timestamp(CORPORATE_ACTIONS[t].effective))]
    if not active:
        return {}, "no active names"
    hist = panel.loc[:as_of, [t for t in active
                              if t not in synthetic_names()]]
    rets = hist.pct_change().dropna(how="all").iloc[-HRP_LOOKBACK:]
    rets = rets.dropna(axis=1, thresh=HRP_MIN_OBS).dropna()
    if len(rets) < HRP_MIN_OBS or rets.shape[1] < 2:
        reason = (f"hrp_fallback_equal_weight: insufficient as-of history "
                  f"({len(rets)} obs, need {HRP_MIN_OBS}+)")
        weights = {t: 1.0 / len(active) for t in active}
    else:                                   # pragma: no cover — cannot happen
        from backend.services.portfolio_optimizer import optimize_hrp
        result = optimize_hrp(list(rets.columns), returns=rets)
        raw = (result or {}).get("weights") or {}
        tot = sum(raw.values())
        if not raw or tot <= 0:
            reason = "hrp_fallback_equal_weight: optimizer returned no weights"
            weights = {t: 1.0 / len(active) for t in active}
        else:
            reason = "hrp"
            weights = {t: wgt / tot for t, wgt in raw.items()}
    return _enforce_single_name_cap(weights, M4_MAX_SINGLE_NAME), reason


def m4_cell(panel: pd.DataFrame, tickers: list[str]) -> dict:
    """M4: the mirror lane's frozen mechanical PM, replayed daily."""
    norm = _norm_window(panel, tickers)
    dates = norm.index
    rel = norm.pct_change()

    weights, reason0 = _m4_targets(panel, tickers, dates[0])
    target = dict(weights)
    last_rebal = dates[0]
    rebalances = [{"date": str(dates[0].date()), "reason": "initialization",
                   "optimizer": reason0, "turnover": 0.0}]
    wealth = [1.0]
    strat_r = []
    total_cost = 0.0
    for t in dates[1:]:
        day = rel.loc[t].fillna(0.0)
        port_r = float(sum(w * day.get(tk, 0.0) for tk, w in weights.items()))
        cost = 0.0
        # drift the weights with the day's returns
        if 1.0 + port_r > 0:
            weights = {tk: w * (1.0 + day.get(tk, 0.0)) / (1.0 + port_r)
                       for tk, w in weights.items()}
        # rebalance check — same semantics as rules.should_rebalance
        drift = max((abs(weights.get(k, 0.0) - target.get(k, 0.0))
                     for k in set(weights) | set(target)), default=0.0)
        trigger = ("drift" if drift > M4_DRIFT_TRIGGER
                   else "monthly" if (t - last_rebal).days >= M4_REBALANCE_DAYS
                   else None)
        if trigger:
            new_target, opt_reason = _m4_targets(panel, tickers, t)
            turnover = sum(abs(new_target.get(k, 0.0) - weights.get(k, 0.0))
                           for k in set(new_target) | set(weights))
            cost = M4_COST_RATE * turnover
            total_cost += cost
            weights = dict(new_target)
            target = dict(new_target)
            last_rebal = t
            rebalances.append({"date": str(t.date()), "reason": trigger,
                               "optimizer": opt_reason,
                               "turnover": round(turnover, 4)})
        net = (1.0 + port_r) * (1.0 - cost) - 1.0
        strat_r.append(net)
        wealth.append(wealth[-1] * (1.0 + net))

    wealth_s = pd.Series(wealth, index=dates)
    hrp_ever_ran = any(r["optimizer"] == "hrp" for r in rebalances)
    return {
        "management": "M4", "wealth_path": wealth_s,
        "daily_returns": pd.Series(strat_r, index=dates[1:]),
        "terminal_wealth": float(wealth_s.iloc[-1]),
        "n_rebalances": len(rebalances) - 1,
        "rebalances": rebalances,
        "total_cost_paid_pts": float(total_cost * 100),
        "hrp_ever_passed_its_gate": hrp_ever_ran,
        "hrp_gate_note": ("the frozen gate (min_observations=252, "
                          "paper_portfolios.yaml optimizer_params) can never "
                          "pass on the 197-bar frozen panel; every rebalance "
                          "ran the lane's frozen loud fallback (equal weight "
                          "over still-trading names). This cell is therefore "
                          "'mirror rules under their fallback', labelled as "
                          "such — NOT an HRP result."),
        "params": {"rebalance": "monthly(>=28d)", "drift_trigger": 0.05,
                   "cost_bps": 5, "slippage_bps": 1, "max_single_name": 0.25,
                   "sector_cap": "NOT applied — no frozen PIT sector map; "
                                 "disclosed above"},
    }


# ═════════════════════════════════════════════════════════════════════════════
# M3 — the checkability audit runs FIRST, and refusal is the finding
# ═════════════════════════════════════════════════════════════════════════════

#: What a condition needs, keyed by the data feed it presupposes. The frozen
#: data on hand is EXACTLY ONE feed: the daily price-history CSV. There is no
#: fundamentals feed for backdated quarters, no analyst/consensus history, no
#: clinical/news event stream.
_FEED_PATTERNS: tuple[tuple[str, str], ...] = (
    ("analyst_consensus_history",
     r"consensus|analyst|coverage|target|revision"),
    ("fundamentals_quarterly",
     r"cash runway|backlog|revenue|retention|loss ratio|concentration|"
     r"quarter"),
    ("clinical_regulatory_events",
     r"clinical|endpoint|programme|program\b|regulatory|adverse|hold"),
    ("corporate_events",
     r"partnership|oem|discontinued|successor|lapses|dilution"),
    ("narrative_qualitative",
     r"narrative|rotation|cracks"),
)

#: The only pattern the price CSV could mechanize: an explicit numeric
#: price/drawdown rule ("price falls below 5", "closes under $12", "-30% stop").
_PRICE_RULE = re.compile(
    r"(price|close|share|stop|drawdown)\D{0,40}\d", re.IGNORECASE)


def condition_checkability(text: str | None) -> dict:
    """Is one kill-condition text evaluable point-in-time from prices alone?"""
    if not text or not str(text).strip():
        return {"checkable": False, "required_feeds": [],
                "reason": "no kill condition on record from any source"}
    low = str(text).lower()
    feeds = sorted(name for name, pat in _FEED_PATTERNS
                   if re.search(pat, low))
    if feeds:
        return {"checkable": False, "required_feeds": feeds,
                "reason": ("requires " + ", ".join(feeds) + " — none exists "
                           "point-in-time in the frozen data (price CSV only)")}
    if _PRICE_RULE.search(low):
        return {"checkable": True, "required_feeds": ["price_history"],
                "reason": "explicit numeric price rule, evaluable from the CSV"}
    return {"checkable": False, "required_feeds": ["unclassifiable"],
            "reason": ("no mechanical predicate: converting this prose into a "
                       "rule would be inventing the rule (prereg M3 clause)")}


def _conditions_on_record() -> dict[str, dict]:
    """ticker -> {text, provenance} from murat_book.yaml + the §0 defaults."""
    out: dict[str, dict] = {}
    book_file = (Path(__file__).resolve().parents[1] / "data"
                 / "murat_book.yaml")
    if book_file.exists():
        import yaml
        data = yaml.safe_load(book_file.read_text(encoding="utf-8")) or {}
        for pos in data.get("positions", []) or []:
            text = pos.get("murat_override") or pos.get("kill_condition")
            if text:
                out[str(pos.get("ticker", "")).upper()] = {
                    "text": text,
                    "provenance": pos.get("kill_condition_provenance",
                                          KC.PROVENANCE_MURAT_STATED)}
    for tkr, text in KC.AUTO_ADOPTED_KILL_CONDITIONS.items():
        out.setdefault(tkr, {"text": text,
                             "provenance": KC.PROVENANCE_AUTO_ADOPTED})
    return out


def m3_audit(tickers: list[str],
             conditions: dict[str, dict] | None = None) -> dict:
    """The M3 cell. Audit first; below 50% checkable -> the cell REFUSES.

    A refusal is a finding (CANON). The audit prints WHICH conditions failed
    and WHY; it never converts thesis prose into an invented rule.
    """
    conds = _conditions_on_record() if conditions is None else conditions
    rows = []
    for t in tickers:
        rec = conds.get(t, {})
        chk = condition_checkability(rec.get("text"))
        rows.append({"ticker": t, "condition": rec.get("text", ""),
                     "provenance": rec.get("provenance", ""), **chk})
    n_checkable = sum(r["checkable"] for r in rows)
    frac = n_checkable / len(tickers) if tickers else 0.0
    refused = frac < 0.5
    return {
        "management": "M3",
        "status": "REFUSED_NOT_MECHANIZABLE" if refused else "CHECKABLE",
        "n_names": len(tickers), "n_checkable": n_checkable,
        "fraction_checkable": round(frac, 3),
        "per_name": rows,
        "note": ("fewer than 50% of the book's names carry a kill condition "
                 "that can be evaluated point-in-time from the frozen price "
                 "CSV — the cell refuses rather than inventing rules"
                 if refused else
                 "checkability >= 50%; a mechanized exit replay would be "
                 "required — NOT implemented tonight; refuse rather than "
                 "improvise (this branch is not expected to be reachable "
                 "with the frozen data)"),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Statistics — block bootstrap on the SAME paths, measured MDEs
# ═════════════════════════════════════════════════════════════════════════════

def _circ_roll_sums(x: np.ndarray, length: int) -> np.ndarray:
    """s[i] = sum of x[i .. i+length-1], circular. Vectorized O(n)."""
    n = len(x)
    c = np.concatenate([x, x[:length]])
    cs = np.concatenate([[0.0], np.cumsum(c)])
    return cs[length:length + n] - cs[:n]


def _boot_log_totals(logr: np.ndarray, n_boot: int,
                     rng: np.random.Generator,
                     starts: tuple[np.ndarray, np.ndarray] | None = None
                     ) -> np.ndarray:
    """Terminal log-wealth under circular 21td block resampling."""
    T = len(logr)
    k, rem = divmod(T, BLOCK)
    if starts is None:
        s_full = rng.integers(0, T, size=(n_boot, k))
        s_rem = rng.integers(0, T, size=n_boot) if rem else None
    else:
        s_full, s_rem = starts
    tot = _circ_roll_sums(logr, BLOCK)[s_full].sum(axis=1)
    if rem:
        tot = tot + _circ_roll_sums(logr, rem)[s_rem]
    return tot


def _joint_starts(T: int, n_boot: int, rng: np.random.Generator):
    k, rem = divmod(T, BLOCK)
    return (rng.integers(0, T, size=(n_boot, k)),
            rng.integers(0, T, size=n_boot) if rem else None)


def paired_terminal_diff(ret_a: pd.Series, ret_b: pd.Series, *,
                         n_boot: int = 2000, seed: int = SEED) -> dict:
    """Terminal-wealth difference a-b, same paths, joint block bootstrap SE.

    The SAME resampled day-blocks are applied to both legs (§18: a difference
    is tested as a difference, with its own SE, never two marginals)."""
    idx = ret_a.index.intersection(ret_b.index)
    la = np.log1p(ret_a.reindex(idx).to_numpy(float))
    lb = np.log1p(ret_b.reindex(idx).to_numpy(float))
    rng = np.random.default_rng(seed)
    starts = _joint_starts(len(la), n_boot, rng)
    wa = np.exp(_boot_log_totals(la, n_boot, rng, starts))
    wb = np.exp(_boot_log_totals(lb, n_boot, rng, starts))
    d_obs = float(np.exp(la.sum()) - np.exp(lb.sum()))
    se = float(np.std(wa - wb, ddof=1))
    z = d_obs / se if se > 0 else float("inf") * np.sign(d_obs or 1)
    return {"difference_pts": d_obs * 100, "se_pts": se * 100,
            "z": float(z), "significant_at_5pct": bool(abs(z) >= SIG_Z),
            "n_days": int(len(la)), "n_boot": n_boot,
            "block_days": BLOCK}


def _resample_indices(T: int, rng: np.random.Generator) -> np.ndarray:
    k, rem = divmod(T, BLOCK)
    parts = [(np.arange(BLOCK) + s) % T for s in rng.integers(0, T, size=k)]
    if rem:
        parts.append((np.arange(rem) + rng.integers(0, T)) % T)
    return np.concatenate(parts) if parts else np.arange(0)


def measure_pair_mde(ret_a: pd.Series, ret_b: pd.Series, *,
                     grid: tuple = MDE_GRID, n_sim: int = 250,
                     n_boot: int = 300, seed: int = SEED,
                     target_power: float = TARGET_POWER) -> dict:
    """MEASURED 80%-power MDE for a paired terminal-wealth difference (§19).

    Mirrors conviction_replay.measure_mde: plant an effect of KNOWN size
    (delta terminal-wealth points on the managed leg, spread evenly in log
    space), rebuild the world by block resampling BOTH legs jointly, run the
    real test, count how often it fires. Never a formula.

    NULL-CENTERED: the managed leg is first shifted by a constant daily drift
    so the OBSERVED pair has zero terminal difference — the planted delta is
    then the world's TRUE effect. Without this the observed effect rides
    inside every world and biases the MDE by its own size."""
    idx = ret_a.index.intersection(ret_b.index)
    la = np.log1p(ret_a.reindex(idx).to_numpy(float))
    lb = np.log1p(ret_b.reindex(idx).to_numpy(float))
    T = len(la)
    la = la - (la.sum() - lb.sum()) / T          # null-center the pair
    rng = np.random.default_rng(seed + 7)
    rows = []
    for delta in grid:
        fires = 0
        for _ in range(n_sim):
            ridx = _resample_indices(T, rng)
            aw, bw = la[ridx], lb[ridx]
            w_a = math.exp(aw.sum())
            aw = aw + math.log((w_a + delta) / w_a) / T
            inner = np.random.default_rng(int(rng.integers(1 << 31)))
            starts = _joint_starts(T, n_boot, inner)
            ba = np.exp(_boot_log_totals(aw, n_boot, inner, starts))
            bb = np.exp(_boot_log_totals(bw, n_boot, inner, starts))
            d = math.exp(aw.sum()) - math.exp(bw.sum())
            se = float(np.std(ba - bb, ddof=1))
            fires += bool(se > 0 and abs(d / se) >= SIG_Z)
        rows.append({"planted_pts": delta * 100, "power": fires / n_sim})
        if rows[-1]["power"] >= target_power:
            break
    hit = [r for r in rows if r["power"] >= target_power]
    return {"mde_pts_at_80pct_power": hit[0]["planted_pts"] if hit else None,
            "grid": rows, "target_power": target_power,
            "note": ("measured by planting terminal-wealth effects of known "
                     "size on the managed leg of jointly block-resampled "
                     "paths — not derived from a formula"),
            "if_none": ("no effect on the grid reached 80% power: the design "
                        "cannot reliably detect ANY management effect of "
                        "plausible size; a null is a statement about the "
                        "design (CANON §19)")}


def difference_of_differences(eff_b1_pts: float, b1_m1: pd.Series,
                              b1_mgd: pd.Series,
                              b3_m1_logs: np.ndarray, b3_mgd_logs: np.ndarray,
                              eff_b3_all_pts: np.ndarray, *,
                              n_boot: int = 1000, seed: int = SEED) -> dict:
    """H2: (management effect on B1) - (mean effect on B3), with its OWN SE.

    Point estimate uses ALL B3 draws; the bootstrap SE uses the passed
    subsample of draw paths (columns), resampled on the SAME day-blocks as
    B1 (§18). Registered expectation: NOT detectable at this sample."""
    idx = b1_m1.index.intersection(b1_mgd.index)
    la = np.log1p(b1_mgd.reindex(idx).to_numpy(float))
    lb = np.log1p(b1_m1.reindex(idx).to_numpy(float))
    T = len(la)
    if b3_m1_logs.shape[0] != T:
        raise ValueError("B1 and B3 paths must share the day axis to be "
                         "resampled jointly")
    point = eff_b1_pts - float(eff_b3_all_pts.mean())
    rng = np.random.default_rng(seed + 13)
    sums_m1 = _circ_roll_sums_matrix(b3_m1_logs, BLOCK)
    sums_mg = _circ_roll_sums_matrix(b3_mgd_logs, BLOCK)
    k, rem = divmod(T, BLOCK)
    rem_m1 = _circ_roll_sums_matrix(b3_m1_logs, rem) if rem else None
    rem_mg = _circ_roll_sums_matrix(b3_mgd_logs, rem) if rem else None
    sa, sb_ = _circ_roll_sums(la, BLOCK), _circ_roll_sums(lb, BLOCK)
    ra = _circ_roll_sums(la, rem) if rem else None
    rb = _circ_roll_sums(lb, rem) if rem else None
    dods = np.empty(n_boot)
    for i in range(n_boot):
        s_full = rng.integers(0, T, size=k)
        s_rem = int(rng.integers(0, T)) if rem else None
        b1_eff = (math.exp(sa[s_full].sum() + (ra[s_rem] if rem else 0.0))
                  - math.exp(sb_[s_full].sum() + (rb[s_rem] if rem else 0.0)))
        m1_tot = sums_m1[s_full].sum(axis=0)
        mg_tot = sums_mg[s_full].sum(axis=0)
        if rem:
            m1_tot = m1_tot + rem_m1[s_rem]
            mg_tot = mg_tot + rem_mg[s_rem]
        b3_eff = float(np.mean(np.exp(mg_tot) - np.exp(m1_tot)))
        dods[i] = b1_eff * 100 - b3_eff * 100
    se = float(np.std(dods, ddof=1))
    z = point / se if se > 0 else 0.0
    return {"dod_pts": point, "se_pts": se, "z": float(z),
            "significant_at_5pct": bool(abs(z) >= SIG_Z),
            "n_b3_draws_point": int(len(eff_b3_all_pts)),
            "n_b3_draws_se": int(b3_m1_logs.shape[1]), "n_boot": n_boot,
            "note": ("SE from a joint day-block bootstrap over B1 and a "
                     "B3 draw subsample; point estimate over all draws")}


def measure_dod_mde(b1_m1: pd.Series, b1_mgd: pd.Series,
                    b3_m1_logs: np.ndarray, b3_mgd_logs: np.ndarray, *,
                    grid: tuple = (0.05, 0.10, 0.15, 0.20, 0.30, 0.50, 0.75,
                                   1.00),
                    n_sim: int = 120, n_boot: int = 200, seed: int = SEED,
                    target_power: float = TARGET_POWER) -> dict:
    """Measured 80%-power MDE for the H2 difference-of-differences (§19).

    Null-centered the same way as `measure_pair_mde`: B1's managed leg is
    shifted so the observed DoD is zero, then a KNOWN interaction effect
    (delta terminal-wealth points on B1's management effect only) is planted
    in block-resampled worlds and the real DoD test is run on each."""
    idx = b1_m1.index.intersection(b1_mgd.index)
    la = np.log1p(b1_mgd.reindex(idx).to_numpy(float))
    lb = np.log1p(b1_m1.reindex(idx).to_numpy(float))
    T = len(la)
    # center so B1's effect equals B3's mean effect (observed DoD -> 0)
    obs_b3_eff = float(np.mean(np.exp(b3_mgd_logs.sum(axis=0))
                               - np.exp(b3_m1_logs.sum(axis=0))))
    w_b = math.exp(lb.sum())
    target_wa = max(w_b + obs_b3_eff, 1e-6)
    la = la + (math.log(target_wa) - la.sum()) / T

    rng = np.random.default_rng(seed + 29)

    def _dod_and_se(law, lbw, m1w, mgw, inner):
        starts = _joint_starts(T, n_boot, inner)
        s_full, s_rem = starts
        rem = T - (T // BLOCK) * BLOCK
        sa, sb = _circ_roll_sums(law, BLOCK), _circ_roll_sums(lbw, BLOCK)
        sm1 = _circ_roll_sums_matrix(m1w, BLOCK)
        smg = _circ_roll_sums_matrix(mgw, BLOCK)
        ra = _circ_roll_sums(law, rem) if rem else None
        rb = _circ_roll_sums(lbw, rem) if rem else None
        rm1 = _circ_roll_sums_matrix(m1w, rem) if rem else None
        rmg = _circ_roll_sums_matrix(mgw, rem) if rem else None
        dods = np.empty(n_boot)
        for i in range(n_boot):
            f = s_full[i]
            b1_eff = (math.exp(sa[f].sum() + (ra[s_rem[i]] if rem else 0.0))
                      - math.exp(sb[f].sum() + (rb[s_rem[i]] if rem else 0.0)))
            m1t = sm1[f].sum(axis=0)
            mgt = smg[f].sum(axis=0)
            if rem:
                m1t = m1t + rm1[s_rem[i]]
                mgt = mgt + rmg[s_rem[i]]
            dods[i] = b1_eff - float(np.mean(np.exp(mgt) - np.exp(m1t)))
        d_obs = (math.exp(law.sum()) - math.exp(lbw.sum())
                 - float(np.mean(np.exp(mgw.sum(axis=0))
                                 - np.exp(m1w.sum(axis=0)))))
        return d_obs, float(np.std(dods, ddof=1))

    rows = []
    for delta in grid:
        fires = 0
        for _ in range(n_sim):
            ridx = _resample_indices(T, rng)
            law, lbw = la[ridx], lb[ridx]
            m1w, mgw = b3_m1_logs[ridx, :], b3_mgd_logs[ridx, :]
            w_a = math.exp(law.sum())
            law = law + math.log((w_a + delta) / w_a) / T
            inner = np.random.default_rng(int(rng.integers(1 << 31)))
            d, se = _dod_and_se(law, lbw, m1w, mgw, inner)
            fires += bool(se > 0 and abs(d / se) >= SIG_Z)
        rows.append({"planted_pts": delta * 100, "power": fires / n_sim})
        if rows[-1]["power"] >= target_power:
            break
    hit = [r for r in rows if r["power"] >= target_power]
    return {"mde_pts_at_80pct_power": hit[0]["planted_pts"] if hit else None,
            "grid": rows, "target_power": target_power,
            "note": ("measured by planting interaction effects of known size "
                     "on B1's management effect in jointly block-resampled "
                     "worlds (null-centered) — not derived from a formula")}


def _circ_roll_sums_matrix(x: np.ndarray, length: int) -> np.ndarray:
    """Column-wise circular rolling sums for a (T, n) matrix."""
    n = x.shape[0]
    c = np.vstack([x, x[:length]])
    cs = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(c, axis=0)])
    return cs[length:length + n] - cs[:n]


def max_drawdown(wealth: pd.Series, start: str, end: str) -> float:
    """Max drawdown of a wealth path re-based inside [start, end]."""
    w = wealth.loc[start:end]
    if len(w) < 2:
        return float("nan")
    w = w / w.iloc[0]
    return float((w / w.cummax() - 1.0).min())
