"""OPTIONS-DIVIDEND-WINDOW-1 — the residue is a WRONG q, and here is the number.

DECLARED BEFORE THE NUMBERS EXIST, with a POINT PREDICTION, which is the part
that makes it a test rather than a search.

WHERE THIS CAME FROM
====================
`OPTIONS-CONVENTION-1` closed 80% of the put-call train/serve gap by inverting
prices ourselves instead of reading yfinance's implied-vol column (which
discounts nothing). It left 0.0053 and two stories for it.

`OPTIONS-RATE-REGIME-1` killed the story I preferred. I had written that the
transfer test was mis-specified — a one-day live median against a median over
OptionMetrics' whole panel, on a quantity that moves +0.0070 per point of rate
across a panel spanning zero to six percent. Measured over 168 months:

    panel residual regressed on FEDFUNDS:  slope +0.00001/pp, t 0.04, R2 0.000

**Flat.** The panel's residual does not move with the rate, because
OptionMetrics discounts correctly and the rate is already absorbed. Ours moves
at 0.0070/pp because our `r` and `q` are INPUTS we can get wrong. The asymmetry
is the whole finding, and it means the full-panel median +0.00194 is a
legitimate reference after all. The 0.0053 is ours.

THE HYPOTHESIS
==============
It is `q`, and specifically the tenor it is measured over.

We used **trailing 12-month dividends / spot**, a median of 0.83% across the 39
names. For a 30-day option the economically correct `q` is the dividend
expected **inside the option's life**, annualised — and a quarterly payer has
an ex-date in a given 30-day window only about a third of the time. For the
other two thirds the correct `q` for that window is **zero**, not the trailing
yield.

So the trailing yield systematically OVER-states the carry deduction, and the
residual is over-subtracted by 0.709 x (q_trailing - q_window).

THE POINT PREDICTION, made now
==============================
The measured sensitivity is 0.709 per unit of (r - q). Median q_trailing is
0.0083. If the median name has no ex-date in its window, q_window is 0 and the
median residual should move by

    +0.709 x 0.0083 = **+0.0059**

from R1's -0.00338 to about **+0.0025**, which is where R2 (the q = 0 arm)
already sits at +0.00250.

**That is the test.** R2 was reported in `OPTIONS-CONVENTION-1` as an arm that
"lands by cancellation" and must not be shipped on that basis. If this
hypothesis is right, R2 was not a coincidence — it was a cruder version of the
right answer, and R7 should land near it FROM A CORRECT MODEL rather than from
setting a real quantity to zero.

If R7 lands near R1 instead, the hypothesis is wrong and the residue is
something else (implied financing above OIS, or borrow) — and R2's pass stays a
coincidence that must not be shipped.

THE APPROXIMATION, named
========================
Future ex-dates are PROJECTED from the historical cadence: the median gap
between observed ex-dates, extrapolated forward from the last one. That is an
estimate, and a name that changes its schedule inside the window will be wrong.
It is not a look-ahead — the projection uses only past ex-dates — and it is the
same information a live collector has at decision time, which is the property
that matters.

DECISION RULE, unchanged from the transfer test and not re-derived here:
R7 transfers iff |median - 0.00194| <= 0.005 AND |pct_positive - 0.548| <= 0.10.

NOT A CLAIM. Servability only.

USAGE
    python -m scripts.options_dividend_window_measure
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend/data/optimus/options_pit"
QUOTES = OUT / "convention_quotes.json"
DIVCACHE = OUT / "dividend_schedule.json"
RECEIPT = OUT / "dividend_window_receipt.json"
CONVENTION = OUT / "convention_receipt.json"

TARGET_DAYS = 30
MEDIAN_BAR = 0.005
PCT_POS_BAR = 0.10
PREDICTED_MEDIAN = 0.0025          # the point prediction, recorded before running


def fetch_dividend_schedule(tickers: list[str]) -> dict:
    """Past ex-dates per name, plus the cadence they imply. Cached."""
    import pandas as pd
    import yfinance as yf

    out = {}
    for i, t in enumerate(tickers, 1):
        try:
            d = yf.Ticker(t).dividends
        except Exception as e:                               # noqa: BLE001
            out[t] = {"error": f"{type(e).__name__}: {e}"}
            continue
        if d is None or len(d) == 0:
            out[t] = {"ex_dates": [], "amounts": [], "cadence_days": None}
        else:
            d = d.tail(12)
            idx = pd.to_datetime(d.index).tz_localize(None)
            gaps = np.diff(idx.values).astype("timedelta64[D]").astype(float)
            out[t] = {
                "ex_dates": [str(x.date()) for x in idx],
                "amounts": [float(v) for v in d.values],
                "cadence_days": (float(np.median(gaps)) if len(gaps) else None),
            }
        if i % 10 == 0:
            print(f"  {i}/{len(tickers)}")
    DIVCACHE.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def q_for_window(sched: dict, spot: float, days: float, asof) -> tuple[float, int]:
    """Annualised continuous `q` from dividends PROJECTED into [asof, asof+days].

    Returns (q, n_dividends_in_window). Projection uses only past ex-dates.
    """
    import pandas as pd

    if not sched or sched.get("error") or not sched.get("ex_dates"):
        return 0.0, 0
    cadence = sched.get("cadence_days") or 0.0
    if cadence <= 0:
        return 0.0, 0
    last = pd.Timestamp(sched["ex_dates"][-1])
    amt = float(sched["amounts"][-1])
    horizon = pd.Timestamp(asof) + pd.Timedelta(days=days)

    total, n = 0.0, 0
    nxt = last + pd.Timedelta(days=cadence)
    # Roll forward past any projected dates that already lie behind us: a stale
    # cache must not credit a dividend that has already been paid.
    while nxt < pd.Timestamp(asof):
        nxt = nxt + pd.Timedelta(days=cadence)
    while nxt <= horizon:
        total += amt
        n += 1
        nxt = nxt + pd.Timedelta(days=cadence)

    if total <= 0 or spot <= 0:
        return 0.0, 0
    t = days / 365.0
    return (total / spot) / t, n


def main() -> None:
    import pandas as pd

    from backend.services.option_implier import implied_vol, to_continuous
    from scripts.options_convention_measure import (_interp_resid,
                                                    risk_free,
                                                    stdopd_reference)

    rows = json.loads(QUOTES.read_text(encoding="utf-8"))["rows"]
    tickers = [r["ticker"] for r in rows]
    sched = (json.loads(DIVCACHE.read_text(encoding="utf-8"))
             if DIVCACHE.exists() else fetch_dividend_schedule(tickers))

    ref = stdopd_reference()
    r_simple, r_src = risk_free()
    r_c = to_continuous(r_simple)
    asof = pd.Timestamp.utcnow().tz_localize(None).normalize()

    per_name, q_tr, q_wi, n_with_div = [], [], [], 0
    for row in rows:
        spot = row["spot"]
        q_trailing = row["q_simple"]
        q_tr.append(q_trailing)
        pts, qs = [], []
        for p in row["points"]:
            qw, n_div = q_for_window(sched.get(row["ticker"], {}), spot,
                                     p["days"], asof)
            qs.append(qw)
            ivc = implied_vol(p["call_mid"], spot, p["strike"],
                              p["days"] / 365.0, r_c, to_continuous(qw), True)
            ivp = implied_vol(p["put_mid"], spot, p["strike"],
                              p["days"] / 365.0, r_c, to_continuous(qw), False)
            if ivc and ivp:
                pts.append((p["days"], ivp - ivc))
        v = _interp_resid(pts)
        qw30 = float(np.median(qs)) if qs else 0.0
        q_wi.append(qw30)
        n_with_div += int(qw30 > 0)
        if v is not None:
            per_name.append({"ticker": row["ticker"], "resid": round(v, 6),
                             "q_trailing": round(q_trailing, 5),
                             "q_window": round(qw30, 5)})

    vals = np.asarray([r["resid"] for r in per_name], dtype=float)
    med, pos = float(np.median(vals)), float((vals > 0).mean())
    transfers = bool(abs(med - ref["median"]) <= MEDIAN_BAR
                     and abs(pos - ref["pct_positive"]) <= PCT_POS_BAR)

    conv = json.loads(CONVENTION.read_text(encoding="utf-8"))["arms"]
    print(f"names                      {len(per_name)}")
    print(f"median q_trailing          {float(np.median(q_tr)):.5f}")
    print(f"median q_window            {float(np.median(q_wi)):.5f}  "
          f"({n_with_div}/{len(q_wi)} names carry a dividend in the window)")
    print(f"R1 (q trailing)            {conv['R1_own_r_q']['median']:+.5f}  "
          f"{conv['R1_own_r_q']['pct_positive']:.1%}")
    print(f"R2 (q = 0)                 {conv['R2_own_r_only']['median']:+.5f}  "
          f"{conv['R2_own_r_only']['pct_positive']:.1%}")
    print(f"PREDICTED before running   {PREDICTED_MEDIAN:+.5f}")
    print(f"R7 (q over the WINDOW)     {med:+.5f}  {pos:.1%}   "
          f"{'TRANSFERS' if transfers else 'no'}")
    print(f"gap vs stdopd              {med - ref['median']:+.5f}")

    RECEIPT.write_text(json.dumps({
        "measurement_id": "OPTIONS-DIVIDEND-WINDOW-1",
        "licence": "PRODUCT_EXPERIMENT (servability — no IC, no forward "
                   "return, not evidence of alpha)",
        "declared_in": "scripts/options_dividend_window_measure.py (this file)",
        "hypothesis": ("the 0.0053 residue is a wrong q: trailing-12m yield "
                       "over-states the carry deduction for a 30-day option, "
                       "because a quarterly payer has an ex-date in a given "
                       "30-day window only about a third of the time"),
        "point_prediction_made_before_running": PREDICTED_MEDIAN,
        "prediction_basis": ("0.709 sensitivity x median q_trailing 0.0083 = "
                             "+0.0059 from R1's -0.00338"),
        "approximation": ("future ex-dates PROJECTED from the median historical "
                          "cadence; uses only past ex-dates, so no look-ahead, "
                          "and it is the same information a live collector has"),
        "stdopd_reference": ref,
        "r_simple": r_simple, "r_source": r_src,
        "median_q_trailing": round(float(np.median(q_tr)), 5),
        "median_q_window": round(float(np.median(q_wi)), 5),
        "n_names_with_dividend_in_window": n_with_div,
        "n_names": len(per_name),
        "R7": {
            "median": round(med, 5),
            "pct_positive": round(pos, 4),
            "median_gap_vs_stdopd": round(med - ref["median"], 5),
            "gate_median": bool(abs(med - ref["median"]) <= MEDIAN_BAR),
            "gate_pct_positive": bool(
                abs(pos - ref["pct_positive"]) <= PCT_POS_BAR),
            "transfers": transfers,
        },
        "prior_arms": {k: {"median": v.get("median"),
                           "pct_positive": v.get("pct_positive")}
                       for k, v in conv.items()},
        "per_name": per_name,
    }, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT}")


if __name__ == "__main__":
    main()
