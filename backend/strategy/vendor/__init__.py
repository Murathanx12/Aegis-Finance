"""Verbatim third-party code, kept byte-identical to its upstream clone.

Everything in this package is **MIT** (Vibe-Trading / HKUDS) and is copied
unedited, with the project's LICENSE prepended to each file as the MIT
condition requires. Nothing here is Aegis's; nothing here is modified. If a
behaviour needs changing, it changes in `backend/strategy/execution.py`, which
wraps these, so that the vendored bodies stay diffable against upstream.

WHY THERE IS AN IMPORT SHIM
===========================
`factor_costs.py` opens with `from src.quantlib.impact import ...`, which is
upstream's own package layout. Rewriting that one line would make the file no
longer byte-identical, and "byte-identical except for the bits we changed" is
not a property worth having. So the module is registered under the name it
expects instead. The alias is installed only when nothing else owns those
names; if some other `src` package is already imported, this REFUSES rather
than resolving `factor_costs`'s import against a stranger's module.
"""

from __future__ import annotations

import sys
import types

from backend.strategy.vendor import impact as _impact


def _install_alias() -> None:
    existing = sys.modules.get("src.quantlib.impact")
    if existing is _impact:
        return
    if existing is not None:
        raise ImportError(
            "REFUSED: `src.quantlib.impact` is already imported and is not the "
            "vendored Vibe-Trading module. Resolving the vendored "
            "`factor_costs` import against a different module would silently "
            "price impact with someone else's formulas.")
    src = sys.modules.get("src")
    if src is None:
        src = types.ModuleType("src")
        src.__path__ = []                       # type: ignore[attr-defined]
        sys.modules["src"] = src
    quantlib = sys.modules.get("src.quantlib")
    if quantlib is None:
        quantlib = types.ModuleType("src.quantlib")
        quantlib.__path__ = []                  # type: ignore[attr-defined]
        sys.modules["src.quantlib"] = quantlib
    src.quantlib = quantlib                     # type: ignore[attr-defined]
    quantlib.impact = _impact                   # type: ignore[attr-defined]
    sys.modules["src.quantlib.impact"] = _impact


_install_alias()

from backend.strategy.vendor import breakeven as _breakeven   # noqa: E402
from backend.strategy.vendor import factor_costs as _factor_costs  # noqa: E402

breakeven_fee_bps = _breakeven.breakeven_fee_bps
apply_adv_capacity = _factor_costs.apply_adv_capacity
borrow_cost = _factor_costs.borrow_cost
rebalance_cost = _factor_costs.rebalance_cost
CapacityResult = _factor_costs.CapacityResult
PeriodCost = _factor_costs.PeriodCost
DEFAULT_MAX_PARTICIPATION = _factor_costs.DEFAULT_MAX_PARTICIPATION
MARKET_BORROW_RATES = _factor_costs.MARKET_BORROW_RATES

#: Upstream provenance, quoted on receipts so a reader can check the copy.
VENDOR = {
    "project": "Vibe-Trading (HKUDS)",
    "licence": "MIT",
    "head": "a4f06a29",
    "cloned": "2026-09-07",
    "files": {
        "impact.py": "agent/src/quantlib/impact.py",
        "factor_costs.py": "agent/backtest/factor_costs.py",
        "breakeven.py": "agent/src/strategy_discovery/models.py::breakeven_fee_bps",
    },
}

__all__ = ["CapacityResult", "DEFAULT_MAX_PARTICIPATION", "MARKET_BORROW_RATES",
           "PeriodCost", "VENDOR", "apply_adv_capacity", "borrow_cost",
           "breakeven_fee_bps", "rebalance_cost"]
