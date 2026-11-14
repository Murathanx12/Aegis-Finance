"""CH-22 -- build, verify and read the ticker hub (`backend/services/ticker_hub.py`).

    python -m scripts.ticker_hub build  [--data-root <optimus dir>] [--out DIR] [--index-days N] [--now ISO]
    python -m scripts.ticker_hub verify [--data-root ...] [--out DIR]
    python -m scripts.ticker_hub show SYMBOL [--days 30] [--tier about|all] [--json]
    python -m scripts.ticker_hub feed [--ticker T] [--sector S] [--source SRC] [--days 30] [--tier about|all]

`build` reads the data root (news corpus, reader page store, world digest cache, forecast
ledger, event store, universe graph, potential universe) and writes ONLY under `--out`
(default `<data-root>/ticker_hub`), as one new generation published atomically. It prints
rows read, the tagged share by method and tier, every source's newest-row age (stale ones
flagged), a shrunk corpus file, and the generation's verify result.

Exit codes: 0 ok; 2 a refusal or a damaged index (corpus missing or unreadable, issuer
table missing, 0 rows in the index, lock held, `verify` problems). `show` exits 2 on an
unknown symbol and on a DEGRADED / NO_INDEX status. No scheduled task calls this yet.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.services import ticker_hub as TH


def _parse(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise SystemExit(f"--now must carry a zone: {s}")
    return d.astimezone(timezone.utc)


def _root(a: argparse.Namespace) -> Path:
    return Path(a.data_root) if a.data_root else TH.default_data_root()


def cmd_build(a: argparse.Namespace) -> int:
    now = _parse(a.now) if a.now else None
    rec = TH.build(_root(a), out=Path(a.out) if a.out else None, now=now, index_days=a.index_days)
    print(f"TICKER_HUB BUILD {rec['built_utc']} generation={rec['generation']} out={rec['out']} "
          f"first_build={rec['first_build']} elapsed={rec['elapsed_s']}s")
    print(f"rows read (new): {rec['rows_read_new']}  tagged: {rec['rows_tagged_new']}  "
          f"untagged: {rec['rows_untagged_new']}  untagged share: {rec['untagged_share_new']}")
    print(f"rows in index: {rec['rows_in_index']}")
    idx = rec.get("tags_by_method_where_tier_index") or {}
    tot = sum(idx.values()) or 1
    print("tags in the index by method/where/tier:")
    for k, n in sorted(idx.items(), key=lambda kv: -kv[1]):
        print(f"  {k:36s} {n:7d} ({n / tot:.1%})")
    print("top tickers by `about` tags: " + ", ".join(f"{t}={n}" for t, n in rec.get("about_top") or []))
    print("per source (new): read / tagged / untagged share")
    for s, v in rec["per_source_new"].items():
        print(f"  {s:34s} {v['read']:7d} {v['tagged']:7d}  {v['untagged_share']}")
    ages = TH.source_ages(rec["newest_per_source"], TH.DA._utc(rec["built_utc"]))
    print("newest row per source (age h / limit h):")
    for x in ages:
        flag = "  STALE" if x["stale"] else ""
        print(f"  {x['source']:34s} {x['newest_utc']}  {x['age_hours']} / {x['limit_hours']:g}{flag}")
    c = rec["counts"]
    if c.get("files_shrunk_reread"):
        print(f"WARNING: {c['files_shrunk_reread']} corpus file(s) were SHORTER than at the last build "
              f"(rewritten); their rows were read again and folded, rows that vanished from the input stay")
    for k in ("universe", "forecasts", "events", "related"):
        if k in rec:
            print(f"{k}: {json.dumps(rec[k], default=str)[:300]}")
    print(f"counts: {json.dumps(c)[:900]}")
    print(f"verify: {rec['verify']['status']} {rec['verify']['problems']}")
    print(f"receipt: {Path(rec['out']) / rec['generation'] / 'latest.json'}")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    root = TH.hub_dir(_root(a), Path(a.out) if a.out else None)
    v = TH.verify(root, full=True)
    print(f"TICKER_HUB VERIFY {root} generation={v.get('generation')} status={v['status']}")
    for p in v["problems"]:
        print(f"  PROBLEM {p}")
    return 0 if v["status"] == "OK" else 2


def _short(r: dict) -> str:
    ev = r.get("event") or {}
    t = r.get("eff_utc") or r.get("first_seen_utc")
    both = f" (collected {r.get('first_seen_utc')})" if r.get("show_both_times") else ""
    return (f"{t}{both} | {r.get('publisher')} ({r.get('source')}) | {r.get('title')} | {r.get('url')} | "
            f"tier={r.get('tier')} tagged_by={','.join(r.get('tagged_by') or [])} copies={r.get('copies')}"
            + (f" | event={ev.get('event_type')}" if ev else ""))


def cmd_show(a: argparse.Namespace) -> int:
    now = _parse(a.now) if a.now else None
    try:
        h = TH.hub(a.symbol, data_root=_root(a), out=Path(a.out) if a.out else None, days=a.days, now=now,
                   tier=a.tier, limit=a.top)
    except KeyError:
        print(f"UNKNOWN_SYMBOL {a.symbol}")
        return 2
    cov = h["coverage"]
    if a.json:
        print(json.dumps(h, indent=1, default=str))
        return 0 if cov["status"] in ("OK", "STALE") else 2
    fc = h["forecasts"]["counts"]
    print(f"{h['ticker']} ({(h['identity'] or {}).get('name')}, sector {(h['identity'] or {}).get('sector')}) "
          f"days={h['days']} tier={a.tier} index={cov['status']} built={cov['index_built_utc']} age_s={cov['index_age_s']}")
    if cov.get("problems"):
        print(f"PROBLEMS {cov['problems']}")
    print(f"stories {cov['n_stories']} from {cov['n_rows']} rows; tier counts (rows) {h['tier_counts']}; "
          f"sources {cov['sources']}; tagged_by {cov['tagged_by']}")
    print(f"forecasts {h['forecasts']['status']} open {fc['open']} resolved {fc['resolved']} void {fc['void']}")
    print(f"calendar {h['calendar'].get('status')} {h['calendar'].get('label')} rows {len(h['calendar'].get('rows') or [])}")
    print(f"events {len(h['events'])}  related {len(h['related'])}")
    print("stale sources: " + ", ".join(f"{x['source']} (newest {x['newest_utc']})" for x in cov.get("stale_sources") or []))
    for r in h["news"][:a.top]:
        print("  " + _short(r))
    return 0 if cov["status"] in ("OK", "STALE") else 2


def cmd_feed(a: argparse.Namespace) -> int:
    try:
        f = TH.feed(data_root=_root(a), out=Path(a.out) if a.out else None, ticker=a.ticker, sector=a.sector,
                    source=a.source, days=a.days, limit=a.limit, tier=a.tier,
                    now=_parse(a.now) if a.now else None)
    except KeyError:
        print(f"UNKNOWN_SYMBOL {a.ticker}")
        return 2
    print(f"feed {f['filters']} days={f['days']} tier={f['tier']} rows {f['n_rows']} "
          f"(stories in scan {f['n_stories_in_scan']}, returned {f['n_returned']}) index={f['coverage']['status']}")
    print("facets ticker: " + ", ".join(f"{x['key']}={x['n']}" for x in f["facets"]["ticker"][:15]))
    print("facets sector: " + ", ".join(f"{x['key']}={x['n']}" for x in f["facets"]["sector"][:10]))
    print("facets source: " + ", ".join(f"{x['key']}={x['n']}" for x in f["facets"]["source"][:15]))
    for r in f["rows"][:a.top]:
        print("  " + _short(r))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.ticker_hub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "verify", "show", "feed"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", default=None)
        p.add_argument("--out", default=None)
        p.add_argument("--now", default=None)
        if name == "build":
            p.add_argument("--index-days", type=int, default=None)
        if name in ("show", "feed"):
            p.add_argument("--days", type=int, default=None)
            p.add_argument("--top", type=int, default=10)
            p.add_argument("--tier", choices=("about", "all"), default="about")
        if name == "show":
            p.add_argument("symbol")
            p.add_argument("--json", action="store_true")
        if name == "feed":
            p.add_argument("--ticker", default=None)
            p.add_argument("--sector", default=None)
            p.add_argument("--source", default=None)
            p.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):        # headlines carry any script; cp1252 consoles refuse them
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        return {"build": cmd_build, "verify": cmd_verify, "show": cmd_show, "feed": cmd_feed}[a.cmd](a)
    except TH.TickerHubRefused as exc:
        print(f"TICKER_HUB REFUSED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
