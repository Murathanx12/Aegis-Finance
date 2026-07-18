"""
EODHD paid-month harvest — archive the scarce data before the plan lapses.

The All World subscription FAILED its acceptance gate for pre-2016 deaths
(NEGATIVE_RESULTS §8) and will not renew, but its post-2016 delisting
coverage tested solid (12/12 of the 2017+ audit names). The one thing worth
keeping from the paid month is a local archive of DELISTED-stock histories —
the asset yfinance cannot provide and the thing that disappears with the
subscription. Active tickers are deliberately NOT harvested (re-fetchable
free, forever).

Resumable: reruns skip tickers already on disk. Storage:
engine/data/eodhd/delisted/{CODE}.csv.gz  (gitignored — local research
cache, personal-use licensed data never enters the repo or the backend).

    python -m engine.research.eodhd_harvest [--limit N]
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

log = logging.getLogger("eodhd_harvest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

BASE = "https://eodhd.com/api"
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "eodhd"
RATE_SLEEP = 0.25  # per-worker pause; with WORKERS below stays ~<10 req/s
WORKERS = 6        # 1000/min plan limit; 6 workers * ~1.4s/req ~= 4-8 req/s


def _token() -> str:
    tok = os.getenv("EODHD_API_TOKEN", "").strip()
    if not tok:
        sys.exit("Set EODHD_API_TOKEN")
    return tok


def fetch_delisted_list(tok: str) -> list[dict]:
    out = DATA_DIR / f"delisted_symbol_list_{date.today().isoformat()}.json.gz"
    if out.exists():
        with gzip.open(out, "rt", encoding="utf-8") as f:
            return json.load(f)
    r = requests.get(f"{BASE}/exchange-symbol-list/US",
                     params={"api_token": tok, "fmt": "json", "delisted": "1"},
                     timeout=180)
    r.raise_for_status()
    rows = r.json()
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as f:
        json.dump(rows, f)
    log.info("delisted list snapshot: %d rows -> %s", len(rows), out.name)
    return rows


def harvest(limit: int | None = None) -> None:
    tok = _token()
    rows = fetch_delisted_list(tok)
    # Common stocks only — funds/ETNs/warrants are not the survivorship asset.
    commons = [r for r in rows if (r.get("Type") or "") == "Common Stock"
               and r.get("Code")]
    log.info("delisted common stocks in list: %d", len(commons))

    dest = DATA_DIR / "delisted"
    dest.mkdir(parents=True, exist_ok=True)
    todo = []
    skipped = 0
    for row in commons[:limit]:
        code = row["Code"]
        # EODHD codes can contain '/', guard the filename
        fname = dest / (code.replace("/", "_") + ".csv.gz")
        if fname.exists():
            skipped += 1
        else:
            todo.append((code, fname))
    log.info("to fetch: %d (skipping %d already on disk)", len(todo), skipped)

    counts = {"done": 0, "empty": 0, "failed": 0}
    stop = False

    def one(code: str, fname: Path) -> str:
        nonlocal stop
        if stop:
            return "failed"
        try:
            r = requests.get(f"{BASE}/eod/{code}.US",
                             params={"api_token": tok, "fmt": "csv"},
                             timeout=60)
            if r.status_code in (401, 402):
                log.error("auth/quota error (%s) — stopping pool", r.status_code)
                stop = True
                return "failed"
            if r.status_code == 404 or not r.text.strip() or \
                    r.text.lstrip().startswith(("{", "Ticker Not Found")):
                return "empty"
            r.raise_for_status()
            with gzip.open(fname, "wt", encoding="utf-8") as f:
                f.write(r.text)
            return "done"
        except Exception as e:  # noqa: BLE001 — harvest must survive one bad row
            log.warning("%s: %s", code, str(e)[:100])
            return "failed"
        finally:
            time.sleep(RATE_SLEEP)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for i, result in enumerate(pool.map(lambda cf: one(*cf), todo)):
            counts[result] += 1
            if (i + 1) % 500 == 0:
                log.info("progress %d/%d  saved=%d empty=%d fail=%d",
                         i + 1, len(todo), counts["done"], counts["empty"],
                         counts["failed"])
    log.info("HARVEST DONE: saved=%d skipped=%d empty=%d failed=%d -> %s",
             counts["done"], skipped, counts["empty"], counts["failed"], dest)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="harvest only the first N (smoke test)")
    harvest(ap.parse_args().limit)
