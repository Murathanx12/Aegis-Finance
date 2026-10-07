"""A manager's receipt of model/worker allocation per session — DECLARED, not measured.

WHY THIS EXISTS
================
Claude Code's own Opus / Sonnet / Fable usage has no API this repo can read, and
the session transcripts that would show it live outside the repo entirely
(`docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` §5b: "Weekly strong-
model allowance is a budget"). There is nothing here to MEASURE, so this module
does not pretend to: the orchestrator (Fable, or whoever is driving a session)
LOGS one row per task — the worker it dispatched to, the priority tier that
justified it (§5b's order: 1 capital/execution correctness, 2 data/measurement
correctness, 3 bugs blocking the live loop, 4 high-value research, 5 forward-
paper improvements, 6 core product/UI, 7 nice-to-have), and a one-line EV
(`P(changes the roadmap) x value - cost`, CLAUDE.md rule 5). `close` turns the
rows into a summary a handoff can paste, and a `status` command prints the open
session's table without closing it.

THE ONE MEASURED NUMBER IN THIS RECEIPT
========================================
Paid-API spend (DeepSeek + OpenClaw) IS instrumented — `backend/services/
llm_telemetry.py` ledgers every wire attempt in `backend/data/optimus/
llm_calls*.jsonl`, and `llm_analyzer.llm_usage()` is the live health surface
over the same ledger. `close_session` pulls `llm_telemetry.summary(since=
<session's own date>)` and labels it `MEASURED` with its ledger named, right
beside the `DECLARED` worker/priority rows, so a reader never mistakes one for
the other. This is NOT Claude Code's own Opus/Sonnet/Fable spend — there is no
ledger for that, which is the whole reason this module's rows are declared.

RULES, ENFORCED IN CODE RATHER THAN BY CAPTION
================================================
* Every declared number carries the literal label `DECLARED` on its own row
  AND in the summary and handoff block — a number that is only declared in a
  docstring is a number a future reader treats as measured, which is the
  "absence of a local object is not evidence of absence" failure shape one
  level removed.
* A row with no priority is REFUSED (`ValueError`), never defaulted. CLAUDE.md:
  "a guard that cannot go green is not a check that passed" — a budget receipt
  that silently accepts "priority unknown" rows is the same shape as
  `monday_gate_check` reporting 0/9 forever because no book carried the key it
  read.
* `tokens` and `usd` are OPTIONAL and NEVER GUESSED. A row that omits them
  stays blank (`null`), never `0` — a fabricated zero reads as "this task cost
  nothing", the same failure `llm_telemetry.price_call` refuses by returning
  `None` rather than inventing a cost for an unpriced model.
* Append-only while a session is open; `log` refuses once `close` has run.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from backend.config import OPTIMUS_LEDGER_DIR

SESSION_DIR = Path(OPTIMUS_LEDGER_DIR) / "session_budget"

#: The worker roster from §5b's operating-model reset: Fable orchestrates,
#: Opus does financial/execution/architecture-moving work and adversarial
#: review, Sonnet does research/docs/low-risk plumbing, DeepSeek/local do bulk
#: extraction, "deterministic" is a test/script with no model in the loop.
WORKERS: tuple[str, ...] = ("fable", "opus", "sonnet", "deepseek", "local", "deterministic")

#: §5b's priority order, 1 = highest. A row outside this range is refused, not
#: clamped — clamping a typo'd "17" to 7 would silently misfile a capital-
#: correctness task as nice-to-have.
PRIORITIES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)

#: The literal labels every row/summary line carries. Not a style choice: a
#: reader scanning for the word is how "declared" and "measured" stay
#: distinguishable once this file is six months old and nobody remembers which
#: module wrote which number.
DECLARED = "DECLARED"
MEASURED = "MEASURED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_id(session_id: str) -> str:
    s = "".join(c for c in str(session_id) if c.isalnum() or c in "-_.")
    return s or "session"


def session_path(session_id: str, base: Optional[Path] = None) -> Path:
    d = Path(base) if base is not None else SESSION_DIR
    return d / f"{_safe_id(session_id)}.json"


def _read(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, sort_keys=False, default=str),
                   encoding="utf-8")
    tmp.replace(path)


# ============================================================ open / log / close

def open_session(session_id: str, *, date_: Optional[str] = None,
                 base: Optional[Path] = None, now: Optional[str] = None) -> dict:
    """Create `<session_id>.json`. Refuses (returns an error dict, raises nothing)
    if a file already exists for this id — `open` creates, it never reopens or
    overwrites a session someone else is logging to."""
    p = session_path(session_id, base)
    existing = _read(p)
    if existing is not None:
        return {"error": f"session {session_id!r} already exists at {p}",
                "path": str(p), "closed_utc": existing.get("closed_utc")}
    doc = {
        "session_id": str(session_id),
        "date": date_ or (now or _now())[:10],
        "opened_utc": now or _now(),
        "closed_utc": None,
        "rows": [],
        "summary": None,
    }
    _write(p, doc)
    return doc


def log_row(session_id: str, *, task: str, worker: str, priority: Optional[int],
           ev: str, tokens: Optional[int] = None, usd: Optional[float] = None,
           note: Optional[str] = None, base: Optional[Path] = None,
           now: Optional[str] = None) -> dict:
    """Append one declared row to an open session.

    Raises `ValueError` — never returns a half-written row — when: the session
    was never opened; it is already closed; `priority` is missing or outside
    1-7; `worker` is not in `WORKERS`; `task` or `ev` is blank. All four are the
    same rule: a row this module cannot classify is refused, not logged with a
    hole in it.
    """
    p = session_path(session_id, base)
    doc = _read(p)
    if doc is None:
        raise ValueError(f"session {session_id!r} was never opened — run "
                         f"`open --session {session_id}` first")
    if doc.get("closed_utc"):
        raise ValueError(f"session {session_id!r} is closed (at "
                         f"{doc['closed_utc']}); open a new session id")
    if priority is None:
        raise ValueError("a row without a priority is refused — pass "
                         f"--priority, one of {PRIORITIES}")
    try:
        priority = int(priority)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"priority must be an int in {PRIORITIES}, "
                         f"got {priority!r}") from exc
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}, got {priority}")
    worker_norm = str(worker or "").strip().lower()
    if worker_norm not in WORKERS:
        raise ValueError(f"worker must be one of {WORKERS}, got {worker!r}")
    if not str(task or "").strip():
        raise ValueError("a row without a task name is refused")
    if not str(ev or "").strip():
        raise ValueError("a row without an EV line is refused")
    row = {
        "ts": now or _now(),
        "task": str(task).strip(),
        "worker": worker_norm,
        "priority": priority,
        "ev": str(ev).strip(),
        "tokens": int(tokens) if tokens is not None else None,
        "tokens_label": DECLARED if tokens is not None else None,
        "usd": round(float(usd), 6) if usd is not None else None,
        "usd_label": DECLARED if usd is not None else None,
        "note": str(note).strip() if note else None,
    }
    doc["rows"].append(row)
    _write(p, doc)
    return row


def _by_count(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        k = str(r.get(key))
        out[k] = out.get(k, 0) + 1
    return out


def opus_share(rows: list[dict]) -> Optional[float]:
    """PURE. `n(worker == "opus") / n(rows)`, rounded to 4dp.

    `None` for an empty session — a 0/0 share is UNKNOWN, not zero, the same
    reading `llm_telemetry.spend` gives an empty ledger rather than fabricating
    a rate out of no rows.
    """
    if not rows:
        return None
    opus = sum(1 for r in rows if r.get("worker") == "opus")
    return round(opus / len(rows), 4)


def _paid_api_spend(date_from: str) -> dict:
    """The ONE measured number in this receipt: DeepSeek + OpenClaw spend since
    the session's own date, read from `llm_telemetry`'s ledger.

    Never degrades to a silent zero. An import failure or a read error is
    reported as `available: False` with the reason, which is the same rule
    `llm_telemetry.spend` follows by returning `{}` rather than a populated
    dict of zeros on a broken ledger.
    """
    try:
        from backend.services import llm_telemetry
    except Exception as exc:                                        # noqa: BLE001
        return {"label": MEASURED, "available": False,
                "reason": f"{type(exc).__name__}: {exc}"}
    try:
        s = llm_telemetry.summary(since=date_from)
    except Exception as exc:                                        # noqa: BLE001
        return {"label": MEASURED, "available": False,
                "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "label": MEASURED,
        "available": True,
        "ledger": "backend/data/optimus/llm_calls*.jsonl (llm_telemetry.summary)",
        "since": date_from,
        "total_cost_usd": s.get("total_cost_usd"),
        "total_is_lower_bound": s.get("total_is_lower_bound"),
        "cost_is_estimate": s.get("cost_is_estimate", True),
        "n_calls": s.get("n_calls"),
        "n_unpriced_calls": s.get("n_unpriced_calls"),
        "note": ("DeepSeek + OpenClaw calls recorded in THIS process's "
                "telemetry ledger from the session's open date through the "
                "moment `close` ran. It is NOT Claude Code's own Opus/Sonnet/"
                "Fable usage -- there is no ledger for that, which is why "
                "every row above this line is DECLARED rather than measured"),
    }


def build_handoff_block(doc: dict) -> str:
    """The markdown snippet `close_session` writes into `summary.handoff_block`,
    meant to be pasted verbatim into the next handoff doc."""
    rows = doc.get("rows", [])
    s = doc.get("summary") or {}
    by_worker = s.get("by_worker") or _by_count(rows, "worker")
    by_priority = s.get("by_priority") or _by_count(rows, "priority")
    share = s.get("opus_share_of_rows", opus_share(rows))
    spend = s.get("paid_api_spend") or _paid_api_spend(doc.get("date", ""))
    lines = [
        f"### Session budget -- {doc['session_id']} ({doc.get('date')}) "
        f"[worker mix is {DECLARED}; paid-API spend is {MEASURED}]",
        "",
        f"- rows: {len(rows)} | opus share of rows: "
        f"{share if share is not None else 'n/a'} ({DECLARED})",
        "- by worker (" + DECLARED + "): "
        + (", ".join(f"{k}={v}" for k, v in sorted(by_worker.items())) or "none"),
        "- by priority (" + DECLARED + "): "
        + (", ".join(f"p{k}={v}" for k, v in
                     sorted(by_priority.items(), key=lambda kv: kv[0])) or "none"),
    ]
    if spend.get("available"):
        lb = " (lower bound)" if spend.get("total_is_lower_bound") else ""
        lines.append(
            f"- paid-API spend since {spend.get('since')} ({MEASURED}, "
            f"{spend.get('ledger')}): ${spend.get('total_cost_usd')}{lb} "
            f"over {spend.get('n_calls')} call(s)")
    else:
        lines.append(f"- paid-API spend ({MEASURED}): UNAVAILABLE -- "
                     f"{spend.get('reason')}")
    return "\n".join(lines)


def close_session(session_id: str, *, base: Optional[Path] = None,
                  now: Optional[str] = None) -> dict:
    """Write the summary and return the full document.

    Idempotent: closing an already-closed session returns the same document
    unchanged rather than re-deriving a summary against a spend window that has
    since moved on -- a second `close` must not silently change a number a
    handoff already quoted.
    """
    p = session_path(session_id, base)
    doc = _read(p)
    if doc is None:
        raise ValueError(f"session {session_id!r} was never opened")
    if doc.get("closed_utc"):
        return doc
    rows = doc.get("rows", [])
    summary: dict[str, Any] = {
        "n_rows": len(rows),
        "by_worker": _by_count(rows, "worker"),
        "by_worker_label": DECLARED,
        "by_priority": _by_count(rows, "priority"),
        "by_priority_label": DECLARED,
        "opus_share_of_rows": opus_share(rows),
        "opus_share_label": DECLARED,
        "paid_api_spend": _paid_api_spend(doc.get("date", "")),
    }
    doc["closed_utc"] = now or _now()
    doc["summary"] = summary
    doc["summary"]["handoff_block"] = build_handoff_block(doc)
    _write(p, doc)
    return doc


def find_open_session(base: Optional[Path] = None) -> Optional[dict]:
    """The most recently opened session with no `closed_utc`, or `None`."""
    d = Path(base) if base is not None else SESSION_DIR
    if not d.exists():
        return None
    best: Optional[dict] = None
    for f in sorted(d.glob("*.json")):
        if f.name.endswith(".tmp"):
            continue
        doc = _read(f)
        if doc and not doc.get("closed_utc"):
            if best is None or str(doc.get("opened_utc", "")) > str(best.get("opened_utc", "")):
                best = doc
    return best


def render_table(doc: dict) -> str:
    """A plain-text table for `status` -- never json.dumps, so it reads on a
    terminal without piping through a formatter."""
    rows = doc.get("rows", [])
    header = (f"session {doc.get('session_id')} ({doc.get('date')}) -- opened "
             f"{doc.get('opened_utc')}"
             + (f", CLOSED {doc['closed_utc']}" if doc.get("closed_utc") else " [OPEN]"))
    lines = [header,
            f"{'task':<42}{'worker':<14}{'pri':<4}{'tokens':<9}{'usd':<9}ev"]
    for r in rows:
        tok = "-" if r.get("tokens") is None else str(r["tokens"])
        usd = "-" if r.get("usd") is None else str(r["usd"])
        lines.append(f"{str(r.get('task'))[:40]:<42}{str(r.get('worker')):<14}"
                     f"{str(r.get('priority')):<4}{tok:<9}{usd:<9}{r.get('ev')}")
    share = opus_share(rows)
    lines.append(f"-- {len(rows)} row(s); opus share of rows: "
                 f"{share if share is not None else 'n/a'} ({DECLARED})")
    return "\n".join(lines)


# ==================================================================== CLI

def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="session_budget")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_open = sub.add_parser("open", help="create a session's budget receipt")
    p_open.add_argument("--session", required=True)
    p_open.add_argument("--date", default=None)

    p_log = sub.add_parser("log", help="append one DECLARED row")
    p_log.add_argument("--session", required=True)
    p_log.add_argument("--task", required=True)
    p_log.add_argument("--worker", required=True, choices=WORKERS)
    p_log.add_argument("--priority", required=True, type=int, choices=PRIORITIES)
    p_log.add_argument("--ev", required=True)
    p_log.add_argument("--tokens", type=int, default=None)
    p_log.add_argument("--usd", type=float, default=None)
    p_log.add_argument("--note", default=None)

    p_close = sub.add_parser("close", help="write the summary + handoff block")
    p_close.add_argument("--session", required=True)

    p_status = sub.add_parser("status", help="print the open session's table")
    p_status.add_argument("--session", default=None,
                          help="omit to find the most recently opened session")

    a = ap.parse_args(argv)

    if a.cmd == "open":
        doc = open_session(a.session, date_=a.date)
        print(json.dumps(doc, indent=2, default=str))
        return 1 if "error" in doc else 0

    if a.cmd == "log":
        try:
            row = log_row(a.session, task=a.task, worker=a.worker,
                          priority=a.priority, ev=a.ev, tokens=a.tokens,
                          usd=a.usd, note=a.note)
        except ValueError as exc:
            print(f"REFUSED: {exc}")
            return 2
        print(json.dumps(row, indent=2, default=str))
        return 0

    if a.cmd == "close":
        try:
            doc = close_session(a.session)
        except ValueError as exc:
            print(f"REFUSED: {exc}")
            return 2
        print(json.dumps(doc["summary"], indent=2, default=str))
        return 0

    if a.cmd == "status":
        doc = _read(session_path(a.session)) if a.session else find_open_session()
        if doc is None:
            print("no open session" + (f" named {a.session!r}" if a.session else "")
                 + " (session_budget status)")
            return 1
        print(render_table(doc))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
