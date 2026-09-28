"""Pure functions of the two LANE X experiment scripts (2026-09-28).

Synthetic data only: no network, no GPU, no LLM. What is pinned:
  * PIT slicing never returns a bar after t; the outcome window starts after t;
  * the blinding map is a reversible bijection and leaves no alias behind;
  * the scoring functions (QLIKE, spread net of costs, Wilson, summary);
  * the cap refuses on unknown spend and on spend + next > cap.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from scripts import exp_kronos_2026_09_28 as K
from scripts import exp_llm_blind_gap_2026_09_28 as X


def _bars(n=600, seed=0, start="2022-01-03"):
    rng = np.random.default_rng(seed)
    d = pd.bdate_range(start, periods=n)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame({"date": d, "close": c, "volume": rng.integers(1e5, 1e6, n).astype(float)})


# ───────────────────────── X1: PIT ──────────────────────────────────────────
def test_pit_slice_never_returns_future_bars():
    g = _bars()
    t = g["date"].iloc[450]
    s = K.pit_slice(g, t, 400)
    assert s["date"].max() == t
    assert len(s) == 400
    assert (s["date"] <= t).all()


def test_forward_outcome_starts_after_t_and_flags_truncation():
    g = _bars(n=460)
    t = g["date"].iloc[449]
    fo = K.forward_outcome(g, t, h=21)
    assert fo["n_fwd"] == 10 and fo["truncated"]
    c0 = g["close"].iloc[449]
    assert fo["fwd_ret"] == pytest.approx(g["close"].iloc[-1] / c0 - 1)
    fo2 = K.forward_outcome(g, g["date"].iloc[100], h=21)
    assert fo2["fwd_ret"] == pytest.approx(g["close"].iloc[121] / g["close"].iloc[100] - 1)
    assert not fo2["truncated"]


def test_future_stamps_are_calendar_not_realised_sessions():
    t = pd.Timestamp("2026-07-02")          # July 3 is a market holiday
    fs = K.future_stamps(t, 5)
    assert fs[0] == pd.Timestamp("2026-07-03")   # business day, not the realised calendar
    assert len(fs) == 5 and (fs > t).all()


def test_hold_month_and_cutoff_split():
    assert K.hold_month(pd.Timestamp("2024-06-28")) == "2024-07"
    assert K.is_post_cutoff("2024-07") and not K.is_post_cutoff("2024-06")


def test_month_end_sessions():
    d = pd.bdate_range("2024-01-01", "2024-03-31")
    me = K.month_end_sessions(d)
    assert [str(x.date()) for x in me] == ["2024-01-31", "2024-02-29", "2024-03-29"]


def test_mom_and_trailing_vol_use_only_given_history():
    c = np.arange(1, 301, dtype=float)
    assert K.mom_12_1(c) == pytest.approx(c[-22] / c[-253] - 1)
    assert math.isnan(K.mom_12_1(c[:200]))
    assert math.isnan(K.trailing_vol(c[:50]))


def test_sample_names_deterministic_and_bounded():
    el = [f"S{i}" for i in range(1000)]
    t = pd.Timestamp("2025-03-31")
    a, b = K.sample_names(el, t), K.sample_names(list(reversed(el)), t)
    assert a == b and len(a) == K.N_NAMES


# ───────────────────────── X1: scoring ──────────────────────────────────────
def test_qlike_zero_at_truth_and_penalises_under_more():
    assert K.qlike(0.02, 0.02) == pytest.approx(0.0)
    under = K.qlike(0.02, 0.01)
    over = K.qlike(0.02, 0.04)
    assert under > over > 0


def test_path_stats_keeps_per_path_variance():
    rng = np.random.default_rng(1)
    paths = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, (64, 21)), axis=1))
    r, sd = K.path_stats(100.0, paths)
    assert sd == pytest.approx(0.03, rel=0.2)
    assert r == pytest.approx(np.mean(paths[:, -1] / 100 - 1))


def test_spread_net_pays_costs_on_both_legs():
    n = 100
    score = pd.Series(np.arange(n, dtype=float))
    fwd = pd.Series(np.where(np.arange(n) >= 80, 0.05, np.where(np.arange(n) < 20, -0.05, 0.0)))
    cost = pd.Series(np.full(n, 0.0018))
    out = K.spread_net(score, fwd, cost, k=20)
    assert out["ls_net"] == pytest.approx(0.10 - 2 * 0.0018)
    assert out["long_net"] == pytest.approx(0.05 - 0.0018)
    assert out["random_net"] == pytest.approx(fwd.mean() - 0.0018)


def test_series_summary_prints_year_loyo_and_without_best5():
    idx = [f"{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
    x = pd.Series(np.r_[np.full(12, -0.01), np.full(12, 0.03)], index=idx)
    s = K.series_summary(x)
    assert s["by_year"]["2025"]["mean"] == pytest.approx(0.03)
    assert s["leave_one_year_out"]["2025"] == pytest.approx(-0.01)
    assert s["mean_without_best_5"] < s["mean"]
    assert s["mde_80"] == pytest.approx(2.8 * s["se"])


def test_decide_rule():
    good = {"n_dates": 26, "qlike_diff": {"mean": -0.1, "t": -3.0},
            "kronos_long_minus_random": {"mean": 0.001, "t": 0.5}}
    assert K.decide(good)["verdict"] == "PARTIAL: vol"
    bad = {"n_dates": 26, "qlike_diff": {"mean": -0.1, "t": -1.0},
           "kronos_long_minus_random": {"mean": 0.001, "t": 0.5}}
    assert K.decide(bad)["verdict"] == "FAILED_VARIANT"


# ───────────────────────── X2: blinding ─────────────────────────────────────
def test_blinding_map_is_reversible_bijection_without_ticker_letters():
    tk = ["NVDA", "AAPL", "F", "MSFT", "T"]
    m = X.make_codes(tk)
    inv = X.invert(m)
    assert {inv[m[t]] for t in tk} == set(tk)
    assert len(set(m.values())) == len(tk)
    for t, code in m.items():
        assert t not in code.replace("STOCK_", "")


def test_invert_refuses_non_bijection():
    with pytest.raises(ValueError):
        X.invert({"A": "STOCK_1", "B": "STOCK_1"})


def test_blind_text_leaves_no_alias():
    al = X.name_aliases("NVDA", "NVIDIA CORP")
    assert "NVDA" in al and any(a.upper() == "NVIDIA" for a in al)
    txt = "Nvidia beats; NVDA shares rise as NVIDIA guides up"
    out = X.blind_text(txt, al, "STOCK_123")
    assert X.leaks(out, al) == []
    assert out.count("STOCK_123") == 3


def test_single_letter_ticker_only_replaced_in_exact_case():
    al = X.name_aliases("F", "FORD MOTOR CO")
    out = X.blind_text("F shares: a Ford recall, f-stop", al, "STOCK_9")
    assert "Ford" not in out and out.startswith("STOCK_9 shares")
    assert "f-stop" in out


def test_date_shift_round_trips():
    assert X.unshift_date(X.shift_date("2026-08-14")) == "2026-08-14"
    assert X.shift_date("2026-08-14").startswith("2036")


def test_headlines_strictly_before_decision_close():
    t = pd.Timestamp("2026-08-14")
    news = pd.DataFrame({"symbol": ["A"] * 4,
                         "title": ["old", "morning", "after close", "next day"],
                         "pub": pd.to_datetime(["2026-07-01T12:00Z", "2026-08-14T13:00Z",
                                                "2026-08-14T20:30Z", "2026-08-15T10:00Z"], utc=True)})
    h = X.headlines_before(news, "A", t)
    assert [x[1] for x in h] == ["morning"]


def test_price_summary_has_no_levels():
    g = _bars(300)
    s = X.price_summary(g["close"].to_numpy(), g["volume"].to_numpy())
    assert set(s) == {"ret_1d_pct", "ret_5d_pct", "ret_21d_pct", "ret_63d_pct", "ret_252d_pct",
                      "vol_21d_daily_pct", "vol_63d_daily_pct", "pct_below_52w_high",
                      "volume_5d_vs_63d"}


# ───────────────────────── X2: schema, parse, scoring, cap ──────────────────
def test_system_prompt_carries_the_schema_it_asks_for():
    for k in X.RESPONSE_KEYS:
        assert f'"{k}"' in X.SYSTEM_PROMPT


def test_parse_reply_validates_rows():
    txt = ('```json\n[{"id":"S1","direction":"up","ret_low_pct":-2,"ret_high_pct":4,"confidence":0.6},'
           '{"id":"S2","direction":"sideways","ret_low_pct":-2,"ret_high_pct":4,"confidence":0.6},'
           '{"id":"S3","direction":"down","ret_low_pct":3,"ret_high_pct":1,"confidence":0.6},'
           '{"id":"S9","direction":"down","ret_low_pct":-3,"ret_high_pct":1,"confidence":0.6}]\n```')
    p = X.parse_reply(txt, ["S1", "S2", "S3"])
    assert list(p) == ["S1"]
    assert X.parse_reply(None, ["S1"]) == {} and X.parse_reply("no json", ["S1"]) == {}


def test_wilson_interval():
    lo, hi = X.wilson(50, 100)
    assert lo < 0.5 < hi and hi - lo == pytest.approx(0.192, abs=0.005)
    assert all(math.isnan(v) for v in X.wilson(0, 0))


def test_implied_sd_and_qlike_sq():
    assert X.implied_sd_pct(-1.2815516, 1.2815516) == pytest.approx(1.0)
    a = X.qlike_sq(2.0, 2.0)
    assert a < X.qlike_sq(2.0, 0.5) and a < X.qlike_sq(2.0, 8.0)


def test_cap_refuses_unknown_spend_and_overrun():
    assert X.cap_allows(0.10, 0.01, cap=1.50)
    assert not X.cap_allows(1.495, 0.01, cap=1.50)
    assert not X.cap_allows(None, 0.0, cap=1.50)
    assert not X.cap_allows(float("nan"), 0.0, cap=1.50)


def test_estimate_cutoff():
    e = {"2025-01": [0.01, 0.02, 0.01, None, 0.3],
         "2025-02": [0.01, 0.2, 0.01, 0.03, None],
         "2025-03": [None, None, 0.5, 0.4, None]}
    assert X.estimate_cutoff(e, tol=0.06, need=3) == "2025-02"
    assert X.estimate_cutoff({"2025-01": [None] * 5}) is None


def test_prompts_blinded_arm_has_no_own_alias_and_named_arm_does():
    summ = {"ret_1d_pct": 1.0, "ret_5d_pct": 2.0}
    items = [{"set": "post", "symbol": "NVDA", "date": "2026-08-14", "summary": summ,
              "headlines": [("2026-08-13", "Nvidia (NVDA) guides up")], "events": [],
              "fwd_ret_pct": 1.0, "prior_sd_pct": 3.0},
             {"set": "post", "symbol": "AAPL", "date": "2026-08-14", "summary": summ,
              "headlines": [("2026-08-12", "Apple Inc. unveils phone")], "events": [],
              "fwd_ret_pct": -1.0, "prior_sd_pct": 3.0}]
    plan = {"items": items, "codes": X.make_codes(["NVDA", "AAPL"]),
            "titles": {"NVDA": "NVIDIA CORP", "AAPL": "Apple Inc."}}
    calls = X.prompts_for(plan)
    assert {c["arm"] for c in calls} == {"NAMED", "BLINDED"}
    for c in calls:
        for (s, _), txt in zip(c["items"], c["item_texts"]):
            lk = X.leaks(txt, X.name_aliases(s, plan["titles"][s]))
            if c["arm"] == "BLINDED":
                assert lk == [] and "2036-08-14" in txt and "2026-08" not in txt
            else:
                assert lk


# ───────────────────────── X2: cap across stages, declared rule ─────────────
def test_prior_spend_carries_across_stages_and_refuses_unpriced(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(X, "OUT_DIR", tmp_path)
    assert X.prior_spend("r") == 0.0
    (tmp_path / "x2_r_probe.json").write_text(_json.dumps({"spent_usd_served_row": 0.2}))
    (tmp_path / "x2_r_calls.jsonl").write_text(
        _json.dumps({"error": None, "cost_usd_served_row": 0.5}) + "\n"
        + _json.dumps({"error": "boom", "cost_usd_served_row": None}) + "\n")
    assert X.prior_spend("r") == pytest.approx(0.7)
    with open(tmp_path / "x2_r_calls.jsonl", "a") as f:
        f.write(_json.dumps({"error": None, "cost_usd_served_row": None}) + "\n")
    assert X.prior_spend("r") is None
    assert not X.cap_allows(X.prior_spend("r"), 0.0)


def _g(hit, lo, hi, t, always_up, q=0.1, qse=0.1):
    return {"by_set_arm": {"post|BLINDED": {
        "hit_rate": hit, "wilson95": (lo, hi), "always_up_hit": always_up,
        "hit_date_block": {"t": t},
        "magnitude": {"qlike_llm_minus_prior_mean": q, "qlike_diff_se": qse}}}}


def test_decide_x2_rule():
    assert X.decide_x2(_g(0.60, 0.55, 0.65, 3.0, 0.52))["verdict"] == "ALPHA_DETECTED"
    assert X.decide_x2(_g(0.60, 0.55, 0.65, 3.0, 0.62))["verdict"] == "BETA_EXPLAINS"
    assert X.decide_x2(_g(0.49, 0.45, 0.54, 0.0, 0.5))["verdict"] == "FAILED_VARIANT"
    assert X.decide_x2(_g(0.52, 0.47, 0.57, 0.5, 0.5))["verdict"] == "CANNOT_DISTINGUISH"
    assert X.decide_x2(_g(0.49, 0.45, 0.54, 0.0, 0.5, q=-0.5, qse=0.1))["verdict"] \
        == "CANNOT_DISTINGUISH"
    assert X.decide_x2({"by_set_arm": {}})["verdict"] == "NO_POST_BLINDED_ROWS"


def test_spearman_matches_pandas_without_scipy_and_drops_pairwise_nan():
    # .venv_kronos has no scipy; the analysis must not need it, and must agree
    # with pandas' own spearman (which uses scipy) to float precision.
    rng = np.random.default_rng(7)
    a = rng.normal(size=200)
    b = a + rng.normal(size=200)
    a[[3, 50]] = np.nan
    b[[4, 50, 99]] = np.nan
    b[10:15] = 1.0                                    # ties -> average ranks
    want = pd.Series(a).corr(pd.Series(b), method="spearman")
    assert K.spearman(a, b) == pytest.approx(want, abs=1e-12)
    assert math.isnan(K.spearman([1.0, np.nan], [np.nan, 2.0]))
