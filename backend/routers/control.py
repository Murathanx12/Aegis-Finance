"""Control plane for Aegis Desktop (roadmap 2026-09-08 section 10.7, phase A0).

Murat's requirement is an `.exe` where "a person that doesn't have any coding
should open it and click". Everything the night factory does is currently a
`python -m scripts...` line; this router turns each of those into one button,
and it is the ONLY new surface the desktop shell needs.

Three rules are enforced here rather than intended:

1. **A whitelist, never a command string.** `POST /api/control/run/{job}` accepts
   only a job id that appears in `scripts.night_factory.QUEUE` (plus the small
   `EXTRA_JOBS` map for the jobs that live in their own module). There is no
   parameter that reaches a shell, and `shell=False` on every spawn.
2. **Kill by PID, from a PID we wrote down.** On 2026-09-06 an agent ran
   `taskkill /F /IM python.exe` to stop its own job and killed two other agents'
   jobs, a test suite, ~1,676 already-billed extractions and the MCP server.
   `POST /api/control/stop/{pid}` writes the queue's STOP file first (which ends
   the run cleanly between jobs), and only then signals the ONE pid, and only if
   that pid is in this process's own run registry.
3. **No order path is importable from here.** The router reads paper-account
   state through files the loops already write; it never imports a broker.
   `backend/tests/test_control_router_authority.py` walks this module's AST and
   fails if a broker/order symbol ever appears.

The mutating endpoints additionally refuse unless `AEGIS_CONTROL_ENABLED=1`, so
the router is inert on the Railway website deployment and live only in the
desktop shell, which sets the flag when it starts the backend on localhost.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from backend.services import quiet_subprocess as qsp  # noqa: E402

router = APIRouter(prefix="/api/control", tags=["control"])

def _repo_root() -> Path:
    """The repository the control plane reads and writes.

    Inside a PyInstaller build `__file__` is `<dist>/_internal/backend/routers/`,
    so the default resolves to `_internal` -- and the packaged app then looked
    for night receipts in a directory that does not exist and reported an empty
    programme with a straight face. Measured on the first packaged run:
    `Database initialized at <dist>/_internal/backend/data/aegis_pi.db`, a fresh
    empty database beside a repo full of real ones.

    `AEGIS_REPO_ROOT` is set by the desktop shell to the real checkout. The
    fallback stays the source layout, which is correct when running from source.
    """
    env = os.getenv("AEGIS_REPO_ROOT")
    if env and Path(env).is_dir():
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


REPO = _repo_root()


def _night_dir(base: Path | None = None) -> Path:
    """The night whose board the page shows and a spawned job writes into.

    This was the literal `night_factory_2026-09-08` until 2026-09-12, so the
    desktop night page served the 09-08 board for four nights while 09-09,
    09-10 and 09-11 accumulated beside it -- a result on disk and invisible,
    which is what `night_leaderboard_sync` already exists to prevent one level
    down. `NIGHT_RUN_DATE` wins (it is what `scripts.night_factory` reads);
    otherwise the NEWEST directory BY NAME, never by mtime, because a fresh
    checkout rewrites every mtime (session protocol 7). The old literal
    survives only as the answer when there is no night directory at all.
    """
    base = base or (REPO / "backend" / "data" / "optimus")
    date = os.getenv("NIGHT_RUN_DATE")
    if date:
        return base / f"night_factory_{date}"
    dirs = sorted(p for p in base.glob("night_factory_20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]")
                  if p.is_dir())
    return dirs[-1] if dirs else base / "night_factory_2026-09-08"


NIGHT_DIR = _night_dir()
RUNS_DIR = REPO / "backend" / "data" / "optimus" / "control_runs"
BALANCE_FILE = REPO / "backend" / "data" / "optimus" / "deepseek_balance.jsonl"
LLAMA_URL = os.getenv("LOCAL_GGUF_URL", "http://127.0.0.1:8080")

#: jobs that live outside `scripts.night_factory`'s QUEUE, as (module, args)
EXTRA_JOBS: dict[str, list[str]] = {
    "C1_counterfactual_news": ["-m", "scripts.night_c_counterfactual_news"],
    "RW2_event_windows": ["-m", "scripts.night_rw2_event_windows"],
    "G3_evolve_v2": ["-m", "scripts.night_g3_evolve_v2"],
    "P6_bars_and_regret": ["-m", "scripts.night_p6_bars_and_regret"],
    "N2_learner_v3": ["-m", "scripts.night_n2_learner_v3"],
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _enabled() -> bool:
    return os.getenv("AEGIS_CONTROL_ENABLED", "") == "1"


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=403,
            detail=("the control plane is disabled. It runs local jobs, so it is off unless "
                    "AEGIS_CONTROL_ENABLED=1 is set by the desktop shell on localhost."))


def queue_jobs() -> list[str]:
    """The night queue's own ids. Derived, never re-typed: a job added to the
    queue is a button without touching this file (a gate that derives its inputs)."""
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from scripts.night_factory import QUEUE
        return [j for j, _ in QUEUE]
    except Exception:  # noqa: BLE001  a checkout without the scripts package still serves reads
        return []


def whitelist() -> list[str]:
    return sorted(set(queue_jobs()) | set(EXTRA_JOBS))


# ------------------------------------------------------------- run registry

def job_python() -> str | None:
    """The interpreter that runs night jobs, or None with a reason.

    The packaged app deliberately does NOT bundle the research stack. The first
    build did -- `collect_data_files` on `backend`/`scripts`/`learner` swept
    `backend/data/` into the bundle and `collect_submodules("scripts")` dragged
    in torch with CUDA -- and produced a **27 GB** dist directory that was
    mostly a second copy of parquets already on disk two directories away.

    The app is a launcher for THIS machine's repo: it reads
    `backend/data/optimus/**` at runtime and is not portable regardless. So the
    .exe carries the window and the API, and night jobs run under a real Python
    that already has torch, lightgbm and the rest.

    Resolution order, and it REFUSES rather than guessing: `AEGIS_JOB_PYTHON`,
    then a `.venv` beside the repo, then `python` on PATH.

    THE ORDER LIVES IN `desktop/_interp.py` AND IS IMPORTED, not repeated. The
    launcher (`desktop/launcher.py`) has to answer the same question before it
    can start anything at all, and two copies of a resolution order drift the
    moment one of them learns about a new venv layout. `desktop/_interp` imports
    the standard library only, so this adds nothing to the control plane.
    """
    if str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from desktop._interp import resolve
    return resolve(REPO)[0]


def child_argv(args: list[str]) -> list[str]:
    """Build the argv for a night job.

    Under a normal Python this is just `[sys.executable, *args]`. In the frozen
    build `sys.executable` is `AegisDesktop.exe`, which has no `-m` and would
    hand the module name to argparse as a positional -- every job launched from
    the packaged app would die instantly, leaving an empty log and a "job
    started" that never ran.

    Two escapes exist and they are not equivalent:

    * a real Python (`job_python()`), which has the research stack -- preferred;
    * the .exe re-entering itself via `--run-module`, dispatched by
      `desktop/aegis_desktop.py` before argparse. That path works for jobs whose
      imports are all inside the bundle, and is the fallback when no interpreter
      can be found.

    A non `-m` argv is passed through unchanged rather than silently mangled.
    """
    if not getattr(sys, "frozen", False):
        return [sys.executable, *args]
    py = job_python()
    if py:
        return [py, *args]
    if args[:1] == ["-m"]:
        return [sys.executable, "--run-module", args[1], *args[2:]]
    return [sys.executable, *args]


def _run_path(pid: int) -> Path:
    return RUNS_DIR / f"run_{pid}.json"


def _registry() -> list[dict]:
    if not RUNS_DIR.exists():
        return []
    out = []
    for p in sorted(RUNS_DIR.glob("run_*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return out


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            r = qsp.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True, text=True, timeout=10)
            return str(pid) in (r.stdout or "")
        os.kill(pid, 0)
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------- reads

@router.get("/services")
def services() -> dict:
    """What is running right now, with a PID for each thing that has one."""
    runs = []
    for r in _registry():
        r = dict(r)
        r["alive"] = _alive(int(r.get("pid") or 0))
        log = Path(r.get("log") or "")
        r["log_size_bytes"] = log.stat().st_size if log.exists() else 0
        r["log_mtime_utc"] = (datetime.fromtimestamp(log.stat().st_mtime, timezone.utc)
                              .isoformat(timespec="seconds") if log.exists() else None)
        runs.append(r)
    llama = {"url": LLAMA_URL, "reachable": False, "detail": "not probed"}
    try:
        import urllib.request
        with urllib.request.urlopen(f"{LLAMA_URL}/health", timeout=2) as fh:   # noqa: S310 localhost only
            llama = {"url": LLAMA_URL, "reachable": True, "detail": fh.read(200).decode("utf-8", "replace")}
    except Exception as exc:  # noqa: BLE001
        llama["detail"] = f"{type(exc).__name__}: {exc}"[:160]
    return {
        "utc": _now(),
        "control_enabled": _enabled(),
        "backend": {"pid": os.getpid(), "cwd": str(REPO)},
        "local_gguf": llama,
        "night_dir": str(NIGHT_DIR),
        "stop_file_present": (NIGHT_DIR / "STOP").exists(),
        "runs": runs,
        "jobs_available": whitelist(),
    }


@router.get("/jobs")
def jobs() -> dict:
    return {"utc": _now(), "queue": queue_jobs(), "extra": sorted(EXTRA_JOBS), "whitelist": whitelist()}


@router.get("/runs/{pid}/log")
def run_log(pid: int, tail: int = 4000) -> dict:
    p = _run_path(pid)
    if not p.exists():
        raise HTTPException(404, f"no run registered for pid {pid}")
    rec = json.loads(p.read_text(encoding="utf-8"))
    log = Path(rec.get("log") or "")
    text = log.read_text(encoding="utf-8", errors="replace")[-max(tail, 0):] if log.exists() else ""
    return {"pid": pid, "job": rec.get("job"), "alive": _alive(pid), "log": rec.get("log"), "tail": text}


@router.get("/leaderboard")
def leaderboard() -> dict:
    p = NIGHT_DIR / "LEADERBOARD.md"
    return {"utc": _now(), "path": str(p),
            "markdown": p.read_text(encoding="utf-8") if p.exists() else None,
            "receipts": sorted(x.name for x in NIGHT_DIR.glob("*_run*.json")) if NIGHT_DIR.exists() else []}


@router.get("/balances")
def balances() -> dict:
    """The provider's OWN balance line, not our telemetry (CLAUDE.md: reconcile
    spend against the provider). Paper equity is read from whatever the loops
    last wrote; this router never calls a venue."""
    last = None
    if BALANCE_FILE.exists():
        for line in BALANCE_FILE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    last = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
    return {"utc": _now(), "deepseek_balance_last_reading": last,
            "source": str(BALANCE_FILE),
            "note": "night-factory receipts all read llm_spend_usd 0.0; this file is the provider's side"}


# ------------------------------------------------------------------ writes

@router.post("/run/{job}")
def run_job(job: str, hours: float | None = None, run: int | None = None) -> dict:
    """Spawn ONE whitelisted job and register its pid. No shell, no free text."""
    _require_enabled()
    wl = whitelist()
    if job not in wl:
        raise HTTPException(400, f"{job!r} is not a whitelisted job id. Available: {wl}")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    NIGHT_DIR.mkdir(parents=True, exist_ok=True)
    if job in EXTRA_JOBS:
        args = list(EXTRA_JOBS[job])
    else:
        args = ["-m", "scripts.night_factory", "--job", job]
    if hours is not None:
        args += ["--hours", str(float(hours))]
    if run is not None:
        args += ["--run", str(int(run))]
    log = NIGHT_DIR / f"control_{job}_{int(time.time())}.log"
    # the child derives its own OUT from NIGHT_RUN_DATE; without this the board
    # this router reads and the directory the job writes can be different nights
    env = {**os.environ, "AEGIS_IGNORE_DOTENV": "1", "PYTHONIOENCODING": "utf-8",
           "NIGHT_RUN_DATE": NIGHT_DIR.name.replace("night_factory_", "")}
    with log.open("w", encoding="utf-8") as fh:
        proc = qsp.popen(child_argv(args), cwd=str(REPO), stdout=fh,
                         stderr=subprocess.STDOUT, env=env)
    rec = {"pid": proc.pid, "job": job, "argv": args, "log": str(log), "started_utc": _now()}
    _run_path(proc.pid).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return {"started": True, **rec}


@router.post("/night")
def run_night(hours: float = 4.0) -> dict:
    """One click: the whole queue, in order. The STOP file ends it between jobs."""
    _require_enabled()
    (NIGHT_DIR / "STOP").unlink(missing_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    NIGHT_DIR.mkdir(parents=True, exist_ok=True)
    log = NIGHT_DIR / f"control_night_{int(time.time())}.log"
    # the child derives its own OUT from NIGHT_RUN_DATE; without this the board
    # this router reads and the directory the job writes can be different nights
    env = {**os.environ, "AEGIS_IGNORE_DOTENV": "1", "PYTHONIOENCODING": "utf-8",
           "NIGHT_RUN_DATE": NIGHT_DIR.name.replace("night_factory_", "")}
    with log.open("w", encoding="utf-8") as fh:
        proc = qsp.popen(child_argv(["-m", "scripts.night_factory", "--hours", str(float(hours))]),
                         cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT, env=env)
    rec = {"pid": proc.pid, "job": "NIGHT_QUEUE", "argv": ["-m", "scripts.night_factory"],
           "log": str(log), "started_utc": _now()}
    _run_path(proc.pid).write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return {"started": True, **rec}


@router.post("/stop/{pid}")
def stop(pid: int, force_after_s: float = 0.0) -> dict:
    """STOP file first, then signal exactly ONE registered pid. Never by image name."""
    _require_enabled()
    p = _run_path(pid)
    if not p.exists():
        raise HTTPException(
            404, f"pid {pid} is not in this control plane's run registry; refusing to signal it. "
                 "Kill by a PID you wrote down, from the process that started it.")
    NIGHT_DIR.mkdir(parents=True, exist_ok=True)
    (NIGHT_DIR / "STOP").write_text(f"stop requested by the control plane at {_now()}\n", encoding="utf-8")
    if force_after_s > 0:
        deadline = time.time() + min(force_after_s, 120.0)
        while time.time() < deadline and _alive(pid):
            time.sleep(1.0)
    killed = False
    detail = "STOP file written; the queue ends between jobs"
    if force_after_s > 0 and _alive(pid):
        try:
            if os.name == "nt":
                qsp.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                        capture_output=True, timeout=20)
            else:
                os.kill(pid, signal.SIGTERM)
            killed = True
            detail = f"STOP file written, then pid {pid} signalled by PID (never by image name)"
        except Exception as exc:  # noqa: BLE001
            detail = f"STOP file written; signalling pid {pid} failed: {type(exc).__name__}"
    return {"pid": pid, "stop_file": str(NIGHT_DIR / "STOP"), "killed": killed,
            "alive": _alive(pid), "detail": detail, "utc": _now()}


@router.post("/stop-file/clear")
def clear_stop() -> dict:
    _require_enabled()
    existed = (NIGHT_DIR / "STOP").exists()
    (NIGHT_DIR / "STOP").unlink(missing_ok=True)
    return {"cleared": existed, "utc": _now()}


# --------------------------------------------------------------------------
# The local AI server: start, stop, status.
#
# Murat asked for a button (2026-09-10) because the only way to stop it today is
# `~/llama/llama-stop.cmd`, which runs `taskkill /IM llama-server.exe /F` -- kill
# by image name, banned since 2026-09-06 -- from a terminal. Every route here
# goes through `backend.services.llama_server`, which kills by PID or refuses.
# --------------------------------------------------------------------------

@router.get("/llama")
def llama_status() -> dict:
    from backend.services import llama_server as ls
    return ls.status()


@router.post("/llama/start")
def llama_start(wait_s: float = 90.0) -> dict:
    _require_enabled()
    from backend.services import llama_server as ls
    return ls.start(wait_s=max(0.0, min(wait_s, 600.0)))


@router.post("/llama/stop")
def llama_stop(allow_foreign: bool = False) -> dict:
    """Stop the local model server.

    `allow_foreign` is the consent gate: without it, a server Aegis did not
    start is REFUSED with `needs_confirmation`, because that process may be
    several GB into somebody else's job. The UI must show what it is stopping
    before it passes the flag.
    """
    _require_enabled()
    from backend.services import llama_server as ls
    return ls.stop(allow_foreign=bool(allow_foreign))


@router.post("/llama/stop-if-owned")
def llama_stop_if_owned() -> dict:
    """What the desktop shell calls as it closes. A server Aegis started is
    stopped; one that was already running is left alone."""
    _require_enabled()
    from backend.services import llama_server as ls
    return ls.stop_if_owned()


# --------------------------------------------------------------------------
# "Ask Aegis": the built-in assistant. A READER of receipts on the local model.
#
# It explains what is on disk. It cannot run a job, seal a book, arm a lane or
# place an order -- there is no code path from here to any of those, and
# `test_control_router_authority.py` asserts no broker is importable from this
# module. That is what keeps the "no LLM authority over real capital" invariant
# (CLAUDE.md, three licences) true rather than merely intended.
# --------------------------------------------------------------------------

#: the assistant's whole authority, stated to the model itself
# --------------------------------------------------------------------------
# Fleet vs the benchmark, with the uncertainty attached to every estimate.
#
# The 09-09 handoff's must-not-regress list, item 5: "uncertainty travels with
# the estimate", and its worked example: "beta 0.18 +/- 2.21 is not a beta".
# The fleet's first week produced exactly that shape -- four sessions, from
# which nothing is estimable -- and the number was quoted anyway.
#
# So this endpoint refuses to call anything estimable below a floor on the
# number of observations, and hands the page `se_daily_excess_pct` and
# `n_days` beside every mean. A page cannot print a bare number it was never
# given.
# --------------------------------------------------------------------------

#: below this many daily observations, a mean excess is reported but NOT
#: labelled estimable. Twenty sessions is a month of trading and is still thin;
#: it is a floor on absurdity, not a claim of power.
FLEET_MIN_DAYS = int(os.getenv("AEGIS_FLEET_MIN_DAYS", "20"))

#: the comparison series. It is a LANE by default, not SPY, and the payload says
#: so: quoting a lane-relative number under a "vs SPY" heading is the
#: `feedback_a_benchmark_relative_number_in_an_absolute_structure` error.
FLEET_BENCHMARK_LANE = os.getenv("AEGIS_FLEET_BENCHMARK_LANE", "balanced-ew-control")


def _nav_series() -> dict[str, list[tuple[str, float]]]:
    """Every LANE's NAV series. The `book:` namespace is excluded BY NAME.

    Lane B writes a paper book's marks into the same table under
    `portfolio_id = "book:<fingerprint>"` (`services/paper_books.py`). This
    table has no twin column and no twin row, and B3's rule is that a book's
    number is never shown without its twin's -- so a book must not arrive here
    and be rendered as a fourteenth lane. Books have their own endpoint
    (`/api/control/books`), which returns each book WITH its twins or not at
    all.
    """
    from backend.db import get_connection
    from backend.services.paper_books import is_book_id
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT portfolio_id, date, nav FROM paper_nav ORDER BY portfolio_id, date"
        ).fetchall()
    finally:
        conn.close()
    out: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        pid = r["portfolio_id"] if hasattr(r, "keys") else r[0]
        d = r["date"] if hasattr(r, "keys") else r[1]
        nav = r["nav"] if hasattr(r, "keys") else r[2]
        if nav is None or is_book_id(pid):
            continue
        out.setdefault(str(pid), []).append((str(d), float(nav)))
    return out


def _daily_returns(series: list[tuple[str, float]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for (d0, n0), (d1, n1) in zip(series, series[1:]):
        if n0:
            out[d1] = n1 / n0 - 1.0
    return out


def _excess_row(lane: str, series: list[tuple[str, float]],
                bench: dict[str, float] | None) -> dict:
    import statistics as st
    nav = series[-1][1] if series else None
    first = series[0][1] if series else None
    row = {
        "lane": lane, "nav": round(nav, 2) if nav is not None else None,
        "last_date": series[-1][0] if series else None,
        "since_inception_pct": (round((nav / first - 1) * 100, 3)
                                if nav is not None and first else None),
    }
    if bench is None:
        return {**row, "estimable": False,
                "why_not_estimable": f"no benchmark series ({FLEET_BENCHMARK_LANE}) to difference against",
                "excess_vs_benchmark_pct": None, "mean_daily_excess_pct": None,
                "se_daily_excess_pct": None, "t_stat": None, "n_days": 0}
    mine = _daily_returns(series)
    paired = [(mine[d] - bench[d]) for d in sorted(set(mine) & set(bench))]
    n = len(paired)
    if n < 2:
        return {**row, "estimable": False,
                "why_not_estimable": f"{n} paired session(s); a standard error needs at least 2",
                "excess_vs_benchmark_pct": None, "mean_daily_excess_pct": None,
                "se_daily_excess_pct": None, "t_stat": None, "n_days": n}
    mean = st.fmean(paired)
    se = st.stdev(paired) / (n ** 0.5)
    cum = 1.0
    for x in paired:
        cum *= (1.0 + x)
    return {**row,
            "excess_vs_benchmark_pct": round((cum - 1.0) * 100, 4),
            "mean_daily_excess_pct": round(mean * 100, 6),
            "se_daily_excess_pct": round(se * 100, 6),
            "t_stat": round(mean / se, 3) if se > 0 else None,
            "n_days": n,
            "estimable": n >= FLEET_MIN_DAYS,
            "why_not_estimable": (None if n >= FLEET_MIN_DAYS else
                                  f"{n} paired sessions is below the {FLEET_MIN_DAYS}-session floor; "
                                  f"the mean is shown with its standard error and should not be read "
                                  f"as an estimate of anything")}


@router.get("/fleet")
def fleet() -> dict:
    """Every lane against the declared benchmark lane, each with its own SE.

    Nothing here is annualised. An annualised figure from a handful of sessions
    is the same number wearing a bigger coat, and the coat is what gets quoted.
    """
    try:
        series = _nav_series()
    except Exception as exc:  # noqa: BLE001
        return {"utc": _now(), "error": f"{type(exc).__name__}: {exc}", "lanes": [],
                "note": "the NAV table could not be read; nothing is inferred from that"}
    if not series:
        # No local NAV rows. The lanes are marked to market by the remote
        # deployment, so this is the ordinary state of a local checkout -- say
        # so, and offer the cached snapshot if one was pulled, rather than
        # rendering an empty table that looks like a flat programme.
        snap = paper_snapshot()
        return {
            "utc": _now(), "lanes": [], "source": "none",
            "local_nav_rows": 0,
            "snapshot": snap,
            # the SPY correction travels even when there is nothing to compare:
            # the page heading says "vs SPY" in every state, so the payload has
            # to carry the correction in every state too
            "benchmark": {"lane": FLEET_BENCHMARK_LANE, "present": False, "n_days": 0,
                          "since_inception_pct": None,
                          "caveat": ("no local NAV rows to difference against. Note also that the "
                                     "benchmark is an EQUAL-WEIGHT CONTROL LANE, not SPY -- a "
                                     "lane-relative number printed under a 'vs SPY' heading is a "
                                     "benchmark-relative number in an absolute structure.")},
            "min_days_for_estimable": FLEET_MIN_DAYS,
            "note": ("This machine has no paper NAV rows: the lanes are marked to market by the "
                     "remote deployment. That is not a result and must not be read as one. "
                     "Pull once with POST /api/control/paper-snapshot/refresh (one request, "
                     "cached to disk, nothing polls it) -- or ignore it: every other page, "
                     "the night factory and the local model work entirely offline."),
        }
    bench_series = series.get(FLEET_BENCHMARK_LANE)
    bench = _daily_returns(bench_series) if bench_series else None
    lanes = [_excess_row(k, v, bench) for k, v in sorted(series.items())
             if k != FLEET_BENCHMARK_LANE]
    dates = sorted({d for v in series.values() for d, _ in v})
    return {
        "utc": _now(),
        "benchmark": {
            "lane": FLEET_BENCHMARK_LANE,
            "present": bench_series is not None,
            "n_days": len(bench) if bench else 0,
            "since_inception_pct": (round((bench_series[-1][1] / bench_series[0][1] - 1) * 100, 3)
                                    if bench_series and bench_series[0][1] else None),
            "caveat": ("this is an EQUAL-WEIGHT CONTROL LANE, not SPY. A lane-relative number "
                       "printed under a 'vs SPY' heading is a benchmark-relative number in an "
                       "absolute structure -- print the raw line beside the excess line."),
        },
        "inception_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
        "min_days_for_estimable": FLEET_MIN_DAYS,
        "lanes": lanes,
        "note": ("every mean carries its standard error and the count it was computed from. "
                 "Where `estimable` is false the mean is not an estimate of anything and must "
                 "not be rendered as one."),
    }


# --------------------------------------------------------------------------
# Paper-account data: LOCAL first, remote only when asked.
#
# Murat, 2026-09-10: "everything on the local model should be on the pc ...
# it can pull paper account data from railway maybe i dont want to increase the
# expense on the servers."
#
# So: the fleet endpoint reads the LOCAL NAV table and nothing else. The paper
# lanes are marked to market by the Railway deployment, so a local checkout has
# no rows -- and rather than silently reaching across the network on every page
# load, this is ONE endpoint the user clicks, which makes ONE request and caches
# the answer to disk. The fleet payload then says which it used and how old it is.
#
# The cost is stated in the response rather than implied: one HTTP GET per
# click, no polling, no background sync.
# --------------------------------------------------------------------------

#: the deployment that marks the paper lanes to market. Read-only; no orders.
PAPER_SOURCE_URL = os.getenv(
    "AEGIS_PAPER_SOURCE_URL", "https://aegis-finance-production.up.railway.app")
PAPER_CACHE = REPO / "backend" / "data" / "optimus" / "paper_snapshot.json"


@router.get("/paper-snapshot")
def paper_snapshot() -> dict:
    """What the last pull returned, and how old it is. Never fetches."""
    if not PAPER_CACHE.exists():
        return {"utc": _now(), "cached": False, "source": PAPER_SOURCE_URL,
                "note": ("no snapshot on disk. The paper lanes are marked to market by the "
                         "remote deployment, so a local checkout has no NAV rows until you "
                         "pull once via POST /api/control/paper-snapshot/refresh.")}
    try:
        blob = json.loads(PAPER_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"utc": _now(), "cached": False, "error": f"{type(exc).__name__}: {exc}",
                "path": str(PAPER_CACHE)}
    fetched = blob.get("fetched_utc")
    age_h = None
    if fetched:
        try:
            age_h = round((datetime.now(timezone.utc)
                           - datetime.fromisoformat(fetched)).total_seconds() / 3600.0, 2)
        except ValueError:
            age_h = None
    return {"utc": _now(), "cached": True, "fetched_utc": fetched, "age_hours": age_h,
            "source": blob.get("source"), "lanes": blob.get("lanes") or {},
            "inception_date": blob.get("inception_date"), "age_days": blob.get("age_days"),
            "note": "a cached read. Nothing was fetched to answer this."}


@router.post("/paper-snapshot/refresh")
def paper_snapshot_refresh(timeout_s: float = 30.0) -> dict:
    """The route. The gate is here; the one GET is in `paper_snapshot_fetch`."""
    _require_enabled()
    return paper_snapshot_fetch(timeout_s=timeout_s)


def paper_snapshot_fetch(timeout_s: float = 30.0) -> dict:
    """Pull the paper lanes once, from the deployment that marks them.

    ONE request. No polling, no background sync, no orders -- this reads
    `/api/health/full` and keeps the `track_record` block. The user asked not to
    add server expense, so the cost is exactly one GET per click and the
    response says so.

    SPLIT FROM THE ROUTE on 2026-09-11: the morning click calls this in-process,
    and a service calling a ROUTE inherits that route's `_require_enabled()`
    gate -- which the first real morning run hit, reporting
    `403 the control plane is disabled` for a step that had already been
    authorised by the route the operator clicked. A gate belongs at the edge,
    once.
    """
    import urllib.error
    import urllib.request
    url = f"{PAPER_SOURCE_URL.rstrip('/')}/api/health/full"
    started = time.time()
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout_s) as fh:   # noqa: S310 - fixed https host
            payload = json.loads(fh.read())
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "utc": _now(), "source": url,
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "note": ("nothing was cached and nothing local was changed. The app works "
                         "without this; only the paper-lane figures need it.")}
    tr = payload.get("track_record") or {}
    lanes = tr.get("lanes") or {}
    blob = {"fetched_utc": _now(), "source": url, "lanes": lanes,
            "inception_date": tr.get("inception_date"), "age_days": tr.get("age_days"),
            "requests_made": 1}
    PAPER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PAPER_CACHE.write_text(json.dumps(blob, indent=1), encoding="utf-8")
    return {"ok": True, "utc": _now(), "source": url, "n_lanes": len(lanes),
            "elapsed_s": round(time.time() - started, 2), "cached_to": str(PAPER_CACHE),
            "requests_made": 1,
            "note": "one GET. Nothing polls this; it refreshes only when you ask."}


# ===========================================================================
# THE DEVELOPER BOARD (O4) -- four read-only routes, and nothing that writes
# ===========================================================================
#
# The board is the desktop app's home page: services, the night, the fleet, the
# ledger, the code, the log. Its one rule is that every card shows a number WITH
# the path of the receipt it came from, or an em dash. A card that renders a
# plausible number from nowhere is the house failure mode in a nicer font.
#
# All four are GETs. None takes a parameter that reaches a shell or a write, and
# the two that take a path resolve it inside the checkout or refuse BY NAME.

#: The subtrees the file viewer will list. A short, named set rather than "the
#: whole repo": the viewer exists to read the code that runs the programme, and
#: `backend/data/` is gigabytes of parquet nobody wants paged into a browser.
TREE_ROOTS: dict[str, Path] = {
    "scripts": REPO / "scripts",
    "learner": REPO / "learner",
    "backend/services": REPO / "backend" / "services",
}

#: Suffixes the viewer will return. Everything else is refused BY TYPE rather
#: than truncated: a 40 MB parquet read as text is not a file view, it is a
#: hung browser.
_VIEWABLE_SUFFIXES = frozenset({".py", ".md", ".txt", ".json", ".yaml", ".yml",
                                ".toml", ".cfg", ".ini", ".sql", ".ts", ".tsx"})

#: 512 KB. The longest module under the declared roots is well inside it.
FILE_MAX_BYTES = 512 * 1024

#: Never served, at any path, whatever the sandbox says.
#:
#: The sandbox below confines every read to the checkout -- but `.env` IS in the
#: checkout, and this router answers on a localhost port a browser page can
#: reach. A file viewer that will hand back `DEEPSEEK_API_KEY=...` is not
#: read-only in any sense that matters. Secrets are refused by NAME, before the
#: path is resolved, and the refusal says which rule fired.
_NEVER_SERVED: tuple[str, ...] = (".env", "/.git/", "id_rsa", ".pem", ".key",
                                  "credential", "secret", "/.ssh/")


def _git() -> str:
    return os.getenv("GIT_EXECUTABLE") or "git"


def _rel(p) -> str:
    """Repo-relative and forward-slashed.

    An absolute Windows path in a receipt was one of the five causes of the
    two days of CI red in September, and it reads as somebody else's machine
    on every card that prints it."""
    try:
        return Path(p).resolve().relative_to(REPO.resolve()).as_posix()
    except (ValueError, OSError):
        return str(p)


def _tree_root_of(p: Path) -> str | None:
    """The declared root `p` lives under, or None if it lives under none."""
    for name, root in TREE_ROOTS.items():
        try:
            p.relative_to(root)
            return name
        except ValueError:
            continue
    return None


def _resolve_in_checkout(path: str) -> Path:
    """A request path -> an absolute path inside the checkout, or a refusal.

    The refusal NAMES the path. A bare "403 Forbidden" from a file viewer sends
    the reader to the network tab to find out what they asked for.
    """
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        raise HTTPException(status_code=422, detail="path is required")
    probe = "/" + raw.lower().lstrip("/")
    for pat in _NEVER_SERVED:
        if pat in probe:
            raise HTTPException(
                status_code=403,
                detail=(f"refused: {raw!r} matches the never-served rule {pat!r}. "
                        f"This viewer answers on localhost to a page in a browser; "
                        f"secrets are refused by name, not by hoping nobody asks."))
    candidate = Path(raw)
    resolved = (candidate if candidate.is_absolute() else REPO / candidate).resolve()
    try:
        resolved.relative_to(REPO.resolve())
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=(f"refused: {raw!r} resolves to {resolved}, which is outside "
                    f"the checkout at {REPO}")) from None
    return resolved


@router.get("/tree")
def tree(root: str = "scripts") -> dict:
    """List one declared subtree. Names and sizes only -- no content."""
    base = TREE_ROOTS.get(root)
    if base is None:
        raise HTTPException(
            status_code=404,
            detail=(f"unknown root {root!r}. Declared roots: "
                    f"{', '.join(sorted(TREE_ROOTS))}"))
    if not base.is_dir():
        return {"utc": _now(), "root": root, "path": _rel(base), "exists": False,
                "roots": sorted(TREE_ROOTS), "files": [], "n_files": 0,
                "max_bytes": FILE_MAX_BYTES,
                "note": f"{base} is not a directory in this checkout"}
    files = []
    for p in sorted(base.rglob("*")):
        if "__pycache__" in p.parts or not p.is_file():
            continue
        if p.suffix.lower() not in _VIEWABLE_SUFFIXES:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        files.append({"path": p.relative_to(REPO).as_posix(), "name": p.name,
                      "bytes": size, "too_big": size > FILE_MAX_BYTES})
    return {"utc": _now(), "root": root, "path": _rel(base), "exists": True,
            "roots": sorted(TREE_ROOTS), "n_files": len(files), "files": files,
            "max_bytes": FILE_MAX_BYTES}


@router.get("/file")
def file(path: str) -> dict:
    """One file's text, plus the last three commits that touched it.

    `git log -3` is the half that makes this a code viewer rather than a text
    box: "when did this last change, and what for" is the question a reader
    actually has, and it is not in the file.
    """
    p = _resolve_in_checkout(path)
    rel = p.relative_to(REPO.resolve()).as_posix()
    if not p.is_file():
        raise HTTPException(status_code=404, detail=f"no file at {rel}")
    if p.suffix.lower() not in _VIEWABLE_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(f"refused: {rel} is a {p.suffix or 'suffixless'} file. This "
                    f"viewer serves text; a binary read as text is a hung "
                    f"browser, not a file view."))
    size = p.stat().st_size
    if size > FILE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"refused: {rel} is {size} bytes, over the {FILE_MAX_BYTES} "
                    f"byte cap. Open it in an editor."))
    text = p.read_text(encoding="utf-8", errors="replace")
    commits: list[str] = []
    git_note = None
    try:
        out = qsp.run([_git(), "log", "-3", "--format=%h %ad %s", "--date=short",
                       "--", rel],
                      cwd=str(REPO), capture_output=True, text=True, timeout=20)
        if out.returncode == 0:
            commits = [ln for ln in (out.stdout or "").splitlines() if ln.strip()]
            if not commits:
                git_note = "no commit in this checkout has touched this path"
        else:
            git_note = (out.stderr or "").strip()[:300] or f"git exited {out.returncode}"
    except Exception as e:  # noqa: BLE001  a checkout without git still serves the file
        git_note = f"{type(e).__name__}: {e}"
    return {"utc": _now(), "path": rel, "abs": str(p), "bytes": size,
            "lines": len(text.splitlines()), "text": text,
            "root": _tree_root_of(p), "commits": commits,
            # Never empty-by-omission: "no commits" and "git could not be run"
            # are different answers, and [] cannot tell them apart.
            "git_note": git_note}


@router.get("/app-log")
def app_log(tail: int = 200) -> dict:
    """The last lines of `aegis_desktop.log`.

    A `console=False` build has nowhere for stdout to go, which is why this log
    exists at all -- and why it belongs on the board. The shutdown path and the
    backend's start line are observable nowhere else.
    """
    tail = max(1, min(int(tail), 5000))
    p = REPO / "backend" / "data" / "optimus" / "aegis_desktop.log"
    if not p.exists():
        return {"utc": _now(), "path": _rel(p), "exists": False, "lines": [],
                "note": ("no log yet. It is written by the desktop shell, so a "
                         "backend started any other way has none.")}
    try:
        raw = p.read_text(encoding="utf-8", errors="replace").splitlines()
        size = p.stat().st_size
    except OSError as e:
        return {"utc": _now(), "path": _rel(p), "exists": True, "lines": [],
                "error": f"{type(e).__name__}: {e}"}
    return {"utc": _now(), "path": _rel(p), "exists": True, "bytes": size,
            "n_lines_total": len(raw), "tail": tail, "lines": raw[-tail:]}


def _graded_within(rows: list[dict], hours: int = 24) -> int:
    """How many records were GRADED in the last `hours`.

    Counted here rather than read off the health row, which reports totals:
    "42 resolved ever" and "0 resolved yesterday" are the same number on a dead
    resolver, and the second is the one that says the loop is alive.

    `resolved_at` is written as a DATE (`str(today)`), so a same-day grade has
    no time of day at all. A bare date counts if it is today or yesterday --
    the coarsest honest reading of "in the last 24 hours" the field supports,
    and the card says `resolved_at is a date` beside it.
    """
    now = datetime.now(timezone.utc)
    cutoff_dt = now - timedelta(hours=hours)
    cutoff_d = cutoff_dt.date()
    n = 0
    for r in rows:
        if r.get("outcome") is None:
            continue
        stamp = str(r.get("resolved_at") or "").strip()
        if not stamp:
            continue
        try:
            if len(stamp) <= 10:
                if datetime.fromisoformat(stamp).date() >= cutoff_d:
                    n += 1
                continue
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when >= cutoff_dt:
                n += 1
        except ValueError:
            continue
    return n


@router.get("/ledger")
def ledger() -> dict:
    """The forecast ledger's health and calibration, from `belief_state`.

    Open forecasts, what was graded in the last 24 h, and Brier by MODEL -- the
    slice that answers "is the local model any better than the engine", which is
    the reason forecasts are written down at all. `n_resolved: 0` is reported as
    such and never smoothed into a Brier of 0.5.
    """
    try:
        from backend.services import belief_state as BS
    except Exception as e:  # noqa: BLE001
        return {"utc": _now(), "available": False,
                "error": f"{type(e).__name__}: {e}"}

    path = getattr(BS, "PREDICTIONS", None)
    out: dict = {"utc": _now(), "available": True,
                 "path": _rel(path) if path else None,
                 "exists": bool(path and Path(path).exists()),
                 "graded_note": "resolved_at is a DATE, so 'last 24h' is today or yesterday"}
    for key, fn in (("health", BS.ledger_health),
                    ("calibration_by_model", lambda: BS.calibration(by="model"))):
        try:
            out[key] = fn()
        except Exception as e:  # noqa: BLE001  a read degrades to a report, never an exception
            out[key] = {"error": f"{type(e).__name__}: {e}"}
    rows: list[dict] = []
    try:
        rows = BS.read_predictions()
        out["n_open"] = sum(1 for r in rows
                            if r.get("outcome") is None and not r.get("void_reason"))
        out["graded_last_24h"] = _graded_within(rows, 24)
    except Exception as e:  # noqa: BLE001
        out["n_open"] = None
        out["graded_last_24h"] = None
        out["graded_note"] = f"{type(e).__name__}: {e}"

    # MURPHY'S DECOMPOSITION (M4). A flat Brier answers two questions at once and
    # the answers point in opposite directions: a forecaster that always says the
    # base rate is perfectly RELIABLE and has zero RESOLUTION, and the flat score
    # cannot tell it from one that is genuinely informative. The board draws the
    # reliability diagram from `overall.bins`; below 45 resolved records the
    # payload says `insufficient_n` rather than drawing one.
    try:
        from backend.services import calibration as CAL
        out["decomposition"] = CAL.report(rows)
    except Exception as e:  # noqa: BLE001  a read degrades to a report
        out["decomposition"] = {"available": False, "error": f"{type(e).__name__}: {e}"}
    return out


# ===========================================================================
# LANE B — the paper books, each WITH its twins (B1-B5)
# ===========================================================================
#
# THE ONE RULE OF THIS ENDPOINT. A book is never returned without its twins.
# Not "usually", not "when the page asks for them": the twins are nested INSIDE
# the book's own object, so there is no shape of this payload in which a client
# can render a book's number and omit its control's. B3's acceptance criterion
# is a property of the data, and a rule enforced by the renderer is a rule one
# refactor away from being gone.
#
# The estimability rule is the fleet card's, deliberately: `FLEET_MIN_DAYS`
# paired sessions before a mean daily excess may be called an estimate, and the
# standard error travels with every mean either way. Two surfaces that disagreed
# about when a number is estimable would be two different claims wearing one
# word.


@router.get("/books")
def books(include_retired: bool = False) -> dict:
    """Every paper book with its twins, its latest mark, and its forecasts."""
    try:
        from backend.services import paper_books as PB
    except Exception as exc:  # noqa: BLE001
        return {"utc": _now(), "available": False,
                "error": f"{type(exc).__name__}: {exc}", "books": []}
    try:
        all_books = PB.list_books()
        series = PB.nav_series()
    except Exception as exc:  # noqa: BLE001
        return {"utc": _now(), "available": False,
                "error": f"{type(exc).__name__}: {exc}", "books": [],
                "note": ("the book table could not be read; nothing is inferred "
                         "from that. A checkout with no books is not a "
                         "programme with no books.")}

    by_id = {b.book_id: b for b in all_books}
    forecasts = _book_forecasts({b.book_id for b in all_books})

    rows: list[dict] = []
    for book in all_books:
        if book.is_twin:
            continue
        if book.status == "retired" and not include_retired:
            continue
        twin_rows = []
        for tid in book.control_twin_ids:
            twin = by_id.get(tid)
            twin_rows.append({
                "book_id": tid,
                "kind": ((twin.strategy.engine_params.get("twin") or {}).get("kind")
                         if twin else None),
                "construction": twin.control_construction if twin else None,
                "present": twin is not None,
                **_book_mark(tid, series.get(tid) or []),
            })
        first_twin = (series.get(book.control_twin_ids[0])
                      if book.control_twin_ids else None)
        own = series.get(book.book_id) or []
        rows.append({
            **book.as_row(),
            **_book_mark(book.book_id, own),
            "vs_twin": _excess_row(book.book_id, own,
                                   _daily_returns(first_twin) if first_twin else None),
            "twins": twin_rows,
            "worst_case": _safe(lambda: PB.worst_case(book)),
            "forecasts": forecasts.get(book.book_id, _no_forecasts()),
        })
    return {
        "utc": _now(), "available": True, "books": rows,
        "n_books": len(rows),
        "n_twins": sum(len(r["twins"]) for r in rows),
        "min_days_for_estimable": FLEET_MIN_DAYS,
        "note": ("every book carries its twins inside its own row. A book's "
                 "number is never shown without its control's (B3), and the "
                 "payload has no shape in which it could be."),
    }


def _safe(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"[:200]}


def _book_mark(book_id: str, series: list) -> dict:
    """The realised facts about one book: NAV, when, how many marks.

    Observations, not estimates -- they carry no sampling error and are printed
    as they arrived. `n_marks` is beside them so a reader can see how thin the
    series is without having to ask.
    """
    if not series:
        return {"nav": None, "last_mark": None, "n_marks": 0,
                "since_inception_pct": None,
                "why_no_nav": ("no cadence pass has marked this book yet; run "
                               "`POST /api/control/morning` or wait for the "
                               "16:45 ET pass")}
    first, last = series[0][1], series[-1][1]
    return {"nav": round(last, 2), "last_mark": series[-1][0],
            "n_marks": len(series),
            "since_inception_pct": (round((last / first - 1) * 100, 4)
                                    if first else None)}


def _no_forecasts() -> dict:
    return {"n_open": 0, "n_graded": 0, "last_grade": None, "brier": None,
            "base_rate_brier": None,
            "why": "no forecast row has been written for this book yet"}


def _book_forecasts(book_ids: set) -> dict:
    """Open and graded forecast counts per book, plus the two Briers.

    The engine's Brier and the BASE-RATE row's Brier are returned together and
    always: the engine's number alone says nothing, because the whole question
    the ledger was built to answer is whether it beats a forecaster that looked
    at nothing.
    """
    out: dict[str, dict] = {}
    try:
        from backend.services import belief_state as BS
        rows = [r for r in BS.read_predictions() if r.get("ticker") in book_ids]
    except Exception as exc:  # noqa: BLE001
        return {b: {**_no_forecasts(), "error": f"{type(exc).__name__}: {exc}"[:200]}
                for b in book_ids}
    for r in rows:
        cur = out.setdefault(r["ticker"], {"n_open": 0, "n_graded": 0,
                                           "last_grade": None,
                                           "_engine": [], "_base": []})
        if r.get("outcome") is None and not r.get("void_reason"):
            cur["n_open"] += 1
            continue
        if r.get("brier") is None:
            continue
        cur["n_graded"] += 1
        if not cur["last_grade"] or str(r.get("resolved_at")) > cur["last_grade"]:
            cur["last_grade"] = str(r.get("resolved_at"))
        (cur["_base"] if r.get("specialist") == "base_rate"
         else cur["_engine"]).append(float(r["brier"]))
    for book_id, cur in out.items():
        eng, base = cur.pop("_engine"), cur.pop("_base")
        cur["brier"] = round(sum(eng) / len(eng), 5) if eng else None
        cur["base_rate_brier"] = round(sum(base) / len(base), 5) if base else None
        cur["n_engine_graded"] = len(eng)
        cur["n_base_rate_graded"] = len(base)
        cur["reading"] = (
            "the engine's Brier is only meaningful beside the base-rate row's: "
            "if they are equal the trailing-IR stand-in carries no information")
    return out


@router.post("/books/create-from-contract")
def create_book_from_contract(payload: dict = Body(...)) -> dict:
    """Create a book AND its twins from a `Strategy` JSON. Control-plane gated.

    This is how the first `origin=night_job` books get seeded by a script. It is
    NOT B2's human hold step: `origin="human_text"` is refused here, because the
    sentence Murat typed and the click he made are the two things that make a
    book his, and a route that could mint one without them would make the
    distinction unauditable. B2 arrives in chunk 6.

    No order path is reachable from here and none may be: this writes a contract
    row and a NAV namespace, and the router's AST test keeps the whole module
    broker-free.
    """
    _require_enabled()
    from backend.services.paper_books import (CADENCES, ORIGINS, BookError, create,
                                              worst_case)
    from backend.services.paper_books import _strategy_from_dict
    from backend.strategy.contract import StrategyError

    contract = payload.get("strategy") or payload.get("contract")
    if not isinstance(contract, dict):
        raise HTTPException(422, "body needs a `strategy` object: the frozen "
                                 "contract, as `Strategy.as_dict()` returns it")
    cadence = str(payload.get("cadence") or "")
    origin = str(payload.get("origin") or "night_job")
    if origin == "human_text":
        raise HTTPException(
            422, "origin 'human_text' is B2's human hold step (chunk 6) and is "
                 "not mintable from a route. A book a human did not hold must "
                 "not be recorded as one he did.")
    if origin not in ORIGINS:
        raise HTTPException(422, f"origin must be one of {sorted(set(ORIGINS) - {'human_text'})}")
    # Validate the REQUEST before touching data. CI's checkout has no bars
    # file, and the first run there answered a bad cadence with 503 ("bars
    # unavailable") instead of 422 -- a request error reported as an
    # environment error, which is the wrong reader sent to the wrong place.
    if cadence not in CADENCES:
        raise HTTPException(422, f"cadence must be one of {list(CADENCES)}, not {cadence!r}")
    try:
        strategy = _strategy_from_dict(contract)
    except (StrategyError, TypeError, KeyError, ValueError) as exc:
        raise HTTPException(422, f"the contract was refused: {exc}") from exc

    bars = None
    try:
        from backend.services.paper_books import load_bars
        bars = load_bars()
    except Exception as exc:  # noqa: BLE001
        # The twins' draws need a universe. Without bars they would be built
        # from the declaration alone, which is a twin with no names in it --
        # refused rather than created empty.
        raise HTTPException(
            503, f"the local bars are unavailable, so no control twin can be "
                 f"drawn and a book without a twin is not created: {exc}") from exc
    try:
        book, twins = create(strategy, cadence=cadence, origin=origin,
                             origin_text=str(payload.get("origin_text") or ""),
                             ips_hash=payload.get("ips_hash"),
                             shadow=bool(payload.get("shadow")), bars=bars)
    except BookError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"utc": _now(), "created": True, "book": book.as_row(),
            "twins": [t.as_row() for t in twins],
            "worst_case": _safe(lambda: worst_case(book)),
            "note": ("the book and its twins are frozen and will be marked by "
                     "the next cadence pass. Nothing here places an order.")}


# ===========================================================================
# LANE A — THE AGENCY (A1-A5)
# ===========================================================================
#
# `docs/research_notes/2026-09-12/spec_agency_intake.md`. Four routes and one
# rule that outranks all of them: **a human holds.** `POST /agency/hold` is the
# only route in this repository that mints `origin="human_text"`, it is
# control-plane gated, and it records the sentence that was typed. Everything
# else here computes, and nothing here places an order.


@router.get("/agency/questionnaire")
def agency_questionnaire() -> dict:
    """The eight questions, their scales, and where each one comes from.

    A READ, and the reason the intake form is not eight strings typed into a
    page: a questionnaire whose items live in the UI cannot be versioned, and
    `AEGIS-RQ-1` is a hash input.
    """
    from backend.services import agency as AG
    return {"utc": _now(), "version": AG.QUESTIONNAIRE_VERSION,
            "questions": [{"qid": q.qid, "text": q.text,
                           "dimension": q.dimension, "scale": q.scale,
                           "source": q.source} for q in AG.QUESTIONS],
            "bands": [{"from": lo, "to": hi, "personality": p}
                      for lo, hi, p in AG.BANDS],
            "personalities": {name: row.as_row()
                              for name, row in AG.TABLE.items()},
            "constraint_vocabulary": {
                "pattern": AG.CONSTRAINT_RE.pattern,
                "esg_categories": sorted(AG.ESG_CATEGORIES)},
            "convention": ("composite = min(ability, willingness); the four "
                           "personalities are DECLARED PREFERENCES, never "
                           "inferred from the data a book will be graded on"),
            "limits": AG.LIMITS_SENTENCE}


@router.post("/agency/intake")
def agency_intake(payload: dict = Body(...)) -> dict:
    """A1 — `{capital, horizon_months, personality, constraints[],
    liquidity_need, answers[8]}` to a validated, hashed IPS.

    Gated: it may call the local model to draft the prose, which is a decision
    about this machine. Nothing is written to any ledger by this route — the
    IPS is returned to the caller, and it becomes durable only when a human
    holds one of the options it proposes.
    """
    _require_enabled()
    from backend.services import agency as AG
    try:
        ips = AG.intake(
            capital=payload.get("capital"),
            horizon_months=payload.get("horizon_months"),
            personality=payload.get("personality"),
            constraints=payload.get("constraints") or [],
            liquidity_need=float(payload.get("liquidity_need") or 0.0),
            answers=payload.get("answers"),
            prior_ips=payload.get("prior_ips"),
            draft=bool(payload.get("draft", True)))
    except AG.AgencyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"the intake was refused: {exc}") from exc
    # The policy is STORED under its own hash so that `hold` can name it by
    # hash alone. Nothing about a book is written here.
    saved = _safe(lambda: _rel(AG.save_ips(ips)))
    return {"utc": _now(), "ips_path_rel": saved, **ips.as_payload()}


def _agency_bars():
    """The local bars, or a 503 naming what is missing.

    Same refusal as `create-from-contract`: without bars no control twin can
    be drawn, and an option shown without its twin is the thing B3 exists to
    prevent. A proposal is exactly the moment a human compares numbers.
    """
    try:
        from backend.services.paper_books import load_bars
        return load_bars()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            503, f"the local bars are unavailable, so no control twin can be "
                 f"drawn and no option is shown without one: {exc}") from exc


@router.post("/agency/propose")
def agency_propose(payload: dict = Body(...)) -> dict:
    """A2 — three books from one IPS, each with its twins and its worst case.

    Takes `{ips_hash}` (the policy the intake stored) or an inline `{ips}`
    document. Writes nothing: a proposal is a comparison, and the books exist
    only once a human holds one.
    """
    from backend.services import agency as AG
    ips = _load_agency_ips(payload)
    bars = _agency_bars()
    try:
        options = AG.propose(ips, bars=bars, signal=payload.get("signal"))
    except AG.AgencyError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"utc": _now(), **AG.propose_payload(ips, options)}


def _load_agency_ips(payload: dict):
    """`{ips_hash}` from the store, or an inline `{ips}` document, revalidated.

    An inline document is accepted because a page that has just run the intake
    already holds one and should not have to trust a round trip — but it is
    validated and re-hashed exactly like a stored one, and a mismatch between
    the document and the `ips_hash` beside it is a refusal rather than a
    preference for whichever arrived first.
    """
    from backend.services import agency as AG
    doc = payload.get("ips")
    want = payload.get("ips_hash")
    if isinstance(doc, dict) and doc:
        try:
            AG.validate_document(doc)
            recomputed = AG.ips_hash(doc)
        except AG.AgencyError as exc:
            raise HTTPException(422, str(exc)) from exc
        if recomputed != doc.get("ips_hash") or (want and want != recomputed):
            raise HTTPException(
                422, f"the IPS document hashes to {recomputed} and the request "
                     f"says {want or doc.get('ips_hash')}. One of the two has "
                     f"been edited; the engine does not pick which.")
        row = AG.TABLE[str(doc["personality"])]
        return AG.IPS(document=doc, validator="revalidated",
                      numbers=AG.numeric_fields(doc, row))
    if not want:
        raise HTTPException(422, "body needs `ips_hash` (a policy the intake "
                                 "stored) or an inline `ips` document")
    try:
        return AG.load_ips(str(want))
    except AG.AgencyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/agency/hold")
def agency_hold(payload: dict = Body(...)) -> dict:
    """A2 — a human holds ONE option; the other two become shadow books.

    THE ONLY ROUTE THAT MINTS `origin="human_text"`. It is control-plane gated,
    it refuses without the sentence, and it records the sentence verbatim: that
    marker is the whole distinction between a book a person chose and a book a
    job produced, and `create-from-contract` refuses to mint one for exactly
    this reason.

    Nothing here places an order. A book is a frozen contract and a NAV series.
    """
    _require_enabled()
    from backend.services import agency as AG
    from backend.services.paper_books import BookError
    ips = _load_agency_ips(payload)
    bars = _agency_bars()
    try:
        return {"utc": _now(), **AG.hold(
            ips,
            chosen_contract_hash=str(payload.get("chosen_contract_hash") or ""),
            sentence=str(payload.get("sentence") or ""),
            bars=bars, signal=payload.get("signal"))}
    except AG.AgencyError as exc:
        raise HTTPException(422, str(exc)) from exc
    except BookError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/agency/protect-first")
def agency_protect_first(book_id: str | None = None) -> dict:
    """A4 — the flip log, with the base-rate control beside every flip.

    A READ. It never checks for a breach and never flips: the breach rule runs
    once per session inside the Morning, on the NAV that pass marked, and a
    route that could flip on a GET would flip whenever a page refreshed.
    """
    from backend.services import agency as AG
    rows = AG.read_flips()
    if book_id:
        rows = [r for r in rows if book_id in (r.get("book_id"),
                                               r.get("to_book_id"))]
    return {"utc": _now(), "n_flips": len(rows),
            "n_open": sum(1 for r in rows if not r.get("reversed_utc")),
            "flips": rows,
            "ledger_rel": _rel(AG.flips_path()),
            "reading": ("the flip count alone says nothing: read it against "
                        "`base_rate_control` on the same row, which is how "
                        "often the same rule fires on the book's own twin"),
            "limits": AG.LIMITS_SENTENCE}


@router.post("/agency/unflip")
def agency_unflip(payload: dict = Body(...)) -> dict:
    """A4 — a HUMAN reverses a protect-first flip. Gated.

    The engine never reverses its own flip: protect-first is one-directional
    automatically and bidirectional only by hand, which is CLAUDE.md's "no LLM
    authority over real capital" extended to paper capital's protective state.
    """
    _require_enabled()
    from backend.services import agency as AG
    try:
        row = AG.unflip(book_id=payload.get("book_id"),
                        flip_seq=payload.get("flip_seq"),
                        by=str(payload.get("by") or "human"))
    except AG.AgencyError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"utc": _now(), "reversed": True, "flip": row,
            "limits": AG.LIMITS_SENTENCE}


@router.get("/agency/review")
def agency_review_latest(day: str | None = None) -> dict:
    """A3 — today's calls, READ from the morning receipt that wrote them.

    A READ, and deliberately not a re-run: the calls a page shows must be the
    ones whose forecast rows are on disk, and a route that recomputed them
    would produce a second set of numbers with no rows behind them. If the
    morning has not run, that is a 200 with a reason — the Ask page asks "what
    happens today?" and "the morning has not run" is the answer, not a 404.
    """
    from backend.services import agency as AG
    from backend.services import morning as M
    blob = M.latest_receipt(day)
    if blob is None:
        return {"utc": _now(), "ran": False, "date": day or _now()[:10],
                "calls": [], "vocabulary": list(AG.DECISIONS),
                "note": ("no morning receipt for this day, so no review has "
                         "been written. POST /api/control/morning runs it."),
                "limits": AG.LIMITS_SENTENCE}
    step = next((s for s in (blob.get("steps") or [])
                 if s.get("step") == "agency_review"), None)
    if step is None:
        return {"utc": _now(), "ran": True, "date": blob.get("date"),
                "calls": [], "vocabulary": list(AG.DECISIONS),
                "note": ("this morning receipt predates the agency review "
                         "step; it has no calls in it, which is not the same "
                         "as a review that found nothing to say."),
                "limits": AG.LIMITS_SENTENCE}
    return {"utc": _now(), "ran": True, "date": blob.get("date"),
            "status": step.get("status"), "reason": step.get("reason"),
            "n_books": step.get("n_books"), "n_calls": step.get("n_calls"),
            "n_refused": step.get("n_refused"),
            "calls": step.get("calls") or [],
            "refused": step.get("refused") or [],
            "protect_first": step.get("protect_first"),
            "vocabulary": list(AG.DECISIONS),
            "receipt_rel": _rel(blob.get("path")) if blob.get("path") else None,
            "limits": AG.LIMITS_SENTENCE}


# ===========================================================================
# ONE CLICK = MORNING (O5)
# ===========================================================================
#
# The button runs `services/morning.py` IN THIS PROCESS. Not a subprocess, and
# not a scheduler job: in desktop mode the twelve APScheduler jobs are
# deliberately not registered (`main.py::_desktop_background_off`), so the
# laptop has no clock at all and the operator IS the clock. The step list, the
# statuses and the receipt shape all live in the service; this route's whole job
# is to be the one place that refuses when the control plane is off.


@router.post("/morning")
def morning(network: bool = True) -> dict:
    """Run the morning, write one receipt, hand back the step table.

    `network=false` is for a machine that has none: every network step then
    reports `skipped` with the caller named, rather than spending a minute
    timing out into a refusal that says the same thing more slowly.
    """
    _require_enabled()
    from backend.services import morning as M
    receipt = M.run_morning(do_network=bool(network))
    receipt["path_rel"] = _rel(receipt.get("path"))
    return receipt


@router.get("/morning")
def morning_latest(day: str | None = None) -> dict:
    """Today's newest morning receipt, or a row saying it has not run.

    A READ. The Ask page loads this before answering "what happens today?", and
    the board renders its step table -- so "the morning has not run" has to be a
    200 with a reason, not a 404 the page has to interpret.
    """
    from backend.services import morning as M
    blob = M.latest_receipt(day)
    if blob is None:
        return {"utc": _now(), "ran": False, "date": day or _now()[:10],
                "dir": _rel(M.MORNING_DIR),
                "declared_steps": [s for s, _ in M.STEPS],
                "note": ("no morning receipt for this day. POST /api/control/morning "
                         "runs it; nothing here runs it for you.")}
    blob["ran"] = True
    blob["utc"] = _now()
    blob["path_rel"] = _rel(blob.get("path"))
    return blob


# ===========================================================================
# THE UNIVERSE, UNCAPPED (O8)
# ===========================================================================
#
# Murat, 2026-09-11: "I want it to show all the stocks -- first time I opened I
# saw the 3,000+, and all of our reviews + analyst reviews."
#
# The scorecard for every name already exists:
# `backend/data/optimus/potential_universe/<day>.jsonl` -- one header row plus
# ONE ROW PER SYMBOL (3,056 on the 2026-09-02 vintage), each carrying the
# engine's ratio/upside, the learner's score, p_beat and the execution tier.
# `routers/candidates.py` already loads, merges and pages it, so this route
# REUSES those loaders rather than growing a second reader of the same file --
# two readers of one file is how two pages start disagreeing about how many
# names there are.
#
# What this route adds on top of `/api/candidates/universe` is the three
# board-only columns: which paper book holds the name, the analyst snapshot we
# have on disk, and the last thing WE said about it. Each is em-dashed when
# absent; none of them is ever inferred.

#: Local analyst snapshots (`backend/data/analyst_snapshots.jsonl`). Small, and
#: on the 1 = STRONG BUY Yahoo scale -- the OPPOSITE of the tracker's
#: `consensus` (5 = strong buy). Both are surfaced, each with its scale named,
#: because a page that prints "1.56" beside "4.15" without saying which way is
#: up has published two numbers and no fact.
ANALYST_SNAPSHOTS = REPO / "backend" / "data" / "analyst_snapshots.jsonl"

#: How many night directories the "last review" index reads. Bounded on
#: purpose: this is a UI convenience, and walking every receipt in the repo to
#: fill a column would make the first page load the slowest thing in the app.
REVIEW_INDEX_NIGHTS = 3

#: A one- or two-character ticker matches inside ordinary prose ("A", "ON",
#: "IT", "SO"), so the review index would attach a sentence about something
#: else to it. Those names get an em dash instead of a wrong sentence.
REVIEW_MIN_SYMBOL_LEN = 3

_UNIVERSE_CACHE: dict[str, tuple[float, object]] = {}
_UNIVERSE_CACHE_TTL_S = 300.0


def _memo(key: str, build):
    """A 5-minute memo for the three joins. Rebuilt, never stale-forever: the
    books change when a lane rebalances and the receipts change every night."""
    now = time.time()
    hit = _UNIVERSE_CACHE.get(key)
    if hit and now - hit[0] < _UNIVERSE_CACHE_TTL_S:
        return hit[1]
    value = build()
    _UNIVERSE_CACHE[key] = (now, value)
    return value


def _books_by_symbol() -> dict[str, list[str]]:
    """symbol -> the paper books holding it, from the volume DB. SELECT only.

    `/api/control/paper-snapshot` cannot answer this: it caches the remote
    deployment's `track_record` block, which is NAV per lane and carries no
    tickers at all. The names live in `paper_positions`, and `closed_at IS
    NULL` is that table's liveness filter (the MTM engine reads the same one;
    omitting it once made every name look duplicated).
    """
    out: dict[str, list[str]] = {}
    try:
        from backend.db import get_connection
    except Exception:  # noqa: BLE001
        return out
    try:
        conn = get_connection()
    except Exception:  # noqa: BLE001  no DB in this checkout -- every cell em-dashes
        return out
    try:
        rows = conn.execute(
            "SELECT portfolio_id, ticker FROM paper_positions "
            "WHERE closed_at IS NULL").fetchall()
    except Exception:  # noqa: BLE001
        rows = []
    finally:
        conn.close()
    for r in rows:
        try:
            sym = str(r["ticker"] or "").upper()
            lane = str(r["portfolio_id"] or "")
        except Exception:  # noqa: BLE001
            continue
        if sym and lane and lane not in out.setdefault(sym, []):
            out[sym].append(lane)
    return {k: sorted(v) for k, v in out.items()}


def _analyst_snapshots() -> dict[str, dict]:
    """ticker -> the newest local analyst snapshot row."""
    out: dict[str, dict] = {}
    if not ANALYST_SNAPSHOTS.exists():
        return out
    try:
        lines = ANALYST_SNAPSHOTS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        sym = str(row.get("ticker") or "").upper()
        if not sym:
            continue
        prev = out.get(sym)
        if prev is None or str(row.get("observed_at") or "") >= str(prev.get("observed_at") or ""):
            out[sym] = row
    return out


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _walk_strings(obj, out: list[str], budget: int = 4000) -> None:
    if len(out) >= budget:
        return
    if isinstance(obj, str):
        if len(obj) > 20:
            out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_strings(v, out, budget)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_strings(v, out, budget)


def _review_index() -> dict[str, dict]:
    """symbol -> {"sentence", "receipt"} from the newest night receipts.

    "The last review" is a sentence WE wrote, with the receipt it came from --
    which is the only version of that column worth having. A generated
    paraphrase with no receipt path is the thing the board exists not to show.

    The index is built over the newest `REVIEW_INDEX_NIGHTS` night directories,
    ordered by the DATE IN THEIR NAME and never by mtime: on a fresh checkout
    every file was written today, and a receipt dated from the filesystem is
    the defect that kept CI red for two days (protocol section 7).
    """
    base = REPO / "backend" / "data" / "optimus"
    if not base.is_dir():
        return {}
    nights = sorted((d for d in base.glob("night_factory_*") if d.is_dir()),
                    key=lambda d: d.name, reverse=True)[:REVIEW_INDEX_NIGHTS]
    index: dict[str, dict] = {}
    for night in nights:
        for p in sorted(night.glob("*.json")):
            try:
                blob = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            strings: list[str] = []
            _walk_strings(blob, strings)
            rel = p.relative_to(REPO).as_posix()
            for s in strings:
                for sent in _sentences(s):
                    for sym in set(re.findall(r"\b[A-Z]{%d,6}\b" % REVIEW_MIN_SYMBOL_LEN, sent)):
                        # Newest night wins; within a night, the first hit wins.
                        if sym not in index:
                            index[sym] = {"sentence": sent[:400], "receipt": rel}
    return index


_UNIVERSE_SORTS = ("upside", "symbol", "p_beat", "consensus", "dollar_volume",
                   "market_cap", "ret_12m")


@router.get("/universe")
def universe(offset: int = 0, limit: int = 100, q: str | None = None,
             sort: str = "upside", dir: str = "desc", day: str | None = None) -> dict:
    """Every name in the tracker universe, paged and searched SERVER-side.

    The header prints `rows_shown / universe_rows` and the two are computed
    from the same file, so a page that shows 100 of 3,056 says so and a page
    that has silently lost 2,900 names cannot look complete.
    """
    if sort not in _UNIVERSE_SORTS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown sort {sort!r}. Allowed: {sorted(_UNIVERSE_SORTS)}")
    if dir not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="dir must be asc or desc")
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    try:
        from backend.routers import candidates as CAND
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503,
                            detail=f"the candidates reader is unavailable: {e}") from None
    try:
        pu_day, header, scorecards, pu_vin = CAND._load_potential_universe(day)
        _, tracker_by_symbol, tr_vin = CAND._load_tracker_day(pu_day)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001  a read degrades to a report
        return {"utc": _now(), "available": False,
                "error": f"{type(e).__name__}: {e}",
                "universe_source": None, "universe_rows": 0, "rows": []}

    # `backend.config` the MODULE, not its `config` dict: the candidate paths
    # are module attributes, and importing the dict here once returned a dict
    # and an AttributeError.
    from backend import config as _cfg
    source = _cfg.CANDIDATE_POTENTIAL_UNIVERSE_DIR / f"{pu_day}.jsonl"
    try:
        src_rel = source.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        src_rel = str(source)

    books = _memo("books", _books_by_symbol)
    snaps = _memo("analyst_snapshots", _analyst_snapshots)
    reviews = _memo("reviews", _review_index)

    rows = []
    needle = (q or "").strip().upper()
    for sc in scorecards:
        sym = str(sc.get("symbol") or "")
        if needle and needle not in sym.upper():
            continue
        base = CAND._row(sc, tracker_by_symbol.get(sym), tr_vin["status"])
        band = base["band"]
        snap = snaps.get(sym.upper())
        rows.append({
            "symbol": sym,
            "sector": base["sector"],
            "exchange": base["exchange"],
            "verdict": base["reason"]["verdict"],
            "tracker_status": base["reason"]["tracker_status"],
            # OUR scorecard: the sealed upside and the consensus the books read.
            "upside": band["upside"],
            "ratio": band["ratio"],
            "consensus_tracker": band["consensus"],
            "consensus_scale": "5 = STRONG BUY (tracker)",
            "n_analysts": band["n_analysts"],
            "coverage": band["coverage"],
            "p_beat": base["our_estimate"]["p_beat"]["debiased"],
            "learner_score": base["our_estimate"]["learner_v1"]["score"],
            "median_dollar_volume": base["execution"]["median_dollar_volume"],
            "execution_tier": base["execution"]["tier"],
            "market_cap_usd": base["market_cap_usd"],
            "ret_12m": base["ret_12m"],
            # The local analyst snapshot, on the OTHER scale, named as such.
            "analyst_snapshot": ({
                "observed_at": snap.get("observed_at"),
                "target_mean": snap.get("target_mean"),
                "consensus_rating": snap.get("consensus_rating"),
                "consensus_label": snap.get("consensus_label"),
                "n_analysts": snap.get("n_analysts"),
                "scale": "1 = STRONG BUY (Yahoo)",
                "source": ANALYST_SNAPSHOTS.name,
            } if snap else None),
            "books": books.get(sym.upper()) or [],
            # L2 has not landed; the column exists and is honest about it.
            "last_event": None,
            "last_review": reviews.get(sym.upper()),
        })

    key = {
        "symbol": lambda r: (r["symbol"] or ""),
        "upside": lambda r: r["upside"],
        "p_beat": lambda r: r["p_beat"],
        "consensus": lambda r: r["consensus_tracker"],
        "dollar_volume": lambda r: r["median_dollar_volume"],
        "market_cap": lambda r: r["market_cap_usd"],
        "ret_12m": lambda r: r["ret_12m"],
    }[sort]
    reverse = dir == "desc"
    # Missing values sort LAST in both directions -- a None that sorts first
    # puts the names we know least about at the top of a ranked page.
    rows.sort(key=lambda r: (key(r) is None, key(r) if key(r) is not None else 0),
              reverse=False)
    if reverse:
        known = [r for r in rows if key(r) is not None]
        unknown = [r for r in rows if key(r) is None]
        known.reverse()
        rows = known + unknown

    page = rows[offset: offset + limit]
    return {
        "utc": _now(),
        "available": True,
        "universe_source": src_rel,
        "universe_day": pu_day,
        "universe_rows": len(scorecards),
        "n_matched": len(rows),
        "rows_shown": len(page),
        "offset": offset,
        "limit": limit,
        "sort": {"key": sort, "dir": dir,
                 "missing_values": "sorted last in both directions"},
        "q": q,
        "sorts": sorted(_UNIVERSE_SORTS),
        "vintage": pu_vin,
        "tracker_vintage": tr_vin,
        "joins": {
            "books": {"source": "paper_positions (volume DB), closed_at IS NULL",
                      "n_symbols": len(books)},
            "analyst_snapshot": {"source": ANALYST_SNAPSHOTS.relative_to(REPO).as_posix(),
                                 "exists": ANALYST_SNAPSHOTS.exists(),
                                 "n_symbols": len(snaps)},
            "last_review": {"source": f"the newest {REVIEW_INDEX_NIGHTS} night_factory_* directories",
                            "n_symbols": len(reviews),
                            "note": (f"symbols shorter than {REVIEW_MIN_SYMBOL_LEN} "
                                     f"characters are not indexed: they match ordinary "
                                     f"prose, and a wrong sentence is worse than an em dash")},
            "last_event": {"source": None,
                           "note": "lane L2 (typed events) has not landed; this column is em dashes"},
        },
        "counts": header.get("counts") or {},
        "conventions": header.get("conventions") or {},
        "rows": page,
    }


# ===========================================================================
# N-F — COVERAGE. "Asia first" becomes a number on the board.
# ===========================================================================
# Roadmap 2026-09-11 §3 N-F: per region and per source — last row age, rows
# today, 7-day trend, resolution rate, RED flags.
#
# Every number here is DERIVED from files on disk (the corpus day-files, the
# per-source cursors, the newest receipt) rather than from anything a pull
# reported into memory. That is the point: a coverage card that believed the
# pull's own summary would keep showing yesterday's success long after the pull
# stopped running. A source with no directory at all reports `rows_total: 0`
# and `status: NEVER_PULLED` — never an em dash that might be a zero.

#: A source is RED after this many consecutive zero-row runs. Read from the
#: cursor, which is the only thing that survives between runs.
COVERAGE_RED_ZERO_RUNS = 2

#: How many days of per-day counts the trend carries.
COVERAGE_TREND_DAYS = 7

#: A source whose newest row is older than this is STALE even if it never
#: recorded a zero-row run — a feed that 500s every time never records one.
COVERAGE_STALE_HOURS = 48


def _corpus_root() -> Path:
    from backend import config as _cfg
    return Path(_cfg.DATA_DIR) / "optimus" / "news_corpus"


def _newest_receipt(root: Path, source_id: str) -> dict:
    d = root / "_receipts"
    if not d.is_dir():
        return {}
    files = sorted(d.glob(f"*_{source_id}.json"))
    if not files:
        return {}
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _last_first_seen(path: Path) -> str:
    """The newest `first_seen_utc` in a day-file, read from the LAST lines.

    Rows are appended in write order, so the last line is the newest. Reading
    the whole corpus for this would make the card O(corpus) per request.
    """
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines[-5:]):
        try:
            return json.loads(line).get("first_seen_utc") or ""
        except Exception:  # noqa: BLE001
            continue
    return ""


def _coverage_for_source(src, root: Path, today: str, trend_days: list[str]) -> dict:
    d = root / src.id
    files = sorted(d.glob("*.jsonl")) if d.is_dir() else []
    by_day: dict[str, int] = {}
    rows_total = 0
    for f in files:
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                n = sum(1 for _ in fh)
        except OSError:
            n = 0
        rows_total += n
        by_day[f.stem] = n

    cursor: dict = {}
    cpath = root / "_cursors" / f"{src.id}.json"
    if cpath.exists():
        try:
            cursor = json.loads(cpath.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            cursor = {}
    receipt = _newest_receipt(root, src.id)

    newest = _last_first_seen(files[-1]) if files else ""
    age_h = None
    if newest:
        try:
            ts = datetime.fromisoformat(newest.replace("Z", "+00:00"))
            age_h = round((datetime.now(timezone.utc) - ts).total_seconds() / 3600.0, 2)
        except ValueError:
            age_h = None

    zeros = int(cursor.get("consecutive_zero_runs", 0) or 0)
    flags: list[str] = []
    if not src.implemented or src.parser == "none":
        status = "NOT_IMPLEMENTED"
        flags.append(src.implemented_note[:200] or "not implemented")
    elif not files and not cursor:
        status = "NEVER_PULLED"
    elif zeros >= COVERAGE_RED_ZERO_RUNS:
        status = "RED"
        flags.append(f"{zeros} consecutive zero-row runs")
    elif receipt.get("status") == "REFUSED":
        status = "REFUSED"
        flags.append((receipt.get("failures") or ["refused"])[0][:200])
    elif age_h is not None and age_h > COVERAGE_STALE_HOURS:
        status = "STALE"
        flags.append(f"newest row is {age_h:.0f}h old")
    elif not files:
        status = "NO_ROWS"
    else:
        status = "OK"

    return {
        "id": src.id, "provider": src.provider, "region": src.region,
        "language": src.language, "tier": src.tier,
        "pit_grade": src.pit_grade, "label_source": src.label_source,
        "implemented": src.implemented,
        "rows_total": rows_total,
        "rows_today": by_day.get(today, 0),
        "trend_7d": [by_day.get(day, 0) for day in trend_days],
        "last_row_utc": newest or None,
        "last_row_age_hours": age_h,
        "last_run_utc": cursor.get("last_run_utc"),
        "runs": int(cursor.get("runs", 0) or 0),
        "consecutive_zero_runs": zeros,
        "resolution_rate": receipt.get("resolution_rate"),
        "status": status,
        "flags": flags,
    }


@router.get("/coverage")
def coverage() -> dict:
    """N-F: per-source and per-region news coverage, derived from disk."""
    try:
        from backend.services import news_entities, news_registry
        sources = news_registry.load()
        meta = news_registry.meta()
    except Exception as e:  # noqa: BLE001 — a read degrades to a report, never a 500
        return {"utc": _now(), "available": False,
                "error": f"{type(e).__name__}: {e}",
                "sources": [], "regions": [], "totals": {}}

    root = _corpus_root()
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    trend_days = [(now.date() - timedelta(days=i)).isoformat()
                  for i in range(COVERAGE_TREND_DAYS - 1, -1, -1)]

    per = [_coverage_for_source(s, root, today, trend_days) for s in sources]

    regions: dict[str, dict] = {}
    for row in per:
        r = regions.setdefault(row["region"], {
            "region": row["region"], "sources": 0, "implemented": 0,
            "rows_total": 0, "rows_today": 0, "red": [], "never_pulled": [],
            "last_row_age_hours": None,
        })
        r["sources"] += 1
        r["implemented"] += 1 if row["implemented"] else 0
        r["rows_total"] += row["rows_total"]
        r["rows_today"] += row["rows_today"]
        if row["status"] in ("RED", "STALE", "REFUSED"):
            r["red"].append(row["id"])
        if row["status"] == "NEVER_PULLED":
            r["never_pulled"].append(row["id"])
        age = row["last_row_age_hours"]
        if age is not None and (r["last_row_age_hours"] is None or age < r["last_row_age_hours"]):
            r["last_row_age_hours"] = age

    rated = [r["resolution_rate"] for r in per if r["resolution_rate"] is not None]
    asia = [r for r in per if r["region"] in ("HK", "CN", "JP", "KR", "SG", "IN")]

    snap_dir = root.parent / "analyst_snapshots"
    snaps = sorted(p.stem for p in snap_dir.glob("*.parquet")) if snap_dir.is_dir() else []

    return {
        "utc": _now(),
        "available": True,
        "registry": meta,
        "corpus_dir": str(root),
        "corpus_exists": root.is_dir(),
        "sources": per,
        "regions": sorted(regions.values(), key=lambda r: -r["rows_total"]),
        "totals": {
            "sources": len(per),
            "implemented": sum(1 for r in per if r["implemented"]),
            "rows_total": sum(r["rows_total"] for r in per),
            "rows_today": sum(r["rows_today"] for r in per),
            "red": [r["id"] for r in per if r["status"] in ("RED", "STALE", "REFUSED")],
            "never_pulled": [r["id"] for r in per if r["status"] == "NEVER_PULLED"],
            "label_sources": [r["id"] for r in per if r["label_source"]],
            "mean_resolution_rate": round(sum(rated) / len(rated), 4) if rated else None,
        },
        "asia_first": {
            "regions": sorted({r["region"] for r in asia}),
            "rows_total": sum(r["rows_total"] for r in asia),
            "rows_today": sum(r["rows_today"] for r in asia),
            "note": ("'Asia first' as a NUMBER rather than a sentence. It counts every "
                     "source whose registry region is HK/CN/JP/KR/SG/IN; a GLOBAL source "
                     "that happens to carry Asian rows is not counted, so this is a "
                     "floor, not a ceiling."),
        },
        "name_table": news_entities.stats(),
        "analyst_snapshots": {
            "dir": str(snap_dir), "days": len(snaps),
            "series_starts": snaps[0] if snaps else None,
            "latest": snaps[-1] if snaps else None,
            "note": ("the analyst series starts the day the job first ran — yfinance "
                     "serves a current snapshot and Finnhub keeps ~4 months, so there "
                     "is no earlier history to fetch, only history to accumulate"),
        },
        "rules": {
            "red_after_zero_runs": COVERAGE_RED_ZERO_RUNS,
            "stale_after_hours": COVERAGE_STALE_HOURS,
            "label_rule": ("a source with pit_grade `index_state` may never label a "
                           "return (invariant 20); it is breadth on this card only"),
        },
    }
