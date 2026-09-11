"""N-A — THE CORPUS WRITER. Whole-market news, resumable, no LLM in the pull.

    python -m scripts.news_pull --source all --resume
    python -m scripts.news_pull --source google_news_rss_en_hk --max-rows 50
    python -m scripts.news_pull --list

One JSONL per source per UTC day under

    <DATA_DIR>/optimus/news_corpus/<source>/<YYYY-MM-DD>.jsonl

every row exactly

    {source, first_seen_utc, published_utc, tz_source, url, title, body, lang,
     tickers[], entity_tags[], raw_id, pit_grade}

a cursor per source under `news_corpus/_cursors/<source>.json`, and a receipt
per run per source under `news_corpus/_receipts/<utc>_<source>.json`.

FIVE THINGS THIS FILE IS CAREFUL ABOUT, each because of a specific failure
=========================================================================

**1. `first_seen_utc` is written by US, at write time.** Never parsed from a
payload, never copied from a provider field. For a `first_seen_only` source it
is the ONLY defensible PIT anchor, and an anchor we did not write ourselves is
an anchor the provider can move.

**2. A source is refused BY NAME, never crashed.** `APCA_API_KEY_ID` and
`APCA_API_SECRET_KEY` are absent in this environment. Alpaca therefore reports
`REFUSED: no credential resolved for alpaca_benzinga_news (looked for
APCA_API_KEY_ID, APCA_API_SECRET_KEY, then the terminal repo's .env
AAT_HACK*_KEY_ID)` — the NAMES, never a value — and the run continues. The
credential helper is the one from `scripts/night_p6_bars_and_regret.py:78-100`,
reused rather than re-derived, with one fix: that copy computes the terminal
repo as `REPO.parent / "aegis-alpha-terminal"`, which resolves to
`.claude/worktrees/aegis-alpha-terminal` when the script runs from a git
worktree. Here the path is searched, and the receipt says which one answered.

**3. A source that returns zero rows TWICE is RED, never silent.** The count
lives in the cursor and survives across runs, because a zero-row run in
isolation is ordinary (a quiet Sunday) and two in a row is a dead feed. A
*refusal* does not increment it: a refusal already names itself.

**4. The parser is named in the registry, because a wrong parser looks exactly
like a dead feed.** Nikkei Asia is RSS 1.0/RDF; a namespace-naive
`findall(".//item")` returns zero items and would have been misdiagnosed by
rule 3 above. Reddit's `.rss` is Atom. SEC EDGAR's current-filings feed is
`action=getcurrent` — `action=getcompany` with no CIK returns an empty feed
with a 200. All three were found by the 2026-09-11 probe and all three are in
the registry rather than in a comment.

**5. GDELT is paced at the MEASURED rate, not the documented one.** The docs say
one request per 5 s; the probe 429'd three of five queries at 6 s spacing. The
registry says 20 s, and a 429 doubles the wait. The NGrams 3.0 bulk fallback is
named in the receipt when the paced path exhausts; it is not implemented, and
saying so is the point.

NO LLM, NO SIGNAL, NO CLAIM. This writes a corpus. N-C labels it; L2 reads it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterable

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import news_entities as entities  # noqa: E402
from backend.services import news_registry as registry  # noqa: E402

#: A contactable User-Agent. The SEC REQUIRES one; Reddit 429s without one.
USER_AGENT = os.getenv(
    "AEGIS_NEWS_USER_AGENT",
    "AegisFinance/1.0 lane-N corpus writer (contact: mrthnabdullaev@gmail.com)",
)

#: How many past day-files are scanned for `raw_id`s before a write. Bounded on
#: purpose: an unbounded seen-set in the cursor grows without limit, and a
#: duplicate that arrives eight days late is a new row by any useful definition.
DEDUPE_LOOKBACK_DAYS = 7

#: Row body cap. GDELT and the RSS feeds carry no body at all; Yahoo's is a
#: ~130-character blurb; Reddit self-posts can be long.
MAX_BODY = 4000

ROW_KEYS = (
    "source", "first_seen_utc", "published_utc", "tz_source", "url", "title",
    "body", "lang", "tickers", "entity_tags", "raw_id", "pit_grade",
)


# --------------------------------------------------------------------- paths

def corpus_dir() -> Path:
    """`<DATA_DIR>/optimus/news_corpus` — WRITTEN state, so it follows DATA_DIR.

    The registry and the name tables deliberately do NOT (they ship with the
    code); the corpus deliberately does, so `AEGIS_DATA_DIR=<main checkout>`
    lands the rows where the app reads them.
    """
    return Path(_config.DATA_DIR) / "optimus" / "news_corpus"


def source_dir(source_id: str) -> Path:
    return corpus_dir() / source_id


def cursor_path(source_id: str) -> Path:
    return corpus_dir() / "_cursors" / f"{source_id}.json"


def receipt_path(source_id: str, stamp: str) -> Path:
    return corpus_dir() / "_receipts" / f"{stamp}_{source_id}.json"


def universe_path() -> Path:
    return Path(_config.DATA_DIR) / "optimus" / "potential_universe" / "2026-09-02.jsonl"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str:
    return "" if dt is None else dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return _now().strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------- credentials

def _terminal_repo() -> Path | None:
    """Where `aegis-alpha-terminal` actually is.

    `night_p6_bars_and_regret.py` hard-codes `REPO.parent / "aegis-alpha-terminal"`,
    which is right from a normal checkout and WRONG from a git worktree (the
    parent is then `.claude/worktrees/`). Candidates are searched in order and
    the receipt records which answered — the path is the finding, not a guess.
    """
    seen: list[Path] = []
    for cand in (
        REPO.parent / "aegis-alpha-terminal",
        Path.home() / "aegis-alpha-terminal",
        REPO.parent.parent.parent / "aegis-alpha-terminal",
    ):
        if cand in seen:
            continue
        seen.append(cand)
        if (cand / ".env").exists():
            return cand
    return None


def alpaca_credential() -> tuple[str | None, str | None, str]:
    """The DATA key, and WHERE it came from. Never an order path.

    Adapted verbatim in shape from `scripts/night_p6_bars_and_regret.py:78-100`
    (`data_credential`), with two changes: it returns instead of `SystemExit`,
    so a missing key refuses one source rather than killing a whole run, and the
    terminal repo is searched rather than assumed. The returned third element is
    a SOURCE NAME, and is the only credential fact that ever reaches a receipt.
    """
    kid, sec = os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY")
    if kid and sec:
        return kid, sec, "process environment (APCA_API_KEY_ID)"
    terminal = _terminal_repo()
    if terminal is None:
        return None, None, "no terminal repo .env found"
    env: dict[str, str] = {}
    for line in (terminal / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    for role in ("HACK3", "HACK1", "HACK2", "HACK4", "HACK5", "HACK6"):
        kid, sec = env.get(f"AAT_{role}_KEY_ID"), env.get(f"AAT_{role}_SECRET_KEY")
        if kid and sec:
            return kid, sec, f"terminal repo .env, {role} (data endpoint only)"
    return None, None, "terminal repo .env carries no AAT_HACK*_KEY_ID / _SECRET_KEY pair"


def finnhub_key_name() -> str | None:
    """Which env NAME holds a Finnhub key, or None. Names only, never values."""
    for name in ("FINNHUB_API_KEY", "AAT_FINNHUB_API_KEY"):
        if os.getenv(name):
            return name
    return None


# ------------------------------------------------------------------- fetching

class FetchError(RuntimeError):
    """A network or parse failure for one call. Recorded, never raised past the source."""


class CallTimeout(FetchError):
    """One third-party call outlived its watchdog. The sweep continues."""


def call_with_timeout(fn, timeout_s: float, what: str):
    """Run `fn()` with a hard wall-clock bound, on a DAEMON thread.

    `_http_get` passes a timeout to urllib, so our own HTTP is bounded. A
    third-party library's own session is not: `yfinance.Ticker(...).news` goes
    through curl_cffi, and on 2026-09-11 the live pull sat on one ESTABLISHED
    socket to Yahoo for five minutes with 0.1s of CPU and no way to stop. This
    repo has paid for an unbounded third-party call before — the 2.5 h suite
    hang that `backend/tests/conftest.py` was written about.

    The hung thread is NOT killed (Python cannot), which is why it is a daemon:
    it cannot hold the process open at exit, and the sweep moves to the next
    symbol instead of waiting on it for ever.
    """
    box: dict = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 — the caller records the string
            box["error"] = e

    t = threading.Thread(target=run, daemon=True, name=f"news_pull:{what}")
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        raise CallTimeout(f"{what}: no response in {timeout_s:.0f}s (thread abandoned)")
    if "error" in box:
        raise FetchError(f"{what}: {type(box['error']).__name__}: {box['error']}")
    return box.get("value")


#: Hard bound on ONE `Ticker.news` call. Yahoo is unofficial and has no SLA.
YF_CALL_TIMEOUT_S = 25.0

#: Default wall-clock budget per source when the CLI does not set one. A
#: nightly job must finish; a source that cannot deliver inside its budget
#: stops with what it has and resumes from its cursor next run.
SOURCE_BUDGET_S = 600.0


def _http_get(url: str, *, headers: dict | None = None, timeout: float = 45.0) -> bytes:
    """The single network door. Every test mocks THIS, so no test needs a socket."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:  # noqa: S310 registry-gated URLs
            return fh.read()
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code} {url.split('?')[0]}") from e
    except Exception as e:  # noqa: BLE001 — the receipt wants the string, not a traceback
        raise FetchError(f"{type(e).__name__}: {e}") from e


# -------------------------------------------------------------------- parsers
# Each parser takes bytes and returns a list of RAW dicts. It knows nothing
# about cursors, dedupe, entities or receipts.

_ATOM = "{http://www.w3.org/2005/Atom}"
_RSS1 = "{http://purl.org/rss/1.0/}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}"


def _text(el, *names) -> str:
    for n in names:
        found = el.find(n)
        if found is not None and (found.text or "").strip():
            return " ".join((found.text or "").split())
    return ""


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return " ".join(_TAG_RE.sub(" ", s or "").split())


def _parse_rfc822(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_rss2(raw: bytes) -> list[dict]:
    """RSS 2.0 — Google News, Quantocracy. Plain <item> under <channel>."""
    root = ET.fromstring(raw)
    out = []
    for item in root.iter("item"):
        link = _text(item, "link")
        guid = _text(item, "guid") or link
        out.append({
            "title": _text(item, "title"),
            "url": link,
            "body": _text(item, "description", _CONTENT + "encoded"),
            "published": _parse_rfc822(_text(item, "pubDate")),
            "raw_id": guid,
        })
    return out


def parse_rss1_rdf(raw: bytes) -> list[dict]:
    """RSS 1.0 / RDF — Nikkei Asia.

    The 2026-09-11 probe's first attempt used `findall(".//item")` and got ZERO
    items, which is indistinguishable from a dead feed. Items here are
    `{http://purl.org/rss/1.0/}item`, and the date is `dc:date`.
    """
    root = ET.fromstring(raw)
    out = []
    for item in root.iter(_RSS1 + "item"):
        link = _text(item, _RSS1 + "link")
        out.append({
            "title": _text(item, _RSS1 + "title"),
            "url": link,
            "body": _text(item, _RSS1 + "description"),
            "published": _parse_iso(_text(item, _DC + "date")),
            "raw_id": item.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about") or link,
        })
    return out


def parse_atom_generic(raw: bytes) -> list[dict]:
    """Atom 1.0 — Reddit's `.rss` is Atom, not RSS 2.0."""
    root = ET.fromstring(raw)
    out = []
    for e in root.iter(_ATOM + "entry"):
        link_el = e.find(_ATOM + "link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        out.append({
            "title": _text(e, _ATOM + "title"),
            "url": link,
            "body": _text(e, _ATOM + "content", _ATOM + "summary"),
            "published": _parse_iso(_text(e, _ATOM + "published", _ATOM + "updated")),
            "raw_id": _text(e, _ATOM + "id") or link,
        })
    return out


def parse_edgar_atom(raw: bytes) -> list[dict]:
    """SEC EDGAR `action=getcurrent` Atom.

    Title: "8-K - COMPANY NAME (0001234567) (Filer)".
    Summary: the filed date, the accession number, the size and the Item
    numbers. Item 2.02 is tagged `8-K:2.02` because it is the free, vendor-free
    earnings-announcement marker; the CIK is carried as `cik:NNNNNNNNNN` so a
    later CIK->ticker join has something to join on.
    """
    root = ET.fromstring(raw)
    out = []
    for e in root.iter(_ATOM + "entry"):
        title = _text(e, _ATOM + "title")
        link_el = e.find(_ATOM + "link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        # EDGAR's summary is `type="html"` and arrives ESCAPED, so the element
        # text is literally `<b>Filed:</b> 2026-09-11 <b>AccNo:</b> 0001104659-...`.
        # Splitting on "AccNo:" without stripping the tags yields "</b>" as the
        # accession — and since every entry then shares that same `raw_id`, the
        # dedupe swallows the whole page. Found by the fixture test, not in prod.
        summary = _strip_html(_text(e, _ATOM + "summary"))
        tags: list[str] = []
        blob = f"{title} {summary}"
        for item_no in _EDGAR_ITEMS:
            if f"Item {item_no}" in blob:
                tags.append(f"8-K:{item_no}")
        cik = ""
        if "(" in title:
            for chunk in title.split("(")[1:]:
                digits = chunk.split(")")[0].strip()
                if digits.isdigit():
                    cik = digits
                    break
        if cik:
            tags.append(f"cik:{cik}")
        accession = ""
        if "AccNo:" in summary:
            accession = summary.split("AccNo:")[1].split()[0].strip()
        out.append({
            "title": title,
            "url": link,
            "body": summary,
            "published": _parse_iso(_text(e, _ATOM + "updated")),
            "raw_id": accession or link,
            "entity_tags": tags,
            # The issuer name sits between the form and the CIK parenthesis.
            "resolve_text": title.split(" - ", 1)[1] if " - " in title else title,
        })
    return out


#: The 8-K items worth tagging. 2.02 is the earnings print; the rest are the
#: event classes L2's vocabulary will most want as a prior.
_EDGAR_ITEMS = ("1.01", "1.02", "2.02", "2.05", "2.06", "4.01", "4.02",
                "5.02", "7.01", "8.01")


def parse_gdelt_doc(raw: bytes) -> list[dict]:
    """GDELT DOC 2.0 `mode=artlist&format=json`."""
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError as e:
        raise FetchError(f"GDELT returned non-JSON ({e}); this is usually a rate-limit page") from e
    out = []
    for a in payload.get("articles", []) or []:
        seen = a.get("seendate") or ""
        dt = None
        if len(seen) >= 15:
            try:
                dt = datetime.strptime(seen[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                dt = None
        out.append({
            "title": a.get("title") or "",
            "url": a.get("url") or "",
            "body": "",
            "published": dt,
            "raw_id": a.get("url") or "",
            "lang": (a.get("language") or "").lower() or None,
            "entity_tags": [f"domain:{a['domain']}"] if a.get("domain") else [],
        })
    return out


PARSERS: dict[str, Callable[[bytes], list[dict]]] = {
    "rss2": parse_rss2,
    "rss1_rdf": parse_rss1_rdf,
    "atom_generic": parse_atom_generic,
    "edgar_atom": parse_edgar_atom,
    "gdelt_doc": parse_gdelt_doc,
}


# ------------------------------------------------------------------- fetchers
# A fetcher turns one registry source into raw dicts, honouring pacing. It
# records its own failures and NEVER raises past `pull_source`.


@dataclass
class FetchResult:
    items: list[dict] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    calls: int = 0
    refused: str = ""
    #: The stamp a `--resume` should continue from next time, if the source has one.
    next_cursor: str = ""
    #: Where a symbol-by-symbol sweep should START next time. See
    #: `fetch_yfinance_news`: without it, every capped run re-pulls the same
    #: alphabetical prefix and the rest of the universe is never covered.
    next_offset: int | None = None


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def fetch_feed(src: registry.NewsSource, ctx: "RunContext") -> FetchResult:
    """Any single-URL feed: the 10 Google News combos, Nikkei, Reddit, Quantocracy."""
    res = FetchResult()
    parser = PARSERS[src.parser]
    try:
        res.calls += 1
        raw = ctx.http_get(src.endpoint_or_feed)
        res.items = parser(raw)
    except (FetchError, ET.ParseError) as e:
        res.failures.append(str(e))
    return res


def fetch_gdelt(src: registry.NewsSource, ctx: "RunContext") -> FetchResult:
    """One paced call per registry query, plus one per theme basket."""
    res = FetchResult()
    queries = list(src.queries) + ctx.theme_queries()
    for i, q in enumerate(queries):
        if ctx.budget_spent(res):
            break
        if i:
            _sleep(ctx.pace(src))
        url = src.endpoint_or_feed + "?" + urllib.parse.urlencode({
            "query": q, "mode": "artlist", "format": "json",
            "maxrecords": min(250, max(10, ctx.max_rows or 250)),
            "sort": "datedesc",
        })
        try:
            res.calls += 1
            res.items.extend(parse_gdelt_doc(ctx.http_get(url)))
        except FetchError as e:
            msg = str(e)
            res.failures.append(f"{q}: {msg}")
            if "429" in msg or "rate" in msg.lower():
                # The documented cadence was measured to be optimistic. Double
                # the registry interval once, then move on — the NGrams 3.0 bulk
                # endpoint is the documented fallback and is NOT implemented.
                _sleep(ctx.pace(src) * 2)
                res.failures.append(
                    "GDELT rate limit hit; the documented NGrams 3.0 bulk fallback is NOT implemented"
                )
    return res


def fetch_edgar(src: registry.NewsSource, ctx: "RunContext") -> FetchResult:
    """EDGAR `getcurrent`, paged with `start=` because the feed is a window."""
    res = FetchResult()
    base = src.endpoint_or_feed
    pages = max(1, min(4, ((ctx.max_rows or 200) + 99) // 100))
    for page in range(pages):
        if ctx.budget_spent(res):
            break
        if page:
            _sleep(ctx.pace(src))
        url = base + (f"&start={page * 100}" if page else "")
        try:
            res.calls += 1
            got = parse_edgar_atom(ctx.http_get(url))
            if not got:
                break
            res.items.extend(got)
        except (FetchError, ET.ParseError) as e:
            res.failures.append(f"start={page * 100}: {e}")
            break
    return res


def fetch_alpaca(src: registry.NewsSource, ctx: "RunContext") -> FetchResult:
    """Alpaca/Benzinga news, incremental by `created_at` — the backfill's cursor.

    Refuses BY NAME when no credential resolves. That is the whole behaviour in
    this environment, and it is a first-class outcome rather than an exception.
    """
    res = FetchResult()
    kid, sec, where = ctx.alpaca_credential()
    if not kid or not sec:
        res.refused = (
            f"REFUSED: no credential resolved for {src.id} (looked for "
            f"{', '.join(src.key_names())}, then the terminal repo's .env "
            f"AAT_HACK*_KEY_ID / _SECRET_KEY) — {where}"
        )
        return res
    start = ctx.since or ctx.cursor.get("next_cursor") or ""
    token = ""
    while True:
        if ctx.budget_spent(res):
            break
        params = {"limit": 50, "sort": "asc", "include_content": "true"}
        if start:
            params["start"] = start
        if ctx.until:
            params["end"] = ctx.until
        if token:
            params["page_token"] = token
        url = src.endpoint_or_feed + "?" + urllib.parse.urlencode(params)
        try:
            res.calls += 1
            payload = json.loads(ctx.http_get(url, headers={
                "APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec,
            }).decode("utf-8", "replace"))
        except (FetchError, json.JSONDecodeError) as e:
            res.failures.append(str(e))
            break
        batch = payload.get("news", []) or []
        for a in batch:
            created = a.get("created_at") or ""
            res.items.append({
                "title": a.get("headline") or "",
                "url": a.get("url") or "",
                "body": (a.get("content") or a.get("summary") or ""),
                "published": _parse_iso(created),
                "raw_id": str(a.get("id") or a.get("url") or ""),
                "tickers": [str(s).upper() for s in (a.get("symbols") or [])],
                "entity_tags": [f"author:{a['author']}"] if a.get("author") else [],
            })
            if created > res.next_cursor:
                res.next_cursor = created
        token = payload.get("next_page_token") or ""
        if not token or not batch:
            break
        _sleep(ctx.pace(src))
    res.failures.append(f"credential source: {where}")
    return res


def fetch_yfinance_news(src: registry.NewsSource, ctx: "RunContext") -> FetchResult:
    """`Ticker(symbol).news` over the tracker universe, paced and row-capped.

    THE SWEEP ROTATES. 3,056 symbols at the registry's 1 s pacing is ~51
    minutes, so a nightly run is capped with `--max-rows` and covers a few
    hundred names. Starting every capped run at symbol 0 means the
    alphabetical prefix is re-pulled for ever and the tail of the universe is
    never covered once — the same shape as the fixed seed that made every
    `G3_evolve_v2` night a bit-identical replay (2026-09-10). The cursor
    therefore carries `next_offset`, and each run continues where the last one
    stopped, wrapping at the end.
    """
    res = FetchResult()
    symbols = ctx.universe_symbols()
    if not symbols:
        res.refused = f"REFUSED: no universe file at {universe_path()} — nothing to iterate"
        return res
    start = int(ctx.cursor.get("next_offset", 0) or 0) % len(symbols)
    order = symbols[start:] + symbols[:start]
    consumed = 0
    for i, sym in enumerate(order):
        if ctx.budget_spent(res):
            break
        consumed = i + 1
        if i:
            _sleep(ctx.pace(src))
        try:
            res.calls += 1
            for item in ctx.yf_news(sym):
                c = item.get("content") or item
                url = ((c.get("canonicalUrl") or {}).get("url")
                       if isinstance(c.get("canonicalUrl"), dict) else c.get("canonicalUrl")) or ""
                res.items.append({
                    "title": c.get("title") or "",
                    "url": url,
                    "body": (c.get("summary") or c.get("description") or ""),
                    "published": _parse_iso(c.get("pubDate") or c.get("displayTime") or ""),
                    "raw_id": url or str(item.get("id") or ""),
                    "tickers": [sym],
                    "entity_tags": (
                        [f"provider:{(c.get('provider') or {}).get('displayName')}"]
                        if isinstance(c.get("provider"), dict) and c["provider"].get("displayName")
                        else []
                    ),
                })
        except Exception as e:  # noqa: BLE001 — one bad symbol must not end the sweep
            res.failures.append(f"{sym}: {type(e).__name__}: {e}")
    res.next_offset = (start + consumed) % len(symbols)
    res.failures.append(
        f"swept {consumed} symbols starting at universe index {start} "
        f"({order[0] if order else '--'}); next run starts at {res.next_offset}")
    return res


FETCHERS: dict[str, Callable[[registry.NewsSource, "RunContext"], FetchResult]] = {
    "rss2": fetch_feed,
    "rss1_rdf": fetch_feed,
    "atom_generic": fetch_feed,
    "edgar_atom": fetch_edgar,
    "gdelt_doc": fetch_gdelt,
    "alpaca_news": fetch_alpaca,
    "yfinance_news": fetch_yfinance_news,
}


# --------------------------------------------------------------- run context

@dataclass
class RunContext:
    """Everything a fetcher needs that is not the registry row.

    Every external effect is a METHOD here, so a test substitutes the context
    and no test needs a socket, a key, or a clock.
    """

    since: str = ""
    until: str = ""
    max_rows: int | None = None
    resume: bool = False
    paced: bool = True
    #: Wall-clock budget for ONE source. A fetcher checks it the same way it
    #: checks `max_rows`, and a source that exceeds it stops with what it has.
    #: See `SOURCE_BUDGET_S` for why this is not optional.
    budget_s: float = 0.0
    cursor: dict = field(default_factory=dict)
    _t0: float = field(default_factory=time.time)
    _universe: list[str] | None = None

    # -- effects (each one is mocked in tests) ---------------------------
    def http_get(self, url: str, headers: dict | None = None) -> bytes:
        return _http_get(url, headers=headers)

    def alpaca_credential(self) -> tuple[str | None, str | None, str]:
        return alpaca_credential()

    def yf_news(self, symbol: str) -> list[dict]:
        import yfinance as yf

        def pull():
            return list(yf.Ticker(symbol).news or [])

        return call_with_timeout(pull, YF_CALL_TIMEOUT_S, f"yfinance {symbol}") or []

    # -- pacing and budget ----------------------------------------------
    def pace(self, src: registry.NewsSource) -> float:
        return src.min_interval_s if self.paced else 0.0

    def budget_spent(self, res: FetchResult) -> bool:
        """Has this source spent its row budget OR its wall-clock budget?

        The wall-clock half was added on 2026-09-11 after the live pull hung:
        `yfinance.Ticker(...).news` goes through curl_cffi with no timeout of
        ours, Yahoo held the connection open, and the whole sweep sat on one
        ESTABLISHED socket for five minutes with 0.1s of CPU. `_http_get` has
        a timeout; a third-party library's own session does not, and this repo
        has paid for that once already (the 2.5 h suite hang, conftest.py).
        """
        if self.max_rows and len(res.items) >= self.max_rows:
            return True
        if self.budget_s and (time.time() - self._t0) > self.budget_s:
            res.failures.append(
                f"source wall-clock budget of {self.budget_s:.0f}s spent; stopping with "
                f"{len(res.items)} rows. This is a BUDGET, not a failure — the next "
                f"run resumes from the cursor.")
            return True
        return False

    def restart_clock(self) -> None:
        """Start this source's wall-clock budget. Called once per source."""
        self._t0 = time.time()

    # -- inputs ----------------------------------------------------------
    def universe_symbols(self) -> list[str]:
        if self._universe is not None:
            return self._universe
        out: list[str] = []
        p = universe_path()
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sym = d.get("symbol")
                if isinstance(sym, str) and sym.strip():
                    out.append(sym.strip().upper())
        self._universe = out
        return out

    def theme_queries(self) -> list[str]:
        """One OR-of-tickers GDELT query per basket in `theme_baskets.yaml`.

        The basket shape is `themes: {<name>: {members: [{ticker, available_from}]}}`
        — NOT a bare symbol list, which is what a first pass here assumed, and
        which silently produced zero theme queries while looking like it worked.
        A shape that yields nothing is returned as an explicit empty list only
        when the FILE is missing; a file that parses but matches no member is a
        bug, so `themes` is read for `members[].ticker` explicitly.
        """
        p = Path(_config.BACKEND_DIR) / "data" / "theme_baskets.yaml"
        if not p.exists():
            return []
        try:
            import yaml
            payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            return []
        themes = payload.get("themes") or {}
        out = []
        if isinstance(themes, dict):
            for body in themes.values():
                members = body.get("members") if isinstance(body, dict) else None
                syms: list[str] = []
                for m in members or []:
                    t = m.get("ticker") if isinstance(m, dict) else m
                    if isinstance(t, str) and t.strip():
                        syms.append(t.strip())
                if syms:
                    # GDELT's query length is bounded; 10 names per theme is
                    # plenty to catch the theme's news without a 414.
                    out.append("(" + " OR ".join(syms[:10]) + ")")
        return out


# ------------------------------------------------------------------- writing

def _read_cursor(source_id: str) -> dict:
    p = cursor_path(source_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_cursor(source_id: str, cur: dict) -> None:
    p = cursor_path(source_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cur, indent=1, sort_keys=True), encoding="utf-8")


def _known_raw_ids(source_id: str, days: int = DEDUPE_LOOKBACK_DAYS) -> set[str]:
    """Every `raw_id` written for this source in the last `days` UTC days."""
    out: set[str] = set()
    d = source_dir(source_id)
    if not d.exists():
        return out
    today = _now().date()
    wanted = {(today - timedelta(days=i)).isoformat() for i in range(days + 1)}
    for f in d.glob("*.jsonl"):
        if f.stem not in wanted:
            continue
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.add(json.loads(line).get("raw_id") or "")
            except json.JSONDecodeError:
                continue
    out.discard("")
    return out


def _row(src: registry.NewsSource, item: dict, first_seen: datetime, tbl) -> dict:
    """One corpus row, with entity resolution applied. `first_seen_utc` is OURS."""
    title = (item.get("title") or "").strip()
    body = (item.get("body") or "").strip()[:MAX_BODY]
    tickers = [str(t).upper() for t in (item.get("tickers") or []) if str(t).strip()]
    tags = list(item.get("entity_tags") or [])
    if not tickers:
        text = item.get("resolve_text") or f"{title}\n{body}"
        res = entities.resolve(text, tbl=tbl)
        tickers = list(res.tickers)
        tags.extend(f"resolved:{sym}={rule}" for sym, rule in res.how.items())
    return {
        "source": src.id,
        "first_seen_utc": _iso(first_seen),
        "published_utc": _iso(item.get("published")),
        "tz_source": src.stamp_tz,
        "url": item.get("url") or "",
        "title": title,
        "body": body,
        "lang": item.get("lang") or src.language,
        "tickers": tickers,
        "entity_tags": tags,
        "raw_id": str(item.get("raw_id") or item.get("url") or "")[:512],
        "pit_grade": src.pit_grade,
    }


# ---------------------------------------------------------------------- pull

def pull_source(source_id: str, ctx: RunContext | None = None) -> dict:
    """Pull one registry source. Returns the receipt; writes rows, cursor, receipt.

    An id not in the registry raises `UnknownSource` BEFORE any effect —
    roadmap N-B's "refusal at parse".
    """
    src = registry.get(source_id)
    ctx = ctx or RunContext()
    ctx.cursor = _read_cursor(source_id) if ctx.resume else {}
    t0 = time.time()
    started = _now()
    tbl = entities.tables()

    receipt: dict[str, Any] = {
        "job": "news_pull", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "source": src.id, "provider": src.provider, "region": src.region,
        "tier": src.tier, "pit_grade": src.pit_grade, "label_source": src.label_source,
        "parser": src.parser, "min_interval_s": src.min_interval_s,
        "started_utc": _iso(started), "requested": 0, "received": 0, "new": 0,
        "dupes": 0, "failures": [], "calls": 0, "rows_by_day": {},
        "resolved": 0, "unresolved": 0, "resolution_rate": None,
        "consecutive_zero_runs": 0, "status": "OK",
    }

    if not src.implemented or src.parser == "none":
        receipt["status"] = "NOT_IMPLEMENTED"
        receipt["failures"].append(f"REFUSED: {src.id} — {src.implemented_note}")
        receipt["wall_s"] = round(time.time() - t0, 2)
        receipt["written_utc"] = _iso(_now())
        _emit(receipt, src)
        return receipt

    fetcher = FETCHERS[src.parser]
    ctx.restart_clock()
    res = fetcher(src, ctx)
    receipt["calls"] = res.calls
    receipt["failures"].extend(res.failures)
    receipt["received"] = len(res.items)
    receipt["requested"] = ctx.max_rows or len(res.items)

    if res.refused:
        # A refusal is NOT a zero-row run: it names itself, and counting it RED
        # would bury the named cause under a generic one.
        receipt["status"] = "REFUSED"
        receipt["failures"].insert(0, res.refused)
        receipt["consecutive_zero_runs"] = int(ctx.cursor.get("consecutive_zero_runs", 0))
        receipt["wall_s"] = round(time.time() - t0, 2)
        receipt["written_utc"] = _iso(_now())
        _emit(receipt, src)
        return receipt

    known = _known_raw_ids(src.id)
    by_day: dict[str, list[dict]] = {}
    seen_this_run: set[str] = set()
    for item in res.items:
        if ctx.max_rows and receipt["new"] >= ctx.max_rows:
            break
        first_seen = _now()
        row = _row(src, item, first_seen, tbl)
        rid = row["raw_id"]
        if not rid or rid in known or rid in seen_this_run:
            receipt["dupes"] += 1
            continue
        seen_this_run.add(rid)
        by_day.setdefault(first_seen.date().isoformat(), []).append(row)
        receipt["new"] += 1
        if row["tickers"]:
            receipt["resolved"] += 1
        else:
            receipt["unresolved"] += 1

    d = source_dir(src.id)
    if by_day:
        d.mkdir(parents=True, exist_ok=True)
    for day, rows in sorted(by_day.items()):
        with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        receipt["rows_by_day"][day] = len(rows)

    graded = receipt["resolved"] + receipt["unresolved"]
    receipt["resolution_rate"] = round(receipt["resolved"] / graded, 4) if graded else None

    # THE RED RULE. A zero-RECEIVED run is the one that counts: zero NEW rows
    # with rows received is a healthy feed we already have.
    zeros = int(ctx.cursor.get("consecutive_zero_runs", 0))
    zeros = zeros + 1 if receipt["received"] == 0 else 0
    receipt["consecutive_zero_runs"] = zeros
    if zeros >= 2:
        receipt["status"] = "RED"
        receipt["failures"].append(
            f"RED: {src.id} returned zero rows on {zeros} consecutive runs. "
            f"Check the parser before the feed — a wrong parser and a dead feed "
            f"look identical (Nikkei's RDF and EDGAR's getcompany both did)."
        )
    elif receipt["failures"] and receipt["new"] == 0:
        receipt["status"] = "DEGRADED"

    _write_cursor(src.id, {
        "source": src.id,
        "last_run_utc": _iso(started),
        "next_cursor": res.next_cursor or ctx.cursor.get("next_cursor", ""),
        "next_offset": (res.next_offset if res.next_offset is not None
                        else ctx.cursor.get("next_offset", 0)),
        "consecutive_zero_runs": zeros,
        "runs": int(ctx.cursor.get("runs", 0)) + 1,
        "rows_written_total": int(ctx.cursor.get("rows_written_total", 0)) + receipt["new"],
        "note": ("next_cursor is only meaningful for sources with a native incremental "
                 "cursor (Alpaca's created_at); next_offset is where a symbol-by-symbol "
                 "sweep resumes, so a capped run does not re-pull the same prefix for ever."),
    })

    receipt["wall_s"] = round(time.time() - t0, 2)
    receipt["written_utc"] = _iso(_now())
    _emit(receipt, src)
    return receipt


def _emit(receipt: dict, src: registry.NewsSource) -> None:
    p = receipt_path(src.id, _stamp())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    receipt["receipt_path"] = str(p)


def _gap_before(next_id: str, prev_id: str) -> float:
    """Seconds to wait between two sources.

    A per-source `min_interval_s` paces calls WITHIN a source and says nothing
    about the gap between two sources that share a provider — and a provider
    rate-limits by IP, not by our loop structure. On 2026-09-11
    `reddit_securityanalysis_rss` 429'd because it followed
    `reddit_algotrading_rss` half a second later. Consecutive sources from the
    same provider now wait twice that provider's interval.
    """
    try:
        nxt, prev = registry.get(next_id), registry.get(prev_id)
    except registry.UnknownSource:
        return 0.5
    same = nxt.provider.split()[0].lower() == prev.provider.split()[0].lower()
    return max(0.5, nxt.min_interval_s * (2.0 if same else 1.0))


def pull_all(source_ids: Iterable[str] | None = None, ctx: RunContext | None = None) -> dict:
    """Every pullable source in registry order, each with its own receipt."""
    t0 = time.time()
    ids = list(source_ids) if source_ids else [s.id for s in registry.pullable()]
    per: list[dict] = []
    for i, sid in enumerate(ids):
        c = RunContext(
            since=(ctx.since if ctx else ""), until=(ctx.until if ctx else ""),
            max_rows=(ctx.max_rows if ctx else None), resume=(ctx.resume if ctx else False),
            paced=(ctx.paced if ctx else True), budget_s=(ctx.budget_s if ctx else 0.0),
        )
        if ctx is not None:
            c.http_get = ctx.http_get            # type: ignore[method-assign]
            c.yf_news = ctx.yf_news              # type: ignore[method-assign]
            c.alpaca_credential = ctx.alpaca_credential  # type: ignore[method-assign]
            c._universe = ctx._universe
        try:
            per.append(pull_source(sid, c))
        except registry.UnknownSource as e:
            per.append({"source": sid, "status": "REFUSED", "failures": [str(e)]})
        if i + 1 < len(ids) and (ctx is None or ctx.paced):
            _sleep(_gap_before(ids[i + 1], sid))
    red = [r["source"] for r in per if r.get("status") == "RED"]
    refused = [r["source"] for r in per if r.get("status") == "REFUSED"]
    total_new = sum(int(r.get("new", 0)) for r in per)
    resolved = sum(int(r.get("resolved", 0)) for r in per)
    graded = resolved + sum(int(r.get("unresolved", 0)) for r in per)
    summary = {
        "job": "news_pull_all", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "sources": len(ids), "rows_new": total_new,
        "resolution_rate": round(resolved / graded, 4) if graded else None,
        "red": red, "refused": refused,
        "registry": registry.meta(),
        "name_table": entities.stats(),
        "corpus_dir": str(corpus_dir()),
        "wall_s": round(time.time() - t0, 2),
        "written_utc": _iso(_now()),
        "per_source": [{k: r.get(k) for k in
                        ("source", "status", "received", "new", "dupes",
                         "resolution_rate", "calls", "wall_s")} for r in per],
        "headline": (f"{total_new:,} new rows over {len(ids)} sources; "
                     f"{len(red)} RED, {len(refused)} refused"),
    }
    p = receipt_path("ALL", _stamp())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    summary["receipt_path"] = str(p)
    return summary


# ---------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--source", default="all", help="a registry id, or 'all'")
    ap.add_argument("--since", default="", help="ISO start (sources with a native cursor)")
    ap.add_argument("--until", default="", help="ISO end")
    ap.add_argument("--resume", action="store_true", help="continue from the source's cursor")
    ap.add_argument("--max-rows", type=int, default=None, help="cap NEW rows per source")
    ap.add_argument("--no-pace", action="store_true", help="skip inter-call sleeps (tests only)")
    ap.add_argument("--budget-s", type=float, default=SOURCE_BUDGET_S,
                    help="wall-clock budget per source; 0 disables (default %(default)s)")
    ap.add_argument("--list", action="store_true", help="print the registry and exit")
    a = ap.parse_args(argv)

    if a.list:
        for s in registry.load():
            mark = "pull" if (s.implemented and s.parser != "none") else "----"
            print(f"{mark}  {s.id:34s} {s.region:7s} {s.pit_grade:16s} "
                  f"label={str(s.label_source):5s} {s.provider}")
        return 0

    ctx = RunContext(since=a.since, until=a.until, max_rows=a.max_rows,
                     resume=a.resume, paced=not a.no_pace, budget_s=a.budget_s)
    if a.source == "all":
        out = pull_all(ctx=ctx)
    else:
        try:
            out = pull_source(a.source, ctx)
        except registry.UnknownSource as e:
            print(str(e))
            return 2
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
