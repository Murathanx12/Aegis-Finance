"""Closed monthly ledgers -> Parquet outside git, with a COMMITTED manifest.

    python -m backend.services.ledger_archive --scan                 # list candidates, write nothing
    python -m backend.services.ledger_archive --apply                # archive every closed month >= the size floor
    python -m backend.services.ledger_archive --ledger <path> --apply  # archive one month file

WHAT "THE LONG-TERM ARCHIVAL DESIGN FOR VERY LARGE MONTHLY LEDGERS" MEANT
======================================================================
Two append-only ledgers were split into one file a month in September
(`scripts/evidence_memory_rotate.py`, `scripts/llm_calls_rotate.py`). The
design was: the live month is gitignored, and on the 1st the CLOSED month is
sealed with `git add -f`. A guard (`untracked_closed_months`) fails the suite
when a closed month is left untracked.

`llm_calls_2026-09.jsonl` closed at **178 MB**. GitHub refuses any blob over
100 MB, so the prescribed remedy could not be run, the guard stayed red, and
the month existed on one laptop only. That is the unresolved part: git was
being used as the warehouse for a ledger that outgrew it.

The answer built here:

* the closed month is converted to Parquet under `<data root>/ledger_archive/`
  (ignored by the blanket `*.parquet` rule -- outside git);
* a small JSON MANIFEST is committed under `ledger_manifests/`: schema, rows,
  first/last stamp, sha256 of the jsonl AND of the parquet, the paths, and the
  command that produced it. The manifest is what git carries; the bytes live on
  disk and in whatever backup the owner chooses;
* the Parquet is LOSSLESS: every line is stored verbatim (as bytes) with its
  line number, so `b"\\n".join(lines)` reproduces the jsonl byte for byte, and
  the archive REFUSES unless that round trip reproduces the jsonl's sha256;
* the jsonl is NOT deleted (that is the owner's call, later). It is marked
  `archived: true` in the manifest, and the writers that file rows by month
  refuse to append to an archived month (`is_archived`), so the manifest's
  sha256 stays true;
* the sealed-month guard accepts a manifest whose recorded size matches the
  file on disk as "sealed" -- the month is accounted for without a 178 MB blob.

What it does NOT do: rewrite git history. The 178 MB file was never committed
(it is gitignored by `llm_calls_[0-9]...jsonl`), so there is nothing in history
to remove. The 62-65 MB pre-rotation monoliths ARE in history; removing them
would need a history rewrite, which is roadmap decision D10 = no.

THE OPEN MONTH IS NEVER TOUCHED
===============================
A month is closed when it is strictly earlier than the CURRENT UTC month by the
run clock. The file's mtime is never consulted -- a fresh checkout writes every
file "today" (protocol item 7).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend import config as _config  # noqa: E402

OPT = Path(_config.OPTIMUS_LEDGER_DIR)
#: Committed: one small JSON per archived month.
MANIFEST_DIR = OPT / "ledger_manifests"
#: NOT committed (`*.parquet` is ignored repo-wide): the archived bytes.
ARCHIVE_DIR = OPT / "ledger_archive"
#: Only months at least this large are archived by `--apply` without `--ledger`.
MIN_BYTES = int(getattr(_config, "LEDGER_ARCHIVE_MIN_BYTES", 50 * 1024 * 1024))

SCHEMA_VERSION = "ledger_manifest/1"
MONTH_FILE = re.compile(r"^(?P<stem>.+)_(?P<month>\d{4}-(?:0[1-9]|1[0-2]))\.jsonl$")
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}")
#: Fields a row's own stamp may live in, in order of preference.
STAMP_FIELDS = ("ts", "utc", "timestamp", "created_at", "observed_at_utc", "date")
#: Growing tracked ledgers this module must never treat as archivable.
NEVER = ("predictions.jsonl",)


class ArchiveRefused(RuntimeError):
    """A refusal, with the reason in the message. Nothing was written."""


class ArchivedMonthRefused(ArchiveRefused):
    """A writer tried to append to a month that has an archive manifest."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_month_file(path: Path) -> Optional[tuple[str, str]]:
    """`(stem, YYYY-MM)` for `<stem>_<YYYY-MM>.jsonl`, else None."""
    m = MONTH_FILE.match(Path(path).name)
    return (m.group("stem"), m.group("month")) if m else None


def manifest_path(path: Path, manifest_dir: Path | None = None) -> Path:
    parsed = parse_month_file(path)
    if parsed is None:
        raise ArchiveRefused(f"{Path(path).name} is not a <ledger>_<YYYY-MM>.jsonl month file")
    stem, month = parsed
    return Path(manifest_dir or MANIFEST_DIR) / f"{stem}_{month}.json"


def manifest_for(path: Path, manifest_dir: Path | None = None) -> Optional[dict]:
    """The archive manifest for exactly THIS file, or None.

    Matched on the recorded path, not only the name: a test ledger in a temp
    directory called `llm_calls_2026-09.jsonl` is not the archived one."""
    if parse_month_file(path) is None:
        return None
    mp = manifest_path(path, manifest_dir)
    if not mp.exists():
        return None
    try:
        man = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not man.get("archived"):
        return None
    if (man.get("jsonl") or {}).get("path") != _rel(Path(path)):
        return None
    return man


def is_archived(path: Path, manifest_dir: Path | None = None) -> bool:
    """True when a writer must NOT append to `path` (its month is archived).

    One `stat` when there is no manifest, so it is cheap enough to ask on every
    append."""
    return manifest_for(path, manifest_dir) is not None


def refuse_if_archived(path: Path, manifest_dir: Path | None = None) -> None:
    man = manifest_for(path, manifest_dir)
    if man is not None:
        raise ArchivedMonthRefused(
            f"{Path(path).name} is an ARCHIVED closed month (manifest "
            f"{_rel(manifest_path(path, manifest_dir))}, sha256 "
            f"{man['jsonl']['sha256'][:12]}...). Appending would make the "
            f"manifest false; nothing was written.")


def git_status(path: Path) -> str:
    """tracked / ignored / untracked / outside_repo / unknown."""
    rel = _rel(path)
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        return "outside_repo"
    try:
        r = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=str(REPO),
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return "tracked"
        r = subprocess.run(["git", "check-ignore", "-q", "--", rel], cwd=str(REPO),
                           capture_output=True, text=True, timeout=30)
        return "ignored" if r.returncode == 0 else "untracked"
    except Exception:                                              # noqa: BLE001
        return "unknown"


def _stamp_of(row: Any) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(row, dict):
        return None, None
    for f in STAMP_FIELDS:
        v = row.get(f)
        if isinstance(v, str) and _STAMP.match(v):
            return v, f
    return None, None


def _split_lines(raw: bytes) -> tuple[list[bytes], bool]:
    lines = raw.split(b"\n")
    trailing = bool(lines) and lines[-1] == b""
    if trailing:
        lines = lines[:-1]
    return lines, trailing


def _join_lines(lines: list[bytes], trailing: bool) -> bytes:
    return b"\n".join(lines) + (b"\n" if trailing else b"")


def find_candidates(root: Path | None = None, *, min_bytes: int = MIN_BYTES,
                    now: datetime | None = None) -> list[dict]:
    """Every `<ledger>_<YYYY-MM>.jsonl` under `root` with its closed/open state.

    Closed = the month is strictly before the run clock's UTC month."""
    root = Path(root or OPT)
    current = f"{(now or _now()):%Y-%m}"
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git", "node_modules")]
        for name in filenames:
            parsed = parse_month_file(Path(name))
            if parsed is None or name in NEVER:
                continue
            p = Path(dirpath) / name
            size = p.stat().st_size
            stem, month = parsed
            out.append({"path": _rel(p), "ledger": stem, "month": month, "bytes": size,
                        "closed": month < current, "over_floor": size >= min_bytes,
                        "archived": manifest_for(p) is not None})
    return sorted(out, key=lambda r: -r["bytes"])


def archive_month(path: Path, *, now: datetime | None = None,
                  archive_dir: Path | None = None, manifest_dir: Path | None = None,
                  apply: bool = True, command: str | None = None) -> dict:
    """Convert one CLOSED month file to Parquet and write its manifest.

    Refuses (ArchiveRefused) on: not a month file, the open month, a protected
    ledger, a manifest that disagrees with the file, or a failed round trip."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(path)
    if path.name in NEVER:
        raise ArchiveRefused(f"{path.name} is a growing tracked ledger; never archived here")
    parsed = parse_month_file(path)
    if parsed is None:
        raise ArchiveRefused(f"{path.name} is not a <ledger>_<YYYY-MM>.jsonl month file")
    if not path.exists():
        raise ArchiveRefused(f"{_rel(path)} does not exist")
    stem, month = parsed
    run = now or _now()
    current = f"{run:%Y-%m}"
    if month >= current:
        raise ArchiveRefused(f"{path.name} is month {month}; the run clock's month is "
                             f"{current}. The open month is never archived.")

    mdir = Path(manifest_dir or MANIFEST_DIR)
    adir = Path(archive_dir or ARCHIVE_DIR)
    mpath = manifest_path(path, mdir)
    raw = path.read_bytes()
    jsonl_sha = hashlib.sha256(raw).hexdigest()

    if mpath.exists():
        prior = json.loads(mpath.read_text(encoding="utf-8"))
        if (prior.get("jsonl") or {}).get("sha256") == jsonl_sha:
            return {**prior, "action": "identical", "manifest_path": _rel(mpath)}
        raise ArchiveRefused(
            f"{_rel(mpath)} records sha256 {str((prior.get('jsonl') or {}).get('sha256'))[:12]} "
            f"but {path.name} now hashes to {jsonl_sha[:12]}: a CLOSED month changed after it "
            f"was archived. Nothing rewritten; investigate before re-archiving.")

    lines, trailing = _split_lines(raw)
    stamps: list[Optional[str]] = []
    keys: Counter = Counter()
    stamp_fields: Counter = Counter()
    unparseable = 0
    outside_month = 0
    for ln in lines:
        try:
            row = json.loads(ln)
        except (json.JSONDecodeError, UnicodeDecodeError):
            row = None
            unparseable += 1
        if isinstance(row, dict):
            keys.update(row.keys())
        s, f = _stamp_of(row)
        stamps.append(s)
        if f:
            stamp_fields[f] += 1
            if s[:7] != month:
                outside_month += 1
    dated = [s for s in stamps if s]

    table = pa.table({
        "line_no": pa.array(range(1, len(lines) + 1), type=pa.int64()),
        "stamp": pa.array(stamps, type=pa.string()),
        "line": pa.array(lines, type=pa.binary()),
    })
    table = table.replace_schema_metadata({
        b"source_sha256": jsonl_sha.encode(), b"trailing_newline": str(trailing).encode(),
        b"ledger": stem.encode(), b"month": month.encode()})

    pq_path = adir / f"{stem}_{month}.parquet"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "ledger": stem, "month": month, "archived": True,
        "archived_at_utc": run.isoformat(timespec="seconds"),
        "dated_by": "each row's own stamp and the run clock; never a file mtime",
        "jsonl": {"path": _rel(path), "bytes": len(raw), "sha256": jsonl_sha,
                  "rows": len(lines), "rows_unparseable": unparseable,
                  "trailing_newline": trailing, "git_status": git_status(path),
                  "deleted": False},
        "parquet": {"path": _rel(pq_path), "rows": table.num_rows,
                    "schema": [{"name": f.name, "type": str(f.type)} for f in table.schema],
                    "compression": "zstd",
                    "layout": "one row per jsonl line, verbatim bytes; "
                              "b'\\n'.join(line) (+ trailing newline) == the jsonl"},
        "row_schema": {"stamp_field": stamp_fields.most_common(1)[0][0] if stamp_fields else None,
                       "top_level_keys": dict(keys.most_common())},
        "first_ts": next((s for s in stamps if s), None),
        "last_ts": next((s for s in reversed(stamps) if s), None),
        "min_ts": min(dated) if dated else None,
        "max_ts": max(dated) if dated else None,
        "rows_stamped_outside_month": outside_month,
        "command": command or f"python -m backend.services.ledger_archive --ledger {_rel(path)} --apply",
        "writers_refuse_appends": True,
        "note": ("The jsonl is kept. Deleting it is the owner's decision; the parquet "
                 "reproduces it byte for byte (verified at archive time)."),
    }
    if not apply:
        return {**manifest, "action": "would_archive", "manifest_path": _rel(mpath)}

    adir.mkdir(parents=True, exist_ok=True)
    tmp = pq_path.with_suffix(".parquet.tmp")
    pq.write_table(table, tmp, compression="zstd")
    back = pq.read_table(tmp, columns=["line"]).column("line").to_pylist()
    if hashlib.sha256(_join_lines(back, trailing)).hexdigest() != jsonl_sha:
        tmp.unlink(missing_ok=True)
        raise ArchiveRefused(f"round trip of {path.name} through parquet did not reproduce "
                             f"its sha256; nothing kept")
    os.replace(tmp, pq_path)
    manifest["parquet"]["bytes"] = pq_path.stat().st_size
    manifest["parquet"]["sha256"] = _sha256_file(pq_path)
    manifest["round_trip_verified"] = True

    mdir.mkdir(parents=True, exist_ok=True)
    mtmp = mpath.with_suffix(".json.tmp")
    mtmp.write_text(json.dumps(manifest, indent=1), encoding="utf-8", newline="\n")
    os.replace(mtmp, mpath)
    return {**manifest, "action": "archived", "manifest_path": _rel(mpath)}


def restore_bytes(manifest: dict, *, archive_path: Path | None = None) -> bytes:
    """Rebuild the jsonl bytes from the parquet and check them against the manifest."""
    import pyarrow.parquet as pq

    p = Path(archive_path) if archive_path else REPO / manifest["parquet"]["path"]
    lines = pq.read_table(p, columns=["line"]).column("line").to_pylist()
    data = _join_lines(lines, bool(manifest["jsonl"]["trailing_newline"]))
    if hashlib.sha256(data).hexdigest() != manifest["jsonl"]["sha256"]:
        raise ArchiveRefused(f"{p.name} does not reproduce the manifest's jsonl sha256")
    return data


def archive_closed(root: Path | None = None, *, min_bytes: int = MIN_BYTES,
                   apply: bool = True, now: datetime | None = None) -> dict:
    """Archive every closed month at or above the floor. Each refusal is a row."""
    rows = []
    for c in find_candidates(root, min_bytes=min_bytes, now=now):
        if not (c["closed"] and c["over_floor"]):
            continue
        try:
            r = archive_month(REPO / c["path"], now=now, apply=apply)
            rows.append({"path": c["path"], "action": r["action"],
                         "manifest": r.get("manifest_path"), "rows": r["jsonl"]["rows"],
                         "bytes": r["jsonl"]["bytes"],
                         "parquet_bytes": (r.get("parquet") or {}).get("bytes")})
        except ArchiveRefused as exc:
            rows.append({"path": c["path"], "action": "REFUSED", "why": str(exc)})
        except Exception as exc:                                   # noqa: BLE001
            rows.append({"path": c["path"], "action": "FAILED",
                         "why": f"{type(exc).__name__}: {str(exc)[:300]}"})
    return {"job": "ledger_archive", "utc": (now or _now()).isoformat(timespec="seconds"),
            "min_bytes": min_bytes, "apply": apply, "months": rows,
            "status": "REFUSED" if any(r["action"] in ("REFUSED", "FAILED") for r in rows) else "OK"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ledger_archive", description=__doc__.split("\n\n")[0])
    ap.add_argument("--scan", action="store_true", help="list month files; write nothing")
    ap.add_argument("--apply", action="store_true", help="write parquet + manifest")
    ap.add_argument("--ledger", default=None, help="one month file to archive")
    ap.add_argument("--min-mb", type=float, default=MIN_BYTES / (1024 * 1024))
    a = ap.parse_args(argv)
    floor = int(a.min_mb * 1024 * 1024)
    if a.scan or not (a.apply or a.ledger):
        print(json.dumps(find_candidates(min_bytes=floor), indent=1))
        return 0
    if a.ledger:
        try:
            r = archive_month(Path(a.ledger), apply=a.apply)
        except ArchiveRefused as exc:
            print(f"REFUSED: {exc}")
            return 2
        print(json.dumps(r, indent=1))
        return 0
    out = archive_closed(min_bytes=floor, apply=True)
    print(json.dumps(out, indent=1))
    return 2 if out["status"] != "OK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
