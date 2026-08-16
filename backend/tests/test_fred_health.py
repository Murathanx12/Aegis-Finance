"""A temporary source miss and a missing model input must not look the same.

Production read `status: ok, degraded_reasons: []` with 22 of 23 FRED series
loaded and ICSA absent. Nothing was broken in a way anything could see: the
fetch drops a failed series, every consumer skips the key that is not there,
and the fetch is cached for 24 hours — so one bad pass removes a leading
indicator from the LIVE crash-model feature matrix
(`build_feature_matrix(data, fred_data=...)`, routers/stock.py) for a day.

Diagnosed before changing anything: ICSA fetches correctly (3,110 observations,
latest 2026-08-08). The bug is not the fetch. It is that the health page could
not tell the two cases apart.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from backend.config import FRED_LKG_TTL_HOURS
from backend.services import fred_health as FH


@pytest.fixture(autouse=True)
def clean():
    FH.reset()
    yield
    FH.reset()


def _series(last="2026-08-08", value=209000.0, n=5):
    idx = pd.date_range(end=pd.Timestamp(last), periods=n, freq="W")
    return pd.Series([value] * n, index=idx)


def _age_last_ok(name: str, hours: float) -> None:
    FH._state[name]["last_ok_at"] = FH._now() - timedelta(hours=hours)


# ── the vocabulary ──────────────────────────────────────────────────────────
def test_a_series_never_seen_is_unavailable_not_fresh():
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] == FH.STATUS_UNAVAILABLE
    assert s["critical"] is True


def test_a_fetched_series_is_fresh():
    FH.record_success("initial_claims", _series())
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] == FH.STATUS_FRESH
    assert s["last_value"] == 209000.0
    assert FH.degraded_reasons() == []


def test_a_series_whose_world_stopped_printing_is_not_fresh():
    """Fetched fine, but the newest observation is far past its release lag."""
    FH.record_success("initial_claims", _series(last="2025-01-02"))
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] == FH.STATUS_STALE_USABLE
    assert s["last_observation_age_days"] > s["publication_lag_days"]


def test_one_miss_with_a_recent_last_known_good_is_stale_usable():
    FH.record_success("initial_claims", _series())
    FH.record_miss("initial_claims")
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] == FH.STATUS_STALE_USABLE
    assert s["consecutive_misses"] == 1
    assert FH.degraded_reasons() == []          # one Thursday is not an outage


def test_two_consecutive_misses_degrade_and_name_the_series():
    FH.record_success("initial_claims", _series())
    FH.record_miss("initial_claims")
    FH.record_miss("initial_claims")
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] == FH.STATUS_DEGRADED_MISSING
    reasons = FH.degraded_reasons()
    assert len(reasons) == 1
    assert "initial_claims" in reasons[0] and "ICSA" in reasons[0]


def test_a_last_known_good_that_ages_out_degrades():
    FH.record_success("initial_claims", _series())
    FH.record_miss("initial_claims")
    _age_last_ok("initial_claims", FRED_LKG_TTL_HOURS + 1)
    assert FH.last_known_good("initial_claims") is None
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] == FH.STATUS_DEGRADED_MISSING


def test_the_ttl_is_measured_from_the_fetch_not_the_observation():
    """A weekly series is six days old at its freshest; that is not staleness."""
    FH.record_success("initial_claims", _series(last="2026-08-08"))
    got = FH.last_known_good("initial_claims")
    assert got is not None and len(got) == 5


# ── the fallback is used AND disclosed ──────────────────────────────────────
def test_a_failed_critical_series_is_served_from_last_known_good():
    good = _series()
    FH.record_pass({"initial_claims": good})
    results = FH.record_pass({})                 # the failing pass
    assert "initial_claims" in results
    # The real last print, carried forward — not an imputed or zero value.
    assert results["initial_claims"] is good
    assert (FH.series_status(["initial_claims"])["initial_claims"]["status"]
            == FH.STATUS_STALE_USABLE)


def test_a_non_critical_series_is_not_substituted():
    FH.record_pass({"cpi": _series(value=300.0)})
    results = FH.record_pass({})
    assert "cpi" not in results
    # The critical five page (nothing was fetched at all here); cpi never does.
    assert "cpi" not in " ".join(FH.degraded_reasons())


def test_a_critical_series_with_no_history_is_loud_and_absent():
    results = FH.record_pass({})
    assert "initial_claims" not in results       # nothing is invented
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] == FH.STATUS_UNAVAILABLE
    assert any("never loaded" in r for r in FH.degraded_reasons())


def test_a_healthy_pass_leaves_no_reasons():
    from backend.config import CRITICAL_FRED_SERIES
    FH.record_pass({n: _series() for n in CRITICAL_FRED_SERIES})
    assert FH.degraded_reasons() == []
    assert FH.health()["status"] == "ok"


class _Broken:
    def __len__(self):
        return 1

    def __getattr__(self, name):
        raise RuntimeError("no index here")


def test_an_unreadable_series_is_a_miss_not_a_fresh_reading():
    """Found by the silent-fragility audit of this very change.

    The first version stored the object, reset the miss counter and reported
    FRESH with `last_value: None` — a green status over an input nobody could
    read. That is the bug this module exists to remove, reintroduced inside the
    fix for it.
    """
    out = FH.record_pass({"initial_claims": _Broken()})
    assert "initial_claims" not in out           # and it is not passed on
    s = FH.series_status(["initial_claims"])["initial_claims"]
    assert s["status"] != FH.STATUS_FRESH
    assert s["consecutive_misses"] == 1


def test_an_unreadable_series_falls_back_to_the_last_known_good():
    good = _series()
    FH.record_pass({"initial_claims": good})
    out = FH.record_pass({"initial_claims": _Broken()})
    assert out["initial_claims"] is good


# ── a pass that never ran is not a clean pass ───────────────────────────────
def test_no_fetch_at_all_reads_unknown_rather_than_ok():
    h = FH.health()
    assert h["status"] == "UNKNOWN"
    assert h["fetch_passes"] == 0


def test_record_no_fetch_makes_the_gap_visible_and_named():
    FH.record_no_fetch("FRED_API_KEY not set")
    h = FH.health()
    assert h["status"] == "DEGRADED"
    assert h["last_no_fetch_reason"] == "FRED_API_KEY not set"
    assert any("initial_claims" in r for r in h["degraded_reasons"])


def test_a_missing_api_key_records_a_no_fetch_pass(monkeypatch):
    # `_fetch_fred_payload` is the cached half; `__wrapped__` reaches the real
    # body. The public `fetch_fred_data` is now a thin uncached wrapper that
    # also reports on whatever the cache hands it — see
    # tests/test_fred_health_survives_restart.py.
    from backend.services import data_fetcher as DF
    monkeypatch.setattr(DF.api_keys, "has", lambda name: False)
    out = DF.DataFetcher()._fetch_fred_payload.__wrapped__(DF.DataFetcher())
    assert out is None, "a pass that could not be attempted must not be cached"
    assert FH.fetch_passes() > 0
    assert FH.health()["last_no_fetch_reason"] == "FRED_API_KEY not set"


def test_a_missing_api_key_returns_an_empty_dict_to_every_caller(monkeypatch):
    """Eighteen callers read `dict[str, pd.Series]`; None must never reach them."""
    from backend.services import data_fetcher as DF
    monkeypatch.setattr(DF.api_keys, "has", lambda name: False)
    assert DF.DataFetcher().fetch_fred_data() == {}


# ── what the health page shows ──────────────────────────────────────────────
def test_health_groups_by_status_and_carries_the_thresholds():
    FH.record_success("initial_claims", _series())
    FH.record_miss("nfci")
    FH.record_miss("nfci")
    h = FH.health()
    assert h["status"] == "DEGRADED"
    assert "initial_claims" in h["by_status"][FH.STATUS_FRESH]
    assert h["lkg_ttl_hours"] == FRED_LKG_TTL_HOURS
    assert "nfci" in " ".join(h["degraded_reasons"])


def test_health_full_names_the_missing_series_in_degraded_reasons():
    from fastapi.testclient import TestClient
    from backend.main import app

    FH.record_success("initial_claims", _series())
    FH.record_miss("initial_claims")
    FH.record_miss("initial_claims")

    body = TestClient(app).get("/api/health/full").json()
    assert "fred_health" in body
    joined = " ".join(body["degraded_reasons"])
    assert "initial_claims" in joined and "ICSA" in joined
    assert body["status"] == "DEGRADED"
