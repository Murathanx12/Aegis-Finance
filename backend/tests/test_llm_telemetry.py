"""The inference ledger — the guards that keep a spend number honest.

Every test here blocks a way of making the LLM look cheaper, more productive,
or more reliable than it was. The two that matter most are the ones with no
metric in them: an unknown model must not be priced at zero, and a broken
ledger must not take down the forecast it was trying to account for.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.config import LLM_PRICE_PER_MTOK
from backend.services import llm_telemetry as tel


@pytest.fixture
def ledger(tmp_path) -> Path:
    return tmp_path / "llm_calls.jsonl"


def _call(**kw):
    base = dict(provider="deepseek", model="deepseek-chat",
                purpose="specialist_forecast", tokens_in=1000, tokens_out=500)
    base.update(kw)
    return tel.build_call(**base)


# ── cost ────────────────────────────────────────────────────────────────────
def test_cost_is_the_published_arithmetic_and_nothing_else():
    p = LLM_PRICE_PER_MTOK["deepseek-chat"]
    got = tel.price_call("deepseek-chat", 1_000_000, 1_000_000)
    assert got == pytest.approx(p["in"] + p["out"])


def test_cached_tokens_are_priced_at_the_cache_rate_not_the_input_rate():
    """The whole reason `extract_usage` normalises the two providers: cached
    input is real spend, but not at the full rate, and pricing it either as
    free or as full input is wrong in a direction someone would act on."""
    p = LLM_PRICE_PER_MTOK["deepseek-chat"]
    full = tel.price_call("deepseek-chat", 1_000_000, 0, 0)
    cached = tel.price_call("deepseek-chat", 0, 0, 1_000_000)
    assert cached == pytest.approx(p["cached_in"])
    assert cached < full
    mixed = tel.price_call("deepseek-chat", 500_000, 0, 500_000)
    assert mixed == pytest.approx((p["in"] + p["cached_in"]) / 2)


def test_a_dated_model_id_prices_as_its_undated_alias():
    """`claude-haiku-4-5-20251001` names the same model as the alias — a rename,
    not a guess, and the config's copilot default uses the dated form."""
    assert (tel.price_call("claude-haiku-4-5-20251001", 1_000_000, 0)
            == tel.price_call("claude-haiku-4-5", 1_000_000, 0))


def test_an_unknown_model_costs_None_and_warns_it_is_never_zero(caplog):
    """THE house failure mode. A fabricated 0.0 would be summed into a spend
    total and read as 'this was free' on every dashboard."""
    with caplog.at_level(logging.WARNING):
        cost = tel.price_call("some-model-nobody-priced", 1_000_000, 1_000_000)
    assert cost is None
    assert cost != 0.0
    assert "no price for model" in caplog.text

    row = _call(model="some-model-nobody-priced")
    assert row.cost_usd is None


def test_every_row_carries_the_estimate_label():
    """A consumer reading the raw JSONL has no other way to know the number is
    a list-price reconstruction rather than a billed amount."""
    row = _call()
    assert row.cost_is_estimate is True
    assert row.pricing_as_of


# ── usage normalisation ─────────────────────────────────────────────────────
def test_openai_cache_hits_are_subtracted_from_the_prompt_total():
    """DeepSeek's prompt_tokens INCLUDES its cache hits; counting both at full
    rate would double-charge the cached span."""
    resp = SimpleNamespace(usage=SimpleNamespace(
        prompt_tokens=1000, completion_tokens=200, prompt_cache_hit_tokens=800))
    u = tel.extract_usage(resp, "deepseek")
    assert u == {"tokens_in": 200, "tokens_out": 200, "cached_tokens": 800}


def test_anthropic_cache_reads_are_added_beside_the_input_count():
    """Anthropic's input_tokens EXCLUDES cache reads; subtracting would erase
    them. Same field, opposite arithmetic — hence one place that knows."""
    resp = SimpleNamespace(usage=SimpleNamespace(
        input_tokens=200, output_tokens=50, cache_read_input_tokens=800))
    u = tel.extract_usage(resp, "anthropic")
    assert u == {"tokens_in": 200, "tokens_out": 50, "cached_tokens": 800}


def test_a_provider_that_reports_no_usage_yields_zeros_not_a_crash():
    assert tel.extract_usage(SimpleNamespace(), "deepseek")["tokens_in"] == 0


# ── the write must never break the caller ───────────────────────────────────
def test_a_failing_ledger_write_is_a_warning_not_an_exception(ledger, caplog,
                                                              monkeypatch):
    def boom(*a, **k):
        raise OSError("disk is gone")

    monkeypatch.setattr(tel, "append", boom)
    with caplog.at_level(logging.WARNING):
        assert tel.record_call(provider="deepseek", model="deepseek-chat",
                               purpose="specialist_forecast",
                               path=ledger) is None
    assert "failed to record" in caplog.text
    assert "MISSING from the ledger" in caplog.text


def test_a_forecast_survives_a_broken_ledger(monkeypatch, tmp_path):
    """A crash in accounting must not cost a specialist its batch. This is the
    end-to-end version: the wired call site returns its forecasts even when
    every telemetry write raises."""
    from backend.services import optimus_specialists as spec

    monkeypatch.setenv("AEGIS_LLM_TELEMETRY_PATH", str(tmp_path / "x.jsonl"))

    def boom(*a, **k):
        raise OSError("disk is gone")

    monkeypatch.setattr(tel, "append", boom)
    batch = spec.run_specialist("biotech", _CANDIDATES,
                                client=_fake_deepseek(_ONE_FORECAST))
    assert len(batch.predictions) == 1


def test_record_call_never_raises_on_a_malformed_argument(ledger):
    """Instrumentation is a caller's least-important concern; a bad kwarg from
    a call site must degrade, not propagate."""
    assert tel.record_call(provider="x", model="deepseek-chat",
                           purpose="p", tokens_in="not-a-number",
                           path=ledger) is None


# ── summary ─────────────────────────────────────────────────────────────────
def test_summary_on_an_empty_ledger_states_a_zero_rather_than_crashing(ledger):
    s = tel.summary(path=ledger)
    assert s["n_calls"] == 0
    assert s["total_cost_usd"] == 0.0
    assert s["status"] == "EMPTY"
    assert s["schema_valid_rate"] is None      # not 1.0 — no calls, no rate
    assert s["predictions_per_dollar"] is None
    assert "uninstrumented" in s["reading"]


def test_the_zero_gradeable_bucket_is_a_first_class_number(ledger):
    """'Spent money, learned nothing' must be readable off the summary, not
    derived by the reader — it is the number the whole file exists for."""
    tel.append([
        _call(purpose="specialist_forecast", prediction_ids=["p1", "p2"]),
        _call(purpose="specialist_forecast", schema_valid=False),   # unparseable
        _call(purpose="copilot_chat"),                              # no records
    ], path=ledger)
    s = tel.summary(path=ledger)

    assert s["n_calls"] == 3
    z = s["zero_gradeable_output"]
    assert z["n_calls"] == 2                    # the invalid one AND the empty one
    assert z["share_of_calls"] == pytest.approx(2 / 3, abs=1e-4)
    assert z["cost_usd"] > 0
    assert z["share_of_spend"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["n_schema_invalid"] == 1
    assert s["schema_valid_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert s["predictions_minted"] == 2
    assert s["by_purpose"]["copilot_chat"]["n_zero_gradeable"] == 1


def test_a_parsed_call_that_minted_nothing_still_counts_as_zero_yield(ledger):
    """schema_valid is not the bar. A specialist whose every forecast was
    refused produced valid JSON and no learning sample."""
    tel.append([_call(schema_valid=True, prediction_ids=[])], path=ledger)
    assert tel.summary(path=ledger)["zero_gradeable_output"]["n_calls"] == 1


def test_an_unpriced_call_makes_the_total_a_declared_lower_bound(ledger):
    tel.append([_call(), _call(model="mystery-model")], path=ledger)
    s = tel.summary(path=ledger)
    assert s["n_unpriced_calls"] == 1
    assert s["total_is_lower_bound"] is True
    assert "mystery-model" in s["unpriced_models"]


def test_summary_slices_by_purpose_and_model(ledger):
    tel.append([_call(purpose="news_summary"),
                _call(purpose="specialist_forecast", model="deepseek-reasoner")],
               path=ledger)
    s = tel.summary(path=ledger)
    assert set(s["by_purpose"]) == {"news_summary", "specialist_forecast"}
    assert set(s["by_model"]) == {"deepseek-chat", "deepseek-reasoner"}
    assert sum(b["cost_usd"] for b in s["by_model"].values()) == pytest.approx(
        s["total_cost_usd"])


def test_since_filters_the_window(ledger):
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    tel.append([_call(ts=old), _call()], path=ledger)
    assert tel.summary(path=ledger)["n_calls"] == 2
    cutoff = date.today() - timedelta(days=1)
    assert tel.summary(since=cutoff, path=ledger)["n_calls"] == 1


# ── the join to the prediction ledger ───────────────────────────────────────
def _write_predictions(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                    encoding="utf-8")


def _pred(pid: str, **kw) -> dict:
    base = {"prediction_id": pid, "ticker": "AAA", "specialist": "biotech",
            "observable": "return_sign", "horizon_days": 20, "probability": 0.6,
            "outcome": None, "brier": None, "void_reason": None}
    base.update(kw)
    return base


def test_no_metric_is_printed_when_nothing_has_resolved(ledger, tmp_path):
    """A Brier over an empty set is not a small number; it is not a number.
    The count is stated instead."""
    preds = tmp_path / "predictions.jsonl"
    _write_predictions(preds, [_pred("p1"), _pred("p2")])
    tel.append([_call(prediction_ids=["p1", "p2"])], path=ledger)

    r = tel.summary(path=ledger, predictions_path=preds)["resolution"]
    assert r["n_resolved"] == 0
    assert "mean_brier" not in r
    assert "0 have resolved yet" in r["reading"]


def test_a_row_claiming_predictions_it_did_not_mint_is_surfaced(ledger, tmp_path,
                                                               caplog):
    """A telemetry row that lies about its yield is worse than no row."""
    preds = tmp_path / "predictions.jsonl"
    _write_predictions(preds, [_pred("p1")])
    tel.append([_call(prediction_ids=["p1", "ghost"])], path=ledger)

    with caplog.at_level(logging.WARNING):
        r = tel.summary(path=ledger, predictions_path=preds)["resolution"]
    assert r["n_matched_in_prediction_ledger"] == 1
    assert r["n_not_found_in_prediction_ledger"] == 1
    assert "ghost" in r["not_found_ids"]
    assert "worse than no row" in caplog.text


def test_cost_per_informative_forecast_once_records_resolve(ledger, tmp_path):
    preds = tmp_path / "predictions.jsonl"
    _write_predictions(preds, [
        _pred("p1", outcome=1, brier=0.04),     # confident and right
        _pred("p2", outcome=1, brier=0.09),
        _pred("p3", outcome=0, brier=0.81),     # confident and wrong
    ])
    tel.append([_call(prediction_ids=["p1", "p2", "p3"])], path=ledger)

    r = tel.summary(path=ledger, predictions_path=preds)["resolution"]
    assert r["n_resolved"] == 3
    assert r["base_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert r["climatology_brier"] == pytest.approx(2 / 9, abs=1e-4)
    assert r["n_informative"] == 2                       # p1, p2 beat climatology
    assert r["cost_per_informative_forecast_usd"] > r["cost_per_resolved_forecast_usd"]


# ── append-only amendments ──────────────────────────────────────────────────
def test_an_amendment_links_outputs_without_rewriting_the_original(ledger):
    """Overwriting the row would delete the evidence of what was known at write
    time; the link arrives as a second line instead."""
    row = _call(purpose="hypothesis_generation")
    tel.append([row], path=ledger)
    tel.attach_outputs(row.call_id, hypothesis_ids=["hyp_a", "hyp_b"],
                       schema_valid=True, path=ledger)

    assert len(ledger.read_text(encoding="utf-8").strip().splitlines()) == 2
    folded = tel.read_calls(ledger)
    assert len(folded) == 1
    assert folded[0]["hypothesis_ids"] == ["hyp_a", "hyp_b"]
    assert tel.summary(path=ledger)["zero_gradeable_output"]["n_calls"] == 0


def test_an_amendment_can_demote_schema_valid(ledger):
    """`ask()` writes schema_valid optimistically because the role's schema is
    only checkable after parsing. The amendment is what makes the unparseable
    case land in the zero-yield bucket."""
    row = _call(purpose="failure_diagnosis", schema_valid=True)
    tel.append([row], path=ledger)
    tel.attach_outputs(row.call_id, schema_valid=False, path=ledger)
    assert tel.read_calls(ledger)[0]["schema_valid"] is False


def test_calls_in_the_same_second_get_distinct_ids(ledger):
    """Regression. At second-resolution timestamps a specialist panel's calls
    collided on call_id, and read_calls deduped one away — the night's spend
    silently understated by one call."""
    rows = [_call(purpose="specialist_forecast") for _ in range(5)]
    assert len({r.call_id for r in rows}) == 5
    tel.append(rows, path=ledger)
    assert tel.summary(path=ledger)["n_calls"] == 5


def test_an_unreadable_line_is_counted_not_silently_skipped(ledger, caplog):
    tel.append([_call()], path=ledger)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write("{not json\n")
    with caplog.at_level(logging.WARNING):
        rows = tel.read_calls(ledger)
    assert len(rows) == 1
    assert "LOWER BOUNDS" in caplog.text


def test_ledger_health_calls_an_empty_ledger_degraded(ledger):
    assert tel.ledger_health(ledger)["status"] == "DEGRADED"
    tel.append([_call()], path=ledger)
    assert tel.ledger_health(ledger)["status"] == "ok"


def test_ledger_health_notices_a_ledger_that_stopped_growing(ledger):
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    tel.append([_call(ts=old)], path=ledger)
    h = tel.ledger_health(ledger)
    assert h["status"] == "DEGRADED"
    assert h["days_quiet"] >= 40


# ── the wiring is real ──────────────────────────────────────────────────────
_CANDIDATES = [{"ticker": "AAA", "as_of": "2026-08-11", "price": 10.0}]

_ONE_FORECAST = json.dumps({"forecasts": [
    {"ticker": "AAA", "observable": "return_sign", "horizon_days": 20,
     "probability": 0.6, "threshold": None, "thesis": "t",
     "counter_thesis": "c", "next_observable": "n"}]})


def _fake_deepseek(content: str, *, tokens=(1200, 300)):
    msg = SimpleNamespace(content=content)
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)], model="deepseek-chat",
        usage=SimpleNamespace(prompt_tokens=tokens[0],
                              completion_tokens=tokens[1],
                              prompt_cache_hit_tokens=0))
    return SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kw: resp)))


def test_a_specialist_run_records_the_ids_it_actually_minted(monkeypatch,
                                                             tmp_path):
    """The link must be real: the row's prediction_ids are the ids of the
    records the batch returned, not a count or a guess."""
    from backend.services import optimus_specialists as spec

    led = tmp_path / "calls.jsonl"
    monkeypatch.setenv("AEGIS_LLM_TELEMETRY_PATH", str(led))
    batch = spec.run_specialist("biotech", _CANDIDATES,
                                client=_fake_deepseek(_ONE_FORECAST))

    rows = tel.read_calls(led)
    assert len(rows) == 1
    assert rows[0]["purpose"] == "specialist_forecast"
    assert rows[0]["agent"] == "biotech"
    assert rows[0]["tokens_in"] == 1200 and rows[0]["tokens_out"] == 300
    assert rows[0]["prediction_ids"] == [p.prediction_id
                                         for p in batch.predictions]
    assert rows[0]["cost_usd"] > 0


def test_an_unparseable_specialist_reply_is_ledgered_before_it_raises(monkeypatch,
                                                                     tmp_path):
    """Money spent, nothing gradeable — the row that an `except: pass` erases."""
    from backend.services import optimus_specialists as spec

    led = tmp_path / "calls.jsonl"
    monkeypatch.setenv("AEGIS_LLM_TELEMETRY_PATH", str(led))
    with pytest.raises(Exception):
        spec.run_specialist("biotech", _CANDIDATES,
                            client=_fake_deepseek("I would rather not."))

    rows = tel.read_calls(led)
    assert len(rows) == 1
    assert rows[0]["schema_valid"] is False
    assert rows[0]["prediction_ids"] == []
    assert tel.summary(path=led)["zero_gradeable_output"]["n_calls"] == 1


def test_a_batch_whose_forecasts_were_all_refused_reads_as_zero_yield(monkeypatch,
                                                                     tmp_path):
    """Valid JSON about a security nobody asked about: parses, mints nothing."""
    from backend.services import optimus_specialists as spec

    led = tmp_path / "calls.jsonl"
    monkeypatch.setenv("AEGIS_LLM_TELEMETRY_PATH", str(led))
    off_universe = json.dumps({"forecasts": [
        {"ticker": "ZZZ", "observable": "return_sign", "horizon_days": 20,
         "probability": 0.6, "threshold": None, "thesis": "t",
         "counter_thesis": "c", "next_observable": "n"}]})
    batch = spec.run_specialist("biotech", _CANDIDATES,
                                client=_fake_deepseek(off_universe))

    assert batch.predictions == [] and batch.refusals
    row = tel.read_calls(led)[0]
    assert row["schema_valid"] is True and row["prediction_ids"] == []
    assert row["meta"]["n_refusals"] == 1
    assert tel.summary(path=led)["zero_gradeable_output"]["n_calls"] == 1


def test_the_analyzer_records_its_purpose_and_schema_verdict(monkeypatch,
                                                             tmp_path):
    """`schema_valid` follows the CALLER's contract: the two-sided card needs
    BULL and BEAR, so loose prose is spend that bought nothing."""
    from backend.services import llm_analyzer as la

    led = tmp_path / "calls.jsonl"
    monkeypatch.setenv("AEGIS_LLM_TELEMETRY_PATH", str(led))
    monkeypatch.setattr(la, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(la, "_DEEPSEEK_API_KEY", "k")
    monkeypatch.setattr(la, "_openai_client",
                        _fake_deepseek("I have no opinion."))

    out = la._call_llm("sys", "usr", purpose="two_sided_signal_card",
                       validate=lambda t: "BULL:" in t and "BEAR:" in t)
    assert out == "I have no opinion."          # the caller is unaffected

    row = tel.read_calls(led)[0]
    assert row["purpose"] == "two_sided_signal_card"
    assert row["provider"] == "deepseek"
    assert row["schema_valid"] is False
    assert tel.summary(path=led)["zero_gradeable_output"]["n_calls"] == 1


def test_a_failed_provider_call_is_ledgered_with_its_error(monkeypatch, tmp_path):
    from backend.services import llm_analyzer as la

    led = tmp_path / "calls.jsonl"
    monkeypatch.setenv("AEGIS_LLM_TELEMETRY_PATH", str(led))
    monkeypatch.setattr(la, "_ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(la, "_DEEPSEEK_API_KEY", "k")

    def blow(**kw):
        raise RuntimeError("upstream 500")

    monkeypatch.setattr(la, "_openai_client", SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=blow))))

    assert la._call_llm("sys", "usr", purpose="news_summary") is None
    row = tel.read_calls(led)[0]
    assert row["schema_valid"] is False
    assert "upstream 500" in row["error"]


def test_a_hypothesis_id_is_stable_across_nights():
    """Keyed on the mechanism, so a model repeating itself does not inflate the
    idea count that spend-per-idea is divided by."""
    from backend.services.llm_research import hypothesis_id

    a = hypothesis_id({"mechanism": "Small-cap revision drift"})
    b = hypothesis_id({"mechanism": "  small-cap revision drift  "})
    c = hypothesis_id({"mechanism": "Something else entirely"})
    assert a == b and a != c


def test_concurrent_appends_do_not_tear_rows(tmp_path):
    """LLM-SWARM-1 measured this failure, so it gets a test.

    24 worker threads wrote 8,014 rows through `append` and TWO came back torn —
    one line holding `"1.0.0"}`, another `"}`. A single short `write()` is
    atomic on POSIX by convention and is not guaranteed on Windows, so the
    accounting silently lost two calls' spend. Losing spend is the one direction
    a cost ledger must not fail in.
    """
    import threading

    from backend.services import llm_telemetry as t

    path = tmp_path / "llm_calls.jsonl"
    n_threads, per_thread = 16, 40

    def writer(k: int) -> None:
        for i in range(per_thread):
            t.record_call(provider="deepseek", model="deepseek-chat",
                          purpose="swarm_specialist_forecast",
                          agent=f"agent{k}", prompt="p" * 200,
                          context={"i": i, "k": k},
                          tokens_in=2500, tokens_out=900,
                          prediction_ids=[f"p{k}-{i}"], path=path)

    threads = [threading.Thread(target=writer, args=(k,))
               for k in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == n_threads * per_thread
    for i, line in enumerate(lines, 1):
        json.loads(line)          # a torn row raises here — that is the point
    assert len(t.read_calls(path)) == n_threads * per_thread


# ── incremental parse (added after MARKET-GRAPH-1 measured the governor
# ── consuming 95% of its throughput on a 21MB ledger) ───────────────────────
#
# These gate SPENDING. If the incremental path disagrees with a full re-parse by
# one row, the ceiling is wrong, and a wrong ceiling is the failure this whole
# module exists to prevent. So every test here compares against a cold re-parse
# rather than against an expected constant.

def _cold(path):
    """A full re-parse from an empty cache — the reference answer."""
    tel._PARSE_CACHE.clear()
    return tel.read_calls(path)


def _append(path, rows):
    with path.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _row(cid, **kw):
    return {"call_id": cid, "ts": "2026-08-12T00:00:00+00:00",
            "model": "deepseek-v4-flash", "tokens_in": 100, "tokens_out": 50,
            "cached_tokens": 0, "cost_usd": 0.0001, "schema_valid": True,
            "prediction_ids": [], **kw}


def test_incremental_read_matches_a_cold_reparse_after_appends(tmp_path):
    p = tmp_path / "calls.jsonl"
    _append(p, [_row(f"c{i}") for i in range(5)])
    warm = tel.read_calls(p)
    assert len(warm) == 5
    _append(p, [_row(f"d{i}") for i in range(3)])
    warm2 = tel.read_calls(p)
    assert [r["call_id"] for r in warm2] == [r["call_id"] for r in _cold(p)]
    assert len(warm2) == 8


def test_a_truncated_or_rewritten_ledger_forces_a_full_reparse(tmp_path):
    """Shrinking is not appending. A cache that trusted mtime alone here would
    keep reporting spend for rows that no longer exist."""
    p = tmp_path / "calls.jsonl"
    _append(p, [_row(f"c{i}") for i in range(6)])
    assert len(tel.read_calls(p)) == 6
    p.write_text(json.dumps(_row("only")) + "\n", encoding="utf-8")
    assert [r["call_id"] for r in tel.read_calls(p)] == ["only"]


def test_a_half_written_final_line_is_held_back_not_counted_as_corrupt(tmp_path):
    """24 concurrent writers tore two lines in LLM-SWARM-1. A line still being
    flushed must be re-read next time, not counted as lost spend."""
    p = tmp_path / "calls.jsonl"
    _append(p, [_row("c0")])
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"call_id": "c1", "model": "deepseek-v4-fl')  # mid-flush
    assert [r["call_id"] for r in tel.read_calls(p)] == ["c0"]
    with p.open("a", encoding="utf-8") as fh:                    # writer finishes
        fh.write('ash", "tokens_in": 1, "tokens_out": 1}\n')
    assert [r["call_id"] for r in tel.read_calls(p)] == ["c0", "c1"]
    assert [r["call_id"] for r in _cold(p)] == ["c0", "c1"]


def test_an_amendment_split_across_two_reads_still_applies(tmp_path):
    """A full parse saw every line before applying, so this pair could never
    split. An incremental parse can end between them; dropping the amendment
    would silently lose the outputs a call claimed."""
    p = tmp_path / "calls.jsonl"
    _append(p, [{"row_type": "amendment", "call_id": "late",
                 "prediction_ids": ["p1"]}])
    assert tel.read_calls(p) == []
    _append(p, [_row("late")])
    rows = tel.read_calls(p)
    assert rows[0]["prediction_ids"] == ["p1"]
    assert _cold(p)[0]["prediction_ids"] == ["p1"]


def test_spend_and_reprice_agree_on_every_row(tmp_path):
    """`spend()` skips reprice() for speed. Same arithmetic or the governor and
    the report disagree about the same ledger."""
    p = tmp_path / "calls.jsonl"
    _append(p, [_row("a"), _row("b", tokens_out=900),
                _row("c", model="unknown-model", cost_usd=None)])
    rows = tel.read_calls(p)
    from_reprice = sum(r["cost_usd"] for r in tel.reprice(rows)
                       if r["cost_usd"] is not None)
    assert tel.spend(path=p)["total_cost_usd"] == pytest.approx(from_reprice)
    assert tel.spend(path=p)["total_is_lower_bound"] is True
