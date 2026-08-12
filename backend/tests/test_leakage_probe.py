"""LLM-LEAKAGE-PROBE-1 — the masker is the experiment, so the masker is tested.

A leak in the masker does not produce a wrong answer. It produces a CONFIDENT
one: the masked arm quietly becomes a second identified arm, the gap collapses
to zero, and "no leakage detectable" gets reported as a finding when it is a
bug. Every test below exists because that failure is invisible from the outside.

These are offline. Nothing here touches the network or the vendor.
"""
from __future__ import annotations

import json

import pytest

from backend.services import leakage_probe as lp

SNAP = {
    "ticker": "NVDA",
    "as_of": "2020-03-16",
    "n_bars_available": 500,
    "last_close": 217.83,
    "trailing_return_pct": {"1d": -3.4, "5d": -12.1, "21d": -18.0,
                            "63d": -9.2, "126d": 4.4, "252d": 31.5},
    "realised_vol_annualised_pct": {"21d": 88.4, "63d": 52.1},
    "max_drawdown_1y_pct": -37.2,
    "pct_below_1y_high": -34.0,
    "pct_above_1y_low": 3.1,
    "beta_vs_benchmark": 1.62,
    "excess_return_63d_pct_vs_benchmark": 6.7,
    "benchmark": "SPY",
    "benchmark_trailing_return_pct": {"21d": -22.1, "63d": -19.4, "252d": -8.8},
    "sector": "Technology",
    "industry": "Semiconductors",
    "company_name": "NVIDIA Corporation",
    "market_cap_usd": 133_000_000_000,
}


def _slate():
    s = lp.slate_for(SNAP)
    assert s is not None
    return s


# ── the mask removes identity, and keeps everything predictive ──────────────

def test_the_masked_snapshot_carries_no_identifier():
    m = lp.mask_snapshot(SNAP)
    blob = json.dumps(m)
    for banned in ("NVDA", "NVIDIA", "2020", "SPY", "217.83"):
        assert banned not in blob, f"{banned!r} survived the mask"


def test_every_numeric_feature_survives_the_mask_unchanged():
    """The arms must differ in IDENTITY ONLY.

    If the masked arm were also a smaller feature set, a gap between the arms
    would measure 'arm A had more inputs' rather than 'arm A had the answer',
    and the headline number would be uninterpretable.
    """
    m = lp.mask_snapshot(SNAP)
    for k in ("trailing_return_pct", "realised_vol_annualised_pct",
              "max_drawdown_1y_pct", "pct_below_1y_high", "pct_above_1y_low",
              "beta_vs_benchmark", "excess_return_63d_pct_vs_benchmark",
              "benchmark_trailing_return_pct", "n_bars_available", "sector",
              "industry"):
        assert m[k] == SNAP[k], f"{k} was altered by the identity mask"


def test_the_deep_mask_removes_the_era_channel_too():
    m = lp.mask_snapshot(SNAP, deep=True)
    assert "benchmark_trailing_return_pct" not in m
    assert "industry" not in m
    assert m["sector"] == "cyclical-growth"
    # ...but the security's own numbers still survive, or the deep arm would be
    # measuring feature removal rather than era removal.
    assert m["beta_vs_benchmark"] == SNAP["beta_vs_benchmark"]
    assert m["trailing_return_pct"] == SNAP["trailing_return_pct"]


def test_the_pseudonym_is_stable_and_cannot_spell_a_real_ticker():
    a = lp.pseudonym("NVDA", "2020-03-16")
    assert a == lp.pseudonym("NVDA", "2020-03-16")
    assert a != lp.pseudonym("NVDA", "2020-03-17")
    assert a != lp.pseudonym("AMD", "2020-03-16")
    assert "-" in a and a.startswith("UNIT-")


# ── the violation scanner: it must actually catch things ────────────────────

def test_the_scanner_catches_every_class_of_leak():
    base = "situation with beta 1.6 and drawdown -37%"
    cases = {
        "own_ticker": base + " NVDA",
        "company_name_token": base + " NVIDIA reported",
        "iso_date": base + " on 2020-03-16",
        "bare_year": base + " during 2020",
        "benchmark_name": base + " versus SPY",
        "absolute_price_level": base + " last close 217.83",
    }
    for kind, text in cases.items():
        v = lp.masking_violations(text, ticker="NVDA",
                                  company_name="NVIDIA Corporation",
                                  as_of="2020-03-16", last_close=217.83)
        assert any(x["kind"] == kind for x in v), f"missed {kind}: {v}"


def test_a_clean_masked_prompt_raises_no_violation():
    system, user = lp.build_prompt("company_fundamental",
                                   lp.mask_snapshot(SNAP), _slate(),
                                   arm="masked")
    v = lp.masking_violations(user, ticker="NVDA",
                              company_name="NVIDIA Corporation",
                              as_of="2020-03-16", last_close=217.83,
                              other_tickers=["AMD", "INTC", "MSFT"])
    assert v == [], f"the rendered masked prompt leaks: {v}"


def test_the_identified_prompt_DOES_leak_which_is_the_point():
    """The scanner would be worthless if it could not tell the arms apart.

    A check that passes on both arms is not a check; it is a decoration. This
    is the positive control for the control.
    """
    system, user = lp.build_prompt("company_fundamental", SNAP, _slate(),
                                   arm="identified")
    v = lp.masking_violations(user, ticker="NVDA",
                              company_name="NVIDIA Corporation",
                              as_of="2020-03-16", last_close=217.83)
    kinds = {x["kind"] for x in v}
    assert "own_ticker" in kinds and "iso_date" in kinds


def test_generic_corporate_tokens_are_not_treated_as_a_leak():
    """'Corporation' in a prompt is not NVIDIA. A scanner that fires on every
    prompt trains its reader to ignore it, which is worse than not running."""
    v = lp.masking_violations("a diversified holdings group company",
                              ticker="NVDA",
                              company_name="NVIDIA Corporation")
    assert v == []


def test_short_symbols_are_not_scanned_and_the_reason_is_stated():
    """Two-letter symbols collide with ordinary uppercase words. The item's OWN
    ticker is always scanned regardless of length."""
    v = lp.masking_violations("IT IS ON", ticker="NVDA",
                              other_tickers=["IT", "ON", "SO"])
    assert v == []
    v2 = lp.masking_violations("the security IT moved", ticker="IT")
    assert any(x["kind"] == "own_ticker" for x in v2)


def test_a_market_cap_containing_a_year_like_run_is_not_a_false_year():
    assert lp.masking_violations("market_cap_usd: 2019000000", ticker="ZZZZ") == []


# ── the runner refuses rather than repairs ──────────────────────────────────

def test_a_masked_cell_whose_prompt_leaks_is_refused_before_the_wire():
    """A prompt patched after the fact is a prompt nobody can reconstruct."""
    called = []

    def never(*a, **k):
        called.append(1)
        raise AssertionError("the vendor must not be called on a leaking cell")

    # A snapshot that keeps its ticker is exactly the accident being guarded
    # against: masking applied in the wrong place, or not at all.
    r = lp.run_cell(cell_id="t1", condition="core", arm="masked",
                    role="company_fundamental",
                    item={"ticker": "NVDA", "as_of": "2020-03-16",
                          "era": "pre_cutoff",
                          "made_at": "2020-03-16T00:00:00+00:00",
                          "company_name": "NVIDIA Corporation",
                          "last_close": 217.83, "universe": ["NVDA"]},
                    snapshot=SNAP, slate=_slate(), llm=never)
    assert r.status == "refused_mask"
    assert not called
    assert r.extra["violations"]


# ── the fixed slate is what makes the pairing possible ──────────────────────

def test_thresholds_are_decimal_fractions_below_one():
    s = _slate()
    for row in s:
        if row["threshold"] is not None:
            assert 0.0 < row["threshold"] < 1.0


def test_both_arms_are_asked_the_identical_questions():
    s = _slate()
    _, u_id = lp.build_prompt("skeptic", SNAP, s, arm="identified")
    _, u_mk = lp.build_prompt("skeptic", lp.mask_snapshot(SNAP), s, arm="masked")
    block = lp._slate_block(s)
    assert block in u_id and block in u_mk


def test_a_missing_slot_is_counted_not_silently_dropped():
    s = _slate()
    reply = json.dumps({
        "abstain": False, "market_implied_expectation": "x",
        "optimus_expectation": "y", "expectation_discrepancy": "z",
        "causal_chain": ["a"], "confidence": 0.6, "counterargument": "c",
        "forecasts": [{"key": "q1", "probability": 0.6, "thesis": "t",
                       "counter_thesis": "ct"}]})
    p = lp.parse_reply("skeptic", "NVDA", s, reply)
    assert len(p.forecasts) == 1
    missing = [r for r in p.rejections if r["reason"] == "slot_missing"]
    assert len(missing) == 4


def test_a_coin_flip_is_refused_and_named():
    s = _slate()
    reply = json.dumps({
        "abstain": False, "market_implied_expectation": "x",
        "optimus_expectation": "y", "expectation_discrepancy": "z",
        "causal_chain": ["a"], "confidence": 0.6, "counterargument": "c",
        "forecasts": [{"key": "q1", "probability": 0.50, "thesis": "t",
                       "counter_thesis": "ct"}]})
    p = lp.parse_reply("skeptic", "NVDA", s, reply)
    assert p.forecasts == []
    assert any(r["reason"] == "coin_flip_filler" for r in p.rejections)


def test_recommendation_language_is_refused():
    s = _slate()
    reply = json.dumps({
        "abstain": False, "market_implied_expectation": "x",
        "optimus_expectation": "y", "expectation_discrepancy": "z",
        "causal_chain": ["a"], "confidence": 0.6, "counterargument": "c",
        "forecasts": [{"key": "q2", "probability": 0.62, "thesis": "buy this",
                       "counter_thesis": "ct"}]})
    p = lp.parse_reply("skeptic", "NVDA", s, reply)
    assert p.forecasts == []
    assert any(r["reason"] == "recommendation_language" for r in p.rejections)


# ── model provenance: the requested name is never evidence ──────────────────

def test_a_reply_with_no_served_model_is_marked_unverified():
    r = lp.Reply(text="{}", model_version="deepseek-v4-flash")
    assert r.model_unverified is True
    r2 = lp.Reply(text="{}", model_version="deepseek-v4-flash",
                  served_model="deepseek-v4-flash")
    assert r2.model_unverified is False


def test_the_alias_trap_is_documented_in_the_real_model_list():
    """`deepseek-chat`/`deepseek-reasoner` both resolve to v4-flash. Anything
    that treats them as two models compares one model with itself."""
    assert "deepseek-chat" not in lp.REAL_MODELS
    assert "deepseek-reasoner" not in lp.REAL_MODELS
    assert set(lp.REAL_MODELS) == {"deepseek-v4-flash", "deepseek-v4-pro"}


# ── the statistics ──────────────────────────────────────────────────────────

def test_the_paired_difference_reports_three_ses_and_uses_the_widest():
    pairs = [{"as_of": f"2020-0{1 + i % 9}-15", "d": 0.01 * ((-1) ** i)}
             for i in range(90)]
    d = lp.paired_difference(pairs)
    assert d["n_pairs"] == 90 and d["n_dates"] == 9
    ses = [d["se_iid_pairs"], d["se_cluster_date"], d["se_hac_date"]]
    assert d["se_used"] == pytest.approx(max(x for x in ses if x is not None))


def test_an_mde_is_refused_when_there_are_too_few_dates():
    pairs = [{"as_of": "2020-01-15", "d": 0.02} for _ in range(50)]
    out = lp.measure_mde(pairs, n_sim=20)
    assert out["mde_at_80pct_power"] is None
    assert "date" in out["reading"]


def test_the_did_is_a_difference_with_its_own_se():
    a = [{"as_of": f"2016-{m:02d}-15", "d": 0.05} for m in range(1, 13)]
    b = [{"as_of": f"2025-{m:02d}-15", "d": 0.00} for m in range(1, 13)]
    out = lp.difference_in_differences(a, b, n_boot=200)
    assert out["difference_in_differences"] == pytest.approx(0.05, abs=1e-9)
    assert out["se_cluster_bootstrap"] is not None


def test_calibration_reports_n_beside_every_number():
    rows = [{"outcome": 1, "brier": 0.09, "probability": 0.7} for _ in range(7)]
    c = lp.calibration_slice(rows)
    assert c["n"] == 7
    assert "climatology_brier" in c and "beats_climatology" in c


def test_effective_distinct_ideas_matches_the_swarm_rule():
    from backend.services import llm_swarm as sw
    preds = [{"ticker": "AAA", "observable": "return_sign", "probability": 0.61,
              "horizon_days": 20},
             {"ticker": "AAA", "observable": "return_sign", "probability": 0.62,
              "horizon_days": 20},
             {"ticker": "BBB", "observable": "return_sign", "probability": 0.61,
              "horizon_days": 20}]
    assert (lp.effective_distinct_ideas(preds)["effective_distinct_ideas"]
            == sw.effective_distinct_ideas(preds)["effective_distinct_ideas"])


# ── the ledger rule that matters most ───────────────────────────────────────

def test_the_historical_ledger_is_not_the_forward_ledger():
    """The forward ledger's entire value is that it is forward-only. Backfilled
    historical records in it would destroy the one clean instrument there is."""
    from backend.services import belief_state as bs
    assert lp.LEAK_PREDICTIONS != bs.PREDICTIONS
    assert lp.LEAK_PREDICTIONS.name == "leakage_probe_predictions.jsonl"


def test_a_historical_record_resolves_in_the_past():
    from backend.services.belief_state import PredictionRecord
    r = PredictionRecord.resolution_date("2020-03-16T00:00:00+00:00", 20)
    assert r < "2021-01-01"
