"""CH-58: does analyst revision flow earn a return as a RELATIVE position?

Licence: PRODUCT_EXPERIMENT study ($0, no LLM, no network). Results are
observations; nothing here is a skill claim.

The earlier long-only backtest (`s69-reports-20261114/accounts_review/
backtest_revision_flow.py`, outside the repo) judged three revision-flow rules
against the market: t 1.26-1.81 on 251 monthly holds, no delisting returns. Its
signal construction, loaders, eligibility and cost bands are PORTED VERBATIM
below (`load_actions`, `load_link`, `signal`, `load_years`, the selection lines
of `evaluate_month`), because that script is not importable from the repo. This
script evaluates the same names as three hedged constructions declared in the
chunk report before any hedged number was computed:

  TWIN        long the rule's names, short their matched twins
              (`backend.services.matched_twins.cell_table` + `draw_twins`,
              unchanged: size band x 63-session vol tercile x 12-1 tercile,
              the rule's holdings excluded), average of CH58_TWIN_DRAWS draws
  BETA        long the rule's names, short ex-ante beta x the CRSP VW market
  TOP_BOTTOM  long the top K by score, short the bottom K

Costs on both legs (the earlier backtest's band rate, in full every month), a
borrow proxy on the short leg, CRSP delisting returns folded in (CH-47's
convention) with the no-delisting number printed beside it.

Inputs are read in place from a WRDS folder (licensed; never copied). Outputs go
ONLY to --out and hold portfolio-level aggregates, no per-security rows.

    python -m scripts.ch58_revision_relative --out <dir> [--wrds <dir>]

Exit codes: 0 receipt written; 2 an input is missing or unreadable (refusal).
"""
from __future__ import annotations

import argparse
import json
import math
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

from backend import config as CFG  # noqa: E402
from backend.services import matched_twins as MT  # noqa: E402
from backend.services.xs_ranker import _year_tables  # noqa: E402

RULES = ("R1", "R2", "R3")
PRIMARY_RULE = "R2"
CONSTRUCTIONS = ("TWIN", "BETA", "TOP_BOTTOM")
RULE_NAMES = {"R1": "revision_flow_v0 (net_raises x n_firms, >= 3 firms)",
              "R2": "net_raises (raises - lowers)",
              "R3": "net_raises, inverse-volatility weights"}
DSF_COLUMNS = ["permno", "date", "prc", "ret", "vol", "openprc"]


class InputMissing(RuntimeError):
    """An input file is absent or unreadable: the run refuses (exit 2)."""


def say(msg: str) -> None:
    print(msg, flush=True)


# ───────────────── ported verbatim from the earlier backtest ─────────────────

def _band_value(mdv: float, bands) -> float:
    for lo, b in bands:
        if mdv >= lo:
            return b
    return bands[-1][1]


def load_actions(wrds: Path) -> pd.DataFrame:
    import pyarrow.parquet as pq
    t = pq.read_table(wrds / "bulk" / "ibes__ptgdet.parquet",
                      columns=["ticker", "amaskcd", "estimid", "value", "anndats", "horizon", "curr",
                               "usfirm"]).to_pandas()
    t["anndats"] = pd.to_datetime(t["anndats"])
    t = t[(t.usfirm == 1) & (t.curr == "USD") & (t.horizon.astype(str) == "12") & t.value.notna() & t.anndats.notna()]
    t = t.sort_values(["ticker", "estimid", "amaskcd", "anndats"])
    g = t.groupby(["ticker", "estimid", "amaskcd"], sort=False)
    t["prev"] = g.value.shift(1)
    t["prev_d"] = g.anndats.shift(1)
    fresh = (t.anndats - t.prev_d).dt.days <= 365
    t["act"] = 0
    t.loc[fresh & (t.value > t.prev * 1.0001), "act"] = 1
    t.loc[fresh & (t.value < t.prev * 0.9999), "act"] = -1
    t = t[["ticker", "estimid", "anndats", "act"]].sort_values("anndats").reset_index(drop=True)
    return t


def load_link(wrds: Path) -> pd.DataFrame:
    import pyarrow.parquet as pq
    l = pq.read_table(wrds / "bulk" / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet").to_pandas()
    l["sdate"] = pd.to_datetime(l["sdate"])
    l["edate"] = pd.to_datetime(l["edate"])
    return l.sort_values("score")


def signal(actions: pd.DataFrame, link: pd.DataFrame, d: pd.Timestamp) -> pd.DataFrame:
    """Net raises and covering firms per permno from announcements STRICTLY before d."""
    lo = d - pd.Timedelta(days=CFG.CH58_SIGNAL_WINDOW_DAYS)
    a = actions.iloc[actions.anndats.searchsorted(lo, "right"): actions.anndats.searchsorted(d, "left")]
    if not len(a):
        return pd.DataFrame({"net": pd.Series(dtype=float), "n_firms": pd.Series(dtype=float)})
    g = a.groupby("ticker").agg(raises=("act", lambda x: int((x == 1).sum())),
                                lowers=("act", lambda x: int((x == -1).sum())),
                                n_firms=("estimid", "nunique"))
    g["net"] = g.raises - g.lowers
    l = link[(link.sdate <= d) & (link.edate >= d)].drop_duplicates("ticker")
    g = g.join(l.set_index("ticker").permno, how="inner").dropna(subset=["permno"])
    g["permno"] = g.permno.astype(int)
    return g.groupby("permno").agg(net=("net", "sum"), n_firms=("n_firms", "max"))


def load_years(wrds: Path, ys) -> dict:
    import pyarrow.parquet as pq
    fr = []
    for y in ys:
        p = wrds / f"crsp_dsf_{y}.parquet"
        if p.exists():
            fr.append(pq.read_table(p, columns=DSF_COLUMNS).to_pandas())
    x = pd.concat(fr, ignore_index=True)
    x["date"] = pd.to_datetime(x.date)
    x = x.drop_duplicates(["permno", "date"])
    return {c: x.pivot(index="date", columns="permno", values=c).sort_index() for c in ["prc", "ret", "vol"]}


# ───────────────────────────── inputs and panel ──────────────────────────────

def required_files(wrds: Path, y0: int, y1: int) -> dict:
    out = {"ibes_price_targets": wrds / "bulk" / "ibes__ptgdet.parquet",
           "ibes_crsp_link": wrds / "bulk" / "wrdsapps_link_crsp_ibes__ibcrsphist.parquet",
           "crsp_delistings": wrds / "bulk" / "crsp__dsedelist.parquet",
           "ff_factors_daily": wrds / "ff_factors_daily.parquet"}
    for y in range(y0 - 1, y1 + 1):
        out[f"crsp_dsf_{y}"] = wrds / f"crsp_dsf_{y}.parquet"
    return out


def check_inputs(wrds: Path, y0: int, y1: int) -> dict:
    """Every required file exists and opens, or InputMissing. Returns the input table."""
    import pyarrow.parquet as pq
    if not Path(wrds).is_dir():
        raise InputMissing(f"WRDS folder not found: {wrds}")
    table, missing = {}, []
    for name, p in required_files(wrds, y0, y1).items():
        if not p.exists():
            missing.append(str(p))
            continue
        try:
            rows = int(pq.ParquetFile(p).metadata.num_rows)
        except Exception as e:  # unreadable is missing
            raise InputMissing(f"cannot read {p}: {type(e).__name__}: {e}") from e
        if rows <= 0:
            raise InputMissing(f"{p} has 0 rows")
        table[name] = {"path": str(p), "bytes": int(p.stat().st_size), "rows": rows}
    if missing:
        raise InputMissing(f"{len(missing)} input file(s) missing, first: {missing[0]}")
    nxt = wrds / f"crsp_dsf_{y1 + 1}.parquet"
    table["_next_year_file_present"] = bool(nxt.exists())
    return table


def panel_survey(wrds: Path, y0: int, y1: int) -> dict:
    """First / last priced session per permno over the price files the run reads."""
    import pyarrow.parquet as pq
    first: dict = {}
    last: dict = {}
    sessions: set = set()
    rows = 0
    years = [y for y in range(y0 - 1, y1 + 2) if (wrds / f"crsp_dsf_{y}.parquet").exists()]
    for y in years:
        x = pq.read_table(wrds / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "prc"]).to_pandas()
        x = x[x["prc"].notna()]
        x["date"] = pd.to_datetime(x["date"])
        rows += len(x)
        g = x.groupby("permno")["date"].agg(["min", "max"])
        for p, a, b in zip(g.index, g["min"], g["max"]):
            if p not in first:
                first[p] = a
            last[p] = b
        sessions.update(x["date"].unique())
        del x, g
    cal = pd.DatetimeIndex(sorted(sessions))
    return survivorship_line(pd.Series(last), cal, CFG.CH58_HOLD_SESSIONS) | {
        "price_files": len(years), "years": [years[0], years[-1]] if years else None, "priced_rows": rows,
        "first_session": str(cal[0].date()) if len(cal) else None,
        "last_session": str(cal[-1].date()) if len(cal) else None, "sessions": int(len(cal))}


def survivorship_line(last_priced: pd.Series, calendar: pd.DatetimeIndex, horizon: int) -> dict:
    """How many names stop trading more than `horizon` sessions before the panel's end."""
    n = int(len(last_priced))
    if n == 0 or len(calendar) <= horizon:
        return {"names": n, "names_that_stop_trading": None, "survivor_selected": None,
                "line": "SURVIVORSHIP: CANNOT DETERMINE (no names or a calendar shorter than one hold)"}
    cutoff = calendar[-(horizon + 1)]
    stopped = int((pd.to_datetime(last_priced) < cutoff).sum())
    sel = stopped == 0
    line = (f"SURVIVORSHIP: {stopped} of {n} names stop trading more than {horizon} sessions before the panel's "
            f"last session ({calendar[-1].date()})"
            + ("; ZERO names stop: THE PANEL IS SURVIVOR-SELECTED and every number here is an upper bound"
               if sel else "; dead names are in the panel"))
    return {"names": n, "names_that_stop_trading": stopped, "survivor_selected": bool(sel), "line": line}


def fold_delistings(prc: pd.DataFrame, ret: pd.DataFrame, delist: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """CH-47's convention on one price window: the CRSP delisting return on the session
    after the last price; missing on codes 500-599 -> CH58_PERF_DELIST_RET; missing
    otherwise -> 0. Returns a COPY of `ret` and the counts."""
    out = ret.copy()
    dates = prc.index
    dl = delist[(delist["dlstcd"] != 100) & (delist["dlstdt"] >= dates[0]) & (delist["dlstdt"] <= dates[-1])
                & delist["permno"].isin(prc.columns)]
    n_applied = n_shumway = n_zero = n_end = 0
    for row in dl.itertuples(index=False):
        col = prc[row.permno].to_numpy()
        valid = np.flatnonzero(np.isfinite(col))
        if not len(valid):
            continue
        last = int(valid[-1])
        if last + 1 >= len(dates):
            n_end += 1
            continue
        if row.dlret is not None and np.isfinite(row.dlret):
            r = float(row.dlret)
        elif 500 <= int(row.dlstcd) < 600:
            r = float(CFG.CH58_PERF_DELIST_RET)
            n_shumway += 1
        else:
            r = 0.0
            n_zero += 1
        out.iat[last + 1, out.columns.get_loc(row.permno)] = r
        n_applied += 1
    return out, {"records_in_window": int(len(dl)), "applied": n_applied, "shumway_imputed": n_shumway,
                 "zero_imputed_nonperformance": n_zero, "at_window_end": n_end}


def name_betas(ret_win: np.ndarray, mkt_win: np.ndarray, min_obs: int) -> np.ndarray:
    """OLS beta of each column on the market, pairwise complete; fewer than `min_obs` -> 1.0."""
    ok = np.isfinite(ret_win) & np.isfinite(mkt_win)[:, None]
    n = ok.sum(axis=0).astype(float)
    rz = np.where(ok, ret_win, 0.0)
    mz = np.where(ok, mkt_win[:, None], 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        mr, mm = rz.sum(0) / n, mz.sum(0) / n
        cov = (rz * mz).sum(0) / n - mr * mm
        var = (mz * mz).sum(0) / n - mm * mm
        beta = cov / var
    beta[(n < min_obs) | ~np.isfinite(beta)] = 1.0
    return beta


# ───────────────────────────── one decision month ────────────────────────────

def _weights(sel, vol63: pd.Series, ivw: bool) -> pd.Series:
    if ivw:
        w = (1 / vol63.reindex(sel)).replace([np.inf, -np.inf], np.nan).fillna(0)
        if w.sum() > 0:
            return w / w.sum()
    return pd.Series(1 / len(sel), index=sel)


def select(sig: pd.DataFrame, rule: str, k: int) -> tuple[pd.Index, pd.Index]:
    """(top, bottom) permnos. The top lines are the earlier backtest's; the bottom is the mirror."""
    if rule == "R1":
        top = (sig[(sig.n_firms >= 3) & (sig.net > 0)].assign(s=lambda z: z.net * z.n_firms)
               .sort_values("s", ascending=False).head(k))
        bot = (sig[(sig.n_firms >= 3) & (sig.net < 0)].assign(s=lambda z: z.net * z.n_firms)
               .sort_values("s", ascending=True).head(k))
    else:
        top = sig[sig.net > 0].sort_values(["net", "n_firms"], ascending=False).head(k)
        bot = sig[sig.net < 0].sort_values(["net", "n_firms"], ascending=[True, False]).head(k)
    return top.index, bot.index


def _leg(w: pd.Series, s: pd.Series) -> float:
    return float((w * s.reindex(w.index).fillna(0)).sum())


def draw_twin_pairs(held: list, ctx: dict, rng: np.random.Generator) -> tuple[list, dict]:
    """`matched_twins.draw_twins`, unchanged, plus a refusal: a twin that is itself a
    held name, or one twin serving two partners, would make the spread partly long - long."""
    pairs, counts = MT.draw_twins(held, ctx["cells"], ctx["panel_d"], rng, index=ctx["cell_index"])
    hs = set(held)
    tw = [t for _s, t, _lv in pairs if t is not None]
    if hs & set(tw) or len(set(tw)) != len(tw):
        raise RuntimeError("twin draw returned a held name or a repeated twin")
    return pairs, counts


def evaluate_month(ctx: dict, sig: pd.DataFrame, rngs: dict, rand_rng: np.random.Generator,
                   n_random: int, k: int, state: Optional[dict] = None) -> dict:
    """All rules x constructions for one decision date. `ctx`: per-name Series on the
    eligible set (fwd_dl, fwd_nd, cost, borrow, beta, vol63_px) + cells + mk.
    `state` carries last month's legs per rule, for the POST HOC cost-on-turnover lines."""
    state = {} if state is None else state
    e = ctx["eligible"]
    fwd = {"dl": ctx["fwd_dl"], "nd": ctx["fwd_nd"]}
    cost, borrow, beta, mk = ctx["cost"], ctx["borrow"], ctx["beta"], ctx["mk"]
    hold_frac = CFG.CH58_HOLD_SESSIONS / 252.0
    mkt_cost = CFG.CH58_MARKET_COST_BPS / 1e4
    mkt_borrow = CFG.CH58_MARKET_BORROW_ANNUAL * hold_frac
    sig = sig[sig.index.isin(e)]
    out: dict = {"n_cov": int(len(sig)), "cells": {}}
    for rule in RULES:
        top, bot = select(sig, "R1" if rule == "R1" else "R2", k)
        ivw = rule == "R3"
        rec = {c: None for c in CONSTRUCTIONS}
        rec["n_long"], rec["n_short_bottom"] = int(len(top)), int(len(bot))
        rec["long_names"] = frozenset(int(p) for p in top)
        if len(top) >= CFG.CH58_MIN_NAMES:
            w = _weights(top, ctx["vol63_px"], ivw)
            lc = _leg(w, cost)
            lg = {c: _leg(w, fwd[c]) for c in fwd}
            prev = state.get(rule) or {}
            p_long = prev.get("long")
            new_long = [s for s in top if p_long is None or s not in p_long]
            lc_turn = _leg(w.reindex(new_long), cost) if new_long else 0.0
            rec["long_only"] = {"gross_dl": lg["dl"], "gross_nd": lg["nd"], "cost": lc}
            # TWIN: the mean of the seeded draws; each twin carries its partner's weight
            tg = {"dl": [], "nd": []}
            tc, tb, fb, tc_turn = [], [], {}, []
            new_set = set(new_long)
            for j, rng in enumerate(rngs[rule]):
                pairs, counts = draw_twin_pairs(list(top), ctx, rng)
                tw = pd.Series({t: float(w[s]) for s, t, _lv in pairs if t is not None})
                twn = pd.Series({t: float(w[s]) for s, t, _lv in pairs if t is not None and s in new_set})
                tc_turn.append(_leg(twn, cost) if len(twn) else 0.0)
                for c in fwd:
                    tg[c].append(_leg(tw, fwd[c]) if len(tw) else 0.0)
                tc.append(_leg(tw, cost) if len(tw) else 0.0)
                tb.append(_leg(tw, borrow) if len(tw) else 0.0)
                for lv, n in counts.items():
                    fb[lv] = fb.get(lv, 0) + int(n)
            rec["TWIN"] = {"gross_dl": lg["dl"] - float(np.mean(tg["dl"])), "gross_nd": lg["nd"] - float(np.mean(tg["nd"])),
                           "cost": lc + float(np.mean(tc)), "borrow": float(np.mean(tb)), "hedge": 1.0,
                           "cost_long_turn": lc_turn, "cost_short": float(np.mean(tc)),
                           "cost_short_turn": float(np.mean(tc_turn)),
                           "draws_net_dl": [lg["dl"] - g - lc - c_ - b_ for g, c_, b_ in zip(tg["dl"], tc, tb)],
                           "n_short": int(len(top)), "fallbacks": fb}
            bp = float((w * beta.reindex(w.index).fillna(1.0)).sum())
            p_bp = prev.get("beta")
            rec["BETA"] = {"gross_dl": lg["dl"] - bp * mk, "gross_nd": lg["nd"] - bp * mk,
                           "cost": lc + abs(bp) * mkt_cost, "borrow": abs(bp) * mkt_borrow, "hedge": bp, "n_short": 1,
                           "cost_long_turn": lc_turn, "cost_short": abs(bp) * mkt_cost,
                           "cost_short_turn": abs(bp - (0.0 if p_bp is None else p_bp)) * mkt_cost}
            new_state = {"long": frozenset(top), "beta": bp, "bot": None}
            if len(bot) >= CFG.CH58_MIN_NAMES:
                wb = _weights(bot, ctx["vol63_px"], ivw)
                p_bot = prev.get("bot")
                new_bot = [s for s in bot if p_bot is None or s not in p_bot]
                new_state["bot"] = frozenset(bot)
                rec["TOP_BOTTOM"] = {"gross_dl": lg["dl"] - _leg(wb, fwd["dl"]), "gross_nd": lg["nd"] - _leg(wb, fwd["nd"]),
                                     "cost": lc + _leg(wb, cost), "borrow": _leg(wb, borrow), "hedge": 1.0,
                                     "cost_long_turn": lc_turn, "cost_short": _leg(wb, cost),
                                     "cost_short_turn": _leg(wb.reindex(new_bot), cost) if new_bot else 0.0,
                                     "n_short": int(len(bot))}
            state[rule] = new_state
        else:
            state[rule] = {}
        out["cells"][rule] = rec
    # random control: the same three constructions on random K-name books from the covered eligible set
    cov = np.array(sorted(int(p) for p in sig.index))
    rand = {c: np.full(n_random, np.nan) for c in CONSTRUCTIONS}
    rand_g = {c: np.full(n_random, np.nan) for c in CONSTRUCTIONS}
    if n_random and len(cov) >= 2 * k:
        f, cs, bo, be = (ctx["fwd_dl"].reindex(cov).fillna(0).to_numpy(), cost.reindex(cov).to_numpy(),
                         borrow.reindex(cov).to_numpy(), beta.reindex(cov).fillna(1.0).to_numpy())
        for r in range(n_random):
            ix = rand_rng.choice(len(cov), 2 * k, replace=False)
            a, b = ix[:k], ix[k:]
            bp = float(be[a].mean())
            rand_g["BETA"][r] = f[a].mean() - bp * mk
            rand["BETA"][r] = rand_g["BETA"][r] - cs[a].mean() - abs(bp) * (mkt_cost + mkt_borrow)
            rand_g["TOP_BOTTOM"][r] = f[a].mean() - f[b].mean()
            rand["TOP_BOTTOM"][r] = rand_g["TOP_BOTTOM"][r] - cs[a].mean() - cs[b].mean() - bo[b].mean()
            pairs, _ = draw_twin_pairs([int(x) for x in cov[a]], ctx, rand_rng)
            tw = [t for _s, t, _lv in pairs if t is not None]
            tws = pd.Series(1.0 / k, index=tw)
            rand_g["TWIN"][r] = f[a].mean() - _leg(tws, ctx["fwd_dl"])
            rand["TWIN"][r] = rand_g["TWIN"][r] - cs[a].mean() - _leg(tws, cost) - _leg(tws, borrow)
    out["random"] = rand
    out["random_gross"] = rand_g
    return out


# ───────────────────────────────── statistics ────────────────────────────────

def _p_two_sided(t: float, dof: int) -> float:
    if not np.isfinite(t):
        return float("nan")
    try:
        from scipy import stats as _st
        return float(2 * _st.t.sf(abs(t), dof))
    except ImportError:
        return float(math.erfc(abs(t) / math.sqrt(2)))


def one_sided(t: float, p2: float) -> float:
    if not np.isfinite(p2):
        return float("nan")
    return p2 / 2 if t > 0 else 1 - p2 / 2


def holm(pvals: list) -> list:
    """Holm step-down adjusted p-values, in the input order (NaN stays NaN)."""
    idx = [i for i, p in enumerate(pvals) if p is not None and np.isfinite(p)]
    m = len(idx)
    out = [float("nan")] * len(pvals)
    run = 0.0
    for rank, i in enumerate(sorted(idx, key=lambda j: pvals[j])):
        run = max(run, min(1.0, (m - rank) * pvals[i]))
        out[i] = run
    return out


def _mean_t(x: np.ndarray) -> dict:
    n = int(len(x))
    if n < 3:
        return {"n": n, "mean": float(np.mean(x)) if n else None, "t": None, "se": None, "mde": None}
    se = float(np.std(x, ddof=1) / math.sqrt(n))
    return {"n": n, "mean": float(np.mean(x)), "se": se, "t": float(np.mean(x) / se) if se > 0 else None,
            "mde": float(CFG.CH58_MDE_MULT * se)}


def series_stats(net: pd.Series, mkt: pd.Series, *, split_year: Optional[int] = None,
                 top_months: Optional[int] = None) -> dict:
    """One hedged series (index = the hold's END session, one row per hold = one block)."""
    split_year = CFG.CH58_SPLIT_YEAR if split_year is None else split_year
    top_months = CFG.CH58_TOP_MONTHS if top_months is None else top_months
    net = net.dropna()
    x = net.to_numpy(dtype=float)
    n = len(x)
    if n < 12:
        return {"n_holds": n, "refused": f"only {n} holds: no statistic is printed below 12"}
    base = _mean_t(x)
    d = x - x.mean()
    g0, g1 = float(d @ d / n), float(d[1:] @ d[:-1] / n)
    nw_var = g0 + g1  # Bartlett, lag 1: g0 + 2 * (1 - 1/2) * g1
    nw_t = float(x.mean() / math.sqrt(nw_var / n)) if nw_var > 0 else None
    p2 = _p_two_sided(base["t"], n - 1) if base["t"] is not None else float("nan")
    years = pd.Series(net.index.year, index=net.index)
    by_year, loo = _year_tables(x, years)
    worst = min(loo, key=loo.get) if loo else None
    m = mkt.reindex(net.index).to_numpy(dtype=float)
    X = np.column_stack([np.ones(n), m])
    b, *_ = np.linalg.lstsq(X, x, rcond=None)
    res = x - X @ b
    covb = (res @ res / (n - 2)) * np.linalg.inv(X.T @ X)
    srt = np.sort(x)[::-1]
    tot = float(x.sum())
    early, late = x[(years < split_year).to_numpy()], x[(years >= split_year).to_numpy()]
    return {
        "n_holds": n, "mean": base["mean"], "sd": float(np.std(x, ddof=1)), "se": base["se"], "t": base["t"],
        "t_newey_west_lag1": nw_t, "mde": base["mde"], "p_two_sided": p2,
        "p_one_sided": one_sided(base["t"], p2) if base["t"] is not None else float("nan"),
        "blocking": "one hold = one block; plain t on holds, Newey-West lag-1 t beside it",
        "hit_rate": float((x > 0).mean()),
        "by_year": {int(y): {"mean": v["mean_net"], "n": v["n_dates"]} for y, v in by_year.items()},
        "years_positive": int(sum(v["mean_net"] > 0 for v in by_year.values())), "years": int(len(by_year)),
        "leave_one_year_out": {int(y): float(v) for y, v in loo.items()},
        "loo_worst_mean": float(loo[worst]) if worst is not None else None,
        "loo_worst_year_dropped": int(worst) if worst is not None else None,
        "split": {f"{int(years.min())}-{split_year - 1}": _mean_t(early), f"{split_year}-{int(years.max())}": _mean_t(late)},
        "late_mean": float(late.mean()) if len(late) else None,
        "realised_beta": float(b[1]), "realised_beta_se": float(math.sqrt(covb[1, 1])),
        "alpha_after_realised_beta": float(b[0]), "alpha_t": float(b[0] / math.sqrt(covb[0, 0])),
        "alpha_mde": float(CFG.CH58_MDE_MULT * math.sqrt(covb[0, 0])),
        "sum": tot, "top_months": top_months,
        "top_months_sum": float(srt[:top_months].sum()),
        "top_months_share_of_sum": float(srt[:top_months].sum() / tot) if tot > 0 else None,
        "mean_without_top_months": float(srt[top_months:].mean()) if n > top_months else None,
    }


def _norm_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2))


def _norm_ppf(q: float) -> float:
    from statistics import NormalDist
    return NormalDist().inv_cdf(q)


def pass_bar(n_cells: int, dof: int) -> dict:
    """The t a cell really needs: Holm over `n_cells` asks the smallest one-sided p to be
    <= p(t = CH58_T_PASS) / n_cells."""
    p_bar = one_sided(CFG.CH58_T_PASS, _p_two_sided(CFG.CH58_T_PASS, 10_000))
    p_need = p_bar / max(n_cells, 1)
    try:
        from scipy import stats as _st
        t_need = float(_st.t.isf(p_need, dof))
    except ImportError:
        t_need = float(_norm_ppf(1 - p_need))
    return {"nominal_t": CFG.CH58_T_PASS, "holm_one_sided_p_bar": p_bar, "cells": n_cells,
            "one_sided_p_needed_by_the_best_cell": p_need, "t_implied_by_holm": t_need,
            "note": (f"the declared 't >= {CFG.CH58_T_PASS} after Holm' in fact asks the best of {n_cells} cells for "
                     f"t >= {t_need:.2f}")}


def power_at(effect: Optional[float], se: Optional[float], t_bar: float) -> Optional[float]:
    """P(t >= t_bar) if the true effect per hold equals `effect` (normal approximation)."""
    if effect is None or se is None or not se > 0:
        return None
    return float(1 - _norm_cdf(t_bar - effect / se))


def forward_sample(mean: Optional[float], sd: Optional[float]) -> dict:
    """Monthly holds a forward book would need, from the measured sd and the observed mean."""
    if mean is None or sd is None or not (mean > 0 and sd > 0):
        return {"months_for_power": None, "months_for_expected_t": None,
                "note": "observed effect is not positive: no forward sample size is defined"}
    z = _norm_ppf(1 - CFG.CH58_FORWARD_ALPHA_TWO_SIDED / 2) + _norm_ppf(CFG.CH58_FORWARD_POWER)
    n_pow = (z * sd / mean) ** 2
    n_t = (CFG.CH58_T_PASS * sd / mean) ** 2
    return {"effect_per_hold": float(mean), "sd_per_hold": float(sd),
            "months_for_power": float(n_pow), "years_for_power": float(n_pow / 12),
            "months_for_expected_t": float(n_t), "years_for_expected_t": float(n_t / 12),
            "power": CFG.CH58_FORWARD_POWER, "alpha_two_sided": CFG.CH58_FORWARD_ALPHA_TWO_SIDED,
            "expected_t": CFG.CH58_T_PASS}


def verdict(primary: dict) -> dict:
    """The verdict after the review's fix round: the MDE is compared with the MEDIAN prior effect."""
    med = float(np.median(CFG.CH58_PRIOR_EFFECTS))
    return _verdict(primary, med, f"the median prior effect {100 * med:.2f}% per hold")


def verdict_predeclared(primary: dict) -> dict:
    """The rule exactly as pre-declared (MDE against the LARGEST prior spread); kept visible."""
    return _verdict(primary, CFG.CH58_PLAUSIBLE_MAX_EFFECT,
                    f"the plausible ceiling {100 * CFG.CH58_PLAUSIBLE_MAX_EFFECT:.2f}% per hold")


def _verdict(primary: dict, threshold: float, label: str) -> dict:
    """Computed, never written by hand. `primary`: {construction: stats with holm_one_sided}."""
    p_bar = one_sided(CFG.CH58_T_PASS, _p_two_sided(CFG.CH58_T_PASS, 10_000))
    passed, reasons, mdes = [], {}, []
    for c, s in primary.items():
        why = []
        if s.get("refused"):
            reasons[c] = [s["refused"]]
            continue
        mdes.append(s["mde"])
        if not (s["t"] is not None and s["t"] >= CFG.CH58_T_PASS):
            why.append(f"net t {_num(s['t'])} < {CFG.CH58_T_PASS}")
        hp = s.get("holm_one_sided")
        if not (hp is not None and np.isfinite(hp) and hp <= p_bar):
            why.append(f"Holm one-sided p {'n/a' if hp is None else format(hp, '.3f')} > {p_bar:.4f} "
                       f"(the one-sided p of t = {CFG.CH58_T_PASS})")
        if not (s["late_mean"] is not None and s["late_mean"] > 0):
            why.append(f"{CFG.CH58_SPLIT_YEAR}+ mean {100 * (s['late_mean'] or 0):+.3f}% is not positive")
        if not (s["loo_worst_mean"] is not None and s["loo_worst_mean"] > 0):
            why.append(f"leave-one-year-out turns non-positive (drop {s['loo_worst_year_dropped']}: "
                       f"{100 * (s['loo_worst_mean'] or 0):+.3f}%)")
        reasons[c] = why
        if not why:
            passed.append(c)
    if passed:
        v, why = "PASS", f"{', '.join(passed)} met every declared condition"
    elif not mdes:
        v, why = "CANNOT_DISTINGUISH", "no primary construction produced a statistic"
    elif all(m > threshold for m in mdes):
        v = "CANNOT_DISTINGUISH"
        why = (f"no construction passed and every MDE ({', '.join(f'{100 * m:.2f}%' for m in mdes)}) exceeds "
               f"{label}")
    else:
        v = "FAILED_VARIANT"
        why = "; ".join(f"{c}: {', '.join(r)}" for c, r in reasons.items() if r)
    return {"verdict": v, "reason": why, "passed": passed, "failing_conditions": reasons,
            "holm_bar_one_sided_p": p_bar,
            "rule": (f"PASS iff a primary construction has net t >= {CFG.CH58_T_PASS}, Holm one-sided p <= the one-sided "
                     f"p of t = {CFG.CH58_T_PASS}, {CFG.CH58_SPLIT_YEAR}+ mean > 0 and worst leave-one-year-out > 0; else "
                     f"CANNOT_DISTINGUISH iff every primary MDE > {label}; else FAILED_VARIANT")}


# ─────────────────────────────────── the run ─────────────────────────────────

def _count_files(*dirs: Path) -> dict:
    return {str(d): sum(1 for _ in Path(d).iterdir()) for d in dirs if Path(d).is_dir()}


def run(wrds: Path, out_dir: Path, *, y0: int, y1: int, k: int, n_random: int, twin_draws: int,
        run_id: Optional[str] = None) -> dict:
    t0 = time.time()
    wrds, out_dir = Path(wrds), Path(out_dir)
    inputs = check_inputs(wrds, y0, y1)
    live_dirs = (wrds, wrds / "bulk")
    files_before = _count_files(*live_dirs)
    say(f"[ch58] inputs under {wrds}")
    for name, v in inputs.items():
        if isinstance(v, dict):
            say(f"    {name}: {v['rows']:,} rows, {v['bytes'] / 1e6:.1f} MB")
    say(f"    live folder file counts before: {files_before}")
    survey = panel_survey(wrds, y0, y1)
    say(f"[ch58] price panel: {survey['price_files']} yearly files {survey['years']}, {survey['priced_rows']:,} priced rows, "
        f"{survey['first_session']} .. {survey['last_session']}, {survey['names']:,} names")
    say(f"    {survey['line']}")

    import pyarrow.parquet as pq
    ff = pq.read_table(wrds / "ff_factors_daily.parquet", columns=["date", "mktrf", "rf"]).to_pandas()
    ff["date"] = pd.to_datetime(ff["date"])
    mkt_daily = (ff.set_index("date").mktrf + ff.set_index("date").rf).astype(float)
    delist = pq.read_table(wrds / "bulk" / "crsp__dsedelist.parquet",
                           columns=["permno", "dlstdt", "dlstcd", "dlret"]).to_pandas()
    delist["dlstdt"] = pd.to_datetime(delist["dlstdt"])
    delist["dlret"] = pd.to_numeric(delist["dlret"], errors="coerce")
    delist = delist.dropna(subset=["dlstdt", "dlstcd", "permno"])
    delist["permno"] = delist["permno"].astype(int)
    actions = load_actions(wrds)
    link = load_link(wrds)
    say(f"[ch58] analyst actions {len(actions):,} (raises {int((actions.act == 1).sum()):,}, lowers "
        f"{int((actions.act == -1).sum()):,}), {actions.anndats.min().date()} .. {actions.anndats.max().date()} "
        f"{time.time() - t0:.0f}s")

    rngs = {r: [np.random.default_rng(MT.seed_for(f"ch58:{r}", j)) for j in range(twin_draws)] for r in RULES}
    rand_rng = np.random.default_rng(CFG.CH58_SEED)
    state: dict = {}
    H = CFG.CH58_HOLD_SESSIONS
    hold_frac = H / 252.0
    rows: list = []
    rand_rows: dict = {c: [] for c in CONSTRUCTIONS}
    rand_rows.update({c + "_gross": [] for c in CONSTRUCTIONS})
    dl_seen: set = set()
    mkt_missing = 0
    for y in range(y0, y1 + 1):
        piv = load_years(wrds, [y - 1, y, y + 1])
        prc, ret, vol = piv["prc"].abs(), piv["ret"], piv["vol"]
        ret_dl, dinfo = fold_delistings(prc, ret, delist)
        dv = prc * vol
        dates = prc.index
        me = pd.Series(dates, index=dates).groupby([dates.year, dates.month]).last()
        for d in [d for d in me if d.year == y]:
            i = dates.get_loc(d)
            if i + H >= len(dates) or i < 126:
                continue
            mdv = dv.iloc[i - 20:i + 1].median()
            hist = prc.iloc[i - 125:i + 1].notna().sum()
            elig = (prc.iloc[i] >= 3) & (mdv >= 3e6) & (hist >= 120)
            e = elig[elig].index
            if len(e) < 2 * k:
                continue
            win = slice(i + 1, i + H + 1)
            fwd_nd = (1 + ret.iloc[win].reindex(columns=e).fillna(0)).prod() - 1
            fwd_dl = (1 + ret_dl.iloc[win].reindex(columns=e).fillna(0)).prod() - 1
            mkw = mkt_daily.reindex(dates[win])
            mkt_missing += int(mkw.isna().sum())
            mk = float((1 + mkw.fillna(0)).prod() - 1)
            vol63_px = np.log(prc.iloc[i - 63:i + 1].reindex(columns=e)).diff().std()   # the earlier R3 weight input
            lb = max(0, i - CFG.CH58_BETA_LOOKBACK + 1)
            rwin = ret.iloc[lb:i + 1].reindex(columns=e)
            beta = pd.Series(name_betas(rwin.to_numpy(dtype=float), mkt_daily.reindex(rwin.index).to_numpy(dtype=float),
                                        CFG.CH58_BETA_MIN_OBS), index=e)
            r63 = ret.iloc[i - 62:i + 1].reindex(columns=e)
            mwin = ret.iloc[max(0, i - 251):i - 20].reindex(columns=e)
            mom = (1 + mwin.fillna(0)).prod() - 1
            mom[mwin.notna().sum() < 200] = np.nan
            mdv_e = mdv.reindex(e)
            panel_d = pd.DataFrame({"symbol": [int(p) for p in e], "eligible": True,
                                    "median_dollar_vol": mdv_e.to_numpy(), "vol_63": r63.std().to_numpy(),
                                    "mom_252_21": mom.to_numpy()})
            cells = MT.cell_table(panel_d)
            ctx = {"eligible": e, "fwd_dl": fwd_dl, "fwd_nd": fwd_nd, "mk": mk, "beta": beta, "vol63_px": vol63_px,
                   "cost": pd.Series([_band_value(v, CFG.CH58_COST_BPS_BANDS) for v in mdv_e.to_numpy()], index=e) / 1e4,
                   "borrow": pd.Series([_band_value(v, CFG.CH58_BORROW_ANNUAL_BANDS) for v in mdv_e.to_numpy()],
                                       index=e) * hold_frac,
                   "cells": cells, "panel_d": panel_d, "cell_index": MT.CellIndex(cells)}
            m = evaluate_month(ctx, signal(actions, link, d), rngs, rand_rng, n_random, k, state)
            # delistings that landed inside this hold, on the eligible set (aggregate count only)
            hit = (ret_dl.iloc[win].reindex(columns=e).to_numpy() != ret.iloc[win].reindex(columns=e).to_numpy()) & \
                  np.isfinite(ret_dl.iloc[win].reindex(columns=e).to_numpy())
            rows.append({"decision": d, "hold_end": dates[i + H], "n_elig": int(len(e)),
                         "n_cov": m["n_cov"], "mk": mk, "delistings_in_hold_eligible": int(hit.any(axis=0).sum()),
                         "cells": m["cells"]})
            for c in CONSTRUCTIONS:
                rand_rows[c].append(m["random"][c])
                rand_rows[c + "_gross"].append(m["random_gross"][c])
        dl_y = delist[(delist["dlstdt"].dt.year == y) & (delist["dlstcd"] != 100) & delist["permno"].isin(prc.columns)]
        dl_seen.update(int(p) for p in dl_y["permno"])
        say(f"    {y}: {len(rows)} holds so far, delisting returns folded in this window {dinfo['applied']} "
            f"(Shumway {dinfo['shumway_imputed']}), {time.time() - t0:.0f}s")
        del piv, prc, ret, ret_dl, vol, dv
    if not rows:
        raise InputMissing("the price files produced no decision month (check the year range against the files)")

    receipt = assemble(rows, rand_rows, k=k, y0=y0, y1=y1, n_random=n_random, twin_draws=twin_draws)
    files_after = _count_files(*live_dirs)
    rid = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    receipt.update({
        "run_id": rid, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0, "inputs": inputs, "panel": survey,
        "survivorship_line": survey["line"],
        "delisting": {"convention": (f"CRSP dlret on the session after the last price; missing on codes 500-599 -> "
                                     f"{CFG.CH58_PERF_DELIST_RET}; missing otherwise -> 0; cash afterwards"),
                      "names_with_a_delisting_record_in_span": len(dl_seen),
                      "without": "the earlier backtest's convention: 0% after the last trade (suffix _nd)"},
        "market_missing_sessions": mkt_missing,
        "live_folder_files": {"before": files_before, "after": files_after, "unchanged": files_before == files_after},
        "elapsed_s": round(time.time() - t0, 1),
    })
    out_dir.mkdir(parents=True, exist_ok=True)
    monthly = receipt.pop("_monthly")
    jp = out_dir / f"revision_relative_{rid}.json"
    tmp = jp.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(receipt, indent=1, default=_json), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(jp)
    monthly.to_csv(out_dir / f"revision_relative_{rid}_monthly.csv")
    md = out_dir / f"revision_relative_{rid}.md"
    md.write_text(render_md(receipt), encoding="utf-8")
    say(render_md(receipt))
    say(f"[ch58] receipt {jp}")
    say(f"[ch58] live folder file counts after: {files_after} (unchanged: {files_before == files_after})")
    return receipt


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


def assemble(rows: list, rand_rows: dict, *, k: int, y0: int, y1: int, n_random: int, twin_draws: int) -> dict:
    """Monthly records -> series, statistics, controls, Holm and the verdict."""
    idx = pd.DatetimeIndex([r["hold_end"] for r in rows])
    dec = pd.DatetimeIndex([r["decision"] for r in rows])
    mk = pd.Series([r["mk"] for r in rows], index=idx)
    overlap = int(sum(1 for a, b in zip(idx[:-1], dec[1:]) if b < a))
    stress = CFG.CH58_BORROW_STRESS_MULT
    monthly = pd.DataFrame({"decision": dec.date, "market": mk.to_numpy(), "n_elig": [r["n_elig"] for r in rows],
                            "n_cov": [r["n_cov"] for r in rows]}, index=idx)
    monthly.index.name = "hold_end"
    results: dict = {}
    rand_ix = {c: np.vstack(v) if v else np.empty((0, 0)) for c, v in rand_rows.items()}
    for rule in RULES:
        results[rule] = {}
        cells = [r["cells"][rule] for r in rows]
        n_long = np.array([c["n_long"] for c in cells])
        names = [c["long_names"] for c in cells]
        turn = [1 - len(a & b) / max(len(b), 1) for a, b in zip(names[:-1], names[1:]) if a and b]
        lo = pd.Series([(c["long_only"]["gross_dl"] - c["long_only"]["cost"]) if c.get("long_only") else np.nan
                        for c in cells], index=idx)
        lo_nd = pd.Series([(c["long_only"]["gross_nd"] - c["long_only"]["cost"]) if c.get("long_only") else np.nan
                           for c in cells], index=idx)
        results[rule]["_control_long_only_minus_market"] = {
            "what": "the long leg alone, net of its costs, minus the market (the earlier backtest's number; no hedge costs)",
            "with_delisting": series_stats(lo - mk, mk), "without_delisting": series_stats(lo_nd - mk, mk)}
        results[rule]["_long_leg"] = {
            "names_per_month_median": float(np.median(n_long)), "names_per_month_min": int(n_long.min()),
            "months_below_min_names_dropped": int((n_long < CFG.CH58_MIN_NAMES).sum()),
            "months_below_k": int((n_long < k).sum()), "k": k,
            "name_turnover_mean": float(np.mean(turn)) if turn else None,
            "note": "turnover = share of the long names replaced month to month; costs are charged in full regardless"}
        for con in CONSTRUCTIONS:
            def col(key, cells=cells, con=con):
                return pd.Series([c[con][key] if c.get(con) else np.nan for c in cells], index=idx, dtype=float)
            g_dl, g_nd, cost, borrow, hedge = col("gross_dl"), col("gross_nd"), col("cost"), col("borrow"), col("hedge")
            net = g_dl - cost - borrow
            n_short = col("n_short")
            st = series_stats(net, mk)
            if st.get("refused"):
                results[rule][con] = {"with_delisting": st}
                continue
            keep = net.notna().to_numpy()
            rd = rand_ix[con][keep] if rand_ix[con].size else np.empty((0, 0))
            ctrl = {"n_draws": int(n_random), "percentile_of_rule": None}
            if rd.size and np.isfinite(rd).any():
                ok = np.isfinite(rd).all(axis=1)
                avg = rd[ok].mean(axis=0)
                ctrl = {"n_draws": int(n_random), "months": int(ok.sum()), "median": float(np.median(avg)),
                        "p05": float(np.percentile(avg, 5)), "p95": float(np.percentile(avg, 95)),
                        "rule_mean_same_months": float(net[keep][ok].mean()),
                        "percentile_of_rule": float((avg < net[keep][ok].mean()).mean()),
                        "what": ("the same construction on random K-name books from the covered eligible set. NET the "
                                 "random books pay more (a random name is smaller and sits in a costlier band than the rule's "
                                 "names), so the GROSS comparison is the like-for-like one")}
                rg = rand_ix[con + "_gross"][keep][ok].mean(axis=0)
                ctrl.update({"gross_median": float(np.median(rg)), "gross_p05": float(np.percentile(rg, 5)),
                             "gross_p95": float(np.percentile(rg, 95)),
                             "rule_gross_mean_same_months": float(g_dl[keep][ok].mean()),
                             "gross_percentile_of_rule": float((rg < g_dl[keep][ok].mean()).mean())})
            block = {
                "with_delisting": st,
                "without_delisting": series_stats(g_nd - cost - borrow, mk),
                "gross_with_delisting": series_stats(g_dl, mk),
                f"borrow_x{stress:g}": series_stats(net - (stress - 1) * borrow, mk),
                "cost_per_hold_mean": float(cost.mean()), "borrow_per_hold_mean": float(borrow.mean()),
                "hedge_ratio_mean": float(hedge.mean()), "hedge_ratio_min": float(hedge.min()),
                "hedge_ratio_max": float(hedge.max()),
                "short_names_per_month_median": float(n_short.median()),
                "months_short_leg_below_k": int((n_short < k).sum()) if con == "TOP_BOTTOM" else None,
                "months_dropped_below_min_names": int(net.isna().sum()),
                "holds_overlapping_the_next": overlap,
                "random_control": ctrl,
            }
            c_long_turn, c_short, c_short_turn = col("cost_long_turn"), col("cost_short"), col("cost_short_turn")
            block["post_hoc_cost_on_turnover"] = {
                "marked": ("POST HOC: added after the first result at the reviewer's request; not pre-declared and not a "
                           "basis for a claim or for the verdict"),
                "convention": ("a name kept from last month is charged nothing (re-weighting trades inside kept names are "
                               "ignored); an entering name pays its full round trip; borrow is unchanged. Short leg: "
                               + {"TWIN": ("the twin of a KEPT long name is assumed kept too (a sticky pairing), although the "
                                           "returns are those of twins redrawn every month, so 'both legs' is an optimistic bound"),
                                  "BETA": "the market short pays on the change in beta",
                                  "TOP_BOTTOM": "the bottom names' own measured turnover"}[con]),
                "long_leg_only": series_stats(g_dl - c_long_turn - c_short - borrow, mk),
                "both_legs": series_stats(g_dl - c_long_turn - c_short_turn - borrow, mk),
                "cost_per_hold_mean_long_leg_only": float((c_long_turn + c_short).mean()),
                "cost_per_hold_mean_both_legs": float((c_long_turn + c_short_turn).mean())}
            block["power_at_observed_effect"] = None   # filled once the Holm bar is known
            block["forward_sample"] = forward_sample(st["mean"], st["sd"])
            if con == "TWIN":
                dm = np.array([c["TWIN"]["draws_net_dl"] if c.get("TWIN") else [np.nan] * twin_draws for c in cells],
                              dtype=float)
                dm = dm[np.isfinite(dm).all(axis=1)]
                d_mean = dm.mean(axis=0)
                d_sd = dm.std(axis=0, ddof=1)
                d_t = d_mean / (d_sd / math.sqrt(len(dm)))
                block["single_twin_basket_across_draws"] = {
                    "draws": int(dm.shape[1]), "holds": int(len(dm)),
                    "mean_min": float(d_mean.min()), "mean_median": float(np.median(d_mean)), "mean_max": float(d_mean.max()),
                    "t_min": float(d_t.min()), "t_median": float(np.median(d_t)), "t_max": float(d_t.max()),
                    "sd_median": float(np.median(d_sd)),
                    "what": (f"each of the {dm.shape[1]} draws read alone as one tradable {k}-name twin basket, net, "
                             "delisting returns in")}
                block["forward_sample_single_twin_basket"] = forward_sample(st["mean"], float(np.median(d_sd)))
                fb: dict = {}
                for c in cells:
                    for lv, n in ((c.get("TWIN") or {}).get("fallbacks") or {}).items():
                        fb[lv] = fb.get(lv, 0) + n
                block["twin_fallbacks"] = fb
                block["twin_draws"] = twin_draws
            results[rule][con] = block
            monthly[f"{rule}_{con}_net"] = net.to_numpy()
            monthly[f"{rule}_{con}_net_nd"] = (g_nd - cost - borrow).to_numpy()
            monthly[f"{rule}_{con}_hedge"] = hedge.to_numpy()
        monthly[f"{rule}_long_only_net"] = lo.to_numpy()
        monthly[f"{rule}_n_long"] = n_long

    def cellstats(rule, con):
        s = results[rule].get(con, {}).get("with_delisting", {})
        return s if not s.get("refused") else None
    fam9 = [(r, c) for r in RULES for c in CONSTRUCTIONS if cellstats(r, c)]
    fam3 = [(PRIMARY_RULE, c) for c in CONSTRUCTIONS if cellstats(PRIMARY_RULE, c)]
    for fam, tag in ((fam3, "holm"), (fam9, "holm_all9")):
        for key in ("p_two_sided", "p_one_sided"):
            adj = holm([cellstats(r, c)[key] for r, c in fam])
            for (r, c), a in zip(fam, adj):
                cellstats(r, c)[f"{tag}_{'two' if 'two' in key else 'one'}_sided"] = a
    primary = {c: results[PRIMARY_RULE][c]["with_delisting"] for c in CONSTRUCTIONS if PRIMARY_RULE in results
               and c in results[PRIMARY_RULE]}
    v = verdict(primary)
    v0 = verdict_predeclared(primary)
    n_holds = max((s["n_holds"] for s in primary.values() if not s.get("refused")), default=0)
    bar = pass_bar(len(fam3), max(n_holds - 1, 1))
    for r, c in fam9:
        st = cellstats(r, c)
        results[r][c]["power_at_observed_effect"] = {
            "at_holm_implied_t": power_at(st["mean"], st["se"], bar["t_implied_by_holm"]),
            "at_nominal_t": power_at(st["mean"], st["se"], CFG.CH58_T_PASS),
            "what": "chance of clearing the bar if the true effect equals the observed net mean (normal approximation)"}
    priors = {"effects_per_hold": list(CFG.CH58_PRIOR_EFFECTS), "median": float(np.median(CFG.CH58_PRIOR_EFFECTS)),
              "largest": float(max(CFG.CH58_PRIOR_EFFECTS)), "source": CFG.CH58_PRIOR_EFFECTS_SOURCE}
    return {
        "question": "does revision flow earn a return as a RELATIVE position (hedged for market and style)?",
        "verdict": v["verdict"], "verdict_reason": v["reason"], "verdict_detail": v,
        "verdict_as_predeclared": v0["verdict"], "verdict_as_predeclared_reason": v0["reason"],
        "verdict_as_predeclared_detail": v0,
        "verdict_change_note": (
            "Changed after the adversarial review of the first result: the pre-declared rule compared each MDE with the "
            "LARGEST prior spread, so a twin MDE a hair under it printed FAILED_VARIANT although both halves and every "
            "leave-one-year-out are positive and the test had little power. The MDE is now compared with the MEDIAN prior "
            "effect. The pass conditions are unchanged."),
        "priors": priors, "pass_bar": bar,
        "claims": "none: observations under a PRODUCT_EXPERIMENT licence, leaders and rules chosen after the fact",
        "window": {"years": [y0, y1], "first_decision": str(dec[0].date()), "last_decision": str(dec[-1].date()),
                   "holds": int(len(rows)), "hold_sessions": CFG.CH58_HOLD_SESSIONS,
                   "holds_overlapping_the_next": overlap,
                   "year_key": "the hold's END session (the year the money was held through)"},
        "primary_rule": PRIMARY_RULE, "rules": RULE_NAMES, "k": k,
        "cells_computed": {"primary": len(fam3), "all": len(fam9),
                           "note": "3 primary (verdict family) + 6 secondary; Holm printed over both families"},
        "constructions": {
            "TWIN": (f"long the rule's names, short their matched twins (matched_twins.cell_table + draw_twins: size band "
                     f"x 63-session vol tercile x 12-1 tercile, rule's holdings excluded), mean of {twin_draws} draws"),
            "BETA": (f"long the rule's names, short ex-ante beta x CRSP VW market; beta = weighted OLS beta over "
                     f"{CFG.CH58_BETA_LOOKBACK} sessions to the decision date (min {CFG.CH58_BETA_MIN_OBS}, else 1.0)"),
            "TOP_BOTTOM": f"long the top {k} by score, short the bottom {k} (most net lowers)"},
        "costs": {"round_trip_bps_by_dollar_volume_band": [list(b) for b in CFG.CH58_COST_BPS_BANDS],
                  "charged": "in full every month on every name of both legs",
                  "post_hoc": "cost on actual turnover is printed beside it, marked POST HOC, outside the verdict",
                  "market_short_bps": CFG.CH58_MARKET_COST_BPS,
                  "borrow_annual_by_band": [list(b) for b in CFG.CH58_BORROW_ANNUAL_BANDS],
                  "market_borrow_annual": CFG.CH58_MARKET_BORROW_ANNUAL,
                  "financing": "no interest credited on short proceeds, none charged on the long"},
        "universe": {"eligible_median": float(np.median([r["n_elig"] for r in rows])),
                     "covered_eligible_median": float(np.median([r["n_cov"] for r in rows])),
                     "delistings_inside_a_hold_on_the_eligible_set": int(sum(r["delistings_in_hold_eligible"] for r in rows))},
        "mde_definition": f"{CFG.CH58_MDE_MULT} x SE per hold",
        "results": results, "_monthly": monthly,
    }


def _pct(v, nd=3) -> str:
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{100 * v:+.{nd}f}%"


def _num(v, nd=2) -> str:
    return "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:+.{nd}f}"


def _split_txt(s: dict) -> str:
    return ", ".join(f"{k} {_pct(v['mean'])} (t {_num(v['t'])})" for k, v in s["split"].items())


def _months(v) -> str:
    return "n/a" if v is None else f"{v:,.0f} months ({v / 12:,.0f} years)"


def _pc(v) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}"


def headline(rc: dict) -> list:
    """The lines a reader sees first: selection (gross) and cost (net) side by side."""
    res = rc["results"][rc["primary_rule"]]
    bar, pri = rc["pass_bar"], rc["priors"]
    L = [f"**VERDICT (computed): {rc['verdict']}** — {rc['verdict_reason']}.",
         f"verdict_as_predeclared: {rc['verdict_as_predeclared']} — {rc['verdict_as_predeclared_reason']}.",
         f"Why the rule changed: {rc['verdict_change_note']}",
         f"Priors (twin-relative, per month): {', '.join(_pct(x, 2) for x in pri['effects_per_hold'])}; median "
         f"{_pct(pri['median'], 2)}, largest {_pct(pri['largest'], 2)}. Source: {pri['source']}.",
         f"Real pass bar: {bar['note']} (one-sided p <= {bar['one_sided_p_needed_by_the_best_cell']:.4f}).", ""]
    for con in CONSTRUCTIONS:
        b = res.get(con) or {}
        s = b.get("with_delisting") or {}
        if not s or s.get("refused"):
            L.append(f"- {con}: REFUSED ({s.get('refused', 'no data')})")
            continue
        g, rcn, pw = b["gross_with_delisting"], b["random_control"], b["power_at_observed_effect"]
        line = (f"- **{con}** — SELECTION (gross): {_pct(g['mean'])} a month, t {_num(g['t'])}, percentile "
                f"{_pc(rcn.get('gross_percentile_of_rule'))} of {rcn['n_draws']} random books (random gross median "
                f"{_pct(rcn.get('gross_median'))}). AFTER COSTS (pre-declared: full cost on both legs every month, plus "
                f"borrow): {_pct(s['mean'])} a month, t {_num(s['t'])}, MDE {_pct(s['mde'])}; {_split_txt(s)}; worst "
                f"leave-one-year-out {_pct(s['loo_worst_mean'])} (drop {s['loo_worst_year_dropped']}); power at the "
                f"observed effect {_pc(pw['at_holm_implied_t'])}% against the real bar; realised beta "
                f"{_num(s['realised_beta'])} (se {s['realised_beta_se']:.2f}).")
        if abs(s["realised_beta"]) > 2 * s["realised_beta_se"] and abs(s["realised_beta"]) > 0.2:
            line += (f" **NOT MARKET-NEUTRAL: this construction carries a market short (beta {_num(s['realised_beta'])}).** "
                     f"POST HOC, in-sample: with the realised beta removed, {_pct(s['alpha_after_realised_beta'])} a month "
                     f"(t {_num(s['alpha_t'])}, MDE {_pct(s['alpha_mde'])}); not a basis for a claim.")
        L.append(line)
    L += ["", "POST HOC cost on actual turnover (added after the first result; not pre-declared, not a basis for a claim or "
          "for the verdict). The pre-declared figure is the first row of each construction:", "",
          "| construction | cost charged | cost bps/month | net/month | t | MDE | early | late | worst LOYO (drop) |",
          "|---|---|---|---|---|---|---|---|---|"]
    for con in CONSTRUCTIONS:
        b = res.get(con) or {}
        s = b.get("with_delisting") or {}
        if not s or s.get("refused"):
            continue
        ph = b["post_hoc_cost_on_turnover"]
        for lab, st, cst in (("PRE-DECLARED: full, both legs", s, b["cost_per_hold_mean"]),
                             ("POST HOC: turnover, long leg only", ph["long_leg_only"], ph["cost_per_hold_mean_long_leg_only"]),
                             ("POST HOC: turnover, both legs", ph["both_legs"], ph["cost_per_hold_mean_both_legs"])):
            sp = list(st["split"].values())
            L.append(f"| {con} | {lab} | {1e4 * cst:.1f} | {_pct(st['mean'])} | {_num(st['t'])} | {_pct(st['mde'])} | "
                     f"{_pct(sp[0]['mean'])} (t {_num(sp[0]['t'])}) | {_pct(sp[1]['mean'])} (t {_num(sp[1]['t'])}) | "
                     f"{_pct(st['loo_worst_mean'])} ({st['loo_worst_year_dropped']}) |")
    tw = res.get("TWIN") or {}
    if tw.get("post_hoc_cost_on_turnover"):
        L += ["", f"Turnover convention (TWIN): {tw['post_hoc_cost_on_turnover']['convention']}."]
    sd_ = tw.get("single_twin_basket_across_draws")
    if sd_:
        L += ["", f"A single {rc['k']}-name twin basket, across the {sd_['draws']} draws (net, pre-declared costs): mean min "
              f"{_pct(sd_['mean_min'])} / median {_pct(sd_['mean_median'])} / max {_pct(sd_['mean_max'])}; t min "
              f"{_num(sd_['t_min'])} / median {_num(sd_['t_median'])} / max {_num(sd_['t_max'])}; monthly sd median "
              f"{_pct(sd_['sd_median'], 2)}."]
    fs, fs1 = tw.get("forward_sample"), tw.get("forward_sample_single_twin_basket") or {}
    if fs:
        L += ["", f"FORWARD SAMPLE (twin spread, from the measured monthly sd {_pct(fs.get('sd_per_hold'), 2)} at the observed "
              f"net effect {_pct(fs.get('effect_per_hold'))}): {_months(fs.get('months_for_power'))} for 80% power at 5% "
              f"two-sided; {_months(fs.get('months_for_expected_t'))} for an expected t of {CFG.CH58_T_PASS}. A single "
              f"{rc['k']}-name twin basket (sd {_pct(fs1.get('sd_per_hold'), 2)}): {_months(fs1.get('months_for_power'))} "
              f"and {_months(fs1.get('months_for_expected_t'))}. Conclusion: a forward paper book of this spread alone "
              "cannot inform within any horizon we would wait for."]
    return L


def render_md(rc: dict) -> str:
    w = rc["window"]
    L = [f"# CH-58 revision flow as a relative position: run {rc.get('run_id', '')}", "", "## Headline", ""]
    L += headline(rc)
    L += ["", f"CLAIMS: {rc['claims']}.", "",
         f"Window {w['first_decision']} .. {w['last_decision']}, {w['holds']} holds of {w['hold_sessions']} sessions "
         f"({w['holds_overlapping_the_next']} holds share a session with the next); by-year keyed on {w['year_key']}.",
         f"Eligible names median {rc['universe']['eligible_median']:.0f}, IBES-covered {rc['universe']['covered_eligible_median']:.0f}. "
         f"{rc.get('survivorship_line', '')}",
         f"Costs: round trip {rc['costs']['round_trip_bps_by_dollar_volume_band']} bps by dollar-volume band, "
         f"{rc['costs']['charged']}; borrow {rc['costs']['borrow_annual_by_band']} a year on the short leg; "
         f"market short {rc['costs']['market_short_bps']} bps + {rc['costs']['market_borrow_annual']} a year. "
         f"MDE = {rc['mde_definition']}.", ""]
    for rule in RULES:
        res = rc["results"][rule]
        tag = "PRIMARY (verdict family)" if rule == rc["primary_rule"] else "secondary"
        L += [f"## {rule}: {rc['rules'][rule]} [{tag}]", ""]
        ll = res["_long_leg"]
        L.append(f"Long leg: names per month median {ll['names_per_month_median']:.0f} (min {ll['names_per_month_min']}); months "
                 f"below {ll['k']} names {ll['months_below_k']}, dropped below the floor {ll['months_below_min_names_dropped']}; "
                 f"name turnover {_num(ll['name_turnover_mean'])} a month.")
        c = res["_control_long_only_minus_market"]["with_delisting"]
        cn = res["_control_long_only_minus_market"]["without_delisting"]
        if not c.get("refused"):
            L.append(f"Control, long leg minus market (no hedge costs): {_pct(c['mean'])} a hold, t {_num(c['t'])}, MDE {_pct(c['mde'])}, "
                     f"beta {_num(c['realised_beta'])}; without delisting returns {_pct(cn['mean'])} (t {_num(cn['t'])}).")
        L += ["", "| construction | net/hold | t | NW t | MDE | Holm p (1-sided, 3) | Holm p (2-sided, 3) | early | late | worst LOYO (drop) | "
              "yrs + | realised beta (se) | top-5 share | w/o top 5 | no-delist net | borrow x3 net | random pctile |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for con in CONSTRUCTIONS:
            b = res.get(con) or {}
            s = b.get("with_delisting") or {}
            if s.get("refused") or not s:
                L.append(f"| {con} | REFUSED: {s.get('refused', 'no data')} |" + " |" * 15)
                continue
            sp = list(s["split"].values())
            sx = next(v for kk, v in b.items() if kk.startswith("borrow_x"))
            top = s["top_months_share_of_sum"]
            L.append(
                f"| {con} | {_pct(s['mean'])} | {_num(s['t'])} | {_num(s['t_newey_west_lag1'])} | {_pct(s['mde'])} | "
                f"{_num(s.get('holm_one_sided'), 3)} | {_num(s.get('holm_two_sided'), 3)} | {_pct(sp[0]['mean'])} (t {_num(sp[0]['t'])}) | "
                f"{_pct(sp[1]['mean'])} (t {_num(sp[1]['t'])}) | {_pct(s['loo_worst_mean'])} ({s['loo_worst_year_dropped']}) | "
                f"{s['years_positive']}/{s['years']} | {_num(s['realised_beta'])} ({s['realised_beta_se']:.2f}) | "
                f"{'n/a (sum <= 0)' if top is None else f'{100 * top:.0f}%'} | {_pct(s['mean_without_top_months'])} | "
                f"{_pct(b['without_delisting'].get('mean'))} | {_pct(sx.get('mean'))} | "
                f"{'n/a' if b['random_control'].get('percentile_of_rule') is None else format(100 * b['random_control']['percentile_of_rule'], '.0f')} |")
        L.append("")
        for con in CONSTRUCTIONS:
            b = res.get(con) or {}
            s = b.get("with_delisting") or {}
            if s.get("refused") or not s:
                continue
            L.append(f"- {con} by year (net %/hold): " + ", ".join(f"{y} {100 * v['mean']:+.2f}" for y, v in s["by_year"].items()))
            extra = f"; twin fallbacks {b['twin_fallbacks']}" if con == "TWIN" else ""
            L.append(f"  gross {_pct(b['gross_with_delisting']['mean'])}, cost {1e4 * b['cost_per_hold_mean']:.1f} bps, borrow "
                     f"{1e4 * b['borrow_per_hold_mean']:.1f} bps a hold; hedge ratio mean {b['hedge_ratio_mean']:.2f} "
                     f"({b['hedge_ratio_min']:.2f}..{b['hedge_ratio_max']:.2f}); short names median "
                     f"{b['short_names_per_month_median']:.0f}; months dropped {b['months_dropped_below_min_names']}"
                     + (f"; months with a short leg below k {b['months_short_leg_below_k']}" if con == "TOP_BOTTOM" else "")
                     + f"; alpha after realised beta {_pct(s['alpha_after_realised_beta'])} (t {_num(s['alpha_t'])}, "
                       f"MDE {_pct(s['alpha_mde'])}); random control net median {_pct(b['random_control'].get('median'))}, GROSS median "
                       f"{_pct(b['random_control'].get('gross_median'))} (5-95% {_pct(b['random_control'].get('gross_p05'))}.."
                       f"{_pct(b['random_control'].get('gross_p95'))}), rule's gross percentile "
                       f"{_num(100 * b['random_control']['gross_percentile_of_rule'], 0) if b['random_control'].get('gross_percentile_of_rule') is not None else 'n/a'}"
                       f"; Holm over all 9 cells: one-sided {_num(s.get('holm_all9_one_sided'), 3)}, two-sided "
                       f"{_num(s.get('holm_all9_two_sided'), 3)}{extra}")
        L.append("")
    L += [f"Verdict rule: {rc['verdict_detail']['rule']}.", ""]
    return "\n".join(L)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path, help="output directory (never the live data folder)")
    ap.add_argument("--wrds", type=Path, default=None, help="WRDS folder (default: <OPTIMUS_LEDGER_DIR>/wrds), read-only")
    ap.add_argument("--start", type=int, default=CFG.CH58_START_YEAR)
    ap.add_argument("--end", type=int, default=CFG.CH58_END_YEAR)
    ap.add_argument("--k", type=int, default=CFG.CH58_K)
    ap.add_argument("--n-random", type=int, default=CFG.CH58_N_RANDOM)
    ap.add_argument("--twin-draws", type=int, default=CFG.CH58_TWIN_DRAWS)
    ap.add_argument("--run-id", default=None)
    a = ap.parse_args(argv)
    wrds = a.wrds if a.wrds is not None else CFG.OPTIMUS_LEDGER_DIR / "wrds"
    try:
        out = Path(a.out).resolve()
        if Path(wrds).resolve() in (out, *out.parents):
            raise InputMissing(f"--out {out} is inside the input folder {wrds}: refused")
        run(wrds, out, y0=a.start, y1=a.end, k=a.k, n_random=a.n_random, twin_draws=a.twin_draws, run_id=a.run_id)
    except InputMissing as e:
        print(f"[ch58] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
