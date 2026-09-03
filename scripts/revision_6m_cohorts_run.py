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

from learner import nullbar                          # noqa: E402
from learner import prior as P                       # noqa: E402
from scripts import holding_period_policy as hpp     # noqa: E402

TRAIN_TABLE = REPO / "backend" / "data" / "optimus" / "learner" / "train_table.parquet"
PARENT_RECEIPT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
                  / "holding_period_policy_20260903.json")
OUT = (REPO / "backend" / "data" / "optimus" / "tracker_backtest"
       / "revision_6m_cohorts_20260904.json")
CKPT = OUT.with_suffix(".checkpoint.json")

RECEIPT_VERSION = "revision-6m-cohorts-1"
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


def null_cohorts(panel: pd.DataFrame, p_ix: dict, d_ix: dict, seed: int):
    """One null draw: permute target_rev_1m within month over the SAME pool
    (admissible AND revision-covered), which for top-k selection is a uniform
    50-name draw from that pool. Identical universe filters as the real arm."""
    rng = np.random.default_rng(seed)
    df = panel[panel["in_admissible"].fillna(False)]
    df = df[df["target_rev_1m"].notna()]
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
    panel = pd.read_parquet(TRAIN_TABLE, columns=[
        "permno", "month", "vintage", "entry_date", "in_admissible", "band",
        "ratio", "consensus", "coverage", "close", "market_cap", "target_rev_1m"])
    panel["entry_date"] = pd.to_datetime(panel["entry_date"])

    print("building the daily return matrix and the VW market ...", flush=True)
    mkt = hpp.build_daily(args.start, args.end)
    print(f"  {mkt['n_days']} sessions x {mkt['n_perm']} permnos", flush=True)

    rb_dates, members, _meta = build_rev_cohorts(panel, mkt["p_ix"], mkt["d_ix"])
    mkt["_start_day"] = rb_dates[WARMUP]
    sizes = [len(x) for x in members]

    def arm(key: str, fn):
        if key in done:
            print(f"  [ckpt] {key}", flush=True)
            return done[key]
        print(f"  {key}", flush=True)
        res = fn()
        done[key] = res
        save_ckpt(ck)
        return res

    # ---- 1. the overlapping-cohort sleeve (replication of the parent arm)
    for c in COST_BPS:
        arm(f"cohort_H6m_{int(c)}bps",
            lambda c=c: hpp.run_fixed(mkt, rb_dates, members, H, c))

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
        for i in range(len(ck["null_draws"]), args.nulls):
            print(f"  null draw {i + 1}/{args.nulls}", flush=True)
            nd_rb, nd_members = null_cohorts(panel, mkt["p_ix"], mkt["d_ix"],
                                             seed=1000 + i)
            res = hpp.run_fixed(mkt, nd_rb, nd_members, H, null_cost)
            ck["null_draws"].append({
                "seed": 1000 + i,
                "monthly_excess_mean_pct": res["monthly_excess_mean_pct"],
                "terminal_wealth": res["terminal_wealth"],
                "t_paired_vs_vw": res["t_paired_vs_vw"],
            })
            save_ckpt(ck)
        obs = done[f"cohort_H6m_{int(null_cost)}bps"]
        null_block = {"null_bar": nullbar.MODEL_NULL_BAR,
                      "shuffle": "target_rev_1m permuted WITHIN month over the "
                                 "admissible+revision-covered pool (uniform 50-draw); "
                                 "identical engine, filters, costs (25bps/side)",
                      "scope": "answers ranking-vs-random-from-pool, NOT pool-vs-market; "
                               "the rule has no fitted parameters, so a fitted-model "
                               "null does not exist for it",
                      "n_draws": len(ck["null_draws"]), "metrics": {}}
        for metric in ("monthly_excess_mean_pct", "terminal_wealth"):
            draws = np.array([d[metric] for d in ck["null_draws"]], dtype=float)
            o = float(obs[metric])
            null_block["metrics"][metric] = {
                "observed": o,
                "null": nullbar.summarise_null(draws),
                "percentile_of_observed": round(nullbar.percentile_of(o, draws), 4),
                "p_one_sided": round(nullbar.p_one_sided(o, draws), 4),
            }

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
            replication[key] = {"match": not drift, "drift": drift or None}

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

    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": hpp.git_head(),
        "python": platform.python_version(),
        "licence": "PRODUCT_EXPERIMENT",
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
        "replication_of_parent_fixed_H6m": replication,
        "arms": {},
        "fullreb_phase_spread": phases,
        "head_to_head": hh,
        "breakeven_cost": be,
        "subwindow_2022_2024": sub,
        "null_vs_random_from_pool": null_block,
        "sessions": mkt["n_days"], "permnos": int(mkt["n_perm"]),
    }

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

    co = receipt["arms"]["cohort_H6m_25bps"]
    fa = receipt["arms"]["cohort_H6m_falsifier_toxic_mktpark_25bps"]
    print("\nHEADLINE (25bps/side, 2015-02..2024-12):")
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
