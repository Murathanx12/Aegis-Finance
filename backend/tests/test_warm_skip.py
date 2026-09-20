"""AEGIS_WARM_SKIP=1: the deployment warms nothing, and says so.

2026-09-20. The website backend's warm loop was ~$20 of the ~$47 Railway
month (0.58 vCPU average, 29.8 vCPU peaks, for a page nobody was on). The
switch has to be (a) read at call time so a Railway redeploy picks it up,
(b) honest on the health page -- `skipped`, never `ready` -- and (c) inert
when unset, because a switch that also changed the warm path when OFF would
be a second change hiding behind the first.
"""

from __future__ import annotations

import asyncio

import pytest

from backend import cache as _cache
from backend import main as M


@pytest.fixture(autouse=True)
def _clean_status():
    before = _cache.cache_status()
    yield
    _cache.set_cache_status(before.get("status") or "pending", before.get("error"))


def test_the_switch_is_read_at_call_time(monkeypatch):
    monkeypatch.delenv("AEGIS_WARM_SKIP", raising=False)
    monkeypatch.setattr(M, "_desktop_background_off", lambda: False)
    from backend import config as C
    monkeypatch.setattr(C, "WARM_SKIP", False, raising=False)
    assert M._warm_skip() is False
    monkeypatch.setenv("AEGIS_WARM_SKIP", "1")
    assert M._warm_skip() is True
    monkeypatch.setenv("AEGIS_WARM_SKIP", "0")
    monkeypatch.setattr(C, "WARM_SKIP", True, raising=False)
    assert M._warm_skip() is True


def test_skip_starts_nothing_and_reports_skipped(monkeypatch):
    monkeypatch.setenv("AEGIS_WARM_SKIP", "1")
    monkeypatch.setattr(M, "_desktop_background_off", lambda: False)
    fetched: list[str] = []

    class _Fetcher:                                   # would be a network call
        def fetch_market_data(self):
            fetched.append("market")

        def fetch_fred_data(self):
            fetched.append("fred")

    import backend.services.data_fetcher as DF
    monkeypatch.setattr(DF, "DataFetcher", _Fetcher)
    spawned: list[str] = []

    async def _run():
        real_create = asyncio.create_task

        def _spy(coro, **kw):
            spawned.append(getattr(coro, "__name__", repr(coro)))
            coro.close()
            return real_create(asyncio.sleep(0))

        monkeypatch.setattr(asyncio, "create_task", _spy)
        await M._prewarm_cache()

    asyncio.run(_run())
    assert fetched == [], "the skip must not touch the data layer"
    assert spawned == [], f"the skip must start no warm task, started {spawned}"
    st = _cache.cache_status()
    assert st["status"] == "skipped"
    assert "AEGIS_WARM_SKIP" in (st.get("error") or "")
    assert _cache.cache_ready() is False


def test_unset_keeps_the_warm_path(monkeypatch):
    """The OFF position is the old code: prewarm runs and both warm tasks start."""
    monkeypatch.delenv("AEGIS_WARM_SKIP", raising=False)
    from backend import config as C
    monkeypatch.setattr(C, "WARM_SKIP", False, raising=False)
    monkeypatch.setattr(M, "_desktop_background_off", lambda: False)
    fetched: list[str] = []

    class _Fetcher:
        def fetch_market_data(self):
            fetched.append("market")

        def fetch_fred_data(self):
            fetched.append("fred")

    import backend.services.data_fetcher as DF
    monkeypatch.setattr(DF, "DataFetcher", _Fetcher)
    spawned: list[str] = []

    async def _run():
        real_create = asyncio.create_task

        def _spy(coro, **kw):
            spawned.append(getattr(coro, "__name__", repr(coro)))
            coro.close()
            return real_create(asyncio.sleep(0))

        monkeypatch.setattr(asyncio, "create_task", _spy)
        await M._prewarm_cache()

    asyncio.run(_run())
    assert fetched == ["market", "fred"]
    assert spawned == ["_prewarm_pi_fast_lanes", "_warm_endpoint_caches_loop"]
    assert _cache.cache_status()["status"] == "ready"
