"""One-shot repair for a slept-through ARENA paper decision.

This is deliberately paper-only and idempotent.  It exists for attended
recovery when the in-process scheduler missed a session because the Railway
web process slept.  It never accepts live-broker credentials or a live Alpaca
host; alpaca_mirror.py independently refuses any non-paper base URL.

Usage (production startup, temporary):
    python scripts/arena_paper_repair_once.py

A successful decision+submission writes a dated marker under AEGIS_DATA_DIR so
process restarts cannot replay the repair.  Remove the temporary startup hook
after the receipt is visible in Railway logs.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path


async def main() -> int:
    session = datetime.now(timezone.utc).date().isoformat()
    data_dir = Path(os.getenv("AEGIS_DATA_DIR", "/data"))
    marker = data_dir / f"arena_paper_repair_{session}.done"
    if marker.exists():
        print(f"ARENA PAPER REPAIR skip: marker exists {marker}", flush=True)
        return 0

    # Require the arena-specific target before doing any research/decision work.
    from backend.services.portfolio_intelligence import paper_broker_targets as pbt
    target = pbt.parse_arena_target()
    if target is None:
        print("ARENA PAPER REPAIR refused: AEGIS_ARENA_BROKER_TARGET unset/invalid", flush=True)
        return 2

    from backend.services.portfolio_intelligence.alpaca_mirror import alpaca_available
    if not alpaca_available(target):
        print("ARENA PAPER REPAIR refused: arena paper credentials unavailable", flush=True)
        return 3

    from backend.services.portfolio_intelligence.scheduler import (
        _arena_daily_pass,
        _submit_arena_broker_intent,
    )

    decided = await _arena_daily_pass()
    if not decided:
        print("ARENA PAPER REPAIR refused: fresh decision pass failed", flush=True)
        return 4

    # The scheduler bridge is the canonical execution path. It reconciles the
    # prior decision first, then submits only the freshly generated intent.
    await _submit_arena_broker_intent()

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps({
            "session_utc": session,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "target_id": target.target_id,
            "purpose": "attended slept-through ARENA paper repair",
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"ARENA PAPER REPAIR completed target={target.target_id} marker={marker}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
