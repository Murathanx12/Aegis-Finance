"""nn_lab test isolation: no test reads the REAL exclusion list on disk (a synthetic symbol
such as AAA is also a real ETF ticker). A test that needs a list plants its own."""
from __future__ import annotations

import pytest

from nn_lab import config as C
from nn_lab import universe_filter as U


@pytest.fixture(autouse=True)
def _no_real_etf_list(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ETF_EXCLUSIONS", tmp_path / "no_etf_list.json")
    U._CACHE.clear()
    yield
    U._CACHE.clear()
