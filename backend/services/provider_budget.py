"""Local DeepSeek reservation envelope with a UTC calendar-month cap (OD-2).

No reset, no replacement, no paid fallback. The default host envelope is ONE
file, `session_budget/deepseek_local.json` -- the same file, schema and lock the
runtime's 2026-10-15 guard reads and writes -- so processes on old and new code
in the same month reserve against one ledger and cannot each spend a cap
(review #88 R1: a separate month file gave each version its own $15). The cap
applies to the RUNNING MONTH: this month's held amount is the calls whose
`started_utc` falls in it (a call without a parseable one counts in every
month) plus the opening debit if the file was created in it. The month cap is
`month_caps[<YYYY-MM>]` (written by an attended `raise`), else
`config.DEEPSEEK_MONTHLY_CAP_USD` (owner decision 2026-11-10: $15/month). The
file is created from config on the first paid call if absent and never
recreated. A block (`blocked`) is file-wide and survives the month boundary
until attended reconciliation. The 10-15 code still checks the file's LIFETIME
held against `cap_units`, which is never below this month's held, so it is
only ever stricter. An explicit `AEGIS_DEEPSEEK_BUDGET_PATH` (or
`budget_path=`) names a FIXED envelope with the old contract: attended
`initialize` only, lifetime cap.

SCOPE (review #88 R2): this envelope binds the DeepSeek calls that go through
`attempt()` -- `llm_analyzer._call_llm` / `call_named` and their callers. The
DeepSeek call sites listed in `UNCAPPED_DEEPSEEK_PATHS` call the provider
outside it and are NOT capped; `status_line()` says so, and
`test_deepseek_call_sites_are_guarded` fails when a new one appears.

Why creation from config rather than "fail loudly" (2026-11-10): the old single
envelope had no rollover and nothing created it, so every DeepSeek call on the PC
was refused from 2026-10-15 to 2026-11-10 while most tasks exited 0. A monthly
cap that needs a hand-made file every month re-arms that same block on the 1st.
The cap number is the owner's declaration (config); the file is its ledger. Every
refusal carries one line: spend so far, cap, and what to do
(`status_line()`, `python -m backend.services.provider_budget status`).

This is shared only by updated processes on one filesystem, not across hosts.
All USD numbers are conservative list-price estimates, never billed balances.
Pricing checked 2026-11-03: https://api-docs.deepseek.com/quick_start/pricing/
V4.1 Flash peak USD/1M: input .30, cached input .006, output 1.20.
Off-peak is cheaper; reserve and settle at peak until an actual billing receipt.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from urllib.parse import urlsplit

from backend.services import disk_guard as DG

PRICE = {"in": .30, "cached_in": .006, "out": 1.20}
MODELS = frozenset({"deepseek-flash"})  # verified returned identity, never a request label
# Compatibility exceptions preserve existing requests, not provider identity.
# 205 current native calls requested deepseek-chat and served deepseek-flash;
# IIF's frozen request string remains untouched. Neither legacy returned name
# has current primary-source pricing authority and neither can release money.
REQUEST_MODELS = MODELS | {"deepseek-chat", "deepseek-v4-flash"}
SCHEMA = "local_deepseek_envelope/2"
SCALE = 1_000_000_000
#: Hard per-envelope ceiling (unchanged from the session design): a cap above it,
#: from config or `raise`, is refused rather than clipped.
HARD_CAP_USD = 20
#: The ONE host envelope file, shared with the runtime's 2026-10-15 guard.
ENVELOPE_NAME = "deepseek_local.json"
CLI = "python -m backend.services.provider_budget"
#: DeepSeek call sites that do NOT pass through `attempt()` (review #88 R2,
#: 2026-11-11). Their spend is outside the monthly cap. Pinned by
#: `backend/tests/test_deepseek_call_sites_are_guarded.py`; shrink it by
#: routing a caller through `attempt()`, never grow it silently.
UNCAPPED_DEEPSEEK_PATHS = (
    "backend/services/architecture_arena.py",
    "backend/services/copilot.py",
    "backend/services/leakage_probe.py",
    "backend/services/llm_research.py",
    "backend/services/llm_swarm.py",
    "backend/services/model_provider.py",
    "backend/services/optimus_specialists.py",
    "backend/services/why_moved.py",
    "scripts/book_factory.py",
    "scripts/companyworld_extract.py",
    "scripts/connection_check.py",
    "scripts/era_replay_v2.py",
    "scripts/n6b_fantasy_exams_round2.py",
    "scripts/recall_canary_positive_control.py",
    "scripts/stack_health.py",
)


class BudgetRefused(RuntimeError):
    """str(exc) is the one human line: reason, spend so far, cap, what to do."""


logger = logging.getLogger(__name__)

#: Retry schedule for an envelope write refused by Windows (`PermissionError`,
#: WinError 5/32: another handle -- a non-locking reader, an AV scan of the fresh
#: temp -- holds the target without FILE_SHARE_DELETE). Retried UNDER the lock;
#: the temp is complete and fsynced, so a retry cannot publish a partial file.
#: 2026-11-10 16:33:40Z: one such refusal in `settle()` discarded a PAID
#: world_digest_synth reply and the night's biggest theme got 0 implications.
WRITE_BACKOFF_S = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)
_sleep = time.sleep
#: The billing status of a paid call whose settlement could not reach the
#: envelope: the reply is KEPT, the envelope still holds the full reservation
#: (never less than the cost), and the settlement waits in the sidecar until the
#: next `reserve()` reconciles it.
DEFERRED_STATUS = "SETTLEMENT_DEFERRED_SIDECAR"


def sidecar_path(p):
    """`deepseek_local.json` -> `deepseek_local.unsettled.jsonl` (same directory)."""
    p = Path(p)
    return p.with_name(p.stem + ".unsettled.jsonl")


def _write(p, s):
    """`atomic_write_json`, retrying a Windows sharing refusal with backoff.
    Anything that is not a PermissionError (disk full, a bad path) raises at once."""
    for i in range(len(WRITE_BACKOFF_S) + 1):
        try:
            DG.atomic_write_json(p, s)
            return
        except PermissionError:
            if i >= len(WRITE_BACKOFF_S):
                raise
            _sleep(WRITE_BACKOFF_S[i])


def _append_sidecar(p, row):
    """One fsynced line. The caller holds the envelope lock, which every sidecar
    writer and reader also holds, so lines never interleave."""
    sp = sidecar_path(p)
    with open(sp, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _reconcile_sidecar(p, s):
    """Apply deferred settlements to `s` in memory. Returns how many applied.

    A line applies only to a call still RESERVED_UNKNOWN in this envelope; a
    line for a call already settled is a no-op (idempotent after a crash between
    the envelope write and the sidecar removal). A line naming no call here is
    kept on the envelope as an orphan, never silently dropped. A deferred block
    is applied whatever the call's state.
    """
    sp = sidecar_path(p)
    if not sp.exists():
        return 0
    applied = 0
    for ln in sp.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(ln)
        except ValueError:
            s.setdefault("sidecar_orphans", []).append({"unparsed": ln[:200]})
            applied += 1
            continue
        if row.get("blocked") and not s.get("blocked"):
            s["blocked"] = row["blocked"]
        r = s["calls"].get(row.get("reservation_id"))
        if r is None:
            s.setdefault("sidecar_orphans", []).append(row)
            applied += 1
            continue
        if r["status"] != "RESERVED_UNKNOWN":
            continue
        if row.get("status") == "SETTLED_PEAK_ESTIMATE" and type(row.get("held_units")) is int:
            # a settled cost above the reservation is already a block (above)
            r.update(status="SETTLED_PEAK_ESTIMATE", held_units=row["held_units"],
                     cost_usd=row["held_units"] / SCALE)
        else:
            r["status"] = "BILLING_UNKNOWN"            # keeps the full reservation held
        r.update(served_model=row.get("served_model"), settled_utc=row.get("settled_utc"),
                 reconciled_from_sidecar=True)
        applied += 1
    return applied


def _clear_sidecar(p):
    try:
        sidecar_path(p).unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:                              # idempotent: re-applied lines no-op
        logger.warning("provider_budget: sidecar not removed (%s); its lines are no-ops now", exc)


def host_envelope_required():
    """Windows always participates; other hosts opt in explicitly.

    This is not a cloud provider cap. A missing PC envelope must not disable
    Railway/Linux. No environment value can turn enforcement off on Windows.
    A path override alone does not opt a cloud host in.
    """
    return sys.platform == "win32" or os.getenv("AEGIS_DEEPSEEK_HOST_ENVELOPE") == "1"


def _units(value):
    d = Decimal(str(value))
    if not d.is_finite() or d < 0:
        raise BudgetRefused("invalid dollar amount")
    return int((d * SCALE).to_integral_value(rounding=ROUND_CEILING))


def month_id(now=None):
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def _default_dir():
    # One host-level directory shared by worktrees and background processes.
    return Path.home() / "aegis-finance/backend/data/optimus/session_budget"


def monthly(budget_path=None):
    """True for the default host envelope; an explicit path is a fixed envelope."""
    return budget_path is None and not os.getenv("AEGIS_DEEPSEEK_BUDGET_PATH")


def path():
    override = os.getenv("AEGIS_DEEPSEEK_BUDGET_PATH")
    if override:
        return Path(override)
    return _default_dir() / ENVELOPE_NAME


def monthly_cap_usd():
    """The owner's declared monthly cap (config, env-overridable)."""
    from backend import config as C
    cap = float(getattr(C, "DEEPSEEK_MONTHLY_CAP_USD", 15.0))
    if not 0 < cap <= HARD_CAP_USD:
        raise BudgetRefused(f"DEEPSEEK BUDGET REFUSED (CONFIG): monthly cap ${cap} is outside "
                            f"(0, ${HARD_CAP_USD}] -- fix AEGIS_DEEPSEEK_MONTHLY_CAP_USD")
    return cap


def _lock(p):
    return DG.file_lock(p.with_name(p.name + ".lock"), timeout_s=5)


def _load(p):
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        if (s["schema"] != SCHEMA or not s["session_id"] or type(s["cap_units"]) is not int
                or not 0 < s["cap_units"] <= HARD_CAP_USD*SCALE):
            raise ValueError("invalid envelope contract")
        if not isinstance(s["calls"], dict) or not isinstance(s["daily"], dict):
            raise ValueError("invalid accounting")
        if type(s["opening_units"]) is not int or s["opening_units"] < 0 or not s["opening_evidence"]:
            raise ValueError("explicit opening debit/evidence required")
        for r in s["calls"].values():
            if type(r["held_units"]) is not int or r["held_units"] < 0:
                raise ValueError("invalid held amount")
            if r["status"] not in {"RESERVED_UNKNOWN", "BILLING_UNKNOWN", "SETTLED_PEAK_ESTIMATE"}:
                raise ValueError("unknown settlement status")
        if any(type(v) is not int or v < 0 for v in s["daily"].values()):
            raise ValueError("invalid daily count")
        return s
    except Exception as exc:
        raise BudgetRefused("shared envelope absent/unreadable; explicit initialization required") from exc


def initialize(session_id, cap_usd, *, opening_charge_usd, opening_evidence, budget_path=None):
    """Attended initialization only, refuses replacement (even an exhausted file)."""
    p = Path(budget_path) if budget_path else path()
    cap = _units(cap_usd)
    opening = _units(opening_charge_usd)
    if not session_id or not 0 < cap <= HARD_CAP_USD*SCALE:
        raise BudgetRefused("explicit session and incremental cap <= $20 required")
    if not opening_evidence or opening > cap:
        raise BudgetRefused("opening debit and its evidence must fit the unchanged session cap")
    with _lock(p):
        if p.exists():
            raise BudgetRefused("existing envelope cannot be reset or replaced")
        _write(p, {"schema": SCHEMA, "session_id": str(session_id),
            "created_utc": datetime.now(timezone.utc).isoformat(), "cap_units": cap,
            "opening_units": opening, "opening_evidence": str(opening_evidence),
            "price_as_of": "2026-11-03", "price_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "price_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED", "calls": {}, "daily": {}, "blocked": None})


def _held(s):
    return s["opening_units"] + sum(r["held_units"] for r in s["calls"].values())


def _month_of(stamp):
    m = str(stamp or "")[:7]
    return m if len(m) == 7 and m[4] == "-" and m[:4].isdigit() and m[5:].isdigit() else None


def _month_cap_units(s, month):
    """This month's cap: an attended raise for it, else config. In the file's
    creation month the attended `cap_units` also binds (the smaller wins)."""
    caps = s.get("month_caps") or {}
    if type(caps.get(month)) is int and 0 < caps[month] <= HARD_CAP_USD*SCALE:
        return caps[month]
    cfg = _units(monthly_cap_usd())
    if _month_of(s.get("created_utc")) in (month, None):
        return min(cfg, s["cap_units"])
    return cfg


def _month_view(s, month):
    """The envelope as the running month sees it: its calls, its opening, its cap.

    Same keys as the file (callers sum `opening_units + calls[*].held_units`
    against `cap_units`), restricted to `month`; a call or a creation stamp that
    does not parse counts in every month.
    """
    calls = {k: r for k, r in s["calls"].items()
             if _month_of(r.get("started_utc")) in (month, None)}
    opening = s["opening_units"] if _month_of(s.get("created_utc")) in (month, None) else 0
    return {**s, "calls": calls, "opening_units": opening, "cap_units": _month_cap_units(s, month),
            "month": month, "envelope_cap_units": s["cap_units"],
            "lifetime_held_units": _held(s), "envelope": ENVELOPE_NAME}


def _fresh(month, *, virtual=False):
    cap = _units(monthly_cap_usd())
    return {"schema": SCHEMA, "session_id": f"od2-monthly-from-{month}",
            "created_utc": datetime.now(timezone.utc).isoformat(), "cap_units": cap,
            "cap_source": "config.DEEPSEEK_MONTHLY_CAP_USD (OD-2)",
            "opening_units": 0, "opening_evidence": f"created from config on the first {month} call",
            "price_as_of": "2026-11-03", "price_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "price_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED", "calls": {}, "daily": {},
            "blocked": None, "month_caps": {}, "cap_history": [],
            **({"virtual": True} if virtual else {})}


def _ensure_envelope(p, budget_path=None):
    """Create the host envelope from config if absent. Caller holds the lock.

    Never touches an existing file or a fixed (explicit-path) envelope.
    """
    if not monthly(budget_path) or p.exists() or p != path():
        return False
    _write(p, _fresh(month_id()))
    return True


def _view(s, budget_path=None):
    return _month_view(s, month_id()) if monthly(budget_path) else s


def _peek(p, budget_path=None):
    """The month view, or for an absent host envelope the one the first call WOULD create."""
    if monthly(budget_path) and p == path() and not p.exists():
        return _month_view(_fresh(month_id(), virtual=True), month_id())
    return _view(_load(p), budget_path)


#: The smallest reservation any call can make (two empty messages, 1 output
#: token). Below this much room every call refuses, so status says EXHAUSTED
#: by the same rule `reserve` applies (review #88 O2).
MIN_RESERVATION_UNITS = _units((1024*PRICE["in"] + 1*PRICE["out"])/1e6)


_HINTS = {
    "EXHAUSTED": f"raise this month: {CLI} raise --cap <usd> --evidence '<why>' (ceiling ${HARD_CAP_USD}); "
                 "future months: AEGIS_DEEPSEEK_MONTHLY_CAP_USD",
    "BLOCKED": f"attended reconciliation required; see `{CLI} status`",
    "DAILY_CALL_CAP": "production daily call cap reached; resets at UTC midnight",
    "MISSING": f"fixed envelope absent; an attended initialize() creates it (`{CLI} init` for the month file)",
    "UNREADABLE": "envelope unreadable or malformed; inspect it, never delete or replace one holding spend",
}


def status_line(*, budget_path=None):
    """One human line: verdict, period, held vs cap, what to do. Never raises.

    Omits the block reason and evidence text (callers print this to logs that
    may be published); `status` on the CLI prints the block reason.
    """
    p = Path(budget_path) if budget_path else path()
    try:
        s = _peek(p, budget_path)
        held, cap = _held(s) / SCALE, s["cap_units"] / SCALE
    except Exception as exc:                                     # noqa: BLE001
        if str(exc).startswith("DEEPSEEK BUDGET"):
            return str(exc)
        code = "MISSING" if isinstance(exc.__cause__, FileNotFoundError) else "UNREADABLE"
        return (f"DEEPSEEK BUDGET REFUSED ({code}): envelope {p.name} could not be read; "
                f"spend so far UNKNOWN -- {_HINTS[code]}")
    room = s["cap_units"] - _held(s)
    code = "BLOCKED" if s.get("blocked") else "EXHAUSTED" if room < MIN_RESERVATION_UNITS else None
    head = f"DEEPSEEK BUDGET REFUSED ({code})" if code else "DEEPSEEK BUDGET OK"
    created = "; not yet created, the first call creates it" if s.get("virtual") else ""
    tail = f" -- {_HINTS[code]}" if code else ""
    scope = (f"; covers llm_analyzer only, {len(UNCAPPED_DEEPSEEK_PATHS)} other DeepSeek "
             f"call-site files are UNCAPPED (`{CLI} status` lists them)"
             if UNCAPPED_DEEPSEEK_PATHS else "")
    return (f"{head}: {s.get('month') or s.get('session_id')} held ${held:.4f} of ${cap:.2f} cap "
            f"(peak list estimate, {len(s['calls'])} calls; envelope {p.name}{created}{scope}){tail}")


def _refuse(code, s, p):
    held, cap = _held(s) / SCALE, s["cap_units"] / SCALE
    return BudgetRefused(f"DEEPSEEK BUDGET REFUSED ({code}): {s.get('month') or s.get('session_id')} "
                         f"held ${held:.4f} of ${cap:.2f} cap (peak list estimate; envelope {p.name}) "
                         f"-- {_HINTS[code.split(':')[0]]}")


def raise_cap(cap_usd, *, evidence, budget_path=None):
    """Attended: raise the running envelope's cap. Never lowers, never resets spend."""
    p = Path(budget_path) if budget_path else path()
    new = _units(cap_usd)
    if not evidence or not 0 < new <= HARD_CAP_USD*SCALE:
        raise BudgetRefused(f"raise needs --evidence and a cap in (0, ${HARD_CAP_USD}]")
    with _lock(p):
        _ensure_envelope(p, budget_path)
        s = _load(p)
        month = month_id()
        current = _view(s, budget_path)["cap_units"]
        if new <= current:
            raise BudgetRefused(f"raise refused: ${cap_usd} is not above the current "
                                f"${current/SCALE:.2f} cap (a cap is never lowered)")
        s.setdefault("cap_history", []).append({"from_units": current, "to_units": new,
            "month": month if monthly(budget_path) else None,
            "evidence": str(evidence), "utc": datetime.now(timezone.utc).isoformat()})
        if monthly(budget_path):
            s.setdefault("month_caps", {})[month] = new
            # In the file's creation month lifetime == month, so the 10-15
            # guard (lifetime vs cap_units) gets exactly the same room.
            if _month_of(s.get("created_utc")) == month and new > s["cap_units"]:
                s["cap_units"] = new
        else:
            s["cap_units"] = new
        _write(p, s)
    return status_line(budget_path=budget_path)


def quote(system, user, max_tokens, model="deepseek-chat"):
    if model not in REQUEST_MODELS or type(max_tokens) is not int or max_tokens <= 0:
        raise BudgetRefused("unpriced request model or invalid output bound")
    # Byte-level tokenizer upper bound plus protocol/role overhead. We transmit
    # exactly two plain-text messages, no tools, images, attachments or streams.
    ti = len((system + user).encode("utf-8")) + 1024
    return {"input_bound": ti, "output_bound": max_tokens,
            "reserved_units": _units((ti*PRICE["in"] + max_tokens*PRICE["out"])/1e6)}


def reserve(system, user, max_tokens, *, model, base_url, purpose,
            production_cap=None, budget_path=None):
    u = urlsplit(base_url)
    if (u.scheme != "https" or u.hostname != "api.deepseek.com" or u.port not in (None, 443)
            or u.username or u.password or u.query or u.fragment):
        raise BudgetRefused("price authority requires official HTTPS DeepSeek endpoint")
    q = quote(system, user, max_tokens, model)
    p = Path(budget_path) if budget_path else path()
    with _lock(p):
        try:
            _ensure_envelope(p, budget_path)
            s = _load(p)
        except BudgetRefused as exc:
            if str(exc).startswith("DEEPSEEK BUDGET"):
                raise
            raise BudgetRefused(status_line(budget_path=budget_path)) from exc
        if _reconcile_sidecar(p, s):
            _write(p, s)
            _clear_sidecar(p)
        v = _view(s, budget_path)
        if s.get("blocked"):
            raise _refuse("BLOCKED", v, p)
        if _held(v) + q["reserved_units"] > v["cap_units"]:
            raise _refuse("EXHAUSTED", v, p)
        day = datetime.now(timezone.utc).date().isoformat()
        if production_cap is not None:
            if s["daily"].get(day, 0) >= production_cap:
                raise _refuse(f"DAILY_CALL_CAP: {production_cap} calls", v, p)
            s["daily"][day] = s["daily"].get(day, 0) + 1
        token = uuid.uuid4().hex
        s["calls"][token] = {**q, "held_units": q["reserved_units"], "status": "RESERVED_UNKNOWN",
            "pid": os.getpid(), "purpose": str(purpose), "request_model": model,
            "started_utc": datetime.now(timezone.utc).isoformat(), "cost_usd": None}
        _write(p, s)
    return {"id": token, "path": str(p), "reserved_usd": q["reserved_units"]/SCALE}


def settle(ticket, response=None):
    """No response, incomplete usage or crash never releases money.

    Unknown served models block more calls pending attended reconciliation.
    A retry is a NEW reservation, never a release/reuse of an unknown attempt.
    """
    p = Path(ticket["path"])
    with _lock(p):
        s = _load(p)
        r = s["calls"][ticket["id"]]
        if r["status"] != "RESERVED_UNKNOWN":
            raise BudgetRefused("reservation already settled")
        was_blocked = bool(s.get("blocked"))
        served = response.get("model") if isinstance(response, dict) else getattr(response, "model", None)
        usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
        cost = None
        if response is not None and served not in MODELS:
            s["blocked"] = "unknown returned model"
        def get(name):
            return usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        ti, to = get("prompt_tokens"), get("completion_tokens")
        cached = get("prompt_cache_hit_tokens")
        cached = 0 if cached is None else cached
        valid = (served in MODELS and all(type(x) is int and x >= 0 for x in (ti, to, cached))
                 and cached <= ti and ti+to > 0)
        if valid:
            cost = _units(((ti-cached)*PRICE["in"] + cached*PRICE["cached_in"] + to*PRICE["out"])/1e6)
            r.update(status="SETTLED_PEAK_ESTIMATE", held_units=cost, cost_usd=cost/SCALE)
            if ti > r["input_bound"] or to > r["output_bound"] or cost > r["reserved_units"]:
                s["blocked"] = "provider usage exceeded request reservation bound"
        else:
            r["status"] = "BILLING_UNKNOWN"
        r["served_model"] = served
        r["settled_utc"] = datetime.now(timezone.utc).isoformat()
        out = {"cost_usd": r["cost_usd"], "budget_charge_usd": r["held_units"]/SCALE,
               "price_as_of": "2026-11-03", "cost_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED",
               "billing_status": r["status"], "reservation_id": ticket["id"]}
        try:
            _write(p, s)
        except PermissionError as exc:
            # The reply is PAID: keep it. The envelope on disk still holds the
            # full reservation (>= this cost), so spend is not under-counted; the
            # settlement (and any block it raised) waits in the sidecar.
            row = {"reservation_id": ticket["id"], "status": r["status"],
                   "held_units": r["held_units"], "served_model": served,
                   "settled_utc": r["settled_utc"], "blocked": s.get("blocked") if not was_blocked
                   else None, "error": f"{type(exc).__name__}: {exc}"[:200]}
            try:
                _append_sidecar(p, row)
                out.update(billing_status=DEFERRED_STATUS, settlement_deferred=True)
            except OSError as exc2:
                # nothing on disk moved: the reservation stays held, the reply is kept
                logger.error("provider_budget: settlement of %s not recorded (%s; sidecar %s); "
                             "the full reservation stays held", ticket["id"], exc, exc2)
                out.update(billing_status="SETTLEMENT_FAILED_RESERVATION_RETAINED",
                           budget_charge_usd=ticket["reserved_usd"], settlement_deferred=False)
        return out


def snapshot(*, budget_path=None):
    """Locked read of the running month's view. An absent host envelope reads
    as the one the first call would create (`virtual: True`); nothing is written."""
    p = Path(budget_path) if budget_path else path()
    with _lock(p):
        s = _peek(p, budget_path)
        s["held_usd"] = _held(s)/SCALE
        return s


def preflight_snapshot():
    """Read-only advisory check; atomic envelope replacements need no sidecar.

    Never creates directories/locks or writes accounting. Reservations still
    re-read under the authoritative lock before any provider dispatch. Returns
    the running month's view; an absent host envelope reads as the fresh one
    the first reservation creates.
    """
    return _peek(path())


def attempt(body, *, base_url, purpose, send, production_cap=None):
    """Reserve/settle one existing transport invocation; no retries or routing.

    `send` is the caller's existing SDK/requests/urllib operation. It must raise
    on a transport/HTTP failure and return the raw provider object or JSON dict.
    """
    if (set(body) - {"model", "messages", "max_tokens", "temperature", "extra_body"}
            or body.get("extra_body", {}) not in ({}, {"thinking": {"type": "disabled"}})):
        exc = BudgetRefused("unsupported billable request options")
        exc.no_wire = True
        raise exc
    messages = body["messages"]
    if (len(messages) != 2 or messages[0].get("role") != "system"
            or messages[1].get("role") != "user"
            or any(type(m.get("content")) is not str for m in messages)):
        exc = BudgetRefused("only two plain text messages are reservation-qualified")
        exc.no_wire = True
        raise exc
    try:
        ticket = reserve(messages[0]["content"], messages[1]["content"], body["max_tokens"],
            model=body["model"], base_url=base_url, purpose=purpose, production_cap=production_cap)
    except Exception as exc:
        exc.no_wire = True
        raise
    def finish(response=None):
        try:
            return settle(ticket, response)
        except BaseException as exc:
            exc.shared_budget_accounting = {"cost_usd": None,
                "budget_charge_usd": ticket["reserved_usd"],
                "billing_status": "SETTLEMENT_FAILED_RESERVATION_RETAINED", "reservation_id": ticket["id"]}
            raise
    try:
        response = send()
    except BaseException as exc:
        accounting = finish()
        try:
            exc.shared_budget_accounting = accounting
        except Exception:
            pass
        raise
    return response, finish(response)


def main(argv=None):
    """`status` (exit 0 admits, 2 refuses) | `init` | `raise --cap USD --evidence TEXT`."""
    import argparse
    ap = argparse.ArgumentParser(prog="provider_budget")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="print the accounting line; exit 2 when refusing")
    sub.add_parser("init", help="create the host envelope from config now (if absent)")
    r = sub.add_parser("raise", help="raise this month's cap (attended)")
    r.add_argument("--cap", type=float, required=True)
    r.add_argument("--evidence", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "init":
            p = path()
            if not monthly():
                print(f"DEEPSEEK BUDGET REFUSED: {p.name} is a fixed envelope; "
                      "use initialize() with explicit evidence")
                return 2
            with _lock(p):
                made = _ensure_envelope(p)
            print(("created " if made else "exists  ") + str(p))
        elif a.cmd == "raise":
            print(raise_cap(a.cap, evidence=a.evidence))
            return 0
        line = status_line()
        print(line)
        try:
            blocked = _peek(path()).get("blocked")
        except Exception:                                        # noqa: BLE001
            blocked = None
        if blocked:
            print(f"blocked: {blocked}")
        if UNCAPPED_DEEPSEEK_PATHS:
            print("uncapped (call DeepSeek outside this envelope): "
                  + ", ".join(UNCAPPED_DEEPSEEK_PATHS))
        return 2 if line.startswith("DEEPSEEK BUDGET REFUSED") else 0
    except BudgetRefused as exc:
        text = str(exc)
        print(text if text.startswith("DEEPSEEK BUDGET") else f"DEEPSEEK BUDGET REFUSED: {text}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
