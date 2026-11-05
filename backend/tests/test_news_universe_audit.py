"""Synthetic offline mapping, provenance, refusal and filing-boundary checks."""
import hashlib
import json
from datetime import datetime, timezone

import pytest

from scripts import news_universe_audit as A


NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
DAY = NOW[:10]


@pytest.fixture
def universe():
    names = {"QCOM": "QUALCOMM Incorporated", "META": "Meta Platforms, Inc.",
             "GOOGL": "Alphabet Inc.", "PSNL": "Personalis, Inc.",
             "GEV": "GE Vernova Inc.", "BE": "Bloom Energy Corporation",
             "SNOW": "Snowflake Inc.", "WU": "Western Union Company",
             "KVYO": "Klaviyo, Inc.", "FSLY": "Fastly, Inc.",
             "CCI": "Crown Castle Inc.", "AAPL": "Apple Inc."}
    return A.Universe([dict(market="US", symbol=s, name=n, membership=A.MEMBERSHIP)
                       for s, n in names.items()])


def row(title="QUALCOMM announces results", tickers=None, source="dj_reader_marketwatch", **extra):
    return dict(source=source, title=title, body="LICENSED_BODY_MUST_NOT_ESCAPE",
                url="https://www.marketwatch.com/story/synthetic", tickers=tickers or [],
                entity_tags=[], first_seen_utc=NOW, published_utc=NOW, **extra)


def classify(universe, r, **kw):
    return A.audit_row(r, source=r["source"], universe=universe, sec_cache=kw.get("sec_cache", {}),
                       held=kw.get("held"), budget=A.Budget(A.Limits()))


def by_symbol(result, symbol):
    return next(c for c in result["candidates"] if c["symbol"] == symbol)


@pytest.mark.parametrize("tag,title", [
    ("META", "QUALCOMM and Starlink update satellite plans"),
    ("GOOGL", "QUALCOMM and SpaceX announce an update"),
    ("PSNL", "QUALCOMM announces results"),
    ("GEV", "Bloom Energy outlines data center plans"),
])
def test_reported_false_discovery_tags_never_direct(universe, tag, title):
    result = classify(universe, row(title, [tag]))
    assert by_symbol(result, tag)["evidence_class"] == "REVIEW_REQUIRED"
    assert by_symbol(result, tag)["reason"] == "TAG_WITHOUT_TITLE_ISSUER_WITNESS"


def test_positive_title_issuer_witness_and_scope(universe):
    c = by_symbol(classify(universe, row("QUALCOMM Incorporated announces results")), "QCOM")
    assert c["evidence_class"] == "DIRECT"
    assert c["evidence_scope"] == "ISSUER_IDENTIFICATION_ONLY"
    assert c["security_event_relation"] == "REVIEW_REQUIRED"
    assert c["membership"] == "UNCONFIRMED_MEMBERSHIP"


@pytest.mark.parametrize("title,extra", [
    ("QCOM moves today", {}),
    ("Industry developments", {"tickers_named": ["QCOM", "AAPL"]}),
])
def test_symbol_or_full_page_sidebar_is_not_issuer_evidence(universe, title, extra):
    r = row(title, ["QCOM"], **extra)
    r["body"] = "QUALCOMM Incorporated " * 10
    c = by_symbol(classify(universe, r), "QCOM")
    assert c["evidence_class"] == "REVIEW_REQUIRED"
    assert all(x["symbol"] != "AAPL" for x in classify(universe, r)["candidates"])


@pytest.mark.parametrize("title,url", [
    ("QUALCOMM Analyst Estimates", "https://example.test/stock/qcom"),
    ("QUALCOMM forecasts", "https://example.test/stock/qcom/analystestimates"),
])
def test_recurring_estimates_are_reference_not_events(universe, title, url):
    r = row(title, ["QCOM"])
    r["url"] = url
    result = classify(universe, r)
    assert result["event_status"] == "NO_EVENT_RECURRING_ESTIMATES"
    assert by_symbol(result, "QCOM")["evidence_class"] == "REVIEW_REQUIRED"


def test_weather_homonym_rejected_and_real_snowflake_retained(universe):
    result = classify(universe, row("Winter storm brings Snow to the region", ["SNOW"], source="gdelt_doc_v2"))
    assert by_symbol(result, "SNOW")["evidence_class"] == "REJECTED"
    assert by_symbol(classify(universe, row("Snowflake Inc. announces results", ["SNOW"])), "SNOW")["evidence_class"] == "DIRECT"


def test_ambiguous_names_markets_and_indirect_mentions_abstain(universe):
    result = classify(universe, row("QUALCOMM and Bloom Energy discuss supplier demand"))
    assert {c["evidence_class"] for c in result["candidates"]} == {"REVIEW_REQUIRED"}
    records = list(universe.by_key.values()) + [dict(market="EU", symbol="QCOM", name="QUALCOMM Incorporated", membership=A.MEMBERSHIP)]
    assert {c["evidence_class"] for c in classify(A.Universe(records), row())["candidates"]} == {"REVIEW_REQUIRED"}


def sec_row(cik="1365135", acc="0001193125-26-447234", filename="ex99.htm", **kw):
    r = row("Exhibit 99.1", source="sec_edgar_8k_ex99_body", **kw)
    r["entity_tags"] = [f"cik:{int(cik):010d}", f"accession:{acc}", "8-K:2.02"]
    r["url"] = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{filename}"
    return r


@pytest.mark.parametrize("cik,symbol", [("1365135", "WU"), ("1835830", "KVYO")])
def test_tagless_sec_issuer_join_uses_cik_not_filing_agent(universe, cik, symbol):
    result = classify(universe, sec_row(cik), sec_cache={cik: {symbol}})
    assert by_symbol(result, symbol)["evidence_class"] == "DIRECT"
    assert not by_symbol(result, symbol)["tagged_in_source"]
    assert result["sec_identity"]["cik"] == cik
    assert result["first_seen_utc"] == NOW
    assert result["published_utc"] == NOW


@pytest.mark.parametrize("change", ["host", "cik", "accession", "duplicate_cik"])
def test_conflicting_or_spoofed_sec_identity_is_not_direct(universe, change):
    r = sec_row(tickers=["WU"])
    if change == "host":
        r["url"] = r["url"].replace("www.sec.gov", "sec.gov.evil.test")
    elif change == "cik":
        r["entity_tags"][0] = "cik:0001835830"
    elif change == "accession":
        r["entity_tags"][1] = "accession:0001193125-26-000001"
    else:
        r["entity_tags"].append("cik:0001835830")
    result = classify(universe, r, sec_cache={"1365135": {"WU"}})
    assert by_symbol(result, "WU")["evidence_class"] == "REVIEW_REQUIRED"
    assert not result["sec_identity"]["verified"]


def test_cik_does_not_choose_share_class(universe):
    result = classify(universe, sec_row(), sec_cache={"1365135": {"WU", "WU-A"}})
    assert by_symbol(result, "WU")["evidence_class"] == "REVIEW_REQUIRED"
    assert by_symbol(result, "WU-A")["evidence_class"] == "REJECTED"


def write_rows(tmp_path, rows, source="dj_reader_marketwatch"):
    path = tmp_path / source / f"{DAY}.jsonl"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows))
    return path


def run_audit(root, universe, **kw):
    return A.audit(root, DAY, universe, {"membership": A.MEMBERSHIP}, **kw)


def test_filing_groups_keep_three_fsly_exhibits_in_two_filings_and_cci_two_in_one(tmp_path, universe):
    rs = [sec_row("1517413", "0001517413-26-000343", "a.htm"),
          sec_row("1517413", "0001517413-26-000342", "a.htm"),
          sec_row("1517413", "0001517413-26-000342", "b.htm"),
          sec_row("1051470", "0001051470-26-000091", "a.htm"),
          sec_row("1051470", "0001051470-26-000091", "b.htm")]
    rs[2]["first_seen_utc"] = "2099-01-01T00:00:00Z"  # later sibling stays dated separately
    write_rows(tmp_path, rs, "sec_edgar_8k_ex99_body")
    result = run_audit(tmp_path, universe, sec_cache={"1517413": {"FSLY"}, "1051470": {"CCI"}})
    assert sorted(g["source_rows"] for g in result["event_candidate_groups"]) == [1, 2, 2]
    assert len({r["sec_identity"]["document_id_sha256"] for r in result["rows"]}) == 5
    assert result["rows"][2]["first_seen_utc"].startswith("2099")
    assert result["rows"][2]["published_utc"] == NOW


def test_provenance_hash_and_no_text_url_or_absolute_path_leak(tmp_path, universe):
    r = row("QUALCOMM TITLE_SENTINEL", ["QCOM"])
    path = write_rows(tmp_path, [r])
    before = path.read_bytes()
    result = run_audit(tmp_path, universe)
    out = json.dumps(result)
    assert result["rows"][0]["row_sha256"] == hashlib.sha256(before).hexdigest()
    assert result["rows"][0]["source_line"] == 1
    assert path.read_bytes() == before
    assert result["files"][0]["snapshot_sha256"] == hashlib.sha256(before).hexdigest()
    assert not any(s in out for s in [r["title"], r["body"], r["url"], str(tmp_path)])
    assert not result["digest_ran"] and not result["decision_ran"] and result["spend_units"] == 0


def test_duplicate_sec_document_keeps_rows_but_does_not_inflate_documents(tmp_path, universe):
    r = sec_row()
    write_rows(tmp_path, [r, r], "sec_edgar_8k_ex99_body")
    result = run_audit(tmp_path, universe, sec_cache={"1365135": {"WU"}})
    assert result["summary"]["rows"] == 2
    assert result["summary"]["groups"] == result["summary"]["documents"] == 1
    assert result["event_candidate_groups"][0]["source_rows"] == 2


def test_held_symbol_outside_proxy_survives_and_ownership_is_unknown(tmp_path, universe):
    write_rows(tmp_path, [row()])
    result = run_audit(tmp_path, universe, held={"SPY", "US:QCOM"}, held_as_of=NOW)
    assert result["held_coverage"][0] == dict(safe_list_entry="SPY", proxy_keys=[], status="OUTSIDE_PROXY_PRESERVED")
    assert by_symbol(result["rows"][0], "QCOM")["held_safe_list_match"] is True
    assert result["ownership_now"] == "UNKNOWN"
    assert result["held_as_of_utc"] == NOW


@pytest.mark.parametrize("field,value", [("first_seen_utc", None), ("first_seen_utc", "2026-01-01"),
                                       ("published_utc", "2099-01-01T00:00:00Z")])
def test_unknown_or_inconsistent_source_clocks_do_not_promote(universe, field, value):
    r = row("QUALCOMM Incorporated announces results")
    r[field] = value
    result = classify(universe, r)
    assert result["clock_issues"]
    assert by_symbol(result, "QCOM")["evidence_class"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("limits,reason", [
    (A.Limits(rows=1), "ROW_LIMIT"), (A.Limits(news_bytes=1), "NEWS_BYTE_LIMIT"),
    (A.Limits(line_bytes=16), "INCOMPLETE_OR_OVERSIZE_LINE"),
    (A.Limits(output_bytes=1), "OUTPUT_SIZE_LIMIT"),
])
def test_bounds_fail_loud_without_partial_green(tmp_path, universe, limits, reason):
    write_rows(tmp_path, [row(), row()])
    with pytest.raises(A.Refused, match=reason):
        run_audit(tmp_path, universe, limits=limits)


def test_deadline_and_candidate_limit(universe, monkeypatch):
    budget = A.Budget(A.Limits())
    monkeypatch.setattr(A.time, "monotonic", lambda: budget.deadline + 1)
    with pytest.raises(A.Refused, match="TIME_LIMIT"):
        budget.check()
    monkeypatch.undo()
    with pytest.raises(A.Refused, match="CANDIDATE_LIMIT"):
        A.audit_row(row("QUALCOMM and Bloom Energy"), source="dj_reader_marketwatch",
                    universe=universe, sec_cache={}, held=None, budget=A.Budget(A.Limits(candidates=1)))


def test_missing_empty_partial_and_malformed_inputs_fail(tmp_path, universe):
    with pytest.raises(A.Refused, match="DATED_INPUT_MISSING"):
        run_audit(tmp_path, universe)
    p = write_rows(tmp_path, [])
    with pytest.raises(A.Refused, match="EMPTY_DATED_INPUT"):
        run_audit(tmp_path, universe)
    p.write_bytes(b'{"secret":"RAW_SECRET"}')
    with pytest.raises(A.Refused, match="INCOMPLETE_OR_OVERSIZE_LINE"):
        run_audit(tmp_path, universe)
    p.write_bytes(b'{"secret":"RAW_SECRET",}\n')
    with pytest.raises(ValueError):
        run_audit(tmp_path, universe)


def test_actual_parquet_schema_and_vintage_validation(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    p = tmp_path / "universe_2026-11-01.parquet"
    records = [dict(market="US", symbol="QCOM", name="QUALCOMM Incorporated", membership=A.MEMBERSHIP,
                    screened_on="2026-10-31")]
    pq.write_table(pa.Table.from_pylist(records), p)
    u, meta = A.load_universe(p, A.Budget(A.Limits()), expected_rows=1)
    assert len(u.by_key) == 1 and meta["membership_confirmed"] is False
    with pytest.raises(A.Refused, match="UNIVERSE_ROW_COUNT"):
        A.load_universe(p, A.Budget(A.Limits()))
    records[0]["screened_on"] = "2026-11-02"
    pq.write_table(pa.Table.from_pylist(records), p)
    with pytest.raises(A.Refused, match="UNIVERSE_VINTAGE"):
        A.load_universe(p, A.Budget(A.Limits()), expected_rows=1)


def test_both_real_sec_cache_schemas_and_collision_preservation(tmp_path):
    p = tmp_path / "cache.json"
    p.write_text(json.dumps({"t": NOW, "map": {"0001365135": "WU"}}))
    mapping, meta = A.load_sec_cache(p, A.Budget(A.Limits()))
    assert mapping == {"1365135": {"WU"}} and meta["reported_cache_utc"] == NOW
    p.write_text(json.dumps({"0": {"cik_str": 1, "ticker": "GOOG", "title": "Alphabet"},
                             "1": {"cik_str": 1, "ticker": "GOOGL", "title": "Alphabet"}}))
    mapping, meta = A.load_sec_cache(p, A.Budget(A.Limits()))
    assert mapping == {"1": {"GOOG", "GOOGL"}}
    assert meta["reported_cache_utc"] is None and not meta["point_in_time_certified"]


def test_safe_list_refuses_identity_objects(tmp_path):
    p = tmp_path / "safe.json"
    p.write_text(json.dumps({"account": "PRIVATE", "holdings": []}))
    with pytest.raises(A.Refused, match="HELD_SAFE_LIST_SCHEMA"):
        A.load_held(p, A.Budget(A.Limits()))


def test_cli_sanitized_nonzero_refusal(tmp_path, capsys):
    code = A.main(["--corpus-root", str(tmp_path), "--date", DAY, "--universe",
                   str(tmp_path / "PRIVATE_FILENAME.parquet")])
    output = capsys.readouterr().out
    assert code == 2 and json.loads(output)["status"] == "REFUSED"
    assert "PRIVATE_FILENAME" not in output and str(tmp_path) not in output


@pytest.mark.parametrize("title,expected", [
    ("Partners announce satellite service expansion", "REVIEW_REQUIRED"),
    ("Partners Group Holding AG announces results", "DIRECT"),
])
def test_c1_real_proxy_name_shortening_cannot_prove_issuer(title, expected):
    universe = A.Universe([dict(market="EU", symbol="PGHN.SW",
                               name="Partners Group Holding AG", membership=A.MEMBERSHIP)])
    c = by_symbol(classify(universe, row(title)), "PGHN.SW")
    assert c["evidence_class"] == expected
    assert c["title_name_candidate"]
    assert c["title_issuer_witness"] == (expected == "DIRECT")
    if expected != "DIRECT":
        assert c["reason"] == "NORMALIZED_NAME_REQUIRES_FULL_ISSUER_WITNESS"


@pytest.mark.parametrize("title", ["QUALCOMM announces results", "Western Union announces results"])
def test_c1_shortened_names_are_candidates_even_when_unique(universe, title):
    result = classify(universe, row(title))
    assert result["candidates"]
    assert all(c["evidence_class"] == "REVIEW_REQUIRED" for c in result["candidates"])


@pytest.mark.parametrize("schema", ["master", "official"])
@pytest.mark.parametrize("other_cik", ["1835830", "0001835830"])
def test_c2_inverse_cik_symbol_conflicts_refuse(tmp_path, schema, other_cik):
    p = tmp_path / "cache.json"
    payload = ({"t": NOW, "map": {"0001365135": "WU", other_cik: "WU"}}
               if schema == "official" else
               {"0": {"cik_str": "0001365135", "ticker": "WU", "title": "Western Union Company"},
                "1": {"cik_str": other_cik, "ticker": "WU", "title": "Klaviyo Inc."}})
    p.write_text(json.dumps(payload))
    with pytest.raises(A.Refused, match="SEC_CACHE_SYMBOL_CIK_CONFLICT"):
        A.load_sec_cache(p, A.Budget(A.Limits()))


def test_c2_same_normalized_cik_is_not_an_inverse_conflict(tmp_path):
    p = tmp_path / "cache.json"
    p.write_text(json.dumps({"t": NOW, "map": {"1365135": "WU", "0001365135": "WU"}}))
    mapping, _ = A.load_sec_cache(p, A.Budget(A.Limits()))
    assert mapping == {"1365135": {"WU"}}


def test_c3_sec_clock_does_not_certify_unrelated_proxy_title_mapping(tmp_path, universe):
    write_rows(tmp_path, [row("QUALCOMM Incorporated announces results")])
    proxy = {"sha256": "proxy-observation", "archive_date": None,
             "historical_availability_utc": None}
    cache = {"provided": True, "sha256": "sec-observation",
             "reported_cache_utc": "2000-01-01T00:00:00+00:00", "cache_utc": "2000-01-01T00:00:00+00:00"}
    r = A.audit(tmp_path, DAY, universe, proxy, sec_cache={"1365135": {"WU"}}, sec_meta=cache)
    assert r["rows"][0]["mapping_known_at_first_seen"] is None
    c = by_symbol(r["rows"][0], "QCOM")
    assert c["mapping_source_refs"] == ["universe"]
    assert c["mapping_known_at_first_seen"] is None
    assert c["evidence_class"] == "DIRECT"


@pytest.fixture
def unbound_proxy(tmp_path):
    """Same accepted count/basename/vintage fields do not bind historical bytes."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    p = tmp_path / "alternate" / "universe_2026-11-01.parquet"
    p.parent.mkdir()
    records = [dict(market="US", symbol="QCOM", name="Novel Quantum Circuits Incorporated",
                    membership=A.MEMBERSHIP, screened_on="2026-10-31")]
    records += [dict(market="US", symbol=f"F{i:05}", name=f"Filler Issuer {i} Incorporated",
                     membership=A.MEMBERSHIP, screened_on="2026-10-31") for i in range(17260)]
    pq.write_table(pa.Table.from_pylist(records), p)
    (p.parent / "universe_2026-11-01_receipt.json").write_text(json.dumps({
        "written_utc": "20991101T000000Z", "path": "unrelated-original.parquet", "rows_after": 17261}))
    return p


@pytest.mark.parametrize("reported_clock", [None, "2000-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"])
def test_c3_cli_same_count_alternate_proxy_is_an_unverified_observation(tmp_path, unbound_proxy, capsys, reported_clock):
    source_root = tmp_path / "corpus"
    source_root.mkdir()
    write_rows(source_root, [row("Novel Quantum Circuits Incorporated announces results")])
    args = ["--corpus-root", str(source_root), "--date", DAY, "--universe", str(unbound_proxy)]
    if reported_clock:
        cache = tmp_path / "cache.json"
        cache.write_text(json.dumps({"t": reported_clock, "map": {"1365135": "WU"}}))
        args += ["--sec-tickers", str(cache)]
    assert A.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    proxy = output["universe"]
    assert proxy["rows"] == 17261 and proxy["archive_date"] is None
    assert proxy["expected_archive_date"] == "2026-11-01"
    assert proxy["reported_screened_on"] == {"min": "2026-10-31", "max": "2026-10-31"}
    assert proxy["provenance_status"] == "OBSERVED_BYTES_UNVERIFIED_VINTAGE"
    assert proxy["historical_availability_utc"] is None
    assert not proxy["point_in_time_certified"]
    assert output["rows"][0]["mapping_known_at_first_seen"] is None
    c = by_symbol(output["rows"][0], "QCOM")
    assert c["evidence_class"] == "DIRECT"
    assert c["mapping_source_refs"] == ["universe"]
    if reported_clock:
        assert output["sec_cache"]["reported_cache_utc"] == reported_clock
        assert output["sec_cache"]["historical_availability_utc"] is None


def test_c3_sec_mapping_uses_both_inputs_without_unbound_availability(tmp_path, unbound_proxy, capsys):
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pq.read_table(unbound_proxy).to_pylist()
    table[0]["symbol"] = "REVTEST"
    pq.write_table(pa.Table.from_pylist(table), unbound_proxy)
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"t": "2000-01-01T00:00:00Z", "map": {"1365135": "REVTEST"}}))
    source_root = tmp_path / "corpus"
    source_root.mkdir()
    write_rows(source_root, [sec_row()], "sec_edgar_8k_ex99_body")
    assert A.main(["--corpus-root", str(source_root), "--date", DAY, "--universe", str(unbound_proxy),
                   "--sec-tickers", str(cache)]) == 0
    output = json.loads(capsys.readouterr().out)
    c = by_symbol(output["rows"][0], "REVTEST")
    assert c["mapping_source_refs"] == ["universe", "sec_cache"]
    assert c["mapping_known_at_first_seen"] is None
    assert output["rows"][0]["mapping_known_at_first_seen"] is None
    assert output["universe"]["archive_date"] is None
    assert output["sec_cache"]["historical_availability_utc"] is None
