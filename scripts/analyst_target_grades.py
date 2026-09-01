"""Grade every INDIVIDUAL analyst price target, then ask the only question
that decides whether "analyst skill" is usable: DOES IT PERSIST?

    python -m scripts.analyst_target_grades --run
    python -m scripts.analyst_target_grades --run --start 2005 --end 2023

WHY (Murat + the GPT review, 2026-09-01)
========================================
EXP-RETURN-XS-1 measured that CONSENSUS ratings are noise (+0.62%/yr, t 0.37)
and consensus targets are an anti-signal at the top. The review's correct
objection: that is a fact about the AVERAGE, and `target = information +
bias` -- the literature separates an analyst's informational component from
their bias component. We hold 7.4M individual targets with `amaskcd`, the
identity that follows a person across firms. So before any model uses
"AnalystSkill(analyst)", this script grades every 12-month USD target on a US
firm against what actually happened, and then runs the make-or-break test:

    Rank analysts by bias and by accuracy on the FIRST half of their targets.
    Do the same ranks hold on the SECOND half?

If per-analyst bias persists (it should: optimism is a stable trait in the
literature) the Time-Machine Arena may subtract each analyst's OWN measured
bias from their target, point-in-time. If accuracy does not persist, then
"listen to the analysts who were right" is noise-mining and every downstream
design must know that BEFORE it is built. A receipt that kills a feature is
worth as much as one that ships it.

PIT NOTES
=========
* implied return uses the last close ON OR BEFORE anndats -- the price the
  analyst saw, never a later one.
* realized return is the CRSP total-return index ~252 sessions ahead
  (calendar 350..380d window), delisting return included.
* the permno link is the official WRDS ibcrsphist (ticker, validity dates);
  a name-keyed join would fragment identities (the mgrno lesson).

Licence: PRODUCT_EXPERIMENT. Row-level output is a LOCAL parquet (too big
for git); the receipt carries every headline number.
Receipt: backend/data/optimus/tracker_backtest/analyst_target_grades.json
Rows:    backend/data/optimus/wrds/analyst_target_grades.parquet (local only)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.tracker_ibes_backtest import load_prices

REPO = Path(__file__).resolve().parent.parent
BULK = REPO / "backend" / "data" / "optimus" / "wrds" / "bulk"
OUT_RECEIPT = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "analyst_target_grades.json"
OUT_ROWS = REPO / "backend" / "data" / "optimus" / "wrds" / "analyst_target_grades.parquet"

#: An analyst is gradeable only above this many graded targets; below it a
#: "skill" estimate is an anecdote with a decimal point.
MIN_TARGETS_PER_ANALYST = 20

#: Winsorise implied returns here. A $44 target over a $0.30 close is a data
#: state, not an opinion (the stale-target-across-a-split lesson).
IMPLIED_CAP = 4.0


def load_targets(start: int, end: int) -> pd.DataFrame:
    df = pd.read_parquet(BULK / "ibes__ptgdetu.parquet",
                         columns=["ticker", "anndats", "horizon", "value",
                                  "estcur", "usfirm", "amaskcd", "estimid"])
    df = df[(df["usfirm"] == 1) & (df["horizon"] == "12") & (df["estcur"] == "USD")]
    df = df[df["value"].notna() & (df["value"] > 0) & df["amaskcd"].notna()]
    df["anndats"] = pd.to_datetime(df["anndats"])
    df = df[(df["anndats"].dt.year >= start) & (df["anndats"].dt.year <= end)]

    link = pd.read_parquet(BULK / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet")
    for c in ("sdate", "edate"):
        link[c] = pd.to_datetime(link[c])
    df = df.merge(link[["ticker", "permno", "sdate", "edate"]], on="ticker", how="inner")
    df = df[(df["anndats"] >= df["sdate"]) & (df["anndats"] <= df["edate"])]
    # the link table's permno is nullable Int64; CRSP's is plain int64 --
    # merge_asof refuses mixed key dtypes, so align here, once.
    df["permno"] = df["permno"].astype("int64")
    return df.drop(columns=["sdate", "edate"])


def attach_prices(df: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    px = load_prices(start, end + 2)
    px = px.sort_values(["permno", "date"])
    # total-return index per permno, from CRSP ret (splits/dividends/delist in)
    px["tri"] = (1.0 + px["ret"].fillna(0.0)).groupby(px["permno"]).cumprod()

    df = df.sort_values("anndats")
    # merge_asof needs the RIGHT side sorted on the `on` key globally, not
    # per-permno -- the tri cumprod above left px sorted (permno, date).
    base = pd.merge_asof(df, px[["permno", "date", "prc", "tri"]].sort_values("date"),
                         left_on="anndats", right_on="date", by="permno",
                         direction="backward", tolerance=pd.Timedelta(days=7))
    base = base[base["prc"].notna() & (base["prc"] > 0)]
    base["implied"] = (base["value"] / base["prc"] - 1.0).clip(-0.99, IMPLIED_CAP)

    fwd = px[["permno", "date", "tri"]].rename(columns={"date": "fdate", "tri": "tri_fwd"})
    base["target_date"] = base["anndats"] + pd.Timedelta(days=365)
    base = base.sort_values("target_date")
    base = pd.merge_asof(base, fwd.sort_values("fdate"),
                         left_on="target_date", right_on="fdate", by="permno",
                         direction="backward", tolerance=pd.Timedelta(days=15))
    base = base[base["tri_fwd"].notna() & (base["tri_fwd"] > 0)]
    # A forward mark closer than ~11 months means the name delisted; CRSP's
    # tri already contains the delisting return, so the LAST mark is the
    # honest terminal value -- keep the row.
    base["realized_12m"] = base["tri_fwd"] / base["tri"] - 1.0
    base["error"] = base["implied"] - base["realized_12m"]
    base["year"] = base["anndats"].dt.year
    return base[["amaskcd", "estimid", "permno", "ticker", "anndats", "year",
                 "implied", "realized_12m", "error"]]


def per_analyst(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per analyst per half of their own graded history."""
    rows = rows.sort_values("anndats")
    rows["half"] = rows.groupby("amaskcd").cumcount()
    counts = rows.groupby("amaskcd")["implied"].transform("size")
    rows["half"] = np.where(rows["half"] < counts / 2, 1, 2)
    out = []
    for (a, h), g in rows.groupby(["amaskcd", "half"]):
        if len(g) < MIN_TARGETS_PER_ANALYST / 2:
            continue
        acc = (float(np.corrcoef(g["implied"], g["realized_12m"])[0, 1])
               if g["implied"].std() > 0 and g["realized_12m"].std() > 0 else np.nan)
        out.append({"amaskcd": a, "half": h, "n": len(g),
                    "bias": float(g["error"].mean()),
                    "acc": acc,
                    "mean_implied": float(g["implied"].mean()),
                    "mean_realized": float(g["realized_12m"].mean())})
    return pd.DataFrame(out)


def persistence(halves: pd.DataFrame, col: str) -> dict | None:
    a = halves[halves["half"] == 1].set_index("amaskcd")[col]
    b = halves[halves["half"] == 2].set_index("amaskcd")[col]
    both = pd.concat([a, b], axis=1, keys=["h1", "h2"]).dropna()
    if len(both) < 100:
        return None
    rho = float(both["h1"].rank().corr(both["h2"].rank()))
    # decile table: rank on half 1, measure half 2
    both["dec"] = pd.qcut(both["h1"], 10, labels=False, duplicates="drop")
    dec = both.groupby("dec")["h2"].agg(["mean", "count"])
    return {"n_analysts": int(len(both)),
            "spearman_h1_h2": round(rho, 4),
            "decile_h2_means": {f"d{int(k)+1}": round(float(v), 4)
                                for k, v in dec["mean"].items()},
            "note": f"analysts ranked by {col} on their OWN first half; column is that decile's "
                    f"{col} on the second half"}


def run(start: int, end: int) -> dict:
    df = load_targets(start, end)
    print(f"  individual 12m USD targets on US firms, linked to permno: {len(df):,}")
    rows = attach_prices(df, start, end)
    print(f"  graded (price at anndats + realized 12m): {len(rows):,}")
    OUT_ROWS.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(OUT_ROWS)

    halves = per_analyst(rows)
    pooled = {
        "n_targets_graded": int(len(rows)),
        "n_analysts_total": int(rows["amaskcd"].nunique()),
        "n_analysts_gradeable": int(halves[halves["half"] == 1]["amaskcd"].nunique()),
        "mean_implied": round(float(rows["implied"].mean()), 4),
        "mean_realized_12m": round(float(rows["realized_12m"].mean()), 4),
        "mean_bias": round(float(rows["error"].mean()), 4),
        "median_bias": round(float(rows["error"].median()), 4),
        "pooled_ic_implied_vs_realized": round(float(
            rows[["implied", "realized_12m"]].corr().iloc[0, 1]), 4),
    }
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "PRODUCT_EXPERIMENT",
        "window": f"{start}-{end} (anndats years)",
        "min_targets_per_analyst": MIN_TARGETS_PER_ANALYST,
        "implied_cap": IMPLIED_CAP,
        "pooled": pooled,
        "persistence_bias": persistence(halves, "bias"),
        "persistence_accuracy": persistence(halves, "acc"),
        "row_level_parquet_local_only": str(OUT_ROWS),
        "read_me_first": ("persistence_bias decides whether per-analyst bias correction is "
                          "real; persistence_accuracy decides whether 'listen to the accurate "
                          "analysts' is real. A near-zero spearman kills the corresponding "
                          "design BEFORE it is built."),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--start", type=int, default=2005)
    ap.add_argument("--end", type=int, default=2023)
    args = ap.parse_args()
    if not args.run:
        print(__doc__)
        return 0
    report = run(args.start, args.end)
    OUT_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    OUT_RECEIPT.write_text(json.dumps(report, indent=2))
    print(f"\nreceipt: {OUT_RECEIPT}")
    print(json.dumps({k: report[k] for k in ("pooled", "persistence_bias",
                                             "persistence_accuracy")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
