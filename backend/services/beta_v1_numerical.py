"""Owner-authorized retrospective H21 close-target experiment; no live writes.

The old ranker target/saved rankings are incompatible. Only trailing features,
eligibility, fixed model specification, folds and calibration are reused.
Native price adjustment is UNKNOWN; all results are direction checks only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, Optional

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from backend.services import beta_v1_policy as policy
from backend.services import xs_ranker as xr
from backend.services import stitched_tickers as st
from backend.services import bar_defects

VERSION = "beta_v1_numerical/1"
OBJECTIVE = "XS_EQUAL_WEIGHT:NATIVE_PRICE_CLOSE_UNKNOWN_ADJUSTMENT:NEXT_SESSION_CLOSE_H21:v1"
TARGET = "NEXT_SESSION_CLOSE_TO_21_FURTHER_ACTUAL_XNYS_CLOSE"
PROGRESS_STAGES = frozenset({"registrants", "price_read", "price_concat", "prepare_prices", "dataset_hash", "features", "feature_hash",
    "eligibility", "close_target", "fold_split", "fold_fit", "fold_predict", "calibration",
    "production_fit", "current_ranking", "source_verification", "metrics"})
PRICE_COLUMNS = ("symbol", "date", "open", "high", "low", "close", "volume", "vwap", "trades")
START = "2024-01-01"
CUTOFF = "2026-10-09"
PRICE_SOURCES = {
    "C:/Users/mrthn/aegis-finance/backend/data/optimus/prices_deep/bars.parquet":
        "780b23c5293d985c25adaba2f4002bcf4eb10009ff23dd2bcd5f12b24e7b7d39",
    "C:/Users/mrthn/aegis-finance/backend/data/optimus/prices_deep/bars_delisted.parquet":
        "eff9558e330a136bad8175aeb130dbeb867ec154844550d4b8b4205addfe440b"}
FACTS_PATH = Path("C:/Users/mrthn/aegis-finance/backend/data/optimus/fundamentals_sec/sec_facts_history.parquet")
TICKERS_PATH = Path("C:/Users/mrthn/aegis-finance/backend/data/optimus/edgar_8k/company_tickers.json")
FROZEN_SOURCE_PINS = {
    "xs_ranker.py": "5c6557f3bb390f0fdfd085425466472b1ebf2f003194119c4dc12b77deb50b77",
    "stitched_tickers.py": "006b33abcbaaf93ff89b871ca0f314a7f4fea55091753f103fd940e485236983",
    "bar_defects.py": "6b9d1ff4be2a2b39db0cbafd9e585c73eb48f165870ae1906660b5cf897a6d92",
    "beta_v1_policy.py": "cfd0ee34cacc7629b221c131ee8127cf8892618cf527e0f5b8e9c62718b2ebf3"}


class NumericalRefused(RuntimeError):
    def __init__(self, reason, *, evidence=None):
        self.evidence = evidence or {}
        super().__init__(reason)


def rss_owned_handle(handle, *, peak=True):
    """Query a retained exact Windows process handle, including after exit.

    This function never opens a PID or closes the caller's handle. Unsupported
    or unavailable final OS counters refuse; no last-sample substitution.
    """
    if os.name != "nt" or not handle:
        raise NumericalRefused("retained Windows process handle unavailable")
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)]+[
            (k, ctypes.c_size_t) for k in ("peak_rss", "rss", "peak_paged", "paged",
                "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    query = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not query(handle, ctypes.byref(counters), counters.cb):
        raise NumericalRefused("retained owned-handle final RSS query failed")
    value = int(counters.peak_rss if peak else counters.rss)
    if value <= 0:
        raise NumericalRefused("retained owned-handle RSS counters unavailable/zero")
    return value


def rss_bytes(pid=None, *, peak=False):
    """No optional dependency/download; query only this or its owned worker."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        process = kernel.OpenProcess(0x410, False, pid or os.getpid())
        if not process:
            raise NumericalRefused("owned-process RSS query unavailable")
        try:
            return rss_owned_handle(process, peak=peak)
        finally:
            kernel.CloseHandle(process)
    status = Path(f"/proc/{pid or os.getpid()}/status").read_text()
    field = "VmHWM:" if peak else "VmRSS:"
    return int(next(line.split()[1] for line in status.splitlines() if line.startswith(field)))*1024


def sha256(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def code_pins():
    return {Path(m.__file__).name: sha256(m.__file__) for m in
            (xr, st, bar_defects, policy, policy.kernels, policy.er, policy.fr)
            } | {Path(__file__).name: sha256(__file__)}


def specification():
    if len(xr.FEATURES) != 24 or xr.LGB_PARAMS["n_estimators"] != 350:
        raise NumericalRefused("original feature/model specification drift")
    if (xr.MIN_TRAIN_ROWS, xr.MIN_DECISION_DATES, xr.MIN_DECILE_ROWS, xr.MIN_DECILE_BLOCKS,
            xr.MIN_HISTORY_SESSIONS, xr.PURGE_SESSIONS) != (40000, 120, 500, 6, 126, 21):
        raise NumericalRefused("original admission/calibration gates drift")
    return {"features": list(xr.FEATURES), "parameters": dict(xr.LGB_PARAMS), "cpu_threads": 2,
        "folds": 4, "min_train_fraction": .45, "purge_sessions": 21,
        "min_train_rows": 40000, "min_decision_dates": 120, "min_history_sessions": 126,
        "min_decile_rows": 500, "min_decile_month_blocks": 6, "horizon": 21,
        "target": TARGET, "objective_version": OBJECTIVE,
        "legacy_target": "INCOMPATIBLE_NEXT_OPEN_TO_T_PLUS_22_CLOSE; never reused"}


@dataclass
class Budget:
    max_rows: int = 2_500_000
    max_rss: int = 3*1024**3
    max_seconds: float = 465
    max_output: int = 32*1024**2
    started: float = field(default_factory=time.monotonic)
    peak_rss: int = 0
    progress_callback: Optional[Callable[[dict], None]] = None
    progress_events: int = field(default=0, init=False)
    progress_bytes: int = field(default=0, init=False)

    def check(self, stage, *, rows=0, phase=None):
        current_rss = rss_bytes()
        self.peak_rss = max(self.peak_rss, current_rss)
        if rows > self.max_rows or self.peak_rss > self.max_rss or time.monotonic()-self.started > self.max_seconds:
            raise NumericalRefused("resource cap exceeded at "+stage)
        if self.progress_callback is not None and phase is not None:
            if stage not in PROGRESS_STAGES or phase not in {"enter", "complete"}:
                raise NumericalRefused("unsupported scalar progress stage/phase")
            event = {"schema": "beta_numerical_progress/1", "stage": stage, "phase": phase,
                "utc": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
                "elapsed_seconds": time.monotonic()-self.started, "rows": rows,
                "rss_bytes": current_rss, "peak_rss_bytes": rss_bytes(peak=True)}
            encoded = (json.dumps(event, indent=2, allow_nan=False)+"\n").encode("utf-8")
            if self.progress_events >= 64 or self.progress_bytes+len(encoded) > 64*1024:
                raise NumericalRefused("scalar progress metadata cap exceeded")
            try:
                self.progress_callback(dict(event))
            except Exception as exc:
                raise NumericalRefused("scalar progress callback failed: "+type(exc).__name__) from None
            self.progress_events += 1
            self.progress_bytes += len(encoded)
            # Callback I/O belongs to this job's unchanged resource budget.
            self.peak_rss = max(self.peak_rss, rss_bytes())
            if self.peak_rss > self.max_rss or time.monotonic()-self.started > self.max_seconds:
                raise NumericalRefused("resource cap exceeded during scalar progress callback")

    def accounting(self):
        return {"elapsed_seconds": time.monotonic()-self.started, "peak_rss_bytes": self.peak_rss,
            "rows_cap": self.max_rows, "rss_cap_bytes": self.max_rss, "outer_wall_seconds": 480,
            "inner_wall_seconds": self.max_seconds, "output_cap_bytes": self.max_output, "cpu_threads": 2,
            "progress_events": self.progress_events, "progress_metadata_bytes": self.progress_bytes}


def read_prices(budget):
    """Only the two explicitly pinned ordinary price inputs, date-filtered batches."""
    import pyarrow as pa
    import pyarrow.dataset as ds

    frames, pins, total = [], {}, 0
    for name, expected in PRICE_SOURCES.items():
        path = Path(name)
        before = sha256(path)
        if before != expected:
            raise NumericalRefused("price source pin drift: "+path.name)
        dataset = ds.dataset(path, format="parquet")
        names = set(dataset.schema.names)
        if not set(PRICE_COLUMNS[:7]) <= names:
            raise NumericalRefused("required ordinary price columns missing")
        date_type = dataset.schema.field("date").type
        start = pa.scalar(pd.Timestamp(START).to_pydatetime(), type=date_type)
        end = pa.scalar(pd.Timestamp(CUTOFF).to_pydatetime(), type=date_type)
        scanner = dataset.scanner(columns=[c for c in PRICE_COLUMNS if c in names],
            filter=(ds.field("date") >= start) & (ds.field("date") <= end),
            batch_size=32768, use_threads=False, batch_readahead=1, fragment_readahead=1)
        for batch in scanner.to_batches():
            total += batch.num_rows
            budget.check("price batch", rows=total)
            frame = batch.to_pandas()
            frame["_src"] = path.stem
            frames.append(frame)
        after = sha256(path)
        if after != before:
            raise NumericalRefused("price changed during streamed read")
        pins[name] = {"sha256": before, "after_sha256": after, "columns": [c for c in PRICE_COLUMNS if c in names]}
    budget.check("price_concat", rows=total, phase="enter")
    result = pd.concat(frames, ignore_index=True)
    frames.clear()
    # Drop the final batch and scanner references as well; concat math is unchanged.
    frame = batch = scanner = dataset = None
    budget.check("price_concat", rows=len(result), phase="complete")
    budget.check("price concat", rows=len(result))
    return result, pins


def registrant_metadata(*, facts_sha256, tickers_sha256, budget):
    """Explicit ordinary ticker/CIK/filed metadata only, preserving ST guards.

    The streamed grouping reproduces the existing registrants helper's minimum
    filing rules when its full projected frame cannot fit the metadata cap.
    No numerical fundamentals are read and no discovery/default paths occur.
    """
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq
    pins = {str(FACTS_PATH): facts_sha256, str(TICKERS_PATH): tickers_sha256}
    if TICKERS_PATH.stat().st_size > 1024**2:
        raise NumericalRefused("company ticker metadata JSON cap exceeded")
    if any(sha256(path) != expected for path, expected in pins.items()):
        raise NumericalRefused("registrant metadata source pin mismatch")
    footer = pq.ParquetFile(FACTS_PATH).metadata
    if footer.num_rows <= 1_000_000 and footer.num_rows*192 <= 64*1024**2:
        result = st.registrants(facts_path=FACTS_PATH, tickers_path=TICKERS_PATH)
        mode = "unchanged ST.registrants; bounded projected metadata frame"
    else:
        groups = pd.DataFrame(columns=["ticker", "cik", "filed"])
        scanner = ds.dataset(FACTS_PATH, format="parquet").scanner(columns=["ticker", "cik", "filed"],
            batch_size=16384, use_threads=False, batch_readahead=1, fragment_readahead=1)
        for batch in scanner.to_batches():
            budget.check("registrant metadata batch")
            frame = batch.to_pandas()
            frame["filed"] = pd.to_datetime(frame["filed"], errors="coerce")
            frame = frame.dropna(subset=["filed", "cik"])
            groups = pd.concat([groups, frame], ignore_index=True).groupby(["ticker", "cik"], as_index=False)["filed"].min()
            if len(groups) > 1_000_000 or groups.memory_usage(deep=True).sum() > 64*1024**2:
                raise NumericalRefused("registrant metadata frame cap exceeded")
        result = {"by_ticker": {}, "cik_first": groups.groupby("cik")["filed"].min().sort_index(),
            "sources": [FACTS_PATH.name, TICKERS_PATH.name]}
        for ticker, cik, filed in groups.sort_values(["ticker", "filed", "cik"]).itertuples(index=False):
            if str(ticker) not in result["by_ticker"]:
                result["by_ticker"][str(ticker)] = {"cik": int(cik), "first_filed": pd.Timestamp(filed), "source": "sec_facts_history"}
        if TICKERS_PATH.stat().st_size > 1024**2:
            raise NumericalRefused("company ticker metadata JSON cap exceeded")
        raw = json.loads(TICKERS_PATH.read_text(encoding="utf-8"))
        for row in (raw.values() if isinstance(raw, dict) else raw):
            ticker, cik = str(row.get("ticker", "")), row.get("cik_str")
            if ticker and cik is not None and ticker not in result["by_ticker"]:
                result["by_ticker"][ticker] = {"cik": int(cik), "first_filed": None, "source": "company_tickers"}
        mode = "field-only streamed minima, same ST registrant semantics"
    if any(sha256(path) != expected for path, expected in pins.items()):
        raise NumericalRefused("registrant metadata changed during read")
    return result, {"source_pins": pins, "mode": mode, "columns": ["ticker", "cik", "filed"],
        "frame_cap_rows": 1_000_000, "frame_cap_bytes": 64*1024**2,
        "scope": "Stitch identity guards only; not current security eligibility or fundamental features"}


def prepare_prices(bars, *, registrants):
    """No keep-first conflicts or gaps spanning a disappeared listing."""
    bars = bars.copy()
    bars["date"] = pd.to_datetime(bars["date"])
    if bars["date"].dt.tz is not None or (bars["date"] != bars["date"].dt.normalize()).any():
        raise NumericalRefused("native bar dates must be unambiguous session dates")
    if bars.empty or bars["date"].min() < pd.Timestamp(START) or bars["date"].max() > pd.Timestamp(CUTOFF):
        raise NumericalRefused("bar date bounds violated")
    duplicated = bars.duplicated(["symbol", "date"], keep=False)
    duplicate_rows = int(duplicated.sum())
    # Source metadata may differ; price values must agree exactly. Conflicting
    # symbol/date data refuses the dataset instead of a source-order winner.
    values = [c for c in PRICE_COLUMNS if c not in ("symbol", "date") and c in bars]
    if duplicated.any() and (bars.loc[duplicated].groupby(["symbol", "date"])[values].nunique(dropna=False) > 1).any().any():
        raise NumericalRefused("conflicting duplicate symbol/date prices")
    if duplicated.any():
        bars.loc[duplicated, "_src"] = bars.loc[duplicated].groupby(["symbol", "date"])["_src"].transform(lambda s: ",".join(sorted(set(s))))
    bars = bars.drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"]).reset_index(drop=True)
    valid = np.isfinite(bars[["open", "high", "low", "close", "volume"]]).all(axis=1)
    valid &= (bars[["open", "high", "low", "close"]] > 0).all(axis=1) & (bars["volume"] >= 0)
    invalid_rows = int((~valid).sum())
    bars = bars.loc[valid].copy()
    if not registrants or not all(k in registrants for k in ("by_ticker", "cik_first", "sources")):
        raise NumericalRefused("explicit stitch registrant metadata required")
    bars, audit = st.split_stitched(bars, src_col="_src", regs=registrants)
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(START, CUTOFF).tz_localize(None)
    position = sessions.get_indexer(bars["date"])
    if (position < 0).any():
        raise NumericalRefused("price row on non-XNYS session")
    gap_count = 0
    # Even unresolved short holes must not connect feature histories. Earlier
    # segments retain distinct dead identities; last segment keeps the ticker.
    for symbol, group in bars.groupby("symbol", sort=False):
        idx = group.index
        positions = sessions.get_indexer(group["date"])
        segment = np.r_[0, np.cumsum(np.diff(positions) != 1)]
        last = int(segment[-1])
        gap_count += last
        if last:
            bars.loc[idx, "symbol"] = [symbol if n == last else f"{symbol}#GAP{n+1}" for n in segment]
    return bars.drop(columns="_src").sort_values(["symbol", "date"]).reset_index(drop=True), {
        "duplicate_rows": duplicate_rows, "conflicting_duplicates": 0, "invalid_price_rows": invalid_rows,
        "stitch": audit, "additional_gap_segments": gap_count,
        "pre_2024_listing_history": "UNKNOWN; sessions_seen counts only bounded continuous segment, conservative floor"}


def close_target(panel):
    """New experiment labels: t+1 CLOSE to t+22 CLOSE (21 exact sessions)."""
    out = panel.copy()
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(out["date"].min(), pd.Timestamp(CUTOFF)+pd.Timedelta(days=65)).tz_localize(None)
    pos = sessions.get_indexer(out["date"])
    if (pos < 0).any():
        raise NumericalRefused("target formation not XNYS")
    close_map = {d: calendar.session_close(d).isoformat() for d in sessions}
    out["formation_at"] = out["date"].map(close_map)
    out["label_start_at"] = pd.Series(sessions[pos+1], index=out.index).map(close_map)
    out["label_end_at"] = pd.Series(sessions[pos+22], index=out.index).map(close_map)
    g = out.groupby("symbol", sort=False)
    entry, exit_ = g["close"].shift(-1), g["close"].shift(-22)
    entry_date, exit_date = g["date"].shift(-1), g["date"].shift(-22)
    valid = (entry_date.values == sessions[pos+1].values) & (exit_date.values == sessions[pos+22].values)
    # Check every intermediate session, not just matching endpoints.
    contiguous = g["date"].transform(lambda s: pd.Series(np.r_[np.diff(sessions.get_indexer(s)) == 1, False], index=s.index)
        .iloc[::-1].rolling(22, min_periods=22).sum().iloc[::-1] == 22)
    valid &= contiguous & np.isfinite(entry) & np.isfinite(exit_) & (entry > 0) & (exit_ > 0)
    out["fwd_ret"] = np.where(valid, exit_/entry-1, np.nan)
    formation = out.loc[out["eligible"]].groupby("date")["fwd_ret"].agg(["size", "count", "mean"])
    complete = formation["size"] == formation["count"]
    bench = formation["mean"].where(complete)
    out["bench_fwd_ret"] = out["date"].map(bench)
    out["fwd_rel"] = out["fwd_ret"]-out["bench_fwd_ret"]
    out["y"] = np.nan
    elig = out["eligible"] & out["fwd_rel"].notna()
    out.loc[elig, "y"] = out.loc[elig].groupby("date")["fwd_rel"].rank(pct=True, method="average")
    return out, {"target": TARGET, "horizon": 21, "invalid_or_unmatured_windows": int((~valid).sum()),
        "benchmark_formation_dates": len(formation), "benchmark_incomplete_dates": int((~complete).sum()),
        "benchmark_missing_policy": "Whole formation-date target unavailable if any formation-eligible member lacks exact exit; no silent survivor-only benchmark"}


def mature_rows(panel, cutoff):
    cutoff = policy._clock(cutoff)
    ends = pd.to_datetime(panel["label_end_at"], utc=True)
    formation = pd.to_datetime(panel["formation_at"], utc=True)
    return panel.loc[panel["eligible"] & panel["y"].notna() & (ends <= cutoff) & (formation < cutoff)].copy()


def fold_rows(panel, train_end, test_start, test_end):
    test = panel.loc[(panel["date"] >= test_start) & (panel["date"] <= test_end) & panel["eligible"] & panel["y"].notna()].copy()
    if test.empty:
        return panel.iloc[:0], test, {"refused": "empty test window"}
    first = min(pd.to_datetime(test["formation_at"], utc=True))
    candidates = panel.loc[(panel["date"] <= train_end) & panel["eligible"] & panel["y"].notna()]
    train = mature_rows(candidates, first.isoformat())
    return train, test, {"first_test_formation_at": first.isoformat(), "purged_by_actual_label_end": len(candidates)-len(train),
        "train_end": str(train_end.date()), "test_start": str(test_start.date()), "test_end": str(test_end.date()),
        "n_train": len(train), "n_test": len(test), "latest_train_label_end": max(train["label_end_at"]) if len(train) else None}


def model_hash(model):
    return hashlib.sha256(model.booster_.model_to_string().encode("utf-8")).hexdigest()


def fit_oos(panel, budget):
    import lightgbm as lgb

    specification()
    rows = panel.loc[panel["eligible"] & panel["y"].notna()]
    predictions, ledger = [], []
    folds = xr.make_folds(rows["date"].values, n_folds=4, min_train_frac=.45)
    del rows
    for train_end, start, end in folds:
        budget.check("before fold")
        budget.check("fold_split", phase="enter")
        train, test, receipt = fold_rows(panel, train_end, start, end)
        budget.check("fold_split", rows=len(train)+len(test), phase="complete")
        if len(train) < xr.MIN_TRAIN_ROWS or test.empty:
            ledger.append({**receipt, "status": "REFUSED", "reason": "unchanged minimum train rows or empty test"})
            del train, test
            continue
        model = lgb.LGBMRegressor(**xr.LGB_PARAMS, n_jobs=2)
        budget.check("fold_fit", rows=len(train), phase="enter")
        model.fit(train[list(xr.FEATURES)], train["y"])
        budget.check("fold_fit", rows=len(train), phase="complete")
        budget.check("after fold fit")
        prediction = test[["symbol", "date", "y", "fwd_rel", "fwd_ret", "bench_fwd_ret", "median_dollar_vol",
            "close", "formation_at", "label_start_at", "label_end_at"]].copy()
        budget.check("fold_predict", rows=len(test), phase="enter")
        prediction["score"] = model.predict(test[list(xr.FEATURES)])
        budget.check("fold_predict", rows=len(test), phase="complete")
        prediction["fold_train_end"] = train_end
        predictions.append(prediction)
        ledger.append({**receipt, "status": "FITTED", "model_serialized_sha256": model_hash(model)})
        del train, test, model
    if not predictions:
        raise NumericalRefused("all four chronological folds refused", evidence={"folds": ledger})
    oos = pd.concat(predictions, ignore_index=True)
    oos["score_pct"] = oos.groupby("date")["score"].rank(pct=True, method="average")
    oos["decile"] = np.clip((oos["score_pct"]*10).astype(int), 0, 9)
    return oos, ledger


def oos_metrics(oos, target_panel):
    """Exact target aggregates, no fills/Sharpe/annualization or reused open P&L."""
    dates, spy_comparisons = [], []
    spy = target_panel.loc[target_panel["symbol"] == "SPY"].set_index("date")
    for date, group in oos.groupby("date"):
        top = group.sort_values(["score", "symbol"], ascending=[False, True]).head(20)
        if len(top) < 20:
            continue
        dates.append({"formation_date": str(date.date()), "label_start_at": top["label_start_at"].iloc[0],
            "label_end_at": top["label_end_at"].iloc[0], "n": len(top),
            "gross_price_return": float(top["fwd_ret"].mean()), "gross_xs_excess": float(top["fwd_rel"].mean()),
            "existing_curve_net_xs_excess": float((top["fwd_rel"]-top["median_dollar_vol"].map(xr.round_trip_bps)/10000).mean()),
            "fixed_50bps_net_xs_excess": float(top["fwd_rel"].mean()-.005)})
        if date in spy.index:
            control = spy.loc[date]
            if (np.isfinite(control["fwd_ret"]) and control["label_start_at"] == top["label_start_at"].iloc[0]
                    and control["label_end_at"] == top["label_end_at"].iloc[0]):
                spy_comparisons.append({"formation_date": str(date.date()), "label_start_at": control["label_start_at"],
                    "label_end_at": control["label_end_at"], "spy_gross_price_return": float(control["fwd_ret"]),
                    "top20_gross_minus_spy": float(top["fwd_ret"].mean()-control["fwd_ret"])})
    return {"horizon": 21, "target": TARGET, "objective_version": OBJECTIVE, "n_rows": len(oos),
        "n_dates": oos["date"].nunique(), "n_month_blocks": oos["date"].dt.to_period("M").nunique(),
        "mean_rank_squared_loss": float(np.mean((oos["score"]-oos["y"])**2)),
        "mean_gross_xs_excess_all_rows": float(oos["fwd_rel"].mean()), "top20_exact_windows": dates,
        "existing_curve_net": "Separate descriptive comparison; not passed to new fixed-cost consumer",
        "SPY": {"role": "SEPARATE_COMPARATOR_ONLY", "status": "EXACT_WINDOW_QUOTES" if spy_comparisons else "UNAVAILABLE",
            "n_matched_windows": len(spy_comparisons), "n_unavailable_windows": len(dates)-len(spy_comparisons),
            "windows": spy_comparisons},
        "claim": "Retrospective overlapping native price direction checks only; not independent alpha or original forecasts"}


def normalize_current(ranking, *, receipt_at, feature_asof, provenance):
    """Only measured GROSS calibration values enter schema3 current H21."""
    now = policy._clock(receipt_at)
    calendar = xcals.get_calendar("XNYS")
    feature_date = pd.Timestamp(feature_asof).normalize()
    feature_close = calendar.session_close(feature_date)
    if feature_close > now or feature_date != calendar.date_to_session(now.date(), direction="previous").tz_localize(None):
        # On an open session before close the previous completed session applies.
        previous = calendar.date_to_session(now.date(), direction="previous")
        if calendar.session_close(previous) > now:
            previous = calendar.previous_session(previous)
        if feature_date != previous.tz_localize(None):
            raise NumericalRefused("feature session is not last completed XNYS session")
    entry = calendar.next_session(feature_date)
    exit_session = calendar.session_offset(entry, 21)
    start, end = calendar.session_close(entry), calendar.session_close(exit_session)
    if now >= start or provenance.get("return_cost_basis") != "GROSS_NATIVE_PRICE_CLOSE_EXCESS":
        raise NumericalRefused("entry expired or NET/unknown calibration cannot be reused")
    required = ("dataset_hash", "feature_hash", "feature_values_hash", "parameter_hash", "model_serialized_sha256", "calibration_hash", "code_hash", "latest_train_label_end")
    hashes = required[:-1]
    if (not all(isinstance(provenance.get(k), str) and len(provenance[k]) == 64
                and all(c in "0123456789abcdef" for c in provenance[k]) for k in hashes)
            or not provenance.get("latest_train_label_end") or policy._clock(provenance["latest_train_label_end"]) > feature_close
            or policy._clock(provenance.get("latest_calibration_label_end")) > feature_close
            or provenance.get("target") != TARGET or provenance.get("objective_version") != OBJECTIVE):
        raise NumericalRefused("incomplete or future training provenance")
    component = "h21_close_ranker"
    model_version = VERSION+":"+provenance["model_serialized_sha256"]
    defs = {component: {"source_family": "numerical", "model_version": model_version,
        "prompt_version": "none", "correlation_group": "numerical_close_ranker"}}
    rows, qualifications, unavailable = [], {}, []
    source_hash = policy.digest(provenance)
    for _, ranked in ranking.iterrows():
        value = ranked.get("expected_relative_return_21d")
        if (ranked.get("calibration_measured") not in (True, np.bool_(True)) or isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, float, np.number)) or not np.isfinite(value)):
            unavailable.append({"ticker": ranked["symbol"], "reason": "exact H21 gross calibration decile unmeasured"})
            continue
        seen = ranked.get("sessions_seen", 0)
        if (pd.Timestamp(ranked["date"]).normalize() != feature_date
                or not isinstance(seen, (int, float, np.number)) or not np.isfinite(seen) or seen < 126):
            unavailable.append({"ticker": ranked["symbol"], "reason": "feature date/history qualification unavailable"})
            continue
        row = {"forecast_id": "H21:"+source_hash+":"+ranked["symbol"], "component": component,
            "ticker": ranked["symbol"], "root_event": "UNKNOWN_DATE_TICKER:"+str(entry.date())+":"+ranked["symbol"],
            "root_independence": "UNKNOWN", "source_hash": source_hash, "forecast_at": now.isoformat(),
            "available_at": now.isoformat(), "feature_at": feature_close.isoformat(), "label_start_at": start.isoformat(),
            "label_end_at": end.isoformat(), "valid_until_at": start.isoformat(), "calendar": "XNYS",
            "window_contract": "session_close_to_close", "task": "expected_excess_return", "horizon": 21,
            "objective_version": OBJECTIVE, "model_version": model_version, "prompt_version": "none",
            "x": float(value), "return_cost_basis": "GROSS_NATIVE_PRICE_CLOSE_EXCESS",
            "price_adjustment_status": "UNKNOWN", "numerical_provenance": provenance}
        rows.append(row)
        qualifications[policy.digest(row)] = {"source_hash": source_hash, "source_ref": "private:numerical-current-receipt",
            "adapter_version": VERSION, "qualification_reason": "new retrospective price-only model; exact close H21 measured gross calibration; unknown adjustment and root independence; inactive only",
            "numerical_provenance_hash": source_hash}
    return {"asof_utc": now.isoformat(), "qualified_scheduled_entry_at": start.isoformat(),
        "qualified_return_records": rows, "qualified_return_qualifications": qualifications,
        "qualified_return_definitions": defs, "unavailable": unavailable, "feature_asof": str(feature_date.date()),
        "source_provenance_hash": source_hash, "target": TARGET, "horizon": 21, "objective_version": OBJECTIVE}


def run(*, facts_sha256, tickers_sha256, budget=None, model_sink=None):
    budget = budget or Budget()
    before = code_pins()
    if any(before[name] != expected for name, expected in FROZEN_SOURCE_PINS.items()):
        raise NumericalRefused("frozen original model/stitch/policy source drift")
    spec = specification()
    budget.check("registrants", phase="enter")
    registrants, metadata_audit = registrant_metadata(facts_sha256=facts_sha256, tickers_sha256=tickers_sha256, budget=budget)
    budget.check("registrants", phase="complete")
    budget.check("price_read", phase="enter")
    bars, input_pins = read_prices(budget)
    budget.check("price_read", rows=len(bars), phase="complete")
    budget.check("prepare_prices", rows=len(bars), phase="enter")
    bars, audit = prepare_prices(bars, registrants=registrants)
    del registrants
    budget.check("prepare_prices", rows=len(bars), phase="complete")
    budget.check("stitch/duplicates", rows=len(bars))
    budget.check("dataset_hash", rows=len(bars), phase="enter")
    dataset_hash = hashlib.sha256(pd.util.hash_pandas_object(bars, index=False).values.tobytes()).hexdigest()
    budget.check("dataset_hash", rows=len(bars), phase="complete")
    budget.check("features", rows=len(bars), phase="enter")
    features = xr.build_features(bars)
    del bars
    budget.check("features", rows=len(features), phase="complete")
    budget.check("eligibility", rows=len(features), phase="enter")
    panel = xr.mark_eligible(features)
    del features
    budget.check("eligibility", rows=len(panel), phase="complete")
    budget.check("trailing features")
    budget.check("feature_hash", rows=len(panel), phase="enter")
    feature_values_hash = hashlib.sha256(pd.util.hash_pandas_object(
        panel[["symbol", "date", *xr.FEATURES]], index=False).values.tobytes()).hexdigest()
    budget.check("feature_hash", rows=len(panel), phase="complete")
    budget.check("close_target", rows=len(panel), phase="enter")
    panel, target_audit = close_target(panel)
    budget.check("close_target", rows=len(panel), phase="complete")
    budget.check("exact close target")
    oos, folds = fit_oos(panel, budget)
    closed = xcals.get_calendar("XNYS").session_close(CUTOFF)
    training = mature_rows(panel, closed.isoformat())
    # Calibrate only OOS outcomes completed by the closed data cutoff.
    calibration_rows = mature_rows(oos.assign(eligible=True), closed.isoformat())
    budget.check("calibration", rows=len(calibration_rows), phase="enter")
    calibration = xr.calibrate(calibration_rows)
    budget.check("calibration", rows=len(calibration_rows), phase="complete")
    import lightgbm as lgb
    if len(training) < xr.MIN_TRAIN_ROWS:
        raise NumericalRefused("production training minimum rows failed")
    model = lgb.LGBMRegressor(**xr.LGB_PARAMS, n_jobs=2)
    budget.check("production_fit", rows=len(training), phase="enter")
    model.fit(training[list(xr.FEATURES)], training["y"])
    budget.check("production_fit", rows=len(training), phase="complete")
    budget.check("production fit")
    serialized = model.booster_.model_to_string()
    model_sha = hashlib.sha256(serialized.encode()).hexdigest()
    model_ref = model_sink(serialized, model_sha) if model_sink else None
    budget.check("current_ranking", rows=len(panel), phase="enter")
    ranking = xr.rank_asof(panel, model, calibration, asof=CUTOFF, train_end=training["date"].max())
    budget.check("current_ranking", rows=len(ranking), phase="complete")
    provenance = {"schema": VERSION, "target": TARGET, "objective_version": OBJECTIVE,
        "dataset_hash": dataset_hash, "input_pins": input_pins, "feature_hash": policy.digest(spec["features"]),
        "feature_values_hash": feature_values_hash,
        "parameter_hash": policy.digest(spec["parameters"]), "model_serialized_sha256": model_sha,
        "calibration_hash": policy.digest(calibration), "code_hash": policy.digest(before),
        "train_end": str(training["date"].max().date()), "latest_train_label_end": max(training["label_end_at"]),
        "latest_calibration_label_end": max(calibration_rows["label_end_at"]), "n_train": len(training),
        "return_cost_basis": "GROSS_NATIVE_PRICE_CLOSE_EXCESS", "native_adjustment": "UNKNOWN",
        "stitch_metadata_pins": metadata_audit["source_pins"],
        "historical_availability": "Posthoc native session endpoints; provider ingestion clocks UNKNOWN; not authentic original/PIT forecasts"}
    current = normalize_current(ranking, receipt_at=datetime.now(timezone.utc).isoformat(), feature_asof=CUTOFF, provenance=provenance)
    budget.check("source_verification", phase="enter")
    if (code_pins() != before or any(sha256(p) != pin["sha256"] for p, pin in input_pins.items())
            or any(sha256(p) != expected for p, expected in metadata_audit["source_pins"].items())):
        raise NumericalRefused("source/code drift during numerical execution")
    budget.check("source_verification", phase="complete")
    budget.check("metrics", rows=len(oos), phase="enter")
    metrics = oos_metrics(oos, panel)
    budget.check("metrics", rows=len(oos), phase="complete")
    result = {"schema": VERSION, "status": "MEASURED_RETROSPECTIVE_DIRECTION_CHECK", "specification": spec,
        "provenance": provenance, "source_pins": before, "audits": {"prices": audit, "target": target_audit},
        "folds": folds, "calibration": calibration, "oos": metrics, "current": current,
        "stitch_metadata": metadata_audit,
        "serialized_model_reference": model_ref, "resources": budget.accounting(),
        "original_forward_forecasts": "SEPARATE; never rewritten or reproduced by this posthoc fit",
        "price_basis": "PRICE_RETURN_NOT_TOTAL_RETURN; adjustment UNKNOWN", "activation": "NONE"}
    budget.check("final output")
    return {**result, "artifact_hash": policy.digest(result)}
