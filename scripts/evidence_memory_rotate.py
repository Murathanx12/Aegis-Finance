"""ONE-SHOT: split `evidence_memory.jsonl` into monthly files, by each row's own stamp.

WHY THIS EXISTS (roadmap E6, the only dated item in it)
=======================================================
`backend/data/optimus/learner/evidence_memory.jsonl` was **65.16 MB** across
102,029 rows on 2026-09-11, and it grows every night the factory runs. GitHub
refuses a blob at 100 MB. The choice was between compacting the ledger and
splitting it, and **compaction is refused**: the store is append-only precisely
so that "what did we believe before we changed the bar" stays answerable, and a
summary that replaces its own rows cannot answer it. So nothing here summarises,
dedupes or drops a row. Every row goes to the month its **own `utc` stamp**
names and comes back out of `evidence_memory.read_all()` in the same order.

BY THE ROW'S STAMP, NEVER BY mtime
==================================
A fresh CI checkout writes every file today. A split dated by `st_mtime` would
therefore file the entire history under whatever month someone last cloned the
repo -- the same defect family that kept finance CI red for two days by dating a
receipt from the filesystem (protocol §7). A row whose stamp will not parse is
not guessed at: this script **refuses**, prints how many and the first three,
and writes nothing.

IDEMPOTENT
==========
Run it twice and the second run is a no-op: with the monolith already gone it
reports `already_rotated`; with the monolith still present and the month files
already holding exactly those rows (plus any rows appended since) it reports
each month as `identical` or `already_contains_these_rows` and rewrites nothing.
A month file whose existing content is NOT a prefix of what this split produces
is a refusal, not an overwrite -- two disagreeing copies of a month is the one
outcome worse than a 65 MB file.

WRITES ARE ATOMIC
=================
Each month file is written to `<name>.tmp` and `os.replace`d into place, so a
crash mid-run leaves either the old file or the new one, never half of either.

USAGE
    python -m scripts.evidence_memory_rotate --dry-run
    python -m scripts.evidence_memory_rotate
    python -m scripts.evidence_memory_rotate --delete-monolith   # after the reader test
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
sys.path.insert(0, str(REPO))

from learner import evidence_memory as EM               # noqa: E402

#: A stamp this script is willing to file. Anything else is a refusal.
STAMP = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])")


class RotationRefused(RuntimeError):
    """A refusal, printed with its count and its first three offenders."""


def _rel(path: Path) -> str:
    """Repo-relative and forward-slashed, so a receipt written on this laptop
    reads the same on Linux CI. `C:\\Users\\mrthn\\...` in provenance was one of
    the five causes of the two days of CI red in September."""
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def month_of_line(line: str) -> str | None:
    """The month this row belongs to, or None if its stamp cannot be read."""
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(row, dict):
        return None
    m = STAMP.match(str(row.get("utc") or ""))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def untracked_closed_months(directory: Path | None = None, *,
                            now: datetime | None = None) -> dict:
    """Month files for a CLOSED month that git does not track.

    The live month is `.gitignore`d on purpose -- committing it would recreate
    the 65 MB blob under a new name -- and a month that has closed is meant to
    be sealed once, by hand:

        git add -f backend/data/optimus/learner/evidence_memory_2026-09.jsonl

    "By hand, on the 1st" is exactly the kind of step that is not done, and the
    failure is SILENT: the ignore rule keeps working, the reader keeps reading
    the local file, and the month is simply missing for everyone else and gone
    the day the laptop is reimaged. Nothing is red, and a month of the ledger
    has left the repository.

    Returns `{"checked", "reason", "months"}`. A guard DERIVES its inputs or
    REFUSES: when `git ls-files` cannot be run (no git, not a checkout, a
    sandbox), `checked` is False with the reason, and the caller must report
    CANNOT DETERMINE rather than "nothing to do".
    """
    import subprocess

    d = Path(directory) if directory is not None else EM.STORE_DIR
    stamp = now or datetime.now(timezone.utc)
    current = f"{stamp:%Y-%m}"

    on_disk = []
    for q in sorted(d.glob("evidence_memory_*.jsonl")):
        m = re.match(r"^evidence_memory_(\d{4}-\d{2})\.jsonl$", q.name)
        if m and m.group(1) < current:       # lexicographic == chronological
            on_disk.append((m.group(1), q))
    if not on_disk:
        return {"checked": True, "reason": None, "months": []}

    try:
        out = subprocess.run(["git", "ls-files", "--", str(d)],
                             cwd=str(REPO), capture_output=True, text=True,
                             timeout=30, check=True).stdout
    except Exception as e:
        return {"checked": False,
                "reason": f"git ls-files failed ({type(e).__name__}: {e}); "
                          f"cannot tell a sealed month from a forgotten one",
                "months": []}

    tracked = {line.strip().rsplit("/", 1)[-1] for line in out.splitlines() if line.strip()}
    missing = []
    for month, q in on_disk:
        if q.name not in tracked:
            missing.append({
                "month": month,
                "file": _rel(q),
                "rows": sum(1 for _ in q.open(encoding="utf-8", errors="replace")),
                "command": f"git add -f {_rel(q)}",
            })
    return {"checked": True, "reason": None, "months": missing}


def split(text: str) -> tuple[dict[str, list[str]], list[tuple[int, str]], int]:
    """`({month: [line, ...]}, [(lineno, line), ...unstamped], rows_in)`.

    Lines are kept VERBATIM (not re-serialised): a round-trip through
    `json.dumps` would reorder keys and rewrite floats, and the whole point of
    an append-only ledger is that a row is the bytes that were written.
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


def rotate(directory: Path | None = None, *, apply: bool = True,
           delete_monolith: bool = False, receipt_dir: Path | None = None) -> dict:
    d = Path(directory) if directory is not None else EM.STORE_DIR
    monolith = d / EM.STORE.name
    live_month = _now()[:7]
    out: dict = {
        "job": "evidence_memory_rotate",
        "lane": "E6",
        "licence": "PRODUCT_EXPERIMENT",
        "utc": _now(),
        "question": "did every row of the monolith reach the month its own stamp names?",
        "compaction": "REFUSED -- no row summarised, deduped or dropped",
        "dated_by": "each row's own `utc`, never the filesystem",
        "directory": _rel(d),
        "live_month": live_month,
        "llm_spend_usd": 0.0, "llm_calls": 0, "network_calls": 0,
    }

    if not monolith.exists():
        out["status"] = "already_rotated"
        out["headline"] = ("no monolith on disk; the monthly files are the store "
                           f"({len(EM.store_files(d))} file(s))")
        out["months"] = {p.name: {"bytes": p.stat().st_size} for p in EM.store_files(d)}
        return out

    raw = monolith.read_bytes()
    text = raw.decode("utf-8")
    by_month, unstamped, rows_in = split(text)

    out["monolith"] = {
        "path": _rel(monolith), "bytes": len(raw),
        "sha256": _sha256(raw), "rows": rows_in,
    }
    out["rows_in"] = rows_in
    out["rows_without_a_parseable_stamp"] = len(unstamped)

    if unstamped:
        out["status"] = "REFUSED"
        out["first_three_unstamped"] = [
            {"line_number": n, "text": s[:200]} for n, s in unstamped[:3]]
        raise RotationRefused(
            f"{len(unstamped)} of {rows_in} rows carry no parseable `utc`. "
            f"A row filed under a guessed month is indistinguishable from one "
            f"made that month, so nothing was written. First three:\n" +
            "\n".join(f"  line {n}: {s[:200]}" for n, s in unstamped[:3]))

    months: dict[str, dict] = {}
    rows_out = 0
    for month in sorted(by_month):
        lines = by_month[month]
        data = "\n".join(lines) + "\n"
        target = d / f"evidence_memory_{month}.jsonl"
        rec = {
            "path": _rel(target), "rows": len(lines),
            "bytes": len(data.encode("utf-8")),
            "sha256": _sha256(data.encode("utf-8")),
            "sealed": month < live_month,
        }
        rows_out += len(lines)
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if existing == data:
                rec["action"] = "identical"
            elif existing.startswith(data):
                extra = len(existing[len(data):].strip().splitlines())
                rec["action"] = "already_contains_these_rows"
                rec["rows_appended_since"] = extra
            else:
                out["status"] = "REFUSED"
                raise RotationRefused(
                    f"{target.name} already exists and its content is not the "
                    f"rows this split produces (nor those rows plus later "
                    f"appends). Refusing to overwrite: two disagreeing copies "
                    f"of one month is worse than one large file. Move it aside "
                    f"and re-run if the existing file is the stale one.")
        elif apply:
            _write_atomic(target, data)
            rec["action"] = "written"
        else:
            rec["action"] = "would_write"
        months[month] = rec

    out["months"] = months
    out["rows_out"] = rows_out
    out["rows_in_equals_rows_out"] = (rows_in == rows_out)
    out["sealed_months"] = sorted(m for m in months if months[m]["sealed"])
    out["untracked_live_month"] = live_month if live_month in months else None
    out["status"] = "OK" if apply else "DRY_RUN"

    if apply and delete_monolith:
        # Only after the caller has proven the reader returns every row from
        # the split. The bytes are still in git history; this removes the
        # working-tree copy so the store has exactly one home per month.
        monolith.unlink()
        out["monolith_deleted"] = True
    else:
        out["monolith_deleted"] = False

    out["headline"] = (
        f"{rows_in} rows -> {len(months)} month file(s): " +
        ", ".join(f"{m} {months[m]['rows']} rows ({months[m]['action']})"
                  for m in sorted(months)))

    if apply:
        rdir = Path(receipt_dir) if receipt_dir is not None else d
        rpath = rdir / f"rotation_receipt_{_now()[:10]}.json"
        if rpath.exists():
            # A second run the same day must not rewrite the receipt: the only
            # field that would change is its own timestamp, and a receipt that
            # churns on a no-op teaches the reader to ignore its date.
            out["receipt"] = _rel(rpath)
            out["receipt_action"] = "kept (already written today)"
        else:
            rdir.mkdir(parents=True, exist_ok=True)
            rpath.write_text(json.dumps(out, indent=1, default=str),
                             encoding="utf-8")
            out["receipt"] = _rel(rpath)
            out["receipt_action"] = "written"
        out["receipt_abs"] = str(rpath)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default=None,
                    help="the learner directory (default: the repo's)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the split, write nothing")
    ap.add_argument("--delete-monolith", action="store_true",
                    help="remove the single file AFTER the reader test passes")
    a = ap.parse_args(argv)
    try:
        rec = rotate(Path(a.dir) if a.dir else None,
                     apply=not a.dry_run,
                     delete_monolith=a.delete_monolith)
    except RotationRefused as exc:
        print(f"REFUSED: {exc}")
        return 2
    printable = {k: v for k, v in rec.items() if k != "months"}
    print(json.dumps(printable, indent=1, default=str))
    for m, r in sorted(rec.get("months", {}).items()):
        print(f"  {m}  {r.get('rows', '-'):>7} rows  {r.get('bytes', '-'):>10} bytes  "
              f"{r.get('action')}  sealed={r.get('sealed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
