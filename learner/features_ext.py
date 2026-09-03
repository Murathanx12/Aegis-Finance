"""INTERACTION features over 13F ownership and analyst identity -- and the
families they are grouped into for an ABLATION, not a leaderboard.

WHY THIS FILE EXISTS AT ALL
===========================
The house's standing evidence on "news features" is negative and specific:
T12 measured that only 7.7% of corpus news is a NEW DATED FACT, and Benzinga's
coverage ratio is 390:1 mega-cap to small-cap, so *requiring* news is a size
filter wearing a sentiment costume. Raw attention/sentiment is therefore not
rebuilt here. What survived measurement is narrower and stranger:

* analyst **BIAS persists** across an analyst's own halves (Spearman 0.376,
  decile means -2.8pp -> +80pp) while **accuracy does not** (0.087). So the
  usable analyst object is *who is systematically optimistic*, not *who is
  right* -- and a consensus is worth de-biasing, not worth trusting.
  (`backend/data/optimus/tracker_backtest/analyst_target_grades.json`)
* 13F **holder identity is thin** (~5bps per 1sd, t 2.24, under costs), and the
  manager's OWN top-decile stake size is **ADVERSE** (-1.21pp/252 sessions,
  t -3.95). NEW-by-long-duration-filer *underperforms*, which the receipt
  attributes to an index-reconstitution confound.
  (`.../holder_h2_h3.json`, `.../holder_fingerprint_summary.json`)

Two thin-and-adverse main effects are exactly the situation where an INTERACTION
is the honest next question: *does a holder action mean something different when
the name is thinly covered, or when the analysts revising it are known to be
optimistic?* This module builds those interactions. It does not build a
sentiment score.

THE PIT RULES, STATED ONCE
==========================
* **13F**: Thomson `s34` carries no SEC filing timestamp. `rdate` is the report
  quarter end, `fdate` is Thomson's vintage. The public date is
  `quarter_end(max(rdate, first vintage)) + 45 calendar days` -- the statutory
  deadline applied to the LATER of the two, which is what
  `scripts/holder_fingerprint.py` already uses. Measured in this pull: `fdate`
  equals `rdate` on 100% of rows, and `_count_vintage_ahead_of_report` counts
  every violation so the build receipt can REFUSE rather than silently inherit
  a 45-day look-ahead if a re-pull ever carries genuine vintages.
* **Fingerprints** stamped for as-of-quarter `q` read filings through `q-1`
  only. That is the guarantee `holder_fingerprint.py` makes and this module
  consumes; it never reads a fingerprint row with `as_of_qidx != q`.
* **Analyst bias**: a target announced at `anndats` does not resolve until
  `anndats + 12m`. An analyst's bias usable in month `m` is the expanding mean
  of the errors of targets that had ALREADY RESOLVED before `m` began. A target
  is "live" in month `m` if it was announced STRICTLY BEFORE month `m` started
  and within the preceding 12 months. Announced-this-month targets are excluded
  even though `statpers` sits mid-month: being conservative in a stated
  direction is the cheap side of this trade.
* Every cross-sectional standardisation (`_z`) is computed WITHIN a month, from
  that month's cross-section only. That reads no future; it is the same
  operation `dataset.py` already performs for its `__xs` ranks.

WHAT THIS MODULE DOES NOT TOUCH
===============================
`learner/dataset.py`, `models.py`, `evaluate.py` and `states.py` are READ-ONLY
here. This module adds columns to a COPY of the training table and declares
which family each column belongs to; the ablation lives in
`scripts/feature_families_run.py`.

Licence: PRODUCT_EXPERIMENT. Exploration. No significance gate, no MDE, no
multiplicity control -- and correspondingly no claim of alpha. Costs are never
omitted: the ablation's books charge 10 bps/side on measured turnover.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
HOLDER_PANEL = WRDS / "feature_ext_holder_panel.parquet"
ANALYST_PANEL = WRDS / "feature_ext_analyst_panel.parquet"
GRADES = WRDS / "analyst_target_grades.parquet"
QSNAP = WRDS / "holder_qsnap.parquet"
FINGERPRINTS = WRDS / "holder_fingerprints.parquet"

FEATURES_EXT_VERSION = "features-ext-1"

#: 13F is public 45 calendar days after the report quarter end at the earliest.
FILING_LAG_DAYS = 45
#: A 13F quarter older than this at the trade date is STALE and is not joined.
#: 45 (deadline) + 92 (a full quarter) + slack. Nothing legitimate exceeds it.
HOLDER_MAX_STALE_DAYS = 190
#: A target is live for 12 months after its announcement.
TARGET_LIFE_DAYS = 365
#: The measured edge band: `ibes_status_rules_2013_2024.json` puts the BUY
#: basket at t 2.355 for coverage 1-3 and t 2.060 for 4-10, decaying to t 0.189
#: at 26+. "Thin" is <= 10 analysts; "very thin" is <= 3.
THIN_COVERAGE = 10
VERY_THIN_COVERAGE = 3
#: A "specialist" filer: concentrated by sector, and running a real book rather
#: than an index. Terciles are re-cut EVERY quarter from that quarter's own
#: filers, so the label never imports a full-sample quantile.
SPECIALIST_MIN_POSITIONS = 5
SPECIALIST_MAX_POSITIONS = 300
#: A duration cohort needs a filer with enough COMPLETED spells to have a
#: median duration at all.
MIN_COMPLETED_SPELLS = 10

# ------------------------------------------------------------------ families

#: B. the holder family. Every column is derived from filings public at least
#: 45 days before the trade date.
HOLDER_FEATURES: tuple[str, ...] = (
    "h_n_holders", "h_log_n_holders",
    "h_n_holders_chg", "h_n_holders_chg_pct",
    "h_inst_own", "h_inst_own_chg",                       # the 13F-popularity CORPSE control
    "h_new_frac", "h_exit_frac", "h_net_entry_frac",
    "h_new_longdur_frac", "h_new_shortdur_frac", "h_exit_longdur_frac",
    "h_stake_anom_mean", "h_stake_anom_top_decile_frac",  # the ADVERSE signal
    "h_specialist_frac", "h_specialist_new_n", "h_multi_specialist_new",
    "h_top5_share", "h_top_holder_log_chg",
)

#: A. the analyst family.
ANALYST_FEATURES: tuple[str, ...] = (
    "a_n_live_analysts", "a_n_live_targets",
    "a_bias_mean", "a_bias_disp", "a_bias_mean_xs",
    "a_implied_mean", "a_implied_bias_corrected", "a_implied_vs_upside",
    "a_upside_bias_corrected",
    "a_rev_accel", "a_thin_cov", "a_very_thin_cov", "a_cov_thinness",
)

#: C. the interaction family. Every one is a PRODUCT of two things whose MAIN
#: EFFECTS are already present in base+analyst+holder, so the ablation asks the
#: interaction question and not a disguised main-effect question.
INTERACTION_FEATURES: tuple[str, ...] = (
    "x_holder_add_x_rev",          # holder action x analyst revision, same quarter
    "x_exit_x_rev_down",
    "x_holder_anom_x_thincov",     # holder anomaly x coverage thinness
    "x_holder_add_x_thincov",
    "x_specialist_x_thincov",
    "x_new13f_x_ret6m_sign",       # new 13F position x trailing 6m sign (reconstitution)
    "x_newlongdur_x_ret6m_sign",
    "x_bias_x_upside",             # optimistic coverage x how much upside it claims
    "x_bias_x_thincov",
)

FAMILIES: dict[str, tuple[str, ...]] = {
    "analyst": ANALYST_FEATURES,
    "holder": HOLDER_FEATURES,
    "interaction": INTERACTION_FEATURES,
}

#: The ablation ladder. Nested as the brief asks, PLUS `base+holder` so that
#: each of the two main families is also tested against base on its own -- a
#: purely nested ladder cannot say which of two families a joint gain came
#: from, and "record the negative" needs an ATTRIBUTABLE negative.
ABLATION_SETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("base", ()),
    ("base+analyst", ("analyst",)),
    ("base+holder", ("holder",)),
    ("base+analyst+holder", ("analyst", "holder")),
    ("base+analyst+holder+interaction", ("analyst", "holder", "interaction")),
)


def family_of(col: str) -> str | None:
    for fam, cols in FAMILIES.items():
        if col in cols:
            return fam
    return None


def all_ext_features() -> list[str]:
    out: list[str] = []
    for fam in ("analyst", "holder", "interaction"):
        out += list(FAMILIES[fam])
    return out


def columns_for(families: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for fam in families:
        out += list(FAMILIES[fam])
    return out


# ------------------------------------------------------------------- helpers

def _z(s: pd.Series, by: pd.Series) -> pd.Series:
    """Within-month standardisation. Reads only the contemporaneous cross
    section, so it is PIT; a full-sample z would not be."""
    g = s.groupby(by)
    mu = g.transform("mean")
    sd = g.transform("std")
    return (s - mu) / sd.where(sd > 0)


def _qidx_of(y: int, q: int) -> int:
    """1995Q1 == 0, matching `scripts/holder_fingerprint.qidx_of`."""
    return (y - 1995) * 4 + (q - 1)


def _quarter_end(qidx: int) -> pd.Timestamp:
    qidx = int(qidx)                       # a float qidx indexes nothing
    y = 1995 + qidx // 4
    q = qidx % 4 + 1
    return pd.Timestamp(year=y, month=[3, 6, 9, 12][q - 1],
                        day=[31, 30, 30, 31][q - 1])


def _public_date(qidx: int) -> pd.Timestamp:
    return _quarter_end(int(qidx)) + timedelta(days=FILING_LAG_DAYS)


def _count_vintage_ahead_of_report(cur: pd.DataFrame, q: int) -> int:
    """How many rows carry a Thomson vintage LATER than the report quarter.

    The public-date rule reduces to `quarter_end(q) + 45d` only because this is
    zero on every row of this pull (`holders_13f.py` measured `fdate - rdate`:
    median 0, min 0, max 0 over 24 quarters). If a future re-pull carries real
    vintages, the reduction becomes a 45-day look-ahead for the stale rows -- so
    the count goes into the receipt and the caller can refuse on it, rather than
    a comment asserting a property nothing checks.
    """
    return int((cur["fq"].to_numpy() > q).sum())


# ------------------------------------------------------------- holder panel

def build_holder_panel(start_year: int = 2012, end_year: int = 2024,
                       verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """One row per (permno, 13F report quarter), stamped with its PUBLIC date.

    Everything here is an aggregate over the filers that held the name that
    quarter. Entries and exits are counted only for filers present in BOTH
    quarters -- a manager who skipped a filing has not sold anything, and
    counting that as an exit is the easiest way to manufacture a signal out of
    Thomson's coverage rather than out of behaviour.
    """
    from scripts import holder_fingerprint as HF        # read-only reuse

    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    diag: dict = {"quarters": 0, "positions": 0, "rows_fq_ahead_of_rq": 0,
                  "positions_no_price": 0, "filers_without_adjacent_prior": 0,
                  "fingerprint_join_hit": 0, "fingerprint_join_miss": 0}

    link = HF.load_cusip_link()
    rdr = HF.S34Reader(link)

    qs = pd.read_parquet(QSNAP, columns=["permno", "qidx", "prc", "shrout", "cfacshr"])
    qs["k"] = qs["qidx"].astype("int64") * 1_000_000 + qs["permno"].astype("int64")
    qsnap = qs.drop_duplicates("k", keep="last").set_index("k")[["prc", "shrout", "cfacshr"]]

    fp = pd.read_parquet(FINGERPRINTS, columns=[
        "mgrno", "as_of_qidx", "dur_median_qtrs", "n_completed_spells",
        "sector_entropy", "n_positions",
        "pct_of_company_p25", "pct_of_company_median", "pct_of_company_p90"])

    q_lo = _qidx_of(start_year, 1)
    q_hi = _qidx_of(end_year, 4)

    out_rows: list[pd.DataFrame] = []
    prev: pd.DataFrame | None = None
    prev_q: int | None = None

    for q in range(q_lo - 1, q_hi + 1):
        cur = rdr.quarter(q)
        if len(cur) == 0:
            prev, prev_q = None, None
            continue
        diag["rows_fq_ahead_of_rq"] += _count_vintage_ahead_of_report(cur, q)

        s = qsnap.reindex(np.int64(q) * 1_000_000 + cur["permno"].to_numpy(dtype="int64"))
        ok = s["prc"].notna().to_numpy() & (s["prc"].to_numpy() > 0)
        diag["positions_no_price"] += int((~ok).sum())
        cur = cur[ok].reset_index(drop=True)
        s = s[ok].reset_index(drop=True)
        if len(cur) == 0:
            prev, prev_q = None, None
            continue

        cfacshr = s["cfacshr"].to_numpy()
        cfac = np.where(np.isfinite(cfacshr) & (cfacshr > 0), cfacshr, 1.0)
        raw_shares = cur["shares"].to_numpy()
        shares_adj = raw_shares * cfac                       # split-comparable
        shrout = np.maximum(s["shrout"].to_numpy(), 1.0) * 1000.0
        shrout_adj = shrout * cfac                           # same units as shares_adj
        pct_co = np.clip(raw_shares / shrout, 0.0, 1.0)

        cq = pd.DataFrame({
            "mgrno": cur["mgrno"].to_numpy(), "permno": cur["permno"].to_numpy(),
            "shares_adj": shares_adj, "pct_co": pct_co,
            "shrout_adj": shrout_adj, "fq": cur["fq"].to_numpy(),
        })
        diag["positions"] += len(cq)

        # ---- PIT public quarter: max(report quarter, the manager's own latest
        #      vintage), per the fingerprint script's conservative rule.
        pub_q_mgr = np.maximum(cq.groupby("mgrno")["fq"].transform("max").to_numpy(), q)
        cq["pub_q"] = pub_q_mgr.astype("int32")

        # ---- the PIT fingerprint stamped FOR THIS QUARTER (which reads q-1 only)
        f = fp[fp["as_of_qidx"] == q]
        cq = cq.merge(f.drop(columns=["as_of_qidx"]), on="mgrno", how="left")
        diag["fingerprint_join_hit"] += int(cq["dur_median_qtrs"].notna().sum())
        diag["fingerprint_join_miss"] += int(cq["dur_median_qtrs"].isna().sum())

        # ---- filer cohorts, RE-CUT from this quarter's filers only
        fq_mgr = cq.drop_duplicates("mgrno")
        dur = fq_mgr["dur_median_qtrs"].where(
            fq_mgr["n_completed_spells"] >= MIN_COMPLETED_SPELLS)
        d_lo, d_hi = dur.quantile(1 / 3), dur.quantile(2 / 3)
        ent = fq_mgr["sector_entropy"]
        e_lo = ent.quantile(1 / 3)
        cohort = pd.DataFrame({
            "mgrno": fq_mgr["mgrno"].to_numpy(),
            "long_dur": (dur >= d_hi).to_numpy(),
            "short_dur": (dur <= d_lo).to_numpy(),
            "specialist": ((ent <= e_lo)
                           & (fq_mgr["n_positions"] >= SPECIALIST_MIN_POSITIONS)
                           & (fq_mgr["n_positions"] <= SPECIALIST_MAX_POSITIONS)).to_numpy(),
        })
        cq = cq.merge(cohort, on="mgrno", how="left")
        # Cohort flags are COUNTED downstream, so they are numeric here. A
        # boolean column whose merge introduced NaN becomes `object`, and
        # `.sum()` over it returns a bool -- which then survives all the way to
        # `to_parquet` and fails there, after the whole 52-quarter loop.
        for c in ("long_dur", "short_dur", "specialist"):
            cq[c] = pd.to_numeric(cq[c], errors="coerce").astype("float64")

        # ---- stake size vs the FILER'S OWN history (the adverse signal).
        #      Where the current stake sits on a log scale inside the manager's
        #      own p25..p90 ladder. NOT a cross-manager z: a manager who only
        #      ever takes 1% stakes must not read as "anomalous" against
        #      everyone else, and the receipt's adverse finding is defined on
        #      the manager's OWN history.
        lo = np.log10(cq["pct_of_company_p25"].to_numpy())
        md = np.log10(cq["pct_of_company_median"].to_numpy())
        hi = np.log10(cq["pct_of_company_p90"].to_numpy())
        pc = cq["pct_co"].to_numpy()
        now = np.log10(np.where(pc > 0, pc, np.nan))
        width = hi - lo
        spread = np.where(np.isfinite(width) & (width > 0), width, np.nan)
        cq["stake_anom"] = (now - md) / spread
        cq["stake_top_decile"] = pc >= cq["pct_of_company_p90"].to_numpy()

        # ---- entries and exits vs the immediately preceding quarter
        ev_cols = ["n_new", "n_exit", "n_new_long", "n_new_short",
                   "n_new_spec", "n_exit_long"]
        if prev is not None and prev_q == q - 1:
            shared = np.intersect1d(cq["mgrno"].unique(), prev["mgrno"].unique())
            diag["filers_without_adjacent_prior"] += int(
                cq["mgrno"].nunique() - len(shared))
            m = cq[["mgrno", "permno", "shares_adj", "long_dur", "short_dur",
                    "specialist"]].merge(
                prev, on=["mgrno", "permno"], how="outer", suffixes=("", "_p"))
            m = m[m["mgrno"].isin(shared)]
            sn = np.nan_to_num(m["shares_adj"].to_numpy(), nan=0.0)
            sp = np.nan_to_num(m["shares_adj_p"].to_numpy(), nan=0.0)
            is_new = (sp == 0) & (sn > 0)
            is_exit = (sp > 0) & (sn == 0)
            new_g = m[is_new].groupby("permno")
            exit_g = m[is_exit].groupby("permno")
            ev = pd.concat([
                new_g.size().rename("n_new"),
                exit_g.size().rename("n_exit"),
                new_g["long_dur"].sum().rename("n_new_long"),
                new_g["short_dur"].sum().rename("n_new_short"),
                new_g["specialist"].sum().rename("n_new_spec"),
                # an exiting filer's cohort is read from the PRIOR quarter's
                # fingerprint -- it is the cohort it belonged to while holding.
                exit_g["long_dur_p"].sum().rename("n_exit_long"),
            ], axis=1)
            has_events = True
        else:
            ev = pd.DataFrame(columns=ev_cols)
            ev.index.name = "permno"
            has_events = False

        if q >= q_lo:
            g = cq.groupby("permno")
            agg = pd.DataFrame({
                "h_n_holders": g.size(),
                "inst_shares": g["shares_adj"].sum(),
                "shrout_adj": g["shrout_adj"].first(),
                "h_stake_anom_mean": g["stake_anom"].mean(),
                "h_stake_anom_top_decile_frac": g["stake_top_decile"].mean(),
                "h_specialist_frac": g["specialist"].mean(),
                "top_shares": g["shares_adj"].max(),
                "top5_shares": g["shares_adj"].apply(
                    lambda x: float(np.sort(x.to_numpy())[-5:].sum())),
            })
            agg = agg.join(ev, how="left")
            for c in ev_cols:
                if c not in agg.columns:
                    agg[c] = np.nan
            agg["qidx"] = q
            agg["has_events"] = has_events
            # PER NAME, not per quarter. The aggregate over a name's filers is
            # only public once the LAST of those filers is public -- but that is
            # a statement about THAT name's filers. Taking the max over the whole
            # quarter would let one stale filer anywhere in the market push every
            # name's features two quarters late, which is safe and useless.
            agg["public_qidx"] = g["pub_q"].max().astype("int32")
            out_rows.append(agg.reset_index())
            diag["quarters"] += 1
            log(f"  {HF.qlabel(q)}: {len(cq):,} positions, {len(agg):,} names, "
                f"{cq['mgrno'].nunique():,} filers")

        prev = cq[["mgrno", "permno", "shares_adj", "long_dur"]].rename(
            columns={"shares_adj": "shares_adj_p", "long_dur": "long_dur_p"})
        prev_q = q

    if not out_rows:
        raise SystemExit("REFUSED: no 13F quarter produced rows.")
    panel = pd.concat(out_rows, ignore_index=True)
    panel = panel.sort_values(["permno", "qidx"]).reset_index(drop=True)

    # ---- own-history deltas, computed ONLY across genuinely adjacent quarters.
    #      A name that left the 13F panel and returned would otherwise show a
    #      "one-quarter" holder-count change spanning years -- the same shape as
    #      the rows-vs-sessions trap `dataset.py` guards on the price side.
    pg = panel.groupby("permno", sort=False)
    adj = ((panel["qidx"] - pg["qidx"].shift(1)) == 1).to_numpy()
    prev_n = pg["h_n_holders"].shift(1).where(adj)
    panel["h_n_holders_chg"] = panel["h_n_holders"] - prev_n
    panel["h_n_holders_chg_pct"] = panel["h_n_holders_chg"] / prev_n.where(prev_n > 0)
    panel["h_log_n_holders"] = np.log1p(panel["h_n_holders"])
    panel["h_inst_own"] = (panel["inst_shares"]
                           / panel["shrout_adj"].where(panel["shrout_adj"] > 0)).clip(upper=2.0)
    prev_own = pg["h_inst_own"].shift(1).where(adj)
    panel["h_inst_own_chg"] = panel["h_inst_own"] - prev_own
    prev_top = pg["top_shares"].shift(1).where(adj)
    ratio_top = (panel["top_shares"] / prev_top.where(prev_top > 0))
    panel["h_top_holder_log_chg"] = np.log(ratio_top.where(ratio_top > 0))
    panel["h_top5_share"] = (panel["top5_shares"]
                             / panel["inst_shares"].where(panel["inst_shares"] > 0))

    denom = prev_n.where(prev_n > 0)
    panel["h_new_frac"] = panel["n_new"].fillna(0.0) / denom
    panel["h_exit_frac"] = panel["n_exit"].fillna(0.0) / denom
    panel["h_net_entry_frac"] = panel["h_new_frac"] - panel["h_exit_frac"]
    panel["h_new_longdur_frac"] = panel["n_new_long"].fillna(0.0) / denom
    panel["h_new_shortdur_frac"] = panel["n_new_short"].fillna(0.0) / denom
    panel["h_exit_longdur_frac"] = panel["n_exit_long"].fillna(0.0) / denom
    panel["h_specialist_new_n"] = panel["n_new_spec"]
    panel["h_multi_specialist_new"] = (panel["n_new_spec"].fillna(0.0) >= 2).astype("float64")

    # A quarter with no adjacent prior filing has NO event features. NaN, never
    # 0 -- "we could not observe entries" is not "no manager entered".
    no_ev = (~panel["has_events"].to_numpy()) | (~adj)
    for c in ("h_new_frac", "h_exit_frac", "h_net_entry_frac", "h_new_longdur_frac",
              "h_new_shortdur_frac", "h_exit_longdur_frac", "h_specialist_new_n",
              "h_multi_specialist_new"):
        panel.loc[no_ev, c] = np.nan

    # A later report quarter must never look public EARLIER than an earlier one
    # (a stale filer in q can push q's public date past q+1's). Without the
    # cumulative max, an as-of join on public_date could hand a trade the q+1
    # row while the q row -- which the join would prefer -- was still pending.
    # This is a monotonicity repair, not a date change: it only ever moves a
    # public date LATER.
    panel["public_qidx"] = (panel.groupby("permno", sort=False)["public_qidx"]
                            .cummax().astype("int32"))
    n_before = len(panel)
    # Two report quarters that become public on the SAME date: keep the FRESHER
    # one. An as-of join on a duplicated key is otherwise resolved by row order.
    panel = panel.sort_values(["permno", "public_qidx", "qidx"]).drop_duplicates(
        ["permno", "public_qidx"], keep="last").reset_index(drop=True)
    diag["rows_dropped_duplicate_public_date"] = int(n_before - len(panel))

    panel["public_date"] = panel["public_qidx"].map(_public_date)
    panel = panel[["permno", "qidx", "public_qidx", "public_date"] + list(HOLDER_FEATURES)]
    for c in HOLDER_FEATURES:
        panel[c] = pd.to_numeric(panel[c], errors="coerce").astype("float64")
    diag["public_lag_quarters"] = (
        (panel["public_qidx"] - panel["qidx"]).value_counts().sort_index().to_dict())

    diag["rows"] = int(len(panel))
    diag["names"] = int(panel["permno"].nunique())
    diag["quarters_kept"] = int(panel["qidx"].nunique())
    diag["public_date_rule"] = ("quarter_end(max(report quarter, the filer's latest "
                                "Thomson vintage)) + 45 calendar days")
    diag["vintage_reduction_valid"] = bool(diag["rows_fq_ahead_of_rq"] == 0)
    diag["nonnull_share"] = {c: round(float(panel[c].notna().mean()), 4)
                             for c in HOLDER_FEATURES}
    diag.update(rdr.stats)
    return panel, diag


# ------------------------------------------------------------ analyst panel

def build_analyst_panel(start_month: str = "2013-01", end_month: str = "2024-12",
                        verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """One row per (permno, month): what the CURRENTLY LIVE targets say, and how
    optimistic the analysts saying it have historically been.

    `analyst_target_grades.parquet` is the row-level artefact behind
    `analyst_target_grades.json`: 1,333,683 graded targets, `amaskcd` following
    an analyst ACROSS FIRMS, `error = implied - realized_12m`. Positive error is
    over-optimism. The receipt's finding is that this quantity persists
    (Spearman 0.376) while accuracy does not (0.087), so the panel DE-BIASES the
    consensus and does NOT weight by accuracy.
    """
    log = (lambda *a: print(*a, flush=True)) if verbose else (lambda *a: None)
    if not GRADES.exists():
        raise SystemExit(
            f"REFUSED: {GRADES} is missing. The analyst family cannot be built "
            "from the consensus panel alone -- per-analyst identity is the whole "
            "point of it.")
    g = pd.read_parquet(GRADES, columns=["amaskcd", "permno", "anndats",
                                         "implied", "error"])
    g = g.dropna(subset=["amaskcd", "permno", "anndats", "implied", "error"])
    diag: dict = {"graded_targets": int(len(g)),
                  "analysts": int(g["amaskcd"].nunique()),
                  "names": int(g["permno"].nunique()),
                  "anndats_min": str(g["anndats"].min().date()),
                  "anndats_max": str(g["anndats"].max().date())}

    months = pd.period_range(start_month, end_month, freq="M")
    grid_months = [str(p) for p in months]
    grid_set = set(grid_months)

    # ---- (1) PIT analyst bias: the expanding mean of the errors of targets
    #          that had already RESOLVED (anndats + 12m) before the month began.
    g = g.assign(resolve=g["anndats"] + pd.Timedelta(days=TARGET_LIFE_DAYS))
    g["_rm"] = g["resolve"].dt.to_period("M")
    per = (g.groupby(["amaskcd", "_rm"], sort=True)
             .agg(s=("error", "sum"), n=("error", "size")).reset_index()
             .sort_values(["amaskcd", "_rm"]))
    pgb = per.groupby("amaskcd", sort=False)
    per["cum_s"] = pgb["s"].cumsum()
    per["cum_n"] = pgb["n"].cumsum()
    # State stamped at resolve-month r is usable from r+1 onward: a target that
    # resolves DURING month r was not resolved when month r opened.
    per["month"] = (per["_rm"] + 1).astype(str)
    per = per[per["month"] <= end_month]
    # Everything usable before the grid opens collapses into the first month.
    per.loc[per["month"] < grid_months[0], "month"] = grid_months[0]
    per = (per.sort_values(["amaskcd", "month"])
              .drop_duplicates(["amaskcd", "month"], keep="last"))

    mi = pd.MultiIndex.from_product(
        [np.sort(per["amaskcd"].unique()), grid_months], names=["amaskcd", "month"])
    bstate = per.set_index(["amaskcd", "month"])[["cum_s", "cum_n"]].reindex(mi)
    bstate = bstate.groupby(level=0).ffill()
    bstate = bstate[bstate["cum_n"].notna() & (bstate["cum_n"] > 0)]
    bstate = bstate.assign(bias=bstate["cum_s"] / bstate["cum_n"]).reset_index()
    bstate = bstate[["amaskcd", "month", "bias", "cum_n"]].rename(
        columns={"cum_n": "n_resolved"})
    diag["analyst_month_bias_rows"] = int(len(bstate))

    # ---- (2) live targets, exploded onto the months in which they are live.
    #          Announced STRICTLY BEFORE the month started, within 12 months.
    ann_p = g["anndats"].dt.to_period("M")
    live = g[["amaskcd", "permno", "implied"]].assign(_ap=ann_p)
    parts = []
    for k in range(1, 13):
        p = live.assign(month=(live["_ap"] + k).astype(str))
        parts.append(p.loc[p["month"].isin(grid_set),
                           ["amaskcd", "permno", "month", "implied"]])
    exploded = pd.concat(parts, ignore_index=True)
    diag["live_target_months"] = int(len(exploded))

    exploded = exploded.merge(bstate, on=["amaskcd", "month"], how="left")
    diag["live_target_months_with_bias"] = int(exploded["bias"].notna().sum())
    diag["bias_coverage"] = round(float(exploded["bias"].notna().mean()), 4)

    # A target from an analyst with no resolved history is left at its face
    # value: correcting it by zero is the honest "no opinion", not an
    # imputation of the pooled bias (which would leak the cross-section).
    exploded["_corrected"] = exploded["implied"] - exploded["bias"].fillna(0.0)
    a = (exploded.groupby(["permno", "month"])
         .agg(a_n_live_targets=("implied", "size"),
              a_n_live_analysts=("amaskcd", "nunique"),
              a_implied_mean=("implied", "mean"),
              a_bias_mean=("bias", "mean"),
              a_bias_disp=("bias", "std"),
              a_implied_bias_corrected=("_corrected", "mean"))
         .reset_index())
    diag["rows"] = int(len(a))
    diag["names_out"] = int(a["permno"].nunique())
    diag["months_out"] = int(a["month"].nunique())
    diag["mean_bias_pooled"] = round(float(a["a_bias_mean"].mean()), 5)
    log(f"  analyst panel: {len(a):,} name-months, {a['permno'].nunique():,} names")
    return a, diag


# --------------------------------------------------------------- attachment

def attach(df: pd.DataFrame, holder: pd.DataFrame,
           analyst: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Join both panels onto a COPY of the training table and build the
    interactions. `df` is never mutated."""
    out = df.copy()
    diag: dict = {}

    # ---- 13F: backward as-of on the PUBLIC date, never the report date.
    h = holder.sort_values("public_date")
    left = out[["permno", "entry_date"]].copy()
    left["_i"] = np.arange(len(left))
    left["permno"] = left["permno"].astype("int64")
    h = h.copy()
    h["permno"] = h["permno"].astype("int64")
    left = left.sort_values("entry_date")
    j = pd.merge_asof(left, h, left_on="entry_date", right_on="public_date",
                      by="permno", direction="backward",
                      tolerance=pd.Timedelta(days=HOLDER_MAX_STALE_DAYS))
    j = j.sort_values("_i")
    for c in HOLDER_FEATURES:
        out[c] = j[c].to_numpy()
    lag = (j["entry_date"] - j["public_date"]).dt.days
    qend_lag = j["entry_date"] - j["public_qidx"].map(
        lambda v: _quarter_end(v) if pd.notna(v) else pd.NaT)
    qend_lag = qend_lag.dt.days
    diag["holder_join"] = {
        "rows": int(len(out)),
        "matched": int(j["public_date"].notna().sum()),
        "match_rate": round(float(j["public_date"].notna().mean()), 4),
        "lag_days_after_public_min": (None if lag.dropna().empty else int(lag.min())),
        "lag_days_after_public_median": (None if lag.dropna().empty else float(lag.median())),
        "lag_days_after_public_max": (None if lag.dropna().empty else int(lag.max())),
        "lag_days_after_quarter_end_min": (None if qend_lag.dropna().empty
                                           else int(qend_lag.min())),
        "tolerance_days": HOLDER_MAX_STALE_DAYS,
        "note": ("as-of BACKWARD on quarter_end+45d. A lag below 45 days after the "
                 "report quarter end would be look-ahead; it REFUSES rather than "
                 "reports."),
    }
    if qend_lag.dropna().size and int(qend_lag.min()) < FILING_LAG_DAYS:
        raise SystemExit(
            f"REFUSED: a 13F row was joined {int(qend_lag.min())} days after its "
            f"report quarter end, inside the {FILING_LAG_DAYS}-day statutory "
            "window. That is look-ahead.")

    # ---- IBES analyst identity: an exact (permno, month) join. `month` is the
    #      IBES statpers month and the panel only used targets announced BEFORE
    #      that month started, so the join needs no tolerance.
    a = analyst.copy()
    a["permno"] = a["permno"].astype(out["permno"].dtype)
    out = out.merge(a, on=["permno", "month"], how="left")
    diag["analyst_join"] = {
        "rows": int(len(out)),
        "matched": int(out["a_n_live_targets"].notna().sum()),
        "match_rate": round(float(out["a_n_live_targets"].notna().mean()), 4),
        "note": ("the grades parquet holds only targets whose 12m outcome could be "
                 "graded (anndats <= 2023-12), so an unmatched row is a name whose "
                 "covering analysts have no GRADED history -- not a name without "
                 "coverage. 2024 rows therefore thin out by construction and the "
                 "receipt reports the per-year match rate."),
    }
    out["_yr"] = out["month"].str.slice(0, 4)
    diag["analyst_join"]["match_rate_by_year"] = (
        out.groupby("_yr")["a_n_live_targets"].apply(
            lambda s: round(float(s.notna().mean()), 3)).to_dict())
    diag["holder_join"]["match_rate_by_year"] = (
        out.groupby("_yr")["h_n_holders"].apply(
            lambda s: round(float(s.notna().mean()), 3)).to_dict())
    out = out.drop(columns=["_yr"])

    # ---- analyst family, derived columns
    out["a_upside_bias_corrected"] = out["upside"] - out["a_bias_mean"]
    out["a_implied_vs_upside"] = out["a_implied_mean"] - out["upside"]
    out["a_rev_accel"] = out["target_rev_1m"] - out["target_rev_3m"] / 3.0
    cov = out["coverage"].astype("float64")
    out["a_thin_cov"] = (cov <= THIN_COVERAGE).astype("float64").where(cov.notna())
    out["a_very_thin_cov"] = (cov <= VERY_THIN_COVERAGE).astype("float64").where(cov.notna())
    out["a_cov_thinness"] = 1.0 / (1.0 + cov)
    out["a_bias_mean_xs"] = out.groupby("month")["a_bias_mean"].rank(pct=True)

    # ---- interactions. Both legs standardised WITHIN the month, so the product
    #      is a genuine interaction and not a scale artefact of either leg.
    mo = out["month"]
    z_add = _z(out["h_net_entry_frac"], mo)
    z_exit = _z(out["h_exit_frac"], mo)
    z_new = _z(out["h_new_frac"], mo)
    z_newlong = _z(out["h_new_longdur_frac"], mo)
    z_anom = _z(out["h_stake_anom_mean"], mo)
    z_spec = _z(out["h_specialist_frac"], mo)
    z_rev = _z(out["target_rev_1m"], mo)
    z_bias = _z(out["a_bias_mean"], mo)
    z_up = _z(out["upside"], mo)
    thin = out["a_thin_cov"]
    sgn6 = np.sign(out["ret_6m"])

    out["x_holder_add_x_rev"] = z_add * z_rev
    out["x_exit_x_rev_down"] = z_exit * (-z_rev)
    out["x_holder_anom_x_thincov"] = z_anom * thin
    out["x_holder_add_x_thincov"] = z_add * thin
    out["x_specialist_x_thincov"] = z_spec * thin
    out["x_new13f_x_ret6m_sign"] = z_new * sgn6
    out["x_newlongdur_x_ret6m_sign"] = z_newlong * sgn6
    out["x_bias_x_upside"] = z_bias * z_up
    out["x_bias_x_thincov"] = z_bias * thin

    diag["nonnull_share"] = {c: round(float(out[c].notna().mean()), 4)
                             for c in all_ext_features()}
    return out, diag


# --------------------------------------------------------------------- io

def load_or_build(rebuild: bool = False,
                  verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    diag: dict = {"features_ext_version": FEATURES_EXT_VERSION}
    if rebuild or not HOLDER_PANEL.exists():
        h, hd = build_holder_panel(verbose=verbose)
        HOLDER_PANEL.parent.mkdir(parents=True, exist_ok=True)
        h.to_parquet(HOLDER_PANEL, index=False)
        diag["holder_build"] = hd
    else:
        h = pd.read_parquet(HOLDER_PANEL)
        diag["holder_build"] = {"cached": str(HOLDER_PANEL), "rows": int(len(h))}
    if rebuild or not ANALYST_PANEL.exists():
        a, ad = build_analyst_panel(verbose=verbose)
        a.to_parquet(ANALYST_PANEL, index=False)
        diag["analyst_build"] = ad
    else:
        a = pd.read_parquet(ANALYST_PANEL)
        diag["analyst_build"] = {"cached": str(ANALYST_PANEL), "rows": int(len(a))}
    return h, a, diag


def describe() -> dict:
    return {
        "version": FEATURES_EXT_VERSION,
        "families": {k: list(v) for k, v in FAMILIES.items()},
        "ablation_sets": [{"name": n, "families": list(f)} for n, f in ABLATION_SETS],
        "pit": {
            "13f_public_date": "quarter_end(max(rdate, latest Thomson vintage)) + 45 calendar days",
            "13f_join": f"as-of backward on entry_date, tolerance {HOLDER_MAX_STALE_DAYS}d",
            "ibes_bias": "expanding mean of errors RESOLVED (anndats+365d) before the month began",
            "ibes_live": "targets announced strictly BEFORE the month started, within 12 months",
            "standardisation": "within-month only",
        },
        "thin_coverage": {
            "thin": THIN_COVERAGE, "very_thin": VERY_THIN_COVERAGE,
            "source": ("ibes_status_rules_2013_2024.json coverage buckets: BUY basket "
                       "t 2.355 (1-3), 2.060 (4-10), 1.573 (11-25), 0.189 (26+)")},
        "not_built": {
            "sentiment_novelty_attention": (
                "NOT built. T12 measured that only 7.7% of corpus news is a new dated "
                "fact, and Benzinga's 390:1 coverage ratio makes 'requires news' a "
                "mega-cap filter. A standalone sentiment feature would re-run a "
                "closed negative."),
            "analyst_accuracy_weighting": (
                "NOT built. Accuracy does not persist (Spearman 0.087), so weighting "
                "a consensus by past accuracy is a design the receipt already kills."),
            "13f_short_side": "13F is longs-only; no short-interest feature exists here.",
            "active_passive_split": (
                "NOT observable in entitled WRDS (idea doc 4a); every filer statement "
                "is a blended index+active statement."),
        },
        "known_data_caveats": {
            "sic_9999_is_unknown_not_an_industry": (
                "A sibling session measured that 22.5% of the training panel's rows "
                "(99,334/441,278) carry CRSP siccd 9999, which is NONCLASSIFIABLE and "
                "is mislabelled 'Public Administration' in the shared sector mapping. "
                "No feature in THIS module conditions on the panel's `sector` column. "
                "The one place it touches SIC at all is indirect: `h_specialist_frac` "
                "and `x_specialist_x_thincov` read `sector_entropy` from "
                "`holder_fingerprints.parquet`, which is a filer-level entropy over "
                "CRSP SIC-2 codes -- so a filer concentrated in the 99 bucket reads as "
                "'concentrated' when it is in fact concentrated in UNKNOWN. That "
                "inflates the specialist flag for such filers and is a reason to read "
                "the specialist features as noisier than the rest of the holder "
                "family, not as a sector claim. The shared mapping is not edited here; "
                "the central fix is queued elsewhere."),
        },
        "licence": "PRODUCT_EXPERIMENT",
    }


__all__ = [
    "FEATURES_EXT_VERSION", "HOLDER_FEATURES", "ANALYST_FEATURES",
    "INTERACTION_FEATURES", "FAMILIES", "ABLATION_SETS", "family_of",
    "all_ext_features", "columns_for", "build_holder_panel",
    "build_analyst_panel", "attach", "load_or_build", "describe",
]
