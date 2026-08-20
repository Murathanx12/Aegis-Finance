"""CONSTRUCTION-CUT-1 — does the top-N CUT destroy the information?

INFORMATION-DIMENSION-1 found that no new information class (options,
expectations, liquidity) buys a new behavioural direction beyond a
size-matched dose of extra price signals, and that 216 books across six
information classes collapse to three clusters. The interpretation
offered — and it was an interpretation, not a measurement — was that the
top-N long-only monthly grammar is what collapses them: the information
is real at security level (the options risk head replicates in both
eras), and the construction destroys it.

That interpretation has a load-bearing, testable implication. A top-N cut
is a coarse quantisation: it throws away everything the signal says about
the other ~2,000 names and everything it says about *how much* the top 50
differ from each other. If the cut is what collapses the space, then
removing the cut should let the classes separate.

TWO GRAMMARS, same signals, same handling, same costs, same dates:

    cut          top 50 by signal, rank-weighted   (the incumbent)
    continuous   NO cut — every eligible name held, rank-weighted across
                 the full cross-section

Readout is the same as INFORMATION-DIMENSION-1: effective rank of the
owned classes, and each candidate class's increment against a
SIZE-MATCHED random subset of the extra-price-signal control pool.

The prediction being tested is specific and falsifiable: **under the
continuous grammar, at least one information class should beat the
control that it failed to beat under the cut.** If no class separates
under either grammar, the cut was not the culprit and the redirect that
came out of §7 ("defer the world-sensor arc; fix construction first")
needs rewriting — the honest conclusion would instead be that these
signal families genuinely carry the same portfolio information.

    python -m scripts.construction_cut_1

SCREEN.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                        # noqa: E402
from backend.services import lane_factory_sim as LFS         # noqa: E402
from backend.services.information_classes import (           # noqa: E402
    CLASSES, build_extras, register)
from scripts.information_dimension_1 import (CANDIDATES,     # noqa: E402
                                             OWNED, eff_rank)

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
BOOKS = OUT / "construction_cut_1_books.jsonl"
SEED = 20260820
HANDLINGS = ("trim", "exempt")
GRAMMARS = {"cut": {"top_n": 50, "weighting": "rank"},
            "continuous": {"top_n": None, "weighting": "rank"}}


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-draws", type=int, default=400)
    a = ap.parse_args()

    register(LFS.SIGNALS)
    panel = LFS.load_panel()
    extras = build_extras(panel)
    signals = [s for names in CLASSES.values() for s in names]

    done = {}
    if BOOKS.exists():
        for line in BOOKS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["key"]] = r
        print(f"resuming: {len(done)} books on disk")

    OUT.mkdir(parents=True, exist_ok=True)
    series = {g: {} for g in GRAMMARS}
    errors = []
    with BOOKS.open("a", encoding="utf-8") as fh:
        for gname, cfg in GRAMMARS.items():
            n = 0
            for sig, h in product(signals, HANDLINGS):
                key = f"{gname}|{sig}|{h}"
                if key in done:
                    r = done[key]
                else:
                    try:
                        b = LFS.run_book(
                            panel, weighting=cfg["weighting"],
                            winner_handling=h, top_n=cfg["top_n"],
                            signal=sig, extras=extras)
                    except Exception as e:                     # noqa: BLE001
                        errors.append({"key": key,
                                       "error": f"{type(e).__name__}: {e}"})
                        continue
                    mr = b["monthly_returns"]
                    r = {"key": key, "grammar": gname, "signal": sig,
                         "handling": h,
                         "ann_vol": float(b["ann_vol"]),
                         "total_return": float(b["total_return"]),
                         "max_drawdown": float(b["max_drawdown"]),
                         "turnover": float(b["turnover_oneway_total"]),
                         "monthly": {str(int(pd.Timestamp(i).timestamp()
                                             * 1000)): float(v)
                                     for i, v in mr.items()}}
                    fh.write(json.dumps(r) + "\n")
                    fh.flush()
                series[gname][f"{sig}|{h}"] = pd.Series(
                    {pd.Timestamp(int(t), unit="ms"): v
                     for t, v in r["monthly"].items()}).sort_index()
                n += 1
                if n % 12 == 0:
                    print(f"  {gname}: {n}/{len(signals) * len(HANDLINGS)}")

    rng = np.random.default_rng(SEED)
    results = {}
    for gname in GRAMMARS:
        R = pd.DataFrame(series[gname]).dropna()
        if R.shape[1] < 10:
            continue
        sig_of = {c: c.split("|")[0] for c in R.columns}
        by_class = {cls: [c for c in R.columns if sig_of[c] in names]
                    for cls, names in CLASSES.items()}
        owned = [c for cls in OWNED for c in by_class[cls]]
        base = eff_rank(R[owned])["effective_rank"]
        ctrl_pool = by_class["price_extra"]

        g = {"n_books": int(R.shape[1]), "n_months": int(R.shape[0]),
             "dim_owned": round(base, 3), "classes": {}}
        for cls in CANDIDATES:
            cols = by_class[cls]
            if not cols:
                continue
            inc = eff_rank(R[owned + cols])["effective_rank"] - base
            entry = {"n_books": len(cols), "increment": round(float(inc), 3)}
            if cls != "price_extra":
                draws = np.empty(a.n_draws)
                for i in range(a.n_draws):
                    pick = list(rng.choice(
                        ctrl_pool, size=min(len(cols), len(ctrl_pool)),
                        replace=False))
                    draws[i] = (eff_rank(R[owned + pick])["effective_rank"]
                                - base)
                entry["control_mean"] = round(float(draws.mean()), 3)
                entry["p_value"] = round(float((draws >= inc).mean()), 4)
                entry["beats_control"] = bool(
                    inc > np.percentile(draws, 95))
            g["classes"][cls] = entry
        results[gname] = g

    any_beat = any(c.get("beats_control")
                   for g in results.values()
                   for c in g["classes"].values())
    cont = results.get("continuous", {}).get("classes", {})
    cut = results.get("cut", {}).get("classes", {})
    freed = [c for c in cont
             if cont[c].get("beats_control")
             and not cut.get(c, {}).get("beats_control")]
    if freed:
        verdict = (f"THE CUT WAS THE CULPRIT — {', '.join(freed)} "
                   f"separate(s) under the continuous grammar but not "
                   f"under the cut")
    elif not any_beat:
        verdict = ("THE CUT IS NOT THE CULPRIT — no information class "
                   "separates under EITHER grammar. The interpretation "
                   "offered by INFORMATION-DIMENSION-1 does not survive: "
                   "these signal families carry the same portfolio "
                   "information as extra price signals, and removing the "
                   "quantisation does not change that.")
    else:
        verdict = "MIXED — see per-class detail"

    res = {"trial": "CONSTRUCTION-CUT-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "grammars": {k: {kk: str(vv) for kk, vv in v.items()}
                        for k, v in GRAMMARS.items()},
           "results": results, "errors": errors, "verdict": verdict,
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    p = OUT / "construction_cut_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    for gname, g in results.items():
        print(f"\n{gname}: {g['n_books']} books, owned effective rank "
              f"{g['dim_owned']}")
        print(f"  {'class':14s} {'books':>5s} {'increment':>10s} "
              f"{'ctrl':>8s} {'p':>7s}  verdict")
        for cls, c in g["classes"].items():
            if "control_mean" not in c:
                print(f"  {cls:14s} {c['n_books']:>5d} "
                      f"{c['increment']:>10.3f} {'—':>8s} {'—':>7s}  "
                      f"CONTROL POOL")
            else:
                print(f"  {cls:14s} {c['n_books']:>5d} "
                      f"{c['increment']:>10.3f} {c['control_mean']:>8.3f} "
                      f"{c['p_value']:>7.3f}  "
                      f"{'BEATS' if c['beats_control'] else 'no'}")
    print(f"\nVERDICT: {verdict}")
    print(f"receipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
