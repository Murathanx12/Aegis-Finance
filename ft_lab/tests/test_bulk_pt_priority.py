"""The price-target keyword only ORDERS the conversion queue; it must match target stories and
not generic 'target' language (TRIAL-PT-REVERSAL-1)."""
from ft_lab.bulk_pt_priority import pt_match


def test_matches_price_target_stories():
    assert pt_match("Goldman raises Nvidia price target to $200", "")
    assert pt_match("JPMorgan cuts its target on Apple", "")
    assert pt_match("Analyst note", "PT raised to $50 from $45")
    assert pt_match("Target lowered at Barclays", "")


def test_ignores_generic_target_and_lowercase_pt():
    assert not pt_match("Company hits its sales target", "")
    assert not pt_match("SEPTEMBER update", "the pt was fine")
