"""Tests for estimate_revisions service (analyst upgrade/downgrade trend)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from backend.services import estimate_revisions as er


def test_score_consensus_thresholds():
    assert er._score_consensus(10, 0, 0) == "strongly_bullish"
    assert er._score_consensus(6, 3, 10) == "bullish"
    assert er._score_consensus(5, 5, 20) == "neutral"
    assert er._score_consensus(1, 4, 10) == "bearish"
    assert er._score_consensus(0, 10, 0) == "strongly_bearish"


def test_score_consensus_empty():
    assert er._score_consensus(0, 0, 0) == "neutral"


def test_window_counts_using_grade_schema():
    rows = []
    for days_ago, frm, to in [
        (3, "Hold", "Buy"),
        (5, "Buy", "Buy"),
        (20, "Buy", "Sell"),
        (60, "Buy", "Hold"),
        (100, "Hold", "Buy"),
    ]:
        rows.append({"date": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago),
                     "From Grade": frm, "To Grade": to})
    df = pd.DataFrame(rows).set_index("date")

    w7 = er._window_counts(df, 7)
    assert w7["up"] == 1 and w7["hold"] == 1 and w7["down"] == 0

    w30 = er._window_counts(df, 30)
    assert w30["up"] == 1 and w30["hold"] == 1 and w30["down"] == 1

    w90 = er._window_counts(df, 90)
    assert w90["up"] == 1 and w90["down"] == 2 and w90["hold"] == 1


def test_window_counts_using_period_counts_schema():
    """yfinance sometimes returns columns like strongBuy/buy/hold/sell/strongSell."""
    df = pd.DataFrame({
        "strongBuy": [5, 6], "buy": [3, 4], "hold": [2, 1],
        "sell": [1, 1], "strongSell": [0, 0],
    })
    w = er._window_counts(df, 30)
    # Takes the last row
    assert w == {"up": 10, "down": 1, "hold": 1, "total": 12}


def test_window_counts_unknown_schema():
    df = pd.DataFrame({"foo": [1, 2, 3]})
    assert er._window_counts(df, 30) == {"up": 0, "down": 0, "hold": 0, "total": 0}


def test_get_revisions_trend_with_mocks():
    rec_rows = []
    for days_ago, frm, to in [(3, "Hold", "Buy"), (10, "Buy", "Hold"), (40, "Hold", "Sell")]:
        rec_rows.append({"date": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_ago),
                          "From Grade": frm, "To Grade": to})
    rec_df = pd.DataFrame(rec_rows).set_index("date")

    fake_targets = {"mean": 200.0, "median": 195.0, "high": 230.0, "low": 170.0,
                    "number_of_analysts": 12}

    with patch.object(er, "_read_yf_recommendations", return_value=rec_df), \
         patch.object(er, "_read_yf_price_targets", return_value=fake_targets):
        # _read_yf_price_targets returning a dict short-circuits the yfinance .info call path
        result = er.get_revisions_trend("MOCK")

    assert result is not None
    assert result["ticker"] == "MOCK"
    assert result["windows"]["7d"]["up"] == 1
    assert result["consensus_label"] in {"strongly_bullish", "bullish", "neutral", "bearish", "strongly_bearish"}
    assert result["price_targets"]["mean"] == 200.0


def test_get_revisions_trend_none_when_everything_fails():
    with patch.object(er, "_read_yf_recommendations", return_value=None), \
         patch.object(er, "_read_yf_price_targets", return_value=None):
        assert er.get_revisions_trend("GHOST") is None
