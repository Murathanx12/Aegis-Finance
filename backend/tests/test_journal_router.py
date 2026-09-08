"""`/api/journal/*` -- the Mode A surface.

Every write path in this router is redirected into `tmp_path` by the `isolated`
fixture. A test that appended to the real journal would put fabricated human
decisions into the only labelled decision dataset this programme has, which is
the dataset's one irreparable failure mode.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import decision_log as dl
from backend.services import human_thesis as ht
from backend.services import terminal_state_reader as tsr

client = TestClient(app)


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ht, "HUMAN_THESIS_LOG", tmp_path / "theses.jsonl")
    monkeypatch.setattr(ht, "HUMAN_BOOK_LOG", tmp_path / "book.jsonl")
    monkeypatch.setattr(dl, "DECISION_LOG_PATH", tmp_path / "decisions.jsonl")
    monkeypatch.setattr(dl, "DECISION_GRADE_LOG_PATH", tmp_path / "grades.jsonl")
    return tmp_path


def _body(**over):
    kw = dict(symbol="NVDA", direction="up", expected_move=0.06,
              catalyst="Q3 FY27 print",
              catalyst_at_utc=(datetime.now(timezone.utc)
                               + timedelta(days=30)).isoformat(),
              reason="AI demand accelerating faster than the guide implies",
              falsifier="Q4 revenue guide at or below $104bn, or GM below 74%",
              horizon_sessions=21, min_normal_hold_sessions=5,
              loss_budget_ref="human_v1")
    kw.update(over)
    return kw


class TestReadSurface:
    def test_the_overview_names_the_benchmark_problem(self):
        r = client.get("/api/journal/")
        assert r.status_code == 200
        b = r.json()
        assert b["benchmark"]["keys_present"] is False
        assert b["benchmark"]["account"] == "PA3I7VTCC0BM"
        assert "PRICE DATA" in b["benchmark"]["note"]

    def test_the_overview_carries_the_schema_provenance(self):
        b = client.get("/api/journal/").json()
        assert b["schema_provenance"]["is_vendored_mirror"] is True
        assert b["brain"] == "human:murat"

    def test_the_known_answer_battery_is_an_endpoint(self):
        r = client.get("/api/journal/known-answer")
        assert r.status_code == 200
        b = r.json()
        assert b["all_pass"] is True and b["n_cases"] >= 25

    def test_all_four_counterfactuals_are_declared(self):
        b = client.get("/api/journal/").json()
        assert len(b["counterfactuals"]) == 4
        assert set(b["counterfactuals"]) == {
            "held_to_horizon", "held_to_next_review", "engine_pick_same_day", "spy"}

    def test_the_taxonomy_endpoint_carries_the_four_named_states(self):
        b = client.get("/api/journal/taxonomy").json()
        for s in ("NOT_OBSERVED", "GENERATED_NOT_RANKED", "RANKED_NOT_BOUGHT",
                  "BOUGHT_SOLD_EARLY"):
            assert s in b["states"]
        assert b["unclassified"] == "UNCLASSIFIED"

    def test_the_gate_endpoint_states_the_rule_and_the_count(self):
        b = client.get("/api/journal/gate").json()
        assert b["need"] == 20 and "four counterfactuals" in b["rule"]
        assert isinstance(b["have"], int)

    def test_every_response_declares_its_authority(self):
        for path in ("/api/journal/", "/api/journal/decisions",
                     "/api/journal/scoreboard", "/api/journal/taxonomy",
                     "/api/journal/gate"):
            b = client.get(path).json()
            assert b["licence"] == "PRODUCT_EXPERIMENT"
            assert "places no order" in b["authority"]

    def test_the_terminal_state_endpoint_never_reads_as_empty(self):
        b = client.get("/api/journal/terminal-state").json()
        assert b["status"] in ("OK", "NEVER_SYNCED", "SOURCE_UNREACHABLE")
        assert b["how_to_refresh"]

    def test_an_unknown_mirror_kind_is_422(self):
        assert client.get("/api/journal/terminal-state/nope/x.json").status_code == 422

    def test_a_missing_mirror_file_is_404(self):
        r = client.get("/api/journal/terminal-state/autopsies/1999-01-01.json")
        assert r.status_code in (404, 422)


class TestTheHonestyGate:
    def test_under_twenty_rows_there_is_no_pnl_number(self, isolated):
        b = client.get("/api/journal/scoreboard").json()
        if not b["gate"]["met"]:
            assert b["pnl"] is None
            assert b["claim"] == "a receipt, not a result"


class TestThesisBridge:
    def test_a_gradeable_decision_creates_a_thesis_and_a_pending_row(self, isolated):
        r = client.post("/api/journal/thesis", json=_body())
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["thesis"]["brain"] == "human:murat"
        assert b["thesis"]["horizon_sessions"] == 21
        assert b["decision_row"]["status"] == "PENDING"
        assert b["decision_row"]["mode"] == "A"
        assert b["book_entry"]["row"]["generator"] == "human:murat"
        assert b["book_entry"]["seal_is_attended"] is True
        assert (isolated / "theses.jsonl").exists()
        assert (isolated / "decisions.jsonl").exists()

    @pytest.mark.parametrize("over,why", [
        ({"falsifier": "goes down"}, "a falsifier under 15 chars"),
        ({"expected_move": -0.06}, "a sign disagreement"),
        ({"min_normal_hold_sessions": 0}, "a zero hold outside an event budget"),
        ({"loss_budget_ref": "invented"}, "an undeclared loss budget"),
        ({"horizon_sessions": 0}, "a zero horizon"),
        ({"reason": "cheap"}, "a reason under 10 chars"),
    ])
    def test_an_ungradeable_decision_is_422_with_the_reason(self, isolated, over, why):
        r = client.post("/api/journal/thesis", json=_body(**over))
        assert r.status_code == 422, f"{why} was accepted: {r.text[:200]}"
        assert len(r.json()["detail"]) > 30, "the refusal did not say why"

    def test_a_thesis_after_its_own_catalyst_is_422(self, isolated):
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        r = client.post("/api/journal/thesis", json=_body(catalyst_at_utc=past))
        assert r.status_code == 422
        assert "memory" in r.json()["detail"].lower()

    def test_the_row_appears_in_the_decision_log(self, isolated):
        client.post("/api/journal/thesis", json=_body())
        b = client.get("/api/journal/decisions").json()
        assert b["n"] == 1 and b["rows"][0]["symbol"] == "NVDA"
        assert b["rows"][0]["source"] == "human:murat"

    def test_a_pending_row_is_not_graded_early(self, isolated):
        client.post("/api/journal/thesis", json=_body())
        r = client.post("/api/journal/resolve", json={"as_of": "2026-09-08"})
        assert r.status_code == 200
        b = r.json()
        assert b["n_graded"] == 0 and b["n_still_pending"] == 1
        assert b["llm_cost_usd"] == 0.0

    def test_resolving_costs_nothing_when_reflection_is_off(self, isolated):
        client.post("/api/journal/thesis", json=_body())
        b = client.post("/api/journal/resolve",
                        json={"as_of": "2026-09-08", "reflect": False}).json()
        assert b["llm_cost_usd"] == 0.0
        assert "FREE backend" in b["llm_note"]


class TestAsOfGateOverHttp:
    def test_a_lesson_read_too_early_is_425(self, isolated):
        row = dl.DecisionRow(
            source="human:murat", symbol="AAA", direction="up", action="enter",
            decided_at_utc="2026-03-02T13:00:00+00:00", decision_day="2026-03-02",
            horizon_sessions=10, min_normal_hold_sessions=5,
            review_cadence_sessions=5, loss_budget_ref="human_v1",
            observed=True, ranked=True, bought=True)
        g = dl.resolve(row, as_of="2026-03-16", price_fn=dl._synth_price_fn)
        dl.record_grade(g)
        r = client.get("/api/journal/grades",
                       params={"as_of": "2026-03-10", "decision_id": g["decision_id"]})
        assert r.status_code == 425, r.text
        assert "learnable" in r.json()["detail"]
        ok = client.get("/api/journal/grades",
                        params={"as_of": "2026-03-17",
                                "decision_id": g["decision_id"]})
        assert ok.status_code == 200 and ok.json()["n"] == 1


class TestWriteAuthority:
    def test_only_three_routes_write(self):
        writes = sorted({r.path for r in app.routes
                         if getattr(r, "path", "").startswith("/api/journal")
                         and getattr(r, "methods", set()) - {"GET", "HEAD", "OPTIONS"}})
        assert writes == ["/api/journal/resolve", "/api/journal/terminal-state/sync",
                          "/api/journal/thesis"]

    def test_the_router_imports_no_broker(self):
        import ast
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2] / "backend" / "routers"
               / "journal.py").read_text(encoding="utf-8")
        mods = set()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import):
                mods |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                mods.add(n.module.split(".")[0])
        assert not (mods & {"alpaca", "alpha", "subprocess", "requests", "httpx"})
