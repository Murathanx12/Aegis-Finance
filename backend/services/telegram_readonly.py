"""The Telegram agent's READ-ONLY command table (CH-05 R7, 2026-11-11).

THE OWNER'S ASK
===============
Telegram as a two-way channel to the system is "very important". On 2026-11-11 the running
agent answered nothing: the runtime checkout had wired every plain-text message into a Codex
bridge that refused (15,961 "codex conversation held (Refused)" log lines since 11-08), and
the Codex bridge is dropped (OD-a). Main's own table, read with a mocked transport the same
day, does answer -- but an unmatched message costs one DeepSeek classifier call, `/sim start`
calls `sim_session.start`, `/deep` and `/research` become paid calls on an `/approve` tap,
and plain "status" makes a live broker GET.

So the default table is this one: a few commands, each a READ of a receipt that already
exists, each reply carrying the receipt's own age compared with a limit. Nothing here places
or cancels an order, starts or stops a simulation or a scheduled task, calls a model, runs a
subprocess, or writes anything (the bridge itself still logs inbox/outbox rows). The full
table stays in `scripts/telegram_agent.py` behind `config.TELEGRAM_AGENT_MODE = "full"`, an
owner decision.

Every handler returns `{"text", "markdown": False}` and never raises: a receipt that cannot
be read is a CANNOT DETERMINE line, never silence and never "ok".
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend import config as _cfg

CANNOT = "CANNOT DETERMINE"
_SEV = {"DOWN": 0, "DEGRADED": 1, "UNKNOWN": 2}


def _root(root: Optional[Path]) -> Path:
    return Path(root or _cfg.OPTIMUS_LEDGER_DIR)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(p: Path) -> Any:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _parse_ts(v: Any) -> Optional[datetime]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        if re.fullmatch(r"\d{8}T\d{6}Z", s):
            return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def age_line(stamp: Any, limit_h: float, source: str, *, now: Optional[datetime] = None) -> str:
    """The receipt's OWN stamp compared with a limit. Missing, unreadable or future = not fresh."""
    now = now or _now()
    t = _parse_ts(stamp)
    if t is None:
        return f"(receipt {source}: no readable stamp -- treat as STALE)"
    h = (now - t).total_seconds() / 3600.0
    if h < -0.1:
        return f"(receipt {source}: stamped {t:%Y-%m-%d %H:%M} UTC, in the FUTURE -- treat as STALE)"
    flag = f" -- STALE (limit {limit_h:g} h)" if h > limit_h else ""
    return f"(receipt {source}: {t:%Y-%m-%d %H:%M} UTC, {h:.1f} h old{flag})"


def _reply(text: str) -> dict:
    return {"text": text, "markdown": False}


# ───────────────────────────────────────────────────────────── commands

def status_text(root: Optional[Path] = None, *, now: Optional[datetime] = None, limit: int = 8) -> str:
    """The systems dashboard's receipt (`scripts.system_status`): counts and the worst rows."""
    p = _root(root) / "system_status" / "status.json"
    rec = _read_json(p)
    if not isinstance(rec, dict) or rec.get("receipt") != "system_status/1":
        return (f"Status -- {CANNOT}: no readable system_status/status.json. "
                "On the PC: python -m scripts.system_status --html")
    c = rec.get("counts") or {}
    head = (f"Status: {c.get('OK', '?')} OK, {c.get('DEGRADED', '?')} degraded, "
            f"{c.get('DOWN', '?')} down, {c.get('UNKNOWN', '?')} unknown")
    rows = [r for s in (rec.get("sections") or {}).values() if isinstance(s, dict)
            for r in (s.get("rows") or []) if isinstance(r, dict)
            and r.get("status") != "OK" and not r.get("one_shot")]
    rows.sort(key=lambda r: (_SEV.get(str(r.get("status")), 2), str(r.get("section")), str(r.get("name"))))
    out = [head]
    for r in rows[:limit]:
        out.append(f"{r.get('status')} {r.get('section')}/{r.get('name')}: {str(r.get('detail') or '')[:110]}")
    if len(rows) > limit:
        out.append(f"... {len(rows) - limit} more not OK")
    if rec.get("undetermined"):
        out.append(f"could not determine: {len(rec['undetermined'])} item(s)")
    out.append(age_line(rec.get("generated_utc"), float(_cfg.TELEGRAM_READONLY_STATUS_STALE_H),
                        "system_status/status.json", now=now))
    return "\n".join(out)


def budget_text(root: Optional[Path] = None, *, now: Optional[datetime] = None,
                line_fn: Optional[Callable[[], str]] = None) -> str:
    """The DeepSeek envelope's own one-line view (`provider_budget.status_line`, a read that
    takes no lock and writes nothing)."""
    try:
        if line_fn is None:
            from backend.services import provider_budget as PB
            line_fn = PB.status_line
        line = str(line_fn())
    except Exception as exc:                                     # noqa: BLE001
        line = f"DeepSeek budget -- {CANNOT} ({type(exc).__name__})"
    cap = getattr(_cfg, "DEEPSEEK_MONTHLY_CAP_USD", None)
    return line + (f"\nmonthly cap in config: ${float(cap):.2f}" if cap is not None else "")


def digest_text(root: Optional[Path] = None, *, now: Optional[datetime] = None) -> str:
    """The newest world digest, stamped (the cockpit's reader; files only)."""
    from backend.services import telegram_cockpit as CK
    return CK.stamped(CK.digest_answer(root), now=now)


def _plain(text: str) -> str:
    """The model_routing readers write Markdown; these replies go out as plain text."""
    return "\n".join(ln.replace("*", "").replace("`", "").strip("_") for ln in str(text).splitlines())


def books_text(root: Optional[Path] = None, *, now: Optional[datetime] = None) -> str:
    from backend.services import model_routing as MR
    return _plain(MR.books_text(root))


def nav_text(root: Optional[Path] = None, *, now: Optional[datetime] = None) -> str:
    from backend.services import model_routing as MR
    return _plain(MR.nav_text(root))


def positions_text(root: Optional[Path] = None, *, now: Optional[datetime] = None) -> str:
    """Paper accounts from the newest fleet-manager run receipt (no broker call)."""
    runs = _root(root) / "paper_accounts" / "fleet_manager" / "runs"
    files = sorted(runs.glob("run_*.json"), key=lambda p: p.name) if runs.is_dir() else []
    rec = _read_json(files[-1]) if files else None
    if not isinstance(rec, dict) or not isinstance(rec.get("accounts"), list):
        return (f"Positions -- {CANNOT}: no readable paper_accounts/fleet_manager/runs/run_*.json "
                "(the fleet manager pass writes it).")
    out = [f"Paper accounts, fleet-manager pass {rec.get('pass')} (receipt, not the broker)"]
    for a in rec["accounts"]:
        if not isinstance(a, dict):
            continue
        stops = {s.get("symbol") for s in (a.get("stop_table") or []) if isinstance(s, dict) and s.get("resting")}
        pos = [p for p in (a.get("positions") or []) if isinstance(p, dict)]
        unprotected = [p.get("symbol") for p in pos if p.get("symbol") not in stops]
        try:
            eq = f"${float(a.get('equity')):,.0f}"
        except (TypeError, ValueError):
            eq = f"equity {CANNOT}"
        syms = ", ".join(str(p.get("symbol")) for p in pos[:8]) + (" ..." if len(pos) > 8 else "")
        line = f"{a.get('role')}: {eq}, {a.get('n_positions', len(pos))} position(s), status {a.get('status')}"
        if syms:
            line += f" [{syms}]"
        if unprotected:
            line += f" UNPROTECTED {unprotected[:6]}"
        out.append(line)
    out.append(age_line(rec.get("finished_utc") or rec.get("started_utc"),
                        float(_cfg.TELEGRAM_READONLY_POSITIONS_STALE_H),
                        f"fleet_manager/runs/{files[-1].name}", now=now))
    return "\n".join(out)


#: name -> (reader, one-line help). The ONLY things this table can do.
COMMANDS: dict[str, tuple[Callable[..., str], str]] = {
    "status": (status_text, "the systems dashboard: counts and what is not OK"),
    "budget": (budget_text, "DeepSeek spend this month vs the cap"),
    "digest": (digest_text, "the newest world news digest"),
    "books": (books_text, "the LLM-portfolio books leaderboard"),
    "nav": (nav_text, "every paper account vs SPY (ROI receipt)"),
    "positions": (positions_text, "paper positions and stops (fleet-manager receipt)"),
}
ALIASES = {"start": "help", "menu": "help", "commands": "help", "?": "help", "health": "status",
           "system": "status", "spend": "budget", "news": "digest", "fleet": "positions"}


def help_text() -> str:
    lines = ["AEGIS (read-only). Send one word, with or without /:"]
    lines += [f"/{k} -- {v[1]}" for k, v in COMMANDS.items()]
    lines += ["/help -- this list", "",
              "Every answer is read from a receipt on disk and shows its age. This bot never places "
              "or cancels an order, starts or stops anything, calls a model or runs a command."]
    return "\n".join(lines)


def command_of(text: str) -> str:
    first = str(text or "").strip().split(" ", 1)[0] if str(text or "").strip() else ""
    name = first.lstrip("/").split("@")[0].lower()
    return ALIASES.get(name, name)


def answer(text: str, *, root: Optional[Path] = None, now: Optional[datetime] = None) -> dict:
    """The reply to one owner message. Never raises."""
    name = command_of(text)
    if name == "help":
        return _reply(help_text())
    entry = COMMANDS.get(name)
    if entry is None:
        shown = re.sub(r"[^\w/@.-]", "", str(text or "").strip().split(" ", 1)[0])[:32] or "(empty)"
        return _reply(f"Not supported: {shown}\n\n{help_text()}")
    try:
        return _reply(entry[0](root, now=now))
    except Exception as exc:                                     # noqa: BLE001
        return _reply(f"/{name} -- {CANNOT} ({type(exc).__name__})")


def text_reply(text: str, msg: dict) -> dict:
    """For `telegram_bridge.poll(text_handler=...)`: every plain text and every unknown /cmd."""
    return answer(text)


def callback_reply(data: str, cq: dict) -> dict:
    return _reply("Buttons are not used in read-only mode. Send /help.")


def _handler(name: str) -> Callable[[list, dict], dict]:
    def h(args: list, msg: dict) -> dict:
        return answer(name)
    h.__name__ = f"readonly_{name}"
    return h


#: For `telegram_bridge.poll(handlers=...)`.
HANDLERS: dict[str, Callable[[list, dict], dict]] = {
    **{name: _handler(name) for name in (*COMMANDS, "help")},
    **{alias: _handler(alias) for alias in ALIASES},
}

__all__ = ["COMMANDS", "ALIASES", "HANDLERS", "answer", "text_reply", "callback_reply",
           "help_text", "command_of", "status_text", "budget_text", "digest_text", "books_text",
           "nav_text", "positions_text", "age_line"]
