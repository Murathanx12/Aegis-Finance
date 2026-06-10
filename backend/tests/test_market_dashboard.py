"""Tests for unified market dashboard service."""



class TestDashboardSections:
    """Test individual dashboard section builders with mocked data."""

    def test_market_section_basic(self):
        """Market section should return core fields."""
        import pandas as pd
        import numpy as np
        from backend.services.market_dashboard import _build_market_section

        dates = pd.bdate_range("2023-01-01", periods=300)
        data = pd.DataFrame({
            "SP500": np.linspace(4000, 5000, 300),
            "VIX": np.random.uniform(15, 25, 300),
            "T10Y": np.random.uniform(3.5, 4.5, 300),
            "T3M": np.random.uniform(4.5, 5.5, 300),
        }, index=dates)

        result = _build_market_section(data)
        assert result is not None
        assert "sp500" in result
        assert "vix" in result
        assert "yield_spread" in result
        assert result["sp500"] > 0

    def test_market_section_missing_columns(self):
        """Should handle missing VIX/yield columns gracefully."""
        import pandas as pd
        import numpy as np
        from backend.services.market_dashboard import _build_market_section

        dates = pd.bdate_range("2023-01-01", periods=300)
        data = pd.DataFrame({
            "SP500": np.linspace(4000, 5000, 300),
        }, index=dates)

        result = _build_market_section(data)
        assert result is not None
        assert result["vix"] is None
        assert result["yield_spread"] is None

    def test_crypto_section_returns_none_on_failure(self):
        """Crypto section should return None, not crash."""
        import pandas as pd
        from backend.services.market_dashboard import _build_crypto_section

        # Empty dataframe — no SP500 column
        data = pd.DataFrame({"SP500": []})
        result = _build_crypto_section(data)
        # Should be None or dict — never raise
        assert result is None or isinstance(result, dict)

    def test_breadth_section_with_no_cache(self):
        """Breadth section should return None when no momentum cache."""
        from backend.services.market_dashboard import _build_breadth_section

        result = _build_breadth_section()
        # With no cached data, should gracefully return None
        assert result is None or isinstance(result, dict)

    def test_fixed_income_section_empty_data(self):
        """Fixed income should handle empty FRED data."""
        from backend.services.market_dashboard import _build_fixed_income_section

        result = _build_fixed_income_section({})
        # Should return None or partial dict
        assert result is None or isinstance(result, dict)

    def test_economic_section(self):
        """Economic section should not crash."""
        from backend.services.market_dashboard import _build_economic_section

        result = _build_economic_section()
        assert result is None or isinstance(result, dict)

    def test_sentiment_section(self):
        """Sentiment section should not crash."""
        from backend.services.market_dashboard import _build_sentiment_section

        result = _build_sentiment_section()
        assert result is None or isinstance(result, dict)
