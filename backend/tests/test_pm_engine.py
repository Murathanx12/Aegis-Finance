"""Portfolio-manager unit tests — offline, on the pure decision functions.

Nothing here touches the network. The enrichment layer is the part that talks to
Yahoo; everything below it is arithmetic, and arithmetic is where the decisions
actually get made, so that is what is pinned.

BUILD-1.1 acceptance tests live in `test_pm_build11.py`.
"""
import math

import pytest

from backend.services import pm_actions, pm_engine


def state(price=10.0, median=20.0, low=12.0, high=40.0, n=8, drift=0.1,
          net=2, days=30, binary=False, adv=5e6):
    return {
        "ticker": "TEST", "available": True, "price": price,
        "market_data_status": "ok", "analyst_data_status": "ok",
        "distribution_status": "ok" if median else "no_target",
        "decisionable": bool(median), "missing_reasons": [],
        "target_low": low, "target_median": median, "target_high": high,
        "target_mean": median,
        "implied_upside": (median / price - 1.0) if median else None,
        "dispersion": ((high - low) / median) if median else None,
        "n_analysts": n, "consensus_score": 1.8, "consensus_label": "buy",
        "rating_drift_3m": drift, "upgrades_90d": max(net, 0),
        "downgrades_90d": max(-net, 0), "net_90d": net,
        "days_since_last_action": days, "binary_event_risk": binary,
        "rating_history_present": True, "target_history_present": False,
        "liquidity": {"available": True, "adv_dollar": adv,
                      "tradeable_at_retail_size": adv > 1e6,
                      "assumed_round_trip_cost": 0.004},
    }


# ── the distribution ───────────────────────────────────────────────────────

def test_the_distribution_is_one_lognormal_read_consistently(monkeypatch):
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.60)
    d = pm_engine.distribution(state())
    assert d["available"]
    assert d["bear"] < d["base"] < d["bull"]
    # the MEAN is the anchor and the median sits BELOW it — the reverse of v1,
    # where the median was the anchor and the mean floated up with sigma
    assert d["expected_return"] > d["median_return"]


def test_the_haircut_actually_bites(monkeypatch):
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.60)
    e = state(price=10, median=20)
    d = pm_engine.distribution(e)
    rel = e["evidence"]["reliability"]["multiplier"] if "evidence" in e else None
    # raw implied upside is +100%; the EXPECTED return must be far below it and
    # must equal haircut x upside x reliability x tilt, exactly
    er = pm_engine.expected_return(e)
    assert d["expected_return"] == pytest.approx(er["mu"], abs=1e-4)
    assert d["expected_return"] < 1.0 * pm_engine.TARGET_HAIRCUT + 1e-9
    assert rel is None or rel <= 1.0


def test_a_binary_name_is_haircut_harder(monkeypatch):
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.60)
    plain = pm_engine.distribution(state(binary=False))
    binary = pm_engine.distribution(state(binary=True))
    assert binary["expected_return"] < plain["expected_return"]
    assert binary["haircut"] < plain["haircut"]


def test_a_bear_case_is_never_rosier_than_the_base(monkeypatch):
    monkeypatch.setattr(pm_engine, "_vol", lambda t: 0.30)
    # an absurdly high analyst low must not be allowed to invent a bear case
    d = pm_engine.distribution(state(low=19.9, median=20.0))
    assert d["bear"] <= d["base"] <= d["bull"]


def test_no_target_means_no_distribution():
    assert pm_engine.distribution(state(median=None))["available"] is False


# ── the score ──────────────────────────────────────────────────────────────

def test_more_upside_scores_higher():
    a = pm_engine.analyst_alpha(state(median=15.0))
    b = pm_engine.analyst_alpha(state(median=30.0))
    assert b["score"] > a["score"]


def test_downgrades_and_staleness_cut_the_score():
    fresh = pm_engine.analyst_alpha(state(net=3, days=10, drift=0.2))
    stale = pm_engine.analyst_alpha(state(net=-3, days=400, drift=-0.2))
    assert stale["score"] < fresh["score"]


def test_penalties_are_itemised_not_hidden():
    s = pm_engine.analyst_alpha(state(binary=True, adv=100.0, price=2.0))
    p = s["penalties"]
    assert p["binary_event"] > 0 and p["liquidity"] > 0 and p["sub_5_dollar"] > 0
    assert p["total"] == pytest.approx(
        sum(v for k, v in p.items() if k != "total"), abs=1e-9)


def test_a_name_trading_above_its_target_scores_zero():
    assert pm_engine.analyst_alpha(state(price=30.0, median=20.0))["score"] == 0


# ── sizing ─────────────────────────────────────────────────────────────────

def test_allocation_preserves_ordering_and_respects_the_cap():
    mode = pm_engine.MODES["high_growth"]
    raw = {"A": 3.0, "B": 2.0, "C": 1.0, "D": 0.5, "E": 0.4, "F": 0.3,
           "G": 0.2, "H": 0.1}
    w = pm_actions.allocate(raw, mode)
    assert all(v <= mode["max_weight"] + 1e-9 for v in w.values())
    assert w["A"] >= w["B"] >= w["C"] >= w["D"]
    # a book cannot invest more than (names x cap), so the budget is whichever
    # of the two binds
    want = min(1.0 - mode["min_cash"], len(raw) * mode["max_weight"])
    assert sum(w.values()) == pytest.approx(want, abs=0.01)


def test_a_capped_book_does_not_collapse_to_equal_weight():
    """Capping before normalising made every name identical. It must not."""
    mode = pm_engine.MODES["growth"]
    w = pm_actions.allocate({c: v for c, v in
                             zip("ABCDEFGHIJKL", range(12, 0, -1))}, mode)
    assert len({round(v, 4) for v in w.values()}) > 3


def test_a_negative_expected_return_gets_no_weight():
    mode = pm_engine.MODES["growth"]
    d = {"available": True, "expected_return": -0.05, "annual_vol": 0.4}
    assert pm_actions.target_weight(d, {"score": 0.2}, mode) == 0.0


def test_moonshot_changes_risk_not_evidence():
    g, m = pm_engine.MODES["growth"], pm_engine.MODES["moonshot"]
    d = {"available": True, "expected_return": 0.30, "annual_vol": 0.60}
    a = {"score": 0.5}
    assert pm_actions.target_weight(d, a, m) > pm_actions.target_weight(d, a, g)
    assert m["max_weight"] > g["max_weight"]


# ── instructions ───────────────────────────────────────────────────────────

def test_small_drifts_do_not_become_tickets():
    r = pm_actions.action_for(0.100, 0.105, 45_000)
    assert r["action"] == "HOLD" and r["dollars"] == 0


def test_a_ticket_below_the_minimum_is_not_a_ticket():
    r = pm_actions.action_for(0.10, 0.13, 5_000)      # $150
    assert r["action"] == "HOLD"


def test_no_data_is_a_review_not_a_sale():
    """The engine must never sell a position it simply cannot see."""
    r = pm_actions.action_for(0.05, 0.0, 45_000, decisionable=False)
    assert r["action"] == "REVIEW" and r["dollars"] == 0


def test_a_zero_target_on_a_visible_name_is_a_sale():
    r = pm_actions.action_for(0.05, 0.0, 45_000, decisionable=True)
    assert r["action"] == "SELL" and r["dollars"] == pytest.approx(-2250)


def test_replacement_edge_names_who_funds_the_trade():
    c = {"ticker": "NEW", "alpha": {"score": 0.60},
         "distribution": {"available": True, "expected_return": 0.40,
                          "annual_vol": 0.50}}
    h = {"ticker": "OLD", "alpha": {"score": 0.10},
         "distribution": {"available": True, "expected_return": 0.05,
                          "annual_vol": 0.50}}
    e = pm_actions.replacement_edge(c, h, switch_cost=0.004)
    assert e["verdict"] == "SWITCH" and e["funded_by"] == "OLD"
    # same vol on both sides, so the CE difference is the mu difference
    assert e["gross_edge"] == pytest.approx(0.35)
    assert e["replacement_edge"] == pytest.approx(0.35 - 0.004)


def test_a_marginal_edge_does_not_justify_a_switch():
    c = {"ticker": "NEW", "alpha": {"score": 0.12},
         "distribution": {"available": True, "expected_return": 0.11,
                          "annual_vol": 0.50}}
    h = {"ticker": "OLD", "alpha": {"score": 0.10},
         "distribution": {"available": True, "expected_return": 0.10,
                          "annual_vol": 0.50}}
    assert pm_actions.replacement_edge(c, h)["verdict"] == "STAY"


# ── the wealth question ────────────────────────────────────────────────────

def rows(k=6, mu=0.25, vol=0.55, w=0.15):
    return [{"ticker": f"T{i}", "proposed": {"target_weight": w},
             "distribution": {"available": True, "expected_return": mu,
                              "annual_vol": vol, "bear": -0.4, "base": mu,
                              "bull": 0.9}} for i in range(k)]


def test_the_target_is_never_reported_without_the_downside():
    w = pm_actions.simulate_wealth(rows(), 45_000, 0,
                                   {"horizon_months": 12,
                                    "target_value": 100_000,
                                    "floor_value": 30_000,
                                    "ruin_value": 20_000})
    for k in ("p_reach_target", "p_below_floor", "p_below_ruin",
              "expected_max_drawdown", "health_warning"):
        assert w[k] is not None


def test_the_drawdown_is_a_path_not_a_terminal_proxy():
    """A book of 55%-vol names cannot have a -8% expected max drawdown."""
    w = pm_actions.simulate_wealth(rows(), 45_000, 0,
                                   {"horizon_months": 12,
                                    "target_value": 100_000})
    assert w["expected_max_drawdown"] < -0.15
    assert w["worst_5pct_max_drawdown"] < w["median_max_drawdown"]


def test_more_risk_raises_both_the_upside_and_the_ruin_probability():
    t = {"horizon_months": 12, "target_value": 100_000,
         "floor_value": 30_000, "ruin_value": 20_000}
    calm = pm_actions.simulate_wealth(rows(vol=0.35), 45_000, 0, t)
    wild = pm_actions.simulate_wealth(rows(vol=0.95), 45_000, 0, t)
    assert wild["p_reach_target"] > calm["p_reach_target"]
    assert wild["p_below_ruin"] > calm["p_below_ruin"]


def test_the_required_return_is_arithmetic_not_a_forecast():
    w = pm_actions.simulate_wealth(rows(), 45_000, 0,
                                   {"target_value": 100_000})
    assert w["required_return_for_target"] == pytest.approx(100 / 45 - 1, abs=1e-3)


def test_an_empty_book_refuses_rather_than_inventing_a_number():
    assert pm_actions.simulate_wealth([], 45_000, 0, {})["available"] is False


# ── the book file ──────────────────────────────────────────────────────────

def test_the_shipped_book_is_marked_unconfirmed():
    """Reconstructed placeholders must never be presented as real positions."""
    b = pm_engine.load_book()
    assert b.confirmed is False
    assert b.positions and b.watchlist
    assert b.wealth_targets["target_value"] > b.wealth_targets["floor_value"]


def test_every_position_carries_a_thesis_and_a_recorded_kill_condition_gap():
    """A thesis is required. A kill condition is required to be HONEST.

    The reconciled book (2026-08-11) recovered five names — ABSI, AMSC, HUBS,
    KYTX, SLDP — that the January reconstruction never covered. The conviction
    log carries Murat's own rationale for them, so a thesis exists. No source
    states an exit rule, and inventing a plausible-sounding one would be worse
    than admitting the gap, so the reconciler records it as unrecoverable
    instead.
    """
    import json
    from pathlib import Path

    missing_kill: list[str] = []
    for p in pm_engine.load_book().positions:
        assert p.thesis, f"{p.ticker}: no thesis from any source"
        if not p.kill_condition:
            missing_kill.append(p.ticker)

    if missing_kill:
        rep = json.loads(
            (Path(__file__).resolve().parents[2] / "docs"
             / "portfolio_reconciliation.json").read_text(encoding="utf-8"))
        recorded = {u["ticker"] for u in rep["unrecoverable"]
                    if u.get("field") == "kill_condition"}
        assert set(missing_kill) <= recorded, (
            f"{sorted(set(missing_kill) - recorded)} have no exit rule and the "
            f"reconciliation does not say so — an invisible gap is the bug")
