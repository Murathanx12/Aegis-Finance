"""Chunk J -- the Dow Jones bundle: free feeds, bounded reads, claims.

    python -m scripts.dowjones_pull --feeds                    # 10 RSS feeds, every item
    python -m scripts.dowjones_pull --probe-free               # which DJ pages answer unauthenticated
    python -m scripts.dowjones_pull --handoff --parent-tab t20 --source wsj \\
        --section heard_on_the_street --max 5
    python -m scripts.dowjones_pull --handoff --parent-tab t33 --source barrons \\
        --section stock_picks --max 5
    python -m scripts.dowjones_pull --handoff --parent-tab t32 --source marketwatch \\
        --section analyst_estimates --tickers MU,DKNG,QUBT
    python -m scripts.dowjones_pull --claims                   # today's stored articles -> forecasts
    python -m scripts.dowjones_pull --archive 2026-09-25 ...   # REFUSED while config says OFF

TERMS OF USE -- printed on every browser run:
    Dow Jones ToU 9.4.1: "You shall not access, view, retrieve ... scrape ...
    store, harvest, or otherwise ingest the Services or any Content ... using
    any automated means, ... browser automation tool, ... AI agent or assistant
    ... without our prior written consent."  9.3: stored articles may not be
    used "to develop or operate an automated trading system, or for text or
    data mining".
The browser reads run ONLY with `--handoff` AND the file Murat creates when he
hands the PC over (`config.DOWJONES_HANDOFF_FILE`). That file is his decision
to accept the risk the clause describes on his own subscription; nothing in
this repository creates it. Without it the command refuses (rc 2). The
primary path is the paste inbox (`scripts/digest_ingest.py`), where Murat
reads and this code only files what he pasted.

HOW THE BROWSER IS DRIVEN (see `backend/services/openclaw_client.py`)
* profile `user` = Murat's own Chrome. A new tab is opened only FROM an
  existing MuratClaw (Work) tab (`--parent-tab`, which must be on
  wsj/barrons/marketwatch) with a fixed `window.open(<url>)`, so it inherits
  that profile. The CDP `open` verb is refused (it lands in his MAIN profile).
* Listing -> snapshot -> links chosen FROM the snapshot (never a guessed
  article URL) -> click/navigate -> fixed innerText read -> stored locally.
* >= 20 s between page loads, <= 30/h, <= 120/day, <= `--max-pages` (20) per
  session; the tab this run opened is closed at the end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402
from backend.services import dowjones_claims as DC  # noqa: E402
from backend.services import dowjones_feeds as DF  # noqa: E402
from backend.services import web_reader as WR  # noqa: E402

TOU_SENTENCE = (
    "Dow Jones ToU 9.4.1: no access/scrape/store of the Services 'using any automated "
    "means, ... browser automation tool, ... AI agent or assistant ... without our prior "
    "written consent'; 9.3: stored articles may not be used 'to develop or operate an "
    "automated trading system, or for text or data mining'. Run only because Murat's "
    "HANDOFF_PC file exists; personal research, nothing republished.")

#: source -> section -> (listing URL, article URL regex, column source_id)
SECTIONS: dict[str, dict[str, tuple[str, str, str]]] = {
    "wsj": {
        "heard_on_the_street": (
            "https://www.wsj.com/news/heard-on-the-street",
            r"^https://www\.wsj\.com/(?!news/|market-data|video|podcasts|livecoverage|buyside)"
            r"[a-z-]+/[a-z0-9/-]*-[0-9a-f]{8}(\?|$)",
            "wsj_heard_on_the_street"),
    },
    "barrons": {
        "stock_picks": (
            "https://www.barrons.com/market-data/stocks/stock-picks",
            r"^https://www\.barrons\.com/articles/[a-z0-9-]+-[0-9a-f]{8}(\?|$)",
            "barrons_stock_picks"),
        "big_money_poll": (
            "https://www.barrons.com/topics/big-money-poll",
            r"^https://www\.barrons\.com/articles/[a-z0-9-]+-[0-9a-f]{8}(\?|$)",
            "barrons_big_money_poll"),
    },
    "marketwatch": {
        "analyst_estimates": (
            "https://www.marketwatch.com/investing/stock/{ticker}/analystestimates",
            "", "mw_analyst_estimates"),
    },
}
DEFAULT_MW_TICKERS = ("MU", "DKNG", "QUBT")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _write(rc: dict, name: str) -> Path:
    p = DF.receipts_dir() / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def handoff_ok(path: Path | None = None) -> bool:
    return Path(path or _config.DOWJONES_HANDOFF_FILE).exists()


def default_mw_tickers(cap: int = 10) -> list[str]:
    out = list(DEFAULT_MW_TICKERS)
    try:
        from scripts.source_reads import thematic_tickers
        for t in thematic_tickers():
            if t not in out:
                out.append(t)
    except Exception:  # noqa: BLE001 -- the three named tickers still run
        pass
    return out[:cap]


# ─────────────────────────────── the browser run ────────────────────────────

def run_reads(source: str, section: str, *, parent_tab: str, max_articles: int = 5,
              tickers: list[str] | None = None, max_pages: int = 20,
              profile: str = "user", driver: Any = None, throttle: Any = None,
              progress_path: Path | None = None) -> dict:
    """One bounded reading session in ONE new tab opened from `parent_tab`."""
    if source not in SECTIONS or section not in SECTIONS[source]:
        raise WR.ReaderRefused(f"REFUSED_SECTION: {source}/{section} not in {SECTIONS}")
    listing, pattern, column = SECTIONS[source][section]
    if driver is None:
        from backend.services import openclaw_client as driver  # type: ignore[no-redef]
    thr = throttle or WR.Throttle(WR.throttle_path())
    started = datetime.now(timezone.utc)
    rc: dict[str, Any] = {"receipt": "dowjones_pull.reads", "source": source,
                          "section": section, "column": column, "profile": profile,
                          "parent_tab": parent_tab, "started_utc": started.isoformat(
                              timespec="seconds"), "tou": TOU_SENTENCE, "cost_usd": 0.0,
                          "articles": [], "refusals": []}
    first_url = listing.format(ticker=(tickers or ["MU"])[0].lower())
    reader_lock = WR.acquire_reader_lock()
    try:
        thr.acquire("open_from_tab", host=source + ".com")
        opened = driver.open_from_tab(parent_tab, first_url, profile_name=profile)
    except Exception:
        WR.release_reader_lock(reader_lock)
        raise
    tab = opened["new_tab"]
    rc["tab_opened"] = tab
    rc["attached_to"] = opened.get("attached_to")
    reader = WR.Reader(profile=profile, tab=tab, throttle=thr, driver=driver,
                       max_pages=max_pages, lock=False)
    reader._lock_path = reader_lock
    reader.pages = 1
    reader.log.append({"page": 1, "what": "open_from_tab", "url": first_url,
                       "waited_s": thr.waits[-1] if thr.waits else 0.0,
                       "at": thr.now_fn().isoformat(timespec="seconds")})
    try:
        driver.browser("wait", "--time", "4000", profile_name=profile, target_id=tab)
        if section == "analyst_estimates":
            for i, t in enumerate(tickers or list(DEFAULT_MW_TICKERS)):
                url = listing.format(ticker=t.lower())
                try:
                    art = (_read_current(reader, url, column, t) if i == 0 else
                           reader.read_article(url, column=column))
                    art["ticker"] = t
                    rc["articles"].append(_summary(art))
                except WR.ReaderRefused as exc:
                    rc["refusals"].append({"ticker": t, "why": str(exc)[:200]})
                    if "SESSION_CAP" in str(exc) or "THROTTLE" in str(exc):
                        _progress(rc, reader, progress_path)
                        break
                _progress(rc, reader, progress_path)
        else:
            links = WR.select_links(reader.snapshot(), pattern, limit=max_articles)
            rc["links_found"] = [{"text": lk["text"][:140], "url": lk["url"],
                                  "has_ref": bool(lk["ref"])} for lk in links]
            if not links:
                rc["refusals"].append({"why": "NO_LINKS_ON_LISTING: the snapshot showed no "
                                              "link matching the article pattern"})
            for lk in links[:max_articles]:
                try:
                    rc["articles"].append(_summary(reader.read_article(lk, column=column)))
                except WR.ReaderRefused as exc:
                    rc["refusals"].append({"url": lk["url"], "why": str(exc)[:200]})
                    if "SESSION_CAP" in str(exc) or "THROTTLE" in str(exc) or "LEFT_HOSTS" in str(exc):
                        _progress(rc, reader, progress_path)
                        break
                _progress(rc, reader, progress_path)
    finally:
        try:
            cl = driver.browser("close", profile_name=profile, target_id=tab)
            rc["tab_closed"] = cl.get("rc") == 0
        except Exception as exc:  # noqa: BLE001 -- say it, never hide it
            rc["tab_closed"] = False
            rc["close_error"] = str(exc)[:200]
        fp = reader.close()
        rc["footprint"] = {k: fp.get(k) for k in ("verdict", "cv_of_gaps", "gaps_s",
                                                  "pages_per_hour", "scroll_share", "path")}
    rc["pages"] = reader.log
    gaps = [p["waited_s"] for p in reader.log]
    stamps = [datetime.fromisoformat(p["at"]) for p in reader.log]
    rc["seconds_between_page_loads"] = [round((b - a).total_seconds(), 1)
                                        for a, b in zip(stamps, stamps[1:])]
    rc["throttle_waits_s"] = gaps
    rc["throttle_targets_s"] = list(thr.targets)
    rc["n_articles"] = len(rc["articles"])
    rc["chars_total"] = sum(a["chars"] for a in rc["articles"])
    rc["finished_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return rc


def _progress(rc: dict, reader: WR.Reader, path: Path | None) -> None:
    """The receipt after EVERY page, so a run that is stopped leaves evidence
    (the first live run was stopped and left none)."""
    if path is None:
        return
    rc["pages"] = reader.log
    rc["in_progress"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def _read_current(reader: WR.Reader, url: str, column: str, ticker: str) -> dict:
    """The first MarketWatch page is already loaded by `open_from_tab`; read it
    in place rather than loading it twice."""
    got = reader.driver.read_text(reader.tab, profile_name=reader.profile)
    if got.get("error") or not (got.get("text") or "").strip():
        raise WR.ReaderRefused(f"REFUSED_EMPTY_READ: {url!r}: "
                               f"{(got.get('error') or 'no text returned')[:200]}")
    final = got.get("url") or url
    if not WR.host_ok(final):
        raise WR.ReaderRefused(f"REFUSED_LEFT_HOSTS: {final!r}")
    text = WR.clean_text(got.get("text") or "", got.get("title"))
    art = {"url": final, "title": got.get("title"), "byline": None,
           "published_utc": None, "text": text, "first_seen_utc": DC.now_iso(),
           "chars": len(text), "raw_chars": len(got.get("text") or ""),
           "publisher": "marketwatch", "origin": "web_reader", "tab": reader.tab,
           "profile": reader.profile, "column": column, "tickers": [ticker],
           "paywall_suspected": False, "read_s": 0.0}
    art["sha"] = DC.text_sha(text)
    if text:
        art["stored"] = WR.store_article(art)
    return art


def _summary(art: dict) -> dict:
    return {k: art.get(k) for k in ("url", "title", "byline", "published_utc",
                                    "first_seen_utc", "chars", "raw_chars", "column",
                                    "sha", "paywall_suspected", "read_s", "ticker")} | {
        "stored": (art.get("stored") or {}).get("path"),
        "duplicate": (art.get("stored") or {}).get("duplicate")}


# ────────────────────────────────── claims ──────────────────────────────────

def _done_path() -> Path:
    return WR.corpus_root() / "_claims" / "_extracted.txt"


def stored_articles(day: str, root: Path | None = None) -> list[dict]:
    root = Path(root) if root else WR.corpus_root()
    out = []
    for p in sorted(root.glob(f"*/{day}/*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return out


def run_claims(day: str | None = None, *, cap_usd: float | None = None, llm_fn: Any = None,
               spend_fn: Any = None, ledger_path: Path | None = None,
               claims_path: Path | None = None, root: Path | None = None,
               done_path: Path | None = None) -> dict:
    """Each stored article not yet extracted -> one DeepSeek call -> forecasts.

    The cap is read from the WRITER's ledger (`llm_telemetry.spend` with this
    purpose, since this run started) plus a per-call estimate for the call
    about to be made; an unreadable ledger REFUSES (spend unknown is not zero).
    """
    day = day or _today()
    cap = float(cap_usd if cap_usd is not None else _config.DOWJONES_CLAIMS_CAP_USD)
    est = float(_config.DOWJONES_CLAIMS_EST_USD_PER_ARTICLE)
    purpose = _config.DOWJONES_CLAIMS_PURPOSE
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    dp = Path(done_path) if done_path else _done_path()
    done = set(dp.read_text(encoding="utf-8").split()) if dp.exists() else set()

    def spent() -> float | None:
        if spend_fn is not None:
            return spend_fn()
        from backend.services import llm_telemetry as LT
        s = LT.spend(since=started, purpose=purpose)
        return None if not s else float(s.get("total_cost_usd") or 0.0)

    per, n_calls, stop = [], 0, None
    for art in stored_articles(day, root):
        if art.get("sha") in done:
            continue
        sp = spent()
        if sp is None:
            stop = "REFUSED_SPEND_UNKNOWN: the telemetry ledger could not be read"
            break
        if sp + est > cap:
            stop = f"CAP: spent ${sp:.4f} + est ${est:.4f} > cap ${cap:.2f}"
            break
        ex = DC.extract_claims(art, llm_fn=llm_fn)
        n_calls += ex["status"] not in ("SKIPPED_TOO_SHORT",)
        w = (DC.write_forecasts(art, ex["claims"], ledger_path=ledger_path,
                                claims_path=claims_path)
             if ex["claims"] else {"n_rows_written": 0, "source_id": art.get("column")})
        per.append({"sha": art.get("sha"), "url": art.get("url"), "column": art.get("column"),
                    "status": ex["status"], "n_claims": len(ex["claims"]),
                    "refused": ex["refused"], "tickers": [c["ticker"] for c in ex["claims"]],
                    "directions": [c["direction"] for c in ex["claims"]],
                    "source_id": w.get("source_id"), "forecast_rows": w.get("n_rows_written", 0),
                    "write_status": w.get("status")})
        if ex["status"] != "LLM_NO_REPLY":
            dp.parent.mkdir(parents=True, exist_ok=True)
            with dp.open("a", encoding="utf-8") as fh:
                fh.write(str(art.get("sha")) + "\n")
    final = spent()
    by_src: dict[str, int] = {}
    for r in per:
        by_src[r["source_id"] or "?"] = by_src.get(r["source_id"] or "?", 0) + r["forecast_rows"]
    return {"receipt": "dowjones_pull.claims", "day": day, "started_utc": started,
            "purpose": purpose, "cap_usd": cap, "spent_usd": final, "n_llm_calls": n_calls,
            "stopped": stop, "n_articles": len(per),
            "n_claims": sum(r["n_claims"] for r in per),
            "forecast_rows_by_source_id": by_src,
            "public_safety": "claim_text in git is the model's paraphrase; verbatim quotes stay "
                             "in the gitignored news_corpus/dowjones/_claims/",
            "per_article": per}


# ─────────────────────────────────── main ───────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--feeds", action="store_true")
    ap.add_argument("--probe-free", action="store_true")
    ap.add_argument("--source", choices=sorted(SECTIONS))
    ap.add_argument("--section")
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--tickers", default="")
    ap.add_argument("--parent-tab", default="")
    ap.add_argument("--profile", default="user")
    ap.add_argument("--handoff", action="store_true",
                    help="required for any browser read; refuses unless HANDOFF_PC exists")
    ap.add_argument("--archive", default="")
    ap.add_argument("--claims", action="store_true")
    ap.add_argument("--claims-day", default="")
    a = ap.parse_args(argv)
    out: dict[str, Any] = {}
    rc = 0
    day = _today()

    if a.feeds:
        r = DF.pull_feeds()
        p = _write(r, f"feeds_{day}.json")
        out["feeds"] = {"receipt": str(p), "items_received": r["items_received"],
                        "items_new": r["items_new"], "refused_or_red": r["refused_or_red"],
                        "per_feed": {f["source"]: f["received"] for f in r["per_feed"]}}
    if a.probe_free:
        r = DF.probe_free_surfaces()
        p = _write(r, f"free_surfaces_{day}.json")
        out["probe_free"] = {"receipt": str(p), "answer_200": r["answer_200"],
                             "walled_401_403": r["walled_401_403"], "other": r["other"]}
    if a.archive:
        print(TOU_SENTENCE)
        try:
            d = date.fromisoformat(a.archive)
        except ValueError:
            print(f"REFUSED_ARCHIVE_DATE: {a.archive!r} is not YYYY-MM-DD")
            return 2
        if d >= datetime.now(timezone.utc).date():
            print(f"REFUSED_ARCHIVE_FUTURE: {d} has not finished yet")
            return 2
        if not getattr(_config, "DOWJONES_ARCHIVE_ENABLED", False):
            print("REFUSED_ARCHIVE_OFF: config.DOWJONES_ARCHIVE_ENABLED is False (Murat, "
                  "2026-09-26). The archive days are links in digest_inbox/"
                  "WEEKEND_READING_LIST.md for a human to read instead.")
            return 2
        print("REFUSED_ARCHIVE_NOT_BUILT: enabled in config but not wired; see the doc.")
        return 2
    if a.source:
        print(TOU_SENTENCE, flush=True)
        if not a.handoff or not handoff_ok():
            print(f"REFUSED_NO_HANDOFF: browser reads need --handoff AND "
                  f"{_config.DOWJONES_HANDOFF_FILE} (created by Murat when he hands the "
                  f"PC over). Use scripts/digest_ingest.py for pasted articles.")
            return 2
        if not a.parent_tab or not a.section:
            print("REFUSED: --parent-tab (a MuratClaw wsj/barrons/marketwatch tab) and "
                  "--section are required")
            return 2
        tickers = [t.strip().upper() for t in a.tickers.split(",") if t.strip()] or None
        if a.section == "analyst_estimates" and not tickers:
            tickers = default_mw_tickers()
        stamp = datetime.now(timezone.utc).strftime("%H%M%S")
        rpath = DF.receipts_dir() / f"reads_{day}_{a.source}_{a.section}_{stamp}.json"
        try:
            r = run_reads(a.source, a.section, parent_tab=a.parent_tab,
                          max_articles=a.max, tickers=tickers, max_pages=a.max_pages,
                          profile=a.profile, progress_path=rpath)
        except Exception as exc:  # noqa: BLE001 -- a refusal is a finding, with rc 2
            print(f"REFUSED: {type(exc).__name__}: {exc}")
            _write({"receipt": "dowjones_pull.reads", "source": a.source, "section": a.section,
                    "parent_tab": a.parent_tab, "n_articles": 0,
                    "refused": f"{type(exc).__name__}: {exc}"[:400],
                    "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                   rpath.name)
            return 2
        r["in_progress"] = False
        p = _write(r, rpath.name)
        out["reads"] = {"receipt": str(p), "n_articles": r["n_articles"],
                        "chars_total": r["chars_total"], "tab": r.get("tab_opened"),
                        "tab_closed": r.get("tab_closed"),
                        "seconds_between_page_loads": r["seconds_between_page_loads"],
                        "refusals": r["refusals"]}
        rc = 0 if r["n_articles"] else 2
    if a.claims:
        r = run_claims(a.claims_day or None)
        p = _write(r, f"claims_{a.claims_day or day}_{datetime.now(timezone.utc):%H%M%S}.json")
        out["claims"] = {"receipt": str(p), "n_articles": r["n_articles"],
                         "n_claims": r["n_claims"], "spent_usd": r["spent_usd"],
                         "rows": r["forecast_rows_by_source_id"], "stopped": r["stopped"]}
    if not out and rc == 0:
        ap.print_help()
        return 2
    print(json.dumps(out, indent=1, default=str))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
