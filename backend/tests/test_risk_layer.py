"""M6's guard rails: the page cannot say more than the measurement did."""

from __future__ import annotations

import math

import pytest

from backend.services.risk_layer import (BREAK_EVEN_SACRIFICE, EVIDENCE,
                                         MIN_OBSERVATIONS, RiskLayerRefused,
                                         RETURN_SACRIFICE_BOUND,
                                         decide_exposure, decision_log,
                                         honest_claim, realised_vol,
                                         sacrifice_bound)


def _returns(n=300, sd=0.01, seed=7):
    import random
    rng = random.Random(seed)
    return [rng.gauss(0.0004, sd) for _ in range(n)]


# ── the refusals ───────────────────────────────────────────────────────────
def test_too_few_days_refuses_rather_than_sizing_a_book_from_noise():
    with pytest.raises(RiskLayerRefused, match="size a real book from noise"):
        realised_vol(_returns(MIN_OBSERVATIONS - 1))


def test_a_claim_that_was_not_measured_cannot_be_rendered():
    with pytest.raises(RiskLayerRefused, match="no fallback that invents one"):
        EVIDENCE.claim("alpha_vs_the_market")


def test_a_break_even_at_an_undeclared_lambda_refuses():
    with pytest.raises(RiskLayerRefused, match="no break-even computed"):
        honest_claim(0.15, lam=2.5)


def test_a_misaligned_decision_log_refuses_rather_than_mislabelling_months():
    with pytest.raises(RiskLayerRefused, match="wrong month"):
        decision_log(["2020-01-02"], [0.01, 0.02], target_vol=0.15)


def test_a_nonpositive_target_or_cap_refuses():
    with pytest.raises(RiskLayerRefused):
        decide_exposure(_returns(), target_vol=0.0)
    with pytest.raises(RiskLayerRefused):
        decide_exposure(_returns(), target_vol=0.15, cap=0.0)


# ── the claim shape ────────────────────────────────────────────────────────
def test_the_return_effect_is_never_established():
    """The half that must survive every future edit."""
    c = EVIDENCE.claim("annual_return")
    assert c.established is False
    assert abs(c.effect) < c.mde
    assert honest_claim(0.15)["return_effect"]["established"] is False


def test_stock_selection_is_carried_as_an_explicit_negative():
    """Absent would read as 'not yet built'; present-and-false is the finding."""
    c = EVIDENCE.claim("stock_selection")
    assert c.established is False
    assert "does not pick stocks" in c.note


def test_utility_is_not_established_even_though_drawdown_is():
    """N18 and the risk result are both true; quoting either alone misleads."""
    assert EVIDENCE.claim("utility_vs_matched_exposure").established is False
    assert EVIDENCE.claim("max_drawdown_vs_matched_exposure").established


def test_every_established_claim_actually_clears_its_own_mde():
    """`established` is arithmetic, not editorial."""
    for c in EVIDENCE.claims:
        if c.established:
            assert c.effect is not None and c.mde is not None
            assert abs(c.effect) >= c.mde, c.outcome
        elif c.effect is not None and c.mde is not None:
            assert abs(c.effect) < c.mde, c.outcome


def test_the_window_is_labelled_explore_not_confirmed():
    assert "EXPLORE" in EVIDENCE.status
    assert EVIDENCE.k_eff < 2.0          # 8 correlated cells on one path


def test_the_evidence_record_cannot_be_edited_at_runtime():
    with pytest.raises(Exception):
        EVIDENCE.window = "1900-2000"    # type: ignore[misc]


# ── the exposure ───────────────────────────────────────────────────────────
def test_high_volatility_cuts_exposure_and_low_volatility_hits_the_cap():
    calm = decide_exposure(_returns(sd=0.005), target_vol=0.15, cap=1.0)
    wild = decide_exposure(_returns(sd=0.03), target_vol=0.15, cap=1.0)
    assert calm.weight == 1.0 and calm.capped
    assert wild.weight < 0.5 and not wild.capped


def test_the_thresholds_are_what_make_it_checkable_tomorrow():
    d = decide_exposure(_returns(sd=0.02), target_vol=0.15, cap=1.0)
    assert d.raise_to_cap_below_vol == pytest.approx(0.15)
    # Doubling volatility halves the weight, so the stated level must be 2x.
    assert d.halve_above_vol == pytest.approx(2 * 0.15 / d.weight)
    assert d.weight == pytest.approx(0.15 / d.realised_vol)


def test_at_the_cap_the_note_says_volatility_must_RISE_to_change_anything():
    d = decide_exposure(_returns(sd=0.004), target_vol=0.15, cap=1.0)
    assert d.capped and "RISE" in d.note


def test_realised_vol_uses_only_the_declared_lookback():
    """A product must report the number its evidence was computed on."""
    tail = _returns(80, sd=0.02, seed=3)
    padded = [0.0] * 500 + tail
    assert realised_vol(padded) == pytest.approx(realised_vol(tail[-60:]),
                                                 rel=1e-9)


# ── the decision log ───────────────────────────────────────────────────────
def test_the_log_scores_each_decision_on_the_month_that_FOLLOWED_it():
    import datetime as dt
    d0 = dt.date(2020, 1, 1)
    dates = [str(d0 + dt.timedelta(days=i)) for i in range(400)]
    rows = decision_log(dates, _returns(400), target_vol=0.15, n=5)
    assert 1 <= len(rows) <= 5
    for r in rows:
        assert 0.0 < r["weight"] <= 1.0
        # cost_vs_full is (w-1) x next month's return: zero only at full weight.
        expected = round((r["weight"] - 1.0) * r["market_return"], 4)
        assert r["cost_vs_full"] == pytest.approx(expected, abs=1e-4)
        assert math.isfinite(r["realised_vol"])


# ── N22: the confirmation is not pending, it is unavailable ────────────────
def test_the_page_says_confirmation_is_UNREACHABLE_not_merely_pending():
    """EXPLORE alone reads as 'confirmation coming'. On this corpus it is not.

    N22 measured the forward quantity on the forward horizon and none of the
    eight cells clears its MDE on the 74 reserved months, at either alpha. A
    status that leaves the reader expecting a confirmation is a claim about the
    future that the power check has already refuted.
    """
    assert "UNREACHABLE" in EVIDENCE.confirmation
    assert "0.44" in EVIDENCE.confirmation_note      # expected crises in 74mo


# ── N24: the bound, and its verdict as arithmetic ───────────────────────────
def test_the_sacrifice_bound_verdict_is_recomputed_not_trusted():
    """A stored verdict that stops following from its numbers must RAISE."""
    b = sacrifice_bound(3.0)
    assert b["verdict"] == "NOT_DEMONSTRATED"
    assert b["worth_it_across_the_interval"] is False
    assert b["upper_95_one_sided_drag_pct"] > b["break_even_pct"]


def test_an_editorial_RULED_OUT_cannot_survive_its_own_arithmetic(monkeypatch):
    """The half of N24 that matters six weeks from now."""
    import backend.services.risk_layer as rl
    monkeypatch.setitem(rl.RETURN_SACRIFICE_BOUND, 3.0,
                        {**rl.RETURN_SACRIFICE_BOUND[3.0],
                         "verdict": "RULED_OUT"})
    with pytest.raises(RiskLayerRefused, match="disagrees"):
        sacrifice_bound(3.0)


def test_the_bound_is_carried_beside_the_estimate_not_instead_of_it():
    """'Not established' and 'bounded above by X' are different statements and
    the page owes both — the first is about our instrument, the second about
    which values have been excluded."""
    r = honest_claim(0.15, lam=3.0)["return_effect"]
    assert r["established"] is False
    assert r["bound"]["verdict"] == "NOT_DEMONSTRATED"
    assert "short by" in r["bound"]["statement"]


def test_a_bound_at_an_undeclared_lambda_refuses():
    with pytest.raises(RiskLayerRefused, match="no sacrifice bound"):
        sacrifice_bound(2.5)


def test_the_bound_does_not_quote_a_comparison_it_loses(monkeypatch):
    """At lambda 1 the bound needs MORE data than a return claim would.

    Citing the ~95-year ratio there would be quoting a benchmark this cell is
    beaten by, which is the flattering-half habit in miniature.
    """
    s1 = sacrifice_bound(1.0)["statement"]
    s3 = sacrifice_bound(3.0)["statement"]
    assert "against the ~95" in s3
    assert "against the ~95" not in s1
    assert "longer than the ~95" in s1


def test_break_even_is_priced_from_two_measured_quantities():
    h = honest_claim(0.15, lam=1.0)
    assert h["break_even_sacrifice_pct_per_year"] == BREAK_EVEN_SACRIFICE[1.0]
    # The comparison that makes it a trade rather than a slogan.
    assert "measured return change" in h["break_even_note"]


# ═══════════════════════════════════════════════════════════════════════════
# The endpoints. Network is blocked in this suite, so the price fetch is
# replaced — what is under test is the contract, not yfinance.
# ═══════════════════════════════════════════════════════════════════════════
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend.routers import risk_layer as rlr  # noqa: E402

client = TestClient(app)


def test_evidence_endpoint_carries_the_negatives_by_name():
    r = client.get("/api/risk-layer/evidence")
    assert r.status_code == 200
    outcomes = {c["outcome"]: c for c in r.json()["evidence"]["claims"]}
    assert outcomes["annual_return"]["established"] is False
    assert outcomes["stock_selection"]["established"] is False
    assert "EXPLORE" in r.json()["evidence"]["status"]


def test_an_unpriceable_book_is_422_not_a_confident_full_exposure(monkeypatch):
    def _boom(_holdings):
        raise rlr.rl.RiskLayerRefused("no holding could be priced")
    monkeypatch.setattr(rlr, "_book_returns", _boom)
    r = client.post("/api/risk-layer/exposure",
                    json={"holdings": [{"ticker": "SPY", "weight": 1.0}]})
    assert r.status_code == 422
    assert "priced" in r.json()["detail"]


def test_an_undeclared_personality_is_refused(monkeypatch):
    r = client.post("/api/risk-layer/exposure",
                    json={"holdings": [{"ticker": "SPY", "weight": 1.0}],
                          "personality": "yolo"})
    assert r.status_code == 422


def test_the_exposure_payload_never_names_a_ticker_to_buy(monkeypatch):
    """The shape of the product, asserted. A future 'top pick' field would have
    to break this test to get onto the page."""
    import datetime as dt
    import random
    rng = random.Random(11)
    d0 = dt.date(2024, 1, 1)
    dates = [str(d0 + dt.timedelta(days=i)) for i in range(400)]
    rets = [rng.gauss(0.0004, 0.011) for _ in range(400)]
    monkeypatch.setattr(rlr, "_book_returns", lambda _h: (dates, rets, []))
    r = client.post("/api/risk-layer/exposure",
                    json={"holdings": [{"ticker": "SPY", "weight": 0.6},
                                       {"ticker": "QQQ", "weight": 0.4}],
                          "target_vol": 0.15, "personality": "balanced"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"decision", "decision_log", "claim", "personality",
                         "unpriced_holdings", "what_would_change_it"}
    assert 0.0 < body["decision"]["weight"] <= 1.0
    assert body["claim"]["return_effect"]["established"] is False
    assert "volatility" in body["what_would_change_it"]["statement"]

    # No FIELD anywhere holds a recommended security. Checked on keys, not on
    # the serialised blob: the first version scanned for "buy" and tripped on
    # the comparator "buy and hold", which is a legitimate name for the thing
    # being measured against. A test that fires on its own vocabulary gets
    # deleted, and then it protects nothing.
    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)

    banned = {"buy", "sell", "top_pick", "picks", "recommended_ticker",
              "recommendation", "signal", "conviction", "target_price"}
    assert not (banned & set(keys(body)))
