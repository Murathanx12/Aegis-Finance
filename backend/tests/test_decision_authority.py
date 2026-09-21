"""EXPLOIT / EXPLORE / REFUSED — the authority split (chunk 21).

`backend/services/decision_authority.py`, roadmap §15.2, from Murat's review of
2026-09-20: *"the ROI rule scored 0 of 43 while the old heuristic still says BUY
four ... EXPLOIT and EXPLORE ... do not require t >= 2 before AEGIS is allowed
to learn."*

The load-bearing test in this file is
`test_no_row_carries_a_budget_without_an_authority`: the whole point of the
chunk is that a BUY with no measured ROI stops existing as a third kind of
thing, and the mechanical version of that claim is that every row with a
position budget names the authority that licensed it.

Everything here is offline and synthetic: a hand-built measured table,
hand-built `Recommendation`s, `tmp_path` for every write, no funnel, no
network, no LLM, and nothing reads `backend/data`.
"""

from __future__ import annotations

import copy
import json
from datetime import date

import pytest

from backend import config
from backend.services import decision_authority as DA
from backend.services import decision_contract as DC
from backend.services import investment_committee as IC
from backend.services.recommendation import Recommendation, SignalContribution

ASOF = date(2026, 9, 20)


# ── fixtures ────────────────────────────────────────────────────────────────

def _row(pct, t, n=419, t_basis="a t on the net return"):
    return {"monthly_net_pct": pct, "t": t, "t_basis": t_basis,
            "n_blocks": n, "net_basis": "synthetic fixture",
            "receipt": "README.md", "measured_on": "2026-09-13"}


def _table(**over):
    base = {
        # clears ROI_MIN_T -> EXPLOIT
        "calibrated": _row(0.50, 3.10),
        # measured, positive, unproven -> EXPLORE
        "unproven": _row(0.17, 1.40),
        # measured, positive, no t at all -> EXPLORE with the widest posterior
        "no_t": _row(0.241, "CANNOT DETERMINE: the receipt states a rank IC t",
                     t_basis="an IC t is about the ORDER, not the return"),
        # measured and NEGATIVE -> refused, never explored
        "negative": _row(-0.30, 1.10),
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


@pytest.fixture(autouse=True)
def _empty_probe_panel(monkeypatch):
    """No test in this file may read the repository's real decision ledger.

    `assign` consults the PROBE panel (chunk 23a) for every name whose leading
    signal has no measured row, and the default path is
    `backend/data/optimus/decisions/ledger.jsonl`. A suite that read it would
    be a suite whose result depends on how many virtual rows this machine has
    graded — so the DEFAULT path reads nothing here, and the tests that are
    ABOUT the panel plant their own ledger in `tmp_path` and are untouched.
    """
    real = DA.probe_panel.scored_probe_rows

    def guarded(path=None, **kw):
        if path is None:
            return []
        return real(path, **kw)

    monkeypatch.setattr(DA.probe_panel, "scored_probe_rows", guarded,
                        raising=True)


@pytest.fixture()
def measured(monkeypatch):
    monkeypatch.setattr(config, "SIGNAL_MEASURED_RETURN", _table(),
                        raising=False)
    monkeypatch.setattr(config, "IC_ROI_RANKING", True, raising=False)
    monkeypatch.setattr(config, "IC_LEGACY_HEURISTIC_SIZING", False,
                        raising=False)
    # CHUNK 21's world, deliberately. Chunk 22 (2026-09-21) tightened the
    # EXPLOIT gate to require a CALIBRATED decile map on disk and gave EXPLORE
    # a decile posterior; every test below describes the behaviour BEFORE that,
    # which `ROI_USE_CALIBRATION = False` restores byte for byte. The chunk-22
    # behaviour is `test_signal_calibration.py`, which plants its own map in
    # tmp_path and never reads `backend/data`.
    monkeypatch.setattr(config, "ROI_USE_CALIBRATION", False, raising=False)
    return _table()


def _book(recs, capital=1_000_000.0, **kw):
    return IC.compose_book(recs, capital=capital, candidates=_cands(recs),
                           asof=ASOF, **kw)


# ===========================================================================
# THE CLAIM THE CHUNK MAKES
# ===========================================================================


def test_no_row_carries_a_budget_without_an_authority(measured):
    """Murat's inconsistency, as a gate: no BUY without EXPLOIT or EXPLORE.

    Every direction that allocates a budget must name the authority that
    licensed it. A row that carries dollars and no authority is precisely the
    'four heuristic BUYs with an ROI of zero' state this chunk exists to end.
    """
    recs = [_rec("AAA", "calibrated", rank=1),
            _rec("BBB", "unproven", rank=2),
            _rec("CCC", "nothing_measured", rank=3),
            _rec("DDD", "negative", rank=4)]
    cands = _cands(recs)
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=cands,
                           asof=ASOF)
    state = {"available": True, "recs": recs, "candidates": cands,
             "funnel_generated_at": "2026-09-20T00:00:00+00:00"}
    rows = DC._ic_rows(state, book, asof=ASOF, capital=1_000_000.0)
    assert rows
    for r in rows:
        assert r["authority"] in DA.AUTHORITIES
        budget = (r.get("position_budget") or {}).get("weight") or 0.0
        if r["direction"] in ("BUY", "WATCH") or budget > 0:
            assert r["authority"] in DA.ACTIVE_AUTHORITIES, r["ticker"]
        if r["authority"] == DA.REFUSED:
            assert budget == 0.0
    blob = DC.payload(rows, asof=ASOF, book=book)
    assert blob["authority"]["rows_with_a_budget_and_no_authority"] == []


def test_the_verdict_times_confidence_buy_is_retired(measured):
    """The exact state the review refused: a BUY with no measured ROI.

    `HIGH` confidence and a `BUY` verdict used to size 3% of the book through
    `cap x verdict x confidence`. With no measured read for its leading signal
    it now receives nothing, and the row says which field was missing.
    """
    recs = [_rec("HEUR", "nothing_measured", rank=1, conf="HIGH")]
    book = _book(recs)
    assert not [p for p in book["positions"] if p["source"] == "evidence-led"]
    # CHUNK 23a: it receives no capital, and it is no longer REFUSED either —
    # an unmeasured name is PROBED at zero weight so the measurement it lacks
    # can accrue. The capital claim this test exists for is unchanged.
    assert book["authority"]["n_refused"] == 0
    assert book["authority"]["n_probe"] == 1
    assert book["authority"]["probe_tickers"] == ["HEUR"]
    assert book["probe_weight"] == 0.0
    why = book["authority"]["probe_basis"]["HEUR"]
    assert "NO measured read exists" in why
    assert "PROBED at zero capital" in why

    # ... and the legacy flag brings it back, unchanged, as a one-line revert.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "IC_LEGACY_HEURISTIC_SIZING", True, raising=False)
        legacy = _book([_rec("HEUR", "nothing_measured", rank=1, conf="HIGH")])
    tilt = [p for p in legacy["positions"] if p["source"] == "evidence-led"]
    assert tilt and tilt[0]["weight"] == pytest.approx(
        config.IC_SINGLE_NAME_TILT_CAP)
    assert "authority" not in legacy


# ===========================================================================
# EXPLOIT
# ===========================================================================


def test_a_calibrated_signal_is_exploit_and_is_kelly_sized(measured):
    recs = [_rec("AAA", "calibrated", rank=1)]
    book = _book(recs)
    pos = [p for p in book["positions"] if p["source"] == "evidence-led"][0]
    assert pos["authority"] == DA.EXPLOIT
    assert pos["weight"] == pytest.approx(book["roi_ranking"]["rows_by_ticker"]
                                          ["AAA"]["kelly_weight"])
    assert "fractional Kelly" in pos["sizing"]
    assert "roi_score" in pos["roi"]
    assert book["exploit_weight"] > 0 and book["explore_weight"] == 0


def test_exploit_is_printed_empty_when_nothing_is_calibrated(measured):
    """Today's real state, and it must read as a finding rather than a gap."""
    recs = [_rec("BBB", "unproven", rank=1)]
    book = _book(recs)
    assert book["authority"]["n_exploit"] == 0
    assert book["authority"]["exploit_tickers"] == []
    assert book["authority"]["n_explore"] == 1


# ===========================================================================
# EXPLORE — the posterior, the draw, the seed, the budget
# ===========================================================================


def test_an_unproven_measured_read_is_explored_not_frozen(measured):
    """t 1.40 is not proven and is not equivalent to zero (Murat, verbatim)."""
    recs = [_rec("BBB", "unproven", rank=1)]
    book = _book(recs)
    pos = [p for p in book["positions"] if p["source"] == "evidence-led"][0]
    assert pos["authority"] == DA.EXPLORE
    assert pos["weight"] == pytest.approx(config.EXPLORE_PER_NAME_PCT)
    ex = pos["explore"]
    # the posterior, the draw, the score and the seed are all PRINTED
    assert ex["posterior_mean_pct_per_month"] == pytest.approx(0.17)
    assert ex["posterior_se_pct_per_month"] == pytest.approx(0.17 / 1.40,
                                                             abs=5e-7)
    assert isinstance(ex["thompson_seed"], int)
    assert "exploration_score" in ex and "thompson_draw_pct_per_month" in ex
    assert ex["cost_pct_per_month"] > 0
    assert ex["risk_penalty_pct_per_month"] > 0
    assert ex["uncertainty_bonus_pct_per_month"] > 0
    assert ex["exploration_score"] == pytest.approx(
        ex["thompson_draw_pct_per_month"] - ex["cost_pct_per_month"]
        - ex["risk_penalty_pct_per_month"]
        + ex["uncertainty_bonus_pct_per_month"], rel=1e-9)


def test_an_unmeasured_t_is_the_widest_posterior_never_a_zero(measured):
    """`CANNOT DETERMINE` on the t must widen the posterior, not fail."""
    mean, se, basis = DA.posterior(_table()["no_t"])
    assert se == pytest.approx(config.EXPLORE_UNKNOWN_T_SE_MULT * abs(mean))
    assert "WIDEST posterior" in basis
    tight, se_tight, _ = DA.posterior(_table()["unproven"])
    assert se > se_tight


def test_exploration_is_for_measured_but_unproven_never_for_nothing(measured):
    """Two refusals that must stay refusals, and one PROBE that must not be.

    The two REFUSALS are EVIDENCE — a measured read that is not positive, and
    a name whose risk penalty cannot be computed. The third is the chunk-23a
    distinction: `NONE` has no measurement at all, which is not evidence about
    the mechanism and must not be recorded as though it were.
    """
    recs = [_rec("NONE", "nothing_measured", rank=1),
            _rec("NEG", "negative", rank=2),
            _rec("NOVOL", "unproven", rank=3)]
    cands = _cands(recs)
    cands["NOVOL"]["vol_annual"] = None
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=cands,
                           asof=ASOF)
    ref = book["authority"]["refused"]
    assert "NONE" not in ref
    assert "NO measured read exists" in book["authority"]["probe_basis"]["NONE"]
    assert "not above EXPLORE_MIN_NET_PCT" in ref["NEG"]
    assert "no usable annualised volatility" in ref["NOVOL"]
    assert not [p for p in book["positions"] if p["source"] == "evidence-led"]


def test_the_paper_risk_budget_is_a_ceiling_not_a_guide(measured):
    """Nine candidates, eight slots: the ninth is refused BY NAME with a score."""
    n = int(config.EXPLORE_BUDGET_PCT / config.EXPLORE_PER_NAME_PCT) + 1
    recs = [_rec(f"E{i:02d}", "unproven", rank=i + 1) for i in range(n)]
    book = _book(recs)
    split = book["authority"]
    assert split["n_explore"] == n - 1
    assert split["explore_weight_total"] == pytest.approx(
        config.EXPLORE_BUDGET_PCT)
    assert book["explore_weight"] <= config.EXPLORE_BUDGET_PCT + 1e-12
    last = [d for d in split["explore_rows"] if d["authority"] == DA.REFUSED]
    assert len(last) == 1
    assert "budget is a ceiling" in split["refused"][last[0]["ticker"]]
    # ranked by exploration score, best first — the budget goes to the top
    scores = [d["exploration_score"] for d in split["explore_rows"]]
    assert scores == sorted(scores, reverse=True)


# ===========================================================================
# DETERMINISM — a receipt that cannot be reproduced is not a receipt
# ===========================================================================


def test_the_draw_is_seeded_from_the_asof_date_and_the_name(measured):
    recs = [_rec("BBB", "unproven", rank=1)]
    a = _book(copy.deepcopy(recs))["authority"]["explore_rows"][0]
    b = _book(copy.deepcopy(recs))["authority"]["explore_rows"][0]
    assert a["thompson_seed"] == b["thompson_seed"]
    assert a["thompson_draw_pct_per_month"] == b["thompson_draw_pct_per_month"]

    other = IC.compose_book(copy.deepcopy(recs), capital=1_000_000.0,
                            candidates=_cands(recs), asof=date(2026, 9, 21))
    c = other["authority"]["explore_rows"][0]
    assert c["thompson_seed"] != a["thompson_seed"]


def test_adding_a_candidate_does_not_move_another_candidates_draw(measured):
    one = [_rec("BBB", "unproven", rank=1)]
    two = [_rec("BBB", "unproven", rank=1), _rec("CCC", "no_t", rank=2)]
    a = _book(one)["authority"]["explore_rows"][0]
    rows = {d["ticker"]: d for d in _book(two)["authority"]["explore_rows"]}
    assert rows["BBB"]["thompson_draw_pct_per_month"] == pytest.approx(
        a["thompson_draw_pct_per_month"])


# ===========================================================================
# THE WORST CASE — session protocol rule 4, printed rather than remembered
# ===========================================================================


def test_explore_adds_at_most_its_budget_to_the_worst_case(measured):
    before = DC.largest_admissible_book()
    n = int(config.EXPLORE_BUDGET_PCT / config.EXPLORE_PER_NAME_PCT) + 4
    recs = ([_rec(f"X{i:02d}", "calibrated", rank=i + 1) for i in range(12)]
            + [_rec(f"E{i:02d}", "unproven", rank=100 + i) for i in range(n)])
    cands = _cands(recs)
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=cands,
                           asof=ASOF)
    assert DC.largest_admissible_book() == before          # the cap never moves
    assert book["exploit_weight"] <= config.IC_TOTAL_TILT_BUDGET + 1e-9
    assert book["explore_weight"] <= config.EXPLORE_BUDGET_PCT + 1e-12
    assert book["tilt_weight"] <= (config.IC_TOTAL_TILT_BUDGET
                                   + config.EXPLORE_BUDGET_PCT + 1e-9)
    state = {"available": True, "recs": recs, "candidates": cands,
             "funnel_generated_at": "2026-09-20T00:00:00+00:00"}
    rows = DC._ic_rows(state, book, asof=ASOF, capital=1_000_000.0)
    blob = DC.payload(rows, asof=ASOF, book=book)
    worst = blob["worst_case_explore_budget"]
    assert worst["worst_case_pct_of_equity"] <= config.EXPLORE_BUDGET_PCT
    assert "ADDS to the tilt worst case" in worst["verdict"]


def test_capacity_and_one_share_still_return_an_explored_name_to_the_core(
        measured):
    """The two post-sizing gates keep biting under the new authorities.

    They were pinned against `cap x verdict x confidence` weights
    (`test_investment_committee.py`, now on the legacy flag); an explored name
    is a much SMALLER weight, so both gates had to be re-checked at the size
    they now see rather than assumed to carry over.
    """
    thin = _rec("THIN", "unproven", rank=1, price=5.0)
    book = IC.compose_book([thin], capital=1_000_000.0,
                           candidates={"THIN": {"price": 5.0,
                                                "vol_annual": 0.6,
                                                "median_dollar_vol": 100.0}},
                           asof=ASOF)
    assert all(p["source"] == "benchmark-core" for p in book["positions"])
    assert any("untradeable" in d for d in book["degradation_reasons"])

    dear = _rec("DEAR", "unproven", rank=1, price=5_000.0)
    book = IC.compose_book([dear], capital=10_000.0,
                           candidates={"DEAR": {"price": 5_000.0,
                                                "vol_annual": 0.4,
                                                "median_dollar_vol": 5e7}},
                           asof=ASOF)
    assert all(p["source"] == "benchmark-core" for p in book["positions"])
    assert any("below one share" in d for d in book["degradation_reasons"])


def test_a_calibrated_name_outranked_by_exploit_is_not_explored(measured,
                                                                monkeypatch):
    """The paper-risk budget resolves UNPROVEN reads, never proven ones.

    Without this, a calibrated signal that lost the last EXPLOIT slot would
    collect exploration money as a consolation — spending the information
    budget on a hypothesis that has no information left to buy.
    """
    monkeypatch.setattr(config, "IC_MAX_TILT_NAMES", 2, raising=False)
    recs = [_rec(f"C{i:02d}", "calibrated", rank=i + 1) for i in range(5)]
    book = _book(recs)
    split = book["authority"]
    assert split["n_exploit"] == 2
    assert split["n_explore"] == 0
    left_out = split["refused"]
    assert len(left_out) == 3
    assert all("does not fund a proven one" in v for v in left_out.values())


def test_the_split_can_never_admit_a_name_the_hard_gates_refused(measured):
    recs = [_rec("NOEV", "calibrated", rank=1, grade="NO_EVIDENCE"),
            _rec("HOLD", "unproven", rank=2, verdict="HOLD"),
            _rec("ZERO", "unproven", rank=3, score=0.0)]
    book = _book(recs)
    assert not [p for p in book["positions"] if p["source"] == "evidence-led"]
    assert book["authority"]["n_considered"] == 0


# ===========================================================================
# THE FILE ON DISK
# ===========================================================================


def test_the_contract_file_carries_the_split_and_reproduces(measured, tmp_path,
                                                            monkeypatch):
    recs = [_rec("AAA", "calibrated", rank=1), _rec("BBB", "unproven", rank=2),
            _rec("CCC", "nothing_measured", rank=3)]
    cands = _cands(recs)
    state = {"available": True, "recs": recs, "candidates": cands,
             "funnel_generated_at": "2026-09-20T00:00:00+00:00"}
    monkeypatch.setattr(DC, "funnel_state", lambda *a, **k: state)
    monkeypatch.setattr(DC, "agency_options", lambda asof: ([], ""))
    DC.build_daily_contracts(asof=ASOF, capital=40_000.0, out_dir=tmp_path,
                             write=True)
    blob = json.loads((tmp_path / "2026-09-20.json").read_text("utf-8"))
    by = {r["ticker"]: r for r in blob["rows"]}
    assert by["AAA"]["authority"] == DA.EXPLOIT
    assert by["BBB"]["authority"] == DA.EXPLORE
    assert by["BBB"]["explore"]["thompson_seed"] == DA.seed_for(
        "2026-09-20", "BBB", "unproven")
    assert by["CCC"]["authority"] == DA.PROBE
    assert blob["authority"]["count_by_authority_over_rows"][DA.EXPLORE] == 1
    assert blob["count_by_direction"]["BUY"] >= 1


# ===========================================================================
# PROBE — chunk 23a. Zero capital, a virtual graded row, a hypothesis id.
# ===========================================================================


def _scored_probe(hypothesis_id, *, horizon=5, months=8, per_month=5,
                  excess=0.01):
    """A synthetic ledger of SCORED PROBE rows, `months` x `per_month` of them.

    Shaped exactly like what `decision_ledger.score_due` writes, because the
    panel's whole job is to read that shape back.
    """
    rows = []
    for m in range(months):
        for i in range(per_month):
            day = f"2026-{(m % 12) + 1:02d}-{i + 1:02d}"
            # The excess VARIES by month on purpose: a fixture whose every
            # month carries the same mean has a block-bootstrap se of exactly
            # zero, and the panel refuses that read by name rather than
            # printing a certainty it does not have.
            e = excess + 0.001 * i + 0.002 * (m - (months - 1) / 2.0)
            rows.append({
                "state": "SCORED", "decision_id": f"{hypothesis_id}-{m}-{i}",
                "asof": day,
                "detail": {"direction": "PROBE",
                           "hypothesis_id": hypothesis_id,
                           "horizon_sessions": horizon,
                           "ticker": f"T{i}",
                           "realised_return": e + 0.02,
                           "benchmark_return": 0.02,
                           "excess_return": e},
            })
    return rows


def _ledger(tmp_path, rows):
    path = tmp_path / "ledger.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                    encoding="utf-8")
    return path


def test_a_name_with_no_measured_read_is_probed_at_four_horizons(measured,
                                                                  tmp_path):
    """Spec test 1: PROBE, four rows, a hypothesis id, weight zero.

    And the claim the whole state rests on: the capital resolution is
    bit-identical to the one the same book produces with the PROBE names
    removed. A row that resolved a dollar would not be a probe.
    """
    recs = [_rec("AAA", "unproven", rank=1),
            _rec("NEW", "nothing_measured", rank=2)]
    cands = _cands(recs)
    state = {"available": True, "recs": recs, "candidates": cands,
             "funnel_generated_at": "2026-09-18T00:00:00+00:00"}
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=cands,
                           asof=ASOF,
                           information_set="2026-09-18T00:00:00+00:00")
    rows = DC._ic_rows(state, book, asof=ASOF, capital=40_000.0)
    probe = [r for r in rows if r["direction"] == "PROBE"]
    assert len(probe) == len(config.PROBE_HORIZONS_SESSIONS)
    assert {r["horizon_sessions"] for r in probe} == set(
        config.PROBE_HORIZONS_SESSIONS)
    assert len({r["decision_id"] for r in probe}) == len(probe), (
        "four rows about one name on one day must be four decisions; one id "
        "would make three of the four grades unwritable by the ledger's own "
        "idempotence rule")
    for r in probe:
        assert r["ticker"] == "NEW"
        assert r["authority"] == DA.PROBE
        assert r["hypothesis_id"] and len(r["hypothesis_id"]) == 12
        assert r["hypothesis_id_basis"]
        assert r["position_budget"]["weight"] == 0.0
        assert r["position_budget"]["dollars"] == 0.0
        assert r["position_budget"]["virtual"] is True
        assert r["position_budget"]["virtual_notional_usd"] == \
            config.PROBE_VIRTUAL_NOTIONAL_USD
        assert r["maximum_loss"]["worst_case_usd"] == 0.0
        assert r["expiry_utc"] and "sessions" in r["expiry_basis"]
        assert r["selection_probability"] == 1.0
        assert r["context_features"]["signal"]

    # the capital resolution, with and without the PROBE rows
    with_probe = DC.capital_resolution(rows, capital=40_000.0)
    without = DC.capital_resolution(
        [r for r in rows if r["direction"] != "PROBE"], capital=40_000.0)
    vector = ("benchmark_pct", "active_exploit_pct", "active_explore_pct",
              "cash_pct", "sums_to", "dollars")
    assert {k: with_probe[k] for k in vector} == {k: without[k] for k in vector}
    assert with_probe["probe_pct"] == 0.0
    assert with_probe["probe_count"] == len(probe)
    assert DA.PROBE not in DA.ACTIVE_AUTHORITIES


def test_a_measured_but_nonpositive_read_is_still_refused(measured):
    """Spec test 2. A measurement that says 'no' is EVIDENCE and stays REFUSED.

    PROBE is for the absence of a measurement, never for a measurement one
    dislikes — the moment it becomes the second thing, every negative result
    this programme has paid for can be re-opened by relabelling it.
    """
    recs = [_rec("NEG", "negative", rank=1)]
    book = _book(recs)
    split = book["authority"]
    assert split["n_probe"] == 0
    assert "not above EXPLORE_MIN_NET_PCT" in split["refused"]["NEG"]


def test_the_panel_is_measured_only_at_both_gates(tmp_path):
    """Spec test 3: 40 rows over 8 months is measured; over 2 months is not."""
    from backend.services import probe_panel as PP

    wide = _ledger(tmp_path, _scored_probe("hyp_wide", months=8, per_month=5))
    read = PP.read_for("hyp_wide", 5, path=wide)
    assert read is not None and read.measured is True
    assert read.n == 40 and read.n_blocks == 8
    assert read.mean_excess_pct == pytest.approx(100 * (0.01 + 0.002), abs=1e-6)
    assert read.se_pct is not None and read.se_pct > 0
    assert read.sign_hit_rate == 1.0
    assert read.n_excess == 40 and read.n_raw_fallback == 0

    narrow = _ledger(tmp_path / "n", _scored_probe("hyp_narrow", months=2,
                                                   per_month=20))
    thin = PP.read_for("hyp_narrow", 5, path=narrow)
    assert thin is not None and thin.measured is False
    assert thin.n == 40 and thin.n_blocks == 2
    assert any("MONTHS" in s for s in thin.shortfalls), thin.shortfalls
    assert not any("graded rows" in s for s in thin.shortfalls), (
        "40 rows clears PROBE_MIN_GRADED; only the BLOCK gate is short, and "
        "the two shortfalls ask for opposite work")
    assert PP.read_for("never_probed", 5, path=wide) is None


def test_a_measured_panel_read_reaches_EXPLORE_as_PROBE_PANEL(measured,
                                                              tmp_path):
    """Spec test 4 — the loop closing.

    A hypothesis that had no measurement built one out of its own graded
    virtual rows, and the name it leads is EXPLORE's today where it was PROBE
    yesterday. The posterior source says which of the three reads produced it.
    """
    recs = [_rec("NEW", "nothing_measured", rank=1)]
    cands = _cands(recs)
    hyp = DA.hypothesis_fields(recs[0], "nothing_measured",
                               information_set="2026-09-18T00:00:00+00:00",
                               asof=ASOF)
    path = _ledger(tmp_path, _scored_probe(hyp["hypothesis_id"], horizon=5,
                                           months=8, per_month=5))
    split = DA.assign(recs, candidates=cands, asof=ASOF,
                      information_set="2026-09-18T00:00:00+00:00",
                      probe_ledger_path=path)
    assert split.authority_for("NEW") == DA.EXPLORE
    block = split.blocks["NEW"]["explore"]
    assert block["posterior_source"] == DA.POSTERIOR_PROBE_PANEL
    assert block["probe_panel"]["measured"] is True
    assert block["posterior_mean_pct_per_month"] > 0
    assert "change of UNITS" in block["posterior_basis"]
    assert block["hypothesis_id"] == hyp["hypothesis_id"]

    # ... and with the panel two months short it stays PROBE, saying how short
    thin = _ledger(tmp_path / "thin",
                   _scored_probe(hyp["hypothesis_id"], horizon=5, months=2,
                                 per_month=3))
    still = DA.assign(recs, candidates=cands, asof=ASOF,
                      information_set="2026-09-18T00:00:00+00:00",
                      probe_ledger_path=thin)
    assert still.authority_for("NEW") == DA.PROBE
    assert "6 graded row(s)" in still.probe_basis["NEW"]


def test_the_selection_probability_sums_to_the_slots_and_reproduces(measured):
    """Spec test 5: sums to M, 1.0 on PROBE, deterministic for one as-of."""
    n = int(config.EXPLORE_BUDGET_PCT / config.EXPLORE_PER_NAME_PCT) + 4
    recs = ([_rec(f"E{i:02d}", "unproven", rank=i + 1) for i in range(n)]
            + [_rec("NEW", "nothing_measured", rank=99)])
    split = DA.assign(recs, candidates=_cands(recs), asof=ASOF)
    sel = split.receipt["selection_probability"]
    slots = split.receipt["explore_slots"]
    assert sel["slots"] == slots
    assert sum(sel["probability"].values()) == pytest.approx(slots, abs=0.05)
    assert all(0.0 <= p <= 1.0 for p in sel["probability"].values())
    for d in split.receipt["explore_rows"]:
        assert d["selection_probability"] == sel["probability"][d["ticker"]]
        assert d["selection_probability_basis"]
        assert d["action_set_sha256"] == split.receipt["action_set_sha256"]
    # a PROBE name never competes for a slot, so its propensity is exactly 1
    assert split.blocks["NEW"]["probe"]["selection_probability"] == 1.0

    again = DA.assign(recs, candidates=_cands(recs), asof=ASOF)
    assert (again.receipt["selection_probability"]["probability"]
            == sel["probability"])
    other = DA.assign(recs, candidates=_cands(recs), asof=date(2026, 9, 21))
    assert (other.receipt["selection_probability"]["seeds"]
            != sel["seeds"])
    # the action set is written ONCE, in full, and referenced by digest
    assert {a["ticker"] for a in split.receipt["action_set"]} == {
        d["ticker"] for d in split.receipt["explore_rows"]}


def test_the_probe_cap_trims_by_rank_and_the_refused_trim_does_not(
        measured, monkeypatch):
    """Spec test 7. MAX_REFUSED_ROWS must not touch the panel; its own cap must.

    The trim that keeps a file readable and the ceiling that bounds a panel are
    different decisions with different numbers, and a panel silently capped at
    50 would cap what the programme can ever measure.
    """
    monkeypatch.setattr(config, "PROBE_MAX_NAMES_PER_DAY", 3, raising=False)
    n = DC.MAX_REFUSED_ROWS + 10
    recs = [_rec(f"N{i:03d}", "nothing_measured", rank=i + 1)
            for i in range(n)]
    cands = _cands(recs)
    state = {"available": True, "recs": recs, "candidates": cands,
             "funnel_generated_at": "2026-09-18T00:00:00+00:00"}
    book = IC.compose_book(recs, capital=1_000_000.0, candidates=cands,
                           asof=ASOF,
                           information_set="2026-09-18T00:00:00+00:00")
    split = book["authority"]
    assert split["n_probe"] == 3
    assert split["probe_tickers"] == ["N000", "N001", "N002"], (
        "the cut is BY RANK: the names the funnel ranked best are the ones "
        "that get a virtual row")
    assert split["n_probe_cut_by_cap"] == n - 3
    rows = DC._ic_rows(state, book, asof=ASOF, capital=40_000.0)
    probe = [r for r in rows if r["direction"] == "PROBE"]
    assert len(probe) == 3 * len(config.PROBE_HORIZONS_SESSIONS)
    refused = [r for r in rows if r["direction"] == "REFUSED"]
    assert len(refused) == DC.MAX_REFUSED_ROWS
    blob = DC.payload(rows, asof=ASOF, capital=40_000.0, book=book)
    census = blob["authority"]
    assert census["probe_rows_written"] == len(probe)
    assert census["probe_rows_without_a_hypothesis_id"] == 0
    assert str(n - 3) in census["probe_rows_exempt_from_the_refused_trim"]
    assert blob["unclassified_owing_a_pattern"] == 0, (
        "the cap's refusal sentence needs a classify_refusal pattern; an "
        "unmatched sentence is work owed, not a typed answer")


def test_a_probe_row_cannot_be_written_without_a_hypothesis_id(measured,
                                                                caplog):
    """The panel joins on it; a row it cannot join is a cost with no return."""
    base = {"ticker": "NEW"}
    out = DC._probe_rows_for(base, {"probe": {}}, expiries={5: ("x", "y")},
                             capital=40_000.0, policy_id="P",
                             policy_version="V", asof=str(ASOF))
    assert out == []


def test_the_scoreboard_carries_the_probe_line(tmp_path):
    """The one line §16.1 needs: rows open / graded / hypotheses measured."""
    from backend.services import morning_scoreboard as MS

    ledger = _ledger(tmp_path, _scored_probe("hyp_board", months=8,
                                             per_month=5))
    board = MS.compose(asof=ASOF, out_dir=tmp_path / "decisions",
                       ledger_path=ledger, night_folder=tmp_path / "night",
                       replay_folder=tmp_path / "replay")
    panel = board["probe_panel"]
    assert panel["rows_graded"] == 40
    assert panel["hypotheses_measured"] == 1
    assert "PROBE panel:" in MS.render(board)
