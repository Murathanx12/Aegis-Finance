"""One survivor out of 206. Is that more than noise produces?

    python -m scripts.library_placebo_null --reps 10

THE QUESTION THE LIBRARY RESULT FORCES
======================================
The screen kept 11 of 206 at FDR 0.10 and exactly one of those was detectable
NET in the liquid tercile, at 1.01x its own MDE. Read one way that is a
benchmark. Read the other way it is what 206 chances produce when nothing is
there. The two readings are not distinguishable from the number alone, and
"~1.1 expected false" is the FDR's own accounting rather than a measurement of
this pipeline.

So measure it. Run the IDENTICAL machinery on signals with the only thing that
matters removed.

WHAT THIS NULL HOLDS FIXED, DECLARED (S57)
==========================================
N21's placebo drew uniform windows against a clustered world and matched at lag
1, so every shallow check cleared it. A null that does not declare what it
preserves cannot be audited, so:

  PRESERVED, exactly
    * the return panel -- every crash, every regime, all of its clustering
    * the universe screen, the deciles, the weighting, the turnover, the cost
    * each predictor's COVERAGE pattern: the same names carry a value in the
      same months, which matters enormously here because coverage ranges from
      45% to 93% and correlates with liquidity
    * each predictor's cross-sectional DISTRIBUTION within each month
    * the number of tests, 206, and the screen applied to them

  DESTROYED, only this
    * which stock gets which signal value, permuted within each month

So a survivor under this null is a survivor produced by the pipeline, the
multiplicity and the panel -- with no information about stocks in it at all.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from backend.services.research_gym.multiplicity import (SCREEN,
                                                        ConfirmationBudget,
                                                        window_id)
from scripts.library_measure_2006_2019 import (END, MIN_DVOL_PCTILE,
                                               MIN_PRICE, OUT, START,
                                               decile_ls, load_osap,
                                               load_panel, osap_columns, score)

Q = 0.10
SEED = 20260817


def two_sided_p(z: float) -> float:
    return 1.0 if not np.isfinite(z) else float(math.erfc(abs(z) / math.sqrt(2)))


def build_masks(months, perms, ret, prc, dvl):
    n_m, n_p = len(months), len(perms)
    R = ret.reindex(index=months, columns=perms).to_numpy()
    P = prc.reindex(index=months, columns=perms).to_numpy()
    V = dvl.reindex(index=months, columns=perms).to_numpy()
    FWD = np.vstack([R[1:], np.full((1, n_p), np.nan)])
    base = np.isfinite(P) & (P >= MIN_PRICE) & np.isfinite(V)
    rank = np.full((n_m, n_p), np.nan)
    for t in range(n_m):
        m = base[t]
        if m.sum() > 10:
            rank[t, m] = pd.Series(V[t, m]).rank(pct=True).to_numpy() * 100
    ok = base & (rank >= MIN_DVOL_PCTILE)
    liq = ok & (rank >= 73.3)
    return FWD, ok, liq


def permute_within_month(S: np.ndarray, rng) -> np.ndarray:
    """NULL A — scramble which stock holds each value, INDEPENDENTLY each month.

    Coverage and the within-month distribution survive untouched; only the
    stock-to-value mapping is destroyed. Permuting the whole matrix instead
    would also destroy the coverage pattern, and coverage here correlates with
    liquidity strongly enough that the null would then be testing two things.

    WHAT IT ALSO DESTROYS, AND WHY THAT MATTERS: persistence. A real value
    stock is still a value stock next month; a re-permuted one is not, so this
    placebo rotates its book completely every month and pays roughly 2%/yr more
    in costs than a low-turnover signal like GP. The SCREEN is unaffected --
    its p-values come from the GROSS monthly mean -- but the liquid-tercile
    gate tests the NET return, so on that gate this null is biased in the
    convenient direction. Null B exists because noticing that is not the same
    as fixing it.
    """
    out = np.full_like(S, np.nan)
    for t in range(S.shape[0]):
        idx = np.flatnonzero(np.isfinite(S[t]))
        if len(idx) > 1:
            out[t, rng.permutation(idx)] = S[t, idx]
        elif len(idx):
            out[t, idx] = S[t, idx]
    return out


def permute_fixed_labels(S: np.ndarray, rng) -> np.ndarray:
    """NULL B — one permutation of the stock labels, applied to every month.

    Stock j now carries the entire history of some other stock's signal, so
    persistence, autocorrelation and therefore TURNOVER are preserved almost
    exactly, while the link between a stock's signal and that stock's return is
    gone. This is the null the net-return gate needs.

    Its own cost: coverage travels with the permutation, so a signal defined
    only for microcaps becomes defined for a random set of names and the
    tercile composition shifts. Neither null dominates, which is why both run
    and both are reported. Agreement between them is the claim; a disagreement
    would be a finding about which property carries the result.
    """
    perm = rng.permutation(S.shape[1])
    return S[:, perm]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--null", choices=["A", "B", "both"], default="both")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    real = json.loads(OUT.read_text(encoding="utf-8"))["results"]
    ret, prc, dvl = load_panel()
    months = pd.period_range(f"{str(START)[:4]}-{str(START)[4:]}",
                             f"{str(END)[:4]}-{str(END)[4:]}", freq="M")
    perms = sorted(set(ret.columns))
    pidx = {p: i for i, p in enumerate(perms)}
    n_m, n_p = len(months), len(perms)
    FWD, OK, LIQ = build_masks(months, perms, ret, prc, dvl)

    cols = osap_columns()
    print(f"loading {len(cols)} predictors as scatter matrices...")
    mats: dict[str, np.ndarray] = {}
    for s in range(0, len(cols), 25):
        chunk = cols[s:s + 25]
        d = load_osap(chunk)
        mi = ((d.yyyymm // 100 - int(str(START)[:4])) * 12
              + (d.yyyymm % 100 - int(str(START)[4:]))).to_numpy()
        pi = d.permno.map(pidx).to_numpy()
        g = np.isfinite(pi.astype("float64")) & (mi >= 0) & (mi < n_m)
        mi2, pi2 = mi[g].astype(int), pi[g].astype(int)
        for c in chunk:
            S = np.full((n_m, n_p), np.nan)
            S[mi2, pi2] = d[c].to_numpy(dtype="float64")[g]
            mats[c] = S

    modes = ["A", "B"] if a.null == "both" else [a.null]
    scramble = {"A": permute_within_month, "B": permute_fixed_labels}
    all_reps: dict[str, list] = {}
    reps: list = []
    for mode in modes:
      rng = np.random.default_rng(SEED)
      reps = []
      print(f"\nNULL {mode} — " + (
          "independent per-month permutation (coverage preserved, "
          "persistence destroyed)" if mode == "A" else
          "one fixed label permutation (persistence and TURNOVER preserved)"))
      print(f"{'rep':>4} {'screen survivors':>17} {'liquid-detectable':>18} "
            f"{'best net (liquid)':>18} {'mean turnover':>14}")
      for r in range(a.reps):
        rows, turns = {}, []
        for c, S in mats.items():
            rets, turn = decile_ls(scramble[mode](S, rng), FWD, OK)
            v = score(rets, turn, rng)
            if v.get("insufficient") or not np.isfinite(v.get("z", np.nan)):
                continue
            v["p"] = two_sided_p(v["z"])
            rows[c] = v
            turns.append(v["monthly_turnover"])
        cb = ConfirmationBudget(Path(tempfile.mkdtemp()) / "n.jsonl")
        W = window_id(universe=f"placebo_{mode}_rep{r}",
                      period=f"{START}..{END}",
                      outcome="ls_decile_net_annual")
        cb.declare_budget(W, budget=len(rows), declared_by="placebo",
                          purpose=SCREEN, rate=Q)
        for nm, v in rows.items():
            cb.reserve(W, trial=nm, hypothesis="h")
            cb.record_result(W, trial=nm, hypothesis="h", p_value=v["p"])
        rep = cb.decide(W)
        surv = [d["trial"] for d in rep["decisions"] if d["rejected"]]

        # The same second gate the real run used: detectable NET inside the
        # liquid tercile.
        best, n_liq = None, 0
        for c in surv:
            rr, tt = decile_ls(scramble[mode](mats[c], rng), FWD, LIQ)
            lv = score(rr, tt, rng)
            if lv.get("detectable") and (lv.get("net_annual") or 0) > 0:
                n_liq += 1
                if best is None or lv["net_annual"] > best:
                    best = lv["net_annual"]
        mt = float(np.nanmean(turns)) if turns else float("nan")
        reps.append({"rep": r, "n_measured": len(rows),
                     "screen_survivors": rep["n_rejected"],
                     "liquid_detectable": n_liq, "best_liquid_net": best,
                     "mean_monthly_turnover": mt})
        print(f"{r:>4} {rep['n_rejected']:>17} {n_liq:>18} "
              f"{('%+.2f%%' % (100 * best)) if best is not None else 'none':>18}"
              f" {mt:>14.2f}")
      all_reps[mode] = reps

    real_ok = {k: v for k, v in real.items()
               if not v.get("refused") and not v.get("insufficient")
               and np.isfinite(v.get("z", np.nan))}
    real_turn = float(np.nanmean([v["monthly_turnover"]
                                  for v in real_ok.values()]))
    print("\n" + "=" * 74)
    print("PLACEBO vs REAL — identical pipeline, identical screen")
    print("=" * 74)
    summary = {}
    for mode, rr in all_reps.items():
        scr = np.array([x["screen_survivors"] for x in rr])
        liq = np.array([x["liquid_detectable"] for x in rr])
        bests = [x["best_liquid_net"] for x in rr if x["best_liquid_net"]]
        tn = float(np.nanmean([x["mean_monthly_turnover"] for x in rr]))
        p_scr = float((scr >= 11).mean())
        p_liq = float((liq >= 1).mean())
        summary[mode] = {"p_screen_ge_real": p_scr, "p_liquid_ge_real": p_liq,
                         "screen_mean": float(scr.mean()),
                         "liquid_mean": float(liq.mean()),
                         "mean_turnover": tn}
        print(f"\n  NULL {mode}")
        print(f"    screen survivors    {scr.mean():>5.1f} "
              f"(range {scr.min()}-{scr.max()})      REAL 11")
        print(f"    liquid-detectable   {liq.mean():>5.1f} "
              f"(range {liq.min()}-{liq.max()})      REAL  1")
        print(f"    mean turnover/mo    {tn:>5.2f}"
              f"                REAL {real_turn:.2f}"
              + ("   <- matched" if abs(tn - real_turn) < 0.35
                 else "   <- NOT matched; this null pays more cost"))
        if bests:
            print(f"    best net in liquid  {100 * max(bests):+5.2f}% (max)"
                  f"        REAL +8.64%")
        # One-sided empirical p. With `reps` draws the resolution is 1/reps and
        # it is quoted as such rather than dressed up as a small number.
        print(f"    P(>= 11 screen survivors) = {p_scr:.2f}   "
              f"P(>= 1 liquid-detectable) = {p_liq:.2f}   "
              f"(resolution 1/{a.reps})")

    print("\n  The liquid-detectable line is the one that decides whether the")
    print("  library's single tradable survivor is a benchmark or an artefact,")
    print("  and NULL B is the one entitled to decide it — A rotates its book")
    print("  every month and pays a cost the real signals do not.")

    out = OUT.parent / "placebo_null.json"
    out.write_text(json.dumps(
        {"reps": all_reps, "summary": summary,
         "real_screen_survivors": 11, "real_liquid_detectable": 1,
         "real_n_measured": len(real_ok),
         "real_mean_monthly_turnover": real_turn,
         "preserved": ["return panel and all its clustering", "universe screen",
                       "decile construction", "weighting", "turnover", "cost",
                       "per-predictor coverage pattern",
                       "per-month cross-sectional distribution",
                       "number of tests and the screen applied"],
         "destroyed": ["which stock holds which signal value, within month"]},
        indent=1, default=float), encoding="utf-8")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
