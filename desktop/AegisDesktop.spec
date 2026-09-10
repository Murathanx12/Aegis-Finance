# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Aegis Desktop.

    cd frontend && AEGIS_DESKTOP_BUILD=1 npx next build
    python -m PyInstaller desktop/AegisDesktop.spec --noconfirm

`--onedir`, deliberately. A onefile build unpacks the whole bundle to a temp
directory on every launch, which turns a 0.75 s cold start into tens of seconds
and is what antivirus heuristics flag hardest. The cost is a folder instead of a
single file, which a desktop shortcut hides anyway.

WHAT IS AND IS NOT IN THE BUNDLE, and why -- the first attempt got this wrong
and produced a **27 GB** dist directory before it was stopped:

* IN: the window (pywebview), the API (`backend`), and the static frontend
  export. That is what a click on the shortcut has to start.
* OUT: `backend/data/**`. `collect_data_files("backend")` swept every parquet --
  the 1.25M-row bar table, the 339,657-row news panel, `train_table_long` --
  into the bundle. The app READS those from the repo at runtime; a second copy
  inside the .exe is pure duplication that also goes stale the moment a night
  job writes.
* OUT: torch, transformers, and the `scripts`/`learner` packages.
  `collect_submodules("scripts")` imports every night job at analysis time and
  drags in torch with CUDA (~2.5 GB) for jobs the WINDOW never runs. Night jobs
  are spawned as subprocesses by `backend.routers.control.job_python()`, which
  resolves a real interpreter that already has that stack, and refuses
  audibly if it cannot find one.

The app is a launcher for THIS machine's repo -- it reads
`backend/data/optimus/**` at runtime and was never portable. Pretending
otherwise is what cost the 27 GB.
"""

from pathlib import Path

REPO = Path(SPECPATH).resolve().parent          # noqa: F821 - SPECPATH is injected

# ---------------------------------------------------------------- data files
# Without `frontend/out` the window shows the API's JSON root and nothing else.
# `mount_desktop_frontend` degrades honestly (logs, reports `mounted: False`),
# but the build should never get that far -- so fail LOUDLY here.
_out = REPO / "frontend" / "out"
if not (_out / "index.html").exists():
    raise SystemExit(
        f"REFUSED: no static export at {_out}. Build it first:\n"
        f"    cd frontend && AEGIS_DESKTOP_BUILD=1 npx next build\n"
        f"Packaging without it produces an .exe whose window is empty, which is "
        f"the kind of failure that looks like a crash and is not."
    )

datas = [
    (str(_out), "frontend/out"),
    (str(REPO / "desktop" / "assets"), "desktop/assets"),
]
# Small configuration the services read at import time. Named explicitly, one
# directory at a time: a glob here is how `backend/data` got swept last time.
for rel in ("backend/data/config", "backend/data/lanes"):
    p = REPO / rel
    if p.exists():
        datas.append((str(p), rel))

# Non-.py files under `backend/` that the code opens BY PATH rather than
# importing -- the vendored `alpha/human.py` schema mirror, the trained crash
# model artefacts. PyInstaller bundles modules, not files a module reads, so
# dropping the blanket `collect_data_files` lost these: the first .exe started,
# imported `backend.services.human_thesis`, and died with
# `SchemaUnavailable: the vendored thesis schema is missing`. It failed loudly
# with the full path, which is the only reason this took one smoke test to find.
#
# `backend/data` and `backend/tests` are skipped BY NAME. That skip is the whole
# safety property: without it this walk is the 27 GB build again, and the size
# ceiling below is the second line of defence.
# `backend/vendor/` is copied WHOLE, `.py` files included, and it is the one
# place where that is right. It holds a byte-identical mirror of the execution
# repo's `alpha/human.py`, which `human_thesis._load_mirror` loads by inserting
# the directory on `sys.path` and importing from there -- so PyInstaller's
# analyser never sees the import and bundles nothing, while the `.py` skip below
# would drop the files even if it had. The first two builds both died on
# `SchemaUnavailable: the vendored thesis schema is missing at <path>` for
# exactly this reason.
_vendor = REPO / "backend" / "vendor"
if _vendor.exists():
    datas.append((str(_vendor), "backend/vendor"))

_SKIP_TOP = {"data", "tests", "vendor", "__pycache__", ".pytest_cache"}
_SKIP_SUFFIX = {".py", ".pyc", ".pyo", ".md", ".log"}
_MAX_MB = 8                 # a data file larger than this does not belong in an app bundle
for _p in (REPO / "backend").rglob("*"):
    if not _p.is_file():
        continue
    _parts = _p.relative_to(REPO / "backend").parts
    if _parts[0] in _SKIP_TOP or "__pycache__" in _parts:
        continue
    if _p.suffix.lower() in _SKIP_SUFFIX or _p.name == "Dockerfile":
        continue
    if _p.stat().st_size > _MAX_MB * 1024 * 1024:
        raise SystemExit(
            f"REFUSED: {_p.relative_to(REPO)} is {_p.stat().st_size / 1e6:.0f} MB. "
            f"Data that large belongs in the repo the app reads at runtime, not inside "
            f"the bundle -- a copy in the .exe is stale the moment a night job writes it."
        )
    datas.append((str(_p), str(_p.parent.relative_to(REPO)).replace("\\", "/")))

# ------------------------------------------------------------ hidden imports
# The API's routers are imported by name in `backend/main.py`, so the analyser
# finds them. These are the ones reached through strings or plugin registries.
hiddenimports = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    "apscheduler.jobstores.sqlalchemy", "apscheduler.triggers.cron",
    "apscheduler.triggers.interval", "apscheduler.executors.pool",
    "sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes",
    "pyarrow.parquet",
]

excludes = [
    # the window is WebView2; a bundled Qt/GTK toolkit adds ~100 MB for nothing
    "PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter",
    # research stack: night jobs run under a real interpreter (see job_python)
    "torch", "torchvision", "torchaudio", "transformers", "sentence_transformers",
    "tensorflow", "tensorboard", "datasets", "accelerate",
    # dev-only
    "matplotlib", "notebook", "IPython", "pytest", "_pytest", "PyInstaller",
]

a = Analysis(                                            # noqa: F821
    [str(REPO / "desktop" / "aegis_desktop.py")],
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
    console=False,           # no terminal window; the shell logs to files
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
