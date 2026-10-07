"""PROPOSAL, NOT WIRED (CHUNK C20, owner decision D13): the mirror cap hole.

`portfolio_intelligence.rules.enforce_position_limits` is a waterfill that, by
its own docstring, "converges when n * cap >= 1.0" and keeps its invariant
"output weights sum to 1.0". When HRP drops names and n * cap < 1 it cannot do
both, so it keeps the sum and breaks the cap: on 2026-06-16 and 2026-07-14 the
mirror lane rebalanced to DKNG 50% / SLDP 50% under a declared
`max_single_name: 0.25` (docs/research_notes/2026-10-06/book_dna_build_2026-10-06.md).

The proposal: when `n_names * max_single_name < 1`, clip every name at the cap
and hold the remainder in an explicit CASH line. When `n * cap >= 1` it defers
to the existing function unchanged, so today's 12-name mirror book (every name
priced since 2026-08-02) is untouched by it.

WHY THIS FILE IS NOT IMPORTED BY ANY LANE PATH. `enforce_position_limits` is
shared by the four reference lanes and `exit_lane`; changing it, or the mirror
path in front of it, is upstream of a lane's rebalance write -- the sacred
paper_nav path (CANON §5) -- and is `lane-integrity-check` work, attended, with
the owner's yes on D13. The lane engine must also be shown to carry a CASH
weight before this is wired (the reference engine's own cash handling, not
assumed here). Until then this module is called only by its tests and by
`scripts/fleet_v3_prepare.py`, which prints the worst case with and without it.
"""

from __future__ import annotations

from typing import Optional

CASH_KEY = "CASH"


def enforce_position_limits_with_cash(
    weights: dict[str, float],
    max_single_name: float,
    max_sector: float,
    sector_map: Optional[dict[str, str]] = None,
    *,
    cash_key: str = CASH_KEY,
) -> dict[str, float]:
    """`rules.enforce_position_limits`, except that a cap which cannot hold
    over the names it was given is honoured by holding cash, never broken.

    Invariant: output weights (names + `cash_key`) sum to the input sum, and no
    name exceeds `max_single_name` -- in BOTH regimes."""
    if not weights:
        return weights
    if cash_key in weights:
        raise ValueError(f"input already carries a {cash_key!r} line; pass names only")
    names = {t: max(0.0, float(w)) for t, w in weights.items()}
    total = sum(names.values())
    if total <= 0:
        return dict(weights)
    cap = float(max_single_name)
    if len(names) * cap >= 1.0 - 1e-12:
        from backend.services.portfolio_intelligence.rules import (  # noqa: PLC0415
            enforce_position_limits)
        return enforce_position_limits(dict(weights), max_single_name, max_sector, sector_map)
    # n * cap < 1: the waterfill cannot reach a fully-invested book under the
    # cap. The same waterfill, except that excess with nowhere to go is CASH.
    result = dict(names)
    frozen: set[str] = set()
    cash = 0.0
    for _ in range(len(result) + 1):
        excess = 0.0
        for t, w in result.items():
            if t not in frozen and w > cap + 1e-12:
                excess += w - cap
                result[t] = cap
                frozen.add(t)
        if excess <= 1e-12:
            break
        unfrozen = [t for t in result if t not in frozen]
        room = sum(cap - result[t] for t in unfrozen)
        if room <= 1e-12:
            cash += excess
            break
        base = sum(result[t] for t in unfrozen)
        for t in unfrozen:
            share = (result[t] / base) if base > 0 else 1.0 / len(unfrozen)
            result[t] += excess * share
    # the sector cap, the same way: an over-cap sector is scaled down to its
    # cap and the trimmed weight is cash (never pushed into another name).
    smap = sector_map or {}
    by_sector: dict[str, float] = {}
    for t, w in result.items():
        sec = smap.get(t)
        if sec:
            by_sector[sec] = by_sector.get(sec, 0.0) + w
    for sec, tot in by_sector.items():
        if tot > float(max_sector) + 1e-12:
            f = float(max_sector) / tot
            for t in result:
                if smap.get(t) == sec:
                    cash += result[t] * (1.0 - f)
                    result[t] *= f
    result[cash_key] = cash
    return result


def cap_hole(weights: dict[str, float], max_single_name: float) -> dict:
    """Describe whether `weights` sits in the hole (n x cap < 1)."""
    n = sum(1 for w in weights.values() if w and w > 0)
    return {"n_names": n, "cap": float(max_single_name),
            "n_x_cap": n * float(max_single_name),
            "in_hole": n * float(max_single_name) < 1.0 - 1e-12,
            "cash_if_fixed": max(0.0, 1.0 - n * float(max_single_name))}


def worst_case_rows(*, nav: float, weights_unfixed: dict[str, float],
                    weights_fixed: dict[str, float], sigmas: dict[str, float],
                    k: float = 3.0, label: str = "") -> list[dict]:
    """Session protocol item 4 for one book, before and after the fix.

    Per book: the largest single name (to zero, and -50%), the k-sigma day on
    the whole book (rho = 1), and sum|notional| / equity."""
    rows = []
    for tag, w in (("without fix", weights_unfixed), ("with fix", weights_fixed)):
        names = {t: v for t, v in w.items() if t != CASH_KEY and v > 0}
        top_t, top_w = max(names.items(), key=lambda kv: kv[1]) if names else (None, 0.0)
        ksig = sum(v * k * float(sigmas.get(t) or 0.0) for t, v in names.items()) * nav
        rows.append({"book": label, "case": tag, "largest_name": top_t,
                     "largest_weight": top_w,
                     "one_name_to_zero_usd": -top_w * nav,
                     "one_name_minus_50pct_usd": -0.5 * top_w * nav,
                     "k_sigma_day_usd": -ksig, "k_sigma": k,
                     "gross_over_equity": sum(names.values()),
                     "cash": float(w.get(CASH_KEY, 0.0))})
    return rows
