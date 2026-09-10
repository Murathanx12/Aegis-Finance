"""Subprocess calls that do not flash a console window.

Murat, 2026-09-10, on the packaged app: *"random cmds popup and close"*.

The cause is not random. `AegisDesktop.exe` is built with `console=False`, so
the process has no console of its own -- and on Windows, launching a CONSOLE
subprocess from a process without one makes the OS allocate a **new console
window** for it. `netstat`, `tasklist`, `taskkill` and `nvidia-smi` are all
console programs, so each call painted a black window on screen and tore it down
milliseconds later.

Three of those run on the Services page's own poll (`llama_server.status()` calls
`pid_on_port` -> netstat, `pid_alive` -> tasklist, and `vram` -> nvidia-smi), and
the page polls every three seconds. That is three flashes every three seconds
for as long as the window is open.

`CREATE_NO_WINDOW` suppresses it. The flag is a per-call keyword that is easy to
add to nine call sites and just as easy to forget on the tenth, so it lives here
instead, and `test_desktop_control_surface.py` asserts that no module on the
desktop path calls `subprocess.run`/`Popen` directly.

Nothing here changes WHAT is run: same argv lists, same `shell=False`, same
kill-by-PID discipline. It only stops the window appearing.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

__all__ = ["CREATE_NO_WINDOW", "NEW_PROCESS_GROUP", "run", "popen", "hidden_flags"]

#: 0 on POSIX, where the whole problem does not exist.
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
NEW_PROCESS_GROUP: int = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                          if sys.platform == "win32" else 0)


def hidden_flags(extra: int = 0) -> int:
    """`creationflags` that keep a child off the screen, plus anything else."""
    return CREATE_NO_WINDOW | extra


def run(args: list[str], **kw: Any) -> subprocess.CompletedProcess:
    """`subprocess.run` with the window suppressed and `shell=False` enforced.

    `shell=True` is refused rather than silently overridden: a shell invocation
    in this codebase is a defect (the control router's authority tests exist to
    keep argv a list), and quietly flipping it would hide the mistake.
    """
    if kw.pop("shell", False):
        raise ValueError("shell=True is not permitted here; pass an argv list")
    kw.setdefault("creationflags", 0)
    kw["creationflags"] = hidden_flags(kw["creationflags"])
    return subprocess.run(args, shell=False, **kw)  # noqa: S603 - argv list, no shell


def popen(args: list[str], **kw: Any) -> subprocess.Popen:
    """`subprocess.Popen` with the window suppressed and `shell=False` enforced."""
    if kw.pop("shell", False):
        raise ValueError("shell=True is not permitted here; pass an argv list")
    kw.setdefault("creationflags", 0)
    kw["creationflags"] = hidden_flags(kw["creationflags"])
    return subprocess.Popen(args, shell=False, **kw)  # noqa: S603 - argv list, no shell
