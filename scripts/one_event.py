"""One event end to end (ROADMAP CH-31). See `backend/services/one_event.py`.

    python -m scripts.one_event list  --data-root <optimus dir> [--hours 48] [--source S ...]
    python -m scripts.one_event run   --data-root <optimus dir> --source <corpus dir> --key <raw_id|url|accession>
                                      [--ticker T] [--direction up|down] [--graph-dir G]
                                      [--out DIR] [--now ISO] [--no-write]
    python -m scripts.one_event grade --data-root <optimus dir> [--out DIR] [--now ISO]

`run` prints one table and writes one receipt under `<out>/receipts/`; exit 2
when a stage is BLOCKED for a reason other than the intended
ATTENDED_ACTIVATION_REQUIRED. Nothing is sent, no order is placed, no LLM is
called. `--out` defaults to `<data-root>/one_event`, so with `--data-root` set
to the runtime it WRITES INTO the runtime: pass `--out` to keep a worktree's
rows out of it. `--no-write` writes NOTHING, neither a forecast row nor the
receipt (the table is printed only): until 2026-11-11 it held back the forecast
rows and still wrote the receipt, so a look at the runtime's data left a file in
it. `--now` moves the visibility clock only; every forecast row
also carries the real write time, and a row whose `--now` is not the wall clock
is a REPLAY row the grader never counts as forward evidence.
`list` exits 2 when there is no corpus; `grade` exits 2 when nothing could be
graded or is pending (no ledger, or every row refused / ungradeable).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                                   # noqa: E402
from backend.services import one_event as OE                         # noqa: E402


def _now(s: str | None) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    d = OE._utc(s)
    if d is None:
        raise SystemExit(f"--now must be an aware ISO timestamp, got {s!r}")
    return d


def _out(a: argparse.Namespace) -> Path:
    return Path(a.out) if a.out else Path(a.data_root) / "one_event"


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")          # type: ignore[union-attr]
        except Exception:                                            # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(prog="one_event")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "run", "grade"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", default=str(_cfg.OPTIMUS_LEDGER_DIR))
        p.add_argument("--out", default=None)
        p.add_argument("--now", default=None)
        if name == "list":
            p.add_argument("--hours", type=float, default=48.0)
            p.add_argument("--source", action="append", default=None)
            p.add_argument("--limit", type=int, default=60)
        if name == "run":
            p.add_argument("--source", required=True)
            p.add_argument("--key", required=True)
            p.add_argument("--ticker", default=None)
            p.add_argument("--direction", choices=("up", "down"), default=None)
            p.add_argument("--graph-dir", default=None)
            p.add_argument("--funnel", default=None)
            p.add_argument("--positions", default=None)
            p.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    now = _now(a.now)
    if a.cmd == "list":
        if not (Path(a.data_root) / "news_corpus").is_dir():
            print(f"REFUSED: no news_corpus under {a.data_root}")
            return 2
        rows = OE.list_events(Path(a.data_root), now=now, hours=a.hours, sources=a.source)
        for r in rows[:a.limit]:
            print(f"{r['published_utc'][:16]}  {r['source']:<28} {','.join(r['tickers'])[:20]:<20} "
                  f"{','.join(r['items']):<14} {r['title'][:80]}  key={r['key']}")
        print(f"{len(rows)} events with >=1 ticker in the last {a.hours:g} h")
        return 0
    if a.cmd == "grade":
        fpath = _out(a) / "forecasts.jsonl"
        if not fpath.exists():
            print(f"REFUSED: no forecast ledger at {fpath}")
            return 2
        res = OE.grade(fpath, data_root=Path(a.data_root), now=now)
        print(json.dumps({k: v for k, v in res.items() if k != "new_grades"}, indent=1))
        for g in res["new_grades"]:
            print(f"{g['ticker']:<6} h={g['horizon_sessions']} {g['entry_date']}->{g['exit_date']} "
                  f"adj {g['market_adjusted']:+.4f} hit {g['hit']}")
        c = res["counts"]
        return 0 if (c["graded"] + c["pending"] + c["already"]) > 0 else 2
    rec = OE.run_one(data_root=Path(a.data_root), source=a.source, key=a.key, now=now,
                     out_dir=_out(a), graph_dir=Path(a.graph_dir) if a.graph_dir else None,
                     funnel_path=Path(a.funnel) if a.funnel else None,
                     positions_path=Path(a.positions) if a.positions else None,
                     ticker=a.ticker,
                     direction={"up": 1, "down": -1}.get(a.direction) if a.direction else None,
                     write=not a.no_write)
    print(OE.table(rec))
    if a.no_write:
        print("-> nothing written (--no-write): no forecast row, no receipt")
    else:
        print(f"-> {OE.write_receipt(rec, _out(a))}")
    return int(rec["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
