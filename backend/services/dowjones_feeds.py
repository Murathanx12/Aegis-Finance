"""The ten free Dow Jones RSS feeds, polled over plain HTTP -- no browser, no LLM.

    python -m scripts.dowjones_pull --feeds          # all ten, every item, + receipt
    python -m scripts.dowjones_pull --probe-free     # which other DJ surfaces answer

The feeds are ordinary `news_registry` rows (`wsj_markets` ... `barrons_magazine`,
`parser: rss2`), so `scripts/news_pull.pull_all` -- which `daily_pass` and the
`always_on_lab` `news_pull` loop already call on their cadence -- pulls them
with everything else, dedupes by guid (`raw_id`) and stamps `first_seen_utc`
at write time. This module is the Dow Jones-specific door on top of that:

* **A non-XML reply is REFUSED before the parser sees it.** Dow Jones' edge
  answers an unauthenticated page request with an HTML bot-check ("Please
  enable JS and disable any ad blocker") and a 401; if a feed URL ever starts
  answering that way, an HTML page that happens to parse would read as a feed
  with zero items, and two of those turn the source RED as "dead" when it is
  actually blocked. `REFUSED_NON_XML` names the real cause.
* **The receipt prints the AGE of each feed's newest item**, not only its
  count (CLAUDE.md, 2026-09-22: print the age and size of the candidate set).

LICENCE (Dow Jones ToU §9.1, quoted in `web_reader`): RSS content is personal,
non-commercial use only. What is stored is headline + the feed's one-sentence
summary + link + stamps, in the gitignored corpus; the committed receipt holds
counts and stamps only.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend import config as _config

FEED_IDS: tuple[str, ...] = (
    "wsj_markets", "wsj_business", "wsj_world", "wsj_opinion", "wsj_tech",
    "mw_topstories", "mw_marketpulse", "mw_realtimeheadlines", "mw_bulletins",
    "barrons_magazine",
)

#: Every other Dow Jones surface the 2026-09-26 research note names, probed by
#: plain HTTP to record which answer without a login. Nothing is stored but the
#: status and size. `{ticker}` / `{ymd}` are filled by `probe_free_surfaces`.
FREE_SURFACES: tuple[tuple[str, str], ...] = (
    ("dj_terms_of_use", "https://www.dowjones.com/terms-of-use/"),
    ("wsj_archive_day", "https://www.wsj.com/news/archive/{ymd}"),
    ("wsj_heard_on_the_street", "https://www.wsj.com/news/heard-on-the-street"),
    ("wsj_research_ratings", "https://www.wsj.com/market-data/quotes/{ticker}/research-ratings"),
    ("wsj_rss_index", "https://www.wsj.com/rss"),
    ("mw_analyst_estimates", "https://www.marketwatch.com/investing/stock/{ticker}/analystestimates"),
    ("mw_rss_index", "https://www.marketwatch.com/rss"),
    ("barrons_stock_picks", "https://www.barrons.com/market-data/stocks/stock-picks"),
    ("barrons_picks_topic", "https://www.barrons.com/topics/barrons-picks"),
    ("barrons_rss_thisweek", "https://feeds.a.dj.com/rss/RSSBarronsThisWeekMagazine.xml"),
    ("barrons_rss_mostviewed", "https://feeds.a.dj.com/rss/RSSBarronsMostViewed.xml"),
    ("dj_feed_barrons", "https://feeds.content.dowjones.io/public/rss/barrons"),
    ("dj_feed_mw_personalfinance", "https://feeds.content.dowjones.io/public/rss/mw_personalfinance"),
)

_XML_HEADS = (b"<?xml", b"<rss", b"<feed", b"<rdf:rdf", b"<rdf")


def looks_like_xml(raw: bytes) -> bool:
    head = (raw or b"").lstrip(b"\xef\xbb\xbf \t\r\n")[:600].lower()
    return head.startswith(_XML_HEADS) and b"<html" not in head


def _np():
    from scripts import news_pull
    return news_pull


def make_context(**kw: Any):
    """A `news_pull.RunContext` whose `http_get` refuses a non-XML reply."""
    np = _np()

    class _DJContext(np.RunContext):
        def http_get(self, url: str, headers: dict | None = None) -> bytes:  # type: ignore[override]
            raw = super().http_get(url, headers)
            if not looks_like_xml(raw):
                raise np.FetchError(
                    f"REFUSED_NON_XML: {url.split('?')[0]} answered {len(raw)} bytes "
                    f"starting {raw[:60]!r} -- an HTML page (bot-check, login wall, "
                    f"error page) is not a feed with zero items.")
            return raw

    return _DJContext(**kw)


def _newest_published(source_id: str) -> str | None:
    np = _np()
    newest = None
    d = np.source_dir(source_id)
    if not d.exists():
        return None
    for f in sorted(d.glob("*.jsonl"))[-8:]:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                p = json.loads(line).get("published_utc") or ""
            except ValueError:
                continue
            if p and (newest is None or p > newest):
                newest = p
    return newest


def pull_feeds(ids: tuple[str, ...] = FEED_IDS, *, ctx_factory: Callable[..., Any] | None = None,
               paced: bool = True) -> dict:
    """Pull every feed to completion (no row cap). Returns the receipt."""
    np = _np()
    now = datetime.now(timezone.utc)
    per = []
    for i, sid in enumerate(ids):
        ctx = (ctx_factory or make_context)(paced=paced, budget_s=np.SOURCE_BUDGET_S)
        rc = np.pull_source(sid, ctx)
        newest = _newest_published(sid)
        age_h = None
        if newest:
            try:
                age_h = round((now - datetime.fromisoformat(newest)).total_seconds() / 3600, 2)
            except ValueError:
                age_h = None
        per.append({"source": sid, "status": rc.get("status"), "received": rc.get("received"),
                    "new": rc.get("new"), "dupes": rc.get("dupes"),
                    "failures": (rc.get("failures") or [])[:3],
                    "newest_published_utc": newest, "newest_age_h": age_h,
                    "resolution_rate": rc.get("resolution_rate")})
        if paced and i + 1 < len(ids):
            time.sleep(2.0)
    return {"receipt": "dowjones_feeds", "generated_utc": now.isoformat(timespec="seconds"),
            "llm_spend_usd": 0.0, "browser_calls": 0,
            "licence": "Dow Jones ToU 9.1 personal non-commercial; metadata only in git",
            "n_feeds": len(ids), "items_received": sum(int(p["received"] or 0) for p in per),
            "items_new": sum(int(p["new"] or 0) for p in per),
            "refused_or_red": [p["source"] for p in per if p["status"] in ("REFUSED", "RED")],
            "per_feed": per}


def _probe(url: str, timeout: float = 25.0) -> dict:
    np = _np()
    req = urllib.request.Request(url, headers={"User-Agent": np.USER_AGENT})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as fh:  # noqa: S310 fixed list
            body = fh.read()
            code = fh.status
    except urllib.error.HTTPError as e:
        body, code = e.read() if hasattr(e, "read") else b"", e.code
    except Exception as e:  # noqa: BLE001
        return {"url": url, "status": None, "error": f"{type(e).__name__}: {e}"[:160]}
    low = body[:4000].lower()
    return {"url": url, "status": code, "bytes": len(body), "xml": looks_like_xml(body),
            "bot_check": b"enable js" in low or b"captcha" in low,
            "wall_s": round(time.time() - t0, 2)}


def probe_free_surfaces(*, ticker: str = "MU", ymd: str | None = None,
                        probe_fn: Callable[[str], dict] | None = None) -> dict:
    ymd = ymd or datetime.now(timezone.utc).strftime("%Y/%m/%d")
    rows = []
    for name, tmpl in FREE_SURFACES:
        url = tmpl.format(ticker=ticker.lower() if "marketwatch" in tmpl else ticker, ymd=ymd)
        r = (probe_fn or _probe)(url)
        rows.append({"surface": name, **r})
        time.sleep(0.0 if probe_fn else 1.5)
    ok = [r["surface"] for r in rows if r.get("status") == 200]
    walled = [r["surface"] for r in rows if r.get("status") in (401, 403)]
    return {"receipt": "dowjones_free_surfaces",
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": "plain HTTP GET, no cookies, no browser", "answer_200": ok,
            "walled_401_403": walled,
            "other": [r["surface"] for r in rows if r["surface"] not in ok + walled],
            "rows": rows}


def receipts_dir() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "dowjones"
