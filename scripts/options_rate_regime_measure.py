"""OPTIONS-RATE-REGIME-1 — is the RESEARCH side's residual rate-driven too?

DECLARED BEFORE THE NUMBERS EXIST. Written and committed before the panel was
read.

WHY THIS IS THE DECIDING TEST
=============================
`OPTIONS-CONVENTION-1` settled the mechanism: yfinance's `impliedVolatility`
column discounts nothing (our own solver at r = 0, q = 0 reproduces it to
0.0009), and that was the whole 0.026 train/serve gap on
`iv_put_minus_call_30d`. Inverting the prices ourselves under a declared r and
q cuts the gap to 0.0053 — outside the declared 0.005 bar by 0.0003.

It also left the comparison itself in doubt, and that doubt is now the binding
one. The transfer test compares:

    a ONE-DAY live cross-sectional median   against   a median over
                                                      OptionMetrics' WHOLE PANEL

on a quantity measured to move **+0.0070 per percentage point of (r − q)** and a
panel spanning 1996-2024, i.e. short rates from zero to six percent. Those two
medians have no reason to coincide even when the feature is identical, and no
amount of care on the live side can fix a comparison that is mis-specified on
the other.

Both halves are testable directly, and the panel is already on disk.

THE TWO QUESTIONS
=================
1. **Is the panel's own residual a function of the prevailing short rate, at the
   slope measured live?** Per-month median of `iv30P - iv30C` regressed on
   FEDFUNDS. If the slope lands near +0.0070/pp, the same mechanism is visible
   on both sides and the level difference is a regime difference.
2. **Restricted to today's regime, does the live residual match?** The panel
   median over months with FEDFUNDS within 0.5pp of today's 3.63%, compared to
   R1's live median under the SAME bars the transfer test already declared.

Note what question 1 buys that question 2 cannot: a slope is a statement about
the panel ALONE, so it cannot be manufactured by anything on the live side. If
the slope is flat, question 2's answer is a coincidence however it comes out.

THE PANEL IS ATM. Checked before declaring: the events extract carries median
delta +0.523 for calls and -0.484 for puts with sd 0.015, so `iv30P - iv30C` is
an at-the-money parity residual and not a skew measure. Had it averaged the
25-delta buckets in, it would have been a DIFFERENT QUANTITY from the live
matched-strike residual and no convention work could ever have reconciled them.

THE DECISION RULE, DECLARED
===========================
  CONFIRMED_RATE_DRIVEN   panel regression slope in [0.004, 0.010] per pp
                          -- the same ORDER as the live 0.0070, not the same
                          number, because the panel's universe, its solver and
                          its dividend treatment all differ -- with |t| > 3.

  TRANSFERS_IN_REGIME     |median(R1_live) - median(panel, restricted)| <= 0.005
                          AND |pct_positive difference| <= 0.10.
                          Same bars as the original transfer test, not new ones.

BOTH hold      -> the feature transfers; the residue was a regime comparison and
                  `EVENT_RESPONSE_v1` may serve the full model on this column.
SLOPE ONLY     -> rate-driven on both sides but the levels still disagree in
                  regime: the remainder is a real live-universe effect (borrow
                  is the standing hypothesis) and must be measured, not fitted.
NEITHER        -> the panel's residual is NOT rate-driven, so OptionMetrics'
                  own discounting already absorbs it, and the live residue is
                  ours to explain -- most likely `q`. Ship the drop-feature arm.

NOT A CLAIM. No forward return is touched, no IC is computed. Servability.

USAGE
    python -m scripts.options_rate_regime_measure
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "backend/data/optimus/wrds/stdopd_events"
OUT = ROOT / "backend/data/optimus/options_pit"
RECEIPT = OUT / "rate_regime_receipt.json"
CONVENTION = OUT / "convention_receipt.json"

TODAY_RATE_PCT = 3.63
REGIME_HALF_WIDTH_PCT = 0.50
SLOPE_BAND = (0.004, 0.010)
SLOPE_T_BAR = 3.0
MEDIAN_BAR = 0.005
PCT_POS_BAR = 0.10
#: Months with fewer than this many names are dropped from the monthly series:
#: a median over a handful of names is not a cross-section, and an early-panel
#: thin month would otherwise carry the same weight as a full one.
MIN_NAMES_PER_MONTH = 50


def load_panel() -> pd.DataFrame:
    files = sorted(PANEL.glob("stdopd_events_*.parquet"))
    if not files:
        raise SystemExit(f"REFUSED: no stdopd events extract at {PANEL}")
    d = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    d = d[d["days"] == 30]
    piv = (d.pivot_table(index=["secid", "date"], columns="cp_flag",
                         values="impl_volatility", aggfunc="mean")
           .reset_index())
    if "P" not in piv or "C" not in piv:
        raise SystemExit("REFUSED: the extract lacks one side")
    piv["resid"] = piv["P"] - piv["C"]
    piv["date"] = pd.to_datetime(piv["date"])
    piv["month"] = piv["date"].values.astype("datetime64[M]")
    return piv.dropna(subset=["resid"])


def fed_funds_monthly() -> pd.DataFrame:
    from backend.services.data_fetcher import DataFetcher
    v = (DataFetcher().fetch_fred_data() or {}).get("fed_funds")
    if v is None or not hasattr(v, "index"):
        raise SystemExit("REFUSED: FEDFUNDS unavailable — this measurement is "
                         "ABOUT the rate, so a fallback constant would make it "
                         "meaningless rather than approximate")
    s = pd.Series(v)
    return pd.DataFrame({
        "month": pd.to_datetime(s.index).values.astype("datetime64[M]"),
        "ff": s.values.astype(float)}).dropna().drop_duplicates("month")


def live_reference() -> dict:
    d = json.loads(CONVENTION.read_text(encoding="utf-8"))
    a = d["arms"]["R1_own_r_q"]
    return {"median": a["median"], "pct_positive": a["pct_positive"],
            "n": a["n"], "r_simple": d["conventions"]["r_simple"]}


def main() -> None:
    panel = load_panel()
    ff = fed_funds_monthly()

    monthly = (panel.groupby("month")
               .agg(median_resid=("resid", "median"),
                    pct_positive=("resid", lambda x: float((x > 0).mean())),
                    n_names=("secid", "nunique"))
               .reset_index())
    monthly = monthly[monthly["n_names"] >= MIN_NAMES_PER_MONTH]
    m = monthly.merge(ff, on="month", how="inner")
    if len(m) < 24:
        raise SystemExit(f"REFUSED: only {len(m)} usable months")

    # ── question 1: is the PANEL's residual rate-driven?
    x = m["ff"].to_numpy(float)
    y = m["median_resid"].to_numpy(float)
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    dof = len(x) - 2
    se = float(np.sqrt((resid ** 2).sum() / dof
                       / ((x - x.mean()) ** 2).sum()))
    tstat = float(slope / se) if se else float("nan")
    r2 = float(1.0 - (resid ** 2).sum() / ((y - y.mean()) ** 2).sum())
    slope_ok = bool(SLOPE_BAND[0] <= slope <= SLOPE_BAND[1]
                    and abs(tstat) > SLOPE_T_BAR)

    # ── question 2: the panel restricted to TODAY'S regime
    lo, hi = TODAY_RATE_PCT - REGIME_HALF_WIDTH_PCT, \
        TODAY_RATE_PCT + REGIME_HALF_WIDTH_PCT
    in_regime = m[(m["ff"] >= lo) & (m["ff"] <= hi)]
    regime_months = sorted(str(d)[:7] for d in in_regime["month"])
    sub = panel[panel["month"].isin(set(in_regime["month"]))]
    reg_median = float(sub["resid"].median()) if len(sub) else float("nan")
    reg_pos = float((sub["resid"] > 0).mean()) if len(sub) else float("nan")

    live = live_reference()
    d_med = live["median"] - reg_median
    d_pos = live["pct_positive"] - reg_pos
    transfers = bool(abs(d_med) <= MEDIAN_BAR and abs(d_pos) <= PCT_POS_BAR)

    verdict = ("BOTH" if (slope_ok and transfers)
               else "SLOPE_ONLY" if slope_ok
               else "TRANSFER_ONLY" if transfers
               else "NEITHER")

    print(f"panel months usable        {len(m)}")
    print(f"panel FULL median          {panel['resid'].median():+.5f}  "
          f"({float((panel['resid'] > 0).mean()):.1%} positive)")
    print(f"slope per pp of FEDFUNDS   {slope:+.5f}  t {tstat:+.2f}  "
          f"R2 {r2:.3f}   {'in band' if slope_ok else 'OUT of band'}")
    print(f"regime months [{lo:.2f},{hi:.2f}]  {len(in_regime)} "
          f"({regime_months[0] if regime_months else '-'} .. "
          f"{regime_months[-1] if regime_months else '-'})")
    print(f"panel median IN REGIME     {reg_median:+.5f}  ({reg_pos:.1%})")
    print(f"live R1 median             {live['median']:+.5f}  "
          f"({live['pct_positive']:.1%})  n {live['n']}")
    print(f"difference                 {d_med:+.5f}  pos {d_pos:+.3f}   "
          f"{'TRANSFERS' if transfers else 'no'}")
    print(f"VERDICT                    {verdict}")

    OUT.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps({
        "measurement_id": "OPTIONS-RATE-REGIME-1",
        "licence": "PRODUCT_EXPERIMENT (servability — no IC, no forward "
                   "return, not evidence of alpha)",
        "declared_in": "scripts/options_rate_regime_measure.py (this file)",
        "question_1": "is the PANEL's own put-call residual a function of the "
                      "prevailing short rate, at the slope measured live?",
        "question_2": "restricted to today's rate regime, does the live "
                      "residual match the panel's?",
        "panel": {
            "months_usable": int(len(m)),
            "min_names_per_month": MIN_NAMES_PER_MONTH,
            "full_median": round(float(panel["resid"].median()), 5),
            "full_pct_positive": round(float((panel["resid"] > 0).mean()), 4),
            "atm_check": "events extract is delta ~ +/-0.5 (sd 0.015), so this "
                         "is an ATM parity residual, not a skew measure",
        },
        "regression": {
            "slope_per_pct_point": round(float(slope), 5),
            "t": round(tstat, 2), "r2": round(r2, 4),
            "band": list(SLOPE_BAND), "t_bar": SLOPE_T_BAR,
            "in_band": slope_ok,
            "live_slope_for_comparison": 0.0070,
        },
        "regime": {
            "today_rate_pct": TODAY_RATE_PCT,
            "half_width_pct": REGIME_HALF_WIDTH_PCT,
            "n_months": int(len(in_regime)),
            "months": regime_months,
            "panel_median": round(reg_median, 5),
            "panel_pct_positive": round(reg_pos, 4),
        },
        "live_R1": live,
        "comparison": {
            "median_difference": round(float(d_med), 5),
            "pct_positive_difference": round(float(d_pos), 4),
            "bars": {"median": MEDIAN_BAR, "pct_positive": PCT_POS_BAR},
            "transfers_in_regime": transfers,
        },
        "verdict": verdict,
    }, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT}")


if __name__ == "__main__":
    main()
