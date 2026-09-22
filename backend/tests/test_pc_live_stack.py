"""The PC live stack's safety properties — the ones that cost money if wrong.

These are not coverage tests. Each one pins a property that, if it silently
stopped holding, would either lose real paper capital or manufacture a false
research result:

* the broker has no real-money path and cannot be given one by an env var;
* the book cannot lever, cannot short, cannot concentrate, cannot be the tape;
* the ranker's target is strictly FORWARD of its features (no leakage);
* the walk-forward purge is at least one horizon wide (no overlapping labels);
* a survivor-selected panel is DETECTED rather than silently ranked over;
* "no measurement yet" permits a small position, and "measured negative"
  forbids one — the distinction Murat asked for on 2026-09-22.

Everything here is offline. `pc_broker`'s network calls are never exercised.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from backend.services import pc_broker as PB
from backend.services import xs_ranker as XR
from scripts.live_market_loop import _ranking_verdict


# ───────────────────────────── the broker ───────────────────────────────────

def test_live_host_is_refused_even_when_an_env_var_asks_for_it(monkeypatch):
    monkeypatch.setenv("AEGIS_PC_TRADING_HOST", "https://api.alpaca.markets")
    with pytest.raises(PB.BrokerError, match="not a paper host"):
        PB._host()


def test_paper_host_is_the_default():
    assert "paper-api" in PB._host()


def test_missing_credentials_refuse_loudly_and_name_both_variables(monkeypatch):
    monkeypatch.delenv(PB.KEY_ENV, raising=False)
    monkeypatch.delenv(PB.SECRET_ENV, raising=False)
    with pytest.raises(PB.BrokerError) as exc:
        PB.credentials()
    assert PB.KEY_ENV in str(exc.value) and PB.SECRET_ENV in str(exc.value)


def test_no_other_roles_credential_is_substituted(monkeypatch):
    """A fallback to another account's key is how one book trades another's."""
    monkeypatch.delenv(PB.KEY_ENV, raising=False)
    monkeypatch.delenv(PB.SECRET_ENV, raising=False)
    monkeypatch.setenv("ALPACA_KEY_2", "hack2key")
    monkeypatch.setenv("ALPACA_SECRET_2", "hack2secret")
    with pytest.raises(PB.BrokerError):
        PB.credentials()


def test_the_mandate_constants_cannot_express_leverage():
    assert PB.MAX_INVESTED_FRAC <= 1.0
    assert 0 < PB.MAX_NAME_FRAC < 0.20, "must sit below the Challenge's 20% cap"


def _plan(targets, equity=100_000.0, held=None, prices=None):
    return PB.plan_orders(targets, equity=equity, held=held or {},
                          prices=prices or {})


def test_gross_exposure_never_exceeds_equity():
    tg = [PB.Target(f"S{i}", 0.25, "x", median_dollar_vol=1e9) for i in range(8)]
    prices = {f"S{i}": 100.0 for i in range(8)}
    plans = _plan(tg, prices=prices)
    buys = sum(p.notional for p in plans if p.side == "buy")
    assert buys <= 100_000.0 * PB.MAX_INVESTED_FRAC + 1e-6, (
        f"2.0x of targets was not scaled back to the mandate: ${buys:,.0f}")


def test_a_negative_weight_is_never_sent_as_a_short():
    plans = _plan([PB.Target("AAA", -0.50, "short me", median_dollar_vol=1e9)],
                  prices={"AAA": 50.0})
    assert not [p for p in plans if p.side == "sell" and p.qty > 0]


def test_single_name_is_capped_and_the_clip_is_reported():
    plans = _plan([PB.Target("AAA", 0.90, "all in", median_dollar_vol=1e12)],
                  prices={"AAA": 10.0})
    p = next(x for x in plans if x.symbol == "AAA")
    assert p.notional <= 100_000.0 * PB.MAX_NAME_FRAC + 10.0
    assert p.refused and "MAX_NAME_FRAC" in p.refused


def test_an_order_cannot_be_the_tape():
    """A thin name is capped at a fraction of its own median dollar volume."""
    plans = _plan([PB.Target("THIN", 0.12, "rank 1", median_dollar_vol=100_000.0)],
                  prices={"THIN": 5.0})
    p = next(x for x in plans if x.symbol == "THIN")
    assert p.notional <= 100_000.0 * PB.MAX_ADV_PARTICIPATION + 5.0
    assert p.refused and "median $vol" in p.refused


def test_a_name_with_no_price_is_refused_not_sized_at_zero():
    plans = _plan([PB.Target("NOPX", 0.10, "rank 1", median_dollar_vol=1e9)],
                  prices={})
    p = next(x for x in plans if x.symbol == "NOPX")
    assert p.qty == 0 and "no price" in (p.refused or "")


def test_a_held_name_absent_from_the_book_is_exited():
    plans = _plan([PB.Target("KEEP", 0.10, "rank 1", median_dollar_vol=1e9)],
                  held={"GONE": 100.0}, prices={"KEEP": 10.0, "GONE": 20.0})
    gone = next(x for x in plans if x.symbol == "GONE")
    assert gone.side == "sell" and gone.qty == 100


def test_sells_are_planned_before_buys():
    plans = _plan([PB.Target("BUYME", 0.10, "rank 1", median_dollar_vol=1e9)],
                  held={"SELLME": 100.0},
                  prices={"BUYME": 10.0, "SELLME": 20.0})
    sides = [p.side for p in plans if p.qty > 0]
    assert sides.index("sell") < sides.index("buy"), (
        "buying before selling spends buying power the account has not freed")


def test_lease_detects_a_foreign_fill(monkeypatch):
    """A fill without our prefix after the lease opened means a second owner."""
    lease = {"opened": "2026-09-22T13:00:00+00:00"}
    monkeypatch.setattr(PB, "orders", lambda **kw: [
        {"id": "1", "client_order_id": f"{PB.LEASE_PREFIX}-ours",
         "submitted_at": "2026-09-22T14:00:00+00:00", "symbol": "AAA"},
        {"id": "2", "client_order_id": "railway-loop-xyz",
         "submitted_at": "2026-09-22T15:00:00+00:00", "symbol": "BBB"},
    ])
    v = PB.check_lease(lease)
    assert v["conflict"] and v["n_foreign_orders"] == 1
    assert v["foreign"][0]["symbol"] == "BBB"


def test_lease_ignores_orders_that_predate_it(monkeypatch):
    lease = {"opened": "2026-09-22T13:00:00+00:00"}
    monkeypatch.setattr(PB, "orders", lambda **kw: [
        {"id": "0", "client_order_id": "old-railway-order",
         "submitted_at": "2026-09-20T15:00:00+00:00", "symbol": "OLD"},
    ])
    assert PB.check_lease(lease)["conflict"] is False


# ───────────────────────────── the ranker ───────────────────────────────────

def _toy_bars(n_sym: int = 60, n_days: int = 420, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    rows = []
    for i in range(n_sym):
        px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, n_days)))
        vol = rng.integers(200_000, 5_000_000, n_days)
        rows.append(pd.DataFrame({
            "symbol": f"T{i:03d}", "date": dates, "open": px * 0.999,
            "high": px * 1.01, "low": px * 0.99, "close": px,
            "volume": vol, "vwap": px, "trades": vol // 100}))
    return pd.concat(rows, ignore_index=True)


def test_the_target_is_strictly_forward_of_the_features():
    """Shifting every price AFTER date t must not change a feature dated t.

    This is the leakage test that matters. If any feature reads a future bar,
    perturbing the tail of the series changes a row it must not touch.
    """
    bars = _toy_bars()
    cut = bars["date"].unique()[300]
    feats_a = XR.build_features(bars)

    tampered = bars.copy()
    mask = tampered["date"] > cut
    for c in ("open", "high", "low", "close", "vwap"):
        tampered.loc[mask, c] *= 3.0
    feats_b = XR.build_features(tampered)

    a = feats_a[feats_a["date"] <= cut][list(XR.FEATURES)].reset_index(drop=True)
    b = feats_b[feats_b["date"] <= cut][list(XR.FEATURES)].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9)


def test_the_forward_window_starts_after_the_decision_date():
    bars = _toy_bars(n_sym=5, n_days=300)
    panel = XR.build_panel(bars)
    one = panel[panel["symbol"] == "T000"].sort_values("date").reset_index(drop=True)
    i = 150
    entry = one.loc[i + 1, "open"]
    exit_ = one.loc[i + 1 + XR.HORIZON_SESSIONS, "close"]
    assert one.loc[i, "fwd_ret"] == pytest.approx(exit_ / entry - 1.0, rel=1e-9)


def test_the_purge_is_at_least_one_horizon_wide():
    """Overlapping 21-session labels leak unless the purge covers the horizon."""
    assert XR.PURGE_SESSIONS >= XR.HORIZON_SESSIONS
    dates = pd.bdate_range("2024-01-01", periods=400).values
    for tr_end, te_start, _ in XR.make_folds(dates, n_folds=3):
        gap = np.busday_count(np.datetime64(tr_end, "D"), np.datetime64(te_start, "D"))
        assert gap >= XR.HORIZON_SESSIONS, f"purge only {gap} sessions wide"


def test_a_survivor_selected_panel_is_detected():
    """Every symbol trading to the last day cannot happen in a real universe."""
    bars = _toy_bars(n_sym=20, n_days=300)
    audit = XR.survivorship_audit(bars)
    assert audit["stopped_90d_before_end"] == 0
    assert "SURVIVOR-SELECTED" in audit["verdict"]


def test_a_panel_with_delistings_passes_the_audit():
    bars = _toy_bars(n_sym=20, n_days=300)
    dead = bars["symbol"].isin({f"T{i:03d}" for i in range(6)})
    cutoff = bars["date"].max() - pd.Timedelta(days=200)
    bars = bars[~(dead & (bars["date"] > cutoff))]
    audit = XR.survivorship_audit(bars)
    assert audit["stopped_90d_before_end"] == 6
    assert "SURVIVOR-SELECTED" not in audit["verdict"]


def test_load_bars_concatenates_panels_without_duplicating_a_symbol(tmp_path):
    a = _toy_bars(n_sym=3, n_days=60)
    pa, pb = tmp_path / "a.parquet", tmp_path / "b.parquet"
    a.to_parquet(pa, index=False)
    a.to_parquet(pb, index=False)          # the SAME rows twice
    merged = XR.load_bars([pa, pb])
    assert len(merged) == len(a), "a re-pull silently doubled a symbol's history"


def test_index_proxies_are_never_ranked_as_stocks():
    bars = _toy_bars(n_sym=4, n_days=300)
    bars.loc[bars["symbol"] == "T000", "symbol"] = "SPY"
    panel = XR.build_panel(bars)
    assert not panel.loc[panel["symbol"] == "SPY", "eligible"].any()


# ──────────────────────── the trade / don't-trade line ──────────────────────

def _cal(measured: bool, mean: float | None) -> dict:
    return {"deciles": [{"decile": 9, "measured": measured,
                         "mean_rel_return": mean, "p20_rel_return": -0.05,
                         "hit_rate": 0.55, "why_unmeasured": None if measured else "too few blocks"}],
            "ic_mean": 0.01}


def test_an_unmeasured_ranking_may_still_be_traded():
    """Murat 2026-09-22: uncertainty sizes the book; it does not veto it."""
    v = _ranking_verdict(_cal(False, None), {"k": 20, "mean_net_rel_21d": None})
    assert v["may_trade"] is True
    assert v["verdict"] == "UNMEASURED_TRADE_SMALL"


def test_a_measured_negative_ranking_is_refused():
    """Not timidity: a measured loser is evidence, not uncertainty."""
    v = _ranking_verdict(_cal(True, -0.01),
                         {"k": 20, "mean_net_rel_21d": -0.043, "n_blocks": 7})
    assert v["may_trade"] is False
    assert v["verdict"] == "MEASURED_NEGATIVE"


def test_a_measured_positive_ranking_needs_no_significance():
    """PRODUCT_EXPERIMENT: no p-value gate stands between paper and a decision."""
    v = _ranking_verdict(_cal(True, 0.01),
                         {"k": 20, "mean_net_rel_21d": 0.004,
                          "n_blocks": 7, "t_across_blocks": 0.9})
    assert v["may_trade"] is True
    assert v["verdict"] == "MEASURED_POSITIVE"


# ───────────────────── what the night may change about itself ───────────────

from backend.services import policy_state as POLICY       # noqa: E402


def test_a_risk_limit_is_not_a_preference(monkeypatch, tmp_path):
    """The night can move preferences; it cannot widen its own sizing bounds.

    2026-08-28: twelve names x 25% = 300% gross on a 3% stop cost -9%, and the
    'fix' that widened the stop took the worst case to -24%. A loop that can
    edit that overnight is the same failure with nobody watching.
    """
    monkeypatch.setattr(POLICY, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(POLICY, "JOURNAL_PATH", tmp_path / "j.jsonl")
    for key in ("max_invested_frac", "MAX_NAME_FRAC", "stop_pct"):
        with pytest.raises(POLICY.PolicyRefused, match="not declared mutable"):
            POLICY.update(key, 2.0, reason="r", evidence="e")


def test_a_declared_preference_cannot_leave_its_range(monkeypatch, tmp_path):
    monkeypatch.setattr(POLICY, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(POLICY, "JOURNAL_PATH", tmp_path / "j.jsonl")
    with pytest.raises(POLICY.PolicyRefused, match="outside its declared range"):
        POLICY.update("book_size", 500, reason="bigger is better", evidence="x")


def test_a_change_without_evidence_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(POLICY, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(POLICY, "JOURNAL_PATH", tmp_path / "j.jsonl")
    with pytest.raises(POLICY.PolicyRefused, match="needs EVIDENCE"):
        POLICY.update("book_size", 20, reason="felt right", evidence=None)


def test_a_legitimate_change_is_journalled_with_old_and_new(monkeypatch, tmp_path):
    monkeypatch.setattr(POLICY, "STATE_PATH", tmp_path / "s.json")
    monkeypatch.setattr(POLICY, "JOURNAL_PATH", tmp_path / "j.jsonl")
    row = POLICY.update("book_size", 22, reason="top-20 beat top-10 net",
                        evidence={"receipt": "bakeoff.json"})
    assert row["old"] == 18 and row["new"] == 22
    assert POLICY.load()["book_size"] == 22
    assert len(POLICY.journal()) == 1


def test_defaults_survive_an_unreadable_state_file(monkeypatch, tmp_path):
    bad = tmp_path / "s.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(POLICY, "STATE_PATH", bad)
    assert POLICY.load() == POLICY.defaults(), "a corrupt preference file must not halt the night"
