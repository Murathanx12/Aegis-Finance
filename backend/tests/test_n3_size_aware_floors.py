"""Tests for `scripts/n3_size_aware_floors.py` (Night Lab 2026-09-07, lane N3).

CI RUNS ON LINUX WITH NO LOCAL DATA (CLAUDE.md): every test that touches the
long panel, CRSP dsf yearly files, or the TAQ liquidity-band receipt MUST
`pytest.skip` when that file is absent. The arithmetic that does not need any
of those files (the size-aware floor formula, the TAQ band lookup, the Holm
helper, the beta-matched OLS, path absoluteness) runs unconditionally on
synthetic inputs.
"""

from __future__ import annotations

import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath

import numpy as np
import pandas as pd
import pytest

from scripts import n3_size_aware_floors as N3


# --------------------------------------------------------- the size-aware floor

def test_size_aware_floor_matches_the_brainstorm_worked_example():
    """The mandate's own arithmetic: a $100k book at 1% ADV participation
    needs a $500k/day floor, not the flat $3m institutional one."""
    f, why = N3.size_aware_floor(100_000.0)
    assert f == pytest.approx(500_000.0)
    assert why is None


def test_size_aware_floor_scales_linearly_with_book_size():
    f100k, _ = N3.size_aware_floor(100_000.0)
    f1m, _ = N3.size_aware_floor(1_000_000.0)
    f10m, _ = N3.size_aware_floor(10_000_000.0)
    assert f1m == pytest.approx(f100k * 10)
    assert f10m == pytest.approx(f100k * 100)


def test_size_aware_floor_refuses_on_missing_book_size():
    f, why = N3.size_aware_floor(None)
    assert f is None
    assert why is not None and "book_size_usd" in why


def test_size_aware_floor_refuses_on_missing_participation():
    f, why = N3.size_aware_floor(100_000.0, participation=None)
    assert f is None and why is not None and "participation" in why


def test_size_aware_floor_refuses_rather_than_divide_by_zero():
    f, why = N3.size_aware_floor(100_000.0, participation=0.0)
    assert f is None
    assert why is not None


def test_size_aware_floor_refuses_on_negative_book_size():
    f, why = N3.size_aware_floor(-1.0)
    assert f is None and why is not None


def test_size_aware_floor_never_raises_on_bad_inputs():
    """A guard derives its inputs or refuses -- it must not throw."""
    for bad in (None, -1.0, 0.0, float("nan")):
        f, why = N3.size_aware_floor(bad)
        # nan > 0 is False in Python, so nan is also correctly refused.
        assert f is None
        assert why is not None


# ------------------------------------------------------------- the TAQ bands

def test_taq_band_edges_are_contiguous_and_span_from_100k():
    edges = N3.TAQ_BAND_EDGES
    assert edges[0][1] == 1e5
    for (name_a, lo_a, hi_a), (name_b, lo_b, hi_b) in zip(edges, edges[1:]):
        assert hi_a == lo_b, f"{name_a} ends at {hi_a}, {name_b} starts at {lo_b}"
    assert edges[-1][2] == float("inf")


@pytest.mark.parametrize("dv,expected_band", [
    (500_000.0, "100k-1m"),
    (999_999.0, "100k-1m"),
    (1_000_000.0, "1m-5m"),
    (5_000_000.0, "5m-10m"),
    (5.0e7, "50m+"),
    (1.0e9, "50m+"),
])
def test_taq_band_for_matches_expected(dv, expected_band):
    assert N3.taq_band_for(dv) == expected_band


def test_taq_band_for_below_lowest_band_is_none():
    assert N3.taq_band_for(1.0) is None
    assert N3.taq_band_for(0.0) is None


def test_taq_band_for_refuses_on_missing_or_nonfinite_input():
    assert N3.taq_band_for(None) is None
    assert N3.taq_band_for(float("nan")) is None
    assert N3.taq_band_for(float("inf")) is None


def test_taq_cost_for_floor_cannot_determine_when_receipt_missing():
    r = N3.taq_cost_for_floor(500_000.0, bands=None)
    assert r["verdict"] == "CANNOT DETERMINE"
    assert "why" in r


def test_taq_cost_for_floor_cannot_determine_on_unmeasured_band():
    r = N3.taq_cost_for_floor(500_000.0, bands={"100k-1m": {"n_measured": 0}})
    assert r["verdict"] == "CANNOT DETERMINE"


def test_taq_cost_for_floor_reads_a_measured_band():
    bands = {"1m-5m": {"n_measured": 30, "round_trip_bps": 38.7,
                       "cost_pct_per_year_at_monthly_turnover": 4.64}}
    r = N3.taq_cost_for_floor(2_000_000.0, bands)
    assert r["verdict"] == "MEASURED"
    assert r["band"] == "1m-5m"
    assert r["round_trip_bps"] == 38.7
    # cost_bps is charged ONE-WAY at the grading call site, which doubles it
    # for the round trip -- so one_way_bps must be exactly half of the
    # measured round-trip figure the TAQ script defines as a FULL spread.
    assert r["one_way_bps"] == pytest.approx(19.35)


def test_taq_cost_for_floor_none_input_cannot_determine():
    r = N3.taq_cost_for_floor(None, {"1m-5m": {"n_measured": 30, "round_trip_bps": 1.0,
                                               "cost_pct_per_year_at_monthly_turnover": 1.0}})
    assert r["verdict"] == "CANNOT DETERMINE"


# ------------------------------------------------------------------ Holm/OLS

def test_holm_family_orders_and_bounds_p_values():
    cells = {
        "a": {"PRIMARY_beta_matched": {"p_one_sided": 0.001}},
        "b": {"PRIMARY_beta_matched": {"p_one_sided": 0.02}},
        "c": {"PRIMARY_beta_matched": {"p_one_sided": 0.5}},
    }
    fam = N3._holm_family(cells)
    assert fam["size"] == 3
    assert fam["best_cell"] == "a"
    adj = fam["holm_adjusted"]
    assert adj["a"] == pytest.approx(0.003)
    assert adj["b"] == pytest.approx(0.04)
    assert adj["c"] == pytest.approx(0.5)
    vals = [adj[k] for k in ("a", "b", "c")]
    assert vals == sorted(vals)


def test_holm_family_ignores_cells_with_no_p_value():
    cells = {"a": {"PRIMARY_beta_matched": {"p_one_sided": 0.01}},
            "b": {"PRIMARY_beta_matched": {}},
            "c": {"verdict": "CANNOT DETERMINE"}}
    fam = N3._holm_family(cells)
    assert fam["size"] == 1
    assert fam["best_cell"] == "a"


def test_ols_market_model_recovers_a_planted_beta():
    rng = np.random.default_rng(20260907)
    n = 240
    mkt = rng.normal(0.0, 0.04, n)
    y = 1.3 * mkt + rng.normal(0.0, 0.001, n)     # beta = 1.3, near-zero noise
    reg = N3.ols_market_model(y, mkt)
    assert reg["beta"] == pytest.approx(1.3, abs=0.05)


def test_ols_market_model_cannot_determine_on_too_few_months():
    reg = N3.ols_market_model([0.01, 0.02, 0.03], [0.01, 0.02, 0.03])
    assert reg["verdict"] == "CANNOT DETERMINE"


def test_grade_cell_cannot_determine_with_no_series():
    blk, ex = N3.grade_cell({"months": 0}, label="x", cost_source={})
    assert blk["verdict"] == "CANNOT DETERMINE"
    assert ex.empty


# ------------------------------------------------------------ path shape

def test_module_paths_are_absolute():
    for p in (N3.OUT_DIR, N3.TAQ_BAND_RECEIPT, N3.LONG_TABLE, N3.CRSP_DSF_DIR):
        s = str(p)
        assert PureWindowsPath(s).is_absolute() or PurePosixPath(s).is_absolute(), \
            f"{s!r} is not absolute under either path grammar"


def test_out_dir_is_the_night_lab_2026_09_07_dir():
    assert N3.OUT_DIR.name == "night_lab_2026-09-07"


def test_book_sizes_match_the_mandate():
    assert N3.BOOK_SIZES_USD == (100_000.0, 1_000_000.0, 10_000_000.0)


def test_institutional_floor_matches_evaluate_tradable_dollar_vol():
    """One floor, one number -- if `learner.evaluate.TRADABLE_DOLLAR_VOL` ever
    moves, this restated constant must move with it or the 'institutional
    flat $3m' comparison silently stops being the house's own floor."""
    from learner import evaluate as E
    assert N3.INSTITUTIONAL_FLOOR_USD == E.TRADABLE_DOLLAR_VOL


# ------------------------------------------------------- taq band pin vs receipt

def test_taq_band_edges_match_the_pulled_receipt_when_present():
    if not N3.TAQ_BAND_RECEIPT.exists():
        pytest.skip(f"{N3.TAQ_BAND_RECEIPT} is absent on this box")
    d = json.loads(N3.TAQ_BAND_RECEIPT.read_text(encoding="utf-8"))
    receipt_bands = set(d.get("summary", {}).keys())
    pinned_bands = {name for name, _lo, _hi in N3.TAQ_BAND_EDGES}
    assert pinned_bands == receipt_bands, (
        "TAQ_BAND_EDGES has drifted from scripts/taq_spread_by_liquidity_band.py's "
        f"own BANDS: pinned={pinned_bands} receipt={receipt_bands}")


def test_taq_cost_for_100k_1m_matches_the_pulled_receipt():
    if not N3.TAQ_BAND_RECEIPT.exists():
        pytest.skip(f"{N3.TAQ_BAND_RECEIPT} is absent on this box")
    bands = N3.load_taq_bands()
    r = N3.taq_cost_for_floor(500_000.0, bands)
    assert r["verdict"] == "MEASURED"
    assert r["band"] == "100k-1m"
    # This is the headline number the reversal/S28 re-grades depend on: a
    # thin name costs roughly 75bps one-way, not the 10-25bps this repo
    # assumes elsewhere. A silent re-pull that halves it should fail loudly.
    assert r["one_way_bps"] > 30.0


# ------------------------------------------------------- receipt-shaped runs

def test_run_populate_observe_tier_refuses_and_names_why():
    out = N3.run_populate_observe_tier()
    assert out["status"] == "REFUSED"
    assert "network" in out["why"].lower() or "venue" in out["why"].lower()
    assert "aegis-alpha-terminal/alpha/universe.py" in out["files_touched_in_the_sibling_repo"]


def test_run_s28_band_regrade_skips_without_the_long_panel():
    if N3.LONG_TABLE.exists():
        pytest.skip(f"{N3.LONG_TABLE} is present on this box; run-with-data is exercised manually")
    out = N3.run_s28_band_regrade()
    assert out["status"] == "SKIPPED"


def test_run_reversal_cell_regrade_skips_without_crsp_dsf():
    has_any = any((N3.CRSP_DSF_DIR / f"crsp_dsf_{y}.parquet").exists() for y in range(2013, 2025))
    if has_any:
        pytest.skip("crsp_dsf_*.parquet is present on this box; run-with-data is exercised manually")
    out = N3.run_reversal_cell_regrade()
    assert out["status"] == "SKIPPED"


def test_run_edge_vs_floor_curve_skips_without_the_long_panel():
    if N3.LONG_TABLE.exists():
        pytest.skip(f"{N3.LONG_TABLE} is present on this box; run-with-data is exercised manually")
    out = N3.run_edge_vs_floor_curve()
    assert out["status"] == "SKIPPED"


def test_all_three_data_jobs_refuse_under_the_memory_backoff_line(monkeypatch):
    """A backoff is only real if it actually stops the job. Force `_free_gb`
    to read below the 2 GB line and confirm every panel-loading job refuses
    before touching disk, regardless of what data happens to be present."""
    monkeypatch.setattr(N3, "_free_gb", lambda: 1.0)
    for fn in (N3.run_edge_vs_floor_curve, N3.run_s28_band_regrade,
              N3.run_reversal_cell_regrade):
        out = fn()
        assert out["status"] == "REFUSED"
        assert "GB free" in out["headline"]


# --------------------------------------------------------------- receipts on disk

@pytest.mark.parametrize("name", [
    "N3_populate_observe_tier.json",
    "N3_edge_vs_floor_curve.json",
    "N3_reversal_cell_regrade.json",
    "N3_s28_band_regrade.json",
])
def test_receipt_is_provenance_clean_when_present(name):
    path = N3.OUT_DIR / name
    if not path.exists():
        pytest.skip(f"{path} has not been generated on this box yet")
    from backend.services import receipt_provenance as RP
    d = json.loads(path.read_text(encoding="utf-8"))
    if "_provenance" not in d:
        pytest.skip(f"{name} carries no _provenance block (a REFUSED/SKIPPED/ERROR "
                    "short-circuit writes before any input is opened)")
    # `N3_populate_observe_tier.json` is, by design, a pure documentation/
    # refusal receipt: it names WHY live population was not attempted and
    # opens no local file at all, so `_inputs_opened` is legitimately empty.
    require_inputs = name != "N3_populate_observe_tier.json"
    findings = RP.check_receipt(d, require_inputs=require_inputs, verify_hashes=False)
    hard = RP.hard_failures(findings)
    assert not hard, f"{name}: {hard}"
