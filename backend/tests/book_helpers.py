"""Shared builders for the lane B tests. Not a test module — no `test_` names.

They live here rather than being imported between test modules because pytest
fixtures imported across modules shadow themselves in every consuming signature
(F811), and the fix people reach for is a blanket `# noqa` that also hides the
real redefinitions.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from backend.strategy.contract import (Benchmark, Construction, CostModel,
                                       HoldRule, Licence, LossBudget, Objective,
                                       Signal, Sizing, Strategy, Universe)

REFERENCE_LANES = ("conservative", "balanced", "aggressive", "balanced-ew-control")


def make_strategy(*, strategy_id: str = "test-book-1",
                  zero_cost: bool = False, rule: str = "top_k",
                  symbols: list[str] | None = None) -> Strategy:
    return Strategy(
        strategy_id=strategy_id, title="a test book",
        universe=Universe(name="test-universe", source="test",
                          floor_dollar_vol_usd=1_000_000.0, min_price_usd=1.0),
        signal=Signal(name="mom_21", column="mom_21", direction=1),
        construction=Construction(rule=rule, k=3, weighting="ew",
                                  max_single_name=0.34),
        hold=HoldRule(horizon_periods=21, stop_loss=-0.08),
        sizing=Sizing(rule="equal_weight", notional_usd=100_000.0),
        # `Policy` refuses zero_cost_diagnostic=True ALONGSIDE non-zero costs,
        # so the diagnostic variant is genuinely frictionless.
        costs=(CostModel(transaction_cost_bps=0.0, slippage_bps=0.0,
                         zero_cost_diagnostic=True) if zero_cost
               else CostModel(transaction_cost_bps=5.0, slippage_bps=1.0)),
        benchmark=Benchmark(),
        objective=Objective(name="terminal_wealth_at_drawdown_budget",
                            drawdown_budget=-0.25),
        loss_budget=LossBudget(positions_judged=12, expected_losers=5),
        licence=Licence.PRODUCT_EXPERIMENT,
        engine_params={"symbols": symbols} if symbols else {},
    )


def synthetic_bars(symbols=("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"),
                   n: int = 150, end: date | None = None):
    """Deterministic daily bars. Dates are DERIVED from `today`, never literal
    (session protocol rule 5: a fixture that hard-codes a calendar moment fails
    the day after that moment passes)."""
    import numpy as np
    import pandas as pd

    end = end or date.today()
    rng = np.random.default_rng(7)
    days = pd.bdate_range(end=pd.Timestamp(end), periods=n)
    rows = []
    for i, sym in enumerate(symbols):
        px = 50.0 + 10.0 * i
        for d in days:
            px = max(1.0, px * float(1.0 + rng.normal(0.0004, 0.012)))
            rows.append({"symbol": sym, "date": d, "open": px, "high": px * 1.01,
                         "low": px * 0.99, "close": px,
                         "volume": 5_000_000 + 100_000 * i, "vwap": px,
                         "trades": 1000})
    return pd.DataFrame(rows)


def seeded_db(path):
    """A fresh PI database with the four reference lanes and three NAV rows each."""
    from backend.db import get_connection, init_db
    init_db(path)
    conn = get_connection(path)
    for lane in REFERENCE_LANES:
        conn.execute("INSERT OR IGNORE INTO paper_portfolios VALUES (?,?,?,?)",
                     (lane, "2026-01-02", 100_000.0, "cfg-v1"))
        for i in range(3):
            d = (date(2026, 1, 2) + timedelta(days=i)).isoformat()
            conn.execute("INSERT OR REPLACE INTO paper_nav VALUES (?,?,?,?,?)",
                         (lane, d, 100_000.0 + 10 * i, "cfg-v1",
                          "2026-01-02T00:00:00+00:00"))
    conn.commit()
    return conn


def lane_rows(conn: sqlite3.Connection) -> list[tuple]:
    """The reference lanes' NAV rows, verbatim, for the byte-identity check."""
    return [tuple(r) for r in conn.execute(
        "SELECT portfolio_id, date, nav, config_version, computed_at FROM paper_nav "
        "WHERE portfolio_id IN (%s) ORDER BY portfolio_id, date"
        % ",".join("?" for _ in REFERENCE_LANES), REFERENCE_LANES).fetchall()]
