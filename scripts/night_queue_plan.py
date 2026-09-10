"""NIGHT QUEUE PLAN -- tomorrow's `NIGHT_QUEUE`, derived from tonight's receipts.

    python -m scripts.night_queue_plan                 # write the plan receipt, print the paste line
    python -m scripts.night_queue_plan --dry-run       # print it, write nothing
    python -m scripts.night_queue_plan --dirs 3        # read the three most recent nights

IT PLANS. IT RUNS NOTHING.
==========================
This module has no `subprocess`, no order path, no seal, no arm, and it never
imports the broker. It reads receipts, derives a proposed queue, writes ONE
receipt and appends ONE observation to `learner/evidence_memory.jsonl`. The
receipt carries `requires_human_veto: true` because a machine that can both
propose the next night and start it has closed the only loop that was
deliberately left open.

**Promotion stays ATTENDED.** A `PRODUCT_PROMISING` row gets its declared next
test scheduled and nothing else; nothing here writes `CAPITAL_CANDIDATE`, flips
a lane flag, or touches a book. That is the whole reason the plan is a receipt
and not a cron entry.

**No learned router.** The plan does not weight, blend, or rank selectors
against each other. There is still exactly one independent selector with
evidence (CLAUDE.md, THE BOTTLENECK), so a router would be a weighting over one
thing wearing a machine-learning hat.

THE FOUR RULES, AND WHERE EACH ONE'S EVIDENCE COMES FROM
========================================================
| status of the job's LATEST receipt | what the plan does |
|---|---|
| `CONDITIONAL` / `PRODUCT_PROMISING` | schedule the job's OWN DECLARED next test |
| `FAILED` / `TIMEOUT`, log on disk, no job-written receipt | schedule a RESUME of that run |
| `REJECTED` / `MECHANISM_REJECTED` / `ERA_DECAYED`, or the lane's trial id is named in a `NEGATIVE_RESULTS.md` heading | NOTHING |
| anything else | NOTHING, with the status printed |

The declared next test must be a FIELD in the receipt or in its amendment --
`next_test`, `next_step`, `open_question`, `what_the_morning_must_decide`. If a
schedulable row declares none, the plan prints
`CANNOT DETERMINE: <job> is CONDITIONAL and declares no next test`
and schedules nothing for it. It does not invent one. On the 2026-09-08/09
receipts that refusal fires more often than the schedule does, which is the
finding: almost nothing in this factory declares its own next test in a field.

WHY A DECLARED NEXT TEST STILL HAS TO NAME A RUNNABLE JOB
=========================================================
`next_step` is prose. Turning prose into a queue entry is exactly where a
planner would start inventing, so the resolution is closed-form and refuses by
default (`resolve_next_job`): the text must name a job id `night_factory_jobs`
knows, or say "re-run" of a declaring job that is itself a known job id.
Anything else is a refusal that names the text it could not resolve. A refusal
here is a finding about the receipt, not a failure of the plan.

TWO TRAPS THIS FILE ENCODES BECAUSE THEY ARE LIVE
=================================================
1. **A citation is not a closure.** `NEGATIVE_RESULTS.md` names
   `RW2_event_windows_run01.json` inside the TRIAL-H5 section as the *source of
   a number*, and names `N1H5_prereg_read` as the job that was closed. A
   substring match over job names would close RW2 for being quoted. So the
   closure link is structured: the file's SECTION HEADINGS supply trial ids
   (`TRIAL-H5`), and a receipt is closed only when its own `trial` field
   prefix-matches one. RW2 declares no trial and stays open.
2. **An empty `NIGHT_QUEUE` is not an empty queue.** `night_factory` reads the
   env var with `if _env_queue:`, so `NIGHT_QUEUE=""` is falsy and the DEFAULT
   thirteen-job queue runs. A plan with nothing in it therefore never prints a
   paste-able assignment -- it prints a refusal line instead.

DATES COME FROM NAMES, NEVER FROM `st_mtime`
============================================
The night directories are ordered by the date in the directory NAME. A fresh
checkout rewrites every mtime, and a gate that reads mtime is a gate on
checkout time (CLAUDE.md session protocol 7).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# `_status` is imported rather than re-implemented on purpose: a second copy of
# the tag-precedence rule would drift from the leaderboard's copy, and then the
# board and the plan would disagree about what a night concluded.
from scripts.night_factory import QUEUE as FACTORY_QUEUE, _status  # noqa: E402

NIGHT_ROOT = REPO / "backend" / "data" / "optimus"
NEGATIVE_RESULTS = REPO / "NEGATIVE_RESULTS.md"

NIGHT_DIR_RE = re.compile(r"^night_factory_(\d{4}-\d{2}-\d{2})$")
RECEIPT_RE = re.compile(r"^(?P<job>.+)_run(?P<run>\d{2})\.json$")
AMENDMENT_RE = re.compile(r"^(?P<job>.+?)_verdict_amendment\.json$")

#: a lane in one of these states gets NOTHING, ever
CLOSED_STATUSES = frozenset({"REJECTED", "MECHANISM_REJECTED", "ERA_DECAYED"})
#: a lane in one of these states gets its OWN DECLARED next test and nothing else
SCHEDULABLE_STATUSES = frozenset({"CONDITIONAL", "PRODUCT_PROMISING"})
#: a run in one of these states is a candidate for a RESUME, not a fresh run
RESUME_STATUSES = frozenset({"FAILED", "TIMEOUT"})

#: where a receipt is allowed to declare its own next test, in precedence order
NEXT_TEST_FIELDS = ("next_test", "next_step", "open_question",
                    "what_the_morning_must_decide", "next_question")

#: the payload `night_factory.run_job` writes when the JOB wrote nothing itself
_STUB_HEADLINE = re.compile(r"^(exited -?\d+ with no receipt|killed after [\d.]+ minutes)$")
_STUB_KEYS = frozenset({"verdict", "headline", "elapsed_s", "exit_code", "log_tail",
                        "licence", "job", "run", "written_utc"})

DEFAULT_MINUTES = 60
#: this module's own output, which it must never read back as a night result
PLAN_PREFIX = "NIGHT_PLAN_"


# ------------------------------------------------------------------ discovery

def night_dirs(root: Path, n: int = 2) -> list[Path]:
    """The `n` most recent night directories, ordered by the date in the NAME."""
    dated = []
    for p in sorted(root.glob("night_factory_*")):
        m = NIGHT_DIR_RE.match(p.name)
        if p.is_dir() and m:
            dated.append((m.group(1), p))
    dated.sort()
    return [p for _, p in dated[-n:]]


def job_wrote_receipt(payload: dict) -> bool:
    """False when the receipt on disk is the QUEUE's stub, not the JOB's output.

    `night_factory.run_job` writes a receipt in both failure paths, so "a receipt
    exists" does not mean "the job said something". The 2026-09-09 G3 crash left
    exactly this shape: eleven thousand seconds of compute, an appended
    evaluations jsonl, and a receipt whose entire content is `exited 1073807364
    with no receipt`. Re-running that from zero is the defect; resuming it is
    the fix.
    """
    headline = str(payload.get("headline") or "").strip()
    if _STUB_HEADLINE.match(headline):
        return False
    return not set(payload) <= _STUB_KEYS


def _rel(p: Path) -> str:
    """Repo-relative where it can be, absolute where it cannot (a tmp dir, a
    checkout somewhere else). `relative_to` RAISES off-tree, and a planner that
    dies on a path is a planner that cannot be tested on a synthetic night."""
    try:
        return p.relative_to(REPO).as_posix()
    except ValueError:
        return str(p)


def _read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  a corrupt receipt is a finding, not a crash
        return None


def load_receipts(dirs: list[Path]) -> tuple[list[dict], dict[tuple[str, int | None], dict]]:
    """Every receipt in `dirs`, plus the amendments keyed by what they amend."""
    records: list[dict] = []
    amendments: dict[tuple[str, int | None], dict] = {}
    for d in dirs:
        night = NIGHT_DIR_RE.match(d.name).group(1) if NIGHT_DIR_RE.match(d.name) else d.name
        for p in sorted(d.glob("*.json")):
            # a smoke artefact is not a result, and the planner's OWN receipt is
            # not a night result either -- reading it back would let a plan
            # schedule itself, which is the loop this file is built to leave open
            if p.name.endswith("_smoke.json") or p.name.startswith(PLAN_PREFIX):
                continue
            am = AMENDMENT_RE.match(p.name)
            if am:
                payload = _read_json(p)
                if payload is None:
                    continue
                amends = str(payload.get("amends") or "")
                m = RECEIPT_RE.match(Path(amends).name) if amends else None
                job = m.group("job") if m else am.group("job")
                run = int(m.group("run")) if m else None
                amendments[(job, run)] = {"path": p, "payload": payload}
                continue
            m = RECEIPT_RE.match(p.name)
            if not m:
                continue
            payload = _read_json(p)
            if payload is None:
                records.append({"job": m.group("job"), "run": int(m.group("run")),
                                "night": night, "path": p, "payload": {},
                                "status": "CANNOT DETERMINE", "unreadable": True,
                                "job_wrote_receipt": False, "log": None})
                continue
            log = p.with_suffix(".log")
            records.append({
                "job": m.group("job"), "run": int(m.group("run")), "night": night,
                "path": p, "payload": payload, "status": _status(payload),
                "unreadable": False,
                "job_wrote_receipt": job_wrote_receipt(payload),
                "log": log if log.is_file() else None,
            })
    return records, amendments


def latest_by_job(records: list[dict], amendments: dict) -> dict[str, dict]:
    """One record per job -- the newest night, then the highest run number.

    An amendment SUPERSEDES the run it names. `night_leaderboard_sync` files
    amendments as run 99 on the board for exactly this reason: the corrected
    verdict is the one the morning must read, and a plan built on the original
    stamp would re-open a lane the amendment closed (D3 was stamped
    PRODUCT_PROMISING and amended to ERA_DECAYED the same night).
    """
    out: dict[str, dict] = {}
    for r in sorted(records, key=lambda r: (r["night"], r["run"])):
        out[r["job"]] = r
    for job, rec in out.items():
        am = amendments.get((job, rec["run"])) or amendments.get((job, None))
        if not am:
            continue
        corrected = am["payload"].get("corrected_verdict")
        rec["amendment"] = am
        if corrected:
            rec["status_before_amendment"] = rec["status"]
            rec["status"] = _status({"verdict": corrected})
    return out


# ------------------------------------------------------- NEGATIVE_RESULTS.md

_ID_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\b")


def closed_trial_ids(path: Path = NEGATIVE_RESULTS) -> set[str]:
    """Trial / instrument ids that appear in a `NEGATIVE_RESULTS.md` HEADING.

    Headings only, because the body of a section cites the receipts of OTHER
    lanes as evidence and a body-wide match would close them by association.
    """
    if not path.is_file():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#"):
            ids.update(_ID_RE.findall(line))
    return ids


def negative_results_closure(rec: dict, closed_ids: set[str]) -> str | None:
    """The id from a heading that closes this record's lane, or None.

    The link is the receipt's OWN `trial` field, so a job is closed because it
    declared the trial the corpus buried -- never because its filename is quoted
    somewhere in the prose.
    """
    trial = str(rec.get("payload", {}).get("trial") or "")
    if not trial:
        return None
    for cid in sorted(closed_ids, key=len, reverse=True):
        if trial == cid or trial.startswith(cid + "-") or trial.startswith(cid + "_"):
            return cid
    return None


# ------------------------------------------------------------- next-test path

def declared_next_test(rec: dict) -> tuple[str | None, str | None, str | None]:
    """(text, field, where) -- the row's OWN declaration, amendment first."""
    am = rec.get("amendment")
    if am:
        for field in NEXT_TEST_FIELDS:
            v = am["payload"].get(field)
            if isinstance(v, str) and v.strip():
                return v.strip(), field, am["path"].name
            if isinstance(v, dict) and v:
                return json.dumps(v), field, am["path"].name
    for field in NEXT_TEST_FIELDS:
        v = rec["payload"].get(field)
        if isinstance(v, str) and v.strip():
            return v.strip(), field, rec["path"].name
        if isinstance(v, dict) and v:
            return json.dumps(v), field, rec["path"].name
    return None, None, None


_RERUN_RE = re.compile(r"\bre-?\s?run\b", re.I)


def known_jobs() -> set[str]:
    """The job ids `NIGHT_QUEUE` will accept -- the same dict it validates against."""
    from scripts.night_factory_jobs import JOBS
    return set(JOBS)


def resolve_next_job(text: str, declaring_job: str, jobs: set[str]) -> tuple[str | None, str]:
    """Turn a DECLARED next test into a runnable job id, or refuse saying why.

    Three closed-form ways in, and no fourth. A planner that guesses which job
    implements a sentence is the "learned router" this file is forbidden to be,
    one layer down.
    """
    if isinstance(text, str) and text.lstrip().startswith("{"):
        try:
            obj = json.loads(text)
        except Exception:  # noqa: BLE001
            obj = None
        if isinstance(obj, dict) and isinstance(obj.get("job"), str):
            job = obj["job"]
            if job in jobs:
                return job, f"the declaration names job {job!r} in its own `job` field"
            return None, f"the declaration names job {job!r}, which `night_factory_jobs` does not know"
    named = sorted((j for j in jobs if j in text), key=len, reverse=True)
    if named:
        return named[0], f"the declaration names the runnable job {named[0]!r} in its text"
    if _RERUN_RE.search(text):
        if declaring_job in jobs:
            return declaring_job, f"the declaration says re-run, and {declaring_job!r} is a runnable job id"
        return None, (f"the declaration says re-run, but {declaring_job!r} is not a job id "
                      f"`night_factory_jobs` knows -- a human must name the successor job")
    return None, "the declaration names no runnable job id and does not say re-run"


def minutes_for(job: str) -> tuple[int, str]:
    """The job's time box, taken from `night_factory.QUEUE` where it has one."""
    for j, m in FACTORY_QUEUE:
        if j == job:
            return m, "scripts.night_factory.QUEUE"
    return DEFAULT_MINUTES, "default (the job is not in night_factory.QUEUE)"


def resume_supported() -> bool:
    """Does the QUEUE know how to resume a run? Derived from its source, not assumed."""
    src = REPO / "scripts" / "night_factory.py"
    return src.is_file() and "--resume" in src.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ the plan

def build_plan(dirs: list[Path], *, closed_ids: set[str] | None = None,
               jobs: set[str] | None = None, plan_date: str | None = None) -> dict:
    closed_ids = closed_trial_ids() if closed_ids is None else closed_ids
    jobs = known_jobs() if jobs is None else jobs
    plan_date = plan_date or datetime.now().date().isoformat()

    records, amendments = load_receipts(dirs)
    latest = latest_by_job(records, amendments)

    queue: list[dict] = []
    refused: list[dict] = []
    cannot_determine: list[str] = []

    for job in sorted(latest):
        rec = latest[job]
        status = rec["status"]
        src = f"{rec['night']}/{rec['path'].name}"

        closure = negative_results_closure(rec, closed_ids)
        if closure:
            refused.append({"job": job, "status": status, "source_receipt": src,
                            "why": f"CLOSED LANE: the receipt declares trial "
                                   f"{rec['payload'].get('trial')!r} and NEGATIVE_RESULTS.md "
                                   f"carries {closure!r} in a section heading"})
            continue
        if status in CLOSED_STATUSES:
            refused.append({"job": job, "status": status, "source_receipt": src,
                            "why": f"CLOSED LANE: latest status is {status}"})
            continue

        if status in RESUME_STATUSES:
            if rec["job_wrote_receipt"]:
                refused.append({"job": job, "status": status, "source_receipt": src,
                                "why": f"{status}, but the JOB wrote this receipt -- there is "
                                       "no interrupted run to resume; a human decides whether "
                                       "the failure is worth re-running"})
                continue
            if rec["log"] is None:
                refused.append({"job": job, "status": status, "source_receipt": src,
                                "why": f"CANNOT DETERMINE: {status} with no job-written receipt "
                                       "AND no log on disk -- nothing survives to resume from"})
                cannot_determine.append(f"CANNOT DETERMINE: {job} is {status} with neither a "
                                        f"job-written receipt nor a log")
                continue
            if job not in jobs:
                refused.append({"job": job, "status": status, "source_receipt": src,
                                "why": f"{status} and resumable, but {job!r} is not a job id "
                                       "`night_factory_jobs` knows, so NIGHT_QUEUE would refuse it"})
                continue
            minutes, msrc = minutes_for(job)
            queue.append({
                "job": job, "minutes": minutes, "kind": "RESUME",
                "reason": f"{status} on run {rec['run']:02d}: the receipt on disk is the queue's "
                          f"stub (headline {str(rec['payload'].get('headline'))!r}), the job wrote "
                          f"nothing itself, and {rec['log'].name} is on disk -- so this is an "
                          "interrupted run to RESUME, not a fresh run",
                "quoted_field": "headline",
                "quoted_text": str(rec["payload"].get("headline")),
                "source_receipt": src, "log": rec["log"].name,
                "minutes_from": msrc,
                "resume_flag_supported_by_night_factory": resume_supported(),
            })
            continue

        if status in SCHEDULABLE_STATUSES:
            text, field, where = declared_next_test(rec)
            if not text:
                msg = f"CANNOT DETERMINE: {job} is {status} and declares no next test"
                cannot_determine.append(msg)
                refused.append({"job": job, "status": status, "source_receipt": src,
                                "why": msg + f" (looked for {', '.join(NEXT_TEST_FIELDS)} in the "
                                             "receipt and in its amendment)"})
                continue
            next_job, why = resolve_next_job(text, job, jobs)
            if next_job is None:
                refused.append({"job": job, "status": status, "source_receipt": src,
                                "why": f"{status} and DECLARES a next test in `{field}` of "
                                       f"{where}, but {why}: {text!r}"})
                continue
            minutes, msrc = minutes_for(next_job)
            queue.append({
                "job": next_job, "minutes": minutes, "kind": "DECLARED_NEXT_TEST",
                "reason": f"{job} is {status}; {why}",
                "quoted_field": field, "quoted_from": where, "quoted_text": text,
                "source_receipt": src, "minutes_from": msrc,
                "promotion": "NOT PROPOSED -- promotion to CAPITAL_CANDIDATE is attended",
            })
            continue

        refused.append({"job": job, "status": status, "source_receipt": src,
                        "why": f"status {status} is neither schedulable "
                               f"({'/'.join(sorted(SCHEDULABLE_STATUSES))}) nor a resumable "
                               f"failure -- no row is derivable, and inventing one is the "
                               f"thing this planner may not do"})

    # de-duplicate while keeping the first reason that put a job in the queue
    seen: dict[str, dict] = {}
    for row in queue:
        if row["job"] in seen:
            seen[row["job"]].setdefault("also_requested_by", []).append(row["reason"])
            continue
        seen[row["job"]] = row
    queue = list(seen.values())

    paste = ",".join(f"{r['job']}:{r['minutes']}" for r in queue)
    notes = []
    if queue and not resume_supported() and any(r["kind"] == "RESUME" for r in queue):
        notes.append("`night_factory` has no `--resume` flag on this checkout, so pasting the "
                     "line below re-runs the crashed job from run 02 at generation 0. The RESUME "
                     "row is a PROPOSAL for a human, not a working resume, until the queue "
                     "learns the flag (HANDOFF_2026-09-10 section 2.1).")
    if not queue:
        notes.append('NOTHING IS SCHEDULED. Do NOT paste NIGHT_QUEUE="": night_factory reads the '
                     "variable with `if _env_queue:`, so an empty string is falsy and the DEFAULT "
                     "thirteen-job queue runs instead of nothing.")

    return {
        "job": "night_queue_plan",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "requires_human_veto": True,
        "authority": "PROPOSES ONLY. This plan runs nothing, seals nothing, arms nothing, and "
                     "promotes nothing. PRODUCT_PROMISING rows get their declared next test and "
                     "no promotion; CAPITAL_CANDIDATE stays attended.",
        "plan_for_date": plan_date,
        "read_from": [_rel(d) for d in dirs],
        "receipts_read": len(records),
        "jobs_seen": sorted(latest),
        "negative_results_heading_ids": sorted(closed_ids),
        "queue": queue,
        "night_queue_env": (f'NIGHT_QUEUE="{paste}"' if queue else None),
        "refused": refused,
        "cannot_determine": cannot_determine,
        "notes_for_the_human": notes,
        "verdict": ("PLAN PROPOSED" if queue else "PLAN EMPTY"),
        "headline": (f"{len(queue)} row(s) proposed, {len(refused)} refused, "
                     f"{len(cannot_determine)} CANNOT DETERMINE, from {len(records)} receipt(s) "
                     f"over {len(dirs)} night(s)"),
    }


def _plan_path(out_dir: Path, plan_date: str) -> Path:
    run = 1
    while (out_dir / f"{PLAN_PREFIX}{plan_date}_run{run:02d}.json").exists():
        run += 1
    return out_dir / f"{PLAN_PREFIX}{plan_date}_run{run:02d}.json"


def write_plan(plan: dict, out_dir: Path) -> Path:
    """Write the plan and stamp its run number ON THE CALLER'S dict.

    The first version wrote a copy, so the memory row that followed recorded
    `run: null` while the file on disk said run 1 -- a receipt and a memory
    entry disagreeing about which artefact they describe.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    plan["written_utc"] = plan.get("written_utc") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = _plan_path(out_dir, plan["plan_for_date"])
    plan["run"] = int(p.stem.rsplit("run", 1)[1])
    plan["receipt"] = _rel(p)
    p.write_text(json.dumps(plan, indent=1, default=str), encoding="utf-8")
    return p


def append_memory(plan: dict, receipt_path: Path) -> dict:
    """One observation, through the sanctioned append-only API."""
    from learner import evidence_memory as EM
    return EM.observe(
        family_id=f"night_queue_plan/{plan['plan_for_date']}",
        cell="__plan__",
        n_months=None,
        verdict=f"{plan['verdict']} (requires_human_veto)",
        job="night_queue_plan",
        run=plan.get("run"),
        note=(f"{plan['headline']}; proposed {plan.get('night_queue_env') or 'NOTHING'}; "
              f"receipt {receipt_path.name}; this plan authorises nothing"),
    )


def render(plan: dict) -> str:
    out = [f"NIGHT QUEUE PLAN for {plan['plan_for_date']} -- {plan['headline']}",
           f"  read: {', '.join(plan['read_from'])}", ""]
    out.append("PROPOSED QUEUE")
    if plan["queue"]:
        for r in plan["queue"]:
            out.append(f"  {r['job']:28s} {r['minutes']:4d} min  [{r['kind']}]")
            out.append(f"      REASON: {r['reason']}")
            out.append(f"      QUOTES `{r.get('quoted_field')}` of "
                       f"{r.get('quoted_from') or r.get('source_receipt')}: "
                       f"{str(r.get('quoted_text'))[:220]}")
    else:
        out.append("  (empty)")
    out += ["", "REFUSED"]
    for r in plan["refused"]:
        out.append(f"  {r['job']:28s} [{r['status']}] {r['why']}")
    if plan["cannot_determine"]:
        out += ["", "CANNOT DETERMINE"]
        out += [f"  {m}" for m in plan["cannot_determine"]]
    if plan["notes_for_the_human"]:
        out += ["", "NOTES"]
        out += [f"  ! {n}" for n in plan["notes_for_the_human"]]
    out += ["", "PASTE THIS (a human decides; this file never runs it):"]
    out.append("  " + (plan["night_queue_env"] or
                       'REFUSED: nothing is scheduled, and NIGHT_QUEUE="" would run the '
                       "DEFAULT queue, not nothing"))
    out.append("")
    out.append("requires_human_veto: true")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Derive tomorrow's NIGHT_QUEUE from tonight's "
                                             "receipts. Proposes only; runs nothing.")
    # THREE, not two: a night directory is created the moment any job in it
    # writes anything, so a fresh one holding a single smoke artefact would
    # otherwise push the night that actually holds the corpus out of the window.
    ap.add_argument("--dirs", type=int, default=3, help="how many recent night directories to read")
    ap.add_argument("--root", default=str(NIGHT_ROOT))
    ap.add_argument("--date", default=None, help="the plan's date (default: today, local)")
    ap.add_argument("--dry-run", action="store_true", help="print it, write nothing")
    ap.add_argument("--no-memory", action="store_true", help="skip the evidence_memory append")
    a = ap.parse_args(argv)

    dirs = night_dirs(Path(a.root), a.dirs)
    if not dirs:
        print(f"REFUSED: no night_factory_YYYY-MM-DD directory under {a.root}", flush=True)
        return 2
    plan = build_plan(dirs, plan_date=a.date)
    print(render(plan), flush=True)
    if a.dry_run:
        print("\n--dry-run: nothing written", flush=True)
        return 0
    p = write_plan(plan, dirs[-1])
    print(f"\nplan receipt: {p}", flush=True)
    if not a.no_memory:
        append_memory(plan, p)
        print("appended 1 observation to learner/evidence_memory.jsonl", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
