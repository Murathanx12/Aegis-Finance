"""`kill_rule_from_measured_gap` (2026-09-29): a kill line from the gap's MEASURED sd.

CRSP_BLEND_v0 registered "-1.645 x its 21-draw noise sd" and the only
implementation (`kill_rule_power`) builds that sd from idiosyncratic risk alone,
so it leaves out the factor mismatch between book and twin: a ~21-25% false kill
under zero edge instead of 5%. The new function takes the measured gap sd; the
old one is unchanged for the books already frozen on it.
"""
import math

import pytest

from scripts import shadow_bayes_rule as SB


def test_line_is_z_times_the_sqrt_time_scaled_measured_sd():
    k = SB.kill_rule_from_measured_gap(0.0237, sessions=126)
    sd = 0.0237 * math.sqrt(6)
    assert k["sd_D"] == pytest.approx(sd, rel=1e-4)
    assert k["kill_line"] == pytest.approx(-1.645 * sd, rel=1e-4)
    assert k["P_kill_if_zero_edge"] == pytest.approx(0.05, abs=1e-3)


def test_a_measured_horizon_sd_overrides_the_scaling():
    k = SB.kill_rule_from_measured_gap(0.0237, sessions=126, horizon_sd=0.07)
    assert k["sd_D"] == pytest.approx(0.07)
    assert k["sd_source"] == "measured horizon sd"
    assert k["sd_D_sqrt_time"] == pytest.approx(0.0237 * math.sqrt(6), rel=1e-4)


def test_power_under_a_claimed_edge():
    k = SB.kill_rule_from_measured_gap(0.0237, sessions=126, claimed_edge_monthly=0.0064)
    mu, sd = 0.0064 * 6, 0.0237 * math.sqrt(6)
    phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))           # noqa: E731
    assert k["expected_D_if_claim_true"] == pytest.approx(mu, rel=1e-4)
    assert k["P_kill_if_claim_true"] == pytest.approx(phi(-1.645 - mu / sd), abs=1e-4)
    assert k["P_kill_if_claim_true"] < k["P_kill_if_zero_edge"]
    assert k["months_to_t2_if_claim_true"] == pytest.approx((2 * 0.0237 / 0.0064) ** 2, abs=0.1)


def test_the_review_number_the_idiosyncratic_line_kills_a_fifth_of_zero_edge_books():
    """Section 6 of the review: a -4.7% line against a measured 5.8% sd."""
    assert SB.false_kill_rate(-0.047, 0.058) == pytest.approx(0.21, abs=0.01)
    k = SB.kill_rule_from_measured_gap(0.058 / math.sqrt(6), sessions=126)
    assert SB.false_kill_rate(k["kill_line"], k["sd_D"]) == pytest.approx(0.05, abs=1e-3)


@pytest.mark.parametrize("bad", [0.0, -0.01, float("nan"), float("inf")])
def test_refuses_a_missing_or_nonsense_sd(bad):
    with pytest.raises(ValueError, match="REFUSED"):
        SB.kill_rule_from_measured_gap(bad)


def test_the_old_function_is_unchanged_for_frozen_books():
    held = {"A": 0.01, "B": 0.01}
    k = SB.kill_rule_power(held, {"A": 0.001, "B": 0.001}, {"A": 0.08, "B": 0.08})
    assert k["sd_D"] == pytest.approx(math.sqrt(2 * 0.25 * 0.08 ** 2 * 3 * (1 + 1 / 21)), rel=1e-3)
    assert "kill_line" not in k            # the new keys live only on the new function


def test_the_crsp_blend_amendment_names_a_5pct_line_and_leaves_the_registration_alone():
    import hashlib
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "backend" / "data" / "optimus" / "shadow_bayes"
    amend = root / "AMENDMENT_CRSP_BLEND_v0_KILL_RULE_2026-09-29.json"
    if not amend.exists():
        pytest.skip("amendment not present in this checkout")
    a = json.loads(amend.read_text(encoding="utf-8"))
    reg = root / "REGISTRATION_CRSP_BLEND_v0_2026-09-28_20260929T082258Z.json"
    assert hashlib.sha256(reg.read_bytes()).hexdigest() == a["amends"]["sha256"]
    assert a["amends"]["modified"] is False
    assert a["kill_rule"]["P_kill_if_zero_edge"] == pytest.approx(0.05, abs=1e-3)
    assert a["kill_rule"]["old_line_real_false_kill_rate"] > 0.15
    assert set(a["reading_schedule"]["by_session"]) == {"21", "63", "126"}
