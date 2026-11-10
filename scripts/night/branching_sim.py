"""A branching population that differs in ALPHA SOURCE, simulated forward-only on history (S65 night).

Simulation only: no books are written, nothing is frozen, no order exists.

Population. Each branch is (selector, k, universe). Roots: one branch per selector
(30 selectors on the survivor-free CRSP monthly panel: price, risk, fundamentals,
analyst flow, ratings, earnings, insider), k=20, eligible universe. Every branch
carries a TURNOVER-MATCHED random twin (same k, same eligible set with the
selector defined, same cost). A branch's score is its net return minus its
twin's -- never vs the market.

Epochs (every `--epoch` months after a `--burn` month start). At epoch T, using
ONLY months < T:
  * kill: the bottom `--kill` fraction of branches aged >= `--min-age` months by
    mean excess-over-twin since birth;
  * branch: each top-`--top` branch spawns one MUTANT (k in {10,20,50} or the
    other universe), and the top pairs with the LOWEST correlation of monthly
    excess spawn a JOIN (rank-average of the two selectors). Children are born at
    T and scored only on months >= T (no inherited history).
  * cap the population at `--cap`.
Allocator. A Thompson book-of-books over live branches aged >= 12 months:
Normal posterior on each branch's mean excess (prior N(0, 0.5%^2)), one draw per
month, capital equal-weighted over the `--alloc-n` highest draws. Its return is
the allocation applied to the branches' NET returns; its CONTROL is the SAME
allocation applied to the branches' TWINS. Also printed: equal weight over all
live branches, and equal weight over roots only (no branching).
Distinct bets: at each epoch, live branches are clustered by mean holdings
Jaccard over the last 12 months (>= 0.5 -> same bet).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "backend" / "data" / "optimus" / "night_2026-11-11"
RT = Path(os.environ.get("AEGIS_RUNTIME_DATA", r"C:\Users\mrthn\aegis-finance\backend\data")) / "optimus"
CR = RT / "crsp_rebuild"
PANEL = CR / "library_panel_2026-09-29T075640Z.parquet"
FUND = CR / "library_fund_2026-09-29T041550Z.parquet"
EB = CR / "event_bridge_EB_2026-09-29T1055Z.parquet"

#: selector -> (column, sign). +1: high buys. Grouped by alpha source for the receipt.
SELECTORS = {
    # price / trend
    "mom_12_1": ("mom_252_21", 1), "mom_6_1": ("mom_126_21", 1), "mom_3": ("mom_63", 1),
    "rev_1m": ("mom_21", -1), "rev_5d": ("rev_5", -1), "resid_mom": ("resid_mom_12_1", 1),
    "near_52w_high": ("px_vs_52w_high", 1), "above_ma200": ("px_vs_ma200", 1),
    "seasonality": ("seas_same_month", 1), "up_days": ("up_days_12_1", 1),
    # risk / liquidity
    "low_vol": ("vol_63", -1), "low_idio": ("idio_vol_63", -1), "low_beta": ("beta_63", -1),
    "low_max": ("max_ret_21", -1), "illiquid": ("amihud", 1), "neg_skew": ("skew_63", -1),
    # fundamentals
    "gp_at": ("gp_at", 1), "value_bm": ("book_to_market", 1), "low_debt": ("debt_at", -1),
    "margin": ("gross_margin", 1), "roe": ("ni_be", 1),
    # analyst / earnings / insider
    "net_raises": ("net_raises", 1), "flow_rule": ("flow_rule_score", 1), "flow_accel": ("flow_accel", 1),
    "rating_net": ("rating_net_90", 1), "low_target_cv": ("target_cv_180", -1),
    "ear": ("ear_last", 1), "insider_buyers": ("ins_buyers_90", 1), "insider_ratio": ("ins_net_ratio_180", 1),
    "target_change": ("median_target_change", 1),
}
SOURCE = {s: ("price" if i < 10 else "risk" if i < 16 else "fundamental" if i < 21 else "analyst_event")
          for i, s in enumerate(SELECTORS)}
ZERO_IS_MISSING = {"net_raises", "flow_rule_score", "flow_accel", "rating_net_90", "ins_buyers_90",
                   "ins_net_ratio_180"}


def load() -> tuple[list, dict, np.ndarray, dict]:
    pcols = ["date", "symbol", "eligible", "fwd_ret", "delisted_in_period", "median_dollar_vol"]
    lib = sorted({c for c, _ in SELECTORS.values()})
    p = pd.read_parquet(PANEL, columns=pcols + [c for c in lib if c in _cols(PANEL) and c not in pcols])
    f = pd.read_parquet(FUND, columns=["date", "symbol"] + [c for c in lib if c in _cols(FUND)])
    e = pd.read_parquet(EB, columns=["date", "symbol", "days_since_earn"] + [c for c in lib if c in _cols(EB)])
    df = p.merge(f, on=["date", "symbol"], how="left").merge(e, on=["date", "symbol"], how="left")
    df = df[df["date"] >= "1994-01-01"]
    df.loc[~(df["days_since_earn"] <= 63), "ear_last"] = np.nan
    for c in ZERO_IS_MISSING:
        if c in df:
            df.loc[df[c] == 0, c] = np.nan
    mkt = df[df["symbol"] == "SPY"].set_index("date")["fwd_ret"]
    el = df[df["eligible"].astype(bool) & (df["symbol"] != "SPY")].copy()
    del df
    el["ret"] = el["fwd_ret"].where(el["fwd_ret"].notna(),
                                    np.where(el["delisted_in_period"].astype(bool), -0.30, 0.0))
    el["sid"] = pd.factorize(el["symbol"])[0]
    el["liq_rank"] = el.groupby("date")["median_dollar_vol"].rank(ascending=False, method="first") - 1
    months = [m for m in sorted(el["date"].unique()) if m < pd.Timestamp("2024-12-31")]
    g = {}
    cols = [c for c in lib if c in el.columns]
    for m, x in el.groupby("date"):
        d = {"sid": x["sid"].to_numpy(np.int64), "ret": x["ret"].to_numpy(float),
             "liq": x["liq_rank"].to_numpy(float) < 500}
        for c in cols:
            v = x[c].to_numpy(float)
            # cross-sectional percentile rank (NaN stays NaN): makes joins well defined
            ok = np.isfinite(v)
            r = np.full(len(v), np.nan)
            if ok.sum() > 1:
                r[ok] = (pd.Series(v[ok]).rank(method="average").to_numpy() - 0.5) / ok.sum()
            d[c] = r
        g[m] = d
    return months, g, mkt.reindex(months).to_numpy(float), {"rows": int(len(el)), "cols": cols}


_COLS: dict = {}


def _cols(p: Path) -> set:
    if p not in _COLS:
        import pyarrow.parquet as pq
        _COLS[p] = set(pq.ParquetFile(p).schema_arrow.names)
    return _COLS[p]


def _panel_cols() -> set:
    return _cols(PANEL)


class Branch:
    _n = 0

    def __init__(self, parts: tuple, k: int, universe: str, born: int, parent: list, kind: str):
        Branch._n += 1
        self.id = f"B{Branch._n:04d}"
        self.parts = parts          # tuple of (column, sign)
        self.k, self.universe, self.born, self.parent, self.kind = k, universe, born, parent, kind
        self.alive = True
        self.died = None
        self.net: dict = {}
        self.twin: dict = {}
        self.hold: dict = {}
        self.prev = None
        self.twin_hold = None

    @property
    def label(self) -> str:
        nm = "+".join(_name(c, s) for c, s in self.parts)
        return f"{nm}/k{self.k}/{self.universe}"

    def score(self, m_idx: np.ndarray) -> np.ndarray:
        return np.array([self.net[i] - self.twin[i] for i in m_idx if i in self.net and i in self.twin])


def _name(col: str, sign: int) -> str:
    for s, (c, sg) in SELECTORS.items():
        if c == col and sg == sign:
            return s
    return f"{col}{'+' if sign > 0 else '-'}"


def step_branch(b: Branch, i: int, x: dict, cost: float, rng: np.random.Generator) -> None:
    sc = None
    for col, sign in b.parts:
        v = x.get(col)
        if v is None:
            return
        v = v if sign > 0 else 1.0 - v
        sc = v if sc is None else sc + v
    ok = np.isfinite(sc)
    if b.universe == "liquid500":
        ok &= x["liq"]
    idx = np.flatnonzero(ok)
    k = b.k
    if len(idx) < max(2 * k, 20):
        return
    pick = idx[np.argsort(-sc[idx], kind="mergesort")[:k]]
    ids = x["sid"][pick]
    cur = set(ids.tolist())
    n_new = k if b.prev is None else len(cur - b.prev)
    traded = 1.0 if b.prev is None else 2.0 * n_new / k
    b.net[i] = float(x["ret"][pick].mean()) - cost * traded
    b.hold[i] = cur
    b.prev = cur
    ids_ok = x["sid"][idx]
    h = b.twin_hold
    if h is None:
        sel = rng.choice(len(idx), size=k, replace=False)
        b.twin_hold = ids_ok[sel]
        b.twin[i] = float(x["ret"][idx[sel]].mean()) - cost
        return
    alive = h[np.isin(h, ids_ok)]
    drop = max(0, n_new - (len(h) - len(alive)))
    if drop and len(alive):
        alive = alive[rng.permutation(len(alive))[: max(0, len(alive) - drop)]]
    need = k - len(alive)
    if need:
        pool = np.flatnonzero(~np.isin(ids_ok, alive))
        alive = np.concatenate([alive, ids_ok[rng.choice(pool, size=need, replace=False)]])
    b.twin_hold = alive
    b.twin[i] = float(x["ret"][idx[np.isin(ids_ok, alive)]].mean()) - cost * 2.0 * need / k


def jaccard_clusters(branches: list, months_idx: list, thr: float = 0.5) -> int:
    reps: list = []
    for b in branches:
        hs = [b.hold[i] for i in months_idx if i in b.hold]
        if not hs:
            continue
        joined = False
        for r in reps:
            rs = [r.hold[i] for i in months_idx if i in r.hold and i in b.hold]
            bs = [b.hold[i] for i in months_idx if i in r.hold and i in b.hold]
            if rs and np.mean([len(p & q) / len(p | q) for p, q in zip(rs, bs)]) >= thr:
                joined = True
                break
        if not joined:
            reps.append(b)
    return len(reps)


def block_t(d: np.ndarray, block: int = 3) -> dict:
    d = d[np.isfinite(d)]
    nb = len(d) // block
    if nb < 4:
        return {"n_months": int(len(d))}
    bm = d[: nb * block].reshape(nb, block).mean(axis=1)
    se = bm.std(ddof=1) / math.sqrt(nb)
    return {"n_months": int(len(d)), "n_blocks": int(nb), "mean_monthly": float(d.mean()),
            "t_blocks": float(bm.mean() / se) if se > 0 else None, "mde_monthly": float(2.8 * se)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epoch", type=int, default=12)
    ap.add_argument("--burn", type=int, default=36)
    ap.add_argument("--kill", type=float, default=0.25)
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--min-age", type=int, default=24)
    ap.add_argument("--cap", type=int, default=80)
    ap.add_argument("--alloc-n", type=int, default=8)
    ap.add_argument("--cost-bps", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=20261111)
    a = ap.parse_args(argv)
    run_id = f"branching_sim_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print("RUN", run_id, "pid", os.getpid(), flush=True)
    t0 = time.time()
    rng = np.random.default_rng(a.seed)
    months, g, mkt, meta = load()
    print(f"loaded {meta['rows']:,} eligible rows, {len(months)} months, {len(meta['cols'])} selector columns "
          f"in {time.time()-t0:.0f}s", flush=True)
    cost = a.cost_bps / 1e4
    roots = [Branch(((c, sg),), 20, "eligible", 0, [], "root") for _nm, (c, sg) in SELECTORS.items()
             if c in meta["cols"]]
    pop = list(roots)
    root_ids = {b.id for b in roots}
    log, alloc_ret, alloc_twin, ew_all, ew_root, distinct = [], [], [], [], [], []
    ew_all_twin, ew_root_twin = [], []
    for i, m in enumerate(months):
        x = g[m]
        for b in pop:
            # roots keep a SHADOW series after being killed, so "all roots, equal weight,
            # never pruned" is a clean no-branching control
            if (b.alive or b.id in root_ids) and i >= b.born:
                step_branch(b, i, x, cost, rng)
        # ---------- allocator for month i, using scores from months < i only ----------
        live = [b for b in pop if b.alive and i in b.net and i in b.twin]
        cand = []
        for b in live:
            past = b.score(np.arange(b.born, i))
            if len(past) >= 12:
                n, mu, sd = len(past), past.mean(), max(past.std(ddof=1), 1e-4)
                prec = 1 / 0.005 ** 2 + n / sd ** 2
                post_mu = (n / sd ** 2) * mu / prec
                cand.append((rng.normal(post_mu, 1 / math.sqrt(prec)), b))
        if cand:
            cand.sort(key=lambda t: -t[0])
            ch = [b for _, b in cand[: a.alloc_n]]
            alloc_ret.append(float(np.mean([b.net[i] for b in ch])))
            alloc_twin.append(float(np.mean([b.twin[i] for b in ch])))
        else:
            alloc_ret.append(np.nan)
            alloc_twin.append(np.nan)
        ew_all.append(float(np.mean([b.net[i] for b in live])) if live else np.nan)
        ew_all_twin.append(float(np.mean([b.twin[i] for b in live])) if live else np.nan)
        rl = [b for b in roots if i in b.net]
        ew_root.append(float(np.mean([b.net[i] for b in rl])) if rl else np.nan)
        ew_root_twin.append(float(np.mean([b.twin[i] for b in rl if i in b.twin])) if rl else np.nan)
        # ---------- epoch: kill / branch at the END of month i (children start at i+1) ----------
        if i >= a.burn and (i - a.burn) % a.epoch == 0 and i + 1 < len(months):
            past_idx = np.arange(0, i + 1)
            scored = []
            for b in pop:
                if not b.alive:
                    continue
                sc = b.score(np.arange(b.born, i + 1))
                if len(sc) >= 6:
                    scored.append((float(sc.mean()), len(sc), b, sc))
            scored.sort(key=lambda t: t[0])
            old = [t for t in scored if t[1] >= a.min_age]
            n_kill = int(len(old) * a.kill)
            for t in old[:n_kill]:
                t[2].alive, t[2].died = False, i
            top = [t for t in scored[::-1] if t[2].alive][: a.top]
            born = []
            for mu, n, b, sc in top:
                ks = [k for k in (10, 20, 50) if k != b.k]
                if rng.random() < 0.5:
                    child = Branch(b.parts, int(rng.choice(ks)), b.universe, i + 1, [b.id], "mutant_k")
                else:
                    child = Branch(b.parts, b.k, "liquid500" if b.universe == "eligible" else "eligible",
                                   i + 1, [b.id], "mutant_universe")
                born.append(child)
            # joins: lowest-correlation pairs among the top
            pairs = []
            for p1 in range(len(top)):
                for p2 in range(p1 + 1, len(top)):
                    b1, b2 = top[p1][2], top[p2][2]
                    common = [j for j in range(max(b1.born, b2.born), i + 1) if j in b1.net and j in b2.net
                              and j in b1.twin and j in b2.twin]
                    if len(common) < 12 or set(b1.parts) & set(b2.parts):
                        continue
                    e1 = np.array([b1.net[j] - b1.twin[j] for j in common])
                    e2 = np.array([b2.net[j] - b2.twin[j] for j in common])
                    pairs.append((float(np.corrcoef(e1, e2)[0, 1]), b1, b2))
            pairs.sort(key=lambda t: t[0])
            for c, b1, b2 in pairs[:3]:
                parts = tuple(sorted(set(b1.parts) | set(b2.parts)))[:3]
                born.append(Branch(parts, 20, b1.universe, i + 1, [b1.id, b2.id], "join"))
            existing = {(b.parts, b.k, b.universe) for b in pop if b.alive}
            born = [c for c in born if (c.parts, c.k, c.universe) not in existing]
            live_n = sum(b.alive for b in pop)
            born = born[: max(0, a.cap - live_n)]
            pop.extend(born)
            live_now = [b for b in pop if b.alive]
            recent = list(range(max(0, i - 11), i + 1))
            nd = jaccard_clusters(live_now, recent)
            distinct.append({"month": str(pd.Timestamp(m).date()), "live": len(live_now), "distinct_bets": nd,
                             "killed": n_kill, "born": len(born)})
            print(f"epoch {pd.Timestamp(m).date()} live {len(live_now):>3} distinct {nd:>3} killed {n_kill:>2} "
                  f"born {len(born):>2} top: " + ", ".join(f"{t[2].label}({100*t[0]:+.2f})" for t in top[:3]),
                  flush=True)
    hold_year = np.array([(pd.Timestamp(m) + pd.offsets.MonthEnd(1)).year for m in months])
    ar, at, ea, er = map(np.array, (alloc_ret, alloc_twin, ew_all, ew_root))

    def cagr(x):
        x = x[np.isfinite(x)]
        return float(np.exp(np.log1p(x).sum() * 12 / len(x)) - 1) if len(x) else None

    def by_year(d):
        return {int(y): float(np.nansum(d[hold_year == y])) for y in sorted(set(hold_year)) if
                np.isfinite(d[hold_year == y]).any()}

    eat, ert = np.array(ew_all_twin), np.array(ew_root_twin)

    def scored(dd):
        okd = np.isfinite(dd)
        byy_ = by_year(np.where(okd, dd, np.nan))
        loo_ = {y: float(np.nanmean(dd[okd & (hold_year != y)])) for y in byy_}
        return {**block_t(dd[okd]), "years_positive": int(sum(v > 0 for v in byy_.values())),
                "n_years": len(byy_), "loo_worst": min(loo_.values()) if loo_ else None,
                "loo_worst_year": min(loo_, key=loo_.get) if loo_ else None, "by_year": byy_}
    pruned_vs_twin = scored(ea - eat)
    roots_vs_twin = scored(er - ert)
    pruning_gain_net_of_twins = scored((ea - eat) - (er - ert))
    ok = np.isfinite(ar) & np.isfinite(at)
    d_alloc = np.where(ok, ar - at, np.nan)
    byy = by_year(d_alloc)
    loo = {y: float(np.nanmean(d_alloc[ok & (hold_year != y)])) for y in byy}
    okm = np.isfinite(ar) & np.isfinite(mkt)
    summary = {
        "allocator_net_cagr": cagr(np.where(ok, ar, np.nan)), "allocator_twin_cagr": cagr(np.where(ok, at, np.nan)),
        "market_cagr_same_months": cagr(np.where(ok, mkt, np.nan)),
        "ew_all_live_cagr_same_months": cagr(np.where(ok, ea, np.nan)),
        "ew_roots_only_cagr_same_months": cagr(np.where(ok, er, np.nan)),
        "ew_roots_static_note": "all 30 roots equal weight, never pruned (shadow series after a kill)",
        "allocator_vs_twin": block_t(d_alloc[ok]),
        "allocator_vs_market": block_t((ar - mkt)[okm]),
        "allocator_vs_ew_roots": block_t((ar - er)[ok & np.isfinite(er)]),
        "ew_all_vs_ew_roots": block_t((ea - er)[np.isfinite(ea) & np.isfinite(er)]),
        "ew_live_vs_its_twins": pruned_vs_twin, "ew_roots_vs_their_twins": roots_vs_twin,
        "pruning_gain_net_of_twins": pruning_gain_net_of_twins,
        "allocator_vs_twin_by_year": byy, "years_positive": int(sum(v > 0 for v in byy.values())),
        "n_years": len(byy), "loo_worst": min(loo.values()) if loo else None,
        "loo_worst_year": min(loo, key=loo.get) if loo else None,
        "first_allocator_month": str(pd.Timestamp(months[int(np.argmax(ok))]).date()) if ok.any() else None,
    }
    branches = []
    for b in pop:
        sc = b.score(np.arange(b.born, len(months)))
        branches.append({"id": b.id, "label": b.label, "kind": b.kind, "parents": b.parent,
                         "born": str(pd.Timestamp(months[min(b.born, len(months) - 1)]).date()),
                         "died": str(pd.Timestamp(months[b.died]).date()) if b.died is not None else None,
                         "source": "+".join(sorted({SOURCE.get(_name(c, s), "?") for c, s in b.parts})),
                         "months": int(len(sc)), "mean_excess_vs_twin": float(sc.mean()) if len(sc) else None,
                         **{"t": block_t(sc).get("t_blocks")}})
    rec = {"run_id": run_id, "pid": os.getpid(), "licence": "PRODUCT_EXPERIMENT (simulation only)",
           "llm_spend_usd": 0.0, "args": vars(a),
           "inputs": {str(p): {"bytes": p.stat().st_size,
                               "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")}
                      for p in (PANEL, FUND, EB)},
           "n_roots": len(roots), "n_branches_ever": len(pop), "summary": summary, "epochs": distinct,
           "branches": branches, "elapsed_s": round(time.time() - t0, 1),
           "hindsight_note": "The ROOT selector list was written on 2026-11-11 by someone who has read the "
                             "2026-09-29 library boards; the epoch decisions are forward-only, the root list is not."}
    out = OUT / f"{run_id}.json"
    tmp = OUT / f"{run_id}.json.tmp"
    tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps(summary, indent=1, default=str), flush=True)
    print("DONE", out, f"{time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
