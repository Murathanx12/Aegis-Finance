"""The owner talks back: short Telegram replies read from disk (LANE A phase 2).

THE OWNER'S WORDS (2026-09-28)
==============================
    "when I reply to it it should be able to read and pass to you or do its own
     research, like i can ask a stock, i can ask a news, daily report, I can give
     it a new info to digest. these can be saved for later but it passing me
     data i think can be done fast and easy."

So every reply here READS FILES that other jobs already wrote. Nothing here
calls an LLM, opens a browser, runs a backtest, starts a process, touches a
broker, or changes a cap, a stop, a weight or a policy. Text the owner sends is
DATA: it is parsed for a command word and a ticker, stored when asked
(`digest`, `ask`), and never executed, never used as a file path, never
forwarded to a model by this module. Questions that need thinking are QUEUED
(`telegram/questions.jsonl`) for the next session.

COMMANDS (case-insensitive; a leading "/" is allowed)
====================================================
    stock <TICKER>     price + moves in sigma, analyst snapshot, typed events,
                       open alerts, frozen books holding it and their verdict
    news <TICKER>      newest headlines on disk, deduplicated by title
    report             paper books vs SPY (newest receipt + its age), alerts
                       today, red health rows, LLM spend today (local ledger)
    digest <text|url>  text -> the paste inbox + the existing ingest, WITH its
                       line breaks, in full up to TELEGRAM_DIGEST_MAX_CHARS
                       (the reply says how much); publisher UNKNOWN unless
                       stated (`digest source=wsj ...`); a bare URL -> the
                       phone reading list (NOT fetched, by anything)
    analyze <alert id> the frozen alert row and the price since
    ask <question>     saved to telegram/questions.jsonl; read by
                       `scripts/owner_queue.py` (the reply says whether the
                       next Claude session sees it at start)
    queue              the questions and links waiting
    help               the list

Plain-language fallbacks: a bare ticker ("NVDA", "$nvda") is `stock`; a bare
URL is `digest`; "news on X" / "X news" is `news`; anything with "report" or
"brief" is `report`; "how is X" / "what about X" / "price of X" is `stock`.
Anything else gets `help`.

Every inbound message and every reply is appended to
`telegram/conversation.jsonl` (the chat is recorded as "owner", never by id).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from backend import config as _cfg
from backend.services import disk_guard as DG

COMMANDS: tuple[str, ...] = ("stock", "news", "report", "digest", "analyze", "ask", "queue",
                              "help")

HELP = """AEGIS replies (read from disk; no advice, no orders)
stock TICKER - price, moves in sigma, analyst snapshot, events, alerts, books
news TICKER - newest headlines on disk
report - paper books vs SPY, alerts today and the ones not sent, red health, LLM spend
digest TEXT - stored with its line breaks for tonight's claim extraction (add source=wsj to name the paper)
digest URL - added to the phone reading list; nothing fetches it
analyze ALERT_ID - the frozen alert and the price since
ask QUESTION - saved for a Claude session; no model runs
queue - the questions and links waiting"""


def _owner_queue():
    """`scripts/owner_queue.py` -- stdlib, the reader of what `ask`/`digest` save."""
    from scripts import owner_queue as OQ
    return OQ

_TICKER = re.compile(r"^\$?([A-Za-z]{1,5}(?:[.\-][A-Za-z]{1,2})?)$")
_URL = re.compile(r"^https?://\S+$", re.I)
_ALERT_ID = re.compile(r"^A[0-9a-f]{12}$", re.I)
_HOW = re.compile(r"^(?:how(?:'s| is| are)?|what about|price of|check|look at)\s+"
                  r"\$?([A-Za-z]{1,5}(?:[.\-][A-Za-z]{1,2})?)\s*\??$", re.I)
_NEWS_ON = re.compile(r"^news\s+(?:on|about|for)\s+\$?([A-Za-z.\-]{1,8})\s*\??$", re.I)
_X_NEWS = re.compile(r"^\$?([A-Za-z]{1,5})\s+news\s*\??$", re.I)
#: common words that are ticker-shaped but are not a request for a stock card
_NOT_TICKERS = {"HI", "HELLO", "HEY", "OK", "OKAY", "YES", "NO", "THANKS", "THX", "HELP",
                "REPORT", "NEWS", "STOCK", "ASK", "DIGEST", "BRIEF", "STOP", "START"}


@dataclass
class Ctx:
    """Where the replies read and write. Tests point every path at tmp_path."""
    optimus: Path = field(default_factory=lambda: Path(_cfg.OPTIMUS_LEDGER_DIR))
    bars_path: Optional[Path] = None
    books_path: Optional[Path] = None
    article_root: Optional[Path] = None

    @property
    def telegram(self) -> Path:
        return self.optimus / "telegram"

    @property
    def alerts_root(self) -> Path:
        return self.optimus / "alerts"

    @property
    def corpus(self) -> Path:
        return self.optimus / "news_corpus"

    @property
    def inbox(self) -> Path:
        return self.optimus / "digest_inbox"

    @property
    def bars(self) -> Path:
        return self.bars_path or self.optimus / "prices_2025_26" / "bars.parquet"


# ─────────────────────────────── parsing ────────────────────────────────────

def parse(text: str) -> tuple[str, str]:
    """(command, argument). Never raises; unknown text is ("help", "")."""
    t = " ".join(str(text or "").split())
    if not t:
        return "help", ""
    m = _NEWS_ON.match(t.lstrip("/"))
    if m:
        return "news", m.group(1)
    head, _, rest = t.partition(" ")
    w = head.lstrip("/").split("@")[0].lower()
    if w in COMMANDS:
        return w, rest.strip()
    if _URL.match(t):
        return "digest", t
    m = _NEWS_ON.match(t) or _X_NEWS.match(t)
    if m:
        return "news", m.group(1)
    m = _TICKER.match(t)
    if m and m.group(1).upper() not in _NOT_TICKERS:
        return "stock", m.group(1)
    m = _HOW.match(t)
    if m:
        return "stock", m.group(1)
    if re.search(r"\b(report|brief)\b", t, re.I):
        return "report", ""
    return "help", ""


def _ticker(arg: str) -> Optional[str]:
    m = _TICKER.match(str(arg or "").strip().split(" ")[0] if arg else "")
    return m.group(1).upper() if m else None


# ─────────────────────────────── helpers ────────────────────────────────────

def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def _closes(ctx: Ctx, ticker: str) -> Optional[pd.Series]:
    p = ctx.bars
    if not p.exists():
        return None
    try:
        b = pd.read_parquet(p, columns=["symbol", "date", "close"],
                            filters=[("symbol", "==", ticker)])
    except (OSError, ValueError):
        return None
    if not len(b):
        return None
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    return b.sort_values("date").set_index("date")["close"].dropna()


def _moves(s: pd.Series) -> dict:
    lr = np.log(s.to_numpy(float))
    r = np.diff(lr)[-int(_cfg.ALERT_SIGMA_LOOKBACK_SESSIONS):]
    r = r[np.isfinite(r)]
    out: dict[str, Any] = {"last": float(s.iloc[-1]), "date": str(s.index[-1].date())}
    if len(r) < 21:
        out["sigma"] = None
        return out
    sd = float(np.std(r, ddof=1))
    out["sigma"] = sd
    for h in (1, 5, 21):
        if len(lr) > h and sd > 0:
            out[f"z{h}"] = float((lr[-1] - lr[-1 - h]) / (sd * math.sqrt(h)))
    return out


def _frozen(ctx: Ctx) -> list[dict]:
    from backend.services import alerts as AL
    return AL.frozen_alerts(AL.read_ledger(ctx.alerts_root))


def _known_ticker(ctx: Ctx, t: str) -> bool:
    try:
        from backend.services import alerts_sources as S
        cmap = S.load_cik_map(ctx.optimus / "edgar_8k" / "company_tickers.json")
        return any(t == x for v in cmap.values() for x, _ in v)
    except Exception:                                              # noqa: BLE001
        return False


# ─────────────────────────────── commands ───────────────────────────────────

def cmd_stock(arg: str, ctx: Ctx, now: datetime) -> str:
    t = _ticker(arg)
    if not t:
        return "Which ticker? e.g. stock NVDA"
    s = _closes(ctx, t)
    if s is None and not _known_ticker(ctx, t):
        return f"Unknown ticker {t}: no bars on disk and not in the SEC ticker map."
    lines = [f"{t} (from disk; no advice)"]
    if s is None or not len(s):
        lines.append("Price: no bars on disk for it")
    else:
        m = _moves(s)
        zs = ", ".join(f"{m[f'z{h}']:+.1f} sigma {h}d" for h in (1, 5, 21) if f"z{h}" in m)
        lines.append(f"Price {m['last']:.2f} ({m['date']} close)" + (f": {zs}" if zs else
                                                                     " (too few bars for sigma)"))
    tp = ctx.optimus / "analyst" / "target_snapshots.parquet"
    if tp.exists():
        try:
            a = pd.read_parquet(tp, filters=[("ticker", "==", t)])
            if len(a):
                r = a.sort_values("observed_at").iloc[-1]
                lines.append(f"Analyst snapshot {str(r['observed_at'])[:10]}: mean target "
                             f"{r['target_mean']:.2f} vs {r['price']:.2f} (a level, not a signal)")
        except (OSError, ValueError, KeyError):
            pass
    fz = [r for r in _frozen(ctx) if r.get("ticker") == t]
    if fz:
        fz.sort(key=lambda r: r["created_utc"])
        recent = [r for r in fz if (now - datetime.fromisoformat(r["created_utc"])) <= timedelta(days=7)]
        lines.append("Events: " + "; ".join(f"{r['created_utc'][:10]} {r['event_type_id']}"
                                             for r in fz[-3:]))
        if recent:
            lines.append(f"Alerts (7d): {len(recent)}: " + ", ".join(r["id"] for r in recent[-3:]))
    else:
        lines.append("Events: none in the alert ledger")
    try:
        from backend.services import llm_portfolio as LP
        books = [b for b in LP.read_books(ctx.books_path)
                 if b.get("kind") in ("personal", "competition")
                 and any(str(p.get("ticker")).upper() == t for p in b.get("positions") or [])]
    except OSError:
        books = []
    if books:
        verdict = _book_verdicts(ctx, [b["book_id"] for b in books])
        lines.append(f"In {len(books)} frozen book(s): " + ", ".join(b["name"] for b in books[:3])
                     + (f"; verdict vs benchmark/twin: {verdict}" if verdict else ""))
    else:
        lines.append("In no frozen book")
    return "\n".join(lines)


def _book_verdicts(ctx: Ctx, ids: list[str]) -> Optional[str]:
    d = ctx.optimus / "llm_portfolio"
    boards = sorted(d.glob("leaderboard_*.json")) if d.exists() else []
    if not boards:
        return None
    try:
        lb = json.loads(boards[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    g = [x for x in lb.get("grades") or [] if x.get("book_id") in ids]
    if not g:
        return None
    st: dict[str, int] = {}
    for x in g:
        k = str(x.get("status"))
        if x.get("vs_benchmark") is not None:
            k += f" ({x['vs_benchmark']:+.2%})"
        st[k] = st.get(k, 0) + 1
    return ", ".join(f"{k} x{v}" for k, v in st.items()) + f" [{boards[-1].name[12:22]}]"


def cmd_news(arg: str, ctx: Ctx, now: datetime) -> str:
    from backend.services import alerts_sources as S
    t = _ticker(arg)
    if not t:
        return "Which ticker? e.g. news NVDA"
    if not ctx.corpus.exists():
        return "No news corpus on disk."
    days = [str((now - timedelta(days=i)).date())
            for i in range(int(_cfg.TELEGRAM_NEWS_LOOKBACK_DAYS))]
    hits = []
    for d in sorted(ctx.corpus.iterdir()):
        n = d.name.lower()
        if not d.is_dir() or any(m in n for m in S.SOCIAL_MARKERS) \
                or not n.startswith(S.DISCOVERY_DIR_PREFIXES):
            continue
        for day in days:
            for r in _read_jsonl(d / f"{day}.jsonl"):
                if t not in {str(x).upper() for x in r.get("tickers") or []}:
                    continue
                ts = str(r.get("published_utc") or r.get("first_seen_utc") or "")
                hits.append((ts, d.name, " ".join(str(r.get("title") or "").split())))
    if not hits:
        return f"No headlines for {t} on disk in the last {_cfg.TELEGRAM_NEWS_LOOKBACK_DAYS} days."
    # dedup: the alert cluster rule on a headline -- same normalised title within
    # the dedup window is one story; the FIRST publication is kept, copies counted
    win = timedelta(hours=float(_cfg.ALERT_DEDUP_WINDOW_H))
    stories: list[dict] = []
    for ts, src, title in sorted(hits):
        key = re.sub(r"[^a-z0-9 ]", "", title.lower())
        tt = _to_dt(ts)
        hit = next((s for s in stories if s["key"] == key and tt and s["t"]
                    and abs(tt - s["t"]) <= win), None)
        if hit:
            hit["copies"] += 1
            continue
        stories.append({"key": key, "t": tt, "ts": ts, "src": src, "title": title, "copies": 0})
    stories.sort(key=lambda s: s["ts"], reverse=True)
    out = [f"{t} headlines (newest first, {len(stories)} stories, {len(hits)} rows)"]
    for s in stories[: int(_cfg.TELEGRAM_NEWS_MAX_ITEMS)]:
        out.append(f"{s['ts'][:10]} {s['src']}: {s['title'][:90]}"
                   + (f" (+{s['copies']} copies)" if s["copies"] else ""))
    return "\n".join(out)


def _to_dt(ts: str) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def cmd_report(arg: str, ctx: Ctx, now: datetime) -> str:
    from backend.services import alerts as AL
    lines = [f"AEGIS report {now:%Y-%m-%d %H:%M} UTC"]
    rois = sorted((ctx.optimus / "paper_accounts").glob("roi_*.json")) \
        if (ctx.optimus / "paper_accounts").exists() else []
    if rois:
        try:
            r = json.loads(rois[-1].read_text(encoding="utf-8"))
            gen = _to_dt(r.get("generated_utc"))
            age = f"{(now - gen).total_seconds() / 3600:.0f} h old" if gen else "age UNKNOWN"
            ag = r.get("aggregate") or {}
            ex = ag.get("priced_excluding_control_twins") or ag.get("all_priced") or {}
            lines.append(f"Paper books ({rois[-1].name}, {age}): {ex.get('n')} priced, "
                         f"ROI {ex.get('roi_pct')}%, P&L ${ex.get('pnl'):,.0f}; "
                         f"{ag.get('n_ahead_of_spy')} ahead of SPY, "
                         f"{ag.get('n_behind_spy')} behind, {ag.get('n_pending')} pending")
        except (OSError, ValueError, TypeError):
            lines.append(f"Paper books: {rois[-1].name} unreadable")
    else:
        lines.append("Paper books: no roi receipt on disk")
    rows = AL.read_ledger(ctx.alerts_root)
    day = AL.owner_day(now)
    sent = [r for r in rows if r.get("kind") == "SEND_RESULT" and r.get("status") == "SENT"
            and AL.owner_day(datetime.fromisoformat(r["created_utc"])) == day]
    would = [r for r in rows if r.get("kind") == "SEND_RESULT"
             and r.get("status") in ("DRY_RUN", "HELD_NOT_ENABLED")
             and AL.owner_day(datetime.fromisoformat(r["created_utc"])) == day]
    lines.append(f"Alerts today (HKT): {sum(len(r['refers_to']) for r in sent)} sent, "
                 f"{sum(len(r['refers_to']) for r in would)} dry-run/held")
    # the list the unsent-summary line points at ("reply `report` for the list")
    frozen = {r["id"]: r for r in AL.frozen_alerts(rows)}
    unsent = [(frozen[i], s["status"]) for i, s in AL.send_state(rows).items()
              if i in frozen and s["status"] in AL.UNSENT
              and AL.owner_day(datetime.fromisoformat(s["at"])) == day]
    if unsent:
        unsent.sort(key=lambda x: AL.rank_key(x[0]))
        lines.append(f"Not sent today ({len(unsent)}):")
        for r, st in unsent[:10]:
            lines.append(f"- {AL.cut_words(AL._row_fact_line(r), 90)} [{st}] "
                         f"{r['id']}")
        if len(unsent) > 10:
            lines.append(f"- ... {len(unsent) - 10} more (analyze <id> for any)")
    try:
        sm = _owner_queue().summary(ctx.optimus)
        lines.append(f"From your phone: {sm.get('questions_waiting')} question(s) waiting, "
                     f"{sm.get('links_queued')} link(s) on the reading list (reply: queue)")
    except Exception as exc:                                       # noqa: BLE001
        lines.append(f"From your phone: CANNOT DETERMINE ({type(exc).__name__})")
    try:
        from backend.services import system_health as SH
        bad = SH.non_alive_lines(limit=4)
        lines.append("Health: " + " | ".join(x.strip("_- ") for x in bad[:4]))
    except Exception as exc:                                       # noqa: BLE001
        lines.append(f"Health: CANNOT DETERMINE ({type(exc).__name__})")
    try:
        from backend.services import lab_budget as LB
        sp = LB.spend_today()
        lines.append(f"LLM spend today: ${sp['spend_today_usd']:.2f} of ${sp['cap_usd']:.2f} cap "
                     f"(local ledger; the provider balance is the truth)")
    except Exception as exc:                                       # noqa: BLE001
        lines.append(f"LLM spend today: CANNOT DETERMINE ({type(exc).__name__})")
    return "\n".join(lines)


_SOURCE_ARG = re.compile(r"^source=([A-Za-z][A-Za-z0-9_'.\- ]{0,39}?)(?:\s|$)", re.I)
#: What happens to a stored paste, said the same way every time (F6: exact).
CLAIMS_WHEN = ("its claims are extracted the next time the night reader or "
               "`python -m scripts.digest_ingest --once --claims` runs (nothing runs it on "
               "a schedule today)")


def cmd_digest(arg: str, ctx: Ctx, now: datetime) -> str:
    """Store a paste WITH its line breaks, in full up to TELEGRAM_DIGEST_MAX_CHARS
    (review F7), publisher UNKNOWN unless the owner states `source=<name>`; or put
    a bare URL on the phone reading list. Never fetches, never calls a model."""
    raw = str(arg or "").replace("\r\n", "\n").strip()
    if not raw:
        return "digest what? Send: digest <text or url>"
    if _URL.match(raw):
        p = ctx.telegram / "reading_queue.jsonl"
        DG.locked_append_line(p, json.dumps({"t": now.isoformat(timespec="seconds"),
                                             "url": raw, "state": "QUEUED_NOT_FETCHED"}))
        OQ = _owner_queue()
        rl = OQ.write_reading_list(ctx.optimus)
        return (f"Added to the phone reading list ({len(OQ.links(ctx.optimus))} link(s)): "
                f"digest_inbox/{rl.name}. Nothing fetches it. Open it when you paste articles, "
                f"then paste the text here with 'digest <text>' or into DIGEST.md.")
    source = None
    m = _SOURCE_ARG.match(raw)
    if m:
        source = m.group(1).strip()
        raw = raw[m.end():].lstrip()
    limit = int(_cfg.TELEGRAM_DIGEST_MAX_CHARS)
    total = len(raw)
    text = raw[:limit]
    # a pasted line that starts with "===" would split the entry in DIGEST.md
    text = "\n".join((" " + ln) if ln.lstrip().startswith("===") else ln
                     for ln in text.split("\n"))
    from backend.services import digest_inbox as DI
    d = DI.ensure_inbox(ctx.inbox)
    hdr = " | ".join(["telegram"] + ([f"source={source}"] if source else []))
    with DG.file_lock(d / "DIGEST.md.lock"):
        with open(d / "DIGEST.md", "a", encoding="utf-8") as fh:
            fh.write(f"\n=== | {hdr}\n{text}\n")
    stored = (f"Stored {len(text):,} of {total:,} characters with line breaks"
              + (f"; the last {total - len(text):,} were NOT stored (limit {limit:,}; paste long "
                 f"articles into DIGEST.md)" if total > len(text) else "")
              + f". Publisher: {source or 'UNKNOWN (add source=wsj to name it)'}."
              + (" Telegram splits pastes over 4,096 characters into several messages; only "
                 "this one was stored." if total >= 4000 else ""))
    try:
        r = DI.ingest(d, now_utc=now.isoformat(timespec="seconds"), root=ctx.article_root)
    except Exception as exc:                                       # noqa: BLE001
        return (f"{stored} The ingest failed ({type(exc).__name__}); the text is in "
                f"DIGEST.md and is ingested by the next digest_ingest run.")
    if r.get("n_new"):
        return f"{stored} Filed as {r['n_new']} new article; {CLAIMS_WHEN}."
    if len(text) < 200:
        return (f"{stored} Under 200 characters the ingest skips it as too short; send the "
                f"full article text.")
    return f"{stored} It was already in the corpus (duplicate); nothing new is extracted."


def cmd_analyze(arg: str, ctx: Ctx, now: datetime) -> str:
    from backend.services import alerts as AL
    aid = str(arg or "").strip().split(" ")[0]
    if not _ALERT_ID.match(aid):
        return "analyze needs an alert id like A81475b01dbcb"
    rows = AL.read_ledger(ctx.alerts_root)
    r = next((x for x in AL.frozen_alerts(rows) if x["id"].lower() == aid.lower()), None)
    if r is None:
        return f"No alert with id {aid}."
    st = AL.send_state(rows).get(r["id"], {})
    n_fu = sum(1 for x in rows if x.get("kind") == "FOLLOWUP" and x.get("refers_to") == r["id"])
    lines = [f"{r['id']} [{r['level']}] {r['ticker']} {r['event_type_id']} "
             f"(frozen {r['created_utc'][:16]}Z, status {st.get('status')}, {n_fu} follow-up(s))",
             r["fact"][:300], f"Source: {r['source_url']}"]
    if r.get("price_state") == "PRICED":
        lines.append(f"At alert: {r['last_price']:.2f} ({r['last_price_ts'][:10]} close), "
                     f"{r['move_1s_sigma']:+.1f} sigma 1d, {r['move_5s_sigma']:+.1f} sigma 5d")
        s = _closes(ctx, r["ticker"])
        after = s[s.index > pd.Timestamp(r["last_price_ts"][:10])] if s is not None else None
        if after is not None and len(after):
            ret = float(after.iloc[-1] / r["last_price"] - 1.0)
            k = len(after)
            sd = r.get("sigma_daily")
            z = (math.log(1 + ret) / (sd * math.sqrt(k))) if sd else None
            lines.append(f"Since: {after.iloc[-1]:.2f} on {after.index[-1].date()} "
                         f"({ret:+.1%} over {k} session(s)"
                         + (f", {z:+.1f} sigma" if z is not None else "") + ")")
        else:
            lines.append("Since: no new bar on disk yet")
    else:
        lines.append(f"At alert: {r.get('price_state')}")
    lines.append(f"Contradicts: {r['contradicts'][:200]}")
    lines.append(f"Not known: {r['not_known'][:300]}")
    return "\n".join(lines)


def cmd_ask(arg: str, ctx: Ctx, now: datetime) -> str:
    q = str(arg or "").strip()
    if not q:
        return "ask what? Send: ask <question>"
    p = ctx.telegram / "questions.jsonl"
    DG.locked_append_line(p, json.dumps({"t": now.isoformat(timespec="seconds"),
                                         "question": q, "state": "QUEUED"}))
    OQ = _owner_queue()
    waiting = [x for x in OQ.questions(ctx.optimus) if x["state"] == "WAITING"]
    n = waiting[-1]["n"] if waiting else "?"
    where = ("It is shown at the top of the next Claude session" if OQ.hooked_into_session_start()
             else "It is NOT yet shown to a Claude session automatically (that one-line hook "
                  "is owed); it is listed by `queue` here and by scripts/owner_queue.py")
    return (f"Saved as question #{n} ({len(waiting)} waiting). No model was called and "
            f"nothing was run. {where}; nobody answers it until a session does.")


def cmd_queue(arg: str, ctx: Ctx, now: datetime) -> str:
    OQ = _owner_queue()
    q = [x for x in OQ.questions(ctx.optimus) if x["state"] == "WAITING"]
    lk = OQ.links(ctx.optimus)
    out = [f"Waiting from your phone: {len(q)} question(s), {len(lk)} link(s)"]
    out += [f"#{x['n']} ({str(x['t'])[:10]}): {x['question'][:120]}" for x in q[-8:]]
    if lk:
        out.append(f"Links: digest_inbox/{OQ.READING_LIST_NAME} (newest: {lk[-1]['url'][:100]})")
    return "\n".join(out)


_DISPATCH = {"stock": cmd_stock, "news": cmd_news, "report": cmd_report,
             "digest": cmd_digest, "analyze": cmd_analyze, "ask": cmd_ask,
             "queue": cmd_queue}


def _digest_arg(raw: str) -> Optional[str]:
    """The text after a leading `digest` / `/digest` word, line breaks KEPT
    (`parse` collapses whitespace, which is right for commands and wrong for an
    article). None when the message is not a digest command."""
    m = re.match(r"^\s*/?digest(?:@\w+)?(?:[ \t]+|\n|$)", raw, re.I)
    return raw[m.end():] if m else None


# ─────────────────────────────── entry points ───────────────────────────────

def handle(text: str, *, ctx: Optional[Ctx] = None, now: Optional[datetime] = None) -> str:
    """The reply to one owner message. Reads files; never raises."""
    ctx = ctx or Ctx()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    raw = str(text or "")
    dg = _digest_arg(raw)
    if dg is not None:
        # a paste has its own stated limit and says what it stored (F7): never
        # the generic inbound cut, never whitespace-collapsed
        try:
            return cmd_digest(dg, ctx, now)
        except Exception as exc:                                   # noqa: BLE001
            return f"digest failed: {type(exc).__name__}"
    cap = int(_cfg.TELEGRAM_REPLY_MAX_INBOUND_CHARS)
    note = ""
    if len(raw) > cap:
        raw = raw[:cap]
        note = f"(Your message was {len(str(text))} characters; only the first {cap} were read.)\n"
    cmd, arg = parse(raw)
    if cmd == "help":
        return note + HELP
    try:
        return note + _DISPATCH[cmd](arg, ctx, now)
    except Exception as exc:                                       # noqa: BLE001
        return note + f"{cmd} failed: {type(exc).__name__}"


def _log(ctx: Ctx, row: dict) -> None:
    DG.locked_append_line(ctx.telegram / "conversation.jsonl", json.dumps(row, default=str))


def replies_last_minute(ctx: Ctx, now: datetime) -> int:
    n = 0
    for r in _read_jsonl(ctx.telegram / "conversation.jsonl")[-200:]:
        if r.get("dir") == "out":
            t = _to_dt(r.get("t"))
            if t and (now - t).total_seconds() < 60:
                n += 1
    return n


def respond(text: str, msg: Optional[dict] = None, *, ctx: Optional[Ctx] = None,
            now: Optional[datetime] = None) -> Optional[str]:
    """Ledger the inbound, rate-limit, reply, ledger the reply. The caller has
    already checked the chat is the owner's; this never sees a stranger."""
    ctx = ctx or Ctx()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cap = max(int(_cfg.TELEGRAM_REPLY_MAX_INBOUND_CHARS), int(_cfg.TELEGRAM_DIGEST_MAX_CHARS))
    _log(ctx, {"t": now.isoformat(timespec="seconds"), "dir": "in", "chat": "owner",
               "chars": len(str(text or "")), "text": str(text or "")[:cap]})
    if replies_last_minute(ctx, now) >= int(_cfg.TELEGRAM_REPLY_MAX_PER_MIN):
        _log(ctx, {"t": now.isoformat(timespec="seconds"), "dir": "dropped",
                   "why": "rate limit"})
        return None
    reply = handle(text, ctx=ctx, now=now)
    _log(ctx, {"t": now.isoformat(timespec="seconds"), "dir": "out", "chat": "owner",
               "cmd": parse(str(text or "")[:cap])[0], "text": reply})
    return reply


__all__ = ["COMMANDS", "Ctx", "HELP", "cmd_analyze", "cmd_ask", "cmd_digest", "cmd_news",
           "cmd_queue", "cmd_report", "cmd_stock", "handle", "parse", "replies_last_minute",
           "respond"]
