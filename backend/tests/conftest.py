"""
Pytest configuration for backend tests.
"""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (require network/data fetching)"
    )
