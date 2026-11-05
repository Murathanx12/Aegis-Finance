"""PRODUCT_EXPERIMENT: synthetic contracts + opt-in saved-input smoke tests.

Run actual smoke offline by setting AEGIS_NEWS_CIK_SMOKE_ROOT to a saved repo
root. No saved body, account or amount is embedded in these fixtures or printed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.services.news_cik_mapping import (
    MEMBERSHIP, SOURCE, CandidateMapper, MappingError, Snapshot,
    canonical_utc, normalize_cik, parse_document,
)
from scripts.news_cik_mapping_audit import audit_files, main


EARLY = "2026-11-05T00:15:28+00:00"
LATE = "2026-11-05T05:02:18+00:00"
CUTOFF = "2026-11-05T06:00:00Z"
OBSERVED = "2026-11-05T05:30:00+00:00"
MASTER = [
    {"cik_str": 1365135, "ticker": "WU"},
    {"cik_str": 1835830, "ticker": "KVYO"},
    {"cik_str": 1517413, "ticker": "FSLY"},
    {"cik_str": 1051470, "ticker": "CCI"},
    {"cik_str": 1652044, "ticker": "GOOG"},
    {"cik_str": 1652044, "ticker": "GOOGL"},
    {"cik_str": 884394, "ticker": "SPY"},
    {"cik_str": 1046179, "ticker": "TSM"},
    {"cik_str": 1067983, "ticker": "BRK-A"},
    {"cik_str": 1067983, "ticker": "BRK-B"},
]
PROXY = [{"market": "US", "exchange": "NYQ", "symbol": r["ticker"]}
         for r in MASTER if r["ticker"] != "SPY"] + [
             {"market": "TW", "exchange": "TAI", "symbol": "2330.TW"},
             {"market": "IN", "exchange": "NSI", "symbol": "M&M.NS"},
         ]


def mapper(master_known="2026-09-03T16:01:11.726816+00:00",
           proxy_known="2026-11-01T04:16:35Z", master=None, proxy=None):
    return CandidateMapper(
        MASTER if master is None else master, PROXY if proxy is None else proxy,
        master_snapshot=Snapshot("a" * 64, master_known),
        proxy_snapshot=Snapshot("b" * 64, proxy_known))


def row(cik=1365135, accession="0001193125-26-447234", filename="ex99_1.htm", seen=EARLY):
    return {"source": SOURCE, "first_seen_utc": seen,
            "published_utc": "1900-01-01T00:00:00Z",
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{filename}",
            "title": f"8-K - Synthetic issuer ({int(cik):010d}) (Filer) - EX-99.1",
            "raw_id": f"{accession}:{filename}", "tickers": []}


def symbols(doc):
    return [c["symbol"] for c in doc["candidates"]]


@pytest.mark.parametrize("cik,symbol", [(1365135, "WU"), (1835830, "KVYO")])
def test_tagless_recovery_is_issuer_level(cik, symbol):
    source = row(cik)
    original = copy.deepcopy(source)
    result = mapper().audit([source], as_of_utc=CUTOFF)
    doc = result["documents"][0]
    assert symbols(doc) == [symbol]
    assert doc["issuer_cik"] == str(cik)  # never accession's filing-agent CIK
    assert doc["cik_witnesses"] == ["SEC_ARCHIVE_URL", "FILING_TITLE"]
    assert doc["listing_identity"] == "UNCONFIRMED_REQUIRES_LISTING_WITNESS"
    assert doc["candidates"][0]["listing_candidates"][0]["membership"] == MEMBERSHIP
    assert source == original


@pytest.mark.parametrize("value", [None, "", "2026-11-05", "2026-11-05T00:00:00",
    "2026-11-05 00:00:00+00:00", "2026-11-05T08:00:00+08:00",
    "2026-11-05T00:00:00.1234567Z", "2026-02-30T00:00:00Z", 1793836800])
def test_noncanonical_availability_rejected_without_published_fallback(value):
    source = row(seen=value)
    result = mapper().audit([source], as_of_utc=CUTOFF)
    assert result["counts"]["rejected_rows"] == 1
    assert result["counts"]["documents"] == 0
    assert result["rejected"][0]["reason"] == "INVALID_CANONICAL_UTC"


def test_invalid_cutoff_and_snapshot_fail_loud():
    with pytest.raises(MappingError, match="INVALID_CANONICAL_UTC"):
        mapper().audit([], as_of_utc="2026-11-05")
    with pytest.raises(MappingError, match="INVALID_CANONICAL_UTC"):
        mapper(master_known="2026-09-03")
    with pytest.raises(MappingError, match="INVALID_SNAPSHOT_SHA256"):
        Snapshot("unbound", EARLY)
    assert canonical_utc(EARLY) == canonical_utc("2026-11-05T00:15:28Z")


@pytest.mark.parametrize("value", [True, 0, -1, 12.5, "12.0", " 12", "1e3", "12345678901"])
def test_cik_rejects_lossy_or_invalid_values(value):
    with pytest.raises(MappingError, match="INVALID_CIK"):
        normalize_cik(value)


def test_cik_sources_normalized_title_fallback_and_conflicts():
    source = row("0001365135")
    assert parse_document(source)["issuer_cik"] == "1365135"
    source["url"] = ""
    assert parse_document(source)["cik_witnesses"] == ["FILING_TITLE"]
    source = row()
    source["title"] = "8-K - Wrong issuer (0001835830) (Filer)"
    with pytest.raises(MappingError, match="URL_TITLE_CIK_CONFLICT"):
        parse_document(source)
    source["title"] += " and (0001365135) (Filer)"
    with pytest.raises(MappingError, match="AMBIGUOUS_TITLE_CIK"):
        parse_document(source)
    source["url"], source["title"] = "", "8-K - Western Union CO"
    with pytest.raises(MappingError, match="NO_ISSUER_CIK_WITNESS"):
        parse_document(source)


@pytest.mark.parametrize("change,reason", [
    ({"raw_id": "not-an-accession"}, "INVALID_RAW_ID"),
    ({"raw_id": "0001193125-26-447235:ex99_1.htm"}, "URL_RAW_ID_CONFLICT"),
    ({"raw_id": "0001193125-26-447234:other.htm"}, "URL_RAW_ID_CONFLICT"),
    ({"url": "https://sec.gov.evil/Archives/edgar/data/1365135/000119312526447234/ex99_1.htm"},
     "INVALID_SEC_ARCHIVE_URL"),
    ({"source": "unrelated"}, "NOT_SEC_EX99_SOURCE"),
])
def test_malformed_or_conflicting_document_abstains(change, reason):
    source = row()
    source.update(change)
    result = mapper().audit([source], as_of_utc=CUTOFF)
    assert result["counts"]["documents"] == 0
    assert result["rejected"][0]["reason"] == reason


def filing_rows():
    return [row(1517413, "0001517413-26-000343"),
            row(1517413, "0001517413-26-000342", "ex991.htm", LATE),
            row(1517413, "0001517413-26-000342", "ex992.htm", LATE),
            row(1051470, "0001051470-26-000091", "ex991.htm", LATE),
            row(1051470, "0001051470-26-000091", "ex992.htm", LATE)]


def test_document_filing_issuer_counts_and_duplicate_idempotence():
    rows = filing_rows()
    result = mapper().audit(rows + [rows[0]], as_of_utc=CUTOFF)
    assert result["counts"] == {"input_rows": 6, "excluded_after_cutoff": 0,
        "rejected_rows": 0, "eligible_rows": 6, "duplicate_rows": 1,
        "documents": 5, "filings": 3, "issuer_groups": 2}
    groups = {g["issuer_cik"]: g for g in result["issuer_groups"]}
    assert (groups["1517413"]["document_count"], groups["1517413"]["filing_count"]) == (3, 2)
    assert (groups["1051470"]["document_count"], groups["1051470"]["filing_count"]) == (2, 1)
    assert sorted(len(g["document_ids"]) for g in result["filings"]) == [1, 2, 2]
    assert "events" not in result["counts"]
    assert mapper().audit(list(reversed(rows)), as_of_utc=CUTOFF)["documents"] == result["documents"]


def test_first_seen_gates_each_sibling_and_duplicate_before_any_enrichment():
    early = row(1517413, "0001517413-26-000342", "ex991.htm")
    late = row(1517413, "0001517413-26-000342", "ex992.htm", LATE)
    duplicate = {**early, "first_seen_utc": LATE, "title": "later conflicting (1835830) (Filer)"}
    result = mapper().audit([late, duplicate, early], as_of_utc=EARLY)
    assert result["counts"]["excluded_after_cutoff"] == 2
    assert result["counts"]["rejected_rows"] == 0
    assert result["counts"]["documents"] == result["counts"]["filings"] == 1
    assert result["documents"] == mapper().audit([early], as_of_utc=EARLY)["documents"]
    # Future published timestamps do not exclude an already observed document either.
    early["published_utc"] = "2099-01-01T00:00:00Z"
    assert mapper().audit([early], as_of_utc=EARLY)["counts"]["documents"] == 1
    assert mapper().audit([early], as_of_utc="2026-11-05T00:04:58Z")["counts"]["documents"] == 0


@pytest.mark.parametrize("known,status", [(None, "UNKNOWN_AVAILABILITY"),
    ("2026-11-06T00:00:00Z", "AFTER_CUTOFF")])
def test_master_and_proxy_availability_gate_independently(known, status):
    r = mapper(master_known=known).audit([row()], as_of_utc=CUTOFF)
    assert r["master_snapshot"]["availability"] == status
    assert r["documents"][0]["candidates"] == []
    r = mapper(proxy_known=known).audit([row()], as_of_utc=CUTOFF)
    assert symbols(r["documents"][0]) == ["WU"]
    assert r["documents"][0]["candidates"][0]["listing_candidates"] == []
    assert r["proxy_snapshot"]["availability"] == status


def test_unknown_cik_abstains_despite_tags_and_names():
    source = row(9999999999)
    source["tickers"] = ["WU"]
    source["title"] = "8-K - Western Union (9999999999) (Filer)"
    doc = mapper().audit([source], as_of_utc=CUTOFF)["documents"][0]
    assert doc["mapping_status"] == "CIK_NOT_IN_SAVED_MASTER"
    assert doc["candidates"] == []


def test_spy_adr_share_class_and_venue_ambiguity_preserved():
    extra = PROXY + [{"market": "US", "exchange": "NMS", "symbol": "WU"},
                     {"market": "TW", "exchange": "TAI", "symbol": "TSM"}]
    m = mapper(proxy=extra)
    result = m.audit([row(cik) for cik in [884394, 1046179, 1652044, 1067983, 1365135]], as_of_utc=CUTOFF)
    docs = {d["issuer_cik"]: d for d in result["documents"]}
    assert symbols(docs["884394"]) == ["SPY"]  # fund survives absent proxy match
    assert docs["884394"]["candidates"][0]["listing_candidates"] == []
    assert symbols(docs["1046179"]) == ["TSM"]  # no inference of 2330.TW relation
    assert {l["market"] for l in docs["1046179"]["candidates"][0]["listing_candidates"]} == {"US"}
    assert symbols(docs["1652044"]) == ["GOOG", "GOOGL"]
    assert symbols(docs["1067983"]) == ["BRK-A", "BRK-B"]
    assert len(docs["1365135"]["candidates"][0]["listing_candidates"]) == 2
    for doc in docs.values():
        assert doc["listing_identity"] == "UNCONFIRMED_REQUIRES_LISTING_WITNESS"


def test_public_result_does_not_copy_body_tags_titles_or_private_fields():
    source = row()
    source.update(body="LICENSED_BODY_SENTINEL", private_amount="PRIVATE_AMOUNT_SENTINEL",
                  entity_tags=["PRIVATE_ENTITY_SENTINEL"], tickers=["FALSE_TAG_SENTINEL"])
    source["title"] += " TITLE_SENTINEL"
    encoded = json.dumps(mapper().audit([source], as_of_utc=CUTOFF))
    assert "SENTINEL" not in encoded
    assert '"body"' not in encoded and '"title"' not in encoded


def saved_paths(root):
    base = Path(root) / "backend/data/optimus"
    return dict(corpus_paths=[base / "news_corpus/sec_edgar_8k_ex99_body/2026-11-05.jsonl"],
                master_path=base / "edgar_8k/company_tickers.json",
                master_meta_path=base / "edgar_8k/company_tickers.meta.json",
                proxy_path=base / "contest/universe/universe_2026-11-01.parquet",
                proxy_receipt_path=base / "contest/universe/universe_2026-11-01_receipt.json")


def cli_args(paths, cutoff=CUTOFF):
    return ["--corpus", str(paths["corpus_paths"][0]), "--master", str(paths["master_path"]),
            "--master-meta", str(paths["master_meta_path"]), "--proxy", str(paths["proxy_path"]),
            "--proxy-receipt", str(paths["proxy_receipt_path"]), "--as-of", cutoff]


@pytest.fixture
def synthetic_files(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.news_cik_mapping_audit._observation_clock", lambda: OBSERVED)
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    paths = saved_paths(tmp_path)
    for path in [paths["corpus_paths"][0], *[p for p in paths.values() if isinstance(p, Path)]]:
        path.parent.mkdir(parents=True, exist_ok=True)
    paths["corpus_paths"][0].write_text(json.dumps({**row(), "body": "LICENSED_SENTINEL"}) + "\n")
    paths["master_path"].write_text(json.dumps({str(i): r for i, r in enumerate(MASTER)}))
    paths["master_meta_path"].write_text(json.dumps({"n_entries": len(MASTER), "fetched_at_utc": EARLY}))
    pd.DataFrame(PROXY).to_parquet(paths["proxy_path"], index=False)
    paths["proxy_receipt_path"].write_text(json.dumps({"rows_after": len(PROXY), "written_utc": "20261101T041635Z"}))
    return paths


def test_cli_reads_only_saved_files_and_prints_safe_json(synthetic_files, capsys):
    paths = synthetic_files
    flat = [paths["corpus_paths"][0], *[p for p in paths.values() if isinstance(p, Path)]]
    before = [p.read_bytes() for p in flat]
    assert main(cli_args(paths)) == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert output["counts"]["documents"] == 1
    assert output["input_sha256"]["corpus"] == [hashlib.sha256(before[0]).hexdigest()]
    assert output["proxy_snapshot"]["known_at_utc"] == OBSERVED
    assert output["proxy_snapshot"]["declared_at_utc"] == "2026-11-01T04:16:35+00:00"
    assert output["master_snapshot"]["known_at_utc"] == OBSERVED
    assert output["master_snapshot"]["clock_basis"] == "CURRENT_OBSERVATION_NO_VERIFIED_VINTAGE"
    assert "SENTINEL" not in captured.out and str(paths["master_path"]) not in captured.out
    assert [p.read_bytes() for p in flat] == before


def test_cli_rejection_and_malformed_json_fail_loud_safely(synthetic_files, capsys):
    paths = synthetic_files
    corpus = paths["corpus_paths"][0]
    corpus.write_text(json.dumps(row(seen="INVALID_SECRET_SENTINEL")))
    assert main(cli_args(paths)) == 1
    assert "SENTINEL" not in capsys.readouterr().out
    corpus.write_text('{"body": "LICENSED_SENTINEL"')
    assert main(cli_args(paths)) == 2
    capture = capsys.readouterr()
    assert capture.out == "" and "SENTINEL" not in capture.err
    assert json.loads(capture.err)["error"] == "UNREADABLE_OR_INVALID_SAVED_INPUT"


def test_cli_detects_input_race_and_mismatched_receipt(synthetic_files, monkeypatch):
    from scripts import news_cik_mapping_audit as cli

    paths = synthetic_files
    real = cli._fingerprint
    count = 0

    def unstable(path):
        nonlocal count
        count += 1
        return real(path) if count <= 5 else "c" * 64

    monkeypatch.setattr(cli, "_fingerprint", unstable)
    with pytest.raises(MappingError, match="INPUT_CHANGED_DURING_AUDIT"):
        audit_files(**paths, as_of_utc=CUTOFF)
    monkeypatch.setattr(cli, "_fingerprint", real)
    paths["proxy_receipt_path"].write_text(json.dumps({"rows_after": 1, "written_utc": "20261101T041635Z"}))
    with pytest.raises(MappingError, match="SNAPSHOT_ROW_COUNT_MISMATCH"):
        audit_files(**paths, as_of_utc=CUTOFF)


def pinned_manifest(paths, tmp_path):
    """Synthetic independently verified provenance; pin before any substitutions."""
    receipt = json.loads(paths["proxy_receipt_path"].read_text())
    entries = {}
    for kind, data_key, meta_key in [("master", "master_path", "master_meta_path"),
                                      ("proxy", "proxy_path", "proxy_receipt_path")]:
        entries[kind] = {
            "data_sha256": hashlib.sha256(paths[data_key].read_bytes()).hexdigest(),
            "metadata_sha256": hashlib.sha256(paths[meta_key].read_bytes()).hexdigest(),
            "known_at_utc": EARLY,
        }
    if "path" in receipt:
        entries["proxy"]["source_path"] = receipt["path"]
    manifest = tmp_path / "verified-provenance.json"
    manifest.write_text(json.dumps({"schema_version": 1, "snapshots": entries}))
    return dict(provenance_manifest_path=manifest,
                provenance_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())


def test_same_count_master_replacement_never_inherits_legacy_date(synthetic_files):
    paths = synthetic_files
    master = json.loads(paths["master_path"].read_text())
    master["0"]["ticker"] = "NEWALIAS"
    paths["master_path"].write_text(json.dumps(master))  # same count, unchanged old metadata
    old = audit_files(**paths, as_of_utc="2026-11-05T01:00:00Z")
    assert old["documents"][0]["candidates"] == []
    assert old["master_snapshot"]["known_at_utc"] == OBSERVED
    assert old["master_snapshot"]["declared_at_utc"] == EARLY
    assert old["master_snapshot"]["availability"] == "AFTER_CUTOFF"
    current = audit_files(**paths, as_of_utc=CUTOFF)
    assert symbols(current["documents"][0]) == ["NEWALIAS"]
    assert current["master_snapshot"]["clock_basis"] == "CURRENT_OBSERVATION_NO_VERIFIED_VINTAGE"


def test_proxy_receipt_path_contradiction_rejected_by_cli(synthetic_files, tmp_path, capsys):
    import pandas as pd

    paths = synthetic_files
    receipt = json.loads(paths["proxy_receipt_path"].read_text())
    receipt["path"] = str(paths["proxy_path"])
    paths["proxy_receipt_path"].write_text(json.dumps(receipt))
    replacement = tmp_path / "replacement.parquet"
    changed = [{**p, "exchange": "FUTURE"} for p in PROXY]
    pd.DataFrame(changed).to_parquet(replacement, index=False)
    assert main(cli_args({**paths, "proxy_path": replacement})) == 2
    capture = capsys.readouterr()
    assert capture.out == ""
    assert json.loads(capture.err) == {"error": "PROXY_RECEIPT_PATH_CONTRADICTION"}


def test_same_path_proxy_replacement_is_current_observation_only(synthetic_files, tmp_path):
    import pandas as pd

    paths = synthetic_files
    provenance = pinned_manifest(paths, tmp_path)
    # Verify the master independently so this checks the proxy gate specifically.
    manifest = provenance["provenance_manifest_path"]
    content = json.loads(manifest.read_text())
    del content["snapshots"]["proxy"]
    manifest.write_text(json.dumps(content))
    provenance["provenance_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    pd.DataFrame([{**p, "exchange": "FUTURE"} for p in PROXY]).to_parquet(paths["proxy_path"], index=False)
    result = audit_files(**paths, **provenance, as_of_utc="2026-11-05T01:00:00Z")
    assert symbols(result["documents"][0]) == ["WU"]
    assert result["documents"][0]["candidates"][0]["listing_candidates"] == []
    assert result["proxy_snapshot"]["known_at_utc"] == OBSERVED
    assert result["proxy_snapshot"]["availability"] == "AFTER_CUTOFF"


def test_verified_content_provenance_allows_copies_without_backdating_arbitrary_bytes(
        synthetic_files, tmp_path, capsys):
    paths = synthetic_files
    receipt = json.loads(paths["proxy_receipt_path"].read_text())
    receipt["path"] = str(paths["proxy_path"])
    paths["proxy_receipt_path"].write_text(json.dumps(receipt))
    provenance = pinned_manifest(paths, tmp_path)
    copies = dict(paths)
    for key in ("master_path", "master_meta_path", "proxy_path", "proxy_receipt_path"):
        copied = tmp_path / ("copied-" + paths[key].name)
        copied.write_bytes(paths[key].read_bytes())
        copies[key] = copied
    args = cli_args(copies, cutoff="2026-11-05T01:00:00Z") + [
        "--provenance-manifest", str(provenance["provenance_manifest_path"]),
        "--provenance-manifest-sha256", provenance["provenance_manifest_sha256"]]
    assert main(args) == 0
    capture = capsys.readouterr()
    result = json.loads(capture.out)
    assert symbols(result["documents"][0]) == ["WU"]
    assert result["documents"][0]["candidates"][0]["listing_candidates"]
    for kind in ("master", "proxy"):
        assert result[f"{kind}_snapshot"]["known_at_utc"] == EARLY
        assert result[f"{kind}_snapshot"]["clock_basis"] == "PINNED_CONTENT_PROVENANCE"
    assert result["input_sha256"]["provenance_manifest"] == provenance["provenance_manifest_sha256"]
    assert str(tmp_path) not in capture.out and "SENTINEL" not in capture.out


@pytest.mark.parametrize("target", ["master_path", "proxy_path", "master_meta_path", "proxy_receipt_path"])
def test_pinned_provenance_rejects_replacement_data_or_metadata(synthetic_files, tmp_path, target):
    import pandas as pd

    paths = synthetic_files
    provenance = pinned_manifest(paths, tmp_path)
    path = paths[target]
    if target == "master_path":
        content = json.loads(path.read_text())
        content["0"]["ticker"] = "NEWALIAS"
        path.write_text(json.dumps(content))
    elif target == "proxy_path":
        pd.DataFrame([{**p, "exchange": "FUTURE"} for p in PROXY]).to_parquet(path, index=False)
    else:
        path.write_text(path.read_text() + " ")  # counts/clock unchanged, receipt bytes differ
    with pytest.raises(MappingError, match="PROVENANCE_CONTENT_MISMATCH"):
        audit_files(**paths, **provenance, as_of_utc=CUTOFF)


@pytest.mark.parametrize("mode,reason", [
    ("no_pin", "INVALID_PROVENANCE_MANIFEST_OPTIONS"),
    ("wrong_pin", "PROVENANCE_MANIFEST_HASH_MISMATCH"),
    ("bad_clock", "INVALID_CANONICAL_UTC"),
    ("null_entry", "INVALID_PROVENANCE_MANIFEST"),
])
def test_manifest_requires_external_pin_valid_schema_and_clock(synthetic_files, tmp_path, mode, reason):
    provenance = pinned_manifest(synthetic_files, tmp_path)
    path = provenance["provenance_manifest_path"]
    if mode == "no_pin":
        provenance["provenance_manifest_sha256"] = None
    elif mode == "wrong_pin":
        provenance["provenance_manifest_sha256"] = "0" * 64
    else:
        content = json.loads(path.read_text())
        if mode == "bad_clock":
            content["snapshots"]["master"]["known_at_utc"] = "2026-09-03"
        else:
            content["snapshots"]["master"] = None
        path.write_text(json.dumps(content))
        provenance["provenance_manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(MappingError, match=reason):
        audit_files(**synthetic_files, **provenance, as_of_utc=CUTOFF)


def test_manifest_cannot_override_a_different_receipt_path(synthetic_files, tmp_path):
    paths = synthetic_files
    receipt = json.loads(paths["proxy_receipt_path"].read_text())
    receipt["path"] = str(tmp_path / "unrelated-original.parquet")
    paths["proxy_receipt_path"].write_text(json.dumps(receipt))
    provenance = pinned_manifest(paths, tmp_path)
    manifest = provenance["provenance_manifest_path"]
    content = json.loads(manifest.read_text())
    content["snapshots"]["proxy"]["source_path"] = str(tmp_path / "different-original.parquet")
    manifest.write_text(json.dumps(content))
    provenance["provenance_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(MappingError, match="PROXY_RECEIPT_PATH_CONTRADICTION"):
        audit_files(**paths, **provenance, as_of_utc=CUTOFF)


@pytest.mark.skipif(not os.environ.get("AEGIS_NEWS_CIK_SMOKE_ROOT"), reason="explicit saved-input root required")
def test_actual_saved_nov5_smoke():
    paths = saved_paths(os.environ["AEGIS_NEWS_CIK_SMOKE_ROOT"])
    # Legacy bytes have no verified historical clock. A current observation can
    # support a current descriptive audit only, never the old book's replay.
    current_cutoff = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    result = audit_files(**paths, as_of_utc=current_cutoff)
    assert result["input_sha256"]["corpus"] == ["2897cb67b3457193f3c3c357017fa8c8adae3e529f729a2d23b87c2ee66186dc"]
    assert result["input_sha256"]["master"] == "69aad87bc3a80196a0340263f4213c8242c1eb9a846bdba861240994bf5e03d5"
    assert result["input_sha256"]["proxy"] == "86a58cc34b44682113f0830c431a1ecb7475025cf6ae57ba08528d1dd727d27d"
    assert result["counts"] == {"input_rows": 21, "excluded_after_cutoff": 0,
        "rejected_rows": 0, "eligible_rows": 21, "duplicate_rows": 0,
        "documents": 21, "filings": 18, "issuer_groups": 17}
    for kind in ("master", "proxy"):
        snapshot = result[f"{kind}_snapshot"]
        assert snapshot["known_at_utc"] == result["observed_at_utc"]
        assert snapshot["clock_basis"] == "CURRENT_OBSERVATION_NO_VERIFIED_VINTAGE"
    groups = {g["issuer_cik"]: g for g in result["issuer_groups"]}
    for cik, symbol in [("1365135", "WU"), ("1835830", "KVYO")]:
        assert [c["symbol"] for c in groups[cik]["candidates"]] == [symbol]
        assert next(d for d in result["documents"] if d["issuer_cik"] == cik)["cik_witnesses"] == [
            "SEC_ARCHIVE_URL", "FILING_TITLE"]
    assert (groups["1517413"]["document_count"], groups["1517413"]["filing_count"]) == (3, 2)
    assert (groups["1051470"]["document_count"], groups["1051470"]["filing_count"]) == (2, 1)
    before_book = audit_files(**paths, as_of_utc="2026-11-05T00:04:58+00:00")
    assert before_book["counts"]["documents"] == 0
    assert before_book["counts"]["excluded_after_cutoff"] == 21
    early = audit_files(**paths, as_of_utc=EARLY)
    assert early["counts"]["documents"] == 8
    assert "1835830" not in {g["issuer_cik"] for g in early["issuer_groups"]}
    assert all(d["candidates"] == [] for d in early["documents"])
    assert early["master_snapshot"]["availability"] == "AFTER_CUTOFF"
    actual_master = json.loads(paths["master_path"].read_text())
    import pandas as pd
    actual_mapper = CandidateMapper(actual_master.values(), pd.read_parquet(
        paths["proxy_path"], columns=["market", "symbol", "exchange"]).to_dict("records"),
        master_snapshot=Snapshot(result["input_sha256"]["master"], result["master_snapshot"]["known_at_utc"]),
        proxy_snapshot=Snapshot(result["input_sha256"]["proxy"], result["proxy_snapshot"]["known_at_utc"]))
    ambiguity = actual_mapper.audit([row(cik) for cik in [884394, 1046179, 1652044]], as_of_utc=current_cutoff)
    docs = {d["issuer_cik"]: d for d in ambiguity["documents"]}
    assert symbols(docs["884394"]) == ["SPY"]
    assert docs["884394"]["candidates"][0]["listing_candidates"] == []
    assert symbols(docs["1046179"]) == ["TSM", "TSMWF"]
    assert all(l["market"] == "US" for c in docs["1046179"]["candidates"]
               for l in c["listing_candidates"])
    assert symbols(docs["1652044"]) == ["GOOG", "GOOGL", "GOOGM", "GOOGN"]
