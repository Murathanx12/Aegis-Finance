"""CH-66: fetch the FULL text of stored 8-K Exhibit 99 documents whose body the
raw collector cut, into `<data root>/sec_exhibit_full/` (or --out).

    python -m scripts.sec_exhibit_full --data-root backend/data/optimus [--out DIR]
        [--max-docs N] [--pace-s S] [--all-tickers | --tickers AAPL,MSFT] [--dry-run]

Scope by default: tickers in the funnel candidate set plus the primary tickers
of open event nodes, newest filing first. Resumable: an exhibit already in the
store is never fetched again. One receipt per run, run id in its name.

Exit codes: 0 rows fetched, or nothing owed · 2 REFUSED (a bad argument such
as --pace-s below the floor, refused before any request; missing input; empty
scope; the source answered 403/429, where the run stops at the FIRST such
answer and does not retry; or a wave of 200 answers that were not the exhibit,
SOURCE_SUSPECT) · 3 requests were made and some or all failed (a
CONTENT_MISMATCH answer is a failure: nothing stored, still owed).

Identification: the request goes through `scripts.news_pull._http_get`, the
same door and the same User-Agent configuration the scheduled raw collector
uses (env AEGIS_NEWS_USER_AGENT, else that module's default). This script
defines no User-Agent of its own. It reads the collector's files and never
writes to them.
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

from backend import config as C  # noqa: E402
from backend.services import sec_exhibit_full as SX  # noqa: E402


def _collector_door():
    """The collector's network door and cleaner, imported late so `--help` and
    `--dry-run` need none of the collector's dependencies."""
    from backend.services import fetch_scrapling
    from scripts import news_pull

    def to_text(raw: bytes) -> str:
        return news_pull._strip_html(fetch_scrapling._decode(raw))

    source = ("env AEGIS_NEWS_USER_AGENT" if __import__("os").environ.get("AEGIS_NEWS_USER_AGENT")
              else "scripts.news_pull.USER_AGENT default")
    return news_pull._http_get, to_text, source


def _pace(value: str) -> float:
    """--pace-s, refused at parse (exit 2, before any request) when it is not a
    finite number at or above `SX.min_pace_s()`."""
    why = SX.pace_problem(value)
    if why:
        raise argparse.ArgumentTypeError(why)
    return float(value)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data-root", default=str(C.OPTIMUS_LEDGER_DIR))
    ap.add_argument("--out", default=None, help="store folder (default <data-root>/sec_exhibit_full)")
    ap.add_argument("--max-docs", type=int, default=int(C.SEC_EXHIBIT_FULL_MAX_DOCS))
    ap.add_argument("--pace-s", type=_pace, default=float(C.SEC_EXHIBIT_FULL_PACE_S),
                    help=f"seconds between requests, at least {SX.min_pace_s():g}")
    ap.add_argument("--all-tickers", action="store_true")
    ap.add_argument("--tickers", default="", help="comma-separated; overrides the default scope")
    ap.add_argument("--funnel", default=None, help="funnel snapshot (default: beside the data root)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what is owed and exit; no request, no write")
    a = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    paths = SX.default_paths(Path(a.data_root))
    if a.funnel:
        paths["funnel"] = Path(a.funnel)
    tickers = [t for t in a.tickers.split(",") if t.strip()] or None
    if a.dry_run:
        try:
            SX.check_inputs(paths)
        except SX.SecExhibitFullRefused as e:
            print(f"REFUSED({e.code}): {e.detail}")
            return 2
        if tickers:
            scope, src, prio = {t.upper().strip() for t in tickers}, {"mode": "explicit"}, set()
        elif a.all_tickers:
            scope, src, prio = None, {"mode": "all"}, set()
        else:
            s = SX.scope_tickers(paths, now)
            scope, src, prio = s["tickers"], s["sources"], s["priority"]
        store = Path(a.out) if a.out else paths["store"]
        todo, counts = SX.owed(SX.read_body_rows(paths["corpus"]),
                               SX.read_full_store(store, with_text=False).keys(),
                               SX.load_cik_map(paths["cik_map"]), scope, prio)
        print(json.dumps({"dry_run": True, "scope": src,
                          "scope_n": None if scope is None else len(scope),
                          "counts": counts,
                          "next": [{"raw_id": o["raw_id"], "tickers": o["tickers"],
                                    "filed_utc": o["filed"].isoformat()}
                                   for o in todo[: a.max_docs]]}, indent=1, default=str))
        return 0

    http_get, to_text, source = _collector_door()
    receipt = SX.run(paths, http_get=http_get, to_text=to_text, now=now,
                     out_dir=Path(a.out) if a.out else None, max_docs=a.max_docs,
                     pace_s=a.pace_s, all_tickers=a.all_tickers, tickers=tickers,
                     user_agent_source=source)
    head = receipt["status"] + (f"({receipt['code']})" if receipt.get("code") else "")
    print(f"sec_exhibit_full {head}: fetched {receipt['fetched']} of "
          f"{(receipt.get('counts') or {}).get('owed', 0)} owed, "
          f"{receipt['requests']} request(s), {len(receipt['failures'])} failure(s)"
          + (f"; {receipt['detail']}" if receipt.get("detail") else ""))
    print(f"scope: {json.dumps(receipt.get('scope'), default=str)}")
    print(f"receipt: {receipt.get('receipt_path')}")
    return int(receipt["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
