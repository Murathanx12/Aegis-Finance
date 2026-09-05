"""WEEKEND LAB -- the night-lab runner, with the two things a 40-hour run needs.

    python -m scripts.weekend_lab --list
    python -m scripts.weekend_lab --job W2_learner_long
    python -m scripts.weekend_lab --queue W2_learner_long,W3_neural_long --once
    python -m scripts.weekend_lab                       # the whole queue, looping

WHY NOT JUST RE-USE `scripts/night_lab.py`
==========================================
Because it is right for a night and wrong for a weekend, in exactly two places.

1. **A NIGHT RUNS A QUEUE ONCE; A WEEKEND RUNS IT MANY TIMES, AND RUNNING THE
   SAME CELL TWENTY TIMES BUYS NOTHING.** The night lab loops by repeating the
   identical job, so pass 7 of `L4_reversal_by_size` re-derives pass 1's number
   at pass 1's cost. Here every job declares a VARIANT LIST and the runner hands
   it `--variant i` on pass `i`, cycling. Twenty passes of W2 are twenty
   different questions asked of the same panel, not one question asked twenty
   times. A job with one variant simply repeats, which is the old behaviour and
   is correct for an inventory.

2. **A JOB THAT FAILS TWICE IS SKIPPED, NOT RETRIED FOREVER.** Overnight, a job
   that raises on a missing file costs one traceback. Over 40 hours it costs
   forty, it fills the leaderboard with the same red line, and it starves the
   jobs that would have run in that slot. Two strikes and the runner records
   `SKIPPED_AFTER_2_FAILURES` with both tracebacks and moves on -- the failure
   is still loud, it is just not loud forty times.

EVERYTHING ELSE IS DELIBERATELY THE NIGHT LAB'S
===============================================
The receipt-per-job invariant, the traceback-IS-the-receipt rule, the per-job
timeout, the STOP file (because `TaskStop` does not kill the python child, so a
kill switch that depends on signals is a kill switch that does not work here),
and the refusal to seal, order, deploy, push or touch a Railway variable. The
lab reads local data and writes under `backend/data/optimus/weekend_lab_<date>/`.

THE LEADERBOARD HAS A HEAD
==========================
`LEADERBOARD.md` grows one row per job per pass, which after 40 hours is a file
nobody reads to the bottom. So the runner rewrites a five-line BEST SO FAR block
at the TOP of the file after every pass, carrying the best cell's headline, its
DSR, its SPA p, its PBO and -- the number the weekend exists to move --
`years_needed_for_t2` beside `n_oos_months`. A scoreboard whose top line is 40
hours old is a scoreboard that gets skimmed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN_DATE = "2026-09-06"
OUT = ROOT / "backend" / "data" / "optimus" / f"weekend_lab_{RUN_DATE}"
STOP = OUT / "STOP"
LEADERBOARD = OUT / "LEADERBOARD.md"
BEST = OUT / "best_so_far.json"

#: (job id, timeout minutes, n_variants). The order IS the priority order.
#: `n_variants` is how many DIFFERENT questions the job knows how to ask; the
#: runner passes `--variant (pass - 1) % n_variants`, so a weekend of passes
#: walks the variant list instead of re-deriving one cell.
QUEUE: list[tuple[str, int, int]] = [
    ("W1_long_panel_inventory", 15, 1),
    # 300, not 200: the full 336-fit grid over 26 years exceeded 200 minutes on a
    # loaded machine. The cell cache (`_w2_grid`, tag-keyed) means a killed pass
    # is resumed rather than repeated, so a generous timeout costs at most one
    # slot and a mean one costs the whole grid, every pass, forever.
    ("W2_learner_long", 300, 5),
    ("W6_behavioural", 60, 1),
    ("W6b_liquidity_band", 45, 1),
    ("W3_neural_long", 180, 4),
    ("W5_options_iv", 120, 2),
    ("W5b_options_book", 90, 1),
    ("W5c_options_exclusion", 90, 1),
    ("W4_graph_momentum", 90, 1),
    ("W7_matched_loser", 180, 4),
    ("W7b_archetype_book", 90, 1),
    ("W8_states_three_nulls", 60, 3),
    ("W9_survivor_books", 90, 1),
    ("W10_decay_autopsy", 60, 1),
    ("W12_short_side", 90, 1),
    ("W11_evidence_writeback", 20, 1),
]


def stopped() -> bool:
    return STOP.exists()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _receipt_path(job: str, run: int, variant: int) -> Path:
    return OUT / f"{job}_run{run:02d}_v{variant}.json"


def write_receipt(job: str, run: int, variant: int, payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    payload.setdefault("licence", "PRODUCT_EXPERIMENT")
    payload.setdefault("job", job)
    payload.setdefault("run", run)
    payload.setdefault("variant", variant)
    payload.setdefault("written_utc", _now())
    p = _receipt_path(job, run, variant)
    p.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return p


# ------------------------------------------------------------------ leaderboard

_HEAD_MARK = "<!-- BEST SO FAR -->"
_HEAD_END = "<!-- /BEST SO FAR -->"


def _table_header() -> str:
    return (
        f"# WEEKEND LAB {RUN_DATE} -- leaderboard\n\n"
        "One line per job per pass. `family max p` is the multiplicity-corrected\n"
        "p-value where a family exists; a job with no family says so rather than\n"
        "quoting a single-cell number as if it were one. `yrs->t2` is the years of\n"
        "tape a t = 2 would need at the arm's own Sharpe -- the number that decides\n"
        "whether a null verdict means NOISE or means NOT ENOUGH TAPE.\n\n"
        f"{_HEAD_MARK}\n{_HEAD_END}\n\n"
        "| job | pass | v | headline | DSR | SPA p | PBO | n_oos_m | yrs->t2 | verdict |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n")


def _dig(payload: dict, *path, default="--"):
    cur = payload
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def append_leaderboard(job: str, run: int, variant: int, payload: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if not LEADERBOARD.exists():
        LEADERBOARD.write_text(_table_header(), encoding="utf-8")
    inf = payload.get("inference") or {}
    row = (f"| {job} | {run} | {variant} | {str(payload.get('headline', '--'))[:100]} "
           f"| {_dig(inf, 'deflated_sharpe', 'dsr')} "
           f"| {_dig(inf, 'spa', 'p_spa_consistent')} "
           f"| {_dig(inf, 'pbo', 'pbo')} "
           f"| {_dig(inf, 'power', 'n_periods')} "
           f"| {_dig(inf, 'power', 'years_needed_for_t2')} "
           f"| {payload.get('verdict', '--')} |\n")
    with LEADERBOARD.open("a", encoding="utf-8") as fh:
        fh.write(row)


def update_best(payload: dict) -> None:
    """Rewrite the BEST SO FAR block at the top of the leaderboard.

    "Best" is by DEFLATED Sharpe, not by Sharpe and not by return. Ranking a
    weekend of searches by raw performance would put the luckiest cell of the
    largest grid on top by construction, which is the exact error DSR exists to
    correct -- so the ranking key is the corrected number or the entry does not
    rank at all.
    """
    inf = payload.get("inference") or {}
    dsr = _dig(inf, "deflated_sharpe", "dsr", default=None)
    if dsr is None or not isinstance(dsr, (int, float)):
        return
    cur = {}
    if BEST.exists():
        try:
            cur = json.loads(BEST.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    if cur and isinstance(cur.get("dsr"), (int, float)) and cur["dsr"] >= dsr:
        return
    entry = {
        "job": payload.get("job"), "run": payload.get("run"),
        "variant": payload.get("variant"),
        "headline": payload.get("headline"),
        "verdict": payload.get("verdict"),
        "dsr": dsr,
        "spa_p": _dig(inf, "spa", "p_spa_consistent", default=None),
        "pbo": _dig(inf, "pbo", "pbo", default=None),
        "n_oos_months": _dig(inf, "power", "n_periods", default=None),
        "years_needed_for_t2": _dig(inf, "power", "years_needed_for_t2", default=None),
        "years_observed": _dig(inf, "power", "years_observed", default=None),
        "era_sign_table": payload.get("era_sign_table"),
        "written_utc": _now(),
    }
    BEST.write_text(json.dumps(entry, indent=1, default=str), encoding="utf-8")
    if not LEADERBOARD.exists():
        LEADERBOARD.write_text(_table_header(), encoding="utf-8")
    txt = LEADERBOARD.read_text(encoding="utf-8")
    block = (
        f"{_HEAD_MARK}\n"
        f"**BEST SO FAR (ranked by DEFLATED Sharpe, not by return)** -- rewritten {entry['written_utc']}\n\n"
        f"- **{entry['job']} pass {entry['run']} variant {entry['variant']}** -- {entry['headline']}\n"
        f"- DSR **{entry['dsr']}** | SPA p {entry['spa_p']} | PBO {entry['pbo']} | verdict **{entry['verdict']}**\n"
        f"- {entry['n_oos_months']} out-of-sample months ({entry['years_observed']} years); "
        f"t = 2 would need **{entry['years_needed_for_t2']}** years at this Sharpe\n"
        f"- three-era sign table: {entry['era_sign_table'] or 'not reported by this job'}\n"
        f"{_HEAD_END}")
    txt = re.sub(re.escape(_HEAD_MARK) + r".*?" + re.escape(_HEAD_END), block, txt,
                 flags=re.S)
    LEADERBOARD.write_text(txt, encoding="utf-8")


# ------------------------------------------------------------------- one job

def _env() -> dict:
    import os
    return dict(os.environ)


def run_job(job: str, run: int, variant: int, timeout_min: int) -> dict:
    """One job as a subprocess. Its traceback IS its receipt when it fails."""
    started = time.time()
    out_path = _receipt_path(job, run, variant)
    cmd = [sys.executable, "-m", "scripts.weekend_lab_jobs", job,
           "--out", str(out_path), "--run", str(run), "--variant", str(variant)]
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           timeout=timeout_min * 60,
                           env={**_env(), "AEGIS_IGNORE_DOTENV": "1",
                                "PYTHONUNBUFFERED": "1"})
        elapsed = round(time.time() - started, 1)
        if out_path.exists():
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            payload["elapsed_s"] = elapsed
            payload["exit_code"] = r.returncode
            if r.returncode:
                payload.setdefault("verdict", "FAILED")
                payload["stderr_tail"] = (r.stderr or "")[-2000:]
            write_receipt(job, run, variant, payload)
            return payload
        payload = {"verdict": "FAILED",
                   "headline": f"exited {r.returncode} with no receipt",
                   "elapsed_s": elapsed, "exit_code": r.returncode,
                   "stdout_tail": (r.stdout or "")[-2000:],
                   "stderr_tail": (r.stderr or "")[-4000:]}
        write_receipt(job, run, variant, payload)
        return payload
    except subprocess.TimeoutExpired:
        payload = {"verdict": "TIMEOUT",
                   "headline": f"killed after {timeout_min} minutes",
                   "elapsed_s": round(time.time() - started, 1)}
        write_receipt(job, run, variant, payload)
        return payload


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="run exactly one job and exit")
    ap.add_argument("--queue", help="comma list of job ids (default: the whole queue)")
    ap.add_argument("--variant", type=int, default=None,
                    help="force a variant index (default: cycle by pass)")
    ap.add_argument("--once", action="store_true", help="one pass, do not loop")
    ap.add_argument("--start-pass", type=int, default=1)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for job, mins, nv in QUEUE:
            print(f"  {job:<26} timeout {mins:>4} min   variants {nv}")
        return 0

    by = {j: (m, v) for j, m, v in QUEUE}
    queue = QUEUE
    if args.job:
        m, v = by.get(args.job, (60, 1))
        queue = [(args.job, m, v)]
    elif args.queue:
        want = [j.strip() for j in args.queue.split(",") if j.strip()]
        queue = [(j, *by.get(j, (60, 1))) for j in want]

    OUT.mkdir(parents=True, exist_ok=True)
    # Two strikes and the job is out. Counted per (job, variant): a variant that
    # is broken should not condemn the variants that work.
    failures: dict[tuple[str, int], int] = {}
    run = int(args.start_pass)
    while True:
        for job, mins, nvar in queue:
            if stopped():
                print(f"STOP file present ({STOP}); halting before {job}", flush=True)
                return 0
            variant = (args.variant if args.variant is not None
                       else (run - 1) % max(1, int(nvar)))
            key = (job, variant)
            if failures.get(key, 0) >= 2:
                print(f"=== {job} v{variant}: SKIPPED_AFTER_2_FAILURES ===", flush=True)
                continue
            print(f"\n=== {job} v{variant} (pass {run}, timeout {mins}m) ===", flush=True)
            payload = run_job(job, run, variant, mins)
            append_leaderboard(job, run, variant, payload)
            update_best(payload)
            if payload.get("verdict") in ("FAILED", "TIMEOUT"):
                failures[key] = failures.get(key, 0) + 1
            print(f"  -> {payload.get('verdict')}: "
                  f"{str(payload.get('headline'))[:140]}", flush=True)
        if args.once or args.job:
            return 0
        run += 1


if __name__ == "__main__":
    raise SystemExit(main())
