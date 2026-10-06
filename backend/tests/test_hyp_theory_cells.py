"""CHUNK C12 (2026-10-06): the three $0 theory cells are DECLARED hyp_lab cells.

Pinned here:
* a cell refuses to run on a mutated declaration (hash mismatch), and the refusal is recorded;
* a declaration receipt is never overwritten;
* the RAM gate polls and refuses rather than competing;
* the insider "no sale within 90 days" flag uses only filings inside the window, and the entry
  gate is the day the absence becomes knowable (no look-ahead);
* the beat streak counts consecutive beats, resets on a miss and on a fiscal gap;
* the verdict vocabulary is CANDIDATE / FAILED_VARIANT / CANNOT_DISTINGUISH (never STOP), and a
  positive needs the leave-one-year-out worst to stay positive.

Offline, synthetic data; dates are built from a fixed synthetic calendar, never from today.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backend.services import hyp_lab as L
from scripts import hyp_theory_cells as T


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "OUT", tmp_path)
    monkeypatch.setattr(L, "LEDGER", tmp_path / "ledger.jsonl")
    return tmp_path


def test_declare_then_mutated_declaration_refuses_and_is_recorded(sandbox):
    assert T.part_declare("beat_streak", "TEST_RUN") == 0
    p = T.decl_path("beat_streak", "TEST_RUN")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert T.verify_declaration(doc) == (True, "ok")
    state = L.load_state()
    assert state[doc["hyp_id"]]["status"] == "DECLARED"
    # mutate the declared horizon after hashing
    doc["horizons"] = [5]
    p.write_text(json.dumps(doc), encoding="utf-8")
    ran = []
    rc = T.part_run("beat_streak", "TEST_RUN", ram_probe=lambda: ran.append(1) or 99.0, sleep=lambda s: None)
    assert rc == 2 and not ran, "a tampered declaration refuses before anything else runs"
    res = json.loads(T.result_path("beat_streak", "TEST_RUN").read_text(encoding="utf-8"))
    assert res["result"]["verdict"] == "REFUSED" and "hash mismatch" in res["result"]["reason"]
    h = L.load_state()[doc["hyp_id"]]
    assert h["status"] == "RUN" and h["verdict"] == "REFUSED"


def test_declaration_is_never_overwritten(sandbox):
    assert T.part_declare("beat_streak", "R1", ledger=False) == 0
    assert T.part_declare("beat_streak", "R1", ledger=False) == 2


def test_declaration_hash_covers_the_decision_rule(sandbox):
    body = T.declaration("insider_hold", "R2")
    body["sha256"] = T.sha_of(body)
    assert T.verify_declaration(body)[0]
    body["decision"] = body["decision"].replace("t >= 2", "t >= 1")
    assert not T.verify_declaration(body)[0]


def test_ram_gate_polls_then_refuses_without_competing():
    sleeps = []
    ok, gb = T.wait_for_ram(floor=4.0, poll_s=120, max_wait_s=0, probe=lambda: 2.5, sleep=sleeps.append)
    assert not ok and gb == 2.5
    vals = iter([3.0, 3.5, 4.2])
    ok, gb = T.wait_for_ram(floor=4.0, poll_s=120, max_wait_s=10_000, probe=lambda: next(vals), sleep=sleeps.append)
    assert ok and gb == 4.2 and sleeps == [120, 120]


def test_insider_hold_uses_only_sales_inside_the_window_and_gates_at_day_90():
    d0 = pd.Timestamp("2010-03-01")
    B = pd.DataFrame({"permno": [1, 2, 3, 3], "cik": ["a", "b", "c", "c"],
                      "pub": [d0, d0, d0, d0 + pd.Timedelta(days=30)]})
    S = pd.DataFrame({"permno": [1, 2, 3], "cik": ["a", "b", "zz"],
                      # permno 1: buyer sells on day 40 (SOLD); permno 2: buyer sells on day 91 (outside: HOLD)
                      # permno 3: a DIFFERENT insider sells (still HOLD for the buyers)
                      "pub": [d0 + pd.Timedelta(days=40), d0 + pd.Timedelta(days=91), d0 + pd.Timedelta(days=10)]})
    E = T.insider_hold_events(B, S).set_index("permno")
    assert E.loc[1, "hold"] == False  # noqa: E712
    assert E.loc[2, "hold"] == True  # noqa: E712
    assert E.loc[3, "hold"] == True  # noqa: E712
    assert (E["gate"] == d0 + pd.Timedelta(days=90)).all(), "entry gate = the day 'no sale' is knowable"
    assert len(E) == 3, "a repeat buy inside the quiet window is not a new event"


def test_insider_quiet_gap_is_measured_from_the_previous_buy():
    d0 = pd.Timestamp("2011-01-03")
    days = [d0 + pd.Timedelta(days=60 * k) for k in range(4)]     # a buy every 60 days: never 90 quiet
    B = pd.DataFrame({"permno": [7] * 4, "cik": ["x"] * 4, "pub": days})
    E = T.insider_hold_events(B, B.iloc[:0])
    assert len(E) == 1 and E["t"].iloc[0] == d0


def test_beat_streak_counts_resets_on_miss_and_on_gap():
    q = pd.DataFrame({"ticker": ["T"] * 7,
                      "pyear": [2010, 2010, 2010, 2010, 2011, 2011, 2012],
                      "pmon": [3, 6, 9, 12, 3, 6, 6],
                      "anndats": pd.date_range("2010-04-20", periods=7, freq="90D"),
                      "actual": [1.1, 1.2, 1.3, 1.0, 1.5, 1.6, 1.7],
                      "surpmean": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]})
    s = T.beat_streaks(q)["streak"].tolist()
    # beat beat beat MEET(no beat) beat beat | 12-month gap -> restart
    assert s == [1, 2, 3, 0, 1, 2, 1]
    assert T.streak_bucket(pd.Series([0, 1, 3, 9])).tolist() == ["miss", "1", "3", "5+"]


def _monthly(values_by_year: dict) -> pd.Series:
    idx, vals = [], []
    for y, v in values_by_year.items():
        for m in range(1, 13):
            idx.append(pd.Timestamp(year=y, month=m, day=1) - pd.Timedelta(days=1))
            vals.append(v + (0.001 if m % 2 else -0.001))
    return pd.Series(vals, index=pd.DatetimeIndex(idx))


SPLITS = {"design": ("2001-01-01", "2004-12-31"), "validate": ("2005-01-01", "2010-12-31"),
          "late": ("2011-01-01", "2012-12-31")}


def test_verdict_vocabulary_and_loo_guard():
    good = _monthly({y: 0.01 for y in range(2001, 2013)})
    r = T.read_series(good, SPLITS, "+1", 0.002)
    assert r["verdict"] == "CANDIDATE" and r["loo_worst"]["validate"] > 0
    bad = _monthly({y: -0.01 for y in range(2001, 2013)})
    assert T.read_series(bad, SPLITS, "+1", 0.002)["verdict"] == "FAILED_VARIANT"
    # design-fixed sign: a consistently negative series is read as its mirror
    r = T.read_series(bad, SPLITS, "design", 0.002)
    assert r["sign_applied"] == -1.0 and r["verdict"] == "CANDIDATE"
    for v in (r["verdict"],):
        assert v in T.VOCAB and v != "STOP"


def test_one_year_carrying_the_validate_mean_is_not_a_candidate():
    """Protocol item 11: everything else passes (design > 0, validate t >= 2, majority of years
    positive) but dropping one year takes the validate mean to <= 0 -> not a CANDIDATE."""
    design = {"mean_monthly": 0.004, "t_blocks": 2.5, "mde_monthly": 0.003, "years_positive": "4 of 4"}
    validate = {"mean_monthly": 0.005, "t_blocks": 2.3, "mde_monthly": 0.006, "years_positive": "4 of 6"}
    assert T.theory_verdict(design, validate, 0.001, 0.002)["verdict"] == "CANDIDATE"
    v = T.theory_verdict(design, validate, -0.0004, 0.002)
    assert v["verdict"] == "CANNOT_DISTINGUISH"
    assert any("leave-one-year-out" in f for f in v["fails"])
