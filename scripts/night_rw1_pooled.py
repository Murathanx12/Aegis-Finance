"""RW1 pooled — read the +0.15 rule on several draws, with its own dispersion.

Roadmap section 10.2 item 1 declared a strategy PRODUCT_PROMISING when its
beta-matched win rate exceeds the random-genome null on the same windows by
>= 0.15 in every start era. The 2026-09-09 second draw measured what a single
240-window draw is worth: Spearman 0.741 on the ordering, but a mean absolute
change of **0.099** and a max of **0.150** in a cell's excess -- the same size
as the threshold. A rule cannot be adjudicated by a measurement whose noise
equals it.

The amended rule (Fable 5.1, finance c24492d) is read here: pool >= 3 draws
(>= 720 windows), print the draw-to-draw dispersion per cell, and pass a cell
only if `excess - dispersion` still clears 0.15. `dispersion` is the standard
deviation of the per-draw excess, which is what "how much would another draw
have moved this?" actually means at this draw count.

    python -m scripts.night_rw1_pooled                      # every RW1 receipt on disk
    python -m scripts.night_rw1_pooled --runs 1 2 3
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
THRESHOLD = 0.15
MIN_DRAWS = 3
MIN_WINDOWS = 720
RECEIPT = re.compile(r"^RW1_random_windows_run(\d{2})\.json$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    try:
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)
    except Exception:  # noqa: BLE001
        return None


def load_draws(runs: list[int] | None) -> list[dict]:
    out = []
    for p in sorted(OUT.glob("RW1_random_windows_run*.json")):
        m = RECEIPT.match(p.name)
        if not m or (runs and int(m.group(1)) not in runs):
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        if not d.get("summary"):
            continue
        out.append({"run": int(m.group(1)), "seed": (d.get("windows") or {}).get("seed"),
                    "n_windows": (d.get("windows") or {}).get("n"), "summary": d["summary"], "path": str(p)})
    return out


def pooled(draws: list[dict]) -> dict:
    cells = sorted(set.intersection(*[set(d["summary"]) for d in draws])) if draws else []
    eras = sorted({e for d in draws for c in cells for e in (d["summary"][c].get("by_start_era") or {})})
    rows = {}
    for c in cells:
        overall = [d["summary"][c]["overall"]["excess_win_bm_over_null"] for d in draws]
        overall = [v for v in overall if v is not None]
        by_era = {}
        for e in eras:
            vals = [(d["summary"][c].get("by_start_era") or {}).get(e, {}).get("excess_win_bm_over_null")
                    for d in draws]
            vals = [v for v in vals if v is not None]
            if not vals:
                by_era[e] = {"draws": 0, "verdict": "NOT MEASURED on any draw"}
                continue
            mean = float(np.mean(vals))
            sd = float(np.std(vals, ddof=1)) if len(vals) > 1 else None
            by_era[e] = {"draws": len(vals), "per_draw": [_r(v, 3) for v in vals],
                         "pooled_excess": _r(mean, 4), "dispersion_sd": _r(sd, 4),
                         "excess_minus_dispersion": _r(mean - sd, 4) if sd is not None else None,
                         "clears_threshold": (bool(sd is not None and (mean - sd) >= THRESHOLD)
                                              if sd is not None else None)}
        m_o = float(np.mean(overall)) if overall else None
        sd_o = float(np.std(overall, ddof=1)) if len(overall) > 1 else None
        era_flags = [v.get("clears_threshold") for v in by_era.values() if v.get("draws")]
        rows[c] = {
            "overall": {"per_draw": [_r(v, 3) for v in overall], "pooled_excess": _r(m_o, 4),
                        "dispersion_sd": _r(sd_o, 4),
                        "excess_minus_dispersion": _r(m_o - sd_o, 4) if sd_o is not None else None,
                        "sign_agrees_across_draws": bool(overall and (min(overall) > 0 or max(overall) < 0))},
            "by_start_era": by_era,
            "PASSES_10.2_ITEM_1": bool(era_flags and all(era_flags)),
            "eras_clearing": int(sum(1 for f in era_flags if f)), "eras_measured": len(era_flags),
        }
    n_draws = len(draws)
    n_windows = sum(int(d["n_windows"] or 0) for d in draws)
    enough = n_draws >= MIN_DRAWS and n_windows >= MIN_WINDOWS
    passing = [c for c, v in rows.items() if v["PASSES_10.2_ITEM_1"]]
    best = max(rows.items(), key=lambda kv: (kv[1]["overall"]["excess_minus_dispersion"] or -9)) if rows else None
    return {
        "job": "RW1_pooled", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "rule": (f"roadmap 10.2 item 1 as amended: pool >= {MIN_DRAWS} draws (>= {MIN_WINDOWS} windows), print "
                 f"the draw-to-draw dispersion per cell, and a cell passes only if "
                 f"excess - dispersion >= {THRESHOLD} in EVERY start era"),
        "draws": [{"run": d["run"], "seed": d["seed"], "n_windows": d["n_windows"]} for d in draws],
        "draws_pooled": n_draws, "windows_pooled": n_windows,
        "enough_to_adjudicate": enough,
        "cells": rows,
        "cells_passing": passing,
        "headline": (f"{n_draws} draws, {n_windows} windows; {len(passing)} of {len(rows)} cells clear "
                     f"'excess - dispersion >= {THRESHOLD} in every era'"
                     + (f"; best by excess-minus-dispersion: {best[0]} "
                        f"{best[1]['overall']['excess_minus_dispersion']}" if best else "")),
        "verdict": (("CANNOT DETERMINE: " if not enough else "") +
                    (f"only {n_draws} draw(s) / {n_windows} windows on disk; the amended rule needs "
                     f"{MIN_DRAWS} draws and {MIN_WINDOWS} windows, and a single draw's own noise "
                     f"(mean 0.099, max 0.150 between draws 1 and 2) is the size of the threshold"
                     if not enough else
                     (f"PRODUCT_PROMISING for {passing}" if passing else
                      "NO CELL clears the threshold once its own draw-to-draw dispersion is subtracted"))),
        "family_max_p": None, "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, nargs="*", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    draws = load_draws(a.runs)
    if not draws:
        print("REFUSED: no RW1 receipts on disk")
        return 2
    p = pooled(draws)
    out = Path(a.out) if a.out else OUT / "RW1_pooled_run01.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\nRW1_pooled: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    for c, v in sorted(p["cells"].items(), key=lambda kv: -(kv[1]["overall"]["excess_minus_dispersion"] or -9)):
        o = v["overall"]
        print(f"  {c[:52]:52s} pooled {o['pooled_excess']:+.3f} sd {o['dispersion_sd']} "
              f"-> {o['excess_minus_dispersion']}  eras {v['eras_clearing']}/{v['eras_measured']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
