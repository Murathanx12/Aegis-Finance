"""Does analyst revision FLOW rank the cross-section? Sweep, rule, and a frozen book.

    python -m scripts.revision_flow_sweep                  # sweep + rule + receipt
    python -m scripts.revision_flow_sweep --freeze-books   # ...and freeze v0 + twin

Q-4 / Q-10 in `docs/RESEARCH_QUEUE.md`, chunk C2 of
`docs/HANDOFF_2026-09-25_FABLE_TO_OPUS_BUILD_PLAN.md`. PRODUCT_EXPERIMENT: no
significance gate, and nothing here is a RESEARCH_CLAIM.

WHAT RUNS
=========
1. THE SWEEP. `xs_ranker.walk_forward` with and without the five flow columns
   (`revision_flow.FLOW_COLUMNS`) as extra features; horizons 5/21/63 sessions;
   top-k at k = 20/50/100. Printed FIRST, before any t (CLAUDE.md protocol 11):
   by-year, leave-one-year-out, the WORST breadth cell, small vs large+mid.
2. THE RULE (Murat's). Each month-end, buy the top-k eligible names by
   `net_raises * n_firms` among names with >= 3 firms acting in 90 days; hold
   21 or 63 sessions; net of `xs_ranker.round_trip_bps` by liquidity band; by
   year and vs SPY (SPY from the same bars, stamped via `learner.benchmark`).
3. THE BOOKS (`--freeze-books`). `revision_flow_v0` = top-20 by the rule today,
   equal weight; `revision_flow_v0_random_twin` = 20 random names from the SAME
   eligible >=3-firm set, `default_rng(20260925)`. Frozen through the current
   `llm_portfolio.freeze` + `append_book` regardless of the sweep's sign.

THE SURVIVORSHIP TRAP THIS SWEEP HAD TO STEP AROUND
===================================================
The revision parquet was pulled in 2026-09 for names alive then: of 1,784
delisted symbols in the survivorship-free bar panel, **64** carry any revision
history. On the full panel, "flow is NaN" therefore means "this name dies", and
a LightGBM arm handed the flow columns would learn delisting from the future.
So both arms are fitted on the COVERED universe only (tickers present in the
parquet, 64 of them dead) -- the with/without comparison is fair between arms,
and both arms are survivor-selected. The receipt carries the audit of exactly
that universe. The rule has the same property by construction (>= 3 firms).

For a covered name a quarter with no revision is a TRUE zero count, so
`net_raises`, `n_firms`, `n_events` are 0 there (not an imputation: the name was
covered and nobody acted); `median_target_change` and `days_since_last` stay NaN.

SAMPLING, SAID OUT LOUD
=======================
Decision dates for the sweep are every `--step` (default 5) sessions, so the
panel fits in memory next to other jobs and the run stays under ~20 minutes.
The purge and every blocking unit are therefore in DECISION DATES:
`ceil(H / step)` dates is one horizon. Features are computed on the full daily
series and only then sampled, so no feature sees a coarser history.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _cfg                        # noqa: E402
from backend.services import revision_flow as RF          # noqa: E402
from backend.services import xs_ranker as XR              # noqa: E402

REVISIONS_PATH = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst" / "target_revisions.parquet"
OUT_DIR = Path(_cfg.OPTIMUS_LEDGER_DIR) / "analyst"

HORIZONS = (5, 21, 63)
BREADTH_K = (20, 50, 100)
RULE_HORIZONS = (21, 63)
RULE_K = (20, 50)
MIN_FIRMS = 3
BOOK_SEED = 20260925
BOOK_K = 20
CHUNK = 400
KEEP_FEATURE_COLS = ("symbol", "date", "eligible", "median_dollar_vol", "close",
                     *XR.FEATURES)


# ─────────────────────────────── the panel ──────────────────────────────────

def _read_chunk(paths: list[Path], symbols: list[str]) -> pd.DataFrame:
    frames = []
    for p in paths:
        df = pd.read_parquet(p, filters=[("symbol", "in", symbols)])
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.drop_duplicates(subset=["symbol", "date"], keep="first")
    return out.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def build_sampled_panel(paths: list[Path], symbols: list[str], keep_dates: set,
                        horizons: tuple[int, ...], *, chunk: int = CHUNK) -> pd.DataFrame:
    """Features on the full daily series per symbol chunk, then sampled to
    `keep_dates`. Forward raw returns `fwd_ret_<H>` use xs_ranker's convention
    (enter t+1 open, exit close of t+1+H). SPY rides in every chunk for beta."""
    keep = pd.DatetimeIndex(sorted(keep_dates))
    syms = [s for s in symbols if s != "SPY"]
    out = []
    for i in range(0, len(syms), chunk):
        part = syms[i:i + chunk] + ["SPY"]
        b = _read_chunk(paths, part)
        if b.empty:
            continue
        f = XR.mark_eligible(XR.build_features(b))
        g = f.groupby("symbol", sort=False)
        entry = g["open"].shift(-1)
        for h in horizons:
            f[f"fwd_ret_{h}"] = g["close"].shift(-(h + 1)) / entry - 1.0
        if i > 0:
            f = f[f["symbol"] != "SPY"]
        cols = [c for c in KEEP_FEATURE_COLS if c in f.columns] + \
               [f"fwd_ret_{h}" for h in horizons]
        f = f.loc[f["date"].isin(keep), cols]
        for c in f.columns:
            if f[c].dtype == np.float64 and c not in ("median_dollar_vol", "close"):
                f[c] = f[c].astype(np.float32)
        out.append(f)
        print(f"  features: {min(i + chunk, len(syms)):,}/{len(syms):,} symbols", flush=True)
        del b
    return pd.concat(out, ignore_index=True)


def attach_flow(panel: pd.DataFrame, revisions: pd.DataFrame, covered: set) -> pd.DataFrame:
    flow = RF.compute_panel(revisions, panel["date"].unique())
    flow = flow.rename(columns={"ticker": "symbol"})
    out = panel.merge(flow, on=["symbol", "date"], how="left")
    cov = out["symbol"].isin(covered)
    for c in ("net_raises", "n_firms", "n_events"):
        # a covered name with no event in the window: a TRUE zero, not a fill
        out.loc[cov & out[c].isna(), c] = 0.0
    for c in RF.FLOW_COLUMNS:
        out[c] = out[c].astype(np.float32)
    return out


def with_target(panel: pd.DataFrame, h: int) -> pd.DataFrame:
    """xs_ranker.build_target's relative target, on an already-sampled panel."""
    p = panel.copy()
    p["fwd_ret"] = p[f"fwd_ret_{h}"].astype(float)
    bench = p.loc[p["eligible"], ["date", "fwd_ret"]].groupby("date")["fwd_ret"].mean()
    p["bench_fwd_ret"] = p["date"].map(bench)
    p["fwd_rel"] = p["fwd_ret"] - p["bench_fwd_ret"]
    elig = p["eligible"] & p["fwd_rel"].notna()
    p["y"] = np.nan
    p.loc[elig, "y"] = p.loc[elig].groupby("date")["fwd_rel"].rank(pct=True, method="average")
    return p


# ───────────────────────────── measurement ──────────────────────────────────

def block_t(dated: pd.Series, h_dates: int) -> dict:
    """t across blocks of `h_dates` consecutive decision dates -- one horizon wide,
    so no two blocks share a forward window. Derived from the horizon, never a
    calendar month (feedback_a_t_whose_bias_depends_on_the_swept_parameter)."""
    s = dated.dropna().sort_index()
    if s.empty:
        return {"n_date_blocks": 0, "t_horizon_blocks": None}
    rank = pd.Series(np.arange(len(s)) // max(1, h_dates), index=s.index)
    bm = s.groupby(rank.values).mean()
    n = int(len(bm))
    if n < 2:
        return {"n_date_blocks": n, "t_horizon_blocks": None}
    se = float(bm.std(ddof=1) / math.sqrt(n))
    return {"n_date_blocks": n, "block_width_dates": int(max(1, h_dates)),
            "t_horizon_blocks": float(bm.mean() / se) if se > 0 else None}


def per_date_net(oos: pd.DataFrame, k: int) -> pd.Series:
    rows = {}
    for d, grp in oos.groupby("date"):
        top = grp.nlargest(k, "score")
        if len(top) < k:
            continue
        bps = float(np.mean([XR.round_trip_bps(v) for v in top["median_dollar_vol"]]))
        rows[pd.Timestamp(d)] = float(top["fwd_rel"].mean()) - bps / 1e4
    return pd.Series(rows, dtype=float)


def cell(oos: pd.DataFrame, k: int, h_dates: int) -> dict:
    bt = XR.top_k_backtest(oos, k=k, horizon=h_dates)
    if bt.get("status") == "REFUSED":
        return bt
    bt.update(block_t(per_date_net(oos, k), h_dates))
    for key in ("worst_date", "best_date"):
        bt.pop(key, None)
    return bt


def run_arm(panel_h: pd.DataFrame, features: list[str], h_dates: int) -> tuple[dict, pd.DataFrame]:
    saved = XR.PURGE_SESSIONS
    XR.PURGE_SESSIONS = h_dates + 1          # one horizon, in decision dates, +1
    try:
        oos, folds = XR.walk_forward(panel_h, features=features)
    finally:
        XR.PURGE_SESSIONS = saved
    oos["band"] = oos["median_dollar_vol"].map(XR.liquidity_band)
    cells = {k: cell(oos, k, h_dates) for k in BREADTH_K}
    split = {
        "small": cell(oos[oos["band"] == "small"], 20, h_dates),
        "largemid": cell(oos[oos["band"] != "small"], 20, h_dates),
    }
    ic = XR._information_coefficient(oos)
    ic.pop("ic_note", None)
    return ({"by_k": cells, "small_vs_largemid_k20": split, **ic,
             "n_oos_rows": int(len(oos)),
             "folds": [{"train_end": str(f.train_end.date()), "test_start": str(f.test_start.date()),
                        "test_end": str(f.test_end.date()), "n_train": f.n_train,
                        "n_test": f.n_test, "refused": f.refused} for f in folds]}, oos)


def _pct(v) -> str:
    return "   n/a" if v is None or not np.isfinite(v) else f"{v*100:+6.2f}%"


def print_h(h: int, res: dict) -> None:
    print(f"\n=== H={h} sessions ===")
    years = sorted({y for arm in res.values() for c in arm["by_k"].values()
                    for y in (c.get("by_year") or {})})
    print("  BY YEAR (mean net rel per hold, k=20/50/100)")
    print("    arm       k   " + " ".join(f"{y:>8}" for y in years))
    for arm, r in res.items():
        for k, c in r["by_k"].items():
            by = c.get("by_year") or {}
            print(f"    {arm:<8} {k:<4}" + " ".join(
                f"{_pct(by.get(y, {}).get('mean_net')):>8}" for y in years))
    print("  LEAVE-ONE-YEAR-OUT (worst)")
    for arm, r in res.items():
        for k, c in r["by_k"].items():
            print(f"    {arm:<8} k={k:<4} mean {_pct(c.get('mean_net_rel_21d'))}  "
                  f"drop {c.get('loo_worst_dropped_year')}: {_pct(c.get('loo_worst_mean_net'))}")
    print("  WORST BREADTH CELL")
    for arm, r in res.items():
        w = min(r["by_k"].values(), key=lambda c: c.get("mean_net_rel_21d", 9))
        print(f"    {arm:<8} k={w.get('k')} {_pct(w.get('mean_net_rel_21d'))} "
              f"(loo-worst {_pct(w.get('loo_worst_mean_net'))})")
    print("  SMALL vs LARGE+MID (k=20 within band)")
    for arm, r in res.items():
        s = r["small_vs_largemid_k20"]
        print(f"    {arm:<8} small {_pct(s['small'].get('mean_net_rel_21d'))} "
              f"(loo {_pct(s['small'].get('loo_worst_mean_net'))})   largemid "
              f"{_pct(s['largemid'].get('mean_net_rel_21d'))} "
              f"(loo {_pct(s['largemid'].get('loo_worst_mean_net'))})")
    print("  ...and only now the t (blocks one horizon wide)")
    for arm, r in res.items():
        ts = ", ".join(f"k={k} t {c.get('t_horizon_blocks') or float('nan'):+.2f}"
                       f"/{c.get('n_date_blocks')}blk" for k, c in r["by_k"].items())
        print(f"    {arm:<8} IC {r.get('ic_mean') or float('nan'):+.4f}  {ts}")


# ─────────────────────────────── the rule ───────────────────────────────────

def rule_backtest(panel: pd.DataFrame, rule_dates: list, spy_fwd: dict) -> dict:
    from learner import benchmark as bm
    out = {}
    for h in RULE_HORIZONS:
        for k in RULE_K:
            rows = []
            for d in rule_dates:
                day = panel[(panel["date"] == d) & panel["eligible"]
                            & panel[f"fwd_ret_{h}"].notna()]
                cov = day[day["n_firms"] >= MIN_FIRMS].copy()
                if len(cov) < k:
                    continue
                cov["rule_score"] = cov["net_raises"] * cov["n_firms"]
                top = cov.nlargest(k, "rule_score")
                bps = float(np.mean([XR.round_trip_bps(v) for v in top["median_dollar_vol"]]))
                gross = float(top[f"fwd_ret_{h}"].mean())
                spy = spy_fwd.get(h, {}).get(pd.Timestamp(d))
                rows.append({"date": pd.Timestamp(d), "gross": gross, "net": gross - bps / 1e4,
                             "cost_bps": bps, "spy": spy,
                             "covered_ew": float(cov[f"fwd_ret_{h}"].mean()),
                             "xs_ew": float(day[f"fwd_ret_{h}"].mean()),
                             "n_covered": int(len(cov))})
            if not rows:
                out[f"H{h}_k{k}"] = {"status": "REFUSED", "why": "no month-end had k covered names"}
                continue
            df = pd.DataFrame(rows).set_index("date").sort_index()
            df["vs_spy"] = df["net"] - df["spy"]
            df["vs_covered_ew"] = df["net"] - df["covered_ew"]
            step = max(1, round(h / 21))
            nov = df.iloc[::step]                   # non-overlapping holds
            by_year = {str(y): {"mean_net": float(g["net"].mean()),
                                "mean_spy": float(g["spy"].mean()),
                                "mean_vs_spy": float(g["vs_spy"].mean()),
                                "mean_vs_covered_ew": float(g["vs_covered_ew"].mean()),
                                "n_months": int(len(g))}
                       for y, g in df.groupby(df.index.year)}
            loo = {y: float(df.loc[df.index.year != int(y), "vs_spy"].mean()) for y in by_year}
            spy_series = nov["spy"].dropna()
            stamp = bm.matched(spy_series, "spy_bars_same_window",
                               construction=(f"SPY from the same local bars, entered at the "
                                             f"open after each month-end, exited at the close "
                                             f"{h} sessions later; price-only (no dividends); "
                                             f"non-overlapping every {step} month-end(s)"),
                               freq="M").stamp()
            out[f"H{h}_k{k}"] = {
                "horizon_sessions": h, "k": k, "n_months": int(len(df)),
                "by_year": by_year, "leave_one_year_out_vs_spy": loo,
                "loo_worst_vs_spy": min(loo.values()) if loo else None,
                "mean_net_per_hold": float(df["net"].mean()),
                "mean_spy_per_hold": float(df["spy"].mean()),
                "mean_vs_spy_per_hold": float(df["vs_spy"].mean()),
                "mean_vs_covered_ew_per_hold": float(df["vs_covered_ew"].mean()),
                "mean_cost_bps": float(df["cost_bps"].mean()),
                "hit_rate_vs_spy": float((df["vs_spy"] > 0).mean()),
                **block_t(df["vs_spy"], step),
                "compounded_nonoverlap": {
                    "strategy_net": float(bm.compound(nov["net"]) - 1.0),
                    "spy": float(bm.compound(spy_series) - 1.0),
                    "n_holds": int(len(nov)),
                    "span": [str(nov.index.min().date()), str(nov.index.max().date())],
                },
                "market_benchmark": stamp,
            }
    return out


def print_rule(rule: dict) -> None:
    print("\n=== THE RULE: top-k by net_raises x n_firms (>=3 firms), month-end ===")
    for key, r in rule.items():
        if r.get("status") == "REFUSED":
            print(f"  {key}: REFUSED {r['why']}")
            continue
        print(f"  {key}: by year  net / SPY / vs SPY / vs covered-EW")
        for y, b in r["by_year"].items():
            print(f"     {y}  {_pct(b['mean_net'])} {_pct(b['mean_spy'])} "
                  f"{_pct(b['mean_vs_spy'])} {_pct(b['mean_vs_covered_ew'])}  ({b['n_months']} mo)")
        c = r["compounded_nonoverlap"]
        print(f"     mean vs SPY {_pct(r['mean_vs_spy_per_hold'])}/hold, loo-worst "
              f"{_pct(r['loo_worst_vs_spy'])}, vs covered-EW {_pct(r['mean_vs_covered_ew_per_hold'])}; "
              f"compounded {c['span'][0]}..{c['span'][1]}: {c['strategy_net']*100:+.1f}% vs SPY "
              f"{c['spy']*100:+.1f}%; t {r.get('t_horizon_blocks') or float('nan'):+.2f} on "
              f"{r['n_date_blocks']} blocks")


# ─────────────────────────────── the books ──────────────────────────────────

def freeze_books(panel: pd.DataFrame, revisions: pd.DataFrame, *, today: date) -> dict:
    from backend.services import llm_portfolio as LP
    last = panel["date"].max()
    day = panel[(panel["date"] == last) & panel["eligible"]].set_index("symbol")
    flow = RF.compute(revisions, asof=pd.Timestamp(today))
    score = RF.rule_score(flow, min_firms=MIN_FIRMS)
    pool = score[score.index.isin(day.index)].sort_values(ascending=False, kind="mergesort")
    if len(pool) < BOOK_K:
        raise SystemExit(f"REFUSED: only {len(pool)} eligible names with >= {MIN_FIRMS} firms")
    top = pool.head(BOOK_K)
    rng = np.random.default_rng(BOOK_SEED)
    twin = sorted(rng.choice(np.array(sorted(pool.index)), size=BOOK_K, replace=False).tolist())
    w = 1.0 / BOOK_K
    common = {"objective": ("Relative P&L vs SPY over 21 sessions, long-only equal weight, "
                            "net of band round-trip cost"),
              "model": "rule:revision_flow_v0", "horizon_days": [1, 5, 21, 126]}
    books = {
        "revision_flow_v0": {
            **common, "name": "revision_flow_v0",
            "strategy": (f"PRODUCT_EXPERIMENT; kind personal. Top-{BOOK_K} xs_ranker-eligible "
                         f"names (liquidity floor, bars asof {last.date()}) by net_raises x n_firms "
                         f"over the 90 days strictly before {today}, among names with >= {MIN_FIRMS} "
                         f"firms acting; equal weight; 21-session cadence. Frozen regardless of "
                         f"the sweep's sign (build plan C2 step 7)."),
            "positions": [{"ticker": t, "weight": w,
                           "thesis": (f"net_raises {int(flow.loc[t, 'net_raises'])} x n_firms "
                                      f"{int(flow.loc[t, 'n_firms'])} = {int(s)}; median target "
                                      f"change {flow.loc[t, 'median_target_change']:+.1%}")}
                          for t, s in top.items()]},
        "revision_flow_v0_random_twin": {
            **common, "name": "revision_flow_v0_random_twin",
            "strategy": (f"PRODUCT_EXPERIMENT; kind personal; CONTROL for revision_flow_v0. "
                         f"{BOOK_K} names drawn uniformly from the SAME pool (eligible, >= "
                         f"{MIN_FIRMS} firms, {len(pool)} names) with default_rng({BOOK_SEED}); "
                         f"equal weight; 21-session cadence."),
            "positions": [{"ticker": t, "weight": w, "thesis": "random twin draw"} for t in twin]},
    }
    existing = {(b.get("name"), b.get("asof")) for b in LP.read_books()}
    out = {}
    for name, bk in books.items():
        rec = LP.freeze(bk, today=today)
        if (rec["name"], rec["asof"]) in existing:
            out[name] = {"book_id": rec["book_id"], "status": "ALREADY_FROZEN_TODAY"}
            continue
        LP.append_book(rec)
        out[name] = {"book_id": rec["book_id"], "status": "FROZEN",
                     "tickers": [p["ticker"] for p in rec["positions"]]}
    out["pool_size"] = int(len(pool))
    out["bars_asof"] = str(last.date())
    out["books_path"] = str(LP.books_path())
    return out


# ─────────────────────────────────── main ───────────────────────────────────

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=5, help="sessions between sweep decision dates")
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--horizons", default=",".join(map(str, HORIZONS)))
    ap.add_argument("--freeze-books", action="store_true")
    ap.add_argument("--skip-sweep", action="store_true")
    ap.add_argument("--max-symbols", type=int, default=0, help="smoke runs only")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    horizons = tuple(int(h) for h in a.horizons.split(",") if h.strip())
    all_h = tuple(sorted(set(horizons) | set(RULE_HORIZONS)))

    revisions = pd.read_parquet(REVISIONS_PATH)
    covered = set(revisions["ticker"].astype(str).str.upper())
    paths = XR.survivorship_free_paths()
    dates_all = pd.DatetimeIndex(sorted(pd.read_parquet(paths[0], columns=["date"])["date"].unique()))
    dates_all = dates_all[dates_all >= pd.Timestamp(a.start)]
    sweep_dates = set(dates_all[::a.step])
    month_end = pd.Series(dates_all).groupby(dates_all.to_period("M")).max()
    rule_dates = sorted(month_end.values)
    keep = sweep_dates | {pd.Timestamp(d) for d in rule_dates} | {dates_all.max()}

    symbols = sorted(set(pd.concat([pd.read_parquet(p, columns=["symbol"])["symbol"]
                                    for p in paths]).unique()) & (covered | {"SPY"}))
    if a.max_symbols:
        symbols = symbols[:a.max_symbols] + ["SPY"]
    print(f"panels: {[p.name for p in paths]}; covered universe {len(symbols):,} symbols; "
          f"{len(sweep_dates)} sweep dates (every {a.step}), {len(rule_dates)} month-ends", flush=True)

    panel = build_sampled_panel(paths, symbols, keep, all_h)
    spy = panel[panel["symbol"] == "SPY"].set_index("date")
    spy_fwd = {h: spy[f"fwd_ret_{h}"].dropna().to_dict() for h in RULE_HORIZONS}
    panel = attach_flow(panel, revisions, covered)
    print(f"panel {len(panel):,} rows in {time.time()-t0:.0f}s", flush=True)

    # survivorship of exactly this universe, read from the bars' last dates
    last = pd.concat([pd.read_parquet(p, columns=["symbol", "date"],
                                      filters=[("symbol", "in", symbols)]) for p in paths])
    audit = XR.survivorship_audit(last.drop_duplicates())
    del last
    print(f"survivorship (covered universe): {audit['verdict'][:110]}")

    flow_cols = list(RF.FLOW_COLUMNS)
    sweep = {}
    if not a.skip_sweep:
        sw = panel[panel["date"].isin(sweep_dates)]
        for h in horizons:
            h_dates = max(1, math.ceil(h / a.step))
            ph = with_target(sw, h)
            res = {}
            for arm, feats in (("base", list(XR.FEATURES)),
                               ("flow", list(XR.FEATURES) + flow_cols)):
                r, _ = run_arm(ph, feats, h_dates)
                res[arm] = r
                print(f"  H={h} {arm}: {r['n_oos_rows']:,} OOS rows "
                      f"({time.time()-t0:.0f}s)", flush=True)
            sweep[h] = res
            print_h(h, res)

    rule = rule_backtest(panel, rule_dates, spy_fwd)
    print_rule(rule)

    books = freeze_books(panel, revisions, today=date.today()) if a.freeze_books else None
    if books:
        print(f"\nBOOKS: {json.dumps(books, default=str)[:600]}")

    # the one-line reading, derived -- worst cell and LOO before any t
    lines = []
    for h, res in sweep.items():
        b, f = res["base"]["by_k"], res["flow"]["by_k"]
        wb = min(c.get("mean_net_rel_21d", 9) for c in b.values())
        wf = min(c.get("mean_net_rel_21d", 9) for c in f.values())
        lb = min((c.get("loo_worst_mean_net") for c in b.values()
                  if c.get("loo_worst_mean_net") is not None), default=None)
        lf = min((c.get("loo_worst_mean_net") for c in f.values()
                  if c.get("loo_worst_mean_net") is not None), default=None)
        lines.append(f"H={h}: worst cell base {_pct(wb)} vs flow {_pct(wf)}; "
                     f"LOO-worst base {_pct(lb)} vs flow {_pct(lf)} (net rel per hold)")
    verdict = " | ".join(lines) or "sweep skipped"

    receipt = {
        "receipt": "revision_flow_sweep", "licence": "PRODUCT_EXPERIMENT",
        "llm_spend_usd": 0.0,
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - t0, 1),
        "question": "Q-4/Q-10: does analyst revision FLOW rank the cross-section, and does "
                    "the simple net_raises x n_firms rule beat SPY net of cost?",
        "universe": {
            "definition": "xs_ranker survivorship-free bars INTERSECT tickers in the revision "
                          "parquet (covered universe); SPY for beta and the market leg",
            "n_symbols": len(symbols),
            "why_not_the_full_panel": "only 64 of 1,784 delisted names have revision history; "
                                      "on the full panel NaN flow would encode future delisting",
            "survivorship_audit": audit,
        },
        "sampling": {"sweep_step_sessions": a.step, "n_sweep_dates": len(sweep_dates),
                     "start": a.start, "purge_dates": "ceil(H/step)+1",
                     "blocking": "t across blocks of ceil(H/step) consecutive decision dates"},
        "revisions": {"path": str(REVISIONS_PATH), "n_rows": int(len(revisions)),
                      "window_days": RF.WINDOW_DAYS, "strictly_before_decision_date": True,
                      "caveat": "yfinance history, pulled 2026-09 for live names; coverage "
                                "density grows ~5x from 2013 to 2025"},
        "features_base": list(XR.FEATURES), "features_flow_extra": flow_cols,
        "sweep": {str(h): r for h, r in sweep.items()},
        "n_date_blocks": {f"H{h}_{arm}_k{k}": c.get("n_date_blocks")
                          for h, res in sweep.items() for arm, r in res.items()
                          for k, c in r["by_k"].items()},
        "rule_backtest": rule,
        "books": books,
        "verdict": verdict,
        "read_me_first": ("PRODUCT_EXPERIMENT; NOT an alpha claim. Both arms and the rule are "
                          "survivor-selected (the revision source covers live names). Read "
                          "by_year and loo_worst before any t."),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(a.out) if a.out else OUT_DIR / f"revision_flow_sweep_{date.today()}.json"
    out.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    print(f"\nVERDICT: {verdict}\n-> {out}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
