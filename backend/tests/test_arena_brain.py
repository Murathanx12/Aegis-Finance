"""ARENA brain layer — outcome legs, perception grading, reliability, regret.

Offline. Every test builds its own tmp namespace root and its own explicit
price panel, so a price fact asserted here is a fact the test wrote, not one
yfinance happened to return.
"""

from __future__ import annotations

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
        "backend.services.arena.perception.perceive",
        lambda day_state, tickers, *, llm_cfg, root=None: {
            "tilts": {}, "minted": [], "status": "stubbed_offline",
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
