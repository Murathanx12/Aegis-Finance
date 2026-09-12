"""ONE FILE A MONTH FOR THE SPEND LEDGER, SPLIT BY EACH ROW'S OWN `ts`.

`backend/data/optimus/llm_calls.jsonl` reached 62.25 MB over 92,737 rows and
every LLM call appends to it. GitHub warns at 50 MB and REFUSES a blob at 100,
and it had already warned on a push. Same shape as the evidence memory E6
rotated the day before, same answer:

* **compaction is REFUSED** -- nothing summarised, deduped or dropped;
* a row goes to the month its OWN `ts` names, never the file's mtime;
* readers concatenate the legacy monolith (while it is there) then every month
  in FILENAME order, so no consumer knows the split happened;
* the live month is gitignored and a closed month is sealed once -- and the
  guard that catches a forgotten one now covers BOTH families.

The one thing this family needed and the evidence memory did not: the ledger
already carries TORN lines. 24 worker threads in LLM-SWARM-1 split rows
mid-write, and a torn line has no `ts` because it is half a row. It is neither
filed under a guessed month nor deleted: `--quarantine-unstamped` copies it
verbatim with its line number, and the receipt closes as
`rows_in == rows_out + rows_quarantined`.
"""

from __future__ import annotations

import fnmatch
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.services import llm_telemetry as TEL
from scripts import llm_calls_rotate as ROT

REPO = Path(__file__).resolve().parents[2]


def _row(month: str, i: int, **kw) -> dict:
    return {"call_id": f"c{month}-{i}", "ts": f"{month}-05T12:00:0{i % 10}+00:00",
            "row_type": "call", "cost_usd": 0.01, "model": "deepseek-chat",
            "provider": "deepseek", "purpose": "test", **kw}


def _monolith(d: Path, rows: list[dict]) -> Path:
    p = d / "llm_calls.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8",
                 newline="\n")
    return p


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    return tmp_path


# ------------------------------------------------------ the month of a row

@pytest.mark.parametrize("ts,expected", [
    ("2026-08-12T09:47:53.835309+00:00", "2026-08"),
    ("2026-01-01T00:00:00+00:00", "2026-01"),
    ("2025-12-31T23:59:59+00:00", "2025-12"),
])
def test_a_row_is_filed_by_its_own_stamp(ts: str, expected: str):
    month, source = TEL.month_of({"ts": ts})
    assert month == expected and source == "row_stamp"


@pytest.mark.parametrize("ts", [None, "", "not-a-date", "2026-13-01T00:00:00+00:00"])
def test_an_unreadable_stamp_is_marked_never_silently_misfiled(ts):
    month, source = TEL.month_of({"ts": ts})
    assert month == datetime.now(timezone.utc).strftime("%Y-%m")
    assert source == "wall_clock_at_write"


def test_the_writer_marks_a_wall_clock_row_in_the_row_it_writes(ledger: Path):
    base = ledger / "llm_calls.jsonl"
    call = TEL.build_call(provider="deepseek", model="deepseek-chat", purpose="p",
                          prompt="x", context={"a": 1}, tokens_in=1, tokens_out=1)
    call.ts = "not-a-date"
    TEL.append([call], path=base)
    files = TEL.ledger_files(base)
    assert len(files) == 1
    row = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert (row.get("meta") or {}).get("month_source") == "wall_clock_at_write"


# --------------------------------------------------- the writer and the reader

def test_the_writer_splits_a_batch_that_straddles_a_month(ledger: Path):
    base = ledger / "llm_calls.jsonl"
    calls = []
    for month in ("2026-08", "2026-09"):
        c = TEL.build_call(provider="deepseek", model="deepseek-chat", purpose="p",
                           prompt=month, context={"m": month}, tokens_in=1, tokens_out=1)
        c.ts = f"{month}-01T00:00:00+00:00"
        calls.append(c)
    TEL.append(calls, path=base)
    names = sorted(q.name for q in TEL.ledger_files(base))
    assert names == ["llm_calls_2026-08.jsonl", "llm_calls_2026-09.jsonl"]
    assert not base.exists(), "the base path must not be written to any more"


def test_the_month_files_are_LF_whatever_the_OS(ledger: Path):
    """The 62 MB monolith was written in text mode on Windows and carries CRLF
    -- one extra byte a line, written here and read on Linux CI. A ledger whose
    bytes depend on the OS that appended them cannot be hashed across
    machines."""
    base = ledger / "llm_calls.jsonl"
    c = TEL.build_call(provider="deepseek", model="deepseek-chat", purpose="p",
                       prompt="x", context={}, tokens_in=1, tokens_out=1)
    c.ts = "2026-08-01T00:00:00+00:00"
    TEL.append([c], path=base)
    assert b"\r\n" not in TEL.ledger_files(base)[0].read_bytes()


def test_the_reader_concatenates_the_monolith_then_the_months_in_name_order(ledger: Path):
    base = _monolith(ledger, [_row("2026-06", 1), _row("2026-06", 2)])
    (ledger / "llm_calls_2026-09.jsonl").write_text(
        json.dumps(_row("2026-09", 1)) + "\n", encoding="utf-8", newline="\n")
    (ledger / "llm_calls_2026-07.jsonl").write_text(
        json.dumps(_row("2026-07", 1)) + "\n", encoding="utf-8", newline="\n")
    assert [q.name for q in TEL.ledger_files(base)] == [
        "llm_calls.jsonl", "llm_calls_2026-07.jsonl", "llm_calls_2026-09.jsonl"]
    ids = [r["call_id"] for r in TEL.read_calls(base)]
    assert ids == ["c2026-06-1", "c2026-06-2", "c2026-07-1", "c2026-09-1"]


def test_the_reader_ignores_a_quarantine_sidecar_and_a_partial_write(ledger: Path):
    """A file that is not a month file must not be read as one: a `.tmp` is a
    half-written file and a quarantine sidecar holds copies, so either would
    double-count spend."""
    base = _monolith(ledger, [_row("2026-06", 1)])
    for name in ("llm_calls.jsonl.quarantine.jsonl", "llm_calls_2026-07.jsonl.tmp",
                 "llm_calls_unstamped.jsonl", "llm_calls_2026-13.jsonl"):
        (ledger / name).write_text(json.dumps(_row("2026-06", 9)) + "\n", encoding="utf-8")
    assert [q.name for q in TEL.ledger_files(base)] == ["llm_calls.jsonl"]
    assert len(TEL.read_calls(base)) == 1


def test_a_new_month_appearing_is_picked_up_without_a_stale_cache(ledger: Path):
    """The incremental parse cache is the whole reason `spend()` is cheap enough
    to consult before every vendor call. A new month file is the stream
    continuing, not a change to it."""
    base = _monolith(ledger, [_row("2026-06", 1)])
    assert len(TEL.read_calls(base)) == 1
    (ledger / "llm_calls_2026-07.jsonl").write_text(
        json.dumps(_row("2026-07", 1)) + "\n", encoding="utf-8", newline="\n")
    assert len(TEL.read_calls(base)) == 2
    with (ledger / "llm_calls_2026-07.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(_row("2026-07", 2)) + "\n")
    assert len(TEL.read_calls(base)) == 3


def test_the_monolith_disappearing_forces_a_full_reparse_not_a_stale_total(ledger: Path):
    """The day the migration deletes the monolith, a cache that kept its rows
    would report spend for rows no longer on disk."""
    base = _monolith(ledger, [_row("2026-06", 1), _row("2026-06", 2)])
    (ledger / "llm_calls_2026-07.jsonl").write_text(
        json.dumps(_row("2026-07", 1)) + "\n", encoding="utf-8", newline="\n")
    assert len(TEL.read_calls(base)) == 3
    base.unlink()
    assert [r["call_id"] for r in TEL.read_calls(base)] == ["c2026-07-1"]


def test_an_amendment_in_a_later_month_still_folds_onto_its_base_row(ledger: Path):
    """A call made on the 31st and amended on the 1st lands in two files. If the
    fold did not cross them the outputs that call claimed would be lost."""
    base = ledger / "llm_calls.jsonl"
    (ledger / "llm_calls_2026-08.jsonl").write_text(
        json.dumps(_row("2026-08", 1)) + "\n", encoding="utf-8", newline="\n")
    (ledger / "llm_calls_2026-09.jsonl").write_text(json.dumps({
        "call_id": "c2026-08-1", "row_type": "amendment", "ts": "2026-09-01T00:00:00+00:00",
        "prediction_ids": ["p1"], "meta": {}}) + "\n", encoding="utf-8", newline="\n")
    rows = TEL.read_calls(base)
    assert len(rows) == 1 and rows[0]["prediction_ids"] == ["p1"]


def test_spend_is_measured_not_unknown_once_the_monolith_is_gone(ledger: Path):
    """`spend()` returns {} for "no ledger was opened at all", and
    `research_budget.check()` reads {} as UNKNOWN and REFUSES. Asking whether
    the BASE path exists would have stopped every campaign on a file rename."""
    base = ledger / "llm_calls.jsonl"
    assert TEL.spend(path=base) == {}
    (ledger / "llm_calls_2026-08.jsonl").write_text(
        json.dumps(_row("2026-08", 1)) + "\n", encoding="utf-8", newline="\n")
    s = TEL.spend(path=base)
    assert s and s["n_calls"] == 1


def test_integrity_scans_every_file_and_names_which_one(ledger: Path):
    """A line number stopped identifying a line the day the ledger became
    several files."""
    base = ledger / "llm_calls.jsonl"
    (ledger / "llm_calls_2026-08.jsonl").write_text(
        json.dumps(_row("2026-08", 1)) + "\n", encoding="utf-8", newline="\n")
    with (ledger / "llm_calls_2026-09.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(_row("2026-09", 1)) + "\n")
        fh.write('{"call_id": "torn"\n')
    scan = TEL.scan_integrity(base)
    assert scan["n_lines"] == 3 and scan["n_unreadable"] == 1
    assert scan["unreadable"][0]["file"].endswith("llm_calls_2026-09.jsonl")
    assert len(scan["files"]) == 2
    q = TEL.quarantine_unreadable(base)
    assert q["n_written"] == 1
    written = json.loads(Path(q["quarantine_path"]).read_text(encoding="utf-8").strip())
    assert written["source"].endswith("llm_calls_2026-09.jsonl")


# ------------------------------------------------------------ the migration

def test_every_row_reaches_the_month_its_own_stamp_names(ledger: Path):
    _monolith(ledger, [_row("2026-07", 1), _row("2026-08", 1), _row("2026-07", 2)])
    rec = ROT.rotate(ledger, receipt_dir=ledger)
    assert rec["status"] == "OK"
    assert rec["rows_in"] == 3 and rec["rows_out"] == 3
    assert rec["rows_in_equals_rows_out"] is True
    assert sorted(rec["months"]) == ["2026-07", "2026-08"]
    assert rec["months"]["2026-07"]["rows"] == 2
    assert "REFUSED" in rec["compaction"]


def test_an_unstamped_row_is_a_refusal_that_writes_nothing(ledger: Path):
    p = _monolith(ledger, [_row("2026-07", 1)])
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write('{"call_id": "no_ts", "row_type": "call"}\n')
    with pytest.raises(ROT.RotationRefused) as exc:
        ROT.rotate(ledger, receipt_dir=ledger)
    assert "--quarantine-unstamped" in str(exc.value)
    assert not (ledger / "llm_calls_2026-07.jsonl").exists()


def test_a_torn_line_is_quarantined_verbatim_never_guessed_at(ledger: Path):
    """The real ledger carries four of these in 92,737 rows. A torn line is a
    FRAGMENT: no month owns it and there is no spend in it to recover."""
    p = _monolith(ledger, [_row("2026-07", 1), _row("2026-08", 1)])
    with p.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write('"1.0.0"}\n')
    rec = ROT.rotate(ledger, receipt_dir=ledger, quarantine_unstamped=True)
    assert rec["rows_in"] == 3 and rec["rows_out"] == 2
    assert rec["rows_quarantined"] == 1
    assert rec["rows_in_equals_rows_out"] is True        # in == out + quarantined
    body = (ledger / ROT.UNSTAMPED).read_text(encoding="utf-8").strip()
    assert json.loads(body)["raw"] == '"1.0.0"}'
    assert json.loads(body)["line_no"] == 3


def test_the_reader_returns_every_row_after_the_split(ledger: Path):
    rows = [_row("2026-07", 1), _row("2026-08", 1), _row("2026-08", 2)]
    base = _monolith(ledger, rows)
    before = [r["call_id"] for r in TEL.read_calls(base)]
    ROT.rotate(ledger, receipt_dir=ledger, delete_monolith=True)
    assert not base.exists()
    assert [r["call_id"] for r in TEL.read_calls(base)] == before


def test_a_second_run_rewrites_nothing(ledger: Path):
    _monolith(ledger, [_row("2026-07", 1)])
    ROT.rotate(ledger, receipt_dir=ledger)
    again = ROT.rotate(ledger, receipt_dir=ledger)
    assert again["months"]["2026-07"]["action"] == "identical"
    assert again["receipt_action"].startswith("kept")


def test_rows_appended_since_the_split_are_not_overwritten(ledger: Path):
    _monolith(ledger, [_row("2026-07", 1)])
    ROT.rotate(ledger, receipt_dir=ledger)
    with (ledger / "llm_calls_2026-07.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(_row("2026-07", 2)) + "\n")
    again = ROT.rotate(ledger, receipt_dir=ledger)
    assert again["months"]["2026-07"]["action"] == "already_contains_these_rows"
    assert again["months"]["2026-07"]["rows_appended_since"] == 1


def test_a_disagreeing_month_file_is_a_refusal_not_an_overwrite(ledger: Path):
    """Two disagreeing copies of one month is the one outcome worse than a
    62 MB file."""
    _monolith(ledger, [_row("2026-07", 1)])
    (ledger / "llm_calls_2026-07.jsonl").write_text(
        json.dumps(_row("2026-07", 99)) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(ROT.RotationRefused):
        ROT.rotate(ledger, receipt_dir=ledger)


def test_a_missing_monolith_reports_already_rotated(ledger: Path):
    (ledger / "llm_calls_2026-07.jsonl").write_text(
        json.dumps(_row("2026-07", 1)) + "\n", encoding="utf-8", newline="\n")
    rec = ROT.rotate(ledger, receipt_dir=ledger)
    assert rec["status"] == "already_rotated"


def test_the_receipt_carries_a_sha256_per_output_file(ledger: Path):
    _monolith(ledger, [_row("2026-07", 1), _row("2026-08", 1)])
    rec = ROT.rotate(ledger, receipt_dir=ledger)
    for month, r in rec["months"].items():
        assert re.fullmatch(r"[0-9a-f]{64}", r["sha256"]), month
    assert re.fullmatch(r"[0-9a-f]{64}", rec["monolith"]["sha256"])


# ------------------------------------------------------------------- gitignore

@pytest.mark.parametrize("directory,prefix", [
    ("backend/data/optimus/learner", "evidence_memory"),
    ("backend/data/optimus", "llm_calls"),
])
def test_the_live_month_is_gitignored_for_both_ledger_families(directory: str, prefix: str):
    """Read `.gitignore`, not `git check-ignore`: the rule has to be visible to
    the person who opens the file, and a sealed month is added with `git add -f`
    once the month closes."""
    name = f"{prefix}_{datetime.now(timezone.utc):%Y-%m}.jsonl"
    rel = f"{directory}/{name}"
    lines = [ln.strip() for ln in (REPO / ".gitignore").read_text(
        encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat)
               for pat in lines), (
        f"{rel} is not ignored; the live month grows with every call and the "
        f"100 MB blob limit is the reason this lane exists")


# ------------------------------------------- a sealed month cannot be forgotten

def test_a_closed_month_of_the_llm_ledger_must_be_tracked():
    """The live month is ignored on purpose; a CLOSED month is sealed once, by
    hand, on the 1st -- and "by hand, on the 1st" is the step that does not get
    done. The failure is silent: the ignore rule keeps working, the reader keeps
    reading the local file, and the month is absent for everyone else and gone
    the day the laptop is reimaged."""
    rec = ROT.untracked_closed_months()
    if not rec["checked"]:
        pytest.skip(f"cannot determine: {rec['reason']}")
    assert not rec["months"], (
        "a CLOSED month of the LLM spend ledger is on disk and untracked:\n  "
        + "\n  ".join(f"{m['file']} ({m['rows']} rows, month {m['month']}) "
                      f"-> run: {m['command']}" for m in rec["months"]))


def test_the_guard_finds_a_forgotten_llm_month_and_ignores_the_live_one(tmp_path: Path,
                                                                       monkeypatch):
    """The gate above passes today because nothing is forgotten yet, which is
    exactly when a gate is worth nothing."""
    live = f"{datetime.now(timezone.utc):%Y-%m}"
    for name in (f"llm_calls_{live}.jsonl", "llm_calls_2026-07.jsonl",
                 "llm_calls_2026-08.jsonl", "evidence_memory_2026-08.jsonl"):
        (tmp_path / name).write_text('{"ts": "2026-07-05T00:00:00+00:00"}\n',
                                     encoding="utf-8")

    class _Done:
        stdout = "backend/data/optimus/llm_calls_2026-07.jsonl\n"

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Done())
    rec = ROT.untracked_closed_months(tmp_path)
    assert rec["checked"]
    assert [m["month"] for m in rec["months"]] == ["2026-08"]
    assert rec["months"][0]["command"].startswith("git add -f ")


def test_one_guard_serves_both_families(tmp_path: Path, monkeypatch):
    """A second copy of this check would be a second place for the rule to
    rot. The prefix is the only difference between the two families."""
    from scripts import evidence_memory_rotate as EMR

    for name in ("llm_calls_2026-07.jsonl", "evidence_memory_2026-07.jsonl"):
        (tmp_path / name).write_text('{"ts": "2026-07-05T00:00:00+00:00"}\n',
                                     encoding="utf-8")

    class _Nothing:
        stdout = ""

    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Nothing())
    assert [m["file"].rsplit("/", 1)[-1]
            for m in EMR.untracked_closed_months(tmp_path, prefix="llm_calls")["months"]
            ] == ["llm_calls_2026-07.jsonl"]
    assert [m["file"].rsplit("/", 1)[-1]
            for m in EMR.untracked_closed_months(tmp_path)["months"]
            ] == ["evidence_memory_2026-07.jsonl"]


def test_the_guard_refuses_rather_than_reporting_clean_when_git_is_unavailable(
        tmp_path: Path, monkeypatch):
    """A guard DERIVES its inputs or REFUSES. "git is not here" must not read as
    "every month is sealed"."""
    (tmp_path / "llm_calls_2026-07.jsonl").write_text("{}\n", encoding="utf-8")
    import subprocess

    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    rec = ROT.untracked_closed_months(tmp_path)
    assert rec["checked"] is False and rec["months"] == []
    assert "cannot tell a sealed month from a forgotten one" in rec["reason"]
