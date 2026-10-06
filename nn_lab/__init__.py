"""nn_lab -- the nightly-improving cross-sectional model (2026-09-28).

A SEPARATE lab. It reads the project's data files (bars, SEC facts, analyst
revisions, news panel, forecast ledger) and nothing from the live decision path;
nothing in the live path imports it. See nn_lab/README.md.
"""


def health_contract(*args, **kwargs) -> dict:
    """One-line verdict on the newest nightly receipt (nn_lab/health.py, review C5 F8)."""
    from nn_lab.health import health_contract as _hc
    return _hc(*args, **kwargs)
