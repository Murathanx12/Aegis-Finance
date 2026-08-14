"""INTERNET-INVESTIGATOR-FWD-1 trigger selection — determinism and pairing.

Offline. The trigger rule is pure arithmetic over point-in-time features, which
is the property that makes the trial paired; these tests pin that property.
"""

from __future__ import annotations

import pytest

from backend.services import investigator_triggers as TR
from backend.services import iif1_prereg as PC
from backend.services.iif1_prereg import load_frozen_config


def _f(z=0.0, vol=0.0, earn=False, filing=False, price=100.0, dv=1e9):
    return {"abs_resid_return_z_1d": z, "volume_z_20d": vol,
            "earnings_within_5d": earn, "filing_within_2d": filing,
            "price": price, "dollar_volume_20d": dv}


# ── the frozen rule ─────────────────────────────────────────────────────────

def test_runtime_weights_match_the_frozen_prereg_config():
    """The config in `Aegis module` is the frozen source of truth; this module
    carries a runtime copy. A silent drift between them would mean the trial
    ran a rule other than the one registered.

    This used to `pytest.skip` when the sibling tree was absent — i.e. report
    green while executing nothing, in exactly the checkouts where it mattered.
    See `backend/services/iif1_prereg.py` for why the default is now a loud
    failure and why the real enforcement moved to the runner.
    """
    mod = load_frozen_config()
    if mod is None:
        # Only reachable where the exemption was DECLARED, which by definition
        # is a context that never accrues. `verify_or_refuse` still binds on
        # any night that spends, and that is pinned separately.
        pytest.skip(f"{PC.OPT_OUT_ENV}=1 declared — see the banner above")
    assert mod.TRIGGER_WEIGHTS == TR.TRIGGER_WEIGHTS
    assert mod.TRIGGERS_PER_NIGHT == TR.TRIGGERS_PER_NIGHT
    assert mod.MIN_PRICE == TR.MIN_PRICE
    assert mod.MIN_DOLLAR_VOLUME_20D == TR.MIN_DOLLAR_VOLUME_20D


def test_a_missing_frozen_config_fails_loudly_instead_of_skipping(monkeypatch,
                                                                 tmp_path):
    """The regression pin for the skip itself.

    The failure this guards is invisible by construction: the test above would
    keep passing, print nothing, and verify nothing. So the absence path is
    exercised directly.
    """
    monkeypatch.setattr(PC, "CONFIG_PATH", tmp_path / "nope" / "iif1_config.py")
    monkeypatch.delenv(PC.OPT_OUT_ENV, raising=False)
    with pytest.raises(PC.FrozenPreregMissing):
        PC.load_frozen_config()


def test_the_opt_out_must_be_declared_explicitly_not_inferred(monkeypatch,
                                                              tmp_path):
    """A context with no sibling tree may opt out — but only by SAYING so."""
    monkeypatch.setattr(PC, "CONFIG_PATH", tmp_path / "nope" / "iif1_config.py")
    monkeypatch.setenv(PC.OPT_OUT_ENV, "1")
    assert PC.load_frozen_config() is None

    monkeypatch.setenv(PC.OPT_OUT_ENV, "true")      # anything but "1" is not it
    with pytest.raises(PC.FrozenPreregMissing):
        PC.load_frozen_config()


def test_score_is_a_weighted_sum_of_its_components():
    c = TR.score_candidate("A", _f(z=2.0, vol=1.0, earn=True, filing=False))
    assert c.components["abs_resid_return_z_1d"] == pytest.approx(2.0)
    assert c.components["volume_z_20d"] == pytest.approx(1.0)
    assert c.components["earnings_within_5d"] == pytest.approx(1.5)
    assert c.components["filing_within_2d"] == pytest.approx(0.0)
    assert c.score == pytest.approx(4.5)


def test_a_negative_move_is_as_unusual_as_a_positive_one():
    assert TR.score_candidate("A", _f(z=-3.0)).score == \
        TR.score_candidate("B", _f(z=3.0)).score


def test_a_wild_z_is_clipped_so_one_bad_tick_cannot_take_the_whole_night():
    c = TR.score_candidate("A", _f(z=40.0))
    assert c.components["abs_resid_return_z_1d"] == TR.Z_CLIP


# ── missing data is disclosed, never read as calm ───────────────────────────

def test_a_missing_component_is_disclosed_rather_than_scored_as_zero():
    f = _f(z=2.0)
    del f["volume_z_20d"]
    c = TR.score_candidate("A", f)
    assert "volume_z_20d" not in c.components
    assert "missing" in c.reason and "volume_z_20d" in c.reason
    assert c.eligible


def test_a_security_with_no_features_at_all_is_excluded_not_ranked_zero():
    """Unmeasured is not calm. Ranking it at zero parks it at the bottom of the
    list forever and the gap never becomes visible."""
    c = TR.score_candidate("A", {"price": 100.0, "dollar_volume_20d": 1e9})
    assert not c.eligible
    assert "no trigger features" in c.reason


def test_nan_and_junk_are_treated_as_missing_not_as_numbers():
    # Liquidity is supplied so this test measures COMPONENT parsing and not the
    # liquidity floor. Without it the name is excluded for an unrelated reason
    # and the assertion below would pass for the wrong one.
    c = TR.score_candidate("A", {"abs_resid_return_z_1d": float("nan"),
                                 "volume_z_20d": "banana",
                                 "earnings_within_5d": False,
                                 "filing_within_2d": False,
                                 "price": 100.0, "dollar_volume_20d": 1e9})
    assert "abs_resid_return_z_1d" not in c.components
    assert "volume_z_20d" not in c.components
    assert c.eligible          # the two boolean components still measured


# ── liquidity floors ────────────────────────────────────────────────────────

def test_penny_stocks_and_illiquid_names_are_excluded_with_a_reason():
    assert not TR.score_candidate("A", _f(z=9.0, price=2.0)).eligible
    assert not TR.score_candidate("B", _f(z=9.0, dv=1e5)).eligible
    assert "price" in TR.score_candidate("A", _f(price=2.0)).reason


# ── selection ───────────────────────────────────────────────────────────────

def test_selection_takes_the_top_k_by_score():
    # z values kept BELOW Z_CLIP so this test measures ranking, not clipping.
    feats = {f"T{i}": _f(z=float(i) / 2.0) for i in range(10)}
    out = TR.select_triggers(feats, k=3)
    assert out["tickers"] == ["T9", "T8", "T7"]
    assert out["n_selected"] == 3 and not out["short_of_k"]


def test_everything_above_the_clip_ties_and_resolves_alphabetically():
    """Deliberate, and worth pinning because it looks like a bug.

    Once several names are past Z_CLIP they are indistinguishable by score, and
    the tie is broken by ticker — arbitrary but DETERMINISTIC, which is the
    property that matters. Breaking the tie by the unclipped z instead would
    hand the slot straight back to the 40-sigma bad tick the clip exists to
    keep out.
    """
    feats = {f"T{i}": _f(z=float(i)) for i in range(6, 10)}   # all >= Z_CLIP
    out = TR.select_triggers(feats, k=3)
    assert out["tickers"] == ["T6", "T7", "T8"]
    assert all(s["score"] == TR.Z_CLIP for s in out["selected"])


def test_selection_is_deterministic_under_ties():
    """Two runs of the same night must produce the same cells, or a restart
    silently makes the arms incomparable."""
    feats = {f"T{i}": _f(z=1.0) for i in range(20)}
    a = TR.select_triggers(feats, k=5)
    b = TR.select_triggers(dict(reversed(list(feats.items()))), k=5)
    assert a["tickers"] == b["tickers"]


def test_being_short_of_k_is_disclosed_and_never_padded():
    """A quiet night is informative. Padding it with the next-most-ordinary
    names would change what "triggered" means on exactly those nights."""
    feats = {"A": _f(z=1.0), "B": _f(price=1.0)}      # B ineligible
    out = TR.select_triggers(feats, k=10)
    assert out["tickers"] == ["A"]
    assert out["short_of_k"] is True
    assert out["n_excluded"] == 1
    assert out["excluded"][0]["ticker"] == "B"


def test_the_weights_used_are_reported_with_the_selection():
    out = TR.select_triggers({"A": _f(z=1.0)}, k=1)
    assert out["weights"] == TR.TRIGGER_WEIGHTS


# ── the pairing guard ───────────────────────────────────────────────────────

def test_identical_cell_sets_pass_the_guard():
    TR.assert_arms_share_cells({"A_snapshot": ["X", "Y"], "B_tools": ["Y", "X"]})


def test_a_divergent_arm_raises_and_voids_the_night():
    """This does not degrade the trial, it invalidates it: the paired statistic
    silently stops being paired and the number still looks like a result."""
    with pytest.raises(ValueError, match="VOID"):
        TR.assert_arms_share_cells({"A_snapshot": ["X", "Y"],
                                    "B_tools": ["X", "Z"]})


def test_the_guard_names_what_diverged():
    with pytest.raises(ValueError) as e:
        TR.assert_arms_share_cells({"A_snapshot": ["X", "Y"], "B_tools": ["X"]})
    assert "Y" in str(e.value)


# ── the liquidity floor cannot be waived by ignorance ───────────────────────

def test_a_security_with_no_price_is_excluded_not_admitted():
    """Found by the first full-universe assembly: MMC, PXD and SQ returned no
    price series (stale/renamed symbols) and came through ELIGIBLE, because the
    floor read `if price is not None and price < MIN_PRICE`.

    The floor exists because a name that cannot be PRICED reliably cannot be
    GRADED reliably. "No price at all" is the limiting case of that, not an
    exemption from it.
    """
    f = _f(z=9.0)
    del f["price"]
    c = TR.score_candidate("MMC", f)
    assert not c.eligible
    assert "liquidity unverifiable" in c.reason and "price" in c.reason


def test_a_security_with_no_dollar_volume_is_excluded_too():
    f = _f(z=9.0)
    del f["dollar_volume_20d"]
    c = TR.score_candidate("PXD", f)
    assert not c.eligible
    assert "dollar_volume_20d" in c.reason


def test_nan_liquidity_is_treated_as_unmeasured_not_as_a_number():
    f = _f(z=9.0, price=float("nan"))
    assert not TR.score_candidate("X", f).eligible


def test_an_unpriceable_name_cannot_reach_the_trigger_list():
    """The property that actually matters: a name nobody can price must not be
    able to consume one of the forty paid slots."""
    feats = {"GOOD": _f(z=1.0)}
    bad = _f(z=9.0)                       # the highest score in the universe
    del bad["price"]
    feats["STALE"] = bad
    out = TR.select_triggers(feats, k=2)
    assert out["tickers"] == ["GOOD"]
    assert out["n_excluded"] == 1
    assert any(r["ticker"] == "STALE" for r in out["excluded"])


def test_measured_liquidity_still_passes_and_still_fails_on_its_merits():
    assert TR.score_candidate("A", _f(z=1.0)).eligible
    assert not TR.score_candidate("B", _f(z=1.0, price=2.0)).eligible
    assert not TR.score_candidate("C", _f(z=1.0, dv=1e5)).eligible
