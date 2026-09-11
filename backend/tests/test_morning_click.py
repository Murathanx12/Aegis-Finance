"""The morning click (roadmap O5), pinned.

Three properties, and the reason each is a test rather than a convention:

1. **The step list is the PLAN, not the log.** The receipt carries one row per
   DECLARED step in declared order, whatever happened. A runner that appended
   only the steps that worked would produce a receipt in which a step that never
   ran is indistinguishable from a step that did not exist -- the exact defect
   `signal_reachability.py` was built for, one layer up.
2. **A network-less run refuses; it does not raise.** The fast suite blocks
   sockets, so "no network" is the condition this suite runs under anyway; the
   test asserts the SHAPE of the answer rather than hoping.
3. **A second click is run02.** Two mornings in one day is a fact about the day
   and the first receipt is the only evidence of what the first click saw.

Every external call is monkeypatched through the module-level indirections in
`services/morning.py`; nothing here touches the live ledger (`predictions.jsonl`
goes to `tmp_path`, per the suite's ledger guard) or the live receipts dir.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from backend.services import morning as M


@pytest.fixture()
def offline(monkeypatch, tmp_path):
    """Every outside call replaced by a refusal, the way a dead network looks."""
    def boom(*a, **k):
        raise OSError("network is unreachable (test)")

    monkeypatch.setattr(M, "fetch_gdelt", boom)
    monkeypatch.setattr(M, "fetch_stock_news", boom)
    monkeypatch.setattr(M, "refresh_paper_snapshot", boom)
    monkeypatch.setattr(M, "resolve_due", boom)
    monkeypatch.setattr(M, "run_all_lanes", lambda: {})
    monkeypatch.setattr(M, "lane_nav_series", lambda: {})
    monkeypatch.setattr(M, "corpus_dir", lambda: tmp_path / "no_corpus")
    return tmp_path


def _run(tmp_path, **kw):
    kw.setdefault("today", date(2026, 9, 11))
    kw.setdefault("out_dir", tmp_path / "morning")
    kw.setdefault("predictions_path", tmp_path / "predictions.jsonl")
    return M.run_morning(**kw)


def test_the_receipt_carries_every_declared_step_in_order(offline, tmp_path):
    r = _run(tmp_path)
    got = [row["step"] for row in r["steps"]]
    assert got == [s for s, _ in M.STEPS], got
    assert r["declared_steps"] == got
    for row in r["steps"]:
        assert row["status"] in M.STATUSES, row
        assert row["what"] and row["utc"]


def test_a_network_less_run_refuses_by_name_and_never_raises(offline, tmp_path):
    r = _run(tmp_path)
    rows = {row["step"]: row for row in r["steps"]}
    # news: every source failed -> a refusal that names them, not an exception
    assert rows["news_pull"]["status"] == "refused"
    assert "gdelt" in rows["news_pull"]["reason"].lower()
    assert rows["news_pull"]["kind"] == "dashboard_fetch_not_corpus"
    # digest: the corpus directory is named in the refusal
    assert rows["digest"]["status"] == "refused"
    assert "no_corpus" in json.dumps(rows["digest"])
    assert rows["digest"]["digest_spec_sha256"]
    # grading needs prices, and the row says so rather than vanishing
    assert rows["grade"]["status"] == "error"
    assert "OSError" in rows["grade"]["reason"]
    # ready summarises rather than declaring success over three refusals
    assert rows["ready"]["status"] == "ok"
    assert set(rows["ready"]["steps_that_did_not_run"]) >= {"news_pull", "digest", "grade"}


def test_the_digest_step_carries_the_frozen_r2_spec_hash(offline, tmp_path):
    """A morning digest built to a different recipe than the registered one is a
    different experiment; the hash is how a later reader can tell."""
    from backend.services.portfolio_intelligence.r2_trial import DIGEST_SPEC_SHA256

    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "digest")
    assert row["digest_spec_sha256"] == DIGEST_SPEC_SHA256


def test_a_second_run_the_same_day_is_run02_and_does_not_overwrite(offline, tmp_path):
    first = _run(tmp_path)
    second = _run(tmp_path)
    assert first["run"] == 1 and second["run"] == 2
    assert first["path"].endswith("2026-09-11_run01.json")
    assert second["path"].endswith("2026-09-11_run02.json")
    from pathlib import Path
    assert Path(first["path"]).exists(), "the first receipt must survive the second click"


def test_forecasts_write_one_gradeable_row_per_lane_against_the_control(
        offline, tmp_path, monkeypatch):
    """The benchmark is the CONTROL lane where one exists, SPY where none does,
    and the row says which -- an index is not a twin."""
    days = [f"2026-0{m}-{d:02d}" for m in (7, 8) for d in range(1, 16)]
    monkeypatch.setattr(M, "lane_nav_series", lambda: {
        "balanced": [(d, 100.0 + i) for i, d in enumerate(days)],
        M.CONTROL_LANE: [(d, 100.0 + 0.5 * i) for i, d in enumerate(days)],
    })
    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "forecasts")
    assert row["status"] == "ok" and row["n_written"] == 2
    by_lane = {x["lane"]: x for x in row["rows"]}
    assert by_lane["balanced"]["benchmark"] == M.CONTROL_LANE
    assert by_lane["balanced"]["benchmark_is_fallback"] is False
    assert by_lane[M.CONTROL_LANE]["benchmark"] == M.FALLBACK_BENCHMARK
    assert by_lane[M.CONTROL_LANE]["benchmark_is_fallback"] is True
    # the probability is the lane's own smoothed win rate, not a constant
    assert by_lane["balanced"]["basis"] == "laplace_smoothed_paired_win_rate"
    assert 0.5 < by_lane["balanced"]["probability"] <= 1.0
    written = [json.loads(x) for x in
               (tmp_path / "predictions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(written) == 2
    assert {w["model"] for w in written} == {"engine"}
    assert {w["observable"] for w in written} == {"beats_benchmark"}
    assert {w["horizon_days"] for w in written} == {M.FORECAST_HORIZON_DAYS}


def test_a_thin_history_forecasts_the_coin_flip_and_says_so(offline, tmp_path, monkeypatch):
    """Four sessions is not a base rate. The row is still written -- a morning
    that writes nothing is indistinguishable from one that did not run."""
    days = ["2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"]
    monkeypatch.setattr(M, "lane_nav_series", lambda: {
        "balanced": [(d, 100.0 + i) for i, d in enumerate(days)],
        M.CONTROL_LANE: [(d, 100.0) for d in days],
    })
    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "forecasts")
    got = {x["lane"]: x for x in row["rows"]}
    assert got["balanced"]["probability"] == 0.5
    assert got["balanced"]["basis"] == "insufficient_history"
    assert got["balanced"]["n_paired_days"] == 3       # paired RETURNS, not levels


def test_no_network_requested_skips_rather_than_pretending_to_refuse(offline, tmp_path):
    r = _run(tmp_path, do_network=False)
    rows = {x["step"]: x for x in r["steps"]}
    assert rows["news_pull"]["status"] == "skipped"
    assert "caller" in rows["news_pull"]["reason"]
    assert r["network_requested"] is False


def test_the_digest_masks_the_company_before_the_model_ever_sees_it(tmp_path, monkeypatch):
    """An unmasked digest is a recall test wearing a reading test's clothes."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "2026-09.jsonl").write_text(json.dumps({
        "observed_at": "2026-09-10T12:00:00+00:00", "symbols": ["NVDA"],
        "title": "Nvidia beats on datacentre revenue", "body": "NVDA guided higher",
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(M, "corpus_dir", lambda: corpus)
    monkeypatch.setattr(M, "company_name_map", lambda: {"NVDA": {"nvidia"}})
    monkeypatch.setattr(M, "fetch_gdelt", lambda: {"available": False, "reason": "test"})
    monkeypatch.setattr(M, "fetch_stock_news", lambda *a, **k: [])
    monkeypatch.setattr(M, "run_all_lanes", lambda: {})
    monkeypatch.setattr(M, "lane_nav_series", lambda: {})
    monkeypatch.setattr(M, "refresh_paper_snapshot", lambda **k: {"ok": False})
    monkeypatch.setattr(M, "resolve_due", lambda **k: {"due": 0, "health": {}})
    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "digest")
    assert row["status"] == "ok" and row["n_symbols"] == 1, row
    blob = json.loads(open(row["digests_written_to"], encoding="utf-8").read())
    text = blob["NVDA"]
    assert "nvidia" not in text.lower() and "nvda" not in text.lower(), text
    assert "[co]" in text and "datacentre" in text


def test_grade_reports_nothing_to_do_rather_than_ok_with_zeros(tmp_path, monkeypatch, offline):
    monkeypatch.setattr(M, "resolve_due", lambda **k: {
        "as_of": "2026-09-11", "due": 0, "newly_resolved": 0, "pending": 3,
        "overdue": 0, "health": {"status": "ok"}})
    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "grade")
    assert row["status"] == "nothing_to_do" and row["pending"] == 3


def test_coverage_distinguishes_a_pending_source_from_an_empty_one(
        offline, tmp_path, monkeypatch):
    """A source that does not exist yet and a source that returned zero are
    different facts. The directory is monkeypatched because asserting "still
    PENDING" against the live path encodes a FILESYSTEM moment -- this test went
    red the hour lane N's puller first created `news_corpus/`."""
    monkeypatch.setattr(M, "NEWS_CORPUS_DIR", tmp_path / "not_yet")
    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "coverage")
    assert row["status"] == "ok"
    pend = next(s for s in row["sources"] if s["source"].startswith("news_corpus"))
    assert pend["rows_today"] is None and "PENDING" in pend["note"]


def test_coverage_counts_the_corpus_once_the_writer_exists(offline, tmp_path, monkeypatch):
    """The other half, so the first test cannot pass by the directory never
    arriving: with a shard for today the row is a COUNT, not a dash."""
    d = tmp_path / "corpus_writer" / "gdelt"
    d.mkdir(parents=True)
    (d / "2026-09-11.jsonl").write_text(
        json.dumps({"a": 1}) + chr(10) + json.dumps({"a": 2}), encoding="utf-8")
    monkeypatch.setattr(M, "NEWS_CORPUS_DIR", tmp_path / "corpus_writer")
    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "coverage")
    got = next(s for s in row["sources"] if s["source"].startswith("news_corpus"))
    assert got["rows_today"] == 2, "two ROWS -- the key says rows, so it counts rows"
    assert got["shards_today"] == 1


def test_latest_receipt_reads_the_newest_run_and_never_runs_anything(offline, tmp_path):
    _run(tmp_path)
    _run(tmp_path)
    blob = M.latest_receipt("2026-09-11", out_dir=tmp_path / "morning")
    assert blob["run"] == 2
    assert M.latest_receipt("1999-01-01", out_dir=tmp_path / "morning") is None


def test_a_lane_with_no_local_nav_still_gets_a_forecast_row(tmp_path, monkeypatch, offline):
    """Found on the first real run: `run_all_lanes()` rebalanced four lanes and
    `paper_nav` was empty, because the DEPLOYMENT marks the lanes and the laptop
    does not. Keying the step off the NAV map made it `nothing_to_do` every
    morning -- a gate that cannot go green."""
    class _Snap:
        latest_rebalance = None

    monkeypatch.setattr(M, "run_all_lanes",
                        lambda: {"balanced": _Snap(), M.CONTROL_LANE: _Snap()})
    monkeypatch.setattr(M, "lane_nav_series", lambda: {})
    r = _run(tmp_path)
    row = next(x for x in r["steps"] if x["step"] == "forecasts")
    assert row["status"] == "ok" and row["n_written"] == 2
    for x in row["rows"]:
        assert x["probability"] == 0.5
        assert x["basis"] == "no_local_nav_history"
        assert "deployment marks the lanes" in x["note"]


def test_the_grade_step_gives_the_resolver_a_frame_that_knows_the_lanes(
        tmp_path, monkeypatch, offline):
    """`balanced beats balanced-ew-control` names no security. Without the lane
    columns every morning row would be logged "can never resolve" and sit in the
    ledger forever, which is worse than not writing it."""
    seen: dict = {}
    monkeypatch.setattr(M, "resolve_due",
                        lambda **kw: seen.update(kw) or {"due": 0, "health": {}})
    _run(tmp_path)
    assert seen["price_fetch"] is M.nav_augmented_price_fetch


def test_the_lane_price_frame_adds_lane_columns_and_never_overwrites_a_ticker(monkeypatch):
    import pandas as pd

    monkeypatch.setattr(M, "lane_nav_series", lambda: {
        "balanced": [("2026-09-09", 100.0), ("2026-09-10", 101.0)]})
    monkeypatch.setattr("backend.services.ledger_resolver._default_price_fetch",
                        lambda t, s, e: pd.DataFrame(
                            {"SPY": [1.0, 2.0]},
                            index=pd.to_datetime(["2026-09-09", "2026-09-10"])))
    frame = M.nav_augmented_price_fetch(["SPY", "balanced"], "2026-09-01", "2026-09-11")
    assert set(frame.columns) == {"SPY", "balanced"}
    assert float(frame["balanced"].iloc[-1]) == 101.0
    assert float(frame["SPY"].iloc[-1]) == 2.0
