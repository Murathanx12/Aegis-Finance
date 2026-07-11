"""
Shared idempotent trial registration — ONE implementation of the registry
INSERT whose cumulative count the DSR/PBO adoption gate deflates against.

Why: ensure_lppls_trial / ensure_crash_trial / ensure_congress_trial /
ensure_ark_trial each carried a verbatim copy of the existing-row check +
count_cumulative_trials()+1 + 10-column INSERT. The counting semantics are
gate-critical; they must live in one place. (The two fragility ensures predate
this helper and migrate opportunistically.)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def ensure_trial_registered(param: str, notes: dict, db_path=None,
                            config_version: str = "descriptive",
                            lane_id: str | None = None) -> int:
    """Idempotently insert a pre-registered trial row. Returns the row id
    (existing or new). Registering enters the cumulative trial count — the
    conservative direction (stricter DSR/PBO)."""
    from backend.db import count_cumulative_trials, get_connection, init_db

    init_db(db_path)
    conn = get_connection(db_path)
    try:
        existing = conn.execute(
            "SELECT id FROM rule_experiments WHERE param = ? ORDER BY id LIMIT 1",
            (param,),
        ).fetchone()
        if existing is not None:
            return int(existing["id"])
        cumulative = count_cumulative_trials(conn) + 1
        cur = conn.execute(
            "INSERT INTO rule_experiments "
            "(created_at, config_version, lane_id, param, old_value, new_value, "
            " batch_trials, cumulative_trials, verdict, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(), config_version, lane_id, param,
             None, "registered", 1, cumulative, "adopted", json.dumps(notes)),
        )
        conn.commit()
        logger.info("Pre-registered trial %s (cumulative trials now %d)",
                    param, cumulative)
        return int(cur.lastrowid)
    finally:
        conn.close()
