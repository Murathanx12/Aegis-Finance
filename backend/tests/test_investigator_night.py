"""INTERNET-INVESTIGATOR-FWD-1 nightly runner — pairing, budget, and voiding.

Offline: the LLM call, the tool runner and the ledger append are all injected or
monkeypatched. Nothing here reaches a vendor or writes the live ledger.

WHAT THESE PROTECT
==================
A night is only usable if every arm saw the same cells and the spend was read
rather than guessed. Both failure modes are silent by nature — a partial night
looks exactly like a complete one in the ledger, and an unreadable telemetry
file looks exactly like a free night — so both are tested for explicitly.
"""

from __future__ import annotations

import json

import pytest

from backend.services import investigator_night as N
from backend.services import investigator_tools as IT
from backend.services.investigator_agent import FORECAST_CELLS
from backend.services.iif1_prereg import load_frozen_config


def _feats(z=1.0):
    return {"abs_resid_return_z_1d": z, "volume_z_20d": 0.5,
            "earnings_within_5d": False, "filing_within_2d": False,
            "price": 100.0, "dollar_volume_20d": 1e9}


class FakeReply:
    def __init__(self, text, model="deepseek-v4-flash"):
        self.text = text
        self.model_version = model
        self.tokens_in = 10
        self.tokens_out = 20
        self.latency_ms = 1.0
        self.retries = 0


def good_llm(*, system, user, model="deepseek-v4-flash", **kw):
    if "Extract what changed" in system:
        body = {"what_changed": "earnings", "when": "soon",
                "who_is_affected": [], "novelty": "low",
                "expectedness": "fully_expected", "unknowns": []}
    elif "prior_market_belief" in system:
        body = {"prior_market_belief": "b", "what_moved_in_expectations": "m",
                "already_priced": "partly"}
    elif "MAGNITUDE" in system:
        body = {"forecasts": [
            {"observable": o, "horizon_days": h, "threshold": t,
             "prior": 0.20, "posterior": 0.35, "rationale": "r"}
            for o, h, t in FORECAST_CELLS]}
    elif "strongest_objection" in system:
        body = {"strongest_objection": "o", "contradicting_evidence": "c",
                "falsifying_check": "f", "confidence_in_chain": "low"}
    else:
        body = {"calls": [], "done": True}
    return FakeReply(json.dumps(body), model)


def no_tools(name, args, budget=None):
    return IT.ToolResult(name, IT.STATUS_EMPTY)


# ── the night runs ──────────────────────────────────────────────────────────

def test_a_dry_run_produces_records_for_every_arm_and_writes_nothing(tmp_path,
                                                                     monkeypatch):
    appended = []
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: appended.extend(recs))
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(6)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True, night="2026-08-14")
    assert res.status == "ok"
    assert len(res.tickers) == 3
    assert set(res.per_arm) == set(N.ARMS)
    for arm in N.ARMS:
        assert res.per_arm[arm]["n_cells"] == 3
        assert res.per_arm[arm]["n_with_forecasts"] == 3
    assert appended == [], "a dry run wrote to the ledger"
    assert res.records_written == 0


def test_every_arm_receives_the_identical_cell_set():
    """The property the paired Brier statistic depends on."""
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(8)},
                      k=4, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    seen = {arm: {r["ticker"] for r in res.per_arm[arm]["rows"]}
            for arm in N.ARMS}
    assert len(set(map(frozenset, seen.values()))) == 1, seen


def test_records_carry_the_arm_and_the_belief_change(monkeypatch):
    captured = []
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: captured.extend(recs))
    monkeypatch.setattr(N, "RECEIPTS_DIR", __import__("pathlib").Path(
        __import__("tempfile").mkdtemp()))
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.01, 5))
    res = N.run_night({"T1": _feats()}, k=1, llm_call=good_llm,
                      tool_runner=no_tools, dry_run=False, sandbox=True)
    assert res.status == "ok"
    # A sandbox run mints in memory and writes NOTHING to the evidence ledger,
    # `dry_run=False` notwithstanding — that is the separation.
    assert captured == [], "a sandbox run reached the evidence ledger"
    captured = list(res.records)
    assert captured, "nothing was minted"
    arms = {r.arm for r in captured}
    assert arms == set(N.ARMS)
    for r in captured:
        assert r.prior == pytest.approx(0.20)
        assert r.posterior == pytest.approx(0.35)
        assert r.belief_change == pytest.approx(0.15)
        assert r.probability == r.posterior
        assert r.specialist.startswith("investigator:")


def test_an_empty_trigger_night_is_void_not_silently_empty():
    res = N.run_night({"T1": {"price": 1.0}}, k=5, llm_call=good_llm,
                      tool_runner=no_tools, dry_run=True, sandbox=True)
    assert res.status == "void"
    assert "no eligible triggers" in res.void_reason
    assert res.records_written == 0


# ── budget ──────────────────────────────────────────────────────────────────

def test_an_unreadable_telemetry_ledger_stops_the_night_rather_than_spending_blind():
    """A read failure that reported zero would disarm the ceiling at exactly
    the moment it is needed."""
    from backend.services import llm_telemetry
    import backend.services.investigator_night as NN

    orig = llm_telemetry.spend
    try:
        llm_telemetry.spend = lambda **kw: {}
        with pytest.raises(N.NightlyBudgetExhausted, match="UNKNOWN, not zero"):
            NN._spend_since("2026-08-14T00:00:00+00:00")
    finally:
        llm_telemetry.spend = orig


def test_the_nightly_ceiling_refuses_before_the_call_not_after(monkeypatch):
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (99.0, 10))
    call = N.make_llm_call(since_iso="2026-08-14T00:00:00+00:00", max_usd=12.0)
    with pytest.raises(N.NightlyBudgetExhausted, match="nightly ceiling"):
        call(system="s", user="u")


def test_the_call_ceiling_also_binds(monkeypatch):
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.01, 99_999))
    call = N.make_llm_call(since_iso="x", max_usd=12.0, max_calls=3000)
    with pytest.raises(N.NightlyBudgetExhausted, match="call ceiling"):
        call(system="s", user="u")


def test_budget_exhaustion_mid_night_marks_the_night_rather_than_pretending(
        monkeypatch):
    calls = {"n": 0}

    def flaky(*, system, user, model="m", **kw):
        calls["n"] += 1
        if calls["n"] > 6:
            raise N.NightlyBudgetExhausted("nightly ceiling reached")
        return good_llm(system=system, user=user, model=model)

    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (12.0, 50))
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(4)},
                      k=4, llm_call=flaky, tool_runner=no_tools, dry_run=True, sandbox=True)
    assert res.status in ("budget_stopped", "void")
    assert res.void_reason


# ── the pairing guard voids rather than degrades ────────────────────────────

def test_divergent_cells_void_the_night_and_mint_nothing(monkeypatch):
    """A partial night written to the ledger would look like data."""
    captured = []
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: captured.extend(recs))
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.01, 5))

    seen = {"n": 0}
    real = N.Investigator

    class Sabotage(real):                                    # type: ignore
        def investigate(self, ticker, snapshot=None):
            seen["n"] += 1
            # the third arm silently drops a name
            if self.arm == "C_tools_only" and ticker.endswith("2"):
                raise N.NightlyBudgetExhausted("simulated drop")
            return super().investigate(ticker, snapshot)

    monkeypatch.setattr(N, "Investigator", Sabotage)
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    assert res.status in ("void", "budget_stopped")
    assert captured == [], "a divergent night minted records"


# ── the cell set is asserted BEFORE the money, not only after ───────────────

def test_the_frozen_cell_set_is_checked_before_any_arm_makes_a_call(monkeypatch):
    """The end-of-night guard catches an arm that dropped cells while running.
    It cannot catch an arm handed the wrong cells to begin with until all five
    arms have been paid for. This check fires before the first vendor call.
    """
    calls = {"n": 0}

    def counting_llm(**kw):
        calls["n"] += 1
        return good_llm(**kw)

    # Corrupt the frozen set the instant the runner tries to hand it out.
    real_assert = N.TR.assert_arms_share_cells

    def sabotage(per_arm):
        if "__frozen_trigger_set__" in per_arm:
            raise ValueError("simulated pre-call cell divergence")
        return real_assert(per_arm)

    monkeypatch.setattr(N.TR, "assert_arms_share_cells", sabotage)
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.0, 0))
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=counting_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    assert res.status == "void"
    assert calls["n"] == 0, "the night spent money before checking its pairing"


def test_the_pre_call_check_names_the_frozen_set_as_the_reference():
    """The reference arm in the message must be the frozen set, so a divergence
    report says which side is authoritative rather than blaming whichever arm
    happened to be iterated first."""
    with pytest.raises(ValueError) as exc:
        N.TR.assert_arms_share_cells({"__frozen_trigger_set__": ["A", "B"],
                                      "B_tools": ["A"]})
    assert "__frozen_trigger_set__" in str(exc.value)


# ── the funding arithmetic, and the ceiling that is not a plan ──────────────

def test_the_night_receipt_carries_the_four_required_funding_numbers():
    res = N.project_funding(0.75)
    for k in ("measured_cost_night_1", "projected_40_night_cost",
              "current_balance", "funding_gap_or_surplus"):
        assert k in res and res[k] is not None
    assert res["projected_40_night_cost"] == pytest.approx(30.0)
    # Against the CONSTANT, not a literal. The balance is a dated fact that
    # changes when Murat tops up (it did, 2026-08-15: 37.12 -> 57.12), and a
    # test pinned to yesterday's figure fails for the one reason that is not a
    # defect.
    assert res["funding_gap_or_surplus"] == pytest.approx(
        N.DEFAULT_BALANCE_USD - 30.0)
    assert res["fundable_nights_at_this_rate"] == int(
        N.DEFAULT_BALANCE_USD // 0.75)


def test_a_night_under_the_ceiling_can_still_be_unfundable():
    """The distinction the referee insisted on. $4 is a third of the safety
    ceiling and still leaves the trial unable to reach its first look."""
    res = N.project_funding(4.00)
    assert res["measured_cost_night_1"] < res["safety_ceiling_per_night"]
    assert res["funding_gap_or_surplus"] < 0
    assert res["fundable_nights_at_this_rate"] == int(
        N.DEFAULT_BALANCE_USD // 4.00)
    # The point of the test: under the ceiling, still short of the first look.
    assert res["fundable_nights_at_this_rate"] < res["nights_required"]


def test_the_funding_average_is_the_planning_number_not_the_ceiling():
    res = N.project_funding(0.75)
    assert res["funding_average_per_night"] == pytest.approx(
        N.DEFAULT_BALANCE_USD / 40, abs=1e-4)
    assert res["funding_average_per_night"] < res["safety_ceiling_per_night"]


def test_an_unreadable_spend_is_reported_unknown_rather_than_free():
    """`_spend_since` returns -1.0 when the telemetry ledger could not be read.
    A projection of $0.00/night off that number would read as a free trial."""
    for bad in (-1.0, 0.0):
        res = N.project_funding(bad)
        assert res["measured_cost_status"] == "unknown"
        assert res["measured_cost_night_1"] is None
        assert res["projected_40_night_cost"] is None
        assert res["funding_gap_or_surplus"] is None


def test_run_night_attaches_the_budget_block_to_the_receipt(monkeypatch):
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: None)
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.50, 20))
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True, night="2026-08-15")
    assert res.budget["measured_cost_night_1"] == pytest.approx(0.50)
    assert res.budget["projected_40_night_cost"] == pytest.approx(20.0)
    assert "trial" in res.as_dict()


# ── the blind stays blind ───────────────────────────────────────────────────

def test_the_receipt_carries_operational_diagnostics_and_no_trial_statistics(
        monkeypatch):
    """The runner may not compute or store anything from which the primary
    contrast could be read during the blind. Forecast probabilities live in the
    ledger, which is gated; the nightly receipt is read by a human every day.
    """
    monkeypatch.setattr("backend.services.belief_state.append",
                        lambda recs, path=None: None)
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.01, 5))
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    d = res.as_dict()
    # `cell_pairing.key` is a prose description of the pairing key, not data —
    # it names the fields ("... x threshold") without carrying any of their
    # values. Dropped before the scan so the scan can stay a blunt substring
    # search, which is what makes it hard to defeat by accident.
    d.get("cell_pairing", {}).pop("key", None)
    blob = json.dumps(d, default=str)
    # Counts (`n_forecasts`) are operational and stay. Anything from which a
    # forecast's VALUE could be recovered does not.
    for leak in ("posterior", "prior\"", "probability", "brier", "rationale",
                 "threshold", "contrast", "t_statistic", "observable"):
        assert leak not in blob, f"receipt leaks {leak!r} during the blind"
    row = res.per_arm["B_tools"]["rows"][0]
    # Deliberately exhaustive: a new field on this row reaches a human's eyes
    # every morning of the blind, so adding one has to be a decision rather
    # than a diff nobody looked at. The three added 2026-08-15 are diagnostic
    # and value-free — a closed-vocabulary drop CODE, a count of truncated
    # calls, and the vendor's stop reason ("stop"/"length"). None of them can
    # carry a probability.
    # The three added 2026-08-16 are wall-clock instants and a duration. They
    # are the evidence for the concurrency amendment's whole claim — that the
    # arms of one cell see the same world — so they have to be on the row that
    # gets read. A clock cannot carry a probability.
    # The two added 2026-08-17 are a count of malformed tool calls and the
    # closed-vocabulary CODES for them. They earn a place on the row because the
    # failure they record can only strike tool-USING arms — Night 1 lost
    # B_tools/ICE this way, and one dead cell cost three paired cells from every
    # other arm — so a nonzero value is a directional bias in the primary
    # contrast rather than a data-quality footnote. Value-free by construction:
    # `TOOL_CALL_DROP_REASONS` is closed and asserted below, and a count of
    # skipped lookups cannot carry a probability.
    assert set(row) == {"arm", "ticker", "status", "n_calls", "n_tool_calls",
                        "n_forecasts", "forecast_drops", "terminal_drop_reason",
                        "n_truncated_calls", "finish_reasons", "served_models",
                        "tokens_in", "tokens_out", "error",
                        "arm_started_at", "arm_finished_at", "arm_seconds",
                        "tool_call_drops", "n_tool_call_drops"}
    _IA = __import__("backend.services.investigator_agent", fromlist=["x"])
    assert set(row["tool_call_drops"]) <= set(_IA.TOOL_CALL_DROP_REASONS), (
        "a tool-call drop reason outside the closed vocabulary reached the "
        "receipt, which is how a model-stated value leaks out via an error path")
    assert row["terminal_drop_reason"] in ({""} | set(
        __import__("backend.services.investigator_agent", fromlist=["x"])
        .DROP_REASONS))
    assert isinstance(row["n_truncated_calls"], int)
    assert all(fr in ("stop", "length", "content_filter", "tool_calls")
               for fr in row["finish_reasons"])


def test_forecast_drop_reasons_are_a_closed_value_free_vocabulary():
    """Night 1 lost 15 of 40 cells in one arm and 8 of 10 in another, and the
    receipt said only `n_forecasts: 0` — the cause could not be established
    afterwards at any price. Reasons are recorded now, as CODES: a reason that
    interpolated the model's own number would leak a forecast out through the
    error path, which the blind scan above would then have to catch.
    """
    from backend.services.investigator_agent import (DROP_REASONS,
                                                     Investigator)
    banned = ("posterior", "probability", "brier", "rationale", "threshold",
              "contrast", "t_statistic", "observable")
    for code in DROP_REASONS:
        assert not any(b in code for b in banned), code

    # Every rejection path emits a code from the closed set, including the one
    # that is the leading suspect: a size bound stated in percent.
    bad = [{"observable": "abs_move_exceeds", "horizon_days": 5,
            "prior": 0.2, "posterior": 0.3, "threshold": 5},
           {"observable": "return_sign", "horizon_days": 999,
            "prior": 0.2, "posterior": 0.3},
           {"observable": "abs_move_exceeds", "horizon_days": 1,
            "prior": 0.2, "posterior": 4.0, "threshold": 0.03},
           "not an object"]
    kept, drops = Investigator._validate(bad)
    assert kept == []
    assert set(drops) <= DROP_REASONS
    assert drops.get("size_bound_not_a_fraction") == 1
    assert drops.get("cell_not_requested") == 1
    assert drops.get("belief_out_of_unit_range") == 1
    assert drops.get("cell_not_an_object") == 1


# ── the runner's constants are the registered ones ──────────────────────────

def test_runner_constants_match_the_frozen_prereg_config():
    """`investigator_night` retypes ARMS, the model, the benchmark and both
    ceilings from `iif1_config`. Only the trigger rule was previously checked
    for drift, which left the arm list — the thing the whole trial compares —
    unguarded. A missing sibling tree fails loudly rather than skipping.
    """
    mod = load_frozen_config()
    if mod is None:
        pytest.skip("frozen-config exemption declared for this context")
    assert tuple(mod.ARMS) == N.ARMS
    assert mod.REQUEST_MODEL == N.REQUEST_MODEL
    assert mod.BENCHMARK == N.BENCHMARK
    assert mod.NIGHTLY_MAX_USD == N.NIGHTLY_MAX_USD
    assert mod.NIGHTLY_MAX_CALLS == N.NIGHTLY_MAX_CALLS
    assert mod.PRIMARY_CONTRAST[0] in N.ARMS
    assert mod.PRIMARY_CONTRAST[1] in N.ARMS


def test_the_first_read_look_is_the_horizon_the_funding_is_projected_over():
    """The projection must be over the nights the design actually needs to
    reach its first licensed look. If the read schedule ever moves, this fails
    rather than quietly projecting the wrong bill."""
    mod = load_frozen_config()
    if mod is None:
        pytest.skip("frozen-config exemption declared for this context")
    assert mod.READ_SCHEDULE[0][0] == N.GRADED_NIGHTS_TO_FIRST_LOOK


# ── the exemption stops at the money ────────────────────────────────────────

def test_a_paying_night_refuses_without_the_prereg_even_when_exempted(
        monkeypatch, tmp_path):
    """The reason the CI exemption is safe.

    `AEGIS_IIF1_PREREG_ABSENT_OK=1` lets a non-accruing context (CI, a prod
    image) run without the sibling tree. If it also waved through the runner,
    the skip would simply have been rebuilt one layer down — which is this
    trial's own tool-layer bug, committed a second time in the fix for it.

    So: exemption declared, config absent, real vendor path requested (no
    injected `llm_call`) -> REFUSE.
    """
    from backend.services import iif1_prereg as P
    monkeypatch.setattr(P, "CONFIG_PATH", tmp_path / "gone" / "iif1_config.py")
    monkeypatch.setenv(P.OPT_OUT_ENV, "1")
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.0, 0))
    # NOT sandbox — the whole point is that the PRODUCTION path refuses. Marking
    # this sandbox would skip the guard and send the run at the real vendor,
    # which is how it was caught: the test hung in retry backoff instead of
    # raising.
    with pytest.raises(P.FrozenPreregMissing):
        N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                    dry_run=True)


def test_an_injected_llm_call_does_not_require_the_sibling_tree(monkeypatch,
                                                                tmp_path):
    """An injected call spends nothing, so it needs no pre-registration to
    spend it against. Tests must not be forced to carry the sibling repo."""
    from backend.services import iif1_prereg as P
    monkeypatch.setattr(P, "CONFIG_PATH", tmp_path / "gone" / "iif1_config.py")
    monkeypatch.setattr(N, "_spend_since", lambda s, **_: (0.0, 0))
    res = N.run_night({f"T{i}": _feats(float(i)) for i in range(3)},
                      k=3, llm_call=good_llm, tool_runner=no_tools,
                      dry_run=True, sandbox=True)
    assert res.status == "ok"


def test_drifted_runtime_constants_refuse_a_paying_night(monkeypatch):
    """Drift is not a warning. An accrual under unregistered parameters is not
    the trial that was pre-registered, and no number of nights fixes that."""
    from backend.services import iif1_prereg as P
    if P.load_frozen_config() is None:
        pytest.skip("frozen-config exemption declared for this context")
    monkeypatch.setattr(N, "ARMS", ("A_snapshot", "B_tools"))   # an arm dropped
    with pytest.raises(P.FrozenPreregDrifted, match="ARMS"):
        P.verify_or_refuse()


def test_verify_or_refuse_passes_on_the_real_tree_as_shipped():
    from backend.services import iif1_prereg as P
    if P.load_frozen_config() is None:
        pytest.skip("frozen-config exemption declared for this context")
    surface = P.verify_or_refuse()
    assert tuple(surface["ARMS"]) == N.ARMS
    assert surface["REQUEST_MODEL"] == N.REQUEST_MODEL
