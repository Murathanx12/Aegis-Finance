"""One forward Teacher Library collection cycle: a day of Forms 3/4/5.

    # the normal cadence — yesterday, after EDGAR posts its index
    python -m scripts.collect_ownership_day

    # a specific day, with a receipt
    python -m scripts.collect_ownership_day --day 2026-08-13

    # a sample, clearly labelled as one
    python -m scripts.collect_ownership_day --day 2026-08-13 --limit 50

WHY YESTERDAY AND NOT TODAY
===========================
EDGAR publishes `form.YYYYMMDD.idx` after the filing day closes. Asking for
today's returns S3's `403 AccessDenied` — the same status a block produces —
which is why `fetch_index` checks the directory listing first and reports
`NOT_YET_PUBLISHED` instead of retrying into a timeout.

So the collector runs one day behind by construction. That is not a lag to be
engineered away: the index for a day IS the set of filings that became public
that day, which is exactly the point-in-time property COPY-LAB needs. Nothing
here can see a filing before the world did.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend import config as _config
from backend.services.teacher_library import adapters_ownership as AO

RECEIPTS = _config.OPTIMUS_LEDGER_DIR / "teacher_library" / "collection_receipts"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--day", default=None,
                    help="YYYY-MM-DD (default: yesterday UTC)")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap filings — produces a SAMPLE, labelled as one")
    ap.add_argument("--allow-historical", action="store_true",
                    help="older than yesterday; the rows are Gym material, "
                         "never forward evidence")
    ap.add_argument("--dry-run", action="store_true",
                    help="collect and report, write nothing")
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    day = a.day or (datetime.now(timezone.utc).date()
                    - timedelta(days=1)).isoformat()
    started = datetime.now(timezone.utc)

    if a.dry_run:
        from backend.services.sec_daily_index import collect_day
        res = collect_day(day, limit=a.limit,
                          allow_historical=a.allow_historical)
        res.pop("parsed", None)
        print(json.dumps(res, indent=2, default=str))
        return 0

    res = AO.collect_and_append(day, limit=a.limit,
                                allow_historical=a.allow_historical)
    res["started_at"] = started.isoformat(timespec="seconds")
    res["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    res["elapsed_s"] = round(
        (datetime.now(timezone.utc) - started).total_seconds(), 1)

    RECEIPTS.mkdir(parents=True, exist_ok=True)
    out = RECEIPTS / f"{day}.json"
    out.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"day                 {day}")
    print(f"source status       {res.get('source_status')} "
          f"{res.get('reason', '')}")
    print(f"filings in index    {res.get('n_ownership_filings_in_index')}")
    print(f"attempted           {res.get('n_attempted')}"
          + ("   [SAMPLE — not the day]" if res.get("sampled") else ""))
    print(f"coverage            {res.get('coverage', 0.0):.3f}")
    print(f"parse errors        {res.get('n_parse_errors')}")
    print(f"events appended     {res.get('appended')}  "
          f"(duplicates skipped {res.get('duplicates', 0)})")
    print(f"usable events       {res.get('usable_events')}")
    # Both directions, side by side, always. A collector that printed only the
    # buys would rebuild the bias this whole path exists to remove.
    print(f"BUY / SELL          {res.get('n_buys')} / {res.get('n_sells')}")
    print(f"receipt             {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
