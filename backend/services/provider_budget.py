"""Local DeepSeek reservation envelope. No implicit create/reset or paid fallback.

This is shared only by updated processes on one filesystem, not across hosts.
All USD numbers are conservative list-price estimates, never billed balances.
Pricing checked 2026-11-03: https://api-docs.deepseek.com/quick_start/pricing/
V4.1 Flash peak USD/1M: input .30, cached input .006, output 1.20.
Off-peak is cheaper; reserve and settle at peak until an actual billing receipt.
"""
from __future__ import annotations

import json
import os
import sys
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


class BudgetRefused(RuntimeError):
    pass


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


def path():
    # One host-level path shared by worktrees and background processes.
    return Path(os.getenv("AEGIS_DEEPSEEK_BUDGET_PATH") or
                str(Path.home() / "aegis-finance/backend/data/optimus/session_budget/deepseek_local.json"))


def _lock(p):
    return DG.file_lock(p.with_name(p.name + ".lock"), timeout_s=5)


def _load(p):
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        if (s["schema"] != SCHEMA or not s["session_id"] or type(s["cap_units"]) is not int
                or not 0 < s["cap_units"] <= 20*SCALE):
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
    if not session_id or not 0 < cap <= 20*SCALE:
        raise BudgetRefused("explicit session and incremental cap <= $20 required")
    if not opening_evidence or opening > cap:
        raise BudgetRefused("opening debit and its evidence must fit the unchanged session cap")
    with _lock(p):
        if p.exists():
            raise BudgetRefused("existing envelope cannot be reset or replaced")
        DG.atomic_write_json(p, {"schema": SCHEMA, "session_id": str(session_id),
            "created_utc": datetime.now(timezone.utc).isoformat(), "cap_units": cap,
            "opening_units": opening, "opening_evidence": str(opening_evidence),
            "price_as_of": "2026-11-03", "price_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "price_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED", "calls": {}, "daily": {}, "blocked": None})


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
        s = _load(p)
        if s.get("blocked"):
            raise BudgetRefused("shared envelope blocked: " + s["blocked"])
        if s["opening_units"] + sum(r["held_units"] for r in s["calls"].values()) + q["reserved_units"] > s["cap_units"]:
            raise BudgetRefused("shared incremental dollar cap would be exceeded")
        day = datetime.now(timezone.utc).date().isoformat()
        if production_cap is not None:
            if s["daily"].get(day, 0) >= production_cap:
                raise BudgetRefused("shared production daily call cap")
            s["daily"][day] = s["daily"].get(day, 0) + 1
        token = uuid.uuid4().hex
        s["calls"][token] = {**q, "held_units": q["reserved_units"], "status": "RESERVED_UNKNOWN",
            "pid": os.getpid(), "purpose": str(purpose), "request_model": model,
            "started_utc": datetime.now(timezone.utc).isoformat(), "cost_usd": None}
        DG.atomic_write_json(p, s)
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
        DG.atomic_write_json(p, s)
        return {"cost_usd": r["cost_usd"], "budget_charge_usd": r["held_units"]/SCALE,
                "price_as_of": "2026-11-03", "cost_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED",
                "billing_status": r["status"], "reservation_id": ticket["id"]}


def snapshot(*, budget_path=None):
    p = Path(budget_path) if budget_path else path()
    with _lock(p):
        s = _load(p)
        s["held_usd"] = (s["opening_units"] + sum(r["held_units"] for r in s["calls"].values()))/SCALE
        return s


def preflight_snapshot():
    """Read-only advisory check; atomic envelope replacements need no sidecar.

    Never creates directories/locks or writes accounting. Reservations still
    re-read under the authoritative lock before any provider dispatch.
    """
    return _load(path())


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
