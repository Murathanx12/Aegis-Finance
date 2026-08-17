"""The suite must not read or write the artifacts the repo actually keeps.

`conftest.py` redirects several of these, and every redirection is written
defensively (`try/except: yield`) so that a missing module cannot break the run.
That defensiveness is the risk: a fixture that swallows its own failure is a
fixture that can silently stop working, which is §47 — a guard whose test never
made it fire.

So each redirection gets an assertion that it is IN EFFECT, from inside a test.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_the_disk_cache_is_not_the_repos_live_one():
    """Found 2026-08-17 when a hand-run of an endpoint made a refusal test pass
    a 200 back to itself. A cache shared between the app and the suite makes
    every cached endpoint's test depend on whether a human called it first."""
    from backend import cache as c
    assert c._CACHE_DIR != REPO / ".cache", (
        "the suite is using the repo's live disk cache; a manual call to any "
        "cached endpoint will then decide test outcomes")
    assert not str(c._CACHE_DIR).startswith(str(REPO)), c._CACHE_DIR


def test_a_write_through_the_cache_lands_outside_the_repo():
    """The attribute being right is not the same as the writes following it."""
    from backend import cache as c
    c.cache_set("suite-isolation-probe", {"v": 1})
    dc = c._get_disk_cache()
    if dc is None:                                   # diskcache absent: nothing
        return                                       # can leak, nothing to check
    assert not str(Path(dc.directory).resolve()).startswith(str(REPO))


def test_the_sandbox_telemetry_is_redirected_too():
    """The 2026-08-15 repair, asserted rather than assumed."""
    try:
        from backend.services import investigator_night as _in
    except Exception:                                            # noqa: BLE001
        return
    for attr in ("SANDBOX_TELEMETRY", "SANDBOX_RECEIPTS_DIR"):
        p = getattr(_in, attr, None)
        if p is None:
            continue
        assert not str(Path(p).resolve()).startswith(str(REPO / "backend")), (
            f"{attr} still points inside the repo: {p}")
