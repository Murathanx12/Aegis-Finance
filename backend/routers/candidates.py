"""
The Candidate Surface — `/api/candidates/*`  (READ-ONLY)
========================================================

Roadmap `docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 **H1**.

WHY THIS ROUTER EXISTS
======================
Mode A is Murat deciding with the machine beside him. The machine's half of
that conversation already exists on disk and has never been visible:

  * 3,056 potential-universe scorecards   `learner/potential_universe.py`
  * a 3,056-name tracker watchlist + status histogram   (execution repo)
  * the analyst-target band beside our own estimate      (both of the above)
  * the capital allocator's decision artefacts           `learner/allocator.py`

The grounding report (`docs/GROUNDING_2026-09-07_WEBSITE_AND_IDEAS.md` A.4-A.5)
lists all four under "web surface today: **NONE**". That is the single largest
product gap in the programme: the research exists and the human cannot see it.

WHAT THIS ROUTER IS NOT
=======================
It is READ-ONLY, and that is a load-bearing property rather than an accident of
the current feature set. No endpoint here writes a file, places an order, sizes
a position, mutates a book or appends to a receipt. Two tests prove it
(`backend/tests/test_candidates_router.py`): an HTTP-method audit over the
router's own route table, and a source scan for write verbs. If a future
session wants a write path, it belongs in a different router with a different
licence — not here.

VINTAGE IS A FIRST-CLASS FIELD
==============================
Every response carries a `vintage` block naming the as-of day of the artefact
it served, and a vintage that is behind the tape is stamped **STALE** rather
than served as if fresh. Three rules follow from things this programme has
already paid for:

1. **A vintage is dated by its OWN stamp, never by the filesystem.** CLAUDE.md
   §7: a gate that reads mtime is a gate on checkout time — on a fresh CI clone
   every file was "written today", and that kept finance CI red for two days.
   `vintage.dated_by` is the audit trail: it can only ever say
   `artefact_self_stamp` or `filename_stem`.
2. **Age is counted in US weekdays, on the US/Eastern clock.** The nightly job
   follows the tape; a calendar-day rule would paint every Monday red, and a
   gate that cannot go green is a broken gate.
3. **An unreachable source REFUSES rather than reads as empty.** The website
   backend cannot see the execution repo's `state/` from a container
   (grounding A.5 gap 9). An empty watchlist and an unreachable one are
   different facts, and a surface that conflates them is the house failure
   mode.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

from backend import config

router = APIRouter(prefix="/api/candidates", tags=["candidates"])
logger = logging.getLogger(__name__)

_NY = ZoneInfo("America/New_York")

#: Repeated verbatim on every response. `learner/allocator.py` earns its
#: SHADOW_ONLY line the same way, and a reader who lands on a candidate list
#: deserves to know they are looking at a file, not an instruction.
AUTHORITY = (
    "READ_ONLY — this surface serves artefacts that already exist on disk. "
    "It places nothing, sizes nothing, and writes nothing."
)

LICENCE = "PRODUCT_EXPERIMENT"

_DAY_LEN = 10


# ══════════════════════════════════════════════════════════════════════════
# Artefact cache — (mtime, size) keyed. No database (CLAUDE.md).
# ══════════════════════════════════════════════════════════════════════════

_CACHE: dict[str, tuple[tuple[int, int], Any]] = {}
_CACHE_LOCK = threading.Lock()


def _cached(path: Path, loader: Callable[[Path], Any]) -> Any:
    """Parse `path` at most once per (mtime, size); re-parse when it changes.

    The potential-universe vintage is 6.4 MB of JSONL and parsing it per
    request would make the page feel like a batch job. Size is in the key as
    well as mtime because a re-run of the nightly job can rewrite the same
    file inside the same mtime tick.
    """
    st = path.stat()
    key = (st.st_mtime_ns, st.st_size)
    ck = str(path)
    with _CACHE_LOCK:
        hit = _CACHE.get(ck)
        if hit is not None and hit[0] == key:
            return hit[1]
    value = loader(path)
    with _CACHE_LOCK:
        if len(_CACHE) >= config.CANDIDATE_CACHE_MAX_ENTRIES and ck not in _CACHE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[ck] = (key, value)
    return value


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> tuple[dict, list[dict]]:
    """Returns (header, rows). Line 1 of a potential-universe vintage is a
    header; a tracker day file has no header and every line is a row."""
    header: dict = {}
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if i == 0 and isinstance(obj, dict) and "artefact" in obj and "symbol" not in obj:
                header = obj
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return header, rows


# ══════════════════════════════════════════════════════════════════════════
# Vintage / staleness
# ══════════════════════════════════════════════════════════════════════════

def _today_et() -> _dt.date:
    """Today on the tape's clock. The dev machine runs UTC+8 and the scheduler
    runs US/Eastern; comparing a US trading day against a UTC+8 date makes
    every vintage look a day fresher than it is for eight hours a day."""
    return _dt.datetime.now(tz=_NY).date()


def _now_utc_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat(timespec="seconds")


def _is_day(s: Any) -> bool:
    if not isinstance(s, str) or len(s) != _DAY_LEN:
        return False
    try:
        _dt.date.fromisoformat(s)
    except ValueError:
        return False
    return True


def _weekdays_between(older: _dt.date, newer: _dt.date) -> int:
    """Mon-Fri days strictly after `older`, up to and including `newer`.

    No holiday calendar is consulted, so the session after a market holiday
    reads one weekday older than it truly is. A false STALE is the safe side
    of this error: it over-warns, it never under-warns.
    """
    if newer <= older:
        return 0
    n = 0
    d = older + _dt.timedelta(days=1)
    while d <= newer:
        if d.weekday() < 5:
            n += 1
        d += _dt.timedelta(days=1)
    return n


def _vintage(
    artefact: str,
    *,
    day: str | None,
    dated_by: str | None,
    generated_at_utc: str | None = None,
    source: Path | str | None = None,
    status: str = "OK",
    note: str | None = None,
) -> dict:
    """The vintage block carried by every response."""
    today = _today_et()
    out: dict[str, Any] = {
        "artefact": artefact,
        "status": status,
        "day": day,
        "dated_by": dated_by,
        "generated_at_utc": generated_at_utc,
        "source": str(source) if source is not None else None,
        "as_of_et": today.isoformat(),
        "as_of_utc": _now_utc_iso(),
        "fresh_max_age_weekdays": config.CANDIDATE_VINTAGE_FRESH_MAX_AGE_WEEKDAYS,
    }
    if status != "OK" or not _is_day(day):
        out.update({
            "age_calendar_days": None,
            "age_weekdays": None,
            "freshness": "CANNOT_DETERMINE",
            "stale": None,
            "stale_reason": note or (
                f"no readable vintage for `{artefact}`; freshness is reported "
                f"as CANNOT_DETERMINE rather than guessed"
            ),
        })
        return out

    d = _dt.date.fromisoformat(str(day))
    cal = (today - d).days
    wd = _weekdays_between(d, today)
    fresh = wd <= config.CANDIDATE_VINTAGE_FRESH_MAX_AGE_WEEKDAYS
    out.update({
        "age_calendar_days": cal,
        "age_weekdays": wd,
        "freshness": "FRESH" if fresh else "STALE",
        "stale": not fresh,
        "stale_reason": None if fresh else (
            f"vintage {day} is {wd} US weekdays behind {today.isoformat()}; the "
            f"nightly job is expected to run at most "
            f"{config.CANDIDATE_VINTAGE_FRESH_MAX_AGE_WEEKDAYS} weekday behind. "
            f"Serve it, but do not read it as today's opinion."
        ),
    })
    if note:
        out["note"] = note
    return out


def _worst(levels: list[str]) -> str:
    for level in ("STALE", "CANNOT_DETERMINE", "FRESH"):
        if level in levels:
            return level
    return "CANNOT_DETERMINE"


# ══════════════════════════════════════════════════════════════════════════
# Sources
# ══════════════════════════════════════════════════════════════════════════

def _days_in(directory: Path, suffix: str) -> list[str]:
    if not directory.is_dir():
        return []
    out = []
    for p in directory.glob(f"*{suffix}"):
        stem = p.name[: -len(suffix)]
        if _is_day(stem):
            out.append(stem)
    return sorted(out)


def _pu_days() -> list[str]:
    return _days_in(config.CANDIDATE_POTENTIAL_UNIVERSE_DIR, ".jsonl")


def _tracker_days() -> list[str]:
    return _days_in(config.CANDIDATE_TRACKER_DIR, ".jsonl")


def _artifact_days() -> list[str]:
    d = config.CANDIDATE_DECISION_ARTIFACT_DIR
    if not d.is_dir():
        return []
    days = {p.name.split("_", 1)[0] for p in d.glob("*.json")}
    return sorted(x for x in days if _is_day(x))


_TRACKER_UNREACHABLE = (
    "the execution repo's state/tracker directory is not reachable from this "
    "backend (grounding A.5 gap 9). Set AEGIS_TERMINAL_STATE_DIR, or wait for "
    "the H5 state reader. This is NOT an empty watchlist."
)


def _load_potential_universe(day: str | None):
    """Returns (day, header, scorecards, vintage)."""
    days = _pu_days()
    if not days:
        return None, {}, [], _vintage(
            "potential_universe", day=None, dated_by=None,
            source=config.CANDIDATE_POTENTIAL_UNIVERSE_DIR, status="ABSENT",
            note="no potential-universe vintage on disk; run "
                 "`python -m scripts.potential_universe_run`")
    if day is None:
        day = days[-1]
    elif day not in days:
        raise HTTPException(
            status_code=404,
            detail=f"no potential-universe vintage for {day}. Available: {days}")
    path = config.CANDIDATE_POTENTIAL_UNIVERSE_DIR / f"{day}.jsonl"
    try:
        header, rows = _cached(path, _read_jsonl)
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail=f"vintage {day} unreadable: {exc}") from exc
    # Rule 1: the day comes from the artefact's own header, else from the
    # filename it declared itself with — never from the file's modification
    # time. A test in `test_candidates_router.py` enforces that the filesystem
    # clock is readable in exactly one function (`_cached`, for invalidation),
    # and it is not this one.
    hd = header.get("day")
    if _is_day(hd):
        stamp_day, dated_by = str(hd), "artefact_self_stamp"
    else:
        stamp_day, dated_by = day, "filename_stem"
    vin = _vintage("potential_universe", day=stamp_day, dated_by=dated_by,
                   generated_at_utc=header.get("generated_at_utc"), source=path)
    vin["version"] = header.get("version")
    vin["licence"] = header.get("licence")
    vin["broker_authority"] = header.get("broker_authority")
    vin["header_status"] = header.get("status")
    vin["available_days"] = days
    return day, header, rows, vin


def _load_tracker_day(day: str | None):
    """Returns (day, {symbol: row}, vintage). Unreachable is a named REFUSAL."""
    d = config.CANDIDATE_TRACKER_DIR
    if not d.is_dir():
        return None, {}, _vintage("tracker_day", day=None, dated_by=None, source=d,
                                  status="NOT_REACHABLE", note=_TRACKER_UNREACHABLE)
    days = _tracker_days()
    if not days:
        return None, {}, _vintage(
            "tracker_day", day=None, dated_by=None, source=d, status="ABSENT",
            note="tracker directory reachable but holds no day files")
    if day is None or day not in days:
        # The potential universe is built FROM a tracker day. If that exact day
        # is gone, fall back to the newest and say so — silently serving a
        # different day's targets beside this day's scorecards would be the
        # lookahead the whole surface exists to avoid.
        requested, day = day, days[-1]
    else:
        requested = day
    path = d / f"{day}.jsonl"
    try:
        _, rows = _cached(path, _read_jsonl)
    except OSError as exc:
        return None, {}, _vintage("tracker_day", day=day, dated_by="filename_stem",
                                  source=path, status="UNREADABLE", note=str(exc))
    by_symbol = {r["symbol"]: r for r in rows if isinstance(r.get("symbol"), str)}
    row_day = next((r.get("day") for r in rows if _is_day(r.get("day"))), None)
    observed = next((r.get("observed_at") for r in rows if r.get("observed_at")), None)
    note = None
    if requested is not None and requested != day:
        note = (f"tracker day {requested} is not on disk; served {day} instead. "
                f"The band legs on this page are from a DIFFERENT day than the "
                f"scorecards.")
    vin = _vintage("tracker_day",
                   day=str(row_day) if row_day else day,
                   dated_by="artefact_self_stamp" if row_day else "filename_stem",
                   generated_at_utc=observed, source=path, note=note)
    vin["available_days"] = days[-10:]
    vin["day_matches_universe"] = requested is None or requested == day

    # A tracker DAY FILE carries raw fields only — no `status`, no `upside`, no
    # `consensus`, no `past_winner`. Those are computed once into
    # `latest.json`'s candidate list (806 of 3,056 names on 2026-09-02), so the
    # human-readable "why is this a candidate" columns exist for the candidates
    # and nowhere else. Overlay them, but ONLY when `latest.json` is the same
    # day: pasting one day's BUY/SELL beside another day's targets is exactly
    # the kind of quiet mismatch this surface exists to make visible.
    summary, candidates, _ = _load_tracker_summary()
    overlay_day = summary.get("day")
    applied = _is_day(overlay_day) and str(overlay_day) == str(vin["day"])
    n_overlaid = 0
    if applied:
        for c in candidates:
            if not isinstance(c, dict):
                continue
            sym = c.get("symbol")
            if isinstance(sym, str):
                by_symbol[sym] = {**by_symbol.get(sym, {}), **c}
                n_overlaid += 1
    vin["status_overlay"] = {
        "applied": applied,
        "n_rows_overlaid": n_overlaid,
        "overlay_day": overlay_day,
        "source": "tracker/latest.json candidates",
        "fields": ["status", "status_reasons", "status_blocked_by", "upside",
                   "consensus", "coverage", "past_winner", "drawdown_60d"],
        "reason": None if applied else (
            f"latest.json is day {overlay_day!r} but the served tracker day is "
            f"{vin['day']!r}; the status/consensus columns are LEFT EMPTY rather "
            f"than filled from a different day"),
    }
    return day, by_symbol, vin


def _load_tracker_summary():
    """`latest.json` — the summary (status histogram) plus the candidate list."""
    d = config.CANDIDATE_TRACKER_DIR
    if not d.is_dir():
        return {}, [], _vintage("tracker_watchlist", day=None, dated_by=None,
                                source=d, status="NOT_REACHABLE",
                                note=_TRACKER_UNREACHABLE)
    path = d / "latest.json"
    if not path.is_file():
        return {}, [], _vintage("tracker_watchlist", day=None, dated_by=None,
                                source=path, status="ABSENT",
                                note="tracker/latest.json has never been written")
    try:
        blob = _cached(path, _read_json)
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [], _vintage("tracker_watchlist", day=None, dated_by=None,
                                source=path, status="UNREADABLE",
                                note=f"{type(exc).__name__}: {exc}")
    summary = blob.get("summary") or {}
    candidates = blob.get("candidates") or []
    day = summary.get("day")
    vin = _vintage("tracker_watchlist",
                   day=str(day) if _is_day(day) else None,
                   dated_by="artefact_self_stamp" if _is_day(day) else None,
                   generated_at_utc=summary.get("generated_utc"), source=path,
                   status="OK" if _is_day(day) else "UNREADABLE")
    vin["schema"] = summary.get("schema")
    return summary, candidates, vin


def _load_decision_artifacts(day: str | None):
    d = config.CANDIDATE_DECISION_ARTIFACT_DIR
    days = _artifact_days()
    if not days:
        return None, {}, _vintage("decision_artifacts", day=None, dated_by=None,
                                  source=d, status="ABSENT",
                                  note="no allocator artefact on disk; run "
                                       "`python -m scripts.allocator_run`")
    if day is None:
        day = days[-1]
    elif day not in days:
        raise HTTPException(status_code=404,
                            detail=f"no decision artefact for {day}. Available: {days}")
    out: dict[str, dict] = {}
    for p in sorted(d.glob(f"{day}_*.json")):
        personality = p.name[len(day) + 1: -len(".json")]
        try:
            out[personality] = _cached(p, _read_json)
        except (OSError, json.JSONDecodeError) as exc:
            out[personality] = {"unreadable": True,
                                "error": f"{type(exc).__name__}: {exc}"}
    stamp = next((a.get("day") for a in out.values() if _is_day(a.get("day"))), None)
    vin = _vintage("decision_artifacts",
                   day=str(stamp) if stamp else day,
                   dated_by="artefact_self_stamp" if stamp else "filename_stem",
                   generated_at_utc=next((a.get("generated_at_utc")
                                          for a in out.values()
                                          if a.get("generated_at_utc")), None),
                   source=d)
    vin["personalities"] = sorted(out)
    vin["available_days"] = days
    return day, out, vin


# ══════════════════════════════════════════════════════════════════════════
# Row shaping
# ══════════════════════════════════════════════════════════════════════════

def _f(x: Any) -> float | None:
    """float or None. NaN becomes None: `NaN` is not JSON and a chart that
    plots it draws a hole that reads as a zero."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _band_block(tr: dict | None, ep: dict, tracker_status: str) -> dict:
    """The analyst-target band. `ratio = mean_target / close`, `upside = ratio-1`
    (the vintage's own convention). The low/high legs live on the tracker row
    and are absent when the execution repo is not reachable."""
    if tr is None:
        return {"status": tracker_status if tracker_status != "OK" else "MISSING",
                "ratio": _f(ep.get("ratio")), "upside": _f(ep.get("upside")),
                "band_label": ep.get("band"),
                "close": None, "target_low": None, "target_mean": None,
                "target_high": None, "upside_low": None, "upside_high": None,
                "n_analysts": None, "coverage": None, "consensus": None,
                "target_source": None, "target_status": None,
                "note": "the low/high legs need the tracker row; only the "
                        "vintage's own ratio/upside are available"}
    close = _f(tr.get("close"))
    lo = _f(tr.get("target_low"))
    mean = _f(tr.get("mean_target"))
    hi = _f(tr.get("target_high"))
    return {
        "status": "OK",
        "close": close,
        "target_low": lo, "target_mean": mean, "target_high": hi,
        "ratio": _f(ep.get("ratio")), "upside": _f(ep.get("upside")),
        "upside_low": (lo / close - 1.0) if (lo and close) else None,
        "upside_high": (hi / close - 1.0) if (hi and close) else None,
        "band_label": ep.get("band"),
        "n_analysts": tr.get("n_analysts_yf"),
        "coverage": tr.get("coverage"),
        "consensus": _f(tr.get("consensus")),
        "target_source": tr.get("target_source"),
        "target_status": tr.get("target_status"),
    }


def _estimate_block(sc: dict) -> dict:
    """Our own estimate beside the street's. Every leg keeps its refusal —
    a REFUSED learner is a fact about the pipeline, not a missing number."""
    ep = sc.get("engine_prior") or {}
    v1 = sc.get("learner_v1") or {}
    pb = sc.get("p_beat") or {}
    v2 = sc.get("learner_v2") or {}
    st = sc.get("state") or {}
    return {
        "engine_prior_1m": _f(ep.get("prior_1m")),
        "learner_v1": {"status": v1.get("status"), "score": _f(v1.get("score")),
                       "unit": v1.get("unit"),
                       "reasons": v1.get("reasons") or [],
                       "missing_inputs": v1.get("missing_inputs") or []},
        "p_beat": {"status": pb.get("status"), "raw": _f(pb.get("raw")),
                   "debiased": _f(pb.get("debiased")),
                   "base_rate": _f(pb.get("base_rate")),
                   "vs_base_rate": _f(pb.get("vs_base_rate"))},
        "learner_v2": {"status": v2.get("status"), "reason": v2.get("reason"),
                       "champion": v2.get("champion")},
        "state": {"status": st.get("status"), "reason": st.get("reason")},
    }


def _row(sc: dict, tr: dict | None, tracker_status: str) -> dict:
    ep = sc.get("engine_prior") or {}
    ident = sc.get("identity") or {}
    ex = sc.get("execution") or {}
    dis = sc.get("disagreement") or {}
    dtc = sc.get("days_to_catalyst") or {}
    reasons = list(ep.get("reasons") or [])
    t = tr or {}
    return {
        "symbol": sc.get("symbol"),
        "day": sc.get("day"),
        "observed_at": sc.get("observed_at"),
        "sector": ident.get("sector"),
        "exchange": ident.get("exchange"),
        "tradable": ident.get("tradable"),
        "shortable": ident.get("shortable"),
        "reason": {
            "verdict": ep.get("verdict"),
            "band": ep.get("band"),
            "headline": reasons[0] if reasons else None,
            "engine_reasons": reasons,
            "tracker_status": t.get("status"),
            "tracker_reasons": t.get("status_reasons") or [],
            "tracker_blocked_by": t.get("status_blocked_by") or [],
        },
        "band": _band_block(tr, ep, tracker_status),
        "our_estimate": _estimate_block(sc),
        "disagreement": {"verdict": dis.get("verdict"),
                         "engine_stance": dis.get("engine_stance"),
                         "learner_stance": dis.get("learner_stance"),
                         "sign_disagreement": dis.get("sign_disagreement"),
                         "rank_gap": _f(dis.get("rank_gap"))},
        "execution": {"tier": ex.get("tier"), "observe_only": ex.get("observe_only"),
                      "max_usd": _f(ex.get("max_usd")),
                      "median_dollar_volume": _f(ex.get("median_dollar_volume")),
                      "reason": ex.get("reason")},
        "days_to_catalyst": {"readable": dtc.get("readable"),
                             "value": _f(dtc.get("value")),
                             "units": dtc.get("units")},
        "market_cap_usd": _f(t.get("market_cap_usd")),
        "ret_12m": _f(t.get("ret_12m")),
        "drawdown_60d": _f(t.get("drawdown_60d")),
        "realised_vol_20d": _f(t.get("realised_vol_20d")),
        "past_winner": t.get("past_winner"),
        "pit": sc.get("pit") or {},
        "falsifiers": sc.get("falsifiers") or [],
    }


# Sort keys are a CLOSED set: an unknown one is a 422, never a silent fallback
# to insertion order that would let the page claim to be sorted when it is not.
_SORT: dict[str, Callable[[dict], Any]] = {
    "symbol": lambda r: r.get("symbol") or "",
    "upside": lambda r: r["band"]["upside"],
    "ratio": lambda r: r["band"]["ratio"],
    "upside_low": lambda r: r["band"]["upside_low"],
    "coverage": lambda r: r["band"]["coverage"],
    "p_beat": lambda r: r["our_estimate"]["p_beat"]["debiased"],
    "vs_base_rate": lambda r: r["our_estimate"]["p_beat"]["vs_base_rate"],
    "learner_score": lambda r: r["our_estimate"]["learner_v1"]["score"],
    "engine_prior_1m": lambda r: r["our_estimate"]["engine_prior_1m"],
    "rank_gap": lambda r: r["disagreement"]["rank_gap"],
    "days_to_catalyst": lambda r: (r.get("days_to_catalyst") or {}).get("value"),
    "dollar_volume": lambda r: r["execution"]["median_dollar_volume"],
    "market_cap": lambda r: r.get("market_cap_usd"),
    "ret_12m": lambda r: r.get("ret_12m"),
    "drawdown_60d": lambda r: r.get("drawdown_60d"),
}

_VERDICTS = ("unreadable", "no_opinion", "toxic_ge_5", "sub_floor", "admitted_shadow")
_TIERS = ("CANNOT_DETERMINE", "NONE", "OBSERVE_ONLY", "FULL")
_STATUSES = ("STRONG_BUY", "BUY", "WATCH", "SELL")


def _csv(value: str | None, allowed: tuple[str, ...], name: str) -> set[str] | None:
    if value is None or not value.strip():
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    bad = [p for p in parts if p not in allowed]
    if bad:
        raise HTTPException(status_code=422,
                            detail=f"unknown {name}: {bad}. Allowed: {list(allowed)}")
    return set(parts)


def _sort_rows(rows: list[dict], sort: str, direction: str) -> list[dict]:
    """Sort, with missing values LAST in both directions.

    A `None` that floats to the top of a "highest upside" list is a name with
    no analyst target pretending to be the best idea on the page.
    """
    keyfn = _SORT[sort]
    present, missing = [], []
    for r in rows:
        (present if keyfn(r) is not None else missing).append(r)
    present.sort(key=keyfn, reverse=(direction == "desc"))
    missing.sort(key=lambda r: r.get("symbol") or "")
    return present + missing


# ══════════════════════════════════════════════════════════════════════════
# Endpoints — every one of them GET
# ══════════════════════════════════════════════════════════════════════════

@router.get("/vintages")
async def get_vintages() -> dict:
    """Every artefact this surface serves, with its as-of day and freshness.

    Read this endpoint FIRST. On 2026-09-07 all four sources were stale at
    2026-09-02 and nothing on the website said so.
    """
    _, pu_header, pu_rows, pu_vin = _load_potential_universe(None)
    _, _, tr_vin = _load_tracker_day(None)
    summary, candidates, wl_vin = _load_tracker_summary()
    _, _artefacts, da_vin = _load_decision_artifacts(None)

    pu_vin["n_scorecards"] = len(pu_rows)
    pu_vin["counts"] = pu_header.get("counts") or {}
    pu_vin["whole_universe_refusals"] = {
        k: {"refused_on": v.get("refused_on"), "of": v.get("of"),
            "reason": v.get("reason")}
        for k, v in (pu_header.get("whole_universe_refusals") or {}).items()
        if isinstance(v, dict)
    }
    pu_vin["field_readability"] = pu_header.get("field_readability") or {}
    wl_vin["status_histogram"] = summary.get("status_histogram")
    wl_vin["n_candidates"] = summary.get("n_candidates", len(candidates))
    wl_vin["n_symbols"] = summary.get("n_symbols")

    vins = [pu_vin, tr_vin, wl_vin, da_vin]
    return {
        "version": config.CANDIDATE_SURFACE_VERSION,
        "licence": LICENCE,
        "authority": AUTHORITY,
        "as_of_utc": _now_utc_iso(),
        "as_of_et": _today_et().isoformat(),
        "worst_freshness": _worst([v["freshness"] for v in vins]),
        "any_stale": any(v.get("stale") for v in vins),
        "sources": {
            "potential_universe": pu_vin,
            "tracker_day": tr_vin,
            "tracker_watchlist": wl_vin,
            "decision_artifacts": da_vin,
        },
        "how_to_refresh": {
            "potential_universe": "python -m scripts.potential_universe_run",
            "decision_artifacts": "python -m scripts.allocator_run",
            "tracker": "python -m scripts.tracker --refresh   (EXECUTION repo; "
                       "the potential universe can never be fresher than the "
                       "tracker day file it reads)",
        },
    }


@router.get("/universe")
async def get_universe(
    day: str | None = Query(None, min_length=_DAY_LEN, max_length=_DAY_LEN),
    verdict: str | None = Query(None, description=f"csv of {list(_VERDICTS)}"),
    tier: str | None = Query(None, description=f"csv of {list(_TIERS)}"),
    status: str | None = Query(None, description=f"tracker status, csv of {list(_STATUSES)}"),
    sector: str | None = Query(None),
    q: str | None = Query(None, description="symbol prefix, case-insensitive"),
    min_upside: float | None = Query(None, ge=-1.0),
    max_upside: float | None = Query(None),
    min_p_beat: float | None = Query(None, ge=0.0, le=1.0),
    min_dollar_volume: float | None = Query(None, ge=0.0),
    max_days_to_catalyst: float | None = Query(None, ge=0.0),
    disagreement_only: bool = Query(False),
    catalyst_readable_only: bool = Query(False),
    sort: str = Query("upside"),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(config.CANDIDATE_PAGE_DEFAULT_LIMIT, ge=1,
                       le=config.CANDIDATE_PAGE_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict:
    """The candidate list: one row per observable company-vintage.

    Filters are AND-ed. Every response names the vintage it was computed from
    and the filters actually applied, so a screenshot is reproducible.
    """
    if day is not None and not _is_day(day):
        raise HTTPException(status_code=422, detail=f"day must be YYYY-MM-DD, got {day!r}")
    if sort not in _SORT:
        raise HTTPException(status_code=422,
                            detail=f"unknown sort {sort!r}. Allowed: {sorted(_SORT)}")
    verdicts = _csv(verdict, _VERDICTS, "verdict")
    tiers = _csv(tier, _TIERS, "tier")
    statuses = _csv(status, _STATUSES, "status")

    pu_day, header, scorecards, pu_vin = _load_potential_universe(day)
    _, tracker_by_symbol, tr_vin = _load_tracker_day(pu_day)
    tracker_status = tr_vin["status"]

    rows: list[dict] = []
    for sc in scorecards:
        ep = sc.get("engine_prior") or {}
        ex = sc.get("execution") or {}
        ident = sc.get("identity") or {}
        sym = sc.get("symbol") or ""
        if verdicts and ep.get("verdict") not in verdicts:
            continue
        if tiers and ex.get("tier") not in tiers:
            continue
        if sector and (ident.get("sector") or "") != sector:
            continue
        if q and not sym.upper().startswith(q.upper()):
            continue
        tr = tracker_by_symbol.get(sym)
        if statuses and (tr or {}).get("status") not in statuses:
            continue
        up = _f(ep.get("upside"))
        if min_upside is not None and (up is None or up < min_upside):
            continue
        if max_upside is not None and (up is None or up > max_upside):
            continue
        pbd = _f((sc.get("p_beat") or {}).get("debiased"))
        if min_p_beat is not None and (pbd is None or pbd < min_p_beat):
            continue
        dv = _f(ex.get("median_dollar_volume"))
        if min_dollar_volume is not None and (dv is None or dv < min_dollar_volume):
            continue
        dtc = sc.get("days_to_catalyst") or {}
        if catalyst_readable_only and not dtc.get("readable"):
            continue
        if max_days_to_catalyst is not None:
            v = _f(dtc.get("value"))
            if v is None or v > max_days_to_catalyst:
                continue
        if disagreement_only and not (sc.get("disagreement") or {}).get("sign_disagreement"):
            continue
        rows.append(_row(sc, tr, tracker_status))

    rows = _sort_rows(rows, sort, dir)
    page = rows[offset: offset + limit]

    return {
        "version": config.CANDIDATE_SURFACE_VERSION,
        "licence": LICENCE,
        "authority": AUTHORITY,
        "vintage": pu_vin,
        "tracker_vintage": tr_vin,
        "stale": bool(pu_vin.get("stale")) or bool(tr_vin.get("stale")),
        "n_scorecards": len(scorecards),
        "n_matched": len(rows),
        "n_returned": len(page),
        "offset": offset,
        "limit": limit,
        "sort": {"key": sort, "dir": dir,
                 "missing_values": "sorted last in both directions"},
        "filters": {
            "day": pu_day,
            "verdict": sorted(verdicts) if verdicts else None,
            "tier": sorted(tiers) if tiers else None,
            "status": sorted(statuses) if statuses else None,
            "sector": sector, "q": q,
            "min_upside": min_upside, "max_upside": max_upside,
            "min_p_beat": min_p_beat, "min_dollar_volume": min_dollar_volume,
            "max_days_to_catalyst": max_days_to_catalyst,
            "disagreement_only": disagreement_only,
            "catalyst_readable_only": catalyst_readable_only,
        },
        "facets": {
            "verdicts": list(_VERDICTS), "tiers": list(_TIERS),
            "statuses": list(_STATUSES), "sorts": sorted(_SORT),
            "sectors": sorted({(sc.get("identity") or {}).get("sector")
                               for sc in scorecards
                               if (sc.get("identity") or {}).get("sector")}),
        },
        "counts": header.get("counts") or {},
        "whole_universe_refusals": header.get("whole_universe_refusals") or {},
        "field_readability": header.get("field_readability") or {},
        "conventions": header.get("conventions") or {},
        "rows": page,
    }


@router.get("/universe/{symbol}")
async def get_candidate(
    symbol: str,
    day: str | None = Query(None, min_length=_DAY_LEN, max_length=_DAY_LEN),
) -> dict:
    """One name: its scorecard, its tracker row, and the refusals behind both."""
    sym = (symbol or "").strip().upper()
    if not sym or len(sym) > 12 or not sym.replace(".", "").replace("-", "").isalnum():
        raise HTTPException(status_code=422, detail=f"invalid symbol {symbol!r}")
    if day is not None and not _is_day(day):
        raise HTTPException(status_code=422, detail=f"day must be YYYY-MM-DD, got {day!r}")

    pu_day, header, scorecards, pu_vin = _load_potential_universe(day)
    sc = next((s for s in scorecards if (s.get("symbol") or "").upper() == sym), None)
    if sc is None:
        raise HTTPException(status_code=404,
                            detail=f"{sym} is not in the {pu_day} potential universe")
    _, tracker_by_symbol, tr_vin = _load_tracker_day(pu_day)
    tr = tracker_by_symbol.get(sc.get("symbol") or sym)
    return {
        "version": config.CANDIDATE_SURFACE_VERSION,
        "licence": LICENCE,
        "authority": AUTHORITY,
        "vintage": pu_vin,
        "tracker_vintage": tr_vin,
        "stale": bool(pu_vin.get("stale")) or bool(tr_vin.get("stale")),
        "row": _row(sc, tr, tr_vin["status"]),
        "scorecard": sc,
        "tracker_row": tr,
        "conventions": header.get("conventions") or {},
    }


@router.get("/watchlist")
async def get_watchlist(
    status: str | None = Query(None, description=f"csv of {list(_STATUSES)}"),
    sector: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(config.CANDIDATE_PAGE_DEFAULT_LIMIT, ge=1,
                       le=config.CANDIDATE_PAGE_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict:
    """The whole-market tracker watchlist and its status histogram.

    An unreachable execution repo returns 200 with `vintage.status`
    NOT_REACHABLE and zero rows — a named refusal, not an empty watchlist.
    """
    statuses = _csv(status, _STATUSES, "status")
    summary, candidates, vin = _load_tracker_summary()
    rows = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        if statuses and c.get("status") not in statuses:
            continue
        if sector and (c.get("sector") or "") != sector:
            continue
        if q and not (c.get("symbol") or "").upper().startswith(q.upper()):
            continue
        rows.append(c)
    rows.sort(key=lambda c: (-(_f(c.get("upside")) if _f(c.get("upside")) is not None
                              else -1e18), c.get("symbol") or ""))
    page = rows[offset: offset + limit]
    return {
        "version": config.CANDIDATE_SURFACE_VERSION,
        "licence": LICENCE,
        "authority": AUTHORITY,
        "vintage": vin,
        "stale": bool(vin.get("stale")),
        "summary": summary,
        "status_histogram": summary.get("status_histogram") or {},
        "n_symbols": summary.get("n_symbols"),
        "n_candidates": summary.get("n_candidates", len(candidates)),
        "n_matched": len(rows),
        "n_returned": len(page),
        "offset": offset,
        "limit": limit,
        "facets": {"statuses": list(_STATUSES),
                   "sectors": sorted({c.get("sector") for c in candidates
                                      if isinstance(c, dict) and c.get("sector")})},
        "rows": page,
    }


@router.get("/bands")
async def get_bands(
    day: str | None = Query(None, min_length=_DAY_LEN, max_length=_DAY_LEN),
    band: str | None = Query(None, description="band label, e.g. toxic_ge_5"),
    min_coverage: int = Query(0, ge=0),
    sort: str = Query("upside"),
    dir: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(config.CANDIDATE_PAGE_DEFAULT_LIMIT, ge=1,
                       le=config.CANDIDATE_PAGE_MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> dict:
    """The analyst-target band beside our own estimate, one row per name.

    Carries the vintage's own `band_status` caveat verbatim: on the
    point-in-time panel NO band survives BH-FDR. A page that ranks by street
    upside without that sentence beside it is selling a factor that was
    measured not to exist.
    """
    if day is not None and not _is_day(day):
        raise HTTPException(status_code=422, detail=f"day must be YYYY-MM-DD, got {day!r}")
    if sort not in _SORT:
        raise HTTPException(status_code=422,
                            detail=f"unknown sort {sort!r}. Allowed: {sorted(_SORT)}")

    pu_day, header, scorecards, pu_vin = _load_potential_universe(day)
    _, tracker_by_symbol, tr_vin = _load_tracker_day(pu_day)

    rows: list[dict] = []
    for sc in scorecards:
        ep = sc.get("engine_prior") or {}
        if band and ep.get("band") != band:
            continue
        r = _row(sc, tracker_by_symbol.get(sc.get("symbol") or ""), tr_vin["status"])
        cov = r["band"].get("coverage")
        if min_coverage and (cov is None or cov < min_coverage):
            continue
        rows.append(r)

    rows = _sort_rows(rows, sort, dir)
    page = [{"symbol": r["symbol"], "sector": r["sector"], "band": r["band"],
             "our_estimate": r["our_estimate"], "disagreement": r["disagreement"],
             "reason": r["reason"], "execution": r["execution"]}
            for r in rows[offset: offset + limit]]
    conventions = header.get("conventions") or {}
    return {
        "version": config.CANDIDATE_SURFACE_VERSION,
        "licence": LICENCE,
        "authority": AUTHORITY,
        "vintage": pu_vin,
        "tracker_vintage": tr_vin,
        "stale": bool(pu_vin.get("stale")) or bool(tr_vin.get("stale")),
        "band_status": conventions.get("band_status"),
        "unit": conventions.get("unit"),
        "n_matched": len(rows),
        "n_returned": len(page),
        "offset": offset, "limit": limit,
        "sort": {"key": sort, "dir": dir},
        "rows": page,
    }


@router.get("/allocator")
async def get_allocator(
    day: str | None = Query(None, min_length=_DAY_LEN, max_length=_DAY_LEN),
    personality: str | None = Query(None),
) -> dict:
    """The capital allocator's decision artefacts, served verbatim.

    `learner/allocator.py` stamps every artefact SHADOW_ONLY and proves it four
    ways (no order path, a source scan, an import audit, verbatim constants).
    This endpoint repeats that stamp rather than paraphrasing it.
    """
    if day is not None and not _is_day(day):
        raise HTTPException(status_code=422, detail=f"day must be YYYY-MM-DD, got {day!r}")
    da_day, artefacts, vin = _load_decision_artifacts(day)
    if personality is not None:
        if personality not in artefacts:
            raise HTTPException(
                status_code=404,
                detail=f"no {personality!r} artefact for {da_day}. "
                       f"Available: {sorted(artefacts)}")
        artefacts = {personality: artefacts[personality]}
    return {
        "version": config.CANDIDATE_SURFACE_VERSION,
        "licence": LICENCE,
        "authority": AUTHORITY,
        "vintage": vin,
        "stale": bool(vin.get("stale")),
        "day": da_day,
        "personalities": sorted(artefacts),
        "artifacts": artefacts,
    }
