"""Investment Committee — graceful degradation (NIGHT-13 ruling, §2).

The composer never returns an empty book: with zero eligible candidates, a
missing funnel, or every archetype refused, the answer is the benchmark core
with the reason printed. Tilts are evidence-scaled and capped; every position
carries a source label and a reason; ruin is always printed beside dream.

All offline: the funnel is a checked-in JSON artifact, the registry is a
checked-in YAML, and the wealth simulation is numpy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import config
from backend.services import investment_committee as IC
from backend.services.recommendation import Recommendation


def _rec(ticker, score=1.0, verdict="BUY", conf="MEDIUM",
         grade="SUPPORTED", rank=1, price=20.0):
    r = Recommendation(ticker=ticker, rank=rank, ranking_score=score,
                       confidence=conf, evidence_grade=grade, price=price)
    r.recommendation = verdict
    r.reason_for_rank = "led by profitability_small (SUPPORTED/PICKER)"
    return r


def _cands(recs):
    return {r.ticker: {"price": r.price, "vol_annual": 0.45,
                       "median_dollar_vol": 5e7} for r in recs}


# ── the composer never returns an empty book ────────────────────────────────

def test_compose_book_never_empty_with_zero_candidates():
    book = IC.compose_book([], capital=40_000.0)
    assert book["n_positions"] > 0
    assert all(p["source"] == "benchmark-core" for p in book["positions"])
    assert abs(sum(p["weight"] for p in book["positions"]) - 1.0) < 1e-6
    assert any("100% benchmark core" in d for d in book["degradation_reasons"])


def test_compose_book_never_empty_when_every_archetype_refused():
    refusals = {"OPTIMUS_MAX_GROWTH": "needs a CALIBRATED expected return",
                "OPTIMUS_BALANCED": "no candidate clears confidence >= LOW"}
    book = IC.compose_book([], capital=40_000.0, refusal_reasons=refusals)
    assert book["n_positions"] > 0
    joined = " | ".join(book["degradation_reasons"])
    assert "OPTIMUS_MAX_GROWTH REFUSED" in joined
    assert "CALIBRATED expected return" in joined


# ── tilt caps ───────────────────────────────────────────────────────────────

def test_single_name_tilt_cap_respected():
    recs = [_rec("AAA", score=99.0, verdict="BUY", conf="HIGH")]
    book = IC.compose_book(recs, capital=40_000.0, candidates=_cands(recs))
    tilts = [p for p in book["positions"] if p["source"] == "evidence-led"]
    assert tilts, "a HIGH-confidence BUY must produce a tilt"
    assert all(p["weight"] <= config.IC_SINGLE_NAME_TILT_CAP + 1e-9
               for p in tilts)


def test_total_tilt_budget_respected():
    recs = [_rec(f"T{i:02d}", verdict="BUY", conf="HIGH", rank=i + 1)
            for i in range(config.IC_MAX_TILT_NAMES + 10)]
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=_cands(recs))
    tilt_total = sum(p["weight"] for p in book["positions"]
                     if p["source"] == "evidence-led")
    assert tilt_total <= config.IC_TOTAL_TILT_BUDGET + 1e-9
    assert book["tilt_weight"] <= config.IC_TOTAL_TILT_BUDGET + 1e-9
    n_tilts = sum(1 for p in book["positions"] if p["source"] == "evidence-led")
    assert n_tilts <= config.IC_MAX_TILT_NAMES


def test_evidence_scaling_orders_tilts():
    """BUY/HIGH must out-tilt WATCH/LOW — size follows evidence strength."""
    recs = [_rec("STRONG", verdict="BUY", conf="HIGH", rank=1),
            _rec("WEAK", verdict="WATCH", conf="LOW", rank=2)]
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=_cands(recs))
    w = {p["ticker"]: p["weight"] for p in book["positions"]}
    assert w["STRONG"] > w["WEAK"]


def test_no_evidence_and_nonpositive_scores_never_tilt():
    recs = [_rec("BLANK", grade="NO_EVIDENCE"),
            _rec("ZERO", score=0.0),
            _rec("HOLDME", verdict="HOLD")]
    book = IC.compose_book(recs, capital=40_000.0, candidates=_cands(recs))
    assert all(p["source"] == "benchmark-core" for p in book["positions"])


# ── labels, weights, degradation ────────────────────────────────────────────

def test_every_position_has_source_and_reason():
    recs = [_rec("CVLG", verdict="BUY", conf="MEDIUM")]
    book = IC.compose_book(recs, capital=40_000.0, candidates=_cands(recs))
    for p in book["positions"]:
        assert p["source"] in ("evidence-led", "benchmark-core")
        assert isinstance(p["reason"], str) and p["reason"]


def test_book_weights_sum_to_one_with_tilts():
    recs = [_rec("AAA", verdict="BUY", conf="HIGH"),
            _rec("BBB", verdict="WATCH", conf="MEDIUM", rank=2)]
    book = IC.compose_book(recs, capital=40_000.0, candidates=_cands(recs))
    assert abs(sum(p["weight"] for p in book["positions"]) - 1.0) < 1e-6
    assert abs(book["core_weight"] + book["tilt_weight"] - 1.0) < 1e-6


def test_sub_one_share_tilt_returns_to_core():
    recs = [_rec("PRICY", verdict="WATCH", conf="LOW", price=5_000.0)]
    cands = {"PRICY": {"price": 5_000.0, "vol_annual": 0.4,
                       "median_dollar_vol": 5e7}}
    # 3% x 0.5 x 1/3 = 0.5% of $10k = $50 < one $5,000 share
    book = IC.compose_book(recs, capital=10_000.0, candidates=cands)
    assert all(p["source"] == "benchmark-core" for p in book["positions"])
    assert any("below one share" in d for d in book["degradation_reasons"])


def test_untradeable_tilt_returns_to_core():
    recs = [_rec("THIN", verdict="BUY", conf="HIGH")]
    cands = {"THIN": {"price": 5.0, "vol_annual": 0.6,
                      "median_dollar_vol": 1_000.0}}  # $1k/day: blocked at $1m
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=cands)
    assert all(p["source"] == "benchmark-core" for p in book["positions"])
    assert any("untradeable" in d for d in book["degradation_reasons"])


def test_share_counts_present_for_priced_tilts():
    recs = [_rec("AAA", verdict="BUY", conf="HIGH", price=25.0)]
    book = IC.compose_book(recs, capital=40_000.0, candidates=_cands(recs))
    tilt = next(p for p in book["positions"] if p["source"] == "evidence-led")
    # 3% of $40k = $1,200 at $25 → 48 shares (rec is HIGH/BUY = full cap)
    assert tilt["shares"] == int(tilt["dollars"] // tilt["price"])
    assert tilt["capacity"]["tradeable"] is True


# ── ruin beside dream ───────────────────────────────────────────────────────

def test_wealth_block_has_ruin_and_dream_together():
    book = IC.compose_book([], capital=40_000.0)
    w = book["wealth"]
    assert w["available"] is True
    assert w["p_reach_target"] is not None
    assert w["p_below_ruin"] is not None
    assert w["targets"]["target_value"] == pytest.approx(
        40_000.0 * config.IC_WEALTH_TARGET_MULT)
    assert w["targets"]["ruin_value"] == pytest.approx(
        40_000.0 * config.IC_WEALTH_RUIN_MULT)


# ── the full page ───────────────────────────────────────────────────────────

def test_committee_all_three_capitals_complete():
    page = IC.committee(use_cache=False)
    assert set(page["books"]) == {f"{int(c)}" for c in config.IC_CAPITAL_LEVELS}
    for book in page["books"].values():
        assert book["n_positions"] > 0
        assert book["wealth"]["p_below_ruin"] is not None
        assert book["wealth"]["p_reach_target"] is not None
        for p in book["positions"]:
            assert p["source"] in ("evidence-led", "benchmark-core")
            assert p["reason"]
    assert page["honesty"]["core_and_tilts"] == (
        "A market portfolio with cost discipline already beats most investors "
        "net; the tilts are small because the evidence is small.")


def test_committee_surfaces_archetype_refusals_as_degradation():
    page = IC.committee(capital=40_000.0, use_cache=False)
    # NIGHT-10 state of the evidence: at least Kelly is refused (no calibrated
    # ER exists in this programme), and the refusal string reaches the page.
    assert any("OPTIMUS_MAX_GROWTH REFUSED" in d
               for d in page["degradation_reasons"])
    assert any("CALIBRATED" in d for d in page["degradation_reasons"])


def test_committee_missing_funnel_degrades_never_500(tmp_path):
    page = IC.committee(funnel_path=tmp_path / "nope.json", use_cache=False)
    assert page["funnel_available"] is False
    assert IC.DEGRADATION_NO_FUNNEL in " | ".join(page["degradation_reasons"])
    for book in page["books"].values():
        assert book["n_positions"] > 0
        assert all(p["source"] == "benchmark-core" for p in book["positions"])


def test_strict_build_page_still_gates(tmp_path):
    """The CLI contract survives the promotion: gate CLEAN on the real funnel,
    FileNotFoundError (not a silent empty page) on a missing one."""
    page = IC.build_page(Path(config.IC_FUNNEL_PATH))
    assert page["registry_gate"]["status"] == "CLEAN"
    with pytest.raises(OSError):
        IC.build_page(tmp_path / "missing.json")


def test_router_rejects_unknown_capital():
    from fastapi import HTTPException
    from backend.routers.investment_committee import get_committee
    with pytest.raises(HTTPException) as e:
        get_committee(capital=123.0, refresh=False)
    assert e.value.status_code == 422


def test_router_serves_a_configured_capital():
    from backend.routers.investment_committee import get_committee
    out = get_committee(capital=40_000.0, refresh=True)
    assert list(out["books"]) == ["40000"]
    assert out["books"]["40000"]["capital"] == 40_000.0
