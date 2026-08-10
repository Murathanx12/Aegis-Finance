"""BUILD-1.1 acceptance tests — the twenty things that must be true before a
dollar figure from this engine is allowed to look like a ticket.

Every one of these corresponds to a defect found in PM v1 by external review,
and every one of them is a property, not an example: they pin the *shape* of
the decision (a missing feed cannot become a sale; volatility cannot become
expected return) rather than a particular number, because the numbers are
supposed to move and the shapes are not.

Offline. The network is blocked for this file by `conftest`, which is the point
— if one of these tests reaches Yahoo, it is not testing the arithmetic.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml

from backend.services import (analyst_ledger, pm_actions, pm_engine,
                              pm_evidence, pm_journal)


# ─────────────────────────────── fixtures ──────────────────────────────────

@pytest.fixture
def offline(monkeypatch):
    """Cut every wire out of `pm_engine` that would reach for a network."""
    monkeypatch.setattr(pm_engine, "_looks_binary",
                        lambda t, out=None: False)
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.60)
    monkeypatch.setattr(pm_engine, "vol_is_measured", lambda t: True)
    monkeypatch.setattr(pm_engine, "_fallback_price",
                        lambda t, out=None: 10.0)
    monkeypatch.setattr(pm_engine, "_liquidity", lambda t, price=None: {
        "available": True, "adv_dollar": 5e6, "tradeable_at_retail_size": True,
        "assumed_round_trip_cost": 0.004, "cost_grade": "ASSUMPTION"})
    monkeypatch.setattr(analyst_ledger, "target_revisions",
                        lambda t, **k: {"history_available": False,
                                        "observations": 0})
    monkeypatch.setattr(analyst_ledger, "snapshot_if_new",
                        lambda *a, **k: None)
    return monkeypatch


def payload(price=10.0, median=20.0, low=12.0, high=40.0, n=8, days=30):
    """A Yahoo-shaped analyst payload."""
    return {
        "ticker": "TEST",
        "price_targets": {"current_price": price, "low": low, "mean": median,
                          "median": median, "high": high},
        "consensus_rating": {"score": 1.8, "label": "buy", "n_analysts": n},
        "recommendation_trend": [
            {"period": "0m", "strongBuy": 4, "buy": 3, "hold": 1,
             "sell": 0, "strongSell": 0},
            {"period": "-3m", "strongBuy": 2, "buy": 3, "hold": 3,
             "sell": 0, "strongSell": 0}],
        "recent_actions": [
            {"date": str(__import__("datetime").date.today()
                         - __import__("datetime").timedelta(days=days)),
             "firm": "Test Bank", "action": "upgrade"}],
        "attribution": "test",
    }


def install_analyst(monkeypatch, fn):
    """`enrich` imports the analyst layer at call time, so patch the module."""
    import backend.services.analyst_intelligence as ai
    monkeypatch.setattr(ai, "get_analyst_intelligence", fn)


def make_state(**kw):
    """A decisionable state straight out of `enrich`, offline."""
    return dict(kw)


# ── 1. the book marks to market ────────────────────────────────────────────

def test_1_a_price_move_changes_nav_without_touching_the_book_file():
    """The v1 bug in one test: a static `dollars` field cannot mark to market.

    Same YAML, same share counts, +20% on the tape. NAV, market value and
    weight must all move. In v1 every one of them was frozen.
    """
    book = pm_engine.Book(
        account="t", confirmed=True, cash=1_000.0, sizing_mode="growth",
        wealth_targets={}, positions=[
            pm_engine.Position(ticker="AAA", shares=100, cost_basis=10.0),
            pm_engine.Position(ticker="BBB", shares=50, cost_basis=20.0)])
    before = pm_engine.mark_book(book, {"AAA": 20.0, "BBB": 40.0})
    after = pm_engine.mark_book(book, {"AAA": 24.0, "BBB": 48.0})

    assert before["nav"] == pytest.approx(1_000 + 2_000 + 2_000)
    assert after["nav"] == pytest.approx(1_000 + 2_400 + 2_400)
    assert after["marks"]["AAA"]["market_value"] > \
        before["marks"]["AAA"]["market_value"]
    # the cash leg does not move, so the equity weight must rise
    assert after["marks"]["AAA"]["weight"] > before["marks"]["AAA"]["weight"]
    assert after["basis"] == "shares x live price"
    assert after["nav_complete"] is True


def test_1b_dollars_are_never_the_basis_of_a_confirmed_position():
    p = pm_engine.Position(ticker="AAA", shares=10, dollars=999_999.0,
                           cost_basis=10.0)
    m = pm_engine.mark_position(p, 12.0, confirmed=True)
    assert m["market_value"] == pytest.approx(120.0)   # not 999,999
    assert m["basis"] == "shares x live price"


def test_1c_an_unpriced_position_is_flagged_not_guessed():
    p = pm_engine.Position(ticker="AAA", shares=10, cost_basis=10.0)
    m = pm_engine.mark_position(p, None, confirmed=True)
    assert m["priced"] is False and "NO LIVE PRICE" in m["basis"]
    book = pm_engine.Book(account="t", confirmed=True, cash=0.0,
                          sizing_mode="growth", wealth_targets={},
                          positions=[p])
    marked = pm_engine.mark_book(book, {"AAA": None})
    assert marked["nav_complete"] is False and marked["unpriced"] == ["AAA"]


# ── 2. a confirmed book must be able to mark to market ─────────────────────

def test_2_a_confirmed_position_without_shares_is_rejected(tmp_path):
    p = tmp_path / "book.yaml"
    p.write_text(yaml.safe_dump({
        "account": "t", "confirmed": True, "cash": 0,
        "sizing_mode": "growth", "wealth_targets": {},
        "positions": [{"ticker": "AAA", "dollars": 5000}]}), encoding="utf-8")
    with pytest.raises(pm_engine.BookError) as e:
        pm_engine.load_book(p)
    assert "no share count" in str(e.value)


@pytest.mark.parametrize("shares,why", [
    (-5, "negative"), (float("nan"), "finite"), (float("inf"), "finite"),
    (0, "zero shares")])
def test_2b_bad_share_counts_are_named_not_swallowed(shares, why):
    book = pm_engine.Book(account="t", confirmed=True, cash=0.0,
                          sizing_mode="growth", wealth_targets={},
                          positions=[pm_engine.Position("AAA", shares=shares)])
    problems = pm_engine.validate_book(book)
    assert problems and any(why in p for p in problems), problems


def test_2c_shares_are_never_silently_inferred():
    out = pm_engine.shares_from_dollars(5_000, 20.0)
    assert out["shares"] == pytest.approx(250.0)
    assert "ESTIMATE" in out["confirm"]
    # and it is not wired into the decision path
    src = Path(pm_engine.__file__).read_text(encoding="utf-8")
    body = src.split("def enrich(")[1]
    assert "shares_from_dollars" not in body


# ── 3-5. absence of evidence is never a sale ───────────────────────────────

def test_3_a_price_only_held_name_is_review_never_sell(offline, monkeypatch):
    """A live price and no consensus target. v1: available -> weight 0 -> SELL."""
    install_analyst(monkeypatch, lambda t: {"ticker": t, "price_targets": None,
                                            "consensus_rating": None,
                                            "recommendation_trend": None,
                                            "recent_actions": None})
    e = pm_engine.enrich("AAA")
    assert e["market_data_status"] == "ok"
    assert e["distribution_status"] == "no_target"
    assert e["decisionable"] is False
    rec = pm_actions.action_for(0.05, 0.0, 45_000,
                                decisionable=e["decisionable"], held=True)
    assert rec["action"] == "REVIEW" and rec["dollars"] == 0


def test_4_a_malformed_target_is_missing_not_a_view(offline, monkeypatch):
    bad = payload()
    bad["price_targets"]["median"] = -3.0
    bad["price_targets"]["mean"] = None
    install_analyst(monkeypatch, lambda t: bad)
    e = pm_engine.enrich("AAA")
    assert e["decisionable"] is False
    assert any("not a positive price" in m for m in e["missing_reasons"])
    assert pm_actions.action_for(0.05, 0.0, 45_000,
                                 decisionable=False)["action"] == "REVIEW"


def test_4b_a_nan_target_is_missing(offline, monkeypatch):
    bad = payload()
    bad["price_targets"]["median"] = float("nan")
    bad["price_targets"]["mean"] = float("nan")
    install_analyst(monkeypatch, lambda t: bad)
    e = pm_engine.enrich("AAA")
    assert e["decisionable"] is False


def test_5_an_analyst_api_exception_is_review_not_a_sale(offline, monkeypatch):
    def boom(t):
        raise RuntimeError("vendor 503")
    install_analyst(monkeypatch, boom)
    e = pm_engine.enrich("AAA")
    assert e["analyst_data_status"] == "error"
    assert e["decisionable"] is False
    assert any("503" in m for m in e["missing_reasons"])
    assert pm_actions.action_for(0.08, 0.0, 45_000,
                                 decisionable=False)["action"] == "REVIEW"


def test_5b_a_stale_tape_downgrades_the_evidence_but_stays_decisionable(
        offline, monkeypatch):
    install_analyst(monkeypatch, lambda t: payload(days=900))
    e = pm_engine.enrich("AAA")
    assert e["analyst_data_status"] == "stale"
    assert e["decisionable"] is True          # a stale target is still a target
    fresh_rel = pm_evidence.reliability(dict(e, analyst_data_status="ok",
                                             days_since_last_action=10))
    assert e["evidence"]["reliability"]["multiplier"] < fresh_rel["multiplier"]


def test_5c_a_not_decisionable_candidate_is_never_bought():
    rec = pm_actions.action_for(0.0, 0.0, 45_000, decisionable=False,
                                held=False)
    assert rec["action"] == "SKIP" and rec["dollars"] == 0


# ── 6-7. volatility widens; it does not pay ────────────────────────────────

def test_6_same_evidence_higher_vol_same_expected_return(monkeypatch):
    """The single most consequential fix in BUILD-1.1.

    v1 set the lognormal's MEDIAN to the haircut upside and then reported its
    MEAN, which is `median x exp(sigma^2/2)`. At 90% vol that is a ~40% uplift
    to the expected return for no reason but uncertainty — and then Kelly sized
    on it.
    """
    from backend.tests.test_pm_engine import state
    calm = dict(state()); wild = dict(state())
    monkeypatch.setattr(pm_engine, "_vol",
                        lambda t: 0.30 if t == "CALM" else 0.90)
    calm["ticker"], wild["ticker"] = "CALM", "WILD"
    dc, dw = pm_engine.distribution(calm), pm_engine.distribution(wild)
    assert dc["expected_return"] == pytest.approx(dw["expected_return"], abs=1e-6)
    # ... and the distribution really is wider
    assert dw["bull"] > dc["bull"] and dw["bear"] < dc["bear"]
    assert dw["median_return"] < dc["median_return"]


def test_7_higher_vol_worsens_every_risk_metric(monkeypatch):
    from backend.tests.test_pm_engine import state, rows
    monkeypatch.setattr(pm_engine, "_vol",
                        lambda t: 0.30 if t == "CALM" else 0.90)
    dc = pm_engine.distribution(dict(state(), ticker="CALM"))
    dw = pm_engine.distribution(dict(state(), ticker="WILD"))
    assert dw["certainty_equivalent"] < dc["certainty_equivalent"]
    t = {"horizon_months": 12, "target_value": 100_000, "ruin_value": 20_000}
    calm = pm_actions.simulate_wealth(rows(vol=0.30), 45_000, 0, t)
    wild = pm_actions.simulate_wealth(rows(vol=0.90), 45_000, 0, t)
    assert wild["expected_max_drawdown"] < calm["expected_max_drawdown"]
    assert wild["p_below_ruin"] > calm["p_below_ruin"]
    assert wild["p5"] < calm["p5"]


def test_6b_expected_return_is_exactly_haircut_times_upside_times_discounts():
    from backend.tests.test_pm_engine import state
    e = state(price=10.0, median=20.0)              # +100% implied upside
    er = pm_engine.expected_return(e)
    ev = pm_evidence.evidence_summary(e)
    assert er["mu"] == pytest.approx(
        1.0 * pm_engine.TARGET_HAIRCUT
        * ev["reliability"]["multiplier"] * ev["revision_tilt"]["multiplier"])
    assert "EXPECTED VALUE" in er["interpretation"]


def test_6c_the_reliability_multiplier_can_only_discount():
    from backend.tests.test_pm_engine import state
    perfect = pm_evidence.reliability(dict(
        state(n=200, days=1), target_history_present=True,
        rating_history_present=True, target_observed_at="2026-08-10",
        market_data_status="ok", analyst_data_status="ok"))
    assert perfect["multiplier"] <= 1.0
    assert perfect["calibrated"] is False


# ── 8. replacement edge in one currency ────────────────────────────────────

def test_8_replacement_cost_units_reconcile():
    c = {"ticker": "NEW", "alpha": {"score": 0.60},
         "distribution": {"available": True, "expected_return": 0.30,
                          "annual_vol": 0.60}}
    h = {"ticker": "OLD", "alpha": {"score": 0.10},
         "distribution": {"available": True, "expected_return": 0.10,
                          "annual_vol": 0.40}}
    free = pm_actions.replacement_edge(c, h, switch_cost=0.0)
    cheap = pm_actions.replacement_edge(c, h, switch_cost=0.004)
    dear = pm_actions.replacement_edge(c, h, switch_cost=0.10)

    # zero cost reconciles exactly to the gross edge
    assert free["replacement_edge"] == pytest.approx(free["gross_edge"])
    # cost enters in the same units, linearly
    assert cheap["replacement_edge"] == pytest.approx(free["gross_edge"] - 0.004)
    assert dear["replacement_edge"] < cheap["replacement_edge"] < \
        free["replacement_edge"]
    # the gross edge IS a CE difference, in return units
    assert free["gross_edge"] == pytest.approx(
        (0.30 - 0.5 * 0.60 ** 2) - (0.10 - 0.5 * 0.40 ** 2))
    assert "expected-return units" in free["unit"]


def test_8b_rescaling_the_display_score_cannot_move_the_economics():
    """v1 subtracted 40bp from a score difference. Scale the scores x100 and
    the '40bp' becomes 0.4bp of the same quantity — a silent rescale of a cost.
    """
    base_c = {"ticker": "NEW", "alpha": {"score": 0.60},
              "distribution": {"available": True, "expected_return": 0.30,
                               "annual_vol": 0.50}}
    base_h = {"ticker": "OLD", "alpha": {"score": 0.10},
              "distribution": {"available": True, "expected_return": 0.10,
                               "annual_vol": 0.50}}
    big_c = {**base_c, "alpha": {"score": 60.0}}
    big_h = {**base_h, "alpha": {"score": 10.0}}
    a = pm_actions.replacement_edge(base_c, base_h, switch_cost=0.004)
    b = pm_actions.replacement_edge(big_c, big_h, switch_cost=0.004)
    assert a["replacement_edge"] == pytest.approx(b["replacement_edge"])
    assert a["alpha_score_delta"] != b["alpha_score_delta"]   # reported, unused


def test_8c_an_alpha_score_delta_is_never_called_net_of_cost():
    src = Path(pm_actions.__file__).read_text(encoding="utf-8")
    fn = src.split("def replacement_edge(")[1].split("\ndef ")[0]
    # the only subtraction of a cost happens against a certainty equivalent
    assert "net = gross - switch_cost" in fn
    assert "b - a - " not in fn


# ── 9-12. one portfolio, with its constraints actually binding ─────────────

def dist(mu, vol=0.5):
    return {"available": True, "expected_return": mu, "annual_vol": vol,
            "certainty_equivalent": mu - 0.5 * vol ** 2}


def row(ticker, mu, *, held=False, w=0.0, decisionable=True, vol=0.5):
    return {"ticker": ticker, "distribution": dist(mu, vol), "held": held,
            "current_weight": w, "decisionable": decisionable, "alpha": {}}


def test_9_a_candidate_is_actually_in_the_proposed_portfolio():
    """v1 ranked candidates in a separate list the portfolio never saw."""
    mode = pm_engine.MODES["growth"]
    rows = [row("OLD1", 0.02, held=True, w=0.5),
            row("OLD2", 0.03, held=True, w=0.5),
            row("NEW", 0.60)]
    plan = pm_actions.build_target_portfolio(rows, mode)
    assert plan["target_weights"]["NEW"] > 0
    # and it is the biggest position, because it has the best evidence
    assert plan["target_weights"]["NEW"] >= max(
        plan["target_weights"]["OLD1"], plan["target_weights"]["OLD2"])


def test_9b_the_wealth_simulation_sees_the_candidate_it_recommended():
    mode = pm_engine.MODES["growth"]
    rows = [row("OLD", 0.02, held=True, w=1.0), row("NEW", 0.60)]
    plan = pm_actions.build_target_portfolio(rows, mode)
    for r in rows:
        r["proposed"] = {"target_weight": plan["target_weights"][r["ticker"]]}
    proposed = [r for r in rows if r["proposed"]["target_weight"] > 0]
    w = pm_actions.simulate_wealth(proposed, 45_000, 0,
                                   {"horizon_months": 12,
                                    "target_value": 100_000})
    assert "NEW" in [r["ticker"] for r in proposed]
    assert w["names_simulated"] == len(proposed)


def test_10_buys_and_sells_reconcile_inside_the_cash_available():
    actions = [
        {"ticker": "A", "action": "SELL", "dollars": -3_000.0},
        {"ticker": "B", "action": "TRIM", "dollars": -1_000.0},
        {"ticker": "C", "action": "BUY", "dollars": 6_000.0},
    ]
    rec = pm_actions.enforce_cash_constraint(actions, cash=500.0, nav=45_000)
    assert rec["scaled"] is True
    assert rec["cash_after"] >= -1.0 and rec["reconciles"]
    assert rec["buys_final"] == pytest.approx(4_500.0, abs=1.0)
    plan = pm_actions.funding_plan(actions, cash=500.0)
    assert {p["funded_by"] for p in plan} <= {"A", "B", "CASH"}
    assert sum(p["dollars"] for p in plan) == pytest.approx(4_500.0, abs=2.0)


def test_10b_a_suppressed_trim_cannot_fund_a_purchase():
    """The band kills a $200 funding trim; the $5,000 buy must not survive it."""
    actions = [{"ticker": "C", "action": "BUY", "dollars": 5_000.0}]
    rec = pm_actions.enforce_cash_constraint(actions, cash=0.0, nav=45_000)
    assert actions[0]["action"] == "HOLD" and actions[0]["dollars"] == 0.0
    assert rec["cash_after"] == pytest.approx(0.0)


def test_11_max_names_is_a_constraint_not_a_comment():
    """`MODES[...]['max_names']` was defined and never read by anything."""
    mode = dict(pm_engine.MODES["moonshot"], max_names=5)
    rows = [row(f"T{i}", 0.60 - 0.01 * i) for i in range(20)]
    plan = pm_actions.build_target_portfolio(rows, mode)
    held = [t for t, w in plan["target_weights"].items() if w > 0]
    assert len(held) == 5
    assert len(plan["dropped_for_max_names"]) == 15
    assert "max_names" in plan["constraints_binding"]


def test_11b_frozen_names_consume_slots_and_budget():
    mode = dict(pm_engine.MODES["growth"], max_names=3, max_weight=0.5)
    rows = [row("BLIND", 0.0, held=True, w=0.20, decisionable=False),
            row("A", 0.50), row("B", 0.40), row("C", 0.30)]
    plan = pm_actions.build_target_portfolio(rows, mode)
    assert plan["target_weights"]["BLIND"] == pytest.approx(0.20)
    assert plan["slots"] == 2
    assert len([t for t, w in plan["target_weights"].items() if w > 0]) == 3


def test_12_min_cash_is_enforced():
    for name in ("growth", "high_growth", "moonshot"):
        mode = pm_engine.MODES[name]
        rows = [row(f"T{i}", 0.40) for i in range(mode["max_names"])]
        plan = pm_actions.build_target_portfolio(rows, mode)
        invested = sum(plan["target_weights"].values())
        assert invested <= 1.0 - mode["min_cash"] + 1e-6, name
        assert plan["cash_weight"] >= mode["min_cash"] - 1e-6, name


def test_13_mode_changes_risk_constraints_only_never_evidence(monkeypatch):
    from backend.tests.test_pm_engine import state
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.60)
    e = state()
    d = pm_engine.distribution(e)
    a = pm_engine.analyst_alpha(e)
    rows_ = [row("A", d["expected_return"]), row("B", 0.20), row("C", 0.10)]
    plans = {m: pm_actions.build_target_portfolio(rows_, pm_engine.MODES[m])
             for m in pm_engine.MODES}
    # the evidence is byte-identical across modes
    assert pm_engine.distribution(e) == d
    assert pm_engine.analyst_alpha(e) == a
    # the constraints are not
    assert plans["moonshot"]["target_weights"]["A"] > \
        plans["growth"]["target_weights"]["A"]
    assert {p["min_cash"] for p in plans.values()} == {0.05, 0.02, 0.0}


# ── 14. an unconfirmed book cannot look actionable ─────────────────────────

def fake_brief(monkeypatch, book, **kw):
    """Run the real `daily_brief` with the network replaced by canned states."""
    def _enrich(ticker, position=None, record_snapshot=False):
        e = {
            "ticker": ticker, "available": True, "price": 10.0,
            "market_data_status": "ok", "analyst_data_status": "ok",
            "distribution_status": "ok", "decisionable": True,
            "missing_reasons": [], "warnings": [],
            "target_low": 12.0, "target_median": 20.0, "target_high": 30.0,
            "target_mean": 20.0, "implied_upside": 1.0,
            "dispersion": 0.9, "n_analysts": 10, "consensus_score": 1.9,
            "consensus_label": "buy", "rating_drift_3m": 0.1, "net_90d": 1,
            "upgrades_90d": 1, "downgrades_90d": 0,
            "days_since_last_action": 20, "binary_event_risk": False,
            "rating_history_present": True, "target_history_present": False,
            "liquidity": {"available": True, "adv_dollar": 5e6,
                          "tradeable_at_retail_size": True,
                          "assumed_round_trip_cost": 0.004},
            "target_revisions": {"history_available": False, "observations": 0},
        }
        e["evidence"] = pm_evidence.evidence_summary(e)
        return e
    monkeypatch.setattr(pm_actions, "enrich", _enrich)
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.60)
    return pm_actions.daily_brief(book, **kw)


def a_book(confirmed=False, shares=None):
    return pm_engine.Book(
        account="t", confirmed=confirmed, cash=1_000.0,
        sizing_mode="growth",
        wealth_targets={"horizon_months": 12, "target_value": 100_000,
                        "floor_value": 30_000, "ruin_value": 20_000},
        positions=[pm_engine.Position("AAA", shares=shares, dollars=5_000,
                                      cost_basis=8.0, thesis="t",
                                      kill_condition="k"),
                   pm_engine.Position("BBB", shares=shares, dollars=5_000,
                                      cost_basis=8.0, thesis="t",
                                      kill_condition="k")],
        watchlist=["CCC"])


def test_14_an_unconfirmed_book_is_not_actionable(monkeypatch):
    b = fake_brief(monkeypatch, a_book(confirmed=False))
    assert b["actionable"] is False
    assert b["ticket_label"] == \
        "SIMULATED TICKETS — BOOK UNCONFIRMED — DO NOT EXECUTE"
    assert b["banner"] and "SIMULATED" in b["banner"]
    assert b["actionable_blockers"]


def test_14b_a_confirmed_priced_book_is_actionable(monkeypatch):
    b = fake_brief(monkeypatch, a_book(confirmed=True, shares=500))
    assert b["actionable"] is True
    assert b["ticket_label"] == "TODAY'S TICKETS"
    assert b["banner"] is None
    assert b["valuation"]["basis"] == "shares x live price"
    # 500 shares at $10 each, plus $1,000 cash
    assert b["portfolio_value"] == pytest.approx(11_000.0)


def test_14e_an_unpriced_position_is_tolerated_only_up_to_a_threshold(
        monkeypatch):
    """One permanently-halted microcap must not freeze a live book forever —
    but every ticket is sized off NAV, so a big hole in it must stop the run.
    """
    real = pm_actions.enrich

    def blind_bbb(ticker, position=None, record_snapshot=False):
        e = fake_state()
        if ticker == "BBB":
            return {"ticker": ticker, "available": False, "price": None,
                    "market_data_status": "missing",
                    "analyst_data_status": "missing",
                    "distribution_status": "no_price", "decisionable": False,
                    "missing_reasons": ["halted"], "warnings": []}
        e["ticker"] = ticker
        return e
    monkeypatch.setattr(pm_actions, "enrich", blind_bbb)
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.60)

    # BBB is ~1.9% of NAV: tolerated, book stays actionable, BBB is in REVIEW
    small = pm_engine.Book(
        account="t", confirmed=True, cash=0.0, sizing_mode="growth",
        wealth_targets={"horizon_months": 12, "target_value": 100_000},
        positions=[pm_engine.Position("AAA", shares=1000, cost_basis=5.0),
                   pm_engine.Position("BBB", shares=20, cost_basis=10.0)])
    b = pm_actions.daily_brief(small, include_watchlist=False)
    assert b["nav_uncertainty"]["unpriced_share_of_nav"] < 0.10
    assert b["actionable"] is True and b["ticket_label"] == "TODAY'S TICKETS"
    bbb = next(r for r in b["holdings"] if r["ticker"] == "BBB")
    assert bbb["recommendation"]["action"] == "REVIEW"

    # BBB is ~50% of NAV: NAV is not knowable, so no ticket is
    big = pm_engine.Book(
        account="t", confirmed=True, cash=0.0, sizing_mode="growth",
        wealth_targets={"horizon_months": 12, "target_value": 100_000},
        positions=[pm_engine.Position("AAA", shares=1000, cost_basis=5.0),
                   pm_engine.Position("BBB", shares=500, cost_basis=10.0)])
    b2 = pm_actions.daily_brief(big, include_watchlist=False)
    assert b2["nav_uncertainty"]["material"] is True
    assert b2["actionable"] is False
    assert "BOOK INCOMPLETE" in b2["ticket_label"]   # not "UNCONFIRMED"


def fake_state():
    e = {
        "available": True, "price": 10.0, "market_data_status": "ok",
        "analyst_data_status": "ok", "distribution_status": "ok",
        "decisionable": True, "missing_reasons": [], "warnings": [],
        "target_low": 12.0, "target_median": 20.0, "target_high": 30.0,
        "target_mean": 20.0, "implied_upside": 1.0, "dispersion": 0.9,
        "n_analysts": 10, "consensus_score": 1.9, "consensus_label": "buy",
        "rating_drift_3m": 0.1, "net_90d": 1, "upgrades_90d": 1,
        "downgrades_90d": 0, "days_since_last_action": 20,
        "binary_event_risk": False, "rating_history_present": True,
        "target_history_present": False,
        "liquidity": {"available": True, "adv_dollar": 5e6,
                      "tradeable_at_retail_size": True,
                      "assumed_round_trip_cost": 0.004},
        "target_revisions": {"history_available": False, "observations": 0},
    }
    e["evidence"] = pm_evidence.evidence_summary(e)
    return e


def test_14c_the_journal_records_recommendations_never_executions(
        monkeypatch, tmp_path):
    monkeypatch.setattr(pm_journal, "JOURNAL", tmp_path / "j.jsonl")
    b = fake_brief(monkeypatch, a_book(confirmed=False))
    out = pm_journal.record_brief(b, note="test")
    assert out["actionable"] is False and "never as executable" in out["caveat"]
    for row_ in out["entries"]:
        assert row_["executed"] is False and row_["actionable"] is False


def test_14d_the_brief_carries_a_model_status_a_reader_can_scan(monkeypatch):
    b = fake_brief(monkeypatch, a_book(confirmed=False))
    ms = b["model_status"]
    for k in ("book_confirmed", "valuation_basis", "mean_evidence_completeness",
              "analyst_sources", "analyst_history_available",
              "target_revision_fields", "catalyst_coverage",
              "return_model_grade", "scenario_sensitivity", "last_refresh"):
        assert k in ms, k
    # the grade must always name what the calendar CANNOT see
    assert ms["catalyst_coverage"].startswith(("NONE", "v0"))
    assert "NOT covered" in ms["catalyst_coverage"] or \
        ms["catalyst_coverage"].startswith("NONE")
    assert "FDA/PDUFA action dates" in ms["catalysts_uncovered"]


# ── 15-16. unknown is not perfect, and history cannot be invented ──────────

def test_15_missing_analyst_history_is_not_perfect_freshness():
    """v1: `1.0 if days is None else exp(-days/180)`. Unknown beat everything."""
    unknown, known = pm_evidence._freshness(None)
    yesterday, _ = pm_evidence._freshness(1)
    old, _ = pm_evidence._freshness(700)
    assert known is False
    assert unknown < yesterday, "an unrated name must not out-score a fresh one"
    assert unknown > old
    assert unknown == pm_evidence.UNKNOWN


def test_15b_unknown_breadth_and_dispersion_are_penalised_too():
    base = {"target_median": 20.0, "market_data_status": "ok",
            "n_analysts": 12, "dispersion": 0.5, "days_since_last_action": 10}
    full = pm_evidence.reliability(base)
    no_n = pm_evidence.reliability({**base, "n_analysts": None})
    no_d = pm_evidence.reliability({**base, "dispersion": None})
    assert no_n["multiplier"] < full["multiplier"]
    assert no_d["multiplier"] < full["multiplier"]
    assert "n_analysts" in no_n["unknowns_penalised"]


def test_15c_completeness_counts_what_is_missing_by_name():
    c = pm_evidence.completeness({"target_median": 20.0,
                                  "market_data_status": "ok"})
    assert c["known_fraction"] < 1.0
    assert "target_history_present" in c["missing"]
    assert c["grade"] in ("thin", "partial", "full")


def test_16_target_revisions_cannot_exist_without_snapshots(tmp_path):
    led = tmp_path / "snap.jsonl"
    # nothing observed at all
    r = analyst_ledger.target_revisions("AAA", path=led)
    assert r["observations"] == 0 and r["history_available"] is False
    for k in ("delta_target_7d", "delta_target_30d", "delta_target_90d"):
        assert r[k] is None
        assert r[k + "_status"].startswith("MISSING")

    # one observation is still not a revision
    analyst_ledger.snapshot("AAA", {"price": 10.0, "target_median": 20.0},
                            path=led)
    r = analyst_ledger.target_revisions("AAA", path=led)
    assert r["observations"] == 1
    assert all(r[f"delta_target_{d}d"] is None for d in (7, 30, 90))


def test_16b_a_real_delta_appears_once_two_snapshots_span_the_window(tmp_path):
    from datetime import date, datetime, timedelta
    led = tmp_path / "snap.jsonl"
    today = date(2026, 8, 10)
    rows_ = [
        {"ticker": "AAA", "observed_at":
            (datetime(2026, 8, 10) - timedelta(days=30)).isoformat(),
         "target_median": 20.0, "n_analysts": 8, "target_low": 15.0,
         "target_high": 25.0},
        {"ticker": "AAA", "observed_at": datetime(2026, 8, 10).isoformat(),
         "target_median": 24.0, "n_analysts": 10, "target_low": 18.0,
         "target_high": 30.0},
    ]
    r = analyst_ledger.target_revisions("AAA", rows=rows_, today=today)
    assert r["delta_target_30d"] == pytest.approx(0.20)
    assert r["delta_target_30d_status"] == "ok"
    # the 7-day window has no anchor near it and must stay MISSING
    assert r["delta_target_7d"] is None
    assert r["breadth_change"] == 2


def test_16c_rating_drift_is_never_labelled_a_target_revision():
    src = Path(pm_engine.__file__).read_text(encoding="utf-8")
    fn = src.split("def _rating_drift(")[1].split("\ndef ")[0]
    assert "NOT a target revision" in fn
    tilt = pm_evidence.revision_tilt({"rating_drift_3m": 0.2, "net_90d": 2})
    assert "NOT a target revision" in tilt["note"]


def test_16d_the_ledger_is_append_only(tmp_path):
    led = tmp_path / "snap.jsonl"
    analyst_ledger.snapshot("AAA", {"price": 10.0, "target_median": 20.0},
                            path=led)
    analyst_ledger.snapshot("AAA", {"price": 11.0, "target_median": 21.0},
                            path=led)
    rows_ = analyst_ledger.read("AAA", path=led)
    assert len(rows_) == 2
    assert rows_[0]["target_median"] == 20.0     # the first row is untouched
    assert rows_[0]["raw_payload_hash"] != rows_[1]["raw_payload_hash"]


# ── 17. the answer carries its model uncertainty ───────────────────────────

def test_17_the_wealth_output_is_three_scenarios_with_the_downside(monkeypatch):
    from backend.tests.test_pm_engine import rows
    w = pm_actions.wealth_scenarios(rows(), 45_000, 0,
                                    {"horizon_months": 12,
                                     "target_value": 100_000,
                                     "floor_value": 30_000,
                                     "ruin_value": 20_000})
    assert set(w["scenarios"]) == {"conservative", "base", "optimistic"}
    for name, s in w["scenarios"].items():
        for k in ("p_reach_target", "p_below_floor", "p_below_ruin",
                  "expected_max_drawdown", "p_drawdown_worse_than_50pct",
                  "median"):
            assert s[k] is not None, (name, k)
    con, base, opt = (w["scenarios"]["conservative"], w["scenarios"]["base"],
                      w["scenarios"]["optimistic"])
    # the arms are ordered where the assumptions unambiguously say they must be
    assert con["median"] < base["median"] < opt["median"]
    assert con["p_below_ruin"] > opt["p_below_ruin"]
    assert con["expected_max_drawdown"] < opt["expected_max_drawdown"]
    rng = w["range"]["p_reach_target"]
    assert rng["low"] <= rng["base"] <= rng["high"]
    assert "MODEL uncertainty" in w["headline"]


def test_17c_a_tail_target_is_flagged_as_a_volatility_outcome():
    """$45k -> $100k in a year needs +122%. That is reached by variance, not by
    drift, so the pessimistic arm can print a HIGHER P(reach) while being worse
    on every measure that matters. The brief must say which case it is in.
    """
    from backend.tests.test_pm_engine import rows
    w = pm_actions.wealth_scenarios(rows(), 45_000, 0,
                                    {"horizon_months": 12,
                                     "target_value": 100_000,
                                     "ruin_value": 20_000})
    assert "volatility_dominates_target" in w
    con, base = w["scenarios"]["conservative"], w["scenarios"]["base"]
    if w["volatility_dominates_target"]:
        assert con["p_reach_target"] >= base["p_reach_target"]
        assert con["median"] < base["median"]        # and poorer where it lives
        assert con["p_below_ruin"] > base["p_below_ruin"]
        assert "volatility outcome" in w["tail_note"]


def test_17b_the_scenarios_are_not_tuned_to_flatter_the_goal():
    """The optimistic arm still takes less than half the street's word."""
    assert pm_actions.SCENARIOS["optimistic"]["target_haircut"] <= 0.50
    assert pm_actions.SCENARIOS["conservative"]["target_haircut"] < \
        pm_engine.TARGET_HAIRCUT
    assert pm_actions.SCENARIOS["conservative"]["correlation"] > \
        pm_actions.SCENARIOS["base"]["correlation"]


# ── the execution layer: a bad quote is not a cost (P4) ───────────────────

def _info(monkeypatch, info):
    class _T:
        def __init__(self, t): self.info = info
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", _T)


def test_p4_an_after_hours_artifact_quote_is_rejected_not_charged(monkeypatch):
    """Live 2026-08-10: Yahoo returned AARD bid 5.48 / ask 9.60 in size TWO
    while it last traded at 7.50. Charged as a round trip that is 55%, and it
    made every replacement comparison touching the name meaningless.
    """
    _info(monkeypatch, {"bid": 5.48, "ask": 9.60, "currentPrice": 7.495,
                        "bidSize": 2, "askSize": 2})
    q = pm_engine._quoted_spread("AARD")
    assert q["available"] is False
    assert "implausible width" in q["reason"]
    assert "round lot" in q["reason"]
    assert q["observed_spread_bps"] > 5_000       # recorded, but not believed


def test_p4_a_real_quote_in_size_is_accepted(monkeypatch):
    _info(monkeypatch, {"bid": 94.97, "ask": 95.12, "currentPrice": 95.085,
                        "bidSize": 400, "askSize": 200})
    q = pm_engine._quoted_spread("ELF")
    assert q["available"] is True
    assert q["spread_bps"] == pytest.approx(15.8, abs=1.0)


def test_p4_a_quote_that_does_not_bracket_the_last_trade_is_rejected(monkeypatch):
    _info(monkeypatch, {"bid": 22.69, "ask": 26.21, "currentPrice": 24.82,
                        "bidSize": 200, "askSize": 200})
    q = pm_engine._quoted_spread("DKNG")
    assert q["available"] is False


def test_p4_the_round_trip_cost_is_capped(monkeypatch):
    """Even an accepted-but-wide quote cannot charge an unbounded cost."""
    import pandas as pd

    class _T:
        def __init__(self, t): pass
        def history(self, **kw):
            return pd.DataFrame({"Close": [10.0] * 20, "Volume": [1e6] * 20,
                                 "High": [10.5] * 20, "Low": [9.5] * 20})
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", _T)
    monkeypatch.setattr(pm_engine, "_quoted_spread",
                        lambda t: {"available": True, "bid": 8.0, "ask": 12.0,
                                   "spread_bps": 4000.0, "size": 500,
                                   "source": "test"})
    liq = pm_engine._liquidity("WIDE", price=10.0)
    # 2 x 40% = 80% uncapped; the cap binds and says so
    assert liq["assumed_round_trip_cost"] == pytest.approx(
        pm_engine.MAX_ROUND_TRIP)
    assert liq["round_trip_capped"] is True
    assert "reason not to trade" in liq["cost_note"]
    # and the intraday range is reported as a range, never as a cost
    assert liq["intraday_range_pct"] == pytest.approx(10.0, abs=0.1)
    assert "not a quoted spread" in liq["intraday_range_note"]


def test_p4_intraday_range_is_never_presented_as_a_spread():
    src = Path(pm_engine.__file__).read_text(encoding="utf-8")
    assert "intraday_range_pct" in src
    assert "a RANGE, not a" in src
    # the old field name must be gone so nothing downstream can read it as one
    assert "typical_daily_range_pct" not in src


def test_p4_the_no_trade_band_widens_with_the_cost_of_trading():
    """A cheap name trades on a 1.5% drift; a name that costs 3% to round-trip
    must not be churned for the same 1.5%.
    """
    cheap = pm_actions.action_for(0.10, 0.125, 45_000, round_trip_cost=0.004)
    dear = pm_actions.action_for(0.10, 0.125, 45_000, round_trip_cost=0.03)
    assert cheap["action"] == "ADD"
    assert dear["action"] == "HOLD"
    assert dear["band"] > cheap["band"]
    assert "cost-aware" in dear["why"]


# ── the catalyst layer (B5 v0) — an empty calendar is not "all clear" ──────

def test_18_an_empty_catalyst_calendar_never_reads_as_nothing_is_coming(
        monkeypatch):
    from backend.services import pm_catalysts
    monkeypatch.setattr(pm_catalysts, "_finnhub", lambda p, q: None)
    cal = pm_catalysts.calendar(["APLT", "NTLA"])
    assert cal["events_found"] == 0
    cov = cal["coverage"]
    assert "NOT evidence that nothing is scheduled" in cov["warning"]
    for gap in ("FDA/PDUFA action dates", "lockup expiries"):
        assert gap in cov["uncovered"]
    assert pm_actions._catalyst_grade(cal).startswith(("v0", "NONE"))


def test_18b_earnings_events_carry_their_provenance(monkeypatch):
    from backend.services import pm_catalysts
    monkeypatch.setattr(pm_catalysts, "cache_get", lambda *a, **k: None)
    monkeypatch.setattr(pm_catalysts, "cache_set", lambda *a, **k: None)
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=5)).isoformat()
    monkeypatch.setattr(pm_catalysts, "_finnhub", lambda p, q: {
        "earningsCalendar": [{"date": soon, "hour": "amc", "quarter": 3,
                              "year": 2026, "epsEstimate": 0.02,
                              "revenueEstimate": 1e9}]})
    evs = pm_catalysts.earnings_events("DKNG")
    assert len(evs) == 1
    e = evs[0]
    assert e["days_away"] == 5 and e["expectedness"] == "scheduled"
    assert e["source"] == "finnhub/calendar/earnings" and e["receipt"]
    assert e["direction"] is None       # we know the date, not the outcome


def test_18c_a_hand_entered_catalyst_is_the_only_route_for_a_pdufa():
    from backend.services import pm_catalysts
    p = pm_engine.Position("APLT", catalysts=[
        {"date": "2026-11-14", "kind": "pdufa", "what": "govorestat action date"}])
    evs = pm_catalysts.book_catalysts(p)
    assert evs[0]["kind"] == "pdufa"
    assert evs[0]["source"] == "book file (human-entered)"
    assert "unverified" in evs[0]["confidence"]


def test_18d_a_past_earnings_date_is_not_an_upcoming_catalyst(monkeypatch):
    from backend.services import pm_catalysts
    from datetime import date, timedelta
    monkeypatch.setattr(pm_catalysts, "cache_get", lambda *a, **k: None)
    monkeypatch.setattr(pm_catalysts, "cache_set", lambda *a, **k: None)
    past = (date.today() - timedelta(days=4)).isoformat()
    monkeypatch.setattr(pm_catalysts, "_finnhub", lambda p, q: {
        "earningsCalendar": [{"date": past, "epsEstimate": 0.02}]})
    assert pm_catalysts.earnings_events("DKNG") == []


# ── the source spine: what we probed, and what it means we cannot claim ────

def test_19_the_source_coverage_matrix_is_committed_with_receipts():
    """No "unavailable" claim without a printed status code."""
    doc = Path(__file__).resolve().parents[2] / "docs" / "BUILD1" / \
        "ANALYST_SOURCE_COVERAGE.md"
    receipt = doc.parent / "analyst_source_probe_DKNG.json"
    assert doc.exists(), "the coverage matrix must be committed"
    assert receipt.exists(), "the raw probe output must be committed"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["results"], "the probe must have called something"
    for r in data["results"]:
        assert r["status"] is not None, r["endpoint"]
    text = doc.read_text(encoding="utf-8")
    # every vendor we hold a key for appears in the matrix with a status
    for vendor in ("finnhub", "fmp", "eodhd", "polygon", "alpha_vantage"):
        assert vendor in text.lower(), vendor


def test_19b_the_engine_does_not_claim_a_source_it_does_not_read():
    """`model_status.analyst_sources` must name what `enrich` actually calls."""
    src = Path(pm_engine.__file__).read_text(encoding="utf-8")
    body = src.split("def enrich(")[1].split("\ndef ")[0]
    assert "analyst_intelligence" in body
    # analyst_intelligence is the Yahoo layer; if a second source is ever wired
    # in, this test fails and model_status must be updated with it
    ai = Path(__file__).resolve().parents[1] / "services" / \
        "analyst_intelligence.py"
    assert "yfinance" in ai.read_text(encoding="utf-8")


# ── silent-fragility audit: four ways this could have run green and lied ──

def test_sf1_a_guessed_volatility_is_never_silent(monkeypatch):
    """A failed vol fetch used to substitute 65% and CACHE IT FOREVER. Every
    Kelly weight is mu/sigma^2, so one transient failure quietly resized the
    name for the life of the process and nothing said so.
    """
    pm_engine._VOL_CACHE.pop("BROKE", None)
    pm_engine.VOL_FALLBACKS.pop("BROKE", None)

    class _T:
        def __init__(self, t): pass
        def history(self, **kw): raise RuntimeError("yahoo down")
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", _T)

    v = pm_engine._vol("BROKE")
    assert v == pm_engine.FALLBACK_VOL
    assert pm_engine.vol_is_measured("BROKE") is False
    assert "BROKE" in pm_engine.VOL_FALLBACKS
    # and crucially it is NOT cached, so recovery is possible
    assert "BROKE" not in pm_engine._VOL_CACHE
    pm_engine.VOL_FALLBACKS.pop("BROKE", None)


def test_sf1b_too_little_history_is_a_fallback_not_a_measurement(monkeypatch):
    import pandas as pd
    pm_engine._VOL_CACHE.pop("THIN", None)

    class _T:
        def __init__(self, t): pass
        def history(self, **kw):
            return pd.DataFrame({"Close": [10.0] * 10})
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", _T)
    pm_engine._vol("THIN")
    assert pm_engine.vol_is_measured("THIN") is False
    assert "bars available" in pm_engine.VOL_FALLBACKS["THIN"]
    pm_engine.VOL_FALLBACKS.pop("THIN", None)


def test_sf2_a_skipped_binary_check_biases_toward_risk_and_says_so(monkeypatch):
    """Returning False on a failed fetch REMOVES the 0.60 extra haircut, so the
    failure makes the riskiest names BIGGER. It must be visible.
    """
    class _T:
        def __init__(self, t): raise RuntimeError("info unavailable")
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", _T)
    out = {"warnings": []}
    assert pm_engine._looks_binary("APLT", out) is False
    assert out["binary_check_ran"] is False
    assert any("LESS conservative" in w for w in out["warnings"])


def test_sf3_a_403_calendar_is_unknown_not_empty(monkeypatch):
    """The whole point of this layer is that silence never reads as safety."""
    from backend.services import pm_catalysts
    monkeypatch.setattr(pm_catalysts, "cache_get", lambda *a, **k: None)
    monkeypatch.setattr(pm_catalysts, "cache_set", lambda *a, **k: None)
    monkeypatch.setattr(pm_catalysts, "_finnhub", lambda p, q: None)
    with pytest.raises(pm_catalysts.CatalystFetchError):
        pm_catalysts.earnings_events("APLT")

    cal = pm_catalysts.calendar(["APLT", "NTLA"])
    assert cal["tickers_checked"] == 0
    assert set(cal["tickers_blind"]) == {"APLT", "NTLA"}
    cov = cal["coverage"]
    assert cov["tickers_not_retrieved"] == 2
    assert "UNKNOWN, not empty" in cov["grade"]
    assert "DEGRADED" in pm_actions._catalyst_grade(cal) or \
        "DEGRADED" in cov["grade"]


def test_sf3b_a_genuinely_quiet_window_is_distinguishable_from_a_failure(
        monkeypatch):
    from backend.services import pm_catalysts
    monkeypatch.setattr(pm_catalysts, "cache_get", lambda *a, **k: None)
    monkeypatch.setattr(pm_catalysts, "cache_set", lambda *a, **k: None)
    monkeypatch.setattr(pm_catalysts, "_finnhub",
                        lambda p, q: {"earningsCalendar": []})
    cal = pm_catalysts.calendar(["AAA"])
    assert cal["tickers_checked"] == 1 and cal["tickers_blind"] == []
    assert cal["coverage"]["tickers_not_retrieved"] == 0
    assert "DEGRADED" not in cal["coverage"]["grade"]


def test_sf4_a_corrupt_ledger_row_is_counted_not_swallowed(tmp_path):
    led = tmp_path / "snap.jsonl"
    analyst_ledger.snapshot("AAA", {"price": 10.0, "target_median": 20.0},
                            path=led)
    with led.open("a", encoding="utf-8") as fh:
        fh.write("{this is not json\n")
    rows_ = analyst_ledger.read(path=led)
    assert len(rows_) == 1
    assert analyst_ledger.coverage(path=led)["malformed_rows"] == 1


def test_sf5_the_model_status_surfaces_every_degradation(monkeypatch):
    """If one of these went dark tonight, the brief has to say so."""
    b = fake_brief(monkeypatch, a_book(confirmed=False))
    ms = b["model_status"]
    for k in ("volatility_fallbacks", "binary_check_did_not_run",
              "analyst_ledger", "catalyst_coverage",
              "trades_not_clearing_their_own_cost"):
        assert k in ms, k


# ── 20. nothing here can place an order ────────────────────────────────────

def test_20_no_execution_path_exists_anywhere_in_the_pm():
    """The engine never trades. Grep is a blunt instrument and that is fine —
    the point is that adding a broker call has to be a deliberate, visible act.
    """
    banned = ("submit_order", "place_order", "create_order", "alpaca",
              "broker.", "TradingClient", "requests.post(\"https://api.")
    for mod in (pm_engine, pm_actions, pm_journal, pm_evidence, analyst_ledger):
        src = Path(mod.__file__).read_text(encoding="utf-8").lower()
        for b in banned:
            assert b.lower() not in src, f"{mod.__name__} mentions {b}"
