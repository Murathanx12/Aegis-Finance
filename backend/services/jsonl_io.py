"""Reading a JSONL file without `str.splitlines()`, and the bug that needs it.

MEASURED 2026-09-13, on the first run of L2 over the news corpus
==============================================================
`backend/data/optimus/news_corpus/alpaca_benzinga_news/2026-09-11.jsonl` has
3,799 rows. `read_text().splitlines()` returns **3,808 lines**, nine of which are
fragments that do not parse, because nine article bodies contain a literal
**U+2028 LINE SEPARATOR**. `json.dumps` does not escape U+2028 (it is not a
control character), and `str.splitlines()` DOES split on it -- along with \\v,
\\f, \\x1c, \\x1d, \\x1e, \\x85 and U+2029. A JSONL file is delimited by `\\n`
and by nothing else.

The failure is silent by construction. Every reader of that corpus wraps the
parse in `except: continue`, so each affected row produced two unparseable
fragments, both skipped, and the row vanished from the panel with no count and no
log line. 9 of 3,799 is 0.24% today; the share is a property of the publisher's
copy-paste, not a constant.

`scripts/night_e1_news_return_panel.py` (the N-C join, line ~368) and
`scripts/night_l2_typed_events.py` both read through here now. Roughly twenty
other modules still call `.splitlines()` on a JSONL path; they are not migrated
in this commit because each needs its own check that the change cannot alter a
count somebody has already published, and because the exposure is real only for
corpora that carry pasted article text. This module is where they go when they
do.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

#: Characters `str.splitlines()` breaks on that a JSONL file does NOT.
#: U+2028/U+2029 are the ones that occur in the wild; the rest are here because a
#: reader who finds this list should not have to re-derive it.
OVER_SPLIT_ON = ("\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", " ", " ")


def split_lines(text: str) -> list[str]:
    """The file's lines, split on `\\n` only. `\\r\\n` is handled; nothing else is."""
    return [line.rstrip("\r") for line in (text or "").split("\n")]


def iter_rows(path: Path | str, *, errors: str = "strict") -> Iterator[dict]:
    """Every parseable row, in file order.

    Raises `json.JSONDecodeError` by default: a line that does not parse is a
    corrupt file, and the reader that skips it silently is the failure this
    module exists to stop. Pass `errors="skip"` only where a count of the skips
    is kept and printed -- `read_rows` returns one.
    """
    for row, _ in _iter(Path(path), errors):
        yield row


def read_rows(path: Path | str, *, errors: str = "skip") -> tuple[list[dict], list[str]]:
    """`(rows, problems)`. The problems list is never thrown away by the caller:
    an empty list and an unread list look identical in a receipt and mean
    opposite things."""
    rows, problems = [], []
    for row, problem in _iter(Path(path), errors):
        if problem:
            problems.append(problem)
        else:
            rows.append(row)
    return rows, problems


def _iter(path: Path, errors: str):
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(split_lines(text), 1):
        if not line.strip():
            continue
        try:
            yield json.loads(line), None
        except json.JSONDecodeError as exc:
            if errors == "strict":
                raise
            yield None, f"{path.name}:{i}: {exc}"


def over_split_count(text: str) -> int:
    """How many lines `str.splitlines()` invents over the JSONL reading.

    A diagnostic a receipt can print: zero means the two readers agree on this
    file, and any other number is rows a `.splitlines()` reader is losing. Blank
    lines are excluded on BOTH sides -- a JSONL file's trailing newline produces
    an empty final element under `split("\\n")` and none under `splitlines()`,
    and counting that difference would report every well-formed file as broken.
    """
    text = text or ""
    return (len([line for line in text.splitlines() if line.strip()])
            - len([line for line in split_lines(text) if line.strip()]))
