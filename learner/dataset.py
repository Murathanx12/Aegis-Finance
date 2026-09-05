"""The AEGIS LEARNER's point-in-time training table.

WHAT THIS IS, AND WHAT IT IS NOT
================================
This builds ONE versioned table: one row per (permno, month, vintage), every
feature knowable at that vintage, and forward EXCESS returns at 1/3/6/12 months
that are NULL until they have matured. It is the substrate for
`learner/models.py`; it makes no prediction and expresses no opinion.

IT REUSES THE PANEL THAT ALREADY EXISTS
=======================================
`scripts/tracker_ibes_backtest.py` already joins IBES consensus targets and
recommendation counts to CRSP daily prices for the whole US market 2013-2024 --
~434k name-months, point-in-time, with the IBES 1=strong-buy scale converted to
the tracker's 5=strong-buy scale. Re-deriving that from raw WRDS would create a
second copy that drifts, so `load_names` and `load_prices` are IMPORTED from it
and the extended IBES loader here is pinned against its `load_ibes` by
`assert_ibes_loader_agrees` -- if the two ever select different name-months, the
build REFUSES rather than training on a quiet fork.

ONE SHARE BASIS, AND THE BUG THAT MADE THAT SENTENCE NECESSARY
==============================================================
Until 2026-09-04 this file read **`ibes__ptgsum`** -- IBES's SPLIT-ADJUSTED
consensus, restated in END-OF-SAMPLE share terms -- and divided `meanptg` by the
**raw** CRSP close. Both legs were defensible in isolation; together they are
not a ratio. AAPL at `statpers` 2013-06-20: adjusted target 19.323, unadjusted
541.04, raw close 413.50, `cfacpr` 28.0 (the 7:1 of 2014 times the 4:1 of 2020).
The tape said the ratio was 0.047; it was 1.308.

Because `ratio_used = true_ratio / cfacpr(t)` and `cfacpr` is a FUTURE quantity,
a name that LATER reverse-splits had its ratio inflated and was labelled
`toxic_ge_5`: 74.35% of the original toxic rows carry a future reverse split
against 0.09% of `lt_1_5`, so "toxic" was a future-collapse detector, not an
opinion (`docs/REVIEW_2026-09-04_FABLE51_VERDICTS.md` §2).

The fix is to READ THE UNADJUSTED FILE (`ibes__ptgsumu`), not to rescale: a
verified re-derivation showed `ratio x cfacpr(t)` agrees with the true PIT ratio
on only ~93% of rows, because it multiplies by the same future factor it is
trying to remove. The rescale is kept as `ratio_adj_check` -- a DIAGNOSTIC
column whose disagreement rate is printed and put in the receipt -- and never as
the ratio. `mean_target_adj` keeps the adjusted number under a name that says
what it is, for anything that genuinely wants end-of-sample share terms.

THE UNIT, SAID ONCE MORE
========================
`ratio = mean_target / close`. `upside = ratio - 1`. Both are columns; neither
is called the other. (S33b lost an afternoon to that.) `mean_target` is the
UNADJUSTED consensus and `close` is the raw CRSP close: one basis, the one a
desk saw that morning.

HYGIENE LIVES HERE, NOT IN EACH CALLER
======================================
Four rules that every consumer of this table used to re-implement (or forget):

* `close >= $2` and `coverage >= 2` -- `prior.has_opinion`, imported, ONE
  definition. Below that the band prior is uninformative (t 0.39, S30b) and the
  honest output is "no opinion", never "historically bad".
* `ratio >= RATIO_UNREADABLE_AT` (50) -- not an opinion at all. A consensus
  target at fifty times the price is a stale number, a corporate action, or a
  currency mismatch; it is UNREADABLE.
* the target must not straddle a share-basis change (`split_prior_year`).
* SIC 9900-9999 is `Unclassified` (`tracker_ibes_backtest.SIC_UNCLASSIFIED`),
  never "Public Administration" -- 9999 means CRSP did not classify the name.

`hygiene()` composes the first three into `has_opinion` / `target_readable` /
`hygiene_ok`; where `hygiene_ok` is False the ratio-derived features are NULL
(mirrored in `miss__*`, never zero-filled) and `band` is `no_opinion`.

BAND_PRIOR v2's FOUR CONSTANTS ARE VOID ON THIS PANEL
=====================================================
`prior.BAND_PRIOR_V2` was fitted on the corrupted tape, so `prior_*` and
`resid_*` columns are carried for schema continuity and are NOT expectations
until B1.5 re-derives them. The build receipt says so under `prior_status`.
A verified re-derivation of the corrected `toxic_ge_5` cell (+37.4%/yr t 1.94,
7 names/month) is ALSO not a signal: 84.1% of it trades under $5, a $5 floor
flips the sign to -31.6%/yr, its median monthly excess is -0.86% against a mean
of +2.69%, 2022-24 is +0.7%/yr t 0.03, and 27.6% still carries a future reverse
split. It is a right-tail cell in a thin, cheap corner, not a location shift.

WHY EXCESS AND WHICH MARKET
===========================
The target is EXCESS over the market, because a model trained on raw return
learns the equity risk premium and the market's calendar, then reports it as
skill. Two benchmarks are built and both are stored:

* **value-weighted (PRIMARY)** -- cap-weighted daily index over the same
  CRSP common-stock universe.
* equal-weighted -- stored, never primary. The house lesson is that an EW
  benchmark is a SIZE ARTEFACT: it is a small-cap portfolio wearing a market's
  name, so beating it is partly a statement about size, not about selection.

The band prior itself was measured against the EW market (S33's receipt), so
`prior_*` and `excess_ew_*` are on the same footing and `excess_vw_*` is a
slightly harder bar for the prior. That is stated in the receipt rather than
quietly resolved in favour of whichever flatters the incumbent.

DELISTING IS NOT TRUNCATION
===========================
A name whose CRSP series stops mid-window either (a) delisted, or (b) ran into
the end of the data. They must not be treated alike:

* (a) delisted -> the forward return is computed to the LAST observed total
  return index value, THE DELISTING RETURN IS COMPOUNDED ONTO IT, and the
  proceeds sit in cash for the rest of the horizon. Dropping these rows would
  delete exactly the failures the horizon is meant to measure, which is
  survivorship bias with extra steps.
* (b) truncated by the panel edge -> the target is NULL. Not matured is not a
  zero and it is not a loss.

THE DELISTING RETURN, AND THE CLAIM THIS DOCSTRING USED TO MAKE
--------------------------------------------------------------
`crsp.dsf.ret` is NOT delisting-inclusive, and this file used to say only that
it "carries a delisting return where one is on the daily file", which was too
generous. Measured 2026-09-04: of 1,114 delistings coded 400-591 in 2013-24,
1,103 have a `dsf` bar on `dlstdt` but only **4** carry `ret == dlret`; mean
`dsf.ret` on those bars is -9.2% against mean `dlret` -19.6%. So the daily file
records the last TRADE, not the wind-up.

`tracker_ibes_backtest.delisting_factors()` therefore joins
`crsp__dsedelist.parquet` on (`permno`, `dlstdt`) and returns one
`(1 + dlret)` factor per permno, which `daily_panel` multiplies into the final
index value of every name whose series ends before the panel edge. Where a
PERFORMANCE-coded delisting has no `dlret`, the Shumway (1997) fill is used --
-30% on NYSE/AMEX, -55% on NASDAQ, the constants imported from
`learner.benchmark.SHUMWAY_FILL` so the panel and the benchmark cannot disagree.
Performance-coded means `dlstcd in {500} u [520, 584]` (866 events, mean `dlret`
-24.63%); code 450 (liquidation, 216 events, mean `dlret` -0.74%) is a SEPARATE
category and is NOT Shumway-filled -- folding it in dilutes the mean to -19.57%
and calls a wind-up a collapse. Mergers (200) and exchanges (300) take their own
`dlret` where present and no fill where absent: inventing a number for a merger
would be a fabrication, and the count of un-filled events is in the receipt.

WHAT IS NOT IN HERE
===================
Daily `CompanyState` rows (`aegis-alpha-terminal/state/company_state/*.jsonl`)
carry richer features -- attention_z, EDGAR form counts, realised vol, dollar
volume bands -- but they begin on 2026-08-30. `company_state_schema()` registers
their field names for the future feature store; nothing trains on n=4 days.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import prior as P                                   # noqa: E402
from scripts import tracker_ibes_backtest as tib                 # noqa: E402

OUT_DIR = REPO / "backend" / "data" / "optimus" / "learner"
TRAIN_TABLE = OUT_DIR / "train_table.parquet"
SCHEMA_RECEIPT = OUT_DIR / "train_table_schema.json"

#: v2 (2026-09-04, B1): PIT share basis (`ibes__ptgsumu`), delisting returns
#: compounded from `crsp__dsedelist`, hygiene inside the panel.
SCHEMA_VERSION = "learner-train-table-2"

#: Horizons in MONTHS, and the trading-session count each is approximated by.
HORIZONS: tuple[int, ...] = (1, 3, 6, 12)
HORIZON_SESSIONS: dict[int, int] = {1: 21, 3: 63, 6: 126, 12: 252}

#: A permno whose last observation is within this many sessions of the panel
#: edge was TRUNCATED, not delisted.
PANEL_EDGE_SESSIONS = 5

#: The SPLIT-ADJUSTED IBES summary, read ONLY for the `ratio_adj_check`
#: diagnostic. Held behind a name so the single `BULK / "ibes__ptgsum*"` literal
#: in this file is the PIT one -- `backend/tests/test_ibes_target_share_basis.py`
#: parses this source for the file the loader opens.
_ADJUSTED_PTG_FILE = "ibes__ptgsum.parquet"

#: `ratio_adj_check` and `ratio` are declared to AGREE when they are within this
#: relative tolerance. They cannot agree everywhere -- the check multiplies by a
#: future `cfacpr` -- and the disagreement RATE is the point of the column.
RATIO_CHECK_TOL = 0.01

#: A consensus target at fifty times the price is not an opinion. It is a stale
#: number, an unhandled corporate action, or a currency mismatch. UNREADABLE, so
#: the ratio-derived features are NULL rather than a 1,000,000x "upside".
RATIO_UNREADABLE_AT = 50.0

#: `crsp.dsf` covers this many distinct permnos over 2013-2024 against a full
#: `shrcd in (10, 11)` and `exchcd in (1, 2, 3)` screen of the same window. The
#: pull is a 99.78%-complete SUBSET -- ZERO pulled permnos fall outside the
#: screen -- not a "screened superset" as an earlier note claimed. Below the
#: floor the build REFUSES; between the floor and 100% it records the gap.
UNIVERSE_COVERAGE_FLOOR = 0.99

# --------------------------------------------------------------- the schema

#: Continuous features. Every one is knowable at `vintage` (= the IBES
#: statpers) using only data dated on or before it.
FEATURES_CONTINUOUS: tuple[str, ...] = (
    "ratio", "upside", "log_ratio",
    "consensus", "coverage", "log_coverage", "numest",
    "disagreement", "dispersion",
    "net_rev_4w", "net_rev_1m",
    "target_rev_1m", "target_rev_3m", "consensus_rev_1m", "coverage_rev_1m",
    "ret_1m", "ret_3m", "ret_6m", "ret_12m", "mom_12_1",
    "drawdown_60d", "vol_20d", "vol_60d",
    "log_dollar_vol_20d", "log_market_cap", "log_close",
)

FEATURES_BOOL: tuple[str, ...] = ("split_prior_year",)
FEATURES_CAT: tuple[str, ...] = ("sector", "band")

#: Features that also get a WITHIN-MONTH percentile rank (`<f>__xs`). The
#: cross-section is what a monthly book actually sorts on, and a raw level is
#: not comparable across a decade of drifting price and cap levels.
RANKED: tuple[str, ...] = (
    "ratio", "consensus", "coverage", "numest", "disagreement", "dispersion",
    "net_rev_4w", "target_rev_1m", "consensus_rev_1m",
    "ret_1m", "ret_3m", "ret_6m", "ret_12m", "mom_12_1", "drawdown_60d",
    "vol_20d", "vol_60d", "log_dollar_vol_20d", "log_market_cap", "log_close",
)

#: The subset that `learner/shadow.py` can actually build from a tracker day
#: file. Declared HERE, next to the full list, so the two cannot drift: the
#: shadow trains its own champion on exactly these columns rather than
#: median-imputing a third of the model's inputs at score time and calling the
#: result a prediction.
SHADOW_MAPPABLE: tuple[str, ...] = (
    "ratio", "upside", "log_ratio",
    "consensus", "coverage", "log_coverage", "numest",
    "disagreement",
    "ret_12m", "drawdown_60d", "vol_20d",
    "log_dollar_vol_20d", "log_market_cap", "log_close",
)


def ranked_name(f: str) -> str:
    return f"{f}__xs"


def feature_columns(shadow_only: bool = False) -> list[str]:
    """The model's X columns, in a FIXED order (the schema hash depends on it)."""
    base = list(SHADOW_MAPPABLE) if shadow_only else list(FEATURES_CONTINUOUS)
    cols = list(base)
    cols += [ranked_name(f) for f in RANKED if f in base]
    cols += [f for f in FEATURES_BOOL if not shadow_only]
    cols += [f"{c}_code" for c in FEATURES_CAT
             if (c == "band" or not shadow_only)]
    return cols


def missing_mask_name(f: str) -> str:
    return f"miss__{f}"


def target_columns() -> list[str]:
    out: list[str] = []
    for h in HORIZONS:
        out += [f"fwd_{h}m", f"mkt_vw_{h}m", f"mkt_ew_{h}m",
                f"excess_vw_{h}m", f"excess_ew_{h}m",
                f"prior_{h}m", f"resid_vw_{h}m", f"resid_ew_{h}m",
                f"pos_vw_{h}m", f"mat_date_{h}m"]
    return out


def feature_schema(shadow_only: bool = False) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "prior_version": P.PRIOR_VERSION,
        "row_key": ["permno", "month", "vintage"],
        "features": feature_columns(shadow_only),
        "features_shadow_mappable": list(SHADOW_MAPPABLE),
        "targets": target_columns(),
        "horizons_months": list(HORIZONS),
        "horizon_sessions": {str(k): v for k, v in HORIZON_SESSIONS.items()},
        "primary_benchmark": "value_weighted",
        "unit_note": ("ratio = mean_target / close ; upside = ratio - 1. "
                      "mean_target is the UNADJUSTED IBES consensus (ibes__ptgsumu) "
                      "and close is the raw CRSP close -- ONE share basis. "
                      "mean_target_adj is the split-adjusted number, kept only for "
                      "the ratio_adj_check diagnostic."),
        "hygiene": {
            "min_price": P.MIN_PRICE, "min_coverage": P.MIN_COVERAGE,
            "ratio_unreadable_at": RATIO_UNREADABLE_AT,
            "split_prior_year_is_unreadable": True,
            "columns": ["has_opinion", "target_readable", "hygiene_ok"],
            "on_failure": "ratio/upside/log_ratio NULL, band no_opinion, row kept",
        },
        "delisting": ("crsp__dsedelist.dlret compounded into the final index value; "
                      "Shumway fill (-30% NYSE/AMEX, -55% NASDAQ) for performance "
                      "codes {500} u [520,584] with no dlret. dsf.ret is NOT "
                      "delisting-inclusive."),
        "missing_policy": (
            "NaN is preserved and mirrored in miss__<feature>. fillna(0) is BANNED; "
            "imputation happens inside a model pipeline (median) or not at all (LightGBM)."),
    }


def schema_hash(shadow_only: bool = False) -> str:
    blob = json.dumps(feature_schema(shadow_only), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def company_state_schema() -> dict:
    """REGISTERED, NOT TRAINED ON. The daily CompanyState rows begin 2026-08-30.

    Recorded so the future feature store knows what will exist, and so a later
    session does not rediscover the field list by grepping. n=4 days is not a
    training set and this function trains nothing.
    """
    return {
        "source": r"aegis-alpha-terminal/state/company_state/<day>.jsonl",
        "schema": "company-state-1",
        "first_day": "2026-08-30",
        "status": "REGISTERED_FOR_FUTURE_USE -- not trainable (n days < 30)",
        "fields_beyond_the_ibes_panel": [
            "market_cap_usd", "median_dollar_volume", "dv_bucket", "band", "band_change_12m",
            "expected_round_trip_bps", "target_high", "target_low", "analyst_disagreement",
            "rec_counts", "realised_vol_20d", "days_to_catalyst", "news_articles",
            "news_sources", "attention_z", "attention_is_new", "edgar_filings_6m",
            "edgar_by_form", "p_up_21d", "exp_return", "downside_5pct", "confidence",
            "upside_downside_ratio", "status_by_horizon", "status_blocked_by",
        ],
        "note": (
            "attention_z, edgar_by_form and days_to_catalyst have NO IBES-panel analogue: "
            "they are the features that will make the 2027 learner different from this one."),
    }


# ------------------------------------------------------------------ loaders

def load_ibes_ext(start: int, end: int) -> pd.DataFrame:
    """IBES consensus targets + recommendations, with the DISPERSION and
    REVISION columns `tracker_ibes_backtest.load_ibes` does not return.

    THE FILE IS `ibes__ptgsumu` -- the UNADJUSTED summary. Its `meanptg` is
    quoted in the share terms that existed at `statpers`, which is the basis the
    raw CRSP close is on. The split-ADJUSTED file is read separately, and only
    to build the `ratio_adj_check` diagnostic; it is never the numerator.

    Same filters, same 6 - meanrec conversion. `assert_ibes_loader_agrees`
    proves it selects the same name-months as the script's loader.
    """
    ptg = pd.read_parquet(
        tib.BULK / "ibes__ptgsumu.parquet",
        columns=["cusip", "statpers", "meanptg", "medptg", "stdev", "ptghigh", "ptglow",
                 "numest", "numup4w", "numdown4w", "numup1m", "numdown1m",
                 "usfirm", "measure", "curr"])
    ptg = ptg[(ptg["usfirm"] == 1) & (ptg["measure"] == "PTG")]
    ptg = ptg[ptg["curr"].isin(["USD"]) | ptg["curr"].isna()]
    ptg["statpers"] = pd.to_datetime(ptg["statpers"])
    ptg = ptg[(ptg["statpers"].dt.year >= start) & (ptg["statpers"].dt.year <= end)]

    # The adjusted consensus, under a name that says what it is. Read through
    # `_ADJUSTED_PTG_FILE` so the only `ibes__ptgsum*` LITERAL in this module is
    # the PIT one -- the share-basis test parses this source for it.
    adj = pd.read_parquet(tib.BULK / _ADJUSTED_PTG_FILE,
                          columns=["cusip", "statpers", "meanptg", "usfirm",
                                   "measure", "curr"])
    adj = adj[(adj["usfirm"] == 1) & (adj["measure"] == "PTG")]
    adj = adj[adj["curr"].isin(["USD"]) | adj["curr"].isna()].copy()
    adj["statpers"] = pd.to_datetime(adj["statpers"])
    adj = adj[(adj["statpers"].dt.year >= start) & (adj["statpers"].dt.year <= end)]
    adj = (adj[["cusip", "statpers", "meanptg"]]
           .rename(columns={"meanptg": "meanptg_adj"})
           .drop_duplicates(["cusip", "statpers"]))
    ptg = ptg.merge(adj, on=["cusip", "statpers"], how="left")

    rec = pd.read_parquet(tib.BULK / "ibes__recdsum.parquet",
                          columns=["cusip", "statpers", "meanrec", "numrec", "usfirm"])
    rec = rec[rec["usfirm"] == 1]
    rec["statpers"] = pd.to_datetime(rec["statpers"])
    rec = rec[(rec["statpers"].dt.year >= start) & (rec["statpers"].dt.year <= end)]

    df = ptg.merge(rec, on=["cusip", "statpers"], how="inner", suffixes=("", "_r"))
    df = df[df["meanptg"].notna() & (df["meanptg"] > 0) & df["meanrec"].notna()]
    # THE SCALE CONVERSION. IBES 1 = strong buy; the tracker's scale is
    # 5 = strong buy. Applying a ">= 4.1" bar to raw meanrec would select the
    # most HATED decile and backtest the opposite strategy.
    df["consensus"] = 6.0 - df["meanrec"]
    df["coverage"] = df["numrec"].fillna(0).astype(int)
    return df.reset_index(drop=True)


def hygiene(ratio, close, coverage, split_prior_year) -> pd.DataFrame:
    """The panel's admission rules, in ONE place, as three boolean columns.

    * `has_opinion`   -- `prior.has_opinion`: close >= $2 and coverage >= 2.
      IMPORTED, not re-implemented: a second copy of a floor is a second floor.
    * `target_readable` -- the ratio exists, is positive, is below
      `RATIO_UNREADABLE_AT`, and does not straddle a share-basis change in the
      prior year.
    * `hygiene_ok`    -- both. Where it is False the row STAYS in the panel (it
      is a name that existed, and deleting it is survivorship bias) but its
      ratio-derived features are NULL and its band is `no_opinion`.

    "No opinion" and "a bearish opinion" are different statements and this
    function is the only place the panel makes either of them.
    """
    r = pd.Series(np.asarray(ratio, dtype="float64"))
    op = P.has_opinion(close, coverage)
    op.index = r.index
    sp = pd.Series(np.asarray(split_prior_year, dtype="object"), index=r.index)
    sp = sp.where(sp.notna(), False).astype(bool)
    readable = r.notna() & (r > 0) & (r < RATIO_UNREADABLE_AT) & ~sp
    return pd.DataFrame({"has_opinion": op.astype(bool),
                         "target_readable": readable.astype(bool),
                         "hygiene_ok": (op & readable).astype(bool)}, index=r.index)


def assert_universe_coverage(start: int, end: int, names: pd.DataFrame) -> dict:
    """Does the CRSP daily pull actually cover the screen it claims to?

    An earlier note called the `crsp.dsf` pull a 6,894-permno "screened
    superset". It is not a superset: measured 2026-09-04 over 2013-2024 the pull
    holds 6,894 distinct permnos, a full `shrcd in (10, 11)` and
    `exchcd in (1, 2, 3)` screen holds 6,909, ZERO pulled permnos fall outside
    the screen, and 15 screened permnos (0.22%) are absent from the pull. So it
    is a 99.78%-complete SUBSET, the missing names are NAMED here rather than
    described, and a re-pull is not warranted.

    REFUSES below `UNIVERSE_COVERAGE_FLOOR`. A guard whose input is derived, and
    whose failure is a number rather than a silence.
    """
    pulled: set[int] = set()
    for year in range(start, end + 1):
        f = tib.WRDS / f"crsp_dsf_{year}.parquet"
        if f.exists():
            pulled |= set(pd.read_parquet(f, columns=["permno"])["permno"].unique().tolist())
    lo, hi = pd.Timestamp(f"{start}-01-01"), pd.Timestamp(f"{end}-12-31")
    scr = names[(names["nameenddt"] >= lo) & (names["namedt"] <= hi)]
    screen = set(scr["permno"].unique().tolist())
    missing = sorted(int(p) for p in (screen - pulled))
    extra = sorted(int(p) for p in (pulled - screen))
    cov = (len(screen & pulled) / len(screen)) if screen else 0.0
    out = {
        "window": f"{start}-{end}",
        "dsf_pull_permnos": len(pulled),
        "screen_permnos": len(screen),
        "screen_definition": "shrcd in (10, 11) and exchcd in (1, 2, 3), name window overlaps",
        "coverage": round(cov, 6),
        "pulled_outside_the_screen": len(extra),
        "missing_from_the_pull": len(missing),
        "missing_permnos": missing,
        "verdict": ("a complete SUBSET of the screen, not a superset"
                    if not extra else "the pull holds names the screen does not"),
    }
    if cov < UNIVERSE_COVERAGE_FLOOR:
        raise SystemExit(
            f"REFUSED: the CRSP daily pull covers {cov:.4%} of the "
            f"{len(screen):,}-permno screen, below the {UNIVERSE_COVERAGE_FLOOR:.2%} "
            f"floor. {len(missing):,} permnos are absent: {missing[:20]}")
    return out


def assert_ibes_loader_agrees(start: int, end: int) -> dict:
    """REFUSE if the extended loader and the script's loader disagree.

    A silent fork here would mean the learner trains on a different universe
    from the one every published band number was measured on, and nothing
    downstream would notice.
    """
    a = load_ibes_ext(start, end)[["cusip", "statpers"]].drop_duplicates()
    b = tib.load_ibes(start, end)[["cusip", "statpers"]].drop_duplicates()
    ka = set(map(tuple, a.itertuples(index=False)))
    kb = set(map(tuple, b.itertuples(index=False)))
    if ka != kb:
        raise SystemExit(
            f"REFUSED: extended IBES loader selects {len(ka):,} name-months, the script's "
            f"loader {len(kb):,}; symmetric difference {len(ka ^ kb):,}. They have forked.")
    return {"name_months": len(ka), "agrees_with": "scripts.tracker_ibes_backtest.load_ibes"}


def load_prices_ext(start: int, end: int) -> pd.DataFrame:
    """The script's price loader, plus `shrout` for market capitalisation.

    `load_prices` already reads one extra leading year (for ret_12m) and
    already handles the two traps that file documents: a negative `prc` is
    CRSP's bid/ask-mean flag (abs, keep the row -- dropping it deletes exactly
    the illiquid names), and everything that compares a price to its own past
    must run on `prc / cfacpr`, never raw, or a reverse split reads as +900%.
    """
    px = tib.load_prices(start, end)
    frames = []
    for year in range(start - 1, end + 1):
        f = tib.WRDS / f"crsp_dsf_{year}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f, columns=["permno", "date", "shrout"]))
    so = pd.concat(frames, ignore_index=True)
    so["date"] = pd.to_datetime(so["date"])
    px = px.merge(so, on=["permno", "date"], how="left")
    # CRSP shrout is in THOUSANDS of shares.
    px["market_cap"] = px["prc"] * px["shrout"] * 1_000.0
    return px


# ------------------------------------------------------- daily derived panel

def daily_panel(px: pd.DataFrame, delist: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per (permno, date): every price-derived feature, and the forward total
    return index values the targets are computed from.

    `delist` is `tracker_ibes_backtest.delisting_factors()[0]`. Its `dl_factor`
    is compounded onto the final index value of every name whose series ends
    before the panel edge, because `dsf.ret` does NOT carry the delisting
    return. Passing None keeps the old, FLATTERING behaviour and records that it
    happened in `px.attrs["delisting_return_applied"]` -- silence would be worse
    than either choice.
    """
    px = px.sort_values(["permno", "date"]).reset_index(drop=True)
    g = px.groupby("permno", sort=False)

    px["tri"] = g["ret"].transform(lambda s: (1.0 + s.fillna(0.0)).cumprod())
    px["high_60d"] = g["adj_prc"].transform(lambda s: s.rolling(60, min_periods=20).max())
    for label, n in (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)):
        px[f"_adj_lag_{label}"] = g["adj_prc"].shift(n)
        px[f"ret_{label}"] = px["adj_prc"] / px[f"_adj_lag_{label}"] - 1.0
    # 12-1: last year's return EXCLUDING the last month. The house's own
    # momentum definition, and the one the arena books all collapse onto.
    px["mom_12_1"] = px["_adj_lag_1m"] / px["_adj_lag_12m"] - 1.0
    px["drawdown_60d"] = px["adj_prc"] / px["high_60d"] - 1.0
    px["vol_20d"] = g["ret"].transform(
        lambda s: s.rolling(20, min_periods=10).std()) * np.sqrt(252.0)
    px["vol_60d"] = g["ret"].transform(
        lambda s: s.rolling(60, min_periods=30).std()) * np.sqrt(252.0)
    px["dollar_vol"] = px["vol"] * px["prc"]
    px["dollar_vol_20d"] = g["dollar_vol"].transform(
        lambda s: s.rolling(20, min_periods=5).median())
    cf252 = g["cfacpr"].shift(252)
    px["split_prior_year"] = (px["cfacpr"] != cf252) & cf252.notna()

    # ---- forward total-return index, with delisting handled, not dropped
    panel_end = px["date"].max()
    last_date = g["date"].transform("max")
    last_tri = g["tri"].transform("last")
    # A permno still trading within PANEL_EDGE_SESSIONS of the file's last day
    # ran into the EDGE of the data; anything earlier left the market.
    edge_cut = panel_end - pd.Timedelta(days=int(PANEL_EDGE_SESSIONS * 1.6))
    delisted = last_date < edge_cut
    # `.where(cond, other=<Series>)` and NEVER `np.where(cond, dates, pd.NaT)`.
    # numpy has no NaT it can broadcast into a datetime64 result: the first
    # version of this file used np.where here and every filled maturity date
    # came back in the year 49557, because NaT was coerced through int64. The
    # targets were unaffected (they are floats) but `walk_forward_splits` keys
    # its train cutoff on these dates, so a silently corrupt column would have
    # quietly deleted training rows and nothing would have failed.
    # ---- THE DELISTING RETURN, compounded onto the last observed index value.
    # `dsf.ret` does not carry it (only 4 of 1,103 delisting-day bars match
    # `dlret`), so without this a dead name's forward return stops at its last
    # TRADE and every long is flattered. The factor is applied only where the
    # permno actually left the market (`delisted`) and only where the delisting
    # event is not BEFORE the last observed bar by more than a week -- a record
    # far away from the series end is a data inconsistency, and inventing a
    # wind-up for it would be worse than counting it.
    dl_applied = {"permnos_with_a_factor": 0, "permnos_applied": 0,
                  "permnos_event_out_of_range": 0, "mean_factor_applied": None,
                  "source": None}
    dl_factor = pd.Series(1.0, index=px.index)
    if delist is not None and len(delist):
        f = delist.set_index("permno")["dl_factor"]
        d0 = delist.set_index("permno")["dlstdt"]
        mapped = px["permno"].map(f)
        event = px["permno"].map(d0)
        dl_applied["permnos_with_a_factor"] = int(
            px.loc[mapped.notna(), "permno"].nunique())
        in_range = event.notna() & (event >= last_date - pd.Timedelta(days=7))
        use = delisted & mapped.notna() & in_range & (mapped != 1.0)
        dl_factor = mapped.where(use, other=1.0).fillna(1.0)
        dl_applied["permnos_applied"] = int(px.loc[use, "permno"].nunique())
        dl_applied["permnos_event_out_of_range"] = int(
            px.loc[delisted & mapped.notna() & ~in_range, "permno"].nunique())
        applied = px.loc[use, ["permno"]].assign(f=dl_factor[use])
        dl_applied["mean_factor_applied"] = (
            round(float(applied.drop_duplicates("permno")["f"].mean()), 6)
            if len(applied) else None)
        dl_applied["source"] = "crsp__dsedelist via tracker_ibes_backtest.delisting_factors"
    else:
        dl_applied["source"] = ("NONE -- delisting returns were NOT applied; "
                                "dead names are held to their last trade and the "
                                "panel is generous to them")
    px.attrs["delisting_return_applied"] = dl_applied

    tri_if_dead = (last_tri * dl_factor).where(delisted)
    date_if_dead = last_date.where(delisted)
    filled = {}
    for h, n in HORIZON_SESSIONS.items():
        fwd = g["tri"].shift(-n)
        # Delisted before the horizon completed: hold to the last observed
        # index value, then cash. Truncated by the panel edge: stays NaN.
        used_fill = fwd.isna() & tri_if_dead.notna()
        px[f"_tri_fwd_{h}m"] = fwd.where(fwd.notna(), other=tri_if_dead)
        md = g["date"].shift(-n)
        px[f"_matdate_{h}m"] = md.where(md.notna(), other=date_if_dead)
        px[f"_delistfill_{h}m"] = used_fill
        filled[f"{h}m"] = int(used_fill.sum())
    px.attrs["delisting_filled_daily_rows"] = filled
    return px.drop(columns=[c for c in px.columns if c.startswith("_adj_lag_")])


def market_indices(px: pd.DataFrame, names: pd.DataFrame) -> pd.DataFrame:
    """Daily VW and EW market total-return indices over the SAME CRSP
    common-stock / main-exchange universe the panel selects from.

    Membership is resolved per (permno, date) against the stocknames validity
    windows, not per permno, because a name that moves off NYSE/AMEX/NASDAQ
    stops being in this market and a permno-level approximation would keep it.
    """
    u = px[["permno", "date", "ret", "market_cap"]].copy()
    nm = names[["permno", "namedt", "nameenddt"]].sort_values("namedt")
    u = u.sort_values("date")
    u = pd.merge_asof(u, nm, left_on="date", right_on="namedt", by="permno",
                      direction="backward")
    u = u[u["namedt"].notna() & (u["date"] <= u["nameenddt"])]
    u = u[u["ret"].notna()]
    u = u.sort_values(["permno", "date"])
    # Weight on YESTERDAY's cap: today's cap already contains today's return.
    u["w"] = u.groupby("permno", sort=False)["market_cap"].shift(1)
    u = u[u["w"].notna() & (u["w"] > 0)]

    by_date = u.groupby("date")
    ew = by_date["ret"].mean()
    num = u.assign(_wr=u["w"] * u["ret"]).groupby("date")["_wr"].sum()
    den = by_date["w"].sum()
    vw = num / den

    idx = pd.DataFrame({"ew_ret": ew, "vw_ret": vw}).sort_index()
    idx["ew_tri"] = (1.0 + idx["ew_ret"]).cumprod()
    idx["vw_tri"] = (1.0 + idx["vw_ret"]).cumprod()
    for h, n in HORIZON_SESSIONS.items():
        idx[f"mkt_ew_{h}m"] = idx["ew_tri"].shift(-n) / idx["ew_tri"] - 1.0
        idx[f"mkt_vw_{h}m"] = idx["vw_tri"].shift(-n) / idx["vw_tri"] - 1.0
    idx.index.name = "date"
    return idx.reset_index()


# ------------------------------------------------------------------- build

def build(start: int = 2013, end: int = 2024, lag_days: int = 1,
          verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """The versioned PIT training table. Returns (frame, build receipt)."""
    log = (lambda *a: print(*a)) if verbose else (lambda *a: None)
    receipt: dict = {"schema_version": SCHEMA_VERSION,
                     "window": f"{start}-{end}", "lag_days": lag_days}

    log("  pinning the IBES loader against the script's ...")
    receipt["ibes_loader_pin"] = assert_ibes_loader_agrees(start, end)
    log(f"    agrees: {receipt['ibes_loader_pin']['name_months']:,} name-months")

    names = tib.load_names()
    receipt["universe_coverage"] = assert_universe_coverage(start, end, names)
    uc = receipt["universe_coverage"]
    log(f"  universe: dsf pull {uc['dsf_pull_permnos']:,} permnos vs screen "
        f"{uc['screen_permnos']:,} -> {uc['coverage']:.4%}, "
        f"{uc['missing_from_the_pull']} missing, {uc['pulled_outside_the_screen']} extra")

    delist, receipt["delistings"] = tib.delisting_factors(start, end)
    log(f"  delisting events {receipt['delistings']['events']:,}; performance "
        f"{receipt['delistings']['by_category'].get('performance', {}).get('events', 0):,} "
        f"mean dlret "
        f"{receipt['delistings']['by_category'].get('performance', {}).get('mean_dlret')}")

    ibes = load_ibes_ext(start, end)
    log(f"  IBES rows with BOTH a target and a rating: {len(ibes):,}")

    ibes = ibes.merge(names[["permno", "ncusip", "namedt", "nameenddt", "sector"]],
                      left_on="cusip", right_on="ncusip", how="inner")
    ibes = ibes[(ibes["statpers"] >= ibes["namedt"]) & (ibes["statpers"] <= ibes["nameenddt"])]
    log(f"  linked to a CRSP common-stock permno valid that month: {len(ibes):,}")

    px = load_prices_ext(start, end)
    log(f"  CRSP daily rows: {len(px):,}")
    receipt["volume_units"] = tib.assert_volume_units(px)
    dp = daily_panel(px, delist=delist)
    receipt["delisting_return_merge"] = dict(dp.attrs.get("delisting_return_applied", {}))
    log(f"  delisting return applied to "
        f"{receipt['delisting_return_merge'].get('permnos_applied', 0):,} permnos "
        f"(mean factor {receipt['delisting_return_merge'].get('mean_factor_applied')})")
    mkt = market_indices(px, names)
    log(f"  market index days: {len(mkt):,}")
    # The panel's own market leg, stamped by the canonical ruler so the receipt
    # names the instrument it was measured with rather than asserting one. Built
    # from the `mkt` frame already in hand -- `benchmark.vw_universe` would call
    # `market_indices` a second time on 13M daily rows for the same series.
    try:
        from learner import benchmark as BM
        receipt["market_benchmark"] = BM.Benchmark(
            "vw_crsp_common_main", mkt.set_index("date")["vw_ret"].dropna(), "D",
            {"source": "learner.dataset.market_indices (same pass as the panel)",
             "construction": "value-weight daily total return, CRSP common stock / "
                             "main exchange, membership resolved per (permno, date), "
                             "weights on the previous session's market cap",
             "dividends_included": True, "network": False}).stamp()
    except Exception as e:                                     # pragma: no cover
        receipt["market_benchmark_error"] = f"{type(e).__name__}: {e}"
    del px

    # ---- PIT join: trade at the first close STRICTLY AFTER statpers + lag.
    keep = ["permno", "date", "prc", "adj_prc", "cfacpr", "high_60d", "tri", "market_cap",
            "dollar_vol_20d", "split_prior_year", "drawdown_60d",
            "vol_20d", "vol_60d", "mom_12_1",
            "ret_1m", "ret_3m", "ret_6m", "ret_12m"]
    keep += ([f"_tri_fwd_{h}m" for h in HORIZONS] + [f"_matdate_{h}m" for h in HORIZONS]
             + [f"_delistfill_{h}m" for h in HORIZONS])
    ibes = ibes.sort_values("statpers")
    ibes["tradable_from"] = ibes["statpers"] + pd.Timedelta(days=lag_days)
    m = pd.merge_asof(ibes, dp[keep].sort_values("date"),
                      left_on="tradable_from", right_on="date", by="permno",
                      direction="forward", tolerance=pd.Timedelta(days=7))
    m = m[m["prc"].notna()].copy()
    log(f"  with a tradable close within 7 days of the cut: {len(m):,}")
    del dp

    m = m.merge(mkt[["date"] + [f"mkt_{b}_{h}m" for b in ("vw", "ew") for h in HORIZONS]],
                on="date", how="left")

    # ---- row key
    m["month"] = m["statpers"].dt.to_period("M").astype(str)
    m = m.rename(columns={"statpers": "vintage", "date": "entry_date"})
    m = m.sort_values(["permno", "vintage"]).reset_index(drop=True)

    # ---- features
    m["close"] = m["prc"]
    # ONE SHARE BASIS: `meanptg` is the UNADJUSTED consensus (the target as it
    # was quoted at `statpers`) and `close` is the raw CRSP close.
    m["ratio"] = m["meanptg"] / m["close"]
    m["upside"] = m["ratio"] - 1.0                 # THE UNIT. ratio - 1.
    m["log_ratio"] = np.log(m["ratio"].where(m["ratio"] > 0))
    # THE CROSS-CHECK, and why it is not the answer. Rescaling the adjusted
    # target by `cfacpr(t)` should undo the restatement; it agrees with the PIT
    # ratio on most rows and cannot agree on all of them, because `cfacpr(t)` is
    # itself a FUTURE quantity (it is the cumulative factor to the END of the
    # sample). A verified re-derivation put the agreement at ~93% and left the
    # rescaled toxic band at -20.3%/yr t -2.70 -- i.e. still contaminated. So
    # this is a DIAGNOSTIC column whose disagreement RATE goes in the receipt,
    # and reading the unadjusted file is the fix.
    cf = m["cfacpr"].where(m["cfacpr"].notna() & (m["cfacpr"] != 0))
    m["ratio_adj_check"] = m["meanptg_adj"] * cf / m["close"]
    _rel = (m["ratio_adj_check"] - m["ratio"]).abs() / m["ratio"].abs().replace(0, np.nan)
    m["ratio_check_agrees"] = (_rel <= RATIO_CHECK_TOL).fillna(False)
    _both = m["ratio"].notna() & m["ratio_adj_check"].notna()
    receipt["share_basis"] = {
        "pit_source": "ibes__ptgsumu.parquet (UNADJUSTED -- the numerator)",
        "adjusted_source": f"{_ADJUSTED_PTG_FILE} (diagnostic only)",
        "denominator": "raw CRSP dsf.prc (abs; negative prc is the bid/ask flag)",
        "check_definition": "ratio_adj_check = mean_target_adj * cfacpr(t) / close",
        "tolerance_relative": RATIO_CHECK_TOL,
        "rows_with_both": int(_both.sum()),
        "agree_rows": int((m["ratio_check_agrees"] & _both).sum()),
        "agree_rate": (round(float((m["ratio_check_agrees"] & _both).sum() / _both.sum()), 6)
                       if _both.any() else None),
        "disagree_rate": (round(float(1.0 - (m["ratio_check_agrees"] & _both).sum() / _both.sum()), 6)
                          if _both.any() else None),
        "why_the_check_cannot_be_the_fix": (
            "cfacpr(t) is the cumulative factor to the END of the sample, so the "
            "rescale multiplies by the same future quantity it is trying to remove"),
        "hand_verified_row": {
            "name": "AAPL", "permno": 14593, "statpers": "2013-06-20",
            "meanptg_adjusted": 19.323, "meanptg_unadjusted": 541.04, "cfacpr": 28.0,
            "note": "cfacpr 28 = the 7:1 of 2014 times the 4:1 of 2020"},
    }
    log(f"  share basis: ratio_adj_check agrees with the PIT ratio on "
        f"{receipt['share_basis']['agree_rate']} of "
        f"{receipt['share_basis']['rows_with_both']:,} rows "
        f"(disagreement {receipt['share_basis']['disagree_rate']})")
    m["log_coverage"] = np.log1p(m["coverage"].clip(lower=0))
    m["disagreement"] = (m["ptghigh"] - m["ptglow"]) / m["meanptg"].replace(0, np.nan)
    m["dispersion"] = m["stdev"] / m["meanptg"].replace(0, np.nan)
    ne = m["numest"].where(m["numest"] > 0)
    m["net_rev_4w"] = (m["numup4w"] - m["numdown4w"]) / ne
    m["net_rev_1m"] = (m["numup1m"] - m["numdown1m"]) / ne
    m["log_dollar_vol_20d"] = np.log1p(m["dollar_vol_20d"].clip(lower=0))
    m["log_market_cap"] = np.log(m["market_cap"].where(m["market_cap"] > 0))
    m["log_close"] = np.log(m["close"].where(m["close"] > 0))

    # Own-history revisions, from the monthly panel itself -- no detail files.
    # A lag is only used when the previous row is genuinely the previous MONTH:
    # a name that left the panel and returned would otherwise have a "one-month"
    # revision spanning a year.
    g = m.groupby("permno", sort=False)
    gap = (m["vintage"] - g["vintage"].shift(1)).dt.days
    ok1 = (gap >= 20) & (gap <= 45)
    gap3 = (m["vintage"] - g["vintage"].shift(3)).dt.days
    ok3 = (gap3 >= 75) & (gap3 <= 115)
    # ONE SHARE BASIS ON BOTH LEGS OF THE REVISION, TOO.
    #
    # `meanptg` is the UNADJUSTED consensus -- the target as quoted in the share
    # terms that existed at that `statpers`. Dividing today's by last month's is
    # therefore a ratio of two DIFFERENT bases whenever a split fell between
    # them: a 2:1 split halves the quoted target and the "revision" reads -50%
    # with no analyst having moved, and a 1-for-10 reverse split reads +900%.
    # Measured on the 1999-2024 panel: 4,303 rows with a mean of +312% and a
    # maximum of +359x, and 6.58% of the holdings of the book this feature
    # produces. Found by an adversarial review, 2026-09-06; it is the same
    # share-basis error as the 2026-09-04 one, one level down, and no test caught
    # it either.
    #
    # THE PRIOR TARGET IS REBASED, NOT DROPPED. `cfacpr` is cumulative to the END
    # of the sample, so its LEVEL is a future quantity -- but the RATIO
    # `cfacpr(t) / cfacpr(t-1)` cancels every factor after t and is exactly the
    # split applied between the two vintages, which is knowable at t. Multiplying
    # the earlier target by it expresses it in today's share terms. Nulling those
    # rows instead would delete 6.58% of the population, and they are not random:
    # names that split are names that ran.
    cf_now = m["cfacpr"].where(m["cfacpr"].notna() & (m["cfacpr"] != 0))
    for h, okh in ((1, ok1), (3, ok3)):
        prev_ptg = g["meanptg"].shift(h)
        prev_cf = g["cfacpr"].shift(h)
        prev_cf = prev_cf.where(prev_cf.notna() & (prev_cf != 0))
        # prior target, restated in the share terms of THIS row
        prev_rebased = prev_ptg * (cf_now / prev_cf)
        m[f"target_rev_{h}m"] = (m["meanptg"] / prev_rebased - 1.0).where(okh)
        m[f"_target_rev_{h}m_rebased"] = (
            okh & prev_cf.notna() & cf_now.notna() & (prev_cf != cf_now)).fillna(False)
    m["consensus_rev_1m"] = (m["consensus"] - g["consensus"].shift(1)).where(ok1)
    m["coverage_rev_1m"] = (m["coverage"] - g["coverage"].shift(1)).where(ok1)

    # ---- HYGIENE, applied HERE so no downstream consumer has to remember it.
    # The census is taken BEFORE the NULLing, because "how many rows did we
    # refuse to have an opinion about, and why" is the number a reader wants.
    _ratio_raw = m["ratio"].copy()
    hy = hygiene(m["ratio"], m["close"], m["coverage"], m["split_prior_year"])
    for c in ("has_opinion", "target_readable", "hygiene_ok"):
        m[c] = hy[c].values
    n = len(m)
    receipt["hygiene"] = {
        "rules": {
            "min_price": P.MIN_PRICE, "min_coverage": P.MIN_COVERAGE,
            "ratio_unreadable_at": RATIO_UNREADABLE_AT,
            "split_prior_year_is_unreadable": True,
            "one_definition": ("close/coverage floors are learner.prior.has_opinion, "
                               "imported not re-implemented"),
        },
        "rows": n,
        "has_opinion": int(m["has_opinion"].sum()),
        "target_readable": int(m["target_readable"].sum()),
        "hygiene_ok": int(m["hygiene_ok"].sum()),
        "failed_price_or_coverage": int((~m["has_opinion"]).sum()),
        "failed_ratio_ge_50": int((_ratio_raw >= RATIO_UNREADABLE_AT).sum()),
        "failed_ratio_nonpositive_or_null": int((~(_ratio_raw > 0)).sum()),
        "failed_split_prior_year": int(m["split_prior_year"].where(
            m["split_prior_year"].notna(), False).astype(bool).sum()),
        "on_failure": ("the row is KEPT (deleting it is survivorship bias) but "
                       "ratio/upside/log_ratio are NULL and band is no_opinion"),
    }
    # The ratio-derived features are NULLED, never zeroed and never clipped: NaN
    # is the panel's word for "we do not know", it is mirrored in `miss__*`, and
    # a 1,000,000x upside left in place is a number a model will happily fit.
    _bad = ~m["hygiene_ok"].astype(bool)
    for c in ("ratio", "upside", "log_ratio"):
        m.loc[_bad, c] = np.nan
    m["ratio_unhygienic"] = _ratio_raw.where(_bad)   # kept for audit, never a feature

    # `band_label` (not `effective_band`) so the band EDGES stay defined in one
    # place while the hygiene that suppresses them is defined in this one.
    m["band"] = np.where(_bad.values, "no_opinion", P.band_label(m["ratio"]).values)
    m["in_admissible"] = (
        P.in_admissible_region(m["ratio"], m["close"], m["coverage"]).values
        & m["hygiene_ok"].to_numpy(dtype=bool))

    # SIC 9900-9999 is CRSP's NONCLASSIFIABLE block and must read as absence of
    # information, never as an industry. The mapping is in ONE place
    # (`tracker_ibes_backtest.SIC_DIVISIONS`); this asserts the panel it produced.
    _sec = m["sector"].astype(str)
    receipt["sector_labels"] = {
        "unclassified_label": tib.SIC_UNCLASSIFIED,
        "counts": _sec.value_counts().to_dict(),
    }
    if "Public Administration" in set(_sec):
        _pa = m.loc[_sec == "Public Administration"]
        if len(_pa) and int(_pa["permno"].nunique()) > 200:
            raise SystemExit(
                "REFUSED: 'Public Administration' covers "
                f"{_pa['permno'].nunique():,} permnos -- that is the pre-2026-09-03 "
                "mislabelling of SIC 9999 (NONCLASSIFIABLE), not a sector.")

    # ---- THE RE-BUCKETING CENSUS. What the old tape called each row, against
    # what the PIT ratio calls it. `ratio_old` is exactly what the corrupted
    # panel computed: the SPLIT-ADJUSTED target over the RAW close.
    _ratio_old = m["meanptg_adj"] / m["close"]
    _band_old = P.effective_band(_ratio_old, m["close"], m["coverage"])
    _cross = (pd.crosstab(_band_old.values, m["band"].astype(str).values)
              .astype(int))
    receipt["rebucketing_census"] = {
        "rows": "old band (adjusted target / raw close) -> new band (PIT)",
        "table": {str(k): {str(kk): int(vv) for kk, vv in v.items()}
                  for k, v in _cross.to_dict(orient="index").items()},
        "old_band_counts": _band_old.value_counts().to_dict(),
        "new_band_counts": pd.Series(m["band"]).value_counts().to_dict(),
    }
    receipt["prior_status"] = {
        "prior_version": P.PRIOR_VERSION,
        "status": "VOID ON THIS PANEL -- constants fitted on the corrupted tape",
        "meaning": ("prior_*/resid_* columns are carried for schema continuity. They "
                    "are NOT expectations until B1.5 re-derives BAND_PRIOR from this "
                    "panel; nothing may read them as an expected excess return."),
        "corrected_toxic_cell_is_not_a_signal": (
            "the corrected toxic_ge_5 cell measures +37.4%/yr t 1.94 on ~7 names/month, "
            "but 84.1% of it trades under $5 (median close $3.08), a $5 floor flips it "
            "to -31.6%/yr t -1.41, its median monthly excess is -0.86% against a mean of "
            "+2.69%, 2022-24 is +0.7%/yr t 0.03, and 27.6% still carries a future "
            "reverse split (+56pp when those are dropped). A right-tail cell in a thin, "
            "cheap corner is not a location shift and must not be carried as a long."),
    }

    # ---- within-month cross-sectional percentile ranks
    for f in RANKED:
        m[ranked_name(f)] = m.groupby("month")[f].rank(pct=True)

    # ---- categorical codes (stable mapping stored in the schema receipt)
    cat_maps: dict[str, dict] = {}
    for c in FEATURES_CAT:
        cats = sorted(m[c].dropna().astype(str).unique())
        mapping = {v: i for i, v in enumerate(cats)}
        m[f"{c}_code"] = m[c].astype(str).map(mapping).astype("float64")
        cat_maps[c] = mapping
    receipt["categorical_maps"] = cat_maps

    # ---- targets
    for h in HORIZONS:
        m[f"fwd_{h}m"] = m[f"_tri_fwd_{h}m"] / m["tri"] - 1.0
        m[f"mat_date_{h}m"] = m[f"_matdate_{h}m"]
        _df = m[f"_delistfill_{h}m"]
        m[f"delisting_filled_{h}m"] = _df.where(_df.notna(), False).astype(bool)
        # THE ROWS-vs-SESSIONS TRAP. `shift(-n)` moves n ROWS, not n sessions.
        # A name that trades a handful of days a year advances five calendar
        # years in 21 rows, and its "one-month" forward return is silently a
        # five-year one -- the same trap `tracker_ibes_backtest` guards with its
        # 20-45 day gap filter. Any row whose realised maturity gap is not
        # roughly the horizon has an UNREADABLE target, so it is NULLED, not
        # kept and not zeroed.
        gap_days = (m[f"mat_date_{h}m"] - m["entry_date"]).dt.days
        expected = HORIZON_SESSIONS[h] * 1.45          # sessions -> calendar days
        filled = m[f"delisting_filled_{h}m"]
        # A delisted name legitimately matures EARLY; it may not mature late,
        # and a same-day death was never buyable.
        ok = np.where(filled,
                      (gap_days >= 1) & (gap_days <= expected * 1.5),
                      (gap_days >= expected * 0.6) & (gap_days <= expected * 1.5))
        m[f"_horizon_ok_{h}m"] = ok & gap_days.notna().to_numpy()
        # A maturity date outside the panel's own span is a coercion bug, not a
        # date. REFUSE rather than train on it: `walk_forward_splits` keys its
        # train cutoff here and a corrupt value deletes rows silently.
        md = m[f"mat_date_{h}m"].dropna()
        if len(md) and (md.min() < pd.Timestamp("1990-01-01")
                        or md.max() > pd.Timestamp.today() + pd.Timedelta(days=400)):
            raise SystemExit(
                f"REFUSED: mat_date_{h}m spans {md.min()} .. {md.max()} -- outside the "
                "panel. A datetime was coerced through int64 somewhere.")
        m[f"fwd_{h}m"] = m[f"fwd_{h}m"].where(m[f"_horizon_ok_{h}m"])
        m[f"mat_date_{h}m"] = m[f"mat_date_{h}m"].where(m[f"_horizon_ok_{h}m"])
        for b in ("vw", "ew"):
            m[f"excess_{b}_{h}m"] = m[f"fwd_{h}m"] - m[f"mkt_{b}_{h}m"]
        m[f"prior_{h}m"] = P.horizon_prior(m["ratio"], m["close"], m["coverage"], h).values
        for b in ("vw", "ew"):
            m[f"resid_{b}_{h}m"] = m[f"excess_{b}_{h}m"] - m[f"prior_{h}m"]
        m[f"pos_vw_{h}m"] = np.where(m[f"excess_vw_{h}m"].notna(),
                                     (m[f"excess_vw_{h}m"] > 0).astype("float64"), np.nan)
    m = m.drop(columns=[c for c in m.columns if c.startswith("_tri_fwd_")
                        or c.startswith("_matdate_") or c.startswith("_delistfill_")
                        or c.startswith("_horizon_ok_")])

    # ---- missingness mask. NaN is preserved; the mask records where.
    masked = list(FEATURES_CONTINUOUS) + list(FEATURES_BOOL) + list(FEATURES_CAT)
    mask_block = pd.DataFrame(
        {missing_mask_name(f): m[f].isna().values for f in masked}, index=m.index)
    m = pd.concat([m, mask_block], axis=1)
    m = m.assign(schema_hash=schema_hash(), prior_version=P.PRIOR_VERSION)

    cols = (["permno", "month", "vintage", "entry_date", "sector", "band",
             "in_admissible", "has_opinion", "target_readable", "hygiene_ok",
             "close", "mean_target", "mean_target_adj", "cfacpr",
             "ratio_adj_check", "ratio_check_agrees", "ratio_unhygienic",
             "market_cap", "schema_hash", "prior_version"]
            + list(FEATURES_CONTINUOUS) + list(FEATURES_BOOL)
            + [f"{c}_code" for c in FEATURES_CAT]
            + [ranked_name(f) for f in RANKED]
            + [missing_mask_name(f) for f in
               list(FEATURES_CONTINUOUS) + list(FEATURES_BOOL) + list(FEATURES_CAT)]
            + target_columns()
            + [f"delisting_filled_{h}m" for h in HORIZONS])
    m = m.rename(columns={"meanptg": "mean_target", "meanptg_adj": "mean_target_adj"})
    cols = [c for c in cols if c in m.columns]
    out = m[cols].copy()

    # The share-basis repair on the revision legs, counted rather than asserted.
    receipt["target_revision_share_basis"] = {
        "rule": ("both legs on ONE basis: the prior target is multiplied by "
                 "cfacpr(t)/cfacpr(t-h), which is exactly the split applied between "
                 "the two vintages and cancels every factor after t"),
        "why": ("meanptg is UNADJUSTED, so a 2:1 split between vintages reads as a -50% "
                "revision with no analyst having moved and a 1-for-10 reverse split as "
                "+900%"),
        "rows_rebased": {f"{h}m": int(m.get(f"_target_rev_{h}m_rebased",
                                            pd.Series(dtype=bool)).sum())
                         for h in (1, 3)},
        "kept_not_dropped": ("names that split are names that ran, so nulling them would "
                             "delete a non-random 6.6% of the population"),
    }
    receipt["rows"] = int(len(out))
    receipt["months"] = int(out["month"].nunique())
    receipt["names"] = int(out["permno"].nunique())
    receipt["schema_hash"] = schema_hash()
    receipt["schema_hash_shadow"] = schema_hash(shadow_only=True)
    receipt["target_maturity"] = {
        f"{h}m": {"rows_with_target": int(out[f"excess_vw_{h}m"].notna().sum()),
                  "rows_null_not_matured": int(out[f"excess_vw_{h}m"].isna().sum())}
        for h in HORIZONS}
    receipt["missingness_top"] = (
        out[[missing_mask_name(f) for f in FEATURES_CONTINUOUS]].mean()
        .sort_values(ascending=False).round(4).to_dict())
    receipt["band_counts"] = out["band"].value_counts().to_dict()
    # THE DELISTING FILL, COUNTED. A name whose CRSP series ends mid-horizon is
    # held to its last total-return index value WITH the delisting return
    # compounded on (`receipt["delisting_return_merge"]` says how many permnos
    # got one and from where), and then sits in cash. Dropping those rows would
    # be survivorship bias. The exposure is a number in the receipt, not a
    # paragraph.
    receipt["horizon_window_guard"] = {
        "rule": "the realised maturity gap must be 0.6x-1.5x the horizon in calendar days "
                "(a delisted name may mature early but never late). shift(-n) moves n ROWS, "
                "and a thinly-traded name advances years in 21 rows.",
        "nulled_by_horizon": {
            f"{h}m": int(out[f"mat_date_{h}m"].isna().sum()
                         - out[f"fwd_{h}m"].isna().sum() * 0) for h in HORIZONS},
    }
    receipt["delisting_filled_rows"] = {
        f"{h}m": {"rows": int(out[f"delisting_filled_{h}m"].sum()),
                  "share": round(float(out[f"delisting_filled_{h}m"].mean()), 5),
                  "mean_fwd_return_of_filled_rows":
                      (round(float(out.loc[out[f"delisting_filled_{h}m"], f"fwd_{h}m"].mean()), 4)
                       if out[f"delisting_filled_{h}m"].any() else None),
                  "mean_fwd_return_of_other_rows":
                      round(float(out.loc[~out[f"delisting_filled_{h}m"], f"fwd_{h}m"].mean()), 4)}
        for h in HORIZONS}
    log(f"  TRAIN TABLE: {len(out):,} rows x {len(out.columns)} cols, "
        f"{receipt['months']} months, {receipt['names']:,} names")
    return out, receipt


def save(df: pd.DataFrame, receipt: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # The schema receipt of the panel being replaced is MOVED ASIDE, never
    # overwritten: a superseded receipt is history, and losing it would delete
    # the evidence of what the old panel actually was.
    if SCHEMA_RECEIPT.exists():
        try:
            old = json.loads(SCHEMA_RECEIPT.read_text(encoding="utf-8"))
            ver = str(old.get("schema", {}).get("schema_version", "unknown"))
        except Exception:
            ver = "unreadable"
        if ver != SCHEMA_VERSION:
            keep = SCHEMA_RECEIPT.with_name(
                f"train_table_schema_{ver}_SUPERSEDED.json")
            if not keep.exists():
                keep.write_text(SCHEMA_RECEIPT.read_text(encoding="utf-8"),
                                encoding="utf-8")
    df.to_parquet(TRAIN_TABLE, index=False)
    payload = {"build": receipt, "schema": feature_schema(),
               "schema_shadow": feature_schema(shadow_only=True),
               "prior": P.describe(),
               "company_state_registered": company_state_schema()}
    SCHEMA_RECEIPT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def load() -> pd.DataFrame:
    if not TRAIN_TABLE.exists():
        raise SystemExit(f"REFUSED: {TRAIN_TABLE} does not exist. Build it first: "
                         "python -m scripts.learner_run --build")
    return pd.read_parquet(TRAIN_TABLE)


# --------------------------------------------------------- walk-forward splits

def walk_forward_splits(df: pd.DataFrame, test_years, horizon_months: int,
                        min_train_months: int = 24):
    """Expanding-window splits BY DATE. Never random, never k-fold.

    The train side is not "everything before the test year" -- it is everything
    whose TARGET HAD ALREADY MATURED before the test year began. A row dated
    Nov 2015 with a 12-month target does not resolve until Nov 2016 and would
    hand a 2016 test year eleven months of its own future.
    """
    mat = f"mat_date_{horizon_months}m"
    y_col = f"excess_vw_{horizon_months}m"
    for y in test_years:
        cutoff = pd.Timestamp(f"{y}-01-01")
        tr = df.index[(df[mat].notna()) & (df[mat] < cutoff) & (df[y_col].notna())]
        te = df.index[(df["entry_date"] >= cutoff)
                      & (df["entry_date"] < pd.Timestamp(f"{y + 1}-01-01"))
                      & (df[y_col].notna())]
        if len(tr) == 0 or len(te) == 0:
            continue
        n_months = df.loc[tr, "month"].nunique()
        if n_months < min_train_months:
            continue
        yield y, tr, te


__all__ = [
    "SCHEMA_VERSION", "HORIZONS", "HORIZON_SESSIONS", "TRAIN_TABLE", "SCHEMA_RECEIPT",
    "FEATURES_CONTINUOUS", "FEATURES_BOOL", "FEATURES_CAT", "RANKED", "SHADOW_MAPPABLE",
    "feature_columns", "feature_schema", "schema_hash", "missing_mask_name",
    "target_columns", "company_state_schema", "load_ibes_ext", "load_prices_ext",
    "daily_panel", "market_indices", "build", "save", "load", "walk_forward_splits",
    "ranked_name", "hygiene", "assert_universe_coverage",
    "RATIO_UNREADABLE_AT", "RATIO_CHECK_TOL", "UNIVERSE_COVERAGE_FLOOR",
]
