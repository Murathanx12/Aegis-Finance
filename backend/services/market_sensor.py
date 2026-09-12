"""X4's market sensor: 21-day SPY trend and the VIX level, and nothing fitted.

`AEGIS_STRATEGIC_INVARIANTS.md` invariant 4 says NVDA/SPY/QQQ *can be* sensors.
Grepped on 2026-09-12: no sensor module existed, so this is the fallback the
roadmap itself names (spec `docs/research_notes/2026-09-12/spec_lane_x.md`
section 5.1) built fresh rather than retrofitted from something that was never
written.

THE THRESHOLDS ARE FROZEN AND PRINTED, AND THAT IS THE POINT
============================================================
VIX 20 is CBOE's and FRED's own conventional regime line, not a number found by
looking at the result. The trend line is the sign of the trailing 21-session
return, not a fitted band. Both live in `THRESHOLDS` and every receipt prints
them, because *a threshold chosen by looking at the result is not a threshold*
(feedback: a min-names filter selects the regime -- a +2.32% cell with t 2.60
became a median of -0.63% at a different filter setting).

Two ties are decided here, in advance, so nobody decides them later on a
borderline number:

* a trailing return of EXACTLY zero is `TREND_DOWN` -- a flat 21-session tape
  is not an uptrend;
* VIX exactly 20.00 is `VIX_HIGH` -- the line is "below 20 is calm", so 20 is
  not below it.

WHAT IT REFUSES
===============
The VIX comes from FRED (`VIXCLS`), which needs a key and a network. Offline,
or with no key, `vix_level()` REFUSES BY NAME and `regime()` returns `unknown`
with the reason attached. It never substitutes a last-known value, and it never
falls back to the trend alone while still calling the answer a regime: a
half-observed sensor that reports a confident label is the shape that put a
permanent red line beside nine real checks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

#: The bars the 2025-26 replay already ingests. SPY is in them (R2's own
#: `MARKET_SYMBOL`), so the trend leg needs no new source.
BARS = REPO / "backend" / "data" / "optimus" / "prices_2025_26" / "bars.parquet"
MARKET_SYMBOL = "SPY"

#: FRED's series id for the VIX. Longer history than the CBOE file and already
#: in `config["data"]["fred_series"]` as `vix_fred`.
VIX_SERIES = "VIXCLS"

THRESHOLDS: dict[str, Any] = {
    "trend_lookback_sessions": 21,
    "trend_up_if": "trailing 21-session total return STRICTLY greater than 0",
    "trend_tie": "a trailing return of exactly 0 is TREND_DOWN",
    "vix_regime_line": 20.0,
    "vix_low_if": "VIX strictly below 20.0",
    "vix_tie": "VIX exactly 20.00 is VIX_HIGH -- the line is 'below 20 is calm'",
    "source_of_the_line": ("CBOE/FRED's own conventional VIX regime level, fixed in "
                           "advance. NOT fitted on any outcome in this repository"),
    "risk_on_cell": "TREND_UP x VIX_LOW",
    "risk_off_cells": "every other observed cell (TREND_DOWN, or VIX_HIGH, or both)",
}

TREND_LOOKBACK = int(THRESHOLDS["trend_lookback_sessions"])
VIX_LINE = float(THRESHOLDS["vix_regime_line"])

RISK_ON, RISK_OFF, UNKNOWN = "risk_on", "risk_off", "unknown"


class SensorRefused(RuntimeError):
    """An input could not be observed. A regime is not guessed from the rest."""


def _load_spy(bars_path: Path | None = None):
    import pandas as pd

    path = Path(bars_path or BARS)
    if not path.is_file():
        raise SensorRefused(f"no bars at {path}: the 21-session SPY trend cannot be "
                            "computed and this sensor does not substitute one")
    bars = pd.read_parquet(path, columns=["symbol", "date", "close"])
    spy = bars[bars["symbol"] == MARKET_SYMBOL].copy()
    if spy.empty:
        raise SensorRefused(f"{MARKET_SYMBOL} is not in {path}; there is no market proxy")
    spy["date"] = pd.to_datetime(spy["date"])
    return spy.sort_values("date").reset_index(drop=True)


def spy_trend(bars=None, *, bars_path: Path | None = None, lookback: int = TREND_LOOKBACK):
    """Trailing `lookback`-session total return per session, as a DataFrame.

    Columns: `date`, `close`, `trend_return`, `trend`. The first `lookback`
    sessions carry a null return and a null trend -- a lookback that is not
    available is not zero.
    """
    import numpy as np

    spy = bars if bars is not None else _load_spy(bars_path)
    spy = spy.copy()
    spy["trend_return"] = spy["close"] / spy["close"].shift(lookback) - 1.0
    spy["trend"] = np.where(
        spy["trend_return"].isna(), None,
        np.where(spy["trend_return"] > 0, "TREND_UP", "TREND_DOWN"))
    return spy[["date", "close", "trend_return", "trend"]]


def vix_history(series=None):
    """The whole VIX series, sorted and date-indexed -- or a NAMED refusal.

    Separate from `vix_level` because a SERIES is what a per-date router needs.
    Measured on 2026-09-12: `regime_series` had fetched one scalar VIX (the
    latest, 17.84) and applied it to all 18 month blocks, so a 2025-01 routing
    decision was being made with a 2026-09 observation -- a look-ahead of
    twenty months inside a module whose whole purpose is a point-in-time
    regime. The rule that caught it is the repo's own: no information acted on
    before it was public.
    """
    import pandas as pd

    if series is None:
        try:
            from backend.services.data_fetcher import DataFetcher
        except Exception as exc:                                   # noqa: BLE001
            raise SensorRefused(f"the FRED fetcher is not importable: {exc}") from exc
        try:
            data = DataFetcher().fetch_fred_data()
        except Exception as exc:                                   # noqa: BLE001
            raise SensorRefused(
                f"FRED fetch failed ({type(exc).__name__}: {exc}); the VIX leg of the "
                "sensor is unobserved and no last-known value is substituted") from exc
        series = (data or {}).get("vix_fred")
        if series is None or len(series) == 0:
            raise SensorRefused(
                f"FRED returned no {VIX_SERIES} series (no key, or the fetch was "
                "skipped). The VIX leg is unobserved")
    s = pd.Series(series).dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def vix_level(as_of=None, *, series=None) -> dict:
    """The VIX close on or before `as_of`, from FRED -- or a NAMED refusal.

    `series` lets a caller (or a test) pass an already-fetched pandas Series
    keyed by date; without it this goes to FRED through the fetcher the rest of
    the repository already uses, and any failure comes back as `SensorRefused`
    naming what was missing rather than as a silent None.
    """
    import pandas as pd

    s = vix_history(series)
    if as_of is not None:
        s = s[s.index <= pd.Timestamp(as_of)]
    if s.empty:
        raise SensorRefused(f"no {VIX_SERIES} observation on or before {as_of}")
    return {"value": float(s.iloc[-1]), "observed_at": str(s.index[-1].date()),
            "series": VIX_SERIES}


def label(trend: str | None, vix: float | None) -> dict:
    """The 2x2 cell and the tri-state regime, from two observations.

    Either input missing gives `unknown` WITH the reason. The tri-state is a
    projection of the 2x2 and both travel, so a consumer that wants the finer
    cell has it and one that wants the coarse call does not have to derive it.
    """
    if trend not in ("TREND_UP", "TREND_DOWN"):
        return {"regime": UNKNOWN, "cell": None, "trend": trend, "vix": vix,
                "reason": "the 21-session SPY trend is unobserved"}
    if vix is None:
        return {"regime": UNKNOWN, "cell": None, "trend": trend, "vix": None,
                "reason": ("the VIX level is unobserved; a trend-only answer is not a "
                           "regime and is not reported as one")}
    vix_cell = "VIX_LOW" if float(vix) < VIX_LINE else "VIX_HIGH"
    cell = f"{trend} x {vix_cell}"
    return {"regime": RISK_ON if (trend == "TREND_UP" and vix_cell == "VIX_LOW") else RISK_OFF,
            "cell": cell, "trend": trend, "vix_cell": vix_cell, "vix": float(vix),
            "reason": None}


def regime(as_of=None, *, bars=None, bars_path: Path | None = None,
           vix_series=None) -> dict:
    """The sensor's answer for one date, with everything it used."""
    out: dict[str, Any] = {"as_of": str(as_of) if as_of is not None else None,
                           "thresholds": dict(THRESHOLDS)}
    try:
        tr = spy_trend(bars, bars_path=bars_path)
    except SensorRefused as exc:
        return {**out, **label(None, None), "reason": str(exc)}
    import pandas as pd

    if as_of is not None:
        tr = tr[tr["date"] <= pd.Timestamp(as_of)]
    if tr.empty:
        return {**out, **label(None, None),
                "reason": f"no SPY session on or before {as_of}"}
    row = tr.iloc[-1]
    out["trend_return"] = (None if pd.isna(row["trend_return"])
                           else round(float(row["trend_return"]), 6))
    out["trend_observed_at"] = str(pd.Timestamp(row["date"]).date())
    try:
        v = vix_level(as_of, series=vix_series)
        out["vix_observation"] = v
        vix_value = v["value"]
    except SensorRefused as exc:
        out["vix_refusal"] = str(exc)
        vix_value = None
    return {**out, **label(row["trend"], vix_value)}


def regime_series(dates, *, bars=None, bars_path: Path | None = None,
                  vix_series=None) -> list[dict]:
    """One regime row per date in `dates`, cheaply (the bars are read once)."""
    import pandas as pd

    try:
        tr = spy_trend(bars, bars_path=bars_path)
    except SensorRefused as exc:
        return [{"as_of": str(d), "regime": UNKNOWN, "cell": None, "reason": str(exc)}
                for d in dates]
    tr = tr.set_index("date")
    vix_refusal = None
    vs = None
    try:
        # THE WHOLE SERIES, indexed per date. One scalar applied to every date
        # is a look-ahead, and it was one here until 2026-09-12.
        vs = vix_history(vix_series)
    except SensorRefused as exc:
        vix_refusal = str(exc)
    out = []
    for d in dates:
        ts = pd.Timestamp(d)
        sub = tr[tr.index <= ts]
        if sub.empty:
            out.append({"as_of": str(d), "regime": UNKNOWN, "cell": None,
                        "reason": f"no SPY session on or before {d}"})
            continue
        row = sub.iloc[-1]
        v = None
        if vs is not None:
            past = vs[vs.index <= ts]
            v = float(past.iloc[-1]) if not past.empty else None
        lab = label(row["trend"], v)
        out.append({"as_of": str(pd.Timestamp(d).date()),
                    "trend_return": (None if pd.isna(row["trend_return"])
                                     else round(float(row["trend_return"]), 6)),
                    "vix_observed_at": (None if v is None
                                        else str(vs[vs.index <= ts].index[-1].date())),
                    **lab,
                    **({"vix_refusal": vix_refusal} if vix_refusal else {})})
    return out


def declaration() -> dict:
    """What this sensor IS, for a receipt. Printed, never paraphrased."""
    return {"module": "backend.services.market_sensor",
            "inputs": {"trend": f"{MARKET_SYMBOL} close from {BARS.name}, "
                                f"{TREND_LOOKBACK}-session total return",
                       "vix": f"FRED {VIX_SERIES} via DataFetcher.fetch_fred_data"},
            "thresholds": dict(THRESHOLDS),
            "states": [RISK_ON, RISK_OFF, UNKNOWN],
            "refuses": ("by name, when either leg is unobserved. A trend-only answer "
                        "is never reported as a regime")}
