"""E6 -- the ledger splits by month, and every row survives the split.

THE DEADLINE THIS ANSWERS. `evidence_memory.jsonl` was 65.16 MB over 102,029
rows on 2026-09-11 and grows every night the factory runs; GitHub rejects a blob
at 100 MB. The alternative to splitting was compacting, and compaction is
refused -- the store is append-only so that "what did we believe before we
changed the bar" stays answerable.

What is actually at risk in a split is not the file size. It is that a row goes
missing, or is filed under a month it was not observed in, and the memory then
reports a different state without anything failing. So the tests below are about
the ROWS, not the files: multiset preserved, order preserved, the reader
indifferent to the split, and a row with no stamp refused rather than guessed.
"""
from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from learner import evidence_memory as EM
from scripts import evidence_memory_rotate as ROT

REPO = Path(__file__).resolve().parents[2]


def _row(month: str, i: int, day: str = "05") -> dict:
    return {"utc": f"{month}-{day}T0{i % 10}:00:00+00:00", "version": EM.VERSION,
            "family_id": f"fam_{i % 3}", "cell": f"cell_{i}", "n_months": 60 + i}


def _monolith(d: Path, rows: list[dict], *, crlf: bool = True) -> Path:
    p = d / "evidence_memory.jsonl"
    sep = "\r\n" if crlf else "\n"
    p.write_bytes(sep.join(json.dumps(r) for r in rows).encode("utf-8") + sep.encode())
    return p


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(EM, "STORE_DIR", tmp_path)
    monkeypatch.setattr(EM, "STORE", tmp_path / "evidence_memory.jsonl")
    monkeypatch.setattr(EM, "SUPERSESSIONS", tmp_path / "supersessions.jsonl")
    monkeypatch.setattr(EM, "STATE_SNAPSHOT", tmp_path / "state.json")
    return tmp_path


# ------------------------------------------------------------ the split itself

def test_every_row_survives_the_split_as_a_multiset(store):
    rows = ([_row("2026-07", i) for i in range(40)]
            + [_row("2026-08", i) for i in range(30)]
            + [_row("2026-09", i) for i in range(32)])
    _monolith(store, rows)
    rec = ROT.rotate(store)
    assert rec["rows_in"] == 102
    assert rec["rows_out"] == 102
    assert rec["rows_in_equals_rows_out"] is True
    written = []
    for m in ("2026-07", "2026-08", "2026-09"):
        p = store / f"evidence_memory_{m}.jsonl"
        written += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    # A multiset, compared as sorted JSON so two identical rows both have to be
    # there -- a set comparison would pass while silently deduping.
    assert sorted(map(json.dumps, written)) == sorted(map(json.dumps, rows))


def test_a_row_goes_to_the_month_its_own_stamp_names_not_the_file_date(store):
    _monolith(store, [_row("2026-07", 1), _row("2026-08", 2)])
    ROT.rotate(store)
    july = (store / "evidence_memory_2026-07.jsonl").read_text(encoding="utf-8")
    aug = (store / "evidence_memory_2026-08.jsonl").read_text(encoding="utf-8")
    assert '"utc": "2026-07' in july and '"utc": "2026-08' not in july
    assert '"utc": "2026-08' in aug and '"utc": "2026-07' not in aug


def test_the_reader_returns_the_same_rows_in_the_same_order_after_the_split(store):
    rows = ([_row("2026-07", i) for i in range(12)]
            + [_row("2026-08", i) for i in range(9)]
            + [_row("2026-09", i) for i in range(7)])
    _monolith(store, rows)
    before = EM.read_all()
    assert len(before) == 28
    ROT.rotate(store, delete_monolith=True)
    after = EM.read_all()
    assert after == before, "the split changed what the memory reads"
    assert not (store / "evidence_memory.jsonl").exists()


def test_the_state_the_memory_derives_is_unchanged_by_the_split(store):
    rows = [_row("2026-07", i) for i in range(6)] + [_row("2026-08", i) for i in range(6)]
    _monolith(store, rows)
    before = EM.snapshot()["by_cell"]
    ROT.rotate(store, delete_monolith=True)
    assert EM.snapshot()["by_cell"] == before


def test_the_rows_are_kept_verbatim_rather_than_re_serialised(store):
    """A round-trip through `json.dumps` reorders keys and rewrites floats. An
    append-only row IS the bytes that were written."""
    line = '{"utc": "2026-08-01T00:00:00+00:00", "z": 1, "a": 0.10000000000000001}'
    (store / "evidence_memory.jsonl").write_text(line + "\n", encoding="utf-8")
    ROT.rotate(store)
    assert (store / "evidence_memory_2026-08.jsonl").read_text(
        encoding="utf-8").strip() == line


# ------------------------------------------------------------------- refusals

def test_a_row_without_a_parseable_stamp_is_refused_and_nothing_is_written(store):
    rows = [_row("2026-08", 1), {"family_id": "no_stamp", "cell": "c"},
            {"utc": "not a date", "family_id": "bad"}]
    _monolith(store, rows)
    with pytest.raises(ROT.RotationRefused) as exc:
        ROT.rotate(store)
    assert "2 of 3" in str(exc.value)
    assert "no_stamp" in str(exc.value)          # the first three are printed
    assert not list(store.glob("evidence_memory_2*.jsonl"))
    assert (store / "evidence_memory.jsonl").exists()


def test_a_month_file_that_disagrees_is_a_refusal_not_an_overwrite(store):
    _monolith(store, [_row("2026-08", 1)])
    (store / "evidence_memory_2026-08.jsonl").write_text(
        json.dumps(_row("2026-08", 99)) + "\n", encoding="utf-8")
    with pytest.raises(ROT.RotationRefused, match="already exists"):
        ROT.rotate(store)


def test_an_impossible_month_is_not_a_month(store):
    assert ROT.month_of_line(json.dumps({"utc": "2026-13-01T00:00:00Z"})) is None
    assert ROT.month_of_line("not json") is None


# ---------------------------------------------------------------- idempotency

def test_running_it_twice_writes_nothing_the_second_time(store):
    _monolith(store, [_row("2026-08", i) for i in range(5)])
    first = ROT.rotate(store)
    target = store / "evidence_memory_2026-08.jsonl"
    stamp = target.read_bytes()
    second = ROT.rotate(store)
    assert first["months"]["2026-08"]["action"] == "written"
    assert second["months"]["2026-08"]["action"] == "identical"
    assert target.read_bytes() == stamp


def test_rows_appended_since_the_split_are_recognised_not_clobbered(store):
    _monolith(store, [_row("2026-08", i) for i in range(4)])
    ROT.rotate(store)
    EM.observe("later", "cell", n_months=12)          # lands in the LIVE month
    (store / "evidence_memory_2026-08.jsonl").open("a", encoding="utf-8",
                                                   newline="\n").write(
        json.dumps(_row("2026-08", 77)) + "\n")
    rec = ROT.rotate(store)
    assert rec["months"]["2026-08"]["action"] == "already_contains_these_rows"
    assert rec["months"]["2026-08"]["rows_appended_since"] == 1


def test_with_no_monolith_it_reports_already_rotated(store):
    (store / "evidence_memory_2026-08.jsonl").write_text(
        json.dumps(_row("2026-08", 1)) + "\n", encoding="utf-8")
    rec = ROT.rotate(store)
    assert rec["status"] == "already_rotated"


# ------------------------------------------------------------------ the writer

def test_a_new_observation_lands_in_the_current_months_file(store):
    EM.observe("fam", "cell", n_months=24)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    assert (store / f"evidence_memory_{month}.jsonl").exists()
    assert not (store / "evidence_memory.jsonl").exists()
    assert EM.read_all()[0]["family_id"] == "fam"


def test_a_row_with_an_unreadable_stamp_says_so_in_the_row_it_writes(store):
    p = EM.append({"family_id": "x", "utc": "whenever"})
    assert p.name == f"evidence_memory_{EM._now()[:7]}.jsonl"
    row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert row["month_source"] == "wall_clock_at_write"


def test_the_writer_follows_a_redirected_store_dir(store, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    EM.append({"utc": "2026-08-01T00:00:00+00:00", "family_id": "x"},
              directory=other)
    assert (other / "evidence_memory_2026-08.jsonl").exists()


def test_rows_are_written_lf_on_every_platform(store):
    EM.observe("fam", "cell", n_months=24)
    data = EM.active_store().read_bytes()
    assert b"\r\n" not in data, (
        "CRLF in the ledger: the same rows hash differently on Windows and on "
        "Linux CI, which is how two days of CI red were bought in September")


# ------------------------------------------------------- the store's file list

def test_the_supersessions_log_is_not_read_as_observations(store):
    """`evidence_memory*.jsonl` also matches `evidence_memory_supersessions`.
    Folding it into the stream would let every retraction vote as evidence."""
    (store / "evidence_memory_supersessions.jsonl").write_text(
        json.dumps({"utc": "2026-08-01T00:00:00+00:00", "family_id": "f",
                    "before_utc": "2026-08-01T00:00:00+00:00", "why": "w"}) + "\n",
        encoding="utf-8")
    (store / "evidence_memory_2026-08.jsonl").write_text(
        json.dumps(_row("2026-08", 1)) + "\n", encoding="utf-8")
    assert [p.name for p in EM.store_files()] == ["evidence_memory_2026-08.jsonl"]
    assert len(EM.read_all()) == 1


def test_the_legacy_monolith_is_still_read_when_it_is_there(store):
    _monolith(store, [_row("2026-07", 1)])
    (store / "evidence_memory_2026-08.jsonl").write_text(
        json.dumps(_row("2026-08", 2)) + "\n", encoding="utf-8")
    names = [p.name for p in EM.store_files()]
    assert names == ["evidence_memory.jsonl", "evidence_memory_2026-08.jsonl"]
    assert len(EM.read_all()) == 2


# ----------------------------------------------------------------- the receipt

def test_the_receipt_records_rows_in_rows_out_and_a_hash_per_file(store):
    _monolith(store, [_row("2026-07", i) for i in range(3)]
              + [_row("2026-08", i) for i in range(4)])
    rec = ROT.rotate(store)
    assert rec["rows_in"] == 7
    assert {m: r["rows"] for m, r in rec["months"].items()} == {"2026-07": 3,
                                                               "2026-08": 4}
    assert len(rec["monolith"]["sha256"]) == 64
    for r in rec["months"].values():
        assert len(r["sha256"]) == 64
    written = json.loads(Path(rec["receipt"]).read_text(encoding="utf-8"))
    assert written["rows_in"] == 7
    assert written["dated_by"].startswith("each row's own")
    assert Path(rec["receipt"]).name.startswith("rotation_receipt_")


def test_the_receipt_is_not_rewritten_on_a_no_op_rerun(store):
    _monolith(store, [_row("2026-08", 1)])
    first = ROT.rotate(store)
    stamp = Path(first["receipt"]).read_bytes()
    second = ROT.rotate(store)
    assert second["receipt_action"].startswith("kept")
    assert Path(second["receipt"]).read_bytes() == stamp


# ------------------------------------------------------------------- gitignore

def test_the_live_month_is_gitignored():
    """Read `.gitignore`, not `git check-ignore`: the rule has to be visible to
    the person who opens the file, and a sealed month is added with `git add -f`
    once the month closes."""
    name = f"evidence_memory_{datetime.now(timezone.utc):%Y-%m}.jsonl"
    rel = f"backend/data/optimus/learner/{name}"
    lines = [ln.strip() for ln in (REPO / ".gitignore").read_text(
        encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")]
    assert any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
               for pat in lines), (
        f"{rel} is not ignored; the live month grows nightly and the 100 MB "
        f"blob limit is the reason this lane exists")
