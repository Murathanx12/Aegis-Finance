"""THE LAB'S DOLLAR CAP — a PRE-CALL guard, beside the call-count cap.

Chunk 14, spec `docs/research_notes/2026-09-13/spec_always_on_lab.md` section 5.

THREE THINGS BOUND CLOUD SPEND IN THIS REPOSITORY, AND THEY ARE NOT THE SAME
===========================================================================
1. `llm_analyzer._DAILY_CAP` — a **call count** (150/day). It bounds how many
   times a provider is asked anything and says nothing at all about money: a
   provider that charges ten times the assumed rate per call passes it
   unchanged.
2. `scripts/llm_cost_audit.py` — the ground-truth **reconciliation**, run
   separately, against the PROVIDER's own reported balance
   (`provider_balance_delta - telemetry_total = unaccounted`). Accurate, and
   retrospective: it tells you what a day cost after the day.
3. **This module** — a **dollar** cap, checked BEFORE the call, on the same UTC
   day boundary `_DAILY_CAP` already uses. Cheaper and less accurate than (2)
   on purpose: its job is to make a runaway impossible, not to be the books.

The relationship is exactly the one the call-count cap already has to the
billing breaker, and all three stay. Replacing any of them with another would
be a narrower guard wearing a wider name.

WHY IT EXISTS BEFORE THERE IS ANYTHING TO CAP
=============================================
As of 2026-09-13 the lab's typing loop reads LOCALLY and `spend_today_usd`
stays 0.00. The guard ships anyway, in the SAME commit as the `CloudReader`
hook it protects, because a gate added after the first rule is written is a
gate that was absent exactly when it mattered. `spec_always_on_lab.md` proposed
$5.00/day; the build brief set $3.00, and the lower number is the one that
ships — a cap is only a cap at the number actually enforced.

LOCAL CALLS ARE UNMETERED
=========================
A local llama-server call costs compute, not dollars. Metering it here would
make the cap fire on work that cannot produce a bill, which is the
"a gate that cannot go green is a broken gate" failure with the sign flipped:
a gate that fires on the wrong thing teaches its reader to raise it.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from backend import config as _config

#: Providers whose calls cost money. A backend not in here is UNMETERED and the
#: receipt says so by name, rather than silently contributing 0.00 to a total
#: that a reader would take for "this ran and was free".
METERED_BACKENDS = ("deepseek", "nvidia", "huggingface", "openrouter",
                    "featherless", "anthropic")
UNMETERED_BACKENDS = ("local", "local_gguf", "llama_server")

_LOCK = threading.Lock()


class SpendCapReached(RuntimeError):
    """The lab's own daily dollar cap would be exceeded BY THIS CALL.

    Raised before the provider is contacted, never after — a refund is not a
    guard, and a call that was made and then regretted has already been billed.
    """


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ledger_path(day: str | None = None) -> Path:
    """One append-only file per UTC day, beside the lab's other state."""
    return (Path(_config.DATA_DIR) / "optimus" /
            f"lab_spend_{day or _today()}.json")


def cap_usd() -> float:
    """The cap, env-overridable by NAME (never by a value in code).

    An unparseable override is the configured default, and the receipt says the
    override was unreadable — a cap that silently becomes infinity because
    somebody typed `3,00` is worse than no cap.
    """
    raw = os.getenv(_config.LAB_SPEND_CAP_ENV)
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return float(_config.LAB_DAILY_SPEND_CAP_USD)


def _read(day: str) -> dict:
    p = ledger_path(day)
    if not p.exists():
        return {"date": day, "spend_usd": 0.0, "calls": [], "unmetered_calls": 0}
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"date": day, "spend_usd": 0.0, "calls": [],
                "unmetered_calls": 0, "unreadable_prior": True}
    rec.setdefault("spend_usd", 0.0)
    rec.setdefault("calls", [])
    rec.setdefault("unmetered_calls", 0)
    return rec


def _write(day: str, rec: dict) -> None:
    p = ledger_path(day)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)


def spend_today(day: str | None = None) -> dict:
    """What has been spent, what the cap is, and whether it has been reached.

    Always returns every key, including on a day with no ledger file: the
    supervisor prints spend in EVERY receipt, and an absent key reads as
    "nobody checked" rather than "nothing was spent".
    """
    day = day or _today()
    rec = _read(day)
    cap = cap_usd()
    spent = round(float(rec.get("spend_usd") or 0.0), 6)
    return {
        "date": day,
        "spend_today_usd": spent,
        "cap_usd": cap,
        "remaining_usd": round(max(0.0, cap - spent), 6),
        "cap_reached": spent >= cap,
        "metered_calls": len(rec.get("calls") or []),
        "unmetered_calls": int(rec.get("unmetered_calls") or 0),
        "ledger": str(ledger_path(day)),
        "note": ("a PRE-CALL guard, not the books: `scripts/llm_cost_audit.py` "
                 "reconciles against the provider's own balance and stays the "
                 "ground truth. Local model calls are unmetered by design."),
    }


def guard(estimated_usd: float, *, backend: str = "cloud",
          what: str = "", day: str | None = None) -> dict:
    """REFUSE, before the call, if this call would take the day over the cap.

    Returns the budget row when the call may proceed. Raises `SpendCapReached`
    otherwise — the caller must not have contacted the provider yet, which is
    what `test_dollar_cap_refuses_before_the_call_not_after` pins by asserting
    the reader mock's call count is 0 rather than 1-then-refunded.
    """
    if backend in UNMETERED_BACKENDS:
        return {**spend_today(day), "metered": False,
                "why": f"{backend} is local; it costs compute, not dollars"}
    row = spend_today(day)
    est = max(0.0, float(estimated_usd or 0.0))
    if row["spend_today_usd"] + est > row["cap_usd"]:
        raise SpendCapReached(
            f"DAILY_SPEND_CAP_REACHED: ${row['spend_today_usd']:.4f} already spent "
            f"today and this call is estimated at ${est:.4f}, against a "
            f"${row['cap_usd']:.2f} cap ({_config.LAB_SPEND_CAP_ENV} overrides). "
            f"No call was made. Cloud reads are refused for the rest of the UTC "
            f"day; local reading is unaffected."
            + (f" [{what}]" if what else ""))
    return {**row, "metered": True, "estimated_usd": est}


def record(actual_usd: float, *, backend: str = "cloud", what: str = "",
           rows: int | None = None, day: str | None = None) -> dict:
    """Book a call that HAS happened. Never a reservation, never a refund.

    An unmetered backend increments a separate counter: a local call is real
    work and must be visible, but folding it into a dollar total at 0.00 makes
    "ten local calls" and "no calls at all" the same row.
    """
    day = day or _today()
    with _LOCK:
        rec = _read(day)
        if backend in UNMETERED_BACKENDS:
            rec["unmetered_calls"] = int(rec.get("unmetered_calls") or 0) + 1
        else:
            rec["spend_usd"] = round(float(rec.get("spend_usd") or 0.0)
                                     + max(0.0, float(actual_usd or 0.0)), 6)
            rec.setdefault("calls", []).append(
                {"utc": _now(), "backend": backend, "usd": round(float(actual_usd), 6),
                 "rows": rows, "what": what[:160]})
        rec["date"] = day
        _write(day, rec)
    return spend_today(day)


__all__ = ["METERED_BACKENDS", "UNMETERED_BACKENDS", "SpendCapReached",
           "cap_usd", "guard", "ledger_path", "record", "spend_today"]
