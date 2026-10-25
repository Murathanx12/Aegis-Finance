"""Pinned public calendar policy, tiny frames and clocks; no native books/writer."""
import copy
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from scripts import original247_listing_policy as P
from scripts import local_branching_grade_child as child
from backend.tests.test_beta_v2_original_grade_freshness import (
    Calendar, S, frame, saved_receipt, consumer as consumer,
)


NOW = datetime(2026, 10, 25, 7, tzinfo=timezone.utc)


def load(**kwargs):
    return P.load_policy(session=kwargs.pop("session", S), observed_at=kwargs.pop("observed_at", NOW),
                         calendar_loader=kwargs.pop("calendar_loader", lambda _: object()), **kwargs)


def rewritten(tmp_path, mutate=None, raw=None):
    if raw is None:
        policy = json.loads(P.POLICY_PATH.read_text(encoding="utf-8"))
        if mutate:
            mutate(policy)
        raw = P.canonical_bytes(policy)
    path = tmp_path / "policy.json"
    path.write_bytes(raw)
    return path, P.sha256(raw)


def test_exact_full_set_and_source_provenance_are_bound():
    result = load()
    assert len(result["mapping"]) == 76
    assert P.sha256(P.canonical_bytes(sorted(result["mapping"]))) == P.IDENTITIES_SHA256
    assert P.sha256(P.POLICY_PATH.read_bytes()) == P.MANIFEST_SHA256
    assert result["receipt"]["scope"] == "FROZEN_INSTRUMENT_CALENDAR_ONLY"
    assert len(result["receipt"]["source_receipts"]) == 4
    assert result["instruments"]["SPY"]["actual_exchange_mic"] == "ARCX"
    assert result["mapping"]["SPY"] == "XNYS"
    assert result["instruments"]["ASML"]["actual_exchange_mic"] == "XNAS"
    assert result["instruments"]["ASML"]["official_symbol"] == "ASML"
    assert result["instruments"]["2330.TW"]["official_symbol"] == "2330"
    assert result["instruments"]["TSM"]["official_symbol"] == "TSM"
    assert result["instruments"]["005930.KS"]["official_symbol"] == "005930"
    assert result["instruments"]["000660.KS"]["official_symbol"] == "KS 000660"
    assert result["sources"]["samsung_common"]["embedded_date"] is None
    assert "year unstated" in result["sources"]["jpx_historical_table"]["embedded_date"]
    assert "class" in " ".join(result["instruments"]["267260.KS"]["uncertainty"])
    for source in result["sources"].values():
        assert P.sha256(source["excerpt"].encode("utf-8")) == source["excerpt_sha256"]
    assert result["sources"]["inherited_five"]["url"] is None
    assert len(result["sources"]["inherited_five"]["receipt_sha256"]) == 64


def test_older_and_undated_identity_bodies_support_only_finite_calendar_policy():
    policy = load()
    assert all(policy["mapping"][s] == "XTKS" for s in ("6146.T", "6920.T", "8035.T"))
    assert policy["mapping"]["2308.TW"] == "XTAI"
    assert policy["mapping"]["005930.KS"] == "XKRX"
    assert policy["instruments"]["005930.KS"]["embedded_date"] is None
    assert "not continuous or current" in policy["instruments"]["6146.T"]["uncertainty"][0]


@pytest.mark.parametrize("session,observed", [
    (date(2026, 10, 14), NOW), (date(2027, 4, 20), datetime(2027, 4, 20, tzinfo=timezone.utc)),
    (S, datetime(2026, 10, 24, 23, 59, tzinfo=timezone.utc)),
    (S, datetime(2027, 4, 21, tzinfo=timezone.utc)),
    (date(2026, 10, 26), NOW),
])
def test_scope_and_expiry_refuse_without_substituting_today(session, observed):
    with pytest.raises(P.PolicyError, match="POLICY_OUTSIDE_VALIDITY"):
        load(session=session, observed_at=observed)


def test_policy_clock_must_be_aware():
    with pytest.raises(P.PolicyError, match="POLICY_CLOCK_REQUIRED"):
        load(observed_at=NOW.replace(tzinfo=None))


def test_inclusive_final_horizon_and_observation_day():
    assert load(session=date(2027, 4, 19), observed_at=datetime(2027, 4, 20, 23, 59, tzinfo=timezone.utc))


@pytest.mark.parametrize("mutation", ["byte", "alias", "class", "calendar"])
def test_fixed_pin_refuses_changed_policy_bytes(tmp_path, mutation):
    def change(p):
        row = p["instruments"]["005930.KS"]
        if mutation == "alias":
            row["official_symbol"] = "005935"
        elif mutation == "class":
            row["security_class"] = "preferred shares"
        elif mutation == "calendar":
            row["calendar_key"] = "XNYS"
        else:
            p["policy_id"] += "x"
    path, _ = rewritten(tmp_path, change)
    with pytest.raises(P.PolicyError, match="POLICY_PIN_MISMATCH"):
        load(path=path)


@pytest.mark.parametrize("mutation,reason", [
    ("missing", "FROZEN_IDENTITY_BINDING"), ("extra", "FROZEN_IDENTITY_BINDING"),
    ("alias_key", "FROZEN_IDENTITY_BINDING"), ("book_pin", "FROZEN_COHORT_BINDING"),
    ("witness_hash", "INVALID_WITNESS_RECEIPT"), ("witness_missing", "INSTRUMENT_WITNESSES"),
    ("body_match", "BODY_MATCH_REQUIRED"), ("crosswalk", "INSTRUMENT_IDENTITY"),
    ("expiry", "INVALID_POLICY_VALIDITY"), ("scope", "POLICY_SCOPE"),
    ("current_claim", "POLICY_CLAIMS"), ("private_ids", "COHORT_SCHEMA"),
    ("url", "WITNESS_URL_REQUIRED"), ("bad_calendar", "CALENDAR_KEY_REQUIRED"),
    ("numeric_false", "POLICY_CLAIMS"), ("retrieval_missing", "INVALID_RETRIEVAL_INTERVAL"),
    ("duplicate_receipt", "SOURCE_RECEIPT_SET"),
])
def test_structure_cannot_be_bypassed_by_repinning_fixture(tmp_path, mutation, reason):
    def change(p):
        row = p["instruments"]["ASML"]
        if mutation == "missing":
            del p["instruments"]["ASML"]
        elif mutation == "extra":
            p["instruments"]["EXTRA"] = copy.deepcopy(row)
        elif mutation == "alias_key":
            p["instruments"]["ASML.AS"] = p["instruments"].pop("ASML")
        elif mutation == "book_pin":
            p["cohort"]["book_ids_sha256"] = "0" * 64
        elif mutation == "witness_hash":
            p["sources"]["nasdaqlisted"]["excerpt"] += "altered"
        elif mutation == "witness_missing":
            del p["sources"]["nasdaqlisted"]
        elif mutation == "body_match":
            row["matches"][0]["text"] = "not in witness body"
        elif mutation == "crosswalk":
            row["crosswalk"] = ""
        elif mutation == "expiry":
            p["validity"]["observation_date_through"] = "2099-01-01"
        elif mutation == "scope":
            p["scope"] = "CERTIFY_CURRENT_LISTINGS"
        elif mutation == "current_claim":
            p["claims"]["current_listing_status"] = True
        elif mutation == "private_ids":
            p["cohort"]["native_book_ids"] = ["must never be here"]
        elif mutation == "url":
            p["sources"]["nasdaqlisted"]["url"] = None
        elif mutation == "numeric_false":
            p["claims"]["current_listing_status"] = 0
        elif mutation == "retrieval_missing":
            p["sources"]["nasdaqlisted"]["retrieval_interval"] = []
        elif mutation == "duplicate_receipt":
            p["source_receipts"][0] = p["source_receipts"][1]
        else:
            row["calendar_key"] = "XUNKNOWN"
    path, pin = rewritten(tmp_path, change)
    with pytest.raises(P.PolicyError, match=reason):
        load(path=path, expected_sha256=pin)


@pytest.mark.parametrize("raw,reason", [
    (b'{"a":1,"a":2}', "DUPLICATE_JSON_KEY"), (b'{"a":NaN}', "NONFINITE_JSON_VALUE"),
    (b'{}\n', "NONCANONICAL_POLICY_JSON"), (b'\xff', "INVALID_POLICY_JSON"),
])
def test_strict_canonical_json(tmp_path, raw, reason):
    path, pin = rewritten(tmp_path, raw=raw)
    with pytest.raises(P.PolicyError, match=reason):
        load(path=path, expected_sha256=pin)


@pytest.mark.parametrize("opening,closing", [(b"[", b"]"), (b'{"x":', b"}")])
def test_deep_json_below_byte_ceiling_is_explicit_policy_refusal(tmp_path, opening, closing):
    raw = opening * 20_000 + b"0" + closing * 20_000
    assert len(raw) < 256 * 1024
    path, pin = rewritten(tmp_path, raw=raw)
    with pytest.raises(P.PolicyError, match="POLICY_JSON_NESTING_LIMIT") as caught:
        load(path=path, expected_sha256=pin)
    assert isinstance(caught.value.__cause__, RecursionError)


def test_normalization_depth_exhaustion_uses_same_parser_boundary(tmp_path, monkeypatch):
    path, pin = rewritten(tmp_path, raw=b"{}")
    def exhausted(_value):
        raise RecursionError("fixture canonical encoder depth exhaustion")
    monkeypatch.setattr(P, "canonical_bytes", exhausted)
    with pytest.raises(P.PolicyError, match="POLICY_JSON_NESTING_LIMIT") as caught:
        load(path=path, expected_sha256=pin)
    assert isinstance(caught.value.__cause__, RecursionError)


def test_recursion_outside_parser_boundary_is_not_hidden(monkeypatch):
    def implementation_defect(_value):
        raise RecursionError("fixture unrelated validation defect")
    monkeypatch.setattr(P, "_retrieved", implementation_defect)
    with pytest.raises(RecursionError, match="unrelated validation defect"):
        load()


def test_missing_policy_is_explicit(tmp_path):
    with pytest.raises(P.PolicyError, match="POLICY_FILE_UNAVAILABLE"):
        load(path=tmp_path / "absent")


def test_all_installed_calendar_keys_are_checked_and_unavailable_refuses():
    calls = []
    load(calendar_loader=lambda key: calls.append(key) or object())
    assert set(calls) == {"XNYS", "XSTO", "XETR", "XOSL", "XTAI", "XKRX", "XTKS", "XASX"}
    def missing(key):
        if key == "XTKS":
            raise ValueError("fixture missing calendar")
        return object()
    with pytest.raises(P.PolicyError, match="CALENDAR_UNAVAILABLE"):
        load(calendar_loader=missing)


def test_full_identity_binding_is_exact():
    names = set(load()["mapping"])
    assert load(exact_symbols=names)
    with pytest.raises(P.PolicyError, match="FROZEN_IDENTITY_SET_MISMATCH"):
        load(exact_symbols=names - {"SPY"})


def calendar(key):
    return Calendar(20 if key == "XNYS" else 15)


def test_completed_default_covers_76_with_manifest_provenance():
    policy = load()
    names = set(policy["mapping"])
    proof = child.completed_session_targets(names, S, NOW, calendar_loader=calendar)
    assert set(proof["required_sessions"]) == names
    assert set(proof["required_sessions"].values()) == {S.isoformat()}
    assert proof["listing_policy_receipt"]["manifest_sha256"] == P.MANIFEST_SHA256
    assert proof["listing_policy_receipt"]["n_allowed"] == 76


@pytest.mark.parametrize("holiday,late,status", [(True, False, "LOCAL_NON_SESSION"), (False, True, "SESSION_UNCLOSED")])
def test_policy_never_overrides_local_completion(holiday, late, status):
    def load_cal(key):
        c = calendar(key)
        if key == "XTKS":
            c.holiday = holiday
            if late:
                c.close += timedelta(days=3)
        return c
    proof = child.completed_session_targets({"6146.T", "SPY"}, S, NOW, calendar_loader=load_cal)
    assert proof["symbols"]["6146.T"]["status"] == status
    assert proof["required_sessions"]["6146.T"] is None
    assert proof["required_sessions"]["SPY"] == S.isoformat()


def test_expired_default_never_falls_back_to_legacy_six():
    proof = child.completed_session_targets({"SPY", "EVO.ST"}, S,
            datetime(2027, 4, 21, tzinfo=timezone.utc), calendar_loader=calendar)
    assert set(proof["required_sessions"].values()) == {None}
    assert proof["listing_policy_receipt"] == {"status": "INVALID", "reason": "POLICY_OUTSIDE_VALIDITY"}


def test_frozen_default_run_reaches_only_mock_writer_with_same_bounded_snapshot(consumer):
    policy = load()
    names = set(policy["mapping"])
    # Synthetic IDs and tmp cache only, preserving the existing fixture's 247-ID proof.
    consumer.books[0]["positions"] = [{"ticker": s, "weight": 0} for s in sorted(names)]
    us = {s for s, mic in policy["mapping"].items() if mic == "XNYS"}
    consumer.save(us=frame(us), glob=frame(names - us))
    consumer.allow_writer()
    result = consumer.run(now=NOW, calendar_loader=calendar, listing_calendars=None)
    assert result["action"] == "GRADED"
    assert result["grade_evidence"]["completed_session_targets"]["listing_policy_receipt"]["n_identities"] == 76
    assert result["grade_evidence"]["freshness_diagnostic"]["n_fresh"] == 76
    assert set(consumer.writer.call_args.kwargs["bars_override"].symbol) == names
    # Existing native child's output ceiling is unchanged; evidence must fit it.
    assert len(json.dumps(result).encode()) < 64 * 1024
    consumer.writer.assert_called_once()


def test_r1_manifest_provenance_cannot_be_replaced():
    reference = child.completed_session_targets({"SPY"}, S, NOW, calendar_loader=calendar)
    fake = copy.deepcopy(reference)
    fake["listing_policy_receipt"]["manifest_sha256"] = "0" * 64
    targets, errors = child.validate_completion_proofs(fake, reference, {"SPY"}, S, NOW)
    assert targets == {"SPY": None}
    assert errors["SPY"].endswith("listing_policy_receipt")


def test_existing_receipt_precedes_policy_loading_and_stays_unchanged(consumer, monkeypatch, tmp_path):
    path = consumer.daydir / "grade_fixture.json"
    path.write_text(json.dumps(saved_receipt(consumer)), encoding="utf-8")
    raw = path.read_bytes()
    monkeypatch.setattr(P, "POLICY_PATH", tmp_path / "missing_policy.json")
    result = consumer.run(now=NOW, calendar_loader=calendar, listing_calendars=None)
    assert result["action"] == "ALREADY_GRADED"
    assert path.read_bytes() == raw
    consumer.writer.assert_not_called()


def test_bad_manifest_default_refuses_even_when_all_price_marks_are_ready(consumer, monkeypatch, tmp_path):
    names = set(load()["mapping"])
    consumer.books[0]["positions"] = [{"ticker": s, "weight": 0} for s in sorted(names)]
    consumer.save(us=frame({"SPY"}), glob=frame(names - {"SPY"}))
    monkeypatch.setattr(P, "POLICY_PATH", tmp_path / "missing_policy.json")
    consumer.allow_writer()
    result = consumer.run(now=NOW, calendar_loader=calendar, listing_calendars=None)
    assert result["action"] == "WAIT_CONSTITUENT_MARKS"
    assert result["reason"] == "POLICY_FILE_UNAVAILABLE"
    consumer.writer.assert_not_called()
