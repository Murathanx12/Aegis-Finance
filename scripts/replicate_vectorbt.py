"""A RE-IMPLEMENTATION OF THE ARITHMETIC for the library's top-10 -- NOT an independent engine.

Review 2026-09-26 (chunks D+E), adjudicated: this shares the factory's holdings,
weights, fill convention, no-drift assumption and cost formula; it recomputes
the period returns from raw bars. Agreement to 1e-8 is the signature of shared
conventions, not evidence of realism. An independent check re-selects from raw
closes with drifting weights (clean-room `mom_12_1`), a second vendor, or LEAN.

    python -m scripts.replicate_vectorbt                       # latest top10_for_replication_<run_id>.json
    python -m scripts.replicate_vectorbt --file <path> --date 2026-09-26

Design: `docs/research_notes/2026-09-26/research_library_expansion_and_lean.md`
Part 2.5. The input is `strategy_library/top10_for_replication_<date>.json`
(the factory's holdings, weights and monthly series). This script NEVER imports
`strategy_library` or the factory: it reads raw bars and the file's own
declared conventions, and recomputes

  * each held name's period return from the bars, with the file's
    `fill_convention` (decide at the month-end close; enter at the NEXT
    session's open; exit at the open of the session after the next decision
    date; a name whose bars stop inside the period is filled at its last close
    x (1 + delist return); a name not trading on the decision date earns 0);
  * the PORTFOLIO accounting in vectorbt (`Portfolio.from_orders`,
    `size_type="targetpercent"`, one order row per period entry, cash shared,
    zero fees) on a synthetic price index per name built from those period
    returns -- and the same weighted sum in plain pandas beside it;
  * the COST in pandas, because vectorbt cannot express the file's convention
    (half the band round trip per side on the weight traded at each
    REBALANCE, the band fixed at the date the name was bought, drift between
    rebalances untraded and uncharged -- vectorbt would charge the monthly
    re-targeting of a quarterly book). Said here rather than discovered.

The band of a name is its trailing 63-session median dollar volume (close x
volume, >= 40 finite closes) at the decision date, cut at the file's
`band_boundaries_median_dollar_vol`.

Per strategy: corr and mean |diff| of NET monthly returns vs the file. AGREE
needs corr >= 0.98 AND mean |diff| <= 15 bps/month; anything else is a
DISAGREEMENT, classified into exactly one of REBALANCE_TIMING /
COST_MODEL_MISMATCH / UNIVERSE_MISMATCH / DATA_MISALIGNMENT /
IMPLEMENTATION_BUG by the declared rules in `classify`, printed, never averaged
away. Output: `strategy_library/replication_vectorbt_<run_id>.json` (the input's
run id; `<date>` for a pre-run-id input).

What this is NOT: independent of pandas/numpy (the weaker form of
independence the design names), nor a re-run of the selection -- the holdings
are the file's. It tests EXECUTION and ACCOUNTING agreement.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LIB_DIR = REPO / "backend" / "data" / "optimus" / "strategy_library"
AGREE_CORR = 0.98
AGREE_MAD = 0.0015
BUCKETS = ("REBALANCE_TIMING", "COST_MODEL_MISMATCH", "UNIVERSE_MISMATCH",
           "DATA_MISALIGNMENT", "IMPLEMENTATION_BUG")
MARKET = "SPY"


# ─────────────────────────────── bars ───────────────────────────────────────

def bar_paths() -> list[Path]:
    deep = REPO / "backend" / "data" / "optimus" / "prices_deep"
    ps = [deep / "bars.parquet", deep / "bars_delisted.parquet"]
    return [p for p in ps if p.exists()]


def load_long(symbols: set, *, start: str = "2016-01-01",
              paths: Optional[list] = None) -> pd.DataFrame:
    cols = ["symbol", "date", "open", "close", "volume"]
    filt = [("symbol", "in", sorted(symbols | {MARKET})), ("date", ">=", pd.Timestamp(start))]
    fr = [pd.read_parquet(p, columns=cols, filters=filt) for p in (paths or bar_paths())]
    df = pd.concat(fr, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates(["symbol", "date"], keep="first")


def wide(df: pd.DataFrame) -> dict:
    """(sessions x symbols) arrays on the MARKET's calendar; non-positive prices
    are missing, missing volume is 0."""
    cal = np.sort(df.loc[df["symbol"] == MARKET, "date"].unique())
    df = df[df["date"].isin(cal)]
    syms = np.array(sorted(df["symbol"].unique()))
    si = np.searchsorted(syms, df["symbol"].to_numpy())
    di = np.searchsorted(cal, df["date"].to_numpy())
    out = {"dates": pd.DatetimeIndex(cal), "symbols": syms}
    for c in ("open", "close", "volume"):
        a = np.full((len(cal), len(syms)), np.nan)
        a[di, si] = df[c].to_numpy(dtype=float)
        bad = ~np.isfinite(a) | (a <= 0)
        a[bad] = 0.0 if c == "volume" else np.nan
        out[c] = a
    C = out["close"]
    out["close_ff"] = pd.DataFrame(C).ffill().to_numpy()
    fin = np.isfinite(C)
    T = len(cal)
    out["last_valid"] = np.where(fin.any(axis=0), T - 1 - np.argmax(fin[::-1], axis=0), -1)
    return out


def month_end_indices(dates: pd.DatetimeIndex) -> np.ndarray:
    s = pd.Series(np.arange(len(dates)), index=dates)
    return s.groupby(dates.to_period("M")).max().to_numpy()


def band_of(mdv: float, bounds: dict) -> str:
    if mdv is None or not np.isfinite(mdv):
        return "small"
    if mdv >= bounds.get("mega", 1e9):
        return "mega"
    if mdv >= bounds.get("large", 1e8):
        return "large"
    if mdv >= bounds.get("mid", 2e7):
        return "mid"
    return "small"


def _bounds(cost_model: dict) -> dict:
    """Parse ">= 1e9"-style boundaries from the file; the numbers are the file's."""
    out = {}
    for k, v in (cost_model.get("band_boundaries_median_dollar_vol") or {}).items():
        v = str(v).replace(">=", "").replace("<", "").strip()
        try:
            out[k] = float(v)
        except ValueError:
            pass
    out.pop("small", None)
    return out


def mdv_at(W: dict, i: int, j: int, window: int = 63, need: int = 40) -> float:
    C, V = W["close"][max(0, i - window + 1): i + 1, j], W["volume"][max(0, i - window + 1): i + 1, j]
    ok = np.isfinite(C)
    if ok.sum() < need:
        return float("nan")
    return float(np.median(C[ok] * V[ok]))


# ────────────────────────────── one strategy ────────────────────────────────

def period_returns(W: dict, dec_dates: list, held: list, *, delist_return: float) -> tuple:
    """R[p, name] for every period p and held name, by the file's fill convention.
    Returns (R dict-of-dicts, n_dead per period)."""
    dates, syms = W["dates"], W["symbols"]
    col = {s: j for j, s in enumerate(syms)}
    me = month_end_indices(dates)
    O, C, Cff, lv = W["open"], W["close"], W["close_ff"], W["last_valid"]
    T = len(dates)
    R, dead = [], []
    for d, names in zip(dec_dates, held):
        i = int(np.searchsorted(dates, pd.Timestamp(d)))
        nxt = me[me > i]
        rp, nd = {}, 0
        if i >= T or dates[i] != pd.Timestamp(d) or not len(nxt) or nxt[0] + 1 > T - 1:
            R.append({n: np.nan for n in names})
            dead.append(0)
            continue
        e0, e1 = i + 1, int(nxt[0]) + 1
        for n in names:
            j = col.get(n)
            if j is None or not np.isfinite(C[i, j]):
                rp[n] = 0.0                       # not trading on the decision date: cash
                continue
            entry = O[e0, j] if np.isfinite(O[e0, j]) else C[i, j]
            died = lv[j] < e1
            ex = Cff[e1, j] * (1.0 + delist_return) if died else (
                O[e1, j] if np.isfinite(O[e1, j]) else Cff[e1, j])
            r = ex / entry - 1.0
            rp[n] = float(r) if np.isfinite(r) else 0.0
            nd += int(died)
        R.append(rp)
        dead.append(nd)
    return R, dead


def holdings_path(row: dict) -> tuple[list, list, list]:
    """(decision dates, held names per period, weights per period), holding the
    last rebalance's weights through non-rebalance months (no drift)."""
    series = row["monthly_return_series"]
    hs, ws = row["held_symbols_by_date"], row["weights_by_date"]
    reb = sorted(hs)
    dd, names, wts = [], [], []
    cur_n, cur_w = [], []
    for x in series:
        d = x["date"]
        if d in hs:
            cur_n, cur_w = list(hs[d]), [float(v) for v in ws[d]]
        dd.append(d)
        names.append(cur_n)
        wts.append(cur_w)
    return dd, names, wts


def gross_vectorbt(R: list, names: list, wts: list) -> tuple[np.ndarray, str]:
    """Portfolio accounting in vectorbt: one targetpercent order row per period."""
    import vectorbt as vbt
    universe = sorted({n for ns in names for n in ns})
    ci = {n: k for k, n in enumerate(universe)}
    P = np.ones((len(R) + 1, len(universe)))
    S = np.zeros((len(R) + 1, len(universe)))
    for p, (rp, ns, ws) in enumerate(zip(R, names, wts)):
        step = np.zeros(len(universe))
        for n, w in zip(ns, ws):
            step[ci[n]] = rp.get(n, 0.0) if np.isfinite(rp.get(n, np.nan)) else 0.0
            S[p, ci[n]] = w
        P[p + 1] = P[p] * (1.0 + step)
    S[-1, :] = np.nan                         # no order after the last period
    idx = pd.date_range("2000-01-01", periods=len(R) + 1, freq="D")
    pf = vbt.Portfolio.from_orders(
        close=pd.DataFrame(P, index=idx, columns=universe),
        size=pd.DataFrame(S, index=idx, columns=universe), size_type="targetpercent",
        group_by=True, cash_sharing=True, call_seq="auto", init_cash=1e9, fees=0.0, freq="D")
    v = pf.value().to_numpy(dtype=float)
    return v[1:] / v[:-1] - 1.0, f"vectorbt {vbt.__version__} Portfolio.from_orders(targetpercent)"


def gross_pandas(R: list, names: list, wts: list) -> np.ndarray:
    return np.array([sum(w * (rp.get(n, 0.0) if np.isfinite(rp.get(n, np.nan)) else 0.0)
                         for n, w in zip(ns, ws)) for rp, ns, ws in zip(R, names, wts)])


def costs(W: dict, row: dict, dec_dates: list, cost_model: dict) -> np.ndarray:
    """The file's convention, in pandas: half the band round trip per side on
    the weight traded at each rebalance; the band is the name's at the date it
    was bought."""
    rt = cost_model["bands_bps_round_trip"]
    bounds = _bounds(cost_model)
    col = {s: j for j, s in enumerate(W["symbols"])}
    hs, ws = row["held_symbols_by_date"], row["weights_by_date"]
    held, held_rt = {}, {}
    out = []
    for d in dec_dates:
        c = 0.0
        if d in hs:
            i = int(np.searchsorted(W["dates"], pd.Timestamp(d)))
            new = {n: float(w) for n, w in zip(hs[d], ws[d])}
            new_rt = {}
            for n in new:
                j = col.get(n)
                new_rt[n] = rt[band_of(mdv_at(W, i, j) if j is not None else float("nan"), bounds)]
            for n, w in new.items():
                dw = w - held.get(n, 0.0)
                if dw > 0:
                    c += dw * new_rt[n] / 2.0
            for n, w in held.items():
                dw = w - new.get(n, 0.0)
                if dw > 0:
                    c += dw * held_rt.get(n, rt["small"]) / 2.0
            held, held_rt = new, new_rt
        out.append(c / 1e4)
    return np.array(out)


def compare(file_net: np.ndarray, ours: np.ndarray, dates: list) -> dict:
    ok = np.isfinite(file_net) & np.isfinite(ours)
    a, b = file_net[ok], ours[ok]
    d = np.abs(a - b)
    corr = float(np.corrcoef(a, b)[0, 1]) if len(a) >= 3 and a.std() > 0 and b.std() > 0 else (
        1.0 if len(a) and np.allclose(a, b) else float("nan"))
    k = int(np.argmax(d)) if len(d) else 0
    dd = [x for x, m in zip(dates, ok) if m]
    mad = float(d.mean()) if len(d) else float("nan")
    return {"n_months_compared": int(ok.sum()), "corr_net_monthly": round(corr, 6),
            "mean_abs_diff_net_monthly": round(mad, 8),
            "max_abs_diff_net_monthly": round(float(d.max()), 8) if len(d) else None,
            "max_abs_diff_date": dd[k] if len(d) else None,
            "verdict": ("AGREE" if (np.isfinite(corr) and corr >= AGREE_CORR and mad <= AGREE_MAD)
                        else "DISAGREEMENT")}


def classify(series: list, ours: dict, unpriced: list) -> dict:
    """Exactly one bucket, first rule that fires (declared order):

    UNIVERSE_MISMATCH  a held name has no bars in this engine at all;
    COST_MODEL_MISMATCH the mean |cost diff| exceeds the mean |gross diff|;
    DATA_MISALIGNMENT  >= 50% of the |net diff| sits on months with a delisting fill;
    REBALANCE_TIMING   >= 80% of the |net diff| sits on rebalance months while
                       rebalance months are < 80% of all months;
    IMPLEMENTATION_BUG none of the above.
    Evidence for every rule is returned beside the bucket.
    """
    fn = np.array([x["net"] for x in series], dtype=float)
    fg = np.array([x["gross"] for x in series], dtype=float)
    fc = np.array([x["cost"] for x in series], dtype=float)
    dn = np.abs(fn - ours["net"])
    dg = np.abs(fg - ours["gross"])
    dc = np.abs(fc - ours["cost"])
    ok = np.isfinite(dn)
    tot = float(dn[ok].sum()) or 1e-12
    dead = np.array([x.get("n_delisted", 0) > 0 for x in series])
    reb = np.array([bool(x.get("rebalanced")) for x in series])
    ev = {"unpriced_names": unpriced[:20],
          "mean_abs_gross_diff": float(np.nanmean(dg)), "mean_abs_cost_diff": float(np.nanmean(dc)),
          "share_of_diff_on_delisting_months": float(dn[ok & dead].sum() / tot),
          "share_of_diff_on_rebalance_months": float(dn[ok & reb].sum() / tot),
          "share_of_months_rebalanced": float(reb.mean()) if len(reb) else None}
    if unpriced:
        b = "UNIVERSE_MISMATCH"
    elif ev["mean_abs_cost_diff"] > ev["mean_abs_gross_diff"]:
        b = "COST_MODEL_MISMATCH"
    elif ev["share_of_diff_on_delisting_months"] >= 0.5:
        b = "DATA_MISALIGNMENT"
    elif ev["share_of_diff_on_rebalance_months"] >= 0.8 and (ev["share_of_months_rebalanced"] or 1) < 0.8:
        b = "REBALANCE_TIMING"
    else:
        b = "IMPLEMENTATION_BUG"
    return {"bucket": b, "evidence": {k: (round(v, 8) if isinstance(v, float) else v)
                                      for k, v in ev.items()}}


def replicate_row(row: dict, W: dict, cost_model: dict, *, delist_return: float,
                  use_vectorbt: bool = True) -> dict:
    dd, names, wts = holdings_path(row)
    R, dead = period_returns(W, dd, names, delist_return=delist_return)
    gp = gross_pandas(R, names, wts)
    engine = "pandas (weighted sum)"
    gv = None
    if use_vectorbt:
        try:
            gv, engine = gross_vectorbt(R, names, wts)
        except Exception as e:                             # noqa: BLE001 -- printed, not hidden
            engine = f"pandas (vectorbt refused: {type(e).__name__}: {e})"
    gross = gv if gv is not None else gp
    c = costs(W, row, dd, cost_model)
    net = gross - c
    series = row["monthly_return_series"]
    fnet = np.array([x["net"] for x in series], dtype=float)
    cmp_ = compare(fnet, net, dd)
    have = set(W["symbols"])
    unpriced = sorted({n for ns in names for n in ns} - have)
    out = {"id": row["id"], "engine_gross": engine,
           "engine_fill": "pandas, from raw bars, by the file's fill_convention",
           "engine_cost": "pandas, by the file's cost_model (vectorbt cannot express it)",
           "vectorbt_vs_pandas_gross_max_abs_diff": (round(float(np.nanmax(np.abs(gv - gp))), 10)
                                                     if gv is not None else None),
           **cmp_,
           "gross": {"corr": compare(np.array([x["gross"] for x in series], float), gross, dd)["corr_net_monthly"],
                     "mean_abs_diff": round(float(np.nanmean(np.abs(
                         np.array([x["gross"] for x in series], float) - gross))), 8)},
           "cost": {"mean_abs_diff": round(float(np.nanmean(np.abs(
               np.array([x["cost"] for x in series], float) - c))), 8),
               "file_mean": round(float(np.mean([x["cost"] for x in series])), 8),
               "ours_mean": round(float(np.mean(c)), 8)},
           "n_delisting_fills_ours": int(sum(dead)),
           "n_delisting_fills_file": int(sum(x.get("n_delisted", 0) for x in series)),
           "unpriced_names": unpriced[:20],
           "monthly_return_series": [{"date": d, "gross": round(float(g), 10),
                                      "cost": round(float(k), 10), "net": round(float(n), 10)}
                                     for d, g, k, n in zip(dd, gross, c, net)]}
    if cmp_["verdict"] != "AGREE":
        out["disagreement"] = classify(series, {"net": net, "gross": gross, "cost": c}, unpriced)
    return out


WHAT_THIS_IS = ("re-implementation of the arithmetic from raw bars, not an independent engine "
                "(shares holdings, fills, cost formula)")


def latest_input(lib_dir: Path = LIB_DIR) -> Path:
    """The newest run-id'd top-10 file; a date-named file only when no run id exists."""
    ps = sorted(lib_dir.glob("top10_for_replication_*T*Z.json"))
    if not ps:
        ps = sorted(lib_dir.glob("top10_for_replication_*.json"))
    if not ps:
        raise FileNotFoundError(f"no top10_for_replication_*.json under {lib_dir}")
    return ps[-1]


def run(doc: dict, W: dict, *, use_vectorbt: bool = True) -> dict:
    dr = _delist_return(doc)
    rows = [replicate_row(r, W, doc["cost_model"], delist_return=dr, use_vectorbt=use_vectorbt)
            for r in doc["rows"]]
    return {"schema": "strategy_library.replication_vectorbt/1", "date": doc.get("date"),
            "run_id": doc.get("run_id"), "what_this_is": WHAT_THIS_IS,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "input": doc.get("_path"), "tolerance": {"corr_net_monthly_min": AGREE_CORR,
                                                     "mean_abs_diff_net_monthly_max": AGREE_MAD},
            "delist_return": dr, "cost_model": doc["cost_model"],
            "fill_convention": doc.get("fill_convention"),
            "n_agree": sum(r["verdict"] == "AGREE" for r in rows), "n_rows": len(rows),
            "rows": rows}


def _delist_return(doc: dict) -> float:
    """The number is in the file's fill_convention text: 'last close x (1 + -0.3)'."""
    import re
    m = re.search(r"\(1 \+ (-?[0-9.]+)\)", str(doc.get("fill_convention") or ""))
    if not m:
        raise ValueError("fill_convention does not declare the delisting fill")
    return float(m.group(1))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None)
    ap.add_argument("--date", default=None)
    ap.add_argument("--no-vectorbt", action="store_true")
    a = ap.parse_args(argv)
    p = Path(a.file) if a.file else latest_input()
    doc = json.loads(p.read_text(encoding="utf-8"))
    doc["_path"] = str(p.resolve().relative_to(REPO)).replace("\\", "/") if p.resolve().is_relative_to(REPO) else str(p)
    syms = {s for r in doc["rows"] for v in r["held_symbols_by_date"].values() for s in v}
    print(f"input {doc['_path']}: {len(doc['rows'])} strategies, {len(syms)} distinct names", flush=True)
    W = wide(load_long(syms))
    print(f"bars: {W['close'].shape} (sessions x symbols), through {W['dates'][-1].date()}", flush=True)
    res = run(doc, W, use_vectorbt=not a.no_vectorbt)
    day = a.date or doc.get("run_id") or doc.get("date") or str(datetime.now().date())
    out = LIB_DIR / f"replication_vectorbt_{day}.json"
    out.write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"{'id':<24} {'n':>4} {'corr':>8} {'MAD bps':>8} {'max bps':>8}  verdict / bucket")
    for r in res["rows"]:
        print(f"{r['id']:<24} {r['n_months_compared']:>4} {r['corr_net_monthly']:>8.4f} "
              f"{r['mean_abs_diff_net_monthly']*1e4:>8.2f} {(r['max_abs_diff_net_monthly'] or 0)*1e4:>8.1f}  "
              f"{r['verdict']}" + (f" / {r['disagreement']['bucket']}" if r.get('disagreement') else ""))
    print(f"gross engine: {res['rows'][0]['engine_gross']}")
    print(f"-> {out}  ({res['n_agree']}/{res['n_rows']} AGREE -- {WHAT_THIS_IS})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
