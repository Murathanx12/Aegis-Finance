"""NIGHT LAB -- run the queue, write a receipt for every job, loop until STOP.

    python -m scripts.night_lab --list
    python -m scripts.night_lab --job L11_belief_inventory
    python -m scripts.night_lab --queue L11,L12,L13 --once
    python -m scripts.night_lab                       # the whole queue, looping

WHY A RUNNER AND NOT THIRTEEN COMMANDS
======================================
Three properties that only a runner can have, and each one was bought by a
failure this repo already paid for:

1. **EVERY JOB WRITES A RECEIPT, INCLUDING THE ONES THAT FIND NOTHING.**
   A job that crashes writes its traceback AS its receipt. A job that finds
   nothing writes the nothing, with the cells it looked at. Invariant 15: a
   process that produces no artefact reads exactly like a process that was
   never run, and on 2026-08-30 a job that exited 127 kept a pid and an empty
   log and read as "running" for two hours.
2. **A TIMEOUT PER JOB.** One job that hangs on a parquet read must not consume
   the night. The subprocess is killed, the receipt says so, and the queue
   continues.
3. **A STOP FILE, CHECKED BETWEEN RUNS.** The human stops the lab by touching
   one file, not by hunting PIDs -- `TaskStop` does not kill the python child
   (reference_taskstop_does_not_kill_the_child), so a kill switch that depends
   on signals is a kill switch that does not work here.

WHAT IT DELIBERATELY DOES NOT DO
================================
Seal, order, deploy, push, or touch a Railway variable. It reads local data and
writes under `backend/data/optimus/night_lab_<date>/`. Every receipt carries
`licence: PRODUCT_EXPERIMENT` and the question it was asked, so a result that
later wants to be a claim has to be re-run under the claim standard.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_DATE = "2026-09-05"
OUT = ROOT / "backend" / "data" / "optimus" / f"night_lab_{RUN_DATE}"
STOP = OUT / "STOP"
LEADERBOARD = OUT / "LEADERBOARD.md"

#: (job id, minutes). The order IS the priority order: a night that only gets
#: through the first four should have got through the four that matter most.
QUEUE: list[tuple[str, int]] = [
    ("L11_belief_inventory", 10),
    ("L12_mirror_reconcile", 15),
    ("L13_corpus_railway_design", 10),
    ("L8_grade_sealed_books", 25),
    ("L4_reversal_by_size", 90),
    ("L1_learner_clean_panel", 180),
]


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


def append_leaderboard(job: str, run: int, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not LEADERBOARD.exists():
        LEADERBOARD.write_text(
            f"# NIGHT LAB {RUN_DATE} -- leaderboard\n\n"
            "One line per job per run. `family max p` is the multiplicity-corrected\n"
            "p-value where a family exists; a job with no family says so rather than\n"
            "quoting a single-cell number as if it were one.\n\n"
            "| job | run | headline | family max p | DSR | verdict |\n"
            "|---|---|---|---|---|---|\n", encoding="utf-8")
    row = (f"| {job} | {run} | {str(payload.get('headline', '--'))[:110]} "
           f"| {payload.get('family_max_p', '--')} | {payload.get('dsr', '--')} "
           f"| {payload.get('verdict', '--')} |\n")
    with LEADERBOARD.open("a", encoding="utf-8") as fh:
        fh.write(row)


def run_job(job: str, run: int, timeout_min: int) -> dict:
    """One job as a subprocess. Its traceback IS its receipt when it fails."""
    started = time.time()
    cmd = [sys.executable, "-m", "scripts.night_lab_jobs", job,
           "--out", str(_receipt_path(job, run)), "--run", str(run)]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=timeout_min * 60,
                           env={**_env(), "AEGIS_IGNORE_DOTENV": "1"})
        elapsed = round(time.time() - started, 1)
        if _receipt_path(job, run).exists():
            payload = json.loads(_receipt_path(job, run).read_text(encoding="utf-8"))
            payload["elapsed_s"] = elapsed
            payload["exit_code"] = r.returncode
            if r.returncode:
                payload.setdefault("verdict", "FAILED")
                payload["stderr_tail"] = (r.stderr or "")[-2000:]
            write_receipt(job, run, payload)
            return payload
        payload = {"verdict": "FAILED", "headline": f"exited {r.returncode} with no receipt",
                   "elapsed_s": elapsed, "exit_code": r.returncode,
                   "stdout_tail": (r.stdout or "")[-2000:],
                   "stderr_tail": (r.stderr or "")[-4000:]}
        write_receipt(job, run, payload)
        return payload
    except subprocess.TimeoutExpired:
        payload = {"verdict": "TIMEOUT",
                   "headline": f"killed after {timeout_min} minutes",
                   "elapsed_s": round(time.time() - started, 1)}
        write_receipt(job, run, payload)
        return payload


def _env() -> dict:
    import os
    return dict(os.environ)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="run exactly one job and exit")
    ap.add_argument("--queue", help="comma list of job ids (default: the whole queue)")
    ap.add_argument("--once", action="store_true", help="one pass, do not loop")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for job, mins in QUEUE:
            print(f"  {job:<28} timeout {mins:>4} min")
        return 0

    queue = QUEUE
    if args.job:
        queue = [(args.job, dict(QUEUE).get(args.job, 60))]
    elif args.queue:
        want = [j.strip() for j in args.queue.split(",") if j.strip()]
        by = dict(QUEUE)
        queue = [(j, by.get(j, 60)) for j in want]

    OUT.mkdir(parents=True, exist_ok=True)
    run = 1
    while True:
        for job, mins in queue:
            if stopped():
                print(f"STOP file present ({STOP}); halting before {job}", flush=True)
                return 0
            print(f"\n=== {job} (run {run}, timeout {mins}m) ===", flush=True)
            payload = run_job(job, run, mins)
            append_leaderboard(job, run, payload)
            print(f"  -> {payload.get('verdict')}: {str(payload.get('headline'))[:140]}",
                  flush=True)
        if args.once or args.job:
            return 0
        run += 1


if __name__ == "__main__":
    raise SystemExit(main())
