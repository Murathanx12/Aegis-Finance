"""How old is the public front-page pin? (2026-10-07 chunk: the public pictures refresh
themselves from the winners)

`scripts/render_public_assets.py` renders the README hero, the live results panel, the
architecture diagram, the social card and the motion page from a PINNED receipt pair
(`RESULTS_RUN_ID`). Nothing re-pins it except a human or `task_keeper assets`
(`scripts.render_public_assets --bump-pin`), scheduled weekly (`AegisPublicAssetsWeekly`,
Saturday `config.PUBLIC_ASSETS_REFRESH_HHMM` HKT). This probe is the "THE REAL BOTTLENECK WAS
A STATIC FILE" lesson (CLAUDE.md) applied here: read the PIN itself -- never a file's mtime --
and go red when it has not moved in too long, so a missed Saturday is visible instead of a
front page that is quietly a month stale.

* the date is the RUN ID in the pin, read as TEXT from `scripts/render_public_assets.py`
  under `ctx.repo` -- NEVER by importing the live module (a probe ctx pointed at an empty
  folder, as `test_system_health.test_every_probe_with_its_evidence_absent_is_not_alive`
  does for every probe, must see no evidence; importing the real installed module would find
  the real pin regardless of `ctx.repo` and falsely report ALIVE on an empty folder) and
  never a file mtime;
* ALIVE when the pin is at most `config.PUBLIC_ASSETS_MAX_PIN_AGE_DAYS` old, DEGRADED
  (`state="DEGRADED"`, coarse verdict STALE) beyond it, UNKNOWN when the pin cannot be read or
  dated (an undateable pin is never fresh).

Registered in `system_health.PROBES` by one line; it reads nothing else.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
#: Same pattern as `render_public_assets.PIN_RE`, duplicated deliberately: reading this
#: module's live `RESULTS_RUN_ID` global would not respect `ctx.repo` in a test harness (or a
#: worktree other than the running process's own), and the whole point is to read exactly
#: what is committed, from wherever the probe is told to look.
PIN_RE = re.compile(r'(?m)^RESULTS_RUN_ID = "([^"]*)"$')
PIN_SCRIPT = "scripts/render_public_assets.py"


def _threshold_days() -> float:
    from backend import config as C                                   # noqa: PLC0415
    return float(getattr(C, "PUBLIC_ASSETS_MAX_PIN_AGE_DAYS", 10))


def run_time(run_id: str) -> Optional[datetime]:
    """`2026-10-06T235345Z` -> an aware UTC datetime; anything else None."""
    try:
        return datetime.strptime(str(run_id), "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def pin_script_text(repo: Optional[Path] = None) -> Optional[str]:
    p = Path(repo or REPO) / PIN_SCRIPT
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def pinned_run_id(repo: Optional[Path] = None) -> Optional[str]:
    """The committed `RESULTS_RUN_ID`, read as text under `repo` (default: this repo)."""
    text = pin_script_text(repo)
    if text is None:
        return None
    m = PIN_RE.search(text)
    return m.group(1) if m else None


def pin_age(now: datetime, *, stale_days: Optional[float] = None, run_id: Optional[str] = None,
           repo: Optional[Path] = None) -> dict:
    """{verdict, run_id, evidence_utc, age_s, detail}. `run_id` is injectable for tests;
    production reads the real pin via `pinned_run_id(repo)`."""
    stale_days = _threshold_days() if stale_days is None else float(stale_days)
    rid = pinned_run_id(repo) if run_id is None else run_id
    if not rid:
        return {"verdict": "UNKNOWN", "run_id": None, "evidence_utc": None, "age_s": None,
                "detail": f"no RESULTS_RUN_ID could be read from {PIN_SCRIPT}: the pin's age "
                          "cannot be known"}
    t = run_time(rid)
    if t is None:
        return {"verdict": "UNKNOWN", "run_id": rid, "evidence_utc": None, "age_s": None,
                "detail": f"RESULTS_RUN_ID = {rid!r}: stamp cannot be dated; an undateable pin "
                          "is never fresh"}
    age_s = round((now - t).total_seconds(), 1)
    days = age_s / 86400.0
    verdict = "ALIVE" if days <= stale_days else "STALE"
    detail = (f"RESULTS_RUN_ID {rid}: {days:.1f} d old (threshold {stale_days:g} d)"
              + ("" if verdict == "ALIVE" else
                 "; DEGRADED -- the weekly refresh "
                 "(`python -m scripts.render_public_assets --bump-pin`, task_keeper `assets`) "
                 "has not landed; rerun it or check AegisPublicAssetsWeekly"))
    return {"verdict": verdict, "run_id": rid, "evidence_utc": t.isoformat(timespec="seconds"),
            "age_s": age_s, "detail": detail}


def p_public_assets(ctx):
    """The `system_health` probe: reads `ctx.repo`'s copy of the pin script, nothing else."""
    from backend.services.system_health import ProbeResult              # noqa: PLC0415
    r = pin_age(ctx.now, repo=getattr(ctx, "repo", None))
    state = "DEGRADED" if r["verdict"] == "STALE" else None
    return ProbeResult(r["verdict"], r["evidence_utc"], r["age_s"], r["detail"], state=state,
                       proof=f"RESULTS_RUN_ID in {PIN_SCRIPT}, parsed as a UTC stamp; "
                             "never a file's mtime")
