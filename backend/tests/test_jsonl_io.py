"""A JSONL file is delimited by \n and by nothing else.

MEASURED 2026-09-13: `news_corpus/alpaca_benzinga_news/2026-09-11.jsonl` holds
3,799 rows and `str.splitlines()` returns 3,808 lines, because nine article
bodies carry a literal U+2028 LINE SEPARATOR. Every reader of that file wrapped
the parse in `except: continue`, so each affected row became two unparseable
fragments and vanished with no count and no log line.
"""

from __future__ import annotations

import json

import pytest

from backend.services import jsonl_io as jio

LS = chr(0x2028)          # U+2028 LINE SEPARATOR, written as a code point on
LSEP = chr(0x2029)        # purpose: a raw one in a source file is invisible


def _file(tmp_path, rows, ensure_ascii=False):
    path = tmp_path / "rows.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=ensure_ascii) + "\n" for r in rows),
                    encoding="utf-8")
    return path


def test_a_line_separator_in_a_value_does_not_end_the_row(tmp_path):
    path = _file(tmp_path, [{"i": 0, "body": f"first{LS}second"}, {"i": 1, "body": ""}])
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) == 3, "the broken reader sees three lines"
    assert jio.over_split_count(text) == 1
    rows, problems = jio.read_rows(path)
    assert [r["i"] for r in rows] == [0, 1]
    assert problems == []
    assert rows[0]["body"] == f"first{LS}second"


def test_the_other_separators_splitlines_invents(tmp_path):
    exotic = "".join(jio.OVER_SPLIT_ON)
    path = _file(tmp_path, [{"i": 0, "body": exotic}])
    rows, problems = jio.read_rows(path)
    assert len(rows) == 1 and problems == []
    assert LSEP in jio.OVER_SPLIT_ON


def test_a_well_formed_file_reports_no_over_split(tmp_path):
    """A trailing newline must not read as a lost row."""
    path = _file(tmp_path, [{"i": i} for i in range(5)])
    assert jio.over_split_count(path.read_text(encoding="utf-8")) == 0


def test_a_corrupt_line_is_returned_as_a_problem_not_swallowed(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"i": 0}\n{"i": \n{"i": 2}\n', encoding="utf-8")
    rows, problems = jio.read_rows(path)
    assert [r["i"] for r in rows] == [0, 2]
    assert len(problems) == 1 and "rows.jsonl:2" in problems[0]


def test_strict_is_the_default_for_the_iterator(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"i": 0}\n{"i": \n', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        list(jio.iter_rows(path))


def test_crlf_is_handled_and_nothing_else_is(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_bytes(b'{"i": 0}\r\n{"i": 1}\r\n')
    assert [r["i"] for r in jio.iter_rows(path)] == [0, 1]
