"""Opt-in saved-artifact diagnostic; no application, ledger, or runtime imports.

Pass exact saved card JSON bytes and forecast JSONL bytes. No paths are opened.
``prospective_from`` is a caller-declared collection boundary, not evidence that
collection occurred then. ``pit_asof`` bounds artifact clocks, not current health.
An exact native link is NOT source availability or source-to-decision proof.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone


class LinkRefused(ValueError):
    """The supplied artifacts cannot establish an unambiguous native link."""


# Mirrored from thesis_card.ENGINE_KEYS / forecast_snapshot. Kept here so the
# diagnostic imports no application code, model, config, or ledger reader.
_ENGINE_KEYS = (
    "engine_px", "engine_mom_21", "engine_mom_63", "engine_vol_63",
    "engine_band", "engine_cost_bps", "engine_rev_qoq",
    "engine_gross_margin", "engine_gross_margin_chg", "engine_inflection_flag",
    "engine_net_raises_90d", "engine_n_firms_90d",
    "engine_median_target_change_90d", "engine_forecast_p_up_1d",
    "engine_forecast_p_up_5d",
)


def _stamp(value):
    if not isinstance(value, str) or "T" not in value:
        raise LinkRefused("timezone-aware timestamp required")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LinkRefused("invalid timestamp") from exc
    if stamp.tzinfo is None:
        raise LinkRefused("timezone-aware timestamp required")
    return stamp.astimezone(timezone.utc)


def _artifact_clock(value, *, field):
    """Return (UTC date, exact instant or None); date-only is not midnight."""
    if not isinstance(value, str):
        raise LinkRefused(f"{field} must be an ISO date or aware timestamp")
    if "T" in value:
        try:
            instant = _stamp(value)
        except LinkRefused as exc:
            raise LinkRefused(f"invalid {field} timestamp: {exc}") from exc
        return instant.date(), instant
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise LinkRefused(f"invalid {field} date") from exc
    if value != day.isoformat():
        raise LinkRefused(f"invalid {field} date")
    return day, None


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise LinkRefused("duplicate JSON key")
        result[key] = value
    return result


def _load(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise LinkRefused("invalid artifact JSON: " + str(exc)) from exc
    if not isinstance(value, dict):
        raise LinkRefused("artifact row must be an object")
    return value


def _nonfinite(_):
    raise LinkRefused("non-finite JSON number")


def _hash(value, *, ascii=False):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str,
                                    ensure_ascii=ascii).encode("utf-8")).hexdigest()[:16]


def _native_snapshot_hash(card):
    snapshot = {"card_hash": card["card_hash"], "asof": card.get("asof"),
                "verdict": card.get("verdict"), "confidence": card.get("confidence")}
    for key in (*_ENGINE_KEYS, "engine_unavailable", "engine_last_filed"):
        snapshot[key] = card.get(key)
    return _hash(snapshot)  # belief_state._hash(forecast_snapshot(card))


def _check_optional_clock(value, *, field, made, cutoff, max_day,
                          prospective_from=None):
    if value is None:
        return
    day, instant = _artifact_clock(value, field=field)
    if day > max_day or day > made.date() or day > cutoff.date():
        raise LinkRefused(f"{field} is after forecast/PIT cutoff")
    if instant is not None and (instant > made or instant > cutoff):
        raise LinkRefused(f"{field} is after forecast/PIT cutoff")
    if prospective_from is not None and day < prospective_from.date():
        raise LinkRefused(f"{field} predates prospective boundary")


def diagnose(card_json: bytes, forecasts_jsonl: bytes, *, enabled=False,
             prospective_from=None, pit_asof=None) -> dict:
    """Return exact saved native links or raise LinkRefused (never guess).

    Both native horizons may link to one card; duplicates within a horizon or
    duplicate IDs are refused. Same-day UTC card/forecast is required as a
    conservative anti-backfill rule. Date-only card asof is never a write clock.
    No persisted deployment switch, scheduler registration, or output writer.
    """
    if enabled is not True:
        return {"status": "DISABLED", "links": []}
    start, cutoff = _stamp(prospective_from), _stamp(pit_asof)
    if start > cutoff:
        raise LinkRefused("prospective boundary exceeds PIT cutoff")
    card = _load(card_json)
    body = {k: v for k, v in card.items() if k != "card_hash" and not k.startswith("_")}
    native_hash = _hash(body, ascii=True)  # thesis_card.card_hash, not file SHA256
    if card.get("card_hash") != native_hash:
        raise LinkRefused("missing or mismatched native card hash")
    if card.get("_unreadable") or card.get("verdict") not in ("supports", "neutral", "against"):
        raise LinkRefused("unforecastable card")
    if card.get("confidence") not in ("high", "med", "low"):
        raise LinkRefused("unforecastable confidence")
    ticker = card.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise LinkRefused("missing ticker")
    try:
        asof = date.fromisoformat(card.get("asof", ""))
    except (TypeError, ValueError) as exc:
        raise LinkRefused("invalid card asof") from exc
    if not start.date() <= asof <= cutoff.date():
        raise LinkRefused("historical or future card")
    sources = card.get("sources")
    if not isinstance(sources, list) or not sources or any(
            not isinstance(s, str) or not s.strip() for s in sources):
        raise LinkRefused("missing or malformed source citations")
    # Optional clocks are reported verbatim and checked, never filled from mtime.
    card_clocks = {k: card.get(k) for k in ("asof", "run_utc", "created_at", "written_at",
                                           "engine_asof", "engine_last_filed")}
    if card.get("engine_asof") is not None:
        engine_day, _ = _artifact_clock(card["engine_asof"], field="engine_asof")
        if engine_day != asof:
            raise LinkRefused("engine_asof conflicts with card asof")
    for key in ("run_utc", "created_at", "written_at"):
        if card.get(key) is not None and not start <= _stamp(card[key]) <= cutoff:
            raise LinkRefused("card clock outside prospective PIT window")
    rows = [_load(line) for line in forecasts_jsonl.splitlines() if line.strip()]
    ids, horizons, links = set(), set(), []
    for row in rows:
        pid = row.get("prediction_id")
        if not isinstance(pid, str) or not pid or pid in ids:
            raise LinkRefused("missing or duplicate forecast ID")
        ids.add(pid)
        inputs = row.get("inputs_used")
        if inputs is not None and not isinstance(inputs, dict):
            raise LinkRefused("malformed inputs_used")
        if (inputs or {}).get("card_hash") != native_hash:
            continue  # no ticker/date/prose fallback
        if (row.get("specialist") != "thesis_card:v1"
                or row.get("mechanism_id") != "thesis_card_v1"
                or inputs.get("source") != "thesis_card"
                or inputs.get("as_of") != card["asof"]
                or inputs.get("card_kind") != card.get("kind")
                or row.get("ticker") != ticker.upper()
                or row.get("observable") != "beats_benchmark"
                or row.get("benchmark") != "SPY"):
            raise LinkRefused("conflicting native link metadata")
        # Native make_prediction identity formula. These remain saved hashes;
        # this check does not certify the prompt or full input snapshot body.
        for key in ("input_snapshot_hash", "prompt_hash"):
            value = row.get(key)
            if not isinstance(value, str) or len(value) != 16 or any(
                    ch not in "0123456789abcdef" for ch in value):
                raise LinkRefused("missing or malformed native forecast hash")
        if row["input_snapshot_hash"] != _native_snapshot_hash(card):
            raise LinkRefused("forecast input_snapshot_hash contradicts native card snapshot")
        identity = [row.get(k) for k in ("ticker", "specialist", "observable",
                    "horizon_days", "made_at", "input_snapshot_hash", "prompt_hash")]
        if pid != _hash(identity):
            raise LinkRefused("forecast ID does not match native identity")
        made = _stamp(row.get("made_at"))
        if not start <= made <= cutoff or made.date() != asof:
            raise LinkRefused("historical/backfilled or future forecast")
        if row.get("decision_date") != asof.isoformat():
            raise LinkRefused("conflicting forecast decision_date")
        _check_optional_clock(card.get("engine_asof"), field="engine_asof",
                              made=made, cutoff=cutoff, max_day=asof)
        _check_optional_clock(card.get("engine_last_filed"), field="engine_last_filed",
                              made=made, cutoff=cutoff, max_day=asof)
        _check_optional_clock(row.get("session_as_of"), field="session_as_of",
                              made=made, cutoff=cutoff, max_day=asof,
                              prospective_from=start)
        for key in ("run_utc", "created_at", "written_at"):
            if card.get(key) is not None and _stamp(card[key]) > made:
                raise LinkRefused("card clock follows forecast")
        h = row.get("horizon_days")
        if type(h) is not int or h not in (20, 120) or h in horizons:
            raise LinkRefused("ambiguous or non-native horizon")
        horizons.add(h)
        links.append({"native_card_hash": native_hash, "forecast_id": pid,
                      "horizon_days": h, "source_citations": list(sources),
                      "card_clocks": dict(card_clocks),
                      "forecast_clocks": {k: row.get(k) for k in
                                          ("made_at", "decision_date", "session_as_of")}})
    if not links:
        raise LinkRefused("no exact native card-hash link; inference forbidden")
    if horizons != {20, 120}:
        raise LinkRefused("incomplete native forecast pair; both 20 and 120 required")
    return {"status": "EXACT_NATIVE_LINK_ONLY", "links": links,
            "artifact_sha256": {"card": hashlib.sha256(card_json).hexdigest(),
                                "forecasts": hashlib.sha256(forecasts_jsonl).hexdigest()},
            "declared_window": {"prospective_from": prospective_from, "pit_asof": pit_asof},
            "source_availability_proven": False, "decision_lineage_proven": False,
            "remaining_gaps": ["source publication/observation clocks and immutable source bodies",
                               "card persistence/availability at forecast time (asof is date-only)",
                               "saved prompt and full input snapshot bodies (native snapshot hash reconstructed)",
                               "explicit forecast-to-decision reference and consumer receipt",
                               "policy/calibration/sizing and action/outcome lineage"]}
