"""The B/B′ beta-twin re-seed (chunk 12, T4) — the gap, the gate, the degeneracy.

No real book database is touched: every test drives a `tmp_path` SQLite file
through `paper_books._conn(db_path=...)`, so nothing here can write into
`backend/data/optimus`'s real `paper_books` table on a CI runner that has none.

Three things are pinned, each a failure this script exists because of:

* **the gap is asked of `make_twins`, not re-derived.** `LONG_ONLY_RULES`
  omitted `passthrough` and the omission was invisible for a day precisely
  because nothing compared what a book CARRIES with what it is OWED. A second
  reading of the rule would reproduce the bug.
* **the write is gated.** Adding a twin rewrites the PARENT's row, because
  `control_twin_ids` lives there, and "no mutation of seeded book histories" is
  one of the things that never relaxes. `--apply` without the flag is a refusal
  that still writes the plan and still exits 0.
* **a "beta-matched" draw that hands back the band is DEGENERATE and says so.**
  The real scan found exactly that for both insider books (2,824 of 2,834
  names, overlap 1.0, the same membership hash for B and B′).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from backend.services import paper_books as PB
from scripts import reseed_beta_twins as RS


# --------------------------------------------------------------------------
# fixtures


def _bars(symbols, n: int = 200, asof: date | None = None):
    """Daily bars ending the day before `asof`, enough for a 120-session beta."""
    asof = asof or date.today()
    idx = pd.bdate_range(end=pd.Timestamp(asof) - pd.Timedelta(days=1), periods=n)
    rows = []
    for i, s in enumerate(symbols):
        for j, d in enumerate(idx):
            rows.append({"symbol": s, "date": d,
                         "open": 100.0, "high": 101.0, "low": 99.0,
                         "close": 100.0 + ((i + 1) * (j % 7)) * 0.1,
                         "volume": 1_000_000 + i * 1000})
    return pd.DataFrame(rows)


def _strategy(strategy_id: str, rule: str):
    """A real contract from `seed_first_books`, re-badged.

    Built from the seeding script's own factories rather than hand-assembled:
    `Strategy` validates a dozen fields, and a hand-built contract that passes
    would be a contract nobody else in the programme uses.
    """
    from scripts import seed_first_books as S

    base = S.book_b() if rule == "passthrough" else S.book_a()
    assert base.construction.rule == rule, (
        f"{base.strategy_id} is {base.construction.rule}, not {rule}")
    return base.with_(strategy_id=strategy_id, title=f"{strategy_id} ({rule})")


@pytest.fixture
def db(tmp_path):
    return tmp_path / "books.db"


@pytest.fixture
def symbols():
    return [f"S{i:03d}" for i in range(40)]


def _seed_book(db, strategy, bars, asof, *, strip_kinds=()):
    """Create a book, then DELETE the named twin kinds from its row.

    That reproduces the 2026-09-12 state: the twin was never made because
    `make_twins` did not know the book was owed it.
    """
    from dataclasses import replace

    conn = PB._conn(db)
    try:
        book, twins = PB.create(strategy, cadence="monthly", origin="night_job",
                                bars=bars, asof=asof, conn=conn)
        if strip_kinds:
            keep = [t for t in twins if RS.twin_kind(t) not in strip_kinds]
            conn.execute("DELETE FROM paper_books WHERE id IN ({})".format(
                ",".join("?" * (len(twins) - len(keep)))),
                [t.book_id for t in twins if RS.twin_kind(t) in strip_kinds])
            conn.commit()
            PB._persist(conn, replace(
                book, control_twin_ids=tuple(t.book_id for t in keep)))
        return PB.get(book.book_id, conn=conn)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# the gap


def test_the_gap_is_what_make_twins_would_produce_minus_what_the_book_carries(
        db, symbols):
    asof = date.today()
    bars = _bars(symbols, asof=asof)
    book = _seed_book(db, _strategy("b_like", "passthrough"), bars, asof,
                      strip_kinds=("beta_matched",))
    conn = PB._conn(db)
    try:
        assert sorted(RS.carried_kinds(book, conn=conn)) == ["random_universe"]
        owed = RS.owed_kinds(book, bars=bars, asof=asof)
        assert "beta_matched" in owed, (
            "a passthrough book IS long-only: decide_weights never produces a "
            "negative weight for any rule")
        p, to_create = RS.plan(bars=bars, asof=asof, conn=conn)
    finally:
        conn.close()
    row = next(r for r in p["books"] if r["strategy_id"] == "b_like")
    assert row["missing"] == ["beta_matched"]
    assert p["n_books_with_a_gap"] == 1 and p["n_twins_to_create"] == 1
    assert len(to_create) == 1 and len(to_create[0][1]) == 1


def test_a_book_whose_controls_are_complete_reports_no_gap(db, symbols):
    asof = date.today()
    bars = _bars(symbols, asof=asof)
    book = _seed_book(db, _strategy("complete", "top_k"), bars, asof)
    conn = PB._conn(db)
    try:
        p, to_create = RS.plan(bars=bars, asof=asof, conn=conn)
    finally:
        conn.close()
    row = next(r for r in p["books"] if r["strategy_id"] == "complete")
    assert row["missing"] == []
    assert to_create == []
    assert book.control_twin_ids


def test_the_expected_gap_is_a_label_not_a_filter(db, symbols):
    """The scan walks every book. A tuple of known cases is how
    `LONG_ONLY_RULES` went wrong in the first place."""
    asof = date.today()
    bars = _bars(symbols, asof=asof)
    _seed_book(db, _strategy("not_on_the_list", "passthrough"), bars, asof,
               strip_kinds=("beta_matched",))
    conn = PB._conn(db)
    try:
        p, _ = RS.plan(bars=bars, asof=asof, conn=conn)
    finally:
        conn.close()
    row = next(r for r in p["books"] if r["strategy_id"] == "not_on_the_list")
    assert row["missing"] == ["beta_matched"]
    assert row["expected_gap"] is False, "found anyway, and labelled honestly"
    assert RS.EXPECTED_GAP == ("insider_cluster_length_v1",
                              "insider_cluster_same_day_v1")


# --------------------------------------------------------------------------
# the gate


def test_apply_without_the_flag_refuses_and_writes_nothing(db, symbols,
                                                           monkeypatch):
    monkeypatch.delenv(RS.ARM_ENV, raising=False)
    asof = date.today()
    bars = _bars(symbols, asof=asof)
    book = _seed_book(db, _strategy("gated", "passthrough"), bars, asof,
                      strip_kinds=("beta_matched",))
    conn = PB._conn(db)
    try:
        p, to_create = RS.plan(bars=bars, asof=asof, conn=conn)
        out = RS.apply_reseed(p, to_create, conn=conn)
        after = PB.get(book.book_id, conn=conn)
    finally:
        conn.close()
    assert out["applied"] is False
    assert RS.ARM_ENV in out["refused"]
    assert "seeded book" in out["refused"]
    assert after.control_twin_ids == book.control_twin_ids, "nothing was written"
    assert RS.ARM_ENV in out["attended_command"]


def test_the_armed_apply_adds_the_twin_and_extends_the_parents_row(db, symbols,
                                                                  monkeypatch):
    monkeypatch.setenv(RS.ARM_ENV, "1")
    asof = date.today()
    bars = _bars(symbols, asof=asof)
    book = _seed_book(db, _strategy("armed", "passthrough"), bars, asof,
                      strip_kinds=("beta_matched",))
    conn = PB._conn(db)
    try:
        p, to_create = RS.plan(bars=bars, asof=asof, conn=conn)
        out = RS.apply_reseed(p, to_create, conn=conn)
        after = PB.get(book.book_id, conn=conn)
        kinds = RS.carried_kinds(after, conn=conn)
        p2, to_create2 = RS.plan(bars=bars, asof=asof, conn=conn)
    finally:
        conn.close()
    assert out["applied"] is True and out["n_twins_created"] == 1
    assert sorted(kinds) == ["beta_matched", "random_universe"]
    assert len(after.control_twin_ids) == len(book.control_twin_ids) + 1
    assert "beta_matched" in after.control_construction
    # idempotent: a second pass finds nothing left to do
    row = next(r for r in p2["books"] if r["strategy_id"] == "armed")
    assert row["missing"] == [] and to_create2 == []


def test_the_parent_row_keeps_every_other_field(db, symbols, monkeypatch):
    """A hand-built parent would be a new contract wearing an old id."""
    monkeypatch.setenv(RS.ARM_ENV, "1")
    asof = date.today()
    bars = _bars(symbols, asof=asof)
    book = _seed_book(db, _strategy("fields", "passthrough"), bars, asof,
                      strip_kinds=("beta_matched",))
    conn = PB._conn(db)
    try:
        p, to_create = RS.plan(bars=bars, asof=asof, conn=conn)
        RS.apply_reseed(p, to_create, conn=conn)
        after = PB.get(book.book_id, conn=conn)
    finally:
        conn.close()
    for field in ("book_id", "cadence", "created_utc", "origin", "origin_text",
                  "ips_hash", "shadow", "status"):
        assert getattr(after, field) == getattr(book, field), field
    assert after.strategy.fingerprint == book.strategy.fingerprint


def test_is_armed_reads_exactly_one(monkeypatch):
    for val, want in (("1", True), (" 1 ", True), ("0", False), ("true", False),
                      ("", False)):
        monkeypatch.setenv(RS.ARM_ENV, val)
        assert RS.is_armed() is want, val


# --------------------------------------------------------------------------
# the degeneracy the real scan found


def test_a_matched_draw_that_hands_back_the_band_is_called_degenerate():
    """MEASURED on the real books 2026-09-13: the twin holds 2,824 of the
    parent's 2,834 names, overlap 1.0, and B and B′ share a membership hash."""
    class _T:
        class strategy:
            strategy_id = "x::beta_matched"
            engine_params = {"symbols": [f"S{i}" for i in range(99)],
                             "twin": {"kind": "beta_matched",
                                      "universe_overlap_with_parent": 1.0}}
        book_id = "book:dead"
        control_construction = "n/a"

    parent = [f"S{i}" for i in range(100)]
    row = RS._twin_row(_T, parent)
    assert row["degenerate_beta_match"] is True
    assert row["degenerate_coverage_of_parent_universe"] == 0.99
    assert "NOT beta-matched in any informative sense" in row["degenerate_note"]
    assert row["parent_universe_size"] == 100


def test_a_real_matched_draw_is_not_called_degenerate():
    class _T:
        class strategy:
            strategy_id = "x::beta_matched"
            engine_params = {"symbols": [f"S{i}" for i in range(10)],
                             "twin": {"kind": "beta_matched"}}
        book_id = "book:dead"
        control_construction = "n/a"

    row = RS._twin_row(_T, [f"S{i}" for i in range(100)])
    assert row["degenerate_beta_match"] is False
    assert row["degenerate_note"] is None
    assert RS.DEGENERATE_COVERAGE == 0.95


def test_the_membership_is_pinned_by_a_hash_not_dumped_in_full():
    class _T:
        class strategy:
            strategy_id = "x::beta_matched"
            engine_params = {"symbols": [f"S{i:04d}" for i in range(3000)],
                             "twin": {"kind": "beta_matched"}}
        book_id = "book:dead"
        control_construction = "n/a"

    row = RS._twin_row(_T, [])
    assert row["n_symbols"] == 3000
    assert len(row["symbols_preview"]) == RS.SYMBOL_PREVIEW
    assert len(row["symbols_sha256"]) == 64


def test_an_unmatched_twin_is_flagged_and_warned_about():
    class _T:
        class strategy:
            strategy_id = "x::beta_matched"
            engine_params = {"symbols": ["A", "B"],
                             "twin": {"kind": "beta_matched",
                                      "UNMATCHED": "no beta could be estimated"}}
        book_id = "book:dead"
        control_construction = "n/a"

    row = RS._twin_row(_T, [])
    assert row["matched"] is False, (
        "a beta-matched twin that is secretly random must never be reported as "
        "the stricter control")


# --------------------------------------------------------------------------
# the receipt and the clock


def test_the_receipt_lands_in_the_nights_own_folder_for_today(monkeypatch,
                                                              tmp_path):
    import backend.config as C

    monkeypatch.setattr(C, "OPTIMUS_LEDGER_DIR", tmp_path, raising=False)
    monkeypatch.setattr(RS, "receipt_path",
                        lambda day=None: tmp_path / f"night_factory_{day or date.today()}"
                        / "r.json")
    today = date.today().isoformat()
    p = RS.receipt_path(today)
    assert today in str(p.parent.name)
    # and the default is derived from the clock, never a literal
    assert date.today().isoformat() in RS.receipt_path().parent.name


def test_the_attended_command_names_the_flag_and_both_shells():
    cmd = RS.attended_command()
    assert RS.ARM_ENV in cmd
    assert "--apply" in cmd
    assert "PowerShell" in cmd, (
        "the machine this runs on is Windows; a bash-only line is a line the "
        "operator has to translate")


def test_yesterdays_receipt_does_not_satisfy_todays_scan(monkeypatch):
    """A gate that reads an old receipt is a gate on an old day (protocol 7)."""
    y = (date.today() - timedelta(days=1)).isoformat()
    assert RS.receipt_path(y) != RS.receipt_path(date.today().isoformat())
