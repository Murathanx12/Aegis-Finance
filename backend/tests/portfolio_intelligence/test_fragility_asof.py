"""Composite percentile must be as-of / leak-proof (approved integrity fix).

`compute_fragility_index` percentile-ranks the current value against history. With
no as-of bound it would rank against the FULL series — a silent lookahead the
instant a backtest path touches it. These tests run it through a simulated
backtest with a FUTURE spike and assert no future data is used at the as-of
point. At the live edge (as_of_ts=None) behavior is unchanged."""

import numpy as np
import pandas as pd

from backend.services.portfolio_intelligence.fragility import compute_fragility_index


def _sp500(n=400):
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame({"SP500": np.linspace(3000.0, 4000.0, n)}, index=idx)


def _hy_with_future_spike(n=400, cutoff_i=200):
    """HY-OAS: a varied pre-cutoff window, a mid value at the cutoff, then a big
    spike afterwards (the 'future' that must not leak into the as-of reading)."""
    idx = pd.bdate_range("2020-01-01", periods=n)
    vals = np.empty(n)
    vals[:cutoff_i] = np.tile([2.0, 4.0], cutoff_i // 2)  # alternating 2/4
    vals[cutoff_i] = 3.0                                   # the as-of value
    vals[cutoff_i + 1:] = 10.0                             # future spike
    return {"hy_oas": pd.Series(vals, index=idx)}, str(idx[cutoff_i].date())


class TestFragilityAsOf:
    def test_asof_equals_truncated_no_future_used(self):
        data = _sp500()
        fred, cutoff = _hy_with_future_spike()
        dt = pd.Timestamp(cutoff)

        # Full data + as_of_ts param (the new leak-proof path).
        r_asof = compute_fragility_index(data=data, fred_data=fred, as_of_ts=cutoff)
        # Manually truncated inputs (the only previously-leak-free way).
        r_trunc = compute_fragility_index(
            data=data.loc[data.index <= dt],
            fred_data={"hy_oas": fred["hy_oas"].loc[fred["hy_oas"].index <= dt]},
        )
        assert r_asof["components"]["hy_oas"]["normalized"] == \
            r_trunc["components"]["hy_oas"]["normalized"]

    def test_without_asof_full_series_differs(self):
        # Proves the leak the as_of bound prevents: with the full series the
        # reading uses the future spike and differs from the as-of reading.
        data = _sp500()
        fred, cutoff = _hy_with_future_spike()
        r_asof = compute_fragility_index(data=data, fred_data=fred, as_of_ts=cutoff)
        r_full = compute_fragility_index(data=data, fred_data=fred)  # live: full series
        assert r_asof["components"]["hy_oas"]["normalized"] != \
            r_full["components"]["hy_oas"]["normalized"]

    def test_live_edge_unchanged(self):
        # as_of_ts=None must behave exactly like calling without the param.
        data = _sp500()
        fred, _ = _hy_with_future_spike()
        a = compute_fragility_index(data=data, fred_data=fred)
        b = compute_fragility_index(data=data, fred_data=fred, as_of_ts=None)
        assert a["components"]["hy_oas"]["normalized"] == b["components"]["hy_oas"]["normalized"]
