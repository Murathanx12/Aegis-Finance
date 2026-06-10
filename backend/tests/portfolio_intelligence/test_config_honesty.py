"""
Config-vs-behavior audit (Step #1 acceptance: "no overclaiming").

The lanes must not claim an optimizer they don't actually run. Today the engine
is equal-weight within sleeves, so:
  - every lane's `optimizer` must be a value the code honors as equal-weight,
  - the actual computed weights must BE equal-weight within each sleeve,
  - intent for future optimization is recorded in `planned_optimizer`, not the
    active `optimizer` field.
This test fails if someone reintroduces 'hrp'/'black-litterman' as the active
optimizer without actually wiring (and leakage-testing) it.
"""


from backend.config import paper_portfolios
from backend.services.portfolio_intelligence.rules import (
    _get_sleeve_tickers,
    classify_asset,
    compute_target_weights,
)

LANES = ["conservative", "balanced", "aggressive"]


def test_active_optimizer_is_honest():
    """Active optimizer must be equal_weight until real optimization is wired."""
    for lane in LANES:
        cfg = paper_portfolios[lane]
        assert cfg.get("optimizer") == "equal_weight", (
            f"{lane}: optimizer='{cfg.get('optimizer')}' overclaims — the engine "
            f"runs equal-weight. Record intent in planned_optimizer instead."
        )


def test_intent_preserved_in_planned_optimizer():
    planned = {paper_portfolios[lane].get("planned_optimizer") for lane in LANES}
    assert planned == {"hrp", "black-litterman"}  # intent not lost


def test_weights_are_actually_equal_weight_within_equity_sleeve():
    """Behavior must match the claim: equity names share equal weight."""
    universe = paper_portfolios.get("universe", {})
    eq = set(_get_sleeve_tickers(universe)["equity"])
    for lane in LANES:
        weights = compute_target_weights(paper_portfolios[lane], universe)
        eq_w = [w for t, w in weights.items()
                if t in eq and classify_asset(t) == "equity" and w > 0]
        assert len(eq_w) > 1
        # All equity weights equal (up to float noise) → genuinely equal-weight.
        assert max(eq_w) - min(eq_w) < 1e-9, f"{lane} equity sleeve is not equal-weight"
