"""The PUBLIC view of the health, providers and scheduler endpoints.

`/api/health/full` was a debugging payload served to the internet: LLM usage and
spend, the last 50 WARNING log lines, provider failure reasons, absolute paths
of the deployment, exception text. The repo is public, so the code is not the
secret; the runtime state is. This module is the ONE place that decides what a
visitor or an uptime monitor may see.

Design rules (pinned by `backend/tests/test_health_public.py`):

* A WHITELIST projection, never a blacklist: a new key added to the full
  payload is invisible publicly until someone adds it here on purpose.
* Coarse status WORDS and freshness DATES only. No free text from a producer
  (`reason`, `error`, `detail`, `proof`, `where`, `message`), no numbers that are
  money, no filesystem paths, no environment-variable names.
* Defence in depth: every string that survives the whitelist still passes
  `withhold_unsafe`, which replaces anything shaped like a path, a traceback, an
  amount in dollars or an env-var name.
* The full view is reachable through `full_view_allowed` (the desktop control
  plane's own gate) or the `X-Health-Token` header (`token_state`); the compare
  is constant time and an unset token means "no hosted full view", never an
  open default.
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Any, Optional

from fastapi import HTTPException, Request

from backend.config import HEALTH_TOKEN_ENV, HEALTH_TOKEN_HEADER

WITHHELD = "[withheld]"

#: Shapes that must never reach a public payload.
UNSAFE_SHAPES = re.compile(
    r"(?:[A-Za-z]:[\\/]"                                    # C:\ or C:/
    r"|(?:^|[\s\"'(=])/(?:app|data|home|usr|var|tmp|mnt|opt|etc|srv|root|Users|proc)\b"
    r"|\\\\"                                                 # UNC / escaped backslash path
    r"|\b[\w.-]+/[\w./-]*\.(?:py|json|jsonl|parquet|db|csv|log|md|yaml|yml|txt)\b"
    r"|Traceback|\bFile \""                                  # exception text
    r"|\$\s?\d|\bUSD\b|\busd\b"                               # amounts of money
    r"|\b[A-Z][A-Z0-9]*_(?:API_)?(?:KEY|TOKEN|SECRET|PASSWORD)\b"   # env var names
    r"|\bAEGIS_[A-Z0-9_]+\b"
    r")")


def withhold_unsafe(value: Any) -> Any:
    """Recursively replace any string shaped like a path, a traceback, money or an
    env var name. Containers keep their shape; only the leaf is replaced."""
    if isinstance(value, str):
        return WITHHELD if UNSAFE_SHAPES.search(value) else value
    if isinstance(value, dict):
        return {k: withhold_unsafe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [withhold_unsafe(v) for v in value]
    return value


# ----------------------------------------------------------------- access ----

def token_state(request: Request) -> str:
    """"ok" | "unset" (no token configured) | "missing" | "bad"."""
    expected = os.environ.get(HEALTH_TOKEN_ENV, "")
    if not expected:
        return "unset"
    supplied = request.headers.get(HEALTH_TOKEN_HEADER)
    if not supplied:
        return "missing"
    return "ok" if hmac.compare_digest(supplied.encode(), expected.encode()) else "bad"


def full_view_allowed(request: Request) -> bool:
    """True for a desktop-control-plane request (the existing gate, unchanged) or
    a hosted request carrying the right token."""
    from backend.routers.control import control_plane_gate
    try:
        control_plane_gate(request)
        return True
    except HTTPException:
        pass
    return token_state(request) == "ok"


def require_full_view(request: Request) -> None:
    """Gate for `/api/health/detail`. 404 when nothing could ever unlock it (no
    control plane, no token configured), 403 otherwise."""
    if full_view_allowed(request):
        return
    from backend.routers.control import _enabled
    if not _enabled() and token_state(request) == "unset":
        raise HTTPException(status_code=404, detail="Not Found")
    raise HTTPException(status_code=403, detail="health detail refused")


# ------------------------------------------------------------- projections ---

def _pick(src: Any, keys: tuple[str, ...]) -> dict:
    src = src if isinstance(src, dict) else {}
    return {k: src[k] for k in keys if k in src}


def _status_only(block: Any) -> dict:
    return _pick(block, ("status",))


def public_scheduler(sched: Any) -> dict:
    """running, job count, per-lane NAV freshness, and the ids of missing or
    undeclared jobs (declared in the public repo). No jobstore class, no next-run
    map, no free-text reason, no exception text."""
    sched = sched if isinstance(sched, dict) else {}
    nav = sched.get("nav") if isinstance(sched.get("nav"), dict) else {}
    lanes = nav.get("lanes") if isinstance(nav.get("lanes"), dict) else {}
    jobs = sched.get("jobs") if isinstance(sched.get("jobs"), dict) else {}
    return {
        "running": bool(sched.get("running")),
        "n_jobs": sched.get("n_jobs") if isinstance(sched.get("n_jobs"), int) else 0,
        "persistent": bool(sched.get("persistent")),
        "last_mtm": sched.get("last_mtm"),
        "nav": {
            "all_fresh": bool(nav.get("all_fresh")),
            "expected_nav_date": nav.get("expected_nav_date"),
            "lanes": {lid: _pick(v, ("last_nav_date", "fresh"))
                      for lid, v in lanes.items() if isinstance(v, dict)},
        },
        "jobs": {
            "status": jobs.get("status"),
            "missing": [str(j) for j in (jobs.get("missing") or [])],
            "unexpected": [str(j) for j in (jobs.get("unexpected") or [])],
        },
    }


def public_subsystems(block: Any) -> dict:
    """Verdict, state, light and ages per subsystem. `detail`, `proof`, `where`
    and `probe` are producer free text (paths, hostnames, exception names) and
    are null here; the alarm keeps its light/status/validity but not `reason`."""
    block = block if isinstance(block, dict) else {}
    alarm_keys = ("light", "status", "healthy", "attention_required",
                  "evidence_mode", "valid_until_utc", "evidence_calendar")
    rows = []
    for r in block.get("rows") or []:
        if not isinstance(r, dict):
            continue
        row = _pick(r, ("name", "verdict", "state", "evidence_utc", "age_s", "age_s_now",
                        "cadence_s", "evidence_mode", "valid_until_utc",
                        "progressing", "same_output"))
        row.update({"probe": None, "where": None, "detail": None})
        if isinstance(r.get("alarm"), dict):
            row["alarm"] = _pick(r["alarm"], alarm_keys)
        rows.append(row)
    out = _pick(block, ("generated_utc", "source", "counts", "state_counts", "exit_code"))
    out["rows"] = rows
    if isinstance(block.get("alarm"), dict):
        out["alarm"] = _pick(block["alarm"], ("schema", "light", "status", "healthy",
                                              "attention_required", "light_counts"))
    return out


def public_health_full(full: dict, codes: list[str]) -> dict:
    """The public `/api/health/full`. `codes` are the coarse degraded codes
    computed beside the full reasons (`nav_not_fresh`, `fred_health`, ...)."""
    tr = full.get("track_record") if isinstance(full.get("track_record"), dict) else {}
    pops = (full.get("forecast_populations") or {}).get("populations") or {}
    fh = full.get("fred_health") if isinstance(full.get("fred_health"), dict) else {}
    out = {
        "view": "public",
        "status": full.get("status"),
        "degraded_reasons": list(codes),
        "deploy": _pick(full.get("deploy"), ("commit", "version", "started_at",
                                             "uptime_seconds", "cache_status")),
        "scheduler": public_scheduler(full.get("scheduler")),
        "track_record": {
            "inception_date": tr.get("inception_date"),
            "age_days": tr.get("age_days"),
            "lanes": {lid: _pick(v, ("last_date", "nav", "since_inception_pct"))
                      for lid, v in (tr.get("lanes") or {}).items() if isinstance(v, dict)},
        },
        "prediction_ledger": _pick(full.get("prediction_ledger"), ("status", "population_id")),
        "forecast_populations": {
            "status": (full.get("forecast_populations") or {}).get("status"),
            "populations": {pid: _pick(p, ("status", "days_quiet", "last_written"))
                            for pid, p in pops.items() if isinstance(p, dict)},
        },
        "investment_committee": _pick(full.get("investment_committee"),
                                      ("status", "funnel_available", "funnel_generated_at",
                                       "funnel_age_days")),
        "accrual_canary": _status_only(full.get("accrual_canary")),
        "event_store": _status_only(full.get("event_store")),
        "options_pit": _status_only(full.get("options_pit")),
        "execution_ledger": _status_only(full.get("execution_ledger")),
        "paper_broker": _status_only(full.get("paper_broker")),
        "information_bus": _status_only(full.get("information_bus")),
        "selector_identity": _status_only(full.get("selector_identity")),
        "fred_health": {
            **_pick(fh, ("status", "critical_series", "fetch_passes")),
            "by_status": {k: [str(s) for s in v] for k, v in (fh.get("by_status") or {}).items()
                          if isinstance(v, list)},
        },
        "subsystems": public_subsystems(full.get("subsystems")),
    }
    return withhold_unsafe(out)


def public_providers(payload: dict) -> dict:
    """Provider name, up/down and capabilities, plus the priority order. The
    `reason` string (what is missing, which key) is withheld."""
    return withhold_unsafe({
        "view": "public",
        "providers": [{"name": p.get("name"), "available": bool(p.get("available")),
                       "capabilities": list(p.get("capabilities") or [])}
                      for p in payload.get("providers") or []],
        "priority": payload.get("priority"),
    })


def public_scheduler_health(h: dict) -> dict:
    out = public_scheduler(h)
    out["view"] = "public"
    return withhold_unsafe(out)


def public_health_minimal(*, cache_ready: bool, cache_status: str, version: str,
                          git_head: Optional[str]) -> dict:
    """`/api/health` for a caller outside the control plane: 200, a few words."""
    return {"status": "ok", "version": version, "cache_ready": cache_ready,
            "cache_status": cache_status, "git_head": git_head}
