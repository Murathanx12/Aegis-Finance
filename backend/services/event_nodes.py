"""CH-35 slice 1 -- EVENT NODES from what the corpus already holds.

Owner design (2026-11-12): the reader should understand what it reads; an
important event becomes a NODE with its news connected to it (the article's own
sources, the filing, coverage from other regions so their biases are visible,
the upcoming dates); after its time passes the node loses importance and is
kept as context and learning material.

The known-answer case this was built against: on 2026-11-12 the corpus held the
Nvidia/Huang story (Barron's 00:29Z, MarketWatch 01:12Z, 07:34Z, 14:20Z,
Barron's 14:34Z, an NVDA 8-K item 5.02, Barron's 14:46Z) hours before the open,
and nothing built an event from it.

WHAT THIS SLICE DOES (no LLM, no network, deterministic)
========================================================
1. READ corpus rows (`news_corpus/<source>/<YYYY-MM-DD>.jsonl`, the same layout
   `discovery_autopsy.Corpus` reads) and SEC 8-K rows of
   `official/tables/filing_events.jsonl`, inside [since, now]. A row first seen
   after `now`, or published after it, is dropped and counted (no look-ahead).
   Quote/estimate pages (`config.AUTOPSY_NOT_NEWS_TAGS`) are attention, not news.
2. RESOLVE issuers with the issuer table CH-14a and the universe graph use
   (`news_entities`: explicit tokens and issuer names; bare words never match),
   plus two stricter rules: a symbol that is also a word (`AI`, `IT`, `ON`, `ALL`,
   `NOW`, `A`, `GOLD`, ...) is never taken from a parenthesis, only from `$AI` /
   `NASDAQ: AI`; name keys in `EVENT_NODES_DROP_NAME_KEYS` ("target", "nasdaq")
   never connect. The static display-name map of `ticker_resolver` adds names the
   issuer table lacks ("Marvell"), under the same length/ambiguity guards, and
   every hit carries the rule that produced it. SEC rows resolve by CIK.
3. CLUSTER: evidence items (one per accession, else one per publisher+title, so a
   Google News article seen in five regional editions is ONE item with five
   regions) are walked in first-seen order. An item joins the best cluster of
   one of its TITLE issuers when it was first seen within
   `EVENT_NODES_JOIN_GAP_HOURS` of a member and its title+lead tokens reach
   `EVENT_NODES_JOIN_MIN_SIMILARITY` (IDF-weighted overlap coefficient, at least
   `EVENT_NODES_JOIN_MIN_SHARED_TOKENS` shared stems, single link, issuer names removed); else it starts a new cluster. Every join prints its score.
4. SCORE importance from countable facts only; each component and its weight is
   printed (`config.EVENT_NODES_IMPORTANCE_WEIGHTS`).
5. WRITE one EVENT NODE per event to an append-only, hash-chained JSONL store
   (`event_nodes.jsonl`, schema `event-node/1`). A rebuild appends a new
   version only when the content changed. Article BODIES are never written.
   `open_questions` / `dated_facts` / `stances` are UNFILLED here; `fill_event`
   is the LLM step that may fill them later (refused and counted otherwise).
6. DECAY is computed on read: `importance_now = importance_0 * 0.5 ** (age_h /
   EVENT_NODES_HALF_LIFE_HOURS)`; nothing is rewritten in place.

DESCRIPTIVE ONLY. A price reaction is printed as what happened, never as a
prediction, and nothing here is a trade.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from backend import config as C
from backend.services import discovery_autopsy as DA
from backend.services import news_entities as NE

SCHEMA = "event-node/1"
FILL_SCHEMA = "event-node-fill/1"
STORE_NAME = "event_nodes.jsonl"
UNFILLED = "UNFILLED"
GENESIS = "0" * 64

# refusal codes (each a red, non-zero exit in the CLI)
CORPUS_MISSING = "CORPUS_MISSING"
FILINGS_MISSING = "FILINGS_MISSING"
CIK_MAP_MISSING = "CIK_MAP_MISSING"
ISSUERS_MISSING = "ISSUERS_MISSING"
GRAPH_MISSING = "GRAPH_MISSING"
CALENDAR_MISSING = "CALENDAR_MISSING"
BARS_MISSING = "BARS_MISSING"
POSITIONS_MISSING = "POSITIONS_MISSING"
LEDGER_MISSING = "LEDGER_MISSING"
BAD_WINDOW = "BAD_WINDOW"
LOOKAHEAD = "LOOKAHEAD"
NO_EVENTS_FROM_ROWS = "NO_EVENTS_FROM_ROWS"
CHAIN_BROKEN = "CHAIN_BROKEN"

# fill refusal codes
FILL_BUDGET_REFUSED = "BUDGET_REFUSED"
FILL_PROVIDER_FAILED = "PROVIDER_FAILED"
FILL_NOT_JSON = "NOT_JSON"
FILL_BAD_SCHEMA = "BAD_SCHEMA"
FILL_NOTHING_ACCEPTED = "NOTHING_ACCEPTED"


class EventNodesRefused(RuntimeError):
    """The event-node build will not run on these inputs. Always a red exit."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class EventFillRefused(EventNodesRefused):
    """The LLM fill step refused (budget, provider, non-JSON, bad schema)."""


# ─────────────────────────────────────────────── small helpers

_utc = DA._utc
timed_utc = DA.timed_utc


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.astimezone(timezone.utc).isoformat(timespec="seconds") if d else None


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=True,
                                     default=str).encode("utf-8")).hexdigest()


def _as_list(v: Any) -> list:
    return DA._as_list(v)


# ─────────────────────────────────────────────── 1. publishers and regions

_FIXED_PUBLISHER = {
    "dj_reader_barrons": ("Barron's", "US"), "barrons_magazine": ("Barron's", "US"),
    "dj_reader_marketwatch": ("MarketWatch", "US"), "dj_reader_wsj": ("WSJ", "US"),
    "nikkei_asia_rss": ("Nikkei Asia", "JP"), "sec_edgar_8k_current_atom": ("SEC EDGAR", "US"),
    "sec_edgar_8k_ex99_body": ("SEC EDGAR", "US"), "filing_events": ("SEC EDGAR", "US"),
    "alpaca_benzinga_news": ("Benzinga", "US"), "yfinance_ticker_news": ("Yahoo Finance", "US"),
    "quantocracy_rss": ("Quantocracy", "US"),
}
_PREFIX_PUBLISHER = (("wsj_", "WSJ", "US"), ("mw_", "MarketWatch", "US"),
                     ("reddit_", "Reddit", None))
_TITLE_SUFFIX = re.compile(r"\s+[-–—|]\s+([^-–—|]{2,60})$")


def publisher_region(source: str, title: str, url: str) -> tuple[str, Optional[str], str, str]:
    """(publisher, feed_region, clean_title, region_basis).

    `feed_region` is the EDITION the row was seen in (a Google News HK feed is
    HK even when the article is CNBC's); the publisher's own origin is not
    known here and is not guessed."""
    t = (title or "").strip()
    if source.startswith("google_news_rss_"):
        cc = source.rsplit("_", 1)[-1].upper()
        m = _TITLE_SUFFIX.search(t)
        if m:
            return m.group(1).strip(), cc, t[:m.start()].strip(), "google_news_edition"
        return "Google News (unattributed)", cc, t, "google_news_edition"
    if source in _FIXED_PUBLISHER:
        pub, reg = _FIXED_PUBLISHER[source]
        m = _TITLE_SUFFIX.search(t)
        if m and source.startswith("dj_reader_"):
            t = t[:m.start()].strip()
        return pub, reg, t, "source_registry"
    for pre, pub, reg in _PREFIX_PUBLISHER:
        if source.startswith(pre):
            return pub, reg, t, "source_registry"
    if source == "gdelt_doc_v2":
        host = re.sub(r"^https?://(www\.)?", "", url or "").split("/", 1)[0]
        return host or "gdelt (unattributed)", None, t, "url_host"
    return source, None, t, "unknown"


def kind_of(source: str) -> str:
    if source.startswith("sec_") or source == "filing_events":
        return "filing"
    if source.startswith("reddit_") or source == "social":
        return "social"
    return "article"


# ─────────────────────────────────────────────── 2. strict issuer resolution

_ALIAS_CACHE: dict[str, Any] = {}


def _alias_regex(tbl: Any) -> tuple[Optional[re.Pattern], dict[str, str]]:
    """`ticker_resolver._ALIASES` display names, filtered by the same guards the
    issuer table uses (length floor, generic and ambiguous words), and only for
    symbols the issuer table holds."""
    key = (id(tbl), str(getattr(tbl, "issuers_path", "")), len(tbl.symbols), len(tbl.name_to_symbol))
    if _ALIAS_CACHE.get("key") == key:
        return _ALIAS_CACHE["rx"], _ALIAS_CACHE["map"]
    try:
        from backend.services.ticker_resolver import _ALIASES
    except Exception:                                                  # noqa: BLE001
        _ALIASES = {}
    m: dict[str, str] = {}
    drop = set(C.EVENT_NODES_DROP_NAME_KEYS)
    for alias, (sym, _name) in _ALIASES.items():
        a = " ".join(str(alias).lower().split())
        s = str(sym).upper().replace("-", ".")
        if (len(a) < NE.MIN_ALIAS_CHARS or a in NE._GENERIC_ALIASES or a in NE._AMBIGUOUS_NAMES
                or a in drop or a in tbl.name_to_symbol):
            continue
        if s in tbl.symbols or s.replace(".", "-") in tbl.symbols:
            m[a] = s
    rx = (re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(a) for a in sorted(m, key=len, reverse=True))
                     + r")(?![A-Za-z0-9])", re.IGNORECASE) if m else None)
    _ALIAS_CACHE.update({"key": key, "rx": rx, "map": m})
    return rx, m


def common_word_keys(texts: Iterable[str], tbl: Any) -> dict[str, dict]:
    """Single-word issuer-name keys the window itself writes in LOWERCASE ("first",
    "people"): ordinary words, not names. Such a key then needs a corporate cue
    nearby, exactly like `news_entities._AMBIGUOUS_NAMES`. Derived from the window,
    printed in the receipt."""
    low: Counter = Counter()
    cap: Counter = Counter()
    for t in texts:
        for _sym, key, pos in tbl.name_matches(t or ""):
            if " " in key or "." in key:
                continue
            surf = t[pos:pos + len(key)]
            (low if surf.islower() else cap)[key] += 1
    share = float(C.EVENT_NODES_COMMON_WORD_LOWER_SHARE)
    out = {}
    for k, n in low.items():
        if n >= int(C.EVENT_NODES_COMMON_WORD_MIN_LOWER) and n / (n + cap[k]) >= share:
            out[k] = {"lower": n, "capitalised": cap[k]}
    return out


def strict_tickers(text: str, tbl: Any, common: Optional[dict] = None) -> dict[str, str]:
    """{symbol: rule} named by `text`, first-appearance order.

    The news_entities rules, with two stricter guards (module docstring §2).
    Never a bare-word regex: a symbol is taken only from an explicit token or
    from an issuer NAME of at least `news_entities.MIN_ALIAS_CHARS` characters."""
    if not text:
        return {}
    bare = set(C.EVENT_NODES_BAREWORD_SYMBOLS)
    drop = set(C.EVENT_NODES_DROP_NAME_KEYS)
    low = text.lower()
    hits: list[tuple[int, str, str]] = []
    for m in NE._LOCAL_CODE_RE.finditer(text):
        us = tbl.local_to_us.get(m.group(1).upper())
        if us:
            hits.append((m.start(), us, "adr_local_code"))
    for rx, rule in ((NE._CASHTAG_RE, "cashtag"), (NE._PAREN_RE, "paren_ticker"),
                     (NE._VENUE_RE, "venue_ticker")):
        for m in rx.finditer(text):
            sym = m.group(1).upper()
            if sym not in tbl.symbols:
                continue
            if rule == "paren_ticker" and sym in bare:
                continue
            hits.append((m.start(), sym, rule))
    common = common or {}
    for sym, key, pos in tbl.name_matches(text):
        if key in drop:
            continue
        if text[pos:pos + len(key)].islower():
            continue                      # a name written in lowercase is a word
        if ((key in NE._AMBIGUOUS_NAMES or key in common)
                and not NE._cue_near(low, pos, len(key))):
            continue
        hits.append((pos, sym, f"name:{key}"))
    rx, amap = _alias_regex(tbl)
    if rx is not None:
        for m in rx.finditer(text):
            k = " ".join(m.group(1).lower().split())
            if k in amap and not m.group(1).islower():
                hits.append((m.start(), amap[k], f"alias_map:{k}"))
    out: dict[str, str] = {}
    for _pos, sym, rule in sorted(hits, key=lambda h: h[0]):
        s = DA.norm_ticker(sym)
        out.setdefault(s, rule)
    return out


# ─────────────────────────────────────────────── 3. reading the corpus

_TAG = re.compile(r"<[^>]+>")
_URLS = re.compile(r"https?://\S+|www\.\S+")


def clean_text(s: str) -> str:
    """Bodies as text: HTML tags, entities and URLs removed (Google News bodies are
    an HTML list of links)."""
    s = _URLS.sub(" ", _TAG.sub(" ", s or ""))
    s = re.sub(r"&[a-z#0-9]+;", " ", s)
    return " ".join(s.split())


#: 8-K item -> the words a headline about it uses (similarity only; the filing's
#: own item text is not always in the row). Vocabulary, not a parameter.
_ITEM_WORDS = {
    "1.01": "agreement deal contract", "1.02": "agreement terminated", "1.03": "bankruptcy",
    "2.01": "acquisition deal completed", "2.02": "earnings results quarter revenue",
    "2.03": "debt notes bonds", "2.05": "restructuring layoffs job cuts", "2.06": "impairment writedown",
    "3.01": "delisting nasdaq nyse notice", "4.01": "auditor", "4.02": "restatement",
    "5.02": "ceo chief executive officer director board departure resigns ousted appointed interim",
    "5.03": "bylaws", "5.07": "shareholder vote", "7.01": "", "8.01": "", "9.01": "",
}

@dataclass
class Item:
    """One real-world evidence item (several corpus rows may fold into it)."""
    key: str
    source: str
    publisher: str
    kind: str
    title: str
    url: str
    first_seen: datetime
    published: Optional[datetime]
    regions: set = field(default_factory=set)
    feeds: set = field(default_factory=set)
    title_tickers: dict = field(default_factory=dict)
    body_tickers: dict = field(default_factory=dict)
    items_8k: list = field(default_factory=list)
    lead: str = ""          # in memory only, never written
    body: str = ""          # in memory only, never written (the fill prompt reads it)
    region_basis: str = ""

    @property
    def event_time(self) -> datetime:
        return self.published or self.first_seen


def _day_files(root: Path, lo: datetime, hi: datetime) -> list[tuple[str, Path]]:
    out = []
    if not root.is_dir():
        return out
    days = []
    d = (lo - timedelta(days=1)).date()
    while d <= (hi + timedelta(days=1)).date():
        days.append(d.isoformat())
        d += timedelta(days=1)
    for src in sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for dd in days:
            f = root / src / f"{dd}.jsonl"
            if f.is_file():
                out.append((src, f))
    return out


def read_rows(corpus_root: Path, filings_path: Path, *, since: datetime, now: datetime,
              cik_map: dict[int, str], tbl: Any) -> tuple[list[Item], dict]:
    """Rows inside [since, now] by their known-at clock, folded into items."""
    stats: dict[str, Any] = {"per_source": {}, "newest_per_source": {},
                             "dropped_after_now": 0, "dropped_published_after_now": 0,
                             "dropped_undated": 0, "dropped_not_news": 0, "rows_read": 0,
                             "rows_unresolved": 0, "files": 0}
    not_news = set(getattr(C, "AUTOPSY_NOT_NEWS_TAGS", ()))
    items: dict[str, Item] = {}
    pending: list[tuple] = []
    common: dict = {}

    def add(src: str, o: dict, fs: Optional[datetime], pub: Optional[datetime],
            tickers_sec: list[str], items_8k: list[str], acc: Optional[str]) -> None:
        known = fs or pub
        if known is None:
            stats["dropped_undated"] += 1
            return
        if known > now:
            stats["dropped_after_now"] += 1
            return
        if pub is not None and pub > now:
            stats["dropped_published_after_now"] += 1
            return
        if known < since:
            return
        stats["rows_read"] += 1
        stats["per_source"][src] = stats["per_source"].get(src, 0) + 1
        nw = stats["newest_per_source"].get(src)
        if nw is None or known > _utc(nw):
            stats["newest_per_source"][src] = _iso(known)
        raw_title = str(o.get("title") or "")
        url = str(o.get("url") or o.get("index_url") or "")
        publisher, region, title, basis = publisher_region(src, raw_title, url)
        body = clean_text(str(o.get("body") or ""))
        kind = kind_of(src)
        # a filing names its issuer by CIK; its title is a company name, not a headline
        tt = {} if kind == "filing" else strict_tickers(title, tbl, common)
        for t in tickers_sec:
            tt.setdefault(DA.norm_ticker(t), "sec_cik")
        bt = {k: v for k, v in strict_tickers(body[:20000], tbl, common).items() if k not in tt}
        if not tt and not bt:
            stats["rows_unresolved"] += 1
        if acc:
            key = "acc:" + acc.replace("-", "")
        else:
            norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
            key = f"t:{publisher.lower()}:{norm[:160]}" if norm else f"u:{url}"
        it = items.get(key)
        if it is None:
            it = Item(key=key, source=src, publisher=publisher, kind=kind, title=title[:300],
                      url=url[:400], first_seen=known, published=pub, region_basis=basis)
            items[key] = it
        else:
            if known < it.first_seen:
                it.first_seen, it.source = known, src
                if url:
                    it.url = url[:400]
            if pub is not None and (it.published is None or pub < it.published):
                it.published = pub
        if region:
            it.regions.add(region)
        it.feeds.add(src)
        for k, v in tt.items():
            it.title_tickers.setdefault(k, v)
        for k, v in bt.items():
            if k not in it.title_tickers:
                it.body_tickers.setdefault(k, v)
        it.items_8k = sorted(set(it.items_8k) | set(items_8k))
        if len(body) > len(it.body):
            it.body = body[:C.EVENT_NODES_FILL_BODY_CHARS * 2]
            it.lead = body[:C.EVENT_NODES_LEAD_CHARS]
        if it.items_8k:
            it.lead = " ".join([it.lead] + [_ITEM_WORDS.get(x, "") for x in it.items_8k])

    for src, f in _day_files(Path(corpus_root), since, now):
        stats["files"] += 1
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(o, dict):
                    continue
                tags = [str(t) for t in _as_list(o.get("entity_tags"))]
                if any(t in not_news for t in tags):
                    stats["dropped_not_news"] += 1
                    continue
                fs = _utc(o.get("first_seen_utc"))
                pub = timed_utc(o.get("published_utc"))
                sec: list[str] = []
                acc = None
                items_8k = sorted({t.split(":", 1)[1] for t in tags if t.startswith("8-K:")})
                if src.startswith("sec_"):
                    for t in tags:
                        if t.startswith("cik:"):
                            try:
                                hit = cik_map.get(int(t[4:]))
                            except ValueError:
                                hit = None
                            if hit:
                                sec.append(hit)
                    sec += [DA.norm_ticker(t) for t in _as_list(o.get("tickers")) if t]
                    k = DA.item_key(src, tags, str(o.get("url") or ""), o.get("raw_id"), o.get("title"))
                    acc = k[4:] if k.startswith("acc:") else None
                pending.append((src, o, fs, pub, sec, items_8k, acc))
    fp = Path(filings_path)
    lo_s = _iso(since - timedelta(days=2)) or ""
    with fp.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"first_seen_utc"' not in line:
                continue
            m = re.search(r'"first_seen_utc":\s*"([^"]+)"', line)
            if m and m.group(1) < lo_s:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if not isinstance(o, dict) or str(o.get("form_type") or "") not in ("8-K", "8-K/A"):
                continue
            fs = _utc(o.get("first_seen_utc"))
            pub = timed_utc(o.get("public_utc"))
            t = o.get("ticker")
            items_8k = [str(x) for x in _as_list(o.get("items"))]
            title = (f"{o.get('form_type')} - {o.get('company') or ''} items {', '.join(items_8k)}"
                     f" ({', '.join(str(x) for x in _as_list(o.get('event_types')))})")
            pending.append(("filing_events", {"title": title, "url": o.get("index_url"), "body": ""},
                            fs, pub, [t] if t else [], items_8k, str(o.get("accession") or "") or None))
    common.update(common_word_keys(
        (str(p[1].get("title") or "") for p in pending if kind_of(p[0]) != "filing"), tbl))
    stats["common_word_keys"] = common
    for args in pending:
        add(*args)
    out = sorted(items.values(), key=lambda i: (i.first_seen, i.key))
    stats["items"] = len(out)
    return out, stats


# ─────────────────────────────────────────────── 4. clustering

_STOP = frozenset("""
a an the and or but of to in on at for from by with as is are was were be been being it its
this that these those after before over under into about than then so not no yes new says
said say will would could can may might should just more most less very also why how what who
when where which stock stocks shares share market markets inc corp co company report reports
today week year amid up down out off his her their our your has have had do does did one two
s us vs via per here there now get gets got make makes made big top live news update updates
""".split())


def _tokens(text: str, drop_words: set) -> set:
    n = int(C.EVENT_NODES_STEM_CHARS)
    out = set()
    for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(w) < 3 or w in _STOP or w in drop_words or w.isdigit():
            continue
        out.add(w[:n])
    return out


def _name_words(tbl: Any, syms: Iterable[str]) -> set:
    words = set()
    want = set(syms)
    for name, s in tbl.name_to_symbol.items():
        if s in want:
            words.update(re.findall(r"[a-z0-9]+", name))
    for s in want:
        words.add(s.lower())
    return words


@dataclass
class Cluster:
    cid: int
    members: list = field(default_factory=list)       # Items
    tokens: list = field(default_factory=list)        # per member token sets
    joins: list = field(default_factory=list)         # (item index, score, via issuer)
    issuers: Counter = field(default_factory=Counter)


def cluster_items(items: list[Item], tbl: Any) -> tuple[list[Cluster], dict]:
    """Deterministic single-link clustering by title issuer + time + tokens."""
    all_syms = set()
    for it in items:
        all_syms.update(it.title_tickers)
    names = _name_words(tbl, all_syms)
    toks = [_tokens(f"{it.title} {it.lead}", names) for it in items]
    # per-source boilerplate ("Reprints", "Gift Article", a byline): a stem in at
    # least EVENT_NODES_SOURCE_BOILERPLATE_SHARE of one source's items says
    # nothing about the story and would tie that source's items to each other
    src_n: Counter = Counter(it.source for it in items)
    src_df: dict[str, Counter] = {}
    for it, t in zip(items, toks):
        src_df.setdefault(it.source, Counter()).update(t)
    share = float(C.EVENT_NODES_SOURCE_BOILERPLATE_SHARE)
    boiler = {s: {w for w, c in df_.items() if c / src_n[s] >= share}
              for s, df_ in src_df.items() if src_n[s] >= 5}
    toks = [t - boiler.get(it.source, set()) for it, t in zip(items, toks)]
    df: Counter = Counter()
    for t in toks:
        df.update(t)
    n = max(1, len(items))
    idf = {w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()}
    gap = timedelta(hours=float(C.EVENT_NODES_JOIN_GAP_HOURS))
    thr = float(C.EVENT_NODES_JOIN_MIN_SIMILARITY)

    min_shared = int(C.EVENT_NODES_JOIN_MIN_SHARED_TOKENS)

    def sim(a: set, b: set) -> float:
        """IDF-weighted overlap coefficient; 0 below `min_shared` shared stems."""
        shared = a & b
        if len(shared) < min_shared:
            return 0.0
        inter = sum(idf.get(w, 0.0) for w in shared)
        den = min(sum(idf.get(w, 0.0) for w in a), sum(idf.get(w, 0.0) for w in b))
        return inter / den if den > 0 else 0.0

    # single link over ALL same-issuer pairs (order-independent): union-find
    by_issuer: dict[str, list[int]] = {}
    unclustered = 0
    for i, it in enumerate(items):
        if not it.title_tickers:
            unclustered += 1
        for s in it.title_tickers:
            by_issuer.setdefault(s, []).append(i)
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    best: dict[int, tuple] = {}
    for s in sorted(by_issuer):
        idx = by_issuer[s]
        for a_ in range(len(idx)):
            i = idx[a_]
            for b_ in range(a_ + 1, len(idx)):
                j = idx[b_]
                if abs(items[i].first_seen - items[j].first_seen) > gap:
                    continue
                sc = sim(toks[i], toks[j])
                for x, y in ((i, j), (j, i)):
                    if x not in best or sc > best[x][0]:
                        best[x] = (sc, y, s)
                if sc >= thr:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[max(ri, rj)] = min(ri, rj)
    comps: dict[int, list[int]] = {}
    for i, it in enumerate(items):
        if it.title_tickers:
            comps.setdefault(find(i), []).append(i)
    clusters: list[Cluster] = []
    for root in sorted(comps, key=lambda r: (items[comps[r][0]].first_seen, r)):
        c = Cluster(cid=len(clusters))
        for i in comps[root]:
            it = items[i]
            sc, j, via = best.get(i, (None, None, None))
            joined = sc is not None and sc >= thr
            c.joins.append({"item": it.key, "score": round(sc, 4) if sc is not None else None,
                            "nearest": items[j].key if j is not None else None, "via": via,
                            "joined": bool(joined) if len(comps[root]) > 1 else False})
            c.members.append(it)
            c.tokens.append(toks[i])
            c.issuers.update(list(it.title_tickers))
        clusters.append(c)
    return clusters, {"n_items": len(items), "n_unclustered_no_title_issuer": unclustered,
                      "boilerplate_stems_by_source": {k: sorted(v) for k, v in sorted(boiler.items()) if v},
                      "n_clusters": len(clusters), "join_threshold": thr, "join_min_shared_tokens": min_shared,
                      "join_gap_hours": float(C.EVENT_NODES_JOIN_GAP_HOURS)}


def primary_issuer(c: Cluster) -> str:
    first_pos: dict[str, int] = {}
    for k, m in enumerate(c.members):
        for s in m.title_tickers:
            first_pos.setdefault(s, k)
    return sorted(c.issuers, key=lambda s: (-c.issuers[s], first_pos.get(s, 1 << 30), s))[0]


# ─────────────────────────────────────────────── 5. context inputs

def load_size_and_moves(bars_path: Path, now: datetime) -> dict:
    """Per symbol: 63-session median dollar volume percentile, and closes for
    the reaction; only bars whose session closed by `now`."""
    import pandas as pd
    start = (now - timedelta(days=140)).date()
    b = pd.read_parquet(bars_path, columns=["symbol", "date", "close", "volume"],
                        filters=[("date", ">=", pd.Timestamp(start))])
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    closed = []
    for d in sorted(b["date"].dt.date.unique()):
        try:
            cl = DA.session_close_utc(d)
        except Exception:                                              # noqa: BLE001
            cl = datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=21)
        if cl <= now:
            closed.append(d)
    b = b[b["date"].dt.date.isin(set(closed))]
    b["sym"] = b["symbol"].map(DA.norm_ticker)
    b["dv"] = b["close"] * b["volume"]
    nses = int(C.EVENT_NODES_DOLLAR_VOL_SESSIONS)
    last = sorted(closed)[-nses:]
    dv = b[b["date"].dt.date.isin(set(last))].groupby("sym")["dv"].median()
    pct = dv.rank(pct=True)
    closes = {s: g.sort_values("date")[["date", "close"]].values.tolist()
              for s, g in b.groupby("sym")}
    return {"size_pct": pct.to_dict(), "closes": closes,
            "last_session": closed[-1].isoformat() if closed else None,
            "n_symbols": int(b["sym"].nunique())}


def price_reaction(sym: str, first_seen: datetime, ctx: dict) -> dict:
    """Market-adjusted move of the FIRST session that closed after first_seen,
    in units of the trailing sigma. Descriptive; absent bar = no component."""
    import numpy as np
    rows = ctx["closes"].get(sym)
    spy = ctx["closes"].get("SPY")
    if not rows or not spy:
        return {"status": "NO_BARS", "z": None}
    spy_map = {r[0]: r[1] for r in spy}
    after = None
    for k, (d, c) in enumerate(rows):
        try:
            cl = DA.session_close_utc(d.date())
        except Exception:                                              # noqa: BLE001
            cl = d.to_pydatetime().replace(tzinfo=timezone.utc) + timedelta(hours=21)
        if cl > first_seen and k > 0:
            after = k
            break
    if after is None:
        return {"status": "NO_BAR_AFTER_FIRST_SEEN", "z": None,
                "last_session": ctx.get("last_session")}
    rets = []
    for k in range(1, len(rows)):
        d0, c0 = rows[k - 1]
        d1, c1 = rows[k]
        s0, s1 = spy_map.get(d0), spy_map.get(d1)
        if not (c0 and c1 and s0 and s1):
            rets.append(None)
            continue
        rets.append((c1 / c0 - 1) - (s1 / s0 - 1))
    r = rets[after - 1]
    hist = [x for x in rets[max(0, after - 1 - int(C.EVENT_NODES_SIGMA_SESSIONS)):after - 1] if x is not None]
    if r is None or len(hist) < 15:
        return {"status": "THIN_HISTORY", "z": None}
    sd = float(np.std(hist, ddof=1))
    z = r / sd if sd > 0 else None
    return {"status": "OK", "session": rows[after][0].date().isoformat(),
            "excess_return": round(float(r), 5), "sigma": round(sd, 5),
            "z": None if z is None else round(float(z), 3)}


def held_symbols(positions_path: Path) -> set:
    """Symbols only -- no quantity or value is read into the node."""
    snap = json.loads(Path(positions_path).read_text(encoding="utf-8"))
    return {DA.norm_ticker(p.get("symbol")) for p in snap.get("positions") or [] if p.get("symbol")}


def forecasts_for(pred_path: Path, syms: set, now: datetime) -> dict:
    """{sym: [{made_at, observable, probability, horizon_days}]}, streamed, read-only."""
    from backend.services import forecast_ledger as FL
    lo = now - timedelta(days=int(C.EVENT_NODES_FORECAST_LOOKBACK_DAYS))
    out: dict[str, list] = {}
    rx = re.compile(r'"ticker":\s*"([A-Za-z.\-]+)"')
    for line in FL.logical_lines(pred_path):
        m = rx.search(line)
        if not m or DA.norm_ticker(m.group(1)) not in syms:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        made = _utc(row.get("made_at"))
        if made is None or not (lo <= made <= now):
            continue
        out.setdefault(DA.norm_ticker(row.get("ticker")), []).append(
            {"made_at": _iso(made), "observable": row.get("observable"),
             "probability": row.get("probability"), "horizon_days": row.get("horizon_days"),
             "specialist": row.get("specialist")})
    return out


def calendar_dates(calendar_dir: Path, syms: set, now: datetime) -> dict:
    """Upcoming earnings rows for `syms` from the newest stored calendar written
    by `now`, with the calendar's own window (an absent date beyond the window
    is 'not covered', never 'nothing scheduled')."""
    import pandas as pd
    files = sorted(p for p in Path(calendar_dir).glob("calendar_*.parquet")
                   if p.stem[len("calendar_"):] <= now.date().isoformat())
    if not files:
        return {"status": "NO_CALENDAR_BY_NOW", "dates": {}, "window": None}
    f = files[-1]
    rec_p = f.with_name(f.stem + "_receipt.json")
    window = None
    if rec_p.is_file():
        try:
            window = json.loads(rec_p.read_text(encoding="utf-8")).get("window")
        except (OSError, ValueError):
            window = None
    df = pd.read_parquet(f, columns=["symbol", "date", "status", "timing", "source"])
    df["sym"] = df["symbol"].map(DA.norm_ticker)
    df = df[df["sym"].isin(syms)]
    horizon = now.date() + timedelta(days=int(C.EVENT_NODES_NEXT_DATES_HORIZON_DAYS))
    out: dict[str, list] = {}
    for r in df.itertuples(index=False):
        d = pd.Timestamp(r.date).date()
        if now.date() <= d <= horizon:
            out.setdefault(r.sym, []).append({"date": d.isoformat(), "kind": "earnings",
                                              "status": r.status, "timing": r.timing,
                                              "source": f"{f.name}:{r.source}"})
    fomc = []
    try:
        from backend.services import macro_calendar as MC
        ft = MC.fomc_table()
        fomc = [{"date": d, "kind": "fomc", "status": ft.get("status"), "source": ft.get("path")}
                for d in ft.get("dates") or [] if now.date().isoformat() <= d <= horizon.isoformat()]
        fomc_status = ft.get("status")
    except Exception as exc:                                           # noqa: BLE001
        fomc_status = f"UNREADABLE:{type(exc).__name__}"
    return {"status": "OK", "file": f.name, "window": window, "dates": out,
            "macro": fomc, "fomc_status": fomc_status}


def graph_neighbours(graph: Any, sym: str) -> list[dict]:
    """Direct links of company:<sym> (weight, n, sign) and shared sector/theme peers."""
    if graph is None:
        return []
    from backend.services import universe_graph as UG
    nid = UG.company_id(sym)
    if nid not in graph.nodes:
        return []
    k = int(C.EVENT_NODES_GRAPH_TOP_K_PER_TYPE)
    by_type: dict[str, dict[str, dict]] = {}
    for e in graph.edges:
        if e.type in ("sector_member", "theme_member", "country_member"):
            continue
        if e.src == nid:
            other = e.dst
        elif e.dst == nid:
            other = e.src
        else:
            continue
        if not other.startswith("company:"):
            continue
        d = by_type.setdefault(e.type, {})
        cur = d.get(other)
        if cur is None or abs(e.weight) > abs(cur["weight"]):
            d[other] = {"ticker": other.split(":", 1)[1], "link": e.type,
                        "direction": "out" if e.src == nid else "in",
                        "weight": round(float(e.weight), 4), "n": int(e.n),
                        "sign": int(e.sign), "source": "universe_graph"}
    out = []
    for t in sorted(by_type):
        out += sorted(by_type[t].values(), key=lambda r: (-abs(r["weight"]), r["ticker"]))[:k]
    direct = {r["ticker"] for r in out}
    for etype, peers in UG.event_neighbours(graph, nid).items():
        if etype not in ("sector", "theme"):
            continue
        shared = sorted(peers, key=lambda p: (p.split(":", 1)[1] not in direct, p))[:k]
        for p in shared:
            out.append({"ticker": p.split(":", 1)[1], "link": f"shared_{etype}",
                        "weight": None, "n": None, "sign": 0, "source": "universe_graph",
                        "n_peers_of_type": len(peers)})
    return out


# ─────────────────────────────────────────────── 6. the node

def importance(c: Cluster, sym: str, ctx: dict) -> dict:
    w = dict(C.EVENT_NODES_IMPORTANCE_WEIGHTS)
    pubs = {m.publisher for m in c.members}
    regions = set().union(*(m.regions for m in c.members)) if c.members else set()
    first = min(m.first_seen for m in c.members)
    pr = price_reaction(sym, first, ctx["bars"]) if ctx.get("bars") else {"status": "NO_BARS", "z": None}
    comp = {
        "publishers": round(math.log1p(len(pubs)), 4),
        "regions": round(min(len(regions), int(C.EVENT_NODES_REGIONS_CAP)) / float(C.EVENT_NODES_REGIONS_CAP), 4),
        "items": round(math.log1p(len(c.members)), 4),
        "filing": 1.0 if any(m.kind == "filing" for m in c.members) else 0.0,
        "size_rank": round(float(ctx["bars"]["size_pct"].get(sym, 0.0)), 4) if ctx.get("bars") else 0.0,
        "price_reaction": (round(min(abs(pr["z"]), float(C.EVENT_NODES_PRICE_Z_CAP))
                                 / float(C.EVENT_NODES_PRICE_Z_CAP), 4) if pr.get("z") is not None else 0.0),
        "held": 1.0 if sym in ctx.get("held", set()) else 0.0,
        "forecast": 1.0 if ctx.get("forecasts", {}).get(sym) else 0.0,
    }
    contrib = {k: round(w.get(k, 0.0) * v, 4) for k, v in comp.items()}
    return {"importance_0": round(sum(contrib.values()), 4), "components": comp,
            "weights": w, "contributions": contrib,
            "facts": {"n_publishers": len(pubs), "publishers": sorted(pubs),
                      "n_regions": len(regions), "regions": sorted(regions),
                      "n_items": len(c.members), "price_reaction": pr,
                      "forecasts": ctx.get("forecasts", {}).get(sym, [])[:5]}}


def decay(importance_0: float, first_seen: datetime, now: datetime,
          half_life_hours: Optional[float] = None) -> float:
    hl = float(half_life_hours if half_life_hours is not None else C.EVENT_NODES_HALF_LIFE_HOURS)
    age_h = max(0.0, (now - first_seen).total_seconds() / 3600.0)
    return float(importance_0) * 0.5 ** (age_h / hl)


def importance_now(node: dict, now: datetime) -> float:
    """Recomputed on read from importance_0 and the node's own first_seen."""
    return round(decay(node["importance"]["importance_0"], _utc(node["first_seen_utc"]), now,
                       node.get("decay", {}).get("half_life_hours")), 4)


def build_node(c: Cluster, ctx: dict, *, now: datetime, build_id: str) -> dict:
    sym = primary_issuer(c)
    timeline = sorted(c.members, key=lambda m: (m.event_time, m.first_seen, m.key))
    evidence = []
    for m in timeline:
        evidence.append({"source": m.source, "publisher": m.publisher, "kind": m.kind,
                         "region": sorted(m.regions)[0] if len(m.regions) == 1 else None,
                         "regions": sorted(m.regions), "region_basis": m.region_basis,
                         "feeds": sorted(m.feeds),
                         "published_utc": _iso(m.published), "first_seen_utc": _iso(m.first_seen),
                         "clock": "published_utc" if m.published else "first_seen_utc",
                         "url": m.url, "title": m.title, "items_8k": m.items_8k,
                         "title_tickers": m.title_tickers, "item_key": m.key})
    first = min(m.first_seen for m in c.members)
    # connected names: co-mentions (titles then bodies) and graph links
    co: dict[str, dict] = {}
    for idx, m in enumerate(timeline):
        for where, tk in (("title", m.title_tickers), ("body", m.body_tickers)):
            for s, rule in tk.items():
                if s == sym:
                    continue
                r = co.setdefault(s, {"ticker": s, "source": "co_mention", "n_items": 0,
                                      "evidence_index": [], "where": set(), "rules": set()})
                if idx not in r["evidence_index"]:
                    r["evidence_index"].append(idx)
                    r["n_items"] += 1
                r["where"].add(where)
                r["rules"].add(rule)
    comention = sorted(co.values(), key=lambda r: (-r["n_items"], r["ticker"]))[:int(C.EVENT_NODES_MAX_COMENTIONS)]
    for r in comention:
        r["where"], r["rules"] = sorted(r["where"]), sorted(r["rules"])
    graph = graph_neighbours(ctx.get("graph"), sym)
    gset = {g["ticker"] for g in graph}
    for r in comention:
        r["also_graph_linked"] = r["ticker"] in gset
    cal = ctx.get("calendar") or {}
    names = [sym] + [r["ticker"] for r in comention] + sorted(gset)
    nd = []
    seen = set()
    for s in names:
        if s in seen:
            continue
        seen.add(s)
        for d in (cal.get("dates") or {}).get(s, []):
            nd.append({"ticker": s, **d})
    nd.sort(key=lambda d: (d["date"], d["ticker"] != sym, d["ticker"]))
    imp = importance(c, sym, ctx)
    core = {"primary_ticker": sym, "first_item": timeline[0].key if timeline else None,
            "first_seen_utc": _iso(first)}
    event_id = f"ev_{first.date().isoformat()}_{sym}_{_sha(core)[:10]}"
    node = {
        "schema": SCHEMA, "event_id": event_id, "build_id": build_id,
        "primary_issuer_id": f"company:{sym}", "primary_ticker": sym,
        "issuers_in_titles": dict(c.issuers.most_common()),
        "first_seen_utc": _iso(first),
        "first_published_utc": _iso(min((m.published for m in c.members if m.published), default=None)),
        "last_seen_utc": _iso(max(m.first_seen for m in c.members)),
        "built_now_utc": _iso(now),
        "n_evidence": len(evidence), "evidence": evidence,
        "timeline": [{"i": i, "t": e["published_utc"] or e["first_seen_utc"], "clock": e["clock"],
                      "publisher": e["publisher"], "kind": e["kind"], "title": e["title"]}
                     for i, e in enumerate(evidence)],
        "joins": c.joins,
        "connected_names": {"co_mention": comention, "graph": graph},
        "next_dates": nd,
        "next_dates_coverage": {"calendar_file": cal.get("file"), "calendar_window": cal.get("window"),
                                "fomc_status": cal.get("fomc_status"), "macro": cal.get("macro", []),
                                "note": ("a date outside the calendar window is NOT COVERED, "
                                         "never 'nothing scheduled'")},
        "importance": imp,
        "decay": {"rule": "importance_0 * 0.5 ** (age_hours / half_life_hours)",
                  "half_life_hours": float(C.EVENT_NODES_HALF_LIFE_HOURS),
                  "age_from": "first_seen_utc", "computed": "on read, never stored"},
        "open_questions": UNFILLED, "dated_facts": UNFILLED, "stances": UNFILLED,
        "fill_status": UNFILLED,
    }
    node["content_hash"] = _sha({k: v for k, v in node.items()
                                 if k not in ("build_id", "built_now_utc")})
    return node


# ─────────────────────────────────────────────── 7. the store (append-only chain)

def _row_hash(row: dict) -> str:
    return _sha({k: v for k, v in row.items() if k != "row_hash"})


def read_store(path: Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def verify_chain(path: Path) -> dict:
    prev = GENESIS
    rows = read_store(path)
    for i, r in enumerate(rows):
        if r.get("prev_row_hash") != prev:
            return {"ok": False, "n": len(rows), "first_bad": i, "why": "prev_row_hash mismatch"}
        if _row_hash(r) != r.get("row_hash"):
            return {"ok": False, "n": len(rows), "first_bad": i, "why": "row_hash mismatch (row edited)"}
        prev = r["row_hash"]
    return {"ok": True, "n": len(rows), "tip": prev}


def append_nodes(path: Path, nodes: list[dict]) -> dict:
    """Append a new version of each node whose content changed. Refuses on a broken chain."""
    p = Path(path)
    v = verify_chain(p)
    if not v["ok"]:
        raise EventNodesRefused(CHAIN_BROKEN, f"{p}: row {v['first_bad']}: {v['why']}")
    rows = read_store(p)
    latest: dict[str, dict] = {}
    for r in rows:
        if r.get("row_kind") == "node":
            latest[r["event_id"]] = r
    prev = v.get("tip", GENESIS)
    new, same = [], 0
    for n in nodes:
        old = latest.get(n["event_id"])
        if old is not None and old.get("content_hash") == n["content_hash"]:
            same += 1
            continue
        row = {"row_kind": "node", "node_version": (old or {}).get("node_version", 0) + 1,
               "supersedes_row_hash": (old or {}).get("row_hash"), **n, "prev_row_hash": prev}
        row["row_hash"] = _row_hash(row)
        prev = row["row_hash"]
        new.append(row)
    if new:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8", newline="\n") as fh:
            for r in new:
                fh.write(json.dumps(r, sort_keys=True, ensure_ascii=True) + "\n")
    return {"appended": len(new), "unchanged": same, "store": str(p), "tip": prev}


# ─────────────────────────────────────────────── 8. inputs and the build

def default_paths(data_root: Path) -> dict:
    dr = Path(data_root)
    return {"corpus": dr / "news_corpus",
            "filings": dr / "official" / "tables" / "filing_events.jsonl",
            "cik_map": dr / "official" / "company_tickers.json",
            "graph": dr / "universe_graph",
            "calendar": dr / "contest" / "calendar",
            "bars": dr / "prices_2025_26" / "bars.parquet",
            "positions": dr / "pc_book" / "state_latest.json",
            "predictions": dr / "predictions.jsonl",
            "issuers": NE.entities_dir() / "issuers.csv"}


REQUIRED_INPUTS = (("corpus", CORPUS_MISSING, "dir"), ("filings", FILINGS_MISSING, "file"),
                   ("cik_map", CIK_MAP_MISSING, "file"), ("issuers", ISSUERS_MISSING, "file"),
                   ("graph", GRAPH_MISSING, "graph"), ("calendar", CALENDAR_MISSING, "dir"),
                   ("bars", BARS_MISSING, "file"), ("positions", POSITIONS_MISSING, "file"),
                   ("predictions", LEDGER_MISSING, "ledger"))


def check_inputs(paths: dict) -> dict:
    """Refuse, by name, on the first missing input; else each input's size/mtime."""
    out = {}
    for key, code, kind in REQUIRED_INPUTS:
        p = Path(paths[key])
        if kind == "dir":
            ok = p.is_dir()
        elif kind == "graph":
            ok = (p / "latest.json").is_file()
        elif kind == "ledger":
            from backend.services import forecast_ledger as FL
            ok = FL.exists(p)
        else:
            ok = p.is_file()
        if not ok:
            raise EventNodesRefused(code, f"required input `{key}` is missing: {p}")
        out[key] = DA.input_stat(p) if kind != "ledger" else {"path": str(p)}
    return out


def build(data_root: Path, *, since: datetime, now: datetime,
          paths: Optional[dict] = None, load_graph: bool = True) -> dict:
    """Everything in memory; nothing written. Returns {nodes, stats, items...}."""
    if since >= now:
        raise EventNodesRefused(BAD_WINDOW, f"since {since} is not before now {now}")
    P = paths or default_paths(data_root)
    inputs = check_inputs(P)
    tbl = NE.tables(issuers=Path(P["issuers"]))
    cik_map = DA.load_cik_map(Path(P["cik_map"]))
    items, rstats = read_rows(Path(P["corpus"]), Path(P["filings"]), since=since, now=now,
                              cik_map=cik_map, tbl=tbl)
    clusters, cstats = cluster_items(items, tbl)
    graph = None
    graph_status = "NOT_LOADED"
    if load_graph:
        from backend.services import universe_graph as UG
        graph = UG.load_graph(Path(P["graph"]))
        graph_status = f"{graph.meta.get('build_id')} as_of {graph.as_of}"
    syms = set()
    for c in clusters:
        syms.add(primary_issuer(c))
    held = held_symbols(Path(P["positions"]))
    fc = forecasts_for(Path(P["predictions"]), syms, now)
    bars = load_size_and_moves(Path(P["bars"]), now)
    # calendar for primaries + everything they may connect to (cheap: one parquet)
    cal_syms = set(syms)
    for it in items:
        cal_syms.update(it.title_tickers)
        cal_syms.update(it.body_tickers)
    if graph is not None:
        for s in list(syms):
            cal_syms.update(g["ticker"] for g in graph_neighbours(graph, s))
    cal = calendar_dates(Path(P["calendar"]), cal_syms, now)
    ctx = {"graph": graph, "held": held, "forecasts": fc, "bars": bars, "calendar": cal}
    build_id = f"en_{now.strftime('%Y%m%dT%H%M%SZ')}_{_sha([_iso(since), _iso(now)])[:6]}"
    nodes = [build_node(c, ctx, now=now, build_id=build_id) for c in clusters]
    for n in nodes:
        n["importance_now_at_build"] = importance_now(n, now)
    nodes.sort(key=lambda n: (-n["importance"]["importance_0"], n["first_seen_utc"], n["event_id"]))
    annotate_split_and_merge(nodes)
    for r, n in enumerate(nodes, 1):
        n["rank_at_build"] = r
    assert_no_lookahead(nodes, now)
    return {"build_id": build_id, "since": _iso(since), "now": _iso(now), "inputs": inputs,
            "read": rstats, "clustering": cstats, "graph": graph_status,
            "bars_last_session": bars.get("last_session"), "calendar": {k: cal.get(k) for k in
                                                                        ("status", "file", "window", "fomc_status")},
            "n_held_symbols": len(held), "nodes": nodes, "items": items}


def annotate_split_and_merge(nodes: list[dict], k: int = 5) -> None:
    """Make a split or a merge VISIBLE in the node itself: the other nodes whose
    primary issuer is the same (a story may be split across them) and the members
    that joined on the weakest link (a different story may have been merged in).
    Not part of `content_hash`: siblings change when other nodes change."""
    by: dict[str, list[dict]] = {}
    for n in nodes:
        by.setdefault(n["primary_ticker"], []).append(n)
    for n in nodes:
        n["same_issuer_siblings"] = [
            {"event_id": o["event_id"], "n_evidence": o["n_evidence"],
             "first_title": o["timeline"][0]["title"][:120] if o["timeline"] else None}
            for o in by[n["primary_ticker"]] if o is not n]
        title_of = {e["item_key"]: e["title"][:120] for e in n["evidence"]}
        joined = [j for j in n["joins"] if j.get("joined") and j.get("score") is not None]
        n["weakest_joins"] = [{"title": title_of.get(j["item"]), "score": j["score"],
                               "nearest": title_of.get(j.get("nearest"))}
                              for j in sorted(joined, key=lambda j: (j["score"], j["item"]))[:k]]


def assert_no_lookahead(nodes: list[dict], now: datetime) -> None:
    for n in nodes:
        for e in n["evidence"]:
            for k in ("first_seen_utc", "published_utc"):
                t = _utc(e.get(k))
                if t is not None and t > now:
                    raise EventNodesRefused(LOOKAHEAD, f"{n['event_id']}: evidence {k}={e.get(k)} after now")


# ─────────────────────────────────────────────── 9. the LLM fill step (contract)

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_ISO_D = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_MD = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
                 r"(?:,?\s+(20\d\d))?\b", re.IGNORECASE)


def dates_in(text: str, year_hint: int) -> set:
    """ISO dates a text states (YYYY-MM-DD, 'Nov. 17', 'November 17, 2026')."""
    out = set()
    for m in _ISO_D.finditer(text or ""):
        try:
            out.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat())
        except ValueError:
            pass
    for m in _MD.finditer(text or ""):
        mon = _MONTHS.get(m.group(1).lower()[:3])
        try:
            out.add(date(int(m.group(3) or year_hint), mon, int(m.group(2))).isoformat())
        except (TypeError, ValueError):
            pass
    return out


FILL_SYSTEM = (
    "You read news evidence about one market event and return ONLY a JSON object with keys "
    "dated_facts, stances, open_questions. dated_facts: list of {date (YYYY-MM-DD), fact, "
    "evidence_index (int, an index of the evidence list), quote (an exact span copied from that "
    "evidence item that contains the date)}. stances: list of {ticker, stance (up|down|unclear), "
    "evidence_index}. open_questions: list of short strings. Use only the evidence given; cite "
    "the evidence index for every fact and stance; a date not written in the cited item is not "
    "allowed. No prose outside the JSON.")


def evidence_texts(node: dict, items_by_key: dict) -> list[str]:
    """Title + body excerpt per evidence index (memory only, for the prompt and validation)."""
    out = []
    for e in node["evidence"]:
        it = items_by_key.get(e["item_key"])
        body = (it.body if it is not None else "")[:int(C.EVENT_NODES_FILL_BODY_CHARS)]
        out.append(f"{e['title']}\n{body}".strip())
    return out


def fill_prompt(node: dict, texts: list[str]) -> tuple[str, str]:
    """The filing(s) first, then the newest items, up to EVENT_NODES_FILL_MAX_EVIDENCE;
    each keeps its index in the node's evidence list, which is what a reply cites."""
    n = int(C.EVENT_NODES_FILL_MAX_EVIDENCE)
    names: list[str] = []
    for t in ([node["primary_ticker"]] + [r["ticker"] for r in node["connected_names"]["co_mention"]]
              + [g["ticker"] for g in node["connected_names"]["graph"]]):
        if t not in names:
            names.append(t)
    ev = node["evidence"][:len(texts)]
    order = sorted(range(len(ev)), key=lambda i: (ev[i].get("kind") != "filing",
                                                   -(_utc(ev[i].get("published_utc") or ev[i].get("first_seen_utc"))
                                                     or datetime.min.replace(tzinfo=timezone.utc)).timestamp(), i))
    chosen = sorted(order[:n])
    parts = [f"EVENT {node['event_id']} primary {node['primary_ticker']} first seen {node['first_seen_utc']}",
             f"CONNECTED NAMES: {', '.join(names[:30])}",
             f"EVIDENCE ({len(chosen)} of {len(ev)} items; cite the [index]):"]
    for i in chosen:
        e = ev[i]
        parts.append(f"[{i}] {e['publisher']} ({', '.join(e['regions']) or '?'}) "
                     f"{e['published_utc'] or e['first_seen_utc']}\n{texts[i]}")
    return FILL_SYSTEM, "\n\n".join(parts)


def validate_fill(reply: Optional[str], node: dict, texts: list[str]) -> dict:
    """Accept only cited, in-range, date-checked items; count every refusal."""
    if reply is None:
        raise EventFillRefused(FILL_NOT_JSON, "empty reply")
    s = reply.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s)
    try:
        obj = json.loads(s)
    except ValueError as exc:
        raise EventFillRefused(FILL_NOT_JSON, f"reply is not JSON: {exc}") from exc
    if not isinstance(obj, dict) or not all(isinstance(obj.get(k, []), list)
                                            for k in ("dated_facts", "stances", "open_questions")):
        raise EventFillRefused(FILL_BAD_SCHEMA, "reply is not {dated_facts:[], stances:[], open_questions:[]}")
    n = min(len(node["evidence"]), len(texts))
    refused: Counter = Counter()
    facts, stances, qs = [], [], []
    for f in obj.get("dated_facts", []):
        if not isinstance(f, dict):
            refused["fact_not_object"] += 1
            continue
        i = f.get("evidence_index")
        if type(i) is not int or not (0 <= i < n):
            refused["evidence_index_out_of_range"] += 1
            continue
        d = str(f.get("date") or "")[:10]
        e = node["evidence"][i]
        yr = (_utc(e.get("published_utc") or e.get("first_seen_utc")) or datetime.now(timezone.utc)).year
        quote = str(f.get("quote") or "")
        if not quote or quote not in texts[i]:
            refused["quote_not_in_evidence"] += 1
            continue
        if d not in dates_in(texts[i], yr) or d not in dates_in(quote, yr):
            refused["uncited_date"] += 1
            continue
        facts.append({"date": d, "fact": str(f.get("fact") or "")[:300], "evidence_index": i,
                      "quote_span": [texts[i].index(quote), texts[i].index(quote) + len(quote)]})
    allowed = {node["primary_ticker"]} | {r["ticker"] for r in node["connected_names"]["co_mention"]} \
        | {g["ticker"] for g in node["connected_names"]["graph"]}
    for st in obj.get("stances", []):
        if not isinstance(st, dict):
            refused["stance_not_object"] += 1
            continue
        i = st.get("evidence_index")
        if type(i) is not int or not (0 <= i < n):
            refused["evidence_index_out_of_range"] += 1
            continue
        t = DA.norm_ticker(st.get("ticker"))
        if t not in allowed:
            refused["stance_ticker_not_connected"] += 1
            continue
        if st.get("stance") not in ("up", "down", "unclear"):
            refused["stance_not_in_enum"] += 1
            continue
        stances.append({"ticker": t, "stance": st["stance"], "evidence_index": i})
    for q in obj.get("open_questions", []):
        if isinstance(q, str) and q.strip():
            qs.append(q.strip()[:300])
        else:
            refused["question_not_string"] += 1
    offered = len(obj.get("dated_facts", [])) + len(obj.get("stances", []))
    accepted = len(facts) + len(stances)
    return {"schema": FILL_SCHEMA, "dated_facts": facts, "stances": stances, "open_questions": qs,
            "refused": dict(refused), "n_refused": sum(refused.values()),
            "n_offered": offered, "n_accepted": accepted,
            "status": ("REFUSED_" + FILL_NOTHING_ACCEPTED) if offered and not accepted else "FILLED"}


def _deepseek_call(system: str, user: str, max_tokens: int) -> dict:
    from backend.services import llm_analyzer as LA
    return LA.call_named(LA.SOLE_PROVISIONED_PROVIDER, system, user,
                         purpose=C.EVENT_NODES_FILL_PURPOSE, max_tokens=max_tokens)


def fill_event(node: dict, texts: list[str], *, call: Optional[Callable[[str, str, int], dict]] = None,
               max_tokens: Optional[int] = None) -> dict:
    """One capped DeepSeek call. A budget refusal or provider failure RAISES."""
    mt = int(max_tokens or C.EVENT_NODES_FILL_MAX_TOKENS)
    system, user = fill_prompt(node, texts)
    res = (call or _deepseek_call)(system, user, mt)
    status = str(res.get("status") or "")
    if status == "BUDGET_REFUSED":
        raise EventFillRefused(FILL_BUDGET_REFUSED, str(res.get("error") or "provider_budget refused"))
    if not res.get("ok"):
        raise EventFillRefused(FILL_PROVIDER_FAILED, f"status={status} error={res.get('error')}")
    out = validate_fill(res.get("text"), node, texts)
    out.update({"event_id": node["event_id"], "node_content_hash": node["content_hash"],
                "provider": res.get("provider"), "served_model": res.get("served_model"),
                "cost_usd": res.get("cost_usd"), "tokens_in": res.get("tokens_in"),
                "tokens_out": res.get("tokens_out")})
    return out


def dry_run_cost(node: dict, texts: list[str], *, max_tokens: Optional[int] = None) -> dict:
    """Prompt size, token estimate and projected cost; no call is made."""
    from backend.services import provider_budget as PB
    mt = int(max_tokens or C.EVENT_NODES_FILL_MAX_TOKENS)
    system, user = fill_prompt(node, texts)
    q = PB.quote(system, user, mt)
    price = C.LLM_PRICE_PER_MTOK[C.EVENT_NODES_FILL_PRICE_MODEL]
    est_in = math.ceil(len(system + user) / 4.0)
    projected = (est_in * price["in"] + mt * price["out"]) / 1e6
    return {"event_id": node["event_id"], "prompt_chars": len(system) + len(user),
            "n_evidence_in_prompt": min(len(texts), int(C.EVENT_NODES_FILL_MAX_EVIDENCE)),
            "est_tokens_in": est_in, "max_tokens_out": mt,
            "projected_usd_at_max_output": round(projected, 6),
            "price_model": C.EVENT_NODES_FILL_PRICE_MODEL,
            "reservation_bound_usd": round(q["reserved_units"] / PB.SCALE, 6),
            "system": system, "user": user}


def append_fill(path: Path, fill: dict) -> dict:
    """A fill is its own chained row; the node row it fills is never rewritten."""
    p = Path(path)
    v = verify_chain(p)
    if not v["ok"]:
        raise EventNodesRefused(CHAIN_BROKEN, f"{p}: row {v['first_bad']}: {v['why']}")
    row = {"row_kind": "fill", **fill, "prev_row_hash": v.get("tip", GENESIS)}
    row["row_hash"] = _row_hash(row)
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
    return {"appended": 1, "tip": row["row_hash"]}
