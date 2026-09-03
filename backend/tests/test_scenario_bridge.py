"""Offline tests for the scenario bridge. NO NETWORK, NO LLM, NO REAL PANEL.

The two things worth pinning here are the two things that would silently make
the whole exercise meaningless:

1. **A synthetic scenario must never be able to acquire a return.** Every
   outcome number in the receipt has to come out of a real (permno, month) row.
   `test_no_outcome_without_a_real_row` builds a panel whose targets are all NaN
   and proves the grade comes back with no number rather than a zero.
2. **A dropped predicate must be reported as dropped.** A filter that silently
   vanishes makes a scenario look better matched than it is -- the same shape as
   `[[feedback-a-reason-count-from-a-short-circuiting-chain-is-an-order]]`.

Everything else is arithmetic on a fixture small enough to check by hand.

Dates are DERIVED, never literal: a fixture that encodes a calendar moment fails
the day after it passes (CLAUDE.md, session-start protocol §5).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from scripts import scenario_bridge as SB


# ------------------------------------------------------------------ fixtures

def _months(n: int) -> list[str]:
    """n consecutive month labels ending on the month before today."""
    today = date.today().replace(day=1)
    out = []
    cur = today
    for _ in range(n):
        cur = (cur - timedelta(days=1)).replace(day=1)
        out.append(f"{cur.year:04d}-{cur.month:02d}")
    return sorted(out)


def tiny_panel(n_months: int = 30, n_names: int = 40, seed: int = 7,
               all_targets_nan: bool = False) -> pd.DataFrame:
    """A hand-sized panel with the same column contract as the real one."""
    rng = np.random.default_rng(seed)
    months = _months(n_months)
    rows = []
    for m in months:
        for j in range(n_names):
            rows.append({
                "permno": 10000 + j,
                "month": m,
                "vintage": pd.Timestamp(f"{m}-15"),
                "sector": "Manufacturing" if j % 2 == 0 else "Services",
                "band": "lt_1_5",
                "close": 10.0 + j,
                "ratio": 1.0 + j / 100.0,
                "ratio__xs": (j + 0.5) / n_names,
                "coverage": 1 + j % 9,
                "numest": 1 + j % 7,
                "drawdown_60d__xs": (j + 0.5) / n_names,
                "mom_12_1": -1.0 + 2.0 * (j + 0.5) / n_names,
                "vol_20d__xs": (j + 0.5) / n_names,
                # Size and liquidity are DELIBERATELY decorrelated from the
                # drawdown rank: if the matching strata lined up with the
                # planted band, the control set would contain the effect and
                # the test would pass for the wrong reason.
                "log_market_cap__xs": ((j * 7) % n_names + 0.5) / n_names,
                "log_dollar_vol_20d__xs": ((j * 13) % n_names + 0.5) / n_names,
                "coverage__xs": (j + 0.5) / n_names,
                "net_rev_4w__xs": (j + 0.5) / n_names,
                "target_rev_1m__xs": (j + 0.5) / n_names,
                "coverage_rev_1m": float(j % 3 - 1),
                "holder_net": float(j - n_names / 2),
                "holder_net__xs": (j + 0.5) / n_names,
            })
    p = pd.DataFrame(rows)
    for h in SB.HORIZONS:
        if all_targets_nan:
            p[f"excess_vw_{h}m"] = np.nan
        else:
            # A REAL, PLANTED effect: deeply drawn-down names do better. Small
            # enough that the test is about plumbing, not about finding alpha.
            base = rng.normal(0.0, 0.02, len(p))
            lo, hi = SB._BANDS["drawdown_state"]["deep_drawdown"]
            in_band = (p["drawdown_60d__xs"] >= lo) & (p["drawdown_60d__xs"] < hi)
            p[f"excess_vw_{h}m"] = base + 0.05 * in_band
    for src, dst in (("log_market_cap__xs", "size_tercile"),
                     ("log_dollar_vol_20d__xs", "liq_tercile")):
        v = p[src]
        p[dst] = np.where(v < 1 / 3, 0, np.where(v < 2 / 3, 1, 2)).astype("int8")
    return p


def a_scenario(**over) -> dict:
    s = {
        "scenario_id": "TEST-0",
        "event_type": "capacity_bottleneck",
        "actors": ["upstream fabricator", "downstream assembler"],
        "company_role": "bottleneck_holder",
        "sector_theme": "a constrained production stage",
        "sic_division_hint": "Manufacturing",
        "demand_change": "rising",
        "supply_change": "falling",
        "capacity_constraint": "binding",
        "holder_action": "unknown",
        "analyst_change": "none",
        "price_state": {"drawdown_state": "deep_drawdown",
                        "momentum_12_1_sign": "unknown"},
        "attention_state": "unknown",
        "expected_horizon_months": "3",
        "direction": "long",
        "falsifier": "output rises while the constraint is said to bind",
    }
    s.update(over)
    return s


# ------------------------------------------------------------------ schema

def test_schema_round_trips_and_names_its_licence():
    sch = SB.scenario_schema()
    assert sch["schema_version"] == SB.SCHEMA_VERSION
    assert sch["licence"] == "PRODUCT_EXPERIMENT"
    json.dumps(sch)                       # must be serialisable, not just built
    names = {f["name"] for f in sch["fields"]}
    for required in ("event_type", "actors", "company_role", "sector_theme",
                     "demand_change", "supply_change", "capacity_constraint",
                     "holder_action", "analyst_change", "price_state",
                     "attention_state", "expected_horizon_months", "direction",
                     "falsifier"):
        assert required in names, f"schema lost the {required!r} field"


def test_schema_carries_no_number_the_model_could_see():
    """The BANDS live in code; the prompt must not contain a numeric guard.

    House rule of 2026-08-30: a bound the model can see is an anchor -- eleven
    of thirteen answers came back at exactly the stated bound.
    """
    prompt = SB._SYSTEM + SB._user_prompt("Manufacturing", "a bottleneck", "SB-X")
    digits = [c for c in prompt if c.isdigit()]
    # "12_1" and the horizon options are STRUCTURAL names, not guards; nothing
    # resembling a quantile or a threshold may appear.
    assert all(d in "1236" for d in digits), (
        f"a numeric guard leaked into the prompt: {sorted(set(digits))}")
    for band_group in SB._BANDS.values():
        for lo, hi in band_group.values():
            for v in (lo, hi):
                assert f"{v}" not in prompt, f"band edge {v} leaked into the prompt"


def test_validate_accepts_good_and_refuses_near_misses():
    ok, errs = SB.validate_scenario(a_scenario())
    assert ok, errs

    bad, errs = SB.validate_scenario(a_scenario(demand_change="increasing"))
    assert not bad and any("demand_change" in e for e in errs), (
        "a near-miss enum value must be an ERROR, not silently coerced")

    bad, errs = SB.validate_scenario(a_scenario(actors=[]))
    assert not bad

    s = a_scenario()
    del s["falsifier"]
    bad, errs = SB.validate_scenario(s)
    assert not bad and any("falsifier" in e for e in errs)

    s = a_scenario(price_state={"drawdown_state": "very_deep",
                                "momentum_12_1_sign": "positive"})
    bad, errs = SB.validate_scenario(s)
    assert not bad

    assert SB.validate_scenario("not a dict")[0] is False
    assert SB.validate_scenario(None)[0] is False


def test_public_administration_is_not_an_offerable_sector():
    """A scenario may never map onto the label that means SIC 9999 unclassified."""
    assert "Public Administration" not in SB.ENUMS["sic_division_hint"]
    assert SB.UNCLASSIFIED_SECTOR not in SB.ENUMS["sic_division_hint"]


# ------------------------------------------------------------------ mapping

def test_mappability_counts_proxies_separately_from_direct():
    m = SB.mappability_summary()
    assert m["direct"] + m["proxy"] + m["coarse"] + m["unmappable"] == m["retrieval_fields"]
    assert m["direct_rate"] < m["any_mapping_rate"], (
        "the headline rate must be DIRECT only; folding proxies in would "
        "overstate what the panel can actually express")
    assert m["unmappable"] > 0, "if nothing is unmappable the field map is lying"


def test_the_unmappable_list_names_the_acquisition_targets():
    _, rep = SB.scenario_predicates(a_scenario())
    un = set(rep["unmappable_fields"])
    for concept in ("demand_change", "supply_change", "capacity_constraint",
                    "company_role", "actors", "event_type"):
        assert concept in un


def test_activist_and_insider_holder_actions_are_refused_not_faked():
    for v in ("activist_stake", "insider_buying", "insider_selling"):
        builders, rep = SB.scenario_predicates(a_scenario(holder_action=v))
        assert "holder_action" not in builders
        assert f"holder_action={v}" in rep["unmappable_fields"], (
            "13D/G and Form 4 are not in the panel; pretending the 13F "
            "aggregate covers them would be a proxy with no name on it")


def test_a_dropped_predicate_is_reported_as_dropped():
    s = a_scenario(attention_state="neglected", holder_action="institutional_accumulation")
    full, rep_full = SB.scenario_predicates(s)
    assert "attention_state" in full and "holder_action" in full

    dropped, rep = SB.scenario_predicates(s, drop=("attention_state",))
    assert "attention_state" not in dropped
    assert "attention_state" in rep["predicates_dropped_by_backoff"]
    assert "attention_state" not in rep["predicates_used"]


# ------------------------------------------------------------------ retrieval

def test_retrieval_selects_the_band_and_nothing_else():
    p = tiny_panel()
    s = a_scenario(price_state={"drawdown_state": "deep_drawdown",
                                "momentum_12_1_sign": "unknown"})
    r = SB.retrieve(p, s, k=5)
    assert r["status"] == "RETRIEVED"
    t = p.iloc[r["treated_index"]]
    lo, hi = SB._BANDS["drawdown_state"]["deep_drawdown"]
    assert (t["drawdown_60d__xs"] >= lo).all() and (t["drawdown_60d__xs"] < hi).all()
    assert (t["sector"] == "Manufacturing").all(), "the sector stratum was not applied"
    assert len(r["exemplars"]) == 5


def test_controls_share_the_strata_and_exclude_the_treated():
    p = tiny_panel()
    s = a_scenario()
    r = SB.retrieve(p, s, k=3)
    t = p.iloc[r["treated_index"]]
    c = p.iloc[r["control_index"]]
    assert not set(r["treated_index"]) & set(r["control_index"])
    cols = ["month", "sector", "size_tercile", "liq_tercile"]
    tk = set(map(tuple, t[cols].itertuples(index=False, name=None)))
    ck = set(map(tuple, c[cols].itertuples(index=False, name=None)))
    assert ck <= tk, "a control outside a treated stratum is a different question"


def test_no_analogue_is_a_finding_not_a_zero():
    p = tiny_panel()
    # A configuration nothing in the fixture satisfies: the panel's drawdown and
    # coverage ranks are perfectly correlated, so at_highs AND neglected is empty.
    s = a_scenario(price_state={"drawdown_state": "at_highs",
                                "momentum_12_1_sign": "unknown"},
                   attention_state="neglected")
    r = SB.retrieve(p, s, k=5)
    assert r["status"] == "NO_ANALOGUE"
    assert r["n_treated"] == 0
    g = SB.grade(p, r)
    assert g["status"] == "NO_ANALOGUE"
    assert "spread_gross" not in json.dumps(g)


def test_a_scenario_with_no_observable_state_is_refused_not_scored():
    """Zero predicates means every control IS a treated row.

    The difference would be 0.000 BY CONSTRUCTION -- arithmetically correct and
    about nothing. The scenario named no state this panel holds, and that is the
    answer it gets.
    """
    p = tiny_panel()
    s = a_scenario(attention_state="unknown", holder_action="unknown",
                   analyst_change="none",
                   price_state={"drawdown_state": "unknown",
                                "momentum_12_1_sign": "unknown"})
    r = SB.retrieve(p, s, k=3)
    assert r["status"] == "NO_OBSERVABLE_STATE"
    assert r["mapping"]["n_predicates"] == 0
    g = SB.grade(p, r)
    assert g["status"] == "NO_OBSERVABLE_STATE"
    assert "spread_gross" not in json.dumps(g)


# ------------------------------------------------------------------ grading

def test_no_outcome_without_a_real_row():
    """THE RULE THIS FILE EXISTS FOR: a synthetic scenario gets no synthetic return."""
    p = tiny_panel(all_targets_nan=True)
    s = a_scenario()
    r = SB.retrieve(p, s, k=5)
    assert r["status"] == "RETRIEVED"
    g = SB.grade(p, r)
    # Every horizon must report NO_MATCHED_STRATA -- a mean over all-NaN is not
    # a zero, and a zero here would be an invented outcome.
    for h in SB.HORIZONS:
        cell = g["horizons"][str(h)]
        assert cell["status"] == "NO_MATCHED_STRATA", cell


def test_grade_refuses_below_the_evidence_floor():
    p = tiny_panel(n_months=6, n_names=40)          # 6 < MIN_MONTH_BLOCKS
    r = SB.retrieve(p, a_scenario(), k=3)
    g = SB.grade(p, r)
    assert g["status"] == "REFUSED_TOO_THIN"
    assert g["floors"]["min_month_blocks"] == SB.MIN_MONTH_BLOCKS
    assert "spread_gross" not in json.dumps(g)


def test_grade_finds_the_planted_effect_and_charges_the_cost():
    p = tiny_panel(n_months=40, n_names=150)
    s = a_scenario()                                 # deep_drawdown => planted +5%
    r = SB.retrieve(p, s, k=5)
    g = SB.grade(p, r, direction="long")
    assert g["status"] == "GRADED"
    cell = g["horizons"]["3"]
    assert cell["spread_gross"] > 0.02, cell
    expected_cost = 2 * SB.COST_BPS_ROUND_TRIP_PER_LEG / 10_000.0
    assert cell["cost_charged"] == pytest.approx(expected_cost)
    assert cell["spread_net"] == pytest.approx(cell["spread_gross"] - expected_cost,
                                               abs=1e-9)
    assert cell["n_month_blocks"] <= 40, "n_effective must count DATE BLOCKS, not rows"
    assert cell["n_treated_rows"] > cell["n_month_blocks"], (
        "the fixture should have many rows per month -- otherwise the pairing "
        "test is not testing pairing")


def test_direction_only_flips_a_sign_it_never_creates_one():
    p = tiny_panel(n_months=40, n_names=150)
    s = a_scenario()
    r = SB.retrieve(p, s, k=3)
    lo = SB.grade(p, r, direction="long")["horizons"]["3"]["spread_gross"]
    sh = SB.grade(p, r, direction="short")["horizons"]["3"]["spread_gross"]
    assert lo == pytest.approx(-sh, abs=1e-9), (
        "the model's direction may only reverse a number computed from realised "
        "returns; it must never be able to change its magnitude")


def test_the_floor_binds_on_the_matched_set_not_the_retrieved_one():
    """The defect this test exists for, found in the first live run.

    SB-20260903-18 retrieved 233 treated rows over 120 month blocks -- clearing
    both floors -- and then reported a t of 1.78 computed from SIX month blocks
    and SIX treated rows, because only six strata ever held enough controls to
    difference against. The floor had been checked on a quantity that was not
    the quantity being reported, which is a check that did not run.
    """
    p = tiny_panel(n_months=40, n_names=150)
    # Make controls almost impossible: a band so narrow that each stratum holds
    # a treated row and hardly anything else.
    lo, hi = SB._BANDS["drawdown_state"]["near_lows"]
    s = a_scenario(price_state={"drawdown_state": "near_lows",
                                "momentum_12_1_sign": "negative"},
                   attention_state="neglected",
                   holder_action="institutional_distribution",
                   analyst_change="targets_cut")
    r = SB.retrieve(p, s, k=3)
    if r["status"] != "RETRIEVED":
        pytest.skip("fixture produced no analogue; the floor path is untested here")
    g = SB.grade(p, r)
    for h, cell in g["horizons"].items():
        if cell["status"] == "GRADED":
            assert cell["n_month_blocks"] >= SB.MIN_MONTH_BLOCKS, cell
            assert cell["n_treated_rows"] >= SB.MIN_TREATED_ROWS, cell
        elif cell["status"] == "REFUSED_TOO_THIN_AFTER_MATCHING":
            assert "spread_gross" not in cell
            assert cell["n_treated_retrieved"] >= cell["n_treated_rows"]


def test_backoff_relaxes_and_names_what_it_dropped():
    p = tiny_panel(n_months=40, n_names=60)
    # Four predicates at once over 60 names is too thin at level 0 here.
    s = a_scenario(attention_state="spiking",
                   holder_action="institutional_distribution",
                   analyst_change="targets_cut",
                   price_state={"drawdown_state": "near_lows",
                                "momentum_12_1_sign": "negative"})
    ret, g = SB.retrieve_and_grade(p, s, k=3)
    assert "backoff_attempts" in ret
    levels = [a["level"] for a in ret["backoff_attempts"]]
    assert levels == sorted(levels), "the ladder must be walked in order"
    assert g["backoff_level"] == len(g["backoff_dropped"])
    if g["backoff_level"]:
        assert list(SB.BACKOFF_ORDER[:g["backoff_level"]]) == g["backoff_dropped"]


def test_losers_are_measured_against_winners_not_ignored():
    p = tiny_panel(n_months=40, n_names=150)
    r = SB.retrieve(p, a_scenario(), k=3)
    lo = r["losers"]
    assert lo.get("n_losers", 0) > 0 and lo.get("n_winners", 0) > 0
    assert lo["loser_mean_excess"] < lo["winner_mean_excess"]
    assert "ratio__xs" in lo["winner_minus_loser_feature_means"], (
        "the RAW ratio carries the stale-target-across-a-split outlier; the "
        "within-month rank is what belongs in a mean")


# ------------------------------------------------------------------ PIT

def test_the_13f_public_date_is_the_statutory_deadline_not_the_quarter_end():
    for qidx in (72, 100, 119):
        qe = SB.quarter_end(qidx)
        pub = SB.public_date_of(qidx)
        assert (pub - qe).days == SB.FILING_LAG_DAYS
        assert pub > qe, "using the quarter end would be look-ahead by 45 days"
    assert SB.quarter_end(0) == date(1995, 3, 31), "qidx 0 must be 1995Q1"
    assert SB.quarter_end(119) == date(2024, 12, 31)


def test_json_extraction_survives_a_fenced_reply():
    obj = SB._extract_json('```json\n{"a": 1}\n```')
    assert obj == {"a": 1}
    assert SB._extract_json('here you go: {"a": 2} hope that helps') == {"a": 2}
    assert SB._extract_json("no json here") is None
    assert SB._extract_json("{not valid}") is None


# ------------------------------------------------------------------ disagreement

def test_disagreement_splits_predicate_fields_from_narrative(tmp_path):
    """The split is the finding, so it must be computed, not eyeballed."""
    a = {"kind": "scenario", "scenario_id": "X-1",
         **{k: v for k, v in a_scenario().items()}}
    a["scenario_id"] = "X-1"
    b = dict(a)
    b["analyst_change"] = "targets_cut"          # a PREDICATE field: disagree
    b["price_state"] = {"drawdown_state": "at_highs",
                        "momentum_12_1_sign": "positive"}
    line_b = {"kind": "second_opinion", "scenario_id": "X-1", "mode": "cross_model",
              "model": "test/model-b", "parsed": b}
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join([json.dumps(a), json.dumps(line_b), ""]),
                 encoding="utf-8")

    d = SB.disagreement_summary(f)
    assert d["status"] == "MEASURED" and d["n_pairs"] == 1
    assert d["predicate_fields"]["rate"] < d["non_predicate_fields"]["rate"], (
        "the fixture disagrees only on predicate fields; the split must show it")
    assert set(d["predicate_fields"]["fields"]) == set(SB.PREDICATE_FIELDS)
    assert SB.disagreement_summary(tmp_path / "absent.jsonl")["status"] == "NO_FILE"
