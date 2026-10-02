"""Read the free OFFICIAL sources (SEC EDGAR, House disclosures, CFTC COT,
FINRA, Federal Register, central banks, White House, Treasury) through their
own APIs and feeds, into point-in-time typed tables under
`backend/data/optimus/official/tables/` (`backend.services.official_sources`).

    python -m scripts.official_sources --due              # what is due (the supervisor's call)
    python -m scripts.official_sources --source sec_form4 --source cftc_cot
    python -m scripts.official_sources --all
    python -m scripts.official_sources --status           # rows per table, requests per source
    python -m scripts.official_sources --schema           # the tables and their fields
    python -m scripts.official_sources --panel            # the joinable daily panel (parquet)

The night reader supervisor launches `--due` out of process every
`OFFICIAL_SOURCES_EVERY_S`; a lock file keeps one run at a time. A STOP file
(`official/STOP`) makes every run exit at once.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import official_sources as OS  # noqa: E402


def _streams() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def _lock(path: Path, stale_s: float = 3 * 3600) -> bool:
    """One run at a time: a lock file with our PID; a lock older than
    `stale_s` is taken over (a crashed run)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, json.dumps({"pid": os.getpid(), "t": OS.iso(OS._now())}).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            age = datetime.now(timezone.utc).timestamp() - path.stat().st_mtime
        except OSError:
            return False
        if age > stale_s:
            try:
                path.unlink()
            except OSError:
                return False
            return _lock(path, stale_s)
        return False


def main(argv: list[str] | None = None) -> int:
    _streams()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--due", action="store_true", help="only the sources whose interval passed")
    ap.add_argument("--all", action="store_true", help="every source now")
    ap.add_argument("--source", action="append", default=[], help="one source (repeatable)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--panel", action="store_true",
                    help="rebuild official/panel/official_daily_panel.parquet now")
    ap.add_argument("--backfill-form4", type=int, default=0, metavar="DAYS",
                    help="also read the last DAYS business days of Forms 4 from EDGAR's daily "
                         "index (rows keep their own acceptance time; flagged backfill)")
    a = ap.parse_args(argv)
    if a.schema:
        print(json.dumps(OS.SCHEMAS, indent=1))
        return 0
    if a.panel:
        rec = OS.build_daily_panel()
        print(json.dumps({k: v for k, v in rec.items() if k != "schema"}, indent=1, default=str))
        return 0
    if a.status:
        print(json.dumps({"tables": OS.table_counts(), "requests": OS.request_counts(),
                          "refused_sources": OS.REFUSED_SOURCES}, indent=1, default=str))
        return 0
    root = OS.root()
    if (root / "STOP").exists():
        print("STOPPED: official/STOP present")
        return 0
    bad = [s for s in a.source if s not in OS.COLLECTORS]
    if bad:
        print(f"REFUSED: unknown source(s) {bad}; known {sorted(OS.COLLECTORS)}")
        return 2
    if not (a.due or a.all or a.source or a.backfill_form4):
        print("nothing to do: pass --due, --all, --source or --backfill-form4")
        return 2
    lock = root / "run.lock"
    # a backfill-only run (hours of Form 4 history) does not hold the lock, so
    # the scheduled `--due` runs keep the live feeds fresh meanwhile; the Form 4
    # state is merged on every save, and the tables deduplicate by row id
    if (a.due or a.all or a.source) and not _lock(lock):
        print("SKIPPED: another official_sources run holds the lock")
        return 0
    try:
        out = OS.run(a.source or None, due=a.due and not a.source) \
            if (a.due or a.all or a.source) else {"tables": OS.table_counts()}
        if a.backfill_form4:
            b = OS.collect_sec_form4_backfill(OS.Fetcher(), days=int(a.backfill_form4))
            print(json.dumps(b, default=str)[:1500], flush=True)
            out["tables"] = OS.table_counts()
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
    print(json.dumps({"receipt": out.get("receipt"), "requests": out.get("requests_this_run"),
                      "tables": {k: v["rows"] for k, v in out["tables"].items()}}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
