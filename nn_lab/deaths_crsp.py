"""Deaths the inactive-asset list never listed (review F3, diagnosed 2026-09-30).

DIAGNOSIS. `bars_delisted.parquet` comes from Alpaca's list of INACTIVE assets, and that list
is not a history of deaths: measured against CRSP's daily file (the 6,254-PERMNO screened
superset on disk, `wrds/crsp_dsf_2016..2024`), it holds 8 of 284 names that died in 2016, 3 of
248 in 2017, most of 2019-2022, and **4 of 400 in 2023 and 4 of 343 in 2024**. The bars endpoint
still serves those tickers by symbol (probed: SGEN to 2023-12-13, ATVI to 2023-10-13, SPLK to
2024-03-15, PXD to 2024-05-02, SIVB to 2023-03-09); only the LIST is missing them.

FIX. Take every CRSP PERMNO whose daily series ends before the CRSP vintage ends, name it by
its ticker in its last CRSP month, pull that ticker's bars (same endpoint, same adjustment,
same instrument filter as `scripts/pull_delisted_bars`), and keep a bar only when
  * its date is inside the PERMNO's own CRSP life (first date .. last date + 3 days), so a
    later company that reused the ticker is never attached, and
  * the Alpaca close-to-close returns match CRSP's `ret` (median |diff| < 1% over the common
    days and correlation > 0.9), so an earlier company that used the ticker is never
    attached either.
A ticker that collides with the living panel or the inactive list is written as `SYM#c`, a
dead name of its own (never spliced, never dropped).

Written to a NEW file, `prices_deep/bars_delisted_crsp.parquet`; `table.build` reads it only
when `config.USE_CRSP_DEATHS` is True. Deaths after the CRSP vintage (2025-26) are still
missing: no free list of them is on disk.

    python -m nn_lab.deaths_crsp            # ~15 min of network, $0
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

WRDS = C.OPTIMUS / "wrds"
OUT = C.BARS_DELISTED_CRSP
RECEIPT = C.OPTIMUS / "prices_deep" / "delisted_crsp_receipt.json"
MATCH_MEDIAN_ABS = 0.01
MATCH_CORR = 0.9
TAIL_DAYS = 3
STOP_FILE = C.OUT / "STOP_DEATHS_PULL"


def is_bar_symbol(s: str) -> bool:
    """Plain common-stock tickers only (copied from scripts.pull_delisted_bars._is_bar_symbol)."""
    if not s or "_" in s or len(s) > 5 or "." in s or not s.isalpha():
        return False
    if len(s) == 5 and s[-1] in ("U", "W", "R"):
        return False
    return True


def crsp_deaths(first_year: int = 2016, last_year: int = 2024) -> pd.DataFrame:
    """One row per PERMNO whose CRSP daily series ends >= 10 sessions before the vintage ends."""
    firsts, lasts = {}, {}
    vint_end = None
    for y in range(first_year, last_year + 1):
        p = WRDS / f"crsp_dsf_{y}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["permno", "date"])
        d["date"] = pd.to_datetime(d["date"])
        vint_end = d["date"].max()
        g = d.groupby("permno")["date"].agg(["min", "max"])
        for k, (a, b) in g.iterrows():
            firsts.setdefault(k, a)
            lasts[k] = b
    s = pd.DataFrame({"first": pd.Series(firsts), "last": pd.Series(lasts)})
    s = s[s["last"] < vint_end - pd.Timedelta(days=14)]
    m = pd.read_parquet(C.OPTIMUS / "crsp_pit" / "crsp_pit_monthly_v1.parquet",
                        columns=["permno", "date", "ticker", "comnam", "dlstcd"])
    m["date"] = pd.to_datetime(m["date"])
    lt = m.sort_values("date").groupby("permno").tail(1).set_index("permno")
    s = s.join(lt[["ticker", "comnam", "dlstcd"]])
    s = s[s["ticker"].fillna("").map(is_bar_symbol)]
    s.index.name = "permno"
    return s.reset_index()


def crsp_returns(permnos) -> pd.DataFrame:
    parts = []
    for y in range(2016, 2025):
        p = WRDS / f"crsp_dsf_{y}.parquet"
        if p.exists():
            d = pd.read_parquet(p, columns=["permno", "date", "ret"], filters=[("permno", "in", list(permnos))])
            parts.append(d)
    r = pd.concat(parts, ignore_index=True)
    r["date"] = pd.to_datetime(r["date"])
    r["ret"] = pd.to_numeric(r["ret"], errors="coerce")
    return r


def verify_and_trim(bars: pd.DataFrame, deaths: pd.DataFrame, rets: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep each ticker's bars inside its PERMNO's CRSP life and only if returns match CRSP."""
    keep, report = [], {"matched": 0, "no_bars": 0, "mismatch": 0, "too_short": 0, "examples_mismatch": []}
    rg = rets.groupby("permno")
    bars = bars.sort_values(["symbol", "date"])
    bg = dict(tuple(bars.groupby("symbol")))
    for r in deaths.itertuples():
        b = bg.get(r.ticker)
        if b is None or b.empty:
            report["no_bars"] += 1
            continue
        b = b[(b["date"] >= r.first) & (b["date"] <= r.last + pd.Timedelta(days=TAIL_DAYS))].copy()
        if len(b) < 40:
            report["too_short"] += 1
            continue
        b["r_a"] = b["close"] / b["close"].shift(1) - 1.0
        cr = rg.get_group(r.permno)[["date", "ret"]] if r.permno in rg.groups else pd.DataFrame(columns=["date", "ret"])
        j = b.merge(cr, on="date", how="inner").dropna(subset=["r_a", "ret"])
        if len(j) < 30:
            report["too_short"] += 1
            continue
        med = float(np.median(np.abs(j["r_a"] - j["ret"])))
        corr = float(np.corrcoef(j["r_a"], j["ret"])[0, 1]) if j["ret"].std() > 0 else 0.0
        if med >= MATCH_MEDIAN_ABS or corr <= MATCH_CORR:
            report["mismatch"] += 1
            if len(report["examples_mismatch"]) < 12:
                report["examples_mismatch"].append({"ticker": r.ticker, "permno": int(r.permno),
                                                    "median_abs_diff": round(med, 4), "corr": round(corr, 3)})
            continue
        b = b.drop(columns=["r_a"])
        b["permno"] = int(r.permno)
        keep.append(b)
        report["matched"] += 1
    out = pd.concat(keep, ignore_index=True) if keep else pd.DataFrame()
    return out, report


def drop_overlaps(df: pd.DataFrame, spans: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Drop a CRSP death whose kept bars OVERLAP in time the bars another file already carries
    under the same ticker: that is the same listed price series under a new PERMNO (a merger
    or spin that kept the ticker: JCI 2016, DOW 2019, FOX 2019), not a death. `spans`:
    symbol -> first, last date in the other files."""
    lf = df.groupby("permno").agg(symbol=("symbol", "first"), first=("date", "min"), last=("date", "max"))
    j = lf.join(spans, on="symbol", rsuffix="_other")
    ov = j["first_other"].notna() & (j["first"] <= j["last_other"]) & (j["last"] >= j["first_other"])
    bad = j.index[ov]
    return df[~df["permno"].isin(bad)], sorted(j.loc[ov, "symbol"].tolist())


def rename_collisions(df: pd.DataFrame, taken: set[str]) -> tuple[pd.DataFrame, list[str]]:
    """A ticker already carried by the living panel or the inactive list becomes `SYM#c`; two
    PERMNOs sharing one ticker in this file get `SYM#c`, `SYM#c2`, ... (oldest first)."""
    df = df.copy()
    renamed = []
    order = df.groupby("permno")["date"].min().sort_values()
    per_ticker: dict[str, int] = {}
    new_sym = {}
    for pn in order.index:
        t = df.loc[df["permno"] == pn, "symbol"].iloc[0]
        k = per_ticker.get(t, 0)
        per_ticker[t] = k + 1
        if t in taken or k > 0:
            new_sym[pn] = f"{t}#c" + ("" if k == 0 else str(k + 1))
            renamed.append(new_sym[pn])
        else:
            new_sym[pn] = t
    df["symbol"] = df["permno"].map(new_sym)
    return df, renamed


def pull_windows(todo: pd.DataFrame, kid: str, sec: str, get, workers: int = 8) -> pd.DataFrame:
    """One request series per ticker, only over its PERMNO's CRSP life (first .. last + 5 days),
    in parallel: the bars host answers ~110 bars/s per request tonight, so a serial pull of
    1,778 ten-year histories would take hours. An explicit `end` is safe here: every window
    ends by 2024, far outside the free plan's recent-data delay."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    win = todo.groupby("ticker").agg(first=("first", "min"), last=("last", "max")).reset_index()

    def one(r):
        rows, token = [], None
        for _ in range(50):
            for attempt in range(4):
                try:
                    d = get("/v2/stocks/bars", {"symbols": r.ticker, "start": str(r.first.date()),
                                                "end": str((r.last + pd.Timedelta(days=5)).date()),
                                                "timeframe": "1Day", "adjustment": "all", "limit": 10000,
                                                "feed": "sip", "page_token": token}, kid, sec)
                    break
                except Exception:                                   # noqa: BLE001
                    if attempt == 3:
                        return r.ticker, rows, "FAILED"
                    time.sleep(2.0 * (attempt + 1))
            for b in (d.get("bars") or {}).get(r.ticker, []):
                rows.append((r.ticker, b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"], b.get("vw"), b.get("n")))
            token = d.get("next_page_token")
            if not token:
                break
        return r.ticker, rows, "OK"

    allrows, failed, t0 = [], [], time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, r) for r in win.itertuples()]
        for i, f in enumerate(as_completed(futs), 1):
            tk, rows, st = f.result()
            allrows.extend(rows)
            if st != "OK":
                failed.append(tk)
            if i % 100 == 0:
                print(f"    {i}/{len(futs)} tickers, {len(allrows):,} bars, {time.time() - t0:.0f}s", flush=True)
            if STOP_FILE.exists():
                print("STOP file: ending the pull early", flush=True)
                for g in futs:
                    g.cancel()
                break
    df = pd.DataFrame(allrows, columns=["symbol", "date", "open", "high", "low", "close", "volume", "vwap", "trades"])
    df["date"] = pd.to_datetime(df["date"])
    df.attrs["failed"] = failed
    return df.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    t0 = time.time()
    sys.path.insert(0, str(C.REPO))
    from scripts import night_p6_bars_and_regret as P6   # data endpoint only; nothing live
    deaths = crsp_deaths()
    living = set(pd.read_parquet(C.BARS_DEEP, columns=["symbol"])["symbol"].unique())
    inactive = set(pd.read_parquet(C.BARS_DELISTED, columns=["symbol"])["symbol"].unique())
    # a PERMNO whose ticker the inactive list already carries is (almost always) that same death
    todo = deaths[~deaths["ticker"].isin(inactive)]
    if a.limit:
        todo = todo.head(a.limit)
    kid, sec, src = P6.data_credential()
    tickers = sorted(set(todo["ticker"]))
    print(f"{len(deaths)} CRSP deaths 2016-2024 with a plain ticker; {len(todo)} not in the inactive list; "
          f"pulling {len(tickers)} tickers", flush=True)
    raw_cache = OUT.with_name(OUT.stem + "_raw_pull.parquet")
    if raw_cache.exists() and not a.limit:
        bars = pd.read_parquet(raw_cache)
        print(f"reusing the raw pull {raw_cache.name}: {len(bars):,} bars", flush=True)
    else:
        bars = pull_windows(todo, kid, sec, P6._get, workers=a.workers)
        if not a.limit:
            bars.to_parquet(raw_cache, index=False)
    rets = crsp_returns(todo["permno"].unique())
    kept, rep = verify_and_trim(bars, todo, rets)
    spans = pd.concat([pd.read_parquet(p, columns=["symbol", "date"]) for p in (C.BARS_DEEP, C.BARS_DELISTED)]
                      ).groupby("symbol")["date"].agg(["min", "max"]).rename(columns={"min": "first", "max": "last"})
    spans.columns = ["first_other", "last_other"]
    kept, overlapped = drop_overlaps(kept, spans)
    kept, renamed = rename_collisions(kept, living | inactive)
    kept = kept.drop(columns=["permno"])
    tmp = OUT.with_suffix(".tmp.parquet")
    kept.to_parquet(tmp, index=False)
    import os
    os.replace(tmp, OUT)
    last = kept.groupby("symbol")["date"].max()
    rec = {"job": "nn_lab.deaths_crsp", "licence": "PRODUCT_EXPERIMENT", "llm_spend_usd": 0.0,
           "credential_source": src.split(",")[0], "crsp_deaths_2016_2024_plain_ticker": int(len(deaths)),
           "already_in_inactive_list": int(len(deaths) - len(todo)),
           "deaths_by_year_crsp": deaths["last"].dt.year.value_counts().sort_index().to_dict(),
           "tickers_requested": len(tickers), "tickers_with_bars": int(bars["symbol"].nunique()) if len(bars) else 0,
           "verification": rep,
           "dropped_same_series_under_new_permno": {"n": len(overlapped), "examples": overlapped[:25]},
           "renamed_on_collision": {"n": len(renamed), "examples": renamed[:20]},
           "symbols_written": int(kept["symbol"].nunique()), "bars": int(len(kept)),
           "deaths_by_year_written": last.dt.year.value_counts().sort_index().to_dict(),
           "path": str(OUT), "elapsed_s": round(time.time() - t0, 1),
           "still_missing": "deaths after the CRSP vintage (2025-26): no free list on disk",
           "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    RECEIPT.write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rec, indent=1, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
