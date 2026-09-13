"""Chunk 15a: the panel as a typing source, concurrency, and the dollar cap.

Nothing here calls a model, starts a reader or spends a cent. `complete` and
`probe` are injected everywhere, the panel is a five-row parquet in `tmp_path`,
and the one test that reads a call ledger writes its own.

The three properties worth naming, because they are the ones that cost money if
they are wrong:

* `--workers N` must produce the SAME rows and the SAME cursor as `--workers 1`.
  A concurrent writer that reorders the cursor re-types or skips rows, and both
  are billed.
* A reader that dies must leave every predecessor on disk and the cursor BEFORE
  the failure -- not after it, which would drop the row for ever, and not at the
  start, which would re-bill the night.
* The spend a receipt prints must come from the CALL LEDGER. The 2026-09-13 run
  printed $0.00 for 7,565 DeepSeek calls because the field was a literal.
"""

from __future__ import annotations

import json
import random
import time

import pytest

from backend.services import event_extraction as ex
from backend.services import jsonl_io as jio
from scripts import night_l2_typed_events as l2

SOURCE = "alpaca_benzinga_news"


# --------------------------------------------------------------------- doubles

def _answer(event_type="stock_buyback", direction=1, bucket="SMALL", conf=0.85,
            span="board authorizes") -> str:
    return json.dumps({"event_type": event_type, "direction": direction,
                       "magnitude_bucket": bucket, "confidence": conf,
                       "evidence_span": span})


class _Reply:
    def __init__(self, text, model="fake"):
        self.text = text
        self.tokens_in, self.tokens_out = 300, 60
        self.cost_usd, self.latency_s, self.model = 0.0, 0.01, model


def _reader(*, jitter=0.0, raise_on_call=None, exc=None, seed=7):
    """A fake `complete`. `jitter` makes the workers finish out of order, which
    is exactly the condition an ordered flush has to survive."""
    rng = random.Random(seed)
    box = {"calls": 0}

    def fn(backend, prompt, *, system, max_tokens, temperature, purpose):
        with _LOCK:
            box["calls"] += 1
            n = box["calls"]
        if jitter:
            time.sleep(rng.random() * jitter)
        if raise_on_call is not None and n >= raise_on_call:
            raise (exc or RuntimeError("reader died"))
        return _Reply(_answer())

    fn.box = box
    return fn


import threading                                                    # noqa: E402
_LOCK = threading.Lock()


def _corpus_row(i: int, *, title="Acme board authorizes new $1B share buyback",
                seen=None, body="", tickers=("ACME",)) -> dict:
    seen = seen or f"2026-09-11T12:{i:02d}:00+00:00"
    return {"source": SOURCE, "first_seen_utc": seen, "published_utc": seen,
            "url": f"https://example.invalid/{i}", "title": f"{title} {i}",
            "body": body, "lang": "en", "tickers": list(tickers),
            "entity_tags": [], "raw_id": f"{i:04d}", "pit_grade": "native_stamp"}


@pytest.fixture
def wired(tmp_path, monkeypatch):
    corpus = tmp_path / "news_corpus"
    typed = tmp_path / "typed_events"
    (corpus / SOURCE).mkdir(parents=True)
    monkeypatch.setattr(l2, "CORPUS", corpus)
    monkeypatch.setattr(l2, "TYPED", typed)
    monkeypatch.setattr(l2, "CURSOR_PATH", typed / "_cursor.json")
    monkeypatch.setattr(l2, "CURSOR_PANEL_PATH", typed / "_cursor_panel.json")
    monkeypatch.setattr(l2, "MANIFEST_PATH", typed / "MANIFEST.json")
    monkeypatch.setattr(l2, "OUT_DIR", tmp_path / "night_factory")
    return {"corpus": corpus, "typed": typed, "tmp": tmp_path}


def _write_corpus(corpus, rows, name="2026-09-11.jsonl", mode="w"):
    path = corpus / SOURCE / name
    with path.open(mode, encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def _typed_on_disk(typed_dir, *, panel=False):
    rows = []
    for path in sorted(typed_dir.glob("panel_*.jsonl" if panel else "*.jsonl")):
        if path.name.endswith("_refusals.jsonl"):
            continue
        if not panel and path.name.startswith("panel_"):
            continue
        rows.extend(jio.iter_rows(path))
    for row in rows:
        row.pop("typed_utc", None)
    return rows


# ================================================================ T1: workers

def test_workers_do_not_change_the_rows_or_the_cursor(wired, tmp_path, monkeypatch):
    """Four workers against a reader with randomised latency must write the same
    rows in the same order, and leave the same cursor, as one worker. This is
    the property the whole ordered-flush design exists for."""
    rows = [_corpus_row(i) for i in range(25)]
    _write_corpus(wired["corpus"], rows)
    monkeypatch.setattr(l2, "FLUSH_EVERY", 4)

    one = l2.L2_typed_events(complete=_reader(jitter=0.004), probe=lambda b: None,
                             kappa_rows=0, workers=1)
    serial_rows = _typed_on_disk(wired["typed"])
    serial_cursor = json.loads((wired["typed"] / "_cursor.json").read_text(encoding="utf-8"))

    # a clean slate, same corpus, four workers
    for path in wired["typed"].glob("*"):
        path.unlink()
    four = l2.L2_typed_events(complete=_reader(jitter=0.004, seed=99),
                              probe=lambda b: None, kappa_rows=0, workers=4)
    parallel_rows = _typed_on_disk(wired["typed"])
    parallel_cursor = json.loads((wired["typed"] / "_cursor.json").read_text(encoding="utf-8"))

    assert one["results"]["rows_typed"] == four["results"]["rows_typed"] == 25
    assert [r["raw_id"] for r in serial_rows] == [r["raw_id"] for r in parallel_rows]
    assert serial_rows == parallel_rows
    assert serial_cursor["per_source"] == parallel_cursor["per_source"]
    assert four["concurrency"]["workers"] == 4
    assert four["concurrency"]["stopped"] == "complete"


def test_a_reader_error_flushes_the_predecessors_and_stops_the_cursor(wired):
    """A reader that raises on row 7 leaves rows 1-6 on disk and the cursor
    before row 7 -- so the next run retries exactly that row and re-bills
    nothing. A reader error is a property of the RUN, not of the document, which
    is why the cursor does not pass it the way it passes a model refusal."""
    rows = [_corpus_row(i) for i in range(10)]
    _write_corpus(wired["corpus"], rows)
    out = l2.L2_typed_events(complete=_reader(raise_on_call=7), probe=lambda b: None,
                             kappa_rows=0, workers=1)

    assert out["status"] == "READER_ERROR"
    assert out["results"]["rows_typed"] == 6
    assert out["results"]["refused"]["REFUSED_READER_ERROR"] == 1
    assert "reader died" in out["concurrency"]["stop_detail"]
    assert out["concurrency"]["failed_index"] == 6

    on_disk = _typed_on_disk(wired["typed"])
    assert [r["raw_id"] for r in on_disk] == [f"{i:04d}" for i in range(6)]
    cursor = json.loads((wired["typed"] / "_cursor.json").read_text(encoding="utf-8"))
    assert cursor["per_source"][SOURCE][1] == "0005"          # before row 6

    # and the failure is KEPT, never dropped
    refusals = list(jio.iter_rows(next(wired["typed"].glob("*_refusals.jsonl"))))
    assert refusals[-1]["reason"] == "REFUSED_READER_ERROR"

    # the restart types exactly the rows the cursor did not pass
    again = l2.L2_typed_events(complete=_reader(), probe=lambda b: None,
                               kappa_rows=0, workers=2)
    assert again["results"]["rows_typed"] == 4
    assert [r["raw_id"] for r in _typed_on_disk(wired["typed"])] == \
        [f"{i:04d}" for i in range(10)]


def test_the_dollar_cap_refuses_further_submissions(wired):
    """The cap is checked BEFORE each submission and stops the run when one more
    row would cross it. Everything already collected is still flushed."""
    _write_corpus(wired["corpus"], [_corpus_row(i) for i in range(20)])
    per_row = l2.MEASURED["usd_per_row"]
    reader = _reader()
    out = l2.L2_typed_events(complete=reader, probe=lambda b: None, kappa_rows=0,
                             workers=1, backend="deepseek", max_usd=per_row * 3.5)
    assert out["status"] == "MAX_USD_CAP"
    assert out["results"]["units_submitted"] == 3
    assert reader.box["calls"] == 3, "the cap must stop SUBMISSIONS, not refund calls"
    assert out["results"]["rows_typed"] == 3
    assert len(_typed_on_disk(wired["typed"])) == 3
    assert out["cap"]["metered"] is True
    assert out["cap"]["max_usd"] == pytest.approx(per_row * 3.5)


def test_a_local_backend_is_unmetered_so_no_dollar_cap_can_bind(wired):
    """A gate that fires on work which cannot produce a bill teaches its reader
    to raise it. Local reads cost compute, not dollars."""
    _write_corpus(wired["corpus"], [_corpus_row(i) for i in range(5)])
    out = l2.L2_typed_events(complete=_reader(), probe=lambda b: None, kappa_rows=0,
                             backend="local_gguf", max_usd=0.0)
    assert out["status"] == "done"
    assert out["results"]["rows_typed"] == 5
    assert out["cap"]["metered"] is False
    assert "costs compute, not dollars" in out["cap"]["unmetered_note"]


def test_the_receipts_spend_comes_from_the_ledger_not_from_a_literal(wired, tmp_path):
    """2026-09-13: 7,565 DeepSeek calls, $2.38 by the ledger's own arithmetic,
    and the receipt said $0.00 because the field was the constant 0.0."""
    from backend.services import llm_telemetry as tel
    ledger = tmp_path / "llm_calls.jsonl"
    for i in range(4):
        tel.record_call(provider="deepseek", model="deepseek-chat",
                        purpose=ex.PURPOSE, tokens_in=1000, tokens_out=50,
                        ts=f"2099-01-01T00:00:0{i}+00:00", path=ledger)
    # a call for a DIFFERENT purpose must not be charged to this run
    tel.record_call(provider="deepseek", model="deepseek-chat", purpose="something_else",
                    tokens_in=900000, tokens_out=900000,
                    ts="2099-01-01T00:00:09+00:00", path=ledger)

    _write_corpus(wired["corpus"], [_corpus_row(i) for i in range(2)])
    out = l2.L2_typed_events(complete=_reader(), probe=lambda b: None, kappa_rows=0,
                             backend="deepseek", ledger_path=ledger)
    expected = l2.spend_from_ledger("2000-01-01T00:00:00+00:00", path=ledger)["usd"]
    assert out["llm_spend_usd"] > 0.0
    assert out["llm_spend_usd"] == pytest.approx(expected, rel=1e-9)
    assert out["usage"]["cost_usd"] == out["llm_spend_usd"]
    assert out["usage"]["ledger"]["calls"] == 4
    assert "the CALL LEDGER" in out["usage"]["cost_source"]
    assert f"${expected:.4f}" in out["verdict"]


def test_a_rate_limit_is_waited_on_and_anything_else_is_raised():
    """A 429 is a request to wait; a 500 is the run's state. Counting the first
    as a refusal throws away a row the provider would have served."""
    assert l2.is_rate_limited(RuntimeError("deepseek HTTP 429: Too Many Requests"))
    assert l2.is_rate_limited(RuntimeError("rate limit exceeded"))
    assert not l2.is_rate_limited(RuntimeError("deepseek HTTP 500: boom"))

    slept: list[float] = []
    box = {"n": 0}

    def flaky(backend, prompt, *, system, max_tokens, temperature, purpose):
        box["n"] += 1
        if box["n"] < 3:
            raise RuntimeError("provider HTTP 429 rate limit")
        return _Reply(_answer())

    unit = l2.corpus_unit(_corpus_row(0))
    out, usage, used = l2.extract_with_backoff(
        unit, backend="deepseek", variant="A", complete=flaky,
        sleep=slept.append, jitter=lambda a, b: b)
    assert not isinstance(out, ex.Refusal)
    assert used == 2 and box["n"] == 3
    assert slept == [l2.RETRY_BASE_S, l2.RETRY_BASE_S * 2], "full-jitter exponential"

    def dead(backend, prompt, *, system, max_tokens, temperature, purpose):
        raise RuntimeError("provider HTTP 500: boom")

    with pytest.raises(RuntimeError):
        l2.extract_with_backoff(unit, backend="deepseek", variant="A",
                                complete=dead, sleep=slept.append)


# ================================================================== T2: panel

@pytest.fixture
def panel(tmp_path):
    """A synthetic panel: one text shared by two symbols, one repeated within a
    symbol, and enough spread to stratify over."""
    import pandas as pd
    rows = []

    def row(uid, sym, pub, entry, title, body="", anchor=None):
        rows.append({"uid": uid, "symbol": sym, "published_utc": pub,
                     "entry_date": entry, "publish_position": "post_bell",
                     "source": "alpaca:benzinga", "title": title, "body": body,
                     "pit_anchor_utc": anchor, "pit_anchor_field":
                         ("published_utc" if anchor else None),
                     "pit_grade": "native_stamp" if anchor else None,
                     "first_seen_utc": "2026-09-11T00:00:00Z"})

    shared = "Sector wide recall announced by regulator"
    row("u1", "AAA", "2025-01-10T21:00:00Z", "2025-01-13", shared)
    row("u2", "BBB", "2025-01-10T21:00:00Z", "2025-01-13", shared)
    row("u3", "AAA", "2025-02-11T21:00:00Z", "2025-02-12", "AAA beats on earnings")
    row("u4", "AAA", "2025-02-11T22:00:00Z", "2025-02-12", "AAA beats on earnings")
    row("u5", "CCC", "2025-03-05T21:00:00Z", "2025-03-06", "CCC announces buyback",
        anchor="2024-12-31T10:00:00Z")
    for i in range(6, 26):
        row(f"u{i}", "AAA" if i % 2 else "BBB",
            f"2025-0{1 + i % 6}-1{i % 9}T21:00:00Z", f"2025-0{1 + i % 6}-2{i % 8}",
            f"Filler headline number {i}")
    path = tmp_path / "panel.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return path


def test_the_joined_hash_equals_the_pair_hash():
    """`panel_units` hashes `title + space + body` once per distinct pair rather
    than calling `text_sha256(title, body)` per row. The two must agree or the
    dedupe key and the double-count guard are different keys."""
    for title, body in (("Acme raises guidance", "The company said."),
                        ("No body here", ""), ("", "body only"),
                        ("spaced   out", "  and   padded ")):
        assert ex.text_sha256(title, body) == ex.text_sha256(f"{title} {body}", "")


def test_panel_units_are_one_per_text_and_carry_the_fanout(panel):
    units = l2.panel_units(path=panel)
    by_hash = {u["text_sha256"]: u for u in units}
    assert len(units) == len(by_hash), "one unit per distinct text"

    shared = [u for u in units if u["title"].startswith("Sector wide recall")]
    assert len(shared) == 1
    u = shared[0]
    assert u["panel_rows"] == 2 and u["panel_symbols"] == 2
    assert sorted(u["panel_cells"]) == [["AAA", "2025-01-13"], ["BBB", "2025-01-13"]]
    assert u["scope"] == "AAA" and u["scope_kind"] == "ticker"

    dup = [x for x in units if x["title"] == "AAA beats on earnings"]
    assert len(dup) == 1 and dup[0]["panel_rows"] == 2
    assert dup[0]["panel_cells"] == [["AAA", "2025-02-12"]]

    total_rows = sum(x["panel_rows"] for x in units)
    assert total_rows == 25, "every panel row is accounted for by exactly one unit"


def test_the_panel_date_is_the_panels_own_pit_anchor(panel):
    """`pit_anchor_utc` where the panel builder wrote one, `published_utc`
    otherwise -- never the day we downloaded the row."""
    units = {u["title"]: u for u in l2.panel_units(path=panel)}
    stamped = units["CCC announces buyback"]
    assert stamped["document_date"] == "2024-12-31"
    assert stamped["document_date_field"] == "published_utc"
    plain = units["Sector wide recall announced by regulator"]
    assert plain["document_date"] == "2025-01-10"
    assert plain["document_date_field"] == "published_utc"
    assert l2.panel_anchor({"pit_anchor_utc": "", "published_utc": "",
                            "first_seen_utc": "2026-01-01T00:00:00Z"}) == \
        ("2026-01-01T00:00:00Z", "first_seen_utc")


def test_stratified_is_seeded_and_spread_over_months_and_buckets(panel):
    units = l2.panel_units(path=panel)
    k = 8
    a = l2.stratified_pick(units, k, seed=11)
    b = l2.stratified_pick(units, k, seed=11)
    c = l2.stratified_pick(units, k, seed=12)
    assert len(a) == k
    assert [u["text_sha256"] for u in a] == [u["text_sha256"] for u in b], "seeded"
    assert a != c or len(units) <= k
    months_all = {u["month"] for u in units}
    months_picked = {u["month"] for u in a}
    assert len(months_picked) >= min(len(months_all), 3), months_picked
    assert l2.stratified_pick(units, 0, seed=1) == units
    assert l2.stratified_pick(units, 10_000, seed=1) == units


def test_the_panel_run_writes_panel_files_and_resumes_from_them(wired, panel):
    out = l2.L2_typed_events(complete=_reader(), probe=lambda b: None, kappa_rows=0,
                             source="panel", panel_path=panel, workers=3)
    assert out["status"] == "done"
    assert out["source"] == "panel"
    files = sorted(p.name for p in wired["typed"].glob("panel_*.jsonl"))
    assert files and all(n.startswith("panel_") for n in files)
    rows = _typed_on_disk(wired["typed"], panel=True)
    assert len(rows) == out["results"]["rows_typed"]
    assert all(r["source"] == l2.PANEL_SOURCE and r["source_kind"] == "panel"
               for r in rows)
    assert all(r["text_sha256"] and r["panel_cells"] for r in rows)
    assert out["corpus"]["distinct_texts"] == len(rows)
    assert (wired["typed"] / "_cursor_panel.json").exists()

    # the resume reads the ROWS, not a watermark
    again = l2.L2_typed_events(complete=_reader(), probe=lambda b: None,
                               kappa_rows=0, source="panel", panel_path=panel)
    assert again["status"] == "done"
    assert "NOTHING TO DO" in again["verdict"]
    assert len(_typed_on_disk(wired["typed"], panel=True)) == len(rows)


def test_a_stratified_panel_run_resumes_without_skipping_the_gaps(wired, panel):
    """A watermark over a total order would mark everything before the last
    sampled text done. The resume is the set of hashes actually written."""
    first = l2.L2_typed_events(complete=_reader(), probe=lambda b: None, kappa_rows=0,
                               source="panel", panel_path=panel, stratified=5, seed=3)
    assert first["results"]["rows_typed"] == 5
    total = first["corpus"]["distinct_texts"]
    second = l2.L2_typed_events(complete=_reader(), probe=lambda b: None, kappa_rows=0,
                                source="panel", panel_path=panel)
    assert second["results"]["rows_typed"] == total - 5
    assert len(l2.panel_typed_hashes(wired["typed"])) == total


# ------------------------------------------------------- the join, in E1's head

def _cells(pairs):
    import pandas as pd
    return pd.DataFrame([{"symbol": s, "entry_date": d, "text": "x"} for s, d in pairs])


def test_event_head_fans_a_panel_row_out_to_every_cell_that_carries_it(tmp_path):
    import learner.event_head as eh
    d = tmp_path / "typed_events"
    d.mkdir()
    row = {"source": l2.PANEL_SOURCE, "source_kind": "panel",
           "text_sha256": "h1", "scope": "AAA", "document_date": "2025-01-10",
           "panel_cells": [["AAA", "2025-01-13"], ["BBB", "2025-01-13"],
                           ["ZZZ", "2025-01-13"]],
           "event_type": "product_recall", "direction": -1,
           "magnitude_bucket": "LARGE", "confidence": 0.8}
    (d / "panel_2026-09-13.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    ev, meta = eh.typed_events(_cells([("AAA", "2025-01-13"), ("BBB", "2025-01-13")]),
                               directory=d)
    assert len(ev) == 2
    assert set(ev["symbol"]) == {"AAA", "BBB"}
    assert set(ev["entry_date"]) == {"2025-01-13"}
    assert meta["fanned_beyond_scope"] == 1                 # BBB is not the scope
    assert meta["dropped_panel_cell_not_in_this_slice"] == 1   # ZZZ is not in the panel
    assert meta["n_typed_rows_from_panel"] == 1
    assert meta["event_source"] == eh.TYPED_L2


def test_event_head_uses_the_panels_own_entry_date_not_the_strictly_after_rule(tmp_path):
    """A pre-bell headline belongs to the SAME session, and the panel already
    said so. Re-deriving it with the corpus rule would put it one session late."""
    import learner.event_head as eh
    d = tmp_path / "typed_events"
    d.mkdir()
    panel_row = {"source_kind": "panel", "text_sha256": "h1", "scope": "AAA",
                 "document_date": "2025-01-13", "panel_cells": [["AAA", "2025-01-13"]],
                 "event_type": "guidance_change", "direction": 1,
                 "magnitude_bucket": "SMALL", "confidence": 0.7}
    (d / "panel_2026-09-13.jsonl").write_text(json.dumps(panel_row) + "\n",
                                              encoding="utf-8")
    ev, _ = eh.typed_events(_cells([("AAA", "2025-01-13"), ("AAA", "2025-01-14")]),
                            directory=d)
    assert list(ev["entry_date"]) == ["2025-01-13"]

    # the CORPUS rule on the same date lands one session later, as it always has
    corpus_row = dict(panel_row, source_kind="corpus", panel_cells=[],
                      source="alpaca_benzinga_news", raw_id="1")
    (d / "panel_2026-09-13.jsonl").unlink()
    (d / "2026-09-13.jsonl").write_text(json.dumps(corpus_row) + "\n", encoding="utf-8")
    ev2, _ = eh.typed_events(_cells([("AAA", "2025-01-13"), ("AAA", "2025-01-14")]),
                             directory=d)
    assert list(ev2["entry_date"]) == ["2025-01-14"]


def test_a_text_in_both_sources_is_one_event_for_a_cell(tmp_path):
    import learner.event_head as eh
    d = tmp_path / "typed_events"
    d.mkdir()
    panel_row = {"source_kind": "panel", "text_sha256": "same", "scope": "AAA",
                 "document_date": "2025-01-13", "panel_cells": [["AAA", "2025-01-14"]],
                 "event_type": "stock_buyback", "direction": 1,
                 "magnitude_bucket": "SMALL", "confidence": 0.9}
    corpus_row = {"source_kind": "corpus", "source": "alpaca_benzinga_news",
                  "raw_id": "7", "text_sha256": "same", "scope": "AAA",
                  "document_date": "2025-01-13", "event_type": "stock_buyback",
                  "direction": 1, "magnitude_bucket": "SMALL", "confidence": 0.9}
    (d / "panel_2026-09-13.jsonl").write_text(json.dumps(panel_row) + "\n",
                                              encoding="utf-8")
    (d / "2026-09-13.jsonl").write_text(json.dumps(corpus_row) + "\n", encoding="utf-8")
    ev, meta = eh.typed_events(_cells([("AAA", "2025-01-13"), ("AAA", "2025-01-14")]),
                               directory=d)
    assert len(ev) == 1, "the corpus row repeats the panel row's text on the same cell"
    assert meta["dropped_duplicate_text_on_the_same_cell"] == 1
    assert meta["n_typed_rows_from_panel"] == 1 and meta["n_typed_rows_from_corpus"] == 1


# =============================================================== T3: the dry run

def test_a_dry_run_calls_nothing_and_prices_both_tables(wired, panel):
    reader = _reader()
    out = l2.L2_typed_events(complete=reader, probe=lambda b: None, source="panel",
                             panel_path=panel, workers=8, max_usd=8.0, dry_run=True)
    assert out["status"] == "DRY_RUN"
    assert reader.box["calls"] == 0, "a dry run must not call the model"
    assert not list(wired["typed"].glob("*.jsonl"))
    est = out["estimate"]
    assert est["no_model_was_called"] is True
    assert est["rows_to_type"] == est["unique_texts"] > 0
    assert est["panel_rows_covered"] == 25
    assert est["tokens"]["system_prompt_tokens"] > 0
    flash = est["cost"]["published_deepseek_list"]["deepseek-v4-flash_offpeak"]
    assert flash["input_cache_miss_per_mtok"] == 0.15
    assert flash["input_cache_hit_per_mtok"] == 0.003
    assert flash["usd_with_prefix_cache"] < flash["usd_no_prefix_cache"]
    assert est["cost"]["repo_derived_rates"]["deepseek-chat"]["output_per_mtok"] > 0
    assert est["cost"]["measured_usd_per_row"] == l2.MEASURED["usd_per_row"]
    eight = est["wall_time"]["ledger_measured_57p4_per_min"]
    one = est["rows_to_type"] / l2.MEASURED["rows_per_min_serial"] / 60.0
    assert eight["workers"] == 8
    assert eight["hours"] == pytest.approx(one / 8, abs=0.01)
    assert est["cap"]["max_usd"] == 8.0 and est["cap"]["binds"] is False


def test_the_dry_run_says_when_the_cap_binds(wired, panel):
    out = l2.L2_typed_events(complete=_reader(), probe=lambda b: None, source="panel",
                             panel_path=panel, max_usd=0.000001, dry_run=True)
    assert out["estimate"]["cap"]["binds"] is True
    assert "the cap STOPS it early" in out["estimate"]["cap"]["note"]


def test_an_unknown_source_is_a_refusal():
    with pytest.raises(ValueError) as exc:
        l2.L2_typed_events(source="whatever", complete=_reader(), probe=lambda b: None)
    assert "--source must be one of" in str(exc.value)
