"""Offline contract fixtures built through the existing native forecast producer."""
import copy
import hashlib
import json

import pytest

from backend.services import thesis_card as TC
from scripts.native_thesis_forecast_diagnostic import LinkRefused, diagnose


START = "2030-01-02T00:00:00Z"
MADE = "2030-01-02T12:00:00+00:00"
CUTOFF = "2030-01-02T13:00:00Z"


@pytest.fixture
def artifacts():
    card = {"ticker": "AAA", "asof": "2030-01-02", "kind": "personal",
            "verdict": "supports", "confidence": "high", "bull": "Café demand",
            "falsifier": "Demand falls", "sources": ["https://example.test/ir"]}
    card["card_hash"] = TC.card_hash(card)
    rows = TC.forecast_rows(card, today=card["asof"], made_at=MADE)
    return card, rows


def blobs(card, rows):
    return (json.dumps(card, ensure_ascii=False, indent=1).encode(),
            "\n".join(json.dumps(row) for row in rows).encode())


def run(card, rows, **kwargs):
    return diagnose(*blobs(card, rows), enabled=True,
                    prospective_from=START, pit_asof=CUTOFF, **kwargs)


def _rebuild(card):
    """Make a fully native row pair after changing a card field."""
    card["card_hash"] = TC.card_hash(card)
    return TC.forecast_rows(card, today=card["asof"], made_at=MADE)


def _reidentify(row):
    identity = [row[k] for k in ("ticker", "specialist", "observable",
                "horizon_days", "made_at", "input_snapshot_hash", "prompt_hash")]
    row["prediction_id"] = hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def test_disabled_does_not_inspect_inputs():
    assert diagnose(None, None) == {"status": "DISABLED", "links": []}


def test_native_producer_roundtrip_and_no_mutation(artifacts):
    card, rows = artifacts
    original = copy.deepcopy(artifacts)
    report = run(card, rows)
    assert artifacts == original
    assert report["status"] == "EXACT_NATIVE_LINK_ONLY"
    assert [link["forecast_id"] for link in report["links"]] == [r["prediction_id"] for r in rows]
    assert {link["horizon_days"] for link in report["links"]} == {20, 120}
    assert report["links"][0]["native_card_hash"] == TC.card_hash(card)
    assert report["links"][0]["source_citations"] == card["sources"]
    assert report["links"][0]["card_clocks"]["written_at"] is None
    assert report["links"][0]["forecast_clocks"]["made_at"] == MADE
    assert report["artifact_sha256"]["card"] == hashlib.sha256(blobs(card, rows)[0]).hexdigest()
    assert report["source_availability_proven"] is False
    assert report["decision_lineage_proven"] is False


def test_snapshot_hash_is_native_forecast_snapshot(artifacts):
    card, rows = artifacts
    from backend.services import belief_state as B
    assert rows[0]["input_snapshot_hash"] == B._hash(TC.forecast_snapshot(card))
    assert run(card, rows)["status"] == "EXACT_NATIVE_LINK_ONLY"
    for key in TC.ENGINE_KEYS:
        card[key] = f"sample:{key}"
    card["engine_unavailable"] = ["news"]
    card["engine_last_filed"] = "2029-12-31"
    rows = _rebuild(card)
    assert rows[0]["input_snapshot_hash"] == B._hash(TC.forecast_snapshot(card))
    assert run(card, rows)["status"] == "EXACT_NATIVE_LINK_ONLY"


@pytest.mark.parametrize("field", ["engine_px", "engine_last_filed"])
def test_saved_snapshot_contradiction_refused_even_with_recomputed_id(artifacts, field):
    card, rows = artifacts
    card[field] = 42 if field == "engine_px" else "2029-12-31"
    card["card_hash"] = TC.card_hash(card)
    for row in rows:
        row["inputs_used"]["card_hash"] = card["card_hash"]
        _reidentify(row)
    with pytest.raises(LinkRefused, match="input_snapshot_hash contradicts"):
        run(card, rows)


def test_missing_snapshot_hash_refused_even_with_recomputed_id(artifacts):
    card, rows = artifacts
    rows[0]["input_snapshot_hash"] = None
    _reidentify(rows[0])
    with pytest.raises(LinkRefused, match="missing or malformed native forecast hash"):
        run(card, rows)


@pytest.mark.parametrize("field,value", [
    ("engine_asof", "2030-01-03"),
    ("engine_asof", "2030-01-02T12:30:00Z"),
    ("engine_asof", "2030-01-02T12:30:00"),
    ("engine_last_filed", "2030-01-03"),
    ("engine_last_filed", "2030-01-02T12:30:00Z"),
    ("engine_last_filed", "2030-01-02T12:30:00"),
    ("engine_last_filed", "2030-01-02garbage"),
])
def test_card_engine_clocks_refuse_future_or_ambiguous_values(artifacts, field, value):
    card, _ = artifacts
    card[field] = value
    rows = _rebuild(card)
    with pytest.raises(LinkRefused, match="engine_asof|engine_last_filed"):
        run(card, rows)


@pytest.mark.parametrize("value", [
    "2030-01-03", "2030-01-02T12:30:00Z",
    "2030-01-02T12:30:00", "2029-12-31",
])
def test_session_as_of_refuses_future_naive_or_historical(artifacts, value):
    card, rows = artifacts
    for row in rows:
        row["session_as_of"] = value
    with pytest.raises(LinkRefused, match="session_as_of"):
        run(card, rows)


def test_date_only_filing_can_precede_window_and_offsets_use_utc(artifacts):
    card, _ = artifacts
    card["engine_asof"] = "2030-01-03T00:30:00+14:00"  # UTC Jan 2, 10:30
    card["engine_last_filed"] = "2029-12-31"  # filing date may predate collection
    rows = _rebuild(card)
    for row in rows:
        row["session_as_of"] = "2030-01-03T00:30:00+14:00"  # same UTC day
    report = run(card, rows)
    assert report["status"] == "EXACT_NATIVE_LINK_ONLY"
    assert report["links"][0]["card_clocks"]["engine_last_filed"] == "2029-12-31"


def test_offset_clock_after_forecast_in_utc_refused(artifacts):
    card, _ = artifacts
    card["engine_last_filed"] = "2030-01-02T00:30:00-13:00"  # UTC 13:30
    rows = _rebuild(card)
    with pytest.raises(LinkRefused, match="engine_last_filed"):
        run(card, rows)


@pytest.mark.parametrize("drop_horizon", [20, 120])
def test_missing_native_horizon_is_not_exact(artifacts, drop_horizon):
    card, rows = artifacts
    rows = [row for row in rows if row["horizon_days"] != drop_horizon]
    with pytest.raises(LinkRefused, match="incomplete native forecast pair"):
        run(card, rows)


@pytest.mark.parametrize("field,value", [
    ("card_hash", None), ("card_hash", "incorrect"), ("bull", "tampered"),
    ("sources", []), ("sources", [None]), ("sources", "url"),
    ("verdict", "REFUSED_EMPTY_LOG"), ("confidence", "unknown"), ("verdict", []),
    ("asof", "2020-01-01"), ("asof", "2030-01-03"),
    ("run_utc", "2030-01-02T14:00:00Z"),
    ("written_at", "2030-01-02T12:30:00Z"),
])
def test_bad_card_refused(artifacts, field, value):
    card, rows = artifacts
    card[field] = value
    if field not in {"card_hash", "bull"}:
        card["card_hash"] = TC.card_hash(card)
        for row in rows:
            row["inputs_used"]["card_hash"] = card["card_hash"]
    with pytest.raises(LinkRefused):
        run(card, rows)


@pytest.mark.parametrize("field,value", [
    ("prediction_id", None), ("specialist", "investigator:x"),
    ("mechanism_id", "other"), ("ticker", "BBB"),
    ("observable", "price_up"), ("benchmark", "QQQ"),
    ("horizon_days", 21), ("horizon_days", True),
    ("decision_date", "2020-01-01"), ("made_at", "2020-01-01T12:00:00Z"),
    ("made_at", "2030-01-02T14:00:00Z"), ("made_at", "2030-01-02T12:00:00"),
    ("inputs_used", []), ("input_snapshot_hash", None), ("prompt_hash", "bad"),
    ("prediction_id", "forged"),
])
def test_conflicting_forecast_refused(artifacts, field, value):
    card, rows = artifacts
    rows[0][field] = value
    with pytest.raises(LinkRefused):
        run(card, rows)


@pytest.mark.parametrize("field", ["card_hash", "source", "as_of", "card_kind"])
def test_missing_native_reference_is_never_inferred(artifacts, field):
    card, rows = artifacts
    for row in rows:
        row["inputs_used"].pop(field)
    with pytest.raises(LinkRefused):
        run(card, rows)


@pytest.mark.parametrize("same_id", [True, False])
def test_duplicate_horizon_or_id_refused(artifacts, same_id):
    card, rows = artifacts
    extra = copy.deepcopy(rows[0])
    if not same_id:
        extra["made_at"] = "2030-01-02T12:01:00+00:00"
        identity = [extra[k] for k in ("ticker", "specialist", "observable",
                    "horizon_days", "made_at", "input_snapshot_hash", "prompt_hash")]
        extra["prediction_id"] = hashlib.sha256(
            json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    with pytest.raises(LinkRefused, match="duplicate forecast ID|ambiguous"):
        run(card, rows + [extra])


def test_later_day_backfill_refused(artifacts):
    card, _ = artifacts
    rows = TC.forecast_rows(card, today="2030-01-03", made_at="2030-01-03T12:00:00Z")
    with pytest.raises(LinkRefused, match="backfilled"):
        diagnose(*blobs(card, rows), enabled=True, prospective_from=START,
                 pit_asof="2030-01-04T00:00:00Z")


@pytest.mark.parametrize("raw", [b'{}', b'{"a":1,"a":2}', b'{"a":NaN}', b'[]', b'bad'])
def test_malformed_artifact_refused(artifacts, raw):
    _, rows = artifacts
    with pytest.raises(LinkRefused):
        diagnose(raw, blobs({}, rows)[1], enabled=True,
                 prospective_from=START, pit_asof=CUTOFF)


def test_missing_or_invalid_window_refused(artifacts):
    with pytest.raises(LinkRefused):
        diagnose(*blobs(*artifacts), enabled=True)
    with pytest.raises(LinkRefused):
        diagnose(*blobs(*artifacts), enabled=True, prospective_from=CUTOFF, pit_asof=START)


def test_no_file_network_or_native_writer_calls(artifacts, monkeypatch):
    import builtins
    import socket

    raw = blobs(*artifacts)

    def forbidden(*args, **kwargs):
        raise AssertionError("I/O or native writer called")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(TC, "write_card", forbidden)
    monkeypatch.setattr(TC, "write_forecasts", forbidden)
    result = diagnose(*raw, enabled=True, prospective_from=START, pit_asof=CUTOFF)
    assert result["status"] == "EXACT_NATIVE_LINK_ONLY"


def test_empty_or_malformed_forecasts_refused(artifacts):
    card, _ = artifacts
    for raw in (b"", b"[]", b"not json", b'{"prediction_id":"x","prediction_id":"y"}'):
        with pytest.raises(LinkRefused):
            diagnose(blobs(card, [])[0], raw, enabled=True,
                     prospective_from=START, pit_asof=CUTOFF)
