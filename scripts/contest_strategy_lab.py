"""Contest strategy lab (2026-09-29 night): which BOOK maximises P(top 10), on past seasons.

    python -m scripts.contest_strategy_lab                  # every season 2019-2026, two pools
    python -m scripts.contest_strategy_lab --draws 2000

The owner's brief: "we are aiming for first place or top 10, not a respectable 5%". The
declared utility is RISK-SEEKING: maximise the RIGHT TAIL of relative P&L vs the WLS index
(ACWI is the proxy here), accepting a large chance of a loss. Nothing here is a claim of
skill: every book below is a variance bet, and the NULL column (one random sign a day on the
book AND the benchmark) is printed beside every realised number.

Books (US listings; long only; 20% a slot; gross <= 100% asserted; sessions from the pool's
own stamps, report timing corrected for untimed stamps):

  ROT5_TRAIL        the desk's frozen rule: 5 reporting names with the largest trailing mean
                    |earnings reaction| (past move size), bought at the open of the session
                    before the print, sold at the reaction session's open (held THROUGH)
  ROT3_TRAIL        the same, 3 slots (60% gross; the 20% cap forbids concentrating further)
  ROT5_TRAIL_BEFORE the same names, sold at the CLOSE of the buy session: out BEFORE the print
                    (needs a close fill; states the pre-print run-up alone)
  ROT5_BLEND        ranked by the mean percentile of trailing |reaction| and nn_lab's
                    walk-forward size-of-move forecast (from 2020; trailing alone before)
  ROT5_SIZE         ranked by nn_lab's size forecast alone (trailing where it is missing)
  ROT5_RANDOM       reporting names in random order: the SELECTION null (no magnitude signal)
  MAXTAIL_BH        the fallback: the 5 highest-volatility liquid operating companies on the
                    window's first day, held to the end (no rotation, no event)

A direction prior is NOT included: none has survived (REVIEW_2026-09-28 §3, the 09-29 bridges:
76 rules, none beats the market; TRIAL-PT-REVERSAL-1 FAILED_VARIANT). Stated, not modelled.

Pools: SEC8K (the desk's, survivor-selected: 0 dead names) and IBES_ALL (IBES actuals,
dead names included -- the survivorship-free reading where it exists, through the IBES end).
Costs: 0 / 10 / 25 bps a side (the contest's own commission is UNCONFIRMED).

PRODUCT_EXPERIMENT; family of one; utility 'contest rank, right tail'. No network, $0 LLM.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import contest_calendar as cc     # noqa: E402
from scripts import contest_desk as desk       # noqa: E402
from scripts import contest_book_compare as cbc  # noqa: E402

OUT = cc.CONTEST / "strategy_lab"
W = desk.WEIGHT
SEED = 20261013
COSTS_BPS = (0.0, 10.0, 25.0)
BOOKS: dict[str, dict] = {
    "ROT5_TRAIL": {"k": 5, "rank": "trail", "exit": "through"},
    "ROT3_TRAIL": {"k": 3, "rank": "trail", "exit": "through"},
    "ROT5_TRAIL_BEFORE": {"k": 5, "rank": "trail", "exit": "before"},
    "ROT5_BLEND": {"k": 5, "rank": "blend", "exit": "through"},
    "ROT5_SIZE": {"k": 5, "rank": "size", "exit": "through"},
    "ROT5_RANDOM": {"k": 5, "rank": "random", "exit": "through"},
    "MAXTAIL_BH": {"k": 5, "rank": "maxtail", "exit": "hold"},
    # the live desk holds VENDOR dates, the sim holds actual prints: a missed date is a slot that
    # holds the name through an ordinary session (its own open->open 5 sessions earlier) instead
    "ROT5_TRAIL_MISS10": {"k": 5, "rank": "trail", "exit": "through", "miss": 0.10},
    "ROT5_TRAIL_MISS30": {"k": 5, "rank": "trail", "exit": "through", "miss": 0.30},
}
POOLS = ("SEC8K", "IBES_ALL")
ERAS = {"Oct 2019-25": lambda w: w.endswith("Oct"),
        "all 2024-26": lambda w: int(w[:4]) >= 2024,
        "all 2019-26": lambda w: True}
UTILITY = ("contest rank of ~2,700; first place or top 10 wanted: RISK-SEEKING by declared choice "
           "(maximise the right tail of relative P&L; a large chance of a loss is accepted)")


def oc_matrix(panel: desk.Panel) -> np.ndarray:
    """Open -> close of the same session (the 'sell before the print' leg); 0 where missing."""
    O = panel.open.astype("float64")
    C = panel.close.astype("float64")
    r = C / O - 1.0
    r = np.where(np.isfinite(r) & (r < 2.0) & (r > -0.8), r, 0.0)
    return r


def rank_key(gg: pd.DataFrame, t: int, rank: str, size: Optional[np.ndarray], rng) -> np.ndarray:
    tr = gg.trail_abs.to_numpy(dtype=float)
    if rank == "trail" or size is None and rank in ("blend", "size"):
        return tr
    if rank == "random":
        return rng.random(len(gg))
    s = size[t, gg.ci.to_numpy(int)]
    if rank == "size":
        # a size forecast where one exists; the trailing mean's percentile otherwise
        return np.where(np.isfinite(s), 1.0 + cbc._rank_pct(s), cbc._rank_pct(tr))
    a = cbc._rank_pct(tr)
    b = cbc._rank_pct(s)
    return np.where(np.isfinite(s), (a + b) / 2.0, a)


def book_path(days: np.ndarray, ev: pd.DataFrame, m: cbc.Mkt, *, k: int, rank: str, exit: str,
              size: Optional[np.ndarray] = None, oc: Optional[np.ndarray] = None,
              operating: Optional[np.ndarray] = None, rng=None, miss: float = 0.0) -> pd.DataFrame:
    """One season, one book. Daily rows: book return, bench return, weight traded, gross.

    Enter at the open of pre_i. exit='through' leaves at the open of react_i; exit='before'
    leaves at the close of pre_i (return = open->close of that session); exit='hold' (MAXTAIL)
    buys on the first day and holds to the window's end."""
    rng = rng if rng is not None else np.random.default_rng(SEED)
    rows = []
    if rank == "maxtail":
        t0 = int(days[0])
        elig = m.liq[t0] & np.isfinite(m.sig[t0])
        if operating is not None:
            elig &= operating
        cand = np.flatnonzero(elig)
        pick = cand[np.argsort(-m.sig[t0, cand], kind="stable")[:k]] if len(cand) else np.array([], int)
        alive = set(int(j) for j in pick)
        for n, t in enumerate(days):
            t = int(t)
            day = sum(W * m.r[t, j] for j in alive)
            gross = W * len(alive)
            traded = W * len(pick) if n == 0 else 0.0
            for j in list(alive):
                if m.last[t, j]:
                    alive.discard(j)          # delisted: out at its last close, cash after
            rows.append({"t": t, "book": day, "bench": float(m.bench[t]), "traded": traded, "gross": gross})
        if rows:
            rows[-1]["traded"] += W * len(alive)
        return pd.DataFrame(rows)
    by_pre = {int(i): g for i, g in ev.groupby("pre_i")} if len(ev) else {}
    held: list[dict] = []
    for t in days:
        t = int(t)
        traded = 0.0
        keep = []
        for p in held:
            if p["exit"] <= t:
                traded += W
            else:
                keep.append(p)
        held = keep
        free = k - len(held)
        held_j = {p["j"] for p in held}
        g = by_pre.get(t)
        before_today: list[int] = []
        if free > 0 and g is not None:
            ok = (g.on_cadence.to_numpy(bool) & g.trail_abs.notna().to_numpy()
                  & m.liq[t, g.ci.to_numpy(int)] & ~g.ci.isin(held_j).to_numpy())
            gg = g[ok].drop_duplicates("ci")
            if len(gg):
                key = rank_key(gg, t, rank, size, rng)
                pick = gg.iloc[np.argsort(-key, kind="stable")[:free]]
                for rr in pick.itertuples():
                    j = int(rr.ci)
                    traded += W
                    if exit == "before":
                        before_today.append(j)
                        traded += W            # out at this session's close
                        continue
                    ex = int(rr.react_i) if pd.notna(rr.react_i) else t + 1
                    lag = 5 if (miss > 0 and rng.random() < miss) else 0
                    held.append({"j": j, "exit": max(ex, t + 1), "lag": lag})
                    held_j.add(j)
        day = sum(W * m.r[max(0, t - p.get("lag", 0)), p["j"]] for p in held)
        if before_today and oc is not None:
            day += sum(W * oc[t, j] for j in before_today)
        gross = W * (len(held) + len(before_today))
        assert gross <= 1.0 + 1e-9, "gross above 100%"
        for p in held:
            if m.last[t, p["j"]]:
                p["exit"] = t + 1
        rows.append({"t": t, "book": day, "bench": float(m.bench[t]), "traded": traded, "gross": gross})
    if rows:
        rows[-1]["traded"] += W * len(held)
    return pd.DataFrame(rows)


def run(draws: int = 4000, from_year: int = 2019) -> dict:
    from scripts import contest_rotation_sim as rsim           # noqa: PLC0415
    long = cc.load_bars_usd([], include_us=True)
    long["date"] = pd.to_datetime(long["date"]).dt.normalize()
    long = long[long.date >= pd.Timestamp("2016-01-01")].drop_duplicates(["symbol", "date"])
    panel = desk.panel_from_long(long)
    del long
    m = cbc.market(panel)
    oc = oc_matrix(panel)
    size = cbc.size_forecast_matrix(panel)
    ib = cbc.ibes_stamps()
    ibes_max = pd.Timestamp(ib.ts_utc.max()).tz_convert(None).normalize()
    P = cbc.pools(panel, ibes=ib)
    rng = np.random.default_rng(SEED)
    wins = rsim.windows(panel, from_year)
    res: dict = {"utility": UTILITY, "licence": desk.LICENCE, "draws": draws, "seed": SEED,
                 "benchmark": "ACWI (proxy for WLS; stated)", "costs_bps_per_side": list(COSTS_BPS),
                 "books": BOOKS, "direction_prior": "NONE included: none has survived (stated, not modelled)",
                 "panel": {"days": int(len(panel.dates)), "symbols": int(len(panel.syms)),
                           "first": str(panel.dates[0].date()), "last": str(panel.dates[-1].date()),
                           "return_faults_zeroed": m.n_faults},
                 "size_forecast": str(cbc.OOS_PATH.name) if size is not None else None,
                 "ibes_last_announcement": str(ibes_max.date()), "pools": {}, "seasons": []}
    for pname in POOLS:
        raw = P[pname]
        ev = desk.build_events(panel, raw)
        ev = ev[ev.market == "US"]
        evs = ev[ev.pre_i.notna()].copy()
        op = cbc.operating_mask(evs, len(panel.syms))
        res["pools"][pname] = {"stamps": int(len(raw)), "events": int(len(ev)),
                               "symbols": int(ev.symbol.nunique())}
        print(pname, res["pools"][pname], flush=True)
        for wname, days in wins:
            end = panel.dates[days[-1]]
            if pname.startswith("IBES") and end + pd.Timedelta(days=3) > ibes_max:
                continue
            row = {"window": wname, "pool": pname, "start": str(panel.dates[days[0]].date()),
                   "end": str(end.date()), "books": {}}
            for book, spec in BOOKS.items():
                d = book_path(days, evs, m, k=spec["k"], rank=spec["rank"], exit=spec["exit"], size=size,
                              oc=oc, operating=op, rng=np.random.default_rng(SEED + len(res["seasons"])),
                              miss=spec.get("miss", 0.0))
                b, bn, tr = d.book.to_numpy(), d.bench.to_numpy(), d.traded.to_numpy()
                out = {"max_gross": float(d.gross.max()), "avg_gross": round(float(d.gross.mean()), 3)}
                for cb in COSTS_BPS:
                    cost = tr * cb / 1e4
                    out[f"{int(cb)}bps"] = {"realised": round(float(cbc.rel_paths(b, bn, cost)), 4),
                                            "null": cbc.probs(cbc.null_draws(b, bn, cost, rng, draws)),
                                            "boot": cbc.probs(cbc.boot_draws(b, bn, cost, rng, draws, len(b))),
                                            "_daily": [b.round(6).tolist(), bn.round(6).tolist(),
                                                       cost.round(7).tolist()]}
                row["books"][book] = out
            res["seasons"].append(row)
            print(pname, wname, " ".join(f"{k_}:{v['10bps']['realised']:+.3f}" for k_, v in row["books"].items()),
                  flush=True)
    res["pooled"] = pooled(res, rng, draws)
    return res


def pooled(res: dict, rng, draws: int) -> dict:
    out: dict = {}
    for pool in res["pools"]:
        for era, f in ERAS.items():
            ss = [s for s in res["seasons"] if s["pool"] == pool and f(s["window"])]
            if not ss:
                continue
            L = int(np.median([len(s["books"]["ROT5_TRAIL"]["0bps"]["_daily"][0]) for s in ss]))
            for book in BOOKS:
                for cb in COSTS_BPS:
                    key = f"{int(cb)}bps"
                    trip = [np.array(s["books"][book][key]["_daily"]) for s in ss]
                    nul = np.concatenate([cbc.null_draws(t[0], t[1], t[2], rng, max(1, draws // len(ss)))
                                          for t in trip])
                    pick = rng.integers(0, len(trip), size=draws)
                    bt = np.concatenate([cbc.boot_draws(trip[i][0], trip[i][1], trip[i][2], rng,
                                                        int((pick == i).sum()), L)
                                         for i in range(len(trip)) if (pick == i).any()])
                    real = np.array([s["books"][book][key]["realised"] for s in ss])
                    out.setdefault(pool, {}).setdefault(era, {}).setdefault(book, {})[key] = {
                        "n_seasons": len(ss), "null": cbc.probs(nul), "boot": cbc.probs(bt),
                        "realised_median": round(float(np.median(real)), 4),
                        "realised_mean": round(float(np.mean(real)), 4),
                        "realised_gt20": int((real > 0.2).sum()), "realised_gt40": int((real > 0.4).sum()),
                        "realised_gt60": int((real > 0.6).sum()), "realised_lt_m20": int((real < -0.2).sum()),
                        "realised_best": round(float(real.max()), 4), "realised_worst": round(float(real.min()), 4)}
    return out


def paired(res: dict, pool: str, a: str, b: str, cost: str = "10bps", era=lambda w: True) -> dict:
    """Season-paired realised difference a - b, with its leave-one-season-out worst mean."""
    z = pd.Series({s["window"]: s["books"][a][cost]["realised"] - s["books"][b][cost]["realised"]
                   for s in res["seasons"] if s["pool"] == pool and era(s["window"])})
    if len(z) < 3:
        return {"n": int(len(z))}
    loo = [float(z.drop(w).mean()) for w in z.index]
    sd = float(z.std(ddof=1))
    return {"n": int(len(z)), "mean": round(float(z.mean()), 4), "median": round(float(z.median()), 4),
            "n_positive": int((z > 0).sum()), "t": round(float(z.mean() / sd * np.sqrt(len(z))), 2) if sd > 0 else None,
            "loo_worst_mean": round(min(loo), 4), "loo_worst_drops": str(z.index[int(np.argmin(loo))])}


def report(res: dict) -> str:
    L = ["# Contest strategy lab (receipt beside this file)", "", f"Utility: {res['utility']}.",
         f"Benchmark: {res['benchmark']}. Draws: {res['draws']}. Direction prior: {res['direction_prior']}.",
         "NULL = zero direction skill (random daily sign on book and benchmark). BOOT = the season's own "
         "days resampled in 5-day blocks (keeps its drift; optimistic). Realised = seasons out of n.", ""]
    for pool, eras in res["pooled"].items():
        for era, books in eras.items():
            L += [f"## {pool}, {era}", "",
                  "| book | cost | n | realised median | realised >+20 / >+40 / >+60 / <-20 | best / worst "
                  "| NULL P>+20 / +40 / +60 / <-20 | BOOT P>+20 / +40 / +60 / <-20 |",
                  "|---|---|---|---|---|---|---|---|"]
            for book, costs in books.items():
                for key in ("0bps", "10bps", "25bps"):
                    v = costs[key]
                    n, b = v["null"], v["boot"]
                    L.append(f"| {book} | {key} | {v['n_seasons']} | {v['realised_median']:+.1%} "
                             f"| {v['realised_gt20']} / {v['realised_gt40']} / {v['realised_gt60']} / "
                             f"{v['realised_lt_m20']} | {v['realised_best']:+.0%} / {v['realised_worst']:+.0%} "
                             f"| {n['P>+20%']:.1%} / {n['P>+40%']:.1%} / {n['P>+60%']:.1%} / {n['P<-20%']:.1%} "
                             f"| {b['P>+20%']:.1%} / {b['P>+40%']:.1%} / {b['P>+60%']:.1%} / {b['P<-20%']:.1%} |")
            L.append("")
    for pool in res["pools"]:
        L += [f"## Every season, {pool}, 10 bps a side: realised relative result", "",
              "| season | " + " | ".join(BOOKS) + " |", "|---|" + "---|" * len(BOOKS)]
        for s in res["seasons"]:
            if s["pool"] == pool:
                L.append(f"| {s['window']} | " + " | ".join(f"{s['books'][b]['10bps']['realised']:+.1%}"
                                                            for b in BOOKS) + " |")
        L.append("")
    L += ["## Paired season differences, realised, 10 bps (a minus b)", "",
          "| pool | era | a | b | n | mean | median | a better | t | leave-one-out worst (drops) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for pool in res["pools"]:
        for era, f in (("all", lambda w: True), ("Oct", lambda w: w.endswith("Oct"))):
            for a, b in (("ROT5_TRAIL", "ROT5_RANDOM"), ("ROT3_TRAIL", "ROT5_TRAIL"),
                         ("ROT5_TRAIL", "ROT5_TRAIL_BEFORE"), ("ROT5_BLEND", "ROT5_TRAIL"),
                         ("ROT5_SIZE", "ROT5_TRAIL"), ("ROT5_TRAIL", "MAXTAIL_BH")):
                p = paired(res, pool, a, b, era=f)
                if p.get("n", 0) >= 3:
                    L.append(f"| {pool} | {era} | {a} | {b} | {p['n']} | {p['mean']:+.1%} | {p['median']:+.1%} "
                             f"| {p['n_positive']} | {p['t']} | {p['loo_worst_mean']:+.1%} ({p['loo_worst_drops']}) |")
    return "\n".join(L) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=4000)
    ap.add_argument("--from-year", type=int, default=2019)
    a = ap.parse_args(argv)
    res = run(a.draws, a.from_year)
    OUT.mkdir(parents=True, exist_ok=True)
    run_id = f"lab_{cc.utc_stamp()}"
    res["run_id"] = run_id
    daily = [{"pool": s["pool"], "window": s["window"], "book": bk, "cost": ck, "book_r": v["_daily"][0],
              "bench_r": v["_daily"][1], "cost_r": v["_daily"][2]}
             for s in res["seasons"] for bk, bv in s["books"].items() for ck, v in bv.items()
             if isinstance(v, dict) and "_daily" in v]
    slim = json.loads(json.dumps(res, default=str))
    for s in slim["seasons"]:
        for b in s["books"].values():
            for k_ in list(b):
                if isinstance(b[k_], dict):
                    b[k_].pop("_daily", None)
    cc.write_json(slim, OUT / f"{run_id}.json")
    pd.DataFrame(daily).to_parquet(OUT / f"{run_id}_daily.parquet", index=False)
    md = report(res)
    (OUT / f"{run_id}.md").write_text(md, encoding="utf-8")
    print(md)
    print("receipt:", OUT / f"{run_id}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
