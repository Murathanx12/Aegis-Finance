"""
Config-vs-behavior audit ("no overclaiming") — config v2 edition.

Since Step #2 (config v2, 2026-06-11) the three reference lanes genuinely run
leakage-safe HRP on the equity sleeve (gate-tested in test_step2_optimizer),
so honesty now means the OPPOSITE direction of the v1 test:
  - the active `optimizer: hrp` claim must be backed by a wired, gate-tested
    path (the leakage + invariant tests are the backing),
  - the control lane must stay frozen at equal_weight — its entire purpose
    is to measure the optimizer, and "controls that drift" is the classic
    way that measurement silently dies,
  - the deferred BL intent must stay recorded, not silently dropped.
"""


from backend.config import paper_portfolios
from backend.services.portfolio_intelligence.rules import (
    REFERENCE_LANES,
    _get_sleeve_tickers,
    classify_asset,
    compute_target_weights,
)

OPTIMIZED_LANES = ["conservative", "balanced", "aggressive"]


def test_active_optimizer_matches_wiring():
    """Optimized lanes claim hrp (wired + gate-tested); control claims and
    runs equal_weight."""
    for lane in OPTIMIZED_LANES:
        cfg = paper_portfolios[lane]
        assert cfg.get("optimizer") == "hrp", (
            f"{lane}: optimizer='{cfg.get('optimizer')}' — config v2 switched "
            f"the reference lanes to HRP; if this was reverted it must be a "
            f"NEW config version, never an in-place edit (hash reuse corrupts "
            f"segment boundaries)."
        )
    assert paper_portfolios["balanced-ew-control"]["optimizer"] == "equal_weight", (
        "the ew-control lane MUST stay frozen at equal-weight — it is the "
        "registered control for the HRP trial"
    )


def test_bl_intent_preserved():
    """BL was deliberately deferred (no views source → BL collapses to its
    prior). The intent must stay recorded for the future config version."""
    assert paper_portfolios["balanced"].get("planned_optimizer") == "black-litterman"


def test_fallback_without_panel_is_equal_weight():
    """Behavior gate: with no as-of panel the lanes degrade to equal-weight
    (never garbage), and the control lane is equal-weight by construction."""
    universe = paper_portfolios.get("universe", {})
    eq = set(_get_sleeve_tickers(universe)["equity"])
    for lane in REFERENCE_LANES:
        meta: dict = {}
        weights = compute_target_weights(paper_portfolios[lane], universe, meta=meta)
        eq_w = [w for t, w in weights.items()
                if t in eq and classify_asset(t) == "equity" and w > 0]
        assert len(eq_w) > 1
        assert max(eq_w) - min(eq_w) < 1e-9, (
            f"{lane}: no-panel path must be exactly equal-weight"
        )
        if paper_portfolios[lane].get("optimizer") == "hrp":
            assert meta.get("optimizer_fallback") == "no as-of price panel supplied"
