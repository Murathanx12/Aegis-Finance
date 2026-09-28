"""How old is the backtest leaderboard? (lane M3, 2026-09-28)

The strategy-library factory (`scripts/night_backtest_factory.py`) has no
scheduled caller: its 868-cell board is exactly as fresh as the last person who
remembered to run it, and nothing went red when it aged -- the failure class the
44-day-old funnel file already cost (CLAUDE.md, "THE REAL BOTTLENECK WAS A
STATIC FILE"). This probe reads the newest `leaderboard_<run id>.json`:

* the date is the RUN ID in the file name (the producer's own stamp), cross-
  checked against the receipt's `run_id` field -- never the file's mtime (a
  fresh checkout makes every file "written today", CLAUDE.md protocol 7);
* ALIVE when the run is at most `config.BACKTEST_LEADERBOARD_STALE_DAYS` old,
  STALE beyond it, UNKNOWN when no receipt exists or its stamp cannot be dated
  (an undateable stamp is never fresh).

Registered in `system_health.PROBES` by one line; it reads nothing else.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

RUN_RE = re.compile(r"^leaderboard_(\d{4}-\d{2}-\d{2}T\d{6}Z)\.json$")
SUBDIR = "strategy_library"


def _threshold_days() -> float:
    from backend import config as C                                   # noqa: PLC0415
    return float(getattr(C, "BACKTEST_LEADERBOARD_STALE_DAYS", 7))


def run_time(run_id: str) -> Optional[datetime]:
    """`2026-09-27T082553Z` -> an aware UTC datetime; anything else None."""
    try:
        return datetime.strptime(str(run_id), "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def newest_leaderboard(lib_dir: Path) -> Optional[Path]:
    """The newest run-stamped leaderboard receipt, by the stamp in its NAME."""
    try:
        c = sorted(p for p in Path(lib_dir).glob("leaderboard_*.json") if RUN_RE.match(p.name))
    except OSError:
        return None
    return c[-1] if c else None


def leaderboard_age(lib_dir: Path, now: datetime, *, stale_days: Optional[float] = None) -> dict:
    """{verdict, run_id, evidence_utc, age_s, detail}. Pure: reads one folder."""
    stale_days = _threshold_days() if stale_days is None else float(stale_days)
    p = newest_leaderboard(lib_dir)
    if p is None:
        return {"verdict": "UNKNOWN", "run_id": None, "evidence_utc": None, "age_s": None,
                "detail": f"no leaderboard_<run id>.json in {lib_dir}: the factory has not run "
                          "here, so the board's age cannot be known"}
    run_id = RUN_RE.match(p.name).group(1)
    t = run_time(run_id)
    try:
        doc = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        doc = None
        body_why = f"unreadable ({type(e).__name__})"
    else:
        body_why = ""
    body_run = (doc or {}).get("run_id") if isinstance(doc, dict) else None
    if t is None:
        return {"verdict": "UNKNOWN", "run_id": run_id, "evidence_utc": None, "age_s": None,
                "detail": f"{p.name}: stamp cannot be dated; an undateable board is never fresh"}
    if doc is None or (body_run is not None and body_run != run_id):
        why = body_why or f"its run_id field says {body_run!r}"
        return {"verdict": "UNKNOWN", "run_id": run_id, "evidence_utc": t.isoformat(timespec="seconds"),
                "age_s": None, "detail": f"{p.name}: name and body disagree or body unreadable ({why})"}
    age_s = round((now - t).total_seconds(), 1)
    days = age_s / 86400.0
    verdict = "ALIVE" if days <= stale_days else "STALE"
    partial = (doc or {}).get("partial")
    detail = (f"newest backtest leaderboard {p.name}: {days:.1f} d old (threshold {stale_days:g} d)"
              + (f"; PARTIAL: {partial}" if partial else "")
              + ("" if verdict == "ALIVE" else
                 "; the factory has no scheduled caller -- rerun "
                 "`python -m scripts.night_backtest_factory` by hand"))
    return {"verdict": verdict, "run_id": run_id, "evidence_utc": t.isoformat(timespec="seconds"),
            "age_s": age_s, "detail": detail}


def p_backtest_leaderboard(ctx):
    """The `system_health` probe: `ctx.optimus_dir/strategy_library`."""
    from backend.services.system_health import ProbeResult          # noqa: PLC0415
    lib = ctx.path("backtest_leaderboard_dir", Path(ctx.optimus_dir) / SUBDIR)
    r = leaderboard_age(lib, ctx.now)
    return ProbeResult(r["verdict"], r["evidence_utc"], r["age_s"], r["detail"],
                       proof="run id in the file name, cross-checked with the body's run_id; never mtime")
