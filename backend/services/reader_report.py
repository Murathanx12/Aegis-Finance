"""The reader's YIELD REPORT, in words the owner reads: what was read today.

`dowjones/reading_report_<day>.md`, refreshed hourly by the reader pool (and by
the night supervisor's hourly digest): pages read per site and lane, articles
stored, tickers covered out of the universe, the ten most recent headlines per
site, pages not found or blocked, social pages, media items and transcripts,
hosts cooling, and the current speed. Built only from files on disk
(`page_log.jsonl`, the stored corpus, the social and transcript rows); no
network, no LLM.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend import config as _config
from backend.services import disk_guard as DG

DJ_SITES = ("wsj.com", "barrons.com", "marketwatch.com")
SOCIAL = ("x.com", "reddit.com", "stocktwits.com")
_STOCK_URL = (
    re.compile(r"marketwatch\.com/investing/stock/([a-z0-9.]+)(?:/|$|\?)", re.I),
    re.compile(r"wsj\.com/market-data/quotes/([A-Za-z0-9.]+)", re.I),
    re.compile(r"barrons\.com/market-data/stocks/([a-z0-9.]+)", re.I),
)


def ledger() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR)


def report_path(day: str) -> Path:
    return ledger() / "dowjones" / f"reading_report_{day}.md"


def _jsonl(p: Path) -> list[dict]:
    out = []
    try:
        for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def ticker_of_stock_url(url: str) -> str | None:
    for rx in _STOCK_URL:
        m = rx.search(url or "")
        if m:
            return m.group(1).upper()
    return None


def gather(day: str, *, root: Path | None = None, universe: list[str] | None = None,
           now: datetime | None = None) -> dict:
    """Every number the report prints, as a dict (a test reads it directly)."""
    root = Path(root) if root else ledger()
    now = now or datetime.now(timezone.utc)
    pages = [r for r in _jsonl(root / "dowjones" / "page_log.jsonl")
             if str(r.get("t") or "").startswith(day)]
    by_site_lane: dict[str, Counter] = defaultdict(Counter)
    classes: dict[str, Counter] = defaultdict(Counter)
    covered: set[str] = set()
    last_hour: Counter = Counter()
    for r in pages:
        h = r.get("host") or "-"
        by_site_lane[h][r.get("lane") or "-"] += 1
        classes[h][r.get("class") or "?"] += 1
        t = ticker_of_stock_url(r.get("url") or "")
        if t and r.get("class") == "OK":
            covered.add(t)
        try:
            if now - datetime.fromisoformat(r["t"]) <= timedelta(hours=1):
                last_hour[h] += 1
        except (KeyError, ValueError, TypeError):
            pass
    arts: list[dict] = []
    fronts_stored = 0
    corpus = root / "news_corpus" / "dowjones"
    for p in corpus.glob(f"*/{day}/*.json"):
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if rec.get("page_kind") == "front":      # a front's headline record, not an article
            fronts_stored += 1
            continue
        arts.append({k: rec.get(k) for k in ("publisher", "title", "url", "first_seen_utc",
                                             "reached_by", "tickers_named", "media", "column")})
        for t in (rec.get("tickers_named") or []):
            covered.add(str(t).upper())
    per_pub = Counter(a.get("publisher") or "?" for a in arts)
    by_lane = Counter(((a.get("reached_by") or {}).get("lane") or "reader (plan)") for a in arts)
    recent: dict[str, list[str]] = {}
    for pub in sorted(per_pub):
        rows = sorted((a for a in arts if a.get("publisher") == pub),
                      key=lambda a: a.get("first_seen_utc") or "", reverse=True)[:10]
        recent[pub] = [f"{(a.get('first_seen_utc') or '')[11:16]} {a.get('title') or a.get('url')}"
                       for a in rows]
    social = {}
    for h in SOCIAL:
        rows = _jsonl(root / "news_corpus" / "social" / h / f"{day}.jsonl")
        social[h] = {"rows": len(rows), "tickers": len({r.get("ticker") for r in rows if r.get("ticker")})}
        for r in rows:
            if r.get("ticker"):
                covered.add(str(r["ticker"]).upper())
    media: dict[str, Counter] = defaultdict(Counter)
    tdir = root / "news_corpus" / "media_transcripts"
    for p in tdir.glob(f"*/{day}.jsonl") if tdir.exists() else []:
        for r in _jsonl(p):
            media[p.parent.name]["items"] += 1
            if r.get("transcript") and r.get("transcript") != "NONE_PUBLISHED":
                media[p.parent.name]["with_transcript"] += 1
    try:
        cooling = json.loads((root / "dowjones" / "host_cooling.json").read_text(encoding="utf-8"))
        cooling = {h: r for h, r in cooling.items()
                   if datetime.fromisoformat(r["until"]) > now}
    except (OSError, ValueError, KeyError, TypeError):
        cooling = {}
    try:
        dropped = json.loads((root / "dowjones" / "sections_not_found.json").read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        dropped = {}
    uni = [u.upper().replace("-", ".") for u in (universe or [])]
    covered = {c.replace("-", ".") for c in covered}
    return {"day": day, "generated_utc": now.isoformat(timespec="seconds"),
            "pages_by_site_lane": {h: dict(c) for h, c in by_site_lane.items()},
            "classes_by_site": {h: dict(c) for h, c in classes.items()},
            "pages_last_hour": dict(last_hour), "articles_by_publisher": dict(per_pub),
            "articles_by_lane": dict(by_lane), "recent_headlines": recent, "social": social,
            "media": {h: dict(c) for h, c in media.items()}, "cooling": cooling,
            "sections_dropped": dropped,
            "universe_size": len(uni),
            "tickers_covered": len(covered & set(uni)) if uni else len(covered),
            "n_pages": len(pages), "n_articles": len(arts), "n_front_records": fronts_stored}


def render(g: dict) -> str:
    """PURE. The markdown the owner reads."""
    L = [f"# What the reader read on {g['day']}", "",
         f"Refreshed {g['generated_utc']} (hourly). Pages: **{g['n_pages']}**; articles "
         f"stored: **{g['n_articles']}**; tickers covered: **{g['tickers_covered']} of "
         f"{g['universe_size']}** in the universe.", "",
         "## Speed now (page loads in the last 60 minutes)", ""]
    tot = sum(g["pages_last_hour"].values())
    L.append(f"- all hosts: **{tot} pages/hour**")
    for h, n in sorted(g["pages_last_hour"].items()):
        L.append(f"- {h}: {n}")
    L += ["", "## Pages read, per site and lane", ""]
    for h, lanes in sorted(g["pages_by_site_lane"].items()):
        L.append(f"- **{h}**: " + ", ".join(f"{k} {v}" for k, v in
                                           sorted(lanes.items(), key=lambda kv: -kv[1])))
    L += ["", "## Not found, blocked, walls (every page class that is not OK)", ""]
    bad = {h: {k: v for k, v in c.items() if k != "OK"} for h, c in g["classes_by_site"].items()}
    bad = {h: c for h, c in bad.items() if c}
    L += [f"- {h}: " + ", ".join(f"{k} {v}" for k, v in c.items()) for h, c in sorted(bad.items())] \
        or ["- none"]
    if g["cooling"]:
        L += ["", "## Hosts stopped for a cooling period", ""]
        L += [f"- **{h}** until {r.get('until')}: {r.get('why')} ({r.get('url')})"
              for h, r in g["cooling"].items()]
    L += ["", "## Articles stored", ""]
    L += [f"- {p}: {n}" for p, n in sorted(g["articles_by_publisher"].items())] or ["- none"]
    L.append("- by how they were reached: " + ", ".join(
        f"{k} {v}" for k, v in sorted(g["articles_by_lane"].items(), key=lambda kv: -kv[1])))
    L += ["", "## Social pages (source_kind = social: never an alert, never an order)", ""]
    L += [f"- {h}: {v['rows']} pages, {v['tickers']} tickers" for h, v in g["social"].items()]
    L += ["", "## Media items and transcripts (text the site publishes)", ""]
    L += [f"- {h}: {v.get('items', 0)} items, {v.get('with_transcript', 0)} with a transcript"
          for h, v in sorted(g["media"].items())] or ["- none yet"]
    if g["sections_dropped"]:
        L += ["", "## Section URLs dropped (not found once)", ""]
        L += [f"- {u}" for u in sorted(g["sections_dropped"])]
    L += ["", "## The ten most recent headlines per site", ""]
    for pub, rows in g["recent_headlines"].items():
        L.append(f"### {pub}")
        L += [f"- {r}" for r in rows]
        L.append("")
    return "\n".join(L).rstrip() + "\n"


# ───────────── everything read in the last N hours (2026-09-29) ──────────────
#
# The one call a digest job makes ("what did the reader read since ..."). It
# reads files only: the page store (`news_corpus/dowjones/<publisher>/<day>/
# <sha>.json`, which since 2026-09-29 also holds the general-news pages and the
# section-front headline records), the social rows and the media transcripts.

PAGE_FIELDS = ("url", "host", "publisher", "section", "title", "published_utc",
               "fetched_utc", "text", "outbound_links", "page_class", "page_kind",
               "source_kind", "column", "reached_by", "tickers_named", "media", "tables",
               "byline", "sha", "chars", "archive", "path")


def _t(s: Any) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _host(url: str) -> str:
    from urllib.parse import urlsplit
    try:
        return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def pages_read_since(hours: float = 6.0, *, now: datetime | None = None,
                     root: Path | None = None, include_text: bool = True,
                     include_social: bool = True, include_transcripts: bool = True,
                     kinds: tuple[str, ...] | None = None,
                     hosts: tuple[str, ...] | None = None,
                     include_archive: bool = True) -> list[dict]:
    """Every page the reader READ and stored in the last `hours`, newest first.

    One dict per page with `PAGE_FIELDS`: `url`, `host`, `publisher`, `section`,
    `title`, `published_utc` (the page's own dateline, None when it prints
    none), `fetched_utc` (when WE read it), `text`, `outbound_links` ([{url,
    text}]), `page_class` ("OK" for every stored page), `page_kind` ("front" =
    a section front's headline list in page order; "article" / "media" /
    "stock_text" / "front_text"; "social"), `source_kind` ("dowjones",
    "general_news", "social"), `column`, `reached_by` (lane, section, parent
    url, position, depth, via), `tickers_named`, `media`, `tables`, `sha`,
    `path`; plus `transcripts` ([{media_kind, title, transcript,
    transcript_source}]) when the page carried media with a published
    transcript. Only OK pages are stored, so blocked / paywalled / blank pages
    are not here: they are counted in `page_log.jsonl` (see `gather`).

    `archive` is True when the page's own dateline is more than
    READER_MAX_ARTICLE_AGE_DAYS before we read it (`include_archive=False`
    drops those). `kinds` / `hosts` filter (a host matches itself or a subdomain);
    `include_text=False` drops the text for a cheap index. Files only; no
    network, no LLM. Missing folders are empty, never an error."""
    root = Path(root) if root else ledger()
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=float(hours))
    days = sorted({(since + timedelta(days=i)).date().isoformat()
                   for i in range((now.date() - since.date()).days + 1)} | {now.date().isoformat()})

    def host_ok(h: str) -> bool:
        return not hosts or any(h == d or h.endswith("." + d) for d in hosts)

    tx: dict[str, list[dict]] = defaultdict(list)
    if include_transcripts:
        troot = root / "news_corpus" / "media_transcripts"
        for d in days:
            for p in (troot.glob(f"*/{d}.jsonl") if troot.exists() else []):
                for r in _jsonl(p):
                    if r.get("transcript") and r.get("transcript") != "NONE_PUBLISHED":
                        tx[str(r.get("url") or "")].append(
                            {k: r.get(k) for k in ("media_kind", "title", "duration_s",
                                                   "transcript", "transcript_source",
                                                   "published")})
    out: list[dict] = []
    corpus = root / "news_corpus" / "dowjones"
    for d in days:
        for p in corpus.glob(f"*/{d}/*.json"):
            if p.parts[-3].startswith("_"):
                continue
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            t = _t(rec.get("first_seen_utc"))
            if t is None or t < since or t > now + timedelta(minutes=5):
                continue
            h = rec.get("host") or _host(rec.get("url") or "")
            kind = rec.get("page_kind") or "article"
            if (kinds and kind not in kinds) or not host_ok(h):
                continue
            if not include_archive and rec.get("archive"):
                continue
            row = {k: rec.get(k) for k in PAGE_FIELDS}
            row.update(host=h, page_kind=kind, fetched_utc=rec.get("first_seen_utc"),
                       page_class=rec.get("page_class") or "OK",
                       source_kind=rec.get("source_kind") or (
                           "dowjones" if rec.get("publisher") in ("wsj", "barrons", "marketwatch")
                           else "unknown"),
                       section=rec.get("section") or (rec.get("reached_by") or {}).get("section"),
                       outbound_links=rec.get("outbound_links") or [], path=str(p),
                       archive=bool(rec.get("archive")))
            if not include_text:
                row.pop("text", None)
            if tx.get(rec.get("url") or ""):
                row["transcripts"] = tx[rec["url"]]
            out.append(row)
    if include_social and (not kinds or "social" in kinds):
        sroot = root / "news_corpus" / "social"
        for d in days:
            for p in (sroot.glob(f"*/{d}.jsonl") if sroot.exists() else []):
                for r in _jsonl(p):
                    t = _t(r.get("read_utc"))
                    h = r.get("host") or _host(r.get("url") or "")
                    if t is None or t < since or t > now + timedelta(minutes=5) or not host_ok(h):
                        continue
                    row = {"url": r.get("url"), "host": h, "publisher": h, "section": None,
                           "title": r.get("title"), "published_utc": None,
                           "fetched_utc": r.get("read_utc"), "text": r.get("text"),
                           "outbound_links": [], "page_class": "OK", "page_kind": "social",
                           "source_kind": "social", "ticker": r.get("ticker"),
                           "chars": r.get("chars"), "path": str(p)}
                    if not include_text:
                        row.pop("text", None)
                    out.append(row)
    out.sort(key=lambda r: str(r.get("fetched_utc") or ""), reverse=True)
    return out


def lane_report(since: datetime, until: datetime, *, root: Path | None = None) -> dict:
    """Loads and OK pages by READING-BUDGET lane, by host and by UTC hour in
    [since, until), from `dowjones/budget_lanes.jsonl` (one row per page load
    the pool spent, 2026-09-30), plus the official API sources' requests over
    the same window (`official/requests.jsonl`)."""
    from collections import Counter
    base = Path(root) if root else ledger()
    lanes, ok_l, hosts, ok_h, hours, ok_hr = (Counter() for _ in range(6))
    for r in _jsonl(base / "dowjones" / "budget_lanes.jsonl"):
        t = _t(r.get("t"))
        if t is None or not (since <= t < until):
            continue
        ok = r.get("outcome") == "OK"
        hr = t.strftime("%Y-%m-%dT%H")
        lanes[r.get("lane") or "?"] += 1
        hosts[r.get("host") or "?"] += 1
        hours[hr] += 1
        if ok:
            ok_l[r.get("lane") or "?"] += 1
            ok_h[r.get("host") or "?"] += 1
            ok_hr[hr] += 1
    src, ok_s = Counter(), Counter()
    for r in _jsonl(base / "official" / "requests.jsonl"):
        t = _t(r.get("t"))
        if t is None or not (since <= t < until):
            continue
        src[r.get("source") or "?"] += 1
        if r.get("class") == "OK":
            ok_s[r.get("source") or "?"] += 1
    return {"since": since.isoformat(timespec="seconds"), "until": until.isoformat(timespec="seconds"),
            "browser_loads": sum(lanes.values()), "browser_ok": sum(ok_l.values()),
            "by_lane": {k: {"loads": v, "ok": ok_l.get(k, 0)} for k, v in lanes.most_common()},
            "by_host": {k: {"loads": v, "ok": ok_h.get(k, 0)} for k, v in hosts.most_common()},
            "by_hour_utc": {k: {"loads": hours[k], "ok": ok_hr.get(k, 0)} for k in sorted(hours)},
            "official_requests": {k: {"requests": v, "ok": ok_s.get(k, 0)}
                                  for k, v in src.most_common()}}


def render_lanes(lr: dict) -> str:
    L = ["", f"## Pages by reading-budget lane ({lr['since'][:16]} to {lr['until'][:16]} UTC)", "",
         f"- browser: {lr['browser_ok']} OK of {lr['browser_loads']} loads"]
    L += [f"- {k}: {v['ok']} OK / {v['loads']} loads" for k, v in lr["by_lane"].items()]
    L += ["", "By host: " + ", ".join(f"{k} {v['ok']}/{v['loads']}" for k, v in lr["by_host"].items())]
    if lr["official_requests"]:
        L += ["", "Official API sources (requests, OK): " + ", ".join(
            f"{k} {v['ok']}/{v['requests']}" for k, v in lr["official_requests"].items())]
    return "\n".join(L) + "\n"


def write_report(day: str | None = None, *, universe: list[str] | None = None,
                 root: Path | None = None, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    day = day or now.date().isoformat()
    if universe is None:
        try:
            from scripts import dowjones_pull as DP
            universe = DP.rolling_names()
        except Exception:  # noqa: BLE001 -- the report still prints
            universe = []
    g = gather(day, root=root, universe=universe, now=now)
    p = (Path(root) / "dowjones" / f"reading_report_{day}.md") if root else report_path(day)
    text = render(g)
    try:                                  # 2026-09-30: the reading budget, by lane
        text += render_lanes(lane_report(now - timedelta(hours=24), now, root=root))
    except Exception as exc:  # noqa: BLE001 -- the report prints without it
        text += f"\n(lane report failed: {type(exc).__name__}: {exc})\n"
    DG.atomic_write_text(p, text)
    try:                                  # 2026-09-30: the owner's check list, always current
        write_what_the_reader_opens(root=root, now=now)
    except Exception:  # noqa: BLE001 -- never blocks the report
        pass
    return p



# ─────────── what the reader opens: the owner's check list (2026-09-30) ──────────
#
# The owner saw something in the dedicated Chrome and said "openclaw opens
# banks". This page lists, from the CONFIG the running reader uses (never
# written by hand), every host the visible browser may open, grouped by kind,
# every source read by feed or API only (never in a window), and every class of
# address that is refused -- so what is on screen can be checked against it.

#: kinds of the browser allowlist. A host on the allowlist that none of these
#: names is printed under "UNCLASSIFIED" (and a test fails), never hidden.
OPENS_KINDS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Paid news (subscription or metered)",
     ("wsj.com", "barrons.com", "marketwatch.com", "ft.com", "asia.nikkei.com", "scmp.com"),
     "Dow Jones on the owner's subscription; FT, Nikkei and SCMP fronts and free pieces only "
     "(a paywall is recorded, never worked around)"),
    ("Free news", ("reuters.com", "apnews.com", "cnbc.com", "finance.yahoo.com", "bbc.com"),
     "public pages; a robots.txt refusal is recorded and the page is never opened"),
    ("Official releases", ("bls.gov", "sec.gov", "treasury.gov"),
     "US statistics, SEC and Treasury press pages"),
    ("Central banks (public releases)",
     ("federalreserve.gov", "ecb.europa.eu", "boj.or.jp", "bankofengland.co.uk", "hkma.gov.hk",
      "pbc.gov.cn"),
     "official public sites, not commercial banks"),
    ("Social (read only)", ("x.com", "reddit.com", "stocktwits.com"),
     "no posting, no messages, no sign-in; per-host caps unchanged"),
)


def _on_any(host: str, domains: tuple[str, ...]) -> bool:
    h = (host or "").lower().removeprefix("www.")
    return any(h == d or h.endswith("." + d) for d in domains)


def what_the_reader_opens(now: datetime | None = None, root: Path | None = None) -> dict:
    """PURE over the imported config and rule modules. The browser allowlist by
    kind with each host's caps, the feed / API sources, and the refused classes."""
    from backend.services import browser_policy as BP
    from backend.services import web_reader as WR
    now = now or datetime.now(timezone.utc)
    allow = tuple(dict.fromkeys(WR.hosts()))
    per_h = dict(getattr(_config, "READER_MAX_PER_HOUR_BY_HOST", {}) or {})
    per_d = dict(getattr(_config, "WEB_READER_MAX_PER_DAY_BY_HOST", {}) or {})
    kinds: list[dict] = []
    placed: set[str] = set()
    for name, doms, note in OPENS_KINDS:
        hs = [h for h in allow if _on_any(h, doms)]
        placed |= set(hs)
        kinds.append({"kind": name, "note": note,
                      "browser_hosts": [{"host": h, "per_hour": per_h.get(h), "per_day": per_d.get(h)}
                                        for h in hs]})
    unclassified = [h for h in allow if h not in placed]
    try:
        from backend.services import official_sources as OS
        feeds = [{"source": k, "host": v.get("host"), "lane": v.get("lane"), "how": v.get("how"),
                  "day_cap": v.get("day_cap")} for k, v in OS.SOURCES.items()]
        refused_sources = {k: v.get("why") for k, v in OS.REFUSED_SOURCES.items()}
    except Exception as exc:  # noqa: BLE001 -- the page still prints the browser part
        feeds, refused_sources = [], {"error": f"{type(exc).__name__}: {exc}"}
    for f in feeds:                       # the feed hosts, placed in the same kinds
        f["kind"] = next((n for n, d, _ in OPENS_KINDS if _on_any(str(f["host"]), d)),
                         "Official data (feed / API)")
    money = set(BP.MONEY_HOSTS)
    checkout = set(BP.CHECKOUT_HOSTS)
    message = set(BP.MESSAGE_HOSTS)
    other_never = [h for h in WR.NEVER_HOSTS if h not in money | checkout | message]
    robots_seen = []
    try:
        # the SAME root the page is written under (2026-09-30: reading the live
        # ledger here made a tmp-root test flaky whenever the reader wrote a
        # robots record between two regenerations)
        rd = (Path(root) if root else ledger()) / "dowjones" / "robots"
        for fp in sorted(rd.glob("*.json")) if rd.exists() else []:
            try:
                rec = json.loads(fp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            dis = rec.get("disallowed_seen") or rec.get("refused") or None
            robots_seen.append({"host": fp.stem, "read_utc": rec.get("t") or rec.get("fetched_utc"),
                                "note": "robots.txt read once a day; disallowed paths never opened"
                                if dis is None else dis})
    except Exception:  # noqa: BLE001
        robots_seen = []
    return {
        "generated_utc": now.isoformat(timespec="seconds"),
        "browser": {"profile": ", ".join(getattr(_config, "OPENCLAW_DEDICATED_PROFILES", ("muratclaw",))),
                    "kinds": kinds, "unclassified": unclassified,
                    "day_total": int(getattr(_config, "WEB_READER_MAX_PER_DAY", 4000))},
        "feeds": feeds,
        "refused": {
            "money_hosts (banks, brokers, payment, crypto)": sorted(money),
            "checkout_hosts (subscription checkout providers)": sorted(checkout),
            "mail_and_message_hosts": sorted(message),
            "other_never_hosts": sorted(other_never),
            "path_rules": {
                "checkout / payment path (any host)": BP.CHECKOUT_PATH.pattern,
                "store / billing path segment (any host)": BP.PAYMENT_PATH.pattern,
                "host labels refused": sorted(BP.PAYMENT_HOST_LABELS),
                "mail / message path": BP.MESSAGE_PATH.pattern,
                "social write path": BP.SOCIAL_WRITE_PATH.pattern},
            "actions": "no forms, typing, sign-in, posting, messages or payments; a reader "
                       "clicks links only; buttons and text boxes are never touched",
            "sources_not_read": refused_sources},
        "robots_files": robots_seen,
        # the same root as the page too (2026-10-02: reading the LIVE page_log here
        # made the tmp-root no-op-rewrite test fail whenever the running reader
        # logged a checkout frame between two regenerations)
        "checkout_frames_24h": checkout_frames_seen(now, root=root),
    }


def checkout_frames_seen(now: datetime | None = None, *, hours: float = 24.0,
                         root: Path | None = None) -> dict:
    """Checkout / payment frames the pool's sweep logged in the last `hours`
    (`page_log.jsonl`, class PAYWALL_CHECKOUT_FRAME), by the site that carried
    them: {host: {n, providers}}."""
    now = now or datetime.now(timezone.utc)
    base = Path(root) if root else ledger()
    out: dict[str, dict] = {}
    for r in _jsonl(base / "dowjones" / "page_log.jsonl"):
        if r.get("class") != "PAYWALL_CHECKOUT_FRAME":
            continue
        t = _t(r.get("t"))
        if t is None or (now - t).total_seconds() > hours * 3600 or t > now:
            continue
        h = str(r.get("host") or "?").removeprefix("auth.")
        prov = _host(str(r.get("url") or ""))
        d = out.setdefault(h, {"n": 0, "providers": []})
        d["n"] += 1
        if prov and prov not in d["providers"]:
            d["providers"].append(prov)
    return dict(sorted(out.items()))


def render_what_the_reader_opens(w: dict) -> str:
    b = w["browser"]
    L = ["# What the reader opens",
         "",
         f"Generated from the configuration the reader runs with, at {w['generated_utc']} UTC "
         f"(`python -m backend.services.reader_report --what-opens`). Never edited by hand.",
         "",
         f"The reader's browser window is the dedicated Chrome profile `{b['profile']}`. It may "
         f"open ONLY the hosts below, at most {b['day_total']:,} page loads a day in total. "
         "Anything else on that window's screen is either one of these hosts' own frames "
         "(ads, video players, a publisher's subscription offer inside an article) or a "
         "fault to report. A subscription offer frame (for example `buy.tinypass.com`) is "
         "never navigated to: the page carrying it is classed PAYWALL_STUB and the frame is "
         "logged as PAYWALL_CHECKOUT_FRAME in `page_log.jsonl`; a pop-up page on a refused "
         "address is closed.",
         "",
         ""]
    cf = w.get("checkout_frames_24h") or {}
    if cf:
        L += ["Subscription offers seen INSIDE allowed pages in the last 24 h (frames the "
              "site itself loads; never navigated to, never typed into; the site then reads "
              "its fronts only for 6 h): " + "; ".join(
                  f"{h} ({v['n']}: {', '.join(v['providers'])})" for h, v in cf.items()), ""]
    L += ["## 1. Hosts the browser window may open", ""]
    for k in b["kinds"]:
        L.append(f"### {k['kind']}")
        L.append(f"_{k['note']}_")
        L.append("")
        if not k["browser_hosts"]:
            L.append("- none in the browser (read by feed / API only; see section 2)")
        for h in k["browser_hosts"]:
            caps = []
            if h["per_hour"]:
                caps.append(f"{h['per_hour']}/hour")
            if h["per_day"]:
                caps.append(f"{h['per_day']}/day")
            L.append(f"- {h['host']}" + (f" ({', '.join(caps)})" if caps else ""))
        L.append("")
    if b["unclassified"]:
        L += ["### UNCLASSIFIED (on the allowlist, in no kind above: report this)", ""]
        L += [f"- {h}" for h in b["unclassified"]] + [""]
    L += ["## 2. Read by feed or API only (never in a browser window)", ""]
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for f in w["feeds"]:
        by_kind[f["kind"]].append(f)
    for kind in sorted(by_kind):
        L.append(f"### {kind}")
        for f in by_kind[kind]:
            L.append(f"- {f['host']}: {f['source']} ({f['how']}; at most {f['day_cap']} requests/day)")
        L.append("")
    r = w["refused"]
    L += ["## 3. Refused on every path (browser, links, digest asks, feeds)", ""]
    for key in ("money_hosts (banks, brokers, payment, crypto)",
                "checkout_hosts (subscription checkout providers)",
                "mail_and_message_hosts", "other_never_hosts"):
        L.append(f"- **{key}**: " + ", ".join(r[key]))
    L += ["", "Address rules (any host):"]
    for k, v in r["path_rules"].items():
        L.append(f"- {k}: `{v if isinstance(v, str) else ', '.join(v)}`")
    L += ["", f"Actions: {r['actions']}.", "", "Sources looked at and NOT read:"]
    for k, v in r["sources_not_read"].items():
        L.append(f"- {k}: {v}")
    L.append("")
    return "\n".join(L)


def opens_path(root: Path | None = None) -> Path:
    return (Path(root) if root else ledger()) / "dowjones" / "WHAT_THE_READER_OPENS.md"


def write_what_the_reader_opens(root: Path | None = None, now: datetime | None = None) -> Path:
    """Regenerate the check list; the file is rewritten only when its content
    (the generation time aside) changed."""
    p = opens_path(root)
    text = render_what_the_reader_opens(what_the_reader_opens(now, root=root))
    body = text.split("\n", 4)[-1]
    try:
        old = p.read_text(encoding="utf-8")
        if old.split("\n", 4)[-1] == body:
            return p
    except OSError:
        pass
    p.parent.mkdir(parents=True, exist_ok=True)
    DG.atomic_write_text(p, text)
    return p


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--day", default=None)
    ap.add_argument("--lanes-hours", type=float, default=None,
                    help="print pages by budget lane / host / hour over the last N hours (JSON)")
    ap.add_argument("--what-opens", action="store_true",
                    help="regenerate dowjones/WHAT_THE_READER_OPENS.md from the config")
    a = ap.parse_args(argv)
    if a.what_opens:
        print(write_what_the_reader_opens())
        return 0
    if a.lanes_hours:
        now = datetime.now(timezone.utc)
        print(json.dumps(lane_report(now - timedelta(hours=a.lanes_hours), now), indent=1))
        return 0
    print(write_report(a.day))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
