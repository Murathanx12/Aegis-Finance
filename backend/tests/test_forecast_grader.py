"""THE FORECAST GRADER — the caller the resolver never had inside the pass.

MEASURED 2026-09-20 on the live ledger: 24,839 records, every one of them with
`resolved_at: null`, 17,614 of them past their resolution date and the oldest
since 2026-08-11. The resolution machine existed and was tested; no step of the
daily pass called it.

What is pinned here:

1. **a due record grades, from LOCAL bars** — no vendor, no network;
2. **every record that did NOT grade lands in a NAMED bucket**, one per reason,
   and the buckets are a CLOSED set;
3. **every mechanism is on the receipt even at zero.** A group that vanishes is
   a group nobody notices is missing, which is precisely how 17,614 records sat
   ungraded for six weeks while an hourly roll-up printed the number.

Every ledger is a `tmp_path` JSONL and every price panel is synthetic. Nothing
here reads `backend/data`, `night_factory_20*`, or the network.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from backend.services import forecast_grader as FG
from backend.services.belief_state import (Observable, append,
                                           make_prediction, read_predictions)


def _pred(**kw):
    base = dict(ticker="AAA", specialist="biotech",
                observable=Observable.RETURN_SIGN, horizon_days=20,
                probability=0.6, thesis="t", counter_thesis="c",
                next_observable="n", model="m", model_version="v",
                prompt="p", input_snapshot={"ticker": "AAA"})
    base.update(kw)
    return make_prediction(**base)


def _today() -> date:
    """Derived from the clock, never a literal (CLAUDE.md protocol 5)."""
    return datetime.now(timezone.utc).date()


def _made_at(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _bars(symbols=("AAA", "SPY"), n=400) -> pd.DataFrame:
    """The LOCAL bars parquet's own long shape: symbol, date, close.

    Long rather than wide on purpose — `local_price_fetch` is what turns one
    into the other, and a test that handed it a wide frame would not exercise
    the thing that can be wrong.
    """
    idx = pd.bdate_range(end=pd.Timestamp(_today()), periods=n)
    rng = np.random.default_rng(0)
    rows = []
    for i, s in enumerate(symbols):
        path = 100 * np.cumprod(1 + 0.002 + rng.normal(0, 0.005, n))
        rows.append(pd.DataFrame({"symbol": s, "date": idx, "close": path,
                                  "open": path, "high": path, "low": path,
                                  "volume": 1_000_000 + i}))
    return pd.concat(rows, ignore_index=True)


@pytest.fixture
def local_fetch():
    bars = _bars()
    return lambda t, s, e: FG.local_price_fetch(t, s, e, bars=bars)


# ── (1) a due record grades, off the local bars ─────────────────────────────


def test_a_due_record_grades_from_the_local_bars(tmp_path, local_fetch):
    led = tmp_path / "predictions.jsonl"
    append([_pred(made_at=_made_at(120))], led)

    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=tmp_path / "receipt.json")

    assert rec["newly_resolved"] == 1
    assert rec["totals"]["graded"] == 1
    row = read_predictions(led)[0]
    # the ledger's OWN convention, written by `belief_state.resolve_one`:
    # an outcome, a resolution date, a Brier and the realised return.
    assert row["outcome"] in (0, 1)
    assert row["resolved_at"] == str(_today())
    assert row["brier"] is not None
    assert "realised_return" in row["resolution_detail"]
    # `graded_by` is a fact about the RUN and lives on the receipt, not on
    # 24,839 rows that would each carry the same string.
    assert "forecast_grader" in rec["graded_by"]
    assert "resolve_one" in rec["graded_by"]


def test_the_local_panel_is_named_and_dated_on_the_receipt(tmp_path, local_fetch):
    led = tmp_path / "predictions.jsonl"
    append([_pred(made_at=_made_at(120))], led)
    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=tmp_path / "r.json")
    # `bars_source()` reads the REAL local panel; what matters is that the
    # receipt carries an answer either way and never omits the field.
    assert "bars" in rec and "available" in rec["bars"]
    assert rec["licence"] == "PRODUCT_EXPERIMENT"
    assert rec["llm_spend_usd"] == 0.0


def test_the_local_fetch_turns_long_bars_into_a_wide_close_panel():
    bars = _bars(symbols=("AAA", "BBB"))
    wide = FG.local_price_fetch(["AAA", "BBB", "NOPE"], "2020-01-01",
                                str(_today()), bars=bars)
    assert list(wide.columns) == ["AAA", "BBB"], (
        "a ticker with no local bars must be ABSENT, which is the contract "
        "the resolver already accounts for by name in `unpriceable`")
    assert wide.index.is_monotonic_increasing


# ── (2) one named refusal per reason ────────────────────────────────────────


def test_a_record_with_no_local_bars_is_NO_BAR_FOR_RESOLUTION_DATE(
        tmp_path, local_fetch):
    led = tmp_path / "predictions.jsonl"
    append([_pred(ticker="ZZZDARK", made_at=_made_at(120),
                  input_snapshot={"ticker": "ZZZDARK"})], led)

    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=tmp_path / "r.json")

    assert rec["newly_resolved"] == 0
    assert rec["totals"]["NO_BAR_FOR_RESOLUTION_DATE"] == 1
    assert rec["n_unpriceable_tickers"] == 1
    # the record is untouched: not graded, not voided, not dropped
    row = read_predictions(led)[0]
    assert row["outcome"] is None and row.get("void_reason") is None


def test_an_observable_no_grader_knows_is_MECHANISM_HAS_NO_GRADER():
    rec = {"prediction_id": "x", "ticker": "AAA", "observable": "vibes_improve",
           "resolves_after": str(_today() - timedelta(days=1)),
           "horizon_days": 20, "outcome": None}
    assert FG.bucket_of(rec, None, today=_today()) == "MECHANISM_HAS_NO_GRADER"
    assert FG.refusal_for(rec, None, today=_today()) == "MECHANISM_HAS_NO_GRADER"


@pytest.mark.parametrize("rec,why", [
    ({"ticker": "", "observable": "return_sign"}, "no ticker at all"),
    ({"ticker": "AAA", "observable": "abs_move_exceeds", "threshold": None},
     "a threshold observable with no threshold"),
    ({"ticker": "AAA", "observable": "beats_benchmark", "benchmark": None},
     "a relative observable with no benchmark"),
])
def test_a_record_missing_what_its_observable_needs_is_RECORD_LACKS_TARGET(
        rec, why):
    full = {"prediction_id": "x", "horizon_days": 20, "outcome": None,
            "resolves_after": str(_today() - timedelta(days=1)), **rec}
    assert FG.bucket_of(full, None, today=_today()) == "RECORD_LACKS_TARGET", why


def test_a_record_with_no_readable_resolution_date_is_not_parked_in_not_yet_due():
    """The one bucket that is not a finding must not absorb a broken record."""
    rec = {"prediction_id": "x", "ticker": "AAA", "observable": "return_sign",
           "horizon_days": 20, "outcome": None, "resolves_after": "never"}
    assert FG.bucket_of(rec, None, today=_today()) == "RECORD_LACKS_TARGET"


def test_a_record_whose_window_is_still_open_is_not_yet_due(tmp_path, local_fetch):
    led = tmp_path / "predictions.jsonl"
    append([_pred(made_at=_made_at(1), horizon_days=120)], led)
    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=tmp_path / "r.json")
    assert rec["totals"]["not_yet_due"] == 1
    assert rec["totals"]["graded"] == 0
    assert rec["n_still_refused"] == 0, (
        "a forecast that has not matured is not a refusal, and counting it as "
        "one would make the refusal headline meaningless")


def test_a_voided_record_stays_VOID_and_is_never_re_graded(tmp_path, local_fetch):
    led = tmp_path / "predictions.jsonl"
    append([_pred(made_at=_made_at(120))], led)
    rows = read_predictions(led)
    rows[0]["void_reason"] = "threshold given in percent, not a decimal fraction"
    led.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")

    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=tmp_path / "r.json")
    assert rec["totals"]["VOID"] == 1
    assert rec["totals"]["graded"] == 0
    assert read_predictions(led)[0]["outcome"] is None


def test_every_record_lands_in_exactly_one_bucket_of_the_closed_set(
        tmp_path, local_fetch):
    """The whole failure, inverted: 17,614 records were in NO bucket at all."""
    led = tmp_path / "predictions.jsonl"
    append([
        _pred(made_at=_made_at(120)),                                  # grades
        _pred(ticker="ZZZDARK", made_at=_made_at(120),
              input_snapshot={"ticker": "ZZZDARK"}),                   # no bar
        _pred(made_at=_made_at(1), horizon_days=120),                  # not due
    ], led)

    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=tmp_path / "r.json")

    assert set(rec["totals"]) == set(FG.BUCKETS)
    assert sum(rec["totals"].values()) == rec["n_records"] == 3


# ── (3) every mechanism on the receipt, including at zero ───────────────────


def test_the_receipt_lists_every_declared_mechanism_even_at_zero(
        tmp_path, local_fetch):
    led = tmp_path / "predictions.jsonl"
    append([_pred(made_at=_made_at(120))], led)

    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=tmp_path / "r.json")

    from backend.services.lab_decision_vs_reality import DECLARED_MECHANISMS
    for mech, _status, _what in DECLARED_MECHANISMS:
        assert mech in rec["counts_by_mechanism"], (
            f"{mech} wrote nothing and is therefore ABSENT from the receipt — "
            f"a group that vanishes is a group nobody notices is missing")
        assert set(rec["counts_by_mechanism"][mech]) == set(FG.BUCKETS)
    # and the mechanism that DID write is there with its real count
    assert rec["counts_by_mechanism"]["biotech"]["graded"] == 1


def test_the_mechanism_is_the_specialist_when_there_is_no_mechanism_id():
    """24,839 of 24,839 live records carry `specialist` and 11 carry
    `mechanism_id`. Reading only the new field would report the whole ledger as
    one mechanism of eleven."""
    assert FG.mechanism_of({"specialist": "skeptic"}) == "skeptic"
    assert FG.mechanism_of({"mechanism_id": "paper_book_v1",
                            "specialist": "skeptic"}) == "paper_book_v1"
    assert FG.mechanism_of({}) == "UNATTRIBUTED"


def test_the_receipt_is_written_where_the_night_folder_expects_it(
        tmp_path, local_fetch):
    led = tmp_path / "predictions.jsonl"
    append([_pred(made_at=_made_at(120))], led)
    out = tmp_path / "grade_forecasts_x.json"
    rec = FG.grade_due(path=led, today=_today(), price_fetch=local_fetch,
                       out=out)
    assert out.is_file() and rec["path"] == str(out)
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["receipt"] == "grade_forecasts"
    assert on_disk["stage"] == "pnl", (
        "an outcome written onto a forecast is what makes it evidence; nothing "
        "upstream may read it")
    assert on_disk["totals"] == rec["totals"]
    assert FG.receipt_path("2026-09-20").name == "grade_forecasts_2026-09-20.json"


# ── the step in the pass ────────────────────────────────────────────────────


def test_the_daily_pass_declares_the_step_after_the_cadence_pass():
    from scripts import daily_pass as DP

    steps = [s for s, _ in DP.STEPS]
    assert "grade_forecasts" in steps, (
        "the graders had no caller on this machine, which is why 17,614 "
        "records sat past due")
    assert steps.index("grade_forecasts") > steps.index("book_cadence"), (
        "the books write their forecast rows in the cadence pass; grading "
        "first would leave today's rows for tomorrow")
    assert DP.step_box_s("grade_forecasts") > 0
    assert DP._HANDLERS["grade_forecasts"] is DP.step_grade_forecasts


def test_the_step_reports_a_refusal_by_NAME_and_never_a_bare_zero(monkeypatch):
    from scripts import daily_pass as DP

    monkeypatch.setattr(DP, "grade_forecasts", lambda **kw: {
        "newly_resolved": 0, "resolver_status": "ok",
        "totals": {b: 0 for b in FG.BUCKETS} | {
            "NO_BAR_FOR_RESOLUTION_DATE": 12, "not_yet_due": 5},
        "n_records": 17, "bars": {"available": True},
        "licence": "PRODUCT_EXPERIMENT", "headline": "h"})

    row = DP.step_grade_forecasts({})
    assert row["status"] == "nothing_to_do", (
        "nothing resolved is NOT an `ok` with zeros — a card cannot tell those "
        "apart from a day on which everything was already graded")
    assert any("NO_BAR_FOR_RESOLUTION_DATE: 12" in r for r in row["refusals"])
    assert not any("not_yet_due" in r for r in row["refusals"])


def test_a_resolver_refusal_is_a_refused_row_and_not_an_error(monkeypatch):
    from scripts import daily_pass as DP

    monkeypatch.setattr(DP, "grade_forecasts", lambda **kw: {
        "newly_resolved": 0, "resolver_status": "REFUSED",
        "resolver_reason": "the campaign ledger is unreadable",
        "totals": {b: 0 for b in FG.BUCKETS},
        "n_records": 0, "licence": "PRODUCT_EXPERIMENT", "headline": "h"})

    row = DP.step_grade_forecasts({})
    assert row["status"] == "refused"
    assert "campaign ledger is unreadable" in row["refusals"][0]


def test_a_graded_run_is_an_ok_row_carrying_the_count(monkeypatch):
    from scripts import daily_pass as DP

    monkeypatch.setattr(DP, "grade_forecasts", lambda **kw: {
        "newly_resolved": 341, "resolver_status": "ok",
        "totals": {b: 0 for b in FG.BUCKETS} | {"graded": 341},
        "n_records": 341, "licence": "PRODUCT_EXPERIMENT", "headline": "h"})

    row = DP.step_grade_forecasts({})
    assert row["status"] == "ok" and row["rows"] == 341
