"""Daily closes for the names the US bars panel never holds.

WHY THIS EXISTS (2026-09-25)
============================
`xs_ranker.load_bars` is a US panel: 3,060 living symbols plus the delisted
pull, and not one ETF but SPY. The books Murat asked for are global
(`2330.TW`, `ASML.AS`, `RHM.DE`), the competition's benchmark proxy is `URTH`,
and the twins hold theme ETFs (`SMH`, `LIT`, `URA`). A book on a name nobody
prices cannot be graded -- `freeze` refuses it -- so this module is the
resolution path: `ensure(tickers, start=...)` pulls yfinance daily bars into an
append-only parquet and returns them.

THE FOUR RULES
==============
1. **Append-only.** A cached (symbol, date) row is never rewritten. A vendor
   that restates yesterday's close does not get to move a grade already read.
2. **One pull per ticker per UTC day.** A daily grader that runs five times
   hits the vendor once. The state lives beside the parquet.
3. **Only completed sessions.** A bar dated today (UTC) can be intraday; it is
   dropped and picked up by tomorrow's pull.
4. **A failure is counted, never raised and never silent.** The receipt carries
   `n_ok` / `n_failed` and the errors; the caller decides what a gap means.

WHAT IT DOES NOT DO
===================
* Prices are in LOCAL currency, unadjusted (`auto_adjust=False`). A `.T` name's
  return is a yen return; there is no FX leg. Stated on every receipt.
* No dividends. Over a 1-26 week book horizon that is a small, one-sided bias
  against high-yield names.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import pandas as pd

from backend import config as _config

logger = logging.getLogger(__name__)

COLUMNS = ["symbol", "date", "open", "high", "low", "close", "volume",
           "source", "pulled_utc"]

Downloader = Callable[[list[str], Any, Any], pd.DataFrame]


def base_dir() -> Path:
    return Path(_config.OPTIMUS_LEDGER_DIR) / "llm_portfolio"


def cache_path() -> Path:
    return base_dir() / "global_bars.parquet"


def receipt_path(day: Any, *, base: Optional[Path] = None) -> Path:
    return (base or base_dir()) / f"global_bars_receipt_{day}.json"


def _state_path(path: Path) -> Path:
    return path.with_name(path.stem + "_pulls.json")


def is_global_suffix(ticker: str) -> bool:
    t = str(ticker).upper()
    return any(t.endswith(s) for s in _config.BOOK_GLOBAL_SUFFIXES)


def needs_global(ticker: str, us_symbols: Optional[Iterable[str]]) -> bool:
    """True when the US panel cannot price this ticker.

    With no US universe supplied the answer is "only if it carries a non-US
    suffix" -- the conservative reading, since we cannot know what is absent.
    """
    if is_global_suffix(ticker):
        return True
    if us_symbols is None:
        return False
    return str(ticker).upper() not in set(us_symbols)


def read_cache(path: Optional[Path] = None) -> pd.DataFrame:
    p = Path(path) if path else cache_path()
    if not p.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_parquet(p)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _yf_download(tickers: list[str], start: Any, end: Any) -> pd.DataFrame:
    """yfinance -> long format. The ONLY network call in this module."""
    import yfinance as yf                                     # noqa: PLC0415

    wide = yf.download(tickers=list(tickers), start=str(start), end=str(end),
                       auto_adjust=False, group_by="ticker", progress=False,
                       threads=True)
    if wide is None or len(wide) == 0:
        return pd.DataFrame(columns=COLUMNS[:7])
    frames = []
    if isinstance(wide.columns, pd.MultiIndex):
        lvl0 = set(wide.columns.get_level_values(0))
        for t in tickers:
            if t not in lvl0:
                continue
            sub = wide[t].copy()
            sub.columns = [str(c).lower() for c in sub.columns]
            sub = sub.reset_index().rename(columns={"Date": "date",
                                                    "index": "date"})
            sub["symbol"] = t
            frames.append(sub)
    else:                                   # a single ticker, flat columns
        sub = wide.copy()
        sub.columns = [str(c).lower() for c in sub.columns]
        sub = sub.reset_index().rename(columns={"Date": "date", "index": "date"})
        sub["symbol"] = tickers[0]
        frames.append(sub)
    if not frames:
        return pd.DataFrame(columns=COLUMNS[:7])
    out = pd.concat(frames, ignore_index=True)
    keep = [c for c in COLUMNS[:7] if c in out.columns]
    out = out[keep].dropna(subset=["close"])
    return out


def ensure(tickers: Iterable[str], *, start: Any,
           path: Optional[Path] = None, today: Optional[date] = None,
           downloader: Optional[Downloader] = None,
           write_receipt: bool = True) -> pd.DataFrame:
    """Make sure the cache holds daily bars for `tickers` since `start`.

    Returns the cached rows for the requested tickers (dated >= start), with
    the run's receipt at `df.attrs["receipt"]`. Never raises on a vendor
    failure: a ticker that returned nothing is in `receipt["failed"]`.
    """
    p = Path(path) if path else cache_path()
    today = today or datetime.now(timezone.utc).date()
    start_ts = pd.Timestamp(start)
    want = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    want = [t for t in want if t != "CASH"]
    dl = downloader or _yf_download

    cache = read_cache(p)
    state_p = _state_path(p)
    try:
        state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    except ValueError:
        state = {}

    due = [t for t in want if state.get(t) != str(today)]
    skipped = len(want) - len(due)
    errors: list[str] = []
    new_rows = pd.DataFrame(columns=COLUMNS)
    if due:
        have = (cache[cache["symbol"].isin(due)].groupby("symbol")["date"].max()
                if not cache.empty else pd.Series(dtype="datetime64[ns]"))
        # One batch from the earliest date anyone needs; dedupe handles overlap.
        froms = [min(start_ts, have[t] + pd.Timedelta(days=1))
                 if t in have.index else start_ts for t in due]
        pull_from = min(froms).date()
        try:
            got = dl(due, pull_from, today + timedelta(days=1))
        except Exception as exc:                            # noqa: BLE001
            logger.warning("global_prices: pull of %d tickers failed: %s",
                           len(due), exc)
            errors.append(f"{type(exc).__name__}: {exc}")
            got = pd.DataFrame(columns=COLUMNS[:7])
        if got is not None and len(got):
            got = got.copy()
            d = pd.to_datetime(got["date"])
            if d.dt.tz is not None:
                d = d.dt.tz_localize(None)
            got["date"] = d.dt.normalize()
            got["symbol"] = got["symbol"].astype(str).str.upper()
            got = got[got["date"] < pd.Timestamp(today)]      # rule 3
            got["source"] = "yfinance"
            got["pulled_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if not cache.empty:
                seen = set(zip(cache["symbol"], cache["date"]))
                mask = [(s, d) not in seen for s, d in zip(got["symbol"], got["date"])]
                got = got[mask]                                # rule 1
            new_rows = got.drop_duplicates(["symbol", "date"], keep="first")
        for t in due:
            state[t] = str(today)
        if len(new_rows):
            cache = pd.concat([cache, new_rows[COLUMNS]], ignore_index=True) \
                if not cache.empty else new_rows[COLUMNS].reset_index(drop=True)
            cache = cache.sort_values(["symbol", "date"], kind="mergesort")
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".parquet.tmp")
            cache.to_parquet(tmp, index=False)
            os.replace(tmp, p)
        state_p.parent.mkdir(parents=True, exist_ok=True)
        state_p.write_text(json.dumps(state, indent=1, sort_keys=True),
                           encoding="utf-8")

    out = cache[cache["symbol"].isin(want) & (cache["date"] >= start_ts)] \
        if not cache.empty else pd.DataFrame(columns=COLUMNS)
    out = out.reset_index(drop=True)
    priced = set(out["symbol"]) if len(out) else set()
    failed = [t for t in want if t not in priced]
    receipt = {
        "receipt": "global_prices_ensure",
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "utc_day": str(today),
        "n_requested": len(want),
        "n_pulled_now": len(due),
        "n_skipped_pulled_today": skipped,
        "n_new_rows": int(len(new_rows)),
        "n_ok": len(priced),
        "n_failed": len(failed),
        "failed": failed,
        "errors": errors,
        "cache": str(p),
        "caveats": ["local currency, no FX leg",
                    "unadjusted closes (auto_adjust=False), no dividends",
                    "only sessions dated before the UTC day are cached"],
    }
    if write_receipt:
        try:
            rp = receipt_path(today, base=p.parent)
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps(receipt, indent=1), encoding="utf-8")
        except OSError as exc:
            logger.warning("global_prices: receipt not written (%s)", exc)
    out.attrs["receipt"] = receipt
    return out


def resolve(tickers: Iterable[str], *, path: Optional[Path] = None,
            today: Optional[date] = None,
            downloader: Optional[Downloader] = None) -> set[str]:
    """The subset of `tickers` that the cache can price after an ensure.

    This is `llm_portfolio.freeze`'s resolution path for a name the US panel
    does not hold.
    """
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=int(_config.BOOK_GLOBAL_HISTORY_DAYS))
    out = ensure(tickers, start=start, path=path, today=today,
                 downloader=downloader)
    return set(out["symbol"]) if len(out) else set()
