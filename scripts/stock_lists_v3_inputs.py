"""Inputs for the stock lists v3.x builder (scripts/stock_lists_v3_build.py). Offline except `yf`. $0, no LLM.

    python -m scripts.stock_lists_v3_inputs facts --asof 2026-09-27 --names VRT,GEV,...   # -> WORK/v3_facts.json
    python -m scripts.stock_lists_v3_inputs yf    --asof 2026-09-27 --names VRT,GEV,...   # -> WORK/yf_analyst_v3.json (network: yfinance)

`facts`: per name, sigma63 / 21- and 126-session predicted |move| / 2 sigma over 126 sessions (rehearsal_book),
the five-ratio fundamentals proxy ranked within the eligible universe, liquidity band, market cap and the
EDGAR 8-K 2.02 + 91d earnings estimate. The name set = --names + every analyst-screen name (upside >= 50%,
price >= $2). `yf`: numberOfAnalystOpinions + the current-month strong-buy/buy/hold/sell counts for the
same set (resumable: names already fetched OK are skipped).
WORK = backend/data/optimus/stock_lists/<asof>/ (override with STOCK_LISTS_WORK).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def work_dir(asof: str) -> Path:
    w = Path(os.environ.get("STOCK_LISTS_WORK") or (REPO / "backend/data/optimus/stock_lists" / asof))
    w.mkdir(parents=True, exist_ok=True)
    return w


def facts(ASOF: str, SHORT: list[str]) -> Path:
    import numpy as np
    import pandas as pd
    from backend.services import rehearsal_book as RB
    from scripts.bloomberg_rehearsal_book import load_bars, OPT
    t = pd.read_parquet(OPT / "analyst/target_snapshots.parquet")
    l = t.sort_values("observed_at").groupby("ticker").tail(1)
    screen = set(l[(l.implied_upside >= 0.5) & (l.price >= 2)].ticker)
    names = sorted(set(SHORT) | screen | {"DELL", "NVDA", "PLTR", "TSLA", "HOOD", "HPQ"})
    bars = load_bars()
    U = RB.universe(bars, ASOF)
    sig = RB.sigma63(bars[bars["symbol"].isin(set(names) | set(U.index))], ASOF)
    facts = pd.read_parquet(OPT / "fundamentals_sec" / "sec_facts_history.parquet",
                            columns=["ticker", "fact", "filed", "end", "period_days", "val"])
    fund = RB.fundamentals_composite(facts, ASOF, set(U.index) | set(names))
    shares = RB.latest_shares(facts, ASOF)
    del facts
    ek = pd.read_parquet(OPT / "edgar_8k" / "eightk_items.parquet", columns=["ticker", "filing_date", "items_joined"])
    earn = RB.earnings_estimates(ek, names, ASOF, window_sessions=126)
    bb = bars[bars.date <= ASOF].sort_values("date")
    last = bb.groupby("symbol").tail(1).set_index("symbol")
    t63 = bb[bb.symbol.isin(set(names))].groupby("symbol").tail(63)
    mdv_all = (t63["close"] * t63["volume"]).groupby(t63["symbol"]).median()
    from backend.services import xs_ranker as XR
    out = {}
    for s in names:
        sd = sig.get(s)
        e = earn.get(s, {})
        ok = sd is not None and np.isfinite(sd)
        out[s] = {"sigma63": float(sd) if ok else None,
                  "move21": RB.predicted_abs_move(sd, 21) if ok else None,
                  "move126": RB.predicted_abs_move(sd, 126) if ok else None,
                  "two_sigma126": 2 * sd * math.sqrt(126) if ok else None,
                  "fund": (float(fund.loc[s, "fund_score"]) if s in fund.index and pd.notna(fund.loc[s, "fund_score"]) else None),
                  "n_legs": int(fund.loc[s, "n_legs"]) if s in fund.index else 0,
                  "in_universe": s in U.index,
                  "band": XR.liquidity_band(float(mdv_all[s])) if s in mdv_all.index else None,
                  "mdv63": float(mdv_all[s]) if s in mdv_all.index else None,
                  "close": float(last.loc[s, "close"]) if s in last.index else None,
                  "bar_date": str(last.loc[s, "date"].date()) if s in last.index else None,
                  "mcap": float(shares.get(s) * last.loc[s, "close"]) if s in shares.index and s in last.index else None,
                  "earn_status": e.get("status"), "earn_est": e.get("estimate"), "earn_session": e.get("session"),
                  "earn_why": e.get("why"), "last_202": e.get("last_202")}
    meta = {"asof": ASOF, "bars_last": str(bars.date.max().date()), "n_universe": int(len(U)), "n_names": len(names),
            "fund_ranked_within": "xs eligible universe on 2026-09-27 U names in this doc",
            "sigma": "daily log-return sd, 63 sessions to 2026-09-25 bars (rehearsal_book.sigma63)",
            "move": "sigma * sqrt(h) * sqrt(2/pi) (rehearsal_book.predicted_abs_move)",
            "earn": "EDGAR 8-K 2.02 + 91d (rehearsal_book.earnings_estimates, window 126 sessions)"}
    meta = {"asof": ASOF, "bars_last": str(bars.date.max().date()), "n_universe": int(len(U)), "n_names": len(names),
            "fund_ranked_within": "the eligible universe on the as-of date + the names in this doc",
            "sigma": "daily log-return sd, 63 sessions to the last bar (rehearsal_book.sigma63)",
            "move": "sigma * sqrt(h) * sqrt(2/pi) (rehearsal_book.predicted_abs_move)",
            "earn": "EDGAR 8-K 2.02 + 91d (rehearsal_book.earnings_estimates, window 126 sessions)"}
    p = work_dir(ASOF) / "v3_facts.json"
    json.dump({"meta": meta, "names": out}, open(p, "w"), indent=0)
    print(meta, sum(v["sigma63"] is not None for v in out.values()), sum(v["fund"] is not None for v in out.values()))
    return p


def yf_counts(ASOF: str, extra: list[str]) -> Path:
    import pandas as pd
    import yfinance as yf
    from concurrent.futures import ThreadPoolExecutor
    df = pd.read_parquet(REPO / "backend/data/optimus/analyst/target_snapshots.parquet")
    l = df.sort_values("observed_at").groupby("ticker").tail(1)
    names = sorted(set(l[(l.implied_upside >= 0.5) & (l.price >= 2)].ticker.tolist()) | set(extra))
    out_path = work_dir(ASOF) / "yf_analyst_v3.json"
    cache = json.load(open(out_path)) if out_path.exists() else {}
    todo = [t for t in names if t not in cache or cache[t].get("status") != "ok"]
    print(len(names), "screened;", len(todo), "to fetch", flush=True)
    def one(t):
        rec = {"status": "err", "fetched_utc": pd.Timestamp.utcnow().isoformat()}
        for attempt in range(3):
            try:
                tk = yf.Ticker(t)
                info = tk.info or {}
                rec.update(n=info.get("numberOfAnalystOpinions"), key=info.get("recommendationKey"),
                           mean=info.get("recommendationMean"), yf_price=info.get("currentPrice") or info.get("regularMarketPrice"),
                           yf_target_mean=info.get("targetMeanPrice"), name=info.get("shortName"))
                try:
                    r = tk.recommendations
                    if r is not None and len(r):
                        row = r[r["period"] == "0m"].iloc[0] if "period" in r else r.iloc[0]
                        rec["counts"] = {k: int(row[k]) for k in ["strongBuy", "buy", "hold", "sell", "strongSell"] if k in row}
                except Exception as e:
                    rec["counts_err"] = str(e)[:100]
                rec["status"] = "ok"; break
            except Exception as e:
                rec["err"] = str(e)[:200]; time.sleep(3 * (attempt + 1))
        time.sleep(0.5)
        return t, rec
    done = 0
    with ThreadPoolExecutor(4) as ex:
        for t, rec in ex.map(one, todo):
            cache[t] = rec; done += 1
            if done % 25 == 0:
                json.dump(cache, open(out_path, "w")); print(done, flush=True)
    json.dump(cache, open(out_path, "w"))
    print("DONE", sum(v["status"] == "ok" for v in cache.values()), flush=True)
    return out_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10))[0])
    ap.add_argument("cmd", choices=["facts", "yf"])
    ap.add_argument("--asof", required=True)
    ap.add_argument("--names", required=True, help="comma list: the shortlist")
    a = ap.parse_args(argv)
    names = [x.strip().upper() for x in a.names.split(",") if x.strip()]
    (facts if a.cmd == "facts" else yf_counts)(a.asof, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
