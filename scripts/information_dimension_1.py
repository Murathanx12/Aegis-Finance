"""INFORMATION-DIMENSION-1 — does a new information class buy a new
DIRECTION, or just re-express one we already own?

Order 24, replacing MEGA-SWEEP-2's headline. The replacement is forced by
a measurement, not a preference: STRATEGY-EFFECTIVE-DIMENSION-1 found the
86-book mega-sweep-1 corpus collapsing to an effective rank of ~3.5, with
one eigenvalue carrying 61% of the variance. Running 1,500-3,000 more
combinations of the same seven signals cannot raise a dimensionality the
signal set has already exhausted. It would buy a longer leaderboard and a
worse selection problem, which is precisely the outcome both reviews of
Order 23 warned about.

So the compute goes here instead.

DESIGN
------
Books are built from signals grouped by INFORMATION CLASS:

    price_base     mom_12_1, mom_63, rev_21, low_vol      (owned)
    fundamental    value_bm, quality_roe                  (owned)
    price_extra    mom_252, rev_63, dd_recovery, vol_21_low
    options        opt_iv_low, opt_skew_low, opt_pc_low
    expectations   exp_breadth, exp_disp_low, exp_revision
    liquidity      liq_dvol_high, liq_dvol_trend

`price_extra` is the MATCHED CONTROL and is the whole reason this
measures anything. Adding ANY signals raises effective rank a little,
because more distinct portfolios span more directions. Comparing a new
class against nothing would therefore always "work". Comparing it
against an equal-sized dose of a class we already own does not.

PRIMARY READOUT
---------------
For each candidate class C, the increment

    dim(owned + C) - dim(owned)

against the control increment

    dim(owned + price_extra) - dim(owned)

A class earns its keep only if its increment exceeds the control's. The
interval comes from bootstrapping DATE BLOCKS and recomputing the whole
eigenspectrum, because effective rank is a path/statistic functional and
not a per-date mean.

NOT A RETURN CLAIM. This measures structure. Whether any of these signals
earns money is a different question needing its own pre-registration;
nothing here screens for profitability, and no leaderboard is printed.

    python -m scripts.information_dimension_1
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

OUT = _config.OPTIMUS_LEDGER_DIR / "structure"
BOOKS = OUT / "information_dimension_1_books.jsonl"
SEED = 20260820

WEIGHTINGS = ("equal", "inverse_vol", "rank")
HANDLINGS = ("trim", "exempt")
TOP_NS = (50, 100)
OWNED = ("price_base", "fundamental")
CANDIDATES = ("price_extra", "options", "expectations", "liquidity")


def eff_rank(R: pd.DataFrame) -> dict:
    """Participation ratio and entropy effective rank of the correlation
    spectrum. Both answer "how many independent behaviours", differently."""
    if R.shape[1] < 2:
        return {"participation_ratio": 1.0, "effective_rank": 1.0}
    C = np.corrcoef(R.to_numpy(float), rowvar=False)
    C = np.nan_to_num(C, nan=0.0)
    np.fill_diagonal(C, 1.0)
    w = np.clip(np.linalg.eigvalsh(C), 0, None)
    s = w.sum()
    if s <= 0:
        return {"participation_ratio": 1.0, "effective_rank": 1.0}
    p = w / s
    ent = float(-(p[p > 0] * np.log(p[p > 0])).sum())
    return {"participation_ratio": float((s ** 2) / float((w ** 2).sum())),
            "effective_rank": float(np.exp(ent))}


def _boot_increment(R: pd.DataFrame, cols_base, cols_add, blk: int,
                    n_boot: int, rng) -> np.ndarray:
    T = len(R)
    base = list(cols_base)
    both = base + list(cols_add)
    n_blocks = int(np.ceil(T / max(blk, 1)))
    out = np.empty(n_boot)
    A = R[both]
    for i in range(n_boot):
        starts = rng.integers(0, max(T - blk, 1), size=n_blocks)
        idx = np.concatenate([np.arange(s, s + blk) for s in starts])[:T]
        idx = np.clip(idx, 0, T - 1)
        S = A.iloc[idx]
        out[i] = (eff_rank(S[both])["effective_rank"]
                  - eff_rank(S[base])["effective_rank"])
    return out


def main() -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                      # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-boot", type=int, default=400)
    ap.add_argument("--resume", action="store_true", default=True)
    a = ap.parse_args()

    register(LFS.SIGNALS)
    print("loading panel + extras (options / expectations / liquidity)...")
    panel = LFS.load_panel()
    extras = build_extras(panel)
    print("extras ready")

    all_signals = [s for names in CLASSES.values() for s in names]
    cells = [{"signal": s, "weighting": w, "winner_handling": h,
              "top_n": n}
             for s, w, h, n in product(all_signals, WEIGHTINGS,
                                       HANDLINGS, TOP_NS)]
    print(f"grammar: {len(all_signals)} signals x {len(WEIGHTINGS)} "
          f"weightings x {len(HANDLINGS)} handlings x {len(TOP_NS)} "
          f"top_n = {len(cells)} books")

    OUT.mkdir(parents=True, exist_ok=True)
    done = {}
    if a.resume and BOOKS.exists():
        for line in BOOKS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["key"]] = r
        print(f"resuming: {len(done)} books already on disk")

    series, meta, errors = {}, {}, []
    with BOOKS.open("a", encoding="utf-8") as fh:
        for i, c in enumerate(cells):
            k = (f"{c['signal']}|{c['weighting']}|{c['winner_handling']}"
                 f"|{c['top_n']}")
            if k in done:
                r = done[k]
            else:
                try:
                    b = LFS.run_book(panel, weighting=c["weighting"],
                                     winner_handling=c["winner_handling"],
                                     top_n=c["top_n"], signal=c["signal"],
                                     extras=extras)
                except Exception as e:                         # noqa: BLE001
                    errors.append({"key": k, "error":
                                   f"{type(e).__name__}: {e}"})
                    continue
                mr = b.pop("monthly_returns")
                b.pop("nav", None)
                r = {"key": k, **{kk: vv for kk, vv in b.items()
                                  if not isinstance(vv, (pd.Series,
                                                         pd.DataFrame))},
                     "monthly": {str(int(pd.Timestamp(ix).timestamp()
                                         * 1000)): float(v)
                                 for ix, v in mr.items()}}
                fh.write(json.dumps(r, default=str) + "\n")
                fh.flush()
            m = r["monthly"]
            series[k] = pd.Series(
                {pd.Timestamp(int(ts), unit="ms"): v
                 for ts, v in m.items()}).sort_index()
            meta[k] = r
            if (i + 1) % 24 == 0:
                print(f"  {i + 1}/{len(cells)} books")

    R = pd.DataFrame(series).dropna()
    print(f"\ncorpus: {R.shape[1]} books x {R.shape[0]} months")
    if errors:
        print(f"errors: {len(errors)} (recorded, not swallowed)")

    sig_of = {k: k.split("|")[0] for k in R.columns}
    cols_by_class = {cls: [k for k in R.columns if sig_of[k] in names]
                     for cls, names in CLASSES.items()}
    for cls, cols in cols_by_class.items():
        print(f"  {cls:14s} {len(cols):3d} books")

    owned_cols = [c for cls in OWNED for c in cols_by_class[cls]]
    dates = np.array(R.index.values, dtype="datetime64[D]")
    from backend.services.net_tournament import bootstrap_block_dates
    blk = bootstrap_block_dates(dates, 21)
    rng = np.random.default_rng(SEED)

    base_dim = eff_rank(R[owned_cols])
    ctrl_pool = cols_by_class["price_extra"]

    def control_increment_distribution(k: int, n_draws: int) -> np.ndarray:
        """Increment from adding k RANDOM control books.

        Size matching is mandatory, not cosmetic: effective rank rises
        mechanically with the number of series added, so a 48-book
        control against a 24-book candidate would hand the control the
        result. Each draw takes a random size-k subset of the control
        pool, so the candidate is compared against the same DOSE of a
        class we already own.
        """
        out = np.empty(n_draws)
        for i in range(n_draws):
            pick = list(rng.choice(ctrl_pool, size=min(k, len(ctrl_pool)),
                                   replace=False))
            out[i] = (eff_rank(R[owned_cols + pick])["effective_rank"]
                      - base_dim["effective_rank"])
        return out

    results = {}
    for cls in CANDIDATES:
        cols = cols_by_class[cls]
        if not cols:
            continue
        both = eff_rank(R[owned_cols + cols])
        draws = _boot_increment(R, owned_cols, cols, blk, a.n_boot, rng)
        inc = float(both["effective_rank"] - base_dim["effective_rank"])
        r = {"n_books": len(cols),
             "dim_owned": round(base_dim["effective_rank"], 3),
             "dim_owned_plus_class": round(both["effective_rank"], 3),
             "increment": round(inc, 3),
             "increment_ci": [round(float(np.percentile(draws, 2.5)), 3),
                              round(float(np.percentile(draws, 97.5)), 3)],
             "participation_ratio_owned_plus_class": round(
                 both["participation_ratio"], 3)}
        if cls != "price_extra":
            ctrl = control_increment_distribution(len(cols), a.n_boot)
            p = float((ctrl >= inc).mean())
            r["vs_size_matched_control"] = {
                "control_books_drawn": len(cols),
                "control_increment_mean": round(float(ctrl.mean()), 3),
                "control_increment_p95": round(
                    float(np.percentile(ctrl, 95)), 3),
                "excess_over_control_mean": round(
                    float(inc - ctrl.mean()), 3),
                "p_value": round(p, 4),
                "beats_control": bool(inc > np.percentile(ctrl, 95))}
        else:
            r["vs_size_matched_control"] = None
        results[cls] = r

    res = {"trial": "INFORMATION-DIMENSION-1", "mode": "SCREEN",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "question": "does a new information class buy a new DIRECTION "
                       "in portfolio-behaviour space, or re-express one "
                       "we already own?",
           "not_a_return_claim": "this measures structure only; "
                                 "profitability of any family here needs "
                                 "its own pre-registration",
           "control": "price_extra — a SIZE-MATCHED dose of a class "
                      "already owned. Adding any signals raises effective "
                      "rank, so a vs-nothing comparison always 'works'; "
                      "and rank rises with the NUMBER added, so an "
                      "unmatched 48-book control against a 24-book "
                      "candidate would hand the control the result. Each "
                      "candidate is compared against random subsets of "
                      "the control pool of its OWN size.",
           "n_books": int(R.shape[1]), "n_months": int(R.shape[0]),
           "owned_classes": list(OWNED),
           "dim_owned": base_dim,
           "classes": results,
           "errors": errors,
           "label": "SIMULATION — LANE-FACTORY-SIM-1, never a track record"}
    p = OUT / "information_dimension_1_2026-08-20.json"
    p.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\nowned ({len(owned_cols)} books) effective rank: "
          f"{base_dim['effective_rank']:.3f}")
    print(f"\n{'class':14s} {'books':>5s} {'increment':>10s} "
          f"{'ctrl(same n)':>13s} {'excess':>8s} {'p':>7s} {'verdict':>14s}")
    for cls, r in results.items():
        vc = r.get("vs_size_matched_control")
        if vc is None:
            print(f"{cls:14s} {r['n_books']:>5d} {r['increment']:>10.3f} "
                  f"{'—':>13s} {'—':>8s} {'—':>7s} {'CONTROL POOL':>14s}")
            continue
        tag = "BEATS CONTROL" if vc["beats_control"] else "no new direction"
        print(f"{cls:14s} {r['n_books']:>5d} {r['increment']:>10.3f} "
              f"{vc['control_increment_mean']:>13.3f} "
              f"{vc['excess_over_control_mean']:>8.3f} "
              f"{vc['p_value']:>7.3f} {tag:>14s}")
    print(f"\nreceipt -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
