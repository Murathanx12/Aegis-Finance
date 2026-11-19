"""CH-65: the hosted backend was retired by the owner, and every surface says so.

The ROI reader must not call the dead URL, must carry the website lanes forward as FROZEN
from the newest local receipt that still holds them (never a mark after the last real one),
and must say SOURCE_RETIRED when no receipt does. Fixtures are small hand-written receipts
under tmp_path; every date is derived from today.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from backend import config as C
from learner import benchmark as B
from scripts import paper_accounts_roi as PA

TODAY = date.today()


def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


LAST_REAL = _d(6)          # the last real lane mark
RETIRED_ON = _d(3)         # the day the host went away


@pytest.fixture
def retired(monkeypatch):
    decl = {"since_utc": RETIRED_ON, "by": "owner", "reason": "hosting stopped on purpose",
            "last_lane_mark": LAST_REAL, "hosts": ("dead.example.invalid",),
            "consequence": "website lanes frozen at their last marks; hosted API off"}
    monkeypatch.setattr(C, "HOSTED_BACKEND_RETIRED", decl)
    monkeypatch.delenv(C.HOSTED_BACKEND_ACTIVE_ENV, raising=False)
    return decl


def _spy() -> B.Benchmark:
    idx = pd.bdate_range(_d(120), _d(0))
    return B.Benchmark("spy_tr_yf_adjclose", pd.Series(0.001, index=idx), "D",
                       {"source": "synthetic", "construction": "constant daily return"})


def _live_receipt(extra_point_after_last_real: bool = False) -> dict:
    """A receipt written while the host still answered: two lanes, marked through LAST_REAL."""
    up = [[_d(90), 100000.0], [_d(30), 104000.0], [LAST_REAL, 107000.0]]
    down = [[_d(90), 100000.0], [_d(30), 80000.0], [LAST_REAL, 64000.0]]
    if extra_point_after_last_real:        # a point that cannot be real: the host was gone
        up = up + [[_d(1), 999999.0]]
    return {"schema": PA.SCHEMA, "generated_utc": f"{_d(5)}T00:30:00+00:00",
            "rows": [{"account": "up", "family": "website_lane", "status": "LIVE", "roi_pct": 7.0,
                      "spy_same_window_pct": 5.0, "vs_spy_pp": 2.0, "last_mark": LAST_REAL},
                     {"account": "down", "family": "website_lane", "status": "LIVE", "roi_pct": -36.0,
                      "spy_same_window_pct": 5.0, "vs_spy_pp": -41.0, "last_mark": LAST_REAL}],
            "lane_nav_series": {"lanes": {"up": up, "down": down},
                                "spy_rebased_100k_at_2026_06_08": [[_d(90), 100000.0], [LAST_REAL, 105000.0]]}}


def _dead_receipt() -> dict:
    """What the reader wrote after the host went away, before CH-65: no lanes at all."""
    return {"schema": PA.SCHEMA, "generated_utc": f"{_d(1)}T00:30:00+00:00",
            "rows": [{"account": "website lanes (all ten)", "family": "website_lane", "status": "UNPRICED"}],
            "lane_nav_series": {}}


def _write(folder: Path, day: str, rc: dict, hhmmss: str = "003000") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / f"roi_{day}T{hhmmss}Z.json"
    p.write_text(json.dumps(rc), encoding="utf-8")
    return p


def _build(tr, src, fresh, frozen, tmp_path, bm=None):
    return PA.build(tr=tr, tr_source=src, tr_fresh=fresh, tr_frozen=frozen, fleet_env={},
                    include_fleet=False, include_pc=False, paper_books_args=([], {}),
                    llm_books_path=tmp_path / "no_books.jsonl", decisions_dir=tmp_path / "no_decisions",
                    murat_bars=pd.DataFrame({"symbol": [], "date": [], "close": []}), bm=bm)


def _no_network(monkeypatch) -> list:
    """Any attempt to reach a host is recorded and fails the test (sockets and `requests`)."""
    import socket

    import requests
    calls: list = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError(f"network call while the hosted backend is declared retired: {a[:1]}")
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(socket.socket, "connect", boom)
    return calls


# ── the declaration ───────────────────────────────────────────────────────

def test_the_shipped_declaration_is_complete_and_readable():
    ret = C.HOSTED_BACKEND_RETIRED
    for k in ("since_utc", "by", "reason", "last_lane_mark", "hosts", "consequence"):
        assert ret.get(k), k
    assert date.fromisoformat(ret["last_lane_mark"]) <= date.fromisoformat(ret["since_utc"])
    assert PA.PROD.split("//")[1] in ret["hosts"], "the ROI reader's host is the retired one"


def test_env_override_reads_at_call_time(retired, monkeypatch):
    assert C.hosted_backend_retired() == retired
    monkeypatch.setenv(C.HOSTED_BACKEND_ACTIVE_ENV, "1")
    assert C.hosted_backend_retired() is None
    monkeypatch.setenv(C.HOSTED_BACKEND_ACTIVE_ENV, "0")
    assert C.hosted_backend_retired() == retired


# ── no call to the dead URL ───────────────────────────────────────────────

def test_retired_means_no_network_call_at_all(retired, tmp_path, monkeypatch):
    calls = _no_network(monkeypatch)
    monkeypatch.setattr(PA, "fetch_track_record",
                        lambda *a, **k: pytest.fail("fetch_track_record called while retired"))
    monkeypatch.setattr(PA, "local_track_record",
                        lambda *a, **k: pytest.fail("the local NAV store is not the frozen source"))
    _write(tmp_path, _d(5), _live_receipt())
    tr, src, fresh, frozen = PA.resolve_lanes(folder=tmp_path)
    assert calls == [] and fresh is False
    assert frozen["status"] == PA.FROZEN and "no network call" in src
    assert set(tr["lanes"]) == {"up", "down"}


def test_env_override_restores_the_live_read(retired, tmp_path, monkeypatch):
    monkeypatch.setenv(C.HOSTED_BACKEND_ACTIVE_ENV, "1")
    seen: list = []

    class R:
        status_code = 200

        def json(self):
            return {"lanes": {"up": [{"date": _d(1), "value": 1.0}]}, "all_fresh": True}

    def get(url, timeout=None):
        seen.append(url)
        return R()
    tr, src, fresh, frozen = PA.resolve_lanes(folder=tmp_path, http_get=get)
    assert seen == [PA.TRACK_RECORD_URL] and src == PA.TRACK_RECORD_URL
    assert fresh is True and frozen is None and tr["lanes"]["up"][0]["date"] == _d(1)


# ── frozen carry-forward ──────────────────────────────────────────────────

def test_lanes_come_frozen_from_the_newest_receipt_that_still_holds_them(retired, tmp_path):
    origin = _write(tmp_path, _d(5), _live_receipt())
    _write(tmp_path, _d(2), _dead_receipt())
    _write(tmp_path, _d(1), _dead_receipt())
    (tmp_path / f"roi_{_d(0)}T010101Z.json").write_text("{not json", encoding="utf-8")
    tr, frozen = PA.frozen_track_record(tmp_path, retired)
    assert frozen["status"] == PA.FROZEN
    assert frozen["origin_receipt"] == origin.name == frozen["carried_from"]
    assert frozen["last_real_mark"] == LAST_REAL and frozen["n_receipts_opened"] == 4
    assert frozen["unreadable_receipts"] and "JSONDecodeError" in frozen["unreadable_receipts"][0]
    rc = _build(tr, frozen["source"], False, frozen, tmp_path, bm=_spy())
    rows = {r["account"]: r for r in rc["rows"]}
    for a in ("up", "down"):
        r = rows[a]
        assert r["status"] == PA.FROZEN and r["frozen"] is True and r["frozen_since"] == LAST_REAL
        assert r["last_mark"] == LAST_REAL and r["mark_status"] == "STALE"
        assert origin.name in r["source"] and "retired by the owner" in r["note"]
        # in no count of any reader: the live fields are empty, the standing is labelled
        assert r["roi_pct"] is None and r["vs_spy_pp"] is None and r["spy_same_window_pct"] is None
        assert r["frozen_standing"]["window"] == [_d(90), LAST_REAL]
    assert rows["up"]["frozen_standing"]["roi_pct"] == pytest.approx(7.0)
    assert rows["down"]["frozen_standing"]["roi_pct"] == pytest.approx(-36.0)
    assert rows["down"]["frozen_standing"]["vs_spy_pp"] < 0 < rows["down"]["equity"]
    ag = rc["aggregate"]
    assert ag["n_ahead_of_spy"] == 0 and ag["n_behind_spy"] == 0 and ag["all_priced"] is None
    fam = ag["by_family"]["website_lane"]
    assert fam["n"] == 2 and fam["n_priced"] == 0 and fam["status"] == PA.FROZEN and fam["n_frozen"] == 2
    assert fam["frozen_since"] == LAST_REAL
    line = ag["frozen_line"]
    assert "2 account(s) FROZEN" in line and LAST_REAL in line and "down" in line
    assert "worst" in line and "none of the counts" in line and line in ag["honest_sentence"]
    src = rc["sources"]["website_lanes"]
    assert src["network_call"] is False and src["reachable"] is False and src["frozen"] is True
    assert src["retired"]["since_utc"] == RETIRED_ON
    assert rc["lane_nav_series"]["frozen"]["origin_receipt"] == origin.name
    md = PA.render_markdown(rc, None)
    assert "NOT CURRENT" in md and "(frozen)" in md and "**FROZEN**" in md
    assert set(PA.doc_accounts(md)) >= {"up", "down"}, "the doc keeps the accounts, so its rewrite is not refused"


def test_a_frozen_lane_never_gets_a_mark_after_the_last_real_one(retired, tmp_path):
    _write(tmp_path, _d(5), _live_receipt(extra_point_after_last_real=True))
    tr, frozen = PA.frozen_track_record(tmp_path, retired)
    assert frozen["n_points_after_last_real_mark_dropped"] == 1
    assert max(p["date"] for pts in tr["lanes"].values() for p in pts) == LAST_REAL
    rc = _build(tr, frozen["source"], False, frozen, tmp_path, bm=_spy())
    for r in rc["rows"]:
        if r["family"] == "website_lane":
            assert r["last_mark"] <= LAST_REAL and r["frozen_since"] <= LAST_REAL
            assert r["equity"] != 999999.0
    for pts in rc["lane_nav_series"]["lanes"].values():
        assert all(d <= LAST_REAL for d, _ in pts)


def test_a_carried_receipt_keeps_naming_the_origin_receipt(retired, tmp_path):
    origin = _write(tmp_path, _d(5), _live_receipt())
    tr, frozen = PA.frozen_track_record(tmp_path, retired)
    rc = _build(tr, frozen["source"], False, frozen, tmp_path, bm=_spy())
    carried = _write(tmp_path, _d(1), json.loads(json.dumps(rc, default=str)))
    tr2, frozen2 = PA.frozen_track_record(tmp_path, retired)
    assert frozen2["carried_from"] == carried.name and frozen2["origin_receipt"] == origin.name
    assert frozen2["n_receipts_opened"] == 1
    assert tr2["lanes"] == tr["lanes"]
    # the standing survives a carry even when the SPY ruler is unavailable that day
    rc2 = _build(tr2, frozen2["source"], False, frozen2, tmp_path, bm=None)
    down = next(r for r in rc2["rows"] if r["account"] == "down")
    was = next(r for r in rc["rows"] if r["account"] == "down")
    assert down["frozen_standing"]["vs_spy_pp"] == was["frozen_standing"]["vs_spy_pp"]
    assert carried.name in down["frozen_standing"]["source"]


def test_no_local_receipt_holds_the_lanes_is_source_retired(retired, tmp_path):
    _write(tmp_path, _d(2), _dead_receipt())
    tr, frozen = PA.frozen_track_record(tmp_path, retired)
    assert tr is None and frozen["status"] == PA.SOURCE_RETIRED
    assert "none of the newest 1 local ROI receipt(s)" in frozen["why"]
    rc = _build(tr, frozen["source"], False, frozen, tmp_path, bm=_spy())
    lane_rows = [r for r in rc["rows"] if r["family"] == "website_lane"]
    assert len(lane_rows) == 1 and lane_rows[0]["status"] == PA.SOURCE_RETIRED
    assert lane_rows[0]["roi_pct"] is None and "retired by the owner" in lane_rows[0]["note"]
    fam = rc["aggregate"]["by_family"]["website_lane"]
    assert fam["n_priced"] == 0 and fam["status"] == PA.SOURCE_RETIRED and fam["reason"]
    assert "SOURCE_RETIRED" in rc["aggregate"]["frozen_line"]


def test_the_lookback_limit_cannot_lose_the_figure(retired, tmp_path):
    """Review B2 (PR #170): while no memory file holds the lanes, every receipt is read (the
    limit used to drop them to SOURCE_RETIRED once ~20 runs had passed); once the memory holds
    them the limit applies and the standing comes from the memory, said in `why`."""
    origin = _write(tmp_path, _d(9), _live_receipt())
    for k in (3, 2, 1):
        _write(tmp_path, _d(k), _dead_receipt())
    tr, frozen = PA.frozen_track_record(tmp_path, retired, max_files=2)
    assert frozen["status"] == PA.FROZEN and frozen["origin_receipt"] == origin.name
    assert frozen["n_receipts_opened"] == 4
    mem = {"schema": PA.FROZEN_SOURCES_SCHEMA, "accounts": {"down": {
        "account": "down", "family": "website_lane", "state": PA.FROZEN, "last_mark": LAST_REAL,
        "inception": _d(90), "nav_end": 64000.0, "roi_pct": -36.0, "vs_spy_pp": -41.0,
        "spy_same_window_pct": 5.0, "source_receipt": origin.name, "source_sha256": "x"}}}
    tr2, frozen2 = PA.frozen_track_record(tmp_path, retired, max_files=2, memory=mem)
    assert tr2 is None and frozen2["status"] == PA.FROZEN and frozen2["standing_only"] is True
    assert frozen2["n_receipts_opened"] == 2 and "newest 2 local ROI receipt(s)" in frozen2["why"]
    assert frozen2["standing"]["down"]["vs_spy_pp"] == -41.0 and frozen2["origin_receipt"] == origin.name


def test_book_dna_is_not_sent_to_the_retired_host(retired, tmp_path):
    seen = {}

    def fake_run(rc, **kw):
        seen.update(kw)
        raise RuntimeError("stop here")
    _write(tmp_path, _d(5), _live_receipt())
    tr, frozen = PA.frozen_track_record(tmp_path, retired)
    rc = _build(tr, frozen["source"], False, frozen, tmp_path, bm=_spy())
    import unittest.mock as um
    with um.patch.object(PA._dna, "run", fake_run):
        PA.attach_book_dna(rc, out_dir=tmp_path, fetch_lanes=False)
    assert seen["fetch_lanes"] is False


def test_without_the_declaration_the_rows_are_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "HOSTED_BACKEND_RETIRED", {})
    assert PA.hosted_retired() is None
    tr = {"lanes": {"up": [{"date": _d(90), "value": 100000.0}, {"date": _d(1), "value": 107000.0}]},
          "all_fresh": True, "expected_nav_date": _d(1)}
    rc = _build(tr, "synthetic", True, None, tmp_path, bm=_spy())
    up = next(r for r in rc["rows"] if r["account"] == "up")
    assert up["status"] == "LIVE" and up["roi_pct"] == pytest.approx(7.0) and "frozen" not in up
    assert rc["aggregate"]["frozen_line"] is None and "retired" not in rc["sources"]["website_lanes"]
