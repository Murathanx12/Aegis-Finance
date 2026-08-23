"""OVERNIGHT vs INTRADAY decomposition on the CRSP daily panel (1990-2024).

WHY THIS SCRIPT EXISTS
======================
A viral claim: "buy MU at the close, sell at the open, since 1990 you'd be up
138 billion percent; do the opposite and you'd be down 99.2%." The claim is
socially sourced and the number is not evidence. The *phenomenon* has real
literature behind it (Cooper/Cliff/Gulen 2008; Berkman et al. 2012; Lou/Polk/
Skouras 2019; Bogousslavsky 2019), so the claim is a LEAD, not a truth.

This script answers it with the PIT-clean CRSP panel already on disk, and -- the
part the viral version never does -- prices the round trip. A close-to-open
strategy trades TWICE EVERY SESSION. At 252 sessions a year even a 5 bps
one-way cost is ~25%/yr of drag, so the decomposition is only interesting if the
gross spread survives a cost that large.

DEFINITIONS (cfacpr-adjusted; CRSP stores bid/ask averages as NEGATIVE prices,
so every price is |p| and non-positive prices are dropped rather than imputed)

    r_overnight(t) = (openprc_t / cfacpr_t) / (prc_{t-1} / cfacpr_{t-1}) - 1
    r_intraday(t)  = prc_t / openprc_t - 1            (same day: cfacpr cancels)

RECONCILIATION is the honesty check: (1+r_on)(1+r_id) - 1 must equal CRSP's own
`retx` (close-to-close, ex-dividend). If it does not, the decomposition is
wrong and nothing downstream means anything. The script REFUSES rather than
reports when reconciliation fails.

n_effective is the number of DATES, not the number of stock-days (CANON section
58): we form the equal-weighted cross-sectional mean each session and t-stat the
time series of those means with Newey-West. 50M stock-days do not buy 50M
independent observations.

Usage:
    python -m scripts.overnight_intraday_study --stage panel
    python -m scripts.overnight_intraday_study --stage analyse
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
OUT = REPO / "backend" / "data" / "optimus" / "overnight_study"
PANEL = OUT / "panel"

MU_PERMNO = 53613

#: Common stock on the three major exchanges. Anything else (ADRs, closed-end
#: funds, non-US issues) is a different animal and pooling it in would make the
#: result a statement about a universe nobody trades.
SHRCD = (10, 11)
EXCHCD = (1, 2, 3)

#: Reconciliation tolerance. CRSP `retx` and a price ratio agree to rounding on
#: clean rows; 2e-4 is loose enough for stored-price rounding and tight enough
#: that a real adjustment error (a missed split) blows straight through it.
RECON_TOL = 2e-4
RECON_MAX_FAIL_FRAC = 0.005


def _names() -> pd.DataFrame:
    n = pd.read_parquet(WRDS / "bulk" / "crsp__dsenames.parquet",
                        columns=["permno", "namedt", "nameendt", "shrcd",
                                 "exchcd"])
    n["namedt"] = pd.to_datetime(n["namedt"])
    n["nameendt"] = pd.to_datetime(n["nameendt"])
    return n


def _eligible_mask(df: pd.DataFrame, names: pd.DataFrame) -> np.ndarray:
    """Share-code / exchange eligibility AS OF each row's own date.

    A single permno changes share code and exchange over its life, so a
    permno-level filter would apply 2024's status to 1994's rows. The join is
    on the name-record interval that CONTAINS the date.
    """
    m = df[["permno", "date"]].reset_index(drop=True)
    m["_row"] = np.arange(len(m))
    j = m.merge(names, on="permno", how="inner")
    live = (j["date"] >= j["namedt"]) & (j["date"] <= j["nameendt"])
    j = j[live]
    ok = j["shrcd"].isin(SHRCD) & j["exchcd"].isin(EXCHCD)
    good = np.zeros(len(m), dtype=bool)
    good[j.loc[ok, "_row"].to_numpy()] = True
    return good


def build_panel() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    PANEL.mkdir(parents=True, exist_ok=True)
    names = _names()
    files = sorted(WRDS.glob("crsp_dsf_*.parquet"))
    if not files:
        sys.exit("REFUSED: no crsp_dsf_*.parquet on disk")

    cols = ["permno", "date", "prc", "retx", "vol", "shrout", "openprc",
            "cfacpr"]

    # The pre-2013 CRSP years on disk were pulled with a NARROW column set
    # (permno, date, prc, ret, vol) to save transfer, so they carry no
    # `openprc` and this decomposition is undefined on them. That is a
    # DECLARED window limit, not a silent one: the viral claim is about 1990
    # onward and we can only speak for the years we actually hold open prices
    # for. `scripts/pull_crsp_open_prices.py` closes the gap.
    import pyarrow.parquet as _pq
    usable, skipped = [], []
    for f in files:
        have = set(_pq.read_schema(f).names)
        (usable if {"openprc", "cfacpr", "retx"} <= have else skipped).append(f)
    if not usable:
        sys.exit("REFUSED: no CRSP year on disk carries openprc/cfacpr/retx. "
                 "Run scripts/pull_crsp_open_prices.py first.")
    skipped_years = [int(f.stem.split("_")[-1]) for f in skipped]
    files = usable

    recon_rows, recon_fail, n_rows_total = 0, 0, 0
    max_abs_err = 0.0
    prev_tail: pd.DataFrame | None = None

    for f in files:
        yr = int(f.stem.split("_")[-1])
        raw = pd.read_parquet(f, columns=cols)
        raw["date"] = pd.to_datetime(raw["date"])

        d = raw if prev_tail is None else pd.concat([prev_tail, raw],
                                                    ignore_index=True)
        d = d.sort_values(["permno", "date"], kind="mergesort")

        d["prc"] = d["prc"].abs()
        d["openprc"] = d["openprc"].abs()
        d.loc[d["prc"] <= 0, "prc"] = np.nan
        d.loc[d["openprc"] <= 0, "openprc"] = np.nan
        d.loc[d["cfacpr"] <= 0, "cfacpr"] = np.nan

        d["adj_close"] = d["prc"] / d["cfacpr"]
        g = d.groupby("permno", sort=False)
        d["prev_adj_close"] = g["adj_close"].shift(1)
        d["prev_date"] = g["date"].shift(1)
        d["prev_prc"] = g["prc"].shift(1)

        # A gap longer than a week is a halt or a relisting, not an overnight.
        gap_days = (d["date"] - d["prev_date"]).dt.days
        d.loc[gap_days > 7, ["prev_adj_close", "prev_prc"]] = np.nan

        d["r_on"] = (d["openprc"] / d["cfacpr"]) / d["prev_adj_close"] - 1.0
        d["r_id"] = d["prc"] / d["openprc"] - 1.0

        d = d[(d["date"].dt.year == yr) & d["r_on"].notna()
              & d["r_id"].notna()].copy()
        d = d[_eligible_mask(d, names)].copy()

        if len(d):
            cc = (1 + d["r_on"]) * (1 + d["r_id"]) - 1
            err = (cc - d["retx"]).abs()
            ok = d["retx"].notna()
            recon_rows += int(ok.sum())
            recon_fail += int((err[ok] > RECON_TOL).sum())
            if ok.any():
                max_abs_err = max(max_abs_err, float(err[ok].max()))

        d["mktcap"] = d["prc"] * d["shrout"]          # $ thousands
        d["dolvol"] = d["prc"] * d["vol"]
        out = d[["permno", "date", "r_on", "r_id", "retx", "prev_prc",
                 "mktcap", "dolvol"]].copy()
        for c in ("r_on", "r_id", "retx", "prev_prc", "mktcap", "dolvol"):
            out[c] = out[c].astype("float32")
        out.to_parquet(PANEL / f"on_id_{yr}.parquet", index=False)
        n_rows_total += len(out)
        print(f"  {yr}: {len(out):>9,} stock-days", flush=True)

        last = raw["date"].max()
        prev_tail = raw[raw["date"] == last].copy()

    fail_frac = recon_fail / recon_rows if recon_rows else 1.0
    receipt = {
        "n_stock_days": n_rows_total,
        "recon_rows": recon_rows,
        "recon_fail": recon_fail,
        "recon_fail_frac": round(fail_frac, 6),
        "recon_max_abs_err": round(max_abs_err, 6),
        "recon_tol": RECON_TOL,
        "years": [int(f.stem.split("_")[-1]) for f in files],
        "years_skipped_no_openprc": skipped_years,
        "window_limit": (
            "The claim under test is stated 'since 1990'. This panel can only "
            "speak for the years holding open prices. Years listed in "
            "years_skipped_no_openprc are NOT evidence of absence -- they are "
            "absence of evidence, and any verdict must be scoped to the "
            "covered window." if skipped_years else None),
        "universe": {"shrcd": list(SHRCD), "exchcd": list(EXCHCD)},
    }
    (OUT / "panel_receipt.json").write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))
    if fail_frac > RECON_MAX_FAIL_FRAC:
        sys.exit(f"REFUSED: reconciliation failed on {fail_frac:.2%} of rows "
                 f"(tolerance {RECON_MAX_FAIL_FRAC:.2%}). The decomposition "
                 f"does not reproduce CRSP retx; nothing downstream is valid.")
    print("Reconciliation PASSED.")


# ---------------------------------------------------------------- analysis


def _nw_tstat(x: np.ndarray, lags: int = 5) -> float:
    """Newey-West t-stat of the mean of a daily series."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 30:
        return float("nan")
    mu = x.mean()
    e = x - mu
    var = (e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        w = 1.0 - L / (lags + 1.0)
        var += 2.0 * w * (e[L:] @ e[:-L]) / n
    if var <= 0:
        return float("nan")
    return float(mu / np.sqrt(var / n))


def _load_panel() -> pd.DataFrame:
    files = sorted(PANEL.glob("on_id_*.parquet"))
    if not files:
        sys.exit("REFUSED: panel not built. Run --stage panel first.")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _series_stats(daily: pd.Series, label: str) -> dict:
    v = daily.dropna().to_numpy(dtype=float)
    if len(v) == 0:
        return {"label": label, "n_days": 0}
    ann = float(np.expm1(np.log1p(v).sum() * 252.0 / len(v)))
    return {
        "label": label,
        "n_days": int(len(v)),
        "mean_bps_per_day": round(float(v.mean()) * 1e4, 3),
        "t_stat_nw": round(_nw_tstat(v), 2),
        "ann_geometric_pct": round(ann * 100, 2),
        "daily_vol_bps": round(float(v.std()) * 1e4, 1),
    }


def _mu_case(df: pd.DataFrame) -> dict:
    m = df[df["permno"] == MU_PERMNO].sort_values("date")
    if m.empty:
        return {"error": "MU (permno 53613) absent from panel"}
    on = np.log1p(m["r_on"].astype(float).to_numpy())
    idy = np.log1p(m["r_id"].astype(float).to_numpy())
    fin = np.isfinite(on) & np.isfinite(idy)
    on, idy = on[fin], idy[fin]

    def _growth(logsum: float) -> float:
        # Report in log10 because the viral claim's own number overflows any
        # sane percentage scale; a "138 billion percent" is 10**11.14.
        return float(logsum / np.log(10.0))

    return {
        "permno": MU_PERMNO,
        "ticker": "MU",
        "n_days": int(len(on)),
        "first_date": str(m["date"].min().date()),
        "last_date": str(m["date"].max().date()),
        "overnight_log10_growth": round(_growth(on.sum()), 3),
        "intraday_log10_growth": round(_growth(idy.sum()), 3),
        "close_to_close_log10_growth": round(_growth(on.sum() + idy.sum()), 3),
        "overnight_total_pct": (round(float(np.expm1(on.sum())) * 100, 1)
                                if on.sum() < 30 else "overflow: see log10"),
        "intraday_total_pct": round(float(np.expm1(idy.sum())) * 100, 4),
        "overnight_mean_bps": round(float(np.expm1(on).mean()) * 1e4, 2),
        "intraday_mean_bps": round(float(np.expm1(idy).mean()) * 1e4, 2),
        "overnight_t_nw": round(_nw_tstat(np.expm1(on)), 2),
        "intraday_t_nw": round(_nw_tstat(np.expm1(idy)), 2),
    }


def _breakeven_cost(daily_mean: float) -> dict:
    """A close-to-open book pays a round trip EVERY session.

    The strategy buys at t-1's close and sells at t's open: two executions per
    session. So the per-session gross edge must exceed 2 x one-way cost. This
    is the number the viral version never states.
    """
    one_way_bps = daily_mean * 1e4 / 2.0
    return {
        "gross_mean_bps_per_session": round(daily_mean * 1e4, 3),
        "breakeven_one_way_cost_bps": round(one_way_bps, 3),
        "note": ("two executions per session; the strategy is only live if "
                 "realistic one-way cost (spread/2 + impact) is below this"),
    }


def analyse() -> None:
    df = _load_panel()
    df["date"] = pd.to_datetime(df["date"])
    print(f"panel: {len(df):,} stock-days, "
          f"{df['date'].nunique():,} sessions, "
          f"{df['permno'].nunique():,} permnos", flush=True)

    res: dict = {
        "panel": {
            "n_stock_days": int(len(df)),
            "n_sessions": int(df["date"].nunique()),
            "n_permnos": int(df["permno"].nunique()),
            "first_date": str(df["date"].min().date()),
            "last_date": str(df["date"].max().date()),
        },
        "mu_case": _mu_case(df),
    }

    # ---- universe-wide, equal weighted, one observation per SESSION
    def ew(frame: pd.DataFrame, col: str) -> pd.Series:
        return frame.groupby("date")[col].mean()

    res["universe_all"] = {
        "overnight": _series_stats(ew(df, "r_on"), "EW overnight, all"),
        "intraday": _series_stats(ew(df, "r_id"), "EW intraday, all"),
        "spread": _series_stats(ew(df, "r_on") - ew(df, "r_id"),
                                "EW overnight minus intraday, all"),
    }

    # ---- the penny-stock question: the anomaly literature's usual confound
    liquid = df[df["prev_prc"] >= 5.0]
    res["universe_price_ge_5"] = {
        "n_stock_days": int(len(liquid)),
        "overnight": _series_stats(ew(liquid, "r_on"), "EW overnight, >=$5"),
        "intraday": _series_stats(ew(liquid, "r_id"), "EW intraday, >=$5"),
        "spread": _series_stats(ew(liquid, "r_on") - ew(liquid, "r_id"),
                                "EW spread, >=$5"),
    }

    # ---- conditional: size quintile (cross-sectional, per session)
    d5 = liquid.copy()
    d5["size_q"] = d5.groupby("date")["mktcap"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False,
                          duplicates="drop"))
    by_size = {}
    for q in sorted(d5["size_q"].dropna().unique()):
        sub = d5[d5["size_q"] == q]
        by_size[f"q{int(q) + 1}"] = {
            "overnight": _series_stats(ew(sub, "r_on"), f"on q{int(q) + 1}"),
            "intraday": _series_stats(ew(sub, "r_id"), f"id q{int(q) + 1}"),
        }
    res["by_size_quintile_price_ge_5"] = {
        "note": "q1 = smallest, q5 = largest, ranked cross-sectionally each "
                "session among price>=$5 names",
        "quintiles": by_size,
    }

    # ---- conditional: dollar-volume quintile (the liquidity axis)
    d5["dv_q"] = d5.groupby("date")["dolvol"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False,
                          duplicates="drop"))
    by_dv = {}
    for q in sorted(d5["dv_q"].dropna().unique()):
        sub = d5[d5["dv_q"] == q]
        by_dv[f"q{int(q) + 1}"] = {
            "overnight": _series_stats(ew(sub, "r_on"), f"on dv{int(q) + 1}"),
            "intraday": _series_stats(ew(sub, "r_id"), f"id dv{int(q) + 1}"),
        }
    res["by_dollar_volume_quintile"] = {
        "note": "q1 = least traded, q5 = most traded",
        "quintiles": by_dv,
    }

    # ---- era stability: is this a 1990s fact or a live one?
    eras = {}
    for lo, hi in ((1990, 1999), (2000, 2009), (2010, 2017), (2018, 2024)):
        sub = liquid[(liquid["date"].dt.year >= lo)
                     & (liquid["date"].dt.year <= hi)]
        if sub.empty:
            continue
        eras[f"{lo}-{hi}"] = {
            "overnight": _series_stats(ew(sub, "r_on"), f"on {lo}-{hi}"),
            "intraday": _series_stats(ew(sub, "r_id"), f"id {lo}-{hi}"),
        }
    res["by_era_price_ge_5"] = eras

    # ---- the cost verdict, on the most tradable slice we have
    big = d5[d5["dv_q"] == d5["dv_q"].max()]
    on_big = ew(big, "r_on").dropna()
    res["cost_verdict_most_liquid_quintile"] = _breakeven_cost(
        float(on_big.mean()))
    res["cost_verdict_most_liquid_quintile"]["n_sessions"] = int(len(on_big))
    res["cost_verdict_most_liquid_quintile"]["t_stat_nw"] = round(
        _nw_tstat(on_big.to_numpy()), 2)

    # ---- THE DECISION. A statistic is not a strategy. Three books on the
    # most-liquid quintile (the only slice where execution is even arguable),
    # each priced across a cost grid. `overnight_only` pays a round trip EVERY
    # session; `buy_hold` pays essentially nothing. If overnight-only does not
    # beat buy-and-hold on the declared utility AFTER costs, the anomaly is
    # real and unspendable -- which is this programme's most common finding
    # (CANON: risk resolves faster than return; a real effect is not an edge).
    on_q5 = ew(big, "r_on").dropna()
    id_q5 = ew(big, "r_id").dropna()
    idx = on_q5.index.intersection(id_q5.index)
    on_v = on_q5.loc[idx].to_numpy(dtype=float)
    id_v = id_q5.loc[idx].to_numpy(dtype=float)
    cc_v = (1 + on_v) * (1 + id_v) - 1

    def _book(daily: np.ndarray, round_trips_per_session: float,
              cost_bps_one_way: float) -> dict:
        drag = 2.0 * round_trips_per_session * cost_bps_one_way / 1e4 / 2.0
        # 2 executions per round trip; `drag` is per-session total cost.
        drag = round_trips_per_session * 2.0 * (cost_bps_one_way / 1e4)
        net = daily - drag
        ann = float(np.expm1(np.log1p(np.clip(net, -0.99, None)).sum()
                             * 252.0 / len(net)))
        sharpe = (float(net.mean()) / float(net.std()) * np.sqrt(252.0)
                  if net.std() > 0 else float("nan"))
        return {"ann_geometric_pct": round(ann * 100, 2),
                "sharpe": round(sharpe, 2),
                "mean_bps_per_session": round(float(net.mean()) * 1e4, 3)}

    grid = {}
    for c in (0.0, 1.0, 2.0, 5.0, 10.0):
        grid[f"{c:g}bps_one_way"] = {
            # buy at yesterday's close, sell at today's open: 1 round trip/session
            "overnight_only": _book(on_v, 1.0, c),
            # hold through the day only: 1 round trip/session
            "intraday_only": _book(id_v, 1.0, c),
            # buy once and hold: cost is amortised to ~0 per session
            "buy_and_hold": _book(cc_v, 0.0, c),
        }
    res["strategy_net_of_costs_most_liquid_quintile"] = {
        "n_sessions": int(len(idx)),
        "universe": "top dollar-volume quintile among price>=$5 common stock",
        "weighting": "equal weight, rebalanced every session",
        "caveat": ("EW over ~600 names rebalanced twice daily. Cost here is a "
                   "flat per-execution bps and does NOT model the market "
                   "impact of demanding that much liquidity in the opening "
                   "auction, so every net number is an UPPER bound."),
        "grid": grid,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage",
                    choices=["panel", "analyse", "earnings", "both"],
                    default="both")
    a = ap.parse_args()
    if a.stage in ("panel", "both"):
        build_panel()
    if a.stage in ("analyse", "both"):
        analyse()
    if a.stage == "earnings":
        analyse_earnings()




# ------------------------------------------------- the earnings-gap slice


def _earnings_gap_dates() -> pd.DataFrame:
    """(permno, date) pairs whose OVERNIGHT gap could contain an earnings call.

    `rdq` is Compustat's report date with no time of day, so a report stamped
    day D was announced either before D's open or after D's close. Both
    readings are kept: the gaps that could contain it are D's overnight and
    D+1's overnight (mapped to the next trading session in each case). Being
    deliberately generous here is the conservative choice -- it can only DILUTE
    a real earnings effect toward the non-earnings baseline, never manufacture
    one.
    """
    fundq = pd.read_parquet(WRDS / "compustat_fundq.parquet",
                            columns=["gvkey", "rdq"]).dropna(subset=["rdq"])
    fundq["rdq"] = pd.to_datetime(fundq["rdq"])
    fundq = fundq.drop_duplicates()

    link = pd.read_parquet(WRDS / "bulk" / "crsp__ccmxpf_lnkhist.parquet")
    # LC/LU are the researched, unambiguous links; P/C are primary issues.
    link = link[link["linktype"].isin(["LC", "LU"])
                & link["linkprim"].isin(["P", "C"])].copy()
    link["linkdt"] = pd.to_datetime(link["linkdt"])
    link["linkenddt"] = pd.to_datetime(link["linkenddt"]).fillna(
        pd.Timestamp("2099-12-31"))

    m = fundq.merge(link, on="gvkey", how="inner")
    m = m[(m["rdq"] >= m["linkdt"]) & (m["rdq"] <= m["linkenddt"])]
    m = m[["lpermno", "rdq"]].rename(columns={"lpermno": "permno"})
    m["permno"] = m["permno"].astype("int64")
    return m.dropna().drop_duplicates()


def analyse_earnings() -> None:
    df = _load_panel()
    df["date"] = pd.to_datetime(df["date"])
    ann = _earnings_gap_dates()

    sessions = pd.Index(sorted(df["date"].unique()))
    # Map each rdq to the NEXT trading session (>= rdq): that session's
    # overnight gap is the first one that could carry the news.
    pos = sessions.searchsorted(ann["rdq"].to_numpy(), side="left")
    ok = pos < len(sessions)
    ann = ann[ok].copy()
    ann["s0"] = sessions[pos[ok]]
    # ...and the session after it, for a report released after that close.
    pos1 = np.minimum(pos[ok] + 1, len(sessions) - 1)
    ann["s1"] = sessions[pos1]

    flag = pd.concat([
        ann[["permno", "s0"]].rename(columns={"s0": "date"}),
        ann[["permno", "s1"]].rename(columns={"s1": "date"}),
    ]).drop_duplicates()
    flag["is_earnings_gap"] = True

    df = df.merge(flag, on=["permno", "date"], how="left")
    df["is_earnings_gap"] = df["is_earnings_gap"].fillna(False)

    liquid = df[df["prev_prc"] >= 5.0]

    def ew(frame, col):
        return frame.groupby("date")[col].mean()

    res = {
        "n_stock_days": int(len(df)),
        "n_earnings_gap_stock_days": int(df["is_earnings_gap"].sum()),
        "share_earnings_gap": round(float(df["is_earnings_gap"].mean()), 5),
        "definition": ("an overnight gap is flagged when a Compustat rdq maps "
                       "to that session or the one before it; rdq has no time "
                       "of day, so both readings are kept"),
    }
    for label, frame in (("all", df), ("price_ge_5", liquid)):
        e = frame[frame["is_earnings_gap"]]
        n = frame[~frame["is_earnings_gap"]]
        res[label] = {
            "earnings_gap": {
                "overnight": _series_stats(ew(e, "r_on"), "on|earnings"),
                "intraday": _series_stats(ew(e, "r_id"), "id|earnings"),
                "n_stock_days": int(len(e)),
            },
            "no_earnings": {
                "overnight": _series_stats(ew(n, "r_on"), "on|no earnings"),
                "intraday": _series_stats(ew(n, "r_id"), "id|no earnings"),
                "n_stock_days": int(len(n)),
            },
        }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "earnings_results.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
