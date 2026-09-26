"""Chunk B -- seed the source registry, discover X handles, read them, score them.

    python -m scripts.source_reads --seed            # corpus + filings + brokerages
    python -m scripts.source_reads --discover        # <= 8 OpenClaw X quests, one per theme
    python -m scripts.source_reads --seed-timelines  # reviewer specialists + company handles
    python -m scripts.source_reads --read            # X handle TIMELINES (<= 15 quests, <= $1.20)
    python -m scripts.source_reads --score           # scoreboard_<date>.json + SOURCES.md (+ brokers)
    python -m scripts.source_reads --grade-promises  # numbered promises vs the 8-K EX-99, no LLM

Social is an ATTENTION layer, never a truth layer and never an order: every
dated claim becomes a `web_events` row and a `source:<id>` forecast row, and the
source earns (or does not earn) a weight from how those rows grade. A source
whose read returns nothing dated is logged `EMPTY_READ`; a source the quest cap
did not reach is logged `NOT_READ_CAP`. Nothing is skipped silently.

Read-only on X: the prompt forbids posting, liking, following, replying and DMs.
This script never imports the broker.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from backend import config as _config  # noqa: E402
from backend.services import source_registry as SR  # noqa: E402


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


SOURCE_READS_DAILY_CAP_USD: float = float(_cfg("SOURCE_READS_DAILY_CAP_USD", 1.0))
SOURCE_READS_MAX_QUESTS: int = int(_cfg("SOURCE_READS_MAX_QUESTS", 20))
SOURCE_DISCOVERY_CAP_USD: float = float(_cfg("SOURCE_DISCOVERY_CAP_USD", 1.0))
SOURCE_DISCOVERY_MAX_QUESTS: int = int(_cfg("SOURCE_DISCOVERY_MAX_QUESTS", 8))
SOURCE_READS_MODEL: str = str(_cfg("SOURCE_READS_MODEL", "deepseek/deepseek-flash"))
HANDLES_PER_QUEST: int = int(_cfg("SOURCE_READS_HANDLES_PER_QUEST", 5))
QUEST_TIMEOUT_S: float = float(_cfg("SOURCE_READS_TIMEOUT_S", 420.0))
UNKNOWN_COST_ESTIMATE_USD: float = float(_cfg("SOURCE_READS_UNKNOWN_COST_USD", 0.06))
READ_PURPOSE = "source_read"
DISCOVERY_PURPOSE = "source_discovery"

PC_SNAPSHOT = REPO / "backend" / "data" / "optimus" / "paper_accounts" / "pc_snapshot" / "state_latest.json"
MURAT_BOOK = REPO / "backend" / "data" / "murat_book.yaml"
LLM_BOOKS = REPO / "backend" / "data" / "optimus" / "llm_portfolio" / "books.jsonl"
_NOT_NAMES = {"CASH", "SPY", "QQQ", "SMH", "XBI", "URA", "IWM", "TLT", "GLD", "SOXX",
              "XLE", "XLK", "XLV", "XLF", "IBB", "ARKK", "DIA", "VTI", "VOO"}

#: theme -> (description for the quest, tickers from our books it covers)
THEMES: dict[str, tuple[str, tuple[str, ...]]] = {
    "ai_power": ("AI data-centre power, grid, nuclear/uranium and electrical equipment",
                 ("GEV", "NVT", "CCJ", "AMSC", "VRT", "GRID")),
    "memory_semis": ("memory, semiconductors, semicap and quantum computing",
                     ("MU", "NVDA", "TSM", "ASML", "AMD", "TER", "AMAT", "QUBT")),
    "biotech": ("biotech and pharma (gene editing, rare disease, oncology, immunology)",
                ("VRTX", "INCY", "JAZZ", "ABSI", "BHVN", "KYTX", "NTLA", "MRK", "AARD")),
    "gambling_prediction_markets": ("online sports betting, iGaming and prediction markets (Kalshi, Polymarket)",
                                    ("DKNG",)),
    "defence": ("defence primes, European defence and military technology",
                ("RHM.DE", "SAAB-B.ST", "KOG.OL", "LMT", "NOC")),
    "megacap_ir_ceo": ("the official company / investor-relations accounts and public CEOs of mega-cap tech",
                       ("AAPL", "AMZN", "GOOGL", "META", "NVDA")),
    "smallcap_ir_ceo": ("the official company / investor-relations accounts and public CEOs/founders of these small and mid caps",
                        ("ALLE", "AVPT", "SNDR", "HUBS", "PRCH", "SOC", "SLDP", "INCY", "JAZZ")),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────── tickers in our books ───────────────────────
def book_tickers(limit: int = 40) -> list[str]:
    """The names our books hold: PC paper positions, Murat's book, then the most
    held names across the LLM books. US tickers only (the X quest reads $TICKER)."""
    out: list[str] = []

    def add(t: Any) -> None:
        t = str(t or "").upper().strip()
        if re.fullmatch(r"[A-Z]{1,5}", t) and t not in _NOT_NAMES and t not in out:
            out.append(t)

    try:
        for p in json.loads(PC_SNAPSHOT.read_text(encoding="utf-8")).get("positions") or []:
            add(p.get("symbol") or p.get("ticker"))
    except (OSError, ValueError):
        pass
    try:
        for p in (yaml.safe_load(MURAT_BOOK.read_text(encoding="utf-8")) or {}).get("positions") or []:
            add(p.get("ticker"))
    except (OSError, ValueError):
        pass
    counts: dict[str, int] = {}
    try:
        for line in LLM_BOOKS.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            for k in ("positions", "holdings", "weights"):
                v = r.get(k)
                keys = (v.keys() if isinstance(v, dict) else
                        [x.get("ticker") if isinstance(x, dict) else x for x in v]
                        if isinstance(v, list) else [])
                for t in keys:
                    counts[str(t).upper()] = counts.get(str(t).upper(), 0) + 1
    except OSError:
        pass
    for t, _ in sorted(counts.items(), key=lambda kv: -kv[1]):
        if len(out) >= limit:
            break
        add(t)
    return out[:limit]


# ─────────────────────────────── the OpenClaw call ──────────────────────────
def _price(usage: dict) -> float:
    pr = getattr(_config, "LLM_PRICE_PER_MTOK", {}).get("deepseek-flash") or {
        "in": 0.169413, "cached_in": 0.00338826, "out": 1.284835}
    return ((usage.get("input") or 0) * pr["in"] + (usage.get("cache_read") or 0) * pr["cached_in"]
            + (usage.get("output") or 0) * pr["out"]) / 1e6


def openclaw_turn(prompt: str, *, purpose: str, model: str = SOURCE_READS_MODEL,
                  timeout: float = QUEST_TIMEOUT_S) -> dict:
    from backend.services import openclaw_client as OC
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(prompt)
        msg = fh.name
    t0 = time.time()
    try:
        res = OC.agent(msg, model=model, timeout=timeout, purpose=purpose)
    except Exception as exc:                                        # noqa: BLE001
        res = {"status": "ERROR", "reply": "", "stderr": f"{type(exc).__name__}: {exc}", "usage": {}}
    finally:
        Path(msg).unlink(missing_ok=True)
    usage = res.get("usage") or {}
    ours = _price(usage)
    theirs = res.get("openclaw_cost_usd")
    try:
        theirs = float(theirs) if theirs is not None else None
    except (TypeError, ValueError):
        theirs = None
    unknown = not usage and theirs is None and res.get("status") != "OK"
    if unknown:
        # a TIMEOUT / RC_NONZERO returns no usage: the spend is UNKNOWN, not zero,
        # so the cap charges a conservative estimate and the receipt says so.
        ours = UNKNOWN_COST_ESTIMATE_USD
    return {"status": res.get("status"), "reply": res.get("reply") or "",
            "cost_unknown": unknown,
            "stderr": (res.get("stderr") or "")[:400], "usage": usage,
            "cost_usd": max(ours, theirs or 0.0), "cost_ours_usd": round(ours, 6),
            "cost_openclaw_usd": theirs, "elapsed_s": round(time.time() - t0, 1),
            "call_id": res.get("call_id")}


def extract_json(text: str) -> Any:
    """The last JSON object/array in a reply (fenced or bare). None if none parses."""
    if not text:
        return None
    for m in reversed(list(re.finditer(r"```(?:json)?\s*(.*?)```", text, re.S))):
        try:
            return json.loads(m.group(1))
        except ValueError:
            continue
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = text.find(opener), text.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except ValueError:
                continue
    return None


def blocker_of(data: Any) -> str | None:
    """The quest's own 'I could not read the page' -- a login wall is a refusal,
    never 'found 0'. None when the page was read."""
    if isinstance(data, dict) and data.get("searched") is False:
        return str(data.get("blocker") or "searched=false with no reason")[:400]
    return None


def is_login_wall(blocker: str | None) -> bool:
    b = (blocker or "").lower()
    return any(k in b for k in ("login", "log in", "logged out", "not logged", "signed out",
                                "sign-in", "authenticat", "onboarding"))


READ_ONLY = ("READ-ONLY. You are using Murat's logged-in X account in the browser. Do NOT "
             "post, reply, like, repost, follow, bookmark, or send any message. Do not open "
             "any brokerage, bank or payment site. Only read.")


# ─────────────────────────────── discovery ──────────────────────────────────
def discovery_url(theme: str, tickers: tuple[str, ...]) -> str:
    """ONE concrete page per quest (an open-ended 'go find accounts' timed out at
    600s on 2026-09-26; chunk A's one-URL X reads finish in 1-2 minutes)."""
    from urllib.parse import quote
    us = [t for t in tickers if re.fullmatch(r"[A-Z]{1,5}", t)] or list(tickers)
    q = " OR ".join("$" + t for t in us[:8])
    return f"https://x.com/search?q={quote(q)}&f=top"


def discovery_prompt(theme: str, desc: str, tickers: tuple[str, ...]) -> str:
    url = discovery_url(theme, tickers)
    return f"""{READ_ONLY}

Use the browser tool with the logged-in X account. Open {url}
and read the results (scroll once or twice). Theme: {desc}.

From the posts you see, list up to 10 distinct AUTHORS worth tracking as sources on this
theme, and classify each author's kind as one of: company, ceo_founder, sell_side,
industry_specialist, engineer_researcher, journalist, fund_manager, retail_influencer,
government_regulatory. Only authors you actually saw on the page; never invent a handle.

Reply with ONLY one JSON object, no prose:
{{"theme": "{theme}", "searched": true, "blocker": "",
"accounts": [{{"handle": "@example", "name": "display name", "kind": "industry_specialist",
"tickers": ["TICKER"], "why": "one line",
"latest_post_url": "https://x.com/example/status/123", "latest_post_utc": "2026-09-25T14:03:00Z"}}]}}
If the page needs a login, is rate-limited or empty, set searched false and say why in blocker.
"""


def run_discovery(*, max_quests: int = SOURCE_DISCOVERY_MAX_QUESTS,
                  cap_usd: float = SOURCE_DISCOVERY_CAP_USD,
                  turn_fn: Callable[..., dict] = openclaw_turn,
                  registry_path: Path | None = None, day: str | None = None) -> dict:
    day = day or date.today().isoformat()
    reg = SR.load_registry(registry_path)
    spent, quests, new_sources, wall = 0.0, [], [], None
    for i, (theme, (desc, ticks)) in enumerate(THEMES.items()):
        if wall:
            quests.append({"quest_id": f"discover:{day}:{theme}", "status": "NOT_RUN_LOGIN_WALL"})
            continue
        if i >= max_quests:
            quests.append({"quest_id": f"discover:{day}:{theme}", "status": "NOT_RUN_CAP_QUESTS"})
            continue
        if spent >= cap_usd:
            quests.append({"quest_id": f"discover:{day}:{theme}", "status": "NOT_RUN_CAP_USD"})
            continue
        qid = f"discover:{day}:{theme}"
        print(f"  discovery quest {qid} ...", flush=True)
        res = turn_fn(discovery_prompt(theme, desc, ticks), purpose=DISCOVERY_PURPOSE)
        spent += float(res.get("cost_usd") or 0.0)
        data = extract_json(res.get("reply") or "")
        accts = (data or {}).get("accounts") if isinstance(data, dict) else None
        blk = blocker_of(data)
        if is_login_wall(blk):
            wall = blk
        found, refused = [], []
        for a in accts or []:
            try:
                s = SR.x_source(a.get("handle", ""), kind=str(a.get("kind") or "").strip(),
                                tickers=[t for t in (a.get("tickers") or []) if isinstance(t, str)] or list(ticks),
                                theme=theme, quest_id=qid, name=str(a.get("name") or ""))
            except SR.RegistryRefused as exc:
                refused.append({"handle": a.get("handle"), "why": str(exc)[:160]})
                continue
            post = {"post_url": a.get("latest_post_url"), "posted_utc": a.get("latest_post_utc")}
            s2 = SR.verify_with_posts(s, [post])   # a quest-reported post verifies only if dated + under this handle
            found.append(s2)
        new_sources += found
        quests.append({"quest_id": qid,
                       "status": ("REFUSED_LOGIN_WALL" if is_login_wall(blk) else
                                  "REFUSED_NOT_SEARCHED" if blk else res.get("status")),
                       "blocker": blk, "parsed": accts is not None, "n_found": len(found),
                       "n_refused": len(refused), "refused": refused[:10],
                       "handles": [s.handle for s in found], "cost_usd": round(float(res.get("cost_usd") or 0), 6),
                       "cost_openclaw_usd": res.get("cost_openclaw_usd"),
                       "cost_unknown": res.get("cost_unknown", False),
                       "elapsed_s": res.get("elapsed_s"), "reply_head": (res.get("reply") or "")[:300]})
        print(f"    {quests[-1]['status']} found {len(found)} ({res.get('elapsed_s')}s, ${float(res.get('cost_usd') or 0):.4f})", flush=True)
    reg2, added = SR.merge_sources(reg, new_sources)
    SR.save_registry(reg2, registry_path)
    rc = {"receipt": "source_reads.discover", "day": day, "generated_at": _now(),
          "model": SOURCE_READS_MODEL, "n_quests_run": sum(1 for q in quests if "cost_usd" in q),
          "cost_usd": round(spent, 6), "cap_usd": cap_usd, "n_handles_found": len(new_sources),
          "n_added": added, "n_verified_at_discovery": sum(1 for s in new_sources if s.verified),
          "quests": quests}
    _write_receipt(rc, f"discovery_{day}.json")
    return rc


# ─────────────────────────────── the daily read ─────────────────────────────
def read_url(sources: list, since: str) -> str:
    from urllib.parse import quote
    q = "(" + " OR ".join("from:" + s.handle.lstrip("@") for s in sources) + f") since:{since}"
    return f"https://x.com/search?q={quote(q)}&f=live"


def read_prompt(sources: list, tickers: list[str], *, since: str | None = None) -> str:
    since = since or (date.today() - timedelta(days=7)).isoformat()
    url = read_url(sources, since)
    return f"""{READ_ONLY}

Use the browser tool with the logged-in X account. Open {url}
and read the results (scroll once or twice). These are the latest posts of:
{', '.join(s.handle for s in sources)}

Report every post that is about one of these tickers or their companies:
{', '.join(tickers)}
For each: its status URL (https://x.com/<handle>/status/<id>), its time in ISO 8601 UTC
(read the post's time element; convert a relative time like "3h" using the current UTC time),
the claim quoted closely, the direction the author implies for the stock ("up", "down" or
"none"), and event_type from: attention_spike, product_launch, guidance_change, contract_win,
customer_announcement, management_language_change, analyst_revision, regulatory_decision,
forum_disagreement.

Reply with ONLY one JSON object, no prose, one entry per handle listed above:
{{"searched": true, "blocker": "", "reads": [{{"handle": "@example", "status": "OK|EMPTY",
"posts": [{{"post_url": "https://x.com/example/status/123", "posted_utc": "2026-09-25T14:03:00Z",
"ticker": "NVDA", "claim": "quoted claim", "direction": "up|down|none",
"event_type": "attention_spike"}}]}}]}}
If the page needs a login, is rate-limited or empty, set searched false and say why in blocker.
"""


def _event_type(st: str, et: Any) -> str:
    from backend.services import web_events as WE
    et = str(et or "attention_spike").strip()
    allowed = WE.SOURCE_REGISTRY.get(st, {}).get("types", ())
    return et if et in allowed else "attention_spike"


def web_event_row(src, post: dict, *, observed_at: str) -> dict:
    st = "reddit" if src.platform == "reddit" else "x"
    conf = "DIRECT_COMPANY_STATEMENT" if src.kind in ("company", "ceo_founder") else "FORUM_CLAIM"
    d = SR._norm_direction(post.get("direction"))
    return {"ticker": str(post.get("ticker") or "").upper(), "source_type": st,
            "source_url": str(post.get("post_url") or ""),
            "event_type": _event_type(st, post.get("event_type")),
            "claim": str(post.get("claim") or "")[:1200],
            "evidence_date": SR.parse_utc(post.get("posted_utc")).date().isoformat(),
            "entity": src.handle, "direction_prior": d,
            "horizon_prior": "1-20 sessions", "confidence_source": conf,
            "observed_at": observed_at, "retrieved_by": f"openclaw:{src.source_id}"}


def process_read(src, read: dict | None, tickers: set[str], *, observed_at: str) -> dict:
    """One source's read -> dated posts. Never silent: EMPTY_READ when nothing dated."""
    posts = (read or {}).get("posts") or []
    dated, undated, off_book = [], 0, 0
    for p in posts:
        if not isinstance(p, dict):
            continue
        if not SR.is_dated_post(src, p):
            undated += 1
            continue
        tk = str(p.get("ticker") or "").upper().lstrip("$")
        if tk not in tickers or not str(p.get("claim") or "").strip():
            off_book += 1
            continue
        p = {**p, "ticker": tk}
        dated.append(p)
    if read is None:
        status = "NO_REPLY_FOR_SOURCE"
    elif dated:
        status = "OK"
    else:
        status = "EMPTY_READ"
    return {"source_id": src.source_id, "handle": src.handle, "status": status,
            "reported_status": (read or {}).get("status"), "n_posts_reported": len(posts),
            "n_dated_on_book": len(dated), "n_undated": undated, "n_off_book": off_book,
            "posts": dated}


def run_reads(*, max_quests: int = SOURCE_READS_MAX_QUESTS,
              cap_usd: float = SOURCE_READS_DAILY_CAP_USD,
              turn_fn: Callable[..., dict] = openclaw_turn,
              registry_path: Path | None = None, ledger_path: Path | None = None,
              claims_path: Path | None = None, write_events: bool = True,
              day: str | None = None, tickers: list[str] | None = None) -> dict:
    from backend.services import web_events as WE
    day = day or date.today().isoformat()
    reg = SR.load_registry(registry_path)
    tickers = tickers or book_tickers()
    tset = set(tickers)
    social = [s for s in reg.values() if s.platform in ("x", "reddit")]
    social.sort(key=lambda s: (s.theme, s.kind, s.source_id))
    batches = [social[i:i + HANDLES_PER_QUEST] for i in range(0, len(social), HANDLES_PER_QUEST)]
    spent, quests, per_source, claims, events, wall = 0.0, [], [], [], [], None
    for qi, batch in enumerate(batches):
        qid = f"read:{day}:{qi:02d}"
        if wall or qi >= max_quests or spent >= cap_usd:
            why = ("NOT_READ_LOGIN_WALL" if wall else
                   "NOT_READ_CAP_QUESTS" if qi >= max_quests else "NOT_READ_CAP_USD")
            for s in batch:
                per_source.append({"source_id": s.source_id, "handle": s.handle, "status": why})
            quests.append({"quest_id": qid, "status": why, "handles": [s.handle for s in batch]})
            continue
        want = sorted({t for s in batch for t in s.tickers_covered} & tset) or tickers
        print(f"  read quest {qid}: {', '.join(s.handle for s in batch)} ...", flush=True)
        res = turn_fn(read_prompt(batch, want if len(want) >= 3 else tickers), purpose=READ_PURPOSE)
        spent += float(res.get("cost_usd") or 0.0)
        observed = _now()
        data = extract_json(res.get("reply") or "")
        reads = (data or {}).get("reads") if isinstance(data, dict) else None
        blk = blocker_of(data)
        if blk:
            # the page was not read: these sources are UNREAD, not empty
            if is_login_wall(blk):
                wall = blk
            st = "NOT_READ_LOGIN_WALL" if is_login_wall(blk) else "NOT_READ_BLOCKED"
            for s in batch:
                per_source.append({"source_id": s.source_id, "handle": s.handle, "status": st})
            quests.append({"quest_id": qid, "status": "REFUSED_" + st[9:], "blocker": blk,
                           "handles": [s.handle for s in batch], "n_claims": 0,
                           "cost_usd": round(float(res.get("cost_usd") or 0), 6),
                           "cost_unknown": res.get("cost_unknown", False),
                           "elapsed_s": res.get("elapsed_s")})
            print(f"    {st}: {blk[:120]}", flush=True)
            continue
        by_handle = {}
        for r in reads or []:
            if isinstance(r, dict) and r.get("handle"):
                by_handle["@" + str(r["handle"]).lstrip("@").lower()] = r
        n_claims_q = 0
        for s in batch:
            pr = process_read(s, by_handle.get(s.handle.lower()), tset, observed_at=observed)
            if pr["posts"]:
                s2 = SR.verify_with_posts(s, pr["posts"])
                if s2 is not s:
                    reg[s.source_id] = s2
                    pr["verified_now"] = True
            for p in pr["posts"]:
                claims.append({"source_id": s.source_id, "source_kind": s.kind,
                               "ticker": p["ticker"], "claim_text": p["claim"],
                               "claim_utc": p["posted_utc"], "direction": p.get("direction"),
                               "post_url": p.get("post_url", "")})
                try:
                    events.append(web_event_row(s, p, observed_at=observed))
                except Exception as exc:                            # noqa: BLE001
                    pr.setdefault("event_errors", []).append(str(exc)[:160])
                n_claims_q += 1
            pr.pop("posts", None)
            per_source.append(pr)
        quests.append({"quest_id": qid, "status": res.get("status"), "parsed": reads is not None,
                       "handles": [s.handle for s in batch], "n_claims": n_claims_q,
                       "cost_usd": round(float(res.get("cost_usd") or 0), 6),
                       "cost_openclaw_usd": res.get("cost_openclaw_usd"),
                       "cost_unknown": res.get("cost_unknown", False),
                       "elapsed_s": res.get("elapsed_s"), "reply_head": (res.get("reply") or "")[:300]})
        print(f"    {res.get('status')} claims {n_claims_q} ({res.get('elapsed_s')}s, ${float(res.get('cost_usd') or 0):.4f})", flush=True)
    SR.save_registry(reg, registry_path)
    we = WE.append(events, day=day) if (write_events and events) else {"written": 0, "refused": 0}
    wc = SR.write_claims(claims, path=ledger_path, claims_path=claims_path)
    counts: dict[str, int] = {}
    for p in per_source:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    rc = {"receipt": "source_reads.read", "day": day, "generated_at": _now(),
          "model": SOURCE_READS_MODEL, "tickers": tickers, "n_social_sources": len(social),
          "n_quests_run": sum(1 for q in quests if "cost_usd" in q), "cost_usd": round(spent, 6),
          "cap_usd": cap_usd, "max_quests": max_quests, "status_counts": counts,
          "login_wall": wall, "n_claims": len(claims), "web_events": {k: we.get(k) for k in ("written", "refused", "duplicates")},
          "web_event_refusals": we.get("refusals", [])[:10], "forecast_rows": wc,
          "never": "no order is generated from any read", "quests": quests, "per_source": per_source}
    _write_receipt(rc, f"reads_{day}.json")
    return rc


# ─────────────────────────────── handle timelines ───────────────────────────
#
# Adjudication 2026-09-26 row 10: X SEARCH is walled logged out, X handle
# TIMELINES are not (F read four dated @MicronTech posts). So the daily read is
# rebuilt around `x.com/<handle>` pages. The reviewer's 15 specialists come
# first (company handles are mostly marketing); company/IR handles for the
# names in `human_ai_thematic_v2` follow. Every one is seeded `verified: false`
# and becomes verified only when a dated post under that handle is read.

TIMELINE_MAX_QUESTS: int = int(_cfg("SOURCE_TIMELINE_MAX_QUESTS", 15))
TIMELINE_CAP_USD: float = float(_cfg("SOURCE_TIMELINE_CAP_USD", 1.20))
TIMELINE_HANDLES_PER_QUEST: int = int(_cfg("SOURCE_TIMELINE_HANDLES_PER_QUEST", 2))
TIMELINE_DAYS: int = int(_cfg("SOURCE_TIMELINE_DAYS", 30))
#: consecutive walled quests before the run stops spending
TIMELINE_WALL_STOP: int = 2
REVIEWER_SEED = "reviewer_abf_2026-09-26"
THEMATIC_BOOK = "human_ai_thematic_v2"

_SEMIS = ("MU", "SNDK", "NVDA", "AMD", "TSM", "ASML", "TER", "AXTI", "WOLF", "LITE", "AVGO")
_BIO = ("INCY", "JAZZ", "VRTX", "BBIO", "NTLA", "ARGX", "AGIO", "AMGN", "MRK", "PRAX", "COGT",
        "KYTX", "BHVN", "ABSI", "ERAS", "RVMD", "TWST", "VKTX", "RGEN", "WST")
#: (handle, kind, theme, tickers) -- REVIEW_2026-09-26_CHUNKS_A_B_F.md, "X handles to seed"
SPECIALIST_HANDLES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("@dylan522p", "industry_specialist", "semis_memory", _SEMIS),
    ("@SemiAnalysis_", "industry_specialist", "semis_memory", _SEMIS),
    ("@Jukanlosreve", "industry_specialist", "semis_memory", _SEMIS),
    ("@TrendForce", "industry_specialist", "semis_memory", _SEMIS),
    ("@adamfeuerstein", "journalist", "biotech", _BIO),
    ("@matthewherper", "journalist", "biotech", _BIO),
    ("@EndpointsNews", "journalist", "biotech", _BIO),
    ("@FierceBiotech", "journalist", "biotech", _BIO),
    ("@DeItaone", "journalist", "tape_headlines", ()),
    ("@FirstSquawk", "journalist", "tape_headlines", ()),
    ("@unusual_whales", "retail_influencer", "tape_headlines", ()),
    ("@muddywatersre", "fund_manager", "short_activist", ()),
    ("@CitronResearch", "fund_manager", "short_activist", ()),
    ("@FuzzyPandaShort", "fund_manager", "short_activist", ()),
)
#: company / IR handles for the names in human_ai_thematic_v2. GUESSED from the
#: company names; unverified until a dated post under the handle is read, and a
#: wrong guess reads as NOT_FOUND, never as "no activity".
COMPANY_HANDLES: dict[str, str] = {
    "MU": "@MicronTech", "AVGO": "@Broadcom", "GEV": "@GEVernova", "VRT": "@Vertiv",
    "HOOD": "@RobinhoodApp", "DKNG": "@DraftKings", "IONQ": "@IonQ_Inc",
    "VRTX": "@VertexPharma", "CCJ": "@Cameco", "LEU": "@CentrusEnergy",
    "BE": "@Bloom_Energy", "MP": "@MPMaterials", "CLS": "@Celestica", "BBIO": "@BridgeBio",
    "TSM": "@TSMC", "NVT": "@nVentHQ", "NOVT": "@NovantaInc", "WST": "@WestPharma",
    "COGT": "@CogentBio", "VKTX": "@VikingTx", "AGIO": "@agiospharma", "RGEN": "@Repligen",
    "PRAX": "@PraxisPrecision",
}


def thematic_tickers(name: str = THEMATIC_BOOK) -> list[str]:
    """The names in the latest frozen `name` book (not its twins)."""
    out: list[str] = []
    try:
        for line in LLM_BOOKS.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("name") != name:
                continue
            out = [str(p.get("ticker") or "").upper() for p in r.get("positions") or []
                   if isinstance(p, dict)]
    except OSError:
        return []
    return [t for t in out if t and t not in _NOT_NAMES]


def timeline_seed_sources(now: str | None = None) -> list:
    """The reviewer's specialists (14 handles listed; its text says 15) and the
    company handles for the thematic book, all `verified: false`."""
    now = now or _now()
    out = []
    for h, kind, theme, ticks in SPECIALIST_HANDLES:
        out.append(SR.x_source(h, kind=kind, tickers=ticks, theme=theme, quest_id="",
                               added_by=REVIEWER_SEED, name="reviewer A+B+F specialist", now=now))
    names = set(thematic_tickers()) or set(COMPANY_HANDLES)
    for t, h in COMPANY_HANDLES.items():
        if t not in names:
            continue
        out.append(SR.x_source(h, kind="company", tickers=[t], theme=THEMATIC_BOOK, quest_id="",
                               added_by="company_ir_seed_2026-09-26",
                               name="guessed company handle; unverified until a dated post is read",
                               now=now))
    return out


def run_seed_timelines(registry_path: Path | None = None) -> dict:
    p = Path(registry_path) if registry_path else SR.REGISTRY_PATH
    reg = SR.load_registry(p) if p.exists() else {}
    reg2, added = SR.merge_sources(reg, timeline_seed_sources())
    SR.save_registry(reg2, p)
    x = [s for s in reg2.values() if s.platform == "x"]
    return {"receipt": "source_reads.seed_timelines", "n_added": added, "n_x_sources": len(x),
            "n_unverified": sum(1 for s in x if not s.verified)}


def timeline_prompt(sources: list, tickers: list[str], *, days: int = TIMELINE_DAYS,
                    today: date | None = None) -> str:
    since = ((today or date.today()) - timedelta(days=days)).isoformat()
    pages = "\n".join(f"  https://x.com/{s.handle.lstrip('@')}" for s in sources)
    return f"""{READ_ONLY}

Use the browser tool. Open each of these X profile pages IN TURN (a profile timeline, not
a search; it usually shows without logging in):
{pages}
On each page, scroll the timeline two or three times and read the posts BY THAT HANDLE
(skip reposts of other accounts and replies to others) dated on or after {since}.

For each handle report:
- status: "OK" if you could see its posts, "EMPTY" if the timeline shows no posts in the
  window, "LOGIN_WALL" if X asked you to log in / sign up instead of showing posts,
  "NOT_FOUND" if the account does not exist or is suspended/protected;
- latest_post_url and latest_post_utc: the newest post by this handle you saw (any topic);
- posts: every post by this handle in the window that mentions one of these tickers or
  their companies: {', '.join(tickers)}
  Each with its status URL (https://x.com/<handle>/status/<id>), its time in ISO 8601 UTC
  (read the post's time element; convert a relative time like "3h" from the current UTC time),
  the ticker, the claim quoted closely, the direction the author states or clearly implies for
  the stock ("up", "down", or "none" when no direction is stated), and event_type from:
  attention_spike, product_launch, guidance_change, contract_win, customer_announcement,
  management_language_change, analyst_revision, regulatory_decision, forum_disagreement.
Never invent a post, a URL or a time. At most 15 posts per handle.

Reply with ONLY one JSON object, no prose:
{{"searched": true, "blocker": "", "reads": [{{"handle": "@example", "status": "OK",
"latest_post_url": "https://x.com/example/status/1", "latest_post_utc": "2026-09-25T14:03:00Z",
"posts": [{{"post_url": "https://x.com/example/status/123", "posted_utc": "2026-09-25T14:03:00Z",
"ticker": "NVDA", "claim": "quoted claim", "direction": "up|down|none",
"event_type": "attention_spike"}}]}}]}}
If no page could be read at all, set searched false and say why in blocker.
"""


def _timeline_status(src, read: dict | None, pr: dict) -> str:
    st = str((read or {}).get("status") or "").upper().replace(" ", "_")
    if "LOGIN" in st or is_login_wall(str((read or {}).get("blocker") or "")):
        return "NOT_READ_LOGIN_WALL"
    if st in ("NOT_FOUND", "SUSPENDED", "PROTECTED"):
        return "NOT_FOUND"
    return pr["status"]


def run_timeline_reads(*, max_quests: int = TIMELINE_MAX_QUESTS, cap_usd: float = TIMELINE_CAP_USD,
                       per_quest: int = TIMELINE_HANDLES_PER_QUEST,
                       turn_fn: Callable[..., dict] = openclaw_turn,
                       registry_path: Path | None = None, ledger_path: Path | None = None,
                       claims_path: Path | None = None, write_events: bool = True,
                       day: str | None = None, tickers: list[str] | None = None) -> dict:
    """One quest per `per_quest` handles, specialists first. Every handle ends
    with a status: OK / EMPTY_READ / NOT_FOUND / NOT_READ_LOGIN_WALL /
    NOT_READ_CAP_QUESTS / NOT_READ_CAP_USD / NO_REPLY_FOR_SOURCE."""
    from backend.services import web_events as WE
    day = day or date.today().isoformat()
    reg = SR.load_registry(registry_path)
    base = tickers or sorted(set(book_tickers(60)) | set(thematic_tickers()))
    order = {h.lower(): i for i, (h, *_rest) in enumerate(SPECIALIST_HANDLES)}
    comp = {h.lower(): i for i, h in enumerate(COMPANY_HANDLES.values())}
    xs = [s for s in reg.values() if s.platform == "x"]
    xs.sort(key=lambda s: (0, order[s.handle.lower()]) if s.handle.lower() in order else
            (1, comp.get(s.handle.lower(), 999), s.source_id))
    batches = [xs[i:i + per_quest] for i in range(0, len(xs), per_quest)]
    spent, quests, per_source, claims, events = 0.0, [], [], [], []
    walls, wall_msg = 0, None
    for qi, batch in enumerate(batches):
        qid = f"timeline:{day}:{qi:02d}"
        why = ("NOT_READ_LOGIN_WALL" if walls >= TIMELINE_WALL_STOP else
               "NOT_READ_CAP_QUESTS" if qi >= max_quests else
               "NOT_READ_CAP_USD" if spent >= cap_usd else None)
        if why:
            for s in batch:
                per_source.append({"source_id": s.source_id, "handle": s.handle, "status": why})
            quests.append({"quest_id": qid, "status": why, "handles": [s.handle for s in batch]})
            continue
        want = sorted(set(base) | {t for s in batch for t in s.tickers_covered})
        print(f"  timeline quest {qid}: {', '.join(s.handle for s in batch)} ...", flush=True)
        res = turn_fn(timeline_prompt(batch, want), purpose=READ_PURPOSE)
        spent += float(res.get("cost_usd") or 0.0)
        observed = _now()
        data = extract_json(res.get("reply") or "")
        reads = (data or {}).get("reads") if isinstance(data, dict) else None
        blk = blocker_of(data)
        by_handle = {"@" + str(r["handle"]).lstrip("@").lower(): r
                     for r in reads or [] if isinstance(r, dict) and r.get("handle")}
        n_claims_q, walled_here = 0, 0
        for s in batch:
            rd = by_handle.get(s.handle.lower())
            if rd is None and blk:
                st = "NOT_READ_LOGIN_WALL" if is_login_wall(blk) else "NOT_READ_BLOCKED"
                per_source.append({"source_id": s.source_id, "handle": s.handle, "status": st,
                                   "blocker": blk[:200]})
                walled_here += st == "NOT_READ_LOGIN_WALL"
                continue
            pr = process_read(s, rd, set(want), observed_at=observed)
            pr["status"] = _timeline_status(s, rd, pr)
            walled_here += pr["status"] == "NOT_READ_LOGIN_WALL"
            latest = {"post_url": (rd or {}).get("latest_post_url"),
                      "posted_utc": (rd or {}).get("latest_post_utc")}
            s2 = SR.verify_with_posts(s, [*pr["posts"], latest])
            if s2 is not s:
                reg[s.source_id] = s2
                pr["verified_now"] = True
            if pr["status"] == "OK":
                for p in pr["posts"]:
                    claims.append({"source_id": s.source_id, "source_kind": s.kind,
                                   "ticker": p["ticker"], "claim_text": p["claim"],
                                   "claim_utc": p["posted_utc"], "direction": p.get("direction"),
                                   "post_url": p.get("post_url", "")})
                    try:
                        events.append(web_event_row(s, p, observed_at=observed))
                    except Exception as exc:                        # noqa: BLE001
                        pr.setdefault("event_errors", []).append(str(exc)[:160])
                    n_claims_q += 1
            pr["n_directional"] = sum(1 for p in pr["posts"] if SR._norm_direction(p.get("direction")))
            pr.pop("posts", None)
            per_source.append(pr)
        if walled_here == len(batch):
            walls += 1
            wall_msg = blk or "every handle in the quest reported LOGIN_WALL"
        else:
            walls = 0
        quests.append({"quest_id": qid, "status": res.get("status"), "parsed": reads is not None,
                       "blocker": blk, "handles": [s.handle for s in batch], "n_claims": n_claims_q,
                       "cost_usd": round(float(res.get("cost_usd") or 0), 6),
                       "cost_openclaw_usd": res.get("cost_openclaw_usd"),
                       "cost_unknown": res.get("cost_unknown", False),
                       "elapsed_s": res.get("elapsed_s"), "reply_head": (res.get("reply") or "")[:300]})
        print(f"    {res.get('status')} claims {n_claims_q} ({res.get('elapsed_s')}s, "
              f"${float(res.get('cost_usd') or 0):.4f}) spent ${spent:.4f}", flush=True)
        SR.save_registry(reg, registry_path)          # flush verification per quest
    SR.save_registry(reg, registry_path)
    we = WE.append(events, day=day) if (write_events and events) else {"written": 0, "refused": 0}
    wc = SR.write_claims(claims, path=ledger_path, claims_path=claims_path)
    counts: dict[str, int] = {}
    for p in per_source:
        counts[p["status"]] = counts.get(p["status"], 0) + 1
    rc = {"receipt": "source_reads.timelines", "day": day, "generated_at": _now(),
          "model": SOURCE_READS_MODEL, "mode": "x.com/<handle> timelines (search is walled logged out)",
          "window_days": TIMELINE_DAYS, "tickers": base, "n_x_sources": len(xs),
          "n_quests_run": sum(1 for q in quests if "cost_usd" in q), "cost_usd": round(spent, 6),
          "cap_usd": cap_usd, "max_quests": max_quests, "handles_per_quest": per_quest,
          "status_counts": counts, "login_wall": wall_msg if walls >= TIMELINE_WALL_STOP else None,
          "n_claims": len(claims),
          "n_directional_claims": sum(1 for c in claims if SR._norm_direction(c.get("direction"))),
          "n_verified_now": sum(1 for p in per_source if p.get("verified_now")),
          "web_events": {k: we.get(k) for k in ("written", "refused", "duplicates")},
          "web_event_refusals": we.get("refusals", [])[:10], "forecast_rows": wc,
          "never": "no order is generated from any read", "quests": quests, "per_source": per_source}
    _write_receipt(rc, f"timelines_{day}.json")
    return rc


# ─────────────────────────────── seed / score ───────────────────────────────
def run_seed(registry_path: Path | None = None) -> dict:
    p = Path(registry_path) if registry_path else SR.REGISTRY_PATH
    reg = SR.load_registry(p) if p.exists() else {}
    reg2, added = SR.merge_sources(reg, SR.seed_base_sources())
    SR.save_registry(reg2, p)
    counts: dict[str, int] = {}
    for s in reg2.values():
        counts[s.kind] = counts.get(s.kind, 0) + 1
    return {"receipt": "source_reads.seed", "n_sources": len(reg2), "n_added": added,
            "by_kind": counts}


def run_score_brokers(day: str | None = None, *, revisions_path: Path | None = None,
                      bar_paths: list[Path] | None = None) -> dict:
    """Adjudication row 13: every brokerage scored from the revisions parquet
    ($0, no LLM). Returns the board; `run_score` writes it."""
    from backend.services import xs_ranker as X
    day = day or date.today().isoformat()
    t0 = time.time()
    claims, load_rc = SR.load_revision_claims(revisions_path, today=day)
    bars = SR.load_close_panel(bar_paths)
    audit = X.survivorship_audit(bars)
    dates, syms, rel = SR.relative_forward_returns(bars)
    del bars
    c = SR.attach_outcomes(claims, dates, syms, rel)
    del rel
    recent_ticks = set(c.loc[c["t"] >= pd_ts(day) - _td(days=30), "ticker"])
    ms = SR.load_mainstream_pit(recent_ticks)
    board = SR.broker_scoreboard(c, today=day, mainstream=ms)
    board["load"] = load_rc
    board["panel"] = {"paths": [str(p) for p in (bar_paths or X.survivorship_free_paths())],
                      "n_sessions": int(len(dates)), "first_session": str(dates.min().date()),
                      "last_session": str(dates.max().date()), "n_symbols": len(syms),
                      "survivorship_audit": audit,
                      "n_claims_priced_21d": int(c["rel_21d"].notna().sum()),
                      "n_claims_before_panel": int((c["t"] < dates.min()).sum())}
    board["elapsed_s"] = round(time.time() - t0, 1)
    return board


def pd_ts(v: Any):
    import pandas as pd
    return pd.Timestamp(v)


def _td(**kw: Any):
    import pandas as pd
    return pd.Timedelta(**kw)


def run_score(day: str | None = None, *, brokers: bool = True) -> dict:
    import pandas as pd
    from backend.services import belief_state as B
    day = day or date.today().isoformat()
    reg = SR.load_registry()
    claims = SR.read_claims()
    ticks = {str(c.get("ticker")).upper() for c in claims}
    bars = None
    if claims and SR.BARS_PATH.exists():
        b = pd.read_parquet(SR.BARS_PATH, columns=["symbol", "date", "close"])
        bars = b[b["symbol"].isin(ticks | {SR.FORECAST_BENCHMARK})]
    ms = SR.load_mainstream_items(ticks, registry=reg) if claims else None
    rows = [r for r in B.read_predictions()
            if str(r.get("specialist") or "").startswith(SR.SPECIALIST_PREFIX)]
    sb = SR.score(reg, claims=claims, ledger_rows=rows, bars=bars, mainstream=ms,
                  sector_map=SR.sector_map_default())
    out: dict[str, Any] = {}
    if brokers:
        board = run_score_brokers(day)
        sb["brokers"] = board
        reg2, wres = SR.apply_broker_weights(SR.load_registry(), board)
        SR.save_registry(reg2)
        board["registry_weights"] = wres
        out["brokers"] = {k: board[k] for k in ("n_claims", "n_directional", "n_firms", "n_ranked",
                                                "base_rate", "base_rate_recent", "heldout_split_date",
                                                "persistence_insample_vs_heldout_spearman",
                                                "n_weight_earned", "elapsed_s")}
        out["brokers"]["registry_weights"] = wres
    jp, mp = SR.write_scoreboard(sb, day=day)
    out.update({"scoreboard": str(jp), "markdown": str(mp), "n_sources": sb["n_sources"],
                "n_claims": sb["n_claims"], "by_kind": sb["by_kind"]})
    return out


def _write_receipt(rc: dict, name: str) -> Path:
    SR.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    p = SR.SOURCES_DIR / name
    p.write_text(json.dumps(rc, indent=2, default=str), encoding="utf-8")
    return p


def run_grade_promises(ticker: str | None = None, *, fetch_full: bool = True) -> dict:
    """Adjudication row 14: grade numbered promises from the 8-K EX-99 earnings
    release by parser (no LLM). `fetch_full` lets the grader GET the exhibit
    from sec.gov (through the shared SEC choke point) when the corpus body,
    capped at 4,000 chars, lacks a metric."""
    from backend.services import thesis_card as TC
    fetch = None
    if fetch_full:
        def fetch(url: str) -> str:
            from backend.services.insider_form4 import _sec_get
            return _sec_get(url).text
    return TC.grade_numeric_promises(ticker, fetch=fetch,
                                     releases_fn=edgar_earnings_releases if fetch_full else None)


def edgar_earnings_releases(ticker: str, since: str) -> list[dict]:
    """8-K Item 2.02 filings for `ticker` filed on/after `since`, straight from
    EDGAR (submissions API -> filing index -> the EX-99.1 document). No LLM."""
    from backend.services import edgar_events as EE
    from backend.services.insider_form4 import _sec_get
    days = max(1, (date.today() - date.fromisoformat(since[:10])).days + 2)
    out = []
    for ev in EE.fetch_events_for_ticker(ticker, days_back=days):
        if "2.02" not in ev.items or ev.filed < since[:10]:
            continue
        folder = ev.primary_doc_url.rsplit("/", 1)[0]
        idx = _sec_get(folder + "/index.json").json()
        items = (idx.get("directory") or {}).get("item") or []
        docs = [it["name"] for it in items if re.search(r"ex[-_]?99", str(it.get("name", "")), re.I)
                and str(it.get("name", "")).lower().endswith((".htm", ".html", ".txt"))]
        if not docs:
            continue
        url = folder + "/" + sorted(docs)[0]
        out.append({"url": url, "published_utc": ev.filed + "T00:00:00+00:00",
                    "body": _sec_get(url).text, "source": "edgar_submissions"})
    out.sort(key=lambda r: r["published_utc"])
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--seed-timelines", action="store_true",
                    help="seed the reviewer's specialists + thematic-book company handles (verified: false)")
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--read", action="store_true",
                    help="X handle TIMELINE reads (x.com/<handle>); search is walled logged out")
    ap.add_argument("--read-search", action="store_true", help="the old from:-search read (walled logged out)")
    ap.add_argument("--score", action="store_true", help="scoreboard + SOURCES.md, brokers included")
    ap.add_argument("--no-brokers", action="store_true")
    ap.add_argument("--grade-promises", action="store_true")
    ap.add_argument("--ticker", default=None)
    ap.add_argument("--declare-targets", nargs=2, metavar=("PROMISE_ID", "JSON"),
                    help="e.g. 28e5... '[{\"metric\": \"revenue\", \"op\": \"within\", \"value\": 50, \"tolerance\": 1}]'")
    ap.add_argument("--max-quests", type=int, default=None)
    ap.add_argument("--cap-usd", type=float, default=None)
    a = ap.parse_args(argv)
    if not (a.seed or a.seed_timelines or a.discover or a.read or a.read_search or a.score
            or a.grade_promises or a.declare_targets):
        ap.error("nothing to do: pass --seed / --seed-timelines / --discover / --read / --score / "
                 "--grade-promises / --declare-targets")
    if a.seed:
        print(json.dumps(run_seed(), indent=2))
    if a.seed_timelines:
        print(json.dumps(run_seed_timelines(), indent=2))
    if a.discover:
        rc = run_discovery(max_quests=a.max_quests or SOURCE_DISCOVERY_MAX_QUESTS,
                           cap_usd=a.cap_usd or SOURCE_DISCOVERY_CAP_USD)
        print(json.dumps({k: v for k, v in rc.items() if k != "quests"}, indent=2))
    if a.read:
        rc = run_timeline_reads(max_quests=a.max_quests or TIMELINE_MAX_QUESTS,
                                cap_usd=a.cap_usd or TIMELINE_CAP_USD)
        print(json.dumps({k: v for k, v in rc.items() if k not in ("quests", "per_source", "tickers")},
                         indent=2))
    if a.read_search:
        rc = run_reads(max_quests=a.max_quests or SOURCE_READS_MAX_QUESTS,
                       cap_usd=a.cap_usd or SOURCE_READS_DAILY_CAP_USD)
        print(json.dumps({k: v for k, v in rc.items() if k not in ("quests", "per_source")}, indent=2))
    if a.declare_targets:
        from backend.services import thesis_card as TC
        pid, js = a.declare_targets
        print(json.dumps(TC.declare_targets(pid, json.loads(js), source="source_reads --declare-targets"),
                         indent=2))
    if a.score:
        print(json.dumps(run_score(brokers=not a.no_brokers), indent=2, default=str))
    if a.grade_promises:
        print(json.dumps(run_grade_promises(a.ticker), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
