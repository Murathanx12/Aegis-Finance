"""Aegis's Telegram operator — the brief, the remote control, the approval tap.

    python -m scripts.telegram_agent --serve         # long-poll, run commands
    python -m scripts.telegram_agent --brief         # send the daily brief, exit
    python -m scripts.telegram_agent --claim         # capture the owner chat id
    python -m scripts.telegram_agent --daily         # the daily digest jobs, exit

WHAT THIS IS FOR (Murat, 2026-09-22)
====================================
    "can it be a remote control or anything else. like aegis sending dailiy
     briefing, how much it made and lost, news, importatn things, stock
     forecasts and updates"

Four jobs, in ascending order of how much they are worth:

1. **The brief.** Money first, from the BROKER, then the ranked book and what
   changed. The morning report already computes this; the phone just gets its
   first page.
2. **Remote control.** `/sim start 8`, `/sim stop`, `/sim status`. The PC is the
   trading node and he is not always sitting at it. A stop from the phone is the
   same SAFE stop as the button: finish the cycle, checkpoint, exit.
3. **The approval tap.** This programme has attended gates -- seeding a lane,
   a spend above a cap, promoting a candidate to CAPITAL_CANDIDATE -- and they
   currently stall until he is at a keyboard. `/pending`, `/approve <id>`,
   `/deny <id>` move the LATENCY without moving the GATE: the request still
   carries what it wants, the evidence and the worst case in dollars, and an
   unanswered request stays unapproved.
4. **Alarms worth interrupting for**, and only those: an ownership conflict on a
   broker account, a drawdown breach, a night that died without a receipt.

WHAT IT WILL NOT DO
===================
It never places an order, never approves anything itself, and never sends to a
chat that is not the configured owner. Commands are a FIXED dict -- there is no
"run this shell command" verb and adding one would make a chat message a remote
shell on a machine holding brokerage credentials.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                         # noqa: E402,F401
from backend.services import telegram_bridge as TG         # noqa: E402
from backend.services import sim_session as SS             # noqa: E402

logger = logging.getLogger("telegram_agent")

HELP = """*AEGIS remote*

*Money* (from receipts -- no model)
`/nav` every paper account vs SPY
`/books` the LLM-portfolio leaderboard
`/forecasts` today's forecast pass
`/broker` live broker equity, cash, positions
`/book` the ranked next-month names
`/brief` the full daily brief

*Models* (each reply names provider, cost, latency)
`/ask <q>` local model, started on demand
`/research <ticker>` evidence from disk, no model (`--quest` runs the card first)
`/deep <q>` DeepSeek · add `--nvidia` for NVIDIA
`/compare [ticker]` the extraction bake-off table (read-only)

*Simulation*
`/sim status` what is running and how far in
`/sim start 8` start a session (6, 8, 10 or 12 hours)
`/sim smoke 30` a 30-minute rehearsal
`/sim stop` SAFE stop: finish the cycle, checkpoint, exit
`/sim resume` continue from the last checkpoint

*Decisions*
`/pending` approvals waiting on you
`/approve <id>` · `/deny <id>`

*System*
`/status` sim + model server (receipts)
`/system` broker, sim, model server, ranker
`/help` this

_This bot answers only this chat. It never places an order and never approves
anything on its own._"""


def _fmt_money(x) -> str:
    try:
        return f"${float(x):,.2f}"
    except (TypeError, ValueError):
        return "CANNOT DETERMINE"


# ───────────────────────────────── commands ─────────────────────────────────

def cmd_help(args, msg) -> str:
    return HELP


def cmd_nav(args, msg) -> str:
    from backend.services import pc_broker as PB
    try:
        a = PB.account()
    except PB.BrokerError as exc:
        return f"*NAV* — CANNOT DETERMINE\n`{str(exc)[:300]}`"
    eq, le = float(a["equity"]), float(a.get("last_equity") or 0)
    day = (eq / le - 1) * 100 if le else None
    pos = PB.positions()
    lines = [f"*NAV* `{a['account_number']}`",
             f"equity *{_fmt_money(eq)}*",
             f"cash {_fmt_money(a['cash'])} · {len(pos)} position(s)"]
    if day is not None:
        lines.append(f"since last close *{day:+.2f}%*")
    if pos:
        best = max(pos, key=lambda p: float(p["unrealized_pl"]))
        worst = min(pos, key=lambda p: float(p["unrealized_pl"]))
        lines.append(f"best {best['symbol']} {_fmt_money(best['unrealized_pl'])} "
                     f"({float(best['unrealized_plpc'])*100:+.1f}%)")
        lines.append(f"worst {worst['symbol']} {_fmt_money(worst['unrealized_pl'])} "
                     f"({float(worst['unrealized_plpc'])*100:+.1f}%)")
    return "\n".join(lines)


def _latest_ranking() -> dict | None:
    base = _cfg.OPTIMUS_LEDGER_DIR / "pc_book"
    files = sorted(base.glob("*/ranking.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def cmd_book(args, msg) -> str:
    r = _latest_ranking()
    if not r:
        return ("*Book* — CANNOT DETERMINE: no ranking on disk yet. "
                "Start a simulation (`/sim start 8`) or run the live loop.")
    top = (r.get("top") or [])[:12]
    v = r.get("verdict") or {}
    head = [f"*Ranked book* — {r.get('asof')}",
            f"{r.get('n_eligible', 0):,} eligible names"]
    if v:
        head.append(f"_{v.get('verdict')}_")
    elif r.get("top20_net_rel_21d") is not None:
        head.append(f"top-20 OOS net {r['top20_net_rel_21d']*100:+.2f}%/21d")
    rows = []
    for x in top:
        er = x.get("expected_relative_return_21d_net")
        rows.append(f"`{x.get('rank'):>3}` *{x.get('symbol')}*  "
                    + ("unmeasured" if er is None else f"{er*100:+.2f}%"))
    tail = ["", "_expected return is the REALISED out-of-sample mean of that "
                "score decile, never a model output._"]
    return "\n".join(head + [""] + rows + tail)


def cmd_brief(args, msg) -> str:
    """Money first, then the book, then what is broken. The phone's front page."""
    parts = [f"*AEGIS brief* {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    parts.append(cmd_nav(args, msg))
    parts += ["", cmd_book(args, msg)]
    st = SS.status()
    parts += ["", f"*Simulation* {st['state']}"
                  + (f" · cycle {st['cycle']}" if st.get("cycle") else "")]
    if st.get("remaining_s"):
        parts.append(f"{st['remaining_s']//3600}h {(st['remaining_s']%3600)//60}m left")
    pend = TG.pending_approvals()
    if pend:
        parts += ["", f"*{len(pend)} approval(s) waiting* — /pending"]
    return "\n".join(parts)


def cmd_sim(args, msg) -> str:
    sub = (args[0].lower() if args else "status")
    if sub == "status":
        st = SS.status()
        out = [f"*Simulation* {st['state']}"]
        s = st.get("session") or {}
        if s:
            out.append(f"id `{s.get('id')}` · {s.get('kind')} · mode {s.get('mode')}")
            out.append(f"cycle {st.get('cycle')} · resumes {st.get('resumable')}")
            if st.get("remaining_s") is not None:
                out.append(f"{st['remaining_s']//3600}h {(st['remaining_s']%3600)//60}m left")
            if st.get("heartbeat_age_s") is not None:
                out.append(f"heartbeat {st['heartbeat_age_s']:.0f}s ago")
            if s.get("unclean_reason"):
                out.append(f"⚠️ {s['unclean_reason']}")
        else:
            out.append("_nothing has run yet_")
        return "\n".join(out)

    if sub in ("start", "smoke", "resume"):
        try:
            if sub == "resume":
                s = SS.start(hours=SS.ALLOWED_HOURS[0], resume=True)
            elif sub == "smoke":
                mins = float(args[1]) if len(args) > 1 else 30
                s = SS.start(minutes=mins)
            else:
                hrs = float(args[1]) if len(args) > 1 else 8
                s = SS.start(hours=hrs)
        except SS.SimRefused as exc:
            return f"*REFUSED*\n`{str(exc)[:500]}`"
        return (f"*Simulation started* `{s['id']}`\n"
                f"{s['kind']} · mode {s['mode']} · pid {s['pid']}\n"
                f"ends {s['planned_end']}\n\n"
                f"_`/sim stop` finishes the current cycle, checkpoints and exits._")

    if sub == "stop":
        r = SS.request_stop(reason="telegram")
        return (f"*Stop requested* — {r.get('detail')}" if r.get("ok")
                else f"Nothing to stop: {r.get('detail')}")

    return f"Unknown `/sim {sub}`. Try status, start, smoke, stop, resume."


def cmd_pending(args, msg) -> str:
    rows = TG.pending_approvals()
    if not rows:
        return "No approvals waiting."
    out = [f"*{len(rows)} approval(s) waiting*", ""]
    for r in rows:
        out += [f"`{r['id']}` — {r['what']}",
                f"  why: {r['why']}", f"  worst case: {r['worst_case']}", ""]
    out.append("_`/approve <id>` or `/deny <id>`. Unanswered means NOT approved._")
    return "\n".join(out)


def cmd_approve(args, msg) -> str:
    if not args:
        return "Usage: `/approve <id>` — see /pending"
    r = TG.resolve_approval(args[0], approved=True)
    return (f"*APPROVED* `{args[0]}` — {r.get('what')}" if r.get("ok")
            else f"Cannot approve: {r.get('why')}")


def cmd_deny(args, msg) -> str:
    if not args:
        return "Usage: `/deny <id>` — see /pending"
    r = TG.resolve_approval(args[0], approved=False)
    return (f"*DENIED* `{args[0]}` — {r.get('what')}" if r.get("ok")
            else f"Cannot deny: {r.get('why')}")


def cmd_status(args, msg) -> str:
    out = ["*System*"]
    from backend.services import pc_broker as PB
    try:
        a = PB.account()
        out.append(f"broker `{a['account_number']}` {a['status']} · {_fmt_money(a['equity'])}")
    except Exception as exc:                                       # noqa: BLE001
        out.append(f"broker ✗ `{str(exc)[:120]}`")
    st = SS.status()
    out.append(f"sim {st['state']}" + (f" · cycle {st['cycle']}" if st.get("cycle") else ""))
    try:
        from backend.services import llama_server as LS
        s = LS.status()
        out.append(f"model server listening={s.get('listening')} ready={s.get('ready')}")
    except Exception as exc:                                       # noqa: BLE001
        out.append(f"model server ? `{str(exc)[:80]}`")
    r = _latest_ranking()
    out.append(f"ranking {r.get('asof')} · {r.get('n_eligible', 0):,} names" if r
               else "ranking — none on disk")
    return "\n".join(out)


def _routed(cmd: str):
    """A handler that goes through `model_routing.route` -- the table the
    tests pin (chunk G, 2026-09-26). Money/state commands read receipts and
    make no model call; model commands name provider, cost and latency."""
    def _h(args, msg) -> str:
        from backend.services import model_routing as MR
        return MR.route(cmd, list(args))
    _h.__name__ = f"routed_{cmd}"
    return _h


HANDLERS = {
    "help": cmd_help, "start": cmd_help,
    "broker": cmd_nav, "book": cmd_book, "brief": cmd_brief,
    "sim": cmd_sim, "system": cmd_status,
    "pending": cmd_pending, "approve": cmd_approve, "deny": cmd_deny,
    **{c: _routed(c) for c in ("nav", "status", "books", "forecasts",
                               "ask", "research", "deep", "compare")},
}


_DAILY_DONE: dict[str, str] = {}


def daily_jobs(*, today=None) -> list[str]:
    """The digest's once-per-UTC-day jobs, one receipt line each.

    G-fix (adjudication row 7): nothing called `source_reads --grade-promises`,
    so MU's 2026-09-30 promises would never have been graded. The grader runs
    here once per UTC day from MODEL_ROUTING_GRADE_PROMISES_FROM on; its own
    stamp file (`model_routing/grade_promises_daily.jsonl`) keeps it to one run
    however often the serve loop or `--brief` fires.
    """
    from backend.services import model_routing as MR
    day = str(today or datetime.now(timezone.utc).date())
    if _DAILY_DONE.get("grade_promises") == day:
        return []
    r = MR.grade_promises_daily(today=today)
    if r.get("action") == "ran" or r.get("reason") == "already ran today":
        _DAILY_DONE["grade_promises"] = day
    if r.get("action") != "ran":
        return []
    return [f"_promises graded ({r.get('day')}): {r.get('state')} in {r.get('elapsed_s')}s_"
            + (f" `{TG.redact(r.get('error'))}`" if r.get("error") else "")]


# ===========================================================================
# LIVENESS — a heartbeat, a lock, and a supervisor (review 2026-09-26 §5 item 3)
#
# The agent died at 2026-09-23 01:07Z with no exit record, no supervisor and
# `agent.pid` holding a BOM and a dead pid, while `stack_health` reported the
# bot TOKEN as READY for days. Liveness is now the agent's OWN evidence: a
# timestamped log line on start, and a heartbeat row every loop. The
# supervisor (`--supervise`, run by the `AegisTelegramAgent` scheduled task at
# logon) restarts `--serve` when it exits OR when its heartbeat goes stale,
# killing only the child it started, by its own handle.
# ===========================================================================

TG_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "telegram"
HEARTBEAT = TG_DIR / "heartbeat.json"
AGENT_LOG = TG_DIR / "agent.log"
SUPERVISOR_LOG = TG_DIR / "supervisor.jsonl"
STOP_FILE = TG_DIR / "STOP"
LOCK = Path(_cfg.OPTIMUS_LEDGER_DIR) / "telegram_agent_lock.json"
TASK_NAME = "AegisTelegramAgent"
#: Supervisor restart backoff: first retry after MIN, doubling to MAX; a child
#: that lived longer than HEALTHY_S resets it.
BACKOFF_MIN_S, BACKOFF_MAX_S, HEALTHY_S = 5.0, 300.0, 600.0


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, obj: dict) -> None:
    """Atomic, UTF-8 WITHOUT a BOM (F17: `agent.pid` began with EF BB BF)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def setup_logging(path: Path = AGENT_LOG) -> None:
    """Timestamped file log always; a stream only when one exists (pythonw)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(process)d %(name)s %(levelname)s %(message)s")
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)


def beat(*, loops: int, last_poll: str, error: str | None = None,
         path: Path = HEARTBEAT) -> dict:
    row = {"utc": _utc(), "pid": os.getpid(), "loops": int(loops),
           "last_poll": last_poll, "error": (error or None)}
    _write_json(path, row)
    return row


def heartbeat_age_s(path: Path = HEARTBEAT, *, now: datetime | None = None) -> float | None:
    """Seconds since the agent's own last heartbeat; None when there is none."""
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
        t = datetime.fromisoformat(str(row["utc"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return ((now or datetime.now(timezone.utc)) - t).total_seconds()


def _pid_is_agent(pid: int) -> bool:
    """Alive AND its command line names this module (PID reuse is real)."""
    try:
        from backend.services import llama_server
        if not llama_server.pid_alive(int(pid)):
            return False
    except Exception:                                              # noqa: BLE001
        return False
    if sys.platform != "win32":
        return True
    try:
        from backend.services import quiet_subprocess as qsp
        r = qsp.run(["powershell", "-NoProfile", "-Command",
                     f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}')"
                     ".CommandLine"], capture_output=True, text=True, timeout=30)
        out = (r.stdout or "").strip()
    except Exception:                                              # noqa: BLE001
        return True
    return (not out) or "telegram_agent" in out


def next_backoff(prev: float, lived_s: float) -> float:
    if lived_s >= HEALTHY_S:
        return BACKOFF_MIN_S
    return min(BACKOFF_MAX_S, max(BACKOFF_MIN_S, prev * 2.0))


def _sup_log(row: dict) -> None:
    SUPERVISOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"utc": _utc(), **row}, default=str) + "\n")


def _kill_tree(child) -> None:
    """Kill the child WE started and its descendants, by ITS pid (never by name).

    The venv's `pythonw.exe` is a redirector that starts the real interpreter
    as ITS child (measured 2026-09-26: 53272 -> 91476), so killing the handle
    alone would orphan the process that actually polls. `/T` walks the tree
    from the pid this supervisor wrote down.
    """
    import subprocess
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(int(child.pid)), "/T", "/F"],
                           capture_output=True, timeout=30)
        except Exception:                                          # noqa: BLE001
            pass
    try:
        child.kill()
    except Exception:                                              # noqa: BLE001
        pass


def supervise(*, interval: float = 3.0) -> int:
    """Run `--serve` as a child for ever; restart on exit or on a stale heartbeat.

    One supervisor per machine: a live lock whose pid still names this module
    refuses a second one. `telegram/STOP` stops the supervisor and its child
    (by the child's handle, never by image name).
    """
    import subprocess

    try:
        old = json.loads(LOCK.read_text(encoding="utf-8-sig"))
        if (old.get("role") == "supervisor" and int(old.get("pid") or 0) != os.getpid()
                and _pid_is_agent(int(old["pid"]))):
            logger.error("REFUSED: supervisor pid %s is alive", old["pid"])
            return 3
    except (OSError, ValueError, TypeError, KeyError):
        pass
    lock = {"pid": os.getpid(), "role": "supervisor", "started_utc": _utc(),
            "hostname": os.environ.get("COMPUTERNAME"), "started_by": TASK_NAME,
            "child_pid": None, "restarts": 0}
    _write_json(LOCK, lock)
    logger.info("telegram supervisor up, pid %s", os.getpid())
    _sup_log({"event": "supervisor_start", "pid": os.getpid()})
    backoff = BACKOFF_MIN_S
    max_age = float(getattr(_cfg, "TELEGRAM_AGENT_HEARTBEAT_MAX_AGE_S", 600))
    while True:
        if STOP_FILE.exists():
            _sup_log({"event": "supervisor_stop", "why": "STOP file"})
            return 0
        err = (TG_DIR / "agent.log.err").open("a", encoding="utf-8")
        child = subprocess.Popen(
            [sys.executable, "-m", "scripts.telegram_agent", "--serve",
             "--interval", str(interval)],
            cwd=str(REPO), stdin=subprocess.DEVNULL, stdout=err, stderr=err)
        started = time.time()
        lock.update({"child_pid": child.pid, "child_started_utc": _utc()})
        _write_json(LOCK, lock)
        # the legacy pid file, now without a BOM and naming the LIVE child
        (TG_DIR / "agent.pid").write_text(f"{child.pid}\n", encoding="ascii")
        _sup_log({"event": "child_start", "child_pid": child.pid})
        why = None
        while child.poll() is None:
            time.sleep(15)
            if STOP_FILE.exists():
                _kill_tree(child)
                why = "STOP file"
                break
            age = heartbeat_age_s()
            if time.time() - started > max_age and (age is None or age > max_age):
                _kill_tree(child)                                 # by its own pid
                why = f"heartbeat stale ({age if age is None else round(age)}s > {max_age:g}s)"
                break
        try:
            rc = child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _kill_tree(child)
            rc = child.wait()
        err.close()
        lived = time.time() - started
        _sup_log({"event": "child_exit", "child_pid": child.pid, "rc": rc,
                  "lived_s": round(lived, 1), "why": why or "exited"})
        logger.warning("telegram agent child %s exited rc=%s after %.0fs (%s)",
                       child.pid, rc, lived, why or "exited")
        if why == "STOP file":
            return 0
        backoff = next_backoff(backoff, lived)
        lock["restarts"] = int(lock.get("restarts") or 0) + 1
        _write_json(LOCK, lock)
        time.sleep(backoff)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="long-poll and run commands")
    ap.add_argument("--supervise", action="store_true",
                    help="run --serve as a child for ever; restart on exit or a stale heartbeat")
    ap.add_argument("--brief", action="store_true", help="send the brief and exit")
    ap.add_argument("--claim", action="store_true", help="capture the owner chat id")
    ap.add_argument("--once", action="store_true", help="one poll pass and exit")
    ap.add_argument("--daily", action="store_true", help="run the daily digest jobs and exit")
    ap.add_argument("--interval", type=float, default=3.0)
    a = ap.parse_args(argv)
    if a.supervise or a.serve:
        setup_logging()
    else:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if a.supervise:
        return supervise(interval=a.interval)

    if a.claim:
        print(json.dumps(TG.claim_owner(), indent=1))
        return 0
    if a.daily:
        print(json.dumps(daily_jobs(), indent=1))
        return 0
    if a.brief:
        extra = daily_jobs()
        TG.send("\n".join([cmd_brief([], {})] + ([""] + extra if extra else [])), tag="brief")
        print("brief sent")
        return 0

    st = TG.status()
    if st.get("state", "").startswith("AWAITING"):
        print("no owner chat id yet — send /start to the bot, then --claim")
        TG.claim_owner()
    if not TG.owner_chat_id():
        return 2

    if a.once:
        print(json.dumps(TG.poll(HANDLERS), indent=1))
        return 0

    try:
        who = TG.me().get("username")
    except Exception as exc:                                       # noqa: BLE001
        who = f"UNKNOWN ({type(exc).__name__})"
    # THE FIRST LOG LINE IS THE LIVENESS PROOF (review 2026-09-26 §5 item 3)
    logger.info("telegram agent serving as %s, pid %s", who, os.getpid())
    beat(loops=0, last_poll="starting")
    loops = 0
    while True:
        try:
            for line in daily_jobs():
                TG.send(line, tag="daily")
        except Exception:                                          # noqa: BLE001
            logger.exception("daily jobs failed")
        state, err = "ok", None
        try:
            TG.poll(HANDLERS)
        except TG.TelegramRefused as exc:
            logger.warning("poll refused: %s", exc)
            state, err = "refused", str(exc)[:200]
            time.sleep(10)
        except Exception as exc:                                   # noqa: BLE001
            logger.exception("poll failed")
            state, err = "failed", f"{type(exc).__name__}: {str(exc)[:200]}"
            time.sleep(10)
        loops += 1
        try:
            beat(loops=loops, last_poll=state, error=err)
        except OSError:
            logger.exception("heartbeat write failed")
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
