"""Grade the owner's frozen rebound forecast (CH-45; replay section 4, 2026-11-14).

    python -m scripts.owner_rebound_forecast --data-root <optimus> --baseline <forecast_owner_rebound_baseline.csv>

Claim: the equal-weight of the 22 high-beta fleet books beats SPY from the
2026-11-13 close at the 21st session (2026-12-15) and the 63rd (2027-02-17), IF
SPY is up over the same horizon. Graded two ways: vs SPY (what was said) and vs
beta x SPY (whether it was more than beta). Before a grade date this prints
NOT_DUE with the running state; it never prints a verdict early. Read only;
writes nothing unless --out is given (a receipt JSON outside the data root).

Book NAVs are the books' frozen weights held from their asof close (no
rebalancing; cash at 0), the reconstruction the replay validated against the
real daily NAVs (median corr 1.000). Foreign listings come from
llm_portfolio/global_bars.parquet, forward-filled onto the SPY calendar (<= 5 days).
Exit: 0 ok (NOT_DUE included), 2 refused, 1 crash.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import config as _config  # noqa: E402

BOOKS_REL = "llm_portfolio/books.jsonl"
GLOBAL_REL = "llm_portfolio/global_bars.parquet"
BARS_REL = "prices_2025_26/bars.parquet"


class ForecastRefused(RuntimeError):
    """An input needed to grade is missing or inconsistent: refused, never guessed."""


def book_label(r: dict) -> str:
    """The replay's label rule (s4_books.py)."""
    return r["name"] if r["name"].endswith(r["asof"]) or "2026-" in r["name"] else f"{r['name']}_{r['asof']}"


def weights_of(r: dict) -> dict:
    w: dict = {}
    for p in r["positions"]:
        if p.get("weight", 0) > 0 and p["ticker"] != "CASH":
            w[p["ticker"]] = w.get(p["ticker"], 0.0) + float(p["weight"])
    return w


def book_nav(w: dict, close: pd.DataFrame, start: pd.Timestamp) -> tuple[pd.Series, float]:
    """NAV (start close = 1) of frozen weights held from `start`; returns the share
    of weight that had a price at `start` (unpriced weight is held flat as cash)."""
    base = close.loc[start]
    nav = pd.Series(1.0 - sum(w.values()), index=close.index)
    priced = 0.0
    for t, v in w.items():
        if t in close.columns and np.isfinite(base.get(t, np.nan)) and base[t] > 0:
            nav = nav + v * (close[t].ffill() / base[t]).fillna(1.0)
            priced += v
        else:
            nav = nav + v
    return nav[nav.index >= start], priced / sum(w.values()) if w else 0.0


def grade(*, sessions_after: list[pd.Timestamp], book_ratio: dict[str, float], beta: dict[str, float],
          spy_ret: float, horizon: int, grade_date: pd.Timestamp, asof: pd.Timestamp) -> dict:
    """One horizon. NOT_DUE until both the session count and the date are reached."""
    ew = float(np.mean([v - 1.0 for v in book_ratio.values()]))
    vs_beta = float(np.mean([book_ratio[b] - 1.0 - beta[b] * spy_ret for b in book_ratio]))
    state = {"horizon_sessions": horizon, "grade_date": grade_date.date().isoformat(),
             "sessions_elapsed": len(sessions_after), "ew_book_return": ew, "spy_return": spy_ret,
             "excess_vs_spy": ew - spy_ret, "excess_vs_beta_spy": vs_beta,
             "share_books_beat_spy": float(np.mean([v - 1.0 > spy_ret for v in book_ratio.values()]))}
    if len(sessions_after) < horizon or asof < grade_date:
        return {**state, "status": "NOT_DUE",
                "note": "running state only; no verdict before the grade date"}
    if spy_ret <= 0:
        return {**state, "status": "CONDITION_NOT_MET",
                "note": "SPY was not up over the horizon: the claim was conditional and is not graded"}
    return {**state, "status": "GRADED",
            "vs_spy": "BEAT" if ew > spy_ret else "DID_NOT_BEAT",
            "vs_beta_spy": "BEAT" if vs_beta > 0 else "DID_NOT_BEAT",
            "note": "an observation on one episode; not a skill claim"}


def load_close(data_root: Path, tickers: list[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    p = Path(data_root) / BARS_REL
    if not p.is_file():
        raise ForecastRefused(f"bars panel {p} is absent")
    need = sorted(set(tickers) | {"SPY", "QQQ", "SMH"})
    b = pd.read_parquet(p, columns=["symbol", "date", "close"],
                        filters=[("symbol", "in", need), ("date", ">=", start), ("date", "<=", end)])
    miss = set(need) - set(b["symbol"].unique())
    g = Path(data_root) / GLOBAL_REL
    if miss and g.is_file():
        gb = pd.read_parquet(g, columns=["symbol", "date", "close"])
        gb["date"] = pd.to_datetime(gb["date"])
        if getattr(gb["date"].dt, "tz", None) is not None:
            gb["date"] = gb["date"].dt.tz_localize(None)
        gb = gb[gb["symbol"].isin(miss) & (gb["date"] >= start) & (gb["date"] <= end)]
        b = pd.concat([b, gb], ignore_index=True)
    b["date"] = pd.to_datetime(b["date"]).dt.normalize()
    c = b.drop_duplicates(["symbol", "date"]).pivot(index="date", columns="symbol", values="close").sort_index()
    us = c["SPY"].dropna().index
    return c.reindex(us).ffill(limit=5)


def run(data_root: Path, baseline: Path, asof: Optional[str] = None) -> dict:
    base = pd.read_csv(baseline)
    if len(base) != 22 or not {"book", "beta_1y", "nav_1113"} <= set(base.columns):
        raise ForecastRefused(f"{baseline} is not the 22-book frozen baseline")
    rows = [json.loads(line) for line in (Path(data_root) / BOOKS_REL).open(encoding="utf8")]
    found = {}
    for r in rows:
        if r.get("kind") in ("personal", "competition") and book_label(r) in set(base["book"]):
            found.setdefault(book_label(r), r)
    if len(found) != 22:
        raise ForecastRefused(f"only {len(found)} of the 22 baseline books are in {BOOKS_REL}")
    ref = pd.Timestamp(_config.OWNER_REBOUND_FORECAST_REF_DATE)
    end = pd.Timestamp(asof) if asof else pd.Timestamp.today().normalize()
    first = min(pd.Timestamp(r["asof"]) for r in found.values()) - pd.Timedelta(days=10)
    tick = sorted({t for r in found.values() for t in weights_of(r)})
    close = load_close(data_root, tick, first, end)
    if ref not in close.index:
        raise ForecastRefused(f"no SPY bar on the reference date {ref.date()}")
    ref_closes = {k: float(close.at[ref, k]) for k in _config.OWNER_REBOUND_FORECAST_REF_CLOSES}
    ratio_now, check, coverage = {}, [], {}
    for _, b in base.iterrows():
        r = found[b["book"]]
        start = close.index[close.index <= pd.Timestamp(r["asof"])][-1]
        nav, cov = book_nav(weights_of(r), close, start)
        coverage[b["book"]] = cov
        check.append(abs(float(nav.loc[ref]) - float(b["nav_1113"])))
        ratio_now[b["book"]] = nav
    beta = dict(zip(base["book"], base["beta_1y"].astype(float)))
    after = [d for d in close.index if d > ref]
    out = {"claim": "EW of the 22 high-beta books beats SPY from the 2026-11-13 close, IF SPY is up",
           "reference_closes_declared": _config.OWNER_REBOUND_FORECAST_REF_CLOSES,
           "reference_closes_in_bars": ref_closes, "bars_through": close.index[-1].date().isoformat(),
           "nav_1113_reconstruction_abs_diff": {"median": float(np.median(check)), "max": float(np.max(check))},
           "min_weight_priced": float(min(coverage.values())), "grades": {}}
    for h, gd in sorted(_config.OWNER_REBOUND_FORECAST_GRADES.items(), key=lambda kv: int(kv[0])):
        h = int(h)
        upto = after[:h]
        at = upto[-1] if upto else ref
        spy = float(close.at[at, "SPY"]) / _config.OWNER_REBOUND_FORECAST_REF_CLOSES["SPY"] - 1.0
        rat = {k: float(v.loc[at] / v.loc[ref]) for k, v in ratio_now.items()}
        out["grades"][str(h)] = {**grade(sessions_after=upto, book_ratio=rat, beta=beta, spy_ret=spy, horizon=h,
                                         grade_date=pd.Timestamp(gd), asof=close.index[-1]),
                                 "state_at": at.date().isoformat()}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="owner_rebound_forecast", description=__doc__.splitlines()[0])
    ap.add_argument("--data-root", required=True, type=Path)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--asof", default=None)
    ap.add_argument("--out", type=Path, default=None, help="optional receipt JSON (outside the data root)")
    a = ap.parse_args(argv)
    try:
        if a.out is not None and Path(a.data_root).resolve() in Path(a.out).resolve().parents:
            raise ForecastRefused("--out is inside the data root")
        res = run(a.data_root, a.baseline, a.asof)
    except (ForecastRefused, OSError) as exc:
        print(json.dumps({"action": "REFUSED", "rc": 2, "reason": str(exc)}))
        return 2
    print(json.dumps(res, indent=1))
    if a.out is not None:
        Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
