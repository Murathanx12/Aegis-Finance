"""Offline E5 contract and adverse controls; all identifiers are synthetic."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

import pandas as pd
import pytest

from scripts import current_exposure_link as L
from backend.services import owner_decision_view as V
from backend.tests.test_owner_decision_bridge import save, row


def pin(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return L.Pin(path, hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def chain(tmp_path):
    url = "https://www.wsj.com/tech/test-source"
    path, digest, root, locators, rec, items = save(
        tmp_path, [row(url, title="Meta discusses infrastructure plans")]
    )
    page = pin(
        tmp_path / "page.json",
        dict(
            url=url,
            page_kind="article",
            body="PRIVATE_TEXT" * 80,
            title="Meta discusses infrastructure plans",
            first_seen_utc="2026-11-05T06:29:55Z",
        ),
    )
    subject = dict(
        schema="e5-subject-assertion/1",
        source_sha256=locators[0].source_sha256,
        raw_line_sha256=rec["groups"][0]["sources"][0]["proof_witness_sha256"],
        page_sha256=page.sha256,
        issuer_cik="1326801",
        issuer_name="Meta Platforms, Inc.",
        qualification="FULL_ISSUER_SUBJECT",
        observed_at_utc="2026-11-05T07:00:00Z",
        rights="LOCAL_METADATA_ONLY",
    )
    inputs = {
        "master": pin(
            tmp_path / "master.json",
            {"0": dict(cik_str=1326801, ticker="META", title="Meta Platforms, Inc.")},
        ),
        "master_meta": pin(tmp_path / "meta.json", {"n_entries": 1}),
        "proxy_receipt": pin(tmp_path / "proxy_receipt.json", {"rows_after": 1}),
    }
    proxy = tmp_path / "proxy.parquet"
    pd.DataFrame([dict(market="US", symbol="META", exchange="NMS")]).to_parquet(proxy)
    inputs["proxy"] = L.Pin(proxy, hashlib.sha256(proxy.read_bytes()).hexdigest())
    mapping = dict(
        schema="e5-mapping-selection/1",
        observed_at_utc="2026-11-05T07:01:00Z",
        provenance_mode="CURRENT_OBSERVATION_NO_VERIFIED_VINTAGE",
        issuer_candidates=[
            {
                "symbol": "META",
                "identity_level": "ISSUER_CANDIDATE_ONLY",
                "listing_candidates": [
                    dict(
                        market="US",
                        exchange="NMS",
                        symbol="META",
                        membership="UNCONFIRMED_MEMBERSHIP",
                        listing_validity="UNKNOWN",
                    )
                ],
            }
        ],
        input_sha256={k: v.sha256 for k, v in inputs.items()},
        rights="LOCAL_METADATA_ONLY",
        candidates=[
            dict(
                cik="1326801",
                symbol="META",
                issuer_name="Meta Platforms, Inc.",
                **{"class": "Class A Common Stock"},
                venue="NASDAQ",
                asset_class="us_equity",
                conflicts=[],
            )
        ],
    )
    broker = dict(
        schema="aegis_current_paper_asset_witness/v1",
        observed_from_utc="2026-11-05T08:02:41Z",
        observed_until_utc="2026-11-05T08:02:44Z",
        host="paper-api.alpaca.markets",
        positions_count=1,
        positions_response_sha256="a" * 64,
        assets_response_sha256={"META": "b" * 64},
        limits=[],
        selected={
            "META": dict(
                position_present_nonzero=True,
                position_asset_id="PRIVATE-ASSET-123",
                asset_id="PRIVATE-ASSET-123",
                name="Meta Platforms, Inc. Class A Common Stock",
                exchange="NASDAQ",
                asset_class="us_equity",
                status="active",
            )
        },
    )
    kw = dict(
        receipt=L.Pin(path, digest),
        selected_event_id=rec["groups"][0]["event_id"],
        corpus_root=root,
        locator=locators[0],
        page=page,
        subject=pin(tmp_path / "subject.json", subject),
        mapping=pin(tmp_path / "mapping.json", mapping),
        mapping_inputs=inputs,
        broker=pin(tmp_path / "broker.json", broker),
    )
    return kw, subject, mapping, broker


def test_saved_shape_candidate_and_read_only(chain, monkeypatch):
    kw, _, _, _ = chain

    def deny(*a, **k):
        raise AssertionError("network forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    import os

    original = os.open

    def readonly(path, flags, *args, **kwargs):
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", readonly)
    before = {
        p.path: p.path.read_bytes()
        for p in [
            kw["receipt"],
            kw["page"],
            kw["subject"],
            kw["mapping"],
            kw["broker"],
            *kw["mapping_inputs"].values(),
        ]
    }
    out = L.build_link(**kw)
    assert out["status"] == L.CANDIDATE and out["event_time_holding"] == "UNKNOWN"
    assert out["E2_direct_issuer_authority"] is False and out["E3_warning_authority"] is False
    assert out["review_at_utc"] != "2026-11-05T08:02:44Z"
    encoded = json.dumps(out)
    for secret in [
        "PRIVATE-ASSET-123",
        "PRIVATE_TEXT",
        "https:",
        "qty",
        "account_number",
        str(kw["corpus_root"]),
    ]:
        assert secret not in encoded
    assert all(p.read_bytes() == data for p, data in before.items())


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer_cik", "999"),
        ("qualification", "TICKER_TAG"),
        ("qualification", "BODY_MENTION"),
        ("issuer_name", "Binance"),
        ("source_sha256", "c" * 64),
        ("page_sha256", "c" * 64),
        ("observed_at_utc", None),
        ("observed_at_utc", "2026-11-05T07:00:00"),
        ("observed_at_utc", "2099-11-05T07:00:00Z"),
        ("rights", "LICENSED_TEXT"),
    ],
)
def test_subject_false_links_and_clocks(chain, field, value):
    kw, s, _, _ = chain
    s[field] = value
    kw["subject"] = pin(kw["subject"].path, s)
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


@pytest.mark.parametrize(
    "changes",
    [
        {"cik": "999"},
        {"symbol": "XYZ"},
        {"symbol": "TGT"},
        {"symbol": "GOOG"},
        {"symbol": "GOOGL"},
        {"symbol": "NWS"},
        {"symbol": "NWSA"},
        {"class": "ADR"},
        {"venue": "NYSE"},
        {"conflicts": ["TICKER_REUSE"]},
        {"conflicts": ["SQ_TO_XYZ_UNDATED"]},
        {"conflicts": ["DELISTED"]},
    ],
)
def test_identity_collisions(chain, changes):
    kw, _, m, _ = chain
    m["candidates"][0].update(changes)
    kw["mapping"] = pin(kw["mapping"].path, m)
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "inactive"),
        ("exchange", "NYSE"),
        ("asset_class", "ADR"),
        ("name", "Meta Platforms, Inc. Class B Common Stock"),
        ("position_asset_id", "DIFFERENT-ASSET"),
        ("position_present_nonzero", False),
        ("position_present_nonzero", 1),
    ],
)
def test_broker_concordance(chain, field, value):
    kw, _, _, b = chain
    b["selected"]["META"][field] = value
    kw["broker"] = pin(kw["broker"].path, b)
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


@pytest.mark.parametrize(
    "which",
    [
        "receipt",
        "subject",
        "mapping",
        "broker",
        "page",
        "master",
        "proxy",
        "master_meta",
        "proxy_receipt",
    ],
)
def test_hash_tamper(chain, which):
    kw, *_ = chain
    p = kw["mapping_inputs"][which] if which in kw["mapping_inputs"] else kw[which]
    with p.path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


def test_clock_cutoffs_and_history(chain, tmp_path):
    kw, s, m, b = chain
    # After source+mapping qualification, later holdings cannot join an earlier view.
    out = L.build_link(**kw, cutoff_utc="2026-11-05T07:30:00Z")
    assert out["status"] == "HOLDINGS_AFTER_CUTOFF" and out["relation_chain"] == []
    with pytest.raises(V.ViewRefused, match="AFTER_CUTOFF"):
        L.build_link(**kw, cutoff_utc="2026-11-05T06:29:55Z")
    b["observed_until_utc"] = "2099-11-05T08:02:44Z"
    kw["broker"] = pin(kw["broker"].path, b)
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)
    kw["broker"] = None
    kw["history"] = pin(
        tmp_path / "history.json",
        dict(t="2026-11-05T00:04:58Z", positions=[dict(symbol="META", qty="1")]),
    )
    assert L.build_link(**kw)["status"] == "SYMBOL_OVERLAP_ONLY"
    kw["history"] = None
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


def test_duplicates_extra_fields_and_fake_vintage(chain):
    kw, _, m, b = chain
    original = deepcopy(m)
    m["candidates"] *= 2
    kw["mapping"] = pin(kw["mapping"].path, m)
    with pytest.raises(V.ViewRefused, match="AMBIGUOUS"):
        L.build_link(**kw)
    original["provenance_mode"] = "PINNED_CONTENT_PROVENANCE"
    kw["mapping"] = pin(kw["mapping"].path, original)
    with pytest.raises(V.ViewRefused, match="PROVENANCE"):
        L.build_link(**kw)
    kw["subject"].path.write_text('{"schema":1,"schema":2}')
    kw["subject"] = L.Pin(
        kw["subject"].path, hashlib.sha256(kw["subject"].path.read_bytes()).hexdigest()
    )
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


def test_exclusive_external_output_and_bounded_read(chain, tmp_path):
    kw, *_ = chain
    dest = L.write_link(**kw, evidence_dir=tmp_path, filename="e5-output.json")
    before = dest.read_bytes()
    with pytest.raises(V.ViewRefused, match="OUTPUT_EXISTS"):
        L.write_link(**kw, evidence_dir=tmp_path, filename="e5-output.json")
    assert dest.read_bytes() == before
    with pytest.raises(V.ViewRefused):
        L.write_link(
            **kw, evidence_dir=Path(__file__).resolve().parents[2], filename="forbidden.json"
        )
    with pytest.raises(V.ViewRefused, match="BYTE_CAP"):
        L.read(kw["broker"], 1)
    with pytest.raises(V.ViewRefused):
        L.write_link(**kw, evidence_dir=tmp_path, filename="../bad.json")


@pytest.mark.parametrize("ticker,issuer", [("TGT", "Binance"), ("XYZ", "Nasdaq")])
def test_false_binance_tgt_and_nasdaq_xyz_stop_before_holdings(chain, tmp_path, ticker, issuer):
    kw, s, _, b = chain
    sub = tmp_path / "false_chain"
    sub.mkdir()
    path, digest, root, locators, rec, _ = save(
        sub,
        [
            row(
                "https://example.test/false-event",
                title=issuer + " reports a corporate event",
                tickers=[ticker],
            )
        ],
        source_dir="google_news_rss_en_gb",
    )
    kw.update(
        receipt=L.Pin(path, digest),
        selected_event_id=rec["groups"][0]["event_id"],
        corpus_root=root,
        locator=locators[0],
    )
    s.update(
        source_sha256=locators[0].source_sha256,
        raw_line_sha256=rec["groups"][0]["sources"][0]["proof_witness_sha256"],
        issuer_name=issuer,
        qualification="TICKER_TAG",
    )
    kw["subject"] = pin(kw["subject"].path, s)
    # Even a real same-ID position cannot supply missing subject authority.
    b["selected"] = {ticker: dict(b["selected"]["META"], exchange="NYSE")}
    b["assets_response_sha256"] = {ticker: "b" * 64}
    kw["broker"] = pin(kw["broker"].path, b)
    with pytest.raises(V.ViewRefused, match="ISSUER_SUBJECT_REQUIRED"):
        L.build_link(**kw)


@pytest.mark.parametrize(
    "which",
    [
        "receipt",
        "page",
        "subject",
        "mapping",
        "broker",
        "master",
        "proxy",
        "master_meta",
        "proxy_receipt",
    ],
)
def test_missing_inputs_refuse(chain, which):
    kw, *_ = chain
    p = kw["mapping_inputs"][which] if which in kw["mapping_inputs"] else kw[which]
    p.path.unlink()
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


def test_self_rehashed_master_collision_and_proxy_venue(chain):
    kw, _, m, _ = chain
    master = {
        "0": dict(cik_str=1326801, ticker="META", title="Meta Platforms, Inc."),
        "1": dict(cik_str=999, ticker="META", title="Another issuer"),
    }
    kw["mapping_inputs"]["master"] = pin(kw["mapping_inputs"]["master"].path, master)
    m["input_sha256"]["master"] = kw["mapping_inputs"]["master"].sha256
    kw["mapping"] = pin(kw["mapping"].path, m)
    with pytest.raises(V.ViewRefused, match="MASTER_COLLISION"):
        L.build_link(**kw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("observed_from_utc", None),
        ("observed_from_utc", "2026-11-05T08:02:45Z"),
        ("observed_until_utc", "2026-11-05T08:12:44Z"),
        ("account_number", "PRIVATE"),
    ],
)
def test_broker_clock_and_extra_fields(chain, field, value):
    kw, _, _, b = chain
    b[field] = value
    kw["broker"] = pin(kw["broker"].path, b)
    with pytest.raises(V.ViewRefused):
        L.build_link(**kw)


def test_wrong_page_and_new_source_version(chain):
    kw, *_ = chain
    p = json.loads(kw["page"].path.read_text())
    p["url"] = "https://www.wsj.com/tech/later-sibling"
    kw["page"] = pin(kw["page"].path, p)
    s = json.loads(kw["subject"].path.read_text())
    s["page_sha256"] = kw["page"].sha256
    kw["subject"] = pin(kw["subject"].path, s)
    with pytest.raises(V.ViewRefused, match="PAGE_IDENTITY_MISMATCH"):
        L.build_link(**kw)
