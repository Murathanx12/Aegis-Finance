"""Offline budget-refusal sidecar: bounded source samples, zero paid paths."""
from datetime import datetime, timezone
import json
from pathlib import Path
import socket

import pytest

from backend.services import provisional_event_review as P, world_digest as WD
from scripts import world_digest as S
from scripts import world_digest_provisional as PS


def _row(path: Path, *, title: str, seen: str, published: str,
         url: str, body: str, tickers=()):
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(source=path.parent.name, title=title, body=body, url=url,
                  first_seen_utc=seen, published_utc=published, tickers=list(tickers),
                  entity_tags=[f"resolved:{ticker}=name" for ticker in tickers])
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")


@pytest.fixture
def sealed(monkeypatch, tmp_path):
    from backend.services import belief_state as B, llm_analyzer, provider_budget as PB

    def forbidden(*_args, **_kwargs):
        pytest.fail("paid, network, forecast, broker or owner path reached")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(S, "_ensure_streams", lambda: None)
    monkeypatch.setattr(S, "_host_budget_required", lambda: True)
    monkeypatch.setattr(S, "_shared_budget_refusal", lambda: "SHARED_ENVELOPE_UNAVAILABLE")
    monkeypatch.setattr(S.WD, "optimus", lambda: tmp_path)
    monkeypatch.setattr(S.WD, "work_dir", lambda: tmp_path / "digest_work")
    monkeypatch.setattr(S.WD, "stop_file", lambda: tmp_path / "digest_work" / "STOP")
    for obj, name in [(S, "_balance"), (S.WD, "Meter"), (S.WD, "collect"),
                      (B, "append"), (llm_analyzer, "call_named"),
                      (PB, "reserve"), (PB, "settle"), (PB, "initialize")]:
        monkeypatch.setattr(obj, name, forbidden)
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 3, 21, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(S, "datetime", Frozen)
    return tmp_path


def test_refusal_keeps_exit_and_receipt_with_pre_election_cutoff(sealed):
    root = sealed
    base = root / "news_corpus/dj_reader_barrons"
    body = "Data center projects face election ballot permitting questions. " * 12
    _row(base / "2026-11-02.jsonl", title="Data center projects on the ballot",
         seen="2026-11-02T23:35:59+00:00", published="2026-11-02T21:49:00+00:00",
         url="https://example.test/ballot-a", body=body)
    _row(base / "2026-11-03.jsonl", title="Data center election project risk",
         seen="2026-11-03T17:53:12+00:00", published="2026-11-03T12:34:00+00:00",
         url="https://example.test/ballot-b", body=body)
    _row(base / "2026-11-04.jsonl", title="Later election result for data centers",
         seen="2026-11-04T01:00:00+00:00", published="2026-11-04T00:50:00+00:00",
         url="https://example.test/ballot-future", body=body)
    _row(base / "2026-11-03.jsonl", title="Premature publication on ballot risk",
         seen="2026-11-03T18:00:00+00:00", published="2026-11-04T00:50:00+00:00",
         url="https://example.test/ballot-premature", body=body)

    assert S.main(["--hours", "36"]) == 2
    directory = root / "digest_work/receipts"
    budget, = directory.glob("budget_refused_*.json")
    sidecar, = directory.glob("provisional_review_*.json")
    assert json.loads(budget.read_text())["state"] == "BUDGET_REFUSED"
    receipt = json.loads(sidecar.read_text())
    assert receipt["upstream_digest"]["state"] == "BUDGET_REFUSED"
    assert receipt["upstream_digest"]["exit_code"] == 2
    assert datetime.fromisoformat(receipt["source_cutoff_utc"].replace("Z", "+00:00")) == datetime(
        2026, 11, 3, 21, tzinfo=timezone.utc)
    assert receipt["coverage"]["status"] == "PARTIAL"
    assert receipt["holdings"]["status"] == "UNKNOWN"
    assert receipt["component_only"] is True and receipt["natural_warning"] is False
    assert receipt["authority"] == {"forecast_writes": 0, "portfolio_action": "NONE",
                                    "delivery": "NOT_ATTEMPTED", "provider_calls": 0}
    assert len(receipt["groups"]) == 2
    assert len({group["event_key"] for group in receipt["groups"]}) == 2
    assert all(len(group["sources"]) == 1 and group["edges"] == []
               for group in receipt["groups"])
    assert set(receipt["uncertainty"].values()) == {"UNKNOWN"}
    assert "ballot-future" not in sidecar.read_text()
    assert body not in sidecar.read_text()


def test_ticker_tags_and_sidebar_cannot_create_direct_held_identity(sealed):
    root = sealed
    _row(root / "news_corpus/google_news_rss_en_gb/2026-11-01.jsonl",
         title="Binance hack reported - Example News", seen="2026-11-01T04:39:46+00:00",
         published="2026-11-01T02:41:00+00:00", url="https://example.test/binance",
         body="Short feed description.", tickers=["TGT"])
    folder = root / "news_corpus/dowjones/marketwatch/2026-11-04"
    folder.mkdir(parents=True)
    qcom = dict(title="Qualcomm's stock falls as sales pressure mounts",
                text="Qualcomm reports sales. Apple appears in the sidebar. " * 12,
                url="https://example.test/qcom", first_seen_utc="2026-11-04T22:41:00+00:00",
                published_utc="2026-11-04T22:03:00+00:00", tickers_named=["AAPL"],
                page_kind="article", publisher="marketwatch")
    (folder / "qcom.json").write_text(json.dumps(qcom), encoding="utf-8")
    for cutoff in (datetime(2026, 11, 1, 5, tzinfo=timezone.utc),
                   datetime(2026, 11, 5, 5, tzinfo=timezone.utc)):
        sources, _ = PS.build_sample(root=root, review_time=cutoff, cutoff=cutoff, hours=36)
        assert len(sources) == 1
        receipt = P.build_review(
            sources=sources, issuer_edges=[], holdings=None,
            review_time_utc=cutoff.isoformat(), source_cutoff_utc=cutoff.isoformat(),
            input_complete=False, upstream_state="BUDGET_REFUSED", upstream_exit_code=2)
        assert receipt["groups"][0]["edges"] == []
        assert receipt["holdings"]["status"] == "UNKNOWN"
        assert receipt["decision"] == "NO_CHANGE_WITH_REASON"
    item = WD.Item("qcom", "article", "marketwatch", qcom["url"], qcom["title"],
                   qcom["text"], qcom["first_seen_utc"], qcom["published_utc"], ["AAPL"])
    raw = dict(event_type="earnings", novelty="new_fact", tickers=["QCOM", "AAPL"],
               forward_claims=[])
    assert WD.type_row(raw, item)["tickers"] == ["QCOM"]
    assert WD.type_row(raw, item)["tickers_unverified"] == ["AAPL"]


def test_tagless_wsj_projection_is_sampled_without_issuer_edge(sealed):
    root = sealed
    _row(root / "news_corpus/dj_reader_wsj/2026-11-05.jsonl",
         title="Meta interview on quarterly investment plans",
         seen="2026-11-05T06:29:55+00:00", published="2026-11-05T03:11:00+00:00",
         url="https://example.test/wsj-meta", body="Interview text. " * 35)
    cutoff = datetime(2026, 11, 5, 6, 35, tzinfo=timezone.utc)
    sources, status = PS.build_sample(root=root, review_time=cutoff, cutoff=cutoff, hours=36)
    assert status == "PARTIAL_ALLOWLIST" and len(sources) == 1
    receipt = P.build_review(sources=sources, issuer_edges=[], holdings=None,
                             review_time_utc=cutoff.isoformat(), source_cutoff_utc=cutoff.isoformat(),
                             input_complete=False, upstream_state="BUDGET_REFUSED", upstream_exit_code=2)
    assert receipt["groups"][0]["edges"] == []
    assert receipt["holdings"]["status"] == "UNKNOWN"


def test_malformed_publication_clock_is_not_silently_treated_as_undated(sealed):
    root = sealed
    _row(root / "news_corpus/dj_reader_barrons/2026-11-03.jsonl",
         title="Data center ballot source with bad clock",
         seen="2026-11-03T17:53:12+00:00", published="not-a-clock",
         url="https://example.test/invalid-publication", body="Synthetic body. " * 35)
    cutoff = datetime(2026, 11, 3, 21, tzinfo=timezone.utc)
    sources, status = PS.build_sample(root=root, review_time=cutoff, cutoff=cutoff, hours=36)
    assert sources == [] and status == "PARTIAL_ALLOWLIST"


def test_recurring_analyst_estimates_page_is_reference_only(sealed):
    root = sealed
    _row(root / "news_corpus/dj_reader_marketwatch/2026-11-05.jsonl",
         title="Example Company Analyst Estimates page",
         seen="2026-11-05T04:00:00+00:00", published="2026-11-05T03:00:00+00:00",
         url="https://example.test/estimates", body="Recurring estimates page. " * 30,
         tickers=["TGT"])
    cutoff = datetime(2026, 11, 5, 5, tzinfo=timezone.utc)
    sources, _ = PS.build_sample(root=root, review_time=cutoff, cutoff=cutoff, hours=36)
    assert len(sources) == 1 and sources[0].kind == "REFERENCE_PAGE"
    receipt = P.build_review(sources=sources, issuer_edges=[], holdings=None,
                             review_time_utc=cutoff.isoformat(), source_cutoff_utc=cutoff.isoformat(),
                             input_complete=False, upstream_state="BUDGET_REFUSED", upstream_exit_code=2)
    assert receipt["groups"][0]["reason_codes"] == ["REFERENCE_ONLY"]
    assert receipt["groups"][0]["edges"] == []


def test_oversized_source_refuses_without_collection_or_sidecar(sealed):
    root = sealed
    path = root / "news_corpus/dj_reader_barrons/2026-11-03.jsonl"
    path.parent.mkdir(parents=True)
    with path.open("wb") as stream:
        stream.truncate(PS.MAX_FILE_BYTES + 1)
    assert S.main([]) == 2
    directory = root / "digest_work/receipts"
    assert len(list(directory.glob("budget_refused_*.json"))) == 1
    assert list(directory.glob("provisional_review_*.json")) == []


def test_budget_receipt_failure_cannot_orphan_a_component(sealed, monkeypatch):
    def failed_receipt(_reason):
        raise OSError("private path unavailable")

    def forbidden_sidecar(**_kwargs):
        pytest.fail("sidecar must wait for original budget receipt")

    monkeypatch.setattr(S, "_budget_failure_receipt", failed_receipt)
    monkeypatch.setattr(PS, "write_budget_sidecar", forbidden_sidecar)
    assert S.main([]) == 2
    assert list((sealed / "digest_work").glob("receipts/provisional_review_*.json")) == []


def test_explicit_opt_out_keeps_original_refusal_only(sealed, monkeypatch):
    def forbidden_sidecar(**_kwargs):
        pytest.fail("opt-out must skip sidecar")

    monkeypatch.setattr(PS, "write_budget_sidecar", forbidden_sidecar)
    assert S.main(["--no-provisional-review"]) == 2
    directory = sealed / "digest_work/receipts"
    assert len(list(directory.glob("budget_refused_*.json"))) == 1
    assert list(directory.glob("provisional_review_*.json")) == []


def test_1742_rows_stop_at_small_cap_and_mark_partial(sealed):
    root = sealed
    path = root / "news_corpus/dj_reader_barrons/2026-11-03.jsonl"
    for number in range(1742):
        _row(path, title=f"Synthetic event {number} reported", seen="2026-11-03T17:53:12+00:00",
             published="2026-11-03T12:34:00+00:00", url=f"https://example.test/{number}",
             body="Short synthetic source.")
    sources, status = PS.build_sample(root=root, review_time=datetime(2026, 11, 3, 21, tzinfo=timezone.utc),
                                      cutoff=datetime(2026, 11, 3, 21, tzinfo=timezone.utc), hours=36)
    assert status == "PARTIAL_CAP" and len(sources) == PS.MAX_SOURCES


def test_binance_context_row_survives_selection_cap_without_identity_edge(sealed):
    root = sealed
    article = root / "news_corpus/dj_reader_barrons/2026-11-01.jsonl"
    for number in range(80):
        _row(article, title=f"Synthetic unrelated report {number}",
             seen="2026-11-01T03:00:00+00:00", published="2026-11-01T02:00:00+00:00",
             url=f"https://example.test/unrelated-{number}", body="Article body. " * 35)
    tagged = root / "news_corpus/google_news_rss_en_gb/2026-11-01.jsonl"
    _row(tagged, title="Binance hack reported - Example News",
         seen="2026-11-01T04:39:46+00:00", published="2026-11-01T02:41:00+00:00",
         url="https://example.test/binance", body="Feed description.", tickers=["TGT"])
    cutoff = datetime(2026, 11, 1, 5, tzinfo=timezone.utc)
    sources, status = PS.build_sample(root=root, review_time=cutoff, cutoff=cutoff, hours=36)
    assert status == "PARTIAL_CAP" and len(sources) == PS.MAX_SOURCES
    assert any(source.kind == "REFERENCE_PAGE" and b'"TGT"' in source.payload
               for source in sources)
