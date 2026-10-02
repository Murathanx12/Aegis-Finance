"""Alpaca us_equity asset list (names) for the ETF/ETN exclusion list (network, $0).

    nn_lab\.venv\Scripts\python.exe -m nn_lab.fetch_assets [--status inactive]

Writes `backend/data/optimus/nn_lab/universe_meta/alpaca_assets_<status>.json`, which
`nn_lab.universe_filter` reads. A one-off fetch, never called by the nightly. Importing this
module does nothing (it used to run at import from a stray copy under backend/data).
Credentials come from `scripts.night_p6_bars_and_regret.data_credential()`; key values are
never printed.
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "backend" / "data" / "optimus" / "nn_lab" / "universe_meta"
URL = "https://paper-api.alpaca.markets/v2/assets?status={status}&asset_class=us_equity"


def out_path(status: str) -> Path:
    return OUT_DIR / f"alpaca_assets_{status}.json"


def fetch(status: str = "inactive", timeout: int = 900) -> int:
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from scripts import night_p6_bars_and_regret as P6              # noqa: PLC0415
    kid, sec, _src = P6.data_credential()
    t = time.time()
    req = urllib.request.Request(URL.format(status=status),
                                 headers={"APCA-API-KEY-ID": kid, "APCA-API-SECRET-KEY": sec})
    raw = urllib.request.urlopen(req, timeout=timeout).read()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path(status).write_bytes(raw)
    print(status, len(raw), round(time.time() - t, 1), flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", default="inactive", choices=["inactive", "active"])
    a = ap.parse_args(argv)
    return fetch(a.status)


if __name__ == "__main__":
    raise SystemExit(main())
