"""The store must survive being killed. That is the requirement, not a nicety.

The news backfill died at 112/134 months -- 83.6% -- and every month was redone,
because progress lived in a local variable, the receipt was written only at the
end, and there was no log. These tests are that failure written down as
assertions: after every document the disk knows enough to continue, a cursor is
never ahead of its data, and a non-200 is stored rather than dropped.

NO NETWORK. Every test writes bodies directly into a tmp_path store.
"""

from __future__ import annotations

import gzip
import json

import pytest

from backend.services.scrape_store import (SCHEMA_VERSION, USER_AGENT,
                                           ScrapeRefusal, ScrapeStore)


@pytest.fixture()
def store(tmp_path):
    return ScrapeStore("unit_src", root=tmp_path).begin(argv=["--unit"])


# ── refusals ────────────────────────────────────────────────────────────────
def test_an_unnamed_source_is_refused(tmp_path):
    with pytest.raises(ScrapeRefusal):
        ScrapeStore("   ", root=tmp_path)


def test_a_document_with_no_url_is_refused(store):
    with pytest.raises(ScrapeRefusal):
        store.put("", 200, b"x")


def test_a_None_body_is_refused_because_it_is_not_an_empty_document(store):
    """b'' with a status is a coverage FACT. None is a bug that would erase it."""
    with pytest.raises(ScrapeRefusal) as e:
        store.put("http://x/1", 200, None)
    assert "never looked" in str(e.value)


# ── provenance ──────────────────────────────────────────────────────────────
def test_the_raw_body_round_trips_byte_for_byte(store):
    body = b"col1,col2\n\xff\xfe binary-ish \x00 payload\n"
    rec = store.put("http://x/raw", 200, body)
    assert store.read_body(rec) == body
    assert gzip.decompress((store.bodies / rec.path).read_bytes()) == body


def test_every_row_carries_url_timestamp_status_and_sha256(store):
    rec = store.put("http://x/1", 200, b"hello")
    import hashlib
    assert rec.url == "http://x/1"
    assert rec.http_status == 200
    assert rec.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert rec.n_bytes == 5
    assert rec.fetched_at.endswith("+00:00")


def test_a_non_200_is_STORED_not_dropped(store):
    """A store that keeps only successes cannot tell "we looked and it was not
    there" from "we never looked" -- the WRDS pull's exact failure."""
    store.put("http://x/404", 404, b"")
    store.put("http://x/429", 429, b"slow down")
    rec = store.receipt(write=False)
    assert rec["by_http_status"] == {"404": 1, "429": 1}


def test_put_is_idempotent_by_source_and_url(store):
    store.put("http://x/1", 200, b"a")
    assert store.has("http://x/1")
    store.put("http://x/1", 200, b"a")
    assert store.count() == 1, "the same URL must not create a second doc_id"


def test_two_sources_do_not_collide_on_the_same_url(tmp_path):
    a = ScrapeStore("src_a", root=tmp_path)
    b = ScrapeStore("src_b", root=tmp_path)
    assert a.doc_id_for("http://x/1") != b.doc_id_for("http://x/1")


# ── the resume ──────────────────────────────────────────────────────────────
def test_the_cursor_survives_the_process(tmp_path):
    s1 = ScrapeStore("resume_src", root=tmp_path).begin()
    s1.put("http://x/1", 200, b"one")
    s1.advance("stamp-001")
    s1.finish()
    s2 = ScrapeStore("resume_src", root=tmp_path)      # a NEW object, as a rerun is
    assert s2.cursor() == "stamp-001"
    assert s2.has("http://x/1"), "the resume must not re-fetch what it has"


def test_cursors_are_NAMED_so_a_backfill_cannot_ride_a_tail_cursor(tmp_path):
    """The bug this file's author wrote on the first pass.

    With one cursor per source, a rolling run left it at 09:45 and a backfill of
    04:00-08:00 fast-forwarded itself past its own window, fetched ZERO stamps
    and reported success. A cursor answers "how far did THIS traversal get".
    """
    s = ScrapeStore("named_src", root=tmp_path).begin()
    s.advance("20260907094500", key="tail")
    s.advance("20260907043000", key="window:0400-0800")
    assert s.cursor("tail") == "20260907094500"
    assert s.cursor("window:0400-0800") == "20260907043000"
    assert s.cursor("never-run") is None


def test_a_corrupt_cursor_reads_as_NO_cursor_which_re_does_work(tmp_path):
    """The safe direction. Reading a corrupt cursor optimistically SKIPS work."""
    s = ScrapeStore("corrupt_src", root=tmp_path).begin()
    s.advance("stamp-1")
    s.cursor_path.write_text("{not json", encoding="utf-8")
    assert s.cursor() is None


def test_a_torn_index_line_is_skipped_and_not_silently_repaired(tmp_path):
    """The normal shape of a crash mid-append."""
    s = ScrapeStore("torn_src", root=tmp_path).begin()
    s.put("http://x/1", 200, b"a")
    with s.index_path.open("a", encoding="utf-8") as fh:
        fh.write('{"doc_id": "half-writ')
    s2 = ScrapeStore("torn_src", root=tmp_path).begin()
    assert s2.count() == 1
    assert len(list(s2.records())) == 1


def test_the_pid_file_is_left_on_a_crash_and_removed_on_a_clean_finish(tmp_path):
    s = ScrapeStore("pid_src", root=tmp_path).begin(argv=["--x"])
    assert s.pid_path.exists(), "a long job must write down its own pid"
    import os
    assert json.loads(s.pid_path.read_text(encoding="utf-8"))["pid"] == os.getpid()
    # A crash is simulated by NOT calling finish.
    s2 = ScrapeStore("pid_src", root=tmp_path).begin()
    assert "RESUME after a crash" in s2.log_path.read_text(encoding="utf-8")
    s2.finish()
    assert not s2.pid_path.exists(), (
        "a clean finish must clear the pid file, or its presence stops being "
        "evidence of anything")


# ── the receipt, written as it goes ─────────────────────────────────────────
def test_the_receipt_exists_BEFORE_the_run_ends(store):
    """A receipt that only exists at the end does not exist for any run that
    fails -- and those are the runs whose coverage somebody urgently needs."""
    store.put("http://x/1", 200, b"a")
    store.receipt(note="in flight")
    assert store.receipt_path.exists()
    d = json.loads(store.receipt_path.read_text(encoding="utf-8"))
    assert d["n_docs"] == 1 and d["note"] == "in flight"
    store.put("http://x/2", 200, b"bb")
    d2 = store.receipt()
    assert d2["n_docs"] == 2 and d2["n_bytes"] == 3


def test_the_receipt_declares_the_user_agent_it_fetched_with(store):
    rec = store.receipt(write=False)
    assert rec["user_agent"] == USER_AGENT
    assert "Aegis" in USER_AGENT and "http" in USER_AGENT, (
        "a User-Agent a site cannot trace back to a contact is not descriptive")
    assert rec["schema_version"] == SCHEMA_VERSION


def test_the_log_is_a_FILE_not_only_a_terminal(store):
    store.log("SOMETHING HAPPENED")
    assert "SOMETHING HAPPENED" in store.log_path.read_text(encoding="utf-8")
