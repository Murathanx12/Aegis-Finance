"""
TRIAL-QUALITY-IC — offline tests for the GP/A score + collector.

Invariants: score IS GP/A alone (diagnostics never enter it); missing
fundamentals are explicit statuses; Gross Profit falls back to Revenue−COGS;
collector snapshots into the PIT store.
"""

import pandas as pd
import pytest

from backend.services import quality_signal as qs


def _statements(gp=400.0, assets=1000.0, ni=120.0, cfo=150.0,
                rev=1000.0, cogs=None, with_gp_row=True, years=2):
    cols = pd.to_datetime(["2025-12-31", "2024-12-31"][:years])
    def _df(rows):
        return pd.DataFrame({c: {k: v for k, v in rows.items()} for c in cols}).T.T
    income_rows = {"Total Revenue": rev, "Net Income": ni}
    if with_gp_row:
        income_rows["Gross Profit"] = gp
    if cogs is not None:
        income_rows["Cost Of Revenue"] = cogs
    income = pd.DataFrame({c: income_rows for c in cols})
    balance = pd.DataFrame({c: {"Total Assets": assets} for c in cols})
    cash = pd.DataFrame({c: {"Operating Cash Flow": cfo} for c in cols})
    return {"income": income, "balance": balance, "cashflow": cash}


class TestScore:
    def test_gpa_is_the_score(self):
        out = qs.compute_quality_score(_statements(gp=400, assets=1000))
        assert out["status"] == "ok"
        assert out["quality_score"] == pytest.approx(0.4)

    def test_diagnostics_do_not_change_score(self):
        good = qs.compute_quality_score(_statements(ni=120, cfo=150))
        bad = qs.compute_quality_score(_statements(ni=-50, cfo=-10))
        assert good["quality_score"] == bad["quality_score"]  # GP/A identical
        assert good["n_checks_passed"] > bad["n_checks_passed"]

    def test_gross_profit_fallback_from_revenue_minus_cogs(self):
        out = qs.compute_quality_score(
            _statements(with_gp_row=False, rev=1000.0, cogs=600.0, assets=1000))
        assert out["status"] == "ok"
        assert out["quality_score"] == pytest.approx(0.4)

    def test_missing_fundamentals_explicit(self):
        out = qs.compute_quality_score({"income": None, "balance": None,
                                        "cashflow": None})
        assert out["status"] == "insufficient_fundamentals"
        assert out["quality_score"] == 0.0

    def test_degenerate_assets(self):
        out = qs.compute_quality_score(_statements(assets=0.0))
        assert out["status"] == "degenerate_assets"

    def test_accrual_diagnostic(self):
        out = qs.compute_quality_score(_statements(ni=120, cfo=150))
        assert out["piotroski_subset"]["accruals_ok"] is True
        out2 = qs.compute_quality_score(_statements(ni=150, cfo=120))
        assert out2["piotroski_subset"]["accruals_ok"] is False


class TestCollector:
    def test_snapshots_into_pit(self, tmp_path):
        from backend.db import get_connection, init_db
        from backend.services.portfolio_intelligence.quality_collector import (
            collect_quality_scores,
        )
        db = tmp_path / "q.db"
        init_db(db)
        out = collect_quality_scores(
            db_path=db, tickers=["AAPL", "KO"],
            fetch=lambda t: _statements(gp=400, assets=1000),
            as_of="2026-07-09")
        assert out["status"] == "collected"
        assert out["nonzero"] == 2
        conn = get_connection(db)
        try:
            rows = conn.execute(
                "SELECT key, value FROM pit_observations WHERE key LIKE 'quality_score:%'"
            ).fetchall()
        finally:
            conn.close()
        assert len(rows) == 2
        assert all(r["value"] == pytest.approx(0.4) for r in rows)
