"""Real sweep CLI with a fake HTTP transport; no paper account requests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import pytest

from backend.services import fleet_manager as FM
from backend.services import fleet_protect_only as FP
from backend.tests.test_fleet_protect_only import FakeVenue, setup_owned
from scripts import fleet_protect_sweep as CLI


def _ready(tmp_path, monkeypatch, *, held=10, stop=0, other_sell=0):
    modes = setup_owned(tmp_path)
    modes.update({r: {"skip": "offline inactive fixture"} for r in FM._cfg.FLEET_MANAGER_ROLES
                  if r != "hack6"})
    FM.atomic_write_json(FM.modes_path(tmp_path), modes)
    receipt_path = FM.root(tmp_path) / "runs" / "run_owner.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.update({"pass": "open", "live_flag": True,
                    "finished_utc": datetime.now(timezone.utc).isoformat()})
    FM.atomic_write_json(receipt_path, receipt)
    venue = FakeVenue(tmp_path, held=held, stop=stop, other_sell=other_sell)
    root = FM.root
    monkeypatch.setattr(FM, "root", lambda base=None: root(base or tmp_path))
    monkeypatch.setattr(CLI.RUN, "read_env_file", lambda _: {
        "AAT_HACK6_KEY_ID": "offline", "AAT_HACK6_SECRET_KEY": "offline"})
    monkeypatch.setattr(CLI.RUN, "panel_sigma_and_screen", lambda _: ({"CCI": 0.02}, {}, {}))
    monkeypatch.setattr(FP, "_sweep_clock", lambda _clock, _now: datetime.now(
        timezone.utc).astimezone(ZoneInfo("America/New_York")).date().isoformat())
    methods = []

    def transport(method, url, _headers, body):
        path = urlparse(url).path
        query = parse_qs(urlparse(url).query)
        methods.append((method, path))
        if method == "POST":
            assert path == "/v2/orders"
            status, result = venue.submit(json.loads(body))
        elif path == "/v2/clock":
            status, result = 200, venue.clock()
        elif path == "/v2/account":
            status, result = 200, venue.account()
        elif path == "/v2/positions":
            status, result = 200, venue.positions()
        elif path == "/v2/orders":
            status, result = 200, (venue.open_orders() if query.get("status") == ["open"]
                                   else venue.orders_since(query.get("after", [""])[0]))
        elif path == "/v2/account/activities/FILL":
            status, result = 200, venue.fills(after=query.get("after", [""])[0])
        elif path == "/v2/orders:by_client_order_id":
            result = venue.order_by_coid(query["client_order_id"][0])
            status = 200 if result else 404
            result = result or {"message": "not found"}
        else:
            raise AssertionError((method, path))
        return status, json.dumps(result).encode()

    return modes, venue, transport, methods


@pytest.mark.parametrize("stop,other_sell", [(10, 0), (4, 6)])
def test_actual_cli_fully_reserved_is_zero_action(tmp_path, monkeypatch, capsys, stop, other_sell):
    _, venue, transport, methods = _ready(tmp_path, monkeypatch,
                                          stop=stop, other_sell=other_sell)
    assert CLI.main(["--live"], transport=transport) == 0
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "ALREADY_COVERED" and row["requests_upper_bound"] <= 180
    assert venue.posts == 0 and all(method == "GET" for method, _ in methods)
    assert len(list((FM.root() / "sweeps").glob("sweep_*.json"))) == 1


def test_actual_cli_late_fill_one_stop_then_noop(tmp_path, monkeypatch, capsys):
    _, venue, transport, methods = _ready(tmp_path, monkeypatch)
    assert CLI.main(["--live"], transport=transport) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "PROTECTED" and venue.posts == 1
    assert sum(method == "POST" for method, _ in methods) == 1
    assert CLI.main(["--live"], transport=transport) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["status"] == "ALREADY_COVERED" and venue.posts == 1
    assert all(path != "/v2/orders" or method != "DELETE" for method, path in methods)


@pytest.mark.parametrize("replacement_pass,prior_held", [
    ("preclose", 10), ("open", 10), ("open", 0)])
def test_actual_cli_owner_handoff_after_selection_refuses_before_post(
        tmp_path, monkeypatch, capsys, replacement_pass, prior_held):
    _, venue, transport, methods = _ready(tmp_path, monkeypatch)
    state_path = FM.state_path("hack6")

    def sigma_with_owner_handoff(_symbols):
        # Legitimate manager takes the same role lock after discovery but before
        # the sweep's final locked stop preflight.
        with FM.role_writer_lock("hack6"):
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.update(run_id="replacement-owner", t=datetime.now(timezone.utc).isoformat(),
                         positions={"CCI": prior_held} if prior_held else {})
            FM.atomic_write_json(state_path, state)
            receipt = {"run_id": "replacement-owner", "pass": replacement_pass,
                       "live_flag": True, "finished_utc": datetime.now(timezone.utc).isoformat(),
                       "accounts": [{"role": "hack6", "status": "ok", "state_written": state["t"],
                                     "account_number": "offline-paper",
                                     "contract_active": {"policy_hash": state["policy_hash"]}}]}
            FM.atomic_write_json(FM.root() / "runs" / "run_replacement-owner.json", receipt)
            venue.fills = lambda **_: [] if prior_held else [{
                "id": "owned-fill", "activity_type": "FILL", "symbol": "CCI", "side": "buy",
                "qty": "10", "order_id": "owned-buy", "transaction_time": datetime.now(timezone.utc).isoformat()}]
        return {"CCI": 0.02}, {}, {}

    monkeypatch.setattr(CLI.RUN, "panel_sigma_and_screen", sigma_with_owner_handoff)
    assert CLI.main(["--live"], transport=transport) == 2
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "INCOMPLETE"
    assert row["candidates"][0]["status"] == "REFUSED"
    assert venue.posts == 0 and all(method != "POST" for method, _ in methods)


def test_actual_cli_clock_closes_after_discovery_refuses_before_post(tmp_path, monkeypatch, capsys):
    _, venue, transport, methods = _ready(tmp_path, monkeypatch)
    def sigma_then_close(_symbols):
        venue.closed = True
        return {"CCI": 0.02}, {}, {}
    monkeypatch.setattr(CLI.RUN, "panel_sigma_and_screen", sigma_then_close)
    assert CLI.main(["--live"], transport=transport) == 2
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "INCOMPLETE"
    assert venue.posts == 0 and all(method != "POST" for method, _ in methods)


def test_actual_cli_dry_and_unowned_fill_refuse(tmp_path, monkeypatch, capsys):
    _, venue, transport, methods = _ready(tmp_path, monkeypatch)
    assert CLI.main([], transport=transport) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "DRY_PLAN"
    assert venue.posts == 0 and all(method == "GET" for method, _ in methods)
    venue.fill_order_id = "unowned"
    assert CLI.main(["--live"], transport=transport) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"
    assert venue.posts == 0


def test_actual_cli_post_unknown_is_durable_and_next_sweep_cannot_retry(tmp_path, monkeypatch, capsys):
    _, venue, transport, methods = _ready(tmp_path, monkeypatch)
    venue.raise_after_post = True
    assert CLI.main(["--live"], transport=transport) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "INCOMPLETE"
    assert venue.posts == 1
    assert CLI.main(["--live"], transport=transport) == 2
    second = json.loads(capsys.readouterr().out)
    assert second["status"] == "REFUSED" and "unresolved prior stop intent" in second["why"]
    assert venue.posts == 1 and sum(method == "POST" for method, _ in methods) == 1


def test_missing_completed_open_owner_is_not_healthy_coverage(tmp_path, monkeypatch, capsys):
    _, venue, transport, _ = _ready(tmp_path, monkeypatch, stop=10)
    receipt_path = FM.root() / "runs" / "run_owner.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.pop("finished_utc")
    FM.atomic_write_json(receipt_path, receipt)
    assert CLI.main(["--live"], transport=transport) == 2
    row = json.loads(capsys.readouterr().out)
    assert row["status"] == "REFUSED" and "completed OPEN" in row["why"]
    assert venue.posts == 0


def test_existing_holding_and_truncated_orders_refuse_before_post(tmp_path, monkeypatch, capsys):
    _, venue, transport, _ = _ready(tmp_path, monkeypatch)
    path = FM.state_path("hack6")
    state = json.loads(path.read_text(encoding="utf-8"))
    state["positions"] = {"CCI": 5}
    FM.atomic_write_json(path, state)
    assert CLI.main(["--live"], transport=transport) == 2
    assert "pre-existing holding" in json.loads(capsys.readouterr().out)["why"]
    assert venue.posts == 0
    state["positions"] = {}
    FM.atomic_write_json(path, state)
    venue.open_orders = lambda: [{"id": f"o-{i}", "symbol": "OTHER", "side": "sell",
                                  "type": "limit", "qty": "1", "filled_qty": "0"}
                                 for i in range(500)]
    assert CLI.main(["--live"], transport=transport) == 2
    assert "500" in json.loads(capsys.readouterr().out)["why"]
    assert venue.posts == 0


def test_duplicate_fill_and_nested_order_refuse_before_post(tmp_path, monkeypatch, capsys):
    _, venue, transport, _ = _ready(tmp_path, monkeypatch)
    original_fills = venue.fills
    venue.fills = lambda **kw: original_fills(**kw) * 2
    assert CLI.main(["--live"], transport=transport) == 2
    assert "duplicate" in json.loads(capsys.readouterr().out)["why"]
    assert venue.posts == 0
    venue.fills = original_fills
    original_orders = venue.open_orders
    venue.open_orders = lambda: original_orders() + [{"id": "nested", "symbol": "CCI",
        "side": "sell", "type": "stop", "qty": "1", "filled_qty": "0", "legs": [{}]}]
    assert CLI.main(["--live"], transport=transport) == 2
    assert "nested order" in json.loads(capsys.readouterr().out)["why"]
    assert venue.posts == 0


def test_clock_cutoff_weekend_stale_and_closed_refuse():
    now = datetime(2026, 10, 9, 19, 16, tzinfo=timezone.utc)  # 15:16 ET
    clock = {"timestamp": now.isoformat(), "is_open": True,
             "next_close": (now + timedelta(minutes=44)).isoformat()}
    with pytest.raises(FM.FleetRefusal, match="preclose safety"):
        FP._sweep_clock(clock, now)
    clock["is_open"] = False
    with pytest.raises(FM.FleetRefusal, match="closed"):
        FP._sweep_clock(clock, now)
    clock["is_open"] = True
    with pytest.raises(FM.FleetRefusal, match="stale"):
        FP._sweep_clock(clock, now + timedelta(minutes=1))
    winter = datetime(2026, 12, 4, 19, 16, tzinfo=timezone.utc)  # 14:16 ET, task at 19:30 UTC
    clock = {"timestamp": winter.isoformat(), "is_open": True,
             "next_close": (winter + timedelta(minutes=104)).isoformat()}
    with pytest.raises(FM.FleetRefusal, match="preclose safety"):
        FP._sweep_clock(clock, winter)


def test_budget_refuses_instead_of_reporting_healthy_zero(tmp_path, monkeypatch, capsys):
    _, venue, transport, _ = _ready(tmp_path, monkeypatch, stop=10)
    budget_type = FP.SweepBudget
    monkeypatch.setattr(CLI.FP, "SweepBudget", lambda: budget_type(requests=0))
    assert CLI.main(["--live"], transport=transport) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REFUSED"
    assert venue.posts == 0
