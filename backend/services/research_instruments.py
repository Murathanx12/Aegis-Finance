"""Keyless, $0 academic-citation instruments for the research-intake "academic" lane.

WHY (Q12, 2026-10-07; register and decision table in `docs/research_notes/
2026-10-07/research_instruments_2026-10-07.md`)
=====================================================================
A research-intake card (`docs/research_intake/cards/<slug>.md`, routine in
`docs/research_intake/README.md`) names open literature questions it could
not close by hand -- a `## Needs evidence` list. This module answers them
with the three instruments measured $0, keyless and working the same day
(OpenAlex, CrossRef, NBER new-working-papers RSS), plus two instruments that
exist in the register but REFUSE without an owner-declared key/opt-in
(Semantic Scholar, arXiv): both were measured HTTP 429 on 2 of 2 tries via two
independent fetch paths, so calling them keyless by default would be noise,
not evidence.

    python -m scripts.research_lane --card <slug>   # run the lane for ONE card
    python -m scripts.research_lane --list          # which cards qualify today
    python -m scripts.research_lane --due           # weekly caller's own pick

NOTHING IS EVER WRITTEN INTO THE CARD ITSELF
=============================================
A card is a research note (`docs/research_intake/README.md`), not a trial; the
lane writes a per-card EVIDENCE file (`docs/research_intake/evidence/
<slug>_<run_id>.json`) and a yield receipt (`research_instruments/
probe_<run_id>.json`, the path and schema this module implements verbatim
from the 2026-10-07 note). Promoting a citation into the card is a human/
Sonnet decision, made by reading the evidence file, never automatic.

THE DECISION TABLE (note §3.2-3.3)
===================================
Default tier (always $0, keyless, proven working): OpenAlex, then CrossRef --
`RESEARCH_INSTRUMENTS_DEFAULT_BUDGET` queries per question (default 2).
Escalation to the extended tier (Semantic Scholar / arXiv / NBER RSS) fires
only when the default tier's coverage of the card's OWN seed citations stays
below `RESEARCH_INSTRUMENTS_STOP_COVERAGE`, capped at
`RESEARCH_INSTRUMENTS_EXTENDED_CAP` more queries. The instrument ORDER depends
on the question's topic class (classical asset-pricing journal mechanism vs.
quant/ML preprint) -- `INSTRUMENT_ORDER_BY_TOPIC`. A question stops escalating
as soon as it holds `RESEARCH_INSTRUMENTS_MIN_VERIFIED` DOI-verified citations,
OR two consecutive instruments return nothing new, OR the cap is hit --
whichever fires first, and the receipt records WHICH.

A PAID INSTRUMENT IS NEVER REACHED BY THIS MODULE.
Perplexity, Consensus beyond its free quota, Brave, Bigdata.com, and any
patent API needing a signup are not implemented here at all -- they are an
owner decision (a payment, a named signup, or an identity-verification step),
never an automatic escalation past the free tier (note §3.3).
"""
from __future__ import annotations

import json
import re
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote, quote_plus

from backend import config as _config

REPO = Path(__file__).resolve().parents[2]
CARDS_DIR = REPO / "docs" / "research_intake" / "cards"
EVIDENCE_DIR = REPO / "docs" / "research_intake" / "evidence"

#: the three card verdicts this lane treats as "still has open questions"
QUALIFYING_VERDICTS: tuple[str, ...] = ("NEEDS_DATA", "READY_TO_CELL", "NOT_A_HYPOTHESIS_YET")
_ALL_VERDICT_TOKENS: tuple[str, ...] = QUALIFYING_VERDICTS + ("ALREADY_CLOSED",)

INSTRUMENTS_DEFAULT: tuple[str, ...] = ("openalex", "crossref")
INSTRUMENTS_EXTENDED: tuple[str, ...] = ("semantic_scholar", "arxiv", "nber_rss")
INSTRUMENTS_ALL: tuple[str, ...] = INSTRUMENTS_DEFAULT + INSTRUMENTS_EXTENDED

TOPIC_CLASSES: tuple[str, ...] = ("classical_asset_pricing", "quant_ml_preprint")
INSTRUMENT_ORDER_BY_TOPIC: dict[str, tuple[str, ...]] = {
    "classical_asset_pricing": ("openalex", "crossref", "semantic_scholar", "nber_rss"),
    "quant_ml_preprint": ("arxiv", "openalex", "semantic_scholar"),
}
_QUANT_ML_KEYWORDS: tuple[str, ...] = (
    "neural", "llm", "large language model", "transformer", "machine learning",
    "deep learning", "reinforcement learning", "gradient boosting", "lightgbm",
    "random forest", "embedding")


def _cfg(name: str, default: Any) -> Any:
    return getattr(_config, name, default)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InstrumentKeyRequired(RuntimeError):
    """Raised by a keyed-or-rate-limited instrument (Semantic Scholar, arXiv)
    with no declared key / owner opt-in: KEY_REQUIRED_OR_RATE_LIMITED.

    Measured 2026-10-07 (`docs/research_notes/2026-10-07/
    research_instruments_2026-10-07.md`): both instruments answered HTTP 429
    on 2 of 2 tries, via two independent fetch paths. A keyless, unreliable
    call is not evidence; this is the missing-input guard the research-intake
    routine's own discipline asks every other collector to carry."""


# ═══════════════════════════════ files (plain) ═══════════════════════════════

def opt_dir(opt: Path | None = None) -> Path:
    return Path(opt or _config.OPTIMUS_LEDGER_DIR)


def academic_ledger_path(opt: Path | None = None) -> Path:
    return opt_dir(opt) / "research_instruments" / "academic_ledger.jsonl"


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


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")


def last_probe_utc(opt: Path | None = None) -> Optional[str]:
    """The newest `t` across every card this lane has ever probed, or None."""
    ts = [str(r.get("t")) for r in _read_jsonl(academic_ledger_path(opt)) if r.get("t")]
    return max(ts) if ts else None


# ═══════════════════════════════ HTTP (one door) ═════════════════════════════

def _http_get(url: str, *, timeout: float | None = None,
             headers: dict | None = None) -> bytes:
    """The single network door for this module. Every test mocks THIS (or the
    higher-level `http_get=` parameter each fetcher takes), never a socket."""
    import urllib.request
    t = float(timeout if timeout is not None else
             _cfg("RESEARCH_INSTRUMENTS_HTTP_TIMEOUT_S", 20.0))
    req = urllib.request.Request(url, headers={
        "User-Agent": "AegisFinance-ResearchInstruments/1.0 (academic lane; $0 keyless; "
                     "contact only if RESEARCH_INSTRUMENTS_MAILTO is declared)",
        **(headers or {})})
    with urllib.request.urlopen(req, timeout=t) as fh:          # noqa: S310
        return fh.read()


def polite_mailto() -> Optional[str]:
    """The OpenAlex/CrossRef "polite pool" contact param -- an OWNER decision,
    never defaulted to a personal address (CLAUDE.md: never hardcode; and this
    value is sent to an external service on every call)."""
    v = _cfg("RESEARCH_INSTRUMENTS_MAILTO", None)
    return str(v).strip() if v and str(v).strip() else None


# ═══════════════════════════════ URL builders (pure) ═════════════════════════

OPENALEX_URL = "https://api.openalex.org/works?search={q}&per_page={n}"
CROSSREF_URL = "https://api.crossref.org/works?query.bibliographic={q}&rows={n}"
NBER_RSS_URL = "https://www.nber.org/rss/new.xml"
SEMANTIC_SCHOLAR_URL = ("https://api.semanticscholar.org/graph/v1/paper/search?query={q}"
                        "&limit={n}&fields=title,year,authors,venue,abstract,externalIds,"
                        "citationCount")
ARXIV_URL = "http://export.arxiv.org/api/query?search_query=all:{q}&max_results={n}"


def openalex_url(query: str, *, per_page: int = 5, mailto: str | None = None) -> str:
    u = OPENALEX_URL.format(q=quote_plus(query), n=per_page)
    return f"{u}&mailto={quote_plus(mailto)}" if mailto else u


def crossref_url(query: str, *, rows: int = 5, mailto: str | None = None) -> str:
    u = CROSSREF_URL.format(q=quote_plus(query), n=rows)
    return f"{u}&mailto={quote_plus(mailto)}" if mailto else u


def semantic_scholar_url(query: str, *, limit: int = 5) -> str:
    return SEMANTIC_SCHOLAR_URL.format(q=quote_plus(query), n=limit)


def arxiv_url(query: str, *, max_results: int = 5) -> str:
    return ARXIV_URL.format(q=quote(query), n=max_results)


# ═══════════════════════════ the normalised citation row (pure) ══════════════
#
# title, authors, year, venue, DOI/URL, abstract (if given), cited_by_count,
# source instrument, fetched_utc -- the exact fields Q12 asks for. No module
# here ever stores full text.

def _clean_doi(doi: str | None) -> Optional[str]:
    if not doi:
        return None
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", str(doi).strip(), flags=re.I)
    return d.lower() or None


def _row(*, title: Any, authors: list, year: Any, venue: Any, doi: Any, url: Any,
        abstract: Any, cited_by_count: Any, source: str, fetched_utc: str) -> dict:
    return {"title": title, "authors": [a for a in (authors or []) if a], "year": year,
            "venue": venue, "doi": _clean_doi(doi), "url": url,
            "abstract": (str(abstract)[:2000] if abstract else None),
            "cited_by_count": cited_by_count, "source": source, "fetched_utc": fetched_utc}


def _abstract_from_inverted_index(idx: dict | None) -> Optional[str]:
    """PURE. OpenAlex serves the abstract as an inverted index (word ->
    [positions]) rather than running text, to dodge publisher copyright on the
    assembled abstract; rebuild the word order from the positions."""
    if not idx:
        return None
    slots: dict[int, str] = {}
    for word, positions in idx.items():
        for p in positions or []:
            slots[int(p)] = word
    return " ".join(slots[i] for i in sorted(slots)) if slots else None


def normalize_openalex(raw: dict, *, fetched_utc: str) -> list[dict]:
    """PURE. OpenAlex `/works` JSON -> normalised citation rows."""
    out = []
    for r in (raw or {}).get("results") or []:
        loc = r.get("primary_location") or {}
        src = loc.get("source") or {} if isinstance(loc, dict) else {}
        out.append(_row(
            title=r.get("display_name") or r.get("title"),
            authors=[(a.get("author") or {}).get("display_name")
                    for a in r.get("authorships") or [] if isinstance(a, dict)],
            year=r.get("publication_year"), venue=src.get("display_name") if isinstance(src, dict) else None,
            doi=r.get("doi"), url=loc.get("landing_page_url") or r.get("id"),
            abstract=_abstract_from_inverted_index(r.get("abstract_inverted_index")),
            cited_by_count=r.get("cited_by_count"), source="openalex", fetched_utc=fetched_utc))
    return out


def normalize_crossref(raw: dict, *, fetched_utc: str) -> list[dict]:
    """PURE. CrossRef `/works` JSON -> normalised citation rows."""
    out = []
    for it in (((raw or {}).get("message") or {}).get("items")) or []:
        title = (it.get("title") or [None])[0]
        authors = [f"{a.get('given', '')} {a.get('family', '')}".strip()
                  for a in it.get("author") or [] if isinstance(a, dict)]
        year = None
        for k in ("published-print", "published", "issued"):
            dp = ((it.get(k) or {}).get("date-parts") or [[None]])
            if dp and dp[0] and dp[0][0]:
                year = dp[0][0]
                break
        out.append(_row(
            title=title, authors=authors, year=year,
            venue=(it.get("container-title") or [None])[0], doi=it.get("DOI"), url=it.get("URL"),
            abstract=it.get("abstract"), cited_by_count=it.get("is-referenced-by-count"),
            source="crossref", fetched_utc=fetched_utc))
    return out


_NBER_TITLE_RE = re.compile(r"^([^:]{3,120}):\s*(.+)$")


def normalize_nber_rss(raw: bytes, *, fetched_utc: str) -> list[dict]:
    """PURE. NBER's `rss/new.xml` (new working papers) -> normalised rows.
    Authors are embedded in the title string ("Author A, Author B: Title");
    there is no separate date field (note §1)."""
    out = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title_full = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip() or None
        desc = (it.findtext("description") or "").strip() or None
        m = _NBER_TITLE_RE.match(title_full)
        if m and "," in m.group(1):
            authors = [a.strip() for a in m.group(1).split(",") if a.strip()]
            title = m.group(2).strip()
        else:
            authors, title = [], title_full
        out.append(_row(title=title or title_full, authors=authors, year=None,
                        venue="NBER Working Paper", doi=None, url=link, abstract=desc,
                        cited_by_count=None, source="nber_rss", fetched_utc=fetched_utc))
    return out


def normalize_semantic_scholar(raw: dict, *, fetched_utc: str) -> list[dict]:
    """PURE. Semantic Scholar Graph API `/paper/search` JSON -> rows."""
    out = []
    for p in (raw or {}).get("data") or []:
        ext = p.get("externalIds") or {}
        out.append(_row(
            title=p.get("title"),
            authors=[a.get("name") for a in p.get("authors") or [] if isinstance(a, dict)],
            year=p.get("year"), venue=p.get("venue"), doi=ext.get("DOI"), url=p.get("url"),
            abstract=p.get("abstract"), cited_by_count=p.get("citationCount"),
            source="semantic_scholar", fetched_utc=fetched_utc))
    return out


_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom"}


def normalize_arxiv(raw: bytes, *, fetched_utc: str) -> list[dict]:
    """PURE. arXiv Atom feed -> rows. No DOI (arXiv preprints rarely carry
    one); the arXiv id is kept in `url`."""
    out = []
    root = ET.fromstring(raw)
    for e in root.findall("a:entry", _ARXIV_NS):
        title = " ".join((e.findtext("a:title", default="", namespaces=_ARXIV_NS) or "").split())
        authors = [" ".join((a.findtext("a:name", default="", namespaces=_ARXIV_NS) or "").split())
                  for a in e.findall("a:author", _ARXIV_NS)]
        published = e.findtext("a:published", default="", namespaces=_ARXIV_NS) or ""
        year = int(published[:4]) if published[:4].isdigit() else None
        link = next((ln.get("href") for ln in e.findall("a:link", _ARXIV_NS)
                    if ln.get("type") == "text/html"), None) \
            or e.findtext("a:id", default=None, namespaces=_ARXIV_NS)
        abstract = " ".join((e.findtext("a:summary", default="", namespaces=_ARXIV_NS) or "").split())
        out.append(_row(title=title, authors=authors, year=year, venue="arXiv", doi=None,
                        url=link, abstract=abstract or None, cited_by_count=None,
                        source="arxiv", fetched_utc=fetched_utc))
    return out


# ═══════════════════════════════ fetchers ═════════════════════════════════

def _fetch(instrument: str, url: str, *, http_get: Callable[[str], bytes],
          parse_fn: Callable[..., list[dict]], fetched_utc: str, json_body: bool = True) -> dict:
    """One HTTP call -> {instrument, status, http_status, error, latency_s,
    rows, query_url, cost_usd}. A hard failure (429, timeout, DNS) reports
    `latency_s: None` -- never 0, never omitted (note §2.2: "a tool that
    cannot be reached is not 'fast'"). `json_body`: the raw bytes are JSON-
    decoded before `parse_fn` sees them (OpenAlex/CrossRef/Semantic Scholar);
    False passes the raw bytes straight through (NBER RSS/arXiv's own XML
    parsers take bytes directly)."""
    t0 = time.monotonic()
    try:
        raw = http_get(url)
    except Exception as exc:                                      # noqa: BLE001
        return {"instrument": instrument, "status": "ERROR",
               "http_status": getattr(exc, "code", None),
               "error": f"{type(exc).__name__}: {exc}"[:300], "latency_s": None, "rows": []}
    latency = round(time.monotonic() - t0, 3)
    try:
        body = json.loads(raw) if json_body else raw
        rows = parse_fn(body, fetched_utc=fetched_utc)
    except Exception as exc:                                      # noqa: BLE001
        return {"instrument": instrument, "status": "ERROR", "http_status": 200,
               "error": f"parse failed: {type(exc).__name__}: {exc}"[:300],
               "latency_s": latency, "rows": []}
    return {"instrument": instrument, "status": "OK", "http_status": 200, "error": None,
           "latency_s": latency, "rows": rows}


def fetch_openalex(query: str, *, http_get: Callable[[str], bytes] | None = None,
                   mailto: str | None = None, now: datetime | None = None,
                   per_page: int = 5) -> dict:
    now = now or _now()
    mailto = mailto if mailto is not None else polite_mailto()
    url = openalex_url(query, per_page=per_page, mailto=mailto)
    r = _fetch("openalex", url, http_get=(http_get or _http_get), parse_fn=normalize_openalex,
              fetched_utc=now.isoformat(timespec="seconds"))
    return {**r, "query_url": url, "cost_usd": 0.0}


def fetch_crossref(query: str, *, http_get: Callable[[str], bytes] | None = None,
                   mailto: str | None = None, now: datetime | None = None,
                   rows: int = 5) -> dict:
    now = now or _now()
    mailto = mailto if mailto is not None else polite_mailto()
    url = crossref_url(query, rows=rows, mailto=mailto)
    r = _fetch("crossref", url, http_get=(http_get or _http_get), parse_fn=normalize_crossref,
              fetched_utc=now.isoformat(timespec="seconds"))
    return {**r, "query_url": url, "cost_usd": 0.0}


def fetch_nber_rss(query: str | None = None, *, http_get: Callable[[str], bytes] | None = None,
                   now: datetime | None = None) -> dict:
    """NBER publishes a NEW-papers feed, not a search endpoint: fetch it once
    and keep only items whose title/abstract shares a word (>=4 letters) with
    `query`, when one is given."""
    now = now or _now()
    r = _fetch("nber_rss", NBER_RSS_URL, http_get=(http_get or _http_get),
              parse_fn=normalize_nber_rss, fetched_utc=now.isoformat(timespec="seconds"),
              json_body=False)
    r = {**r, "query_url": NBER_RSS_URL, "cost_usd": 0.0}
    if query and r.get("rows"):
        kws = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", query)}
        def hit(row: dict) -> bool:
            text = f"{row.get('title') or ''} {row.get('abstract') or ''}".lower()
            return any(k in text for k in kws)
        r["rows"] = [row for row in r["rows"] if hit(row)]
    return r


def fetch_semantic_scholar(query: str, *, key: str | None = None,
                           http_get: Callable[[str], bytes] | None = None,
                           now: datetime | None = None, limit: int = 5) -> dict:
    key = key if key is not None else _cfg("RESEARCH_INSTRUMENTS_SEMANTIC_SCHOLAR_KEY", None)
    if not key:
        raise InstrumentKeyRequired(
            "semantic_scholar: KEY_REQUIRED_OR_RATE_LIMITED -- no "
            "RESEARCH_INSTRUMENTS_SEMANTIC_SCHOLAR_KEY declared; measured unreliable keyless "
            "(HTTP 429 on 2 of 2 tries via 2 independent fetch paths, 2026-10-07). Declaring a "
            "free key is a cheap owner upgrade, not required to use the default tier.")
    now = now or _now()
    url = semantic_scholar_url(query, limit=limit)

    def _get(u: str) -> bytes:
        if http_get is not None:
            return http_get(u)
        import urllib.request
        req = urllib.request.Request(u, headers={"x-api-key": key})
        with urllib.request.urlopen(          # noqa: S310
                req, timeout=float(_cfg("RESEARCH_INSTRUMENTS_HTTP_TIMEOUT_S", 20.0))) as fh:
            return fh.read()

    r = _fetch("semantic_scholar", url, http_get=_get, parse_fn=normalize_semantic_scholar,
              fetched_utc=now.isoformat(timespec="seconds"))
    return {**r, "query_url": url, "cost_usd": 0.0}


def fetch_arxiv(query: str, *, enabled: bool | None = None,
                http_get: Callable[[str], bytes] | None = None,
                now: datetime | None = None, max_results: int = 5) -> dict:
    enabled = enabled if enabled is not None else bool(_cfg("RESEARCH_INSTRUMENTS_ARXIV_ENABLED", False))
    if not enabled:
        raise InstrumentKeyRequired(
            "arxiv: KEY_REQUIRED_OR_RATE_LIMITED -- RESEARCH_INSTRUMENTS_ARXIV_ENABLED is False "
            "(measured HTTP 429 on 2 of 2 tries, 2026-10-07; real coverage is the quant/ML "
            "preprint class only, not classical asset-pricing journal mechanisms). Owner "
            "opt-in required before this lane calls it automatically.")
    now = now or _now()
    url = arxiv_url(query, max_results=max_results)
    r = _fetch("arxiv", url, http_get=(http_get or _http_get), parse_fn=normalize_arxiv,
              fetched_utc=now.isoformat(timespec="seconds"), json_body=False)
    return {**r, "query_url": url, "cost_usd": 0.0}


def run_instrument(name: str, query: str, *, http_get: Callable[[str], bytes] | None = None,
                   now: datetime | None = None) -> dict:
    fns: dict[str, Callable[..., dict]] = {
        "openalex": fetch_openalex, "crossref": fetch_crossref, "nber_rss": fetch_nber_rss,
        "semantic_scholar": fetch_semantic_scholar, "arxiv": fetch_arxiv}
    fn = fns.get(name)
    if fn is None:
        raise ValueError(f"unknown instrument: {name!r} (not in {INSTRUMENTS_ALL})")
    return fn(query, http_get=http_get, now=now)


def _try_instrument(name: str, query: str, *, http_get: Callable[[str], bytes] | None = None,
                    now: datetime | None = None) -> dict:
    """Never raises: a gated instrument's refusal becomes one more named-zero
    row instead of stopping the whole probe."""
    try:
        r = run_instrument(name, query, http_get=http_get, now=now)
    except InstrumentKeyRequired as exc:
        return {"instrument": name, "status": "REFUSED", "http_status": None,
               "error": str(exc), "latency_s": None, "rows": [], "query_url": None,
               "cost_usd": 0.0, "zero_kind": "KEY_REQUIRED_OR_RATE_LIMITED"}
    r.setdefault("zero_kind", None if r.get("rows") else
                ("TOOL_FIRED_BUT_UNAVAILABLE" if r.get("status") == "ERROR"
                 else "QUERIES_RAN_NO_CITATIONS"))
    return r


# ═════════════════════════ topic class + the decision table ══════════════════

def classify_topic_class(text: str) -> str:
    """PURE. A question is `quant_ml_preprint` if it names an ML/LLM
    construction, else the default `classical_asset_pricing`."""
    t = (text or "").lower()
    return "quant_ml_preprint" if any(k in t for k in _QUANT_ML_KEYWORDS) else "classical_asset_pricing"


# ═══════════════════════════════ card parsing (pure) ══════════════════════════

def _section(card_text: str, heading: str) -> Optional[str]:
    m = re.search(rf"^{re.escape(heading)}\s*$(.*?)(?=^## |\Z)", card_text, re.M | re.S)
    return m.group(1) if m else None


_VERDICT_TOKEN_RE = re.compile(r"\*\*([A-Z_]+)\.?\*\*")


def card_verdicts(card_text: str) -> list[str]:
    """PURE. Every bold verdict token inside the card's `## Verdict` section,
    in order of first appearance (a card may carry a split verdict)."""
    body = _section(card_text, "## Verdict") or card_text
    seen: list[str] = []
    for t in _VERDICT_TOKEN_RE.findall(body):
        if t in _ALL_VERDICT_TOKENS and t not in seen:
            seen.append(t)
    return seen


def card_qualifies(card_text: str) -> bool:
    """A card is an academic-lane seed if ANY of its verdict tokens is
    NEEDS_DATA / READY_TO_CELL / NOT_A_HYPOTHESIS_YET -- a split verdict (one
    arm ALREADY_CLOSED, another READY_TO_CELL) still qualifies."""
    return any(v in QUALIFYING_VERDICTS for v in card_verdicts(card_text))


def card_needs_evidence(card_text: str) -> list[str]:
    """PURE. Bullet lines under the card's optional `## Needs evidence`
    section -- the open literature questions this lane answers."""
    body = _section(card_text, "## Needs evidence")
    if not body:
        return []
    out = []
    for ln in body.splitlines():
        ln = ln.strip()
        if ln.startswith(("-", "*")):
            q = ln.lstrip("-*").strip()
            if q:
                out.append(q)
    return out


_DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+")
_TITLE_RE = re.compile(r'"([^"]{8,300})"')


def card_seed_citations(card_text: str) -> list[dict]:
    """PURE. (doi, title) the card already names in its own `## Citation`
    line and `## Known failure modes...` section (McLean & Pontiff-style
    standing references) -- the existing citation set a novelty check is
    measured against (note §2.1-2.2)."""
    out = []
    for heading in ("## Citation", "## Known failure modes and post-publication decay"):
        body = _section(card_text, heading)
        if not body:
            continue
        dois = [d.rstrip(".,;)") for d in _DOI_RE.findall(body)]
        titles = _TITLE_RE.findall(body)
        if dois or titles:
            out.append({"doi": _clean_doi(dois[0]) if dois else None,
                       "title": titles[0] if titles else None, "section": heading})
    return out


def _norm_title(t: str | None) -> str:
    t = re.sub(r"\s+", " ", (t or "").lower())
    return re.sub(r"[^a-z0-9 ]", "", t).strip()


def is_novel(row: dict, seed_citations: list[dict]) -> bool:
    """PURE. A found row is novel if it matches NEITHER a seed DOI NOR a seed
    title (normalised, substring-tolerant: a card's prose sometimes truncates
    a title)."""
    rdoi, rtitle = row.get("doi"), _norm_title(row.get("title"))
    for s in seed_citations:
        if rdoi and s.get("doi") and rdoi == s["doi"]:
            return False
        st = _norm_title(s.get("title"))
        if rtitle and st and len(st) > 10 and (rtitle in st or st in rtitle):
            return False
    return True


def verified_doi(row: dict) -> bool:
    """A citation whose DOI is present is DOI-verified (resolvable); one with
    no DOI (an NBER/arXiv preprint, mostly) is not, and the evidence file
    tags each row with this flag rather than silently treating both alike."""
    return bool(row.get("doi"))


# ═══════════════════════════════ one question ═══════════════════════════════

def probe_question(question: str, *, fetch_fn: Callable[[str, str], dict],
                   topic_class: str | None = None, seed_citations: list[dict] | None = None,
                   default_budget: int | None = None, extended_cap: int | None = None,
                   stop_coverage: float | None = None, min_verified: int | None = None) -> dict:
    """The decision table for ONE needs-evidence question (note §3.2-3.3).
    `fetch_fn(instrument_name, query_text) -> result dict` is the only side
    effect; everything else here is pure, which is what makes this testable
    without a socket."""
    seed_citations = seed_citations or []
    topic_class = topic_class or classify_topic_class(question)
    order = INSTRUMENT_ORDER_BY_TOPIC.get(topic_class,
                                          INSTRUMENT_ORDER_BY_TOPIC["classical_asset_pricing"])
    default_budget = int(default_budget if default_budget is not None else
                         _cfg("RESEARCH_INSTRUMENTS_DEFAULT_BUDGET", 2))
    extended_cap = int(extended_cap if extended_cap is not None else
                       _cfg("RESEARCH_INSTRUMENTS_EXTENDED_CAP", 3))
    stop_coverage = float(stop_coverage if stop_coverage is not None else
                          _cfg("RESEARCH_INSTRUMENTS_STOP_COVERAGE", 0.8))
    min_verified = int(min_verified if min_verified is not None else
                       _cfg("RESEARCH_INSTRUMENTS_MIN_VERIFIED", 1))
    seed_keys = {s.get("doi") or s.get("title") for s in seed_citations
                if s.get("doi") or s.get("title")}
    seed_n = len(seed_keys)
    found_seed: set = set()
    n_verified = 0
    attempts: list[dict] = []
    zero_streak = 0
    stop_reason: Optional[str] = None

    def coverage() -> Optional[float]:
        return (len(found_seed) / seed_n) if seed_n else None

    def run_one(name: str) -> dict:
        nonlocal n_verified
        r = dict(fetch_fn(name, question))
        rows = r.get("rows") or []
        r["found_dois"] = [row.get("doi") for row in rows if row.get("doi")]
        r["novel_rows"] = [row for row in rows if is_novel(row, seed_citations)]
        r["novel_dois"] = [row.get("doi") for row in r["novel_rows"] if row.get("doi")]
        r["verified_count"] = sum(1 for row in rows if verified_doi(row))
        n_verified += r["verified_count"]
        for row in rows:
            rd, rt = row.get("doi"), _norm_title(row.get("title"))
            for s in seed_citations:
                sd, st = s.get("doi"), _norm_title(s.get("title"))
                if (rd and sd and rd == sd) or (rt and st and len(st) > 10 and
                                                (rt in st or st in rt)):
                    found_seed.add(sd or st)
        return r

    def tier(names: list[str]) -> bool:
        """Run one tier's instruments; True = stop condition fired inside it."""
        nonlocal zero_streak, stop_reason
        for name in names:
            r = run_one(name)
            attempts.append(r)
            zero_streak = 0 if r.get("rows") else zero_streak + 1
            if n_verified >= min_verified and (coverage() is None or coverage() >= 1.0):
                stop_reason = "min_verified_and_full_coverage"
                return True
            if zero_streak >= 2:
                stop_reason = "two_consecutive_instruments_zero_new"
                return True
        return False

    default_tier = [i for i in order if i in INSTRUMENTS_DEFAULT][:default_budget]
    stopped = tier(default_tier)
    if not stopped:
        needs_escalation = n_verified < min_verified or (coverage() is not None and
                                                         coverage() < stop_coverage)
        if needs_escalation:
            extended_tier = [i for i in order if i in INSTRUMENTS_EXTENDED][:extended_cap]
            if not extended_tier:
                stop_reason = "no_extended_tier_for_topic_class"
            elif not tier(extended_tier):
                stop_reason = "extended_tier_cap_reached"
        else:
            stop_reason = "default_tier_sufficient"
    return {"question": question, "topic_class": topic_class, "attempts": attempts,
           "coverage": coverage(), "n_verified": n_verified,
           "found_seed": sorted(str(x) for x in found_seed), "stop_reason": stop_reason}


# ═══════════════════════════════ one card (the lane) ═════════════════════════

def _aggregate_by_instrument(q_results: list[dict]) -> dict:
    agg: dict[str, dict] = {}
    for q in q_results:
        for a in q["attempts"]:
            name = a["instrument"]
            d = agg.setdefault(name, {"queries": 0, "rows": 0, "verified": 0, "novel": 0,
                                      "latency_s": [], "statuses": Counter(), "zero_kinds": Counter()})
            d["queries"] += 1
            d["rows"] += len(a.get("rows") or [])
            d["verified"] += int(a.get("verified_count") or 0)
            d["novel"] += len(a.get("novel_rows") or [])
            d["statuses"][a.get("status")] += 1
            if a.get("zero_kind"):
                d["zero_kinds"][a["zero_kind"]] += 1
            if a.get("latency_s") is not None:
                d["latency_s"].append(a["latency_s"])
    out = {}
    for name in INSTRUMENTS_ALL:
        d = agg.get(name)
        if d is None:
            out[name] = {"queries": 0, "rows_returned": 0, "verified_citations": 0,
                        "novel_citations": 0, "avg_latency_s": None, "statuses": {},
                        "named_zeros": {"NOT_ATTEMPTED": 1}}
            continue
        out[name] = {"queries": d["queries"], "rows_returned": d["rows"],
                    "verified_citations": d["verified"], "novel_citations": d["novel"],
                    "avg_latency_s": (round(sum(d["latency_s"]) / len(d["latency_s"]), 3)
                                     if d["latency_s"] else None),
                    "statuses": dict(d["statuses"]), "named_zeros": dict(d["zero_kinds"]) or None}
    return out


def _evidence_rows(q_results: list[dict], seed_citations: list[dict]) -> list[dict]:
    out = []
    for q in q_results:
        for a in q["attempts"]:
            for row in a.get("rows") or []:
                out.append({**row, "question": q["question"], "topic_class": q["topic_class"],
                           "instrument": a["instrument"], "verified_doi": verified_doi(row),
                           "novel": is_novel(row, seed_citations)})
    return out


def _card_zero_kind(q_results: list[dict]) -> str:
    attempts = [a for q in q_results for a in q["attempts"]]
    if not attempts:
        return "NO_QUERIES_RAN"
    total_rows = sum(len(a.get("rows") or []) for a in attempts)
    if total_rows == 0:
        kinds = sorted({a["zero_kind"] for a in attempts if a.get("zero_kind")})
        return "ALL_INSTRUMENTS_" + "_OR_".join(kinds) if kinds else "QUERIES_RAN_NO_CITATIONS"
    return "YIELDING"


def probe_card(card_slug: str, *, cards_dir: Path | None = None, evidence_dir: Path | None = None,
              opt: Path | None = None, run_id: str | None = None, now: datetime | None = None,
              http_get: Callable[[str], bytes] | None = None, write: bool = True) -> dict:
    """Run the academic lane for ONE card: read its `## Needs evidence`
    questions and seed citations, run the decision table per question inside
    the lane's own per-day cap, write the evidence file, and return (and, if
    `write`, persist) the probe receipt. Never raises."""
    now = now or _now()
    run_id = run_id or f"{now:%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"
    cards_dir = Path(cards_dir or CARDS_DIR)
    evidence_dir = Path(evidence_dir or EVIDENCE_DIR)
    rec: dict = {"receipt": "research_instruments_probe", "run_id": run_id,
                "card_slug": card_slug, "generated_utc": now.isoformat(timespec="seconds"),
                "licence": "PRODUCT_EXPERIMENT (research-intake evidence; nothing written "
                          "into the card)"}

    def finish(status: str, refusal: str | None = None, **extra) -> dict:
        rec.update(status=status, refusal=refusal, **extra)
        if write:
            p = opt_dir(opt) / "research_instruments" / f"probe_{run_id}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
            tmp.replace(p)
            rec["path"] = str(p)
        return rec

    if not bool(_cfg("RESEARCH_INSTRUMENTS_ENABLED", True)):
        return finish("REFUSED", "RESEARCH_INSTRUMENTS_ENABLED is False")
    try:
        text = (cards_dir / f"{card_slug}.md").read_text(encoding="utf-8")
    except OSError as exc:
        return finish("REFUSED", f"card not found: {card_slug} ({type(exc).__name__}: {exc})")
    verdicts = card_verdicts(text)
    rec["card_verdicts"] = verdicts
    if not card_qualifies(text):
        return finish("REFUSED", f"NOT_A_QUALIFYING_VERDICT: {verdicts or ['none found']} has "
                                 f"no NEEDS_DATA / READY_TO_CELL / NOT_A_HYPOTHESIS_YET arm")
    questions = card_needs_evidence(text)
    rec["needs_evidence"] = questions
    if not questions:
        return finish("OK", None, zero_kind="NO_NEEDS_EVIDENCE_DECLARED", questions_run=[],
                      queries_issued=0, instruments=_aggregate_by_instrument([]), evidence=[])
    seeds = card_seed_citations(text)
    rec["seed_citations"] = seeds
    day = now.date().isoformat()
    day_cap = int(_cfg("QUERY_PLANNER_ACADEMIC_QUERIES_DAY", 12))
    issued_today = sum(1 for r in _read_jsonl(academic_ledger_path(opt))
                       if str(r.get("t") or "")[:10] == day)
    budget_left = max(0, day_cap - issued_today)
    get = http_get or _http_get
    issued_rows: list[dict] = []

    def fetch_fn(name: str, q: str) -> dict:
        nonlocal budget_left
        if budget_left <= 0:
            return {"instrument": name, "status": "REFUSED", "http_status": None,
                   "error": "DAY_CAP_REACHED", "latency_s": None, "rows": [], "query_url": None,
                   "cost_usd": 0.0, "zero_kind": "DAY_CAP_REACHED"}
        r = _try_instrument(name, q, http_get=get, now=now)
        budget_left -= 1
        issued_rows.append({"t": _now().isoformat(timespec="seconds"), "run_id": run_id,
                            "card_slug": card_slug, "instrument": name, "query_text": q,
                            "status": r.get("status"), "http_status": r.get("http_status"),
                            "latency_s": r.get("latency_s"), "n_rows": len(r.get("rows") or []),
                            "cost_usd": r.get("cost_usd", 0.0)})
        return r

    q_results = [probe_question(q, seed_citations=seeds, fetch_fn=fetch_fn) for q in questions]
    if write:
        _append_jsonl(academic_ledger_path(opt), issued_rows)
    evidence = _evidence_rows(q_results, seeds)
    if write:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ev_path = evidence_dir / f"{card_slug}_{run_id}.json"
        tmp = ev_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"card_slug": card_slug, "run_id": run_id,
                                   "generated_utc": rec["generated_utc"], "needs_evidence": questions,
                                   "seed_citations": seeds, "citations": evidence},
                                  indent=2, default=str), encoding="utf-8")
        tmp.replace(ev_path)
        rec["evidence_path"] = str(ev_path)
    return finish("OK", None, day_cap=day_cap, queries_issued=len(issued_rows),
                 questions_run=q_results, instruments=_aggregate_by_instrument(q_results),
                 evidence=evidence, zero_kind=_card_zero_kind(q_results))
