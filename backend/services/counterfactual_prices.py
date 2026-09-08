"""Closes for the four-counterfactual grader, and the NAME of whatever answered.

    from backend.services import counterfactual_prices as cp

    cp.close_on("SPY", "2026-08-03")     -> PriceAnswer(price=..., source="conviction_prices_csv")
    cp.window_return("SPY", "2026-07-01", "2026-08-03")
    cp.sessions_after("2026-09-08", 21)  -> (date, "XNYS")

THE FAILURE THIS MODULE EXISTS TO PREVENT
=========================================
The `market` benchmark account (**PA3I7VTCC0BM**, contract `PASSIVE_BETA_v1`)
holds SPY, and **its keys are not in this environment**. So the SPY leg of the
fourth counterfactual cannot be read off a broker; it has to be computed from
price data. The tempting shape is a helper that returns 0.0 when it cannot find
a price, and 0.0 is indistinguishable from "SPY was flat" -- which would make the
benchmark leg quietly free every time the data was missing, in the direction that
flatters the human. Every function here therefore returns a NAMED SOURCE beside
the number, or raises `PriceUnavailable`. There is no zero branch.

THE SOURCE CHAIN (`config.COUNTERFACTUAL_PRICE_SOURCES`, tried in order)
=======================================================================
`terminal_state_mirror`  CSV closes under `data/terminal_mirror/prices/`. The H5
                         sync does NOT populate this today (its whitelist covers
                         seals, fills, refusals, autopsies and learning reports,
                         not marks), so this source refuses with that reason. It
                         is in the chain because a source that is *planned* and a
                         source that is *absent* are different facts, and a chain
                         that quietly has two links reads as a chain of two.
`conviction_prices_csv`  `backend/data/conviction_prices.csv` -- 197 sessions,
                         2025-10-27..2026-08-10, 66 tickers INCLUDING SPY, QQQ,
                         IWM, XBI and SMH. Offline, so the fast suite can grade.
                         Split/dividend adjusted yfinance; descriptive only.
`yfinance_live`          the network. **Refused inside the fast suite** by
                         `backend/tests/conftest.py`'s offline guard, which is
                         the correct behaviour: a unit test that reaches a vendor
                         is a bug, and the refusal is reported as a source that
                         could not answer rather than as a zero.

SESSIONS, NOT DAYS
==================
A row resolves at ITS OWN horizon in SESSIONS. `sessions_after` walks the real
XNYS calendar and stamps `"XNYS"`; if `exchange_calendars` is missing it falls
back to weekday arithmetic and stamps `"WEEKDAY_APPROX"`. The stamp travels onto
the graded row, because a horizon counted over a fortnight containing
Thanksgiving is a different horizon depending on which calendar answered.
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from pathlib import Path

from backend.config import (COUNTERFACTUAL_PRICE_SOURCES, TERMINAL_MIRROR_DIR)

logger = logging.getLogger(__name__)

#: The offline panel. Same file `backend/services/conviction_prices.py` reads.
_CONVICTION_CSV = Path(__file__).resolve().parents[1] / "data" / "conviction_prices.csv"

#: Where a mirrored price artefact WOULD live. See the module docstring.
_MIRROR_PRICES = TERMINAL_MIRROR_DIR / "prices"

XNYS = "XNYS"
WEEKDAY_APPROX = "WEEKDAY_APPROX"


class PriceUnavailable(LookupError):
    """No declared source could supply the price, and none of them guessed.

    Carries `attempts`: one line per source saying what it tried and why it
    could not answer. A caller that catches this has the receipt for the gap.
    """

    def __init__(self, message: str, attempts: list[dict] | None = None):
        super().__init__(message)
        self.attempts = attempts or []


@dataclass(frozen=True)
class PriceAnswer:
    symbol: str
    day: str
    price: float
    source: str
    note: str = ""
    attempts: tuple = ()

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "day": self.day, "price": self.price,
                "source": self.source, "note": self.note,
                "attempts": list(self.attempts)}


# ── sessions ────────────────────────────────────────────────────────────────
def _as_date(day) -> _dt.date:
    if isinstance(day, _dt.datetime):
        return day.date()
    if isinstance(day, _dt.date):
        return day
    return _dt.date.fromisoformat(str(day)[:10])


def sessions_after(day, n_sessions: int) -> tuple[_dt.date, str]:
    """The date `n_sessions` trading sessions after `day`, and the calendar used.

    `n_sessions == 0` returns `day` itself, so a caller does not have to special
    case a zero-hold event row.
    """
    d0 = _as_date(day)
    if int(n_sessions) <= 0:
        return d0, XNYS if _calendar_available() else WEEKDAY_APPROX
    try:
        import exchange_calendars as xc                            # noqa: PLC0415

        cal = xc.get_calendar("XNYS", start="1990-01-01", end="2035-12-31")
        idx = cal.sessions_in_range(d0.isoformat(),
                                    (d0 + _dt.timedelta(days=int(n_sessions) * 3 + 30)).isoformat())
        days = [s.date() for s in idx]
        # `sessions_in_range` includes d0 when d0 is itself a session.
        after = [s for s in days if s > d0]
        if len(after) >= int(n_sessions):
            return after[int(n_sessions) - 1], XNYS
        logger.warning("XNYS range too short for %s + %s sessions; widening",
                       d0, n_sessions)
        idx = cal.sessions_in_range(d0.isoformat(),
                                    (d0 + _dt.timedelta(days=int(n_sessions) * 4 + 120)).isoformat())
        after = [s.date() for s in idx if s.date() > d0]
        if len(after) >= int(n_sessions):
            return after[int(n_sessions) - 1], XNYS
    except Exception as exc:                                       # noqa: BLE001
        logger.info("XNYS calendar unavailable (%s); weekday arithmetic",
                    type(exc).__name__)
    d, left = d0, int(n_sessions)
    while left > 0:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d, WEEKDAY_APPROX


def _calendar_available() -> bool:
    try:
        import exchange_calendars                                   # noqa: F401,PLC0415
        return True
    except Exception:                                               # noqa: BLE001
        return False


def sessions_between(start, end) -> tuple[int, str]:
    """How many sessions separate two dates, and which calendar counted them."""
    a, b = _as_date(start), _as_date(end)
    if b < a:
        return -sessions_between(b, a)[0], _calendar_name()
    try:
        import exchange_calendars as xc                             # noqa: PLC0415

        cal = xc.get_calendar("XNYS", start="1990-01-01", end="2035-12-31")
        idx = cal.sessions_in_range(a.isoformat(), b.isoformat())
        return max(0, len(idx) - 1), XNYS
    except Exception:                                               # noqa: BLE001
        n, d = 0, a
        while d < b:
            d += _dt.timedelta(days=1)
            if d.weekday() < 5:
                n += 1
        return n, WEEKDAY_APPROX


def _calendar_name() -> str:
    return XNYS if _calendar_available() else WEEKDAY_APPROX


# ── the sources ─────────────────────────────────────────────────────────────
_CSV_CACHE: dict[str, tuple] = {}


def _load_conviction_csv(path: Path | None = None):
    p = Path(path or _CONVICTION_CSV)
    if not p.exists():
        return None, f"{p} is absent"
    key = f"{p}:{p.stat().st_mtime_ns}:{p.stat().st_size}"
    if key in _CSV_CACHE:
        return _CSV_CACHE[key][0], _CSV_CACHE[key][1]
    try:
        import pandas as pd                                          # noqa: PLC0415

        df = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
        df.columns = [str(c).upper() for c in df.columns]
    except Exception as exc:                                         # noqa: BLE001
        return None, f"{p.name} did not parse: {type(exc).__name__}: {exc}"
    _CSV_CACHE.clear()
    _CSV_CACHE[key] = (df, "")
    return df, ""


def _from_csv(symbol: str, day: _dt.date, path: Path | None = None):
    df, why = _load_conviction_csv(path)
    if df is None:
        return None, why
    sym = symbol.upper()
    if sym not in df.columns:
        return None, (f"{sym} is not one of the {len(df.columns)} tickers in "
                      "conviction_prices.csv")
    col = df[sym].dropna()
    if col.empty:
        return None, f"{sym} has no non-null close in conviction_prices.csv"
    import pandas as pd                                              # noqa: PLC0415

    ts = pd.Timestamp(day)
    upto = col[col.index <= ts]
    if upto.empty:
        return None, (f"{sym} has no close on or before {day} "
                      f"(panel starts {col.index[0].date()})")
    if col.index[-1] < ts:
        return None, (f"{sym} panel ends {col.index[-1].date()}, before {day}; "
                      "refusing to carry the last price forward")
    return (float(upto.iloc[-1]), str(upto.index[-1].date())), ""


def _from_mirror(symbol: str, day: _dt.date):
    if not _MIRROR_PRICES.exists():
        return None, (f"{_MIRROR_PRICES} does not exist -- the H5 mirror's "
                      "artefact whitelist covers seals, fills, refusals, "
                      "autopsies and learning reports, not marks")
    f = _MIRROR_PRICES / "closes.csv"
    if not f.exists():
        return None, f"{f} is absent"
    return _from_csv(symbol, day, path=f)


def _from_yfinance(symbol: str, day: _dt.date):
    try:
        from backend.services.data_fetcher import fetch_ticker_history   # noqa: PLC0415

        hist = fetch_ticker_history(symbol.upper(), period="2y")
    except Exception as exc:                                         # noqa: BLE001
        return None, f"yfinance refused: {type(exc).__name__}: {str(exc)[:120]}"
    if hist is None or len(hist) == 0:
        return None, "yfinance returned no rows"
    try:
        import pandas as pd                                          # noqa: PLC0415

        s = hist["Close"].dropna()
        s.index = pd.to_datetime(s.index).tz_localize(None)
        upto = s[s.index <= pd.Timestamp(day)]
        if upto.empty:
            return None, f"yfinance has no close on or before {day}"
        return (float(upto.iloc[-1]), str(upto.index[-1].date())), ""
    except Exception as exc:                                         # noqa: BLE001
        return None, f"yfinance frame unusable: {type(exc).__name__}"


_SOURCE_FNS = {
    "terminal_state_mirror": _from_mirror,
    "conviction_prices_csv": _from_csv,
    "yfinance_live": _from_yfinance,
}


def close_on(symbol: str, day, *, sources: tuple[str, ...] | None = None) -> PriceAnswer:
    """The close for `symbol` on or before `day`, from the first source that has it.

    Raises `PriceUnavailable` -- never returns 0.0, never carries a stale price
    silently across the end of a panel.
    """
    d = _as_date(day)
    chain = tuple(sources or COUNTERFACTUAL_PRICE_SOURCES)
    attempts: list[dict] = []
    for name in chain:
        fn = _SOURCE_FNS.get(name)
        if fn is None:
            attempts.append({"source": name, "answered": False,
                             "reason": "undeclared source name"})
            continue
        got, why = fn(symbol, d)
        if got is None:
            attempts.append({"source": name, "answered": False, "reason": why})
            continue
        price, on_day = got
        return PriceAnswer(symbol=symbol.upper(), day=on_day, price=float(price),
                           source=name,
                           note=("" if on_day == d.isoformat()
                                 else f"asked for {d}, answered with the close on {on_day}"),
                           attempts=tuple(attempts))
    raise PriceUnavailable(
        f"no declared source could price {symbol.upper()} on {d}. "
        f"Tried {list(chain)}. This is a REFUSAL: a zero here would read as "
        "'the benchmark was flat' and make the counterfactual free.",
        attempts=attempts)


def window_return(symbol: str, start, end, *,
                  sources: tuple[str, ...] | None = None) -> dict:
    """Simple return between two closes, with both sources named.

    Returns a dict rather than a float so a caller cannot use the number without
    also holding the provenance. `ok=False` carries the reason; there is no
    numeric answer in that case, not even zero.
    """
    try:
        a = close_on(symbol, start, sources=sources)
        b = close_on(symbol, end, sources=sources)
    except PriceUnavailable as exc:
        return {"ok": False, "symbol": symbol.upper(), "ret": None,
                "reason": str(exc), "attempts": exc.attempts,
                "source": "NOT_AVAILABLE"}
    if a.price <= 0:
        return {"ok": False, "symbol": symbol.upper(), "ret": None,
                "reason": f"start close {a.price} is not positive",
                "source": a.source}
    return {"ok": True, "symbol": symbol.upper(), "ret": (b.price / a.price) - 1.0,
            "start_day": a.day, "end_day": b.day,
            "start_price": a.price, "end_price": b.price,
            "source": a.source if a.source == b.source else f"{a.source}+{b.source}",
            "reason": None,
            "note": "; ".join(x for x in (a.note, b.note) if x)}


def source_report() -> dict:
    """What each declared source could do RIGHT NOW. A probe, not a promise."""
    out = {}
    for name in COUNTERFACTUAL_PRICE_SOURCES:
        if name == "conviction_prices_csv":
            df, why = _load_conviction_csv()
            out[name] = {"available": df is not None,
                         "reason": why or None,
                         "n_sessions": (0 if df is None else int(len(df))),
                         "n_symbols": (0 if df is None else int(df.shape[1])),
                         "covers": (None if df is None else
                                    [str(df.index[0].date()), str(df.index[-1].date())]),
                         "network": False}
        elif name == "terminal_state_mirror":
            out[name] = {"available": (_MIRROR_PRICES / "closes.csv").exists(),
                         "reason": (None if (_MIRROR_PRICES / "closes.csv").exists()
                                    else "the H5 mirror does not sync marks"),
                         "network": False}
        else:
            out[name] = {"available": None,
                         "reason": ("network source; blocked inside the fast test "
                                    "suite by conftest, which is correct"),
                         "network": True}
    return {"order": list(COUNTERFACTUAL_PRICE_SOURCES), "sources": out,
            "benchmark_note": (
                "the `market` paper account PA3I7VTCC0BM (PASSIVE_BETA_v1) holds "
                "SPY and its keys are NOT in this environment, so the SPY "
                "counterfactual is computed from PRICE DATA and names the source "
                "that answered."),
            "session_calendar": _calendar_name()}
