"""The control the weekend's headline was never published beside.

WHY THIS FILE EXISTS
====================
`REVIEW_2026-09-06_ATTACK_ON_THE_WEEKEND.md` closes its CLAIM 1 section with
three things that would settle it. Two were already done by the time the review
landed (`W9_survivor_books_run40_v0.json` re-runs the DSR over 307 trials; the
share-basis gate was rebuilt to test the LEVEL). The third was not:

    "Publish the size-matched control table beside the raw excess. It is the
     difference between 'beats the market' and 'beats a cap-matched draw', and
     this claim survives both -- which is worth saying."

The reviewer computed it in a scratch session and quoted it in prose. CLAUDE.md:
**put every headline number in a receipt** -- `corr = 0.516` lived in prose only
and turned out to be a filtered subset nobody had named. So this script exists to
make that table durable, and to publish the THREE benchmarks side by side rather
than the one the build doc chose:

  * vs the VALUE-weighted CRSP market  (what the build doc reported)
  * vs the EQUAL-weighted CRSP market  (where the reviewer found no era alive)
  * vs a CAP-DECILE-MATCHED random draw at identical weights (the right control)

WHY THE MATCHED DRAW IS THE RIGHT CONTROL, AND THE SMB REGRESSION IS NOT
-----------------------------------------------------------------------
The book carries an SMB beta of 0.562 (t 5.13) on `mkt_ew_1m - mkt_vw_1m`, and
regressing the paired excess on that proxy takes t from 2.055 to 1.25. But
within its own covered universe the book sits at cap percentile 0.72-0.76 -- it
is NOT a small-cap book -- and the crude SMB proxy is driven by CRSP micro-caps
the book never holds. The regression over-controls. Replacing each holding with
a random name from the SAME within-month market-cap decile at the SAME weight
asks the question the regression was trying to ask, without borrowing a factor
built out of names the book cannot buy.

WHAT IS HELD FIXED
------------------
The control pays the BOOK's cost series, not its own. The question is whether
the SELECTION is doing work; giving the control a different turnover schedule
would fold a trading difference into a selection answer. This is stated on the
receipt so nobody has to infer it.

Usage:
    python -m scripts.size_matched_control                    # the headline arm
    python -m scripts.size_matched_control --feature net_rev_4w --seeds 10
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from learner import evaluate, inference
from learner import long_panel as LP

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "backend" / "data" / "optimus" / "continuation_2026-09-06"

#: The weekend's headline arm, exactly as `W9_survivor_books` booked it.
DEFAULT_FEATURE = "target_rev_1m__xs"
DEFAULT_K = 50
DEFAULT_COST_BPS = 10.0
N_CAP_DECILES = 10


def _monthly_book(d: pd.DataFrame, feature: str, k: int, month_col: str = "month"):
    """Reproduce `evaluate.book`'s selection and weights, month by month.

    Deliberately mirrors `evaluate.book` rather than calling it: the control
    needs the SELECTED ROWS and their weights, which `book()` does not return.
    The tie-break constant is imported from `evaluate` so the two cannot drift.
    """
    mo = d[month_col].astype(str).str.replace("-", "", regex=False).astype("int64")
    d = d.copy()
    d["_tb"] = (d["permno"].astype("int64") * 2_654_435_761 + mo * 97
                + evaluate.TIE_SEED) % 1_000_003
    out = {}
    for m, chunk in d.groupby(month_col, sort=True):
        ranked = chunk.sort_values([feature, "_tb"], ascending=[False, True])
        sel = ranked.head(k)
        if sel.empty:
            continue
        if "market_cap" in sel.columns and sel["market_cap"].notna().any():
            w = sel["market_cap"].fillna(sel["market_cap"].median()).clip(lower=0)
            w = w / w.sum() if w.sum() > 0 else pd.Series(1.0 / len(sel), index=sel.index)
        else:
            w = pd.Series(1.0 / len(sel), index=sel.index)
        out[m] = (sel, w.to_numpy(), chunk)
    return out


def _cap_decile(chunk: pd.DataFrame) -> pd.Series:
    """Within-month market-cap decile. Rows with no cap get their own bucket."""
    cap = chunk["market_cap"]
    try:
        dec = pd.qcut(cap.rank(method="first"), N_CAP_DECILES,
                      labels=False, duplicates="drop")
    except ValueError:                                            # too few rows
        dec = pd.Series(0, index=chunk.index)
    return dec.fillna(-1).astype(int)


def run(feature: str = DEFAULT_FEATURE, k: int = DEFAULT_K,
        cost_bps: float = DEFAULT_COST_BPS, seeds: int = 10,
        tradable_floor: float | None = None, price_floor: float | None = None) -> dict:
    df = LP.load_long()
    need = [feature, "fwd_1m", "mkt_vw_1m", "mkt_ew_1m", "market_cap", "month",
            "permno", "era"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        return {"verdict": inference.CANNOT_DETERMINE,
                "why": f"panel is missing {missing}"}
    cols = need + [c for c in ("close", "log_dollar_vol_20d", "dollar_vol_20d")
                   if c in df.columns]
    d = df[cols].dropna(subset=[feature, "fwd_1m", "mkt_vw_1m"]).copy()

    floors = {"tradable_dollar_vol": None, "price": None}
    if tradable_floor is not None:
        if "dollar_vol_20d" in d.columns and d["dollar_vol_20d"].notna().any():
            dv = d["dollar_vol_20d"]
        elif "log_dollar_vol_20d" in d.columns:
            dv = np.expm1(d["log_dollar_vol_20d"])
        else:
            raise SystemExit("REFUSED: a tradable floor was requested and the panel "
                             "carries no dollar-volume column. A liquidity gate with "
                             "no liquidity column silently passes everything.")
        d = d[dv.to_numpy() >= tradable_floor]
        floors["tradable_dollar_vol"] = float(tradable_floor)
    if price_floor is not None:
        if "close" not in d.columns:
            raise SystemExit("REFUSED: a price floor was requested and `close` is absent.")
        d = d[d["close"] >= price_floor]
        floors["price"] = float(price_floor)
    if d.empty:
        return {"verdict": inference.CANNOT_DETERMINE, "why": "no rows survive the floors"}

    sel_by_month = _monthly_book(d, feature, k)
    months = sorted(sel_by_month)
    if not months:
        return {"verdict": inference.CANNOT_DETERMINE, "why": "no month produced a book"}

    # ---- the book, and the two market legs on exactly the same months
    gross, mkt_vw, mkt_ew, weights, eras = {}, {}, {}, {}, {}
    for m in months:
        sel, w, _chunk = sel_by_month[m]
        gross[m] = float((w * sel["fwd_1m"].to_numpy()).sum())
        mkt_vw[m] = float(sel["mkt_vw_1m"].iloc[0])
        mkt_ew[m] = float(sel["mkt_ew_1m"].iloc[0])
        weights[m] = dict(zip(sel["permno"].astype(int).tolist(), w.tolist()))
        eras[m] = str(sel["era"].iloc[0]) if "era" in sel.columns else "?"

    g = pd.Series(gross).sort_index()
    turn, prev = [], None
    for m in g.index:
        cur = weights[m]
        if prev is None:
            turn.append(1.0)
        else:
            keys = set(cur) | set(prev)
            turn.append(0.5 * sum(abs(cur.get(kk, 0.0) - prev.get(kk, 0.0)) for kk in keys))
        prev = cur
    cost = pd.Series(turn, index=g.index) * (cost_bps / 10_000.0) * 2.0
    net = g - cost
    vw = pd.Series(mkt_vw).sort_index()
    ew = pd.Series(mkt_ew).sort_index()

    # ---- the cap-decile-matched control, averaged over `seeds` draws
    ctrl_draws = []
    for s in range(seeds):
        rng = np.random.default_rng(20260906 + s)
        rows = {}
        for m in months:
            sel, w, chunk = sel_by_month[m]
            dec = _cap_decile(chunk)
            chunk = chunk.assign(_dec=dec.to_numpy())
            sel_dec = chunk.loc[sel.index, "_dec"].to_numpy()
            picks = np.empty(len(sel), dtype=float)
            for i, dd in enumerate(sel_dec):
                pool = chunk.loc[chunk["_dec"].to_numpy() == dd, "fwd_1m"].to_numpy()
                picks[i] = rng.choice(pool) if pool.size else sel["fwd_1m"].to_numpy()[i]
            rows[m] = float((w * picks).sum())
        ctrl_draws.append(pd.Series(rows).sort_index())
    ctrl = pd.concat(ctrl_draws, axis=1).mean(axis=1)
    ctrl_net = ctrl - cost                    # the BOOK's cost series, on purpose

    def _tw(series: pd.Series) -> float:
        return float(np.prod(1.0 + series.to_numpy()))

    def _paired(a: pd.Series, b: pd.Series, label: str) -> dict:
        diff = (a - b).dropna()
        n = int(diff.size)
        mean = float(diff.mean())
        t = float(mean / (diff.std(ddof=1) / np.sqrt(n))) if n > 1 and diff.std(ddof=1) > 0 else float("nan")
        by_era = {}
        era_s = pd.Series({m: eras[m] for m in diff.index})
        for e, idx in era_s.groupby(era_s).groups.items():
            sub = diff.loc[list(idx)]
            if len(sub) < 2:
                continue
            se = sub.std(ddof=1) / np.sqrt(len(sub))
            by_era[str(e)] = {"months": int(len(sub)),
                              "mean_pct_per_month": round(float(sub.mean()) * 100, 4),
                              "t": round(float(sub.mean() / se), 3) if se > 0 else None,
                              "sign": int(np.sign(sub.mean()))}
        return {"benchmark": label, "months": n,
                "mean_pct_per_month": round(mean * 100, 4),
                "annualised_pct": round(((1 + mean) ** 12 - 1) * 100, 3),
                "t_paired": round(t, 3),
                "by_era": by_era}

    vs_vw = _paired(net, vw, "CRSP value-weighted market (what the build doc reported)")
    vs_ew = _paired(net, ew, "CRSP equal-weighted market")
    vs_ctrl = _paired(net, ctrl_net, f"cap-decile-matched random draw, identical weights, {seeds} seeds")

    inf = inference.deflated_sharpe((net - ctrl_net).dropna().tolist(), n_trials=307)
    pw = inference.power_note((net - ctrl_net).dropna().tolist(), periods_per_year=12)

    return {
        "job": "S2_size_matched_control",
        "question": ("does the weekend's headline arm beat a CAP-MATCHED draw, or only "
                     "a value-weighted market index?"),
        "feature": feature,
        "k": k, "weighting": "vw", "cost_bps_per_side": cost_bps,
        "seeds": seeds, "floors_applied": floors,
        "panel": "train_table_long.parquet (learner-train-table-3)",
        "months": len(months),
        "terminal_wealth": {
            "book_net": round(_tw(net), 4),
            "vw_market_same_months": round(_tw(vw), 4),
            "ew_market_same_months": round(_tw(ew), 4),
            "cap_matched_control_same_cost": round(_tw(ctrl_net), 4),
        },
        "paired_tests": {"vs_vw_market": vs_vw, "vs_ew_market": vs_ew,
                         "vs_cap_matched_control": vs_ctrl},
        "control_construction": (
            "each holding is replaced by a name drawn uniformly from the SAME "
            "within-month market-cap decile of the same eligible universe, at the "
            "IDENTICAL weight, averaged over the seeds. The control pays the BOOK's "
            "cost series, not its own, so the comparison isolates SELECTION and does "
            "not fold a turnover difference into it."),
        "deflated_sharpe_of_the_book_minus_control": inf,
        "power_of_the_book_minus_control": pw,
        "n_trials_note": ("307 is the trial count `W9_survivor_books_run40_v0.json` "
                          "computes for this weekend's whole search; this control is "
                          "not a new search and must not be priced as one cell."),
        "reading_rule": ("three benchmarks, three answers, and a claim is only as strong "
                         "as its weakest one. Quoting the VW line alone is the thing the "
                         "review objected to."),
        "written_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feature", default=DEFAULT_FEATURE)
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS)
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--tradable-floor", type=float, default=None)
    ap.add_argument("--price-floor", type=float, default=None)
    ap.add_argument("--run", default="01")
    a = ap.parse_args()
    payload = run(a.feature, a.k, a.cost_bps, a.seeds, a.tradable_floor, a.price_floor)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"S2_size_matched_control_run{a.run}.json"
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(json.dumps(payload.get("paired_tests", payload), indent=1))
    print(f"\nreceipt: {path}")


if __name__ == "__main__":
    main()
