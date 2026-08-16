"""N20 — is the forgone return in N4B's break-even the return you actually forgo?

    python -m scripts.n20_conditional_mu_rest --power-only   # design stage
    python -m scripts.n20_conditional_mu_rest                # run stage

Registered at `docs/TRIALS/PREREG_N20_CONDITIONAL_MU_REST.md` before this file
computed anything. Read that first.

THE POINT
=========
N4B prices the action "when a precursor fires, cut exposure for H days" with

    L_min = (mu_rest + c) / ( q * (|mu_tail| + mu_rest) )

and computes `mu_rest` at `n4b_coverage_equivalence.py:205` as `f[~mask].mean()`
— the mean non-tail forward return over EVERY day. But exposure is only removed
on days the precursor FIRED. The return the action forgoes is therefore

    E[R | fire, not tail]        not        E[R | not tail]

and those are equal only if firing is independent of the non-tail return
distribution. N4B assumed that implicitly. This measures it.

WHAT THIS TRIAL GIVES UP
========================
N4B's `mu_rest` is immune to the signal, which is what made its margin
prospective. Conditioning on `fire` forfeits that immunity: the margin now
depends on the precursor library. That is a real cost, not a correction, so
BOTH estimands are reported and neither may be selected after seeing the other.

THE TWO-STAGE GUARD
===================
`--power-only` computes the fire rate and the outcome dispersion — the inputs a
power declaration needs — and is structurally unable to compute the conditional
mean: it never calls `_conditional_mu_rest`. The declared effect size is derived
from the frozen formula, not from the data. Run it, paste the numbers into the
prereg, commit, THEN run the test. The order is the point.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import autopsy as AU

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n20_conditional_mu_rest.json"
AUTOPSIES = _config.OPTIMUS_LEDGER_DIR / "research_gym"

# ── frozen in the prereg; not tunable mid-trial ────────────────────────────
UNIVERSE = ["SPY", "QQQ", "IWM", "XLF", "XLE", "XLK"]
HORIZONS = (20, 60)
PRIMARY_HORIZON = 20
TAIL_Q = 0.10
SEED = 20260816
N_BOOT = 2000
COST = 0.0010
COST_GRID = (0.0, 0.0010, 0.0025)
BLOCK_MULTIPLIERS = (0.5, 1.0, 2.0)
#: N9's confirmed transfer lift (2ba9fb3). Frozen; NOT re-estimated here.
COMPARISON_LIFT = 1.271

_ORDER = {"BREAK_EVEN_CLEARED_IN_SCOPE": 0, "NOT_RESOLVED": 1,
          "REFUTED_IN_SCOPE": 2}


def _latest_autopsies() -> Path | None:
    files = sorted(AUTOPSIES.glob("autopsies_*.jsonl"))
    return files[-1] if files else None


def _weakest(verdicts: list[str]) -> str:
    """Weakest cell in the grid, inherited from N4B.

    Reporting the headline cell would be choosing the flattering assumption
    after seeing the answer.
    """
    if not verdicts:
        return "NOT_DETECTABLE_IN_SCOPE"
    return max(verdicts, key=lambda v: _ORDER.get(v, -1))


def l_min(mu_tail: float, mu_rest: float, cost: float) -> float:
    """N4B's formula, byte-for-byte. Only the mu_rest ESTIMAND changes."""
    mr = max(mu_rest, 0.0)
    denom = TAIL_Q * (abs(mu_tail) + mr)
    return (mr + cost) / denom if denom > 0 else float("inf")


def mu_rest_for_l_min(mu_tail: float, target_l: float, cost: float) -> float:
    """Invert L_min: what forgone return makes the break-even equal `target_l`?

        L = (m + c) / (q(|t| + m))   =>   m = (L q |t| - c) / (1 - L q)

    This is the number the trial has to move `mu_rest` to, and it is derived
    from the frozen formula BEFORE any conditional statistic is computed.
    """
    lq = target_l * TAIL_Q
    denom = 1.0 - lq
    if denom <= 0:
        return float("nan")
    return (lq * abs(mu_tail) - cost) / denom


def _build(a) -> tuple:
    """Rebuild N4B's arrays exactly: same universe, precursors, calendar."""
    import numpy as np
    import pandas as pd
    import yfinance as yf

    path = Path(a.autopsies) if a.autopsies else _latest_autopsies()
    if path is None:
        raise SystemExit("no autopsy file")
    rows = [json.loads(ln) for ln in
            path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    precursors = []
    for r in rows:
        au = r.get("autopsy") or {}
        spec = au.get("affected_precursor") or au.get("executable_precursor")
        if not spec:
            continue
        try:
            precursors.append(AU.compile_precursor(spec))
        except Exception as exc:                                 # noqa: BLE001
            print(f"  skipped a precursor that will not compile: {exc}")
    print(f"library: {len(rows)} mechanisms, {len(precursors)} compiled "
          f"from {path.name}")
    if not precursors:
        raise SystemExit("no precursors compiled")

    vix = yf.download("^VIX", start=a.start, end=a.end, progress=False)["Close"]
    if isinstance(vix, pd.DataFrame):
        vix = vix.squeeze()

    per: dict[str, pd.DataFrame] = {}
    for tkr in UNIVERSE:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        r = px.pct_change().dropna()
        v = vix.reindex(r.index).ffill().shift(1)
        roll_max = px.rolling(252, min_periods=20).max()
        rv20 = r.rolling(20).std() * np.sqrt(252) * 100.0
        rv60 = r.rolling(60).std() * np.sqrt(252) * 100.0
        state = pd.DataFrame({
            "vix": v,
            "drawdown_pct": ((px / roll_max - 1.0) * 100.0).shift(1),
            "ret_1m_pct": (px.pct_change(21) * 100.0).shift(1),
            "ret_3m_pct": (px.pct_change(63) * 100.0).shift(1),
            "ret_6m_pct": (px.pct_change(126) * 100.0).shift(1),
            "realised_vol_20d": rv20.shift(1),
            "vol_ratio_20_60": (rv20 / rv60).shift(1),
        }).reindex(r.index)
        state["security"] = tkr

        fired = np.zeros(len(state), dtype=bool)
        recs = state.to_dict("records")
        for fn in precursors:
            for i, rec in enumerate(recs):
                if fired[i]:
                    continue
                try:
                    if fn(rec):
                        fired[i] = True
                except Exception:                                # noqa: BLE001
                    pass
        df = pd.DataFrame({"fired": fired,
                           "has_vix": state["vix"].notna().to_numpy()},
                          index=r.index)
        for H in HORIZONS:
            df[f"fwd_{H}"] = ((px.shift(-H) / px - 1.0) * 100.0).reindex(r.index)
        per[tkr] = df
        print(f"  {tkr}: {len(df)} days, precursor fires on "
              f"{100.0 * fired.mean():.1f}%")

    common = None
    for df in per.values():
        idx = df.index[df["has_vix"].to_numpy()]
        common = idx if common is None else common.intersection(idx)
    print(f"\nshared calendar: {len(common)} days "
          f"{common[0].date()} -> {common[-1].date()}")

    arrays: dict[tuple[str, int], tuple] = {}
    for tkr in UNIVERSE:
        d = per[tkr].loc[common]
        fire = d["fired"].to_numpy()
        for H in HORIZONS:
            f = d[f"fwd_{H}"].to_numpy()
            ok = ~np.isnan(f)
            arrays[(tkr, H)] = (f[ok], fire[ok])
    return arrays, common, len(precursors), path.name


def _power_inputs(arrays, common) -> dict:
    """Fire rate and outcome dispersion ONLY.

    Deliberately does not touch the conditional mean. These are design inputs;
    computing them before declaring power is correct, and computing the
    estimand before declaring power is not.
    """
    import numpy as np

    out = {}
    for H in HORIZONS:
        fires, sds, ns = [], [], []
        for tkr in UNIVERSE:
            f, fire = arrays[(tkr, H)]
            fires.append(float(fire.mean()))
            sds.append(float(np.std(f, ddof=1)))
            ns.append(int(len(f)))
        out[H] = {
            "fire_rate": float(np.mean(fires)),
            "fire_events_per_year": float(np.mean(fires) * 252.0),
            "outcome_dispersion_pct": float(np.mean(sds)),
            "n_obs_per_security": int(np.mean(ns)),
        }
    return out


def _conditional_mu_rest(arrays, H: int, tail: str, pos=None):
    """Pooled (lift, mu_tail, mu_rest_uncond, mu_rest_cond, n_fire_nontail).

    `mu_rest_cond` is the mean non-tail forward return ON FIRING DAYS — the
    population the action actually removes exposure from.
    """
    import numpy as np

    lifts, mts, mr_u, mr_c, nfc = [], [], [], [], []
    for tkr in UNIVERSE:
        f, fire = arrays[(tkr, H)]
        if pos is not None:
            p = pos[pos < len(f)]
            f, fire = f[p], fire[p]
        if len(f) < 200:
            return None
        cut = (np.quantile(f, TAIL_Q) if tail == "bottom"
               else np.quantile(f, 1.0 - TAIL_Q))
        mask = f <= cut if tail == "bottom" else f >= cut
        base = float(fire.mean())
        if base <= 0 or not mask.any() or mask.all():
            return None
        rest = ~mask
        rest_fire = rest & fire
        if not rest_fire.any():
            return None
        lifts.append(float(fire[mask].mean()) / base)
        mts.append(float(f[mask].mean()) / 100.0)
        mr_u.append(float(f[rest].mean()) / 100.0)
        mr_c.append(float(f[rest_fire].mean()) / 100.0)
        nfc.append(int(rest_fire.sum()))
    k = len(lifts)
    return (sum(lifts) / k, sum(mts) / k, sum(mr_u) / k, sum(mr_c) / k,
            int(sum(nfc)))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--autopsies", default=None)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--power-only", action="store_true",
                    help="design stage: fire rate + dispersion, no estimand")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import numpy as np

    arrays, common, n_prec, autopsy_name = _build(a)

    # ── declared effect size, from the FROZEN formula, before any estimand ──
    n4b = json.loads(
        (_config.OPTIMUS_LEDGER_DIR / "research_gym"
         / "n4b_coverage_equivalence.json").read_text(encoding="utf-8"))
    n4b_rows = {(r["horizon"], r["tail"]): r for r in n4b["rows"]}

    pw = _power_inputs(arrays, common)
    print("\n=== POWER INPUTS (design stage) ===")
    declared = {}
    for H in HORIZONS:
        row = n4b_rows[(H, "bottom")]
        mu_t = row["mu_tail_pct"] / 100.0
        mu_r_unc = row["mu_rest_pct"] / 100.0
        needed = mu_rest_for_l_min(mu_t, COMPARISON_LIFT, COST)
        eff = (mu_r_unc - needed) * 100.0
        declared[H] = {
            **pw[H],
            "mu_tail_pct": row["mu_tail_pct"],
            "mu_rest_uncond_pct": row["mu_rest_pct"],
            "L_min_n4b": row["L_min_declared_cost"],
            "mu_rest_needed_pct": needed * 100.0,
            "declared_effect_size_pp": eff,
        }
        print(f"  H={H}d  fire {pw[H]['fire_rate']*100:.1f}% "
              f"({pw[H]['fire_events_per_year']:.0f}/yr)  "
              f"sd {pw[H]['outcome_dispersion_pct']:.2f}pp  "
              f"| need mu_rest < {needed*100:.3f}% "
              f"(from {row['mu_rest_pct']:.3f}%) "
              f"=> declared effect {eff:.3f}pp")

    if a.power_only:
        print("\n--power-only: the conditional estimand was NOT computed.")
        print("Paste these into the prereg, commit, then run without the flag.")
        return 0

    # ── run stage ──────────────────────────────────────────────────────────
    rng = np.random.default_rng(SEED)
    n = len(common)
    out_rows = []

    for H in HORIZONS:
        for tail in ("bottom", "top"):
            point = _conditional_mu_rest(arrays, H, tail, None)
            if point is None:
                continue
            lift, mu_t, mu_r_unc, mu_r_cond, n_fire_rest = point
            applicable = tail == "bottom"

            cells = []
            for bm in BLOCK_MULTIPLIERS:
                block = max(2, int(round(H * bm)))
                nb = int(np.ceil(n / block))
                boots_cond, boots_unc = [], []
                for _ in range(a.n_boot):
                    starts = rng.integers(0, max(1, n - block), size=nb)
                    pos = np.concatenate(
                        [np.arange(s, s + block) for s in starts])[:n]
                    p = _conditional_mu_rest(arrays, H, tail, pos)
                    if p is None:
                        continue
                    boots_cond.append(p[3])
                    boots_unc.append(p[2])
                if len(boots_cond) < 100:
                    continue
                bc = np.asarray(boots_cond)
                bu = np.asarray(boots_unc)
                diff = bc - bu

                for cost in COST_GRID:
                    lm_cond = l_min(mu_t, mu_r_cond, cost)
                    lm_unc = l_min(mu_t, mu_r_unc, cost)
                    lm_boot = np.asarray(
                        [l_min(mu_t, float(x), cost) for x in bc])
                    lo, hi = (float(np.quantile(lm_boot, 0.05)),
                              float(np.quantile(lm_boot, 0.95)))

                    # R13 power gate, evaluated BEFORE the verdict is read
                    needed = mu_rest_for_l_min(mu_t, COMPARISON_LIFT, cost)
                    required_diff = needed - mu_r_unc          # negative
                    d_lo, d_hi = (float(np.quantile(diff, 0.05)),
                                  float(np.quantile(diff, 0.95)))
                    detectable = (d_hi - d_lo) <= abs(required_diff)

                    if not applicable:
                        verdict = "DESCRIPTIVE_ONLY"
                    elif not detectable:
                        verdict = "NOT_DETECTABLE_IN_SCOPE"
                    elif hi < COMPARISON_LIFT:
                        verdict = "BREAK_EVEN_CLEARED_IN_SCOPE"
                    elif lo > COMPARISON_LIFT:
                        verdict = "REFUTED_IN_SCOPE"
                    else:
                        verdict = "NOT_RESOLVED"

                    cells.append({
                        "block": block, "cost": cost,
                        "L_min_conditional": lm_cond,
                        "L_min_unconditional": lm_unc,
                        "ci_lo": lo, "ci_hi": hi,
                        "diff_ci_lo_pp": d_lo * 100.0,
                        "diff_ci_hi_pp": d_hi * 100.0,
                        "required_diff_pp": required_diff * 100.0,
                        "detectable": bool(detectable),
                        "verdict": verdict,
                    })

            verdicts = [c["verdict"] for c in cells
                        if c["verdict"] != "DESCRIPTIVE_ONLY"]
            robust = _weakest(verdicts) if applicable else "DESCRIPTIVE_ONLY"
            out_rows.append({
                "horizon": H, "tail": tail,
                "margin_applicable": applicable,
                "lift": lift,
                "mu_tail_pct": mu_t * 100.0,
                "mu_rest_uncond_pct": mu_r_unc * 100.0,
                "mu_rest_conditional_pct": mu_r_cond * 100.0,
                "delta_mu_rest_pp": (mu_r_cond - mu_r_unc) * 100.0,
                "n_nontail_firing_days": n_fire_rest,
                "L_min_uncond_declared_cost": l_min(mu_t, mu_r_unc, COST),
                "L_min_cond_declared_cost": l_min(mu_t, mu_r_cond, COST),
                "comparison_lift": COMPARISON_LIFT,
                "cells": cells,
                "robust_verdict": robust,
            })

    payload = {
        "trial": "N20",
        "prereg": "docs/TRIALS/PREREG_N20_CONDITIONAL_MU_REST.md",
        "slice": {
            "universe": UNIVERSE,
            "purpose": "re-analysis of a consumed exploration slice",
            "not_confirmation": True,
        },
        "autopsy_file": autopsy_name,
        "n_precursors": n_prec,
        "n_days": n,
        "seed": SEED,
        "n_boot": a.n_boot,
        "comparison_lift": COMPARISON_LIFT,
        "power_declaration": declared,
        "rows": out_rows,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== N20 RESULT ===")
    for r in out_rows:
        tag = "" if r["margin_applicable"] else "  (descriptive only)"
        print(f"\nH={r['horizon']}d {r['tail']}{tag}")
        print(f"  mu_rest  unconditional {r['mu_rest_uncond_pct']:+.3f}%"
              f"   | fire {r['mu_rest_conditional_pct']:+.3f}%"
              f"   delta {r['delta_mu_rest_pp']:+.3f}pp"
              f"  (n={r['n_nontail_firing_days']})")
        print(f"  L_min    unconditional {r['L_min_uncond_declared_cost']:.4f}"
              f"   | conditional {r['L_min_cond_declared_cost']:.4f}"
              f"   vs N9 lift {COMPARISON_LIFT}")
        print(f"  VERDICT (weakest cell): {r['robust_verdict']}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
