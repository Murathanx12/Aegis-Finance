"""web_events: the generic `claim` type and the optional `source_id` field
(adjudication 2026-09-26 row 9). F's thesis cards wrote 26 dated claims and
20 of them lived only in the claims ledger because no web_events type fit."""

from __future__ import annotations

import json

import pytest

from backend.services import web_events as WE

_OLD_TYPES = {
    "filing_8k", "filing_10q", "filing_10k", "filing_form4", "filing_13d",
    "earnings_release", "guidance_change", "capacity_guidance", "product_launch",
    "contract_win", "customer_announcement", "supplier_constraint",
    "management_language_change", "analyst_revision", "regulatory_decision",
    "litigation", "index_change", "mna", "offering", "buyback", "dividend_change",
    "attention_spike", "forum_disagreement", "no_event_found", "contradiction"}


def _claim(**kw) -> dict:
    row = {"ticker": "MU", "source_type": "news", "event_type": "claim",
           "source_url": "https://www.trendforce.com/price/dram/dram_spot",
           "claim": "DDR5 spot up 4% w/w", "evidence_date": "2026-09-24",
           "observed_at": "2026-09-26T03:00:00+00:00",
           "source_id": "openclaw:trendforce.com"}
    row.update(kw)
    return row


def test_the_25_existing_types_are_unchanged_and_claim_is_added():
    assert _OLD_TYPES <= WE.EVENT_TYPES
    assert WE.EVENT_TYPES - _OLD_TYPES == {"claim"}


@pytest.mark.parametrize("st,url", [
    ("news", "https://www.trendforce.com/x"), ("sec", "https://www.sec.gov/Archives/x"),
    ("x", "https://x.com/MicronTech/status/1"), ("company_ir", "https://investors.micron.com/x"),
    ("reddit", "https://www.reddit.com/r/x"), ("internal", "https://aegis.local/x")])
def test_every_source_type_may_carry_a_generic_claim(st, url):
    out = WE.validate(_claim(source_type=st, source_url=url))
    assert out["event_type"] == "claim"


def test_source_id_is_kept_and_does_not_move_the_event_id():
    a = WE.validate(_claim())
    b = WE.validate(_claim(source_id="openclaw:someone_else"))
    assert a["source_id"] == "openclaw:trendforce.com"
    assert a["event_id"] == b["event_id"]           # a re-read by another source is the same event
    assert WE.validate(_claim(source_id=None))["source_id"] is None


def test_a_claim_still_refuses_what_every_row_refuses():
    with pytest.raises(WE.WebEventRefused, match="missing"):
        WE.validate(_claim(claim=""))
    with pytest.raises(WE.WebEventRefused, match="may not carry"):
        WE.validate(_claim(expected_return=0.1))
    with pytest.raises(WE.WebEventRefused, match="not an allowed URL"):
        WE.validate(_claim(source_type="sec", source_url="https://example.com/x"))


def test_old_rows_without_source_id_still_read(tmp_path, monkeypatch):
    monkeypatch.setattr(WE, "LEDGER_DIR", tmp_path)
    old = {"observed_at": "2026-09-22T01:00:00+00:00", "evidence_date": "2026-09-21",
           "ticker": "AAA", "entity": "", "source_type": "sec",
           "source_url": "https://www.sec.gov/x", "event_type": "filing_8k",
           "claim": "8-K", "direction_prior": None, "affected_entities": [],
           "horizon_prior": None, "confidence_source": "REGULATOR",
           "retrieved_by": "openclaw:x", "event_id": "abc"}
    (tmp_path / "events_2026-09-22.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")
    assert WE.read(day="2026-09-22")[0]["event_id"] == "abc"
    s = WE.summary("2026-09-22")
    assert s["n_events"] == 1
    res = WE.append([_claim(evidence_date="2026-09-21", observed_at="2026-09-22T02:00:00+00:00")],
                    day="2026-09-22")
    assert res["written"] == 1
    assert {e["event_type"] for e in WE.read(day="2026-09-22")} == {"filing_8k", "claim"}
