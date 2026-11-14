"""Every scheduled task judged by the RECEIPT it must advance (chunk C8, 2026-10-07).

WHY
===
Until 2026-10-06 the `task:*` health rows read `schtasks`' "Last Result", which is
the exit code of `cmd.exe` or `pythonw.exe`, not of the job. Seventeen rows said
UNKNOWN every night, and behind them the nn_lab nightly wrote six non-OK receipts
in a row (2026-10-02 -> 10-06) without anything turning red. A task the scheduler
fires is not a task that produces, so each task is judged ONLY by what it wrote.

REVIEW 2026-10-07 (docs/reviews/REVIEW_2026-10-07_C8_PROGRESS_AWARE_HEALTH.md)
-----------------------------------------------------------------------------
The first version replaced "UNKNOWN by omission" with "ALIVE by omission" in five
readers: replayed on the BRK-B blackout (09-30 -> 10-02) the daily pass read
ALIVE_PROGRESSING three days running with `bars_refresh: refused`. Fixed by ONE
rule enforced in ONE place: every reader passes the producer's own status fields
through `map_status` / `receipt_status`, and `judge` never returns an ALIVE_*
state for a reading whose status is REFUSED / DEGRADED / STOPPED / DEAD.

States
------
* ``ALIVE_PROGRESSING``   -- a fresh receipt, status OK, substance moved
* ``ALIVE_IDLE_EXPECTED`` -- fresh enough inside a DECLARED idle window (no XNYS
                             session, outside the producer's own time window, not
                             yet due, or the producer wrote `identical_ok`)
* ``DEGRADED``            -- fresh, but the receipt says something failed
* ``STALE``               -- older than its declared cadence, or the same
                             substance for too long ("same output for X h")
* ``REFUSED``             -- the newest receipt is a fresh refusal, with its reason
* ``DEAD``                -- nothing scheduled and nothing fresh, or every account
                             in the pass failed
* ``UNREGISTERED``        -- declared, deliberately not yet registered (a review is
                             pending); not a failure and not alive
* ``UNKNOWN``             -- the receipt cannot be read on this machine, and why

The coarse `verdict` beside each state (ALIVE / STALE / REFUSED / DEAD / UNKNOWN /
STOPPED_BY_OPERATOR) is what existing consumers compare against.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from backend import config as _config

#: fine state -> coarse verdict
COARSE = {"ALIVE_PROGRESSING": "ALIVE", "ALIVE_IDLE_EXPECTED": "ALIVE",
          "DEGRADED": "STALE", "STALE": "STALE", "REFUSED": "REFUSED", "DEAD": "DEAD",
          "UNKNOWN": "UNKNOWN", "STOPPED_BY_OPERATOR": "STOPPED_BY_OPERATOR",
          "UNREGISTERED": "STOPPED_BY_OPERATOR"}
STATES = tuple(COARSE)
ALIVE_STATES = ("ALIVE_PROGRESSING", "ALIVE_IDLE_EXPECTED")

#: schtasks' "Last Result" for a task that has never run (SCHED_S_TASK_HAS_NOT_RUN)
NEVER_RAN_RC = "267011"

#: `task_keeper/disabled/<task name>`: a file the OWNER writes when disabling a
#: task on purpose (its text is the reason). Disabled without it is not proof
#: that a person did it (review F7).
DISABLED_MARKER_DIR = ("task_keeper", "disabled")


# ═══════════════════════════════════════════════════════ the ONE status mapping

#: severity order; the reading's status is the WORST of every field it read
_SEVERITY = {"OK": 0, "IDLE": 1, "DEGRADED": 2, "STOPPED": 3, "REFUSED": 4, "DEAD": 5}


def map_status(value: Any) -> str:
    """Any producer status / state / action string -> OK / IDLE / DEGRADED /
    STOPPED / REFUSED / DEAD. Every reader goes through this; an UNRECOGNISED
    non-empty value is DEGRADED, never OK (a new failure word must not read green)."""
    if value is None or value is True:
        return "OK"
    if value is False:
        return "DEGRADED"
    s = str(value).strip().upper().replace("-", "_").replace(" ", "_")
    if s in ("", "NONE", "OK", "ALIVE", "SUCCESS", "DONE", "COMPLETE", "COMPLETED", "PASS",
             "FINISHED", "STARTED", "WOULD_START", "RUNNING", "LAUNCH", "LAUNCHED",
             "NOTHING_TO_DO", "OBSERVE_ONLY"):
        return "OK"
    if s.startswith("OBSERVE_ONLY") or s.startswith("OK"):
        return "OK"
    if s.startswith("REFUS") or s.startswith("BLOCKED") or s.startswith("BUDGET_REFUS"):
        return "REFUSED"
    if s.startswith("STOP") or s.startswith("PAUSED"):
        return "STOPPED"
    if s.startswith("DEAD"):
        return "DEAD"
    if s.startswith(("IDLE", "OUTSIDE_WINDOW", "SKIP", "NOT_DUE", "WAIT")):
        return "IDLE"
    if s.startswith(("ERROR", "FAIL", "TIMEOUT", "TIMED_OUT", "EXCEPTION", "CRASH", "HTTP_",
                     "DEGRADED", "STALE", "RED", "WARN", "PARTIAL", "CANNOT_DETERMINE",
                     "LAUNCH_FAILED", "START_FAILED", "UNREADABLE", "MISSING")):
        return "DEGRADED"
    return "DEGRADED"


def worst(*statuses: str) -> str:
    return max((s for s in statuses if s), key=lambda s: _SEVERITY.get(s, 2), default="OK")


def receipt_status(d: Any, *, fields: Iterable[str] = ("status", "state", "result", "action"),
                   error_fields: Iterable[str] = ("error", "errors", "sections_error",
                                                  "refused", "refusal", "why_exited"),
                   ) -> tuple[str, str]:
    """(status, reason) from a receipt dict's own top-level fields: the worst of
    every status-like field, and any non-empty error-like field."""
    if not isinstance(d, dict):
        return "DEGRADED", "receipt is not a JSON object"
    st, why = "OK", []
    for k in fields:
        if k in d and d[k] is not None and not isinstance(d[k], (dict, list)):
            m = map_status(d[k])
            if _SEVERITY[m] > _SEVERITY["OK"]:
                why.append(f"{k}={str(d[k])[:120]}")
            st = worst(st, m)
    for k in error_fields:
        v = d.get(k)
        if v:
            st = worst(st, "REFUSED" if k.startswith("refus") or k == "why_exited" else "DEGRADED")
            why.append(f"{k}={str(v)[:160]}")
    return st, "; ".join(why)


# ═══════════════════════════════════════════════════════════════ reading

@dataclass
class Reading:
    stamp: Optional[datetime] = None
    status: str = "OK"               # OK / IDLE / DEGRADED / STOPPED / REFUSED / DEAD
    reason: str = ""
    substance: Optional[str] = None  # None = the hash rule is off (see `hash_off`)
    proof: str = ""
    detail: str = ""
    idle_reason: Optional[str] = None
    unknown_reason: Optional[str] = None
    delegated: Optional[str] = None  # a coarse verdict another probe already judged
    never_by_task: bool = False      # a receipt exists but this task has never run
    run_start: Optional[datetime] = None  # producer start, for window/tick provenance


@dataclass(frozen=True)
class TaskSpec:
    reader: Callable[[Any, Optional[dict]], Reading]
    receipt: str                     # where the receipt lives, for the row and the docs
    session_only: bool = False       # produces only for XNYS sessions
    hash_off: str = ""               # why the same-substance rule does not apply
    retired: bool = False
    #: judged only when the scheduler holds the task (a command the repo PRINTS for
    #: the owner, or a job a Startup script owns instead)
    registered_only: bool = False
    #: declared, deliberately NOT registered yet: the reason (a pending review)
    unregistered_ok: str = ""
    #: a daily ET window the producer only writes inside: (config start, config end)
    window_cfg: Optional[tuple[str, str]] = None
    #: fixed UTC repeat window; unlike an ET window this matches a fixed SGT trigger
    window_utc: Optional[tuple[str, str]] = None
    #: A separately owned private task may declare cadence without repinning config.
    cadence_h: Optional[float] = None


def parse_stamp(v: Any) -> Optional[datetime]:
    """ISO, a date, or the compact `20261006T163002Z` the receipts use."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?", s)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc)
    try:
        if len(s) == 10:
            d = date.fromisoformat(s)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ═══════════════════════════════════════════════ the substance (review F6)

#: exact key names that are clocks or ids (never a substring match: `outcome`,
#: `rows_written`, `coverage_rate`, `n_blocks` are PROGRESS, not clocks)
VOLATILE_KEYS = frozenset({
    "t", "ts", "at", "utc", "stamp", "run_id", "id", "pid", "now", "now_et", "now_utc",
    "elapsed_s", "elapsed_min", "wall_min", "runtime_s", "seconds", "receipt", "receipt_path",
    "path", "log", "trace", "git_head", "free_ram_gb_start", "free_gb"})
_VOLATILE_SUFFIX = re.compile(r"^(.*_)?(utc|ts|stamp|run_id|pid|at)$")
_ISO_DT = re.compile(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}:?\d{2}|Z)?)?")
_COMPACT = re.compile(r"\d{8}T\d{6}Z?")
_HEXID = re.compile(r"\b[0-9a-f]{12,64}\b")


def _norm_value(v: Any) -> Any:
    if isinstance(v, str):
        v = _COMPACT.sub("<stamp>", v)
        v = _ISO_DT.sub("<date>", v)
        return _HEXID.sub("<id>", v)
    return v


def substance(obj: Any, *, drop: Iterable[str] = ()) -> str:
    """The receipt with its clocks and ids removed (exact key names + an anchored
    suffix rule) and ISO dates / compact stamps / hex ids inside VALUES normalised,
    as canonical JSON. A series whose content is frozen hashes identical even when
    its file name and day move."""
    dropset = VOLATILE_KEYS | set(drop)

    def strip(o):
        if isinstance(o, dict):
            return {_norm_value(k): strip(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))
                    if str(k) not in dropset and not _VOLATILE_SUFFIX.match(str(k))}
        if isinstance(o, list):
            return [strip(x) for x in o]
        return _norm_value(o)
    return json.dumps(strip(obj), sort_keys=True, default=str)


def pick(d: Any, paths: Iterable[str]) -> dict:
    """The declared progress fields (dotted paths) of a receipt."""
    out = {}
    for p in paths:
        cur: Any = d
        for part in p.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        out[p] = cur
    return out


def _declared_idle(d: Any) -> Optional[str]:
    """A producer may declare `identical_ok: true` with `identical_reason` when an
    unchanged output is legitimate today (review F6)."""
    if isinstance(d, dict) and d.get("identical_ok") is True:
        return f"producer declares identical output OK: {d.get('identical_reason') or 'no reason given'}"
    return None


# ═══════════════════════════════════════════════════════════════ io

def _read(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _newest(folder: Path, pattern: str) -> tuple[Optional[Path], Any]:
    """The newest receipt by NAME (the producer's stamp), never by mtime."""
    try:
        files = sorted(Path(folder).glob(pattern))
    except OSError:
        return None, None
    for p in reversed(files):
        d = _read(p)
        if d is not None:
            return p, d
    return (files[-1] if files else None), None


def _last_row(p: Path, pred: Callable[[dict], bool] = lambda r: True,
              nbytes: int = 262144) -> Optional[dict]:
    from backend.services import system_health as SH                # noqa: PLC0415
    for line in reversed(SH._tail_lines(Path(p), nbytes)):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and pred(r):
            return r
    return None


def _none(where: str) -> Reading:
    """No receipt at all."""
    return Reading(stamp=None, detail=f"no receipt at {where}", proof=where)


def _never_ran(task: Optional[dict]) -> bool:
    return task is not None and str(task.get("Last Result", "")).strip() == NEVER_RAN_RC


# ═══════════════════════════════════════════════════════════════ readers

#: daily-pass steps whose `nothing_to_do` is a FAILURE when due rows wait (F1)
GRADING_STEPS = ("grade_forecasts",)


def read_daily_pass_receipt(ctx, d: dict, day: Any = None) -> Reading:
    """One daily-pass receipt -> a reading. Every step's status goes through
    `map_status`; a `refused` step (the BRK-B blackout's bars_refresh) is DEGRADED
    with the step named; a grading step that did `nothing_to_do` while due rows
    are unresolved is DEGRADED too."""
    from backend.services import system_health as SH                # noqa: PLC0415
    steps = [s for s in d.get("steps") or [] if isinstance(s, dict)]
    stamps = [t for t in (parse_stamp(s.get("utc")) for s in steps) if t]
    t = max(stamps) if stamps else parse_stamp(d.get("finished_utc") or d.get("started_utc"))
    status, bad = "OK", []
    for s in steps:
        m = map_status(s.get("status"))
        if m != "OK" and m != "IDLE":
            status = worst(status, "DEGRADED")
            why = "; ".join(str(x) for x in (s.get("refusals") or [])[:1])
            bad.append(f"{s.get('step')}={s.get('status')}" + (f" ({why[:120]})" if why else ""))
    L = SH._ledger_scan(ctx) or {}
    due = int(L.get("due_unresolved") or 0)
    for s in steps:
        if s.get("step") in GRADING_STEPS and str(s.get("status")) == "nothing_to_do" and due > 0:
            status = worst(status, "DEGRADED")
            bad.append(f"{s.get('step')}=nothing_to_do while {due} due row(s) are unresolved")
    sub = substance([{k: s.get(k) for k in ("step", "status", "rows")} for s in steps])
    return Reading(stamp=t, status=status, reason="; ".join(bad),
                   substance=sub, idle_reason=_declared_idle(d),
                   proof=f"daily_pass_{day or d.get('date')}.json steps[*]",
                   detail=f"daily_pass {day or d.get('date')}: {str(d.get('headline') or '')[:120]}")


def r_daily_pass(ctx, task) -> Reading:
    from backend.services import system_health as SH                # noqa: PLC0415
    day, d = SH._newest_daily_pass(ctx, back=8)
    if not d:
        return _none("night_factory_<d>/daily_pass_<d>.json")
    return read_daily_pass_receipt(ctx, d, day)


def _delegate(fn_name: str, label: str):
    def reader(ctx, task) -> Reading:
        from backend.services import system_health as SH            # noqa: PLC0415
        r = getattr(SH, fn_name)(ctx)
        return Reading(stamp=SH._ts(r.evidence_utc), delegated=r.verdict,
                       substance=None, proof=r.proof or label,
                       detail=f"{label}: {r.detail}",
                       reason=r.detail if r.verdict != "ALIVE" else "")
    return reader


def r_nn_lab(ctx, task) -> Reading:
    # Read the lab's receipts directly through the shared contract: the live path
    # never imports the lab package (own interpreter; pinned by the lab's suite).
    from backend.services import nightly_receipt_contract as NRC     # noqa: PLC0415
    rd = ctx.path("nn_lab_receipts", ctx.optimus_dir / "nn_lab" / "receipts")
    c = NRC.health_contract(receipt_dir=rd, now=ctx.now)
    proof = f"nightly_receipt_contract.health_contract(): {c.get('receipt') or 'no receipt'}"
    if c.get("receipt") is None:
        return _none("nn_lab/receipts/nightly_*.json")
    age = c.get("age_hours")
    t = ctx.now - timedelta(hours=float(age)) if age is not None else None
    st = map_status(c.get("receipt_status"))
    if str(c.get("status")) == "REFUSED":
        st = worst(st, "REFUSED")
    return Reading(stamp=t or (ctx.now if st == "REFUSED" else None), status=st,
                   reason=c.get("line", "") if st != "OK" else "",
                   substance=None, proof=proof, detail=c.get("line", ""))


def r_sim_owner(ctx, task) -> Reading:
    row = _last_row(ctx.optimus_dir / "sim" / "owner.jsonl")
    if row is None:
        return _none("sim/owner.jsonl")
    a = str(row.get("action"))
    st = map_status(a)
    why = str(row.get("why") or "")
    return Reading(stamp=parse_stamp(row.get("utc")), status=st, reason=why,
                   idle_reason=f"owner: {why[:140]}" if st == "IDLE" else None,
                   proof="sim/owner.jsonl[-1].utc", detail=f"owner {a}: {why[:140]}")


def r_catalog(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "data_catalog", "catalog_*.json")
    if not isinstance(d, dict):
        return _none("data_catalog/catalog_*.json")
    st, why = receipt_status(d)
    t = parse_stamp(d.get("utc") or d.get("run_id"))
    # C15 (2026-10-07): the same daily firing rebuilds the Opportunity Explorer receipt and
    # publishes the sanitised public receipts; each writes its own keeper row. A step row of
    # this firing (within CATALOG_STEP_WINDOW_H of the catalog receipt) that is not ok
    # degrades the task row, named; a step that never wrote a row is named too.
    steps = []
    for step, fname in CATALOG_STEPS:
        k = _last_row(ctx.optimus_dir / "task_keeper" / fname)
        tk = parse_stamp((k or {}).get("utc"))
        if k is None or tk is None or (t is not None and tk < t - timedelta(hours=CATALOG_STEP_WINDOW_H)):
            steps.append(f"{step}: no row from this firing")
            continue
        act = k.get("action") or {"COMMITTED": "ok"}.get(str(k.get("status")), k.get("status"))
        ms = map_status(act)
        if ms != "OK":
            st = worst(st, "DEGRADED" if ms in ("REFUSED", "DEAD") else ms)
            why = (why + f"; {step} {act}: {str(k.get('why') or k.get('reasons') or '')[:160]}").strip("; ")
        steps.append(f"{step}: {act}")
    return Reading(stamp=t, status=st, reason=why,
                   substance=substance(d.get("summary")), idle_reason=_declared_idle(d),
                   proof=f"data_catalog/{p.name} utc + task_keeper/{{opportunities,publish_receipts,publish_commit}}.jsonl",
                   detail=f"catalog {p.name}: {str(d.get('summary'))[:120]}; " + "; ".join(steps))


#: C15: the steps that ride the AegisDataCatalog firing, each with its own keeper series
CATALOG_STEPS = (("opportunities_build", "opportunities.jsonl"), ("publish_receipts", "publish_receipts.jsonl"),
                 ("publish_commit", "publish_commit.jsonl"))
CATALOG_STEP_WINDOW_H = 6.0


#: the rehearsal's declared progress: the grade, not the day or the sheet hash (F6)
REHEARSAL_PROGRESS = ("grade.relative_0bps", "grade.n_closed")


def r_rehearsal(ctx, task) -> Reading:
    row = _last_row(ctx.optimus_dir / "contest" / "rehearsal" / "runs.jsonl")
    if row is None:
        return _none("contest/rehearsal/runs.jsonl")
    t = parse_stamp(row.get("finished_utc") or row.get("started_utc"))
    st, why = receipt_status(row)
    sheet = row.get("sheet")
    grade = row.get("grade") or {}
    if isinstance(grade, dict) and grade.get("error"):
        st, why = worst(st, "DEGRADED"), (why + f"; grade.error={grade['error']}").strip("; ")
    return Reading(stamp=t, status=st, reason=why,
                   substance=substance(pick(row, REHEARSAL_PROGRESS)), idle_reason=_declared_idle(row),
                   proof="contest/rehearsal/runs.jsonl[-1]",
                   detail=f"rehearsal {row.get('day')}: sheet "
                          + (str((sheet or {}).get('sheet_code')) if isinstance(sheet, dict) else str(sheet)[:100]))


def _contest_live_first_day() -> date:
    """Raises when the contest calendar cannot be imported (the caller reports
    the exception class; review F2)."""
    from scripts import contest_calendar as cc                        # noqa: PLC0415
    return cc.CONTEST_START - timedelta(days=3)


def r_contest_desk(ctx, task) -> Reading:
    live = ctx.optimus_dir / "contest" / "live"
    run = _last_row(live / "runs.jsonl")
    rp, ref = _newest(live / "refusals", "live_gate_*.json")
    t_run = parse_stamp((run or {}).get("finished_utc") or (run or {}).get("started_utc"))
    t_ref = parse_stamp((ref or {}).get("written_utc")) if isinstance(ref, dict) else None
    if t_ref and (t_run is None or t_ref >= t_run):
        why = " | ".join(ref.get("reasons") or []) or "gate refused"
        return Reading(stamp=t_ref, status="REFUSED", reason=why, substance=None,
                       proof=f"contest/live/refusals/{rp.name}", detail=f"live gate REFUSED: {why[:160]}")
    if t_run:
        st, why = receipt_status(run)
        return Reading(stamp=t_run, status=st, reason=why, substance=substance(run),
                       proof="contest/live/runs.jsonl[-1]", detail=f"live desk {run.get('day')}")
    try:
        first = _contest_live_first_day()
    except Exception as exc:                                          # noqa: BLE001
        return Reading(unknown_reason=(f"no live receipt, and the contest calendar could not be "
                                       f"imported to say whether one is due ({type(exc).__name__}: "
                                       f"{str(exc)[:120]})"),
                       proof="scripts.contest_calendar.CONTEST_START")
    rd = _none("contest/live/runs.jsonl or contest/live/refusals/")
    if ctx.now.date() < first:
        rd.idle_reason = f"not yet due: the live desk's first sheet day is {first}"
    else:
        rd.detail = (f"no live receipt although the first sheet day {first} has passed"
                     + (" and the scheduler says it has NEVER run (0x41303)" if _never_ran(task) else ""))
    return rd


def r_hyp_lab(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "hyp_lab" / "receipts", "nightly_*.json")
    if not isinstance(d, dict):
        return _none("hyp_lab/receipts/nightly_*.json")
    st, why = receipt_status(d, fields=("status",), error_fields=("why_exited", "error"))
    if "status" not in d:
        st, why = "DEGRADED", "receipt carries no status"
    return Reading(stamp=parse_stamp(d.get("started_utc")), status=st,
                   reason=str(d.get("reason") or why),
                   substance=substance({k: d.get(k) for k in ("declared", "results")}),
                   idle_reason=_declared_idle(d),
                   proof=f"hyp_lab/receipts/{p.name} started_utc",
                   detail=f"hyp_lab nightly {d.get('status')}; declared {d.get('declared')}")


def r_world_digest(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "digest", "world_digest_*.json")
    # Budget refusals live outside the normal digest directory. Read only this
    # public receipt family, never the private shared-budget envelope.
    reasons = {"SHARED_ENVELOPE_BLOCKED", "SHARED_ENVELOPE_INVALID",
               "SHARED_ENVELOPE_EXHAUSTED", "SHARED_ENVELOPE_UNAVAILABLE",
               # the preflight's finer codes (6b75aee6) read as REFUSED with
               # their name, not as a malformed receipt (2026-11-10, CH-04)
               "SHARED_ENVELOPE_MISSING", "SHARED_ENVELOPE_LOCK_UNREADABLE",
               "SHARED_ENVELOPE_MALFORMED", "SHARED_ENVELOPE_IMPORT_FAILED"}
    latest = None
    try:
        failures = sorted((ctx.optimus_dir / "news_digest" / "receipts").glob(
            "budget_refused_*.json"))
    except OSError:
        return Reading(status="DEAD", reason="budget failure receipts unreadable",
                       delegated="DEAD", detail="budget failure receipts unreadable")
    for fp in failures:
        proof = f"news_digest/receipts/{fp.name} observed_at"
        failure = _read(fp)
        try:
            match = re.fullmatch(r"budget_refused_(\d{8}T\d{6}Z)_[0-9a-f]{32}\.json", fp.name)
            observed = failure.get("observed_at") if isinstance(failure, dict) else None
            clock = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            compact = parse_stamp(failure.get("stamp"))
            valid = (match is not None and clock.tzinfo is not None
                     and clock.utcoffset() == timedelta(0)
                     and clock <= ctx.now
                     and compact == clock.replace(microsecond=0)
                     and failure.get("stamp") == match.group(1)
                     and failure.get("state") == "BUDGET_REFUSED"
                     and failure.get("stage") == "shared_budget_preflight"
                     and failure.get("written") is False
                     and failure.get("reason") in reasons)
        except (ValueError, TypeError, AttributeError, OverflowError):
            valid = False
        if not valid:
            # An undateable failure cannot safely be ordered behind an OK run.
            # Do not echo arbitrary receipt text or exception messages.
            return Reading(status="DEAD", reason="malformed or future budget failure receipt",
                           delegated="DEAD", detail="malformed or future budget failure receipt",
                           proof=proof)
        if latest is None or clock > latest[0]:
            latest = (clock, failure["reason"], proof)
    if latest is not None:
        try:
            digest_clock = parse_stamp(d.get("stamp")) if isinstance(d, dict) else None
        except (ValueError, TypeError, OverflowError):
            digest_clock = None
        if digest_clock is None or digest_clock > ctx.now or latest[0] >= digest_clock:
            return Reading(stamp=latest[0], status="DEGRADED", reason=latest[1],
                           proof=latest[2], detail="world digest shared budget preflight refused")
    if not isinstance(d, dict):
        return _none("digest/world_digest_*.json")
    st, why = receipt_status(d, fields=("status",))
    bad = [why] if why else []
    spend = d.get("spend") or {}
    if int(spend.get("failed") or 0) > 0:
        st = worst(st, "DEGRADED")
        bad.append(f"{spend.get('failed')} of {spend.get('calls')} LLM call(s) failed")
    if int(d.get("n_items") or 0) == 0:
        st = worst(st, "DEGRADED")
        bad.append("zero items in the window")
    return Reading(stamp=parse_stamp(d.get("stamp")), status=st, reason="; ".join(bad),
                   substance=substance(pick(d, ("n_items", "counts", "themes"))),
                   idle_reason=_declared_idle(d), proof=f"digest/{p.name} stamp",
                   detail=f"digest {p.name}: {d.get('n_items')} items")


def r_local_runtime_digest(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "local_runtime_digest", "digest_*.json")
    if not isinstance(d, dict):
        return _none("local_runtime_digest/digest_*.json")
    st = map_status(d.get("status") or "FAILED")
    inputs = d.get("inputs") or []
    valid = sum(max(0, int(x.get("sampled_rows", 0)) - int(x.get("invalid_rows", 0)))
                for x in inputs if isinstance(x, dict) and x.get("exists"))
    why = str(d.get("reason") or "")
    if st == "OK" and (not valid or not d.get("served_models") or not d.get("summary")
                       or int(d.get("tokens_out") or 0) <= 0
                       or d.get("paid_fallback") is not False or d.get("cost_usd") != 0
                       or d.get("owned_server_stopped") is False):
        st, why = "DEGRADED", "receipt lacks successful local inference over valid log rows or cleanup failed"
    return Reading(stamp=parse_stamp(d.get("generated_utc")), status=st, reason=why,
                   substance=substance(inputs), proof=f"local_runtime_digest/{p.name}",
                   detail=f"local model status {d.get('status')}; {valid} valid sampled log rows")


def r_local_branching_private_grade(ctx, task) -> Reading:
    """Read the existing native owner's journal, including its real refusals.

    This private owner is registered separately, not by task_keeper. No grade,
    source review or population admission is manufactured by this health reader.
    """
    from backend.services import system_health as SH
    default = Path.home() / "aegis-recovery-evidence/oct14-continuation-20261014/local-branching/automation_runs.jsonl"
    path = ctx.path("local_branching_runs", default)
    lines = SH._tail_lines(path, 262144)
    if not lines:
        return _none(str(path))
    # Never fall back to an older green row when the newest write is malformed.
    try:
        d = json.loads(lines[-1])
    except ValueError:
        return Reading(status="DEGRADED", detail="newest branching owner row is malformed", proof=str(path))
    if not isinstance(d, dict):
        return Reading(status="DEGRADED", detail="newest branching owner row is not an object", proof=str(path))
    action = d.get("action")
    status = {"GRADED": "OK", "ALREADY_GRADED": "IDLE", "WAIT_ENTRY": "IDLE",
              "WAIT_SHARED_REFRESH": "IDLE", "WAIT_CONSTITUENT_MARKS": "IDLE",
              "YIELD_IIF_WINDOW": "IDLE", "STOP": "STOPPED", "REFUSED": "REFUSED"}.get(action, "DEGRADED")
    stamp = parse_stamp(d.get("utc"))
    why = str(d.get("reason") or "")
    if d.get("task") != "AegisLocalBranchingPrivateGrade" or stamp is None or stamp > ctx.now + timedelta(seconds=30):
        status, why = "DEGRADED", "owner identity or receipt UTC is invalid"
    if action in {"GRADED", "ALREADY_GRADED", "WAIT_ENTRY", "WAIT_SHARED_REFRESH", "WAIT_CONSTITUENT_MARKS"}:
        proof = d.get("resource_proof") or {}
        if not isinstance(proof, dict):
            proof = {}
        peak, limit = proof.get("aggregate_peak_upper_bound"), proof.get("aggregate_limit_bytes")
        if (proof.get("child_reaped") is not True or type(peak) is not int or peak < 0
                or type(limit) is not int or limit != 512 * 1024 ** 2 or peak >= limit):
            status, why = "DEGRADED", "owned child cleanup or aggregate resource proof is absent/invalid"
    if action == "GRADED" and (d.get("n_books") != 247 or d.get("n_twins") != 0 or not d.get("grade_receipt")):
        status, why = "DEGRADED", "original frozen cohort grade receipt/counts are absent/invalid"
    population = d.get("population1000")
    if population is not None:
        nested, note = receipt_status(population, fields=("action",), error_fields=("error", "errors", "traceback"))
        if isinstance(population, dict) and population.get("action") == "POPULATION_OPERATED":
            counts = [population.get(k) for k in ("new_frozen_books", "marked", "pending_entry")]
            if population.get("activation") == "NONE" and all(type(n) is int and n >= 0 for n in counts):
                errors, note = receipt_status(population, fields=(), error_fields=("error", "errors", "traceback"))
                nested = worst("OK" if counts[0] or counts[1] else "IDLE", errors)
            else:
                nested, note = "DEGRADED", "population operating counts/activation are invalid"
        status, why = worst(status, nested), "; ".join(x for x in (why, note) if x)
    return Reading(stamp=stamp, status=status, reason=why,
                   substance=substance(pick(d, ("action", "session", "grade_receipt", "population1000"))),
                   proof=str(path) + "[-1]", detail=f"private branching owner {action}; population "
                   + (str(population.get("action")) if isinstance(population, dict) else "not present in this owner version"))


def r_alerts(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "alerts" / "receipts", "alert_pass_*.json")
    if not isinstance(d, dict):
        return _none("alerts/receipts/alert_pass_*.json")
    st, why = receipt_status(d, fields=("status", "state"))
    bh = d.get("bars_health")
    bad = [why] if why else []
    if not isinstance(bh, dict):
        st = worst(st, "DEGRADED")
        bad.append("no bars_health block (the pass cannot say its bars are fresh)")
    elif map_status(bh.get("state")) != "OK":
        st = worst(st, "DEGRADED")
        bad.append(f"bars_health {bh.get('state')}: {str(bh.get('line'))[:120]}")
    return Reading(stamp=parse_stamp(d.get("created_utc")), status=st, reason="; ".join(bad),
                   idle_reason=_declared_idle(d), proof=f"alerts/receipts/{p.name} created_utc",
                   detail=f"alert pass {d.get('mode')}: {d.get('n_events')} event(s)")


def r_straddle(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "straddle_forward" / "runs", "pass_*.json")
    if not isinstance(d, dict):
        return _none("straddle_forward/runs/pass_*.json")
    state = str(d.get("state") or "")
    st = map_status(state.split(":", 1)[0])           # "REFUSED: ...", "STOPPED: ...", "OBSERVE_ONLY: ..."
    why = state if st != "OK" else ""
    g = d.get("grade") or {}
    if isinstance(g, dict) and g.get("error"):
        st, why = worst(st, "DEGRADED"), (why + f"; grade.error={g['error']}").strip("; ")
    return Reading(stamp=parse_stamp(d.get("now_utc") or d.get("stamp")), status=st, reason=why,
                   substance=substance(pick(d, ("state", "summary.n_usable",
                                                "summary.median_straddle_spread_usable"))),
                   idle_reason=_declared_idle(d), proof=f"straddle_forward/runs/{p.name} now_utc",
                   detail=f"straddle pass: {state[:120]}")


def accounts_status(accts: Iterable[Any]) -> tuple[str, str, list]:
    """Per-account statuses -> (status, reason, excused). Shared by the fleet
    daily check and both fleet-manager passes (review F3): any non-retired
    account not OK is DEGRADED; EVERY non-retired account failing is DEAD."""
    retired = set(getattr(_config, "PAPER_ACCOUNTS_RETIRED_UNREADABLE", ()) or ())
    rows = [a for a in accts or [] if isinstance(a, dict)]
    live = [a for a in rows if a.get("role") not in retired]
    excused = [f"{a.get('role')} {a.get('status')}" for a in rows
               if a.get("role") in retired and map_status(a.get("status")) != "OK"]
    bad = [a for a in live if map_status(a.get("status")) not in ("OK", "IDLE")]
    if not live:
        return "DEGRADED", "no live account in the receipt", excused
    names = [f"{a.get('role')}={a.get('status')}" + (f" ({str(a.get('why'))[:80]})" if a.get("why") else "")
             for a in bad]
    if bad and len(bad) == len(live):
        return "DEAD", f"EVERY account failed: {names}", excused
    if bad:
        return "DEGRADED", f"accounts not ok: {names}", excused
    return "OK", "", excused


def _eod_audit_status(ctx, d: dict, fm_root: Path, name: str) -> tuple[str, str]:
    """C26: a Preclose pass must be followed by its end-of-day audit rows
    (`fleet_manager/eod_audit/audit.jsonl`, same run_id). Missing -> DEGRADED;
    rows present -> the same per-account rule as the passes (retired excused).
    Receipts started before FLEET_EOD_AUDIT_SINCE_UTC predate the audit."""
    since = parse_stamp(getattr(_config, "FLEET_EOD_AUDIT_SINCE_UTC", None))
    started = parse_stamp(d.get("started_utc"))
    if since and started and started < since:
        return "OK", ""
    from backend.services import system_health as SH                # noqa: PLC0415
    rows = []
    for line in SH._tail_lines(fm_root / "eod_audit" / "audit.jsonl", 262144):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("run_id") == d.get("run_id"):
            rows.append(r)
    if not rows:
        blk = d.get("eod_audit") or {}
        return "DEGRADED", (f"no end-of-day audit row for preclose {name}"
                            + (f" ({str(blk.get('status'))[:120]})" if blk.get("status") else ""))
    st, why, _ex = accounts_status(rows)
    return ("OK", "") if st == "OK" else ("DEGRADED", f"eod audit: {why}")


def _fleet_rejections_status(d: dict) -> tuple[str, str]:
    """(status, reason) from a fleet run receipt's LIVE buys: DEGRADED when the
    broker rejected more than `FLEET_REJECTED_BUY_DEGRADED_FRAC` of them."""
    from backend.services import fleet_manager as _FM     # lazy: the reader module stays import-light
    accs = [a for a in d.get("accounts") or [] if isinstance(a, dict)]
    summ = _FM.rejection_summary([x for a in accs for x in (a.get("actions") or [])])
    if not summ["degraded"]:
        return "OK", ""
    per = []
    for a in accs:
        s_ = _FM.rejection_summary(a.get("actions") or [])
        if s_["n_rejected"]:
            per.append(f"{a.get('role')} {s_['n_rejected']}/{s_['n_live_buys_sent']}")
    return "DEGRADED", (f"broker rejected {summ['n_rejected']} of {summ['n_live_buys_sent']} LIVE buys "
                        f"({summ['rejected_frac']:.0%} > {summ['threshold']:.0%}): "
                        f"{summ['by_reason']['wash_trade_403']} wash-trade 403, {summ['by_reason']['http_422']} 422, "
                        f"{summ['by_reason']['other']} other [{', '.join(per)}]")


def _fleet_pass(which: str):
    def reader(ctx, task) -> Reading:
        folder = ctx.optimus_dir / "paper_accounts" / "fleet_manager" / "runs"
        try:
            files = sorted(folder.glob("run_*.json"))
        except OSError:
            files = []
        for p in reversed(files):
            d = _read(p)
            if isinstance(d, dict) and str(d.get("pass")) == which:
                st0, why0 = receipt_status(d, fields=("status",))
                st, why, excused = accounts_status(d.get("accounts"))
                st_a, why_a = (_eod_audit_status(ctx, d, folder.parent, p.name) if which == "preclose"
                               else ("OK", ""))
                blind = [f"{a.get('role')} ({str(a.get('stop_history_error'))[:80]})"
                         for a in d.get("accounts") or [] if isinstance(a, dict) and a.get("stop_history_error")]
                if blind:
                    st_a = worst(st_a, "DEGRADED")
                    why_a = "; ".join(x for x in (why_a, f"stop history unreadable (cooldown blind): {blind}") if x)
                # C27: a pass where the broker rejected more than FLEET_REJECTED_BUY_DEGRADED_FRAC of the
                # LIVE buys it was sent is DEGRADED, with the counts by reason (derived from the actions,
                # so receipts written before C27 are read the same way)
                st_r, why_r = _fleet_rejections_status(d)
                st_a = worst(st_a, st_r)
                why_a = "; ".join(x for x in (why_a, why_r) if x)
                return Reading(stamp=parse_stamp(d.get("finished_utc") or d.get("started_utc")),
                               status=worst(st0, st, st_a),
                               reason="; ".join(x for x in (why0, why, why_a) if x),
                               substance=substance([{k: a.get(k) for k in ("role", "status", "equity")}
                                                    for a in d.get("accounts") or [] if isinstance(a, dict)]),
                               proof=f"fleet_manager/runs/{p.name} accounts[*].status",
                               detail=f"fleet manager {which} pass {p.name}"
                                      + (f"; retired, excused by config: {excused}" if excused else ""))
        return _none(f"paper_accounts/fleet_manager/runs/run_*.json with pass={which}")
    return reader


def _sweep_success_shape(d: dict) -> bool:
    """Check the producer's complete role/result census before crediting coverage."""
    roles = d.get("roles")
    if not isinstance(roles, list) or not roles or len(roles) > 5:
        return False
    counts: dict[str, int] = {}
    for role in roles:
        if not isinstance(role, dict):
            return False
        name, count, held = role.get("role"), role.get("candidates"), role.get("held_symbols")
        if (not isinstance(name, str) or name not in _config.FLEET_MANAGER_ROLES or name in counts
                or type(count) is not int or count < 0 or type(held) is not int or held < count
                or role.get("status") != ("CANDIDATE" if count else "ALREADY_COVERED")):
            return False
        counts[name] = count
    candidates = d.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) != sum(counts.values()):
        return False
    seen: set[tuple[str, str]] = set()
    for row in candidates:
        if not isinstance(row, dict):
            return False
        role, symbol = row.get("role"), row.get("symbol")
        if (not isinstance(role, str) or role not in counts or not isinstance(symbol, str) or not symbol
                or (role, symbol) in seen or row.get("status") !=
                ("PROTECTED" if d.get("status") == "PROTECTED" else "ALREADY_COVERED")):
            return False
        seen.add((role, symbol))
    return (all(sum(1 for role, _ in seen if role == name) == n for name, n in counts.items())
            and (bool(candidates) if d.get("status") == "PROTECTED" else True))


def _sweep_stamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None


def _sweep_reading(ctx, p: Path) -> Reading:
    d = _read(p)
    proof = f"paper_accounts/fleet_manager/sweeps/{p.name}"
    if not isinstance(d, dict) or d.get("schema") != "fleet_protect_sweep/1":
        return Reading(status="DEGRADED", reason="newest sweep receipt unreadable or wrong schema",
                       proof=proof, detail="sweep receipt invalid")
    started, stamp = _sweep_stamp(d.get("started_utc")), _sweep_stamp(d.get("finished_utc"))
    try:
        named_start = datetime.strptime(p.stem, "sweep_%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    except ValueError:
        named_start = None
    if (started is None or stamp is None or named_start != started
            or not started <= stamp <= ctx.now or (stamp - started) > timedelta(minutes=3)):
        return Reading(stamp=stamp, run_start=started, status="DEGRADED",
                       reason="sweep start/finish/filename chronology invalid or unfinished",
                       proof=proof, detail=f"sweep {d.get('status')}")
    status = d.get("status")
    if status == "REFUSED":
        st = "REFUSED"
    elif d.get("live_flag") is not True or status in {"INCOMPLETE", "DRY_PLAN"}:
        st = "DEGRADED"
    elif status in {"ALREADY_COVERED", "PROTECTED"}:
        st = "OK" if _sweep_success_shape(d) else "DEGRADED"
    else:
        st = "DEGRADED"
    warnings = d.get("history_warnings", [])
    if not isinstance(warnings, list):
        st = worst(st, "DEGRADED")
        warning_note = "invalid historical-intent warning field"
    elif warnings:
        st = worst(st, "DEGRADED")
        warning_note = f"{len(warnings)} unresolved historical stop intent warning(s); manual review required"
    else:
        warning_note = ""
    reason = ("DRY receipt is not live coverage" if d.get("live_flag") is not True and st != "REFUSED"
              else str(d.get("why") or status)[:180])
    reason = "; ".join(part for part in (reason, warning_note) if part)
    return Reading(stamp=stamp, run_start=started, status=st, reason=reason,
                   proof=proof, detail=f"sweep {status} ({p.name})")


def r_fleet_sweep(ctx, task) -> Reading:
    """Newest sweep attempt, with a calendar-proven post-close idle exception."""
    folder = ctx.optimus_dir / "paper_accounts" / "fleet_manager" / "sweeps"
    try:
        files = sorted(folder.glob("sweep_*.json"))
    except OSError:
        files = []
    if not files:
        return _none("paper_accounts/fleet_manager/sweeps/sweep_*.json")
    latest = _sweep_reading(ctx, files[-1])
    # The producer's refusal text is ambiguous (closed OR stale clock). Only a
    # verified calendar close and a complete final eligible LIVE pass make it idle.
    if latest.status == "REFUSED" and latest.run_start is not None:
        raw = _read(files[-1])
        window = _sweep_window(latest.run_start.date())
        if (window and latest.run_start >= window[2]
                and isinstance(raw, dict) and raw.get("live_flag") is True
                and raw.get("history_warnings", []) == []
                and "sweep venue closed, clock stale, or inside frozen close buffer" in str(raw.get("why"))):
            # Only the immediately preceding attempt can prove the final window.
            # A newer warning, failure or corrupt receipt supersedes older success,
            # even when the later post-close refusal itself carries no warning.
            if len(files) > 1:
                previous = _sweep_reading(ctx, files[-2])
                chain = f"{previous.proof} + {latest.proof}"
                if (previous.status == "OK" and previous.run_start is not None
                        and window[1] <= previous.run_start <= window[1] + timedelta(minutes=3)
                        and previous.stamp is not None and previous.stamp <= window[2]):
                    return Reading(stamp=previous.stamp, run_start=previous.run_start, status="IDLE",
                                   idle_reason="calendar-verified post-close; final eligible live sweep completed",
                                   proof=chain, detail="sweep closed-session idle")
                latest.proof = chain
                latest.reason = (f"latest preceding attempt {previous.status.lower()}: "
                                 f"{previous.reason[:120]}; {latest.reason}")
    return latest


def r_fleet_daily(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "paper_accounts" / "fleet_daily", "fleet_*.json")
    if not isinstance(d, dict):
        return _none("paper_accounts/fleet_daily/fleet_*.json")
    st, why, excused = accounts_status(d.get("accounts"))
    return Reading(stamp=parse_stamp(d.get("stamp_utc")), status=st, reason=why,
                   substance=substance([{k: a.get(k) for k in ("role", "status", "equity")}
                                        for a in d.get("accounts") or [] if isinstance(a, dict)]),
                   proof=f"fleet_daily/{p.name} stamp_utc",
                   detail=f"fleet daily check: {d.get('n_flags')} flag(s)"
                          + (f"; retired, excused by config: {excused}" if excused else ""))


def r_reader(ctx, task) -> Reading:
    dj = ctx.optimus_dir / "dowjones"
    row = _last_row(dj / "night_reader_supervisor.jsonl", lambda r: r.get("event") == "tick")
    if (dj / "SUPERVISOR_STOP").exists():
        return Reading(stamp=parse_stamp((row or {}).get("t")), status="STOPPED",
                       reason="dowjones/SUPERVISOR_STOP exists (the owner's pause)",
                       proof="dowjones/SUPERVISOR_STOP", detail="reader paused by the owner")
    if row is None:
        return _none("dowjones/night_reader_supervisor.jsonl (event tick)")
    return Reading(stamp=parse_stamp(row.get("t")), substance=str(row.get("page_loads_total")),
                   proof="night_reader_supervisor.jsonl[tick].t + page_loads_total",
                   detail=f"supervisor tick: {row.get('page_loads_total')} page loads total, "
                          f"{row.get('new_loads')} new")


def r_catchup(ctx, task) -> Reading:
    row = _last_row(ctx.optimus_dir / "task_keeper" / "keeper.jsonl", lambda r: r.get("job") == "catchup")
    if row is None:
        return _none("task_keeper/keeper.jsonl (job catchup)")
    st = map_status(row.get("action")) if row.get("action") else "OK"
    # `too_old` / `wait` / `skip` are the catch-up deciding correctly; only a start
    # that the scheduler rejected is a failure of the catch-up itself
    failed = [d.get("task") for d in row.get("decisions") or []
              if isinstance(d, dict) and str(d.get("action")) == "start_failed"]
    if failed:
        st = worst(st, "DEGRADED")
    return Reading(stamp=parse_stamp(row.get("utc")), status=st,
                   reason=str(row.get("why") or "") + (f" start failed: {failed}" if failed else ""),
                   proof="task_keeper/keeper.jsonl[catchup].utc",
                   detail=f"catch-up: started {row.get('started') or 'nothing'}")


def _terminal_repo(ctx) -> Path:
    return Path(ctx.paths.get("terminal_repo")
                or os.getenv("AAT_REPO") or (ctx.repo.parent / "aegis-alpha-terminal"))


def r_analyst_panel(ctx, task) -> Reading:
    folder = _terminal_repo(ctx) / "state" / "research" / "analyst_panel"
    if not folder.exists():
        return Reading(unknown_reason=("the panel's receipts live in the terminal repo "
                                       "(state/research/analyst_panel/<date>.jsonl), which is not "
                                       "present beside this repo on this machine"),
                       proof="aegis-alpha-terminal/state/research/analyst_panel")
    try:
        files = sorted(folder.glob("20??-??-??.jsonl"))
    except OSError:
        files = []
    if not files:
        return _none("aegis-alpha-terminal/state/research/analyst_panel/<date>.jsonl")
    p = files[-1]
    row = _last_row(p)
    t = parse_stamp((row or {}).get("captured_utc")) or parse_stamp(p.stem)
    n = sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
    return Reading(stamp=t, status="OK" if n > 0 else "DEGRADED",
                   reason="" if n > 0 else "the newest panel file is empty",
                   proof=f"analyst_panel/{p.name}[-1].captured_utc",
                   detail=f"analyst panel {p.stem}: {n} rows")


def r_analyst_pull(ctx, task) -> Reading:
    p, d = _newest(ctx.optimus_dir / "analyst", "analyst_pull_*.json")
    k = _last_row(ctx.optimus_dir / "task_keeper" / "analyst.jsonl")
    t_pull = parse_stamp((d or {}).get("written_utc")) if isinstance(d, dict) else None
    t_k = parse_stamp((k or {}).get("utc"))
    if k and t_k and (t_pull is None or t_k > t_pull):
        st = map_status(k.get("action"))
        if st != "OK":                       # refused OR failed (rc != 0, timeout): REFUSED (F5)
            return Reading(stamp=t_k, status="REFUSED",
                           reason=f"{k.get('action')}: {k.get('why')}",
                           proof="task_keeper/analyst.jsonl[-1]",
                           detail=f"analyst pull {k.get('action')}: {k.get('why')}")
    if not isinstance(d, dict):
        return _none("analyst/analyst_pull_<day>.json")
    ok = (d.get("n_snapshots") or 0) > 0
    rd = Reading(stamp=t_pull, status="OK" if ok else "DEGRADED",
                 reason="" if ok else "the pull wrote zero snapshots",
                 proof=f"analyst/{p.name} written_utc",
                 detail=f"analyst pull {d.get('day')}: {d.get('n_snapshots')} snapshots of "
                        f"{d.get('n_requested')}, {d.get('n_failed')} failed")
    if _never_ran(task) and not k:
        rd.never_by_task = True
        rd.idle_reason = ("the data is fresh from a MANUAL pull; this task has never run "
                          f"(next run {task.get('Next Run Time')}) -- the row certifies the data, "
                          "not the task")
    return rd


def r_brain(ctx, task) -> Reading:
    k = _last_row(ctx.optimus_dir / "task_keeper" / "brain.jsonl")
    if k is None:
        return _none("task_keeper/brain.jsonl")
    a = str(k.get("action"))
    st = {"ok": "OK", "refused": "REFUSED"}.get(a, "DEGRADED")
    return Reading(stamp=parse_stamp(k.get("utc")), status=st, reason=str(k.get("why") or ""),
                   substance=None, proof="task_keeper/brain.jsonl[-1]",
                   detail=f"brain refresh {a}: {str(k.get('summary') or k.get('why') or '')[:140]}")


def r_public_flow(ctx, task) -> Reading:
    """C16 (2026-10-07): the public-flow sensors' daily job. A DEGRADED step
    (zero new USAspending rows on a weekday, a refused crypto component, LDA
    access denied) reads DEGRADED with the step named, never OK."""
    k = _last_row(ctx.optimus_dir / "task_keeper" / "public_flow.jsonl")
    if k is None:
        return _none("task_keeper/public_flow.jsonl")
    a = str(k.get("action"))
    status = {"ok": "OK", "refused": "REFUSED", "degraded": "DEGRADED"}.get(a, "DEGRADED")
    bad = [f"{n}={(v or {}).get('status')}" for n, v in k.items()
           if isinstance(v, dict) and map_status((v or {}).get("status")) not in ("OK", "IDLE")]
    if bad:
        status = worst(status, "DEGRADED")
    return Reading(stamp=parse_stamp(k.get("utc")), status=status, reason="; ".join(bad),
                   substance=None, proof="task_keeper/public_flow.jsonl[-1]",
                   detail=f"public flow {a}" + (f": {'; '.join(bad)[:140]}" if bad else ""))


def r_assets(ctx, task) -> Reading:
    """2026-10-07: the weekly public-assets refresh (`scripts/task_keeper.py`'s `assets`
    job -- bump the front-page pin, gate on `test_public_assets.py`, commit + push).

    Read `task_keeper/assets.jsonl`'s own row, NEVER `paper_accounts/public_assets_refresh_
    <run_id>.json` alone: that refresh receipt is written only on a SUCCESSFUL bump, so a
    week the job fired and REFUSED (the newest receipt pair not newer than the pinned one,
    a featured family with no LIVE account, a failed pinning test, an unpushed commit) would
    read UNKNOWN for want of a file a refusal never writes -- exactly the "a check that did
    not run is not a check that passed" trap this file exists to close. `action: "ok"` is
    OK; any `"skip"` (which covers both the ordinary identical-pin no-op most weeks and a
    real refusal) is DEGRADED rather than silently OK, so a real failure is never hidden
    behind the common case -- coarse, but never wrongly green."""
    k = _last_row(ctx.optimus_dir / "task_keeper" / "assets.jsonl")
    if k is None:
        return _none("task_keeper/assets.jsonl")
    a = str(k.get("action"))
    status = {"ok": "OK"}.get(a, "DEGRADED")
    why = str(k.get("why") or "")
    pin_note = (f" (pin {k.get('old_run_id')} -> {k.get('new_run_id')})"
               if k.get("new_run_id") and k.get("new_run_id") != k.get("old_run_id") else "")
    return Reading(stamp=parse_stamp(k.get("utc")), status=status, reason=why if status != "OK" else "",
                   substance=None, proof="task_keeper/assets.jsonl[-1]",
                   detail=f"public assets {a}{pin_note}" + (f": {why[:140]}" if why else ""))


def r_research_lane(ctx, task) -> Reading:
    """Q12 (2026-10-07): the weekly academic lane
    (`backend/services/research_instruments.py`, `scripts/task_keeper.py`'s
    `research` job / `scripts/research_lane.py --due`). Judged by the newest
    `research_instruments/probe_<run_id>.json` receipt's OWN stamp
    (`generated_utc`), never by the scheduler firing: the lane decides most
    weeks are a no-op (`research_lane_due`) and `HEALTH_TASK_CADENCE_H`
    declares the week, so a probe that is a few days old is still
    ALIVE_IDLE_EXPECTED, not STALE. `task_keeper/research_lane.jsonl`'s own
    row is read only when it is NEWER than the newest probe -- a `not_due`
    skip, or a `failed`/`refused` attempt that never reached `probe_card`."""
    p, d = _newest(ctx.optimus_dir / "research_instruments", "probe_*.json")
    k = _last_row(ctx.optimus_dir / "task_keeper" / "research_lane.jsonl")
    t_probe = parse_stamp((d or {}).get("generated_utc")) if isinstance(d, dict) else None
    t_k = parse_stamp((k or {}).get("utc"))
    if k is not None and (t_probe is None or (t_k is not None and t_k > t_probe)):
        action = str(k.get("action"))
        if action == "not_due":
            return Reading(stamp=t_probe, status="OK", idle_reason=f"not due yet: {k.get('why')}",
                           proof="task_keeper/research_lane.jsonl[-1]",
                           detail=f"research lane not due: {k.get('why')}")
        if action in ("failed", "refused"):
            return Reading(stamp=t_k, status="REFUSED" if action == "refused" else "DEGRADED",
                           reason=str(k.get("why") or ""),
                           proof="task_keeper/research_lane.jsonl[-1]",
                           detail=f"research lane {action}: {k.get('why')}")
    if not isinstance(d, dict):
        if k is not None:
            return Reading(stamp=None, status="OK",
                           idle_reason=(f"no probe has run yet; the weekly job's newest row is "
                                        f"{k.get('action')}: {k.get('why')}"),
                           proof="task_keeper/research_lane.jsonl[-1]",
                           detail="academic lane: no probe receipt yet")
        return _none("research_instruments/probe_<run_id>.json")
    st, why = receipt_status(d)
    return Reading(stamp=t_probe, status=st, reason=why,
                   substance=substance(pick(d, ("zero_kind", "card_slug"))),
                   proof=f"research_instruments/{p.name} generated_utc",
                   detail=f"academic lane probe {d.get('card_slug')}: {d.get('zero_kind')}, "
                          f"{d.get('queries_issued')} queries issued")


# ═══════════════════════════════ the tasks added 2026-11-11 .. 11-14 (S69, CH-22a §5.8)
#
# "A task is wired only when the status page reads its own receipt." Each reader below
# opens the file THAT job writes each run (named in its TaskSpec). Jobs repointed at a
# release clone run through `scripts/runtime_task.py`, which appends start/end rows (rc)
# to `runtime_switch/runtime_task_runs.jsonl`; that wrapper row is read ONLY to see a
# refusal the job prints and does not write (event_nodes rc 2, forward_calendar
# SNAPSHOT_EXISTS, discovery_autopsy refusals ...), and only when it is NEWER than the
# job's own receipt. Manual attended runs of the same module (`--help`, `--dry-run`,
# `contract`) land in that log too, so a run is matched by its scheduled argv.

RUNTIME_TASK_RUN_LOG = ("runtime_switch", "runtime_task_runs.jsonl")
#: argv tokens that mark an attended manual run, never the scheduled job
MANUAL_RUN_TOKENS = frozenset({"--help", "-h", "--dry-run", "--print-plan", "--now"})
#: wrapper rcs that are a refusal (the job's documented 2, the wrapper's own 90)
WRAPPER_REFUSED_RCS = frozenset({2, 90})


def _wrapper_lines(ctx) -> list[str]:
    from backend.services import system_health as SH                # noqa: PLC0415
    key = "runtime_task_runs_tail"
    if key not in ctx.cache:
        p = ctx.optimus_dir.joinpath(*RUNTIME_TASK_RUN_LOG)
        ctx.cache[key] = SH._tail_lines(p, int(getattr(_config, "TASK_RECEIPT_WRAPPER_TAIL_BYTES", 2_000_000)))
    return ctx.cache[key]


def _argv_matches(argv: Any, module: str, want: Iterable[str], exclude: Iterable[str]) -> bool:
    if not isinstance(argv, list):
        return False
    a = [str(x) for x in argv]
    at = next((i for i in range(len(a) - 1) if a[i] == "-m" and a[i + 1] == module), None)
    if at is None:
        return False
    tail = a[at + 2:]
    return (all(w in tail for w in want) and not any(x in tail for x in exclude)
            and not any(x in MANUAL_RUN_TOKENS for x in tail))


def wrapper_outcome(ctx, module: str, want: Iterable[str] = (), exclude: Iterable[str] = ()
                    ) -> Optional[dict]:
    """The newest `runtime_task.py` outcome of the SCHEDULED run of `module`: an `end`
    row paired (by wrapper_pid) with a start whose argv carries every `want` token, or a
    `refused` / `launch_failed` row with such an argv. None when the tail holds none."""
    want, exclude = tuple(want), tuple(exclude)
    starts: dict = {}
    out = None
    for line in _wrapper_lines(ctx):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not isinstance(r, dict):
            continue
        ev = r.get("event")
        if ev == "start" and _argv_matches(r.get("argv"), module, want, exclude):
            starts[r.get("wrapper_pid")] = r
        elif ev == "end" and r.get("module") == module and r.get("wrapper_pid") in starts:
            out = {"utc": parse_stamp(r.get("utc")), "rc": r.get("rc"), "event": "end",
                   "argv": starts.pop(r.get("wrapper_pid")).get("argv")}
        elif ev in ("refused", "launch_failed") and _argv_matches(r.get("argv"), module, want, exclude):
            out = {"utc": parse_stamp(r.get("utc")), "rc": r.get("rc"), "event": ev,
                   "argv": r.get("argv"), "why": str(r.get("why") or "")[:160]}
    return out


def _after_wrapper(ctx, rd: Reading, module: str, want: Iterable[str] = (), exclude: Iterable[str] = (),
                   *, idle_rcs: Optional[dict] = None,
                   refused_rcs: Iterable[int] = WRAPPER_REFUSED_RCS) -> Reading:
    """`rd` unless the scheduled run's wrapper row is NEWER than its receipt and exited
    non-zero: then REFUSED (rc 2 / 90) or DEGRADED (a crash code), stamped by that row.
    A receipt that already says it failed keeps its own (more specific) reason."""
    o = wrapper_outcome(ctx, module, want, exclude)
    if o is None or o["utc"] is None or o["utc"] > ctx.now + timedelta(seconds=60):
        return rd
    rc = o["rc"]
    if rd.stamp is not None and o["utc"] <= rd.stamp:
        return rd
    if rc == 0:
        return rd
    if idle_rcs and rc in idle_rcs:
        rd.detail = (rd.detail + f"; newest scheduled run exited {rc} ({idle_rcs[rc]})").strip("; ")
        return rd
    st = "REFUSED" if rc in set(refused_rcs) else "DEGRADED"
    why = (f"the scheduled `{module}` run at {o['utc']:%Y-%m-%d %H:%M} UTC exited rc {rc} "
           f"({o['event']}{': ' + o['why'] if o.get('why') else ''}) and wrote no newer receipt")
    if rd.status not in ("OK", "IDLE"):
        rd.reason = f"{rd.reason}; {why}"
        return rd
    return Reading(stamp=o["utc"], status=st, reason=why, substance=None,
                   proof="runtime_switch/runtime_task_runs.jsonl (end row after " + (rd.proof or "no receipt") + ")",
                   detail=rd.detail or f"{module}: no receipt")


def _newest_strict(folder: Path, pattern: str, keep: Callable[[dict], bool] = lambda d: True
                   ) -> tuple[Optional[Path], Any, Optional[str]]:
    """(path, receipt, unknown_reason): the newest receipt by NAME that `keep` accepts.
    An unreadable file met on the way is UNKNOWN (its kind cannot be told), never skipped."""
    try:
        files = sorted(Path(folder).glob(pattern))
    except OSError as exc:
        return None, None, f"cannot list {folder} ({type(exc).__name__})"
    for p in reversed(files):
        d = _read(p)
        if not isinstance(d, dict):
            return p, None, f"newest receipt {p.name} cannot be read as a JSON object"
        if keep(d):
            return p, d, None
    return None, None, None


def _sched_local(task: Optional[dict], date_key: str, time_key: str) -> Optional[datetime]:
    """A schtasks local date + time (this machine's US-format CSV) -> aware UTC, else None."""
    if not task:
        return None
    s = f"{str(task.get(date_key) or '').strip()} {str(task.get(time_key) or '').strip()}".strip()
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt).astimezone().astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def not_due_yet(ctx, task: Optional[dict], cadence_h: float) -> tuple[Optional[str], Optional[str]]:
    """For a task the scheduler says has NEVER run (0x41303): (idle_reason, fault).
    Not due yet while its first trigger (`Start Date`/`Start Time`) + one cadence (with
    grace) is in the future; past that, never having run is a fault. An unparseable
    trigger is a fault with its reason (a guard derives its inputs or refuses)."""
    from backend.services import system_health as SH                # noqa: PLC0415
    if not _never_ran(task):
        return None, None
    first = _sched_local(task, "Start Date", "Start Time")
    if first is None:
        return None, (f"the task has never run and its first trigger "
                      f"({task.get('Start Date')!r} {task.get('Start Time')!r}) cannot be read")
    due_by = first + timedelta(hours=float(cadence_h) * (1 + SH.GRACE))
    if ctx.now < due_by:
        return (f"not due yet: the task has never run; its trigger starts {first:%Y-%m-%d %H:%M} UTC and "
                f"its next run is {task.get('Next Run Time')}", None)
    return None, (f"the task has NEVER run although its first trigger ({first:%Y-%m-%d %H:%M} UTC) "
                  f"is more than one cadence ago")


def _cadence(name: str) -> float:
    return float(_config.HEALTH_TASK_CADENCE_H.get(name, 24.0))


def r_event_nodes(ctx, task) -> Reading:
    """CH-35 `event_nodes daily` (every 30 min): `event_nodes/daily_latest.json`, the
    small receipt each run rewrites. A broken chain, a degraded input block (graph,
    forward calendar, catalyst calendar) or zero corpus rows read is DEGRADED."""
    out = ctx.optimus_dir / str(getattr(_config, "EVENT_NODES_DIRNAME", "event_nodes"))
    p = out / "daily_latest.json"
    where = f"{out.name}/daily_latest.json"
    if not p.exists():
        return _after_wrapper(ctx, _none(where), "scripts.event_nodes", ("daily",))
    d = _read(p)
    if not isinstance(d, dict):
        return Reading(unknown_reason=f"{where} exists but cannot be read as a JSON object", proof=where)
    t = parse_stamp(d.get("now"))
    bad = []
    chain = d.get("chain") if isinstance(d.get("chain"), dict) else {}
    if chain.get("ok") is not True:
        bad.append(f"chain.ok={chain.get('ok')} (n {chain.get('n')})")
    for blk in ("graph", "calendar", "catalyst_calendar"):
        b = d.get(blk) if isinstance(d.get(blk), dict) else {}
        if map_status(b.get("status") or "MISSING") != "OK":
            bad.append(f"{blk}={b.get('status') or 'missing'}")
    rows = (d.get("read") or {}).get("rows_read") if isinstance(d.get("read"), dict) else None
    if not rows:
        bad.append(f"rows_read={rows} (no corpus rows in the window)")
    rd = Reading(stamp=t, status="DEGRADED" if bad else "OK", reason="; ".join(bad),
                 proof=f"{where} now + chain.ok + input blocks",
                 detail=f"event nodes {d.get('build_id')}: {d.get('n_events')} events, "
                        f"+{d.get('appended_versions')} versions, chain n {chain.get('n')}")
    return _after_wrapper(ctx, rd, "scripts.event_nodes", ("daily",))


def r_forward_calendar(ctx, task) -> Reading:
    """CH-08 `forward_calendar pull` (daily): the newest FULL_UNIVERSE pull receipt
    (`forward_calendar/snapshots/fc_*_receipt.json`; a manual `--tickers`/`--limit` pull is
    PARTIAL and ignored). Its own `status` LOW_COVERAGE / LOW_DATE_SHARE is the CLI's rc 2
    refusal: REFUSED with both shares. rc 3 (SKIP_PULL_LOCKED: another pull held the
    lock) is a skip, not a failure."""
    snap = ctx.optimus_dir / str(getattr(_config, "FORWARD_CALENDAR_DIRNAME", "forward_calendar")) / "snapshots"
    p, d, unk = _newest_strict(snap, "fc_*_receipt.json", lambda r: r.get("scope") == "FULL_UNIVERSE")
    if unk:
        return Reading(unknown_reason=unk, proof=f"forward_calendar/snapshots/{p.name if p else ''}")
    args = ("forward_calendar", ("pull",), ("--tickers", "--limit"))
    if d is None:
        return _after_wrapper(ctx, _none("forward_calendar/snapshots/fc_*_receipt.json (scope FULL_UNIVERSE)"),
                              "scripts." + args[0], args[1], args[2], idle_rcs={3: "SKIP_PULL_LOCKED"})
    st = "OK" if d.get("status") == "OK" else "REFUSED"
    why = "" if st == "OK" else (
        f"{d.get('status')}: answered {d.get('answered')}/{d.get('requested')} (share {d.get('answered_share')}, "
        f"floor {d.get('min_answered_share')}), date share {d.get('date_share')} (floor {d.get('min_date_share')}), "
        f"earnings-fields share {d.get('earnings_fields_share')} (floor {d.get('min_earnings_fields_share')})")
    rd = Reading(stamp=parse_stamp(d.get("finished_utc")), status=st, reason=why,
                 proof=f"forward_calendar/snapshots/{p.name} finished_utc + status",
                 detail=f"forward calendar {d.get('pull_id')}: {d.get('with_date')} dated of "
                        f"{d.get('requested')}, status {d.get('status')}")
    return _after_wrapper(ctx, rd, "scripts." + args[0], args[1], args[2], idle_rcs={3: "SKIP_PULL_LOCKED"})


def r_owner_calls_record(ctx, task) -> Reading:
    """CH-01 `owner_calls record` (daily): `owner_calls/states.jsonl`, one sealed row per
    newly pinned day. The age of the newest `recorded_utc` is the check; a broken chain
    exits rc 2 with no row and is read from the wrapper."""
    p = ctx.optimus_dir / "owner_calls" / "states.jsonl"
    if not p.exists():
        return _after_wrapper(ctx, _none("owner_calls/states.jsonl"), "scripts.owner_calls", ("record",))
    row = _last_row(p)
    if row is None:
        return Reading(unknown_reason="owner_calls/states.jsonl holds no readable row", proof="owner_calls/states.jsonl")
    bad = [] if row.get("seal") and row.get("prev") else ["newest row carries no seal/prev"]
    rd = Reading(stamp=parse_stamp(row.get("recorded_utc")), status="DEGRADED" if bad else "OK",
                 reason="; ".join(bad), proof="owner_calls/states.jsonl[-1].recorded_utc",
                 detail=f"owner calls: newest pinned day {row.get('day')}")
    return _after_wrapper(ctx, rd, "scripts.owner_calls", ("record",))


def r_discovery_autopsy(ctx, task) -> Reading:
    """CH-13 `discovery_autopsy --daily`: the newest `discovery_autopsy/index.jsonl` row
    (session, run_id, summary.degradations). A run whose inputs are unchanged writes
    nothing, so the run_id stays put until a new session arrives (session-only cadence).
    Every AutopsyRefused is rc 2 with nothing written: read from the wrapper."""
    folder = ctx.optimus_dir / str(getattr(_config, "AUTOPSY_DAILY_DIRNAME", "discovery_autopsy"))
    p = folder / "index.jsonl"
    if not p.exists():
        return _after_wrapper(ctx, _none(f"{folder.name}/index.jsonl"), "scripts.discovery_autopsy", ("--daily",))
    row = _last_row(p)
    if row is None:
        return Reading(unknown_reason=f"{folder.name}/index.jsonl holds no readable row", proof=f"{folder.name}/index.jsonl")
    summ = row.get("summary") if isinstance(row.get("summary"), dict) else {}
    deg = summ.get("degradations") or []
    rd = Reading(stamp=parse_stamp(row.get("run_id")), status="DEGRADED" if deg else "OK",
                 reason=f"degradations: {deg}"[:200] if deg else "",
                 proof=f"{folder.name}/index.jsonl[-1].run_id",
                 detail=f"autopsy of session {row.get('session')} ({row.get('receipt')})")
    return _after_wrapper(ctx, rd, "scripts.discovery_autopsy", ("--daily",))


def _lab_window(day: date) -> tuple[datetime, datetime]:
    a, b = (_hhmm(x) for x in getattr(_config, "LAB_NIGHT_WINDOW_UTC", ("15:00", "22:15")))
    return datetime.combine(day, a, timezone.utc), datetime.combine(day, b, timezone.utc)


def r_lab_night(ctx, task) -> Reading:
    """The night lab (`always_on_lab --ticks 70`, 23:00-06:15 local = LAB_NIGHT_WINDOW_UTC).
    Its receipt is `lab_status.json`, written at the END of every tick. Inside the window
    the always_on_lab probe judges the live process; outside it, the last window must have
    written at least one tick. A night whose lock shows a start and whose status never
    moved is DEGRADED: the scheduler's 0x40010004 is the window-end kill, not the fault."""
    from backend.services import system_health as SH                # noqa: PLC0415
    d = _read(ctx.optimus_dir / "lab_status.json")
    lock = _read(ctx.optimus_dir / "always_on_lab_lock.json")
    marker = ctx.optimus_dir / str(getattr(_config, "ALWAYS_ON_LAB_OFF_MARKER", "always_on_lab_OFF"))
    if marker.exists():
        return Reading(stamp=ctx.now, status="STOPPED", reason=f"{marker.name} present (no launcher starts the lab)",
                       proof=marker.name, detail="night lab OFF by marker")
    if (ctx.optimus_dir / "lab_status.json").exists() and not isinstance(d, dict):
        return Reading(unknown_reason="lab_status.json exists but cannot be read as a JSON object",
                       proof="lab_status.json")
    utc = ctx.now.astimezone(timezone.utc)
    s0, e0 = _lab_window(utc.date())
    tick = parse_stamp((d or {}).get("utc"))
    started = parse_stamp((d or {}).get("started_utc"))
    lock_start = parse_stamp((lock or {}).get("started_utc")) if isinstance(lock, dict) else None
    grace = timedelta(minutes=float(getattr(_config, "LAB_NIGHT_FIRST_TICK_GRACE_MIN", 30)))
    lock_txt = (f"lock: pid {(lock or {}).get('pid')} started {lock_start:%Y-%m-%d %H:%M} UTC, previous exit "
                f"{(lock or {}).get('previous_exit_reason')}" if lock_start else "no readable lock")
    base = dict(proof="lab_status.json utc/started_utc/ticks + always_on_lab_lock.json")
    if s0 <= utc <= e0:
        if tick is not None and tick >= s0:
            r = SH.p_always_on_lab(ctx)
            st = "OK" if r.verdict == "ALIVE" else ("STOPPED" if r.verdict == "STOPPED_BY_OPERATOR" else "DEGRADED")
            return Reading(stamp=tick, status=st, reason="" if st == "OK" else r.detail, **base,
                           detail=f"night lab running: tick {(d or {}).get('ticks')} at {tick:%H:%M} UTC; {r.detail[:120]}")
        if utc - s0 <= grace:
            return Reading(stamp=None, idle_reason=f"the night window opened {SH._fmt_age((utc - s0).total_seconds())} "
                                                   f"ago; the first tick is not due yet", **base,
                           detail="night lab starting")
        return Reading(stamp=lock_start if lock_start and lock_start >= s0 - grace else tick, status="DEGRADED",
                       reason=(f"the night window opened at {s0:%H:%M} UTC and no tick has been written "
                               f"(newest lab_status tick {tick and f'{tick:%Y-%m-%d %H:%M}'}); {lock_txt}"),
                       **base, detail="night lab: no tick this window")
    day = utc.date() if utc > e0 else utc.date() - timedelta(days=1)
    s, e = _lab_window(day)
    if tick is not None and s <= tick <= e + timedelta(minutes=15) and started is not None and started >= s - grace:
        return Reading(stamp=tick, status="OK",
                       idle_reason=f"outside its night window {s:%H:%M}-{e:%H:%M} UTC (the last night produced)",
                       **base, detail=f"night lab {day}: {(d or {}).get('ticks')} ticks, last at {tick:%H:%M} UTC, "
                                      f"exit {(d or {}).get('previous_exit_reason') or 'see lock'}")
    in_window = lock_start is not None and s - grace <= lock_start <= e
    return Reading(stamp=lock_start if in_window else tick, status="DEGRADED",
                   reason=(f"the night window of {day} ({s:%H:%M}-{e:%H:%M} UTC) wrote no lab tick "
                           f"(newest lab_status tick {tick and f'{tick:%Y-%m-%d %H:%M}'} UTC); {lock_txt}"),
                   **base, detail="night lab: last window produced nothing")


def r_news_overlay(ctx, task) -> Reading:
    """CH-14b `news_overlay_book step`: the newest FORWARD row of
    `news_overlay_book/decisions.jsonl` (`written_utc`). `refused: true` (stale base bars)
    is REFUSED; a `degradation` (no/stale/empty digest, no baseline) is DEGRADED. The
    step's raised refusals (STALE_PANEL, outside the window) write no row: wrapper rc 2."""
    p = ctx.optimus_dir / "news_overlay_book" / "decisions.jsonl"
    args = ("scripts.news_overlay_book", ("step",), ("--date",))
    idle, fault = not_due_yet(ctx, task, _cadence("AegisNewsOverlayBook"))
    if not p.exists():
        rd = _none("news_overlay_book/decisions.jsonl (FORWARD rows)")
        rd.idle_reason = idle
        if fault:
            rd.detail += f"; {fault}"
        return _after_wrapper(ctx, rd, *args)
    row = _last_row(p, lambda r: r.get("label") == "FORWARD")
    if row is None:
        return Reading(unknown_reason="news_overlay_book/decisions.jsonl holds no readable FORWARD row",
                       proof="news_overlay_book/decisions.jsonl")
    st, why = "OK", ""
    if row.get("refused"):
        st, why = "REFUSED", f"refused: {row.get('degradation')}"
    elif row.get("degradation"):
        st, why = "DEGRADED", f"degradation {row.get('degradation')}"
    rd = Reading(stamp=parse_stamp(row.get("written_utc")), status=st, reason=why,
                 proof="news_overlay_book/decisions.jsonl[-1 FORWARD].written_utc",
                 detail=f"news overlay {row.get('session')}: scalar {row.get('scalar')}")
    return _after_wrapper(ctx, rd, *args)


#: llm_selector_book's exit codes: 2 refused, 3 DeepSeek budget refused, 4 flag off
SELECTOR_REFUSED_RCS = frozenset({2, 3, 4, 90})


def r_llm_selector(ctx, task) -> Reading:
    """The weekly LLM selector book (`llm_selector_book --decide`): the newer of
    `llm_selector/decisions.jsonl` and `llm_selector/refusals.jsonl` (each `written_utc`).
    A newer refusal is REFUSED with its code, except ALREADY_DECIDED for a date that
    already holds a decision (the goal is met). Until the scheduler has run it once, the
    rows are the brain's manual runs: the row certifies the data, not the task, and
    reads "not due yet" only until its first trigger + one cadence has passed."""
    folder = ctx.optimus_dir / "llm_selector"
    args = ("scripts.llm_selector_book", ("--decide",))
    dec = _last_row(folder / "decisions.jsonl") if (folder / "decisions.jsonl").exists() else None
    ref = _last_row(folder / "refusals.jsonl") if (folder / "refusals.jsonl").exists() else None
    if (folder / "decisions.jsonl").exists() and dec is None:
        return Reading(unknown_reason="llm_selector/decisions.jsonl holds no readable row",
                       proof="llm_selector/decisions.jsonl")
    t_d = parse_stamp((dec or {}).get("written_utc"))
    t_r = parse_stamp((ref or {}).get("written_utc"))
    idle, fault = not_due_yet(ctx, task, _cadence("AegisLLMSelectorBook"))
    if t_d is None and t_r is None:
        rd = _none("llm_selector/decisions.jsonl | refusals.jsonl")
        rd.idle_reason = idle
        if fault:
            rd.detail += f"; {fault}"
        return _after_wrapper(ctx, rd, *args, refused_rcs=SELECTOR_REFUSED_RCS)
    if t_r is not None and (t_d is None or t_r > t_d):
        code = str(ref.get("code"))
        if code == "ALREADY_DECIDED" and dec and dec.get("decision_date") == ref.get("decision_date"):
            rd = Reading(stamp=t_r, status="IDLE", reason=f"ALREADY_DECIDED for {ref.get('decision_date')}",
                         idle_reason=f"a decision for {ref.get('decision_date')} already exists",
                         proof="llm_selector/refusals.jsonl[-1]", detail="llm selector: already decided")
        else:
            rd = Reading(stamp=t_r, status="REFUSED", reason=f"{code}: {str(ref.get('detail'))[:160]}",
                         proof="llm_selector/refusals.jsonl[-1].written_utc",
                         detail=f"llm selector refused {code}")
    else:
        rd = Reading(stamp=t_d, proof="llm_selector/decisions.jsonl[-1].written_utc",
                     detail=f"llm selector decision {dec.get('decision_date')} (entry {dec.get('entry_session')})")
    if _never_ran(task):
        rd.never_by_task = True
        if idle:
            rd.idle_reason = (f"{idle}; the newest row is from a MANUAL run -- the row certifies the data, "
                              f"not the task")
        elif rd.status in ("OK", "IDLE"):
            rd.status, rd.reason = "DEGRADED", f"{fault}; the rows are from manual runs"
    return _after_wrapper(ctx, rd, *args, refused_rcs=SELECTOR_REFUSED_RCS)


def r_system_status(ctx, task) -> Reading:
    """The systems page itself (`system_status --html`, every 15 min): its own
    `system_status/status.json` (`generated_utc`, `exit_code`). Exit 3 means "collected,
    some rows undetermined"; those rows are red on their own, so this job's row is OK
    with the count and never DOWN for them (no self-referential loop)."""
    p = ctx.optimus_dir / "system_status" / "status.json"
    if not p.exists():
        return _none("system_status/status.json")
    d = _read(p)
    if not isinstance(d, dict):
        return Reading(unknown_reason="system_status/status.json exists but cannot be read as a JSON object",
                       proof="system_status/status.json")
    rc = d.get("exit_code")
    und = d.get("undetermined") or []
    st, why = ("OK", "") if rc in (0, 3) else ("DEGRADED", f"exit_code={rc}")
    if d.get("schema") not in (None, "system_status/1") and st == "OK":
        st, why = "DEGRADED", f"unexpected schema {d.get('schema')}"
    return Reading(stamp=parse_stamp(d.get("generated_utc")), status=st, reason=why,
                   proof="system_status/status.json generated_utc + exit_code",
                   detail=f"status receipt exit {rc}; counts {d.get('counts')}"
                          + (f"; {len(und)} row(s) undetermined (their own rows are judged)" if und else ""))


#: the keyless SEC raw collector's own words (raw_collection_once.py `controls`)
RAW_SEC_YIELDS = frozenset({"CORPUS_WRITER_ACTIVE", "IIF_LAUNCH_WINDOW"})
RAW_SEC_STOPS = frozenset({"RAW_COLLECTION_STOP", "BETA_COORDINATOR_STOP"})
RAW_SEC_SCAN = 48


def r_raw_sec(ctx, task) -> Reading:
    """The hourly keyless SEC 8-K Ex-99 collector, a hash-pinned recovery-evidence
    harness (`run_raw_collection.ps1` -> `raw_collection_once.py`). Its receipts are
    `<harness>/receipts/<stamp>_<pid>.json`. A yield to another corpus writer or the IIF
    launch window is skipped (judged by the newest non-yield receipt, so a yield neither
    flaps red nor hides an older failure); a backoff SKIP is DEGRADED; REFUSED is REFUSED."""
    default = (ctx.repo.parent / "aegis-recovery-evidence" / "oct15-clean-recovery-20261015"
               / "oct15-sec-cursor-runtime-r6" / "receipts")
    folder = ctx.path("raw_sec_receipts", default)
    try:
        files = sorted(folder.glob("2*_*.json"))
    except OSError:
        files = []
    if not files:
        return _none(str(folder / "<stamp>_<pid>.json"))
    yields = []
    for p in reversed(files[-RAW_SEC_SCAN:]):
        d = _read(p)
        if not isinstance(d, dict):
            return Reading(unknown_reason=f"receipt {p.name} cannot be read as a JSON object", proof=str(p))
        status, reason = str(d.get("status")), str(d.get("reason"))
        t = parse_stamp(d.get("written_utc") or d.get("started_utc"))
        if status == "REFUSED" and reason in RAW_SEC_YIELDS:
            yields.append((t, reason))
            continue
        note = f"; {len(yields)} newer yield(s) ({yields[0][1]})" if yields else ""
        if status == "REFUSED" and reason in RAW_SEC_STOPS:
            st, why = "STOPPED", f"{reason} present"
        elif status == "OK":
            st, why = "OK", ""
        elif status == "SKIPPED":
            st, why = "DEGRADED", f"SKIPPED {reason} after {d.get('consecutive_failures')} consecutive failure(s)"
        else:
            st, why = map_status(status) if status != "REFUSED" else "REFUSED", f"{status} {reason}"
        return Reading(stamp=t, status=st, reason=why, proof=f"{folder.name}/{p.name} written_utc",
                       detail=f"raw SEC collection {status} {reason}: {d.get('rows_new')} new rows{note}")
    t = yields[-1][0] if yields else None
    return Reading(stamp=t, status="IDLE", idle_reason=f"every one of the newest {len(yields)} receipts yielded",
                   proof=str(folder), detail=f"raw SEC collection yielded ({yields[0][1] if yields else ''})")


#: owner_warning_once.ps1's journal words
OWNER_WARNING_OK = frozenset({"PROVISIONAL", "NO_HELD_EVENT"})
OWNER_WARNING_NO_RECEIPT_WHY = (
    "NO_RUNNER_RECEIPT: the runner printed nothing and the harness could not read its exit code "
    "(Windows PowerShell 5.1 Start-Process -PassThru leaves .ExitCode null after WaitForExit(ms), "
    "measured 2026-11-14), so 'no held event' and a silent failure both land here and the task "
    "exits 2; the harness, not the warning, is what this row reports")


def r_owner_warning(ctx, task) -> Reading:
    """The owner event warning harness (`owner_warning_once.ps1`, every 10 min): its own
    journal `owner_warning_journal/owner_warning_runs.jsonl`. One run may write several
    rows with the same `at_utc`; the run's status is the worst of them."""
    default = (ctx.repo.parent / "aegis-recovery-evidence" / "beta-v2-owner-20261025" / "continuation-20261103"
               / "owner_warning_journal" / "owner_warning_runs.jsonl")
    p = ctx.path("owner_warning_runs", default)
    from backend.services import system_health as SH                # noqa: PLC0415
    lines = SH._tail_lines(p, 65536)
    if not lines:
        return _none(str(p))
    rows = []
    for ln in lines:
        try:
            r = json.loads(ln.lstrip("﻿"))
        except ValueError:
            continue
        if isinstance(r, dict):
            rows.append(r)
    if not rows:
        return Reading(unknown_reason="owner_warning_runs.jsonl holds no readable row", proof=str(p))
    at = rows[-1].get("at_utc")
    run = [r for r in rows if r.get("at_utc") == at]
    st, why = "OK", []
    for r in run:
        s = str(r.get("status"))
        if s in OWNER_WARNING_OK:
            continue
        if s == "DEFERRED_IIF_WINDOW":
            st = worst(st, "IDLE")
        elif s == "NO_RUNNER_RECEIPT":
            st = worst(st, "DEGRADED")
            why.append(OWNER_WARNING_NO_RECEIPT_WHY)
        elif s == "REFUSED":
            st = worst(st, "REFUSED")
            why.append(f"REFUSED {r.get('reason')}")
        else:
            st = worst(st, "DEGRADED")
            why.append(s)
    return Reading(stamp=parse_stamp(at), status=st, reason="; ".join(why),
                   idle_reason="deferred: inside the IIF launch window" if st == "IDLE" else None,
                   proof=f"{p.name}[-1].at_utc",
                   detail=f"owner warning run: {', '.join(sorted({str(r.get('status')) for r in run}))}")


def r_no_receipt(why: str):
    def reader(ctx, task) -> Reading:
        return Reading(unknown_reason=why)
    return reader


def r_retired(ctx, task) -> Reading:
    return Reading(detail="retired one-shot")


TASK_RECEIPT: dict[str, TaskSpec] = {
    "AegisDailyPass": TaskSpec(r_daily_pass, "night_factory_<d>/daily_pass_<d>.json"),
    "AegisIIF1NightLauncher": TaskSpec(_delegate("p_iif1_night", "iif1_night"), "iif1_nights/<weekday>.json",
                                       hash_off="judged by the iif1_night probe (weekday-aware)"),
    "AegisNNLabNightly": TaskSpec(r_nn_lab, "nightly_receipt_contract over nn_lab/receipts/nightly_*.json",
                                  hash_off="the shared nightly contract judges status and age"),
    "AegisSimOwner": TaskSpec(r_sim_owner, "sim/owner.jsonl",
                              hash_off="the owner's row is legitimately constant while one session runs; "
                                       "the session itself is the sim_session row"),
    "AegisDataCatalog": TaskSpec(r_catalog, "data_catalog/catalog_*.json + task_keeper/opportunities.jsonl "
                                            "(opportunities_build, C15) + task_keeper/publish_receipts.jsonl "
                                            "(public_receipts, C15)"),
    "AegisContestRehearsal": TaskSpec(r_rehearsal, "contest/rehearsal/runs.jsonl"),
    "AegisContestDesk": TaskSpec(r_contest_desk, "contest/live/runs.jsonl | contest/live/refusals/live_gate_*.json",
                                 session_only=True),
    "AegisHypLabNightly": TaskSpec(r_hyp_lab, "hyp_lab/receipts/nightly_*.json"),
    "AegisWorldDigest": TaskSpec(r_world_digest, "digest/world_digest_*.json"),
    "AegisLocalRuntimeDigest": TaskSpec(r_local_runtime_digest,
                                        "local_runtime_digest/digest_*.json", registered_only=True),
    "AegisLocalBranchingPrivateGrade": TaskSpec(r_local_branching_private_grade,
        "~/aegis-recovery-evidence/oct14-continuation-20261014/local-branching/automation_runs.jsonl",
        registered_only=True, cadence_h=2.0),
    "AegisAlerts": TaskSpec(r_alerts, "alerts/receipts/alert_pass_*.json",
                            hash_off="a quiet market legitimately repeats the same pass; its own state "
                                     "and bars_health are read instead"),
    "AegisStraddleForward": TaskSpec(r_straddle, "straddle_forward/runs/pass_*.json", session_only=True,
                                     window_cfg=("STRADDLE_FWD_ENTRY_START_ET", "STRADDLE_FWD_ENTRY_END_ET")),
    "AegisFleetManagerOpen": TaskSpec(_fleet_pass("open"), "paper_accounts/fleet_manager/runs/run_* (pass open)",
                                      session_only=True),
    "AegisFleetManagerPreclose": TaskSpec(_fleet_pass("preclose"),
                                          "paper_accounts/fleet_manager/runs/run_* (pass preclose)",
                                          session_only=True),
    "AegisFleetProtectSweep": TaskSpec(
        r_fleet_sweep, "paper_accounts/fleet_manager/sweeps/sweep_*.json",
        session_only=True,
        hash_off="each eligible repeat is a new broker coverage observation",
        window_utc=("15:05", "19:05")),
    "AegisFleetDailyCheck": TaskSpec(r_fleet_daily, "paper_accounts/fleet_daily/fleet_*.json"),
    "AegisReaderSupervisor": TaskSpec(r_reader, "dowjones/night_reader_supervisor.jsonl (tick)"),
    "AegisCatchUp": TaskSpec(r_catchup, "task_keeper/keeper.jsonl (job catchup)",
                             hash_off="an all-'ok' catch-up row is the healthy steady state"),
    "AegisTelegramAgent": TaskSpec(_delegate("p_telegram_agent", "telegram_agent"),
                                   "telegram/heartbeat.json + agent pid",
                                   hash_off="judged by the telegram_agent probe (pid + heartbeat)"),
    "AegisAnalystPanelDaily": TaskSpec(r_analyst_panel, "aegis-alpha-terminal state/research/analyst_panel/<date>.jsonl",
                                       session_only=True,
                                       hash_off="a daily snapshot of a slow consensus can repeat; age and row "
                                                "count are the checks"),
    "AegisAnalystPull": TaskSpec(r_analyst_pull, "analyst/analyst_pull_<day>.json | task_keeper/analyst.jsonl",
                                 hash_off="weekly; age and n_snapshots are the checks"),
    "AegisBrainRefresh": TaskSpec(r_brain, "task_keeper/brain.jsonl",
                                  hash_off="the brain page's own stamp is the optimus_brain row"),
    "AegisPublicFlow": TaskSpec(r_public_flow, "task_keeper/public_flow.jsonl (+ public_flow/receipts/)",
                                hash_off="each step's own receipt carries rows_added; the job row is a summary",
                                unregistered_ok="C16 public-flow sensors: registration waits for its review"),
    "AegisResearchLane": TaskSpec(r_research_lane, "research_instruments/probe_<run_id>.json "
                                                   "(+ task_keeper/research_lane.jsonl)",
                                 hash_off="weekly; most weeks are a declared not_due no-op, judged idle "
                                          "not stale",
                                 unregistered_ok="Q12 academic lane: registration waits for owner review "
                                                 "(python -m scripts.task_keeper register-owners --apply)"),
    "AegisPublicAssetsWeekly": TaskSpec(
        r_assets, "task_keeper/assets.jsonl (+ paper_accounts/public_assets_refresh_<run_id>.json "
                 "on a successful bump)",
        hash_off="weekly; most weeks are correctly 'nothing newer to pin', which repeats the same "
                "substance by design",
        unregistered_ok="2026-10-07: public-assets weekly refresh, printed by `register`; "
                        "registration waits for owner review (python -m scripts.task_keeper "
                        "register --apply)"),
    "AegisWRDSPullNight": TaskSpec(r_retired, "none (retired one-shot, 2026-08-21)", retired=True),
    # ── S69 (2026-11-14): the tasks added 11-11 .. 11-14, each judged by its own receipt
    "AegisEventNodes": TaskSpec(
        r_event_nodes, "event_nodes/daily_latest.json (+ runtime_switch/runtime_task_runs.jsonl rc)",
        hash_off="every 30 min; a quiet window legitimately repeats the counts; chain and input blocks are read"),
    "AegisForwardCalendar": TaskSpec(
        r_forward_calendar, "forward_calendar/snapshots/fc_<stamp>_receipt.json, scope FULL_UNIVERSE "
                            "(+ runtime_task_runs.jsonl rc)",
        hash_off="daily; status and both shares are read"),
    "AegisOwnerCallsRecord": TaskSpec(
        r_owner_calls_record, "owner_calls/states.jsonl (+ runtime_task_runs.jsonl rc)",
        hash_off="a row is written only when a new day is pinned; its recorded_utc is the check"),
    "AegisDiscoveryAutopsy": TaskSpec(
        r_discovery_autopsy, "discovery_autopsy/index.jsonl (+ runtime_task_runs.jsonl rc)", session_only=True,
        hash_off="an unchanged-input run writes nothing; the run_id's age is the check"),
    "AegisRawSecCollection": TaskSpec(
        r_raw_sec, "~/aegis-recovery-evidence/oct15-clean-recovery-20261015/oct15-sec-cursor-runtime-r6/"
                   "receipts/<stamp>_<pid>.json",
        hash_off="hourly; a caught-up source legitimately repeats CAUGHT_UP_*"),
    "AegisLabNight": TaskSpec(
        r_lab_night, "lab_status.json (+ always_on_lab_lock.json), inside LAB_NIGHT_WINDOW_UTC",
        hash_off="judged per night window: a tick inside the window, or the last window produced"),
    "AegisNewsOverlayBook": TaskSpec(
        r_news_overlay, "news_overlay_book/decisions.jsonl FORWARD rows (+ runtime_task_runs.jsonl rc)",
        session_only=True, window_cfg=("NEWS_OVERLAY_TASK_WINDOW_START_ET", "NEWS_OVERLAY_TASK_WINDOW_END_ET"),
        hash_off="one row per session; its written_utc is the check"),
    "AegisLLMSelectorBook": TaskSpec(
        r_llm_selector, "llm_selector/decisions.jsonl | llm_selector/refusals.jsonl (+ runtime_task_runs.jsonl rc)",
        hash_off="weekly; one decision per decision_date"),
    "AegisSystemStatus": TaskSpec(
        r_system_status, "system_status/status.json generated_utc + exit_code",
        hash_off="the page's counts legitimately repeat; its stamp and exit code are the check"),
    "AegisOwnerEventWarning": TaskSpec(
        r_owner_warning, "~/aegis-recovery-evidence/beta-v2-owner-20261025/continuation-20261103/"
                         "owner_warning_journal/owner_warning_runs.jsonl",
        hash_off="every 10 min; a quiet book legitimately repeats the same status"),
    "AegisCodexDaemonAtLogon": TaskSpec(
        r_retired, "none (retired: Codex-month leftover, Disabled since 2026-11-07; starts the Codex app-server "
                   "daemon at logon, which nothing on main consumes)", retired=True),
    "AegisAlwaysOnLab": TaskSpec(_delegate("p_always_on_lab", "always_on_lab"),
                                 "lab_status.json (judged by the always_on_lab probe)",
                                 hash_off="judged by the always_on_lab probe (pid + OFF marker)",
                                 registered_only=True),
    "AegisNightPreOpen": TaskSpec(r_no_receipt(
        "scripts.night_cache_sentinel --before prints and writes NO receipt; night_schedule_plan "
        "only prints this registration. Give the sentinel a receipt before registering it."),
        "none: night_cache_sentinel writes no receipt", registered_only=True),
    "AegisNetworkResume": TaskSpec(r_no_receipt(
        "registered by local_pc/network_resume.ps1, which writes no receipt; give it one before "
        "it can be judged"), "none: network_resume.ps1 writes no receipt", registered_only=True),
    # Not Aegis-prefixed, but part of this stack and running (review: keep it visible)
    "OpenClaw Gateway": TaskSpec(_delegate("p_openclaw_gateway", "openclaw_gateway"),
                                 "`openclaw gateway status` (judged by the openclaw_gateway probe)",
                                 hash_off="judged by the openclaw_gateway probe (runtime + reader proof)",
                                 registered_only=True),
}

#: scheduler names outside the `Aegis*` prefix that the probe still reads
EXTRA_TASK_NAMES = tuple(n for n in TASK_RECEIPT if not n.startswith("Aegis"))


# ═══════════════════════════════════════════════════════════════ judging

def _non_session_days(after: date, upto: date) -> int:
    from backend.services import system_health as SH                # noqa: PLC0415
    if upto <= after:
        return 0
    sess, _ = SH._sessions(after + timedelta(days=1), upto)
    return (upto - after).days - len(sess)


def allowed_age_s(name: str, spec: TaskSpec, stamp: Optional[datetime], now: datetime) -> float:
    from backend.services import system_health as SH                # noqa: PLC0415
    cad_h = float(spec.cadence_h if spec.cadence_h is not None
                  else _config.HEALTH_TASK_CADENCE_H.get(name, 24.0))
    allowed = cad_h * 3600 * (1 + SH.GRACE)
    if spec.session_only and not spec.window_utc and stamp is not None:
        allowed += 86400 * _non_session_days(SH._et(stamp).date(), SH._et(now).date())
    return allowed


def _hhmm(s: str) -> dtime:
    h, m = str(s).split(":")[:2]
    return dtime(int(h), int(m))


def _sweep_window(day: date) -> Optional[tuple[datetime, datetime, datetime]]:
    """First/final eligible scheduled UTC tick and authoritative XNYS close."""
    try:
        import exchange_calendars as xc                            # noqa: PLC0415
        cal = xc.get_calendar("XNYS", start="2015-01-01", end="2035-12-31")
        if not cal.is_session(day.isoformat()):
            return None
        close = cal.session_close(day.isoformat()).to_pydatetime().astimezone(timezone.utc)
    except Exception:                                               # noqa: BLE001
        return None  # no weekday approximation can certify a session/half-day close
    first = datetime.combine(day, dtime(15, 5), timezone.utc)
    ny_cutoff = datetime.combine(day, dtime(15, 15), ZoneInfo("America/New_York")).astimezone(timezone.utc)
    bound = min(datetime.combine(day, dtime(19, 5), timezone.utc),
                datetime.combine(day, dtime(19, 15), timezone.utc), ny_cutoff,
                close - timedelta(minutes=_config.FLEET_MANAGER_MIN_MINUTES_TO_CLOSE + 3))
    if first > bound:
        return None
    last = first + timedelta(minutes=15 * int((bound - first).total_seconds() // 900))
    return first, last, close


def window_status(spec: TaskSpec, stamp: Optional[datetime], now: datetime,
                  allowed: float, run_start: Optional[datetime] = None) -> Optional[tuple[str, str]]:
    """For a windowed producer (review F4): None when `now` is inside today's
    window and past its first cadence (judge normally); else (state, text):
    idle-expected when the newest receipt comes from the last window, STALE when
    the last window produced nothing."""
    if spec.window_utc:
        utc = now.astimezone(timezone.utc)
        try:
            import exchange_calendars as xc                        # noqa: PLC0415
            cal = xc.get_calendar("XNYS", start="2015-01-01", end="2035-12-31")
            days = [s.date() for s in cal.sessions_in_range(
                (utc.date() - timedelta(days=14)).isoformat(), utc.date().isoformat())]
        except Exception:                                           # noqa: BLE001
            return ("STALE", "XNYS session/close calendar unavailable for sweep cadence")
        today = _sweep_window(utc.date())
        if today and today[0] <= utc <= today[1] + timedelta(seconds=allowed) and (
                run_start is not None and run_start >= today[0] or utc > today[0] + timedelta(seconds=allowed)):
            return None
        completed = [d for d in days if d < utc.date() or
                     (d == utc.date() and today is not None and utc > today[1] + timedelta(seconds=allowed))]
        if not completed:
            return ("STALE", "no completed XNYS sweep window in 14 days")
        last_day = completed[-1]
        window = _sweep_window(last_day)
        if window is None:
            return ("STALE", "last XNYS sweep window cannot be established")
        _, last, close = window
        if (run_start is not None and last <= run_start <= last + timedelta(minutes=3)
                and stamp is not None and run_start <= stamp <= min(close - timedelta(
                    minutes=_config.FLEET_MANAGER_MIN_MINUTES_TO_CLOSE), run_start + timedelta(minutes=3))):
            return ("ALIVE_IDLE_EXPECTED", f"outside eligible sweep window; final tick {last:%H:%M} UTC "
                                            f"on {last_day} produced")
        return ("STALE", f"last eligible sweep tick ({last_day} {last:%H:%M} UTC) produced no receipt")
    if not spec.window_cfg:
        return None
    from backend.services import system_health as SH                # noqa: PLC0415
    start = _hhmm(getattr(_config, spec.window_cfg[0]))
    end = _hhmm(getattr(_config, spec.window_cfg[1]))
    et = SH._et(now)
    tz = et.tzinfo
    days, _ = SH._sessions(et.date() - timedelta(days=14), et.date())
    today_open = bool(days) and days[-1] == et.date()
    win = f"{start:%H:%M}-{end:%H:%M} ET"
    if today_open and start <= et.time() <= end:
        opened = datetime.combine(et.date(), start, tz)
        if (et - opened).total_seconds() > allowed:
            return None
        prev = [d for d in days if d < et.date()]
    else:
        prev = [d for d in days if d < et.date() or (d == et.date() and et.time() > end)]
    if not prev:
        return ("ALIVE_IDLE_EXPECTED", f"outside its declared window {win}; no session in 14 days")
    last_close = datetime.combine(prev[-1], end, tz)
    if stamp is not None and stamp >= last_close - timedelta(seconds=allowed):
        return ("ALIVE_IDLE_EXPECTED", f"outside its declared window {win} (last window {prev[-1]} "
                                       f"produced; next window on the next session)")
    return ("STALE", f"the last window ({prev[-1]} {win}) produced no receipt"
                     + (f"; newest is {SH._fmt_age(SH._age(stamp, now))} old" if stamp else ""))


def _progress(ctx, name: str, sub: Optional[str]) -> tuple[int, Optional[datetime]]:
    """Record the substance hash; return (consecutive probes with it, first seen)."""
    from backend.services import system_health as SH                # noqa: PLC0415
    prog = ctx.new_state.setdefault("progress", dict(ctx.prev_state.get("progress") or {}))
    if sub is None:
        prog.pop(name, None)
        return 0, None
    h = hashlib.sha256(sub.encode("utf-8")).hexdigest()[:16]
    prev = prog.get(name) or {}
    if prev.get("hash") == h:
        rec = {"hash": h, "first_seen_utc": prev.get("first_seen_utc") or SH._iso(ctx.now),
               "n_same": int(prev.get("n_same") or 1) + 1}
    else:
        rec = {"hash": h, "first_seen_utc": SH._iso(ctx.now), "n_same": 1}
    prog[name] = rec
    return rec["n_same"], parse_stamp(rec["first_seen_utc"])


def _today_idle(spec: TaskSpec, now: datetime) -> Optional[str]:
    if not spec.session_only:
        return None
    from backend.services import system_health as SH                # noqa: PLC0415
    et = SH._et(now)
    sess, _ = SH._sessions(et.date(), et.date())
    return None if sess else f"no XNYS session on {et.date()} (declared idle: session-only task)"


@dataclass
class Judgement:
    state: str
    detail: str
    stamp: Optional[datetime] = None
    proof: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def verdict(self) -> str:
        return COARSE[self.state]


def _disabled_marker(ctx, name: str) -> Optional[str]:
    p = ctx.optimus_dir.joinpath(*DISABLED_MARKER_DIR) / name
    try:
        return p.read_text(encoding="utf-8").strip() or "no reason written" if p.exists() else None
    except OSError:
        return None


def judge(ctx, name: str, task: Optional[dict], spec: Optional[TaskSpec] = None) -> Judgement:
    """One task -> one state. `task` is the schtasks row (None = not registered)."""
    j = _judge(ctx, name, task, spec)
    # THE invariant (review F1): no ALIVE_* state over a reading that failed is
    # enforced inside `_judge`; this asserts it so a future branch cannot slip.
    assert j.state in STATES, j.state
    return j


def _judge(ctx, name: str, task: Optional[dict], spec: Optional[TaskSpec]) -> Judgement:
    from backend.services import system_health as SH                # noqa: PLC0415
    spec = spec or TASK_RECEIPT.get(name)
    if spec is None:
        return Judgement("UNKNOWN", f"no receipt is declared for {name}: add it to "
                                    f"task_receipts.TASK_RECEIPT")
    if spec.retired:
        return Judgement("DEGRADED", f"retired task still registered ({spec.receipt}); delete it: "
                                     f"schtasks /Delete /TN {name} /F", proof="task_receipts.TASK_RECEIPT retired")
    unreg = task is None
    if unreg and spec.unregistered_ok:
        return Judgement("UNREGISTERED", f"declared, not registered on purpose: {spec.unregistered_ok}",
                         proof=spec.receipt)
    disabled = task is not None and str(task.get("Scheduled Task State")) == "Disabled"
    if disabled:
        marker = _disabled_marker(ctx, name)
        if marker is not None:
            return Judgement("STOPPED_BY_OPERATOR", f"Disabled by the owner: {marker[:200]}",
                             proof="/".join(DISABLED_MARKER_DIR) + f"/{name}")
    try:
        rd = spec.reader(ctx, task)
    except Exception as exc:                                          # noqa: BLE001
        return Judgement("UNKNOWN", f"receipt reader raised {type(exc).__name__}: {str(exc)[:160]}")
    t, now = rd.stamp, ctx.now
    age = SH._age(t, now)
    proof = rd.proof or spec.receipt
    owner = "" if not unreg else "; NO scheduled task by this name -- nothing writes the next receipt"
    if rd.unknown_reason:
        return Judgement("UNKNOWN", rd.unknown_reason, proof=proof)
    allowed = allowed_age_s(name, spec, t, now)
    age_txt = f"newest receipt {SH._fmt_age(age)} old (allowed {SH._fmt_age(allowed)})"
    if disabled:
        return Judgement("STALE", f"the task is Disabled and no owner marker "
                                  f"({'/'.join(DISABLED_MARKER_DIR)}/{name}) says why; "
                                  + (age_txt if t else "no receipt"), t, proof)
    if rd.status == "STOPPED":
        return Judgement("STOPPED_BY_OPERATOR", rd.reason or rd.detail, t, proof)
    if rd.delegated is not None:
        v = rd.delegated
        state = {"ALIVE": "ALIVE_PROGRESSING", "STALE": "STALE", "DEAD": "DEAD", "REFUSED": "REFUSED",
                 "UNKNOWN": "UNKNOWN", "STOPPED_BY_OPERATOR": "STOPPED_BY_OPERATOR"}.get(v, "UNKNOWN")
        if state == "ALIVE_PROGRESSING" and unreg:
            state = "DEGRADED"
        if state == "UNKNOWN":
            state = "DEAD" if unreg else "STALE"
            return Judgement(state, f"scheduled, but no derivable receipt -- {rd.detail}" + owner, t, proof)
        return Judgement(state, rd.detail + owner, t, proof)
    if t is None:
        if rd.idle_reason:
            return Judgement("ALIVE_IDLE_EXPECTED", f"no receipt yet; {rd.idle_reason}" + owner, None, proof)
        if unreg:
            return Judgement("DEAD", f"{rd.detail}{owner}", None, proof)
        return Judgement("STALE", f"{rd.detail}: the task is scheduled but has not written its receipt "
                                  f"(Last Run {task.get('Last Run Time')})", None, proof)
    if rd.status == "DEAD":
        return Judgement("DEAD", f"{rd.reason[:220]}; {rd.detail} ({SH._fmt_age(age)} ago)" + owner, t, proof)
    ws = window_status(spec, t, now, allowed, rd.run_start)
    too_old = age is not None and age > allowed
    if ws is not None and rd.status in ("OK", "IDLE"):
        if ws[0] == "STALE" and unreg:
            return Judgement("DEAD", f"{ws[1]}{owner}", t, proof)
        if ws[0] == "STALE" or not unreg:
            return Judgement(ws[0], f"{ws[1]}; {rd.detail}" + owner, t, proof)
    elif too_old:
        if rd.status == "REFUSED":
            return Judgement("DEAD" if unreg else "STALE",
                             f"newest receipt is an OLD refusal ({rd.reason[:120]}); {age_txt}" + owner, t, proof)
        return Judgement("DEAD" if unreg else "STALE", f"{age_txt}; {rd.detail}{owner}", t, proof)
    if rd.status == "REFUSED":
        return Judgement("REFUSED", f"{rd.reason[:220]} ({SH._fmt_age(age)} ago)" + owner, t, proof)
    if rd.status == "DEGRADED":
        return Judgement("DEGRADED", f"{rd.reason[:220]}; {rd.detail} ({SH._fmt_age(age)} ago)" + owner, t, proof)
    # from here on the reading's own status is OK or IDLE
    n_same, first = _progress(ctx, name, rd.substance)
    idle = rd.idle_reason or (f"producer idle: {rd.reason}" if rd.status == "IDLE" else None) \
        or _today_idle(spec, now)
    if (rd.substance is not None and n_same >= int(_config.HEALTH_PROGRESS_SAME_HASH_PROBES)
            and first is not None and (now - first).total_seconds() > allowed and not idle):
        return Judgement("STALE", f"same output for {SH._fmt_age((now - first).total_seconds())} across "
                                  f"{n_same} probes (allowed {SH._fmt_age(allowed)}), though the stamp "
                                  f"moved; {rd.detail}" + owner, t, proof,
                         extra={"same_hash_probes": n_same})
    if unreg:
        return Judgement("DEGRADED", f"receipt fresh ({SH._fmt_age(age)}) but{owner[1:]}; {rd.detail}", t, proof)
    if idle:
        return Judgement("ALIVE_IDLE_EXPECTED", f"{idle}; {rd.detail} ({SH._fmt_age(age)} ago)", t, proof)
    hash_note = f" [hash rule off: {spec.hash_off}]" if rd.substance is None and spec.hash_off else ""
    return Judgement("ALIVE_PROGRESSING", f"{rd.detail} ({SH._fmt_age(age)} ago){hash_note}", t, proof)
