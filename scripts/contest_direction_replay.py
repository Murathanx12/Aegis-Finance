"""ROT5_DIR event-level replay, as OUR receipt (2026-10-07; REVIEW_2026-10-06_C9 F2, owed by C15 §deferred).

    python -m scripts.contest_direction_replay --run-id DRR_2026-10-07_1      # ~10 min, $0, no network

The C9 reviewer ran this replay in six minutes, and its numbers existed only in the review. This
script makes it a receipt and adds the control the reviewer lacked: 63-day price momentum.

The question: among the names ROT5_TRAIL would buy (US reporters, ranked per buy day by the
desk's `trail_abs`, the mean |earnings reaction| of the previous reactions), does the ROT5_DIR
filter (`contest_direction.analyst_direction`, used read-only) drop names that do worse through
the print? Is that just 63-day momentum (target cuts follow price falls)?

- Events: `contest_desk.build_events` over the desk's US stamps (`contest_desk.raw_event_stamps`:
  SEC 8-K item 2.02 as the primary source, plus `contest/earnings_history_us_recent.parquet` for
  stamps after the SEC file ends), buy day (`pre_date`) from 2019-01-01. Same eligibility as the
  lab's ROT5_TRAIL: on cadence, `trail_abs` known, liquid at the buy open (`contest_book_compare.market`).
- Books: the top 5 and the top 20 per buy day by `trail_abs` (descending, stable).
- Return: `r_o2o`, the open before the print to the open after it (ROT5's hold); costs 10 and 25
  bps a side are charged to both groups alike (the difference is cost-free by construction).
- Direction: `analyst_direction(symbols, pre_date, rev, now_utc=<last pull>)`. Rows dated before the
  buy day 00:00 UTC. No `first_seen` exists before 2026-10-06, so point in time rests on the
  vendor's `event_date` (REVIEW C9 F1): stated on the receipt.
- Primary: mean per-event `r_o2o` of DROPPED minus KEPT (ADMIT + UNRATED, the book's kept set),
  t clustered on buy DAYS (daily blocks); month-clustered beside, for comparison with the review.
- Tails: P(> +20%), P(< -20%), the 1st and 5th percentiles, per group.
- Momentum control: `mom63` = close(t-1) / close(t-64) - 1 (known before the buy open); dropped vs
  kept inside momentum terciles (cut points from the subset's own pooled events, stated), and the
  drop coefficient with tercile fixed effects (+ linear mom63), day-clustered.
- By year and leave-one-year-out on the primary difference.

The declaration (`docs/research_notes/2026-10-07/DECLARATION_ROT5_DIR_REPLAY_v1.json`) is hashed
before the run. A run refuses when the declaration's body no longer hashes to its stamp, or when
this module's analysis code no longer hashes to the declared value. Receipt:
`contest/strategy_lab/direction_replay_<run_id>.json` (a run id is written once).

PRODUCT_EXPERIMENT. An exploration receipt, not a claim. The pool is SURVIVOR-SELECTED (the
contest universe alive today) and the ratings are live-ticker: both are printed on the receipt.
`contest_direction.py` and `contest_rehearsal.py` are imported, never edited (their contract hash
covers their code until the contest ends).
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DECLARATION = REPO / "docs" / "research_notes" / "2026-10-07" / "DECLARATION_ROT5_DIR_REPLAY_v1.json"
START = "2019-01-01"
BARS_FROM = "2016-01-01"               # the lab's panel start: trail_abs needs prior reactions
TOPS = (5, 20)
COSTS_BPS = (10.0, 25.0)
TAIL = 0.20
MOM_N = 63
MEM_FLOOR_GB = 3.0                     # C15 §deferred: the replay's floor (a CRSP-scale load)
LICENCE = "PRODUCT_EXPERIMENT"


class ReplayRefused(RuntimeError):
    """The replay refuses: no receipt is written (a refusal file names the reason)."""


# ───────────────────────────── the declaration ─────────────────────────────

def body_sha(d: dict) -> str:
    body = {k: v for k, v in d.items() if k != "sha256_of_body_without_this_field"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, indent=1).encode("utf-8")).hexdigest()


def code_source() -> str:
    """The analysis code the declaration pins."""
    fns = (event_table, verdicts_by_day, mom63_of, cluster_diff, group_stats, momentum_control,
           by_year_and_loo, subset_report)
    return "".join(inspect.getsource(f) for f in fns)


def code_sha() -> str:
    return hashlib.sha256(code_source().encode("utf-8")).hexdigest()


def load_declaration(path: Optional[Path] = None, *, check_code: bool = True) -> dict:
    """The replay's declaration, checked: refuses when absent, when the body was edited after it was
    stamped, or (check_code) when this module's analysis code no longer hashes to the declared value."""
    path = Path(path) if path else DECLARATION
    if not path.exists():
        raise ReplayRefused(f"{path.name} absent: the replay is undeclared")
    d = json.loads(path.read_text(encoding="utf-8"))
    have = body_sha(d)
    if have != d.get("sha256_of_body_without_this_field"):
        raise ReplayRefused(f"{path.name}: body hash {have[:16]} != its stamp (the declaration was edited)")
    if check_code and d.get("code", {}).get("source_sha256") != code_sha():
        raise ReplayRefused(f"analysis code hash {code_sha()[:16]} != declared "
                            f"{str(d.get('code', {}).get('source_sha256'))[:16]}")
    return d


# ───────────────────────────── the analysis (pure; pinned by the declaration) ─────────────────────────────

def event_table(ev: pd.DataFrame, liq: np.ndarray, *, start: str = START, tops=TOPS) -> pd.DataFrame:
    """Built events (US) -> the eligible buy-day candidates with `rank` (1 = largest trail_abs that
    day) and `top<k>` flags. Eligibility is the lab's ROT5_TRAIL: on cadence, trail_abs known,
    liquid at the buy open; plus a finite r_o2o (a split / fault zeroed by build_events is out)."""
    e = ev[ev.pre_i.notna() & ev.react_i.notna()].copy()
    e["pre_i"] = e.pre_i.astype(int)
    e = e[e.on_cadence.astype(bool) & e.trail_abs.notna() & e.r_o2o.notna()]
    e = e[liq[e.pre_i.to_numpy(), e.ci.astype(int).to_numpy()]]
    e = e[pd.to_datetime(e.pre_date) >= pd.Timestamp(start)]
    e = e.drop_duplicates(["pre_i", "ci"])
    e = e.sort_values(["pre_i", "trail_abs", "symbol"], ascending=[True, False, True], kind="mergesort")
    e["rank"] = e.groupby("pre_i").cumcount() + 1
    for k in tops:
        e[f"top{k}"] = e["rank"] <= k
    return e.reset_index(drop=True)


def verdicts_by_day(e: pd.DataFrame, rev: pd.DataFrame, direction_fn, *, max_rank: int) -> pd.DataFrame:
    """`analyst_direction` per buy day over that day's names ranked <= max_rank, at asof = pre_date.
    `rev` is read per day through the day's symbols only; a day with no row for any of its
    symbols is UNRATED for all (exactly what the function returns for a symbol with no rows).
    `now_utc` is the day's rows' last pull: the first-seen guard (first_seen <= now) is then
    non-binding, as it must be for history (no first_seen exists before 2026-10-06), and the
    14-day freshness rule -- a live-sheet rule, not what is replayed -- reads age 0."""
    sub = e[e["rank"] <= max_rank]
    tk = rev["ticker"].astype(str).str.upper()
    by_tk = {s: g for s, g in rev.assign(ticker=tk).groupby("ticker", sort=False)}
    out = []
    for pre_date, g in sub.groupby("pre_date", sort=True):
        syms = [str(s).upper() for s in g.symbol]
        parts = [by_tk[s] for s in dict.fromkeys(syms) if s in by_tk]
        if parts:
            day_rev = pd.concat(parts, ignore_index=True)
            now_utc = pd.to_datetime(day_rev["pulled_at"], utc=True, errors="coerce").max()
            d, _ = direction_fn(syms, pd.Timestamp(pre_date).date(), day_rev, now_utc=now_utc)
        else:
            d = pd.DataFrame({"symbol": syms, "verdict": "UNRATED", "cons": 0.0, "net_raises90": 0,
                              "rev_mom": 0.0, "n_firms": 0})
        d = d.drop_duplicates("symbol")
        out.append(pd.DataFrame({"pre_date": pre_date, "symbol": g.symbol.to_numpy(),
                                 "_S": syms}).merge(d.rename(columns={"symbol": "_S"}), on="_S", how="left"))
    v = pd.concat(out, ignore_index=True).drop(columns=["_S"])
    return v[["pre_date", "symbol", "verdict", "cons", "net_raises90", "rev_mom", "n_firms"]]


def mom63_of(close_ff: np.ndarray, pre_i: np.ndarray, ci: np.ndarray, n: int = MOM_N) -> np.ndarray:
    """close(t-1) / close(t-1-n) - 1 on the forward-filled close: known before the open of t."""
    a, b = pre_i - 1, pre_i - 1 - n
    ok = b >= 0
    out = np.full(len(pre_i), np.nan)
    c1 = close_ff[a[ok], ci[ok]]
    c0 = close_ff[b[ok], ci[ok]]
    with np.errstate(divide="ignore", invalid="ignore"):
        out[ok] = np.where((c0 > 0) & np.isfinite(c0) & np.isfinite(c1), c1 / c0 - 1.0, np.nan)
    return out


def cluster_diff(y: np.ndarray, x: np.ndarray, groups: np.ndarray, controls: Optional[np.ndarray] = None) -> dict:
    """OLS y = a + b*x (+ controls), b's t with cluster-robust (CR1) SE over `groups`. With no
    controls b is mean(y | x=1) - mean(y | x=0)."""
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(y)), np.asarray(x, float)] + ([controls] if controls is not None else []))
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X, g = y[ok], X[ok], np.asarray(groups)[ok]
    n, p = X.shape
    G = len(pd.unique(g))
    if n <= p or G < 3 or X[:, 1].min() == X[:, 1].max():
        return {"b": None, "t": None, "n": int(n), "clusters": int(G)}
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    u = y - X @ beta
    S = pd.DataFrame(X * u[:, None]).groupby(g).sum().to_numpy()
    meat = S.T @ S
    adj = (G / (G - 1)) * ((n - 1) / (n - p))
    V = adj * XtX_inv @ meat @ XtX_inv
    se = float(np.sqrt(max(V[1, 1], 0.0)))
    return {"b": float(beta[1]), "se": se, "t": float(beta[1] / se) if se > 0 else None, "n": int(n),
            "clusters": int(G)}


def group_stats(r: np.ndarray, costs_bps=COSTS_BPS, tail: float = TAIL) -> dict:
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    if not len(r):
        return {"n": 0}
    out = {"n": int(len(r)), "mean_gross": float(r.mean()), "median_gross": float(np.median(r)),
           "sd": float(r.std(ddof=1)) if len(r) > 1 else None,
           f"p_gt_+{int(tail*100)}pct": float((r > tail).mean()), f"p_lt_-{int(tail*100)}pct": float((r < -tail).mean()),
           "p01": float(np.quantile(r, 0.01)), "p05": float(np.quantile(r, 0.05)),
           "p95": float(np.quantile(r, 0.95)), "p99": float(np.quantile(r, 0.99))}
    for c in costs_bps:
        out[f"mean_net_{int(c)}bps_a_side"] = float(r.mean() - 2 * c / 1e4)
    return out


def momentum_control(s: pd.DataFrame) -> dict:
    """Dropped vs kept inside 63-day momentum terciles (cut points: the subset's pooled tercile
    quantiles), the pooled within-tercile difference (n-weighted), and the drop coefficient with
    tercile fixed effects + linear mom63, day-clustered. The split must sum to the total."""
    m = s[np.isfinite(s.mom63)].copy()
    cuts = np.nanquantile(m.mom63, [1 / 3, 2 / 3])
    m["terc"] = np.digitize(m.mom63, cuts)                       # 0 low, 1 mid, 2 high
    rows, wsum, wn = {}, 0.0, 0
    for t, name in enumerate(("low", "mid", "high")):
        g = m[m.terc == t]
        dr, kp = g[g.is_drop], g[~g.is_drop]
        cd = cluster_diff(g.r_o2o.to_numpy(), g.is_drop.to_numpy(), g.pre_date.to_numpy())
        rows[name] = {"n": int(len(g)), "n_drop": int(len(dr)), "n_kept": int(len(kp)),
                      "drop_share": float(len(dr) / len(g)) if len(g) else None,
                      "mom63_range": [float(g.mom63.min()), float(g.mom63.max())] if len(g) else None,
                      "mean_drop": float(dr.r_o2o.mean()) if len(dr) else None,
                      "mean_kept": float(kp.r_o2o.mean()) if len(kp) else None,
                      "diff_drop_minus_kept": cd["b"], "t_day_clustered": cd["t"],
                      "p_gt_+20pct_drop_kept": [float((dr.r_o2o > TAIL).mean()) if len(dr) else None,
                                                float((kp.r_o2o > TAIL).mean()) if len(kp) else None],
                      "p_lt_-20pct_drop_kept": [float((dr.r_o2o < -TAIL).mean()) if len(dr) else None,
                                                float((kp.r_o2o < -TAIL).mean()) if len(kp) else None]}
        if cd["b"] is not None:
            wsum += cd["b"] * len(g)
            wn += len(g)
    fe = np.column_stack([(m.terc == 1).to_numpy(float), (m.terc == 2).to_numpy(float), m.mom63.to_numpy(float)])
    ctrl = cluster_diff(m.r_o2o.to_numpy(), m.is_drop.to_numpy(), m.pre_date.to_numpy(), controls=fe)
    raw = cluster_diff(m.r_o2o.to_numpy(), m.is_drop.to_numpy(), m.pre_date.to_numpy())
    return {"cut_points_mom63": [float(c) for c in cuts], "cut_points_basis": "pooled quantiles of this subset "
            "(a description of the sample, not a trading rule)",
            "n_with_mom63": int(len(m)), "n_without_mom63": int(len(s) - len(m)),
            "terciles": rows,
            "split_sums_to_total": bool(sum(v["n"] for v in rows.values()) == len(m)
                                        and sum(v["n_drop"] for v in rows.values()) == int(m.is_drop.sum())),
            "within_tercile_diff_n_weighted": (wsum / wn) if wn else None,
            "diff_same_events_no_control": raw,
            "diff_with_tercile_fe_and_linear_mom63": ctrl}


def by_year_and_loo(s: pd.DataFrame) -> dict:
    yr = pd.to_datetime(s.pre_date).dt.year.to_numpy()
    out = {"by_year": {}, "leave_one_year_out": {}}
    for y in sorted(set(yr.tolist())):
        g = s[yr == y]
        cd = cluster_diff(g.r_o2o.to_numpy(), g.is_drop.to_numpy(), g.pre_date.to_numpy())
        out["by_year"][str(y)] = {"n": int(len(g)), "n_drop": int(g.is_drop.sum()), "diff": cd["b"], "t_day": cd["t"]}
        h = s[yr != y]
        ch = cluster_diff(h.r_o2o.to_numpy(), h.is_drop.to_numpy(), h.pre_date.to_numpy())
        out["leave_one_year_out"][str(y)] = {"diff": ch["b"], "t_day": ch["t"]}
    d = [v["diff"] for v in out["by_year"].values() if v["diff"] is not None]
    lo = [v["diff"] for v in out["leave_one_year_out"].values() if v["diff"] is not None]
    out["years_negative"] = int(sum(x < 0 for x in d))
    out["years"] = len(d)
    out["loo_range"] = [min(lo), max(lo)] if lo else None
    return out


def subset_report(s: pd.DataFrame) -> dict:
    """One subset (top 5 or top 20): drop share, groups, the primary difference, momentum, years."""
    s = s.copy()
    s["is_drop"] = s.verdict.astype(str).str.startswith("DROP")
    month = pd.to_datetime(s.pre_date).dt.to_period("M").astype(str).to_numpy()
    dr, kp = s[s.is_drop], s[~s.is_drop]
    ad = s[s.verdict == "ADMIT"]
    da = s[s.is_drop | (s.verdict == "ADMIT")]
    prim = cluster_diff(s.r_o2o.to_numpy(), s.is_drop.to_numpy(), s.pre_date.to_numpy())
    mon = cluster_diff(s.r_o2o.to_numpy(), s.is_drop.to_numpy(), month)
    # daily blocks, the narrow reading: days holding both groups, mean of the daily differences
    dd = s.groupby(["pre_date", "is_drop"]).r_o2o.mean().unstack()
    both = dd.dropna() if {True, False} <= set(dd.columns) else pd.DataFrame(columns=[True, False])
    dif = (both[True] - both[False]).to_numpy() if len(both) else np.array([])
    vc = s.verdict.value_counts().to_dict()
    return {"n_events": int(len(s)), "n_buy_days": int(s.pre_date.nunique()),
            "verdicts": {k: int(v) for k, v in vc.items()},
            "drop_share": float(s.is_drop.mean()),
            "drop_by_reason": {"DROP_NET_SELL": int(vc.get("DROP_NET_SELL", 0)),
                               "DROP_NET_LOWERING": int(vc.get("DROP_NET_LOWERING", 0))},
            "dropped": group_stats(dr.r_o2o.to_numpy()), "kept_admit_plus_unrated": group_stats(kp.r_o2o.to_numpy()),
            "kept_admit_only": group_stats(ad.r_o2o.to_numpy()),
            "primary_diff_drop_minus_kept": {"diff": prim["b"], "t_day_clustered": prim["t"],
                                             "day_clusters": prim["clusters"],
                                             "t_month_clustered": mon["t"], "month_clusters": mon["clusters"],
                                             "cost_note": "both groups pay the same round trip at 10 or 25 bps a "
                                                          "side: the difference is identical gross and net"},
            "diff_drop_minus_admit_only": cluster_diff(da.r_o2o.to_numpy(), da.is_drop.to_numpy(),
                                                       da.pre_date.to_numpy()),
            "daily_block_paired": {"days_with_both": int(len(dif)),
                                   "mean_daily_diff": float(dif.mean()) if len(dif) else None,
                                   "t": float(dif.mean() / (dif.std(ddof=1) / np.sqrt(len(dif))))
                                   if len(dif) > 2 and dif.std(ddof=1) > 0 else None},
            "momentum_control": momentum_control(s),
            "by_year_and_loo": by_year_and_loo(s)}


# ───────────────────────────── the run (loads; not pinned) ─────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mem_gb() -> float:
    try:
        import psutil                                              # noqa: PLC0415
        return psutil.virtual_memory().available / 2**30
    except Exception:                                              # noqa: BLE001
        return float("inf")


def survivorship(panel, syms: list[str], gap_days: int = 30) -> dict:
    from scripts import contest_book_compare as cbc               # noqa: PLC0415
    dead = cbc.dead_symbols(panel, gap_days=gap_days)
    n_dead = sum(1 for s in syms if s in dead)
    return {"symbols_in_events": len(syms), "symbols_last_bar_over_30d_before_panel_end": n_dead,
            "statement": ("SURVIVOR-SELECTED: the pool is the contest bars universe alive today; "
                          f"{n_dead} of {len(syms)} event symbols stopped trading more than {gap_days} days "
                          "before the panel's end. Names that died (and the ratings vendor serves live tickers "
                          "only, so a dead name would be UNRATED) are missing; the bias falls on both groups, "
                          "but not necessarily equally.")}


def run(run_id: str, *, out_dir: Optional[Path] = None) -> dict:
    from scripts import contest_book_compare as cbc               # noqa: PLC0415
    from scripts import contest_calendar as cc                    # noqa: PLC0415
    from scripts import contest_desk as desk                      # noqa: PLC0415
    from scripts import contest_direction as cd                   # noqa: PLC0415  (read-only)
    out_dir = Path(out_dir) if out_dir else cc.CONTEST / "strategy_lab"
    out = out_dir / f"direction_replay_{run_id}.json"
    if out.exists():
        raise ReplayRefused(f"{out.name} exists (a run id is written once)")
    decl = load_declaration()
    t0 = time.time()
    free = _mem_gb()
    if free < MEM_FLOOR_GB:
        raise ReplayRefused(f"{free:.1f} GB free < {MEM_FLOOR_GB} GB: the bars panel was not loaded")
    long = cc.load_bars_usd([], include_us=True)
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    long = long[long.date >= pd.Timestamp(BARS_FROM)].drop_duplicates(["symbol", "date"])
    panel = desk.panel_from_long(long)
    del long
    m = cbc.market(panel)
    raw = desk.raw_event_stamps()
    raw_us = raw[raw.symbol.map(cc.market_of) == "US"]
    src_counts = {str(k): int(v) for k, v in raw_us.source.value_counts().items()}
    ev = desk.build_events(panel, raw_us)
    ev = ev[ev.market == "US"]
    e = event_table(ev, m.liq)
    n_candidates = int(len(e))
    rev = cd.load_revisions()
    fp = cd.frame_fingerprint(rev)
    rev = rev.copy()
    rev["pulled_at"] = pd.to_datetime(rev["pulled_at"], utc=True, errors="coerce")
    last_pull = rev["pulled_at"].max()
    v = verdicts_by_day(e, rev, cd.analyst_direction, max_rank=max(TOPS))
    e = e[e["rank"] <= max(TOPS)].merge(v, on=["pre_date", "symbol"], how="left")
    if e.verdict.isna().any():
        raise ReplayRefused(f"{int(e.verdict.isna().sum())} events have no verdict")
    close_ff = pd.DataFrame(panel.close).ffill(limit=5).to_numpy(dtype="float64")
    e["mom63"] = mom63_of(close_ff, e.pre_i.to_numpy(int), e.ci.astype(int).to_numpy())
    body = {"schema": "contest/direction_replay/1", "run_id": run_id, "written_utc": _now(), "licence": LICENCE,
            "llm_spend_usd": 0.0, "status": "OK",
            "declaration": {"path": str(DECLARATION.relative_to(REPO)).replace("\\", "/"),
                            "sha256": decl["sha256_of_body_without_this_field"], "code_sha256": code_sha()},
            "universe": {"stamps": "contest_desk.raw_event_stamps(), US: SEC 8-K item 2.02 (primary) + "
                                   "contest/earnings_history_us_recent.parquet after the SEC file ends",
                         "stamps_by_source": src_counts, "events_built_us": int(len(ev)),
                         "eligible_candidates_since_2019": n_candidates,
                         "buy_days": int(e.pre_date.nunique()),
                         "first_buy_day": str(pd.Timestamp(e.pre_date.min()).date()),
                         "last_buy_day": str(pd.Timestamp(e.pre_date.max()).date()),
                         "panel": {"first": str(panel.dates[0].date()), "last": str(panel.dates[-1].date()),
                                   "symbols": int(len(panel.syms))}},
            "ranking_key": "contest_desk.build_events trail_abs (mean |r_c2c| of the previous reactions), "
                           "descending per buy day; the lab's ROT5_TRAIL eligibility (on cadence, liquid at the open)",
            "direction": {"function": "scripts.contest_direction.analyst_direction (imported read-only)",
                          "asof": "each event's pre_date (rows with event_date before it, 00:00 UTC)",
                          "now_utc": "per buy day, the last pull of that day's rows (first-seen guard "
                                     "non-binding; the 14-day freshness rule is a live-sheet rule)",
                          "last_pull_utc": str(last_pull), "source_fingerprint": fp,
                          "pit_caveat": "no first_seen_utc exists for rows served before 2026-10-06; the "
                                        "first-seen guard is non-binding here and point in time rests on the "
                                        "vendor's event_date. REVIEW C9 F1: the vendor rewrote 30 pre-09-29 rows "
                                        "between pulls"},
            "survivorship": survivorship(panel, sorted(e.symbol.unique().tolist())),
            "return": "r_o2o: open of the buy session (pre_i) to the open of the reaction session (react_i)",
            "costs_bps_a_side": list(COSTS_BPS),
            "subsets": {}}
    for k in TOPS:
        s = e[e[f"top{k}"]]
        body["subsets"][f"top{k}"] = subset_report(s)
    body["headline"] = headline(body)
    body["seconds"] = round(time.time() - t0, 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(out)
    return body


def _pp(x) -> str:
    return "n/a" if x is None else f"{x * 100:+.2f} pp"


def _t(x) -> str:
    return "n/a" if x is None else f"{x:+.2f}"


def headline(body: dict) -> dict:
    out = {}
    for k, s in body["subsets"].items():
        p, mc = s["primary_diff_drop_minus_kept"], s["momentum_control"]
        c = mc["diff_with_tercile_fe_and_linear_mom63"]
        out[k] = (f"{k}: drop share {s['drop_share']:.1%}; dropped minus kept {_pp(p['diff'])} per event "
                  f"(t day {_t(p['t_day_clustered'])}, t month {_t(p['t_month_clustered'])}); with the 63d "
                  f"momentum control {_pp(c['b'])} (t {_t(c['t'])}); P(>+20%) drop/kept "
                  f"{s['dropped'].get('p_gt_+20pct', float('nan')):.1%}/"
                  f"{s['kept_admit_plus_unrated'].get('p_gt_+20pct', float('nan')):.1%}, P(<-20%) "
                  f"{s['dropped'].get('p_lt_-20pct', float('nan')):.1%}/"
                  f"{s['kept_admit_plus_unrated'].get('p_lt_-20pct', float('nan')):.1%}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args(argv)
    try:
        body = run(a.run_id)
    except ReplayRefused as e:
        from scripts import contest_calendar as cc                # noqa: PLC0415
        ref = cc.CONTEST / "strategy_lab" / f"direction_replay_{a.run_id}_REFUSED.txt"
        if not (cc.CONTEST / "strategy_lab" / f"direction_replay_{a.run_id}.json").exists():
            ref.write_text(f"{_now()} REFUSED: {e}" + chr(10), encoding="utf-8")
        print(f"REFUSED: {e}", flush=True)
        return 2
    for line in body["headline"].values():
        print(line, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
