"""A warm cache and a dead source must not produce the same health page.

WHAT WENT WRONG (found live, 2026-08-16 02:06 UTC)
==================================================
`/api/health/full` reported `fred_health: UNKNOWN` with all 23 series
`UNAVAILABLE`, `fetch_passes: 0`, `last_no_fetch_reason: null` — while the FRED
data being served was fine. The Railway logs show exactly why:

    2026-08-15 17:42:48  Fetching macroeconomic indicators from FRED (parallel)...
    2026-08-15 17:42:52    Loaded 23/23 FRED series          <- 3.6s, body ran
    2026-08-15 17:42:52  Prewarmed: FRED data

    2026-08-16 02:06:31,754  Prewarmed: market data
    2026-08-16 02:06:31,763  Prewarmed: FRED data            <- 9 milliseconds

The process restarted 8.4 hours later, `@cached(ttl=86400)` served the payload
from the SQLite disk cache, and the decorator returns BEFORE the function body —
so `record_pass` never ran. `fetch_passes` stayed 0 and every series read
UNAVAILABLE.

WHY THIS IS WORSE THAN A FALSE ALARM
====================================
`fred_health` was built to measure whether the FRED inputs are trustworthy. What
it actually measured was whether the fetch BODY executed in THIS process. Those
two agree only until something serves the data without re-fetching it.

The dangerous half is not the noise, and it is narrower than it first looks.
Checked rather than assumed: a dark FRED with a COLD cache still records misses
and reads DEGRADED, so those two cases do differ. What actually breaks is the
paging surface. `degraded_reasons()` names a never-loaded critical series only
when `passes_seen > 0` (fred_health.py:247), and a restart zeroes that — so a
critical series that was ALREADY missing when the payload was cached goes
SILENT, while remaining absent from the data served for the rest of the TTL:

    cold pass, ICSA missing        -> 1 reason, named        DEGRADED
    restart into that warm cache   -> 0 reasons              UNKNOWN

That is the exact ICSA incident this module was written to eliminate, arriving
through the cache instead of through the fetch.

WHY NOT JUST PERSIST THE HEALTH STATE
=====================================
The module's own scope note refuses to persist "a health claim that outlives the
evidence for it", and that principle is right. But its premise does not hold
here: the evidence does NOT die with the process. The payload lives in the disk
cache and is still being served. The restart destroyed the health RECORD, not
the data it describes — they have different lifetimes, and the module assumed
they had the same one.

So nothing is persisted and no claim is remembered. Health is RE-DERIVED from
the artefact actually being served, which carries its own fetch timestamp.
"""

from __future__ import annotations

import pandas as pd
import pytest

from backend.config import config
from backend.services import fred_health as FH

SERIES_IDS = config["data"]["fred_series"]


class _FakeDisk:
    """Stands in for diskcache — survives a simulated restart, like the real one."""

    def __init__(self):
        self.store: dict = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


class _StubFred:
    """Counts calls so a cache HIT is provable rather than assumed."""

    calls = 0
    dark = False

    def __init__(self, api_key=None):
        pass

    def get_series(self, series_id):
        type(self).calls += 1
        if type(self).dark:
            raise RuntimeError(f"FRED is unreachable ({series_id})")
        idx = pd.date_range(end=pd.Timestamp("2026-08-14"), periods=5, freq="W")
        return pd.Series([100.0] * 5, index=idx)


@pytest.fixture
def world(monkeypatch):
    """A cold process with an isolated disk cache and a stubbed FRED.

    The key is forced present. CI exports no secrets at all — its pytest step
    sets `AEGIS_IIF1_PREREG_ABSENT_OK` and nothing else — so a test that leans on
    the ambient FRED_API_KEY passes on this machine and fails there. It did:
    these four tests were green locally in both worlds and turned CI red on
    4d16013. `ci_env_sim` now models the missing secrets so the next one cannot.
    """
    import fredapi

    import backend.cache as C
    from backend.services import data_fetcher as DF

    disk = _FakeDisk()
    monkeypatch.setattr(C, "_get_disk_cache", lambda: disk)
    monkeypatch.setattr(fredapi, "Fred", _StubFred)
    monkeypatch.setattr(DF.api_keys, "fred", "test-key-not-a-real-one")
    _StubFred.calls = 0
    _StubFred.dark = False

    C._cache.clear()
    FH.reset()
    yield C
    C._cache.clear()
    FH.reset()
    _StubFred.dark = False


def _fetch():
    from backend.services.data_fetcher import DataFetcher

    return DataFetcher().fetch_fred_data()


def _restart(C):
    """A process restart: memory cache and health state die, DISK survives.

    That asymmetry is the entire defect — the data outlives the record of it.
    """
    C._cache.clear()
    FH.reset()


# ── the defect ───────────────────────────────────────────────────────────────
def test_a_cache_hit_still_reports_the_fred_data_it_is_serving(world):
    """The live 02:06 restart, reproduced."""
    data = _fetch()
    assert len(data) == len(SERIES_IDS)
    after_cold = _StubFred.calls
    assert after_cold == len(SERIES_IDS)

    _restart(world)

    data2 = _fetch()
    assert _StubFred.calls == after_cold, "expected a cache hit, got a real fetch"
    assert len(data2) == len(SERIES_IDS), "the DATA is fine — only the record was lost"

    h = FH.health()
    assert h["status"] != "UNKNOWN", (
        "health reported UNKNOWN while serving 23 good series from cache")
    assert h["fetch_passes"] > 0
    assert not h["by_status"].get(FH.STATUS_UNAVAILABLE), (
        "series being served right now cannot be UNAVAILABLE")
    assert h["degraded_reasons"] == []


def test_the_whole_payload_reads_the_way_production_read_it(world):
    """The shape, asserted together — because the fields lie separately.

    Verified live on 2026-08-16 at 8c57800, on a restart into a cache warmed at
    the 04:36 UTC boot:

        status ok · fetch_passes 1 · served_from_cache True
        served_fetch_at 2026-08-16T04:36:10+00:00 · served_age_hours 1.44
        19 FRESH · 4 STALE_USABLE · degraded_reasons []

    Every individual field was already covered by a test below. None of them
    would have caught `served_from_cache: True` paired with a `served_fetch_at`
    of *now*, which is the combination that would mean the page had quietly gone
    back to reporting on its own process. `fetch_passes == 1` is the deliberate
    part: the serve floors it at one so `degraded_reasons` can still name a
    critical series that never loaded (`_from_served_payload`, fred_health.py).
    """
    _fetch()
    cold = FH.health()
    assert cold["served_from_cache"] is False, "the cold pass is not a cache hit"
    original_fetch_at = cold["served_fetch_at"]
    assert original_fetch_at is not None

    _restart(world)
    _fetch()

    warm = FH.health()
    assert warm["served_from_cache"] is True
    assert warm["served_fetch_at"] == original_fetch_at, (
        "the served payload's own fetch time must survive the restart — a "
        "fresh timestamp here is the page reporting on its process again")
    assert warm["fetch_passes"] == 1
    assert warm["status"] == "ok"
    assert warm["degraded_reasons"] == []
    assert not warm["by_status"].get(FH.STATUS_UNAVAILABLE)


def test_a_critical_gap_frozen_into_the_cache_keeps_being_paged_on(world):
    """The half that matters, and the original incident arriving by a new door.

    `degraded_reasons()` only names a never-loaded series when `passes_seen > 0`
    (fred_health.py:247). A restart zeroes that, so a critical series that was
    ALREADY missing when the payload was cached stops being reported — while
    still being absent from the data served for the rest of the 24h TTL.

    Measured on the real module before the fix:
        cold pass, ICSA missing      -> 1 reason, named          DEGRADED
        restart into that warm cache -> 0 reasons                UNKNOWN
    """
    real_get = _StubFred.get_series

    def _drop_icsa(self, series_id):
        if series_id == SERIES_IDS["initial_claims"]:
            raise RuntimeError("ICSA failed this pass")
        return real_get(self, series_id)

    _StubFred.get_series = _drop_icsa
    try:
        served = _fetch()
        assert "initial_claims" not in served
        cold_reasons = FH.degraded_reasons()
        assert cold_reasons, "a cold pass missing ICSA must page"

        _restart(world)
        served_again = _fetch()
        assert "initial_claims" not in served_again, (
            "the gap is still in the payload being served")
    finally:
        _StubFred.get_series = real_get

    assert FH.degraded_reasons(), (
        "the critical gap went SILENT across a restart while still being "
        "absent from the served data — this is the ICSA incident again, "
        "reached through the cache instead of through the fetch")


def test_the_served_payloads_own_fetch_time_is_what_ages_it(world):
    """Nothing is remembered; the timestamp travels WITH the data."""
    _fetch()
    fetched_at = FH.health()["series"]["initial_claims"]["last_fetch_ok_at"]
    assert fetched_at is not None

    _restart(world)
    _fetch()

    after = FH.health()["series"]["initial_claims"]
    assert after["last_fetch_ok_at"] == fetched_at, (
        "the restart must report the ORIGINAL fetch time, not a fresh one — "
        "claiming a fetch that did not happen is the opposite failure")


def test_a_cache_hit_does_not_invent_a_new_fetch_pass(world):
    """Serving cached data is not evidence that FRED answered again."""
    _fetch()
    passes_after_cold = FH.health()["fetch_passes"]

    _restart(world)
    _fetch()
    _fetch()
    _fetch()

    assert FH.health()["fetch_passes"] == passes_after_cold, (
        "three cache hits must not read as three successful FRED passes")


def test_a_carried_forward_print_is_not_upgraded_to_FRESH_by_a_restart(world):
    """The one way this change could make the page LESS honest.

    `record_pass` substitutes a last-known-good series for a failed critical one
    and labels it STALE_USABLE. That substituted series IS in the cached
    payload, so a serve that only checked "is it present?" would report a
    carried-forward print as a live one — trading a false alarm for a false
    reassurance, which is the worse direction.
    """
    _fetch()                                   # pass 1: everything arrives
    real_get = _StubFred.get_series

    def _drop_icsa(self, series_id):
        if series_id == SERIES_IDS["initial_claims"]:
            raise RuntimeError("ICSA failed this pass")
        return real_get(self, series_id)

    # Pass 2 with ICSA failing, so it is served from last known good.
    world._cache.clear()
    world._get_disk_cache().store.clear()
    _StubFred.get_series = _drop_icsa
    try:
        served = _fetch()
        assert "initial_claims" in served, "substituted from last known good"
        assert (FH.health()["series"]["initial_claims"]["status"]
                == FH.STATUS_STALE_USABLE)

        _restart(world)
        _fetch()                               # cache hit on that payload
    finally:
        _StubFred.get_series = real_get

    s = FH.health()["series"]["initial_claims"]
    assert s["status"] != FH.STATUS_FRESH, (
        "a carried-forward print was reported as a live fetch after a restart")
    assert s["status"] == FH.STATUS_STALE_USABLE


def test_a_dark_source_with_a_cold_cache_is_still_loud(world):
    """The pre-existing behaviour the fix must not trade away."""
    _StubFred.dark = True
    assert _fetch() == {}, "a dark source returns nothing"
    h = FH.health()
    assert h["status"] == "DEGRADED"
    assert h["degraded_reasons"], "a dead source must name its casualties"
