"""Every parquet under the WRDS tree must be covered by a row in the manifest.

`docs/DATA_MANIFEST.md` states its own rule in its own words: *"If you add an
ignore rule for a data file, add its row here in the same commit. An ignore rule
without a manifest row is the bug."* On 2026-09-04 that rule was violated by
58.52 GiB — the blanket ``*.parquet`` rule (`.gitignore` line 63) swallowed
1,378 WRDS files and the manifest named two JSONs.

This test closes that loop the only way that stays true: the pattern list is
**parsed out of the manifest**, never hard-coded here. Adding a family row is
what makes a new family pass — which is the point, since the failure mode is a
pull that lands on disk and is never written down.

Design constraints, both deliberate:

1. **It must be able to go green.** It does, today, on the machine that holds
   the tree — every one of the 1,378 files matches a row.
2. **It must skip cleanly where the tree is absent.** CI and every other machine
   do not have 59 GB. A gate that can only ever be red teaches the reader to
   skim red lines (CLAUDE.md, "a gate that cannot go green is a broken gate"),
   so absence of the substrate is a SKIP, and a partial tree is fine — the test
   asserts coverage of what is present, never that everything is present.

Metadata only: this reads directory entries. It never opens a parquet.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "docs" / "DATA_MANIFEST.md"
WRDS_PREFIX = "backend/data/optimus/wrds/"
WRDS_ROOT = REPO / WRDS_PREFIX

#: Backticked path in a markdown table cell, e.g. `backend/data/.../comp__*.parquet`
_CELL = re.compile(r"`([^`\n]+\.parquet)`")


def manifest_patterns() -> list[str]:
    """Every `...parquet` glob the manifest declares under the WRDS tree.

    Returned relative to ``WRDS_PREFIX``. Derived from the file, so a new
    family row is the whole fix for a new family.
    """
    if not MANIFEST.exists():  # pragma: no cover - the doc is committed
        return []
    text = MANIFEST.read_text(encoding="utf-8")
    pats = []
    for raw in _CELL.findall(text):
        p = raw.strip().replace("\\", "/")
        if p.startswith(WRDS_PREFIX):
            rel = p[len(WRDS_PREFIX):]
            if rel and rel not in pats:
                pats.append(rel)
    return pats


def _to_regex(glob: str) -> re.Pattern[str]:
    """glob -> regex where ``*`` matches within ONE path segment.

    `fnmatch` is wrong here: its ``*`` crosses ``/``, so a row for
    ``bulk/comp__*.parquet`` would silently also cover
    ``bulk/_quarantine_truncated/comp__x.parquet`` and the quarantine would
    never need its own row.
    """
    out = []
    for ch in glob:
        out.append("[^/]*" if ch == "*" else re.escape(ch))
    return re.compile("".join(out) + r"\Z")


def wrds_parquets() -> list[str]:
    if not WRDS_ROOT.is_dir():
        return []
    return sorted(p.relative_to(WRDS_ROOT).as_posix()
                  for p in WRDS_ROOT.rglob("*.parquet"))


def test_manifest_declares_wrds_families() -> None:
    """The manifest must carry WRDS parquet rows at all.

    Runs everywhere — needs no data. It is the guard against the *other* silent
    failure: someone reformats the table, the regex stops matching, every path
    below trivially passes against an empty pattern list, and the gate goes
    green by knowing nothing.
    """
    pats = manifest_patterns()
    assert len(pats) >= 50, (
        f"docs/DATA_MANIFEST.md declares only {len(pats)} WRDS parquet "
        "families. Either the WRDS substrate section was removed or its table "
        "format changed and this parser no longer reads it."
    )


def test_every_wrds_parquet_matches_a_manifest_row() -> None:
    """No parquet on disk without a family row that covers it."""
    if not WRDS_ROOT.is_dir():
        pytest.skip(f"no WRDS substrate at {WRDS_PREFIX} (59 GB, local only)")
    files = wrds_parquets()
    if not files:
        pytest.skip(f"{WRDS_PREFIX} exists but holds no parquet")

    regexes = [_to_regex(g) for g in manifest_patterns()]
    unmatched = [f for f in files if not any(r.match(f) for r in regexes)]

    assert not unmatched, (
        f"{len(unmatched)} of {len(files)} parquet files under {WRDS_PREFIX} "
        "match no row in docs/DATA_MANIFEST.md. Add a family row (one glob per "
        "family, `*` matches within one path segment) — an ignored data file "
        "with no manifest row is the bug the manifest exists to prevent.\n"
        + "\n".join("  " + f for f in unmatched[:25])
        + (f"\n  ... and {len(unmatched) - 25} more" if len(unmatched) > 25 else "")
    )


def test_manifest_rows_are_segment_scoped() -> None:
    """A row must not be a catch-all that covers the whole tree.

    ``*.parquet`` or ``**/*.parquet`` as a family would make the test above
    vacuous. Segment-scoped globs are enforced by construction in `_to_regex`;
    this pins that no row tries to smuggle a directory wildcard through.
    """
    bad = [g for g in manifest_patterns() if g in ("*.parquet", "**/*.parquet")
           or "**" in g]
    assert not bad, (
        "catch-all WRDS rows in docs/DATA_MANIFEST.md would make coverage "
        f"vacuous: {bad}"
    )
