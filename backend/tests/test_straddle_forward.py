"""TRIAL-STRADDLE-FWD-1: offline tests for the straddle forward log (no network).

Every date is DERIVED (from today, or a year derived from today) -- no literal expiry
or calendar moment, so nothing here goes stale when a date passes (protocol item 5).
The exchange calendar is injected as a weekday rule where a test needs a holiday.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, time as dtime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backend.services import straddle_forward as SF
from backend.services.option_implier import bsm_price


def weekdays(d: date) -> bool:
    return d.weekday() < 5


# ─────────────────────────── ET sessions ─────────────────────────────────────

def _et_to_utc(d: date, hh: int, mm: int) -> datetime:
    return datetime.combine(d, dtime(hh, mm), tzinfo=SF.ET).astimezone(timezone.utc)


def _a_weekday(year: int, month: int) -> date:
    d = date(year, month, 10)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def test_entry_window_is_computed_in_eastern_time_across_dst():
    y = date.today().year
    summer, winter = _a_weekday(y, 7), _a_weekday(y, 1)
    for d in (summer, winter):
        w = SF.entry_window(_et_to_utc(d, 11, 0), is_session=weekdays)
        assert w["in_window"] and w["session_date"] == d.isoformat()
        assert SF.entry_window(_et_to_utc(d, 9, 50), is_session=weekdays)["reason"] == "BEFORE_WINDOW"
        assert SF.entry_window(_et_to_utc(d, 15, 45), is_session=weekdays)["reason"] == "AFTER_WINDOW"
    # the same UTC clock time is inside the window in summer (EDT) and before it in winter (EST)
    utc_summer = datetime.combine(summer, dtime(14, 50), tzinfo=timezone.utc)
    utc_winter = datetime.combine(winter, dtime(14, 50), tzinfo=timezone.utc)
    assert SF.entry_window(utc_summer, is_session=weekdays)["in_window"]
    assert SF.entry_window(utc_winter, is_session=weekdays)["reason"] == "BEFORE_WINDOW"


def test_entry_window_refuses_a_non_session():
    d = date.today()
    while d.weekday() != 5:
        d += timedelta(days=1)
    assert SF.entry_window(_et_to_utc(d, 11, 0), is_session=weekdays)["reason"] == "NOT_A_SESSION"


def test_third_friday_and_holiday_rule():
    y = date.today().year + 1
    for m in range(1, 13):
        f = SF.third_friday(y, m)
        assert f.weekday() == 4 and 15 <= f.day <= 21
    tf = SF.third_friday(y, 4)
    closed = lambda d: weekdays(d) and d != tf                          # noqa: E731
    assert SF.monthly_expiry(y, 4, closed) == tf - timedelta(days=1)


def test_pick_expiry_respects_the_dte_window_and_leaves_gap_days():
    start = date.today()
    got, gaps = 0, 0
    for i in range(120):
        d = start + timedelta(days=i)
        e = SF.pick_expiry(d, weekdays)
        if e is None:
            gaps += 1
            n = SF.nearest_monthly(d, weekdays)
            assert (n - d).days >= 7
            continue
        got += 1
        assert SF.DTE_MIN <= (e - d).days <= SF.DTE_MAX
        assert e == SF.monthly_expiry(e.year, e.month, weekdays)
    assert got > 0 and gaps > 0


def test_sessions_between_counts_open_interval():
    d = date.today()
    while d.weekday() != 0:
        d += timedelta(days=1)
    assert SF.sessions_between(d, d + timedelta(days=7), weekdays) == 5


# ─────────────────────────── quotes ──────────────────────────────────────────

def _chain(spot: float, sigma: float, expiry: date, now: datetime, *, half_spread: float = 0.02,
           oi: int = 500, last_trade: datetime | None = None, strikes=None):
    t = ((datetime.combine(expiry, dtime(16, 0), tzinfo=SF.ET) - now).total_seconds() / 86400.0) / 365.0
    strikes = strikes or [round(spot * k) for k in (0.9, 0.95, 1.0, 1.05, 1.1)]
    lt = (last_trade or now - timedelta(hours=1)).isoformat()
    rows_c, rows_p = [], []
    for k in strikes:
        for is_call, rows in ((True, rows_c), (False, rows_p)):
            m = bsm_price(spot, k, t, SF.RATE, 0.0, sigma, is_call)
            rows.append({"strike": float(k), "bid": m * (1 - half_spread), "ask": m * (1 + half_spread),
                         "lastPrice": m, "openInterest": oi, "volume": 10, "impliedVolatility": sigma,
                         "lastTradeDate": lt, "contractSymbol": f"X{k}{'C' if is_call else 'P'}"})
    return pd.DataFrame(rows_c), pd.DataFrame(rows_p), t


def test_build_straddle_recovers_iv_and_prices_at_ask_and_bid():
    now = datetime.now(timezone.utc)
    exp = now.date() + timedelta(days=28)
    c, p, t = _chain(100.0, 0.30, exp, now)
    s = SF.build_straddle("X", c, p, spot=100.0, spot_time_utc=now, now_utc=now, expiry=exp, in_session=True)
    assert s.ok, s.reasons
    f = s.fields
    assert f["strike"] == 100.0
    assert f["iv_atm"] == pytest.approx(0.30, abs=2e-3)
    assert f["ask_sum"] > f["mid_sum"] > f["bid_sum"]
    assert f["straddle_rel_spread"] == pytest.approx(0.04, abs=1e-9)
    assert f["implied_move"] == pytest.approx(0.30 * math.sqrt(t) * math.sqrt(2 / math.pi), rel=1e-2)


@pytest.mark.parametrize("mutate,reason", [
    (lambda c, p: c.assign(bid=c["ask"] * 1.1), "CROSSED_CALL"),
    (lambda c, p: c.assign(bid=0.0), "NO_BID_CALL"),
    (lambda c, p: p.assign(ask=np.nan), "NO_ASK_PUT"),
    (lambda c, p: c.assign(openInterest=0), "THIN_OI_CALL"),
])
def test_build_straddle_refusals_are_recorded(mutate, reason):
    now = datetime.now(timezone.utc)
    exp = now.date() + timedelta(days=28)
    c, p, _ = _chain(100.0, 0.30, exp, now)
    out = mutate(c, p)
    if reason.endswith("PUT"):
        p = out
    else:
        c = out
    s = SF.build_straddle("X", c, p, spot=100.0, spot_time_utc=now, now_utc=now, expiry=exp, in_session=True)
    assert not s.ok and reason in s.reasons


def test_build_straddle_refuses_wide_stale_offatm_and_stale_underlying():
    now = datetime.now(timezone.utc)
    exp = now.date() + timedelta(days=28)
    c, p, _ = _chain(100.0, 0.30, exp, now, half_spread=0.15)
    assert "WIDE_STRADDLE" in SF.build_straddle("X", c, p, spot=100.0, spot_time_utc=now, now_utc=now,
                                                expiry=exp, in_session=True).reasons
    c, p, _ = _chain(100.0, 0.30, exp, now, last_trade=now - timedelta(days=SF.LEG_STALE_DAYS + 1))
    r = SF.build_straddle("X", c, p, spot=100.0, spot_time_utc=now, now_utc=now, expiry=exp, in_session=True).reasons
    assert "STALE_CALL" in r and "STALE_PUT" in r
    c, p, _ = _chain(100.0, 0.30, exp, now, strikes=[80, 120])
    assert "OFF_ATM" in SF.build_straddle("X", c, p, spot=100.0, spot_time_utc=now, now_utc=now,
                                          expiry=exp, in_session=False).reasons
    c, p, _ = _chain(100.0, 0.30, exp, now)
    old = now - timedelta(minutes=SF.UNDERLYING_STALE_MIN + 5)
    assert "STALE_UNDERLYING" in SF.build_straddle("X", c, p, spot=100.0, spot_time_utc=old, now_utc=now,
                                                   expiry=exp, in_session=True).reasons
    assert "STALE_UNDERLYING" not in SF.build_straddle("X", c, p, spot=100.0, spot_time_utc=old, now_utc=now,
                                                       expiry=exp, in_session=False).reasons
    assert SF.build_straddle("X", c, p, spot=None, spot_time_utc=now, now_utc=now, expiry=exp,
                             in_session=True).reasons == ["NO_SPOT"]


# ─────────────────────────── features + model ────────────────────────────────

def _panel(n_days: int = 300, seed: int = 7):
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(date.today()) - pd.offsets.BDay(1)
    idx = pd.bdate_range(end=end, periods=n_days)
    sig = {"LOW": 0.005, "HIGH": 0.03}
    close = pd.DataFrame({s: 100 * np.cumprod(1 + rng.normal(0, v, n_days)) for s, v in sig.items()}, index=idx)
    mkt = pd.Series(400 * np.cumprod(1 + rng.normal(0, 0.008, n_days)), index=idx)
    dv = close * 1e6
    return close, dv, mkt, idx


def test_live_features_vol_order_ems4_and_point_in_time_flag():
    close, dv, mkt, idx = _panel()
    dec = idx[-1].date()
    past = [idx[-200].date(), idx[-137].date(), idx[-74].date()]
    future = dec + timedelta(days=10)
    entry = dec + timedelta(days=1)
    window_end = entry + timedelta(days=30)
    reports = {"LOW": past + [future], "HIGH": past}
    f = SF.live_features(close, dv, mkt, reports, entry=entry, window_end=window_end)
    assert f.loc["HIGH", "vol_63"] > 3 * f.loc["LOW", "vol_63"]
    assert f.attrs["future_reports_dropped"] == 1                    # the scheduled future date is never read
    # ems4 by hand for HIGH
    R = close["HIGH"].pct_change().to_numpy()
    M = mkt.pct_change().to_numpy()
    hand = []
    for d in past:
        d0 = int(np.searchsorted(idx.normalize(), pd.Timestamp(d)))
        hand.append(abs((1 + R[d0]) * (1 + R[d0 + 1]) - (1 + M[d0]) * (1 + M[d0 + 1])))
    assert f.loc["HIGH", "ems4"] == pytest.approx(np.mean(hand))
    # projection: last done + 91-day steps past entry, flagged iff on/before the window end
    nd = pd.Timestamp(past[-1]) + pd.Timedelta(days=91)
    while nd.date() <= entry:
        nd += pd.Timedelta(days=91)
    assert f.loc["HIGH", "earn_next_pit"] == float(nd.date() <= window_end)
    assert f.loc["LOW", "earn_next_pit"] == f.loc["HIGH", "earn_next_pit"]   # the future row changed nothing
    assert f.loc["HIGH", "earn_x_ems_pit"] == pytest.approx(f.loc["HIGH", "earn_next_pit"] * f.loc["HIGH", "ems4"])


def _toy_model():
    spec = {"vol_63": "log", "ems4": "log"}
    body = {"spec": spec, "feature_order": list(spec), "alpha": 10.0, "winsor_cap": 1.0, "floor": 0.01,
            "mu": [math.log(0.3), math.log(0.05)], "sd": [0.5, 0.5], "coef": [0.02, 0.01], "intercept": 0.08,
            "target": "abs_r21"}
    body["model_sha"] = SF.model_hash(body)
    return body


def test_apply_model_imputes_missing_with_training_mean_and_floors(tmp_path):
    m = _toy_model()
    feats = pd.DataFrame({"vol_63": [0.3, 0.6, 0.3], "ems4": [0.05, 0.05, np.nan]}, index=["A", "B", "C"])
    f = SF.apply_model(m, feats)
    assert f["A"] == pytest.approx(0.08) and f["C"] == pytest.approx(0.08) and f["B"] > f["A"]
    lo = SF.apply_model(m, pd.DataFrame({"vol_63": [1e-9], "ems4": [0.05]}, index=["Z"]))
    assert lo["Z"] == pytest.approx(0.01)
    p = tmp_path / "m.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    assert SF.load_model(p)["model_sha"] == m["model_sha"]
    bad = dict(m, coef=[0.03, 0.01])
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(RuntimeError):
        SF.load_model(p)


def test_rank_legs_orders_by_log_gap_and_skips_thin_cells():
    n = 60
    df = pd.DataFrame({"f": np.linspace(0.05, 0.10, n), "implied_move": np.full(n, 0.07),
                       "horizon_scale": np.full(n, 0.9)}, index=[f"S{i:02d}" for i in range(n)])
    legs = SF.rank_legs(df, "f", 20)
    assert legs["long"][0] == "S59" and legs["short"][0] == "S00"
    assert not set(legs["long"]) & set(legs["short"])
    assert SF.rank_legs(df, "f", 30) is None                           # 60 < 2*30 + 10


# ─────────────────────────── contract + frozen log ───────────────────────────

def test_contract_freeze_is_immutable(tmp_path):
    p = tmp_path / "c.json"
    c = SF.freeze_contract({"a": 1}, p)
    assert SF.freeze_contract({"a": 1}, p)["policy_hash"] == c["policy_hash"]
    with pytest.raises(RuntimeError):
        SF.freeze_contract({"a": 2}, p)
    rec = json.loads(p.read_text(encoding="utf-8"))
    rec["body"]["a"] = 3
    p.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(RuntimeError):
        SF.load_contract(p)


def test_frozen_writer_chains_refuses_duplicates_and_pre_freeze_rows(tmp_path):
    log = tmp_path / "entries.jsonl"
    c = SF.freeze_contract({"x": 1}, tmp_path / "c.json")
    later = (pd.Timestamp(c["frozen_utc"]) + pd.Timedelta(minutes=5)).isoformat()
    d1 = date.today().isoformat()
    d2 = (date.today() + timedelta(days=1)).isoformat()
    rows = [{"kind": "SESSION", "written_utc": later}, {"kind": "NAME", "symbol": "A", "quote_utc": later}]
    assert SF.append_frozen(rows, session_date=d1, contract=c, path=log) == 2
    with pytest.raises(RuntimeError):
        SF.append_frozen(rows, session_date=d1, contract=c, path=log)
    early = (pd.Timestamp(c["frozen_utc"]) - pd.Timedelta(hours=1)).isoformat()
    with pytest.raises(RuntimeError):
        SF.append_frozen([{"kind": "SESSION", "written_utc": early}], session_date=d2, contract=c, path=log)
    SF.append_frozen(rows, session_date=d2, contract=c, path=log)
    v = SF.verify_chain(log)
    assert v["ok"] and v["rows"] == 4
    assert SF.entered_sessions(log) == {d1, d2}
    lines = log.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[1])
    tampered["symbol"] = "B"
    lines[1] = SF.canonical(tampered)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not SF.verify_chain(log)["ok"]


# ─────────────────────────── grading ─────────────────────────────────────────

def test_terminal_price_rescales_splits_not_dividends():
    assert SF.terminal_price(50.0, 100.0, 99.0) == (50.0, "unscaled")               # 1% = a dividend adjustment
    s, how = SF.terminal_price(50.0, 100.0, 50.0)                                   # 2:1 split since entry
    assert s == pytest.approx(100.0) and how.startswith("split_scaled")


def test_grade_one_long_at_ask_short_at_bid():
    row = {"strike": 100.0, "ask_sum": 6.0, "bid_sum": 5.0, "mid_sum": 5.5}
    g = SF.grade_one(row, 110.0)
    assert g["payoff"] == pytest.approx(10.0)
    assert g["long_ret"] == pytest.approx(10 / 6 - 1)
    assert g["short_ret"] == pytest.approx(1 - 10 / 5)
    assert SF.grade_one(row, 100.0)["long_ret"] == pytest.approx(-1.0)              # at the strike: premium lost


def _book(session, expiry, sel, long, short, breadth=2):
    return {"session_date": session, "expiry": expiry, "selector": sel, "breadth": breadth,
            "long": long, "short": short}


def test_cohorts_and_book_vs_twin_block_by_expiry():
    today = date.today()
    rows, books = [], []
    rng = np.random.default_rng(3)
    for k in range(8):                                                   # 8 expiries, 2 cohorts each
        exp = (today + timedelta(days=35 * (k + 1))).isoformat()
        for j in range(2):
            sess = (today + timedelta(days=35 * k + j)).isoformat()
            pay = {"A": 12.0 + rng.normal(), "B": 11.0, "C": 3.0, "D": 2.0 + rng.normal() * 0.1}
            for s, v in pay.items():
                rows.append({"session_date": sess, "symbol": s, "payoff": v, "ask_sum": 6.0, "bid_sum": 5.0})
            books.append(_book(sess, exp, "ridge", ["A", "B"], ["C", "D"]))
            books.append(_book(sess, exp, "vol", ["C", "D"], ["A", "B"]))
    co = SF.cohort_returns(pd.DataFrame(rows), books)
    assert co["complete"].all() and len(co) == 32
    r = SF.book_vs_twin(co)["2"]
    assert r["n_expiry_blocks"] == 8 and r["n_cohorts"] == 16
    assert r["diff_equity_bp_mean"] > 0
    assert r["log_utility_diff_by_expiry"]["t_blocks"] > 2
    assert r["kill_rule"].startswith("RUNNING")
    hc = SF.book_vs_twin(SF.cohort_returns(pd.DataFrame(rows), books, exit_haircut=0.05))["2"]
    assert hc["ridge_ls_mean_on_premium"] < r["ridge_ls_mean_on_premium"]


def test_kill_rule_fires_only_after_min_blocks_on_failed_variant():
    assert SF.kill_rule_state({"n_blocks": 3, "mean_monthly": -1.0, "t_blocks": -5}).startswith("TOO_FEW")
    assert SF.kill_rule_state({"n_blocks": SF.MIN_BLOCKS_KILL, "mean_monthly": -0.001,
                               "t_blocks": -1.2}).startswith("KILL")
    assert SF.kill_rule_state({"n_blocks": SF.FIRST_READ_BLOCKS, "mean_monthly": 0.001,
                               "t_blocks": 0.5}) == "FIRST_READ_DUE"


def test_short_leg_worst_case_scales_with_sigma_and_is_labelled_unbounded():
    s = [{"spot": 100.0, "strike": 100.0, "bid_sum": 5.0, "iv_atm": 0.30, "days_to_expiry": 30.0}] * 10
    w = SF.short_leg_worst_case(s, equity=1_000_000, budget=0.02)
    assert w["long_leg_worst_case"] == -20_000
    move3 = 3 * 0.30 * math.sqrt(30 / 365) * 100
    per = 2_000 / 5.0 * (move3 - 5.0)
    assert w["3_sigma"]["loss_per_name_max"] == pytest.approx(-per)
    assert w["3_sigma"]["loss_leg_all_names_at_once"] == pytest.approx(-10 * per)
    assert w["10_sigma"]["loss_leg_all_names_at_once"] < w["3_sigma"]["loss_leg_all_names_at_once"]
    assert "DEFINED-RISK" in w["unbounded"]
