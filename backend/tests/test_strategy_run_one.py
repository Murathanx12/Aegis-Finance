"""S1 -- `run_one`, the four-stage chain, and the two acceptance reproductions.

THE ACCEPTANCE GATE, AND WHAT IT CAN AND CANNOT BE
==================================================
The block's gate is "the composite arena book and the growth champion both
reproduce their sealed receipts through the interface". Two things about that
sentence turned out to be load-bearing and are encoded here rather than in
prose:

* **The arena has no sealed BACKTEST receipt.** It is a forward paper engine;
  its NAV rows come from live marks. Its sealed artefact is its IDENTITY under
  scheme `book-v1` -- `config_hash`, `policy_fingerprint`, `book_fingerprint`
  -- plus the deterministic `policies.select` / `.size` pair. That is what is
  reproduced, and the receipt SAYS that is what is reproduced.
* **The growth champion's sealed era cannot be re-run, on purpose.** It is
  opened once per frozen champion against an append-only ledger and the count
  is already 1. `run_one` refuses a sealed window without an explicit
  authorisation. So the DEVELOPMENT half of `G4_seal.json` is reproduced field
  by field (that test is `slow`: it loads the 925k-row panel) and the SEALED
  half is refused. A sealed receipt that could be re-run on demand would not be
  sealed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.strategy import (Benchmark, Construction, CostModel, HoldRule,
                              LossBudget, Objective, Signal, Sizing, Strategy,
                              Universe, Window, arena_book_strategy,
                              compare_to_sealed, engines, run_one)
from backend.strategy.chain import TC_DEFECT_FLOOR, exit_attribution, hold_statistics
from backend.strategy.run import EngineNotRegistered, SealedWindowRefused

REPO = Path(__file__).resolve().parents[2]
G4_SEAL = REPO / "backend" / "data" / "optimus" / "growth_book" / "G4_seal.json"
CHAMPION_DECL = (REPO / "backend" / "data" / "optimus" / "growth_book"
                 / "G4_CHAMPION_DECLARATION.json")


# --------------------------------------------------------------- fixtures


def _series_strategy(**kw) -> Strategy:
    base = dict(
        strategy_id="test:series",
        title="a graded series",
        universe=Universe(name="u"),
        signal=Signal(name="mom_12_1"),
        construction=Construction(k=12),
        hold=HoldRule(horizon_periods=21),
        sizing=Sizing(),
        costs=CostModel(transaction_cost_bps=5.0, slippage_bps=1.0),
        benchmark=Benchmark(),
        objective=Objective(name="alpha_intercept"),
        loss_budget=LossBudget(positions_judged=20, expected_losers=8),
        engine="series",
    )
    base.update(kw)
    return Strategy(**base)


def _monthly(seed: int = 5, n: int = 132) -> dict:
    rng = np.random.default_rng(seed)
    idx = [f"{2004 + i // 12}-{i % 12 + 1:02d}" for i in range(n)]
    mkt = rng.normal(0.006, 0.04, size=n)
    book = 0.9 * mkt + rng.normal(0.002, 0.02, size=n)
    return {"book": pd.Series(book, index=idx),
            "benchmark": pd.Series(mkt, index=idx),
            "rf": pd.Series(np.full(n, 0.001), index=idx),
            "n_boot": 100}


WINDOW = Window("2004-01", "2014-12", label="fixture")


# ------------------------------------------------------------ the receipt


def test_BETA_IS_THE_FIRST_KEY_of_every_receipt():
    """Not 'is on the receipt' -- FIRST. A reader who meets the wealth line
    before the loading has already formed the wrong impression (S43)."""
    r = run_one(_series_strategy(), window=WINDOW, data=_monthly())
    assert list(r)[0] == "beta"
    assert r["beta"] is not None


def test_the_receipt_reports_all_four_stages_of_the_information_chain():
    r = run_one(_series_strategy(), window=WINDOW, data=_monthly())
    stages = r["information_chain"]["stages"]
    assert set(stages) == {"1_prediction", "2_selection", "3_construction",
                           "4_holding_exit"}
    assert "17" in r["information_chain"]["invariant"]


def test_an_unmeasured_TC_is_CANNOT_DETERMINE_and_not_a_pass():
    """A check that did not run is not a check that passed."""
    r = run_one(_series_strategy(), window=WINDOW, data=_monthly())
    assert r["information_chain"]["transfer_coefficient"] is None
    assert r["construction_defect"] is False
    assert r["signal_verdict"].startswith("CANNOT DETERMINE")


def test_the_cost_flag_travels_onto_the_receipt_and_into_the_headline():
    r = run_one(_series_strategy(), window=WINDOW, data=_monthly())
    assert r["costs"]["zero_cost_diagnostic"] is False
    assert r["costs"]["round_trip_bps"] == pytest.approx(12.0)
    assert "12 bps round trip" in r["headline"]

    free = _series_strategy(
        strategy_id="test:free",
        costs=CostModel(transaction_cost_bps=0.0, slippage_bps=0.0,
                        zero_cost_diagnostic=True))
    rf = run_one(free, window=WINDOW, data=_monthly())
    assert rf["costs"]["zero_cost_diagnostic"] is True
    assert "FRICTIONLESS DIAGNOSTIC" in rf["headline"]


def test_the_receipt_carries_provenance_naming_argv_config_and_every_input():
    r = run_one(_series_strategy(), window=WINDOW, data=_monthly())
    prov = r["_provenance"]
    assert "sys_argv" in prov and "_inputs_opened" in prov
    assert prov["resolved_config"]["strategy_fingerprint"] == r["strategy_fingerprint"]
    assert prov["resolved_config"]["licence"] == "PRODUCT_EXPERIMENT"


def test_the_receipt_names_the_ruler_it_was_computed_under():
    r = run_one(_series_strategy(), window=WINDOW, data=_monthly())
    assert r["objective"]["name"] == "alpha_intercept"
    assert r["grade"]["objective_value"]["ruler"] == "alpha_intercept"
    assert "objective alpha_intercept" in r["headline"]


def test_n_effective_on_the_receipt_counts_date_blocks():
    r = run_one(_series_strategy(), window=WINDOW, data=_monthly())
    n = r["grade"]["n_effective"]
    assert n["basis"] == "distinct DATE BLOCKS"
    assert n["n_effective"] == n["n_rows"]        # one portfolio return per month


# ------------------------------------------------------------- refusals


def test_a_sealed_window_is_REFUSED_without_an_explicit_authorisation():
    w = Window("2016-01", "2024-12", label="sealed", sealed=True)
    with pytest.raises(SealedWindowRefused, match="SEALED"):
        run_one(_series_strategy(), window=w, data=_monthly())


def test_a_missing_window_is_a_refusal_and_not_a_default():
    from backend.strategy.contract import StrategyError
    with pytest.raises(StrategyError, match="needs a Window"):
        run_one(_series_strategy(), data=_monthly())


def test_an_unregistered_engine_is_a_refusal_that_lists_the_registered_ones():
    s = _series_strategy(strategy_id="test:nope", engine="does_not_exist")
    with pytest.raises(EngineNotRegistered, match="registered:"):
        run_one(s, window=WINDOW, data=_monthly())


def test_the_series_engine_refuses_to_grade_a_book_without_its_benchmark():
    """Beta is printed first, so a book with no benchmark is not gradeable."""
    from backend.strategy.contract import StrategyError
    d = _monthly()
    with pytest.raises(StrategyError, match="benchmark"):
        run_one(_series_strategy(), window=WINDOW,
                data={"book": d["book"], "rf": d["rf"]})


def test_the_registered_engines_are_the_three_the_interface_declares():
    assert set(engines()) == {"series", "arena_composite", "growth_lab"}


# ------------------------------------------------- the four-stage chain


def test_hold_statistics_measure_spells_and_one_sided_turnover():
    holdings = {"2020-01": ["A", "B", "C"],
                "2020-02": ["A", "B", "D"],
                "2020-03": ["A", "D", "E"]}
    h = hold_statistics(holdings)
    assert h["n_periods"] == 3
    assert h["mean_names_per_period"] == pytest.approx(3.0)
    # one name entered in each of two transitions, out of three held
    assert h["mean_turnover_one_sided"] == pytest.approx(1 / 3)
    assert h["max_hold_periods"] == 3           # A held throughout
    assert h["n_open_spells"] == 3


def test_an_exit_with_no_reason_is_counted_UNTYPED_and_not_dropped():
    e = exit_attribution([{"reason": "STOP", "pnl": -0.05},
                          {"reason": "STOP", "pnl": -0.04},
                          {"pnl": 0.02}],
                         declared_priority=("STOP", "DEADLINE"))
    assert e["n_exits"] == 3
    assert e["n_untyped"] == 1
    assert e["by_reason"]["STOP"]["n"] == 2
    assert e["by_reason"]["STOP"]["win_rate"] == pytest.approx(0.0)


def test_an_exit_reason_the_contract_never_declared_is_reported():
    e = exit_attribution([{"reason": "MARGIN_CALL"}],
                         declared_priority=("STOP", "DEADLINE"))
    assert e["reasons_not_in_declared_priority"] == ["MARGIN_CALL"]


def test_a_low_transfer_coefficient_makes_the_signal_verdict_UNREADABLE():
    """Invariant 17. The book's wealth numbers stand; the SENTENCE about its
    signal does not."""
    from backend.strategy import information_chain

    n_names, n_months = 40, 24
    rows, weights = [], {}
    rng = np.random.default_rng(3)
    for m in range(n_months):
        month = f"2020-{m % 12 + 1:02d}-{m // 12}"
        score = rng.normal(size=n_names)
        # weights deliberately UNRELATED to the score: the construction throws
        # the signal away, which is exactly what TC is for.
        w = rng.random(n_names)
        w = w / w.sum()
        for j in range(n_names):
            rows.append({"month": month, "permno": j, "pred": float(score[j]),
                         "fwd_1m": float(rng.normal())})
        weights[month] = {j: float(w[j]) for j in range(n_names)}
    panel = pd.DataFrame(rows)
    ch = information_chain(panel=panel, pred_col="pred",
                           weights_by_period=weights, ret_col="fwd_1m")
    assert ch["transfer_coefficient"] is not None
    assert abs(ch["transfer_coefficient"]) < TC_DEFECT_FLOOR
    assert ch["construction_defect"] is True
    assert ch["signal_verdict_readable_from_this_book"] == "UNREADABLE_CONSTRUCTION_DEFECT"


# ============================================================================
# ACCEPTANCE (a): THE COMPOSITE ARENA BOOK


def _fixture_day_state() -> dict:
    from scripts.run_one import _fixture_day_state as f
    return f()


def test_the_arena_composite_book_is_expressible_as_a_Strategy():
    s = arena_book_strategy("ENGINE_BASELINE_v1")
    assert s.signal.name == "arena_composite"
    assert s.construction.rule == "composite_top_k"
    assert s.construction.k == 12
    assert s.costs.round_trip_bps == pytest.approx(12.0)
    assert s.licence.value == "PRODUCT_EXPERIMENT"


def test_run_one_REPRODUCES_the_arena_books_sealed_identity_exactly():
    """ACCEPTANCE (a). The arena's sealed artefact is its identity under scheme
    `book-v1`; there is no sealed offline replay to diff against, and the
    receipt says so rather than inventing one."""
    from backend.services.arena import spec as SPEC

    b = SPEC.load_specs()["ENGINE_BASELINE_v1"]
    s = arena_book_strategy("ENGINE_BASELINE_v1")
    r = run_one(s, window=Window("2026-09-01", "2026-09-30", label="identity"),
                data={"day_state": _fixture_day_state()})
    ident = r["engine_block"]["identity"]
    sealed = {"config_hash": b.config_hash,
              "policy_fingerprint": b.policy_fingerprint,
              "book_fingerprint": b.book_fingerprint,
              "config_version": b.config_version}
    diff = compare_to_sealed(ident, sealed)
    assert diff["identical"], diff["differences"]
    assert diff["n_compared"] == 4
    assert r["engine_block"]["identity"]["selector_identity"].startswith("arena_composite@")


def test_run_one_REPRODUCES_the_arena_selection_computed_by_policies_select():
    """The selection is the other half of the reproduction: the same twelve
    names, the same ranks, the same weights, from the same functions."""
    from backend.services.arena import policies as POL

    s = arena_book_strategy("ENGINE_BASELINE_v1")
    ds = _fixture_day_state()
    r = run_one(s, window=Window("2026-09-01", "2026-09-30"), data={"day_state": ds})
    got = r["engine_block"]["selection"]

    want = POL.select(ds, top_k=12, min_price=5.0, screens=(),
                      signal="arena_composite")
    want_w = POL.size(want.chosen, ds, sizing="equal_weight", max_single_name=0.15)
    assert got["chosen"] == want.chosen
    assert got["weights"] == want_w
    assert got["n_chosen"] == 12
    assert got["gross"] == pytest.approx(1.0)


def test_the_arena_engine_refuses_to_quote_a_beta_it_did_not_measure():
    """A forward paper book has no offline series to regress. Reporting
    CANNOT DETERMINE is the finding; reporting the lane NAV's beta would quote
    a table separately marked STALE."""
    s = arena_book_strategy("ENGINE_BASELINE_v1")
    r = run_one(s, window=Window("2026-09-01", "2026-09-30"),
                data={"day_state": _fixture_day_state()})
    assert r["beta"] is None
    assert "CANNOT DETERMINE" in r["engine_block"]["beta_note_engine"]
    assert "STALE" in r["engine_block"]["beta_note_engine"]


def test_the_arena_engine_without_a_day_state_says_so_instead_of_inventing_one():
    s = arena_book_strategy("ENGINE_BASELINE_v1")
    r = run_one(s, window=Window("2026-09-01", "2026-09-30"))
    assert r["engine_block"]["selection"]["verdict"].startswith("CANNOT DETERMINE")


# ============================================================================
# ACCEPTANCE (b): THE GROWTH-BOOK CHAMPION


@pytest.mark.skipif(not CHAMPION_DECL.exists(),
                    reason=f"{CHAMPION_DECL} absent -- CHECK DID NOT RUN")
def test_the_growth_champion_is_expressible_as_a_Strategy_from_its_frozen_declaration():
    from backend.strategy import growth_champion_strategy

    d = json.loads(CHAMPION_DECL.read_text(encoding="utf-8"))
    s = growth_champion_strategy(cost_bps=25.0)
    assert s.strategy_id == f"growth:{d['champion_genome_id']}"
    assert s.engine == "growth_lab"
    assert s.engine_params["champion_sha256"] == d["champion_sha256"]
    assert s.costs.transaction_cost_bps == 25.0
    assert s.objective.name == "terminal_wealth_at_drawdown_budget"
    assert s.construction.hysteresis_rank == d["champion_genome"]["spec"]["hold_k"]
    assert set(s.sizing.overlays) == set(d["champion_genome"]["overlay"])


@pytest.mark.skipif(not G4_SEAL.exists(),
                    reason=f"{G4_SEAL} absent -- CHECK DID NOT RUN")
def test_the_sealed_era_of_the_growth_book_is_REFUSED_by_run_one():
    """ACCEPTANCE (b), the half that must NOT reproduce.

    `SEALED_ERA_OPENINGS.jsonl` already holds one opening for this champion.
    An interface that could re-run the sealed evaluation on demand would have
    destroyed the only property the seal has.
    """
    from backend.strategy import growth_champion_strategy

    seal = json.loads(G4_SEAL.read_text(encoding="utf-8"))
    assert seal["sealed_era_openings"] == 1
    s = growth_champion_strategy(cost_bps=25.0)
    w = Window(seal["sealed_era"][0], seal["sealed_era"][1],
               label="growth sealed era", sealed=True)
    with pytest.raises(SealedWindowRefused, match="opened once per frozen strategy"):
        run_one(s, window=w)


@pytest.mark.slow
@pytest.mark.skipif(not G4_SEAL.exists(),
                    reason=f"{G4_SEAL} absent -- CHECK DID NOT RUN")
def test_run_one_REPRODUCES_the_growth_books_sealed_DEVELOPMENT_cells():
    """ACCEPTANCE (b). Field for field, both cost rates, against G4_seal.json.

    Marked `slow` because it loads the 925,757-row long panel and the W3b stage
    predictions; the fast suite is offline and network-blocked and this is a
    minutes-long disk job, not a network one. The result on the dev machine is
    recorded in `backend/data/optimus/strategy_interface/S1_reproduction.json`
    and in the build doc.
    """
    from backend.strategy import growth_champion_strategy

    seal = json.loads(G4_SEAL.read_text(encoding="utf-8"))
    for bps in (10.0, 25.0):
        sealed_cell = seal["development"][f"{bps:.0f}bps"]
        s = growth_champion_strategy(cost_bps=bps)
        r = run_one(s, window=Window("2004-01", "2015-12", label="growth development"))
        got = r["engine_block"]["evaluate_growth"]
        diff = compare_to_sealed(got, sealed_cell)
        assert diff["identical"], (bps, diff["differences"], diff["absent_from_run"])
        assert diff["n_compared"] > 50, "a vacuous comparison is not a reproduction"
        assert r["beta"] == sealed_cell["beta"]
        # BYTE-FOR-BYTE, through the serialiser the sealed receipt was written
        # with. Key ORDER is part of this, so it is a strictly stronger claim
        # than the field-by-field diff above -- two dicts with the same values
        # in a different order are the same finding and a different file.
        run_bytes = json.dumps(got, indent=1, default=str)
        sealed_bytes = json.dumps(sealed_cell, indent=1, default=str)
        assert list(got) == list(sealed_cell), f"{bps}: key order differs"
        assert run_bytes == sealed_bytes, (
            f"{bps}: {hashlib.sha256(run_bytes.encode()).hexdigest()[:16]} != "
            f"{hashlib.sha256(sealed_bytes.encode()).hexdigest()[:16]}")


def test_compare_to_sealed_names_ignored_keys_rather_than_skipping_them_silently():
    d = compare_to_sealed({"a": 1, "generated_utc": "x"},
                          {"a": 1, "generated_utc": "y"})
    assert d["identical"] is True
    assert "generated_utc" in d["ignored_keys"]
    bad = compare_to_sealed({"a": 2}, {"a": 1})
    assert bad["identical"] is False
    assert bad["differences"][0]["field"] == "a"
    absent = compare_to_sealed({}, {"a": 1})
    assert absent["identical"] is False
    assert absent["n_absent_from_run"] == 1
