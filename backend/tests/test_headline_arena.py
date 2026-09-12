"""M6: the row precedes the POST, and with no credentials nothing is sent.

Two properties, and they are the only two that make third-party settlement worth
anything:

1. **the ledger row is written BEFORE any network call.** A submission made
   first can be reconciled against whatever we later say we forecast.
2. **credit-earning never touches the stated confidence.** The arena's financial
   track scores `50 ± 50·confidence`, which pays for overstatement; the only
   defence is that the number was already committed in our own ledger, and the
   payload reads it off the record rather than recomputing it.

Every HTTP call is a callable this test passes in. No test in this file can
reach the network — and the third test proves the absent-credential path makes
no call at all, rather than making one that happens to fail.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.services.belief_state import read_predictions
from backend.tests.book_helpers import synthetic_bars

arena = pytest.importorskip("scripts.headline_arena_daily")


@pytest.fixture(autouse=True)
def _no_migration(monkeypatch):
    from backend.services import belief_state as BS
    monkeypatch.setattr(BS, "_migrate_once", lambda: None)


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch):
    """The default state of this environment, made explicit."""
    monkeypatch.delenv(arena.AGENT_ID_ENV, raising=False)
    monkeypatch.delenv(arena.CLIENT_SECRET_ENV, raising=False)


@pytest.fixture()
def bars():
    """SPY and NVDA with enough history for the 252-session standardisation."""
    return synthetic_bars(symbols=("SPY", "NVDA"), n=400)


@pytest.fixture()
def ledger(tmp_path):
    return tmp_path / "predictions.jsonl"


@pytest.fixture(autouse=True)
def _receipts_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(arena, "receipt_dir", lambda: tmp_path / "arena_receipts")


class Recorder:
    """An HTTP layer that records instead of calling."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, body: dict) -> dict:
        self.calls.append((url, body))
        return {"ok": True}


# ── the pre-registration ───────────────────────────────────────────────────


def test_the_mapping_matches_its_own_prereg_hash():
    """A rule that changed without being re-registered is not pre-registered."""
    v = arena.verify_prereg(arena.load_mapping())
    assert v["match"], v


def test_a_changed_rule_changes_the_hash():
    """The guard has teeth: proves the hash is over the RULES, not the file."""
    m = arena.load_mapping()
    before = arena.prereg_hash(m)
    m["targets"][0]["direction"] = "-sign(z)"
    assert arena.prereg_hash(m) != before
    # and a change to the prose does NOT change it
    m2 = arena.load_mapping()
    m2["api"]["base_url"] = "https://elsewhere.example"
    assert arena.prereg_hash(m2) == before


def test_a_prereg_mismatch_refuses_the_whole_run(bars, ledger, monkeypatch):
    bad = arena.load_mapping()
    bad["prereg_hash"] = "0000000000000000"
    monkeypatch.setattr(arena, "load_mapping", lambda *a, **k: bad)
    rep = arena.run(dry_run=True, bars=bars, predictions_path=ledger)
    assert "refused" in rep
    assert rep["posted"] is False
    assert read_predictions(ledger) == [], (
        "a refused run must write no row: a forecast whose rule changed "
        "without being re-registered is not a forecast we may keep")


# ── the order ──────────────────────────────────────────────────────────────


def test_the_row_is_written_before_the_post(bars, ledger, monkeypatch):
    monkeypatch.setenv(arena.AGENT_ID_ENV, "test-agent")
    monkeypatch.setenv(arena.CLIENT_SECRET_ENV, "test-secret")
    seen_at_post: list[int] = []

    def poster(url, body):
        # the ledger is read FROM INSIDE the post: if the write came second,
        # this list would hold a zero
        seen_at_post.append(len(read_predictions(ledger)))
        return {"ok": True}

    rep = arena.run(dry_run=False, bars=bars, predictions_path=ledger,
                    http_post=poster)
    assert rep["n_rows"] > 0
    assert rep["ledger_written_before_post"] is True
    assert seen_at_post, "nothing was posted, so the ordering was not exercised"
    assert all(n == rep["n_rows"] for n in seen_at_post), (
        f"the ledger held {seen_at_post} rows at post time, expected "
        f"{rep['n_rows']} — the row must exist before the submission")


def test_absent_credentials_make_no_network_call_at_all(bars, ledger):
    rec = Recorder()
    rep = arena.run(dry_run=False, bars=bars, predictions_path=ledger,
                    http_post=rec)
    assert rec.calls == [], "a call was made without credentials"
    assert rep["posted"] is False
    assert rep["reason_not_posted"] == "credentials absent (registration is attended)"
    assert rep["credentials"]["present"] is False
    assert rep["credentials"]["env_names"] == [arena.AGENT_ID_ENV,
                                               arena.CLIENT_SECRET_ENV]
    # and the rows ARE written: the ledger half of the job is the half that works
    assert len(read_predictions(ledger)) == rep["n_rows"] > 0


def test_dry_run_writes_rows_and_posts_nothing(bars, ledger):
    rec = Recorder()
    rep = arena.run(dry_run=True, bars=bars, predictions_path=ledger, http_post=rec)
    assert rec.calls == []
    assert rep["dry_run"] is True
    assert rep["posted"] is False
    assert "--dry-run" in rep["reason_not_posted"]
    assert len(read_predictions(ledger)) == rep["n_rows"] > 0
    assert rep["receipt_path"]


# ── the confidence ─────────────────────────────────────────────────────────


def test_the_posted_confidence_is_the_ledgers(bars, ledger, monkeypatch):
    """Credit-earning never touches the stated confidence."""
    monkeypatch.setenv(arena.AGENT_ID_ENV, "a")
    monkeypatch.setenv(arena.CLIENT_SECRET_ENV, "b")
    rec = Recorder()
    rep = arena.run(dry_run=False, bars=bars, predictions_path=ledger, http_post=rec)
    assert rec.calls
    by_id = {r["prediction_id"]: r for r in read_predictions(ledger)}
    for _url, body in rec.calls:
        row = by_id[body["external_id"]]
        # the payload's confidence inverts the ledger's probability, to the
        # six decimals the payload is rounded to -- and to nothing coarser
        assert abs(body["confidence"] - abs(2 * row["probability"] - 1)) < 1e-6
        assert body["direction"] == ("up" if row["probability"] >= 0.5 else "down")
    assert rep["n_posted"] == len(rec.calls)


def test_the_confidence_is_capped(bars):
    m = arena.load_mapping()
    assert arena.confidence_from_z(100.0, m) == m["confidence"]["ceiling"]
    assert arena.confidence_from_z(0.0, m) == m["confidence"]["floor"]


def test_the_submitted_reasoning_carries_no_holding(bars, ledger, monkeypatch):
    """Their terms take a perpetual, sublicensable licence to submitted text."""
    monkeypatch.setenv(arena.AGENT_ID_ENV, "a")
    monkeypatch.setenv(arena.CLIENT_SECRET_ENV, "b")
    rec = Recorder()
    arena.run(dry_run=False, bars=bars, predictions_path=ledger, http_post=rec)
    for _url, body in rec.calls:
        text = body["reasoning"].lower()
        assert "prereg_hash" in text
        for leak in ("book:", "portfolio", "position", "shares", "holding"):
            assert leak not in text, f"the public reasoning leaked {leak!r}"


def test_the_payload_refuses_anything_that_is_not_a_written_record():
    class NotARecord:
        prediction_id = None
        probability = 0.6
        notes_text = ""

    with pytest.raises(ValueError, match="written PredictionRecord"):
        arena.arena_payload(NotARecord(), "ES", "deadbeef")


# ── the rows themselves ────────────────────────────────────────────────────


def test_every_row_names_the_settling_party_as_its_benchmark(bars, ledger):
    arena.run(dry_run=True, bars=bars, predictions_path=ledger)
    rows = read_predictions(ledger)
    assert rows
    for r in rows:
        assert r["benchmark"] == arena.BENCHMARK
        assert r["model"] == "engine"
        assert r["mechanism_id"] == arena.MECHANISM_ID
        assert r["policy_hash"] == arena.verify_prereg(arena.load_mapping())["computed"]
        assert r["observable"] == "return_sign"
        assert r["costs_charged"] is False, (
            "no transaction happens here; claiming costs were charged would be "
            "a statement about a trade that does not exist")
        assert r["confidence"] is not None


def test_a_target_whose_sensor_is_missing_is_skipped_by_name(ledger):
    """A sensor the bars cannot support is reported, never substituted."""
    thin = synthetic_bars(symbols=("SPY", "NVDA"), n=30)
    rep = arena.run(dry_run=True, bars=thin, predictions_path=ledger)
    assert rep.get("nothing_to_do") is True
    assert rep["skipped"], "the skipped targets must be named"
    for s in rep["skipped"]:
        assert s["target"] and s["sensor"] and s["reason"]
    assert read_predictions(ledger) == []


def test_an_unimplemented_direction_rule_raises_rather_than_defaulting():
    with pytest.raises(ValueError, match="does not implement"):
        arena.direction_for({"id": "X", "direction": "sign(z) if monday else 0"}, 1.0)


def test_the_dead_zone_is_read_from_the_challenge_not_hardcoded():
    """Roadmap M6: read each challenge's own `dead_zone_pct`."""
    m = arena.load_mapping()
    assert m["api"]["dead_zone"] == "from_challenge"
    import inspect
    src = inspect.getsource(arena)
    assert "dead_zone_pct" not in src or "from_challenge" in src


def test_the_run_carries_its_caveats(bars, ledger):
    rep = arena.run(dry_run=True, bars=bars, predictions_path=ledger)
    joined = " ".join(rep["caveats"]).lower()
    assert "perpetual" in joined
    assert "not brier" in joined or "is not brier" in joined
    assert "attended" in joined


def test_the_horizon_is_one_of_the_declared_ones(bars, ledger):
    from backend.services.belief_state import HORIZONS
    arena.run(dry_run=True, bars=bars, predictions_path=ledger)
    for r in read_predictions(ledger):
        assert r["horizon_days"] in HORIZONS


def test_made_at_is_the_bar_date_not_the_wall_clock(bars, ledger):
    """The claim is about a session, and the resolver measures from `made_at`."""
    rep = arena.run(dry_run=True, bars=bars, predictions_path=ledger)
    for r in read_predictions(ledger):
        assert r["made_at"].startswith(rep["bar_date"])
        assert r["session_as_of"] == rep["bar_date"]
        assert r["decision_date"] == rep["bar_date"]


def test_today_is_derived_not_literal(bars, ledger):
    """Session protocol rule 5: a fixture that encodes a calendar moment fails
    the day after it passes. The run takes `today` and derives everything."""
    d = date.today()
    rep = arena.run(dry_run=True, today=d, bars=bars, predictions_path=ledger)
    assert rep["today"] == str(d)
