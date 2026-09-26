"""Dow Jones article -> dated, directional claims -> `source:<column>` forecast rows.

One door for BOTH ways a Dow Jones article reaches Aegis: the operator's paste
inbox (`digest_inbox`, the primary path) and the browser reader
(`web_reader`, only on a `--handoff` night). Both call `extract_claims` and
`write_forecasts`, so a claim graded on Monday is graded the same way whichever
door the article came through.

THE COLUMN IS THE SOURCE
========================
The forecast row's `source_id` is the COLUMN, not the publisher:
`wsj_heard_on_the_street`, `barrons_stock_picks`, `barrons_big_money_poll`,
`mw_analyst_estimates`. "The Wall Street Journal" is not a forecaster; a
column with a stable desk and a recurring format is, and it is the unit whose
weight `forecast_reputation` can earn. Anything unrecognised is
`<publisher>_other` so it is still counted and never silently merged into a
named column.

WHAT GOES IN GIT AND WHAT DOES NOT (the repo is PUBLIC)
======================================================
`sources/claims.jsonl` and `predictions.jsonl` are TRACKED and pushed to a
public GitHub repo. Dow Jones' subscriber agreement §9.3 forbids
redistributing the content ("you may not use, sell, publish, distribute,
retransmit or otherwise provide access to the Content ... to anyone"). So:

* the forecast row's `claim_text` is the model's OWN one-sentence paraphrase
  (`paraphrase`), capped at `PARAPHRASE_MAX` characters, never the quote;
* the verbatim `quote` -- kept because it is how a human checks the model did
  not invent the claim -- lives ONLY in the gitignored local corpus
  (`news_corpus/dowjones/_claims/<date>.jsonl`);
* a quote that does not occur in the article text is REFUSED, not repaired
  (an invented quote is an invented claim).

PIT
===
`claim_utc` is `first_seen_utc` -- when Aegis first held the text -- never the
article's own dateline. An article more than `news_registry.ARCHIVE_LAG_DAYS`
older than its `first_seen_utc` is an ARCHIVE row: its claims are recorded but
write NO forecast rows, because a forecast dated today about a month-old call is
backfilled evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend import config as _config

#: Column source ids, and the evidence that assigns an article to one. Checked
#: in order; the first match wins.
COLUMN_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # (source_id, publisher, (url/title/text markers, lowercase))
    ("wsj_heard_on_the_street", "wsj", ("heard-on-the-street", "heard on the street")),
    ("barrons_big_money_poll", "barrons", ("big-money-poll", "big money poll", "big money")),
    ("barrons_stock_picks", "barrons", ("stock-picks", "stock picks", "/buy-", "barron's picks",
                                         "stock pick")),
    ("mw_analyst_estimates", "marketwatch", ("analystestimates", "analyst estimates")),
)
PUBLISHERS: tuple[str, ...] = ("wsj", "barrons", "marketwatch")

HOST_PUBLISHER: dict[str, str] = {"wsj.com": "wsj", "barrons.com": "barrons",
                                  "marketwatch.com": "marketwatch"}

#: Stated horizon buckets (sessions). The grader's own grid is 1/5/20; the
#: stated horizon travels with the claim so a later study can read it.
HORIZON_BUCKETS: tuple[int, ...] = (5, 21, 63, 126, 252)
MAGNITUDE_BUCKETS: tuple[str, ...] = ("small", "medium", "large", "unstated")
PARAPHRASE_MAX = 200
QUOTE_MAX = 300
MAX_CLAIMS_PER_ARTICLE = 6

SYSTEM_PROMPT = (
    "You extract investment claims from one financial news article. Answer in "
    "English with ONLY a JSON object, no prose. Schema: "
    '{"claims": [{"ticker": "US ticker, uppercase", '
    '"direction": "up|down|none", '
    '"horizon_days": 5|21|63|126|252, '
    '"magnitude_bucket": "small|medium|large|unstated", '
    '"quote": "the sentence from the article that makes the claim, copied verbatim, <= 300 chars", '
    '"paraphrase": "your own words, one sentence, <= 200 chars, no quotation"}]}. '
    "A claim is the AUTHOR'S OR A NAMED SOURCE'S FORWARD-LOOKING view that a "
    "specific listed stock will rise or fall (or beat/lag the market). A "
    "description of what a stock already did ('has risen 26% this year') is NOT "
    "a claim. Skip facts with no implied direction, skip indexes and ETFs, skip "
    "private companies. Use the exact exchange ticker (HP Inc is HPQ). At most "
    "ONE claim per ticker: the article's overall view of that stock. "
    "magnitude: small < 5%, medium 5-15%, large > 15%, unstated if no number. "
    "horizon: the stated or clearly implied horizon, else 63. At most 6 claims. "
    'If there is none, answer {"claims": []}.'
)

_TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")


def publisher_of(url: str = "", text: str = "") -> str | None:
    from urllib.parse import urlsplit
    try:
        h = (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        h = ""
    for dom, pub in HOST_PUBLISHER.items():
        if h == dom or h.endswith("." + dom):
            return pub
    low = (text or "")[:4000].lower()
    if "barron's" in low or "barrons" in low:
        return "barrons"
    if "marketwatch" in low:
        return "marketwatch"
    if "wall street journal" in low or "wsj" in low:
        return "wsj"
    return None


def column_of(url: str = "", title: str = "", text: str = "",
              publisher: str | None = None) -> str:
    """The column `source_id`. `<publisher>_other` (or `dowjones_other`)
    when nothing identifies a column -- counted, never merged into one."""
    pub = publisher or publisher_of(url, text)
    hay = " ".join([(url or "").lower(), (title or "").lower(), (text or "")[:1500].lower()])
    for sid, p, markers in COLUMN_RULES:
        if pub not in (None, p):
            continue
        if any(m in hay for m in markers):
            return sid
    return f"{pub}_other" if pub else "dowjones_other"


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def _nearest(v: Any, grid: tuple[int, ...], default: int = 63) -> int:
    try:
        x = int(float(v))
    except (TypeError, ValueError):
        return default
    return min(grid, key=lambda g: abs(g - x))


def parse_reply(reply: str | None) -> list[dict]:
    if not reply:
        return []
    try:
        d = json.loads(reply[reply.index("{"):reply.rindex("}") + 1])
    except ValueError:
        return []
    cl = d.get("claims") if isinstance(d, dict) else None
    return [c for c in (cl or []) if isinstance(c, dict)]


def article_tickers(text: str, title: str = "") -> set[str] | None:
    """Tickers the ARTICLE names: resolved from company names by
    `news_entities`, plus any written as `(TICK)` or `$TICK`. None when the
    resolver cannot run (the check is then skipped and says so)."""
    found = set(re.findall(r"\(([A-Z]{1,5}(?:\.[A-Z])?)\)", text or ""))
    found |= set(re.findall(r"\$([A-Z]{1,5})\b", text or ""))
    try:
        from backend.services import news_entities as E
        found |= set(E.resolve(title + "\n" + (text or ""), tbl=E.tables(), limit=200).tickers)
    except Exception:  # noqa: BLE001 -- the caller records that the check was skipped
        return None
    return found


#: A claim whose quote AND paraphrase only describe a move that already
#: happened ("has risen 26% this year") is not a forecast. The model was told
#: so and still emitted one on the first live night (DELL), so it is checked.
_PAST_MOVE = re.compile(r"\b(has|have|had)\s+(risen|fallen|rallied|climbed|dropped|gained|"
                        r"lost|soared|surged|slumped|doubled|tripled|jumped|tumbled)\b|"
                        r"\b(rose|fell|rallied|climbed|dropped|soared|surged|slumped|jumped|"
                        r"tumbled)\b", re.I)
_FORWARD_CUE = re.compile(r"\b(will|would|should|could|may|might|expect\w*|likely|poised|"
                          r"set to|stands to|forecast\w*|project\w*|outlook|ahead|next|"
                          r"further|continue\w*|keep|upside|downside|target|deserves|"
                          r"undervalued|overvalued|cheap|expensive|risk|threat\w*|bet)\b", re.I)


def backward_only(quote: str, paraphrase: str) -> bool:
    """True when the model's OWN paraphrase (its summary of the claim) only
    describes a past move, or when quote and paraphrase together do. The
    paraphrase alone decides first: a forward word elsewhere in the quoted
    sentence ("... and investors expect more") does not turn "Dell has risen
    sharply this year" into a forecast."""
    def past_only(t: str) -> bool:
        return bool(_PAST_MOVE.search(t)) and not _FORWARD_CUE.search(t)
    return past_only(paraphrase) or past_only(f"{quote} {paraphrase}")


_GENERIC_FIRST = {"the", "first", "united", "american", "general", "national", "international",
                  "global", "new", "north", "south", "west", "east", "great", "royal", "china",
                  "bank", "capital", "energy", "health", "select", "advanced", "applied"}
_NAMES_BY_SYMBOL: dict[str, list[str]] = {}


def ticker_named(ticker: str, text: str) -> bool:
    """Does the article name this ticker's company in the SHORT form papers use
    after the first mention ("Micron" for Micron Technology)? The resolver
    only matches full registered names, and a column says "Micron" nine times
    and "Micron Technology" once, if at all. The distinctive first word of any
    registered name (>= 4 letters, not generic) must appear as a word."""
    if not _NAMES_BY_SYMBOL:
        try:
            from backend.services import news_entities as E
            for name, sym in E.tables().name_to_symbol.items():
                _NAMES_BY_SYMBOL.setdefault(sym, []).append(name)
        except Exception:  # noqa: BLE001
            return False
    low = (text or "").lower()
    for name in _NAMES_BY_SYMBOL.get(ticker.upper(), []):
        first = re.sub(r"[^a-z0-9&]", "", name.split()[0]) if name.split() else ""
        if len(first) >= 4 and first not in _GENERIC_FIRST and re.search(
                r"\b" + re.escape(first) + r"\b", low):
            return True
        if name in low:
            return True
    return False


def validate_claims(raw: list[dict], article_text: str, *,
                    allowed_tickers: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """(kept, refused). Refuses a bad ticker, a ticker the article does not
    name (when `allowed_tickers` is known), a quote not in the article, and a
    second claim on the same (ticker, direction) -- one article is ONE view of
    a stock, not four independent forecasts."""
    kept, refused = [], []
    seen: set[tuple[str, str]] = set()
    body = _norm(article_text)
    for c in raw[:MAX_CLAIMS_PER_ARTICLE]:
        t = str(c.get("ticker") or "").upper().lstrip("$").strip()
        q = str(c.get("quote") or "").strip()[:QUOTE_MAX]
        para = re.sub(r"\s+", " ", str(c.get("paraphrase") or "")).strip()[:PARAPHRASE_MAX]
        d = str(c.get("direction") or "none").lower().strip()
        why = None
        if not _TICKER.match(t):
            why = f"REFUSED_TICKER: {t!r}"
        elif (allowed_tickers is not None and t not in allowed_tickers
              and not ticker_named(t, article_text)):
            why = f"REFUSED_TICKER_NOT_IN_ARTICLE: {t!r}"
        elif d != "none" and backward_only(q, para):
            why = f"REFUSED_BACKWARD_LOOKING: {t!r}"
        elif (t, d) in seen:
            why = f"REFUSED_DUPLICATE_VIEW: {t!r} {d}"
        elif not q or _norm(q)[:120] not in body:
            why = "REFUSED_QUOTE_NOT_IN_ARTICLE"
        elif not para:
            why = "REFUSED_NO_PARAPHRASE"
        elif d not in ("up", "down", "none"):
            why = f"REFUSED_DIRECTION: {d!r}"
        if why:
            refused.append({"ticker": t, "why": why})
            continue
        seen.add((t, d))
        mb = str(c.get("magnitude_bucket") or "unstated").lower()
        kept.append({"ticker": t, "direction": d,
                     "horizon_days_stated": _nearest(c.get("horizon_days"), HORIZON_BUCKETS),
                     "magnitude_bucket": mb if mb in MAGNITUDE_BUCKETS else "unstated",
                     "quote": q, "paraphrase": para})
    return kept, refused


def default_llm(system: str, user: str) -> str | None:
    from backend.services import llm_analyzer as LA
    return LA._call_llm(system, user, purpose=str(
        getattr(_config, "DOWJONES_CLAIMS_PURPOSE", "dowjones_claims")))


def extract_claims(article: dict, *, llm_fn: Callable[[str, str], str | None] | None = None
                   ) -> dict:
    """One LLM call per article. Returns `{claims, refused, status}`."""
    text = str(article.get("text") or "")
    if len(text) < 300:
        return {"claims": [], "refused": [], "status": "SKIPPED_TOO_SHORT"}
    user = (f"Title: {article.get('title') or ''}\nURL: {article.get('url') or ''}\n"
            f"Published: {article.get('published') or 'unknown'}\n\n{text[:12000]}")
    reply = (llm_fn or default_llm)(SYSTEM_PROMPT, user)
    if reply is None:
        return {"claims": [], "refused": [], "status": "LLM_NO_REPLY"}
    allowed = article_tickers(text, str(article.get("title") or ""))
    kept, refused = validate_claims(parse_reply(reply), text, allowed_tickers=allowed)
    return {"claims": kept, "refused": refused, "ticker_check": allowed is not None,
            "status": "OK" if kept else ("ALL_REFUSED" if refused else "NO_CLAIMS")}


def local_claims_path(day: str) -> Path:
    return (Path(_config.OPTIMUS_LEDGER_DIR) / "news_corpus" / "dowjones" / "_claims"
            / f"{day}.jsonl")


def write_forecasts(article: dict, claims: list[dict], *, ledger_path: Path | None = None,
                    claims_path: Path | None = None, local_path: Path | None = None) -> dict:
    """Claims -> `source_registry.write_claims` (tracked, paraphrase only) and
    the local verbatim file (gitignored). Archive articles write no forecast."""
    from backend.services import news_registry as NR
    from backend.services import source_registry as SR
    seen = str(article["first_seen_utc"])
    col = article.get("column") or column_of(article.get("url", ""), article.get("title", ""),
                                             article.get("text", ""))
    grade = NR.effective_pit_grade({"published_utc": article.get("published_utc"),
                                    "first_seen_utc": seen, "pit_grade": "first_seen_only"})
    day = seen[:10]
    lp = Path(local_path) if local_path else local_claims_path(day)
    lp.parent.mkdir(parents=True, exist_ok=True)
    with lp.open("a", encoding="utf-8") as fh:
        for c in claims:
            fh.write(json.dumps({"source_id": col, "article_sha": article.get("sha"),
                                 "url": article.get("url"), "first_seen_utc": seen,
                                 "published_utc": article.get("published_utc"),
                                 "pit_grade": grade, **c}, ensure_ascii=False) + "\n")
    if grade == NR.ARCHIVE_GRADE:
        return {"source_id": col, "pit_grade": grade, "n_claims": len(claims),
                "n_rows_written": 0, "status": "ARCHIVE_NO_FORECAST"}
    rows = [{"source_id": col, "source_kind": "journalist", "ticker": c["ticker"],
             "claim_text": f"[{col}] {c['paraphrase']}", "claim_utc": seen,
             "direction": c["direction"], "post_url": str(article.get("url") or "")}
            for c in claims]
    res = SR.write_claims(rows, path=ledger_path, claims_path=claims_path)
    return {"source_id": col, "pit_grade": grade, "n_claims": len(claims), **res,
            "status": "OK"}


def text_sha(text: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", text or "").strip().encode("utf-8")).hexdigest()[:20]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
