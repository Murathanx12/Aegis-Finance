"""THE 52-WEEK TARGET (roadmap O11), pinned by known answers and by AST.

Two kinds of test here, and the second kind is the point.

**Known answers.** Each leg has a textbook value a person can check by hand:
`forward EPS 5.00 × a sector median 20x` is 100.00 to the cent; a degenerate
Gordon-growth DCF (`FCF 10, r 10%, g 4%`) is 173.33; a +50% consensus minus the
pooled +9.78pp bias is +40.22%. An off-by-one in the terminal year or an
arithmetic/log drift mix-up is the failure class this codebase has hit before,
and a hand-checkable number is what catches it.

**Negative properties, read off the AST.** The module must not contain the
defect it was built to remove, and "it does not appear in the source" is not
enough — the docstrings EXPLAIN the defect, and a grep-shaped guard that cannot
tell an explanation from an instance is a broken guard (CLAUDE.md rule 10).
So: no `np.clip` on a consensus quantity, and no `(1+x)**(1/n)` horizon back-out
anywhere, checked over the parsed tree with docstrings skipped.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from backend.services import price_target as PT
from backend.services import stock_analyzer as SA

MODULE = Path(PT.__file__)
ANALYZER = Path(SA.__file__)


def _executable_nodes(path: Path):
    """Every AST node outside a docstring.

    A guard that fires on the comment explaining the banned pattern teaches the
    next reader to delete the comment. Three tests in this repo failed that way
    on their first run.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(n, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docs.add(id(body[0].value))
    return [n for n in ast.walk(tree) if id(n) not in docs], docs


# ======================================================================= legs

def test_the_multiple_leg_is_eps_times_the_multiple_to_the_cent():
    """A firm on $5.00 forward EPS in a sector trading at 20x is worth $100.
    At `PEERS_FOR_NO_SHRINKAGE` peers the shrinkage is exactly zero, so the
    market multiple cannot creep into the answer."""
    leg = PT.multiple_leg(forward_eps=5.0, peer_multiple=20.0,
                          n_peers=PT.PEERS_FOR_NO_SHRINKAGE)
    assert leg["available"] and leg["shrinkage_weight"] == 0.0
    assert leg["value"] == pytest.approx(100.00, abs=1e-9)
    assert leg["justified_multiple"] == pytest.approx(20.0, abs=1e-9)


def test_fewer_peers_shrink_toward_the_market_and_the_weight_is_printed():
    leg = PT.multiple_leg(forward_eps=5.0, peer_multiple=30.0, n_peers=0,
                          market_multiple=20.0)
    assert leg["shrinkage_weight"] == PT.MAX_MULTIPLE_SHRINKAGE
    # 0.4*30 + 0.6*20 = 24 -> 5 * 24 = 120
    assert leg["value"] == pytest.approx(120.0, abs=1e-9)
    assert leg["market_multiple_source"].startswith("PRIOR_UNMEASURED")


def test_a_non_positive_eps_uses_sales_rather_than_a_degenerate_pe():
    """A negative denominator gives a negative 'fair value', which is not a low
    valuation — it is arithmetic noise."""
    leg = PT.multiple_leg(forward_eps=-2.0, peer_multiple=20.0, n_peers=8,
                          revenue_per_share=10.0, peer_ps=3.0)
    assert leg["available"] and leg["basis"] == "price_to_sales_fallback"
    assert leg["value"] > 0


def test_the_leg_refuses_by_name_when_it_has_nothing():
    leg = PT.multiple_leg(forward_eps=None, peer_multiple=None, n_peers=None)
    assert leg["available"] is False
    assert "forward EPS" in leg["reason"] and "peer median" in leg["reason"]


def test_the_dcf_reproduces_gordon_growth_exactly_when_the_stages_collapse():
    """FCF $10, r 10%, g 4% -> 10 * 1.04 / 0.06 = 173.33. Two decimals, by hand."""
    leg = PT.dcf_lite_leg(fcf_per_share=10.0, growth_stage1=0.0, discount_rate=0.10,
                          terminal_growth=0.04, years_stage1=0, years_stage2=0)
    assert leg["available"]
    assert leg["terminal_value"] == pytest.approx(173.33, abs=0.01)
    assert leg["value"] == pytest.approx(173.33, abs=0.01)
    assert leg["terminal_value_share_pct"] == pytest.approx(100.0, abs=0.01)


def test_the_dcf_refuses_when_growth_is_not_below_the_discount_rate():
    """Gordon diverges. A number produced here would be a division artefact."""
    leg = PT.dcf_lite_leg(fcf_per_share=10.0, growth_stage1=0.0, discount_rate=0.03,
                          terminal_growth=0.05, years_stage1=0, years_stage2=0)
    # g is bounded to r-0.005 rather than allowed through, so this stays finite
    assert leg["available"] and leg["terminal_growth"] < 0.03


def test_the_dcf_discloses_the_terminal_value_share():
    leg = PT.dcf_lite_leg(fcf_per_share=5.0, growth_stage1=0.10, discount_rate=0.09)
    assert leg["available"]
    assert 0.0 < leg["terminal_value_share_pct"] <= 100.0
    assert leg["terminal_basis"] in ("gordon", "exit_multiple")


def test_capm_names_a_beta_of_one_when_beta_is_absent():
    r = PT.capm_discount_rate(risk_free_rate=0.04, beta=None, equity_risk_premium=0.07)
    assert r == pytest.approx(0.11, abs=1e-12)


def test_the_consensus_leg_subtracts_the_bias_and_never_clips():
    """+50% raw, the pooled +9.78pp bias -> +40.22%. And +200% survives."""
    leg = PT.consensus_leg(consensus_target=150.0, current_price=100.0,
                           bias=0.0978, bias_source="fixture")
    assert leg["debiased_upside_pct"] == pytest.approx(40.22, abs=0.01)
    big = PT.consensus_leg(consensus_target=300.0, current_price=100.0,
                           bias=0.0978, bias_source="fixture")
    assert big["debiased_upside_pct"] == pytest.approx(190.22, abs=0.01)
    assert big["value"] > 250.0, "a +200% consensus must reach the page"


def test_the_pooled_bias_comes_from_the_receipt_and_says_so():
    bias, source = PT.pooled_bias_pp()
    assert 0.05 < bias < 0.15
    assert "analyst_target_grades" in source or "receipt unreadable" in source


# =============================================================== calibration

def test_no_fitted_table_is_the_identity_and_announces_itself():
    out = PT.apply_calibration(0.62, None)
    assert out["calibrated_upside"] == 0.62
    assert out["calibration"] == "identity_unfitted"
    assert "not a cap" in out["note"]


def test_the_isotonic_map_interpolates_and_holds_its_ends():
    cohort = {"isotonic": [[0.0, 0.02], [0.5, 0.10], [1.0, 0.15]]}
    mid = PT.apply_calibration(0.25, cohort)
    assert mid["calibration"] == "isotonic"
    assert mid["calibrated_upside"] == pytest.approx(0.06, abs=1e-9)
    hi = PT.apply_calibration(5.0, cohort)
    assert hi["calibration"] == "isotonic_clamped_high"
    assert hi["calibrated_upside"] == pytest.approx(0.15, abs=1e-9)
    lo = PT.apply_calibration(-3.0, cohort)
    assert lo["calibration"] == "isotonic_clamped_low"


def test_no_fitted_quantiles_means_no_band_rather_than_an_invented_one():
    """An invented band reads as measured uncertainty, which is worse than none."""
    band = PT.interval(current_price=100.0, point_return=0.2, cohort=None)
    assert band["p10"] is None and band["p90"] is None
    assert band["basis"] == "no_empirical_support"
    assert band["p50"] == 120.0


def test_the_band_covers_about_eighty_percent_of_a_known_distribution():
    """The spec's interval-coverage test: on a synthetic bucket whose generating
    distribution is known, the empirical p10-p90 band must contain ~80% of the
    realised outcomes. Run on synthetic data, where the truth is known, BEFORE
    the band is trusted on IBES."""
    rng = np.random.default_rng(20260911)
    n = 20000
    target = 0.20
    realised = target + rng.normal(0.0, 0.30, size=n)
    err = target - realised                       # the quantity the fit stores
    cohort = {"error_quantiles": {"p10": float(np.percentile(-err, 10)),
                                  "p90": float(np.percentile(-err, 90)), "n": n}}
    band = PT.interval(current_price=100.0, point_return=target, cohort=cohort)
    inside = np.mean((realised >= band["p10"] / 100.0 - 1.0)
                     & (realised <= band["p90"] / 100.0 - 1.0))
    assert 0.77 < inside < 0.83, inside


def test_a_price_can_never_go_below_zero():
    """GPRO's first live run produced p10 = -0.74 on a $1.40 stock."""
    cohort = {"error_quantiles": {"p10": -1.5, "p90": 1.5, "n": 100}}
    band = PT.interval(current_price=1.40, point_return=-0.19, cohort=cohort)
    assert band["p10"] == 0.0 and band.get("p10_floored_at_zero") is True
    assert "cannot be negative" in band["basis"]


def test_a_band_wholly_above_spot_is_withheld_not_shown():
    """NVDA's first live run: p10 $234.93 on a $218.36 stock. A pooled error
    bucket gives a top-of-range name a band centred on the bucket's typical
    name, so the whole band can sit above spot -- a claim of near-certain gain
    the data never made. Until the quantiles are conditioned on the upside
    tercile, the band is withheld and says why; p50 stands (withholding is not
    a clip)."""
    cohort = {"error_quantiles": {"p10": -0.05, "p90": 0.60, "n": 500}}
    band = PT.interval(current_price=218.36, point_return=0.50, cohort=cohort)
    assert band["p10"] is None and band["p90"] is None
    assert band.get("band_withheld") is True
    assert "above" in band["basis"] and "spot" in band["basis"]
    assert band["p50"] == round(218.36 * 1.5, 4)
    # and a band that straddles spot is untouched
    ok = PT.interval(current_price=218.36, point_return=0.50,
                     cohort={"error_quantiles": {"p10": -0.70, "p90": 0.60, "n": 500}})
    assert ok["p10"] is not None and ok.get("band_withheld") is None


def test_an_unfitted_bucket_falls_back_to_a_coarser_one_and_names_the_level():
    """NVDA and MU resolved to `Technology|mega|vol_high`, which the fit does not
    contain, because the backtest buckets on MONTHLY vol and the live path on
    DAILY vol. A coarser band with its level printed is usable; an em dash where
    a band should be is not."""
    cal = {"buckets": {
        "Technology|mega|vol_mid": {"n_obs": 300, "mean_bias": 0.10, "mae_pct": 40.0,
                                    "hit_rate_12m_pct": 50.0,
                                    "error_quantiles": {"p10": -0.4, "p90": 0.4, "n": 300},
                                    "isotonic": [[0.0, 0.0], [1.0, 0.2]],
                                    "leg_mae_pct": {"consensus_debiased": 40.0}},
    }}
    cohort, key, level = PT.resolve_cohort(cal, "Technology", "mega", 0.90)
    assert key == "Technology|mega|vol_high"
    assert level == "sector_cap" and cohort is not None
    assert cohort["n_obs"] == 300
    # the merged cohort deliberately carries NO isotonic: averaging two monotone
    # curves fitted on different supports produces a curve fitted on neither
    assert cohort["isotonic"] == []
    exact, key2, lvl2 = PT.resolve_cohort(cal, "Technology", "mega", 0.30)
    assert lvl2 == "exact" and exact["isotonic"]


def test_nothing_fitted_at_all_is_reported_as_such():
    cohort, key, level = PT.resolve_cohort({"buckets": {}}, "Widgets", "mid", 0.3)
    assert cohort is None and level == "none"


# ==================================================================== weights

def test_an_unmeasured_leg_may_not_dilute_a_measured_one():
    """NVDA's consensus said +50% and our combined target said -16%, because an
    UNBACKTESTED DCF carried half the weight against a de-biased consensus whose
    error IS measured. A number with a known error averaged into one with an
    unknown error has an unknown error."""
    legs = {"dcf_lite": {"available": True, "value": 50.0},
            "consensus_debiased": {"available": True, "value": 150.0}}
    cohort = {"n_obs": 300, "leg_mae_pct": {"consensus_debiased": 40.0}}
    w, basis = PT.inverse_error_weights(legs, cohort)
    assert w == {"consensus_debiased": 1.0}
    assert "weight 0" in basis and "dcf_lite" in basis


def test_with_no_fitted_cohort_the_weights_are_priors_and_say_so():
    legs = {"dcf_lite": {"available": True, "value": 50.0},
            "consensus_debiased": {"available": True, "value": 150.0}}
    w, basis = PT.inverse_error_weights(legs, None)
    assert basis == "prior_unbacktested"
    assert w["dcf_lite"] == pytest.approx(0.5, abs=1e-6)


def test_no_leg_available_is_reported_not_defaulted():
    w, basis = PT.inverse_error_weights({"dcf_lite": {"available": False}}, None)
    assert w == {} and basis == "no_leg_available"


# ============================================== the whole thing, and authority

def _fixture_calibration() -> dict:
    return {"generated_utc": "2026-09-11T00:00:00+00:00",
            "buckets": {"Technology|mega|vol_mid": {
                "n_obs": 500, "mean_bias": 0.12, "mae_pct": 42.0,
                "hit_rate_12m_pct": 48.0,
                "error_quantiles": {"p10": -0.35, "p90": 0.35, "n": 500},
                "isotonic": [[-0.2, -0.05], [0.2, 0.06], [0.8, 0.12]],
                "leg_mae_pct": {"consensus_debiased": 42.0}}}}


def test_a_plus_sixty_percent_consensus_survives_to_the_payload():
    """The regression test for the exact defect removed: the old chain turned a
    +60% consensus into +30% before anything else happened."""
    out = PT.compute_target(ticker="TEST", current_price=100.0, sector="Technology",
                            cap_tier="mega", annual_vol=0.35,
                            consensus_target=160.0, n_analysts=40,
                            calibration=_fixture_calibration())
    assert out["available"]
    leg = out["legs"]["consensus_debiased"]
    assert leg["raw_consensus_upside_pct"] == pytest.approx(60.0, abs=1e-6)
    # de-biased by the COHORT's 12pp, not truncated to a tier ceiling
    assert leg["debiased_upside_pct"] == pytest.approx(48.0, abs=1e-6)
    assert "fitted cohort bias" in leg["bias_source"]
    t = out["target_12m"]
    assert t["uncalibrated_return_pct"] == pytest.approx(48.0, abs=1e-6)
    assert t["p10"] is not None and t["p90"] is not None
    assert out["calibration"]["hit_rate_12m_pct"] == 48.0


def test_the_payload_always_carries_its_authority():
    out = PT.compute_target(ticker="TEST", current_price=100.0,
                            consensus_target=120.0, calibration={"buckets": {}})
    eu = out["engine_usage"]
    assert eu["rank_bearing"] is False and eu["registry_role"] == "RISK_INPUT"
    assert "PERVERSE" in eu["reason"] and "ANALYST-IBES-1" in eu["reason"]
    assert eu["trial"].endswith("TRIAL-CALIBRATED-TARGET-UPSIDE-1.md")


def test_the_registry_bars_the_calibrated_upside_from_leading_a_ranking():
    from backend.services.signal_registry import load

    reg = load()
    assert reg.permits("calibrated_target_upside", "RISK_INPUT") is True
    assert reg.permits("calibrated_target_upside", "PICKER") is False
    s = reg.get("calibrated_target_upside")
    assert "analyst_target_upside_xs" in s.distinct_from
    # the control that beats us is in the registry, not only in a receipt
    assert "drift" in s.known_failure.lower()


def test_the_prereg_draft_exists_and_is_unsigned():
    p = Path(PT.REPO) / "docs" / "TRIALS" / "TRIAL-CALIBRATED-TARGET-UPSIDE-1.md"
    text = p.read_text(encoding="utf-8")
    assert "UNSIGNED" in text
    assert "SIGNED-BY" not in text.replace("Signed by:", "")
    for required in ("HYPOTHESIS", "PRIMARY METRIC", "DECISION RULE",
                     "FROZEN PARAMETERS", "WHAT THIS RULE MAY NOT DO"):
        assert required in text, required


def test_an_unpriceable_name_refuses_rather_than_returning_a_number():
    out = PT.compute_target(ticker="X", current_price=0.0, consensus_target=10.0)
    assert out["available"] is False and "unpriceable" in out["reason"]


def test_nothing_computable_is_a_named_refusal_with_the_legs_shown():
    out = PT.compute_target(ticker="X", current_price=100.0, calibration={"buckets": {}})
    assert out["available"] is False
    assert "no leg could be computed" in out["reason"]
    assert set(out["legs"]) == {"multiple_based", "dcf_lite", "consensus_debiased"}


# ================================================================ AST GUARDS

def test_the_target_module_clips_no_consensus_quantity():
    """`np.clip(analyst_1y_return, -0.30, max_cagr)` is the defect. Read the
    tree, not the text: the docstring EXPLAINS the defect and must not satisfy
    a guard that is supposed to catch it."""
    nodes, _ = _executable_nodes(MODULE)
    for n in nodes:
        if isinstance(n, ast.Call):
            name = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
            assert name != "clip", "price_target must contain no clip at all"


def test_no_horizon_back_out_anywhere_in_either_module():
    """`(1 + x) ** (1/n)` and `x / n` from a multi-year figure are the literal
    move Murat rejected. A power with a reciprocal exponent is banned in both
    modules; the AUDIT script keeps one, on purpose, to show what the old page
    said."""
    for path in (MODULE, ANALYZER):
        nodes, _ = _executable_nodes(path)
        for n in nodes:
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow):
                r = n.right
                is_reciprocal = (isinstance(r, ast.BinOp) and isinstance(r.op, ast.Div)
                                 and isinstance(getattr(r.left, "value", None), (int, float))
                                 and float(getattr(r.left, "value", 0)) == 1.0)
                assert not is_reciprocal, (
                    f"{path.name} annualises by a reciprocal power -- the horizon "
                    f"back-out this work removed")


def test_the_analyzer_no_longer_reads_the_cagr_caps():
    """`config['stocks']['cagr_caps']` stays in config.py so old receipts stay
    readable, and nothing reads it."""
    src = ANALYZER.read_text(encoding="utf-8")
    nodes, _ = _executable_nodes(ANALYZER)
    literals = [n.value for n in nodes
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert "cagr_caps" not in literals, "the analyzer still asks config for the caps"
    assert not any(isinstance(n, ast.Name) and n.id == "STOCK_CAGR_CAPS" for n in nodes)
    assert "STOCK_CAGR_CAPS" in src, (
        "the name should survive in the comment that explains why it went -- "
        "deleting the rationale is how the next reader puts the caps back")


def test_the_analyzer_clips_nothing_that_is_a_return():
    """The three surviving clips must be on VOLATILITY and on a crash frequency
    -- bounds on model inputs, not on a forecast. Every `np.clip` in the module
    is enumerated here, so a fourth one fails this test rather than sliding in."""
    nodes, _ = _executable_nodes(ANALYZER)
    clipped = []
    for n in nodes:
        if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "clip" and n.args:
            clipped.append(ast.unparse(n.args[0]))
    # Enumerated, so a FOURTH clip fails here rather than sliding in.
    assert sorted(clipped) == ["base_crash_freq * beta", "hist_sigma", "hist_sigma"], clipped
    for expr in clipped:
        assert ("sigma" in expr or "crash" in expr or "vol" in expr), (
            f"a clip on {expr!r} -- returns are calibrated in this codebase, not capped")


# ===========================================================================
# THE BAND, CONDITIONED ON THE UPSIDE TERCILE (2026-09-12, chunk 3c T2)
# ===========================================================================
#
# Pooled error quantiles hand a name at the TOP of its bucket's upside range a
# band centred on the bucket's typical name, so the whole band can sit above
# spot -- NVDA, p10 $234.93 on a $218.36 stock -- and be withheld. Asquith,
# Mikhail and Au: error grows with implied upside. So slice the SAME errors by
# the raw upside they were made at.


def _tercile_cohort(*, low: tuple[float, float], mid: tuple[float, float],
                    high: tuple[float, float], cuts=(0.10, 0.35), n: int = 500) -> dict:
    return {
        "n_obs": 3 * n,
        "error_quantiles": {"p10": -0.05, "p90": 0.60, "n": 3 * n},
        "upside_tercile_cuts": list(cuts),
        "error_quantiles_by_upside_tercile": {
            "low": {"p10": low[0], "p90": low[1], "n": n},
            "mid": {"p10": mid[0], "p90": mid[1], "n": n},
            "high": {"p10": high[0], "p90": high[1], "n": n},
        },
    }


def test_a_bucket_whose_top_tercile_errs_more_gives_a_high_upside_name_a_wider_band():
    cohort = _tercile_cohort(low=(-0.10, 0.10), mid=(-0.25, 0.25), high=(-0.80, 0.80))
    quiet = PT.interval(current_price=100.0, point_return=0.05, cohort=cohort, raw_upside=0.05)
    loud = PT.interval(current_price=100.0, point_return=0.05, cohort=cohort, raw_upside=0.90)
    assert quiet["upside_tercile"] == "low" and loud["upside_tercile"] == "high"
    assert (loud["p90"] - loud["p10"]) > 3 * (quiet["p90"] - quiet["p10"])
    assert "conditioned on the high raw-upside tercile" in loud["basis"]
    assert "conditioned on the low raw-upside tercile" in quiet["basis"]
    assert loud["upside_tercile_cuts"] == [0.10, 0.35]


def test_the_middle_tercile_is_picked_at_the_cut_points():
    cohort = _tercile_cohort(low=(-0.1, 0.1), mid=(-0.2, 0.2), high=(-0.3, 0.3))
    at_lo = PT.interval(current_price=100.0, point_return=0.0, cohort=cohort, raw_upside=0.10)
    just_over = PT.interval(current_price=100.0, point_return=0.0, cohort=cohort, raw_upside=0.1001)
    at_hi = PT.interval(current_price=100.0, point_return=0.0, cohort=cohort, raw_upside=0.35)
    assert at_lo["upside_tercile"] == "low"          # the cut belongs to the lower side
    assert just_over["upside_tercile"] == "mid"
    assert at_hi["upside_tercile"] == "mid"


def test_an_unconditioned_bucket_still_uses_the_pooled_quantiles_and_says_POOLED():
    """The fallback is the behaviour every band had before today. It must be
    visible in the basis, not silent."""
    cohort = {"error_quantiles": {"p10": -0.70, "p90": 0.60, "n": 500}}
    band = PT.interval(current_price=100.0, point_return=0.10, cohort=cohort, raw_upside=2.0)
    assert band["upside_tercile"] is None
    assert "POOLED over the bucket's whole upside range" in band["basis"]
    assert band["p10"] is not None


def test_a_raw_upside_that_is_not_a_number_falls_back_rather_than_guessing():
    cohort = _tercile_cohort(low=(-0.1, 0.1), mid=(-0.2, 0.2), high=(-0.3, 0.3))
    for bad in (None, float("nan"), float("inf")):
        assert PT.upside_tercile(bad, cohort) == (None, {})
    assert PT.upside_tercile(0.9, {"error_quantiles": {"p10": -1, "p90": 1}}) == (None, {})


def test_the_withhold_still_fires_on_a_conditioned_band_that_sits_above_spot():
    """The conditioning is a better prior, not a guarantee. The last line of
    defence stays a last line of defence."""
    cohort = _tercile_cohort(low=(-0.9, 0.2), mid=(-0.9, 0.3), high=(0.05, 0.60))
    band = PT.interval(current_price=218.36, point_return=0.50, cohort=cohort, raw_upside=0.90)
    assert band["upside_tercile"] == "high"
    assert band["p10"] is None and band["p90"] is None and band["band_withheld"] is True
    assert "high upside tercile" in band["basis"]
    assert band["p50"] == round(218.36 * 1.5, 4)


def _bucket(n, p10, p90, cuts, t_lo, t_mid, t_high):
    return {"n_obs": n, "mean_bias": 0.1, "mae_pct": 30.0, "hit_rate_12m_pct": 40.0,
            "error_quantiles": {"p10": p10, "p90": p90},
            "upside_tercile_cuts": list(cuts),
            "error_quantiles_by_upside_tercile": {
                "low": {"p10": t_lo[0], "p90": t_lo[1], "n": n // 3},
                "mid": {"p10": t_mid[0], "p90": t_mid[1], "n": n // 3},
                "high": {"p10": t_high[0], "p90": t_high[1], "n": n // 3}}}


def test_a_pooled_cohort_takes_the_widest_tercile_and_averages_the_cuts():
    """NVDA and MU resolve to `Technology|mega|vol_high`, which the monthly-vol
    fit never produces, so they arrive through `sector_cap` POOLING. Leaving
    that path unconditioned left the two names the exercise was about with the
    withheld band. The merge is the same rule the pooled quantiles already use
    -- a coarser bucket is a less certain one, so take the WIDEST -- and the
    cuts are observation-weighted, which the payload admits is an
    approximation."""
    merged = PT._merge_buckets([
        _bucket(100, -0.4, 0.4, (0.10, 0.30), (-0.1, 0.1), (-0.2, 0.2), (-0.9, 0.3)),
        _bucket(300, -0.6, 0.5, (0.50, 0.70), (-0.3, 0.2), (-0.4, 0.5), (-0.5, 0.8)),
    ])
    assert merged["upside_tercile_cuts"] == [0.4, 0.6]      # (100*.1+300*.5)/400, likewise
    high = merged["error_quantiles_by_upside_tercile"]["high"]
    assert high["p10"] == -0.9 and high["p90"] == 0.8       # widest of the pool, both ends
    assert high["n"] == 133                                  # 33 + 100
    assert "widest" in merged["tercile_basis"]
    band = PT.interval(current_price=100.0, point_return=0.5, cohort=merged, raw_upside=0.9)
    assert band["upside_tercile"] == "high"
    assert "widest p10/p90 of 2 pooled buckets" in band["basis"]


def test_a_pool_where_any_bucket_is_unconditioned_carries_no_block():
    """A `widest` taken over a subset is a width that depends on which buckets
    happened to be fitted, which is not a measurement."""
    merged = PT._merge_buckets([
        _bucket(100, -0.4, 0.4, (0.10, 0.30), (-0.1, 0.1), (-0.2, 0.2), (-0.9, 0.3)),
        {"n_obs": 300, "mean_bias": 0.2, "mae_pct": 35.0, "hit_rate_12m_pct": 45.0,
         "error_quantiles": {"p10": -0.6, "p90": 0.5}},
    ])
    assert merged["error_quantiles_by_upside_tercile"] == {}
    assert merged["upside_tercile_cuts"] == []
    band = PT.interval(current_price=100.0, point_return=0.1, cohort=merged, raw_upside=5.0)
    assert band["upside_tercile"] is None and "POOLED" in band["basis"]


# ------------------------------------------------------- the fitter's own side

def test_the_fitter_refuses_to_condition_a_bucket_whose_terciles_are_thin():
    from scripts.price_target_backtest import (MIN_TERCILE_OBS, conditioned_quantiles,
                                               tercile_cuts)

    rng = np.random.default_rng(20260912)
    n = 3 * (MIN_TERCILE_OBS - 5)
    imp = np.linspace(-0.2, 1.2, n)
    err = rng.normal(0.0, 0.3, size=n)
    assert conditioned_quantiles(None, imp, err, tercile_cuts(imp)) == {}
    assert conditioned_quantiles(None, imp, err, []) == {}


def test_the_fitter_recovers_a_widening_it_was_given():
    """Plant heteroskedasticity along the upside axis and read it back."""
    from scripts.price_target_backtest import conditioned_quantiles, tercile_cuts

    rng = np.random.default_rng(20260912)
    n = 9000
    imp = rng.uniform(-0.2, 1.6, size=n)
    # sd grows with implied upside, which is the Asquith-Mikhail-Au claim
    err = rng.normal(0.0, 0.05 + 0.5 * np.maximum(imp, 0.0), size=n)
    cuts = tercile_cuts(imp)
    got = conditioned_quantiles(None, imp, err, cuts)
    assert set(got) == {"low", "mid", "high"}
    widths = {k: got[k]["p90"] - got[k]["p10"] for k in ("low", "mid", "high")}
    assert widths["low"] < widths["mid"] < widths["high"], widths
    assert widths["high"] > 2 * widths["low"], widths
    assert got["low"]["raw_upside_lo"] is None and got["high"]["raw_upside_hi"] is None
    assert got["mid"]["raw_upside_lo"] == cuts[0] and got["mid"]["raw_upside_hi"] == cuts[1]


def test_the_live_calibration_on_disk_carries_conditioned_terciles():
    """A fit that ships without the block leaves every band pooled, silently."""
    cal = PT.latest_calibration()
    if not cal:
        pytest.skip("no calibration artefact on this checkout")
    buckets = cal.get("buckets") or {}
    conditioned = [k for k, v in buckets.items() if v.get("error_quantiles_by_upside_tercile")]
    assert conditioned, ("the calibration on disk predates the tercile refit; run "
                         "`python -m scripts.price_target_backtest`")
    v = buckets[conditioned[0]]
    assert len(v["upside_tercile_cuts"]) == 2
    assert set(v["error_quantiles_by_upside_tercile"]) == {"low", "mid", "high"}
