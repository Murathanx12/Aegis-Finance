"""Deepen the price panel — the same pull as P6a, from an earlier start.

WHY: `xs_ranker` needs 12-1 momentum, which costs a year of history per symbol.
The 2025-01-01 panel therefore yields only 156 usable decision dates out of 430
sessions, and 156 overlapping 21-session windows is roughly seven independent
month-blocks. That is too thin to validate a ranker on and too thin to tell a
champion from a challenger.

Alpaca's free SIP plan serves daily bars back well before 2016, so the fix costs
wall-clock and nothing else. This writes a SEPARATE parquet
(`prices_deep/bars.parquet`) and never touches `prices_2025_26/bars.parquet`, so
a failed or partial pull cannot damage the panel that already works.

    python -m scripts.pull_deep_bars --start 2016-01-01

Credentials resolve exactly as P6 resolves them (`night_p6_bars_and_regret`);
nothing is aliased into the environment here — that mistake cost the 09-21 night
its bars refresh.
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

from scripts import night_p6_bars_and_regret as P6  # noqa: E402

OUT_PARQUET = REPO / "backend" / "data" / "optimus" / "prices_deep" / "bars.parquet"
RECEIPT = REPO / "backend" / "data" / "optimus" / "prices_deep" / "pull_receipt.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(OUT_PARQUET))
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    kid, sec, src = P6.data_credential()
    syms, uni_meta = P6.universe_symbols(limit=a.limit)
    syms = list(dict.fromkeys(syms + ["SPY", "QQQ", "IWM", "RSP"]))
    print(f"pulling {len(syms)} symbols from {a.start} (credential: {src})", flush=True)

    df = P6.pull_bars(syms, a.start, None, kid, sec)
    if df is None or df.empty:
        print("REFUSED: the venue returned no bars", flush=True)
        return 2
    df.to_parquet(out, index=False)

    receipt = {
        "job": "pull_deep_bars",
        "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "credential_source": src,
        "universe": uni_meta,
        "start_requested": a.start,
        "symbols_requested": len(syms),
        "symbols_with_bars": int(df["symbol"].nunique()),
        "bars": int(len(df)),
        "sessions": int(df["date"].nunique()),
        "first_session": str(df["date"].min().date()),
        "last_session": str(df["date"].max().date()),
        "parquet": str(out),
        "parquet_mb": round(out.stat().st_size / 1e6, 2),
        "elapsed_s": round(time.time() - t0, 1),
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    receipt["headline"] = (f"{receipt['bars']:,} daily bars for {receipt['symbols_with_bars']} "
                           f"symbols over {receipt['sessions']} sessions, "
                           f"{receipt['first_session']}..{receipt['last_session']}")
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(receipt["headline"], flush=True)
    print(f"-> {out} ({receipt['parquet_mb']} MB) in {receipt['elapsed_s']}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
