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

SCOPE (review #88 R2; widened by CH-05 R2, 2026-11-11): this envelope binds
the DeepSeek calls that go through `attempt()` -- `llm_analyzer._call_llm` /
`call_named` and their callers, and every caller of `guarded_create()` (an
OpenAI-SDK client) or `guarded_send()` (raw HTTP): `llm_swarm`,
`model_provider`, `llm_research`, `why_moved`, `leakage_probe`, and the
scripts `book_factory`, `companyworld_extract`, `era_replay_v2`,
`n6b_fantasy_exams_round2`, `recall_canary_positive_control`, `stack_health`.
The DeepSeek call sites listed in `UNCAPPED_DEEPSEEK_PATHS` call the provider
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
import re
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
#: CH-05 R2 (2026-11-11) routed eleven and reclassified one (connection_check
#: probes DeepSeek at /user/balance only). What is left cannot be reserved by
#: this envelope without changing what the call sends:
#:   architecture_arena -- a multi-turn transcript, and a v4-pro arm that has no
#:                         price authority here;
#:   copilot            -- tool calls, a growing history and no max_tokens;
#:   optimus_specialists -- no max_tokens, so no output bound to reserve.
UNCAPPED_DEEPSEEK_PATHS = (
    "backend/services/architecture_arena.py",
    "backend/services/copilot.py",
    "backend/services/optimus_specialists.py",
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


def _utcnow():
    return datetime.now(timezone.utc)


#: Blocks raised by a settlement that could reach neither the envelope nor the
#: sidecar (review 3 O2). Latched per envelope path for THIS process: its readers
#: see the block and its next `reserve()` persists it before admitting anything.
_UNRECORDED_BLOCKS: dict = {}


def _sidecar_lock(p):
    """The sidecar's own lock. Order is always envelope -> sidecar, and a writer
    that could not take the envelope lock takes only this one, so a settlement
    that timed out on the envelope can still be recorded (review 3 R1)."""
    sp = sidecar_path(p)
    return DG.file_lock(sp.with_name(sp.name + ".lock"), timeout_s=5)


def _append_sidecar(p, row):
    """One fsynced line under the sidecar lock. A torn last line (a crash or a
    full disk mid-write) is terminated first, so it can never swallow this row
    (review 3 O1)."""
    sp = sidecar_path(p)
    with _sidecar_lock(p):
        with open(sp, "ab+") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() > 0:
                fh.seek(-1, os.SEEK_END)
                if fh.read(1) != b"\n":
                    fh.write(b"\n")
            fh.write((json.dumps(row, sort_keys=True) + "\n").encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())


def _read_sidecar(p, *, locked=True):
    """The sidecar's bytes (b"" when absent). `locked=False` is for the
    read-only readers (`_peek`), which never create a lock file."""
    sp = sidecar_path(p)
    if not sp.exists():
        return b""
    if not locked:
        try:
            return sp.read_bytes()
        except OSError:
            return b""
    with _sidecar_lock(p):
        try:
            return sp.read_bytes()
        except FileNotFoundError:
            return b""


def _consume_sidecar(p, raw):
    """Remove the `raw` prefix that was just applied; keep anything appended
    since (a writer that could not take the envelope lock). Idempotent: a line
    left behind is a no-op on the next reconcile."""
    if not raw:
        return
    sp = sidecar_path(p)
    try:
        with _sidecar_lock(p):
            now = sp.read_bytes() if sp.exists() else b""
            if not now.startswith(raw):
                return                                  # rewritten meanwhile: leave it
            rest = now[len(raw):]
            if rest:
                tmp = sp.with_name(sp.name + f".{uuid.uuid4().hex}.tmp")
                tmp.write_bytes(rest)
                os.replace(tmp, sp)
            else:
                sp.unlink()
    except (OSError, DG.FileLockTimeout) as exc:        # idempotent: re-applied lines no-op
        logger.warning("provider_budget: sidecar not cleared (%s); its lines are no-ops now", exc)


def _clear_sidecar(p):
    _consume_sidecar(p, _read_sidecar(p))


def _sidecar_lines(raw):
    return [ln for ln in raw.decode("utf-8", errors="replace").splitlines() if ln.strip()]


def _orphan_key(o):
    return json.dumps(o, sort_keys=True, default=str)


def _price(bounds, response):
    """Pure settlement arithmetic, shared by `settle`, the lock-free fallback in
    `attempt` and the sidecar reconcile (which recomputes from tokens, review 3
    O5). `bounds` carries input_bound / output_bound / reserved_units."""
    served = response.get("model") if isinstance(response, dict) else getattr(response, "model", None)
    usage = response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)

    def get(name):
        return usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    ti, to = get("prompt_tokens"), get("completion_tokens")
    cached = get("prompt_cache_hit_tokens")
    cached = 0 if cached is None else cached
    return _price_tokens(bounds, served, ti, to, cached, answered=response is not None)


def _price_tokens(bounds, served, ti, to, cached, *, answered=True):
    block = "unknown returned model" if answered and served not in MODELS else None
    valid = (served in MODELS and all(type(x) is int and x >= 0 for x in (ti, to, cached))
             and cached <= ti and ti+to > 0)
    cost = None
    if valid:
        cost = _units(((ti-cached)*PRICE["in"] + cached*PRICE["cached_in"] + to*PRICE["out"])/1e6)
        if (ti > bounds["input_bound"] or to > bounds["output_bound"]
                or cost > bounds["reserved_units"]):
            block = "provider usage exceeded request reservation bound"
    return {"status": "SETTLED_PEAK_ESTIMATE" if valid else "BILLING_UNKNOWN",
            "cost_units": cost, "served": served, "block": block,
            "tokens": {"ti": ti, "to": to, "cached": cached}}


def _apply_sidecar(p, s, raw):
    """Apply deferred settlements in `raw` to `s` in memory. Returns how many
    changed `s`.

    A line applies only to a call still RESERVED_UNKNOWN in this envelope; a
    line for a call already settled is a no-op (idempotent after a crash between
    the envelope write and the sidecar removal). A line naming no call here is
    kept on the envelope as an orphan, never silently dropped and never twice
    (review 3 O3). A deferred block is applied whatever the call's state. The
    cost is recomputed from the line's TOKENS against the call's own bounds; a
    line without tokens keeps the full reservation (review 3 O5).
    """
    applied = 0
    orphans = list(s.get("sidecar_orphans") or [])
    seen = {_orphan_key(o) for o in orphans}

    def orphan(o):
        nonlocal applied
        k = _orphan_key(o)
        if k not in seen:
            seen.add(k)
            orphans.append(o)
            applied += 1
    for ln in _sidecar_lines(raw):
        try:
            row = json.loads(ln)
            if not isinstance(row, dict):
                raise ValueError("not an object")
        except ValueError:
            orphan({"unparsed": ln[:200]})
            continue
        if row.get("blocked") and not s.get("blocked"):
            s["blocked"] = row["blocked"]
            applied += 1
        r = s["calls"].get(row.get("reservation_id"))
        if r is None:
            orphan(row)
            continue
        if r["status"] != "RESERVED_UNKNOWN":
            continue
        tk = {k: row.get(k) for k in ("ti", "to", "cached")}
        if (row.get("status") == "SETTLED_PEAK_ESTIMATE"
                and all(type(v) is int for v in tk.values())):
            pr = _price_tokens(r, row.get("served_model"), tk["ti"], tk["to"], tk["cached"])
        else:
            pr = {"status": "BILLING_UNKNOWN", "cost_units": None, "block": None}
        if pr["status"] == "SETTLED_PEAK_ESTIMATE":
            r.update(status="SETTLED_PEAK_ESTIMATE", held_units=pr["cost_units"],
                     cost_usd=pr["cost_units"] / SCALE)
        else:
            r["status"] = "BILLING_UNKNOWN"            # keeps the full reservation held
        if pr["block"] and not s.get("blocked"):
            s["blocked"] = pr["block"]
        r.update(served_model=row.get("served_model"), settled_utc=row.get("settled_utc"),
                 reconciled_from_sidecar=True)
        applied += 1
    if orphans:
        s["sidecar_orphans"] = orphans
    return applied


def _apply_latch(p, s):
    reason = _UNRECORDED_BLOCKS.get(str(Path(p)))
    if reason and not s.get("blocked"):
        s["blocked"] = reason
        return 1
    return 0


def _reconcile_sidecar(p, s):
    """Read the sidecar (locked) and apply it to `s` in memory."""
    return _apply_sidecar(p, s, _read_sidecar(p))


def _sidecar_state(raw, now=None):
    """(pending lines, age in hours of the oldest; None when any is undateable).
    Dated by the rows' own stamps, never by the file's mtime."""
    lines = _sidecar_lines(raw)
    if not lines:
        return 0, None
    stamps = []
    for ln in lines:
        try:
            row = json.loads(ln)
            t = datetime.fromisoformat(str(row.get("deferred_utc") or row.get("settled_utc")))
            if t.tzinfo is None:
                raise ValueError("naive stamp")
            stamps.append(t)
        except (ValueError, TypeError, AttributeError):
            return len(lines), None
    return len(lines), ((now or _utcnow()) - min(stamps)).total_seconds() / 3600


def reconcile(*, budget_path=None):
    """Apply the sidecar to the envelope now (the next `reserve()` would do the
    same). Returns the status line."""
    p = Path(budget_path) if budget_path else path()
    with _lock(p):
        s = _load(p)
        raw = _read_sidecar(p)
        if _apply_sidecar(p, s, raw) + _apply_latch(p, s):
            _write(p, s)
        _UNRECORDED_BLOCKS.pop(str(p), None)
        _consume_sidecar(p, raw)
    return status_line(budget_path=budget_path)


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
    # Review 3 R2: every reader (status, preflight, snapshot, the dashboard)
    # sees the TRUE spend and any deferred block: the sidecar and this
    # process's unrecorded blocks are applied IN MEMORY. Nothing is written and
    # no lock file is created.
    s = _load(p)
    raw = _read_sidecar(p, locked=False)
    _apply_sidecar(p, s, raw)
    _apply_latch(p, s)
    v = dict(_view(s, budget_path))
    v["sidecar_pending"], v["sidecar_oldest_age_h"] = _sidecar_state(raw)
    return v


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
    "SIDECAR_STALE": f"the next paid call reconciles it, or run `{CLI} reconcile` now",
}


def _cfg():
    from backend import config as C
    return C


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
    pending, age_h = s.get("sidecar_pending") or 0, s.get("sidecar_oldest_age_h")
    limit_h = float(getattr(_cfg(), "DEEPSEEK_SIDECAR_STALE_HOURS", 12.0))
    if code:
        head = f"DEEPSEEK BUDGET REFUSED ({code})"
    elif pending and (age_h is None or age_h > limit_h):
        # an unreconciled sidecar is a date that must be compared (review 3 R2);
        # an undateable line is UNKNOWN, never fresh
        code = "SIDECAR_STALE"
        head = "DEEPSEEK BUDGET DEGRADED (SIDECAR_STALE)"
    else:
        head = "DEEPSEEK BUDGET OK"
    created = "; not yet created, the first call creates it" if s.get("virtual") else ""
    tail = f" -- {_HINTS[code]}" if code else ""
    side = ""
    if pending:
        age = "age unknown" if age_h is None else f"oldest {age_h:.1f} h"
        side = (f"; {pending} deferred settlement(s) pending in the sidecar ({age}, limit "
                f"{limit_h:g} h), counted in the held amount")
    scope = (f"; covers calls routed through attempt(), {len(UNCAPPED_DEEPSEEK_PATHS)} other DeepSeek "
             f"call-site files are UNCAPPED (`{CLI} status` lists them)"
             if UNCAPPED_DEEPSEEK_PATHS else "")
    return (f"{head}: {s.get('month') or s.get('session_id')} held ${held:.4f} of ${cap:.2f} cap "
            f"(peak list estimate, {len(s['calls'])} calls; envelope {p.name}{created}{side}"
            f"{scope}){tail}")


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
        raw = _read_sidecar(p)
        if _apply_sidecar(p, s, raw) + _apply_latch(p, s):
            _write(p, s)
        _UNRECORDED_BLOCKS.pop(str(p), None)
        _consume_sidecar(p, raw)                     # only what was applied; later lines stay
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
    # the bounds travel on the ticket so a settlement that cannot read the
    # envelope can still be priced and checked (review 3 R1)
    return {"id": token, "path": str(p), "reserved_usd": q["reserved_units"]/SCALE,
            "reserved_units": q["reserved_units"], "input_bound": q["input_bound"],
            "output_bound": q["output_bound"]}


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
        pr = _price(r, response)
        if pr["block"]:
            s["blocked"] = pr["block"]
        if pr["status"] == "SETTLED_PEAK_ESTIMATE":
            cost = pr["cost_units"]
            r.update(status="SETTLED_PEAK_ESTIMATE", held_units=cost, cost_usd=cost/SCALE)
        else:
            r["status"] = "BILLING_UNKNOWN"
        r["served_model"] = pr["served"]
        r["settled_utc"] = _utcnow().isoformat()
        out = {"cost_usd": r["cost_usd"], "budget_charge_usd": r["held_units"]/SCALE,
               "price_as_of": "2026-11-03", "cost_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED",
               "billing_status": r["status"], "reservation_id": ticket["id"]}
        try:
            _write(p, s)
        except PermissionError as exc:
            # The reply is PAID: keep it. The envelope on disk still holds the
            # full reservation; every reader applies the sidecar in memory
            # (`_peek`), so spend is not under-counted even when the cost
            # exceeds the reservation; the settlement and any block it raised
            # wait in the sidecar for the next reserve.
            out.update(_defer(ticket, pr, r["settled_utc"], exc,
                              new_block=s.get("blocked") if not was_blocked else None))
        return out


def _defer(ticket, pr, settled_utc, exc, *, new_block):
    """Record a settlement the envelope could not take. Returns the accounting
    fields to report. Never raises: the caller holds a PAID reply."""
    p = Path(ticket["path"])
    row = {"reservation_id": ticket["id"], "status": pr["status"],
           "held_units": pr["cost_units"], **pr["tokens"], "served_model": pr["served"],
           "settled_utc": settled_utc, "deferred_utc": _utcnow().isoformat(),
           "blocked": new_block, "error": f"{type(exc).__name__}: {exc}"[:200]}
    held_now = max(ticket["reserved_units"], pr["cost_units"] or 0)
    try:
        _append_sidecar(p, row)
        return {"billing_status": DEFERRED_STATUS, "settlement_deferred": True,
                "budget_charge_usd": held_now / SCALE}
    except Exception as exc2:                               # noqa: BLE001
        # nothing on disk moved: the reservation stays held, the reply is kept,
        # and a block it raised is latched for this process (review 3 O2)
        if new_block:
            _UNRECORDED_BLOCKS[str(p)] = new_block
        logger.error("provider_budget: settlement of %s not recorded (%s; sidecar %s); "
                     "the full reservation stays held%s", ticket["id"], exc, exc2,
                     "; its block is latched in this process" if new_block else "")
        return {"billing_status": "SETTLEMENT_FAILED_RESERVATION_RETAINED",
                "budget_charge_usd": held_now / SCALE, "settlement_deferred": False}


def snapshot(*, budget_path=None):
    """Locked read of the running month's view. An absent host envelope reads
    as the one the first call would create (`virtual: True`); nothing is written."""
    p = Path(budget_path) if budget_path else path()
    with _lock(p):
        s = _peek(p, budget_path)
        s["held_usd"] = _held(s)/SCALE
        return s


def preflight_snapshot():
    """Read-only advisory check. Deferred settlements in the sidecar (and any
    block they carry) are applied in memory, so it sees true spend (review 3).

    Never creates directories/locks or writes accounting. Reservations still
    re-read under the authoritative lock before any provider dispatch. Returns
    the running month's view; an absent host envelope reads as the fresh one
    the first reservation creates.
    """
    return _peek(path())


#: The request keys a reservation can price (see `attempt`).
_ADMITTED_OPTIONS = frozenset({"model", "messages", "max_tokens", "temperature",
                               "extra_body", "response_format"})
_JSON_OBJECT = {"type": "json_object"}
#: The base URL a caller that names none is assumed to speak to.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def guarded_send(body, *, purpose, send, base_url=DEEPSEEK_BASE_URL, production_cap=None):
    """One DeepSeek request through the envelope on a host that requires it.

    Returns `(response, accounting)`. On a host where the envelope is not
    required (Railway/Linux without `AEGIS_DEEPSEEK_HOST_ENVELOPE=1`) it is the
    plain `send()` and `accounting` is None, exactly like
    `llm_analyzer._budgeted_deepseek_create`. A refusal raises `BudgetRefused`
    with `no_wire = True` and nothing was sent; the caller must make it a red,
    non-zero outcome, never an empty success.
    """
    if not host_envelope_required():
        return send(), None
    return attempt(body, base_url=base_url, purpose=purpose, send=send,
                   production_cap=production_cap)


def guarded_create(client, body, *, purpose, send, production_cap=None):
    """One OpenAI-SDK DeepSeek request through the envelope.

    `send(transport)` is the caller's own `transport.chat.completions.create(
    **body)`. It stays written AT THE CALL SITE on purpose: the language
    contract (`llm_language.DIRECT_CALL_SITES`) and the call-site guard find
    call sites by that expression, and a helper that hid it would hide the
    module from both. On the envelope host `transport` is the client with SDK
    retries disabled -- an SDK retry is a second billable request inside ONE
    reservation; callers keep their own retry loops, and each of their retries
    is a new reservation. Elsewhere it is the client unchanged. Returns
    `(response, accounting)`; see `guarded_send`.
    """
    if not host_envelope_required():
        return send(client), None
    with_options = getattr(client, "with_options", None)
    transport = with_options(max_retries=0) if callable(with_options) else client
    return attempt(body, base_url=str(getattr(client, "base_url", None) or DEEPSEEK_BASE_URL),
                   purpose=purpose, production_cap=production_cap,
                   send=lambda: send(transport))


def attempt(body, *, base_url, purpose, send, production_cap=None):
    """Reserve/settle one existing transport invocation; no retries or routing.

    `send` is the caller's existing SDK/requests/urllib operation. It must raise
    on a transport/HTTP failure and return the raw provider object or JSON dict.

    `response_format={"type": "json_object"}` is admitted (CH-05 R2): JSON mode
    changes the reply's form, not what is billed -- settlement prices the
    returned usage, and the input bound in `quote()` already carries 1024
    tokens of protocol overhead. Any other `response_format` is refused.
    """
    if (set(body) - _ADMITTED_OPTIONS
            or body.get("extra_body", {}) not in ({}, {"thinking": {"type": "disabled"}})
            or body.get("response_format", _JSON_OBJECT) != _JSON_OBJECT):
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
    try:
        return response, finish(response)
    except Exception as exc:                                    # noqa: BLE001
        # Review 3 R1: the provider ANSWERED, so the reply is paid and is
        # returned whatever settlement raised (a lock timeout, an unreadable
        # envelope, a busy disk). The envelope still holds the full
        # RESERVED_UNKNOWN reservation; the priced settlement goes to the
        # sidecar, which every reader applies in memory and the next reserve
        # writes.
        pr = _price(ticket, response)
        acct = {"cost_usd": None if pr["cost_units"] is None else pr["cost_units"] / SCALE,
                "price_as_of": "2026-11-03", "cost_basis": "PEAK_LIST_ESTIMATE_NOT_BILLED",
                "reservation_id": ticket["id"], "settle_error": type(exc).__name__}
        acct.update(_defer(ticket, pr, _utcnow().isoformat(), exc, new_block=pr["block"]))
        return response, acct


# ───────────────── FEATHERLESS: the second provider's own envelope ─────────────────
#
# Owner, 2026-11-11: "we have 75$ usd in featherless api use it", for bulk work,
# through the same kind of guard as DeepSeek and never uncapped. Measured the
# same day (`GET /v1/plan`, `/credits/balance`): the account is on Featherless's
# REQUEST-PRICING plan -- a prepaid credit balance billed per token, per model,
# successful requests only, credits never expire -- with ~$74.50 left. So the
# cap is in dollars, exactly like DeepSeek's: a monthly cap AND a lifetime
# ceiling (the owner's $75), both from config.
#
# WHY ITS OWN FILE (`session_budget/featherless_local.json`), not a provider key
# inside `deepseek_local.json`: that file is shared with the runtime's 10-15
# guard, which reads `cap_units` as a LIFETIME DeepSeek cap capped at $20 and
# sums every call's `held_units` against it. A Featherless row there would be
# spent out of DeepSeek's cap by the old code and the $75 lifetime would fail
# `_load`'s $20 contract. A separate file keeps the two ledgers independent; a
# Featherless refusal never touches DeepSeek's room and vice versa.
#
# Same contract as above, smaller machinery: reserve a worst-case bound BEFORE
# dispatch (bytes + 1024 tokens of input at the model's configured price, plus
# max_tokens of output), refuse an unpriced model, settle from the returned
# usage (the larger of our price x tokens and the provider's own `usage.cost`),
# keep the FULL reservation when billing is unknown, and block the envelope
# when a reply exceeds its bound or names a different model. There is no
# Railway exemption: a Featherless call is capped on every host.

FEATHERLESS_SCHEMA = "local_featherless_envelope/1"
FEATHERLESS_ENVELOPE_NAME = "featherless_local.json"
FEATHERLESS_HOST = "api.featherless.ai"
_FL_HINTS = {
    "EXHAUSTED_MONTH": "monthly cap reached; future months: AEGIS_FEATHERLESS_MONTHLY_CAP_USD "
                       "(config.FEATHERLESS_MONTHLY_CAP_USD)",
    "EXHAUSTED_LIFETIME": "lifetime ceiling reached (config.FEATHERLESS_LIFETIME_CAP_USD, the owner's "
                          "stated credit); only the owner raises it",
    "BLOCKED": f"attended reconciliation required; see `{CLI} status --provider featherless`",
    "UNREADABLE": "envelope unreadable or malformed; inspect it, never delete or replace one holding spend",
    "UNPRICED": "the model is not in config.FEATHERLESS_MODELS with a row in LLM_PRICE_PER_MTOK; add its price "
                "(GET /v1/models/<id> .pricing) before using it",
    "CONFIG": "fix FEATHERLESS_MONTHLY_CAP_USD / FEATHERLESS_LIFETIME_CAP_USD in backend/config.py",
}


def featherless_path():
    override = os.getenv("AEGIS_FEATHERLESS_BUDGET_PATH")
    return Path(override) if override else _default_dir() / FEATHERLESS_ENVELOPE_NAME


def _fl_caps():
    """(monthly, lifetime) caps in units, from config. Refuses a nonsense pair."""
    C = _cfg()
    month = float(getattr(C, "FEATHERLESS_MONTHLY_CAP_USD", 0.0))
    life = float(getattr(C, "FEATHERLESS_LIFETIME_CAP_USD", 0.0))
    if not (0 < month <= life) or life > float(getattr(C, "FEATHERLESS_HARD_CAP_USD", 75.0)):
        raise BudgetRefused(f"FEATHERLESS BUDGET REFUSED (CONFIG): month ${month} / lifetime ${life} "
                            f"-- {_FL_HINTS['CONFIG']}")
    return _units(month), _units(life)


def _fl_price(model):
    """(in, out) USD/1M from THE rate table, for a model named in FEATHERLESS_MODELS only."""
    C = _cfg()
    row = ((getattr(C, "LLM_PRICE_PER_MTOK", {}) or {}).get(str(model))
           if str(model) in tuple(getattr(C, "FEATHERLESS_MODELS", ()) or ()) else None)
    if (not isinstance(row, dict) or not all(isinstance(row.get(k), (int, float)) and row[k] >= 0
                                             for k in ("in", "out"))):
        raise BudgetRefused(f"FEATHERLESS BUDGET REFUSED (UNPRICED): {model!r} -- {_FL_HINTS['UNPRICED']}")
    return float(row["in"]), float(row["out"])


def featherless_quote(system, user, max_tokens, model):
    """Worst-case bound for two plain messages. Raises for an unpriced model."""
    if type(max_tokens) is not int or max_tokens <= 0:
        raise BudgetRefused("FEATHERLESS BUDGET REFUSED: invalid output bound")
    p_in, p_out = _fl_price(model)
    ti = len((system + user).encode("utf-8")) + 1024
    return {"input_bound": ti, "output_bound": max_tokens,
            "reserved_units": _units((ti*p_in + max_tokens*p_out)/1e6)}


def _fl_fresh():
    C = _cfg()
    return {"schema": FEATHERLESS_SCHEMA, "provider": "featherless",
            "created_utc": _utcnow().isoformat(),
            "cap_source": "config.FEATHERLESS_MONTHLY_CAP_USD / FEATHERLESS_LIFETIME_CAP_USD",
            "price_source": "config.LLM_PRICE_PER_MTOK rows for FEATHERLESS_MODELS (GET /v1/models/<id> .pricing)",
            "price_as_of": str(getattr(C, "FEATHERLESS_PRICE_AS_OF", "")),
            "calls": {}, "blocked": None}


def _fl_load(p):
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        if s.get("schema") != FEATHERLESS_SCHEMA or not isinstance(s.get("calls"), dict):
            raise ValueError("invalid envelope contract")
        for r in s["calls"].values():
            if type(r.get("held_units")) is not int or r["held_units"] < 0:
                raise ValueError("invalid held amount")
            if r.get("status") not in {"RESERVED_UNKNOWN", "BILLING_UNKNOWN", "SETTLED",
                                       "UNBILLED_HTTP_REFUSAL"}:
                raise ValueError("unknown settlement status")
        return s
    except Exception as exc:
        raise BudgetRefused(f"FEATHERLESS BUDGET REFUSED (UNREADABLE): {p.name} -- "
                            f"{_FL_HINTS['UNREADABLE']}") from exc


def _fl_held(s, month=None):
    return sum(r["held_units"] for r in s["calls"].values()
               if month is None or _month_of(r.get("started_utc")) in (month, None))


def _fl_view(p):
    """(state, month held, lifetime held, month cap, lifetime cap); an absent
    file reads as the empty one the first call creates. Never writes."""
    s = _fl_load(p) if p.exists() else {**_fl_fresh(), "virtual": True}
    month_cap, life_cap = _fl_caps()
    return s, _fl_held(s, month_id()), _fl_held(s), month_cap, life_cap


def _fl_refuse(code, held_m, held_l, cap_m, cap_l):
    exc = BudgetRefused(
        f"FEATHERLESS BUDGET REFUSED ({code}): {month_id()} held ${held_m/SCALE:.4f} of "
        f"${cap_m/SCALE:.2f} month cap; lifetime ${held_l/SCALE:.4f} of ${cap_l/SCALE:.2f} "
        f"(envelope {FEATHERLESS_ENVELOPE_NAME}) -- {_FL_HINTS[code]}")
    exc.no_wire = True
    return exc


def featherless_status_line(*, budget_path=None):
    """One human line, like `status_line()`. Never raises."""
    p = Path(budget_path) if budget_path else featherless_path()
    try:
        s, held_m, held_l, cap_m, cap_l = _fl_view(p)
    except BudgetRefused as exc:
        return str(exc)
    code = ("BLOCKED" if s.get("blocked") else "EXHAUSTED_LIFETIME" if cap_l - held_l <= 0
            else "EXHAUSTED_MONTH" if cap_m - held_m <= 0 else None)
    head = f"FEATHERLESS BUDGET REFUSED ({code})" if code else "FEATHERLESS BUDGET OK"
    made = "; not yet created, the first call creates it" if s.get("virtual") else ""
    n_month = sum(1 for r in s["calls"].values() if _month_of(r.get("started_utc")) in (month_id(), None))
    return (f"{head}: {month_id()} held ${held_m/SCALE:.4f} of ${cap_m/SCALE:.2f} month cap, lifetime "
            f"${held_l/SCALE:.4f} of ${cap_l/SCALE:.2f} ({n_month} calls this month; envelope "
            f"{p.name}{made})" + (f" -- {_FL_HINTS[code]}" if code else ""))


def featherless_reserve(system, user, max_tokens, *, model, base_url, purpose, budget_path=None):
    u = urlsplit(base_url)
    if (u.scheme != "https" or u.hostname != FEATHERLESS_HOST or u.port not in (None, 443)
            or u.username or u.password or u.query or u.fragment):
        exc = BudgetRefused("FEATHERLESS BUDGET REFUSED: price authority requires the official "
                            "HTTPS Featherless endpoint")
        exc.no_wire = True
        raise exc
    q = featherless_quote(system, user, max_tokens, model)
    p = Path(budget_path) if budget_path else featherless_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _lock(p):
        s = _fl_load(p) if p.exists() else _fl_fresh()
        month_cap, life_cap = _fl_caps()
        held_m, held_l = _fl_held(s, month_id()), _fl_held(s)
        if s.get("blocked"):
            raise _fl_refuse("BLOCKED", held_m, held_l, month_cap, life_cap)
        if held_l + q["reserved_units"] > life_cap:
            raise _fl_refuse("EXHAUSTED_LIFETIME", held_m, held_l, month_cap, life_cap)
        if held_m + q["reserved_units"] > month_cap:
            raise _fl_refuse("EXHAUSTED_MONTH", held_m, held_l, month_cap, life_cap)
        token = uuid.uuid4().hex
        s["calls"][token] = {**q, "held_units": q["reserved_units"], "status": "RESERVED_UNKNOWN",
                             "pid": os.getpid(), "purpose": str(purpose), "request_model": str(model),
                             "started_utc": _utcnow().isoformat(), "cost_usd": None}
        _write(p, s)
    return {"id": token, "path": str(p), "reserved_usd": q["reserved_units"]/SCALE,
            "reserved_units": q["reserved_units"], "input_bound": q["input_bound"],
            "output_bound": q["output_bound"], "model": str(model)}


#: Reply classes (S66, revised after the PR #131 review). The row's `status`
#: stays inside the four values every reader of this file already accepts (an
#: older release clone sharing the file refuses an unknown status as UNREADABLE,
#: which would stop every caller); the finer class travels in `reply_class`.
#: Money is released to $0 ONLY on an HTTP error status actually observed.
#:   NO_RESPONSE            send() raised with no HTTP status (timeout, reset, DNS):
#:                          BILLING_UNKNOWN, full reservation held, no block
#:   HTTP_AMBIGUOUS         an observed status after which generation MAY have run
#:                          (config.FEATHERLESS_AMBIGUOUS_HTTP_STATUSES: 408 499 502 504 524):
#:                          BILLING_UNKNOWN, full reservation held, no block
#:   HTTP_ERROR             any other observed 4xx/5xx (403 gated, 429, 503, ...):
#:                          UNBILLED_HTTP_REFUSAL, released to $0, no block
#:   EMPTY_2XX              a reply with no model, no usage and no choices (e.g. an
#:                          error body the SDK still parsed): BILLING_UNKNOWN, full
#:                          reservation held (we cannot prove it was not billed); rate rule
#:   SERVED_MODEL_MISSING   a reply with usage or choices but NO model: BILLING_UNKNOWN,
#:                          full reservation held; rate rule
#:   SERVED_MODEL_MISMATCH  a reply naming a DIFFERENT model: BILLING_UNKNOWN, full
#:                          reservation held, envelope BLOCKED ("unknown returned model")
#:   USAGE_MISSING          the right model, unreadable usage: BILLING_UNKNOWN, held, no block
#:   OK                     SETTLED at the higher of our price and the provider's cost
#:   ABANDONED_DEAD_PID     set by the attended reconcile on a stale RESERVED_UNKNOWN row
#: Rate rule (`_fl_missing_model_block`): EMPTY_2XX and SERVED_MODEL_MISSING block
#: the envelope only past FEATHERLESS_MISSING_MODEL_MAX_IN_WINDOW of the last
#: WINDOW calls or MAX_CONSECUTIVE in a row; each is held at full reservation.
FL_REPLY_CLASSES = ("NO_RESPONSE", "HTTP_AMBIGUOUS", "HTTP_ERROR", "EMPTY_2XX", "SERVED_MODEL_MISSING",
                    "SERVED_MODEL_MISMATCH", "USAGE_MISSING", "OK", "ABANDONED_DEAD_PID")
_FL_RATE_CLASSES = ("EMPTY_2XX", "SERVED_MODEL_MISSING")
_FL_ERROR_FIELDS = ("error", "detail", "message")
_FL_TOKENISH = re.compile(r"(?i)bearer\s+\S+|[A-Za-z0-9_\-]{24,}")


class FeatherlessReply:
    """What a Featherless `send()` returns to carry the REAL HTTP status of the
    reply it read (`with_raw_response`). A bare reply is accepted too; its status
    is then recorded as unknown (None), never assumed."""
    __slots__ = ("response", "http_status")

    def __init__(self, response, http_status=None):
        self.response = response
        self.http_status = http_status if type(http_status) is int else None


def _fl_field(obj, name):
    """A field of a dict reply or of an SDK object (incl. pydantic extras)."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    val = getattr(obj, name, None)
    if val is None:
        extra = getattr(obj, "model_extra", None)
        if isinstance(extra, dict):
            val = extra.get(name)
    return val


def _fl_reply_keys(response):
    """Top-level field NAMES present in a reply (never values): a receipt of its shape."""
    if isinstance(response, dict):
        return sorted(str(k) for k in response)[:20]
    names = [k for k, v in (getattr(response, "__dict__", {}) or {}).items()
             if not str(k).startswith("_") and v is not None]
    names += list((getattr(response, "model_extra", None) or {}).keys())
    return sorted({str(k) for k in names})[:20]


def _fl_quotes(msg, prompt):
    """True when `msg` repeats any 16-character run of the prompt."""
    if not msg or not prompt or len(msg) < 16:
        return False
    return any(msg[i:i+16] in prompt for i in range(len(msg) - 15))


def _fl_error_excerpt(source, prompt=""):
    """A short, redacted description of an error: the exception class, the body's
    type/code and <= 80 characters of its message with anything token-like (a key,
    a bearer header) redacted; the message is dropped if it quotes the prompt."""
    parts, body = [], source
    if isinstance(source, BaseException):
        parts.append(type(source).__name__)
        body = getattr(source, "body", None)
        if not isinstance(body, dict) or not body:
            body = {"message": str(getattr(source, "message", "") or "")}
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        body = body["error"]
    msg = ""
    if isinstance(body, dict):
        for k in ("type", "code"):
            v = body.get(k)
            if v not in (None, ""):
                parts.append(f"{k}={str(v)[:40]}")
        msg = body.get("message") or body.get("detail") or ""
        if not isinstance(msg, str):
            msg = ""
    elif isinstance(body, str):
        msg = body
    msg = _FL_TOKENISH.sub("<redacted>", " ".join(str(msg).split()))[:80]
    if msg and _fl_quotes(msg, prompt or ""):
        msg = "<dropped: quotes the prompt>"
    if msg:
        parts.append(f"msg={msg}")
    return "; ".join(parts)[:200] or None


def _fl_classify(ticket, response, prompt=""):
    """{status, reply_class, held, cost, reported, served, block, error_excerpt}."""
    full = ticket["reserved_units"]
    unknown = {"status": "BILLING_UNKNOWN", "held": full, "cost": None, "reported": None,
               "served": None, "block": None, "error_excerpt": None}
    if response is None:
        return {**unknown, "reply_class": "NO_RESPONSE"}
    served = _fl_field(response, "model")
    usage = _fl_field(response, "usage")

    def get(name):
        return usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
    ti, to, reported = get("prompt_tokens"), get("completion_tokens"), get("cost")
    try:
        reported = float(reported) if reported is not None else None
        if reported is not None and (not reported >= 0 or reported != reported):
            reported = None
    except (TypeError, ValueError):
        reported = None
    if served in (None, ""):
        err = next((v for v in (_fl_field(response, f) for f in _FL_ERROR_FIELDS) if v), None)
        empty = usage is None and not _fl_field(response, "choices")
        return {**unknown, "reply_class": "EMPTY_2XX" if empty else "SERVED_MODEL_MISSING",
                "reported": reported,
                "error_excerpt": _fl_error_excerpt(err, prompt) if err is not None else None}
    if served != ticket["model"]:
        return {**unknown, "reply_class": "SERVED_MODEL_MISMATCH", "reported": reported,
                "served": served, "block": "unknown returned model"}
    if not all(type(x) is int and x >= 0 for x in (ti, to)) or ti + to <= 0:
        return {**unknown, "reply_class": "USAGE_MISSING", "reported": reported, "served": served}
    p_in, p_out = _fl_price(served)
    ours = _units((ti*p_in + to*p_out)/1e6)
    held = max(ours, _units(reported) if reported is not None else 0)
    block = None
    if ti > ticket["input_bound"] or to > ticket["output_bound"] or held > ticket["reserved_units"]:
        block = "provider usage exceeded request reservation bound"
    return {"status": "SETTLED", "reply_class": "OK", "held": held, "cost": held/SCALE,
            "reported": reported, "served": served, "block": block, "error_excerpt": None}


def _fl_price_reply(ticket, response):
    """(status, held_units, cost_usd, provider_cost_usd, served, block) -- the old
    tuple, kept for any reader of it; `_fl_classify` carries the reply class."""
    c = _fl_classify(ticket, response)
    return c["status"], c["held"], c["cost"], c["reported"], c["served"], c["block"]


def _fl_last_settled(s, window):
    return sorted((r for r in s["calls"].values() if r.get("settled_utc")),
                  key=lambda r: str(r.get("settled_utc")))[-window:]


def _fl_missing_model_block(s):
    """A block reason when MORE than MAX_IN_WINDOW of the last WINDOW settled
    calls, or MORE than MAX_CONSECUTIVE in a row, were EMPTY_2XX or
    SERVED_MODEL_MISSING; else None. Each such call is held at its full
    reservation, so the envelope over-holds until the block."""
    C = _cfg()
    window = max(1, int(getattr(C, "FEATHERLESS_MISSING_MODEL_WINDOW", 50)))
    max_in = int(getattr(C, "FEATHERLESS_MISSING_MODEL_MAX_IN_WINDOW", 5))
    max_run = int(getattr(C, "FEATHERLESS_MISSING_MODEL_MAX_CONSECUTIVE", 3))
    last = _fl_last_settled(s, window)
    n = sum(1 for r in last if r.get("reply_class") in _FL_RATE_CLASSES)
    run = 0
    for r in reversed(last):
        if r.get("reply_class") not in _FL_RATE_CLASSES:
            break
        run += 1
    if n > max_in:
        return (f"served model missing or empty on {n} of the last {len(last)} calls "
                f"(limit {max_in} of {window})")
    if run > max_run:
        return f"served model missing or empty on {run} consecutive calls (limit {max_run})"
    return None


def featherless_health(s):
    """(unbilled-or-unknown count, settled calls looked at, window, max share)."""
    C = _cfg()
    window = max(1, int(getattr(C, "FEATHERLESS_MISSING_MODEL_WINDOW", 50)))
    last = _fl_last_settled(s, window)
    bad = sum(1 for r in last if r.get("status") in ("BILLING_UNKNOWN", "UNBILLED_HTTP_REFUSAL"))
    return bad, len(last), window, float(getattr(C, "FEATHERLESS_STATUS_MAX_BAD_SHARE", 0.20))


def featherless_settle(ticket, response=None, *, http_status=None, error_class=None,
                       error_excerpt=None, prompt=""):
    """Never releases money on an unknown outcome; a bound breach blocks the file.

    `http_status` is the status the client OBSERVED: for a raised error, the
    exception's status; for a reply, the raw response's status, or None when the
    client could not read it (never assumed). Featherless bills successful
    requests only (docs/request-pricing-and-credits), so an observed 4xx/5xx
    settles at $0 as UNBILLED_HTTP_REFUSAL -- except the statuses after which
    generation may have run (FEATHERLESS_AMBIGUOUS_HTTP_STATUSES), which keep the
    full reservation. A returned reply is classified by `_fl_classify` (see
    FL_REPLY_CLASSES). `prompt` is used only to drop an excerpt that quotes it;
    it is never stored.

    A write that fails after a PAID reply keeps the reply: the envelope still
    holds the full reservation (never less than the cost unless the bound was
    breached, which is what the block is for) and the error is logged."""
    ambiguous = tuple(getattr(_cfg(), "FEATHERLESS_AMBIGUOUS_HTTP_STATUSES", (408, 499, 502, 504, 524)))
    if response is None and type(http_status) is int and 400 <= http_status < 600:
        if http_status in ambiguous:
            c = {"status": "BILLING_UNKNOWN", "reply_class": "HTTP_AMBIGUOUS", "held": ticket["reserved_units"],
                 "cost": None, "reported": None, "served": None, "block": None}
        else:
            c = {"status": "UNBILLED_HTTP_REFUSAL", "reply_class": "HTTP_ERROR", "held": 0, "cost": 0.0,
                 "reported": None, "served": None, "block": None}
        c["error_excerpt"] = error_excerpt
    else:
        c = _fl_classify(ticket, response, prompt)
        if response is None:
            c["error_excerpt"] = error_excerpt
    status, held, cost, reported, served, block = (c["status"], c["held"], c["cost"], c["reported"],
                                                   c["served"], c["block"])
    p = Path(ticket["path"])
    # an unknown outcome returns the full reservation as `held`
    out = {"cost_usd": cost, "budget_charge_usd": held / SCALE,
           "provider_cost_usd": reported, "billing_status": status, "reply_class": c["reply_class"],
           "reservation_id": ticket["id"],
           "price_as_of": str(getattr(_cfg(), "FEATHERLESS_PRICE_AS_OF", "")),
           "cost_basis": "CONFIG_PRICE_X_TOKENS_OR_PROVIDER_COST_WHICHEVER_HIGHER",
           "budget_envelope": FEATHERLESS_ENVELOPE_NAME}
    try:
        with _lock(p):
            s = _fl_load(p)
            r = s["calls"][ticket["id"]]
            if r["status"] != "RESERVED_UNKNOWN":
                raise BudgetRefused("reservation already settled")
            now = _utcnow().isoformat()
            r.update(status=status, held_units=(held if status in ("SETTLED", "UNBILLED_HTTP_REFUSAL")
                                                else r["held_units"]),
                     http_status=http_status if type(http_status) is int else None,
                     reply_class=c["reply_class"],
                     error_class=(str(error_class)[:80] if error_class else None),
                     error_excerpt=(str(c["error_excerpt"])[:200] if c.get("error_excerpt") else None),
                     cost_usd=cost, provider_cost_usd=reported, served_model=served,
                     settled_utc=now)
            if response is not None:
                r["reply_keys"] = _fl_reply_keys(response)
            if not block and c["reply_class"] in _FL_RATE_CLASSES:
                block = _fl_missing_model_block(s)
            if block and not s.get("blocked"):
                s["blocked"] = block
                s["blocked_by"] = {"reservation_id": ticket["id"], "utc": now, "reason": block,
                                   "reply_class": c["reply_class"], "http_status": r["http_status"],
                                   "error_excerpt": r["error_excerpt"],
                                   "purpose": r.get("purpose"), "pid": r.get("pid")}
            _write(p, s)
    except (OSError, DG.FileLockTimeout, BudgetRefused) as exc:
        logger.error("provider_budget: featherless settlement of %s not recorded (%s); "
                     "the full reservation stays held", ticket["id"], exc)
        out.update(billing_status="SETTLEMENT_FAILED_RESERVATION_RETAINED",
                   budget_charge_usd=max(held, ticket["reserved_units"]) / SCALE)
    return out


def featherless_attempt(body, *, purpose, send, base_url=None, budget_path=None):
    """Reserve/settle ONE Featherless request. Returns `(response, accounting)`.

    Same admission as `attempt()`: two plain messages, the priced options and
    JSON mode only. A refusal raises `BudgetRefused` with `no_wire = True` and
    nothing was sent; the caller makes it red, never an empty success. `send`
    may retry 429/503 inside one reservation: Featherless bills successful
    requests only, so a refused attempt costs nothing and one success fits.
    `send` returns the reply, or a `FeatherlessReply(reply, http_status)` carrying
    the status it read from the wire."""
    base_url = base_url or str(getattr(_cfg(), "FEATHERLESS_BASE_URL", f"https://{FEATHERLESS_HOST}/v1"))
    messages = body.get("messages") or []
    if (set(body) - _ADMITTED_OPTIONS or body.get("extra_body", {}) != {}
            or body.get("response_format", _JSON_OBJECT) != _JSON_OBJECT
            or len(messages) != 2 or messages[0].get("role") != "system"
            or messages[1].get("role") != "user"
            or any(type(m.get("content")) is not str for m in messages)):
        exc = BudgetRefused("FEATHERLESS BUDGET REFUSED: unsupported billable request options")
        exc.no_wire = True
        raise exc
    try:
        ticket = featherless_reserve(messages[0]["content"], messages[1]["content"], body.get("max_tokens"),
                                     model=body.get("model"), base_url=base_url, purpose=purpose,
                                     budget_path=budget_path)
    except Exception as exc:
        exc.no_wire = True
        raise
    prompt = messages[0]["content"] + "\n" + messages[1]["content"]
    try:
        out = send()
    except BaseException as exc:
        code = getattr(exc, "status_code", None)
        if code is None:
            code = getattr(getattr(exc, "response", None), "status_code", None)
        try:
            exc.shared_budget_accounting = featherless_settle(
                ticket, None, http_status=code if type(code) is int else None,
                error_class=type(exc).__name__, error_excerpt=_fl_error_excerpt(exc, prompt), prompt=prompt)
        except Exception:                                        # noqa: BLE001
            pass
        raise
    if isinstance(out, FeatherlessReply):
        response, code = out.response, out.http_status
    else:
        response, code = out, None
    return response, featherless_settle(ticket, response, http_status=code, prompt=prompt)


# ───────────── FEATHERLESS: status details and the attended reconcile (S66) ─────────────
#
# 2026-11-12: a block ("unknown returned model") had no exit -- `reconcile` was
# DeepSeek-only -- so one malformed reply would have refused every Featherless
# caller until someone edited the file by hand. The reconcile below is the exit,
# and it is conservative: it clears a MODEL-IDENTITY block only when the envelope
# holds at least what the provider's own balance says was spent since the
# envelope's opening balance, and it writes who/when/what/why into `history`.
# A refused run writes ONLY a history row saying so.

class FeatherlessBalanceUnavailable(RuntimeError):
    """The Featherless balance could not be read. NOT a zero, NOT a stale number."""


def _fl_pid_alive(pid):
    from backend.services.sim_session import pid_alive
    return pid_alive(pid)


def _fl_no_redirect_opener():
    """`urllib` opener that never follows a redirect: the Authorization header
    must never reach another host. A 3xx surfaces as an HTTPError."""
    import urllib.request

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
            return None
    return urllib.request.build_opener(_NoRedirect).open


def _fl_balance_from(payload):
    """The USD balance under one of config.FEATHERLESS_BALANCE_FIELDS, or raise."""
    C = _cfg()
    if not isinstance(payload, dict):
        raise FeatherlessBalanceUnavailable(f"balance reply is not a JSON object ({type(payload).__name__})")
    max_usd = float(getattr(C, "FEATHERLESS_BALANCE_MAX_USD", 150.0))
    seen = sorted(str(k) for k in payload)[:20]
    if isinstance(payload.get("data"), dict):
        seen += [f"data.{k}" for k in sorted(payload["data"])][:20]
    for path in tuple(getattr(C, "FEATHERLESS_BALANCE_FIELDS", ()) or ()):
        container, cur, ok = payload, payload, True
        for part in str(path).split("."):
            if isinstance(cur, dict) and part in cur:
                container, cur = cur, cur[part]
            else:
                ok = False
                break
        if not ok:
            continue
        cur_code = container.get("currency") if isinstance(container, dict) else None
        if cur_code is not None and str(cur_code).upper() != "USD":
            raise FeatherlessBalanceUnavailable(f"field {path!r} is in {cur_code!r}, not USD")
        if isinstance(cur, bool) or not isinstance(cur, (int, float, str)):
            raise FeatherlessBalanceUnavailable(f"field {path!r} is not a number (fields seen: {seen})")
        try:
            usd = float(cur)
        except ValueError:
            raise FeatherlessBalanceUnavailable(f"field {path!r} is not a number (fields seen: {seen})") from None
        if not (usd >= 0 and usd <= max_usd):
            raise FeatherlessBalanceUnavailable(
                f"field {path!r} = {usd!r} is outside 0..{max_usd:g} USD "
                f"(config.FEATHERLESS_BALANCE_MAX_USD; a unit mix-up or not this account)")
        return usd, str(path), seen
    raise FeatherlessBalanceUnavailable(
        f"no accepted USD balance field in the reply (fields seen: {seen}; accepted: "
        f"{list(getattr(C, 'FEATHERLESS_BALANCE_FIELDS', ()))}); add the exact path to "
        f"config.FEATHERLESS_BALANCE_FIELDS, or pass --observed-balance with --evidence at a terminal")


def featherless_read_balance(*, opener=None, url=None, api_key=None):
    """USD balance from the free balance endpoint (no completion call, $0).

    The key is read from `config.FEATHERLESS_KEY_ENV` and sent ONLY to the official
    HTTPS host, with redirects refused; it is never printed, returned or stored.
    Raises `FeatherlessBalanceUnavailable` when the request fails or the reply has
    no accepted field (see `_fl_balance_from`)."""
    import urllib.error
    import urllib.request
    C = _cfg()
    url = str(url or getattr(C, "FEATHERLESS_BALANCE_URL", f"https://{FEATHERLESS_HOST}/credits/balance"))
    u = urlsplit(url)
    if (u.scheme != "https" or u.hostname != FEATHERLESS_HOST or u.port not in (None, 443)
            or u.username or u.password):
        raise FeatherlessBalanceUnavailable("the balance URL must be the official HTTPS Featherless host")
    key = api_key if api_key is not None else os.getenv(
        str(getattr(C, "FEATHERLESS_KEY_ENV", "FEATHERLESS_API_KEY")), "").strip()
    if not key:
        raise FeatherlessBalanceUnavailable(
            f"{getattr(C, 'FEATHERLESS_KEY_ENV', 'FEATHERLESS_API_KEY')} is not set; the balance cannot be read")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        _open = opener or _fl_no_redirect_opener()
        with _open(req, timeout=float(getattr(C, "FEATHERLESS_BALANCE_TIMEOUT_S", 20.0))) as resp:
            final = getattr(resp, "geturl", lambda: url)()
            if urlsplit(str(final)).hostname not in (None, FEATHERLESS_HOST):
                raise FeatherlessBalanceUnavailable("the balance reply came from another host")
            payload = json.loads(resp.read().decode("utf-8"))
    except FeatherlessBalanceUnavailable:
        raise
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        raise FeatherlessBalanceUnavailable(f"{type(exc).__name__}: balance request failed") from exc
    usd, field, seen = _fl_balance_from(payload)
    return {"balance_usd": usd, "read_utc": _utcnow().isoformat(), "source": "GET " + u.path,
            "field": field, "fields": seen}


def featherless_status_detail(*, budget_path=None, now=None, pid_alive=None):
    """Counts by status / reply class / purpose, the block and the call that set
    it, unsettled rows by pid liveness, the recent unbilled/unknown share, the
    last observed balance. Never writes."""
    p = Path(budget_path) if budget_path else featherless_path()
    s, held_m, held_l, cap_m, cap_l = _fl_view(p)
    now = now or _utcnow()
    alive = pid_alive or _fl_pid_alive
    stale_min = float(getattr(_cfg(), "FEATHERLESS_RECONCILE_STALE_MINUTES", 30.0))
    by_status, by_class, by_purpose = {}, {}, {}
    open_rows = []
    for k, r in s["calls"].items():
        st = r.get("status")
        by_status[st] = by_status.get(st, 0) + 1
        rc = r.get("reply_class") or ("(not recorded)" if st != "RESERVED_UNKNOWN" else "(in flight)")
        by_class[rc] = by_class.get(rc, 0) + 1
        key = f"{st} {r.get('purpose')}"
        by_purpose[key] = by_purpose.get(key, 0) + 1
        if st == "RESERVED_UNKNOWN":
            try:
                age = (now - datetime.fromisoformat(str(r.get("started_utc")))).total_seconds() / 60
            except (TypeError, ValueError):
                age = None
            open_rows.append({"id": k, "pid": r.get("pid"), "age_min": None if age is None else round(age, 1),
                              "pid_alive": bool(alive(r.get("pid"))),
                              "stale": age is None or age > stale_min, "held_usd": r["held_units"] / SCALE})
    held_by = {st: sum(r["held_units"] for r in s["calls"].values() if r.get("status") == st) / SCALE
               for st in by_status}
    bad, n_last, window, max_share = featherless_health(s)
    obs = (s.get("balance_observations") or [])
    return {"envelope": str(p), "created_utc": s.get("created_utc"), "n_calls": len(s["calls"]),
            "by_status": by_status, "held_usd_by_status": held_by, "by_reply_class": by_class,
            "by_status_purpose": by_purpose, "held_lifetime_usd": held_l / SCALE,
            "held_month_usd": held_m / SCALE, "blocked": s.get("blocked"),
            "blocked_by": s.get("blocked_by") or (
                "not recorded (this block was set before `blocked_by` existed)" if s.get("blocked") else None),
            "unsettled": open_rows, "opening_balance_usd": s.get("opening_balance_usd"),
            "baseline_held_usd": int(s.get("baseline_held_units") or 0) / SCALE,
            "recent_bad": bad, "recent_n": n_last, "recent_window": window, "recent_max_share": max_share,
            "degraded": n_last > 0 and bad > max_share * n_last,
            "last_balance_observation": obs[-1] if obs else None,
            "n_history": len(s.get("history") or [])}


def _fl_who(who):
    if who is not None:
        return str(who)
    import getpass
    import socket
    return f"{getpass.getuser()}@{socket.gethostname()}"


def _fl_clearable(reason):
    allow = tuple(getattr(_cfg(), "FEATHERLESS_RECONCILE_CLEARABLE_BLOCKS", ()) or ())
    return any(str(reason).startswith(a) for a in allow)


def featherless_reconcile(*, dry_run=False, opening_balance_usd=None, observed_balance_usd=None,
                          evidence=None, clear_reason=None, budget_path=None, balance_reader=None,
                          pid_alive=None, now=None, who=None, interactive=None):
    """The attended reconcile. Returns `{"rc", "decision", "lines", ...}`; rc 0
    done (or nothing to do), 2 refused. `dry_run` makes the balance request only
    and writes nothing.

    1. observed balance X: the free endpoint (`balance_reader`); or an operator's
       `observed_balance_usd`, which needs `evidence` AND an interactive terminal
       (recorded `manual: true`);
    2. opening O: the envelope's stored one (set by the first NON-refused
       reconcile, or by `featherless_rebaseline`); a different `--opening-balance`
       is refused; X > O is refused (a top-up: rebaseline first);
       observed spend = O - X; held = lifetime held - the baseline's held;
    3. a block is cleared ONLY when its reason is a model-identity block
       (config.FEATHERLESS_RECONCILE_CLEARABLE_BLOCKS) or `clear_reason` repeats
       it exactly with `evidence`, AND held >= observed spend;
    4. on success: RESERVED_UNKNOWN rows older than FEATHERLESS_RECONCILE_STALE_MINUTES
       with a dead pid are settled BILLING_UNKNOWN at their FULL reservation
       (never lowered: one account balance cannot attribute spend to a row), the
       opening is stored if new, the observation is appended, and a cleared block
       gets a `history` evidence row;
    5. on refusal: ONLY a `history` row saying it was refused and why (none on a
       dry run, none when there is no envelope)."""
    p = Path(budget_path) if budget_path else featherless_path()
    now = now or _utcnow()
    alive = pid_alive or _fl_pid_alive
    stale_min = float(getattr(_cfg(), "FEATHERLESS_RECONCILE_STALE_MINUTES", 30.0))
    lines = []
    manual = observed_balance_usd is not None

    def refuse(why, **extra):
        lines.append(f"FEATHERLESS RECONCILE REFUSED: {why}")
        if not dry_run and p.exists():
            try:
                with _lock(p):                      # re-entrant when the caller holds it
                    s2 = _fl_load(p)
                    s2.setdefault("history", []).append(
                        {"utc": now.isoformat(), "action": "reconcile_refused", "who": _fl_who(who),
                         "reason": why[:400], "manual": manual,
                         **{k: v for k, v in extra.items() if isinstance(v, (int, float, str, type(None)))}})
                    _write(p, s2)
            except (BudgetRefused, OSError, DG.FileLockTimeout) as exc:
                lines.append(f"(the refusal itself could not be recorded: {type(exc).__name__})")
        return {"rc": 2, "decision": "REFUSED", "reason": why, "lines": lines, "dry_run": dry_run, **extra}

    if not p.exists():
        return refuse(f"no envelope at {p.name}")
    if manual:
        if interactive is None:
            try:
                interactive = bool(sys.stdin and sys.stdin.isatty())
            except (AttributeError, ValueError):
                interactive = False
        if not interactive:
            return refuse("NOT_A_TERMINAL: --observed-balance is an operator reading and needs an "
                          "interactive terminal; a script reads the endpoint instead")
        if not (evidence and str(evidence).strip()):
            return refuse("--observed-balance needs --evidence (where the number was read)")
        try:
            observed = float(observed_balance_usd)
        except (TypeError, ValueError):
            return refuse("--observed-balance is not a number")
        max_usd = float(getattr(_cfg(), "FEATHERLESS_BALANCE_MAX_USD", 150.0))
        if not (observed >= 0 and observed <= max_usd):
            return refuse(f"--observed-balance must be within 0..{max_usd:g} USD")
        obs = {"balance_usd": observed, "read_utc": now.isoformat(), "source": "operator",
               "manual": True, "evidence": str(evidence)[:300]}
    else:
        try:
            obs = (balance_reader or featherless_read_balance)()
        except FeatherlessBalanceUnavailable as exc:
            return refuse(f"balance unavailable: {exc}")
        observed = float(obs["balance_usd"])
    lines.append(f"observed balance ${observed:.4f} ({obs.get('source')}, {obs.get('read_utc')})")

    with (_lock(p) if not dry_run else _NullCtx()):
        s = _fl_load(p)
        stored = s.get("opening_balance_usd")
        if stored is not None and opening_balance_usd is not None and abs(float(stored) - float(opening_balance_usd)) > 1e-9:
            return refuse(f"--opening-balance ${float(opening_balance_usd):.4f} differs from the envelope's "
                          f"stored ${float(stored):.4f}; change it only with `rebaseline --provider featherless`")
        opening = float(stored) if stored is not None else (
            float(opening_balance_usd) if opening_balance_usd is not None else None)
        if opening is None or not opening >= 0 or opening == float("inf"):
            return refuse("no opening balance: pass --opening-balance USD (2026-11-11 measurement: $74.50)")
        if observed > opening + 1e-9:
            return refuse(f"observed ${observed:.4f} is ABOVE the opening ${opening:.4f} (a top-up or a unit "
                          f"mix-up); after a top-up run `rebaseline --provider featherless`",
                          observed_balance_usd=observed)
        spend_units = _units(opening - observed)
        base = int(s.get("baseline_held_units") or 0)
        held = _fl_held(s) - base
        blocked = s.get("blocked")
        lines.append(f"opening ${opening:.4f} -> observed spend ${spend_units/SCALE:.6f}; envelope holds "
                     f"${held/SCALE:.6f} since the baseline ({len(s['calls'])} rows)")
        if clear_reason is not None and clear_reason != blocked:
            return refuse(f"--clear-reason does not match the block exactly (block: {blocked!r})")
        if blocked and not _fl_clearable(blocked):
            if clear_reason != blocked or not (evidence and str(evidence).strip()):
                return refuse(f"block {blocked!r} is not a model-identity block; clearing it needs "
                              f"--clear-reason \"<exact reason>\" --evidence TEXT")
        if held < spend_units:
            return refuse(f"envelope holds ${held/SCALE:.6f} < observed provider spend ${spend_units/SCALE:.6f}"
                          f" (block {'kept' if blocked else 'not set'}); spend outside this envelope or an "
                          f"under-priced row -- inspect before any call",
                          held_usd=held / SCALE, observed_spend_usd=spend_units / SCALE)
        settle_ids, left_alone = [], []
        for k, r in s["calls"].items():
            if r.get("status") != "RESERVED_UNKNOWN":
                continue
            try:
                age = (now - datetime.fromisoformat(str(r.get("started_utc")))).total_seconds() / 60
            except (TypeError, ValueError):
                age = None
            if age is not None and age > stale_min and not alive(r.get("pid")):
                settle_ids.append(k)
            else:
                left_alone.append((k, r.get("pid"), None if age is None else round(age, 1)))
        lines.append(f"stale RESERVED_UNKNOWN with a dead pid -> settle at full reservation: {len(settle_ids)}"
                     + (f" ({', '.join(i[:8] for i in settle_ids[:8])}{' ...' if len(settle_ids) > 8 else ''})"
                        if settle_ids else ""))
        for k, pid, age in left_alone:
            lines.append(f"left alone (pid {pid} alive or row younger than {stale_min:g} min; age {age}): {k[:8]}")
        decision = "CLEAR_BLOCK" if blocked else "NO_BLOCK"
        if not dry_run:
            stamp = now.isoformat()
            for k in settle_ids:
                s["calls"][k].update(status="BILLING_UNKNOWN", reply_class="ABANDONED_DEAD_PID",
                                     settled_utc=stamp, settled_by="reconcile")
            if stored is None:
                s["opening_balance_usd"] = opening
                s["baseline_held_units"] = 0
                s["opening_balance_evidence"] = "first non-refused reconcile --opening-balance (attended)"
            s.setdefault("balance_observations", []).append(
                {**{k: v for k, v in obs.items() if k != "fields"}, "observed_spend_usd": spend_units / SCALE,
                 "held_usd": held / SCALE, "decision": decision, "utc": stamp})
            if decision == "CLEAR_BLOCK":
                s.setdefault("history", []).append({
                    "utc": stamp, "action": "unblock", "previous_block": blocked,
                    "blocked_by": s.get("blocked_by"), "who": _fl_who(who), "manual": manual,
                    "clear_reason": clear_reason,
                    "observed_balance_usd": observed, "balance_source": obs.get("source"),
                    "opening_balance_usd": opening, "observed_spend_usd": spend_units / SCALE,
                    "held_usd": held / SCALE, "settled_dead_pid_rows": len(settle_ids),
                    "why": "held >= observed provider spend since the opening balance: the envelope is "
                           "conservative, so the block is cleared by attended reconcile"
                           + (f"; operator evidence: {str(evidence)[:200]}" if evidence else "")})
                s["blocked"] = None
                s.pop("blocked_by", None)
            _write(p, s)
    verb = "would " if dry_run else ""
    lines.append(f"{verb}{'clear the block ' + repr(blocked) if decision == 'CLEAR_BLOCK' else 'keep: no block set'}"
                 f"; {verb}settle {len(settle_ids)} dead-pid rows; {verb}record the observation")
    return {"rc": 0, "decision": decision, "lines": lines, "dry_run": dry_run, "held_usd": held / SCALE,
            "observed_spend_usd": spend_units / SCALE, "settled": len(settle_ids),
            "left_alone": len(left_alone), "observed_balance_usd": observed}


def featherless_rebaseline(*, opening_balance_usd, evidence, at_creation=False, budget_path=None,
                           now=None, who=None):
    """Attended: set the opening balance the reconcile compares against, for a
    top-up (default: the balance NOW; the held amount so far becomes the
    baseline) or a typo (`at_creation`: the balance when the envelope opened).
    Records old/new/who/when/why in `history`; never touches a block; refuses
    without evidence text. Returns `{"rc", "lines"}`."""
    p = Path(budget_path) if budget_path else featherless_path()
    now = now or _utcnow()
    if not (evidence and str(evidence).strip()):
        return {"rc": 2, "lines": ["FEATHERLESS REBASELINE REFUSED: --evidence TEXT is required "
                                   "(why the opening changes: a top-up, a typo, a statement)"]}
    try:
        x = float(opening_balance_usd)
    except (TypeError, ValueError):
        return {"rc": 2, "lines": ["FEATHERLESS REBASELINE REFUSED: --opening-balance is not a number"]}
    max_usd = float(getattr(_cfg(), "FEATHERLESS_BALANCE_MAX_USD", 150.0))
    if not (x >= 0 and x <= max_usd):
        return {"rc": 2, "lines": [f"FEATHERLESS REBASELINE REFUSED: --opening-balance outside 0..{max_usd:g} USD"]}
    if not p.exists():
        return {"rc": 2, "lines": [f"FEATHERLESS REBASELINE REFUSED: no envelope at {p.name}"]}
    with _lock(p):
        s = _fl_load(p)
        old, old_base = s.get("opening_balance_usd"), int(s.get("baseline_held_units") or 0)
        new_base = 0 if at_creation else _fl_held(s)
        s["opening_balance_usd"] = x
        s["baseline_held_units"] = new_base
        s["opening_balance_evidence"] = f"rebaseline: {str(evidence)[:200]}"
        s.setdefault("history", []).append({
            "utc": now.isoformat(), "action": "rebaseline", "who": _fl_who(who),
            "old_opening_usd": old, "new_opening_usd": x,
            "old_baseline_held_usd": old_base / SCALE, "new_baseline_held_usd": new_base / SCALE,
            "as_of": "creation" if at_creation else "now", "why": str(evidence)[:300],
            "block_untouched": s.get("blocked")})
        _write(p, s)
    return {"rc": 0, "lines": [f"opening ${old if old is None else f'{float(old):.4f}'} -> ${x:.4f} "
                               f"(as of {'creation' if at_creation else 'now'}; baseline held "
                               f"${new_base/SCALE:.6f}); block {'untouched: ' + repr(s.get('blocked')) if s.get('blocked') else 'none'}"]}


class _NullCtx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main(argv=None):
    """`status` (exit 0 admits, 1 admits but DEGRADED, 2 refuses) | `init` |
    `raise --cap USD --evidence TEXT` | `reconcile` (apply the sidecar now).
    `status --provider featherless` reads the Featherless envelope instead."""
    import argparse
    ap = argparse.ArgumentParser(prog="provider_budget")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="print the accounting line; exit 2 when refusing")
    st.add_argument("--provider", choices=("deepseek", "featherless"), default="deepseek")
    sub.add_parser("init", help="create the host envelope from config now (if absent)")
    rc_ = sub.add_parser("reconcile", help="deepseek: apply deferred settlements (the sidecar) now; "
                                           "featherless: attended balance reconcile (can clear a block)")
    rc_.add_argument("--provider", choices=("deepseek", "featherless"), default="deepseek")
    rc_.add_argument("--dry-run", action="store_true", help="featherless: read the balance, write nothing")
    rc_.add_argument("--opening-balance", type=float, default=None,
                     help="featherless: USD balance when the envelope opened (first reconcile only)")
    rc_.add_argument("--observed-balance", type=float, default=None,
                     help="featherless: an operator-read USD balance instead of the endpoint (needs --evidence)")
    rc_.add_argument("--evidence", default=None)
    rc_.add_argument("--clear-reason", default=None,
                     help="featherless: the EXACT reason of a non-model-identity block, to clear it (with --evidence)")
    rb = sub.add_parser("rebaseline", help="featherless: set the opening balance (top-up, typo); attended")
    rb.add_argument("--provider", choices=("featherless",), required=True)
    rb.add_argument("--opening-balance", type=float, required=True)
    rb.add_argument("--evidence", default=None)
    rb.add_argument("--at-creation", action="store_true",
                    help="the balance when the envelope opened (a typo fix), not the balance now (a top-up)")
    r = sub.add_parser("raise", help="raise this month's cap (attended)")
    r.add_argument("--cap", type=float, required=True)
    r.add_argument("--evidence", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "status" and a.provider == "featherless":
        line = featherless_status_line()
        print(line)
        try:
            d = featherless_status_detail()
        except BudgetRefused:
            d = None
        if d is not None:
            print(f"by status: {d['by_status']}  held by status: "
                  + ", ".join(f"{k} ${v:.6f}" for k, v in d["held_usd_by_status"].items()))
            print(f"by reply class: {d['by_reply_class']}")
            for k, v in sorted(d["by_status_purpose"].items()):
                print(f"  {v:6d}  {k}")
            if d["blocked"]:
                print(f"blocked: {d['blocked']}")
                print(f"blocked by: {d['blocked_by']}")
            for o in d["unsettled"]:
                print(f"unsettled {o['id'][:8]} pid {o['pid']} ({'alive' if o['pid_alive'] else 'dead'}), "
                      f"age {o['age_min']} min, held ${o['held_usd']:.6f}"
                      + (" -- stale: `reconcile --provider featherless` settles it at full reservation"
                         if o["stale"] and not o["pid_alive"] else ""))
            lo = d["last_balance_observation"]
            print(f"opening balance: {d['opening_balance_usd']} (baseline held ${d['baseline_held_usd']:.6f}); "
                  "last observed: "
                  + (f"${lo['balance_usd']:.4f} at {lo.get('utc') or lo.get('read_utc')} ({lo.get('decision')})"
                     if lo else "never (run `reconcile --provider featherless --dry-run`)"))
            print(f"last {d['recent_n']} settled calls: {d['recent_bad']} unbilled or unknown "
                  f"(limit {d['recent_max_share']:.0%})")
        if line.startswith("FEATHERLESS BUDGET REFUSED"):
            return 2
        if d is not None and d["degraded"]:
            print(f"FEATHERLESS BUDGET DEGRADED: {d['recent_bad']} of the last {d['recent_n']} calls were "
                  f"unbilled or unknown (> {d['recent_max_share']:.0%}); inspect the reply classes above")
            return 1
        return 0
    if a.cmd == "reconcile" and a.provider == "featherless":
        try:
            res = featherless_reconcile(dry_run=a.dry_run, opening_balance_usd=a.opening_balance,
                                        observed_balance_usd=a.observed_balance, evidence=a.evidence,
                                        clear_reason=a.clear_reason)
        except (BudgetRefused, DG.FileLockTimeout) as exc:
            print(f"FEATHERLESS RECONCILE REFUSED: {exc}")
            return 2
        for ln in res["lines"]:
            print(("[dry-run] " if a.dry_run else "") + ln)
        if not a.dry_run:
            print(featherless_status_line())
        return int(res["rc"])
    if a.cmd == "rebaseline":
        try:
            res = featherless_rebaseline(opening_balance_usd=a.opening_balance, evidence=a.evidence,
                                         at_creation=a.at_creation)
        except (BudgetRefused, DG.FileLockTimeout) as exc:
            print(f"FEATHERLESS REBASELINE REFUSED: {exc}")
            return 2
        for ln in res["lines"]:
            print(ln)
        return int(res["rc"])
    if a.cmd == "reconcile" and (a.dry_run or a.opening_balance is not None or a.clear_reason is not None
                                 or a.observed_balance is not None or a.evidence is not None):
        print("DEEPSEEK BUDGET REFUSED: --dry-run/--opening-balance/--observed-balance/--evidence/"
              "--clear-reason belong to `reconcile --provider featherless`")
        return 2
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
        elif a.cmd == "reconcile":
            reconcile()
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
        if line.startswith("DEEPSEEK BUDGET REFUSED"):
            return 2
        return 1 if line.startswith("DEEPSEEK BUDGET DEGRADED") else 0
    except (BudgetRefused, DG.FileLockTimeout) as exc:
        text = str(exc)
        print(text if text.startswith("DEEPSEEK BUDGET") else f"DEEPSEEK BUDGET REFUSED: {text}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
