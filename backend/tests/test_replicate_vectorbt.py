"""The second engine agrees with a hand-computed two-name case, and names a disagreement.

Offline: synthetic bars only. The expected series is written out by hand from
the file's declared fill convention, not by calling the code under test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import replicate_vectorbt as RV

COST_MODEL = {
    "bands_bps_round_trip": {"mega": 6.0, "large": 10.0, "mid": 18.0, "small": 35.0},
    "band_boundaries_median_dollar_vol": {"mega": ">= 1e9", "large": ">= 1e8",
                                         "mid": ">= 2e7", "small": "< 2e7"},
}
FILL = ("decide at the month-end close; enter at the NEXT session's open; exit at the open of "
        "the session after the next decision date; a name whose bars stop inside the period is "
        "filled at its last close x (1 + -0.3); cash (regime gate off) earns 0")


def _bars() -> pd.DataFrame:
    """SPY + AAA (mega) + BBB (small, dies mid-June 2020), business days 2020."""
    cal = pd.bdate_range("2020-01-01", "2020-08-31")
    rows = []
    for k, d in enumerate(cal):
        rows.append(("SPY", d, 300 + k * 0.1, 300 + k * 0.1 + 0.05, 1e7))
        a = 100 * (1.004 ** k)
        rows.append(("AAA", d, a * 0.998, a, 2e7))            # dollar vol ~2e9: mega
        if d <= pd.Timestamp("2020-06-15"):
            b = 50 * (1 + 0.05 * np.sin(k / 7.0))
            rows.append(("BBB", d, b * 1.003, b, 1e5))         # dollar vol ~5e6: small
    return pd.DataFrame(rows, columns=["symbol", "date", "open", "close", "volume"])


def _by_hand(bars: pd.DataFrame) -> tuple[list, dict]:
    px = {s: g.set_index("date") for s, g in bars.groupby("symbol")}
    cal = pd.DatetimeIndex(sorted(px["SPY"].index))
    me = pd.Series(cal, index=cal).groupby(cal.to_period("M")).max()
    dec = [me.iloc[i] for i in range(2, 6)]          # 03-31, 04-30, 05-29, 06-30
    hold = {dec[0]: (["AAA", "BBB"], [0.5, 0.5]), dec[1]: (["AAA", "BBB"], [0.7, 0.3]),
            dec[2]: (["AAA", "BBB"], [0.4, 0.6]), dec[3]: (["AAA"], [1.0])}
    rt = {"AAA": 6.0, "BBB": 35.0}
    series, prev = [], {}
    for n, d in enumerate(dec):
        nxt = me[me > d].iloc[0]
        e0 = cal[cal.get_loc(d) + 1]
        e1 = cal[cal.get_loc(nxt) + 1]
        names, ws = hold[d]
        gross = 0.0
        dead = 0
        for s, w in zip(names, ws):
            g = px[s]
            entry = g.loc[e0, "open"]
            if g.index.max() < e1:                               # stopped inside the period
                ex = g["close"].iloc[-1] * 0.7
                dead += 1
            else:
                ex = g.loc[e1, "open"]
            gross += w * (ex / entry - 1.0)
        new = dict(zip(names, ws))
        cost = sum(max(w - prev.get(s, 0.0), 0.0) * rt[s] / 2 for s, w in new.items())
        cost += sum(max(w - new.get(s, 0.0), 0.0) * rt[s] / 2 for s, w in prev.items())
        prev = new
        series.append({"date": str(d.date()), "gross": gross, "cost": cost / 1e4,
                       "net": gross - cost / 1e4, "n_delisted": dead, "rebalanced": True})
    row = {"id": "two_name", "held_symbols_by_date": {str(d.date()): hold[d][0] for d in dec},
           "weights_by_date": {str(d.date()): hold[d][1] for d in dec},
           "monthly_return_series": series}
    return series, row


def test_two_name_case_agrees_within_tolerance():
    bars = _bars()
    series, row = _by_hand(bars)
    W = RV.wide(bars)
    out = RV.replicate_row(row, W, COST_MODEL, delist_return=RV._delist_return({"fill_convention": FILL}))
    assert out["verdict"] == "AGREE"
    assert out["corr_net_monthly"] >= RV.AGREE_CORR
    assert out["mean_abs_diff_net_monthly"] <= RV.AGREE_MAD
    assert out["mean_abs_diff_net_monthly"] < 1e-9           # the same convention, exactly
    assert out["n_delisting_fills_ours"] == 1                 # BBB, June
    if not out["engine_gross"].startswith("vectorbt"):
        # CI (2026-09-26): plotly 6 removed `scattermapbox`, so `import vectorbt`
        # raises inside its plotly template and the script falls back to the
        # pandas path BY DESIGN (the fallback is named on the receipt, never
        # silent). The agreement assertions above already ran on that path; the
        # vectorbt-vs-pandas cross-check below needs the engine, so it is a
        # visible SKIP here, not a pass.
        pytest.skip(f"vectorbt unavailable on this interpreter: {out['engine_gross'][:120]}")
    assert out["vectorbt_vs_pandas_gross_max_abs_diff"] < 1e-9


def test_pandas_path_matches_the_vectorbt_path():
    bars = _bars()
    _series, row = _by_hand(bars)
    W = RV.wide(bars)
    a = RV.replicate_row(row, W, COST_MODEL, delist_return=-0.3, use_vectorbt=True)
    b = RV.replicate_row(row, W, COST_MODEL, delist_return=-0.3, use_vectorbt=False)
    na = [x["net"] for x in a["monthly_return_series"]]
    nb = [x["net"] for x in b["monthly_return_series"]]
    assert np.allclose(na, nb, atol=1e-9)


def test_a_cost_error_is_a_named_disagreement():
    bars = _bars()
    series, row = _by_hand(bars)
    for x in series:                                          # the "file" charges 10x the toll
        x["cost"] *= 10
        x["net"] = x["gross"] - x["cost"]
    out = RV.replicate_row(row, RV.wide(bars), COST_MODEL, delist_return=-0.3)
    assert out["verdict"] == "DISAGREEMENT"
    assert out["disagreement"]["bucket"] == "COST_MODEL_MISMATCH"


def test_a_delisting_fill_error_is_data_misalignment():
    bars = _bars()
    _series, row = _by_hand(bars)
    out = RV.replicate_row(row, RV.wide(bars), COST_MODEL, delist_return=0.0)   # wrong fill
    assert out["verdict"] == "DISAGREEMENT"
    assert out["disagreement"]["bucket"] == "DATA_MISALIGNMENT"


def test_the_delist_return_is_read_from_the_file_or_refused():
    assert RV._delist_return({"fill_convention": FILL}) == pytest.approx(-0.3)
    with pytest.raises(ValueError):
        RV._delist_return({"fill_convention": "no number here"})
