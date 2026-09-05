"""BEHAVIOURAL PRICE-SHAPE FEATURES -- the ones a human actually looks at.

WHAT THIS ADDS THAT THE PANEL DOES NOT ALREADY HAVE
===================================================
`learner/dataset.py` already carries momentum, 60-day drawdown, two realised
vols and a 20-day dollar volume. Those are RISK and TREND. What is missing is
the family of features that are about where a price sits relative to a
REFERENCE POINT a human would name out loud -- the 52-week high, the price they
bought at, "unusual volume today". They are behavioural because their content is
not the number itself but the fact that market participants anchor on it:

* **52-week-high proximity** (George & Hwang 2004). `adj_prc / max(adj_prc, 252d)`.
  The claim is that a name close to its own annual high underreacts, because
  holders anchor on the high as a ceiling and sellers hesitate below it. It is
  NOT momentum: the two disagree exactly on the names that ran up and then
  gave it back, which is the population the feature exists to separate.
* **52-week-low proximity.** The mirror. Reported separately rather than as a
  single 0-1 position within the range, because the two halves of that range
  behave differently and averaging them into one number would hide it.
* **VWAP anchor.** `adj_prc / VWAP(60d) - 1`, the dollar-volume-weighted average
  price of the last 60 sessions. This approximates the average holder's entry
  price, which is the reference point the disposition effect runs on.
* **Attention.** The z-score of today's DOLLAR volume against its own trailing
  60-session distribution. "Unusual volume" as the market itself measures it.
* **Amihud illiquidity.** `mean(|ret| / dollar_vol)` over 21 sessions -- price
  impact per dollar traded. Not behavioural, but it is the control every
  behavioural claim in this universe needs, because the names where anchoring is
  strongest are also the names nobody can trade.
* **Short-run reversal.** The 5-session return, which is the thing every one of
  the above is most likely to be a disguise for.

DOLLAR VOLUME, AND WHY THE ATTENTION FEATURE IS NOT BUILT ON SHARES
===================================================================
CRSP `vol` is a SHARE count on the raw share basis, so a 2:1 split doubles it
overnight and a z-score whose 60-day window straddles the split reads a routine
session as a 6-sigma attention event. The panel loads `cfacpr` but not
`cfacshr`, so adjusting shares would mean either a second assumption or a second
pull. **Dollar volume (`prc * vol`) is split-invariant by construction** -- the
price halves exactly as the share count doubles -- so building attention on
dollars removes the problem instead of correcting for it. This is the same
lesson as `reference_farm_split_adjustment`, reached from the other side.

Everything price-shaped runs on `adj_prc = prc / cfacpr`, never raw, for the
reason that file records: on raw prices a 1-for-10 reverse split reads as +900%
and a 2-for-1 as -50%, the upside is unbounded and the downside floors at -100%,
so the asymmetry biases every cross-sectional mean upward.

POINT-IN-TIME
=============
Every column at date `t` uses bars dated `t` and earlier, and nothing else. The
join onto the training panel is a BACKWARD `merge_asof` on `entry_date` -- the
date the money moved -- with a 7-session tolerance, so a name with no recent bar
gets NaN and never a stale value carried forward from a month ago.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "backend" / "data" / "optimus" / "learner"
PRICE_FEATURES = OUT_DIR / "features_price.parquet"
PRICE_RECEIPT = OUT_DIR / "features_price_receipt.json"

VERSION = "features-price-1"

#: The columns this module produces, and the family each belongs to. The family
#: is what an ablation removes -- one behavioural idea at a time, never one
#: column at a time, because two columns of the same idea protect each other.
FAMILIES: dict[str, tuple[str, ...]] = {
    "anchor_high_low": ("prox_52w_high", "prox_52w_low"),
    "anchor_vwap": ("vwap_60d_gap",),
    "attention": ("attention_z", "attention_z_5d"),
    "liquidity_impact": ("amihud_21d",),
    "short_reversal": ("ret_5d",),
}

FEATURES: tuple[str, ...] = tuple(c for cols in FAMILIES.values() for c in cols)


def family_of(col: str) -> str | None:
    for fam, cols in FAMILIES.items():
        if col in cols:
            return fam
    return None


# ------------------------------------------------------------------- build

def build(start: int = 1998, end: int = 2024, verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """One row per (permno, date) with the behavioural columns. 1998 is read so
    a panel that starts in 1999 has a full 252-session lookback on day one."""
    from scripts import tracker_ibes_backtest as tib
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    frames = []
    for year in range(start, end + 1):
        f = tib.WRDS / f"crsp_dsf_{year}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f, columns=["permno", "date", "prc", "ret",
                                                      "cfacpr", "vol"]))
    if not frames:
        raise SystemExit("REFUSED: no CRSP daily files in that range.")
    px = pd.concat(frames, ignore_index=True)
    del frames
    px["date"] = pd.to_datetime(px["date"])
    # A NEGATIVE prc is CRSP's bid/ask-mean flag: take abs and KEEP the row --
    # dropping it deletes exactly the illiquid names anchoring is loudest in.
    px["prc"] = px["prc"].abs()
    px = px[px["prc"].notna() & (px["prc"] > 0)]
    px["ret"] = pd.to_numeric(px["ret"], errors="coerce")
    cf = px["cfacpr"].where(px["cfacpr"].notna() & (px["cfacpr"] != 0), 1.0)
    px["adj_prc"] = px["prc"] / cf
    # SPLIT-INVARIANT BY CONSTRUCTION: price halves as share count doubles.
    px["dollar_vol"] = px["prc"] * px["vol"].fillna(0.0)
    px = px.sort_values(["permno", "date"]).reset_index(drop=True)
    log(f"  daily rows {len(px):,}, permnos {px['permno'].nunique():,}")

    g = px.groupby("permno", sort=False)

    hi252 = g["adj_prc"].transform(lambda s: s.rolling(252, min_periods=120).max())
    lo252 = g["adj_prc"].transform(lambda s: s.rolling(252, min_periods=120).min())
    px["prox_52w_high"] = px["adj_prc"] / hi252
    px["prox_52w_low"] = px["adj_prc"] / lo252 - 1.0

    # VWAP over 60 sessions, ON THE ADJUSTED BASIS, with no second data pull.
    #
    # The obvious construction -- sum(prc * vol) / sum(vol), then divide by
    # today's cfacpr -- is WRONG across a split: the numerator mixes pre- and
    # post-split prices and the denominator mixes pre- and post-split share
    # counts, and dividing the result by TODAY's factor rescales the whole
    # window by a factor that was only correct for part of it. Adjusting the
    # share leg properly would need `cfacshr`, which the panel does not load.
    #
    # It does not have to. Adjusted share volume is derivable from what is
    # already here:  dollar_vol / adj_prc  =  (prc * vol) / (prc / cfacpr)
    #                                      =  vol * cfacpr,
    # which is the share count on the adjusted basis. So
    # sum(dollar_vol) / sum(dollar_vol / adj_prc) is a dollar-weighted average
    # of `adj_prc` itself -- split-consistent by construction, one basis on both
    # legs, and comparable to `adj_prc` without any rescaling at all.
    px["_adjshr"] = px["dollar_vol"] / px["adj_prc"].where(px["adj_prc"] > 0)
    dv60 = g["dollar_vol"].transform(lambda s: s.rolling(60, min_periods=20).sum())
    as60 = px.groupby("permno", sort=False)["_adjshr"].transform(
        lambda s: s.rolling(60, min_periods=20).sum())
    vwap_adj = dv60 / as60.where(as60 > 0)
    px["vwap_60d_gap"] = px["adj_prc"] / vwap_adj - 1.0

    # Attention: today's dollar volume against its own trailing distribution.
    # The window EXCLUDES today (shift(1)) -- a z-score whose own denominator
    # contains the observation is smaller exactly when the event is largest.
    ldv = np.log1p(px["dollar_vol"])
    px["_ldv"] = ldv
    prev = g["_ldv"].shift(1)
    px["_prev"] = prev
    mu = px.groupby("permno", sort=False)["_prev"].transform(
        lambda s: s.rolling(60, min_periods=20).mean())
    sd = px.groupby("permno", sort=False)["_prev"].transform(
        lambda s: s.rolling(60, min_periods=20).std())
    px["attention_z"] = (ldv - mu) / sd.where(sd > 0)
    px["attention_z_5d"] = px.groupby("permno", sort=False)["attention_z"].transform(
        lambda s: s.rolling(5, min_periods=3).mean())

    # Amihud: |return| per dollar traded, scaled so the number is readable.
    illiq = (px["ret"].abs() / px["dollar_vol"].where(px["dollar_vol"] > 0)) * 1e9
    px["_illiq"] = illiq
    px["amihud_21d"] = px.groupby("permno", sort=False)["_illiq"].transform(
        lambda s: s.rolling(21, min_periods=10).mean())

    lag5 = g["adj_prc"].shift(5)
    px["ret_5d"] = px["adj_prc"] / lag5 - 1.0

    out = px[["permno", "date", *FEATURES]].copy()
    # A feature that is NaN everywhere is a feature that was never built. This
    # is the coverage line the receipt carries, and it is checked rather than
    # assumed -- `silent_fragility` in one number per column.
    cov = {c: round(float(out[c].notna().mean()), 4) for c in FEATURES}
    empty = [c for c, v in cov.items() if v == 0.0]
    if empty:
        raise SystemExit(
            f"REFUSED: {empty} are NaN on every row of {len(out):,}. A column that is "
            "empty everywhere is a column that was never built, and joining it to the "
            "panel would add a feature the model silently ignores.")
    receipt = {
        "version": VERSION,
        "window": f"{start}-{end}",
        "rows": int(len(out)),
        "permnos": int(out["permno"].nunique()),
        "first_date": str(out["date"].min().date()),
        "last_date": str(out["date"].max().date()),
        "families": {k: list(v) for k, v in FAMILIES.items()},
        "non_null_rate": cov,
        "split_note": ("attention is built on DOLLAR volume, which is split-invariant by "
                       "construction; a share-count z-score would read a 2:1 split as a "
                       "6-sigma attention event"),
        "pit_note": ("every column at date t uses bars dated t and earlier; the attention "
                     "window excludes today's own observation"),
        "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    log("  coverage: " + ", ".join(f"{c} {v:.3f}" for c, v in cov.items()))
    return out, receipt


def save(df: pd.DataFrame, receipt: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(PRICE_FEATURES, index=False)
    PRICE_RECEIPT.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")


def load() -> pd.DataFrame:
    if not PRICE_FEATURES.exists():
        raise SystemExit(f"REFUSED: {PRICE_FEATURES} does not exist. Build it: "
                         "python -m learner.features_price --build")
    return pd.read_parquet(PRICE_FEATURES)


def available() -> bool:
    return PRICE_FEATURES.exists()


def attach(panel: pd.DataFrame, feats: pd.DataFrame | None = None,
           tolerance_days: int = 7) -> tuple[pd.DataFrame, dict]:
    """BACKWARD merge_asof onto `entry_date` -- the date the money moved.

    Backward, not nearest: a forward join would hand the panel a bar dated after
    the trade. Tolerance is 7 calendar days, so a name with no recent bar gets
    NaN rather than a value carried forward from a month ago -- and the receipt
    reports the MATCH RATE, because a join that silently matched 3% of rows and
    a join that matched 97% produce the same shaped frame.
    """
    if feats is None:
        feats = load()
    p = panel.copy()
    p["entry_date"] = pd.to_datetime(p["entry_date"])
    f = feats.copy()
    f["date"] = pd.to_datetime(f["date"])
    p = p.sort_values("entry_date")
    f = f.sort_values("date")
    before = len(p)
    p = pd.merge_asof(p, f, left_on="entry_date", right_on="date", by="permno",
                      direction="backward", tolerance=pd.Timedelta(days=tolerance_days),
                      suffixes=("", "_pxfeat"))
    rates = {c: round(float(p[c].notna().mean()), 4) for c in FEATURES}
    note = {
        "rows_in": before, "rows_out": int(len(p)),
        "match_rate": rates,
        "tolerance_days": tolerance_days,
        "direction": "backward (a forward join would use a bar dated after the trade)",
    }
    worst = min(rates.values()) if rates else 0.0
    note["verdict"] = ("JOINED" if worst > 0.5 else
                       f"THIN -- worst column matches {worst:.1%} of rows")
    return p.drop(columns=[c for c in p.columns if c.endswith("_pxfeat")]), note


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="behavioural price-shape features")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--start", type=int, default=1998)
    ap.add_argument("--end", type=int, default=2024)
    a = ap.parse_args(argv)
    if a.build:
        df, rec = build(a.start, a.end)
        save(df, rec)
        print(f"WROTE {PRICE_FEATURES} ({len(df):,} rows)")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
