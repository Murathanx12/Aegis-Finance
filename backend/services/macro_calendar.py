"""THE MACRO HALF OF THE CATALYST CALENDAR — CPI, NFP and FOMC.

Chunk 14, spec `docs/research_notes/2026-09-13/spec_always_on_lab.md` section 3.4.
Murat, 2026-09-13: "upcoming dates and possibilities".

WHAT THIS ADDS, AND WHAT IT DELIBERATELY DOES NOT REBUILD
=========================================================
`pm_catalysts.py` already covers the per-ticker half (scheduled earnings from
Finnhub, free tier, cached 6 h, `HORIZON_DAYS=120`) and already NAMES what it
cannot cover in its `UNCOVERED` tuple — PDUFA dates, secondaries, 13D/G,
lockups, index adds and deletes, investor days. None of that is re-probed here;
no free source was found for any of it and finding one is later work, not this
module's.

This adds the MARKET-WIDE dates, in one block beside the per-ticker one:

* **CPI and the Employment Situation (NFP)** — FRED's `release/dates` endpoint,
  which publishes SCHEDULED future release dates, not just past ones. Same key
  and the same refusal-by-name pattern `market_sensor.py` already uses for
  `VIXCLS`: no key is `FRED_KEY_ABSENT`, a failed call is `FRED_FETCH_FAILED`,
  and neither is ever an empty list that a reader would take for "nothing is
  scheduled".
* **FOMC** — not a FRED series. The Fed publishes its own calendar as HTML, and
  scraping it is a fetcher nobody has probed. The honest shortcut is a static
  table a human refreshes once a year, exactly as `pm_catalysts` already lets a
  human write `catalysts:` by hand for FDA dates.

THE STATIC FOMC TABLE IS EMPTY UNTIL A HUMAN SEEDS IT
=====================================================
It ships EMPTY, and asking for FOMC dates returns `FOMC_SCHEDULE_NOT_SEEDED`
with the URL to copy from. Inventing eight plausible meeting dates would have
produced a calendar that looks complete and is wrong, and a wrong scheduled
date is worse than an absent one: a reader plans around it. The file is
`backend/data/fomc_schedule.json`, it carries `verified_on` and `source_url`,
and a table older than `STALE_AFTER_DAYS` is reported STALE rather than served
quietly.

SCENARIO PROBABILITIES ARE `null`, AND THAT IS THE HONEST STATE
==============================================================
The task asks for "the engine's scenario probabilities attached and graded
afterwards". `scenario_forecasts.py` (X3) is the contract for that and is NOT
wired — it needs L2's typed rows and E1's base-rate table, and L2 is still
PENDING_MODEL. So every entry carries `engine_probability: null` with
`probability_status: "AWAITING_L2"` rather than a number this repository cannot
yet produce. What ships is the calendar, on cadence, with every entry's
provenance and every gap named, which is most of the value before the
probabilities exist.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger("macro_calendar")

_FRED_BASE = "https://api.stlouisfed.org/fred"
_TIMEOUT = 12

#: How far ahead the macro calendar looks. Matches `pm_catalysts.HORIZON_DAYS`
#: on purpose: two horizons in one calendar is two calendars.
HORIZON_DAYS = 120

#: FRED release ids, from FRED's own release list. A wrong id produces a NAMED
#: fetch error rather than an empty list — which is the whole reason the ids
#: are declared here instead of being guessed at the call site.
FRED_RELEASES: dict = {
    "CPI": {"release_id": 10, "what": "Consumer Price Index (BLS)"},
    "NFP": {"release_id": 50, "what": "Employment Situation / non-farm payrolls (BLS)"},
}

#: Where a human pastes the Fed's own published schedule.
FOMC_SCHEDULE_FILE = "fomc_schedule.json"
FOMC_SOURCE_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

#: A hand-maintained table older than this is STALE, and says so. The Fed
#: publishes the following year's dates in the middle of the current one, so a
#: year-old table is missing meetings rather than merely dated.
STALE_AFTER_DAYS = 365

#: Cache TTL, matching `pm_catalysts.CACHE_TTL` — the calendar loop runs every
#: six hours and a second TTL would make the two blocks disagree about freshness.
CACHE_TTL = 6 * 3600


class MacroRefused(RuntimeError):
    """The macro calendar was not retrieved. Distinct from "nothing is scheduled"."""


def _today() -> date:
    return date.today()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def fomc_path() -> Path:
    return Path(_config.DATA_DIR) / FOMC_SCHEDULE_FILE


def _macro_event(kind: str, when: str, *, source: str, what: str,
                 detail: dict | None = None) -> dict:
    """One macro date, in the shape `pm_catalysts._event` uses for a ticker one.

    `engine_probability` is null by construction here: X3 is not wired, and a
    fabricated number attached to a real date is the one failure this block
    could cause that nobody would notice for months.
    """
    try:
        d = date.fromisoformat(str(when)[:10])
        days = (d - _today()).days
    except ValueError:
        d, days = None, None
    return {
        "kind": kind,
        "event_time": (d.isoformat() if d else None),
        "days_away": days,
        "source": source,
        "what": what,
        "expectedness": "scheduled",
        "engine_probability": None,
        "probability_status": "AWAITING_L2",
        "probability_note": (
            "X3 (`scenario_forecasts.py`) is the contract for an engine "
            "probability and is NOT wired: it needs L2's typed rows and E1's "
            "base-rate table, and L2 is still PENDING_MODEL. A number here "
            "would be invented."),
        "detail": detail or {},
    }


# ---------------------------------------------------------------- FRED releases


def _fred_get(path: str, params: dict) -> dict:
    """One FRED GET. Raises `MacroRefused` with the reason — never returns {}.

    Same shape as `pm_catalysts._finnhub`'s failure discipline: a 403 and a
    quiet month must never produce the same empty result. The key is read by
    NAME through `config.api_keys`, and its value never reaches a log line.
    """
    if not _config.api_keys.has("fred"):
        raise MacroRefused("FRED_KEY_ABSENT: FRED_API_KEY is unset or a "
                           "placeholder. The macro calendar is UNOBSERVED, not "
                           "empty, and no last-known value is substituted.")
    import requests
    try:
        r = requests.get(f"{_FRED_BASE}/{path}",
                         params={**params, "api_key": _config.api_keys.fred,
                                 "file_type": "json"},
                         timeout=_TIMEOUT)
    except Exception as exc:                                       # noqa: BLE001
        raise MacroRefused(
            f"FRED_FETCH_FAILED: {_config.api_keys.redact(str(exc))[:160]}") from exc
    if r.status_code != 200:
        raise MacroRefused(f"FRED_FETCH_FAILED: HTTP {r.status_code} from {path}")
    try:
        return r.json()
    except ValueError as exc:
        raise MacroRefused(f"FRED_FETCH_FAILED: {path} returned unparseable JSON") from exc


def release_dates(kind: str, *, horizon_days: int = HORIZON_DAYS,
                  fetch=None) -> list[dict]:
    """Scheduled release dates for one FRED release, from today forward.

    `include_release_dates_with_no_data=true` is what makes FRED return FUTURE
    dates: without it the endpoint answers only for releases that already have
    data, which is the past. A calendar that silently returned only history
    would be a calendar of things that already happened.
    """
    spec = FRED_RELEASES.get(kind)
    if spec is None:
        raise MacroRefused(f"UNKNOWN_RELEASE: {kind!r}; have {sorted(FRED_RELEASES)}")
    start = _today()
    payload = (fetch or _fred_get)(
        f"release/dates", {"release_id": spec["release_id"],
                           "include_release_dates_with_no_data": "true",
                           "sort_order": "asc",
                           "realtime_start": start.isoformat(),
                           "realtime_end": (start + timedelta(days=horizon_days)
                                            ).isoformat()})
    rows = (payload or {}).get("release_dates") or []
    out = []
    for row in rows:
        when = str(row.get("date") or "")[:10]
        if not when or when < start.isoformat():
            continue
        out.append(_macro_event(kind, when, source="fred_release_dates",
                                what=spec["what"],
                                detail={"release_id": spec["release_id"]}))
    return out


# ------------------------------------------------------------------ FOMC table


def fomc_table(path: Path | None = None) -> dict:
    """The hand-maintained Fed schedule, or a NAMED refusal.

    Three states, and the middle one is the one that matters: SEEDED (a table
    with a `verified_on` inside `STALE_AFTER_DAYS`), STALE (a table older than
    that, served WITH the warning rather than withheld — an old meeting list is
    still better than none, provided the reader is told), and NOT_SEEDED.
    """
    p = path or fomc_path()
    if not p.exists():
        return {"status": "FOMC_SCHEDULE_NOT_SEEDED", "dates": [],
                "path": str(p), "source_url": FOMC_SOURCE_URL,
                "how_to_seed": (
                    f"Copy the meeting dates from {FOMC_SOURCE_URL} into {p} as "
                    '{"verified_on": "<YYYY-MM-DD>", "source_url": "...", '
                    '"dates": ["<YYYY-MM-DD>", ...]}. They are NOT invented here: '
                    "a wrong scheduled date is worse than an absent one, because "
                    "a reader plans around it.")}
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "FOMC_SCHEDULE_UNREADABLE", "dates": [],
                "path": str(p), "why": f"{type(exc).__name__}: {exc}"[:200]}
    dates = [str(d)[:10] for d in (rec.get("dates") or [])]
    verified = str(rec.get("verified_on") or "")[:10]
    age = None
    if verified:
        try:
            age = (_today() - date.fromisoformat(verified)).days
        except ValueError:
            age = None
    status = "ok"
    if age is None:
        status = "FOMC_SCHEDULE_UNDATED"
    elif age > STALE_AFTER_DAYS:
        status = "FOMC_SCHEDULE_STALE"
    return {"status": status, "dates": sorted(dates), "verified_on": verified or None,
            "age_days": age, "path": str(p),
            "source_url": rec.get("source_url") or FOMC_SOURCE_URL,
            "stale_after_days": STALE_AFTER_DAYS}


def fomc_events(*, horizon_days: int = HORIZON_DAYS, path: Path | None = None) -> list[dict]:
    table = fomc_table(path)
    start = _today()
    end = start + timedelta(days=horizon_days)
    out = []
    for when in table.get("dates") or []:
        try:
            d = date.fromisoformat(when)
        except ValueError:
            continue
        if not (start <= d <= end):
            continue
        out.append(_macro_event("FOMC", when, source="fed_schedule_static",
                                what="FOMC statement and, on four of them, projections",
                                detail={"table_status": table["status"],
                                        "verified_on": table.get("verified_on")}))
    return out


# ------------------------------------------------------------------- the block


def macro_block(*, horizon_days: int = HORIZON_DAYS, fetch=None,
                fomc_file: Path | None = None) -> dict:
    """The `macro` block that sits beside `pm_catalysts.calendar()`'s per-ticker one.

    Never raises: a refused leg is a NAMED row in `refusals`, and the block is
    returned with whatever legs did answer. A macro calendar that raised because
    FRED had no key would take the earnings half down with it.
    """
    events: list[dict] = []
    refusals: list[dict] = []
    legs: dict = {}
    for kind in FRED_RELEASES:
        try:
            got = release_dates(kind, horizon_days=horizon_days, fetch=fetch)
        except MacroRefused as exc:
            refusals.append({"kind": kind, "refusal": str(exc)[:240]})
            legs[kind] = "REFUSED"
            continue
        events.extend(got)
        legs[kind] = f"{len(got)} date(s)"
    fomc = fomc_events(horizon_days=horizon_days, path=fomc_file)
    table = fomc_table(fomc_file)
    if table["status"] != "ok":
        refusals.append({"kind": "FOMC", "refusal": table["status"],
                         "detail": table.get("how_to_seed") or table.get("why")})
    events.extend(fomc)
    legs["FOMC"] = f"{len(fomc)} date(s) ({table['status']})"
    events.sort(key=lambda e: e["event_time"] or "9999")
    return {
        "macro": events,
        "legs": legs,
        "refusals": refusals,
        "horizon_days": horizon_days,
        "fomc_table": {k: table.get(k) for k in
                       ("status", "verified_on", "age_days", "source_url", "path")},
        "uncovered": ["ECB and BoJ decisions", "Treasury refunding",
                      "PCE and GDP release dates (FRED ids not declared here)",
                      "any intra-meeting action, by definition"],
        "utc": _now(),
        "note": ("`engine_probability` is null on every entry: X3 is not wired, "
                 "and a fabricated probability attached to a real date is the one "
                 "failure this block could cause that nobody would notice."),
    }


def calendar_extended(tickers: list[str], positions: dict | None = None, *,
                      fetch=None, fomc_file: Path | None = None) -> dict:
    """`pm_catalysts.calendar()` plus the macro block. The per-ticker half is
    CALLED, never re-implemented: two answers to "when are earnings" is one
    answer too many."""
    from backend.services import pm_catalysts
    base = pm_catalysts.calendar(tickers, positions)
    macro = macro_block(fetch=fetch, fomc_file=fomc_file)
    return {**base, **macro,
            "coverage": {**(base.get("coverage") or {}),
                         "macro_legs": macro["legs"],
                         "macro_refusals": macro["refusals"],
                         "macro_uncovered": macro["uncovered"]}}


__all__ = ["CACHE_TTL", "FOMC_SCHEDULE_FILE", "FOMC_SOURCE_URL", "FRED_RELEASES",
           "HORIZON_DAYS", "STALE_AFTER_DAYS", "MacroRefused", "calendar_extended",
           "fomc_events", "fomc_path", "fomc_table", "macro_block", "release_dates"]
