"""N6.1's new world and N7's bookkeeping, tested without fitting anything.

Both files have the same failure mode and it is not a wrong number: it is a
RIGHT number that never arrives. A world whose planted alpha also moves the
market passes its own test for the wrong reason; a receipt whose keys the
memory does not recognise folds to zero rows and is later read as "tested,
found nothing". Neither shows up as a crash, so both are pinned here.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts import n6_battery_v2 as B2
from scripts import n7_memory_and_leaderboard as N7


# ------------------------------------------------------------- the event world

class _Cfg:
    alpha_scale = 0.012


def _null_panel(n_months: int = 24, n_names: int = 100, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_months):
        m = f"{2010 + i // 12:04d}-{i % 12 + 1:02d}"
        mkt = float(rng.normal(0.006, 0.04))
        r = mkt + rng.normal(0, 0.06, n_names)
        rows.append(pd.DataFrame({
            "month": m, "permno": np.arange(n_names) + 90_000,
            "net_rev_4w": rng.normal(size=n_names),
            "market_cap": rng.lognormal(21.0, 1.2, n_names),
            "fwd_1m": r, "mkt_vw_1m": mkt,
            "excess_vw_1m": r - mkt, "excess_ew_1m": r - r.mean(),
            "resid_vw_1m": r - mkt, "resid_ew_1m": r - r.mean(),
            "pos_vw_1m": (r - mkt > 0).astype(float),
            "__true_alpha": 0.0,
        }))
    return pd.concat(rows, ignore_index=True)


def test_the_event_alpha_is_demeaned_so_the_equal_weighted_market_is_unmoved():
    df = _null_panel()
    before = df.groupby("month")["excess_ew_1m"].mean()
    out, meta = B2.plant_event(df, _Cfg())
    after = out.groupby("month")["excess_ew_1m"].mean()
    assert np.allclose(before.to_numpy(), after.to_numpy(), atol=1e-12)
    assert meta["ew_market_leg_shift"] == 0.0
    # The VW leg CAN move, and the receipt must say by how much rather than
    # claim it did not.
    assert meta["vw_market_leg_shift_bps_max"] is not None


def test_the_event_edge_sits_on_a_tenth_of_the_rows_and_nowhere_else():
    df = _null_panel()
    out, meta = B2.plant_event(df, _Cfg())
    share = float((out["__true_alpha"] > 0).mean())
    assert share == pytest.approx(0.10, abs=0.02)
    assert meta["share_of_rows_carrying_the_edge"] == pytest.approx(0.10)
    # The rows that do not carry the event still moved -- by the DEMEANING, not
    # by an edge. Their alpha is negative and identical inside a month, which
    # is what makes the month's mean zero.
    neg = out.loc[out["__true_alpha"] <= 0].groupby("month")["__true_alpha"].nunique()
    assert (neg == 1).all()


def test_planting_the_event_does_not_touch_the_carrier_or_the_features():
    df = _null_panel()
    out, _ = B2.plant_event(df, _Cfg())
    assert np.allclose(df["net_rev_4w"].to_numpy(), out["net_rev_4w"].to_numpy())
    assert np.allclose(df["market_cap"].to_numpy(), out["market_cap"].to_numpy())


def test_planting_refuses_a_carrier_that_is_not_on_the_panel():
    with pytest.raises(SystemExit) as e:
        B2.plant_event(_null_panel(), _Cfg(), carrier="a_column_nobody_built")
    assert "REFUSED" in str(e.value)


def test_the_planted_event_is_actually_recoverable_by_a_ranker_that_can_see_it():
    """A planted world nobody could recover would make the battery vacuous."""
    df = _null_panel(n_months=60, n_names=150)
    out, _ = B2.plant_event(df, _Cfg())
    top = out.groupby("month", group_keys=False).apply(
        lambda g: g.nlargest(max(2, len(g) // 10), "net_rev_4w"), include_groups=False)
    assert float(top["excess_vw_1m"].mean()) > float(out["excess_vw_1m"].mean())


# ------------------------------------------------------------- adjudication

def _world(t_value, planted=True):
    return {"cells": {"lgbm_clf": {"books": {
        "broad_top40pct_ew_hysteresis": {"t_paired_vs_market": t_value}}}}}


def test_a_planted_world_that_is_missed_is_a_FAIL_and_says_machine_defect():
    a = B2.adjudicate({"linear": _world(0.4)})
    assert a["per_world"]["linear"]["verdict"].startswith("FAIL")
    assert "machine defect" in a["per_world"]["linear"]["verdict"]
    assert a["ALL_PASS"] is False


def test_a_null_world_that_fires_is_a_FAIL_too():
    a = B2.adjudicate({"null": _world(3.1)})
    assert a["per_world"]["null"]["verdict"].startswith("FAIL")


def test_all_pass_requires_every_world_including_the_null():
    a = B2.adjudicate({"linear": _world(4.0), "null": _world(0.2)})
    assert a["ALL_PASS"] is True
    assert a["n_pass"] == 2


def test_the_ladder_descends_from_the_reference_scale():
    assert B2.LADDER[0] == 1.0
    assert list(B2.LADDER) == sorted(B2.LADDER, reverse=True)


# ------------------------------------------------------------------- N7

def _night_receipt() -> dict:
    return {
        "job": "N1_construction_books",
        "cells": {
            "good": {"beta": 1.1, "months": 300,
                     "terminal_wealth_net": 20.0,
                     "terminal_wealth_market_same_months": 13.0,
                     "PRIMARY_beta_matched": {"annualised_pct": 5.0, "t_paired": 2.4,
                                              "p_one_sided": 0.008},
                     "era_table_on_the_beta_matched_excess": {"holds_in_2_of_3": True},
                     "fundamental_law": {"transfer_coefficient": {"tc": 0.46},
                                         "effective_breadth": {
                                             "mean_effective_names_per_month": 100.0}}},
            "rich_but_random": {"beta": 1.9, "months": 300,
                                "terminal_wealth_net": 900.0,
                                "terminal_wealth_market_same_months": 13.0,
                                "PRIMARY_beta_matched": {"annualised_pct": 0.4,
                                                         "t_paired": 0.1,
                                                         "p_one_sided": 0.46}},
            "no_t_at_all": {"beta": 1.0, "months": 4},
        },
        "family": {"size": 160, "family_min_p": 0.0049,
                   "best_cell": "good", "best_cell_holm_adjusted_p": 0.79,
                   "cells_surviving_holm_at_0.05": []},
        "inference_on_the_best_cell": {"deflated_sharpe": {"dsr": 0.45}},
        "verdict_on_the_best_cell": "NOISE",
    }


def test_normalise_maps_the_nights_own_key_names_and_loses_nothing():
    """`family.best_cell`, `inference_on_the_best_cell` and
    `verdict_on_the_best_cell` are this night's names. An unmapped key is a
    result that never reaches the memory."""
    n = N7.normalise(_night_receipt(), __import__("pathlib").Path("x.json"))
    assert n["family_id"].endswith("N1_construction_books")
    assert n["best_cell"] == "good"
    assert n["verdict"] == "NOISE"
    assert n["inference"]["deflated_sharpe"]["dsr"] == 0.45
    assert n["era_sign_table"] == {"holds_in_2_of_3": True}
    assert set(n["cells"]) == {"good", "rich_but_random", "no_t_at_all"}


def test_a_receipt_that_uses_B1s_key_names_is_still_a_receipt():
    """B1 and the N6b jobs write `item` + `title`, not `job`. The first version
    of the guard demanded `job` and dropped four real receipts as "not a
    receipt" -- the same failure `record_receipt` was fixed for last weekend,
    reintroduced one layer up."""
    from pathlib import Path
    assert N7._identifies_a_receipt({"item": "N6b", "title": "x", "licence": "P"})
    assert N7._identifies_a_receipt({"licence": "PRODUCT_EXPERIMENT"})
    assert not N7._identifies_a_receipt({"rows": 3, "written_utc": "z"})
    n = N7.normalise({"item": "N6b_path_monte_carlo", "licence": "P"},
                     Path("N6b_path_monte_carlo.json"))
    assert n["family_id"].endswith("N6b_path_monte_carlo")


def test_a_skipped_or_refused_receipt_is_recorded_as_such_not_dropped():
    for st in ("SKIPPED", "REFUSED", "FAILED"):
        n = N7.normalise({"job": "J", "status": st, "headline": "because"},
                         __import__("pathlib").Path("x.json"))
        assert n["verdict"].startswith(st)
        assert n["cells"] == {}


def test_the_board_is_ranked_on_the_beta_matched_t_and_not_on_terminal_wealth():
    """THE test. `rich_but_random` has 45x the terminal wealth and no t. A
    leaderboard sorted on wealth is a leaderboard sorted on beta."""
    n = N7.normalise(_night_receipt(), __import__("pathlib").Path("x.json"))
    rows = N7.leaderboard_rows([n])
    assert {r["cell"] for r in rows} == {"good", "rich_but_random"}
    md = N7.render(rows, {n["family_id"]: {"size": 160, "family_min_p": 0.0049,
                                           "best_cell_holm_adjusted_p": 0.79,
                                           "cells_surviving_holm_at_0.05": []}},
                   "2026-09-07T00:00:00Z")
    head = md.split("## Every cell")[0]
    assert "BEST SO FAR" in head
    assert "`good`" in head and "rich_but_random" not in head
    assert "beta 1.1" in head            # beta printed FIRST
    assert "family size **160**" in head
    assert "Holm-adjusted **0.79**" in head


def test_a_cell_without_a_t_never_reaches_the_board():
    n = N7.normalise(_night_receipt(), __import__("pathlib").Path("x.json"))
    rows = N7.leaderboard_rows([n])
    assert "no_t_at_all" not in {r["cell"] for r in rows}


def test_an_empty_night_says_so_instead_of_rendering_a_champion():
    md = N7.render([], {}, "2026-09-07T00:00:00Z")
    assert "no cell in this night's receipts" in md


def test_the_job_does_not_fold_its_own_output_back_into_the_memory():
    assert "N7_memory_and_leaderboard.json" in N7.SELF
    assert "best_so_far.json" in N7.SELF


def test_scratch_receipts_are_skipped_because_they_share_the_real_jobs_name(tmp_path,
                                                                            monkeypatch):
    """`_n5_states_quick_test.json` carries `job: N5_states_third_null`, the same
    name as the real receipt. Folding both records the family twice with two
    disagreeing sample sizes and no way to tell which was the run."""
    monkeypatch.setattr(N7, "OUT_DIR", tmp_path)
    monkeypatch.setattr(N7, "LEADERBOARD", tmp_path / "LEADERBOARD.md")
    monkeypatch.setattr(N7, "BEST", tmp_path / "best_so_far.json")
    (tmp_path / "N9_real.json").write_text(
        json.dumps({"job": "N9", "status": "SKIPPED", "headline": "nothing here"}),
        encoding="utf-8")
    (tmp_path / "_N9_quick_test.json").write_text(
        json.dumps({"job": "N9", "status": "SKIPPED", "headline": "scratch"}),
        encoding="utf-8")
    rec = N7.run(to_registry=False, verbose=False)
    assert rec["receipts_read"] == ["N9_real.json"]
    assert rec["receipts_ignored_as_scratch"] == ["_N9_quick_test.json"]
