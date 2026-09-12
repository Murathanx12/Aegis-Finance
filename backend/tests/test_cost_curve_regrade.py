"""5c T4 -- the migration: a no-op re-grade reproduces the archived net exactly.

The one test the spec singles out (S4 item 5) is here: run an archived receipt
through the SAME pipeline with the target curve set back to `flat` and the
number must come out unchanged. It is not a tolerance check -- the adjustment
factor is `((1-c)/(1-c))**n`, which is 1.0 in IEEE arithmetic, so any
difference at all means the pipeline is doing something to the number besides
substituting a rate.

No parquet is read here: the cross-section is a two-element fixture, because
what is under test is the arithmetic and the refusals, not the fit.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts import cost_curve_regrade as RG

SPREADS = np.array([2.0, 4.0, 8.0])
DVS = np.array([1e9, 1e8, 5e6])


def _entry(**node):
    base = {"terminal_wealth_net": 12.8267, "mean_turnover": 0.692,
            "months": 107, "cost_bps_per_side": 25.0}
    base.update(node)
    return {"path": "/x", "node": base, "inherited": {}, "family": "/"}


def test_a_no_op_regrade_reproduces_the_archived_net_TO_THE_CENT():
    """SPEC S4 ITEM 5."""
    e = _entry()
    row = RG.regrade_node(e, SPREADS, DVS, target_curve="flat")
    assert row["regraded"] is True
    assert row["terminal_wealth_net_curve"] == row["terminal_wealth_net_archived"]
    assert row["delta_tw_ratio"] == 1.0
    assert row["delta_cagr_pp"] == 0.0


def test_the_real_regrade_moves_the_level_and_says_by_how_much():
    row = RG.regrade_node(_entry(), SPREADS, DVS)
    assert row["cost_bps_one_way_curve"] < row["cost_bps_per_side_flat"]
    assert row["terminal_wealth_net_curve"] > row["terminal_wealth_net_archived"]
    assert row["delta_cagr_pp"] > 0
    # The substitution is on the SAME turnover: the monthly costs differ by
    # exactly the rate ratio, nothing else.
    assert (row["monthly_cost_curve"] / row["monthly_cost_flat"]
            == pytest.approx(row["cost_bps_one_way_curve"]
                             / row["cost_bps_per_side_flat"], rel=1e-3))


def test_a_node_with_no_turnover_on_disk_is_REFUSED_BY_NAME():
    e = _entry()
    del e["node"]["mean_turnover"]
    row = RG.regrade_node(e, SPREADS, DVS)
    assert row["refused"] is True
    assert any("turnover" in m for m in row["refused_for"])
    assert "terminal_wealth_net_curve" not in row


def test_a_node_with_no_identifiable_cost_rate_is_REFUSED_BY_NAME():
    e = _entry()
    del e["node"]["cost_bps_per_side"]
    row = RG.regrade_node(e, SPREADS, DVS)
    assert row["refused"] is True
    assert any("cost rate" in m for m in row["refused_for"])


def test_an_inherited_cost_rate_is_used_and_RECORDED():
    e = _entry()
    del e["node"]["cost_bps_per_side"]
    e["inherited"] = {"cost_bps": 25.0, "cost_bps_from": "/search_space/cost_bps"}
    row = RG.regrade_node(e, SPREADS, DVS)
    assert row["regraded"] is True
    assert row["cost_bps_source"] == "/search_space/cost_bps"


def test_the_execution_floor_selects_which_names_the_rate_represents():
    lo = RG.representative_bps(SPREADS, DVS, None)
    hi = RG.representative_bps(SPREADS, DVS, 1e8)
    assert hi < lo, "a higher liquidity floor must not imply a wider spread"


def test_a_family_is_the_deepest_container_with_SIBLINGS():
    """The first version grouped by the immediate parent, which made every
    book a family of one and reported 'no ranking changed' because there were
    no rankings -- a check that cannot fail is not a check."""
    rows = [{"path": "/scoreboards/1m/a/book"}, {"path": "/scoreboards/1m/b/book"},
            {"path": "/top10[0]"}, {"path": "/top10[1]"}]
    RG.assign_families(rows)
    assert rows[0]["family"] == "/scoreboards/1m"
    assert rows[1]["family"] == "/scoreboards/1m"
    assert rows[2]["family"] == "/top10"


def test_ranking_change_is_COMPUTED_not_assumed():
    rows = [
        {"path": "/f/a", "family": "/f", "regraded": True,
         "terminal_wealth_net_archived": 2.0, "terminal_wealth_net_curve": 2.1},
        {"path": "/f/b", "family": "/f", "regraded": True,
         "terminal_wealth_net_archived": 1.9, "terminal_wealth_net_curve": 2.3},
    ]
    out = RG.family_rankings(rows)
    assert out[0]["ranking_unchanged"] is False
    assert out[0]["n_discordant_pairs"] == 1
    assert out[0]["kendall_tau"] == -1.0


# ------------------------------------------------------------ the artefacts

def _summaries():
    d = (Path(__file__).resolve().parents[1] / "data" / "optimus" / "cost_curve")
    return sorted(d.glob("regrade_summary_*.json"))


def test_the_migration_ran_and_NOTHING_WAS_OVERWRITTEN():
    found = _summaries()
    assert found, "run `python -m scripts.cost_curve_regrade`"
    blob = json.loads(found[-1].read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[2]
    assert blob["n_receipts_regraded"] > 0
    for f in blob["files"]:
        src, out = root / f["source"], root / f["regrade"]
        assert src.exists(), f["source"]
        assert out.exists(), f["regrade"]
        assert src != out, "a re-grade must never be written over its source"
        assert out.name.endswith(RG.SUFFIX)
        # The source is still the source: it carries no re-grade fields.
        assert "terminal_wealth_net_curve" not in src.read_text(encoding="utf-8")


def test_the_summary_counts_the_refusals_BY_NAME():
    blob = json.loads(_summaries()[-1].read_text(encoding="utf-8"))
    assert blob["n_refused_unidentifiable"] > 0
    assert len(blob["refused_by_name"]) == blob["n_refused_unidentifiable"]
    assert all(":" in r for r in blob["refused_by_name"])
