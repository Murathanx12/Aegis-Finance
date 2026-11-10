"""The owner's dip/bounce habit as an ADD-WHILE-INVESTED overlay (S65 night, simulation only).

Book: a held core at base weight `base` (rest in cash at the FF risk-free rate).
A DIP (trigger at close t) raises the target weight by `step` (capped at `cap`);
the exit is either TRIM (a +2% 3-session rise lowers the target by `step`, never
below base) or DECAY (each add expires after `hold` sessions). Trades execute at
the NEXT close (t+1), never at the close that defined the trigger. Costs per unit
of traded weight: `cost_bps`.

Controls, all at the same settings:
* `const_avg`  — a constant weight equal to the overlay's realised AVERAGE weight
                 (an overlay that only adds beta must not get credit for beta);
* `random_twin`— the SAME number of add events on random dates (uniform over the
                 eligible sessions), same step / exit / cap / costs; `--twins` draws.
* `buy_hold`   — 100% invested, and `base` constant.
Score = overlay CAGR - twin median CAGR, with the overlay's percentile among the
twins, by-year sign count (overlay minus twin-median annual return), and the worst
leave-one-year-out mean.

Instruments: SPY and QQQ (prices_deep, 2016-01 -> 2026-11, close-to-close, NOT
dividend adjusted -- both arms hold the same instrument so dividends mostly cancel;
said on the receipt), the FF value-weighted market total return 1964-2024, and
single stocks from the liquid 500 (CRSP total return, 1994-2024).
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


def triggers(r: np.ndarray, kind: str, sig: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """dip[t], bounce[t] from returns known at close t."""
    lr = np.log1p(np.nan_to_num(r))
    c3 = np.full(len(r), np.nan)
    cs = np.cumsum(lr)
    c3[3:] = cs[3:] - cs[:-3]
    c3 = np.expm1(c3)
    if kind == "dip3":           # -2% over 3 sessions
        dip = c3 <= -0.02
    elif kind == "dip1":         # -1% day
        dip = r <= -0.01
    elif kind == "dip3_sigma":   # -1 sigma over 3 sessions (sigma from trailing 63d, known at t)
        dip = c3 <= -1.0 * sig * math.sqrt(3)
    else:
        raise ValueError(kind)
    bounce = c3 >= (0.02 if kind != "dip3_sigma" else 1.0 * sig * math.sqrt(3))
    return np.nan_to_num(dip, nan=0).astype(bool), np.nan_to_num(bounce, nan=0).astype(bool)


def target_path(dip_days: np.ndarray, bounce: np.ndarray, *, base: float, step: float,
                cap: float, exit_: str, hold: int) -> tuple[np.ndarray, int]:
    """Target weight decided at close t (state machine over the trigger series)."""
    n = len(dip_days)
    tgt = np.empty(n)
    target = base
    expiries: list[int] = []
    adds = 0
    for t in range(n):
        if exit_ == "decay":
            while expiries and expiries[0] <= t:
                expiries.pop(0)
                target = max(base, target - step)
        if dip_days[t] and target + step <= cap + 1e-12:
            target += step
            adds += 1
            if exit_ == "decay":
                expiries.append(t + hold)
        elif exit_ == "trim" and bounce[t] and target - step >= base - 1e-12:
            target -= step
        tgt[t] = target
    return tgt, adds


def run_book(r: np.ndarray, rf: np.ndarray, tgt: np.ndarray, cost: float, base: float) -> dict:
    """Decision at close t, trade at close t+1, so the weight held in session t is tgt[t-2]."""
    n = len(r)
    w = np.full(n, base)
    w[2:] = tgt[:-2]
    dw = np.zeros(n)
    dw[1:] = np.abs(np.diff(w))
    g = 1.0 + w * r + (1.0 - w) * rf - cost * dw
    nav = np.cumprod(g)
    return {"nav": nav, "w": w, "traded": float(dw.sum())}


def cagr(nav: np.ndarray, n_per_year: float = 252.0) -> float:
    return float(max(nav[-1], 1e-9) ** (n_per_year / len(nav)) - 1.0)


def annual(nav: np.ndarray, years: np.ndarray) -> dict:
    out, prev = {}, 1.0
    for y in sorted(set(years.tolist())):
        last = nav[years == y][-1]
        out[int(y)] = float(last / prev - 1.0)
        prev = last
    return out


def evaluate(name: str, r: np.ndarray, rf: np.ndarray, years: np.ndarray, sig, *, variant: dict,
             twins: int, rng: np.random.Generator, cost: float) -> dict:
    dip, bounce = triggers(r, variant["trigger"], sig)
    kw = dict(base=variant["base"], step=variant["step"], cap=variant["cap"],
              exit_=variant["exit"], hold=variant["hold"])
    tgt, adds = target_path(dip, bounce, **kw)
    ov = run_book(r, rf, tgt, cost, variant["base"])
    avg_w = float(ov["w"].mean())
    const = run_book(r, rf, np.full(len(r), avg_w), cost, avg_w)
    bh = run_book(r, rf, np.ones(len(r)), cost, 1.0)
    base_b = run_book(r, rf, np.full(len(r), variant["base"]), cost, variant["base"])
    n_trig = int(dip.sum())
    valid = np.arange(3, len(r))
    tw_cagr, tw_ann, tw_w, tw_timing = [], [], [], []
    for _ in range(twins):
        rd = np.zeros(len(r), bool)
        rd[rng.choice(valid, size=min(n_trig, len(valid)), replace=False)] = True
        tt, _a = target_path(rd, bounce, **kw)
        b = run_book(r, rf, tt, cost, variant["base"])
        tw_cagr.append(cagr(b["nav"]))
        tw_ann.append(annual(b["nav"], years))
        aw = float(b["w"].mean())
        tw_w.append(aw)
        tw_timing.append(cagr(b["nav"]) - cagr(run_book(r, rf, np.full(len(r), aw), cost, aw)["nav"]))
    tw_cagr = np.array(tw_cagr)
    tw_timing = np.array(tw_timing)
    a_ov = annual(ov["nav"], years)
    a_const = annual(const["nav"], years)
    yrs = sorted(a_ov)
    tw_med_ann = {y: float(np.median([t[y] for t in tw_ann])) for y in yrs}
    d = np.array([a_ov[y] - tw_med_ann[y] for y in yrs])
    dc = np.array([a_ov[y] - a_const[y] for y in yrs])
    loo = [float(np.delete(d, i).mean()) for i in range(len(d))] if len(d) > 1 else [float("nan")]
    se = float(d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 2 else float("nan")
    c_ov = cagr(ov["nav"])
    return {
        "instrument": name, **variant, "n_sessions": int(len(r)), "first_year": int(yrs[0]),
        "last_year": int(yrs[-1]), "n_trigger_days": n_trig, "n_adds": adds, "avg_weight": avg_w,
        "traded_weight": ov["traded"],
        "cagr_overlay": c_ov, "cagr_const_avg_weight": cagr(const["nav"]),
        "cagr_base_constant": cagr(base_b["nav"]), "cagr_buy_hold": cagr(bh["nav"]),
        "cagr_twin_median": float(np.median(tw_cagr)), "cagr_twin_p10": float(np.percentile(tw_cagr, 10)),
        "cagr_twin_p90": float(np.percentile(tw_cagr, 90)),
        "overlay_percentile_in_twins": float((tw_cagr < c_ov).mean() * 100),
        "twin_avg_weight_median": float(np.median(tw_w)),
        "timing_value": c_ov - cagr(const["nav"]),
        "twin_timing_value_median": float(np.median(tw_timing)),
        "twin_timing_value_p10": float(np.percentile(tw_timing, 10)),
        "twin_timing_value_p90": float(np.percentile(tw_timing, 90)),
        "timing_percentile_in_twins": float((tw_timing < c_ov - cagr(const["nav"])).mean() * 100),
        "vs_twin_cagr": c_ov - float(np.median(tw_cagr)),
        "vs_const_cagr": c_ov - cagr(const["nav"]),
        "years_positive_vs_twin": int((d > 0).sum()), "years_positive_vs_const": int((dc > 0).sum()),
        "n_years": len(yrs), "mean_annual_vs_twin": float(d.mean()), "se_annual_vs_twin": se,
        "t_annual_vs_twin": float(d.mean() / se) if se == se and se > 0 else None,
        "mde_annual_vs_twin": 2.8 * se if se == se else None,
        "loo_worst_mean_annual_vs_twin": float(min(loo)),
        "by_year_vs_twin": {int(y): float(v) for y, v in zip(yrs, d)},
    }


VARIANTS = [
    {"trigger": t, "exit": e, "base": 0.8, "step": 0.1, "cap": 1.0, "hold": 20}
    for t in ("dip3", "dip1") for e in ("trim", "decay")
]


def load_etf(sym: str) -> pd.DataFrame:
    b = pd.read_parquet(RT / "prices_deep" / "bars.parquet", columns=["symbol", "date", "close"],
                        filters=[("symbol", "==", sym)])
    b["date"] = pd.to_datetime(b["date"])
    if getattr(b["date"].dt, "tz", None) is not None:
        b["date"] = b["date"].dt.tz_localize(None)
    b["date"] = b["date"].dt.normalize()
    b = b.sort_values("date").drop_duplicates("date", keep="last")
    b["r"] = b["close"].pct_change()
    return b.dropna(subset=["r"]).reset_index(drop=True)


def _ff() -> pd.DataFrame:
    ff = pd.read_parquet(RT / "wrds" / "ff_factors_daily.parquet")
    dc = [c for c in ff.columns if "date" in c.lower()][0]
    ff = ff.rename(columns={dc: "date"})
    ff["date"] = pd.to_datetime(ff["date"])
    for c in ("mktrf", "rf"):
        ff[c] = ff[c].astype(float)
    if ff["mktrf"].abs().max() > 1.0:
        ff[["mktrf", "rf"]] = ff[["mktrf", "rf"]] / 100.0
    return ff.sort_values("date")


def rf_daily(dates) -> np.ndarray:
    s = _ff().set_index("date")["rf"]
    return s.reindex(pd.to_datetime(pd.Series(dates).values)).ffill().fillna(0.0).to_numpy()


def ff_market() -> pd.DataFrame:
    m = _ff()[["date", "mktrf", "rf"]].copy()
    m["r"] = m["mktrf"] + m["rf"]
    return m[m["date"] >= "1964-01-01"].reset_index(drop=True)


def stocks(a, rng) -> list:
    """Each liquid-500 name (chosen per 5-year block on the PRIOR year's dollar volume) gets the overlay."""
    wr = RT / "wrds"
    blocks = [(1995, 1999), (2000, 2004), (2005, 2009), (2010, 2014), (2015, 2019), (2020, 2024)]
    out = []
    variants = VARIANTS + [{"trigger": "dip3_sigma", "exit": e, "base": 0.8, "step": 0.1, "cap": 1.0,
                            "hold": 20} for e in ("trim", "decay")]
    for (y0, y1) in blocks:
        prev = pd.read_parquet(wr / f"crsp_dsf_{y0 - 1}.parquet", columns=["permno", "prc", "vol"])
        prev["dv"] = prev["prc"].abs() * prev["vol"]
        top = prev.groupby("permno")["dv"].median().nlargest(a.stocks).index.to_numpy()
        del prev
        frames = [pd.read_parquet(wr / f"crsp_dsf_{y}.parquet", columns=["permno", "date", "ret"],
                                  filters=[("permno", "in", top.tolist())]) for y in range(y0, y1 + 1)]
        d = pd.concat(frames)
        del frames
        d["date"] = pd.to_datetime(d["date"])
        d["ret"] = pd.to_numeric(d["ret"], errors="coerce")
        wide = d.pivot_table(index="date", columns="permno", values="ret").sort_index()
        del d
        rf = rf_daily(wide.index)
        yrs = wide.index.year.to_numpy()
        for v in variants:
            res = []
            for pm in wide.columns:
                r = wide[pm].to_numpy(float)
                ok = np.isfinite(r)
                if ok.sum() < 252:
                    continue
                first = int(np.argmax(ok))
                last = len(r) - int(np.argmax(ok[::-1]))
                rr = np.nan_to_num(r[first:last])
                sig = pd.Series(rr).rolling(63, min_periods=40).std().to_numpy()
                row = evaluate(str(pm), rr, rf[first:last], yrs[first:last], sig, variant=v,
                               twins=a.stock_twins, rng=rng, cost=a.stock_cost_bps / 1e4)
                res.append((row["vs_twin_cagr"], row["vs_const_cagr"], row["timing_percentile_in_twins"],
                            row["cagr_overlay"], row["cagr_buy_hold"], row["n_adds"],
                            row["timing_value"] - row["twin_timing_value_median"]))
            arr = np.array(res)
            s = {"block": f"{y0}-{y1}", **v, "n_names": int(len(arr)),
                 "mean_vs_twin_cagr": float(arr[:, 0].mean()), "median_vs_twin_cagr": float(np.median(arr[:, 0])),
                 "share_names_beating_twin": float((arr[:, 0] > 0).mean()),
                 "mean_vs_const_cagr": float(arr[:, 1].mean()),
                 "share_names_beating_const": float((arr[:, 1] > 0).mean()),
                 "mean_timing_percentile_in_twins": float(arr[:, 2].mean()),
                 "mean_timing_vs_twin_timing": float(arr[:, 6].mean()),
                 "share_names_timing_beats_twin": float((arr[:, 6] > 0).mean()),
                 "mean_cagr_overlay": float(arr[:, 3].mean()), "mean_cagr_buy_hold": float(arr[:, 4].mean()),
                 "mean_adds": float(arr[:, 5].mean())}
            out.append(s)
            print(f"stocks {y0}-{y1} {v['trigger']:<10} {v['exit']:<5} n={s['n_names']} vs twin mean "
                  f"{100*s['mean_vs_twin_cagr']:+.2f}%/y med {100*s['median_vs_twin_cagr']:+.2f} "
                  f"share>0 {s['share_names_beating_twin']:.2f} vs const {100*s['mean_vs_const_cagr']:+.2f} "
                  f"timing-vs-twin {100*s['mean_timing_vs_twin_timing']:+.2f} share {s['share_names_timing_beats_twin']:.2f} "
                  f"pct {s['mean_timing_percentile_in_twins']:.0f}", flush=True)
        del wide
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--twins", type=int, default=200)
    ap.add_argument("--etf-cost-bps", type=float, default=2.0)
    ap.add_argument("--stock-cost-bps", type=float, default=10.0)
    ap.add_argument("--stocks", type=int, default=500)
    ap.add_argument("--stock-twins", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261111)
    ap.add_argument("--skip-stocks", action="store_true")
    a = ap.parse_args(argv)
    run_id = f"dip_add_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    print("RUN", run_id, "pid", os.getpid(), flush=True)
    rng = np.random.default_rng(a.seed)
    t0 = time.time()
    rows, inputs = [], {}
    for p in (RT / "prices_deep" / "bars.parquet", RT / "wrds" / "ff_factors_daily.parquet"):
        st = p.stat()
        inputs[str(p)] = {"bytes": st.st_size,
                          "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
    series = {}
    for sym in ("SPY", "QQQ"):
        b = load_etf(sym)
        series[sym] = (b["r"].to_numpy(float), rf_daily(b["date"]), b["date"].dt.year.to_numpy())
        inputs[sym] = {"first": str(b["date"].min().date()), "last": str(b["date"].max().date()),
                       "n": int(len(b)), "max_abs_daily_ret": float(b["r"].abs().max())}
    m = ff_market()
    series["FF_VW_market_1964_2024"] = (m["r"].to_numpy(float), m["rf"].to_numpy(float),
                                        m["date"].dt.year.to_numpy())
    inputs["FF_VW_market"] = {"first": str(m["date"].min().date()), "last": str(m["date"].max().date()),
                              "n": int(len(m))}
    print(json.dumps(inputs, indent=1), flush=True)
    for name, (r, rf, yrs) in series.items():
        for v in VARIANTS:
            row = evaluate(name, r, rf, yrs, None, variant=v, twins=a.twins, rng=rng,
                           cost=a.etf_cost_bps / 1e4)
            rows.append(row)
            print(f"{name:<24} {v['trigger']:<5} {v['exit']:<5} adds {row['n_adds']:>4} avgw {row['avg_weight']:.3f} | "
                  f"ovl {100*row['cagr_overlay']:.2f} const {100*row['cagr_const_avg_weight']:.2f} "
                  f"twin {100*row['cagr_twin_median']:.2f} [{100*row['cagr_twin_p10']:.2f},{100*row['cagr_twin_p90']:.2f}] "
                  f"BH {100*row['cagr_buy_hold']:.2f} | pct {row['overlay_percentile_in_twins']:.0f} "
                  f"yrs+ {row['years_positive_vs_twin']}/{row['n_years']} vsConst+ {row['years_positive_vs_const']} "
                  f"LOO {100*row['loo_worst_mean_annual_vs_twin']:+.2f} MDE {100*(row['mde_annual_vs_twin'] or 0):.2f} | "
                  f"TIMING ovl {100*row['timing_value']:+.2f} twins med {100*row['twin_timing_value_median']:+.2f} "
                  f"[{100*row['twin_timing_value_p10']:+.2f},{100*row['twin_timing_value_p90']:+.2f}] pct {row['timing_percentile_in_twins']:.0f} "
                  f"twin avgw {row['twin_avg_weight_median']:.3f}",
                  flush=True)
    stock_rows = [] if a.skip_stocks else stocks(a, rng)
    rec = {"run_id": run_id, "pid": os.getpid(), "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "args": vars(a), "inputs": inputs, "variants": VARIANTS,
           "variants_already_tried_before_tonight": 24,
           "notes": "ETF closes from prices_deep are NOT dividend-adjusted; both arms hold the instrument. "
                    "Execution at the next close. Twin = same number of trigger days on random sessions, "
                    "same exit rule (the trim exit keeps the REAL bounce rule). Single stocks: CRSP total "
                    "return, no delisting return added; a name's series ends at its last trade.",
           "etf_rows": rows, "stock_summary": stock_rows, "elapsed_s": round(time.time() - t0, 1)}
    out = OUT / f"{run_id}.json"
    tmp = OUT / f"{run_id}.json.tmp"
    tmp.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    tmp.replace(out)
    print("DONE", out, f"{time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
