"""scripts/paper_accounts_roi.py -- every paper account in one table.

Offline: every broker/prod/benchmark leg is injected. The fast suite blocks the
network, so a leaked live call would fail here rather than pass by luck.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from learner import benchmark as B
from scripts import paper_accounts_roi as PA


def _spy(start="2026-06-01", end="2026-09-30", daily=0.001):
    idx = pd.bdate_range(start, end)
    return B.Benchmark("spy_tr_yf_adjclose", pd.Series(daily, index=idx), "D",
                       {"source": "synthetic", "construction": "constant daily return"})


def _tr():
    return {"expected_nav_date": "2026-09-25", "all_fresh": False,
            "lanes": {"alpha": [{"date": "2026-06-08", "value": 100000.0},
                                {"date": "2026-09-25", "value": 110000.0}],
                      "beta": [{"date": "2026-06-08", "value": 100000.0},
                               {"date": "2026-09-18", "value": 90000.0}]},
            "benchmarks": {"SPY": [{"date": "2026-06-08", "value": 100000.0},
                                   {"date": "2026-09-25", "value": 105000.0}]}}


class _Resp:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


def _http(url, headers=None, timeout=None, **_):
    kid = headers["APCA-API-KEY-ID"]
    if kid == "bad":
        return _Resp(401, {"message": "unauthorized"})
    if url.endswith("/v2/account"):
        return _Resp(200, {"equity": "95000", "cash": "1000", "last_equity": "94000",
                           "account_number": "PAX", "created_at": "2026-08-28T08:11:50Z"})
    return _Resp(200, [{"symbol": "A"}, {"symbol": "B"}])


def _llm_books(tmp_path: Path) -> Path:
    p = tmp_path / "books.jsonl"
    parent = {"book_id": "p1", "name": "pers_x", "kind": "personal", "asof": "2026-09-25",
              "start_capital_usd": 1e6, "n_positions": 20, "benchmark": "SPY",
              "frozen_utc": "2026-09-25T05:54:13+00:00"}
    twin = {"book_id": "t1", "name": "pers_x__ew", "kind": "twin", "twin": "ew",
            "parent_book_id": "p1", "asof": "2026-09-25", "start_capital_usd": 1e6,
            "n_positions": 20, "benchmark": "SPY", "frozen_utc": "2026-09-25T07:00:00+00:00"}
    p.write_text("\n".join(json.dumps(r) for r in (parent, twin)) + "\n", encoding="utf-8")
    return p


def _build(tmp_path, monkeypatch, bm=None):
    monkeypatch.setattr(PA, "collect_murat", lambda **k: [PA._row(
        "murat_live", "murat_book", source="t", inception="2026-08-11",
        start_capital=1000.0, equity=900.0, last_mark="2026-09-21", n_positions=12)])
    dec = tmp_path / "decisions"
    dec.mkdir()
    (dec / "2026-09-26.json").write_text(json.dumps(
        {"rows": [{"ticker": "AGENCY_BOOK:balanced", "authority": "EXPLORE"}]}), encoding="utf-8")
    return PA.build(
        tr=_tr(), tr_source="synthetic", tr_fresh=True,
        fleet_env={"AAT_HACK1_KEY_ID": "ok", "AAT_HACK1_SECRET_KEY": "s",
                   "AAT_HACK3_KEY_ID": "bad", "AAT_HACK3_SECRET_KEY": "s"},
        http_get=_http,
        pc_snapshot=lambda: {"equity": 1_010_000.0, "n_positions": 11, "account_number": "PC"},
        paper_books_args=([], {}), llm_books_path=_llm_books(tmp_path), llm_leaderboard={"books": []},
        decisions_dir=dec, bm=bm if bm is not None else _spy(),
        # the day these fixtures describe (before the 09-28 entry); a later
        # today makes an ungraded book UNGRADED, which has its own test
        llm_today=date(2026, 9, 27))


def test_synthetic_account_set_produces_table_and_aggregate(tmp_path, monkeypatch):
    rc = _build(tmp_path, monkeypatch)
    rows = {r["account"]: r for r in rc["rows"]}
    assert rows["alpha"]["roi_pct"] == pytest.approx(10.0)
    assert rows["beta"]["roi_pct"] == pytest.approx(-10.0)
    assert rows["hack1"]["equity"] == 95000.0 and rows["hack1"]["n_positions"] == 2
    assert rows["PC-PAPER"]["roi_pct"] == pytest.approx(1.0)
    for r in rc["rows"]:
        assert r["source"], f"{r['account']} names no source"
        assert r["status"] in PA.STATUSES
    ag = rc["aggregate"]["all_priced"]
    # alpha 110k + beta 90k + hack1 95k + PC 1.01M + murat 900 over 100k*3 + 1M + 1000
    assert ag["sum_equity"] == pytest.approx(110000 + 90000 + 95000 + 1_010_000 + 900)
    assert ag["sum_start_capital"] == pytest.approx(300000 + 1_000_000 + 1000)
    s = rc["aggregate"]["honest_sentence"]
    assert "ahead of SPY" in s and "PENDING" in s
    assert rc["aggregate"]["n_ahead_of_spy"] + rc["aggregate"]["n_behind_spy"] == 5
    # a stale lane says so
    assert rows["beta"]["fresh"] is False and "2026-09-18" in rows["beta"]["note"]
    md = PA.render_markdown(rc, None)
    assert "| alpha |" in md and "pers_x__ew" in md


def test_401_is_credential_invalid_never_zero(tmp_path, monkeypatch):
    rc = _build(tmp_path, monkeypatch)
    h3 = next(r for r in rc["rows"] if r["account"] == "hack3")
    assert h3["status"] == "CREDENTIAL_INVALID"
    assert h3["equity"] is None and h3["roi_pct"] is None
    assert "401" in h3["note"]
    # absent key pair is also not $0
    h2 = next(r for r in rc["rows"] if r["account"] == "hack2")
    assert h2["status"] == "CREDENTIAL_INVALID" and h2["equity"] is None


def test_pending_book_shows_entry_date_and_its_twin(tmp_path, monkeypatch):
    rc = _build(tmp_path, monkeypatch)
    p = next(r for r in rc["rows"] if r["account"] == "pers_x")
    t = next(r for r in rc["rows"] if r["account"] == "pers_x__ew")
    assert p["status"] == "PENDING" and p["roi_pct"] is None
    assert p["note"] == "PENDING (entry 2026-09-28)"      # Fri 09-25 -> Mon 09-28
    assert "ew" in p["graded_against"]
    assert t["family"] == "llm_portfolio:twin" and "pers_x" in t["graded_against"]
    agency = next(r for r in rc["rows"] if r["family"] == "agency")
    assert agency["status"] == "UNGRADED" and "no NAV path" in agency["note"]


def test_spy_leg_comes_from_learner_benchmark(tmp_path, monkeypatch):
    calls = []

    def fake(start=None, end=None):
        calls.append(start)
        return _spy()
    monkeypatch.setattr(B, "spy_total_return", fake)
    bm, err = PA.load_spy("2026-05-15")
    assert calls == ["2026-05-15"] and err is None
    rc = _build(tmp_path, monkeypatch, bm=bm)
    ok, why = B.validate_stamp(rc[B.STAMP_KEY])
    assert ok, why
    alpha = next(r for r in rc["rows"] if r["account"] == "alpha")
    n = len([d for d in bm.returns.index if pd.Timestamp("2026-06-08") < d <= pd.Timestamp("2026-09-25")])
    assert alpha["spy_same_window_pct"] == pytest.approx((1.001 ** n - 1) * 100, abs=1e-3)
    assert alpha["vs_spy_pp"] == pytest.approx(alpha["roi_pct"] - alpha["spy_same_window_pct"], abs=1e-3)


def test_spy_unavailable_is_reported_not_substituted(monkeypatch):
    def boom(start=None, end=None):
        raise B.BenchmarkUnavailable("spy_tr_yf_adjclose", "network")
    monkeypatch.setattr(B, "spy_total_return", boom)
    bm, err = PA.load_spy("2026-05-15")
    assert bm is None and "network" in err


def test_route_serves_newest_receipt_and_404s_when_absent(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.routers import portfolio_intelligence as R
    monkeypatch.setattr(R, "_paper_accounts_dir", lambda: tmp_path)
    c = TestClient(app)
    r = c.get("/api/pi/paper-accounts")
    assert r.status_code == 404 and "paper_accounts_roi" in r.json()["detail"]
    (tmp_path / "roi_2026-09-25.json").write_text(json.dumps({"rows": [], "v": 1}), encoding="utf-8")
    (tmp_path / "roi_2026-09-26.json").write_text(json.dumps({"rows": [], "v": 2}), encoding="utf-8")
    r = c.get("/api/pi/paper-accounts")
    assert r.status_code == 200
    assert r.json()["v"] == 2 and r.json()["receipt_file"] == "roi_2026-09-26.json"


def test_a_voided_book_is_listed_not_graded(tmp_path):
    """Review 2026-09-26: `llm_portfolio.void` appends a row; this reader must not
    crash on it, must not count the book, and must say why."""
    p = _llm_books(tmp_path)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"schema": "llm_portfolio/void", "kind": "void", "book_id": "p1",
                             "name": "pers_x", "reason": "VOID_BEFORE_ENTRY: concentration",
                             "voided_utc": "2026-09-26T09:00:00+00:00", "who": "t"}) + "\n")
    rows = PA.collect_llm_books(p, leaderboard={"books": []}, leaderboard_name="t",
                                today=date(2026, 9, 27))
    assert len(rows) == 2                                    # parent + twin, never the void row
    par = next(r for r in rows if r["account"] == "pers_x")
    assert par["status"] == "VOIDED" and "concentration" in par["note"]
    assert par["roi_pct"] is None
    tw = next(r for r in rows if r["account"] == "pers_x__ew")
    assert tw["status"] == "PENDING"
    ag = PA.aggregate(rows)
    assert ag["status_counts"]["VOIDED"] == 1 and "1 VOIDED" in ag["honest_sentence"]


# ── entry dates come from the GRADER's rule (llm_portfolio.entry_session) ────
# The two books frozen 2026-09-26T19:59Z (Saturday UTC; Sunday 03:59 HKT) carry
# asof 2026-09-27, a SUNDAY. The old weekday arithmetic rolled Sunday forward to
# Monday and then added one, labelling them Tuesday 09-29; the grader enters at
# the Monday 09-28 open. Dates below are fixed on purpose: they are the
# regression, not a calendar moment a fixture will drift past.

def _bars_through(last: str) -> pd.DataFrame:
    idx = pd.bdate_range("2026-09-01", last)
    rows = []
    for sym in ("SPY", "AAA"):
        for i, d in enumerate(idx):
            rows.append({"symbol": sym, "date": d, "open": 100.0 + i, "high": 101.0 + i,
                         "low": 99.0 + i, "close": 100.5 + i, "volume": 1e7})
    return pd.DataFrame(rows)


def test_weekend_freeze_enters_monday_from_the_graders_rule():
    from backend.services import llm_portfolio as LP
    # Sunday-dated (the 09-27 books), and Saturday-dated
    assert PA.next_session_after("2026-09-27") == "2026-09-28"
    assert PA.next_session_after("2026-09-26") == "2026-09-28"
    # same answer whether the grader's calendar is bars or the exchange calendar
    sessions = _bars_through("2026-10-02")["date"].unique()
    assert PA.next_session_after("2026-09-27", sessions) == "2026-09-28"
    assert str(LP.entry_session("2026-09-27", sessions).date()) == "2026-09-28"


def test_late_friday_utc_freeze_enters_monday():
    # frozen 2026-09-25T23:30Z = Saturday 07:30 HKT: the asof date is either the
    # Friday (UTC) or the Saturday (HKT); both enter at the Monday open, never
    # at the Friday session that had already closed.
    assert PA.next_session_after("2026-09-25") == "2026-09-28"
    assert PA.next_session_after("2026-09-26") == "2026-09-28"


def test_holiday_is_skipped_by_the_exchange_calendar():
    # Thanksgiving 2026-11-26 is a weekday and not a session.
    assert PA.next_session_after("2026-11-25") == "2026-11-27"


def test_grader_and_label_agree_on_a_sunday_book():
    """grade() is PENDING with bars through Friday and OK once the Monday bar
    exists -- i.e. it entered on the date the label now prints."""
    from backend.services import llm_portfolio as LP
    rec = {"book_id": "b", "name": "sun_book", "kind": "personal", "asof": "2026-09-27",
           "objective": "x", "n_positions": 1, "benchmark": "SPY",
           "frozen_utc": "2026-09-26T19:59:52+00:00",
           "positions": [{"ticker": "AAA", "weight": 1.0}]}
    assert LP.grade(rec, _bars_through("2026-09-25"))["status"] == "PENDING"
    assert LP.grade(rec, _bars_through("2026-09-28"))["status"] == "OK"
    assert PA.next_session_after(rec["asof"]) == "2026-09-28"


def test_weekday_arithmetic_is_gone():
    import inspect
    assert "busday_offset" not in inspect.getsource(PA.next_session_after).split('"""')[-1]


# ── Monday rehearsal 2026-09-28 (docs/REHEARSAL_2026-09-28_MONDAY_ENTRY.md) ──
# Synthetic, offline. Dates are fixed on purpose: every call passes `today`.

def _lb_row(book_id, name, **kw):
    row = {"book_id": book_id, "name": name, "status": "OK", "nav_usd": 1_010_000.0,
           "benchmark": "SPY", "benchmark_to_date": 0.004, "vs_benchmark": 0.006}
    row.update(kw)
    return row


def test_a_refused_book_after_entry_is_unpriced_not_pending(tmp_path):
    """The rehearsal's 13 all-ETF twins were REFUSED by the grader and printed
    as "PENDING (entry 2026-09-28)" on the evening of 09-28."""
    p = _llm_books(tmp_path)
    lb = {"bars_through": "2026-09-28", "books": [
        _lb_row("t1", "pers_x__ew", status="REFUSED", nav_usd=None,
                why="no position could be priced; missing ['XBI']")]}
    rows = {r["account"]: r for r in PA.collect_llm_books(
        p, leaderboard=lb, leaderboard_name="t", today=date(2026, 9, 29))}
    tw = rows["pers_x__ew"]
    assert tw["status"] == "UNPRICED" and "XBI" in tw["note"] and "REFUSED" in tw["note"]
    assert tw["roi_pct"] is None
    assert PA.aggregate(list(rows.values()))["status_counts"]["UNPRICED"] == 1


def test_spy_leg_of_a_graded_book_is_the_graders_open_to_close_leg(tmp_path):
    """`inception_close` dropped the entry session: on 09-28 evening every book's
    day was compared with SPY = 0.0. The grade's own leg is the book's window."""
    p = _llm_books(tmp_path)
    lb = {"bars_through": "2026-09-28", "books": [_lb_row("p1", "pers_x")]}
    rows = {r["account"]: r for r in PA.collect_llm_books(
        p, leaderboard=lb, leaderboard_name="t", today=date(2026, 9, 29))}
    r = rows["pers_x"]
    assert r["status"] == "LIVE" and r["roi_pct"] == pytest.approx(1.0)
    assert r["spy_same_window_pct"] == pytest.approx(0.4)
    assert r["vs_spy_pp"] == pytest.approx(0.6)
    assert r["spy_base"] == PA.BASE_GRADE
    # a ruler that would say SPY 0.0 on the entry day must not overwrite it
    s = pd.Series([0.05], index=pd.to_datetime(["2026-09-29"]))
    PA.attach_spy([r], SimpleNamespace(returns=s, overlapping=False))
    assert r["spy_same_window_pct"] == pytest.approx(0.4)
    assert r["vs_spy_pp"] == pytest.approx(0.6)


def test_a_urth_book_gets_no_spy_leg_on_a_window_the_grade_did_not_measure(tmp_path):
    p = _llm_books(tmp_path)
    lb = {"bars_through": "2026-09-28", "books": [
        _lb_row("p1", "pers_x", benchmark="URTH", benchmark_to_date=None, vs_benchmark=None)]}
    r = next(x for x in PA.collect_llm_books(p, leaderboard=lb, leaderboard_name="t",
                                             today=date(2026, 9, 29)) if x["account"] == "pers_x")
    assert r["spy_base"] == PA.BASE_NOT_SPY and r["spy_same_window_pct"] is None
    assert "URTH" in r["note"] and "no URTH bars" in r["note"]


def test_an_ungraded_book_after_entry_says_so_instead_of_pending(tmp_path):
    """Nothing schedules `scripts.llm_portfolio grade`. With the newest board
    ending before the entry session, a book is UNGRADED the day after entry."""
    p = _llm_books(tmp_path)
    stale = {"bars_through": "2026-09-25", "books": []}
    before = PA.collect_llm_books(p, leaderboard=stale, leaderboard_name="old",
                                  today=date(2026, 9, 28))
    assert {r["status"] for r in before} == {"PENDING"}      # entry day itself: not yet
    after = PA.collect_llm_books(p, leaderboard=stale, leaderboard_name="old",
                                 today=date(2026, 9, 29))
    assert {r["status"] for r in after} == {"UNGRADED"}
    assert all("scripts.llm_portfolio grade" in r["note"] for r in after)
    fresh = {"bars_through": "2026-09-28", "books": [
        _lb_row("p1", "pers_x", status="PENDING", nav_usd=None)]}
    rows = {r["account"]: r["status"] for r in PA.collect_llm_books(
        p, leaderboard=fresh, leaderboard_name="new", today=date(2026, 9, 29))}
    assert rows["pers_x"] == "PENDING"                       # the grader said so


def test_an_under_priced_book_is_unpriced_with_its_weight_priced(tmp_path):
    """Rule v2 (entry >= 2026-09-28): `REFUSED_UNDER_PRICED` is a refusal, not a
    graded row and not PENDING."""
    p = _llm_books(tmp_path)
    lb = {"bars_through": "2026-10-02", "books": [
        _lb_row("t1", "pers_x__ew", status="REFUSED_UNDER_PRICED", nav_usd=None,
                weight_priced=0.3, why="weight_priced 0.300 < 0.5 after 5 session(s)")]}
    rows = {r["account"]: r for r in PA.collect_llm_books(
        p, leaderboard=lb, leaderboard_name="t", today=date(2026, 10, 3))}
    tw = rows["pers_x__ew"]
    assert tw["status"] == "UNPRICED" and tw["roi_pct"] is None
    assert "REFUSED_UNDER_PRICED" in tw["note"] and "weight_priced 0.3" in tw["note"]


def test_the_reader_is_never_told_to_grade_with_no_pull(tmp_path):
    """`--no-pull` cannot price URTH or the sector ETFs; the daily pass grades in
    PULL mode, so no row or source line may tell a reader to run it."""
    import inspect
    p = _llm_books(tmp_path)
    for r in PA.collect_llm_books(p, leaderboard={"books": []}, leaderboard_name="t",
                                  today=date(2026, 9, 29)):
        assert "--no-pull" not in (r.get("source") or "") + (r.get("note") or "")
    src = inspect.getsource(PA.main)
    assert "--no-pull" not in src


def test_data_paths_follow_the_config_not_the_repo():
    """AEGIS_DATA_DIR moves the reader like it moves the grader (rehearsal: the
    drivers had to re-point these constants in-process)."""
    from backend import config as C
    from backend.services import llm_portfolio as LP
    opt = Path(C.OPTIMUS_LEDGER_DIR)
    assert PA.LLM_DIR == opt / "llm_portfolio" == LP.ledger_dir()
    assert PA.OUT_DIR == opt / "paper_accounts"
    assert PA.DECISIONS_DIR == opt / "decisions"
    assert PA.MURAT_BOOK == Path(C.DATA_DIR) / "murat_book.yaml"
