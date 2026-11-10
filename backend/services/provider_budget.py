"""Local DeepSeek reservation envelope: one per UTC calendar month (OD-2).

No reset, no replacement, no paid fallback. The default host envelope is a
MONTH file, `session_budget/deepseek_local_<YYYY-MM>.json`, created on the first
paid call of the month from `config.DEEPSEEK_MONTHLY_CAP_USD` (owner decision
2026-11-10: $15/month, raised on demand). Inside a month it is never recreated:
an exhausted or blocked month stays refused until an attended `raise` or
reconciliation. An explicit `AEGIS_DEEPSEEK_BUDGET_PATH` (or `budget_path=`)
names a FIXED envelope with the old contract: attended `initialize` only.

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
#: Hard per-envelope ceiling (unchanged from the session design): a cap above it,
#: from config or `raise`, is refused rather than clipped.
HARD_CAP_USD = 20
#: The pre-OD-2 single envelope. Its spend inside the running month is carried
#: into the month file as an opening debit, so the switch cannot double a month.
LEGACY_NAME = "deepseek_local.json"
CLI = "python -m backend.services.provider_budget"


class BudgetRefused(RuntimeError):
    """str(exc) is the one human line: reason, spend so far, cap, what to do."""


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


def path(month=None):
    override = os.getenv("AEGIS_DEEPSEEK_BUDGET_PATH")
    if override:
        return Path(override)
    return _default_dir() / f"deepseek_local_{month or month_id()}.json"


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
        DG.atomic_write_json(p, {"schema": SCHEMA, "session_id": str(session_id),
            "created_utc": datetime.now(timezone.utc).isoformat(), "cap_units": cap,
            "opening_units": opening, "opening_evidence": str(opening_evidence),
            "price_as_of": "2026-11-03", "price_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "price_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED", "calls": {}, "daily": {}, "blocked": None})


def _held(s):
    return s["opening_units"] + sum(r["held_units"] for r in s["calls"].values())


def _legacy_carry(month):
    """Spend the pre-OD-2 single envelope holds for `month`, and any block on it.

    An unreadable legacy file refuses: carrying an unknown amount as zero would
    let the switch double the month.
    """
    legacy = _default_dir() / LEGACY_NAME
    if not legacy.exists():
        return 0, None, "no legacy envelope"
    s = _load(legacy)
    units = sum(r["held_units"] for r in s["calls"].values()
                if str(r.get("started_utc", ""))[:7] == month)
    if str(s.get("created_utc", ""))[:7] == month:
        units += s["opening_units"]
    used = units > 0 or str(s.get("created_utc", ""))[:7] == month
    blocked = (f"carried from {LEGACY_NAME}: {s['blocked']}"
               if used and s.get("blocked") else None)
    return units, blocked, f"carried {units/SCALE:.6f} USD held in {month} by {LEGACY_NAME}"


def _fresh(month, *, virtual=False):
    cap = _units(monthly_cap_usd())
    opening, blocked, evidence = _legacy_carry(month)
    return {"schema": SCHEMA, "session_id": f"monthly-{month}", "month": month,
            "created_utc": datetime.now(timezone.utc).isoformat(), "cap_units": cap,
            "cap_source": "config.DEEPSEEK_MONTHLY_CAP_USD (OD-2)",
            "opening_units": min(opening, cap), "opening_evidence": evidence,
            "price_as_of": "2026-11-03", "price_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "price_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED", "calls": {}, "daily": {},
            "blocked": blocked, "cap_history": [], **({"virtual": True} if virtual else {})}


def _ensure_month(p, budget_path=None):
    """Create THIS month's envelope from config if absent. Caller holds the lock.

    Never touches an existing file, a fixed (explicit-path) envelope, or a past
    or future month.
    """
    if not monthly(budget_path) or p.exists() or p != path():
        return False
    DG.atomic_write_json(p, _fresh(month_id()))
    return True


def _peek(p, budget_path=None):
    """Load, or for an absent current month the envelope the first call WOULD create."""
    if monthly(budget_path) and p == path() and not p.exists():
        return _fresh(month_id(), virtual=True)
    return _load(p)


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
    code = "BLOCKED" if s.get("blocked") else "EXHAUSTED" if held >= cap else None
    head = f"DEEPSEEK BUDGET REFUSED ({code})" if code else "DEEPSEEK BUDGET OK"
    created = "; not yet created, the first call creates it" if s.get("virtual") else ""
    tail = f" -- {_HINTS[code]}" if code else ""
    return (f"{head}: {s.get('month') or s.get('session_id')} held ${held:.4f} of ${cap:.2f} cap "
            f"(peak list estimate, {len(s['calls'])} calls; envelope {p.name}{created}){tail}")


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
        _ensure_month(p, budget_path)
        s = _load(p)
        if new <= s["cap_units"]:
            raise BudgetRefused(f"raise refused: ${cap_usd} is not above the current "
                                f"${s['cap_units']/SCALE:.2f} cap (a cap is never lowered)")
        s.setdefault("cap_history", []).append({"from_units": s["cap_units"], "to_units": new,
            "evidence": str(evidence), "utc": datetime.now(timezone.utc).isoformat()})
        s["cap_units"] = new
        DG.atomic_write_json(p, s)
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
            _ensure_month(p, budget_path)
            s = _load(p)
        except BudgetRefused as exc:
            if str(exc).startswith("DEEPSEEK BUDGET"):
                raise
            raise BudgetRefused(status_line(budget_path=budget_path)) from exc
        if s.get("blocked"):
            raise _refuse("BLOCKED", s, p)
        if _held(s) + q["reserved_units"] > s["cap_units"]:
            raise _refuse("EXHAUSTED", s, p)
        day = datetime.now(timezone.utc).date().isoformat()
        if production_cap is not None:
            if s["daily"].get(day, 0) >= production_cap:
                raise _refuse(f"DAILY_CALL_CAP: {production_cap} calls", s, p)
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
    """Locked read. An absent current month reads as the envelope the first
    call would create (`virtual: True`); nothing is written."""
    p = Path(budget_path) if budget_path else path()
    with _lock(p):
        s = _peek(p, budget_path)
        s["held_usd"] = _held(s)/SCALE
        return s


def preflight_snapshot():
    """Read-only advisory check; atomic envelope replacements need no sidecar.

    Never creates directories/locks or writes accounting. Reservations still
    re-read under the authoritative lock before any provider dispatch. An absent
    current month reads as the fresh envelope the first reservation creates.
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
    sub.add_parser("init", help="create this month's envelope from config now")
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
                made = _ensure_month(p)
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
        return 2 if line.startswith("DEEPSEEK BUDGET REFUSED") else 0
    except BudgetRefused as exc:
        text = str(exc)
        print(text if text.startswith("DEEPSEEK BUDGET") else f"DEEPSEEK BUDGET REFUSED: {text}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
