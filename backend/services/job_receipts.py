"""One receipt per scheduled-job run, including the runs that did nothing.

WHY THIS EXISTS, AND WHY IT IS THE LAST OBSERVABILITY WORK
==========================================================
Four states kept producing identical evidence — none:

    the job was skipped          the job never ran
    the job ran and failed       the job wrote to the wrong place

`options_pit` wrote inside the container image for weeks and every deploy
destroyed it; its health said `ABSENT` without naming a directory. `_hourly_mtm`
dropped four trading days out of `paper_nav` with two early returns logging at
`DEBUG` — below production level — and no record of the decision not to write.
In both cases the subsystem was emitting output that LOOKED like a measurement
and was actually an absence.

The codebase already had the principle, in `pi_ledger_resolve`'s own docstring —
*"`nothing_was_due` is a RESULT, written down, not an inference from silence"* —
and it had been applied to exactly one job. Then to a second, by hand, on
2026-08-25. Writing it a third time by hand is how a convention becomes six
slightly different conventions.

So: one wrapper, every scheduled job, one shape. **After this, no new
observability work without a concrete failure that pays for it.**

WHAT A RECEIPT CARRIES
======================
    job                the registered job id
    scheduled_for      when the trigger meant to fire (None if not supplied)
    started_at         when the body actually began
    finished_at        when it returned or raised
    duration_seconds
    status             ran | skipped | failed | raised
    skip_reason        WHY nothing happened — the field the NAV gap needed
    expected_data_date the date this run was supposed to produce
    writes             what it actually persisted
    exception          type and message, when it raised
    commit             the deploy that produced it

A SKIP IS A RESULT
==================
`status="skipped"` with a reason is a successful, informative run. The failure
mode this exists to kill is a job that returns early and leaves nothing behind,
because that is indistinguishable from a job that never fired at all.
"""
from __future__ import annotations

import contextvars
import functools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Keep the directory small enough to list quickly. Older receipts are pruned
#: per job, not globally — a chatty hourly job must not evict the daily one
#: whose absence is the thing being investigated.
MAX_RECEIPTS_PER_JOB = 200

#: The in-flight receipt, so a job body can annotate the run it is inside
#: without every function growing a parameter. A ContextVar rather than a
#: module global because jobs are async and the gate may interleave them.
_current: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "job_receipt_current", default=None)


def _root() -> Path:
    """Resolved at CALL time through config, never from `__file__`.

    `options_pit_store` rebuilt its path from `__file__`, which points inside
    the deployed image; Railway wipes that on every deploy and the store was
    silently ephemeral for weeks. Pinned by `test_ledger_dir_resolution.py`.
    """
    from backend import config as _config
    return Path(_config.OPTIMUS_LEDGER_DIR) / "job_receipts"


def _commit() -> str | None:
    """The deploy that produced this run.

    Read from the same env var `main._DEPLOY_COMMIT` uses, so a receipt and
    `/api/health/full` can never disagree about which build ran the job. That
    matters because the two defects this module exists for were both diagnosed
    by comparing a subsystem's state ACROSS a deploy.
    """
    import os
    return os.getenv("RAILWAY_GIT_COMMIT_SHA") or None


def note(*, skip_reason: str | None = None,
         expected_data_date: str | None = None,
         writes: Any = None, **extra) -> None:
    """Annotate the receipt for the run currently in flight.

    A no-op outside a `@receipted` job, so a job body can call it
    unconditionally and stay testable in isolation. Silence here is safe
    precisely because the wrapper writes a receipt either way — the annotation
    enriches a record that already exists.
    """
    r = _current.get()
    if r is None:
        return
    if skip_reason is not None:
        r["skip_reason"] = skip_reason
        r["status"] = "skipped"
    if expected_data_date is not None:
        r["expected_data_date"] = str(expected_data_date)
    if writes is not None:
        r["writes"] = writes
    if extra:
        r.setdefault("extra", {}).update(extra)


def _prune(d: Path) -> None:
    try:
        files = sorted(d.glob("*.json"))
        for f in files[:-MAX_RECEIPTS_PER_JOB]:
            f.unlink(missing_ok=True)
    except OSError:                                            # noqa: BLE001
        pass


def write(receipt: dict) -> Path | None:
    """Persist one receipt. NEVER raises — a receipt failure must not take
    down the work it describes."""
    try:
        d = _root() / str(receipt.get("job", "unknown"))
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S_%fZ")
        p = d / f"{stamp}.json"
        p.write_text(json.dumps(receipt, indent=2, default=str),
                     encoding="utf-8")
        _prune(d)
        return p
    except Exception as exc:                                   # noqa: BLE001
        logger.warning("job receipt not written for %s: %s",
                       receipt.get("job"), exc)
        return None


def receipted(job: str | None = None):
    """Wrap a scheduled job so every outcome leaves a dated record.

    Ordering matters: put this OUTSIDE `@_gated`, so the receipt covers the
    time spent waiting on the heavy-work gate. A job starved by the gate and a
    job that ran instantly are different findings, and the duration is the only
    thing that separates them.

    `functools.wraps` keeps the module-level qualname, which the persistent
    APScheduler jobstore needs to resolve the reference. A wrapper that lost it
    would make the job undeserialisable, and APScheduler REMOVES jobs it cannot
    restore — the NIGHT-13 defect, silently, at every rolling deploy.
    """
    def deco(fn):
        name = job or fn.__name__.lstrip("_")

        @functools.wraps(fn)
        async def run(*args, **kwargs):
            started = datetime.now(timezone.utc)
            r: dict = {
                "job": name,
                "scheduled_for": kwargs.pop("_scheduled_for", None),
                "started_at": started.isoformat(timespec="seconds"),
                "status": "ran",
                "skip_reason": None,
                "expected_data_date": None,
                "writes": None,
                "exception": None,
                "commit": _commit(),
            }
            token = _current.set(r)
            try:
                out = await fn(*args, **kwargs)
                # A body that returned without annotating and without writing
                # anything is the exact state that used to be invisible. It is
                # recorded as `ran` with nothing written, which is a claim a
                # reader can challenge — unlike silence.
                return out
            except Exception as exc:                           # noqa: BLE001
                r["status"] = "raised"
                r["exception"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                _current.reset(token)
                fin = datetime.now(timezone.utc)
                r["finished_at"] = fin.isoformat(timespec="seconds")
                r["duration_seconds"] = round(
                    (fin - started).total_seconds(), 3)
                write(r)
        return run
    return deco


def read(job: str, limit: int = 10) -> dict:
    """Most recent receipts for one job, newest first.

    Reports the directory it looked in even when empty. `options_pit` cost an
    hour of inference because `ABSENT` did not say *absent from where*.
    """
    d = _root() / job
    if not d.exists():
        return {"job": job, "dir": str(d), "exists": False, "n_receipts": 0,
                "note": "no receipt directory — no run has written one yet",
                "receipts": []}
    files = sorted(d.glob("*.json"), reverse=True)[:max(1, limit)]
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):                # noqa: PERF203
            continue
    return {"job": job, "dir": str(d), "exists": True,
            "n_receipts": len(list(d.glob("*.json"))), "receipts": out}


def known_jobs() -> list[str]:
    d = _root()
    if not d.exists():
        return []
    return sorted(p.name for p in d.iterdir() if p.is_dir())
