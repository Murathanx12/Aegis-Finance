"""strategy_library_ext: the discovery rows, their claimed numbers, and the loader's refusal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.services import strategy_library as sl
from backend.services import strategy_library_ext as ext


def test_every_entry_has_the_required_keys():
    assert ext.EXTRA_STRATEGIES, "the extension list is empty"
    for r in ext.EXTRA_STRATEGIES:
        m = r.meta()
        for k in ext.REQUIRED_KEYS:
            assert k in m, (r.id, k)
        assert m["family"] and m["economic_reason"] and m["source"], r.id
        assert m["first_registered_utc"], r.id


def test_discovery_rows_carry_a_claimed_number():
    disc = [r for r in ext.EXTRA_STRATEGIES if r.source.startswith("discovery:")]
    assert len(disc) >= 15
    assert all(r in ext.DISCOVERY_STRATEGIES for r in disc)
    for r in disc:
        m = r.meta()
        for k in ext.DISCOVERY_KEYS:
            assert m.get(k), (r.id, k)
        assert m["first_registered_utc"] == ext.REGISTERED_DISCOVERY
        assert "http" in m["source"] or "quantpedia" in m["source"], r.id
        # the claim reaches the leaderboard row, which prints literature_reported
        assert m["claimed_number"] in m["literature_reported"]
    for row in ext.EXT_COVERED_BY + ext.EXT_NOT_REACHABLE:
        assert row["id"] and row["source"] and row["claimed_number"] and row["why"], row
    assert all(row["missing_column"] for row in ext.EXT_NOT_REACHABLE)


def test_no_discovery_row_is_filed_twice():
    ids = [r.discovery_id for r in ext.DISCOVERY_STRATEGIES]
    ids += [row["id"] for row in ext.EXT_COVERED_BY + ext.EXT_NOT_REACHABLE]
    assert len(ids) == len(set(ids))


def test_every_extension_rule_was_registered_by_the_loader():
    ours = {r.id for r in ext.EXTRA_STRATEGIES}
    assert sl.EXTRA_SOURCE.startswith("backend.services.strategy_library_ext")
    assert not (set(sl.EXTRA_REFUSED) & ours), sl.EXTRA_REFUSED
    assert ours <= {r.id for r in sl.RULES}


def test_covered_rows_point_at_real_rules():
    ids = {r.id for r in sl.RULES}
    for row in ext.EXT_COVERED_BY:
        assert row["base_rule"] in ids, row


def test_loader_refuses_a_threshold_only_duplicate_of_a_base_rule(monkeypatch):
    """EXT-QC-12 as literally built (5 lowest 252d-vol large caps) IS lowvol_252_large."""
    base = sl.rule_by_id("lowvol_252_large")
    twin = ext.DiscoveryStrategy(
        "qc310_lowvol_5_large", "low_risk", "5 lowest 252d vol, large band",
        sl.col("vol_252", -1), universe_rule="large", k=5, source="discovery:EXT-QC-12 test",
        claimed_number="5Y CAGR 9.8%", economic_reason="x")
    assert twin.signature() == base.signature()
    good = ext.DISCOVERY_STRATEGIES[0]
    base_rules = [r for r in sl.RULES if r.id not in {x.id for x in ext.EXTRA_STRATEGIES}]
    monkeypatch.setattr(sl, "RULES", list(base_rules))
    monkeypatch.setattr(sl, "EXTRA_REFUSED", {})
    monkeypatch.setattr(sl, "EXTRA_SOURCE", sl.EXTRA_SOURCE)
    monkeypatch.setattr(ext, "EXTRA_STRATEGIES", [twin, good])
    sl._load_extra()
    assert "qc310_lowvol_5_large" in sl.EXTRA_REFUSED
    assert "ThresholdVariant" in sl.EXTRA_REFUSED["qc310_lowvol_5_large"]
    assert "lowvol_252_large" in sl.EXTRA_REFUSED["qc310_lowvol_5_large"]
    ids = [r.id for r in sl.RULES]
    assert good.id in ids and "qc310_lowvol_5_large" not in ids
    assert sl.RULES[-1].control                       # controls stay last


def test_derived_columns_are_functions_of_panel_columns():
    p = pd.DataFrame({"mom_252": [0.2, 0.1], "vol_252": [0.4, 0.0],
                      "mkt_stress": [1.0, np.nan],
                      "px_vs_52w_high": [-0.02, -0.5], "px_vs_52w_low": [0.5, 0.0]})
    out = ext.derive_columns(p)
    assert out.loc[0, "sharpe_252"] == pytest.approx(0.5)
    assert np.isnan(out.loc[1, "sharpe_252"])              # zero vol is NaN, not inf
    assert out.loc[0, "mkt_not_stress"] == 0.0 and np.isnan(out.loc[1, "mkt_not_stress"])
    assert out.loc[0, "low_vs_high_252"] == pytest.approx(0.98 / 1.5 - 1.0)
    assert list(p.columns) == ["mom_252", "vol_252", "mkt_stress", "px_vs_52w_high", "px_vs_52w_low"]


def test_discovery_rules_score_on_a_panel_with_their_columns():
    rng = np.random.default_rng(7)
    n = 40
    cols = {c for r in ext.DISCOVERY_STRATEGIES for c in r.requires} - set(ext.DERIVED_COLUMNS)
    cols |= {"mom_252", "vol_252", "mkt_stress", "px_vs_52w_high", "px_vs_52w_low"}
    p = pd.DataFrame({c: rng.normal(size=n) for c in cols})
    p["vol_252"] = np.abs(p["vol_252"]) + 0.1
    p["px_vs_52w_low"] = np.abs(p["px_vs_52w_low"])
    p["px_vs_52w_high"] = -np.abs(p["px_vs_52w_high"]) / 10
    p["gsector"] = rng.integers(0, 4, size=n)
    p["date"] = pd.Timestamp("2024-01-31")
    p["symbol"] = [f"S{i}" for i in range(n)]
    p = ext.derive_columns(p)
    for r in ext.DISCOVERY_STRATEGIES:
        s = r.signal(p)
        assert len(s) == n, r.id
