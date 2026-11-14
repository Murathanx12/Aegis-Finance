"""CH-22 / M-universe -- the TICKER HUB: everything we hold on one ticker, from our own files.

Owner (2026-11-14): "when I write NVIDIA as a ticker, I should be able to see all of the
news, all of the stock forecast, everything about that ... I can open Aegis and get all
the information I need from there."

WHAT THIS IS
============
A local, deterministic, no-LLM index over what this PC already collected:

* NEWS -- the news corpus (`news_corpus/<source>/<day>.jsonl`, ~30 feeds) and the web
  reader's page store (`news_corpus/dowjones/<publisher>/<day>/<sha>.json`: article pages,
  plus the headline links on the front and search pages it read), tagged by ticker;
* the world digest's typed rows (`news_corpus/_digest_cache/extract_wd_v1.jsonl`), joined
  by URL so a headline shows its event type when one was typed;
* FORECASTS -- the frozen forecast ledger (`predictions.jsonl`), open and resolved;
* EVENT NODES -- `event_nodes/event_nodes.jsonl` as known at build time;
* RELATED NAMES -- same sector (`potential_universe` identity) and universe-graph links;
* the CALENDAR is read live per request (`forward_calendar.next_dates`, point in time).

HOW A ROW GETS A TICKER (each tag records its method; the page prints it)
==========================================================================
In order, first method wins per ticker:

1. ``source_field`` -- a symbol the source row already carries: the provider's own tag,
   an explicit token the collector recorded (`resolved:X=cashtag|venue_ticker|
   adr_local_code|paren_ticker`), the reader's `tickers_named`, a generic `ticker` field.
   A collector NAME match (`resolved:X=name`) is NOT trusted: the inventory found
   "Six dead in Krakow" -> PPLI ("People") and "Mississippi election" -> FCF ("First"),
   so those rows are re-resolved by rule 4. A word-like symbol (`A`, `IT`, `ON`, `ALL`,
   `NOW`, ... `config.EVENT_NODES_BAREWORD_SYMBOLS`) is never taken from a bare
   parenthesis.
2. ``sec_cik`` -- an SEC row's `cik:` tag through `official/company_tickers.json`.
   ``reader_lane`` -- a reader ARTICLE page reached while looking up that ticker;
   ``reader_search`` -- a headline link on a reader SEARCH page for that ticker.
3. ``digest_typed`` -- the world digest's VERIFIED `tickers` for the same URL.
4. ``text_token`` / ``name_match`` -- `event_nodes.strict_tickers` on the title and the
   first `TICKER_HUB_BODY_CHARS` of the body: `$NVDA`, `(NASDAQ: NVDA)`, issuer names and
   aliases with the CH-35 guards (length floor, common words need an ATTACHED cue,
   lowercase surface refused), plus `config.TICKER_HUB_CASED_ALIASES` (case-sensitive
   short names: Meta, AMD, TSMC, Apple ...).

Untagged rows are NOT stored; the build prints how many rows stayed untagged per
source so the owner can decide whether a classifier is worth it.

INCREMENTAL, AND WHAT A REQUEST READS
=====================================
The build keeps cursors in `state.json` (byte offset per corpus file, seen page files per
reader day folder, the digest offset). A request NEVER scans the corpus: it reads
`postings_<YYYY-MM>.json` (ticker -> [[first_seen epoch, byte offset]]) and seeks the
rows in `rows_<YYYY-MM>.jsonl`. Every file is written temp -> replace. An index older than
`TICKER_HUB_STALE_HOURS` is reported STALE with its age.

DESCRIPTIVE ONLY. Nothing here ranks, scores or recommends; a forecast row is printed
as written and graded, never as advice.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import urlsplit

from backend import config as C
from backend.services import discovery_autopsy as DA
from backend.services import disk_guard as DG
from backend.services import event_nodes as EN
from backend.services import news_entities as NE

SCHEMA = "ticker-hub/1"
STATE_SCHEMA = "ticker-hub-state/1"

# refusal codes (each a red, non-zero exit in the CLI)
CORPUS_MISSING = "CORPUS_MISSING"
CORPUS_UNREADABLE = "CORPUS_UNREADABLE"
ISSUERS_MISSING = "ISSUERS_MISSING"
NOTHING_INDEXED = "NOTHING_INDEXED"
BUILD_LOCKED = "BUILD_LOCKED"

#: tag methods, strongest first (a ticker keeps the first method that named it)
METHODS = ("source_field", "sec_cik", "reader_lane", "reader_search", "digest_typed",
           "text_token", "name_match")
_TOKEN_RULES = frozenset({"cashtag", "paren_ticker", "venue_ticker", "adr_local_code"})

_READER_PUBLISHER = {"wsj": "WSJ", "marketwatch": "MarketWatch", "barrons": "Barron's",
                     "cnbc": "CNBC", "apnews": "AP", "yahoo": "Yahoo", "yahoo_finance": "Yahoo Finance",
                     "scmp": "SCMP", "bbc": "BBC", "ft": "FT", "nikkei": "Nikkei", "sec": "SEC",
                     "treasury": "US Treasury", "bls": "BLS", "fed": "Federal Reserve",
                     "reuters": "Reuters"}
_SUFFIX_PUBLISHER_WORDS = ("wsj", "wall street journal", "ap news", "associated press", "cnbc",
                           "barron", "marketwatch", "financial times", "ft.com", "bbc", "yahoo",
                           "scmp", "south china morning post", "nikkei", "reuters")
_TITLE_SUFFIX = re.compile(r"\s+[-–—|]\s+([^-–—|]{2,60})$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TickerHubRefused(RuntimeError):
    """A build that cannot run (missing/unreadable input, nothing indexed, locked)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


# ─────────────────────────────────────────────── small helpers

def _iso(d: Optional[datetime]) -> Optional[str]:
    return None if d is None else d.astimezone(timezone.utc).isoformat(timespec="seconds")


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()[:16]


def url_key(url: str) -> str:
    """Scheme/host lowercased, query and fragment dropped (tracking `?mod=` differs per page)."""
    u = (url or "").strip()
    if not u:
        return ""
    try:
        p = urlsplit(u)
    except ValueError:
        return _sha16(u)
    if p.scheme in ("http", "https") and p.netloc:
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return _sha16(f"{host}{p.path.rstrip('/')}")
    return _sha16(u)


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()[:160]


def row_id(publisher: str, title: str, url: str) -> str:
    """One headline from one publisher is one row, whichever feed or page carried it."""
    nt = _norm_title(title)
    return _sha16(f"t|{publisher.lower()}|{nt}") if nt else _sha16(f"u|{url_key(url)}")


_READER_FETCHERS = frozenset({"web_reader", "reader_pool"})


def _article_body(text: str, title: str) -> str:
    """A reader page snapshot from its headline on: the nav, video carousels and 'more
    videos' lists before it are page chrome (AP's carousel named Nvidia twice above an
    Iran-war article). Unchanged when the headline is not found in the text."""
    anchor = re.sub(r"\s+", " ", (title or "").strip().lower())[:40]
    if len(anchor) >= 12:
        i = text.lower().find(anchor)
        if i > 0:
            return text[i:]
    return text


def _strip_publisher_suffix(title: str) -> str:
    t = (title or "").strip()
    m = _TITLE_SUFFIX.search(t)
    if m and any(w in m.group(1).lower() for w in _SUFFIX_PUBLISHER_WORDS):
        return t[:m.start()].strip()
    return t


def default_data_root() -> Path:
    """`<DATA_DIR>/optimus`, the same root the control router reads the corpus from."""
    return Path(C.DATA_DIR) / "optimus"


def default_paths(data_root: Path) -> dict:
    dr = Path(data_root)
    return {"corpus": dr / "news_corpus",
            "digest": dr / "news_corpus" / "_digest_cache" / "extract_wd_v1.jsonl",
            "cik_map": dr / "official" / "company_tickers.json",
            "issuers": NE.entities_dir() / "issuers.csv",
            "predictions": dr / "predictions.jsonl",
            "event_store": dr / str(C.EVENT_NODES_DIRNAME) / EN.STORE_NAME,
            "graph": dr / "universe_graph",
            "potential_universe": dr / "potential_universe",
            "calendar_root": dr}


def hub_dir(data_root: Path, out: Optional[Path] = None) -> Path:
    return Path(out) if out else Path(data_root) / str(C.TICKER_HUB_DIRNAME)


def _write_json(path: Path, obj: Any) -> None:
    DG.atomic_write_json(path, obj, indent=None, ensure_ascii=True, default=str)


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ─────────────────────────────────────────────── tagging

class Tagger:
    """The tag rules of the module docstring, bound to one issuer table and one
    common-word set. `refused` counts every refused name match by key."""

    def __init__(self, tbl: Any, cik_map: dict, common: dict):
        self.tbl = tbl
        self.cik_map = cik_map
        self.common = common
        self.refused: Counter = Counter()
        self._memo: dict[tuple[str, str], list[dict]] = {}
        self.drop_keys = {str(k).lower() for k in C.TICKER_HUB_DROP_NAME_KEYS}
        for k in C.TICKER_HUB_COMMON_WORD_NAMES:
            self.common.setdefault(str(k).lower(), {"lower": None, "capitalised": None, "listed": "ticker_hub"})
        chrome = [re.escape(p) for p in C.TICKER_HUB_BODY_BOILERPLATE]
        self._chrome_rx = re.compile("|".join(chrome), re.IGNORECASE) if chrome else None
        self.symbols = {DA.norm_ticker(s) for s in tbl.symbols}
        self.bare = {str(s).upper() for s in C.EVENT_NODES_BAREWORD_SYMBOLS}
        cased = {}
        for alias, sym in dict(C.TICKER_HUB_CASED_ALIASES).items():
            s = DA.norm_ticker(sym)
            if s in self.symbols:
                cased[alias] = s
        self.cased = cased
        self.cased_need_context = set(C.TICKER_HUB_CASED_ALIASES_NEED_CONTEXT)
        self._cased_rx = (re.compile(r"(?<![A-Za-z0-9])(" + "|".join(
            re.escape(a) for a in sorted(cased, key=len, reverse=True)) + r")(?![A-Za-z0-9\-])")
            if cased else None)

    def known(self, sym: str) -> bool:
        return DA.norm_ticker(sym) in self.symbols

    def text_tags(self, text: str, where: str) -> list[dict]:
        """Memoised for short texts: a front-page headline recurs on dozens of pages."""
        if not text:
            return []
        if len(text) <= 300:
            k = (where, text)
            hit = self._memo.get(k)
            if hit is None:
                hit = self._text_tags(text, where)
                if len(self._memo) < 200_000:
                    self._memo[k] = hit
            return [dict(t) for t in hit]
        return self._text_tags(text, where)

    def body_tags(self, body: str) -> list[dict]:
        """Body tags with one more guard: in a body longer than TICKER_HUB_SHORT_BODY_CHARS
        (a reader page snapshot carries the site's sidebars and 'most read' lists) a NAME
        must occur at least TICKER_HUB_BODY_MIN_MENTIONS times. An explicit token
        ($NVDA, NASDAQ: NVDA) needs one. Refusals are counted as `body_single_mention:`."""
        if body and self._chrome_rx is not None:
            body = self._chrome_rx.sub(" ", body)
        tags = self.text_tags(body, "body")
        if len(body or "") <= int(C.TICKER_HUB_SHORT_BODY_CHARS):
            return tags
        need = int(C.TICKER_HUB_BODY_MIN_MENTIONS)
        low = body.lower()
        out = []
        for t in tags:
            rule = str(t.get("rule") or "")
            if t["m"] != "name_match" or ":" not in rule:
                out.append(t)
                continue
            kind, key = rule.split(":", 1)
            if kind == "cased_alias":
                n = len(re.findall(r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![A-Za-z0-9])", body))
            elif kind == "foreign_alias":
                n = body.count(key)
            else:
                n = len(re.findall(r"(?<![a-z0-9])" + re.escape(key.lower()) + r"(?![a-z0-9])", low))
            if n >= need:
                out.append(t)
            else:
                self.refused[f"body_single_mention:{key}"] += 1
        return out

    def _text_tags(self, text: str, where: str) -> list[dict]:
        out: list[dict] = []
        hits = EN.strict_tickers(text, self.tbl, self.common, self.refused)
        for sym, rule in hits.items():
            if rule.split(":", 1)[-1] in self.drop_keys:
                self.refused[f"hub_drop_key:{rule}"] += 1
                continue
            m = "text_token" if rule in _TOKEN_RULES else "name_match"
            out.append({"t": DA.norm_ticker(sym), "m": m, "rule": rule, "where": where})
        if self._cased_rx is not None:
            seen = {o["t"] for o in out}
            # another company in a TITLE is context ("Apple, Palantir, AMD ... Stocks"); in a
            # body it is not (a food column's body named "Waters" and carried the fruit into AAPL)
            others = bool(out) and where == "title"
            for mm in self._cased_rx.finditer(text):
                s = self.cased.get(mm.group(1))
                if s and s not in seen:
                    if mm.group(1) in self.cased_need_context and not (
                            others or self._company_context(text, mm.start(), mm.end())):
                        self.refused[f"cased_alias_no_context:{mm.group(1)}"] += 1
                        continue
                    seen.add(s)
                    out.append({"t": s, "m": "name_match", "rule": f"cased_alias:{mm.group(1)}",
                                "where": where})
        return out

    @staticmethod
    def _company_context(text: str, start: int, end: int) -> bool:
        """A possessive ("Apple's"), an attached corporate cue ("Apple shares", "Apple Inc"),
        a context word anywhere in the text (TICKER_HUB_CASED_CONTEXT_WORDS), or a corporate
        cue word within the news_entities window."""
        nxt = text[end:end + 2]
        if nxt in ("'s", "’s"):
            return True
        if EN._ADJ_CUE.match(text[end:end + 30]):
            return True
        low = text.lower()
        if any(w in low for w in C.TICKER_HUB_CASED_CONTEXT_WORDS):
            return True
        return NE._cue_near(low, start, end - start)

    def confirmed(self, sym: str, title: str, body: str) -> bool:
        """Does the row's own text name `sym` (title, or body with one mention)?"""
        s = DA.norm_ticker(sym)
        return any(t["t"] == s for t in self.text_tags(title or "", "title") + self.text_tags(body or "", "body"))

    def source_field_tags(self, tickers: Iterable[Any], entity_tags: Iterable[Any]) -> list[dict]:
        """Rule 1 over a corpus row's `tickers` + `entity_tags` (`resolved:X=rule`)."""
        rules: dict[str, str] = {}
        for t in entity_tags or []:
            s = str(t)
            if s.startswith("resolved:") and "=" in s:
                sym, rule = s[len("resolved:"):].rsplit("=", 1)
                rules[DA.norm_ticker(sym)] = rule
        out = []
        for t in tickers or []:
            sym = DA.norm_ticker(t)
            if not sym:
                continue
            rule = rules.get(sym)
            if rule == "name":
                continue                      # a collector NAME match is re-resolved strictly
            if rule == "paren_ticker" and sym in self.bare:
                continue
            if not self.known(sym):
                self.refused[f"unknown_symbol:{sym}"] += 1
                continue
            out.append({"t": sym, "m": "source_field", "rule": rule or "provider", "where": "field"})
        return out

    def cik_tags(self, entity_tags: Iterable[Any]) -> list[dict]:
        out = []
        for t in entity_tags or []:
            s = str(t)
            if s.startswith("cik:"):
                try:
                    hit = self.cik_map.get(int(s[4:]))
                except ValueError:
                    hit = None
                if hit and self.known(hit):
                    out.append({"t": DA.norm_ticker(hit), "m": "sec_cik", "rule": s, "where": "field"})
        return out


def merge_tags(*groups: Iterable[dict]) -> list[dict]:
    """First method per ticker wins (groups are passed strongest first)."""
    seen: dict[str, dict] = {}
    for g in groups:
        for t in g:
            if t["t"] and t["t"] not in seen:
                seen[t["t"]] = t
    return list(seen.values())


def _bump_common(counter_low: Counter, counter_cap: Counter, title: str, tbl: Any) -> None:
    """The `event_nodes.common_word_keys` counters, accumulated across builds."""
    for _sym, key, pos in tbl.name_matches(title or ""):
        if " " in key or "." in key:
            continue
        surf = title[pos:pos + len(key)]
        (counter_low if surf.islower() else counter_cap)[key] += 1


def common_from_counters(low: Counter, cap: Counter) -> dict:
    share = float(C.EVENT_NODES_COMMON_WORD_LOWER_SHARE)
    out = {}
    for k, n in low.items():
        if n >= int(C.EVENT_NODES_COMMON_WORD_MIN_LOWER) and n / (n + cap.get(k, 0)) >= share:
            out[k] = {"lower": n, "capitalised": cap.get(k, 0)}
    return out


# ─────────────────────────────────────────────── reading the stores

def _corpus_files(corpus: Path, cutoff_day: str) -> list[tuple[str, Path]]:
    skip = set(C.TICKER_HUB_SKIP_SOURCES) | {"dowjones"}
    out = []
    for d in sorted(p for p in corpus.iterdir() if p.is_dir()):
        if d.name.startswith("_") or d.name in skip:
            continue
        for f in sorted(d.glob("*.jsonl")):
            if _DAY.match(f.stem) and f.stem >= cutoff_day:
                out.append((d.name, f))
    return out


def _read_new_lines(path: Path, start: int, end: int) -> tuple[list[str], int]:
    """Complete lines in [start, end); returns (lines, new offset)."""
    lines, off = [], start
    for line, line_end in _read_new_lines_at(path, start, end):
        lines.append(line)
        off = line_end
    return lines, off


def _read_new_lines_at(path: Path, start: int, end: int) -> list[tuple[str, int]]:
    """Complete lines in [start, end), each with the byte offset just past it."""
    with open(path, "rb") as fh:
        fh.seek(start)
        data = fh.read(max(0, end - start))
    out, pos = [], 0
    while True:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break
        out.append((data[pos:nl].decode("utf-8", errors="replace").rstrip("\r"), start + nl + 1))
        pos = nl + 1
    return out


def _as_list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def _corpus_row(src: str, o: dict, tagger: Tagger, typed: dict, now: datetime,
                stats: Counter) -> Optional[dict]:
    """One corpus jsonl row -> a hub row (tagged) or None (untagged / dropped, counted)."""
    title_raw = str(o.get("title") or "")
    entity = [str(t) for t in _as_list(o.get("entity_tags"))]
    not_news = set(getattr(C, "AUTOPSY_NOT_NEWS_TAGS", ()))
    if any(t in not_news for t in entity):
        stats["dropped_not_news"] += 1
        return None
    if title_raw.strip() == "read_next" or any(t.startswith("column:search_") and t.endswith("_read_next")
                                               for t in entity):
        stats["skipped_read_next"] += 1
        return None
    fs = DA._utc(o.get("first_seen_utc"))
    pub = DA.timed_utc(o.get("published_utc"))
    known = fs or pub
    if known is None:
        stats["dropped_undated"] += 1
        return None
    if known > now:
        stats["dropped_after_now"] += 1
        return None
    url = str(o.get("url") or o.get("index_url") or "")
    publisher, region, title, _basis = EN.publisher_region(src, title_raw, url)
    reader_row = src.startswith("dj_reader_") or str(o.get("fetcher") or "") in _READER_FETCHERS
    raw_body = EN.clean_text(str(o.get("body") or o.get("text") or ""))
    body = (_article_body(raw_body, title) if reader_row else raw_body)[:int(C.TICKER_HUB_BODY_CHARS)]
    uk = url_key(url)
    ty = typed.get(uk) if uk else None
    generic = [o.get("ticker")] if o.get("ticker") else []
    g_field = tagger.source_field_tags(_as_list(o.get("tickers")) + generic, entity)
    if reader_row:
        # the reader's `tickers` is the LANE it was browsing, not a provider tag: an
        # annuity column read from the NTLA lane carried NTLA. Kept only when the text
        # itself names the ticker (one mention is enough), and labelled reader_lane.
        lane = [t for t in g_field if t["rule"] == "provider"]
        g_field = [t for t in g_field if t["rule"] != "provider"]
        for t in lane:
            if tagger.confirmed(t["t"], title, body):
                g_field.append({**t, "m": "reader_lane", "rule": "reader_tickers"})
            else:
                stats["reader_lane_unconfirmed"] += 1
    g_cik = tagger.cik_tags(entity) if src.startswith("sec_") else []
    g_digest = [{"t": DA.norm_ticker(t), "m": "digest_typed", "rule": "world_digest", "where": "field"}
                for t in (ty or {}).get("tickers") or [] if tagger.known(t)]
    kind = EN.kind_of(src)
    g_title = [] if kind == "filing" else tagger.text_tags(title, "title")
    g_body = tagger.body_tags(body)
    tags = merge_tags(g_field, g_cik, g_digest, g_title, g_body)
    stats[f"rows_read:{src}"] += 1
    if not tags:
        stats[f"rows_untagged:{src}"] += 1
        return None
    return {"id": row_id(publisher, title, url), "source": src, "publisher": publisher, "kind": kind,
            "first_seen_utc": _iso(known), "published_utc": _iso(pub), "title": title[:300],
            "url": url[:600], "url_key": uk, "feeds": [src], "regions": [region] if region else [],
            "tags": tags}


def _reader_rows(pub_dir: str, page: dict, tagger: Tagger, now: datetime,
                 stats: Counter) -> list[dict]:
    """A reader page -> hub rows: the article itself, or the headline links of a
    front/search page (each link its own row, tagged only by its own text)."""
    src = f"reader:{pub_dir}"
    if str(page.get("page_class") or "OK") != "OK":
        stats["reader_pages_not_ok"] += 1
        return []
    kind = str(page.get("page_kind") or "")
    if kind in set(C.TICKER_HUB_SKIP_PAGE_KINDS):
        stats[f"reader_skipped_kind:{kind}"] += 1
        return []
    fs = DA._utc(page.get("first_seen_utc"))
    pub = DA.timed_utc(page.get("published_utc"))
    known = fs or pub
    if known is None:
        stats["dropped_undated"] += 1
        return []
    if known > now:
        stats["dropped_after_now"] += 1
        return []
    publisher = _READER_PUBLISHER.get(pub_dir, pub_dir)
    rb = page.get("reached_by") if isinstance(page.get("reached_by"), dict) else {}
    lane_t = DA.norm_ticker(rb.get("ticker")) if rb.get("ticker") else ""
    out: list[dict] = []
    if kind == "article":
        title = _strip_publisher_suffix(str(page.get("title") or ""))
        url = str(page.get("url") or "")
        text = _article_body(EN.clean_text(str(page.get("text") or "")), title)[:int(C.TICKER_HUB_BODY_CHARS)]
        g_lane = ([{"t": lane_t, "m": "reader_lane", "rule": str(rb.get("lane") or "lane"), "where": "field"}]
                  if lane_t and tagger.known(lane_t) else [])
        if g_lane and not tagger.confirmed(lane_t, title, text):
            stats["reader_lane_unconfirmed"] += 1
            g_lane = []
        # `tickers_named` includes quote chips ("NVDA -3.2%") from the page's market strip,
        # so a Barron's retirement column carried NVDA: kept only when the text names it.
        g_named = []
        for t in tagger.source_field_tags(_as_list(page.get("tickers_named")), []):
            if t["t"] in tagger.bare:
                continue
            if tagger.confirmed(t["t"], title, text):
                g_named.append({**t, "rule": "tickers_named"})
            else:
                stats["tickers_named_unconfirmed"] += 1
        tags = merge_tags(g_named, g_lane, tagger.text_tags(title, "title"), tagger.body_tags(text))
        stats[f"rows_read:{src}"] += 1
        if not tags:
            stats[f"rows_untagged:{src}"] += 1
            return []
        out.append({"id": row_id(publisher, title, url), "source": src, "publisher": publisher,
                    "kind": "article", "first_seen_utc": _iso(known), "published_utc": _iso(pub),
                    "title": title[:300], "url": url[:600], "url_key": url_key(url), "feeds": [src],
                    "regions": [], "tags": tags})
        return out
    # front / search pages: their outbound headline links
    min_c, min_w = int(C.TICKER_HUB_MIN_LINK_CHARS), int(C.TICKER_HUB_MIN_LINK_WORDS)
    for ln in _as_list(page.get("outbound_links")):
        if not isinstance(ln, dict):
            continue
        text = " ".join(str(ln.get("text") or "").split())
        url = str(ln.get("url") or "")
        if len(text) < min_c or len(text.split()) < min_w or not url:
            stats["reader_links_too_short"] += 1
            continue
        stats[f"rows_read:{src}"] += 1
        g_search = ([{"t": lane_t, "m": "reader_search", "rule": str(rb.get("lane") or "search"),
                      "where": "field"}] if kind == "search" and lane_t and tagger.known(lane_t)
                    and tagger.confirmed(lane_t, text, "") else [])
        tags = merge_tags(g_search, tagger.text_tags(text, "title"))
        if not tags:
            stats[f"rows_untagged:{src}"] += 1
            continue
        out.append({"id": row_id(publisher, text, url), "source": src, "publisher": publisher,
                    "kind": "headline_link", "first_seen_utc": _iso(known), "published_utc": None,
                    "title": text[:300], "url": url[:600], "url_key": url_key(url), "feeds": [src],
                    "regions": [], "tags": tags})
    return out


def _update_typed(digest: Path, state: dict, typed: dict, stats: Counter) -> None:
    """Append the digest rows written since the last build into the URL -> typed map."""
    if not digest.is_file():
        stats["digest_missing"] += 1
        return
    cur = state.setdefault("digest", {"offset": 0})
    size = digest.stat().st_size
    start = int(cur.get("offset") or 0)
    if size < start:
        start = 0
    lines, off = _read_new_lines(digest, start, size)
    for line in lines:
        try:
            row = json.loads(line).get("row") or {}
        except (ValueError, AttributeError):
            stats["digest_bad_lines"] += 1
            continue
        uk = url_key(str(row.get("url") or ""))
        if not uk:
            continue
        typed[uk] = {"event_type": row.get("event_type"), "topic": (row.get("topic") or "")[:160],
                     "sentiment": row.get("sentiment"),
                     "tickers": [DA.norm_ticker(t) for t in row.get("tickers") or [] if t],
                     "model": row.get("extract_model")}
        stats["digest_rows_read"] += 1
    cur["offset"] = off


# ─────────────────────────────────────────────── shards

def _month(iso: str) -> str:
    return iso[:7]


def shard_paths(hd: Path, month: str) -> tuple[Path, Path]:
    return hd / f"rows_{month}.jsonl", hd / f"postings_{month}.json"


def _epoch(iso: Optional[str]) -> int:
    d = DA._utc(iso) if iso else None
    return int(d.timestamp()) if d else 0


def _read_shard(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            out[r["id"]] = r
    return out


def _fold(old: dict, new: dict) -> dict:
    """Same headline seen again: earliest first_seen, union of feeds/regions/tags."""
    if new["first_seen_utc"] < old["first_seen_utc"] and _month(new["first_seen_utc"]) == _month(old["first_seen_utc"]):
        old["first_seen_utc"] = new["first_seen_utc"]
        old["source"] = new["source"]
        old["url"] = new["url"] or old["url"]
        old["url_key"] = new["url_key"] or old["url_key"]
    if not old.get("published_utc") and new.get("published_utc"):
        old["published_utc"] = new["published_utc"]
    old["feeds"] = sorted(set(old.get("feeds") or []) | set(new.get("feeds") or []))
    old["regions"] = sorted(set(old.get("regions") or []) | set(new.get("regions") or []))
    old["tags"] = merge_tags(old.get("tags") or [], new.get("tags") or [])
    return old


def _write_shard(hd: Path, month: str, rows: dict[str, dict]) -> dict:
    """rows newest first; postings carry [epoch, byte offset] per ticker/source/all."""
    rp, pp = shard_paths(hd, month)
    ordered = sorted(rows.values(), key=lambda r: (r["first_seen_utc"], r["id"]), reverse=True)
    parts: list[str] = []
    off = 0
    post: dict[str, Any] = {"schema": SCHEMA, "month": month, "n_rows": len(ordered),
                            "ticker": {}, "source": {}, "all": []}
    for r in ordered:
        line = json.dumps(r, ensure_ascii=True, separators=(",", ":")) + "\n"
        ep = _epoch(r["first_seen_utc"])
        post["all"].append([ep, off])
        post["source"].setdefault(r["source"], []).append([ep, off])
        for t in {t["t"] for t in r.get("tags") or []}:
            post["ticker"].setdefault(t, []).append([ep, off])
        parts.append(line)
        off += len(line.encode("utf-8"))
    DG.atomic_write_text(rp, "".join(parts) or "\n")
    _write_json(pp, post)
    return {"month": month, "rows": len(ordered), "bytes": off}


# ─────────────────────────────────────────────── universe / forecasts / events / related

def load_universe(paths: dict, tbl: Any) -> dict[str, dict]:
    """{sym: {name, sector, industry, gics_sector}} for every issuer-table symbol.
    `sector` is the potential_universe identity label (the universe graph's sectors);
    `gics_sector` is `config.WHY_MOVED_TICKER_SECTOR` where it knows the name."""
    import csv
    out: dict[str, dict] = {}
    ip = Path(paths["issuers"])
    with ip.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            s = DA.norm_ticker(row.get("symbol"))
            if s:
                out[s] = {"name": (row.get("primary_name") or "").strip() or None,
                          "sector": None, "gics_sector": None}
    pu_dir = Path(paths["potential_universe"])
    files = sorted(pu_dir.glob("*.jsonl")) if pu_dir.is_dir() else []
    if files:
        with files[-1].open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                ident = r.get("identity") if isinstance(r, dict) else None
                if isinstance(ident, dict) and r.get("symbol"):
                    s = DA.norm_ticker(r["symbol"])
                    rec = out.setdefault(s, {"name": None, "sector": None, "gics_sector": None})
                    rec["sector"] = ident.get("sector") or rec.get("sector")
    gics = dict(getattr(C, "WHY_MOVED_TICKER_SECTOR", {}) or {})
    for s, v in gics.items():
        ns = DA.norm_ticker(s)
        if ns in out:
            out[ns]["gics_sector"] = v
    return out


def _forecast_compact(r: dict) -> dict:
    det = r.get("resolution_detail") if isinstance(r.get("resolution_detail"), dict) else {}
    return {"id": r.get("prediction_id"), "made_at": r.get("made_at"), "specialist": r.get("specialist"),
            "observable": r.get("observable"), "probability": r.get("probability"),
            "threshold": r.get("threshold"), "benchmark": r.get("benchmark"),
            "horizon_days": r.get("horizon_days"), "resolves_after": r.get("resolves_after"),
            "resolved_at": r.get("resolved_at"), "outcome": r.get("outcome"), "brier": r.get("brier"),
            "realised_return": det.get("realised_return"), "void_reason": r.get("void_reason"),
            "model": r.get("model"), "thesis": (r.get("thesis") or "")[:280] or None}


def build_forecasts(pred: Path, hd: Path, state: dict, stats: Counter) -> dict:
    """Per-ticker compact forecast rows, rebuilt whole when the ledger changed (it is
    rewritten in place, so no byte cursor is valid). Streamed, read-only."""
    from backend.services import forecast_ledger as FL
    if not FL.exists(pred):
        stats["forecast_ledger_missing"] += 1
        return {"status": "LEDGER_MISSING", "path": str(pred)}
    try:
        st = Path(pred).stat()
        fp = [st.st_size, st.st_mtime_ns]
    except OSError:
        fp = None
    prev = state.get("forecasts") or {}
    if fp is not None and prev.get("fingerprint") == fp and (hd / "forecasts.jsonl").is_file():
        return {**prev, "status": "UNCHANGED"}
    by: dict[str, list] = {}
    n = bad = 0
    for line in FL.logical_lines(pred):
        try:
            r = json.loads(line)
        except ValueError:
            bad += 1
            continue
        t = DA.norm_ticker(r.get("ticker"))
        if not t:
            continue
        n += 1
        by.setdefault(t, []).append(_forecast_compact(r))
    parts, index, off = [], {}, 0
    for t in sorted(by):
        rows = sorted(by[t], key=lambda x: str(x.get("made_at") or ""), reverse=True)
        line = json.dumps({"ticker": t, "rows": rows}, ensure_ascii=True, separators=(",", ":")) + "\n"
        index[t] = off
        parts.append(line)
        off += len(line.encode("utf-8"))
    DG.atomic_write_text(hd / "forecasts.jsonl", "".join(parts) or "\n")
    _write_json(hd / "forecasts_index.json", index)
    out = {"status": "REBUILT", "fingerprint": fp, "rows": n, "bad_lines": bad, "tickers": len(by),
           "path": str(pred)}
    state["forecasts"] = out
    return out


def build_events(store: Path, hd: Path, now: datetime, stats: Counter) -> dict:
    """{ticker: [node brief + first evidence title]} as the event store stood at `now`."""
    if not Path(store).is_file():
        _write_json(hd / "events.json", {"tickers": {}, "status": "STORE_MISSING"})
        return {"status": "STORE_MISSING", "path": str(store)}
    known = EN.nodes_known_at(Path(store), now)
    by: dict[str, list] = {}
    for n in known["nodes"].values():
        fs = DA._utc(n.get("first_seen_utc"))
        if fs is None or fs > now:
            continue
        ev = n.get("evidence") or []
        title = (ev[0].get("title") if ev and isinstance(ev[0], dict) else None)
        for t, role in EN.roles_of(n).items():
            b = EN.node_brief(n, t, now, role)
            b["title"] = (title or "")[:300] or None
            by.setdefault(DA.norm_ticker(t), []).append(b)
    for t in by:
        by[t].sort(key=lambda b: (str(b.get("first_seen_utc") or "")), reverse=True)
    meta = {k: known.get(k) for k in ("newest_build_utc", "age_hours", "stale", "stale_after_hours")}
    _write_json(hd / "events.json", {"tickers": by, "status": "OK", **meta})
    return {"status": "OK", "nodes": len(known["nodes"]), "tickers": len(by), **meta}


def build_related(graph_dir: Path, hd: Path, now: datetime) -> dict:
    """Universe-graph neighbours per company, as the newest graph built at or before now."""
    if not Path(graph_dir).is_dir():
        _write_json(hd / "related.json", {"tickers": {}, "graph": {"status": "GRAPH_MISSING"}})
        return {"status": "GRAPH_MISSING"}
    try:
        graph, gmeta = EN.select_graph(Path(graph_dir), now)
    except Exception as exc:                                           # noqa: BLE001
        gmeta = {"status": f"GRAPH_UNREADABLE: {type(exc).__name__}: {str(exc)[:160]}"}
        graph = None
    by: dict[str, list] = {}
    if graph is not None:
        comps = [nid.split(":", 1)[1] for nid in graph.nodes if str(nid).startswith("company:")]
        for s in comps:
            nb = EN.graph_neighbours(graph, s, gmeta)
            if nb:
                by[DA.norm_ticker(s)] = nb
    gm = {k: v for k, v in (gmeta or {}).items() if k != "skipped_after_now"}
    _write_json(hd / "related.json", {"tickers": by, "graph": gm})
    return {**gm, "companies_with_links": len(by)}


# ─────────────────────────────────────────────── the build

class _Lock:
    def __init__(self, path: Path):
        self.path = path
        self.fd: Optional[int] = None

    def __enter__(self) -> "_Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            age = time.time() - self.path.stat().st_mtime
            if age < 6 * 3600:
                raise TickerHubRefused(BUILD_LOCKED, f"{self.path} exists ({age:.0f}s old): "
                                                     f"another build is running")
            self.path.unlink()
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(self.fd, str(os.getpid()).encode())
        return self

    def __exit__(self, *exc: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except OSError:
            pass


def check_inputs(paths: dict) -> None:
    corpus = Path(paths["corpus"])
    if not corpus.is_dir():
        raise TickerHubRefused(CORPUS_MISSING, f"no news corpus at {corpus}")
    try:
        next(iter(corpus.iterdir()), None)
    except OSError as exc:
        raise TickerHubRefused(CORPUS_UNREADABLE, f"{corpus}: {exc}") from exc
    if not Path(paths["issuers"]).is_file():
        raise TickerHubRefused(ISSUERS_MISSING, f"no issuer table at {paths['issuers']}")


def build(data_root: Path, *, out: Optional[Path] = None, now: Optional[datetime] = None,
          index_days: Optional[int] = None, paths: Optional[dict] = None,
          with_extras: bool = True) -> dict:
    """Index everything new since the last build into `out` (default `<data_root>/ticker_hub`).
    Reads the data root only; writes only under `out`. Returns the receipt."""
    t0 = time.time()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    P = paths or default_paths(data_root)
    check_inputs(P)
    hd = hub_dir(data_root, out)
    hd.mkdir(parents=True, exist_ok=True)
    with _Lock(hd / ".build.lock"):
        return _build_locked(P, hd, now, int(index_days or C.TICKER_HUB_INDEX_DAYS), t0, with_extras)


def _build_locked(P: dict, hd: Path, now: datetime, index_days: int, t0: float,
                  with_extras: bool) -> dict:
    stats: Counter = Counter()
    state = _read_json(hd / "state.json", None) or {"schema": STATE_SCHEMA}
    first_build = not state.get("built_utc")
    tbl = NE.tables(issuers=Path(P["issuers"]))
    try:
        cik_map = DA.load_cik_map(Path(P["cik_map"]))
        cik_status = "OK"
    except Exception as exc:                                           # noqa: BLE001
        cik_map, cik_status = {}, f"CIK_MAP_UNAVAILABLE: {str(exc)[:160]}"
    typed = _read_json(hd / "typed.json", None) or {}
    _update_typed(Path(P["digest"]), state, typed, stats)
    cutoff_day = (now - timedelta(days=index_days)).date().isoformat()
    corpus = Path(P["corpus"])

    # pass 0: which byte ranges are new
    files_state: dict = state.setdefault("files", {})
    work: list[tuple[str, Path, str, int, int]] = []
    for src, f in _corpus_files(corpus, cutoff_day):
        rel = f"{src}/{f.name}"
        try:
            size = f.stat().st_size
        except OSError:
            stats["files_unreadable"] += 1
            continue
        prev = files_state.get(rel) or {}
        start = int(prev.get("offset") or 0)
        if size < start:
            start = 0                                  # rewritten shorter: read again (rows fold by id)
            stats["files_shrunk_reread"] += 1
        if size > start:
            work.append((src, f, rel, start, size))
    stats["corpus_files_considered"] = len(work)

    # pass 1: the common-word counters, over the new titles
    low = Counter((state.get("common") or {}).get("low") or {})
    cap = Counter((state.get("common") or {}).get("cap") or {})
    for src, f, _rel, start, end in work:
        lines, _ = _read_new_lines(f, start, end)
        for line in lines:
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if isinstance(o, dict) and EN.kind_of(src) != "filing":
                _pub, _reg, title, _b = EN.publisher_region(src, str(o.get("title") or ""), "")
                _bump_common(low, cap, title, tbl)
    common = common_from_counters(low, cap)
    for k in C.EVENT_NODES_COMMON_WORD_NAMES:
        common.setdefault(str(k).lower(), {"lower": None, "capitalised": None, "listed": True})
    tagger = Tagger(tbl, cik_map, common)

    # pass 2: tag
    new_rows: list[dict] = []
    newest: dict = state.setdefault("newest_per_source", {})
    for src, f, rel, start, end in work:
        off = start
        for line, line_end in _read_new_lines_at(f, start, end):
            try:
                o = json.loads(line)
            except ValueError:
                stats["bad_json_lines"] += 1
                off = line_end
                continue
            if not isinstance(o, dict):
                stats["bad_json_lines"] += 1
                off = line_end
                continue
            known = DA._utc(o.get("first_seen_utc")) or DA.timed_utc(o.get("published_utc"))
            if known is not None and known > now:
                # written after this build's clock: the cursor stops here, the next build reads it
                stats["deferred_after_now"] += 1
                break
            off = line_end
            r = _corpus_row(src, o, tagger, typed, now, stats)
            fs = o.get("first_seen_utc") or o.get("read_utc")
            if isinstance(fs, str) and fs > (newest.get(src) or "") and fs <= _iso(now):
                newest[src] = fs
            if r is not None:
                new_rows.append(r)
        files_state[rel] = {"offset": off, "size": end}

    # reader page store
    dj = corpus / "dowjones"
    rd_state: dict = state.setdefault("reader_days", {})
    if dj.is_dir():
        for pub in sorted(p for p in dj.iterdir() if p.is_dir() and not p.name.startswith("_")):
            for day in sorted(p for p in pub.iterdir() if p.is_dir() and _DAY.match(p.name)):
                if day.name < cutoff_day:
                    continue
                key = f"{pub.name}/{day.name}"
                try:
                    mt = day.stat().st_mtime_ns
                except OSError:
                    continue
                prev = rd_state.get(key) or {}
                if prev.get("mtime_ns") == mt:
                    continue
                seen = set(prev.get("seen") or [])
                deferred = 0
                names = sorted(n for n in os.listdir(day) if n.endswith(".json"))
                for name in names:
                    if name in seen:
                        continue
                    try:
                        page = json.loads((day / name).read_text(encoding="utf-8", errors="replace"))
                    except (OSError, ValueError):
                        stats["reader_pages_unreadable"] += 1
                        continue
                    if not isinstance(page, dict):
                        seen.add(name)
                        continue
                    pfs = DA._utc(page.get("first_seen_utc"))
                    if pfs is not None and pfs > now:
                        # first seen after this build's clock: left unseen for the next build
                        deferred += 1
                        stats["deferred_after_now"] += 1
                        continue
                    seen.add(name)
                    stats["reader_pages_read"] += 1
                    new_rows.extend(_reader_rows(pub.name, page, tagger, now, stats))
                    fs = page.get("first_seen_utc")
                    s = f"reader:{pub.name}"
                    if isinstance(fs, str) and fs > (newest.get(s) or "") and fs <= _iso(now):
                        newest[s] = fs
                # a deferred page keeps the folder dirty, so the next build looks again
                rd_state[key] = {"mtime_ns": None if deferred else mt, "seen": sorted(seen)}

    # merge into month shards
    keys: dict = state.setdefault("keys", {})
    by_month: dict[str, list[dict]] = {}
    for r in new_rows:
        m = keys.get(r["id"]) or _month(r["first_seen_utc"])
        by_month.setdefault(m, []).append(r)
    shard_receipts = []
    for m in sorted(by_month):
        rows = _read_shard(shard_paths(hd, m)[0])
        before = len(rows)
        for r in by_month[m]:
            if r["id"] in rows:
                _fold(rows[r["id"]], r)
                stats["rows_folded"] += 1
            else:
                rows[r["id"]] = r
                keys[r["id"]] = m
        shard_receipts.append({**_write_shard(hd, m, rows), "new": len(rows) - before})
    _write_json(hd / "typed.json", typed)

    # totals over the whole index
    n_index = 0
    by_method: Counter = Counter()
    for pp in sorted(hd.glob("postings_*.json")):
        po = _read_json(pp, {}) or {}
        n_index += int(po.get("n_rows") or 0)
    for r in new_rows:
        for t in r["tags"]:
            by_method[t["m"]] += 1
    read_total = sum(v for k, v in stats.items() if k.startswith("rows_read:"))
    untagged_total = sum(v for k, v in stats.items() if k.startswith("rows_untagged:"))
    per_source = {}
    for k, v in stats.items():
        if k.startswith("rows_read:"):
            s = k.split(":", 1)[1]
            u = stats.get(f"rows_untagged:{s}", 0)
            per_source[s] = {"read": v, "untagged": u, "tagged": v - u,
                             "untagged_share": round(u / v, 4) if v else None}

    extras: dict = {}
    if with_extras:
        uni = load_universe(P, tbl)
        _write_json(hd / "universe.json", uni)
        extras["universe"] = {"symbols": len(uni), "with_sector": sum(1 for v in uni.values() if v.get("sector")),
                              "potential_universe_dir": str(P["potential_universe"])}
        extras["forecasts"] = build_forecasts(Path(P["predictions"]), hd, state, stats)
        try:
            extras["events"] = build_events(Path(P["event_store"]), hd, now, stats)
        except Exception as exc:                                       # noqa: BLE001
            extras["events"] = {"status": f"EVENTS_UNREADABLE: {type(exc).__name__}: {str(exc)[:160]}"}
        extras["related"] = build_related(Path(P["graph"]), hd, now)

    state["common"] = {"low": dict(low), "cap": dict(cap)}
    state["built_utc"] = _iso(now)
    state["n_builds"] = int(state.get("n_builds") or 0) + 1
    state["schema"] = STATE_SCHEMA
    _write_json(hd / "state.json", state)
    receipt = {
        "schema": SCHEMA, "built_utc": _iso(now), "first_build": first_build,
        "index_days": index_days, "cutoff_day": cutoff_day, "elapsed_s": round(time.time() - t0, 1),
        "data_root_corpus": str(corpus), "out": str(hd),
        "rows_read_new": read_total, "rows_untagged_new": untagged_total,
        "rows_tagged_new": read_total - untagged_total,
        "untagged_share_new": round(untagged_total / read_total, 4) if read_total else None,
        "tags_by_method_new": dict(by_method), "rows_in_index": n_index,
        "per_source_new": dict(sorted(per_source.items())),
        "newest_per_source": dict(sorted(newest.items())),
        "shards_written": shard_receipts, "cik_map": cik_status,
        "common_word_keys": len(common),
        "refused_name_matches_top": dict(tagger.refused.most_common(25)),
        "counts": {k: v for k, v in sorted(stats.items())
                   if not k.startswith(("rows_read:", "rows_untagged:"))},
        **extras,
    }
    _write_json(hd / "latest.json", receipt)
    rec_dir = hd / "receipts"
    rec_dir.mkdir(exist_ok=True)
    _write_json(rec_dir / f"build_{now.strftime('%Y%m%dT%H%M%SZ')}_{os.getpid()}.json", receipt)
    if n_index == 0:
        raise TickerHubRefused(NOTHING_INDEXED, f"0 tagged rows in the index at {hd} "
                                                f"({read_total} rows read this build)")
    return receipt


# ─────────────────────────────────────────────── reading the index (requests)

_CACHE: dict[str, tuple[Any, Any]] = {}
_CACHE_LOCK = threading.Lock()


def _cached_json(path: Path) -> Any:
    """Parsed JSON keyed on (path, mtime_ns, size); one copy per file."""
    try:
        st = path.stat()
    except OSError:
        return None
    stamp = (st.st_mtime_ns, st.st_size)
    k = str(path)
    with _CACHE_LOCK:
        hit = _CACHE.get(k)
        if hit and hit[0] == stamp:
            return hit[1]
    obj = _read_json(path, None)
    with _CACHE_LOCK:
        _CACHE[k] = (stamp, obj)
        if len(_CACHE) > 24:
            for kk in list(_CACHE)[:len(_CACHE) - 24]:
                _CACHE.pop(kk, None)
    return obj


def _months_between(lo: datetime, hi: datetime) -> list[str]:
    out, y, m = [], lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def _clamp_days(days: Optional[int]) -> int:
    d = int(days if days is not None else C.TICKER_HUB_DEFAULT_DAYS)
    return max(1, min(d, int(C.TICKER_HUB_MAX_DAYS)))


def index_status(hd: Path, now: datetime) -> dict:
    latest = _cached_json(hd / "latest.json")
    if not latest:
        return {"status": "NO_INDEX", "index_built_utc": None, "index_age_s": None,
                "stale_after_s": int(float(C.TICKER_HUB_STALE_HOURS) * 3600),
                "detail": f"no index at {hd}: run `python -m scripts.ticker_hub build`"}
    built = DA._utc(latest.get("built_utc"))
    age = None if built is None else int((now - built).total_seconds())
    lim = int(float(C.TICKER_HUB_STALE_HOURS) * 3600)
    status = "STALE" if (age is None or age > lim) else "OK"
    return {"status": status, "index_built_utc": latest.get("built_utc"), "index_age_s": age,
            "stale_after_s": lim, "rows_in_index": latest.get("rows_in_index"),
            "untagged_share_last_build": latest.get("untagged_share_new"),
            "newest_per_source": latest.get("newest_per_source") or {},
            "detail": (f"STALE: the index was built {age} s ago (limit {lim} s); "
                       f"run `python -m scripts.ticker_hub build`") if status == "STALE" else None}


def _postings(hd: Path, months: list[str]) -> list[tuple[str, dict]]:
    out = []
    for m in months:
        po = _cached_json(shard_paths(hd, m)[1])
        if po:
            out.append((m, po))
    return out


def _read_at(path: Path, offsets: list[int]) -> list[dict]:
    rows = []
    if not offsets:
        return rows
    with open(path, "rb") as fh:
        for off in sorted(offsets):
            fh.seek(off)
            line = fh.readline()
            try:
                rows.append(json.loads(line.decode("utf-8")))
            except ValueError:
                continue
    return rows


def _siblings(sym: str) -> list[str]:
    return [sym] + [DA.norm_ticker(s) for s in dict(C.TICKER_HUB_SIBLINGS).get(sym, ())]


def _decorate(r: dict, typed: dict, want: Optional[set] = None) -> dict:
    ty = typed.get(r.get("url_key") or "") if typed else None
    out = {k: r.get(k) for k in ("id", "source", "publisher", "kind", "first_seen_utc", "published_utc",
                                  "title", "url", "feeds", "regions", "tags")}
    out["event"] = ({k: ty.get(k) for k in ("event_type", "topic", "sentiment", "model")} if ty else None)
    if want:
        out["tagged_by"] = sorted({t["m"] for t in r.get("tags") or [] if t["t"] in want},
                                  key=lambda m: METHODS.index(m) if m in METHODS else 99)
    return out


def universe(hd: Path) -> dict:
    return _cached_json(hd / "universe.json") or {}


def known_symbol(hd: Path, sym: str) -> bool:
    return DA.norm_ticker(sym) in universe(hd)


def news_for(hd: Path, syms: list[str], days: int, now: datetime, limit: int) -> tuple[list[dict], dict]:
    lo = now - timedelta(days=days)
    lo_ep = int(lo.timestamp())
    want = set(syms)
    picked: list[tuple[int, str, int]] = []
    for m, po in _postings(hd, _months_between(lo, now)):
        seen_off = set()
        for s in syms:
            for ep, off in po.get("ticker", {}).get(s, []):
                if ep >= lo_ep and off not in seen_off:
                    seen_off.add(off)
                    picked.append((ep, m, off))
    picked.sort(reverse=True)
    total = len(picked)
    by_m: dict[str, list[int]] = {}
    for _ep, m, off in picked[:limit]:
        by_m.setdefault(m, []).append(off)
    typed = _cached_json(hd / "typed.json") or {}
    rows = []
    for m, offs in by_m.items():
        rows += [_decorate(r, typed, want) for r in _read_at(shard_paths(hd, m)[0], offs)]
    rows.sort(key=lambda r: (r.get("first_seen_utc") or "", r.get("id") or ""), reverse=True)
    by_source = Counter(r["source"] for r in rows)
    by_method = Counter(m for r in rows for m in r.get("tagged_by") or [])
    return rows, {"n_rows": total, "n_returned": len(rows), "truncated": total > len(rows),
                  "sources": dict(by_source.most_common()), "tagged_by": dict(by_method),
                  "newest_utc": rows[0]["first_seen_utc"] if rows else None}


def forecasts_for(hd: Path, syms: list[str]) -> dict:
    idx = _cached_json(hd / "forecasts_index.json")
    if idx is None:
        return {"status": "NO_FORECAST_INDEX", "open": [], "resolved": [], "void": [],
                "counts": {"open": 0, "resolved": 0, "void": 0}}
    rows: list[dict] = []
    fp = hd / "forecasts.jsonl"
    for s in syms:
        off = idx.get(s)
        if off is None:
            continue
        with open(fp, "rb") as fh:
            fh.seek(int(off))
            try:
                rows += json.loads(fh.readline().decode("utf-8")).get("rows") or []
            except ValueError:
                continue
    void = [r for r in rows if r.get("void_reason")]
    resolved = [r for r in rows if r.get("outcome") is not None and not r.get("void_reason")]
    opn = [r for r in rows if r.get("outcome") is None and not r.get("void_reason")]
    briers = [float(r["brier"]) for r in resolved if isinstance(r.get("brier"), (int, float))]
    hits = [int(r["outcome"]) for r in resolved if r.get("outcome") in (0, 1)]
    return {"status": "OK", "open": opn, "resolved": resolved, "void": void,
            "counts": {"open": len(opn), "resolved": len(resolved), "void": len(void),
                       "resolved_outcome_1": sum(hits), "resolved_outcome_0": len(hits) - sum(hits),
                       "mean_brier": round(sum(briers) / len(briers), 4) if briers else None,
                       "n_brier": len(briers)}}


def calendar_for(data_root: Path, sym: str, now: datetime) -> dict:
    """Live, point in time: the newest forward-calendar snapshot pulled at or before now."""
    from backend.services import forward_calendar as FC
    try:
        res = FC.next_dates([sym], now, root=Path(data_root))
        mac = FC.next_macro(now, root=Path(data_root))
    except Exception as exc:                                           # noqa: BLE001
        return {"status": "CALENDAR_UNREADABLE", "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                "rows": []}
    v = (res.get("tickers") or {}).get(sym) or {}
    rows = []
    if v.get("date"):
        rows.append({"date": v.get("date"), "kind": "earnings", "label": v.get("label"),
                     "confirmation": v.get("confirmation"), "timing": v.get("timing"),
                     "days_away": v.get("days_away"), "sessions_away": v.get("sessions_away"),
                     "source": f"{v.get('pull_id')}:{v.get('source')}"})
    for m in mac.get("dates") or []:
        rows.append({"date": m.get("date"), "kind": m.get("kind"), "label": "MACRO",
                     "confirmation": "scheduled", "timing": None, "days_away": None,
                     "sessions_away": None, "source": f"{mac.get('pull_id')}:{m.get('source')}"})
    rows.sort(key=lambda r: str(r.get("date") or ""))
    return {"status": "OK", "label": v.get("label"), "last_reported": v.get("last_reported"),
            "age_days": v.get("age_days"), "rows": rows,
            "snapshot": v.get("pull_id"), "macro_snapshot": mac.get("pull_id")}


def related_for(hd: Path, sym: str) -> list[dict]:
    uni = universe(hd)
    me = uni.get(sym) or {}
    out: list[dict] = []
    rel = (_cached_json(hd / "related.json") or {}).get("tickers") or {}
    for g in rel.get(sym) or []:
        t = DA.norm_ticker(g.get("ticker"))
        out.append({"ticker": t, "name": (uni.get(t) or {}).get("name"), "link": g.get("link"),
                    "weight": g.get("weight"), "n": g.get("n"), "sign": g.get("sign"),
                    "source": "universe_graph", "graph_build_id": g.get("graph_build_id")})
    sec = me.get("sector")
    if sec:
        have = {r["ticker"] for r in out}
        peers = sorted(s for s, v in uni.items() if v.get("sector") == sec and s != sym and s not in have)
        for s in peers[:int(C.TICKER_HUB_SECTOR_PEERS)]:
            out.append({"ticker": s, "name": uni[s].get("name"), "link": "same_sector", "weight": None,
                        "n": None, "sign": None, "source": "potential_universe.identity.sector",
                        "graph_build_id": None})
    return out


def hub(symbol: str, *, data_root: Optional[Path] = None, out: Optional[Path] = None,
        days: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    """Everything the index holds on one ticker. Raises KeyError for an unknown symbol."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dr = Path(data_root) if data_root else default_data_root()
    hd = hub_dir(dr, out)
    sym = DA.norm_ticker(symbol)
    st = index_status(hd, now)
    uni = universe(hd)
    if st["status"] != "NO_INDEX" and sym not in uni:
        raise KeyError(sym)
    d = _clamp_days(days)
    syms = _siblings(sym)
    news, ncov = news_for(hd, syms, d, now, int(C.TICKER_HUB_NEWS_LIMIT))
    ev = ((_cached_json(hd / "events.json") or {}).get("tickers") or {})
    return {"schema": SCHEMA, "ticker": sym, "siblings": syms[1:], "days": d, "now_utc": _iso(now),
            "identity": uni.get(sym) or None,
            "news": news,
            "forecasts": forecasts_for(hd, syms),
            "calendar": calendar_for(dr, sym, now),
            "events": [e for s in syms for e in ev.get(s, [])][:50],
            "related": related_for(hd, sym),
            "coverage": {**st, **ncov}}


def feed(*, data_root: Optional[Path] = None, out: Optional[Path] = None, ticker: Optional[str] = None,
         sector: Optional[str] = None, source: Optional[str] = None, days: Optional[int] = None,
         limit: Optional[int] = None, now: Optional[datetime] = None) -> dict:
    """The news feed filtered by ticker / sector / source, newest first, with facets
    (row counts by ticker, sector and source inside the same window and filters)."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dr = Path(data_root) if data_root else default_data_root()
    hd = hub_dir(dr, out)
    st = index_status(hd, now)
    d = _clamp_days(days)
    lim = max(1, min(int(limit or C.TICKER_HUB_FEED_LIMIT), int(C.TICKER_HUB_FEED_LIMIT)))
    uni = universe(hd)
    lo_ep = int((now - timedelta(days=d)).timestamp())
    want_t = set(_siblings(DA.norm_ticker(ticker))) if ticker else None
    if want_t is not None and st["status"] != "NO_INDEX" and DA.norm_ticker(ticker) not in uni:
        raise KeyError(DA.norm_ticker(ticker))
    sec_syms = {s for s, v in uni.items() if v.get("sector") == sector} if sector else None
    picked: list[tuple[int, str, int]] = []
    f_ticker: Counter = Counter()
    f_source: Counter = Counter()
    f_sector: Counter = Counter()
    for m, po in _postings(hd, _months_between(now - timedelta(days=d), now)):
        tick = po.get("ticker") or {}
        # the candidate offsets for the filters
        def offs_for(syms: Iterable[str]) -> set:
            o = set()
            for s in syms:
                o.update(off for ep, off in tick.get(s, []) if ep >= lo_ep)
            return o
        cand: Optional[set] = None
        if want_t is not None:
            cand = offs_for(want_t)
        if sec_syms is not None:
            so = offs_for(sec_syms)
            cand = so if cand is None else cand & so
        if source:
            src_o = {off for ep, off in (po.get("source") or {}).get(source, []) if ep >= lo_ep}
            cand = src_o if cand is None else cand & src_o
        ep_of = {off: ep for ep, off in po.get("all") or [] if ep >= lo_ep}
        if cand is None:
            cand = set(ep_of)
        cand &= set(ep_of)
        for off in cand:
            picked.append((ep_of[off], m, off))
        # facets over the candidate set
        src_of = {}
        for s, lst in (po.get("source") or {}).items():
            for ep, off in lst:
                if off in cand:
                    src_of[off] = s
        f_source.update(src_of.values())
        sec_of: dict[int, set] = {}
        for s, lst in tick.items():
            hit = [off for ep, off in lst if off in cand]
            if hit:
                f_ticker[s] += len(hit)
                sv = (uni.get(s) or {}).get("sector")
                if sv:
                    for off in hit:
                        sec_of.setdefault(off, set()).add(sv)
        for secs in sec_of.values():
            f_sector.update(secs)
    picked.sort(reverse=True)
    by_m: dict[str, list[int]] = {}
    for _ep, m, off in picked[:lim]:
        by_m.setdefault(m, []).append(off)
    typed = _cached_json(hd / "typed.json") or {}
    rows = []
    for m, offs in by_m.items():
        rows += [_decorate(r, typed, want_t) for r in _read_at(shard_paths(hd, m)[0], offs)]
    rows.sort(key=lambda r: (r.get("first_seen_utc") or "", r.get("id") or ""), reverse=True)
    top = int(C.TICKER_HUB_FACET_TOP)
    return {"schema": SCHEMA, "now_utc": _iso(now), "days": d,
            "filters": {"ticker": DA.norm_ticker(ticker) if ticker else None, "sector": sector,
                        "source": source},
            "rows": rows, "n_rows": len(picked), "n_returned": len(rows), "truncated": len(picked) > len(rows),
            "facets": {"ticker": [{"key": k, "n": n, "name": (uni.get(k) or {}).get("name")}
                                  for k, n in f_ticker.most_common(top)],
                       "sector": [{"key": k, "n": n} for k, n in f_sector.most_common(top)],
                       "source": [{"key": k, "n": n} for k, n in f_source.most_common()]},
            "sectors": sorted({v["sector"] for v in uni.values() if v.get("sector")}),
            "coverage": st}


def iter_index_rows(hd: Path) -> Iterator[dict]:
    """Every stored row (tests and the CLI's `show`)."""
    for rp in sorted(hd.glob("rows_*.jsonl")):
        with open(rp, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)
