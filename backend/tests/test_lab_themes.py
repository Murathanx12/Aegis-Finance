"""MURAT'S THEMES AS STREAMS (chunk 14, loop 7) — registration, not invention.

What is pinned here is mostly what these streams REFUSE to do:

* **registration is idempotent by `mechanism_id`.** Two supervisor restarts
  produce one row per theme, and `first_registered_utc` never moves — a stream
  whose inception shifted on every restart would make its own history
  unreadable.
* **no stream writes a probability it cannot justify.** `holders_13f_v1` has a
  working data source and still accrues OBSERVATIONS rather than forecasts,
  because it has no fitted model and no trailing record to anchor `p` on, and
  an LLM number is never admissible. The forecast gate is a count.
* **a placeholder stays in the payload.** A stream that vanished while it waited
  is a stream somebody invents from nothing later, with no history.
* **"the business, the future, anything" is NOT a mechanism**, and the reason is
  in the payload rather than only in a commit message.

Nothing here touches the network: the ownership fetch is injected. Dates come
from `date.today()`.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from backend import config as _config
from backend.services import lab_themes as T


@pytest.fixture
def themes_dir(tmp_path, monkeypatch):
    (tmp_path / "optimus").mkdir(parents=True)
    monkeypatch.setattr(_config, "DATA_DIR", tmp_path)
    return tmp_path


def fake_owner(ok=("NVDA",)):
    def _fetch(ticker):
        if ticker not in ok:
            return None
        return {"holders": [{"holder": "A"}, {"holder": "B"}],
                "pct_institutional": 0.61, "crowding": "high"}
    return _fetch


# --------------------------------------------------------------------------
# registration


def test_thematic_stream_registration_is_idempotent(themes_dir):
    first = T.register_streams()
    assert set(first) == {t["mechanism_id"] for t in T.THEMES}
    inception = {k: v["first_registered_utc"] for k, v in first.items()}

    second = T.register_streams()
    assert set(second) == set(first), "a restart created a second set of streams"
    assert {k: v["first_registered_utc"] for k, v in second.items()} == inception, (
        "a stream's inception moved on restart; its own history is then unreadable")

    rec = json.loads(T.registry_path().read_text(encoding="utf-8"))
    assert len(rec["streams"]) == len(T.THEMES)


def test_every_stream_carries_murats_own_words_as_its_origin(themes_dir):
    streams = T.register_streams()
    for row in streams.values():
        assert row["origin"] == "murat_theme"
        assert row["origin_text"] == T.ORIGIN_TEXT
        assert "linkedin theory" in row["origin_text"]


def test_the_catch_all_is_not_a_stream_and_says_why(themes_dir):
    T.register_streams()
    rec = json.loads(T.registry_path().read_text(encoding="utf-8"))
    assert "the business, the future, anything" in rec["not_a_stream"]["theme"]
    assert "applies_when" in rec["not_a_stream"]["why"]
    assert "the business" not in {t["theme"] for t in T.THEMES}


def test_the_registry_is_written_atomically(themes_dir):
    T.register_streams()
    assert T.registry_path().exists()
    assert not T.registry_path().with_suffix(".json.tmp").exists()


# --------------------------------------------------------------------------
# readiness is checked against the repository, not copied from the spec


def test_hiring_is_awaiting_a_collector_not_live(themes_dir):
    """The registry row is `implemented: false` and its own note says the
    collector is not built. A YAML row is a promise to pull, not a puller."""
    row = T.theme("hiring_pivot_ai_v1")
    assert row["readiness"] == "registered_awaiting_collector"
    assert "hiring_pull.py" in row["blocked_by"]
    assert "LinkedIn itself is banned" in row["blocked_by"]
    assert row["trial"].startswith("TRIAL-HIRING-PIVOT-1")


def test_the_registry_row_this_claim_rests_on_really_is_unimplemented():
    """Assert the FACT, not my reading of it — if someone implements the ATS
    collector, this test fails and the readiness above must be revisited."""
    from backend.services import news_registry
    src = news_registry.get("greenhouse_lever_ashby_ats")
    assert src.implemented is False
    assert src.label_source is False


def test_pivot_to_ai_is_blocked_on_a_vocabulary_id_that_does_not_exist(themes_dir):
    row = T.theme("pivot_to_ai_narrative_v1")
    assert row["readiness"] == "placeholder"
    from backend.services import event_vocabulary
    assert not [e for e in event_vocabulary.EVENT_TYPES if "pivot" in e], (
        "a strategic-pivot id now exists; this stream can move past placeholder")


def test_motivation_names_the_collector_that_would_be_needed(themes_dir):
    row = T.theme("management_motivation_v1")
    assert row["readiness"] == "placeholder"
    assert row["data_source"] is None
    assert "transcripts" in row["blocked_by"]


def test_holders_carries_its_known_weak_prior_on_the_row(themes_dir):
    row = T.theme("holders_13f_v1")
    assert row["readiness"] == "observing"
    assert "45-day" in row["known_weak_prior"]
    assert "coin flip" in row["known_weak_prior"], (
        "a reader of the daily line must not be surprised by this stream's Brier")


# --------------------------------------------------------------------------
# observations, and the forecast gate


def test_holders_writes_observations_and_never_a_probability(themes_dir):
    out = T.observe_holders(["NVDA"], fetch=fake_owner())
    assert out["observed"] == 1
    rows = [json.loads(x) for x in
            T.observations_path().read_text(encoding="utf-8").splitlines() if x]
    assert len(rows) == 1
    r = rows[0]
    assert r["is_forecast"] is False
    assert "probability" not in r
    assert "invented" in r["why_not_a_forecast"]
    assert r["first_seen_utc"], "the PIT anchor is the stamp WE wrote"
    assert r["n_holders"] == 2


def test_a_name_whose_source_returns_nothing_is_recorded_by_name(themes_dir):
    out = T.observe_holders(["NVDA", "GONE"], fetch=fake_owner(ok=("NVDA",)))
    assert out["observed"] == 1
    assert [u["ticker"] for u in out["unavailable"]] == ["GONE"], (
        "an observation series with silent holes reads as a complete series")


def test_a_raising_fetch_is_recorded_not_swallowed(themes_dir):
    def _boom(ticker):
        raise TimeoutError("yahoo hung")
    out = T.observe_holders(["NVDA"], fetch=_boom)
    assert out["observed"] == 0
    assert "TimeoutError" in out["unavailable"][0]["why"]


def test_the_forecast_gate_is_a_count_and_says_how_far_off_it_is(themes_dir):
    T.register_streams()
    gate = T.may_forecast("holders_13f_v1")
    assert gate["may_forecast"] is False
    assert gate["required"] == T.MIN_OBSERVATIONS_BEFORE_FORECAST
    assert "invented" in gate["why_not"]


def test_run_due_observes_once_then_respects_the_weekly_cadence(themes_dir):
    today = date.today()
    first = T.run_due(["NVDA"], today=today, fetch=fake_owner())
    holders = [r for r in first["streams"] if r["mechanism_id"] == "holders_13f_v1"][0]
    assert holders["n_observations"] == 1 and holders["status"] == "ok"

    same_day = T.run_due(["NVDA"], today=today, fetch=fake_owner())
    holders = [r for r in same_day["streams"] if r["mechanism_id"] == "holders_13f_v1"][0]
    assert holders["due"] is False and holders["status"] == "not_due"
    assert holders["n_observations"] == 0

    later = T.run_due(["NVDA"], today=today + timedelta(days=7), fetch=fake_owner())
    holders = [r for r in later["streams"] if r["mechanism_id"] == "holders_13f_v1"][0]
    assert holders["due"] is True and holders["n_observations"] == 1


def test_every_stream_including_the_placeholders_is_in_the_payload(themes_dir):
    out = T.run_due([], today=date.today(), fetch=fake_owner())
    got = {r["mechanism_id"] for r in out["streams"]}
    assert got == {t["mechanism_id"] for t in T.THEMES}
    for r in out["streams"]:
        assert r["n_fired"] == 0
        if r["readiness"] != "observing":
            assert r["blocked_by"], r["mechanism_id"]
    assert out["llm_spend_usd"] == 0.0
    assert "placeholder" in out["headline"]


def test_the_status_block_is_one_word_per_stream(themes_dir):
    T.register_streams()
    st = T.status()
    assert set(st) == {t["mechanism_id"] for t in T.THEMES}
    assert set(st.values()) <= set(T.READINESS)


def test_an_undeclared_theme_raises_rather_than_returning_a_blank(themes_dir):
    with pytest.raises(KeyError):
        T.theme("vibes_v1")
