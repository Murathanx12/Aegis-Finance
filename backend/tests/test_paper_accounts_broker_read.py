"""Lane M5 (2026-09-28): the broker legs of `scripts/paper_accounts_roi.py`.

A failed broker read is BROKER_ERROR by name (401, timeout, no key), never $0;
every row carries `mark_status` and `mark_age_days`; the read is GET-only and
prints no key; a key shared by two roles is refused, not aliased. Offline:
every broker leg is injected. Dates derived from today.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from learner import benchmark as B
from scripts import paper_accounts_roi as PA

SECRET = "sk-THIS-MUST-NEVER-APPEAR"
#: the receipt ages marks on the UTC date (the machine runs at UTC+8)
TODAY = datetime.now(timezone.utc).date()


class _Resp:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class _Http:
    """Records every call; answers by key id."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, headers=None, timeout=None, **kw):
        self.calls.append(("GET", url, sorted(kw)))
        kid = headers["APCA-API-KEY-ID"]
        if kid == "k401":
            return _Resp(401, {"message": "unauthorized"})
        if kid == "kslow":
            raise TimeoutError("read timed out")
        if kid == "k500":
            return _Resp(500, {})
        if url.endswith("/v2/account"):
            return _Resp(200, {"equity": "101000", "cash": "5", "last_equity": "100500",
                               "account_number": "PA1", "created_at": "2026-08-28T08:11:50Z"})
        return _Resp(200, [{"symbol": "A"}])


def _env(**pairs):
    e = {}
    for role, kid in pairs.items():
        n = role.replace("hack", "")
        e[f"AAT_HACK{n}_KEY_ID"], e[f"AAT_HACK{n}_SECRET_KEY"] = kid, SECRET
    return e


def _spy():
    idx = pd.bdate_range(TODAY - timedelta(days=120), TODAY)
    return B.Benchmark("spy_tr_yf_adjclose", pd.Series(0.001, index=idx), "D",
                       {"source": "synthetic", "construction": "constant"})


def _build(tmp_path, monkeypatch, env, *, include=True, pc=None):
    monkeypatch.setattr(PA, "collect_murat", lambda **k: [])
    monkeypatch.setattr(PA, "collect_agency", lambda *a, **k: [])
    lanes = {"expected_nav_date": str(TODAY), "all_fresh": True,
             "lanes": {"fresh_lane": [{"date": str(TODAY - timedelta(days=60)), "value": 1e5},
                                      {"date": str(TODAY), "value": 1.01e5}],
                       "old_lane": [{"date": str(TODAY - timedelta(days=60)), "value": 1e5},
                                    {"date": str(TODAY - timedelta(days=10)), "value": 0.99e5}]},
             "benchmarks": {}}
    http = _Http()
    books = tmp_path / "books.jsonl"
    books.write_text("", encoding="utf-8")
    rc = PA.build(tr=lanes, tr_source="synthetic", tr_fresh=True, fleet_env=env, http_get=http,
                  pc_snapshot=pc or (lambda: {"equity": 999_000.0, "n_positions": 3,
                                              "account_number": "PC"}),
                  paper_books_args=([], {}), llm_books_path=books, llm_leaderboard={"books": []},
                  decisions_dir=tmp_path, bm=_spy(), include_fleet=include, include_pc=include)
    return rc, http


def _rows(rc):
    return {r["account"]: r for r in rc["rows"]}


def test_every_failed_read_is_broker_error_by_name_never_zero(tmp_path, monkeypatch):
    rc, _ = _build(tmp_path, monkeypatch,
                   _env(hack1="kok", hack2="k401", hack4="kslow", hack5="k500"))
    r = _rows(rc)
    assert r["hack1"]["mark_status"] == "LIVE" and r["hack1"]["mark_age_days"] == 0
    assert r["hack1"]["equity"] == 101000.0
    for acct, name in (("hack2", "HTTP_401"), ("hack4", "TIMEOUT"), ("hack5", "HTTP_500"),
                       ("hack3", "NO_CREDENTIAL"), ("hack6", "NO_CREDENTIAL")):
        assert r[acct]["mark_status"] == "BROKER_ERROR", acct
        assert r[acct]["broker_error"].startswith(name), (acct, r[acct]["broker_error"])
        assert r[acct]["equity"] is None and r[acct]["roi_pct"] is None
    br = rc["broker_read"]
    assert br["performed"] is True and br["n_broker_error"] == 5
    assert set(br["errors"]) == {"hack2", "hack3", "hack4", "hack5", "hack6"}


def test_the_read_is_get_only_on_account_and_positions(tmp_path, monkeypatch):
    _, http = _build(tmp_path, monkeypatch, _env(hack1="kok"))
    assert http.calls, "no broker call was made"
    for method, url, kw in http.calls:
        assert method == "GET"
        assert url.endswith("/v2/account") or url.endswith("/v2/positions"), url
        assert "json" not in kw and "data" not in kw


def test_no_key_or_secret_reaches_the_receipt(tmp_path, monkeypatch):
    rc, _ = _build(tmp_path, monkeypatch, _env(hack1="kok", hack2="k401"))
    blob = json.dumps(rc, default=str)
    assert SECRET not in blob and "kok" not in blob and "k401" not in blob


def test_a_key_two_roles_share_is_refused_not_aliased(tmp_path, monkeypatch):
    rc, http = _build(tmp_path, monkeypatch, _env(hack1="kok", hack2="kok"))
    r = _rows(rc)
    assert r["hack1"]["mark_status"] == "LIVE"
    assert r["hack2"]["mark_status"] == "BROKER_ERROR"
    assert r["hack2"]["broker_error"].startswith("KEY_SHARED_WITH_HACK1")
    assert sum(1 for c in http.calls if c[1].endswith("/v2/account")) == 1


def test_pc_paper_failure_is_named(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("HTTPSConnectionPool: Read timed out. (read timeout=20)")
    rc, _ = _build(tmp_path, monkeypatch, {}, pc=boom)
    pc = _rows(rc)["PC-PAPER"]
    assert pc["mark_status"] == "BROKER_ERROR" and pc["broker_error"].startswith("TIMEOUT")
    assert pc["equity"] is None


def test_mark_age_decides_live_or_stale_on_every_row(tmp_path, monkeypatch):
    rc, _ = _build(tmp_path, monkeypatch, _env(hack1="kok"))
    r = _rows(rc)
    assert r["fresh_lane"]["mark_status"] == "LIVE" and r["fresh_lane"]["mark_age_days"] == 0
    assert r["old_lane"]["mark_status"] == "STALE" and r["old_lane"]["mark_age_days"] == 10
    for row in rc["rows"]:
        assert row["mark_status"] in PA.MARK_STATUSES
        assert "mark_age_days" in row
    assert sum(rc["mark_status_counts"].values()) == len(rc["rows"])


def test_pending_void_and_never_marked_rows():
    today = TODAY
    assert PA.mark_status({"status": "PENDING"}, today) == ("PENDING", None)
    assert PA.mark_status({"status": "VOIDED"}, today) == ("VOID", None)
    assert PA.mark_status({"status": "UNGRADED", "last_mark": None}, today) == ("STALE", None)
    old = str(today - timedelta(days=30))
    assert PA.mark_status({"status": "LIVE", "last_mark": old}, today) == ("STALE", 30)


def test_no_broker_says_so_in_the_receipt(tmp_path, monkeypatch):
    rc, http = _build(tmp_path, monkeypatch, {}, include=False)
    assert http.calls == []
    assert rc["broker_read"]["performed"] is False
    assert "alpaca_fleet" in rc["broker_read"]["families"]
    assert not any(r["family"] in PA.BROKER_FAMILIES for r in rc["rows"])


def test_a_run_id_receipt_is_written_and_never_overwritten(tmp_path, monkeypatch):
    rc, _ = _build(tmp_path, monkeypatch, _env(hack1="kok"))
    out = PA.write_outputs(rc, chart=False, out_dir=tmp_path / "pa", doc_path=tmp_path / "PA.md")
    rr = out["receipt_run"]
    assert rr.exists() and out["receipt"].exists() and rr != out["receipt"]
    body = rr.read_text(encoding="utf-8")
    rc2 = dict(rc, rows=[])
    PA.write_outputs(rc2, chart=False, out_dir=tmp_path / "pa", doc_path=tmp_path / "PA.md")
    assert rr.read_text(encoding="utf-8") == body                 # untouched
    assert json.loads(out["receipt"].read_text(encoding="utf-8"))["rows"] == []  # latest moved


# ── review F6 (2026-09-28): a narrower scope never replaces the broker-included receipt ──

def test_a_receipt_records_its_scope(tmp_path, monkeypatch):
    rc, _ = _build(tmp_path, monkeypatch, _env(hack1="kok"))
    assert rc["scope"]["with_broker"] is True and rc["scope"]["broker_accounts_attempted"] >= 1
    assert rc["scope"]["accounts_attempted"] == len(rc["rows"])
    rc2, _ = _build(tmp_path, monkeypatch, {}, include=False)
    assert rc2["scope"]["with_broker"] is False and rc2["scope"]["broker_accounts_attempted"] == 0


def test_a_no_broker_pass_never_overwrites_the_broker_included_receipt(tmp_path, monkeypatch):
    wide, _ = _build(tmp_path, monkeypatch, _env(hack1="kok"))
    out = PA.write_outputs(wide, chart=False, out_dir=tmp_path / "pa", doc_path=tmp_path / "PA.md")
    body = out["receipt"].read_text(encoding="utf-8")
    doc = (tmp_path / "PA.md").read_text(encoding="utf-8")
    narrow, _ = _build(tmp_path, monkeypatch, {}, include=False)
    narrow["generated_utc"] = wide["generated_utc"]           # same second: the hardest case
    out2 = PA.write_outputs(narrow, chart=False, out_dir=tmp_path / "pa", doc_path=tmp_path / "PA.md")
    assert out["receipt"].read_text(encoding="utf-8") == body            # wide receipt untouched
    assert out["receipt_run"].exists() and out2["receipt_run"] != out["receipt_run"]
    assert ".nobroker" in out2["receipt"].name and out2["receipt"].exists()
    assert json.loads(out2["receipt"].read_text(encoding="utf-8"))["scope"]["with_broker"] is False
    assert (tmp_path / "PA.md").read_text(encoding="utf-8") == doc       # the doc keeps the wide read


def test_a_legacy_broker_receipt_without_scope_is_still_protected(tmp_path, monkeypatch):
    wide, _ = _build(tmp_path, monkeypatch, _env(hack1="kok"))
    legacy = {k: v for k, v in wide.items() if k != "scope"}
    assert PA.scope_of(legacy)["with_broker"] is True                     # inferred from the rows
    assert PA.narrower({"with_broker": False}, PA.scope_of(legacy))
    assert PA.narrower({"with_broker": True, "broker_accounts_attempted": 1},
                       {"with_broker": True, "broker_accounts_attempted": 7})
    assert not PA.narrower({"with_broker": True, "broker_accounts_attempted": 7},
                           {"with_broker": False, "broker_accounts_attempted": 0})
    day = wide["generated_utc"][:10]
    pa = tmp_path / "pa"
    pa.mkdir()
    (pa / f"roi_{day}.json").write_text(json.dumps(legacy), encoding="utf-8")
    fewer = dict(wide, scope=dict(wide["scope"], broker_accounts_attempted=0), rows=[])
    fewer["scope"]["with_broker"] = True
    out = PA.write_outputs(fewer, chart=False, out_dir=pa, doc_path=tmp_path / "PA.md")
    assert out["date_copy_refused"] and json.loads((pa / f"roi_{day}.json").read_text(encoding="utf-8"))["rows"]
