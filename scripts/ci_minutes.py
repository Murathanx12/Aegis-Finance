"""Measure GitHub Actions minutes per workflow and project a month (CH-28).

A private repository on the free plan has 2,000 Actions minutes a month. In
October 2026 the repository was private, the minutes ran out, and every check
stopped. The reader of a "CI is too expensive" claim needs the measured split,
so this prints it: minutes by workflow, by event and by job, from the jobs the
runner actually billed.

    python -m scripts.ci_minutes measure --days 30 --out <receipt.json>
    python -m scripts.ci_minutes project --receipt <receipt.json>

`measure` reads the public REST API through the `gh` CLI (read-only). GitHub
bills every job rounded UP to a whole minute, so a 20-second job costs one
minute; this applies the same rule. A skipped job never got a runner and costs
nothing. Jobs still running are counted to the time of the call and marked.

`project` needs no network. It re-prices the measured month under the policies
in `POLICIES` and refuses (exit 2) when the receipt is missing or has no runs:
an empty month must not print "0 minutes, fits".

The numbers are runner minutes on Linux. They are an estimate of the invoice,
not the invoice: a public repository is not billed at all, and GitHub's own
billing page is the only ground truth for a private one.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = "Murathanx12/Aegis-Finance"
FREE_MINUTES_PRIVATE = 2000          # GitHub Free, private repository, per month
TARGET_MINUTES = 1500                # roadmap CH-28 acceptance
DAYS_PER_MONTH = 30.0

# What each policy changes, as a multiplier on the measured minutes of a
# (workflow, event, job) cell. A cell no rule names keeps its measured minutes.
# `nightly_backend_minutes` adds one backend run per day at the measured mean.
POLICIES: dict[str, dict] = {
    "as_measured": {"rules": [], "nightly_backend": False},
    # CH-28: the backend suite runs when a change lands on main and once a
    # night, not on every push to a pull request.
    "backend_on_main_and_nightly": {
        "rules": [{"workflow": "CI", "event": "pull_request", "job_prefix": "backend", "factor": 0.0}],
        "nightly_backend": True,
    },
    # The same, and the prod monitor pings every 30 minutes instead of 10.
    "backend_on_main_and_nightly__monitor_30min": {
        "rules": [
            {"workflow": "CI", "event": "pull_request", "job_prefix": "backend", "factor": 0.0},
            {"workflow": "Prod monitor", "event": "schedule", "job_prefix": "", "factor": 1.0 / 3.0},
        ],
        "nightly_backend": True,
    },
}


class CiMinutesRefused(RuntimeError):
    """The receipt is missing, unreadable or empty; nothing can be projected."""


def _ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def job_minutes(job: dict, now: datetime) -> tuple[int, bool]:
    """Billed minutes of one job and whether it was still running."""
    if job.get("conclusion") == "skipped":
        return 0, False
    start = _ts(job.get("started_at"))
    end = _ts(job.get("completed_at"))
    if start is None:
        return 0, False
    running = end is None
    seconds = ((end or now) - start).total_seconds()
    if seconds <= 0:
        return 0, running
    return int(math.ceil(seconds / 60.0)), running


def summarise(runs: list[dict], *, days: float, now: datetime) -> dict:
    """`runs` = [{workflow, event, id, created_at, jobs: [...]}, ...]."""
    cells: dict[tuple[str, str, str], dict] = defaultdict(lambda: {"minutes": 0, "jobs": 0})
    per_wf: dict[str, dict] = defaultdict(lambda: {"minutes": 0, "runs": 0})
    running = 0
    for run in runs:
        wf, ev = run.get("workflow") or "?", run.get("event") or "?"
        per_wf[wf]["runs"] += 1
        for job in run.get("jobs") or []:
            m, live = job_minutes(job, now)
            running += int(live)
            if m == 0:
                continue
            c = cells[(wf, ev, job.get("name") or "?")]
            c["minutes"] += m
            c["jobs"] += 1
            per_wf[wf]["minutes"] += m
    total = sum(c["minutes"] for c in cells.values())
    return {
        "days": days,
        "runs": len(runs),
        "total_minutes": total,
        "per_month_minutes": round(total * DAYS_PER_MONTH / days, 1) if days else None,
        "jobs_still_running": running,
        "by_workflow": {k: v for k, v in sorted(per_wf.items(), key=lambda kv: -kv[1]["minutes"])},
        "cells": [
            {"workflow": wf, "event": ev, "job": job, **c,
             "mean_minutes": round(c["minutes"] / c["jobs"], 2)}
            for (wf, ev, job), c in sorted(cells.items(), key=lambda kv: -kv[1]["minutes"])
        ],
    }


def project(summary: dict) -> dict:
    """Re-price the measured window under each policy, per 30-day month."""
    cells = summary.get("cells") or []
    days = float(summary.get("days") or 0)
    if not cells or days <= 0 or not summary.get("runs"):
        raise CiMinutesRefused("the receipt has no runs; an empty window projects nothing")
    scale = DAYS_PER_MONTH / days
    backend = [c for c in cells if c["workflow"] == "CI" and c["job"].startswith("backend")]
    b_jobs = sum(c["jobs"] for c in backend)
    b_mean = (sum(c["minutes"] for c in backend) / b_jobs) if b_jobs else None
    out: dict[str, dict] = {}
    for name, pol in POLICIES.items():
        total = 0.0
        for c in cells:
            f = 1.0
            for r in pol["rules"]:
                if (c["workflow"] == r["workflow"] and c["event"] == r["event"]
                        and c["job"].startswith(r["job_prefix"])):
                    f = r["factor"]
            total += c["minutes"] * f
        month = total * scale
        nightly = None
        if pol["nightly_backend"]:
            if b_mean is None:
                out[name] = {"status": "CANNOT_DETERMINE",
                             "why": "no backend job in the window, so a nightly run has no measured cost"}
                continue
            nightly = round(b_mean * DAYS_PER_MONTH, 1)
            month += nightly
        out[name] = {
            "per_month_minutes": round(month, 1),
            "nightly_backend_minutes": nightly,
            "fits_target": month < TARGET_MINUTES,
            "fits_free_private_plan": month < FREE_MINUTES_PRIVATE,
        }
    return {"target_minutes": TARGET_MINUTES, "free_private_minutes": FREE_MINUTES_PRIVATE,
            "backend_mean_minutes": round(b_mean, 2) if b_mean is not None else None,
            "policies": out}


def _gh(path: str, *fields: str) -> dict:
    argv = ["gh", "api", "-X", "GET", path]
    for f in fields:
        argv += ["-f", f]
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if r.returncode != 0:
        raise CiMinutesRefused(f"gh api {path} exited {r.returncode}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def fetch(days: int, now: datetime) -> list[dict]:
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    runs: list[dict] = []
    page = 1
    while True:
        d = _gh(f"repos/{REPO}/actions/runs", f"created=>={since}", "per_page=100", f"page={page}")
        batch = d.get("workflow_runs") or []
        for r in batch:
            jobs = _gh(f"repos/{REPO}/actions/runs/{r['id']}/jobs", "per_page=100", "filter=all")
            runs.append({
                "id": r["id"], "workflow": r.get("name"), "event": r.get("event"),
                "created_at": r.get("created_at"), "head_branch": r.get("head_branch"),
                "jobs": [{"name": j.get("name"), "conclusion": j.get("conclusion"),
                          "started_at": j.get("started_at"), "completed_at": j.get("completed_at")}
                         for j in (jobs.get("jobs") or [])],
            })
        if len(batch) < 100:
            break
        page += 1
    return runs


def _print(summary: dict, proj: dict) -> None:
    print(f"window {summary['days']} days, {summary['runs']} runs, "
          f"{summary['total_minutes']} billed-equivalent minutes "
          f"= {summary['per_month_minutes']} per 30 days")
    for wf, v in summary["by_workflow"].items():
        print(f"  {v['minutes']:6d} min  {v['runs']:4d} runs  {wf}")
    print("largest cells (workflow / event / job):")
    for c in summary["cells"][:8]:
        print(f"  {c['minutes']:6d} min  {c['jobs']:4d} jobs  mean {c['mean_minutes']:5.1f}  "
              f"{c['workflow']} / {c['event']} / {c['job']}")
    print(f"projection per 30 days (target < {proj['target_minutes']}, "
          f"free private plan {proj['free_private_minutes']}):")
    for name, p in proj["policies"].items():
        if "per_month_minutes" not in p:
            print(f"  {name}: {p['status']} ({p['why']})")
        else:
            print(f"  {p['per_month_minutes']:8.1f}  fits target: {p['fits_target']}  {name}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--days", type=int, default=30)
    m.add_argument("--out", required=True)
    p = sub.add_parser("project")
    p.add_argument("--receipt", required=True)
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if a.cmd == "measure":
            runs = fetch(a.days, now)
            summary = summarise(runs, days=float(a.days), now=now)
            proj = project(summary)
            out = Path(a.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(out.suffix + ".tmp")
            tmp.write_text(json.dumps({"schema": "ci_minutes/1", "repo": REPO,
                                       "measured_utc": now.isoformat(timespec="seconds"),
                                       "summary": summary, "projection": proj}, indent=1),
                           encoding="utf-8")
            tmp.replace(out)
        else:
            path = Path(a.receipt)
            if not path.is_file():
                raise CiMinutesRefused(f"no receipt at {path}")
            summary = json.loads(path.read_text(encoding="utf-8")).get("summary") or {}
            proj = project(summary)
    except CiMinutesRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    _print(summary, proj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
