"""C26: the fleet's END-OF-DAY AUDIT (`backend/services/fleet_eod_audit.py`).

A fixture fleet of two accounts: one readable with a missing stop, one whose
key answers 401. Pinned: one row per account, the 401 is NAMED
CREDENTIAL_INVALID (never skipped), a missing stop is DEGRADED, the worst-case
arithmetic, that the audit cannot send anything but GET, and that the health
reader marks a Preclose pass without its audit DEGRADED. Offline; dates derive
from `today`.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.services import fleet_eod_audit as EOD
from backend.services import fleet_manager as FM

TODAY = date.today()
PREV = EOD.prev_weekday(TODAY)


class FleetFake:
    """Answers per key id: 'good' is a readable account, 'dead' answers 401."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        if headers.get("APCA-API-KEY-ID") == "dead":
            return 401, b'{"message":"unauthorized"}'
        path = url.split("?")[0].replace(FM.TRADING_HOST, "")
        if path == "/v2/account":
            return 200, json.dumps({"equity": "10000", "cash": "4000", "last_equity": "9950"}).encode()
        if path == "/v2/clock":
            return 200, json.dumps({"timestamp": f"{TODAY.isoformat()}T15:00:00-04:00", "is_open": True}).encode()
        if path == "/v2/positions":
            return 200, json.dumps([
                {"symbol": "AAA", "qty": "100", "current_price": "50", "market_value": "5000",
                 "asset_class": "us_equity"},
                {"symbol": "BBB", "qty": "50", "current_price": "20", "market_value": "1000",
                 "asset_class": "us_equity"}]).encode()
        if path == "/v2/orders" and "status=open" in url:
            return 200, json.dumps([{"symbol": "AAA", "side": "sell", "type": "stop", "qty": "100",
                                     "stop_price": "45", "client_order_id": "aegisfm-x-stop"}]).encode()
        if path == "/v2/orders":
            return 200, json.dumps([{"symbol": "AAA", "side": "sell", "type": "stop",
                                     "client_order_id": "aegisfm-x-stop", "status": "new"}]).encode()
        if path.startswith("/v2/account/activities/FILL"):
            return 200, b"[]"
        return 404, b"{}"


def _fixture(tmp_path):
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "hackA.json").write_text(json.dumps(
        {"t": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
         "positions": {"AAA": 100.0, "BBB": 50.0}}), encoding="utf-8")
    FM.append_jsonl(FM.grades_path(tmp_path), {"role": "hackA", "session": PREV.isoformat(), "equity": 9950.0})
    env = {"AAT_HACKA_KEY_ID": "good", "AAT_HACKA_SECRET_KEY": "s",
           "AAT_HACKB_KEY_ID": "dead", "AAT_HACKB_SECRET_KEY": "s"}
    return env


def test_one_row_per_account_names_the_401_and_the_missing_stop(tmp_path):
    env = _fixture(tmp_path)
    fake = FleetFake()
    rows = EOD.run_audit(["hackA", "hackB", "hackC"], env, run_id="r1", trigger="preclose_pass",
                         base=tmp_path, transport=fake)
    assert [r["role"] for r in rows] == ["hackA", "hackB", "hackC"]
    on_disk = FM.read_jsonl(EOD.audit_path(tmp_path))
    assert len(on_disk) == 3 and all(r["run_id"] == "r1" and r["places_orders"] is False for r in on_disk)
    a, b, c = rows
    assert b["status"] == "CREDENTIAL_INVALID" and b["credential"] == "INVALID_HTTP_401"
    assert c["status"] == "NO_CREDENTIAL"
    assert a["status"] == "DEGRADED" and a["credential"] == "OK"
    assert a["stops"]["missing"] == ["BBB"] and a["stops"]["n_protected"] == 1
    assert any(f.startswith("MISSING_STOP") for f in a["flags"])
    assert a["n_mismatches"] == 0 and a["reconciliation"]["state"]["status"] == "OK"
    assert a["reconciliation"]["grades"]["status"] == "OK"
    assert a["orders_today"] == {"n": 1, "ours": 1, "foreign": 0}
    assert {m for m, _ in fake.calls} == {"GET"}


def test_worst_case_arithmetic_at_the_accounts_stops(tmp_path):
    env = _fixture(tmp_path)
    a = EOD.run_audit(["hackA"], env, run_id="r2", trigger="manual", base=tmp_path,
                      transport=FleetFake(), write=False)[0]
    wc = a["worst_case"]
    # AAA: (50 - 45) x 100 = 500 at its stop; BBB has no stop -> whole 1,000
    assert wc["usd_at_stops"] == pytest.approx(1500.0)
    assert wc["pct_equity"] == pytest.approx(15.0)
    assert wc["gross_over_equity"] == pytest.approx(0.6)
    # n x largest notional% x widest stop%: 2 x 0.50 x 1.00 (BBB unprotected) of $10,000
    fb = wc["formula_bound"]
    assert (fb["n"], fb["notional_frac"], fb["stop_frac"]) == (2, 0.5, 1.0)
    assert fb["worst_usd"] == pytest.approx(10_000.0) and fb["worst_usd"] >= wc["usd_at_stops"]


def test_state_and_grade_mismatches_are_counted_with_examples(tmp_path):
    env = _fixture(tmp_path)
    (tmp_path / "state" / "hackA.json").write_text(json.dumps(
        {"t": datetime.now(timezone.utc).isoformat(), "positions": {"AAA": 90.0}}), encoding="utf-8")
    FM.append_jsonl(FM.grades_path(tmp_path), {"role": "hackA", "session": PREV.isoformat(), "equity": 9000.0})
    a = EOD.run_audit(["hackA"], env, run_id="r3", trigger="manual", base=tmp_path,
                      transport=FleetFake(), write=False)[0]
    assert a["status"] == "DEGRADED"
    st = a["reconciliation"]["state"]
    assert st["status"] == "MISMATCH" and st["n_mismatch"] == 2
    assert {e["symbol"] for e in st["examples"]} == {"AAA", "BBB"}
    assert a["reconciliation"]["grades"]["status"] == "MISMATCH"
    assert a["n_mismatches"] == 3 and a["mismatch_examples"]


def test_the_audit_transport_refuses_every_write_verb():
    t = EOD.readonly_transport(lambda *a: (200, b"{}"))
    assert t("GET", FM.TRADING_HOST + "/v2/account", {}, None) == (200, b"{}")
    for verb in ("POST", "DELETE", "PATCH", "PUT"):
        with pytest.raises(EOD.EodAuditRefusal):
            t(verb, FM.TRADING_HOST + "/v2/orders", {}, b"{}")
    v = FM.Venue("k", "s", transport=t)
    with pytest.raises(EOD.EodAuditRefusal):
        v.submit({"symbol": "AAA"})
    with pytest.raises(EOD.EodAuditRefusal):
        v.cancel("x")


def test_an_audit_of_no_roles_refuses(tmp_path):
    with pytest.raises(EOD.EodAuditRefusal):
        EOD.run_audit([], {}, run_id="r", trigger="manual", base=tmp_path)


# ─────────────────────────────── health ─────────────────────────────────────

def _preclose(tmp_path, run_id: str, started: datetime) -> None:
    runs = tmp_path / "paper_accounts" / "fleet_manager" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / f"run_{run_id}.json").write_text(json.dumps(
        {"schema": "fleet_manager_run/1", "run_id": run_id, "pass": "preclose",
         "started_utc": started.isoformat(), "finished_utc": started.isoformat(),
         "accounts": [{"role": "hack1", "status": "ok"}, {"role": "hack3", "status": "SKIPPED"}]}),
        encoding="utf-8")


def test_a_preclose_pass_without_its_audit_is_degraded(tmp_path):
    from types import SimpleNamespace

    from backend.services import task_receipts as TR
    from backend import config as _cfg
    ctx = SimpleNamespace(optimus_dir=tmp_path)
    since = TR.parse_stamp(_cfg.FLEET_EOD_AUDIT_SINCE_UTC)
    t = max(datetime.now(timezone.utc), since + timedelta(hours=1)).replace(microsecond=0)
    rid = t.strftime("%Y%m%dT%H%M%SZ") + "-abcdef"
    _preclose(tmp_path, rid, t)
    r = TR._fleet_pass("preclose")(ctx, None)
    assert r.status == "DEGRADED" and "no end-of-day audit row" in r.reason
    audit = tmp_path / "paper_accounts" / "fleet_manager" / "eod_audit" / "audit.jsonl"
    audit.parent.mkdir(parents=True)
    with audit.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": rid, "role": "hack1", "status": "OK"}) + "\n")
        f.write(json.dumps({"run_id": rid, "role": "hack3", "status": "CREDENTIAL_INVALID"}) + "\n")
    r2 = TR._fleet_pass("preclose")(ctx, None)
    assert r2.status == "OK", r2.reason             # hack3 is retired: excused by config, still named
    with audit.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"run_id": rid, "role": "hack2", "status": "DEGRADED", "why": "MISSING_STOP"}) + "\n")
    r3 = TR._fleet_pass("preclose")(ctx, None)
    assert r3.status == "DEGRADED" and "eod audit" in r3.reason
    # the open pass never needs an audit
    _o = tmp_path / "paper_accounts" / "fleet_manager" / "runs" / f"run_{rid}-open.json"
    _o.write_text(json.dumps({"run_id": "x", "pass": "open", "started_utc": t.isoformat(),
                              "accounts": [{"role": "hack1", "status": "ok"}]}), encoding="utf-8")
    assert TR._fleet_pass("open")(ctx, None).status == "OK"


def test_a_preclose_receipt_older_than_the_audit_is_excused(tmp_path):
    from types import SimpleNamespace

    from backend.services import task_receipts as TR
    from backend import config as _cfg
    t = TR.parse_stamp(_cfg.FLEET_EOD_AUDIT_SINCE_UTC) - timedelta(hours=1)
    _preclose(tmp_path, t.strftime("%Y%m%dT%H%M%SZ") + "-old000", t)
    r = TR._fleet_pass("preclose")(SimpleNamespace(optimus_dir=tmp_path), None)
    assert r.status == "OK"


def test_the_preclose_step_audits_every_role_and_a_failure_is_a_named_refusal(tmp_path, monkeypatch):
    from backend import config as _cfg
    from scripts import fleet_manager_run as RUN
    monkeypatch.setattr(FM, "root", lambda base=None: tmp_path if base is None else base)
    blk = RUN.eod_audit_step({}, "rid-1")
    assert blk["status"] == "ok" and blk["rows_written"] == len(_cfg.FLEET_MANAGER_ROLES)
    assert set(blk["accounts"].values()) == {"NO_CREDENTIAL"}
    assert len(FM.read_jsonl(EOD.audit_path())) == len(_cfg.FLEET_MANAGER_ROLES)

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(EOD, "run_audit", boom)
    bad = RUN.eod_audit_step({}, "rid-2")
    assert bad["status"].startswith("REFUSED") and bad["rows_written"] == 0
