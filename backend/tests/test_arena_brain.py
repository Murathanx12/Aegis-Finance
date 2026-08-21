"""ARENA brain layer — outcome legs, perception grading, reliability, regret.

Offline. Every test builds its own tmp namespace root and its own explicit
price panel, so a price fact asserted here is a fact the test wrote, not one
yfinance happened to return.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from backend.services.arena import experience, regret, reliability, store


# ── an explicit panel: opens and closes are independent, on purpose ─────────
class DictPanel:
    """Prices given literally, so an overnight gap can be constructed."""

    def __init__(self, sessions, closes: dict, opens: dict | None = None):
        self._sessions = list(sessions)
        self._closes = closes
        self._opens = opens if opens is not None else closes

    def sessions(self):
        return list(self._sessions)

    def close_price(self, ticker, day):
        return self._closes.get(ticker.upper(), {}).get(day)

    def open_price(self, ticker, day):
        return self._opens.get(ticker.upper(), {}).get(day)

    def close_history(self, ticker, day, n):
        px = self._closes.get(ticker.upper(), {})
        return [px[s] for s in self._sessions if s <= day and s in px][-n:]


def _weekdays(n, end=None):
    end = end or (date.today() - timedelta(days=1))
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


@pytest.fixture()
def root(tmp_path):
    return tmp_path / "arena"


def _exp(root, ticker, action, day, *, is_hash="H1", book="ENGINE_BASELINE_v1",
         rank=None, alt=None, score=None):
    rec = experience.make_experience(
        book_id=book, policy_version=1, ticker=ticker, action=action,
        decision_date=str(day), information_state_hash=is_hash,
        model_id="arena_rules@v1", thesis="t", rank=rank, score=score,
        chosen_alternative=alt)
    store.append_experiences([rec], root)
    return rec


# ── the two legs ────────────────────────────────────────────────────────────
def test_forecast_and_execution_legs_are_recorded_separately(root):
    """The whole gain happens in the overnight gap BEFORE the fill.

    forecast  close 100 -> 110  = +10% vs a flat benchmark -> GOOD_CALL
    execution open 110 -> 110   =   0% vs a flat benchmark -> BAD_CALL

    If these two ever collapse into one number again, the book learns that a
    decision it could not have traded was a good decision.
    """
    ss = _weekdays(10)
    flat = {s: 100.0 for s in ss}
    closes = {"SPY": dict(flat), "GAP": dict(flat)}
    opens = {"SPY": dict(flat), "GAP": dict(flat)}
    for s in ss[1:]:
        closes["GAP"][s] = 110.0   # jumped at the close after the decision
        opens["GAP"][s] = 110.0    # ...and the open already reflects it
    panel = DictPanel(ss, closes, opens)

    _exp(root, "GAP", "ENTER", ss[0])
    out = experience.mature_outcomes(panel, today=ss[-1], root=root)
    assert out["schema_version"] == experience.OUTCOME_SCHEMA_VERSION

    rows = [r for r in store.read_outcomes(root) if r["horizon_days"] == 1]
    assert len(rows) == 1
    r = rows[0]
    assert r["basis"] == experience.FORECAST_BASIS
    assert r["execution_basis"] == experience.EXECUTION_BASIS
    assert r["excess_return"] == pytest.approx(0.10)
    assert r["outcome_class"] == "GOOD_CALL"
    assert r["execution_excess_return"] == pytest.approx(0.0)
    assert r["execution_outcome_class"] == "BAD_CALL"
    assert r["traded"] is True


def test_row_waits_for_the_execution_window_not_just_the_forecast_one(root):
    """h=1 needs sessions d0, d0+1 (forecast) AND d0+2 (execution exit).

    The files are append-only: a row written while its execution leg is still
    pending could never be completed later, only contradicted by a second row.
    """
    ss = _weekdays(3)
    px = {t: {s: 100.0 for s in ss} for t in ("SPY", "AAA")}
    panel = DictPanel(ss, px)
    _exp(root, "AAA", "ENTER", ss[0])

    # today = ss[1]: the forecast window has closed, the execution one has not.
    assert experience.mature_outcomes(panel, today=ss[1], root=root)["resolved"] == 0
    assert experience.mature_outcomes(panel, today=ss[2], root=root)["resolved"] == 1


def test_price_holes_are_counted_not_hidden(root):
    ss = _weekdays(6)
    closes = {"SPY": {s: 100.0 for s in ss}, "DARK": {}}
    panel = DictPanel(ss, closes)
    _exp(root, "DARK", "ENTER", ss[0])
    out = experience.mature_outcomes(panel, today=ss[-1], root=root)
    assert out["resolved"] > 0 and out["price_holes"] == out["resolved"]
    assert all(r["price_missing"] for r in store.read_outcomes(root))
    assert all(r["outcome_class"] == "UNRESOLVED"
               for r in store.read_outcomes(root))


# ── perception grading ──────────────────────────────────────────────────────
def test_matured_llm_prediction_gets_outcome_and_brier(root):
    from backend.services import belief_state as B

    ss = _weekdays(40)
    closes = {"SPY": {s: 100.0 for s in ss},
              "WIN": {s: 100.0 + i for i, s in enumerate(ss)}}
    panel = DictPanel(ss, closes)

    rec = B.make_prediction(
        ticker="WIN", specialist="arena:perception:v1",
        observable=B.Observable.BEATS_BENCHMARK, horizon_days=20,
        probability=0.8, benchmark="SPY", thesis="up", counter_thesis="down",
        next_observable="n", model="test", model_version="v1", prompt="p",
        input_snapshot={"a": 1}, prior=0.6, posterior=0.8, arm="arena",
        made_at=f"{ss[0]}T21:00:00+00:00")
    B.append([rec], store.predictions_path(root))

    out = experience.resolve_perceptions(panel, today=ss[-1], root=root)
    assert out["status"] == "ok" and out["newly_resolved"] == 1
    graded = store._read_jsonl(store.predictions_path(root))[0]
    assert graded["outcome"] == 1                       # WIN beat flat SPY
    assert graded["brier"] == pytest.approx((0.8 - 1) ** 2)
    assert graded["resolved_at"]


def test_perception_grading_says_so_when_it_has_no_prices(root, caplog):
    from backend.services import belief_state as B

    ss = _weekdays(40)
    panel = DictPanel(ss, {})           # no prices at all
    rec = B.make_prediction(
        ticker="WIN", specialist="arena:perception:v1",
        observable=B.Observable.BEATS_BENCHMARK, horizon_days=20,
        probability=0.8, benchmark="SPY", thesis="up", counter_thesis="down",
        next_observable="n", model="test", model_version="v1", prompt="p",
        input_snapshot={"a": 1}, prior=0.6, posterior=0.8,
        made_at=f"{ss[0]}T21:00:00+00:00")
    B.append([rec], store.predictions_path(root))
    out = experience.resolve_perceptions(panel, today=ss[-1], root=root)
    assert out["status"] == "no_price_frame" and out["newly_resolved"] == 0


def test_perception_grading_never_touches_the_research_ledger(root, monkeypatch):
    """The arena ledger path is the ONLY path this function may write."""
    from backend.services import belief_state as B

    calls = {}

    def _spy(prices, path=None, **kw):
        calls["path"] = path
        return {"newly_resolved": 0}

    monkeypatch.setattr(B, "resolve_all", _spy)
    ss = _weekdays(10)
    closes = {"SPY": {s: 100.0 for s in ss}, "AAA": {s: 100.0 for s in ss}}
    store._append_jsonl(store.predictions_path(root),
                        [{"ticker": "AAA", "benchmark": "SPY"}])
    experience.resolve_perceptions(DictPanel(ss, closes), today=ss[-1],
                                   root=root)
    assert calls["path"] == store.predictions_path(root)
    assert calls["path"] != B.PREDICTIONS


# ── reliability ─────────────────────────────────────────────────────────────
def _bulk(root, n, *, action="ENTER", ticker="AAA", drift=1.0):
    """n experiences on n distinct sessions, all resolvable."""
    ss = _weekdays(n + 200)
    closes = {"SPY": {s: 100.0 for s in ss},
              ticker: {s: 100.0 * (drift ** i) for i, s in enumerate(ss)}}
    panel = DictPanel(ss, closes)
    for i in range(n):
        _exp(root, ticker, action, ss[i], is_hash=f"H{i}")
    experience.mature_outcomes(panel, today=ss[-1], root=root)
    return panel, ss


def test_thin_cell_refuses_and_prints_its_n(root):
    _bulk(root, 3, drift=1.01)
    rep = reliability.decision_cells(root=root, min_n=20)
    assert rep["n_cells"] > 0
    for cell in rep["cells"].values():
        assert cell["verdict"] == "REFUSED_THIN"
        assert "hit_rate" not in cell           # no rate over three events
        assert cell["n"] < 20 and cell["min_n"] == 20
    assert rep["n_cells_reported"] == 0


def test_a_fat_cell_reports_with_the_right_sign(root):
    _bulk(root, 25, drift=1.01)                 # the name always beats flat SPY
    rep = reliability.decision_cells(root=root, min_n=20)
    fat = [c for c in rep["cells"].values() if c["verdict"] == "REPORTED"]
    assert fat, rep["cells"]
    for c in fat:
        assert c["hit_rate"] == 1.0
        assert c["mean_signed_excess"] > 0      # taking it was right


def test_passing_on_a_winner_scores_as_a_bad_pass(root):
    _bulk(root, 25, action="REJECT", drift=1.01)
    rep = reliability.decision_cells(root=root, min_n=20)
    fat = [c for c in rep["cells"].values() if c["verdict"] == "REPORTED"]
    assert fat
    for c in fat:
        assert c["hit_rate"] == 0.0             # every pass was a BAD_PASS
        assert c["mean_signed_excess"] < 0      # passing destroyed value


def test_reliability_refuses_to_pool_legacy_outcome_rows(root):
    _bulk(root, 25, drift=1.01)
    store.append_outcomes([{  # a v1-shaped row, as the first build wrote them
        "experience_id": "legacy", "book_id": "ENGINE_BASELINE_v1",
        "entity_key": "AAA", "action": "ENTER", "horizon_days": 21,
        "decision_date": "2026-01-05", "excess_return": 0.5,
        "outcome_class": "GOOD_CALL"}], root)
    rep = reliability.decision_cells(root=root, min_n=20)
    assert rep["n_rows_dropped_legacy_schema"] == 1


def test_execution_leg_is_reportable_separately(root):
    _bulk(root, 25, drift=1.01)
    f = reliability.decision_cells(root=root, leg="forecast", min_n=20)
    x = reliability.decision_cells(root=root, leg="execution", min_n=20)
    assert f["basis"] != x["basis"]
    assert f["basis"] == experience.FORECAST_BASIS


def test_vol_state_labels_come_from_the_frozen_snapshot(root):
    day = "2026-08-19"
    names = {f"T{i}": {"status": "ok", "vol63": 0.01 * (i + 1)}
             for i in range(9)}
    store.freeze_snapshot(day, {"date": day, "names": names}, root)
    labels = reliability.state_labels(root)[day]
    assert labels["T0"] == "LOW_VOL" and labels["T8"] == "HIGH_VOL"
    assert set(labels.values()) <= set(reliability.VOL_STATES)


def test_snapshot_is_idempotent_per_day(root):
    _bulk(root, 25, drift=1.01)
    a = reliability.snapshot(today=date(2026, 8, 20), root=root)
    b = reliability.snapshot(today=date(2026, 8, 20), root=root)
    assert a["status"] == "ok" and b["status"] == "already_snapshotted"
    assert len(store.read_reliability(root)) == 1


def test_forecast_cells_refuse_a_degenerate_base_rate(root):
    from backend.services import belief_state as B

    ss = _weekdays(60)
    rows = []
    for i in range(25):
        rec = B.make_prediction(
            ticker="AAA", specialist="arena:perception:v1",
            observable=B.Observable.BEATS_BENCHMARK, horizon_days=20,
            probability=0.7, benchmark="SPY", thesis="t", counter_thesis="c",
            next_observable="n", model="test", model_version="v1",
            prompt=f"p{i}", input_snapshot={"i": i},
            made_at=f"{ss[i]}T21:00:00+00:00")
        d = rec.__dict__ if hasattr(rec, "__dict__") else dict(rec)
        d = dict(d)
        d["outcome"] = 1                      # every single one resolved TRUE
        d["brier"] = (0.7 - 1) ** 2
        rows.append(d)
    store._append_jsonl(store.predictions_path(root), rows)
    rep = reliability.forecast_cells(root=root, min_n=20)
    verdicts = {c["verdict"] for c in rep["cells"].values()}
    assert verdicts == {"REFUSED_DEGENERATE"}


# ── regret ──────────────────────────────────────────────────────────────────
def _regret_fixture(root, reject_drift, chosen_drift):
    ss = _weekdays(30)
    closes = {"SPY": {s: 100.0 for s in ss},
              "CHOSE": {s: 100.0 * (chosen_drift ** i) for i, s in enumerate(ss)},
              "PASSED": {s: 100.0 * (reject_drift ** i) for i, s in enumerate(ss)}}
    panel = DictPanel(ss, closes)
    _exp(root, "CHOSE", "ENTER", ss[0], rank=1)
    _exp(root, "PASSED", "REJECT", ss[0], rank=13, alt="CHOSE")
    experience.mature_outcomes(panel, today=ss[-1], root=root)
    return ss


def test_good_pass_and_bad_pass_produce_correctly_signed_regret(root, tmp_path):
    # the passed name LOST while the chosen name won -> passing was right
    _regret_fixture(root, reject_drift=0.99, chosen_drift=1.01)
    good = regret.pairs(root=root)
    assert good["n_pairs"] > 0
    assert all(r["regret_vs_basket"] < 0 for r in good["rows"])
    assert all(r["regret_vs_named"] < 0 for r in good["rows"])

    # the passed name WON while the chosen name lost -> passing cost money
    other = tmp_path / "arena2"
    _regret_fixture(other, reject_drift=1.01, chosen_drift=0.99)
    bad = regret.pairs(root=other)
    assert all(r["regret_vs_basket"] > 0 for r in bad["rows"])
    assert all(r["regret_vs_named"] > 0 for r in bad["rows"])


def test_unmatched_regret_legs_are_reported_not_dropped(root):
    ss = _weekdays(30)
    closes = {"SPY": {s: 100.0 for s in ss},
              "PASSED": {s: 100.0 for s in ss}}
    panel = DictPanel(ss, closes)
    # a REJECT with no chosen leg in its information state at all
    _exp(root, "PASSED", "REJECT", ss[0], is_hash="LONELY", alt="GHOST")
    experience.mature_outcomes(panel, today=ss[-1], root=root)
    out = regret.pairs(root=root)
    assert out["n_pairs"] == 0
    assert out["unpaired"]["no_chosen_leg_in_group"] > 0


def test_regret_summary_refuses_a_thin_cell(root):
    _regret_fixture(root, reject_drift=1.01, chosen_drift=0.99)
    s = regret.summary(root=root, min_n=20)
    assert s["cells"]
    assert all(c["verdict"] == "REFUSED_THIN" for c in s["cells"].values())
    assert all("mean_regret_vs_basket" not in c for c in s["cells"].values())


def test_regret_named_alternative_absence_is_counted(root):
    ss = _weekdays(30)
    closes = {"SPY": {s: 100.0 for s in ss},
              "CHOSE": {s: 100.0 for s in ss},
              "PASSED": {s: 100.0 for s in ss}}
    panel = DictPanel(ss, closes)
    _exp(root, "CHOSE", "ENTER", ss[0], rank=1)
    _exp(root, "PASSED", "REJECT", ss[0], rank=13, alt="NOT_IN_THIS_BOOK")
    experience.mature_outcomes(panel, today=ss[-1], root=root)
    out = regret.pairs(root=root)
    assert out["unpaired"]["named_alternative_absent"] > 0
    assert all(r["regret_vs_named"] is None for r in out["rows"])
    assert all(r["regret_vs_basket"] is not None for r in out["rows"])


# ── the acceptance test: one pass, no manual calls ─────────────────────────
def test_a_full_day_runs_decision_to_reliability_to_regret(root, tmp_path,
                                                           monkeypatch):
    """decision -> prediction -> experience -> maturation -> grading ->
    reliability -> regret, driven ONLY by engine.run_daily().

    Before this session the chain stopped at "experience": minted predictions
    never resolved and nothing counted. If this test ever needs a manual call
    inserted between two steps, the loop is open again.
    """
    from backend.db import get_connection, snapshot as pit_snapshot
    from backend.services import belief_state as B
    from backend.services.arena import discovery, engine

    tickers = [f"T{i:02d}" for i in range(20)]
    ss = _weekdays(300)
    closes = {"SPY": {s: 100.0 for s in ss}, "QQQ": {s: 100.0 for s in ss}}
    for i, t in enumerate(tickers):
        drift = 1.0 + 0.0005 * (i - 10)
        closes[t] = {s: 50.0 * (drift ** j) for j, s in enumerate(ss)}
    panel = DictPanel(ss, closes)

    db = tmp_path / "pit.db"
    conn = get_connection(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL, as_of TEXT NOT NULL, observed_at TEXT NOT NULL,
            value REAL, payload TEXT, source TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0,
            UNIQUE(key, as_of, observed_at))""")
    obs = ss[-5]
    for i, t in enumerate(tickers):
        pit_snapshot(conn, f"multifactor_score:{t}", str(obs),
                     float(len(tickers) - i), source="test",
                     observed_at=f"{obs}T20:00:00+00:00")
    conn.commit()
    conn.close()

    monkeypatch.setattr(discovery, "candidate_universe",
                        lambda extra=None: sorted(set(tickers) | set(extra or [])))
    monkeypatch.setattr(
        "backend.services.arena.beliefs.daily_review",
        lambda day_state, *, book_id, holdings, challengers, llm_cfg,
        root=None, event_context=None: {
            "tilts": {}, "reviewed": [], "status": "stubbed_offline",
            "attempted": 0, "failed": 0})
    engine.seed_all(root=root)

    # A perception minted on an earlier session, exactly as the live path does.
    B.append([B.make_prediction(
        ticker="T00", specialist="arena:perception:v1",
        observable=B.Observable.BEATS_BENCHMARK, horizon_days=20,
        probability=0.7, benchmark="SPY", thesis="t", counter_thesis="c",
        next_observable="n", model="test", model_version="arena-perception-v1",
        prompt="p", input_snapshot={"x": 1}, prior=0.5, posterior=0.7,
        arm="arena", made_at=f"{ss[-60]}T21:00:00+00:00")],
        store.predictions_path(root))

    # Four sessions: the first decides, the second fills and marks, and by the
    # fourth the h=1 execution window of the first day's decisions has closed.
    first = engine.run_daily(ss[-4], panel=panel, root=root, db_path=db)
    engine.run_daily(ss[-3], panel=panel, root=root, db_path=db)
    engine.run_daily(ss[-2], panel=panel, root=root, db_path=db)
    summary = engine.run_daily(ss[-1], panel=panel, root=root, db_path=db)

    assert summary["status"] == "ok"
    assert store.read_experiences(root), "no experiences were written"
    # the LLM ledger was graded by the pass itself, not by a manual call
    assert first["perception_grading"]["newly_resolved"] == 1
    # ...and grading is not repeated once a record carries an outcome
    assert summary["perception_grading"]["newly_resolved"] == 0
    graded = store._read_jsonl(store.predictions_path(root))[0]
    assert graded["outcome"] is not None and graded["brier"] is not None
    # and the reliability snapshot exists for the session
    assert summary["reliability"]["status"] == "ok"
    assert store.read_reliability(root), "no reliability row appended"

    # both readers run over what the pass produced, with honest denominators
    rel = reliability.decision_cells(root=root)
    assert rel["n_cells"] >= 1
    assert all(c["verdict"] == "REFUSED_THIN" for c in rel["cells"].values()), \
        "a two-day-old arena must not be reporting rates"
    reg = regret.summary(root=root)
    assert "cells" in reg and "unpaired" in reg


# ── FEATURE-COVERAGE-AUDIT-1: coverage must not decide the ranking ─────────
def test_coverage_normalization_stops_thin_names_owning_the_tail():
    """Two names with identical evidence STRENGTH must score identically,
    whether that evidence arrived as one factor or as six.

    Under the plain weighted mean, a name at +2z on its single factor scores
    +2.0 while a name at +2z on all six scores +2.0 too — but only because
    every factor agrees. Give the six-factor name mixed signals of the same
    average and averaging shrinks it, which is the defect. What must hold is
    that a fully-covered name at the SAME per-factor level is not penalised
    for having been measured more.
    """
    from backend.services.arena import discovery

    names = {}
    # 30 background names with momentum only, spread across the z range
    for i in range(30):
        names[f"BG{i:02d}"] = {"status": "ok", "close": 100.0,
                               "scores": {"mom_12_1": 0.001 * (i - 15)}}
    # THIN and FULL sit at the same place in every factor they have
    names["THIN"] = {"status": "ok", "close": 100.0,
                     "scores": {"mom_12_1": 0.05}}
    full = {"mom_12_1": 0.05}
    for f in ("multifactor", "revisions", "insider_opp", "pead", "quality"):
        full[f] = 0.05
        for i in range(30):
            names[f"BG{i:02d}"]["scores"][f] = 0.001 * (i - 15)
    names["FULL"] = {"status": "ok", "close": 100.0, "scores": full}

    discovery._add_arena_composite(names)
    thin = names["THIN"]["scores"]
    fullr = names["FULL"]["scores"]
    assert thin["coverage_n"] == 1 and fullr["coverage_n"] == 6
    # the well-measured name is NOT below the thin one at equal evidence
    assert fullr["arena_composite"] >= thin["arena_composite"]
    # both readings are kept so the change stays auditable
    assert fullr["arena_composite_raw_mean"] is not None


def test_coverage_vector_and_histogram_are_frozen_into_the_state():
    from backend.services.arena import discovery

    names = {"A": {"status": "ok", "close": 10.0,
                   "scores": {"mom_12_1": 0.1, "quality": 0.2}},
             "B": {"status": "ok", "close": 10.0, "scores": {"mom_12_1": -0.1}},
             "C": {"status": "no_price"}}
    discovery._add_arena_composite(names)
    assert names["A"]["scores"]["coverage"] == ["mom_12_1", "quality"]
    assert names["B"]["scores"]["coverage_n"] == 1
    assert "coverage" not in names["C"].get("scores", {})


def test_a_name_with_no_factors_scores_none_not_zero():
    from backend.services.arena import discovery

    names = {"A": {"status": "ok", "close": 10.0, "scores": {"mom_12_1": 0.1}},
             "DARK": {"status": "ok", "close": 10.0,
                      "scores": {"mom_12_1": None}}}
    discovery._add_arena_composite(names)
    assert names["DARK"]["scores"]["arena_composite"] is None
    assert names["DARK"]["scores"]["coverage_n"] == 0


def test_correlation_shrinks_to_the_predecessor_when_there_is_no_evidence():
    """With <3 shared observations the correlation is 1.0, and rho=1 makes the
    normalized composite identical to the plain weighted mean. The estimator
    degrades to what it replaced, never to a third thing."""
    from backend.services.arena import discovery

    z = {"mom_12_1": {"A": 1.0, "B": -1.0}, "quality": {"A": 0.5}}
    corr = discovery._pairwise_corr(z, list(discovery.COMPOSITE_WEIGHTS))
    assert corr[0][1] == 1.0


# ── segment identity covers the estimator, not just the YAML ───────────────
def test_policy_fingerprint_covers_the_composite_not_only_the_yaml(monkeypatch):
    from backend.services.arena import discovery
    from backend.services.arena import spec as spec_mod

    before = spec_mod.policy_fingerprint()
    monkeypatch.setattr(discovery, "COMPOSITE_VERSION", "something_else@9")
    after = spec_mod.policy_fingerprint()
    assert before != after
    assert spec_mod.config_hash() == spec_mod.config_hash()  # YAML untouched


def test_a_changed_estimator_refuses_to_run_under_the_old_seed(root,
                                                               monkeypatch):
    from backend.services.arena import discovery, engine
    from backend.services.arena import spec as spec_mod

    engine.seed_all(root=root)
    monkeypatch.setattr(discovery, "COMPOSITE_VERSION", "changed@9")
    spec = spec_mod.active_specs()["ENGINE_BASELINE_v1"]
    with pytest.raises(store.ConfigDrift, match="SELECTION ESTIMATOR"):
        store.assert_config_current(spec, root=root)


def test_seed_records_the_policy_fingerprint(root):
    from backend.services.arena import engine
    from backend.services.arena import spec as spec_mod

    engine.seed_all(root=root)
    seed = store.read_seed("ENGINE_BASELINE_v1", root)
    assert seed["policy_fingerprint"] == spec_mod.policy_fingerprint()


# ── P1: the daily belief review, and where the prior comes from ────────────
class _FakeLLM:
    """A model that answers with whatever posterior the test hands it, and
    records every prompt it saw."""

    def __init__(self, posteriors, thesis_status="INTACT"):
        self.posteriors = list(posteriors)
        self.prompts = []
        self.status = thesis_status

    def available(self):
        return True, "ok"

    def ask(self, prompt, **kw):
        self.prompts.append(prompt)
        self.kwargs = kw
        p = self.posteriors.pop(0) if self.posteriors else 0.5
        return {"text": json.dumps({
            "posterior": p, "evidence": "e", "interpretation": "i",
            "thesis": "t", "thesis_status": self.status,
            "invalidation": "inv", "next_observable": "next"}),
            "call": {"model": "fake"}}

    @staticmethod
    def parse_json_block(text):
        return json.loads(text)


def _install_llm(monkeypatch, fake):
    import sys
    import types
    mod = types.ModuleType("backend.services.llm_research")
    mod.available = fake.available
    mod.ask = fake.ask
    mod.parse_json_block = fake.parse_json_block
    monkeypatch.setitem(sys.modules, "backend.services.llm_research", mod)


def _day_state(tickers, day="2026-08-20", score=1.0):
    return {"date": day, "names": {
        t: {"status": "ok", "close": 100.0, "ret21": 0.01, "vol63": 0.02,
            "streak_up": 1, "scores": {"arena_composite": score,
                                       "coverage": ["mom_12_1"]}}
        for t in tickers}}


def test_first_look_opens_at_the_declared_prior_and_is_an_initiation(
        root, monkeypatch):
    from backend.services.arena import beliefs

    fake = _FakeLLM([0.7])
    _install_llm(monkeypatch, fake)
    out = beliefs.daily_review(_day_state(["AAA"]), book_id="B",
                               holdings={"AAA"}, challengers=[],
                               llm_cfg={"max_names_per_day": 5}, root=root)
    assert out["status"] == "ok" and out["initiations"] == 1
    row = store.read_beliefs(root)[0]
    assert row["prior"] == beliefs.OPENING_PRIOR
    assert row["prior_source"] == "DECLARED_OPENING_PRIOR"
    assert row["is_initiation"] is True
    # an opening LEVEL is not a belief CHANGE, so it may not tilt anything
    assert out["tilts"] == {}


def test_the_prior_comes_from_the_ledger_not_from_the_model(root, monkeypatch):
    """Day 2's prompt must contain day 1's posterior, and the minted record's
    prior must equal it. The model is never asked what it used to think."""
    from backend.services.arena import beliefs

    fake = _FakeLLM([0.7, 0.4])
    _install_llm(monkeypatch, fake)
    cfg = {"max_names_per_day": 5}
    beliefs.daily_review(_day_state(["AAA"], day="2026-08-19"), book_id="B",
                         holdings={"AAA"}, challengers=[], llm_cfg=cfg,
                         root=root)
    out = beliefs.daily_review(_day_state(["AAA"], day="2026-08-20"),
                               book_id="B", holdings={"AAA"}, challengers=[],
                               llm_cfg=cfg, root=root)

    rows = store.read_beliefs(root)
    assert len(rows) == 2
    assert rows[1]["prior"] == pytest.approx(0.7)      # yesterday's posterior
    assert rows[1]["prior_source"] == "LEDGER"
    assert rows[1]["belief_change"] == pytest.approx(-0.3)
    assert '"prior": 0.7' in fake.prompts[1]
    assert "from the ledger, not from you" in fake.prompts[1]
    # and the model is instructed it may not revise what it was handed
    assert "PRIOR IS GIVEN TO YOU" in fake.kwargs["schema_hint"]
    assert "may not restate, revise" in fake.kwargs["schema_hint"]
    # a real belief change tilts; its sign follows the change
    assert out["tilts"]["AAA"] < 1.0

    minted = store._read_jsonl(store.predictions_path(root))
    assert minted[1]["prior"] == pytest.approx(0.7)
    assert minted[1]["posterior"] == pytest.approx(0.4)
    assert minted[1]["probability"] == pytest.approx(0.4)


def test_holdings_are_reviewed_before_challengers_and_never_dropped(root):
    from backend.services.arena import beliefs

    ds = _day_state([f"T{i}" for i in range(10)])
    todo = beliefs.review_list(ds, holdings={"T7", "T8"},
                               challengers=["T0", "T1", "T2"],
                               beliefs={}, book_id="B", max_names=3)
    assert [x["ticker"] for x in todo][:2] == ["T7", "T8"]
    assert todo[0]["reason"] == "HOLDING"
    assert todo[2]["reason"] == "CHALLENGER"


def test_a_moved_score_earns_a_review_even_when_not_held_or_ranked(root):
    from backend.services.arena import beliefs

    ds = _day_state(["AAA", "BBB"])
    ds["names"]["BBB"]["scores"]["arena_composite"] = 3.0
    prior_rows = {("B", "BBB"): {"score_at_review": 0.1, "posterior": 0.5}}
    todo = beliefs.review_list(ds, holdings=set(), challengers=[],
                               beliefs=prior_rows, book_id="B", max_names=5)
    assert [x["ticker"] for x in todo] == ["BBB"]
    assert todo[0]["reason"] == "STATE_CHANGE"


def test_no_llm_is_a_status_never_a_silent_skip(root, monkeypatch):
    import sys
    import types

    from backend.services.arena import beliefs
    mod = types.ModuleType("backend.services.llm_research")
    mod.available = lambda: (False, "no api key")
    mod.ask = None
    mod.parse_json_block = None
    monkeypatch.setitem(sys.modules, "backend.services.llm_research", mod)
    out = beliefs.daily_review(_day_state(["AAA"]), book_id="B",
                               holdings={"AAA"}, challengers=[],
                               llm_cfg={}, root=root)
    assert out["status"].startswith("llm_unavailable")
    assert store.read_beliefs(root) == []


def test_an_unparseable_reply_fails_one_name_not_the_pass(root, monkeypatch):
    from backend.services.arena import beliefs

    fake = _FakeLLM([0.7])

    def _bad_then_good(prompt, **kw):
        if "AAA" in prompt:
            return {"text": "not json at all", "call": {"model": "fake"}}
        return _FakeLLM.ask(fake, prompt, **kw)

    _install_llm(monkeypatch, fake)
    import sys
    sys.modules["backend.services.llm_research"].ask = _bad_then_good
    sys.modules["backend.services.llm_research"].parse_json_block = (
        lambda t: None if t == "not json at all" else json.loads(t))

    out = beliefs.daily_review(_day_state(["AAA", "BBB"]), book_id="B",
                               holdings={"AAA", "BBB"}, challengers=[],
                               llm_cfg={"max_names_per_day": 5}, root=root)
    assert out["failed"] == 1 and out["written"] == 1
    assert [r["ticker"] for r in store.read_beliefs(root)] == ["BBB"]


def test_review_runs_on_a_session_with_no_decision(root, tmp_path, monkeypatch):
    """The point of P1: the book thinks on days it does not trade."""
    from backend.services.arena import beliefs, engine

    seen = {"calls": 0}

    def _spy(day_state, *, book_id, holdings, challengers, llm_cfg, root=None,
             event_context=None):
        seen["calls"] += 1
        seen["event_context"] = event_context
        return {"tilts": {}, "reviewed": [], "status": "ok", "attempted": 0,
                "failed": 0}

    monkeypatch.setattr(beliefs, "daily_review", _spy)
    spec = __import__("backend.services.arena.spec",
                      fromlist=["x"]).active_specs()["LLM_PERCEPTION_v1"]
    ss = _weekdays(10)
    closes = {"SPY": {s: 100.0 for s in ss}}
    panel = DictPanel(ss, closes)
    engine.seed_all(root=root)
    ds = _day_state(["AAA"], day=str(ss[-1]))
    # a state too thin to decide from: the decision refuses, the review runs
    r = engine.run_book(spec, panel, ss[-1], ds, "hash", root=root)
    assert seen["calls"] == 1
    assert r["decision"]["status"] == "insufficient_breadth"
    assert r["belief_review"]["status"] == "ok"


# ── a degraded fetch is a different universe, not a thin day ───────────────
def test_a_partial_price_fetch_holds_instead_of_ranking_a_smaller_world(root):
    """20 of 180 names priced still yields 12 chosen, so insufficient_breadth
    never fires — but those 12 were ranked by z-scores over a cross-section
    that is not the declared universe."""
    from backend.services.arena import engine
    from backend.services.arena import spec as spec_mod

    spec = spec_mod.active_specs()["ENGINE_BASELINE_v1"]
    ds = _day_state([f"T{i:02d}" for i in range(20)])
    ds["universe_n"] = 180
    ds["priced_n"] = 20
    ds["priced_fraction"] = 20 / 180
    for i, t in enumerate(ds["names"]):
        ds["names"][t]["scores"]["arena_composite"] = float(20 - i)
        ds["names"][t]["vol63"] = 0.02

    book = {"cash": 100000.0, "positions": {}, "pending": [],
            "session_index": 0, "last_rebalance_month": None,
            "last_marked": None}
    dec = engine._decide(spec, book, ds, "hash", root=root)
    assert dec["status"] == "degraded_information_state"
    assert dec["priced_fraction"] == pytest.approx(20 / 180)
    assert book["pending"] == []          # nothing was queued


def test_a_full_fetch_decides_normally(root):
    from backend.services.arena import engine
    from backend.services.arena import spec as spec_mod

    spec = spec_mod.active_specs()["ENGINE_BASELINE_v1"]
    ds = _day_state([f"T{i:02d}" for i in range(20)])
    ds["universe_n"] = 20
    ds["priced_n"] = 20
    ds["priced_fraction"] = 1.0
    for i, t in enumerate(ds["names"]):
        ds["names"][t]["scores"]["arena_composite"] = float(20 - i)
        ds["names"][t]["vol63"] = 0.02
    book = {"cash": 100000.0, "positions": {}, "pending": [],
            "session_index": 0, "last_rebalance_month": None,
            "last_marked": None}
    dec = engine._decide(spec, book, ds, "hash", root=root)
    assert dec["status"] == "decided" and dec["orders_queued"] > 0


def test_priced_fraction_is_frozen_into_the_state(panel_free_state=None):
    from backend.services.arena import discovery

    class _P:
        def sessions(self):
            return [date(2026, 8, 19)]

        def close_price(self, t, d):
            return 100.0 if t in ("A", "B") else None

        def open_price(self, t, d):
            return 100.0

        def close_history(self, t, d, n):
            return [100.0] * 300 if t in ("A", "B") else []

    class _Conn:
        def close(self):
            pass

    state = discovery._build_day_state_with_conn(
        date(2026, 8, 19), _P(), ["A", "B", "C", "D"], _Conn(),
        "2026-08-19T23:59:59+00:00")
    assert state["priced_n"] == 2
    assert state["priced_fraction"] == pytest.approx(0.5)


def test_a_yaml_key_the_engine_never_reads_refuses_at_load(tmp_path):
    """A setting that changes nothing must not sit in the file looking live."""
    from backend.services.arena.spec import SpecError, load_specs

    p = tmp_path / "books.yaml"
    p.write_text("schema: arena-v1\ndefaults:\n  invented_knob: 7\n"
                 "books:\n  X_v1:\n    sizing: equal_weight\n",
                 encoding="utf-8")
    with pytest.raises(SpecError, match="neither read by the engine"):
        load_specs(p)


def test_an_unknown_llm_block_key_refuses_at_load(tmp_path):
    from backend.services.arena.spec import SpecError, load_specs

    p = tmp_path / "books.yaml"
    p.write_text("schema: arena-v1\ndefaults: {}\nbooks:\n  X_v1:\n"
                 "    sizing: equal_weight\n    llm:\n      temperature: 0.9\n",
                 encoding="utf-8")
    with pytest.raises(SpecError, match="looking live"):
        load_specs(p)


def test_the_shipped_yaml_declares_every_key_it_carries():
    """The real file must satisfy the contract it just imposed."""
    from backend.services.arena import spec as spec_mod
    assert spec_mod.active_specs()


# ── trackers: discovery and context, never a score ─────────────────────────
class _TrackPanel(DictPanel):
    def __init__(self, sessions, closes, opens=None, volumes=None):
        super().__init__(sessions, closes, opens)
        self._volumes = volumes or {}

    def volume_history(self, ticker, day, n):
        v = self._volumes.get(ticker.upper(), {})
        return [v[s] for s in self._sessions if s <= day and s in v][-n:]


def _flat_panel(tickers, n=300, spike=None):
    ss = _weekdays(n)
    closes, vols = {}, {}
    for i, t in enumerate(tickers):
        closes[t] = {s: 100.0 + 0.01 * i * j for j, s in enumerate(ss)}
        vols[t] = {s: 1_000_000.0 for s in ss}
    closes["SPY"] = {s: 100.0 for s in ss}
    vols["SPY"] = {s: 1_000_000.0 for s in ss}
    if spike:
        t = spike
        vols[t][ss[-1]] = 50_000_000.0        # a 50x volume day
        closes[t][ss[-1]] = closes[t][ss[-2]] * 1.30
    return _TrackPanel(ss, closes, volumes=vols), ss


def test_tracker_features_are_none_when_absent_never_zero():
    from backend.services.arena import trackers

    f = trackers.name_features([], [], None)
    assert set(f) == set(trackers.CONTEXT_FEATURES)
    assert all(v is None for v in f.values())


def test_no_tracker_feature_is_ever_a_composite_factor():
    """The contract that keeps a Holm-surviving ANTI-signal out of the score."""
    from backend.services.arena import discovery, trackers

    assert not (set(trackers.CONTEXT_FEATURES)
                & set(discovery.COMPOSITE_WEIGHTS))


def test_volume_spike_and_abnormal_move_fire_observations():
    from backend.services.arena import trackers

    names = [f"N{i:02d}" for i in range(20)]
    panel, ss = _flat_panel(names, spike="N07")
    out = trackers.observe(ss[-1], panel, names)
    kinds = {o["kind"] for o in out["observations"] if o["ticker"] == "N07"}
    assert "VOLUME_SPIKE" in kinds
    assert "ABNORMAL_MOVE_UP" in kinds
    assert out["scanned_n"] == 20 and out["priced_n"] == 20


def test_a_name_outside_the_core_universe_can_be_nominated():
    """The acceptance test for DISCOVERY: a tracker event must be able to pull
    a ticker the watchlist never contained into the candidate set."""
    from backend.services.arena import trackers

    names = [f"N{i:02d}" for i in range(20)]
    panel, ss = _flat_panel(names, spike="N07")
    out = trackers.observe(ss[-1], panel, names)
    core = {n for n in names if n != "N07"}     # N07 is NOT in the core
    noms = trackers.nominations(out["observations"], core=core)
    assert [n["ticker"] for n in noms] == ["N07"]
    assert noms[0]["reason"] in trackers.OBSERVATION_KINDS
    assert noms[0]["observation"]["ticker"] == "N07"   # the reason is attached


def test_nominations_never_re_nominate_a_core_name():
    from backend.services.arena import trackers

    names = [f"N{i:02d}" for i in range(20)]
    panel, ss = _flat_panel(names, spike="N07")
    out = trackers.observe(ss[-1], panel, names)
    noms = trackers.nominations(out["observations"], core=set(names))
    assert noms == []


def test_nomination_cap_truncates_the_weakest_not_the_alphabet():
    from backend.services.arena import trackers

    obs = [{"kind": "VOLUME_SPIKE", "ticker": "AAA", "value": 1.1,
            "threshold": 1.0},
           {"kind": "VOLUME_SPIKE", "ticker": "ZZZ", "value": 9.9,
            "threshold": 1.0}]
    noms = trackers.nominations(obs, core=set(), max_new=1)
    assert [n["ticker"] for n in noms] == ["ZZZ"]


def test_priced_fraction_uses_the_CORE_universe_not_the_scan():
    """A scan full of tickers renamed since the CRSP vintage must not be able
    to trip the degraded-fetch guard for names the books actually trade."""
    from backend.services.arena import discovery

    class _P:
        def sessions(self): return [date(2026, 8, 19)]
        def close_price(self, t, d): return 100.0 if t.startswith("CORE") else None
        def open_price(self, t, d): return 100.0
        def close_history(self, t, d, n):
            return [100.0] * 300 if t.startswith("CORE") else []
        def volume_history(self, t, d, n): return []

    class _Conn:
        def close(self): pass

    core = ["CORE1", "CORE2", "CORE3", "CORE4"]
    dead = [f"DEAD{i}" for i in range(40)]
    state = discovery._build_day_state_with_conn(
        date(2026, 8, 19), _P(), core + dead, _Conn(),
        "2026-08-19T23:59:59+00:00", core=core, scan=dead)
    assert state["core_n"] == 4 and state["core_priced_n"] == 4
    assert state["priced_fraction"] == 1.0      # NOT 4/44
    assert state["priced_n"] == 4               # the honest whole-set count


def test_tracker_failure_freezes_the_state_without_context_and_says_so(
        monkeypatch):
    from backend.services.arena import discovery, trackers

    def _boom(*a, **k):
        raise RuntimeError("tracker exploded")

    monkeypatch.setattr(trackers, "observe", _boom)

    class _P:
        def sessions(self): return [date(2026, 8, 19)]
        def close_price(self, t, d): return 100.0
        def open_price(self, t, d): return 100.0
        def close_history(self, t, d, n): return [100.0] * 300
        def volume_history(self, t, d, n): return []

    class _Conn:
        def close(self): pass

    state = discovery._build_day_state_with_conn(
        date(2026, 8, 19), _P(), ["A", "B"], _Conn(),
        "2026-08-19T23:59:59+00:00", core=["A", "B"], scan=[])
    assert "error" in state["trackers"]
    assert state["trackers"]["observations"] == []


def test_scan_universe_absent_source_is_loud_and_empty(monkeypatch, tmp_path):
    from backend import config as _c
    from backend.services.arena import discovery

    discovery._SCAN_CACHE.clear()
    monkeypatch.setattr(_c, "OPTIMUS_LEDGER_DIR", tmp_path)
    assert discovery.scan_universe(50) == []
    discovery._SCAN_CACHE.clear()


# ── P2: the event context, and the ablation it makes possible ──────────────
def test_the_ablation_twin_differs_by_exactly_one_rule():
    from backend.services.arena import spec as spec_mod

    specs = spec_mod.active_specs()
    a, b = specs["LLM_PERCEPTION_v1"], specs["LLM_EVENTS_v1"]
    assert a.llm_perception and b.llm_perception
    assert a.event_context is False and b.event_context is True
    for field in ("sizing", "screens", "winner_exemption", "substitution",
                  "policy_version", "llm"):
        assert getattr(a, field) == getattr(b, field), field


def test_event_context_distinguishes_no_events_from_never_looked():
    from backend.services.arena import events

    ctx = {"names": {"HAS": {"events": [{"title": "x"}], "n_events": 1,
                             "unavailable_feeds": []},
                     "QUIET": {"events": [], "n_events": 0,
                               "unavailable_feeds": ["edgar_8k"]}}}
    assert events.for_name(ctx, "HAS")["coverage"] == "FETCHED"
    quiet = events.for_name(ctx, "QUIET")
    assert quiet["coverage"] == "FETCHED_NO_EVENTS"
    assert quiet["unavailable_feeds"] == ["edgar_8k"]
    assert events.for_name(ctx, "NEVER")["coverage"] == "NOT_FETCHED"


def test_event_fetch_never_raises_and_reports_an_empty_result(monkeypatch):
    import sys
    import types

    from backend.services.arena import events
    mod = types.ModuleType("backend.services.event_intel")

    def _boom(t):
        raise RuntimeError("feed down")

    mod.get_ticker_events = _boom
    monkeypatch.setitem(sys.modules, "backend.services.event_intel", mod)
    out = events.fetch(["AAA", "BBB"])
    assert out["status"] == "empty" and out["fetched_n"] == 0
    assert set(out["errors"]) == {"AAA", "BBB"}


def test_event_context_reaches_the_prompt_and_the_frozen_snapshot(root,
                                                                  monkeypatch):
    """What the model saw must be a fact on disk: the feed is fetched live, so
    without freezing it the day could never be replayed."""
    from backend.services.arena import beliefs

    fake = _FakeLLM([0.7])
    _install_llm(monkeypatch, fake)
    ctx = {"status": "ok", "names": {
        "AAA": {"events": [{"title": "AAA announces a recall",
                            "timestamp": "2026-08-20T18:00:00+00:00",
                            "direction": "negative", "category": "legal",
                            "source": "yfinance_news", "tier": "HIGH"}],
                "n_events": 1, "unavailable_feeds": []}}}
    out = beliefs.daily_review(_day_state(["AAA"]), book_id="B",
                               holdings={"AAA"}, challengers=[],
                               llm_cfg={"max_names_per_day": 5}, root=root,
                               event_context=ctx)
    assert out["names_with_events"] == 1
    assert "EVENT CONTEXT" in fake.prompts[0]
    assert "announces a recall" in fake.prompts[0]

    row = store.read_beliefs(root)[0]
    assert row["event_coverage"] == "FETCHED" and row["n_events_shown"] == 1
    # ...and the minted prediction's input_snapshot hash covers it
    minted = store._read_jsonl(store.predictions_path(root))[0]
    assert minted["input_snapshot_hash"]


def test_numeric_only_arm_carries_no_event_block(root, monkeypatch):
    from backend.services.arena import beliefs

    fake = _FakeLLM([0.7])
    _install_llm(monkeypatch, fake)
    beliefs.daily_review(_day_state(["AAA"]), book_id="B", holdings={"AAA"},
                         challengers=[], llm_cfg={"max_names_per_day": 5},
                         root=root, event_context=None)
    assert "EVENT CONTEXT" not in fake.prompts[0]
    row = store.read_beliefs(root)[0]
    assert row["event_coverage"] == "NOT_REQUESTED"


# ── universe-wide quality: filling the factor the composite already declared ─
def _fake_quality(value=0.4, status="ok"):
    def _score(inputs):
        return {"quality_score": value, "status": status,
                "fiscal_period": "2025", "n_checks_passed": 5}
    return _score


def test_quality_refresh_is_budgeted_and_oldest_first(root):
    from backend.services.arena import fundamentals as F

    universe = [f"N{i:02d}" for i in range(10)]
    out = F.refresh(universe, budget=3, root=root,
                    fetch=lambda t: {}, score=_fake_quality())
    assert out["attempted"] == 3 and out["written"] == 3
    assert out["stale_remaining"] == 7
    assert len(F.scores(root)) == 3

    # a second pass takes the NEXT three, not the same three
    out2 = F.refresh(universe, budget=3, root=root,
                     fetch=lambda t: {}, score=_fake_quality())
    assert out2["attempted"] == 3
    assert len(F.scores(root)) == 6


def test_an_unscorable_name_stores_null_not_zero(root):
    """The scorer returns quality_score 0.0 alongside its failure status. 0.0
    is a real, mid-pack value in a z-score — the C6 lesson."""
    from backend.services.arena import fundamentals as F

    F.refresh(["BAD"], budget=5, root=root, fetch=lambda t: {},
              score=_fake_quality(0.0, "insufficient_fundamentals"))
    rec = F.cache(root)["BAD"]
    assert rec["quality_score"] is None
    assert rec["status"] == "insufficient_fundamentals"
    assert "BAD" not in F.scores(root)


def test_a_stale_quality_score_is_dropped_not_served(root):
    from backend.services.arena import fundamentals as F

    F.refresh(["OLD"], budget=1, root=root, today=date(2020, 1, 1),
              fetch=lambda t: {}, score=_fake_quality())
    assert F.scores(root, today=date(2020, 2, 1)) == {"OLD": 0.4}
    assert F.scores(root, today=date(2026, 8, 21)) == {}


def test_one_bad_name_never_kills_the_refresh(root):
    from backend.services.arena import fundamentals as F

    def _boom(t):
        if t == "BOOM":
            raise RuntimeError("yfinance exploded")
        return {}

    out = F.refresh(["AAA", "BOOM", "CCC"], budget=5, root=root,
                    fetch=_boom, score=_fake_quality())
    assert out["failed"] == 1 and out["scored"] == 2
    assert set(F.scores(root)) == {"AAA", "CCC"}


def test_quality_is_not_read_from_the_registered_pit_cross_section():
    """TRIAL-QUALITY-IC's cross-section must stay untouched: two populations
    inside one z-score is the error the coverage work exists to remove."""
    from backend.services.arena import discovery

    assert "quality" not in discovery.SCORE_PREFIXES
    assert "quality" in discovery.COMPOSITE_WEIGHTS


def test_universe_quality_raises_coverage_for_every_name(root, monkeypatch):
    from backend.services.arena import discovery, fundamentals as F

    tickers = [f"T{i:02d}" for i in range(12)]
    F.refresh(tickers, budget=99, root=root, fetch=lambda t: {},
              score=_fake_quality())
    monkeypatch.setattr(F, "scores", lambda *a, **k: F.scores.__wrapped__(root)
                        if hasattr(F.scores, "__wrapped__")
                        else {t: 0.4 for t in tickers})

    names = {t: {"status": "ok", "close": 100.0,
                 "scores": {"mom_12_1": 0.01 * i}}
             for i, t in enumerate(tickers)}
    for t, v in {t: 0.4 + 0.01 * i for i, t in enumerate(tickers)}.items():
        names[t]["scores"]["quality"] = v
    discovery._add_arena_composite(names)
    assert all(names[t]["scores"]["coverage_n"] == 2 for t in tickers)
    assert F.coverage(tickers, root)["coverage_pct"] == 100.0
