"""
Optimus Prediction-Ledger Router
================================

GET /api/optimus/calibration — specialist × observable × horizon cross-tab
    (honest counts: sparse cells print n and None; pending never scored)
GET /api/optimus/job_receipts — dated receipts left by the scheduled jobs, so
    "it ran and had nothing to do" is distinguishable from "it never fired"
GET /api/optimus/digest — the day's assembled digest (what happened vs what
    we thought), latest by default or ?day=YYYY-MM-DD
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/optimus", tags=["optimus"])
logger = logging.getLogger(__name__)


@router.get("/calibration")
async def get_calibration():
    """Calibration report for the prediction ledger, with ledger health attached."""
    try:
        from backend.services.ledger_calibration import calibration_report
        return await asyncio.to_thread(calibration_report)
    except Exception as e:
        logger.error("ledger calibration report failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job_receipts")
async def get_job_receipts(limit: int = 10):
    """Dated receipts left by the scheduled jobs, newest first.

    WHY THIS ENDPOINT EXISTS
    ========================
    `pi_ledger_resolve` and `pi_ownership_collect` each write a dated receipt to
    the persistent volume so that a run leaves evidence independent of logs. On
    2026-08-15 that turned out to be only half a fix: the receipts were being
    written where nothing could read them. The 16:30 ET resolver run left the
    ledger unchanged — which is the EXPECTED result when nothing is due, and
    therefore indistinguishable from a job that never fired — and by the time
    anyone looked, the container had restarted and the log lines were gone.

    A receipt nobody can read is barely better than the log line it replaced.
    That is the same failure shape one level up, so the read path is part of
    the fix rather than a convenience.

    Read-only, and cheap: it reads filenames and small JSON blobs, never the
    prediction ledger.
    """
    from backend import config as _config

    def _read(kind: str, d):
        if not d.exists():
            return {"kind": kind, "dir": str(d), "exists": False,
                    "n_receipts": 0,
                    # An absent DIRECTORY and an empty one are different facts:
                    # the first means no run has ever written here.
                    "note": "no receipt directory — no run has written one yet",
                    "receipts": []}
        files = sorted(d.glob("*.json"), key=lambda p: p.name, reverse=True)
        out = []
        for f in files[:max(1, min(int(limit), 50))]:
            try:
                out.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception as exc:                           # noqa: BLE001
                out.append({"file": f.name, "unreadable": True,
                            "error": f"{type(exc).__name__}: {exc}"})
        return {"kind": kind, "dir": str(d), "exists": True,
                "n_receipts": len(files), "receipts": out}

    base = _config.OPTIMUS_LEDGER_DIR
    return {
        "pi_ledger_resolve": _read("pi_ledger_resolve",
                                   base / "resolver_receipts"),
        "pi_ownership_collect": _read("pi_ownership_collect",
                                      base / "teacher_library"
                                      / "collection_receipts"),
        # Added 2026-08-25. paper_nav had four missing trading days and no way
        # to tell a skipped mark from a failed one, because both of
        # `_hourly_mtm`'s early returns logged at DEBUG and wrote nothing.
        "pi_hourly_mtm": _read("pi_hourly_mtm", base / "mtm_receipts"),
        "note": ("A run that had nothing to do still writes a receipt. An "
                 "unchanged ledger is the expected result of a healthy quiet "
                 "run and cannot, by itself, distinguish that from a job that "
                 "never fired — the receipt is what does."),
    }


@router.get("/digest")
async def get_digest(day: str | None = None):
    """The daily digest: one dated record of what the system decided, graded,
    collected, and marked, assembled from durable state by `pi_daily_digest`.

    Documentation only — nothing in any scoring or decision path reads this.
    404 when no digest exists yet (a fact, not an error to hide)."""
    from backend.services.daily_digest import latest_digest, read_digest

    try:
        if day is not None:
            body = await asyncio.to_thread(read_digest, day)
        else:
            body = await asyncio.to_thread(latest_digest)
    except Exception as e:
        logger.error("digest read failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    if body is None:
        raise HTTPException(
            status_code=404,
            detail=(f"no digest for {day}" if day else
                    "no digests written yet — pi_daily_digest runs 18:15 ET"))
    return body
