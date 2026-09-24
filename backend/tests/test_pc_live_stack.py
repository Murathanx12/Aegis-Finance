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
    # every accepted spelling, not just the canonical one: `.env` carries the
    # pair as `PC-PAPER_key` / `PC-PAPER_secret`
    for k in (*PB.KEY_ALTS, *PB.SECRET_ALTS):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(PB.BrokerError) as exc:
        PB.credentials()
    assert PB.KEY_ENV in str(exc.value) and PB.SECRET_ENV in str(exc.value)


def test_no_other_roles_credential_is_substituted(monkeypatch):
    """A fallback to another account's key is how one book trades another's."""
    for k in (*PB.KEY_ALTS, *PB.SECRET_ALTS):
        monkeypatch.delenv(k, raising=False)
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


# ──────────────── the simulation's safe stop, and its resume ────────────────

from backend.services import sim_session as SS                # noqa: E402


@pytest.fixture
def sim_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(SS, "STATE_DIR", tmp_path)
    monkeypatch.setattr(SS, "SESSION_PATH", tmp_path / "session.json")
    monkeypatch.setattr(SS, "STOP_FLAG", tmp_path / "STOP_REQUESTED")
    monkeypatch.setattr(SS, "HISTORY_PATH", tmp_path / "sessions.jsonl")
    # The fake launcher returns a pid that does not exist, and `status()`
    # correctly reads a dead pid as UNCLEAN. Tests about the RUNNING path
    # therefore have to say the process is alive; the one test that is ABOUT
    # a vanished process overrides this back to False.
    monkeypatch.setattr(SS, "pid_alive", lambda pid: True)
    return tmp_path


def _fake_launch(session):
    return 424242


def test_a_duration_outside_the_declared_set_is_refused(sim_tmp):
    """An arbitrary duration is how a quick test becomes a 40-hour run."""
    with pytest.raises(SS.SimRefused, match="must be one of"):
        SS.start(hours=7, launcher=_fake_launch)


def test_two_sessions_cannot_run_at_once(sim_tmp):
    """One session owns the GPU and the broker lease."""
    SS.start(hours=6, launcher=_fake_launch)
    monkey = SS.status()
    assert monkey["state"] == "RUNNING"
    with pytest.raises(SS.SimRefused, match="already RUNNING"):
        SS.start(hours=6, launcher=_fake_launch)


def test_a_stop_is_requested_not_executed(sim_tmp):
    """`request_stop` must NOT kill anything — it raises a flag the loop reads."""
    SS.start(hours=6, launcher=_fake_launch)
    r = SS.request_stop(reason="test")
    assert r["ok"] and r["state"] == "STOPPING"
    assert SS.stop_requested() is True
    go, why = SS.should_continue(SS.status()["session"])
    assert go is False and why == "stop requested"


def test_the_loop_keeps_going_until_asked(sim_tmp):
    SS.start(hours=6, launcher=_fake_launch)
    go, why = SS.should_continue(SS.status()["session"])
    assert go is True, why


def test_a_checkpoint_survives_the_stop_and_is_resumable(sim_tmp):
    SS.start(hours=6, launcher=_fake_launch)
    SS.record_cycle(3, {"units": {"rank": {"ok": True}}, "elapsed_s": 12.0})
    SS.finish("STOPPED", "stop requested", {"final_cycle": 3})
    st = SS.status()
    assert st["state"] == "STOPPED"
    assert st["resumable"] is True
    assert st["session"]["checkpoint"]["cycle"] == 3


def test_a_resume_keeps_the_session_id_and_counts_itself(sim_tmp):
    SS.start(hours=6, launcher=_fake_launch)
    first = SS.status()["session"]["id"]
    SS.record_cycle(2, {"units": {}, "elapsed_s": 1.0})
    SS.finish("STOPPED", "stop requested", {"final_cycle": 2})
    s = SS.start(hours=6, resume=True, launcher=_fake_launch)
    assert s["id"] == first, "a resume that renames the session loses its history"
    assert s["resume_count"] == 1
    assert s["cycle"] == 2


def test_a_resume_into_a_different_configuration_is_refused(sim_tmp):
    SS.start(hours=6, mode="observe", launcher=_fake_launch)
    SS.record_cycle(1, {"units": {}, "elapsed_s": 1.0})
    SS.finish("STOPPED", "stop requested", {"final_cycle": 1})
    with pytest.raises(SS.SimRefused, match="different configuration"):
        SS.start(hours=6, resume=True, mode="trade", launcher=_fake_launch)


def test_a_vanished_process_reads_as_UNCLEAN_not_RUNNING(sim_tmp, monkeypatch):
    """A crashed process cannot set its own 'I crashed' flag."""
    SS.start(hours=6, launcher=_fake_launch)
    monkeypatch.setattr(SS, "pid_alive", lambda pid: False)
    st = SS.status()
    assert st["state"] == "UNCLEAN"
    assert "no stop receipt" in st["session"]["unclean_reason"]


def test_nothing_to_resume_is_refused(sim_tmp):
    with pytest.raises(SS.SimRefused, match="nothing to resume"):
        SS.start(hours=6, resume=True, launcher=_fake_launch)


# ───────────────── the browser: one profile, no money, no JS ────────────────

from backend.services import openclaw_client as OC          # noqa: E402


def test_money_domains_are_refused_before_the_call_leaves_python():
    """Murat's one strict rule: never for payments."""
    for url in ("https://app.alpaca.markets/paper/dashboard",
                "https://www.paypal.com/signin",
                "https://www.coinbase.com/",
                "https://www.chase.com/personal"):
        with pytest.raises(OC.OpenClawRefused, match="REFUSED_DOMAIN"):
            OC.check_url(url)


def test_research_domains_are_allowed():
    for url in ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent",
                "https://www.reddit.com/r/stocks/",
                "https://investor.nvidia.com/"):
        OC.check_url(url)          # must not raise


def test_evaluate_is_not_an_allowed_verb():
    """Arbitrary JS in a page the agent did not write is prompt-injection surface."""
    assert "evaluate" not in OC.ALLOWED_VERBS
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_VERB"):
        OC.browser("evaluate", "() => document.cookie")


def test_a_missing_profile_refuses_and_never_falls_back(monkeypatch):
    monkeypatch.setenv(OC.PROFILE_ENV, "no_such_profile")
    monkeypatch.setattr(OC, "profiles", lambda: [{"name": "openclaw", "state": "stopped"}])
    with pytest.raises(OC.OpenClawRefused, match="REFUSED_BROWSER_PROFILE_UNAVAILABLE"):
        OC.assert_profile()


def test_the_profile_is_named_on_every_browser_call(monkeypatch):
    """Not 'whatever the default is' — the default moved four times in one day."""
    seen = {}
    monkeypatch.setenv(OC.PROFILE_ENV, "muratclaw")
    monkeypatch.setattr(OC, "profiles", lambda: [{"name": "muratclaw", "state": "stopped"}])

    def fake_run(args, **kw):
        seen["argv"] = args
        import subprocess as sp
        return sp.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(OC, "_run", fake_run)
    OC.browser("open", url="https://www.sec.gov/")
    assert seen["argv"][:4] == ["browser", "--browser-profile", "muratclaw", "open"]


def test_profiles_parser_ignores_indented_continuation_lines(monkeypatch):
    """`port:` and `transport:` are not profiles; treating them as such would
    let assert_profile pass on a name that does not exist."""
    out = ("muratclaw: stopped [default]\n"
           "  port: 18801, color: #FF4500\n"
           "chrome: stopped [extension]\n"
           "  transport: extension, relayPort: 18799\n")
    import subprocess as sp
    monkeypatch.setattr(OC, "_run", lambda a, **k: sp.CompletedProcess(a, 0, out, ""))
    names = [p["name"] for p in OC.profiles()]
    assert names == ["muratclaw", "chrome"], names
    assert OC.profiles()[0]["port"] == 18801


# ───────────── the web-event ledger: evidence in, never a decision ──────────

from backend.services import web_events as WE               # noqa: E402


def _ev(**over):
    base = {"ticker": "MU", "entity": "Micron", "source_type": "sec",
            "source_url": "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent",
            "event_type": "filing_8k", "claim": "8-K filed",
            "evidence_date": "2026-09-21", "confidence_source": "REGULATOR",
            "retrieved_by": "openclaw:muratclaw"}
    base.update(over)
    return base


def test_a_web_event_may_never_carry_a_decision():
    """The ledger records what was OBSERVED; the ranker decides what it is worth."""
    for field in ("expected_return", "target_price", "rank", "position_size", "action"):
        with pytest.raises(WE.WebEventRefused, match="may not carry"):
            WE.validate(_ev(**{field: 1}))


def test_event_type_is_a_closed_vocabulary():
    with pytest.raises(WE.WebEventRefused, match="closed vocabulary"):
        WE.validate(_ev(event_type="looks_bullish"))


def test_a_forum_cannot_file_an_8k():
    with pytest.raises(WE.WebEventRefused, match="may not carry event_type"):
        WE.validate(_ev(source_type="reddit"))


def test_an_off_registry_url_is_refused():
    """A wandering browser's evidence cannot be attributed to a tracked source."""
    with pytest.raises(WE.WebEventRefused, match="not an allowed URL"):
        WE.validate(_ev(source_url="https://example.com/whatever"))


def test_evidence_cannot_be_dated_after_we_read_it():
    with pytest.raises(WE.WebEventRefused, match="is AFTER"):
        WE.validate(_ev(evidence_date="2099-01-01"))


def test_a_direction_with_no_claim_is_refused():
    """`claim=""` is caught earlier as a missing field; WHITESPACE is the case
    this guard actually exists for — a row that looks populated and says
    nothing."""
    with pytest.raises(WE.WebEventRefused, match="missing required field"):
        WE.validate(_ev(claim="", direction_prior="positive"))
    with pytest.raises(WE.WebEventRefused, match="opinion"):
        WE.validate(_ev(claim="   ", direction_prior="positive"))


def test_observed_at_and_evidence_date_stay_separate():
    """Conflating them is how a backtest trades on information it never had."""
    e = WE.validate(_ev(evidence_date="2026-09-21"))
    assert e["evidence_date"] == "2026-09-21"
    assert e["observed_at"][:4] >= "2026"
    assert e["observed_at"][:10] >= e["evidence_date"]


def test_pit_safe_asof_filters_on_when_we_SAW_it(monkeypatch, tmp_path):
    monkeypatch.setattr(WE, "LEDGER_DIR", tmp_path)
    # a filing dated well before `asof`, but READ after it
    WE.append([_ev(evidence_date="2026-01-05",
                   observed_at="2026-06-01T00:00:00+00:00")], day="2026-06-01")
    assert WE.pit_safe_asof("2026-03-01") == [], (
        "a filing we had not yet read must not be visible at an earlier asof")
    assert len(WE.pit_safe_asof("2026-06-02")) == 1


def test_a_rescrape_is_not_a_new_event(monkeypatch, tmp_path):
    monkeypatch.setattr(WE, "LEDGER_DIR", tmp_path)
    r = WE.append([_ev(), _ev(), _ev()])
    assert r["written"] == 1 and r["duplicates"] == 2


def test_refusals_are_counted_and_returned_never_dropped(monkeypatch, tmp_path):
    monkeypatch.setattr(WE, "LEDGER_DIR", tmp_path)
    r = WE.append([_ev(), _ev(event_type="nonsense")])
    assert r["written"] == 1 and r["refused"] == 1
    assert "closed vocabulary" in r["refusals"][0]["why"]


# ───────────── SEC fundamentals: filed, not ended, is the PIT date ──────────

from scripts.pull_sec_fundamentals import _latest, _ratio     # noqa: E402


def _facts(rows):
    return {"us-gaap": {"Assets": {"units": {"USD": rows}}}}


def test_latest_chooses_on_FILED_not_on_period_end():
    """A figure describing an older period but filed later IS the newer fact.

    Choosing on `end` would prefer a number that has since been restated or
    superseded, and would let a feature see a value before it was public.
    """
    rows = [
        {"val": 100, "end": "2026-06-30", "filed": "2026-08-05", "form": "10-Q"},
        {"val": 90, "end": "2026-03-31", "filed": "2026-09-01", "form": "10-Q/A"},
    ]
    got = _latest(_facts(rows), ("Assets",))
    assert got["filed"] == "2026-09-01" and got["val"] == 90


def test_an_asof_hides_facts_filed_after_it():
    """The whole point: a 2026-08-05 filing is not knowable on 2026-07-01."""
    rows = [{"val": 100, "end": "2026-06-30", "filed": "2026-08-05"}]
    assert _latest(_facts(rows), ("Assets",), asof="2026-07-01") is None
    assert _latest(_facts(rows), ("Assets",), asof="2026-08-31")["val"] == 100


def test_a_missing_fact_is_None_and_says_which_one():
    """Never zero-filled: LightGBM reads NaN natively, and a zero where a number
    is missing is a lie the model will happily fit."""
    v, why = _ratio(None, {"val": 10})
    assert v is None and "numerator" in why
    v, why = _ratio({"val": 10}, None)
    assert v is None and "denominator" in why
    v, why = _ratio({"val": 10}, {"val": 0})
    assert v is None and "zero" in why


def test_a_real_ratio_is_computed():
    v, why = _ratio({"val": 50.0}, {"val": 200.0})
    assert v == pytest.approx(0.25) and why == "ok"


# ───────── fundamentals: joined on WHEN IT BECAME PUBLIC, never on period ────

from backend.services import fundamental_features as FF     # noqa: E402


def _hist(rows):
    d = pd.DataFrame(rows)
    d["filed"] = pd.to_datetime(d["filed"])
    return d


def test_a_filing_is_invisible_before_it_was_filed():
    """The whole defence. Joining on `end` would hand the model six weeks of
    foresight on every quarter of every name."""
    hist = _hist([
        {"ticker": "AAA", "cik": 1, "fact": "assets", "filed": "2026-08-05",
         "end": "2026-06-30", "start": None, "period_days": None, "val": 100.0, "form": "10-Q"},
        {"ticker": "AAA", "cik": 1, "fact": "assets", "filed": "2026-02-05",
         "end": "2025-12-31", "start": None, "period_days": None, "val": 80.0, "form": "10-K"},
    ])
    panel = pd.DataFrame({"symbol": ["AAA", "AAA"],
                          "date": pd.to_datetime(["2026-07-01", "2026-08-20"])})
    j = FF.attach(panel, history=hist, lag_days=0)
    before = j[j["date"] == pd.Timestamp("2026-07-01")].iloc[0]
    after = j[j["date"] == pd.Timestamp("2026-08-20")].iloc[0]
    assert before["filed"] == pd.Timestamp("2026-02-05"), (
        "a row dated 2026-07-01 saw a filing made on 2026-08-05")
    assert after["filed"] == pd.Timestamp("2026-08-05")


def test_flow_facts_are_filtered_to_annual_periods():
    """A 10-K states annual revenue and a 10-Q a quarter. Measured on NVDA,
    mixing them made gp_at read 0.742 / 0.236 / 0.225 for one company."""
    hist = _hist([
        {"ticker": "AAA", "cik": 1, "fact": "revenue", "filed": "2026-05-01",
         "end": "2026-03-31", "start": "2026-01-01", "period_days": 90, "val": 25.0, "form": "10-Q"},
        {"ticker": "AAA", "cik": 1, "fact": "revenue", "filed": "2026-02-01",
         "end": "2025-12-31", "start": "2025-01-01", "period_days": 365, "val": 100.0, "form": "10-K"},
    ])
    kept = FF.annual_flows_only(hist)
    assert list(kept["period_days"]) == [365], "the quarterly row survived"


def test_stock_facts_are_never_filtered_by_period():
    """Assets is a balance at a date and carries no period; a filter that
    treats it like a flow silently deletes the balance sheet."""
    hist = _hist([
        {"ticker": "AAA", "cik": 1, "fact": "assets", "filed": "2026-05-01",
         "end": "2026-03-31", "start": None, "period_days": None, "val": 500.0, "form": "10-Q"},
    ])
    assert len(FF.annual_flows_only(hist)) == 1


def test_a_missing_fact_leaves_NaN_and_never_zero():
    wide = pd.DataFrame({"ticker": ["AAA"], "filed": pd.to_datetime(["2026-01-01"]),
                         "assets": [100.0], "equity": [np.nan]})
    r = FF.ratios(wide)
    assert pd.isna(r["ope_be"].iloc[0]), "a missing fact became a number"


def test_a_zero_denominator_is_NaN_not_infinity():
    wide = pd.DataFrame({"ticker": ["AAA"], "filed": pd.to_datetime(["2026-01-01"]),
                         "operating_income": [5.0], "equity": [0.0],
                         "assets": [10.0]})
    r = FF.ratios(wide)
    assert pd.isna(r["ope_be"].iloc[0])


def test_a_stale_filing_is_dropped_rather_than_carried_forever():
    """A filing older than ~15 months describes a different company."""
    hist = _hist([{"ticker": "AAA", "cik": 1, "fact": "assets", "filed": "2020-01-01",
                   "end": "2019-12-31", "start": None, "period_days": None,
                   "val": 1.0, "form": "10-K"}])
    panel = pd.DataFrame({"symbol": ["AAA"], "date": pd.to_datetime(["2026-01-01"])})
    j = FF.attach(panel, history=hist)
    assert pd.isna(j["book_equity_log"].iloc[0]) or pd.isna(j["gp_at"].iloc[0])
    assert j["fundamental_age_days"].iloc[0] > 460


def test_missing_history_refuses_rather_than_ranking_on_nothing(tmp_path):
    with pytest.raises(FF.FundamentalsMissing, match="no SEC filing history"):
        FF.load_history(tmp_path / "absent.parquet")


# ═══════════════════ the funnel's age, and the audit's blind spot ═══════════
#
# Both of these pin failures that were LIVE and invisible on 2026-09-24:
# a 44-day-old candidate set reporting `status: ok`, and an undateable position
# counted as fresh. Neither was a crash. Both resolved silently to the benign
# branch, which is the only reason they survived six weeks and one publication.

class TestFunnelStaleness:
    """`ic_health` read `generated_at` for months and never compared it."""

    def test_a_fresh_snapshot_is_not_flagged(self):
        from datetime import datetime, timedelta, timezone
        from backend.services import investment_committee as IC
        fresh = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        assert IC.funnel_staleness(fresh) is None

    def test_an_old_snapshot_is_flagged_and_says_how_old(self):
        from datetime import datetime, timedelta, timezone
        from backend.services import investment_committee as IC
        old = (datetime.now(timezone.utc)
               - timedelta(days=IC.FUNNEL_STALE_DAYS + 34)).isoformat()
        why = IC.funnel_staleness(old)
        assert why and "44 days old" in why
        # It must name the remedy, or the reader has a red line and no move.
        assert "opportunity_funnel" in why

    def test_an_undateable_snapshot_is_unknown_not_fresh(self):
        """The whole defect family: missing data must not take the good branch."""
        from backend.services import investment_committee as IC
        for bad in (None, "", "not a date", "2026-13-45"):
            why = IC.funnel_staleness(bad)
            assert why is not None, f"{bad!r} was treated as fresh"
            assert "CANNOT BE DETERMINED" in why

    def test_the_boundary_is_the_configured_limit(self):
        from datetime import datetime, timedelta, timezone
        from backend.services import investment_committee as IC
        now = datetime.now(timezone.utc)
        inside = (now - timedelta(days=IC.FUNNEL_STALE_DAYS - 1)).isoformat()
        outside = (now - timedelta(days=IC.FUNNEL_STALE_DAYS + 1)).isoformat()
        assert IC.funnel_staleness(inside, now=now) is None
        assert IC.funnel_staleness(outside, now=now) is not None

    def test_the_advertised_refresh_command_actually_runs(self):
        """`python -m backend.services.opportunity_funnel` was a silent no-op.

        The module had `run()` and no `__main__`, so the command printed in
        `pm_actions` -- and now in the staleness message -- imported the module
        and exited 0. An operator following the instruction saw the file
        unchanged and no error. This asserts the entry point EXISTS; it does not
        run it (that is a network call).
        """
        from backend.services import opportunity_funnel as OF
        assert callable(getattr(OF, "main", None))
        from pathlib import Path as _P
        src = _P(OF.__file__).read_text(encoding="utf-8")
        assert '__name__ == "__main__"' in src


class TestFleetAuditAgeIsNotAssumedFresh:
    """An entry date the order history could not reach is UNKNOWN, not new."""

    def test_unknown_age_is_never_counted_as_fresh(self):
        import scripts.fleet_audit as FA
        from pathlib import Path as _P
        src = _P(FA.__file__).read_text(encoding="utf-8")
        # `stale` may only be True with a real age -- that part was already
        # right. What was wrong is that nothing else recorded the absence.
        assert '"age_unknown": age is None' in src, (
            "a position with no reachable entry date must be marked UNKNOWN, "
            "not silently folded into the fresh side of the stale count")

    def test_the_order_history_is_paged(self):
        """One 500-row request is 'the oldest 500 orders', not 'the history'."""
        import scripts.fleet_audit as FA
        from pathlib import Path as _P
        src = _P(FA.__file__).read_text(encoding="utf-8")
        assert "MAX_ORDER_PAGES" in src and "&after=" in src, (
            "fleet_trade_autopsy measured 500 fills across this fleet, so a "
            "single limit=500 page sits exactly on the cap and drops the "
            "newest entries")

    def test_entry_dates_reports_its_own_coverage(self):
        import inspect
        import scripts.fleet_audit as FA
        sig = inspect.signature(FA.entry_dates)
        assert "tuple" in str(sig.return_annotation), (
            "the caller must be able to tell 'this position is new' from "
            "'this audit could not see far enough back'")


class TestLeaveOneYearOutIsNotOptional:
    """A result that is one calendar year must not read as an edge.

    On 2026-09-24 a +2.62%/hold cell survived a purge, a survivorship-free
    panel, a breadth sweep and a corrected error bar, then went to +0.12% when
    2025 was removed. The check that caught it cost one groupby and was run
    last. It is now unconditional.
    """

    @staticmethod
    def _oos(regime_year: str | None = None):
        """Two names a day over six years; `regime_year` gets all the return."""
        import numpy as np
        import pandas as pd
        rng = np.random.default_rng(11)
        rows = []
        # BUSINESS days, not 21-calendar-day steps. The real panel rebalances
        # every session, so "21 consecutive rebalance dates" is about a month
        # and lines up with the monthly blocking. A fixture on 21-day spacing
        # makes one non-overlap block span a YEAR and the two statistics
        # incomparable -- which is a property of the fixture, not the code.
        for year in range(2021, 2027):
            for d in pd.date_range(f"{year}-01-05", f"{year}-11-20", freq="B"):
                for i, sym in enumerate(("AAA", "BBB", "CCC", "DDD")):
                    hot = regime_year is not None and str(year) == regime_year
                    # score orders the names; only in `regime_year` does the
                    # ordering pay. Elsewhere the forward return is pure noise.
                    rows.append({
                        "symbol": sym, "date": d, "score": float(3 - i),
                        "fwd_rel": (0.10 if (hot and i == 0) else 0.0)
                                   + rng.normal(0, 0.002),
                        "median_dollar_vol": 5e8,
                    })
        return pd.DataFrame(rows)

    def test_a_single_regime_result_is_visible_in_the_receipt(self):
        from backend.services import xs_ranker as XR
        bt = XR.top_k_backtest(self._oos("2025"), k=1, horizon=21)
        assert bt["mean_net_rel_21d"] > 0, "the fixture should look profitable"
        assert bt["loo_worst_dropped_year"] == "2025"
        # Removing the one paying year must remove essentially all of it.
        assert bt["loo_worst_mean_net"] < bt["mean_net_rel_21d"] / 4, (
            f"LOO did not expose the regime: {bt['loo_worst_mean_net']} vs "
            f"{bt['mean_net_rel_21d']}")
        assert set(bt["by_year"]) == {str(y) for y in range(2021, 2027)}

    def test_a_broad_result_survives_leave_one_year_out(self):
        """The control: the check must not condemn a result spread evenly."""
        import numpy as np
        import pandas as pd
        from backend.services import xs_ranker as XR
        rng = np.random.default_rng(12)
        rows = []
        for year in range(2021, 2027):
            for d in pd.date_range(f"{year}-01-05", f"{year}-11-20", freq="B"):
                for i, sym in enumerate(("AAA", "BBB", "CCC", "DDD")):
                    rows.append({"symbol": sym, "date": d, "score": float(3 - i),
                                 "fwd_rel": (0.02 if i == 0 else 0.0)
                                            + rng.normal(0, 0.002),
                                 "median_dollar_vol": 5e8})
        bt = XR.top_k_backtest(pd.DataFrame(rows), k=1, horizon=21)
        assert bt["loo_worst_mean_net"] > bt["mean_net_rel_21d"] / 2, (
            "an evenly spread result must survive LOO, or the check is useless")

    def test_the_nonoverlap_t_agrees_where_monthly_was_already_right(self):
        """Validity check on the corrected statistic, not on the strategy."""
        from backend.services import xs_ranker as XR
        bt = XR.top_k_backtest(self._oos(), k=1, horizon=21)
        tm, tn = bt["t_across_blocks"], bt["t_nonoverlap"]
        assert tm is not None and tn is not None
        # RELATIVE, not absolute: the claim is about the RATIO of the two
        # standard errors. At H=126 on the real panel that ratio was 2.13
        # (+2.83 -> +1.33); at H=21 monthly blocks barely overlap, so a
        # corrected statistic that disagreed by much here would be the
        # suspicious one. An absolute tolerance would pass or fail on the size
        # of t rather than on the thing being tested.
        assert 0.7 < tn / tm < 1.4, f"monthly {tm:.2f} vs non-overlap {tn:.2f}"
        # And strict independence is always the smaller count.
        assert bt["n_blocks_strict"] <= bt["n_blocks_nonoverlap"]


class TestTheFunnelNowHasAScheduledCaller:
    """`funnel_night10.json` went 44 days without a refresh because NOTHING
    CALLED THE REFRESH. `u_funnel` is the scheduled caller."""

    @staticmethod
    def _stale(td: Path) -> Path:
        import json as _j
        p = td / "stale_funnel.json"
        p.write_text(_j.dumps({"generated_at": "2026-08-11T02:33:48+00:00",
                               "candidates": [{"ticker": "OLD"}]}), encoding="utf-8")
        return p

    def test_it_is_wired_into_the_cycle_before_the_rank(self):
        """A ranking over last month's candidate set is the 09-22 failure."""
        import scripts.sim_run as SR
        from pathlib import Path as _P
        src = _P(SR.__file__).read_text(encoding="utf-8")
        i, j = src.index('c.unit("funnel"'), src.index('c.unit("rank"')
        assert i < j, "the funnel must refresh BEFORE the rank reads it"

    def test_a_fresh_snapshot_costs_nothing(self, tmp_path, monkeypatch):
        import json as _j
        import scripts.sim_run as SR
        from backend import config as C
        from datetime import datetime, timezone
        p = tmp_path / "fresh.json"
        p.write_text(_j.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                               "candidates": [{"ticker": "NEW"}]}), encoding="utf-8")
        monkeypatch.setattr(C, "IC_FUNNEL_PATH", p)
        monkeypatch.setattr(SR, "_in_subprocess",
                            lambda *a, **k: pytest.fail("refreshed a fresh funnel"))
        assert "skipped" in SR.u_funnel(tmp_path)

    def test_it_attempts_once_per_session_not_once_per_cycle(self, tmp_path, monkeypatch):
        """121 cycles must not mean 121 rebuilds of a 310-second job."""
        import scripts.sim_run as SR
        from backend import config as C
        calls = []
        monkeypatch.setattr(C, "IC_FUNNEL_PATH", self._stale(tmp_path))
        monkeypatch.setattr(SR, "_in_subprocess",
                            lambda *a, **k: (calls.append(1) or {"rc": 0}))
        for _ in range(5):
            SR.u_funnel(tmp_path)
        assert len(calls) == 1, f"attempted {len(calls)} times in one session"

    def test_a_refusal_keeps_the_old_snapshot_and_does_not_raise(self, tmp_path, monkeypatch):
        """A stale candidate set beats none, and beats losing the night."""
        import scripts.sim_run as SR
        from backend import config as C
        monkeypatch.setattr(C, "IC_FUNNEL_PATH", self._stale(tmp_path))
        monkeypatch.setattr(SR, "_in_subprocess", lambda *a, **k: {"rc": 2})
        r = SR.u_funnel(tmp_path)          # must NOT raise
        assert "refresh_failed" in r and r["kept"] == "2026-08-11T02:33:48+00:00"

    def test_rc_zero_with_an_unmoved_stamp_is_a_failure(self, tmp_path, monkeypatch):
        """The 09-22 failure in miniature: a remedy that reports success and
        changes nothing. Verify the persistence claim, not the exit code."""
        import scripts.sim_run as SR
        from backend import config as C
        monkeypatch.setattr(C, "IC_FUNNEL_PATH", self._stale(tmp_path))
        monkeypatch.setattr(SR, "_in_subprocess", lambda *a, **k: {"rc": 0})
        r = SR.u_funnel(tmp_path)
        assert "refresh_failed" in r and "did not move" in r["refresh_failed"]


class TestExitRuleFillConventions:
    """The fill conventions ARE the validity of the exit-rule test.

    A stop backtest that gets any of these wrong reports that stops are free,
    which is the same optimism the fleet autopsy's "75% saved" was built on.
    Each of these is a case I checked by hand before running the job; they are
    here so a later refactor cannot quietly restore the flattering convention.
    """

    @staticmethod
    def _p(rows):
        import pandas as pd
        from scripts.night_exit_rules import Path_
        return Path_(pd.DataFrame(rows, columns=["date", "open", "high",
                                                 "low", "close"]))

    def test_the_stop_fires_intraday_not_close_to_close(self):
        """Entry 100, dips to 97, CLOSES at 105. A close-only test holds."""
        from scripts.night_exit_rules import walk_one
        p = self._p([("2020-01-01", 100, 101, 99, 100),
                     ("2020-01-02", 104, 106, 97, 105),
                     ("2020-01-03", 105, 106, 104, 106)])
        r, held, why = walk_one(p, 0, 3, stop=0.02)
        assert why == "stop" and abs(r + 0.02) < 1e-9 and held == 2
        # ... and with no rule the same path is a WINNER, which is the point:
        # the stop is giving up +6% to avoid a −2% mark.
        r2, _, why2 = walk_one(p, 0, 3)
        assert why2 == "horizon" and r2 > 0.05

    def test_a_gap_through_the_level_fills_at_the_open(self):
        """The largest source of optimism in stop backtests. Stop is 98; the
        session OPENS at 95, so 98 was never available."""
        from scripts.night_exit_rules import walk_one
        p = self._p([("2020-01-01", 100, 101, 99, 100),
                     ("2020-01-02", 95, 96, 90, 93),
                     ("2020-01-03", 93, 94, 92, 93)])
        r, _, why = walk_one(p, 0, 3, stop=0.02)
        assert why == "stop_gap", "a gap must be distinguishable in the receipt"
        assert abs(r + 0.05) < 1e-9, f"filled at {r:+.4f}, not the open's −5%"

    def test_a_same_session_collision_resolves_to_the_stop(self):
        """Daily bars do not record intra-session order, so the worst
        admissible sequence is assumed. Anything else lets the test pick its
        own luck."""
        from scripts.night_exit_rules import walk_one
        p = self._p([("2020-01-01", 100, 101, 99, 100),
                     ("2020-01-02", 100, 112, 97, 111)])
        r, _, why = walk_one(p, 0, 2, stop=0.02, take=0.10)
        assert why == "stop" and abs(r + 0.02) < 1e-9, (
            "the session touched both +10% and −2%; the stop must win")
        # With no stop in play the target fires normally.
        r2, _, why2 = walk_one(p, 0, 2, take=0.10)
        assert why2 == "take" and abs(r2 - 0.10) < 1e-9

    def test_the_trail_does_not_use_the_high_that_triggers_it(self):
        """A trail recomputed from TODAY's high to justify TODAY's exit is
        using information from after the trigger."""
        from scripts.night_exit_rules import walk_one
        p = self._p([("2020-01-01", 100, 120, 99, 119),
                     ("2020-01-02", 119, 119, 110, 112),
                     ("2020-01-03", 112, 113, 111, 112)])
        r, held, why = walk_one(p, 0, 3, trail=0.05)
        # High 120 set on day 1; 5% below is 114, touched on day 2.
        assert why == "trail" and held == 2 and abs(r - 0.14) < 1e-9

    def test_entry_is_the_session_after_the_score(self):
        """Matches `xs_ranker.build_target`: a row dated t is never credited
        with a move that had already happened when it was scored."""
        import numpy as np
        import pandas as pd
        from scripts.night_exit_rules import _entry_index
        p = self._p([("2020-01-01", 100, 101, 99, 100),
                     ("2020-01-02", 200, 201, 199, 200),
                     ("2020-01-03", 300, 301, 299, 300)])
        i = _entry_index(p, np.datetime64(pd.Timestamp("2020-01-01"), "ns"))
        assert i == 1 and p.open[i] == 200, "entry must be t+1's OPEN"
        # A score dated after the last bar has no entry at all, and that is a
        # skip, not an entry at the last price.
        assert _entry_index(p, np.datetime64(pd.Timestamp("2020-01-03"), "ns")) is None

    def test_the_hold_arm_reproduces_the_panel_target(self):
        """If the no-rule arm does not equal `fwd_ret`, the comparison is
        measuring the harness rather than the rule."""
        from scripts.night_exit_rules import walk_one
        p = self._p([(f"2020-01-{d:02d}", 100 + d, 102 + d, 98 + d, 101 + d)
                     for d in range(1, 12)])
        r, held, why = walk_one(p, 1, 5)
        assert why == "horizon" and held == 5
        assert abs(r - (p.close[5] / p.open[1] - 1.0)) < 1e-12


class TestOpenClawHealthCanActuallyGoGreen:
    """`health()` matched a literal string through the CLI's ANSI colour codes.

    The CLI emits the escape sequence BETWEEN the label and the value --
    'Connectivity probe:\x1b[39m \x1b[38;2;47;191;113mok\x1b[39m' -- so
    `"Connectivity probe: ok" in text` was False regardless of what the gateway
    was doing. health() therefore ALWAYS returned "DO NOT BROWSE: gateway
    unreachable", and the night runner was never once permitted to browse.

    Found 2026-09-24 only because two agent quests demonstrably succeeded while
    health() called the gateway unreachable. A gate that cannot go green is a
    broken gate, not a strict one.
    """

    def test_run_strips_ansi_from_both_streams(self, monkeypatch):
        import subprocess
        from backend.services import openclaw_client as OC
        coloured = ("Runtime:\x1b[39m \x1b[38;2;47;191;113mrunning\x1b[39m\n"
                    "Connectivity probe:\x1b[39m \x1b[38;2;47;191;113mok\x1b[39m\n")
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **k: subprocess.CompletedProcess(a[0], 0, coloured,
                                                        "\x1b[31merr\x1b[39m"))
        r = OC._run(["gateway", "status"])
        assert "\x1b[" not in r.stdout and "\x1b[" not in r.stderr
        # And the exact literals health() greps for must now be present.
        assert "Runtime: running" in r.stdout
        assert "Connectivity probe: ok" in r.stdout

    def test_health_reports_the_gateway_up_when_it_is_up(self, monkeypatch):
        """The regression that matters: a healthy gateway must read as healthy."""
        from backend.services import openclaw_client as OC
        healthy = ("Runtime:\x1b[39m \x1b[38;2;47;191;113mrunning\x1b[39m\n"
                   "Connectivity probe:\x1b[39m \x1b[38;2;47;191;113mok\x1b[39m\n")
        # Stub `subprocess.run`, NOT `_run` -- the stripping happens INSIDE
        # `_run`, so stubbing that would skip the very thing under test. The
        # first version of this test did exactly that and failed.
        import subprocess
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: subprocess.CompletedProcess(
                                a[0] if a else [], 0, healthy, ""))
        monkeypatch.setattr(OC, "assert_profile",
                            lambda strict=True: {"ok": True, "state": "running"})
        monkeypatch.setattr(OC, "_default_profile_matches", lambda: True)
        monkeypatch.setattr(OC, "_channel_count", lambda: 0)
        h = OC.health()
        assert h.rows["gateway_probe_ok"] is True
        assert h.rows["gateway_running"] is True
        assert h.ok is True, f"a healthy gateway must read READY: {h.rows['verdict']}"

    def test_health_still_refuses_when_a_messaging_channel_exists(self, monkeypatch):
        """The WhatsApp incident guard must survive the fix.

        Fixing a gate that could not go green must not make it a gate that
        cannot go red.
        """
        from backend.services import openclaw_client as OC
        healthy = "Runtime: running\nConnectivity probe: ok\n"
        monkeypatch.setattr(OC, "_run", lambda args, **k: __import__(
            "subprocess").CompletedProcess(args, 0, healthy, ""))
        monkeypatch.setattr(OC, "assert_profile",
                            lambda strict=True: {"ok": True, "state": "running"})
        monkeypatch.setattr(OC, "_default_profile_matches", lambda: True)
        monkeypatch.setattr(OC, "_channel_count", lambda: 1)
        h = OC.health()
        assert h.ok is False and "messaging channel" in h.rows["verdict"]
