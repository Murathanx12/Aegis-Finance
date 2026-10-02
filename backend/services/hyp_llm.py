"""hyp_llm: the ONE budgeted LLM call path for hyp_lab work (generation, LLM-theory arms).

Every call goes through `llm_analyzer.call_named` (language pin, telemetry, served model),
and every hyp_lab-owned call is appended to `hyp_lab/spend.jsonl` with the ledger cost AND
an own estimate at the PEAK list price, so the cap binds even when the ledger prices a served
model at $0 (memory: "an unpriced model makes every dollar cap a lower bound of $0").

The cap is per NIGHT and shared by every process that writes the same spend file: before each
DeepSeek call the file is re-read, so two scripts running side by side cannot each spend the
whole cap. Local calls (`provider="local"`) are logged at $0.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import config as C

HYP_DIR = C.DATA_DIR / "optimus" / "hyp_lab"
SPEND = HYP_DIR / "spend.jsonl"

_lock = threading.Lock()
_cache = {"mtime": None, "size": None, "by_night": {}}


def night_id(now: datetime | None = None) -> str:
    """The evening a night belongs to, on the machine's local clock: 21:00 and 06:00 the next
    morning are the same night; a night ends at 08:00 (local time minus 8 hours), so the 09:30
    scheduled nightly books to its own day and not to the attended night before it."""
    now = now or datetime.now().astimezone()
    return (now - timedelta(hours=8)).date().isoformat()


def own_cost(tokens_in: int | None, tokens_out: int | None) -> float:
    return ((tokens_in or 0) * C.HYP_LAB_PRICE_IN_PER_M + (tokens_out or 0) * C.HYP_LAB_PRICE_OUT_PER_M) / 1e6


def spent(night: str | None = None, path: Path | None = None) -> dict:
    """Sum of this night's hyp_lab spend: max(ledger, own peak estimate) is what the cap reads."""
    path = path or SPEND
    night = night or night_id()
    tot = {"calls": 0, "ledger_usd": 0.0, "own_peak_usd": 0.0}
    if not path.exists():
        return {**tot, "binding_usd": 0.0, "night": night}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("night") != night or r.get("provider") != "deepseek":
                continue
            tot["calls"] += 1
            tot["ledger_usd"] += float(r.get("cost_usd_ledger") or 0.0)
            tot["own_peak_usd"] += float(r.get("cost_usd_own_peak") or 0.0)
    tot["binding_usd"] = max(tot["ledger_usd"], tot["own_peak_usd"])
    tot["night"] = night
    return tot


def _append(row: dict, path: Path | None = None) -> None:
    path = path or SPEND
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")


def call(system: str, user: str, *, purpose: str, arm: str, provider: str = "deepseek",
         max_tokens: int = 300, temperature: float = 0.0, cap_usd: float | None = None,
         night: str | None = None, spend_path: Path | None = None, _call_named=None) -> dict:
    """One budgeted chat turn. Returns call_named's dict plus `cap_state`.

    Refuses (status HYP_CAP_REFUSED, no call made) when this night's binding spend is already
    at or above the cap. `_call_named` is injectable for offline tests."""
    cap = C.HYP_LAB_NIGHT_CAP_USD if cap_usd is None else float(cap_usd)
    night = night or night_id()
    if provider == "deepseek":
        s = spent(night, spend_path)
        if s["binding_usd"] >= cap:
            return {"ok": False, "status": "HYP_CAP_REFUSED", "text": None, "provider": provider,
                    "cap_state": {**s, "cap_usd": cap}}
    if _call_named is None:
        from backend.services import llm_analyzer as LA  # noqa: PLC0415
        _call_named = LA.call_named
    t0 = time.time()
    r = _call_named(provider, system, user, purpose=purpose, max_tokens=max_tokens,
                    temperature=temperature, production_budget=False)
    row = {"night": night, "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "provider": provider, "purpose": purpose, "arm": arm, "ok": bool(r.get("ok")),
           "status": r.get("status"), "served_model": r.get("served_model"), "model": r.get("model"),
           "tokens_in": r.get("tokens_in"), "tokens_out": r.get("tokens_out"),
           "cost_usd_ledger": float(r.get("cost_usd") or 0.0) if provider == "deepseek" else 0.0,
           "cost_usd_own_peak": round(own_cost(r.get("tokens_in"), r.get("tokens_out")), 7)
           if provider == "deepseek" else 0.0,
           "wall_s": round(time.time() - t0, 2)}
    _append(row, spend_path)
    r = dict(r)
    r["cap_state"] = {"cap_usd": cap, "night": night}
    return r


def parse_json(text: str | None) -> dict | list | None:
    """First JSON object (or array) in a reply; fenced code tolerated. None if unparseable."""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if not starts:
        return None
    a = min(starts)
    close = "}" if t[a] == "{" else "]"
    b = t.rfind(close)
    if b <= a:
        return recover_objects(t[a:]) if t[a] == "[" else None
    try:
        return json.loads(t[a:b + 1])
    except json.JSONDecodeError:
        pass
    if t[a] == "[":
        return recover_objects(t[a:])
    return None


def recover_objects(t: str) -> list | None:
    """Complete top-level objects of a TRUNCATED JSON array (a reply cut by max_tokens): every
    object that closed before the cut is kept; the partial last one is dropped."""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    out.append(json.loads(t[start:i + 1]))
                except json.JSONDecodeError:
                    pass
                start = None
    return out or None
