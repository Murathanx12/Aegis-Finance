"""Offline, fake-venue tests for the late-fill stop-only consumer."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.services import fleet_manager as FM
from backend.services import fleet_protect_only as FP
from scripts import fleet_protect_only as CLI


class FakeVenue:
    def __init__(self, base, *, held=10, stop=0, other_sell=0):
        self.base = base
        self.held = held
        self.stop = stop
        self.stop_filled = 0
        self.stop_status = "accepted"
        self.other_sell = other_sell
        self.account_number = "offline-paper"
        self.posts = 0
        self.orders_by_coid = {}
        self.raise_after_post = False
        self.record_post = True
        self.closed = False
        self.price = 100
        self.next_price = None
        self.next_held = None
        self.position_reads = 0
        self.fill_order_id = "owned-buy"
        self.fill_time = datetime.now(timezone.utc).isoformat()

    def clock(self):
        now = datetime.now(timezone.utc)
        return {"timestamp": now.isoformat(), "is_open": not self.closed,
                "next_close": (now + timedelta(hours=2)).isoformat()}

    def account(self):
        px = self.next_price if self.position_reads and self.next_price is not None else self.price
        held = self.next_held if self.position_reads and self.next_held is not None else self.held
        return {"account_number": self.account_number,
                "equity": str(100000 - self.held * 100 + held * px),
                "cash": str(100000 - self.held * 100)}

    def positions(self):
        self.position_reads += 1
        px = self.next_price if self.position_reads > 1 and self.next_price is not None else self.price
        held = self.next_held if self.position_reads > 1 and self.next_held is not None else self.held
        return [{"symbol": "CCI", "qty": str(held),
                 "current_price": str(px), "market_value": str(held * px),
                 "asset_class": "us_equity"}] if self.held else []

    def open_orders(self):
        rows = []
        if self.stop:
            rows.append({"id": "old-stop", "symbol": "CCI", "side": "sell",
                         "type": "stop", "qty": str(self.stop),
                         "filled_qty": str(self.stop_filled),
                         "stop_price": "90", "time_in_force": "gtc",
                         "status": self.stop_status})
        if self.other_sell:
            rows.append({"id": "old-sell", "symbol": "CCI", "side": "sell",
                         "type": "limit", "qty": str(self.other_sell), "filled_qty": "0",
                         "status": "accepted"})
        rows.extend(o for o in self.orders_by_coid.values() if o["status"] == "accepted")
        return rows

    def fills(self, *, after):
        return [{"id": "owned-fill", "activity_type": "FILL",
                 "symbol": "CCI", "side": "buy", "qty": str(self.held),
                 "order_id": self.fill_order_id,
                 "transaction_time": self.fill_time}]

    def orders_since(self, _):
        return []

    def order_by_coid(self, coid):
        return self.orders_by_coid.get(coid)

    def submit(self, body):
        assert FM.read_jsonl(FM.decisions_path(self.base))[-1]["row"] == "decision"
        assert body["side"] == "sell" and body["type"] == "stop"
        self.posts += 1
        row = {"id": f"new-{self.posts}", "symbol": "CCI", "side": "sell",
               "type": "stop", "qty": body["qty"], "filled_qty": "0",
               "stop_price": body["stop_price"], "time_in_force": body["time_in_force"],
               "client_order_id": body["client_order_id"], "status": "accepted"}
        if not self.raise_after_post:
            if self.record_post:
                self.orders_by_coid[body["client_order_id"]] = row
            return 201, row
        raise FM.FleetRefusal("POST acknowledgement lost")


def setup_owned(tmp_path):
    body = {"schema": "fleet_manager_contract/1", "role": "hack6", "version": "v2",
            "licence": FM.LICENCE, "alpha_source": "offline", "selection": {"kind": "news_sleeve"},
            "legacy_terms": {"expected_horizon_sessions": 21},
            "stop_rule": FM.stop_rule_block(0.10), "caps": FM.caps_block(),
            "costs": FM.costs_block()}
    contract = FM.freeze_contract(body, base=tmp_path)
    state_t = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    FM.atomic_write_json(FM.state_path("hack6", tmp_path),
                         {"t": state_t, "positions": {},
                          "run_id": "owner", "contract": "v2",
                          "policy_hash": contract["policy_hash"]})
    FM.atomic_write_json(FM.root(tmp_path) / "runs" / "run_owner.json",
                         {"run_id": "owner", "accounts": [{"role": "hack6", "status": "ok",
                                        "state_written": state_t,
                                        "account_number": "offline-paper",
                                        "contract_active": {"policy_hash": contract["policy_hash"]}}]})
    FM.append_jsonl(FM.decisions_path(tmp_path), {
        "row": "decision", "run_id": "owner", "role": "hack6", "coid": "owned-buy-coid",
        "mode": "LIVE", "type": "limit", "kind": "buy", "symbol": "CCI",
        "side": "buy", "qty": 10})
    FM.append_jsonl(FM.decisions_path(tmp_path), {
        "row": "outcome", "run_id": "owner", "role": "hack6", "coid": "owned-buy-coid",
        "outcome": "submitted filled id owned-buy", "order_id": "owned-buy"})
    modes = {"hack6": {"contract": "v2", "maintenance": "LIVE", "entries": "LIVE"}}
    FM.atomic_write_json(FM.modes_path(tmp_path), modes)
    return modes


def run(tmp_path, venue, modes, *, live=False):
    return FP.protect_once("hack6", "CCI", venue, modes, {"CCI": 0.02},
                           live=live, base=tmp_path)


def test_late_fill_dry_then_live_protects_once(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    dry = run(tmp_path, venue, modes)
    assert dry["status"] == "DRY_PLAN" and dry["qty"] == 10 and venue.posts == 0
    assert len(FM.read_jsonl(FM.decisions_path(tmp_path))) == 2
    live = run(tmp_path, venue, modes, live=True)
    assert live["status"] == "PROTECTED" and venue.posts == 1
    assert run(tmp_path, venue, modes, live=True)["status"] == "ALREADY_COVERED"
    assert venue.posts == 1
    rows = FM.read_jsonl(FM.decisions_path(tmp_path))
    assert [r["row"] for r in rows[-2:]] == ["decision", "outcome"]


def test_partial_stop_and_other_sell_reservation_size_only_free_shares(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path, stop=4, other_sell=2)
    result = run(tmp_path, venue, modes, live=True)
    assert result["status"] == "PROTECTED" and result["qty"] == 4
    assert venue.posts == 1
    assert sum(float(o["qty"]) for o in venue.open_orders() if o["type"] == "stop") == 8
    with pytest.raises(FM.FleetRefusal, match="no unreserved long shares"):
        run(tmp_path, venue, modes)


def test_partial_filled_stop_counts_remaining_not_original_quantity(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path, stop=8)
    venue.stop_filled = 4
    result = run(tmp_path, venue, modes, live=True)
    assert result["status"] == "PROTECTED" and result["qty"] == 6


def test_quote_tick_changes_mark_but_preserves_valid_stop(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    venue.next_price = 101
    result = run(tmp_path, venue, modes, live=True)
    assert result["status"] == "PROTECTED" and venue.posts == 1


@pytest.mark.parametrize("next_price", [90, 120])
def test_fresh_quote_reprices_stop_under_frozen_rule(tmp_path, next_price):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    venue.next_price = next_price
    result = run(tmp_path, venue, modes, live=True)
    assert result["status"] == "PROTECTED" and venue.posts == 1
    assert result["stop_price"] == FM.stop_price_for(next_price, 0.06)


def test_final_boundary_refuses_held_race(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    venue.next_held = 9
    with pytest.raises(FM.FleetRefusal, match="held quantity or sell reservations changed"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


def test_already_covered_and_closed_venue_refuse_live(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path, stop=10)
    assert run(tmp_path, venue, modes, live=True)["status"] == "ALREADY_COVERED"
    venue.stop = 0
    venue.closed = True
    assert run(tmp_path, venue, modes)["status"] == "DRY_PLAN"
    with pytest.raises(FM.FleetRefusal, match="venue closed"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


def test_pending_cancel_stop_is_not_claimed_as_cover(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path, stop=10)
    venue.stop_status = "pending_cancel"
    with pytest.raises(FM.FleetRefusal, match="not proven resting"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


def test_duplicate_fill_id_cannot_make_ten_shares_from_two_fives(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    fill = {"id": "same-fill", "activity_type": "FILL", "symbol": "CCI",
            "side": "buy", "qty": "5", "order_id": "owned-buy",
            "transaction_time": datetime.now(timezone.utc).isoformat()}
    venue.fills = lambda **_: [dict(fill), dict(fill)]
    with pytest.raises(FM.FleetRefusal, match="fill identity duplicate"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


def test_distinct_partial_fills_match_accepted_buy_quantity(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    fill = {"activity_type": "FILL", "symbol": "CCI", "side": "buy",
            "qty": "5", "order_id": "owned-buy",
            "transaction_time": datetime.now(timezone.utc).isoformat()}
    venue.fills = lambda **_: [dict(fill, id="first"), dict(fill, id="second")]
    assert run(tmp_path, venue, modes, live=True)["status"] == "PROTECTED"
    assert venue.posts == 1


@pytest.mark.parametrize("change", [
    {"symbol": "OTHER"}, {"side": "sell"}, {"qty": "11"},
])
def test_fill_must_match_accepted_order_shape(tmp_path, change):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    original = venue.fills
    venue.fills = lambda **kw: [{**original(**kw)[0], **change}]
    with pytest.raises(FM.FleetRefusal):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


@pytest.mark.parametrize("bad_price", ["NaN", "0", "100"])
def test_invalid_existing_stop_price_never_counts_as_cover(tmp_path, bad_price):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path, stop=10)
    original = venue.open_orders
    def bad_stops():
        rows = original()
        for row in rows:
            row["stop_price"] = bad_price
        return rows
    venue.open_orders = bad_stops
    with pytest.raises(FM.FleetRefusal, match="stop price"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


@pytest.mark.parametrize("corruption", ["ack_qty", "ack_stop", "resting_qty", "duplicate_open",
                                        "duplicate_position"])
def test_corrupt_post_evidence_stays_unknown_and_never_retries(tmp_path, corruption):
    modes = setup_owned(tmp_path)
    class CorruptVenue(FakeVenue):
        def submit(self, body):
            status, ack = super().submit(body)
            if corruption == "ack_qty":
                ack["qty"] = "5"
            if corruption == "ack_stop":
                ack["stop_price"] = "1"
            if corruption == "resting_qty":
                ack = dict(ack)
                self.orders_by_coid[body["client_order_id"]]["qty"] = "5"
            return status, ack
        def open_orders(self):
            rows = super().open_orders()
            return rows + rows if corruption == "duplicate_open" and self.posts else rows
        def positions(self):
            rows = super().positions()
            return rows + rows if corruption == "duplicate_position" and self.posts else rows
    venue = CorruptVenue(tmp_path)
    assert run(tmp_path, venue, modes, live=True)["status"] == "SUBMIT_UNKNOWN"
    assert venue.posts == 1
    if corruption in {"ack_qty", "ack_stop"}:
        # Restore the broker's fake view to 404 to prove durable uncertainty,
        # not a current-open-order guard, is what prevents a resend.
        venue.orders_by_coid.clear()
        with pytest.raises(FM.FleetRefusal, match="prior LIVE stop intent"):
            run(tmp_path, venue, modes, live=True)
        assert venue.posts == 1


def test_lost_ack_and_broker_404_never_retry(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    venue.raise_after_post = True
    assert run(tmp_path, venue, modes, live=True)["status"] == "SUBMIT_UNKNOWN"
    assert venue.posts == 1 and venue.orders_by_coid == {}
    with pytest.raises(FM.FleetRefusal, match="prior LIVE stop intent"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 1


def test_accepted_ack_without_resting_stop_stays_unknown(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    venue.record_post = False
    assert run(tmp_path, venue, modes, live=True)["status"] == "SUBMIT_UNKNOWN"
    with pytest.raises(FM.FleetRefusal, match="prior LIVE stop intent"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 1


def test_post_unknown_blocks_next_session_new_client_id(tmp_path, monkeypatch):
    modes = setup_owned(tmp_path)
    class DuplicatedResting(FakeVenue):
        def open_orders(self):
            rows = super().open_orders()
            return rows + rows if self.posts else rows
    venue = DuplicatedResting(tmp_path)
    first = run(tmp_path, venue, modes, live=True)
    assert first["status"] == "SUBMIT_UNKNOWN" and venue.posts == 1
    assert FM.read_jsonl(FM.decisions_path(tmp_path))[-1]["verification"] == "SUBMIT_UNKNOWN"
    venue.orders_by_coid.clear()  # broker 404 next day is not proof of no POST
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return tomorrow
    venue.clock = lambda: {"timestamp": tomorrow.isoformat(), "is_open": True,
                           "next_close": (tomorrow + timedelta(hours=2)).isoformat()}
    with monkeypatch.context() as patcher:
        patcher.setattr(FP, "datetime", FakeDateTime)
        with pytest.raises(FM.FleetRefusal, match="prior LIVE stop intent"):
            run(tmp_path, venue, modes, live=True)
    assert venue.posts == 1


@pytest.mark.parametrize("where", ["ack", "resting"])
def test_day_tif_cannot_certify_protective_stop(tmp_path, where):
    modes = setup_owned(tmp_path)
    class DayVenue(FakeVenue):
        def submit(self, body):
            status, ack = super().submit(body)
            if where == "ack":
                ack = dict(ack, time_in_force="day")
            else:
                ack = dict(ack)
                self.orders_by_coid[body["client_order_id"]]["time_in_force"] = "day"
            return status, ack
    venue = DayVenue(tmp_path)
    assert run(tmp_path, venue, modes, live=True)["status"] == "SUBMIT_UNKNOWN"
    assert venue.posts == 1


def test_existing_day_stop_is_not_gtc_cover(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path, stop=10)
    original = venue.open_orders
    venue.open_orders = lambda: [dict(o, time_in_force="day") for o in original()]
    with pytest.raises(FM.FleetRefusal, match="not GTC"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


def test_identity_stop_file_and_nonfinite_held_refuse(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    venue.account_number = "wrong-account"
    with pytest.raises(FM.FleetRefusal, match="broker account"):
        run(tmp_path, venue, modes, live=True)
    venue.account_number = "offline-paper"
    venue.held = float("nan")
    with pytest.raises(FM.FleetRefusal, match="nonfinite"):
        run(tmp_path, venue, modes, live=True)
    venue.held = 10
    FM.stop_file(tmp_path).write_text("STOP", encoding="utf-8")
    with pytest.raises(FM.FleetRefusal, match="STOP"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


def test_unowned_fill_corrupt_ledger_and_competing_writer_refuse(tmp_path):
    modes = setup_owned(tmp_path)
    venue = FakeVenue(tmp_path)
    venue.fill_order_id = "foreign"
    with pytest.raises(FM.FleetRefusal, match="not accepted-owned"):
        run(tmp_path, venue, modes, live=True)
    venue.fill_order_id = "owned-buy"
    with FM.role_writer_lock("hack6", tmp_path):
        with pytest.raises(FM.FleetRefusal, match="another fleet writer"):
            run(tmp_path, venue, modes, live=True)
    with FM.decisions_path(tmp_path).open("a", encoding="utf-8") as fh:
        fh.write("{corrupt\n")
    with pytest.raises(FM.FleetRefusal, match="ledger unreadable"):
        run(tmp_path, venue, modes, live=True)
    assert venue.posts == 0


@pytest.mark.parametrize("live,expected", [(False, "DRY_PLAN"), (True, "PROTECTED")])
def test_actual_cli_uses_one_shot_consumer(tmp_path, monkeypatch, capsys,
                                          live, expected):
    modes = setup_owned(tmp_path)
    FM.atomic_write_json(FM.modes_path(tmp_path), modes)
    venue = FakeVenue(tmp_path)
    real_root = FM.root
    monkeypatch.setattr(FM, "root", lambda base=None: real_root(base or tmp_path))
    monkeypatch.setattr(CLI.RUN, "read_env_file", lambda _: {
        "AAT_HACK6_KEY_ID": "offline", "AAT_HACK6_SECRET_KEY": "offline"})
    monkeypatch.setattr(FM, "Venue", lambda *_: venue)
    monkeypatch.setattr(CLI.RUN, "panel_sigma_and_screen",
                        lambda _: ({"CCI": 0.02}, {}, {}))
    argv = ["--role", "hack6", "--symbol", "CCI"] + (["--live"] if live else [])
    assert CLI.main(argv) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == expected and venue.posts == int(live)
