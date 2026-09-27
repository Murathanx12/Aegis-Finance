"""Pull FINRA's Reg SHO daily consolidated short-sale volume files (resumable).

    python -m scripts.pull_finra_short_volume                  # 2018-08-01 -> yesterday
    python -m scripts.pull_finra_short_volume --start 2026-09-01 --max-files 5
    python -m scripts.pull_finra_short_volume --consolidate-only

Network: cdn.finra.org only, >= 0.5 s between files. Refuses to start under
20 GB free. Writes `<OPTIMUS>/finra_short_volume/` (parquets gitignored) and a
receipt `pull_receipt_<UTC stamp>.json` beside the tracked `manifest.json`.
Every receipt prints the PIT rule. See `backend/services/finra_short_volume.py`.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from backend.services import finra_short_volume as F  # noqa: E402
from backend.services.disk_guard import atomic_write_json, require_free  # noqa: E402

MIN_FREE_GB = 20.0
RETRIES = 3
RETRY_WAIT_S = 5.0


def fetch_with_retry(url: str):
    """Network errors retried (RETRIES x RETRY_WAIT_S); HTTP answers are returned as-is."""
    last = None
    for i in range(RETRIES):
        try:
            return F.http_fetch(url)
        except Exception as e:  # noqa: BLE001 -- retried, then re-raised by name
            last = e
            time.sleep(RETRY_WAIT_S * (i + 1))
    raise F.FinraShortVolumeError(f"network: {type(last).__name__}: {last}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--start", default=str(F.START_DATE))
    ap.add_argument("--end", default=None)
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--consolidate-only", action="store_true")
    ap.add_argument("--root", default=None)
    a = ap.parse_args(argv)
    root = Path(a.root) if a.root else F.default_root()
    root.mkdir(parents=True, exist_ok=True)
    disk = require_free(MIN_FREE_GB, "pull_finra_short_volume", path=root)
    print(f"PIT RULE: {F.PIT_RULE}")
    print(f"disk: {disk['free_gb']:.1f} GB free on {disk['volume']}")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    rec: dict = {"started_utc": stamp, "disk_free_gb": round(disk["free_gb"], 1)}
    rc = 0
    if not a.consolidate_only:
        try:
            rec["pull"] = F.pull(date.fromisoformat(a.start),
                                 date.fromisoformat(a.end) if a.end else None,
                                 root=root, fetch=fetch_with_retry, max_files=a.max_files)
        except F.FinraShortVolumeError as e:
            rec["pull"] = {"stopped": f"{type(e).__name__}: {e}"}
            print(f"STOPPED: {e}  (staged days are kept; re-run resumes)")
            rc = 2
    man = F.consolidate(root)
    rec["manifest"] = {k: man[k] for k in ("rows", "dates", "first", "last", "not_published_weekdays")}
    rec["pit_rule"] = F.PIT_RULE
    rec["finished_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    atomic_write_json(root / f"pull_receipt_{stamp}.json", rec, indent=1)
    print(f"manifest: {man['rows']:,} rows, {man['dates']} dates {man['first']} -> {man['last']}; "
          f"{man['not_published_weekdays']} weekdays not published")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
