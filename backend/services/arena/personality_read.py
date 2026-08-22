"""The four personalities read the arena — a GRADING READ, never a book.

OPTIMUS_OBJECTIVE §0.9: one brain, several utility functions — capital
preservation · balanced · aggressive · extreme growth. Those are DECLARED
PREFERENCES (config.ARENA_PERSONALITY_RHO, declared 2026-08-22 before any
arena NAV row existed) and are never tuned against history. This module
scores every book's realised NAV path under each declared utility and ranks
— because mission rule 3 says every ranked comparison names the objective it
was computed under, and until now the arena had no way to say "best FOR
WHOM".

What this is NOT: not a book, not a promotion authority, not a signal.
Nothing here writes into the arena; it reads nav.jsonl and reports. A book
that wins under extreme growth and loses under preservation is the system
working, not a contradiction to resolve.

Scoring: daily log returns r_t from the NAV path. Certainty-equivalent
annual growth under CRRA(rho): CE = 252*mean(r) − 0.5*rho*252*var(r).
Sortino, max drawdown, annualised return/vol are REPORTED, never deciding.
Books under ARENA_PERSONALITY_MIN_DAYS refuse with their n — a CE over a
week of NAV is a description of a week.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from backend import config
from backend.services.arena import spec as spec_mod
from backend.services.arena import store

logger = logging.getLogger(__name__)

BANNER = {
    "validation_status": "PRODUCT_EXPERIMENT",
    "simulation": True,
    "kind": "grading_read",
    "may_mutate_books": False,
    "promotion_authority": "none — quarterly generations promote, this ranks",
    "preferences": ("DECLARED (config.ARENA_PERSONALITY_RHO, 2026-08-22, "
                    "before any NAV row existed) — never tuned against "
                    "history"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _daily_log_returns(nav_rows: list[dict]) -> list[float]:
    """Sorted by date, one NAV per date (last write wins), log day-overs."""
    by_date: dict[str, float] = {}
    for r in nav_rows:
        try:
            by_date[str(r["date"])] = float(r["nav"])
        except (KeyError, TypeError, ValueError):
            continue
    navs = [v for _, v in sorted(by_date.items()) if v > 0]
    return [math.log(b / a) for a, b in zip(navs, navs[1:]) if a > 0]


def _path_stats(rets: list[float]) -> dict:
    n = len(rets)
    mean = sum(rets) / n
    var = (sum((x - mean) ** 2 for x in rets) / (n - 1)) if n > 1 else 0.0
    downside = [min(0.0, x) for x in rets]
    dvar = (sum(d * d for d in downside) / n) if n else 0.0
    # max drawdown on the cumulative log path
    peak = cum = 0.0
    max_dd = 0.0
    for x in rets:
        cum += x
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return {
        "n_days": n,
        "ann_log_growth": round(252.0 * mean, 4),
        "ann_vol": round((252.0 * var) ** 0.5, 4),
        "sortino": (round(mean * 252.0 / ((252.0 * dvar) ** 0.5), 2)
                    if dvar > 0 else None),
        "max_drawdown": round(1.0 - math.exp(-max_dd), 4),
        "_mean": mean, "_var": var,
    }


def certainty_equivalent(mean_daily: float, var_daily: float,
                         rho: float) -> float:
    """CE annual growth under CRRA(rho) on the daily log-return path."""
    return 252.0 * mean_daily - 0.5 * rho * 252.0 * var_daily


def report(root=None) -> dict:
    """Every book under every declared personality. Read-only."""
    min_days = config.ARENA_PERSONALITY_MIN_DAYS
    books: dict[str, dict] = {}
    for book_id in spec_mod.active_specs():
        rets = _daily_log_returns(store.read_nav(book_id, root))
        if len(rets) < min_days:
            books[book_id] = {"verdict": "REFUSED_THIN",
                              "n_days": len(rets), "min_days": min_days}
            continue
        books[book_id] = {"verdict": "SCORED", **{
            k: v for k, v in _path_stats(rets).items()
            if not k.startswith("_")}}
        stats = _path_stats(rets)
        books[book_id]["ce_by_personality"] = {
            p: round(certainty_equivalent(stats["_mean"], stats["_var"], rho),
                     4)
            for p, rho in config.ARENA_PERSONALITY_RHO.items()}

    personalities = {}
    scored = [b for b, v in books.items() if v["verdict"] == "SCORED"]

    def _objective(rho: float) -> str:
        # ANNOTATION (2026-08-22 adjudication) — the declared rhos are FROZEN;
        # this names what rho=1 mathematically IS. "Extreme growth" at rho=1
        # is log utility, the Kelly growth-optimal objective — a raw
        # expected-terminal-wealth personality (rho→0, ruin-constrained)
        # would be a NEW declaration, forward-only, never a rename.
        base = f"CE annual log growth under CRRA(rho={rho})"
        if rho == 1.0:
            return base + " [= log utility, the Kelly growth-optimal objective]"
        return base

    for p, rho in config.ARENA_PERSONALITY_RHO.items():
        if not scored:
            personalities[p] = {
                "verdict": "ABSTAIN", "rho": rho,
                "objective": _objective(rho),
                "reason": (f"no book has {min_days}+ NAV days yet — a "
                           f"ranking would be noise wearing a podium")}
            continue
        ranking = sorted(
            scored, key=lambda b: books[b]["ce_by_personality"][p],
            reverse=True)
        personalities[p] = {
            "verdict": "RANKED", "rho": rho,
            "objective": _objective(rho),
            "ranking": [{"book_id": b,
                         "ce": books[b]["ce_by_personality"][p]}
                        for b in ranking]}

    return {**BANNER, "computed_at": _now(),
            "min_days": min_days,
            "n_books": len(books), "n_scored": len(scored),
            "personalities": personalities, "books": books}
