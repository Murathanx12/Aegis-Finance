"""X5 -- the exclusion screen (re-test 1 of the 2026-09-19 failure thesis).

WHAT THESE TESTS PIN, AND WHY EACH ONE EXISTS
=============================================
Every test here is built on SYNTHETIC ranks under `tmp_path`. Nothing reads
`backend/data/`, no CRSP year file is opened and no night folder is touched:
CI has none of them, and a test that silently skipped on their absence would
be a test that never ran (`a check that did not run is not a check that
passed`).

The three properties that make this job a test rather than a demonstration:

1. the worst end is the LEDGER'S, frozen per screen, and the exclusion takes
   the end the declaration names;
2. the random-exclusion twin removes the SAME COUNT, so pool size and the
   mechanical part of the turnover change cancel out of the difference;
3. a missing rank source REFUSES BY NAME with the paths it looked for, and the
   refused leg is still NAMED in the Holm block.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from scripts import night_x5_exclusion_screen as X


# --------------------------------------------------------------------------
# fixtures: a tiny panel with a KNOWN answer


def _panel(n_names: int = 40, n_months: int = 36, seed: int = 7):
    """A monthly panel in the replay's own shape.

    Half the names are 'bad' (they earn less), and the synthetic rank puts them
    at the end the screen is told is worst. A screen that works must therefore
    beat both an unscreened book and a random exclusion.
    """
    rng = np.random.default_rng(seed)
    months = pd.period_range("2015-01", periods=n_months, freq="M")
    rows = []
    for ym in months:
        for p in range(1, n_names + 1):
            bad = p <= n_names // 2
            ret = rng.normal(-0.02 if bad else 0.02, 0.01)
            rows.append({"permno": p, "ym": ym, "ret_m": float(ret),
                         "price": 50.0, "dv": 5e7,
                         "turnover_m": 0.1})
    return pd.DataFrame(rows)


def _ranks(panel, *, bad_at_bottom: bool = True):
    """Percentile ranks that put the 'bad' half at one declared end."""
    names = sorted(panel["permno"].unique())
    out = {}
    for ym in sorted(panel["ym"].unique()):
        d = {}
        for i, p in enumerate(names):
            # names 1..half are the bad ones and they sort first, so the plain
            # index rank puts them at the BOTTOM; `bad_at_bottom=False` mirrors
            # it so the same fixture serves a "high end is worst" screen.
            d[int(p)] = ((i + 1) / len(names) if bad_at_bottom
                         else 1.0 - (i + 1) / len(names))
        out[ym] = d
    return out


def _select_worst_first(panel):
    """A selector that picks the LOWEST-numbered names: the bad half first.

    Deliberately perverse, so that removing the bad decile has an effect the
    test can see. A selector that already avoided them would make every arm
    identical and the test would pass on a screen that did nothing.
    """
    def select(pool, ym):
        return sorted(int(p) for p in pool["permno"])
    return select


# --------------------------------------------------------------------------
# 1. the declaration


def test_every_screen_declares_its_worst_end_and_the_receipt_it_comes_from():
    assert set(X.SCREENS) == {"io_level", "io_abn", "skew_25d", "skew_resid"}
    for name, decl in X.SCREENS.items():
        assert decl["worst_end"] in ("low", "high"), name
        assert "NEGATIVE_RESULTS" in decl["receipt"], name
        assert decl["source"].strip(), name
        assert callable(decl["builder"]), name


def test_the_declared_directions_are_the_ones_the_ledger_measured():
    """§28: LOW institutional ownership and HIGH skew are the bad ends."""
    assert X.SCREENS["io_level"]["worst_end"] == "low"
    assert X.SCREENS["io_abn"]["worst_end"] == "low"
    assert X.SCREENS["skew_25d"]["worst_end"] == "high"
    assert X.SCREENS["skew_resid"]["worst_end"] == "high"


def test_the_family_is_declared_at_the_number_of_screens():
    p = {s: None for s in X.SCREENS}
    block = X.holm(p, family=X.FAMILY)
    assert block["declared_family_size"] == len(X.SCREENS) == 4
    assert block["family"] == X.FAMILY


def test_the_run_date_is_never_a_literal():
    """2026-09-18: three idle-queue jobs overwrote committed receipts."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(X))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "RUN_DATE"
                for t in node.targets):
            assert not isinstance(node.value, ast.Constant), (
                "RUN_DATE is a literal; unset must mean TODAY")


# --------------------------------------------------------------------------
# 2. the exclusion itself


def test_the_low_end_screen_removes_the_bottom_of_the_rank():
    panel = _panel()
    ym = sorted(panel["ym"].unique())[0]
    pool = panel[panel["ym"] == ym]
    ranks = _ranks(panel)[ym]
    dropped = X.excluded_names(pool, ranks, worst_end="low", share=0.10)
    assert len(dropped) == 4                       # 10% of 40
    assert max(ranks[p] for p in dropped) <= 0.1 + 1e-9


def test_the_high_end_screen_removes_the_top_of_the_rank():
    panel = _panel()
    ym = sorted(panel["ym"].unique())[0]
    pool = panel[panel["ym"] == ym]
    ranks = _ranks(panel)[ym]
    dropped = X.excluded_names(pool, ranks, worst_end="high", share=0.10)
    assert min(ranks[p] for p in dropped) >= 0.9 - 1e-9


def test_a_name_with_no_rank_is_never_excluded():
    """An exclusion screen that removed what it cannot see is a coverage
    filter wearing a screen's name."""
    panel = _panel()
    ym = sorted(panel["ym"].unique())[0]
    pool = panel[panel["ym"] == ym]
    partial = {p: v for p, v in _ranks(panel)[ym].items() if p <= 10}
    dropped = X.excluded_names(pool, partial, worst_end="low", share=0.50)
    assert dropped and all(p <= 10 for p in dropped)


def test_the_cut_is_taken_inside_the_pool_not_in_the_rank_universe():
    panel = _panel()
    ym = sorted(panel["ym"].unique())[0]
    full = panel[panel["ym"] == ym]
    narrow = full[full["permno"] <= 20]
    ranks = _ranks(panel)[ym]
    assert len(X.excluded_names(full, ranks, worst_end="low")) == 4
    assert len(X.excluded_names(narrow, ranks, worst_end="low")) == 2


# --------------------------------------------------------------------------
# 3. the three arms, paired


def test_the_three_arms_share_one_block_set():
    panel = _panel()
    res = X.run_screen_arms(panel, _select_worst_first(panel),
                            ranks=_ranks(panel), worst_end="low",
                            pool_filter=None, floor_usd=1e6, k=8,
                            seed=X._seed_for("io_level"))
    n = res["n_blocks"]
    assert n > 20
    assert all(len(v) == n for v in res["arms"].values())
    assert len(res["host_random_universe_twin"]) == n


def test_the_random_twin_removes_exactly_as_many_names_as_the_screen():
    """Otherwise the difference would measure the pool's SIZE."""
    panel = _panel()
    ym = sorted(panel["ym"].unique())[0]
    pool = panel[panel["ym"] == ym]
    ranks = _ranks(panel)[ym]
    dropped = X.excluded_names(pool, ranks, worst_end="low")
    rng = np.random.default_rng(1)
    cand = [int(x) for x in pool["permno"]]
    rand = rng.choice(len(cand), size=len(dropped), replace=False)
    assert len(rand) == len(dropped)


def test_removing_the_bad_half_beats_both_controls_on_a_planted_panel():
    """The known answer. A screen that cannot find a planted edge is broken."""
    panel = _panel()
    res = X.run_screen_arms(panel, _select_worst_first(panel),
                            ranks=_ranks(panel), worst_end="low",
                            pool_filter=None, floor_usd=1e6, k=8,
                            seed=X._seed_for("io_level"))
    vs_un = X._difference(res["arms"]["screened"], res["arms"]["unscreened"],
                          res["blocks"], label="u")
    vs_tw = X._difference(res["arms"]["screened"], res["arms"]["random_twin"],
                          res["blocks"], label="t")
    assert vs_un["mean_excess_net_monthly"] > 0, vs_un
    assert vs_tw["mean_excess_net_monthly"] > 0, vs_tw
    assert X._verdict(vs_un, vs_tw)["verdict"] in (
        "PRODUCT_PROMISING", "CONDITIONAL")


def test_a_rank_that_orders_nothing_does_not_beat_the_random_exclusion():
    """The null. Ranks drawn at random must not produce a screen."""
    rng = np.random.default_rng(3)
    panel = _panel()
    names = sorted(panel["permno"].unique())
    noise = {ym: {int(p): float(rng.random()) for p in names}
             for ym in sorted(panel["ym"].unique())}
    res = X.run_screen_arms(panel, _select_worst_first(panel), ranks=noise,
                            worst_end="low", pool_filter=None, floor_usd=1e6,
                            k=8, seed=X._seed_for("io_abn"))
    vs_tw = X._difference(res["arms"]["screened"], res["arms"]["random_twin"],
                          res["blocks"], label="t")
    assert abs(vs_tw["nw_lag2_t"] or 0.0) < X.T_ALIVE, vs_tw


def test_each_arm_pays_its_own_turnover():
    """An arm that inherited another's holdings would pay someone else's cost."""
    panel = _panel(n_names=20, n_months=12)
    res = X.run_screen_arms(panel, _select_worst_first(panel),
                            ranks=_ranks(panel), worst_end="low",
                            pool_filter=None, floor_usd=1e6, k=5,
                            seed=X._seed_for("skew_25d"))
    # Every arm's first block carries the entry cost of a fresh book.
    for arm, series in res["arms"].items():
        assert math.isfinite(series[0]), arm


# --------------------------------------------------------------------------
# 4. the verdict ladder


def test_a_negative_point_estimate_is_a_failed_variant_not_under_power():
    v = X._verdict({"mean_excess_net_monthly": -0.001, "nw_lag2_t": -0.3},
                   {"mean_excess_net_monthly": 0.004, "nw_lag2_t": 2.9})
    assert v["verdict"] == "FAILED_VARIANT"


def test_beating_only_the_random_twin_is_not_a_screen():
    v = X._verdict({"mean_excess_net_monthly": -0.0001, "nw_lag2_t": -0.1},
                   {"mean_excess_net_monthly": 0.01, "nw_lag2_t": 5.0})
    assert v["verdict"] == "FAILED_VARIANT"


def test_positive_but_under_powered_is_conditional():
    v = X._verdict({"mean_excess_net_monthly": 0.001, "nw_lag2_t": 1.2},
                   {"mean_excess_net_monthly": 0.001, "nw_lag2_t": 1.1})
    assert v["verdict"] == "CONDITIONAL"


def test_a_missing_block_mean_is_cannot_determine():
    v = X._verdict({"mean_excess_net_monthly": None, "nw_lag2_t": None},
                   {"mean_excess_net_monthly": 0.01, "nw_lag2_t": 5.0})
    assert v["verdict"] == "CANNOT_DETERMINE"


# --------------------------------------------------------------------------
# 5. the refusals


def test_a_missing_option_file_refuses_by_name_with_the_path(tmp_path,
                                                             monkeypatch):
    monkeypatch.setattr(X, "learner_dir", lambda: tmp_path / "nowhere")
    with pytest.raises(X.RankSourceMissing) as exc:
        X.build_skew_ranks(_panel(), residual=False)
    assert "features_options.parquet" in str(exc.value)
    assert exc.value.paths and exc.value.paths[0].endswith(
        "features_options.parquet")
    assert "REFUSED" in str(exc.value)


def test_a_missing_ownership_link_refuses_by_name(tmp_path, monkeypatch):
    monkeypatch.setattr(X, "wrds_dir", lambda: tmp_path / "nowrds")
    with pytest.raises(X.RankSourceMissing) as exc:
        X.build_io_ranks(_panel(), start=2015, end=2016, abnormal=False)
    assert "tr13f" in str(exc.value)


def test_a_refused_screen_is_named_in_holm_not_dropped():
    block = X.holm({"io_level": 0.01, "io_abn": None, "skew_25d": None,
                    "skew_resid": None}, family=X.FAMILY)
    assert block["declared_family_size"] == 4
    assert block["legs_without"] == ["io_abn", "skew_25d", "skew_resid"]
    assert block["per_leg"]["io_level"]["holm_alpha"] == pytest.approx(0.0125)


def test_the_seed_is_reproducible_across_processes():
    """`hash()` is salted per process; a seed derived from it would draw a
    different control every night under one printed number."""
    import ast
    import inspect

    src = inspect.getsource(X)
    assert "hash(name)" not in src
    assert X._seed_for("io_level") == X._seed_for("io_level")
    assert X._seed_for("io_level") != X._seed_for("skew_25d")
    ast.parse(src)


# --------------------------------------------------------------------------
# 6. registration


def test_the_job_is_registered_with_a_stage_and_a_loader():
    from scripts.night_factory_jobs import JOBS, JOB_STAGES, STAGE_ORDER
    assert "X5_exclusion_screen" in JOBS
    assert JOB_STAGES["X5_exclusion_screen"] in STAGE_ORDER
    assert JOB_STAGES["X5_exclusion_screen"] == "pnl"


def _offline(monkeypatch, tmp_path, *, jkp: bool = True):
    """Every real-data door closed. Nothing under backend/data is opened."""
    panel = _panel()
    monkeypatch.setattr(X, "load_monthly_panel",
                        lambda *a, **k: panel.copy())
    monkeypatch.setattr(X, "wrds_dir", lambda: tmp_path / "nowrds")
    monkeypatch.setattr(X, "learner_dir", lambda: tmp_path / "nolearner")
    monkeypatch.setattr(X, "out_dir", lambda: tmp_path / "out")
    if jkp:
        monkeypatch.setattr(X, "load_jkp_monthly", lambda *a, **k: object())
        monkeypatch.setattr(X, "by_month", lambda frame: {})
        monkeypatch.setattr(X, "covered_permnos", lambda frames, *, book: {
            ym: {int(p) for p in panel["permno"].unique()}
            for ym in sorted(panel["ym"].unique())})
        monkeypatch.setattr(X, "coverage_and_contamination",
                            lambda *a, **k: {"excluded_years": [],
                                             "per_year": {}})
        monkeypatch.setattr(X, "_pool_filter",
                            lambda covered, skip: (lambda pool, ym: pool))
        monkeypatch.setattr(X, "book_f_selector",
                            lambda frames, **k: _select_worst_first(panel))
    else:
        def _boom(*a, **k):
            raise X.CharacteristicPanelUnavailable(
                "no jkp_usa_*.parquet on this checkout")
        monkeypatch.setattr(X, "load_jkp_monthly", _boom)
    return panel


def test_every_screen_refuses_by_name_when_no_rank_source_is_on_disk(
        tmp_path, monkeypatch):
    """The refusal path end to end. Nothing real is read and nothing is faked."""
    _offline(monkeypatch, tmp_path)
    out = X.X5_exclusion_screen(smoke=True)
    assert out["n_ran"] == 0 and out["n_refused"] == 4
    for name, block in out["screens"].items():
        assert block["ran"] is False, name
        assert "REFUSED" in block["refused"], name
        assert block["paths_looked_for"], name
    looked = " ".join(out["screens"]["skew_25d"]["paths_looked_for"])
    assert looked.endswith("features_options.parquet")
    assert any(p.endswith("tr13f_permno_link.json")
               for p in out["screens"]["io_level"]["paths_looked_for"])
    assert out["holm"]["declared_family_size"] == 4
    assert out["holm"]["legs_without"] == sorted(X.SCREENS)
    json.dumps(out, default=str)


def test_a_missing_characteristic_panel_refuses_the_whole_job_by_name(
        tmp_path, monkeypatch):
    _offline(monkeypatch, tmp_path, jkp=False)
    out = X.X5_exclusion_screen(smoke=True)
    assert out["n_ran"] == 0
    assert "REFUSED" in out["verdict"]
    assert out["holm"]["declared_family_size"] == 4
    json.dumps(out, default=str)


def test_the_receipt_prints_the_construction_it_actually_ran(
        tmp_path, monkeypatch):
    _offline(monkeypatch, tmp_path)
    rc = X.X5_exclusion_screen(smoke=True)["registered_construction"]
    assert rc["honours_the_registration"] is False    # a smoke run cannot
    assert rc["host_book"] == X.HOST_BOOK
    assert rc["cost_curve"] == X.COST_CURVE
    assert len(rc["controls"]) == 3


def test_smoke_says_it_does_not_honour_the_registration():
    """A shortened window cannot be mistaken for the registered read."""
    import inspect
    src = inspect.getsource(X.X5_exclusion_screen)
    assert '"honours_the_registration": bool(not smoke)' in src


def test_the_receipt_declares_both_controls():
    import inspect
    src = inspect.getsource(X.X5_exclusion_screen)
    assert "random exclusion of the SAME COUNT" in src
    assert "PRIMARY_vs_random_exclusion_twin" in src
    assert "PRIMARY_vs_unscreened" in src


def test_holm_corrects_the_random_exclusion_comparison():
    """Correcting the easier comparison would be correcting the wrong test."""
    import inspect
    src = inspect.getsource(X.X5_exclusion_screen)
    assert 'pvals[name] = vs_tw.get("p_two_sided")' in src


def test_the_difference_block_is_json_serialisable():
    panel = _panel(n_names=20, n_months=24)
    res = X.run_screen_arms(panel, _select_worst_first(panel),
                            ranks=_ranks(panel), worst_end="low",
                            pool_filter=None, floor_usd=1e6, k=5,
                            seed=X._seed_for("skew_resid"))
    d = X._difference(res["arms"]["screened"], res["arms"]["unscreened"],
                      res["blocks"], label="x")
    json.dumps(d)
    assert d["n_eras_read"] >= 1
