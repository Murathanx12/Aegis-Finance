"""Real threads and a private foreign OS lock; no OpenClaw/browser/provider call."""
from contextlib import contextmanager
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from backend.services import disk_guard as DG
from backend.services import openclaw_client as OC


@pytest.fixture
def scope_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path / "aegis_openclaw_exclusive_paper_scope.lock"


@pytest.mark.parametrize("raise_in_first", [False, True])
def test_two_actual_threads_wait_then_both_enter_without_filelock_failure(scope_path, raise_in_first):
    first_entered, second_started = threading.Event(), threading.Event()
    second_entered, second_done, release = threading.Event(), threading.Event(), threading.Event()
    order, failures, expected_exceptions = [], [], []

    def first():
        try:
            with OC._paper_scope_lock() as path:
                assert path == scope_path
                order.append("first")
                first_entered.set()
                assert release.wait(5), "test did not release first scope"
                if raise_in_first:
                    raise ValueError("fixture exception")
        except ValueError as exc:
            expected_exceptions.append(str(exc))
        except BaseException as exc:
            failures.append(exc)

    def second():
        try:
            second_started.set()
            with OC._paper_scope_lock():
                order.append("second")
                second_entered.set()
        except BaseException as exc:
            failures.append(exc)
        finally:
            second_done.set()

    threads = [threading.Thread(target=first, daemon=True), threading.Thread(target=second, daemon=True)]
    threads[0].start()
    try:
        assert first_entered.wait(5)
        threads[1].start()
        assert second_started.wait(5)
        assert not second_done.wait(0.15), "second thread failed or bypassed the held scope"
        assert not second_entered.is_set()
    finally:
        release.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(5)
    assert not any(t.is_alive() for t in threads)
    assert failures == []
    assert expected_exceptions == (["fixture exception"] if raise_in_first else [])
    assert order == ["first", "second"]
    assert second_entered.is_set()


def test_same_thread_reentry_and_exception_release_keep_original_scope_value(scope_path):
    with OC._paper_scope_lock() as outer:
        with OC._paper_scope_lock() as inner:
            assert outer == inner == scope_path
    with pytest.raises(RuntimeError, match="fixture"):
        with OC._paper_scope_lock():
            raise RuntimeError("fixture")
    with OC._paper_scope_lock() as after:
        assert after == scope_path


_FOREIGN_LOCK = r"""
import os, sys
from pathlib import Path
path, ready = map(Path, sys.argv[1:])
with path.open('a+b') as stream:
    if os.name == 'nt':
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    ready.write_text('HELD', encoding='utf-8')
    sys.stdin.buffer.read(1)
    if os.name == 'nt':
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
"""


def test_foreign_process_still_refuses_before_protected_action_and_releases_local_gate(
    scope_path, monkeypatch,
):
    # Direct base interpreter avoids an owned venv-launcher descendant on Windows.
    executable = getattr(sys, "_base_executable", sys.executable)
    ready = scope_path.with_name("foreign-ready.txt")
    child = subprocess.Popen(
        [executable, "-I", "-S", "-B", "-c", _FOREIGN_LOCK, str(scope_path), str(ready)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    actions, file_lock_calls = [], []
    actual_file_lock = DG.file_lock

    @contextmanager
    def observed_file_lock(path, **kwargs):
        file_lock_calls.append((path, kwargs))
        assert kwargs == {"timeout_s": 0}, "cross-process refusal policy changed"
        with actual_file_lock(path, **kwargs) as held:
            yield held

    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), "owned private foreign-lock fixture did not become ready"
        monkeypatch.setattr(DG, "file_lock", observed_file_lock)
        with pytest.raises(DG.FileLockTimeout, match="held by another process"):
            with OC._paper_scope_lock():
                actions.append("protected action")
        assert actions == []  # Outside the guard; no swallowed failure can hide entry.
    finally:
        try:
            _, stderr = child.communicate(input="\n", timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()  # Only this test-owned direct interpreter PID, no descendants.
            child.communicate(timeout=5)
            pytest.fail("owned foreign-lock fixture did not exit")
    assert child.returncode == 0, stderr
    assert file_lock_calls == [(scope_path, {"timeout_s": 0})]
    with OC._paper_scope_lock() as held:
        assert held == scope_path
        actions.append("after foreign release")
    assert actions == ["after foreign release"]
