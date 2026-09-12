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
def creds(monkeypatch):
    """Credentials for the tests that exercise the POST path.

    They are absent by default (`_no_credentials`), which is the real state of
    this environment; a test that needs them says so.
    """
    monkeypatch.setenv(arena.AGENT_ID_ENV, "test-agent")
    monkeypatch.setenv(arena.CLIENT_SECRET_ENV, "test-secret")


@pytest.fixture()
def ledger(tmp_path):
    return tmp_path / "predictions.jsonl"


@pytest.fixture(autouse=True)
def _receipts_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(arena, "receipt_dir", lambda: tmp_path / "arena_receipts")


class Recorder:
    """An HTTP POST layer that records instead of calling.

    Takes the optional bearer the submit path passes, because the token call
    and the submit call go through the same poster and only the second one
    carries a token.
    """

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.tokens: list = []

    def __call__(self, url: str, body: dict, token=None) -> dict:
        self.calls.append((url, body))
        self.tokens.append(token)
        if url.endswith("/auth/token"):
            return {"access_token": "a-test-bearer", "expires_in": 3600}
        return {"ok": True}

    @property
    def submits(self) -> list:
        return [(u, b) for u, b in self.calls if u.endswith("/predict")]


class ChallengeGetter:
    """A GET layer that returns one open challenge per target."""

    def __init__(self, dead_zone_pct: float = 0.25,
                 targets=("ES", "CL", "ZN", "GC", "DXY")):
        self.urls: list[str] = []
        self.dead_zone_pct = dead_zone_pct
        self.targets = tuple(targets)

    def __call__(self, url: str):
        self.urls.append(url)
        return {"challenges": [
            {"id": f"ch-{t}", "target_key": t,
             "dead_zone_pct": self.dead_zone_pct,
             "resolution_criteria": "settled T+24h"} for t in self.targets]}


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
    rec, get = Recorder(), ChallengeGetter()
    rep = arena.run(dry_run=False, bars=bars, predictions_path=ledger,
                    http_post=rec, http_get=get)
    assert rec.submits
    rows = read_predictions(ledger)
    ledger_conf = sorted(round(abs(2 * r["probability"] - 1), 6) for r in rows)
    assert sorted(b["confidence"] for _u, b in rec.submits) == ledger_conf
    for _url, body in rec.submits:
        assert body["direction"] in ("bullish", "bearish", "neutral")
    assert rep["n_posted"] == len(rec.submits)


def test_the_confidence_is_capped(bars):
    m = arena.load_mapping()
    assert arena.confidence_from_z(100.0, m) == m["confidence"]["ceiling"]
    assert arena.confidence_from_z(0.0, m) == m["confidence"]["floor"]


def test_the_submitted_reasoning_carries_no_holding(bars, ledger, monkeypatch):
    """Their terms take a perpetual, sublicensable licence to submitted text."""
    monkeypatch.setenv(arena.AGENT_ID_ENV, "a")
    monkeypatch.setenv(arena.CLIENT_SECRET_ENV, "b")
    rec, get = Recorder(), ChallengeGetter()
    arena.run(dry_run=False, bars=bars, predictions_path=ledger,
              http_post=rec, http_get=get)
    assert rec.submits
    for _url, body in rec.submits:
        text = (body["reasoning"] + " " + body["summary"]).lower()
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


def test_the_dead_zone_is_read_from_the_challenge_not_hardcoded(bars, ledger, creds):
    """Roadmap M6: read each challenge's own `dead_zone_pct`.

    The v1 form of this test was a grep over the module source. It said
    nothing about behaviour and it broke the moment the variable was actually
    implemented -- the same shape as the three guards that matched their own
    docstrings on 2026-09-11. This one changes the VENUE's number and watches
    the threshold move.
    """
    m = arena.load_mapping()
    assert m["api"]["dead_zone"] == "from_challenge"
    narrow = arena.effective_neutral_z(m, 0.25)
    wide = arena.effective_neutral_z(m, 2.50)
    assert wide == pytest.approx(narrow * 10.0)
    rec, get = Recorder(), ChallengeGetter(dead_zone_pct=2.50)
    arena.run(dry_run=False, bars=bars, predictions_path=ledger,
              http_post=rec, http_get=get)
    rows = read_predictions(ledger)
    assert rows
    for r in rows:
        assert r["inputs_used"]["dead_zone_pct"] == 2.50
        assert r["inputs_used"]["dead_zone_source"] == "challenge"


def test_a_run_that_fetched_no_challenge_says_the_dead_zone_was_assumed(
        bars, ledger):
    rep = arena.run(dry_run=True, bars=bars, predictions_path=ledger)
    assert rep["dead_zone_source"].startswith("mapping_default")
    for r in read_predictions(ledger):
        assert r["inputs_used"]["dead_zone_source"] == "mapping_default"


def test_a_wide_dead_zone_turns_a_weak_view_into_neutral():
    m = arena.load_mapping()
    target = {"id": "ES", "direction": "sign(z)"}
    assert arena.direction_for(target, 0.5, mapping=m, dead_zone_pct=0.25) == 1
    assert arena.direction_for(target, 0.5, mapping=m, dead_zone_pct=2.50) == 0


def test_a_neutral_call_is_probability_one_half_and_confidence_zero(
        bars, ledger, creds):
    rec, get = Recorder(), ChallengeGetter(dead_zone_pct=100.0)
    arena.run(dry_run=False, bars=bars, predictions_path=ledger,
              http_post=rec, http_get=get)
    rows = read_predictions(ledger)
    assert rows and all(r["probability"] == 0.5 for r in rows)
    for _u, body in rec.submits:
        assert body["direction"] == "neutral"
        assert body["confidence"] == 0.0


def test_the_payload_is_exactly_the_venues_five_fields(bars, ledger, creds):
    rec, get = Recorder(), ChallengeGetter()
    arena.run(dry_run=False, bars=bars, predictions_path=ledger,
              http_post=rec, http_get=get)
    assert rec.submits
    for _u, body in rec.submits:
        assert set(body) == {"direction", "confidence", "reasoning", "summary",
                             "prompt_hash"}
        assert len(body["prompt_hash"]) == 64
        assert 0.0 <= body["confidence"] <= 1.0


def test_the_token_is_fetched_first_and_carried_as_a_bearer(bars, ledger, creds):
    rec, get = Recorder(), ChallengeGetter()
    arena.run(dry_run=False, bars=bars, predictions_path=ledger,
              http_post=rec, http_get=get)
    assert rec.calls[0][0].endswith("/api/v1/agent/auth/token")
    assert rec.calls[0][1]["grant_type"] == "client_credentials"
    assert rec.tokens[0] is None
    assert all(tok == "a-test-bearer" for tok in rec.tokens[1:])


def test_the_submit_url_is_addressed_by_challenge_id(bars, ledger, creds):
    rec, get = Recorder(), ChallengeGetter()
    arena.run(dry_run=False, bars=bars, predictions_path=ledger,
              http_post=rec, http_get=get)
    assert rec.submits
    for url, _b in rec.submits:
        assert "/api/v1/eval/challenges/ch-" in url
        assert url.endswith("/predict")


def test_a_target_with_no_open_challenge_is_skipped_not_guessed(bars, ledger, creds):
    rec, get = Recorder(), ChallengeGetter(targets=("ES",))
    rep = arena.run(dry_run=False, bars=bars, predictions_path=ledger,
                    http_post=rec, http_get=get)
    assert len(rec.submits) == 1
    skipped = [s for s in rep["submissions"] if s.get("skipped")]
    assert len(skipped) == 4
    assert all("no OPEN challenge" in s["skipped"] for s in skipped)


def test_the_challenge_listing_is_asked_for_open_challenges_only(bars, ledger, creds):
    rec, get = Recorder(), ChallengeGetter()
    arena.run(dry_run=False, bars=bars, predictions_path=ledger,
              http_post=rec, http_get=get)
    assert get.urls and all("status=open" in u for u in get.urls)


def test_a_token_that_fails_posts_nothing_and_keeps_the_rows(bars, ledger, creds):
    def poster(url, body, token=None):
        if url.endswith("/auth/token"):
            raise RuntimeError("401")
        raise AssertionError("nothing may be posted without a token")

    rep = arena.run(dry_run=False, bars=bars, predictions_path=ledger,
                    http_post=poster, http_get=ChallengeGetter())
    assert rep["posted"] is False
    assert "token call failed" in rep["reason_not_posted"]
    assert len(read_predictions(ledger)) == rep["n_rows"] > 0


def test_the_results_endpoint_is_the_settlement_read():
    m = arena.load_mapping()
    seen: list = []

    def getter(url):
        seen.append(url)
        return {}

    arena.fetch_results(m, "ch-ES", http_get=getter)
    assert seen == ["https://headlinearena.com/api/v1/eval/challenges/"
                    "ch-ES/results"]


def test_the_mapping_was_re_registered_and_says_so():
    m = arena.load_mapping()
    assert m["version"] == 2
    hist = m["registration_history"]
    assert hist[0]["prereg_hash"] == "e70b4fff23c0c6a7"
    assert "SUPERSEDED BEFORE ANY SUBMISSION" in hist[0]["status"]
    assert m["prereg_hash"] != hist[0]["prereg_hash"]


def test_the_ternary_block_is_inside_the_pre_registration_hash():
    """The neutral floor IS a rule, and a rule outside the hash can move
    unnoticed -- which is the one thing the hash exists to prevent."""
    assert "ternary" in arena.HASHED_BLOCKS
    m = arena.load_mapping()
    before = arena.prereg_hash(m)
    m["ternary"]["neutral_z"] = 0.9
    assert arena.prereg_hash(m) != before


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
