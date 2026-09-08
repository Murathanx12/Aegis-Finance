"""T2/H4 -- the decision log and the four-counterfactual regret grader.

The centre of this file is `TestKnownAnswer`: a grader nobody has shown to
produce the RIGHT regret on a constructed example is not a grader. The battery
lives in the module (so it is also runnable as a receipt) and is asserted here
case by case, so a failure names the case rather than the total.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from backend.config import DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM
from backend.services import counterfactual_prices as cp
from backend.services import decision_log as dl
from backend.services import human_thesis as ht

REPO = Path(__file__).resolve().parents[2]


def _row(**over):
    kw = dict(source="human:murat", symbol="AAA", direction="up", action="enter",
              decided_at_utc="2026-03-02T13:00:00+00:00", decision_day="2026-03-02",
              horizon_sessions=10, min_normal_hold_sessions=5,
              review_cadence_sessions=5, loss_budget_ref="human_v1",
              observed=True, ranked=True, bought=True)
    kw.update(over)
    return dl.DecisionRow(**kw)


# ── the known-answer battery ────────────────────────────────────────────────
class TestKnownAnswer:
    @pytest.fixture(scope="class")
    def battery(self):
        return dl.known_answer_battery()

    def test_the_battery_is_not_empty(self, battery):
        """The guard on the guard. A battery that silently plants nothing passes
        forever while checking nothing -- S47's exact failure."""
        assert battery["n_cases"] >= 25
        names = {c["case"] for c in battery["cases"]}
        for must in ("short/actual", "no_spy/ret_is_none", "pending/status",
                     "early/taxonomy", "unsourced/refused"):
            assert must in names

    def test_every_planted_case_passes(self, battery):
        failed = [(c["case"], c["got"], c["want"], c["catches"])
                  for c in battery["cases"] if not c["pass"]]
        assert not failed, f"planted cases FAILED: {failed}"

    def test_every_case_says_what_it_catches(self, battery):
        """A battery of assertions with no stated failure mode is a checksum."""
        for c in battery["cases"]:
            assert len(c["catches"]) > 15

    def test_the_battery_can_actually_fail(self, monkeypatch):
        """Break the arithmetic and the battery must go red. Without this the
        29 green lines above are 29 lines of decoration."""
        real = dl._leg

        def bent(name, out, sign):
            leg = real(name, out, sign)
            if leg.get("available"):
                leg["ret"] = float(leg["ret"]) + 0.01
            return leg

        monkeypatch.setattr(dl, "_leg", bent)
        assert dl.known_answer_battery()["all_pass"] is False


# ── the four legs ───────────────────────────────────────────────────────────
class TestFourCounterfactuals:
    def test_all_four_names_are_graded(self):
        g = dl.resolve(_row(engine_pick_symbol="ENG"), as_of="2026-03-16",
                       price_fn=dl._synth_price_fn)
        assert set(g["counterfactuals"]) == set(dl.COUNTERFACTUALS)
        assert set(g["regret"]) == set(dl.COUNTERFACTUALS)
        assert len(dl.COUNTERFACTUALS) == 4

    def test_the_row_resolves_at_its_OWN_horizon_not_five_days(self):
        short = dl.resolve(_row(horizon_sessions=5, review_cadence_sessions=5),
                           as_of="2026-03-16", price_fn=dl._synth_price_fn)
        long_ = dl.resolve(_row(horizon_sessions=10), as_of="2026-03-16",
                           price_fn=dl._synth_price_fn)
        assert short["resolves_on"] == "2026-03-09"
        assert long_["resolves_on"] == "2026-03-16"
        assert short["resolves_on"] != long_["resolves_on"], (
            "two rows with different declared horizons resolved on the same day; "
            "the grader is on a fixed clock")

    def test_every_available_leg_names_a_source(self):
        g = dl.resolve(_row(engine_pick_symbol="ENG"), as_of="2026-03-16",
                       price_fn=dl._synth_price_fn)
        for leg in g["counterfactuals"].values():
            assert leg["source"], f"{leg['leg']} has no source"

    def test_a_missing_benchmark_is_never_zero(self):
        def no_spy(symbol, start, end):
            if str(symbol).upper() == "SPY":
                return {"ok": False, "ret": None, "source": "NOT_AVAILABLE",
                        "reason": "planted"}
            return dl._synth_price_fn(symbol, start, end)

        g = dl.resolve(_row(), as_of="2026-03-16", price_fn=no_spy)
        assert g["counterfactuals"]["spy"]["ret"] is None
        assert g["regret"]["spy"] is None
        assert g["fully_graded"] is False

    def test_the_spy_leg_does_not_read_a_broker(self):
        """The `market` account's keys are not in this environment, so the leg
        must be computed from PRICE data. AST-scanned rather than asserted."""
        src = (REPO / "backend" / "services" / "decision_log.py").read_text(
            encoding="utf-8")
        tree = ast.parse(src)
        names = {getattr(n.func, "id", getattr(n.func, "attr", ""))
                 for n in ast.walk(tree) if isinstance(n, ast.Call)}
        assert not (names & {"TradingClient", "get_account", "submit_order",
                             "OrderRequest", "list_positions"})
        g = dl.resolve(_row(), as_of="2026-03-16", price_fn=dl._synth_price_fn)
        assert g["benchmark"]["keys_present"] is False
        assert g["benchmark"]["account"] == "PA3I7VTCC0BM"

    def test_a_short_thesis_earns_when_the_stock_falls(self):
        g = dl.resolve(_row(symbol="BBB", direction="down"), as_of="2026-03-16",
                       price_fn=dl._synth_price_fn)
        assert g["actual"]["ret"] == pytest.approx(0.20)
        assert g["counterfactuals"]["spy"]["ret"] == pytest.approx(0.02), (
            "the benchmark's sign flipped with the thesis")

    def test_an_unsourced_price_is_refused(self):
        with pytest.raises(dl.DecisionRefused):
            dl.resolve(_row(), as_of="2026-03-16",
                       price_fn=lambda s, a, b: {"ok": True, "ret": 0.5})


# ── PENDING and the as_of gate ──────────────────────────────────────────────
class TestPendingAndAsOf:
    def test_a_row_before_its_horizon_is_PENDING_with_no_numbers(self):
        g = dl.resolve(_row(), as_of="2026-03-10", price_fn=dl._synth_price_fn)
        assert g["status"] == "PENDING"
        assert g["counterfactuals"] is None and g["regret"] is None

    def test_a_lesson_cannot_be_read_before_it_was_learnable(self, tmp_path):
        p = tmp_path / "grades.jsonl"
        g = dl.resolve(_row(), as_of="2026-03-16", price_fn=dl._synth_price_fn)
        dl.record_grade(g, path=p)
        with pytest.raises(dl.LessonNotYetLearnable) as e:
            dl.lessons(as_of="2026-03-10", path=p, decision_id=g["decision_id"])
        assert "learnable" in str(e.value)
        got = dl.lessons(as_of="2026-03-17", path=p, decision_id=g["decision_id"])
        assert got["n"] == 1

    def test_the_bulk_gate_counts_what_it_withheld(self, tmp_path):
        p = tmp_path / "grades.jsonl"
        dl.record_grade(dl.resolve(_row(horizon_sessions=5, review_cadence_sessions=5),
                                   as_of="2026-03-16",
                                   price_fn=dl._synth_price_fn), path=p)
        dl.record_grade(dl.resolve(_row(symbol="BBB", horizon_sessions=10),
                                   as_of="2026-03-16",
                                   price_fn=dl._synth_price_fn), path=p)
        # the 5-session row resolves 2026-03-09, the 10-session row 2026-03-16.
        out = dl.lessons(as_of="2026-03-08", path=p)
        assert out["n"] == 0 and out["n_withheld"] == 2
        out2 = dl.lessons(as_of="2026-03-10", path=p)
        assert out2["n"] == 1 and out2["n_withheld"] == 1, (
            "the as_of gate is all-or-nothing; it is not reading each row's own "
            "resolution date")

    def test_an_unknown_decision_id_is_a_refusal_not_an_empty_list(self, tmp_path):
        with pytest.raises(dl.LessonNotYetLearnable):
            dl.lessons(as_of="2999-01-01", path=tmp_path / "none.jsonl",
                       decision_id="deadbeef")


# ── the taxonomy ────────────────────────────────────────────────────────────
class TestTaxonomy:
    def test_the_four_named_states_all_exist(self):
        for s in ("NOT_OBSERVED", "GENERATED_NOT_RANKED", "RANKED_NOT_BOUGHT",
                  "BOUGHT_SOLD_EARLY"):
            assert s in dl.TAXONOMY and s in dl.TAXONOMY_MEANING

    @pytest.mark.parametrize("kw,want", [
        (dict(observed=False), "NOT_OBSERVED"),
        (dict(observed=True, ranked=False), "GENERATED_NOT_RANKED"),
        (dict(observed=True, ranked=True, bought=False), "RANKED_NOT_BOUGHT"),
        (dict(observed=True, ranked=True, bought=True), "CAPTURED"),
    ])
    def test_each_state_is_reachable(self, kw, want):
        assert dl.classify(_row(**kw))["state"] == want

    def test_an_early_exit_is_typed_early(self):
        r = _row(exit_day="2026-03-05", min_normal_hold_sessions=5)
        assert dl.classify(r, sessions_held=3)["state"] == "BOUGHT_SOLD_EARLY"

    def test_an_exit_at_the_minimum_hold_is_NOT_early(self):
        r = _row(exit_day="2026-03-09", min_normal_hold_sessions=5)
        assert dl.classify(r, sessions_held=5)["state"] == "CAPTURED"

    @pytest.mark.parametrize("kw", [dict(observed=None),
                                    dict(observed=True, ranked=None),
                                    dict(observed=True, ranked=True, bought=None)])
    def test_an_unknown_input_refuses_instead_of_blaming_a_stage(self, kw):
        out = dl.classify(_row(**kw))
        assert out["state"] == dl.UNCLASSIFIED
        assert "UNKNOWN" in out["reason"]

    def test_no_exit_is_not_evidence_of_an_early_one(self):
        assert dl.classify(_row(exit_day=None))["state"] == "CAPTURED"


# ── the honesty gate ────────────────────────────────────────────────────────
class TestHonestyGate:
    def test_under_twenty_rows_there_is_no_pnl(self, tmp_path):
        p = tmp_path / "g.jsonl"
        for i in range(3):
            g = dl.resolve(_row(engine_pick_symbol="ENG",
                                decided_at_utc=f"2026-03-02T1{i}:00:00+00:00"),
                           as_of="2026-03-16", price_fn=dl._synth_price_fn)
            dl.record_grade(g, path=p)
        b = dl.scoreboard(path=p)
        assert b["gate"]["met"] is False
        assert b["pnl"] is None
        assert b["claim"] == "a receipt, not a result"
        assert b["process_metrics"]["taxonomy_histogram"]

    def test_the_gate_can_go_green(self, tmp_path):
        """A gate that cannot go green is a broken gate, not a strict one."""
        p = tmp_path / "g.jsonl"
        for i in range(DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM):
            g = dl.resolve(_row(engine_pick_symbol="ENG",
                                decided_at_utc=f"2026-03-02T{i:02d}:00:00+00:00"),
                           as_of="2026-03-16", price_fn=dl._synth_price_fn)
            dl.record_grade(g, path=p)
        b = dl.scoreboard(path=p)
        assert b["gate"]["met"] is True
        assert b["pnl"]["n"] == DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM
        assert "not an alpha claim" in b["pnl"]["caveat"]

    def test_a_three_leg_row_does_not_count_toward_the_gate(self, tmp_path):
        p = tmp_path / "g.jsonl"
        for i in range(DECISION_LOG_MIN_GRADED_ROWS_FOR_PNL_CLAIM):
            g = dl.resolve(_row(decided_at_utc=f"2026-03-02T{i:02d}:00:00+00:00"),
                           as_of="2026-03-16", price_fn=dl._synth_price_fn)
            dl.record_grade(g, path=p)      # no engine pick => 3 legs
        assert dl.scoreboard(path=p)["gate"]["met"] is False


# ── the reflection ──────────────────────────────────────────────────────────
class TestReflection:
    def test_the_paid_provider_is_refused_by_name(self):
        g = dl.resolve(_row(), as_of="2026-03-16", price_fn=dl._synth_price_fn)
        with pytest.raises(dl.DecisionRefused):
            dl.reflect(g, backends=("deepseek",))

    def test_deepseek_is_not_in_the_declared_chain(self):
        from backend.config import DECISION_REFLECTION_BACKENDS
        assert "deepseek" not in DECISION_REFLECTION_BACKENDS

    def test_an_unusable_reply_is_refused_and_costs_nothing(self, monkeypatch):
        class Reply:
            backend, model, text = "local_gguf", "local", "one sentence only."
            cost_usd, cost_class = 0.0, "free"
            tokens_in = tokens_out = 1
            latency_s = 0.1

        import backend.services.free_inference as fi
        monkeypatch.setattr(fi, "complete", lambda *a, **k: Reply())
        g = dl.resolve(_row(), as_of="2026-03-16", price_fn=dl._synth_price_fn)
        out = dl.reflect(g, backends=("local_gguf",), record=False)
        assert out["status"] == "REFUSED"
        assert out["cost_usd"] == 0.0 and out["paid_provider_used"] is False

    def test_a_good_reply_is_accepted_and_priced_at_zero(self, monkeypatch):
        class Reply:
            backend, model = "local_gguf", "local"
            text = "It earned 21%. SPY earned 2%. The process held to horizon."
            cost_usd, cost_class = 0.0, "free"
            tokens_in, tokens_out, latency_s = 200, 40, 2.5

        import backend.services.free_inference as fi
        monkeypatch.setattr(fi, "complete", lambda *a, **k: Reply())
        g = dl.resolve(_row(), as_of="2026-03-16", price_fn=dl._synth_price_fn)
        out = dl.reflect(g, backends=("local_gguf",), record=False)
        assert out["status"] == "OK" and out["sentences"] == 3
        assert out["cost_usd"] == 0.0 and out["cost_class"] == "free"

    def test_the_prompt_carries_all_four_legs_and_invents_nothing(self):
        g = dl.resolve(_row(engine_pick_symbol="ENG"), as_of="2026-03-16",
                       price_fn=dl._synth_price_fn)
        p = dl.reflection_prompt(g)
        for name in dl.COUNTERFACTUALS:
            assert name in p
        assert "+21.00%" in p


# ── the row itself ──────────────────────────────────────────────────────────
class TestDecisionRow:
    def test_a_source_with_no_authority_level_is_refused(self):
        with pytest.raises(dl.DecisionRefused):
            _row(source="murat")

    def test_mode_is_derived_from_the_brain_not_declared(self):
        assert _row(source="human:murat").mode == "A"
        assert _row(source="engine:hack6").mode == "B"

    def test_an_undeclared_loss_budget_is_refused(self):
        with pytest.raises(dl.DecisionRefused):
            _row(loss_budget_ref="none_of_them")

    def test_a_zero_horizon_is_refused(self):
        with pytest.raises(dl.DecisionRefused):
            _row(horizon_sessions=0)

    def test_a_thesis_becomes_a_row_carrying_the_same_three_fields(self):
        from datetime import datetime, timedelta, timezone
        t = ht.build(symbol="NVDA", direction="up", expected_move=0.06,
                     catalyst="print",
                     catalyst_at_utc=(datetime.now(timezone.utc)
                                      + timedelta(days=20)).isoformat(),
                     reason="AI demand accelerating faster than the guide",
                     falsifier="Q4 guide at or below $104bn, or GM below 74%",
                     horizon_sessions=63, min_normal_hold_sessions=21,
                     loss_budget_ref="thesis_3m_v1")
        r = dl.from_thesis(t)
        assert (r.horizon_sessions, r.min_normal_hold_sessions,
                r.loss_budget_ref) == (63, 21, "thesis_3m_v1")
        assert r.source == "human:murat" and r.mode == "A"
        assert r.thesis_id == t.thesis_id() and r.falsifier == t.falsifier

    def test_records_round_trip_through_the_dataclass(self, tmp_path):
        p = tmp_path / "d.jsonl"
        written = dl.record_decision(_row(engine_pick_symbol="ENG"), path=p)
        back = dl.load_decisions(p)[0]
        rebuilt = dl.DecisionRow(**{k: v for k, v in back.items()
                                    if k in dl.DecisionRow.__dataclass_fields__})
        assert rebuilt.decision_id() == written["decision_id"]


# ── the price layer ─────────────────────────────────────────────────────────
class TestPriceSources:
    def test_the_offline_panel_answers_for_spy(self):
        a = cp.close_on("SPY", "2026-08-03")
        assert a.source == "conviction_prices_csv" and a.price > 0

    def test_an_unknown_symbol_refuses_with_the_attempts(self):
        with pytest.raises(cp.PriceUnavailable) as e:
            cp.close_on("NOTATICKER", "2026-08-03",
                        sources=("conviction_prices_csv",))
        assert e.value.attempts and e.value.attempts[0]["answered"] is False

    def test_a_date_past_the_panel_is_not_carried_forward(self):
        with pytest.raises(cp.PriceUnavailable):
            cp.close_on("SPY", "2030-01-02", sources=("conviction_prices_csv",))

    def test_window_return_without_prices_has_no_number(self):
        out = cp.window_return("NOTATICKER", "2026-07-01", "2026-08-03",
                               sources=("conviction_prices_csv",))
        assert out["ok"] is False and out["ret"] is None
        assert out["source"] == "NOT_AVAILABLE"

    def test_the_source_report_names_the_benchmark_account_problem(self):
        r = cp.source_report()
        assert "PA3I7VTCC0BM" in r["benchmark_note"]
        assert r["order"] == list(r["order"])

    def test_sessions_are_counted_on_a_named_calendar(self):
        day, cal = cp.sessions_after("2026-03-02", 10)
        assert str(day) == "2026-03-16"
        assert cal in (cp.XNYS, cp.WEEKDAY_APPROX)

    def test_zero_sessions_is_the_same_day(self):
        day, _ = cp.sessions_after("2026-03-02", 0)
        assert str(day) == "2026-03-02"


def test_the_module_can_be_run_as_a_receipt():
    assert dl.main() == 0
