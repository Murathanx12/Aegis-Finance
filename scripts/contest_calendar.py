"""Contest desk DATA LAYER: markets, universe, global bars, earnings calendar.

The Bloomberg Global Trading Challenge 2026 (Oct 12 - Nov 13, relative P&L vs the
WLS index, long only, <= 20% a name). Orders are entered BY THE OWNER on a Bloomberg
Terminal; nothing here can place one. This module only reads free public data.

    python -m scripts.contest_calendar universe            # screen the proxy universe (Yahoo screener)
    python -m scripts.contest_calendar bars                # pull daily bars for the non-US universe
    python -m scripts.contest_calendar history             # past earnings dates for the non-US universe
    python -m scripts.contest_calendar calendar            # build today's calendar, print what changed
    python -m scripts.contest_calendar all                 # the four above, in order

WHAT A DATE'S STATUS MEANS (the project was burned by an aggregator date that had passed)
    CONFIRMED_EXCHANGE   the exchange's own schedule (JPX kessan files), with the file URL
    CONFIRMED_COMPANY    a company document (manual confirmations.csv row with a source URL)
    CONFIRMED_TERMINAL   the owner's Bloomberg export flagged the date as confirmed
    VENDOR_ANNOUNCED     an aggregator (Yahoo / Nasdaq) says the company announced it; NOT verified here
    VENDOR_ESTIMATE      an aggregator's own estimate
    ESTIMATED_PATTERN    our estimate from the last four years' same-quarter dates, spread shown
Only the three CONFIRMED_* statuses ever render as confirmed (`is_confirmed`).

Every network call is rate limited and carries a User-Agent. Every table write goes
through `safe_write_parquet`, which REFUSES to replace a larger table with a smaller one.

PRODUCT_EXPERIMENT; utility "contest rank, right tail". Nothing here is a claim of skill.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OPT = REPO / "backend" / "data" / "optimus"
CONTEST = OPT / "contest"
WLS_DIR = CONTEST / "wls"
UNIV_DIR = CONTEST / "universe"
BARS_DIR = CONTEST / "bars"
CAL_DIR = CONTEST / "calendar"
HIST_PATH = CONTEST / "earnings_history_global.parquet"
HIST_US_PATH = CONTEST / "earnings_history_us_recent.parquet"   # Yahoo stamps after the 8-K file ends
CONFIRM_CSV = CAL_DIR / "confirmations.csv"

HKT = ZoneInfo("Asia/Hong_Kong")
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128 Safari/537.36")
UA_SEC = "Aegis-Finance research contact mrthnabdullaev@gmail.com"   # SEC asks for a contact UA

CONTEST_START = date(2026, 10, 12)
CONTEST_END = date(2026, 11, 13)
POSITION_CAP = 0.20
LIQ_FLOOR_USD = 10e6          # median daily $ volume; a $200k ticket is then <= 2% of a day
PROXY_MIN_MCAP_USD = 300e6    # WLS small-cap floor PROXY (the real cut is Bloomberg's; UNCONFIRMED)
PULL_START = "2019-06-01"

CONFIRMED_STATUSES = ("CONFIRMED_EXCHANGE", "CONFIRMED_COMPANY", "CONFIRMED_TERMINAL")
STATUS_ORDER = {"CONFIRMED_EXCHANGE": 0, "CONFIRMED_COMPANY": 0, "CONFIRMED_TERMINAL": 0,
                "VENDOR_ANNOUNCED": 1, "VENDOR_ESTIMATE": 2, "ESTIMATED_PATTERN": 3}


class ShrinkRefused(RuntimeError):
    """A write would replace a larger table with a smaller one."""


class CalendarRefused(ValueError):
    """A calendar row that would present an unconfirmed date as confirmed."""


# ───────────────────────────── markets ─────────────────────────────

@dataclass(frozen=True)
class Market:
    code: str
    name: str
    suffixes: tuple
    tz: str
    open: str
    close: str
    currency: str
    fx: str                 # Yahoo FX ticker quoting LOCAL per USD ("" for USD)
    price_limit: str
    regions: tuple          # Yahoo screener region codes
    bbg_suffix: str         # Bloomberg exchange code as written on the Terminal
    lunch: str = ""
    cap_rank: int = 600     # how many names (by $ volume) we pull bars for


# Hours are regular sessions; limits from exchange rules as the builder knows them.
# UNVERIFIED unless marked: re-check on the Terminal (EXCH <GO>) before relying on one.
MARKETS: dict[str, Market] = {m.code: m for m in [
    Market("JP", "Japan (TSE)", (".T",), "Asia/Tokyo", "09:00", "15:30", "JPY", "JPY=X",
           "daily limit by price band (roughly +-15-30% of prior close); UNVERIFIED",
           ("jp",), "JT", lunch="11:30-12:30", cap_rank=800),
    Market("KR", "Korea (KRX)", (".KS", ".KQ"), "Asia/Seoul", "09:00", "15:30", "KRW", "KRW=X",
           "+-30% daily", ("kr",), "KS", cap_rank=500),
    Market("TW", "Taiwan (TWSE/TPEx)", (".TW", ".TWO"), "Asia/Taipei", "09:00", "13:30", "TWD",
           "TWD=X", "+-10% daily", ("tw",), "TT", cap_rank=500),
    Market("HK", "Hong Kong (HKEX)", (".HK",), "Asia/Hong_Kong", "09:30", "16:00", "HKD", "HKD=X",
           "no daily limit (VCM cooling-off on some names)", ("hk",), "HK",
           lunch="12:00-13:00", cap_rank=400),
    Market("CN", "China A (Stock Connect proxy)", (".SS", ".SZ"), "Asia/Shanghai", "09:30",
           "15:00", "CNY", "CNY=X",
           "+-10% main board; +-20% STAR/ChiNext; +-5% ST", ("cn",), "CH",
           lunch="11:30-13:00", cap_rank=600),
    Market("IN", "India (NSE)", (".NS", ".BO"), "Asia/Kolkata", "09:15", "15:30", "INR", "INR=X",
           "per-stock bands 2/5/10/20%; derivative names have dynamic bands; UNVERIFIED",
           ("in",), "IN", cap_rank=600),
    Market("ID", "Indonesia (IDX)", (".JK",), "Asia/Jakarta", "09:00", "16:00", "IDR", "IDR=X",
           "auto-rejection bands by price tier (~+-20-35% up; down band changed in 2025); UNVERIFIED",
           ("id",), "IJ", lunch="12:00-13:30 (Fri 11:30-14:00)", cap_rank=150),
    Market("EU", "Europe (LSE, Xetra, Euronext, SIX, Nordics, Milan, Madrid)",
           (".L", ".DE", ".PA", ".AS", ".SW", ".MI", ".MC", ".ST", ".CO", ".HE", ".OL", ".BR"),
           "Europe/Berlin", "09:00", "17:30", "EUR", "EUR=X",
           "no daily limit (volatility interruptions)",
           ("gb", "de", "fr", "nl", "ch", "it", "es", "se", "dk", "fi", "no", "be"), "",
           cap_rank=700),
    Market("US", "United States (NYSE/Nasdaq)", ("",), "America/New_York", "09:30", "16:00",
           "USD", "", "no daily limit (LULD pauses)", ("us",), "US", cap_rank=0),
]}

EU_SUFFIX_BBG = {".L": "LN", ".DE": "GY", ".PA": "FP", ".AS": "NA", ".SW": "SW", ".MI": "IM",
                 ".MC": "SM", ".ST": "SS", ".CO": "DC", ".HE": "FH", ".OL": "NO", ".BR": "BB"}
EU_SUFFIX_TZ = {".L": "Europe/London"}
EU_SUFFIX_HOURS = {".L": ("08:00", "16:30")}
CCY_FX = {"USD": "", "JPY": "JPY=X", "KRW": "KRW=X", "TWD": "TWD=X", "HKD": "HKD=X",
          "CNY": "CNY=X", "INR": "INR=X", "IDR": "IDR=X", "EUR": "EUR=X", "GBP": "GBP=X",
          "GBp": "GBP=X", "CHF": "CHF=X", "SEK": "SEK=X", "DKK": "DKK=X", "NOK": "NOK=X"}
OTC_EXCHANGES = ("PNK", "OQX", "OQB", "OID", "BTS", "OEM", "OGM")
ASIA = ("JP", "KR", "TW", "HK", "CN", "IN", "ID")


def market_of(symbol: str) -> str:
    s = str(symbol).upper()
    for code, m in MARKETS.items():
        if code == "US":
            continue
        for suf in m.suffixes:
            if s.endswith(suf.upper()):
                return code
    return "US"


def session_hours(symbol: str) -> tuple[str, str, str]:
    """(tz, open, close) local for this symbol's listing."""
    mk = MARKETS[market_of(symbol)]
    s = str(symbol).upper()
    for suf, tz in EU_SUFFIX_TZ.items():
        if s.endswith(suf.upper()):
            o, c = EU_SUFFIX_HOURS[suf]
            return tz, o, c
    return mk.tz, mk.open, mk.close


def hkt_hours(symbol_or_market: str, on: date) -> tuple[str, str]:
    """The session's open and close in Hong Kong time on a given local date (DST-aware)."""
    if symbol_or_market in MARKETS:
        mk = MARKETS[symbol_or_market]
        tz, o, c = mk.tz, mk.open, mk.close
    else:
        tz, o, c = session_hours(symbol_or_market)

    def conv(hm: str) -> str:
        h, m = map(int, hm.split(":"))
        t = datetime(on.year, on.month, on.day, h, m, tzinfo=ZoneInfo(tz)).astimezone(HKT)
        day = "" if t.date() == on else f" (+{(t.date() - on).days}d)"
        return t.strftime("%H:%M") + day
    return conv(o), conv(c)


def bloomberg_ticker(symbol: str) -> str:
    """Yahoo symbol -> the Terminal's '<ticker> <exch> Equity' form (best effort; CHECK)."""
    s = str(symbol).upper()
    mk = market_of(s)
    if mk == "US":
        return f"{s.replace('-', '/')} US Equity"
    base = s.rsplit(".", 1)[0]
    suf = "." + s.rsplit(".", 1)[1]
    if mk == "EU":
        return f"{base} {EU_SUFFIX_BBG.get(suf, '??')} Equity"
    if mk == "HK":
        return f"{int(base) if base.isdigit() else base} HK Equity"
    if mk == "CN":
        return f"{base} {'CH'} Equity"      # C1 (Shanghai) / C2 (Shenzhen) also used; CHECK
    if mk == "KR":
        return f"{base} KS Equity"
    if mk == "TW":
        return f"{base} TT Equity"
    if mk == "IN":
        return f"{base} IN Equity"
    if mk == "ID":
        return f"{base} IJ Equity"
    if mk == "JP":
        return f"{base} JT Equity"
    return s


# ───────────────────────────── safe writes ─────────────────────────────

def safe_write_parquet(df: pd.DataFrame, path: Path, *, allow_shrink: bool = False) -> dict:
    """Atomic write that REFUSES to replace a larger table with a smaller one."""
    path = Path(path)
    old_n = None
    if path.exists():
        try:
            import pyarrow.parquet as pq                       # noqa: PLC0415
            old_n = pq.ParquetFile(path).metadata.num_rows
        except Exception:                                      # noqa: BLE001
            old_n = len(pd.read_parquet(path))
    if old_n is not None and len(df) < old_n and not allow_shrink:
        raise ShrinkRefused(f"refusing to shrink {path.name}: {old_n} rows -> {len(df)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    back = len(pd.read_parquet(tmp, columns=[df.columns[0]])) if len(df.columns) else 0
    if back != len(df):
        tmp.unlink(missing_ok=True)
        raise ShrinkRefused(f"write verification failed for {path.name}: {back} != {len(df)}")
    os.replace(tmp, path)
    return {"path": str(path), "rows_before": old_n, "rows_after": len(df)}


def write_json(obj: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ───────────────────────────── HTTP ─────────────────────────────

_LAST_CALL: dict[str, float] = {}


def http_get(url: str, *, ua: str = UA_BROWSER, min_gap: float = 1.0, timeout: int = 40,
             headers: Optional[dict] = None, method: str = "GET",
             data: Optional[dict] = None) -> bytes:
    import requests                                            # noqa: PLC0415
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    wait = _LAST_CALL.get(host, 0) + min_gap - time.time()
    if wait > 0:
        time.sleep(wait)
    h = {"User-Agent": ua, "Accept": "*/*"}
    h.update(headers or {})
    r = requests.request(method, url, headers=h, timeout=timeout, data=data)
    _LAST_CALL[host] = time.time()
    r.raise_for_status()
    return r.content


# ───────────────────────────── FX ─────────────────────────────

def fx_rates_now(ccys: Iterable[str]) -> dict[str, float]:
    """LOCAL per USD, latest daily close (Yahoo)."""
    import yfinance as yf                                      # noqa: PLC0415
    tick = sorted({CCY_FX[c] for c in ccys if CCY_FX.get(c)})
    out: dict[str, float] = {"USD": 1.0}
    if not tick:
        return out
    px = yf.download(tick, period="10d", auto_adjust=False, progress=False, threads=True)["Close"]
    if isinstance(px, pd.Series):
        px = px.to_frame(tick[0])
    last = px.ffill().iloc[-1]
    for c in ccys:
        t = CCY_FX.get(c)
        if t and t in last.index and np.isfinite(last[t]):
            out[c] = float(last[t]) * (100.0 if c == "GBp" else 1.0)
    return out


# ───────────────────────────── universe (proxy + WLS export) ─────────────────────────────

def screen_region(region: str, min_mcap_local: float, *, page: int = 250,
                  max_pages: int = 40, sleep: float = 1.5) -> list[dict]:
    import yfinance as yf                                      # noqa: PLC0415
    from yfinance import EquityQuery as Q                      # noqa: PLC0415
    q = Q("and", [Q("eq", ["region", region]), Q("gt", ["intradaymarketcap", float(min_mcap_local)])])
    out: list[dict] = []
    for p in range(max_pages):
        r = yf.screen(q, size=page, offset=p * page, sortField="intradaymarketcap", sortAsc=False)
        quotes = r.get("quotes", []) if isinstance(r, dict) else []
        out.extend(quotes)
        time.sleep(sleep)
        total = r.get("total", 0) if isinstance(r, dict) else 0
        if len(quotes) < page or len(out) >= total:
            break
    return out


REGION_CCY = {"jp": "JPY", "kr": "KRW", "tw": "TWD", "hk": "HKD", "cn": "CNY", "in": "INR",
              "id": "IDR", "gb": "GBP", "de": "EUR", "fr": "EUR", "nl": "EUR", "ch": "CHF",
              "it": "EUR", "es": "EUR", "se": "SEK", "dk": "DKK", "fi": "EUR", "no": "NOK",
              "be": "EUR", "us": "USD"}


def build_proxy_universe(*, min_mcap_usd: float = PROXY_MIN_MCAP_USD,
                         today: Optional[date] = None) -> pd.DataFrame:
    """Every listed common stock above the WLS small-cap PROXY, with next-earnings fields.

    Membership is UNCONFIRMED_MEMBERSHIP for every row until the owner's WLS export lands.
    """
    today = today or date.today()
    fx = fx_rates_now(set(REGION_CCY.values()) | {"GBp"})
    rows = []
    for code, mk in MARKETS.items():
        for reg in mk.regions:
            ccy = REGION_CCY[reg]
            rate = fx.get(ccy)
            if not rate:
                print(f"  {reg}: no FX for {ccy}; skipped", flush=True)
                continue
            min_local = min_mcap_usd * rate * (100 if reg == "gb" else 1)
            try:
                quotes = screen_region(reg, min_local)
            except Exception as exc:                           # noqa: BLE001
                print(f"  {reg}: screen FAILED {type(exc).__name__}: {exc}", flush=True)
                continue
            n0 = len(rows)
            for q in quotes:
                if q.get("quoteType") not in (None, "EQUITY"):
                    continue
                sym = str(q.get("symbol", "")).upper()
                if not sym or market_of(sym) != code:
                    continue
                if code == "US" and q.get("exchange") in OTC_EXCHANGES:
                    continue            # OTC lines are not index members (the home listing is)
                qccy = q.get("currency") or ccy
                r = fx.get(qccy) or (fx.get("GBp") if qccy == "GBp" else None)
                if not r:
                    continue
                px = q.get("regularMarketPrice")
                adv = q.get("averageDailyVolume3Month")
                mcap = q.get("marketCap")
                rows.append({
                    "symbol": sym, "name": q.get("longName") or q.get("shortName"),
                    "market": code, "region": reg, "exchange": q.get("exchange"),
                    "currency": qccy, "fx_local_per_usd": r,
                    "price_local": px, "price_usd": (px / r) if px else None,
                    # Yahoo quotes London PRICES in pence (GBp) but market cap in pounds
                    "mcap_usd": (mcap / (r / 100.0 if qccy == "GBp" else r)) if mcap else None,
                    "adv_usd_3m": (adv * px / r) if (adv and px) else None,
                    "earn_ts_start": q.get("earningsTimestampStart"),
                    "earn_ts_end": q.get("earningsTimestampEnd"),
                    "earn_is_estimate": q.get("isEarningsDateEstimate"),
                    "tz": q.get("exchangeTimezoneName"),
                    "bbg_ticker": bloomberg_ticker(sym),
                    "membership": "UNCONFIRMED_MEMBERSHIP",
                    "screened_on": str(today),
                })
            print(f"  {code}/{reg}: {len(quotes)} quotes -> {len(rows) - n0} rows", flush=True)
    df = pd.DataFrame(rows).drop_duplicates("symbol")
    return apply_wls(df)


def load_wls_export(folder: Path = WLS_DIR) -> Optional[pd.DataFrame]:
    """The owner's Terminal export of WLS membership (MEMB / index members), CSV or Excel.

    Accepts any file in the folder; picks the newest. Finds the ticker column by name
    (Ticker / Security / Member Ticker and Exchange Code) or by the ' Equity' suffix.
    Returns a frame with `bbg_key` = '<TICKER> <EXCH>' upper, or None when absent.
    """
    folder = Path(folder)
    if not folder.exists():
        return None
    files = sorted([p for p in folder.iterdir() if p.suffix.lower() in (".csv", ".xlsx", ".xls")],
                   key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    f = files[-1]
    raw = pd.read_csv(f) if f.suffix.lower() == ".csv" else pd.read_excel(f)
    col = None
    for c in raw.columns:
        cl = str(c).lower()
        if any(k in cl for k in ("ticker", "security", "member")):
            col = c
            break
    if col is None:
        for c in raw.columns:
            if raw[c].astype(str).str.contains(r"\sEquity$", case=False, regex=True).mean() > 0.5:
                col = c
                break
    if col is None:
        raise ValueError(f"WLS export {f.name}: no ticker column found in {list(raw.columns)}")
    keys = raw[col].astype(str).str.upper().str.replace(r"\s+EQUITY$", "", regex=True).str.strip()
    out = pd.DataFrame({"bbg_key": keys})
    out["source_file"] = f.name
    return out[out.bbg_key.str.len() > 0].drop_duplicates("bbg_key")


def _bbg_key(bbg_ticker: str) -> str:
    return re.sub(r"\s+EQUITY$", "", str(bbg_ticker).upper()).strip()


def apply_wls(univ: pd.DataFrame, folder: Path = WLS_DIR) -> pd.DataFrame:
    """Mark membership CONFIRMED / NOT_IN_WLS from the export; UNCONFIRMED when none exists."""
    univ = univ.copy()
    wls = load_wls_export(folder)
    if wls is None or univ.empty:
        univ["membership"] = "UNCONFIRMED_MEMBERSHIP"
        return univ
    keys = set(wls.bbg_key)
    # the Terminal writes composite codes (US, JP, HK...) and sometimes exchange codes; match both
    alt = {"JT": "JP", "C1": "CH", "C2": "CH", "KQ": "KS", "UN": "US", "UW": "US"}
    keys |= {f"{k.rsplit(' ', 1)[0]} {alt.get(k.rsplit(' ', 1)[-1], k.rsplit(' ', 1)[-1])}"
             for k in keys if " " in k}
    def mark(bt: str) -> str:
        k = _bbg_key(bt)
        if " " in k:
            k2 = f"{k.rsplit(' ', 1)[0]} {alt.get(k.rsplit(' ', 1)[-1], k.rsplit(' ', 1)[-1])}"
        else:
            k2 = k
        return "CONFIRMED_WLS" if (k in keys or k2 in keys) else "NOT_IN_WLS_EXPORT"
    univ["membership"] = univ["bbg_ticker"].map(mark)
    return univ


def latest_universe() -> Optional[pd.DataFrame]:
    files = sorted(UNIV_DIR.glob("universe_*.parquet"))
    if not files:
        return None
    return apply_wls(pd.read_parquet(files[-1]))


# ───────────────────────────── bars ─────────────────────────────

def _yf_download(tickers: list[str], start: Any, end: Any) -> pd.DataFrame:
    """Reuses the project's global_prices downloader (yfinance, unadjusted, long format)."""
    from backend.services.global_prices import _yf_download as dl   # noqa: PLC0415
    return dl(tickers, start, end)


def bars_path(market: str) -> Path:
    return BARS_DIR / f"bars_{market}.parquet"


def pull_bars(symbols: list[str], market: str, *, start: str = PULL_START,
              batch: int = 40, sleep: float = 3.0,
              downloader: Optional[Callable] = None, today: Optional[date] = None) -> dict:
    """Append-only union into bars_<market>.parquet. Only sessions before today (UTC)."""
    dl = downloader or _yf_download
    today = today or datetime.now(timezone.utc).date()
    p = bars_path(market)
    old = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    frames, failed = [], []
    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        try:
            got = dl(chunk, start, today + timedelta(days=1))
        except Exception as exc:                               # noqa: BLE001
            failed.extend(chunk)
            print(f"  {market} batch {i // batch}: FAILED {type(exc).__name__}: {exc}", flush=True)
            time.sleep(sleep * 3)
            continue
        if got is None or got.empty:
            failed.extend(chunk)
        else:
            got = got.copy()
            d = pd.to_datetime(got["date"])
            if getattr(d.dt, "tz", None) is not None:
                d = d.dt.tz_localize(None)
            got["date"] = d.dt.normalize()
            got["symbol"] = got["symbol"].astype(str).str.upper()
            got = got[got["date"] < pd.Timestamp(today)]
            failed.extend(sorted(set(chunk) - set(got["symbol"])))
            frames.append(got)
        if (i // batch) % 5 == 0:
            print(f"  {market}: {min(i + batch, len(symbols))}/{len(symbols)} requested", flush=True)
        time.sleep(sleep)
    new = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if new.empty and old.empty:
        return {"market": market, "rows": 0, "failed": failed}
    for c in ("open", "high", "low", "close", "volume"):
        if c in new.columns:
            new[c] = pd.to_numeric(new[c], errors="coerce").astype("float64")
    allb = pd.concat([old, new], ignore_index=True) if not old.empty else new
    allb = allb.drop_duplicates(["symbol", "date"], keep="first").sort_values(["symbol", "date"])
    rec = safe_write_parquet(allb.reset_index(drop=True), p)
    rec.update(market=market, n_symbols=int(allb.symbol.nunique()), failed=failed,
               n_failed=len(failed), last_date=str(allb.date.max().date()))
    return rec


# ───────────────────────────── reused tickers (stitched histories) ─────────────────────────────

#: market -> the audit `stitched_tickers.split_stitched` returned on the last load.
STITCH_AUDIT: dict[str, dict] = {}
_NO_REGISTRANTS = {"by_ticker": {}, "cik_first": None, "sources": ["none (non-US listing)"]}


def cut_stitched(long: pd.DataFrame, market: str, *, regs: Optional[dict] = None) -> pd.DataFrame:
    """Refuse a reused ticker's OLD company's history (backend.services.stitched_tickers).

    Every segment before a STITCHED / GAP_UNRESOLVED gap is renamed `SYM#k`, so the living
    symbol's history starts at its new company's first bar and every trailing feature that
    would reach across the hole is NaN, never the dead company's prices. US names use the
    SEC registrant evidence and the SPY calendar; other markets use their own file's session
    calendar and the price-jump evidence only (no registrant data on disk for them).
    Rows are never dropped and prices never changed. The audit is kept in STITCH_AUDIT.
    """
    from backend.services import stitched_tickers as st        # noqa: PLC0415
    if long.empty:
        STITCH_AUDIT[market] = {"candidates": 0, "cut_symbols": []}
        return long
    # the gap is counted in market sessions: SPY's for the US when present, otherwise a
    # weekday calendar (a frame of one name would otherwise measure its hole in its own days)
    cal_sym = "SPY" if (market == "US" and (long.symbol == "SPY").any()) else f"__weekdays_{market}__"
    b = long
    if cal_sym.startswith("__"):
        d = pd.to_datetime(long["date"])
        cal = pd.DataFrame({"symbol": cal_sym, "date": pd.bdate_range(d.min(), d.max()), "src": "calendar"})
        b = pd.concat([long, cal], ignore_index=True)
    if market == "US":
        out, audit = st.split_stitched(b, src_col="src", regs=regs, market=cal_sym)
    else:
        out, audit = st.split_stitched(b, src_col="src", regs=regs or _NO_REGISTRANTS, market=cal_sym)
    out = out[out.symbol != cal_sym].reset_index(drop=True)
    STITCH_AUDIT[market] = audit
    return out


def stitched_cut_symbols() -> set[str]:
    """Every living symbol whose older history was cut on the last load."""
    return {s for a in STITCH_AUDIT.values() for s in a.get("cut_symbols", [])}


def load_bars_usd(markets: Iterable[str], *, include_us: bool = True,
                  us_symbols: Optional[Iterable[str]] = None) -> pd.DataFrame:
    """Long frame symbol,date,open,close,volume, prices converted to USD with the day's FX.

    Every market passes through `cut_stitched` first: a reused ticker's history before its
    new company's first bar is renamed `SYM#k` and never reaches the living symbol."""
    frames = []
    fxp = bars_path("FX")
    fx = pd.read_parquet(fxp) if fxp.exists() else pd.DataFrame(columns=["symbol", "date", "close"])
    fxw = fx.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill() \
        if not fx.empty else pd.DataFrame()
    for m in markets:
        p = bars_path(m)
        if m == "US" or not p.exists():
            continue
        b = pd.read_parquet(p, columns=["symbol", "date", "open", "close", "volume"])
        b["src"] = p.stem
        b = cut_stitched(b, m).drop(columns=["src"])
        univ = latest_universe()
        ccy_map = dict(zip(univ.symbol, univ.currency)) if univ is not None else {}
        b["ccy"] = b.symbol.map(ccy_map).fillna(_default_ccy(m))
        for ccy, g in b.groupby("ccy"):
            t = CCY_FX.get(ccy, "")
            if not t:
                frames.append(g)
                continue
            if fxw.empty or t not in fxw.columns:
                continue
            rate = fxw[t].reindex(pd.DatetimeIndex(g.date)).ffill().to_numpy()
            rate = rate * (100.0 if ccy == "GBp" else 1.0)
            g = g.copy()
            g["open"] = g["open"].to_numpy() / rate
            g["close"] = g["close"].to_numpy() / rate
            frames.append(g)
    if not fx.empty:                     # the USD benchmarks live in the FX file
        bm = fx[fx.symbol.isin(["ACWI", "URTH"])]
        if len(bm):
            frames.append(bm[["symbol", "date", "open", "close", "volume"]])
    if include_us:
        cols = ["symbol", "date", "open", "close", "volume"]
        us = []
        for up in (OPT / "prices_deep" / "bars.parquet", OPT / "prices_deep" / "bars_delisted.parquet",
                   bars_path("US")):
            if up.exists():
                x = pd.read_parquet(up, columns=cols)
                x["src"] = up.stem
                us.append(x)
        u = pd.concat(us, ignore_index=True)
        u["date"] = pd.to_datetime(u["date"]).dt.normalize()
        u = u.drop_duplicates(["symbol", "date"])
        if us_symbols is not None:                 # keep the old segments too: the cut needs them
            keep = set(us_symbols)
            u = u[u.symbol.isin(keep)]
        u = cut_stitched(u, "US").drop(columns=["src"])
        frames.append(u)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if "ccy" in out.columns:
        out = out.drop(columns=["ccy"])
    out["date"] = pd.to_datetime(out["date"])
    return out


def _default_ccy(m: str) -> str:
    return MARKETS[m].currency if m in MARKETS else "USD"


# ───────────────────────────── past earnings (global) ─────────────────────────────

def pull_earnings_history(symbols: list[str], *, limit: int = 28, sleep: float = 1.0,
                          fetch: Optional[Callable] = None, path: Optional[Path] = None) -> dict:
    """Yahoo earnings dates (past AND next) per symbol, appended to HIST_PATH.

    VENDOR data: the reaction sessions it implies are checked against bars later; a
    future row is at best VENDOR_ANNOUNCED, never confirmed.
    """
    import yfinance as yf                                      # noqa: PLC0415
    fetch = fetch or (lambda s: yf.Ticker(s).get_earnings_dates(limit=limit))
    path = Path(path) if path else HIST_PATH
    old = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    done_today = set()
    if not old.empty and "pulled_on" in old.columns:
        done_today = set(old.loc[old.pulled_on == str(date.today()), "symbol"])
    rows, failed = [], []
    todo = [s for s in symbols if s not in done_today]
    for i, s in enumerate(todo):
        try:
            d = fetch(s)
        except Exception as exc:                               # noqa: BLE001
            failed.append(s)
            if "Rate" in type(exc).__name__ or "429" in str(exc):
                print("  rate limited; sleeping 120s", flush=True)
                time.sleep(120)
            d = None
        if d is not None and len(d):
            d = d.reset_index()
            tcol = d.columns[0]
            for _, r in d.iterrows():
                ts = pd.Timestamp(r[tcol])
                rows.append({"symbol": s, "ts_utc": ts.tz_convert("UTC") if ts.tzinfo else ts.tz_localize("UTC"),
                             "eps_est": r.get("EPS Estimate"), "eps_rep": r.get("Reported EPS"),
                             "surprise_pct": r.get("Surprise(%)"),
                             "pulled_on": str(date.today()), "source": "yahoo_earnings_dates"})
        elif d is not None:
            failed.append(s)
        if i % 100 == 0:
            print(f"  history {i}/{len(todo)} (failed {len(failed)})", flush=True)
        time.sleep(sleep)
    new = pd.DataFrame(rows)
    if not new.empty:
        new["ts_utc"] = pd.to_datetime(new["ts_utc"], utc=True)
        for c in ("eps_est", "eps_rep", "surprise_pct"):
            new[c] = pd.to_numeric(new[c], errors="coerce")
    allh = pd.concat([old, new], ignore_index=True) if not old.empty else new
    if allh.empty:
        return {"rows": 0, "failed": failed}
    allh["ts_utc"] = pd.to_datetime(allh["ts_utc"], utc=True)
    # a later pull supersedes an earlier one for the same (symbol, ts) - keep the newest
    allh = allh.sort_values("pulled_on").drop_duplicates(["symbol", "ts_utc"], keep="last")
    rec = safe_write_parquet(allh.reset_index(drop=True), path)
    rec.update(n_symbols=int(allh.symbol.nunique()), n_failed=len(failed), failed=failed[:50])
    return rec


# ───────────────────────────── past earnings (US, SEC 8-K item 2.02) ─────────────────────────────

def us_8k_events(asof: Optional[date] = None) -> pd.DataFrame:
    """Scheduled-print candidates from EDGAR 8-K item 2.02 acceptance times (PRIMARY: SEC).

    Returns symbol, ts_utc, amc (bool), source. Only filings accepted on/before `asof`.
    """
    e = pd.read_parquet(OPT / "edgar_8k" / "eightk_items.parquet",
                        columns=["ticker", "acceptance_datetime", "items_joined"])
    e = e[e.items_joined.fillna("").str.contains("2.02", regex=False)].copy()
    acc = pd.to_datetime(e.acceptance_datetime, utc=True, errors="coerce")
    e = e.assign(ts_utc=acc).dropna(subset=["ts_utc"])
    if asof is not None:
        e = e[e.ts_utc.dt.tz_convert("America/New_York").dt.date <= asof]
    out = pd.DataFrame({"symbol": e.ticker.astype(str).str.upper(), "ts_utc": e.ts_utc,
                        "source": "sec_8k_2.02"})
    return out.drop_duplicates(["symbol", "ts_utc"])


# ───────────────────────────── event -> sessions ─────────────────────────────

def event_sessions(ts_utc: pd.Timestamp, symbol: str, sessions: pd.DatetimeIndex) -> tuple:
    """(pre_idx, react_idx, timing) into `sessions` (the name's own trading days).

    timing: AMC (after the local close -> reacts next session), BMO (before the open ->
    reacts that session), INTRA (during the session -> reacts that session, partly),
    UNKNOWN (a midnight stamp: we cannot tell -> pre = last session before the local
    date, react = first session AFTER it, i.e. a two-session hold covering both cases).
    """
    tz, o, c = session_hours(symbol)
    loc = pd.Timestamp(ts_utc).tz_convert(tz)
    d = pd.Timestamp(loc.date())
    mins = loc.hour * 60 + loc.minute
    oh, om = map(int, o.split(":"))
    ch, cm = map(int, c.split(":"))
    if mins == 0 and loc.second == 0:
        timing = "UNKNOWN"
    elif mins >= ch * 60 + cm:
        timing = "AMC"
    elif mins < oh * 60 + om:
        timing = "BMO"
    else:
        timing = "INTRA"
    ge = int(sessions.searchsorted(d, side="left"))    # first session >= d
    gt = int(sessions.searchsorted(d, side="right"))   # first session > d
    if timing == "AMC":
        pre, react = gt - 1, gt
        if pre < 0 or sessions[pre] != d:              # announced on a non-trading day
            pre = gt - 1
    elif timing in ("BMO", "INTRA"):
        pre, react = ge - 1, ge
    else:
        pre, react = ge - 1, gt
    return pre, react, timing


# ───────────────────────────── the calendar ─────────────────────────────

def estimate_from_history(hist_ts: pd.Series, asof: date, *, horizon_days: int = 120) -> Optional[dict]:
    """ESTIMATED_PATTERN: the next print after `asof` from the last four years' same quarter.

    Uses only prints on/before `asof`. For each prior year k=1..4, find the print closest
    to (anchor - 365k) where anchor = last print + 91d, and project it forward 364k days
    (52 weeks keeps the weekday). Estimate = median; spread = max - min of the projections.
    """
    ts = pd.to_datetime(hist_ts, utc=True)
    ds = sorted({t.date() for t in ts if t.date() <= asof})
    if not ds:
        return None
    last = ds[-1]
    anchor = last + timedelta(days=91)
    while anchor <= asof:
        anchor += timedelta(days=91)
    proj = []
    for k in range(1, 5):
        target = anchor - timedelta(days=365 * k)
        near = min(ds, key=lambda x: abs((x - target).days))
        if abs((near - target).days) <= 30:
            p = near + timedelta(days=364 * k)
            if p > asof:
                proj.append(p)
    if proj:
        proj.sort()
        est = proj[len(proj) // 2]
        spread = (proj[-1] - proj[0]).days
        conf = "HIGH" if (len(proj) >= 3 and spread <= 7) else ("MEDIUM" if spread <= 14 else "LOW")
    else:
        est, spread, conf = anchor, 21, "LOW"
    if (est - asof).days > horizon_days:
        return None
    return {"date": est, "spread_days": int(spread), "n_years": len(proj), "confidence": conf}


def usual_timing(hist_ts: pd.Series, symbol: str) -> str:
    """Majority timing of the last four prints (AMC/BMO/INTRA/UNKNOWN)."""
    tz, o, c = session_hours(symbol)
    ts = pd.to_datetime(hist_ts, utc=True).sort_values().tail(4)
    lab = []
    for t in ts:
        loc = t.tz_convert(tz)
        mins = loc.hour * 60 + loc.minute
        oh, om = map(int, o.split(":"))
        ch, cm = map(int, c.split(":"))
        lab.append("UNKNOWN" if mins == 0 else "AMC" if mins >= ch * 60 + cm
                   else "BMO" if mins < oh * 60 + om else "INTRA")
    return pd.Series(lab).mode().iloc[0] if lab else "UNKNOWN"


def fetch_jpx_schedule() -> pd.DataFrame:
    """CONFIRMED_EXCHANGE: JPX's 'scheduled dates for earnings announcements' files."""
    base = "https://www.jpx.co.jp"
    html = http_get(base + "/listing/event-schedules/financial-announcement/index.html",
                    min_gap=2.0).decode("utf-8", "replace")
    links = sorted(set(re.findall(r'href="([^"]*kessan[^"]*\.xlsx?)"', html)))
    frames = []
    for ln in links:
        url = base + ln if ln.startswith("/") else ln
        raw = pd.read_excel(io.BytesIO(http_get(url, min_gap=2.0)), header=None)
        hdr = raw.index[raw.iloc[:, 1].astype(str).str.contains("Code", na=False)]
        if len(hdr) == 0:
            continue
        body = raw.iloc[hdr[0] + 1:, [0, 1, 3, 7, 8]].copy()
        body.columns = ["date", "code", "name", "period_jp", "period"]
        body["date"] = pd.to_datetime(body["date"], errors="coerce")
        body = body.dropna(subset=["date"])
        body["symbol"] = body["code"].astype(str).str.strip().str.upper() + ".T"
        body["source_url"] = url
        frames.append(body[["symbol", "name", "date", "period", "source_url"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["symbol", "name", "date", "period", "source_url"])


def fetch_nasdaq_day(d: date) -> pd.DataFrame:
    """VENDOR_ANNOUNCED (Nasdaq's public calendar; its data vendor is not the company)."""
    raw = http_get(f"https://api.nasdaq.com/api/calendar/earnings?date={d.isoformat()}",
                   headers={"Accept": "application/json"}, min_gap=1.5)
    js = json.loads(raw.decode("utf-8", "replace"))
    rows = ((js.get("data") or {}).get("rows")) or []
    tmap = {"time-pre-market": "BMO", "time-after-hours": "AMC"}
    return pd.DataFrame([{"symbol": str(r.get("symbol", "")).upper(), "date": pd.Timestamp(d),
                          "timing": tmap.get(r.get("time"), "UNKNOWN"),
                          "name": r.get("name"), "source_url": f"api.nasdaq.com/api/calendar/earnings?date={d}"}
                         for r in rows])


def load_confirmations(path: Path = CONFIRM_CSV) -> pd.DataFrame:
    """Manual confirmations: symbol,date,timing,source_url[,status]. A row without a URL is refused."""
    cols = ["symbol", "date", "timing", "source_url", "status"]
    if not Path(path).exists():
        return pd.DataFrame(columns=cols)
    c = pd.read_csv(path)
    c["symbol"] = c["symbol"].astype(str).str.upper().str.strip()
    c["date"] = pd.to_datetime(c["date"], errors="coerce")
    if "timing" not in c.columns:
        c["timing"] = "UNKNOWN"
    if "status" not in c.columns:
        c["status"] = "CONFIRMED_COMPANY"
    bad = c["source_url"].isna() | (c["source_url"].astype(str).str.len() < 8) | c["date"].isna()
    if bad.any():
        print(f"  confirmations: {int(bad.sum())} row(s) refused (no source URL or date): "
              f"{c.loc[bad, 'symbol'].tolist()}", flush=True)
    c = c[~bad]
    c.loc[~c["status"].isin(CONFIRMED_STATUSES), "status"] = "CONFIRMED_COMPANY"
    return c[cols]


def merge_calendar(candidates: pd.DataFrame) -> pd.DataFrame:
    """One row per symbol: the best-status date, with every source listed and conflicts flagged.

    `candidates`: symbol, date, status, timing, source, spread_days, confidence.
    """
    if candidates.empty:
        return candidates.assign(is_confirmed=pd.Series(dtype=bool))
    c = candidates.copy()
    unknown = ~c["status"].isin(STATUS_ORDER)
    if unknown.any():
        raise CalendarRefused(f"unknown statuses: {sorted(c.loc[unknown, 'status'].unique())}")
    c["rank"] = c["status"].map(STATUS_ORDER)
    c["date"] = pd.to_datetime(c["date"]).dt.normalize()
    out = []
    for sym, g in c.groupby("symbol"):
        g = g.sort_values(["rank", "date"])
        best = g.iloc[0].to_dict()
        others = g.iloc[1:]
        dev = (others["date"] - best["date"]).abs().dt.days if len(others) else pd.Series(dtype=float)
        best["conflict_days"] = int(dev.max()) if len(dev) else 0
        best["sources"] = "; ".join(f"{r.status}:{r.date.date()}:{r.source}" for r in g.itertuples())
        tim = g.loc[g["timing"].isin(["AMC", "BMO", "INTRA"]), "timing"]
        if best.get("timing") in (None, "UNKNOWN") and len(tim):
            best["timing"] = tim.iloc[0]
        out.append(best)
    m = pd.DataFrame(out).drop(columns=["rank"])
    m["is_confirmed"] = m["status"].isin(CONFIRMED_STATUSES)
    return m.sort_values(["date", "symbol"]).reset_index(drop=True)


def assert_calendar_honest(cal: pd.DataFrame) -> None:
    """A row may say confirmed only with a CONFIRMED_* status and a source."""
    if cal.empty:
        return
    bad = cal["is_confirmed"] & ~cal["status"].isin(CONFIRMED_STATUSES)
    if bad.any():
        raise CalendarRefused(f"unconfirmed dates shown as confirmed: {cal.loc[bad, 'symbol'].tolist()}")


def build_calendar(asof: date, *, window: tuple[date, date] = (CONTEST_START, CONTEST_END),
                   use_network: bool = True, universe: Optional[pd.DataFrame] = None,
                   hist_global: Optional[pd.DataFrame] = None,
                   us_events: Optional[pd.DataFrame] = None) -> tuple[pd.DataFrame, dict]:
    """Every universe name with an expected print inside `window`, best source first."""
    w0, w1 = pd.Timestamp(window[0]), pd.Timestamp(window[1])
    universe = universe if universe is not None else latest_universe()
    if universe is None:
        raise FileNotFoundError("no universe file; run `python -m scripts.contest_calendar universe`")
    syms = set(universe.symbol)
    cands, receipt = [], {"asof": str(asof), "window": [str(window[0]), str(window[1])], "sources": {}}

    # 1) pattern estimates: US from SEC 8-K, the rest from the Yahoo history (PIT: <= asof)
    us_events = us_events if us_events is not None else us_8k_events(asof)
    hist_global = hist_global if hist_global is not None else (
        pd.read_parquet(HIST_PATH) if HIST_PATH.exists() else pd.DataFrame(columns=["symbol", "ts_utc"]))
    hg = hist_global[pd.to_datetime(hist_global.ts_utc, utc=True).dt.date <= asof] \
        if not hist_global.empty else hist_global
    past = pd.concat([us_events[["symbol", "ts_utc"]], hg[["symbol", "ts_utc"]]], ignore_index=True)
    past = past[past.symbol.isin(syms)]
    n_est = 0
    for sym, g in past.groupby("symbol"):
        e = estimate_from_history(g.ts_utc, asof)
        if e is None:
            continue
        cands.append({"symbol": sym, "date": pd.Timestamp(e["date"]), "status": "ESTIMATED_PATTERN",
                      "timing": usual_timing(g.ts_utc, sym), "source": f"pattern_{e['n_years']}y",
                      "spread_days": e["spread_days"], "confidence": e["confidence"]})
        n_est += 1
    receipt["sources"]["ESTIMATED_PATTERN"] = n_est

    if use_network and asof >= date.today() - timedelta(days=1):
        # 2) Yahoo screener's next-earnings fields (vendor)
        n = 0
        for r in universe.itertuples():
            ts = getattr(r, "earn_ts_start", None)
            if ts is None or not np.isfinite(ts):
                continue
            t = pd.Timestamp(int(ts), unit="s", tz="UTC")
            tz, _, _ = session_hours(r.symbol)
            loc = t.tz_convert(tz)
            st = "VENDOR_ESTIMATE" if bool(getattr(r, "earn_is_estimate", True)) else "VENDOR_ANNOUNCED"
            cands.append({"symbol": r.symbol, "date": pd.Timestamp(loc.date()), "status": st,
                          "timing": "UNKNOWN", "source": "yahoo_screener", "spread_days": np.nan,
                          "confidence": "VENDOR"})
            n += 1
        receipt["sources"]["yahoo_screener"] = n
        # 3) Nasdaq calendar per day in the window (US, vendor, gives BMO/AMC)
        n = 0
        d = max(window[0], asof)
        errs = []
        while d <= window[1]:
            if d.weekday() < 5:
                try:
                    nd = fetch_nasdaq_day(d)
                    for r in nd.itertuples():
                        if r.symbol in syms:
                            cands.append({"symbol": r.symbol, "date": r.date, "status": "VENDOR_ANNOUNCED",
                                          "timing": r.timing, "source": "nasdaq", "spread_days": np.nan,
                                          "confidence": "VENDOR"})
                            n += 1
                except Exception as exc:                       # noqa: BLE001
                    errs.append(f"{d}: {type(exc).__name__}")
            d += timedelta(days=1)
        receipt["sources"]["nasdaq"] = n
        receipt["nasdaq_errors"] = errs
        # 4) JPX exchange schedule (CONFIRMED_EXCHANGE)
        try:
            jp = fetch_jpx_schedule()
            jp = jp[jp.symbol.isin(syms)]
            for r in jp.itertuples():
                cands.append({"symbol": r.symbol, "date": r.date, "status": "CONFIRMED_EXCHANGE",
                              "timing": "UNKNOWN", "source": r.source_url, "spread_days": 0,
                              "confidence": "EXCHANGE"})
            receipt["sources"]["jpx"] = int(len(jp))
        except Exception as exc:                               # noqa: BLE001
            receipt["sources"]["jpx"] = f"FAILED {type(exc).__name__}: {exc}"
    # 5) manual confirmations (company / Terminal)
    conf = load_confirmations()
    for r in conf.itertuples():
        cands.append({"symbol": r.symbol, "date": r.date, "status": r.status, "timing": r.timing,
                      "source": r.source_url, "spread_days": 0, "confidence": "PRIMARY"})
    receipt["sources"]["confirmations_csv"] = int(len(conf))

    cand = pd.DataFrame(cands)
    if cand.empty:
        return cand, receipt
    cand = cand[(cand.date >= w0 - pd.Timedelta(days=3)) & (cand.date <= w1 + pd.Timedelta(days=3))]
    cal = merge_calendar(cand)
    cal = cal[(cal.date >= w0) & (cal.date <= w1)].reset_index(drop=True)
    cal = cal.merge(universe[["symbol", "name", "market", "bbg_ticker", "membership", "adv_usd_3m"]],
                    on="symbol", how="left")
    assert_calendar_honest(cal)
    receipt["n_names"] = int(len(cal))
    receipt["by_status"] = cal.status.value_counts().to_dict()
    receipt["by_market"] = cal.market.value_counts().to_dict()
    receipt["n_confirmed"] = int(cal.is_confirmed.sum())
    return cal, receipt


def diff_calendars(old: pd.DataFrame, new: pd.DataFrame) -> list[str]:
    lines = []
    o = old.set_index("symbol") if not old.empty else pd.DataFrame()
    n = new.set_index("symbol")
    for s in sorted(set(n.index) - set(o.index)):
        lines.append(f"NEW      {s} {n.at[s, 'date'].date()} {n.at[s, 'status']}")
    for s in sorted(set(o.index) - set(n.index)):
        lines.append(f"DROPPED  {s} (was {o.at[s, 'date'].date()} {o.at[s, 'status']})")
    for s in sorted(set(o.index) & set(n.index)):
        a, b = o.loc[s], n.loc[s]
        if a["date"] != b["date"] or a["status"] != b["status"]:
            lines.append(f"CHANGED  {s} {a['date'].date()} {a['status']} -> {b['date'].date()} {b['status']}")
    return lines


# ───────────────────────────── CLI ─────────────────────────────

def cmd_universe() -> None:
    u = build_proxy_universe()
    p = UNIV_DIR / f"universe_{date.today()}.parquet"
    rec = safe_write_parquet(u, p, allow_shrink=True)   # a fresh daily file; shrink vs yesterday is printed
    prev = sorted(UNIV_DIR.glob("universe_*.parquet"))
    if len(prev) >= 2:
        n_prev = len(pd.read_parquet(prev[-2], columns=["symbol"]))
        if len(u) < 0.8 * n_prev:
            print(f"WARNING universe shrank {n_prev} -> {len(u)}: a screen failed; check the log", flush=True)
    summ = u.groupby("market").agg(n=("symbol", "size"),
                                   liquid=("adv_usd_3m", lambda s: int((s >= LIQ_FLOOR_USD).sum())))
    print(summ.to_string())
    write_json({"written_utc": utc_stamp(), **rec, "by_market": summ.to_dict(),
                "membership": "UNCONFIRMED_MEMBERSHIP unless a WLS export is in contest/wls/",
                "proxy_rule": f"market cap >= ${PROXY_MIN_MCAP_USD / 1e6:.0f}M (Yahoo screener)"},
               UNIV_DIR / f"universe_{date.today()}_receipt.json")


def pull_targets(u: pd.DataFrame) -> dict[str, list[str]]:
    out = {}
    for code, mk in MARKETS.items():
        if code == "US":
            continue
        g = u[(u.market == code) & (u.adv_usd_3m >= LIQ_FLOOR_USD * 0.5)]
        out[code] = g.sort_values("adv_usd_3m", ascending=False).symbol.head(mk.cap_rank).tolist()
    # US names the prices_deep panel lacks
    us_have = set(pd.read_parquet(OPT / "prices_deep" / "bars.parquet", columns=["symbol"]).symbol.unique())
    g = u[(u.market == "US") & (u.adv_usd_3m >= LIQ_FLOOR_USD) & ~u.symbol.isin(us_have)]
    out["US"] = g.symbol.tolist()
    return out


def cmd_bars() -> None:
    u = latest_universe()
    if u is None:
        raise SystemExit("no universe; run `universe` first")
    fx_syms = sorted({t for t in CCY_FX.values() if t}) + ["ACWI", "URTH", "SPY"]
    recs = {"FX": pull_bars(fx_syms, "FX")}
    for m, syms in pull_targets(u).items():
        print(f"== {m}: {len(syms)} symbols", flush=True)
        if syms:
            recs[m] = pull_bars(syms, m)
            print(f"   {m}: {recs[m].get('n_symbols')} symbols, {recs[m].get('rows_after')} rows, "
                  f"failed {recs[m].get('n_failed')}", flush=True)
    write_json({"written_utc": utc_stamp(), "receipts": recs,
                "caveats": ["local-currency bars; USD via the day's Yahoo FX close in load_bars_usd",
                            "unadjusted (auto_adjust=False)", "only sessions before the UTC day"]},
               BARS_DIR / f"bars_receipt_{date.today()}.json")


def cmd_history() -> None:
    u = latest_universe()
    targets = pull_targets(u)
    syms = [s for m, ss in targets.items() if m != "US" for s in ss]
    rec = pull_earnings_history(syms)
    write_json({"written_utc": utc_stamp(), **rec}, CONTEST / f"earnings_history_receipt_{date.today()}.json")
    print(json.dumps({k: v for k, v in rec.items() if k != "failed"}, default=str))


def cmd_calendar(asof: Optional[date] = None) -> None:
    asof = asof or date.today()
    cal, rec = build_calendar(asof)
    p = CAL_DIR / f"calendar_{asof}.parquet"
    prev = sorted(x for x in CAL_DIR.glob("calendar_*.parquet") if x.name < p.name)
    changes = diff_calendars(pd.read_parquet(prev[-1]), cal) if prev else ["(first calendar)"]
    safe_write_parquet(cal, p, allow_shrink=True)
    rec["changes_vs_previous"] = changes[:500]
    rec["n_changes"] = len(changes)
    write_json({"written_utc": utc_stamp(), **rec}, CAL_DIR / f"calendar_{asof}_receipt.json")
    print(json.dumps({k: v for k, v in rec.items() if k != "changes_vs_previous"}, indent=1, default=str))
    print(f"{len(changes)} change(s) vs previous calendar; first 40:")
    for ln in changes[:40]:
        print("  " + ln)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["universe", "bars", "history", "calendar", "all"])
    ap.add_argument("--asof", default=None)
    a = ap.parse_args(argv)
    asof = date.fromisoformat(a.asof) if a.asof else None
    if a.cmd in ("universe", "all"):
        cmd_universe()
    if a.cmd in ("bars", "all"):
        cmd_bars()
    if a.cmd in ("history", "all"):
        cmd_history()
    if a.cmd in ("calendar", "all"):
        cmd_calendar(asof)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
