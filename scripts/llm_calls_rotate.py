"""ONE-SHOT: split `llm_calls.jsonl` into monthly files, by each row's own `ts`.

WHY THIS EXISTS
===============
`backend/data/optimus/llm_calls.jsonl` was **62.25 MB** on 2026-09-12 and every
LLM call appends to it. GitHub WARNED on a push at 50 MB and REFUSES a blob at
100. This is the same shape as the evidence memory that E6 rotated the day
before, so it takes the same answer, and this script is deliberately the same
script with a different stamp key.

**COMPACTION IS REFUSED.** The ledger is append-only so that "what did this call
cost, and what did it yield" stays answerable per call; a summary that replaces
its own rows cannot answer it, and a spend ledger that cannot be re-derived is
not a ledger. Nothing here summarises, dedupes or drops a row.

BY THE ROW'S STAMP, NEVER BY mtime
==================================
A fresh CI checkout writes every file today. A split dated by `st_mtime` would
file the entire history under whatever month someone last cloned the repo --
the defect family that kept finance CI red for two days (protocol section 7). A
row whose `ts` will not parse is not guessed at: this script **refuses**, prints
how many and the first three, and writes nothing.

The refusal is not a dead end. This ledger already carries TORN lines -- 24
worker threads in LLM-SWARM-1 split rows mid-write, and `llm_telemetry.
scan_integrity` has counted them ever since -- and a torn line is a FRAGMENT
with no `ts` because it is half a row. `--quarantine-unstamped` copies those
lines VERBATIM to `llm_calls_unstamped.jsonl` with their line numbers: no month
is guessed, nothing is deleted, and the receipt closes the arithmetic as
`rows_in == rows_out + rows_quarantined`. Four of 92,737 rows on 2026-09-12.

LINE ENDINGS
============
The monolith was written in text mode on Windows and carries CRLF, one extra
byte a line. The month files are written with `newline="\\n"`, so the rotation
also ends a ledger whose bytes depended on the OS that appended them -- the same
lesson the evidence memory paid for. Row COUNT is what the receipt reconciles
(`rows_in == rows_out`), not byte equality, and the receipt carries a sha256 per
output file so a later reader can prove which bytes it read.

IDEMPOTENT
==========
Run it twice and the second run is a no-op: with the monolith already gone it
reports `already_rotated`; with the monolith still present and the month files
already holding exactly those rows (plus any appended since) it reports each
month as `identical` or `already_contains_these_rows` and rewrites nothing. A
month file whose content is NOT a prefix of what this split produces is a
refusal, not an overwrite -- two disagreeing copies of a month is the one
outcome worse than a 62 MB file.

USAGE
    python -m scripts.llm_calls_rotate --dry-run
    python -m scripts.llm_calls_rotate
    python -m scripts.llm_calls_rotate --delete-monolith   # after the reader test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import llm_telemetry as TEL            # noqa: E402
# ONE guard, two families: the sealed-month check is the evidence memory's, with
# a different prefix. A second copy would be a second place for the rule to rot.
from scripts.evidence_memory_rotate import (RotationRefused,  # noqa: E402
                                            untracked_closed_months as _untracked)

#: the family name, which is also the file stem
PREFIX = "llm_calls"
#: A stamp this script is willing to file. Anything else is a refusal.
STAMP = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])")


def _rel(path: Path) -> str:
    """Repo-relative and forward-slashed, so a receipt written on this laptop
    reads the same on Linux CI."""
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def untracked_closed_months(directory: Path | None = None, *,
                            now: datetime | None = None) -> dict:
    """The sealed-month guard for THIS family. See `evidence_memory_rotate`."""
    return _untracked(directory if directory is not None else TEL.LEDGER_DIR,
                      prefix=PREFIX, now=now)


def month_of_line(line: str) -> str | None:
    """The month this row belongs to, or None if its `ts` cannot be read.

    `ts`, not `utc`: that one word is the whole difference between this family
    and the evidence memory's, and it is why the split is a function here rather
    than a parameter passed into somebody else's loop.
    """
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict):
        return None
    m = STAMP.match(str(row.get("ts") or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def split(text: str) -> tuple[dict[str, list[str]], list[tuple[int, str]], int]:
    """`({month: [line, ...]}, [(lineno, line), ...unstamped], rows_in)`.

    Lines are kept VERBATIM (not re-serialised): a round-trip through
    `json.dumps` would reorder keys and rewrite floats, and the point of an
    append-only ledger is that a row is the bytes that were written.
    """
    by_month: dict[str, list[str]] = {}
    unstamped: list[tuple[int, str]] = []
    rows_in = 0
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        rows_in += 1
        month = month_of_line(line)
        if month is None:
            unstamped.append((i, line))
            continue
        by_month.setdefault(month, []).append(line)
    return by_month, unstamped, rows_in


def _write_atomic(path: Path, data: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


#: Where a line with no readable `ts` goes when the operator says so. Copied
#: VERBATIM with its line number and the reason, never dropped and never
#: repaired -- the same doctrine as `llm_telemetry.quarantine_unreadable`.
UNSTAMPED = f"{PREFIX}_unstamped.jsonl"


def rotate(directory: Path | None = None, *, apply: bool = True,
           delete_monolith: bool = False, receipt_dir: Path | None = None,
           quarantine_unstamped: bool = False) -> dict:
    d = Path(directory) if directory is not None else TEL.LEDGER_DIR
    monolith = d / f"{PREFIX}.jsonl"
    live_month = _now()[:7]
    out: dict = {
        "job": "llm_calls_rotate",
        "lane": "T6",
        "licence": "PRODUCT_EXPERIMENT",
        "utc": _now(),
        "question": "did every row of the monolith reach the month its own `ts` names?",
        "compaction": "REFUSED -- no row summarised, deduped or dropped",
        "dated_by": "each row's own `ts`, never the filesystem",
        "line_endings": ("the monolith carries CRLF (text mode on Windows); the "
                         "month files are LF, so rows_in == rows_out is the "
                         "reconciliation, not byte equality"),
        "directory": _rel(d),
        "live_month": live_month,
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
    }

    if not monolith.exists():
        files = TEL.ledger_files(monolith)
        out["status"] = "already_rotated"
        out["headline"] = (f"no monolith on disk; the monthly files are the ledger "
                           f"({len(files)} file(s))")
        out["months"] = {p.name: {"bytes": p.stat().st_size} for p in files}
        return out

    raw = monolith.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    by_month, unstamped, rows_in = split(text)

    out["monolith"] = {"path": _rel(monolith), "bytes": len(raw),
                       "sha256": _sha256(raw), "rows": rows_in}
    out["rows_in"] = rows_in
    out["rows_without_a_parseable_stamp"] = len(unstamped)

    if unstamped and not quarantine_unstamped:
        out["status"] = "REFUSED"
        out["first_three_unstamped"] = [{"line_number": n, "text": s[:200]}
                                        for n, s in unstamped[:3]]
        raise RotationRefused(
            f"{len(unstamped)} of {rows_in} rows carry no parseable `ts`. "
            f"A row filed under a guessed month is indistinguishable from a "
            f"call made that month, so nothing was written. If these are the "
            f"TORN lines the ledger already knows about "
            f"(`llm_telemetry.scan_integrity`), re-run with "
            f"--quarantine-unstamped: they are then copied VERBATIM to "
            f"{UNSTAMPED} with their line numbers, counted in the receipt, and "
            f"filed under no month. First three:\n" +
            "\n".join(f"  line {n}: {s[:200]}" for n, s in unstamped[:3]))

    if unstamped:
        # NOT a month, NOT a deletion. A torn line is a FRAGMENT of accounting
        # data: it has no `ts` because it is half a row, so there is no month it
        # belongs to and no spend in it to recover. Filing it under the wall
        # clock would put a fabricated date on damage; dropping it would destroy
        # the only evidence that anything was lost. It gets an address instead,
        # and `rows_in == rows_out + rows_quarantined` keeps the arithmetic
        # closed.
        out["quarantined"] = {
            "path": _rel(d / UNSTAMPED), "rows": len(unstamped),
            "first_three": [{"line_number": n, "text": s[:200]} for n, s in unstamped[:3]],
            "why": ("no parseable `ts`; copied verbatim, never filed under a "
                    "guessed month and never deleted"),
        }
        if apply:
            blob = "".join(json.dumps(
                {"line_no": n, "raw": s, "source": _rel(monolith),
                 "reason": "no parseable `ts`", "detected_at": _now()},
                ensure_ascii=False) + "\n" for n, s in unstamped)
            with (d / UNSTAMPED).open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(blob)

    months: dict[str, dict] = {}
    rows_out = 0
    for month in sorted(by_month):
        lines = by_month[month]
        data = "\n".join(lines) + "\n"
        target = d / f"{PREFIX}_{month}.jsonl"
        rec = {"path": _rel(target), "rows": len(lines),
               "bytes": len(data.encode("utf-8")),
               "sha256": _sha256(data.encode("utf-8")),
               "sealed": month < live_month}
        rows_out += len(lines)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if existing == data:
                rec["action"] = "identical"
            elif existing.startswith(data):
                rec["action"] = "already_contains_these_rows"
                rec["rows_appended_since"] = len(existing[len(data):].strip().splitlines())
            else:
                out["status"] = "REFUSED"
                raise RotationRefused(
                    f"{target.name} already exists and its content is not the "
                    f"rows this split produces (nor those rows plus later "
                    f"appends). Refusing to overwrite: two disagreeing copies "
                    f"of one month is worse than one large file.")
        elif apply:
            _write_atomic(target, data)
            rec["action"] = "written"
        else:
            rec["action"] = "would_write"
        months[month] = rec

    out["months"] = months
    out["rows_out"] = rows_out
    out["rows_quarantined"] = len(unstamped)
    out["rows_in_equals_rows_out"] = (rows_in == rows_out + len(unstamped))
    out["sealed_months"] = sorted(m for m in months if months[m]["sealed"])
    out["untracked_live_month"] = live_month if live_month in months else None
    out["status"] = "OK" if apply else "DRY_RUN"

    if apply and delete_monolith:
        # Only after the caller has proven the reader returns every row from the
        # split. The bytes are still in git history; this removes the working-
        # tree copy so the ledger has exactly one home per month.
        monolith.unlink()
        out["monolith_deleted"] = True
    else:
        out["monolith_deleted"] = False

    out["headline"] = (
        f"{rows_in} rows -> {rows_out} in {len(months)} month file(s)"
        + (f" + {len(unstamped)} unstamped quarantined" if unstamped else "") + ": "
        + ", ".join(f"{m} {months[m]['rows']} rows ({months[m]['action']})"
                    for m in sorted(months)))

    if apply:
        rdir = Path(receipt_dir) if receipt_dir is not None else d
        rpath = rdir / f"llm_calls_rotation_receipt_{_now()[:10]}.json"
        if rpath.exists():
            # A second run the same day must not rewrite the receipt: the only
            # field that would change is its own timestamp, and a receipt that
            # churns on a no-op teaches the reader to ignore its date.
            out["receipt"] = _rel(rpath)
            out["receipt_action"] = "kept (already written today)"
        else:
            rdir.mkdir(parents=True, exist_ok=True)
            rpath.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
            out["receipt"] = _rel(rpath)
            out["receipt_action"] = "written"
        out["receipt_abs"] = str(rpath)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=None, help="the ledger directory (default: the repo's)")
    ap.add_argument("--dry-run", action="store_true", help="report the split, write nothing")
    ap.add_argument("--delete-monolith", action="store_true",
                    help="remove the single file AFTER the reader test passes")
    ap.add_argument("--quarantine-unstamped", action="store_true",
                    help=f"copy rows with no parseable `ts` to {UNSTAMPED} "
                         f"instead of refusing (for the ledger's known torn lines)")
    a = ap.parse_args(argv)
    try:
        rec = rotate(Path(a.dir) if a.dir else None, apply=not a.dry_run,
                     delete_monolith=a.delete_monolith,
                     quarantine_unstamped=a.quarantine_unstamped)
    except RotationRefused as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps({k: v for k, v in rec.items() if k != "months"},
                     indent=1, default=str))
    for m, r in sorted(rec.get("months", {}).items()):
        print(f"  {m}  {r.get('rows', '-'):>7} rows  {r.get('bytes', '-'):>10} bytes  "
              f"{r.get('action')}  sealed={r.get('sealed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
