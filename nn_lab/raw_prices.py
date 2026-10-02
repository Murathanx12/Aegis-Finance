"""An unadjusted close for market cap, without the future-split leak (review F1, 2026-09-30).

Every bar file is split- AND dividend-adjusted as of its pull date, so `close x shares-as-filed`
shrank every later splitter (NVDA 2019 read as $1.9B). The fix needs close_raw(t), which must
not depend on anything after t.

Method (cheap: ~130 monthly bars per symbol, $0): pull MONTHLY bars with adjustment=raw. At each
month-end session m, ratio(m) = raw_close(m) / adjusted_close(m) = the cumulative adjustment for
every event AFTER m. For a row at t, take the latest month-end m <= t and set

    close_raw(t) = adjusted_close(t) x ratio(m).

A split after t scales adjusted_close(t) and ratio(m) by the same factor, so it cancels: no
future information (pinned by a planted-split test). A split inside (m, t] is PAST information
and leaves close_raw(t) off by that split's ratio for under a month; the receipt counts those
rows. A ratio is used only when the raw monthly close falls inside the symbol's own bar life
(a reused ticker's other company is never used) and lies in [1e-3, 1e3].

Behind `config.USE_CLOSE_RAW` (default OFF): the nightly has no monthly raw refresh yet, so a
live row would lack what training rows have (train/live skew).

    python -m nn_lab.raw_prices pull      # monthly raw bars for every symbol in the bar files
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from nn_lab import config as C

RAW_MONTHLY = C.OPTIMUS / "prices_deep" / "bars_raw_monthly.parquet"
RECEIPT = C.OPTIMUS / "prices_deep" / "raw_monthly_receipt.json"
STOP_FILE = C.OUT / "STOP_RAW_PULL"


def month_end_ratios(adj: pd.DataFrame, raw_m: pd.DataFrame) -> pd.DataFrame:
    """(symbol, m_date, ratio) at each month's LAST session of the adjusted bars.

    `raw_m`: monthly raw bars (symbol, month, close_raw) with `month` = the bar's calendar month.
    A monthly raw close is matched to the adjusted close of the last session of that month."""
    a = adj[["symbol", "date", "close"]].copy()
    a["month"] = a["date"].dt.to_period("M")
    # the month's last SESSION on the market calendar: a segment whose own last bar in the
    # month is earlier (it died, or another company took the ticker) gets no ratio that month
    mkt_last = a.groupby("month")["date"].max()
    last = a.sort_values("date").groupby(["symbol", "month"]).tail(1)
    last = last[last["date"] >= last["month"].map(mkt_last) - pd.Timedelta(days=3)]
    last["base"] = last["symbol"].astype(str).str.split("#").str[0]
    r = raw_m.rename(columns={"symbol": "base"}).copy()
    r["month"] = pd.PeriodIndex(r["month"], freq="M")
    m = last.merge(r[["base", "month", "close_raw"]], on=["base", "month"], how="inner")
    m["ratio"] = m["close_raw"] / m["close"]
    m = m[(m["ratio"] > 1e-3) & (m["ratio"] < 1e3)]
    return m[["symbol", "date", "ratio"]].rename(columns={"date": "m_date"}).sort_values(["symbol", "m_date"])


def attach_close_raw(bars: pd.DataFrame, ratios: pd.DataFrame) -> pd.DataFrame:
    """close_raw(t) = close(t) x ratio(latest month-end <= t); NaN before the first ratio."""
    b = bars.copy()
    b["_i"] = np.arange(len(b))
    left = b[["symbol", "date", "_i"]].sort_values("date")
    right = ratios.sort_values("m_date")
    m = pd.merge_asof(left, right, left_on="date", right_on="m_date", by="symbol", direction="backward",
                      allow_exact_matches=True).sort_values("_i")
    b["close_raw"] = b["close"].to_numpy(dtype="float64") * m["ratio"].to_numpy(dtype="float64")
    return b.drop(columns=["_i"])


def pull(symbols: list[str], kid: str, sec: str, get, workers: int = 8, batch: int = 20) -> pd.DataFrame:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    chunks = [symbols[i:i + batch] for i in range(0, len(symbols), batch)]

    def one(chunk):
        rows, token = [], None
        for _ in range(100):
            for attempt in range(4):
                try:
                    d = get("/v2/stocks/bars", {"symbols": ",".join(chunk), "start": "2015-12-01",
                                                "timeframe": "1Month", "adjustment": "raw", "limit": 10000,
                                                "feed": "sip", "page_token": token}, kid, sec)
                    break
                except Exception:                                   # noqa: BLE001
                    if attempt == 3:
                        return rows, chunk
                    time.sleep(2.0 * (attempt + 1))
            for s, bars in (d.get("bars") or {}).items():
                for b in bars:
                    rows.append((s, b["t"][:7], b["c"]))
            token = d.get("next_page_token")
            if not token:
                break
        return rows, []

    out, failed, t0 = [], [], time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, c) for c in chunks]
        for i, f in enumerate(as_completed(futs), 1):
            rows, bad = f.result()
            out.extend(rows)
            failed.extend(bad)
            if i % 20 == 0:
                print(f"    {i}/{len(futs)} chunks, {len(out):,} monthly bars, {time.time() - t0:.0f}s", flush=True)
            if STOP_FILE.exists():
                print("STOP file: ending the pull early", flush=True)
                for g in futs:
                    g.cancel()
                break
    df = pd.DataFrame(out, columns=["symbol", "month", "close_raw"])
    df.attrs["failed"] = failed
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["pull"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    t0 = time.time()
    sys.path.insert(0, str(C.REPO))
    from scripts import night_p6_bars_and_regret as P6
    syms = set()
    for p in (C.BARS_DEEP, C.BARS_DELISTED, C.BARS_DELISTED_CRSP):
        if p.exists():
            syms |= {s.split("#")[0] for s in pd.read_parquet(p, columns=["symbol"])["symbol"].unique()}
    syms = sorted(syms)[: a.limit] if a.limit else sorted(syms)
    kid, sec, src = P6.data_credential()
    print(f"pulling monthly RAW bars for {len(syms)} tickers", flush=True)
    df = pull(syms, kid, sec, P6._get, workers=a.workers)
    tmp = RAW_MONTHLY.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    import os
    os.replace(tmp, RAW_MONTHLY)
    rec = {"job": "nn_lab.raw_prices pull", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "credential_source": src.split(",")[0], "tickers_requested": len(syms),
           "tickers_with_bars": int(df["symbol"].nunique()) if len(df) else 0,
           "monthly_bars": int(len(df)), "failed_chunks_symbols": len(df.attrs.get("failed", [])),
           "path": str(RAW_MONTHLY), "elapsed_s": round(time.time() - t0, 1),
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    RECEIPT.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(json.dumps(rec, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
