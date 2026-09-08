"""H5 -- a READ-ONLY mirror of the execution repo's `state/`, for the website.

    from backend.services import terminal_state_reader as tsr

    tsr.sync()                 # copy the whitelisted artefacts INTO the mirror
    tsr.inventory()            # what the mirror holds, and how old it is
    tsr.read("autopsies", "2026-09-04.json")

THE GAP THIS CLOSES
===================
`aegis-alpha-terminal/state/` holds every seal, fill, refusal, autopsy and
learning report the fleet has produced, and **the website has never been able to
see any of it** (grounding report A.5 gap 9). The Docker backend runs from an
image that has never contained that repository, and H1's candidate surface
already degrades to `NOT_REACHABLE` on the tracker legs for exactly this reason.

WHY A SYNC AND NOT AN API
=========================
The obvious fix is an HTTP endpoint in the execution repo. H5 forbids it, and
the reason is not tidiness: the execution repo is the one that can place orders.
Every port it opens is a surface on the process that holds the broker client, and
"a read-only endpoint" is one refactor away from not being one. A one-directional
file copy has no such failure mode -- there is no request the website can make
that the execution repo will answer, because nothing over there is listening.

DIRECTIONALITY IS THE WHOLE PROPERTY, AND IT IS PROVEN THREE WAYS
=================================================================
1. **Every source handle is opened for read.** `_copy_file` reads bytes and
   writes them under `TERMINAL_MIRROR_DIR`; nothing in this module opens a path
   under `TERMINAL_STATE_DIR` for anything else. AST-scanned by
   `test_terminal_state_reader.py::TestReadOnly`.
2. **Every destination is re-anchored and checked.** `_dest_for` resolves the
   candidate path and refuses it unless it is *inside* the mirror. A `..` in an
   artefact name therefore cannot walk back into the source tree -- and the test
   plants one.
3. **The source tree is fingerprinted before and after.** The runtime test hashes
   every file in a temporary source tree, runs `sync()`, and asserts the file
   list, the sizes and the SHA-256s are all identical. That is the assertion that
   would fail if a future edit made this module write upstream, and it does not
   depend on anyone re-reading the docstring.

WHAT IS MIRRORED, AND WHY NOT ALL OF IT
=======================================
`state/` is **2.4 GB**, most of it logs, caches and 16 MB of prediction books.
`config.TERMINAL_MIRROR_ARTEFACTS` is a whitelist of the five families H5 names --
seals, fills, refusals, autopsies, learning reports -- plus contracts and the
opportunity-recall ledger, which the decision-log page reads. A directory that is
not on the list is not copied, and the receipt counts what it skipped: a mirror
that silently omits something is worse than one that omits it loudly.

A file over `config.TERMINAL_MIRROR_MAX_BYTES` is **tail-truncated** if it is
line-oriented (`.jsonl`) and **skipped** if it is a single JSON blob, and the
receipt says which happened per file. Half a JSON document is not a smaller JSON
document.

NOTHING HERE PLACES AN ORDER, and this module imports no broker, no `alpha`
package and no network client.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from backend.config import (HUMAN_LOOP_VERSION, TERMINAL_MIRROR_ARTEFACTS,
                            TERMINAL_MIRROR_DIR, TERMINAL_MIRROR_MAX_BYTES,
                            TERMINAL_STATE_DIR)

logger = logging.getLogger(__name__)

MIRROR_MANIFEST = "MANIFEST.json"

#: Kinds a caller may ask for, derived from the whitelist so the two cannot
#: disagree.
KINDS = tuple(sorted({kind for _, kind, _ in TERMINAL_MIRROR_ARTEFACTS}))


class MirrorRefused(RuntimeError):
    """The mirror could not be built, or a request pointed outside it.

    A refusal, never a quiet empty directory: an empty mirror and an unreachable
    execution repo look identical from a web page and mean opposite things.
    """


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _dest_for(mirror: Path, kind: str, name: str) -> Path:
    """A path INSIDE the mirror, or a refusal.

    `Path.resolve()` then a containment check. A name carrying `..` resolves
    outside and is refused here -- which is the only place a copy could ever
    have escaped toward the source tree.
    """
    root = Path(mirror).resolve()
    cand = (root / kind / name).resolve()
    try:
        cand.relative_to(root)
    except ValueError as exc:
        raise MirrorRefused(
            f"destination {cand} is outside the mirror root {root}. A mirror "
            "that can write outside itself is not a mirror.") from exc
    return cand


def _copy_file(src: Path, dst: Path, *, max_bytes: int) -> dict:
    """Copy one file, READ-ONLY on the source side. Returns its manifest row."""
    size = src.stat().st_size
    truncated = False
    #: 'rb' is the ONLY mode this module ever opens a source path with.
    data = src.read_bytes()
    if size > max_bytes:
        if src.suffix == ".jsonl":
            lines = data.splitlines(keepends=True)
            kept: list[bytes] = []
            total = 0
            for line in reversed(lines):
                total += len(line)
                if total > max_bytes:
                    break
                kept.append(line)
            data = b"".join(reversed(kept))
            truncated = True
        else:
            return {"file": src.name, "copied": False, "bytes": size,
                    "reason": (f"{size} bytes exceeds the {max_bytes}-byte "
                               "ceiling and this is a single JSON document; "
                               "half a JSON document is not a smaller one")}
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    return {"file": src.name, "copied": True, "bytes": len(data),
            "source_bytes": size, "truncated_from_tail": truncated,
            "sha256": _sha256(data),
            "source_sha256": _sha256(src.read_bytes()) if not truncated else None,
            "source_mtime_utc": datetime.fromtimestamp(
                src.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
            "reason": None}


def sync(*, source: Path | None = None, mirror: Path | None = None,
         max_bytes: int | None = None) -> dict:
    """Copy the whitelisted artefacts into the mirror. Returns a receipt.

    Refuses rather than degrading when the execution repo is not on this
    machine, and refuses if source and mirror are the same tree.
    """
    src_root = Path(source or TERMINAL_STATE_DIR)
    dst_root = Path(mirror or TERMINAL_MIRROR_DIR)
    cap = int(max_bytes if max_bytes is not None else TERMINAL_MIRROR_MAX_BYTES)

    if not src_root.exists():
        raise MirrorRefused(
            f"the execution repo's state directory is not on this machine "
            f"({src_root}). Set AEGIS_TERMINAL_STATE_DIR, or accept that the "
            "mirror is UNREACHABLE -- which is a different fact from an empty "
            "mirror and must not be reported as one.")
    if src_root.resolve() == dst_root.resolve():
        raise MirrorRefused(
            "source and mirror resolve to the same directory. A sync onto "
            "itself is the one shape in which this module could write upstream.")

    started = _now()
    artefacts: dict[str, list[dict]] = {}
    skipped: list[dict] = []
    n_files = n_bytes = 0

    for rel, kind, keep in TERMINAL_MIRROR_ARTEFACTS:
        src = src_root / rel
        rows: list[dict] = []
        if not src.exists():
            skipped.append({"artefact": rel, "kind": kind,
                            "reason": "absent in the execution repo"})
            artefacts.setdefault(kind, [])
            continue
        if src.is_file():
            files = [src]
        else:
            files = sorted([p for p in src.iterdir() if p.is_file()],
                           key=lambda p: p.name, reverse=True)[:int(keep)]
            if not files:
                skipped.append({"artefact": rel, "kind": kind,
                                "reason": "directory exists and is empty"})
        for f in files:
            dst = _dest_for(dst_root, kind, f.name)
            row = _copy_file(f, dst, max_bytes=cap)
            row["artefact"] = rel
            rows.append(row)
            if row["copied"]:
                n_files += 1
                n_bytes += int(row["bytes"])
            else:
                skipped.append({"artefact": rel, "kind": kind,
                                "file": f.name, "reason": row["reason"]})
        artefacts.setdefault(kind, []).extend(rows)

    receipt = {
        "version": HUMAN_LOOP_VERSION,
        "mirror": "terminal_state_mirror_v1",
        "authority": ("READ_ONLY, ONE DIRECTION. This process reads the "
                      "execution repo and writes only inside the mirror. It "
                      "opens no port over there, and the execution repo answers "
                      "no request from here."),
        "source": str(src_root), "mirror_dir": str(dst_root),
        "started_utc": started, "finished_utc": _now(),
        "n_files": n_files, "n_bytes": n_bytes,
        "n_skipped": len(skipped), "skipped": skipped,
        "kinds": {k: len([r for r in v if r.get("copied")])
                  for k, v in artefacts.items()},
        "artefacts": artefacts,
        "whitelist": [{"path": r, "kind": k, "keep": n}
                      for r, k, n in TERMINAL_MIRROR_ARTEFACTS],
        "not_mirrored_note": (
            "state/ is ~2.4 GB. Everything outside the whitelist above -- logs, "
            "caches, 16 MB of prediction books, the 18 MB decisions ledger -- is "
            "deliberately not copied. This list is the definition of what the "
            "website can see."),
        "max_bytes": cap,
    }
    dst_root.mkdir(parents=True, exist_ok=True)
    (dst_root / MIRROR_MANIFEST).write_text(
        json.dumps(receipt, indent=1, sort_keys=True), encoding="utf-8")
    return receipt


def manifest(*, mirror: Path | None = None) -> dict | None:
    p = Path(mirror or TERMINAL_MIRROR_DIR) / MIRROR_MANIFEST
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def inventory(*, mirror: Path | None = None) -> dict:
    """What the mirror holds right now, and whether it has ever been built.

    Never returns an empty list to mean "unreachable". `status` is one of
    `OK`, `NEVER_SYNCED`, `SOURCE_UNREACHABLE`.
    """
    root = Path(mirror or TERMINAL_MIRROR_DIR)
    man = manifest(mirror=root)
    src_present = Path(TERMINAL_STATE_DIR).exists()
    if man is None:
        return {
            "version": HUMAN_LOOP_VERSION,
            "status": "NEVER_SYNCED",
            "mirror_dir": str(root),
            "source_present_on_this_machine": src_present,
            "kinds": {k: [] for k in KINDS},
            "reason": (
                "the mirror has never been built on this machine. This is NOT "
                "an empty execution repo. Run "
                "`python -m backend.services.terminal_state_reader --sync`"
                + ("" if src_present else
                   f", but note {TERMINAL_STATE_DIR} is not present here either")
                + "."),
            "how_to_refresh": "python -m backend.services.terminal_state_reader --sync",
        }
    kinds: dict[str, list] = {}
    for kind in KINDS:
        d = root / kind
        kinds[kind] = ([{"file": p.name, "bytes": p.stat().st_size}
                        for p in sorted(d.iterdir()) if p.is_file()]
                       if d.exists() else [])
    return {
        "version": HUMAN_LOOP_VERSION,
        "status": "OK" if src_present else "SOURCE_UNREACHABLE",
        "mirror_dir": str(root),
        "source_present_on_this_machine": src_present,
        "synced_at_utc": man.get("finished_utc"),
        "n_files": man.get("n_files"), "n_bytes": man.get("n_bytes"),
        "n_skipped": man.get("n_skipped"), "skipped": man.get("skipped"),
        "authority": man.get("authority"),
        "not_mirrored_note": man.get("not_mirrored_note"),
        "kinds": kinds,
        "how_to_refresh": "python -m backend.services.terminal_state_reader --sync",
    }


def read(kind: str, name: str, *, mirror: Path | None = None) -> dict:
    """One mirrored artefact, parsed. Refuses an unknown kind or a stray name."""
    if kind not in KINDS:
        raise MirrorRefused(f"unknown kind {kind!r}; declared: {list(KINDS)}")
    if os.sep in name or "/" in name or name in ("", ".", ".."):
        raise MirrorRefused(
            f"{name!r} is not a bare file name. Path separators are refused "
            "here rather than resolved.")
    root = Path(mirror or TERMINAL_MIRROR_DIR)
    p = _dest_for(root, kind, name)
    if not p.exists():
        raise MirrorRefused(
            f"{kind}/{name} is not in the mirror. Either it was never synced or "
            "it is outside the whitelist; `inventory()` says which.")
    raw = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix == ".jsonl":
        rows, bad = [], 0
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
        return {"kind": kind, "name": name, "format": "jsonl",
                "n_rows": len(rows), "n_unparseable": bad, "rows": rows}
    try:
        return {"kind": kind, "name": name, "format": "json",
                "content": json.loads(raw)}
    except json.JSONDecodeError as exc:
        raise MirrorRefused(f"{kind}/{name} did not parse as JSON: {exc}") from exc


def main(argv: list[str] | None = None) -> int:            # pragma: no cover
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sync", action="store_true", help="build/refresh the mirror")
    args = ap.parse_args(argv)
    if args.sync:
        r = sync()
        print(json.dumps({k: v for k, v in r.items() if k != "artefacts"},
                         indent=1))
        return 0
    print(json.dumps(inventory(), indent=1, default=str))
    return 0


if __name__ == "__main__":                                 # pragma: no cover
    raise SystemExit(main())
