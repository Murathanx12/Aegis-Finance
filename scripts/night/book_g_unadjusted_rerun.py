"""Book G re-run on the UNADJUSTED IBES summary, beside the leaky input, same code.

    AEGIS_DATA_DIR=<runtime>/backend/data python -m scripts.night.book_g_unadjusted_rerun

Reads the runtime's CRSP panel and IBES files read-only. Writes ONLY into this
checkout's `backend/data/optimus/night_2026-11-11/` with a run id in every filename:
the per-book receipts `replay_book_g` produces, and one summary
`book_g_unadjusted_rerun_<run>.json` with old -> new for both constructions and both
floors.

Four reads through `night_books_efg_replay.replay_book_g`, the registered engine
(turnover-matched twin from the covered band, flat 25 bps, NW lag-2 t, both floors):

  v0_as_quoted      |stdev / meanest|, unadjusted statsumu_epsus   (the fix)
  price_as_quoted   |stdev / price|,   unadjusted statsumu_epsus   (the fix)
  v0_leaky          |stdev / meanest|, split-adjusted file          (reproduces run 01)
  price_leaky       |stdev / price|,   split-adjusted file          (reproduces Amendment 1)

The leaky frames are the old loader's output stamped as-quoted ON PURPOSE, so the
two pairs differ by the input file and nothing else; they exist to show that this
checkout reproduces the 2026-09-13 receipts before the fixed number is believed.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "backend" / "data" / "optimus" / "night_2026-11-11"

#: The 2026-09-13 receipts this re-run is compared against (runtime paths, read-only).
OLD = {
    "v0": "first_books/replay/forecast_dispersion_v0_2026-09-13T073215Z.json",
    "price": "first_books/replay/forecast_dispersion_price_scaled_v1_2026-09-13T152104Z.json",
}


def _leaky_frames(start: int, end: int):
    """The pre-2026-11-11 loader, verbatim in effect: the split-adjusted file."""
    import pandas as pd

    from backend.services.ibes_pit_consensus import AS_QUOTED
    from scripts import night_books_efg_replay as EFG

    w = EFG.wrds_dir()
    frames = [pd.read_parquet(p, columns=list(EFG.IBES_COLUMNS))
              for p in (w / "ibes_consensus_monthly_early.parquet",
                        w / "ibes_consensus_monthly.parquet") if p.is_file()]
    ib = pd.concat(frames, ignore_index=True)
    ib = ib[(ib["measure"].astype(str) == "EPS") & (ib["fpi"].astype(str) == "1")]
    ib = ib.dropna(subset=["permno"])
    ib["permno"] = ib["permno"].astype("int64")
    ib["statpers"] = pd.to_datetime(ib["statpers"])
    ib["ym"] = ib["statpers"].dt.to_period("M")
    ib = ib[(ib["ym"].dt.year >= int(start)) & (ib["ym"].dt.year <= int(end))]
    ib = ib.sort_values(["permno", "ym", "statpers"], kind="mergesort")
    ib = ib.drop_duplicates(subset=["permno", "ym"], keep="last")
    ib["share_basis"] = AS_QUOTED        # DELIBERATE mislabel: the leaky reproduction
    return ib[["permno", "ym", "numest", "meanest", "stdev", "share_basis"]].reset_index(drop=True)


def _cell(book: dict, floor: str) -> dict:
    c = ((book.get("cells") or {}).get(floor) or {})
    r = c.get("result") or {}
    return {"floor_usd": r.get("floor_usd"), "n_blocks": r.get("n_blocks"),
            "mean_excess_net_monthly": r.get("mean_excess_net_monthly"),
            "nw_lag2_t": r.get("nw_lag2_t"),
            "mean_book_net_monthly": r.get("mean_book_net_monthly"),
            "mean_twin_net_monthly": r.get("mean_twin_net_monthly"),
            "by_era": c.get("by_era")}


def main() -> int:
    from backend.config import OPTIMUS_LEDGER_DIR
    from scripts import night_books_efg_replay as EFG

    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUT.mkdir(parents=True, exist_ok=True)
    EFG.out_dir = lambda: OUT                        # never the runtime's replay folder
    t0 = time.time()
    start, end = EFG.FULL_START, EFG.FULL_END
    print(f"[{run}] data dir {OPTIMUS_LEDGER_DIR} window {start}-{end}", flush=True)
    panel = EFG.load_monthly_panel(start, end, max_names=None)
    print(f"panel {len(panel):,} rows {time.time()-t0:.0f}s", flush=True)
    fixed = EFG.by_month(EFG.load_ibes_dispersion(start, end))
    leaky = EFG.by_month(_leaky_frames(start, end))
    print(f"ibes months fixed {len(fixed)} leaky {len(leaky)} {time.time()-t0:.0f}s", flush=True)

    out = {"run_id": run, "job": "book_g_unadjusted_rerun", "licence": "PRODUCT_EXPERIMENT",
           "window": [start, end], "engine": "night_books_efg_replay.replay_book_g",
           "source_fixed": "ibes_pit_consensus.load_consensus (statsumu_epsus, unadjusted)",
           "source_leaky": "ibes_consensus_monthly[_early] (statsum_epsus, split-adjusted)",
           "variants_tried": 4, "reads": {}, "old_receipts": {}}
    for scale in ("meanest", "price"):
        for tag, frames in (("as_quoted", fixed), ("leaky", leaky)):
            key = f"{'v0' if scale == 'meanest' else 'price'}_{tag}"
            book = EFG.replay_book_g(panel, frames, smoke=False, scale=scale)
            name = f"book_g_{key}_{run}.json"
            (OUT / name).write_text(json.dumps(book, indent=2, default=str), encoding="utf-8")
            out["reads"][key] = {"receipt": name, "headline": book.get("headline"),
                                 "verdict": book.get("verdict"),
                                 "primary": _cell(book, "primary_floor"),
                                 "secondary": _cell(book, "secondary_floor")}
            print(f"{key}: {book.get('headline')} {time.time()-t0:.0f}s", flush=True)
    for k, rel in OLD.items():
        p = OPTIMUS_LEDGER_DIR / rel
        if p.is_file():
            b = json.loads(p.read_text(encoding="utf-8"))
            out["old_receipts"][k] = {"path": rel, "headline": b.get("headline"),
                                      "primary": _cell(b, "primary_floor"),
                                      "secondary": _cell(b, "secondary_floor")}
    out["wall_s"] = round(time.time() - t0, 1)
    p = OUT / f"book_g_unadjusted_rerun_{run}.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"receipt -> {p}", flush=True)
    return 0


if __name__ == "__main__":
    if not os.getenv("AEGIS_DATA_DIR"):
        sys.exit("set AEGIS_DATA_DIR to the runtime's backend/data (read-only use)")
    raise SystemExit(main())
