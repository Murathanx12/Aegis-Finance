"""
NAV history reconstruction for the 2026-07-26 re-book defect (ATTENDED,
env-gated, one-boot, idempotent).

THE DEFECT: until commit 36c8ece, `_get_portfolio_notional` returned the
static inception_value, so every non-initialization rebalance re-booked the
lane at $100k − costs. NAV teleported toward inception at every boundary and
compounding was severed (aggressive lost its +2.0% at the 2026-07-08 weekly
reset on a +0.85% SPY day; conviction was re-based at every logged decision).

WHY RECONSTRUCTION IS SOUND: the daily NAV marks BETWEEN boundaries are
honest (shares × real prices). A re-book preserved target weights and only
mis-scaled the notional, so the true chain differs from the booked chain by a
per-boundary multiplicative factor:

    k_E = (last honest NAV mark before the reset materialized) / 100000

Costs cancel to first order (they were charged on |Δw|×100k booked vs
|Δw|×NAV_true — the residual is bps-of-bps, disclosed). The corrected series
is: corrected NAV_t = booked NAV_t × Π k_E over boundaries materialized ≤ t.

BOUNDARY MATERIALIZATION: for the 16:30 daily-check reblances the same-day
NAV row was written pre-book (observed live: balanced 2026-07-08 = 100,807,
continuous), so the reset materializes at the NEXT row (k from the event
day's row). For boot-time config_change events the same-day row is already
post-book (~100k − cost); the reset materializes AT that row (k from the
prior row). Detection rule (disclosed approximation, error bounded by the
band): a same-day row within 0.5% of $100,000 is treated as post-book.

WRITES (single attended run):
  1. archive: paper_nav_archive_20260726 = byte copy of paper_nav
  2. paper_nav.nav ×= F(lane, date)
  3. OPEN paper_positions shares ×= F(lane, now) — so future MTM continues
     the corrected chain seamlessly
  4. audit rows per lane (boundaries, factors, final scale) + a global
     marker row that makes the whole operation idempotent

Never runs unattended: main.py invokes it only under
AEGIS_RECONSTRUCT_NAV=1 (Murat's flag, one boot, then unset).
"""

from __future__ import annotations

import logging
from datetime import datetime

from backend.db import get_connection, init_db, insert_audit_log

logger = logging.getLogger(__name__)

MARKER_EVENT = "nav_reconstruction_20260726"
ARCHIVE_TABLE = "paper_nav_archive_20260726"
INCEPTION_BOOK = 100_000.0
POST_BOOK_BAND = 0.005  # |row/100k − 1| < 0.5% ⇒ same-day row is post-book
# Events at/after this instant ran the FIXED code (commit 36c8ece deployed
# 2026-07-26 ~13:30 UTC) and book correctly — they are NOT boundaries.
FIX_CUTOFF = "2026-07-26T13:30:00"


def _lane_boundaries(conn, lane_id: str) -> list[dict]:
    """Corrupted-era re-book boundaries: every non-initialization rebalance
    event before the fix cutoff. Returns [{date, materializes_at, k}] using
    ONLY the booked NAV series (so factors are order-independent)."""
    events = conn.execute(
        "SELECT triggered_at FROM rebalance_events "
        "WHERE portfolio_id = ? AND trigger_reason != 'initialization' "
        "AND triggered_at < ? ORDER BY triggered_at",
        (lane_id, FIX_CUTOFF),
    ).fetchall()
    nav_rows = conn.execute(
        "SELECT date, nav FROM paper_nav WHERE portfolio_id = ? ORDER BY date",
        (lane_id,),
    ).fetchall()
    if not nav_rows:
        return []
    dates = [r["date"] for r in nav_rows]
    navs = {r["date"]: r["nav"] for r in nav_rows}

    boundaries: list[dict] = []
    seen_dates: set[str] = set()
    for ev in events:
        d = ev["triggered_at"][:10]
        if d in seen_dates:
            # A second same-day re-book starts from an already-reset (~100k)
            # book — no additional discontinuity (k ≈ 1). Skip.
            continue
        seen_dates.add(d)

        same_day = navs.get(d)
        prior = [x for x in dates if x < d]
        if same_day is not None and abs(same_day / INCEPTION_BOOK - 1) >= POST_BOOK_BAND:
            # Case A: same-day row is the honest pre-book mark; the reset
            # shows up in the NEXT row.
            k = same_day / INCEPTION_BOOK
            later = [x for x in dates if x > d]
            materializes_at = later[0] if later else None
        elif prior:
            # Case B (or ambiguous-within-band): same-day row is post-book
            # (or the event day has no row at all); the last honest mark is
            # the prior row, and the reset materializes at the first row at
            # or after the event date.
            k = navs[prior[-1]] / INCEPTION_BOOK
            at_or_after = [x for x in dates if x >= d]
            materializes_at = at_or_after[0] if at_or_after else None
        else:
            # Boundary before any NAV row (event on inception day) — the
            # chain never saw a pre-boundary mark; nothing to correct.
            continue
        if materializes_at is None:
            continue  # reset never materialized in a NAV row (nothing after)
        boundaries.append({"event_date": d, "materializes_at": materializes_at,
                           "k": k})
    return boundaries


def plan_reconstruction(conn) -> dict:
    """Pure read: per-lane boundaries, factors and final scale. The loggable,
    reviewable plan — computed identically in dry-run and live."""
    lanes = [r["id"] for r in conn.execute(
        "SELECT id FROM paper_portfolios ORDER BY id").fetchall()]
    plan: dict = {}
    for lane_id in lanes:
        bounds = _lane_boundaries(conn, lane_id)
        f = 1.0
        for b in bounds:
            f *= b["k"]
        plan[lane_id] = {"boundaries": bounds,
                         "final_scale": f,
                         "n_boundaries": len(bounds)}
    return plan


def _factor_at(bounds: list[dict], nav_date: str) -> float:
    f = 1.0
    for b in bounds:
        if nav_date >= b["materializes_at"]:
            f *= b["k"]
    return f


def reconstruct_nav_history(db_path=None, dry_run: bool = False) -> dict:
    """Execute (or plan) the reconstruction. Idempotent via the audit marker.

    Returns {status, plan} — status 'already_ran' | 'dry_run' | 'reconstructed'.
    """
    init_db(db_path)
    conn = get_connection(db_path)
    try:
        marker = conn.execute(
            "SELECT 1 FROM audit_log WHERE event_type = ? LIMIT 1",
            (MARKER_EVENT,),
        ).fetchone()
        if marker:
            logger.info("NAV reconstruction already ran — skipping (idempotent)")
            return {"status": "already_ran"}

        plan = plan_reconstruction(conn)
        loud = {k: {"n_boundaries": v["n_boundaries"],
                    "final_scale": round(v["final_scale"], 6)}
                for k, v in plan.items()}
        logger.warning("NAV RECONSTRUCTION PLAN: %s", loud)
        if dry_run:
            return {"status": "dry_run", "plan": plan}

        from backend.db import _write_lock
        ts = datetime.now().isoformat()
        with _write_lock:
            # 1. archive the original rows, byte-for-byte, exactly once
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {ARCHIVE_TABLE} AS "
                "SELECT * FROM paper_nav",
            )
            # 2. correct the NAV chain
            for lane_id, p in plan.items():
                if not p["boundaries"]:
                    continue
                rows = conn.execute(
                    "SELECT date, nav FROM paper_nav WHERE portfolio_id = ?",
                    (lane_id,),
                ).fetchall()
                for r in rows:
                    f = _factor_at(p["boundaries"], r["date"])
                    if f != 1.0:
                        conn.execute(
                            "UPDATE paper_nav SET nav = ? "
                            "WHERE portfolio_id = ? AND date = ?",
                            (r["nav"] * f, lane_id, r["date"]),
                        )
                # 3. rescale the OPEN book so future MTM continues the
                #    corrected chain
                final = p["final_scale"]
                if final != 1.0:
                    conn.execute(
                        "UPDATE paper_positions SET shares = shares * ? "
                        "WHERE portfolio_id = ? AND closed_at IS NULL",
                        (final, lane_id),
                    )
            conn.commit()

        # 4. audit trail (outside the write lock — insert_audit_log locks)
        for lane_id, p in plan.items():
            insert_audit_log(conn, ts, lane_id, "nav_reconstruction_lane", {
                "n_boundaries": p["n_boundaries"],
                "final_scale": p["final_scale"],
                "boundaries": p["boundaries"],
            })
        insert_audit_log(conn, ts, None, MARKER_EVENT, {
            "archive_table": ARCHIVE_TABLE,
            "fix_cutoff": FIX_CUTOFF,
            "lanes": {k: round(v["final_scale"], 6) for k, v in plan.items()},
        })
        logger.warning("NAV RECONSTRUCTION DONE: %s", loud)
        return {"status": "reconstructed", "plan": plan}
    finally:
        conn.close()
