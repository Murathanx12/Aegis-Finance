"""The one copy of the nightly-receipt health contract (review C5 F8, moved 2026-10-07).

Shared by the backend's task-receipt judge (`task_receipts.r_nn_lab`) and the research
lab's own wrapper (`nn_lab/health.py`). It lives here, pure stdlib, because the live
backend path must never import the lab package: the lab has its own interpreter and
requirements, and its suite pins that invariant. The lab imports this module; the
backend never imports the lab.

    newest receipts/nightly_*.json with status in {OK, DEGRADED} and a written_utc under
    max_age_hours old -> ALIVE. Any other status -> REFUSED (with the reason and the count
    of consecutive non-OK receipts). Too old -> STALE. No receipt at all, or one with no
    readable timestamp -> UNKNOWN, never ALIVE.

The age comes from the receipt's own `written_utc` (or `started_utc`), never the file's
mtime (CLAUDE.md protocol item 7).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

GOOD = ("OK", "DEGRADED")
DEFAULT_MAX_AGE_HOURS = 26.0
DEFAULT_NAME = "nn_lab_nightly"


def receipt_stamp(r: dict) -> datetime | None:
    for k in ("written_utc", "started_utc"):
        v = r.get(k)
        if v:
            try:
                d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def health_contract(receipt_dir: Path, now: datetime | None = None,
                    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
                    name: str = DEFAULT_NAME, pattern: str = "nightly_*.json") -> dict:
    rd = Path(receipt_dir)
    max_age = float(max_age_hours)
    now = now or datetime.now(timezone.utc)
    recs = []
    for f in sorted(rd.glob(pattern)):                     # run ids sort by time
        try:
            recs.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
        except Exception:                                   # noqa: BLE001
            recs.append((f.name, {"status": "UNREADABLE"}))
    base = {"name": name, "max_age_hours": max_age}
    if not recs:
        return {**base, "status": "UNKNOWN", "line": f"{name} UNKNOWN: no nightly receipt on disk"}
    fname, r = recs[-1]
    if not isinstance(r, dict):
        r = {"status": "UNREADABLE"}
    st = str(r.get("status") or "MISSING_STATUS")
    n_bad = 0
    for _, x in reversed(recs):
        if isinstance(x, dict) and str(x.get("status")) in GOOD:
            break
        n_bad += 1
    ts = receipt_stamp(r)
    age_h = round((now - ts).total_seconds() / 3600, 1) if ts else None
    out = {**base, "receipt": fname, "receipt_status": st, "age_hours": age_h, "consecutive_non_ok": n_bad}
    if st not in GOOD:
        why = r.get("refused") or r.get("error") or r.get("stopped_before") or st
        return {**out, "status": "REFUSED", "reason": str(why)[:300],
                "line": f"{name} REFUSED: {st} ({str(why)[:160]}); {n_bad} consecutive non-OK receipts"}
    if age_h is None:
        return {**out, "status": "UNKNOWN", "line": f"{name} UNKNOWN: {fname} carries no readable timestamp"}
    if age_h >= max_age:
        return {**out, "status": "STALE",
                "line": f"{name} STALE: newest receipt {fname} is {age_h} h old (>= {max_age:g} h)"}
    return {**out, "status": "ALIVE",
            "line": f"{name} ALIVE: {st} {age_h} h ago ({fname})"}
