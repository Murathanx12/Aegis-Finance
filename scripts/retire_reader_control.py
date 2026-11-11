"""Retire the separate "Aegis Reader" desktop shortcut (CH-22b, 2026-11-11).

    python -m scripts.retire_reader_control            # dry run: say what it would do
    python -m scripts.retire_reader_control --apply    # move the shortcut aside

Owner, 2026-11-11: "join that controller in the desktop to the exe, no need for
multiple controllers." The reader's ON/OFF switch now lives in the AegisDesktop
app (Reader tab, `/api/control/reader*`). This moves `Aegis Reader.lnk` off the
desktop into an evidence folder so there is one controller to click.

It MOVES, never deletes; it refuses when the shortcut points at anything other
than `AegisReaderControl.exe` or when the destination already holds a file. It
does NOT delete the old program folder and does NOT touch any scheduled task --
it prints what still points at the old controller so a human can decide.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path, PureWindowsPath

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from desktop.make_shortcut import _target_of, desktop_dir  # noqa: E402

SHORTCUT_NAME = "Aegis Reader.lnk"
EXPECTED_EXE = "AegisReaderControl.exe"
DEFAULT_DEST = Path.home() / "aegis-recovery-evidence" / "s65-retired-reader-control-20261111"


def plan(*, desktop: Path | None = None, dest_dir: Path | None = None,
         target_of=_target_of) -> dict:
    """PURE apart from reads: what `--apply` would do, or why it refuses."""
    desktop = desktop or desktop_dir()
    dest_dir = dest_dir or DEFAULT_DEST
    src = desktop / SHORTCUT_NAME
    dst = dest_dir / SHORTCUT_NAME
    out: dict = {"shortcut": str(src), "destination": str(dst), "action": None, "why": None}
    if not src.exists():
        out.update(action="nothing", why="no such shortcut on the desktop (already retired?)")
        return out
    target = target_of(src)
    out["shortcut_target"] = target
    # a .lnk target is a Windows path; PureWindowsPath parses it the same on
    # every OS (Path() on Linux would treat the backslashes as one file name)
    if not target or PureWindowsPath(target).name.lower() != EXPECTED_EXE.lower():
        out.update(action="refuse", why=f"the shortcut points at {target!r}, not {EXPECTED_EXE}")
        return out
    if dst.exists():
        out.update(action="refuse", why=f"{dst} already exists; nothing is overwritten")
        return out
    out.update(action="move", why="the reader switch now lives in the AegisDesktop app")
    return out


def apply(p: dict) -> dict:
    if p["action"] != "move":
        return {**p, "applied": False}
    dst = Path(p["destination"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(p["shortcut"], str(dst))
    ok = dst.exists() and not Path(p["shortcut"]).exists()
    return {**p, "applied": ok}


def still_pointing_at_the_old_controller() -> list[str]:
    """Read-only notes for the human: the scheduled task and the old exe folder."""
    notes = []
    old = Path.home() / "AppData" / "Local" / "Programs" / "AegisReaderControl"
    if old.exists():
        notes.append(f"the old program folder stays at {old} (not deleted)")
    notes.append("the scheduled task AegisReaderSupervisor is NOT changed by this script; on "
                 "2026-11-11 its action ran the retired attested wrapper "
                 "(clean_reader_action.py), which refuses. Repointing it at "
                 "`-m scripts.task_keeper reader` is a separate, attended step.")
    return notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="the default: change nothing")
    g.add_argument("--apply", action="store_true", help="move the shortcut aside")
    ap.add_argument("--dest", type=Path, default=None)
    a = ap.parse_args(argv)
    p = plan(dest_dir=a.dest)
    out = apply(p) if a.apply else {**p, "applied": False, "dry_run": True}
    out["notes"] = still_pointing_at_the_old_controller()
    print(json.dumps(out, indent=1))
    if out["action"] == "refuse":
        return 2
    if a.apply and out["action"] == "move" and not out["applied"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
