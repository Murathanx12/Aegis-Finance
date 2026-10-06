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
    if s.startswith("REFUS") or s.startswith("BLOCKED"):
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
    return Reading(stamp=parse_stamp(d.get("utc") or d.get("run_id")), status=st, reason=why,
                   substance=substance(d.get("summary")), idle_reason=_declared_idle(d),
                   proof=f"data_catalog/{p.name} utc",
                   detail=f"catalog {p.name}: {str(d.get('summary'))[:120]}")


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
                return Reading(stamp=parse_stamp(d.get("finished_utc") or d.get("started_utc")),
                               status=worst(st0, st), reason="; ".join(x for x in (why0, why) if x),
                               substance=substance([{k: a.get(k) for k in ("role", "status", "equity")}
                                                    for a in d.get("accounts") or [] if isinstance(a, dict)]),
                               proof=f"fleet_manager/runs/{p.name} accounts[*].status",
                               detail=f"fleet manager {which} pass {p.name}"
                                      + (f"; retired, excused by config: {excused}" if excused else ""))
        return _none(f"paper_accounts/fleet_manager/runs/run_*.json with pass={which}")
    return reader


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
    "AegisDataCatalog": TaskSpec(r_catalog, "data_catalog/catalog_*.json"),
    "AegisContestRehearsal": TaskSpec(r_rehearsal, "contest/rehearsal/runs.jsonl"),
    "AegisContestDesk": TaskSpec(r_contest_desk, "contest/live/runs.jsonl | contest/live/refusals/live_gate_*.json",
                                 session_only=True),
    "AegisHypLabNightly": TaskSpec(r_hyp_lab, "hyp_lab/receipts/nightly_*.json"),
    "AegisWorldDigest": TaskSpec(r_world_digest, "digest/world_digest_*.json"),
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
    "AegisWRDSPullNight": TaskSpec(r_retired, "none (retired one-shot, 2026-08-21)", retired=True),
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
    cad_h = float(_config.HEALTH_TASK_CADENCE_H.get(name, 24.0))
    allowed = cad_h * 3600 * (1 + SH.GRACE)
    if spec.session_only and stamp is not None:
        allowed += 86400 * _non_session_days(SH._et(stamp).date(), SH._et(now).date())
    return allowed


def _hhmm(s: str) -> dtime:
    h, m = str(s).split(":")[:2]
    return dtime(int(h), int(m))


def window_status(spec: TaskSpec, stamp: Optional[datetime], now: datetime,
                  allowed: float) -> Optional[tuple[str, str]]:
    """For a windowed producer (review F4): None when `now` is inside today's
    window and past its first cadence (judge normally); else (state, text):
    idle-expected when the newest receipt comes from the last window, STALE when
    the last window produced nothing."""
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
    ws = window_status(spec, t, now, allowed)
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
