"""ARENA Gen-1 (ORDER 25) — offline tests. No network, no shared state:
every test runs against a tmp_path namespace root and a tmp sqlite PIT db.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.db import get_connection, snapshot as pit_snapshot
from backend.services.arena import discovery, engine, experience, policies
from backend.services.arena import spec as spec_mod
from backend.services.arena import store


# ── fixtures ────────────────────────────────────────────────────────────────
TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH",
           "III", "JJJ", "KKK", "LLL", "MMM", "NNN", "OOO"]


def _weekday_sessions(n: int, end: date | None = None) -> list[date]:
    end = end or (date.today() - timedelta(days=1))
    out: list[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


class FakePanel:
    """Deterministic prices: each ticker drifts at its own daily rate."""

    def __init__(self, sessions: list[date], tickers=None, benchmark="SPY"):
        self._sessions = sessions
        self.benchmark = benchmark
        names = list(tickers or TICKERS)
        self._px: dict[str, dict[date, float]] = {}
        for i, t in enumerate(names + [benchmark, "QQQ"]):
            base = 50.0 + 10.0 * i
            drift = 0.001 * ((i % 5) - 2)  # -0.2% .. +0.2% per session
            px = {}
            p = base
            for s in sessions:
                p *= (1.0 + drift)
                px[s] = round(p, 4)
            self._px[t] = px

    def sessions(self) -> list[date]:
        return list(self._sessions)

    def open_price(self, ticker, day):
        c = self._px.get(ticker.upper(), {}).get(day)
        return round(c * 0.999, 4) if c else None

    def close_price(self, ticker, day):
        return self._px.get(ticker.upper(), {}).get(day)

    def close_history(self, ticker, day, n):
        px = self._px.get(ticker.upper(), {})
        upto = [px[s] for s in self._sessions if s <= day and s in px]
        return upto[-n:]


@pytest.fixture()
def sessions():
    # 300 sessions so 12-1 momentum (252 + skip) is computable near the end.
    return _weekday_sessions(300)


@pytest.fixture()
def panel(sessions):
    return FakePanel(sessions)


@pytest.fixture()
def pit_db(tmp_path, sessions):
    """A PIT db with multifactor scores observed BEFORE the last session."""
    db = tmp_path / "pit.db"
    conn = get_connection(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL, as_of TEXT NOT NULL, observed_at TEXT NOT NULL,
            value REAL, payload TEXT, source TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0,
            UNIQUE(key, as_of, observed_at))
    """)
    conn.commit()
    obs_day = sessions[-3]
    for i, t in enumerate(TICKERS):
        pit_snapshot(conn, f"multifactor_score:{t}", str(obs_day),
                     float(len(TICKERS) - i),  # AAA best, HHH worst
                     source="test",
                     observed_at=f"{obs_day}T20:00:00+00:00")
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def root(tmp_path):
    return tmp_path / "arena"


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """The daily belief review is stubbed off in engine tests — beliefs.py has
    its own tests in test_arena_brain.py."""
    monkeypatch.setattr(
        "backend.services.arena.beliefs.daily_review",
        lambda day_state, *, book_id, holdings, challengers, llm_cfg,
        root=None, event_context=None: {
            "tilts": {}, "reviewed": [], "status": "stubbed_offline",
            "attempted": 0, "failed": 0})


def _state(day, panel, pit_db, universe=None):
    return discovery.build_day_state(day, panel, universe or TICKERS,
                                     db_path=pit_db)


# ── spec ────────────────────────────────────────────────────────────────────
def test_yaml_and_code_agree_on_active_books():
    specs = spec_mod.active_specs()
    assert set(specs) == set(spec_mod.AUTHORISED_ACTIVE)
    for s in specs.values():
        assert s.validation_status == "PRODUCT_EXPERIMENT"
        assert s.config_hash == spec_mod.config_hash()


def test_control_twin_differs_by_exactly_one_rule():
    specs = spec_mod.active_specs()
    base = specs["ENGINE_BASELINE_v1"]
    assert base.sizing == "equal_weight" and not base.screens
    assert not base.llm_perception and not base.winner_exemption
    assert specs["RISK_SIZED_v1"].sizing == "inverse_trailing_vol"
    assert not specs["RISK_SIZED_v1"].screens
    assert specs["WINNER_EXEMPT_v1"].winner_exemption
    assert specs["WINNER_EXEMPT_v1"].sizing == "equal_weight"
    assert set(specs["ANTI_SIGNAL_v1"].screens) == {"streak_up_5",
                                                    "top_decile_ret21"}
    assert specs["LLM_PERCEPTION_v1"].llm_perception
    assert specs["LLM_PERCEPTION_v1"].sizing == "equal_weight"


def test_personality_overrides_apply_to_their_book_only():
    """The 2026-08-21 personality pair: concentration is a declared per-book
    axis. The override must land on its book and must NOT leak into any other
    book's view of the shared defaults."""
    specs = spec_mod.active_specs()
    assert specs["AGGRESSIVE_TOP5_v1"].top_k == 5
    assert specs["AGGRESSIVE_TOP5_v1"].max_single_name == 0.25
    assert specs["DIVERSIFIED_TOP20_v1"].top_k == 20
    # the wide book keeps the file-level cap — it only declared breadth
    assert specs["DIVERSIFIED_TOP20_v1"].max_single_name == 0.15
    # no leakage: the control twin still reads the file defaults
    assert specs["ENGINE_BASELINE_v1"].top_k == 12
    assert specs["ENGINE_BASELINE_v1"].max_single_name == 0.15


def test_personality_books_share_the_common_world():
    """Costs and benchmark are NOT overridable, so every book is judged in
    the same market. If this ever fails, the factorial is broken."""
    specs = spec_mod.active_specs()
    base = specs["ENGINE_BASELINE_v1"]
    for book_id in ("AGGRESSIVE_TOP5_v1", "DIVERSIFIED_TOP20_v1"):
        s = specs[book_id]
        assert s.cost_bps == base.cost_bps
        assert s.slippage_bps == base.slippage_bps
        assert s.benchmark == base.benchmark
        assert s.min_priced_fraction == base.min_priced_fraction


def test_non_whitelisted_override_refuses_at_load(tmp_path):
    """A book that quietly ran on cheaper fills would make the factorial
    incomparable while every hash still verified — refuse at load."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema: arena-v1\ndefaults: {}\nbooks:\n  X_v1:\n"
        "    overrides: {transaction_cost_bps: 0}\n", encoding="utf-8")
    with pytest.raises(spec_mod.SpecError):
        spec_mod.load_specs(bad)


def test_unknown_screen_refuses_at_load(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "schema: arena-v1\ndefaults: {}\nbooks:\n  X_v1:\n"
        "    screens: [made_up_screen]\n", encoding="utf-8")
    with pytest.raises(spec_mod.SpecError):
        spec_mod.load_specs(bad)


# ── store ───────────────────────────────────────────────────────────────────
def test_seed_is_idempotent_and_refuses_a_moved_inception(root):
    s = spec_mod.active_specs()["ENGINE_BASELINE_v1"]
    rec1 = store.seed_book(s, root=root)
    rec2 = store.seed_book(s, root=root)
    assert rec1["seeded_at"] == rec2["seeded_at"]
    assert rec1["simulation"] is True
    assert rec1["validation_status"] == "PRODUCT_EXPERIMENT"

    class Drifted:
        book_id = s.book_id
        config_hash = "f" * 64
    with pytest.raises(store.SeedRefused):
        store.seed_book(Drifted, root=root)


def test_snapshot_is_write_once(root):
    a = store.freeze_snapshot("2026-01-05", {"x": 1}, root=root)
    b = store.freeze_snapshot("2026-01-05", {"x": 1}, root=root)
    assert a["information_state_hash"] == b["information_state_hash"]
    with pytest.raises(store.SnapshotConflict):
        store.freeze_snapshot("2026-01-05", {"x": 2}, root=root)


# ── discovery ───────────────────────────────────────────────────────────────
def test_day_state_reads_pit_scores_leak_free(panel, pit_db, sessions):
    state = _state(sessions[-1], panel, pit_db)
    assert state["scored_n"] == len(TICKERS)
    assert state["names"]["AAA"]["scores"]["multifactor"] == float(len(TICKERS))
    assert state["names"]["AAA"]["scores"]["arena_composite"] is not None
    assert state["names"]["AAA"]["scores"]["mom_12_1"] is not None
    # A day BEFORE the observation must not see the PIT score (observed_at
    # filter) — momentum, being price-derived, is legitimately still there.
    early = _state(sessions[-10], panel, pit_db)
    assert early["names"]["AAA"]["scores"]["multifactor"] is None
    assert early["names"]["AAA"]["scores"]["mom_12_1"] is not None


def test_universe_includes_holdings():
    u = discovery.candidate_universe(extra=["zzzz"])
    assert "ZZZZ" in u


# ── policies ────────────────────────────────────────────────────────────────
def test_selection_ranks_and_keeps_rejects():
    state = {"names": {
        f"T{i}": {"status": "ok", "close": 10.0,
                  "scores": {"arena_composite": float(10 - i)}}
        for i in range(6)}}
    sel = policies.select(state, top_k=3, min_price=5.0)
    assert [c["ticker"] for c in sel.chosen] == ["T0", "T1", "T2"]
    assert sel.rejected and sel.rejected[0]["ticker"] == "T3"
    assert sel.rejected[0]["reason"] == "below_rank_cutoff"


def test_composite_blends_momentum_with_pit_families(panel, pit_db, sessions):
    """A name with only momentum still gets a composite; PIT families shift
    the blend for the names that have them."""
    state = _state(sessions[-1], panel, pit_db)
    comp = {t: state["names"][t]["scores"]["arena_composite"]
            for t in TICKERS}
    assert all(v is not None for v in comp.values())
    # AAA has the best PIT multifactor score; among names with the SAME
    # momentum drift class, AAA must outrank them.
    same_drift = [t for i, t in enumerate(TICKERS) if i % 5 == 0]  # AAA, FFF, KKK
    assert comp["AAA"] == max(comp[t] for t in same_drift)


def test_streak_screen_excludes_with_reason(panel, pit_db, sessions):
    state = _state(sessions[-1], panel, pit_db)
    # every drift>0 ticker is on a long up-streak by construction
    sel = policies.select(state, top_k=8, min_price=5.0,
                          screens=("streak_up_5",))
    screened = {e["ticker"] for e in sel.excluded
                if e["reason"] == "streak_up_5"}
    assert screened  # the up-drifters
    assert all(c["ticker"] not in screened for c in sel.chosen)


def test_inverse_vol_and_missing_vol_is_ineligible():
    state = {"names": {
        "LOWV": {"status": "ok", "close": 10.0, "vol63": 0.01},
        "HIV": {"status": "ok", "close": 10.0, "vol63": 0.04},
        "NOV": {"status": "ok", "close": 10.0, "vol63": None},
    }}
    chosen = [{"ticker": t, "rank": i + 1, "score": 1.0}
              for i, t in enumerate(["LOWV", "HIV", "NOV"])]
    w = policies.size(chosen, state, sizing="inverse_trailing_vol",
                      max_single_name=1.0)
    assert "NOV" not in w
    assert w["LOWV"] == pytest.approx(4 * w["HIV"], rel=1e-6)


def test_llm_tilt_is_bounded_and_renormalized():
    w = {"A": 0.5, "B": 0.5}
    out = policies.apply_llm_tilts(w, {"A": 5.0, "B": 0.0},
                                   tilt_cap=0.2, max_single_name=1.0)
    assert sum(out.values()) == pytest.approx(1.0)
    assert out["A"] / out["B"] == pytest.approx(1.2 / 0.8, rel=1e-6)


def test_winner_exemption_keeps_current_weight():
    state = {"names": {"WIN": {"status": "ok", "close": 150.0},
                       "OTH": {"status": "ok", "close": 100.0}}}
    positions = {"cash": 0.0, "positions": {
        "WIN": {"shares": 10.0, "cost_basis": 100.0,
                "exempt_since_session": 5},
        "OTH": {"shares": 15.0, "cost_basis": 100.0,
                "exempt_since_session": None}}}
    target = {"WIN": 0.10, "OTH": 0.90}
    out, receipts = policies.apply_winner_exemption(
        target, positions, state, session_index=10,
        gain_threshold_pct=40.0, exempt_trading_days=60)
    assert receipts and receipts[0]["ticker"] == "WIN"
    assert out["WIN"] > 0.10  # kept at (renormalized) current weight
    # after the window the exemption lapses
    out2, receipts2 = policies.apply_winner_exemption(
        target, positions, state, session_index=70,
        gain_threshold_pct=40.0, exempt_trading_days=60)
    assert not receipts2 and out2["WIN"] == pytest.approx(0.10)


def test_substitution_needs_a_margin():
    state = {"names": {"HELD": {"status": "ok", "close": 10.0,
                                "scores": {"arena_composite": 1.0}},
                       "CAND": {"status": "ok", "close": 10.0,
                                "scores": {"arena_composite": 1.3}}}}
    positions = {"cash": 0.0,
                 "positions": {"HELD": {"shares": 10, "cost_basis": 10}}}
    sel = policies.Selection(chosen=[{"ticker": "CAND", "rank": 1,
                                      "score": 1.3}])
    assert policies.substitution_check(positions, sel, state,
                                       margin_z=0.5) is None
    hit = policies.substitution_check(positions, sel, state, margin_z=0.2)
    assert hit == {"sell": "HELD", "buy": "CAND",
                   "score_gap": pytest.approx(0.3), "margin_z": 0.2}


def test_orders_never_borrow():
    state = {"names": {t: {"status": "ok", "close": 100.0}
                       for t in ["A", "B"]}}
    book = {"cash": 100000.0, "positions": {}}
    orders = policies.orders_from_targets(
        book, {"A": 0.5, "B": 0.5}, state, cost_bps=5, slippage_bps=1)
    spend = sum(o["usd"] for o in orders)
    cost = spend * 6 / 10_000
    assert spend + cost <= 100000.0


# ── experience ──────────────────────────────────────────────────────────────
def test_experience_refuses_the_ungradeable():
    with pytest.raises(experience.ExperienceInvalid):
        experience.make_experience(
            book_id="B", policy_version=1, ticker="AAA", action="YOLO",
            decision_date="2026-01-05", information_state_hash="h",
            model_id="m", thesis="t")
    with pytest.raises(experience.ExperienceInvalid):
        experience.make_experience(
            book_id="B", policy_version=1, ticker="AAA", action="ENTER",
            decision_date="2026-01-05", information_state_hash="",
            model_id="m", thesis="t")


def test_outcome_classes_cover_pass_and_call():
    assert experience.classify_outcome("ENTER", 0.05) == "GOOD_CALL"
    assert experience.classify_outcome("ENTER", -0.05) == "BAD_CALL"
    assert experience.classify_outcome("REJECT", -0.05) == "GOOD_PASS"
    assert experience.classify_outcome("REJECT", 0.05) == "BAD_PASS"
    assert experience.classify_outcome("ENTER", None) == "UNRESOLVED"


def test_maturation_resolves_each_horizon_once(root, panel, sessions):
    d0 = sessions[10]
    rec = experience.make_experience(
        book_id="ENGINE_BASELINE_v1", policy_version=1, ticker="AAA",
        action="ENTER", decision_date=str(d0),
        information_state_hash="hash", model_id="arena_rules@v1",
        thesis="test")
    store.append_experiences([rec], root)
    r1 = experience.mature_outcomes(panel, today=sessions[-1], root=root)
    assert r1["resolved"] == len([h for h in experience.HORIZONS
                                  if 10 + h < len(sessions)])
    r2 = experience.mature_outcomes(panel, today=sessions[-1], root=root)
    assert r2["resolved"] == 0  # write-once per (experience, horizon)
    rows = store.read_outcomes(root)
    assert all(o["excess_return"] is not None for o in rows)
    assert {o["horizon_days"] for o in rows} <= set(experience.HORIZONS)


# ── engine end-to-end ───────────────────────────────────────────────────────
def _run_two_days(root, panel, pit_db, sessions, monkeypatch):
    monkeypatch.setattr(discovery, "candidate_universe",
                        lambda extra=None: sorted(set(TICKERS)
                                                  | set(extra or [])))
    engine.seed_all(root=root)
    s1 = engine.run_daily(sessions[-2], panel=panel, root=root,
                          db_path=pit_db)
    s2 = engine.run_daily(sessions[-1], panel=panel, root=root,
                          db_path=pit_db)
    return s1, s2


def test_engine_decides_then_fills_then_marks(root, panel, pit_db, sessions,
                                              monkeypatch):
    s1, s2 = _run_two_days(root, panel, pit_db, sessions, monkeypatch)
    assert s1["status"] == "ok" and s2["status"] == "ok"
    assert s1["books_seeded"] == len(spec_mod.AUTHORISED_ACTIVE)
    r1 = {r["book_id"]: r for r in s1["receipts"]}
    r2 = {r["book_id"]: r for r in s2["receipts"]}
    base1, base2 = r1["ENGINE_BASELINE_v1"], r2["ENGINE_BASELINE_v1"]
    assert base1["decision_reason"] == "initial_build"
    assert base1["pending_orders"] > 0 and base1["open_positions"] == 0
    assert base2["fills"] == base1["pending_orders"]
    assert base2["open_positions"] > 0
    nav = store.read_nav("ENGINE_BASELINE_v1", root)
    assert [row["date"] for row in nav] == [str(sessions[-2]),
                                            str(sessions[-1])]
    assert nav[0]["nav"] == pytest.approx(100000.0)
    assert all(row["simulation"] is True for row in nav)


def test_engine_is_idempotent_within_a_session(root, panel, pit_db, sessions,
                                               monkeypatch):
    _run_two_days(root, panel, pit_db, sessions, monkeypatch)
    again = engine.run_daily(sessions[-1], panel=panel, root=root,
                             db_path=pit_db)
    assert all(r["status"] == "already_marked" for r in again["receipts"])
    assert len(store.read_nav("ENGINE_BASELINE_v1", root)) == 2


def test_engine_writes_chosen_and_rejected_experiences(root, panel, pit_db,
                                                       sessions, monkeypatch):
    _run_two_days(root, panel, pit_db, sessions, monkeypatch)
    exps = store.read_experiences(root)
    assert exps, "no experiences written"
    actions = {e["action"] for e in exps}
    assert "ENTER" in actions and "REJECT" in actions
    assert all(e["information_state_hash"] for e in exps)
    assert all(e["validation_status"] == "PRODUCT_EXPERIMENT" for e in exps)
    rejects = [e for e in exps if e["action"] == "REJECT"]
    assert all(e["chosen_alternative"] for e in rejects)


def test_unseeded_books_are_skipped_never_autoseeded(root, panel, pit_db,
                                                     sessions, monkeypatch):
    monkeypatch.setattr(discovery, "candidate_universe",
                        lambda extra=None: TICKERS)
    s = engine.run_daily(sessions[-1], panel=panel, root=root,
                         db_path=pit_db)
    assert s["status"] == "no_seeded_books"
    assert set(s["skipped_unseeded"]) == set(spec_mod.AUTHORISED_ACTIVE)
    assert not store.is_seeded("ENGINE_BASELINE_v1", root)


def test_thin_information_holds_instead_of_concentrating(root, tmp_path,
                                                         monkeypatch):
    """No momentum history AND no PIT scores must NOT become a one-stock
    100% book — the rehearsal failure (scored 1 of 180 → all-in on it)."""
    short_sessions = _weekday_sessions(60)
    short_panel = FakePanel(short_sessions)  # too short for 12-1 momentum
    db = tmp_path / "empty.db"
    conn = get_connection(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pit_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL, as_of TEXT NOT NULL, observed_at TEXT NOT NULL,
            value REAL, payload TEXT, source TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 0,
            UNIQUE(key, as_of, observed_at))
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(discovery, "candidate_universe",
                        lambda extra=None: TICKERS)
    engine.seed_all(root=root)
    s = engine.run_daily(short_sessions[-1], panel=short_panel, root=root,
                         db_path=db)
    for r in s["receipts"]:
        assert r["decision"]["status"] == "insufficient_breadth"
        assert r["pending_orders"] == 0 and r["open_positions"] == 0


def test_config_drift_refuses_to_run(root, panel, pit_db, sessions,
                                     monkeypatch):
    engine.seed_all(root=root)
    seed_p = store.seed_path("ENGINE_BASELINE_v1", root)
    rec = seed_p.read_text(encoding="utf-8").replace(
        spec_mod.config_hash()[:8], "deadbeef")
    seed_p.write_text(rec, encoding="utf-8")
    monkeypatch.setattr(discovery, "candidate_universe",
                        lambda extra=None: TICKERS)
    s = engine.run_daily(sessions[-1], panel=panel, root=root,
                         db_path=pit_db)
    r = {x["book_id"]: x for x in s["receipts"]}["ENGINE_BASELINE_v1"]
    assert r["status"] == "error" and "ConfigDrift" in r["error"]


def test_arena_never_touches_paper_nav_tables():
    """Static guard: the arena package must not import the sacred write path.

    Doc references to `paper_nav` (saying we never touch it) are fine; code
    that could actually write it is not. So the needles are call/import
    shaped, not words.
    """
    import pathlib
    pkg = pathlib.Path(engine.__file__).parent
    forbidden = ("insert_nav(", "insert_rebalance_event(",
                 "portfolio_intelligence import reference_engine",
                 "INSERT INTO paper_nav", "INSERT OR REPLACE INTO paper_nav",
                 "paper_positions")
    for f in pkg.glob("*.py"):
        text = f.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{f.name} references {needle}"
