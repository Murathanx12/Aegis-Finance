"""
Task 3: Risk Score Stress Test
================================

Feeds the risk scorer data from known stress and calm periods
and verifies scores are appropriately elevated or low.
Uses real historical data via yfinance.
"""

import logging
import pytest
import pandas as pd
import yfinance as yf

from backend.services.risk_scorer import build_risk_score

logger = logging.getLogger(__name__)


def _fetch_period(start: str, end: str) -> pd.DataFrame:
    """Fetch market data for a specific historical period."""
    tickers = {"^GSPC": "SP500", "^VIX": "VIX"}
    frames = {}
    for yf_ticker, col_name in tickers.items():
        data = yf.download(yf_ticker, start=start, end=end, progress=False)["Close"]
        if isinstance(data, pd.DataFrame):
            data = data.squeeze()
        frames[col_name] = data

    df = pd.DataFrame(frames).dropna()
    return df


def _get_risk_score_at_end(start: str, end: str) -> float:
    """Get the risk score at the end of the period."""
    df = _fetch_period(start, end)
    if df.empty:
        return float("nan")

    df["Risk_Score"] = build_risk_score(df)
    return float(df["Risk_Score"].iloc[-1])


class TestRiskScoreStress:
    """Test that risk scores are elevated during stress and low during calm."""

    def test_covid_peak_stress_march_2020(self):
        """March 16, 2020 (VIX hit 82): risk score should be elevated (> 0.6)."""
        score = _get_risk_score_at_end("2019-01-01", "2020-03-20")
        logger.info("March 2020 risk score: %.2f", score)
        if pd.isna(score):
            pytest.skip("Could not fetch data")
        assert score > 0.6, f"Risk score during COVID peak should be > 0.6, got {score:.2f}"

    def test_svb_collapse_march_2023(self):
        """March 2023 (SVB collapse): risk score should be elevated (> 0.3)."""
        score = _get_risk_score_at_end("2022-01-01", "2023-03-20")
        logger.info("March 2023 (SVB) risk score: %.2f", score)
        if pd.isna(score):
            pytest.skip("Could not fetch data")
        # SVB was a sector-specific event, VIX spiked to ~30 briefly
        # Risk score may not be as elevated as COVID
        assert score > 0.3, f"Risk score during SVB crisis should be > 0.3, got {score:.2f}"

    def test_japan_carry_trade_aug_2024(self):
        """August 5, 2024 (Japan carry trade unwind): risk score should be elevated (> 0.3)."""
        score = _get_risk_score_at_end("2023-06-01", "2024-08-10")
        logger.info("Aug 2024 carry trade unwind risk score: %.2f", score)
        if pd.isna(score):
            pytest.skip("Could not fetch data")
        assert score > 0.3, f"Risk score during carry trade unwind should be > 0.3, got {score:.2f}"

    def test_tariff_april_2025(self):
        """April 2025 (tariff announcement): risk score should be elevated (> 0.4)."""
        score = _get_risk_score_at_end("2024-01-01", "2025-04-10")
        logger.info("April 2025 tariff risk score: %.2f", score)
        if pd.isna(score):
            pytest.skip("Could not fetch data")
        assert score > 0.4, f"Risk score during tariff crisis should be > 0.4, got {score:.2f}"

    def test_calm_july_2021(self):
        """July 2021 (calm bull market): risk score should be low (< 0.5)."""
        score = _get_risk_score_at_end("2020-06-01", "2021-07-30")
        logger.info("July 2021 risk score: %.2f", score)
        if pd.isna(score):
            pytest.skip("Could not fetch data")
        assert score < 0.5, f"Risk score during calm July 2021 should be < 0.5, got {score:.2f}"

    def test_calm_december_2023(self):
        """December 2023 (year-end rally): risk score should be low (< 0.5)."""
        score = _get_risk_score_at_end("2022-12-01", "2023-12-29")
        logger.info("December 2023 risk score: %.2f", score)
        if pd.isna(score):
            pytest.skip("Could not fetch data")
        assert score < 0.5, f"Risk score during calm Dec 2023 should be < 0.5, got {score:.2f}"
