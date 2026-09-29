"""Contest books compared on past seasons: the desk's rule vs the reviewer's book (2026-09-29).

    python -m scripts.contest_book_compare                 # every season 2019-2026, all pools
    python -m scripts.contest_book_compare --draws 2000

Answers REVIEW_2026-09-29_CONTEST_DESK findings 2 and 6 and the owner's brief of 2026-09-29:

1. **Survivorship, measured not asserted.** The desk's US event pool is SEC 8-K item 2.02, which
   covers 47 of 1,784 delisted names. IBES actuals (`wrds/bulk/ibes__actu_epsus.parquet`,
   announcement date AND time, ET) cover about half of them. The same book is run on:
     SEC8K         the desk's survivor pool
     IBES_ALL      IBES stamps, dead names included
     IBES_LIVING   IBES stamps, names alive at the end of the bars only
   IBES_ALL minus IBES_LIVING is the survivorship effect inside one source.
2. **Earnings drift vs high-volatility beta.** VOLMATCH_CONTROL holds, in each slot the desk
   rule fills, a liquid operating company with NO report within 5 sessions and the nearest
   63-session volatility, for the same sessions. CURRENT minus VOLMATCH_CONTROL is what the
   print itself added.
3. **The books** (US only; five slots at 20% of NAV; long only; gross never above 100%):
     CURRENT          the desk rule: the five reporting names with the largest trailing mean
                      |earnings reaction|; empty slots stay in cash
     CURRENT_FILL     the same with empty slots filled by the most volatile liquid operating
                      companies (the reviewer's "no cash" rule alone)
     REVIEWER         ranked by the expected earnings move = mean percentile rank of trailing
                      |reaction| and nn_lab's walk-forward size-of-move forecast
                      (`ridgeabs_score_5`, 2020-01 onward; trailing |reaction| alone before);
                      empty slots filled with the most volatile names. The option-implied
                      move is NOT used: no history of it exists on disk (stated).
     VOLMATCH_CONTROL see 2
   Buy at the open of the last session before the print, sell at the open of the reaction
   session (an untimed print: the open after the two sessions around it). Fillers are held
   open to open and re-chosen daily; a filler kept is not traded. Costs 0 / 10 / 25 bps a side.
4. **Probabilities per season, three ways, never pooled silently:**
     REALISED   the actual path (one number)
     NULL       zero direction skill: one random sign a day on the book AND the benchmark
                (the rotation sim's convention; keeps magnitude, removes drift)
     BOOT       the season's own daily (book, benchmark) pairs resampled in 5-day blocks:
                keeps that season's drift and volatility
   plus the same NULL/BOOT pooled by era (Oct seasons 2019-25; all seasons 2024-26).

UTILITY, declared: contest rank of about 2,700 teams, top 10 wanted -- a deliberately
RISK-SEEKING utility (maximise P(relative > +40%); a loss has no floor below "not top 10").
PRODUCT_EXPERIMENT; family of one. Nothing here is evidence of skill. No network, $0.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import contest_calendar as cc   # noqa: E402
from scripts import contest_desk as desk     # noqa: E402

OUT = cc.CONTEST / "compare"
IBES_PATH = cc.OPT / "wrds" / "bulk" / "ibes__actu_epsus.parquet"
OOS_PATH = cc.OPT / "nn_lab" / "walkforward" / "oos_wf_20260929_post_review.parquet"
THRESH = (0.20, 0.40, 0.60)
LOSS = -0.20
COSTS_BPS = (0.0, 10.0, 25.0)
SEED = 20261012
K = desk.K_SLOTS
W = desk.WEIGHT
QUIET = 5                 # a control name has no report within this many sessions
BLOCK = 5
BOOKS = ("CURRENT", "CURRENT_FILL", "REVIEWER", "VOLMATCH_CONTROL")
UTILITY = ("contest rank of ~2,700, top 10 wanted: RISK-SEEKING by declared choice "
           "(maximise P(relative > +40%); the depth of a loss below 'not top 10' is not penalised)")


# ───────────────────────────── event pools ─────────────────────────────

def ibes_stamps(path: Path = IBES_PATH) -> pd.DataFrame:
    """US quarterly EPS announcements from IBES actuals: symbol, ts_utc, source.

    anntims is New York time (checked 2026-09-29: median -5 min vs the 8-K acceptance time on
    67,786 matched reports). A time before 06:00 ET is an overnight processing stamp, not a
    release time, so it is written as local midnight = UNKNOWN (held two sessions)."""
    a = pd.read_parquet(path, columns=["oftic", "measure", "pdicity", "anndats", "anntims", "usfirm"])
    a = a[(a.pdicity == "QTR") & (a.measure == "EPS") & (a.usfirm == 1) & a.oftic.notna()]
    a["anndats"] = pd.to_datetime(a.anndats, errors="coerce")
    a = a[a.anndats >= pd.Timestamp("2015-06-01")].dropna(subset=["anndats"])
    a = a.drop_duplicates(["oftic", "anndats"])
    tt = pd.to_timedelta(a.anntims.fillna("00:00:00"), errors="coerce").fillna(pd.Timedelta(0))
    tt = tt.where(tt >= pd.Timedelta(hours=6), pd.Timedelta(0))
    ts = (a.anndats + tt).dt.tz_localize("America/New_York", ambiguous="NaT",
                                          nonexistent="shift_forward").dt.tz_convert("UTC")
    out = pd.DataFrame({"symbol": a.oftic.astype(str).str.upper().to_numpy(), "ts_utc": ts.to_numpy(),
                        "source": "ibes_actu"})
    return out.dropna(subset=["ts_utc"]).reset_index(drop=True)


def dead_symbols(panel: desk.Panel, *, gap_days: int = 30) -> set:
    """Names whose last bar is more than `gap_days` calendar days before the panel's end."""
    live = np.isfinite(panel.close)
    last_i = np.where(live.any(axis=0), live.shape[0] - 1 - np.argmax(live[::-1], axis=0), -1)
    end = panel.dates[-1]
    out = set()
    for j, li in enumerate(last_i):
        if li >= 0 and (end - panel.dates[li]).days > gap_days:
            out.add(str(panel.syms[j]))
    return out


def pools(panel: desk.Panel, *, sec: Optional[pd.DataFrame] = None,
          ibes: Optional[pd.DataFrame] = None) -> dict[str, pd.DataFrame]:
    sec = sec if sec is not None else cc.us_8k_events()
    ibes = ibes if ibes is not None else ibes_stamps()
    dead = dead_symbols(panel)
    return {"SEC8K": sec, "IBES_ALL": ibes, "IBES_LIVING": ibes[~ibes.symbol.isin(dead)]}


# ───────────────────────────── the market ─────────────────────────────

@dataclass
class Mkt:
    r: np.ndarray            # open t -> open t+1 (delisting: close t / open t), 0 where not held-able
    last: np.ndarray         # True where t is the name's last session with an open
    bench: np.ndarray        # benchmark open -> open
    liq: np.ndarray          # at t: dv63 of t-1 >= floor and price >= $1 (known before the open)
    sig: np.ndarray          # sig63 of t-1
    n_faults: int


def market(panel: desk.Panel, bench: str = "ACWI") -> Mkt:
    O = panel.open.astype("float64")
    C = panel.close.astype("float64")
    nxt = np.vstack([O[1:], np.full((1, O.shape[1]), np.nan)])
    r = nxt / O - 1.0
    last = np.isfinite(O) & ~np.isfinite(nxt)
    r = np.where(last, C / O - 1.0, r)                     # delisted: exit at the last close
    bad = np.isfinite(r) & ((r > 2.0) | (r < -0.8))        # splits / data faults
    r = np.where(bad, 0.0, r)
    r = np.nan_to_num(r, nan=0.0)
    b = pd.Series(panel.open[:, panel.col[bench]]).ffill().to_numpy(dtype="float64")
    bench_r = np.nan_to_num(np.append(b[1:] / b[:-1] - 1.0, 0.0))
    prev = lambda a: np.vstack([np.full((1, a.shape[1]), np.nan), a[:-1]])   # noqa: E731
    px = prev(pd.DataFrame(C).ffill(limit=5).to_numpy())
    liq = (np.nan_to_num(prev(panel.dv63)) >= cc.LIQ_FLOOR_USD) & (np.nan_to_num(px) >= desk.MIN_PRICE_USD) \
        & np.isfinite(O)
    return Mkt(r, last, bench_r, liq, prev(panel.sig63.astype("float64")), int(bad.sum()))


def size_forecast_matrix(panel: desk.Panel, path: Path = OOS_PATH) -> Optional[np.ndarray]:
    """nn_lab's walk-forward ridge |5-session move| forecast, as of the grid date <= t-1."""
    if not Path(path).exists():
        return None
    d = pd.read_parquet(path, columns=["date", "symbol", "ridgeabs_score_5"])
    d["date"] = pd.to_datetime(d.date)
    w = d.pivot_table(index="date", columns="symbol", values="ridgeabs_score_5")
    w = w.reindex(columns=panel.syms)
    idx = panel.dates.searchsorted(w.index, side="right")         # usable from the NEXT session
    out = np.full(panel.close.shape, np.nan)
    for k, i in enumerate(idx):
        if i < len(panel.dates):
            out[i] = w.iloc[k].to_numpy()
    return pd.DataFrame(out).ffill(limit=10).to_numpy()


# ───────────────────────────── the books ─────────────────────────────

def _rank_pct(x: np.ndarray) -> np.ndarray:
    s = pd.Series(x)
    return s.rank(pct=True).to_numpy()


def season_path(days: np.ndarray, ev: pd.DataFrame, m: Mkt, book: str, *,
                size: Optional[np.ndarray] = None, reporting: Optional[np.ndarray] = None,
                operating: Optional[np.ndarray] = None) -> dict:
    """One season, one book: daily book return, turnover (weight traded), bench return.

    `ev` needs pre_i, react_i, ci, trail_abs, on_cadence. Positions enter at the open of pre_i
    and leave at the open of react_i. At most K slots of W each: gross <= 100% by construction."""
    by_pre = {int(i): g for i, g in ev.groupby("pre_i")} if len(ev) else {}
    held: list[dict] = []
    fillers: set = set()
    t0, tN = int(days[0]), int(days[-1])
    rows, names = [], []
    for t in days:
        t = int(t)
        traded = 0.0
        # exits at this open (event holds that end here; delisted names)
        keep = []
        for p in held:
            if p["exit"] <= t:
                traded += W
            else:
                keep.append(p)
        held = keep
        free = K - len(held)
        held_j = {p["j"] for p in held}
        g = by_pre.get(t)
        if free > 0 and g is not None:
            ok = (g.on_cadence.to_numpy(bool) & g.trail_abs.notna().to_numpy()
                  & m.liq[t, g.ci.to_numpy(int)] & ~g.ci.isin(held_j).to_numpy())
            gg = g[ok].drop_duplicates("ci")
            if len(gg):
                if book == "REVIEWER" and size is not None:
                    a = _rank_pct(gg.trail_abs.to_numpy())
                    s = size[t, gg.ci.to_numpy(int)]
                    b = _rank_pct(s)
                    key = np.where(np.isfinite(s), (a + b) / 2.0, a)
                else:
                    key = gg.trail_abs.to_numpy()
                pick = gg.iloc[np.argsort(-key, kind="stable")[:free]]
                for rr in pick.itertuples():
                    j = int(rr.ci)
                    ex = int(rr.react_i) if pd.notna(rr.react_i) else t + 1
                    if book == "VOLMATCH_CONTROL":
                        j = _control(t, j, m, reporting, operating, held_j)
                        if j < 0:
                            continue
                    held.append({"j": j, "exit": max(ex, t + 1), "kind": "event"})
                    held_j.add(j)
                    traded += W
                    names.append(str(j))
        # fillers: the most volatile liquid operating companies not already held
        new_f: set = set()
        if book in ("CURRENT_FILL", "REVIEWER"):
            nfree = K - len(held)
            if nfree > 0:
                elig = m.liq[t] & np.isfinite(m.sig[t])
                if operating is not None:
                    elig &= operating
                elig[list(held_j)] = False
                cand = np.flatnonzero(elig)
                if len(cand):
                    new_f = set(cand[np.argsort(-m.sig[t, cand], kind="stable")[:nfree]].tolist())
        traded += W * len(new_f.symmetric_difference(fillers))
        fillers = new_f
        day = sum(W * m.r[t, p["j"]] for p in held) + sum(W * m.r[t, j] for j in fillers)
        gross = W * (len(held) + len(fillers))
        # a delisted name leaves at its last close
        for p in held:
            if m.last[t, p["j"]]:
                p["exit"] = t + 1
        rows.append({"t": t, "book": day, "bench": float(m.bench[t]), "traded": traded, "gross": gross,
                     "n_event": sum(1 for p in held if p["kind"] == "event"), "n_fill": len(fillers)})
    # everything still held is sold at the open after the window's last session
    if rows:
        rows[-1]["traded"] += W * (len(held) + len(fillers))
    df = pd.DataFrame(rows)
    return {"daily": df, "max_gross": float(df.gross.max()) if len(df) else 0.0}


def _control(t: int, j: int, m: Mkt, reporting: Optional[np.ndarray], operating: Optional[np.ndarray],
             taken: set) -> int:
    """The liquid operating company with no report within QUIET sessions and the nearest sig63."""
    elig = m.liq[t] & np.isfinite(m.sig[t])
    if reporting is not None:
        elig &= ~reporting[t]
    if operating is not None:
        elig &= operating
    elig[list(taken)] = False
    elig[j] = False
    cand = np.flatnonzero(elig)
    if not len(cand) or not np.isfinite(m.sig[t, j]):
        return -1
    return int(cand[np.argmin(np.abs(m.sig[t, cand] - m.sig[t, j]))])


def reporting_matrix(ev: pd.DataFrame, shape: tuple) -> np.ndarray:
    rep = np.zeros(shape, dtype=bool)
    e = ev[ev.pre_i.notna()]
    for pi, ri, ci in zip(e.pre_i.astype(int), e.react_i.fillna(e.pre_i + 1).astype(int), e.ci.astype(int)):
        rep[max(0, pi - QUIET): min(shape[0], ri + QUIET + 1), ci] = True
    return rep


def operating_mask(ev: pd.DataFrame, n_cols: int) -> np.ndarray:
    """A name that has reported at least 3 times in the pool is an operating company (not an
    ETF/ETN: those file no earnings), so it may be a filler or a control."""
    cnt = ev.groupby("ci").size()
    out = np.zeros(n_cols, dtype=bool)
    out[cnt[cnt >= 3].index.astype(int)] = True
    return out


# ───────────────────────────── probabilities ─────────────────────────────

def rel_paths(book: np.ndarray, bench: np.ndarray, cost: np.ndarray) -> np.ndarray:
    """Relative result (book cumulative return minus benchmark cumulative return) per row."""
    nav = np.prod(np.maximum(1.0 + book - cost, 0.0), axis=-1)
    bn = np.prod(1.0 + bench, axis=-1)
    return nav - bn


def probs(rel: np.ndarray) -> dict:
    rel = np.asarray(rel, dtype=float)
    d = {f"P>+{int(t * 100)}%": round(float((rel > t).mean()), 4) for t in THRESH}
    d[f"P<{int(LOSS * 100)}%"] = round(float((rel < LOSS).mean()), 4)
    d["median"] = round(float(np.median(rel)), 4)
    return d


def null_draws(book: np.ndarray, bench: np.ndarray, cost: np.ndarray, rng, n: int) -> np.ndarray:
    s = rng.choice([-1.0, 1.0], size=(n, len(book)))
    return rel_paths(s * book[None, :], s * bench[None, :], np.broadcast_to(cost, (n, len(book))))


def boot_draws(book: np.ndarray, bench: np.ndarray, cost: np.ndarray, rng, n: int, length: int,
               block: int = BLOCK) -> np.ndarray:
    """Moving-block bootstrap of (book, bench, cost) day triples: keeps drift and co-movement."""
    T = len(book)
    if T == 0:
        return np.zeros(n)
    nb = int(np.ceil(length / block))
    starts = rng.integers(0, max(1, T - block + 1), size=(n, nb))
    idx = (starts[:, :, None] + np.arange(min(block, T))[None, None, :]).reshape(n, -1)[:, :length]
    idx = np.minimum(idx, T - 1)
    return rel_paths(book[idx], bench[idx], cost[idx])


# ───────────────────────────── the run ─────────────────────────────

def run(draws: int = 4000, from_year: int = 2019) -> dict:
    from scripts import contest_rotation_sim as rsim           # noqa: PLC0415
    long = cc.load_bars_usd([], include_us=True)
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    long = long[long.date >= pd.Timestamp("2016-01-01")].drop_duplicates(["symbol", "date"])
    panel = desk.panel_from_long(long)
    del long
    m = market(panel)
    size = size_forecast_matrix(panel)
    ib = ibes_stamps()
    ibes_max = pd.Timestamp(ib.ts_utc.max()).tz_convert(None).normalize()
    P = pools(panel, ibes=ib)
    dead = dead_symbols(panel)
    rng = np.random.default_rng(SEED)
    wins = rsim.windows(panel, from_year)
    res: dict = {"utility": UTILITY, "licence": desk.LICENCE, "draws": draws, "seed": SEED,
                 "benchmark": "ACWI (proxy for WLS; stated)", "costs_bps_per_side": list(COSTS_BPS),
                 "panel": {"days": int(len(panel.dates)), "symbols": int(len(panel.syms)),
                           "first": str(panel.dates[0].date()), "last": str(panel.dates[-1].date()),
                           "dead_symbols": len(dead), "return_faults_zeroed": m.n_faults},
                 "size_forecast": str(OOS_PATH.name) if size is not None else None,
                 "implied_move": "NOT USED: no history of option-implied moves on disk "
                                 "(event_panel_cache.options_implied_move is empty; the desk's "
                                 "snapshot file starts with the live desk)",
                 "ibes_last_announcement": str(ibes_max.date()), "pools": {}, "seasons": []}
    for pname, raw in P.items():
        ev = desk.build_events(panel, raw)
        ev = ev[ev.market == "US"] if "market" in ev else ev
        n_dead_ev = int(ev.symbol.isin(dead).sum())
        res["pools"][pname] = {"stamps": int(len(raw)), "events": int(len(ev)),
                               "symbols": int(ev.symbol.nunique()),
                               "dead_symbols_with_events": int(ev.loc[ev.symbol.isin(dead), "symbol"].nunique()),
                               "events_of_dead_names": n_dead_ev,
                               "timing": ev.timing.value_counts().to_dict()}
        print(pname, res["pools"][pname], flush=True)
        evs = ev[ev.pre_i.notna()].copy()
        rep = reporting_matrix(evs, panel.close.shape)
        op = operating_mask(evs, len(panel.syms))
        for wname, days in wins:
            end = panel.dates[days[-1]]
            if pname.startswith("IBES") and end + pd.Timedelta(days=3) > ibes_max:
                continue
            row = {"window": wname, "pool": pname, "start": str(panel.dates[days[0]].date()),
                   "end": str(end.date()), "books": {}}
            for book in BOOKS:
                sp = season_path(days, evs, m, book, size=size, reporting=rep, operating=op)
                d = sp["daily"]
                assert sp["max_gross"] <= 1.0 + 1e-9, "gross above 100%"
                b, bn, tr = d.book.to_numpy(), d.bench.to_numpy(), d.traded.to_numpy()
                out = {"max_gross": sp["max_gross"], "avg_event_slots": round(float(d.n_event.mean()), 2),
                       "avg_filler_slots": round(float(d.n_fill.mean()), 2)}
                for cb in COSTS_BPS:
                    cost = tr * cb / 1e4
                    key = f"{int(cb)}bps"
                    out[key] = {"realised": round(float(rel_paths(b, bn, cost)), 4),
                                "null": probs(null_draws(b, bn, cost, rng, draws)),
                                "boot": probs(boot_draws(b, bn, cost, rng, draws, len(b))),
                                "_daily": [b.round(6).tolist(), bn.round(6).tolist(), cost.round(7).tolist()]}
                row["books"][book] = out
            res["seasons"].append(row)
            r0 = row["books"]
            print(pname, wname, " ".join(f"{k}:{v['0bps']['realised']:+.3f}" for k, v in r0.items()), flush=True)
    res["pooled"] = pooled(res, rng, draws)
    return res


def pooled(res: dict, rng, draws: int) -> dict:
    """NULL and BOOT over the days of several seasons (one ex-ante distribution per era)."""
    eras = {"Oct 2019-25": lambda w: w.endswith("Oct"),
            "all 2024-26": lambda w: int(w[:4]) >= 2024,
            "all 2019-26": lambda w: True}
    out: dict = {}
    for pool in res["pools"]:
        for era, f in eras.items():
            ss = [s for s in res["seasons"] if s["pool"] == pool and f(s["window"])]
            if not ss:
                continue
            L = int(np.median([len(s["books"]["CURRENT"]["0bps"]["_daily"][0]) for s in ss]))
            for book in BOOKS:
                for cb in COSTS_BPS:
                    key = f"{int(cb)}bps"
                    trip = [np.array(s["books"][book][key]["_daily"]) for s in ss]
                    # NULL: each season's own path sign-flipped, pooled across seasons
                    nul = np.concatenate([null_draws(t[0], t[1], t[2], rng, max(1, draws // len(ss)))
                                          for t in trip])
                    # BOOT: blocks drawn within a randomly chosen season (no cross-season blocks)
                    pick = rng.integers(0, len(trip), size=draws)
                    bt = np.concatenate([boot_draws(trip[i][0], trip[i][1], trip[i][2], rng,
                                                    int((pick == i).sum()), L)
                                         for i in range(len(trip)) if (pick == i).any()])
                    real = np.array([s["books"][book][key]["realised"] for s in ss])
                    out.setdefault(pool, {}).setdefault(era, {}).setdefault(book, {})[key] = {
                        "n_seasons": len(ss), "null": probs(nul), "boot": probs(bt),
                        "realised_median": round(float(np.median(real)), 4),
                        "realised_mean": round(float(np.mean(real)), 4),
                        "realised_pos": int((real > 0).sum()),
                        "realised_gt20": int((real > 0.2).sum()), "realised_gt40": int((real > 0.4).sum()),
                        "realised_gt60": int((real > 0.6).sum()), "realised_lt_m20": int((real < -0.2).sum())}
    return out


def report(res: dict) -> str:
    L = ["# Contest books compared (receipt beside this file)", "",
         f"Utility: {res['utility']}.", f"Benchmark: {res['benchmark']}. Draws: {res['draws']}. "
         f"Implied move: {res['implied_move']}.", "",
         "## Event pools (survivorship)", "", "| pool | stamps | events | symbols | dead symbols with events | events of dead names |",
         "|---|---|---|---|---|---|"]
    for p, v in res["pools"].items():
        L.append(f"| {p} | {v['stamps']:,} | {v['events']:,} | {v['symbols']:,} | {v['dead_symbols_with_events']:,} "
                 f"| {v['events_of_dead_names']:,} |")
    L += [""]
    for pool, eras in res["pooled"].items():
        for era, books in eras.items():
            L += [f"## {pool}, {era}", "",
                  "| book | cost | seasons | realised median | realised >0 / >+20 / >+40 / >+60 / <-20 "
                  "| NULL P>+20 / +40 / +60 / <-20 | BOOT P>+20 / +40 / +60 / <-20 |",
                  "|---|---|---|---|---|---|---|"]
            for book, costs in books.items():
                for key, v in costs.items():
                    n, b = v["null"], v["boot"]
                    L.append(f"| {book} | {key} | {v['n_seasons']} | {v['realised_median']:+.1%} "
                             f"| {v['realised_pos']} / {v['realised_gt20']} / {v['realised_gt40']} / "
                             f"{v['realised_gt60']} / {v['realised_lt_m20']} "
                             f"| {n['P>+20%']:.1%} / {n['P>+40%']:.1%} / {n['P>+60%']:.1%} / {n['P<-20%']:.1%} "
                             f"| {b['P>+20%']:.1%} / {b['P>+40%']:.1%} / {b['P>+60%']:.1%} / {b['P<-20%']:.1%} |")
            L.append("")
    for pool in res["pools"]:
        L += [f"## Every season, {pool}, 10 bps a side: REALISED / NULL P>+40% / BOOT P>+40%", "",
              "| season | " + " | ".join(BOOKS) + " |", "|---|" + "---|" * len(BOOKS)]
        for s in res["seasons"]:
            if s["pool"] != pool:
                continue
            L.append(f"| {s['window']} | " + " | ".join(
                f"{s['books'][b]['10bps']['realised']:+.1%} / {s['books'][b]['10bps']['null']['P>+40%']:.1%} / "
                f"{s['books'][b]['10bps']['boot']['P>+40%']:.1%}" for b in BOOKS) + " |")
        L.append("")
    return "\n".join(L) + "\n"


def paired_effects(res: dict, cost: str = "10bps") -> dict:
    """Season-paired differences, each with its leave-one-season-out worst mean (rule 11:
    which part of the sample is the number)."""
    real = {(s["pool"], s["window"], b): v[cost]["realised"] for s in res["seasons"] for b, v in s["books"].items()}
    pairs = {
        "survivorship: IBES_ALL minus IBES_LIVING (CURRENT)": (("IBES_ALL", "CURRENT"), ("IBES_LIVING", "CURRENT")),
        "survivorship: IBES_ALL minus IBES_LIVING (REVIEWER)": (("IBES_ALL", "REVIEWER"), ("IBES_LIVING", "REVIEWER")),
        "the print: CURRENT minus VOLMATCH_CONTROL (SEC8K)": (("SEC8K", "CURRENT"), ("SEC8K", "VOLMATCH_CONTROL")),
        "the print: CURRENT minus VOLMATCH_CONTROL (IBES_ALL)": (("IBES_ALL", "CURRENT"), ("IBES_ALL", "VOLMATCH_CONTROL")),
        "ranking: REVIEWER minus CURRENT (SEC8K)": (("SEC8K", "REVIEWER"), ("SEC8K", "CURRENT")),
        "ranking: REVIEWER minus CURRENT (IBES_ALL)": (("IBES_ALL", "REVIEWER"), ("IBES_ALL", "CURRENT")),
        "no cash: CURRENT_FILL minus CURRENT (SEC8K)": (("SEC8K", "CURRENT_FILL"), ("SEC8K", "CURRENT")),
    }
    out = {}
    for name, ((pa, ba), (pb, bb)) in pairs.items():
        ws = [s["window"] for s in res["seasons"] if s["pool"] == pa]
        z = pd.Series({w: real[(pa, w, ba)] - real[(pb, w, bb)] for w in ws
                       if (pa, w, ba) in real and (pb, w, bb) in real})
        if len(z) < 3:
            continue
        loo = [float(z.drop(w).mean()) for w in z.index]
        nz = z[z != 0]
        out[name] = {"n_seasons": int(len(z)), "mean": round(float(z.mean()), 4), "median": round(float(z.median()), 4),
                     "n_positive": int((z > 0).sum()), "n_zero": int((z == 0).sum()),
                     "t_over_seasons": round(float(z.mean() / z.std(ddof=1) * np.sqrt(len(z))), 2) if z.std() > 0 else None,
                     "loo_worst_mean": round(min(loo), 4), "loo_worst_drops": str(z.index[int(np.argmin(loo))]),
                     "last_nonzero_season": str(nz.index[-1]) if len(nz) else None}
    return out


def by_season_table(res: dict, books=("CURRENT", "REVIEWER"), pool: str = "SEC8K", cost: str = "10bps") -> str:
    L = [f"### {pool}, {cost} a side: per season, REALISED and P(> +20% / > +40% / > +60% / < -20%) "
         "under NULL (zero skill) and BOOT (the season's own drift)", "",
         "| season | book | realised | NULL +20 / +40 / +60 / -20 | BOOT +20 / +40 / +60 / -20 |", "|---|---|---|---|---|"]
    for s in res["seasons"]:
        if s["pool"] != pool:
            continue
        for b in books:
            v = s["books"][b][cost]
            n, bt = v["null"], v["boot"]
            L.append(f"| {s['window']} | {b} | {v['realised']:+.1%} | {n['P>+20%']:.1%} / {n['P>+40%']:.1%} / "
                     f"{n['P>+60%']:.1%} / {n['P<-20%']:.1%} | {bt['P>+20%']:.1%} / {bt['P>+40%']:.1%} / "
                     f"{bt['P>+60%']:.1%} / {bt['P<-20%']:.1%} |")
    return "\n".join(L) + "\n"


def tables_from_receipt(path: Path) -> Path:
    """Derived tables for an existing receipt, written beside it under a NEW name."""
    res = json.loads(Path(path).read_text(encoding="utf-8"))
    eff = paired_effects(res)
    L = [f"# Derived from {Path(path).name} (the receipt is not modified)", "",
         "## Paired season effects, 10 bps a side", "",
         "| effect | seasons | mean | median | positive / zero | t | leave-one-out worst mean (drops) | last non-zero |",
         "|---|---|---|---|---|---|---|---|"]
    for k, v in eff.items():
        L.append(f"| {k} | {v['n_seasons']} | {v['mean']:+.1%} | {v['median']:+.1%} | {v['n_positive']} / {v['n_zero']} "
                 f"| {v['t_over_seasons']} | {v['loo_worst_mean']:+.1%} ({v['loo_worst_drops']}) | {v['last_nonzero_season']} |")
    L += ["", by_season_table(res, pool="SEC8K"), by_season_table(res, pool="IBES_ALL")]
    out = Path(path).with_name(Path(path).stem + "_derived.md")
    out.write_text("\n".join(L), encoding="utf-8")
    cc.write_json({"source_receipt": Path(path).name, "paired_effects_10bps": eff},
                  Path(path).with_name(Path(path).stem + "_derived.json"))
    return out


def prior_by_market(boot: int = 200, seed: int = SEED) -> dict:
    """The TRIAL-CONTEST-MAG-1 secondary prior re-measured with the corrected report timing:
    rank(|reaction|) ~ rank(trail8) + rank(sig63) over liquid on-cadence events, by market group
    and year; iid bootstrap SE (understates a date-clustered SE, as the original said). Written
    as a NEW receipt; prereg_prior_global_by_market.json is not modified."""
    long = cc.load_bars_usd([m for m in cc.MARKETS if m != "US"], include_us=True)
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    long = long[long.date >= pd.Timestamp("2016-01-01")].drop_duplicates(["symbol", "date"])
    panel = desk.panel_from_long(long)
    del long
    ev = desk.build_events(panel, desk.raw_event_stamps())
    ev = ev[ev.pre_i.notna() & ev.react_i.notna() & ev.absr.notna() & ev.trail_abs.notna() & ev.on_cadence]
    pi = ev.pre_i.astype(int).to_numpy()
    ci = ev.ci.astype(int).to_numpy()
    ev = ev.assign(dv=panel.dv63[pi, ci], sig=panel.sig63[pi, ci])
    ev = ev[(ev.dv >= cc.LIQ_FLOOR_USD) & np.isfinite(ev.sig)]
    grp = ev.market.map(lambda m: "US" if m == "US" else "EU" if m == "EU" else "IN" if m == "IN" else "ASIA")
    ev = ev.assign(group=grp.to_numpy(), year=pd.to_datetime(ev.react_date).dt.year.to_numpy())
    rng = np.random.default_rng(seed)
    rows = []
    for (g, y), d in ev.groupby(["group", "year"]):
        if len(d) < 200 or y < 2021:
            continue
        Y = d.absr.rank(pct=True).to_numpy()
        X = np.column_stack([np.ones(len(d)), d.trail_abs.rank(pct=True), d.sig.rank(pct=True)])
        b = np.linalg.lstsq(X, Y, rcond=None)[0][1]
        bs = []
        for _ in range(boot):
            i = rng.integers(0, len(d), len(d))
            bs.append(np.linalg.lstsq(X[i], Y[i], rcond=None)[0][1])
        rows.append({"group": g, "year": int(y), "n": int(len(d)), "b_vol": round(float(b), 3),
                     "se_iid_boot": round(float(np.std(bs)), 3),
                     "timing": d.timing.value_counts().to_dict()})
    return {"what": "rank(|reaction|) ~ rank(trail8) + rank(sig63), liquid on-cadence events, by group-year; "
                    "iid bootstrap SE; report timing CORRECTED (00:00 UTC stamps = UNKNOWN, two-session hold)",
            "supersedes_reading_of": "prereg_prior_global_by_market.json (not modified)", "rows": rows}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=4000)
    ap.add_argument("--from-year", type=int, default=2019)
    ap.add_argument("--tables-from", default=None, help="write derived tables for an existing receipt")
    ap.add_argument("--prior-by-market", action="store_true",
                    help="re-measure the MAG-1 secondary prior with corrected timing (new receipt)")
    a = ap.parse_args(argv)
    if a.prior_by_market:
        OUT.mkdir(parents=True, exist_ok=True)
        out = OUT / f"prior_by_market_timingfix_{cc.utc_stamp()}.json"
        cc.write_json(prior_by_market(), out)
        print("receipt:", out)
        return 0
    if a.tables_from:
        print(tables_from_receipt(Path(a.tables_from)))
        return 0
    res = run(a.draws, a.from_year)
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = f"compare_{cc.utc_stamp()}"
    res["run_id"] = run_id
    slim = json.loads(json.dumps(res, default=str))
    for s in slim["seasons"]:                 # the daily paths go to a sidecar, not the receipt
        for b in s["books"].values():
            for k in list(b):
                if isinstance(b[k], dict):
                    b[k].pop("_daily", None)
    cc.write_json(slim, OUT / f"{run_id}.json")
    daily = [{"pool": s["pool"], "window": s["window"], "book": bk, "cost": ck, "book_r": v["_daily"][0],
              "bench_r": v["_daily"][1], "cost_r": v["_daily"][2]}
             for s in res["seasons"] for bk, bv in s["books"].items() for ck, v in bv.items()
             if isinstance(v, dict) and "_daily" in v]
    pd.DataFrame(daily).to_parquet(OUT / f"{run_id}_daily.parquet", index=False)
    md = report(res)
    (OUT / f"{run_id}.md").write_text(md, encoding="utf-8")
    print(md)
    print("derived:", tables_from_receipt(OUT / f"{run_id}.json"))
    print("receipt:", OUT / f"{run_id}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
