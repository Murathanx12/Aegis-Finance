"""Focused guards for the read-only original-evidence report."""
from __future__ import annotations

from datetime import date
import json

import pytest

from scripts.original_evidence_audit import (
    EvidenceRefused, Sources, common_window, forecast_census, main,
    verify_original_twin,
)


def _twin_inputs():
    freeze = "2026-09-25T05:54:13+00:00"
    parent = {"book_id": "cb8d492bb8bf9ade", "name": "revision_flow_v0",
              "frozen_utc": freeze, "asof": "2026-09-25",
              "model": "rule:revision_flow_v0",
              "positions": [{"ticker": "AAA", "weight": 1.0}]}
    twin = {"book_id": "e74c9063d451e316",
            "name": "revision_flow_v0_random_twin",
            "frozen_utc": freeze, "asof": "2026-09-25",
            "model": "rule:revision_flow_v0",
            "strategy": "CONTROL for revision_flow_v0; same pool seed 20260925",
            "positions": [{"ticker": "BBB", "weight": 1.0}]}
    contract = {"selection": {"book_id": parent["book_id"],
                              "book_frozen_utc": freeze,
                              "positions": parent["positions"]},
                "twin": {"book_id": twin["book_id"],
                         "weights": {"BBB": 1.0}}}
    rows = {name: {"inception": "2026-09-28", "last_mark": "2026-10-08",
                   "spy_same_window_pct": 0.726, "roi_pct": ret}
            for name, ret in (("revision_flow_v0", 6.969),
                              ("revision_flow_v0_random_twin", -1.177))}
    dna = {name: {"book_id": book_id, "sessions_graded": 9,
                  "category": "strategy", "twin_of": None}
           for name, book_id in (("revision_flow_v0", parent["book_id"]),
                                 ("revision_flow_v0_random_twin", twin["book_id"]))}
    return [parent, twin], contract, rows, dna


def test_original_twin_requires_ids_seed_epoch_and_matched_marks():
    books, contract, rows, dna = _twin_inputs()
    linked = verify_original_twin(books, contract, rows, dna)
    assert linked["same_mark_gap_pp"] == 8.146
    assert linked["published_dna_twin_of"] is None
    books[1]["frozen_utc"] = "2026-09-26T00:00:00+00:00"
    with pytest.raises(EvidenceRefused, match="epoch"):
        verify_original_twin(books, contract, rows, dna)
    books[1]["frozen_utc"] = books[0]["frozen_utc"]
    books[1]["strategy"] = "a different random_twin name"
    with pytest.raises(EvidenceRefused, match="seed"):
        verify_original_twin(books, contract, rows, dna)
    books[1]["strategy"] = "CONTROL for revision_flow_v0; seed 20260925"
    rows["revision_flow_v0_random_twin"]["last_mark"] = "2026-10-07"
    with pytest.raises(EvidenceRefused, match="last_mark"):
        verify_original_twin(books, contract, rows, dna)
    rows["revision_flow_v0_random_twin"]["last_mark"] = "2026-10-08"
    contract["twin"]["book_id"] = "wrong"
    with pytest.raises(EvidenceRefused, match="contract"):
        verify_original_twin(books, contract, rows, dna)


def test_jsonl_captures_complete_prefix_and_refuses_rewrite(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_bytes(b'{"n":1}\n{"n":2}\n')
    src = Sources(tmp_path)
    rows = src.jsonl("rows.jsonl")
    assert next(rows) == {"n": 1}
    with p.open("ab") as stream:
        stream.write(b'{"n":3}\n')
    assert list(rows) == [{"n": 2}]
    assert src.records["rows.jsonl"]["complete_prefix_bytes"] == len(
        b'{"n":1}\n{"n":2}\n')
    p.write_bytes(b'{"n":1}\n{"n":2}')
    with pytest.raises(EvidenceRefused, match="incomplete"):
        list(Sources(tmp_path).jsonl("rows.jsonl"))
    p.write_bytes(b'{"n":1}\n{"n":2}\n')
    rows = Sources(tmp_path).jsonl("rows.jsonl")
    assert next(rows) == {"n": 1}
    p.write_bytes(b'{"n":9}\n{"n":2}\n')
    with pytest.raises(EvidenceRefused, match="prefix changed"):
        list(rows)


@pytest.mark.parametrize("rel", ["llm_portfolio/books.jsonl", "sources/claims.jsonl"])
def test_repeated_source_read_refuses_append_and_keeps_first_provenance(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b'{"n":1}\n')
    src = Sources(tmp_path)
    assert list(src.jsonl(rel)) == [{"n": 1}]
    first = src.records[rel].copy()
    assert list(src.jsonl(rel)) == [{"n": 1}]
    assert src.records[rel] == first
    with p.open("ab") as stream:
        stream.write(b'{"n":2}\n')
    with pytest.raises(EvidenceRefused, match="changed between reads"):
        list(src.jsonl(rel))
    assert src.records[rel] == first


def test_repeated_json_read_refuses_change_and_keeps_first_provenance(tmp_path):
    p = tmp_path / "receipt.json"
    p.write_text('{"n":1}', encoding="utf-8")
    src = Sources(tmp_path)
    assert src.json("receipt.json") == {"n": 1}
    first = src.records["receipt.json"].copy()
    p.write_text('{"n":2}', encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="changed between reads"):
        src.json("receipt.json")
    assert src.records["receipt.json"] == first


def test_forecast_reproduction_and_resolution_buckets(tmp_path):
    from backend.services.source_registry import claim_rows

    claim = {"source_id": "wsj_heard_on_the_street", "source_kind": "journalist",
             "ticker": "PSNL", "claim_text": "Dated source direction",
             "claim_utc": "2026-09-26T19:50:06+00:00",
             "observed_utc": "2026-09-26T20:50:32+00:00",
             "direction": "up", "post_url": "https://example.invalid/source"}
    rows = claim_rows(claim["source_id"], claim["ticker"], claim["claim_text"],
                      claim["claim_utc"], direction=claim["direction"],
                      source_kind=claim["source_kind"], post_url=claim["post_url"],
                      made_at=claim["observed_utc"])
    assert [r["horizon_days"] for r in rows] == [1, 5, 20]
    for row in rows[:2]:
        row["outcome"] = 1
        row["resolved_at"] = "2026-10-02"
    (tmp_path / "predictions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / "claims.jsonl").write_text(
        json.dumps(claim) + "\n", encoding="utf-8")
    result, cases = forecast_census(Sources(tmp_path), "2026-09-26",
                                    date(2026, 10, 9))
    assert result["constructed"] == result["matched"] == 3
    assert result["ledger_scope"] == "pre-migration physical legacy prefix only"
    assert result["probability_semantics"] == "P(beats SPY), not P(absolute up)"
    assert result["by_horizon"]["20"]["buckets"] == {"not_yet_due": 1}
    assert len(cases["PSNL"]) == 3
    rows[0]["probability"] = 0.7
    (tmp_path / "predictions.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="reproduction mismatch"):
        forecast_census(Sources(tmp_path), "2026-09-26", date(2026, 10, 9))


@pytest.mark.parametrize("contents", [
    '{"schema":"forecast_ledger_migration/1","legacy_name":"predictions.jsonl"}',
    "{invalid marker",
])
def test_forecast_census_refuses_any_migration_marker_before_read(tmp_path, contents):
    from backend.services import forecast_ledger

    marker = forecast_ledger.marker_path(tmp_path / forecast_ledger.LEGACY_NAME)
    marker.parent.mkdir(parents=True)
    marker.write_text(contents, encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="migration marker present"):
        forecast_census(Sources(tmp_path), "2026-09-26", date(2026, 10, 9))


def test_forecast_reproduction_requires_exact_unique_ids(tmp_path):
    from backend.services.source_registry import claim_rows

    common = {"source_id": "wsj_heard_on_the_street", "source_kind": "journalist",
              "ticker": "AAA", "claim_utc": "2026-09-26T19:50:06+00:00",
              "observed_utc": "2026-09-26T20:50:32+00:00", "direction": "up",
              "post_url": "https://example.invalid/source"}
    a = {**common, "claim_text": "First independent claim"}
    b = {**common, "claim_text": "Second independent claim"}

    def rows(claim):
        return claim_rows(claim["source_id"], claim["ticker"], claim["claim_text"],
                          claim["claim_utc"], direction=claim["direction"],
                          source_kind=claim["source_kind"], post_url=claim["post_url"],
                          made_at=claim["observed_utc"])

    original = rows(a) + rows(b)
    (tmp_path / "sources").mkdir()
    predictions = tmp_path / "predictions.jsonl"
    claims = tmp_path / "sources" / "claims.jsonl"
    predictions.write_text("".join(json.dumps(r) + "\n" for r in original), encoding="utf-8")
    claims.write_text(json.dumps(a) + "\n" + json.dumps(a) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="duplicate constructed forecast"):
        forecast_census(Sources(tmp_path), "2026-09-26", date(2026, 10, 9))
    duplicate_id = [dict(r) for r in original]
    duplicate_id[3]["prediction_id"] = duplicate_id[0]["prediction_id"]
    predictions.write_text("".join(json.dumps(r) + "\n" for r in duplicate_id),
                           encoding="utf-8")
    claims.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="duplicate or missing original prediction ID"):
        forecast_census(Sources(tmp_path), "2026-09-26", date(2026, 10, 9))


def test_forecast_reproduction_refuses_empty_or_wrong_source_day(tmp_path):
    (tmp_path / "sources").mkdir()
    (tmp_path / "predictions.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "sources" / "claims.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="no original forecasts"):
        forecast_census(Sources(tmp_path), "2026-09-26", date(2026, 10, 9))
    (tmp_path / "predictions.jsonl").write_text(
        json.dumps({"specialist": "source:wsj_heard_on_the_street",
                    "made_at": "2026-09-26T20:50:32+00:00"}) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="no original forecasts"):
        forecast_census(Sources(tmp_path), "2026-09-27", date(2026, 10, 9))


def test_common_window_refuses_missing_session_or_twin_bar(tmp_path):
    llm = tmp_path / "llm_portfolio"
    fleet = tmp_path / "paper_accounts" / "fleet_manager"
    llm.mkdir()
    fleet.mkdir(parents=True)
    names = ("revision_flow_v0", "revision_flow_v0_random_twin",
             "lib_net_raises_2026-09-26", "pers_revision_flow_leaders_2026-09-25")
    for filename, day, net in (("start.json", "2026-09-28", 0.0),
                               ("end.json", "2026-09-30", 0.02)):
        (llm / filename).write_text(json.dumps({
            "bars_through": day,
            "grades": [{"name": n, "to_date": {"status": "OK", "net": net}}
                       for n in names]}), encoding="utf-8")
    a = {"role": "hack2", "session": "2026-09-29", "prev_session": "2026-09-28",
         "contract_version": "v2", "policy_hash": "2301fa30c7b851df",
         "twin_priced_share": 1.0, "account_return": 0.01,
         "spy_return": 0.0, "twin_return": -0.01}
    b = {**a, "session": "2026-09-30", "prev_session": "2026-09-29"}
    grades = fleet / "grades.jsonl"
    grades.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n",
                      encoding="utf-8")
    result = common_window(Sources(tmp_path), "start.json", "end.json")
    assert result["frozen_net_endpoint_ratio_pct"]["revision_flow_v0"] == 2.0
    grades.write_text(json.dumps(b) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="chain has a gap"):
        common_window(Sources(tmp_path), "start.json", "end.json")
    b["prev_session"] = "2026-09-28"
    grades.write_text(json.dumps(b) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="missing weekday"):
        common_window(Sources(tmp_path), "start.json", "end.json")
    b["prev_session"] = "2026-09-29"
    b["twin_priced_share"] = 0.9
    grades.write_text(json.dumps(a) + "\n" + json.dumps(b) + "\n",
                      encoding="utf-8")
    with pytest.raises(EvidenceRefused, match="policy/pricing"):
        common_window(Sources(tmp_path), "start.json", "end.json")


def test_private_report_cannot_be_written_into_git_checkout(tmp_path):
    from scripts import original_evidence_audit as audit

    repo = audit.Path(audit.__file__).resolve().parents[1]
    out = repo / "private-audit.json"
    with pytest.raises(SystemExit) as exc:
        main(["--data-root", str(tmp_path), "--run-id", "x",
              "--asof", "2026-10-09", "--out", str(out)])
    assert exc.value.code == 2
    assert not out.exists()
