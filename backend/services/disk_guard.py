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


# ───────────────────── cross-process file lock (2026-09-27) ─────────────────
#
# The Dow Jones reader can run as N worker processes (one per site) that share
# ONE throttle file, one `_search_seen.jsonl` and one corpus. A read-modify-
# write of a shared file must be exclusive across processes AND across threads
# of one process, or two workers read the same "last page load" and both take
# the same slot. `file_lock` holds an OS byte-range lock (msvcrt on Windows,
# fcntl on POSIX) on a sidecar `.lock` file plus a per-path threading lock.

import threading as _threading
import time as _time
from contextlib import contextmanager as _contextmanager

_THREAD_LOCKS: dict[str, Any] = {}
_THREAD_LOCKS_GUARD = _threading.Lock()
_HELD = _threading.local()


def _thread_lock_for(key: str) -> Any:
    with _THREAD_LOCKS_GUARD:
        lk = _THREAD_LOCKS.get(key)
        if lk is None:
            lk = _THREAD_LOCKS[key] = _threading.RLock()
        return lk


class FileLockTimeout(TimeoutError):
    """`file_lock` could not take the lock within its timeout. Named, never a
    silent pass: a shared file written WITHOUT the lock is the failure."""


@_contextmanager
def file_lock(path: Path, *, timeout_s: Optional[float] = None, poll_s: float = 0.05):
    """Exclusive lock on `path` (the lock FILE itself; callers pass a sidecar
    such as `<file>.lock`). Blocks, polling every `poll_s`, up to `timeout_s`
    (None = forever) and raises `FileLockTimeout` after. Re-entrant within one
    thread; exclusive across threads and processes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = str(path.resolve())
    held = getattr(_HELD, "keys", None)
    if held is None:
        held = _HELD.keys = {}
    if held.get(key):
        # re-entry from the thread that already holds it: a second OS lock on
        # a new handle would wait for ITSELF forever (Windows locks per handle)
        held[key] += 1
        try:
            yield path
        finally:
            held[key] -= 1
        return
    tl = _thread_lock_for(key)
    t0 = _time.monotonic()
    if not tl.acquire(timeout=-1 if timeout_s is None else max(0.0, timeout_s)):
        raise FileLockTimeout(f"thread lock on {path} not taken within {timeout_s} s")
    fd = None
    try:
        fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if timeout_s is not None and _time.monotonic() - t0 >= timeout_s:
                    raise FileLockTimeout(f"{path} is held by another process "
                                          f"(waited {timeout_s} s)")
                _time.sleep(poll_s)
        held[key] = 1
        try:
            yield path
        finally:
            held.pop(key, None)
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        if fd is not None:
            os.close(fd)
        tl.release()


def locked_append_line(path: Path, line: str, *, encoding: str = "utf-8") -> Path:
    """Append ONE line to a shared log under `file_lock(<path>.lock)`, so two
    writers never interleave half-lines. A full disk raises `DiskTooFull`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = line if line.endswith(chr(10)) else line + chr(10)
    with file_lock(path.with_name(path.name + ".lock")):
        try:
            with _open(path, "a", encoding=encoding) as fh:
                fh.write(text)
                fh.flush()
        except OSError as exc:
            if _is_enospc(exc):
                raise DiskTooFull(f"disk full appending to {path}") from exc
            raise
    return path


__all__ = ["DiskTooFull", "FileLockTimeout", "GB", "atomic_write_json", "atomic_write_text",
           "file_lock", "locked_append_line", "measure", "require_free", "volume_of"]
