"""E3 pinned, offline, single-event display contract."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from backend.services import owner_decision_view as V
from backend.services import provisional_event_review as E


EARLY = "2026-11-02T12:00:00Z"
CUTOFF = "2026-11-03T21:00:00Z"
REVIEW = "2026-11-05T08:00:00Z"
LATE = "2026-11-04T12:00:00Z"
WITNESS = "b" * 64


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source(*, key="article:a", event="event:one", body=b"LICENSED_BODY_SENTINEL",
           seen=EARLY, version=EARLY):
    return E.SourceItem(key, event, body, seen, version, None,
                        E.SourceProof(sha(body), version, WITNESS))


def build(items, edges=(), held=None, *, complete=True, upstream="UNKNOWN"):
    return E.build_review(sources=items, issuer_edges=edges, holdings=held,
                          review_time_utc=REVIEW, source_cutoff_utc=CUTOFF,
                          input_complete=complete, upstream_state=upstream,
                          upstream_exit_code=17 if upstream == "BUDGET_REFUSED" else None)


def fixture(tmp_path, items=None, receipt=None):
    items = items or [source()]
    receipt = receipt or build(items)
    receipt_file = tmp_path / "receipt.json"
    data = E._canonical(receipt) + b"\n"
    receipt_file.write_bytes(data)
    pins = []
    for item in items:
        file = tmp_path / (item.source_key.replace(":", "_") + ".raw")
        file.write_bytes(item.payload)
        pins.append(V.SourcePin(item.source_key, sha(item.payload), file))
    return receipt_file, sha(data), pins, receipt


def view(path, digest, pins, **kw):
    return V.build_owner_decision_view(receipt_path=path, receipt_sha256=digest,
                                       source_pins=pins, **kw)


def rewrite(path, receipt):
    body = {k: v for k, v in receipt.items() if k != "receipt_id"}
    receipt["receipt_id"] = sha(E._canonical(body))
    data = E._canonical(receipt) + b"\n"
    path.write_bytes(data)
    return sha(data)


def test_valid_replay_and_no_raw_body(tmp_path):
    path, digest, pins, receipt = fixture(tmp_path)
    first = view(path, digest, pins)
    assert first == view(path, digest, pins)
    assert first["status"] == "CANDIDATE_FOR_OWNER_REVIEW"
    assert first["decision"] == "NO_CHANGE_WITH_REASON"
    assert first["owner_decision"] == "UNOBSERVED"
    assert first["delivery"] == "NOT_ATTEMPTED"
    assert first["holdings"]["status"] == "UNKNOWN"
    assert first["event_id"] == receipt["groups"][0]["event_id"]
    assert "LICENSED_BODY_SENTINEL" not in json.dumps(first)
    assert set(tmp_path.iterdir()) == {path, pins[0].absolute_local_path}


def test_new_version_changes_view_but_not_event_id(tmp_path):
    old = source()
    path, digest, pins, _ = fixture(tmp_path, [old])
    before = view(path, digest, pins)
    new = source(body=b"NEW_VERSION_BODY", version="2026-11-03T12:00:00Z")
    path2, digest2, pins2, _ = fixture(tmp_path, [new])
    after = view(path2, digest2, pins2)
    assert before["event_id"] == after["event_id"]
    assert before["receipt_id"] != after["receipt_id"]
    assert before["view_id"] != after["view_id"]


def test_budget_partial_unknown_remain_explicit(tmp_path):
    item = source()
    path, digest, pins, _ = fixture(tmp_path, [item], build([item], complete=False,
                                                            upstream="BUDGET_REFUSED"))
    candidate = view(path, digest, pins)
    assert candidate["upstream_digest"] == {"state": "BUDGET_REFUSED", "exit_code": 17,
                                             "parse_status": "UNKNOWN"}
    assert candidate["coverage"]["status"] == "PARTIAL"
    assert candidate["holdings"]["status"] == "UNKNOWN"
    assert "PARTIAL_INPUT_COVERAGE_UNKNOWN" in candidate["reason_codes"]


@pytest.mark.parametrize("relation,basis,symbol", [
    ("ISSUER_CANDIDATE", "SEC_CIK", None),
    ("ISSUER_CANDIDATE", "FULL_ISSUER_SUBJECT", None),
    ("DISCOVERY_CONTEXT", "QUEUE_CONTEXT", "US:TGT"),
])
def test_caller_claims_never_become_direct_held(tmp_path, relation, basis, symbol):
    item = source()
    edge = E.IssuerEdge(item.source_key, sha(item.payload), "cik:111111", symbol,
                        relation, basis, EARLY, WITNESS)
    held = E.HoldingsSnapshot(EARLY, EARLY, ("US:TGT", "US:XYZ"), WITNESS, True)
    path, digest, pins, _ = fixture(tmp_path, [item], build([item], [edge], held))
    candidate = view(path, digest, pins)
    assert candidate["decision"] == "NO_CHANGE_WITH_REASON"
    assert candidate["caller_supplied_indirect_symbol_matches"] == []
    assert "DIRECT_ISSUER" not in json.dumps(candidate)
    assert "PIT_VERIFIED" not in json.dumps(candidate)


def test_indirect_is_labeled_caller_hypothesis(tmp_path):
    item = source()
    edge = E.IssuerEdge(item.source_key, sha(item.payload), "cik:111111", "US:XYZ",
                        "INDIRECT_CANDIDATE", "CALLER_DESCRIBED_MECHANISM", EARLY, WITNESS)
    held = E.HoldingsSnapshot(EARLY, EARLY, ("US:XYZ",), WITNESS, True)
    path, digest, pins, _ = fixture(tmp_path, [item], build([item], [edge], held))
    candidate = view(path, digest, pins)
    assert candidate["decision"] == "REVIEW_EXPOSURE"
    assert candidate["relation_status"] == "CALLER_SUPPLIED_INDIRECT_HYPOTHESIS"
    assert candidate["holdings"]["authority"] == "CALLER_SUPPLIED_NOT_VERIFIED"
    assert candidate["caller_supplied_indirect_symbol_matches"] == ["US:XYZ"]


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(delivery="SENT_TO_OWNER"),
    lambda r: r.update(forecast_generated=True),
    lambda r: r.update(owner_decision="APPROVED"),
    lambda r: r.update(listing_identity="PIT_VERIFIED"),
    lambda r: r.update(licensed_body="raw article"),
    lambda r: r["groups"][0]["sources"][0].update(body="raw article"),
    lambda r: r["groups"][0].update(event_id="0" * 64),
    lambda r: r["groups"][0]["sources"][0].update(first_seen_utc=LATE),
    lambda r: r["groups"][0]["sources"][0].update(proof_known_at_utc=LATE),
])
def test_self_rehashed_false_claims_and_clocks_refuse(tmp_path, mutation):
    path, _, pins, receipt = fixture(tmp_path)
    mutation(receipt)
    digest = rewrite(path, receipt)
    with pytest.raises(V.ViewRefused):
        view(path, digest, pins)


def test_multiple_groups_and_duplicate_source_identity_refuse(tmp_path):
    a, b = source(), source(key="article:b", event="event:two", body=b"OTHER")
    path, digest, pins, _ = fixture(tmp_path, [a, b], build([a, b]))
    with pytest.raises(V.ViewRefused):
        view(path, digest, pins)
    path, _, pins, receipt = fixture(tmp_path, [a])
    receipt["groups"][0]["sources"].append(receipt["groups"][0]["sources"][0].copy())
    digest = rewrite(path, receipt)
    with pytest.raises(V.ViewRefused):
        view(path, digest, pins + pins)


def test_missing_wrong_and_redirected_source_pin_refuse(tmp_path):
    path, digest, pins, _ = fixture(tmp_path)
    wrong = replace(pins[0], source_key="article:wrong")
    with pytest.raises(V.ViewRefused):
        view(path, digest, [wrong])
    with pytest.raises(V.ViewRefused):
        view(path, digest, [])
    pins[0].absolute_local_path.write_bytes(b"SUBSTITUTED_BODY")
    with pytest.raises(V.ViewRefused):
        view(path, digest, pins)
    pins[0].absolute_local_path.write_bytes(b"LICENSED_BODY_SENTINEL")
    link = tmp_path / "redirect.raw"
    try:
        link.symlink_to(pins[0].absolute_local_path)
    except (OSError, NotImplementedError):
        pass
    else:
        with pytest.raises(V.ViewRefused):
            view(path, digest, [replace(pins[0], absolute_local_path=link)])


def test_duplicate_json_key_and_wrong_receipt_hash_refuse(tmp_path):
    path, digest, pins, _ = fixture(tmp_path)
    with pytest.raises(V.ViewRefused):
        view(path, "0" * 64, pins)
    data = path.read_bytes().replace(b'"status":"PROVISIONAL_REVIEW",',
                                     b'"status":"SENT","status":"PROVISIONAL_REVIEW",')
    assert data != path.read_bytes()
    path.write_bytes(data)
    with pytest.raises(V.ViewRefused):
        view(path, sha(data), pins)


def test_self_rehashed_future_edge_refuses(tmp_path):
    item = source()
    edge = E.IssuerEdge(item.source_key, sha(item.payload), "cik:111111", None,
                        "ISSUER_CANDIDATE", "SEC_CIK", EARLY, WITNESS)
    path, _, pins, receipt = fixture(tmp_path, [item], build([item], [edge]))
    receipt["groups"][0]["edges"][0]["known_at_utc"] = LATE
    digest = rewrite(path, receipt)
    with pytest.raises(V.ViewRefused):
        view(path, digest, pins)


def test_self_rehashed_conflicting_issuer_for_one_source_refuses(tmp_path):
    item = source()
    edge = E.IssuerEdge(item.source_key, sha(item.payload), "cik:111111", None,
                        "ISSUER_CANDIDATE", "SEC_CIK", EARLY, WITNESS)
    path, _, pins, receipt = fixture(tmp_path, [item], build([item], [edge]))
    conflict = receipt["groups"][0]["edges"][0].copy()
    conflict["issuer_id"] = "cik:222222"
    receipt["groups"][0]["edges"].append(conflict)
    digest = rewrite(path, receipt)
    with pytest.raises(V.ViewRefused):
        view(path, digest, pins)


def test_optional_station_is_only_labeled_hypothesis(tmp_path):
    path, digest, pins, _ = fixture(tmp_path)
    map_path = tmp_path / "station.map"
    map_path.write_bytes(b"MAP_BYTES_NOT_SOURCE_BODY")
    station = V.StationPin("macro:japan", map_path, sha(map_path.read_bytes()),
                           "Japan financial stress")
    candidate = view(path, digest, pins, station=station)
    assert candidate["station"]["status"] == "CALLER_LABELED_HYPOTHESIS"
    assert "MAP_BYTES_NOT_SOURCE_BODY" not in json.dumps(candidate)
    with pytest.raises(V.ViewRefused):
        view(path, digest, pins, station=replace(station, map_sha256="0" * 64))


@pytest.mark.parametrize("map_bytes", [300 * 1024, 1_048_576])
def test_pinned_map_through_one_mib_is_accepted_without_body(tmp_path, map_bytes):
    path, digest, pins, _ = fixture(tmp_path)
    map_path = tmp_path / "station.map"
    payload = b"MAP_BODY_SENTINEL" + b"M" * (map_bytes - len(b"MAP_BODY_SENTINEL"))
    map_path.write_bytes(payload)
    station = V.StationPin("macro:japan", map_path, sha(payload), "Japan financial stress")
    candidate = view(path, digest, pins, station=station)
    assert candidate["station"] == {"status": "CALLER_LABELED_HYPOTHESIS",
                                     "station_key": "macro:japan",
                                     "label": "Japan financial stress", "map_sha256": sha(payload)}
    assert "MAP_BODY_SENTINEL" not in json.dumps(candidate)
    assert map_path.read_bytes() == payload


def test_pinned_map_above_one_mib_refuses_before_display(tmp_path):
    path, digest, pins, _ = fixture(tmp_path)
    map_path = tmp_path / "station.map"
    payload = b"M" * (1_048_576 + 1)
    map_path.write_bytes(payload)
    station = V.StationPin("macro:japan", map_path, sha(payload), "Japan financial stress")
    with pytest.raises(V.ViewRefused, match="BYTE_CAP"):
        view(path, digest, pins, station=station)
    assert map_path.read_bytes() == payload


def test_read_only_file_access(tmp_path, monkeypatch):
    path, digest, pins, _ = fixture(tmp_path)
    before = {p.name: sha(p.read_bytes()) for p in tmp_path.iterdir()}
    real_open = os.open

    def guarded_open(filename, flags, *args, **kwargs):
        assert flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC) == 0
        return real_open(filename, flags, *args, **kwargs)

    monkeypatch.setattr(V.os, "open", guarded_open)
    view(path, digest, pins)
    assert before == {p.name: sha(p.read_bytes()) for p in tmp_path.iterdir()}
