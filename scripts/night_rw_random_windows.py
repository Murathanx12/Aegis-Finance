"""RW1 -- RANDOMISED-WINDOW BACKTESTS: when does a strategy beat the market, and what was it holding?

    python -m scripts.night_rw_random_windows --windows 12 --smoke
    python -m scripts.night_rw_random_windows                    # 240 windows, ~30-40 min

MURAT, 2026-09-09: "randomize the backtest ... four-year interval, five-year
interval, six-month interval ... from 2000 to 2025 ... 2019 to 2020 ... really
randomized times to see how it performs at any different time ... if we just
run it straight from 2000 to current date, it will pick up all the noise ...
see when it beats the S&P 500, what it was focusing on, and then differentiate
if it was noise or not."

WHAT THIS DOES
==============
For every strategy x construction pair, the SAME `n_windows` random windows are
drawn (seeded): a length from {6, 12, 24, 36, 48, 60, 72} months and a start
month uniform over 1999-03 .. (2024-12 - length). Each window is graded with
the repo's own monthly book (`learner.evaluate.book`: measured turnover, 25 bps
a side, hold band, liquidity floor) -- beta FIRST, beta-matched excess, terminal
wealth beside the VW market's over exactly the same months, drawdown, and WHAT
THE BOOK HELD: the average sector shares and size-band shares of its weights
over the window, so a "win" can be read as "it was 60% Manufacturing small caps
in 2003-2005" rather than as a number.

The NULL is five random genomes drawn from G1's search space and graded on the
identical windows: a strategy's win rate is reported as an excess over the null's
win rate on the same windows, which is the only comparison that removes the
windows' own luck (a 2009-2010 window is a win for almost anything with beta).

No window is a holdout. This job is DESCRIPTIVE: it answers "how often, when,
and holding what", and the receipt says so. The G1 genome included here was
already read on the sealed window by G2 (2026-09-09), so nothing new leaks.

LICENCE: PRODUCT_EXPERIMENT. $0 LLM. Places nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from learner import evaluate as E                     # noqa: E402

RUN_DATE = "2026-09-08"
OUT = REPO / "backend" / "data" / "optimus" / f"night_factory_{RUN_DATE}"
OUT.mkdir(parents=True, exist_ok=True)
LONG = REPO / "backend" / "data" / "optimus" / "learner" / "train_table_long.parquet"
G1_RECEIPT = OUT / "G1_evolve_run01.json"

COST_BPS = 25.0
LENGTHS = (6, 12, 24, 36, 48, 60, 72)
FIRST, LAST = "1999-03", "2024-12"
NW_LAG = 4

FEATURES = ["mom_12_1__xs", "net_rev_4w__xs", "ratio__xs", "consensus_rev_1m__xs", "disagreement__xs",
            "drawdown_60d__xs", "vol_60d__xs", "log_market_cap__xs", "ret_1m__xs", "ret_6m__xs",
            "coverage__xs", "target_rev_1m__xs", "log_close__xs", "dispersion__xs"]

#: the strategies the fleet and the farm actually run, as frozen selectors
STRATEGIES: dict[str, dict[str, float]] = {
    "momentum_12_1": {"mom_12_1__xs": 1.0},
    "revisions_4w": {"net_rev_4w__xs": 1.0},
    "target_upside": {"ratio__xs": 1.0},
    "human_heuristic_proxy": {"ratio__xs": 1.0, "consensus_rev_1m__xs": 1.0, "disagreement__xs": -1.0,
                              "drawdown_60d__xs": 0.5},
    "ensemble_3": {"mom_12_1__xs": 1.0, "net_rev_4w__xs": 1.0, "ratio__xs": 1.0},
}

CONSTRUCTIONS: dict[str, dict] = {
    "broad_k100_ew_hold400_floor3m": dict(k=100, weight="ew", hold_k=400, tradable_floor=3e6),
    "arena_k50_vw": dict(k=50, weight="vw", hold_k=None, tradable_floor=None),
}


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
    if n < 6:
        return None
    m = x.mean()
    u = x - m
    s = float(np.dot(u, u)) / n
    for L in range(1, min(lag, n - 1) + 1):
        w = 1.0 - L / (lag + 1.0)
        s += 2.0 * w * float(np.dot(u[L:], u[:-L])) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return float(m / se) if se > 0 else None


def _months(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def draw_windows(n: int, seed: int) -> list[tuple[str, str, int]]:
    rng = random.Random(seed)
    months = _months(FIRST, LAST)
    out = []
    for _ in range(n):
        L = rng.choice(LENGTHS)
        s = rng.randrange(0, len(months) - L + 1)
        out.append((months[s], months[s + L - 1], L))
    return out


def g1_best_genome() -> dict[str, float] | None:
    if not G1_RECEIPT.exists():
        return None
    g = json.loads(G1_RECEIPT.read_text(encoding="utf-8"))
    top = (g.get("top10_dev") or [{}])[0].get("genome") or {}
    return top.get("w")


def random_genomes(n: int, seed: int) -> dict[str, dict[str, float]]:
    rng = random.Random(seed)
    out = {}
    for i in range(n):
        w = {f: rng.choice((-1.0, -0.5, 0.0, 0.5, 1.0)) for f in FEATURES}
        if all(v == 0.0 for v in w.values()):
            w[rng.choice(FEATURES)] = 1.0
        out[f"NULL_random_{i}"] = w
    return out


def signal(df: pd.DataFrame, w: dict[str, float]) -> np.ndarray:
    s = np.zeros(len(df))
    for f, v in w.items():
        if v and f in df.columns:
            s += v * df[f].fillna(0.0).to_numpy(dtype="float64")
    return s


def era_of(month: str) -> str:
    y = int(month[:4])
    return "1999-2007" if y <= 2007 else ("2008-2015" if y <= 2015 else "2016-2024")


def grade_window(df_w: pd.DataFrame, pred_col: str, cons: dict, meta: dict) -> dict:
    try:
        r = E.book(df_w, pred_col, cost_bps=COST_BPS, with_risk=True, return_series=True,
                   return_weights=True, **cons)
    except SystemExit as exc:
        return {"verdict": "REFUSED", "why": str(exc)[:160]}
    if r.get("months", 0) < 3:
        return {"verdict": "REFUSED", "why": f"{r.get('months')} months"}
    net = r["_series"]["net"].astype("float64")
    mkt = r["_series"]["market"].reindex(net.index).astype("float64")
    y, x = net.to_numpy(), mkt.to_numpy()
    beta = float(np.polyfit(x, y, 1)[0]) if len(y) >= 6 and np.std(x) > 0 else None
    ex_bm = y - (beta if beta is not None else 1.0) * x
    tw_n, tw_m = float(np.prod(1 + y)), float(np.prod(1 + x))
    # what it held: weight-averaged sector and size-band shares over the window
    sec = defaultdict(float)
    band = defaultdict(float)
    n_m = 0
    for m, wts in r["_weights"].items():
        n_m += 1
        for p, w in wts.items():
            key = (m, int(p))
            s_, b_ = meta.get(key, ("?", "?"))
            sec[s_] += w
            band[b_] += w
    sec = {k: round(v / max(n_m, 1), 4) for k, v in sec.items()}
    band = {k: round(v / max(n_m, 1), 4) for k, v in band.items()}
    top_sec = max(sec.items(), key=lambda kv: kv[1]) if sec else ("?", 0.0)
    return {
        "verdict": "OK", "months": int(len(y)), "beta": _r(beta),
        "tw_net": _r(tw_n), "tw_market": _r(tw_m), "tw_ratio": _r(tw_n / tw_m if tw_m > 0 else None),
        "ann_net_pct": _r((tw_n ** (12 / len(y)) - 1) * 100, 2), "ann_market_pct": _r((tw_m ** (12 / len(x)) - 1) * 100, 2),
        "beta_matched_ann_pct": _r(float(ex_bm.mean()) * 12 * 100, 3), "t_beta_matched": _r(_nw_t(ex_bm), 3),
        "max_dd": _r((r.get("risk") or {}).get("max_drawdown_net")),
        "max_dd_market": _r((r.get("risk") or {}).get("max_drawdown_market_same_months")),
        "mean_turnover": _r(r.get("mean_turnover")),
        "beats_market_raw": bool(tw_n > tw_m), "beats_beta_matched": bool(ex_bm.mean() > 0),
        "top_sector": top_sec[0], "top_sector_share": _r(top_sec[1]),
        "sector_shares": sec, "band_shares": band,
        "small_share": _r(band.get("lt_1_5", 0.0) + band.get("no_opinion", 0.0)),
    }


def RW1_random_windows(n_windows: int = 240, seed: int = 20260909, smoke: bool = False,
                       n_null: int = 5) -> dict:
    t0 = time.time()
    cols = ["month", "permno", "fwd_1m", "mkt_vw_1m", "market_cap", "log_dollar_vol_20d",
            "sector", "band"] + FEATURES
    df = pd.read_parquet(LONG, columns=cols)
    meta = dict(zip(zip(df["month"].astype(str), df["permno"].astype(int)),
                    zip(df["sector"].astype(str), df["band"].astype(str))))
    strategies = dict(STRATEGIES)
    g1w = g1_best_genome()
    if g1w:
        strategies["G1_best_dev_genome_ALREADY_READ_ON_HOLDOUT"] = g1w
    nulls = random_genomes(n_null, seed + 1)
    all_sel = {**strategies, **nulls}
    for name, w in all_sel.items():
        df[f"_s_{name}"] = signal(df, w)
    windows = draw_windows(n_windows if not smoke else 12, seed)
    cons_items = list(CONSTRUCTIONS.items()) if not smoke else list(CONSTRUCTIONS.items())[:1]
    rows = []
    i = 0
    total = len(windows) * len(all_sel) * len(cons_items)
    for (a, b, L) in windows:
        df_w = df[(df["month"] >= a) & (df["month"] <= b)]
        for cname, cons in cons_items:
            for sname in all_sel:
                g = grade_window(df_w, f"_s_{sname}", cons, meta)
                g.update({"start": a, "end": b, "length_m": L, "era_start": era_of(a),
                          "strategy": sname, "construction": cname,
                          "is_null": sname.startswith("NULL_")})
                rows.append(g)
                i += 1
        if len(rows) % (len(all_sel) * len(cons_items) * 10) == 0:
            print(f"    {i}/{total} gradings, {time.time() - t0:.0f}s", flush=True)
    res = pd.DataFrame(rows)
    ok = res[res["verdict"] == "OK"].copy()
    ok.to_parquet(OUT / "RW1_windows.parquet", index=False)

    # ---- aggregate: win rates vs the null on the SAME windows ----------------
    def agg(g: pd.DataFrame) -> dict:
        return {"n": int(len(g)),
                "win_raw": _r(g["beats_market_raw"].mean()), "win_beta_matched": _r(g["beats_beta_matched"].mean()),
                "median_tw_ratio": _r(g["tw_ratio"].median()), "median_beta": _r(g["beta"].median()),
                "median_bm_ann_pct": _r(g["beta_matched_ann_pct"].median(), 2),
                "share_t_gt_2": _r((g["t_beta_matched"].fillna(0) > 2).mean()),
                "median_max_dd": _r(g["max_dd"].median())}
    summary = {}
    null_by_key: dict = {}
    for cname in ok["construction"].unique():
        nl = ok[(ok["construction"] == cname) & ok["is_null"]]
        null_by_key[cname] = {"overall": agg(nl),
                              "by_length": {int(L): agg(g) for L, g in nl.groupby("length_m")},
                              "by_era": {e: agg(g) for e, g in nl.groupby("era_start")}}
    for (sname, cname), g in ok[~ok["is_null"]].groupby(["strategy", "construction"]):
        nl = null_by_key[cname]
        base = agg(g)
        # excess over the null on the same windows (raw and beta-matched)
        by_len = {}
        for L, gg in g.groupby("length_m"):
            nn = nl["by_length"].get(int(L), {})
            by_len[int(L)] = {**agg(gg), "excess_win_bm_over_null": _r(agg(gg)["win_beta_matched"] - (nn.get("win_beta_matched") or 0.0))}
        by_era = {}
        for e, gg in g.groupby("era_start"):
            nn = nl["by_era"].get(e, {})
            by_era[e] = {**agg(gg), "excess_win_bm_over_null": _r(agg(gg)["win_beta_matched"] - (nn.get("win_beta_matched") or 0.0))}
        bull = g[g["tw_market"] > 1]
        bear = g[g["tw_market"] <= 1]
        wins = g[g["beats_beta_matched"]]
        losses = g[~g["beats_beta_matched"]]
        def _sec_mean(x: pd.DataFrame) -> dict:
            acc = defaultdict(float)
            for d in x["sector_shares"]:
                for k, v in d.items():
                    acc[k] += v
            n = max(len(x), 1)
            return {k: round(v / n, 3) for k, v in sorted(acc.items(), key=lambda kv: -kv[1])[:6]}
        summary[f"{sname}|{cname}"] = {
            "overall": {**base, "excess_win_bm_over_null": _r(base["win_beta_matched"] - nl["overall"]["win_beta_matched"]),
                        "excess_win_raw_over_null": _r(base["win_raw"] - nl["overall"]["win_raw"])},
            "by_length_months": by_len, "by_start_era": by_era,
            "by_market_regime": {"market_up_windows": agg(bull), "market_down_windows": agg(bear)},
            "what_it_held": {"sector_shares_when_it_WON": _sec_mean(wins),
                             "sector_shares_when_it_LOST": _sec_mean(losses),
                             "small_share_when_won": _r(wins["small_share"].mean()),
                             "small_share_when_lost": _r(losses["small_share"].mean()),
                             "share_of_windows_with_one_sector_gt_40pct": _r((g["top_sector_share"] > 0.4).mean())},
            "null_same_windows": nl["overall"],
        }
    best = max(summary.items(), key=lambda kv: kv[1]["overall"]["excess_win_bm_over_null"] or -9) if summary else None
    return {
        "job": "RW1_random_windows", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
        "question": ("Across random windows of 6-72 months anywhere in 1999-2024: how often does each "
                     "strategy beat a beta-matched market, in which eras and regimes, holding what -- and "
                     "how much of that is the windows' own luck (the random-genome null on the same windows)?"),
        "windows": {"n": len(windows), "lengths": LENGTHS, "seed": seed,
                    "n_by_length": {int(L): int(sum(1 for w in windows if w[2] == L)) for L in LENGTHS}},
        "strategies": list(strategies), "null_genomes": list(nulls), "constructions": CONSTRUCTIONS,
        "cost_bps_per_side": COST_BPS, "gradings": int(len(res)), "refused": int((res["verdict"] != "OK").sum()),
        "summary": summary, "null_by_construction": null_by_key,
        "windows_parquet": str(OUT / "RW1_windows.parquet"),
        "headline": (f"{len(windows)} random windows x {len(strategies)} strategies x {len(cons_items)} constructions; "
                     f"best excess beta-matched win rate over the null: {best[0]} "
                     f"{best[1]['overall']['excess_win_bm_over_null']:+.2f} (win {best[1]['overall']['win_beta_matched']}, "
                     f"null {best[1]['null_same_windows']['win_beta_matched']}, median beta {best[1]['overall']['median_beta']})")
        if best else "no window graded",
        "verdict": "DESCRIPTIVE: no window is a holdout; read win rates as EXCESS over the null on the same windows, "
                   "and read 'what_it_held' before believing any win",
        "family_max_p": None,
        "elapsed_s": round(time.time() - t0, 1), "written_utc": _now(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--windows", type=int, default=240)
    ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args(argv)
    payload = RW1_random_windows(n_windows=a.windows, seed=a.seed, smoke=a.smoke)
    payload["run"] = a.run
    out = Path(a.out) if a.out else OUT / f"RW1_random_windows_run{a.run:02d}{'_smoke' if a.smoke else ''}.json"
    out.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    print(f"\nRW1: {payload['headline']}\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
