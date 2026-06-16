"""
TRIAL-MULTIFACTOR-IC — cross-sectional multi-factor selection model (forward).

Combines per-name factor signals into one cross-sectional composite score:
z-score each factor across the universe, then a weighted mean (equal weights,
pre-registered). v1 factors = momentum + insider + revisions. Quality (Piotroski)
is DEFERRED: it routes through edgartools, which hangs (see TRIAL-INSIDER-IC) and
must not sit in a scheduled collector until a guarded fundamentals path exists.

The composite is snapshotted forward (`multifactor_score:{ticker}`) so the model's
output is visible and leak-safe-recorded. Validated forward only (T7): rank-IC
against forward returns once a window accrues. Descriptive — never arms a lane.
See `docs/TRIALS/TRIAL-MULTIFACTOR-IC.md`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from statistics import mean, pstdev

from backend.db import get_connection, get_latest_observable, snapshot
from backend.services.portfolio_intelligence.insider_collector import book_universe

logger = logging.getLogger(__name__)

KEY_PREFIX = "multifactor_score:"
# Pre-registered equal weights over the v1 factor set.
FACTOR_WEIGHTS = {"momentum": 1.0, "insider": 1.0, "revisions": 1.0}


def _zscore(d: dict[str, float]) -> dict[str, float]:
    """Cross-sectional z-score. Degenerate cases (n<2 or zero spread) → all 0."""
    vals = list(d.values())
    if len(vals) < 2:
        return {k: 0.0 for k in d}
    mu, sd = mean(vals), pstdev(vals)
    if sd == 0:
        return {k: 0.0 for k in d}
    return {k: (v - mu) / sd for k, v in d.items()}


def compute_multifactor_scores(components: dict[str, dict[str, float]],
                               weights: dict[str, float] | None = None) -> dict[str, float]:
    """Composite cross-sectional score per ticker (pure, the frozen estimator):
    z-score each factor across the universe, then weighted-mean the available
    factors per ticker (a ticker missing a factor just uses the rest)."""
    if not components:
        return {}
    weights = weights or FACTOR_WEIGHTS
    z = {f: _zscore(scores) for f, scores in components.items()}
    tickers: set[str] = set()
    for scores in components.values():
        tickers |= set(scores)
    out: dict[str, float] = {}
    for t in tickers:
        num = den = 0.0
        for f in components:
            if t in z[f]:
                w = weights.get(f, 1.0)
                num += w * z[f][t]
                den += w
        out[t] = round(num / den, 4) if den else 0.0
    return out


def _read_pit_scores(conn, prefix: str, tickers: list[str]) -> dict[str, float]:
    """Latest leak-safe value per ticker for a PIT key prefix (0.0 if absent)."""
    out: dict[str, float] = {}
    for t in tickers:
        obs = get_latest_observable(conn, prefix + t)
        out[t] = float(obs["value"]) if obs and obs.get("value") is not None else 0.0
    return out


def _live_momentum(tickers: list[str]) -> dict[str, float]:
    """Per-ticker momentum percentile (reconstructable leak-free from prices)."""
    from backend.services.cross_sectional_momentum import compute_momentum_rankings
    rankings = compute_momentum_rankings(tickers, include_sector_relative=False)
    rows = rankings.get("rankings", rankings) if isinstance(rankings, dict) else rankings
    out: dict[str, float] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("ticker"):
            out[r["ticker"]] = float(r.get("percentile", r.get("composite_score", 0.0)))
    return out


def collect_multifactor_scores(db_path=None, tickers=None, *, as_of=None,
                               throttle_days=5, momentum_fn=None) -> dict:
    """Gather components (momentum live; insider/revisions from PIT), compute the
    composite cross-sectionally, and snapshot it forward. Throttled + leak-safe.
    ``momentum_fn`` injectable for tests."""
    tickers = tickers if tickers is not None else book_universe()
    aso = as_of or date.today().isoformat()
    momentum_fn = momentum_fn or _live_momentum

    conn = get_connection(db_path)
    try:
        last = conn.execute(
            "SELECT MAX(as_of) AS d FROM pit_observations WHERE key LIKE ?",
            (KEY_PREFIX + "%",),
        ).fetchone()
        if last and last["d"] and throttle_days > 0:
            from datetime import timedelta
            try:
                if date.fromisoformat(aso) - date.fromisoformat(last["d"]) < timedelta(days=throttle_days):
                    return {"status": "throttled", "last_as_of": last["d"], "n": 0}
            except ValueError:
                pass

        try:
            momentum = momentum_fn(tickers)
        except Exception as e:
            logger.warning("multifactor momentum fetch failed: %s", e)
            momentum = {}
        components = {
            "momentum": momentum,
            "insider": _read_pit_scores(conn, "insider_opp:", tickers),
            "revisions": _read_pit_scores(conn, "revisions_score:", tickers),
        }
        composite = compute_multifactor_scores(components)

        observed = datetime.now(timezone.utc).isoformat()
        written = 0
        for t in tickers:
            rid = snapshot(conn, KEY_PREFIX + t, aso, float(composite.get(t, 0.0)),
                           source="multifactor", observed_at=observed,
                           payload={f: round(components[f].get(t, 0.0), 4)
                                    for f in components})
            if rid is not None:
                written += 1
        logger.info("multifactor collect: %d tickers, %d written (as_of %s)",
                    len(tickers), written, aso)
        return {"status": "collected", "as_of": aso, "n": len(tickers),
                "written": written, "scores": composite}
    finally:
        conn.close()
