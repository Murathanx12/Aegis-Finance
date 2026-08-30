"""Do the tracker's status rules survive OUT OF SAMPLE, on the whole US market?

    python -m scripts.tracker_ibes_backtest --run
    python -m scripts.tracker_ibes_backtest --run --start 2013 --end 2024 --cost-bps 10

THE QUESTION, AND WHY IT IS NOT ANSWERABLE IN THE OTHER REPO
===========================================================
`aegis-alpha-terminal` grades `murat_rule_v1` against a base rate measured on a
152-name news panel over ELEVEN DATE BLOCKS, in sample. The tracker it now
selects from holds several thousand names and is one day old, so it cannot
produce a base rate of its own: a forward rate needs forward returns and there
are none yet.

IBES can. `ibes__ptgsum` carries consensus PRICE TARGETS and `ibes__recdsum`
carries recommendation counts, both monthly, both point-in-time, for the whole
US market from 2013. Joined to CRSP daily prices that is eleven years of the
same screen on names nobody curated -- which is the only instrument that can
answer Murat's two hypotheses:

    "thin coverage has more upside"     -> split every result by coverage bucket
    "do not buy last year's winner"     -> split every result by past_winner

THE SCALE TRAP, NAMED BECAUSE IT WOULD NOT LOOK LIKE AN ERROR
=============================================================
IBES `meanrec` runs 1 = STRONG BUY to 5 = STRONG SELL. The tracker's consensus
runs 5 = STRONG BUY, matching Murat's ">= 4.1 / 5". They are the same numbers
in opposite order, so applying a `>= 4.1` bar to raw `meanrec` would select the
most HATED decile of the market and would produce a perfectly clean-looking
backtest of the opposite strategy. The conversion is `6 - meanrec` and it is
asserted by a test below before anything else runs.

THE RULES ARE IMPORTED, NEVER RETYPED
=====================================
`alpha/tracker.py` lives in the other repository and is loaded here BY PATH.
Re-implementing the thresholds in this file would guarantee that the two drift,
and a test of thresholds nobody runs live is not an out-of-sample test of
anything. The module's sha256 goes in the receipt so the result names the exact
version of the rules it tested.

WHAT THIS TEST CANNOT DO, STATED UP FRONT
=========================================
* **Clause (d), the dated catalyst, is not readable here.** IBES carries no
  event calendar, so `days_to_catalyst` is None for every row and STRONG_BUY --
  which asserts a catalyst -- can never fire. What is tested is the BUY bar,
  which has no catalyst clause. This is a real limit on scope, not a silent
  approximation: the receipt says `strong_buy_testable: false`.
* **Monthly, not daily.** IBES summary is a monthly cut, so the basket
  rebalances monthly and holds one month. A rule that only works intra-month is
  invisible here.
* Costs are charged on measured TURNOVER, both sides, and are never zero.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
BULK = WRDS / "bulk"
OUT = REPO / "backend" / "data" / "optimus" / "tracker_backtest"

#: The other repository. The rules live there and are imported, not copied.
TERMINAL = Path(r"C:\Users\mrthn\aegis-alpha-terminal")
TRACKER_PY = TERMINAL / "alpha" / "tracker.py"

#: CRSP share codes 10 and 11 are US COMMON STOCK. Everything else -- ADRs,
#: closed-end funds, REITs with other codes, units -- is a different instrument
#: and the tracker's live universe (Alpaca US equities, non-ETF) does not hold
#: them either.
SHRCD_COMMON = (10, 11)
#: NYSE / AMEX / NASDAQ.
EXCHCD_MAIN = (1, 2, 3)

#: One side, in basis points. Charged on measured turnover, both sides. The
#: farm's `Policy` REFUSES a zero-cost run unless it is declared a diagnostic,
#: and the same rule applies here.
DEFAULT_COST_BPS = 10.0

#: SIC division -> the sector label `past_winner` groups on. Coarse on purpose:
#: the live tracker groups on Finnhub's industry string, which is coarser than
#: a 4-digit SIC and finer than a 1-digit division. What matters for the test is
#: that names are compared against LIKE names and that thin groups fall back to
#: the market, which the imported rule already handles.
SIC_DIVISIONS = (
    (1, 999, "Agriculture"), (1000, 1499, "Mining"), (1500, 1799, "Construction"),
    (2000, 3999, "Manufacturing"), (4000, 4999, "Transport & Utilities"),
    (5000, 5199, "Wholesale"), (5200, 5999, "Retail"),
    (6000, 6799, "Finance & Real Estate"), (7000, 8999, "Services"),
    (9000, 9999, "Public Administration"),
)


def sic_division(siccd) -> str:
    try:
        s = int(siccd)
    except (TypeError, ValueError):
        return "_UNKNOWN"
    for lo, hi, name in SIC_DIVISIONS:
        if lo <= s <= hi:
            return name
    return "_UNKNOWN"


# --------------------------------------------------------------- the rules

def load_tracker_rules():
    """Import `alpha/tracker.py` from the terminal repo. (module, sha256).

    REFUSES rather than falling back to a local copy. A backtest that silently
    tested a stale duplicate of the rules would be worse than no backtest: it
    would carry the authority of an out-of-sample result while measuring
    something that is not running anywhere.
    """
    if not TRACKER_PY.exists():
        raise SystemExit(
            f"REFUSED: {TRACKER_PY} not found. The status rules live in the terminal repo "
            "and are imported, never retyped -- a second copy would drift and this test "
            "would stop testing what actually runs.")
    sha = hashlib.sha256(TRACKER_PY.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location("_aat_tracker", TRACKER_PY)
    mod = importlib.util.module_from_spec(spec)
    # `alpha.tracker.consensus_score` delegates to `alpha.analyst_targets`; make
    # the terminal repo importable so that delegation resolves.
    if str(TERMINAL) not in sys.path:
        sys.path.insert(0, str(TERMINAL))
    # `@dataclass` resolves its own module's namespace through `sys.modules`, so
    # a module loaded by path must be registered there BEFORE it is executed --
    # otherwise the decorator dereferences None on the first dataclass it meets.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod, sha


def assert_scale_conversion(T) -> None:
    """IBES 1=best -> tracker 5=best. Checked BEFORE anything is measured.

    If this is wrong every number downstream is a clean backtest of the
    opposite strategy, which is the failure that does not announce itself.
    """
    strong_buy_ibes, strong_sell_ibes = 1.0, 5.0
    assert 6.0 - strong_buy_ibes == 5.0, "IBES 1 (strong buy) must map to 5"
    assert 6.0 - strong_sell_ibes == 1.0, "IBES 5 (strong sell) must map to 1"
    # and the bar must select the bullish end on the converted scale
    assert (6.0 - strong_buy_ibes) >= T.BUY_CONSENSUS
    assert (6.0 - strong_sell_ibes) < T.SELL_CONSENSUS


# ----------------------------------------------------------------- the data

def load_names() -> pd.DataFrame:
    """permno <-> ncusip with validity dates, share code, exchange, SIC."""
    df = pd.read_parquet(BULK / "crsp__stocknames.parquet",
                         columns=["permno", "namedt", "nameenddt", "shrcd", "exchcd",
                                  "siccd", "ncusip"])
    df = df[df["ncusip"].notna() & (df["ncusip"] != "")]
    df = df[df["shrcd"].isin(SHRCD_COMMON) & df["exchcd"].isin(EXCHCD_MAIN)]
    for c in ("namedt", "nameenddt"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["sector"] = df["siccd"].map(sic_division)
    return df.dropna(subset=["namedt", "nameenddt"])


def load_ibes(start: int, end: int) -> pd.DataFrame:
    """Consensus targets joined to recommendation counts, monthly, US firms."""
    ptg = pd.read_parquet(BULK / "ibes__ptgsum.parquet",
                          columns=["cusip", "statpers", "meanptg", "numest", "usfirm",
                                   "measure", "curr"])
    ptg = ptg[(ptg["usfirm"] == 1) & (ptg["measure"] == "PTG")]
    ptg = ptg[ptg["curr"].isin(["USD"]) | ptg["curr"].isna()]
    ptg["statpers"] = pd.to_datetime(ptg["statpers"])
    ptg = ptg[(ptg["statpers"].dt.year >= start) & (ptg["statpers"].dt.year <= end)]

    rec = pd.read_parquet(BULK / "ibes__recdsum.parquet",
                          columns=["cusip", "statpers", "meanrec", "numrec", "usfirm"])
    rec = rec[rec["usfirm"] == 1]
    rec["statpers"] = pd.to_datetime(rec["statpers"])
    rec = rec[(rec["statpers"].dt.year >= start) & (rec["statpers"].dt.year <= end)]

    df = ptg.merge(rec, on=["cusip", "statpers"], how="inner", suffixes=("", "_r"))
    df = df[df["meanptg"].notna() & (df["meanptg"] > 0) & df["meanrec"].notna()]
    # THE CONVERSION. IBES 1 = strong buy; the tracker's scale is 5 = strong buy.
    df["consensus"] = 6.0 - df["meanrec"]
    df["coverage"] = df["numrec"].fillna(0).astype(int)
    return df[["cusip", "statpers", "meanptg", "numest", "consensus", "coverage"]]


def load_prices(start: int, end: int) -> pd.DataFrame:
    """Daily CRSP closes, one year per file. `prc` is negated for bid/ask means."""
    frames = []
    for year in range(start - 1, end + 1):        # one extra year for ret_12m
        f = WRDS / f"crsp_dsf_{year}.parquet"
        if not f.exists():
            continue
        d = pd.read_parquet(f, columns=["permno", "date", "prc", "ret", "cfacpr"])
        frames.append(d)
    if not frames:
        raise SystemExit("REFUSED: no CRSP daily files found for that range.")
    px = pd.concat(frames, ignore_index=True)
    px["date"] = pd.to_datetime(px["date"])
    # A NEGATIVE `prc` is CRSP's flag for "no trade; this is the bid/ask
    # average". It is a real price estimate and dropping it would delete
    # exactly the illiquid names Murat wants in the universe, so take abs()
    # and keep the row -- and never let the sign reach a return calculation.
    px["prc"] = px["prc"].abs()
    px = px[px["prc"].notna() & (px["prc"] > 0)]
    px["ret"] = pd.to_numeric(px["ret"], errors="coerce")
    # SPLIT ADJUSTMENT, and why the first version of this file was wrong.
    #
    # Every price-derived quantity must be adjusted. Run on RAW `prc`, a 1-for-10
    # REVERSE split reads as +900% and a 2-for-1 forward split reads as -50%:
    # the upside is unbounded and the downside floors at -100%, so the asymmetry
    # biases every cross-sectional mean upward. It is not a small effect in this
    # universe -- reverse splits are common in exactly the thin, beaten-down
    # names the screen selects. The first run of this script reported a 42% CAGR
    # "equal weighted market" and an 831x basket, both of which were that
    # artefact and neither of which is a return anyone could have earned.
    #
    # `cfacpr` is CRSP's cumulative price adjustment factor: `prc / cfacpr` is a
    # split-consistent series. `ret` is CRSP's own total return, already net of
    # splits and inclusive of dividends and of the delisting return where one
    # exists, so REALISED performance is compounded from `ret` and never from a
    # price ratio.
    cf = px["cfacpr"].where(px["cfacpr"].notna() & (px["cfacpr"] != 0), 1.0)
    px["adj_prc"] = px["prc"] / cf
    return px.sort_values(["permno", "date"])


def price_panel(px: pd.DataFrame) -> pd.DataFrame:
    """Per (permno, date): raw close, adjusted 60-session high, 12m total return.

    `prc` stays RAW because the analyst target is quoted in today's dollars and
    `meanptg / prc` is the ratio a desk would actually see. Everything that
    compares a price to its own past -- the 60-day high, the twelve-month
    return -- uses the ADJUSTED series, and realised performance uses the
    total-return index.
    """
    px = px.copy()
    g = px.groupby("permno", sort=False)
    px["high_60d"] = g["adj_prc"].transform(lambda s: s.rolling(60, min_periods=20).max())
    px["adj_252"] = g["adj_prc"].transform(lambda s: s.shift(252))
    px["ret_12m"] = px["adj_prc"] / px["adj_252"] - 1.0
    # Total-return index: dividends in, splits out, delisting return included.
    px["tri"] = g["ret"].transform(lambda s: (1.0 + s.fillna(0.0)).cumprod())
    # Did the share basis change in the prior year? `cfacpr` moves only on a
    # split or similar adjustment. A stale IBES target across such a change
    # makes `meanptg / prc` meaningless, so the share of affected rows is
    # reported beside every upside band rather than cleaned out of it.
    cf252 = g["cfacpr"].transform(lambda s: s.shift(252))
    px["split_prior_year"] = (px["cfacpr"] != cf252) & cf252.notna()
    return px


# ------------------------------------------------------------------ the run

def build_monthly(start: int, end: int, lag_days: int) -> pd.DataFrame:
    """One row per (name, month) with every column the status rules read."""
    names = load_names()
    ibes = load_ibes(start, end)
    print(f"  IBES rows with BOTH a target and a rating: {len(ibes):,}")

    # cusip -> permno, valid AT statpers (a cusip is reassigned over time)
    ibes = ibes.merge(names[["permno", "ncusip", "namedt", "nameenddt", "sector"]],
                      left_on="cusip", right_on="ncusip", how="inner")
    ibes = ibes[(ibes["statpers"] >= ibes["namedt"]) & (ibes["statpers"] <= ibes["nameenddt"])]
    print(f"  linked to a CRSP common-stock permno valid that month: {len(ibes):,}")

    px = price_panel(load_prices(start, end))
    print(f"  CRSP daily rows: {len(px):,}")

    # PIT: trade at the first close STRICTLY AFTER statpers + lag. The IBES cut
    # is dated statpers but is not on a desk that morning; using statpers itself
    # would buy at a price set before the number existed.
    ibes = ibes.sort_values("statpers")
    ibes["tradable_from"] = ibes["statpers"] + pd.Timedelta(days=lag_days)
    px = px.sort_values("date")
    merged = pd.merge_asof(
        ibes, px[["permno", "date", "prc", "adj_prc", "high_60d", "ret_12m", "tri",
                  "split_prior_year"]],
        left_on="tradable_from", right_on="date", by="permno",
        direction="forward", tolerance=pd.Timedelta(days=7))
    merged = merged[merged["prc"].notna()]
    print(f"  with a tradable close within 7 days of the cut: {len(merged):,}")

    # forward one-month return: the next month's entry price for the same name
    merged = merged.sort_values(["permno", "statpers"])
    merged["tri_next"] = merged.groupby("permno", sort=False)["tri"].shift(-1)
    merged["statpers_next"] = merged.groupby("permno", sort=False)["statpers"].shift(-1)
    gap = (merged["statpers_next"] - merged["statpers"]).dt.days
    # A gap far from one month is a name that left the panel and came back; its
    # "one-month" return would silently be a one-year return.
    merged = merged[(gap >= 20) & (gap <= 45)]
    # From the TOTAL RETURN INDEX, never from a price ratio: splits out,
    # dividends in, delisting return included.
    merged["fwd_1m"] = merged["tri_next"] / merged["tri"] - 1.0
    merged = merged[merged["fwd_1m"].notna()]
    merged["month"] = merged["statpers"].dt.to_period("M").astype(str)
    print(f"  with a forward one-month return: {len(merged):,}")
    return merged


def label(df: pd.DataFrame, T) -> pd.DataFrame:
    """Apply the IMPORTED status rules, month by month, cross-sectionally."""
    out = []
    for month, chunk in df.groupby("month", sort=True):
        rows = [{
            "symbol": int(r.permno), "close": float(r.prc),
            "adj_close": float(r.adj_prc),
            "high_60d": float(r.high_60d) if pd.notna(r.high_60d) else None,
            "ret_12m": float(r.ret_12m) if pd.notna(r.ret_12m) else None,
            "sector": r.sector,
            "mean_target": float(r.meanptg),
            "consensus": float(r.consensus),
            "coverage": int(r.coverage),
            # IBES carries no event calendar: clause (d) is UNREADABLE, not
            # failed. STRONG_BUY asserts a catalyst so it cannot fire here.
            "days_to_catalyst": None,
            "tradable": True,
            "fwd_1m": float(r.fwd_1m), "month": month,
            "split_prior_year": bool(r.split_prior_year),
        } for r in chunk.itertuples()]
        for row in rows:
            row["upside"] = T.upside(row["mean_target"], row["close"])
            # drawdown compares a price to its OWN past: both legs adjusted.
            row["drawdown_60d"] = T.drawdown_60d(row["adj_close"], row["high_60d"])
            row["coverage_bucket"] = T.coverage_bucket(row["coverage"])
        T.mark_past_winners(rows)             # per-month cross-section, never pooled
        T.apply_status(rows)                  # no `prev`: HOLD needs history, BUY does not
        out.extend(rows)
    return pd.DataFrame(out)


def wealth(monthly_returns: pd.Series) -> dict:
    r = monthly_returns.dropna()
    if r.empty:
        return {"months": 0}
    terminal = float((1.0 + r).prod())
    yrs = len(r) / 12.0
    return {
        "months": int(len(r)),
        "terminal_wealth": round(terminal, 4),
        "cagr": round(terminal ** (1 / yrs) - 1.0, 4) if yrs > 0 and terminal > 0 else None,
        "mean_monthly": round(float(r.mean()), 5),
        "vol_monthly": round(float(r.std()), 5),
        "hit_rate": round(float((r > 0).mean()), 4),
        "worst_month": round(float(r.min()), 4),
        "t_stat": (round(float(r.mean() / (r.std() / np.sqrt(len(r)))), 3)
                   if r.std() > 0 else None),
    }


def basket(df: pd.DataFrame, mask: pd.Series, cost_bps: float) -> dict:
    """Equal-weighted monthly basket over the masked names, net of turnover cost."""
    sel = df[mask]
    if sel.empty:
        return {"months": 0, "note": "no names ever selected"}
    per_month = sel.groupby("month")["fwd_1m"].mean()
    holdings = sel.groupby("month")["symbol"].apply(set)

    # TURNOVER, MEASURED. A monthly basket that keeps most of its names does not
    # pay a full round trip; asserting 100% turnover would overstate the cost as
    # badly as asserting zero would understate it.
    turnovers, prev = [], None
    for m in holdings.index:
        cur = holdings.loc[m]
        turnovers.append(1.0 if prev is None
                         else len(cur - prev) / max(1, len(cur)))
        prev = cur
    turnover = pd.Series(turnovers, index=holdings.index)
    cost = turnover * (cost_bps / 10_000.0) * 2.0        # both sides
    net = per_month - cost.reindex(per_month.index).fillna(0.0)

    out = wealth(net)
    out["gross"] = wealth(per_month)
    out["mean_names_per_month"] = round(float(sel.groupby("month").size().mean()), 1)
    out["mean_turnover"] = round(float(turnover.mean()), 3)
    out["cost_bps_per_side"] = cost_bps
    return out


def paired_vs_market(df: pd.DataFrame, mask: pd.Series, market: pd.Series,
                     cost_bps: float) -> dict:
    """The DECISIVE test: the monthly spread (basket - market), paired by month.

    Comparing two terminal wealths is not a test -- both are one draw of a
    correlated pair, and the market's own t over this window is only 1.7. The
    paired difference removes the shared market factor and asks the question
    that actually matters: better than WHAT, month by month.
    """
    sel = df[mask]
    if sel.empty:
        return {"months": 0}
    per_month = sel.groupby("month")["fwd_1m"].mean()
    holdings = sel.groupby("month")["symbol"].apply(set)
    turnovers, prev = [], None
    for m in holdings.index:
        cur = holdings.loc[m]
        turnovers.append(1.0 if prev is None else len(cur - prev) / max(1, len(cur)))
        prev = cur
    cost = pd.Series(turnovers, index=holdings.index) * (cost_bps / 10_000.0) * 2.0
    net = per_month - cost.reindex(per_month.index).fillna(0.0)
    spread = (net - market.reindex(net.index)).dropna()
    if spread.empty:
        return {"months": 0}
    t = float(spread.mean() / (spread.std() / np.sqrt(len(spread)))) if spread.std() > 0 else None
    return {
        "months": int(len(spread)),
        "mean_monthly_excess": round(float(spread.mean()), 5),
        "annualised_excess": round(float(spread.mean()) * 12, 4),
        "t_stat_paired": round(t, 3) if t is not None else None,
        "months_beating_market": round(float((spread > 0).mean()), 4),
    }


def quintile_shape(df: pd.DataFrame, column: str, market: pd.Series,
                   cost_bps: float, n_bins: int = 5) -> dict:
    """Sort the WHOLE universe by one column each month and grade every bin.

    ASK THE CROSS SECTION FIRST. A rule that takes the top of a column is only
    sensible if that column is monotone in the right direction. If the bottom
    bin beats the top, the screen is inverted and no threshold on it can help;
    if the shape is flat, the column carries nothing and the threshold is
    ceremony. Bins are cut PER MONTH -- a full-sample quantile would be
    lookahead.
    """
    d = df[df[column].notna()].copy()
    if d.empty:
        return {}
    d["_bin"] = d.groupby("month")[column].transform(
        lambda s: pd.qcut(s.rank(method="first"), n_bins, labels=False, duplicates="drop"))
    out = {}
    for b in sorted(x for x in d["_bin"].dropna().unique()):
        m = d["_bin"] == b
        sub = d[m]
        per_month = sub.groupby("month")["fwd_1m"].mean()
        spread = (per_month - market.reindex(per_month.index)).dropna()
        t = (float(spread.mean() / (spread.std() / np.sqrt(len(spread))))
             if len(spread) > 1 and spread.std() > 0 else None)
        out[f"Q{int(b)+1}"] = {
            "mean_value": round(float(sub[column].mean()), 4),
            "name_months": int(m.sum()),
            "gross_wealth": wealth(per_month).get("terminal_wealth"),
            "annualised_excess_vs_market": round(float(spread.mean()) * 12, 4),
            "t_stat_paired": round(t, 3) if t is not None else None,
        }
    return out


#: Absolute upside bands. Quintiles say WHERE the top of the column is; these
#: say what the LIVE BAR actually buys. `BUY_UPSIDE` is 0.30 and
#: `STRONG_BUY_UPSIDE` is 0.50, so the rule lives entirely inside the last four
#: bands and the question is which of them carry the damage.
UPSIDE_BANDS = ((-9.9, 0.0), (0.0, 0.15), (0.15, 0.30), (0.30, 0.50),
                (0.50, 1.00), (1.00, 2.00), (2.00, 4.00), (4.00, 1e9))


def upside_bands(df: pd.DataFrame, market: pd.Series) -> dict:
    """Grade every absolute upside band against the market, paired by month.

    WHY THIS AND NOT ONLY QUINTILES. A quintile is relative -- "the top 20% of
    whatever was on offer that month" -- and it moves as the market's optimism
    moves. The rule is written in ABSOLUTE terms (`upside >= 0.30`), so the
    only cut that tells us what the rule buys is an absolute one.

    THE SPLIT CAVEAT, WHICH THIS CANNOT FULLY REMOVE. `meanptg` is a consensus
    target in the dollars of whenever it was set; `prc` is today's raw price.
    If a split falls between the two, the ratio is meaningless -- a 1-for-10
    reverse split leaves a stale target a tenth of the new price, and a forward
    split leaves it a multiple. Those land in the extreme bands. So a band is
    reported with the SHARE of its rows that saw a split in the prior year,
    which is what separates "the rule buys bad names" from "the rule buys a
    measurement error". Flagged and counted, never dropped.
    """
    out = {}
    for lo, hi in UPSIDE_BANDS:
        m = (df["upside"] >= lo) & (df["upside"] < hi)
        sub = df[m]
        if len(sub) < 500:
            continue
        per_month = sub.groupby("month")["fwd_1m"].mean()
        spread = (per_month - market.reindex(per_month.index)).dropna()
        if len(spread) < 12:
            continue
        t = (float(spread.mean() / (spread.std() / np.sqrt(len(spread))))
             if spread.std() > 0 else None)
        label_ = f"{lo:+.0%} to {hi:+.0%}" if hi < 1e8 else f"{lo:+.0%}+"
        out[label_] = {
            "name_months": int(m.sum()),
            "median_upside": round(float(sub["upside"].median()), 4),
            "annualised_excess_vs_market": round(float(spread.mean()) * 12, 4),
            "t_stat_paired": round(t, 3) if t is not None else None,
            "months_beating_market": round(float((spread > 0).mean()), 4),
            "split_in_prior_year_share": (round(float(sub["split_prior_year"].mean()), 4)
                                          if "split_prior_year" in sub else None),
        }
    return out


def run(start: int, end: int, cost_bps: float, lag_days: int) -> int:
    T, sha = load_tracker_rules()
    assert_scale_conversion(T)
    print(f"rules: {TRACKER_PY} sha256 {sha[:16]}")
    print(f"  BUY bar: upside >= {T.BUY_UPSIDE:.0%}, consensus >= {T.BUY_CONSENSUS} "
          f"(IBES meanrec <= {6 - T.BUY_CONSENSUS:.1f}), not a past winner")

    print(f"\nbuilding the monthly panel {start}-{end} ...")
    panel = build_monthly(start, end, lag_days)
    print("\nlabelling with the imported rules ...")
    lab = label(panel, T)
    print(f"  {len(lab):,} name-months labelled")

    hist = lab["status"].value_counts().to_dict()
    print(f"  statuses: {hist}")

    market = lab.groupby("month")["fwd_1m"].mean()
    is_cand = lab["status"].isin(T.CANDIDATE_STATUSES)

    report = {
        "generated": date.today().isoformat(),
        "window": f"{start}-{end}", "cost_bps_per_side": cost_bps,
        "ibes_lag_days": lag_days,
        "tracker_py_sha256": sha,
        "thresholds": {"BUY_UPSIDE": T.BUY_UPSIDE, "BUY_CONSENSUS": T.BUY_CONSENSUS,
                       "PAST_WINNER_ABSOLUTE_RETURN": T.PAST_WINNER_ABSOLUTE_RETURN,
                       "PAST_WINNER_SECTOR_DECILE": T.PAST_WINNER_SECTOR_DECILE},
        "strong_buy_testable": False,
        "strong_buy_note": ("IBES carries no event calendar, so clause (d) is UNREADABLE and "
                            "STRONG_BUY -- which asserts a dated catalyst -- cannot fire. What "
                            "is tested below is the BUY bar, which has no catalyst clause."),
        "name_months": int(len(lab)),
        "status_histogram": {k: int(v) for k, v in hist.items()},
        "market_equal_weighted": wealth(market),
        "buy_basket": basket(lab, is_cand, cost_bps),
    }

    # -- Murat's hypothesis 1: does thin coverage behave differently? ------
    by_cov = {}
    for b in [x[0] for x in T.COVERAGE_BUCKETS]:
        m = is_cand & (lab["coverage_bucket"] == b)
        if m.sum() == 0:
            continue
        by_cov[b] = basket(lab, m, cost_bps)
        by_cov[b]["name_months"] = int(m.sum())
    report["buy_basket_by_coverage_bucket"] = by_cov

    # -- Murat's hypothesis 2: is excluding past winners the right call? ---
    # The BUY rule already excludes them, so the counterfactual is the basket
    # that would have been bought WITHOUT clause (f).
    # ONE CHANGE AT A TIME. `relaxed` must carry the SAME upside cap as the live
    # rule, otherwise the comparison confounds clause (f) with the cap and hands
    # the cap's benefit to the past-winner exclusion. The only difference
    # between `buy_basket` and this is `past_winner`.
    relaxed = ((lab["upside"] >= T.BUY_UPSIDE)
               & (lab["upside"] < T.UPSIDE_IMPLAUSIBLE_AT)
               & (lab["consensus"] >= T.BUY_CONSENSUS))
    report["buy_without_clause_f"] = basket(lab, relaxed, cost_bps)
    report["past_winners_only"] = basket(lab, relaxed & (lab["past_winner"] == True), cost_bps)  # noqa: E712
    # THE DECISIVE TESTS -- paired, and the cross-sectional shape.
    report["paired_vs_market"] = {
        "buy_basket": paired_vs_market(lab, is_cand, market, cost_bps),
        "buy_without_clause_f": paired_vs_market(lab, relaxed, market, cost_bps),
        "past_winners_only": paired_vs_market(
            lab, relaxed & (lab["past_winner"] == True), market, cost_bps),  # noqa: E712
        "note": ("terminal wealth alone compares two correlated single draws; the market's own "
                 "t over this window is 1.72. The paired monthly spread removes the shared "
                 "market factor and is the number that decides."),
    }
    report["cross_section_shape"] = {
        "upside": quintile_shape(lab, "upside", market, cost_bps),
        "consensus": quintile_shape(lab, "consensus", market, cost_bps),
        "ret_12m": quintile_shape(lab, "ret_12m", market, cost_bps),
        "note": ("every name sorted into per-month quintiles by one column, each bin graded "
                 "against the market. A threshold on a column is only sensible if the column "
                 "is monotone in the direction the rule assumes."),
    }
    # THE VARIANT THE BANDS POINT AT. `UPSIDE_IMPLAUSIBLE_AT` already exists in
    # the tracker as a FLAG; the bands say whether it should also be a BAR.
    lab["year_tmp"] = lab["month"].str[:4].astype(int)
    capped = is_cand & (lab["upside"] < T.UPSIDE_IMPLAUSIBLE_AT)
    report["buy_basket_with_upside_cap"] = basket(lab, capped, cost_bps)
    report["paired_buy_with_upside_cap"] = paired_vs_market(lab, capped, market, cost_bps)
    report["upside_cap_used"] = T.UPSIDE_IMPLAUSIBLE_AT
    report["excluded_by_cap_name_months"] = int((is_cand & ~capped).sum())
    # IS THE CAP A PLATEAU OR A KNIFE EDGE? A threshold that only works at one
    # value is a fitted parameter wearing a rule's clothes. `UPSIDE_IMPLAUSIBLE_AT`
    # was in the code BEFORE this data was looked at, which is the honest defence
    # of the level -- but the sensitivity is what shows whether the level matters.
    report["upside_cap_sensitivity"] = {}
    for cap in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 10.0, 100.0):
        m = is_cand & (lab["upside"] < cap)
        if m.sum() < 1000:
            continue
        report["upside_cap_sensitivity"][f"<{cap:g}x"] = {
            "name_months": int(m.sum()),
            **paired_vs_market(lab, m, market, cost_bps)}
    # and the capped rule, era by era, never pooled
    report["capped_by_era"] = {}
    for lo, hi in ((2013, 2016), (2017, 2020), (2021, 2024)):
        m = capped & lab["year_tmp"].between(lo, hi) if "year_tmp" in lab else None
        if m is None:
            continue
        if m.sum() == 0:
            continue
        report["capped_by_era"][f"{lo}-{hi}"] = paired_vs_market(lab, m, market, cost_bps)
    # DOES CONCENTRATION HELP? The basket above holds every candidate -- ~416
    # names. The live books hold 5 to 15. That is a different portfolio and it
    # has to be tested as one: the farm's standing result is that breadth raised
    # terminal wealth in EVERY row and that concentration is a return decision,
    # not a risk preference. Top-k is taken by upside, the only ranking that
    # exists in both this panel and the live book.
    report["top_k_by_upside"] = {}
    ranked = lab[capped].copy()
    ranked["rk"] = ranked.groupby("month")["upside"].rank(ascending=False, method="first")
    for k in (5, 10, 15, 25, 50, 100, 250):
        idx = ranked[ranked["rk"] <= k].index
        m = pd.Series(False, index=lab.index)
        m.loc[idx] = True
        if m.sum() < 200:
            continue
        report["top_k_by_upside"][f"top{k}"] = {
            "name_months": int(m.sum()),
            "wealth": basket(lab, m, cost_bps).get("terminal_wealth"),
            **paired_vs_market(lab, m, market, cost_bps)}
    report["upside_bands"] = upside_bands(lab, market)
    report["upside_bands_note"] = (
        "the quintiles say where the top of the column is; these say what the LIVE BAR buys. "
        f"BUY_UPSIDE is {T.BUY_UPSIDE:.0%} and STRONG_BUY_UPSIDE is {T.STRONG_BUY_UPSIDE:.0%}, "
        "so the rule lives entirely in the upper bands. `split_in_prior_year_share` separates "
        "'the rule buys bad names' from 'the rule buys a stale target across a split'.")
    report["buy_basket_note"] = (
        "`buy_basket` applies clause (f); `buy_without_clause_f` is the same screen with the "
        "past-winner exclusion removed. The DIFFERENCE between them is what clause (f) bought "
        "or cost -- which is the only way to answer 'do not buy last year's winner' rather "
        "than assume it.")

    # -- by decade / era, never pooled ------------------------------------
    lab["year"] = lab["month"].str[:4].astype(int)
    eras = {}
    for lo, hi in ((2013, 2016), (2017, 2020), (2021, 2024)):
        m = is_cand & lab["year"].between(lo, hi)
        em = lab["year"].between(lo, hi)
        if m.sum() == 0:
            continue
        eras[f"{lo}-{hi}"] = {"buy": basket(lab, m, cost_bps),
                              "market": wealth(lab[em].groupby("month")["fwd_1m"].mean())}
    report["by_era"] = eras

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"ibes_status_rules_{start}_{end}.json"
    path.write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")

    _print(report)
    print(f"\nreceipt -> {path}")
    return 0


def _print(rep: dict) -> None:
    def line(name, d):
        if not d or not d.get("months"):
            print(f"  {name:28s} -- no months --")
            return
        print(f"  {name:28s} wealth {d['terminal_wealth']:>8.3f}  CAGR "
              f"{(d['cagr'] or 0):>7.2%}  hit {d['hit_rate']:>5.1%}  t {str(d['t_stat']):>7s}  "
              f"n/mo {d.get('mean_names_per_month','--')}")

    print("\n" + "=" * 78)
    print(f"TRACKER STATUS RULES ON IBES + CRSP, {rep['window']}, "
          f"costs {rep['cost_bps_per_side']}bps/side")
    print("=" * 78)
    print(f"{rep['name_months']:,} name-months. STRONG_BUY not testable here "
          f"(no event calendar).")
    print("\nHEADLINE")
    line("market (equal weighted)", rep["market_equal_weighted"])
    line("BUY basket (net)", rep["buy_basket"])
    print("\nHYPOTHESIS 1 -- does thin coverage behave differently?")
    for b, d in rep["buy_basket_by_coverage_bucket"].items():
        line(f"  coverage {b}", d)
    print("\nHYPOTHESIS 2 -- is 'do not buy the past winner' right?")
    line("BUY with clause (f)", rep["buy_basket"])
    line("BUY without clause (f)", rep["buy_without_clause_f"])
    line("past winners only", rep["past_winners_only"])
    print("\nBY ERA (never pooled)")
    for era, d in rep["by_era"].items():
        line(f"  {era} BUY", d["buy"])
        line(f"  {era} market", d["market"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS,
                    help="one side, in basis points, charged on measured turnover")
    ap.add_argument("--lag-days", type=int, default=1,
                    help="calendar days after the IBES cut before the basket may trade")
    a = ap.parse_args(argv)
    if a.cost_bps <= 0:
        raise SystemExit("REFUSED: a zero-cost run is a diagnostic, not a result. "
                         "The farm's Policy refuses one and so does this.")
    if not a.run:
        ap.print_help()
        return 0
    return run(a.start, a.end, a.cost_bps, a.lag_days)


if __name__ == "__main__":
    sys.exit(main())
