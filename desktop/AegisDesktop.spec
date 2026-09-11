# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Aegis Desktop -- the LAUNCHER, not the app.

    python -m PyInstaller desktop/AegisDesktop.spec --noconfirm

WHAT CHANGED ON 2026-09-11, AND WHY THE FILE IS NOW SHORT
=========================================================
This spec used to freeze the whole backend: `backend/**` walked file by file,
the static frontend export, the vendored schema mirror, a size ceiling, an
eight-megabyte walker and a list of hidden imports for routers reached by
string. 1.1 GB of dist directory. It bought two things, and both were bad:

* **the app could not update itself** -- every change needed a rebuild; and
* **a path that resolves differently when frozen** became a defect FAMILY, six
  instances by 09-11: an empty database inside the bundle, the vendored schema
  dropped, the llama ownership note written where nothing could read it back (so
  a model server outlived the app with 5 GB mapped), `AEGIS_DATA_DIR` one level
  too deep, the frozen `-m` spawn, and `.env` invisible to `config.py` so the
  packaged app ran with NO API KEYS while looking perfectly healthy.

So the .exe is now `desktop/launcher.py` and its two stdlib-only companions. It
finds the checkout, pulls it, and runs `python -m desktop.aegis_desktop` under
the CHECKOUT'S interpreter. `backend/`, `scripts/`, `learner/`, the frontend
export and the data are read from the repository at runtime, as they always
were in practice. **Nothing that is not frozen can have a frozen-path defect.**

WHAT IS IN THE BUNDLE
* `desktop/launcher.py`, `desktop/_interp.py`, pywebview (for the one window the
  launcher can draw itself: the refusal page when no checkout is found).
* the icon.

WHAT IS NOT
* `backend/`, `scripts/`, `learner/`, `frontend/out`, `backend/vendor`,
  `backend/data/config`, uvicorn, fastapi, sklearn, pyarrow, apscheduler --
  every one of them is imported by the SHELL, which runs from the checkout.

`--onedir`, still deliberately: a onefile build unpacks to a temp directory on
every launch, which is both slow and the hardest thing for antivirus heuristics
to swallow.

THE STALE-EXPORT REFUSAL IS GONE, on purpose. It existed because the bundle
carried `frontend/out` and an empty one produced a window showing raw JSON. The
launcher serves the checkout's export and rebuilds it when `frontend/` has
changed, so the build no longer has an opinion about it.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(SPECPATH).resolve().parent          # noqa: F821 - SPECPATH is injected

# A running AegisDesktop.exe holds its own directory open, and PyInstaller's
# COLLECT step wipes the target first -- so a rebuild while the app is open dies
# with `PermissionError: [WinError 5] Access is denied` forty lines deep in
# `_make_clean_directory`, which names the directory but not the reason. Say the
# reason here, at the top, before the analysis is spent.
_running = []
if sys.platform == "win32":
    try:
        _tasks = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq AegisDesktop.exe", "/NH"],
            capture_output=True, text=True, timeout=15, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        if "AegisDesktop.exe" in _tasks:
            _running.append(_tasks.strip().splitlines()[0].strip())
    except (OSError, subprocess.SubprocessError):
        pass
if _running and str(DISTPATH).lower().rstrip("\\/").endswith("dist"):   # noqa: F821
    raise SystemExit(
        "REFUSED: AegisDesktop.exe is running, and it holds the directory this build "
        "would wipe:\n    " + "\n    ".join(_running) + "\n"
        "Close the app, or build alongside it with a staging path:\n"
        "    python -m PyInstaller desktop/AegisDesktop.spec --noconfirm --distpath dist_next\n"
        "then swap the folders once it is closed. Never kill it to unblock a build -- it may be "
        "running a night job."
    )

datas = [
    (str(REPO / "desktop" / "assets"), "desktop/assets"),
]

hiddenimports = [
    # pywebview picks its platform backend at runtime through a string.
    "webview.platforms.edgechromium",
]

excludes = [
    # THE WHOLE APP. Every one of these is imported by the shell, which runs
    # from the checkout under a real interpreter. Listing them is not belt and
    # braces: pywebview pulls in `typing_extensions` and friends, and without
    # the excludes PyInstaller's analyser follows `desktop.aegis_desktop` --
    # which `launcher.py` names only as a STRING, so it should not be followed
    # at all, and is listed here so that a future import cannot make it so.
    "backend", "scripts", "learner", "desktop.aegis_desktop",
    "uvicorn", "fastapi", "starlette", "pydantic",
    "pandas", "numpy", "scipy", "sklearn", "lightgbm", "pyarrow", "yfinance",
    "apscheduler", "sqlalchemy", "statsmodels",
    "torch", "torchvision", "torchaudio", "transformers", "sentence_transformers",
    "tensorflow", "tensorboard", "datasets", "accelerate",
    "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter",
    "matplotlib", "notebook", "IPython", "pytest", "_pytest", "PyInstaller",
]

a = Analysis(                                            # noqa: F821
    [str(REPO / "desktop" / "launcher.py")],
    pathex=[str(REPO)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)                                        # noqa: F821

exe = EXE(                                               # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AegisDesktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX compression is the other big antivirus trigger
    console=False,           # no terminal window; the launcher logs to files
    disable_windowed_traceback=False,
    icon=str(REPO / "desktop" / "assets" / "aegis.ico"),
)

coll = COLLECT(                                          # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AegisDesktop",
)
