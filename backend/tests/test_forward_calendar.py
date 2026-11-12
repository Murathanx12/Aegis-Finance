"""Forward catalyst calendar: point-in-time snapshots, a reader that cannot look ahead,
red when the pull returns nothing. Offline: every fetcher is a stub, every clock is
injected, every date is derived from NOW (no calendar-moment literal)."""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from backend.services import forward_calendar as FC

#: 15:00 UTC on the test day: 10:00/11:00 in New York, far from either midnight.
NOW = datetime.combine(date.today(), time(15, 0), tzinfo=timezone.utc)
TODAY = NOW.date()


def _ts(d: date, hh: int = 21, mm: int = 0) -> int:
    """A UTC epoch on day `d` at hh:mm UTC (21:00 UTC = 16:00/17:00 New York: after the close)."""
    return int(datetime.combine(d, time(hh, mm), tzinfo=timezone.utc).timestamp())


def _q(sym: str, d: date, *, est: bool = False, hh: int = 21, end: date | None = None,
       qt: str = "EQUITY") -> dict:
    return {"symbol": sym, "quoteType": qt, "earningsTimestamp": _ts(d, hh),
            "earningsTimestampStart": _ts(d, hh), "earningsTimestampEnd": _ts(end or d, hh),
            "isEarningsDateEstimate": est, "exchangeTimezoneName": "America/New_York"}


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        self.t += timedelta(seconds=1)
        return self.t


def _stub(table: dict):
    calls = []

    def fetch(symbols):
        calls.append(list(symbols))
        return {s: table[s] for s in symbols if s in table}
    fetch.calls = calls
    return fetch


def _pull(tmp_path, tickers, table, at, **kw):
    return FC.pull(tickers, tmp_path, fetch=_stub(table), macro=False, now_fn=Clock(at),
                   sleep_fn=lambda s: None, **kw)


# ─────────────────────────────────────────── append-only, never overwritten

def test_snapshots_append_and_never_overwrite(tmp_path):
    d = TODAY + timedelta(days=5)
    r1 = _pull(tmp_path, ["NVDA", "AMD"], {"NVDA": _q("NVDA", d), "AMD": _q("AMD", d)},
               NOW - timedelta(days=1))
    first = Path(r1["snapshot_path"])
    before = first.read_bytes()
    r2 = _pull(tmp_path, ["NVDA", "AMD"], {"NVDA": _q("NVDA", d), "AMD": _q("AMD", d)}, NOW)
    assert r1["pull_id"] != r2["pull_id"]
    assert first.read_bytes() == before                      # the first pull is untouched
    finals = sorted(FC.snapshots_dir(tmp_path).glob("fc_*.jsonl"))
    assert len([f for f in finals if ".partial" not in f.name]) == 2
    # the same pull id again (same clock, same tickers) refuses rather than overwrite
    with pytest.raises(FC.ForwardCalendarRefused) as e:
        _pull(tmp_path, ["NVDA", "AMD"], {"NVDA": _q("NVDA", d), "AMD": _q("AMD", d)}, NOW)
    assert e.value.code == FC.SNAPSHOT_EXISTS
    assert Path(r2["snapshot_path"]).is_file()


def test_a_revised_date_is_two_rows_and_the_reader_returns_the_one_valid_at_each_now(tmp_path):
    d1, d2 = TODAY + timedelta(days=6), TODAY + timedelta(days=8)
    t1, t2 = NOW - timedelta(days=2), NOW - timedelta(days=1)
    _pull(tmp_path, ["NVDA"], {"NVDA": _q("NVDA", d1, est=True)}, t1)
    _pull(tmp_path, ["NVDA"], {"NVDA": _q("NVDA", d2)}, t2)
    rows = [r for f in FC.snapshots_dir(tmp_path).glob("fc_*.jsonl")
            for r in FC._read_jsonl(f) if r.get("ticker") == "NVDA"]
    assert sorted(r["next_date"] for r in rows) == [d1.isoformat(), d2.isoformat()]

    before = FC.next_dates(["NVDA"], t1 - timedelta(hours=1), root=tmp_path)["tickers"]["NVDA"]
    assert before["label"] == FC.NOT_COVERED and before["reason"] == "NO_ROW_BY_NOW"
    mid = FC.next_dates(["NVDA"], t1 + timedelta(hours=12), root=tmp_path)
    assert mid["tickers"]["NVDA"]["date"] == d1.isoformat()
    assert mid["tickers"]["NVDA"]["confirmation"] == "VENDOR_ESTIMATE"
    assert mid["tickers"]["NVDA"]["timing"] == "UNKNOWN"        # an estimate's time is not information
    late = FC.next_dates(["NVDA"], NOW, root=tmp_path)["tickers"]["NVDA"]
    assert late["date"] == d2.isoformat() and late["label"] == FC.DATE_IN_HORIZON
    assert late["confirmation"] == "VENDOR_ANNOUNCED" and late["timing"] == "AMC"
    assert late["days_away"] == (d2 - FC.market_date(NOW)).days


def test_rows_pulled_after_now_inside_a_file_started_before_now_are_not_used(tmp_path):
    d = TODAY + timedelta(days=4)
    r = _pull(tmp_path, ["NVDA", "AMD"], {"NVDA": _q("NVDA", d), "AMD": _q("AMD", d)}, NOW,
              batch_size=1)
    rows = FC._read_jsonl(Path(r["snapshot_path"]))
    first_t = FC._utc(rows[0]["pulled_utc"])
    res = FC.next_dates(["NVDA", "AMD"], first_t, root=tmp_path)
    labels = {t: v["label"] for t, v in res["tickers"].items()}
    assert labels[rows[0]["ticker"]] == FC.DATE_IN_HORIZON
    other = "AMD" if rows[0]["ticker"] == "NVDA" else "NVDA"
    assert labels[other] == FC.NOT_COVERED and res["n_rows_after_now_skipped"] == 1


# ─────────────────────────────────────────── failures are recorded, never skipped

def test_a_failed_ticker_is_recorded(tmp_path):
    d = TODAY + timedelta(days=3)
    calls = []

    def fetch(symbols):
        calls.append(list(symbols))
        if "BAD" in symbols:
            raise ConnectionError("boom")
        return {"NVDA": _q("NVDA", d)}                      # GHOST is absent from the reply
    rec = FC.pull(["NVDA", "GHOST", "BAD"], tmp_path, fetch=fetch, macro=False, now_fn=Clock(NOW),
                  sleep_fn=lambda s: None, batch_size=2)
    assert rec["requested"] == 3 and rec["failed"] == 2 and rec["with_date"] == 1
    rows = {r["ticker"]: r for r in FC._read_jsonl(Path(rec["snapshot_path"]))}
    assert rows["GHOST"]["status"] == FC.FAILED and rows["GHOST"]["error"] == "NOT_IN_RESPONSE"
    assert rows["BAD"]["status"] == FC.FAILED and "BATCH_FAILED ConnectionError" in rows["BAD"]["error"]
    assert set(rec["failed_tickers"]) == {"GHOST", "BAD"}
    res = FC.next_dates(["GHOST", "BAD"], NOW + timedelta(minutes=5), root=tmp_path)["tickers"]
    assert res["BAD"]["label"] == FC.NOT_COVERED and res["BAD"]["reason"] == "ONLY_FAILED_ATTEMPTS"
    assert "ConnectionError" in res["BAD"]["last_error"]


def test_rate_limit_backs_off_once_then_stops_and_records_the_rest(tmp_path):
    slept = []

    def fetch(symbols):
        raise RuntimeError("429 Too Many Requests")
    rec = FC.pull(["A", "B", "C"], tmp_path, fetch=fetch, macro=False, now_fn=Clock(NOW),
                  sleep_fn=slept.append, batch_size=1)
    assert rec["stopped"] == "RATE_LIMITED_PULL_STOPPED" and rec["failed"] == 3
    assert rec["n_requests"] == 2                          # one batch, one retry, then stop
    assert slept == [FC._cfg("FORWARD_CALENDAR_RATE_LIMIT_BACKOFF_S", 60.0)]
    rows = FC._read_jsonl(Path(rec["snapshot_path"]))
    assert {r["ticker"] for r in rows} == {"A", "B", "C"}
    assert all(r["status"] == FC.FAILED for r in rows)


def test_low_coverage_pull_is_kept_but_red(tmp_path):
    rec = _pull(tmp_path, ["A", "B", "C", "D"], {}, NOW)
    assert rec["status"] == FC.LOW_COVERAGE and rec["share_covered"] == 0.0
    assert Path(rec["snapshot_path"]).is_file()            # the failure is itself a record
    with pytest.raises(FC.ForwardCalendarRefused) as e:
        FC.check_coverage(rec)
    assert e.value.code == FC.LOW_COVERAGE and "0 of 4" in str(e.value)
    f = FC.freshness(tmp_path, NOW + timedelta(minutes=1))
    assert f["verdict"] == "STALE" and "LOW_COVERAGE" in f["detail"]


def _data_root(tmp_path: Path, syms: list[str]) -> Path:
    dr = tmp_path / "optimus"
    (dr / "pc_book").mkdir(parents=True)
    (dr / "pc_book" / "state_latest.json").write_text(json.dumps(
        {"t": (NOW - timedelta(hours=1)).isoformat(), "positions": [{"symbol": s} for s in syms]}),
        encoding="utf-8")
    return dr


def test_cli_low_coverage_pull_exits_non_zero_with_the_counts(tmp_path, monkeypatch, capsys):
    from scripts import forward_calendar as CLI
    dr = _data_root(tmp_path, ["NVDA", "AMD", "MU"])
    monkeypatch.setattr(FC, "yahoo_quote_batch", lambda syms: {})
    monkeypatch.setattr(FC.time, "sleep", lambda s: None)
    rc = CLI.main(["pull", "--data-root", str(dr), "--out", str(tmp_path / "out"), "--no-macro",
                   "--tickers", "NVDA,AMD,MU"])
    out = capsys.readouterr().out
    assert rc == 2 and "REFUSED LOW_COVERAGE" in out and '"failed": 3' in out
    rc = CLI.main(["status", "--data-root", str(dr), "--out", str(tmp_path / "out")])
    assert rc == 2


def test_cli_good_pull_is_rc0_and_writes_only_under_out(tmp_path, monkeypatch, capsys):
    from scripts import forward_calendar as CLI
    dr = _data_root(tmp_path, ["NVDA", "AMD"])
    d = TODAY + timedelta(days=5)
    monkeypatch.setattr(FC, "yahoo_quote_batch", lambda syms: {s: _q(s, d) for s in syms})
    n_before = sum(1 for _ in dr.rglob("*"))
    rc = CLI.main(["pull", "--data-root", str(dr), "--out", str(tmp_path / "out"), "--no-macro"])
    assert rc == 0, capsys.readouterr().out
    assert sum(1 for _ in dr.rglob("*")) == n_before
    rc = CLI.main(["show", "--data-root", str(dr), "--out", str(tmp_path / "out"), "--tickers", "NVDA"])
    assert rc == 0 and '"DATE_IN_HORIZON"' in capsys.readouterr().out


# ─────────────────────────────────────────── labels are distinct

def test_stale_and_not_covered_are_distinct(tmp_path):
    d = TODAY + timedelta(days=30)
    old = NOW - timedelta(days=FC._cfg("FORWARD_CALENDAR_STALE_DAYS", 3.0) + 2)
    _pull(tmp_path, ["NVDA"], {"NVDA": _q("NVDA", d)}, old)
    res = FC.next_dates(["NVDA", "AVGO"], NOW, root=tmp_path)["tickers"]
    assert res["NVDA"]["label"] == FC.CALENDAR_STALE and res["NVDA"]["date"] == d.isoformat()
    assert res["NVDA"]["age_days"] > FC._cfg("FORWARD_CALENDAR_STALE_DAYS", 3.0)
    assert res["AVGO"]["label"] == FC.NOT_COVERED
    assert FC.CALENDAR_STALE != FC.NOT_COVERED != FC.NO_DATE_IN_HORIZON


def test_no_date_in_horizon_reasons(tmp_path):
    q_none = {"symbol": "XX", "quoteType": "EQUITY"}
    tbl = {"FAR": _q("FAR", TODAY + timedelta(days=200)), "XX": q_none,
           "SPY": {"symbol": "SPY", "quoteType": "ETF"},
           "PAST": _q("PAST", TODAY - timedelta(days=10))}
    _pull(tmp_path, list(tbl), tbl, NOW)
    res = FC.next_dates(list(tbl), NOW + timedelta(minutes=1), horizon_days=45, root=tmp_path)["tickers"]
    assert {t: v["label"] for t, v in res.items()} == {t: FC.NO_DATE_IN_HORIZON for t in tbl}
    assert res["FAR"]["reason"] == "BEYOND_HORIZON"
    assert res["XX"]["reason"] == "VENDOR_HAS_NO_EARNINGS_FIELDS"
    assert res["SPY"]["reason"].startswith("NOT_AN_ISSUER")
    assert res["PAST"]["reason"] == "ONLY_PAST_DATES"
    # a stored date that has since passed is not "upcoming"
    later = FC.next_dates(["FAR"], NOW + timedelta(days=1), horizon_days=400, root=tmp_path)
    assert later["tickers"]["FAR"]["label"] == FC.DATE_IN_HORIZON


def test_parse_quote_timing_and_confirmation():
    d = TODAY + timedelta(days=2)
    p = lambda q, t="NVDA": FC.parse_quote(t, FC.yahoo_symbol(t), q, pulled_utc=NOW, pull_id="x")  # noqa: E731
    assert p(_q("NVDA", d, hh=21))["timing"] == "AMC"
    assert p(_q("NVDA", d, hh=11))["timing"] == "BMO"         # 06:00/07:00 New York
    assert p(_q("NVDA", d, hh=17))["timing"] == "INTRA"
    untimed = p(_q("NVDA", d, hh=0))
    assert untimed["timing"] == "UNKNOWN" and untimed["next_date"] == d.isoformat()
    rng = p(_q("NVDA", d, end=d + timedelta(days=4)))
    assert rng["confirmation"] == "VENDOR_ESTIMATE" and rng["date_end"] == (d + timedelta(days=4)).isoformat()
    q = _q("NVDA", d)
    q.pop("isEarningsDateEstimate")
    assert p(q)["confirmation"] == "UNKNOWN"
    assert FC.yahoo_symbol("BRK.B") == "BRK-B" and FC.yahoo_symbol("7203.T") == "7203.T"
    assert p(None)["status"] == FC.FAILED
    assert p(_q("NVDA", d))["raw"]["isEarningsDateEstimate"] is False


# ─────────────────────────────────────────── resumable

def test_an_interrupted_pull_resumes_and_skips_done_tickers(tmp_path):
    d = TODAY + timedelta(days=5)
    snap = FC.snapshots_dir(tmp_path)
    snap.mkdir(parents=True)
    start = NOW - timedelta(hours=1)
    pid = f"fc_{FC._stamp(start)}_abcdef"
    done = FC.parse_quote("NVDA", "NVDA", _q("NVDA", d), pulled_utc=start, pull_id=pid)
    (snap / f"{pid}.partial.jsonl").write_text(json.dumps(done) + "\n", encoding="utf-8")
    fetch = _stub({"AMD": _q("AMD", d), "NVDA": _q("NVDA", d)})
    rec = FC.pull(["NVDA", "AMD"], tmp_path, fetch=fetch, macro=False, now_fn=Clock(NOW),
                  sleep_fn=lambda s: None)
    assert rec["pull_id"] == pid and rec["resumed_from"] == f"{pid}.partial.jsonl"
    assert fetch.calls == [["AMD"]]
    assert rec["with_date"] == 2 and not list(snap.glob("*.partial.jsonl"))


# ─────────────────────────────────────────── macro stored the same way

def test_macro_rows_and_refusals_are_stored(tmp_path):
    d = (TODAY + timedelta(days=9)).isoformat()
    blk = {"macro": [{"kind": "FOMC", "event_time": d, "what": "FOMC", "source": "fed_schedule_static"}],
           "refusals": [{"kind": "CPI", "refusal": "FRED_KEY_ABSENT: ..."}],
           "legs": {"CPI": "REFUSED", "FOMC": "1 date(s) (ok)"}, "fomc_table": {"status": "ok"},
           "horizon_days": 120}
    rec = FC.pull(["NVDA"], tmp_path, fetch=_stub({"NVDA": _q("NVDA", TODAY + timedelta(days=3))}),
                  macro=lambda: blk, now_fn=Clock(NOW), sleep_fn=lambda s: None)
    assert rec["macro"]["n_dates"] == 1 and rec["macro"]["n_refusals"] == 1
    m = FC.next_macro(NOW + timedelta(minutes=1), root=tmp_path)
    assert m["dates"][0]["date"] == d and m["refusals"][0]["kind"] == "CPI"
    assert FC.next_macro(NOW - timedelta(days=1), root=tmp_path)["status"] == "NO_MACRO_SNAPSHOT_BY_NOW"


# ─────────────────────────────────────────── universe + health

def test_universe_union_and_a_source_stamped_after_now_contributes_nothing(tmp_path):
    dr = _data_root(tmp_path, ["NVDA", "SPY"])
    (dr / "llm_portfolio").mkdir()
    (dr / "llm_portfolio" / "books.jsonl").write_text("\n".join(json.dumps(b) for b in [
        {"frozen_utc": (NOW - timedelta(days=1)).isoformat(), "positions": [{"ticker": "MU"}]},
        {"frozen_utc": (NOW + timedelta(days=1)).isoformat(), "positions": [{"ticker": "LATE"}]},
    ]), encoding="utf-8")
    fun = tmp_path / "funnel.json"
    fun.write_text(json.dumps({"generated_at": (NOW - timedelta(days=2)).isoformat(),
                               "candidates": [{"ticker": "TXRH"}]}), encoding="utf-8")
    u = FC.build_universe(dr, NOW, funnel_path=fun)
    assert u["tickers"] == ["MU", "NVDA", "SPY", "TXRH"]
    assert u["sources"]["universe_graph"]["status"] == "MISSING"
    assert u["sources"]["funnel"]["age_days"] == 2.0
    # without --funnel, the snapshot BESIDE the data root is read (backend/data/funnel_night10.json),
    # not the code checkout's tracked copy
    (tmp_path / "funnel_night10.json").write_text(fun.read_text(encoding="utf-8"), encoding="utf-8")
    assert FC.build_universe(dr, NOW)["sources"]["funnel"]["path"] == str(tmp_path / "funnel_night10.json")
    with pytest.raises(FC.ForwardCalendarRefused) as e:
        FC.build_universe(tmp_path / "empty_root_does_not_exist", NOW)
    assert e.value.code == FC.DATA_ROOT_MISSING


def test_health_row_unknown_alive_stale_and_registered(tmp_path, monkeypatch):
    from backend.services import system_health as SH
    assert any(p.name == "forward_calendar" for p in SH.PROBES)
    ctx = SH.ProbeCtx(optimus_dir=tmp_path, now=NOW, repo=tmp_path, allow_proc=False)
    assert FC.p_forward_calendar(ctx).verdict == "UNKNOWN"
    d = TODAY + timedelta(days=5)
    _pull(tmp_path, ["NVDA"], {"NVDA": _q("NVDA", d)}, NOW - timedelta(hours=2))
    assert FC.p_forward_calendar(ctx).verdict == "ALIVE"
    later = SH.ProbeCtx(optimus_dir=tmp_path, now=NOW + timedelta(days=10), repo=tmp_path, allow_proc=False)
    assert FC.p_forward_calendar(later).verdict == "STALE"
    monkeypatch.setattr(SH, "on_railway", lambda: False)
    rows = SH.run_probes(ctx, only={"forward_calendar"})
    assert len(rows) == 1 and rows[0]["verdict"] == "ALIVE"
    # a receipt stamped after `now` is not evidence at `now`
    early = SH.ProbeCtx(optimus_dir=tmp_path, now=NOW - timedelta(days=1), repo=tmp_path, allow_proc=False)
    assert FC.p_forward_calendar(early).verdict == "UNKNOWN"


# ─────────────────────────────────────────── no test can reach the network

def test_the_real_fetcher_is_blocked_offline_and_the_pull_goes_red(tmp_path):
    """The default fetcher, un-stubbed, under the suite's network block: it must raise,
    and a pull through it records every ticker FAILED and is LOW_COVERAGE (never green)."""
    with pytest.raises(Exception):
        FC.yahoo_quote_batch(["NVDA"])
    rec = FC.pull(["NVDA", "AMD"], tmp_path, macro=False, now_fn=Clock(NOW), sleep_fn=lambda s: None)
    assert rec["failed"] == 2 and rec["status"] == FC.LOW_COVERAGE
    assert all("BATCH_FAILED" in (r.get("error") or "")
               for r in FC._read_jsonl(Path(rec["snapshot_path"])))
