"""Tests for the process-wide heavy-work gate (backend/services/heavy_work.py).

The gate exists because of the 2026-08-21 OOM restart loop: background
computes stacking in one process. These tests pin the three behaviours that
matter: (1) two gated bodies never overlap, (2) a gate timeout runs the work
anyway instead of silently skipping it, (3) the high-water mark records what
held the gate at the peak.
"""

import asyncio

import backend.services.heavy_work as hw


class TestGateSerializes:
    def test_two_bodies_never_overlap(self):
        events: list[str] = []

        async def job(name: str, hold_s: float):
            async with hw.heavy(name, timeout_s=5.0):
                events.append(f"{name}:in")
                await asyncio.sleep(hold_s)
                events.append(f"{name}:out")

        async def _run():
            await asyncio.gather(job("a", 0.05), job("b", 0.05))

        asyncio.run(_run())
        # Whatever the order, an :in must be followed by its own :out before
        # the other task's :in — overlap would interleave them.
        assert events in (
            ["a:in", "a:out", "b:in", "b:out"],
            ["b:in", "b:out", "a:in", "a:out"],
        ), f"gated bodies overlapped: {events}"

    def test_timeout_runs_the_work_anyway(self):
        ran: list[str] = []

        async def holder():
            async with hw.heavy("holder", timeout_s=5.0):
                await asyncio.sleep(0.3)

        async def latecomer():
            await asyncio.sleep(0.05)  # let holder take the gate first
            async with hw.heavy("latecomer", timeout_s=0.05):
                ran.append("latecomer")

        async def _run():
            await asyncio.gather(holder(), latecomer())

        asyncio.run(_run())
        assert ran == ["latecomer"], (
            "a gate timeout must degrade to unserialized execution, "
            "never to silently skipped work")

    def test_gate_survives_multiple_event_loops(self):
        """asyncio primitives bind to their first loop; the gate must be
        usable across sequential asyncio.run() calls (the test-suite shape)."""
        async def one_pass():
            async with hw.heavy("loop-check", timeout_s=1.0):
                pass

        asyncio.run(one_pass())
        asyncio.run(one_pass())  # would raise "bound to a different event loop"


class TestHighWater:
    def test_peak_carries_the_holder_name(self, monkeypatch):
        samples = iter([100.0, 3500.0, 200.0])
        monkeypatch.setattr(hw, "rss_mb", lambda: next(samples, 200.0))
        # Reset the module mark so earlier tests can't have set a higher peak.
        with hw._state_lock:
            hw._high_water.update({"rss_mb": None, "at": None, "during": None})

        async def _run():
            hw.note_rss("before")            # 100 — baseline
            async with hw.heavy("job:spiky", timeout_s=1.0):
                hw.note_rss()                # 3500 — inside the gate
            hw.note_rss("after")             # 200 — below peak, ignored

        asyncio.run(_run())
        peak = hw.high_water()
        assert peak["rss_mb"] == 3500.0
        assert peak["during"] == "job:spiky", (
            "the high-water mark must name what held the gate at the peak — "
            f"got {peak}")
        assert peak["now_running"] is None
