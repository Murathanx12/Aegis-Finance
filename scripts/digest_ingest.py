"""Ingest the operator's paste inbox; optionally extract claims into forecast rows.

    python -m scripts.digest_ingest --once              # store every new pasted entry
    python -m scripts.digest_ingest --once --claims     # ... then claims -> forecasts (<= $0.30)
    python -m scripts.digest_ingest --reading-list      # (re)write WEEKEND_READING_LIST.md
    python -m scripts.digest_ingest --watch --every 300 # poll (optional)

See `backend/services/digest_inbox.py` for the format and the PIT rule. The
receipt (`backend/data/optimus/dowjones/digest_ingest_<date>.json`) holds
metadata only; the pasted text stays in the gitignored corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import digest_inbox as DI  # noqa: E402
from backend.services import dowjones_feeds as DF  # noqa: E402


def _write(rc: dict, name: str) -> Path:
    p = DF.receipts_dir() / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rc, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return p


def once(claims: bool) -> dict:
    r = DI.ingest()
    day = r["ingest_utc"][:10]
    out = {"ingest": {"n_entries": r["n_entries"], "n_new": r["n_new"],
                      "n_duplicate": r["n_duplicate"], "n_too_short": r["n_too_short"]}}
    if claims:
        from scripts.dowjones_pull import run_claims
        c = run_claims(day)
        r["claims"] = {k: c[k] for k in ("n_articles", "n_claims", "spent_usd",
                                          "forecast_rows_by_source_id", "stopped")}
        out["claims"] = r["claims"]
    out["receipt"] = str(_write(r, f"digest_ingest_{day}.json"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--claims", action="store_true")
    ap.add_argument("--reading-list", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--every", type=float, default=300.0)
    a = ap.parse_args(argv)
    if a.reading_list:
        print(f"wrote {DI.write_reading_list()}")
    if a.watch:
        while True:
            print(json.dumps(once(a.claims), default=str), flush=True)
            time.sleep(max(30.0, a.every))
    if a.once or not a.reading_list:
        print(json.dumps(once(a.claims), indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
