"""TOP-N mega-cap concentration vs the S&P-500 proxy, on local CRSP daily data.

CLAIM UNDER TEST (Murat, 2026-09-02)
    "Holding the S&P top 1 / top 3 / top 5 / top 10 stocks works better than
     holding the S&P 500 itself, in the long term."

This is a diagnostic under the PRODUCT_EXPERIMENT licence (CLAUDE.md): no
transaction costs, no taxes, no significance gate. It is a REGIME question, so
the era table is the headline, not the full-sample number.

DESIGN (pre-registered in the receipt header before any number was computed)
  Universe proxy for "the S&P 500": at each month-end, the 500 largest US
  common-stock COMPANIES (permco) by market cap, restricted to CRSP share
  codes 10/11 and exchanges NYSE/AMEX/NASDAQ (exchcd 1/2/3), using the
  stocknames name-range valid at that month-end.

  Market cap is aggregated to the COMPANY (permco), summing share classes, so
  Alphabet A+C and Berkshire A+B rank as one company. Each company's monthly
  return is the value-weighted return of its own share classes.

  TOPn: at each month-end select the n largest companies, hold value-weighted
  for the next calendar month. Benchmarks: TOP500 value-weighted (the S&P
  proxy) and TOP500 equal-weighted (second line).

  Returns come from CRSP `ret` (total return, dividends + split adjusted),
  compounded within the month. Prices are NEVER differenced across days.

  Objective is TERMINAL WEALTH (house rule: rank on terminal wealth, not the
  mean monthly return).

LIMITATIONS, stated up front
  - No transaction costs, no taxes, no bid-ask. TOP1..TOP10 turn over far more
    than a 500-name index, so the net gap is smaller than the gross gap here.
  - No CRSP delisting returns (we hold daily `dsf` only). A name that vanishes
    mid-month contributes only the days it traded. Immaterial for mega caps,
    which leave by merger, not by delisting to zero.
  - Missing daily `ret` is treated as 0.0 for that day (counted in the receipt).
  - "Top 500 by cap" is a PROXY for S&P 500 membership. The real index is a
    committee's choice and lags cap; the proxy has no lag. This biases the
    benchmark UP slightly (it holds the newly-huge name immediately), which
    makes the TOPn advantage a conservative estimate.

Usage
    python -m scripts.topn_concentration_backtest --start 1993 --end 2024
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260902
REPO = Path(__file__).resolve().parents[1]
WRDS = REPO / "backend" / "data" / "optimus" / "wrds"
STOCKNAMES = WRDS / "bulk" / "crsp_a_stock__stocknames.parquet"
OUT = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "topn_concentration.json"

SHRCD_KEEP = (10, 11)          # US common stock
EXCHCD_KEEP = (1, 2, 3)        # NYSE, AMEX, NASDAQ
TOPNS = (1, 3, 5, 10)
# The concentration grid exists because terminal wealth need not be MONOTONE in n.
# If TOPn wins only at one n, that is a ridge (luck), not a plateau (mechanism).
GRID_NS = (1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 50, 100, 200)
BENCH_N = 500

ERAS = {
    "1993-1999_late_90s": (1993, 1999),
    "2000-2012_lost_decade": (2000, 2012),
    "2013-2019_megacap_era": (2013, 2019),
    "2020-2024_covid_to_ai": (2020, 2024),
}


# ----------------------------------------------------------------- data layer
def load_names() -> pd.DataFrame:
    sn = pd.read_parquet(
        STOCKNAMES,
        columns=["permno", "namedt", "nameenddt", "shrcd", "exchcd",
                 "ticker", "comnam", "permco"],
    )
    sn["namedt"] = pd.to_datetime(sn["namedt"])
    sn["nameenddt"] = pd.to_datetime(sn["nameenddt"])
    return sn.sort_values(["permno", "namedt"]).reset_index(drop=True)


def names_asof(sn: pd.DataFrame, when: pd.Timestamp) -> pd.DataFrame:
    """The name row valid at `when`, one per permno, already screened."""
    m = (sn["namedt"] <= when) & (sn["nameenddt"] >= when)
    row = sn.loc[m].drop_duplicates("permno", keep="last")
    return row[row["shrcd"].isin(SHRCD_KEEP) & row["exchcd"].isin(EXCHCD_KEEP)]


def monthly_from_year(year: int) -> tuple[pd.DataFrame, dict]:
    """Per permno per month: month-end market cap and the month's total return.

    Market cap uses the LAST trading day of the month (the observation a
    rebalancer standing at the close of month t actually has).
    """
    path = WRDS / f"crsp_dsf_{year}.parquet"
    df = pd.read_parquet(path, columns=["permno", "date", "prc", "ret", "shrout"])
    df["date"] = pd.to_datetime(df["date"])
    df["ym"] = df["date"].values.astype("datetime64[M]")

    n_ret_nan = int(df["ret"].isna().sum())
    n_rows = int(len(df))
    df["ret"] = df["ret"].fillna(0.0)

    # month return: compound daily total returns
    df["gross"] = 1.0 + df["ret"]
    mret = df.groupby(["permno", "ym"], sort=False)["gross"].prod() - 1.0

    # month-end cap: abs(prc) * shrout on the permno's last trading day of month
    last = df.sort_values("date").groupby(["permno", "ym"], sort=False).tail(1)
    last = last.assign(
        mktcap=last["prc"].abs() * last["shrout"],   # shrout is in thousands -> $k
        me_date=last["date"],
    )
    cap = last.set_index(["permno", "ym"])[["mktcap", "me_date"]]

    out = cap.join(mret.rename("ret_m"), how="outer").reset_index()
    out = out[out["mktcap"].notna() | out["ret_m"].notna()]
    diag = {"year": year, "daily_rows": n_rows, "daily_ret_nan": n_ret_nan}
    return out, diag


def build_panel(start: int, end: int) -> tuple[pd.DataFrame, list[dict]]:
    frames, diags = [], []
    for y in range(start, end + 1):
        f, d = monthly_from_year(y)
        frames.append(f)
        diags.append(d)
    panel = pd.concat(frames, ignore_index=True)
    return panel, diags


# ------------------------------------------------------------ portfolio layer
def company_month_table(panel: pd.DataFrame, sn: pd.DataFrame) -> pd.DataFrame:
    """One row per (permco, month): cap at month end, and that month's VW return."""
    rows = []
    for ym, g in panel.groupby("ym", sort=True):
        nm = names_asof(sn, pd.Timestamp(ym) + pd.offsets.MonthEnd(0))
        g = g.merge(nm[["permno", "permco", "ticker", "comnam"]], on="permno", how="inner")
        g = g[g["mktcap"].notna() & (g["mktcap"] > 0)]
        if g.empty:
            continue
        g["ret_m"] = g["ret_m"].fillna(0.0)
        g["num"] = g["mktcap"] * g["ret_m"]
        agg = g.groupby("permco", sort=False).agg(
            mktcap=("mktcap", "sum"), num=("num", "sum"), n_classes=("permno", "size"),
        )
        agg["ret_m"] = agg["num"] / agg["mktcap"]
        # label from the LARGEST share class of the company
        big = g.sort_values("mktcap").drop_duplicates("permco", keep="last")
        agg = agg.join(big.set_index("permco")[["ticker", "comnam"]])
        agg = agg.rename(columns={"comnam": "label"}).drop(columns=["num"])
        agg["ym"] = pd.Timestamp(ym)
        rows.append(agg.reset_index())
    tab = pd.concat(rows, ignore_index=True)
    tab["mktcap"] = tab["mktcap"].astype(float)
    tab["ret_m"] = tab["ret_m"].astype(float)
    return tab


def run_strategies(tab: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Select at month-end t on cap; earn month t+1's return. Returns monthly series."""
    months = sorted(tab["ym"].unique())
    by_month = {m: g for m, g in tab.groupby("ym", sort=False)}

    recs, holdings = [], {n: [] for n in TOPNS}
    for i in range(len(months) - 1):
        t, t1 = months[i], months[i + 1]
        sel_pool = by_month[t].sort_values("mktcap", ascending=False)
        nxt = by_month[t1].set_index("permco")["ret_m"]

        row = {"ym_selected": t, "ym_earned": t1}
        universe = sel_pool.head(BENCH_N)
        for n in sorted(set(TOPNS) | set(GRID_NS) | {BENCH_N}):
            picks = sel_pool.head(n).copy()
            picks["r"] = picks["permco"].map(nxt)
            live = picks[picks["r"].notna()]
            if live.empty:
                row[f"top{n}_vw"] = np.nan
                continue
            w = live["mktcap"] / live["mktcap"].sum()
            row[f"top{n}_vw"] = float((w * live["r"]).sum())
            if n in TOPNS:
                holdings[n].append({
                    "ym": str(pd.Timestamp(t).date()),
                    "names": list(zip(live["ticker"].fillna("?"), live["label"])),
                })
        ubench = universe.copy()
        ubench["r"] = ubench["permco"].map(nxt)
        ubench = ubench[ubench["r"].notna()]
        row["top500_ew"] = float(ubench["r"].mean())
        row["n_universe"] = int(len(universe))
        recs.append(row)

    ser = pd.DataFrame(recs)
    ser["year"] = pd.to_datetime(ser["ym_earned"]).dt.year
    return ser, holdings


# ---------------------------------------------------------------- metric layer
def metrics(r: pd.Series, years: pd.Series) -> dict:
    r = r.dropna()
    if r.empty:
        return {}
    wealth = float((1.0 + r).prod())
    n_months = len(r)
    yrs = n_months / 12.0
    cagr = wealth ** (1.0 / yrs) - 1.0
    vol = float(r.std(ddof=1) * np.sqrt(12))
    curve = (1.0 + r).cumprod()
    dd = float((curve / curve.cummax() - 1.0).min())
    yr = (1.0 + r).groupby(years.loc[r.index]).prod() - 1.0
    return {
        "terminal_wealth_multiple": round(wealth, 4),
        "cagr": round(cagr, 6),
        "ann_vol": round(vol, 6),
        "max_drawdown_monthly": round(dd, 6),
        "worst_calendar_year": {"year": int(yr.idxmin()), "return": round(float(yr.min()), 6)},
        "best_calendar_year": {"year": int(yr.idxmax()), "return": round(float(yr.max()), 6)},
        "n_months": n_months,
        "sharpe_excess_of_zero": round(float(cagr / vol), 4) if vol else None,
    }


def buy_and_hold(tab: pd.DataFrame, n: int) -> dict:
    """Buy the top n companies at the first month-end and NEVER rebalance."""
    months = sorted(tab["ym"].unique())
    first = tab[tab["ym"] == months[0]].sort_values("mktcap", ascending=False).head(n)
    w0 = (first["mktcap"] / first["mktcap"].sum()).values
    permcos = first["permco"].values
    labels = list(first["ticker"].fillna("?"))
    ret_map = tab.set_index(["permco", "ym"])["ret_m"]

    wealth = dict(zip(permcos, w0))
    alive_last = {p: months[0] for p in permcos}
    for m in months[1:]:
        for p in permcos:
            r = ret_map.get((p, m), np.nan)
            if pd.notna(r):
                wealth[p] *= (1.0 + float(r))
                alive_last[p] = m
    total = float(sum(wealth.values()))
    yrs = (len(months) - 1) / 12.0
    return {
        "terminal_wealth_multiple": round(total, 4),
        "cagr": round(total ** (1.0 / yrs) - 1.0, 6),
        "initial_names": labels,
        "per_name_multiple": {labels[i]: round(float(wealth[permcos[i]] / w0[i]), 3)
                              for i in range(n)},
        "last_month_with_data": {labels[i]: str(pd.Timestamp(alive_last[permcos[i]]).date())
                                 for i in range(n)},
        "note": "a name whose CRSP data ends early is held FLAT thereafter (cash at 0%); "
                "mega caps exit by merger, so this understates nothing dramatic but is a "
                "stated assumption, not a fact",
    }


def modal_holdings(holdings: list[dict], lo: int, hi: int) -> list[dict]:
    from collections import Counter
    c = Counter()
    for h in holdings:
        y = int(h["ym"][:4])
        if lo <= y <= hi:
            for tk, nm in h["names"]:
                c[(tk, nm)] += 1
    tot = sum(1 for h in holdings if lo <= int(h["ym"][:4]) <= hi)
    return [{"ticker": k[0], "company": k[1], "months_held": v,
             "share_of_months": round(v / tot, 3) if tot else None}
            for k, v in c.most_common(12)]


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", type=int, default=1993)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    np.random.default_rng(SEED)  # nothing stochastic here; seeded for house rule

    prereg = {
        "hypothesis": ("Murat: holding the S&P top 1 / top 3 / top 5 / top 10 stocks "
                       "beats holding the S&P 500 itself over the long term."),
        "written_before_computation": True,
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "licence": "PRODUCT_EXPERIMENT (diagnostic; no significance gate, no costs)",
        "objective": "TERMINAL WEALTH under buy-and-hold-the-rule, not mean monthly return",
        "primary_metric": "terminal wealth multiple of TOPn / terminal wealth multiple of TOP500-VW",
        "decision_rule": ("CONFIRMED only if every era's ratio > 1. If the ratio flips below 1 "
                          "in any era, the verdict is REGIME-CONDITIONAL, not a law."),
        "expected_failure_era": ("2000-2012: the top names of Dec-1999 (MSFT/CSCO/GE/INTC) "
                                 "were the epicentre of the crash. Pre-stated."),
        "design": {
            "universe": f"top {BENCH_N} US companies (permco) by month-end market cap; "
                        f"shrcd in {SHRCD_KEEP}, exchcd in {EXCHCD_KEEP}",
            "cap_aggregation": "permco (share classes summed: GOOG+GOOGL, BRK.A+BRK.B)",
            "selection": "month-end cap rank; hold value-weighted for the NEXT calendar month",
            "returns": "CRSP daily `ret` (total return) compounded within month; prc never differenced",
            "benchmarks": ["top500 value-weighted (S&P proxy)", "top500 equal-weighted"],
            "eras": ERAS,
            "eras_evaluated": None,  # filled after the run
            "costs": "ZERO. No commissions, spread, or tax. Stated, not hidden.",
            "turnover_note": "TOP1-TOP10 rebalance monthly; the benchmark barely trades. "
                             "The gross gap overstates the net gap.",
            "seed": SEED,
        },
        "known_limitations": [
            "no CRSP delisting returns (daily dsf only)",
            "missing daily ret treated as 0.0",
            "'top 500 by cap' is a proxy for actual S&P 500 membership (no committee lag)",
            "survivorship-free by construction (CRSP includes dead names) but merger-driven "
            "disappearance inside a month costs the partial month only",
        ],
    }

    print(f"[1/4] loading CRSP {args.start}-{args.end} ...")
    sn = load_names()
    panel, diags = build_panel(args.start, args.end)
    print(f"      panel rows: {len(panel):,}")

    print("[2/4] aggregating to company-months ...")
    tab = company_month_table(panel, sn)
    print(f"      company-months: {len(tab):,}")

    print("[3/4] running strategies ...")
    ser, holdings = run_strategies(tab)

    cols = [f"top{n}_vw" for n in TOPNS] + ["top500_vw", "top500_ew"]
    grid_cols = [f"top{n}_vw" for n in GRID_NS]
    full = {c: metrics(ser[c], ser["year"]) for c in cols}

    era_tables = {}
    for name, (lo, hi) in ERAS.items():
        sub = ser[(ser["year"] >= lo) & (ser["year"] <= hi)]
        if sub.empty:
            continue          # era falls outside --start/--end; omit rather than fake it
        era_tables[name] = {c: metrics(sub[c].reset_index(drop=True),
                                       sub["year"].reset_index(drop=True)) for c in cols}

    # calendar-year table + win counts vs top500_vw
    yr = ser.groupby("year")[cols].apply(lambda g: (1 + g).prod() - 1)
    win_counts = {}
    for n in TOPNS:
        w = int((yr[f"top{n}_vw"] > yr["top500_vw"]).sum())
        win_counts[f"top{n}_vw"] = {"years_beating_top500_vw": w,
                                    "of_years": int(len(yr)),
                                    "hit_rate": round(w / len(yr), 3)}

    prereg["design"]["eras_evaluated"] = list(era_tables)

    print("[4/4] writing receipt ...")
    receipt = {
        "PREREGISTRATION": prereg,
        "verdict": None,  # filled below
        "sample": {
            "start_year": args.start, "end_year": args.end,
            "months_evaluated": int(len(ser)),
            "first_month_earned": str(pd.Timestamp(ser["ym_earned"].iloc[0]).date()),
            "last_month_earned": str(pd.Timestamp(ser["ym_earned"].iloc[-1]).date()),
            "median_universe_size": int(ser["n_universe"].median()),
            "per_year_daily_diagnostics": diags,
        },
        "full_sample_metrics": full,
        "ratio_vs_top500_vw_full_sample": {
            c: round(full[c]["terminal_wealth_multiple"] /
                     full["top500_vw"]["terminal_wealth_multiple"], 4)
            for c in cols
        },
        "concentration_grid": {
            "why": ("terminal wealth as a function of n. A MECHANISM gives a smooth "
                    "plateau; a lucky draw gives a single spike. Read the shape before "
                    "quoting any single n."),
            "full_sample": {c: metrics(ser[c], ser["year"]).get("terminal_wealth_multiple")
                            for c in grid_cols + ["top500_vw"]},
            "by_era": {
                era: {c: metrics(ser[(ser["year"] >= ERAS[era][0]) & (ser["year"] <= ERAS[era][1])][c]
                                 .reset_index(drop=True),
                                 ser[(ser["year"] >= ERAS[era][0]) & (ser["year"] <= ERAS[era][1])]["year"]
                                 .reset_index(drop=True)).get("terminal_wealth_multiple")
                      for c in grid_cols + ["top500_vw"]}
                for era in era_tables
            },
        },
        "era_metrics": era_tables,
        "era_ratio_vs_top500_vw": {
            era: {c: round(era_tables[era][c]["terminal_wealth_multiple"] /
                           era_tables[era]["top500_vw"]["terminal_wealth_multiple"], 4)
                  for c in cols}
            for era in era_tables
        },
        "calendar_year_returns": {
            str(int(y)): {c: round(float(yr.loc[y, c]), 6) for c in cols}
            for y in yr.index
        },
        "years_beating_benchmark": win_counts,
        "modal_holdings": {
            f"top{n}": {era: modal_holdings(holdings[n], lo, hi)
                        for era, (lo, hi) in ERAS.items()}
            for n in (1, 3)
        },
        "top1_holding_by_month_sampled": [
            {"ym": h["ym"], "name": h["names"][0][0]}
            for h in holdings[1] if h["ym"].endswith("-01-01") or h["ym"].endswith("-07-01")
        ],
        "buy_and_hold_no_rebalance": {f"top{n}": buy_and_hold(tab, n) for n in TOPNS},
    }

    ratios = receipt["era_ratio_vs_top500_vw"]
    all_eras_win = all(ratios[e][f"top{n}_vw"] > 1.0 for e in ratios for n in TOPNS)
    receipt["verdict"] = {
        "full_sample": "SUPPORTED" if all(
            receipt["ratio_vs_top500_vw_full_sample"][f"top{n}_vw"] > 1.0 for n in TOPNS
        ) else "MIXED",
        "every_era": "SUPPORTED" if all_eras_win else "REGIME-CONDITIONAL",
        "reading": ("The claim is a REGIME observation unless every era's ratio exceeds 1. "
                    "See era_ratio_vs_top500_vw before quoting the full-sample number."),
    }

    # Shape of the n-curve per era. A NEGATIVE rank correlation between n and
    # terminal wealth means concentration PAID smoothly (a mechanism); a POSITIVE
    # one means concentration COST smoothly (the same mechanism running backwards).
    grid_ns = list(GRID_NS) + [BENCH_N]
    shape = {}
    for era, d in receipt["concentration_grid"]["by_era"].items():
        vals = [d[f"top{n}_vw"] for n in grid_ns]
        rho = float(pd.Series(grid_ns).corr(pd.Series(vals), method="spearman"))
        shape[era] = {
            "spearman_n_vs_terminal_wealth": round(rho, 3),
            "reading": ("concentration PAID, smoothly" if rho <= -0.6 else
                        "concentration COST, smoothly" if rho >= 0.6 else
                        "no clean monotone relation - treat any single n as a path, not a rule"),
        }
    receipt["concentration_grid"]["shape_by_era"] = shape
    vals = [receipt["concentration_grid"]["full_sample"][f"top{n}_vw"] for n in grid_ns]
    receipt["concentration_grid"]["shape_full_sample"] = {
        "spearman_n_vs_terminal_wealth": round(
            float(pd.Series(grid_ns).corr(pd.Series(vals), method="spearman")), 3),
        "note": ("the full-sample curve averages two OPPOSITE regimes and should not be "
                 "read as one mechanism"),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")

    # ------------------------------------------------------------ console
    print("\n=== FULL SAMPLE %d-%d (terminal wealth multiple) ===" % (args.start, args.end))
    for c in cols:
        m = full[c]
        print(f"  {c:>11}  x{m['terminal_wealth_multiple']:>9.2f}  CAGR {m['cagr']*100:6.2f}%  "
              f"vol {m['ann_vol']*100:5.1f}%  maxDD {m['max_drawdown_monthly']*100:6.1f}%  "
              f"worst {m['worst_calendar_year']['year']} {m['worst_calendar_year']['return']*100:6.1f}%")
    print("\n=== ERA terminal wealth multiples ===")
    hdr = "  " + "era".ljust(26) + "".join(c.rjust(11) for c in cols)
    print(hdr)
    for era in era_tables:
        line = "  " + era.ljust(26)
        for c in cols:
            line += f"{era_tables[era][c]['terminal_wealth_multiple']:>11.2f}"
        print(line)
    print("\n=== years beating top500_vw ===")
    for k, v in win_counts.items():
        print(f"  {k:>11}  {v['years_beating_top500_vw']}/{v['of_years']}  ({v['hit_rate']:.0%})")
    print("\n=== concentration grid: terminal wealth vs n (full sample) ===")
    print("    (a MECHANISM gives a smooth plateau; a lucky path gives a spike)")
    g = receipt["concentration_grid"]["full_sample"]
    gmax = max(g.values())
    for c in grid_cols + ["top500_vw"]:
        nlab = c.replace("top", "").replace("_vw", "")
        print(f"  n={nlab:>4}  x{g[c]:>8.2f}  {'#' * int(60 * g[c] / gmax)}")

    print("\n=== concentration grid BY ERA (terminal wealth) ===")
    be = receipt["concentration_grid"]["by_era"]
    print("  n".ljust(8) + "".join(e[:9].rjust(11) for e in be))
    for c in grid_cols + ["top500_vw"]:
        nlab = c.replace("top", "").replace("_vw", "")
        print("  " + nlab.ljust(6) + "".join(f"{be[e][c]:>11.2f}" for e in be))

    print(f"\nreceipt -> {args.out}")


if __name__ == "__main__":
    main()
