"""global_prices: the yfinance cache for names the US panel never holds.

Offline: every test injects a downloader (or stubs `yfinance.download`), so no
socket is opened. Dates derive from `today`, never a literal calendar moment.
"""

from __future__ import annotations

import sys
import types
from datetime import date, timedelta

import pandas as pd
import pytest

from backend.services import global_prices as GP


def _today() -> date:
    return date.today()


def _bars(symbol: str, days: list[date], px: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": symbol, "date": pd.to_datetime(days),
        "open": px, "high": px * 1.01, "low": px * 0.99, "close": px,
        "volume": 1_000_000.0})


class _Downloader:
    """Records every call; returns bars for the tickers it knows."""

    def __init__(self, known: dict[str, pd.DataFrame]):
        self.known = known
        self.calls: list[tuple[list[str], str, str]] = []

    def __call__(self, tickers, start, end):
        self.calls.append((list(tickers), str(start), str(end)))
        frames = [self.known[t] for t in tickers if t in self.known]
        if not frames:
            return pd.DataFrame(columns=GP.COLUMNS[:7])
        return pd.concat(frames, ignore_index=True)


def _days(n: int, *, end_offset: int = 1) -> list[date]:
    t = _today()
    return [t - timedelta(days=end_offset + i) for i in range(n)][::-1]


def test_needs_global_by_suffix_or_absence():
    us = {"AAPL", "SPY"}
    assert GP.needs_global("2330.TW", us)
    assert GP.needs_global("URTH", us)          # an ETF the US panel lacks
    assert not GP.needs_global("AAPL", us)
    assert GP.needs_global("AAPL", None) is False


def test_ensure_writes_cache_and_receipt(tmp_path):
    dl = _Downloader({"2330.TW": _bars("2330.TW", _days(5))})
    out = GP.ensure(["2330.TW", "NOPE.KS"], start=_today() - timedelta(days=30),
                    path=tmp_path / "g.parquet", downloader=dl, today=_today())
    rc = out.attrs["receipt"]
    assert rc["n_ok"] == 1 and rc["n_failed"] == 1
    assert rc["failed"] == ["NOPE.KS"]
    assert set(out["symbol"]) == {"2330.TW"}
    assert (tmp_path / "g.parquet").exists()
    assert GP.receipt_path(_today(), base=tmp_path).exists()


def test_one_pull_per_utc_day(tmp_path):
    dl = _Downloader({"2330.TW": _bars("2330.TW", _days(5))})
    p = tmp_path / "g.parquet"
    GP.ensure(["2330.TW"], start=_today() - timedelta(days=30), path=p,
              downloader=dl, today=_today())
    out = GP.ensure(["2330.TW"], start=_today() - timedelta(days=30), path=p,
                    downloader=dl, today=_today())
    assert len(dl.calls) == 1, "second ensure on the same UTC day must not pull"
    assert out.attrs["receipt"]["n_skipped_pulled_today"] == 1
    assert len(out) == 5
    # the next UTC day pulls again
    GP.ensure(["2330.TW"], start=_today() - timedelta(days=30), path=p,
              downloader=dl, today=_today() + timedelta(days=1))
    assert len(dl.calls) == 2


def test_cache_is_append_only(tmp_path):
    p = tmp_path / "g.parquet"
    first = _bars("7203.T", _days(3, end_offset=3), px=10.0)
    GP.ensure(["7203.T"], start=_today() - timedelta(days=30), path=p,
              downloader=_Downloader({"7203.T": first}),
              today=_today() - timedelta(days=1))
    # a re-pull that RESTATES the old rows at a new price and adds a new one
    restated = pd.concat([_bars("7203.T", _days(3, end_offset=3), px=99.0),
                          _bars("7203.T", _days(1, end_offset=1), px=11.0)])
    out = GP.ensure(["7203.T"], start=_today() - timedelta(days=30), path=p,
                    downloader=_Downloader({"7203.T": restated}), today=_today())
    old = out[out["date"] < pd.Timestamp(_today() - timedelta(days=2))]
    assert (old["close"] == 10.0).all(), "cached rows were rewritten"
    assert len(out) == 4


def test_drops_the_incomplete_session(tmp_path):
    """A bar dated today (UTC) may be intraday; it never enters the cache."""
    rows = _bars("0700.HK", [_today() - timedelta(days=1), _today()])
    out = GP.ensure(["0700.HK"], start=_today() - timedelta(days=30),
                    path=tmp_path / "g.parquet",
                    downloader=_Downloader({"0700.HK": rows}), today=_today())
    assert out["date"].max() < pd.Timestamp(_today())


def test_resolve_returns_only_priced(tmp_path):
    dl = _Downloader({"ASML.AS": _bars("ASML.AS", _days(3))})
    got = GP.resolve(["ASML.AS", "ZZZZ.PA"], path=tmp_path / "g.parquet",
                     downloader=dl, today=_today())
    assert got == {"ASML.AS"}


def test_default_downloader_reshapes_yfinance(monkeypatch, tmp_path):
    """The real code path, with yfinance.download stubbed (no socket)."""
    idx = pd.to_datetime(_days(2))
    cols = pd.MultiIndex.from_product(
        [["2330.TW", "URTH"], ["Open", "High", "Low", "Close", "Volume"]])
    wide = pd.DataFrame(1.0, index=idx, columns=cols)
    wide[("URTH", "Close")] = [150.0, 151.0]
    fake = types.SimpleNamespace(download=lambda *a, **k: wide)
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    out = GP.ensure(["2330.TW", "URTH"], start=_today() - timedelta(days=30),
                    path=tmp_path / "g.parquet", today=_today())
    assert set(out["symbol"]) == {"2330.TW", "URTH"}
    assert out[out["symbol"] == "URTH"]["close"].tolist() == [150.0, 151.0]


def test_empty_request_is_an_empty_frame_with_a_receipt(tmp_path):
    out = GP.ensure([], start=_today(), path=tmp_path / "g.parquet",
                    downloader=_Downloader({}), today=_today())
    assert out.empty and out.attrs["receipt"]["n_requested"] == 0


def test_downloader_exception_is_counted_not_raised(tmp_path):
    def boom(*_a, **_k):
        raise RuntimeError("rate limited")
    out = GP.ensure(["2330.TW"], start=_today() - timedelta(days=5),
                    path=tmp_path / "g.parquet", downloader=boom, today=_today())
    rc = out.attrs["receipt"]
    assert rc["n_failed"] == 1 and "rate limited" in rc["errors"][0]


@pytest.mark.parametrize("sym", ["2330.TW", "SAAB-B.ST", "NOVO-B.CO"])
def test_suffixes_are_global(sym):
    assert GP.is_global_suffix(sym)
