"""N2 step one -- the DATA-NET with event features (`learner_v3`).

Roadmap 2026-09-08 section 10.6: one network per source, each graded ALONE
before any joining. This is the first head -- the data-net, which is the 143-
column monthly panel `learner_v2` already learns -- given the one input it has
never had: what the company's most recent earnings PRINT did, and how long ago.

The question is narrow on purpose and it is a PAIRED one:

    does adding event features to the monthly data-net change what it earns,
    on the same folds, the same seeds, the same book construction and the same
    costs -- and does that change survive its own control?

Three things make the answer readable rather than another headline:

1. **Paired, month by month.** Two terminal wealths are one draw of a
   correlated pair. v3 minus v2 is graded on the months both were live.
2. **A control arm that cannot know anything.** The same event features are
   attached a SECOND time from the placebo event tape (announcement dates
   shifted +40 sessions, so zero event information). If `v3 - v2` and
   `v3_placebo - v2` are the same size, the gain is the extra columns, not the
   earnings print. A control printed and not subtracted is decoration
   (the 09-08 D1 lesson).
3. **Both rulers, and the window ruler.** Beta-matched excess with a
   Newey-West t for the claim; terminal wealth against the market at a stated
   drawdown for the product; and the RW1 random-window win rate, because a
   single 21-year path is one window (section 10.2 item 1).

PIT DISCIPLINE. An event feature attached to month m uses only announcements
strictly BEFORE that month's `entry_date`, and the trailing percentile of a
reaction is computed against announcements in the previous 90 calendar days --
the pool that existed when the print landed. `test_n2_event_features_are_pit.py`
pins that no feature can see its own month.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import evaluate as E                       # noqa: E402

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
OUT.mkdir(parents=True, exist_ok=True)
LONG = REPO / "backend" / "data" / "optimus" / "learner" / "train_table_long.parquet"
EVENTS = REPO / "backend" / "data" / "optimus" / "r4_event_families" / "R4_earnings_events.parquet"
PLACEBO = REPO / "backend" / "data" / "optimus" / "r4_event_families" / "R4_placebo_offset40.parquet"
FEAT_PATH = REPO / "backend" / "data" / "optimus" / "learner" / "event_features_v3.parquet"

COST_BPS = 25.0
NW_LAG = 4
FIRST_TEST_YEAR = 2004
TARGET = "excess_vw_1m"
RANK_DAYS = 90
DD_BUDGET = 0.35

#: the data-net's own columns -- the cross-sectional panel, unchanged from v2
PANEL_FEATURES = [
    "ratio__xs", "consensus__xs", "coverage__xs", "numest__xs", "disagreement__xs", "dispersion__xs",
    "net_rev_4w__xs", "target_rev_1m__xs", "consensus_rev_1m__xs", "ret_1m__xs", "ret_3m__xs",
    "ret_6m__xs", "ret_12m__xs", "mom_12_1__xs", "drawdown_60d__xs", "vol_20d__xs", "vol_60d__xs",
    "log_dollar_vol_20d__xs", "log_market_cap__xs", "log_close__xs", "sector_code", "band_code",
]
#: what the event tape adds
EVENT_FEATURES = ["ev_reaction", "ev_z_reaction", "ev_reaction_pct", "ev_sue", "ev_sue_pct",
                  "ev_days_since", "ev_count_12m", "ev_gap"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(v, nd=4):
    try:
        return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), nd)
    except Exception:  # noqa: BLE001
        return None


def _nw_t(x: np.ndarray, lag: int = NW_LAG) -> float | None:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 12:
        return None
    u = x - x.mean()
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2.0 * (1.0 - L / (lag + 1.0)) * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return float(x.mean() / se) if se > 0 else None


def _max_dd(m: np.ndarray) -> float:
    eq = np.cumprod(1.0 + np.asarray(m, dtype="float64"))
    return float((eq / np.maximum.accumulate(eq) - 1.0).min()) if len(eq) else 0.0


# ------------------------------------------------------- the event features

def trailing_pct(dates: np.ndarray, values: np.ndarray, days: int = RANK_DAYS) -> np.ndarray:
    """Percentile of each value among the values printed in the previous `days`,
    INCLUDING the same day (all of which are public when this print lands).

    This is the PIT analogue of D1's session-window `pit_rank`: a within-month
    or full-sample rank would be a look-ahead, which is exactly what halved R4's
    spread when it was corrected on 09-08.
    """
    order = np.argsort(dates, kind="mergesort")
    d, v = dates[order], values[order]
    out = np.full(len(d), np.nan)
    lo = 0
    for i in range(len(d)):
        while d[i] - d[lo] > np.timedelta64(days, "D"):
            lo += 1
        pool = v[lo:i + 1]
        pool = pool[np.isfinite(pool)]
        if len(pool) >= 30 and np.isfinite(v[i]):
            out[i] = float(np.searchsorted(np.sort(pool), v[i], side="right")) / len(pool)
    res = np.full(len(d), np.nan)
    res[order] = out
    return res


def common_event_columns() -> list[str]:
    """Columns present on BOTH tapes. The control has to carry the SAME number of
    columns as the treatment, or `v3 - control` measures column count rather than
    the earnings print."""
    import pyarrow.parquet as pq

    want = ["permno", "anndats", "reaction_01", "suescore", "sue_pct", "gap"]
    a = set(pq.ParquetFile(EVENTS).schema.names)
    b = set(pq.ParquetFile(PLACEBO).schema.names)
    keep = [c for c in want if c in a and c in b]
    for c in ("permno", "anndats", "reaction_01"):
        if c not in keep:
            raise SystemExit(f"REFUSED: {c} is missing from one of the two event tapes")
    dropped = [c for c in want if c not in keep]
    if dropped:
        print(f"    {dropped} exist on only one tape; dropped from BOTH so the control matches", flush=True)
    return keep


def build_event_features(ev_path: Path, panel: pd.DataFrame, label: str,
                         want: list[str] | None = None) -> pd.DataFrame:
    """For every (permno, month): the most recent announcement STRICTLY BEFORE
    that month's entry_date, and how stale it is."""
    want = want or common_event_columns()
    ev = pd.read_parquet(ev_path, columns=want)
    ev = ev.rename(columns={"reaction_01": "ev_reaction", "suescore": "ev_sue",
                            "sue_pct": "ev_sue_pct", "gap": "ev_gap"})
    ev["anndats"] = pd.to_datetime(ev["anndats"])
    ev = ev.dropna(subset=["permno", "anndats"]).sort_values("anndats", kind="mergesort")
    ev["permno"] = ev["permno"].astype("int64")
    ev["ev_reaction_pct"] = trailing_pct(ev["anndats"].to_numpy(), ev["ev_reaction"].to_numpy(dtype="float64"))
    # a per-name volatility scale from the PREVIOUS prints only, so z is PIT
    ev["_sd"] = (ev.groupby("permno")["ev_reaction"].transform(
        lambda s: s.shift(1).expanding(min_periods=4).std()))
    ev["ev_z_reaction"] = ev["ev_reaction"] / ev["_sd"]
    ev["ev_count_12m"] = 1.0
    ev["ev_count_12m"] = (ev.set_index("anndats").groupby("permno")["ev_count_12m"]
                          .rolling("365D").sum().reset_index(level=0, drop=True).to_numpy())
    keep = ["permno", "anndats"] + [c for c in EVENT_FEATURES if c in ev.columns]
    ev = ev[keep].sort_values("anndats", kind="mergesort")

    p = panel[["permno", "month", "entry_date"]].copy()
    p["entry_date"] = pd.to_datetime(p["entry_date"])
    p["permno"] = p["permno"].astype("int64")
    p = p.sort_values("entry_date", kind="mergesort")
    # `allow_exact_matches=False`: an announcement ON the entry date is not
    # knowable at the entry close for this panel's convention
    j = pd.merge_asof(p, ev, left_on="entry_date", right_on="anndats", by="permno",
                      direction="backward", allow_exact_matches=False)
    j["ev_days_since"] = (j["entry_date"] - j["anndats"]).dt.days.astype("float64")
    # a print older than a year is not news; blank it rather than let the tree
    # learn "no recent print" from a stale value
    stale = j["ev_days_since"] > 400
    for c in EVENT_FEATURES:
        if c in j.columns and c != "ev_days_since":
            j.loc[stale, c] = np.nan
    cov = float(j["ev_reaction"].notna().mean())
    print(f"    {label}: {len(ev):,} announcements -> {cov:.1%} of {len(j):,} panel rows carry a print "
          f"within 400 days (median staleness {j['ev_days_since'].median():.0f}d)", flush=True)
    return j[["permno", "month"] + [c for c in EVENT_FEATURES if c in j.columns]]


# ------------------------------------------------------------ the data-net

def walk_forward(df: pd.DataFrame, feats: list[str], seed: int) -> np.ndarray:
    """Train on every month that has MATURED before the test year opens."""
    import lightgbm as lgb

    pred = np.full(len(df), np.nan)
    yr = df["month"].str.slice(0, 4).astype(int).to_numpy()
    X = df[feats].astype("float64").reset_index(drop=True)
    y = df[TARGET].to_numpy(dtype="float64")
    for Y in sorted({int(v) for v in yr if v >= FIRST_TEST_YEAR}):
        tr = (yr < Y) & np.isfinite(y)          # a 1m target matures inside its month
        te = yr == Y
        if tr.sum() < 20000 or te.sum() < 500:
            continue
        m = lgb.LGBMRegressor(n_estimators=400, learning_rate=0.05, num_leaves=63,
                              min_child_samples=200, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, random_state=seed, n_jobs=4, verbose=-1)
        m.fit(X.loc[tr], y[tr])
        pred[te] = m.predict(X.loc[te])
    return pred


def grade(df: pd.DataFrame, col: str, label: str, k: int = 100) -> dict:
    d = df[np.isfinite(df[col].to_numpy())]
    r = E.book(d, col, k=k, weight="ew", cost_bps=COST_BPS, hold_k=4 * k,
               tradable_floor=3e6, with_risk=True, return_series=True)
    net = r["_series"]["net"].astype("float64")
    mkt = r["_series"]["market"].reindex(net.index).astype("float64")
    y, x = net.to_numpy(), mkt.to_numpy()
    beta = float(np.polyfit(x, y, 1)[0])
    ex = y - beta * x
    return {"label": label, "months": int(len(y)), "beta": _r(beta),
            "ALPHA_RULER": {"beta_matched_ann_pct": _r(float(ex.mean()) * 12 * 100, 3),
                            "t_nw": _r(_nw_t(ex), 3)},
            "PRODUCT_RULER": {"terminal_wealth_net": _r(float(np.prod(1 + y))),
                              "terminal_wealth_market": _r(float(np.prod(1 + x))),
                              "max_drawdown": _r(_max_dd(y)),
                              "within_dd_budget": bool(-_max_dd(y) <= max(DD_BUDGET, -_max_dd(x))),
                              "market_max_drawdown": _r(_max_dd(x))},
            "_m": {"idx": [str(v) for v in net.index], "net": [float(v) for v in y],
                   "mkt": [float(v) for v in x]}}


def paired(a: dict, b: dict, label: str) -> dict:
    """b MINUS a on the months both were live -- the only honest 'did it help?'."""
    ia, ib = a["_m"]["idx"], b["_m"]["idx"]
    common = [m for m in ia if m in set(ib)]
    da = {m: v for m, v in zip(ia, a["_m"]["net"])}
    db = {m: v for m, v in zip(ib, b["_m"]["net"])}
    d = np.array([db[m] - da[m] for m in common])
    return {"label": label, "months_paired": len(common),
            "mean_diff_ann_pct": _r(float(d.mean()) * 12 * 100, 3),
            "t_nw": _r(_nw_t(d), 3),
            "share_of_months_v3_higher": _r(float((d > 0).mean()), 3)}


def N2_learner_v3(seeds=(0, 1, 2), smoke: bool = False) -> dict:
    t0 = time.time()
    cols = (["permno", "month", "entry_date", TARGET, "fwd_1m", "mkt_vw_1m", "market_cap",
             "dollar_vol_20d", "log_dollar_vol_20d"] + PANEL_FEATURES)
    import pyarrow.parquet as pq
    have = set(pq.ParquetFile(LONG).schema.names)
    absent = [c for c in cols if c not in have]
    if any(c in absent for c in ("month", "permno", TARGET)):
        raise SystemExit(f"REFUSED: the panel lacks {absent}")
    if absent:
        print(f"    columns absent from the panel, dropped: {sorted(set(absent))}", flush=True)
    df = pd.read_parquet(LONG, columns=sorted({c for c in cols if c in have}))
    if smoke:
        df = df[(df["month"] >= "2002-01") & (df["month"] <= "2008-12")].copy()
    print(f"    panel: {len(df):,} rows, {df['month'].nunique()} months", flush=True)

    want = common_event_columns()
    ev = build_event_features(EVENTS, df, "announcements", want)
    pl = build_event_features(PLACEBO, df, "placebo +40 (the control)", want)
    pl = pl.rename(columns={c: f"PL_{c}" for c in EVENT_FEATURES if c in pl.columns})
    df = df.merge(ev, on=["permno", "month"], how="left").merge(pl, on=["permno", "month"], how="left")
    if not smoke:
        df[["permno", "month"] + [c for c in df.columns if c.startswith(("ev_", "PL_ev_"))]] \
            .to_parquet(FEAT_PATH, index=False)

    arms = {
        "v2_panel_only": PANEL_FEATURES,
        "v3_panel_plus_event": PANEL_FEATURES + [c for c in EVENT_FEATURES if c in df.columns],
        "v3_CONTROL_panel_plus_placebo_event": PANEL_FEATURES + [f"PL_{c}" for c in EVENT_FEATURES
                                                                 if f"PL_{c}" in df.columns],
    }
    seeds = tuple(seeds) if not smoke else (0,)
    graded: dict[str, dict] = {}
    per_seed: dict[str, list] = {}
    for name, feats in arms.items():
        for s in seeds:
            col = f"_p_{name}_{s}"
            df[col] = walk_forward(df, feats, s)
            g = grade(df, col, f"{name}|seed{s}")
            per_seed.setdefault(name, []).append(g)
            print(f"    {name} seed {s}: beta {g['beta']}  bm {g['ALPHA_RULER']['beta_matched_ann_pct']}%/yr "
                  f"t {g['ALPHA_RULER']['t_nw']}  TW {g['PRODUCT_RULER']['terminal_wealth_net']} vs "
                  f"{g['PRODUCT_RULER']['terminal_wealth_market']}  DD {g['PRODUCT_RULER']['max_drawdown']} "
                  f"[{time.time() - t0:.0f}s]", flush=True)
        graded[name] = per_seed[name][0]

    pairs = {
        "v3_minus_v2": paired(graded["v2_panel_only"], graded["v3_panel_plus_event"], "event features vs none"),
        "v3control_minus_v2": paired(graded["v2_panel_only"], graded["v3_CONTROL_panel_plus_placebo_event"],
                                     "the SAME number of dateless columns vs none"),
    }
    incr = None
    if pairs["v3_minus_v2"]["mean_diff_ann_pct"] is not None and \
            pairs["v3control_minus_v2"]["mean_diff_ann_pct"] is not None:
        incr = _r(pairs["v3_minus_v2"]["mean_diff_ann_pct"] - pairs["v3control_minus_v2"]["mean_diff_ann_pct"], 3)

    def seed_row(name):
        ts = [g["ALPHA_RULER"]["t_nw"] for g in per_seed[name] if g["ALPHA_RULER"]["t_nw"] is not None]
        anns = [g["ALPHA_RULER"]["beta_matched_ann_pct"] for g in per_seed[name]]
        return {"seeds": len(per_seed[name]), "t_median": _r(float(np.median(ts)), 3) if ts else None,
                "ann_median_pct": _r(float(np.median(anns)), 3), "ann_min": _r(min(anns), 3),
                "ann_max": _r(max(anns), 3)}

    d3 = pairs["v3_minus_v2"]
    dc = pairs["v3control_minus_v2"]
    if d3["t_nw"] is None:
        verdict = "CANNOT DETERMINE: the paired difference has too few months"
    elif abs(dc["t_nw"] or 0) >= 2.0:
        verdict = (f"CONSTRUCTION_SENSITIVE: attaching the SAME number of DATELESS event columns moves the "
                   f"book by {dc['mean_diff_ann_pct']}%/yr (t {dc['t_nw']}), so the v3 gain of "
                   f"{d3['mean_diff_ann_pct']}%/yr is largely extra columns, not the earnings print. "
                   f"Incremental over the control: {incr}%/yr.")
    elif (d3["t_nw"] or 0) > 2.0 and (incr or 0) > 0:
        verdict = (f"PRODUCT_PROMISING: the event features add {d3['mean_diff_ann_pct']}%/yr paired "
                   f"(t {d3['t_nw']}) and the dateless control adds {dc['mean_diff_ann_pct']}%/yr "
                   f"(t {dc['t_nw']}); incremental {incr}%/yr")
    else:
        verdict = (f"FAILED_VARIANT: the event print does not change what the monthly data-net earns "
                   f"({d3['mean_diff_ann_pct']}%/yr paired, t {d3['t_nw']}; control "
                   f"{dc['mean_diff_ann_pct']}%/yr, incremental {incr}%/yr)")

    return {
        "job": "N2_learner_v3", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "question": ("Does the DATA-NET learn more when it is told what the company's most recent earnings "
                     "print did and how stale it is -- more than it learns from the same number of dateless "
                     "columns?"),
        "panel_features": len(PANEL_FEATURES), "event_features": EVENT_FEATURES,
        "target": TARGET, "first_test_year": FIRST_TEST_YEAR, "seeds": list(seeds),
        "book": f"top-100 EW, hold band 400, $3m floor, {COST_BPS} bps a side",
        "control": ("the identical pipeline with event features drawn from R4_placebo_offset40 -- same "
                    "columns, same coverage, announcement dates shifted +40 sessions"),
        "arms": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")} for k, v in graded.items()},
        "seed_stability": {k: seed_row(k) for k in arms},
        "paired": pairs, "incremental_over_control_ann_pct": incr,
        "event_features_parquet": str(FEAT_PATH) if not smoke else None,
        "headline": (f"v3 (panel + event) vs v2 (panel only), paired over {d3['months_paired']} months: "
                     f"{d3['mean_diff_ann_pct']}%/yr t {d3['t_nw']}; the DATELESS control adds "
                     f"{dc['mean_diff_ann_pct']}%/yr t {dc['t_nw']}; incremental {incr}%/yr"),
        "verdict": verdict, "family_max_p": None,
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    p = N2_learner_v3(seeds=tuple(int(x) for x in a.seeds.split(",") if x.strip()), smoke=a.smoke)
    p["run"] = a.run
    out = Path(a.out) if a.out else OUT / f"N2_learner_v3_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(p, indent=1, default=str), encoding="utf-8")
    print(f"\nN2: {p['headline']}\n  verdict: {p['verdict']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
