"""THE STITCHED-TICKER FIX REACHES EVERY READER (2026-09-29).

`xs_ranker.load_bars` cuts reused tickers; eight other readers of the same bar
files concatenated them raw. Each now calls `stitched_tickers.cut_reader_bars`.
One parametrised test over all of them, synthetic bars, dates from today,
offline: the living symbol starts at the new company's first bar, the old
company is `SYM#1`, no row is dropped, a clean name is untouched, and no bar
file is rewritten. (`scripts/contest_calendar` carries its own `cut_stitched`
and is owned by the contest desk.)
"""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.services import stitched_tickers as ST
from backend.services import xs_ranker as XR

N_SESS, OLD_N, NEW_FROM = 600, 250, 450


def _cal() -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=N_SESS)


def _series(sym, dates, px, seed):
    c = px * np.exp(np.cumsum(np.random.default_rng(seed).normal(0.0005, 0.02, len(dates))))
    return pd.DataFrame({"symbol": sym, "date": dates, "open": c, "high": c * 1.01,
                         "low": c * 0.99, "close": c, "volume": 5e5})


@pytest.fixture
def bars(tmp_path, monkeypatch):
    monkeypatch.setattr(ST, "SEC_FACTS_PATH", tmp_path / "none.parquet")
    monkeypatch.setattr(ST, "COMPANY_TICKERS_PATH", tmp_path / "none.json")
    ST._registrants_cached.cache_clear()
    cal = _cal()
    live = tmp_path / "prices_deep" / "bars.parquet"
    dead = tmp_path / "bars_delisted.parquet"
    live.parent.mkdir()
    pd.concat([_series("SPY", cal, 400.0, 3), _series("CLEAN", cal, 50.0, 4),
               _series("JAN", cal[NEW_FROM:], 23.0, 2)], ignore_index=True).to_parquet(live)
    _series("JAN", cal[:OLD_N], 2.0, 1).to_parquet(dead)      # the old company, 10x lower
    paths = [live, dead]
    monkeypatch.setattr(XR, "survivorship_free_paths", lambda: list(paths))
    monkeypatch.setattr(XR, "BARS_PATH", tmp_path / "absent" / "bars.parquet")
    digest = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    yield {"cal": cal, "paths": paths}
    ST._registrants_cached.cache_clear()
    for p in paths:
        assert hashlib.sha256(p.read_bytes()).hexdigest() == digest[p], f"{p} was rewritten"


def _r_backtest_factory(b):
    from scripts import night_backtest_factory as F
    w = F.load_wide(b["paths"], start=str(b["cal"][0].date()), market="SPY")
    rows = []
    for j, s in enumerate(w["symbols"]):
        ok = np.isfinite(w["close"][:, j])
        rows.append(pd.DataFrame({"symbol": s, "date": w["dates"][ok]}))
    return pd.concat(rows, ignore_index=True)


def _r_source_registry(b):
    from backend.services import source_registry as M
    return M.load_close_panel(b["paths"])


def _r_fast_mover(b):
    from backend.services import fast_mover_forensics as M
    return M._load_bars_since(b["cal"][0])


def _r_bridge_report(b):
    from scripts import bridge_report as M
    return M.load_bars()


def _r_decision_autopsy(b):
    from scripts import decision_autopsy as M
    out, _src = M.load_bars(["JAN", "CLEAN"], fetch=False, start=str(b["cal"][0].date()))
    return out


def _r_source_scorecard(b):
    from backend.services import source_scorecard as M
    return M.load_bars(b["paths"])


def _r_pit_features(b):
    from backend.services import pit_features as M
    return M.load_close_bars(b["paths"])


READERS = {
    "night_backtest_factory.load_wide": _r_backtest_factory,
    "source_registry.load_close_panel": _r_source_registry,
    "fast_mover_forensics._load_bars_since": _r_fast_mover,
    "bridge_report.load_bars": _r_bridge_report,
    "decision_autopsy.load_bars": _r_decision_autopsy,
    "source_scorecard.load_bars": _r_source_scorecard,
    "pit_features.load_close_bars": _r_pit_features,
}


@pytest.mark.parametrize("name", sorted(READERS))
def test_every_reader_starts_a_reused_ticker_at_the_new_company(name, bars):
    out = READERS[name](bars)
    cal = bars["cal"]
    d = pd.to_datetime(out["date"])
    jan = d[out["symbol"] == "JAN"]
    assert len(jan) and jan.min() == cal[NEW_FROM], f"{name}: JAN starts {jan.min()}"
    assert (out["symbol"] == "JAN#1").sum() == OLD_N, f"{name}: the old company was dropped"
    assert (out["symbol"] == "JAN").sum() == N_SESS - NEW_FROM
    assert (out["symbol"] == "CLEAN").sum() == N_SESS            # untouched
    assert "_src" not in out.columns


def test_the_helper_detects_a_hole_without_the_market_in_the_frame(bars):
    """A reader that loads one symbol: the fallback calendar must still see the
    hole (the frame's own dates would call every pair of bars one session apart)."""
    cal = _cal()
    one = pd.concat([_series("JAN", cal[:OLD_N], 2.0, 1),
                     _series("JAN", cal[NEW_FROM:], 23.0, 2)], ignore_index=True)
    out = ST.cut_reader_bars(one)
    assert (out["symbol"] == "JAN#1").sum() == OLD_N and len(out) == len(one)
