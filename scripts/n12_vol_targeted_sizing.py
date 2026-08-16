"""N12 — volatility-targeted sizing. PRODUCT_EXPERIMENT, not an alpha claim.

    python -m scripts.n12_vol_targeted_sizing

Registered at `docs/TRIALS/PREREG_N12_VOL_TARGETED_SIZING.md` before any wealth
path existed.

WHY THIS IS BEING BUILT
=======================
Four convergent findings, none of them designed to be about sizing: NIGHT-12's
drawdown at beta 2.15; NIGHT-13's constant half-exposure beating the timing
ladder; the de-risking result's failure being the state -> EXPOSURE map; and N6
finding that the moment which governs sizing is the predictable one. Four
independent arrivals at the same place, and the thing they point at has never
been built.

Order 3 settles the objection that stopped it last time: vol-targeted sizing
does not need to beat `rv20`. It needs volatility to be forecastable at all, by
anything, `rv20` included. A free baseline that matches the model is GOOD news
for a product — cheap input, no model risk. It is bad news only for a paper.

THE COMPARISON THAT WOULD BE DISHONEST
======================================
Vol targeting lowers average exposure, so in a rising market it loses to
buy-and-hold by being less invested and wins on drawdown for the same trivial
reason. Quoting either number alone chooses the answer.

The primary comparison is therefore at MATCHED EX-POST REALISED VOLATILITY:
every policy scaled by one constant to the same realised vol, then compared on
terminal log-wealth at that common risk level. The unmatched table is printed
alongside, never instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend import config as _config
from backend.services.research_gym import ex_post as XP
from backend.services.research_gym import power as PW
from backend.services.research_gym import utility as U

OUT = _config.OPTIMUS_LEDGER_DIR / "research_gym" / "n12_vol_targeted_sizing.json"

UNIVERSE = ("SPY", "QQQ", "IWM", "EFA")
TARGET_VOL_PCT = 15.0
COST_BPS_ONE_WAY = 10.0
SEED = 20260816
N_BOOT = 2000
BLOCK = 63


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", default="1999-01-01")
    ap.add_argument("--end", default="2026-08-15")
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args(argv)

    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                                        # noqa: BLE001
            pass

    import numpy as np
    import pandas as pd
    import yfinance as yf

    rows: list[dict] = []
    rng = np.random.default_rng(SEED)

    def _exposures(rv20: "np.ndarray", cap: float) -> "np.ndarray":
        """target / trailing vol, capped. NaN before the window fills -> 0."""
        with np.errstate(divide="ignore", invalid="ignore"):
            e = TARGET_VOL_PCT / rv20
        e = np.where(np.isfinite(e), e, 0.0)
        return np.clip(e, 0.0, cap)

    def _wealth(r: "np.ndarray", expo: "np.ndarray") -> "np.ndarray":
        """Net wealth path. Turnover is charged on the CHANGE in exposure."""
        turn = np.abs(np.diff(expo, prepend=expo[0] if len(expo) else 0.0))
        net = expo * r - turn * (COST_BPS_ONE_WAY / 10_000.0)
        return np.cumprod(1.0 + net)

    for tkr in UNIVERSE:
        px = yf.download(tkr, start=a.start, end=a.end, progress=False)["Close"]
        if isinstance(px, pd.DataFrame):
            px = px.squeeze()
        px = px.dropna()
        r = px.pct_change().dropna()
        # Sized on the PREVIOUS close's trailing vol: no policy ever sees the
        # day it is sizing for.
        rv20 = (r.rolling(20).std() * np.sqrt(252) * 100.0).shift(1)
        ok = rv20.notna()
        r_arr = r[ok].to_numpy(dtype=float)
        rv_arr = rv20[ok].to_numpy(dtype=float)
        n = len(r_arr)
        if n < 1000:
            print(f"  {tkr}: too little history — skipped")
            continue

        policies = {
            "buy_hold": np.ones(n),
            "constant_half": np.full(n, 0.5),
            "vol_target_1x": _exposures(rv_arr, 1.0),
            "vol_target_2x": _exposures(rv_arr, 2.0),
        }

        def _stats(expo, idx=None):
            rr = r_arr if idx is None else r_arr[idx]
            ee = expo if idx is None else expo[idx]
            return U.path_stats(_wealth(rr, ee).tolist())

        base = {k: _stats(v) for k, v in policies.items()}
        # ── vol matching: one constant per policy, so every row is compared
        # at the SAME realised risk. Without it the whole table is a statement
        # about average exposure and nothing else.
        #
        # `pv` is the policy's realised vol over the WHOLE sample, so this
        # scale is hindsight and can never be an exposure anyone could have
        # taken. It is therefore built as an `ExPostScale`, which is not a
        # number: `v * scale` raises rather than silently producing a
        # deployable-looking series. Getting the value out requires naming the
        # act — `.for_comparison_only()` — and that name is greppable.
        ref_vol = base["buy_hold"].realised_vol_pct
        matched = {}
        for k, v in policies.items():
            pv = base[k].realised_vol_pct
            scale = XP.matched_vol_scale(
                ref_vol, pv,
                basis=(f"{k} realised vol measured over the full "
                       f"{n}-day sample being evaluated"))
            matched[k] = (_stats(v * scale.for_comparison_only()), scale)

        print(f"\n{'=' * 78}\n{tkr}  {n} days  "
              f"(reference realised vol {ref_vol:.1f}%)")
        print(f"{'policy':<16s} {'mean expo':>9s} {'CAGR%':>7s} {'vol%':>6s} "
              f"{'maxDD%':>7s} {'TUW':>6s} {'ES5%':>7s} {'ruin':>5s}   "
              f"{'MATCHED CAGR%':>13s} {'scale':>6s} {'maxDD%':>7s}")
        for k in policies:
            s, (m, sc) = base[k], matched[k]
            yrs = n / 252.0
            cagr = (s.terminal_wealth ** (1.0 / yrs) - 1.0) * 100.0
            mcagr = (m.terminal_wealth ** (1.0 / yrs) - 1.0) * 100.0
            print(f"{k:<16s} {policies[k].mean():>9.2f} {cagr:>7.2f} "
                  f"{s.realised_vol_pct:>6.1f} {s.max_drawdown_pct:>7.1f} "
                  f"{s.time_under_water_frac:>6.2f} "
                  f"{(s.expected_shortfall_5_pct or float('nan')):>7.2f} "
                  f"{str(s.ruin):>5s}   {mcagr:>13.2f} "
                  f"{sc.for_comparison_only():>6.2f} "
                  f"{m.max_drawdown_pct:>7.1f}")
            rows.append({"security": tkr, "policy": k, "n_days": n,
                         "mean_exposure": float(policies[k].mean()),
                         "cagr_pct": cagr, "matched_cagr_pct": mcagr,
                         # named so that nothing downstream can read this as a
                         # deployable exposure multiplier
                         "vol_match_scale_EX_POST": sc.for_comparison_only(),
                         "vol_match_scale_basis": sc.basis,
                         "raw": s.as_dict(), "matched": m.as_dict()})

        # ── §18: the DIFFERENCE, paired, with its own SE ────────────────────
        # Same blocks for every policy, so the market's path cancels and only
        # the policy difference survives the resampling.
        print(f"  paired block bootstrap ({a.n_boot} x {BLOCK}d blocks), "
              f"matched-vol log-wealth difference vs buy_hold:")
        n_blocks = max(n // BLOCK, 1)
        diffs: dict[str, list[float]] = {k: [] for k in policies
                                         if k != "buy_hold"}
        dd_diffs: dict[str, list[float]] = {k: [] for k in policies
                                            if k != "buy_hold"}
        for _ in range(a.n_boot):
            starts = rng.integers(0, max(n - BLOCK, 1), size=n_blocks)
            idx = (starts[:, None] + np.arange(BLOCK)[None, :]).ravel()
            idx = idx[idx < n]
            bh = _stats(policies["buy_hold"] * matched["buy_hold"][1], idx)
            if bh is None or bh.terminal_wealth <= 0:
                continue
            for k in diffs:
                st = _stats(policies[k] * matched[k][1], idx)
                if st is None or st.terminal_wealth <= 0:
                    continue
                diffs[k].append(float(np.log(st.terminal_wealth)
                                      - np.log(bh.terminal_wealth)))
                # CAVEAT, and it is not a small one: block resampling destroys
                # the PATH, and max drawdown is a path statistic. A 63-day
                # block series has a different drawdown structure from the real
                # 27-year one, so this quantity is reported for its dispersion
                # (the MDE) and NOT as an estimate of the drawdown difference.
                # The full-sample matched column above is the estimate.
                dd_diffs[k].append(float(st.max_drawdown_pct
                                         - bh.max_drawdown_pct))
        for k in diffs:
            xs, ds = diffs[k], dd_diffs[k]
            if len(xs) < 50:
                continue
            mean, sd = float(np.mean(xs)), float(np.std(xs, ddof=1))
            mde = PW.mde_from_se(sd)
            det = mde is not None and abs(mean) >= mde
            dmean, dsd = float(np.mean(ds)), float(np.std(ds, ddof=1))
            dmde = PW.mde_from_se(dsd)
            ddet = dmde is not None and abs(dmean) >= dmde
            print(f"    {k:<16s} dlog {mean:+7.4f} (MDE "
                  f"{('-' if mde is None else f'{mde:6.4f}')}) "
                  f"{'DETECTABLE' if det else 'not detectable':<14s}"
                  f"  dMaxDD {dmean:+6.2f}pp (MDE "
                  f"{('-' if dmde is None else f'{dmde:5.2f}')}) "
                  f"{'DETECTABLE' if ddet else 'not detectable'}")
            rows.append({"security": tkr, "policy": k,
                         "comparison": "matched_vol_vs_buy_hold",
                         "delta_log": mean, "sd": sd, "mde": mde,
                         "detectable": bool(det),
                         "delta_maxdd_pp": dmean, "maxdd_sd": dsd,
                         "maxdd_mde": dmde, "maxdd_detectable": bool(ddet),
                         "n_boot": len(xs)})

        # ── break-even risk aversion: the preference-unit answer ────────────
        # A product decision is made under a declared utility, so the useful
        # number is not "is the mean difference detectable" but "at what risk
        # aversion does the choice flip".
        yrs_blocks = []
        for _ in range(400):
            starts = rng.integers(0, max(n - BLOCK, 1), size=n_blocks)
            idx = (starts[:, None] + np.arange(BLOCK)[None, :]).ravel()
            idx = idx[idx < n]
            yrs_blocks.append(idx)
        for k in ("vol_target_1x", "constant_half"):
            aw = [ _stats(policies[k], i).terminal_wealth for i in yrs_blocks ]
            bw = [ _stats(policies["buy_hold"], i).terminal_wealth
                   for i in yrs_blocks ]
            g = U.break_even_gamma(aw, bw)
            print(f"    gamma* ({k} vs buy_hold, UNMATCHED): "
                  + ("preferred at every gamma searched" if g is None
                     else f"{g:.2f}"))
            rows.append({"security": tkr, "policy": k,
                         "comparison": "break_even_gamma_vs_buy_hold",
                         "gamma_star": g})

    # ── the pooled reading, because four per-security tests are four looks ──
    # Each security's difference is underpowered on its own. The informative
    # statistic across four is the SIGN CONSISTENCY, and it is reported as what
    # it is: four correlated markets, not four independent draws.
    print(f"\n{'=' * 78}\nPOOLED — sign consistency across {len(UNIVERSE)} "
          f"securities (correlated, so this is a pattern, not a p-value)")
    for k in ("vol_target_1x", "vol_target_2x", "constant_half"):
        cmp_rows = [r for r in rows
                    if r.get("comparison") == "matched_vol_vs_buy_hold"
                    and r["policy"] == k]
        if not cmp_rows:
            continue
        n_g = sum(1 for r in cmp_rows if r["delta_log"] > 0)
        # Full-sample matched drawdown, not the block-resampled one — see the
        # caveat above. One path per security, but the right path.
        fs = [r for r in rows if r.get("policy") == k and "matched" in r
              and r.get("comparison") is None]
        bh = {r["security"]: r["matched"]["max_drawdown_pct"] for r in rows
              if r.get("policy") == "buy_hold" and "matched" in r
              and r.get("comparison") is None}
        dds = [r["matched"]["max_drawdown_pct"] - bh[r["security"]]
               for r in fs if r["security"] in bh]
        n_dd = sum(1 for d in dds if d < 0)
        mdd = (sum(dds) / len(dds)) if dds else float("nan")
        print(f"  {k:<16s} log-wealth better in {n_g}/{len(cmp_rows)}   "
              f"max drawdown better in {n_dd}/{len(dds)}   "
              f"mean dMaxDD {mdd:+.2f}pp  (full-sample matched paths)")

    p = Path(a.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"universe": list(UNIVERSE),
                             "target_vol_pct": TARGET_VOL_PCT,
                             "cost_bps_one_way": COST_BPS_ONE_WAY,
                             "seed": SEED, "rows": rows}, indent=2),
                 encoding="utf-8")
    print(f"\nwritten  {p}")
    print("PRODUCT_EXPERIMENT. Read the MATCHED column: the unmatched one is "
          "mostly a statement about average exposure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
