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

The logic itself lives ONCE in backend/services/nightly_receipt_contract.py, because the live
backend must not import this package (it reads the receipts directly); this wrapper only
supplies the lab's own receipt directory and age limit.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from backend.services.nightly_receipt_contract import GOOD, receipt_stamp as _stamp  # noqa: F401
from backend.services.nightly_receipt_contract import health_contract as _contract


def health_contract(receipt_dir: Path | None = None, now: datetime | None = None,
                    max_age_hours: float | None = None) -> dict:
    from nn_lab import config as C
    rd = Path(receipt_dir or C.RECEIPT_DIR)
    max_age = float(max_age_hours if max_age_hours is not None else C.HEALTH_MAX_AGE_HOURS)
    return _contract(rd, now=now, max_age_hours=max_age)
