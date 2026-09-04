"""HOLDING-PERIOD POLICY: how long should the engine hold what it admits?

THE QUESTION, IN MURAT'S WORDS
==============================
"rn because of the hackathon we are day trading but I want engine to be able to
invest in any timeframe it sees fit ... I think holding 6-12 months and being
adaptive is much better but sometimes daily opportunities appear we should catch
them. But I also see day trading reading graphs and movements doesn't work and
makes you lose. Test that with multiple scenarios and backtests."

So: hold the ADMISSION SIGNAL CONSTANT and vary only the HOLDING PERIOD. Any
difference in terminal wealth is then attributable to horizon and turnover, not
to selection. Every arm below buys the SAME names on the SAME days; they differ
only in how long they keep them and how often they touch them.

LICENCE: PRODUCT_EXPERIMENT. No significance gate is required to run this.
Costs are never omitted (every arm is reported gross AND at 10bps AND 25bps per
side), PIT is never relaxed (formation uses only the IBES vintage already
lagged one day by `learner/dataset.py`), and claims stay scope-aware
(US common stocks, 2013-2024, IBES-covered, the band prior's admissible region).

THE ARMS
========
FIXED HORIZON    buy the admitted set, equal weight, hold H months, no
                 intra-cohort rebalancing. H in {1, 3, 6, 12}. Overlapping
                 cohorts (Jegadeesh-Titman calendar time): the book is H
                 sleeves, one reformed each month, so every arm is fully
                 invested every month and the ONLY difference is turnover.
DAILY REBALANCE  the H=1 signal, but the book is dragged back to equal weight
                 EVERY SESSION. The signal updates monthly, so every trade
                 between vintages is pure drift-correction: information gain
                 zero, cost real. This is the cost of "touching it".
CHART ARMS       genuinely daily signals over the same universe -- 1-day
                 reversal, 5-day and 20-day price momentum, long the top (or
                 bottom) decile, rebalanced daily. This is "reading graphs and
                 movements", measured.
ADAPTIVE         hold 12 months by DEFAULT, exit early only on a TYPED trigger:
                 a stop, a band exit (the vintage's ratio enters the toxic
                 >= 5.0 band or leaves the admissible region), or a delisting.
                 Proceeds park in cash (primary) or in the market (variant).

CONVENTIONS, STATED RATHER THAN BURIED
======================================
* Returns are CRSP `ret` -- total return, splits out, dividends in, delisting
  return included where the daily file carries one. A delisted name's proceeds
  sit in cash for the remainder of its holding period; the position is NOT
  dropped, because dropping it would delete exactly the failures a long horizon
  is supposed to be punished by.
* Costs are `c` basis points on EVERY SIDE of traded notional. Turnover is
  measured from the actual weight changes the simulator makes, never assumed.
* The measured window starts at rebalance index WARMUP so that the 12-month
  arm's twelve sleeves are all live before anybody is scored. Every arm is
  scored on the identical window.
* The benchmark is the VALUE-WEIGHTED CRSP common-stock market. An
  equal-weighted benchmark is a size portfolio wearing a market's name.
* `zero_cost_diagnostic` gross numbers are printed for decomposition only and
  are never the headline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import benchmark as BM                   # noqa: E402
from learner import prior as P                       # noqa: E402
from scripts import tracker_ibes_backtest as tib     # noqa: E402

TRAIN_TABLE = REPO / "backend" / "data" / "optimus" / "learner" / "train_table.parquet"
OUT = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "holding_period_policy_20260905.json"
SIBLING = REPO / "backend" / "data" / "optimus" / "tracker_backtest" / "band_horizon_20260905.json"
#: The receipt this one REPLACES.
SUPERSEDES = "holding_period_policy_20260903.json"

RECEIPT_VERSION = "holding-period-policy-2"
WARMUP = 24                 # rebalance indices reserved for sleeve warm-up
#: Every fixed-horizon arm. 18 and 24 are in because the literature says the
#: 12-month momentum/target horizon REVERSES beyond a year, and a decay curve
#: that stops at its own maximum cannot show a maximum.
HORIZONS_M = (1, 3, 6, 12, 18, 24)
COST_BPS = (0.0, 10.0, 25.0, 50.0)
SESSIONS_PER_YEAR = 252.0


# --------------------------------------------------------------- the market

def build_daily(start: int, end: int) -> dict:
    """Daily return matrix + the value-weighted market, over one universe."""
    px = tib.load_prices(start, end)
    px = px[(px["date"].dt.year >= start) & (px["date"].dt.year <= end)]
    names = tib.load_names()

    # market cap for the VW index; shrout is in thousands on CRSP dsf
    sh = []
    for year in range(start, end + 1):
        f = REPO / "backend" / "data" / "optimus" / "wrds" / f"crsp_dsf_{year}.parquet"
        if f.exists():
            sh.append(pd.read_parquet(f, columns=["permno", "date", "shrout"]))
    shr = pd.concat(sh, ignore_index=True)
    shr["date"] = pd.to_datetime(shr["date"])
    px = px.merge(shr, on=["permno", "date"], how="left")
    px["market_cap"] = px["prc"] * px["shrout"] * 1000.0

    dates = pd.DatetimeIndex(sorted(px["date"].unique()))
    perms = np.array(sorted(px["permno"].unique()))
    d_ix = {d: i for i, d in enumerate(dates)}
    p_ix = {p: i for i, p in enumerate(perms)}

    R = np.zeros((len(dates), len(perms)), dtype=np.float32)
    LIVE = np.zeros((len(dates), len(perms)), dtype=bool)
    di = px["date"].map(d_ix).to_numpy()
    pi = px["permno"].map(p_ix).to_numpy()
    rv = pd.to_numeric(px["ret"], errors="coerce").fillna(0.0).to_numpy(dtype=np.float32)
    R[di, pi] = rv
    LIVE[di, pi] = True

    # --- VW market over the CRSP common-stock / main-exchange universe,
    #     membership resolved per (permno, date) against the name windows.
    nm = names[["permno", "namedt", "nameenddt"]].sort_values("namedt")
    u = px[["permno", "date", "ret", "market_cap"]].sort_values("date")
    u = pd.merge_asof(u, nm, left_on="date", right_on="namedt", by="permno",
                      direction="backward")
    u = u[u["namedt"].notna() & (u["date"] <= u["nameenddt"])]
    u = u[u["ret"].notna()].sort_values(["permno", "date"])
    u["w"] = u.groupby("permno", sort=False)["market_cap"].shift(1)   # yesterday's cap
    u = u[u["w"].notna() & (u["w"] > 0)]
    num = u.assign(_wr=u["w"] * u["ret"]).groupby("date")["_wr"].sum()
    den = u.groupby("date")["w"].sum()
    vw = (num / den).reindex(dates).fillna(0.0)
    # EW is stored as a SECONDARY only: it is a size portfolio wearing a
    # market's name, and the band prior was fitted against it, so it is the
    # softer bar. Both are printed so nobody has to guess which one a number is.
    ew = u.groupby("date")["ret"].mean().reindex(dates).fillna(0.0)

    return {"dates": dates, "perms": perms, "d_ix": d_ix, "p_ix": p_ix,
            "R": R, "LIVE": LIVE, "mkt": vw.to_numpy(dtype=np.float64),
            "mkt_ew": ew.to_numpy(dtype=np.float64),
            "n_days": len(dates), "n_perm": len(perms)}


# ------------------------------------------------------------- the cohorts

def build_cohorts(panel: pd.DataFrame, p_ix: dict, d_ix: dict,
                  selector: str) -> tuple[list, list, dict]:
    """(rebalance date index, member column indices, per-month ratio lookup)."""
    # The FULL PIT HYGIENE universe: every row the rebuilt dataset was willing to
    # give an opinion on (price floor, coverage floor, readable across splits,
    # ratio < 50). It is 363,684 name-months against 66,821 in the band prior's
    # admissible region -- 5.4x wider. B1 task 4 requires the revision selector
    # to be measured HERE, because the old admissible region was itself carved by
    # the corrupted ratio, so a revision result measured inside it was measured
    # inside a contaminated pool.
    if selector.endswith("_hygiene"):
        if "hygiene_ok" in panel.columns:
            df = panel[panel["hygiene_ok"].fillna(False)].copy()
        else:
            raise SystemExit("REFUSED: selector %r needs `hygiene_ok`, which this "
                             "panel does not carry (schema v1?)" % selector)
    else:
        df = panel[panel["in_admissible"].fillna(False)].copy()
    if selector == "admissible":
        pass
    elif selector == "rev_top50_hygiene":
        # target_rev_1m: 1-month pct change of the IBES consensus mean target.
        df = df[df["target_rev_1m"].notna()]
        df = df.sort_values(["month", "target_rev_1m"], ascending=[True, False])
        df = df.groupby("month").head(50)
    elif selector == "netrev_top50_hygiene":
        # net_rev_1m: IBES UP minus DOWN revision counts -- an INDEPENDENT
        # definition of "revision" that never touches the target level, so it
        # cannot inherit the ratio's share-basis defect even in principle.
        df = df[df["net_rev_1m"].notna()]
        df = df.sort_values(["month", "net_rev_1m"], ascending=[True, False])
        df = df.groupby("month").head(50)
    elif selector == "hygiene_all":
        pass
    elif selector == "band_3_5":
        df = df[df["band"] == "b_3_5"]
    elif selector == "murat_rule":
        df = df[df["consensus"] >= 4.1]
    elif selector == "rev_top50":
        # Brav & Lehavy (2003): what pays on a monthly clock is the REVISION,
        # not the level -- their favourable-revision drift accrues to +6.22%
        # by month 6. So run the same horizon ladder on a revision selector and
        # see whether its best horizon is SHORTER than the level signal's.
        df = df[df["target_rev_1m"].notna()]
        df = df.sort_values(["month", "target_rev_1m"], ascending=[True, False])
        df = df.groupby("month").head(50)
    elif selector == "top50_ratio":
        df = df.sort_values(["month", "ratio"], ascending=[True, False])
        df = df.groupby("month").head(50)
    else:
        raise SystemExit(f"REFUSED: unknown selector {selector!r}")

    months = sorted(df["month"].unique())
    rb_dates, members = [], []
    for m in months:
        sub = df[df["month"] == m]
        d = sub["entry_date"].iloc[0]
        if d not in d_ix:
            continue
        cols = np.array([p_ix[p] for p in sub["permno"].unique() if p in p_ix], dtype=int)
        if len(cols) == 0:
            continue
        rb_dates.append(d_ix[d])
        members.append(cols)
    return rb_dates, members, {"months": months, "selector": selector}


def selector_census(panel: pd.DataFrame, selector: str) -> dict:
    """What a selector actually BUYS: price, size, liquidity, and the cost verdict.

    A book measured at 10bps is only measured at 10bps if the tape offers 10bps.
    A cohort whose median close is $3 does not, and this census is what makes
    that visible without a reader having to go looking (VERIFICATION_2026-09-04
    SS4: the corrected toxic cell earned everything it earned below $5).
    """
    if selector.endswith("_hygiene") and "hygiene_ok" in panel.columns:
        df = panel[panel["hygiene_ok"].fillna(False)]
    else:
        df = panel[panel["in_admissible"].fillna(False)]
    if selector == "rev_top50_hygiene":
        df = df[df["target_rev_1m"].notna()].sort_values(
            ["month", "target_rev_1m"], ascending=[True, False]).groupby("month").head(50)
    elif selector == "netrev_top50_hygiene":
        df = df[df["net_rev_1m"].notna()].sort_values(
            ["month", "net_rev_1m"], ascending=[True, False]).groupby("month").head(50)
    elif selector == "rev_top50":
        df = df[df["target_rev_1m"].notna()].sort_values(
            ["month", "target_rev_1m"], ascending=[True, False]).groupby("month").head(50)
    elif selector == "top50_ratio":
        df = df.sort_values(["month", "ratio"], ascending=[True, False]).groupby("month").head(50)
    pr = pd.to_numeric(df.get("close"), errors="coerce").dropna()
    cap = pd.to_numeric(df.get("market_cap"), errors="coerce").dropna()
    below5 = float((pr < 5.0).mean()) if len(pr) else float("nan")
    return {
        "name_months": int(len(df)),
        "months": int(df["month"].nunique()),
        "median_close": round(float(pr.median()), 3) if len(pr) else None,
        "share_close_below_5": round(below5, 4) if len(pr) == len(pr) else None,
        "share_close_below_2": round(float((pr < 2.0).mean()), 4) if len(pr) else None,
        "median_market_cap_musd": round(float(cap.median()) / 1e6, 1) if len(cap) else None,
        "cost_verdict": (
            "the 10bps and 25bps rows are DEFENSIBLE for this cohort (mostly >= $5)"
            if (below5 == below5 and below5 < 0.25) else
            "UPPER BOUND ONLY: a large share of this cohort trades under $5, where a "
            "10bps round trip is fiction (a realistic spread on a $3 microcap is "
            "50-200bps). Read the 50bps column as the nearest honest one and treat "
            "every tighter column as a decomposition."),
    }


# ------------------------------------------------------------- the engines

def _apply_rebalance(v: np.ndarray, cash: float, targets: np.ndarray,
                     cost: float) -> tuple[np.ndarray, float, float]:
    """Move a sleeve to `targets` (column indices, equal weight). Returns
    (new value vector, new cash, notional traded)."""
    total = float(v.sum()) + cash
    if total <= 0.0 or len(targets) == 0:
        return v, cash, 0.0
    new = np.zeros_like(v)
    new[targets] = total / len(targets)
    traded = float(np.abs(new - v).sum())
    fee = traded * cost
    if fee > 0.0:
        new *= (total - fee) / total
    return new, 0.0, traded


def run_fixed(mkt, rb_dates, members, H: int, cost_bps: float,
              daily_rebalance: bool = False, start_day: int | None = None) -> dict:
    """H overlapping monthly sleeves, buy-and-hold within a sleeve.

    `start_day` pins the SCORED window. It defaults to this cohort's own 24th
    rebalance (the historical behaviour of this receipt), but a caller comparing
    two DIFFERENT selection pools must pass one shared day: two pools whose
    first vintage differs by a month otherwise come back measured against two
    different market terminal wealths, and the difference reads as a result.
    """
    cost = cost_bps / 10000.0
    n_perm, n_days = mkt["n_perm"], mkt["n_days"]
    R = mkt["R"]
    sleeves = [np.zeros(n_perm, dtype=np.float64) for _ in range(H)]
    scash = [0.0] * H
    live = [False] * H
    sleeve_target = [None] * H

    rb_at = {d: i for i, d in enumerate(rb_dates)}
    book = np.zeros(n_days, dtype=np.float64)
    traded_total = 0.0
    traded_series = np.zeros(n_days, dtype=np.float64)
    if start_day is None:
        start_day = rb_dates[WARMUP]
    elif start_day < rb_dates[0]:
        raise SystemExit(
            f"REFUSED: start_day {start_day} precedes this cohort's first rebalance "
            f"{rb_dates[0]} -- the book is not invested yet and the score would be "
            "measured on cash.")

    for t in range(rb_dates[0], n_days):
        # --- grow every live sleeve by the day's returns
        if t > rb_dates[0]:
            r = R[t].astype(np.float64)
            for j in range(H):
                if live[j]:
                    sleeves[j] *= (1.0 + r)

        # --- monthly rebalance: sleeve (i mod H) is reformed
        if t in rb_at:
            i = rb_at[t]
            j = i % H
            if not live[j]:
                # seed this sleeve with 1/H of one unit of capital
                scash[j] = 1.0 / H
                live[j] = True
            sleeves[j], scash[j], tr = _apply_rebalance(
                sleeves[j], scash[j], members[i], cost)
            sleeve_target[j] = members[i]
            traded_total += tr
            traded_series[t] += tr
        elif daily_rebalance:
            # drag every live sleeve back to equal weight on its OWN cohort
            for j in range(H):
                if live[j] and sleeve_target[j] is not None:
                    sleeves[j], scash[j], tr = _apply_rebalance(
                        sleeves[j], scash[j], sleeve_target[j], cost)
                    traded_total += tr
                    traded_series[t] += tr

        book[t] = sum(float(s.sum()) for s in sleeves) + sum(scash)

    return _score(mkt, book, traded_series, start_day, cost_bps)


def run_banded(mkt, panel: pd.DataFrame, p_ix, d_ix, cost_bps: float,
               entry_lo: float, entry_hi: float, keep_lo: float, keep_hi: float,
               k_entry: int | None = None, k_keep: int | None = None) -> dict:
    """THE BUY/HOLD SPREAD -- a STRICTER bar to enter than to stay.

    Novy-Marx & Velikov (2016 RFS) test three ways to survive trading costs --
    restrict to cheap-to-trade stocks, slow the rebalance clock, or widen the
    gap between the entry and the exit threshold -- and find the third
    dominates. It keeps the decision monthly (so the signal never goes stale)
    while refusing to pay a round trip for a name that drifted one rank across
    an arbitrary line. This arm is that policy on OUR signal: enter on
    [entry_lo, entry_hi), stay while [keep_lo, keep_hi).

    A name that stops appearing in the IBES panel is DROPPED, not held: no
    vintage means no opinion, and holding on absence is how a book quietly
    becomes a graveyard.
    """
    cost = cost_bps / 10000.0
    R = mkt["R"]
    n_days, n_perm = mkt["n_days"], mkt["n_perm"]

    ent, kep = {}, {}
    for m, sub in panel.groupby("month"):
        d = sub["entry_date"].iloc[0]
        if d not in d_ix:
            continue
        t = d_ix[d]
        ok = P.has_opinion(sub["close"], sub["coverage"]).to_numpy()
        r = sub["ratio"].to_numpy(dtype=float)
        cols = np.array([p_ix.get(p, -1) for p in sub["permno"]], dtype=int)
        good = (cols >= 0) & ok & np.isfinite(r)
        e = good & (r >= entry_lo) & (r < entry_hi)
        k = good & (r >= keep_lo) & (r < keep_hi)
        if k_entry is not None:
            order = np.argsort(-np.where(e, r, -np.inf))
            sel = np.zeros_like(e)
            sel[order[:k_entry]] = True
            e = e & sel
        if k_keep is not None:
            order = np.argsort(-np.where(k, r, -np.inf))
            sel = np.zeros_like(k)
            sel[order[:k_keep]] = True
            k = k & sel
        ent[t] = cols[e]
        kep[t] = set(cols[k].tolist())

    rb_dates = sorted(ent)
    start_day = rb_dates[WARMUP]
    v = np.zeros(n_perm)
    cash = 1.0
    book = np.zeros(n_days)
    traded_series = np.zeros(n_days)
    target: set = set()
    churn = []

    for t in range(rb_dates[0], n_days):
        if t > rb_dates[0]:
            v *= (1.0 + R[t].astype(np.float64))
        if t in ent:
            held = target & kep[t]
            new = set(ent[t].tolist())
            nxt = held | new
            if nxt:
                churn.append({"held_through": len(held), "entered": len(new - target),
                              "exited": len(target - held), "n": len(nxt)})
                target = nxt
                v, cash, tr = _apply_rebalance(v, cash, np.array(sorted(target), dtype=int), cost)
                traded_series[t] += tr
        book[t] = float(v.sum()) + cash

    out = _score(mkt, book, traded_series, start_day, cost_bps)
    if churn:
        out["banding"] = {
            "entry_band": [entry_lo, entry_hi], "keep_band": [keep_lo, keep_hi],
            "k_entry": k_entry, "k_keep": k_keep,
            "mean_names": round(float(np.mean([c["n"] for c in churn])), 1),
            "mean_entered_per_month": round(float(np.mean([c["entered"] for c in churn])), 1),
            "mean_exited_per_month": round(float(np.mean([c["exited"] for c in churn])), 1),
            "mean_retention_rate": round(float(np.mean(
                [c["held_through"] / max(c["n"], 1) for c in churn])), 3),
        }
    return out


def run_chart(mkt, panel: pd.DataFrame, p_ix, d_ix, lookback: int, side: str,
              decile: float, cost_bps: float) -> dict:
    """A daily price-only signal over the SAME admissible universe.

    Eligibility is PIT: a name is eligible on day t if its most recent monthly
    IBES vintage on or before t admitted it. The signal is the trailing
    `lookback`-session total return, known at the close of t, traded at that
    close, earning day t+1.
    """
    cost = cost_bps / 10000.0
    R = mkt["R"]
    n_days, n_perm = mkt["n_days"], mkt["n_perm"]

    # rolling trailing return over `lookback` sessions (float32: this is a
    # ranking input, not a P&L number)
    cum = np.cumsum(np.log1p(np.clip(R, -0.99, None)), axis=0, dtype=np.float32)
    trail = np.full((n_days, n_perm), np.nan, dtype=np.float32)
    trail[lookback:] = cum[lookback:] - cum[:-lookback]
    del cum

    # eligibility mask, forward-filled from the monthly vintages
    elig = np.zeros((n_days, n_perm), dtype=bool)
    adm = panel[panel["in_admissible"].fillna(False)]
    cur = np.zeros(n_perm, dtype=bool)
    by_day = {}
    for m, sub in adm.groupby("month"):
        d = sub["entry_date"].iloc[0]
        if d in d_ix:
            by_day[d_ix[d]] = np.array(
                [p_ix[p] for p in sub["permno"].unique() if p in p_ix], dtype=int)
    for t in range(n_days):
        if t in by_day:
            cur = np.zeros(n_perm, dtype=bool)
            cur[by_day[t]] = True
        elig[t] = cur
    elig &= mkt["LIVE"]

    rb_dates = sorted(by_day)
    start_day = rb_dates[WARMUP]
    v = np.zeros(n_perm, dtype=np.float64)
    cash = 1.0
    book = np.zeros(n_days, dtype=np.float64)
    traded_series = np.zeros(n_days, dtype=np.float64)

    for t in range(rb_dates[0], n_days):
        if t > rb_dates[0]:
            v *= (1.0 + R[t].astype(np.float64))
        s = np.where(elig[t], trail[t], np.nan)
        ok = ~np.isnan(s)
        if ok.sum() >= 20:
            vals = s[ok]
            idx = np.flatnonzero(ok)
            k = max(5, int(round(decile * len(vals))))
            order = np.argsort(vals)
            pick = idx[order[:k]] if side == "low" else idx[order[-k:]]
            v, cash, tr = _apply_rebalance(v, cash, pick, cost)
            traded_series[t] += tr
        book[t] = float(v.sum()) + cash

    return _score(mkt, book, traded_series, start_day, cost_bps)


def run_adaptive(mkt, panel: pd.DataFrame, p_ix, d_ix, rb_dates, members,
                 cost_bps: float, stop_pct: float, exit_toxic: bool,
                 exit_left_band: bool, park: str) -> dict:
    """Hold 12 months by default; exit early ONLY on a typed trigger."""
    cost = cost_bps / 10000.0
    H = 12
    R = mkt["R"]
    n_days, n_perm = mkt["n_days"], mkt["n_perm"]
    mkt_r = mkt["mkt"]

    # per (rebalance index, permno column) -> ratio at that vintage
    ratio_at = {}
    for m, sub in panel.groupby("month"):
        d = sub["entry_date"].iloc[0]
        if d not in d_ix:
            continue
        t = d_ix[d]
        cols = np.array([p_ix[p] for p in sub["permno"] if p in p_ix], dtype=int)
        rr = sub["ratio"].to_numpy(dtype=float)[
            [i for i, p in enumerate(sub["permno"]) if p in p_ix]]
        ratio_at[t] = (cols, rr)

    sleeves = [np.zeros(n_perm) for _ in range(H)]
    entry = [np.zeros(n_perm) for _ in range(H)]
    scash = [0.0] * H
    parked = [0.0] * H                 # value parked in the market index
    live = [False] * H
    rb_at = {d: i for i, d in enumerate(rb_dates)}
    book = np.zeros(n_days)
    traded_series = np.zeros(n_days)
    trig = {"stop": 0, "toxic": 0, "left_band": 0}
    start_day = rb_dates[WARMUP]

    for t in range(rb_dates[0], n_days):
        if t > rb_dates[0]:
            r = R[t].astype(np.float64)
            for j in range(H):
                if live[j]:
                    sleeves[j] *= (1.0 + r)
                    if park == "market":
                        parked[j] *= (1.0 + mkt_r[t])

        # --- typed triggers, checked daily (stop) and at vintages (band)
        for j in range(H):
            if not live[j]:
                continue
            held = sleeves[j] > 0
            if not held.any():
                continue
            kill = np.zeros(n_perm, dtype=bool)
            if stop_pct is not None:
                with np.errstate(invalid="ignore", divide="ignore"):
                    cr = np.where(entry[j] > 0, sleeves[j] / np.maximum(entry[j], 1e-12) - 1.0, 0.0)
                hit = held & (cr <= -stop_pct)
                trig["stop"] += int(hit.sum())
                kill |= hit
            if t in ratio_at and (exit_toxic or exit_left_band):
                cols, rr = ratio_at[t]
                bad = np.zeros(n_perm, dtype=bool)
                if exit_toxic:
                    sel = cols[rr >= P.ADMISSIBLE_RATIO_HI]
                    bad[sel] = True
                    trig["toxic"] += int(held[sel].sum())
                if exit_left_band:
                    sel = cols[rr < P.ADMISSIBLE_RATIO_LO]
                    bad[sel] = True
                    trig["left_band"] += int(held[sel].sum())
                kill |= (held & bad)
            if kill.any():
                proceeds = float(sleeves[j][kill].sum())
                fee = proceeds * cost
                traded_series[t] += proceeds
                sleeves[j][kill] = 0.0
                entry[j][kill] = 0.0
                if park == "market":
                    parked[j] += proceeds - fee
                else:
                    scash[j] += proceeds - fee

        if t in rb_at:
            i = rb_at[t]
            j = i % H
            if not live[j]:
                scash[j] = 1.0 / H
                live[j] = True
            pool = scash[j] + parked[j]
            sleeves[j], _, tr = _apply_rebalance(sleeves[j], pool, members[i], cost)
            scash[j] = 0.0
            parked[j] = 0.0
            entry[j] = sleeves[j].copy()
            traded_series[t] += tr

        book[t] = sum(float(s.sum()) for s in sleeves) + sum(scash) + sum(parked)

    out = _score(mkt, book, traded_series, start_day, cost_bps)
    out["triggers_fired"] = trig
    return out


# --------------------------------------------------------------- the score

def _score(mkt, book: np.ndarray, traded_series: np.ndarray,
           start_day: int, cost_bps: float) -> dict:
    dates = mkt["dates"]
    n_days = mkt["n_days"]
    b = book[start_day:n_days].copy()
    b = b / b[0]
    d = dates[start_day:n_days]
    mkt_r = mkt["mkt"][start_day:n_days]
    m = np.cumprod(1.0 + mkt_r)
    m = m / m[0]

    years = (d[-1] - d[0]).days / 365.25
    # monthly (calendar-month-end) series for the paired test
    s = pd.Series(b, index=d)
    ms = pd.Series(m, index=d)
    mb = s.resample("ME").last().dropna()
    mm = ms.resample("ME").last().dropna()
    rb_m = mb.pct_change().dropna()
    rm_m = mm.pct_change().dropna()
    j = rb_m.index.intersection(rm_m.index)
    diff = (rb_m.loc[j] - rm_m.loc[j]).to_numpy()
    n = len(diff)
    t_paired = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(n))) if n > 2 else float("nan")
    # Newey-West with 3 lags on the paired difference
    t_nw = _nw_t(diff, lags=3)
    _MKT_MONTHLY["vw"] = ([round(float(x), 8) for x in rm_m.to_numpy()],
                          [str(x.date()) for x in rm_m.index])

    # secondary: the same paired test against the EQUAL-WEIGHTED market
    ew_r = mkt["mkt_ew"][start_day:n_days]
    e = np.cumprod(1.0 + ew_r)
    e = e / e[0]
    es = pd.Series(e, index=d)
    re_m = es.resample("ME").last().dropna().pct_change().dropna()
    je = rb_m.index.intersection(re_m.index)
    diff_ew = (rb_m.loc[je] - re_m.loc[je]).to_numpy()
    t_ew = (float(diff_ew.mean() / (diff_ew.std(ddof=1) / np.sqrt(len(diff_ew))))
            if len(diff_ew) > 2 else float("nan"))

    peak = np.maximum.accumulate(b)
    dd = b / peak - 1.0
    mret = rb_m.to_numpy()

    raw = book[start_day:n_days]
    tr = traded_series[start_day:n_days]
    with np.errstate(invalid="ignore", divide="ignore"):
        frac = np.where(raw > 0, tr / np.maximum(raw, 1e-12), 0.0)
    turn_annual = float(frac.sum() / years)

    return {
        "cost_bps_per_side": cost_bps,
        # Costs are never omitted. A 0bps arm is a DECOMPOSITION, not a result,
        # and the flag rides on the row so no downstream reader can quote it as
        # a net number (`portfolio_farm.Policy` refuses zero costs without it).
        "zero_cost_diagnostic": bool(cost_bps == 0.0),
        "start": str(d[0].date()), "end": str(d[-1].date()),
        "years": round(years, 3),
        "terminal_wealth": round(float(b[-1]), 4),
        "cagr": round(float(b[-1] ** (1.0 / years) - 1.0), 5),
        "market_terminal_wealth": round(float(m[-1]), 4),
        "market_cagr": round(float(m[-1] ** (1.0 / years) - 1.0), 5),
        "excess_cagr": round(float(b[-1] ** (1.0 / years) - m[-1] ** (1.0 / years)), 5),
        "monthly_excess_mean_pct": round(float(diff.mean() * 100), 4),
        "t_paired_vs_vw": round(t_paired, 3),
        "t_newey_west_3": round(t_nw, 3),
        "n_months": int(n),
        "max_drawdown": round(float(dd.min()), 4),
        "ann_vol": round(float(mret.std(ddof=1) * np.sqrt(12)), 4),
        "sharpe_excess_of_market": round(
            float(diff.mean() * 12 / (diff.std(ddof=1) * np.sqrt(12))), 3) if n > 2 else None,
        "annual_turnover_x": round(turn_annual, 3),
        "implied_annual_cost_drag_pct": round(turn_annual * cost_bps / 10000.0 * 100, 3),
        "ew_market_terminal_wealth": round(float(e[-1]), 4),
        "ew_market_cagr": round(float(e[-1] ** (1.0 / years) - 1.0), 5),
        "excess_cagr_vs_ew": round(float(b[-1] ** (1.0 / years) - e[-1] ** (1.0 / years)), 5),
        "t_paired_vs_ew": round(t_ew, 3),
        "_monthly": [round(float(x), 8) for x in rb_m.to_numpy()],
        "_monthly_index": [str(x.date()) for x in rb_m.index],
    }


#: filled by `_score` -- the VW market's own monthly series on the scored window
_MKT_MONTHLY: dict = {}


def paired(a: dict, b: dict, label_a: str, label_b: str) -> dict:
    """HEAD TO HEAD. "Better than what?" is answered against ANOTHER BOOK, not
    only against an index: the horizon question is a choice between two arms
    that hold the same names, so the paired difference removes the common
    market and the common selection and leaves only the horizon."""
    ia = pd.Series(a["_monthly"], index=pd.to_datetime(a["_monthly_index"]))
    ib = pd.Series(b["_monthly"], index=pd.to_datetime(b["_monthly_index"]))
    j = ia.index.intersection(ib.index)
    dd = (ia.loc[j] - ib.loc[j]).to_numpy()
    n = len(dd)
    if n < 3:
        return {"n_months": n, "t": None}
    return {
        "a": label_a, "b": label_b, "n_months": n,
        "mean_monthly_diff_pct": round(float(dd.mean() * 100), 4),
        "t": round(float(dd.mean() / (dd.std(ddof=1) / np.sqrt(n))), 3),
        "t_newey_west_3": round(_nw_t(dd, 3), 3),
        "terminal_wealth_ratio": round(a["terminal_wealth"] / b["terminal_wealth"], 4),
        "win_rate_months": round(float((dd > 0).mean()), 3),
    }


def blend(core: dict, fast: dict, w_fast: float) -> dict:
    """"Sometimes daily opportunities appear and we should catch them."
    So: what does giving the fast lane w_fast of the book actually do to
    terminal wealth? Monthly rebalanced blend of two measured series."""
    ia = pd.Series(core["_monthly"], index=pd.to_datetime(core["_monthly_index"]))
    ib = pd.Series(fast["_monthly"], index=pd.to_datetime(fast["_monthly_index"]))
    j = ia.index.intersection(ib.index)
    r = (1.0 - w_fast) * ia.loc[j] + w_fast * ib.loc[j]
    tw = float((1.0 + r).prod())
    years = len(r) / 12.0
    mv, mi = _MKT_MONTHLY["vw"]
    m = pd.Series(mv, index=pd.to_datetime(mi)).reindex(j)
    dd = (r - m).to_numpy()
    cw = np.cumprod(1.0 + r.to_numpy())
    return {
        "w_fast": w_fast, "n_months": len(r),
        "terminal_wealth": round(tw, 4),
        "cagr": round(float(tw ** (1.0 / years) - 1.0), 5),
        "t_paired_vs_vw": round(float(dd.mean() / (dd.std(ddof=1) / np.sqrt(len(dd)))), 3),
        "max_drawdown": round(float((cw / np.maximum.accumulate(cw) - 1.0).min()), 4),
    }


def _nw_t(x: np.ndarray, lags: int = 3) -> float:
    n = len(x)
    if n <= lags + 2:
        return float("nan")
    e = x - x.mean()
    g0 = float(e @ e) / n
    s = g0
    for L in range(1, lags + 1):
        g = float(e[L:] @ e[:-L]) / n
        s += 2.0 * (1.0 - L / (lags + 1.0)) * g
    se = np.sqrt(max(s, 1e-18) / n)
    return float(x.mean() / se)


# ----------------------------------------------------------------- driver

def git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO,
                                       text=True).strip()[:12]
    except Exception:
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    print("loading the training table ...")
    cols = ["permno", "month", "vintage", "entry_date", "in_admissible", "band",
            "ratio", "consensus", "coverage", "close", "market_cap", "target_rev_1m"]
    # schema v2 additions: the hygiene flag (the FULL PIT universe B1 task 4
    # requires) and net_rev_1m (the second, independent revision definition).
    import pyarrow.parquet as _pq
    have = set(_pq.ParquetFile(TRAIN_TABLE).schema_arrow.names)
    for extra in ("hygiene_ok", "net_rev_1m", "schema_hash"):
        if extra in have:
            cols.append(extra)
    panel = pd.read_parquet(TRAIN_TABLE, columns=cols)
    panel["entry_date"] = pd.to_datetime(panel["entry_date"])

    print("building the daily return matrix and the VW market ...")
    mkt = build_daily(args.start, args.end)
    print(f"  {mkt['n_days']} sessions x {mkt['n_perm']} permnos")

    schema_hash = (str(panel["schema_hash"].iloc[0])
                   if "schema_hash" in panel.columns and len(panel) else None)
    receipt: dict = {
        "receipt_version": RECEIPT_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": git_head(),
        "python": platform.python_version(),
        "licence": "PRODUCT_EXPERIMENT",
        "supersedes": SUPERSEDES,
        "supersedes_reason": (
            "the superseded receipt was computed on `learner-train-table-1`, whose "
            "`ratio` divided the SPLIT-ADJUSTED IBES consensus (`ptgsum`) by the RAW CRSP "
            "close. Every arm here selects inside `in_admissible`, which is a RATIO "
            "threshold, so the admission column itself was corrupted -- the arms were "
            "buying a different set of names than the receipt said. This is a straight "
            "re-run of the identical code path on `learner-train-table-2`, which reads the "
            "UNADJUSTED consensus `ibes__ptgsumu` over the same raw close, PLUS two new "
            "selectors over the full PIT hygiene universe (B1 task 4). The old file is "
            "sealed and unedited; it carries a SUPERSEDED_BY sidecar."),
        "panel": {
            "table": "backend/data/optimus/learner/train_table.parquet",
            "schema_version": "learner-train-table-2",
            "schema_hash": schema_hash,
            "rebuild_receipt": "backend/data/optimus/tracker_backtest/panel_rebuild_20260904.json",
            "numerator": "ibes__ptgsumu (UNADJUSTED IBES consensus mean target)",
            "denominator": "raw CRSP dsf close (prc), same share basis",
            "known_open_limitation": (
                "`build_monthly` drops a dying name's FINAL month because `fwd_1m` needs a "
                "next monthly row. It is NOT fixed and is named in the panel receipt. "
                "Effect HERE is smaller than on the band study: this script does not read "
                "`fwd_*` at all -- it simulates a daily book off the CRSP return matrix "
                "built by `build_daily`, and a delisted name's proceeds sit in cash for the "
                "rest of the holding period. The limitation bites only the ADMISSION side "
                "(a name in its final month is absent from the panel, so it is never "
                "bought), which removes a small number of terminal losers from every arm "
                "equally and is therefore mildly generous in LEVEL and close to neutral in "
                "the arm-vs-arm contrasts this study exists to measure."),
        },
        "question": ("Hold the admission signal constant and vary ONLY the holding "
                     "period. Which horizon maximises terminal wealth net of costs?"),
        "scope": {
            "universe": "CRSP common stock, NYSE/AMEX/NASDAQ, with an IBES consensus "
                        "target AND a recommendation that month",
            "window": f"{args.start}-{args.end}",
            "benchmark": "value-weighted CRSP common-stock market (PRIMARY)",
            "admission": {
                "rule": "band prior v2 admissible region",
                "ratio_lo": P.ADMISSIBLE_RATIO_LO, "ratio_hi": P.ADMISSIBLE_RATIO_HI,
                "min_price": P.MIN_PRICE, "min_coverage": P.MIN_COVERAGE,
                "prior_version": P.PRIOR_VERSION,
            },
            "pit": "formation uses the IBES statpers already lagged one day by "
                   "learner/dataset.py; entry is the first close strictly after",
            "delisting": "CRSP ret carries the delisting return where the daily file has "
                         "one; proceeds then sit in cash for the rest of the holding period",
            "costs": "basis points per SIDE on measured traded notional; turnover is "
                     "measured from the simulator's own weight changes, never assumed",
            "warmup_rebalances": WARMUP,
        },
        "arms": {},
        "sessions": mkt["n_days"], "permnos": int(mkt["n_perm"]),
    }

    # ---- THE RULER. This script builds its own VW market inside `build_daily`,
    # so it holds the series and stamps a real Benchmark object rather than a
    # declaration. The pinned Fama-French market is then compared to it over the
    # same span: two independently-constructed value-weighted total returns that
    # disagree would mean one of them is wrong, and the disagreement is printed
    # instead of assumed away.
    vw_series = pd.Series(mkt["mkt"], index=mkt["dates"], name="vw_crsp_common_main")
    vw_bm = BM.Benchmark(
        "vw_crsp_common_main", vw_series, "D",
        {"source": "scripts.holding_period_policy.build_daily",
         "construction": "value-weight daily total return of the CRSP common-stock / "
                         "main-exchange universe, weights on the PREVIOUS session's "
                         "market cap (prc x shrout x 1000), membership resolved per "
                         "(permno, date) against the CRSP name windows; identical "
                         "construction to learner.benchmark.vw_universe",
         "dividends_included": True, "network": False,
         "delisting": "CRSP dsf `ret` carries a delisting return only where the daily "
                      "file has one -- mildly generous to dead names, and stated rather "
                      "than claimed the other way"})
    receipt[BM.STAMP_KEY] = vw_bm.stamp()
    try:
        pin = BM.pinned_market_total_return(
            str(mkt["dates"][0].date()), str(mkt["dates"][-1].date()))
        receipt["benchmark_crosscheck_vs_pinned_ff"] = {
            "this_scripts_vw_total_return_pct": round(100.0 * vw_bm.total_return(), 3),
            "pinned_ff_vw_total_return_pct": round(100.0 * pin.total_return(), 3),
            "pinned_sessions": int(len(pin.returns)),
            "this_scripts_sessions": int(len(vw_series)),
            "note": ("two independent value-weighted TOTAL returns over the same span. "
                     "They are not required to match to the digit -- the pinned vintage "
                     "is the full Fama-French CRSP universe, this one is the panel own "
                     "common-stock / main-exchange screen -- but a large gap would be a "
                     "finding, so it is printed."),
        }
    except BM.BenchmarkUnavailable as e:
        receipt["benchmark_crosscheck_vs_pinned_ff"] = {
            "status": "CANNOT DETERMINE", "missing": e.missing, "detail": str(e)}

    receipt["void_columns"] = {
        "columns": ["prior_*", "resid_vw_*", "resid_ew_*"],
        "status": "VOID",
        "why": ("BAND_PRIOR v2 expectations fitted on the corrupted split-adjusted ratio; "
                "an attended proposal retires them (roadmap B1 task 5). Nothing in this "
                "receipt reads one. NOTE that `in_admissible` and the adaptive arms "
                "`toxic` / `left_band` triggers ARE band thresholds "
                "(learner.prior.ADMISSIBLE_RATIO_LO/HI) applied to the REBUILT "
                "point-in-time ratio. Those thresholds are hygiene-shaped, not "
                "expectations, and the band study run beside this one finds NO band "
                "premium survives point-in-time -- so read the adaptive arms as tests of "
                "an EXIT RULE, never as evidence for the bands themselves."),
    }

    selectors = ["admissible", "top50_ratio", "rev_top50"]
    receipt["selector_census"] = {sel: selector_census(panel, sel) for sel in selectors}
    for sel in selectors:
        rb_dates, members, meta = build_cohorts(panel, mkt["p_ix"], mkt["d_ix"], sel)
        sizes = [len(x) for x in members]
        receipt["arms"].setdefault(sel, {})["cohort_sizes"] = {
            "n_rebalances": len(rb_dates), "mean": round(float(np.mean(sizes)), 1),
            "median": int(np.median(sizes)), "min": int(min(sizes)), "max": int(max(sizes))}

        for H in HORIZONS_M:
            for c in COST_BPS:
                key = f"fixed_H{H}m_{int(c)}bps"
                print(f"  [{sel}] {key}")
                receipt["arms"][sel][key] = run_fixed(mkt, rb_dates, members, H, c)

        # the cost of TOUCHING it: same monthly signal, dragged back daily
        for c in COST_BPS:
            key = f"daily_rebalance_H1m_{int(c)}bps"
            print(f"  [{sel}] {key}")
            receipt["arms"][sel][key] = run_fixed(mkt, rb_dates, members, 1, c,
                                                  daily_rebalance=True)

        if sel == "admissible":
            for el, eh, kl, kh, ke, kk, tag in (
                (1.5, 5.0, 1.5, 5.0, None, None, "symmetric_control"),
                (1.5, 5.0, 1.2, 6.0, None, None, "entry15_keep12"),
                (1.5, 5.0, 1.0, 8.0, None, None, "entry15_keep10"),
                (2.0, 5.0, 1.2, 6.0, None, None, "entry20_keep12"),
                (3.0, 5.0, 1.2, 6.0, None, None, "entry30_keep12"),
                (1.5, 5.0, 1.2, 6.0, 25, 100, "top25_in_top100_out"),
                (1.5, 5.0, 1.2, 6.0, 50, 200, "top50_in_top200_out"),
            ):
                for c in COST_BPS:
                    key = f"banded_{tag}_{int(c)}bps"
                    print(f"  [{sel}] {key}")
                    receipt["arms"][sel][key] = run_banded(
                        mkt, panel, mkt["p_ix"], mkt["d_ix"], c, el, eh, kl, kh, ke, kk)

            for stop, tox, leave, park, tag in (
                (0.20, True, False, "cash", "stop20_toxicexit_cash"),
                (0.30, True, False, "cash", "stop30_toxicexit_cash"),
                (0.50, True, False, "cash", "stop50_toxicexit_cash"),
                (0.20, True, True, "cash", "stop20_toxic_leftband_cash"),
                (0.20, True, False, "market", "stop20_toxicexit_mktpark"),
                (0.30, True, False, "market", "stop30_toxicexit_mktpark"),
                (0.50, True, False, "market", "stop50_toxicexit_mktpark"),
                (None, True, False, "cash", "toxicexit_only_cash"),
                (None, True, False, "market", "toxicexit_only_mktpark"),
                (None, False, True, "market", "leftband_only_mktpark"),
                (None, True, True, "market", "toxic_and_leftband_mktpark"),
            ):
                for c in (10.0, 25.0):
                    key = f"adaptive12m_{tag}_{int(c)}bps"
                    print(f"  [{sel}] {key}")
                    receipt["arms"][sel][key] = run_adaptive(
                        mkt, panel, mkt["p_ix"], mkt["d_ix"], rb_dates, members,
                        c, stop, tox, leave, park)

    # ---- the chart arms: "reading graphs and movements", measured
    print("  chart arms ...")
    receipt["arms"]["chart_daily"] = {}
    for lookback, side, tag in ((1, "low", "reversal_1d"),
                                (5, "high", "momentum_5d"),
                                (20, "high", "momentum_20d"),
                                (5, "low", "reversal_5d")):
        for c in COST_BPS:
            key = f"{tag}_decile_{int(c)}bps"
            print(f"    {key}")
            receipt["arms"]["chart_daily"][key] = run_chart(
                mkt, panel, mkt["p_ix"], mkt["d_ix"], lookback, side, 0.10, c)

    # ------------------------------------------------- head to head, and blends
    A = receipt["arms"]["admissible"]
    C = receipt["arms"]["chart_daily"]
    hh = {}
    for c in (10, 25):
        for h in (1, 3, 6, 18, 24):
            hh[f"H12m_vs_H{h}m_{c}bps"] = paired(
                A[f"fixed_H12m_{c}bps"], A[f"fixed_H{h}m_{c}bps"], "H12m", f"H{h}m")
        hh[f"H6m_vs_H1m_{c}bps"] = paired(
            A[f"fixed_H6m_{c}bps"], A[f"fixed_H1m_{c}bps"], "H6m", "H1m")
        hh[f"H12m_vs_dailyrebal_{c}bps"] = paired(
            A[f"fixed_H12m_{c}bps"], A[f"daily_rebalance_H1m_{c}bps"], "H12m", "daily_rebal")
        hh[f"H1m_vs_dailyrebal_{c}bps"] = paired(
            A[f"fixed_H1m_{c}bps"], A[f"daily_rebalance_H1m_{c}bps"], "H1m", "daily_rebal")
        for tag in ("stop20_toxicexit_cash", "stop30_toxicexit_cash",
                    "stop50_toxicexit_cash", "stop20_toxic_leftband_cash",
                    "stop20_toxicexit_mktpark", "stop30_toxicexit_mktpark",
                    "stop50_toxicexit_mktpark", "toxicexit_only_cash",
                    "toxicexit_only_mktpark", "leftband_only_mktpark",
                    "toxic_and_leftband_mktpark"):
            hh[f"adaptive_{tag}_vs_H12m_{c}bps"] = paired(
                A[f"adaptive12m_{tag}_{c}bps"], A[f"fixed_H12m_{c}bps"],
                f"adaptive_{tag}", "H12m")
        for tag in ("entry15_keep12", "entry15_keep10", "entry20_keep12",
                    "entry30_keep12", "top25_in_top100_out", "top50_in_top200_out"):
            hh[f"banded_{tag}_vs_H1m_{c}bps"] = paired(
                A[f"banded_{tag}_{c}bps"], A[f"fixed_H1m_{c}bps"], f"banded_{tag}", "H1m")
            hh[f"banded_{tag}_vs_H12m_{c}bps"] = paired(
                A[f"banded_{tag}_{c}bps"], A[f"fixed_H12m_{c}bps"], f"banded_{tag}", "H12m")
        for tag in ("reversal_1d", "momentum_5d", "momentum_20d", "reversal_5d"):
            hh[f"H12m_vs_chart_{tag}_{c}bps"] = paired(
                A[f"fixed_H12m_{c}bps"], C[f"{tag}_decile_{c}bps"], "H12m", tag)
    receipt["head_to_head"] = hh

    # ---- BREAKEVEN COST. The one number that decides a turnover argument:
    # at what cost per side does an arm's GROSS advantage over the 12-month
    # hold get eaten by its extra turnover?  Linearised (drag = turnover x c),
    # which is exact in arithmetic terms and close in geometric ones.
    be = {}
    for grp in ("admissible", "top50_ratio", "rev_top50", "chart_daily"):
        ref = (receipt["arms"]["admissible"]["fixed_H12m_0bps"]
               if grp == "chart_daily" else receipt["arms"][grp]["fixed_H12m_0bps"])
        for k, v in receipt["arms"][grp].items():
            if not (isinstance(v, dict) and k.endswith("_0bps")):
                continue
            dturn = v["annual_turnover_x"] - ref["annual_turnover_x"]
            dcagr = v["cagr"] - ref["cagr"]
            be[f"{grp}/{k}"] = {
                "gross_cagr_advantage_vs_H12m": round(dcagr, 5),
                "extra_annual_turnover_x": round(dturn, 3),
                "breakeven_cost_bps_per_side": (
                    round(dcagr / dturn * 10000.0, 2) if abs(dturn) > 1e-9 else None),
                "verdict": (
                    "no gross advantage to pay for" if dcagr <= 0 and dturn > 0 else
                    "cheaper AND better" if dcagr > 0 and dturn <= 0 else
                    "advantage survives only below the breakeven cost"),
            }
    receipt["breakeven_cost_vs_12m_hold"] = be

    # "sometimes daily opportunities appear" -- price the sleeve
    bl = {}
    for c in (10, 25):
        for tag in ("reversal_1d", "momentum_20d"):
            for w in (0.0, 0.05, 0.10, 0.20):
                bl[f"core_H12m_plus_{w:.2f}_{tag}_{c}bps"] = blend(
                    A[f"fixed_H12m_{c}bps"], C[f"{tag}_decile_{c}bps"], w)
    receipt["fast_lane_blends"] = bl

    # ---- RISK BOUNDS. The session protocol requires the worst case in
    # dollars BEFORE any stop / sizing / cap change is proposed, and this study
    # recommends changing a stop, so it is printed here rather than asserted.
    rbnd = {}
    for name, arm in (("fixed_H12m_25bps", A["fixed_H12m_25bps"]),
                      ("fixed_H1m_25bps", A["fixed_H1m_25bps"]),
                      ("adaptive_stop20_cash_25bps", A["adaptive12m_stop20_toxicexit_cash_25bps"]),
                      ("adaptive_stop20_mktpark_25bps", A["adaptive12m_stop20_toxicexit_mktpark_25bps"]),
                      ("rev_top50_H6m_25bps", receipt["arms"]["rev_top50"]["fixed_H6m_25bps"]),
                      ("chart_reversal_1d_25bps", C["reversal_1d_decile_25bps"])):
        ser = pd.Series(arm["_monthly"], index=pd.to_datetime(arm["_monthly_index"]))
        roll12 = (1.0 + ser).rolling(12).apply(np.prod, raw=True) - 1.0
        rbnd[name] = {
            "worst_month_pct": round(float(ser.min() * 100), 3),
            "worst_rolling_12m_pct": round(float(roll12.min() * 100), 3),
            "max_drawdown_pct": round(arm["max_drawdown"] * 100, 3),
            "months_negative": int((ser < 0).sum()), "months": int(len(ser)),
        }
    rbnd["_arithmetic_bound_note"] = {
        "with_per_name_stop": "worst case = n_names x notional_pct x stop_pct",
        "without_per_name_stop": ("worst case per name is -100%, so the ONLY remaining "
                                  "bound is the GROSS cap: sum|notional| / equity. Removing "
                                  "a stop therefore REQUIRES a gross cap to be the binding "
                                  "control, and the worst case must be requoted as "
                                  "gross x realised_drawdown, not as n x w x stop."),
        "measured_substitute_for_the_stop": ("this study's max drawdown and worst rolling "
                                             "12m for each arm, above, at 100% gross"),
    }
    receipt["risk_bounds_at_100pct_gross"] = rbnd

    # the monthly series live in their own block, out of the arm tables
    series = {}
    for grp in ("admissible", "top50_ratio", "rev_top50", "chart_daily"):
        for k, v in receipt["arms"][grp].items():
            if isinstance(v, dict) and "_monthly" in v:
                series[f"{grp}/{k}"] = {"index": v.pop("_monthly_index"),
                                        "monthly_return": v.pop("_monthly")}
    mv, mi = _MKT_MONTHLY["vw"]
    series["benchmark/vw_market"] = {"index": mi, "monthly_return": mv}
    receipt["monthly_series"] = series

    # ---- FAMILY SIZE. Every t in this receipt is one of hundreds of arms over
    # one history. Quote the count or do not quote the t.
    arm_keys = [(g, k) for g in receipt["arms"]
                for k, v in receipt["arms"][g].items()
                if isinstance(v, dict) and "t_paired_vs_vw" in v]
    ts = [receipt["arms"][g][k]["t_paired_vs_vw"] for g, k in arm_keys
          if receipt["arms"][g][k].get("t_paired_vs_vw") is not None]
    receipt["family"] = {
        "arms_measured": len(arm_keys),
        "head_to_head_comparisons": len(receipt["head_to_head"]),
        "breakeven_cells": len(receipt["breakeven_cost_vs_12m_hold"]),
        "blend_cells": len(receipt["fast_lane_blends"]),
        "family_size_total": (len(arm_keys) + len(receipt["head_to_head"])
                              + len(receipt["breakeven_cost_vs_12m_hold"])
                              + len(receipt["fast_lane_blends"])),
        "max_t_paired_vs_vw_over_all_arms": (round(float(np.nanmax(ts)), 3) if ts else None),
        "family_max_p": None,
        "family_correction_status": (
            "PENDING AND NOT COMPUTED. This is a HORIZON SWEEP over one 12-year history: "
            "the arms are not independent (they hold the same names on the same days and "
            "differ only in holding period), so a BH-FDR or Holm correction over them "
            "would be both wrong and flattering. The correct instrument is the roadmap "
            "B4 block -- CPCV with purge/embargo, a Deflated Sharpe over the true trial "
            "count, and a SPA/Reality-Check over the whole arm set -- and it does not "
            "exist yet. NO ARM IN THIS RECEIPT IS CLAIMED SIGNIFICANT. The paired "
            "arm-vs-arm t values are the ones to read, because they difference out the "
            "common market and the common selection and leave only the horizon."),
        "model_null_percentile": None,
        "model_null_status": (
            "NOT RUN IN THIS RECEIPT. These arms have no fitted parameters, so the "
            ">=64-draw MODEL null (learner/nullbar.py) has nothing to re-fit. The "
            "random-selection null for the revision selector IS run, over >=64 draws "
            "through this same engine, in `revision_6m_cohorts_20260905.json`."),
    }

    if SIBLING.exists():
        blob = SIBLING.read_bytes()
        sib = json.loads(blob.decode("utf-8"))
        # The sibling used to be embedded whole (0.6 MB). A reference plus a hash
        # plus the one block a reader of THIS receipt must not miss is better: a
        # copy of a sealed receipt inside another receipt is a second source of
        # truth waiting to drift.
        receipt["sibling_band_horizon_receipt"] = {
            "path": f"backend/data/optimus/tracker_backtest/{SIBLING.name}",
            "sha256": hashlib.sha256(blob).hexdigest(),
            "supersedes": sib.get("supersedes"),
            "MANDATORY_TOXIC_BAND_DISCLOSURE": sib.get("MANDATORY_TOXIC_BAND_DISCLOSURE"),
            "note": ("embedded BY REFERENCE. The adaptive arms in this receipt exit on the "
                     "toxic threshold, so the sibling finding -- that no band premium "
                     "survives a point-in-time ratio, and that the toxic cell sign "
                     "depends on a $5 price floor -- is the context those arms must be "
                     "read in."),
        }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(receipt, indent=2, default=str))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
