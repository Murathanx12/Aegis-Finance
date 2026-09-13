"""MURAT'S THEMES AS TYPED HYPOTHESIS STREAMS.

Chunk 14, spec `docs/research_notes/2026-09-13/spec_always_on_lab.md` section 3.7.
Murat, 2026-09-13, verbatim: "linkedin theory, business pivot to ai, motivation,
holders, the business, the future anything."

Each theme becomes ONE `mechanism_id` with its own stream — never a new ledger,
never a new grading function. `lab_decision_vs_reality` grades them separately
from the books and from each other, which is the whole point of giving them
their own ids rather than folding them into one "ideas" bucket.

WHAT THE SPEC SAID, AND WHAT THE REPOSITORY ACTUALLY HOLDS
==========================================================
The spec marked `hiring_pivot_ai_v1` **LIVE** on the strength of
`greenhouse_lever_ashby_ats` being in the news registry. It was in the registry
and it was `implemented: false`, `label_source: false`, and its own
`implemented_note` said the collector (`scripts/hiring_pull.py`) was "not built
here" and that the company-to-board-token mapping "does not exist yet". A
registry row is a PROMISE to pull, not a puller, so the status here was
`registered_awaiting_collector`.

**Chunk 15b, 2026-09-13: the collector exists.** `scripts/hiring_pull.py` is
built, its three endpoint shapes were verified live (one request each against
Greenhouse's `airbnb`, Lever's `leverdemo`, Ashby's `ashby`), and it writes a
board map plus daily rows. So this stream's readiness moves to
`collector_present` -- and NO FURTHER. It is deliberately not "live" and not
"forecasting":

  * `label_source` stays **false** in `news_sources.yaml`, because
    TRIAL-HIRING-PIVOT-1 is still not written and a collector may not label a
    return before its trial exists;
  * the map's coverage is a MEASURED fraction with a large structural
    false-negative rate (a tenant under an unguessable token is
    indistinguishable from an absent one at a three-request budget), and the
    stream carries that denominator rather than the numerator alone;
  * a collector that has run once is not a graded hypothesis stream.

What is missing is now the TRIAL, not the fetcher -- which is the opposite of
what was missing yesterday, and the readiness word says which.

Likewise `pivot_to_ai_narrative_v1`: the spec asked whether the 43-id event
vocabulary carries a strategic-pivot class. It does not — the closest ids are
`new_contract_or_partnership` and `product_launch_or_innovation`, neither of
which is a pivot — so the stream is registered and cannot fire until a
vocabulary id exists. That is chunk-15 work and is named as such.

NO STREAM INVENTS A PROBABILITY
===============================
`holders_13f_v1` is the one theme whose data source works today
(`ownership.get_institutional_ownership`). It still does not write a
`PredictionRecord` on its first week, because a forecast needs a probability
and this stream has no fitted model and no trailing record to anchor one on.
An LLM number is forbidden outright (invariant: no LLM authority, and `p` is
deterministic everywhere else in this repo — `book_forecasts.probability_from_ir`
is Φ of a trailing IR, not a judgement). So the stream accrues OBSERVATIONS,
which are cheap, real and unfabricated, and the first forecast is GATED on
`MIN_OBSERVATIONS_BEFORE_FORECAST`. A stream that fired invented probabilities
from week one would look productive and be worthless.

"THE BUSINESS, THE FUTURE, ANYTHING" IS NOT A STREAM
====================================================
Deliberately. A catch-all `mechanism_id` with no falsifiable `applies_when` is
exactly the shape M2's schema refuses (`applies_when` is a typed condition list
with `minItems: 1`). That surface is X3's once X3 is wired, and inventing an
untyped bucket now would put ungradeable rows in a ledger whose entire value is
that everything in it can be graded.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend import config as _config

logger = logging.getLogger("lab_themes")

#: Observations a stream must accrue before it may write its first forecast.
#: The number is deliberately the same order as `calibration.MIN_PER_BIN`: a
#: probability anchored on fewer than this is a number with a decimal point and
#: no evidence behind it.
MIN_OBSERVATIONS_BEFORE_FORECAST = 15

#: Murat's own sentence, verbatim, carried on every stream as `origin_text` —
#: the convention `paper_books.py` already uses, so a reader six months from now
#: can see what was actually asked for rather than a paraphrase of it.
ORIGIN_TEXT = ("linkedin theory, business pivot to ai, motivation, holders, "
               "the business, the future anything")

#: The four streams. `readiness` is what is TRUE TODAY, checked against the
#: repository rather than copied from the spec.
THEMES: tuple[dict, ...] = (
    {
        "mechanism_id": "hiring_pivot_ai_v1",
        "theme": "hiring / 'linkedin theory'",
        "cadence_days": 1,
        "data_source": "greenhouse_lever_ashby_ats (news registry, N-B)",
        "trial": "TRIAL-HIRING-PIVOT-1 (N-G), already pre-registered",
        "observable": "ai_role_share_change_predicts_forward_return",
        "readiness": "collector_present",
        "collector": "scripts/hiring_pull.py (H1_hiring_pull)",
        "blocked_by": (
            "the collector `scripts/hiring_pull.py` now EXISTS and pulls "
            "Greenhouse/Lever/Ashby into "
            "`backend/data/optimus/hiring/<date>.jsonl` with a board map and a "
            "cursor. What blocks the stream now is the TRIAL, not the fetcher: "
            "TRIAL-HIRING-PIVOT-1 is still unwritten, so `label_source` stays "
            "false and nothing here may label a return. Coverage is also a "
            "measured fraction with a structural false-negative rate -- a board "
            "under an unguessable token is indistinguishable from no board at a "
            "three-request budget -- so the denominator travels with every "
            "number. LinkedIn itself is banned; the ATS boards are the legal "
            "substitute."),
    },
    {
        "mechanism_id": "holders_13f_v1",
        "theme": "holders",
        "cadence_days": 7,
        "data_source": "backend/services/ownership.py (13F institutional holders)",
        "trial": None,
        "observable": "institutional_ownership_change_predicts_forward_return",
        "readiness": "observing",
        "known_weak_prior": (
            "13F has a 45-day filing lag and `research_agency.md` section 4 "
            "already flagged the copy-trading signal THIN. A Brier that looks "
            "like a coin flip here is the expected result, not a surprise."),
        "blocked_by": (
            "no fitted probability: a forecast needs `p`, and this stream has no "
            "model and no trailing record to anchor one on. It accrues "
            f"observations and may forecast after {MIN_OBSERVATIONS_BEFORE_FORECAST}."),
    },
    {
        "mechanism_id": "pivot_to_ai_narrative_v1",
        "theme": "business pivot to AI, beyond the hiring proxy",
        "cadence_days": 1,
        "data_source": "L2 typed events, once a strategic-pivot id exists",
        "trial": None,
        "observable": "strategic_pivot_language_predicts_forward_return",
        "readiness": "placeholder",
        "blocked_by": (
            "the frozen 43-id event vocabulary carries NO strategic-pivot class. "
            "`new_contract_or_partnership` and `product_launch_or_innovation` are "
            "the nearest ids and neither is a pivot. A new vocabulary id is "
            "chunk-15 work, and typing rows against the wrong id would be worse "
            "than not typing them."),
    },
    {
        "mechanism_id": "management_motivation_v1",
        "theme": "management motivation",
        "cadence_days": 7,
        "data_source": None,
        "trial": None,
        "observable": "management_motivation_language_predicts_forward_return",
        "readiness": "placeholder",
        "blocked_by": (
            "no collector exists. It would need an LLM read of earnings-call "
            "transcripts or shareholder letters, and this repository does not "
            "ingest either as a labelled source. Named here so the stream can "
            "start accruing the day one exists, rather than being invented later "
            "with no history."),
    },
)

#: NOT a stream, and the reason is load-bearing.
NOT_A_STREAM = {
    "theme": "the business, the future, anything",
    "why": ("a catch-all mechanism_id with no falsifiable `applies_when` is the "
            "shape M2's schema refuses (`applies_when` is a typed condition list, "
            "minItems 1). This surface is X3's once X3 is wired; an untyped "
            "bucket now would put ungradeable rows in a ledger whose whole value "
            "is that everything in it can be graded."),
}

#: `collector_present` (chunk 15b) sits between `registered_awaiting_collector`
#: and `forecasting`: the puller exists and writes rows, and the trial that would
#: let those rows label a return does not. Two different kinds of "not ready"
#: with two different fixes deserve two different words -- one word for both is
#: how a stream waits a month for the thing that was already built.
READINESS = ("observing", "registered_awaiting_collector", "collector_present",
             "placeholder", "forecasting")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def registry_path() -> Path:
    return Path(_config.DATA_DIR) / "optimus" / "lab_theme_streams.json"


def observations_path() -> Path:
    return Path(_config.DATA_DIR) / "optimus" / "lab_theme_observations.jsonl"


def theme(mechanism_id: str) -> dict:
    for t in THEMES:
        if t["mechanism_id"] == mechanism_id:
            return t
    raise KeyError(f"{mechanism_id!r} is not a declared theme; have "
                   f"{[t['mechanism_id'] for t in THEMES]}")


def _read_registry() -> dict:
    p = registry_path()
    if not p.exists():
        return {}
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return rec.get("streams") or {}


def _write_registry(streams: dict) -> Path:
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"receipt": "lab_theme_streams", "utc": _now(),
               "origin": "murat_theme", "origin_text": ORIGIN_TEXT,
               "not_a_stream": NOT_A_STREAM, "streams": streams}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)
    return p


def register_streams() -> dict:
    """Create one row per theme. IDEMPOTENT — by `mechanism_id`, which is the id.

    Called on every supervisor restart. `first_registered_utc` is written once
    and never touched again: it is the stream's own inception, and a stream
    whose inception moved every time the process restarted would make its own
    history unreadable. The same identity discipline `paper_books.py` applies to
    a `Strategy` fingerprint, applied to a mechanism id.
    """
    streams = _read_registry()
    for t in THEMES:
        mid = t["mechanism_id"]
        row = streams.get(mid) or {}
        row.setdefault("first_registered_utc", _now())
        row.setdefault("n_fired", 0)
        row.setdefault("n_observations", 0)
        row.setdefault("last_run_date", None)
        row.update({
            "mechanism_id": mid,
            "theme": t["theme"],
            "origin": "murat_theme",
            "origin_text": ORIGIN_TEXT,
            "observable": t["observable"],
            "readiness": t["readiness"],
            "blocked_by": t.get("blocked_by"),
            "data_source": t.get("data_source"),
            "trial": t.get("trial"),
            "known_weak_prior": t.get("known_weak_prior"),
            "cadence_days": t["cadence_days"],
            "state": "CANDIDATE",
            "last_seen_utc": _now(),
        })
        streams[mid] = row
    _write_registry(streams)
    return streams


def due(mechanism_id: str, *, today: date | None = None,
        streams: dict | None = None) -> bool:
    today = today or date.today()
    streams = streams if streams is not None else _read_registry()
    row = streams.get(mechanism_id) or {}
    last = row.get("last_run_date")
    if not last:
        return True
    try:
        prev = date.fromisoformat(str(last)[:10])
    except ValueError:
        return True
    return (today - prev).days >= int(theme(mechanism_id)["cadence_days"])


def _append_observations(rows: list[dict]) -> Path:
    p = observations_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    return p


def observe_holders(tickers: list[str], *, fetch=None,
                    today: date | None = None) -> dict:
    """One 13F ownership observation per name. NOT a forecast.

    `first_seen_utc` is stamped by us, the same convention the news corpus uses,
    because the provider's own asOfDate is a quarter-end 45 days in the past and
    the only honest point-in-time anchor is when WE saw it.

    A name whose fetch returns nothing is recorded BY NAME as `unavailable`
    rather than skipped: an observation series with silent holes reads as a
    complete series with fewer names in it.
    """
    today = today or date.today()
    if fetch is None:
        from backend.services.ownership import get_institutional_ownership as fetch
    rows, unavailable = [], []
    for t in tickers:
        try:
            got = fetch(t)
        except Exception as exc:                                   # noqa: BLE001
            unavailable.append({"ticker": t, "why": f"{type(exc).__name__}: {exc}"[:160]})
            continue
        if not got:
            unavailable.append({"ticker": t, "why": "the source returned nothing"})
            continue
        rows.append({
            "mechanism_id": "holders_13f_v1",
            "kind": "observation",
            "ticker": t,
            "observation_date": today.isoformat(),
            "first_seen_utc": _now(),
            "n_holders": len(got.get("holders") or []),
            "pct_institutional": got.get("pct_institutional"),
            "crowding": got.get("crowding"),
            "known_weak_prior": theme("holders_13f_v1")["known_weak_prior"],
            "is_forecast": False,
            "why_not_a_forecast": (
                "no fitted probability exists for this stream; a `p` written "
                "here would be invented, and an LLM number is never admissible."),
        })
    if rows:
        _append_observations(rows)
    return {"mechanism_id": "holders_13f_v1", "observed": len(rows),
            "unavailable": unavailable, "tickers_requested": len(tickers)}


def may_forecast(mechanism_id: str, *, streams: dict | None = None) -> dict:
    """Has this stream accrued enough observations to anchor a probability?"""
    streams = streams if streams is not None else _read_registry()
    n = int((streams.get(mechanism_id) or {}).get("n_observations") or 0)
    return {"mechanism_id": mechanism_id, "n_observations": n,
            "required": MIN_OBSERVATIONS_BEFORE_FORECAST,
            "may_forecast": n >= MIN_OBSERVATIONS_BEFORE_FORECAST,
            "why_not": (None if n >= MIN_OBSERVATIONS_BEFORE_FORECAST else
                        f"{n} observation(s) of the "
                        f"{MIN_OBSERVATIONS_BEFORE_FORECAST} needed to anchor a "
                        f"probability that is not invented")}


def run_due(tickers: list[str] | None = None, *, today: date | None = None,
            fetch=None) -> dict:
    """Every stream whose own cadence has elapsed. Registration first, always.

    Returns one row per theme — including the placeholders, which report
    `n_fired: 0` and the reason. A placeholder that vanished from this payload
    would be a stream nobody remembers is waiting.
    """
    today = today or date.today()
    streams = register_streams()
    rows = []
    for t in THEMES:
        mid = t["mechanism_id"]
        row = {"mechanism_id": mid, "theme": t["theme"],
               "readiness": t["readiness"], "n_fired": 0, "n_observations": 0,
               "due": due(mid, today=today, streams=streams)}
        if t["readiness"] != "observing":
            row["status"] = t["readiness"].upper()
            row["blocked_by"] = t["blocked_by"]
            rows.append(row)
            continue
        if not row["due"]:
            row["status"] = "not_due"
            rows.append(row)
            continue
        if mid == "holders_13f_v1":
            out = observe_holders(list(tickers or []), fetch=fetch, today=today)
            row["n_observations"] = out["observed"]
            row["unavailable"] = out["unavailable"]
            row["status"] = "ok" if out["observed"] else "nothing_to_do"
            streams[mid]["n_observations"] = (
                int(streams[mid].get("n_observations") or 0) + out["observed"])
            streams[mid]["last_run_date"] = today.isoformat()
            row["may_forecast"] = may_forecast(mid, streams=streams)
        rows.append(row)
    _write_registry(streams)
    return {
        "receipt": "lab_theme_streams_run",
        "licence": "PRODUCT_EXPERIMENT", "stage": "raw", "llm_spend_usd": 0.0,
        "utc": _now(), "date": today.isoformat(),
        "origin": "murat_theme", "origin_text": ORIGIN_TEXT,
        "streams": rows,
        "not_a_stream": NOT_A_STREAM,
        "registry_path": str(registry_path()),
        "headline": (
            f"{sum(1 for r in rows if r['readiness'] == 'observing')} observing, "
            f"{sum(1 for r in rows if r['readiness'] in ('registered_awaiting_collector', 'collector_present'))} "
            f"awaiting a collector, "
            f"{sum(1 for r in rows if r['readiness'] == 'placeholder')} placeholder; "
            f"{sum(r['n_observations'] for r in rows)} observation(s), "
            f"{sum(r['n_fired'] for r in rows)} forecast(s)"),
    }


def status() -> dict:
    """The one-word-per-stream block `lab_status.json` carries."""
    streams = _read_registry()
    return {t["mechanism_id"]: (streams.get(t["mechanism_id"]) or {}).get(
        "readiness", t["readiness"]) for t in THEMES}


__all__ = ["MIN_OBSERVATIONS_BEFORE_FORECAST", "NOT_A_STREAM", "ORIGIN_TEXT",
           "READINESS", "THEMES", "due", "may_forecast", "observations_path",
           "observe_holders", "register_streams", "registry_path", "run_due",
           "status", "theme"]
