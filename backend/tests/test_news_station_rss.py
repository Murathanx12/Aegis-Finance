"""Saved RSS projection remains bounded, historical and source-only."""
from datetime import datetime, timezone
import hashlib
import json
import socket
import subprocess
import sys

import pytest

from scripts import news_station_rss as N

NOW = datetime(2026, 11, 5, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    source = tmp_path / "repo/backend/data/optimus/news_corpus/google_news_rss_en_gb/2026-11-01.jsonl"
    source.parent.mkdir(parents=True)
    evidence = tmp_path / "evidence"

    def forbidden(*_args, **_kwargs):
        pytest.fail("network/provider path reached")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    return source, evidence


def _raw(title="Source headline", **extra):
    row = {"source": N.SOURCE, "title": title, "body": "Description text",
           "url": "https://example.test/story", "tickers": [],
           "published_utc": "2026-11-01T02:40:00+00:00",
           "first_seen_utc": "2026-11-01T04:39:46+00:00"} | extra
    return (json.dumps(row, separators=(",", ":")) + "\n").encode()


def _pass(result):
    return json.loads(open(result["receipt_path"], "rb").read())


def test_multi_pass_eventual_file_snapshot_coverage_and_exact_clocks(paths):
    source, evidence = paths
    rows = [_raw(title=f"Headline {n}", url=f"https://example.test/{n}") for n in range(5)]
    source.write_bytes(b"".join(rows))
    passes = [N.project_file(source, evidence, max_rows=2, now=NOW) for _ in range(3)]
    assert [p["projected_rows"] for p in passes] == [2, 2, 1]
    assert all(p["coverage"] == "PARTIAL" for p in passes)
    assert passes[0]["denominator"]["exact"] is False
    assert passes[-1]["denominator"] == {
        "scope": "ONE_SOURCE_FILE", "exact": True, "eligible_rows": 5,
        "rows_lower_bound": 5, "unread_bytes_at_snapshot": 0}
    assert passes[-1]["cursor_after"] == source.stat().st_size
    first = _pass(passes[0])["projections"][0]
    assert first["raw_row_sha256"] == hashlib.sha256(rows[0]).hexdigest()
    assert (first["event_at"], first["published_at"], first["first_seen_at"],
            first["projected_at"]) == (
        None, "2026-11-01T02:40:00+00:00", "2026-11-01T04:39:46+00:00",
        NOW.isoformat())
    assert first["byte_start"] == 0 and first["byte_end"] == len(rows[0])
    assert len(list((evidence / "station_cursors").glob("*.json"))) == 1
    no_new = N.project_file(source, evidence, max_rows=2, now=NOW)
    assert no_new["projected_rows"] == 0 and no_new["denominator"]["exact"] is True


def test_append_then_same_length_rewrite_blocks_without_cursor_leap(paths):
    source, evidence = paths
    first = _raw(title="Headline Alpha")
    source.write_bytes(first)
    initial = N.project_file(source, evidence, now=NOW)
    with source.open("ab") as stream:
        stream.write(_raw(title="Headline Beta"))
    appended = N.project_file(source, evidence, now=NOW)
    assert appended["projected_rows"] == 1 and appended["line_after"] == 2
    contents = source.read_bytes().replace(b"Headline Alpha", b"Headline Omega")
    assert len(contents) == source.stat().st_size
    source.write_bytes(contents)
    blocked = N.project_file(source, evidence, now=NOW)
    assert blocked["coverage"] == "BLOCKED"
    assert blocked["reason"] == "SOURCE_PREFIX_REWRITTEN"
    assert blocked["cursor_before"] == blocked["cursor_after"] == appended["cursor_after"]
    assert initial["receipt_path"] != appended["receipt_path"]


def test_malformed_and_oversized_rows_block_with_exact_hash(paths):
    source, evidence = paths
    good = _raw()
    bad = b"{bad json}\n"
    source.write_bytes(good + bad)
    malformed = N.project_file(source, evidence, now=NOW)
    assert malformed["coverage"] == "BLOCKED" and malformed["reason"] == "MALFORMED_ROW"
    assert malformed["blocked_row_sha256"] == hashlib.sha256(bad).hexdigest()
    assert malformed["cursor_after"] == 0
    assert _pass(malformed)["projections"] == []
    huge = _raw(body="X" * 500)
    source.write_bytes(huge)
    oversized = N.project_file(source, evidence, max_row_bytes=128, now=NOW)
    assert oversized["reason"] == "OVERSIZED_ROW"
    assert oversized["blocked_row_sha256"] == hashlib.sha256(huge).hexdigest()
    assert oversized["cursor_after"] == 0
    assert b"X" * 100 not in open(oversized["receipt_path"], "rb").read()


def test_false_binance_tgt_tag_creates_no_identity_or_text(paths):
    source, evidence = paths
    source.write_bytes(_raw(title="Binance $6.3bn hack reported",
                            tickers=["TGT"], entity_tags=["resolved:TGT=name"],
                            body="Licensed body must never be projected"))
    result = N.project_file(source, evidence, now=NOW)
    output = open(result["receipt_path"], "rb").read()
    assert result["projected_rows"] == 1
    assert all(term not in output for term in (b"Binance", b"TGT", b"Licensed body"))
    projected = _pass(result)["projections"][0]
    assert projected["issuer_edges"] == projected["causal_edges"] == projected["held_edges"] == []
    assert projected["forecast_authority"] == "NONE"
    assert projected["owner_delivery"] == "NOT_ATTEMPTED"


def test_pass_bundle_replays_after_cursor_write_failure(paths, monkeypatch):
    source, evidence = paths
    source.write_bytes(_raw())
    original = N._atomic_json

    def cursor_fails(path, body):
        if path.parent.name == "station_cursors":
            raise OSError("simulated cursor I/O failure")
        original(path, body)

    monkeypatch.setattr(N, "_atomic_json", cursor_fails)
    with pytest.raises(OSError):
        N.project_file(source, evidence, now=NOW)
    monkeypatch.setattr(N, "_atomic_json", original)
    result = N.project_file(source, evidence, now=NOW)
    assert result["projected_rows"] == 1
    assert len(list((evidence / "station_passes").glob("*.json"))) == 1
    assert result["cursor_after"] == source.stat().st_size


def test_output_inside_source_root_is_refused(paths):
    source, _ = paths
    source.write_bytes(_raw())
    with pytest.raises(ValueError, match="REPOSITORY_OUTPUT_REFUSED"):
        N.project_file(source, source.parents[2] / "brain/station", now=NOW)


def test_two_dated_files_keep_distinct_projection_cursors(paths):
    source, evidence = paths
    second = source.with_name("2026-11-02.jsonl")
    source.write_bytes(_raw(title="First") + _raw(title="Second"))
    second.write_bytes(_raw(title="Other file"))
    partial = N.project_file(source, evidence, max_rows=1, now=NOW)
    other = N.project_file(second, evidence, max_rows=1, now=NOW)
    finished = N.project_file(source, evidence, max_rows=1, now=NOW)
    assert partial["denominator"]["exact"] is False
    assert other["denominator"]["eligible_rows"] == 1
    assert finished["denominator"]["eligible_rows"] == 2
    assert len(list((evidence / "station_cursors").glob("*.json"))) == 2


def test_truncation_and_malformed_clock_keep_previous_cursor(paths):
    source, evidence = paths
    first = _raw()
    source.write_bytes(first)
    initial = N.project_file(source, evidence, now=NOW)
    source.write_bytes(first[:20])
    truncated = N.project_file(source, evidence, now=NOW)
    assert truncated["reason"] == "SOURCE_TRUNCATED"
    assert truncated["cursor_after"] == initial["cursor_after"]

    # Separate unprojected file: bad clock is not converted to UNKNOWN.
    second = source.with_name("2026-11-02.jsonl")
    bad = _raw(first_seen_utc="not-a-clock")
    second.write_bytes(bad)
    blocked = N.project_file(second, evidence, now=NOW)
    assert blocked["reason"] == "MALFORMED_CLOCK"
    assert blocked["cursor_after"] == 0
    assert blocked["blocked_row_sha256"] == hashlib.sha256(bad).hexdigest()


@pytest.mark.parametrize("field,value", [
    ("issuer_edges", [{"issuer": "Target", "symbol": "TGT"}]),
    ("owner_delivery", "DELIVERED"),
])
def test_pending_pass_replay_refuses_forged_authority(paths, monkeypatch, field, value):
    source, evidence = paths
    source.write_bytes(_raw(title="Binance reported", tickers=["TGT"]))
    original = N._atomic_json

    def fail_cursor(path, body):
        if path.parent.name == "station_cursors":
            raise OSError("interrupted after pass commit")
        original(path, body)

    monkeypatch.setattr(N, "_atomic_json", fail_cursor)
    with pytest.raises(OSError):
        N.project_file(source, evidence, now=NOW)
    monkeypatch.setattr(N, "_atomic_json", original)
    pass_path, = (evidence / "station_passes").glob("*.json")
    forged = json.loads(pass_path.read_bytes())
    forged["projections"][0][field] = value
    pass_path.write_bytes(N._json(forged))
    blocked = N.project_file(source, evidence, now=NOW)
    assert blocked["coverage"] == "BLOCKED" and blocked["reason"] == "PASS_REPLAY_CONFLICT"
    assert blocked["cursor_after"] == 0
    assert list((evidence / "station_cursors").glob("*.json")) == []


@pytest.mark.parametrize("forge", ["skip_to_eof", "line_only", "wrong_last_pass_id"])
def test_cursor_must_match_linked_pass_offset_and_line(paths, forge):
    source, evidence = paths
    source.write_bytes(_raw(title="First") + _raw(title="Second"))
    first = N.project_file(source, evidence, max_rows=1, now=NOW)
    cursor_path, = (evidence / "station_cursors").glob("*.json")
    cursor = json.loads(cursor_path.read_bytes())
    if forge == "skip_to_eof":
        cursor["byte_offset"] = source.stat().st_size
        cursor["line_number"] = 2
        cursor["prefix_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    elif forge == "line_only":
        cursor["line_number"] = 101
    else:
        cursor["last_pass_id"] = "0" * 64
    cursor_path.write_bytes(N._json(cursor))
    blocked = N.project_file(source, evidence, max_rows=1, now=NOW)
    assert blocked["coverage"] == "BLOCKED" and blocked["reason"] == "COMMITTED_PASS_INVALID"
    assert blocked["projected_rows"] == 0
    assert len(list((evidence / "station_passes").glob("*.json"))) == 2  # original + blocked
    assert first["line_after"] == 1


@pytest.mark.parametrize("tamper", ["authority", "extra_field", "bool_count"])
def test_committed_receipt_allowlist_rejects_forgery_even_with_cursor_rehash(paths, tamper):
    source, evidence = paths
    source.write_bytes(_raw())
    N.project_file(source, evidence, now=NOW)
    pass_path, = (evidence / "station_passes").glob("*.json")
    cursor_path, = (evidence / "station_cursors").glob("*.json")
    forged = json.loads(pass_path.read_bytes())
    if tamper == "authority":
        forged["projections"][0]["owner_delivery"] = "DELIVERED"
        forged["projections"][0]["issuer_edges"] = [{"symbol": "TGT"}]
    elif tamper == "extra_field":
        forged["owner_delivery"] = "DELIVERED"
    else:
        forged["denominator"]["eligible_rows"] = True  # True == 1 in Python
    pass_path.write_bytes(N._json(forged))
    cursor = json.loads(cursor_path.read_bytes())
    cursor["last_pass_sha256"] = hashlib.sha256(pass_path.read_bytes()).hexdigest()
    cursor_path.write_bytes(N._json(cursor))
    blocked = N.project_file(source, evidence, now=NOW)
    assert blocked["coverage"] == "BLOCKED" and blocked["reason"] == "COMMITTED_PASS_INVALID"
    assert blocked["projected_rows"] == 0


def test_entire_repo_and_sibling_worktree_output_roots_are_refused(paths):
    source, evidence = paths
    source.write_bytes(_raw())
    repo = source.parents[5]
    for output in (repo / "docs/station-evidence", repo / "scripts/station-evidence"):
        with pytest.raises(ValueError, match="REPOSITORY_OUTPUT_REFUSED"):
            N.project_file(source, output, now=NOW)
        assert not output.exists()
    other = evidence.parent / "other_worktree"
    other.mkdir()
    (other / ".git").write_text("gitdir: external", encoding="utf-8")
    with pytest.raises(ValueError, match="REPOSITORY_OUTPUT_REFUSED"):
        N.project_file(source, other / "docs/station-evidence", now=NOW)


def test_output_junction_or_symlink_component_is_refused(paths):
    source, evidence = paths
    source.write_bytes(_raw())
    target = source.parents[5] / "docs"
    target.mkdir()
    link = evidence.parent / "linked_docs"
    if sys.platform == "win32":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            pytest.skip("junction creation unavailable")
    else:
        link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="REPOSITORY_OUTPUT_REFUSED"):
        N.project_file(source, link / "station-evidence", now=NOW)
    assert not (target / "station-evidence").exists()


def test_older_pass_forgery_cannot_hide_behind_rehashed_chain(paths):
    source, evidence = paths
    source.write_bytes(_raw(title="First") + _raw(title="Second") + _raw(title="Third"))
    for _ in range(3):
        N.project_file(source, evidence, max_rows=1, now=NOW)
    indexed = sorted((json.loads(p.read_bytes())["cursor_before"], p)
                     for p in (evidence / "station_passes").glob("*.json"))
    first, second, third = [p for _, p in indexed]
    forged = json.loads(first.read_bytes())
    forged["projections"][0]["owner_delivery"] = "DELIVERED"
    first.write_bytes(N._json(forged))
    middle = json.loads(second.read_bytes())
    middle["previous_pass_sha256"] = hashlib.sha256(first.read_bytes()).hexdigest()
    second.write_bytes(N._json(middle))
    last = json.loads(third.read_bytes())
    last["previous_pass_sha256"] = hashlib.sha256(second.read_bytes()).hexdigest()
    third.write_bytes(N._json(last))
    cursor_path, = (evidence / "station_cursors").glob("*.json")
    cursor = json.loads(cursor_path.read_bytes())
    cursor["last_pass_sha256"] = hashlib.sha256(third.read_bytes()).hexdigest()
    cursor_path.write_bytes(N._json(cursor))
    blocked = N.project_file(source, evidence, now=NOW)
    assert blocked["coverage"] == "BLOCKED" and blocked["reason"] == "COMMITTED_PASS_INVALID"
    assert blocked["projected_rows"] == 0


def test_output_subdirectory_junction_cannot_write_into_repo(paths):
    source, evidence = paths
    source.write_bytes(_raw())
    evidence.mkdir()
    target = source.parents[5] / "docs"
    target.mkdir()
    link = evidence / "station_passes"
    if sys.platform == "win32":
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            pytest.skip("junction creation unavailable")
    else:
        link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="REPOSITORY_OUTPUT_REFUSED"):
        N.project_file(source, evidence, now=NOW)
    assert list(target.glob("*.json")) == []
