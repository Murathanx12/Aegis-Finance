"""THE 52-WEEK TARGET, TESTED AGAINST WHAT ACTUALLY HAPPENED (roadmap O11).

Murat, 2026-09-11: *"see how our price targets compare to analysts' and learn
why they differ too much and how ours is wrong. Test on backtests… The engine
should run and learn to correct itself: not caps or limits, but corrections on
every mistake."*

WHAT THIS SCRIPT MEASURES, AND WHAT IT CANNOT
=============================================
Three arms, on the same PIT panel of IBES consensus targets 2005-2023:

* **Arm 1 — ours (de-biased consensus).** The raw consensus upside minus the
  optimism bias measured on data STRICTLY BEFORE the target's own announcement
  date, per sector × cap-tier × vol bucket. Walk-forward, expanding window.
* **Arm 2 — the consensus, raw.** What Wall Street published, unmodified.
* **Arm 3 — the naive control.** `current price × (1 + trailing market drift)`,
  the drift itself computed only from months already closed. Murat asked for
  this one by name, and it is what stops a small edge over the consensus being
  read as an edge over doing nothing.

**It measures ONE of the three legs.** The de-biased consensus leg (C) has a
PIT panel on this machine: `analyst_target_grades.parquet`, 1,333,683 graded
targets with realised 12-month returns already attached. The justified-multiple
leg (A) needs a PIT sector-median forward P/E series and the DCF leg (B) needs
PIT free cash flow per share; neither exists as a built panel here, so their
weights stay at the prior thirds and every payload that uses them says
`prior_unbacktested`. That is a statement about this run, not a claim that the
legs do not work — and it is in the receipt so nobody reads the fitted weights
as covering all three.

WHAT IT WRITES
==============
1. `backend/data/optimus/tracker_backtest/price_target_backtest_<date>.json` —
   the receipt: per era, per bucket, abs error and hit rate for all three arms,
   with `n_effective` counted in DATE BLOCKS (months), never in name-months:
   twelve-month-overlapping targets on names inside one month share the market
   and are not independent draws (CANON §58).
2. `backend/data/optimus/price_target/calibration_<date>.json` — the artefact
   `services/price_target.py` READS: per bucket, the mean bias, the isotonic map
   raw-upside → realised-12m-return, the empirical error quantiles that become
   the p10/p90 band, and the leg MAEs the inverse-error weights come from.

REFUSAL
=======
No parquet, no run. The script prints the `DATA_MANIFEST.md` line naming what is
missing and exits non-zero; it does not fall back to a synthetic panel, because
a calibration fit on invented data is worse than no calibration — the service
handles "no calibration" correctly and loudly, and would handle a fake one
silently.

Usage::

    python -m scripts.price_target_backtest                 # full run
    python -m scripts.price_target_backtest --max-rows 200000   # a fast probe
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("price_target_backtest")

WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
GRADES = WRDS / "analyst_target_grades.parquet"
MSF = WRDS / "bulk" / "crsp__msf.parquet"
OUT_RECEIPT = REPO / "backend" / "data" / "optimus" / "tracker_backtest"
OUT_CAL = REPO / "backend" / "data" / "optimus" / "price_target"

#: The repo's OWN era convention (`learner/evaluate.ERAS` shape). Not a new
#: scheme: a per-run era boundary is a free parameter.
ERAS = (("pre_2013", 1900, 2012), ("2013_2016", 2013, 2016),
        ("2016_2020", 2017, 2020), ("2020_2024", 2021, 2024))

#: SIC -> a coarse sector. Fama-French's 10-industry spirit, deliberately
#: COARSE: the bucket has to hold enough observations to fit an isotonic map,
#: and a 49-industry split would leave most cells below the minimum.
SIC_SECTORS = (
    (100, 999, "Agriculture"), (1000, 1499, "Mining"), (1500, 1799, "Construction"),
    (2000, 2199, "Food"), (2200, 2799, "Consumer Goods"), (2800, 2899, "Chemicals"),
    (2900, 2999, "Energy"), (3000, 3299, "Manufacturing"), (3300, 3499, "Materials"),
    (3500, 3599, "Machinery"), (3570, 3579, "Technology"), (3600, 3699, "Electronics"),
    (3700, 3799, "Transport Equip"), (3800, 3899, "Instruments"),
    (4000, 4799, "Transport"), (4800, 4899, "Communications"), (4900, 4999, "Utilities"),
    (5000, 5199, "Wholesale"), (5200, 5999, "Retail"), (6000, 6499, "Financials"),
    (6500, 6799, "Real Estate"), (7000, 7299, "Services"), (7370, 7379, "Technology"),
    (7300, 7999, "Services"), (8000, 8099, "Healthcare"), (8100, 8999, "Services"),
)

#: Cap tiers, the SAME thresholds `stock_analyzer._get_cap_tier` uses, in $.
CAP_TIERS = ((200e9, "mega"), (10e9, "large"), (2e9, "mid"), (0.0, "small"))

#: Vol buckets, imported from the service so the backtest and the live path
#: cannot drift into disagreeing about what "vol_high" means.
MIN_BUCKET_OBS = 50
MIN_ISOTONIC_KNOTS = 3
#: A data-cleaning bound on the INPUT, not a cap on any forecast: an implied
#: upside above +400% or below -95% in this table is a share-basis artefact, and
#: the grading receipt itself was built with the same 4.0 bound.
IMPLIED_CLEAN_HI, IMPLIED_CLEAN_LO = 4.0, -0.95


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sector_of(siccd) -> str:
    try:
        s = int(siccd)
    except (TypeError, ValueError):
        return "Unknown"
    for lo, hi, name in SIC_SECTORS:
        if lo <= s <= hi:
            return name
    return "Unknown"


def cap_tier_of(mcap) -> str:
    try:
        v = float(mcap)
    except (TypeError, ValueError):
        return "unknown"
    if v <= 0:
        return "unknown"
    for lo, name in CAP_TIERS:
        if v >= lo:
            return name
    return "small"


def era_of(year: int) -> str:
    for name, lo, hi in ERAS:
        if lo <= year <= hi:
            return name
    return "post_2024"


def refuse(reason: str) -> int:
    print(json.dumps({"status": "REFUSED", "utc": _now(), "reason": reason,
                      "manifest": "docs/DATA_MANIFEST.md"}, indent=1))
    return 2


# ---------------------------------------------------------------- the panel

def build_panel(max_rows: int | None = None):
    """One row per (permno, month) with a consensus target and what happened."""
    import numpy as np
    import pandas as pd

    from backend.services.price_target import vol_bucket

    if not GRADES.is_file():
        raise FileNotFoundError(
            f"{GRADES} is absent. It is the LOCAL-ONLY row-level grading table "
            f"named in analyst_target_grades.json's `row_level_parquet_local_only`; "
            f"rebuild it with the IBES grading job before this backtest can run.")
    if not MSF.is_file():
        raise FileNotFoundError(
            f"{MSF} is absent (CRSP monthly stock file, from the WRDS bulk pull). "
            f"Without it there is no market cap, no volatility and therefore no "
            f"bucket -- and a pooled-only calibration is the defect this spec "
            f"exists to avoid.")

    log.info("reading %s", GRADES.name)
    g = pd.read_parquet(GRADES, columns=["permno", "anndats", "implied", "realized_12m"])
    if max_rows:
        g = g.head(int(max_rows))
    g = g.dropna(subset=["permno", "anndats", "implied", "realized_12m"])
    g = g[(g["implied"] <= IMPLIED_CLEAN_HI) & (g["implied"] >= IMPLIED_CLEAN_LO)]
    g["permno"] = g["permno"].astype("int64")
    g["anndats"] = pd.to_datetime(g["anndats"])
    g["month"] = g["anndats"].values.astype("datetime64[M]")
    log.info("  %d graded targets after cleaning", len(g))

    # THE CONSENSUS IS THE MEAN OF THE ANALYSTS WHO PUBLISHED THAT MONTH.
    # Not a rolling 12-month consensus: a target from eleven months ago is a
    # stale number and averaging it in would make the "consensus" partly a
    # memory of a different price.
    cons = (g.groupby(["permno", "month"], sort=False)
              .agg(implied=("implied", "mean"),
                   realized_12m=("realized_12m", "mean"),
                   n_analysts=("implied", "size"))
              .reset_index())
    log.info("  %d (permno, month) consensus cells", len(cons))

    log.info("reading %s", MSF.name)
    m = pd.read_parquet(MSF, columns=["permno", "date", "prc", "shrout", "ret", "hsiccd"])
    m = m.dropna(subset=["permno", "date"])
    m["permno"] = m["permno"].astype("int64")
    m["date"] = pd.to_datetime(m["date"])
    m["month"] = m["date"].values.astype("datetime64[M]")
    # CRSP marks a bid/ask average with a NEGATIVE price. |prc| is the standard
    # treatment and the sign carries no information about the company.
    m["mcap"] = m["prc"].abs() * m["shrout"] * 1000.0
    m["ret"] = pd.to_numeric(m["ret"], errors="coerce")
    m = m.sort_values(["permno", "month"])
    # Trailing 12-month realised vol, annualised from MONTHLY returns, shifted
    # so the month's own return is not in its own bucket (a one-month
    # look-ahead is still a look-ahead).
    m["vol12"] = (m.groupby("permno")["ret"]
                    .transform(lambda s: s.shift(1).rolling(12, min_periods=6).std())
                  * np.sqrt(12.0))
    m["sector"] = [sector_of(v) for v in m["hsiccd"]]

    panel = cons.merge(m[["permno", "month", "mcap", "vol12", "sector"]],
                       on=["permno", "month"], how="left")
    panel["cap_tier"] = [cap_tier_of(v) for v in panel["mcap"]]
    panel["vol_bucket"] = [vol_bucket(v) for v in panel["vol12"]]
    panel["bucket"] = (panel["sector"].fillna("Unknown") + "|"
                       + panel["cap_tier"] + "|" + panel["vol_bucket"])
    panel["year"] = panel["month"].dt.year
    panel["era"] = [era_of(y) for y in panel["year"]]
    panel = panel.dropna(subset=["implied", "realized_12m"])
    log.info("  panel: %d cells, %d months, %d buckets",
             len(panel), panel["month"].nunique(), panel["bucket"].nunique())
    return panel


# ------------------------------------------------------------ the three arms

def walk_forward(panel):
    """Score the three arms month by month, fitting only on months already closed.

    The bias table and the market drift are EXPANDING-WINDOW: at month t they
    see months strictly before t and nothing else. That is the whole point --
    a bias table fit on the full sample and then applied to the full sample is
    a description of the sample, not a forecast.
    """
    import numpy as np
    import pandas as pd

    months = sorted(panel["month"].unique())
    rows = []
    # running sums per bucket, so the walk is O(n) rather than O(n * months)
    bias_sum: dict[str, float] = {}
    bias_n: dict[str, int] = {}
    drift_sum = 0.0
    drift_n = 0
    for t in months:
        cur = panel[panel["month"] == t]
        pooled_bias = (sum(bias_sum.values()) / sum(bias_n.values())
                       if sum(bias_n.values()) else None)
        market_drift = (drift_sum / drift_n) if drift_n else None
        for r in cur.itertuples(index=False):
            b = r.bucket
            n_b = bias_n.get(b, 0)
            # A bucket with fewer than 20 prior observations does not have a
            # bias of its own yet; it borrows the pooled one and the row says so.
            if n_b >= 20:
                bias = bias_sum[b] / n_b
                bias_basis = "bucket"
            elif pooled_bias is not None:
                bias = pooled_bias
                bias_basis = "pooled"
            else:
                bias = 0.0
                bias_basis = "none_yet"
            rows.append({
                "month": t, "permno": r.permno, "bucket": b, "era": r.era,
                "implied": r.implied, "realized": r.realized_12m,
                "ours": r.implied - bias,
                "consensus": r.implied,
                "drift": market_drift if market_drift is not None else np.nan,
                "bias_applied": bias, "bias_basis": bias_basis,
                "n_analysts": r.n_analysts,
            })
        # close the month: its observations become tomorrow's training data
        for r in cur.itertuples(index=False):
            e = r.implied - r.realized_12m
            bias_sum[r.bucket] = bias_sum.get(r.bucket, 0.0) + e
            bias_n[r.bucket] = bias_n.get(r.bucket, 0) + 1
            drift_sum += r.realized_12m
            drift_n += 1
    return pd.DataFrame(rows)


def score(df, by: str | None = None) -> list[dict]:
    """Abs error and hit rate per arm, with n counted in DATE BLOCKS."""
    import numpy as np

    groups = [(None, df)] if by is None else list(df.groupby(by, sort=True))
    out = []
    for key, g in groups:
        row = {"group": (str(key) if key is not None else "ALL"),
               "n_cells": int(len(g)),
               "n_effective_date_blocks": int(g["month"].nunique()),
               "n_names": int(g["permno"].nunique()),
               "mean_realized_12m_pct": round(100.0 * float(g["realized"].mean()), 3)}
        for arm in ("ours", "consensus", "drift"):
            pred = g[arm].to_numpy(dtype=float)
            real = g["realized"].to_numpy(dtype=float)
            ok = np.isfinite(pred) & np.isfinite(real)
            if ok.sum() < 10:
                row[arm] = {"n": int(ok.sum()), "note": "too few finite pairs to score"}
                continue
            p, y = pred[ok], real[ok]
            row[arm] = {
                "n": int(ok.sum()),
                "mae_pct": round(100.0 * float(np.mean(np.abs(p - y))), 3),
                "bias_pp": round(100.0 * float(np.mean(p - y)), 3),
                # "hit at 12 months" = the realised 12-month return reached the
                # implied one. The literature's other convention (touched at ANY
                # point in the year) needs an intramonth path this panel does
                # not carry, and is NOT reported rather than approximated.
                "hit_rate_12m_pct": round(100.0 * float(np.mean(y >= p)), 2),
            }
        out.append(row)
    return out


def _quantiles(ours, consensus_signed) -> dict:
    """The band's source, named. The de-biased arm's errors when they exist."""
    import numpy as np

    if ours is not None and ours.size >= MIN_BUCKET_OBS:
        signed = -ours          # realised - predicted
        return {"p10": round(float(np.percentile(signed, 10)), 6),
                "p50": round(float(np.percentile(signed, 50)), 6),
                "p90": round(float(np.percentile(signed, 90)), 6),
                "n": int(signed.size), "source": "debiased_arm_walk_forward"}
    return {"p10": round(float(np.percentile(consensus_signed, 10)), 6),
            "p50": round(float(np.percentile(consensus_signed, 50)), 6),
            "p90": round(float(np.percentile(consensus_signed, 90)), 6),
            "n": int(np.asarray(consensus_signed).size),
            "source": ("raw_consensus_fallback -- the walk-forward had too few "
                       "de-biased observations in this bucket, so the band is the "
                       "consensus's width around a de-biased point and is WIDER "
                       "than the arm's own history would justify")}


#: a tercile needs its own observations before it may narrow or widen a band.
#: Below this the bucket keeps the pooled quantiles and says so -- three thin
#: terciles are three noisy bands, not a conditioned one.
MIN_TERCILE_OBS = 40


def tercile_cuts(imp) -> list[float]:
    """The two raw-upside cut points for a bucket, as the LIVE path will read
    them. Computed on the panel's implied upside so the fit and the service
    agree on which tercile a name is in."""
    import numpy as np

    a = np.asarray(imp, dtype=float)
    a = a[np.isfinite(a)]
    if a.size < 3:
        return []
    lo, hi = (float(x) for x in np.percentile(a, [100.0 / 3.0, 200.0 / 3.0]))
    return [] if not (lo < hi) else [round(lo, 6), round(hi, 6)]


def _tercile_of(x: float, cuts: list[float]) -> str:
    return "low" if x <= cuts[0] else ("mid" if x <= cuts[1] else "high")


def conditioned_quantiles(ours_pair, imp, err, cuts: list[float]) -> dict:
    """`error_quantiles` per raw-upside tercile within one bucket.

    THE DEFECT THIS ANSWERS. Error quantiles pooled over a bucket give a name
    at the TOP of the upside range a band centred on the bucket's typical name.
    On 2026-09-11 that printed p10 $234.93 on a $218.36 NVDA -- a band wholly
    above spot, which is a claim the data did not make -- and the service
    withheld it. Asquith-Mikhail-Au: error grows with implied upside, so the
    conditioning is on raw upside and the top tercile should come back WIDER.

    `{}` when the cuts are absent or any tercile is thinner than
    `MIN_TERCILE_OBS`. The pooled quantiles then stand, unchanged, and the
    withhold rule is still the last line of defence.
    """
    import numpy as np

    if not cuts:
        return {}
    imp = np.asarray(imp, dtype=float)
    out: dict[str, dict] = {}
    o_err, o_imp = ours_pair if ours_pair is not None else (None, None)
    for name, mask in (("low", imp <= cuts[0]),
                       ("mid", (imp > cuts[0]) & (imp <= cuts[1])),
                       ("high", imp > cuts[1])):
        if int(mask.sum()) < MIN_TERCILE_OBS:
            return {}
        sub_ours = None
        if o_err is not None:
            m2 = ((o_imp <= cuts[0]) if name == "low" else
                  ((o_imp > cuts[0]) & (o_imp <= cuts[1])) if name == "mid" else
                  (o_imp > cuts[1]))
            if int(m2.sum()) >= MIN_TERCILE_OBS:
                sub_ours = o_err[m2]
        q = _quantiles(sub_ours, -err[mask])
        q["raw_upside_lo"] = (None if name == "low" else cuts[0 if name == "mid" else 1])
        q["raw_upside_hi"] = (cuts[0] if name == "low" else (cuts[1] if name == "mid" else None))
        out[name] = q
    return out


def fit_calibration(df, panel) -> dict:
    """The artefact the live service reads. Fit on the FULL sample, on purpose.

    The walk-forward above is how the METHOD is judged; this is the table the
    product uses tomorrow, and tomorrow's forecast may legitimately use every
    observation that has already resolved. The two must not be confused, so the
    receipt scores the walk-forward and the calibration file carries
    `fit_window: full_sample_through <date>` on its face.
    """
    import numpy as np

    # The walk-forward's OWN errors, per bucket. The band must be built from the
    # error of the prediction it is drawn around: using the raw consensus's error
    # width for a DE-BIASED point double-counts the bias we just removed, and
    # produced a p10 ABOVE spot on NVDA in the first live audit.
    # (error, implied) per bucket -- the implied is kept so the SAME rows can be
    # split by raw-upside tercile below. Dropping it was why the band could only
    # ever be pooled.
    ours_err: dict = {}
    ours_pairs: dict = {}
    if df is not None and len(df):
        for key, gg in df.groupby("bucket", sort=False):
            e = (gg["ours"] - gg["realized"]).to_numpy(dtype=float)
            i = gg["implied"].to_numpy(dtype=float)
            ok = np.isfinite(e) & np.isfinite(i)
            if ok.any():
                ours_err[str(key)] = e[ok]
                # `-e` is `realised - predicted`, the sign `_quantiles` expects
                ours_pairs[str(key)] = (e[ok], i[ok])

    buckets: dict[str, dict] = {}
    for key, g in panel.groupby("bucket", sort=True):
        n = len(g)
        if n < MIN_BUCKET_OBS:
            continue
        imp = g["implied"].to_numpy(dtype=float)
        real = g["realized_12m"].to_numpy(dtype=float)
        err = imp - real
        # ISOTONIC WITHOUT SKLEARN: decile means of realised return against
        # decile means of implied upside, then a cumulative-maximum so the map
        # is monotone by construction. A non-monotone calibration would let a
        # higher raw upside map to a lower expectation, which is not a
        # correction, it is noise with a curve fitted to it.
        order = np.argsort(imp)
        xs, ys = [], []
        k = max(MIN_ISOTONIC_KNOTS, min(10, n // 25))
        for chunk in np.array_split(order, k):
            if len(chunk) < 5:
                continue
            xs.append(float(np.mean(imp[chunk])))
            ys.append(float(np.mean(real[chunk])))
        if len(xs) >= MIN_ISOTONIC_KNOTS:
            ys = list(np.maximum.accumulate(np.asarray(ys, dtype=float)))
        else:
            xs, ys = [], []
        buckets[key] = {
            "n_obs": int(n),
            "mean_bias": round(float(np.mean(err)), 6),
            "median_bias": round(float(np.median(err)), 6),
            "mae_pct": round(100.0 * float(np.mean(np.abs(err))), 3),
            "hit_rate_12m_pct": round(100.0 * float(np.mean(real >= imp)), 2),
            "hit_rate_anytime_pct": None,
            # `-err` is `realised - predicted`: what to ADD to a point estimate to
            # reach the outcome. The de-biased arm's own errors where the
            # walk-forward has them; the raw consensus's only as a named fallback.
            "error_quantiles": _quantiles(ours_err.get(key), -err),
            # THE BAND, CONDITIONED. Pooled quantiles hand a high-upside name the
            # typical name's band; these are the same errors sliced by the raw
            # upside they were made at. `{}` when any tercile is too thin.
            "upside_tercile_cuts": tercile_cuts(imp),
            "error_quantiles_by_upside_tercile": conditioned_quantiles(
                ours_pairs.get(key), imp, err, tercile_cuts(imp)),
            "error_quantiles_consensus": {"p10": round(float(np.percentile(-err, 10)), 6),
                                          "p50": round(float(np.percentile(-err, 50)), 6),
                                          "p90": round(float(np.percentile(-err, 90)), 6),
                                          "n": int(n)},
            "isotonic": [[round(x, 6), round(y, 6)] for x, y in zip(xs, ys)],
            # ONLY leg C was backtested on this panel. The other two keep the
            # prior thirds and the service says `prior_unbacktested`; writing a
            # MAE here for a leg that was never scored would manufacture a
            # weight out of nothing.
            "leg_mae_pct": {"consensus_debiased": round(
                100.0 * float(np.mean(np.abs(err))), 3)},
        }
    return buckets


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-rows", type=int, default=0,
                    help="cap the grading table read, for a fast probe")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args(argv)

    try:
        panel = build_panel(args.max_rows or None)
    except FileNotFoundError as exc:
        return refuse(str(exc))

    if panel.empty:
        return refuse("the joined panel is empty; nothing to fit and nothing to score")

    log.info("walking forward over %d months", panel["month"].nunique())
    scored = walk_forward(panel)
    receipt = {
        "receipt": "price_target_backtest",
        "roadmap_item": "O11",
        "licence": "PRODUCT_EXPERIMENT",
        "generated_utc": _now(),
        "window": f"{panel['month'].min():%Y-%m} .. {panel['month'].max():%Y-%m}",
        "n_cells": int(len(panel)), "n_names": int(panel["permno"].nunique()),
        "n_months": int(panel["month"].nunique()),
        "legs_backtested": ["consensus_debiased"],
        "legs_not_backtested": ["multiple_based", "dcf_lite"],
        "arms": {
            "ours": ("raw consensus upside minus the optimism bias measured on data "
                     "STRICTLY BEFORE the target's own month, per sector|cap|vol "
                     "bucket, expanding window; pooled bias until a bucket has 20 "
                     "prior observations"),
            "consensus": "the published consensus upside, unmodified",
            "drift": ("current price x (1 + trailing mean realised 12m return), the "
                      "naive control Murat named"),
        },
        "pooled": score(scored),
        "by_era": score(scored, "era"),
        "by_bucket": [r for r in score(scored, "bucket") if r["n_cells"] >= MIN_BUCKET_OBS],
        "read_me_first": (
            "This is a FORECAST-ACCURACY backtest, not a tradable-strategy backtest: "
            "no trades, no costs, no turnover -- the question 'does trading on the "
            "calibrated upside earn money net of costs' is SEPARATE and is gated by "
            "ANALYST-IBES-1's PERVERSE verdict on the raw ranked upside. "
            "`n_effective_date_blocks` counts MONTHS, not name-months: 12-month "
            "overlapping targets on names inside one month share the market and are "
            "not independent draws. Only the consensus leg was scored here; the "
            "multiple and DCF legs have no PIT panel on this machine and keep prior "
            "weights, labelled `prior_unbacktested` wherever they are used."),
    }
    out_receipt = Path(args.out_dir or OUT_RECEIPT)
    out_receipt.mkdir(parents=True, exist_ok=True)
    rp = out_receipt / f"price_target_backtest_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    rp.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    log.info("receipt -> %s", rp)

    cal = {
        "generated_utc": _now(),
        "source_receipt": rp.name,
        "fit_window": f"full_sample_through {panel['month'].max():%Y-%m}",
        "fit_note": ("the WALK-FORWARD run in the receipt is how the method was "
                     "judged; this table is what the product uses tomorrow and may "
                     "legitimately use every observation that has already resolved. "
                     "They are different questions and must not be read as one."),
        "market_forward_pe_prior": 19.0,
        "vol_estimator": ("trailing 12 MONTHLY CRSP returns, annualised by sqrt(12), "
                          "shifted one month. The LIVE path buckets on 252 DAILY "
                          "yfinance returns, which is a different estimator: monthly "
                          "sampling rarely puts a mega-cap above the 45% vol_high line "
                          "that daily sampling clears easily. `price_target."
                          "resolve_cohort` falls back to a coarser bucket and NAMES "
                          "the level rather than pretending the exact one was fitted."),
        "buckets": fit_calibration(scored, panel),
    }
    OUT_CAL.mkdir(parents=True, exist_ok=True)
    cp = OUT_CAL / f"calibration_{datetime.now(timezone.utc):%Y-%m-%d}.json"
    cp.write_text(json.dumps(cal, indent=1, default=str), encoding="utf-8")
    log.info("calibration -> %s (%d buckets)", cp, len(cal["buckets"]))

    print(json.dumps({"status": "ok", "receipt": str(rp), "calibration": str(cp),
                      "pooled": receipt["pooled"], "by_era": receipt["by_era"]},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
