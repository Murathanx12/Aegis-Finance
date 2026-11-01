"""Portable scoped-fixture effects; all real OS locks stay in private test paths."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

import pytest

from backend.services import disk_guard as DG
from backend.services import openclaw_client as OC
from backend.tests import conftest as original_conftest

ROOT = Path(original_conftest.__file__).resolve().parents[2]
NAME = "aegis_openclaw_exclusive_paper_scope.lock"
MEMBER = ROOT / "backend/tests/test_openclaw_client.py"


def fixture_function(pytest_request):
    installed = getattr(original_conftest, "_paper_scope_isolated_for_fake_transports", None)
    if installed is None:
        # E-only pre-integration run; after W integration conftest supplies it.
        plugin = pytest_request.config.pluginmanager.get_plugin("ci41_scope_plugin")
        installed = plugin._paper_scope_isolated_for_fake_transports
    return installed.__wrapped__


def fake_request(path, allocations, mp=None, private=None):
    def getfixturevalue(name):
        allocations.append(name)
        if mp is None:
            raise AssertionError("nonmember allocated a fixture")
        return {"monkeypatch": mp, "tmp_path": private}[name]
    return SimpleNamespace(config=SimpleNamespace(rootpath=ROOT), node=SimpleNamespace(path=path),
                           getfixturevalue=getfixturevalue)


@contextmanager
def activate(request, private):
    allocations = []
    mp = pytest.MonkeyPatch()
    gen = fixture_function(request)(fake_request(MEMBER, allocations, mp, private))
    try:
        next(gen)
        yield allocations
    finally:
        try:
            next(gen)
        except StopIteration:
            pass
        finally:
            mp.undo()


@pytest.mark.parametrize("relative", ["backend/tests/test_personal_mode.py",
                                      "backend/tests/test_openclaw_paper_scope_threads.py",
                                      "unrelated/test_openclaw_client.py"])
def test_nonmembers_allocate_zero_and_do_not_patch(request, relative):
    calls = []
    original = DG.file_lock
    gen = fixture_function(request)(fake_request(ROOT / relative, calls))
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)
    assert calls == []
    assert DG.file_lock is original


def test_only_full_native_path_maps_and_arguments_pass_unchanged(request, tmp_path, monkeypatch):
    calls = []

    @contextmanager
    def observed(path, *args, **kwargs):
        calls.append((path, args, kwargs))
        yield path

    monkeypatch.setattr(DG, "file_lock", observed)
    native = Path(tempfile.gettempdir()) / NAME
    other = tmp_path / "different-directory" / NAME
    unrelated = tmp_path / "t.log.lock"
    with activate(request, tmp_path) as allocations:
        with DG.file_lock(native, timeout_s=0, poll_s=0.13):
            pass
        with DG.file_lock(other, timeout_s=0.3, poll_s=0.02):
            pass
        with DG.file_lock(unrelated, timeout_s=2):
            pass
    assert allocations == ["monkeypatch", "tmp_path"]
    assert calls == [(tmp_path / NAME, (), {"timeout_s": 0, "poll_s": 0.13}),
                     (other, (), {"timeout_s": 0.3, "poll_s": 0.02}),
                     (unrelated, (), {"timeout_s": 2})]


@pytest.mark.parametrize("first_raises", [False, True])
def test_actual_oc_threads_and_original_private_lock_release(request, tmp_path, first_raises):
    lock, scope, gettempdir = OC._PAPER_SCOPE_THREAD_LOCK, OC._paper_scope_lock, tempfile.gettempdir
    temp_values = {k: os.environ.get(k) for k in ("TEMP", "TMP")}
    entered, requested, released = threading.Event(), threading.Event(), threading.Event()
    second_done = threading.Event()
    order, errors = [], []

    def first():
        try:
            with OC._paper_scope_lock() as held:
                assert held == tmp_path / NAME
                order.append("first")
                entered.set()
                assert released.wait(5)
                if first_raises:
                    raise ValueError("expected fixture release")
        except ValueError:
            if not first_raises:
                errors.append("unexpected value error")
        except BaseException as exc:
            errors.append(type(exc).__name__)

    def second():
        try:
            requested.set()
            with OC._paper_scope_lock():
                order.append("second")
        except BaseException as exc:
            errors.append(type(exc).__name__)
        finally:
            second_done.set()

    with activate(request, tmp_path):
        workers = [threading.Thread(target=first), threading.Thread(target=second)]
        workers[0].start()
        try:
            assert entered.wait(5)
            workers[1].start()
            assert requested.wait(5)
            assert not second_done.wait(0.1)
        finally:
            released.set()
            for worker in workers:
                if worker.ident is not None:
                    worker.join(5)
        assert not any(worker.is_alive() for worker in workers)
        assert errors == []
        assert order == ["first", "second"]
        with OC._paper_scope_lock() as outer:
            with OC._paper_scope_lock() as inner:
                assert outer == inner == tmp_path / NAME
    assert OC._PAPER_SCOPE_THREAD_LOCK is lock and OC._paper_scope_lock is scope
    assert tempfile.gettempdir is gettempdir
    assert {k: os.environ.get(k) for k in ("TEMP", "TMP")} == temp_values


FOREIGN_LOCK = r"""
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
"""


def test_real_foreign_private_holder_refuses_zero_action_then_release_positive(request, tmp_path, monkeypatch):
    private = tmp_path / NAME
    ready = tmp_path / "ready.txt"
    original = DG.file_lock
    calls, actions = [], []

    @contextmanager
    def observed(path, **kwargs):
        calls.append((path, kwargs))
        with original(path, **kwargs) as held:
            yield held

    monkeypatch.setattr(DG, "file_lock", observed)
    child = subprocess.Popen([getattr(sys, "_base_executable", sys.executable), "-I", "-S", "-B", "-c",
                              FOREIGN_LOCK, str(private), str(ready)], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        with activate(request, tmp_path):
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert ready.exists(), "test-owned private holder was not ready"
                with pytest.raises(DG.FileLockTimeout):
                    with OC._paper_scope_lock():
                        actions.append("protected action")
                assert actions == []  # Outside catch; guard cannot mask unexpected action.
            finally:
                try:
                    _, error = child.communicate(input="\n", timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()  # Only this test-owned direct child, never a native owner.
                    child.communicate(timeout=5)
                    pytest.fail("private test holder did not exit")
            assert child.returncode == 0, error
            assert calls == [(private, {"timeout_s": 0})]
            with OC._paper_scope_lock():
                actions.append("after private release")
    finally:
        # Activation can fail before yielding; this outer cleanup owns the child.
        if child.poll() is None:
            try:
                child.communicate(input="\n", timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate(timeout=5)
                pytest.fail("private holder survived activation failure")
    assert actions == ["after private release"]


def test_activation_failure_still_reaps_only_test_owned_holder(request, tmp_path, monkeypatch):
    children = []
    original = subprocess.Popen

    def observed(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    @contextmanager
    def failed_activation(*args, **kwargs):
        raise RuntimeError("synthetic activation refused")
        yield  # Make the pre-yield failure exercise the context-manager seam.

    monkeypatch.setattr(subprocess, "Popen", observed)
    monkeypatch.setattr(sys.modules[__name__], "activate", failed_activation)
    with pytest.raises(RuntimeError, match="synthetic activation refused"):
        test_real_foreign_private_holder_refuses_zero_action_then_release_positive(request, tmp_path, monkeypatch)
    assert len(children) == 1
    assert children[0].poll() == 0
