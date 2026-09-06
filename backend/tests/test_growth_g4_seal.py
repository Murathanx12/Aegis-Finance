"""G4: one opening, one champion, and a gate that compares like with like."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from learner import growth_lab as GL
from scripts import growth_g4_seal as G4


def _months(a, b):
    return [f"{y}-{m:02d}" for y in range(int(a[:4]), int(b[:4]) + 1)
            for m in range(1, 13) if a <= f"{y}-{m:02d}" <= b]


def _s(a, b, v=0.01):
    idx = _months(a, b)
    return pd.Series([v] * len(idx), index=pd.Index(idx, name="month"))


# ------------------------------------------------------- the single opening

def test_four_legs_of_one_comparison_are_ONE_opening(tmp_path):
    """An opening is the ACT of looking, not a call to a slicing function.

    The book at two cost rates, the SPY leg and the risk-free leg are four
    series and one look. Logging four lines would make `sealed_era_openings: 1`
    an artefact of how the comparison happened to be coded.
    """
    led = tmp_path / "openings.jsonl"
    legs = {"book_10bps": _s("2004-01", "2024-12"),
            "book_25bps": _s("2004-01", "2024-12"),
            "spy_tr": _s("1999-03", "2024-11"),
            "risk_free": _s("1999-03", "2024-11", 0.001)}
    out = GL.open_sealed_window(legs, champion_id="planted", champion_sha256="ab",
                                reason="unit test", ledger=led)
    assert set(out) == set(legs)
    for s in out.values():
        assert s.index[0] >= GL.SEALED_START and s.index[-1] <= GL.SEALED_END
    assert GL.openings_for("planted", ledger=led) == 1
    rec = json.loads(led.read_text(encoding="utf-8").strip())
    assert set(rec["legs"]) == set(legs)
    assert rec["legs"]["book_10bps"]["months"] == len(out["book_10bps"])


def test_a_second_look_is_a_second_line_and_cannot_be_un_written(tmp_path):
    led = tmp_path / "openings.jsonl"
    legs = {"book": _s("2004-01", "2024-12")}
    GL.open_sealed_window(legs, champion_id="p", champion_sha256="ab",
                          reason="first", ledger=led)
    GL.open_sealed_window(legs, champion_id="p", champion_sha256="ab",
                          reason="second", ledger=led)
    assert GL.openings_for("p", ledger=led) == 2


def test_the_opening_returns_nothing_outside_the_sealed_window(tmp_path):
    led = tmp_path / "o.jsonl"
    out = GL.open_sealed_window({"b": _s("1999-01", "2015-12")},
                                champion_id="p", champion_sha256="ab",
                                reason="dev only", ledger=led)
    assert len(out["b"]) == 0
    assert json.loads(led.read_text(encoding="utf-8").strip())["legs"]["b"]["months"] == 0


# --------------------------------------------------------------- the gate

def _claim(book_tw, spy_tw, adm_tw, lev_spy_tw, ln_tw=1.0, passes=True):
    return {
        "beta": 0.67,
        "book": {"terminal_wealth": book_tw, "max_drawdown": -0.3},
        "spy": {"terminal_wealth": spy_tw, "max_drawdown": -0.31},
        "leverage_neutral": {"terminal_wealth": ln_tw},
        "largest_admissible": {"terminal_wealth": adm_tw, "leverage": 1.30},
        "levered_spy_at_budget": {"terminal_wealth": lev_spy_tw, "leverage": 1.25},
        "constraints": {"passes": passes},
    }


def test_the_gate_compares_two_books_sized_to_the_SAME_budget():
    """The amendment says 'at EQUAL drawdown budget'. Both sides are levered.

    The first version of this gate put the UNLEVERED book against LEVERED SPY,
    which is the confusion `learner/growth.py` exists to stop, and it read as a
    loss on a pair where the like-for-like comparison is a win.
    """
    g = G4.build_gate(_claim(book_tw=3.67, spy_tw=3.67, adm_tw=4.66,
                             lev_spy_tw=4.48),
                      {"dsr": 0.99}, ["POSITIVE", "POSITIVE"], {"pbo": 0.1})
    assert g["sealed_tw_at_budget_beats_levered_spy_at_budget"] is True
    assert g["_also_reported_not_part_of_the_gate"]["unlevered_book_beats_spy_tr"] is False
    assert g["ALL_MET"] is True


def test_the_gate_still_fails_when_only_the_wealth_condition_passes():
    g = G4.build_gate(_claim(3.67, 3.67, 4.66, 4.48),
                      {"dsr": 0.0046}, ["POSITIVE", "POSITIVE"], {"pbo": 0.6429})
    assert g["ALL_MET"] is False
    assert set(g["failed"]) == {"dsr_over_family_gt_0_95", "family_pbo_below_0_5"}


def test_the_gate_needs_two_of_three_development_eras():
    g = G4.build_gate(_claim(3.67, 3.67, 4.66, 4.48),
                      {"dsr": 0.99}, ["POSITIVE", "NEGATIVE"], {"pbo": 0.1})
    assert "positive_in_at_least_2_of_3_development_eras" in g["failed"]


def test_the_gate_records_that_it_was_corrected_after_the_fact():
    g = G4.build_gate(_claim(1, 1, 1, 1), {"dsr": 0.1}, [], {"pbo": 0.9})
    assert "NOT re-opened" in g["_correction"]
    assert "equal drawdown budget" in g["_correction"].lower()


# ---------------------------------------------------------- the freeze rule

def test_the_champion_is_chosen_at_the_rate_the_claim_is_made_at():
    """Selecting at 10 bps and claiming at 25 flatters the most turnover."""
    assert G4.SELECTION_COST_BPS == G4.CLAIM_COST_BPS


def test_a_cell_that_breaks_the_constraints_cannot_be_champion():
    g2 = {"cells": {
        "loser|25bps": {"beta": 1.0, "constraints": {"passes": True},
                        "leverage_neutral": {"terminal_wealth": 2.0},
                        "book": {"terminal_wealth": 2.0}, "spy": {},
                        "market_model": {}},
        "breaks_the_budget|25bps": {"beta": 1.0, "constraints": {"passes": False},
                                    "leverage_neutral": {"terminal_wealth": 99.0},
                                    "book": {}, "spy": {}, "market_model": {}},
    }}
    cid, ev = G4.choose_champion(g2, {"cells": {}})
    assert cid == "loser"
    assert ev["constraints_pass"] is True


def test_a_cell_at_the_other_cost_rate_cannot_be_champion():
    g2 = {"cells": {
        "cheap_and_huge|10bps": {"beta": 1.0, "constraints": {"passes": True},
                                 "leverage_neutral": {"terminal_wealth": 99.0},
                                 "book": {}, "spy": {}, "market_model": {}},
        "honest|25bps": {"beta": 1.0, "constraints": {"passes": True},
                         "leverage_neutral": {"terminal_wealth": 2.0},
                         "book": {}, "spy": {}, "market_model": {}},
    }}
    assert G4.choose_champion(g2, {"cells": {}})[0] == "honest"


def test_no_admissible_cell_refuses_rather_than_freezing_something():
    with pytest.raises(SystemExit) as e:
        G4.choose_champion({"cells": {}}, {"cells": {}})
    assert "REFUSED" in str(e.value) and "sealed era stays closed" in str(e.value)


# ------------------------------------------------------- the shipped receipt

def test_the_shipped_sealed_receipt_records_exactly_one_opening():
    p = GL.OUT_DIR / "G4_seal.json"
    if not p.exists():
        pytest.skip("G4 has not been run in this checkout")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["sealed_era_openings"] == 1
    assert d["sealed_era_reopened_by_this_correction"] is False
    # BETA FIRST, in the headline, before any wealth number.
    h = d["headline"]
    assert h.startswith("beta ")
    assert h.index("beta") < h.index("returned")
    # the champion declaration was written before the open
    decl = json.loads((GL.OUT_DIR / "G4_CHAMPION_DECLARATION.json")
                      .read_text(encoding="utf-8"))
    assert decl["champion_sha256"] == d["champion_sha256"]
    assert decl["sealed_era_openings_before_this_job"] == 0
