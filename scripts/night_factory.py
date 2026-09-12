"""NIGHT FACTORY 2026-09-08 -- the CPU queue. $0 of LLM. Nothing ordered, sealed, pushed.

    python -m scripts.night_factory --list
    python -m scripts.night_factory                  # the whole queue, in order
    python -m scripts.night_factory --job D1_reaction_book
    python -m scripts.night_factory --hours 5        # G1's time box

Copied from `scripts/night_lab.py` (2026-09-05): one subprocess per job, a
receipt BEFORE the next job starts, a STOP file that ends the night between
jobs, a traceback that IS the receipt when a job dies. Two leaderboards, per
the 2026-09-08 roadmap: RESEARCH_PROVEN (Holm / DSR / three eras) and
PRODUCT_PROMISING (beats a beta-matched market after costs in the development
window, not yet family-clean). A row that fails the first is not deleted; it
is filed under the second with a typed status.

The GPU job (C1, the local-Qwen counterfactual curriculum) is NOT in this
queue: it runs beside it as its own process (`scripts.night_c_counterfactual_news`)
because it is I/O-bound on the llama server, not CPU-bound.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 2026-09-09 (Murat, 23:0x local): "run the nightly sim ... make it pull every
# news ... using the local LLM run sims again with made-up news so it can train
# the nn and find logic, reason and learn". Tonight's queue is a different queue
# in a different directory, so set both from the environment rather than forking
# this file for every night.
# 2026-09-13: the default was the literal "2026-09-08" for five days; two runs
# (B_verdict, A_corner) wrote into that folder before anyone noticed, because a
# stale default date reads exactly like a chosen one. Unset, the night is TODAY.
RUN_DATE = os.getenv("NIGHT_RUN_DATE") or datetime.now().strftime("%Y-%m-%d")
OUT = ROOT / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
STOP = OUT / "STOP"
LEADERBOARD = OUT / "LEADERBOARD.md"

#: (job id, minutes). Priority order.
QUEUE: list[tuple[str, int]] = [
    ("D1_reaction_book", 90),
    ("D2_reaction_mutations", 150),
    ("G1_evolve", 8 * 60),
    # added 2026-09-08 22:5x local, while G1 was still running. D1 graded every
    # cell against ZERO while its own placebo -- same names, same construction,
    # same 25 bps, dates shifted +40 sessions -- lost 14.868%/yr beta-matched.
    # D3 differences every leg against its own control; N1 trains on the event
    # level, where the construction cannot contaminate the label.
    ("D3_matched_control_grid", 90),
    ("N1_train_reaction_learner", 8 * 60),
    ("D4_ls_robustness_and_decay", 120),
    # the sealed window is opened ONCE, here, for G1's archive -- pre-declared
    # in the 2026-09-08 roadmap section 2.4 as the morning job
    ("G2_holdout_once", 90),
    # 2026-09-09 (Murat): "randomize the backtest ... really randomized times ...
    # see when it beats the S&P 500, what it was focusing on". Descriptive, no
    # holdout, null = random genomes on the SAME windows.
    ("RW1_random_windows", 60),
    # 2026-09-09 DAY RUN (roadmap section 10.8). Every one of these answers a
    # defect the 09-08 night's review named: RW2 puts the event-clock books on
    # the same random windows with their own control and a borrow curve; G3
    # replaces the single-window fitness with a distribution and makes the
    # drawdown budget a refusal; N2 gives the data-net the event print beside a
    # dateless control; P6 finally pulls the 2025-26 bars the repo never had.
    ("RW2_event_windows", 60),
    ("G3_evolve_v2", 5 * 60),
    ("N2_learner_v3", 120),
    ("P6_bars_and_regret", 60),
]

# NIGHT_QUEUE="E1_news_return_panel:20,C2_curriculum_transfer:90" replaces the
# queue above wholesale. An unknown job id is a REFUSAL at parse time, not a
# job that silently never runs -- a queue that quietly drops a name is the
# "gate that cannot go green" failure wearing a different hat.
_env_queue = os.getenv("NIGHT_QUEUE")
if _env_queue:
    from scripts.night_factory_jobs import JOBS as _KNOWN_JOBS
    QUEUE = []
    for item in (x.strip() for x in _env_queue.split(",") if x.strip()):
        name, _, mins = item.partition(":")
        if name not in _KNOWN_JOBS:
            raise SystemExit(f"NIGHT_QUEUE names an unknown job {name!r}; known: "
                             f"{', '.join(sorted(_KNOWN_JOBS))}")
        QUEUE.append((name, int(mins or 60)))

#: jobs whose length is a time box, not a computation
TIMEBOXED = {"G1_evolve", "N1_train_reaction_learner", "G3_evolve_v2"}
#: imported, not retyped, so the dispatch and the guard cannot drift apart
from scripts.night_smoke_job import SMOKE_PREFIX          # noqa: E402
#: mirrors `scripts.night_factory_jobs.RESUMABLE`; imported rather than retyped
#: so the two cannot drift apart into a --resume that the dispatcher refuses.
try:
    from scripts.night_factory_jobs import RESUMABLE          # noqa: E402
except Exception:                                             # noqa: BLE001
    RESUMABLE = {"G3_evolve_v2"}


def stopped() -> bool:
    return STOP.exists()


def _receipt_path(job: str, run: int) -> Path:
    return OUT / f"{job}_run{run:02d}.json"


def write_receipt(job: str, run: int, payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    payload.setdefault("licence", "PRODUCT_EXPERIMENT")
    payload.setdefault("job", job)
    payload.setdefault("run", run)
    payload.setdefault("written_utc", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    p = _receipt_path(job, run)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return p


TAGS = ("PRODUCT_PROMISING", "CONDITIONAL", "BETA_ONLY", "CONSTRUCTION_SENSITIVE", "CONTROL_ALSO_FIRES",
        "FAILED_VARIANT", "ERA_DECAYED", "CANNOT DETERMINE", "TIMEOUT", "FAILED", "REFUSED",
        "DEV ARCHIVE", "PANEL BUILT", "DESCRIPTIVE", "SCREEN", "READ_ONCE", "UNDERPOWERED",
        "MEMORY_SUSPECTED", "REJECTED", "ADOPT")


def _status(payload: dict) -> str:
    """The verdict's OWN leading tag, not whichever tag appears first in a list.

    The first version returned the first tag from a fixed tuple that occurred
    ANYWHERE in the verdict text, so P6 -- which built the 2025-26 panel and then
    explained that the six-mandate replay is REFUSED for a named missing input --
    was filed on the board as REFUSED. A status that reads a word out of a
    sentence about something else is worse than no status.
    """
    v = str(payload.get("verdict") or "")
    # earliest position wins; at the SAME position the LONGEST tag wins, or
    # `FAILED_VARIANT` files itself as the much harsher `FAILED`
    hits = sorted(((v.find(t), -len(t), t) for t in TAGS if t in v))
    if hits:
        return hits[0][2]
    return v[:24].strip() or "--"


def _cell(text: object, limit: int = 160) -> str:
    """A markdown table cell. A `|` inside a headline splits the row into extra
    columns -- RW1's own headline contains `genome|arena_k50_vw` and did exactly
    that -- so pipes are escaped and newlines flattened."""
    s = str(text if text is not None else "--")
    return s.replace("|", "\\|").replace("\n", " ")[:limit]


def append_leaderboard(job: str, run: int, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not LEADERBOARD.exists():
        LEADERBOARD.write_text(
            f"# NIGHT FACTORY {RUN_DATE} -- leaderboard\n\n"
            "Two rulers, two lists (ROADMAP_2026-09-08_NIGHT_ALPHA_FACTORY.md section 1).\n"
            "A row is never deleted for failing the first ruler; it moves to the second with a\n"
            "typed status: PRODUCT_PROMISING / CONDITIONAL / BETA_ONLY / FAILED_VARIANT.\n"
            "`family max p` is Holm over the job's own family, or `--` where the job has none.\n\n"
            "## RESEARCH_PROVEN (alpha ruler: Holm, three eras, placebo)\n\n"
            "(nothing yet -- a row lands here only from a pre-registered lane)\n\n"
            "## PRODUCT_PROMISING (product ruler: beta first, terminal wealth at a drawdown budget)\n\n"
            "| job | run | status | headline | family max p | utc |\n"
            "|---|---|---|---|---|---|\n", encoding="utf-8")
    row = (f"| {job} | {run} | {_cell(_status(payload), 30)} | {_cell(payload.get('headline'))} "
           f"| {_cell(payload.get('family_max_p'), 20)} | {_cell(payload.get('written_utc'), 30)} |\n")
    with LEADERBOARD.open("a", encoding="utf-8") as fh:
        fh.write(row)


def _log_path(job: str, run: int) -> Path:
    return OUT / f"{job}_run{run:02d}.log"


def _is_crashed_stub(job: str, run: int) -> bool:
    """True when the receipt at (job, run) is THIS file's stub for a job that
    died without writing its own -- i.e. there is work on disk to continue.

    `_receipt_path(job, run).exists()` alone was the whole test, so the crashed
    G3 run of 2026-09-09 -- 3.1 hours, 1,945 evaluations, killed by the OS with
    `exit 1073807364` (`DBG_TERMINATE_PROCESS`) -- looked exactly like a
    completed run and the next night would have started at run 02 from zero.
    """
    p = _receipt_path(job, run)
    if not p.exists():
        return False
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return (str(payload.get("verdict") or "") in {"FAILED", "TIMEOUT"}
            and "no receipt" in str(payload.get("headline") or ""))


def resolve_run(job: str, first_run: int) -> tuple[int, bool]:
    """(run number, resume?) for the next attempt at `job`.

    A run whose log is on disk and whose only receipt is the crash stub is
    RESUMED under its own number. Bumping to n+1 would leave the crashed run's
    checkpoint orphaned and its three hours unclaimed, which is what happened on
    2026-09-09 and is the reason nothing accumulated overnight.
    """
    run = first_run
    while _receipt_path(job, run).exists():
        if _is_crashed_stub(job, run) and _log_path(job, run).exists():
            return run, True
        run += 1
    if _log_path(job, run).exists():          # a log with no receipt at all
        return run, True
    return run, False


# --------------------------------------------------------------- the time box
#
# 2026-09-12. `N3_frozen_embedding_head` ran 40,569.7 s under a `<= 60 min` box
# and `subprocess.run(..., timeout=3600)` RETURNED NORMALLY with `exit_code 0`:
# the success branch, not the timeout branch. The machine was in Modern Standby
# 15:58Z -> 00:09Z, so awake time was still ~3h05m against the 60-minute box.
# The SHAPE is not at fault -- a probe copying this call verbatim (venv
# `sys.executable`, file-handle stdout, `stderr=STDOUT`, `text=True`, the same
# env dict) with a 20 s box and a 90 s sleeper raised `TimeoutExpired` at
# 20.01 s and the real grandchild died with it. What failed is the dependence
# on `WaitForSingleObject`'s timeout across a standby transition, which I could
# not reproduce on demand and therefore do not claim to have diagnosed.
#
# So the box no longer asks Windows to time it. It owns its own clock, it
# counts AWAKE seconds only, and it kills the whole process TREE by PID.

#: a single poll interval longer than this means the MACHINE stopped, not that
#: the job ran. Anything under it is time the job actually had.
SLEEP_GAP_S = float(os.getenv("AEGIS_NIGHT_SLEEP_GAP_S", "300"))
#: how often the box looks at the child. Cheap: one `poll()` per second.
POLL_S = float(os.getenv("AEGIS_NIGHT_POLL_S", "1.0"))
#: after the tree is asked to die, how long before we record that it did not
KILL_GRACE_S = float(os.getenv("AEGIS_NIGHT_KILL_GRACE_S", "20"))


def _job_module(job: str) -> str:
    """The module that runs `job`.

    `SMOKE_*` routes to `scripts.night_smoke_job`, a job that only sleeps, so
    the time box has something cheap to be exercised against. No real queue may
    contain a `SMOKE_` id; `test_night_factory_timebox.py` fails if one does.
    """
    return "scripts.night_smoke_job" if job.startswith(SMOKE_PREFIX) else "scripts.night_factory_jobs"


def _descendants(pid: int) -> list[int]:
    """Every descendant PID of `pid`, best effort; `[]` when we cannot enumerate.

    The venv launcher is a REDIRECTOR: `.venv/Scripts/python.exe` (274,424 B)
    starts the real `Python312/python.exe` (104,952 B) and waits, so the job is
    a GRANDCHILD and killing only the immediate child can orphan hours of
    compute -- and an orphan that finishes later OVERWRITES the receipt that
    said it was killed.
    """
    try:
        import psutil                                       # noqa: PLC0415
    except ImportError:
        psutil = None
    if psutil is not None:
        try:
            return [c.pid for c in psutil.Process(pid).children(recursive=True)]
        except Exception:                                   # noqa: BLE001
            return []
    if os.name != "nt":
        return []
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId "
             "| ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    parent_of: dict[int, int] = {}
    for line in r.stdout.splitlines()[1:]:
        parts = [x.strip().strip('"') for x in line.split(",")[:2]]
        try:
            parent_of[int(parts[0])] = int(parts[1])
        except (ValueError, IndexError):
            continue
    out: list[int] = []
    frontier = {pid}
    while frontier:
        nxt = {k for k, par in parent_of.items() if par in frontier and k != pid and k not in out}
        out.extend(sorted(nxt))
        frontier = nxt
    return out


def kill_tree(pid: int) -> list[int]:
    """Kill `pid` and every descendant BY PID, never by image name.

    CLAUDE.md session protocol 6: on 2026-09-06 one agent ran
    `taskkill /F` with an image-name filter to stop its own job and killed two
    other agents' jobs, a running test suite and the MCP server. PIDs only.
    """
    kids = _descendants(pid)
    asked = [pid, *kids]
    if os.name == "nt":
        for target, flags in [(pid, ["/T", "/F"]), *[(k, ["/F"]) for k in kids]]:
            try:
                subprocess.run(["taskkill", "/PID", str(int(target)), *flags],
                               capture_output=True, text=True, timeout=120, check=False)
            except (OSError, subprocess.SubprocessError):
                continue
    else:
        import signal                                       # noqa: PLC0415
        for target in reversed(asked):
            try:
                os.kill(int(target), signal.SIGKILL)
            except OSError:
                continue
    return asked


def await_within_box(proc, box_s: float, *, poll_s: float | None = None,
                     gap_s: float | None = None, killer=kill_tree,
                     clock=time.time, sleeper=time.sleep) -> tuple[int | None, dict]:
    """Wait for `proc`, spending only AWAKE seconds out of `box_s`.

    Returns `(returncode, stats)`; `returncode is None` means the box ran out
    and the tree was killed. Two clocks are read, because two different
    failures look identical from either one alone:

    * a poll interval far longer than `poll_s` means the interval did not
      happen -- the process was frozen (Modern Standby's Desktop Activity
      Moderator) or the machine suspended. The job did not have that time, so
      it is `slept_s`, and it does not spend the box.
    * `time.monotonic()` may or may not advance across a suspend depending on
      the platform, so `wall_minus_monotonic_s` is REPORTED beside the poll
      gaps rather than trusted instead of them.

    A job is killed for exceeding its box AWAKE. N3 on 2026-09-11 was awake
    about 3h05m under a 60-minute box, so this still kills it; what it must not
    do is kill a job for the eight hours the machine was not running it.
    """
    poll_s = POLL_S if poll_s is None else poll_s
    gap_s = SLEEP_GAP_S if gap_s is None else gap_s
    wall0, mono0 = clock(), time.monotonic()
    last = wall0
    awake = 0.0
    gaps: list[dict] = []
    while True:
        rc = proc.poll()
        now = clock()
        delta = now - last
        last = now
        if delta > gap_s:
            gaps.append({"gap_s": round(delta, 1),
                         "resumed_utc": datetime.fromtimestamp(now, timezone.utc)
                         .isoformat(timespec="seconds")})
        else:
            awake += max(delta, 0.0)
        elapsed = max(now - wall0, 0.0)
        stats = {
            "elapsed_s": round(elapsed, 1),
            "awake_s": round(awake, 1),
            "slept_s": round(max(elapsed - awake, 0.0), 1),
            "box_s": round(float(box_s), 1),
            "wall_minus_monotonic_s": round(elapsed - (time.monotonic() - mono0), 1),
            "sleep_gaps": gaps,
            "child_pid": proc.pid,
            "killed_pids": [],
        }
        if rc is not None:
            return rc, stats
        if awake >= box_s:
            stats["killed_pids"] = list(killer(proc.pid))
            try:
                proc.wait(timeout=KILL_GRACE_S)
            except Exception:                               # noqa: BLE001
                stats["tree_survived_the_kill"] = True
            return None, stats
        sleeper(poll_s)


# --------------------------------------------------- the machine must stay up

def standby_timeout_ac() -> tuple[int | None, str]:
    """`(AC idle sleep timeout in seconds, the evidence)` for the ACTIVE plan.

    `0` is "never sleep". `None` is CANNOT DETERMINE -- no `powercfg` (any
    non-Windows machine, CI included) or output this cannot parse. A guard that
    refused on CANNOT DETERMINE would be a gate that can never go green off
    Windows, so only a PARSED, non-zero timeout refuses.
    """
    try:
        r = subprocess.run(["powercfg", "/query", "SCHEME_CURRENT", "SUB_SLEEP", "STANDBYIDLE"],
                           capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"powercfg did not run ({exc.__class__.__name__})"
    if r.returncode != 0:
        return None, f"powercfg exited {r.returncode}"
    return parse_standby_ac(r.stdout)


def parse_standby_ac(stdout: str) -> tuple[int | None, str]:
    """The AC index out of `powercfg /query ... STANDBYIDLE` output.

    Split from the call so the guard is testable on a machine with no
    `powercfg` at all -- which is every CI runner this repo has.
    """
    for line in stdout.splitlines():
        if "Current AC Power Setting Index" in line:
            raw = line.split(":")[-1].strip()
            try:
                return int(raw, 0), f"Current AC Power Setting Index: {raw}"
            except ValueError:
                return None, f"could not parse {raw!r}"
    return None, "powercfg printed no AC setting index"


#: the one line Murat runs. Printed on refusal; never run by a session.
POWERCFG_FIX = "powercfg /change standby-timeout-ac 0"


def refuse_if_the_machine_may_sleep() -> str | None:
    """The refusal text, or `None` when the night may start.

    2026-09-11: the machine entered Modern Standby at 23:58 local and left at
    08:09, and a job that should have had one hour had eight of them handed to
    a suspended CPU. A night that can be slept through is not an unattended
    night. `AEGIS_NIGHT_ALLOW_SLEEP=1` overrides (tests, and a human who means
    it).
    """
    if os.getenv("AEGIS_NIGHT_ALLOW_SLEEP") == "1":
        return None
    secs, evidence = standby_timeout_ac()
    if secs is None:
        print(f"power plan: CANNOT DETERMINE ({evidence}); starting anyway", flush=True)
        return None
    if secs == 0:
        print("power plan: AC standby timeout 0 (never) -- the machine will stay up", flush=True)
        return None
    return (f"REFUSED: the active power plan sleeps after {secs}s on AC ({evidence}).\n"
            f"An unattended night cannot be slept through. Run this, then start again:\n"
            f"    {POWERCFG_FIX}\n"
            f"(or set AEGIS_NIGHT_ALLOW_SLEEP=1 to start anyway and accept the risk)")


def gpu_line() -> str:
    """Driver version and VRAM in use, so the next crash receipt has them.

    2026-09-12 10:53 HKT: bugcheck 0x116 VIDEO_TDR_ERROR while an unattended
    job held 5.3 GB of 8 GB on the local model. The next crash should not need
    an archaeologist to learn which driver was loaded.
    """
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.used,memory.total",
                            "--format=csv,noheader"], capture_output=True, text=True,
                           timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return "GPU: -- (nvidia-smi did not run)"
    if r.returncode != 0 or not r.stdout.strip():
        return f"GPU: -- (nvidia-smi exited {r.returncode})"
    return "GPU: " + " | ".join(x.strip() for x in r.stdout.strip().splitlines())


def run_job(job: str, run: int, timeout_min: int, extra: list[str], resume: bool = False) -> dict:
    """Run one job under its box and return the receipt payload.

    The box is `await_within_box`, not `subprocess.run(timeout=)`: it counts
    awake seconds, it kills the tree, and it says in the receipt which PIDs it
    asked to die and how long the machine was asleep.
    """
    cmd = [sys.executable, "-m", _job_module(job), job,
           "--out", str(_receipt_path(job, run)), "--run", str(run), *extra]
    if resume:
        cmd.append("--resume")
    log = OUT / f"{job}_run{run:02d}.log"
    OUT.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT, text=True,
                                env={**os.environ, "AEGIS_IGNORE_DOTENV": "1",
                                     "PYTHONIOENCODING": "utf-8"})
        rc, box = await_within_box(proc, timeout_min * 60)

    def _tail(n: int) -> str:
        try:
            return log.read_text(encoding="utf-8", errors="replace")[-n:]
        except OSError:
            return ""

    if rc is None:
        slept = box["slept_s"]
        headline = (f"killed after {box['awake_s']:.0f}s awake against a {timeout_min}-minute box "
                    f"(pids {box['killed_pids']})")
        if slept > 0:
            headline += (f"; the machine also slept {slept:.0f}s of the "
                         f"{box['elapsed_s']:.0f}s on the wall, which did NOT count")
        payload = {"verdict": "TIMEOUT", "headline": headline, "log_tail": _tail(4000), **box}
        write_receipt(job, run, payload)
        return payload

    if _receipt_path(job, run).exists():
        payload = json.loads(_receipt_path(job, run).read_text(encoding="utf-8"))
        payload.update(box)
        payload["exit_code"] = rc
        if rc:
            payload.setdefault("verdict", "FAILED")
            payload["log_tail"] = _tail(3000)
        write_receipt(job, run, payload)
        return payload

    payload = {"verdict": "FAILED", "headline": f"exited {rc} with no receipt",
               "exit_code": rc, "log_tail": _tail(4000), **box}
    write_receipt(job, run, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="run only these jobs, in QUEUE order (comma-separated)")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--hours", type=float, default=5.0, help="G1's time box")
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    if a.list:
        for j, m in QUEUE:
            print(f"{j:28s} {m:4d} min")
        return 0
    want = {j.strip() for j in a.job.split(",")} if a.job else None
    if want:
        unknown = want - {j for j, _ in QUEUE}
        if unknown:
            print(f"REFUSED: not in the queue: {sorted(unknown)}", flush=True)
            return 2
    queue = [(j, m) for j, m in QUEUE if want is None or j in want]
    print(f"NIGHT FACTORY {RUN_DATE}: {len(queue)} job(s); STOP file: {STOP}", flush=True)
    print(gpu_line(), flush=True)
    refusal = refuse_if_the_machine_may_sleep()
    if refusal:
        print(refusal, flush=True)
        return 3
    for job, minutes in queue:
        if stopped():
            print("STOP file present; ending the night between jobs", flush=True)
            break
        run, resume = resolve_run(job, a.run)
        if resume and job not in RESUMABLE:
            # A job with a checkpoint gets continued; one without gets restarted
            # and the receipt SAYS so, rather than the reader assuming the three
            # hours in the log were carried forward.
            print(f"    {job} run {run} crashed and has no checkpoint support; restarting from zero",
                  flush=True)
            resume = False
        extra = ["--hours", str(a.hours)] if job in TIMEBOXED else []
        print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {job} run {run} "
              f"({'RESUME' if resume else 'fresh'}, <= {minutes} min)", flush=True)
        payload = run_job(job, run, minutes, extra, resume=resume)
        if resume:
            payload["resumed"] = True
        append_leaderboard(job, run, payload)
        print(f"    -> {payload.get('verdict')}: {str(payload.get('headline'))[:150]}", flush=True)
    print("night queue done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
