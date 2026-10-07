"""Q12 (2026-10-07): the research-intake "academic" lane.

Offline: every HTTP call is a fake (two real, saved OpenAlex/CrossRef
responses for the Lou-Polk-Skouras query, fetched once live and frozen as
fixtures); the suite blocks sockets anyway. Covers normalisation, the
keyless-refusal guard (Semantic Scholar / arXiv), the lane's own per-day cap,
novelty detection against a card's existing citations, and the named zeros.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend import config as _config
from backend.services import research_instruments as RI

FIX = Path(__file__).parent / "fixtures" / "research_instruments"
OPENALEX_RAW = json.loads((FIX / "openalex_lou_polk_skouras.json").read_text(encoding="utf-8"))
CROSSREF_RAW = json.loads((FIX / "crossref_lou_polk_skouras.json").read_text(encoding="utf-8"))

CARD_TEXT = """# CARD: test-card

## Citation
A. Author, B. Author (2019), "A Tug of War: Overnight versus Intraday
Expected Returns," Journal of Financial Economics, 134(1): 192-213. DOI
10.1016/j.jfineco.2019.03.011.

## The claim, in one sentence
test claim.

## Needs evidence
- Post-2019 citing literature on the tug-of-war mechanism.
- A second open question about cross-sectional ranking.

## Verdict
**READY_TO_CELL** for testing.
"""

CLOSED_CARD_TEXT = """# CARD: closed-card

## Citation
X. Writer (2020), "Something Else," Journal of Nothing, 1(1): 1-2.

## Needs evidence
- An open thread kept only for a future resurrection.

## Verdict
**ALREADY_CLOSED.** Nothing to do here.
"""


# ════════════════════════════════ normalisation ══════════════════════════════

def test_normalize_openalex_finds_the_primary_paper_with_its_fields():
    rows = RI.normalize_openalex(OPENALEX_RAW, fetched_utc="2026-10-07T00:00:00+00:00")
    assert rows, "the real fixture must yield at least one row"
    primary = rows[0]
    assert primary["doi"] == "10.1016/j.jfineco.2019.03.011"
    assert "tug of war" in primary["title"].lower()
    assert primary["year"] == 2019
    assert "Dong Lou" in primary["authors"]
    assert primary["venue"] == "Journal of Financial Economics"
    assert isinstance(primary["cited_by_count"], int) and primary["cited_by_count"] > 0
    assert primary["source"] == "openalex"
    assert primary["fetched_utc"] == "2026-10-07T00:00:00+00:00"


def test_normalize_crossref_finds_the_primary_paper_with_its_fields():
    rows = RI.normalize_crossref(CROSSREF_RAW, fetched_utc="2026-10-07T00:00:00+00:00")
    assert rows
    primary = rows[0]
    assert primary["doi"] == "10.1016/j.jfineco.2019.03.011"
    assert "tug of war" in primary["title"].lower()
    assert primary["year"] == 2019
    assert "Dong Lou" in primary["authors"]
    assert isinstance(primary["cited_by_count"], int) and primary["cited_by_count"] > 0
    assert primary["source"] == "crossref"


def test_normalize_nber_rss_splits_authors_from_title():
    xml = (b'<?xml version="1.0"?><rss><channel>'
          b'<item><title>Jane Q. Economist, Bob R. Scholar: A Fine Paper About Returns</title>'
          b'<link>https://www.nber.org/papers/w00001</link>'
          b'<description>An abstract.</description></item>'
          b'</channel></rss>')
    rows = RI.normalize_nber_rss(xml, fetched_utc="t")
    assert len(rows) == 1
    assert rows[0]["title"] == "A Fine Paper About Returns"
    assert rows[0]["authors"] == ["Jane Q. Economist", "Bob R. Scholar"]
    assert rows[0]["venue"] == "NBER Working Paper"
    assert rows[0]["doi"] is None
    assert rows[0]["source"] == "nber_rss"


def test_normalize_arxiv_atom_feed():
    xml = (b'<feed xmlns="http://www.w3.org/2005/Atom">'
          b'<entry><title>A Preprint Title</title>'
          b'<author><name>Alice Example</name></author>'
          b'<published>2025-03-01T00:00:00Z</published>'
          b'<id>http://arxiv.org/abs/2503.00001</id>'
          b'<link rel="alternate" type="text/html" href="http://arxiv.org/abs/2503.00001"/>'
          b'<summary>A summary.</summary></entry></feed>')
    rows = RI.normalize_arxiv(xml, fetched_utc="t")
    assert len(rows) == 1
    assert rows[0]["title"] == "A Preprint Title"
    assert rows[0]["year"] == 2025
    assert rows[0]["source"] == "arxiv"
    assert rows[0]["doi"] is None


# ═══════════════════════════ the keyless-refusal guard ═══════════════════════

def test_semantic_scholar_refuses_without_a_declared_key(monkeypatch):
    monkeypatch.setattr(_config, "RESEARCH_INSTRUMENTS_SEMANTIC_SCHOLAR_KEY", None, raising=False)
    with pytest.raises(RI.InstrumentKeyRequired):
        RI.fetch_semantic_scholar("some query")


def test_semantic_scholar_runs_once_a_key_is_declared(monkeypatch):
    calls = []

    def fake_get(url):
        calls.append(url)
        return b'{"data": []}'
    r = RI.fetch_semantic_scholar("some query", key="k123", http_get=fake_get)
    assert r["status"] == "OK"
    assert calls, "a declared key must actually issue the call"


def test_arxiv_refuses_unless_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(_config, "RESEARCH_INSTRUMENTS_ARXIV_ENABLED", False, raising=False)
    with pytest.raises(RI.InstrumentKeyRequired):
        RI.fetch_arxiv("some query")


def test_arxiv_runs_once_enabled(monkeypatch):
    monkeypatch.setattr(_config, "RESEARCH_INSTRUMENTS_ARXIV_ENABLED", True, raising=False)
    r = RI.fetch_arxiv("some query", http_get=lambda u: (
        b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>'))
    assert r["status"] == "OK"


def test_try_instrument_never_raises_and_names_the_zero():
    r = RI._try_instrument("semantic_scholar", "q", http_get=None)
    assert r["status"] == "REFUSED"
    assert r["zero_kind"] == "KEY_REQUIRED_OR_RATE_LIMITED"
    assert r["rows"] == []


# ═══════════════════════════════ novelty detection ════════════════════════════

def test_novelty_true_for_a_paper_not_in_the_seed_set_false_for_the_seed_itself():
    seeds = RI.card_seed_citations(CARD_TEXT)
    assert seeds and seeds[0]["doi"] == "10.1016/j.jfineco.2019.03.011"
    rows = RI.normalize_openalex(OPENALEX_RAW, fetched_utc="t")
    primary = next(r for r in rows if r["doi"] == "10.1016/j.jfineco.2019.03.011")
    assert RI.is_novel(primary, seeds) is False
    others = [r for r in rows if r["doi"] != "10.1016/j.jfineco.2019.03.011"]
    assert others, "the fixture must carry at least one non-primary result"
    assert any(RI.is_novel(r, seeds) for r in others)


def test_verified_doi_flag():
    assert RI.verified_doi({"doi": "10.1/x"}) is True
    assert RI.verified_doi({"doi": None}) is False
    assert RI.verified_doi({}) is False


# ═══════════════════════════════ card parsing ════════════════════════════════

def test_card_qualifies_and_needs_evidence_round_trip():
    assert RI.card_verdicts(CARD_TEXT) == ["READY_TO_CELL"]
    assert RI.card_qualifies(CARD_TEXT) is True
    qs = RI.card_needs_evidence(CARD_TEXT)
    assert qs == ["Post-2019 citing literature on the tug-of-war mechanism.",
                 "A second open question about cross-sectional ranking."]


def test_a_card_with_only_already_closed_does_not_qualify():
    assert RI.card_verdicts(CLOSED_CARD_TEXT) == ["ALREADY_CLOSED"]
    assert RI.card_qualifies(CLOSED_CARD_TEXT) is False


def test_classify_topic_class():
    assert RI.classify_topic_class("post-2010 evidence for the Monday effect") == \
        "classical_asset_pricing"
    assert RI.classify_topic_class("a transformer-based LLM forecasting model") == \
        "quant_ml_preprint"


# ═══════════════════════════════ probe_card: the lane ════════════════════════

def _fake_http(url: str) -> bytes:
    if "openalex.org" in url:
        return json.dumps(OPENALEX_RAW).encode()
    if "crossref.org" in url:
        return json.dumps(CROSSREF_RAW).encode()
    raise AssertionError(f"unexpected default-tier fetch: {url}")


def _write_card(tmp_path: Path, slug: str, text: str) -> Path:
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    (cards_dir / f"{slug}.md").write_text(text, encoding="utf-8")
    return cards_dir


def test_probe_card_writes_evidence_and_a_named_zero_free_receipt(tmp_path):
    cards_dir = _write_card(tmp_path, "test-card", CARD_TEXT)
    evidence_dir = tmp_path / "evidence"
    opt = tmp_path / "optimus"
    rec = RI.probe_card("test-card", cards_dir=cards_dir, evidence_dir=evidence_dir, opt=opt,
                        http_get=_fake_http, run_id="r1")
    assert rec["status"] == "OK"
    assert rec["zero_kind"] == "YIELDING"
    assert rec["queries_issued"] > 0
    assert Path(rec["path"]).exists()
    assert Path(rec["evidence_path"]).exists()
    ev = json.loads(Path(rec["evidence_path"]).read_text(encoding="utf-8"))
    assert ev["citations"], "the primary paper must appear in the evidence file"
    primary_rows = [c for c in ev["citations"] if c.get("doi") == "10.1016/j.jfineco.2019.03.011"]
    assert primary_rows and all(c["verified_doi"] and not c["novel"] for c in primary_rows)
    novel_rows = [c for c in ev["citations"] if c.get("novel")]
    assert novel_rows, "the fixtures carry at least one paper outside the seed set"
    # the day's ledger now carries these queries
    ledger = RI._read_jsonl(RI.academic_ledger_path(opt))
    assert len(ledger) == rec["queries_issued"]


def test_probe_card_refuses_a_card_with_no_qualifying_verdict(tmp_path):
    cards_dir = _write_card(tmp_path, "closed-card", CLOSED_CARD_TEXT)
    rec = RI.probe_card("closed-card", cards_dir=cards_dir, evidence_dir=tmp_path / "evidence",
                        opt=tmp_path / "optimus", http_get=_fake_http, run_id="r2")
    assert rec["status"] == "REFUSED"
    assert "NOT_A_QUALIFYING_VERDICT" in rec["refusal"]


def test_probe_card_refuses_an_unknown_card(tmp_path):
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    rec = RI.probe_card("does-not-exist", cards_dir=cards_dir, evidence_dir=tmp_path / "evidence",
                        opt=tmp_path / "optimus", http_get=_fake_http, run_id="r3")
    assert rec["status"] == "REFUSED"
    assert "card not found" in rec["refusal"]


# ═══════════════════════════════ the lane's day cap ══════════════════════════

def test_the_day_cap_stops_new_queries_once_reached(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "QUERY_PLANNER_ACADEMIC_QUERIES_DAY", 1, raising=False)
    cards_dir = _write_card(tmp_path, "test-card", CARD_TEXT)
    opt = tmp_path / "optimus"
    calls = {"n": 0}

    def counting_http(url):
        calls["n"] += 1
        return _fake_http(url)

    rec = RI.probe_card("test-card", cards_dir=cards_dir, evidence_dir=tmp_path / "evidence",
                       opt=opt, http_get=counting_http, run_id="r4")
    assert rec["status"] == "OK"
    # the cap is 1 query/day: only the FIRST instrument of the FIRST question
    # may actually call out; everything after must be refused with the named
    # zero DAY_CAP_REACHED, never a second real HTTP call
    assert calls["n"] == 1
    zero_kinds = {a.get("zero_kind") for q in rec["questions_run"] for a in q["attempts"]}
    assert "DAY_CAP_REACHED" in zero_kinds


def test_day_cap_counts_queries_already_issued_today_by_an_earlier_run(tmp_path):
    cards_dir = _write_card(tmp_path, "test-card", CARD_TEXT)
    opt = tmp_path / "optimus"
    # pre-seed today's ledger with QUERY_PLANNER_ACADEMIC_QUERIES_DAY (12, the
    # default) rows so a fresh probe_card call starts with budget_left == 0
    import datetime as _dt
    today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    rows = [{"t": f"{today}T00:00:0{i}+00:00", "run_id": "earlier", "card_slug": "other",
            "instrument": "openalex", "query_text": "x", "status": "OK"} for i in range(12)]
    RI._append_jsonl(RI.academic_ledger_path(opt), rows)

    def must_not_be_called(url):
        raise AssertionError("budget_left should already be 0 -- no HTTP call expected")

    rec = RI.probe_card("test-card", cards_dir=cards_dir, evidence_dir=tmp_path / "evidence",
                       opt=opt, http_get=must_not_be_called, run_id="r5")
    assert rec["status"] == "OK"
    assert rec["queries_issued"] == 0
    assert all(a.get("zero_kind") == "DAY_CAP_REACHED"
              for q in rec["questions_run"] for a in q["attempts"])


# ═══════════════════════════════ named zeros, end to end ═════════════════════

def test_named_zero_when_every_instrument_returns_nothing(tmp_path):
    cards_dir = _write_card(tmp_path, "test-card", CARD_TEXT)

    def empty_http(url):
        if "openalex" in url:
            return b'{"results": []}'
        if "crossref" in url:
            return b'{"message": {"items": []}}'
        raise AssertionError(url)

    rec = RI.probe_card("test-card", cards_dir=cards_dir, evidence_dir=tmp_path / "evidence",
                       opt=tmp_path / "optimus", http_get=empty_http, run_id="r6")
    assert rec["status"] == "OK"
    assert rec["zero_kind"] == "ALL_INSTRUMENTS_QUERIES_RAN_NO_CITATIONS"


def test_probe_card_reports_no_needs_evidence_as_its_own_named_zero(tmp_path):
    no_ne_card = CARD_TEXT.split("## Needs evidence")[0] + "## Verdict\n**READY_TO_CELL**.\n"
    cards_dir = _write_card(tmp_path, "no-ne", no_ne_card)
    rec = RI.probe_card("no-ne", cards_dir=cards_dir, evidence_dir=tmp_path / "evidence",
                       opt=tmp_path / "optimus", http_get=_fake_http, run_id="r7")
    assert rec["status"] == "OK"
    assert rec["zero_kind"] == "NO_NEEDS_EVIDENCE_DECLARED"
    assert rec["queries_issued"] == 0
