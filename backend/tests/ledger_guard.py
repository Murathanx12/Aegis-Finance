"""Did the fast suite write into the tracked evidence ledger?

THE DEFECT THIS EXISTS FOR, found by Fable validating chunk 1 on 2026-09-11.
`test_scratch_receipts_are_skipped_because_they_share_the_real_jobs_name`
redirects N7's *receipt* directory to `tmp_path` and then calls `N7.run()`,
which folds every receipt it read into `learner.evidence_memory` -- the module
attribute, the LIVE one. So a test about which files a job reads appended a
`SKIPPED -- nothing here` observation to a 102,029-row, 65 MB ledger on every
single suite run. Nothing failed; `git status` was simply dirty afterwards, and
on 2026-09-11 one such row was discarded by hand.

It is the same family as `_execution_ledger_to_tmp` and `_disk_cache_to_tmp` in
`conftest.py`: a test drives a real writer and the writer's destination is a
module constant nobody redirected. Those two were also found by reading
`git status` after a run -- which is to say, by luck and by habit. This module
turns the habit into a gate: `conftest.pytest_sessionstart` fingerprints the
ledger files, `pytest_sessionfinish` fingerprints them again, and a difference
fails the run with the offending file named.

It hashes bytes rather than counting rows on purpose: a row REPLACED in place
(a compaction, a rewrite) is as much a defect as a row appended, and a size
comparison alone would miss it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Every ledger file the suite must leave alone: the legacy monolith, the
#: monthly files it rotated into (E6), and the supersessions log.
LEDGER_DIR = REPO / "backend" / "data" / "optimus" / "learner"
PATTERN = "evidence_memory*.jsonl"


def fingerprint(directory: Path | None = None) -> dict[str, tuple[int, str]]:
    """`{filename: (size_bytes, sha256)}` for every ledger file that exists."""
    d = Path(directory) if directory is not None else LEDGER_DIR
    out: dict[str, tuple[int, str]] = {}
    if not d.is_dir():
        return out
    for p in sorted(d.glob(PATTERN)):
        try:
            data = p.read_bytes()
        except OSError:
            continue
        out[p.name] = (len(data), hashlib.sha256(data).hexdigest())
    return out


def differences(before: dict[str, tuple[int, str]],
                after: dict[str, tuple[int, str]]) -> list[str]:
    """One human-readable line per file the run changed. Empty list = clean."""
    msgs = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name), after.get(name)
        if b == a:
            continue
        if b is None:
            msgs.append(f"{name}: CREATED by the run ({a[0]} bytes)")
        elif a is None:
            msgs.append(f"{name}: DELETED by the run (was {b[0]} bytes)")
        else:
            msgs.append(
                f"{name}: CHANGED by the run ({b[0]} -> {a[0]} bytes, "
                f"sha256 {b[1][:12]} -> {a[1][:12]})")
    return msgs


FAILURE_HEADER = (
    "THE SUITE WROTE INTO THE EVIDENCE LEDGER. A test drove a real writer whose "
    "destination is a module constant (`learner.evidence_memory.STORE_DIR`) that "
    "the test did not redirect. Redirect it with `monkeypatch.setattr(EM, "
    "\"STORE_DIR\", tmp_path)` -- the ledger is append-only and tracked, and a "
    "row written by a test is indistinguishable from a row written by a job.")
