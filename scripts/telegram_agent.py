"""Aegis's Telegram operator — the brief, the remote control, the approval tap.

    python -m scripts.telegram_agent --serve         # long-poll, run commands
    python -m scripts.telegram_agent --brief         # send the daily brief, exit
    python -m scripts.telegram_agent --claim         # capture the owner chat id

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

*Money*
`/nav` broker equity, cash, positions, day move
`/book` the ranked next-month names
`/brief` the full daily brief

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
`/status` broker, sim, model server, ranker
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


HANDLERS = {
    "help": cmd_help, "start": cmd_help,
    "nav": cmd_nav, "book": cmd_book, "brief": cmd_brief,
    "sim": cmd_sim, "status": cmd_status,
    "pending": cmd_pending, "approve": cmd_approve, "deny": cmd_deny,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="long-poll and run commands")
    ap.add_argument("--brief", action="store_true", help="send the brief and exit")
    ap.add_argument("--claim", action="store_true", help="capture the owner chat id")
    ap.add_argument("--once", action="store_true", help="one poll pass and exit")
    ap.add_argument("--interval", type=float, default=3.0)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if a.claim:
        print(json.dumps(TG.claim_owner(), indent=1))
        return 0
    if a.brief:
        TG.send(cmd_brief([], {}), tag="brief")
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

    logger.info("telegram agent serving as %s", TG.me().get("username"))
    while True:
        try:
            TG.poll(HANDLERS)
        except TG.TelegramRefused as exc:
            logger.warning("poll refused: %s", exc)
            time.sleep(10)
        except Exception:                                          # noqa: BLE001
            logger.exception("poll failed")
            time.sleep(10)
        time.sleep(a.interval)


if __name__ == "__main__":
    raise SystemExit(main())
