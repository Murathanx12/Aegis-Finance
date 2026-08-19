"""MEGA-SWEEP-1 — the frozen 84-book grid + 2 baselines, resumable.

    python -m scripts.mega_sweep_1            # runs remaining books
    python -m scripts.mega_sweep_1 --report   # BH-FDR screen over results

Grid authority: docs/research/MEGA_SWEEP_1_DECLARATION.md (frozen
pre-run). Per-book rows append to books.jsonl as they finish, so a
killed run resumes without recomputation. SCREEN ONLY — BH-FDR 0.10 at
m = 84 vs the same-handling baseline; risk panel reported for all.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from itertools import product
from math import erf, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services.lane_factory_sim import (SIGNALS,      # noqa: E402
                                               load_panel, prepare_extras,
                                               run_book)
from backend.services.net_tournament import (                # noqa: E402
    bootstrap_block_dates)
from backend.services.world_model import (                   # noqa: E402
    block_bootstrap_paired)

OUT = _config.OPTIMUS_LEDGER_DIR / "lane_factory"
BOOKS_PATH = OUT / "mega_sweep_1_books.jsonl"
RETS_DIR = OUT / "mega_sweep_1_monthly"

WEIGHTINGS = ("equal", "inverse_vol", "rank")
HANDLINGS = ("trim", "exempt")
TOP_NS = (50, 100)


def grid() -> list[dict]:
    cells = [{"signal": s, "weighting": w, "winner_handling": h,
              "top_n": n}
             for s, w, h, n in product(sorted(SIGNALS), WEIGHTINGS,
                                       HANDLINGS, TOP_NS)]
    for h in HANDLINGS:
        cells.append({"signal": "none", "weighting": "equal",
                      "winner_handling": h, "top_n": None})
    return cells


def key(c: dict) -> str:
    return f"{c['signal']}|{c['weighting']}|{c['winner_handling']}|" \
           f"{c['top_n']}"


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mega_sweep_1")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    if a.report:
        return report()

    OUT.mkdir(parents=True, exist_ok=True)
    RETS_DIR.mkdir(parents=True, exist_ok=True)
    done = set()
    if BOOKS_PATH.exists():
        done = {json.loads(x)["key"] for x in
                BOOKS_PATH.read_text(encoding="utf-8").splitlines() if x}
    cells = [c for c in grid() if key(c) not in done]
    print(f"grid {len(grid())} cells, {len(done)} done, "
          f"{len(cells)} to run")
    if not cells:
        return report()
    panel = load_panel()
    extras = prepare_extras(panel)
    with BOOKS_PATH.open("a", encoding="utf-8") as fh:
        for i, c in enumerate(cells):
            k = key(c)
            try:
                b = run_book(panel, extras=extras, **c)
            except Exception as e:                             # noqa: BLE001
                row = {"key": k, **c, "error": f"{type(e).__name__}: {e}"}
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                print(f"[{i+1}/{len(cells)}] {k}  ERROR {e}")
                continue
            b["monthly_returns"].to_json(RETS_DIR / f"{k}.json")
            row = {"key": k, **{kk: vv for kk, vv in b.items()
                                if kk not in ("monthly_returns", "nav")}}
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            print(f"[{i+1}/{len(cells)}] {k}  tot {b['total_return']:+.3f}"
                  f"  vol {b['ann_vol']:.3f}  dd {b['max_drawdown']:.3f}")
    return report()


def report() -> int:
    rows = [json.loads(x) for x in
            BOOKS_PATH.read_text(encoding="utf-8").splitlines() if x]
    ok = [r for r in rows if "error" not in r]
    errs = [r for r in rows if "error" in r]
    base = {}
    for h in HANDLINGS:
        k = f"none|equal|{h}|None"
        base[h] = pd.read_json(RETS_DIR / f"{k}.json", typ="series")

    stats = []
    for r in ok:
        if r["signal"] == "none":
            continue
        mret = pd.read_json(RETS_DIR / f"{r['key']}.json", typ="series")
        b = base[r["winner_handling"]]
        ix = mret.index.intersection(b.index)
        d = (mret.loc[ix] - b.loc[ix]).to_numpy(float)
        dates = ix.to_numpy(dtype="datetime64[D]")
        block = bootstrap_block_dates(dates, 21)
        inf = block_bootstrap_paired(d, dates, block_days=block,
                                     seed=20260819)
        z = inf.mean / inf.se if inf.se > 0 else 0.0
        p = 2 * (1 - 0.5 * (1 + erf(abs(z) / sqrt(2))))
        stats.append({"key": r["key"], "ann_diff_vs_baseline":
                      round(float(np.mean(d) * 12), 5),
                      "p": round(float(p), 5),
                      "mde_monthly": round(float(inf.mde_80pct_power), 5),
                      "ann_vol": r["ann_vol"],
                      "max_drawdown": r["max_drawdown"],
                      "total_return": r["total_return"]})

    m = len(stats)
    ranked = sorted(stats, key=lambda s: s["p"])
    q = 0.10
    passed, thresh = [], 0.0
    for i, s in enumerate(ranked, start=1):
        if s["p"] <= q * i / m:
            thresh = q * i / m
            passed = ranked[:i]
    receipt = {
        "sweep": "MEGA-SWEEP-1 (SIMULATION, SCREEN, BH-FDR 0.10)",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "m_declared": 84, "m_run": m, "n_errors": len(errs),
        "errors": errs,
        "bh_fdr_survivors": [s["key"] for s in passed],
        "bh_threshold_p": thresh,
        "top_15_by_p": ranked[:15],
        "bottom_5_by_ann_diff": sorted(
            stats, key=lambda s: s["ann_diff_vs_baseline"])[:5],
        "note": ("screen only; survivors need their own registrations "
                 "with mean-masked audits — §37 applies"),
    }
    p = OUT / "mega_sweep_1_screen_2026-08-19.json"
    p.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"\nm_run {m}, errors {len(errs)}, "
          f"BH-FDR survivors {len(receipt['bh_fdr_survivors'])}")
    for s in ranked[:10]:
        print(f"  {s['key']:<38} ann_diff {s['ann_diff_vs_baseline']:+.4f}"
              f"  p {s['p']:.4f}  dd {s['max_drawdown']:.3f}")
    print(f"receipt: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
