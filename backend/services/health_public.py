"""The PUBLIC view of the health, providers, scheduler and system-health endpoints.

`/api/health/full` was a debugging payload served to the internet: LLM usage and
spend, the last 50 WARNING log lines, provider failure reasons, absolute paths
of the deployment, exception text. The repo is public, so the code is not the
secret; the runtime state is. This module is the ONE place that decides what a
visitor or an uptime monitor may see.

EXACTLY WHAT IS ALLOW-LISTED (pinned by `backend/tests/test_health_public.py`)

1. KEYS: every public payload is built key by key from the builders below
   (`public_health_full`, `public_providers`, `public_scheduler_health`,
   `public_system_health`, `public_health_minimal`). A key a builder does not
   name is absent, whatever the producer put there.
2. VALUES: `_pick` copies SCALARS only (str, int, float, bool, None). A dict or
   list under a picked key is dropped. A container is kept only where a builder
   declares it: a map with an identifier-shaped key and scalar values
   (`_scalar_map`: `counts`, `state_counts`, `light_counts`, `states`,
   `by_status` lists), a list of identifier strings (`_id_list`:
   `critical_series`, `missing`, `unexpected`, `capabilities`), or a map of
   rows whose own fields are picked scalars (lanes, populations, priority).
3. MAP KEYS must match `IDENT` (letters, digits, `_ . : + -`, max 64) and must
   not match `UNSAFE_SHAPES`; otherwise the entry is dropped and counted in
   `withheld_keys` (never silently).
4. STRINGS that survive 1-3 still pass `UNSAFE_SHAPES` (a leaf matching a path,
   traceback or exception text, money, host:port, an API-key-shaped token or an
   env-var name becomes `[withheld]`). Exemption: a bare git hash (7-64 hex) is
   data, not a secret.
5. NOT served publicly under any key: free text from a producer (`reason`,
   `error`, `detail`, `proof`, `where`, `message`), log lines, spend or balance,
   paths, env names, exception text.

ACCESS: the full payload is reachable through `full_view_allowed` (the desktop
control plane's own gate) or the `X-Health-Token` header (`token_state`, constant
time). `/api/health/detail` answers 404 to everyone else, so an outsider cannot
tell whether a token is configured.
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Any, Optional

from fastapi import HTTPException, Request

from backend.config import HEALTH_TOKEN_ENV, HEALTH_TOKEN_HEADER

WITHHELD = "[withheld]"

#: Shapes that must never reach a public payload (values AND map keys).
UNSAFE_SHAPES = re.compile(
    r"(?:[A-Za-z]:[\\/]"                                          # C:\ or C:/
    r"|\\\\"                                                       # UNC / escaped backslash path
    r"|(?:^|[\s\"'(=:,;])~?/[A-Za-z_.][\w.-]*(?:/[\w.@%+-]+)+"      # any absolute unix path, 2+ parts
    r"|(?:^|[\s\"'(=:,;])/(?:app|data|home|usr|var|tmp|mnt|opt|etc|srv|root|Users|proc|workspace|"
    r"workdir|code|repo|build|railway)\b"                          # one-part unix roots
    r"|(?:^|\s)~/"                                                 # ~/ home paths
    r"|\b[\w.-]+/[\w./-]*\.(?:py|json|jsonl|parquet|db|csv|log|md|yaml|yml|txt|toml|env)\b"  # file path
    r"|Traceback|\bFile \""                                        # exception text
    r"|\b[A-Z][A-Za-z0-9]*(?:Error|Exception)\b"                    # SomethingError: ...
    r"|\$\s?\d|[\u20ac\u00a3]\s?\d"                                # amounts of money
    r"|\b\d[\d,.]*\s*(?:dollars?|USD|usd|bucks|EUR|GBP)\b|\b(?:USD|usd)\b"
    r"|\b[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\b"  # env var names
    r"|\bAEGIS_[A-Z0-9_]+\b|\bAPCA_[A-Z0-9_]+\b"
    r"|\bsk-[A-Za-z0-9_-]{8,}|\bghp_[A-Za-z0-9]{8,}|\bxox[abp]-[A-Za-z0-9-]{8,}|\bBearer\s+\S{8,}"  # key-like
    r"|[A-Za-z0-9+/_=-]{40,}"                                       # long base64 / hex run
    r"|\b[\w-]+(?:\.[\w-]+)+:\d{2,5}\b|\blocalhost:\d+|\b\d{1,3}(?:\.\d{1,3}){3}\b"  # host:port, IPs
    r")")

_GIT_HASH = re.compile(r"[0-9a-f]{7,64}")
#: A map key in a public payload.
IDENT = re.compile(r"[A-Za-z0-9_.:+-]{1,64}")

_SCALARS = (str, int, float, bool, type(None))


class _Tally:
    """Counts the map entries dropped on the way out (`withheld_keys`)."""
    def __init__(self) -> None:
        self.n = 0


def _unsafe(s: str) -> bool:
    return not _GIT_HASH.fullmatch(s) and bool(UNSAFE_SHAPES.search(s))


def _scrub(value: Any, t: _Tally) -> Any:
    """Recursively replace unsafe string leaves and DROP dict entries whose key
    is not an identifier or is itself unsafe (counted in `t`)."""
    if isinstance(value, str):
        return WITHHELD if _unsafe(value) else value
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str) or not IDENT.fullmatch(k) or _unsafe(k):
                t.n += 1
                continue
            out[k] = _scrub(v, t)
        return out
    if isinstance(value, (list, tuple)):
        return [_scrub(v, t) for v in value]
    return value


def withhold_unsafe(value: Any) -> Any:
    """`_scrub` for callers that do not need the drop count."""
    return _scrub(value, _Tally())


def _finish(payload: dict, t: _Tally) -> dict:
    out = _scrub(payload, t)
    out["withheld_keys"] = t.n
    return out


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
    """Gate for `/api/health/detail`: 404 for everyone not allowed, whether or not
    a token is configured (the answer must not say whether one is)."""
    if not full_view_allowed(request):
        raise HTTPException(status_code=404, detail="Not Found")


# ------------------------------------------------------------- projections ---

def _pick(src: Any, keys: tuple[str, ...]) -> dict:
    """Scalars only: a dict or list under a picked key is dropped."""
    src = src if isinstance(src, dict) else {}
    return {k: src[k] for k in keys if k in src and isinstance(src[k], _SCALARS)}


def _scalar_map(src: Any, t: _Tally) -> dict:
    """A declared map: identifier keys, scalar values; anything else dropped+counted."""
    out: dict = {}
    if not isinstance(src, dict):
        return out
    for k, v in src.items():
        if not isinstance(k, str) or not IDENT.fullmatch(k) or _unsafe(k) or not isinstance(v, _SCALARS):
            t.n += 1
            continue
        out[k] = v
    return out


def _id_list(src: Any, t: _Tally) -> list[str]:
    """A declared list of identifier strings; other items dropped+counted."""
    out: list[str] = []
    for v in src if isinstance(src, (list, tuple)) else []:
        if isinstance(v, str) and IDENT.fullmatch(v) and not _unsafe(v):
            out.append(v)
        else:
            t.n += 1
    return out


def _row_map(src: Any, keys: tuple[str, ...], t: _Tally) -> dict:
    """A declared map of rows: identifier keys, each row picked to scalars."""
    out: dict = {}
    if not isinstance(src, dict):
        return out
    for k, v in src.items():
        if not isinstance(k, str) or not IDENT.fullmatch(k) or _unsafe(k) or not isinstance(v, dict):
            t.n += 1
            continue
        out[k] = _pick(v, keys)
    return out


def _status_only(block: Any) -> dict:
    return _pick(block, ("status",))


def _scheduler(sched: Any, t: _Tally) -> dict:
    """running, job count, per-lane NAV freshness, and the ids of missing or
    undeclared jobs (declared in the public repo). `last_mtm` and `jobs.status`
    are declared scalars (a dict there is dropped)."""
    sched = sched if isinstance(sched, dict) else {}
    nav = sched.get("nav") if isinstance(sched.get("nav"), dict) else {}
    jobs = sched.get("jobs") if isinstance(sched.get("jobs"), dict) else {}
    return {
        "running": sched.get("running") is True,
        "n_jobs": sched.get("n_jobs") if isinstance(sched.get("n_jobs"), int) else 0,
        "persistent": sched.get("persistent") is True,
        "last_mtm": sched.get("last_mtm") if isinstance(sched.get("last_mtm"), (str, type(None))) else None,
        "nav": {
            "all_fresh": nav.get("all_fresh") is True,
            "expected_nav_date": nav.get("expected_nav_date")
            if isinstance(nav.get("expected_nav_date"), (str, type(None))) else None,
            "lanes": _row_map(nav.get("lanes"), ("last_nav_date", "fresh"), t),
        },
        "jobs": {
            "status": jobs.get("status") if isinstance(jobs.get("status"), (str, type(None))) else None,
            "missing": _id_list(jobs.get("missing"), t),
            "unexpected": _id_list(jobs.get("unexpected"), t),
        },
    }


_ALARM_KEYS = ("light", "status", "healthy", "attention_required",
               "evidence_mode", "valid_until_utc", "evidence_calendar")
_ROW_KEYS = ("name", "verdict", "state", "evidence_utc", "age_s", "age_s_now", "age_s_at_probe",
             "cadence_s", "evidence_mode", "valid_until_utc", "public_view",
             "progressing", "same_output")


def _alarm(a: Any, t: _Tally, *, extra: tuple[str, ...] = ()) -> dict:
    out = _pick(a, _ALARM_KEYS + extra)
    if isinstance(a, dict) and "light_counts" in a:
        out["light_counts"] = _scalar_map(a["light_counts"], t)
    return out


def _probe_row(r: dict, t: _Tally) -> dict:
    """One subsystem row: verdict words, state, ages, light. The producer's free
    text (`probe`, `where`, `detail`, `proof`, `evidence`, `missing_because`) is
    null: the keys stay so the frontend's types hold."""
    row = _pick(r, _ROW_KEYS)
    if isinstance(r.get("probe"), str) and IDENT.fullmatch(r["probe"]) and not _unsafe(r["probe"]):
        row["probe"] = r["probe"]            # an id, e.g. `process_census`
    else:
        row["probe"] = None
    row.update({"where": None, "detail": None, "proof": None, "evidence": None,
                "missing_because": None})
    if isinstance(r.get("alarm"), dict):
        row["alarm"] = _alarm(r["alarm"], t)
    return row


def public_subsystems(block: Any, t: Optional[_Tally] = None) -> dict:
    t = t or _Tally()
    block = block if isinstance(block, dict) else {}
    out = _pick(block, ("generated_utc", "source", "exit_code"))
    out["counts"] = _scalar_map(block.get("counts"), t)
    out["state_counts"] = _scalar_map(block.get("state_counts"), t)
    out["rows"] = [_probe_row(r, t) for r in block.get("rows") or [] if isinstance(r, dict)]
    if isinstance(block.get("alarm"), dict):
        out["alarm"] = _alarm(block["alarm"], t, extra=("schema",))
    return out


def public_health_full(full: dict, codes: list[str]) -> dict:
    """The public `/api/health/full`. `codes` are the coarse degraded codes
    computed beside the full reasons (`nav_not_fresh`, `fred_health`, ...)."""
    t = _Tally()
    tr = full.get("track_record") if isinstance(full.get("track_record"), dict) else {}
    fp = full.get("forecast_populations") if isinstance(full.get("forecast_populations"), dict) else {}
    fh = full.get("fred_health") if isinstance(full.get("fred_health"), dict) else {}
    by_status = fh.get("by_status") if isinstance(fh.get("by_status"), dict) else {}
    out = {
        "view": "public",
        "status": full.get("status") if isinstance(full.get("status"), str) else None,
        "degraded_reasons": _id_list(list(codes), t),
        "deploy": _pick(full.get("deploy"), ("commit", "version", "started_at",
                                             "uptime_seconds", "cache_status")),
        "scheduler": _scheduler(full.get("scheduler"), t),
        "track_record": {
            "inception_date": tr.get("inception_date") if isinstance(tr.get("inception_date"), _SCALARS) else None,
            "age_days": tr.get("age_days") if isinstance(tr.get("age_days"), _SCALARS) else None,
            "lanes": _row_map(tr.get("lanes"), ("last_date", "nav", "since_inception_pct"), t),
        },
        "prediction_ledger": _pick(full.get("prediction_ledger"), ("status", "population_id")),
        "forecast_populations": {
            "status": fp.get("status") if isinstance(fp.get("status"), _SCALARS) else None,
            "populations": _row_map(fp.get("populations"), ("status", "days_quiet", "last_written"), t),
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
            **_pick(fh, ("status", "fetch_passes")),
            "critical_series": _id_list(fh.get("critical_series"), t),
            "by_status": {k: _id_list(v, t) for k, v in by_status.items()
                          if isinstance(k, str) and IDENT.fullmatch(k) and not _unsafe(k)},
        },
        "subsystems": public_subsystems(full.get("subsystems"), t),
    }
    return _finish(out, t)


def public_providers(payload: dict) -> dict:
    """Provider name, up/down and capability ids, plus the priority order. The
    `reason` string (what is missing, which key) is withheld."""
    t = _Tally()
    prio = payload.get("priority") if isinstance(payload.get("priority"), dict) else {}
    out = {
        "view": "public",
        "providers": [{"name": p.get("name") if isinstance(p.get("name"), str) else None,
                       "available": p.get("available") is True,
                       "capabilities": _id_list(p.get("capabilities"), t)}
                      for p in payload.get("providers") or [] if isinstance(p, dict)],
        "priority": {k: _id_list(v, t) for k, v in prio.items()
                     if isinstance(k, str) and IDENT.fullmatch(k) and not _unsafe(k)},
    }
    return _finish(out, t)


def public_scheduler_health(h: dict) -> dict:
    t = _Tally()
    out = _scheduler(h, t)
    out["view"] = "public"
    return _finish(out, t)


#: The prewarm lifecycle values `backend/main.py` sets; anything else is "other".
CACHE_STATUSES = ("pending", "ready", "failed", "skipped")


def public_health_minimal(*, cache_ready: Any, cache_status: Any, version: Any,
                          git_head: Any) -> dict:
    """`/api/health` for a caller outside the control plane: 200, a few words."""
    t = _Tally()
    gh = git_head if isinstance(git_head, str) and _GIT_HASH.fullmatch(git_head) else None
    out = {"status": "ok",
           "version": version if isinstance(version, str) else None,
           "cache_ready": cache_ready is True,
           "cache_status": cache_status if cache_status in CACHE_STATUSES else "other",
           "git_head": gh}
    scrubbed = _scrub(out, t)
    return scrubbed


def public_system_health(payload: dict) -> dict:
    """`/api/legibility/v1/system-health` at SERVE time: status words, ids, dates
    and counts only. Row `detail`/`proof`/`where`/`evidence`/`missing_because`,
    the receipt file name and line, `read_me_first`, `same_output_rule` and the
    task owners' receipt column are null; `health_line` is rebuilt from the
    counts. The publisher applies the same projection before it writes the tracked
    copy under `public_receipts/` (`publish_receipts._public_system_health`), so
    this call at serve time is defence in depth (and covers a live receipt)."""
    t = _Tally()
    p = payload if isinstance(payload, dict) else {}
    counts = _scalar_map(p.get("counts"), t)
    n_total = sum(v for v in counts.values() if isinstance(v, int) and not isinstance(v, bool))
    n_alive = sum(v for k, v in counts.items() if k.startswith("ALIVE") and isinstance(v, int))
    line = (f"health rc {p.get('exit_code')}: {', '.join(f'{k} {v}' for k, v in counts.items() if v)}; "
            f"{n_total - n_alive} of {n_total} subsystems not ALIVE") if counts else None

    def row(r: Any) -> dict:
        return _probe_row(r, t) if isinstance(r, dict) else {}

    groups = [{"verdict": g.get("verdict") if isinstance(g.get("verdict"), str) else None,
               "n": g.get("n") if isinstance(g.get("n"), int) else 0,
               "states": _scalar_map(g.get("states"), t),
               "rows": [row(r) for r in g.get("rows") or []]}
              for g in p.get("groups") or [] if isinstance(g, dict)]
    owners = []
    for o in p.get("task_owners") or []:
        if not isinstance(o, dict):
            continue
        d = _pick(o, ("task", "cadence_h", "session_only", "retired", "registered_only",
                      "state", "verdict"))
        d["hash_rule_off"] = bool(o.get("hash_rule_off"))
        d.update({"receipt": None, "detail": None, "missing_because": None})
        if isinstance(o.get("alarm"), dict):
            d["alarm"] = _alarm(o["alarm"], t)
        owners.append(d)
    receipts = [{**_pick(r, ("kind", "stamp_utc", "age_hours", "stale_after_hours", "status")),
                 "file": None, "line": None}
                for r in p.get("receipts") or [] if isinstance(r, dict)]
    src = p.get("source")
    out = {
        "view": "public",
        **_pick(p, ("schema", "page", "served_utc", "status", "published_utc", "generated_utc",
                    "exit_code", "observation_current", "observation_clock_source")),
        "served_from": ("published_copy" if str(p.get("served_from") or "").startswith("public_receipts/")
                        else ("live" if p.get("served_from") is None else "other")),
        "receipts": receipts, "missing_because": {},
        "health_line": line, "read_me_first": None, "same_output_rule": None,
        "source": src if isinstance(src, str) and IDENT.fullmatch(src) else None,
        "counts": counts, "state_counts": _scalar_map(p.get("state_counts"), t),
        "alarm": _alarm(p.get("alarm"), t, extra=("schema",)),
        "groups": groups,
        "process_census": [row(r) for r in p.get("process_census") or []],
        "same_output_rows": [row(r) for r in p.get("same_output_rows") or []],
        "task_owners": owners,
    }
    return _finish(out, t)
