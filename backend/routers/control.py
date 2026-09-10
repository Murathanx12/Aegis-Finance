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
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/control", tags=["control"])

REPO = Path(__file__).resolve().parent.parent.parent
NIGHT_DIR = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-08"
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
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                               capture_output=True, text=True, timeout=10, shell=False)
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
    env = {**os.environ, "AEGIS_IGNORE_DOTENV": "1", "PYTHONIOENCODING": "utf-8"}
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen([sys.executable, *args], cwd=str(REPO), stdout=fh,
                                stderr=subprocess.STDOUT, env=env, shell=False)
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
    env = {**os.environ, "AEGIS_IGNORE_DOTENV": "1", "PYTHONIOENCODING": "utf-8"}
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen([sys.executable, "-m", "scripts.night_factory", "--hours", str(float(hours))],
                                cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT, env=env, shell=False)
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
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=20, shell=False)
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
ASK_SYSTEM = (
    "You are the Aegis desktop assistant. You READ receipts and explain them. "
    "You have no authority: you cannot run jobs, seal books, arm lanes, size positions "
    "or place orders, and you must never imply otherwise. "
    "Every number you state must appear in the context you were given; if a number is "
    "not there, say you do not have it rather than estimating. "
    "If a result has a control, quote the control beside it. If an estimate has a "
    "standard error, quote it. Answer in English."
)


def _ask_context(max_chars: int = 12000) -> dict:
    """The receipts the assistant is allowed to see, newest night first."""
    import glob
    parts: list[str] = []
    used: list[str] = []
    board = NIGHT_DIR / "LEADERBOARD.md"
    nights = sorted(glob.glob(str(NIGHT_DIR.parent / "night_factory_*")), reverse=True)
    for night in nights[:2]:
        b = Path(night) / "LEADERBOARD.md"
        if b.exists():
            parts.append(f"### {Path(night).name} leaderboard\n{b.read_text(encoding='utf-8')}")
            used.append(str(b))
    if not parts and board.exists():
        parts.append(board.read_text(encoding="utf-8"))
        used.append(str(board))
    text = "\n\n".join(parts)
    truncated = len(text) > max_chars
    return {"text": text[:max_chars], "sources": used, "truncated": truncated}


@router.post("/ask")
def ask(question: str, backend: str = "local_gguf", max_tokens: int = 700) -> dict:
    _require_enabled()
    q = (question or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="question is empty")
    from backend.services import free_inference as fi
    from backend.services import llama_server as ls
    st = ls.status()
    if backend == "local_gguf" and not st.get("ready"):
        # a refusal that names the fix, rather than a 500 from a dead socket
        return {"ok": False, "answer": None, "utc": _now(),
                "refusal": ("the local model is not ready: "
                            + str(st.get("detail"))
                            + ". Start it from the Services page (or POST /api/control/llama/start)."),
                "llama": st}
    ctx = _ask_context()
    prompt = (f"{ASK_SYSTEM}\n\n"
              f"--- RECEIPTS ON DISK (this is your only source of numbers) ---\n"
              f"{ctx['text']}\n"
              f"--- END RECEIPTS ---\n\n"
              f"Question: {q}\n")
    try:
        reply = fi.complete(backend=backend, prompt=prompt, max_tokens=int(max_tokens))
    except Exception as exc:  # noqa: BLE001 - surface the reason, never a blank page
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}") from exc
    text = getattr(reply, "text", None) or getattr(reply, "content", None) or str(reply)
    return {"ok": True, "utc": _now(), "question": q, "answer": text,
            "backend": backend, "model": st.get("model"),
            "context_sources": ctx["sources"], "context_truncated": ctx["truncated"],
            "authority": "READER ONLY: this endpoint cannot run, seal, arm or order anything",
            "cost_usd": 0.0}


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
    from backend.db import get_connection
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
        if nav is None:
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
