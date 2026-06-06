"""Tests for signal_optimizer — grid search over signal weights.

The full optimizer requires yfinance downloads; smoke-test the module loads
and that the public entrypoint handles the no-data path cleanly.
"""

from unittest.mock import patch

import pandas as pd
import pytest


def test_module_imports():
    from backend.services import signal_optimizer
    assert hasattr(signal_optimizer, "optimize_weights")


def test_optimize_weights_no_data_returns_error():
    """If yfinance returns empty data, optimizer should report an error string — not crash."""
    from backend.services import signal_optimizer

    empty_df = pd.DataFrame({"Close": pd.Series(dtype=float)})
    with patch("yfinance.download", return_value=empty_df):
        try:
            result = signal_optimizer.optimize_weights(start_date="2024-01-01", end_date="2024-02-01")
        except Exception as e:
            # The optimizer should either return a dict with 'error' or raise a handled error.
            # An unhandled exception is a bug — catch and report so the test is clearer.
            pytest.fail(f"optimize_weights raised on empty input: {type(e).__name__}: {e}")

    assert isinstance(result, dict)
    assert "error" in result


@pytest.mark.slow
def test_optimize_weights_small_range():
    """End-to-end smoke test with network — marked slow."""
    from backend.services import signal_optimizer

    result = signal_optimizer.optimize_weights(start_date="2024-01-01", end_date="2024-03-01")
    assert isinstance(result, dict)
    # Either produced results or returned an error — never raise
    assert "error" in result or "top_3" in result
    # When results exist, the overfitting guard must be attached.
    if "top_3" in result:
        assert "overfitting_guard" in result
