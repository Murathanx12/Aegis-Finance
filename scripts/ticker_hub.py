"""CH-22 -- build and read the ticker hub (`backend/services/ticker_hub.py`).

    python -m scripts.ticker_hub build [--data-root <optimus dir>] [--out DIR] [--index-days N] [--now ISO]
    python -m scripts.ticker_hub show SYMBOL [--data-root ...] [--out DIR] [--days 30] [--json]
    python -m scripts.ticker_hub feed [--ticker T] [--sector S] [--source SRC] [--days 30] [--limit 50]

`build` reads the data root (news corpus, reader page store, world digest cache, forecast
ledger, event store, universe graph, potential universe) and writes ONLY under `--out`
(default `<data-root>/ticker_hub`). Incremental: a second run reads only what is new.
It prints rows read, the tagged share by method and by source, and the newest row per
source.

Exit codes: 0 ok; 2 a refusal (corpus missing or unreadable, issuer table missing,
0 rows in the index, another build holding the lock). No scheduled task calls this yet:
the brain registers one by hand.
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
    print(f"TICKER_HUB BUILD {rec['built_utc']} out={rec['out']} first_build={rec['first_build']} "
          f"elapsed={rec['elapsed_s']}s")
    print(f"rows read (new): {rec['rows_read_new']}  tagged: {rec['rows_tagged_new']}  "
          f"untagged: {rec['rows_untagged_new']}  untagged share: {rec['untagged_share_new']}")
    print(f"rows in index (all builds): {rec['rows_in_index']}")
    tot = sum(rec["tags_by_method_new"].values()) or 1
    print("tags by method (new rows): " + ", ".join(
        f"{m}={n} ({n / tot:.1%})" for m, n in sorted(rec["tags_by_method_new"].items(), key=lambda kv: -kv[1])))
    print("per source (new): read / tagged / untagged share")
    for s, v in rec["per_source_new"].items():
        print(f"  {s:34s} {v['read']:7d} {v['tagged']:7d}  {v['untagged_share']}")
    print("newest row per source:")
    for s, t in rec["newest_per_source"].items():
        print(f"  {s:34s} {t}")
    for k in ("universe", "forecasts", "events", "related"):
        if k in rec:
            print(f"{k}: {json.dumps(rec[k], default=str)[:300]}")
    print(f"counts: {json.dumps(rec['counts'])[:600]}")
    print(f"receipt: {Path(rec['out']) / 'latest.json'}")
    return 0


def _short(r: dict) -> str:
    ev = r.get("event") or {}
    return (f"{r.get('first_seen_utc')} | {r.get('publisher')} ({r.get('source')}) | {r.get('title')} | "
            f"{r.get('url')} | tagged_by={','.join(r.get('tagged_by') or [])}"
            + (f" | event={ev.get('event_type')}" if ev else ""))


def cmd_show(a: argparse.Namespace) -> int:
    now = _parse(a.now) if a.now else None
    try:
        h = TH.hub(a.symbol, data_root=_root(a), out=Path(a.out) if a.out else None, days=a.days, now=now)
    except KeyError:
        print(f"UNKNOWN_SYMBOL {a.symbol}")
        return 2
    if a.json:
        print(json.dumps(h, indent=1, default=str))
        return 0
    cov = h["coverage"]
    fc = h["forecasts"]["counts"]
    print(f"{h['ticker']} ({(h['identity'] or {}).get('name')}, sector {(h['identity'] or {}).get('sector')}) "
          f"days={h['days']} index={cov['status']} built={cov['index_built_utc']} age_s={cov['index_age_s']}")
    print(f"news {cov['n_rows']} (returned {cov['n_returned']}); sources {cov['sources']}; tagged_by {cov['tagged_by']}")
    print(f"forecasts open {fc['open']} resolved {fc['resolved']} void {fc['void']} mean_brier {fc.get('mean_brier')}")
    print(f"calendar {h['calendar'].get('status')} {h['calendar'].get('label')} rows {len(h['calendar'].get('rows') or [])}")
    print(f"events {len(h['events'])}  related {len(h['related'])}")
    for r in h["news"][:a.top]:
        print("  " + _short(r))
    return 0


def cmd_feed(a: argparse.Namespace) -> int:
    try:
        f = TH.feed(data_root=_root(a), out=Path(a.out) if a.out else None, ticker=a.ticker, sector=a.sector,
                    source=a.source, days=a.days, limit=a.limit,
                    now=_parse(a.now) if a.now else None)
    except KeyError:
        print(f"UNKNOWN_SYMBOL {a.ticker}")
        return 2
    print(f"feed {f['filters']} days={f['days']} rows {f['n_rows']} (returned {f['n_returned']}) "
          f"index={f['coverage']['status']}")
    print("facets ticker: " + ", ".join(f"{x['key']}={x['n']}" for x in f["facets"]["ticker"][:15]))
    print("facets sector: " + ", ".join(f"{x['key']}={x['n']}" for x in f["facets"]["sector"][:10]))
    print("facets source: " + ", ".join(f"{x['key']}={x['n']}" for x in f["facets"]["source"][:15]))
    for r in f["rows"][:a.top]:
        print("  " + _short(r))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.ticker_hub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("build", "show", "feed"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", default=None)
        p.add_argument("--out", default=None)
        p.add_argument("--now", default=None)
        if name == "build":
            p.add_argument("--index-days", type=int, default=None)
        else:
            p.add_argument("--days", type=int, default=None)
            p.add_argument("--top", type=int, default=10)
        if name == "show":
            p.add_argument("symbol")
            p.add_argument("--json", action="store_true")
        if name == "feed":
            p.add_argument("--ticker", default=None)
            p.add_argument("--sector", default=None)
            p.add_argument("--source", default=None)
            p.add_argument("--limit", type=int, default=50)
    a = ap.parse_args(argv)
    try:
        return {"build": cmd_build, "show": cmd_show, "feed": cmd_feed}[a.cmd](a)
    except TH.TickerHubRefused as exc:
        print(f"TICKER_HUB REFUSED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
