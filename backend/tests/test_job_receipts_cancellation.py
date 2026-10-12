"""Real wrapper cancellation must not turn interruption into success."""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from backend.services import job_receipts as JR
from backend.services import forecast_populations as FP


@pytest.fixture(autouse=True)
def isolated_receipts(monkeypatch, tmp_path):
    monkeypatch.setattr(JR, "_root", lambda: tmp_path / "job_receipts")


@pytest.mark.parametrize("annotation", [None, "grading", "skip"])
def test_real_task_cancel_propagates_and_preserves_partial_work(annotation, tmp_path):
    outer = {"job": "outer"}
    outer_token = JR._current.set(outer)
    calls = []

    async def scenario():
        entered = asyncio.Event()
        blocked = asyncio.Event()

        @JR.receipted("arena_daily")
        async def job():
            if annotation == "grading":
                JR.note(writes={"completed": 1}, arena_grading_status="OK")
            elif annotation == "skip":
                JR.note(skip_reason="fixture partial decision")
            entered.set()
            try:
                await blocked.wait()
                calls.append("submission")
            finally:
                JR.note(body_finally_completed=True)

        async def caller():
            try:
                await job()
            except asyncio.CancelledError:
                assert JR._current.get() is outer
                calls.append("caller_cancelled")
                raise

        task = asyncio.create_task(caller())
        await entered.wait()
        task.cancel("PRIVATE_CANCELLATION_SENTINEL")
        with pytest.raises(asyncio.CancelledError) as exc:
            await task
        assert exc.value.args == ("PRIVATE_CANCELLATION_SENTINEL",)
        assert task.cancelled()

    try:
        asyncio.run(scenario())
        assert JR._current.get() is outer
    finally:
        JR._current.reset(outer_token)
    receipts = JR.read("arena_daily")["receipts"]
    assert len(receipts) == 1
    r = receipts[0]
    assert r["status"] == "raised" and r["exception"] == "CancelledError"
    assert "PRIVATE_CANCELLATION_SENTINEL" not in json.dumps(r)
    assert r["extra"]["body_finally_completed"] is True
    assert r["finished_at"] and r["duration_seconds"] >= 0
    assert calls == ["caller_cancelled"]
    if annotation == "grading":
        assert r["writes"] == {"completed": 1}
        assert r["extra"]["arena_grading_status"] == "OK"
    if annotation == "skip":
        assert r["skip_reason"] == "fixture partial decision"
    # Even pre-cancellation OK notes cannot qualify an interrupted run.
    observation = FP._arena_grading_receipt(root=tmp_path, now=datetime.now(timezone.utc))
    assert observation["status"] == "UNKNOWN"


def test_wait_for_timeout_records_interruption_and_propagates_timeout():
    @JR.receipted("timeout")
    async def blocked():
        await asyncio.Event().wait()

    async def caller():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(blocked(), timeout=0.01)
        assert JR._current.get() is None

    asyncio.run(caller())
    receipt = JR.read("timeout")["receipts"][0]
    assert receipt["status"] == "raised" and receipt["exception"] == "CancelledError"


def test_existing_receipt_is_not_rewritten_by_new_cancelled_run(tmp_path):
    directory = tmp_path / "job_receipts" / "arena_daily"
    directory.mkdir(parents=True)
    historical = directory / "2000-01-01T000000_000000Z_history.json"
    original = b'{"job":"arena_daily","status":"ran","historical":true}'
    historical.write_bytes(original)

    @JR.receipted("arena_daily")
    async def cancelled():
        raise asyncio.CancelledError("PRIVATE_SENTINEL")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancelled())
    assert historical.read_bytes() == original
    assert JR.read("arena_daily")["n_receipts"] == 2


def test_receipt_disk_failure_does_not_swallow_cancellation(monkeypatch):
    def unavailable():
        raise OSError("fixture disk unavailable")
    monkeypatch.setattr(JR, "_root", unavailable)

    @JR.receipted("cancelled_disk")
    async def cancelled():
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancelled())
    assert JR._current.get() is None


def test_actual_arena_scheduler_await_cancellation_cannot_submit(monkeypatch, tmp_path):
    # Compile the exact existing two function bodies; omit decorators/gate and
    # replace only the engine/thread dispatch, so no real engine or broker runs.
    import ast
    import logging
    import sys
    from pathlib import Path
    from types import ModuleType, SimpleNamespace
    source = Path("backend/services/portfolio_intelligence/scheduler.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"_arena_daily", "_arena_daily_pass"}
    functions = [n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name in names]
    assert {n.name for n in functions} == names
    for fn in functions:
        fn.decorator_list = []
    calls = []

    async def scenario():
        entered = asyncio.Event()
        blocker = asyncio.Event()

        async def dispatch(fn):
            entered.set()
            await blocker.wait()
            raise AssertionError("thread dispatch must stay blocked")

        async def submit():
            calls.append("submit")

        fake_package = ModuleType("backend.services.arena")
        fake_package.engine = SimpleNamespace(run_daily=lambda: None)
        monkeypatch.setitem(sys.modules, "backend.services.arena", fake_package)
        monkeypatch.setattr(asyncio, "to_thread", dispatch)
        scope = {"logger": logging.getLogger("fixture"), "note": JR.note,
                 "_submit_arena_broker_intent": submit}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), scope)
        wrapped = JR.receipted("arena_daily")(scope["_arena_daily"])
        task = asyncio.create_task(wrapped())
        await entered.wait()
        task.cancel("PRIVATE_CANCELLATION_SENTINEL")
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert calls == []
    receipt = JR.read("arena_daily")["receipts"][0]
    assert receipt["status"] == "raised" and "extra" not in receipt
    observation = FP._arena_grading_receipt(root=tmp_path, now=datetime.now(timezone.utc))
    assert observation["status"] == "UNKNOWN"
