"""The decision contract's ONE mandate and its candidate-set census (review 2026-09-26).

R4: the 09-26 contract said `capital_usd: 40000` and priced its worst case on
$1,000,000; four per-name caps (2% / 3% / 10% / 12%) bound one account and the
largest reachable book was 1.00x gross with no stop. The mandate block prints
ONE capital base, ONE per-name cap (the tightest), the worst case in dollars,
and REFUSES when the bases or caps disagree instead of picking one silently.

R5: `roi_ranking.n_considered` read 2 for seven days beside a 25-name funnel.
It is the POST-gate count; the receipt now carries the pre-gate set's source,
size and age beside it.

No test reads this machine's data: the PC-PAPER equity seam is replaced.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend import config
from backend.services import decision_contract as DC


@pytest.fixture(autouse=True)
def no_local_equity(monkeypatch):
    monkeypatch.setattr(DC, "pc_paper_equity", lambda: None)


# ─────────────────────────────── the mandate ────────────────────────────────

def test_disagreeing_capital_bases_and_caps_are_refused_by_name():
    m = DC.account_mandate(40_000.0, equity={"equity_usd": 999_054.0,
                                             "as_of": "t", "source": "fixture"})
    assert m["status"] == "REFUSED"
    kinds = {r.split(":", 1)[0] for r in m["refusals"]}
    assert {"CAPITAL_BASES_DISAGREE", "PER_NAME_CAPS_DISAGREE"} <= kinds
    # ONE base, ONE cap, both printed
    assert m["capital_usd"] == 40_000.0
    assert m["per_name_cap"] == min(m["per_name_caps_seen"].values())
    assert m["line"].startswith("MANDATE REFUSED: capital $40,000; per-name cap")
    # the worst case is in dollars, on the one base, and on the largest seen
    c = m["largest_admissible_book_as_configured"]
    assert c["worst_case_no_stop_usd"] == pytest.approx(-c["gross_over_equity"] * 40_000.0)
    assert c["on_largest_base_seen"]["equity_usd"] == pytest.approx(1_000_000.0)
    assert "sum|notional|/equity" in m["line"] and "-$" in m["line"]


def test_the_limits_themselves_are_not_changed():
    before = (config.IC_SINGLE_NAME_TILT_CAP, config.PROBE_MAX_WEIGHT,
              config.ER_EXPLOIT_MAX_WEIGHT, config.PROBE_GROSS_CAP,
              config.IC_TOTAL_TILT_BUDGET)
    DC.account_mandate(40_000.0, equity=None)
    assert before == (config.IC_SINGLE_NAME_TILT_CAP, config.PROBE_MAX_WEIGHT,
                      config.ER_EXPLOIT_MAX_WEIGHT, config.PROBE_GROSS_CAP,
                      config.IC_TOTAL_TILT_BUDGET)


def test_an_agreeing_mandate_is_ok(monkeypatch):
    monkeypatch.setattr(DC, "per_name_caps", lambda: {"one cap": 0.10})
    monkeypatch.setattr(DC, "gross_caps", lambda: {"one gross": 1.0})
    top = max(float(c) for c in config.IC_CAPITAL_LEVELS)
    m = DC.account_mandate(top, equity={"equity_usd": top, "as_of": "t", "source": "f"})
    assert m["status"] == "OK" and m["refusals"] == []
    assert m["line"].startswith("MANDATE OK")


def test_the_worst_case_block_is_priced_on_the_contract_capital():
    w = DC.largest_admissible_book(40_000.0)
    assert w["equity_usd"] == 40_000.0
    assert DC.largest_admissible_book()["equity_usd"] == max(
        float(c) for c in config.IC_CAPITAL_LEVELS)


# ─────────────────────────────── the candidates ─────────────────────────────

def _rec(t, verdict, grade, score):
    return SimpleNamespace(ticker=t, recommendation=verdict, evidence_grade=grade,
                           ranking_score=score)


def test_the_candidate_set_prints_every_hop_with_size_and_age(tmp_path):
    gen = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")
    recs = ([_rec(f"H{i}", "HOLD", "SUPPORTED", -0.1) for i in range(16)]
            + [_rec(f"N{i}", "NO_ACTION", "NO_EVIDENCE", 0.0) for i in range(7)]
            + [_rec("SON", "WATCH", "SUPPORTED", 0.2), _rec("ALLE", "WATCH", "SUPPORTED", 0.15)])
    state = {"funnel_generated_at": gen, "recs": recs,
             "candidates": {r.ticker: {} for r in recs}}
    book = {"roi_ranking": {"n_considered": 2}}
    cs = DC.candidate_set(state, book, funnel_path=tmp_path / "funnel.json")
    assert cs["n_candidates"] == 25 and cs["n_considered"] == 2
    assert cs["candidates_generated_at"] == gen
    assert cs["candidates_age_days"] == pytest.approx(2.0, abs=0.1)
    assert cs["excluded_by_gate"] == {"ranking score <= 0": 16,
                                      "no licensed evidence (NO_EVIDENCE)": 7}
    assert cs["line"].startswith("candidates 25 (funnel.json, generated")


def test_the_receipt_carries_the_pre_gate_set_beside_n_considered():
    cands = {"candidates_source": "funnel_night10.json", "n_candidates": 25,
             "candidates_generated_at": "2026-01-01T00:00:00+00:00", "line": "x"}
    blob = DC.payload([], asof=date.today(), capital=40_000.0,
                      book={"roi_ranking": {"n_considered": 2}}, candidates=cands)
    rr = blob["roi_ranking"]
    assert rr["n_considered"] == 2
    assert rr["candidates_source"] == "funnel_night10.json"
    assert rr["n_candidates"] == 25
    assert rr["candidates_generated_at"] == "2026-01-01T00:00:00+00:00"
    assert blob["candidate_set"] is cands
    assert blob["mandate"]["line"].startswith("MANDATE")
    assert blob["worst_case_largest_admissible_book"]["equity_usd"] == 40_000.0


def test_a_writer_that_passes_no_candidate_set_says_cannot_determine():
    blob = DC.payload([], asof=date.today(), capital=40_000.0, book=None)
    assert blob["candidate_set"]["line"].startswith("CANNOT DETERMINE")
