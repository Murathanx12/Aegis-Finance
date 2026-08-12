"""Tests for the why-moved module — the spec, written as assertions.

Every test here is OFFLINE: the price panel is a fixture and the language model
is a fake. The fast suite blocks the network on purpose, and a unit test that
reaches for it is a bug (backend/tests/conftest.py).

The tests are grouped by the thing they protect:
  * the arithmetic adds up, and refuses to add up quietly when it cannot;
  * an ungradeable hypothesis is REJECTED and COUNTED, never stored;
  * corroboration grading puts hit / miss / unavailable in the right buckets,
    including the sign conventions of the relative and magnitude kinds;
  * degradation is explicit and never fabricates;
  * the forward claim reaches the real ledger, with the real refusals.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backend.services import why_moved as wm
from backend.services.belief_state import HORIZONS

BENCH = "SPY"
ASSETS = ["AAA", "BBB", BENCH, "XLV", "XLK", "QQQ", "TLT", "^VIX", "CL=F"]
DAYS = 300


@pytest.fixture
def panel() -> pd.DataFrame:
    """A deterministic price panel ending 2026-08-10, business days only.

    The last two sessions are hand-set so every expectation in the file is
    arithmetic a reader can check by eye rather than a property of the RNG.
    """
    idx = pd.bdate_range(end="2026-08-10", periods=DAYS)
    rng = np.random.default_rng(20260814)
    df = pd.DataFrame(index=idx, dtype="float64")
    for i, t in enumerate(ASSETS):
        steps = rng.normal(0.0003, 0.012 + 0.004 * i, DAYS)
        df[t] = 100.0 * np.exp(np.cumsum(steps))
    # prev close = 100 for everything, then a hand-set final day
    df.iloc[-2] = 100.0
    df.iloc[-1] = pd.Series({
        "AAA": 95.0,      # -5%
        "BBB": 102.0,     # +2%
        BENCH: 99.0,      # -1%
        "XLV": 98.0,      # -2%
        "XLK": 101.0,     # +1%
        "QQQ": 98.5,      # -1.5%, i.e. underperforms SPY
        "TLT": 100.5,     # +0.5%
        "^VIX": 104.0,    # +4%
        "CL=F": 97.0,     # -3%
    })
    return df


@pytest.fixture
def positions() -> list[tuple[str, float]]:
    return [("AAA", 100.0), ("BBB", 50.0)]


SECTORS = {"AAA": "Health Care", "BBB": "Information Technology"}


def _attr(panel, positions, **kw):
    return wm.attribute_move(positions, panel, "2026-08-10", benchmark=BENCH,
                             sector_map=SECTORS, **kw)


# ── the arithmetic ──────────────────────────────────────────────────────────

def test_contributions_sum_to_total_pnl(panel, positions):
    a = _attr(panel, positions)
    assert a.as_of == "2026-08-10"
    # 100 shares x -$5 + 50 shares x +$2 = -$400 on a $15,000 book
    assert a.pnl_usd == pytest.approx(-400.0)
    assert sum(p.pnl_usd for p in a.positions) == pytest.approx(a.pnl_usd, abs=1e-9)
    assert (sum(p.contribution_pct for p in a.positions)
            == pytest.approx(a.pnl_pct, abs=1e-9))
    assert (sum(p.contribution_bps for p in a.positions)
            == pytest.approx(a.pnl_pct * 100.0, abs=1e-6))


def test_decomposition_closes_exactly(panel, positions):
    """market + sector + residual is the whole move, by construction."""
    a = _attr(panel, positions)
    assert (a.market_component_pct + a.sector_component_pct + a.idiosyncratic_pct
            == pytest.approx(a.pnl_pct, abs=1e-9))
    assert (a.market_component_usd + a.sector_component_usd + a.idiosyncratic_usd
            == pytest.approx(a.pnl_usd, abs=1e-6))


def test_unpriceable_book_fails_loud_not_zero(panel, positions):
    """A name we cannot price is an error, never a $0 contribution."""
    with pytest.raises(wm.PricingError) as e:
        _attr(panel, positions + [("GHOST", 10.0)])
    assert "GHOST" in str(e.value)


def test_missing_benchmark_fails_loud(panel, positions):
    with pytest.raises(wm.PricingError):
        wm.attribute_move(positions, panel.drop(columns=[BENCH]), "2026-08-10",
                          benchmark=BENCH, sector_map=SECTORS)


def test_weekend_walks_back_and_says_which_day(panel, positions):
    """2026-08-15 is a Saturday; the answer must name the day it graded."""
    a = wm.attribute_move(positions, panel, "2026-08-15", benchmark=BENCH,
                          sector_map=SECTORS)
    assert a.requested_date == "2026-08-15"
    assert a.as_of == "2026-08-10"
    assert a.prev_close_date == "2026-08-07"


def test_unmapped_sector_is_named_not_swallowed(panel, positions):
    a = wm.attribute_move(positions, panel, "2026-08-10", benchmark=BENCH,
                          sector_map={"AAA": "Health Care"})
    assert a.sector_unmapped == ["BBB"]
    assert any("BBB" in n for n in a.notes)


def test_short_history_beta_defaults_and_is_named(panel, positions):
    a = _attr(panel, positions, beta_lookback=5, min_beta_obs=60)
    assert set(a.beta_fallbacks) == {"AAA", "BBB"}
    assert all(p.beta == 1.0 for p in a.positions)


def test_walkback_skips_a_day_the_whole_book_does_not_print(panel, positions):
    """The live failure of 2026-08-11: SPY closed, the small caps had not."""
    p = panel.copy()
    p.loc[p.index[-1], "AAA"] = np.nan          # vendor lag on one name only
    day, skipped = wm.last_priceable_session(positions, p, "2026-08-10",
                                             benchmark=BENCH)
    assert day == "2026-08-07"
    assert len(skipped) == 1 and "AAA" in skipped[0]


def test_walkback_gives_up_loudly(panel, positions):
    p = panel.copy()
    p["AAA"] = np.nan
    with pytest.raises(wm.PricingError) as e:
        wm.last_priceable_session(positions, p, "2026-08-10", benchmark=BENCH,
                                  max_walkback=2)
    assert "no session in the last 3" in str(e.value)


def test_universe_covers_book_sector_proxies_and_benchmark():
    u = wm.universe_for([("SOC", 1.0), ("HUBS", 1.0)])
    assert {"SOC", "HUBS", "XLE", "XLK", "SPY", "^VIX"} <= set(u)


# ── parsing: what gets refused ──────────────────────────────────────────────

ALLOWED = set(ASSETS)


def _hyp(**over) -> dict:
    base = {
        "hypothesis_id": "h1",
        "claim": "Long-duration risk repriced on a hawkish rates impulse.",
        "causal_chain": ["yields rose", "long-duration equity discounted harder"],
        "affected_assets": [{"ticker": "AAA", "expected_sign": "down"}],
        "confidence": 0.4,
        "counter_evidence": "TLT was up, which is the opposite sign.",
        "falsification_condition": "TLT rises while small caps fall",
        "evidence": [{"what": "CPI print", "source": "BLS",
                      "first_public_timestamp": "2026-08-10T12:30:00Z"}],
        "cross_asset_corroboration": [
            {"kind": "direction", "asset": "TLT", "expect": "down"}],
        "next_observable": {"ticker": "AAA", "observable": "return_sign",
                            "horizon_days": 2, "probability": 0.45,
                            "threshold": None, "claim": "AAA up over two days"},
    }
    base.update(over)
    return base


def test_ungradeable_hypothesis_is_rejected_and_counted():
    """No corroboration and no forward claim: it cannot be wrong, so it is out."""
    raw = {"hypotheses": [_hyp(cross_asset_corroboration=[], next_observable=None)]}
    kept, rejected = wm.parse_hypotheses("macro_rates", raw, allowed_assets=ALLOWED)
    assert kept == []
    assert len(rejected) == 1
    assert "ungradeable" in rejected[0]["reason"]
    assert rejected[0]["hypothesis_id"] == "h1"


def test_one_checkable_assertion_is_enough():
    raw = {"hypotheses": [_hyp(next_observable=None)]}
    kept, rejected = wm.parse_hypotheses("macro_rates", raw, allowed_assets=ALLOWED)
    assert len(kept) == 1 and rejected == []
    assert kept[0].forward is None


def test_forward_claim_alone_is_enough():
    raw = {"hypotheses": [_hyp(cross_asset_corroboration=[])]}
    kept, _ = wm.parse_hypotheses("macro_rates", raw, allowed_assets=ALLOWED)
    assert len(kept) == 1 and kept[0].forward.horizon_days in HORIZONS


def test_assertion_outside_the_priceable_universe_is_not_a_check():
    """An unknown instrument leaves the hypothesis with nothing to check."""
    raw = {"hypotheses": [_hyp(
        cross_asset_corroboration=[{"kind": "direction", "asset": "NOPE",
                                    "expect": "up"}],
        next_observable=None)]}
    kept, rejected = wm.parse_hypotheses("geopolitical", raw, allowed_assets=ALLOWED)
    assert kept == []
    assert any("NOPE" in s for s in rejected[0]["sub_reasons"])


def test_recommendation_language_is_refused_and_the_evidence_kept():
    raw = {"hypotheses": [_hyp(claim="Weakness is a chance to buy the dip.")]}
    kept, rejected = wm.parse_hypotheses("company_news", raw, allowed_assets=ALLOWED)
    assert kept == []
    assert "recommendation language" in rejected[0]["reason"]
    # a rejection you cannot audit is a number, not a finding
    assert rejected[0]["matched_terms"] == ["buy"]
    assert "buy the dip" in rejected[0]["refused_text_excerpt"]


def test_bad_confidence_is_refused():
    raw = {"hypotheses": [_hyp(confidence=140)]}
    kept, rejected = wm.parse_hypotheses("company_news", raw, allowed_assets=ALLOWED)
    assert kept == []
    assert "credence" in rejected[0]["reason"]


def test_magnitude_percent_bounds_are_refusals_not_clamps():
    """0.0 makes everything a hit; 900 is a units error. Neither is coerced."""
    for bad in (0.0, 900.0):
        raw = {"hypotheses": [_hyp(
            cross_asset_corroboration=[{"kind": "magnitude", "asset": "^VIX",
                                        "expect": "up", "min_abs_move_pct": bad}],
            next_observable=None)]}
        kept, rejected = wm.parse_hypotheses("options_vol", raw,
                                             allowed_assets=ALLOWED)
        assert kept == []
        assert any("min_abs_move_pct" in s for s in rejected[0]["sub_reasons"])


def test_forward_horizon_outside_the_frozen_set_is_refused():
    raw = {"hypotheses": [_hyp(
        cross_asset_corroboration=[],
        next_observable={"ticker": "AAA", "observable": "return_sign",
                         "horizon_days": 3, "probability": 0.5,
                         "threshold": None})]}
    kept, rejected = wm.parse_hypotheses("revisions", raw, allowed_assets=ALLOWED)
    assert kept == []
    assert any("horizon 3" in s for s in rejected[0]["sub_reasons"])


def test_hypotheses_past_the_cap_are_counted():
    raw = {"hypotheses": [_hyp(hypothesis_id=f"h{i}") for i in range(9)]}
    kept, rejected = wm.parse_hypotheses("skeptic", raw, allowed_assets=ALLOWED)
    assert len(kept) == wm.WHY_MOVED_MAX_HYPOTHESES_PER_SPECIALIST
    assert any("past the cap" in r["reason"] for r in rejected)


# ── grading the day that already happened ───────────────────────────────────

def _graded(panel, checks: list[dict], derivable=None) -> list[wm.Corroboration]:
    raw = {"hypotheses": [_hyp(cross_asset_corroboration=checks)]}
    kept, _ = wm.parse_hypotheses("geopolitical", raw, allowed_assets=ALLOWED | {"GHOST"})
    wm.grade_corroboration(kept, panel, as_of="2026-08-10", prev="2026-08-07",
                           derivable=derivable)
    return kept[0].corroboration


def test_direction_hit_and_miss(panel):
    checks = _graded(panel, [
        {"kind": "direction", "asset": "^VIX", "expect": "up"},     # +4% -> hit
        {"kind": "direction", "asset": "CL=F", "expect": "up"},     # -3% -> miss
    ])
    assert [c.status for c in checks] == ["hit", "miss"]
    assert checks[0].observed["return_pct"] == pytest.approx(4.0)


def test_unavailable_is_its_own_bucket_and_never_a_hit(panel):
    checks = _graded(panel, [{"kind": "direction", "asset": "GHOST", "expect": "up"}])
    assert checks[0].status == "unavailable"
    assert "GHOST" in checks[0].observed["reason"]


def test_relative_sign_convention(panel):
    """QQQ -1.5% vs SPY -1.0%: QQQ underperformed."""
    checks = _graded(panel, [
        {"kind": "relative", "asset": "QQQ", "versus": BENCH,
         "expect": "underperforms"},
        {"kind": "relative", "asset": "QQQ", "versus": BENCH,
         "expect": "outperforms"},
    ])
    assert [c.status for c in checks] == ["hit", "miss"]
    assert checks[0].observed["spread_pct"] == pytest.approx(-0.5, abs=1e-9)


def test_relative_unavailable_when_the_versus_leg_is_missing(panel):
    checks = _graded(panel, [{"kind": "relative", "asset": "QQQ",
                              "versus": "GHOST", "expect": "outperforms"}])
    assert checks[0].status == "unavailable"


def test_magnitude_needs_both_size_and_sign(panel):
    checks = _graded(panel, [
        {"kind": "magnitude", "asset": "^VIX", "expect": "up",
         "min_abs_move_pct": 3.0},                                  # +4% -> hit
        {"kind": "magnitude", "asset": "^VIX", "expect": "up",
         "min_abs_move_pct": 6.0},                                  # too small
        {"kind": "magnitude", "asset": "^VIX", "expect": "down",
         "min_abs_move_pct": 3.0},                                  # wrong sign
        {"kind": "magnitude", "asset": "CL=F", "expect": "either",
         "min_abs_move_pct": 2.0},                                  # -3% -> hit
    ])
    assert [c.status for c in checks] == ["hit", "miss", "miss", "hit"]


def test_hit_rate_denominator_excludes_unavailable(panel):
    raw = {"hypotheses": [_hyp(cross_asset_corroboration=[
        {"kind": "direction", "asset": "^VIX", "expect": "up"},
        {"kind": "direction", "asset": "CL=F", "expect": "up"},
        {"kind": "direction", "asset": "GHOST", "expect": "up"},
    ])]}
    kept, _ = wm.parse_hypotheses("geopolitical", raw,
                                  allowed_assets=ALLOWED | {"GHOST"})
    wm.grade_corroboration(kept, panel, as_of="2026-08-10", prev="2026-08-07")
    s = kept[0].score
    assert (s["corroboration_hits"], s["corroboration_misses"],
            s["corroboration_unavailable"]) == (1, 1, 1)
    assert s["corroboration_hit_rate_external"] == pytest.approx(0.5)


def test_hit_rate_is_none_when_nothing_was_checkable(panel):
    raw = {"hypotheses": [_hyp(cross_asset_corroboration=[
        {"kind": "direction", "asset": "GHOST", "expect": "up"}])]}
    kept, _ = wm.parse_hypotheses("geopolitical", raw,
                                  allowed_assets=ALLOWED | {"GHOST"})
    wm.grade_corroboration(kept, panel, as_of="2026-08-10", prev="2026-08-07")
    assert kept[0].score["corroboration_hit_rate_external"] is None
    assert kept[0].score["corroboration_hit_rate_derivable"] is None


# ── the circularity guard ───────────────────────────────────────────────────

def test_derivable_assets_are_read_off_the_prompt_payload(panel, positions):
    """An asset whose move the prompt states is not a check on anything."""
    a = _attr(panel, positions)
    facts = wm.lens_input(a)
    d = wm.derivable_assets(facts)
    assert {"AAA", "BBB", BENCH} <= d          # positions + benchmark
    assert "XLV" in d and "XLK" in d           # sector returns were disclosed
    assert "^VIX" not in d and "CL=F" not in d  # never mentioned in the payload


def test_classification_follows_the_payload_not_a_hardcoded_list():
    """Drop the sector block from the payload and XLV stops being derivable."""
    facts = {"benchmark": "SPY", "benchmark_return_pct": -1.0,
             "positions": [{"ticker": "AAA", "return_pct": -5.0}]}
    assert wm.derivable_assets(facts) == {"AAA", "SPY"}
    facts["sector_returns_pct"] = {"Health Care": 1.6}
    assert wm.derivable_assets(facts) == {"AAA", "SPY", "XLV"}


def test_derivable_hits_are_scored_apart_from_external_ones(panel):
    checks = _graded(panel, [
        {"kind": "direction", "asset": "XLV", "expect": "down"},   # disclosed
        {"kind": "direction", "asset": "^VIX", "expect": "up"},    # external
        {"kind": "direction", "asset": "CL=F", "expect": "up"},    # external
    ], derivable={"XLV", "SPY", "AAA", "BBB"})
    assert [c.evidence_class for c in checks] == [
        "derivable_from_prompt", "external", "external"]
    s = wm.score_corroboration(checks)
    # XLV fell 2%, so "XLV down" hits — but the prompt had already said so,
    # which is why that hit is scored in its own bucket and never quoted.
    assert s["corroboration_hit_rate_derivable"] == pytest.approx(1.0)
    assert s["corroboration_hit_rate_external"] == pytest.approx(0.5)
    assert s["corroboration_hit_rate_combined"] == pytest.approx(2 / 3)


def test_relative_is_derivable_only_when_both_legs_were_disclosed(panel):
    checks = _graded(panel, [
        {"kind": "relative", "asset": "QQQ", "versus": BENCH,
         "expect": "underperforms"}], derivable={BENCH})
    assert checks[0].evidence_class == "external"


# ── the ledger ──────────────────────────────────────────────────────────────

def test_forward_claim_mints_a_prediction_record(panel, positions):
    a = _attr(panel, positions)
    raw = {"hypotheses": [_hyp()]}
    kept, _ = wm.parse_hypotheses("macro_rates", raw, allowed_assets=ALLOWED)
    recs, refusals = wm.mint_predictions(
        kept, attribution=a, prompts={"macro_rates": "p"}, model="deepseek-chat",
        model_version="deepseek-chat-x")
    assert refusals == [] and len(recs) == 1
    r = recs[0]
    assert r.horizon_days in HORIZONS
    assert r.specialist == "why_moved:macro_rates"
    assert r.ticker == "AAA" and 0.0 <= r.probability <= 1.0
    assert r.resolves_after > r.made_at[:10]
    assert kept[0].forward.prediction_id == r.prediction_id


def test_percent_vs_fraction_threshold_is_surfaced_not_swallowed(panel, positions):
    """The bug that wrote six guaranteed-wrong records: |move| > 20.0 = 2000%."""
    a = _attr(panel, positions)
    raw = {"hypotheses": [_hyp(next_observable={
        "ticker": "AAA", "observable": "abs_move_exceeds", "horizon_days": 5,
        "probability": 0.75, "threshold": 20.0})]}
    kept, _ = wm.parse_hypotheses("skeptic", raw, allowed_assets=ALLOWED)
    recs, refusals = wm.mint_predictions(
        kept, attribution=a, prompts={}, model="m", model_version="v")
    assert recs == []
    assert len(refusals) == 1
    assert "decimal fraction" in refusals[0]["reason"]
    assert kept[0].forward.refusal.startswith("ValueError")


def test_beats_benchmark_record_carries_the_benchmark(panel, positions):
    a = _attr(panel, positions)
    raw = {"hypotheses": [_hyp(next_observable={
        "ticker": "AAA", "observable": "beats_benchmark", "horizon_days": 20,
        "probability": 0.4, "threshold": None})]}
    kept, _ = wm.parse_hypotheses("sector_factor", raw, allowed_assets=ALLOWED)
    recs, refusals = wm.mint_predictions(kept, attribution=a, prompts={},
                                         model="m", model_version="v")
    assert refusals == [] and recs[0].benchmark == BENCH


# ── CANON §20 ───────────────────────────────────────────────────────────────

def test_identical_ideas_collapse_to_one(panel):
    same = {"hypotheses": [
        _hyp(hypothesis_id="a"),
        _hyp(hypothesis_id="b",
             claim="Long-duration risk repriced on a hawkish rates impulse!"),
    ]}
    kept, _ = wm.parse_hypotheses("macro_rates", same, allowed_assets=ALLOWED)
    out = wm.effective_distinct_ideas(kept)
    assert out["n_hypotheses"] == 2 and out["effective_distinct_ideas"] == 1


def test_different_ideas_stay_distinct():
    raw = {"hypotheses": [
        _hyp(hypothesis_id="a"),
        _hyp(hypothesis_id="b",
             claim="A clinical readout removed a binary overhang from one name.",
             cross_asset_corroboration=[{"kind": "direction", "asset": "XLV",
                                         "expect": "up"}]),
    ]}
    kept, _ = wm.parse_hypotheses("company_news", raw, allowed_assets=ALLOWED)
    assert wm.effective_distinct_ideas(kept)["effective_distinct_ideas"] == 2


# ── end to end, with a fake model ───────────────────────────────────────────

def _fake_llm(payload: dict | str, *, model_version: str = "fake-1"):
    text = payload if isinstance(payload, str) else json.dumps(payload)

    def call(system: str, user: str) -> wm.LLMReply:
        assert "cross_asset_corroboration" in system
        return wm.LLMReply(text=text, model_version=model_version)
    return call


def test_run_end_to_end_grades_and_mints(panel, positions):
    out = wm.run_why_moved(
        positions, "2026-08-10", panel=panel, lenses=["geopolitical", "skeptic"],
        llm_call=_fake_llm({"hypotheses": [_hyp(cross_asset_corroboration=[
            {"kind": "direction", "asset": "CL=F", "expect": "up"},
            {"kind": "magnitude", "asset": "^VIX", "expect": "up",
             "min_abs_move_pct": 3.0}])]}))
    assert out["status"] == "ok"
    assert out["attribution"]["pnl_usd"] == pytest.approx(-400.0)
    assert len(out["hypotheses"]) == 2
    # both lenses were handed the same fake answer: one idea, not two
    assert out["batch"]["effective_distinct_ideas"] == 1
    c = out["batch"]["corroboration"]
    assert (c["corroboration_hits"], c["corroboration_misses"],
            c["corroboration_unavailable"]) == (2, 2, 0)
    # CL=F and ^VIX are in nobody's prompt payload, so all four are external
    assert c["corroboration_hit_rate_external"] == pytest.approx(0.5)
    assert c["corroboration_hit_rate_derivable"] is None
    assert c["headline"] == "corroboration_hit_rate_external"
    assert out["n_predictions_minted"] == 2
    assert (out["lenses"]["skeptic"]["corroboration_hit_rate_external"]
            == pytest.approx(0.5))
    json.dumps(out)          # the artifact and the API response are one object


def test_no_deepseek_key_degrades_but_still_attributes(panel, positions, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    out = wm.run_why_moved(positions, "2026-08-10", panel=panel,
                           lenses=["macro_rates", "geopolitical"])
    assert out["status"] == "degraded_no_hypotheses"
    assert out["hypotheses"] == [] and out["predictions"] == []
    assert out["attribution"]["pnl_usd"] == pytest.approx(-400.0)
    for lens in ("macro_rates", "geopolitical"):
        assert out["lenses"][lens]["status"] == "degraded"
        assert "DEEPSEEK_API_KEY" in out["lenses"][lens]["degraded_reason"]


def test_unparseable_json_is_a_counted_rejection_not_a_crash(panel, positions):
    out = wm.run_why_moved(positions, "2026-08-10", panel=panel,
                           lenses=["options_vol"],
                           llm_call=_fake_llm("I think it was the vol sellers."))
    assert out["status"] == "degraded_no_hypotheses"
    assert out["lenses"]["options_vol"]["n_rejected"] == 1
    assert out["batch"]["n_rejected"] == 1
    assert out["hypotheses"] == []


def test_attribution_only_never_calls_the_model(panel, positions):
    def boom(system, user):                     # pragma: no cover - must not run
        raise AssertionError("with_hypotheses=False must not call the model")
    out = wm.run_why_moved(positions, "2026-08-10", panel=panel, llm_call=boom,
                           with_hypotheses=False)
    assert out["status"] == "attribution_only"
    assert out["hypotheses"] == [] and out["lenses"] == []


def test_ledger_write_is_opt_in(panel, positions, tmp_path):
    ledger = tmp_path / "predictions.jsonl"
    out = wm.run_why_moved(positions, "2026-08-10", panel=panel,
                           lenses=["macro_rates"], llm_call=_fake_llm(
                               {"hypotheses": [_hyp()]}),
                           write_ledger=True, ledger_path=ledger)
    rows = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
    assert len(rows) == out["n_predictions_minted"] == 1
    assert rows[0]["specialist"] == "why_moved:macro_rates"

    quiet = wm.run_why_moved(positions, "2026-08-10", panel=panel,
                             lenses=["macro_rates"],
                             llm_call=_fake_llm({"hypotheses": [_hyp()]}))
    assert "ledger_written" not in quiet


def test_output_never_claims_a_cause(panel, positions):
    out = wm.run_why_moved(positions, "2026-08-10", panel=panel, lenses=[],
                           llm_call=_fake_llm({"hypotheses": []}))
    txt = json.dumps(out["epistemics"]).lower()
    assert "cannot identify a cause" in txt
    assert "never" in txt


def test_regrade_rescores_without_calling_the_model(panel, positions):
    """A scoring fix must not mint a second batch of forecasts about one day."""
    art = wm.run_why_moved(
        positions, "2026-08-10", panel=panel, lenses=["sector_factor"],
        llm_call=_fake_llm({"hypotheses": [_hyp(cross_asset_corroboration=[
            {"kind": "direction", "asset": "AAA", "expect": "down"},   # disclosed
            {"kind": "direction", "asset": "CL=F", "expect": "up"}])]}))  # external
    before = art["batch"]["corroboration"]
    assert before["corroboration_hits_derivable"] == 1     # AAA fell, as printed
    assert before["corroboration_hit_rate_external"] == 0.0  # CL=F fell

    def boom(system, user):                     # pragma: no cover - must not run
        raise AssertionError("regrade must not call the model")
    art["hypotheses"][0]["score"] = {}
    out = wm.regrade(art, panel)
    after = out["batch"]["corroboration"]
    assert after["corroboration_hits_derivable"] == 1
    assert after["corroboration_hit_rate_external"] == 0.0
    assert out["regrades"][0]["no_records_minted"] is True
    assert out["n_predictions_minted"] == art["n_predictions_minted"]


# ── the book loader ─────────────────────────────────────────────────────────

def test_book_positions_refuses_a_position_without_shares(tmp_path):
    p = tmp_path / "book.yaml"
    p.write_text("account: t\nconfirmed: false\ncash: null\n"
                 "sizing_mode: growth\nwealth_targets: {}\npositions:\n"
                 "  - ticker: AAA\n    shares: 10\n  - ticker: BBB\n",
                 encoding="utf-8")
    with pytest.raises(wm.PricingError) as e:
        wm.book_positions(p)
    assert "BBB" in str(e.value)


def test_book_positions_reads_shares(tmp_path):
    p = tmp_path / "book.yaml"
    p.write_text("account: t\nconfirmed: false\ncash: null\n"
                 "sizing_mode: growth\nwealth_targets: {}\npositions:\n"
                 "  - ticker: aaa\n    shares: 10\n", encoding="utf-8")
    assert wm.book_positions(p) == [("AAA", 10.0)]


# ── the router ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.routers import why_moved as router_mod
    monkeypatch.setattr(router_mod, "_positions", lambda: [("AAA", 1.0)])
    app = FastAPI()
    app.include_router(router_mod.router)
    return TestClient(app), router_mod


def test_router_returns_attribution_without_the_model(client, monkeypatch):
    c, mod = client
    seen = {}

    def fake_run(positions, when, **kw):
        seen.update(kw)
        return {"status": "attribution_only"}
    monkeypatch.setattr(mod.wm, "run_why_moved", fake_run)
    r = c.get("/api/why-moved/attribution?as_of=2026-08-10")
    assert r.status_code == 200 and r.json()["status"] == "attribution_only"
    assert seen["with_hypotheses"] is False


def test_router_reports_an_unpriceable_book_as_422(client, monkeypatch):
    c, mod = client

    def boom(*a, **k):
        raise mod.wm.PricingError("no closes for GHOST")
    monkeypatch.setattr(mod.wm, "run_why_moved", boom)
    r = c.get("/api/why-moved/attribution")
    assert r.status_code == 422 and "GHOST" in r.json()["detail"]


def test_router_refuses_an_unknown_lens(client):
    c, _ = client
    r = c.get("/api/why-moved/explain?lenses=astrology")
    assert r.status_code == 422 and "astrology" in r.json()["detail"]


# ── telemetry on the lens call path ─────────────────────────────────────────
# The telemetry ledger's own audit named `default_llm_call` as the ONE
# uninstrumented LLM path in the repo, which made every WHY-MOVED lens call
# invisible to the accounting built to answer "is the inference buying
# anything". These pin the wiring, because an uninstrumented path that LOOKS
# wired is exactly the failure the ledger exists to expose.

class _FakeUsage:
    prompt_tokens = 1200
    completion_tokens = 340

    class prompt_tokens_details:            # noqa: N801 — mirrors the vendor
        cached_tokens = 256


class _FakeMsg:
    content = '{"hypotheses": []}'


class _FakeChoice:
    message = _FakeMsg()


class _FakeResp:
    model = "deepseek-chat-x"
    usage = _FakeUsage()
    choices = [_FakeChoice()]


def _patch_openai(monkeypatch, resp):
    """Stand in for the OpenAI client so no socket is opened."""
    import sys, types
    mod = types.ModuleType("openai")

    class _Client:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=lambda **k: resp))

    mod.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", mod)


def test_a_lens_call_is_recorded_with_its_real_token_counts(monkeypatch, tmp_path):
    from backend.services import llm_telemetry, why_moved as wm

    ledger = tmp_path / "calls.jsonl"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _patch_openai(monkeypatch, _FakeResp())

    recorded = {}
    real = llm_telemetry.record_call
    monkeypatch.setattr(llm_telemetry, "record_call",
                        lambda **kw: recorded.update(kw) or real(**kw, path=ledger))

    reply = wm.default_llm_call("sys", "user")

    assert reply.text == '{"hypotheses": []}'
    assert reply.model_version == "deepseek-chat-x"
    assert recorded["purpose"] == "why_moved_hypothesis"
    assert recorded["provider"] == "deepseek"
    # The point of the row: the real numbers, not zeros standing in for them.
    assert recorded["tokens_in"] == 1200
    assert recorded["tokens_out"] == 340
    assert recorded["cached_tokens"] == 256
    assert recorded["latency_ms"] > 0
    assert llm_telemetry.read_calls(ledger), "the row must reach the ledger"


def test_a_telemetry_failure_never_costs_us_the_hypothesis(monkeypatch):
    """Instrumentation may degrade to a log line; a forecast may not be lost."""
    from backend.services import llm_telemetry, why_moved as wm

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _patch_openai(monkeypatch, _FakeResp())

    def explode(**kw):
        raise RuntimeError("ledger volume is gone")
    monkeypatch.setattr(llm_telemetry, "record_call", explode)

    reply = wm.default_llm_call("sys", "user")
    assert reply.text == '{"hypotheses": []}'


def test_a_vendor_reply_without_usage_records_zeros_not_a_crash(monkeypatch, tmp_path):
    """`usage` is the vendor's object. A missing field degrades to a zero-token
    row that is still COUNTED — never an exception, and never a silent skip
    that would drop the call out of the spend denominator entirely."""
    from backend.services import llm_telemetry, why_moved as wm

    class _NoUsage(_FakeResp):
        usage = None

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _patch_openai(monkeypatch, _NoUsage())
    seen = {}
    monkeypatch.setattr(llm_telemetry, "record_call", lambda **kw: seen.update(kw))

    reply = wm.default_llm_call("sys", "user")
    assert reply.text == '{"hypotheses": []}'
    assert seen["tokens_in"] == 0 and seen["tokens_out"] == 0
    assert seen["purpose"] == "why_moved_hypothesis"
