"""Synthetic frozen inputs for the offline candidate; no provider claim."""

from copy import deepcopy
import base64
from datetime import date
import hashlib
import json

import pytest

from backend.services import pre_event_owner_warning as warning

OBSERVED = "2026-11-03T20:00:00Z"
CUTOFF = "2026-11-03T21:00:00Z"
NOW = "2026-11-03T21:01:00Z"


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def row(**changes):
    value = {"symbol": "AAPL", "date": "2026-11-06", "hour": "amc",
             "quarter": 4, "year": 2026, "epsEstimate": 1.5,
             "epsActual": None, "revenueEstimate": 100000000000,
             "revenueActual": None}
    value.update(changes)
    return value


def freeze(rows=None, *, observed=OBSERVED, cutoff=CUTOFF):
    rows = [row()] if rows is None else rows
    response = _canonical({"earningsCalendar": rows})
    decision_date = date.fromisoformat(cutoff[:10])
    packet = {
        "schema": warning.SCHEMA, "status": "EVIDENCE_ONLY", "source": warning.SOURCE,
        "ticker": "AAPL", "observed_utc": observed.replace("Z", "+00:00"),
        "cutoff_utc": cutoff.replace("Z", "+00:00"),
        "decision_date_et": decision_date.isoformat(), "event_date_et": rows[0]["date"],
        "days_ahead": (date.fromisoformat(rows[0]["date"]) - decision_date).days,
        "fiscal_year": rows[0]["year"],
        "fiscal_quarter": rows[0]["quarter"], "event_time_status": "UNKNOWN",
        "response_sha256": _sha(response),
        "response_bytes_b64": base64.b64encode(response).decode("ascii"),
        "forecast_status": "NOT_GENERATED", "runtime_authority": "NONE",
        "qualification": "Injected saved response; provider authenticity unverified.",
    }
    packet["input_id"] = _sha(_canonical(packet))
    return packet, response


def snapshot(*, held=True):
    positions = ([{"symbol": "AAPL", "qty": 10, "market_value": 1000,
                   "current_price": 100}] if held else
                 [{"symbol": "MSFT", "qty": 10, "market_value": 1000,
                   "current_price": 100}])
    return {"t": "2026-11-03T20:00:00Z", "tag": "sim_owner",
            "account_number": "APPROVED_PC_PAPER_ACCOUNT", "equity": 2000,
            "cash": 1000, "long_market_value": 1000, "short_market_value": 0,
            "n_positions": 1, "positions": positions}


def build(packet=None, response=None, account=None, **changes):
    default_packet, default_response = freeze()
    packet = default_packet if packet is None else packet
    response = default_response if response is None else response
    account = snapshot() if account is None else account
    account_bytes = _canonical(account) if type(account) is dict else account
    args = {"packet": packet, "response_bytes": response,
            "snapshot_bytes": account_bytes,
            "expected_snapshot_sha256": _sha(account_bytes),
            "expected_account_sha256": _sha(b"APPROVED_PC_PAPER_ACCOUNT"),
            "cutoff_utc": CUTOFF, "now_utc": NOW}
    args.update(changes)
    return warning.build_pre_event_warning_bytes(**args)


def test_held_provisional_is_pure_reproducible_and_conditional():
    first = build()
    assert first == build()
    assert first["status"] == "PROVISIONAL"
    assert first["event_date_et"] == "2026-11-06"
    assert first["conditional_loss_usd"] == {
        "5_percent_decline": "50.00", "10_percent_decline": "100.00"}
    assert first["forecast_status"] == "NO_CALIBRATED_EVENT_FORECAST"
    assert first["paper_decision"] == ["HOLD_EXISTING", "NO_NEW_BET", "REVIEW_NEW_EVIDENCE"]
    assert "direction" in first["interpretation"]
    assert len(first["event_id"]) == len(first["decision_id"]) == 64
    assert build(now_utc="2026-11-03T22:00:00Z")["decision_id"] == first["decision_id"]


@pytest.mark.parametrize("change", [
    {"packet": {}}, {"response_bytes": b"{"},
    {"response_bytes": b'\xff'}, {"response_bytes": b'{}'},
    {"response_bytes": b'{"earningsCalendar":[],"earningsCalendar":[]}'},
    {"response_bytes": b'{"earningsCalendar":[{'},
])
def test_malformed_or_mismatched_bytes_refused(change):
    assert build(**change)["status"] == "REFUSED"


def test_packet_recomputation_and_exact_response_binding():
    packet, response = freeze()
    changed = deepcopy(packet)
    changed["days_ahead"] = 4
    assert build(packet=changed, response=response)["reason"] == "PACKET_RECOMPUTATION_MISMATCH"
    changed = deepcopy(packet)
    changed["input_id"] = "0" * 64
    assert build(packet=changed, response=response)["status"] == "REFUSED"
    assert build(packet=packet, response=response + b" ")["status"] == "REFUSED"


@pytest.mark.parametrize("observed,cutoff,expected", [
    ("2026-11-03T21:00:01Z", CUTOFF, "OBSERVATION_AFTER_CUTOFF"),
    ("2026-11-02T20:59:59Z", CUTOFF, "OBSERVATION_STALE"),
    ("2026-11-02T21:00:00Z", CUTOFF, "PROVISIONAL"),
])
def test_observation_clock_boundaries(observed, cutoff, expected):
    packet, response = freeze(observed=observed, cutoff=cutoff)
    result = build(packet=packet, response=response, now_utc=cutoff)
    assert result["status"] == expected or result["reason"] == expected


def test_cutoff_now_and_et_window():
    assert build(cutoff_utc="2026-11-03T21:00:01Z")["reason"] == "CUTOFF_MISMATCH"
    assert build(now_utc="2026-11-03T20:59:59Z")["reason"] == "NOW_BEFORE_CUTOFF"
    packet, response = freeze([row(date="2026-11-03")])
    assert build(packet=packet, response=response)["reason"] == "EVENT_OUTSIDE_WINDOW"
    packet, response = freeze([row(date="2026-11-11")])
    assert build(packet=packet, response=response)["reason"] == "EVENT_OUTSIDE_WINDOW"


def test_presentation_freshness_and_et_event_start():
    packet, response = freeze(observed="2026-11-02T21:00:00Z")
    assert build(packet=packet, response=response)["reason"] == "OBSERVATION_STALE_AT_NOW"
    account = snapshot()
    account["t"] = "2026-11-02T21:00:00Z"
    assert build(account=account)["reason"] == "SNAPSHOT_STALE_AT_NOW"

    # Crossing the cutoff's ET civil date is allowed while inputs remain fresh.
    assert build(now_utc="2026-11-04T04:59:59Z")["status"] == "PROVISIONAL"
    assert build(now_utc="2026-11-04T05:00:00Z")["status"] == "PROVISIONAL"

    later_cutoff = "2026-11-05T21:00:00Z"
    packet, response = freeze(observed="2026-11-05T20:00:00Z", cutoff=later_cutoff)
    account = snapshot()
    account["t"] = "2026-11-05T20:00:00Z"
    assert build(packet=packet, response=response, account=account,
                 cutoff_utc=later_cutoff, now_utc="2026-11-06T04:59:59Z")["status"] == "PROVISIONAL"
    assert build(packet=packet, response=response, account=account,
                 cutoff_utc=later_cutoff, now_utc="2026-11-06T05:00:00Z")["reason"] == "EVENT_DATE_STARTED_ET"
    assert build(now_utc="2026-11-07T12:00:00Z")["status"] == "REFUSED"


@pytest.mark.parametrize("rows", [
    [row(), row()], [row(), row(date="2026-11-07")],
    [row(), row(quarter=1, year=2027, date="2026-11-07")],
])
def test_duplicate_or_conflicting_issuer_refused(rows):
    packet, response = freeze(rows)
    assert build(packet=packet, response=response)["reason"] == "ISSUER_SELECTION_AMBIGUOUS"


def test_actuals_and_unheld_refused():
    packet, response = freeze([row(epsActual=1.6)])
    assert build(packet=packet, response=response)["reason"] == "FUTURE_ACTUAL_PRESENT"
    assert build(account=snapshot(held=False))["reason"] == "NOT_HELD"


@pytest.mark.parametrize("mutation", [
    lambda s: s.update(cash=-1),
    lambda s: s.update(short_market_value=10),
    lambda s: s.update(margin_enabled=True),
    lambda s: s.update(equity=0),
    lambda s: s.update(t="2026-11-03T21:00:01Z"),
    lambda s: s.update(t="2026-11-02T20:59:59Z"),
    lambda s: s["positions"][0].update(current_price=99),
    lambda s: s["positions"][0].update(symbol="aapl"),
    lambda s: s["positions"][0].update(side="short"),
    lambda s: s["positions"][0].update(leverage=2),
    lambda s: s["positions"].append(deepcopy(s["positions"][0])),
])
def test_bad_account_or_snapshot_refused(mutation):
    account = snapshot()
    mutation(account)
    assert build(account=account)["status"] == "REFUSED"


def test_external_pin_is_required_and_binding():
    assert build(expected_snapshot_sha256="0" * 64)["reason"] == "SNAPSHOT_SHA256_MISMATCH"
    assert build(expected_account_sha256=None)["reason"] == "EXPECTED_ACCOUNT_HASH_REQUIRED"
    assert build(expected_account_sha256="0" * 64)["reason"] == "ACCOUNT_MISMATCH"
    account = snapshot()
    account["account_number"] = "OTHER_ACCOUNT"
    result = build(account=account)
    assert result["reason"] == "ACCOUNT_MISMATCH"
    assert "OTHER_ACCOUNT" not in json.dumps(result)
    account.pop("account_number")
    assert build(account=account)["reason"] == "ACCOUNT_REQUIRED"
    result = build()
    assert "APPROVED_PC_PAPER_ACCOUNT" not in json.dumps(result)
    assert "account_pin_sha256" not in result
    assert build(snapshot_bytes=b"not json", expected_snapshot_sha256=_sha(b"not json"))["status"] == "REFUSED"


def test_account_pin_hashes_exact_utf8_identity():
    account = snapshot()
    account["account_number"] = "PC-É"
    assert build(account=account, expected_account_sha256=_sha("PC-É".encode("utf-8")))["status"] == "PROVISIONAL"
    assert build(account=account, expected_account_sha256=_sha(_canonical("PC-É")))["reason"] == "ACCOUNT_MISMATCH"
