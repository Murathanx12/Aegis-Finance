"""C10: the data catalog and closed-ledger archival.

Every fixture date is derived from the run clock (protocol item 5): a "closed
month" is last month relative to `now`, never a literal.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from backend.services import data_catalog as DC
from backend.services import ledger_archive as LA

NOW = datetime.now(timezone.utc)
LIVE = f"{NOW:%Y-%m}"
CLOSED = f"{(NOW.replace(day=1) - timedelta(days=1)):%Y-%m}"


def _cat(root: Path, *, manifest_text: str = "", code: dict | None = None,
         cache: Path | None = None) -> dict:
    return DC.build_catalog(
        roots=[DC.Root("t", root, "<t>")], cache_path=cache,
        manifest_text=manifest_text,
        code_index=DC.TokenIndex.from_texts(code or {}),
        doc_index=DC.TokenIndex.from_texts({}), use_git=False, workers=1)


def _by_path(cat: dict) -> dict:
    return {r["path"]: r for r in cat["rows"]}


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "panel").mkdir(parents=True)
    t = pa.table({"date": pa.array([datetime(2021, 1, 4), datetime(2023, 6, 30)],
                                   type=pa.timestamp("us")),
                  "ticker": ["AAA", "BBB"], "ret": [0.01, -0.02]})
    pq.write_table(t, root / "panel" / "bars.parquet")
    rows = [{"ts": f"{CLOSED}-0{i}T10:00:00+00:00", "v": i} for i in range(1, 4)]
    (root / "ledger_x.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                         encoding="utf-8", newline="\n")
    return root


# ------------------------------------------------------------------ catalog

def test_a_parquet_row_carries_rows_schema_hash_and_a_date_range_from_the_data(tree: Path):
    r = _by_path(_cat(tree))["<t>/panel/bars.parquet"]
    assert r["kind"] == "parquet" and r["rows"] == 2
    assert r["rows_method"] == "parquet footer"
    assert r["date_range"]["min"] == "2021-01-04" and r["date_range"]["max"] == "2023-06-30"
    assert r["date_range"]["method"] == "parquet column statistics"
    assert len(r["schema_hash"]) == 16
    assert [c[0] for c in r["schema"]] == ["date", "ticker", "ret"]
    assert r["content"]["mode"] == "full"
    assert r["content"]["sha256"] == hashlib.sha256(
        (tree / "panel" / "bars.parquet").read_bytes()).hexdigest()


def test_a_jsonl_row_counts_lines_and_dates_from_its_own_rows(tree: Path):
    r = _by_path(_cat(tree))["<t>/ledger_x.jsonl"]
    assert r["rows"] == 3 and r["rows_method"] == "line count"
    assert r["date_range"]["min"] == f"{CLOSED}-01" and r["date_range"]["column"] == "ts"


def test_the_same_bytes_at_two_paths_are_listed_as_a_duplicate(tree: Path):
    (tree / "copy").mkdir()
    (tree / "copy" / "bars_again.parquet").write_bytes((tree / "panel" / "bars.parquet").read_bytes())
    cat = _cat(tree)
    assert cat["summary"]["duplicate_groups"] == 1
    g = cat["duplicates"][0]
    assert g["certainty"] == "exact" and g["n"] == 2
    assert g["paths"] == ["<t>/copy/bars_again.parquet", "<t>/panel/bars.parquet"]


def test_a_file_named_nowhere_is_unknown_provenance_and_a_manifest_row_fixes_it(tree: Path):
    cat = _cat(tree)
    assert _by_path(cat)["<t>/ledger_x.jsonl"]["provenance"]["source"] == DC.UNKNOWN
    assert cat["summary"]["unknown_provenance"] >= 2
    md = ("| Path | Size | Produced by | What |\n|---|---:|---|---|\n"
          "| `<t>/panel/*.parquet` | 1 KB | `scripts/pull_bars.py` | bars |\n")
    r = _by_path(_cat(tree, manifest_text=md))["<t>/panel/bars.parquet"]
    assert r["provenance"]["source"] == "DATA_MANIFEST.md table"
    assert r["provenance"]["produced_by"] == "scripts/pull_bars.py"


def test_an_orphan_has_no_consumer_and_a_named_file_has_one(tree: Path):
    code = {"scripts/use_bars.py": 'P = ROOT / "panel" / "bars.parquet"\n'}
    rows = _by_path(_cat(tree, code=code))
    assert rows["<t>/panel/bars.parquet"]["consumers"]["n"] == 1
    assert rows["<t>/panel/bars.parquet"]["consumers"]["match"] == "basename"
    assert rows["<t>/ledger_x.jsonl"]["consumers"]["n"] == 0


def test_a_month_family_is_found_by_its_prefix():
    ix = DC.TokenIndex.from_texts({"backend/services/llm_telemetry.py":
                                   'LLM_CALLS = LEDGER_DIR / "llm_calls.jsonl"\n'})
    c = DC.consumers_for(f"backend/data/optimus/llm_calls_{CLOSED}.jsonl", ix)
    assert c["match"] == "family" and c["n"] == 1


def test_touching_a_file_changes_nothing_in_its_row(tree: Path, tmp_path: Path):
    """mtime is a cache key, never a date: a touched file is re-inspected and
    yields the identical row, and no row carries an mtime."""
    cache = tmp_path / "cache.json"
    before = _cat(tree, cache=cache)
    old = NOW.timestamp() - 400 * 86400
    for p in tree.rglob("*"):
        if p.is_file():
            os.utime(p, (old, old))
    after = _cat(tree, cache=cache)
    assert after["cache"]["inspected"] == before["cache"]["inspected"]   # all re-inspected
    assert after["rows"] == before["rows"]
    assert "mtime" not in json.dumps(after["rows"])


def test_the_cache_skips_unchanged_files(tree: Path, tmp_path: Path):
    cache = tmp_path / "cache.json"
    first = _cat(tree, cache=cache)
    second = _cat(tree, cache=cache)
    assert first["cache"]["inspected"] >= 2 and second["cache"]["inspected"] == 0
    assert second["rows"] == first["rows"]


def test_a_big_file_is_hashed_head_tail_and_labelled(tmp_path: Path):
    p = tmp_path / "big.jsonl"
    p.write_bytes(b'{"ts": "2020-01-01"}\n' * 200_000)
    fe = DC.walk([DC.Root("t", tmp_path, "<t>")])[0]
    res = DC.inspect_file(fe, full_max=1024)
    assert res["content"]["mode"] == "size+head1MB+tail1MB"
    assert res["rows"] is None and res["rows_method"].startswith("skipped")


def test_small_receipts_roll_up_into_one_directory_row(tmp_path: Path):
    d = tmp_path / "receipts"
    d.mkdir()
    for i in range(5):
        (d / f"r{i}.json").write_text('{"generated_at": "2026-01-01"}', encoding="utf-8")
    cat = _cat(tmp_path)
    assert [r["kind"] for r in cat["rows"]] == ["dir"]
    assert cat["rows"][0]["n_files"] == 5
    assert "listing" in cat["rows"][0]["content"]["mode"]


def test_query_answers_do_we_have_x(tree: Path):
    cat = _cat(tree)
    assert [r["path"] for r in DC.query(cat, "bars")] == ["<t>/panel/bars.parquet"]
    assert DC.query(cat, "ticker")[0]["path"] == "<t>/panel/bars.parquet"   # by column
    assert DC.query(cat, "no_such_dataset") == []


def test_the_latest_receipt_is_chosen_by_its_run_id_not_its_mtime(tmp_path: Path):
    a = tmp_path / "catalog_20260101T000000Z.json"
    b = tmp_path / "catalog_20260201T000000Z.json"
    b.write_text("{}"), a.write_text("{}")          # `a` written last
    assert DC.latest_receipt(tmp_path) == b


# ------------------------------------------------------------- ledger archive

def _ledger(tmp_path: Path, month: str, n: int = 5, torn: bool = False) -> Path:
    p = tmp_path / f"llm_calls_{month}.jsonl"
    body = "".join(json.dumps({"call_id": f"c{i}", "ts": f"{month}-1{i % 9}T00:00:00+00:00",
                               "cost_usd": 0.01 * i}) + "\n" for i in range(n))
    if torn:
        body += '"1.0.0"}\n'
    p.write_text(body, encoding="utf-8", newline="\n")
    return p


@pytest.fixture()
def dirs(tmp_path: Path, monkeypatch) -> dict:
    d = {"man": tmp_path / "manifests", "arc": tmp_path / "archive"}
    monkeypatch.setattr(LA, "MANIFEST_DIR", d["man"])
    monkeypatch.setattr(LA, "ARCHIVE_DIR", d["arc"])
    return d


def test_archive_round_trip_reproduces_the_jsonl_sha(tmp_path: Path, dirs: dict):
    p = _ledger(tmp_path, CLOSED, torn=True)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    m = LA.archive_month(p)
    assert m["action"] == "archived" and m["round_trip_verified"] is True
    assert m["jsonl"]["sha256"] == sha and m["jsonl"]["rows"] == 6
    assert m["jsonl"]["rows_unparseable"] == 1 and m["jsonl"]["deleted"] is False
    assert m["first_ts"].startswith(CLOSED) and m["parquet"]["rows"] == 6
    pq_path = dirs["arc"] / f"llm_calls_{CLOSED}.parquet"
    assert m["parquet"]["sha256"] == hashlib.sha256(pq_path.read_bytes()).hexdigest()
    on_disk = json.loads((dirs["man"] / f"llm_calls_{CLOSED}.json").read_text(encoding="utf-8"))
    assert on_disk["archived"] is True and on_disk["command"].startswith("python -m ")
    assert LA.restore_bytes(on_disk, archive_path=pq_path) == p.read_bytes()
    assert p.exists(), "the jsonl is never deleted by this chunk"


def test_archiving_twice_is_identical_and_a_changed_closed_month_is_refused(tmp_path: Path,
                                                                            dirs: dict):
    p = _ledger(tmp_path, CLOSED)
    LA.archive_month(p)
    assert LA.archive_month(p)["action"] == "identical"
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"call_id": "late", "ts": f"{CLOSED}-28T00:00:00+00:00"}) + "\n")
    with pytest.raises(LA.ArchiveRefused, match="changed after it was archived"):
        LA.archive_month(p)


def test_the_open_month_and_protected_ledgers_are_refused(tmp_path: Path, dirs: dict):
    with pytest.raises(LA.ArchiveRefused, match="open month"):
        LA.archive_month(_ledger(tmp_path, LIVE))
    (tmp_path / "predictions.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(LA.ArchiveRefused, match="growing tracked ledger"):
        LA.archive_month(tmp_path / "predictions.jsonl")
    assert not dirs["man"].exists()


def test_the_month_writer_refuses_an_archived_closed_month(tmp_path: Path, dirs: dict):
    """`llm_telemetry.append` files a row by its own `ts`. A row stamped into an
    archived month must not touch that file (its sha256 is committed); the
    spend is kept, in the live month, marked with where it was refused from."""
    from backend.services import llm_telemetry as TEL

    p = _ledger(tmp_path, CLOSED)
    LA.archive_month(p)
    before = p.read_bytes()
    call = TEL.build_call(provider="deepseek", model="deepseek-chat", purpose="t",
                          prompt="x", context={}, tokens_in=1, tokens_out=1)
    call.ts = f"{CLOSED}-27T00:00:00+00:00"
    TEL.append([call], path=tmp_path / "llm_calls.jsonl")
    assert p.read_bytes() == before
    live = tmp_path / f"llm_calls_{LIVE}.jsonl"
    row = json.loads(live.read_text(encoding="utf-8").strip())
    assert row["meta"]["month_source"] == f"redirected_from_archived_{CLOSED}"


def test_the_evidence_memory_writer_raises_on_an_archived_month(tmp_path: Path, dirs: dict):
    from learner import evidence_memory as EM

    p = tmp_path / f"evidence_memory_{CLOSED}.jsonl"
    p.write_text(json.dumps({"utc": f"{CLOSED}-02T00:00:00+00:00"}) + "\n",
                 encoding="utf-8", newline="\n")
    LA.archive_month(p)
    with pytest.raises(LA.ArchivedMonthRefused):
        EM.append({"utc": f"{CLOSED}-03T00:00:00+00:00"}, directory=tmp_path)
    EM.append({"utc": NOW.isoformat()}, directory=tmp_path)        # the live month still writes


def test_the_rotation_script_refuses_to_rewrite_an_archived_month(tmp_path: Path, dirs: dict):
    from scripts import llm_calls_rotate as ROT

    p = _ledger(tmp_path, CLOSED)
    LA.archive_month(p)
    p.rename(tmp_path / "llm_calls.jsonl")            # as if the month file were gone
    with pytest.raises(ROT.RotationRefused, match="archive manifest"):
        ROT.rotate(tmp_path, receipt_dir=tmp_path)


def test_the_sealed_month_guard_accepts_a_manifest_instead_of_git_add(tmp_path: Path,
                                                                    dirs: dict, monkeypatch):
    import subprocess

    from scripts import llm_calls_rotate as ROT

    p = _ledger(tmp_path, CLOSED)

    class _Nothing:
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Nothing())
    assert [m["month"] for m in ROT.untracked_closed_months(tmp_path)["months"]] == [CLOSED]
    monkeypatch.undo()
    monkeypatch.setattr(LA, "MANIFEST_DIR", dirs["man"])
    monkeypatch.setattr(LA, "ARCHIVE_DIR", dirs["arc"])
    LA.archive_month(p)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Nothing())
    rec = ROT.untracked_closed_months(tmp_path)
    assert rec["months"] == [] and [a["month"] for a in rec["archived"]] == [CLOSED]


def test_find_candidates_marks_closed_and_over_floor(tmp_path: Path, dirs: dict):
    _ledger(tmp_path, CLOSED)
    _ledger(tmp_path, LIVE)
    c = {r["month"]: r for r in LA.find_candidates(tmp_path, min_bytes=1)}
    assert c[CLOSED]["closed"] and not c[LIVE]["closed"]


def test_the_keeper_job_logs_both_steps_and_refuses_on_a_failed_step(tmp_path: Path):
    from scripts import task_keeper as K

    ok = K.run_catalog(archive=lambda: {"status": "OK", "months": []},
                       catalog=lambda: {"datasets": 1}, log_path=tmp_path / "k.jsonl")
    assert ok["action"] == "ok" and ok["job"] == "catalog"

    def boom():
        raise OSError("disk")

    bad = K.run_catalog(archive=boom, catalog=lambda: {}, log_path=tmp_path / "k.jsonl")
    assert bad["action"] == "refused" and "disk" in bad["archive"]["why"]
    assert "AegisDataCatalog" in K.CATCHUP_TASKS


def test_a_directory_named_in_prose_is_not_provenance_for_everything_under_it(tree: Path):
    md = "All panels live under `<t>/` and `<t>/ledger_x.jsonl` is named.\n"
    rules = DC.load_manifest_rules(md.replace("<t>", "backend/data/x"))
    assert DC.provenance_for("backend/data/x/panel/bars.parquet", rules=rules)["source"] == DC.UNKNOWN
    assert DC.provenance_for("backend/data/x/ledger_x.jsonl",
                             rules=rules)["source"] == "DATA_MANIFEST.md prose"


def test_a_name_only_tests_mention_falls_through_to_the_family_level():
    ix = DC.TokenIndex.from_texts({
        "backend/tests/test_x.py": f'"llm_calls_{CLOSED}.jsonl"\n',
        "backend/services/llm_telemetry.py": '"llm_calls.jsonl"\n'})
    c = DC.consumers_for(f"backend/data/optimus/llm_calls_{CLOSED}.jsonl", ix)
    assert c["match"] == "family" and c["n"] == 1
