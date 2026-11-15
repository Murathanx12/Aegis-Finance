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
* RELATED NAMES -- universe-graph links, and same-sector peers ranked by how often our own
  corpus names them together with the ticker (90 days), then by median dollar volume;
* the CALENDAR is read live per request (`forward_calendar.next_dates`, point in time).

HOW A ROW GETS A TICKER (each tag records its method AND its tier; the page prints both)
========================================================================================
Methods, first one wins per ticker:

1. ``source_field`` -- a symbol the source row already carries (provider tag, an explicit
   token the collector recorded). A collector NAME match (`resolved:X=name`) is NOT
   trusted: it is re-resolved by rule 4.
2. ``sec_cik`` -- an SEC row's `cik:` tag through `official/company_tickers.json`.
   ``reader_lane`` / ``reader_search`` -- the reader was browsing that ticker; kept only
   when the row's text names it.
3. ``text_token`` / ``name_match`` -- `event_nodes.strict_tickers` on the title and body.
   Body rules (review of PR #145, F1): per-source boilerplate is cut first
   (`TICKER_HUB_SOURCE_BOILERPLATE`); a publisher's own ticker never comes from its body
   (`TICKER_HUB_PUBLISHER_TICKERS`); in a SHORT body (<= TICKER_HUB_SHORT_BODY_CHARS) a
   name never tags (only an explicit symbol pattern does); in a long body a name needs
   TICKER_HUB_BODY_MIN_MENTIONS mentions.
4. ``digest_typed`` -- the world digest's tickers, kept only when the row's own text names
   the ticker under the rules above, and ranked LAST (F2). In practice it then never
   decides a tag; the digest labels the row's event type instead.

Tiers: ``about`` = the TITLE names the company (name or explicit symbol), or an SEC filing
by CIK. Everything else is ``mentions``. The re-measured strict precision of every
method other than title matches and CIK was under ~50 %, so they only ever reach
`mentions`; the News tab shows `about` by default.

ONE GENERATION AT A TIME
========================
A build writes a complete new generation directory (rows, postings, state, extras), then
renames it into place and replaces `CURRENT.json` (generation name + manifest of every
file's size, sha256 and row count) atomically. A reader resolves `CURRENT.json` and checks
the manifest's sizes and row counts on every request; a mismatch, an unreadable postings
file, rows that do not carry the ticker their posting says, an unreadable universe or a
missing forecast file each turn the payload's status DEGRADED with a named problem --
never OK, never a 404 for every symbol, never a 500. `verify` re-hashes everything.

DESCRIPTIVE ONLY. Nothing here ranks companies, scores or recommends; a forecast row is
printed as written and graded, never as advice.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
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

SCHEMA = "ticker-hub/2"
INDEX_SCHEMA = str(C.TICKER_HUB_INDEX_SCHEMA)
STATE_SCHEMA = "ticker-hub-state/2"
CURRENT_NAME = "CURRENT.json"

# refusal codes (each a red, non-zero exit in the CLI)
CORPUS_MISSING = "CORPUS_MISSING"
CORPUS_UNREADABLE = "CORPUS_UNREADABLE"
ISSUERS_MISSING = "ISSUERS_MISSING"
NOTHING_INDEXED = "NOTHING_INDEXED"
BUILD_LOCKED = "BUILD_LOCKED"
INDEX_DAMAGED = "INDEX_DAMAGED"

#: tag methods, strongest first (a ticker keeps the first method that named it)
METHODS = ("source_field", "sec_cik", "reader_lane", "reader_search", "text_token",
           "name_match", "digest_typed")
TIERS = ("about", "mentions")
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
_GN_STORY_LINK = re.compile(r"<a\b[^>]*href=\"https?://news\.google\.com/stories/[^\"]*\"[^>]*>.*?</a>",
                            re.IGNORECASE | re.DOTALL)
_CHIP_RX = [re.compile(p) for p in C.TICKER_HUB_QUOTE_CHIP_PATTERNS]
#: files of a v1 cache (no CURRENT.json) that a v2 build removes from the index root
_V1_FILES = ("state.json", "typed.json", "universe.json", "forecasts.jsonl", "forecasts_index.json",
             "events.json", "related.json", "latest.json")


class TickerHubRefused(RuntimeError):
    """A build that cannot run (missing/unreadable input, nothing indexed, locked, damaged)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


# ─────────────────────────────────────────────── small helpers

def _iso(d: Optional[datetime]) -> Optional[str]:
    return None if d is None else d.astimezone(timezone.utc).isoformat(timespec="seconds")


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()[:16]


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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


def norm_title(t: str) -> str:
    """Unicode-aware: casefolded, every run of non-word characters one space. A CJK
    headline keeps its characters (v1 kept only [a-z0-9] and folded different Chinese
    headlines into one row, review F5)."""
    return re.sub(r"[\W_]+", " ", (t or "").casefold()).strip()


def row_id(source: str, title: str, url: str, published_utc: Optional[str] = None) -> str:
    """One row per (source, full normalised title, published time); a title-less row is
    keyed on its URL. Copies of one story across sources are joined at READ time."""
    nt = norm_title(title)
    if nt:
        return _sha16(f"t|{source}|{nt}|{published_utc or ''}")
    return _sha16(f"u|{source}|{url_key(url)}")


def is_quote_chip(text: str) -> bool:
    t = " ".join((text or "").split())
    return any(rx.match(t) for rx in _CHIP_RX)


def _prefixed(table: dict, src: str) -> tuple:
    """Values of the first key that `src` equals or starts with."""
    for k, v in table.items():
        if src == k or src.startswith(k):
            return tuple(v)
    return ()


_READER_FETCHERS = frozenset({"web_reader", "reader_pool"})


def _article_body(text: str, title: str) -> str:
    """A reader page snapshot from its headline on (nav and carousels before it are chrome)."""
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


def effective_utc(first_seen: Optional[datetime], published: Optional[datetime]) -> Optional[datetime]:
    """When the row happened: its published time when the source gives one (and it is not
    after first_seen by more than a zone error), else when we first saw it."""
    if published is not None and (first_seen is None or published <= first_seen + timedelta(
            seconds=int(C.TICKER_HUB_PUBLISHED_FUTURE_SLACK_S))):
        return min(published, first_seen) if first_seen is not None else published
    return first_seen


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
    """The index ROOT (holds CURRENT.json, the generations and receipts/)."""
    return Path(out) if out else Path(data_root) / str(C.TICKER_HUB_DIRNAME)


def _write_json(path: Path, obj: Any) -> None:
    DG.atomic_write_json(path, obj, indent=None, ensure_ascii=True, default=str)


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _as_list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


# ─────────────────────────────────────────────── tagging

class Tagger:
    """The tag rules of the module docstring, bound to one issuer table and one
    common-word set. `refused` counts every refused match by reason."""

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
        self._source_chrome: dict[str, Optional[re.Pattern]] = {}
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

    # -- text --------------------------------------------------------------------------

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

    def _text_tags(self, text: str, where: str) -> list[dict]:
        out: list[dict] = []
        hits = EN.strict_tickers(text, self.tbl, self.common, self.refused)
        for sym, rule in hits.items():
            if rule.split(":", 1)[-1] in self.drop_keys:
                self.refused[f"hub_drop_key:{rule}"] += 1
                continue
            if not self.token_ok(DA.norm_ticker(sym), rule, text):
                continue
            m = "text_token" if rule in _TOKEN_RULES else "name_match"
            out.append({"t": DA.norm_ticker(sym), "m": m, "rule": rule, "where": where})
        if self._cased_rx is not None:
            seen = {o["t"] for o in out}
            # another company in a TITLE is context ("Apple, Palantir, AMD ... Stocks"); in a body it is not
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

    def _name_words(self, sym: str) -> set:
        """First words (>= 3 chars) of every issuer-table name and cased alias of `sym`."""
        if not hasattr(self, "_names_by_sym"):
            by: dict[str, set] = {}
            weak = {"the", "and", "new", "first"} | set(NE._GENERIC_ALIASES) | set(self.common)
            for key, s in self.tbl.name_to_symbol.items():
                w = key.split()[0] if key.split() else ""
                if len(w) >= 3 and w not in weak:
                    by.setdefault(DA.norm_ticker(s), set()).add(w)
            for alias, s in self.cased.items():
                by.setdefault(s, set()).add(alias.lower())
            self._names_by_sym = by
        return self._names_by_sym.get(sym, set())

    def token_ok(self, sym: str, rule: str, text: str) -> bool:
        """An explicit token is trusted only when it is unambiguous: never a one-letter
        symbol from `$X` / `(X)`, and a bare `(XYZ)` only when the same text also names
        the issuer (the re-measured sample: "Affordable Care Act (ACA)" -> ACA, Treasury
        "(OCC)", "MESA(R)" -> R). `NASDAQ: X` and local codes stay trusted."""
        if rule not in ("paren_ticker", "cashtag"):
            return True
        if len(sym) <= 1:
            self.refused[f"one_letter_{rule}:{sym}"] += 1
            return False
        if rule == "paren_ticker":
            low = (text or "").lower()
            if not any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low) for w in self._name_words(sym)):
                self.refused["paren_ticker_without_name"] += 1
                return False
        return True

    @staticmethod
    def _company_context(text: str, start: int, end: int) -> bool:
        """A possessive ("Apple's"), an attached corporate cue ("Apple shares"),
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

    def strip_boilerplate(self, body: str, src: str) -> str:
        """The general page chrome plus the source's own declared boilerplate."""
        if not body:
            return body
        if self._chrome_rx is not None:
            body = self._chrome_rx.sub(" ", body)
        if src not in self._source_chrome:
            phrases = [re.escape(p) for p in _prefixed(dict(C.TICKER_HUB_SOURCE_BOILERPLATE), src)]
            self._source_chrome[src] = re.compile("|".join(phrases), re.IGNORECASE) if phrases else None
        rx = self._source_chrome[src]
        if rx is not None:
            body, n = rx.subn(" ", body)
            if n:
                self.refused[f"boilerplate_cut:{src.split('_')[0] if src.startswith('google') else src}"] += n
        return body

    def body_tags(self, body: str, src: str = "") -> list[dict]:
        """Body tags under the body rules (module docstring, rule 3)."""
        body = self.strip_boilerplate(body or "", src)
        tags = self.text_tags(body, "body")
        own = set(_prefixed(dict(C.TICKER_HUB_PUBLISHER_TICKERS), src))
        short = len(body) <= int(C.TICKER_HUB_SHORT_BODY_CHARS)
        need = int(C.TICKER_HUB_BODY_MIN_MENTIONS)
        low = body.lower()
        out = []
        for t in tags:
            if t["t"] in own:
                self.refused[f"publisher_own_ticker_in_body:{t['t']}"] += 1
                continue
            if t["m"] != "name_match":
                out.append(t)                     # an explicit symbol pattern ($NVDA, NASDAQ: NVDA)
                continue
            if short:
                self.refused["short_body_name_only"] += 1
                continue
            rule = str(t.get("rule") or "")
            kind, _, key = rule.partition(":")
            if kind == "cased_alias":
                n = len(re.findall(r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![A-Za-z0-9])", body))
            elif kind == "foreign_alias":
                n = body.count(key)
            else:
                n = len(re.findall(r"(?<![a-z0-9])" + re.escape(key.lower()) + r"(?![a-z0-9])", low))
            if n >= need:
                out.append(t)
            else:
                self.refused["body_single_mention"] += 1
        return out

    def confirmed(self, sym: str, title: str, body: str) -> bool:
        """Lenient: the title or the body text names `sym` (one mention is enough)."""
        s = DA.norm_ticker(sym)
        return any(t["t"] == s for t in self.text_tags(title or "", "title") + self.text_tags(body or "", "body"))

    def confirmed_strict(self, sym: str, title: str, body: str, src: str) -> bool:
        """The title names `sym`, or the body does under the body rules."""
        s = DA.norm_ticker(sym)
        return any(t["t"] == s for t in self.text_tags(title or "", "title") + self.body_tags(body or "", src))

    # -- fields ------------------------------------------------------------------------

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


def with_tiers(tags: list[dict], title_syms: set) -> list[dict]:
    """`about` when the title names the ticker or the row is the company's own SEC filing."""
    for t in tags:
        t["tier"] = "about" if (t["t"] in title_syms or t["m"] == "sec_cik") else "mentions"
    return tags


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


def _row(src: str, publisher: str, kind: str, title: str, url: str, fs: datetime,
         pub: Optional[datetime], regions: list, tags: list[dict]) -> dict:
    pub_iso = _iso(pub)
    eff = effective_utc(fs, pub)
    return {"id": row_id(src, title, url, pub_iso), "source": src, "publisher": publisher, "kind": kind,
            "first_seen_utc": _iso(fs), "published_utc": pub_iso, "eff_utc": _iso(eff),
            "title": title[:300], "url": url[:600], "url_key": url_key(url), "feeds": [src],
            "regions": regions, "tags": tags}


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
    if is_quote_chip(title):
        stats["quote_chips_skipped"] += 1
        return None
    reader_row = src.startswith("dj_reader_") or str(o.get("fetcher") or "") in _READER_FETCHERS
    raw = str(o.get("body") or o.get("text") or "")
    if src.startswith("google_news_rss_"):
        raw = _GN_STORY_LINK.sub(" ", raw)       # the "full coverage" link, any language
    raw_body = EN.clean_text(raw)
    body = (_article_body(raw_body, title) if reader_row else raw_body)[:int(C.TICKER_HUB_BODY_CHARS)]
    uk = url_key(url)
    ty = typed.get(uk) if uk else None
    generic = [o.get("ticker")] if o.get("ticker") else []
    g_field = [t for t in tagger.source_field_tags(_as_list(o.get("tickers")) + generic, entity)
               if t["rule"] not in ("paren_ticker", "cashtag") or tagger.token_ok(t["t"], t["rule"], f"{title}\n{body}")]
    if reader_row:
        # the reader's `tickers` is the LANE it was browsing, not a provider tag
        lane = [t for t in g_field if t["rule"] == "provider"]
        g_field = [t for t in g_field if t["rule"] != "provider"]
        for t in lane:
            if tagger.confirmed(t["t"], title, body):
                g_field.append({**t, "m": "reader_lane", "rule": "reader_tickers"})
            else:
                stats["reader_lane_unconfirmed"] += 1
    g_cik = tagger.cik_tags(entity) if src.startswith("sec_") else []
    kind = EN.kind_of(src)
    g_digest = []
    for t in (ty or {}).get("tickers") or []:
        if not tagger.known(t):
            continue
        # a filing's title is the FILER's name, not a headline: "Blackstone Real Estate Income
        # Trust" is not BX, "Reliance Global Group" is not RS (re-measured sample)
        if tagger.confirmed_strict(t, "" if kind == "filing" else title, body, src):
            g_digest.append({"t": DA.norm_ticker(t), "m": "digest_typed", "rule": "world_digest",
                             "where": "field"})
        else:
            stats["digest_unconfirmed"] += 1
    g_title = [] if kind == "filing" else tagger.text_tags(title, "title")
    g_body = tagger.body_tags(body, src)
    tags = with_tiers(merge_tags(g_field, g_cik, g_title, g_body, g_digest), {t["t"] for t in g_title})
    stats[f"rows_read:{src}"] += 1
    if not tags:
        stats[f"rows_untagged:{src}"] += 1
        return None
    return _row(src, publisher, kind, title, url, known, pub, [region] if region else [], tags)


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
        if is_quote_chip(title):
            stats["quote_chips_skipped"] += 1
            return []
        url = str(page.get("url") or "")
        text = _article_body(EN.clean_text(str(page.get("text") or "")), title)[:int(C.TICKER_HUB_BODY_CHARS)]
        g_lane = ([{"t": lane_t, "m": "reader_lane", "rule": str(rb.get("lane") or "lane"), "where": "field"}]
                  if lane_t and tagger.known(lane_t) else [])
        if g_lane and not tagger.confirmed(lane_t, title, text):
            stats["reader_lane_unconfirmed"] += 1
            g_lane = []
        g_named = []
        for t in tagger.source_field_tags(_as_list(page.get("tickers_named")), []):
            if t["t"] in tagger.bare:
                continue
            if tagger.confirmed(t["t"], title, text):
                g_named.append({**t, "rule": "tickers_named"})
            else:
                stats["tickers_named_unconfirmed"] += 1
        g_title = tagger.text_tags(title, "title")
        tags = with_tiers(merge_tags(g_named, g_lane, g_title, tagger.body_tags(text, src)),
                          {t["t"] for t in g_title})
        stats[f"rows_read:{src}"] += 1
        if not tags:
            stats[f"rows_untagged:{src}"] += 1
            return []
        out.append(_row(src, publisher, "article", title, url, known, pub, [], tags))
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
        if is_quote_chip(text):
            stats["quote_chips_skipped"] += 1
            continue
        stats[f"rows_read:{src}"] += 1
        g_search = ([{"t": lane_t, "m": "reader_search", "rule": str(rb.get("lane") or "search"),
                      "where": "field"}] if kind == "search" and lane_t and tagger.known(lane_t)
                    and tagger.confirmed(lane_t, text, "") else [])
        g_title = tagger.text_tags(text, "title")
        tags = with_tiers(merge_tags(g_search, g_title), {t["t"] for t in g_title})
        if not tags:
            stats[f"rows_untagged:{src}"] += 1
            continue
        out.append(_row(src, publisher, "headline_link", text, url, known, None, [], tags))
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


def shard_paths(gd: Path, month: str) -> tuple[Path, Path]:
    return gd / f"rows_{month}.jsonl", gd / f"postings_{month}.json"


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
    """The same row (same source, title, published time) seen again."""
    if new["first_seen_utc"] < old["first_seen_utc"] and _month(new["first_seen_utc"]) == _month(old["first_seen_utc"]):
        old["first_seen_utc"] = new["first_seen_utc"]
        old["eff_utc"] = new["eff_utc"]
        old["url"] = new["url"] or old["url"]
        old["url_key"] = new["url_key"] or old["url_key"]
    old["regions"] = sorted(set(old.get("regions") or []) | set(new.get("regions") or []))
    merged = merge_tags(old.get("tags") or [], new.get("tags") or [])
    about = {t["t"] for t in (old.get("tags") or []) + (new.get("tags") or []) if t.get("tier") == "about"}
    for t in merged:
        t["tier"] = "about" if t["t"] in about else t.get("tier", "mentions")
    old["tags"] = merged
    return old


def _write_shard(gd: Path, month: str, rows: dict[str, dict]) -> dict:
    """rows newest first; postings carry [eff epoch, byte offset] per ticker (all tiers),
    per ticker in the `about` tier, per source, and for all rows (with an about flag)."""
    rp, pp = shard_paths(gd, month)
    ordered = sorted(rows.values(), key=lambda r: (r.get("eff_utc") or r["first_seen_utc"], r["id"]), reverse=True)
    parts: list[str] = []
    off = 0
    post: dict[str, Any] = {"schema": SCHEMA, "month": month, "n_rows": len(ordered),
                            "ticker": {}, "about": {}, "source": {}, "all": []}
    for r in ordered:
        line = json.dumps(r, ensure_ascii=True, separators=(",", ":")) + "\n"
        ep = _epoch(r.get("eff_utc") or r["first_seen_utc"])
        tags = r.get("tags") or []
        any_about = any(t.get("tier") == "about" for t in tags)
        post["all"].append([ep, off, 1 if any_about else 0])
        post["source"].setdefault(r["source"], []).append([ep, off])
        for t in {t["t"] for t in tags}:
            post["ticker"].setdefault(t, []).append([ep, off])
        for t in {t["t"] for t in tags if t.get("tier") == "about"}:
            post["about"].setdefault(t, []).append([ep, off])
        parts.append(line)
        off += len(line.encode("utf-8"))
    DG.atomic_write_text(rp, "".join(parts) or "\n")
    _write_json(pp, post)
    return {"month": month, "rows": len(ordered), "bytes": off}


# ─────────────────────────────────────────────── universe / forecasts / events / related

def load_universe(paths: dict, tbl: Any) -> dict[str, dict]:
    """{sym: {name, sector, gics_sector, dollar_volume}} for every issuer-table symbol.
    `sector` is the potential_universe identity label (the universe graph's sectors);
    `dollar_volume` its execution.median_dollar_volume (the size measure on file; no
    market cap is in the data)."""
    import csv
    out: dict[str, dict] = {}
    ip = Path(paths["issuers"])
    with ip.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            s = DA.norm_ticker(row.get("symbol"))
            if s:
                out[s] = {"name": (row.get("primary_name") or "").strip() or None,
                          "sector": None, "gics_sector": None, "dollar_volume": None}
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
                    rec = out.setdefault(s, {"name": None, "sector": None, "gics_sector": None,
                                             "dollar_volume": None})
                    rec["sector"] = ident.get("sector") or rec.get("sector")
                    ex = r.get("execution") if isinstance(r.get("execution"), dict) else {}
                    dv = ex.get("median_dollar_volume")
                    if isinstance(dv, (int, float)):
                        rec["dollar_volume"] = float(dv)
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


def build_forecasts(pred: Path, gd: Path, prev_gd: Optional[Path], state: dict, stats: Counter) -> dict:
    """Per-ticker compact forecast rows, rebuilt whole when the ledger changed (it is
    rewritten in place, so no byte cursor is valid). Streamed, read-only."""
    from backend.services import forecast_ledger as FL
    if not FL.exists(pred):
        # written empty, so the index is complete; the receipt and the panel say why it is empty
        stats["forecast_ledger_missing"] += 1
        DG.atomic_write_text(gd / "forecasts.jsonl", "\n")
        _write_json(gd / "forecasts_index.json", {})
        return {"status": "LEDGER_MISSING", "path": str(pred)}
    try:
        # the layer's own cache key: it changes with ANY backing file, legacy or streams
        fp = json.loads(json.dumps(list(FL.fingerprint(pred)), default=str))
    except (OSError, ValueError, TypeError):
        fp = None
    prev = state.get("forecasts") or {}
    if (fp is not None and prev.get("fingerprint") == fp and prev_gd is not None
            and (prev_gd / "forecasts.jsonl").is_file() and (prev_gd / "forecasts_index.json").is_file()):
        for name in ("forecasts.jsonl", "forecasts_index.json"):
            _carry(prev_gd / name, gd / name)
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
    DG.atomic_write_text(gd / "forecasts.jsonl", "".join(parts) or "\n")
    _write_json(gd / "forecasts_index.json", index)
    out = {"status": "REBUILT", "fingerprint": fp, "rows": n, "bad_lines": bad, "tickers": len(by),
           "path": str(pred)}
    state["forecasts"] = out
    return out


def build_events(store: Path, gd: Path, now: datetime) -> dict:
    """{ticker: [node brief + first evidence title]} as the event store stood at `now`."""
    if not Path(store).is_file():
        _write_json(gd / "events.json", {"tickers": {}, "status": "STORE_MISSING"})
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
    _write_json(gd / "events.json", {"tickers": by, "status": "OK", **meta})
    return {"status": "OK", "nodes": len(known["nodes"]), "tickers": len(by), **meta}


def build_related(graph_dir: Path, gd: Path, now: datetime) -> dict:
    """Universe-graph neighbours per company, as the newest graph built at or before now."""
    if not Path(graph_dir).is_dir():
        _write_json(gd / "related.json", {"tickers": {}, "graph": {"status": "GRAPH_MISSING"}})
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
    _write_json(gd / "related.json", {"tickers": by, "graph": gm})
    return {**gm, "companies_with_links": len(by)}


# ─────────────────────────────────────────────── generations

def read_current(root: Path) -> tuple[Optional[dict], Optional[str]]:
    """(CURRENT.json, problem). No file -> (None, None); unreadable -> (None, problem)."""
    p = Path(root) / CURRENT_NAME
    if not p.is_file():
        return None, None
    cur = _read_json(p, None)
    if not isinstance(cur, dict) or not cur.get("generation"):
        return None, "CURRENT_UNREADABLE"
    return cur, None


def _carry(src: Path, dst: Path) -> None:
    """An unchanged file into the new generation: a hard link, else a copy."""
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _manifest(gd: Path) -> dict:
    files = {}
    for p in sorted(gd.iterdir()):
        if not p.is_file():
            continue
        rec: dict[str, Any] = {"bytes": p.stat().st_size, "sha256": _sha256_file(p)}
        if p.name.startswith("postings_"):
            po = _read_json(p, {}) or {}
            rec["rows"] = int(po.get("n_rows") or 0)
        files[p.name] = rec
    return files


def verify(root: Path, *, full: bool = True) -> dict:
    """Every problem of the current generation by name. `full` re-hashes every file; the
    request path checks sizes and counts only (`index_problems`)."""
    root = Path(root)
    cur, prob = read_current(root)
    if cur is None:
        return {"status": "NO_INDEX" if prob is None else "DEGRADED", "problems": [prob] if prob else [],
                "generation": None}
    problems = list(index_problems(root, cur))
    if full and not any(p.startswith(("GENERATION_MISSING", "INDEX_SCHEMA")) for p in problems):
        gd = root / cur["generation"]
        for name, rec in (cur.get("manifest") or {}).items():
            p = gd / name
            if p.is_file() and _sha256_file(p) != rec.get("sha256"):
                problems.append(f"FILE_HASH_MISMATCH:{name}")
        for name, rec in (cur.get("manifest") or {}).items():
            if name.startswith("rows_"):
                m = name[len("rows_"):-len(".jsonl")]
                try:
                    with open(gd / name, "rb") as fh:
                        n = sum(1 for line in fh if line.strip())
                except OSError:
                    continue
                want = ((cur.get("manifest") or {}).get(f"postings_{m}.json") or {}).get("rows")
                if want is not None and n != want:
                    problems.append(f"ROWS_POSTINGS_MISMATCH:{m}")
    problems = sorted(set(problems))
    return {"status": "DEGRADED" if problems else "OK", "problems": problems,
            "generation": cur.get("generation"), "built_utc": cur.get("built_utc")}


_PROBLEM_CACHE: dict[str, tuple[Any, list]] = {}


def index_problems(root: Path, cur: dict) -> list[str]:
    """Cheap checks: schema, generation present, every manifest file present at its size,
    postings parse and match the manifest's row counts."""
    if cur.get("schema") != INDEX_SCHEMA:
        return [f"INDEX_SCHEMA_OLD:{cur.get('schema')}"]
    gd = Path(root) / cur["generation"]
    if not gd.is_dir():
        return [f"GENERATION_MISSING:{cur['generation']}"]
    problems = []
    for name, rec in (cur.get("manifest") or {}).items():
        p = gd / name
        try:
            size = p.stat().st_size
        except OSError:
            problems.append(f"FILE_MISSING:{name}")
            continue
        if size != rec.get("bytes"):
            problems.append(f"FILE_SIZE_MISMATCH:{name}")
            continue
        if name.startswith("postings_"):
            po = _cached_json(p)
            if not isinstance(po, dict):
                problems.append(f"POSTINGS_UNREADABLE:{name}")
            elif int(po.get("n_rows") or 0) != int(rec.get("rows") or 0):
                problems.append(f"POSTINGS_COUNT_MISMATCH:{name}")
        if name == "universe.json":
            uni = _cached_json(p)
            if not isinstance(uni, dict) or not uni:
                problems.append("UNIVERSE_UNREADABLE")
    for need in ("universe.json", "forecasts_index.json", "forecasts.jsonl", "state.json"):
        if need not in (cur.get("manifest") or {}):
            problems.append(f"FILE_NOT_IN_MANIFEST:{need}")
    return problems


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
    """Index everything new since the last build into a NEW generation under `out`
    (default `<data_root>/ticker_hub`). Reads the data root only; writes only under `out`."""
    t0 = time.time()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    P = paths or default_paths(data_root)
    check_inputs(P)
    root = hub_dir(data_root, out)
    root.mkdir(parents=True, exist_ok=True)
    with _Lock(root / ".build.lock"):
        return _build_locked(P, root, now, int(index_days or C.TICKER_HUB_INDEX_DAYS), t0, with_extras)


def _build_locked(P: dict, root: Path, now: datetime, index_days: int, t0: float,
                  with_extras: bool) -> dict:
    stats: Counter = Counter()
    cur, cur_prob = read_current(root)
    prev_gd: Optional[Path] = None
    if cur is not None and cur.get("schema") == INDEX_SCHEMA and (root / cur["generation"]).is_dir():
        prev_gd = root / cur["generation"]
    elif cur is not None or cur_prob:
        stats["schema_or_current_rebuild"] += 1
    if cur is None and (root / "state.json").is_file():
        # a v1 cache: its row ids are not v2's, so it is removed and rebuilt, never mixed
        for p in list(root.glob("rows_*.jsonl")) + list(root.glob("postings_*.json")) + [root / n for n in _V1_FILES]:
            if p.is_file():
                p.unlink()
                stats["v1_files_removed"] += 1
    state = (_read_json(prev_gd / "state.json", None) if prev_gd else None) or {"schema": STATE_SCHEMA}
    first_build = prev_gd is None
    gen = f"g_{now.strftime('%Y%m%dT%H%M%SZ')}_{os.getpid()}"
    gd = root / (gen + ".tmp")
    if gd.exists():
        shutil.rmtree(gd)
    gd.mkdir(parents=True)
    tbl = NE.tables(issuers=Path(P["issuers"]))
    try:
        cik_map = DA.load_cik_map(Path(P["cik_map"]))
        cik_status = "OK"
    except Exception as exc:                                           # noqa: BLE001
        cik_map, cik_status = {}, f"CIK_MAP_UNAVAILABLE: {str(exc)[:160]}"
    typed = (_read_json(prev_gd / "typed.json", None) if prev_gd else None) or {}
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
                stats["deferred_after_now"] += 1          # the cursor stops here; the next build reads it
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
                        deferred += 1                     # left unseen for the next build
                        stats["deferred_after_now"] += 1
                        continue
                    seen.add(name)
                    stats["reader_pages_read"] += 1
                    new_rows.extend(_reader_rows(pub.name, page, tagger, now, stats))
                    fs = page.get("first_seen_utc")
                    s = f"reader:{pub.name}"
                    if isinstance(fs, str) and fs > (newest.get(s) or "") and fs <= _iso(now):
                        newest[s] = fs
                rd_state[key] = {"mtime_ns": None if deferred else mt, "seen": sorted(seen)}

    # merge into month shards of the NEW generation; untouched shards are carried over
    keys: dict = state.setdefault("keys", {})
    by_month: dict[str, list[dict]] = {}
    for r in new_rows:
        m = keys.get(r["id"]) or _month(r["first_seen_utc"])
        by_month.setdefault(m, []).append(r)
    shard_receipts = []
    months_prev = sorted(p.name[len("rows_"):-len(".jsonl")] for p in prev_gd.glob("rows_*.jsonl")) if prev_gd else []
    for m in sorted(set(months_prev) | set(by_month)):
        if m not in by_month:
            for p in shard_paths(prev_gd, m):            # type: ignore[arg-type]
                _carry(p, gd / p.name)
            continue
        rows = _read_shard(shard_paths(prev_gd, m)[0]) if prev_gd else {}
        before = len(rows)
        for r in by_month[m]:
            if r["id"] in rows:
                _fold(rows[r["id"]], r)
                stats["rows_folded"] += 1
            else:
                rows[r["id"]] = r
                keys[r["id"]] = m
        shard_receipts.append({**_write_shard(gd, m, rows), "new": len(rows) - before})
    _write_json(gd / "typed.json", typed)

    # one pass over the whole index: totals, tiers, co-mentions
    totals = _index_totals(gd, now)
    _write_json(gd / "comention.json", totals.pop("comention"))
    read_total = sum(v for k, v in stats.items() if k.startswith("rows_read:"))
    untagged_total = sum(v for k, v in stats.items() if k.startswith("rows_untagged:"))
    per_source = {}
    for k, v in stats.items():
        if k.startswith("rows_read:"):
            s = k.split(":", 1)[1]
            u = stats.get(f"rows_untagged:{s}", 0)
            per_source[s] = {"read": v, "untagged": u, "tagged": v - u,
                             "untagged_share": round(u / v, 4) if v else None}
    by_method_new: Counter = Counter()
    for r in new_rows:
        for t in r["tags"]:
            by_method_new[f"{t['m']}/{t.get('tier')}"] += 1

    extras: dict = {}
    if with_extras:
        uni = load_universe(P, tbl)
        _write_json(gd / "universe.json", uni)
        extras["universe"] = {"symbols": len(uni), "with_sector": sum(1 for v in uni.values() if v.get("sector")),
                              "with_dollar_volume": sum(1 for v in uni.values() if v.get("dollar_volume")),
                              "potential_universe_dir": str(P["potential_universe"])}
        extras["forecasts"] = build_forecasts(Path(P["predictions"]), gd, prev_gd, state, stats)
        try:
            extras["events"] = build_events(Path(P["event_store"]), gd, now)
        except Exception as exc:                                       # noqa: BLE001
            extras["events"] = {"status": f"EVENTS_UNREADABLE: {type(exc).__name__}: {str(exc)[:160]}"}
        extras["related"] = build_related(Path(P["graph"]), gd, now)
    elif prev_gd is not None:
        for name in ("universe.json", "forecasts.jsonl", "forecasts_index.json", "events.json", "related.json"):
            if (prev_gd / name).is_file():
                _carry(prev_gd / name, gd / name)

    state["common"] = {"low": dict(low), "cap": dict(cap)}
    state["built_utc"] = _iso(now)
    state["n_builds"] = int(state.get("n_builds") or 0) + 1
    state["schema"] = STATE_SCHEMA
    _write_json(gd / "state.json", state)
    receipt = {
        "schema": SCHEMA, "index_schema": INDEX_SCHEMA, "generation": gen, "built_utc": _iso(now),
        "first_build": first_build, "index_days": index_days, "cutoff_day": cutoff_day,
        "data_root_corpus": str(corpus), "out": str(root),
        "rows_read_new": read_total, "rows_untagged_new": untagged_total,
        "rows_tagged_new": read_total - untagged_total,
        "untagged_share_new": round(untagged_total / read_total, 4) if read_total else None,
        "tags_by_method_tier_new": dict(by_method_new), **totals,
        "per_source_new": dict(sorted(per_source.items())),
        "newest_per_source": dict(sorted(newest.items())),
        "shards_written": shard_receipts, "cik_map": cik_status,
        "common_word_keys": len(common),
        "refused_top": dict(tagger.refused.most_common(30)),
        "counts": {k: v for k, v in sorted(stats.items())
                   if not k.startswith(("rows_read:", "rows_untagged:"))},
        **extras,
    }
    receipt["elapsed_s"] = round(time.time() - t0, 1)
    _write_json(gd / "latest.json", receipt)

    # publish: the generation dir is renamed into place, then CURRENT.json points at it
    manifest = _manifest(gd)
    final = root / gen
    os.replace(gd, final)
    _write_json(root / CURRENT_NAME, {"schema": INDEX_SCHEMA, "generation": gen, "built_utc": _iso(now),
                                       "rows_in_index": totals["rows_in_index"], "manifest": manifest})
    _prune_generations(root, keep={gen, prev_gd.name if prev_gd else ""})
    rec_dir = root / "receipts"
    rec_dir.mkdir(exist_ok=True)
    _write_json(rec_dir / f"build_{now.strftime('%Y%m%dT%H%M%SZ')}_{os.getpid()}.json", receipt)
    v = verify(root, full=True)
    receipt["verify"] = v
    if v["problems"]:
        raise TickerHubRefused(INDEX_DAMAGED, f"the new generation {gen} fails verify: {v['problems']}")
    if totals["rows_in_index"] == 0:
        raise TickerHubRefused(NOTHING_INDEXED, f"0 tagged rows in the index at {root} "
                                                f"({read_total} rows read this build)")
    return receipt


def _prune_generations(root: Path, keep: set) -> None:
    gens = sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("g_"))
    n_keep = int(C.TICKER_HUB_KEEP_GENERATIONS)
    candidates = [p for p in gens if p.name not in keep]
    excess = len(gens) - n_keep
    for p in candidates:
        if excess <= 0 and not p.name.endswith(".tmp"):
            break
        try:
            shutil.rmtree(p)
            excess -= 1
        except OSError:
            pass                                        # a reader still holds a file open; next build


def _index_totals(gd: Path, now: datetime) -> dict:
    """Totals over every row of a generation, plus co-mention counts over
    TICKER_HUB_COMENTION_DAYS (rows naming both tickers, any tier)."""
    lo = _iso(now - timedelta(days=int(C.TICKER_HUB_COMENTION_DAYS))) or ""
    n = 0
    by_mt: Counter = Counter()
    about: Counter = Counter()
    pairs: dict[str, Counter] = {}
    for rp in sorted(gd.glob("rows_*.jsonl")):
        with open(rp, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                n += 1
                syms = sorted({t["t"] for t in r.get("tags") or []})
                for t in r.get("tags") or []:
                    by_mt[f"{t['m']}/{t.get('where')}/{t.get('tier')}"] += 1
                    if t.get("tier") == "about":
                        about[t["t"]] += 1
                if 1 < len(syms) <= 12 and (r.get("eff_utc") or r.get("first_seen_utc") or "") >= lo:
                    for a in syms:
                        c = pairs.setdefault(a, Counter())
                        for b in syms:
                            if b != a:
                                c[b] += 1
    com = {a: c.most_common(60) for a, c in pairs.items()}
    return {"rows_in_index": n, "tags_by_method_where_tier_index": dict(by_mt.most_common()),
            "about_top": about.most_common(25), "comention": com}


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
        if len(_CACHE) > 32:
            for kk in list(_CACHE)[:len(_CACHE) - 32]:
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


class Index:
    """One resolved generation for one request, collecting every problem it meets."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.cur, prob = read_current(self.root)
        self.problems: list[str] = [prob] if prob else []
        self.gd: Optional[Path] = None
        if self.cur is not None:
            self.problems += index_problems(self.root, self.cur)
            if not any(p.startswith(("INDEX_SCHEMA_OLD", "GENERATION_MISSING")) for p in self.problems):
                self.gd = self.root / self.cur["generation"]
        elif prob is None and (self.root / "state.json").is_file():
            self.problems.append("INDEX_SCHEMA_OLD:v1 (no CURRENT.json)")

    @property
    def present(self) -> bool:
        return self.gd is not None

    def json(self, name: str) -> Any:
        return _cached_json(self.gd / name) if self.gd else None

    def universe(self) -> dict:
        u = self.json("universe.json")
        return u if isinstance(u, dict) else {}

    def postings(self, months: list[str]) -> list[tuple[str, dict]]:
        out = []
        if not self.gd:
            return out
        for m in months:
            rp, pp = shard_paths(self.gd, m)
            if not pp.is_file():
                continue
            po = _cached_json(pp)
            if not isinstance(po, dict):
                self.problems.append(f"POSTINGS_UNREADABLE:postings_{m}.json")
                continue
            out.append((m, po))
        return out

    def read_at(self, month: str, offsets: Iterable[int], want: Optional[set] = None,
                tier: str = "all") -> list[dict]:
        """Rows at byte offsets; an unparseable line or a row that does not carry the
        ticker its posting promised is a named problem, never a silent skip."""
        rows: list[dict] = []
        offs = sorted(set(offsets))
        if not offs or not self.gd:
            return rows
        bad = mismatch = 0
        try:
            fh = open(shard_paths(self.gd, month)[0], "rb")
        except OSError:
            self.problems.append(f"FILE_MISSING:rows_{month}.jsonl")
            return rows
        with fh:
            for off in offs:
                fh.seek(off)
                line = fh.readline()
                try:
                    r = json.loads(line.decode("utf-8"))
                except ValueError:
                    bad += 1
                    continue
                if want:
                    tags = [t for t in r.get("tags") or [] if t["t"] in want
                            and (tier == "all" or t.get("tier") == "about")]
                    if not tags:
                        mismatch += 1
                        continue
                rows.append(r)
        if bad:
            self.problems.append(f"ROWS_UNREADABLE_AT_OFFSET:rows_{month}.jsonl:{bad}")
        if mismatch:
            self.problems.append(f"ROWS_POSTINGS_MISMATCH:rows_{month}.jsonl:{mismatch}")
        return rows


def source_ages(newest: dict, now: datetime) -> list[dict]:
    """Every source's newest row, its age and its limit; `stale` past the limit."""
    out = []
    by = dict(C.TICKER_HUB_SOURCE_STALE_HOURS_BY_SOURCE)
    for s, t in sorted((newest or {}).items()):
        d = DA._utc(t)
        age_h = None if d is None else round((now - d).total_seconds() / 3600.0, 1)
        lim = float(by.get(s, C.TICKER_HUB_SOURCE_STALE_HOURS))
        out.append({"source": s, "newest_utc": t, "age_hours": age_h, "limit_hours": lim,
                    "stale": age_h is None or age_h > lim})
    return out


def index_status(root: Path, now: datetime, ix: Optional[Index] = None) -> dict:
    """OK / STALE / DEGRADED / NO_INDEX, with every named problem and the per-source ages."""
    ix = ix or Index(root)
    lim = int(float(C.TICKER_HUB_STALE_HOURS) * 3600)
    base = {"stale_after_s": lim, "generation": (ix.cur or {}).get("generation")}
    if ix.cur is None and not ix.problems:
        return {**base, "status": "NO_INDEX", "index_built_utc": None, "index_age_s": None, "problems": [],
                "sources": [], "stale_sources": [],
                "detail": f"no index at {root}: run `python -m scripts.ticker_hub build`"}
    latest = ix.json("latest.json") or {}
    built = DA._utc((ix.cur or {}).get("built_utc"))
    age = None if built is None else int((now - built).total_seconds())
    ages = source_ages(latest.get("newest_per_source") or {}, now)
    stale_src = [a for a in ages if a["stale"]]
    problems = sorted(set(ix.problems))
    if any(p.startswith("INDEX_SCHEMA_OLD") for p in problems) and ix.gd is None:
        status = "NO_INDEX"
        detail = f"the index at {root} is an older layout ({problems[0]}): run `python -m scripts.ticker_hub build`"
    elif problems:
        status = "DEGRADED"
        detail = ("DEGRADED: the index is damaged (" + ", ".join(problems[:6]) +
                  "); run `python -m scripts.ticker_hub verify`, then `build`")
    elif age is None or age > lim:
        status = "STALE"
        detail = f"STALE: the index was built {age} s ago (limit {lim} s); run `python -m scripts.ticker_hub build`"
    else:
        status, detail = "OK", None
    return {**base, "status": status, "index_built_utc": (ix.cur or {}).get("built_utc"), "index_age_s": age,
            "problems": problems, "rows_in_index": (ix.cur or {}).get("rows_in_index"),
            "untagged_share_last_build": latest.get("untagged_share_new"),
            "sources": ages, "stale_sources": stale_src, "detail": detail}


def _siblings(sym: str) -> list[str]:
    return [sym] + [DA.norm_ticker(s) for s in dict(C.TICKER_HUB_SIBLINGS).get(sym, ())]


def _decorate(r: dict, typed: dict, want: Optional[set] = None) -> dict:
    ty = typed.get(r.get("url_key") or "") if typed else None
    out = {k: r.get(k) for k in ("id", "source", "publisher", "kind", "first_seen_utc", "published_utc",
                                  "eff_utc", "title", "url", "regions", "tags")}
    fs, pb = DA._utc(r.get("first_seen_utc")), DA._utc(r.get("published_utc"))
    out["show_both_times"] = bool(fs and pb and abs((fs - pb).total_seconds()) > int(C.TICKER_HUB_SHOW_BOTH_TIMES_S))
    out["event"] = ({k: ty.get(k) for k in ("event_type", "topic", "sentiment", "model")} if ty else None)
    if want:
        mine = [t for t in r.get("tags") or [] if t["t"] in want]
        out["tagged_by"] = sorted({t["m"] for t in mine},
                                  key=lambda m: METHODS.index(m) if m in METHODS else 99)
        out["tier"] = "about" if any(t.get("tier") == "about" for t in mine) else "mentions"
    return out


def stories(rows: list[dict]) -> list[list[dict]]:
    """Rows that share a URL or a normalised title (>= TICKER_HUB_MIN_STORY_TITLE_CHARS) are
    one story. Returned as groups, each sorted earliest first."""
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen: dict[str, int] = {}
    mn = int(C.TICKER_HUB_MIN_STORY_TITLE_CHARS)
    for i, r in enumerate(rows):
        keys = []
        if r.get("url_key"):
            keys.append("u:" + r["url_key"])
        nt = norm_title(r.get("title") or "")
        if len(nt) >= mn:
            keys.append("t:" + nt)
        for k in keys:
            if k in seen:
                a, b = find(i), find(seen[k])
                if a != b:
                    parent[a] = b
            else:
                seen[k] = i
    groups: dict[int, list[dict]] = {}
    for i, r in enumerate(rows):
        groups.setdefault(find(i), []).append(r)
    out = []
    for g in groups.values():
        g.sort(key=lambda r: (r.get("eff_utc") or r.get("first_seen_utc") or "", r.get("id") or ""))
        out.append(g)
    out.sort(key=lambda g: (g[0].get("eff_utc") or g[0].get("first_seen_utc") or "", g[0].get("id") or ""),
             reverse=True)
    return out


def _story_payload(g: list[dict], typed: dict, want: Optional[set]) -> dict:
    head = _decorate(g[0], typed, want)
    head["copies"] = len(g)
    head["sources"] = sorted({r["source"] for r in g})
    head["publishers"] = sorted({r.get("publisher") or r["source"] for r in g})
    head["other_copies"] = [{"source": r["source"], "publisher": r.get("publisher"), "url": r.get("url"),
                             "first_seen_utc": r.get("first_seen_utc"), "published_utc": r.get("published_utc")}
                            for r in g[1:20]]
    if want:
        tiers = {t.get("tier") for r in g for t in r.get("tags") or [] if t["t"] in want}
        head["tier"] = "about" if "about" in tiers else "mentions"
    return head


def news_page(ix: Index, syms: list[str], days: int, now: datetime, *, tier: str = "about",
              offset: int = 0, limit: Optional[int] = None) -> tuple[list[dict], dict]:
    """One page of distinct stories for `syms` in the window (by when each row happened)."""
    lim = max(1, min(int(limit or C.TICKER_HUB_NEWS_PAGE), 500))
    lo_ep = int((now - timedelta(days=days)).timestamp())
    want = set(syms)
    key = "about" if tier == "about" else "ticker"
    rows: list[dict] = []
    for m, po in ix.postings(_months_between(now - timedelta(days=days), now)):
        offs = {off for s in syms for ep, off in (po.get(key) or {}).get(s, []) if ep >= lo_ep}
        rows += ix.read_at(m, offs, want, "about" if tier == "about" else "all")
    groups = stories(rows)
    typed = ix.json("typed.json") or {}
    page = [_story_payload(g, typed, want) for g in groups[offset:offset + lim]]
    by_source = Counter(r["source"] for r in rows)
    by_method = Counter(t["m"] for r in rows for t in r.get("tags") or [] if t["t"] in want)
    newest = max((g[0].get("eff_utc") or "" for g in groups), default=None)
    return page, {"tier": tier, "n_stories": len(groups), "n_rows": len(rows), "n_returned": len(page),
                  "offset": offset, "limit": lim, "has_more": offset + lim < len(groups),
                  "sources": dict(by_source.most_common()), "tagged_by": dict(by_method),
                  "newest_utc": newest or None}


def tier_counts(ix: Index, syms: list[str], days: int, now: datetime) -> dict:
    lo_ep = int((now - timedelta(days=days)).timestamp())
    out = {"about": 0, "all": 0}
    for _m, po in ix.postings(_months_between(now - timedelta(days=days), now)):
        out["about"] += len({off for s in syms for ep, off in (po.get("about") or {}).get(s, []) if ep >= lo_ep})
        out["all"] += len({off for s in syms for ep, off in (po.get("ticker") or {}).get(s, []) if ep >= lo_ep})
    return out


def forecasts_for(ix: Index, syms: list[str]) -> dict:
    empty = {"open": [], "resolved": [], "void": [], "counts": {"open": 0, "resolved": 0, "void": 0}}
    idx = ix.json("forecasts_index.json")
    fp = ix.gd / "forecasts.jsonl" if ix.gd else None
    if not isinstance(idx, dict) or fp is None or not fp.is_file():
        ix.problems.append("FORECASTS_MISSING")
        return {"status": "FORECASTS_MISSING", **empty}
    rows: list[dict] = []
    for s in syms:
        off = idx.get(s)
        if off is None:
            continue
        try:
            with open(fp, "rb") as fh:
                fh.seek(int(off))
                rows += json.loads(fh.readline().decode("utf-8")).get("rows") or []
        except (OSError, ValueError, AttributeError):
            ix.problems.append("FORECASTS_UNREADABLE")
            return {"status": "FORECASTS_UNREADABLE", **empty}
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


RELATED_PEER_RANK = ("same-sector peers ranked by how many rows of our own corpus name both tickers "
                     f"(last {int(C.TICKER_HUB_COMENTION_DAYS)} days), then by median dollar volume "
                     "(potential_universe; no market cap is on file)")


def related_for(ix: Index, sym: str) -> list[dict]:
    uni = ix.universe()
    me = uni.get(sym) or {}
    out: list[dict] = []
    rel = (ix.json("related.json") or {}).get("tickers") or {}
    for g in rel.get(sym) or []:
        t = DA.norm_ticker(g.get("ticker"))
        out.append({"ticker": t, "name": (uni.get(t) or {}).get("name"), "link": g.get("link"),
                    "weight": g.get("weight"), "n": g.get("n"), "sign": g.get("sign"),
                    "source": "universe_graph", "graph_build_id": g.get("graph_build_id"),
                    "rank_by": "universe graph link weight"})
    sec = me.get("sector")
    if sec:
        have = {r["ticker"] for r in out}
        com = dict(((ix.json("comention.json") or {}).get(sym) or []))
        peers = [s for s, v in uni.items() if v.get("sector") == sec and s != sym and s not in have]
        peers.sort(key=lambda s: (-int(com.get(s, 0)), -(uni[s].get("dollar_volume") or 0.0), s))
        for s in peers[:int(C.TICKER_HUB_SECTOR_PEERS)]:
            out.append({"ticker": s, "name": uni[s].get("name"), "link": "same_sector", "weight": None,
                        "n": int(com.get(s, 0)), "sign": None, "source": "potential_universe.identity.sector",
                        "graph_build_id": None, "dollar_volume": uni[s].get("dollar_volume"),
                        "rank_by": RELATED_PEER_RANK})
    return out


def _resolve(data_root: Optional[Path], out: Optional[Path]) -> tuple[Path, Path]:
    dr = Path(data_root) if data_root else default_data_root()
    return dr, hub_dir(dr, out)


def hub(symbol: str, *, data_root: Optional[Path] = None, out: Optional[Path] = None,
        days: Optional[int] = None, now: Optional[datetime] = None, tier: str = "about",
        offset: int = 0, limit: Optional[int] = None) -> dict:
    """Everything the index holds on one ticker. KeyError only for a symbol a READABLE
    universe does not hold; a damaged index answers with status DEGRADED instead."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    dr, root = _resolve(data_root, out)
    ix = Index(root)
    sym = DA.norm_ticker(symbol)
    uni = ix.universe()
    if ix.present and uni and sym not in uni:
        raise KeyError(sym)
    d = _clamp_days(days)
    syms = _siblings(sym)
    news, ncov = news_page(ix, syms, d, now, tier=tier, offset=offset, limit=limit)
    ev = ((ix.json("events.json") or {}).get("tickers") or {})
    payload = {"schema": SCHEMA, "ticker": sym, "siblings": syms[1:], "days": d, "now_utc": _iso(now),
               "identity": uni.get(sym) or None,
               "news": news,
               "tier_counts": tier_counts(ix, syms, d, now),
               "forecasts": forecasts_for(ix, syms),
               "calendar": calendar_for(dr, sym, now),
               "events": [e for s in syms for e in ev.get(s, [])][:50],
               "related": related_for(ix, sym), "related_rank": RELATED_PEER_RANK}
    payload["coverage"] = {**index_status(root, now, ix), **ncov}
    return payload


def news(symbol: str, *, data_root: Optional[Path] = None, out: Optional[Path] = None,
         days: Optional[int] = None, now: Optional[datetime] = None, tier: str = "about",
         offset: int = 0, limit: Optional[int] = None) -> dict:
    """One more page of a ticker's stories ("load more")."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _dr, root = _resolve(data_root, out)
    ix = Index(root)
    sym = DA.norm_ticker(symbol)
    uni = ix.universe()
    if ix.present and uni and sym not in uni:
        raise KeyError(sym)
    page, ncov = news_page(ix, _siblings(sym), _clamp_days(days), now, tier=tier, offset=offset, limit=limit)
    return {"schema": SCHEMA, "ticker": sym, "news": page, "coverage": {**index_status(root, now, ix), **ncov}}


def feed(*, data_root: Optional[Path] = None, out: Optional[Path] = None, ticker: Optional[str] = None,
         sector: Optional[str] = None, source: Optional[str] = None, days: Optional[int] = None,
         limit: Optional[int] = None, now: Optional[datetime] = None, tier: str = "about") -> dict:
    """The news feed filtered by ticker / sector / source, as distinct stories newest first,
    with facets (ROW counts by ticker, sector and source inside the same window and filters)."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    _dr, root = _resolve(data_root, out)
    ix = Index(root)
    d = _clamp_days(days)
    lim = max(1, min(int(limit or C.TICKER_HUB_FEED_LIMIT), int(C.TICKER_HUB_FEED_LIMIT)))
    uni = ix.universe()
    lo_ep = int((now - timedelta(days=d)).timestamp())
    want_t = set(_siblings(DA.norm_ticker(ticker))) if ticker else None
    if want_t is not None and ix.present and uni and DA.norm_ticker(ticker) not in uni:
        raise KeyError(DA.norm_ticker(ticker))
    sec_syms = {s for s, v in uni.items() if v.get("sector") == sector} if sector else None
    tkey = "about" if tier == "about" else "ticker"
    picked: list[tuple[int, str, int]] = []
    f_ticker: Counter = Counter()
    f_source: Counter = Counter()
    f_sector: Counter = Counter()
    for m, po in ix.postings(_months_between(now - timedelta(days=d), now)):
        tick = po.get(tkey) or {}

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
        ep_of = {e[1]: e[0] for e in po.get("all") or [] if e[0] >= lo_ep and (tier != "about" or e[2])}
        if cand is None:
            cand = set(ep_of)
        cand &= set(ep_of)
        for off in cand:
            picked.append((ep_of[off], m, off))
        src_of = {}
        for s, lst in (po.get("source") or {}).items():
            for _ep, off in lst:
                if off in cand:
                    src_of[off] = s
        f_source.update(src_of.values())
        sec_of: dict[int, set] = {}
        for s, lst in tick.items():
            hit = [off for _ep, off in lst if off in cand]
            if hit:
                f_ticker[s] += len(hit)
                sv = (uni.get(s) or {}).get("sector")
                if sv:
                    for off in hit:
                        sec_of.setdefault(off, set()).add(sv)
        for secs in sec_of.values():
            f_sector.update(secs)
    picked.sort(reverse=True)
    scan = picked[:max(lim * 4, lim)]
    by_m: dict[str, list[int]] = {}
    for _ep, m, off in scan:
        by_m.setdefault(m, []).append(off)
    rows: list[dict] = []
    for m, offs in by_m.items():
        rows += ix.read_at(m, offs, want_t, "about" if tier == "about" else "all")
    groups = stories(rows)
    typed = ix.json("typed.json") or {}
    page = [_story_payload(g, typed, want_t) for g in groups[:lim]]
    top = int(C.TICKER_HUB_FACET_TOP)
    return {"schema": SCHEMA, "now_utc": _iso(now), "days": d, "tier": tier,
            "filters": {"ticker": DA.norm_ticker(ticker) if ticker else None, "sector": sector,
                        "source": source},
            "rows": page, "n_rows": len(picked), "n_stories_in_scan": len(groups),
            "n_rows_scanned": len(scan), "n_returned": len(page), "truncated": len(picked) > len(scan),
            "facets": {"ticker": [{"key": k, "n": n, "name": (uni.get(k) or {}).get("name")}
                                  for k, n in f_ticker.most_common(top)],
                       "sector": [{"key": k, "n": n} for k, n in f_sector.most_common(top)],
                       "source": [{"key": k, "n": n} for k, n in f_source.most_common()]},
            "sectors": sorted({v["sector"] for v in uni.values() if v.get("sector")}),
            "coverage": index_status(root, now, ix)}


def iter_index_rows(root: Path) -> Iterator[dict]:
    """Every stored row of the CURRENT generation (tests and the CLI)."""
    cur, _ = read_current(Path(root))
    if cur is None:
        return
    gd = Path(root) / cur["generation"]
    for rp in sorted(gd.glob("rows_*.jsonl")):
        with open(rp, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def current_dir(root: Path) -> Optional[Path]:
    cur, _ = read_current(Path(root))
    return (Path(root) / cur["generation"]) if cur else None
