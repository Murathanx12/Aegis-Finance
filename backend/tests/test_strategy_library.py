"""A published claim must never be able to stand in for an Aegis measurement.

Both look like a float in a column six weeks later. This is the only property
of the library that actually needs defending.
"""

from __future__ import annotations

import pytest

from backend.services.strategy_library import (SEED, ClaimIsNotEvidence,
                                               Performance, Reproduction,
                                               Source, StrategySpec,
                                               status_report)


def spec(**over) -> StrategySpec:
    base = dict(name="X", family="f", source=Source.PUBLISHED_ACADEMIC,
                citation="Someone (2001)",
                claimed=Performance(gross_annual_return=0.12, sharpe=1.4))
    base.update(over)
    return StrategySpec(**base)


# ── the guard ──────────────────────────────────────────────────────────────
def test_asking_for_a_measurement_that_does_not_exist_refuses(spec_=None):
    s = spec()
    with pytest.raises(ClaimIsNotEvidence, match="NOT a substitute"):
        s.measured("post_publication")


def test_it_refuses_even_though_a_claim_is_sitting_right_there():
    """The whole failure mode. `measured()` must contain no fallback."""
    s = spec(claimed=Performance(gross_annual_return=0.99, sharpe=9.9))
    with pytest.raises(ClaimIsNotEvidence):
        s.measured()
    assert s.claimed.gross_annual_return == 0.99, "the claim is still recorded"


def test_a_measurement_is_returned_once_it_exists():
    s = spec(post_publication=Performance(gross_annual_return=0.03))
    assert s.measured().gross_annual_return == 0.03


def test_the_refusal_names_the_reproduction_status():
    """So the reader knows whether it was never attempted or attempted and
    failed — those call for different next actions."""
    s = spec(reproduction_status=Reproduction.FAILED)
    with pytest.raises(ClaimIsNotEvidence, match="FAILED"):
        s.measured()


# ── decay ──────────────────────────────────────────────────────────────────
def test_decay_needs_both_halves_measured_on_our_data():
    s = spec(post_publication=Performance(gross_annual_return=0.02))
    d = s.decay()
    assert d["decay"] is None
    assert "cannot stand in" in d["why"]


def test_decay_compares_our_window_to_our_window_not_to_the_paper():
    """measured/claimed would confound decay with every difference between
    their pipeline and ours — universe, survivorship, costs, weighting."""
    s = spec(claimed=Performance(gross_annual_return=0.99),
             in_sample=Performance(gross_annual_return=0.10),
             post_publication=Performance(gross_annual_return=0.04))
    d = s.decay()
    assert d["decay"] == pytest.approx(0.6)
    assert d["in_sample_gross"] == 0.10, "not the claimed 0.99"


def test_the_mclean_pontiff_prior_travels_with_the_number():
    s = spec(in_sample=Performance(gross_annual_return=0.10),
             post_publication=Performance(gross_annual_return=0.10))
    d = s.decay()
    assert d["decay"] == pytest.approx(0.0)
    assert d["mclean_pontiff_prior"] == 0.58
    assert "PRIOR to compare against, not a target" in d["why"]


def test_a_zero_in_sample_return_does_not_divide_by_zero():
    s = spec(in_sample=Performance(gross_annual_return=0.0),
             post_publication=Performance(gross_annual_return=0.01))
    assert s.decay()["decay"] is None


# ── the seed ───────────────────────────────────────────────────────────────
def test_nothing_in_the_seed_claims_to_be_reproduced():
    for s in SEED:
        assert s.reproduction_status is Reproduction.NOT_ATTEMPTED, (
            f"{s.name} claims a reproduction status nobody has earned")


def test_no_seeded_strategy_carries_an_aegis_measurement():
    for s in SEED:
        assert s.in_sample is None and s.post_sample is None \
            and s.post_publication is None, f"{s.name} carries a measurement"


def test_the_status_report_says_so_out_loud():
    r = status_report()
    assert r["n_with_any_aegis_measurement"] == 0
    assert r["by_reproduction"]["NOT_ATTEMPTED"] == r["n_strategies"]
    assert "never an Aegis result" in r["warning"]


def test_every_seeded_strategy_can_be_reimplemented_from_its_own_record():
    """If the construction cannot be written down, the strategy is not
    specified and can be neither reproduced nor refuted."""
    for s in SEED:
        assert len(s.construction) > 40, f"{s.name} is under-specified"
        assert s.citation, f"{s.name} has no citation"
        assert s.family and s.universe or s.family, s.name


def test_the_high_turnover_strategies_carry_their_cost_warning():
    """Novy-Marx & Velikov: low-turnover anomalies survive costs, high-turnover
    ones mostly do not. A library that ranked purely on gross return would put
    the least implementable strategy first."""
    hot = [s for s in SEED if s.family in ("reversal", "momentum")]
    assert hot
    for s in hot:
        assert "turnover" in s.capacity_note.lower() or "cost" in s.capacity_note.lower()


def test_pead_is_seeded_as_a_conditional_question_not_a_strategy():
    """The modern evidence says the unconditional large-cap drift is attenuated
    or gone, so importing it as a strategy would be importing a dead one."""
    p = next(s for s in SEED if s.name.startswith("PEAD"))
    assert "CONDITIONAL" in p.construction
    assert "conditional" in p.priority.lower()


def test_bab_is_seeded_with_its_critique_rather_than_its_headline():
    b = next(s for s in SEED if s.name.startswith("BAB"))
    assert "betting against betting against beta" in b.citation.lower()
    assert "DECOMPOSITION" in b.construction


def test_volatility_targeting_is_labelled_a_sizing_rule():
    """It is the layer §59 says this slice can actually resolve — a risk effect
    is measurable in ~4 years where a return effect needs ~95."""
    v = next(s for s in SEED if s.name.startswith("Volatility"))
    assert "SIZING" in v.construction
    assert "not a stock picker" in v.priority


def test_sources_are_recorded_but_do_not_rank():
    """Provenance is a label, not a quality score: all three compete under the
    same utility function."""
    r = status_report()
    assert r["by_source"]["PUBLISHED_ACADEMIC"] > 0
    assert r["by_source"]["PUBLIC_PRACTITIONER"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# Attaching a measurement run — the half that turns the library from a reading
# list into a benchmark.
# ═══════════════════════════════════════════════════════════════════════════
import json  # noqa: E402

from backend.services.strategy_library import (  # noqa: E402
    IMPLEMENTED_BY, MeasurementUnavailable, Reproduction, load_measured)


def test_every_seeded_strategy_is_mapped_or_explicitly_unmapped():
    """The mapping is enrolment, not memory: a spec with no entry at all would
    silently never be measured and would read as 'not run yet' forever."""
    assert {s.name for s in SEED} == set(IMPLEMENTED_BY)


def _payload(tmp_path, results):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"window": "200601..201912",
                             "screens": {"cost_bps_per_crossing": 10.0},
                             "results": results}), encoding="utf-8")
    return p


def test_a_missing_measurement_file_refuses_rather_than_returning_claims(
        tmp_path):
    with pytest.raises(MeasurementUnavailable, match="exists to refuse"):
        load_measured(tmp_path / "never_ran.json")


def test_loading_does_not_mutate_the_module_level_seed(tmp_path):
    p = _payload(tmp_path, {"Mom12m": {"gross_annual": 0.004,
                                       "net_annual": -0.011, "sharpe": 0.05,
                                       "n_months": 167,
                                       "monthly_turnover": 1.5,
                                       "breakeven_bps": 2.6,
                                       "detectable": False}})
    specs = load_measured(p)
    got = [s for s in specs if IMPLEMENTED_BY[s.name] == "Mom12m"][0]
    assert got.measured("post_publication").net_annual_return == -0.011
    # The originals are untouched, so `measured()` stays predictable.
    orig = [s for s in SEED if IMPLEMENTED_BY[s.name] == "Mom12m"][0]
    with pytest.raises(ClaimIsNotEvidence):
        orig.measured("post_publication")


def test_a_strategy_with_no_faithful_implementation_reports_that(tmp_path):
    specs = load_measured(_payload(tmp_path, {}))
    qmj = [s for s in specs if s.name.startswith("QMJ")][0]
    assert qmj.reproduction_status is Reproduction.NOT_ATTEMPTED
    assert "no faithful implementation" in qmj.reproduction_note
    with pytest.raises(ClaimIsNotEvidence):
        qmj.measured("post_publication")


def test_the_measured_window_never_becomes_the_authors_claim(tmp_path):
    """A post-publication number is not a reproduction of the original."""
    p = _payload(tmp_path, {"GP": {"gross_annual": 0.069, "net_annual": 0.065,
                                   "sharpe": 0.4, "n_months": 167,
                                   "monthly_turnover": 0.34,
                                   "breakeven_bps": 167.3,
                                   "detectable": False}})
    gp = [s for s in load_measured(p)
          if IMPLEMENTED_BY[s.name] == "GP"][0]
    assert gp.reproduction_status is Reproduction.PARTIAL
    assert "DECAYED" in gp.reproduction_note
    # No in-sample half exists, so decay must refuse rather than invent one.
    assert gp.decay()["decay"] is None


# ═════════════════════════════════════════════════════════════════════════════
# THE RULE LIBRARY (2026-09-26, spec chunk 3b)
# ═════════════════════════════════════════════════════════════════════════════

import re  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backend.services import strategy_library as SL  # noqa: E402

_CATALOGUE = (Path(__file__).resolve().parents[2] / "docs" / "research_notes"
              / "2026-09-26" / "research_strategy_library.md")


def planted_panel(n_dates: int = 96, n_sym: int = 120, seed: int = 11) -> pd.DataFrame:
    """Month-end panel where `alpha` carries a known net edge and nothing else does."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-31", periods=n_dates, freq="ME")
    syms = [f"S{i:03d}" for i in range(n_sym)]
    band = np.arange(n_sym) % 3
    mdv = np.where(band == 0, 5e8, np.where(band == 1, 5e7, 5e6))
    rows = []
    for d in dates:
        a = rng.standard_normal(n_sym)
        fwd = rng.normal(0.008, 0.06, n_sym) + 0.02 * a
        rows.append(pd.DataFrame({
            "date": d, "symbol": syms, "eligible": True, "median_dollar_vol": mdv,
            "alpha": a, "noise_feat": rng.standard_normal(n_sym), "fwd_ret": fwd,
            "delisted_in_period": False, "is_month_end": True}))
    p = pd.concat(rows, ignore_index=True)
    p.loc[p["date"] == dates[-1], "fwd_ret"] = np.nan      # the open period
    return p


def planted_spy(panel: pd.DataFrame, seed: int = 12) -> pd.Series:
    d = sorted(panel["date"].unique())
    return pd.Series(np.random.default_rng(seed).normal(0.008, 0.04, len(d)), index=d)


def test_the_library_seeds_at_least_one_hundred_rules_with_unique_ids():
    live = SL.rules(include_controls=False)
    assert len(live) >= 100
    ids = [r.id for r in SL.RULES]
    assert len(ids) == len(set(ids))
    assert any(r.control for r in SL.RULES), "no random control -> no bar for luck"


def test_every_rule_carries_its_registration_date_and_a_fingerprint():
    stamps = {SL.REGISTERED_2026_09_26, SL.REGISTERED_2026_09_26_PM}
    for r in SL._rules():                   # the library's own rules (not the sibling module's)
        assert r.first_registered_utc in stamps, r.id
    for r in SL.RULES:
        assert re.fullmatch(r"[0-9a-f]{16}", r.fingerprint())
    assert re.fullmatch(r"[0-9a-f]{16}", SL.library_fingerprint())


@pytest.mark.skipif(not _CATALOGUE.exists(), reason="catalogue note absent")
def test_every_catalogue_row_is_a_rule_or_named_unreachable():
    """A catalogue row in neither place would be a row silently dropped."""
    text = _CATALOGUE.read_text(encoding="utf-8")
    ids = set(re.findall(r"^\| ([A-Z]+-\d+) \|", text, flags=re.M))
    assert len(ids) >= 100
    mapped = set()
    for r in SL.RULES:
        for m in re.findall(r"literature:([A-Z]+-\d+(?:/\d+)?)", r.source):
            head, _, tail = m.partition("/")
            mapped.add(head)
            if tail:
                mapped.add(head.rsplit("-", 1)[0] + "-" + tail.zfill(2))
    for e in SL.FORWARD_ONLY:
        mapped.update(re.findall(r"literature:([A-Z]+-\d+)", e["source"]))
    missing = sorted(ids - mapped - set(SL.NOT_REACHABLE))
    assert not missing, f"catalogue rows with no rule and no reason: {missing}"


def test_zero_cost_is_refused_by_the_farm_policy_it_inherits():
    from backend.services.portfolio_farm.policy import PolicyError
    with pytest.raises(PolicyError, match="zero transaction cost"):
        SL.Strategy("free", "test", "frictionless", SL.col("alpha"), cost_scale=0.0)
    ok = SL.Strategy("free_diag", "test", "declared diagnostic", SL.col("alpha"),
                     cost_scale=0.0, zero_cost_diagnostic=True)
    assert ok.zero_cost_diagnostic
    with pytest.raises(PolicyError):
        SL.Strategy("liar", "test", "labels a real run free", SL.col("alpha"),
                    cost_scale=1.0, zero_cost_diagnostic=True)


def test_a_rule_over_an_absent_column_refuses_rather_than_selecting_nothing():
    p = planted_panel(12, 30)
    r = SL.Strategy("ghost", "test", "reads a column nobody built", SL.col("not_there"))
    with pytest.raises(SL.RuleInputMissing, match="not_there"):
        SL.run_strategy(p, r)


def test_the_planted_signal_beats_noise_net_of_band_costs():
    p = planted_panel()
    good = SL.Strategy("planted", "test", "alpha", SL.col("alpha"))
    bad = SL.Strategy("noise", "test", "noise", SL.col("noise_feat"))
    mg, mb = SL.run_strategy(p, good), SL.run_strategy(p, bad)
    assert mg["net"].mean() > mb["net"].mean() + 0.01
    assert (mg["cost"] > 0).all(), "a monthly-rebalanced book traded for free"
    costs = SL._band_costs()
    first = mg.iloc[0]
    # the first month buys 100%: at most half the SMALL round trip, never zero
    assert 0 < first["cost"] <= costs["small"] / 2 / 1e4 + 1e-12
    assert first["turnover"] == pytest.approx(1.0)


def test_evaluate_prints_by_year_loo_and_the_block_t():
    p = planted_panel()
    m = SL.run_strategy(p, SL.Strategy("planted", "test", "alpha", SL.col("alpha")))
    ev = SL.evaluate(m, planted_spy(p))
    assert set(ev["by_year"]) == {str(y) for y in range(2018, 2026)}
    assert ev["loo_worst_dropped_year"] in ev["by_year"]
    assert ev["loo_worst_mean_active"] == min(ev["leave_one_year_out_mean_active"].values())
    assert ev["n_blocks_horizon"] == ev["n_date_blocks"]
    assert ev["t_active_horizon_blocks"] > 3.0 and ev["clears_hlz_t3"]
    assert ev["hindsight_since_2020"]["label"].startswith("HINDSIGHT")
    # which part of the sample: the best five months, and the CAGR without them
    assert 0 < ev["top5_months_share_of_log_return"] < 1
    assert ev["cagr_without_best_5_months"] < SL._cagr(m["net"])


def test_a_quarterly_hold_is_t_tested_on_quarterly_blocks():
    p = planted_panel()
    r = SL.Strategy("planted_q", "test", "alpha, quarterly", SL.col("alpha"), hold_months=3)
    m = SL.run_strategy(p, r)
    assert m["rebalanced"].sum() == pytest.approx(len(m) / 3, abs=1)
    ev = SL.evaluate(m, planted_spy(p), hold_months=3)
    assert ev["n_blocks_horizon"] == int(np.ceil(ev["n_date_blocks"] / 3))


def test_a_rule_registered_after_2024_06_has_no_quotable_number_before_it():
    p = planted_panel()
    r = SL.Strategy("late", "test", "alpha", SL.col("alpha"),
                    first_registered_utc="2024-07-01T00:00:00+00:00")
    m = SL.run_strategy(p, r)
    ev = SL.evaluate(m, planted_spy(p), registered_utc=r.first_registered_utc)
    q = ev["quotable_since_registration"]
    n_after = int((m["date"] >= pd.Timestamp("2024-07-01")).sum())
    assert q["status"] == "OK" and q["n_months"] == n_after
    assert 0 < n_after < len(m)
    assert "HINDSIGHT" in ev["hindsight_since_2020"]["label"]
    ev2 = SL.evaluate(m, planted_spy(p))      # registered today: nothing yet
    assert ev2["quotable_since_registration"]["status"] == "NONE_YET"


def test_deflate_uses_the_number_of_cells_looked_at():
    p = planted_panel()
    spy = planted_spy(p)
    cells = []
    for i in range(30):
        r = SL.Strategy(f"n{i}", "test", "noise", SL.seeded_noise(100 + i))
        cells.append(SL.evaluate(SL.run_strategy(p, r), spy))
    good = SL.Strategy("planted", "t", "a", SL.col("alpha"))
    cells.append(SL.evaluate(SL.run_strategy(p, good), spy))
    SL.deflate(cells, effective_trials=3)
    assert all(c["dsr_n_trials"] == 31 for c in cells)
    assert cells[-1]["dsr"] == max(c["dsr"] for c in cells)
    assert cells[-1]["dsr_effective"] >= cells[-1]["dsr"]


def test_adoption_rule_is_the_declared_one():
    kw = dict(forward_sessions=63, positive_years=4)
    assert SL.adoption_status(forward_vs_spy=0.01, forward_vs_random=0.01, **kw) == "ADOPTED"
    assert SL.adoption_status(forward_vs_spy=-0.01, forward_vs_random=-0.02, **kw) == "REJECTED"
    assert SL.adoption_status(forward_vs_spy=0.01, forward_vs_random=-0.01, **kw) == "RUNNING"
    assert SL.adoption_status(forward_vs_spy=0.05, forward_vs_random=0.05,
                              forward_sessions=62, positive_years=6) == "RUNNING"
    assert SL.adoption_status(forward_vs_spy=0.05, forward_vs_random=0.05,
                              forward_sessions=63, positive_years=3) == "RUNNING"


def test_forward_only_rules_carry_the_replay_number_as_a_citation():
    ids = {e["id"] for e in SL.FORWARD_ONLY}
    assert {"forecast_dispersion_v1", "book_f_seasonality_11_20_v0"} <= ids
    for e in SL.FORWARD_ONLY:
        assert e["green_replay_never_forward"] is True
        assert "replay" in e["replay_reported"].lower()


# ═════════════════════════════════════════════════════════════════════════════
# CHUNK D (2026-09-26 PM): the sealed split, >= 200 different rules, no thresholds
# ═════════════════════════════════════════════════════════════════════════════

def test_the_split_constants_are_declared_in_code():
    assert SL.DEV_END == "2023-12-31"
    assert SL.SEALED_START == "2024-01-01"
    assert SL.RECENT_SESSIONS == 126 and SL.RECENT_PERIODS == 6


def test_a_december_decision_earned_in_january_is_sealed():
    idx = pd.DatetimeIndex(["2023-11-30", "2023-12-29", "2024-01-31"])
    w = SL.split_windows(idx)
    assert list(w["dev"]) == [True, False, False]
    assert list(w["sealed"]) == [False, True, True]


def test_a_rule_that_differs_only_by_a_threshold_is_refused():
    lib: list = []
    SL.register(lib, SL.Strategy("a", "revision_flow", "rule >= 3 firms",
                                 SL.gated(SL.col("flow_rule_score"), "n_firms", lo=3)))
    with pytest.raises(SL.ThresholdVariant, match="differs only by a threshold or k"):
        SL.register(lib, SL.Strategy("b", "revision_flow", "rule >= 5 firms",
                                     SL.gated(SL.col("flow_rule_score"), "n_firms", lo=5)))
    with pytest.raises(SL.ThresholdVariant):
        SL.register(lib, SL.Strategy("c", "revision_flow", "same rule, k=50",
                                     SL.gated(SL.col("flow_rule_score"), "n_firms", lo=3), k=50))
    with pytest.raises(SL.ThresholdVariant):
        SL.register(lib, SL.Strategy("d", "x", "same interaction, another fraction",
                                     SL.within_top(SL.col("a"), "b", 0.3)))
        SL.register(lib, SL.Strategy("e", "x", "same interaction, another fraction",
                                     SL.within_top(SL.col("a"), "b", 0.5)))
    # a different MECHANISM on the same column is not a threshold variant
    SL.register(lib, SL.Strategy("f", "revision_flow", "NO raise at all (the other side)",
                                 SL.gated(SL.col("flow_rule_score"), "n_firms", hi=0)))
    SL.register(lib, SL.Strategy("g", "revision_flow", "same rule, large band",
                                 SL.gated(SL.col("flow_rule_score"), "n_firms", lo=3), "large"))
    SL.register(lib, SL.Strategy("h", "revision_flow", "same rule, in cash below SPY 200d",
                                 SL.gated(SL.col("flow_rule_score"), "n_firms", lo=3),
                                 regime_gate="mkt_trend_up"))
    assert [r.id for r in lib] == ["a", "d", "f", "g", "h"]


def test_the_library_holds_200_genuinely_different_rules_with_reasons():
    live = SL.rules(include_controls=False)
    assert len(live) >= 200
    sigs = [r.signature() for r in live]
    assert len(sigs) == len(set(sigs)), "two registered rules share a signature"
    for r in live:
        assert r.family and r.source and r.first_registered_utc, r.id
        assert r.economic_reason, f"{r.id} carries no economic reason"
    assert not set(SL.RETIRED_THRESHOLD_VARIANTS) & {r.id for r in SL.RULES}


def test_the_newly_reachable_rows_left_not_reachable_and_have_rules():
    moved = set(SL.BECAME_REACHABLE_2026_09_26_PM)
    assert not moved & set(SL.NOT_REACHABLE)
    mapped = set()
    for r in SL.RULES:
        mapped.update(re.findall(r"literature:([A-Z]+-\d+)", r.source))
    assert moved <= mapped, sorted(moved - mapped)


def test_evaluate_prints_the_sealed_columns():
    p = planted_panel()
    spy = planted_spy(p)
    m = SL.run_strategy(p, SL.Strategy("planted", "x", "alpha", SL.col("alpha")))
    ev = SL.evaluate(m, spy)
    for k_ in ("dev_cagr", "sealed_cagr", "sealed_vs_spy", "recent_126_return", "turnover_annual",
               "cost_bps_paid", "max_dd", "n_sealed_months", "sealed_active_returns"):
        assert k_ in ev, k_
    assert ev["n_sealed_months"] == 24          # decisions 2023-12-31 .. 2025-11-30 (last open)
    assert ev["sealed_vs_spy"] == pytest.approx(ev["sealed_cagr"] - ev["sealed_spy_cagr"])
    assert ev["recent_window"]["n_months"] == SL.RECENT_PERIODS
    assert ev["cost_bps_paid"] > 0 and ev["turnover_annual"] > 0


def test_a_regime_gate_sends_the_book_to_cash_and_charges_the_exit():
    p = planted_panel(36, 60)
    d = sorted(p["date"].unique())
    off = set(d[10:14])
    p["gate"] = [0.0 if x in off else 1.0 for x in p["date"]]
    base = SL.run_strategy(p, SL.Strategy("u", "x", "alpha", SL.col("alpha")))
    hold: list = []
    g = SL.run_strategy(p, SL.Strategy("g", "x", "alpha gated", SL.col("alpha"),
                                       regime_gate="gate"), holdings=hold)
    gi = g.set_index("date")
    for x in off:
        assert gi.loc[x, "gross"] == 0.0 and gi.loc[x, "n_held"] == 0
    assert gi.loc[d[10], "cost"] > 0            # selling into cash is charged
    assert any(h["risk_off"] for h in hold)
    on = [x for x in d[:10]]
    assert np.allclose(gi.loc[on, "net"], base.set_index("date").loc[on, "net"])


def test_inverse_vol_weights_sum_to_one_and_tilt_to_the_calm():
    p = planted_panel(24, 60)
    p["vol_63"] = np.where(p["symbol"].str[-1].astype(int) % 2 == 0, 0.2, 0.8)
    hold: list = []
    SL.run_strategy(p, SL.Strategy("w", "x", "alpha ivw", SL.col("alpha"), weight_rule="inv_vol"),
                    holdings=hold)
    for h in hold:
        assert sum(h["weights"]) == pytest.approx(1.0)
        assert max(h["weights"]) / min(h["weights"]) == pytest.approx(4.0)


def test_the_sibling_module_rules_are_registered_or_refused_by_name(monkeypatch):
    """strategy_library_ext (another builder's file) enters through `register`."""
    import importlib.machinery
    import sys
    import types
    name = "backend.services.strategy_library_ext"
    fake = types.ModuleType(name)
    fake.__spec__ = importlib.machinery.ModuleSpec(name, None)
    fake.EXTRA_STRATEGIES = [
        SL.Strategy("ext_new_mechanism", "attention", "a new column", SL.col("attention_z"),
                    economic_reason="attention shocks revert", first_registered_utc="2026-09-26T10:00:00+00:00"),
        SL.Strategy("ext_flow_rule_min7", "revision_flow", "flow_rule at 7 firms",
                    SL.gated(SL.col("flow_rule_score"), "n_firms", lo=7)),
        {"id": "ext_fwd", "family": "attention", "description": "forward only",
         "signal": SL.col("thesis_p"), "forward_only": True},
    ]
    monkeypatch.setitem(sys.modules, name, fake)
    saved = list(SL.RULES)
    try:
        SL.EXTRA_REFUSED.clear()
        SL._load_extra()
        ids = [r.id for r in SL.RULES]
        assert "ext_new_mechanism" in ids and "ext_fwd" in ids
        assert "ext_flow_rule_min7" in SL.EXTRA_REFUSED
        assert "ThresholdVariant" in SL.EXTRA_REFUSED["ext_flow_rule_min7"]
        assert SL.RULES[-1].control, "controls stay last"
        assert SL.EXTRA_SOURCE.startswith(name)
    finally:
        SL.RULES[:] = saved
        SL.EXTRA_REFUSED.clear()
