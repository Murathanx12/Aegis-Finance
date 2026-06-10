"""
PI test fixtures.

The optimizer price panel is network-fetched in production; tests must stay
offline and deterministic. Default every test to "no panel" → the hard gate
falls back to equal-weight (the pre-v2 behavior existing tests assert).
Optimizer tests that need a panel patch _get_price_panel themselves.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_optimizer_panel(monkeypatch):
    from backend.services.portfolio_intelligence import reference_engine

    monkeypatch.setattr(reference_engine, "_get_price_panel", lambda *a, **k: None)
    yield
