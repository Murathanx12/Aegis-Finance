"""AEGIS TIME-MACHINE ARENA v1 -- freeze a date, let every mind speak, reveal
the future, score everyone.

    python -m scripts.time_machine_arena --run
    python -m scripts.time_machine_arena --run --start 2015 --end 2024

THE INSTRUMENT (Murat, 2026-09-01)
==================================
    "Take historical dates ... literally pretend we are living on that date.
     AEGIS is allowed to see only information publicly knowable then. ...
     Alongside it we save contemporaneous competitors. Then reveal the
     future. ... That is far more useful than asking whether today's five
     trades happen to be green."

Every month-end 2015-2024, four eras, six minds, four horizons:

  minds     AEGIS (BAND_PRIOR v2 verdicts) | STREET rating | STREET target |
            SKILL-WEIGHTED STREET (per-analyst bias removed, PIT) |
            MOMENTUM (12m) | MARKET (equal weight)
  horizons  1m / 3m / 6m / 12m forward, total-return, delisting included
  eras      2015-2018 pre-COVID | 2019-2021 COVID/liquidity |
            2022 rate shock | 2023-2024 AI/mega-cap

WHAT IS AND IS NOT PIT HERE
===========================
* Prices, targets, ratings, coverage: IBES statpers cuts traded at the first
  close strictly after the cut (parent machinery).
* SKILL STREET's per-analyst bias uses only targets whose 12-month OUTCOME
  had resolved before the frozen date, expanding-window, shrunk toward the
  pooled bias -- an analyst with no resolved history gets the pooled prior.
* AEGIS's band thresholds are the one deliberate anachronism: they were
  chosen from receipts measured ON this panel (2013-2024). The arena is
  therefore a DECOMPOSITION of where those rules win and lose against the
  street era by era -- not out-of-sample proof they work. The forward paper
  books are the out-of-sample test. Stated here and in the receipt.

t-STATS ON OVERLAPPING HORIZONS
===============================
3/6/12-month forward windows overlap month to month, which inflates naive t.
Every multi-month cell reports BOTH the overlapping t (optimistic) and the t
on the non-overlapping subsample (every 3rd/6th/12th month; honest, fewer
blocks). Read the second one.

Licence: PRODUCT_EXPERIMENT. Row-level output is a LOCAL parquet; the
receipt carries the scoreboards and the disagreement cells.
Receipt: backend/data/optimus/tracker_backtest/time_machine_arena.json
Rows:    backend/data/optimus/wrds/time_machine_arena_rows.parquet (local)
Parent:  scripts/tracker_ibes_backtest.py + scripts/analyst_target_grades.py
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

REPO = Path(__file__).resolve().parent.parent
BULK = REPO / "backend" / "data" / "optimus" / "wrds" / "bulk"
GRADES = REPO / "backend" / "data" / "optimus" / "wrds" / "analyst_target_grades.parquet"
OUT_RECEIPT = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "time_machine_arena.json"
OUT_ROWS = REPO / "backend" / "data" / "optimus" / "wrds" / "time_machine_arena_rows.parquet"

ERAS = {"2015-2018_preCOVID": (2015, 2018),
        "2019-2021_liquidity": (2019, 2021),
        "2022_rate_shock": (2022, 2022),
        "2023-2024_AI_megacap": (2023, 2024)}

HORIZONS = {"1m": 1, "3m": 3, "6m": 6, "12m": 12}

#: v2 band bounds in the panel's upside units (target/close - 1).
TOXIC_LO, ADMIT_LO = 4.0, 0.5

#: Bias shrinkage for SKILL STREET: bias_hat = n/(n+K) * mean_resolved_error.
SHRINK_K = 10

MIN_NAMES = 40


def forward_horizons(df: pd.DataFrame) -> pd.DataFrame:
    """fwd_{3,6,12}m from the total-return index, calendar-guarded."""
    df = df.sort_values(["permno", "statpers"])
    g = df.groupby("permno", sort=False)
    for name, k in HORIZONS.items():
        if k == 1:
            continue
        tri_k = g["tri"].shift(-k)
        gap = (g["statpers"].shift(-k) - df["statpers"]).dt.days
        lo, hi = k * 30 - 12, k * 30 + 35
        df[f"fwd_{name}"] = np.where((gap >= lo) & (gap <= hi),
                                     tri_k / df["tri"] - 1.0, np.nan)
    return df


def skill_street(lab: pd.DataFrame) -> pd.Series:
    """Per (symbol, month): mean bias-corrected implied return, PIT.

    Each analyst's bias is the expanding mean of (implied - realized) over
    their OWN targets whose outcome had resolved before this target's
    announcement, shrunk toward the pooled expanding bias. Correction is
    applied per target; the name's score is the mean corrected implied over
    targets announced in the 90 days before the frozen month's cut.
    """
    t = pd.read_parquet(GRADES)
    t = t.sort_values("anndats").reset_index(drop=True)
    t["resolved"] = t["anndats"] + pd.Timedelta(days=380)

    # expanding per-analyst bias over RESOLVED targets only: iterate in
    # announcement order, consuming a resolution queue sorted by resolve date.
    res_order = t.sort_values("resolved").index.to_numpy()
    res_dates = t["resolved"].to_numpy()
    ann_dates = t["anndats"].to_numpy()
    errors = t["error"].to_numpy()
    analysts = t["amaskcd"].to_numpy()

    sums: dict = {}
    counts: dict = {}
    pooled_sum = 0.0
    pooled_n = 0
    bias_hat = np.zeros(len(t))
    j = 0
    order = np.argsort(ann_dates, kind="stable")
    for i in order:
        while j < len(res_order) and res_dates[res_order[j]] <= ann_dates[i]:
            k = res_order[j]
            a = analysts[k]
            sums[a] = sums.get(a, 0.0) + errors[k]
            counts[a] = counts.get(a, 0) + 1
            pooled_sum += errors[k]
            pooled_n += 1
            j += 1
        a = analysts[i]
        n = counts.get(a, 0)
        pooled = (pooled_sum / pooled_n) if pooled_n else 0.0
        own = (sums.get(a, 0.0) / n) if n else pooled
        w = n / (n + SHRINK_K)
        bias_hat[i] = w * own + (1 - w) * pooled
    t["bias_hat"] = bias_hat
    t["corrected"] = t["implied"] - t["bias_hat"]

    # map onto the arena's (permno, month) grid: targets announced in the 90d
    # before each month's statpers-cut are that month's live opinions.
    t["month"] = t["anndats"].dt.to_period("M").astype(str)
    recent = []
    for shift in (0, 1, 2):
        s = t.copy()
        s["month"] = (s["anndats"] + pd.offsets.MonthBegin(shift)).dt.to_period("M").astype(str)
        recent.append(s[["permno", "month", "corrected"]])
    r = pd.concat(recent)
    return r.groupby(["permno", "month"])["corrected"].mean()


def cell(spread: pd.Series, k: int) -> dict | None:
    """Annualised mean + overlapping AND non-overlapping t for horizon k months."""
    s = spread.dropna()
    if len(s) < max(12, 2 * k):
        return None
    tov = float(s.mean() / (s.std() / np.sqrt(len(s)))) if s.std() > 0 else None
    sub = s.iloc[::k]
    tno = (float(sub.mean() / (sub.std() / np.sqrt(len(sub))))
           if len(sub) >= 8 and sub.std() > 0 else None)
    return {"months": int(len(s)),
            "annualised_excess": round(float(s.mean()) * 12 / k, 4),
            "t_overlapping": round(tov, 2) if tov is not None else None,
            "t_nonoverlapping": round(tno, 2) if tno is not None else None,
            "share_positive": round(float((s > 0).mean()), 3)}


def grade_mind(lab: pd.DataFrame, mask: pd.Series, market: dict) -> dict:
    out = {"avg_names_per_month": round(float(
        lab[mask].groupby("month").size().mean()), 1) if mask.any() else 0.0}
    for hname, k in HORIZONS.items():
        col = "fwd_1m" if k == 1 else f"fwd_{hname}"
        sub = lab[mask & lab[col].notna()]
        if len(sub) < 300:
            out[hname] = None
            continue
        per_month = sub.groupby("month")[col].mean()
        spread = (per_month - market[hname].reindex(per_month.index)).dropna()
        out[hname] = cell(spread, k)
    return out


def run(start: int, end: int, lag_days: int) -> dict:
    T, tracker_sha = load_tracker_rules()
    df = build_monthly(start, end, lag_days)
    df = forward_horizons(df)
    lab = label(df, T)
    extra = df[["permno", "month"] + [f"fwd_{h}" for h in HORIZONS if h != "1m"]]
    lab = lab.merge(extra.rename(columns={"permno": "symbol"}),
                    on=["symbol", "month"], how="left")

    hygiene = ((lab["close"] >= 2.0) & ~lab["split_prior_year"]
               & (lab["coverage"] >= 2) & lab["upside"].notna())
    aegis_buy = hygiene & (lab["upside"] >= ADMIT_LO) & (lab["upside"] < TOXIC_LO)
    aegis_avoid = hygiene & (lab["upside"] >= TOXIC_LO)
    street_buy = hygiene & (lab["consensus"] >= 4.1)
    street_sell = hygiene & (lab["consensus"] <= 2.5)

    # per-month top quintiles: raw target-implied, skill-corrected, momentum
    lab["skill_implied"] = np.nan
    if GRADES.exists():
        sk = skill_street(lab)
        lab = lab.merge(sk.rename("skill_implied_m"),
                        left_on=["symbol", "month"], right_index=True, how="left")
        lab["skill_implied"] = lab["skill_implied_m"]
    else:
        print("  WARNING: analyst_target_grades.parquet missing -- SKILL STREET skipped")

    def top_quintile(col: str) -> pd.Series:
        m = pd.Series(False, index=lab.index)
        for month, chunk in lab[hygiene & lab[col].notna()].groupby("month"):
            if len(chunk) < MIN_NAMES:
                continue
            cut = chunk[col].quantile(0.8)
            m.loc[chunk[chunk[col] >= cut].index] = True
        return m

    minds = {
        "AEGIS_admissible": aegis_buy,
        "AEGIS_avoid_toxic": aegis_avoid,
        "STREET_rating_buy": street_buy,
        "STREET_rating_sell": street_sell,
        "STREET_target_top_quintile": top_quintile("upside"),
        "SKILL_STREET_top_quintile": (top_quintile("skill_implied")
                                      if lab["skill_implied"].notna().any() else None),
        "MOMENTUM_top_quintile": top_quintile("ret_12m"),
    }

    market = {}
    for hname, k in HORIZONS.items():
        col = "fwd_1m" if k == 1 else f"fwd_{hname}"
        market[hname] = lab[lab[col].notna()].groupby("month")[col].mean()

    lab["era"] = ""
    for era, (y0, y1) in ERAS.items():
        m = lab["month"].str[:4].astype(int).between(y0, y1)
        lab.loc[m, "era"] = era

    scoreboard: dict = {}
    for era in list(ERAS) + ["ALL"]:
        emask = (lab["era"] == era) if era != "ALL" else pd.Series(True, index=lab.index)
        scoreboard[era] = {}
        for mind, mmask in minds.items():
            if mmask is None:
                scoreboard[era][mind] = "SKIPPED: no skill grades"
                continue
            scoreboard[era][mind] = grade_mind(lab[emask], mmask[emask], market)

    # ---- disagreement mining at the 12m horizon
    nm = pd.read_parquet(BULK / "crsp__stocknames.parquet",
                         columns=["permno", "nameenddt", "ticker", "comnam"]).sort_values("nameenddt")
    tick = {int(r.permno): str(r.ticker) for r in nm.itertuples() if pd.notna(r.ticker)}

    def examples(mask: pd.Series, n: int = 5) -> dict:
        sub = lab[mask & lab["fwd_12m"].notna()]
        cols = ["symbol", "month", "upside", "consensus", "fwd_12m"]
        pick = lambda d: [{**{c: (round(float(r[c]), 3) if isinstance(r[c], float) else r[c])
                              for c in cols}, "ticker": tick.get(int(r["symbol"]), "?")}
                          for _, r in d[cols].iterrows()]
        return {"n": int(len(sub)),
                "mean_fwd_12m": round(float(sub["fwd_12m"].mean()), 4) if len(sub) else None,
                "median_fwd_12m": round(float(sub["fwd_12m"].median()), 4) if len(sub) else None,
                "best": pick(sub.nlargest(n, "fwd_12m")),
                "worst": pick(sub.nsmallest(n, "fwd_12m"))}

    disagreement = {
        "AEGIS_avoids_STREET_buys": examples(aegis_avoid & street_buy),
        "AEGIS_buys_STREET_sells": examples(aegis_buy & street_sell),
        "both_buy": examples(aegis_buy & street_buy),
        "note": ("every 'best' row in AEGIS_avoids_STREET_buys is research material: what did "
                 "the street see that the band prior priced away? -- and every 'worst' row in "
                 "AEGIS_buys_STREET_sells is the mirror question."),
    }

    keep = ["symbol", "month", "era", "close", "upside", "consensus", "coverage",
            "ret_12m", "skill_implied", "fwd_1m", "fwd_3m", "fwd_6m", "fwd_12m"]
    lab[keep].to_parquet(OUT_ROWS)

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "PRODUCT_EXPERIMENT",
        "window": f"{start}-{end}",
        "tracker_sha256": tracker_sha,
        "eras": {k: list(v) for k, v in ERAS.items()},
        "anachronism_note": ("AEGIS band thresholds were chosen from receipts measured on this "
                             "panel; this arena DECOMPOSES where they win/lose vs the street, "
                             "it does not prove them out-of-sample. SKILL STREET and every "
                             "other mind are fully PIT."),
        "scoreboard": scoreboard,
        "disagreement_12m": disagreement,
        "row_level_parquet_local_only": str(OUT_ROWS),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--start", type=int, default=2015)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--lag-days", type=int, default=3)
    args = ap.parse_args()
    if not args.run:
        print(__doc__)
        return 0
    report = run(args.start, args.end, args.lag_days)
    OUT_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    OUT_RECEIPT.write_text(json.dumps(report, indent=2))
    print(f"\nreceipt: {OUT_RECEIPT}")
    for era, minds in report["scoreboard"].items():
        print(f"\n== {era} (12m horizon, ann. excess vs market | t_no-overlap) ==")
        for mind, g in minds.items():
            if isinstance(g, str):
                print(f"  {mind:30s} {g}")
                continue
            c = g.get("12m")
            if c:
                print(f"  {mind:30s} {c['annualised_excess']:+8.2%}  t {c['t_nonoverlapping']}"
                      f"  ({g['avg_names_per_month']} names/mo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
