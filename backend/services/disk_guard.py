"""A full disk refuses by name and leaves the OLD file.

WHY THIS EXISTS (2026-09-27, `docs/HANDOFF_2026-09-26_WAVE2_THE_REVIEW_LOOP_CLOSED_FOUR_IDEAS.md` §20)
===================================================================================================
C: reached 0 bytes free for about 85 minutes. The lab died, the reader
stopped, a crawl lost its checkpoint and **13 receipts were truncated to zero
bytes** -- `write_text` opens the target with `"w"` (truncating it) BEFORE it
knows whether the bytes will fit, so a full disk replaced a good receipt with
an empty one. Nothing went red until agents tripped over it.

Two tools, both small:

* ``require_free(gb, what)`` -- a start-up refusal. A run that cannot finish
  its receipts must not start; it raises ``DiskTooFull`` naming the run, the
  volume and the measured free space. A volume whose free space cannot be
  MEASURED also refuses: an unmeasured disk is not a disk with room.
* ``atomic_write_json(path, obj)`` / ``atomic_write_text(path, text)`` --
  write a sibling temp file, flush + fsync, check the temp is non-empty and
  (for JSON) re-parses, then ``os.replace`` it over the target. On a full disk
  the write fails on the TEMP, the temp is removed, and the old file is still
  there, whole. Raises ``DiskTooFull`` on ENOSPC, so the caller's log names it.
"""

from __future__ import annotations

import errno
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Optional

GB = 1024 ** 3

#: Injectable for tests (a fake `disk_usage` / a fake `open`); production reads
#: the real volume and the real file system.
_disk_usage: Callable[[str], Any] = shutil.disk_usage
_open = open


class DiskTooFull(OSError, RuntimeError):
    """A named refusal: the volume has less free space than the run needs, its
    free space could not be measured, or a write ran out of space midway.

    An ``OSError`` too, so every existing ``except OSError`` around a write
    (the lab's exit hook, the reader's receipts) still catches it: converting a
    writer to the atomic one must not turn a handled failure into a crash."""


def _existing_anchor(path: Path) -> Path:
    """The nearest existing ancestor (a receipt dir may not exist yet)."""
    p = Path(path).resolve()
    for cand in (p, *p.parents):
        if cand.exists():
            return cand
    return Path(p.anchor or ".")


def volume_of(path: Path) -> str:
    """`C:\\` on Windows, the mount-ish root elsewhere (printed, not used to decide)."""
    return Path(path).resolve().anchor or str(path)


def measure(path: Optional[Path] = None, *,
            disk_usage: Optional[Callable[[str], Any]] = None) -> dict:
    """Free/total bytes on the volume holding `path` (default: the ledger dir).

    Raises ``DiskTooFull`` when the volume cannot be measured -- the caller that
    wants a soft answer catches it; a start-up guard lets it refuse."""
    if path is None:
        from backend import config as C                            # noqa: PLC0415
        path = Path(C.OPTIMUS_LEDGER_DIR)
    du = disk_usage or _disk_usage
    anchor = _existing_anchor(Path(path))
    try:
        u = du(str(anchor))
        free, total = int(u.free), int(u.total)
    except Exception as exc:                                        # noqa: BLE001
        raise DiskTooFull(
            f"cannot measure free space on the volume holding {path} "
            f"({type(exc).__name__}: {str(exc)[:120]}); an unmeasured disk is "
            f"not a disk with room") from exc
    return {"path": str(path), "volume": volume_of(anchor), "free_bytes": free,
            "total_bytes": total, "free_gb": round(free / GB, 2),
            "total_gb": round(total / GB, 1)}


def require_free(gb: float, what: str, *, path: Optional[Path] = None,
                 disk_usage: Optional[Callable[[str], Any]] = None) -> dict:
    """Refuse (``DiskTooFull``) unless the volume holding `path` has `gb` free.

    Returns the measurement when there is room, so a caller can print it."""
    m = measure(path, disk_usage=disk_usage)
    if m["free_bytes"] < float(gb) * GB:
        raise DiskTooFull(
            f"{what}: REFUSED -- {m['free_gb']:.2f} GB free on {m['volume']} "
            f"(< {float(gb):g} GB required). A run that cannot finish its "
            f"receipts must not start; free space first (see "
            f"docs/HEALTH_PROBES_2026-09-26.md, 'regenerable space').")
    return m


def _is_enospc(exc: BaseException) -> bool:
    return isinstance(exc, OSError) and getattr(exc, "errno", None) in (
        errno.ENOSPC, getattr(errno, "EDQUOT", -1))


def atomic_write_text(path: Path, text: str, *, check_json: bool = False,
                      encoding: str = "utf-8") -> Path:
    """Write `text` to `path` so that a failure leaves the OLD file whole.

    temp in the same directory -> write -> flush -> fsync -> non-empty check
    (-> re-parse when `check_json`) -> ``os.replace``. Any failure removes the
    temp and re-raises; ENOSPC re-raises as ``DiskTooFull`` naming the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    data = text.encode(encoding)
    if not data:
        raise DiskTooFull(f"refusing to write an EMPTY file over {path}")
    try:
        with _open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        size = os.path.getsize(tmp)
        if size != len(data) or size == 0:
            raise DiskTooFull(f"short write on {tmp.name}: {size} of {len(data)} bytes "
                              f"reached the disk; {path.name} left as it was")
        if check_json:
            with _open(tmp, "rb") as f:
                json.loads(f.read().decode(encoding))
        os.replace(tmp, path)
    except BaseException as exc:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        if _is_enospc(exc):
            raise DiskTooFull(f"disk full writing {path}: the old file (if any) "
                              f"is left as it was") from exc
        raise
    return path


def atomic_write_json(path: Path, obj: Any, *, indent: Optional[int] = 1,
                      ensure_ascii: bool = False, default: Any = str,
                      sort_keys: bool = False) -> Path:
    """`json.dumps(obj)` written with ``atomic_write_text`` and re-parsed first."""
    text = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii,
                      default=default, sort_keys=sort_keys)
    return atomic_write_text(path, text, check_json=True)


__all__ = ["DiskTooFull", "GB", "atomic_write_json", "atomic_write_text",
           "measure", "require_free", "volume_of"]
