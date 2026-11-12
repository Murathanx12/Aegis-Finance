"""CH-14a -- news and fresh filings ADD names to the opportunity funnel.

The funnel (`opportunity_funnel`) took no name from news: of 30 top idiosyncratic
movers on 2026-11-11, 18 were in the universe and never became a candidate, and 3
of those had a fresh overnight 8-K before the open. This module turns two local,
already-collected inputs into names the funnel must CONSIDER:

    news    the newest world digest (`optimus/digest/world_digest_*.json`): each
            theme's `top_tickers` and every typed ticker implication that the
            digest did not refuse (SOCIAL_ONLY is refused)
    filing  8-K / 8-K/A rows of `optimus/official/tables/filing_events.jsonl`
            with a mapped ticker, public after the previous US close and before
            the next open (weekday clock; exchange holidays are NOT modelled)

What a news name may and may not do (`admit`):
  * it passes stage 0 (listed common stock / ADR), every stage-1 eligibility
    screen (`opportunity_funnel.eligibility`) and the stage-3 fundamentals
    requirement, exactly as any other name; a failure is reported by screen name
  * it sets no weight and changes no score; the ranker's own top-25 is computed
    first, unchanged, and a news name enters the final list through at most
    `FUNNEL_NEWS_MAX_FINAL_SLOTS` reserved slots, displacing the lowest-ranked
    ranker-only names (listed on the receipt)

Freshness is judged on CONTENT: a digest with zero typed implications is EMPTY
whatever any `fresh` flag says; one older than FUNNEL_NEWS_DIGEST_MAX_AGE_HOURS
(from its own as_of, never mtime) is STALE. Either contributes zero names and the
receipt carries a degradation line. No look-ahead: a digest whose stamp or as_of
is after the build time, or a filing public or first seen after it, is refused
and counted; the stamp used is recorded per name.

No LLM, no network. Off by default (`config.FUNNEL_NEWS_SOURCE_ENABLED`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from backend import config as _cfg

SOURCE_RANKER = "ranker"
SOURCE_NEWS = "news"
SOURCE_FILING = "filing"
NEWS_SOURCES = (SOURCE_NEWS, SOURCE_FILING)

FILING_FORMS = frozenset({"8-K", "8-K/A"})
_STAMP = re.compile(r"(\d{8}T\d{6}Z)")


# ─────────────────────────────── small helpers ──────────────────────────────

def _to_dt(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        m = _STAMP.search(str(ts))
        if not m:
            return None
        t = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ")
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _iso(t: Optional[datetime]) -> Optional[str]:
    return t.astimezone(timezone.utc).isoformat(timespec="seconds") if t else None


def _ticker_ok(sym: str) -> bool:
    from backend.services.world_digest import _TICKER   # the digest's own rule
    return bool(_TICKER.match(sym))


def _issuer_id(sym: str) -> str:
    from backend.services.universe_graph import company_id  # the graph's node id
    return company_id(sym)


def digest_dir() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / "digest"


def filings_path() -> Path:
    return Path(_cfg.OPTIMUS_LEDGER_DIR) / "official" / "tables" / "filing_events.jsonl"


# ─────────────────────────────── news (digest) ──────────────────────────────

def digest_names(build_time: datetime, *, root: Optional[Path] = None,
                 max_age_hours: Optional[float] = None) -> dict:
    """Names from the newest digest stamped before `build_time`, judged on content."""
    d = Path(root) if root else digest_dir()
    max_age = float(_cfg.FUNNEL_NEWS_DIGEST_MAX_AGE_HOURS if max_age_hours is None
                    else max_age_hours)
    out: dict = {"dir": str(d), "digest_id": None, "as_of": None, "age_hours": None,
                 "n_themes": 0, "n_typed_rows": 0, "n_ticker_rows": 0,
                 "refused_after_build": [], "status": "MISSING", "names": {}}
    files = sorted(d.glob("world_digest_*.json")) if d.exists() else []
    if not files:
        out["degradation"] = f"NEWS_DIGEST_MISSING: no world_digest_*.json under {d}"
        return out
    chosen = None
    for fp in reversed(files):
        stamp = _to_dt(fp.stem.removeprefix("world_digest_"))
        if stamp is None:
            continue
        if stamp > build_time:
            out["refused_after_build"].append(fp.stem.removeprefix("world_digest_"))
            continue
        try:
            got = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(got, dict) or got.get("dry_run") or got.get("themes") is None:
            continue
        as_of = _to_dt((got.get("world_state") or {}).get("as_of")) or stamp
        if as_of > build_time:        # stamped before, finished after: still the future
            out["refused_after_build"].append(fp.stem.removeprefix("world_digest_"))
            continue
        chosen = (fp, got, as_of)
        break
    if chosen is None:
        out["degradation"] = (f"NEWS_DIGEST_MISSING: no usable digest at or before "
                              f"{_iso(build_time)} ({len(out['refused_after_build'])} refused "
                              f"as after build time)")
        return out
    fp, got, as_of = chosen
    themes = got.get("themes") or []
    names: dict[str, dict] = {}
    n_typed = n_tick = 0
    for th in themes:
        title = str(th.get("title") or "")[:120]
        for t in th.get("top_tickers") or []:
            t = str(t).upper().strip()
            if _ticker_ok(t):
                n_tick += 1
                names.setdefault(t, []).append({"via": "top_ticker", "theme": title})
        for imp in th.get("implications") or []:
            n_typed += 1
            if imp.get("subject_type") != "ticker" or imp.get("refused"):
                continue
            t = str(imp.get("subject") or "").upper().strip()
            if _ticker_ok(t):
                n_tick += 1
                names.setdefault(t, []).append(
                    {"via": "implication", "theme": title, "direction": imp.get("direction"),
                     "order": imp.get("order")})
    age_h = round((build_time - as_of).total_seconds() / 3600.0, 2)
    did = str(got.get("stamp") or fp.stem.removeprefix("world_digest_"))
    out.update({"digest_id": did, "path": str(fp), "as_of": _iso(as_of), "age_hours": age_h,
                "n_themes": len(themes), "n_typed_rows": n_typed, "n_ticker_rows": n_tick,
                "fresh_flag_ignored": got.get("fresh")})
    if n_typed == 0:
        out["status"] = "EMPTY"
        out["degradation"] = (f"NEWS_DIGEST_EMPTY: digest {did} has 0 typed implications "
                              f"({len(themes)} themes) -- contributes 0 names whatever its "
                              f"`fresh` flag says")
        return out
    if age_h > max_age:
        out["status"] = "STALE"
        out["degradation"] = (f"NEWS_DIGEST_STALE: digest {did} is {age_h:.1f} h old "
                              f"(> {max_age:g} h) -- contributes 0 names")
        return out
    out["status"] = "FRESH"
    out["names"] = {t: [dict(e, source=SOURCE_NEWS, digest_id=did, stamp_used=_iso(as_of))
                        for e in ev] for t, ev in sorted(names.items())}
    return out


# ─────────────────────────────── filings (8-K) ──────────────────────────────

def overnight_window(build_time: datetime) -> tuple[datetime, datetime]:
    """(previous US close, min(build_time, next open)) in UTC; weekdays only."""
    import pandas as pd
    et = pd.Timestamp(build_time).tz_convert("America/New_York")
    close = et.normalize() + pd.Timedelta(hours=16)
    while close > et or close.weekday() >= 5:
        close = (close - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=16)
    nxt = close.normalize() + pd.Timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt = nxt + pd.Timedelta(days=1)
    open_ = nxt + pd.Timedelta(hours=9, minutes=30)
    end = min(et, open_)
    return (close.tz_convert("UTC").to_pydatetime(), end.tz_convert("UTC").to_pydatetime())


def filing_names(build_time: datetime, *, path: Optional[Path] = None) -> dict:
    """8-K filers public inside the overnight window and knowable by build time."""
    p = Path(path) if path else filings_path()
    start, end = overnight_window(build_time)
    out: dict = {"path": str(p), "window_utc": [_iso(start), _iso(end)],
                 "window_note": "weekday clock; exchange holidays not modelled",
                 "n_8k_rows": 0, "n_8k_with_ticker": 0, "newest_8k_public": None,
                 "refused_after_build": 0, "n_in_window": 0, "status": "MISSING",
                 "names": {}}
    if not p.exists():
        out["degradation"] = f"FILINGS_MISSING: {p} does not exist"
        return out
    names: dict[str, list] = {}
    newest = None
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if str(r.get("form_type") or "") not in FILING_FORMS:
                continue
            out["n_8k_rows"] += 1
            t = str(r.get("ticker") or "").upper().strip()
            pub = _to_dt(r.get("public_utc"))
            if not t or pub is None:
                continue
            out["n_8k_with_ticker"] += 1
            seen = _to_dt(r.get("first_seen_utc")) or pub
            knowable = max(pub, seen)
            if pub > build_time or knowable > build_time:
                out["refused_after_build"] += 1
                continue
            newest = pub if newest is None or pub > newest else newest
            if not (start < pub <= end) or not _ticker_ok(t):
                continue
            out["n_in_window"] += 1
            names.setdefault(t, []).append(
                {"source": SOURCE_FILING, "via": str(r.get("form_type")),
                 "accession": r.get("accession"), "items": list(r.get("items") or [])[:8],
                 "public_utc": _iso(pub), "first_seen_utc": _iso(seen),
                 "stamp_used": _iso(knowable)})
    out["newest_8k_public"] = _iso(newest)
    out["names"] = dict(sorted(names.items()))
    if names:
        out["status"] = "FRESH"
    else:
        out["status"] = "NONE_IN_WINDOW"
        out["degradation"] = (f"FILINGS_NONE_IN_WINDOW: 0 mapped 8-Ks public in "
                              f"({_iso(start)}, {_iso(end)}]; newest knowable 8-K public at "
                              f"{_iso(newest)}")
    return out


# ─────────────────────────────── collect + admit ────────────────────────────

def collect(build_time: datetime, *, digest_root: Optional[Path] = None,
            filings: Optional[Path] = None, filings_enabled: Optional[bool] = None,
            max_age_hours: Optional[float] = None) -> dict:
    """Every name news/filings offer, with its sources, evidence and stamp used."""
    dg = digest_names(build_time, root=digest_root, max_age_hours=max_age_hours)
    use_f = bool(_cfg.FUNNEL_NEWS_FILINGS_ENABLED if filings_enabled is None
                 else filings_enabled)
    fl = filing_names(build_time, path=filings) if use_f else {
        "status": "OFF", "names": {}, "degradation": None}
    per: dict[str, dict] = {}
    for block in (dg, fl):
        for t, ev in (block.get("names") or {}).items():
            row = per.setdefault(t, {"issuer_id": _issuer_id(t), "sources": [], "evidence": []})
            for e in ev:
                if e["source"] not in row["sources"]:
                    row["sources"].append(e["source"])
                row["evidence"].append(e)
    for row in per.values():
        row["sources"] = [s for s in NEWS_SOURCES if s in row["sources"]]
    degr = [b["degradation"] for b in (dg, fl) if b.get("degradation")]
    dg_pub = {k: v for k, v in dg.items() if k != "names"}
    fl_pub = {k: v for k, v in fl.items() if k != "names"}
    dg_pub["n_names"] = len(dg.get("names") or {})
    fl_pub["n_names"] = len(fl.get("names") or {})
    return {"build_time": _iso(build_time), "digest": dg_pub, "filings": fl_pub,
            "names": dict(sorted(per.items())), "degradations": degr}


def _priority(t: str, names: dict) -> tuple:
    """Order among news names when a cap binds: more evidence rows first, then
    filings-and-news, then ticker. A tie-break for admission, never a weight."""
    row = names[t]
    return (-len(row["evidence"]), -len(row["sources"]), t)


ScreenFn = Callable[[list], dict]        # names -> {ticker: (Candidate|None, screen)}
EnrichFn = Callable[[list], list]        # Candidates -> enriched Candidates


def admit(news: dict, ranker_s3: list, ranker_s4: list, *, universe: Iterable[str],
          screen_fn: ScreenFn, enrich_fn: EnrichFn, stage4_keep: int,
          max_enrich: Optional[int] = None, max_final_slots: Optional[int] = None) -> dict:
    """Merge news/filing names into the funnel's stage-3 and final lists.

    `ranker_s3` / `ranker_s4` are the ranker's own lists, computed first and
    unchanged. Returns {"stage3": [...], "final": [...], "receipt": {...}}; every
    Candidate in both lists carries `sources`.
    """
    names: dict = news.get("names") or {}
    max_enrich = int(_cfg.FUNNEL_NEWS_MAX_ENRICH if max_enrich is None else max_enrich)
    max_slots = int(_cfg.FUNNEL_NEWS_MAX_FINAL_SLOTS if max_final_slots is None
                    else max_final_slots)
    uni = set(universe)
    s3_by = {c.ticker: c for c in ranker_s3}
    s4_set = {c.ticker for c in ranker_s4}
    dropped: dict[str, str] = {}

    need = [t for t in names if t not in s3_by]
    not_uni = [t for t in need if t not in uni]
    for t in not_uni:
        dropped[t] = "stage0_universe"
    screened = screen_fn([t for t in need if t in uni]) if need else {}
    passed = []
    for t in [t for t in need if t in uni]:
        cand, screen = screened.get(t, (None, "no_price_history"))
        if cand is None:
            dropped[t] = screen or "no_price_history"
        else:
            passed.append(cand)
    passed.sort(key=lambda c: _priority(c.ticker, names))
    for c in passed[max_enrich:]:
        dropped[c.ticker] = "news_enrich_cap"
    to_enrich = passed[:max_enrich]
    enriched = enrich_fn(to_enrich) if to_enrich else []
    got = {c.ticker for c in enriched}
    for c in to_enrich:
        if c.ticker not in got:
            dropped[c.ticker] = "stage3_fundamentals"

    def tag(c: Any, ranker: bool) -> Any:
        row = names.get(c.ticker)
        srcs = ([SOURCE_RANKER] if ranker else []) + (row["sources"] if row else [])
        c.sources = srcs
        if row:
            c.news_evidence = row["evidence"][:6]
        return c

    stage3 = [tag(c, True) for c in ranker_s3] + [tag(c, False) for c in enriched]

    # final: ranker's own order first; news names not already in it compete for
    # the reserved slots (enriched news-only names + news names the ranker kept at
    # stage 3 but cut at stage 4).
    pool = [c for c in stage3 if c.ticker in names and c.ticker not in s4_set]
    pool.sort(key=lambda c: _priority(c.ticker, names))
    reserved = pool[:max_slots]
    for c in pool[max_slots:]:
        dropped[c.ticker] = "final_slot_cap"
    keep_ranker = max(0, min(len(ranker_s4), stage4_keep - len(reserved)))
    displaced = [c.ticker for c in ranker_s4[keep_ranker:]]
    final = [tag(c, True) for c in ranker_s4[:keep_ranker]]
    for c in reserved:
        c.sources = [s for s in c.sources if s != SOURCE_RANKER]
        c.why.append("news source (CH-14a): admitted to a reserved final slot after "
                     "passing the stage-0/1 screens and the stage-3 fundamentals "
                     "requirement; its score was not changed")
        final.append(c)

    def has_news(c: Any) -> bool:
        return any(s in NEWS_SOURCES for s in getattr(c, "sources", []))

    by_screen: dict[str, list] = {}
    for t, s in sorted(dropped.items()):
        by_screen.setdefault(s, []).append(t)
    n_news_final = sum(1 for c in final if has_news(c))
    n_only = sum(1 for c in final if SOURCE_RANKER not in c.sources)
    receipt = {
        "offered": {"total": len(names),
                    "news": sum(1 for r in names.values() if SOURCE_NEWS in r["sources"]),
                    "filing": sum(1 for r in names.values() if SOURCE_FILING in r["sources"]),
                    "already_in_ranker_stage3": sorted(set(names) & set(s3_by))},
        "screened_by_funnel": len([t for t in need if t in uni]),
        "passed_stage1": len(passed), "enriched_stage3": len(enriched),
        "dropped": dict(sorted(dropped.items())), "dropped_by_screen": by_screen,
        "stage3": {"n": len(stage3), "ranker": len(ranker_s3), "news_added": len(enriched),
                   "names": [{"ticker": c.ticker, "sources": c.sources} for c in stage3]},
        "final": {"n": len(final), "news_names": n_news_final,
                  "entered_only_by_news_or_filing": n_only,
                  "news_share": round(n_news_final / len(final), 4) if final else None,
                  "news_share_note": (f"{n_news_final} of {len(final)} final names carry a "
                                      f"news/filing source; {len(names)} names were offered"),
                  "displaced_ranker_names": displaced,
                  "names": [{"ticker": c.ticker, "sources": c.sources} for c in final]},
        "max_enrich": max_enrich, "max_final_slots": max_slots,
    }
    return {"stage3": stage3, "final": final, "receipt": receipt}


# ───────────────────── offline replay (no network) ───────────────────────────
#
# The live funnel needs Finnhub + yfinance. The replay rebuilds ONLY what can be
# rebuilt offline and says which stage was reused: the ranker's lists come from
# a stored snapshot (only stage 4 is stored, so the snapshot's 25 stand in for
# the ranker's stage 3 as well), stage-0 from the cached symbol list, stage-1
# screens from the local daily bars (dates before the build day), and stage-3
# fundamentals from local SEC facts filed before the build time (live uses
# Finnhub / yfinance, so the replay's fundamentals source differs and is named).

def _bars_screen(bars: Path, as_of: datetime) -> ScreenFn:
    import pandas as pd
    from backend.services import opportunity_funnel as F

    def fn(names: list) -> dict:
        if not names:
            return {}
        df = pd.read_parquet(bars, columns=["symbol", "date", "close", "volume"],
                             filters=[("symbol", "in", list(names))])
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"].dt.date < as_of.date()]
        df = df[df["date"] >= df["date"].max() - pd.Timedelta(days=366)] if len(df) else df
        close = df.pivot_table(index="date", columns="symbol", values="close")
        vol = df.pivot_table(index="date", columns="symbol", values="volume")
        return {t: F.eligibility(t, close, vol) for t in names}
    return fn


def _sec_enrich(facts: Path, as_of: datetime) -> EnrichFn:
    import pandas as pd

    def fn(cands: list) -> list:
        if not cands:
            return []
        want = [c.ticker for c in cands]
        df = pd.read_parquet(facts, columns=["ticker", "fact", "filed", "period_days", "val"],
                             filters=[("ticker", "in", want),
                                      ("fact", "in", ["revenue", "cogs", "assets"])])
        df = df[pd.to_datetime(df["filed"]) < pd.Timestamp(as_of.date())]
        out = []
        for c in cands:
            g = df[df["ticker"] == c.ticker].sort_values("filed")
            ann = g[g["period_days"].between(350, 380)]
            rev, cogs = ann[ann.fact == "revenue"], ann[ann.fact == "cogs"]
            assets = g[g.fact == "assets"]
            if rev.empty or cogs.empty or assets.empty or not assets["val"].iloc[-1]:
                continue
            c.quality = float(rev["val"].iloc[-1] - cogs["val"].iloc[-1]) / float(assets["val"].iloc[-1])
            c.stage = 3
            c.why.append(f"gross profitability {c.quality:.2f} (REPLAY: local SEC facts filed "
                         f"before {as_of.date()}, standing in for the live Finnhub/yfinance call)")
            out.append(c)
        return out
    return fn


def _sha(p: Path) -> Optional[str]:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else None


def _live_state(data_root: Path) -> dict:
    """What the replay must never change: the live snapshot and its history."""
    snap = data_root / "funnel_night10.json"
    hist = data_root / "funnel_history"
    return {"funnel_snapshot_sha": _sha(snap),
            "funnel_history_files": len(list(hist.glob("*"))) if hist.exists() else 0}


def replay(as_of: datetime, *, data_root: Path, snapshot: Path, out_dir: Path
           ) -> tuple[dict, int]:
    from backend.services import opportunity_funnel as F

    snap = json.loads(Path(snapshot).read_text(encoding="utf-8"))
    gen = _to_dt(snap.get("generated_at"))
    if gen is None or gen > as_of:
        print(f"REFUSED: snapshot generated_at {snap.get('generated_at')} is not before "
              f"the build time {_iso(as_of)} (look-ahead)")
        return {}, 2
    fields = set(F.Candidate.__dataclass_fields__)
    s4 = [F.Candidate(**{k: v for k, v in c.items() if k in fields})
          for c in snap.get("candidates") or []]
    uni_p = data_root / "funnel_cache" / "universe.json"
    uni = json.loads(uni_p.read_text(encoding="utf-8"))
    opt = data_root / "optimus"
    fil = opt / "official" / "tables" / "filing_events.jsonl"
    bars = opt / "prices_2025_26" / "bars.parquet"
    facts = opt / "fundamentals_sec" / "sec_facts_history.parquet"
    news = collect(as_of, digest_root=opt / "digest", filings=fil)
    res = admit(news, list(s4), list(s4), universe=uni["tickers"],
                screen_fn=_bars_screen(bars, as_of), enrich_fn=_sec_enrich(facts, as_of),
                stage4_keep=F.STAGE4_KEEP)
    payload = {
        "schema": "funnel_news_replay/v1", "build_time": _iso(as_of),
        "recomputed": ["news/filing names (digest + filing_events)",
                       "stage-0 membership of news names (cached universe.json)",
                       "stage-1 screens of news names (local bars, dates < build day)",
                       "stage-3 fundamentals of news names (local SEC facts; live uses Finnhub)",
                       "final-list merge"],
        "reused": {"ranker_stage4": {"path": str(snapshot), "generated_at": snap.get("generated_at"),
                                     "n": len(s4), "stages": snap.get("stages")},
                   "ranker_stage3": "NOT STORED on the snapshot: the 25 stand in for the 40",
                   "universe": {"path": str(uni_p), "n": uni.get("n"),
                                "fetched_at": uni.get("fetched_at")}},
        "inputs": {str(p): {"bytes": p.stat().st_size if p.exists() else None}
                   for p in (bars, facts, fil, uni_p)},
        "news_source": {**{k: v for k, v in news.items() if k != "names"},
                        "per_name": news["names"], **res["receipt"]},
        "candidates": [c.to_dict() for c in res["final"]],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y%m%dT%H%M%SZ")
    fp = out_dir / f"funnel_news_replay_{stamp}.json"
    tmp = fp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    tmp.replace(fp)
    payload["_written"] = str(fp)
    return payload, 0


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="CH-14a offline replay: which names news and "
                                             "filings add to a stored funnel snapshot.")
    ap.add_argument("--as-of", required=True, help="build time, ISO UTC")
    ap.add_argument("--data-root", default=str(Path(_cfg.BACKEND_DIR) / "data"),
                    help="the backend/data folder to READ (never written)")
    ap.add_argument("--snapshot", default=None, help="default <data-root>/funnel_night10.json")
    ap.add_argument("--out", required=True, help="output directory (never the data folder)")
    a = ap.parse_args(argv)
    as_of = _to_dt(a.as_of)
    root = Path(a.data_root).resolve()
    out_dir = Path(a.out).resolve()
    if as_of is None or out_dir == root or root in out_dir.parents:
        print("REFUSED: --as-of unparsable or --out inside the data folder")
        return 2
    before = _live_state(root)
    payload, rc = replay(as_of, data_root=root,
                         snapshot=Path(a.snapshot) if a.snapshot else root / "funnel_night10.json",
                         out_dir=out_dir)
    after = _live_state(root)
    print(f"live state before {before}")
    print(f"live state after  {after}")
    if rc:
        return rc
    ns = payload["news_source"]
    dg = ns["digest"]
    print(f"digest {dg.get('digest_id')} age {dg.get('age_hours')} h typed rows "
          f"{dg.get('n_typed_rows')} status {dg.get('status')}; filings {ns['filings'].get('status')} "
          f"in window {ns['filings'].get('n_in_window')}")
    for d in ns["degradations"]:
        print(f"DEGRADED: {d}")
    print(f"offered {ns['offered']['total']} (news {ns['offered']['news']}, filing "
          f"{ns['offered']['filing']}); passed stage1 {ns['passed_stage1']}; enriched "
          f"{ns['enriched_stage3']}; final {ns['final']['news_share_note']}; only-by-news "
          f"{ns['final']['entered_only_by_news_or_filing']}")
    for s, ts in ns["dropped_by_screen"].items():
        print(f"  dropped by {s}: {len(ts)} {ts[:12]}")
    print(f"-> {payload['_written']}")
    return 1 if before != after else 0


if __name__ == "__main__":
    sys.exit(main())
