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
RUN_DATE = os.getenv("NIGHT_RUN_DATE", "2026-09-08")
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
    for job, minutes in queue:
        if stopped():
            print("STOP file present; ending the night between jobs", flush=True)
            break
        run = a.run
        while _receipt_path(job, run).exists():
            run += 1
        extra = ["--hours", str(a.hours)] if job in TIMEBOXED else []
        print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {job} run {run} (<= {minutes} min)", flush=True)
        payload = run_job(job, run, minutes, extra)
        append_leaderboard(job, run, payload)
        print(f"    -> {payload.get('verdict')}: {str(payload.get('headline'))[:150]}", flush=True)
    print("night queue done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
