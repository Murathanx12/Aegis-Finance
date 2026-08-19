"""AEGIS-NET-TOURNAMENT-1 runner — signed run, or full-shape rehearsal.

    python -m scripts.net_tournament_run --rehearsal     # synthetic, no gate
    python -m scripts.net_tournament_run --head cs_rank  # REFUSES unsigned

THE REHEARSAL (same logic as the resolver's dress rehearsal)
============================================================
Friday's lesson generalizes: every piece of the tournament passes its tests,
but the SEQUENCE — panel → folds → five arms → contrasts → receipt — had
never run end to end. The rehearsal runs it on a SYNTHETIC panel of the real
panel's exact shape (145 monthly dates × ~170 names × the 7 features, with a
planted weak linear signal), so what is proven is the plumbing and the
wall-clock, and nothing about the market. The receipt is stamped REHEARSAL
and the registered panel is never opened.

THE REAL RUN
============
Refused until `assert_signed` finds a human on the prereg's SIGNED-BY line.
After signature: one command, all declared heads, receipt to the daemon dir.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config                       # noqa: E402
from backend.services import net_panel as NP                # noqa: E402
from backend.services import net_tournament as NT           # noqa: E402

OUT_DIR = _config.OPTIMUS_LEDGER_DIR / "net_tournament"

#: The heads a signed run executes, in declared order. cs_rank is the
#: deciding head per the prereg; the rest are reported, never deciding.
HEADS = ("cs_rank", "forward_return", "forward_realised_vol",
         "forward_max_drawdown")


#: Synthetic worlds with a DECLARED answer. `linear` — ridge should win or
#: tie. `nonlinear` — the signal is a pure interaction, invisible to a
#: linear map; tree/MLP should recover more of it. `null` — no signal at
#: all; no arm may earn COMPLEX_WINS. `barrier` — barrier timing driven by
#: a feature; the survival arm should beat the timing-blind comparator on
#: held-out concordance. This is the start of G1's known-answer battery.
WORLDS = ("linear", "nonlinear", "null", "barrier")


def synthetic_panel(seed: int = 20260819, world: str = "linear",
                    n_dates: int = 145, n_names: int = 170) -> pd.DataFrame:
    """The real panel's SHAPE with a planted, DECLARED signal. Nothing market."""
    if world not in WORLDS:
        raise SystemExit(f"unknown world {world!r}; declared: {WORLDS}")
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2014-06-30", periods=n_dates, freq="ME")
    names = [f"S{i:03d}" for i in range(n_names)]
    rows = []
    for d in dates:
        f = {c: rng.normal(size=len(names)) for c in NP.FEATURE_COLUMNS}
        if world == "linear":
            # weak planted signal: IC ~0.05 on mom_63, the realistic regime
            y = 0.05 * f["mom_63"] + rng.normal(size=len(names))
        elif world == "nonlinear":
            # pure interaction + threshold: zero linear projection by
            # construction (both factors are centred), so ridge sees noise
            y = (0.35 * f["mom_63"] * f["vol_63"]
                 + 0.25 * (np.abs(f["mom_21"]) > 1.0)
                 + rng.normal(size=len(names)))
        else:                               # null and barrier: no rank signal
            y = rng.normal(size=len(names))
        ranks = pd.Series(y).rank(pct=True).to_numpy()

        # barrier labels: in the barrier world the UP hazard is driven by
        # mom_63 (high → hits early); elsewhere barrier outcome is noise.
        if world == "barrier":
            up_p = 1.0 / (1.0 + np.exp(-(f["mom_63"] - 0.4)))
            hit_up = rng.random(len(names)) < 0.45 * up_p
            hit_dn = (~hit_up) & (rng.random(len(names)) < 0.15)
            days = np.clip(rng.integers(1, 21, len(names)), 1, 20)
        else:
            hit_up = rng.random(len(names)) < 0.10
            hit_dn = (~hit_up) & (rng.random(len(names)) < 0.10)
            days = rng.integers(1, 21, len(names))
        outc = np.where(hit_up, "up", np.where(hit_dn, "down", "neither"))

        for i, n in enumerate(names):
            row = {"date": d, "ticker": n,
                   **{c: f[c][i] for c in NP.FEATURE_COLUMNS},
                   "forward_return": y[i] * 0.02,
                   "forward_realised_vol": abs(rng.normal(0.25, 0.05)),
                   "forward_max_drawdown": -abs(rng.normal(0.05, 0.02)),
                   "cs_rank": ranks[i],
                   "barrier_up20_down10": outc[i],
                   "barrier_up20_down10_days": (int(days[i])
                                                if outc[i] != "neither"
                                                else np.nan)}
            rows.append(row)
    return pd.DataFrame(rows)


def run(df: pd.DataFrame, *, heads, first_test_year: int, tag: str,
        with_barrier: bool = True) -> dict:
    out = {"tournament": NT.TOURNAMENT, "mode": tag,
           "first_test_year": first_test_year,
           "started_at": datetime.now(timezone.utc).isoformat(
               timespec="seconds"),
           "heads": {}}
    for head in heads:
        t0 = time.perf_counter()
        res = NT.run_head(df, feature_cols=list(NP.FEATURE_COLUMNS),
                          target_col=head, horizon_days=20,
                          first_test_year=first_test_year)
        res["elapsed_s"] = round(time.perf_counter() - t0, 1)
        if head == "cs_rank":
            res["verdicts"] = NT.head_verdicts(res["ic_contrast_vs_baseline"])
        out["heads"][head] = res
        print(f"  head {head:24s} {res['elapsed_s']:7.1f}s  "
              f"folds {len(res['folds'])}  rows {res['n_rows_scored']}")
        for arm, a in res["arms"].items():
            ic = a["ic_mean"]
            line = (f"    {arm:14s} ic {ic:+.4f}" if ic is not None
                    else f"    {arm:14s} ic n/a")
            v = res.get("verdicts", {}).get(arm)
            if v:
                line += (f"  dIC {v['mean_dIC']:+.4f} (mde {v['mde']:.4f})"
                         f"  -> {v['verdict']}")
            print(line)
    if with_barrier and "barrier_up20_down10" in df.columns:
        t0 = time.perf_counter()
        br = NT.run_barrier_head(df, list(NP.FEATURE_COLUMNS),
                                 barrier="up20_down10", horizon_days=20,
                                 first_test_year=first_test_year)
        br["elapsed_s"] = round(time.perf_counter() - t0, 1)
        out["heads"]["barrier_up20_down10"] = br
        for cause, s in br["summary"].items():
            if s.get("n_folds_scored"):
                print(f"  barrier[{cause}]  cox {s['mean_holdout_cox']:.3f}"
                      f" vs mn {s['mean_holdout_multinomial']:.3f}"
                      f"  (folds {s['n_folds_scored']},"
                      f" refused {s['n_folds_refused']})")
            else:
                print(f"  barrier[{cause}]  NOT_ANSWERABLE_AT_N "
                      f"(refused {s['n_folds_refused']} folds)")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="net_tournament_run")
    ap.add_argument("--rehearsal", action="store_true",
                    help="synthetic full-shape run; no signature needed")
    ap.add_argument("--world", default="linear", choices=WORLDS,
                    help="rehearsal world (declared answer); default linear")
    ap.add_argument("--head", default="", help="single head (signed run)")
    a = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    if a.rehearsal:
        print("=" * 74)
        print(f"REHEARSAL — synthetic {a.world!r} world, real pipeline. "
              f"Nothing here is evidence about the world.")
        print("=" * 74)
        df = synthetic_panel(world=a.world)
        out = run(df, heads=("cs_rank",), first_test_year=2018,
                  tag=f"REHEARSAL_SYNTHETIC_{a.world.upper()}",
                  with_barrier=(a.world == "barrier"))
        out["world"] = a.world
        p = OUT_DIR / f"REHEARSAL_{a.world}_{stamp}.json"
        p.write_text(json.dumps(out, indent=2, default=str),
                     encoding="utf-8")
        print(f"\nrehearsal receipt: {p.name} (stamped REHEARSAL; not a "
              f"tournament result)")
        return 0

    # ── the real thing: gate first, before the panel is even opened ────────
    signer = NT.assert_signed()          # raises while unsigned
    panel_path = _config.OPTIMUS_LEDGER_DIR / "net_panel" / "net_panel_v1.parquet"
    df = pd.read_parquet(panel_path)
    heads = (a.head,) if a.head else HEADS
    print(f"signed by: {signer}")
    out = run(df, heads=heads, first_test_year=2016, tag="REGISTERED")
    out["signed_by"] = signer
    p = OUT_DIR / f"tournament_{stamp}.json"
    p.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\nreceipt: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
