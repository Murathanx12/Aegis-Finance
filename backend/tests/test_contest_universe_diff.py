"""Tiny offline archives exercise accounting, refusals and sanitized CLI output."""
import json
import socket
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts import contest_universe_diff as D


def archive(tmp_path, day, pairs, *, mutate=None, row_mutate=None):
    path = tmp_path / f"universe_{day}.parquet"
    receipt_path = tmp_path / f"universe_{day}_receipt.json"
    rows = [dict(market=m, symbol=s, membership=D.MEMBERSHIP, screened_on=day)
            for m, s in pairs]
    if row_mutate:
        row_mutate(rows)
    schema = pa.schema([(c, pa.string()) for c in D.COLUMNS])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, row_group_size=2)
    receipt = dict(path=str(path), written_utc=day.replace("-", "") + "T120000Z",
                   rows_after=len(rows), membership=D.MEMBERSHIP,
                   by_market={"n": dict(Counter(m for m, _ in pairs))})
    if mutate:
        mutate(receipt)
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return path, receipt_path


def test_accounting_exact_keys_and_no_source_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    old = archive(tmp_path, "2026-10-22", [("US", "A"), ("US", "a"), ("HK", "A")])
    new = archive(tmp_path, "2026-11-01", [("US", "A"), ("US", "B"), ("HK", "A")])
    before = [D.digest(p) for p in (*old, *new)]
    result = D.compare(*old, *new)
    assert (result["persisted"], result["old_only"], result["new_only"]) == (2, 1, 1)
    assert result["by_market"][1]["observed_key_entries"] == 1
    assert result["membership"] == D.MEMBERSHIP
    assert result["first_seen"] == result["pit_availability"] == "UNKNOWN"
    assert [D.digest(p) for p in (*old, *new)] == before
    assert str(tmp_path) not in json.dumps(result)


def test_missing_market_is_not_churn(tmp_path):
    old = archive(tmp_path, "2026-10-22", [("US", "A"), ("HK", "A")])
    new = archive(tmp_path, "2026-11-01", [("HK", "A"), ("JP", "A")])
    result = D.compare(*old, *new)
    markets = {m["market"]: m for m in result["by_market"]}
    for m in ("US", "JP"):
        assert markets[m]["observed_key_exits"] is None
        assert markets[m]["observed_key_entries"] is None
        assert markets[m]["old_persistence_pct"] is None
    assert markets["US"]["coverage"] == "MISSING_NEW_MARKET"
    assert markets["JP"]["coverage"] == "MISSING_OLD_MARKET"
    assert result["old_only"] == result["new_only"] == 1


@pytest.mark.parametrize("mutate,code", [
    (lambda r: r.update(rows_after=4), "RECEIPT_COUNT_MISMATCH"),
    (lambda r: r.update(rows_after=True), "INVALID_ROW_COUNT"),
    (lambda r: r.update(written_utc="20260230T120000Z"), "INVALID_RECEIPT_CLOCK"),
    (lambda r: r.update(written_utc="20261023T120000Z"), "RECEIPT_DATE_MISMATCH"),
    (lambda r: r.update(written_utc=None), "INVALID_RECEIPT_CLOCK"),
    (lambda r: r.update(path="universe_2026-10-21.parquet"), "RECEIPT_PATH_MISMATCH"),
    (lambda r: r.update(by_market={"n": {"HK": 1}}), "MARKET_COUNT_MISMATCH"),
    (lambda r: r.update(by_market={"n": {"US": -1}}), "INVALID_MARKET_COUNTS"),
    (lambda r: r.update(membership="CONFIRMED_WLS"), "INVALID_MEMBERSHIP"),
])
def test_bad_receipts(tmp_path, mutate, code):
    pair = archive(tmp_path, "2026-10-22", [("US", "A")], mutate=mutate)
    with pytest.raises(D.SnapshotRefused, match=code):
        D.load_snapshot(*pair)


@pytest.mark.parametrize("field,value,code", [
    ("symbol", None, "INVALID_KEY"), ("symbol", "", "INVALID_KEY"),
    ("symbol", "X\nprivate", "INVALID_KEY"), ("symbol", "a" * 129, "INVALID_KEY"),
    ("market", "private/path", "INVALID_MARKET"),
    ("membership", "CONFIRMED_WLS", "INVALID_MEMBERSHIP"),
    ("screened_on", "2026-02-30", "INVALID_DATE"),
    ("screened_on", "2026-10-23", "SCREENING_AFTER_RECEIPT"),
])
def test_bad_rows(tmp_path, field, value, code):
    pair = archive(tmp_path, "2026-10-22", [("US", "A")],
                   row_mutate=lambda rows: rows[0].update({field: value}))
    with pytest.raises(D.SnapshotRefused, match=code):
        D.load_snapshot(*pair)


def test_duplicate_across_batches(tmp_path):
    pair = archive(tmp_path, "2026-10-22", [("US", str(i)) for i in range(513)] + [("US", "0")])
    with pytest.raises(D.SnapshotRefused, match="DUPLICATE_KEY"):
        D.load_snapshot(*pair)


def test_empty_and_zero_market_counts(tmp_path):
    old = archive(tmp_path, "2026-10-22", [],
                  mutate=lambda r: r.update(by_market={"n": {"US": 0}}))
    new = archive(tmp_path, "2026-11-01", [])
    result = D.compare(*old, *new)
    assert result["by_market"] == [] and result["persisted"] == 0


def test_prior_screen_date_and_reverse_clock(tmp_path):
    old = archive(tmp_path, "2026-10-22", [("US", "A")])
    new = archive(tmp_path, "2026-11-01", [("US", "A")],
                  row_mutate=lambda rows: rows[0].update(screened_on="2026-10-31"))
    assert D.compare(*old, *new)["inputs"]["new"]["screened_on_census"] == {"2026-10-31": 1}
    for args in ((*new, *old), (*old, *old)):
        with pytest.raises(D.SnapshotRefused, match="NONINCREASING"):
            D.compare(*args)


def test_schema_and_size_limits(tmp_path, monkeypatch):
    pair = archive(tmp_path, "2026-10-22", [("US", "A")])
    monkeypatch.setattr(D, "MAX_PROJECTED_BYTES", 1)
    with pytest.raises(D.SnapshotRefused, match="PROJECTED_INPUT_LIMIT"):
        D.load_snapshot(*pair)
    monkeypatch.setattr(D, "MAX_PROJECTED_BYTES", 16 * 1024 * 1024)
    pq.write_table(pa.table({"market": ["US"], "symbol": [1]}), pair[0])
    with pytest.raises(D.SnapshotRefused, match="INVALID_SCHEMA"):
        D.load_snapshot(*pair)
    monkeypatch.setattr(D, "MAX_FILE_BYTES", 1)
    with pytest.raises(D.SnapshotRefused, match="INPUT_LIMIT"):
        D.load_snapshot(*pair)


def test_cli_sanitizes_errors_and_success(tmp_path, capsys):
    old = archive(tmp_path, "2026-10-22", [("US", "A")])
    new = archive(tmp_path, "2026-11-01", [("US", "A")])
    argv = ["--old-parquet", str(old[0]), "--old-receipt", str(old[1]),
            "--new-parquet", str(new[0]), "--new-receipt", str(new[1])]
    assert D.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["persisted"] == 1
    old[1].write_text('{"private":"secret","private":2}', encoding="utf-8")
    assert D.main(argv) == 2
    output = capsys.readouterr().out
    assert json.loads(output) == {"status": "REFUSED", "reason": "DUPLICATE_RECEIPT_FIELD"}
    assert "private" not in output and str(tmp_path) not in output


def test_input_change_detected(tmp_path, monkeypatch):
    pair = archive(tmp_path, "2026-10-22", [("US", "A")])
    original = D.digest
    calls = []
    def changed(path):
        calls.append(path)
        return original(path) if len(calls) <= 2 else "changed"
    monkeypatch.setattr(D, "digest", changed)
    with pytest.raises(D.SnapshotRefused, match="INPUT_CHANGED"):
        D.load_snapshot(*pair)


def test_no_remote_or_directory_inputs(tmp_path):
    for path in ("//server/share/input.parquet", "https://host/input.parquet"):
        with pytest.raises(D.SnapshotRefused, match="LOCAL_INPUT_REQUIRED"):
            D.load_snapshot(path, path)
    with pytest.raises(D.SnapshotRefused, match="INPUT_NOT_FILE"):
        D.load_snapshot(tmp_path, tmp_path)


def test_projection_skips_unrelated_nested_columns(tmp_path):
    pair = archive(tmp_path, "2026-10-22", [("US", "A")])
    original = pq.read_table(pair[0])
    table = pa.table({"unused": pa.array([{"nested": "unrelated"}]),
                      **{c: original[c] for c in D.COLUMNS}})
    pq.write_table(table, pair[0])
    keys, _ = D.load_snapshot(*pair)
    assert keys == {"US": {"A"}}


def test_metadata_row_count_mismatch(tmp_path):
    pair = archive(tmp_path, "2026-10-22", [("US", "A")],
                   mutate=lambda r: r.update(rows_after=0, by_market={"n": {}}))
    with pytest.raises(D.SnapshotRefused, match="ROW_COUNT_MISMATCH"):
        D.load_snapshot(*pair)


def test_argument_errors_do_not_echo_private_values(capsys):
    with pytest.raises(SystemExit) as exc:
        D.main(["--private-secret-value"])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert json.loads(output.out) == {"status": "REFUSED", "reason": "INVALID_ARGUMENTS"}
    assert output.err == "" and "private" not in output.out
