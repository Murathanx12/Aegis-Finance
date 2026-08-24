"""OPTIONS-CONVENTION-1 — is the put-call residual a SIGNAL gap or a SOLVER gap?

DECLARED BEFORE THE NUMBERS EXIST. Arms, bars and decision rule below were
written and committed before a chain was pulled.

THE STANDING PROBLEM
====================
`EVENT_RESPONSE_v1` is fit on OptionMetrics `stdopd` and served on yfinance.
Three of four option features transfer. One does not:

    iv_put_minus_call_30d    live median -0.0237   stdopd median +0.0019
                             live 25% positive     stdopd 55% positive

Two routes are spent. A matched-strike residual moved the median only
-0.0254 -> -0.0237. A cross-sectional rank (`AMENDMENT-2`) passed exactly one
horizon per candidate arm, which is how a model gets chosen by whichever
horizon someone wrote down first.

WHAT BOTH ROUTES HELD FIXED
===========================
Both kept reading yfinance's `impliedVolatility` COLUMN — the output of Yahoo's
pricer under Yahoo's undisclosed assumptions about the risk-free rate, the
dividend, the exercise style and which price to invert. OptionMetrics inverts a
binomial American model against the bid/ask MIDPOINT with its own zero curve
and projected discrete dividends.

This feature is the one of the four where that matters most, and structurally
rather than by luck. By put-call parity a call and a put at the same strike are
tied, so a same-strike IV residual is close to a pure statement about the
pricer's r and q: it is a DIFFERENCE, so the level of volatility cancels and
the convention error does not. The other three are levels or same-side slopes,
where a shared bias largely cancels or is small beside the quantity.

That is why the matched-strike fix barely moved: it corrected WHICH strikes were
compared and left the disputed quantity — somebody else's implied vol —
completely intact.

THE ARMS
========
Every arm inverts the SAME chain at the SAME matched strike. Only the
convention changes.

  R0  vendor         yfinance `impliedVolatility`.  THE CONTROL — reproduces
                     the standing -0.0237.
  R1  own_r_q        our BSM inversion of the bid/ask MID, with a declared
                     continuous r from the Treasury curve and a declared
                     continuous q from trailing dividends. The candidate.
  R2  own_r_only     same, q = 0.  Isolates the DIVIDEND term.
  R3  own_zero       same, r = 0 and q = 0.  Isolates the RATE term — and it
                     is the diagnostic that identifies what Yahoo is assuming:
                     if R3 lands on R0, Yahoo is discounting nothing.
  R4  own_last       R1's convention inverted against the LAST TRADE instead of
                     the mid. Isolates the price basis, which on a thin strike
                     can move the residual by more than the whole gap.

Isolating one term per arm is the point. "Re-implied and it got better" is not
a diagnosis, and a fitted map that made the medians agree would be the thing
the rank route was chosen to avoid.

THE DECISION RULE, DECLARED
===========================
An arm TRANSFERS iff both:

  1. |median(arm) - median(stdopd)|      <= 0.005   (half a vol point)
  2. |pct_positive(arm) - pct_positive(stdopd)| <= 0.10

stdopd reference, from `train_serve_skew_receipt.json` (a committed file, not a
number retyped here): median +0.00194, 54.8% positive. R0 misses both by
0.0256 and 0.30.

If R1 transfers, the mismatch was a solver gap and the fix is to stop reading
the vendor's IV column — no calibration layer, nothing to drift.

If R1 does not transfer but moves most of the way, the receipt must say which
TERM carried it (R2 vs R3 vs R4) and the residue is named rather than fitted.

If R1 moves nothing, the difference is exercise style or discrete dividends —
the two things `option_implier` declares it does NOT model — and the honest
route is the review's fallback: ship the drop-feature arm as a labelled
PRODUCT_EXPERIMENT and say plainly it sits under its own MDE80.

NOT A CLAIM, and no forward return is touched. This is servability.

USAGE
    python -m scripts.options_convention_measure --names 40
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "backend/data/optimus/options_pit"
RECEIPT = OUT / "convention_receipt.json"
REFERENCE = OUT / "train_serve_skew_receipt.json"

MEDIAN_BAR = 0.005
PCT_POS_BAR = 0.10

#: Declared conventions. `r` is the 1-month Treasury as a simple annual yield;
#: `q` is trailing-12-month dividends over spot. Both are converted to
#: continuous compounding at use. Recorded on every row so a later reader can
#: re-derive the number instead of trusting this docstring.
R_FALLBACK = 0.0425
TARGET_DAYS = 30
BAND = 0.06


def stdopd_reference() -> dict:
    d = json.loads(REFERENCE.read_text(encoding="utf-8"))
    for row in d["distributions"]:
        if row["feature"] == "iv_put_minus_call_30d":
            return {"median": row["stdopd_median"],
                    "pct_positive": row["stdopd_pct_positive"],
                    "live_median_previously_measured": row["live_median"],
                    "live_pct_positive_previously_measured":
                        row["live_pct_positive"]}
    raise SystemExit("reference feature missing from the receipt")


def risk_free() -> tuple[float, str]:
    """1-month Treasury, simple annual. FRED if reachable, else declared."""
    try:
        from backend.services.data_fetcher import DataFetcher
        fred = DataFetcher().fetch_fred_data() or {}
        for key in ("fed_funds",):
            v = fred.get(key)
            v = v.get("value") if isinstance(v, dict) else v
            if v is not None and math.isfinite(float(v)):
                return float(v) / 100.0, f"FRED:{key}"
    except Exception as e:                                   # noqa: BLE001
        print(f"  (FRED unavailable: {type(e).__name__}) ")
    return R_FALLBACK, "declared fallback"


def universe(n: int) -> list[str]:
    from backend.config import config
    names: list[str] = []
    for v in config["stock_universe"]["sector_stocks"].values():
        names.extend(v)
    return sorted(set(names))[:n]


def one_name(ticker: str, r_simple: float) -> dict | None:
    """Every arm's residual for one name, off ONE chain pull."""
    import pandas as pd
    import yfinance as yf

    from backend.services.option_implier import (imply_matched_strike,
                                                 to_continuous)
    from backend.services.options_pit_store import (_interp_constant_maturity,
                                                    _matched_strike_iv)

    tk = yf.Ticker(ticker)
    hist = tk.history(period="1y", auto_adjust=False, actions=True)
    if hist is None or hist.empty:
        return None
    spot = float(hist["Close"].iloc[-1])
    if not spot or not math.isfinite(spot) or spot <= 0:
        return None

    divs = 0.0
    if "Dividends" in hist.columns:
        divs = float(hist["Dividends"].tail(252).sum())
    q_simple = divs / spot if spot else 0.0
    r_c, q_c = to_continuous(r_simple), to_continuous(q_simple)

    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    vend_c: list[tuple[float, float]] = []
    vend_p: list[tuple[float, float]] = []
    arms: dict[str, list[tuple[float, float]]] = {
        "R1_own_r_q": [], "R2_own_r_only": [], "R3_own_zero": [],
        "R4_own_last": []}
    basis_seen: list[str] = []

    for e in list(tk.options or []):
        days = (pd.Timestamp(e).normalize() - today).days
        if days <= 0 or days > TARGET_DAYS + 45:
            continue
        try:
            ch = tk.option_chain(e)
        except Exception:                                    # noqa: BLE001
            continue
        mc, mp = _matched_strike_iv(ch.calls, ch.puts, spot)
        if mc:
            vend_c.append((float(days), mc))
        if mp:
            vend_p.append((float(days), mp))
        for arm, (rr, qq) in (("R1_own_r_q", (r_c, q_c)),
                              ("R2_own_r_only", (r_c, 0.0)),
                              ("R3_own_zero", (0.0, 0.0))):
            pt = imply_matched_strike(ch.calls, ch.puts, spot, days, rr, qq,
                                      band=BAND)
            if pt and pt.iv_call and pt.iv_put:
                arms[arm].append((float(days), pt.iv_put - pt.iv_call))
                if arm == "R1_own_r_q":
                    basis_seen.append(pt.price_basis)
        pt_last = _imply_on_last(ch, spot, days, r_c, q_c)
        if pt_last is not None:
            arms["R4_own_last"].append((float(days), pt_last))

    def _interp_resid(points):
        """A residual is a DIFFERENCE, so it interpolates linearly in time —
        the total-variance rule used for IV levels does not apply to it and
        applying it anyway would be a third convention nobody declared."""
        pts = sorted(points)
        if not pts:
            return None
        below = [p for p in pts if p[0] <= TARGET_DAYS]
        above = [p for p in pts if p[0] >= TARGET_DAYS]
        if below and above:
            d0, v0 = below[-1]
            d1, v1 = above[0]
            if d0 == d1:
                return v0
            return v0 + (v1 - v0) * (TARGET_DAYS - d0) / (d1 - d0)
        d, v = (below[-1] if below else above[0])
        return v if abs(d - TARGET_DAYS) <= 15 else None

    c30 = _interp_constant_maturity(vend_c, TARGET_DAYS)
    p30 = _interp_constant_maturity(vend_p, TARGET_DAYS)
    row = {"ticker": ticker, "spot": round(spot, 2),
           "q_simple": round(q_simple, 5), "r_simple": round(r_simple, 5),
           "price_basis": (max(set(basis_seen), key=basis_seen.count)
                           if basis_seen else None),
           "R0_vendor": (round(p30 - c30, 6)
                         if (c30 is not None and p30 is not None) else None)}
    for arm, pts in arms.items():
        v = _interp_resid(pts)
        row[arm] = round(v, 6) if v is not None else None
    return row


def _imply_on_last(ch, spot, days, r_c, q_c):
    """R4: the same convention, inverted against the LAST TRADE."""
    from backend.services.option_implier import implied_vol

    calls, puts = ch.calls, ch.puts
    if calls is None or puts is None or calls.empty or puts.empty:
        return None
    cb = {float(x["strike"]): x for _, x in calls.iterrows()}
    pb = {float(x["strike"]): x for _, x in puts.iterrows()}
    t = float(days) / 365.0
    for k in sorted(set(cb) & set(pb), key=lambda x: abs(x - spot)):
        if abs(k - spot) > spot * BAND:
            break
        try:
            pc, pp = float(cb[k]["lastPrice"]), float(pb[k]["lastPrice"])
        except Exception:                                    # noqa: BLE001
            continue
        if not (pc > 0 and pp > 0):
            continue
        ivc = implied_vol(pc, spot, k, t, r_c, q_c, True)
        ivp = implied_vol(pp, spot, k, t, r_c, q_c, False)
        if ivc and ivp:
            return ivp - ivc
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=int, default=40)
    args = ap.parse_args()

    ref = stdopd_reference()
    r_simple, r_src = risk_free()
    print(f"r = {r_simple:.4f} ({r_src})")

    rows = []
    for i, t in enumerate(universe(args.names), 1):
        try:
            row = one_name(t, r_simple)
        except Exception as e:                               # noqa: BLE001
            print(f"  {t}: {type(e).__name__}: {e}")
            continue
        if row:
            rows.append(row)
        if i % 10 == 0:
            print(f"  {i}/{args.names}")

    arms = ["R0_vendor", "R1_own_r_q", "R2_own_r_only", "R3_own_zero",
            "R4_own_last"]
    summary = {}
    for arm in arms:
        vals = np.asarray([r[arm] for r in rows if r.get(arm) is not None],
                          dtype=float)
        if not vals.size:
            summary[arm] = {"n": 0}
            continue
        med = float(np.median(vals))
        pos = float((vals > 0).mean())
        summary[arm] = {
            "n": int(vals.size),
            "median": round(med, 5),
            "pct_positive": round(pos, 4),
            "p10": round(float(np.percentile(vals, 10)), 5),
            "p90": round(float(np.percentile(vals, 90)), 5),
            "median_gap_vs_stdopd": round(med - ref["median"], 5),
            "pct_pos_gap_vs_stdopd": round(pos - ref["pct_positive"], 4),
            "gate_median": bool(abs(med - ref["median"]) <= MEDIAN_BAR),
            "gate_pct_positive": bool(
                abs(pos - ref["pct_positive"]) <= PCT_POS_BAR),
        }
        summary[arm]["transfers"] = bool(summary[arm].get("gate_median")
                                         and summary[arm].get(
                                             "gate_pct_positive"))
        s = summary[arm]
        print(f"{arm:16s} n {s['n']:3d}  median {s['median']:+.5f} "
              f"(gap {s['median_gap_vs_stdopd']:+.5f})  "
              f"pos {s['pct_positive']:.1%}  "
              f"{'TRANSFERS' if s['transfers'] else 'no'}")

    OUT.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps({
        "measurement_id": "OPTIONS-CONVENTION-1",
        "licence": "PRODUCT_EXPERIMENT (servability — no IC, no forward "
                   "return, not evidence of alpha)",
        "declared_in": "scripts/options_convention_measure.py (this file)",
        "question": ("is the iv_put_minus_call_30d train/serve gap a SIGNAL "
                     "difference or an artefact of inverting the vendor's "
                     "implied-vol column instead of the prices?"),
        "stdopd_reference": ref,
        "conventions": {"r_simple": r_simple, "r_source": r_src,
                        "q": "trailing 12m dividends / spot, per name",
                        "model": "Black-Scholes-Merton, European",
                        "not_modelled": ["American early exercise",
                                         "discrete dividends"]},
        "bars": {"median": MEDIAN_BAR, "pct_positive": PCT_POS_BAR},
        "n_names_attempted": args.names,
        "n_names_measured": len(rows),
        "arms": summary,
        "per_name": rows,
    }, indent=1), encoding="utf-8")
    print(f"\nreceipt -> {RECEIPT}")


if __name__ == "__main__":
    main()
