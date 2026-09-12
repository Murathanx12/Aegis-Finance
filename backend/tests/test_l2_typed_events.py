"""L2's night job: the cursor, the refusal counting, the language guard, the kappa.

The model is mocked and the corpus is a `tmp_path` of three rows. Nothing here
starts, stops or probes the real reader -- `probe` is injected, so a machine with
llama-server running gets the same result as one without.
"""

from __future__ import annotations

import json

import pytest

from backend.services import event_extraction as ex
from backend.services import event_vocabulary as vocab
from backend.services import jsonl_io as jio
from scripts import night_l2_typed_events as l2

SOURCE = "alpaca_benzinga_news"          # a real `label_source: true` id


def _corpus_row(i: int, *, title: str = "Acme board authorizes new $1B share buyback program",
                seen: str = "2026-09-11T12:00:00+00:00", body: str = "",
                tickers=("ACME",)) -> dict:
    return {"source": SOURCE, "first_seen_utc": seen, "published_utc": seen,
            "url": f"https://example.invalid/{i}", "title": title, "body": body,
            "lang": "en", "tickers": list(tickers), "entity_tags": [],
            "raw_id": f"{i:04d}", "pit_grade": "native_stamp"}


def _answer(event_type="stock_buyback", direction=1, bucket="SMALL", conf=0.85,
            span="board authorizes") -> str:
    return json.dumps({"event_type": event_type, "direction": direction,
                       "magnitude_bucket": bucket, "confidence": conf,
                       "evidence_span": span})


class _Reply:
    def __init__(self, text):
        self.text = text
        self.tokens_in, self.tokens_out = 300, 60
        self.cost_usd, self.latency_s = 0.0, 1.2


def _complete(answers):
    """A fake `complete` that walks a list of replies, then repeats the last."""
    box = {"i": 0, "calls": 0}

    def fn(backend, prompt, *, system, max_tokens, temperature, purpose):
        box["calls"] += 1
        text = answers[min(box["i"], len(answers) - 1)]
        box["i"] += 1
        return _Reply(text)
    fn.box = box
    return fn


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """The job pointed entirely at `tmp_path`. Nothing touches the real corpus."""
    corpus = tmp_path / "news_corpus"
    typed = tmp_path / "typed_events"
    (corpus / SOURCE).mkdir(parents=True)
    monkeypatch.setattr(l2, "CORPUS", corpus)
    monkeypatch.setattr(l2, "TYPED", typed)
    monkeypatch.setattr(l2, "CURSOR_PATH", typed / "_cursor.json")
    monkeypatch.setattr(l2, "MANIFEST_PATH", typed / "MANIFEST.json")
    monkeypatch.setattr(l2, "OUT_DIR", tmp_path / "night_factory")
    return {"corpus": corpus, "typed": typed, "tmp": tmp_path}


def _write(corpus, rows, name="2026-09-11.jsonl", mode="w", ensure_ascii=True):
    """`ensure_ascii=False` is how the real corpus is written -- which is why a
    raw U+2028 can reach the file at all: the default escapes it."""
    path = corpus / SOURCE / name
    with path.open(mode, encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=ensure_ascii) + "\n")
    return path


# ------------------------------------------------------------------ the cursor

def test_the_cursor_resumes_and_never_re_types_a_row(wired):
    _write(wired["corpus"], [_corpus_row(i, seen=f"2026-09-11T12:0{i}:00+00:00")
                             for i in range(3)])
    fake = _complete([_answer()])
    first = l2.L2_typed_events(complete=fake, probe=lambda b: None, kappa_rows=0)
    assert first["results"]["rows_typed"] == 3
    typed_file = wired["typed"] / first["results"]["output_file"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    assert sum(1 for _ in jio.iter_rows(typed_file)) == 3
    calls_after_first = fake.box["calls"]

    # second run, same corpus: nothing to do, and NO model call
    again = l2.L2_typed_events(complete=fake, probe=lambda b: None, kappa_rows=0)
    assert again["status"] == "done"
    assert "NOTHING TO DO" in again["verdict"]
    assert fake.box["calls"] == calls_after_first

    # two new rows arrive: only those two are typed
    _write(wired["corpus"], [_corpus_row(i, seen=f"2026-09-11T13:0{i}:00+00:00")
                             for i in (7, 8)], mode="a")
    third = l2.L2_typed_events(complete=fake, probe=lambda b: None, kappa_rows=0)
    assert third["results"]["rows_read"] == 2
    assert third["results"]["rows_typed"] == 2
    assert sum(1 for _ in jio.iter_rows(typed_file)) == 5


def test_the_cursor_carries_its_totals_across_runs(wired):
    _write(wired["corpus"], [_corpus_row(0)])
    l2.L2_typed_events(complete=_complete([_answer()]), probe=lambda b: None, kappa_rows=0)
    _write(wired["corpus"], [_corpus_row(1, seen="2026-09-11T14:00:00+00:00")], mode="a")
    l2.L2_typed_events(complete=_complete([_answer()]), probe=lambda b: None, kappa_rows=0)
    cur = json.loads((wired["typed"] / "_cursor.json").read_text(encoding="utf-8"))
    assert cur["rows_written_total"] == 2 and cur["runs"] == 2


def test_a_corrupt_cursor_is_a_refusal_not_a_fresh_start(wired):
    (wired["typed"]).mkdir(parents=True, exist_ok=True)
    (wired["typed"] / "_cursor.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        l2.load_cursor()
    assert "duplicate every row already typed" in str(exc.value)


# --------------------------------------------------------------- the refusals

def test_a_refused_row_is_counted_and_kept_never_dropped(wired):
    _write(wired["corpus"], [_corpus_row(i, seen=f"2026-09-11T12:0{i}:00+00:00")
                             for i in range(3)])
    fake = _complete([_answer(), "I think this is an earnings beat, probably.", _answer()])
    out = l2.L2_typed_events(complete=fake, probe=lambda b: None, kappa_rows=0)
    assert out["results"]["rows_read"] == 3
    assert out["results"]["rows_typed"] == 2
    assert out["results"]["refused"]["REFUSED_UNPARSEABLE"] == 1
    assert out["results"]["refusal_rate"] == pytest.approx(1 / 3, abs=1e-3)
    kept = list(jio.iter_rows(wired["typed"].glob("*_refusals.jsonl").__next__()))
    assert len(kept) == 1 and kept[0]["reason"] == "REFUSED_UNPARSEABLE"
    assert kept[0]["raw"].startswith("I think this is an earnings beat")


def test_the_language_refusal_fires_on_a_mostly_non_latin_reply(wired):
    _write(wired["corpus"], [_corpus_row(0)])
    chinese = json.dumps({"event_type": "earnings_report", "direction": 1,
                          "magnitude_bucket": "MODERATE", "confidence": 0.9,
                          "evidence_span": "公司报告季度业绩超出市场预期利润大幅增长"},
                         ensure_ascii=False)
    out = l2.L2_typed_events(complete=_complete([chinese]), probe=lambda b: None,
                             kappa_rows=0)
    assert out["results"]["refused"]["REFUSED_LANGUAGE"] == 1
    assert out["results"]["rows_typed"] == 0


def test_a_schema_violation_is_its_own_class(wired):
    _write(wired["corpus"], [_corpus_row(0)])
    out = l2.L2_typed_events(
        complete=_complete([json.dumps({"event_type": "analyst_upgrade", "direction": 1,
                                        "magnitude_bucket": "SMALL", "confidence": 0.8,
                                        "evidence_span": "x"})]),
        probe=lambda b: None, kappa_rows=0)
    assert out["results"]["refused"]["REFUSED_SCHEMA"] == 1


def test_a_no_event_row_is_written_like_any_other(wired):
    """It is how L2 measures the corpus's genuine event rate."""
    _write(wired["corpus"], [_corpus_row(0, title="5 things to know before the open")])
    out = l2.L2_typed_events(
        complete=_complete([_answer("no_event", 0, "NEGLIGIBLE", 0.7, "")]),
        probe=lambda b: None, kappa_rows=0)
    assert out["results"]["rows_typed"] == 1
    assert out["results"]["no_event_rows"] == 1
    assert out["results"]["no_event_share"] == 1.0
    assert sum(out["results"]["refused"].values()) == 0


# ---------------------------------------------------------------- eligibility

def test_only_label_source_feeds_are_read(wired):
    (wired["corpus"] / "google_news_rss_en_us").mkdir()
    (wired["corpus"] / "google_news_rss_en_us" / "2026-09-11.jsonl").write_text(
        json.dumps(_corpus_row(0) | {"source": "google_news_rss_en_us"}) + "\n",
        encoding="utf-8")
    _write(wired["corpus"], [_corpus_row(1)])
    files = l2.corpus_files()
    assert [f.parent.name for f in files] == [SOURCE]


def test_a_row_from_a_non_label_source_refuses_the_run(wired):
    _write(wired["corpus"], [_corpus_row(0) | {"source": "quantocracy_rss"}])
    with pytest.raises(ValueError) as exc:
        l2.read_rows(l2.corpus_files() or [wired["corpus"] / SOURCE / "2026-09-11.jsonl"])
    assert "cannot label a return" in str(exc.value)


def test_a_line_separator_inside_a_body_does_not_split_the_row(wired):
    """MEASURED on the real corpus: nine Benzinga bodies carry a literal U+2028,
    which `str.splitlines()` breaks on and JSONL does not."""
    path = _write(wired["corpus"], [_corpus_row(0, body="first\u2028second"),
                                    _corpus_row(1, seen="2026-09-11T12:05:00+00:00")],
                  ensure_ascii=False)
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) == 3            # what the broken reader sees
    assert jio.over_split_count(text) == 1
    rows, problems = l2.read_rows([path])
    assert len(rows) == 2 and problems == []


# ----------------------------------------------------------------- PIT + scope

def test_the_prompts_date_is_the_panels_own_pit_anchor():
    """A `native_stamp` backfill row is anchored on `published_utc`, not on the
    day we downloaded it. The Alpaca backfill is 3,799 rows all first seen on
    2026-09-11 and published from 2015 on; anchoring on `first_seen_utc` would
    show the model the wrong decade and stack every typed row onto one session."""
    from scripts.night_e1_news_return_panel import _anchor

    row = _corpus_row(0, seen="2026-09-11T12:00:00+00:00")
    row["published_utc"] = "2015-01-01T00:00:00+00:00"
    row["pit_grade"] = "native_stamp"
    assert l2.document_date(row) == "2015-01-01" == _anchor(row)[0][:10]
    assert l2.anchor_field(row) == "published_utc"
    assert "2015-01-01" in l2.prompt_for(row)

    crawled = dict(row, pit_grade="first_seen_only")
    assert l2.document_date(crawled) == "2026-09-11"
    assert l2.anchor_field(crawled) == "first_seen_utc"


def test_a_multi_ticker_document_is_one_row_scoped_to_the_first():
    row = _corpus_row(0, tickers=("LLY", "NVS"))
    assert l2.scope_of(row) == ("LLY", "ticker")
    row2 = _corpus_row(1, tickers=())
    assert l2.scope_of(row2) == ("MARKET", "macro_topic")


# ----------------------------------------------------------- the model is down

def test_pending_model_freezes_the_inputs_and_makes_no_call(wired):
    _write(wired["corpus"], [_corpus_row(i, seen=f"2026-09-11T12:0{i}:00+00:00")
                             for i in range(3)])
    fake = _complete([_answer()])
    out = l2.L2_typed_events(complete=fake,
                             probe=lambda b: "ProviderRefusal: nothing is listening")
    assert out["status"] == "PENDING_MODEL"
    assert fake.box["calls"] == 0, "PENDING_MODEL must not call the model"
    assert out["inputs_frozen"]["n_rows"] == 3
    assert len(out["inputs_frozen"]["inputs_sha256"]) == 64
    frozen = json.loads(open(out["inputs_frozen"]["file"], encoding="utf-8").read())
    assert frozen["keys"] == [[SOURCE, f"2026-09-11T12:0{i}:00+00:00", f"{i:04d}"]
                              for i in range(3)]
    # and the cursor did NOT move: nothing was typed
    assert not (wired["typed"] / "_cursor.json").exists()


def test_the_frozen_hash_is_a_function_of_the_documents(wired):
    rows = [_corpus_row(i, seen=f"2026-09-11T12:0{i}:00+00:00") for i in range(3)]
    a = l2.inputs_fingerprint(rows)
    b = l2.inputs_fingerprint(rows[:2])
    assert a["inputs_sha256"] != b["inputs_sha256"]
    assert l2.inputs_fingerprint(rows)["inputs_sha256"] == a["inputs_sha256"]


def test_the_projection_names_its_assumptions_and_its_rates(wired):
    rows = [_corpus_row(i) for i in range(10)]
    proj = l2.projection(rows)
    assert proj["rows"] == 10
    assert proj["assumptions"]["chars_per_token"] == 4.0
    for name, block in proj["per_rate"].items():
        assert block["total_hours_with_prefix_cache"] <= block["total_hours_no_prefix_cache"]
    assert proj["empirical_anchor_r2_panelA"]["measured_seconds_per_call"] == 0.379
    assert proj["generation_only_at_20_tok_s_hours"] > 0


# ----------------------------------------------------------------- inter-rater

def test_perfect_agreement_is_kappa_one_and_a_disagreement_is_less():
    a = ["earnings_report"] * 8 + ["guidance_change"] * 2
    assert l2.cohens_kappa(a, a) == pytest.approx(1.0)
    b = ["guidance_change"] * 10
    assert l2.cohens_kappa(a, b) is None or l2.cohens_kappa(a, b) <= 0.0


def test_weighted_kappa_penalises_a_two_bucket_miss_more_than_a_one_bucket_miss():
    base = ["SMALL", "MODERATE", "LARGE", "SMALL", "MODERATE", "LARGE"]
    near = ["SMALL", "MODERATE", "MODERATE", "SMALL", "MODERATE", "MODERATE"]
    far = ["SMALL", "MODERATE", "NEGLIGIBLE", "SMALL", "MODERATE", "NEGLIGIBLE"]
    k_near = l2.weighted_kappa(base, near, list(vocab.MAGNITUDE_BUCKETS))
    k_far = l2.weighted_kappa(base, far, list(vocab.MAGNITUDE_BUCKETS))
    assert k_near > k_far


def test_the_second_prompt_is_a_second_hash_over_the_same_rows(wired):
    _write(wired["corpus"], [_corpus_row(i, seen=f"2026-09-11T12:0{i}:00+00:00")
                             for i in range(4)])
    seen_systems = []

    def fn(backend, prompt, *, system, max_tokens, temperature, purpose):
        seen_systems.append(system)
        return _Reply(_answer())

    out = l2.L2_typed_events(complete=fn, probe=lambda b: None, kappa_rows=2)
    assert out["inter_rater"]["n"] == 2
    assert out["inter_rater"]["kappa_event_type"] in (None, 1.0)   # identical answers
    assert out["inter_rater"]["confidence_mean_abs_difference"] == 0.0
    assert out["inter_rater"]["spec_control_size"] == 500
    assert seen_systems.count(ex.SYSTEM_PROMPT) == 4
    assert seen_systems.count(ex.SYSTEM_PROMPT_B) == 2


# ------------------------------------------------------------------- manifest

def test_the_manifest_is_written_beside_the_gitignored_data(wired):
    _write(wired["corpus"], [_corpus_row(0)])
    out = l2.L2_typed_events(complete=_complete([_answer()]), probe=lambda b: None,
                             kappa_rows=0)
    man = out["manifest"]
    assert man["typed_rows_total"] == 1
    assert man["vocabulary_hash"] == vocab.VOCABULARY_HASH
    assert man["prompt_hash_A"] == ex.PROMPT_HASH
    assert len(man["files"][0]["sha256"]) == 64
    assert json.loads((wired["typed"] / "MANIFEST.json").read_text(encoding="utf-8"))


def test_every_typed_row_carries_its_corpus_key_and_both_hashes(wired):
    _write(wired["corpus"], [_corpus_row(0)])
    l2.L2_typed_events(complete=_complete([_answer()]), probe=lambda b: None, kappa_rows=0)
    row = next(jio.iter_rows(next(p for p in wired["typed"].glob("*.jsonl")
                                  if not p.name.endswith("_refusals.jsonl"))))
    assert row["source"] == SOURCE and row["raw_id"] == "0000"
    assert row["prompt_hash"] == ex.PROMPT_HASH
    assert row["vocabulary_hash"] == vocab.VOCABULARY_HASH
    assert row["scope"] == "ACME" and row["pit_grade"] == "native_stamp"


# ----------------------------------------------------------- factory wiring

def test_the_factory_knows_the_job_and_calls_it_resumable():
    from scripts import night_factory_jobs as nf
    assert "L2_typed_events" in nf.JOBS
    assert "L2_typed_events" in nf.RESUMABLE
    assert nf.JOB_STAGES["L2_typed_events"] == "features"
