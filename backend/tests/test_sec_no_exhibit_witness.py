"""CH-05 R5 (ported from the runtime): an 8-K whose COMPLETE index lists no
Exhibit 99 is retired by a stored, re-verified witness instead of being
re-fetched by every bounded run forever. Absence is proved by a strict schema,
never by parser silence; a missing or altered witness puts the work back.
Offline: the network door is a fake that returns synthetic SEC-shaped bytes."""
from __future__ import annotations

import html

import pytest

from scripts import news_pull as n

SOURCE = "sec_edgar_8k_ex99_body"
ACC = "0000950142-26-002986"
FOLDER = ACC.replace("-", "")
BASE = f"https://www.sec.gov/Archives/edgar/data/1/{FOLDER}"
INDEX_URL = f"{BASE}/{ACC}-index-headers.html"


def entry():
    return {"url": f"{BASE}/{ACC}-index.htm", "title": ACC, "entity_tags": ["8-K:8.01"]}


def index_page(*docs: tuple[str, str], declared: int | None = None, extra: str = "") -> bytes:
    body = "".join(f"<DOCUMENT>\n<TYPE>{t}\n<SEQUENCE>{k + 1}\n<FILENAME>{f}\n</DOCUMENT>\n"
                   for k, (t, f) in enumerate(docs))
    sgml = (f"<SEC-DOCUMENT>{ACC}.txt : 20261110\n<SEC-HEADER>{ACC}.hdr.sgml : 20261110\n"
            f"ACCESSION NUMBER:\t\t{ACC}\n"
            f"PUBLIC DOCUMENT COUNT:\t\t{len(docs) if declared is None else declared}\n"
            f"</SEC-HEADER>\n{body}</SEC-DOCUMENT>")
    return (f"<html><head><title>{ACC}</title></head><body>{extra}<pre>{html.escape(sgml)}</pre>"
            f"</body></html>").encode("utf-8")


def served(raw: bytes, *, url: str = INDEX_URL, length: int | None = None, ctype="text/html") -> bytes:
    return n.HttpBytes(raw, {"status": 200, "url": url, "content_type": ctype,
                             "content_length": str(len(raw) if length is None else length)})


NO_EX99 = index_page(("8-K", "form8k.htm"), ("EX-10.1", "ex101.htm"))


def test_a_complete_index_without_ex99_is_a_witness():
    proof = n.sec_no_exhibit_witness(served(NO_EX99), ACC, INDEX_URL)
    assert proof and proof["public_document_count"] == 2
    assert proof["schema"] == "sec_complete_index_no_ex99/1"


@pytest.mark.parametrize("case", ["ex99", "count", "length", "url", "ctype", "challenge", "plain_bytes"])
def test_anything_short_of_a_complete_index_is_no_proof(case):
    raw, kw = NO_EX99, {}
    if case == "ex99":
        raw = index_page(("8-K", "form8k.htm"), ("EX-99.1", "pr.htm"))
    elif case == "count":
        raw = index_page(("8-K", "form8k.htm"), declared=3)
    elif case == "length":
        kw = {"length": len(NO_EX99) - 1}                          # a truncated response
    elif case == "url":
        kw = {"url": INDEX_URL.replace("www.sec.gov", "sec.example")}
    elif case == "ctype":
        kw = {"ctype": "application/octet-stream"}
    elif case == "challenge":
        raw = index_page(("8-K", "form8k.htm"), extra="Request Rate Threshold Exceeded")
    blob = raw if case == "plain_bytes" else served(raw, **kw)
    assert n.sec_no_exhibit_witness(blob, ACC, INDEX_URL) is None


class Context(n.RunContext):
    def __init__(self, payload):
        super().__init__(resume=True, paced=False)
        self.payload, self.urls = payload, []

    def http_get_via(self, src, url, headers=None):
        self.urls.append(url)
        return self.payload.get(url.rsplit("/", 1)[-1], b"feed")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(n._config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(n.entities, "tables", lambda: None)
    monkeypatch.setattr(n.entities, "resolve", lambda *a, **k: type("R", (), {"tickers": (), "how": {}})())
    monkeypatch.setattr(n, "parse_edgar_atom", lambda raw: [entry()])
    return tmp_path


def test_a_verified_negative_retires_the_filing_and_is_not_refetched(corpus):
    first = n.pull_source(SOURCE, Context({f"{ACC}-index-headers.html": served(NO_EX99)}))
    assert first["sec_progress"]["pending_filings"] == 0
    assert first["sec_progress"]["no_exhibit_verified"] == 1
    assert ACC in n._read_cursor(SOURCE)["sec_no_exhibit"]
    again = Context({})
    n.pull_source(SOURCE, again)
    assert again.urls == [again.urls[0]] and not again.urls[0].endswith("-index-headers.html")


def test_an_altered_witness_puts_the_filing_back_to_work(corpus):
    n.pull_source(SOURCE, Context({f"{ACC}-index-headers.html": served(NO_EX99)}))
    witness = next((corpus / "optimus" / "news_corpus" / "_sec_index_witnesses" / ACC).glob("*.html"))
    witness.write_bytes(witness.read_bytes() + b" ")
    ctx = Context({f"{ACC}-index-headers.html": b"<html>temporarily unavailable</html>"})
    rec = n.pull_source(SOURCE, ctx)
    assert any(u.endswith(f"{ACC}-index-headers.html") for u in ctx.urls)
    assert rec["sec_progress"]["pending_filings"] == 1
    assert ACC not in n._read_cursor(SOURCE)["sec_no_exhibit"]


def test_without_proof_the_filing_stays_pending_as_before(corpus):
    rec = n.pull_source(SOURCE, Context({f"{ACC}-index-headers.html": served(NO_EX99, length=1)}))
    assert rec["sec_progress"]["pending_filings"] == 1
    assert rec["sec_progress"]["no_exhibit_verified"] == 0
