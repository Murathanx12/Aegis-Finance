"""INFORMATION-DIMENSION-1 re-read with the expectations class on the UNADJUSTED IBES.

    AEGIS_DATA_DIR=<runtime>/backend/data python -m scripts.night.information_dimension_rerun

The 2026-08-20 screen (`scripts/information_dimension_1.py`) built its 36
`expectations` books from the split-adjusted `ibes_consensus_monthly.parquet`, whose
`exp_disp` / `exp_rev` read cent-rounded levels on today's share basis (the
split-rounding leak). Every other class (price, fundamental, options, liquidity) does
not touch IBES, so their 180 books are read back unchanged from the 08-20 books file
(runtime, read-only) and only the 36 expectations books are rebuilt with
`information_classes` on `ibes_pit_consensus`. The effective-rank analysis is the
08-20 script's, verbatim in logic and seed. Writes only into this checkout's
`backend/data/optimus/night_2026-11-11/` with a run id.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "backend" / "data" / "optimus" / "night_2026-11-11"


def main() -> int:
    from backend import config as _config
    from backend.services import lane_factory_sim as LFS
    from backend.services.information_classes import CLASSES, build_extras, register
    from scripts import information_dimension_1 as ID

    run = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    t0 = time.time()
    old_books = _config.OPTIMUS_LEDGER_DIR / "structure" / "information_dimension_1_books.jsonl"
    old_receipt = _config.OPTIMUS_LEDGER_DIR / "structure" / "information_dimension_1_2026-08-20.json"
    done = {}
    for line in old_books.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            done[r["key"]] = r
    exp_signals = set(CLASSES["expectations"])
    register(LFS.SIGNALS)
    panel = LFS.load_panel()
    extras = build_extras(panel, include=("expectations",))   # the only class rebuilt
    print(f"panel + extras {time.time()-t0:.0f}s", flush=True)

    all_signals = [s for names in CLASSES.values() for s in names]
    cells = [{"signal": s, "weighting": w, "winner_handling": h, "top_n": n}
             for s, w, h, n in product(all_signals, ID.WEIGHTINGS, ID.HANDLINGS, ID.TOP_NS)]
    series, errors, rebuilt, books_out = {}, [], 0, []
    for c in cells:
        k = f"{c['signal']}|{c['weighting']}|{c['winner_handling']}|{c['top_n']}"
        if c["signal"] in exp_signals:
            try:
                b = LFS.run_book(panel, weighting=c["weighting"],
                                 winner_handling=c["winner_handling"],
                                 top_n=c["top_n"], signal=c["signal"], extras=extras)
            except Exception as e:                                 # noqa: BLE001
                errors.append({"key": k, "error": f"{type(e).__name__}: {e}"})
                continue
            mr = b.pop("monthly_returns")
            b.pop("nav", None)
            r = {"key": k, **{kk: vv for kk, vv in b.items()
                              if not isinstance(vv, (pd.Series, pd.DataFrame))},
                 "monthly": {str(int(pd.Timestamp(ix).timestamp() * 1000)): float(v)
                             for ix, v in mr.items()}}
            books_out.append(r)
            rebuilt += 1
        elif k in done:
            r = done[k]
        else:
            errors.append({"key": k, "error": "not in the 08-20 books file"})
            continue
        series[k] = pd.Series({pd.Timestamp(int(ts), unit="ms"): v
                               for ts, v in r["monthly"].items()}).sort_index()
    print(f"rebuilt {rebuilt} expectations books {time.time()-t0:.0f}s", flush=True)

    R = pd.DataFrame(series).dropna()
    sig_of = {k: k.split("|")[0] for k in R.columns}
    cols_by_class = {cls: [k for k in R.columns if sig_of[k] in names]
                     for cls, names in CLASSES.items()}
    owned_cols = [c for cls in ID.OWNED for c in cols_by_class[cls]]
    dates = np.array(R.index.values, dtype="datetime64[D]")
    from backend.services.net_tournament import bootstrap_block_dates
    blk = bootstrap_block_dates(dates, 21)
    rng = np.random.default_rng(ID.SEED)
    base_dim = ID.eff_rank(R[owned_cols])
    ctrl_pool = cols_by_class["price_extra"]
    n_boot = 400

    def control(k: int) -> np.ndarray:
        out = np.empty(n_boot)
        for i in range(n_boot):
            pick = list(rng.choice(ctrl_pool, size=min(k, len(ctrl_pool)), replace=False))
            out[i] = ID.eff_rank(R[owned_cols + pick])["effective_rank"] - base_dim["effective_rank"]
        return out

    results = {}
    for cls in ID.CANDIDATES:
        cols = cols_by_class[cls]
        if not cols:
            continue
        both = ID.eff_rank(R[owned_cols + cols])
        draws = ID._boot_increment(R, owned_cols, cols, blk, n_boot, rng)
        inc = float(both["effective_rank"] - base_dim["effective_rank"])
        r = {"n_books": len(cols), "dim_owned": round(base_dim["effective_rank"], 3),
             "dim_owned_plus_class": round(both["effective_rank"], 3),
             "increment": round(inc, 3),
             "increment_ci": [round(float(np.percentile(draws, 2.5)), 3),
                              round(float(np.percentile(draws, 97.5)), 3)]}
        if cls != "price_extra":
            ctrl = control(len(cols))
            r["vs_size_matched_control"] = {
                "control_increment_mean": round(float(ctrl.mean()), 3),
                "control_increment_p95": round(float(np.percentile(ctrl, 95)), 3),
                "excess_over_control_mean": round(float(inc - ctrl.mean()), 3),
                "p_value": round(float((ctrl >= inc).mean()), 4),
                "beats_control": bool(inc > np.percentile(ctrl, 95))}
        results[cls] = r

    exp_cagr = {b["key"]: b.get("total_return") for b in books_out}
    old_exp_cagr = {k: v.get("total_return") for k, v in done.items() if k.split("|")[0] in exp_signals}
    old = json.loads(old_receipt.read_text(encoding="utf-8")) if old_receipt.is_file() else {}
    res = {"run_id": run, "trial": "INFORMATION-DIMENSION-1 (re-read, unadjusted IBES)",
           "mode": "SCREEN", "not_a_return_claim": True,
           "changed": "the 36 expectations books only (exp_breadth unchanged by construction; "
                      "exp_disp_low and exp_revision now as-quoted)",
           "n_books": int(R.shape[1]), "n_months": int(R.shape[0]),
           "dim_owned": base_dim, "classes": results, "errors": errors,
           "old_receipt": str(old_receipt), "old_classes": old.get("classes"),
           "expectations_book_total_return_new": exp_cagr,
           "expectations_book_total_return_old": old_exp_cagr,
           "wall_s": round(time.time() - t0, 1),
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"information_dimension_rerun_{run}.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    for cls, r in results.items():
        o = (old.get("classes") or {}).get(cls) or {}
        print(f"{cls:14s} increment {o.get('increment')} -> {r['increment']} "
              f"excess-over-control {((o.get('vs_size_matched_control') or {}).get('excess_over_control_mean'))}"
              f" -> {(r.get('vs_size_matched_control') or {}).get('excess_over_control_mean')}")
    print(f"receipt -> {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
