"""Telegram as the remote cockpit: plain-text questions, inline buttons, context.

THE OWNER'S ASK (2026-10-06)
============================
    "Can I have a conversation with it just by asking questions rather than
     sending a / command? Can it send a text with bubbles I can click for
     certain responses? Is OpenClaw always on?"

WHAT THIS MODULE DOES
=====================
1. **An intent router.** A plain-text message ("how is pc paper doing", "why
   did we buy ACN", "and vs spy?") is mapped DETERMINISTICALLY by the fixed
   regex table `INTENT_TABLE` to one of `INTENTS`. Every intent is a RECEIPT
   READ: the numbers come from files on disk (or, for `broker`, the same
   read-only broker GET `/broker` already makes), never from a model.
2. **One cheap fallback.** Only when no row of the table matches does ONE
   DeepSeek classification call run, through `llm_analyzer._call_llm` (so the
   language pin, the spend breaker and telemetry all apply) with
   `purpose="telegram_router"`. The enum is IN the system prompt, the reply is
   validated against it, and an invented intent is REFUSED -- nothing runs.
   At most `TELEGRAM_ROUTER_LLM_MAX_PER_DAY` calls per UTC day.
3. **Inline buttons.** A reply can carry 2-4 buttons. `callback_data` is a short
   opaque id (Telegram caps it at 64 bytes) resolved from `telegram/callbacks.json`.
   Every button is a read-only receipt action, except:
     * "Run deeper research (needs /approve)" -- it ENQUEUES the existing
       approval flow (`/research` -> `request_approval`); nothing is spent
       until the owner taps Approve;
     * "Approve <id>" / "Deny <id>" -- offered ONLY for an item that is already
       PENDING and that the owner created from the phone (its evidence carries
       an `action` the phone asked for), and re-checked at tap time. The tap
       calls the very same `/approve` handler.
4. **A 30-minute context per chat** (last ticker / account / intent), so "and
   vs spy?" and "scale to $40k" resolve.

WHAT IT WILL NOT DO
===================
No intent places, approves, cancels, starts or stops anything. An imperative
("buy NVDA", "stop the sim", "approve AP1") is REFUSED with the explicit
command to use instead. The classifier cannot widen this: its enum contains
only read intents, and the router never runs a handler the table does not name.
Replies go to the owner only: the poller has already checked the chat id, and a
callback is honoured only when its chat AND its sender are the owner AND the
id was minted for that chat.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from backend import config as _cfg

logger = logging.getLogger(__name__)

PURPOSE = "telegram_router"

#: intent -> one line the classifier sees. The ENUM is these keys; an answer
#: outside them is refused. Every one is a READ.
INTENTS: dict[str, str] = {
    "nav": "every paper account's return vs SPY, from the ROI receipt",
    "account": "one paper account (PC paper, hack1..hack6, a website lane) vs SPY",
    "fleet": "the Alpaca paper fleet (hack accounts + PC paper) and today's fleet decisions",
    "compare_spy": "compare the account or stock being discussed to SPY",
    "scale": "what the discussed account's return would be on a different dollar amount",
    "broker": "live PC paper broker equity, cash and positions (read only)",
    "book": "the ranked next-month names",
    "books": "the LLM-portfolio books leaderboard",
    "forecasts": "today's forecast pass",
    "brief": "the full daily brief",
    "status": "simulation, model server and ranking status",
    "health": "the newest system health receipt: what is dead or stale",
    "openclaw": "whether OpenClaw (the gateway and the web reader) is on",
    "reader": "what the web reader read today",
    "digest": "the latest world news digest",
    "why_stock": "why we bought or hold a stock",
    "stock": "a stock's price, moves, events and books",
    "evidence": "the evidence fields for a stock (rank, holdings, revisions, catalyst, stop)",
    "pending": "approvals waiting on the owner",
    "help": "what the bot can do",
    "none": "nothing above fits",
}
INTENT_ENUM: tuple[str, ...] = tuple(INTENTS)

#: Accounts the router recognises, alias regex -> the account name in the ROI
#: receipt. Website lanes are matched by their own names at runtime.
ACCOUNT_ALIASES: tuple[tuple[str, str], ...] = (
    (r"pc[ -]?paper|the pc|pc account|\bpc\b", "PC-PAPER"),
    *((rf"hack ?{i}\b", f"hack{i}") for i in range(1, 7)),
)
WEBSITE_LANES: tuple[str, ...] = (
    "tsmom-overlay", "conservative-atr", "aggressive", "balanced-ew-control", "balanced",
    "conservative", "tsmom-6040-control", "smallmid-quality", "conviction", "mirror")

_TICKER_RX = r"\$?([A-Za-z]{1,5}(?:[.\-][A-Za-z]{1,2})?)"
#: Words that are ticker-shaped but never a ticker in these sentences.
_STOP = {"A", "AN", "THE", "IT", "THIS", "THAT", "WE", "YOU", "US", "SPY", "VS", "TO", "AND",
         "ON", "FOR", "OF", "IN", "IS", "ARE", "DID", "DO", "WHY", "WHAT", "HOW", "STOCK",
         "NAME", "ONE", "THEM", "THESE", "THOSE", "ME", "MY", "OUR", "PC", "PAPER", "HACK",
         "BUY", "SELL", "HOLD", "OWN", "SHOW", "TELL", "ABOUT", "ITS", "NOW", "TODAY"}

#: Imperatives the router refuses outright (it is a reader, not a trader).
_ACTION_RX = re.compile(
    r"^(?:please\s+|can you\s+|could you\s+|go\s+)?(buy|sell|short|cover|place|cancel|close|"
    r"liquidate|approve|deny|start|stop|kill|restart|trade|execute|send)\b", re.I)

#: THE INTENT TABLE. Ordered; the first match wins. (pattern, intent).
INTENT_TABLE: tuple[tuple[re.Pattern, str], ...] = tuple((re.compile(p, re.I), i) for p, i in (
    (r"\bopen ?claw\b|\bgateway\b", "openclaw"),
    (r"\breader\b|\bwhat did (?:it|we|you|aegis) read\b|\bpages? read\b", "reader"),
    (r"\bpending\b|\bapprovals?\b|\bwaiting on me\b", "pending"),
    (r"\bhealth\b|\bwhat'?s (?:broken|red|dead|stale)\b|\bis (?:everything|anything) "
     r"(?:ok|okay|broken|fine)\b", "health"),
    (r"\bdigest\b|\bworld news\b|\bheadlines\b|\bwhat'?s (?:happening|going on) in the "
     r"(?:world|market)s?\b", "digest"),
    (r"\bscale\b.*?\$?\s*\d", "scale"),
    (r"\bwhy\b.*\b(?:buy|bought|own|hold|holding|long|pick|picked|choose|chose)\b", "why_stock"),
    (r"\bwhy (?:this|that|it)\b", "why_stock"),
    (r"\b(?:vs\.?|versus|against|compare[sd]?|relative to)\b.*\bspy\b|\bspy\b.*\b(?:vs\.?|versus|"
     r"against|compare[sd]?)\b|^and spy\b", "compare_spy"),
    (r"\bevidence\b|\bresearch\b", "evidence"),
    (r"\bfleet\b|\ball (?:the )?accounts\b|\bhack accounts\b", "fleet"),
    (r"pc[ -]?paper|\bhack ?[1-6]\b|\bthe pc\b|\bpc account\b|\b(?:" + "|".join(
        re.escape(x) for x in WEBSITE_LANES) + r")\b lane", "account"),
    (r"\bbroker\b|\bcash\b|\bpositions\b|\bwhat do we (?:hold|own)\b", "broker"),
    (r"\bbooks\b|\bleaderboard\b", "books"),
    (r"\b(?:ranked )?book\b|\branking\b|\btop names\b", "book"),
    (r"\bforecasts?\b|\bpredictions?\b", "forecasts"),
    (r"\bbrief(?:ing)?\b|\bsummary\b|\bmorning report\b", "brief"),
    (r"\bnav\b|\bp ?& ?l\b|\bpnl\b|\bperformance\b|\bhow (?:are|is) (?:we|it|everything|"
     r"the books?|paper|our paper)\b.*\bdoing\b|\bhow much (?:did|have) we (?:make|made|lose|lost)\b|"
     r"\bhow are we doing\b", "nav"),
    (r"\bstatus\b|\bsystem\b|\bsim(?:ulation)?\b|\bis (?:it|aegis) running\b", "status"),
    (r"^(?:help|commands|menu)\b|\bwhat can you do\b", "help"),
))


# ─────────────────────────────── paths / io ─────────────────────────────────

def tg_dir(root: Path | None = None) -> Path:
    return Path(root or _cfg.OPTIMUS_LEDGER_DIR) / "telegram"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, obj: Any) -> None:
    """Atomic, UTF-8 without a BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return out


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


# ─────────────────────────────── entities ───────────────────────────────────

def find_account(text: str) -> Optional[str]:
    t = str(text or "").lower()
    for rx, name in ACCOUNT_ALIASES:
        if re.search(rx, t):
            return name
    for lane in WEBSITE_LANES:                      # longest names listed first
        if re.search(rf"\b{re.escape(lane)}\b", t):
            return lane
    return None


_SYMBOLS_CACHE: dict[str, frozenset] = {}


def known_symbols(root: Path | None = None) -> frozenset:
    """Symbols in the bars panel (cached per path). Empty when unreadable --
    then a stop-word-shaped token is never promoted to a ticker."""
    p = Path(root or _cfg.OPTIMUS_LEDGER_DIR) / "prices_2025_26" / "bars.parquet"
    key = str(p)
    if key not in _SYMBOLS_CACHE:
        try:
            import pandas as pd
            _SYMBOLS_CACHE[key] = frozenset(
                str(x).upper() for x in pd.read_parquet(p, columns=["symbol"])["symbol"].unique())
        except Exception:                                          # noqa: BLE001
            _SYMBOLS_CACHE[key] = frozenset()
    return _SYMBOLS_CACHE[key]


#: A lower/title-case pronoun that points back at the last thing discussed.
#: Case-SENSITIVE on purpose: "IT" in capitals is Gartner's ticker, not "it".
_PRONOUN_RX = re.compile(r"\b(?:it|It|this|This|that|That|them|Them|the same)\b")


def refers_back(text: str) -> bool:
    return bool(_PRONOUN_RX.search(str(text or "")))


def find_ticker(text: str, *, symbols: frozenset | None = None) -> Optional[str]:
    """A ticker the sentence names, or None. Prefers an explicit `$X`; then an
    ALL-CAPS word (a stop-word-shaped one such as IT, ON, NOW or A only when it
    is a symbol in the bars panel); then the word after buy/bought/own/hold.
    Independent of any account the sentence also names (review C6 F1)."""
    raw = str(text or "")
    m = re.search(r"\$([A-Za-z]{1,5}(?:[.\-][A-Za-z]{1,2})?)\b", raw)
    if m:
        return m.group(1).upper()
    caps = [w for w in re.findall(r"\b[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?\b", raw)
            if not re.fullmatch(r"HACK\d?|PC", w)]
    for w in caps:
        if w not in _STOP and len(w) >= 2:
            return w
    for w in caps:
        if w in _STOP and w != "SPY" and w in (symbols or frozenset()):
            return w
    m = re.search(r"\b(?:buy|bought|own|hold|holding|pick|picked|on|about|for|of|is|"
                  r"research|evidence)\s+" + _TICKER_RX + r"\b", raw, re.I)
    if m and m.group(1).upper() not in _STOP:
        return m.group(1).upper()
    return None


def parse_amount(text: str) -> Optional[float]:
    m = re.search(r"\$?\s*(\d+(?:[.,]\d+)?)\s*(k|m|mm|million|thousand|bn)?\b", str(text or ""), re.I)
    if not m:
        return None
    x = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    x *= {"k": 1e3, "thousand": 1e3, "m": 1e6, "mm": 1e6, "million": 1e6, "bn": 1e9}.get(unit, 1.0)
    return x if x > 0 else None


# ─────────────────────────────── context ────────────────────────────────────

def _ctx_path(root: Path | None = None) -> Path:
    return tg_dir(root) / "cockpit_context.json"


def get_context(chat: str, *, root: Path | None = None, now: datetime | None = None) -> dict:
    """The chat's context if younger than TELEGRAM_CONTEXT_TTL_MIN, else {}."""
    now = now or _now()
    d = _read_json(_ctx_path(root)) or {}
    c = d.get(str(chat)) if isinstance(d, dict) else None
    if not isinstance(c, dict):
        return {}
    try:
        t = datetime.fromisoformat(str(c.get("t")))
    except (TypeError, ValueError):
        return {}
    if now - t > timedelta(minutes=float(_cfg.TELEGRAM_CONTEXT_TTL_MIN)):
        return {}
    return c


def set_context(chat: str, *, root: Path | None = None, now: datetime | None = None,
                **fields) -> dict:
    now = now or _now()
    p = _ctx_path(root)
    d = _read_json(p)
    d = d if isinstance(d, dict) else {}
    cur = get_context(chat, root=root, now=now)
    cur.update({k: v for k, v in fields.items() if v is not None})
    cur["t"] = _iso(now)
    d[str(chat)] = cur
    _write_json(p, d)
    return cur


# ─────────────────────────────── classification ─────────────────────────────

def classify(text: str, *, symbols: frozenset | None = None) -> Optional[dict]:
    """The deterministic path. {"intent", "ticker", "account", "amount", "via"}
    or None when no table row matches. Never calls a model. `symbols` (the bars
    panel's) lets a capital stop-word-shaped token (IT, ON, NOW) be a ticker."""
    t = " ".join(str(text or "").split()).strip()
    if not t:
        return None
    m = _ACTION_RX.match(t)
    if m:
        return {"intent": "refused_action", "verb": m.group(1).lower(), "via": "table"}
    for rx, intent in INTENT_TABLE:
        if rx.search(t):
            out = {"intent": intent, "via": "table",
                   "account": find_account(t), "ticker": None, "amount": None}
            if intent in ("why_stock", "compare_spy", "evidence", "stock"):
                out["ticker"] = find_ticker(t, symbols=symbols)
                out["refers_back"] = refers_back(t)
            if intent == "scale":
                out["amount"] = parse_amount(re.sub(r"hack ?\d", "", t, flags=re.I))
            if intent == "account" and not out["account"]:
                continue
            return out
    return None


def _router_log(root: Path | None = None) -> Path:
    return tg_dir(root) / "router_llm.jsonl"


def llm_calls_today(*, root: Path | None = None, now: datetime | None = None) -> int:
    day = str((now or _now()).date())
    return sum(1 for r in _read_jsonl(_router_log(root))
               if r.get("day") == day and r.get("phase") == "call")


LLM_SYSTEM = (
    "You classify ONE message sent to an investment operator's read-only status bot. "
    "Answer with ONE JSON object and nothing else: "
    '{"intent": <one of the enum>, "ticker": <US ticker or null>, "account": <account or null>}. '
    "The intent MUST be exactly one of these strings:\n"
    + "\n".join(f"- {k}: {v}" for k, v in INTENTS.items())
    + "\nAccounts: PC-PAPER, hack1..hack6, " + ", ".join(WEBSITE_LANES) + ". "
    "If the message asks to buy, sell, approve, cancel, start or stop anything, answer "
    '"none". Never invent an intent.')


def _parse_llm(reply: Optional[str]) -> tuple[Optional[dict], Optional[str]]:
    if reply is None:
        return None, "no reply (provider unavailable, budget, breaker, or a non-English reply refused)"
    s = str(reply).strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I).strip()
    m = re.search(r"\{.*\}", s, re.S)
    if not m:
        return None, f"not JSON: {s[:60]!r}"
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None, f"not JSON: {s[:60]!r}"
    intent = str(d.get("intent") or "").strip()
    if intent not in INTENT_ENUM:
        return None, f"intent {intent[:40]!r} is not in the enum"
    tk = d.get("ticker")
    tk = str(tk).upper().lstrip("$") if tk else None
    if tk and not re.fullmatch(r"[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?", tk):
        tk = None
    acc = d.get("account")
    acc = find_account(str(acc)) if acc else None
    return {"intent": intent, "ticker": tk, "account": acc, "amount": None, "via": "llm"}, None


def classify_llm(text: str, *, call_fn: Callable[..., Optional[str]] | None = None,
                 root: Path | None = None, now: datetime | None = None) -> dict:
    """ONE DeepSeek call, capped per UTC day, validated against the enum.

    Returns {"intent": ...} or {"refused": why}. Every attempt is a row in
    `telegram/router_llm.jsonl` BEFORE the call (so a crash still counts)."""
    now = now or _now()
    t = " ".join(str(text or "").split())
    if len(t) > int(_cfg.TELEGRAM_ROUTER_LLM_MAX_CHARS):
        return {"refused": f"message longer than {_cfg.TELEGRAM_ROUTER_LLM_MAX_CHARS} chars; "
                           "not sent to the classifier"}
    cap = int(_cfg.TELEGRAM_ROUTER_LLM_MAX_PER_DAY)
    n = llm_calls_today(root=root, now=now)
    if n >= cap:
        return {"refused": f"classifier cap reached ({n} of {cap} today, "
                           "TELEGRAM_ROUTER_LLM_MAX_PER_DAY)"}
    try:
        from backend.services import lab_budget as LB
        sp = LB.spend_today()
        if sp.get("cap_reached"):
            return {"refused": f"today's LLM spend ${sp.get('spend_today_usd', 0):.2f} has reached "
                               f"the ${sp.get('cap_usd', 0):.2f} cap"}
    except Exception as exc:                                       # noqa: BLE001
        return {"refused": f"today's LLM spend CANNOT BE DETERMINED ({type(exc).__name__})"}
    row = {"t": _iso(now), "day": str(now.date()), "purpose": PURPOSE, "chars": len(t)}
    _append_jsonl(_router_log(root), {**row, "phase": "call"})
    if call_fn is None:
        from backend.services import llm_analyzer as LA
        call_fn = LA._call_llm
    try:
        reply = call_fn(LLM_SYSTEM, t, purpose=PURPOSE,
                        validate=lambda s: _parse_llm(s)[0] is not None)
    except Exception as exc:                                       # noqa: BLE001
        reply, err = None, f"call failed: {type(exc).__name__}"
    else:
        err = None
    parsed, why = _parse_llm(reply)
    why = err or why
    _append_jsonl(_router_log(root), {**row, "phase": "result",
                                      "intent": (parsed or {}).get("intent"), "refused": why})
    if parsed is None:
        return {"refused": f"classifier answer refused: {why}"}
    return parsed


# ─────────────────────────────── receipt readers ────────────────────────────
#
# Every function below READS a receipt and returns an `Answer`: the text, the
# receipt's own stamp and its kind. `run_intent` passes every Answer through
# `stamped()`, the ONE place that prints the age and says STALE past
# TELEGRAM_RECEIPT_STALE_H (review C6 F3). A reader cannot return bare text:
# `READERS` is the table `run_intent` dispatches through, and the tests call
# every entry and assert it returned an Answer. No model, no order.

CANNOT = "CANNOT DETERMINE"


@dataclass
class Answer:
    text: str
    as_of: Optional[str]          # the receipt's OWN stamp (ISO), never a file mtime
    kind: str                     # key into TELEGRAM_RECEIPT_STALE_H
    source: str                   # the receipt's name
    dated: str = ""               # when as_of is None: why there is no single stamp


def _optimus(root: Path | None) -> Path:
    return Path(root or _cfg.OPTIMUS_LEDGER_DIR)


def _pct(x: Any, nd: int = 2) -> str:
    try:
        return f"{float(x):+.{nd}f}%"
    except (TypeError, ValueError):
        return CANNOT


def _pp(x: Any) -> str:
    try:
        return f"{float(x):+.2f} pp vs SPY"
    except (TypeError, ValueError):
        return f"vs SPY {CANNOT}"


def _usd(x: Any) -> str:
    try:
        return f"${float(x):,.0f}"
    except (TypeError, ValueError):
        return CANNOT


def _val(x: Any) -> str:
    return CANNOT if x is None or x == "" else str(x)


def _parse_ts(ts: Any) -> Optional[datetime]:
    """An ISO stamp, a date, or a `YYYYMMDDTHHMMSSZ` file stamp -> aware UTC."""
    s = str(ts or "").strip()
    if not s:
        return None
    try:
        if re.fullmatch(r"\d{8}T\d{6}Z", s):
            return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def stale_limit_h(kind: str) -> float:
    lim = dict(_cfg.TELEGRAM_RECEIPT_STALE_H)
    return float(lim.get(kind, lim["default"]))


def age_line(as_of: Optional[str], kind: str, source: str, *, now: datetime | None = None,
             dated: str = "") -> str:
    """'receipt X: as of ... (N h old)', with STALE past the configured limit;
    an absent or unreadable stamp is CANNOT DETERMINE, never fresh."""
    now = now or _now()
    if as_of is None and dated:
        return f"(receipts: {source}; {dated})"
    t = _parse_ts(as_of)
    if t is None:
        return f"(receipt {source}: age {CANNOT} -- no readable stamp; treat as STALE)"
    h = (now - t).total_seconds() / 3600.0
    lim = stale_limit_h(kind)
    flag = f" -- STALE (limit {lim:g} h)" if h > lim else ""
    return f"(receipt {source}: as of {t:%Y-%m-%d %H:%M} UTC, {h:.1f} h old{flag})"


def stamped(a: Answer, *, now: datetime | None = None) -> str:
    return f"{a.text}\n{age_line(a.as_of, a.kind, a.source, now=now, dated=a.dated)}"


def latest_roi(root: Path | None = None) -> tuple[Optional[Path], Optional[dict]]:
    base = _optimus(root) / "paper_accounts"
    files = sorted(base.glob("roi_*.json"), key=lambda p: p.name)
    files = [f for f in files if "nobroker" not in f.name] or files
    if not files:
        return None, None
    return files[-1], _read_json(files[-1])


def roi_row(account: str, root: Path | None = None) -> tuple[Optional[Path], Optional[dict], Optional[dict]]:
    p, d = latest_roi(root)
    if not d:
        return p, d, None
    for r in d.get("rows") or []:
        if str(r.get("account")).lower() == str(account).lower():
            return p, d, r
    return p, d, None


def _no_roi() -> Answer:
    return Answer(f"{CANNOT}: no paper_accounts/roi_*.json receipt on disk.", None, "roi",
                  "paper_accounts/roi_*.json")


def account_answer(account: str, root: Path | None = None) -> Answer:
    p, d, r = roi_row(account, root)
    if p is None:
        return _no_roi()
    stamp = (d or {}).get("generated_utc")
    if r is None:
        return Answer(f"{account} -- {CANNOT}: not a row in {p.name}.", stamp, "roi", p.name)
    if r.get("roi_pct") is None:
        return Answer(f"{account} -- {r.get('status')}: {str(r.get('note') or '')[:160]}",
                      stamp, "roi", p.name)
    return Answer("\n".join([
        f"{r['account']} ({_val(r.get('family'))}) since {_val(r.get('inception'))}",
        f"equity {_usd(r.get('equity'))} on {_usd(r.get('start_capital'))}: {_pct(r.get('roi_pct'))}",
        f"SPY same window {_pct(r.get('spy_same_window_pct'))} -> {_pp(r.get('vs_spy_pp'))}",
        f"positions {_val(r.get('n_positions'))} · last mark {_val(r.get('last_mark'))} · "
        f"{_val(r.get('status'))}",
        "every book is PRODUCT_EXPERIMENT, paper"]), stamp, "roi", p.name)


def _broker_equity() -> dict:
    """The PC paper account's live equity: the same read-only GET `/broker`
    makes. {'equity': float} or {'error': why}. Tests replace this."""
    try:
        from backend.services import pc_broker as PB
        a = PB.account()
        return {"equity": float(a["equity"])}
    except Exception as exc:                                       # noqa: BLE001
        return {"error": type(exc).__name__}


#: The book_dna fields (chunk C3) the mandate answer prints INSTEAD of the raw
#: ahead-of-SPY count, which double-counts twins and clones.
DNA_FIELDS: tuple[str, ...] = ("n_ahead_non_twin", "n_independent_clusters_ahead",
                               "collapse_factor")


def mandate_answer(root: Path | None = None, *, broker_fn: Callable[[], dict] | None = None) -> Answer:
    """'How are we doing' answers the MANDATE, not the census (review C6 F2):
    PC-PAPER vs SPY over its own window, then each fleet account over its own
    window, then the ahead-of-SPY count AFTER the twin collapse -- or a plain
    NOT YET COMPUTED, never the raw count."""
    p, d = latest_roi(root)
    if not d:
        return _no_roi()
    rows = d.get("rows") or []
    pc = next((r for r in rows if r.get("account") == "PC-PAPER"), None)
    out = ["How we are doing: the mandate (PC-PAPER) first, then the fleet."]
    if pc and pc.get("roi_pct") is not None:
        out.append(f"PC-PAPER {_pct(pc.get('roi_pct'))} vs SPY {_pct(pc.get('spy_same_window_pct'))} "
                   f"over its own window since {_val(pc.get('inception'))} -> "
                   f"{_pp(pc.get('vs_spy_pp'))} (mark {_val(pc.get('last_mark'))})")
        live = (broker_fn or _broker_equity)()
        if live.get("equity") is not None and pc.get("start_capital"):
            eq = float(live["equity"])
            out.append(f"live broker equity now {_usd(eq)} "
                       f"({(eq / float(pc['start_capital']) - 1) * 100:+.2f}% since inception; "
                       "SPY is not re-marked live)")
        else:
            out.append(f"live broker equity: {CANNOT} ({live.get('error') or 'no start capital'})")
    else:
        out.append(f"PC-PAPER: {CANNOT} (no priced row)")
    out.append("Fleet (each over its own window):")
    for r in [x for x in rows if x.get("family") == "alpaca_fleet"]:
        if r.get("roi_pct") is None:
            out.append(f"  {r.get('account')}: {_val(r.get('status'))}")
        else:
            out.append(f"  {r.get('account')}: {_pct(r.get('roi_pct'))} ({_pp(r.get('vs_spy_pp'))}, "
                       f"since {_val(r.get('inception'))})")
    agg = d.get("aggregate") or {}
    dna = {**(agg.get("book_dna") if isinstance(agg.get("book_dna"), dict) else {}), **agg}
    if all(dna.get(k) is not None for k in DNA_FIELDS):
        out.append(f"Books ahead of SPY: {dna['n_ahead_non_twin']} non-twin = "
                   f"{dna['n_independent_clusters_ahead']} independent clusters "
                   f"(collapse factor {dna['collapse_factor']})")
    else:
        out.append("Books ahead of SPY: collapse factor NOT YET COMPUTED (the book_dna fields are "
                   "not in this receipt), so no count is shown.")
    out.append("Paper experiments; not the owner's money. /nav prints the full census.")
    return Answer("\n".join(out), d.get("generated_utc"), "roi", p.name)


def results_block(root: Path | None = None, *, markdown: bool = False) -> str:
    """The RESULTS block (2026-10-07, "speak with results"): the six headline lines of
    the newest `paper_accounts/results_voice_<run>.md`, put at the TOP of the brief and
    of 'how are we doing'. Absent file -> one CANNOT DETERMINE line, never silence.
    `markdown=True` escapes the legacy-Markdown specials (account names carry `_`)."""
    try:
        from backend.services import results_voice as RV           # noqa: PLC0415
        p, lines = RV.headline_block(_optimus(root) / "paper_accounts")
    except Exception as exc:                                        # noqa: BLE001 -- a line, never a raise
        p, lines = None, [f"RESULTS: {CANNOT} ({type(exc).__name__})"]
    if p is None and not lines:
        lines = [f"RESULTS: {CANNOT}: no paper_accounts/results_voice_*.md (python -m scripts.results_voice)"]
    elif p is not None:
        lines = lines + [f"(receipt {p.name})"]
    text = "\n".join(lines)
    if markdown:
        for ch in ("_", "*", "`", "["):
            text = text.replace(ch, "\\" + ch)
    return text


def fleet_answer(root: Path | None = None, *, now: datetime | None = None) -> Answer:
    p, d = latest_roi(root)
    if not d:
        return _no_roi()
    rows = [r for r in d.get("rows") or [] if r.get("family") in ("alpaca_fleet", "pc_paper")]
    rows.sort(key=lambda r: (r.get("vs_spy_pp") is None, -(float(r.get("vs_spy_pp") or 0))))
    out = ["Fleet (each account over its own window)"]
    for r in rows:
        if r.get("roi_pct") is None:
            out.append(f"{r.get('account')}: {_val(r.get('status'))}")
        else:
            out.append(f"{r.get('account')}: {_pct(r.get('roi_pct'))} ({_pp(r.get('vs_spy_pp'))}) · "
                       f"{_val(r.get('n_positions'))} pos")
    day = str((now or _now()).date())
    dec = [x for x in _read_jsonl(_optimus(root) / "paper_accounts" / "fleet_manager" /
                                  "decisions.jsonl") if x.get("row") == "decision"
           and str(x.get("session")) == day]
    if dec:
        kinds: dict[str, int] = {}
        for x in dec:
            kinds[str(x.get("kind"))] = kinds.get(str(x.get("kind")), 0) + 1
        out.append(f"fleet manager today ({day}): {len(dec)} decision(s): "
                   + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    else:
        out.append(f"fleet manager: no decision rows for session {day}")
    return Answer("\n".join(out), d.get("generated_utc"), "roi", p.name)


def scale_answer(account: str, amount: float, root: Path | None = None) -> Answer:
    p, d, r = roi_row(account, root)
    if p is None:
        return _no_roi()
    stamp = (d or {}).get("generated_utc")
    if r is None or r.get("roi_pct") is None:
        return Answer(f"Scale -- {CANNOT}: no priced row for {account}.", stamp, "roi", p.name)
    roi = float(r["roi_pct"]) / 100.0
    spy = r.get("spy_same_window_pct")
    pnl = amount * roi
    lines = ["LINEAR SCALING, NOT A FORECAST: the past paper return times a different amount; "
             "it ignores fills, minimum order sizes and costs at that size.",
             f"{r['account']} returned {_pct(r['roi_pct'])} since {_val(r.get('inception'))}.",
             f"The same percentage on ${amount:,.0f}: {'+' if pnl >= 0 else '-'}${abs(pnl):,.0f} "
             f"-> ${amount + pnl:,.0f}."]
    if spy is not None:
        s = amount * float(spy) / 100.0
        lines.append(f"SPY over the same window: {'+' if s >= 0 else '-'}${abs(s):,.0f}.")
    else:
        lines.append(f"SPY over the same window: {CANNOT}.")
    return Answer("\n".join(lines), stamp, "roi", p.name)


def _closes(ticker: str, root: Path | None = None):
    from backend.services import alerts_replies as AR
    ctx = AR.Ctx(optimus=_optimus(root))
    return AR._closes(ctx, ticker)


def ticker_vs_spy_answer(ticker: str, root: Path | None = None) -> Answer:
    src = "prices_2025_26/bars.parquet"
    s, b = _closes(ticker, root), _closes("SPY", root)
    if s is None or not len(s):
        return Answer(f"{ticker} vs SPY -- {CANNOT}: no bars for {ticker} on disk.", None, "bars", src)
    if b is None or not len(b):
        return Answer(f"{ticker} vs SPY -- {CANNOT}: no SPY bars on disk.", None, "bars", src)
    j = s.to_frame("x").join(b.to_frame("spy"), how="inner").dropna()
    if len(j) < 2:
        return Answer(f"{ticker} vs SPY -- {CANNOT}: fewer than 2 common sessions.", None, "bars", src)
    out = [f"{ticker} vs SPY (closes through {j.index[-1].date()})"]
    for h in (1, 5, 21, 63):
        if len(j) > h:
            a = j["x"].iloc[-1] / j["x"].iloc[-1 - h] - 1
            m = j["spy"].iloc[-1] / j["spy"].iloc[-1 - h] - 1
            if math.isfinite(a) and math.isfinite(m):
                out.append(f"{h:>2} sessions: {ticker} {a*100:+.2f}% · SPY {m*100:+.2f}% · "
                           f"diff {(a-m)*100:+.2f} pp")
    return Answer("\n".join(out), str(j.index[-1].date()), "bars", src)


def _newest_health(root: Path | None) -> tuple[Optional[Path], dict]:
    files = sorted((_optimus(root) / "health").glob("health_*.json"))
    if not files:
        return None, {}
    return files[-1], (_read_json(files[-1]) or {})


def health_answer(root: Path | None = None, *, limit: int = 8) -> Answer:
    p, d = _newest_health(root)
    if p is None:
        return Answer(f"Health -- {CANNOT}: no health/health_*.json receipt on disk.", None,
                      "health", "health/health_*.json")
    c = d.get("counts") or {}
    out = ["Health", " · ".join(f"{k} {v}" for k, v in c.items()) or f"counts {CANNOT}"]
    for v in ("DEAD", "STALE"):
        for r in [x for x in d.get("rows") or [] if x.get("verdict") == v][:limit]:
            out.append(f"{v} {r.get('name')}: {str(r.get('detail') or '')[:110]}")
            limit -= 1
        if limit <= 0:
            break
    return Answer("\n".join(out), d.get("generated_utc"), "health", p.name)


def openclaw_answer(root: Path | None = None) -> Answer:
    """Two lines: the gateway (newest health receipt), and the reader (its own
    status file, which carries its own age line in the text)."""
    p, d = _newest_health(root)
    if p is None:
        return Answer(f"OpenClaw -- {CANNOT}: no health/health_*.json receipt on disk.", None,
                      "health", "health/health_*.json")
    rows = {str(r.get("name")): r for r in d.get("rows") or []}
    g = rows.get("openclaw_gateway")
    sup = rows.get("task:AegisReaderSupervisor")
    st = _read_json(_optimus(root) / "dowjones" / "reader_status.json") or {}
    if g:
        parts = [x.strip() for x in str(g.get("detail") or "").split(";") if x.strip()]
        keep = parts[:1] + [x for x in parts[1:] if "PROVEN" in x or "pages" in x]
        l1 = (f"Gateway: {g.get('verdict')}: " + "; ".join(keep))[:300]
    else:
        l1 = f"Gateway: {CANNOT} (no openclaw_gateway row)"
    if st:
        reader = (f"{_val(st.get('state'))}, {_val(st.get('pages_ok_60m'))} pages OK in 60 min "
                  + age_line(st.get("t"), "reader", "reader_status.json"))
    else:
        reader = f"{CANNOT} (no reader_status.json)"
    sup_s = (f"supervisor task {sup.get('verdict')} "
             f"({str(sup.get('detail') or '').split(';')[0][:80]})"
             if sup else "NO reader supervisor row in the receipt")
    return Answer(f"{l1}\nReader: {reader}; {sup_s}.", d.get("generated_utc"), "health", p.name)


def reader_answer(root: Path | None = None) -> Answer:
    st = _read_json(_optimus(root) / "dowjones" / "reader_status.json")
    if not st:
        return Answer(f"Reader -- {CANNOT}: no dowjones/reader_status.json on disk.", None,
                      "reader", "dowjones/reader_status.json")
    out = [f"Reader {_val(st.get('state'))}: {_val(st.get('pages_ok_10m'))} OK in 10 min, "
           f"{_val(st.get('pages_ok_60m'))} OK in 60 min"]
    lanes = ((st.get("by_lane") or {}).get("lanes") or {})
    if lanes:
        out.append("Last 24 h by lane (OK / loads):")
        for k, v in sorted(lanes.items(), key=lambda kv: -int((kv[1] or {}).get("ok_24h") or 0)):
            out.append(f"  {k}: {_val(v.get('ok_24h'))} / {_val(v.get('loads_24h'))}")
    else:
        out.append(f"by lane: {CANNOT}")
    cls = st.get("classes_60m") or {}
    if cls:
        top = sorted(cls.items(), key=lambda kv: -int((kv[1] or {}).get("OK") or 0))[:6]
        out.append("Top sites, 60 min: " + ", ".join(f"{k} {v.get('OK', 0)}" for k, v in top))
    if st.get("last_error"):
        out.append(f"last error: {str(st['last_error'])[:120]}")
    return Answer("\n".join(out), st.get("t"), "reader", "dowjones/reader_status.json")


def digest_answer(root: Path | None = None) -> Answer:
    from backend.services import alerts_replies as AR
    files = sorted((_optimus(root) / "digest").glob("world_digest_*.json"))
    m = re.search(r"(\d{8}T\d{6}Z)", files[-1].name) if files else None
    text = AR.cmd_news("", AR.Ctx(optimus=_optimus(root)), _now())
    return Answer(text, m.group(1) if m else None, "digest",
                  files[-1].name if files else "digest/world_digest_*.json")


def stock_answer(ticker: str, root: Path | None = None) -> Answer:
    from backend.services import alerts_replies as AR
    return Answer(AR.cmd_stock(ticker, AR.Ctx(optimus=_optimus(root)), _now()), None, "bars",
                  "bars + alert ledger + frozen books",
                  "the price line names its close date; the others are ledgers")


def evidence_answer(ticker: str, root: Path | None = None) -> Answer:
    from backend.services import model_routing as MR
    kw = {"root": root} if root is not None else {}
    return Answer(MR.evidence_text(MR.evidence(ticker, **kw)), None, "default",
                  "model_routing.evidence", "each field is read from its own receipt")


def _dated(ts: Any, kind: Optional[str]) -> str:
    """A line's own age. kind=None for a historical decision row (its age is a
    fact, not a staleness); a kind for state that should be current."""
    t = _parse_ts(ts)
    if t is None:
        return f"date {CANNOT}"
    h = (_now() - t).total_seconds() / 3600.0
    if kind is None:
        return f"decided {h:.0f} h ago"
    return f"{h:.0f} h old" + (" STALE" if h > stale_limit_h(kind) else "")


def why_stock_answer(ticker: str, root: Path | None = None, *, account: str | None = None) -> Answer:
    """Why a name was bought, from the decision receipts that bought it. With an
    account named ("why did hack2 buy NVDA"), only that account's rows."""
    t = str(ticker).upper()
    base = _optimus(root)
    scope = f" in {account}" if account else ""
    out = [f"Why {t}{scope}? (from decision receipts; no model)"]
    found = False
    if account in (None, "PC-PAPER"):
        for day in sorted((base / "pc_book").glob("*/decisions.jsonl"), reverse=True)[:10]:
            hit = None
            for r in reversed(_read_jsonl(day)):
                for b in r.get("book") or []:
                    if str(b.get("symbol")).upper() == t:
                        hit = (r, b)
                        break
                if hit:
                    break
            if hit:
                r, b = hit
                er = b.get("expected_relative_return_21d")
                out.append(f"PC book {_val(r.get('asof'))} (a ranking, not a fill): rank "
                           f"{_val(b.get('rank'))}, state {_val(b.get('state'))}, weight "
                           + (f"{float(b['weight'])*100:.1f}%" if b.get("weight") is not None else CANNOT)
                           + ", decile OOS mean "
                           + ("unmeasured" if er is None else f"{er*100:+.2f}%/21d")
                           + f"; plan verdict {_val(r.get('verdict'))} [{_dated(r.get('t'), None)}]")
                found = True
                break
    buys = [x for x in _read_jsonl(base / "paper_accounts" / "fleet_manager" / "decisions.jsonl")
            if x.get("row") == "decision" and x.get("kind") == "buy"
            and str(x.get("symbol")).upper() == t
            and (account is None or str(x.get("role")) == str(account))]
    for x in buys[-3:]:
        out.append(f"{x.get('role')} {_val(x.get('session'))}: {str(x.get('reason'))[:140]} "
                   f"(policy {_val(x.get('policy_hash'))}) [{_dated(x.get('t'), None)}]")
        found = True
    if account is None:
        try:
            from backend.services import llm_portfolio as LP
            books = LP.read_books()
        except Exception as exc:                                   # noqa: BLE001
            books = None
            out.append(f"frozen books: could not be read ({type(exc).__name__})")
        for bk, p in [(bk, p) for bk in (books or []) for p in bk.get("positions") or []
                      if str(p.get("ticker")).upper() == t][-3:]:
            out.append(f"book {str(bk.get('name'))[:40]} ({bk.get('kind')}, "
                       f"frozen {str(bk.get('frozen_utc'))[:10]}): weight "
                       + (f"{float(p['weight'])*100:.1f}%" if p.get("weight") is not None else CANNOT)
                       + f", thesis: {str(p.get('thesis'))[:140]}")
            found = True
    if account in (None, "PC-PAPER"):
        snap = _read_json(base / "paper_accounts" / "pc_snapshot" / "state_latest.json") or {}
        for p in snap.get("positions") or []:
            if str(p.get("symbol")).upper() == t:
                out.append(f"PC-PAPER holds {_val(p.get('qty'))} @ {_val(p.get('avg_entry_price'))}, "
                           f"unrealised {_pct((p.get('unrealized_plpc') or 0) * 100, 1) if p.get('unrealized_plpc') is not None else CANNOT} "
                           f"[snapshot {_dated(snap.get('t'), 'snapshot')}]")
                found = True
    if not found:
        out.append(f"No buy of {t}{scope} in the receipts read. CANNOT EXPLAIN a buy that is not "
                   "on record.")
    return Answer("\n".join(out), None, "default",
                  "pc_book decisions, fleet_manager decisions, frozen books, PC snapshot",
                  "each line carries its own date")


#: intent -> the reader `run_intent` calls. Each returns an Answer; `stamped()`
#: adds the age. The tests call every entry.
READERS: dict[str, Callable[..., Answer]] = {
    "account": account_answer, "fleet": fleet_answer, "scale": scale_answer,
    "health": health_answer, "openclaw": openclaw_answer, "reader": reader_answer,
    "digest": digest_answer, "why_stock": why_stock_answer, "stock": stock_answer,
    "evidence": evidence_answer, "compare_spy": ticker_vs_spy_answer, "nav": mandate_answer,
}


# Plain-text views kept for callers that want the text alone (still stamped).
def account_text(account: str, root: Path | None = None) -> str:
    return stamped(account_answer(account, root))


def fleet_text(root: Path | None = None) -> str:
    return stamped(fleet_answer(root))


def scale_text(account: str, amount: float, root: Path | None = None) -> str:
    return stamped(scale_answer(account, amount, root))


def openclaw_text(root: Path | None = None) -> str:
    return stamped(openclaw_answer(root))


def reader_text(root: Path | None = None) -> str:
    return stamped(reader_answer(root))


def health_text(root: Path | None = None) -> str:
    return stamped(health_answer(root))


def why_stock_text(ticker: str, root: Path | None = None) -> str:
    return stamped(why_stock_answer(ticker, root))


def ticker_vs_spy_text(ticker: str, root: Path | None = None) -> str:
    return stamped(ticker_vs_spy_answer(ticker, root))


# ─────────────────────────────── callbacks / buttons ────────────────────────

def _cb_path(root: Path | None = None) -> Path:
    return tg_dir(root) / "callbacks.json"


def mint(chat: str, action: str, args: dict | None = None, *, root: Path | None = None,
         now: datetime | None = None) -> str:
    """Store an action under a short opaque id; return the id (<= 64 bytes)."""
    now = now or _now()
    p = _cb_path(root)
    d = _read_json(p)
    d = d if isinstance(d, dict) else {}
    ttl = timedelta(hours=float(_cfg.TELEGRAM_CALLBACK_TTL_H))
    keep = {}
    for k, v in d.items():
        try:
            if now - datetime.fromisoformat(str(v.get("t"))) <= ttl:
                keep[k] = v
        except (TypeError, ValueError, AttributeError):
            continue
    cid = "c" + secrets.token_hex(6)
    keep[cid] = {"t": _iso(now), "chat": str(chat), "action": action, "args": args or {}}
    if len(keep) > 500:
        for k in sorted(keep, key=lambda k: keep[k]["t"])[: len(keep) - 500]:
            keep.pop(k, None)
    _write_json(p, keep)
    assert len(cid.encode()) <= 64
    return cid


def resolve(cid: str, chat: str, *, root: Path | None = None,
            now: datetime | None = None) -> Optional[dict]:
    """The stored action for `cid` if it was minted for `chat` and is fresh."""
    now = now or _now()
    if not re.fullmatch(r"c[0-9a-f]{12}", str(cid or "")):
        return None
    d = _read_json(_cb_path(root))
    e = d.get(cid) if isinstance(d, dict) else None
    if not isinstance(e, dict) or str(e.get("chat")) != str(chat):
        return None
    try:
        if now - datetime.fromisoformat(str(e.get("t"))) > timedelta(
                hours=float(_cfg.TELEGRAM_CALLBACK_TTL_H)):
            return None
    except (TypeError, ValueError):
        return None
    return e


#: Every button action. All are reads except `research` (enqueues an approval
#: request) and `approve`/`deny` (the existing `/approve` `/deny` handlers, for
#: an owner-created PENDING item only).
BUTTON_ACTIONS: tuple[str, ...] = ("intent", "research", "approve", "deny")


def _keyboard(chat: str, buttons: list[tuple[str, str, dict]], root: Path | None) -> Optional[dict]:
    rows, row = [], []
    for label, action, args in buttons[:4]:
        row.append({"text": label[:40], "callback_data": mint(chat, action, args, root=root)})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows} if rows else None


def owner_created_pending(pending: list[dict]) -> list[dict]:
    """PENDING items the OWNER created from the phone (a `/research` or `/deep`
    request carries `evidence.action`). Other gates never get a button."""
    out = []
    for r in pending:
        ev = r.get("evidence") if isinstance(r.get("evidence"), dict) else {}
        act = ev.get("action") if isinstance(ev.get("action"), dict) else None
        if r.get("state") == "PENDING" and act and act.get("cmd") in ("research", "deep"):
            out.append(r)
    return out


def buttons_for(intent: str, c: dict) -> list[tuple[str, str, dict]]:
    """(label, action, args) for a reply. Context-dependent, 2-4 of them."""
    tk, acc = c.get("ticker"), c.get("account")
    if intent in ("why_stock", "stock", "evidence", "compare_spy") and tk:
        b = [("Show evidence", "intent", {"intent": "evidence", "ticker": tk}),
             ("Compare to SPY", "intent", {"intent": "compare_spy", "ticker": tk}),
             ("Why this stock?", "intent", {"intent": "why_stock", "ticker": tk}),
             ("Run deeper research (needs /approve)", "research", {"ticker": tk})]
        drop = {"evidence": "Show evidence", "compare_spy": "Compare to SPY",
                "why_stock": "Why this stock?"}.get(intent)
        return [x for x in b if x[0] != drop]
    if intent in ("account", "scale", "compare_spy") and acc:
        return [("Compare to SPY", "intent", {"intent": "compare_spy", "account": acc}),
                ("Scale to $40k", "intent", {"intent": "scale", "account": acc, "amount": 40000}),
                ("Scale to $1M", "intent", {"intent": "scale", "account": acc, "amount": 1000000}),
                ("Fleet", "intent", {"intent": "fleet"})]
    if intent in ("nav", "fleet", "brief", "broker"):
        return [("Fleet", "intent", {"intent": "fleet"}),
                ("PC paper", "intent", {"intent": "account", "account": "PC-PAPER"}),
                ("Health", "intent", {"intent": "health"})]
    if intent in ("health", "openclaw", "reader", "status"):
        return [("OpenClaw", "intent", {"intent": "openclaw"}),
                ("Reader today", "intent", {"intent": "reader"}),
                ("Health", "intent", {"intent": "health"})]
    return []


# ─────────────────────────────── dispatch ───────────────────────────────────

HELP = ("Ask in plain words, e.g.\n"
        "how is pc paper doing · show me the fleet · compare hack2 to spy · "
        "why did we buy ACN · and vs spy? · scale to $40k · what's the digest saying · "
        "health · is OpenClaw always on · what did the reader read today · pending\n"
        "Every number comes from a receipt on disk, with its age. Plain text never places, "
        "approves, cancels, starts or stops anything: use /approve <id> or /sim. /help lists commands.")

#: Intents that need an entity, and which one.
_TICKER_INTENTS = ("why_stock", "stock", "evidence")


def run_intent(intent: str, c: dict, *, handlers: dict, msg: dict | None = None,
               root: Path | None = None, now: datetime | None = None) -> tuple[str, bool]:
    """(text, markdown) for one READ intent. File readers go through READERS and
    `stamped()` (age + STALE); the rest are the agent's fixed handlers
    (cmd_book, cmd_brief, cmd_status, cmd_nav, cmd_pending), which print their
    own receipts."""
    tk, acc = c.get("ticker"), c.get("account")
    msg = msg or {}

    def h(name: str) -> str:
        fn = handlers.get(name)
        return fn([], msg) if fn else f"{name}: no handler"

    def r(name: str, *a, **k) -> str:
        return stamped(READERS[name](*a, root=root, **k), now=now)

    if intent == "refused_action":
        return (f"REFUSED: plain text never places, approves, cancels, starts or stops anything "
                f"(you wrote '{c.get('verb')}'). Use /approve <id> (see /pending), /deny <id>, or "
                f"/sim start|stop. The bot never originates an order."), False
    if c.get("ask"):
        return c["ask"], False
    if intent == "nav":
        return results_block(root) + "\n\n" + r("nav"), False
    if intent == "account":
        return (r("account", acc) if acc else
                "Which account? e.g. pc paper, hack2, balanced lane"), False
    if intent == "fleet":
        return r("fleet"), False
    if intent == "compare_spy":
        if tk:
            return r("compare_spy", tk), False
        if acc:
            return r("account", acc), False
        return "Compare what to SPY? Name an account (hack2, pc paper) or a ticker.", False
    if intent == "scale":
        amt = c.get("amount")
        if not acc:
            return "Scale which account? Name it, e.g. scale hack2 to $40k.", False
        if not amt:
            return "Scale to how much? e.g. scale to $40k", False
        return r("scale", acc, float(amt)), False
    if intent in ("health", "openclaw", "reader", "digest"):
        return r(intent), False
    if intent in _TICKER_INTENTS:
        if not tk:
            return "Which stock? e.g. why did we buy ACN (write $IT for a ticker that is a word)", False
        if intent == "why_stock":
            return r("why_stock", tk, account=acc), False
        return r(intent, tk), False
    handler = {"broker": "broker", "book": "book", "books": "books", "forecasts": "forecasts",
               "brief": "brief", "status": "system", "pending": "pending"}.get(intent)
    if handler:
        return h(handler), True
    return HELP, False


def _chat_of(msg: dict | None) -> str:
    return str(((msg or {}).get("chat") or {}).get("id") or "owner")


def reply_for(intent: str, c: dict, *, handlers: dict, msg: dict | None, chat: str,
              root: Path | None = None, pending_fn: Callable[[], list] | None = None,
              now: datetime | None = None) -> dict:
    text, md = run_intent(intent, c, handlers=handlers, msg=msg, root=root, now=now)
    if c.get("entity_note") and not c.get("ask"):
        text = f"{c['entity_note']}\n{text}"
    buttons = buttons_for(intent, c)
    if intent == "pending":
        if pending_fn is None:
            from backend.services import telegram_bridge as TG
            pending_fn = TG.pending_approvals
        mine = owner_created_pending(pending_fn())[:2]
        buttons = []
        for row in mine:
            buttons += [(f"Approve {row['id']}", "approve", {"id": row["id"]}),
                        (f"Deny {row['id']}", "deny", {"id": row["id"]})]
    out = {"text": text or "(empty reply)", "markdown": md, "intent": intent}
    kb = _keyboard(chat, buttons, root) if buttons else None
    if kb:
        out["reply_markup"] = kb
    return out


def _caps_tokens(text: str) -> list[str]:
    """Ticker-SHAPED words: all capitals, not SPY/HACKn/PC/I. A sentence that
    carries one never inherits a ticker from context (review C6 F1)."""
    return [w for w in re.findall(r"\b[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?\b", str(text or ""))
            if w not in ("SPY", "PC", "I") and not re.fullmatch(r"HACK\d?", w)]


def _resolve_entities(cls: dict, ctx: dict, text: str) -> dict:
    """Entities named in the sentence always win. Context fills a gap only when
    the sentence names nothing ticker-shaped, and the reply then SAYS so
    (`entity_note`). Never a silent substitution (review C6 F1)."""
    c = dict(cls)
    intent = c["intent"]
    named_tk, named_acc = c.get("ticker"), c.get("account")
    caps = _caps_tokens(text)
    carried = None

    if intent == "compare_spy" and not (named_tk or named_acc):
        if caps:
            c["ask"] = (f"Compare what to SPY? I read {', '.join(caps)} as a word, not a symbol "
                        "in the bars panel. Write $X for a ticker.")
        elif ctx.get("last_kind") == "account" and ctx.get("account"):
            c["account"], carried = ctx["account"], ctx["account"]
        elif ctx.get("ticker"):
            c["ticker"], carried = ctx["ticker"], ctx["ticker"]
        elif ctx.get("account"):
            c["account"], carried = ctx["account"], ctx["account"]
    if intent == "scale" and not named_acc and ctx.get("account"):
        c["account"], carried = ctx["account"], ctx["account"]
    if intent in _TICKER_INTENTS and not named_tk:
        if caps:
            c["ask"] = (f"Which stock? I read {', '.join(caps)} as a word, not a symbol in the "
                        "bars panel. Write $X for a ticker (e.g. $IT).")
        elif ctx.get("ticker"):
            c["ticker"], carried = ctx["ticker"], ctx["ticker"]
    if carried:
        c["entity_note"] = (f"(about {carried}: carried from your last 30 min, not named in this "
                            "message)")
    elif intent in _TICKER_INTENTS + ("compare_spy", "scale", "account") and (named_tk or named_acc):
        c["entity_note"] = "(about " + " in ".join(x for x in (named_tk, named_acc) if x) + ")"
    return c


def rate_wait_s(*, root: Path | None = None, now: datetime | None = None) -> Optional[int]:
    """Seconds until the per-minute reply limit frees a slot; None when not limited."""
    now = now or _now()
    try:
        from backend.services import alerts_replies as AR
        ctx = AR.Ctx(optimus=_optimus(root))
        if AR.replies_last_minute(ctx, now) < int(_cfg.TELEGRAM_REPLY_MAX_PER_MIN):
            return None
        ts = []
        for row in AR._read_jsonl(ctx.telegram / "conversation.jsonl")[-200:]:
            t = _parse_ts(row.get("t")) if row.get("dir") == "out" else None
            if t and (now - t).total_seconds() < 60:
                ts.append(t)
        oldest = min(ts) if ts else now
        return max(1, int(60 - (now - oldest).total_seconds()) + 1)
    except Exception:                                              # noqa: BLE001
        return None


def replies_rate_limited(*, root: Path | None = None, now: datetime | None = None) -> bool:
    return rate_wait_s(root=root, now=now) is not None


def _rate_limited_reply(wait: int) -> dict:
    """Never silence (review C6 F6): the owner learns why and when."""
    return {"text": f"rate-limited: more than {_cfg.TELEGRAM_REPLY_MAX_PER_MIN} replies in the last "
                    f"minute. Try again in {wait} s.", "markdown": False, "intent": "rate_limited"}


def route_text(text: str, msg: dict | None, *, handlers: dict, root: Path | None = None,
               call_fn: Callable[..., Optional[str]] | None = None,
               fallback: Callable[[str, dict], Optional[str]] | None = None,
               now: datetime | None = None) -> Optional[dict | str]:
    """The owner's plain-text message -> a reply dict {text, markdown, reply_markup?}.

    Order: the existing reply grammar's explicit commands (`stock X`, `digest
    <paste>`, a URL, `ask ...`) keep their meaning; then the intent table; then
    the existing bare-ticker grammar ("NVDA", "how is NVDA"); then ONE capped
    classifier call; then the help reply. The caller has checked the chat."""
    from backend.services import alerts_replies as AR
    now = now or _now()
    chat = _chat_of(msg)
    raw = str(text or "")
    t = " ".join(raw.split())
    first = t.split(" ", 1)[0].lstrip("/").split("@")[0].lower() if t else ""
    explicit = first in AR.COMMANDS and first != "help"

    def _grammar() -> Optional[dict | str]:
        """The existing reply grammar (`alerts_replies`), plus stock buttons."""
        cmd, arg = AR.parse(t)
        rep = (fallback or AR.respond)(raw, msg)
        if rep is None:                            # AR.respond's only None: its rate limit
            return _rate_limited_reply(rate_wait_s(root=root, now=now) or 60)
        tk = AR._ticker(arg) if cmd in ("stock", "news") else None
        if not tk:
            return rep
        set_context(chat, root=root, now=now, ticker=tk, last_kind="ticker")
        kb = _keyboard(chat, buttons_for("stock", {"ticker": tk}), root)
        return {"text": rep, "markdown": False, "intent": "stock",
                **({"reply_markup": kb} if kb else {})}

    if explicit or AR._URL.match(t):
        return _grammar()
    caps_stop = [w for w in _caps_tokens(t) if w in _STOP]
    cls = classify(t, symbols=known_symbols(root) if caps_stop else None)
    if cls is None and AR.parse(t)[0] != "help":
        return _grammar()
    wait = rate_wait_s(root=root, now=now)
    if wait is not None:
        return _rate_limited_reply(wait)
    if cls is None:
        cls = classify_llm(t, call_fn=call_fn, root=root, now=now)
        if "refused" in cls:
            return {"text": f"{cls['refused']}. Nothing ran.\n\n{HELP}", "markdown": False,
                    "intent": "refused"}
        if cls["intent"] == "none":
            return {"text": HELP, "markdown": False, "intent": "help"}
    ctx = get_context(chat, root=root, now=now)
    c = _resolve_entities(cls, ctx, t)
    rep = reply_for(c["intent"], c, handlers=handlers, msg=msg, chat=chat, root=root, now=now)
    upd: dict[str, Any] = {"intent": c["intent"]}
    if c.get("ticker"):
        upd.update(ticker=c["ticker"], last_kind="ticker")
    if c.get("account"):
        upd.update(account=c["account"], last_kind="account")
    set_context(chat, root=root, now=now, **upd)
    if cls.get("via") == "llm":
        rep["text"] = rep["text"] + f"\n\n(understood as '{c['intent']}' by the classifier)"
    _log_turn(raw, rep, root=root, now=now)
    return rep


def _log_turn(text: str, rep: dict, *, root: Path | None, now: datetime) -> None:
    """The same conversation ledger `alerts_replies` writes, so the per-minute
    reply limit counts these replies too."""
    try:
        from backend.services import alerts_replies as AR
        ctx = AR.Ctx(optimus=_optimus(root))
        AR._log(ctx, {"t": _iso(now), "dir": "in", "chat": "owner", "chars": len(text),
                      "text": text[:400]})
        AR._log(ctx, {"t": _iso(now), "dir": "out", "chat": "owner",
                      "cmd": f"intent:{rep.get('intent')}", "text": str(rep.get("text"))[:2000]})
    except Exception:                                              # noqa: BLE001
        logger.exception("telegram cockpit: conversation log failed")


def _log_tap(cid: str, entry: Optional[dict], rep: Optional[dict], *, root: Path | None,
             now: datetime) -> None:
    """Append-only `telegram/taps.jsonl`: what each tap resolved to and the first
    line of what it answered, so a tap stays traceable after `callbacks.json`
    prunes its id (review C6 F5)."""
    try:
        first = str((rep or {}).get("text") or "").split("\n", 1)[0][:200]
        _append_jsonl(tg_dir(root) / "taps.jsonl", {
            "t": _iso(now), "id": str(cid)[:64],
            "action": (entry or {}).get("action"), "args": (entry or {}).get("args"),
            "resolved": entry is not None, "reply_first_line": first,
            "intent": (rep or {}).get("intent")})
    except Exception:                                              # noqa: BLE001
        logger.exception("telegram cockpit: tap log failed")


def handle_callback(data: str, cq: dict, *, handlers: dict, owner: Optional[str],
                    root: Path | None = None, now: datetime | None = None,
                    pending_fn: Callable[[], list] | None = None) -> Optional[dict]:
    """A button tap. None (nothing at all) unless the tap came from the OWNER's
    chat, by the owner, on an id minted for that chat. The poller checks the
    chat too; this re-checks, because a guard that trusts its caller is one.
    Every owner tap is a row in `taps.jsonl` and a turn in `conversation.jsonl`,
    and counts against the per-minute reply limit."""
    now = now or _now()
    chat = str(((cq.get("message") or {}).get("chat") or {}).get("id"))
    who = str((cq.get("from") or {}).get("id"))
    if not owner or chat != str(owner) or who != str(owner):
        return None
    e = resolve(str(data or ""), chat, root=root, now=now)
    wait = rate_wait_s(root=root, now=now)
    if wait is not None:
        rep = _rate_limited_reply(wait)
    elif e is None:
        rep = {"text": "That button has expired or is unknown. Ask again.", "markdown": False,
               "intent": "expired"}
    else:
        rep = _run_tap(e, chat=chat, cq=cq, handlers=handlers, root=root, now=now,
                       pending_fn=pending_fn)
    _log_tap(str(data or ""), e, rep, root=root, now=now)
    if rep and rep.get("intent") != "rate_limited":
        _log_turn(f"[tap {str(data or '')[:16]}]", rep, root=root, now=now)
    return rep


def _run_tap(e: dict, *, chat: str, cq: dict, handlers: dict, root: Path | None,
             now: datetime, pending_fn: Callable[[], list] | None) -> dict:
    action, args = e.get("action"), e.get("args") or {}
    msg = {"chat": {"id": chat}, "from": cq.get("from"), "text": ""}
    if action == "intent":
        intent = str(args.get("intent"))
        if intent not in INTENT_ENUM or intent == "none":
            return {"text": f"REFUSED: button intent {intent!r} is not in the enum.",
                    "markdown": False, "intent": "refused"}
        c = {"intent": intent, "ticker": args.get("ticker"), "account": args.get("account"),
             "amount": args.get("amount")}
        if c["ticker"] or c["account"]:
            c["entity_note"] = "(about " + " in ".join(
                x for x in (c["ticker"], c["account"]) if x) + ")"
        upd = {"intent": intent}
        if c["ticker"]:
            upd.update(ticker=c["ticker"], last_kind="ticker")
        if c["account"]:
            upd.update(account=c["account"], last_kind="account")
        set_context(chat, root=root, now=now, **upd)
        return reply_for(intent, c, handlers=handlers, msg=msg, chat=chat, root=root,
                         pending_fn=pending_fn, now=now)
    if pending_fn is None:
        from backend.services import telegram_bridge as TG
        pending_fn = TG.pending_approvals
    if action == "research":
        tk = str(args.get("ticker") or "").upper()
        if not re.fullmatch(r"[A-Z]{1,5}(?:[.\-][A-Z]{1,2})?", tk):
            return {"text": "REFUSED: no valid ticker on that button.", "markdown": False,
                    "intent": "refused"}
        fn = handlers.get("research")
        if fn is None:
            return {"text": "REFUSED: no /research handler.", "markdown": False, "intent": "refused"}
        before = {r["id"] for r in pending_fn()}
        out = fn([tk], {**msg, "text": f"/research {tk}"})
        if out:                                    # model_gate refused, or a usage line
            return {"text": out, "markdown": True, "intent": "research"}
        new = [r for r in owner_created_pending(pending_fn()) if r["id"] not in before]
        if not new:
            return {"text": "Research request sent for approval (see /pending).",
                    "markdown": False, "intent": "research"}
        r = new[-1]
        kb = _keyboard(chat, [(f"Approve {r['id']}", "approve", {"id": r["id"]}),
                              (f"Deny {r['id']}", "deny", {"id": r["id"]})], root)
        return {"text": f"Queued `{r['id']}`: /research {tk} waits for your tap. "
                        "Nothing is spent until you approve.",
                "markdown": True, "intent": "research", **({"reply_markup": kb} if kb else {})}
    if action in ("approve", "deny"):
        rid = str(args.get("id") or "")
        mine = {r["id"] for r in owner_created_pending(pending_fn())}
        if rid not in mine:
            return {"text": f"REFUSED: {rid} is not a PENDING request you created from the phone.",
                    "markdown": False, "intent": "refused"}
        fn = handlers.get(action)
        if fn is None:
            return {"text": f"REFUSED: no /{action} handler.", "markdown": False, "intent": "refused"}
        return {"text": fn([rid], {**msg, "text": f"/{action} {rid}"}) or "", "markdown": True,
                "intent": action}
    return {"text": f"REFUSED: unknown button action {action!r}.", "markdown": False,
            "intent": "refused"}


__all__ = ["INTENTS", "INTENT_ENUM", "INTENT_TABLE", "BUTTON_ACTIONS", "READERS", "Answer",
           "classify", "classify_llm", "route_text", "handle_callback", "mint", "resolve",
           "buttons_for", "owner_created_pending", "stamped", "age_line", "mandate_answer",
           "openclaw_text", "reader_text", "health_text", "account_text", "fleet_text",
           "scale_text", "why_stock_text", "ticker_vs_spy_text", "get_context", "set_context",
           "llm_calls_today", "rate_wait_s", "known_symbols", "PURPOSE"]
