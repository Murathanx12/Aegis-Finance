"""Regression: the shared price-panel cache must be keyed by ticker set.

2026-08-01 prod failure: `_get_price_panel`'s cache key was
`pi:price-panel:{lookback}:{date}` — no ticker set — so whichever lane family
fetched first that day poisoned the panel for the rest (the TSMOM check
received the reference lanes' equity panel and HELD on
"panel missing assets: ['GLD','TLT','USO']").

Lives OUTSIDE backend/tests/portfolio_intelligence/ on purpose: that
directory's autouse fixture stubs `_get_price_panel` to None, which is
exactly the function under test here.
"""

from unittest.mock import patch

import pandas as pd

from backend.services.portfolio_intelligence import reference_engine as re_


def _fake_fetch(calls):
    def fetch(tickers, start, end):
        calls.append(list(tickers))
        return {t: pd.Series([1.0, 2.0]) for t in tickers}
    return fetch


def test_distinct_ticker_sets_get_distinct_panels():
    calls: list = []
    with patch("backend.services.data_fetcher._fetch_batch_yahoo",
               side_effect=_fake_fetch(calls)):
        equity = re_._get_price_panel(["AAPL", "MSFT", "SPY"])
        etf = re_._get_price_panel(["SPY", "TLT", "GLD", "USO"])

    assert set(equity.columns) == {"AAPL", "MSFT", "SPY"}
    # the poisoning failure: second call served the first call's panel
    assert set(etf.columns) == {"SPY", "TLT", "GLD", "USO"}
    assert len(calls) == 2, "second ticker set must MISS the cache"


def test_same_ticker_set_hits_cache_order_insensitively():
    calls: list = []
    with patch("backend.services.data_fetcher._fetch_batch_yahoo",
               side_effect=_fake_fetch(calls)):
        a = re_._get_price_panel(["QQQ", "IWM"])
        b = re_._get_price_panel(["IWM", "QQQ"])

    assert set(a.columns) == set(b.columns) == {"QQQ", "IWM"}
    assert len(calls) == 1, "identical set (any order) must HIT the cache"
