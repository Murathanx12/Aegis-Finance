"""Offline E4 selected-event bridge, with hook-shaped raw containers."""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket

import pytest

from backend.services import owner_decision_bridge as B
from backend.services import owner_decision_view as V
from backend.services import provisional_event_review as E
from scripts import world_digest_provisional as H


FIRST = "2026-11-05T06:29:55+00:00"
PUBLISHED = "2026-11-05T03:11:00+00:00"
CUTOFF = "2026-11-05T09:00:00Z"
REVIEW = "2026-11-05T09:20:00Z"
WITNESS = "a" * 64


def sha(data):
    return hashlib.sha256(data).hexdigest()


def row(url, *, first=FIRST, published=PUBLISHED, title="Distinct source event title",
        body="BODY_SENTINEL" * 40, tickers=None):
    return {"url": url, "first_seen_utc": first, "published_utc": published,
            "title": title, "body": body, "tickers": tickers or []}


def item(raw, source_dir, *, event_key=None):
    payload = raw.rstrip(b"\r\n")
    entry = json.loads(payload)
    identity = H.WD.norm_url(entry["url"]) or str(entry.get("raw_id") or "")
    source_key = "source:" + sha(identity.encode())[:40]
    first = H._utc(entry["first_seen_utc"]).isoformat()
    published = H._utc(entry["published_utc"]).isoformat() if entry.get("published_utc") else None
    kind = ("FILING" if source_dir == "sec_edgar_8k_ex99_body" else
            "HEADLINE" if source_dir == "google_news_rss_en_gb" else "ARTICLE")
    event_key = event_key or H._event_key(identity, filing=kind == "FILING", raw_url=entry["url"])
    source = E.SourceItem(source_key, event_key, payload, first, first, published,
                          E.SourceProof(sha(payload), first, sha(raw)), kind)
    return source


def receipt(items, *, edges=(), held=None):
    return E.build_review(sources=items, issuer_edges=edges, holdings=held,
                          review_time_utc=REVIEW, source_cutoff_utc=CUTOFF,
                          input_complete=False, upstream_state="BUDGET_REFUSED",
                          upstream_exit_code=2)


def save(tmp_path, rows, *, source_dir="dj_reader_wsj", receipt_obj=None):
    root = tmp_path / "news_corpus"
    folder = root / source_dir
    folder.mkdir(parents=True)
    container = folder / "2026-11-05.jsonl"
    raw_rows = [json.dumps(entry, separators=(",", ":")).encode() + b"\n" for entry in rows]
    data = b"".join(raw_rows)
    container.write_bytes(data)
    items = [item(raw, source_dir) for raw in raw_rows]
    rec = receipt_obj or receipt(items)
    rec_path = tmp_path / "receipt.json"
    rec_bytes = E._canonical(rec) + b"\n"
    rec_path.write_bytes(rec_bytes)
    pins = [B.RowLocator(source.source_key, sha(source.payload),
                         f"{source_dir}/2026-11-05.jsonl", sha(data), i)
            for i, source in enumerate(items, 1)]
    return rec_path, sha(rec_bytes), root, pins, rec, items


def call(rec_path, digest, root, locators, event_id, **kw):
    return B.build_selected_event_view(receipt_path=rec_path, receipt_sha256=digest,
                                       selected_event_id=event_id, corpus_root=root,
                                       locators=locators, **kw)


def rewrite(path, rec):
    body = {key: value for key, value in rec.items() if key != "receipt_id"}
    rec["receipt_id"] = sha(E._canonical(body))
    data = E._canonical(rec) + b"\n"
    path.write_bytes(data)
    return sha(data)


def two_rows():
    return [row("https://www.wsj.com/tech/ai/a", tickers=["META"],
                title="A false sidebar ticker tag appears"),
            row("https://www.wsj.com/tech/ai/b", tickers=["TGT"],
                title="A separate infrastructure event appears")]


def test_exact_selected_group_and_replay_do_not_promote_tags(tmp_path):
    path, digest, root, pins, rec, items = save(tmp_path, two_rows())
    assert len(rec["groups"]) == 2
    selected_id = E._stable_id("event", items[0].event_key)
    first = call(path, digest, root, [pins[0]], selected_id)
    assert first == call(path, digest, root, [pins[0]], selected_id)
    assert first["decision"] == "NO_CHANGE_WITH_REASON"
    assert first["global_context_scope"] == "WHOLE_E2_RECEIPT"
    assert first["coverage"]["status"] == "PARTIAL"
    assert first["upstream_digest"]["state"] == "BUDGET_REFUSED"
    assert first["upstream_digest_authority"] == "CALLER_SUPPLIED_NOT_TASK_ATTESTED"
    assert first["owner_decision"] == "UNOBSERVED"
    assert first["delivery"] == "NOT_ATTEMPTED"
    display = json.dumps(first)
    assert not any(value in display for value in ("BODY_SENTINEL", "META", "TGT", "wsj.com",
                                                   str(root), "relative_corpus_path", ".jsonl",
                                                   "DIRECT_ISSUER"))


def test_positive_root_from_other_group_does_not_promote_selection(tmp_path):
    rows = two_rows()
    raw = [json.dumps(entry, separators=(",", ":")).encode() + b"\n" for entry in rows]
    items = [item(raw_entry, "dj_reader_wsj") for raw_entry in raw]
    edge = E.IssuerEdge(items[1].source_key, sha(items[1].payload), "cik:111111", "US:XYZ",
                        "INDIRECT_CANDIDATE", "CALLER_DESCRIBED_MECHANISM",
                        items[1].first_seen_utc, WITNESS)
    held = E.HoldingsSnapshot(items[1].first_seen_utc, items[1].first_seen_utc,
                              ("US:XYZ",), WITNESS, True)
    rec = receipt(items, edges=[edge], held=held)
    path, digest, root, pins, _, _ = save(tmp_path, rows, receipt_obj=rec)
    assert rec["decision"] == "REVIEW_EXPOSURE"
    selected = call(path, digest, root, [pins[0]], E._stable_id("event", items[0].event_key))
    assert selected["decision"] == "NO_CHANGE_WITH_REASON"
    assert selected["caller_supplied_indirect_symbol_matches"] == []
    assert selected["holdings"]["authority"] == "CALLER_SUPPLIED_NOT_VERIFIED"


def test_sec_exhibits_group_by_cik_plus_accession(tmp_path):
    acc = "000119312526447234"
    rows = [row(f"https://www.sec.gov/Archives/edgar/data/1365135/{acc}/wu-ex99_{n}.htm",
                title=f"Western Union exhibit number {n}") for n in (1, 2)]
    rows.append(row(f"https://www.sec.gov/Archives/edgar/data/1835830/{acc}/kvyo-ex99.htm",
                    title="Klaviyo separate CIK exhibit"))
    path, digest, root, pins, rec, items = save(tmp_path, rows,
                                                source_dir="sec_edgar_8k_ex99_body")
    assert len(rec["groups"]) == 2
    assert items[0].event_key == items[1].event_key != items[2].event_key
    selected = call(path, digest, root, pins[:2], E._stable_id("event", items[0].event_key))
    assert len(selected["sources"]) == 2
    assert selected["decision"] == "NO_CHANGE_WITH_REASON"
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, pins[:2], E._stable_id("event", items[2].event_key))


@pytest.mark.parametrize("change", [
    lambda pins: [],
    lambda pins: pins + pins,
    lambda pins: [replace(pins[0], line_number=2)],
    lambda pins: [replace(pins[0], container_sha256="0" * 64)],
    lambda pins: [replace(pins[0], source_key="source:" + "0" * 40)],
    lambda pins: [replace(pins[0], relative_corpus_path="../escape.jsonl")],
    lambda pins: [replace(pins[0], relative_corpus_path="dj_reader_wsj/2026-11-04.jsonl")],
])
def test_wrong_locator_or_line_refuses(tmp_path, change):
    path, digest, root, pins, _, items = save(tmp_path, two_rows())
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, change([pins[0]]), E._stable_id("event", items[0].event_key))


def test_mutated_unselected_group_refuses_before_selection(tmp_path):
    path, _, root, pins, rec, items = save(tmp_path, two_rows())
    other = next(group for group in rec["groups"] if group["event_key"] != items[0].event_key)
    other["sources"][0]["first_seen_utc"] = "2026-11-06T00:00:00Z"
    digest = rewrite(path, rec)
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, [pins[0]], E._stable_id("event", items[0].event_key))


def test_duplicate_event_or_source_id_refuses(tmp_path):
    path, _, root, pins, rec, items = save(tmp_path, two_rows())
    rec["groups"].append(rec["groups"][0].copy())
    digest = rewrite(path, rec)
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, [pins[0]], E._stable_id("event", items[0].event_key))


def test_self_rehashed_duplicate_source_id_across_groups_refuses(tmp_path):
    path, _, root, pins, rec, items = save(tmp_path, two_rows())
    first, second = rec["groups"]
    first_source = first["sources"][0]
    second_source = second["sources"][0]
    second_source["source_id"] = first_source["source_id"]
    second_source["version_id"] = sha(
        f"version\0{second_source['source_id']}\0{second_source['source_sha256']}".encode())
    digest = rewrite(path, rec)
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, [pins[0]], E._stable_id("event", items[0].event_key))


def test_more_than_hook_source_cap_refuses(tmp_path):
    items = []
    for number in range(H.MAX_SOURCES + 1):
        entry = row(f"https://www.wsj.com/tech/ai/article-{number}")
        raw = json.dumps(entry, separators=(",", ":")).encode() + b"\n"
        items.append(item(raw, "dj_reader_wsj"))
    rec = E.build_review(sources=items, issuer_edges=[], holdings=None,
                         review_time_utc=REVIEW, source_cutoff_utc=CUTOFF,
                         input_complete=False, max_sources=H.MAX_SOURCES + 1)
    rec_path = tmp_path / "receipt.json"
    data = E._canonical(rec) + b"\n"
    rec_path.write_bytes(data)
    root = tmp_path / "news_corpus"
    root.mkdir()
    with pytest.raises(V.ViewRefused, match="SOURCE_COUNT_CAP"):
        call(rec_path, sha(data), root, [], E._stable_id("event", items[0].event_key))


def test_changed_selected_bytes_and_later_append(tmp_path):
    path, digest, root, pins, _, items = save(tmp_path, two_rows())
    selected = E._stable_id("event", items[0].event_key)
    container = root / pins[0].relative_corpus_path
    container.write_bytes(container.read_bytes() + b'{"unrelated":true}\n')
    refreshed = replace(pins[0], container_sha256=sha(container.read_bytes()))
    assert call(path, digest, root, [refreshed], selected)["event_id"] == selected
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, [pins[0]], selected)
    container.write_bytes(container.read_bytes().replace(b"BODY_SENTINEL", b"BODY_CHANGED_", 1))
    tampered = replace(pins[0], container_sha256=sha(container.read_bytes()))
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, [tampered], selected)


def test_redirected_parent_and_file_cap_refuse(tmp_path):
    path, digest, root, pins, _, items = save(tmp_path, two_rows())
    selected = E._stable_id("event", items[0].event_key)
    link_root = tmp_path / "linked" / "news_corpus"
    link_root.parent.mkdir()
    try:
        link_root.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pass
    else:
        with pytest.raises(V.ViewRefused):
            call(path, digest, link_root, [pins[0]], selected)
    container = root / pins[0].relative_corpus_path
    container.write_bytes(container.read_bytes() + b"X" * (H.MAX_FILE_BYTES + 1))
    oversized = replace(pins[0], container_sha256=sha(container.read_bytes()))
    with pytest.raises(V.ViewRefused, match="BYTE_CAP"):
        call(path, digest, root, [oversized], selected)


def test_wrong_receipt_hash_event_and_no_output_file(tmp_path):
    path, digest, root, pins, _, items = save(tmp_path, two_rows())
    before = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(V.ViewRefused):
        call(path, "0" * 64, root, [pins[0]], E._stable_id("event", items[0].event_key))
    with pytest.raises(V.ViewRefused, match="EVENT_NOT_FOUND"):
        call(path, digest, root, [pins[0]], "0" * 64)
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_exact_full_page_json_requires_null_line_and_day(tmp_path):
    root = tmp_path / "news_corpus"
    folder = root / "dowjones" / "wsj" / "2026-11-05"
    folder.mkdir(parents=True)
    page = folder / "article.json"
    entry = row("https://www.wsj.com/tech/ai/full-page", body="PAGE_BODY_SENTINEL" * 30)
    payload = json.dumps(entry, separators=(",", ":")).encode()
    page.write_bytes(payload)
    first = H._utc(entry["first_seen_utc"]).isoformat()
    source_key = "source:" + sha(H.WD.norm_url(entry["url"]).encode())[:40]
    event_key = H._event_key(H.WD.norm_url(entry["url"]))
    item = E.SourceItem(source_key, event_key, payload, first, first,
                        H._utc(entry["published_utc"]).isoformat(),
                        E.SourceProof(sha(payload), first, sha(payload)), "ARTICLE")
    rec = receipt([item])
    rec_path = tmp_path / "receipt.json"
    rec_bytes = E._canonical(rec) + b"\n"
    rec_path.write_bytes(rec_bytes)
    pin = B.RowLocator(source_key, sha(payload), "dowjones/wsj/2026-11-05/article.json",
                       sha(payload), None)
    selected = E._stable_id("event", event_key)
    assert call(rec_path, sha(rec_bytes), root, [pin], selected)["event_id"] == selected
    with pytest.raises(V.ViewRefused):
        call(rec_path, sha(rec_bytes), root, [replace(pin, line_number=1)], selected)
    with pytest.raises(V.ViewRefused):
        call(rec_path, sha(rec_bytes), root,
             [replace(pin, relative_corpus_path="dowjones/wsj/2026-11-04/article.json")], selected)


def test_superseded_row_cannot_replace_selected_version(tmp_path):
    old = row("https://www.wsj.com/tech/ai/a", body="OLD_BODY_SENTINEL" * 40)
    new = row("https://www.wsj.com/tech/ai/a", body="NEW_BODY_SENTINEL" * 40,
              first="2026-11-05T07:00:00+00:00")
    path, digest, root, pins, rec, items = save(tmp_path, [old, new])
    selected = E._stable_id("event", items[0].event_key)
    assert len(rec["groups"]) == 1
    assert rec["groups"][0]["sources"][0]["source_sha256"] == pins[1].source_sha256
    assert call(path, digest, root, [pins[1]], selected)["event_id"] == selected
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, [pins[0]], selected)
    wrong_line = replace(pins[1], line_number=1)
    with pytest.raises(V.ViewRefused):
        call(path, digest, root, [wrong_line], selected)


def test_sec_filing_without_exact_archive_accession_refuses(tmp_path):
    rows = [row("https://www.sec.gov/Archives/edgar/data/1365135/not-an-accession/ex99.htm",
                title="Western Union filing with malformed accession")]
    path, digest, root, pins, _, items = save(tmp_path, rows,
                                               source_dir="sec_edgar_8k_ex99_body")
    with pytest.raises(V.ViewRefused, match="INVALID_SEC_ACCESSION"):
        call(path, digest, root, pins, E._stable_id("event", items[0].event_key))


def test_bridge_uses_read_opens_only_and_never_connects(tmp_path, monkeypatch):
    path, digest, root, pins, _, items = save(tmp_path, two_rows())
    files = [path, root / pins[0].relative_corpus_path]
    before = {str(file): sha(file.read_bytes()) for file in files}
    real_open = os.open

    def guarded_open(filename, flags, *args, **kwargs):
        assert flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC) == 0
        return real_open(filename, flags, *args, **kwargs)

    def deny_connect(*_args, **_kwargs):
        raise AssertionError("NETWORK_CALLED")

    monkeypatch.setattr(V.os, "open", guarded_open)
    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    selected = E._stable_id("event", items[0].event_key)
    call(path, digest, root, [pins[0]], selected)
    assert before == {str(file): sha(file.read_bytes()) for file in files}
