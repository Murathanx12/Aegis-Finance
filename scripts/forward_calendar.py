"""Forward catalyst calendar CLI (ROADMAP CH-35 / CH-08, module M2 UNIVERSE).

    python -m scripts.forward_calendar universe --data-root <optimus> [--with-bars-panel]
    python -m scripts.forward_calendar pull --data-root <optimus> [--out DIR] [--limit N]
                                       [--tickers A,B,...] [--with-bars-panel] [--no-macro]
    python -m scripts.forward_calendar show --data-root <optimus> [--out DIR] --tickers NVDA
                                       [--now ISO] [--horizon-days N]
    python -m scripts.forward_calendar status --data-root <optimus> [--out DIR]

`--data-root` is where the universe is READ from (the optimus folder). `--out` is
the root the store is written under (`<out>/forward_calendar/`); without it the
store lives under `--data-root`. Exit codes: 0 ok; 2 refused (low coverage, empty
universe, a snapshot that would be overwritten); `status` exits 2 unless ALIVE.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.services import forward_calendar as FC


def _now(v: Optional[str]) -> datetime:
    if not v:
        return datetime.now(timezone.utc)
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _print(obj: dict) -> None:
    print(json.dumps(obj, indent=1, sort_keys=True, default=str))


def _universe(a: argparse.Namespace, now: datetime) -> dict:
    u = FC.build_universe(Path(a.data_root), now, with_bars_panel=a.with_bars_panel)
    if a.tickers:
        u = {**u, "tickers": [t.strip().upper() for t in a.tickers.split(",") if t.strip()],
             "explicit_tickers": True}
    if a.limit:
        u = {**u, "tickers": u["tickers"][:int(a.limit)], "limited_to": int(a.limit)}
    return u


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.forward_calendar")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("universe", "pull", "show", "status"):
        p = sub.add_parser(name)
        p.add_argument("--data-root", required=True)
        p.add_argument("--out", default=None)
        p.add_argument("--now", default=None, help="show/status only: the instant to read as of")
        if name in ("universe", "pull"):
            p.add_argument("--with-bars-panel", action="store_true")
            p.add_argument("--limit", type=int, default=None)
        if name in ("universe", "pull", "show"):
            p.add_argument("--tickers", default=None)
        if name == "pull":
            p.add_argument("--no-macro", action="store_true")
            p.add_argument("--batch-size", type=int, default=None)
        if name == "show":
            p.add_argument("--horizon-days", type=int, default=None)
    a = ap.parse_args(argv)
    out_root = Path(a.out) if a.out else Path(a.data_root)
    try:
        if a.cmd == "universe":
            u = _universe(a, _now(None))
            _print({"n": len(u["tickers"]), "sources": u["sources"], "first": u["tickers"][:20]})
            return 0
        if a.cmd == "pull":
            u = _universe(a, _now(None))
            meta = {"n": len(u["tickers"]), "sources": u["sources"],
                    "explicit_tickers": u.get("explicit_tickers", False),
                    "limited_to": u.get("limited_to")}
            print(f"forward_calendar pull: {len(u['tickers'])} tickers -> {FC.snapshots_dir(out_root)}",
                  flush=True)
            rec = FC.pull(u["tickers"], out_root, universe_meta=meta,
                          macro=False if a.no_macro else None, batch_size=a.batch_size)
            _print({k: rec.get(k) for k in ("pull_id", "status", "requested", "fetched", "with_date",
                                            "no_date", "failed", "not_an_issuer", "share_covered",
                                            "min_share", "n_requests", "n_rate_limited", "stopped",
                                            "no_date_reasons", "failure_errors", "confirmation_counts",
                                            "macro", "started_utc", "finished_utc",
                                            "snapshot_path", "receipt_path")})
            FC.check_coverage(rec)
            return 0
        if a.cmd == "show":
            if not a.tickers:
                print("show needs --tickers", file=sys.stderr)
                return 2
            now = _now(a.now)
            res = FC.next_dates(a.tickers.split(","), now, a.horizon_days, root=out_root)
            res["macro"] = FC.next_macro(now, a.horizon_days, root=out_root)
            _print(res)
            return 0
        if a.cmd == "status":
            f = FC.freshness(out_root, _now(a.now))
            _print(f)
            return 0 if f["verdict"] == "ALIVE" else 2
    except FC.ForwardCalendarRefused as exc:
        print(f"REFUSED {exc}", flush=True)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
