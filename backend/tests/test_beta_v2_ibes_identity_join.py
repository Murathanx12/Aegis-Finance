"""Synthetic-only C05 tests. Run with --noconftest and a private --basetemp.

No actual partition, historical link source, acquisition worker, model or native
store is imported/opened. Every fixture is created below pytest's basetemp.
"""
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts import beta_v2_ibes_identity_join as m


KEY = "SYNTH_PRIVATE_IDENTITY_DO_NOT_EXPORT"
OTHER = "SYNTH_SECOND_IDENTITY_DO_NOT_EXPORT"
PERMNO = 987654321


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def ref(path):
    return {"path": str(path), "sha256": m.sha(path.read_bytes())}


def link(key=KEY, permno=PERMNO, start="2025-01-01", end="2025-01-31", score=0):
    return dict(ticker=key, permno=permno, ncusip="SYNTH_CUSIP_DO_NOT_EXPORT",
                sdate=start, edate=end, score=score)


def row(key=KEY, day="2025-01-16", extra=None):
    return [["str", key] if key is not None else ["null"],
            ["date", day] if day is not None else ["null"],
            extra if extra is not None else ["EXCLUDED_OUTCOME_SENTINEL", {"never_decode": 123}]]


class Fixture:
    def __init__(self, root, rows=None, links=None):
        self.root = root
        self.packet = root / "packet"
        self.planpath = self.packet / "plans/job01.json"
        self.path = self.packet / "artifacts/partition01.typed.jsonl"
        self.linkpath = root / "links.parquet"
        self.rows = rows if rows is not None else [row()]
        self.job = {"schema": "C05_exact_raw_IBES_month/1", "table": "ibes.statsum_epsus",
                    "date_column": "statpers", "from_inclusive": "2025-01-01", "until_exclusive": "2025-02-01",
                    "all_source_identifiers": True, "preserve_all_rows_and_fields": True,
                    "expected_columns": ["ticker", "statpers", "actual"],
                    "expected_source_type_oids": {"ticker": 1043, "statpers": 1082, "actual": 701},
                    "output_root": str(self.path.parent),
                    "typed_schema_witness_path": str(root / "witness.json")}
        write_json(root / "witness.json", {"columns": self.job["expected_columns"],
                                          "source_type_oids": self.job["expected_source_type_oids"]})
        self.job["typed_schema_witness_sha256"] = ref(root / "witness.json")["sha256"]
        write_json(self.planpath, self.job)
        (self.packet / "raw_ibes_worker.py").write_text("# synthetic provenance only", encoding="utf-8")
        actualpath = root / "actual_schema.json"
        write_json(actualpath, {"tables": {self.job["table"]: [
            {"column_name": c, "udt_name": "date" if c == "statpers" else "varchar"}
            for c in self.job["expected_columns"]]}})
        self.rootplan = {"schema": "C05_exact_four_raw_IBES_plan/1",
                         "jobs": [ref(self.planpath), {}, {}, {}],
                         "actual_schema_path": str(actualpath),
                         "actual_schema_sha256": ref(actualpath)["sha256"]}
        write_json(self.packet / "PLAN.json", self.rootplan)
        self.header = {"schema": "C05_exact_typed_rows_jsonl/1", "columns": self.job["expected_columns"],
                       "source_type_oids": self.job["expected_source_type_oids"],
                       "job_plan_sha256": ref(self.planpath)["sha256"],
                       "query_template_sha256": m.query_hash(self.job), "rows_expected": len(self.rows),
                       "all_source_fields_rows_and_duplicate_versions_preserved": True}
        self.write_partition()
        self.set_links(links if links is not None else [link()])
        self.sync_evidence()

    def write_partition(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"\n".join(json.dumps(x).encode() for x in [self.header, *self.rows]) + b"\n")

    def set_links(self, links):
        schema = pa.schema([("ticker", pa.string()), ("permno", pa.int64()), ("ncusip", pa.string()),
                            ("sdate", pa.string()), ("edate", pa.string()), ("score", pa.float64())])
        pq.write_table(pa.Table.from_pylist(links, schema=schema), self.linkpath, compression="gzip")
        self.linkrows = len(links)

    def sync_evidence(self):
        artifact = {**ref(self.path), "bytes": self.path.stat().st_size, "rows": len(self.rows),
                    "source_date_predicate_validated": True, "typed_roundtrip_equal": True,
                    "all_columns_and_original_order_retained": True}
        self.record = {"table": self.job["table"], "status": "COMPLETE", "artifact": artifact,
                       "job_plan_sha256": ref(self.planpath)["sha256"],
                       "query_template_sha256": m.query_hash(self.job)}
        self.run = {"schema": "C05_raw_IBES_jan2025_receipt/1", "status": "COMPLETED_RAW_FOUR_TABLE_PARTITIONS",
                    "plan_sha256": ref(self.packet / "PLAN.json")["sha256"],
                    "worker_sha256": ref(self.packet / "raw_ibes_worker.py")["sha256"],
                    "connection_closed": True, "cleanup_gates": [], "jobs": [self.record, {}, {}, {}]}
        self.back = {"table": self.job["table"], "status": "COMPLETE", "predicate_column": "statpers",
                     "column_count": 3, **{k: artifact[k] for k in ("bytes", "rows", "sha256")},
                     "actual_column_order_OIDs_and_date_predicate_match": True,
                     "all_cell_type_roundtrips_equal": True, "all_source_rows_fields_and_clock_values_retained": True}
        self.flush_receipts()

    def flush_receipts(self):
        write_json(self.packet / "RUN_RECEIPT.json", self.run)
        write_json(self.packet / "READBACK_JOB01.json", self.back)
        write_json(self.packet / "ACTUAL_RESULT_PINS.json", {
            "status": "FROZEN_ACTUAL_FOUR_COMPLETE_NO_FURTHER_QUERIES", "frozen_sourcepins_still_equal": True,
            "files": {n: ref(self.packet / n)["sha256"] for n in ("RUN_RECEIPT.json", "READBACK_JOB01.json")}})
        self.binding = {"schema": "C05_identity_binding/1", "sources": {
            "job": ref(self.planpath), "root_plan": ref(self.packet / "PLAN.json"),
            "run": ref(self.packet / "RUN_RECEIPT.json"), "readback": ref(self.packet / "READBACK_JOB01.json"),
            "raw_pins": ref(self.packet / "ACTUAL_RESULT_PINS.json"),
            "codec": ref(self.packet / "raw_ibes_worker.py"), "actual_schema": ref(self.root / "actual_schema.json"),
            "typed_schema": ref(self.root / "witness.json")},
            "partition": {k: self.record["artifact"][k] for k in ("path", "sha256", "bytes", "rows")},
            "link": {**ref(self.linkpath), "bytes": self.linkpath.stat().st_size,
                     "rows": self.linkrows, "columns": m.LINK_COLUMNS}}

    def run_join(self, limits=m.Limits()):
        return m.run_diagnostic(self.binding, limits)


def test_duplicate_denominator_nulls_and_no_excluded_values(tmp_path):
    fixture = Fixture(tmp_path, rows=[row(), row(), row(None), row(day=None), row(OTHER)])
    result = fixture.run_join()
    assert result["rows"] == 5
    assert result["categories"] == dict(no_link=1, one_unique_permno=2, multiple_permnos=0,
                                         overlap_one_permno=0, unqualified_link=0,
                                         missing_key_or_date=2, malformed_key_or_date=0)
    assert result["projected_cell_states"]["ticker"]["missing"] == 1
    assert result["projected_cell_states"]["statpers"]["missing"] == 1
    assert result["link_sha256_before"] == result["link_sha256_after"]
    assert sum(result["categories"].values()) == 5
    assert result["decoded_columns"] == ["ticker", "statpers"]
    rendered = json.dumps(result)
    for private in (KEY, OTHER, str(PERMNO), "SYNTH_CUSIP_DO_NOT_EXPORT", "EXCLUDED_OUTCOME_SENTINEL", str(tmp_path)):
        assert private not in rendered


@pytest.mark.parametrize("start,end,expected", [
    ("2025-01-17", "2025-01-31", "no_link"),
    ("2024-12-01", "2025-01-15", "no_link"),
    ("2025-01-16", "2025-01-16", "one_unique_permno"),
    ("2026-01-01", "2026-01-31", "no_link"),
])
def test_dated_future_expired_and_inclusive_boundaries(tmp_path, start, end, expected):
    result = Fixture(tmp_path, links=[link(start=start, end=end)]).run_join()
    assert result["categories"][expected] == 1


def test_multiple_link_rows_one_permno_is_not_multiple_permnos_or_unique(tmp_path):
    result = Fixture(tmp_path, rows=[row(), row()], links=[link(), link()]).run_join()
    assert result["categories"]["overlap_one_permno"] == 2
    assert result["categories"]["one_unique_permno"] == 0
    assert result["observations_multiple_link_rows_one_permno"] == 2
    assert result["observations_multiple_permnos"] == 0
    assert result["active_link_row_matches"] == 4


def test_conflicting_permnos_never_pick_best_score(tmp_path):
    result = Fixture(tmp_path, links=[link(score=0), link(permno=PERMNO + 1, score=6)]).run_join()
    assert result["categories"]["multiple_permnos"] == 1
    assert result["categories"]["one_unique_permno"] == 0
    assert result["active_link_score_buckets_row_weighted"] == {"0": 1, "6": 1}


def test_disjoint_historical_rows_do_not_invent_ambiguity(tmp_path):
    result = Fixture(tmp_path, links=[link(end="2025-01-15"), link(start="2025-01-16")]).run_join()
    assert result["categories"]["one_unique_permno"] == 1


@pytest.mark.parametrize("patch", [dict(start=None), dict(end=None), dict(start="2025-02-01"),
                                    dict(start="not-a-date"), dict(permno=None), dict(score=None), dict(score=float("nan"))])
def test_unqualified_links_block_unique_claim(tmp_path, patch):
    result = Fixture(tmp_path, links=[link(), link(**patch)]).run_join()
    assert result["categories"]["unqualified_link"] == 1
    assert result["link_source"]["unqualified_rows"] == 1


def test_unknown_link_key_refuses_all_unique_claims(tmp_path):
    result = Fixture(tmp_path, links=[link(), link(key=None)]).run_join()
    assert result["categories"]["unqualified_link"] == 1


@pytest.mark.parametrize("cell,index", [(["null", "extra"], 0), (["str", 4], 0), (["str", KEY, 0], 0),
                                       (["int", "123"], 0), (["date", "20250116"], 1),
                                       (["date", "2025-02-30"], 1), (["str", "2025-01-16"], 1),
                                       (["datetime", "2025-01-16T00:00:00", 0], 1), (["date", None], 1)])
def test_malformed_projected_typed_cells_preserve_denominator(tmp_path, cell, index):
    source_row = row()
    source_row[index] = cell
    result = Fixture(tmp_path, rows=[source_row, row()]).run_join()
    assert result["rows"] == 2
    assert result["categories"]["malformed_key_or_date"] == 1
    assert result["categories"]["one_unique_permno"] == 1


@pytest.mark.parametrize("bad_key", ["\ud800", "\udfff", "A\ud800B"])
def test_escaped_surrogate_ticker_counts_malformed_with_duplicate_denominator(tmp_path, bad_key):
    fixture = Fixture(tmp_path, rows=[row(bad_key), row(), row()])
    assert json.dumps(["str", bad_key]).encode() in fixture.path.read_bytes()
    result = fixture.run_join()
    assert result["rows"] == 3
    assert result["categories"]["malformed_key_or_date"] == 1
    assert result["categories"]["one_unique_permno"] == 2
    assert result["projected_cell_states"]["ticker"] == {"malformed": 1, "missing": 0, "valid": 2}
    assert result["active_link_row_matches"] == 2
    assert sum(result["categories"].values()) == 3


@pytest.mark.parametrize("ensure_ascii", [True, False])
def test_valid_non_ascii_ticker_keeps_exact_utf8_key_and_byte_limit(tmp_path, ensure_ascii):
    key = "\u00c5BC"
    fixture = Fixture(tmp_path, rows=[row(key), row(key)], links=[link(key=key)])
    fixture.path.write_bytes(b"\n".join(json.dumps(x, ensure_ascii=ensure_ascii).encode("utf-8")
                                       for x in [fixture.header, *fixture.rows]) + b"\n")
    fixture.sync_evidence()
    result = fixture.run_join()
    assert result["rows"] == 2
    assert result["categories"]["one_unique_permno"] == 2
    assert result["projected_cell_states"]["ticker"]["valid"] == 2
    assert m.key_ok("\u00e9" * 64, m.Limits())
    assert not m.key_ok("\u00e9" * 64 + "A", m.Limits())


def test_raw_observation_date_range_is_checked(tmp_path):
    with pytest.raises(m.Refusal, match="OBSERVATION_DATE_OUTSIDE_DECLARED_RANGE"):
        Fixture(tmp_path, rows=[row(day="2025-02-01")]).run_join()


@pytest.mark.parametrize("field,value", [("source_type_oids", {"ticker": 1043, "statpers": 1114, "actual": 701}),
                                         ("source_type_oids", {"ticker": 1043.0, "statpers": 1082, "actual": 701}),
                                         ("columns", ["statpers", "ticker", "actual"]),
                                         ("job_plan_sha256", "a" * 64), ("rows_expected", 2),
                                         ("rows_expected", True),
                                         ("all_source_fields_rows_and_duplicate_versions_preserved", 1),
                                         ("all_source_fields_rows_and_duplicate_versions_preserved", False)])
def test_header_schema_and_source_drift_refuse(tmp_path, field, value):
    fixture = Fixture(tmp_path)
    fixture.header[field] = value
    fixture.write_partition()
    fixture.sync_evidence()
    with pytest.raises(m.Refusal, match="TYPED_HEADER_DRIFT"):
        fixture.run_join()


@pytest.mark.parametrize("role", sorted(m.ROLES))
def test_missing_evidence_is_not_zero_coverage(tmp_path, role):
    fixture = Fixture(tmp_path)
    del fixture.binding["sources"][role]
    with pytest.raises(m.Refusal, match="EVIDENCE_MISSING"):
        fixture.run_join()


def test_independent_receipt_disagreement_refuses_before_input_open(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    fixture.back["rows"] += 1
    fixture.flush_receipts()
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.resolve() != fixture.path.resolve(), "partition opened before evidence agreement"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(m.Refusal, match="INDEPENDENT_ARTIFACT_DRIFT"):
        fixture.run_join()


def test_metadata_validation_never_opens_partition_or_link(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.resolve() not in {fixture.path.resolve(), fixture.linkpath.resolve()}
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    m.validate_binding(fixture.binding, m.Limits())


@pytest.mark.parametrize("role", ["job", "codec", "typed_schema", "readback", "raw_pins"])
def test_metadata_hash_drift(tmp_path, role):
    fixture = Fixture(tmp_path)
    with Path(fixture.binding["sources"][role]["path"]).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(m.Refusal, match="SOURCE_HASH_DRIFT"):
        fixture.run_join()


@pytest.mark.parametrize("target", ["input", "link", "evidence"])
def test_midstream_mutation_discards_diagnostic(tmp_path, monkeypatch, target):
    fixture = Fixture(tmp_path)
    original = m.classify
    called = False

    def mutate(*args):
        nonlocal called
        if not called:
            path = {"input": fixture.path, "link": fixture.linkpath,
                    "evidence": fixture.packet / "READBACK_JOB01.json"}[target]
            raw = path.read_bytes()
            path.write_bytes(raw + b" ")
            called = True
        return original(*args)

    monkeypatch.setattr(m, "classify", mutate)
    with pytest.raises(m.Refusal):
        fixture.run_join()
    assert called


def test_same_size_input_mutation_after_buffered_read(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    original = m.classify

    def mutate(*args):
        raw = fixture.path.read_bytes()
        changed = raw.replace(b"C05_exact_typed", b"C06_exact_typed", 1)
        assert len(changed) == len(raw) and changed != raw
        fixture.path.write_bytes(changed)
        return original(*args)

    monkeypatch.setattr(m, "classify", mutate)
    with pytest.raises(m.Refusal):
        fixture.run_join()


def test_link_source_hash_and_schema_drift(tmp_path):
    fixture = Fixture(tmp_path)
    fixture.binding["link"]["sha256"] = "a" * 64
    with pytest.raises(m.Refusal, match="LINK_HASH_OR_BYTES_DRIFT"):
        fixture.run_join()
    fixture.flush_receipts()
    fixture.binding["link"]["columns"] = list(reversed(m.LINK_COLUMNS))
    with pytest.raises(m.Refusal, match="LINK_REFERENCE_OR_LIMIT"):
        fixture.run_join()


def test_actual_parquet_column_schema_checked(tmp_path):
    fixture = Fixture(tmp_path)
    table = pq.read_table(fixture.linkpath).rename_columns(list(reversed(m.LINK_COLUMNS)))
    pq.write_table(table, fixture.linkpath)
    fixture.flush_receipts()
    with pytest.raises(m.Refusal, match="PARQUET_SCHEMA_OR_ROWS"):
        fixture.run_join()


@pytest.mark.parametrize("patch", [dict(input_bytes=10), dict(input_rows=1), dict(line_bytes=20),
                                    dict(link_bytes=10), dict(link_rows=1), dict(parquet_footer_bytes=4),
                                    dict(parquet_uncompressed_bytes=8), dict(arrow_batch_bytes=1),
                                    dict(links_per_key=1), dict(score_buckets=1), dict(metadata_bytes=20)])
def test_resource_limits_refuse_not_truncate(tmp_path, patch):
    fixture = Fixture(tmp_path, rows=[row(), row()], links=[link(), link(score=5)])
    with pytest.raises(m.Refusal):
        fixture.run_join(replace(m.Limits(), **patch))


def test_parquet_decompression_limit_precedes_batch_read(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("decompressed before advertised uncompressed-byte preflight")

    monkeypatch.setattr(pq.ParquetFile, "iter_batches", forbidden)
    with pytest.raises(m.Refusal, match="PARQUET_UNCOMPRESSED_LIMIT"):
        fixture.run_join(replace(m.Limits(), parquet_uncompressed_bytes=1))


def test_wall_limit(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    values = iter([0.0, 1000.0])
    monkeypatch.setattr(m.time, "monotonic", lambda: next(values))
    with pytest.raises(m.Refusal, match="WALL_LIMIT"):
        fixture.run_join()


@pytest.mark.parametrize("suffix", [b"", b"\n", b"[]\n", b"garbage\n"])
def test_incomplete_or_extra_stream_refuses(tmp_path, suffix):
    fixture = Fixture(tmp_path)
    raw = fixture.path.read_bytes()
    fixture.path.write_bytes(raw[:-2] + suffix if suffix == b"" else raw + suffix)
    # Repin the byte stream so syntax/count checks, rather than merely a hash, must fire.
    fixture.sync_evidence()
    with pytest.raises(m.Refusal):
        fixture.run_join()


@pytest.mark.parametrize("raw", [b'[["str","x"], ["date","2025-01-16"],NaN]\n',
                                b'[["str","x"], ["date","2025-01-16"],]\n',
                                b'[["str","x"], ["date","2025-01-16"], [1 2]]\n',
                                b'[["str","x"], ["date","2025-01-16"], [truefalse]]\n'])
def test_excluded_cell_syntax_is_still_checked(raw):
    with pytest.raises(m.Refusal):
        m.project_row(raw, 3, {0, 1})


def test_excluded_values_not_materialized(monkeypatch):
    raw = json.dumps(row(extra=["float64_bits", "excluded-value-not-valid-hex"])).encode()
    original = m.parse_json

    def guarded(part):
        assert "excluded-value" not in part
        return original(part)

    monkeypatch.setattr(m, "parse_json", guarded)
    projected = m.project_row(raw, 3, {0, 1})
    assert set(projected) == {0, 1}


def test_json_duplicate_keys_and_deep_excluded_values_refuse():
    with pytest.raises(m.Refusal, match="DUPLICATE_JSON_KEY"):
        m.parse_json('{"rows":1,"rows":2}')
    raw = b'[["str","x"],["date","2025-01-16"],' + b'[' * 15 + b'0' + b']' * 15 + b']'
    with pytest.raises(m.Refusal, match="ROW_JSON_DEPTH_OR_SYNTAX"):
        m.project_row(raw, 3, {0, 1})


def test_date_type_not_datetime_and_no_key_normalization():
    assert m.calendar_date("2025-01-16T00:00:00") is None
    assert m.calendar_date(date(2025, 1, 16)) == date(2025, 1, 16)
    assert m.typed_projection(["str", " " + KEY], "str", m.Limits())[0] == "malformed"
    assert m.typed_projection(["null", "secret"], "str", m.Limits())[0] == "malformed"


def test_cli_success_private_create_only_and_refusal_privacy(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m, "PRIVATE_ROOT", tmp_path)
    fixture = Fixture(tmp_path / "fixture")
    bindingpath = tmp_path / "binding.json"
    write_json(bindingpath, fixture.binding)
    args = ["--binding", str(bindingpath), "--binding-sha256", ref(bindingpath)["sha256"],
            "--output-dir", str(tmp_path / "result"), "--consume-one-partition"]
    assert m.main(args) == 0
    stored = (tmp_path / "result/RESULT.json").read_text()
    assert json.loads(stored)["rows"] == 1
    assert m.main(args) == 2
    assert (tmp_path / "result/RESULT.json").read_text() == stored
    fixture.path.unlink()
    args[5] = str(tmp_path / "refused")
    assert m.main(args) == 2
    refusal = (tmp_path / "refused/REFUSED.json").read_text()
    assert "rows" not in json.loads(refusal)
    for secret in (KEY, str(PERMNO), str(fixture.path), "Traceback"):
        assert secret not in capsys.readouterr().out + refusal


def test_cli_input_error_messages_do_not_leak(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(m, "PRIVATE_ROOT", tmp_path)
    source = tmp_path / "binding.json"
    source.write_text("{}", encoding="utf-8")

    def private_failure(*args, **kwargs):
        raise RuntimeError(KEY + str(PERMNO))

    monkeypatch.setattr(m, "run_diagnostic", private_failure)
    assert m.main(["--binding", str(source), "--binding-sha256", ref(source)["sha256"],
                   "--output-dir", str(tmp_path / "failed"), "--consume-one-partition"]) == 2
    stored = (tmp_path / "failed/REFUSED.json").read_text()
    assert KEY not in stored + capsys.readouterr().out
    assert str(PERMNO) not in stored
    assert "rows" not in json.loads(stored)


# Observed pinned schema shape only. Every value below is newly synthetic.
LINK_NS_SCHEMA = pa.schema([
    ("ticker", pa.string()), ("permno", pa.int64()), ("ncusip", pa.string()),
    ("sdate", pa.timestamp("ns")), ("edate", pa.timestamp("ns")), ("score", pa.float64())])
DAY_NS = 86_400_000_000_000


def synthetic_date_ns(day):
    return (date.fromisoformat(day) - date(1970, 1, 1)).days * DAY_NS


def synthetic_ns_link(**overrides):
    return dict(link(start=synthetic_date_ns("2025-01-01"),
                     end=synthetic_date_ns("2025-01-31")), **overrides)


def set_synthetic_ns_links(fixture, links=None, schema=LINK_NS_SCHEMA):
    values = links if links is not None else [synthetic_ns_link()]
    arrays = []
    for field in schema:
        column = [value[field.name] for value in values]
        # Construct timestamp storage from integers so a 1 ns component cannot
        # disappear through a Python datetime/pandas conversion in the fixture.
        array = (pa.array(column, type=pa.int64()).cast(field.type)
                 if pa.types.is_timestamp(field.type) else pa.array(column, type=field.type))
        arrays.append(array)
    table = pa.Table.from_arrays(arrays, schema=schema)
    pq.write_table(table, fixture.linkpath, compression="gzip", version="2.6")
    fixture.linkrows = len(values)
    fixture.flush_receipts()  # Existing synthetic-only evidence machinery.


def test_pinned_schema_shape_end_to_end_synthetic_only(tmp_path):
    rows = [row(day="2025-01-01"), row(day="2025-01-31"), row(), row(), row(OTHER), row(None)]
    reference = Fixture(tmp_path / "strings", rows=rows).run_join()
    fixture = Fixture(tmp_path / "timestamp_ns", rows=rows)
    set_synthetic_ns_links(fixture)
    with pq.ParquetFile(fixture.linkpath) as pf:
        assert pf.schema_arrow.equals(LINK_NS_SCHEMA)
        assert all(field.nullable for field in pf.schema_arrow)
        for name in ("sdate", "edate"):
            col = pf.schema.column(m.LINK_COLUMNS.index(name))
            assert col.physical_type == "INT64"
            assert "isAdjustedToUTC=false" in str(col.logical_type)
    result = fixture.run_join()
    assert result["rows"] == 6
    assert result["categories"]["one_unique_permno"] == 4
    assert result["categories"]["no_link"] == 1
    assert result["categories"]["missing_key_or_date"] == 1
    for name in ("categories", "projected_cell_states", "active_link_row_matches",
                 "active_link_score_buckets_row_weighted", "observations_multiple_permnos",
                 "observations_multiple_link_rows_one_permno"):
        assert result[name] == reference[name]
    assert sum(result["categories"].values()) == 6
    assert all(sum(states.values()) == 6 for states in result["projected_cell_states"].values())
    assert result["link_source"]["rows"] == 1
    assert result["link_source"]["unqualified_rows"] == 0
    assert result["link_sha256_before"] == result["link_sha256_after"]
    for private in (KEY, OTHER, str(PERMNO), "SYNTH_CUSIP_DO_NOT_EXPORT", str(tmp_path)):
        assert private not in json.dumps(result)


@pytest.mark.parametrize("day", ["1677-09-22", "1900-03-01", "1969-12-31", "1970-01-01",
                                  "2000-02-29", "2024-02-29", "2025-01-01", "2262-04-11"])
def test_link_timestamp_ns_exact_midnight_dates(day):
    assert m.link_timestamp_ns_date(synthetic_date_ns(day)) == date.fromisoformat(day)


@pytest.mark.parametrize("value", [None, True, False, 0.0, "0", 1, -1, DAY_NS - 1,
                                    DAY_NS + 1, -(2**63), 2**63 - 1, -(2**63) - 1, 2**63])
def test_link_timestamp_ns_rejects_ambiguous_nonmidnight_or_invalid_integer(value):
    assert m.link_timestamp_ns_date(value) is None


def test_arrow_null_nat_sentinel_and_negative_subsecond_storage_are_not_truncated():
    storage = [None, -(2**63), -1, -DAY_NS, -DAY_NS + 1, DAY_NS + 1]
    timestamps = pa.array(storage, type=pa.int64()).cast(pa.timestamp("ns"))
    recovered = timestamps.cast(pa.int64()).to_pylist()
    assert recovered == storage
    assert [m.link_timestamp_ns_date(value) for value in recovered] == [
        None, None, None, date(1969, 12, 31), None, None]


def test_numpy_nat_becomes_null_and_keeps_link_unqualified(tmp_path):
    import numpy as np
    values = pa.array(np.array(["NaT"], dtype="datetime64[ns]"), from_pandas=True)
    assert values.type == pa.timestamp("ns")
    assert values.null_count == 1 and values.cast(pa.int64()).to_pylist() == [None]
    fixture = Fixture(tmp_path)
    bad = synthetic_ns_link()
    bad["sdate"] = values.cast(pa.int64()).to_pylist()[0]
    set_synthetic_ns_links(fixture, [synthetic_ns_link(), bad])
    result = fixture.run_join()
    assert result["categories"]["unqualified_link"] == 1
    assert result["categories"]["one_unique_permno"] == 0


@pytest.mark.parametrize("field", ["sdate", "edate"])
@pytest.mark.parametrize("offset", [None, 1, -1, 1000, 1_000_000, DAY_NS // 2, DAY_NS - 1])
def test_nonmidnight_ns_or_null_interval_stays_unqualified(tmp_path, field, offset):
    fixture = Fixture(tmp_path)
    bad = synthetic_ns_link()
    bad[field] = None if offset is None else bad[field] + offset
    set_synthetic_ns_links(fixture, [synthetic_ns_link(), bad])
    result = fixture.run_join()
    assert result["categories"]["unqualified_link"] == 1
    assert result["categories"]["one_unique_permno"] == 0
    assert result["link_source"]["unqualified_rows"] == 1


@pytest.mark.parametrize("start,end,expected", [
    ("1969-12-31", "2025-01-16", "one_unique_permno"),
    ("2025-01-16", "2025-01-16", "one_unique_permno"),
    ("2025-01-17", "2025-01-31", "no_link"),
    ("2024-12-01", "2025-01-15", "no_link"),
    ("2026-01-01", "2026-01-31", "no_link"),
    ("2025-01-31", "2025-01-01", "unqualified_link")])
def test_timestamp_ns_inclusive_disjoint_future_and_reversed_intervals(tmp_path, start, end, expected):
    fixture = Fixture(tmp_path)
    values = synthetic_ns_link()
    values.update(sdate=synthetic_date_ns(start), edate=synthetic_date_ns(end))
    set_synthetic_ns_links(fixture, [values])
    assert fixture.run_join()["categories"][expected] == 1


@pytest.mark.parametrize("field", ["sdate", "edate"])
@pytest.mark.parametrize("dtype", [pa.timestamp("ns", tz="UTC"), pa.timestamp("ns", tz="Asia/Singapore"),
                                    pa.timestamp("s"), pa.timestamp("ms"), pa.timestamp("us")])
def test_timestamp_schema_support_is_limited_to_observed_naive_ns_date_fields(tmp_path, monkeypatch, field, dtype):
    fixture = Fixture(tmp_path)
    schema = LINK_NS_SCHEMA.set(m.LINK_COLUMNS.index(field), pa.field(field, dtype))
    # Zero is exact midnight in every unit, so refusal must be on schema.
    values = synthetic_ns_link()
    values[field] = 0
    set_synthetic_ns_links(fixture, [values], schema)

    def forbidden(*args, **kwargs):
        pytest.fail("decoded before timezone/unit schema refusal")

    monkeypatch.setattr(pq.ParquetFile, "iter_batches", forbidden)
    with pytest.raises(m.Refusal, match="PARQUET_PRIMITIVE_SCHEMA"):
        fixture.run_join()


@pytest.mark.parametrize("field", ["ticker", "permno", "ncusip", "score"])
def test_timestamp_schema_never_accepted_in_other_columns(tmp_path, field):
    fixture = Fixture(tmp_path)
    schema = LINK_NS_SCHEMA.set(m.LINK_COLUMNS.index(field), pa.field(field, pa.timestamp("ns")))
    values = synthetic_ns_link()
    values[field] = 0
    set_synthetic_ns_links(fixture, [values], schema)
    with pytest.raises(m.Refusal, match="PARQUET_PRIMITIVE_SCHEMA"):
        fixture.run_join()


def test_timestamp_schema_keeps_excluded_column_schema_and_byte_preflights(tmp_path, monkeypatch):
    fixture = Fixture(tmp_path)
    values = synthetic_ns_link()
    values["ncusip"] = "SYNTHETIC_PADDING_" * 1024
    set_synthetic_ns_links(fixture, [values])
    with pq.ParquetFile(fixture.linkpath) as pf:
        group = pf.metadata.row_group(0)
        total = sum(group.column(i).total_uncompressed_size for i in range(6))
        excluded = group.column(2).total_uncompressed_size
    assert 0 < total - excluded < total

    def forbidden(*args, **kwargs):
        pytest.fail("decoded before all-column advertised-size refusal")

    monkeypatch.setattr(pq.ParquetFile, "iter_batches", forbidden)
    with pytest.raises(m.Refusal, match="PARQUET_UNCOMPRESSED_LIMIT"):
        fixture.run_join(replace(m.Limits(), parquet_uncompressed_bytes=total - excluded))
    schema = LINK_NS_SCHEMA.set(2, pa.field("ncusip", pa.list_(pa.string())))
    values["ncusip"] = ["SYNTHETIC_NESTED"]
    set_synthetic_ns_links(fixture, [values], schema)
    with pytest.raises(m.Refusal, match="PARQUET_PRIMITIVE_SCHEMA"):
        fixture.run_join()


@pytest.mark.parametrize("conflict", [False, True])
def test_timestamp_schema_keeps_duplicate_and_conflicting_identity_policy(tmp_path, conflict):
    fixture = Fixture(tmp_path, rows=[row(), row()])
    other = synthetic_ns_link()
    if conflict:
        other["permno"] += 1
        other["score"] = 6
    set_synthetic_ns_links(fixture, [synthetic_ns_link(), other])
    result = fixture.run_join()
    category = "multiple_permnos" if conflict else "overlap_one_permno"
    assert result["categories"][category] == 2
    assert result["categories"]["one_unique_permno"] == 0
    assert result["active_link_row_matches"] == 4


def test_timestamp_link_support_does_not_relax_raw_observation_date_or_strings():
    for value in (datetime(2025, 1, 16), datetime(2025, 1, 16, tzinfo=timezone.utc),
                  "2025-01-16T00:00:00", "2025-01-16T00:00:00Z"):
        assert m.calendar_date(value) is None
        assert m.typed_projection(["date", value], "date", m.Limits())[0] == "malformed"


def test_timestamp_schema_cli_refusal_exports_no_partial_counts(tmp_path, monkeypatch, capsys):
    fixture = Fixture(tmp_path / "fixture")
    schema = LINK_NS_SCHEMA.set(3, pa.field("sdate", pa.timestamp("ns", tz="UTC")))
    set_synthetic_ns_links(fixture, schema=schema)
    monkeypatch.setattr(m, "PRIVATE_ROOT", tmp_path)
    bindingpath = tmp_path / "binding.json"
    write_json(bindingpath, fixture.binding)
    output = tmp_path / "timestamp_refusal"
    assert m.main(["--binding", str(bindingpath), "--binding-sha256", ref(bindingpath)["sha256"],
                   "--output-dir", str(output), "--consume-one-partition"]) == 2
    stored = (output / "REFUSED.json").read_text()
    assert json.loads(stored)["gate"] == "PARQUET_PRIMITIVE_SCHEMA"
    assert set(json.loads(stored)) == {"schema", "status", "gate", "claims"}
    assert not (output / "RESULT.json").exists()
    for private in (KEY, str(PERMNO), str(tmp_path)):
        assert private not in stored + capsys.readouterr().out
