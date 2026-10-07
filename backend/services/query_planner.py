"""The search-led query planner: make the reader SEARCH, not only revisit.

    python -m backend.services.query_planner --plan            # print today's queries, run nothing
    python -m backend.services.query_planner --run --max 10    # issue up to 10 queries now
    python -m backend.services.query_planner --run --due       # the supervisor's call: only when due
    python -m backend.services.query_planner --yield           # the yield receipt, files only

WHY (chunk C7, 2026-10-06; audit `docs/research_notes/2026-10-06/
openclaw_open_web_and_model_audit_2026-10-06.md` §D)
=====================================================================
The reader is healthy -- 9,368 page loads in 7 days, 238 claims, 3,587 forecast
rows -- but it only REVISITS: section fronts, stock pages, the digest's asks.
OpenClaw's own `web_search` and `x_search` tools are allowed on every agent turn
by the read-only tool scope (`openclaw_tool_scope.READ_TOOLS`) and had never
been invoked once. They are the lawful search primitive (scraping DuckDuckGo or
Bing HTML is REFUSED: ToS / robots.txt, and Bing served a CAPTCHA before).

THE PIPELINE
============
1. SEEDS, all files: held names across the fleet (`paper_accounts/fleet_manager/
   state/*.json`) and PC-PAPER (`paper_accounts/pc_snapshot/state_latest.json`),
   the newest world digest's themes (`digest/world_digest_*.json`), and the
   opportunities shortlist (`opportunities/opportunities_*.json`, list `roi_v3`).
2. QUERIES are TEMPLATED, never written by a model, so they are auditable and
   cost nothing: a bounded number per UTC day (`QUERY_PLANNER_MAX_QUERIES_DAY`),
   per seed lane (`QUERY_PLANNER_LANE_QUERIES_DAY`) and per run, least-recently
   searched seed first. Each has a `query_id` (hash of day, lane, tool, text).
3. THE SEARCH (review 2026-10-06 F1). With NO declared provider
   (`QUERY_PLANNER_SEARCH_PROVIDER = None`, the default and today's truth) not
   one agent turn is issued: the same templates run against the $0 keyless
   sources -- Google News RSS (publisher + headline -> that publisher's OWN
   search page; the Google redirect is never opened) and EDGAR full-text
   search (the company's own 8-Ks on sec.gov). With a declared provider:
   ONE OpenClaw agent turn per query (`openclaw_client.agent`, the existing
   path, the read-only tool scope UNCHANGED): "call <tool> once, list the URLs,
   open nothing". The scope is audited BEFORE the run (any config problem or
   any tool call outside the read set in 24 h = REFUSED) and the turn's own
   transcript is read AFTER it: a call outside the read set, or ANY tool but
   the query's own (`web_fetch` included, F4), stops the run; a
   reply whose search tool never fired is not a search result, so its URLs are
   REFUSED (`NO_TOOL_CALL`) rather than trusted.
4. EVERY URL is classified: REFUSED (money / checkout / mail / message hosts
   via `web_reader.host_ok` and `browser_policy`, plus the ToS / robots refusals
   in `QUERY_PLANNER_REFUSED_HOSTS`), ADMITTED (the reader's own allowlist), or
   QUARANTINED (a host nobody has reviewed: written to
   `dowjones/query_planner_quarantine.jsonl` for a human, NEVER queued, never
   auto-allowed). `source_registry.score` is not the gate: it grades a source's
   forward skill by `source_id`, and a search result has no source id until a
   claim is read from it -- the reputation join happens downstream, unchanged.
5. ADMITTED URLs go to `dowjones/query_planner_queue.jsonl` with
   `first_seen_utc`, `query_id`, `discovered_via=web_search|x_search`; the
   reader pool adopts them into the `query_planner` budget lane (0.03 of the
   same 4,000 loads) with lane `qp:<query_id>`, so the page log, the stored
   article's `reached_by`, the claim's `post_url` and the forecast row's
   `inputs_used.claim_hash` attribute every yield back to its query.

A ZERO MUST SAY WHICH ZERO
==========================
Memory, 2026-09-28: "a zero that is always zero is a broken reader". The yield
block names its zero: NO_QUERIES_RAN, QUERIES_RAN_NO_TOOL_CALL,
QUERIES_RAN_NO_URLS, URLS_FOUND_NONE_ADMITTED, ADMITTED_NOT_YET_READ,
PAGES_READ_NO_CLAIMS, CLAIMS_NO_FORECASTS -- or YIELDING -- and prints the same
counts for the non-planner queue beside it.

No order, no message, no sign-up, no typing: the agent turn holds only the read
tools, and the browser only ever opens what the pool's own guards admit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlsplit

from backend import config as _config

TOOLS: tuple[str, ...] = ("web_search", "x_search")
SEED_LANES: tuple[str, ...] = ("held_names", "themes", "opportunities")
VERDICTS: tuple[str, ...] = ("admitted", "quarantined", "refused")
ZERO_KINDS: tuple[str, ...] = (
    "NO_QUERIES_RAN", "QUERIES_RAN_NO_TOOL_CALL", "TOOL_FIRED_BUT_UNAVAILABLE",
    "QUERIES_RAN_NO_URLS",
    "URLS_FOUND_NONE_ADMITTED", "ADMITTED_NOT_YET_READ", "PAGES_READ_NO_CLAIMS",
    "CLAIMS_NO_FORECASTS", "YIELDING")

_URL_RE = re.compile(r"https?://[^\s\"'<>\]\)]+")
_SAFE_TEXT = re.compile(r"[^A-Za-z0-9 $.,'&:/+\-]")


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def opt_dir(opt: Path | None = None) -> Path:
    return Path(opt or _config.OPTIMUS_LEDGER_DIR)


def dj_dir(opt: Path | None = None) -> Path:
    return opt_dir(opt) / "dowjones"


def ledger_path(opt: Path | None = None) -> Path:
    return dj_dir(opt) / "query_planner_ledger.jsonl"


def queue_path(opt: Path | None = None) -> Path:
    return dj_dir(opt) / "query_planner_queue.jsonl"


def quarantine_path(opt: Path | None = None) -> Path:
    return dj_dir(opt) / "query_planner_quarantine.jsonl"


def stop_path(opt: Path | None = None) -> Path:
    return dj_dir(opt) / "QUERY_PLANNER_STOP"


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        for ln in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if isinstance(r, dict):
                out.append(r)
    except OSError:
        pass
    return out


def _append_jsonl(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ts(v: Any) -> Optional[datetime]:
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


# ════════════════════════════════ seeds (files only) ═════════════════════════

def held_names(opt: Path | None = None) -> list[str]:
    """Every name held on PC-PAPER and across the fleet, PC-PAPER first,
    each in the file's own order (deduplicated, upper-case)."""
    base = opt_dir(opt) / "paper_accounts"
    out: list[str] = []
    pc = _read_json(base / "pc_snapshot" / "state_latest.json")
    for p in (pc or {}).get("positions") or [] if isinstance(pc, dict) else []:
        if isinstance(p, dict) and p.get("symbol") and float(p.get("qty") or 0) != 0:
            out.append(str(p["symbol"]).upper())
    for f in sorted((base / "fleet_manager" / "state").glob("*.json")):
        d = _read_json(f)
        pos = (d or {}).get("positions") if isinstance(d, dict) else None
        if isinstance(pos, dict):
            out += [str(k).upper() for k, v in pos.items() if _num(v) != 0]
        elif isinstance(pos, list):
            out += [str(p.get("symbol")).upper() for p in pos
                    if isinstance(p, dict) and p.get("symbol") and _num(p.get("qty")) != 0]
    return [t for t in dict.fromkeys(out) if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", t)]


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def newest(paths: Iterable[Path]) -> Optional[Path]:
    ps = sorted(paths, key=lambda p: p.name)
    return ps[-1] if ps else None


def digest_themes(opt: Path | None = None, limit: int = 12) -> list[dict]:
    """The newest world digest's themes: title, keywords, top tickers."""
    f = newest((opt_dir(opt) / "digest").glob("world_digest_*.json"))
    d = _read_json(f) if f else None
    out = []
    for t in (d or {}).get("themes") or [] if isinstance(d, dict) else []:
        if isinstance(t, dict) and str(t.get("title") or "").strip():
            out.append({"title": str(t["title"]).strip(),
                        "keywords": [str(k) for k in (t.get("keywords") or [])][:6],
                        "top_tickers": [str(k) for k in (t.get("top_tickers") or [])][:5],
                        "digest": f.name})
    return out[:limit]


def opportunity_names(opt: Path | None = None, list_id: str = "roi_v3",
                      limit: int = 30) -> list[str]:
    """The opportunities shortlist (`roi_v3`), by rank, EXCLUDED names left out."""
    f = newest((opt_dir(opt) / "opportunities").glob("opportunities_*.json"))
    d = _read_json(f) if f else None
    for L in (d or {}).get("lists") or [] if isinstance(d, dict) else []:
        if isinstance(L, dict) and L.get("list_id") == list_id:
            rows = [r for r in L.get("rows") or [] if isinstance(r, dict) and r.get("ticker")
                    and not str(r.get("eligibility") or "").upper().startswith("EXCLUDED")
                    and not r.get("is_etf")]
            rows.sort(key=lambda r: _num(r.get("rank")) if r.get("rank") is not None else 1e9)
            return [str(r["ticker"]).upper() for r in rows][:limit]
    return []


def seeds(opt: Path | None = None) -> dict:
    return {"held_names": held_names(opt), "themes": digest_themes(opt),
            "opportunities": opportunity_names(opt)}


# ════════════════════════════════ queries (pure) ═════════════════════════════

def clean_text(s: str, n: int = 160) -> str:
    """PURE. A query is plain words: no quotes, brackets or control text that
    could be read as an instruction inside the prompt."""
    return " ".join(_SAFE_TEXT.sub(" ", str(s or "")).split())[:n].strip()


def query_id(day: str, lane: str, tool: str, text: str) -> str:
    return hashlib.sha256(f"{day}|{lane}|{tool}|{text}".encode()).hexdigest()[:12]


def search_provider() -> Optional[str]:
    """The DECLARED OpenClaw search provider, or None (review 2026-10-06 F1).

    Agent search turns are issued ONLY when this is set. Measured 2026-10-06:
    `web_search` is allowed by the tool policy and has no provider behind it,
    and `x_search` is not offered at all. Configuring a provider is an owner
    decision (the audit's candidate, Brave, is card-gated; "no payments")."""
    v = _cfg("QUERY_PLANNER_SEARCH_PROVIDER", None)
    return str(v).strip() if v and str(v).strip() else None


def templates(lane: str, seed: Any, i: int, *, mode: str = "free",
              x_offered: bool = False) -> tuple[str, str]:
    """PURE. (tool, text) for the i-th query of a lane.

    `mode="agent"` (a provider is declared): `web_search`; every third held name
    is an `x_search` by cashtag ONLY when `x_offered`. `mode="free"` (no
    provider, the default): the $0 keyless sources -- `gnews_rss` (Google News
    RSS search) for every lane, and `edgar_fts` (EDGAR full-text search, the
    company's own 8-Ks) for every third held name and every second
    opportunity. Same seeds, same fixed wording, no LLM turn."""
    title = seed.get("title") if isinstance(seed, dict) else str(seed)
    kw = " ".join((seed.get("keywords") or [])[:2]) if isinstance(seed, dict) else ""
    if mode == "agent":
        if lane == "held_names":
            if i % 3 == 2 and x_offered:
                return "x_search", f"${seed}"
            return "web_search", f"{seed} stock news this week"
        if lane == "themes":
            return "web_search", f"{title} {kw} market impact".strip()
        return "web_search", f"{seed} stock catalyst news"
    if lane == "held_names":
        if i % 3 == 2:
            return "edgar_fts", str(seed)
        return "gnews_rss", f"{seed} stock"
    if lane == "themes":
        return "gnews_rss", f"{title} {kw}".strip()
    if i % 2 == 1:
        return "edgar_fts", str(seed)
    return "gnews_rss", f"{seed} stock catalyst"


def seed_key(lane: str, seed: Any) -> str:
    return f"{lane}:{seed.get('title') if isinstance(seed, dict) else seed}"


def budget() -> dict:
    return {"day": int(_cfg("QUERY_PLANNER_MAX_QUERIES_DAY", 24)),
            "run": int(_cfg("QUERY_PLANNER_MAX_QUERIES_RUN", 8)),
            "lanes": dict(_cfg("QUERY_PLANNER_LANE_QUERIES_DAY",
                               {"held_names": 12, "themes": 8, "opportunities": 4}))}


def plan_queries(sd: dict, *, day: str, ledger: list[dict], max_run: int | None = None,
                 bud: dict | None = None, mode: str = "free",
                 x_offered: bool = False) -> list[dict]:
    """PURE. The queries to issue now, within every budget.

    `ledger` is every earlier query row; today's rows count against the day and
    lane caps, and every earlier row orders the seeds (least recently searched
    first, never-searched before all). Lanes are interleaved so one run covers
    each lane before it covers any lane twice."""
    bud = bud or budget()
    today = [r for r in ledger if r.get("day") == day and r.get("status") != "PLANNED_ONLY"]
    left_day = max(0, int(bud["day"]) - len(today))
    left_run = min(left_day, int(bud["run"] if max_run is None else max_run))
    used = Counter(r.get("seed_lane") for r in today)
    issued = {r.get("query_id") for r in today}
    last: dict[str, str] = {}
    for r in ledger:
        k = str(r.get("seed_key") or "")
        if k and str(r.get("t") or "") > last.get(k, ""):
            last[k] = str(r.get("t") or "")
    per_lane: dict[str, list[dict]] = {}
    for lane in SEED_LANES:
        cap = max(0, int(bud["lanes"].get(lane, 0)) - used.get(lane, 0))
        items = list(sd.get(lane) or [])
        order = sorted(range(len(items)), key=lambda j: (last.get(seed_key(lane, items[j]), ""), j))
        qs = []
        n_lane = used.get(lane, 0)
        for j in order:
            if len(qs) >= cap:
                break
            tool, text = templates(lane, items[j], n_lane + len(qs), mode=mode,
                                   x_offered=x_offered)
            text = clean_text(text)
            if not text:
                continue
            qid = query_id(day, lane, tool, text)
            if qid in issued:
                continue
            seed = items[j].get("title") if isinstance(items[j], dict) else items[j]
            qs.append({"query_id": qid, "day": day, "seed_lane": lane, "seed": seed,
                       "seed_key": seed_key(lane, items[j]), "tool": tool, "text": text})
        per_lane[lane] = qs
    out: list[dict] = []
    while len(out) < left_run and any(per_lane.values()):
        for lane in SEED_LANES:
            if per_lane.get(lane) and len(out) < left_run:
                out.append(per_lane[lane].pop(0))
    return out


def prompt(q: dict, *, max_urls: int | None = None) -> str:
    n = int(max_urls or _cfg("QUERY_PLANNER_MAX_URLS_PER_QUERY", 6))
    return (
        "You are a read-only research helper for a personal investment notebook.\n"
        f"Call the {q['tool']} tool exactly once with this query: {q['text']}\n"
        "Do not call any other tool. Do not open, fetch or browse any page. Do not sign in, "
        "type into anything, post, or message anyone.\n"
        "Reply in English with ONLY a JSON object and no other text: "
        f'{{"urls": ["https://...", ...]}} listing up to {n} result URLs exactly as the tool '
        'returned them, most relevant first. If the tool returned nothing, reply {"urls": []}.\n')


def parse_urls(reply: str, *, max_urls: int | None = None) -> list[str]:
    """PURE. The URLs in a reply: the JSON object's `urls` when it parses, else
    every http(s) URL in the text. Trailing punctuation stripped, deduplicated."""
    n = int(max_urls or _cfg("QUERY_PLANNER_MAX_URLS_PER_QUERY", 6))
    txt = str(reply or "")
    found: list[str] = []
    if "{" in txt and "}" in txt:
        try:
            d = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
            if isinstance(d, dict) and isinstance(d.get("urls"), list):
                found = [str(u) for u in d["urls"] if isinstance(u, str)]
        except ValueError:
            found = []
    if not found:
        found = _URL_RE.findall(txt)
    out = []
    for u in found:
        u = u.strip().rstrip(".,;:!?)]}'\"")
        if u.lower().startswith(("http://", "https://")) and u not in out:
            out.append(u)
    return out[:n]


# ═══════════════════════════════ classifier (pure) ═══════════════════════════

def _on(host: str, domains: Iterable[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def classify_url(url: str) -> tuple[str, str]:
    """PURE (reads config). ('admitted' | 'quarantined' | 'refused', reason).

    Refused stays refused on every path: the browser's own NEVER_HOSTS (money,
    mail, message, broker, checkout providers), any checkout / payment PATH on
    any host (`browser_policy.money_url_refusal`), and the ToS / robots refusals
    of `QUERY_PLANNER_REFUSED_HOSTS`. Admitted = the reader's own allowlist
    (`web_reader.host_ok`). Anything else is a host nobody has reviewed:
    QUARANTINED, never queued and never auto-allowed."""
    from backend.services import browser_policy as BP
    from backend.services import web_reader as WR
    try:
        parts = urlsplit(str(url or "").strip())
        host = (parts.hostname or "").lower()
    except ValueError:
        return "refused", "unparseable URL"
    if parts.scheme not in ("http", "https") or not host:
        return "refused", "not an http(s) URL"
    if parts.username or parts.password:
        return "refused", "credentials in URL"
    if _on(host, WR.NEVER_HOSTS):
        return "refused", f"never host ({host}): bank / broker / payment / mail / message"
    why = BP.url_refusal(url) or BP.money_url_refusal(url)
    if why:
        return "refused", f"browser policy: {str(why).split(':')[0]}"
    if _on(host, tuple(_cfg("QUERY_PLANNER_REFUSED_HOSTS", ()))):
        return "refused", f"refused source ({host}): ToS / robots.txt / login wall / search page"
    if WR.host_ok(url):
        return "admitted", "allowlisted host"
    return "quarantined", f"new host ({host}): review before it is allowed"


# ═════════════════════════════════ the run ═══════════════════════════════════

def scope_preflight() -> dict:
    """The read-only tool scope, audited offline (config + 24 h of transcripts)."""
    from backend.services import openclaw_tool_scope as OTS
    r = OTS.audit(hours=24.0)
    return {"verdict": r.get("verdict"), "config_problems": r.get("config_problems"),
            "n_calls_24h": r.get("n_calls"), "n_violations_24h": r.get("n_violations"),
            "calls_by_tool_24h": r.get("calls_by_tool")}


def gateway_reachable() -> bool:
    from backend.services import gateway_repair as GR
    return bool(GR._port_open(GR._gw_host(), GR._gw_port()))


def session_tool_calls(session_id: str, since: datetime) -> Optional[list[dict]]:
    """Tool calls recorded for ONE session (None: the stores could not be read)."""
    from backend.services import openclaw_tool_scope as OTS
    calls, errors = OTS.tool_calls(OTS.default_home(), since - timedelta(seconds=5))
    if errors and not calls:
        return None
    return [c for c in calls if session_id in str(c.get("session") or "")]


_TOOL_ERR_TEXT = re.compile(r"Source: API\s*-{3}\s*(.*?)\s*<<<END_EXTERNAL", re.S)


def session_tool_errors(session_id: str, since: datetime) -> Optional[list[dict]]:
    """Tool RESULTS with `status: error` for ONE session, read-only from the
    agents' transcript stores: `[{tool, error}]` (None: unreadable).

    MEASURED 2026-10-06 on the first live run: `web_search` FIRED and answered
    `web_search is disabled or no provider is available.` -- allowed by the
    tool policy, with no search provider behind it. Without this read the
    receipt said QUERIES_RAN_NO_URLS, which blames the query, not the tool."""
    import sqlite3
    from backend.services import openclaw_tool_scope as OTS
    out: list[dict] = []
    since_ms = int((since - timedelta(seconds=5)).timestamp() * 1000)
    stores = OTS.transcript_stores(OTS.default_home())
    if not stores:
        return None
    for _aid, db in stores:
        try:
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10)
            try:
                keys = dict(con.execute("select current_session_id, session_key from "
                                        "session_nodes").fetchall())
                rows = con.execute("select session_id, event_json from transcript_events "
                                   "where created_at >= ?", (since_ms,)).fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            return None
        for sid, ej in rows:
            if session_id not in str(keys.get(sid, sid)):
                continue
            try:
                m = (json.loads(ej) or {}).get("message") or {}
            except ValueError:
                continue
            if m.get("role") != "toolResult":
                continue
            for it in m.get("content") or []:
                try:
                    d = json.loads(it.get("text") or "")
                except (ValueError, AttributeError, TypeError):
                    continue
                if isinstance(d, dict) and d.get("status") == "error":
                    err = str(d.get("error") or "")
                    mm = _TOOL_ERR_TEXT.search(err)
                    out.append({"tool": m.get("toolName") or d.get("tool"),
                                "error": (mm.group(1) if mm else err[-200:]).strip()[:200]})
    return out


def tool_unavailable(errors: Optional[list[dict]]) -> bool:
    """PURE. Every tool result says the tool is not usable: 'disabled / no
    provider' (measured on web_search) or 'not offered' (recorded for a turn
    whose tool never fired and returned nothing -- x_search, measured)."""
    return bool(errors) and all(any(w in str(e.get("error")) for w in
                                    ("disabled", "no provider", "not offered"))
                                for e in errors)


def _agent(msg_file: str, *, model: str, timeout: float, purpose: str, session_id: str) -> dict:
    from backend.services import openclaw_client as OC
    return OC.agent(msg_file, model=model, timeout=timeout, purpose=purpose,
                    session_id=session_id)


def _release(session_id: str) -> bool:
    from backend.services import openclaw_client as OC
    return OC.release_session(session_id)


def issue(q: dict, *, agent_fn: Callable[..., dict], tool_calls_fn: Callable[..., Any],
          release_fn: Callable[[str], bool] | None = None,
          tool_errors_fn: Callable[..., Any] | None = None) -> dict:
    """One query -> one agent turn -> its URLs and its own transcript's tool calls.

    The session id is OURS (so `agent` does not archive it before we read the
    transcript); it is released here afterwards. Review 2026-10-06 F4: in a
    planner turn ANY tool other than the query's own search tool is a
    violation (`web_fetch` included: it would reach a host `classify_url` never
    saw), and so is any call outside the read set."""
    from backend.services import openclaw_tool_scope as OTS
    sid = f"aegis-qp-{q['query_id']}-{uuid.uuid4().hex[:6]}"
    t0 = _now()
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(prompt(q))
        msg = fh.name
    try:
        res = agent_fn(msg, model=str(_cfg("QUERY_PLANNER_MODEL", "deepseek/deepseek-flash")),
                       timeout=float(_cfg("QUERY_PLANNER_TURN_TIMEOUT_S", 240.0)),
                       purpose=f"query_planner:{q['seed_lane']}:{q['query_id']}",
                       session_id=sid)
    except Exception as exc:                                        # noqa: BLE001
        res = {"status": "ERROR", "reply": "", "stderr": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        Path(msg).unlink(missing_ok=True)
    calls = tool_calls_fn(sid, t0)
    try:
        terrs = tool_errors_fn(sid, t0) if tool_errors_fn is not None else []
    except Exception:                                               # noqa: BLE001
        terrs = None
    released = None
    if release_fn is not None:
        try:
            released = bool(release_fn(sid))
        except Exception:                                           # noqa: BLE001
            released = False
    by_tool = Counter(c.get("tool") for c in (calls or []))
    bad = [c for c in (calls or []) if not OTS.is_read_call(c) or c.get("tool") != q["tool"]]
    fired = None if calls is None else bool(by_tool.get(q["tool"]))
    if fired is False and terrs == []:
        # the tool never fired AND left no result: it is not offered to the agent
        # (x_search, measured 2026-10-06). Recorded, so the row is not a silent zero.
        terrs = [{"tool": q["tool"], "error": "not offered: the agent fired no tool and the "
                                              "transcript holds no result for it"}]
    cost = res.get("priced_cost_usd")
    cost_known = cost is not None
    if cost is None:
        # no usage came back, or the model is unpriced: UNKNOWN, never zero
        cost = float(_cfg("QUERY_PLANNER_UNKNOWN_COST_USD", 0.03))
    return {"session_id": sid, "status": res.get("status"), "reply": res.get("reply") or "",
            "stderr": (res.get("stderr") or "")[:300], "call_id": res.get("call_id"),
            "tool_calls": None if calls is None else dict(by_tool),
            "tool_fired": fired,
            "violations": [f"{c.get('utc')} {c.get('tool')}" for c in bad],
            "tool_errors": terrs,
            "cost_usd": float(cost), "cost_known": cost_known, "released": released,
            "latency_s": res.get("latency_s")}


# ═══════════════════════════ the $0 keyless sources ══════════════════════════
#
# Review 2026-10-06 ("three things I would have done instead", 1): the query
# text is fixed by template, so an LLM turn is only a transport to a search
# tool that does not exist. These two are plain HTTP, keyless and $0:
# * Google News RSS search (`news.google.com/rss/search`) -- already an ADOPTED
#   source here (audit §C). Its item links are Google redirects and are NEVER
#   opened (google.com stays refused); what is used is the item's PUBLISHER
#   (`<source url=...>`) and HEADLINE: an allowlisted publisher with its own
#   search page becomes a navigation to that site's search for the headline
#   (`reader_scheduler.SEARCH_URLS`, the digest asks' mechanism -- never typing).
# * EDGAR full-text search (`efts.sec.gov`, the SEC's own API, through the one
#   SEC choke point `insider_form4._sec_get`): the company's own 8-Ks of the
#   last 7 days, filtered to filings whose display name carries `(<TICKER>)`;
#   the document URL is on sec.gov (an official, allowlisted host).

FREE_SOURCES: tuple[str, ...] = ("gnews_rss", "edgar_fts")
GNEWS_URL = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
EDGAR_FTS_URL = ("https://efts.sec.gov/LATEST/search-index?q=%22{t}%22&forms=8-K"
                 "&startdt={d0}&enddt={d1}")


def gnews_url(text: str) -> str:
    from urllib.parse import quote_plus
    return GNEWS_URL.format(q=quote_plus(f"{text} when:7d"))


def edgar_url(ticker: str, now: datetime) -> str:
    from urllib.parse import quote
    return EDGAR_FTS_URL.format(t=quote(ticker), d0=(now - timedelta(days=7)).date().isoformat(),
                                d1=now.date().isoformat())


def parse_gnews(raw: bytes, *, now: datetime, max_age_days: float = 7.0) -> list[dict]:
    """PURE. Google News RSS -> [{headline, publisher, publisher_url, published}],
    newest first, items older than `max_age_days` dropped. The redirect link is
    NOT returned: it is never opened."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    out = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        src = it.find("source")
        pub_name = (src.text or "").strip() if src is not None else ""
        pub_url = (src.get("url") or "").strip() if src is not None else ""
        try:
            t = parsedate_to_datetime(it.findtext("pubDate") or "")
            t = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            t = None
        if t is not None and (now - t).total_seconds() > max_age_days * 86400:
            continue
        if pub_name and title.endswith(" - " + pub_name):
            title = title[: -len(" - " + pub_name)].strip()
        if title and pub_url:
            out.append({"headline": title, "publisher": pub_name, "publisher_url": pub_url,
                        "published": t.isoformat() if t else None})
    out.sort(key=lambda r: r["published"] or "", reverse=True)
    return out


_PAREN = re.compile(r"\(([^)]*)\)")


def parse_edgar(data: dict, ticker: str) -> list[dict]:
    """PURE. EDGAR FTS JSON -> [{url, form, file_date, company}] for filings
    whose display name carries `(<TICKER>)` (the company's OWN filings)."""
    out = []
    t = str(ticker).upper()
    for h in ((data or {}).get("hits") or {}).get("hits") or []:
        src = h.get("_source") or {}
        names = [str(n) for n in src.get("display_names") or []]
        own = any(t in [x.strip().upper() for x in m.split(",")]
                  for n in names for m in _PAREN.findall(n))
        if not own:
            continue
        adsh = str(src.get("adsh") or "")
        fname = str(h.get("_id") or "").split(":", 1)[-1]
        ciks = src.get("ciks") or []
        if not (adsh and fname and ciks):
            continue
        try:
            cik = int(str(ciks[0]))
        except ValueError:
            continue
        out.append({"url": f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                           f"{adsh.replace('-', '')}/{fname}",
                    "form": src.get("form"), "file_date": src.get("file_date"),
                    "company": names[0] if names else None})
    return out


def _http_get(url: str) -> bytes:
    from scripts import news_pull as NP
    return NP._http_get(url)


def _sec_json(url: str) -> dict:
    from backend.services.insider_form4 import _sec_get
    return _sec_get(url).json()


def _site_for_host(host: str) -> Optional[str]:
    """The reader's own search-page site key for a publisher host, if any."""
    from backend.services import reader_scheduler as RS
    h = host.lower().removeprefix("www.")
    for site, tpl in RS.SEARCH_URLS.items():
        th = (urlsplit(tpl).hostname or "").lower().removeprefix("www.")
        if h == th or h.endswith("." + th):
            return site
    return None


def issue_free(q: dict, *, now: datetime, http_get: Callable[[str], bytes] | None = None,
               sec_json: Callable[[str], dict] | None = None) -> dict:
    """One $0 query -> candidate items (no LLM, no gateway)."""
    items: list[dict] = []
    status, err = "OK", None
    # the newest 3 x the per-query URL cap are classified (a Google News search
    # returns up to 100 items; classifying all of them only fills the quarantine)
    n_items = 3 * int(_cfg("QUERY_PLANNER_MAX_URLS_PER_QUERY", 6))
    try:
        if q["tool"] == "gnews_rss":
            for g in parse_gnews((http_get or _http_get)(gnews_url(q["text"])), now=now)[:n_items]:
                items.append({"kind": "headline", **g})
        elif q["tool"] == "edgar_fts":
            for e in parse_edgar((sec_json or _sec_json)(edgar_url(q["text"], now)), q["text"]):
                items.append({"kind": "article", **e})
        else:
            status, err = "ERROR", f"not a free source: {q['tool']}"
    except Exception as exc:                                        # noqa: BLE001
        status, err = "ERROR", f"{type(exc).__name__}: {exc}"[:300]
    return {"session_id": None, "status": status, "reply": "", "stderr": err or "",
            "call_id": None, "tool_calls": None,
            "tool_fired": status == "OK", "violations": [], "tool_errors": [],
            "cost_usd": 0.0, "cost_known": True, "released": None, "latency_s": None,
            "items": items}


def candidates(q: dict, r: dict) -> list[dict]:
    """PURE (reads config). The query's result -> [{url, kind, site?, headline?,
    verdict, reason}] BEFORE the day / duplicate / already-read checks."""
    out: list[dict] = []
    if q["tool"] == "gnews_rss":
        for g in r.get("items") or []:
            host = (urlsplit(g["publisher_url"]).hostname or "").lower()
            v, why = classify_url(f"https://{host}/") if host else ("refused", "no publisher")
            row = {"url": g["publisher_url"], "kind": "headline", "headline": g["headline"],
                   "publisher": g.get("publisher"), "published": g.get("published"),
                   "host": host}
            if v == "admitted":
                site = _site_for_host(host)
                if site is None:
                    v, why = "no_site_search", (f"publisher {host} is allowed but has no own "
                                                "search page here; the redirect is never opened")
                else:
                    from backend.services import reader_scheduler as RS
                    su = RS.search_url(site, g["headline"])
                    v, why = classify_url(su or "")
                    row.update(url=su, kind="search", site=site)
            out.append({**row, "verdict": v, "reason": why})
        return out
    if q["tool"] == "edgar_fts":
        for e in r.get("items") or []:
            v, why = classify_url(e["url"])
            out.append({"url": e["url"], "kind": "article", "form": e.get("form"),
                        "file_date": e.get("file_date"), "verdict": v, "reason": why})
        return out
    for u in parse_urls(r.get("reply") or ""):
        if r["tool_fired"] is False:
            v, why = "refused", "NO_TOOL_CALL: the search tool never fired; not a search result"
        elif r["tool_fired"] is None:
            v, why = "quarantined", "tool call unverifiable (transcript unreadable)"
        else:
            v, why = classify_url(u)
        from backend.services import web_reader as WR
        out.append({"url": u, "kind": "social" if WR.is_social(u) else "article",
                    "verdict": v, "reason": why})
    return out


def _norm(u: str) -> str:
    from backend.services import web_reader as WR
    return WR.norm_url(u)


def _stored_urls() -> set[str]:
    from backend.services import web_reader as WR
    return set(WR.stored_urls())


def admitted_today(day: str, opt: Path | None = None) -> int:
    return sum(1 for r in _read_jsonl(queue_path(opt)) if str(r.get("t") or "")[:10] == day)


def runs_log_path(opt: Path | None = None) -> Path:
    return dj_dir(opt) / "query_planner_runs.jsonl"


def lock_path(opt: Path | None = None) -> Path:
    return dj_dir(opt) / "query_planner.lock"


def acquire_lock(opt: Path | None = None, *, now: datetime | None = None,
                 max_age_s: float | None = None) -> Optional[dict]:
    """The single-run lock (review F3: never two planners at once). Returns the
    HOLDER when another run holds a fresh lock, else None (acquired). A lock
    older than QUERY_PLANNER_LOCK_MAX_S is stale (a crashed run) and is taken."""
    import os
    now = now or _now()
    lim = float(_cfg("QUERY_PLANNER_LOCK_MAX_S", 3600.0) if max_age_s is None else max_age_s)
    p = lock_path(opt)
    p.parent.mkdir(parents=True, exist_ok=True)
    held = _read_json(p)
    if isinstance(held, dict):
        t = _ts(held.get("t"))
        if t is not None and (now - t).total_seconds() < lim:
            return held
    p.write_text(json.dumps({"pid": os.getpid(), "t": now.isoformat(timespec="seconds")}),
                 encoding="utf-8")
    return None


def release_lock(opt: Path | None = None) -> None:
    import os
    held = _read_json(lock_path(opt))
    if isinstance(held, dict) and held.get("pid") == os.getpid():
        lock_path(opt).unlink(missing_ok=True)


def run(*, max_queries: int | None = None, due_only: bool = False, opt: Path | None = None,
        now: datetime | None = None, agent_fn: Callable[..., dict] | None = None,
        tool_calls_fn: Callable[..., Any] | None = None,
        release_fn: Callable[[str], bool] | None = None,
        tool_errors_fn: Callable[..., Any] | None = None,
        scope_fn: Callable[[], dict] | None = None,
        gateway_fn: Callable[[], bool] | None = None,
        seeds_fn: Callable[[], dict] | None = None,
        http_get: Callable[[str], bytes] | None = None,
        sec_json: Callable[[str], dict] | None = None,
        stored_fn: Callable[[], set] | None = None,
        provider: Any = "config", write: bool = True) -> dict:
    """Plan, issue, classify, queue; write the receipt. Never raises.

    A receipt is written only for a run that got past the STOP / enabled / due
    / lock checks (review F7); those four append ONE line to
    `dowjones/query_planner_runs.jsonl` instead."""
    now = now or _now()
    day = now.date().isoformat()
    run_id = f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    prov = search_provider() if provider == "config" else provider
    mode = "agent" if prov else "free"
    rec: dict = {"receipt": "query_planner", "run_id": run_id,
                 "generated_utc": now.isoformat(timespec="seconds"), "day": day,
                 "status": None, "refusal": None, "budget": budget(), "mode": mode,
                 "agent_search": ({"status": "ENABLED", "provider": prov} if prov else
                                  {"status": "REFUSED", "reason": (
                                      "NO_SEARCH_PROVIDER_DECLARED: no search provider declared;"
                                      " owner decision (QUERY_PLANNER_SEARCH_PROVIDER)")}),
                 "model": _cfg("QUERY_PLANNER_MODEL", "deepseek/deepseek-flash") if prov else None,
                 "licence": "PRODUCT_EXPERIMENT (reader input; no order, no claim)",
                 "queries": [], "totals": {}}
    ledger = _read_jsonl(ledger_path(opt))

    def log_only(status: str, why: str) -> dict:
        rec["status"], rec["refusal"] = status, why
        if write:
            _append_jsonl(runs_log_path(opt), [{"t": now.isoformat(timespec="seconds"),
                                                "status": status, "why": why}])
        return rec

    def done(status: str, refusal: str | None = None) -> dict:
        rec["status"], rec["refusal"] = status, refusal
        rec["totals"] = totals(rec["queries"])
        try:
            rec["yield"] = yield_report(now=now, opt=opt)
        except Exception as exc:                                    # noqa: BLE001
            rec["yield"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
        if write:
            rec["path"] = str(write_receipt(rec, opt))
            _append_jsonl(runs_log_path(opt), [{"t": now.isoformat(timespec="seconds"),
                                                "status": status, "why": refusal,
                                                "run_id": run_id, "mode": mode}])
        return rec

    if stop_path(opt).exists():
        return log_only("REFUSED", f"STOP file present: {stop_path(opt).name}")
    if not bool(_cfg("QUERY_PLANNER_ENABLED", True)):
        return log_only("REFUSED", "QUERY_PLANNER_ENABLED is False")
    if due_only:
        last = max((_ts(r.get("t")) for r in ledger if r.get("t")), default=None,
                   key=lambda t: t or datetime.min.replace(tzinfo=timezone.utc))
        every = float(_cfg("QUERY_PLANNER_EVERY_H", 6.0))
        if last is not None and (now - last).total_seconds() < every * 3600:
            return log_only("NOT_DUE", f"last query {last.isoformat(timespec='seconds')} "
                                       f"< {every:g} h ago")
    if write:
        holder = acquire_lock(opt, now=now)
        if holder is not None:
            return log_only("ALREADY_RUNNING", f"another planner holds the lock: {holder}")
    try:
        return _run_locked(rec, done, ledger=ledger, mode=mode, now=now, day=day, opt=opt,
                           run_id=run_id, max_queries=max_queries, agent_fn=agent_fn,
                           tool_calls_fn=tool_calls_fn, release_fn=release_fn,
                           tool_errors_fn=tool_errors_fn, scope_fn=scope_fn,
                           gateway_fn=gateway_fn, seeds_fn=seeds_fn, http_get=http_get,
                           sec_json=sec_json, stored_fn=stored_fn, write=write)
    finally:
        if write:
            release_lock(opt)


def _run_locked(rec: dict, done: Callable[..., dict], *, ledger: list[dict], mode: str,
                now: datetime, day: str, opt: Path | None, run_id: str,
                max_queries: int | None, agent_fn, tool_calls_fn, release_fn, tool_errors_fn,
                scope_fn, gateway_fn, seeds_fn, http_get, sec_json, stored_fn,
                write: bool) -> dict:
    if mode == "free" and not bool(_cfg("QUERY_PLANNER_FREE_SOURCES_ENABLED", True)):
        return done("REFUSED", rec["agent_search"]["reason"]
                    + "; and the $0 sources are switched off")
    sd = (seeds_fn or seeds)()
    rec["seeds"] = {k: len(v or []) for k, v in sd.items()}
    plan = plan_queries(sd, day=day, ledger=ledger, max_run=max_queries, mode=mode,
                        x_offered=bool(_cfg("QUERY_PLANNER_X_SEARCH_OFFERED", False)))
    rec["planned"] = len(plan)
    if not plan:
        return done("NOTHING_TO_DO", "no query left inside today's budget (or no seeds)")
    if mode == "agent":
        try:
            scope = (scope_fn or scope_preflight)()
        except Exception as exc:                                    # noqa: BLE001
            scope = {"verdict": "CANNOT_DETERMINE",
                     "error": f"{type(exc).__name__}: {exc}"[:200]}
        rec["scope_before"] = scope
        if scope.get("verdict") != "OK":
            return done("REFUSED", f"read-only tool scope is {scope.get('verdict')}: "
                                   f"{scope.get('config_problems') or scope.get('error') or ''}"[:300])
        try:
            gw = (gateway_fn or gateway_reachable)()
        except Exception:                                           # noqa: BLE001
            gw = False
        if not gw:
            return done("REFUSED", "OpenClaw gateway not reachable on its loopback port")
        agent_fn = agent_fn or _agent
        tool_calls_fn = tool_calls_fn or session_tool_calls
        if release_fn is None and agent_fn is _agent:
            release_fn = _release
        if tool_errors_fn is None and agent_fn is _agent:
            tool_errors_fn = session_tool_errors
    cap = float(_cfg("QUERY_PLANNER_RUN_USD_CAP", 0.30))
    max_adm = int(_cfg("QUERY_PLANNER_MAX_ADMITTED_DAY", 120))
    per_q = int(_cfg("QUERY_PLANNER_MAX_URLS_PER_QUERY", 6))
    n_adm_today = admitted_today(day, opt)
    queued_before = {_norm(str(r.get("url") or "")) for r in _read_jsonl(queue_path(opt))}
    try:
        stored = (stored_fn or _stored_urls)()
    except Exception:                                               # noqa: BLE001
        stored = set()
    spent = 0.0
    stop_reason = None
    for q in plan:
        if spent >= cap:
            stop_reason = f"run USD cap {cap:g} reached ({spent:.4f})"
            break
        if q["tool"] in FREE_SOURCES:
            r = issue_free(q, now=now, http_get=http_get, sec_json=sec_json)
        else:
            r = issue(q, agent_fn=agent_fn, tool_calls_fn=tool_calls_fn,
                      release_fn=release_fn, tool_errors_fn=tool_errors_fn)
        spent += r["cost_usd"]
        rows = candidates(q, r)
        n_q = 0
        for x in rows:
            if x["verdict"] != "admitted":
                continue
            nu = _norm(x["url"])
            if nu in queued_before:
                x["verdict"], x["reason"] = "duplicate", "already queued by an earlier query"
            elif x["kind"] != "search" and nu in stored:
                # review F2: the fixed reader already read it -- not planner novelty
                x["verdict"], x["reason"] = "already_read", "the reader already stored this page"
            elif n_q >= per_q:
                x["verdict"], x["reason"] = "deferred", f"{per_q} URLs per query"
            elif n_adm_today >= max_adm:
                x["verdict"], x["reason"] = "deferred", (f"QUERY_PLANNER_MAX_ADMITTED_DAY "
                                                         f"{max_adm} reached")
            else:
                n_adm_today += 1
                n_q += 1
                queued_before.add(nu)
        stamp = _now().isoformat(timespec="seconds")
        qrow = {**q, "t": stamp, "run_id": run_id, "status": r["status"],
                "session_id": r["session_id"], "call_id": r["call_id"],
                "tool_calls": r["tool_calls"], "tool_fired": r["tool_fired"],
                "violations": r["violations"], "tool_errors": r["tool_errors"],
                "tool_unavailable": tool_unavailable(r["tool_errors"]),
                "cost_usd": round(r["cost_usd"], 6),
                "cost_known": r["cost_known"], "released": r["released"],
                "n_urls": len(rows), "urls": rows,
                "error": r["stderr"] if r["status"] != "OK" else None}
        rec["queries"].append(qrow)
        if write:
            _append_jsonl(ledger_path(opt), [{k: v for k, v in qrow.items() if k != "urls"}
                                             | {"verdicts": dict(Counter(x["verdict"] for x in rows))}])
            _append_jsonl(queue_path(opt), [
                {"t": stamp, "first_seen_utc": stamp, "query_id": q["query_id"],
                 "discovered_via": q["tool"], "url": x["url"], "kind": x["kind"],
                 "site": x.get("site"), "headline": x.get("headline"),
                 "seed_lane": q["seed_lane"], "seed": q["seed"], "question": q["text"],
                 "run_id": run_id}
                for x in rows if x["verdict"] == "admitted"])
            _append_jsonl(quarantine_path(opt), [
                {"t": stamp, "first_seen_utc": stamp, "query_id": q["query_id"],
                 "discovered_via": q["tool"], "url": x["url"],
                 "host": x.get("host") or (urlsplit(x["url"]).hostname or "").lower(),
                 "headline": x.get("headline"), "reason": x["reason"],
                 "run_id": run_id, "review": "PENDING: a human allows or refuses this host"}
                for x in {(x.get("host") or (urlsplit(x["url"]).hostname or "").lower()): x
                          for x in rows if x["verdict"] == "quarantined"}.values()])
        if r["violations"]:
            stop_reason = f"SCOPE_VIOLATION: {r['violations'][:3]} -- run stopped"
            break
    rec["spent_usd"] = round(spent, 6)
    if stop_reason and stop_reason.startswith("SCOPE_VIOLATION"):
        return done("REFUSED", stop_reason)
    if mode == "agent":
        try:
            rec["scope_after"] = (scope_fn or scope_preflight)()
        except Exception as exc:                                    # noqa: BLE001
            rec["scope_after"] = {"verdict": "CANNOT_DETERMINE", "error": str(exc)[:200]}
    return done("OK", stop_reason)


def totals(queries: list[dict]) -> dict:
    """PURE. Counts over one run's query rows, overall and per seed lane / tool."""
    def blank() -> dict:
        return {"queries": 0, "tool_fired": 0, "tool_unverified": 0, "tool_unavailable": 0,
                "urls": 0, "admitted": 0, "quarantined": 0, "refused": 0, "duplicate": 0,
                "already_read": 0, "deferred": 0, "no_site_search": 0, "cost_usd": 0.0}
    out, by_lane, by_tool = blank(), defaultdict(blank), defaultdict(blank)
    for q in queries:
        for b in (out, by_lane[q.get("seed_lane")], by_tool[q.get("tool")]):
            b["queries"] += 1
            b["tool_fired"] += int(q.get("tool_fired") is True)
            b["tool_unverified"] += int(q.get("tool_fired") is None)
            b["tool_unavailable"] += int(bool(q.get("tool_unavailable")))
            b["urls"] += int(q.get("n_urls") or 0)
            b["cost_usd"] = round(b["cost_usd"] + float(q.get("cost_usd") or 0.0), 6)
            for x in q.get("urls") or []:
                b[x["verdict"]] = b.get(x["verdict"], 0) + 1
    out["tool_calls_web_search"] = sum((q.get("tool_calls") or {}).get("web_search", 0)
                                       for q in queries)
    out["tool_calls_x_search"] = sum((q.get("tool_calls") or {}).get("x_search", 0)
                                     for q in queries)
    out["by_seed_lane"] = dict(by_lane)
    out["by_tool"] = dict(by_tool)
    return out


def write_receipt(rec: dict, opt: Path | None = None) -> Path:
    p = dj_dir(opt) / f"query_planner_{rec['run_id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    tmp.replace(p)
    return p


# ═══════════════════════════════ the yield (files only) ══════════════════════

def zero_kind(*, queries: int, tool_fired: int, urls: int, admitted: int, pages: int,
              claims: int, forecasts: int, tool_unavailable: int = 0) -> str:
    """PURE. WHICH zero (or YIELDING), so '0 claims' never hides 'no query ran'."""
    if queries == 0:
        return "NO_QUERIES_RAN"
    if urls == 0 and tool_unavailable > 0 and tool_unavailable >= tool_fired:
        return "TOOL_FIRED_BUT_UNAVAILABLE"
    if tool_fired == 0 and urls == 0:
        return "QUERIES_RAN_NO_TOOL_CALL"
    if urls == 0:
        return "QUERIES_RAN_NO_URLS"
    if admitted == 0:
        return "URLS_FOUND_NONE_ADMITTED"
    if pages == 0:
        return "ADMITTED_NOT_YET_READ"
    if claims == 0:
        return "PAGES_READ_NO_CLAIMS"
    if forecasts == 0:
        return "CLAIMS_NO_FORECASTS"
    return "YIELDING"


def _host(u: str) -> str:
    """The bare host of a URL WITH a scheme (review F6: a scheme-less
    normalised URL has no hostname, so every claim fell into one '' bucket)."""
    u = str(u or "")
    if u and "://" not in u:
        u = "https://" + u
    try:
        return (urlsplit(u).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _pred_claim_rows(od: Path) -> list[tuple[str, str]] | None:
    """(made_at, claim_hash) for every forecast row that carries a claim hash,
    cached in `dowjones/query_planner_pred_cache.json` keyed by the ledger's
    size and mtime (review F7: the 50 MB ledger is read once per change, not
    once per launch). None when the ledger REFUSED (an unreadable migration
    marker): that is "unknown", and must not print as zero forecasts."""
    from backend.services import forecast_ledger as FL
    pred = od / "predictions.jsonl"
    cache = od / "dowjones" / "query_planner_pred_cache.json"
    try:
        if not FL.exists(pred):
            return []
        # keyed on every backing file: the legacy file, or the monthly streams
        stamp = ":".join(str(x) for x in FL.fingerprint(pred))
    except FL.ForecastLedgerError:
        return None
    except OSError:
        return []
    c = _read_json(cache)
    if isinstance(c, dict) and c.get("stamp") == stamp:
        return [tuple(x) for x in c.get("rows") or []]
    rows: list[tuple[str, str]] = []
    for ln in FL.logical_lines(pred, contains='"claim_hash"'):
        if '"claim_hash"' not in ln:
            continue
        try:
            p = json.loads(ln)
        except ValueError:
            continue
        ch = (p.get("inputs_used") or {}).get("claim_hash")
        if ch and p.get("made_at"):
            rows.append((str(p["made_at"]), str(ch)))
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"stamp": stamp, "rows": rows}), encoding="utf-8")
        tmp.replace(cache)
    except OSError:
        pass
    return rows


def yield_report(*, now: datetime | None = None, window_h: float = 24.0,
                 opt: Path | None = None) -> dict:
    """Queries -> URLs -> pages read -> claims -> forecast rows, for the planner
    and for the fixed reader in the same window. Files only.

    ATTRIBUTION IS RECORDED, NEVER INFERRED (review 2026-10-06 F2):
    * a planner page is a page-log row whose lane is `qp:<query_id>` AND whose
      time is at or after that query's issue time; a page the fixed lanes had
      already read earlier in the window is counted as `pages_already_read`
      and NOT as planner yield;
    * a planner claim is a `sources/claims.jsonl` row carrying `query_id` (or a
      `reader_lane` of `qp:`), stamped when the claim was WRITTEN from the
      stored article's `reached_by`;
    * forecast rows follow the claim hash.
    The comparison the review asks for is on the receipt: claims per page for
    planner pages vs fixed-lane pages ON THE SAME HOSTS in the same window."""
    now = now or _now()
    since = now - timedelta(hours=window_h)
    od = opt_dir(opt)
    all_led = _read_jsonl(ledger_path(opt))
    led = [r for r in all_led if (_ts(r.get("t")) or since) >= since]
    q_by_id = {r.get("query_id"): r for r in all_led}
    vc = Counter()
    for r in led:
        for k, v in (r.get("verdicts") or {}).items():
            vc[k] += int(v or 0)
    q_tot = {"queries": len(led),
             "tool_fired": sum(1 for r in led if r.get("tool_fired") is True),
             "tool_unavailable": sum(1 for r in led if r.get("tool_unavailable")),
             "urls": sum(int(r.get("n_urls") or 0) for r in led),
             **{k: vc.get(k, 0) for k in ("admitted", "quarantined", "refused", "duplicate",
                                          "already_read", "deferred", "no_site_search")},
             "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in led), 6)}
    adm_or_read = q_tot["admitted"] + q_tot["already_read"]
    q_tot["share_already_read"] = (round(q_tot["already_read"] / adm_or_read, 4)
                                   if adm_or_read else None)

    def blank() -> dict:
        return {"pages_read": 0, "pages_ok": 0, "claims": 0, "forecast_rows": 0}
    pl, other = blank(), blank()
    pl_lane, pl_tool, pl_host = defaultdict(blank), defaultdict(blank), defaultdict(blank)
    ot_host = defaultdict(blank)
    fixed_first: dict[str, datetime] = {}
    pages_before_query = pages_already_read = 0
    rows = []
    for r in _read_jsonl(od / "dowjones" / "page_log.jsonl"):
        t = _ts(r.get("t"))
        if t is not None and t >= since:
            rows.append((t, r))
    rows.sort(key=lambda x: x[0])
    for t, r in rows:
        u = _norm(str(r.get("url") or ""))
        lane = str(r.get("lane") or "")
        h = _host(str(r.get("url") or "")) or str(r.get("host") or "").removeprefix("www.")
        ok = int(str(r.get("class") or "") == "OK")
        if lane.startswith("qp:"):
            qid = lane[3:]
            ql = q_by_id.get(qid) or {}
            issued = _ts(ql.get("t"))
            if issued is None or t < issued:
                pages_before_query += 1
                continue
            if u in fixed_first and fixed_first[u] <= t:
                pages_already_read += 1
                continue
            for b in (pl, pl_lane[ql.get("seed_lane")], pl_tool[ql.get("tool")], pl_host[h]):
                b["pages_read"] += 1
                b["pages_ok"] += ok
        else:
            fixed_first.setdefault(u, t)
            for b in (other, ot_host[h]):
                b["pages_read"] += 1
                b["pages_ok"] += ok
    pl_claims: dict[str, dict] = {}
    ot_claims: dict[str, str] = {}
    for c in _read_jsonl(od / "sources" / "claims.jsonl"):
        t = _ts(c.get("observed_utc"))
        if t is None or t < since:
            continue
        h = _host(str(c.get("post_url") or ""))
        lane = str(c.get("reader_lane") or "")
        qid = c.get("query_id") or (lane[3:] if lane.startswith("qp:") else None)
        if qid:
            ql = q_by_id.get(qid) or {}
            m = {"seed_lane": ql.get("seed_lane"), "tool": ql.get("tool"), "host": h}
            for b in (pl, pl_lane[m["seed_lane"]], pl_tool[m["tool"]], pl_host[h]):
                b["claims"] += 1
            pl_claims[str(c.get("claim_hash"))] = m
        else:
            other["claims"] += 1
            ot_host[h]["claims"] += 1
            ot_claims[str(c.get("claim_hash"))] = h
    claim_rows = _pred_claim_rows(od)
    ledger_refused = claim_rows is None
    for made, ch in claim_rows or []:
        t = _ts(made)
        if t is None or t < since:
            continue
        if ch in pl_claims:
            m = pl_claims[ch]
            for b in (pl, pl_lane[m["seed_lane"]], pl_tool[m["tool"]], pl_host[m["host"]]):
                b["forecast_rows"] += 1
        else:
            other["forecast_rows"] += 1
            if ch in ot_claims:
                ot_host[ot_claims[ch]]["forecast_rows"] += 1
    # the review's measurement: the planner's marginal claim rate vs what the
    # fixed reader earns per page on the SAME hosts in the SAME window
    same = sorted(h for h in pl_host if h and ot_host.get(h, {}).get("pages_read"))
    pp = sum(pl_host[h]["pages_read"] for h in same)
    pc = sum(pl_host[h]["claims"] for h in same)
    fp = sum(ot_host[h]["pages_read"] for h in same)
    fc = sum(ot_host[h]["claims"] for h in same)
    rate = {"hosts": same,
            "planner_pages": pp, "planner_claims": pc,
            "planner_claims_per_page": round(pc / pp, 4) if pp else None,
            "fixed_pages": fp, "fixed_claims": fc,
            "fixed_claims_per_page": round(fc / fp, 4) if fp else None,
            "pages_before_query_excluded": pages_before_query,
            "pages_already_read_excluded": pages_already_read}
    zk = zero_kind(queries=q_tot["queries"], tool_fired=q_tot["tool_fired"], urls=q_tot["urls"],
                   admitted=q_tot["admitted"], pages=pl["pages_read"],
                   claims=pl["claims"], forecasts=pl["forecast_rows"],
                   tool_unavailable=q_tot["tool_unavailable"])
    return {"window_h": window_h, "since_utc": since.isoformat(timespec="seconds"),
            "zero_kind": zk, "queries": q_tot,
            "planner": {**pl, "by_seed_lane": dict(pl_lane), "by_tool": dict(pl_tool),
                        "by_host": dict(pl_host)},
            "non_planner": {**other, "by_host_top": dict(sorted(
                ot_host.items(), key=lambda kv: -kv[1]["pages_read"])[:12])},
            "claims_per_page_same_hosts": rate,
            # True when the forecast ledger refused to answer: every
            # forecast_rows count above is then UNKNOWN, not zero.
            "forecast_rows_unknown": ledger_refused,
            "line": yield_line(zk, q_tot, pl, other, window_h, rate)
                    + (" [forecast_rows UNKNOWN: the forecast ledger refused]" if ledger_refused
                       else "")}


def yield_line(zk: str, q: dict, pl: dict, other: dict, window_h: float,
               rate: dict | None = None) -> str:
    rate = rate or {}
    return (f"query_planner {window_h:g}h: {zk} -- {q['queries']} queries "
            f"({q['tool_fired']} answered, {q.get('tool_unavailable', 0)} tool "
            f"unavailable), {q['urls']} URLs, {q['admitted']} admitted / "
            f"{q['quarantined']} quarantined / {q['refused']} refused / "
            f"{q.get('already_read', 0)} already read (share {q.get('share_already_read')}); "
            f"planner pages {pl['pages_read']} -> claims {pl['claims']} -> forecasts "
            f"{pl['forecast_rows']}; non-planner pages {other['pages_read']} -> claims "
            f"{other['claims']} -> forecasts {other['forecast_rows']}; claims/page same hosts "
            f"planner {rate.get('planner_claims_per_page')} vs fixed "
            f"{rate.get('fixed_claims_per_page')}; spend ${q['cost_usd']:.4f}")


# ═══════════════════════════════════ CLI ═════════════════════════════════════

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="print the queries, run nothing")
    g.add_argument("--run", action="store_true", help="issue the queries now")
    g.add_argument("--yield", dest="yld", action="store_true", help="the yield, files only")
    ap.add_argument("--max", type=int, default=None, help="queries this run (<= run cap)")
    ap.add_argument("--due", action="store_true", help="only when QUERY_PLANNER_EVERY_H passed")
    ap.add_argument("--window-h", type=float, default=24.0)
    ap.add_argument("--dry", action="store_true",
                    help="with --run: issue the $0 queries but write NOTHING (no ledger, "
                         "queue, quarantine or receipt) and never open an agent turn")
    a = ap.parse_args(argv)
    if a.plan:
        now = _now()
        p = plan_queries(seeds(), day=now.date().isoformat(), ledger=_read_jsonl(ledger_path()),
                         max_run=a.max, mode="agent" if search_provider() else "free",
                         x_offered=bool(_cfg("QUERY_PLANNER_X_SEARCH_OFFERED", False)))
        print(json.dumps(p, indent=2))
        return 0
    if a.yld:
        print(json.dumps(yield_report(window_h=a.window_h), indent=2, default=str))
        return 0
    if a.dry:
        rec = run(max_queries=a.max, due_only=a.due, provider=None, write=False)
        print(json.dumps(rec, indent=2, default=str))
        return 0
    rec = run(max_queries=a.max, due_only=a.due)
    print(json.dumps({k: rec.get(k) for k in ("status", "refusal", "run_id", "path", "planned",
                                              "spent_usd", "totals")}, indent=2, default=str))
    print((rec.get("yield") or {}).get("line"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
