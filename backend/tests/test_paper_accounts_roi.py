"""scripts/paper_accounts_roi.py -- every paper account in one table.

Offline: every broker/prod/benchmark leg is injected. The fast suite blocks the
network, so a leaked live call would fail here rather than pass by luck.
"""
from __future__ import annotations

import json
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
        decisions_dir=dec, bm=bm if bm is not None else _spy())


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
