"""The funnel must not smuggle a killed signal in, or hide what it dropped.

The failure this file guards against is not a wrong number. It is a funnel that
returns twenty-five confident names ranked by something the lab has already
measured as negative, or that silently becomes a watchlist view when a feed
goes down.
"""
from __future__ import annotations

import json

import pytest

from backend.services import opportunity_funnel as F


@pytest.fixture(autouse=True)
def clean():
    F.STAGE_FAILURES.clear()
    yield
    F.STAGE_FAILURES.clear()


def _cand(t, *, mdv=5e6, vol=0.3, quality=None, mom=0.2, price=20.0):
    return F.Candidate(ticker=t, price=price, median_dollar_vol=mdv,
                       vol_annual=vol, mom_12_1=mom, quality=quality)


# ─────────────────────────── the evidence rules ─────────────────────────────

def test_no_closed_signal_may_order_the_funnel():
    """The assertion lives in stage2; this proves it is load-bearing."""
    from backend.services import signal_registry as SR
    reg = SR.load()
    for closed in ("momentum_12_1", "reversal_dip", "analyst_target_upside_xs"):
        assert not reg.permits(closed, "PICKER")


def test_momentum_is_recorded_but_never_ranked_on():
    cands = [_cand("AAA", mom=0.90, vol=0.5), _cand("BBB", mom=-0.50, vol=0.2)]
    out = F.stage2(cands, keep=2)
    by = {c.ticker: c for c in out}
    # BBB has far worse momentum and lower vol; low-vol is the only permitted
    # ordering input, so BBB must score higher.
    assert by["BBB"].score > by["AAA"].score
    assert any("momentum_12_1 is CLOSED" in b for b in by["AAA"].blocked_by)


def test_analyst_upside_is_recorded_as_blocked_not_as_a_rank(monkeypatch):
    monkeypatch.setattr(F, "_fundamentals", lambda t: (
        {"gross_profitability": 0.3, "sector": "X", "market_cap": 1e9,
         "target": 40.0, "n_analysts": 5, "source": "test"}, "ok"))
    c = _cand("AAA", price=20.0)
    c.why.append("size band 1 of 5")
    out = F.stage3([c], keep=1, budget=1)
    assert out and out[0].analyst_upside == pytest.approx(1.0)
    assert any("CLOSED/PERVERSE" in b for b in out[0].blocked_by)
    assert any("does NOT rank" in b for b in out[0].blocked_by)


def test_every_survivor_says_why_it_survived(monkeypatch):
    monkeypatch.setattr(F, "_fundamentals", lambda t: (
        {"gross_profitability": 0.4, "sector": "X", "market_cap": 1e9,
         "target": None, "n_analysts": None, "source": "test"}, "ok"))
    cands = [_cand(f"T{i:02d}", mdv=(i + 1) * 3e6, vol=0.2 + i * 0.01)
             for i in range(10)]
    s2 = F.stage2(cands, keep=10)
    s3 = F.stage3(s2, keep=5, budget=10)
    s4 = F.stage4(s3, keep=3)
    assert s4
    for c in s4:
        assert c.why, f"{c.ticker} survived with no reason"
        assert any("liquidity" in w for w in c.why)


# ────────────────────────── fail loud, not empty ────────────────────────────

def test_a_dead_universe_call_raises_rather_than_falling_back(monkeypatch):
    monkeypatch.setattr("backend.services.pm_catalysts._finnhub",
                        lambda p, q: None)
    monkeypatch.setattr(F, "_read_cache", lambda name, ttl: None)
    with pytest.raises(F.FunnelError) as e:
        F.universe(force=True)
    assert "refuses to fall back to the watchlist" in str(e.value)
    assert "stage0" in F.STAGE_FAILURES


def test_no_price_history_raises_rather_than_returning_no_opportunities(
        monkeypatch):
    import pandas as pd
    monkeypatch.setattr(F, "_batch_history", lambda t, period="1y": {
        "close": pd.DataFrame(), "volume": pd.DataFrame(), "failed_batches": 3})
    with pytest.raises(F.FunnelError) as e:
        F.stage1(["AAA", "BBB"])
    assert "outage, not an empty market" in str(e.value)


def test_stage3_records_why_each_enrichment_failed(monkeypatch):
    monkeypatch.setattr(F, "_fundamentals",
                        lambda t: (None, "finnhub HTTP 429"))
    c = _cand("AAA")
    c.why.append("size band 1 of 5")
    out = F.stage3([c, _cand("BBB")], keep=5, budget=5)
    assert out == []
    assert "stage3" in F.STAGE_FAILURES
    assert "429" in F.STAGE_FAILURES["stage3"]


def test_stage4_with_no_profitability_returns_nothing_and_says_so():
    cands = [_cand("AAA", quality=None), _cand("BBB", quality=None)]
    assert F.stage4(cands) == []
    assert "no permitted picker" in F.STAGE_FAILURES["stage4"]


def test_a_truncated_stage1_is_reported(monkeypatch):
    import numpy as np
    import pandas as pd
    n = 30
    idx = pd.date_range("2025-01-01", periods=300, freq="D")
    close = pd.DataFrame({f"T{i:02d}": np.linspace(10, 20, 300) for i in range(n)},
                         index=idx)
    vol = pd.DataFrame({f"T{i:02d}": np.full(300, 1e6) for i in range(n)},
                       index=idx)
    monkeypatch.setattr(F, "_batch_history", lambda t, period="1y": {
        "close": close, "volume": vol, "failed_batches": 0})
    out = F.stage1(["x"], keep=5)
    assert len(out) == 5
    assert "stage1_truncated" in F.STAGE_FAILURES
    assert "never scored" in F.STAGE_FAILURES["stage1_truncated"]


# ─────────────────────── size must not become a picker ──────────────────────

def test_the_shortlist_is_stratified_so_size_cannot_pick():
    """The first version ranked on log(dollar volume) and returned the S&P 20."""
    cands = [_cand(f"T{i:03d}", mdv=(i + 1) * 1e6, vol=0.3) for i in range(100)]
    out = F.stage2(cands, keep=25)
    mdvs = sorted(c.median_dollar_vol for c in out)
    assert mdvs[0] < 2e7, "the shortlist must reach small names"
    assert mdvs[-1] > 8e7, "and large ones"
    assert any("size band" in w for c in out for w in c.why)


def test_liquidity_is_a_gate_not_a_score():
    """Two names identical but for dollar volume must score the SAME."""
    a, b = _cand("AAA", mdv=3e6, vol=0.3), _cand("BBB", mdv=3e10, vol=0.3)
    out = F.stage2([a, b], keep=2)
    scores = {c.ticker: c.score for c in out}
    assert scores["AAA"] == pytest.approx(scores["BBB"]), (
        "$30bn/day is not more eligible than $3m/day for a $45k account")


def test_interleave_makes_any_prefix_span_the_size_range():
    cands = []
    for band in range(1, 6):
        for j in range(4):
            c = _cand(f"B{band}N{j}")
            c.why.append(f"size band {band} of 5")
            cands.append(c)
    order = F._interleave(cands)
    bands = {next(w for w in c.why if w.startswith("size band")) for c in order[:5]}
    assert len(bands) == 5, "the first five must touch every band"


def test_stage3_budget_is_a_hard_cap(monkeypatch):
    calls = {"n": 0}

    def fake(t):
        calls["n"] += 1
        return {"gross_profitability": 0.2, "sector": "", "market_cap": 1e9,
                "target": None, "n_analysts": None, "source": "test"}, "ok"

    monkeypatch.setattr(F, "_fundamentals", fake)
    cands = [_cand(f"T{i:03d}") for i in range(500)]
    F.stage3(cands, keep=1000, budget=12)
    assert calls["n"] <= 12, "the per-ticker stage must never run away"


class TestMarketCapCurrency:
    """Finnhub reports market cap in the company's REPORTING currency.

    Multiplying by 1e6 and calling it USD overstated IBN by 95x (INR), TSM by
    28x (TWD) and FMX by 6x (MXN). Market cap decides which cap band a name is
    in, and therefore which signals `recommendation.in_universe` will license
    to score it — so a wrong cap silently applies the wrong evidence.
    """

    def _profile(self, monkeypatch, profile, metric=None):
        from backend.services import opportunity_funnel as F

        def fake(path, params=None):
            if path == "stock/metric":
                return {"metric": metric or {"grossMarginTTM": 40.0,
                                             "assetTurnoverTTM": 1.0}}
            if path == "stock/profile2":
                return profile
            return {}

        monkeypatch.setattr("backend.services.pm_catalysts._finnhub", fake)
        return F._fundamentals("TEST")

    def test_usd_market_cap_is_scaled_to_dollars(self, monkeypatch):
        out, why = self._profile(
            monkeypatch, {"marketCapitalization": 842.72, "currency": "USD"})
        assert why == "ok"
        assert out["market_cap"] == pytest.approx(842.72e6)

    def test_foreign_currency_market_cap_is_unknown_not_converted(self, monkeypatch):
        out, why = self._profile(
            monkeypatch, {"marketCapitalization": 61_459_714.86,
                          "currency": "TWD"})
        assert why == "ok"
        assert out["market_cap"] is None, (
            "a TWD market cap read as USD put TSM at $61 trillion")
        assert "TWD" in out["market_cap_note"]

    def test_missing_market_cap_records_a_reason(self, monkeypatch):
        out, _why = self._profile(monkeypatch, {"currency": "USD"})
        assert out["market_cap"] is None
        assert out["market_cap_note"]

    def test_unknown_cap_denies_a_size_limited_signal(self):
        """The downstream consequence, asserted end to end."""
        from backend.services import recommendation as REC
        from backend.services import signal_registry as SR
        reg = SR.load()
        ok, why = REC.in_universe(reg.get("profitability_small"), None)
        assert ok is False and "unknown" in why.lower()
