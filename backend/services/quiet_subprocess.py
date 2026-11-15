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

__all__ = ["CREATE_NO_WINDOW", "NEW_PROCESS_GROUP", "run", "popen", "hidden_flags",
           "install_windowless_default", "process_is_windowless"]

#: 0 on POSIX, where the whole problem does not exist.
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
NEW_PROCESS_GROUP: int = (getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                          if sys.platform == "win32" else 0)


def hidden_flags(extra: int = 0) -> int:
    """`creationflags` that keep a child off the screen, plus anything else."""
    return CREATE_NO_WINDOW | extra


#: Flags that mean the caller chose its own console arrangement; the default leaves them alone.
_OWN_CONSOLE: int = 0x00000008 | 0x00000010          # DETACHED_PROCESS | CREATE_NEW_CONSOLE


def process_is_windowless() -> bool:
    """True for a `pythonw.exe` task or a frozen GUI build: a process with no console."""
    exe = (sys.executable or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return sys.platform == "win32" and (sys.stdout is None or exe == "pythonw.exe")


def install_windowless_default(force: bool = False) -> bool:
    """Make EVERY `subprocess.Popen` of a windowless process start without a window.

    Murat, 2026-11-15: *"PowerShells and CMDs pop up several times a minute, over my game"*.
    Measured the same day by sampling visible console windows: `pythonw -m
    scripts.system_status` (every 15 minutes) started `powershell`, `schtasks`, `gh` and `git`
    through `subprocess.run` with no `creationflags`. A windowless parent has no console to
    lend, so Windows allocated one per child, and with Windows Terminal as the default host
    each appeared as a Terminal window IN THE FOREGROUND. The per-call wrappers above had been
    the rule since 09-10 and 114 call sites did not use them; a rule that is easy to forget on
    the next call site belongs in one place.

    Idempotent. Does nothing in a process that has a console (a shell, pytest, CI), so what a
    developer sees does not change. A caller that passes DETACHED_PROCESS or
    CREATE_NEW_CONSOLE keeps exactly what it asked for. Returns whether the default is active.
    """
    if getattr(subprocess.Popen, "_aegis_windowless_default", False):
        return True
    if not (force or process_is_windowless()):
        return False
    original = subprocess.Popen.__init__

    def __init__(self: subprocess.Popen, *args: Any, **kw: Any) -> None:
        flags = int(kw.get("creationflags") or 0)
        if not flags & _OWN_CONSOLE:
            kw["creationflags"] = flags | CREATE_NO_WINDOW
        original(self, *args, **kw)

    subprocess.Popen.__init__ = __init__                  # type: ignore[method-assign]
    subprocess.Popen._aegis_windowless_default = True     # type: ignore[attr-defined]
    return True


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
