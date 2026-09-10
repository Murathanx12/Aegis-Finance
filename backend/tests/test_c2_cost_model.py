"""C2's cost model — the flat per-date charge is pinned OUT, and the corrected
net numbers are pinned to their amendment receipt.

Two things are asserted here, and they fail for different reasons on purpose.

1. **Behaviour.** `turnover_costs` charges `sum |w_t - w_(t-1)| x bps`. A book
   that does not trade must cost NOTHING, and a book that replaces both legs
   entirely must cost exactly `2 sides x 2 legs x bps` — the old flat charge,
   which is the CEILING of the model rather than its default. If someone puts
   a constant back in (`cost = 2 * bps * 2` on every date, as run01 had at
   `_daily_returns` line 159), the zero-turnover case goes non-zero and this
   file goes red before a receipt is written.

2. **The numbers.** `C2_cost_model_amendment.json` carries the corrected net
   line (-134.091 / -149.234 / -150.708 %/yr) and the turnover that produced
   it. run01's file is left byte-for-byte as written, and the test asserts that
   its net numbers are the FLAT-cost numbers the amendment retracts — so a
   silent edit of either receipt is visible.

Receipts are large and are not on every checkout, so a missing receipt SKIPS;
a receipt that is present and disagrees is a failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
NIGHT = REPO / "backend" / "data" / "optimus" / "night_factory_2026-09-09"
RUN01 = NIGHT / "C2_curriculum_transfer_run01.json"
AMEND = NIGHT / "C2_cost_model_amendment.json"

C2 = pytest.importorskip("scripts.night_c2_curriculum_transfer")


def _json(p: Path) -> dict:
    if not p.is_file():
        pytest.skip(f"receipt absent on this machine: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------- the behaviour
def test_a_book_that_does_not_trade_pays_nothing():
    """The whole defect in one assertion: no turnover, no cost."""
    w = {"AAA": 0.5, "BBB": 0.5, "CCC": -0.5, "DDD": -0.5}
    days = [(f"d{i}", dict(w)) for i in range(10)]
    df = C2.turnover_costs(days, 25.0, charge_entry=False, charge_exit=False)
    assert float(df["cost"].sum()) == 0.0, (
        "a book whose weights never change was charged a cost — the flat "
        "per-date charge is back")
    assert float(df["turnover"].abs().sum()) == 0.0
    assert float(df["traded"].abs().sum()) == 0.0


def test_full_replacement_costs_exactly_the_old_flat_charge():
    """The flat 100 bps is the CEILING of the model, not its default."""
    a = {"AAA": 1.0, "CCC": -1.0}
    b = {"BBB": 1.0, "DDD": -1.0}
    df = C2.turnover_costs([("d0", a), ("d1", b), ("d2", a)], 25.0,
                           charge_entry=False, charge_exit=False)
    later = df.iloc[1:]
    assert later["turnover"].round(10).eq(1.0).all(), "full replacement is turnover 1.0"
    assert later["cost"].round(10).eq(round(C2.FLAT_LIQUIDATION_COST, 10)).all(), (
        "a fully replaced long-short book must cost 2 legs x 2 sides x 25 bps = 100 bps")


def test_half_the_book_turning_over_costs_half():
    """Cost is linear in traded notional — not a step function, not a constant."""
    a = {"AAA": 0.5, "BBB": 0.5, "CCC": -0.5, "DDD": -0.5}
    b = {"AAA": 0.5, "XXX": 0.5, "CCC": -0.5, "YYY": -0.5}
    df = C2.turnover_costs([("d0", a), ("d1", b)], 25.0,
                           charge_entry=False, charge_exit=False)
    assert round(float(df["turnover"].iloc[1]), 10) == 0.5
    assert round(float(df["cost"].iloc[1]), 10) == round(C2.FLAT_LIQUIDATION_COST / 2, 10)


def test_entry_and_exit_are_charged_when_asked_and_only_then():
    w = {"AAA": 1.0, "CCC": -1.0}
    on = C2.turnover_costs([("d0", w), ("d1", w)], 25.0)
    off = C2.turnover_costs([("d0", w), ("d1", w)], 25.0,
                            charge_entry=False, charge_exit=False)
    # entry buys one unit a leg, exit sells one unit a leg: half a replacement each
    assert round(float(on["cost"].sum()), 10) == round(C2.FLAT_LIQUIDATION_COST, 10)
    assert float(off["cost"].sum()) == 0.0


def test_the_scripts_own_constant_is_the_flat_charge_it_replaced():
    assert round(C2.FLAT_LIQUIDATION_COST * 1e4, 6) == 100.0
    assert C2.COST_BPS_PER_SIDE == 25.0


# ------------------------------------------------------------------ the numbers
def test_run01_net_is_the_flat_cost_number_the_amendment_retracts():
    """run01 stays as written; this pins WHAT it says so an edit is visible."""
    arms = _json(RUN01)["arms"]
    assert arms["BASELINE"]["net"]["ann_pct"] == -221.422
    assert arms["CONTROL"]["net"]["ann_pct"] == -232.537
    assert arms["TRANSFER"]["net"]["ann_pct"] == -236.982
    assert "flat 100 bps per date" in _json(RUN01)["construction"]["cost_note"]


def test_amendment_carries_the_corrected_net_and_the_turnover_behind_it():
    a = _json(AMEND)
    assert a["amends"] == "C2_curriculum_transfer_run01.json"
    corrected = {"BASELINE": -134.091, "CONTROL": -149.234, "TRANSFER": -150.708}
    for arm, net in corrected.items():
        row = a["corrected_numbers"][arm]
        assert row["net_ann_pct"] == net, arm
        # every net number names the turnover and the rate that produced it
        assert 0.5 <= row["turnover_per_rebalance"] < 1.0, arm
        assert row["run01_flat_cost_bps_per_date"] == 100.0
        # the realised charge is BELOW the flat ceiling, and it is what the net used
        assert row["realised_cost_bps_per_date"] < 100.0, arm
        assert round(row["realised_cost_bps_per_date"], 1) == round(
            row["traded_notional_per_date"] * 25.0, 1), arm


def test_the_amendment_does_not_move_the_gross_line_or_the_verdict():
    """A cost fix that changed the gross numbers would be a different experiment."""
    a = _json(AMEND)
    old = _json(RUN01)["arms"]
    for arm in ("BASELINE", "CONTROL", "TRANSFER"):
        assert a["corrected_numbers"][arm]["gross_ann_pct"] == old[arm]["gross"]["ann_pct"], arm
        assert (a["corrected_numbers"][arm]["net_daily_liquidation_ann_pct"]
                == old[arm]["net"]["ann_pct"]), arm
    assert a["verdict_unchanged"] is True
    assert "CURRICULUM_NOT_EARNED" in a["corrected_verdict"]
    # the ordering the verdict rests on
    c = a["corrected_numbers"]
    assert (c["TRANSFER"]["net_ann_pct"] < c["CONTROL"]["net_ann_pct"]
            < c["BASELINE"]["net_ann_pct"])


def test_the_live_script_no_longer_declares_a_flat_charge():
    src = (REPO / "scripts" / "night_c2_curriculum_transfer.py").read_text(encoding="utf-8")
    body = src[src.index("def run("):]
    assert "realised_weight_turnover" in body
    assert "flat 100 bps per date" not in body, (
        "the receipt would tell the reader the cost is flat again")
