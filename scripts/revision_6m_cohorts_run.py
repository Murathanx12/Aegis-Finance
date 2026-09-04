"""REVISION-6M COHORTS: the build-queue #7 evidence base.

WHAT THIS ANSWERS
=================
S36's holding-period study (`scripts/holding_period_policy.py`, receipt
`holding_period_policy_20260903.json`) found that the ONLY admission family
beating the value-weighted market net of costs was the revision selector at a
6-month horizon: `rev_top50/fixed_H6m_25bps` — terminal wealth 3.743 vs market
3.2362 over 2015-02..2024-12, excess CAGR +1.674pp, t_paired_vs_vw 0.69,
breakeven vs the 12m hold 59.58 bps/side. The external review
(`docs/REVIEW_2026-09-03_GPT_VERDICTS_AND_CAPITAL_ALLOCATOR.md` PART B)
specifies the PRODUCT_EXPERIMENT book for hack2 as: **monthly overlapping
cohorts — each month's revision winners get ~1/6 of the sleeve and are held 6
months unless a hard falsifier fires** — so the mechanism keeps its measured
horizon without 6-month information blackouts.

The receipt's `fixed_H6m` arm IS already that overlapping-cohort design
(Jegadeesh-Titman calendar time, 6 sleeves, one reformed per month) minus the
falsifier exits. So this study:

  1. REPLICATES `rev_top50/fixed_H6m` (same code path, imported) and checks
     the numbers against the stored receipt — a drift here would mean the
     evidence base moved under us;
  2. ADDS the falsifier-exit variant the review asks for (typed triggers only:
     the vintage's ratio enters the toxic >= 5.0 band; variants add left-band
     exit and a 20% stop; proceeds park in the MARKET, never cash — S36's
     stop-side rule);
  3. ADDS the naive alternative the review's design is meant to beat: FULL
     rebalance every 6 months (one book, reformed on every 6th vintage, blind
     in between). Its answer depends on WHICH month you start, so all six
     phases are run and reported — headline is the phase mean, worst phase
     printed beside it;
  4. Reports the 2022-2024 sub-window separately (the band prior died there —
     does revision?);
  5. Runs a >= 64-draw null through the IDENTICAL engine and universe filters
     (learner/nullbar.py conventions: percentile + add-one p, the one-draw
     |t|<2 bar is retired). The shuffle permutes `target_rev_1m` WITHIN each
     month across the admissible+revision-covered pool, which for a top-k
     rule is a uniform 50-name draw from that pool. SCOPE OF THIS NULL,
     stated plainly: it answers "does ranking on the revision beat a random
     draw from the same admissible pool", NOT "does the pool beat the
     market" — the rule has no fitted parameters, so there is no fitted
     model to re-fit, and the pool-vs-market question is answered by the
     paired t against the VW market, not by this permutation.

LICENCE: PRODUCT_EXPERIMENT. No significance gate. The four never-relaxed
rules hold: PIT (formation uses the IBES vintage already lagged one day by
`learner/dataset.py`; entry is the first close strictly after), no target
leakage (the engine sees only formation-date columns), costs never omitted
(every arm at 0/10/25/50 bps per side; gross is decomposition, not headline),
every number lands in the receipt
`backend/data/optimus/tracker_backtest/revision_6m_cohorts_20260904.json`.

RESUMABLE: a checkpoint JSON sits next to the receipt; every finished arm and
every finished null draw is flushed to it, and a rerun skips what is done.
The daily return matrix is rebuilt on resume (deterministic, ~minutes).

Run:  python -m scripts.revision_6m_cohorts_run [--nulls 64] [--skip-nulls]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import benchmark as BM                   # noqa: E402
from learner import nullbar                          # noqa: E402
from learner import prior as P                       # noqa: E402
from scripts import holding_period_policy as hpp     # noqa: E402

TRAIN_TABLE = REPO / "backend" / "data" / "optimus" / "learner" / "train_table.parquet"
PARENT_RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
                  / "holding_period_policy_20260905.json")
OUT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
       / "revision_6m_cohorts_20260905.json")
#: The receipt this one REPLACES.
SUPERSEDES = "revision_6m_cohorts_20260904.json"
#: NOT `.json`. A work file that lives in `tracker_backtest/` and ends in
#: `.json` is scanned by `test_benchmark_canonical.py` as if it were a receipt,
#: so a half-finished checkpoint would turn the suite red mid-run for a reason
#: that has nothing to do with the gate. The extension says what it is.
CKPT = OUT.with_suffix(".checkpoint.json.tmp")

RECEIPT_VERSION = "revision-6m-cohorts-2"
#: The two INDEPENDENT definitions of "a revision", each over the FULL PIT
#: hygiene universe. B1 task 4 requires both: the old receipt measured only the
#: first, and only inside the band prior admissible region -- a pool carved by
#: the corrupted split-adjusted ratio, so the pool itself was contaminated.
#:   target_rev_1m : 1-month pct change of the IBES consensus MEAN PRICE TARGET.
#:                   A level-derived quantity, so it inherits whatever the target
#:                   level inherits.
#:   net_rev_1m    : IBES UP minus DOWN revision COUNTS. Never touches a price,
#:                   so it cannot carry a share-basis defect even in principle.
#: If both agree, the mechanism is about revisions. If only the first works, it
#: is about the target level and was mislabelled.
REV_POOLS = {
    "hygiene_targetrev": "rev_top50_hygiene",
    "hygiene_netrev": "netrev_top50_hygiene",
}
#: The legacy pool, kept ONLY so the superseded receipt has a counterpart on the
#: rebuilt panel. It is not the primary any more.
LEGACY_POOL = "rev_top50"
H = 6                              #: the measured horizon, months
COST_BPS = (0.0, 10.0, 25.0, 50.0)
WARMUP = hpp.WARMUP                #: same scored window as the parent study
SUBWINDOW = ("2022-01-01", "2024-12-31")   #: where the band prior died
K = 50                             #: cohort size, exactly the parent's rev_top50


# ----------------------------------------------------------------- engines

def run_fullreb(mkt: dict, rb_dates: list, members: list, cost_bps: float,
                phase: int, holding_m: int = H) -> dict:
    """The NAIVE arm: one book, fully rebalanced on every `holding_m`-th
    vintage (those with index % holding_m == phase), blind in between.

    Same names on formation days, same cost model, same scored window as the
    cohort arm — the ONLY difference is the cohort structure. Formations
    start from the first eligible vintage so the book is invested long before
    the WARMUP boundary; scoring starts at rb_dates[WARMUP] like every arm.
    """
    if not 0 <= phase < holding_m:
        raise SystemExit(f"REFUSED: phase {phase} outside 0..{holding_m - 1}")
    cost = cost_bps / 10000.0
    R = mkt["R"]
    n_days, n_perm = mkt["n_days"], mkt["n_perm"]
    form = {rb_dates[i]: i for i in range(len(rb_dates)) if i % holding_m == phase}
    t0 = min(form)
    v = np.zeros(n_perm, dtype=np.float64)
    cash = 1.0
    book = np.zeros(n_days, dtype=np.float64)
    traded_series = np.zeros(n_days, dtype=np.float64)
    for t in range(t0, n_days):
        if t > t0:
            v *= (1.0 + R[t].astype(np.float64))
        if t in form:
            v, cash, tr = hpp._apply_rebalance(v, cash, members[form[t]], cost)
            traded_series[t] += tr
        book[t] = float(v.sum()) + cash
    out = hpp._score(mkt, book, traded_series, mkt["_start_day"], cost_bps)
    out["phase"] = phase
    return out


def run_cohort_falsifier(mkt: dict, panel: pd.DataFrame, p_ix: dict, d_ix: dict,
                         rb_dates: list, members: list, cost_bps: float,
                         stop_pct: float | None, exit_toxic: bool,
                         exit_left_band: bool, park: str = "market",
                         holding_m: int = H) -> dict:
    """The review's design: H overlapping monthly sleeves, buy-and-hold
    within a sleeve, EXCEPT that a typed falsifier fires a position out early.

    Port of `hpp.run_adaptive` with the horizon parametrised (the parent
    hardcodes H=12). Triggers: per-name stop (checked daily, on the sleeve's
    own entry value), toxic-band entry (the name's CURRENT vintage ratio
    >= ADMISSIBLE_RATIO_HI, checked on vintage days), left-band exit (ratio
    < ADMISSIBLE_RATIO_LO). Proceeds park in the VW market (S36: stops park
    in SPY, never cash) or cash, and are recycled — the slot is freed — when
    that sleeve next reforms.

    A name with NO vintage this month keeps its position: no vintage means no
    opinion, and the parent's adaptive arms use the same convention.
    """
    cost = cost_bps / 10000.0
    R = mkt["R"]
    n_days, n_perm = mkt["n_days"], mkt["n_perm"]
    mkt_r = mkt["mkt"]

    # per vintage day -> (member columns, their ratios), for the band triggers
    ratio_at: dict = {}
    for _m, sub in panel.groupby("month"):
        d = sub["entry_date"].iloc[0]
        if d not in d_ix:
            continue
        keep = [i for i, p in enumerate(sub["permno"]) if p in p_ix]
        cols = np.array([p_ix[p] for p in sub["permno"].iloc[keep]], dtype=int)
        rr = sub["ratio"].to_numpy(dtype=float)[keep]
        ratio_at[d_ix[d]] = (cols, rr)

    sleeves = [np.zeros(n_perm, dtype=np.float64) for _ in range(holding_m)]
    entry = [np.zeros(n_perm, dtype=np.float64) for _ in range(holding_m)]
    scash = [0.0] * holding_m
    parked = [0.0] * holding_m
    live = [False] * holding_m
    rb_at = {d: i for i, d in enumerate(rb_dates)}
    book = np.zeros(n_days, dtype=np.float64)
    traded_series = np.zeros(n_days, dtype=np.float64)
    trig = {"stop": 0, "toxic": 0, "left_band": 0}

    for t in range(rb_dates[0], n_days):
        if t > rb_dates[0]:
            r = R[t].astype(np.float64)
            for j in range(holding_m):
                if live[j]:
                    sleeves[j] *= (1.0 + r)
                    if park == "market":
                        parked[j] *= (1.0 + mkt_r[t])

        for j in range(holding_m):
            if not live[j]:
                continue
            held = sleeves[j] > 0
            if not held.any():
                continue
            kill = np.zeros(n_perm, dtype=bool)
            if stop_pct is not None:
                with np.errstate(invalid="ignore", divide="ignore"):
                    cr = np.where(entry[j] > 0,
                                  sleeves[j] / np.maximum(entry[j], 1e-12) - 1.0, 0.0)
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
            j = i % holding_m
            if not live[j]:
                scash[j] = 1.0 / holding_m
                live[j] = True
            pool = scash[j] + parked[j]
            sleeves[j], _, tr = hpp._apply_rebalance(sleeves[j], pool, members[i], cost)
            scash[j] = 0.0
            parked[j] = 0.0
            entry[j] = sleeves[j].copy()
            traded_series[t] += tr

        book[t] = (sum(float(s.sum()) for s in sleeves)
                   + sum(scash) + sum(parked))

    out = hpp._score(mkt, book, traded_series, mkt["_start_day"], cost_bps)
    out["triggers_fired"] = trig
    return out


def nw_h_minus_1(arm: dict, vw_monthly: pd.Series, h: int = H) -> dict:
    """Newey-West(h-1) on the paired monthly excess of ONE arm.

    Why this is not the arm own `t_newey_west_3`: the parent engine hardcodes
    three Bartlett lags, which is right for a 3-month object and wrong for a
    6-month one. An overlapping 6-month cohort book carries serial correlation
    out to five lags by construction, so h-1 = 5 is the lag the roadmap asks for
    and the one a decision should read. The naive t is printed beside it and is
    OVERSTATED; do not quote it.
    """
    s_ = pd.Series(arm["_monthly"], index=pd.to_datetime(arm["_monthly_index"]))
    m = vw_monthly.reindex(s_.index)
    d = (s_ - m).dropna().to_numpy()
    if len(d) < h + 3:
        return {"n_months": int(len(d)), "status": "TOO_FEW_MONTHS"}
    naive = float(d.mean() / (d.std(ddof=1) / np.sqrt(len(d))))
    return {
        "n_months": int(len(d)),
        "lags": h - 1,
        "mean_monthly_excess_pct": round(float(d.mean() * 100), 4),
        "t_naive_OVERSTATED": round(naive, 3),
        "t_newey_west_h_minus_1": round(hpp._nw_t(d, h - 1), 3),
        "t_newey_west_3_parent_convention": round(hpp._nw_t(d, 3), 3),
        "n_effective_date_blocks_if_non_overlapping": int(len(d) // h),
    }


# ------------------------------------------------------------- sub-window

def subwindow_stats(arm: dict, vw_monthly: pd.Series, lo: str, hi: str) -> dict:
    """Score an arm's ALREADY-MEASURED monthly series on a sub-window.

    Nothing is re-simulated: the sub-window is a slice of the same book, so
    turnover and costs are already inside the returns.
    """
    s = pd.Series(arm["_monthly"], index=pd.to_datetime(arm["_monthly_index"]))
    s = s.loc[(s.index >= lo) & (s.index <= hi)]
    m = vw_monthly.reindex(s.index)
    if len(s) < 3 or m.isna().any():
        return {"n_months": int(len(s)), "verdict": "CANNOT DETERMINE (window not covered)"}
    diff = (s - m).to_numpy()
    n = len(diff)
    cw = np.cumprod(1.0 + s.to_numpy())
    cm = np.cumprod(1.0 + m.to_numpy())
    years = n / 12.0
    return {
        "window": [str(s.index[0].date()), str(s.index[-1].date())],
        "n_months": n,
        "terminal_wealth": round(float(cw[-1]), 4),
        "market_terminal_wealth": round(float(cm[-1]), 4),
        "cagr": round(float(cw[-1] ** (1 / years) - 1), 5),
        "market_cagr": round(float(cm[-1] ** (1 / years) - 1), 5),
        "excess_cagr": round(float(cw[-1] ** (1 / years) - cm[-1] ** (1 / years)), 5),
        "monthly_excess_mean_pct": round(float(diff.mean() * 100), 4),
        "t_paired_vs_vw": round(float(diff.mean() / (diff.std(ddof=1) / np.sqrt(n))), 3),
        "t_newey_west_3": round(hpp._nw_t(diff, 3), 3),
        "max_drawdown": round(float((cw / np.maximum.accumulate(cw) - 1.0).min()), 4),
        "win_rate_months": round(float((diff > 0).mean()), 3),
    }


# ------------------------------------------------------------ checkpointing

def load_ckpt() -> dict:
    if CKPT.exists():
        try:
            return json.loads(CKPT.read_text())
        except json.JSONDecodeError:
            print("  checkpoint unreadable, starting clean")
    return {"arms": {}, "null_draws": []}


def save_ckpt(ck: dict) -> None:
    tmp = CKPT.with_suffix(".tmp")
    tmp.write_text(json.dumps(ck, default=str))
    tmp.replace(CKPT)


# ----------------------------------------------------------------- driver

def build_rev_cohorts(panel: pd.DataFrame, p_ix: dict, d_ix: dict):
    """EXACTLY the parent's rev_top50 admission (build_cohorts, selector
    'rev_top50'): in the band-prior-v2 admissible region, target_rev_1m
    non-null, top 50 per month by target_rev_1m."""
    return hpp.build_cohorts(panel, p_ix, d_ix, "rev_top50")


def null_cohorts(panel: pd.DataFrame, p_ix: dict, d_ix: dict, seed: int,
                 selector: str = "rev_top50"):
    """One null draw: permute the revision column within month over the SAME
    pool, which for top-k selection is a uniform 50-name draw from that pool.
    Identical universe filters as the real arm.

    SCOPE, stated plainly: this answers *does ranking on the revision beat a
    random draw from the same pool*, NOT *does the pool beat the market*. The
    rule has no fitted parameters, so there is no fitted model to re-fit; the
    pool-vs-market question is answered by the paired t against the VW market.
    """
    rng = np.random.default_rng(seed)
    if selector.endswith("_hygiene"):
        df = panel[panel["hygiene_ok"].fillna(False)]
    else:
        df = panel[panel["in_admissible"].fillna(False)]
    col = "net_rev_1m" if selector.startswith("netrev") else "target_rev_1m"
    df = df[df[col].notna()]
    rb_dates, members = [], []
    for _m, sub in df.groupby("month"):
        d = sub["entry_date"].iloc[0]
        if d not in d_ix:
            continue
        perms = sub["permno"].unique()
        perms = np.array([p for p in perms if p in p_ix])
        if len(perms) == 0:
            continue
        pick = rng.choice(perms, size=min(K, len(perms)), replace=False)
        rb_dates.append(d_ix[d])
        members.append(np.array([p_ix[p] for p in pick], dtype=int))
    return rb_dates, members


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2013)
    ap.add_argument("--end", type=int, default=2024)
    ap.add_argument("--nulls", type=int, default=nullbar.MIN_DRAWS)
    ap.add_argument("--skip-nulls", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    ck = load_ckpt()
    done = ck["arms"]

    print("loading the training table ...", flush=True)
    cols = ["permno", "month", "vintage", "entry_date", "in_admissible", "band",
            "ratio", "consensus", "coverage", "close", "market_cap", "target_rev_1m"]
    import pyarrow.parquet as _pq
    have = set(_pq.ParquetFile(TRAIN_TABLE).schema_arrow.names)
    for extra in ("hygiene_ok", "net_rev_1m", "schema_hash"):
        if extra in have:
            cols.append(extra)
        else:
            raise SystemExit(
                f"REFUSED: the panel does not carry {extra!r}. This receipt is "
                "defined over the FULL PIT HYGIENE universe (roadmap B1 task 4) and "
                "cannot be produced from a schema-v1 table. Rebuild the panel first.")
    panel = pd.read_parquet(TRAIN_TABLE, columns=cols)
    panel["entry_date"] = pd.to_datetime(panel["entry_date"])

    print("building the daily return matrix and the VW market ...", flush=True)
    mkt = hpp.build_daily(args.start, args.end)
    print(f"  {mkt['n_days']} sessions x {mkt['n_perm']} permnos", flush=True)

    rb_dates, members, _meta = build_rev_cohorts(panel, mkt["p_ix"], mkt["d_ix"])
    mkt["_start_day"] = rb_dates[WARMUP]
    sizes = [len(x) for x in members]

    # The two PRIMARY pools, over the full PIT hygiene universe.
    pool_cohorts = {}
    for tag, sel in REV_POOLS.items():
        rb, mem, _ = hpp.build_cohorts(panel, mkt["p_ix"], mkt["d_ix"], sel)
        pool_cohorts[tag] = (rb, mem)
        print(f"  pool {tag:20s} ({sel}) {len(rb)} rebalances, "
              f"mean cohort {np.mean([len(x) for x in mem]):.1f}", flush=True)
    # Every arm must be scored on the SAME window or the comparison is a
    # different-sample comparison wearing a horizon label. The scored window is
    # the LATEST of the three pools WARMUP boundary.
    start_day = max([rb_dates[WARMUP]] + [rb[WARMUP] for rb, _ in pool_cohorts.values()])
    mkt["_start_day"] = start_day

    def arm(key: str, fn):
        if key in done:
            print(f"  [ckpt] {key}", flush=True)
            return done[key]
        print(f"  {key}", flush=True)
        res = fn()
        done[key] = res
        save_ckpt(ck)
        return res

    # ---- 1. the overlapping-cohort sleeve (replication of the parent arm, on
    #         the LEGACY admissible pool -- kept for continuity, not primary)
    for c in COST_BPS:
        arm(f"cohort_H6m_{int(c)}bps",
            lambda c=c: hpp.run_fixed(mkt, rb_dates, members, H, c,
                                      start_day=mkt["_start_day"]))

    # ---- 1b. THE PRIMARY ARMS: both revision definitions over the FULL PIT
    #          hygiene universe. Same engine, same costs, same scored window.
    for tag, (rb, mem) in pool_cohorts.items():
        for c in COST_BPS:
            arm(f"cohort_H6m_{tag}_{int(c)}bps",
                lambda rb=rb, mem=mem, c=c: hpp.run_fixed(
                    mkt, rb, mem, H, c, start_day=mkt["_start_day"]))

    # ---- 2. cohorts + hard falsifier exits (the review's design)
    for c in COST_BPS:
        arm(f"cohort_H6m_falsifier_toxic_mktpark_{int(c)}bps",
            lambda c=c: run_cohort_falsifier(
                mkt, panel, mkt["p_ix"], mkt["d_ix"], rb_dates, members, c,
                stop_pct=None, exit_toxic=True, exit_left_band=False))
    for c in (10.0, 25.0):
        arm(f"cohort_H6m_falsifier_toxic_leftband_mktpark_{int(c)}bps",
            lambda c=c: run_cohort_falsifier(
                mkt, panel, mkt["p_ix"], mkt["d_ix"], rb_dates, members, c,
                stop_pct=None, exit_toxic=True, exit_left_band=True))
        arm(f"cohort_H6m_falsifier_stop20_toxic_mktpark_{int(c)}bps",
            lambda c=c: run_cohort_falsifier(
                mkt, panel, mkt["p_ix"], mkt["d_ix"], rb_dates, members, c,
                stop_pct=0.20, exit_toxic=True, exit_left_band=False))

    # ---- 3. the naive full-rebalance-every-6m book, all six phases
    for c in COST_BPS:
        for ph in range(H):
            arm(f"fullreb_6m_phase{ph}_{int(c)}bps",
                lambda c=c, ph=ph: run_fullreb(mkt, rb_dates, members, c, ph))

    # ---- 4. the null (learner/nullbar.py conventions)
    null_block: dict = {"skipped": True}
    if not args.skip_nulls:
        if args.nulls < nullbar.MIN_DRAWS:
            raise SystemExit(f"REFUSED: --nulls {args.nulls} < {nullbar.MIN_DRAWS}")
        null_cost = 25.0
        ck.setdefault("null_draws_by_pool", {})
        # One null family PER POOL. A null drawn from a different pool than the
        # arm it is compared to is not a null for that arm.
        null_specs = {tag: (REV_POOLS[tag], f"cohort_H6m_{tag}_{int(null_cost)}bps")
                      for tag in REV_POOLS}
        null_specs[LEGACY_POOL] = (LEGACY_POOL, f"cohort_H6m_{int(null_cost)}bps")
        null_block = {"null_bar": nullbar.MODEL_NULL_BAR,
                      "shuffle": ("the pool revision column permuted WITHIN month over "
                                  "that pool, which for a top-50 rule is a uniform "
                                  "50-name draw from it; identical engine, filters, "
                                  "scored window and costs (25bps/side)"),
                      "scope": ("answers ranking-vs-random-from-pool, NOT "
                                "pool-vs-market. The rule has no fitted parameters, so a "
                                "fitted-model null does not exist for it -- the "
                                "pool-vs-market question is answered by the paired t "
                                "against the VW market, not by this permutation."),
                      "by_pool": {}}
        for tag, (sel, obs_key) in null_specs.items():
            lst = ck["null_draws_by_pool"].setdefault(tag, [])
            for i in range(len(lst), args.nulls):
                print(f"  null [{tag}] draw {i + 1}/{args.nulls}", flush=True)
                nd_rb, nd_members = null_cohorts(panel, mkt["p_ix"], mkt["d_ix"],
                                                 seed=1000 + i, selector=sel)
                res = hpp.run_fixed(mkt, nd_rb, nd_members, H, null_cost,
                                    start_day=mkt["_start_day"])
                lst.append({
                    "seed": 1000 + i,
                    "monthly_excess_mean_pct": res["monthly_excess_mean_pct"],
                    "terminal_wealth": res["terminal_wealth"],
                    "t_paired_vs_vw": res["t_paired_vs_vw"],
                })
                save_ckpt(ck)
            obs = done[obs_key]
            entry = {"selector": sel, "observed_arm": obs_key,
                     "n_draws": len(lst), "metrics": {}}
            for metric in ("monthly_excess_mean_pct", "terminal_wealth",
                           "t_paired_vs_vw"):
                draws = np.array([d[metric] for d in lst], dtype=float)
                o = float(obs[metric])
                entry["metrics"][metric] = {
                    "observed": o,
                    "null": nullbar.summarise_null(draws),
                    "percentile_of_observed": round(nullbar.percentile_of(o, draws), 4),
                    "p_one_sided": round(nullbar.p_one_sided(o, draws), 4),
                }
            for metric, mv in entry["metrics"].items():
                if mv["percentile_of_observed"] >= 1.0:
                    mv["p_is_the_add_one_FLOOR_not_a_measurement"] = (
                        f"the observed value exceeds ALL {len(lst)} draws, so the "
                        f"exceedance count is ZERO and p = 1/{len(lst) + 1} = "
                        f"{round(1.0 / (len(lst) + 1), 4)} is the add-one FLOOR -- a "
                        "CENSORED BOUND, not a measured p. More draws would push it "
                        "lower; they cannot make it larger. Do not quote it as if it "
                        "were an estimate.")
            null_block["by_pool"][tag] = entry

    # ------------------------------------------------------------- assembly
    vw_vals, vw_idx = hpp._MKT_MONTHLY["vw"]
    vw_monthly = pd.Series(vw_vals, index=pd.to_datetime(vw_idx))

    # replication check against the parent receipt
    replication = {}
    if PARENT_RECEIPT.exists():
        parent = json.loads(PARENT_RECEIPT.read_text())
        for c in COST_BPS:
            key = f"fixed_H{H}m_{int(c)}bps"
            pa = parent["arms"]["rev_top50"].get(key)
            mine = done[f"cohort_H6m_{int(c)}bps"]
            if pa is None:
                continue
            drift = {f: (pa[f], mine[f]) for f in
                     ("terminal_wealth", "cagr", "t_paired_vs_vw", "annual_turnover_x")
                     if abs(float(pa[f]) - float(mine[f])) > 1e-6}
            replication[key] = {
                "match": not drift, "drift": drift or None,
                "parent_window": [pa.get("start"), pa.get("end")],
                "this_window": [mine.get("start"), mine.get("end")],
                "note": ("this receipt scores every arm from the LATEST of its three "
                         "pools warm-up boundaries so the pools are comparable; the "
                         "parent scores each selector from its own. If the windows "
                         "differ, drift is EXPECTED and is not a replication failure -- "
                         "compare the windows before reading the drift."),
            }

    # head to head: cohort vs each fullreb phase, cohort vs falsifier variant
    hh = {}
    for c in (10, 25):
        co = done[f"cohort_H6m_{c}bps"]
        for ph in range(H):
            hh[f"cohort_vs_fullreb_phase{ph}_{c}bps"] = hpp.paired(
                co, done[f"fullreb_6m_phase{ph}_{c}bps"], "cohort_H6m", f"fullreb_ph{ph}")
        hh[f"cohort_vs_falsifier_toxic_{c}bps"] = hpp.paired(
            co, done[f"cohort_H6m_falsifier_toxic_mktpark_{c}bps"],
            "cohort_H6m", "cohort_falsifier_toxic")
        hh[f"falsifier_toxic_vs_fullreb_phase0_{c}bps"] = hpp.paired(
            done[f"cohort_H6m_falsifier_toxic_mktpark_{c}bps"],
            done[f"fullreb_6m_phase0_{c}bps"], "cohort_falsifier_toxic", "fullreb_ph0")

    # phase spread of the naive arm — the honest headline is the mean, and the
    # spread IS the finding (a design whose answer depends on its start month
    # is not a design, it is a lottery over phases)
    phases = {}
    for c in COST_BPS:
        tws = [done[f"fullreb_6m_phase{ph}_{int(c)}bps"]["terminal_wealth"]
               for ph in range(H)]
        ts = [done[f"fullreb_6m_phase{ph}_{int(c)}bps"]["t_paired_vs_vw"]
              for ph in range(H)]
        phases[f"{int(c)}bps"] = {
            "terminal_wealth_by_phase": [round(x, 4) for x in tws],
            "terminal_wealth_mean": round(float(np.mean(tws)), 4),
            "terminal_wealth_min": round(float(np.min(tws)), 4),
            "terminal_wealth_max": round(float(np.max(tws)), 4),
            "t_paired_vs_vw_by_phase": ts,
        }

    # breakeven costs
    co0 = done["cohort_H6m_0bps"]
    fr0_tw = [done[f"fullreb_6m_phase{ph}_0bps"] for ph in range(H)]
    fr0_cagr = float(np.mean([a["cagr"] for a in fr0_tw]))
    fr0_turn = float(np.mean([a["annual_turnover_x"] for a in fr0_tw]))
    be = {
        "cohort_vs_vw_market": {
            "note": "cost/side at which the cohort book's excess CAGR over the VW "
                    "market linearises to zero: gross excess / annual turnover",
            "gross_excess_cagr": co0["excess_cagr"],
            "annual_turnover_x": co0["annual_turnover_x"],
            "breakeven_cost_bps_per_side": round(
                co0["excess_cagr"] / co0["annual_turnover_x"] * 10000.0, 2),
        },
        "cohort_vs_fullreb_6m_phase_mean": {
            "note": "parent-study convention: gross CAGR advantage / extra turnover",
            "gross_cagr_advantage": round(co0["cagr"] - fr0_cagr, 5),
            "extra_annual_turnover_x": round(co0["annual_turnover_x"] - fr0_turn, 3),
            "breakeven_cost_bps_per_side": (
                round((co0["cagr"] - fr0_cagr)
                      / (co0["annual_turnover_x"] - fr0_turn) * 10000.0, 2)
                if abs(co0["annual_turnover_x"] - fr0_turn) > 1e-9 else None),
        },
    }

    # sub-window 2022-2024
    sub = {}
    for key in list(done):
        if key.startswith("fullreb_6m_phase") and "phase0" not in key:
            continue                      # one phase is enough for the sub-window
        sub[key] = subwindow_stats(done[key], vw_monthly, *SUBWINDOW)
    mv = vw_monthly.loc[(vw_monthly.index >= SUBWINDOW[0])
                        & (vw_monthly.index <= SUBWINDOW[1])]
    sub["vw_market"] = {"terminal_wealth": round(float((1 + mv).prod()), 4),
                        "n_months": int(len(mv))}

    parent_cite = {}
    if PARENT_RECEIPT.exists():
        pa = json.loads(PARENT_RECEIPT.read_text())["arms"]["rev_top50"]
        parent_cite = {
            "receipt": PARENT_RECEIPT.name,
            "fixed_H6m_25bps": {k: pa["fixed_H6m_25bps"][k] for k in
                                ("terminal_wealth", "market_terminal_wealth", "cagr",
                                 "excess_cagr", "t_paired_vs_vw", "annual_turnover_x",
                                 "max_drawdown")},
            "breakeven_vs_H12m_bps_per_side": 59.58,
        }

    schema_hash = (str(panel["schema_hash"].iloc[0])
                   if "schema_hash" in panel.columns and len(panel) else None)
    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": hpp.git_head(),
        "python": platform.python_version(),
        "licence": "PRODUCT_EXPERIMENT",
        "supersedes": SUPERSEDES,
        "supersedes_reason": (
            "the superseded receipt is void for TWO reasons, and only the first was "
            "known when it was written. (1) It was computed on `learner-train-table-1`, "
            "whose `ratio` divided the SPLIT-ADJUSTED IBES consensus by the RAW close. "
            "(2) More seriously, every arm selected inside `in_admissible` -- a RATIO "
            "threshold -- so the revision mechanism was measured inside a pool carved by "
            "the corrupted ratio. A revision result measured in a contaminated pool is "
            "not a revision result. This receipt runs the same engine over the FULL PIT "
            "HYGIENE universe (roadmap B1 task 4), which is 5.4x wider, and reports TWO "
            "independent definitions of a revision so the mechanism can be separated "
            "from the target level it was derived from. The old file is sealed and "
            "unedited; it carries a SUPERSEDED_BY sidecar."),
        "panel": {
            "table": "backend/data/optimus/learner/train_table.parquet",
            "schema_version": "learner-train-table-2",
            "schema_hash": schema_hash,
            "rebuild_receipt": "backend/data/optimus/tracker_backtest/panel_rebuild_20260904.json",
            "numerator": "ibes__ptgsumu (UNADJUSTED IBES consensus mean target)",
            "denominator": "raw CRSP dsf close (prc), same share basis",
            "known_open_limitation": (
                "`build_monthly` drops a dying name FINAL month because `fwd_1m` needs a "
                "next monthly row. Not fixed; named in the panel receipt. This script "
                "does not read `fwd_*` -- it simulates a daily book off the CRSP return "
                "matrix -- so the limitation bites only ADMISSION: a name in its final "
                "month is absent from the panel and is therefore never bought. That "
                "removes a small number of terminal losers from every arm AND from every "
                "null draw equally, so the ranking-vs-random comparison is unaffected and "
                "the LEVEL of every arm is mildly generous."),
        },
        BM.STAMP_KEY: BM.declare(
            "vw_crsp_common_main",
            construction=(
                "value-weight daily total return of the CRSP common-stock / main-exchange "
                "universe, weights on the previous session market cap, membership "
                "resolved per (permno, date) against the CRSP name windows; built by "
                "scripts.holding_period_policy.build_daily, which is the same "
                "construction as learner.benchmark.vw_universe. Compounded to calendar "
                "months for the paired tests. Declared rather than re-derived because the "
                "series is produced inside the imported engine; the engine own receipt "
                f"({PARENT_RECEIPT.name}) carries the full Benchmark stamp for the "
                "identical series, cross-checked there against the pinned "
                "Fama-French vintage."),
            span=[str(min(panel["month"])), str(max(panel["month"]))],
            n_periods=int(panel["month"].nunique()),
            freq="M",
            equal_weight_leg="reported as ew_market_cagr / t_paired_vs_ew on every arm "
                             "(ew_crsp_common_main); it is a size portfolio wearing a "
                             "market name and is the SOFTER bar"),
        "void_columns": {
            "columns": ["prior_*", "resid_vw_*", "resid_ew_*", "in_admissible (as a "
                        "PRIMARY selector)"],
            "status": "VOID",
            "why": ("the `prior_*` columns are BAND_PRIOR v2 expectations fitted on the "
                    "corrupted ratio and nothing here reads one. `in_admissible` is a "
                    "band threshold on the ratio; it is retained ONLY as the legacy arm "
                    "so the superseded receipt has a counterpart, and the PRIMARY arms "
                    "use `hygiene_ok` instead. The falsifier arms exit on the toxic "
                    "threshold and are therefore tests of an EXIT RULE, not evidence for "
                    "the bands -- the band study run beside this one finds no band "
                    "premium survives point-in-time."),
        },
        "question": ("Build-queue #7: does the review's monthly-overlapping-cohort "
                     "Revision-6M design (with hard falsifier exits) beat (a) the "
                     "naive full-rebalance-every-6m version and (b) the VW market, "
                     "net of the same cost tiers as the holding-period study?"),
        "design_source": "docs/REVIEW_2026-09-03_GPT_VERDICTS_AND_CAPITAL_ALLOCATOR.md PART B",
        "parent_receipt": parent_cite,
        "scope": {
            "universe": "CRSP common stock, NYSE/AMEX/NASDAQ, with an IBES consensus "
                        "target AND a recommendation that month",
            "window": f"{args.start}-{args.end}",
            "benchmark": "value-weighted CRSP common-stock market (PRIMARY)",
            "admission": {
                "rule": "band prior v2 admissible region AND target_rev_1m non-null; "
                        "top 50 per month by target_rev_1m (1-month pct change of the "
                        "IBES consensus mean price target, valid only when consecutive "
                        "vintages are 20-45 days apart; learner/dataset.py)",
                "ratio_lo": P.ADMISSIBLE_RATIO_LO, "ratio_hi": P.ADMISSIBLE_RATIO_HI,
                "min_price": P.MIN_PRICE, "min_coverage": P.MIN_COVERAGE,
                "prior_version": P.PRIOR_VERSION, "k": K,
            },
            "pit": "formation uses the IBES statpers already lagged one day by "
                   "learner/dataset.py; entry is the first close strictly after",
            "delisting": "CRSP ret carries the delisting return where the daily file "
                         "has one; proceeds then sit in cash for the rest of the "
                         "holding period",
            "costs": "basis points per SIDE on measured traded notional; turnover "
                     "measured from the simulator's own weight changes, never assumed",
            "warmup_rebalances": WARMUP,
            "falsifier_exits": "typed triggers only — toxic-band entry (ratio >= 5.0 "
                               "at the name's newest vintage), variants add left-band "
                               "exit (< 1.5) and a 20% stop; proceeds park in the VW "
                               "market and recycle at the sleeve's next reform",
        },
        "cohort_sizes": {"n_rebalances": len(rb_dates),
                         "mean": round(float(np.mean(sizes)), 1),
                         "min": int(min(sizes)), "max": int(max(sizes))},
        "pool_census": {
            **{tag: hpp.selector_census(panel, sel) for tag, sel in REV_POOLS.items()},
            LEGACY_POOL: hpp.selector_census(panel, LEGACY_POOL),
            "_universe_sizes": {
                "hygiene_ok_name_months": int(panel["hygiene_ok"].fillna(False).sum()),
                "in_admissible_name_months": int(panel["in_admissible"].fillna(False).sum()),
                "hygiene_and_target_rev": int((panel["hygiene_ok"].fillna(False)
                                               & panel["target_rev_1m"].notna()).sum()),
                "hygiene_and_net_rev": int((panel["hygiene_ok"].fillna(False)
                                            & panel["net_rev_1m"].notna()).sum()),
                "admissible_and_target_rev": int((panel["in_admissible"].fillna(False)
                                                 & panel["target_rev_1m"].notna()).sum()),
            },
        },
        "newey_west_h_minus_1_by_arm": {},
        "scored_window": {
            "start_day_index": int(start_day),
            "start_date": str(mkt["dates"][start_day].date()),
            "end_date": str(mkt["dates"][-1].date()),
            "pinned_via": "hpp.run_fixed(start_day=...) on every real arm AND every "
                          "null draw",
            "note": ("all arms, all pools and all null draws are scored from the SAME "
                     "day -- the latest of the three pools' 24-rebalance warm-up "
                     "boundaries -- so an arm cannot win by having a different sample. "
                     "The first version of this receipt did NOT pin it: hpp.run_fixed "
                     "scored each cohort from its own 24th rebalance, and the two "
                     "revision definitions came back against market terminal wealths of "
                     "3.2362 and 3.41 respectively. A benchmark that moves between two "
                     "arms is not a benchmark."),
            "market_terminal_wealth_must_be_identical_across_arms": True,
        },
        "replication_of_parent_fixed_H6m": replication,
        "arms": {},
        "fullreb_phase_spread": phases,
        "head_to_head": hh,
        "breakeven_cost": be,
        "subwindow_2022_2024": sub,
        "null_vs_random_from_pool": null_block,
        "sessions": mkt["n_days"], "permnos": int(mkt["n_perm"]),
    }

    for k, v in done.items():
        if isinstance(v, dict) and "_monthly" in v:
            receipt["newey_west_h_minus_1_by_arm"][k] = nw_h_minus_1(v, vw_monthly, H)

    # ---- FAMILY SIZE. Two pools x four cost tiers x the legacy pool x the
    # falsifier and full-rebalance variants, plus the sub-window. Quote the count.
    arm_ct = len([k for k, v in done.items() if isinstance(v, dict)])
    receipt["family"] = {
        "arms_measured": arm_ct,
        "head_to_head_comparisons": len(receipt["head_to_head"]),
        "subwindow_cells": len(receipt["subwindow_2022_2024"]),
        "family_size_total": (arm_ct + len(receipt["head_to_head"])
                              + len(receipt["subwindow_2022_2024"])),
        "family_max_p": None,
        "family_correction_status": (
            "PENDING AND NOT COMPUTED. The arms are not independent -- they hold "
            "overlapping name sets over one 2013-2024 history -- so a BH-FDR or Holm "
            "correction across them would be both wrong and flattering. The roadmap B4 "
            "block (CPCV with purge/embargo, Deflated Sharpe over the true trial count, "
            "SPA/Reality-Check over the arm set) does not exist yet. NO ARM IN THIS "
            "RECEIPT IS CLAIMED SIGNIFICANT."),
        "what_IS_computed_instead": (
            "a >=64-draw permutation null PER POOL, through the identical engine, "
            "filters, scored window and cost tier, with the percentile of the observed "
            "value and the add-one p reported. That controls for ranking-vs-random "
            "WITHIN a pool. It does NOT control for the number of pools, definitions and "
            "cost tiers examined, and it does not answer pool-vs-market."),
        "model_null_draws_per_pool": args.nulls,
        "model_null_percentiles": {
            tag: {m: e["metrics"][m]["percentile_of_observed"]
                  for m in e["metrics"]}
            for tag, e in (null_block.get("by_pool") or {}).items()},
    }

    # ---- THE COMPARISON THE ROADMAP ASKS FOR: do the two independent revision
    # definitions agree? If only the target-level one works, the mechanism was
    # mislabelled and is about the LEVEL, not about revisions.
    two_defs = {}
    for c in (10, 25):
        a = done.get(f"cohort_H6m_hygiene_targetrev_{c}bps")
        b = done.get(f"cohort_H6m_hygiene_netrev_{c}bps")
        lg = done.get(f"cohort_H6m_{c}bps")
        if not (a and b):
            continue
        two_defs[f"{c}bps"] = {
            "target_rev_1m": {k: a[k] for k in (
                "terminal_wealth", "market_terminal_wealth", "cagr", "excess_cagr",
                "t_paired_vs_vw", "t_newey_west_3", "annual_turnover_x",
                "max_drawdown", "zero_cost_diagnostic")},
            "net_rev_1m": {k: b[k] for k in (
                "terminal_wealth", "market_terminal_wealth", "cagr", "excess_cagr",
                "t_paired_vs_vw", "t_newey_west_3", "annual_turnover_x",
                "max_drawdown", "zero_cost_diagnostic")},
            "legacy_admissible_pool_target_rev": ({k: lg[k] for k in (
                "terminal_wealth", "cagr", "excess_cagr", "t_paired_vs_vw")}
                if lg else None),
            "newey_west_h_minus_1": {
                "target_rev_1m": receipt["newey_west_h_minus_1_by_arm"].get(
                    f"cohort_H6m_hygiene_targetrev_{c}bps"),
                "net_rev_1m": receipt["newey_west_h_minus_1_by_arm"].get(
                    f"cohort_H6m_hygiene_netrev_{c}bps"),
            },
            "paired_targetrev_minus_netrev": hpp.paired(
                a, b, "hygiene_targetrev", "hygiene_netrev"),
        }
    receipt["TWO_INDEPENDENT_REVISION_DEFINITIONS"] = {
        "why": ("B1 task 4: report `target_rev_1m` AND `net_rev_1m` as two independent "
                "definitions of a revision. `target_rev_1m` is a pct change of the "
                "consensus PRICE TARGET, so it is derived from the same level whose share "
                "basis was the defect; `net_rev_1m` is a count of UP minus DOWN analyst "
                "revisions and touches no price at all. Agreement means the mechanism is "
                "about revisions. Target-level-only means it is about the level and was "
                "mislabelled. Neither working means the mechanism does not survive the "
                "de-contaminated pool."),
        "by_cost": two_defs,
    }

    # ---- the invariant the first version of this receipt broke: every arm must
    # be measured against the SAME market. Checked, not asserted.
    mtws = sorted({round(float(v["market_terminal_wealth"]), 6)
                   for v in done.values()
                   if isinstance(v, dict) and "market_terminal_wealth" in v})
    receipt["scored_window"]["market_terminal_wealth_observed"] = mtws
    receipt["scored_window"]["invariant_holds"] = (len(mtws) == 1)
    if len(mtws) != 1:
        receipt["scored_window"]["INVARIANT_VIOLATED"] = (
            "arms in this receipt are measured against DIFFERENT market terminal "
            f"wealths {mtws}. Every cross-arm comparison below is a different-sample "
            "comparison and must NOT be read as a result.")
        print(f"  WARNING: market TW not unique across arms: {mtws}", flush=True)

    series = {}
    for k, v in done.items():
        v = dict(v)
        if "_monthly" in v:
            series[k] = {"index": v.pop("_monthly_index"),
                         "monthly_return": v.pop("_monthly")}
        receipt["arms"][k] = v
    series["benchmark/vw_market"] = {"index": vw_idx, "monthly_return": vw_vals}
    receipt["monthly_series"] = series

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(receipt, indent=2, default=str))
    print(f"\nwrote {out_path}", flush=True)
    # The checkpoint is a WORK FILE. Leaving it beside a sealed receipt invites a
    # later reader to treat it as one.
    if CKPT.exists():
        CKPT.unlink()
        print(f"removed checkpoint {CKPT.name}", flush=True)

    print("\nTWO REVISION DEFINITIONS over the FULL PIT HYGIENE universe "
          "(25bps/side):", flush=True)
    for tag in REV_POOLS:
        a = receipt["arms"].get(f"cohort_H6m_{tag}_25bps")
        nw = receipt["newey_west_h_minus_1_by_arm"].get(f"cohort_H6m_{tag}_25bps", {})
        npc = ((null_block.get("by_pool") or {}).get(tag, {})
               .get("metrics", {}).get("terminal_wealth", {}))
        if a:
            print(f"  {tag:22s} TW {a['terminal_wealth']}  vs market "
                  f"{a['market_terminal_wealth']}  excess CAGR "
                  f"{a['excess_cagr']}  t_NW({H - 1}) "
                  f"{nw.get('t_newey_west_h_minus_1')}  null pct "
                  f"{npc.get('percentile_of_observed')}  p {npc.get('p_one_sided')}",
                  flush=True)

    co = receipt["arms"]["cohort_H6m_25bps"]
    fa = receipt["arms"]["cohort_H6m_falsifier_toxic_mktpark_25bps"]
    print("\nLEGACY admissible pool (25bps/side, 2015-02..2024-12):")
    print(f"  cohort_H6m           TW {co['terminal_wealth']}  vs market "
          f"{co['market_terminal_wealth']}  t {co['t_paired_vs_vw']}  "
          f"maxDD {co['max_drawdown']}  turn {co['annual_turnover_x']}x")
    print(f"  + falsifier (toxic)  TW {fa['terminal_wealth']}  t {fa['t_paired_vs_vw']}  "
          f"maxDD {fa['max_drawdown']}  triggers {fa.get('triggers_fired')}")
    ph = receipt["fullreb_phase_spread"]["25bps"]
    print(f"  fullreb 6m           TW mean {ph['terminal_wealth_mean']} "
          f"[{ph['terminal_wealth_min']}..{ph['terminal_wealth_max']}] across phases")


if __name__ == "__main__":
    main()
