"""THE ROI RULE — what it scores, what it refuses, and what it may never move.

`backend/services/roi_rank.py` (chunk 18c, spec
`docs/research_notes/2026-09-20/spec_decision_engine_and_scenario_gym.md` §B).

The load-bearing test in this file is not any of the arithmetic ones: it is
`test_every_measured_row_has_a_receipt_on_disk`. The whole rule rests on the
claim that `config.SIGNAL_MEASURED_RETURN`'s numbers were MEASURED, and the
only mechanical version of that claim is that each row names a file this
checkout actually has. A number whose receipt has moved, been archived or never
existed is prose with a filename, and it would be sizing real positions.

Everything else is offline and synthetic: a hand-built table, hand-built
`Recommendation`s, no funnel, no network, no LLM.
"""

from __future__ import annotations

import copy
import json

import pytest

from backend import config
from backend.services import decision_contract as DC
from backend.services import investment_committee as IC
from backend.services import roi_rank
from backend.services.recommendation import Recommendation, SignalContribution


# ── fixtures: a table with a receipt that exists, and recs with a leader ─────

def _table(**over):
    """A synthetic measured table. `README.md` is used as the receipt because
    the receipt only has to EXIST for these tests; the real table's real paths
    are checked by their own test against the real config."""
    def row(pct, t, n=419, t_basis="a t on the net return"):
        return {"monthly_net_pct": pct, "t": t, "t_basis": t_basis,
                "n_blocks": n, "net_basis": "synthetic fixture",
                "receipt": "README.md", "measured_on": "2026-09-13"}

    base = {
        "strong_signal": row(0.50, 3.10),
        "weak_t_signal": row(0.90, 1.07),
        "negative_signal": row(-0.30, 4.00),
        "quiet_signal": row(0.20, 2.40),
        "no_return_t_signal": row(
            0.80, "CANNOT DETERMINE: the receipt states a rank IC t",
            t_basis="an IC t is a statistic about the ORDER, not the return."),
    }
    base.update(over)
    return base


def _rec(ticker, signal=None, *, score=1.0, verdict="BUY", conf="MEDIUM",
         grade="SUPPORTED", rank=1, price=20.0):
    r = Recommendation(ticker=ticker, rank=rank, ranking_score=score,
                       confidence=conf, evidence_grade=grade, price=price)
    r.recommendation = verdict
    r.reason_for_rank = f"led by {signal}"
    if signal:
        r.signal_contributions = [SignalContribution(
            signal_id=signal, role="PICKER", grade="SUPPORTED", raw_value=1.0,
            weight=0.7, contribution=0.5, rank_bearing=True, basis="test")]
    return r


def _cands(recs, vol=0.45):
    return {r.ticker: {"price": r.price, "vol_annual": vol,
                       "median_dollar_vol": 5e7} for r in recs}


@pytest.fixture()
def measured(monkeypatch):
    monkeypatch.setattr(config, "SIGNAL_MEASURED_RETURN", _table(),
                        raising=False)
    monkeypatch.setattr(config, "IC_ROI_RANKING", True, raising=False)
    # CHUNK 18c's world, deliberately: mu from the family row, downside from
    # the ticker's vol. Chunk 22 (2026-09-21) moved both INPUTS and gated
    # EXPLOIT on a CALIBRATED decile map; `ROI_USE_CALIBRATION = False`
    # restores this file's subject byte for byte, and the chunk-22 behaviour is
    # tested in `test_signal_calibration.py` against a map planted in tmp_path.
    monkeypatch.setattr(config, "ROI_USE_CALIBRATION", False, raising=False)
    return _table()


# ===========================================================================
# THE CLAIM THE WHOLE RULE RESTS ON
# ===========================================================================


def test_every_measured_row_has_a_receipt_on_disk():
    """No number without a receipt, and no receipt without a file.

    This is the test that fails when somebody adds a return by hand, or when a
    document that carried one is archived to a new path.
    """
    table = getattr(config, "SIGNAL_MEASURED_RETURN", {})
    assert isinstance(table, dict)
    checks = roi_rank.table_receipts()
    missing = {sig: row["receipt"] for sig, row in checks.items()
               if not row["exists"]}
    assert not missing, (
        f"SIGNAL_MEASURED_RETURN rows whose receipt is not in this checkout: "
        f"{missing}. A measured return whose receipt has moved is a number "
        f"nobody can check, and it would be sizing positions.")


def test_every_measured_row_carries_every_required_field():
    """Each row is a number, a t (or a NAMED absence of one), and a basis.

    `t` and `n_blocks` may be `CANNOT DETERMINE: ...` — several of this repo's
    receipts state a monthly net return beside a rank IC t, which is a
    statistic about the ordering and not about the return. What may never
    happen is a bare hole: the basis field has to say which it is.
    """
    for sig in getattr(config, "SIGNAL_MEASURED_RETURN", {}):
        row = roi_rank.measured_return(sig)       # raises if a field is missing
        assert row is not None
        assert isinstance(float(row["monthly_net_pct"]), float)
        for key in ("t", "n_blocks"):
            value = row[key]
            if isinstance(value, str):
                assert value.startswith("CANNOT DETERMINE:"), (
                    f"{sig}.{key} is prose without being a named absence")
            else:
                assert float(value) == float(value)
        assert len(str(row["t_basis"])) > 20
        assert len(str(row["net_basis"])) > 20


def test_a_row_missing_a_field_is_refused_not_used(monkeypatch):
    monkeypatch.setattr(config, "SIGNAL_MEASURED_RETURN",
                        {"bad": {"monthly_net_pct": 1.0, "t": 9.0,
                                 "t_basis": "x", "net_basis": "y",
                                 "n_blocks": 10, "measured_on": "2026-09-20"}},
                        raising=False)
    with pytest.raises(roi_rank.MeasuredReturnError) as exc:
        roi_rank.measured_return("bad")
    assert "receipt" in str(exc.value)


def test_a_receipt_that_states_no_return_t_can_never_rank(measured):
    recs = [_rec("NOT", "no_return_t_signal", rank=1)]
    out = roi_rank.rank(recs, candidates=_cands(recs))
    assert not out.is_scored("NOT")
    why = out.not_calibrated["NOT"]
    assert "NO t on that return" in why and "IC t" in why


def test_only_registry_pickers_carry_a_row():
    """A FILTER or SHELF signal with an expected return would be a filter
    licensed to lead the order — the exact defect `recommendation.py` exists
    to prevent. So the table may only name signals the registry permits as
    PICKERs."""
    from backend.services import signal_registry as SR

    reg = SR.load()
    for sig in getattr(config, "SIGNAL_MEASURED_RETURN", {}):
        assert reg.permits(sig, "PICKER"), (
            f"{sig} carries a measured expected return but the registry does "
            f"not permit it to lead a ranking")


def test_a_closed_signal_has_no_row():
    """A signal the registry closed must never carry a measured return here."""
    table = getattr(config, "SIGNAL_MEASURED_RETURN", {})
    for closed in ("analyst_target_upside_xs", "analyst_target_level_haircut",
                   "momentum_12_1"):
        assert closed not in table, (
            f"{closed} is CLOSED/REJECTED in the signal registry and may not "
            f"carry an expected return that could size a position")


# ===========================================================================
# THE PARTITION: SCORED vs NOT_CALIBRATED
# ===========================================================================


def test_scored_and_not_calibrated_partition(measured):
    recs = [_rec("AAA", "strong_signal", rank=1),
            _rec("BBB", "no_such_signal", rank=2),
            _rec("CCC", None, rank=3)]
    out = roi_rank.rank(recs, candidates=_cands(recs))
    assert out.is_scored("AAA")
    assert set(out.not_calibrated) == {"BBB", "CCC"}
    assert "no measured net forward return is on file" in out.not_calibrated["BBB"]
    assert "no rank-bearing licensed signal" in out.not_calibrated["CCC"]
    # every un-scored row names the FIELD it is missing, first
    for text in out.not_calibrated.values():
        assert text.startswith("NOT_CALIBRATED: ")


def test_a_candidate_below_min_t_is_not_ranked(measured):
    """'It can't be sure, so it doesn't make one' — printed, not silent."""
    recs = [_rec("SLOW", "weak_t_signal", rank=1)]
    out = roi_rank.rank(recs, candidates=_cands(recs))
    assert not out.is_scored("SLOW")
    why = out.not_calibrated["SLOW"]
    assert "confidence" in why and "1.07" in why
    assert f"{config.ROI_MIN_T:.2f}" in why


def test_a_negative_measured_return_is_not_ranked(measured):
    recs = [_rec("DOWN", "negative_signal", rank=1)]
    out = roi_rank.rank(recs, candidates=_cands(recs))
    assert not out.is_scored("DOWN")
    assert "not positive" in out.not_calibrated["DOWN"]


def test_missing_volatility_refuses_the_downside(measured):
    recs = [_rec("NOVOL", "strong_signal", rank=1)]
    cands = {"NOVOL": {"price": 20.0, "vol_annual": None}}
    out = roi_rank.rank(recs, candidates=cands)
    assert not out.is_scored("NOVOL")
    assert "downside" in out.not_calibrated["NOVOL"]


def test_lower_volatility_scores_higher_at_the_same_signal(measured):
    """The ratio is the point: same return, calmer name, better ROI."""
    calm = _rec("CALM", "strong_signal", rank=1)
    wild = _rec("WILD", "strong_signal", rank=2)
    cands = {"CALM": {"price": 20.0, "vol_annual": 0.20},
             "WILD": {"price": 20.0, "vol_annual": 0.80}}
    out = roi_rank.rank([calm, wild], candidates=cands)
    assert out.rows["CALM"]["roi_score"] > out.rows["WILD"]["roi_score"]
    assert out.rows["CALM"]["roi_rank"] == 1
    assert out.weights["CALM"] > out.weights["WILD"]


def test_expected_return_scales_linearly_with_the_horizon(measured):
    er12, _, _ = roi_rank.expected_return_net("strong_signal", horizon_months=12)
    er24, _, _ = roi_rank.expected_return_net("strong_signal", horizon_months=24)
    assert er12 == pytest.approx(0.005 * 12)
    assert er24 == pytest.approx(2 * er12)


# ===========================================================================
# TOP-K, THE CAPS, AND THE WORST CASE
# ===========================================================================


def test_top_k_and_caps_hold(measured):
    n = config.IC_MAX_TILT_NAMES + 7
    recs = [_rec(f"T{i:02d}", "strong_signal", rank=i + 1) for i in range(n)]
    out = roi_rank.rank(recs, candidates=_cands(recs))
    assert len(out.admitted) == config.IC_MAX_TILT_NAMES
    assert len(out.weights) <= config.IC_MAX_TILT_NAMES
    assert all(w <= config.IC_SINGLE_NAME_TILT_CAP + 1e-9
               for w in out.weights.values())
    assert sum(out.weights.values()) <= config.IC_TOTAL_TILT_BUDGET + 1e-9
    # the names that scored but lost the K cut say so by name
    ranked_out = [t for t, why in out.not_calibrated.items()
                  if "ranked out" in why]
    assert len(ranked_out) == n - config.IC_MAX_TILT_NAMES


def test_measured_names_are_ordered_ahead_of_unmeasured_for_a_scarce_slot(measured):
    recs = ([_rec(f"U{i:02d}", "no_such_signal", rank=i + 1)
             for i in range(config.IC_MAX_TILT_NAMES)]
            + [_rec("MEASURED", "strong_signal", rank=99)])
    out = roi_rank.rank(recs, candidates=_cands(recs))
    assert out.admitted[0].ticker == "MEASURED"
    assert len(out.admitted) == config.IC_MAX_TILT_NAMES


def test_a_cap_breach_is_refused_not_trimmed():
    with pytest.raises(roi_rank.CapBreach):
        roi_rank._refuse_cap_breach({"AAA": 0.9}, cap=0.03, budget=0.10)
    with pytest.raises(roi_rank.CapBreach):
        roi_rank._refuse_cap_breach({"A": 0.03, "B": 0.03, "C": 0.03,
                                     "D": 0.03}, cap=0.03, budget=0.10)


def test_personalities_are_kelly_fractions_and_never_raise_the_cap(measured):
    weights = {}
    for name in config.ROI_KELLY_FRACTION_BY_PERSONALITY:
        recs = [_rec("AAA", "strong_signal", rank=1)]
        out = roi_rank.rank(recs, candidates=_cands(recs), personality=name)
        weights[name] = out.weights["AAA"]
        assert out.weights["AAA"] <= config.IC_SINGLE_NAME_TILT_CAP + 1e-9
    assert weights["preservation"] <= weights["balanced"] <= weights["aggressive"]


def test_an_unknown_personality_falls_back_and_says_so():
    frac, basis = roi_rank.kelly_fraction_for("reckless")
    assert frac == config.ROI_KELLY_FRACTION_BY_PERSONALITY[
        config.ROI_DEFAULT_PERSONALITY]
    assert "not one of the declared personalities" in basis


def test_the_worst_case_the_contract_prints_does_not_move(measured):
    """The rule may resize a tilt; it may not enlarge the admissible book."""
    before = DC.largest_admissible_book()
    recs = [_rec(f"T{i:02d}", "strong_signal", rank=i + 1) for i in range(20)]
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=_cands(recs))
    after = DC.largest_admissible_book()
    assert before == after
    assert book["tilt_weight"] <= config.IC_TOTAL_TILT_BUDGET + 1e-9
    for p in book["positions"]:
        if p["source"] == "evidence-led":
            assert p["weight"] <= config.IC_SINGLE_NAME_TILT_CAP + 1e-9


# ===========================================================================
# THE WIRING, AND THE FLAG
# ===========================================================================


def test_compose_book_carries_the_roi_block_when_scored(measured):
    recs = [_rec("AAA", "strong_signal", rank=1)]
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=_cands(recs))
    tilt = [p for p in book["positions"] if p["source"] == "evidence-led"][0]
    assert tilt["roi"]["roi_rank"] == 1
    assert tilt["roi"]["roi_basis"] == "README.md"
    assert "fractional Kelly" in tilt["sizing"]
    assert book["roi_ranking"]["n_scored"] == 1


def test_contract_rows_carry_roi_or_the_named_absence(measured, tmp_path):
    recs = [_rec("AAA", "strong_signal", rank=1),
            _rec("BBB", "no_such_signal", rank=2),
            _rec("CCC", "strong_signal", rank=3, verdict="HOLD")]
    cands = _cands(recs)
    state = {"available": True, "recs": recs, "candidates": cands,
             "funnel_generated_at": "2026-09-20T00:00:00+00:00"}
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=cands)
    rows = DC._ic_rows(state, book, asof=__import__("datetime").date(2026, 9, 20),
                       capital=1_000_000.0)
    by = {r["ticker"]: r for r in rows}
    assert by["AAA"]["roi"] == "SCORED"
    assert by["AAA"]["roi_basis"] == "README.md"
    assert by["AAA"]["roi_score"] > 0
    assert by["BBB"]["roi"].startswith("NOT_CALIBRATED: expected_return_net")
    # A name the HARD gate refused never reaches the rule, and says so. Its
    # DIRECTION is PROBE from chunk 23a-ii — a HOLD verdict is an absence of a
    # view, so the name keeps a zero-weight virtual row instead of vanishing —
    # and the ROI block is unchanged: the rule still never saw it.
    assert by["CCC"]["direction"] == "PROBE"
    assert by["CCC"]["position_budget"]["weight"] == 0.0
    assert "not considered" in by["CCC"]["roi"]
    blob = DC.payload(rows, asof=__import__("datetime").date(2026, 9, 20),
                      book=book)
    assert blob["roi_ranking"]["n_rows_scored"] == 1
    assert blob["roi_ranking"]["n_rows_not_calibrated_by_missing_field"]


def test_the_rule_never_turns_a_refused_into_a_buy(measured):
    """A hard-gate refusal with a wonderful measured signal stays refused."""
    recs = [_rec("NOEV", "strong_signal", rank=1, grade="NO_EVIDENCE"),
            _rec("HOLD", "strong_signal", rank=2, verdict="HOLD"),
            _rec("ZERO", "strong_signal", rank=3, score=0.0)]
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=_cands(recs))
    assert not [p for p in book["positions"] if p["source"] == "evidence-led"]


def _comparable(book: dict) -> str:
    """Everything the ROI rule could have touched, canonically. `wealth` is a
    Monte Carlo and is excluded — it is downstream of the weights, so a change
    in it without a change here would be a change in numpy, not in the rule."""
    return json.dumps({k: v for k, v in book.items() if k != "wealth"},
                      sort_keys=True, default=str)


def test_flag_off_reproduces_todays_output_byte_for_byte(monkeypatch):
    """The revert must be a flag flip, not an archaeology exercise.

    Two claims, both mechanical: with `IC_ROI_RANKING` off the measured table
    cannot leak into the book at all (a full table and an empty one produce the
    same bytes), and every tilt weight is exactly today's
    `cap x verdict x confidence`.
    """
    recs = [_rec("AAA", "strong_signal", rank=1),
            _rec("BBB", "strong_signal", rank=2, verdict="WATCH", conf="LOW")]
    cands = _cands(recs)

    monkeypatch.setattr(config, "IC_ROI_RANKING", False, raising=False)
    monkeypatch.setattr(config, "SIGNAL_MEASURED_RETURN", _table(), raising=False)
    off_full = IC.compose_book(copy.deepcopy(recs), capital=1_000_000.0,
                               candidates=cands)
    monkeypatch.setattr(config, "SIGNAL_MEASURED_RETURN", {}, raising=False)
    off_empty = IC.compose_book(copy.deepcopy(recs), capital=1_000_000.0,
                                candidates=cands)
    assert _comparable(off_full) == _comparable(off_empty)

    assert "roi_ranking" not in off_full
    for p in off_full["positions"]:
        assert "roi" not in p and "sizing" not in p
    w = {p["ticker"]: p["weight"] for p in off_full["positions"]
         if p["source"] == "evidence-led"}
    assert w["AAA"] == pytest.approx(
        config.IC_SINGLE_NAME_TILT_CAP * 1.0 * (2 / 3))
    assert w["BBB"] == pytest.approx(
        config.IC_SINGLE_NAME_TILT_CAP * 0.5 * (1 / 3))

    monkeypatch.setattr(config, "SIGNAL_MEASURED_RETURN", _table(), raising=False)
    monkeypatch.setattr(config, "IC_ROI_RANKING", True, raising=False)
    on = IC.compose_book(copy.deepcopy(recs), capital=1_000_000.0,
                         candidates=cands)
    assert "roi_ranking" in on
    assert _comparable(on) != _comparable(off_full)
