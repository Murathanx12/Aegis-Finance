"""The nn_lab nightly's one-line health contract (review C5 F8, 2026-10-07).

Six non-OK receipts in a row (2026-10-02 -> 10-06) turned nothing red, because the scheduled
task's Last Result is cmd's rc and nothing read the receipt. This is the reader:

    nn_lab_nightly: the newest receipts/nightly_*.json must have status in {OK, DEGRADED} and a
    written_utc under HEALTH_MAX_AGE_HOURS old -> ALIVE. Otherwise REFUSED (its status is
    anything else: REFUSED / FAILED / TIMEOUT / STALE_BARS, with the reason and the count of
    consecutive non-OK receipts) or STALE (the newest receipt is too old). No receipt at all,
    or one with no readable timestamp, is UNKNOWN -- never ALIVE.

The age comes from the receipt's own `written_utc` (or `started_utc`), never the file's
mtime (CLAUDE.md protocol item 7). Pure stdlib: the probe can import it cheaply.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

GOOD = ("OK", "DEGRADED")


def _stamp(r: dict) -> datetime | None:
    for k in ("written_utc", "started_utc"):
        v = r.get(k)
        if v:
            try:
                d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def health_contract(receipt_dir: Path | None = None, now: datetime | None = None,
                    max_age_hours: float | None = None) -> dict:
    from nn_lab import config as C
    rd = Path(receipt_dir or C.RECEIPT_DIR)
    max_age = float(max_age_hours if max_age_hours is not None else C.HEALTH_MAX_AGE_HOURS)
    now = now or datetime.now(timezone.utc)
    recs = []
    for f in sorted(rd.glob("nightly_*.json")):          # run ids sort by time
        try:
            recs.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
        except Exception:                                   # noqa: BLE001
            recs.append((f.name, {"status": "UNREADABLE"}))
    base = {"name": "nn_lab_nightly", "max_age_hours": max_age}
    if not recs:
        return {**base, "status": "UNKNOWN", "line": "nn_lab_nightly UNKNOWN: no nightly receipt on disk"}
    name, r = recs[-1]
    st = str(r.get("status") or "MISSING_STATUS")
    n_bad = 0
    for _, x in reversed(recs):
        if str(x.get("status")) in GOOD:
            break
        n_bad += 1
    ts = _stamp(r)
    age_h = round((now - ts).total_seconds() / 3600, 1) if ts else None
    out = {**base, "receipt": name, "receipt_status": st, "age_hours": age_h, "consecutive_non_ok": n_bad}
    if st not in GOOD:
        why = r.get("refused") or r.get("error") or r.get("stopped_before") or st
        return {**out, "status": "REFUSED", "reason": str(why)[:300],
                "line": f"nn_lab_nightly REFUSED: {st} ({str(why)[:160]}); {n_bad} consecutive non-OK receipts"}
    if age_h is None:
        return {**out, "status": "UNKNOWN", "line": f"nn_lab_nightly UNKNOWN: {name} carries no readable timestamp"}
    if age_h >= max_age:
        return {**out, "status": "STALE",
                "line": f"nn_lab_nightly STALE: newest receipt {name} is {age_h} h old (>= {max_age:g} h)"}
    return {**out, "status": "ALIVE",
            "line": f"nn_lab_nightly ALIVE: {st} {age_h} h ago ({name})"}
