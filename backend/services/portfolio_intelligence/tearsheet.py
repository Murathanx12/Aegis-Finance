"""
Lane tearsheets + bootstrap confidence intervals (V4 rigor layer).
==================================================================

Puts honest error bars on the forward record: every headline lane stat
(Sharpe / Sortino / max drawdown) ships with a 95% bootstrap CI, and each
lane gets a full quantstats HTML tearsheet generated from its REAL
``paper_nav`` rows.

Discipline:
- Returns come ONLY from ``paper_nav`` via ``db.get_nav_series`` (read-only —
  the write path is sacred, CANON §5).
- quantstats is used strictly as a renderer: its yfinance download helpers
  are never called. The optional benchmark is fetched through our own
  ``data_fetcher`` (cached) and silently dropped when unavailable.
- Sharpe/Sortino CIs are BCa bootstrap (PyBroker-style, scipy). Max drawdown
  is a PATH statistic — iid resampling destroys the paths that create
  drawdowns — so it gets a circular block bootstrap (percentile CI) instead.
- Seeded RNG throughout: re-running gives the same intervals.

With ~6 weeks of history the intervals are enormous. That is the point —
"Sharpe 1.1 [95% CI: −0.2, 2.4]" is the honest sentence, and the CIs narrow
as the record accrues.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

TRADING_DAYS = 252
CONFIDENCE = 0.95
MIN_OBS = 20  # below this, report insufficient_history instead of a fake CI
_N_RESAMPLES = 2000
_SEED = 42


# ── returns from the forward record ──────────────────────────────────────────


def lane_return_series(lane_id: str, db_path=None):
    """Daily simple returns for a lane from its paper_nav rows (read-only).

    Returns a pd.Series indexed by DatetimeIndex, or None when the lane has
    fewer than 2 NAV rows (unseeded / just-seeded lanes).
    """
    import pandas as pd

    from backend.db import get_connection, get_nav_series

    conn = get_connection(db_path)
    try:
        rows = get_nav_series(conn, lane_id)
    finally:
        conn.close()
    if len(rows) < 2:
        return None
    s = pd.Series(
        [r["nav"] for r in rows],
        index=pd.to_datetime([r["date"] for r in rows]),
        name=lane_id,
    ).sort_index()
    return s.pct_change().dropna()


# ── stat functions (rf=0, quantstats convention; annualized daily) ──────────


def _sharpe(returns: np.ndarray) -> float:
    sd = returns.std(ddof=1)
    if sd < 1e-12:
        return 0.0
    return float(returns.mean() / sd * np.sqrt(TRADING_DAYS))


def _sortino(returns: np.ndarray) -> float:
    downside = returns[returns < 0]
    if downside.size == 0:
        return float("inf")
    dd = np.sqrt((downside**2).sum() / returns.size)
    if dd < 1e-12:
        return 0.0
    return float(returns.mean() / dd * np.sqrt(TRADING_DAYS))


def _max_drawdown(returns: np.ndarray) -> float:
    cum = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(cum)
    return float((cum / peak - 1.0).min())


def _bca_ci(returns: np.ndarray, stat: Callable[[np.ndarray], float],
            seed: int, n_resamples: int = _N_RESAMPLES) -> tuple[float, float, str]:
    """95% BCa bootstrap CI; falls back to percentile when BCa degenerates
    (tiny n / constant resamples make the jackknife acceleration blow up)."""
    from scipy.stats import bootstrap

    for method in ("BCa", "percentile"):
        try:
            res = bootstrap(
                (returns,),
                lambda x: stat(np.asarray(x)),
                n_resamples=n_resamples,
                confidence_level=CONFIDENCE,
                method=method,
                vectorized=False,
                random_state=np.random.default_rng(seed),
            )
            lo, hi = float(res.confidence_interval.low), float(res.confidence_interval.high)
            if np.isfinite(lo) and np.isfinite(hi):
                return lo, hi, method
        except Exception as e:  # noqa: BLE001 — degenerate resamples raise variously
            logger.debug("bootstrap %s failed: %s", method, e)
    return float("nan"), float("nan"), "failed"


def _block_bootstrap_maxdd(returns: np.ndarray, seed: int,
                           n_resamples: int = _N_RESAMPLES) -> tuple[float, float]:
    """Circular block bootstrap percentile CI for max drawdown.

    Blocks of ~sqrt(n) preserve the local autocorrelation that produces
    drawdown paths; circular wrapping keeps every observation equally likely.
    """
    rng = np.random.default_rng(seed)
    n = returns.size
    block = max(5, int(round(np.sqrt(n))))
    n_blocks = int(np.ceil(n / block))
    stats = np.empty(n_resamples)
    for i in range(n_resamples):
        starts = rng.integers(0, n, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel() % n
        stats[i] = _max_drawdown(returns[idx[:n]])
    alpha = (1.0 - CONFIDENCE) / 2.0
    return (float(np.quantile(stats, alpha)), float(np.quantile(stats, 1.0 - alpha)))


def bootstrap_stat_cis(returns, n_resamples: int = _N_RESAMPLES,
                       seed: int = _SEED) -> dict:
    """95% CIs on Sharpe / Sortino / max drawdown for a daily-returns series.

    Returns a plain dict (JSON-ready). Status is ``insufficient_history``
    below MIN_OBS observations — a CI from 10 points is theater, not rigor.
    """
    arr = np.asarray(returns, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = int(arr.size)
    if n < MIN_OBS:
        return {"status": "insufficient_history", "n_obs": n,
                "min_obs": MIN_OBS, "stats": None}

    out: dict = {"status": "ok", "n_obs": n, "confidence": CONFIDENCE,
                 "rf_convention": "rf=0 (raw ratio, quantstats convention)",
                 "stats": {}}

    for name, fn in (("sharpe", _sharpe), ("sortino", _sortino)):
        value = fn(arr)
        if not np.isfinite(value):
            out["stats"][name] = {"value": None, "ci_lo": None, "ci_hi": None,
                                  "method": "undefined"}
            continue
        lo, hi, method = _bca_ci(arr, fn, seed, n_resamples)
        out["stats"][name] = {
            "value": round(value, 4),
            "ci_lo": round(lo, 4) if np.isfinite(lo) else None,
            "ci_hi": round(hi, 4) if np.isfinite(hi) else None,
            "method": method,
        }

    mdd = _max_drawdown(arr)
    lo, hi = _block_bootstrap_maxdd(arr, seed, n_resamples)
    out["stats"]["max_drawdown"] = {
        "value": round(mdd, 4), "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
        "method": "circular_block_percentile",
    }
    return out


def lane_stats_with_cis(lane_id: str, db_path=None) -> dict:
    """Bootstrap-CI stat pack for one lane's forward record."""
    rets = lane_return_series(lane_id, db_path=db_path)
    if rets is None:
        return {"lane_id": lane_id, "status": "insufficient_history",
                "n_obs": 0, "min_obs": MIN_OBS, "stats": None}
    pack = bootstrap_stat_cis(rets.to_numpy())
    pack["lane_id"] = lane_id
    pack["first_date"] = rets.index[0].date().isoformat()
    pack["last_date"] = rets.index[-1].date().isoformat()
    return pack


# ── quantstats HTML tearsheet ────────────────────────────────────────────────


def _benchmark_returns(index) -> Optional[object]:
    """SPY daily returns over the lane's window via OUR data_fetcher (cached).
    None on any failure — the tearsheet renders benchmark-free rather than
    letting quantstats touch the network itself."""
    try:
        from backend.services.data_fetcher import fetch_safe

        start = index[0].date().isoformat()
        end = index[-1].date().isoformat()
        s = fetch_safe("SPY", start, end, name="SPY")
        if s is None or len(s) < 2:
            return None
        bench = s.pct_change().dropna()
        bench.name = "SPY"
        return bench
    except Exception as e:  # noqa: BLE001
        logger.warning("tearsheet benchmark unavailable (disclosed): %s", e)
        return None


def lane_tearsheet_html(lane_id: str, db_path=None,
                        include_benchmark: bool = True) -> str:
    """Full quantstats HTML tearsheet for a lane's forward paper_nav record.

    Raises ValueError when the lane has too little history to render.
    Heavy imports (quantstats/matplotlib) stay inside this function so the
    baseline process footprint is untouched until someone asks for a sheet.
    """
    rets = lane_return_series(lane_id, db_path=db_path)
    if rets is None or len(rets) < 5:
        raise ValueError(
            f"lane '{lane_id}' has insufficient NAV history for a tearsheet"
        )

    import matplotlib

    matplotlib.use("Agg")  # headless — must precede any pyplot import
    import quantstats as qs

    benchmark = _benchmark_returns(rets.index) if include_benchmark else None

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / f"{lane_id}.html"
        qs.reports.html(
            rets,
            benchmark=benchmark,
            output=str(out_path),
            title=f"Aegis lane: {lane_id} (forward paper record)",
            download_filename=f"{lane_id}.html",
        )
        html = out_path.read_text(encoding="utf-8")

    # Honest banner: this is a paper record, and it is young.
    banner = (
        '<div style="background:#fff8e1;border:1px solid #f0c36d;'
        'padding:10px 16px;margin:8px;border-radius:6px;'
        'font-family:sans-serif;font-size:14px">'
        f"Forward <b>paper</b> track record for lane <b>{lane_id}</b> — "
        f"{len(rets)} daily observations. No skill claims before 24 months; "
        "every statistic on this page carries wide uncertainty at this age. "
        "Educational, not financial advice.</div>"
    )
    import re

    injected, n_sub = re.subn(r"(<body[^>]*>)", r"\1" + banner, html, count=1)
    return injected if n_sub else banner + html
