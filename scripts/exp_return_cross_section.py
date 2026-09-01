"""Can exp_return be STOCK-SPECIFIC, and how does the engine compare to analysts?

    python -m scripts.exp_return_cross_section --run
    python -m scripts.exp_return_cross_section --run --start 2013 --end 2024

TWO QUESTIONS, ONE PANEL (Murat + the GPT review, 2026-09-01)
=============================================================
S33 measured that the long-book coherence floor is non-positive on 722 of 766
names and that 41 of the 44 positives are two constants: the category prior IS
the opportunity set, and the 764-distinct-value ranking does nothing. The
review's proposal: stop using the category base rate AS the stock's expected
return; use it as a prior and let stock-specific evidence move names off it.

That proposal is a hypothesis, and this script is the adjudication:

  Q1  WITHIN the region the book may actually buy (upside 1.5..5, >=$2, no
      split in the prior year, >=2 analysts), does ANY stock-level feature
      separate forward returns month after month? If yes, the measured tilt
      becomes the stock-specific term and its t-stat sizes the shrinkage. If
      no, the constant prior is all the data supports and the "decorative
      ranking" is the honest state of knowledge, not a bug.

  Q2  Murat's ask verbatim: "make a backtest on what the company thinks now on
      a past stock ... compare it to the analyst reviews and then compare it
      to the reality." At every month 2013-2024: what the CURRENT engine rules
      select, what analyst RATINGS select, what analyst TARGETS select, and
      what each earned -- including the two disagreement cells that matter
      (engine-buy/analyst-shun, and toxic-band/analyst-love).

IN-SAMPLE, AND LABELLED IN-SAMPLE
=================================
The band thresholds being "tested" in Q2 were chosen FROM receipts measured on
this same panel. Q2 is therefore a consistency check and a decomposition, not
out-of-sample validation -- the forward paper books are the out-of-sample
test. The tilt-ranked book in Q1 uses full-sample coefficients and is the most
in-sample number here; it is a CEILING estimate, printed as such.

Licence: PRODUCT_EXPERIMENT. Grading is paired excess vs the equal-weight
market, identical convention to the parent so numbers line up.
Receipt: backend/data/optimus/tracker_backtest/exp_return_cross_section.json
Parent:  scripts/tracker_ibes_backtest.py (machinery imported, never retyped).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.tracker_ibes_backtest import build_monthly, label, load_tracker_rules

OUT = Path(__file__).resolve().parent.parent / "backend" / "data" / "optimus" / "tracker_backtest"
BULK = Path(__file__).resolve().parent.parent / "backend" / "data" / "optimus" / "wrds" / "bulk"

#: The region the live book is permitted to hold: clause (a) floor to the
#: toxic-band ceiling, plus the CLEAN-cell hygiene the S30b decontamination
#: showed is load-bearing (sub-$2 uninformative, split = unreadable upside,
#: 1-analyst = one stale voice).
#:
#: UNITS: the panel's `upside` is target/close - 1 (a RETURN), while
#: `murat_rule.BAND_PRIOR` keys on target/close (a RATIO). Clause (a)
#: ratio >= 1.5 is upside >= 0.5; the toxic bar ratio >= 5 is upside >= 4;
#: the lost-winners band ratio 3..5 is upside 2..4. The first run of this
#: script used ratio bounds on the return column and measured a region
#: shifted one band up -- the receipt it wrote was discarded.
ADMIT = dict(upside_lo=0.5, upside_hi=4.0, min_price=2.0, min_coverage=2)

#: Q1 features. `ret_12m` INCLUDES the most recent month (CRSP trailing total
#: return as built by the parent); classic 12-1 momentum excludes it. Stated
#: here so a momentum tilt is not over-read.
FEATURES = ["upside", "consensus", "ret_12m", "drawdown_60d", "log_coverage", "log_dollar_vol"]

MIN_NAMES_PER_MONTH = 40


def monthly_spread_stats(spread: pd.Series) -> dict | None:
    """Mean/t of a monthly return-spread series. Months ARE the date blocks."""
    s = spread.dropna()
    if len(s) < 24:
        return None
    t = float(s.mean() / (s.std() / np.sqrt(len(s)))) if s.std() > 0 else None
    return {"months": int(len(s)),
            "annualised": round(float(s.mean()) * 12, 4),
            "t_stat": round(t, 3) if t is not None else None,
            "share_months_positive": round(float((s > 0).mean()), 4)}


def quintile_tilt(adm: pd.DataFrame, col: str) -> dict | None:
    """Q5-Q1 forward-return spread of per-month quintiles WITHIN the region."""
    rows = adm[adm[col].notna()]
    q5, q1 = [], []
    for month, chunk in rows.groupby("month"):
        if len(chunk) < MIN_NAMES_PER_MONTH:
            continue
        ranks = chunk[col].rank(pct=True)
        top, bot = chunk[ranks >= 0.8], chunk[ranks <= 0.2]
        if top.empty or bot.empty:
            continue
        q5.append((month, top["fwd_1m"].mean()))
        q1.append((month, bot["fwd_1m"].mean()))
    if not q5:
        return None
    s5 = pd.Series(dict(q5))
    s1 = pd.Series(dict(q1))
    stats = monthly_spread_stats(s5 - s1)
    if stats is None:
        return None
    return {**stats, "q5_annualised": round(float(s5.mean()) * 12, 4),
            "q1_annualised": round(float(s1.mean()) * 12, 4)}


def fama_macbeth(adm: pd.DataFrame) -> dict:
    """Per-month cross-sectional OLS of fwd_1m on z-scored features.

    Coefficients are collected monthly and the t-stat is computed ACROSS
    months -- each month is one observation of the cross-section (§58), so a
    feature must work repeatedly, not once in one regime, to clear zero.
    """
    coefs: list[np.ndarray] = []
    months_used = 0
    rows_used = 0
    for month, chunk in adm.groupby("month"):
        sub = chunk.dropna(subset=FEATURES + ["fwd_1m"])
        if len(sub) < MIN_NAMES_PER_MONTH:
            continue
        X = sub[FEATURES].to_numpy(dtype=float)
        mu, sd = X.mean(axis=0), X.std(axis=0)
        sd[sd == 0] = 1.0
        Xz = (X - mu) / sd
        Xz = np.column_stack([np.ones(len(Xz)), Xz])
        y = sub["fwd_1m"].to_numpy(dtype=float)
        beta, *_ = np.linalg.lstsq(Xz, y, rcond=None)
        coefs.append(beta[1:])
        months_used += 1
        rows_used += len(sub)
    if not coefs:
        return {"months": 0}
    C = np.vstack(coefs)
    out = {"months": months_used, "name_months": rows_used, "features": {}}
    for i, f in enumerate(FEATURES):
        c = C[:, i]
        t = float(c.mean() / (c.std() / np.sqrt(len(c)))) if c.std() > 0 else None
        out["features"][f] = {
            "mean_monthly_coef_per_sd": round(float(c.mean()), 5),
            "t_stat_across_months": round(t, 3) if t is not None else None,
        }
    out["mean_coefs_vector"] = {f: round(float(C[:, i].mean()), 6)
                                for i, f in enumerate(FEATURES)}
    return out


def book_stats(lab: pd.DataFrame, mask: pd.Series, market: pd.Series) -> dict | None:
    """Grade one selection rule as a monthly EW book vs the market, paired."""
    sub = lab[mask]
    if len(sub) < 300:
        return None
    per_month = sub.groupby("month")["fwd_1m"].mean()
    spread = (per_month - market.reindex(per_month.index)).dropna()
    stats = monthly_spread_stats(spread)
    if stats is None:
        return None
    aligned = per_month.reindex(spread.index)
    by_year: dict[str, float] = {}
    for y, chunk in spread.groupby(spread.index.str[:4]):
        by_year[y] = round(float(chunk.mean()) * 12, 4)
    return {**stats,
            "name_months": int(len(sub)),
            "avg_names_per_month": round(float(sub.groupby("month").size().mean()), 1),
            "terminal_wealth": round(float((1 + aligned).prod()), 3),
            "terminal_wealth_market_same_months": round(
                float((1 + market.reindex(spread.index)).prod()), 3),
            "annualised_excess_by_year": by_year}


def tickers_for(permnos: set[int]) -> dict[int, str]:
    nm = pd.read_parquet(BULK / "crsp__stocknames.parquet",
                         columns=["permno", "nameenddt", "ticker", "comnam"])
    nm = nm[nm["permno"].isin(permnos)].sort_values("nameenddt")
    return {int(r.permno): f"{r.ticker} ({str(r.comnam).title()})"
            for r in nm.itertuples() if pd.notna(r.ticker)}


def run(start: int, end: int, lag_days: int) -> dict:
    T, tracker_sha = load_tracker_rules()
    df = build_monthly(start, end, lag_days)

    # fwd_12m from the total-return index, same-name row 12 cuts ahead, with a
    # calendar guard: a name that left the panel and returned would otherwise
    # report a multi-year gap as "12 months".
    df = df.sort_values(["permno", "statpers"])
    g = df.groupby("permno", sort=False)
    df["tri_12"] = g["tri"].shift(-12)
    gap12 = (g["statpers"].shift(-12) - df["statpers"]).dt.days
    df["fwd_12m"] = np.where((gap12 >= 330) & (gap12 <= 430),
                             df["tri_12"] / df["tri"] - 1.0, np.nan)

    lab = label(df, T)
    lab = lab.merge(df[["permno", "month", "fwd_12m"]]
                    .rename(columns={"permno": "symbol"}),
                    on=["symbol", "month"], how="left")

    lab["log_coverage"] = np.log1p(lab["coverage"])
    lab["log_dollar_vol"] = np.log(lab["dollar_vol_20d"].where(lab["dollar_vol_20d"] > 0))

    hygiene = ((lab["close"] >= ADMIT["min_price"])
               & ~lab["split_prior_year"]
               & (lab["coverage"] >= ADMIT["min_coverage"])
               & lab["upside"].notna())
    admissible = hygiene & (lab["upside"] >= ADMIT["upside_lo"]) & (lab["upside"] < ADMIT["upside_hi"])
    band_35 = admissible & (lab["upside"] >= 2.0)
    toxic = hygiene & (lab["upside"] >= ADMIT["upside_hi"])
    rating_bull = lab["consensus"] >= 4.1

    market = lab.groupby("month")["fwd_1m"].mean()
    adm = lab[admissible]

    # ---- Q1: the within-region cross-section
    tilts = {f: quintile_tilt(adm, f) for f in FEATURES}
    fm = fama_macbeth(adm)

    # The in-sample CEILING: rank the admissible region by the full-sample FM
    # score and hold the top quintile. Full-sample coefficients see the future.
    score_cols = fm.get("mean_coefs_vector") or {}
    tilt_book = None
    if score_cols:
        sc = np.zeros(len(lab))
        ok = np.ones(len(lab), dtype=bool)
        for f, w in score_cols.items():
            v = lab[f].to_numpy(dtype=float)
            ok &= ~np.isnan(v)
            sc = sc + np.where(np.isnan(v), 0.0, v) * w
        lab["_tilt_score"] = np.where(ok, sc, np.nan)
        top_mask = pd.Series(False, index=lab.index)
        for month, chunk in lab[admissible & lab["_tilt_score"].notna()].groupby("month"):
            if len(chunk) < MIN_NAMES_PER_MONTH:
                continue
            cut = chunk["_tilt_score"].quantile(0.8)
            top_mask.loc[chunk[chunk["_tilt_score"] >= cut].index] = True
        tilt_book = book_stats(lab, top_mask, market)

    # ---- Q2: engine vs analysts vs reality
    books = {
        "BAND_below_1_5": book_stats(lab, hygiene & (lab["upside"] < ADMIT["upside_lo"]), market),
        "BAND_1_5_to_3_alone": book_stats(lab, admissible & (lab["upside"] < 2.0), market),
        "ENGINE_TODAY_band_3_5": book_stats(lab, band_35, market),
        "ENGINE_admissible_region": book_stats(lab, admissible, market),
        "ANALYST_rating_ge_4.1": book_stats(lab, hygiene & rating_bull, market),
        "ANALYST_strong_ge_4.5": book_stats(lab, hygiene & (lab["consensus"] >= 4.5), market),
        "ANALYST_top_target_quintile": None,
        "TOXIC_band_ge_5": book_stats(lab, toxic, market),
        "TILT_RANKED_top_quintile_IN_SAMPLE_CEILING": tilt_book,
    }
    tgt_mask = pd.Series(False, index=lab.index)
    for month, chunk in lab[hygiene].groupby("month"):
        if len(chunk) < MIN_NAMES_PER_MONTH:
            continue
        cut = chunk["upside"].quantile(0.8)
        tgt_mask.loc[chunk[chunk["upside"] >= cut].index] = True
    books["ANALYST_top_target_quintile"] = book_stats(lab, tgt_mask, market)

    disagreement = {
        "engine_yes_analyst_no": book_stats(lab, admissible & ~rating_bull, market),
        "engine_yes_analyst_yes": book_stats(lab, admissible & rating_bull, market),
        "engine_toxic_analyst_yes": book_stats(lab, toxic & rating_bull, market),
        "engine_toxic_analyst_no": book_stats(lab, toxic & ~rating_bull, market),
    }

    # Calibration: what each side CLAIMS vs what happened.
    #   engine: the sealed band 3..5 exp_return is +1.725%/mo -- is that the
    #   realized in-region mean?  analysts: a target is ~12m ahead, so implied
    #   12m return is upside-1; graded per upside decile.
    band_rows = lab[band_35]
    calib_engine = {
        "claimed_monthly_exp_return_band_3_5": round(0.20700 / 12.0, 5),
        "realized_mean_fwd_1m_band_3_5": round(float(band_rows["fwd_1m"].mean()), 5),
        "realized_median_fwd_1m_band_3_5": round(float(band_rows["fwd_1m"].median()), 5),
        "n": int(len(band_rows)),
        "note": ("claimed is the RECEIPT mean (annualised excess/12) used as the sealed "
                 "exp_return; realized here is RAW not excess -- the gap between raw and "
                 "excess is the market's own monthly mean"),
    }
    calib_analyst = []
    hyg12 = lab[hygiene & lab["fwd_12m"].notna()]
    if len(hyg12) > 1000:
        deciles = pd.qcut(hyg12["upside"], 10, duplicates="drop")
        for dec, chunk in hyg12.groupby(deciles, observed=True):
            calib_analyst.append({
                "upside_range": f"{chunk['upside'].min():.2f}..{chunk['upside'].max():.2f}",
                "implied_12m_return_median": round(float(chunk["upside"].median()), 3),
                "realized_12m_mean": round(float(chunk["fwd_12m"].mean()), 3),
                "realized_12m_median": round(float(chunk["fwd_12m"].median()), 3),
                "n": int(len(chunk)),
            })

    # Examples for the two cells Murat will ask about, best and worst by fwd_1m.
    tick = tickers_for(set(lab.loc[admissible & ~rating_bull, "symbol"].astype(int))
                       | set(lab.loc[toxic & rating_bull, "symbol"].astype(int)))

    def examples(mask: pd.Series) -> dict:
        sub = lab[mask].dropna(subset=["fwd_1m"])
        cols = ["symbol", "month", "upside", "consensus", "fwd_1m"]
        pick = lambda d: [{**{c: (round(float(r[c]), 3) if isinstance(r[c], float) else r[c])
                              for c in cols},
                           "name": tick.get(int(r["symbol"]), "?")}
                          for _, r in d[cols].iterrows()]
        return {"best": pick(sub.nlargest(5, "fwd_1m")),
                "worst": pick(sub.nsmallest(5, "fwd_1m"))}

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "PRODUCT_EXPERIMENT",
        "window": f"{start}-{end}",
        "tracker_sha256": tracker_sha,
        "admissible_region": ADMIT,
        "in_sample_note": ("band thresholds were chosen from receipts measured on this panel; "
                           "Q2 is a decomposition, not out-of-sample validation. The tilt-ranked "
                           "book uses full-sample coefficients and is a CEILING."),
        "region_counts": {
            "panel_name_months": int(len(lab)),
            "hygiene": int(hygiene.sum()),
            "admissible": int(admissible.sum()),
            "band_3_5": int(band_35.sum()),
            "toxic_ge_5": int(toxic.sum()),
        },
        "q1_within_region_tilts_q5_minus_q1": tilts,
        "q1_fama_macbeth": fm,
        "q2_books": books,
        "q2_disagreement_2x2": disagreement,
        "q2_calibration_engine": calib_engine,
        "q2_calibration_analyst_targets_12m": calib_analyst,
        "examples_engine_yes_analyst_no": examples(admissible & ~rating_bull),
        "examples_toxic_analyst_yes": examples(toxic & rating_bull),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--lag-days", type=int, default=3)
    args = ap.parse_args()
    if not args.run:
        print(__doc__)
        return 0
    report = run(args.start, args.end, args.lag_days)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "exp_return_cross_section.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nreceipt: {out}")
    fm = report["q1_fama_macbeth"].get("features", {})
    print("\nQ1 Fama-MacBeth (per-sd monthly coef, t across months):")
    for f, s in fm.items():
        print(f"  {f:16s} {s['mean_monthly_coef_per_sd']:+.5f}  t {s['t_stat_across_months']}")
    print("\nQ2 books (annualised excess vs market, t):")
    for k, v in report["q2_books"].items():
        if v:
            print(f"  {k:44s} {v['annualised']:+.2%}  t {v['t_stat']}  "
                  f"({v['avg_names_per_month']} names/mo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
