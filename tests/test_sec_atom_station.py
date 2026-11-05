"""Synthetic offline SEC metadata station contracts; no application imports."""

from datetime import datetime, timezone
import json
from pathlib import Path
import socket

import pytest

from scripts import sec_atom_station as S

PUBLISHED = "2026-11-04T21:30:00Z"
SEEN = "2026-11-04T22:44:42Z"


def row(cik="123", accession="0009999999-26-000001", form="8-K", **changes):
    value = dict(
        source=S.SOURCE,
        raw_id=accession,
        title=f"{form} - Example Holdings, Inc. ({cik}) (Filer)",
        url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm",
        published_utc=PUBLISHED,
        first_seen_utc=SEEN,
        body="BODY_SECRET_SENTINEL",
        entity_tags=[f"cik:{cik}", "8-K:2.02", "resolved:XYZ=name"],
        tickers=["XYZ"],
    )
    value.update(changes)
    return value


def write_manifest(tmp, source):
    path = tmp / ("manifest-" + S.digest(source.read_bytes()) + ".json")
    value = dict(
        schema="sec-atom-snapshot/1",
        adapter=S.ADAPTER,
        source=S.SOURCE,
        relative_path=f"{S.SOURCE}/{source.name}",
        sha256=S.digest(source.read_bytes()),
        bytes=source.stat().st_size,
        observed_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    path.write_bytes(S.canonical(value))
    return path, S.digest(path.read_bytes())


def setup(tmp, rows):
    root = tmp / "news_corpus"
    folder = root / S.SOURCE
    folder.mkdir(parents=True)
    source = folder / "2026-11-04.jsonl"
    data = b"".join(v if isinstance(v, bytes) else S.canonical(v) + b"\n" for v in rows)
    source.write_bytes(data)
    output = tmp / "station"
    output.mkdir()
    path, sha = write_manifest(tmp, source)
    return dict(
        source_root=root, manifest_path=path, manifest_sha256=sha, output_dir=output
    ), source


def bundles(kw):
    return [
        S.unseal(S.parse(p.read_bytes()))
        for p in sorted(kw["output_dir"].glob("pass-*/bundle.json"))
    ]


def test_filing_metadata_agent_prefix_and_rights(tmp_path, monkeypatch):
    kw, source = setup(tmp_path, [row()])
    before = source.read_bytes()

    def deny(*a, **k):
        raise AssertionError("network denied")

    monkeypatch.setattr(socket.socket, "connect", deny)
    result = S.run_pass(**kw)
    record = bundles(kw)[0]["records"][0]
    assert record["issuer_cik"] == "0000000123"
    assert record["raw_accession"].startswith("0009999999")
    assert record["security_identity"] == "UNKNOWN"
    assert record["issuer_resolution"] == "UNRESOLVED"
    assert record["hint_authority"] == "HEURISTIC_DISCOVERY_HINT"
    assert record["acceptance_utc"] == record["event_date"] == "UNKNOWN"
    assert record["published_basis"] == "ATOM_UPDATED_AS_PUBLISHED"
    assert record["exhibit_acquisition_complete"] is False
    assert result["receipt"]["coverage"] == "PARTIAL"
    assert result["receipt"]["scope"] == "FIRST_100_PHYSICAL_LINES"
    assert "BODY_SECRET_SENTINEL" not in json.dumps(bundles(kw))
    assert source.read_bytes() == before


def test_zero_padding_amendment_cross_filer_and_versions(tmp_path):
    a = row()
    padded = row(cik="0000000123")
    other = row(cik="456")
    amendment = row(accession="0009999999-26-000002", form="8-K/A")
    changed = dict(a, body="DIFFERENT_BODY_NOT_EXPORTED")
    kw, _ = setup(tmp_path, [a, padded, other, amendment, changed, a])
    result = S.run_pass(**kw)
    records = bundles(kw)[0]["records"]
    assert records[0]["filing_id"] == records[1]["filing_id"]
    assert records[0]["filing_id"] != records[2]["filing_id"]
    assert records[2]["cross_observation_ambiguity"] is True
    assert len(records[2]["observed_ciks_for_accession"]) == 2
    assert records[3]["form"] == "8-K/A" and records[3]["amends_filing_id"] == "UNKNOWN"
    assert result["receipt"]["counts"] == dict(
        attempted=6,
        projected_new=5,
        exact_replays=1,
        quarantined=0,
        explicitly_excluded=0,
        changed_versions=2,
    )
    assert len(bundles(kw)[0]["occurrences"]) == 6


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"source": "sec_edgar_8k_ex99_body"}, "WRONG_SOURCE"),
        ({"raw_id": "https://www.sec.gov/fallback"}, "INVALID_ACCESSION"),
        ({"raw_id": "bad"}, "INVALID_ACCESSION"),
        ({"entity_tags": ["cik:456"]}, "CONFLICTING_CIK"),
        ({"entity_tags": ["cik:0000000000"]}, "INVALID_CIK"),
        ({"url": "https://evil.test/Archives/edgar/data/123/x"}, "INVALID_SEC_URL"),
        ({"url": "https://www.sec.gov@evil.test/Archives/edgar/data/123/x"}, "INVALID_SEC_URL"),
        ({"url": "https://www.sec.gov/Archives/../secret"}, "NOT_FILING_INDEX"),
        ({"url": row()["url"] + "?secret=BODY_SECRET_SENTINEL"}, "INVALID_SEC_URL"),
        ({"url": row()["url"].replace("/123/", "/456/")}, "CONFLICTING_CIK"),
        (
            {"url": row()["url"].replace("000999999926000001", "000999999926000009")},
            "ACCESSION_URL_MISMATCH",
        ),
        ({"url": row()["url"].replace("-index.htm", "ex99-1.htm")}, "NOT_FILING_INDEX"),
        ({"url": row()["url"].replace("-index.htm", "ex99-2.htm")}, "NOT_FILING_INDEX"),
        ({"published_utc": None}, "INVALID_CLOCK"),
        ({"published_utc": "2026-11-04"}, "INVALID_CLOCK"),
        ({"first_seen_utc": "2026-11-04T22:44:42"}, "INVALID_CLOCK"),
        ({"published_utc": "2026-11-04T23:00:00Z"}, "PUBLICATION_AFTER_FIRST_SEEN"),
        ({"first_seen_utc": "2099-11-04T22:44:42Z"}, "FUTURE_CLOCK"),
        ({"title": "10-Q - Example Holdings, Inc. (123) (Filer)"}, "UNSUPPORTED_FORM_OR_TITLE"),
        ({"tickers": ["BODY_SECRET_SENTINEL"]}, "INVALID_HINT"),
        ({"entity_tags": ["8-K:SECRET"]}, "INVALID_ITEM_CODE"),
        ({"tickers": ["X"] * 33}, "TAG_LIMIT"),
    ],
)
def test_named_metadata_quarantines(tmp_path, changes, reason):
    kw, _ = setup(tmp_path, [row(**changes)])
    result = S.run_pass(**kw)
    assert result["receipt"]["counts"]["quarantined"] == 1
    assert result["receipt"]["reason_counts"] == {reason: 1}
    assert bundles(kw)[0]["records"] == []
    assert "BODY_SECRET_SENTINEL" not in json.dumps(bundles(kw))


@pytest.mark.parametrize(
    "raw", [b"\n", b"{bad}\n", b"\xff\n", b'{"source":1,"source":2}\n', b"[]\n"]
)
def test_physical_malformed_lines_are_accounted_not_replaced(tmp_path, raw):
    kw, _ = setup(tmp_path, [raw, row()])
    result = S.run_pass(**kw, line_limit=1)
    assert (
        result["receipt"]["counts"]["attempted"] == result["receipt"]["counts"]["quarantined"] == 1
    )
    assert result["receipt"]["remaining_physical_rows"] == 1
    assert result["receipt"]["cursor_after_line"] == 1


def test_exact_committed_replay_and_chunked_resume(tmp_path):
    kw, _ = setup(tmp_path, [row(), row(), row(accession="0009999999-26-000002")])
    first = S.run_pass(**kw, line_limit=2)
    contents = {p: p.read_bytes() for p in kw["output_dir"].glob("pass-*/bundle.json")}
    cursor = (kw["output_dir"] / "cursor.json").read_bytes()
    replay = S.run_pass(**kw, line_limit=2)
    assert replay["execution"] == "COMMITTED_PASS_REPLAY" and replay["receipt"] == first["receipt"]
    assert (kw["output_dir"] / "cursor.json").read_bytes() == cursor
    assert all(p.read_bytes() == v for p, v in contents.items())
    second = S.run_pass(**kw, start_line=2, line_limit=2)
    assert second["receipt"]["cursor_after_line"] == 3 and len(bundles(kw)) == 2
    with pytest.raises(S.StationRefused, match="CURSOR_POSITION_MISMATCH"):
        S.run_pass(**kw, start_line=1, line_limit=2)


@pytest.mark.parametrize(
    "boundary",
    [
        "before_bundle",
        "after_stage",
        "after_bundle",
        "before_cursor",
        "after_cursor_stage",
        "before_cursor_replace",
        "after_cursor",
    ],
)
def test_crash_boundaries_recover_without_duplicates(tmp_path, boundary):
    kw, _ = setup(tmp_path, [row()])

    def crash(stage):
        if stage == boundary:
            raise RuntimeError("simulated process crash")

    with pytest.raises(RuntimeError):
        S.run_pass(**kw, _fault=crash)
    result = S.run_pass(**kw)
    assert result["receipt"]["counts"]["projected_new"] == 1
    assert len(bundles(kw)) == 1
    assert S.run_pass(**kw)["execution"] == "COMMITTED_PASS_REPLAY"
    assert S.unseal(S.parse((kw["output_dir"] / "cursor.json").read_bytes()))["physical_lines"] == 1


def test_append_new_witness_unchanged_prefix(tmp_path):
    kw, source = setup(tmp_path, [row()])
    S.run_pass(**kw)
    with source.open("ab") as f:
        f.write(S.canonical(row(accession="0009999999-26-000002")) + b"\n")
    path, sha = write_manifest(tmp_path, source)
    kw.update(manifest_path=path, manifest_sha256=sha)
    result = S.run_pass(**kw, start_line=1)
    assert result["receipt"]["counts"]["attempted"] == 1
    assert result["receipt"]["cursor_after_line"] == 2


@pytest.mark.parametrize(
    "mode",
    [
        "same_size",
        "truncated",
        "reordered",
        "missing",
        "parser_drift",
        "cursor_tamper",
        "bundle_tamper",
    ],
)
def test_integrity_failures_leave_cursor_unchanged(tmp_path, mode):
    kw, source = setup(tmp_path, [row(), row(accession="0009999999-26-000002")])
    S.run_pass(**kw, line_limit=1)
    cursor = kw["output_dir"] / "cursor.json"
    if mode == "same_size":
        import os

        stamp = source.stat()
        source.write_bytes(source.read_bytes().replace(b"Example", b"Exomple", 1))
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    elif mode == "truncated":
        source.write_bytes(source.read_bytes().splitlines(keepends=True)[0])
    elif mode == "reordered":
        source.write_bytes(b"".join(reversed(source.read_bytes().splitlines(keepends=True))))
    elif mode == "missing":
        source.unlink()
    elif mode == "parser_drift":
        data = S.unseal(S.parse(cursor.read_bytes()))
        data["adapter"] = "different/2"
        cursor.write_bytes(S.canonical(S.seal(data)))
    elif mode == "cursor_tamper":
        cursor.write_bytes(cursor.read_bytes().replace(b'physical_lines":1', b'physical_lines":2'))
    else:
        p = next(kw["output_dir"].glob("pass-*/bundle.json"))
        p.write_bytes(p.read_bytes() + b" ")
    before = cursor.read_bytes()
    if mode in ["same_size", "truncated", "reordered"]:
        path, sha = write_manifest(tmp_path, source)
        kw.update(manifest_path=path, manifest_sha256=sha)
    with pytest.raises(S.StationRefused):
        S.run_pass(**kw, start_line=1, line_limit=1)
    assert cursor.read_bytes() == before


@pytest.mark.parametrize(
    "raw,reason",
    [(b"x" * 32769 + b"\n", "LINE_BYTE_LIMIT"), (b"{}", "PARTIAL_TRAILING_LINE")],
    ids=["oversize", "partial"],
)
def test_structural_caps_do_not_commit(tmp_path, raw, reason):
    kw, _ = setup(tmp_path, [raw])
    with pytest.raises(S.StationRefused, match=reason):
        S.run_pass(**kw)
    assert not (kw["output_dir"] / "cursor.json").exists()


def test_output_and_resource_caps_refuse_before_cursor(tmp_path, monkeypatch):
    kw, _ = setup(tmp_path, [row()])
    monkeypatch.setattr(S, "MAX_OUTPUT", 100)
    with pytest.raises(S.StationRefused, match="OUTPUT_OR_STATE_LIMIT"):
        S.run_pass(**kw)
    assert not (kw["output_dir"] / "cursor.json").exists()
    monkeypatch.setattr(S, "MAX_OUTPUT", 1_048_576)
    monkeypatch.setattr(S, "MAX_IO", 100)
    with pytest.raises(S.StationRefused):
        S.run_pass(**kw)
    assert not (kw["output_dir"] / "cursor.json").exists()


def test_source_changed_during_pass_no_cursor(tmp_path, monkeypatch):
    kw, source = setup(tmp_path, [row()])
    original = S.project

    def mutate(value, observed):
        with source.open("ab") as f:
            f.write(S.canonical(row()) + b"\n")
        return original(value, observed)

    monkeypatch.setattr(S, "project", mutate)
    with pytest.raises(S.StationRefused):
        S.run_pass(**kw, line_limit=1)
    assert not (kw["output_dir"] / "cursor.json").exists()


def test_manifest_pin_traversal_and_future(tmp_path):
    kw, _ = setup(tmp_path, [row()])
    with pytest.raises(S.StationRefused, match="MANIFEST_PIN_MISMATCH"):
        S.run_pass(**dict(kw, manifest_sha256="a" * 64))
    data = json.loads(kw["manifest_path"].read_bytes())
    for field, value in [
        ("relative_path", "../secret"),
        ("source", "other"),
        ("observed_at_utc", "2099-01-01T00:00:00Z"),
    ]:
        altered = dict(data, **{field: value})
        kw["manifest_path"].write_bytes(S.canonical(altered))
        kw["manifest_sha256"] = S.digest(kw["manifest_path"].read_bytes())
        with pytest.raises(S.StationRefused):
            S.run_pass(**kw)
    assert not (kw["output_dir"] / "cursor.json").exists()


def test_cross_file_lineage_and_sibling_exhibits(tmp_path):
    kw, _ = setup(tmp_path, [row()])
    S.run_pass(**kw)
    other = tmp_path / "other"
    other.mkdir()
    kw2, source = setup(other, [row()])
    source.rename(source.with_name("2026-11-03.jsonl"))
    path, sha = write_manifest(other, source.with_name("2026-11-03.jsonl"))
    kw2.update(manifest_path=path, manifest_sha256=sha)
    S.run_pass(**kw2)
    a, b = bundles(kw)[0], bundles(kw2)[0]
    assert a["records"][0]["metadata_version_id"] == b["records"][0]["metadata_version_id"]
    assert a["occurrences"][0]["occurrence_id"] != b["occurrences"][0]["occurrence_id"]
    for filename in ["ex99-1.htm", "ex99-2.htm"]:
        with pytest.raises(S.StationRefused, match="NOT_FILING_INDEX"):
            S.project(
                row(url=row()["url"].rsplit("/", 1)[0] + "/" + filename), datetime.now(timezone.utc)
            )


def test_no_application_or_network_imports():
    import ast

    tree = ast.parse(Path(S.__file__).read_text(encoding="utf-8-sig"))
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(n.startswith(("backend", "requests", "socket", "http")) for n in imports)


def test_first_100_physical_bound_and_remaining(tmp_path):
    rows = [row(accession=f"0009999999-26-{n:06d}") for n in range(150)]
    rows[1] = b"\n"
    kw, _ = setup(tmp_path, rows)
    result = S.run_pass(**kw)
    assert result["receipt"]["counts"]["attempted"] == 100
    assert result["receipt"]["counts"]["quarantined"] == 1
    assert result["receipt"]["counts"]["projected_new"] == 99
    assert result["receipt"]["remaining_physical_rows"] == 50
    assert result["receipt"]["total_input_io_bytes"] <= S.MAX_IO
    assert len(bundles(kw)[0]["records"]) == 99


def test_clock_quarantine_preserves_safe_evidence(tmp_path):
    kw, _ = setup(tmp_path, [row(published_utc="SECRET_CLOCK_SENTINEL")])
    result = S.run_pass(**kw)
    refusal = bundles(kw)[0]["quarantines"][0]
    assert result["receipt"]["status"] == "QUARANTINED_ONLY"
    assert refusal["clock_evidence"]["published_utc"]["raw"] == "UNKNOWN"
    assert refusal["clock_evidence"]["published_utc"]["parsed_utc"] == "UNKNOWN"
    assert refusal["clock_evidence"]["first_seen_utc"]["raw"] == SEEN
    assert "SECRET_CLOCK_SENTINEL" not in json.dumps(bundles(kw))


def test_deadline_and_state_cap(tmp_path, monkeypatch):
    kw, _ = setup(tmp_path, [row()])
    monkeypatch.setattr(S, "MAX_SECONDS", -1)
    with pytest.raises(S.StationRefused, match="TIME_LIMIT"):
        S.run_pass(**kw)
    assert not (kw["output_dir"] / "cursor.json").exists()
    monkeypatch.setattr(S, "MAX_SECONDS", 30)
    monkeypatch.setattr(S, "MAX_STATE", 100)
    with pytest.raises(S.StationRefused, match="OUTPUT_OR_STATE_LIMIT"):
        S.run_pass(**kw)
    assert not (kw["output_dir"] / "cursor.json").exists()


def test_no_pending_distinguished(tmp_path):
    kw, _ = setup(tmp_path, [])
    result = S.run_pass(**kw)
    assert result["receipt"]["status"] == "NO_PENDING_ROWS"
    assert result["receipt"]["counts"]["attempted"] == 0
    assert result["receipt"]["remaining_physical_rows"] == 0


def test_rehashed_cursor_cannot_override_commit_anchor(tmp_path):
    kw, _ = setup(tmp_path, [row(), row(accession="0009999999-26-000002")])
    S.run_pass(**kw, line_limit=1)
    path = kw["output_dir"] / "cursor.json"
    cursor = S.unseal(S.parse(path.read_bytes()))
    cursor["versions"] = {}
    path.write_bytes(S.canonical(S.seal(cursor)))
    before = path.read_bytes()
    with pytest.raises(S.StationRefused, match="CURSOR_ANCHOR_MISMATCH"):
        S.run_pass(**kw, start_line=1, line_limit=1)
    assert path.read_bytes() == before


def test_cli_fixed_error_and_quarantine_exit(tmp_path, capsys):
    kw, _ = setup(tmp_path, [row(published_utc="PRIVATE_CLOCK")])
    argv = [
        "--source-root",
        str(kw["source_root"]),
        "--manifest",
        str(kw["manifest_path"]),
        "--manifest-sha256",
        kw["manifest_sha256"],
        "--output-dir",
        str(kw["output_dir"]),
    ]
    assert S.main(argv) == 1
    output = capsys.readouterr()
    assert "PRIVATE_CLOCK" not in output.out and not output.err
    argv[argv.index("--manifest-sha256") + 1] = "a" * 64
    assert S.main(argv) == 2
    output = capsys.readouterr()
    assert output.out == "" and json.loads(output.err) == {"error": "MANIFEST_PIN_MISMATCH"}


def test_output_in_repository_and_changed_stream_refuse(tmp_path):
    kw, _ = setup(tmp_path, [row()])
    (kw["output_dir"] / ".git").mkdir()
    with pytest.raises(S.StationRefused, match="OUTPUT_IN_REPOSITORY"):
        S.run_pass(**kw)
    (kw["output_dir"] / ".git").rmdir()
    S.run_pass(**kw)
    manifest = json.loads(kw["manifest_path"].read_bytes())
    source = kw["source_root"] / manifest["relative_path"]
    renamed = source.with_name("2026-11-03.jsonl")
    renamed.write_bytes(source.read_bytes())
    path, sha = write_manifest(tmp_path, renamed)
    with pytest.raises(S.StationRefused, match="CURSOR_BINDING"):
        S.run_pass(**dict(kw, manifest_path=path, manifest_sha256=sha))


def test_redirect_path_rejected(tmp_path):
    kw, _ = setup(tmp_path, [row()])
    link = tmp_path / "redirect"
    import os
    import subprocess

    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(kw["source_root"])],
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0
    else:
        link.symlink_to(kw["source_root"], target_is_directory=True)
    try:
        with pytest.raises(S.StationRefused, match="REDIRECT_PATH"):
            S.run_pass(**dict(kw, source_root=link))
    finally:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()


def test_append_at_commit_boundary_and_manifest_tamper(tmp_path):
    kw, source = setup(tmp_path, [row()])

    def mutate(stage):
        if stage == "before_cursor":
            with source.open("ab") as f:
                f.write(b"\n")

    with pytest.raises(S.StationRefused, match="SOURCE_CHANGED_BEFORE_CURSOR"):
        S.run_pass(**kw, _fault=mutate)
    assert not (kw["output_dir"] / "cursor.json").exists()
    with pytest.raises(S.StationRefused):
        S.run_pass(**kw)


def test_manifest_replaced_during_pass_no_cursor(tmp_path):
    kw, _ = setup(tmp_path, [row()])

    def mutate(stage):
        if stage == "before_cursor":
            kw["manifest_path"].write_bytes(b"{}")

    with pytest.raises(S.StationRefused, match="MANIFEST_CHANGED_BEFORE_CURSOR"):
        S.run_pass(**kw, _fault=mutate)
    assert not (kw["output_dir"] / "cursor.json").exists()


def test_partial_staging_rebuilds_and_never_duplicates(tmp_path):
    kw, _ = setup(tmp_path, [row()])

    def crash(stage):
        if stage == "after_stage":
            raise RuntimeError("crash")

    with pytest.raises(RuntimeError):
        S.run_pass(**kw, _fault=crash)
    (stage,) = kw["output_dir"].glob(".pass-*.pending/bundle.json")
    stage.write_bytes(b"{partial")
    S.run_pass(**kw)
    assert len(bundles(kw)) == 1
    assert S.run_pass(**kw)["execution"] == "COMMITTED_PASS_REPLAY"


def test_identifiers_require_ascii_digits_and_forged_authority_is_ignored():
    with pytest.raises(S.StationRefused, match="INVALID_CIK"):
        S.cik("???")
    projected = S.project(
        row(canonical_security="XYZ", held=True, cause="FORGED", forecast=1),
        datetime.now(timezone.utc),
    )
    assert projected["security_identity"] == "UNKNOWN"
    assert (
        "canonical_security" not in projected
        and "held" not in projected
        and "cause" not in projected
        and "forecast" not in projected
    )
