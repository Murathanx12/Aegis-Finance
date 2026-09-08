"""S5 -- breakeven fee and the ADV cap, against HAND-COMPUTED known answers.

Every number asserted here is derivable with a calculator from the identity in
the docstring, so a regression in either implementation is caught by the value,
not merely by the shape.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.strategy.execution import (CANNOT_DETERMINE, ExecutionRefused,
                                        adv_capped_path, breakeven_row,
                                        execution_row, trades_from_turnover)
from backend.strategy.vendor import VENDOR

CLONE = Path(r"C:\Users\mrthn\reference\Vibe-Trading")


# --------------------------------------------------------------------------
# licence provenance: the vendored bodies are NOT edited


@pytest.mark.parametrize("local,upstream", [
    ("impact.py", "agent/src/quantlib/impact.py"),
    ("factor_costs.py", "agent/backtest/factor_costs.py"),
])
def test_the_vendored_bodies_are_not_edited(local: str, upstream: str):
    src = CLONE / upstream
    if not src.exists():                                     # pragma: no cover
        pytest.skip(f"the Vibe-Trading clone is not present at {src}; the "
                    f"byte comparison cannot run here")
    ours = (Path(__file__).resolve().parents[1] / "strategy" / "vendor"
            / local).read_text(encoding="utf-8")
    theirs = src.read_text(encoding="utf-8")
    assert ours.endswith(theirs), (
        f"{local} is NOT byte-identical to upstream after its header. An "
        f"edited vendored file cannot be diffed against upstream, which is the "
        f"only reason to vendor rather than reimplement.")


def test_the_ONE_extracted_function_is_byte_identical_to_upstream():
    """`breakeven_fee_bps` was lifted out of a 453-line module. The extracted
    body must be the upstream body, character for character."""
    src = CLONE / "agent/src/strategy_discovery/models.py"
    if not src.exists():                                     # pragma: no cover
        pytest.skip(f"the Vibe-Trading clone is not present at {src}")
    text = src.read_text(encoding="utf-8")
    body = text[text.index("def breakeven_fee_bps("):
                text.index("def build_warnings(")].rstrip()
    ours = (Path(__file__).resolve().parents[1] / "strategy" / "vendor"
            / "breakeven.py").read_text(encoding="utf-8")
    assert body in ours


def test_the_MIT_licence_text_is_reproduced_in_every_vendored_file():
    vendor = Path(__file__).resolve().parents[1] / "strategy" / "vendor"
    for name in ("impact.py", "factor_costs.py", "breakeven.py"):
        text = (vendor / name).read_text(encoding="utf-8")
        assert "MIT License" in text
        assert "Vibe-Trading Contributors" in text
        assert "VENDORED VERBATIM" in text
    assert VENDOR["licence"] == "MIT"


def test_the_import_shim_resolves_the_vendored_impact_module_and_no_other():
    import sys

    from backend.strategy.vendor import impact as vendored

    assert sys.modules["src.quantlib.impact"] is vendored


# --------------------------------------------------------------------------
# breakeven_fee_bps -- hand-computed


def test_breakeven_fee_matches_the_identity_by_hand():
    """ln(1.10) / (2 * 10 * 1.0) * 1e4 = 0.0953102 / 20 * 1e4 = 47.6551 bps."""
    row = breakeven_row(gross_return=0.10, trades=10, position_size=1.0)
    assert row["breakeven_fee_bps"] == pytest.approx(47.65508990, abs=1e-6)
    assert row["breakeven_fee_bps"] == pytest.approx(
        math.log(1.10) / 20.0 * 10_000.0, rel=1e-12)


def test_breakeven_halves_when_the_trade_count_doubles():
    a = breakeven_row(gross_return=0.10, trades=10)["breakeven_fee_bps"]
    b = breakeven_row(gross_return=0.10, trades=20)["breakeven_fee_bps"]
    assert b == pytest.approx(a / 2.0, rel=1e-12)


def test_breakeven_halves_when_the_position_size_doubles():
    a = breakeven_row(gross_return=0.10, trades=10, position_size=0.5)
    b = breakeven_row(gross_return=0.10, trades=10, position_size=1.0)
    assert b["breakeven_fee_bps"] == pytest.approx(
        a["breakeven_fee_bps"] / 2.0, rel=1e-12)


def test_a_book_below_its_own_declared_cost_rate_is_called_DEAD():
    """47.66 bps a side breakeven vs a 60 bps a side venue: already gone."""
    row = breakeven_row(gross_return=0.10, trades=10,
                        declared_cost_bps_per_side=60.0)
    assert row["edge_survives_declared_cost"] is False
    assert "DEAD AT ITS OWN COST RATE" in row["verdict"]
    assert row["headroom_bps_per_side"] == pytest.approx(47.65508990 - 60.0,
                                                         abs=1e-6)


def test_a_book_above_its_declared_cost_rate_survives():
    row = breakeven_row(gross_return=0.10, trades=10,
                        declared_cost_bps_per_side=12.0)
    assert row["edge_survives_declared_cost"] is True
    assert "SURVIVES" in row["verdict"]


def test_THE_UNITS_ARE_PER_SIDE_and_the_row_says_so():
    """The `2` in the denominator is the two legs, so the rate solved for is
    charged on EACH leg. Comparing it with a round trip is a factor of two and
    flatters every book."""
    row = breakeven_row(gross_return=0.10, trades=10,
                        declared_cost_bps_per_side=25.0)
    assert "PER SIDE" in row["units"]
    assert row["declared_cost_bps_per_side"] == 25.0
    assert row["declared_round_trip_bps"] == 50.0        # printed, not compared
    assert "a side" in row["verdict"]


@pytest.mark.parametrize("breakeven_side,cost_side,survives", [
    (1.2, 10.0, False),      # PEAD, thinnest cell, 10 bps grid
    (1.2, 25.0, False),      # PEAD, thinnest cell, 25 bps grid
    (14.6, 10.0, True),      # PEAD, widest cell, 10 bps grid
    (14.6, 25.0, False),     # PEAD, widest cell, 25 bps grid
])
def test_THE_PEAD_VALIDATION_CASE(breakeven_side, cost_side, survives):
    """The event-family lane measured PEAD's breakeven at 1.2-14.6 bps A SIDE
    against the 10 / 25 bps grid: the effect is inside the spread in three of
    the four cells. This is the number `breakeven_fee_bps` exists to surface,
    and it is the case that caught the units bug -- against a ROUND TRIP the
    14.6 cell would have read as a survivor at 25 bps too."""
    # solve the identity backwards for a gross return that gives this breakeven
    gross = math.expm1(breakeven_side / 10_000.0 * 2 * 10 * 1.0)
    row = breakeven_row(gross_return=gross, trades=10,
                        declared_cost_bps_per_side=cost_side)
    assert row["breakeven_fee_bps"] == pytest.approx(breakeven_side, abs=1e-6)
    assert row["edge_survives_declared_cost"] is survives


def test_zero_trades_is_CANNOT_DETERMINE_not_infinity():
    row = breakeven_row(gross_return=0.10, trades=0)
    assert row["breakeven_fee_bps"] is None
    assert CANNOT_DETERMINE in row["verdict"]
    assert "costs cannot kill this" in row["verdict"]


def test_a_total_loss_is_CANNOT_DETERMINE():
    assert breakeven_row(gross_return=-1.0, trades=5)["breakeven_fee_bps"] is None


def test_no_declared_cost_rate_says_so_in_house_words():
    row = breakeven_row(gross_return=0.10, trades=10)
    assert "Quote the cost rate or do not quote the count" in row["verdict"]


def test_trades_from_turnover_is_two_legs_per_round_trip():
    # one-way turnover 0.90 per period over 12 periods = 10.8 book-legs = 5.4
    # round trips -> 5
    assert trades_from_turnover([0.90] * 12) == 5
    assert trades_from_turnover([]) == 0
    assert trades_from_turnover([0.90] * 12, n_names=10) == 54


# --------------------------------------------------------------------------
# the ADV cap and the carried-forward shortfall -- known by construction


def _adv(periods, symbols, value):
    return pd.DataFrame({s: [value] * len(periods) for s in symbols},
                        index=periods)


def test_the_shortfall_is_CARRIED_FORWARD_over_four_periods():
    """KNOWN BY CONSTRUCTION. capital 1e6, ADV 1e6, cap 10% -> a name may move
    0.10 of capital per period. A 0.35 target therefore fills 0.10, 0.10, 0.10,
    0.05 and is complete on the fourth period, never before."""
    periods = ["p1", "p2", "p3", "p4", "p5"]
    tw = pd.DataFrame({"A": [0.35] * 5}, index=periods)
    path = adv_capped_path(tw, _adv(periods, ["A"], 1e6), capital=1e6,
                           max_participation=0.10)
    got = [round(float(x), 10) for x in path.achieved["A"]]
    assert got == [0.10, 0.20, 0.30, 0.35, 0.35]
    unf = [round(float(x), 10) for x in path.unfilled["A"]]
    assert unf == [0.25, 0.15, 0.05, 0.0, 0.0]
    assert path.capped_symbols["p1"] == ("A",)
    assert path.capped_symbols["p4"] == ()          # 0.05 <= the 0.10 capacity


def test_a_target_inside_capacity_fills_in_one_period_and_nothing_is_unfilled():
    periods = ["p1", "p2"]
    tw = pd.DataFrame({"A": [0.05, 0.05]}, index=periods)
    path = adv_capped_path(tw, _adv(periods, ["A"], 1e6), capital=1e6,
                           max_participation=0.10)
    assert float(path.achieved["A"].iloc[0]) == pytest.approx(0.05)
    assert float(path.unfilled_turnover.sum()) == pytest.approx(0.0)
    assert path.as_dict()["fill_ratio"] == pytest.approx(1.0)


def test_a_name_with_NO_ADV_is_untradeable_not_infinitely_liquid():
    periods = ["p1", "p2"]
    tw = pd.DataFrame({"A": [0.20, 0.20]}, index=periods)
    adv = pd.DataFrame({"A": [np.nan, np.nan]}, index=periods)
    path = adv_capped_path(tw, adv, capital=1e6, max_participation=0.10)
    assert float(path.achieved["A"].iloc[-1]) == 0.0
    assert float(path.unfilled["A"].iloc[-1]) == pytest.approx(0.20)


def test_the_fill_ratio_reports_what_the_tape_could_actually_supply():
    periods = ["p1"]
    tw = pd.DataFrame({"A": [0.50]}, index=periods)
    path = adv_capped_path(tw, _adv(periods, ["A"], 1e6), capital=1e6,
                           max_participation=0.10)
    d = path.as_dict()
    assert d["executed_turnover_total"] == pytest.approx(0.10)
    assert d["unfilled_turnover_total"] == pytest.approx(0.40)
    assert d["fill_ratio"] == pytest.approx(0.20)
    assert d["final_unfilled_by_symbol"] == {"A": pytest.approx(0.40)}


def test_an_empty_target_path_REFUSES_rather_than_reporting_a_full_fill():
    with pytest.raises(ExecutionRefused, match="no target weights"):
        adv_capped_path(pd.DataFrame(), pd.DataFrame(), capital=1e6)


def test_a_period_with_targets_and_no_ADV_REFUSES():
    tw = pd.DataFrame({"A": [0.1, 0.1]}, index=["p1", "p2"])
    adv = pd.DataFrame({"A": [1e6]}, index=["p1"])
    with pytest.raises(ExecutionRefused, match="no ADV"):
        adv_capped_path(tw, adv, capital=1e6)


def test_the_execution_row_says_UNMEASURED_when_no_ADV_was_supplied():
    row = execution_row(gross_return=0.1, trades=10,
                        declared_cost_bps_per_side=10.0)
    assert CANNOT_DETERMINE in row["capacity"]["verdict"]
    assert "not the same as uncapped" in row["capacity"]["verdict"]


def test_the_execution_row_carries_the_MIT_provenance():
    row = execution_row(gross_return=0.1, trades=10)
    assert row["breakeven"]["provenance"]["licence"] == "MIT"
    assert row["breakeven"]["provenance"]["head"] == "a4f06a29"
