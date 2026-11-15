"""A windowless process starts every child without a console window (owner, 2026-11-15)."""
import subprocess
import sys

import pytest

from backend.services import quiet_subprocess as qsp

NO_WINDOW = 0x08000000


@pytest.fixture
def restored():
    original = subprocess.Popen.__init__
    had = getattr(subprocess.Popen, "_aegis_windowless_default", None)
    yield
    subprocess.Popen.__init__ = original
    if had is None and hasattr(subprocess.Popen, "_aegis_windowless_default"):
        del subprocess.Popen._aegis_windowless_default


def _flags_seen(monkeypatch, **kw):
    seen = {}

    def fake(self, *a, **k):
        seen.update(k)

    monkeypatch.setattr(subprocess.Popen, "__init__", fake)
    monkeypatch.delattr(subprocess.Popen, "_aegis_windowless_default", raising=False)
    monkeypatch.setattr(qsp, "CREATE_NO_WINDOW", NO_WINDOW)
    assert qsp.install_windowless_default(force=True) is True
    subprocess.Popen(["x"], **kw)
    return seen.get("creationflags")


def test_a_console_process_is_left_alone(restored):
    assert sys.stdout is not None
    before = subprocess.Popen.__init__
    assert qsp.install_windowless_default() is False
    assert subprocess.Popen.__init__ is before


def test_a_windowless_process_adds_the_flag_to_every_child(restored, monkeypatch):
    assert _flags_seen(monkeypatch) == NO_WINDOW


def test_flags_the_caller_passed_are_kept(restored, monkeypatch):
    assert _flags_seen(monkeypatch, creationflags=0x200) == NO_WINDOW | 0x200


@pytest.mark.parametrize("own", [0x8, 0x10])
def test_a_caller_that_chose_its_own_console_keeps_it(restored, monkeypatch, own):
    assert _flags_seen(monkeypatch, creationflags=own) == own


def test_installing_twice_wraps_once(restored, monkeypatch):
    monkeypatch.delattr(subprocess.Popen, "_aegis_windowless_default", raising=False)
    assert qsp.install_windowless_default(force=True) is True
    first = subprocess.Popen.__init__
    assert qsp.install_windowless_default(force=True) is True
    assert subprocess.Popen.__init__ is first


def test_pythonw_and_a_missing_stdout_count_as_windowless(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", r"C:\x\.venv\Scripts\pythonw.exe")
    assert qsp.process_is_windowless() is True
    monkeypatch.setattr(sys, "executable", r"C:\x\.venv\Scripts\python.exe")
    assert qsp.process_is_windowless() is False
    monkeypatch.setattr(sys, "stdout", None)
    assert qsp.process_is_windowless() is True


def test_config_installs_it_before_anything_else_can_spawn():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8"))
    calls = [n for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and getattr(n.value.func, "id", "") == "_install_windowless_default"]
    assert calls, "backend/config.py no longer installs the windowless default"
