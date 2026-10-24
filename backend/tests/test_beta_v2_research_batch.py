"""Bounded readiness tests: local fixtures only, no strategy or P&L evaluation."""
from datetime import date, datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts import beta_v2_research_batch as R
from backend.services import data_catalog as C


@pytest.fixture
def selected(tmp_path):
    root, runtime = tmp_path / "repo", tmp_path / "runtime"
    (root / "docs").mkdir(parents=True)
    runtime.mkdir()
    (root / "docs/CANON.md").write_text("fixture canon", encoding="utf8")
    (root / "NEGATIVE_RESULTS.md").write_text("\n".join(
        "## " + s + ". fixture" for s in {s for f in R.FAMILIES.values() for s in f["failure_sections"]}), encoding="utf8")
    path = runtime / R.INPUTS[0][2]
    path.parent.mkdir(parents=True)
    pq.write_table(pa.table({"date": [date(2020, 1, 2), date(2020, 1, 3)]}), path)
    row = {"path": R.INPUTS[0][2], "schema_hash": C.inspect_parquet(path)["schema_hash"],
           "content": {"mode": "full", "sha256": R.hash_file(path)}}
    catalogue = tmp_path / "catalogue.json"
    def save(rows=None, **updates):
        data = {"schema_version": "data_catalog/1", "utc": "2020-01-04T00:00:00Z", "run_id": "fixture", "rows": rows if rows is not None else [row]}
        data.update(updates)
        catalogue.write_text(json.dumps(data), encoding="utf8")
    save()
    return SimpleNamespace(root=root, runtime=runtime, path=path, row=row, catalogue=catalogue, save=save)


def manifest(f, **kwargs):
    return R.build_manifest(f.catalogue, f.runtime, root=f.root, limit=kwargs.pop("limit", 1), **kwargs)


def inspect(f, **kwargs):
    return R.inspect_input(R.INPUTS[0], kwargs.pop("row", f.row), f.runtime,
                           sample_rows=kwargs.pop("sample_rows", 64), max_file_bytes=kwargs.pop("max_file_bytes", 64 * 1024**2), **kwargs)


def test_five_families_twenty_one_arms_and_zero_evaluations(selected):
    value = manifest(selected)
    assert value["denominators"]["planned_families"] == 5
    assert value["denominators"]["planned_arms"] == len(value["arms"]) == 21
    assert value["denominators"]["arm_evaluations_attempted"] == 0
    assert value["denominators"]["historical_cumulative_trials"] is None
    assert all(a["registration_id"] is None and a["p_value"] is None for a in value["arms"])
    assert value["readiness"] == "unknown_not_qualified"


@pytest.mark.parametrize("bad", ["yesterday", "2020-02-30", "2020-01-01T12:00:00", None])
def test_bad_catalogue_clock_refuses_before_data_reads(selected, bad):
    selected.save(utc=bad)
    with pytest.raises(ValueError, match="clock"):
        manifest(selected)


def test_clock_types_and_timezone_normalization_are_honest():
    value = R.structural_diagnostic([
        {"id": "a", "at": "2020-01-01T12:00:00+08:00"},
        {"id": "b", "at": "2020-01-01T04:00:00Z"},
        {"id": "c", "at": "2020-01-01T12:00:00"},
        {"id": "d", "at": "bad"}], ("id",), ("at",))
    assert value["clocks"]["at"]["present"] == 2
    assert value["clocks"]["at"]["missing_or_invalid"] == 2
    assert value["clocks"]["at"]["sample_min"] == value["clocks"]["at"]["sample_max"]
    assert value["lookahead_validation"] == "not established by clock presence"


def test_date_labels_are_not_silently_mixed_with_instants():
    value = R.structural_diagnostic([{"id": 1, "at": date(2020, 1, 1)},
                                     {"id": 2, "at": datetime(2020, 1, 1, tzinfo=timezone.utc)}], ("id",), ("at",))
    assert value["clocks"]["at"]["date_labels"] == 1
    assert value["clocks"]["at"]["aware_instants"] == 1
    assert value["clocks"]["at"]["sample_min"] is None


@pytest.mark.parametrize("path", ["../outside.parquet", "/outside.parquet", "x/*.parquet", "x/a?b", "x/secret:stream", ""])
def test_invalid_or_escaping_path_refuses(selected, path):
    with pytest.raises(ValueError):
        R.local_path(selected.runtime, path)


def test_missing_and_invalid_keys_are_not_valid_duplicate_events():
    rows = [{"k": None}, {"k": ""}, {"k": []}, {"k": float("nan")}, {"k": True}, {"k": "x"}, {"k": "x"}]
    value = R.structural_diagnostic(rows, ("k",), ())
    assert value["missing_key_rows"] == 2
    assert value["invalid_key_rows"] == 3
    assert value["duplicate_key_rows"] == 1
    assert value["defects_observed"] and not value["population_claim"]


@pytest.mark.parametrize("content", [{"mode": "sample", "sha256": "a" * 64}, {"mode": "full", "sha256": "bad"}, ["wrong"]])
def test_missing_or_malformed_full_hash_cannot_qualify(selected, content):
    row = {**selected.row, "content": content}
    assert inspect(selected, row=row)["status"] == "blocked"


def test_changed_content_refuses_without_sampling(selected):
    selected.path.write_bytes(b"changed parquet bytes")
    value = inspect(selected)
    assert value["status"] == "changed" and value["sampled_rows"] == 0


def test_schema_hash_mismatch_blocks_sample(selected):
    row = {**selected.row, "schema_hash": "0" * 16}
    value = inspect(selected, row=row)
    assert value["status"] == "blocked" and value["sampled_rows"] == 0


def test_missing_columns_claim_is_limited_to_selected_file(selected):
    pq.write_table(pa.table({"other": [1]}), selected.path)
    row = {**selected.row, "schema_hash": C.inspect_parquet(selected.path)["schema_hash"],
           "content": {"mode": "full", "sha256": R.hash_file(selected.path)}}
    value = inspect(selected, row=row)
    assert value["missing_required_columns"] == ["date"]
    assert value["status"] == "blocked"


@pytest.mark.parametrize("size", [R.DECOMPRESS_LIMIT + 1, None, -1])
def test_decompression_budget_refuses_before_iter_batches(selected, monkeypatch, size):
    fake = SimpleNamespace(schema_arrow=SimpleNamespace(names=["date"]), metadata=SimpleNamespace(
        num_columns=1, num_row_groups=1, num_rows=100,
        schema=SimpleNamespace(column=lambda _: SimpleNamespace(path="date")),
        row_group=lambda _: SimpleNamespace(column=lambda _: SimpleNamespace(total_uncompressed_size=size))))
    fake.iter_batches = lambda **_: pytest.fail("must not decompress")
    monkeypatch.setattr(C, "inspect_parquet", lambda _: {"schema_hash": selected.row["schema_hash"]})
    monkeypatch.setattr(pq, "ParquetFile", lambda _: fake)
    value = inspect(selected)
    assert value["status"] == "blocked" and value["sampled_rows"] == 0


def test_first_row_group_prefix_does_not_spill_into_later_groups(selected):
    pq.write_table(pa.table({"date": [date(2020, 1, 2), date(2020, 1, 3)]}), selected.path, row_group_size=1)
    selected.row["content"]["sha256"] = R.hash_file(selected.path)
    value = inspect(selected)
    assert value["sampled_rows"] == 1
    assert value["sample_fraction_of_footer_rows"] == 0.5
    assert value["readiness"] == "unqualified"


def test_source_change_during_sample_discards_diagnostic(selected, monkeypatch):
    calls = []
    real = R.hash_file
    def unstable(path):
        calls.append(path)
        return real(path) if len(calls) == 1 else "f" * 64
    monkeypatch.setattr(R, "hash_file", unstable)
    value = inspect(selected)
    assert value["status"] == "changed" and value["diagnostic_discarded"]
    assert "diagnostic" not in value


def test_final_hash_io_failure_discards_sample_and_family_admission(selected, monkeypatch):
    real = R.hash_file
    calls = []
    def unavailable_after_sampling(path):
        if Path(path) == selected.path:
            calls.append(path)
            if len(calls) == 2:
                raise OSError("synthetic final source verification unavailable")
        return real(path)
    monkeypatch.setattr(R, "hash_file", unavailable_after_sampling)
    result = manifest(selected)
    value = result["inputs"][0]
    assert len(calls) == 2
    assert value["status"] == "blocked"
    assert value["readiness"] == "unqualified"
    assert value["diagnostic_discarded"] is True
    assert value["attempted_sample_rows"] == 2
    assert value["sampled_rows"] == 0
    assert "diagnostic" not in value
    assert "sample_fraction_of_footer_rows" not in value
    assert "OSError" in value["reason"]
    assert result["denominators"]["actual_diagnostic_families"] == []
    assert all("rf_series" in arm["unqualified_structural_inputs"]
               for arm in result["arms"] if arm["family"] == "rf_nr")


@pytest.mark.parametrize("limits", [{"sample_rows": 0}, {"sample_rows": 129}, {"limit": True}, {"limit": 0}, {"max_file_bytes": 0}, {"max_file_bytes": 65 * 1024**2}])
def test_resource_limits_fail_closed(selected, limits):
    with pytest.raises(ValueError):
        manifest(selected, **limits)


def test_file_budget_blocks_before_hash_or_sample(selected, monkeypatch):
    monkeypatch.setattr(R, "hash_file", lambda _: pytest.fail("over-budget file must not be hashed"))
    value = inspect(selected, max_file_bytes=1)
    assert value["status"] == "blocked" and value["observed_sha256"] is None


def test_duplicate_catalogue_paths_and_wrong_schema_refuse(selected):
    selected.save(rows=[selected.row, selected.row])
    with pytest.raises(ValueError, match="duplicate catalogue"):
        manifest(selected)
    selected.save(schema_version="unrecognized")
    with pytest.raises(ValueError, match="schema"):
        manifest(selected)


def test_duplicate_json_keys_and_overflow_numbers_refuse():
    for raw in ('{"status":0,"status":1}', '{"n":NaN}', '{"n":1e9999}'):
        with pytest.raises(ValueError):
            R.strict_json(raw)


def test_resume_recomputes_sample_instead_of_trusting_modified_metrics(selected):
    prior = manifest(selected)
    prior["inputs"][0]["diagnostic"]["missing_key_rows"] = 999
    current = manifest(selected, prior=prior)
    assert current["checkpoint"]["next_offset"] == 2
    assert current["inputs"][0]["diagnostic"]["missing_key_rows"] == 0
    assert current["inputs"][0]["resume"].startswith("rehash_and_recompute")


@pytest.mark.parametrize("change", ["tool", "schema", "readiness", "cursor", "ids", "input_status", "input_path", "pit", "research_complete", "observation_clock"])
def test_invalid_resume_contract_or_unknown_readiness_refuses(selected, change):
    prior = manifest(selected)
    if change == "tool":
        prior["contract"]["tool_sha256"] = "f" * 64
    elif change == "schema":
        prior["schema"] = "aegis-beta-v2-research-qualification/1"
    elif change == "readiness":
        prior["readiness"] = "ready"
    elif change == "cursor":
        prior["checkpoint"]["next_offset"] = True
    elif change == "ids":
        prior["inputs"][1]["id"] = prior["inputs"][0]["id"]
    elif change == "input_status":
        prior["inputs"][1]["status"] = "structure_checked"
    elif change == "input_path":
        prior["inputs"][0]["path"] = "different.parquet"
    elif change == "pit":
        prior["inputs"][0]["pit_status"] = "verified"
    elif change == "research_complete":
        prior["checkpoint"]["research_complete"] = True
    else:
        prior["observed_at"] = "yesterday"
    with pytest.raises(ValueError):
        manifest(selected, prior=prior)


def test_cli_prior_requires_matching_hash(selected, tmp_path, capsys):
    prior_path = tmp_path / "prior.json"
    prior_path.write_text(json.dumps(manifest(selected)), encoding="utf8")
    args = ["--catalogue", str(selected.catalogue), "--runtime-root", str(selected.runtime),
            "--prior-manifest", str(prior_path)]
    assert R.main(args) == 1
    assert "SHA256" in capsys.readouterr().out
    assert R.main(args + ["--prior-sha256", "0" * 64]) == 1
    assert "hash mismatch" in capsys.readouterr().out


def test_exact_missing_slot_is_not_global_source_absence(selected):
    value = R.inspect_input(R.INPUTS[-1], None, selected.runtime, sample_rows=64, max_file_bytes=1000)
    assert value["status"] == "blocked" and "No exact existing input bound" in value["reason"]
    assert value["readiness"] == "unqualified"
