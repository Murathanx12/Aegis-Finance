"""Compact machine-derived session state for Claude session starts.

The stale-handoff failure mode this replaces: a session writes an 8,000-word
handoff from memory, the next session believes it, and stale claims survive
forever. This script DERIVES state from the repo and the live deploy at the
moment a session starts, so the first thing a new session reads is measured,
not remembered. Human intent (attended queue, signatures) still lives in the
dated handoff docs — this payload points at the newest ones instead of
paraphrasing them.

Design constraints, deliberate:
  * stdlib only — runs under any python on PATH, no venv assumption, because
    a SessionStart hook that can crash is worse than no hook.
  * never raises; every section is ok / unavailable with a reason. An
    unreachable prod is a fact worth injecting, not a reason to be silent.
  * short timeouts (5 s) — session start must not hang on a dead network.
  * read-only everywhere.

Output: one JSON object on stdout (~70 lines). Claude Code adds SessionStart
hook stdout to the session context.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[1]
PROD = "https://aegis-finance-production.up.railway.app"
#: /api/health/full runs real checks and can take >5 s warm — measured at
#: first validation. Everything else answers fast.
TIMEOUT_S = 6
HEALTH_TIMEOUT_S = 15


def _get_json(url: str, timeout: int = TIMEOUT_S) -> dict:
    # the Railway edge resets bare python-urllib requests; a plain UA passes
    # — measured at first validation (curl ok, urllib WinError 10054)
    req = Request(url, headers={"User-Agent": "aegis-session-state/1"})  # noqa: S310
    with urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed host
        return json.loads(r.read().decode("utf-8"))


def _git(*args: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO), *args],
                         capture_output=True, text=True, timeout=15)
    return out.stdout.strip()


def local_section() -> dict:
    try:
        dirty = _git("status", "--porcelain")
        return {
            "status": "ok",
            "head": _git("rev-parse", "--short", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty_files": len([ln for ln in dirty.splitlines() if ln.strip()]),
            "last_commit": _git("log", "-1", "--format=%h %s"),
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(e)}


def prod_section() -> dict:
    try:
        h = _get_json(f"{PROD}/api/health/full", timeout=HEALTH_TIMEOUT_S)
        sched = h.get("scheduler") or {}
        return {
            "status": "ok",
            "deployed_commit": (h.get("deploy") or {}).get("commit"),
            "degraded_reasons": h.get("degraded_reasons") or [],
            "nav_all_fresh": (sched.get("nav") or {}).get("all_fresh"),
            "jobs": (sched.get("jobs") or {}).get("status",
                                                  sched.get("jobs")),
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(e)}


def arena_section() -> dict:
    try:
        a = _get_json(f"{PROD}/api/arena/status")
        books = a.get("books") or {}
        last_navs = [((b.get("last_nav") or {}).get("date"))
                     for b in books.values() if b.get("last_nav")]
        return {
            "status": "ok",
            "books": len(books),
            "seeded": sum(1 for b in books.values() if b.get("seeded")),
            "experiences": a.get("experiences"),
            "matured_outcomes": a.get("experience_outcomes"),
            "last_nav_date": max(last_navs) if last_navs else None,
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(e)}


def digest_section() -> dict:
    try:
        d = _get_json(f"{PROD}/api/optimus/digest")
        return {"status": "ok", "latest_day": d.get("day") or d.get("date")}
    except HTTPError as e:
        if e.code == 404:
            return {"status": "ok_empty",
                    "note": "no digest rows yet (first lands 18:15 ET)"}
        return {"status": "unavailable", "reason": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(e)}


def pointers_section() -> dict:
    """Newest dated docs — where human intent lives. Pointed at, not
    paraphrased: a paraphrase here would rot exactly like the handoffs did."""
    try:
        def newest(pattern: str, n: int) -> list[str]:
            # by mtime, not name: lexicographic put HANDOFF_OPUS5_* above
            # every dated handoff — measured at first validation
            files = sorted((REPO / "docs").glob(pattern),
                           key=lambda f: f.stat().st_mtime, reverse=True)
            return [f"docs/{f.name}" for f in files[:n]]
        return {
            "status": "ok",
            "handoffs_newest_first": newest("HANDOFF_*.md", 3),
            "roadmap_position": newest("ROADMAP_POSITION_*.md", 1),
        }
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "reason": str(e)}


def build_state() -> dict:
    return {
        "schema": "aegis-session-state-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "note": ("machine-derived at session start; trust this over any "
                 "remembered handoff claim. Human intent (attended queue, "
                 "signatures) is in the pointed-at docs."),
        "local": local_section(),
        "prod": prod_section(),
        "arena": arena_section(),
        "digest": digest_section(),
        "docs": pointers_section(),
        "standing": {
            "iif_clock": ("IIF-1 fires 17:00 local, ~2-min safe-launch "
                          "margin; nothing may load the machine 16:45-17:05 "
                          "or touch the AegisIIF1NightLauncher task"),
            "seed_flag": "AEGIS_SEED_ARENA is Murat's action, LAST",
            "date": str(date.today()),
        },
    }


def main() -> int:
    try:
        print(json.dumps(build_state(), indent=1, default=str))
    except Exception as e:  # noqa: BLE001 - a hook must never fail the session
        print(json.dumps({"schema": "aegis-session-state-v1",
                          "status": "unavailable", "reason": str(e)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
