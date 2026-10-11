"""Metadata-first parser fixtures only; no original ledger access."""
import hashlib
import json

import exchange_calendars as xcals
import pytest

from backend.services import beta_v1_decision_projection as projection
from backend.services import decision_ledger as DL


@pytest.fixture(autouse=True)
def semantic_fixture_rss(monkeypatch):
    # Semantic parser tests own no data job. Full-suite high-water RSS belongs
    # to unrelated previous tests. Dedicated budget tests inject high/zero RSS;
    # mixed-RSS integration tests probe the real OS in a fresh process.
    from backend.services import beta_v1_replay as limits
    monkeypatch.setattr(limits, "_rss_bytes", lambda: 32*1024*1024)


def row():
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range("2025-01-02", "2025-03-01")
    start, end = calendar.session_close(sessions[0]), calendar.session_close(sessions[21])
    return {"decision_id": "fx-id", "state": "SCORED", "utc": (end+__import__('pandas').Timedelta(hours=1)).isoformat(),
        "asof": "2025-01-02", "by": "decision_grader", "evidence_population": "campaign_forward",
        "formation_utc": "2025-01-02T14:00:00Z", "detail": {"er_horizon": 21,
            "benchmark": "SPY", "label_start_at": start.isoformat(), "label_end_at": end.isoformat(),
            "expiry_utc": end.isoformat(), "target_calendar": "XNYS", "window_contract": "session_close_to_close",
            "task": "expected_excess_return", "score_units": "decimal_price_excess_return",
            "grading_rule": DL.SCORING_RULE, "er_by_component": {"ranker": {"x": .03}}, "excess_return": -.02,
            "model_version": "fixture-v1", "source_versions": {"panel": "fixture-price-v1"},
            "costs_charged": False, "cost_rate_bps": 0}}


def encode(value):
    return (json.dumps(value)+"\n").encode()


def test_protected_malformed_analytical_number_never_calls_full_parser(monkeypatch):
    called = []
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: called.append(line))
    line = b'{"decision_id":"fx","state":"SCORED","evidence_population":"sealed_trial","detail":{"excess_return":NOT_A_NUMBER}}\n'
    projected, _, reason = projection.project_line(line, cutoff="2025-03-01T00:00:00Z")
    assert projected is None and not called
    assert "population" in reason


@pytest.mark.parametrize("hidden", [{"config": {"source": {"arm": "investigator:A_holdout"}}},
    {"metadata": [{"writer": "trial_sealed"}]}, {"source": {"protected": True}},
    {"config": {"evidence_population": "sandbox"}}, {"by": "IIF_reader"}])
def test_recursive_hidden_metadata_protection(hidden):
    item = row()
    item["detail"]["nested"] = hidden
    projected, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert projected is None


def test_duplicate_keys_and_incomplete_lines_refused_before_analytical_parse():
    for line in (b'{"decision_id":"a","decision_id":"b"}',
                 b'{"evidence_population":"campaign_forward","detail":{"x":1,"x":2}}',
                 b'{"decision_id":"a","detail":{"x":12', b'{} trailing'):
        with pytest.raises(projection.ProjectionRefusal):
            projection.MetadataLexer(line).scan()


def test_exact_h21_clocks_qualify_future_score_and_date_only_do_not():
    item = row()
    valid, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert valid["h21_qualification"]["eligible_h21_training"] is True
    future, _, _ = projection.project_line(encode(item), cutoff="2025-01-10T00:00:00Z")
    assert not future["h21_qualification"]["eligible_h21_training"]
    item.pop("formation_utc")
    missing, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert missing["h21_qualification"]["clock_status"] == "UNKNOWN_OR_DATE_ONLY"
    assert not missing["h21_qualification"]["eligible_h21_training"]


def test_full_parse_invalid_admitted_numeric_not_false_zero_or_eligible():
    with pytest.raises(projection.ProjectionRefusal, match="nonfinite"):
        projection.project_line(encode(row()).replace(b'-0.02', b'NaN'), cutoff="2025-03-01T00:00:00Z")
    with pytest.raises(projection.ProjectionRefusal, match="nonfinite"):
        projection.project_line(encode(row()).replace(b'-0.02', b'1e999'), cutoff="2025-03-01T00:00:00Z")


def test_conflicting_same_identity_lifecycle_quarantines_all_and_pins_source(tmp_path):
    first = row()
    other = row()
    other["detail"]["excess_return"] = .2
    protected = row()
    protected["evidence_population"] = "sandbox"
    path = tmp_path/"original.jsonl"
    path.write_bytes(encode(first)+encode(first)+encode(other)+encode(protected))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    result = projection.project_file(path, expected_sha256=sha, cutoff="2025-03-01T00:00:00Z")
    assert not result["rows_private"]
    assert result["counts"]["conflicting_identity_lifecycle_quarantined"] == 3
    assert result["all_population_counts"]["sandbox"] == 1
    assert result["source_sha256_before_after"] == sha


@pytest.mark.parametrize("marker", ["investigator:A", "investigator_B", "investigator-C", "investigatorD_holdout"])
@pytest.mark.parametrize("nested", [False, True])
def test_all_protected_arm_markers_gate_before_opaque_numerics(monkeypatch, marker, nested):
    item = row()
    container = item["detail"].setdefault("arbitrary", {"deeper": {}})["deeper"] if nested else item
    container["arm"] = marker
    calls = []
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: calls.append(line))
    result, _, _ = projection.project_line(encode(item).replace(b'-0.02', b'BROKEN_NUMBER'), cutoff="2025-03-01T00:00:00Z")
    assert result is None and calls == []


@pytest.mark.parametrize("key,value", [("evidence_population", []), ("population", {}),
    ("population", ["campaign_forward"]), ("protected", {}), ("holdout", []),
    ("trial", True), ("experiment", True), ("replay", True), ("sandbox", True),
    ("IIF", True), ("investigator_A", True), ("trial_id", "ordinary-id"),
    ("writer", "investigator:A"), ("by_id", "investigator:B")])
def test_metadata_types_and_protected_identifiers_refuse_without_parse(monkeypatch, key, value):
    item = row()
    item["detail"]["arbitrary"] = {key: value}
    calls = []
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: calls.append(line))
    result, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert result is None and calls == []


@pytest.mark.parametrize("value", [False, None, ""])
def test_explicit_inactive_protection_flags(value):
    item = row()
    item["detail"]["protected"] = value
    result, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert result["h21_qualification"]["eligible_h21_training"]


def stream(tmp_path, lines):
    path = tmp_path/"synthetic.jsonl"
    path.write_bytes(b"".join(lines))
    return projection.project_file(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                   cutoff="2025-03-01T00:00:00Z")


def test_identity_conflict_precedes_numeric_parse_even_malformed_or_excluded_version(monkeypatch, tmp_path):
    calls = []
    original = projection._parse_admitted
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: (calls.append(line), original(line))[1])
    first = encode(row())
    result = stream(tmp_path, [first, first.replace(b'-0.02', b'BROKEN_NUMBER')])
    assert not calls and not result["rows_private"]
    assert result["counts"]["conflicting_identity_lifecycle_quarantined"] == 2
    protected = row()
    protected["arm"] = "investigator:A_holdout"
    result = stream(tmp_path, [first, encode(protected)])
    assert not calls and not result["rows_private"]


def test_duplicate_idempotence_and_distinct_lifecycles(monkeypatch, tmp_path):
    calls = []
    original = projection._parse_admitted
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: (calls.append(line), original(line))[1])
    scored = row()
    open_row = row()
    open_row["state"] = "OPEN"
    result = stream(tmp_path, [encode(scored), encode(scored), encode(open_row)])
    assert len(calls) == 2 and len(result["rows_private"]) == 2
    assert result["counts"]["identical_raw_duplicate_idempotent"] == 1


@pytest.mark.parametrize("key,value", [("benchmark", "UNKNOWN"), ("model_version", "UNRECORDED"),
    ("model_version", []), ("source_versions", {"panel": "UNKNOWN"}),
    ("source_versions", {"panel": {"part": "UNRECORDED"}}),
    ("source_versions", {"panel": ""}), ("source_versions", {}),
    ("source_versions", {"panel": False}), ("costs_charged", True), ("cost_rate_bps", None)])
def test_unrecorded_or_malformed_provenance_never_qualifies(key, value):
    item = row()
    item["detail"][key] = value
    result, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert result is None or not result["h21_qualification"]["eligible_h21_training"]


@pytest.mark.parametrize("key,value", [("horizon_sessions", 5), ("formation_utc", "2025-01-02T15:00:00Z"),
    ("entry_utc", "2025-01-02"), ("exit_utc", "2025-02-05T21:00:00Z"), ("benchmark_symbol", "QQQ"),
    ("score_available_utc", "2025-03-02T00:00:00Z")])
def test_contradictory_or_invalid_declared_aliases_remain_ineligible(key, value):
    item = row()
    item["detail"][key] = value
    result, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert not result["h21_qualification"]["eligible_h21_training"]
    assert any("aliases" in reason or "invalid declared" in reason for reason in result["h21_qualification"]["reasons"])


@pytest.mark.parametrize("detail", ["invalid", [], True, 3, None])
def test_malformed_detail_shape_has_explicit_stream_exclusion(tmp_path, detail):
    item = row()
    item["detail"] = detail
    result = stream(tmp_path, [encode(item)])
    assert not result["rows_private"] and result["eligible_h21_training_rows"] == 0
    assert result["counts"]["excluded:invalid_admitted_detail_shape"] == 1


def test_family_counter_is_recursive_before_numeric_parse(monkeypatch, tmp_path):
    item = row()
    item["detail"]["nested"] = {"writer": "investigator:A", "metadata": {"specialist": "trial-persona"}}
    calls = []
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: calls.append(line))
    result = stream(tmp_path, [encode(item).replace(b'-0.02', b'BROKEN_NUMBER')])
    assert not calls
    assert result["all_metadata_family_counts"]["investigator"] == 1
    assert result["all_metadata_family_counts"]["trial-persona"] == 1


@pytest.mark.parametrize("value", [True, [], {}, 10**500])
def test_invalid_grade_types_are_explicitly_ineligible(value):
    item = row()
    item["detail"]["excess_return"] = value
    result, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    assert not result["h21_qualification"]["eligible_h21_training"]
    assert "finite original excess/component grades unavailable" in result["h21_qualification"]["reasons"]


def test_wrong_grader_and_missing_cost_provenance_cannot_qualify():
    item = row()
    item["by"] = "fixture_unapproved_grader"
    item["detail"].pop("costs_charged")
    result, _, _ = projection.project_line(encode(item), cutoff="2025-03-01T00:00:00Z")
    reasons = result["h21_qualification"]["reasons"]
    assert "approved original grader identity unavailable" in reasons
    assert any("cost provenance" in reason for reason in reasons)


def test_malformed_population_type_is_counted_before_parse(monkeypatch, tmp_path):
    item = row()
    item["detail"]["population"] = []
    calls = []
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: calls.append(line))
    result = stream(tmp_path, [encode(item)])
    assert not calls and result["all_population_counts"]["UNKNOWN_INVALID_TYPE:array"] == 1


def test_source_hash_change_is_refused_before_analytical_phase(monkeypatch, tmp_path):
    path = tmp_path/"synthetic.jsonl"
    path.write_bytes(encode(row()))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    hashes = iter([sha, "changed"])
    calls = []
    monkeypatch.setattr(projection, "_hash", lambda path: next(hashes))
    monkeypatch.setattr(projection, "_parse_admitted", lambda line: calls.append(line))
    with pytest.raises(projection.ProjectionRefusal, match="source changed"):
        projection.project_file(path, expected_sha256=sha, cutoff="2025-03-01T00:00:00Z")
    assert not calls


@pytest.mark.parametrize("payload", [b'{}', b' '*(256*1024)+b'\n'], ids=["no-newline", "oversized-line"])
def test_newline_and_line_bounds_refuse(tmp_path, payload):
    with pytest.raises(projection.ProjectionRefusal, match="line size/newline"):
        stream(tmp_path, [payload])


def test_compact_references_restore_exact_typed_selected_rows(tmp_path):
    first = row()
    unknown = row()
    unknown["decision_id"] = "unknown"
    unknown["detail"]["source_versions"] = {"panel": "UNKNOWN"}
    unknown["detail"]["er_by_component"] = {"ranker": {"x": .03, "count": 2, "flag": False, "absent": None}}
    lines = [encode(first), encode(unknown)]
    expected = {json.loads(line)["decision_id"]: projection.project_line(line, cutoff="2025-03-01T00:00:00Z")[0]
                for line in lines}
    result = stream(tmp_path, lines)
    for compact in result["rows_private"]:
        assert projection.expand_projected_row(result, compact) == expected[compact["decision_id"]]
        tags = projection.MetadataLexer(lines[0] if compact["decision_id"] == "fx-id" else lines[1]).scan()
        assert compact["admission_metadata_sha256"] == hashlib.sha256(projection.canonical_bytes(tags)).hexdigest()
    assert result["eligible_h21_training_rows"] == 1
    assert result["all_population_counts"] == {"campaign_forward": 2}
    assert result["all_metadata_family_counts"] == {"decision_grader": 2}
    assert result["original_metadata_lookup"]["source_sha256"] == result["source_sha256_before_after"]
    compact = result["rows_private"][0]
    result["reference_tables"]["qualification"][compact["qualification_ref"]]["clock_status"] = "TAMPERED"
    with pytest.raises(projection.ProjectionRefusal, match="reference integrity"):
        projection.expand_projected_row(result, compact)


def test_bloated_repeated_metadata_with_all_rows_preserved_under_output_cap(tmp_path):
    """Near-bound synthetic source reproduces >4MiB expanded-output inflation."""
    count = 2600
    lines = []
    for i in range(count):
        item = {"decision_id": f"bloated-{i}", "state": "SCORED", "utc": "2025-02-04T22:00:00Z",
            "asof": "2025-01-02", "by": "decision_grader", "evidence_population": "campaign_forward",
            "detail": {"excess_return": -.02, "er_by_component": {"ranker": {"x": i/100000, "flag": False}},
                "model_version": "fixture-v1", "source_versions": {"panel": "fixture-source-v1"},
                "metadata": {"note": "original recorded fixture metadata "*6}}}
        lines.append(encode(item))
    assert sum(map(len, lines)) < 2*1024*1024
    result = stream(tmp_path, lines)
    assert len(result["rows_private"]) == count
    assert result["counts"]["all_rows"] == count
    assert result["counts"]["explicit_original_campaign_metadata_admitted"] == count
    assert result["eligible_h21_training_rows"] == 0
    assert result["all_population_counts"] == {"campaign_forward": count}
    assert result["all_metadata_family_counts"] == {"decision_grader": count}
    baseline_bytes = 0
    for compact in result["rows_private"]:
        original_line = lines[int(compact["decision_id"].split("-")[1])]
        expected = projection.project_line(original_line, cutoff="2025-03-01T00:00:00Z")[0]
        expanded = projection.expand_projected_row(result, compact)
        assert expanded == expected
        assert compact["full_row_sha256"] == hashlib.sha256(original_line).hexdigest()
        baseline_bytes += len(projection.canonical_bytes(expanded))
    assert baseline_bytes > 4*1024*1024
    assert len(projection.canonical_bytes(result)) < 4*1024*1024
    assert len(result["reference_tables"]["qualification"]) == 1


def test_private_cli_serializes_compact_envelope_and_refuses_oversize_before_write(tmp_path, monkeypatch):
    import sys
    from scripts import beta_v1_decision_projection as command
    source = tmp_path/"synthetic.jsonl"
    source.write_bytes(encode(row()))
    output = tmp_path/"private"/"beta_v1_original_decision_projection.json"
    argv = ["projection", "--source", str(source), "--source-sha256", hashlib.sha256(source.read_bytes()).hexdigest(),
        "--cutoff", "2025-03-01T00:00:00Z", "--output", str(output)]
    monkeypatch.setattr(sys, "argv", argv)
    command.main()
    encoded = output.read_bytes()
    assert len(encoded) < 4*1024*1024
    payload = json.loads(encoded)
    result = payload["projection"]
    expected = projection.project_line(encode(row()), cutoff="2025-03-01T00:00:00Z")[0]
    assert projection.expand_projected_row(result, result["rows_private"][0]) == expected
    assert payload["activation"] is False
    blocked = tmp_path/"never-created"/"beta_v1_original_decision_projection.json"
    argv[-1] = str(blocked)
    monkeypatch.setattr(command.projection, "project_file", lambda *args, **kwargs: {"padding": "x"*(4*1024*1024)})
    with pytest.raises(projection.ProjectionRefusal, match="complete private serialized envelope"):
        command.main()
    assert not blocked.parent.exists()
