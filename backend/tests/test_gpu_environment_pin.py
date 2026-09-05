"""The CUDA build must not be able to disappear silently.

WHY
===
On 2026-09-06 a reviewer found `W3_neural_long_run13` claiming
`torch 2.11.0+cu128` / `cuda_available: true` / RTX 5060 / `sm_120`, while the
repo's own `.venv` reported `2.11.0+cpu`. Two hypotheses were on the table:
a different interpreter ran the job, or torch was downgraded afterwards.

It was the first (see `requirements-gpu.txt` for the filesystem receipt), and
the reason it took an hour to establish is that **nothing in the receipt said
which interpreter produced it**. Two guards follow:

1. `learner.neural_long.resolve_device()` now stamps `python_executable`,
   `python_version` and `torch_file` onto every neural receipt.
2. This file. On a host that HAS an NVIDIA GPU (this laptop), the designated
   GPU interpreter must exist and must report CUDA. On a host without one (CI),
   every test here SKIPS -- a GPU assertion on a GPU-less runner is a broken
   gate, not a strict one.

Note the asymmetry on purpose: this does NOT require the repo `.venv` to carry
a CUDA torch. The venv is the test/CPU environment and always has been; the GPU
interpreter is a second, declared one. What is forbidden is the GPU interpreter
quietly becoming a CPU one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REQ_GPU = ROOT / "requirements-gpu.txt"

DEFAULT_GPU_PYTHON = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python" / "Python312" / "python.exe"
)

_PROBE = (
    "import json, sys, torch;"
    "print(json.dumps({'exe': sys.executable, 'torch': torch.__version__,"
    " 'cuda': bool(torch.cuda.is_available())}))"
)


def _host_has_nvidia_gpu() -> bool:
    """True only if `nvidia-smi` runs AND lists at least one GPU."""
    try:
        out = subprocess.run(["nvidia-smi", "-L"], capture_output=True,
                             text=True, timeout=30)
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and "GPU 0" in (out.stdout or "")


def _gpu_python() -> Path:
    override = os.environ.get("AEGIS_GPU_PYTHON")
    return Path(override) if override else DEFAULT_GPU_PYTHON


requires_gpu_host = pytest.mark.skipif(
    not _host_has_nvidia_gpu(),
    reason="no NVIDIA GPU on this host (CI) -- the CUDA pin is a laptop invariant",
)


def test_requirements_gpu_file_exists_and_pins_a_cuda_build():
    """The pin is a committed file, not a memory of how it was installed."""
    assert REQ_GPU.exists(), f"{REQ_GPU} is missing -- the CUDA build is unpinned"
    text = REQ_GPU.read_text(encoding="utf-8")
    assert "+cu" in text, "requirements-gpu.txt does not pin a +cuXXX torch build"
    assert "download.pytorch.org/whl/cu" in text, (
        "requirements-gpu.txt does not carry the --index-url that makes the "
        "install reproducible; a bare `pip install torch` gets the CPU wheel")
    assert "AEGIS_GPU_PYTHON" in text, (
        "requirements-gpu.txt must name the override env var so the interpreter "
        "is discoverable rather than remembered")


@requires_gpu_host
def test_designated_gpu_interpreter_exists():
    py = _gpu_python()
    assert py.exists(), (
        f"this host has an NVIDIA GPU but the designated GPU interpreter "
        f"{py} does not exist. Set AEGIS_GPU_PYTHON, or install per "
        f"requirements-gpu.txt.")


@requires_gpu_host
def test_designated_gpu_interpreter_still_reports_cuda():
    """FAILS on this laptop the moment the CUDA build is replaced by the CPU one."""
    py = _gpu_python()
    if not py.exists():
        pytest.fail(f"designated GPU interpreter {py} does not exist")
    proc = subprocess.run([str(py), "-c", _PROBE], capture_output=True,
                          text=True, timeout=180)
    assert proc.returncode == 0, (
        f"the designated GPU interpreter {py} could not import torch:\n"
        f"{proc.stderr[-2000:]}\nInstall line is in requirements-gpu.txt.")
    info = json.loads((proc.stdout or "").strip().splitlines()[-1])
    assert info["cuda"] is True, (
        f"CUDA DRIFT: {py} reports torch {info['torch']} with "
        f"cuda_available=False. A `pip install torch` from PyPI silently "
        f"replaces the CUDA wheel with the CPU one. Reinstall per "
        f"requirements-gpu.txt before quoting any receipt as a GPU result.")
    assert "+cu" in info["torch"], (
        f"CUDA DRIFT: {py} reports torch {info['torch']}, which is not a "
        f"+cuXXX build (see requirements-gpu.txt)")


def test_neural_receipts_record_the_interpreter_that_produced_them():
    """The defect that cost the review an hour: a device block with no interpreter."""
    from learner import neural_long as N

    if not getattr(N, "_TORCH", False):
        pytest.skip("torch not importable in this interpreter")
    _dev, info = N.resolve_device(prefer_cuda=False)
    for key in ("python_executable", "python_version", "torch_file",
                "torch_version", "cuda_available", "device_actually_used"):
        assert key in info, (
            f"resolve_device() omits {key!r}; a receipt without it cannot be "
            f"traced back to the environment that produced it")
    assert info["python_executable"] == sys.executable
    assert info["device_actually_used"] == "cpu"
    assert info["device_warning"], "a CPU-by-choice run must still say so"
