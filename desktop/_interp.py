"""Which Python runs the checkout's code, and why it is never `sys.executable`.

THE PROBLEM, IN ONE LINE. Inside a PyInstaller build `sys.executable` is
`AegisDesktop.exe`, which has no `-m` and no research stack; hand it a module
name and argparse eats it as a positional, the job dies instantly, and the app
reports "started" over an empty log. `backend/routers/control.job_python()` has
carried the resolution order for months; the launcher needs exactly the same
answer before it can start anything, so the logic lives here and both import it.

It REFUSES rather than guessing, and every refusal says what it looked for. A
launcher that silently falls back to a Python without pandas produces a window
that opens onto an ImportError, which is the harder failure to read.

This module imports the standard library and nothing else -- no `backend`, no
`desktop.aegis_desktop`. The launcher is frozen alone, and anything it imports
is frozen with it.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

#: Tried in order, relative to the checkout.
VENV_CANDIDATES = (
    ".venv/Scripts/python.exe",
    ".venv/bin/python",
    "venv/Scripts/python.exe",
    "venv/bin/python",
)


def resolve(root: Path | None = None, *,
            frozen: bool | None = None) -> tuple[str | None, str]:
    """`(interpreter, why)`. `interpreter` is None only when nothing was found.

    `frozen` and `root` are parameters rather than globals so the resolution can
    be tested without building an .exe -- the frozen branch is the one that
    matters and the one that cannot otherwise be exercised.
    """
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    if not frozen:
        return sys.executable, "running from source: this interpreter"

    cand = os.getenv("AEGIS_JOB_PYTHON")
    if cand and Path(cand).exists():
        return cand, "AEGIS_JOB_PYTHON"
    if cand:
        # Named and absent is worth saying: it is a typo, not a missing venv.
        why_env = f"AEGIS_JOB_PYTHON={cand!r} does not exist; "
    else:
        why_env = ""

    if root is not None:
        for rel in VENV_CANDIDATES:
            p = Path(root) / rel
            if p.exists():
                return str(p), f"{why_env}the checkout's {rel}"

    found = shutil.which("python") or shutil.which("python3")
    if found:
        return found, f"{why_env}`python` on PATH"
    return None, (
        f"{why_env}no interpreter found: no AEGIS_JOB_PYTHON, no "
        f"{' / '.join(VENV_CANDIDATES)} under {root}, and no python on PATH")
