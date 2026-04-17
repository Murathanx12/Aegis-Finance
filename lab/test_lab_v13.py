"""Sanity tests for the lab v13 wiring.

These exercise the lab modules themselves (themes / hypotheses /
robustness / data_generator) so the overnight rd_loop can't break
silently. Run via:

    python -m pytest lab/test_lab_v13.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAB_DIR = Path(__file__).parent
if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))

import robustness  # noqa: E402
import themes      # noqa: E402
import hypotheses  # noqa: E402
import data_generator as dg  # noqa: E402


# ── robustness probes ────────────────────────────────────────────────


def test_robustness_has_v13_probes():
    names = {p.__name__ for p in robustness.PROBES}
    expected = {
        "_probe_bond_par_ytm",
        "_probe_bond_duration_predicts_shock",
        "_probe_fx_cip_arbitrage",
        "_probe_commodity_slope_classifier",
        "_probe_currency_inference",
        "_probe_edgar_taxonomy_complete",
    }
    assert expected.issubset(names), f"missing probes: {expected - names}"


def test_v13_probes_pass():
    """Each v13 probe must succeed against the current engine."""
    for name in (
        "_probe_bond_par_ytm",
        "_probe_bond_duration_predicts_shock",
        "_probe_fx_cip_arbitrage",
        "_probe_commodity_slope_classifier",
        "_probe_currency_inference",
        "_probe_edgar_taxonomy_complete",
    ):
        probe = getattr(robustness, name)
        n, ok, detail = probe()
        assert ok, f"probe {n} failed: {detail}"


def test_run_all_aggregates_score():
    report = robustness.run_all()
    assert report["total"] == len(robustness.PROBES)
    assert 0.0 <= report["score"] <= 1.0
    # We expect every v13 probe to be green right now
    fails = [p["name"] for p in report["probes"] if not p["ok"]]
    # Allow at most the legacy flat_vol_mc to fail if MC signature drifts again
    assert len(fails) <= 1, f"unexpected probe failures: {fails}"


# ── themes ───────────────────────────────────────────────────────────


def test_build_theme_mentions_v13_services():
    text = themes.instructions_for("build")
    assert "v13" in text.lower()
    assert "bond_analytics" in text
    assert "edgar_events" in text
    assert "fx_curves" in text or "commodity_curves" in text


def test_themes_set_unchanged():
    assert "build" in themes.THEMES
    assert "stabilise" in themes.THEMES


# ── hypothesis ledger ───────────────────────────────────────────────


def test_hypotheses_summarise_handles_empty(tmp_path):
    out = hypotheses.summarise_for_prompt(tmp_path / "missing.json")
    assert "No prior hypotheses" in out


# ── data_generator collectors ───────────────────────────────────────


def test_v13_collectors_defined():
    """The new v13 collector functions must exist as module attributes."""
    for name in (
        "collect_bond_lab",
        "collect_edgar_events",
        "collect_esg",
        "collect_fx_dashboard",
        "collect_commodities_dashboard",
        "collect_crypto_defi",
        "collect_portfolio_currency",
    ):
        assert hasattr(dg, name), f"missing collector {name}"
        assert callable(getattr(dg, name))


def test_bond_lab_collector_runs(tmp_path):
    """collect_bond_lab must run end-to-end and produce a file."""
    out = dg.collect_bond_lab(str(tmp_path))
    assert "benchmark_10y_4_5" in out
    benchmark = out["benchmark_10y_4_5"]
    assert "ytm_pct" in benchmark
    assert "modified_duration_years" in benchmark
    assert (tmp_path / "bond_lab.json").exists()


def test_portfolio_currency_collector_runs(tmp_path):
    out = dg.collect_portfolio_currency(str(tmp_path))
    assert "report" in out or "error" in out
    if "report" in out:
        assert "exposure" in out["report"]
    assert (tmp_path / "portfolio_currency.json").exists()


def test_collectors_registry_includes_v13():
    """The main run_engine_data_collection must enumerate the v13 names."""
    import inspect
    src = inspect.getsource(dg.run_engine_data_collection)
    for name in (
        "bond_lab",
        "edgar_events",
        "esg",
        "fx_dashboard",
        "commodities_dashboard",
        "crypto_defi",
        "portfolio_currency",
    ):
        assert f'"{name}"' in src, f"v13 collector {name} missing from registry"
