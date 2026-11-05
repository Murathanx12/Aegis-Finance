"""Offline E2 component checks; no collector, provider or native warning."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import socket

import pytest

from backend.services import provisional_event_review as P


CUTOFF = "2026-11-03T21:00:00Z"
REVIEW = "2026-11-05T08:00:00Z"
EARLY = "2026-11-02T23:35:59Z"
LATE = "2026-11-04T16:00:00Z"
PROOF = "b" * 64


def source(key="article:a", event="policy:ballot", seen=EARLY, body="LICENSED_BODY_SENTINEL",
           version=None, known=None, kind="ARTICLE"):
    payload = json.dumps({"body": body, "first_seen_utc": seen}).encode()
    sha = hashlib.sha256(payload).hexdigest()
    return P.SourceItem(source_key=key, event_key=event, payload=payload,
                        first_seen_utc=seen, version_seen_utc=version or seen,
                        published_utc=None, kind=kind,
                        provenance=P.SourceProof(sha, known or version or seen, PROOF))


def edge(item, *, symbol="US:NVDA", issuer="cik:1045810", relation="INDIRECT_CANDIDATE",
         basis="CALLER_DESCRIBED_MECHANISM", known=EARLY):
    return P.IssuerEdge(item.source_key, item.provenance.source_sha256, issuer, symbol,
                        relation, basis, known, PROOF)


def holdings(symbols=("US:NVDA",), *, clock=EARLY, known=EARLY, complete=True):
    return P.HoldingsSnapshot(clock, known, symbols, PROOF, complete)


def build(items, edges=(), held=None, **kw):
    args = dict(sources=items, issuer_edges=edges, holdings=held, review_time_utc=REVIEW,
                source_cutoff_utc=CUTOFF, input_complete=True)
    args.update(kw)
    return P.build_review(**args)


def test_pre_election_cutoff_excludes_later_bytes_and_edge_proofs():
    old = source()
    later = source(version=LATE, known=LATE, body="LATER_ELECTION_OUTCOME_SENTINEL")
    r = build([old, later], [edge(old), edge(later, known=LATE)], holdings())
    assert r["decision"] == "REVIEW_EXPOSURE"
    assert r["coverage"]["future_source_versions_excluded"] == 1
    assert r["coverage"]["future_edges_excluded"] == 1
    assert r["groups"][0]["sources"][0]["source_sha256"] == old.provenance.source_sha256
    assert later.provenance.source_sha256 not in json.dumps(r)
    assert set(r["uncertainty"].values()) == {"UNKNOWN"}
    assert r["source_cutoff_utc"] != r["review_time_utc"]


def test_future_conflicting_identity_cannot_poison_historical_join():
    a = source()
    future = source("article:b", seen=LATE)
    r = build([a, future], [edge(a), edge(future, issuer="cik:1326801", known=LATE)], holdings())
    assert r["decision"] == "REVIEW_EXPOSURE"
    assert len(r["groups"][0]["sources"]) == 1


def test_duplicate_versions_are_not_independent_events_or_sources():
    a = source()
    b = source(body="SECOND_VERSION", version="2026-11-03T17:53:12Z")
    r = build([b, a, a], [edge(b, known="2026-11-03T17:53:12Z")], holdings())
    group = r["groups"][0]
    assert len(r["groups"]) == len(group["sources"]) == 1
    assert group["sources"][0]["source_sha256"] == b.provenance.source_sha256
    assert group["sources"][0]["superseded_version_hashes"] == [a.provenance.source_sha256]
    assert r["coverage"]["duplicate_versions"] == 1


def test_old_issuer_edge_does_not_qualify_changed_article_version():
    a = source()
    b = source(body="NEW_SUBJECT", version="2026-11-03T17:53:12Z")
    r = build([a, b], [edge(a)], holdings())
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert r["coverage"]["edges_not_joined"] == 1


def test_stable_ids_and_permutation_determinism():
    a, b = source(), source("article:b")
    first = build([a, b], [edge(a), edge(b)], holdings())
    assert first == build([b, a], [edge(b), edge(a)], holdings())
    later = build([a, b], [edge(a), edge(b)], holdings(), review_time_utc="2026-11-05T09:00:00Z")
    assert first["receipt_id"] != later["receipt_id"]
    assert first["groups"][0]["event_id"] == later["groups"][0]["event_id"]
    assert first["groups"][0]["sources"] == later["groups"][0]["sources"]


def test_false_queue_tag_is_context_and_cannot_trigger_direct_review():
    a = source()
    r = build([a], [edge(a, symbol="US:META", issuer="cik:1326801",
                         relation="DISCOVERY_CONTEXT", basis="QUEUE_CONTEXT")], holdings(("US:META",)))
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert r["groups"][0]["caller_supplied_indirect_symbol_matches"] == []
    assert r["groups"][0]["edges"][0]["relation"] == "DISCOVERY_CONTEXT"
    assert r["groups"][0]["edges"][0]["caller_snapshot_symbol_match"] == "UNKNOWN"
    with pytest.raises(P.ReviewRefused, match="UNQUALIFIED_DIRECT_EDGE"):
        build([a], [edge(a, relation="DIRECT_ISSUER", basis="QUEUE_CONTEXT")], holdings())


def test_full_name_claim_stays_descriptive_without_security_or_held_witness():
    a = source()
    with pytest.raises(P.ReviewRefused, match="UNQUALIFIED_DIRECT_EDGE"):
        build([a], [edge(a, relation="DIRECT_ISSUER",
                         basis="FULL_ISSUER_SUBJECT")], holdings())
    r = build([a], [edge(a, symbol=None, relation="ISSUER_CANDIDATE",
                         basis="FULL_ISSUER_SUBJECT")], holdings())
    g = r["groups"][0]
    assert g["caller_supplied_indirect_symbol_matches"] == []
    assert g["edges"][0]["caller_snapshot_symbol_match"] == "UNKNOWN"
    assert r["reason_codes"] == ["ISSUER_SECURITY_UNRESOLVED"]
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert g["contradiction"] and g["falsifier"]


def test_caller_indirect_match_is_only_a_manual_review_candidate():
    a = source()
    r = build([a], [edge(a)], holdings())
    assert r["decision"] == "REVIEW_EXPOSURE"
    assert r["groups"][0]["caller_supplied_indirect_symbol_matches"] == ["US:NVDA"]
    assert r["groups"][0]["edges"][0]["caller_snapshot_symbol_match"] is True
    assert r["holdings"]["authority"] == "CALLER_SUPPLIED_NOT_VERIFIED"
    assert r["provenance_authority"] == "CALLER_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED"
    assert not r["natural_warning"]


def test_sec_cik_without_security_witness_cannot_name_a_held_symbol():
    a = source(body="SYNTHETIC ISSUER cik:111111 ONLY")
    with pytest.raises(P.ReviewRefused, match="UNQUALIFIED_DIRECT_EDGE"):
        build([a], [edge(a, issuer="cik:222222", symbol="US:NVDA",
                         relation="DIRECT_ISSUER", basis="SEC_CIK")], holdings())
    with pytest.raises(P.ReviewRefused, match="UNQUALIFIED_ISSUER_CANDIDATE"):
        build([a], [edge(a, symbol="US:AAPL", relation="ISSUER_CANDIDATE",
                         basis="SEC_CIK")], holdings(("US:AAPL",)))
    candidate = edge(a, symbol=None, issuer="cik:222222",
                     relation="ISSUER_CANDIDATE", basis="SEC_CIK")
    r = build([a], [candidate], holdings(("US:NVDA", "US:AAPL")))
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert r["reason_codes"] == ["ISSUER_SECURITY_UNRESOLVED"]
    assert r["groups"][0]["caller_supplied_indirect_symbol_matches"] == []
    assert r["groups"][0]["edges"][0]["symbol"] is None
    assert r["groups"][0]["edges"][0]["caller_snapshot_symbol_match"] == "UNKNOWN"
    late = replace(candidate, known_at_utc=LATE)
    excluded = build([a], [late], holdings(("US:NVDA",)))
    assert excluded["coverage"]["future_edges_excluded"] == 1
    assert excluded["groups"][0]["edges"] == []
    with pytest.raises(P.ReviewRefused, match="INVALID_EDGE_QUALIFICATION"):
        build([a], [edge(a, symbol=None, issuer="issuer:" + "a" * 64,
                         relation="ISSUER_CANDIDATE", basis="SEC_CIK")], holdings())


@pytest.mark.parametrize("held,reason", [
    (None, "HOLDINGS_UNKNOWN"),
    (holdings(clock=LATE, known=LATE), "HOLDINGS_AFTER_CUTOFF"),
    (holdings((), complete=False), "PARTIAL_HOLDINGS_UNKNOWN"),
])
def test_missing_or_later_holdings_are_unknown_not_no_exposure(held, reason):
    a = source()
    r = build([a], [edge(a)], held)
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert reason in r["reason_codes"]
    assert r["groups"][0]["edges"][0]["caller_snapshot_symbol_match"] == "UNKNOWN"


def test_empty_complete_snapshot_supports_only_bounded_no_match():
    a = source()
    r = build([a], [edge(a)], holdings(()))
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert "NO_CALLER_INDIRECT_SYMBOL_MATCH" in r["reason_codes"]


def test_partial_cap_does_not_claim_an_unexamined_book_is_clear():
    a, b = source(), source("article:b")
    r = build([b, a], [edge(b)], holdings(), max_sources=1)
    assert r["coverage"]["status"] == "PARTIAL"
    assert r["coverage"]["sources_omitted_by_cap"] == 1
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert "PARTIAL_INPUT_COVERAGE_UNKNOWN" in r["reason_codes"]
    assert r["coverage"]["edges_not_joined"] == 1
    assert build([a], [edge(a)], holdings(), input_complete=False)["decision"] == "REVIEW_EXPOSURE"


def test_reference_page_is_not_an_event_review_even_with_held_match():
    a = source(kind="REFERENCE_PAGE")
    r = build([a], [edge(a)], holdings())
    assert r["decision"] == "NO_CHANGE_WITH_REASON"
    assert "REFERENCE_ONLY" in r["groups"][0]["reason_codes"]


@pytest.mark.parametrize("bad", [None, "", "2026-11-03", "2026-11-03T21:00:00",
                                  "2026-11-03T21:00:00+01:00", "2026-02-30T21:00:00Z"])
def test_invalid_clock_refuses(bad):
    with pytest.raises(P.ReviewRefused, match="INVALID_UTC_CLOCK"):
        build([source()], source_cutoff_utc=bad)


def test_review_before_cutoff_and_inconsistent_source_clocks_refuse():
    with pytest.raises(P.ReviewRefused, match="REVIEW_BEFORE_CUTOFF"):
        build([source()], review_time_utc="2026-11-01T00:00:00Z")
    with pytest.raises(P.ReviewRefused, match="INVALID_SOURCE_TIMELINE"):
        build([source(version="2026-11-01T00:00:00Z")])


def test_missing_source_provenance_and_hash_mismatch_refuse():
    with pytest.raises(P.ReviewRefused, match="MISSING_SOURCE"):
        build([])
    with pytest.raises(P.ReviewRefused, match="MISSING_SOURCE_PROVENANCE"):
        build([replace(source(), provenance=None)])
    with pytest.raises(P.ReviewRefused, match="SOURCE_HASH_MISMATCH"):
        build([replace(source(), payload=b"DIFFERENT_BYTES")])
    with pytest.raises(P.ReviewRefused, match="MISSING_EDGE_SOURCE"):
        build([source()], [edge(source("missing"))])
    with pytest.raises(P.ReviewRefused, match="INVALID_PROVENANCE_HASH"):
        build([source()], [replace(edge(source()), evidence_sha256="")])


def test_identity_and_version_collisions_refuse():
    a = source()
    with pytest.raises(P.ReviewRefused, match="SOURCE_EVENT_COLLISION"):
        build([a, replace(a, event_key="different-event")])
    with pytest.raises(P.ReviewRefused, match="SOURCE_VERSION_CLOCK_COLLISION"):
        build([a, source(body="CONFLICTING_BYTES")])
    with pytest.raises(P.ReviewRefused, match="SYMBOL_ISSUER_COLLISION"):
        build([a], [edge(a), edge(a, issuer="cik:0001326801")], holdings())


@pytest.mark.parametrize("kind", ["source", "event"])
def test_hash_id_collision_is_not_first_writer_wins(monkeypatch, kind):
    original = P._stable_id
    monkeypatch.setattr(P, "_stable_id", lambda namespace, value: "collision" if namespace == kind else original(namespace, value))
    with pytest.raises(P.ReviewRefused, match="ID_COLLISION"):
        build([source(), source("article:b", event="other")])


def test_bounds_and_caller_completeness_refuse():
    with pytest.raises(P.ReviewRefused, match="INPUT_CAP"):
        build([source()] * (P.MAX_INPUT_SOURCES + 1))
    with pytest.raises(P.ReviewRefused, match="SOURCE_BYTE_CAP"):
        build([source(body="x" * P.MAX_SOURCE_BYTES)])
    with pytest.raises(P.ReviewRefused, match="INVALID_COMPLETENESS"):
        build([source()], input_complete=None)


def test_refusal_is_not_parse_failure_and_no_natural_warning_claim():
    r = build([source()], upstream_state="BUDGET_REFUSED", upstream_exit_code=2)
    assert r["upstream_digest"] == {"state": "BUDGET_REFUSED", "exit_code": 2, "parse_status": "UNKNOWN"}
    assert r["status"] == "PROVISIONAL_REVIEW" and r["component_only"]
    assert not r["natural_warning"]
    assert r["authority"] == {"forecast_writes": 0, "portfolio_action": "NONE",
                               "delivery": "NOT_ATTEMPTED", "provider_calls": 0}
    with pytest.raises(P.ReviewRefused, match="INVALID_UPSTREAM_STATUS"):
        build([source()], upstream_state="BUDGET_REFUSED", upstream_exit_code=0)


def test_builder_has_no_io_network_or_input_mutation(monkeypatch):
    a = source();e = edge(a);h = holdings()
    before = repr((a, e, h))
    def forbidden(*args, **kwargs):
        pytest.fail("pure builder attempted I/O or network")
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    import builtins
    monkeypatch.setattr(builtins, "open", forbidden)
    r = build([a], [e], h)
    assert repr((a, e, h)) == before
    assert "LICENSED_BODY_SENTINEL" not in json.dumps(r)
    assert "body" not in r
    assert r["provenance_authority"] == "CALLER_SUPPLIED_NOT_INDEPENDENTLY_VERIFIED"


def test_writer_is_exclusive_dated_append_only_and_only_writes_receipt(tmp_path, monkeypatch):
    r = build([source()])
    sentinel = tmp_path / "ledger.jsonl";sentinel.write_text("UNCHANGED")
    monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: pytest.fail("network"))
    path = P.write_receipt(r, directory=tmp_path)
    assert "20261105T080000" in path.name and path.suffix == ".json"
    assert json.loads(path.read_bytes()) == r
    before = path.read_bytes()
    with pytest.raises(P.ReviewRefused, match="RECEIPT_EXISTS"):
        P.write_receipt(r, directory=tmp_path)
    assert path.read_bytes() == before and sentinel.read_text() == "UNCHANGED"
    assert {p.name for p in tmp_path.iterdir()} == {path.name, sentinel.name}


def test_writer_refuses_tampering_before_open_and_preserves_partial_failure(tmp_path, monkeypatch):
    r = build([source()]);bad = dict(r, decision="TRADE")
    with pytest.raises(P.ReviewRefused, match="RECEIPT_INTEGRITY"):
        P.write_receipt(bad, directory=tmp_path)
    assert list(tmp_path.iterdir()) == []
    monkeypatch.setattr(P.os, "fsync", lambda *a: (_ for _ in ()).throw(OSError("PRIVATE_ERROR")))
    with pytest.raises(P.ReviewRefused, match="RECEIPT_IO_INCOMPLETE"):
        P.write_receipt(r, directory=tmp_path)
    assert len(list(tmp_path.iterdir())) == 1  # no destructive cleanup or green retry


@pytest.mark.parametrize("injection", ["delivery", "forecast", "approval", "pit",
                                        "licensed_body", "paid_typing", "nested_body"])
def test_writer_rejects_self_hashed_false_claims_before_open(tmp_path, injection):
    r = build([source()])
    if injection == "delivery":
        r["delivery"] = "SENT_TO_OWNER"
    elif injection == "forecast":
        r["forecast_generated"] = True
    elif injection == "approval":
        r["owner_decision"] = "APPROVED"
    elif injection == "pit":
        r["listing_identity"] = "PIT_VERIFIED"
    elif injection == "licensed_body":
        r["licensed_body"] = "LICENSED_SENTINEL"
    elif injection == "paid_typing":
        r["upstream_digest"]["state"] = "OK"
        r["upstream_digest"]["exit_code"] = 0
        r["upstream_digest"]["parse_status"] = "TYPED"
    else:
        r["groups"][0]["licensed_body"] = "LICENSED_SENTINEL"
    body = {k: v for k, v in r.items() if k != "receipt_id"}
    r["receipt_id"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    with pytest.raises(P.ReviewRefused, match="RECEIPT_INTEGRITY"):
        P.write_receipt(r, directory=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_writer_accepts_only_original_builder_result_not_rehashed_copy(tmp_path):
    raw = json.loads(json.dumps(build([source()])))
    raw["owner_decision"] = "APPROVED"
    body = {k: v for k, v in raw.items() if k != "receipt_id"}
    raw["receipt_id"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    with pytest.raises(P.ReviewRefused, match="RECEIPT_INTEGRITY"):
        P.write_receipt(raw, directory=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_writer_refuses_non_json_extra_field_with_sanitized_error(tmp_path):
    r = build([source()])
    r["licensed_body"] = b"PRIVATE_BYTES"
    with pytest.raises(P.ReviewRefused, match="RECEIPT_INTEGRITY"):
        P.write_receipt(r, directory=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("injection", ["top_delivery", "nested_typing", "nested_body"])
def test_writer_schema_rejects_even_a_newly_sealed_forged_receipt(tmp_path, injection):
    raw = json.loads(json.dumps(build([source()])))
    if injection == "top_delivery":
        raw["delivery"] = "SENT_TO_OWNER"
    elif injection == "nested_typing":
        raw["upstream_digest"] = {"state": "OK", "exit_code": 0,
                                  "parse_status": "TYPED"}
    else:
        raw["groups"][0]["licensed_body"] = "LICENSED_SENTINEL"
    body = {k: v for k, v in raw.items() if k != "receipt_id"}
    raw["receipt_id"] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    with pytest.raises(P.ReviewRefused, match="RECEIPT_INTEGRITY"):
        P.write_receipt(P._BuiltReceipt(raw), directory=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_writer_refuses_missing_directory_and_invalid_clock(tmp_path):
    r = build([source()])
    with pytest.raises(P.ReviewRefused, match="RECEIPT_DIRECTORY"):
        P.write_receipt(r, directory=tmp_path / "not-created")
    assert not (tmp_path / "not-created").exists()
