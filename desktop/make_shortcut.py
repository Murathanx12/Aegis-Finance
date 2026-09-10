"""Put an Aegis shortcut on the Windows desktop, pointing at the built .exe.

    python -m desktop.make_shortcut                    # after the PyInstaller build
    python -m desktop.make_shortcut --check            # say what it would do, change nothing
    python -m desktop.make_shortcut --remove

Murat, 2026-09-10: "once you are done with the .exe put it into my desktop with
the logo we have (white png)".

The icon is built from `frontend/public/logo.png` -- the white A-and-arrow on
transparent -- composited onto a dark rounded tile by `desktop/build_icon.py`.
Left bare, a white-on-transparent icon is invisible against a light wallpaper or
a light taskbar, which is a shortcut you cannot find.

This script REFUSES rather than guessing:

* it will not create a shortcut to an .exe that is not there (a shortcut to a
  missing target is a double-click that does nothing and explains nothing);
* it will not overwrite a shortcut whose target is something else without
  `--force`, because the desktop is the user's and a name collision is theirs
  to resolve.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.services import quiet_subprocess as qsp  # noqa: E402
DIST_EXE = REPO / "dist" / "AegisDesktop" / "AegisDesktop.exe"
ICON = REPO / "desktop" / "assets" / "aegis.ico"
SHORTCUT_NAME = "Aegis.lnk"


def desktop_dir() -> Path:
    """The real Desktop, which is not always `~/Desktop`.

    OneDrive redirects it, and so does any roaming profile; writing to
    `~/Desktop` on a redirected machine creates a folder nobody looks at. The
    registry's User Shell Folders is the authority, so ask it first.
    """
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
            with key:
                raw, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(os.path.expandvars(raw))
        except OSError:
            pass
    return Path.home() / "Desktop"


def create(target: Path, icon: Path, dest: Path, *, force: bool = False) -> dict:
    if not target.exists():
        return {"ok": False, "action": "refused",
                "reason": (f"no .exe at {target}. Build it first:\n"
                           f"    cd frontend && AEGIS_DESKTOP_BUILD=1 npx next build\n"
                           f"    python -m PyInstaller desktop/AegisDesktop.spec --noconfirm\n"
                           f"A shortcut to a missing target is a double-click that does nothing.")}
    if dest.exists() and not force:
        existing = _target_of(dest)
        if existing and Path(existing).resolve() == target.resolve():
            return {"ok": True, "action": "already_correct", "shortcut": str(dest),
                    "target": str(target)}
        return {"ok": False, "action": "refused",
                "reason": f"{dest} already exists and points at {existing!r}. Pass --force to replace it."}
    # PowerShell's WScript.Shell is the supported way to write a .lnk without a
    # third-party dependency in the frozen build's requirements.
    ps = (
        "$s = New-Object -ComObject WScript.Shell; "
        f"$l = $s.CreateShortcut('{dest}'); "
        f"$l.TargetPath = '{target}'; "
        f"$l.WorkingDirectory = '{target.parent}'; "
        f"$l.IconLocation = '{icon},0'; "
        "$l.Description = 'Aegis - local research desktop'; "
        "$l.Save()"
    )
    r = qsp.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=60)
    if r.returncode != 0 or not dest.exists():
        return {"ok": False, "action": "failed", "reason": (r.stderr or r.stdout or "").strip()[:400]}
    return {"ok": True, "action": "created", "shortcut": str(dest), "target": str(target),
            "icon": str(icon)}


def _target_of(lnk: Path) -> str | None:
    ps = ("$s = New-Object -ComObject WScript.Shell; "
          f"$s.CreateShortcut('{lnk}').TargetPath")
    try:
        r = qsp.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                    capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout or "").strip() or None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="desktop shortcut for Aegis")
    ap.add_argument("--exe", default=str(DIST_EXE))
    ap.add_argument("--icon", default=str(ICON))
    ap.add_argument("--name", default=SHORTCUT_NAME)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true", help="report, change nothing")
    ap.add_argument("--remove", action="store_true")
    a = ap.parse_args(argv)

    dest = desktop_dir() / a.name
    target, icon = Path(a.exe), Path(a.icon)

    if a.remove:
        existed = dest.exists()
        dest.unlink(missing_ok=True)
        print(f"{'removed' if existed else 'nothing to remove at'} {dest}")
        return 0
    if a.check:
        print(f"desktop      : {desktop_dir()}")
        print(f"shortcut     : {dest} ({'exists -> ' + str(_target_of(dest)) if dest.exists() else 'absent'})")
        print(f"target .exe  : {target} ({'present' if target.exists() else 'MISSING'})")
        print(f"icon         : {icon} ({'present' if icon.exists() else 'MISSING'})")
        return 0

    out = create(target, icon, dest, force=a.force)
    print(f"{out['action']}: {out.get('shortcut') or out.get('reason')}")
    if out.get("reason") and not out["ok"]:
        print(out["reason"])
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
