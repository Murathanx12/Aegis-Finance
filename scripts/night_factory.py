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
RUN_DATE = "2026-09-08"
OUT = ROOT / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
STOP = OUT / "STOP"
LEADERBOARD = OUT / "LEADERBOARD.md"

#: (job id, minutes). Priority order.
QUEUE: list[tuple[str, int]] = [
    ("D1_reaction_book", 90),
    ("D2_reaction_mutations", 150),
    ("G1_evolve", 8 * 60),
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


def _status(payload: dict) -> str:
    v = str(payload.get("verdict") or "")
    for tag in ("PRODUCT_PROMISING", "CONDITIONAL", "BETA_ONLY", "CONSTRUCTION_SENSITIVE", "FAILED_VARIANT", "CANNOT DETERMINE",
                "TIMEOUT", "FAILED", "REFUSED", "DEV ARCHIVE", "SCREEN", "READ_ONCE"):
        if tag in v:
            return tag
    return v[:24] or "--"


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
    row = (f"| {job} | {run} | {_status(payload)} | {str(payload.get('headline', '--'))[:160]} "
           f"| {payload.get('family_max_p', '--')} | {payload.get('written_utc', '--')} |\n")
    with LEADERBOARD.open("a", encoding="utf-8") as fh:
        fh.write(row)


def run_job(job: str, run: int, timeout_min: int, extra: list[str]) -> dict:
    started = time.time()
    cmd = [sys.executable, "-m", "scripts.night_factory_jobs", job,
           "--out", str(_receipt_path(job, run)), "--run", str(run), *extra]
    log = OUT / f"{job}_run{run:02d}.log"
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        with log.open("w", encoding="utf-8") as fh:
            r = subprocess.run(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT, text=True,
                               timeout=timeout_min * 60,
                               env={**os.environ, "AEGIS_IGNORE_DOTENV": "1", "PYTHONIOENCODING": "utf-8"})
        elapsed = round(time.time() - started, 1)
        if _receipt_path(job, run).exists():
            payload = json.loads(_receipt_path(job, run).read_text(encoding="utf-8"))
            payload["elapsed_s"] = elapsed
            payload["exit_code"] = r.returncode
            if r.returncode:
                payload.setdefault("verdict", "FAILED")
                payload["log_tail"] = log.read_text(encoding="utf-8", errors="replace")[-3000:]
            write_receipt(job, run, payload)
            return payload
        payload = {"verdict": "FAILED", "headline": f"exited {r.returncode} with no receipt",
                   "elapsed_s": elapsed, "exit_code": r.returncode,
                   "log_tail": log.read_text(encoding="utf-8", errors="replace")[-4000:]}
        write_receipt(job, run, payload)
        return payload
    except subprocess.TimeoutExpired:
        payload = {"verdict": "TIMEOUT", "headline": f"killed after {timeout_min} minutes",
                   "elapsed_s": round(time.time() - started, 1)}
        write_receipt(job, run, payload)
        return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="run exactly one job and exit")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--hours", type=float, default=5.0, help="G1's time box")
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    if a.list:
        for j, m in QUEUE:
            print(f"{j:28s} {m:4d} min")
        return 0
    queue = [(j, m) for j, m in QUEUE if not a.job or j == a.job]
    print(f"NIGHT FACTORY {RUN_DATE}: {len(queue)} job(s); STOP file: {STOP}", flush=True)
    for job, minutes in queue:
        if stopped():
            print("STOP file present; ending the night between jobs", flush=True)
            break
        run = a.run
        while _receipt_path(job, run).exists():
            run += 1
        extra = ["--hours", str(a.hours)] if job == "G1_evolve" else []
        print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {job} run {run} (<= {minutes} min)", flush=True)
        payload = run_job(job, run, minutes, extra)
        append_leaderboard(job, run, payload)
        print(f"    -> {payload.get('verdict')}: {str(payload.get('headline'))[:150]}", flush=True)
    print("night queue done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
