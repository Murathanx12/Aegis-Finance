"""Source health with a vocabulary: a temporary miss is not a missing model input.

WHAT WENT WRONG
===============
A production health page read `status: ok, degraded_reasons: []` while 22 of 23
FRED series had loaded and `initial_claims` (ICSA) had not. Nothing was broken
in a way anything could see, because:

  * `fetch_fred_data` drops a failed series from its result dict;
  * `get_macro_features` iterates `if fred_key in fred_data` and simply skips
    what is absent;
  * the FRED fetch is cached for 86,400 seconds, so ONE failed pass removes a
    leading indicator for a whole day;
  * and 22/23 is a perfectly plausible number to read past.

The composite then measures something slightly different and says nothing. That
is the house failure mode: code that runs green and silently does less.

Diagnosed 2026-08-14 before changing anything: ICSA fetches correctly right now
(3,110 observations, latest 2026-08-08, 209,000), so the production miss was a
transient failure inside the parallel fetch — NOT a dead series and NOT a
retired series id. The defect worth fixing is therefore not the fetch. It is
that a transient miss and a degraded model input were indistinguishable.

THE VOCABULARY
==============
  FRESH             fetched this pass, and its newest observation is inside the
                    series' own publication lag
  STALE_USABLE      this pass failed; the last known good series is inside its
                    TTL and is being USED — disclosed, never silently swapped
  DEGRADED_MISSING  a critical series has missed enough consecutive passes, or
                    its last known good has aged out. Enters degraded_reasons
                    BY NAME
  UNAVAILABLE       never successfully fetched in this process — there is no
                    last known good to fall back to

Only the last two page. A single miss on a weekly series is a Thursday.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
=========================================
It does not touch the risk-score weights, and it does not impute. A stale value
is the real last print, carried forward and labelled; a missing one stays
missing and says so.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from backend.config import (CRITICAL_FRED_SERIES, FRED_DEGRADED_AFTER_MISSES,
                            FRED_LKG_TTL_HOURS, config)

logger = logging.getLogger(__name__)

STATUS_FRESH = "FRESH"
STATUS_STALE_USABLE = "STALE_USABLE"
STATUS_DEGRADED_MISSING = "DEGRADED_MISSING"
STATUS_UNAVAILABLE = "UNAVAILABLE"

_lock = threading.Lock()

#: name -> {"last_ok_at", "last_value_at", "last_value", "series",
#:          "consecutive_misses", "passes"}
_state: dict[str, dict] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def reset() -> None:
    """Test hook. Process state, not persisted state — see `series_status`."""
    with _lock:
        _state.clear()


def _publication_lag_days(name: str) -> int:
    lags = config["data"].get("fred_publication_lag_days") or {}
    lag = lags.get(name)
    if lag is None:
        return int(config["data"].get("fred_publication_lag_default", 45))
    return int(lag)


def record_success(name: str, series) -> bool:
    """A series arrived and is readable. Keep it as the last known good.

    Returns False — and records a MISS — when the object cannot be read. An
    unreadable series that reset the miss counter would report FRESH with no
    value in it, which is the exact shape this module exists to eliminate: a
    green status over an input that is not there.
    """
    try:
        last_idx = series.index[-1]
        last_value_at = getattr(last_idx, "to_pydatetime", lambda: last_idx)()
        last_value = float(series.iloc[-1])
    except Exception as exc:                                   # noqa: BLE001
        logger.error("FRED: %s came back unreadable (%s: %s) — counting it as "
                     "a MISS, because a series whose last value cannot be read "
                     "is not a series that arrived", name, type(exc).__name__,
                     exc)
        record_miss(name)
        return False
    with _lock:
        st = _state.setdefault(name, {"passes": 0})
        st.update({
            "last_ok_at": _now(),
            "last_value_at": last_value_at,
            "last_value": last_value,
            "series": series,
            "consecutive_misses": 0,
            "passes": st.get("passes", 0) + 1,
        })
    return True


def record_miss(name: str) -> None:
    """A series did not arrive this pass."""
    with _lock:
        st = _state.setdefault(name, {"passes": 0})
        st["consecutive_misses"] = int(st.get("consecutive_misses", 0)) + 1
        st["passes"] = st.get("passes", 0) + 1
        st.setdefault("last_ok_at", None)


def record_no_fetch(reason: str) -> None:
    """No pass happened at all — no key, no library, a timeout, a crash.

    Recorded as a miss for every configured series, because the alternative is
    the worst outcome available: zero passes recorded, every series reading
    UNAVAILABLE with `passes_seen == 0`, and the health page therefore saying
    nothing. "We never asked" and "it is fine" must not be the same page.
    """
    names = list((config["data"].get("fred_series") or {}).keys())
    logger.error("FRED: no fetch pass ran (%s) — recording a miss for all %d "
                 "configured series so the gap is visible", reason, len(names))
    for name in names:
        record_miss(name)
    with _lock:
        _state.setdefault("__pass__", {})["last_no_fetch_reason"] = reason


def fetch_passes() -> int:
    """How many passes any series has seen. Zero means nothing ever ran."""
    return max((int(v.get("passes", 0)) for k, v in _state.items()
                if k != "__pass__"), default=0)


def last_known_good(name: str):
    """The last good series for `name`, or None if there is none or it aged out.

    Age is measured from the FETCH, not from the observation date: a weekly
    series is legitimately six days old at its freshest, and confusing "we have
    not looked recently" with "the world has not printed recently" is how a TTL
    ends up rejecting healthy data.
    """
    with _lock:
        st = _state.get(name) or {}
        ok_at, series = st.get("last_ok_at"), st.get("series")
    if series is None or ok_at is None:
        return None
    if _now() - ok_at > timedelta(hours=FRED_LKG_TTL_HOURS):
        return None
    return series


def _status_for(name: str) -> dict:
    st = _state.get(name) or {}
    critical = name in CRITICAL_FRED_SERIES
    misses = int(st.get("consecutive_misses", 0))
    ok_at = st.get("last_ok_at")
    value_at = st.get("last_value_at")

    age_h = None
    if ok_at is not None:
        age_h = round((_now() - ok_at).total_seconds() / 3600.0, 2)

    obs_age_d = None
    if value_at is not None:
        try:
            va = value_at if value_at.tzinfo else value_at.replace(
                tzinfo=timezone.utc)
            obs_age_d = (_now() - va).days
        except Exception:                                      # noqa: BLE001
            obs_age_d = None

    lag = _publication_lag_days(name)
    if ok_at is None:
        status = STATUS_UNAVAILABLE
    elif misses == 0:
        # Fetched this pass. FRESH only if the world has actually printed
        # recently enough for this series' own release schedule.
        status = (STATUS_FRESH if obs_age_d is None or obs_age_d <= lag * 2
                  else STATUS_STALE_USABLE)
    elif age_h is not None and age_h <= FRED_LKG_TTL_HOURS:
        status = STATUS_STALE_USABLE
    else:
        status = STATUS_DEGRADED_MISSING

    if (status == STATUS_STALE_USABLE and critical
            and misses >= FRED_DEGRADED_AFTER_MISSES):
        # Two consecutive passes is no longer a transient, whatever the TTL says.
        status = STATUS_DEGRADED_MISSING

    return {
        "series": name,
        "series_id": (config["data"].get("fred_series") or {}).get(name),
        "critical": critical,
        "status": status,
        "consecutive_misses": misses,
        "passes_seen": int(st.get("passes", 0)),
        "last_fetch_ok_at": ok_at.isoformat(timespec="seconds") if ok_at else None,
        "hours_since_last_ok": age_h,
        "last_observation_at": (str(getattr(value_at, "date", lambda: value_at)())
                                if value_at is not None else None),
        "last_observation_age_days": obs_age_d,
        "publication_lag_days": lag,
        "last_value": st.get("last_value"),
    }


def series_status(names: "list[str] | None" = None) -> dict:
    """Per-series health.

    NOTE ON SCOPE: this is PROCESS state. A restart clears it, and a series
    seen zero times reads UNAVAILABLE rather than pretending to remember. That
    is deliberate — the alternative is persisting a health claim that outlives
    the evidence for it.
    """
    names = list(names or (config["data"].get("fred_series") or {}).keys())
    return {n: _status_for(n) for n in names}


def degraded_reasons() -> list[str]:
    """What /api/health/full must page on. Named series, never a count."""
    out = []
    for name in CRITICAL_FRED_SERIES:
        s = _status_for(name)
        if s["status"] == STATUS_DEGRADED_MISSING:
            out.append(
                f"critical FRED series missing: {name} "
                f"({s['series_id']}) — {s['consecutive_misses']} consecutive "
                f"failed fetch pass(es), last good "
                f"{s['last_fetch_ok_at'] or 'never in this process'}")
        elif s["status"] == STATUS_UNAVAILABLE and s["passes_seen"] > 0:
            out.append(
                f"critical FRED series never loaded: {name} "
                f"({s['series_id']}) — no value has been fetched in this "
                f"process, so the model input does not exist")
    return out


def health() -> dict:
    """The block /api/health/full carries."""
    per = series_status()
    by_status: dict[str, list[str]] = {}
    for name, s in per.items():
        by_status.setdefault(s["status"], []).append(name)
    reasons = degraded_reasons()
    passes = fetch_passes()
    meta = _state.get("__pass__") or {}
    served_at = meta.get("recorded_fetch_at")
    served_age_h = None
    if isinstance(served_at, datetime):
        ref = served_at if served_at.tzinfo else served_at.replace(
            tzinfo=timezone.utc)
        served_age_h = round((_now() - ref).total_seconds() / 3600.0, 2)
    return {
        # UNKNOWN, not ok. Nothing has fetched in this process, so there is no
        # evidence either way and "ok" would be a claim rather than a reading.
        "status": ("UNKNOWN" if passes == 0
                   else ("ok" if not reasons else "DEGRADED")),
        "fetch_passes": passes,
        "last_no_fetch_reason": (_state.get("__pass__") or {}).get(
            "last_no_fetch_reason"),
        "critical_series": list(CRITICAL_FRED_SERIES),
        "lkg_ttl_hours": FRED_LKG_TTL_HOURS,
        "degraded_after_consecutive_misses": FRED_DEGRADED_AFTER_MISSES,
        "by_status": {k: sorted(v) for k, v in sorted(by_status.items())},
        "series": per,
        "degraded_reasons": reasons,
        # Provenance of the payload this reading describes. The FRED fetch is
        # cached for 24h, so the data being served is routinely older than the
        # process reporting on it; saying WHEN it was fetched is the difference
        # between a reading and a guess.
        "served_fetch_at": (served_at.isoformat(timespec="seconds")
                            if isinstance(served_at, datetime) else None),
        "served_age_hours": served_age_h,
        "served_from_cache": bool(meta.get("served_from_cache")),
        "scope": ("derived from the payload being served, which carries its own "
                  "fetch time — not from what this process happened to do. "
                  "Nothing is persisted: a series absent from that payload "
                  "reads UNAVAILABLE rather than remembering a claim whose "
                  "evidence is gone"),
    }


def last_substituted() -> list[str]:
    """Names the last `record_pass` served from last-known-good, not from FRESH
    data. The caller stores this alongside the payload it caches."""
    return list((_state.get("__pass__") or {}).get("substituted") or [])


def record_served(series_map: dict, fetched_at, series_ids: "dict | None" = None,
                  substituted: "list | None" = None) -> None:
    """Re-derive health from the payload actually being SERVED.

    Called on every read of the FRED payload, cache hit or cold fetch. It exists
    because `fetch_fred_data` is cached for 24h and the `@cached` decorator
    returns BEFORE the function body: a process that restarts into a warm cache
    serves 23 good series while `record_pass` never runs, so every series read
    UNAVAILABLE and `degraded_reasons` went silent on gaps that were still in
    the data. See `tests/test_fred_health_survives_restart.py`.

    This does NOT persist a health claim — the thing this module's scope note
    rightly refuses. It reads the artefact in hand. The payload carries its own
    `fetched_at`, so the age reported is the real one and a cache hit never
    manufactures a fresh fetch it did not perform.

    Idempotent by `fetched_at`: a pass already accounted for (by `record_pass`
    on the cold path, or by an earlier serve) is left exactly as it is.

    `substituted` names the series that were carried forward from last-known-good
    rather than fetched. They ARE in the payload, so without it a restart would
    report a carried-forward print as FRESH — trading a false alarm for a false
    reassurance, which is the worse direction. They are re-marked STALE_USABLE.
    The age shown for them is this pass's time rather than the original print's
    fetch time, which understates staleness slightly; the label is what carries
    the disclosure.
    """
    series_ids = series_ids or (config["data"].get("fred_series") or {})
    carried = set(substituted or [])
    with _lock:
        meta = _state.setdefault("__pass__", {})
        if fetched_at is not None and meta.get("recorded_fetch_at") == fetched_at:
            return
        meta["recorded_fetch_at"] = fetched_at
        meta["served_from_cache"] = True

    restored = 0
    for name in series_ids:
        got = (series_map or {}).get(name)
        if got is not None and len(got) > 0:
            try:
                last_idx = got.index[-1]
                last_value_at = getattr(
                    last_idx, "to_pydatetime", lambda: last_idx)()
                last_value = float(got.iloc[-1])
            except Exception:                                  # noqa: BLE001
                logger.error("FRED: %s is in the served payload but unreadable "
                             "— counting it as absent rather than FRESH", name)
                got = None
            else:
                with _lock:
                    st = _state.setdefault(name, {})
                    st.update({
                        "last_ok_at": fetched_at,
                        "last_value_at": last_value_at,
                        "last_value": last_value,
                        "series": got,
                        # A carried-forward print is present but is NOT this
                        # pass's data; one miss is what makes it STALE_USABLE.
                        "consecutive_misses": 1 if name in carried else 0,
                        "passes": max(int(st.get("passes", 0)), 1),
                    })
                restored += 1
                continue
        # Absent from the payload being served. One pass is known to have
        # happened (at `fetched_at`) and this series was not in its output, so
        # one miss is the honest count — and `passes_seen > 0` is what lets
        # `degraded_reasons` name a critical series that never loaded.
        with _lock:
            st = _state.setdefault(name, {})
            st.setdefault("last_ok_at", None)
            st["consecutive_misses"] = max(int(st.get("consecutive_misses", 0)), 1)
            st["passes"] = max(int(st.get("passes", 0)), 1)

    missing = len(series_ids) - restored
    logger.info("FRED: health re-derived from the served payload (%d/%d series "
                "present, fetched %s)", restored, len(series_ids), fetched_at)
    if missing:
        logger.warning("FRED: %d configured series are absent from the payload "
                       "being served — they stay visible for its whole TTL",
                       missing)


def record_pass(results: dict, series_ids: "dict | None" = None,
                fetched_at=None) -> dict:
    """Record one whole fetch pass and fill critical gaps from last known good.

    Returns the (possibly extended) results dict. A substituted series is
    LOGGED at WARNING and reported STALE_USABLE — the point of the fallback is
    that the composite keeps its input AND the reader is told, not that the gap
    disappears.

    `fetched_at` stamps this pass so that `record_served`, which runs on every
    read of the (cached) payload, recognises it as already accounted for and
    leaves it alone. Without that stamp a serve would immediately overwrite a
    STALE_USABLE substitution with FRESH.
    """
    series_ids = series_ids or (config["data"].get("fred_series") or {})
    substituted: list[str] = []
    for name in series_ids:
        got = results.get(name)
        arrived = False
        if got is not None and len(got) > 0:
            arrived = record_success(name, got)
            if not arrived:
                # Unreadable. It must not stay in `results` — a downstream
                # consumer would take an object we could not even read the last
                # value of as this pass's data.
                results.pop(name, None)
        else:
            record_miss(name)
        if arrived or name not in CRITICAL_FRED_SERIES:
            continue
        lkg = last_known_good(name)
        if lkg is not None:
            results[name] = lkg
            substituted.append(name)
        else:
            logger.error(
                "FRED: critical series %s (%s) failed and there is no last "
                "known good inside %dh — this is a MODEL INPUT DEGRADATION, "
                "not a temporary source miss", name,
                series_ids.get(name), FRED_LKG_TTL_HOURS)
    with _lock:
        meta = _state.setdefault("__pass__", {})
        # Which names in `results` are carried-forward prints rather than this
        # pass's data. The caller puts this in the cached payload so that a
        # later serve can keep calling them STALE_USABLE — see `record_served`.
        meta["substituted"] = list(substituted)
        if fetched_at is not None:
            meta["recorded_fetch_at"] = fetched_at
    if substituted:
        logger.warning(
            "FRED: %d critical series served from LAST KNOWN GOOD this pass "
            "(%s) — values are real prints carried forward, and every consumer "
            "sees them reported STALE_USABLE", len(substituted),
            ", ".join(sorted(substituted)))
    return results
