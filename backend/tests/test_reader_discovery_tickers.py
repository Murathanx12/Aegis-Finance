"""Discovery lineage must survive without becoming article issuer metadata."""
import json

import pytest

from backend.tests.test_reader_pool import FakeDriver, _pool, _stored, ledger  # noqa: F401


@pytest.mark.parametrize("kind,via,lane", [
    ("article", "stock_links", "marketwatch:stock"),
    ("article", "related", "related"),
    ("article", "browse", "browse"),
    ("article", "direct", "direct"),
    ("stock_text", "direct", "marketwatch:stock"),
    ("front_text", "front", "front:marketwatch"),
])
def test_pool_never_promotes_discovery_ticker_even_for_stock_or_direct_queue(ledger, kind, via, lane):
    url = "https://www.marketwatch.com/story/qualcomm-synthetic-12345678"
    driver = FakeDriver({url: {"title": "QUALCOMM announces a satellite update",
                              "text": "QUALCOMM announces a satellite update. " * 35
                                      + " Sidebar stock quote: Apple (AAPL)."}})
    pool, _ = _pool(ledger, driver, fronts=[], names=("META", "QCOM", "AAPL"))
    it = {"kind": kind, "site": "marketwatch", "host": "marketwatch.com", "lane": lane,
          "ticker": "META", "url": url, "parent_url": "https://www.marketwatch.com/investing/stock/meta",
          "via": via, "section": "stock", "key": "synthetic", "depth": 1}
    pool.process(it, 0)
    stored = _stored(ledger)[url]
    assert stored["reached_by"]["ticker"] == "META"
    assert stored["reached_by"]["via"] == via
    # This candidate is allowed to remain a full-page mention, including
    # sidebar noise. It is neither article tickers nor event issuer evidence.
    assert "AAPL" in stored["tickers_named"]
    paths = list((ledger / "news_corpus" / "dj_reader_marketwatch").glob("*.jsonl"))
    assert len(paths) == 1
    rows = [json.loads(line) for line in paths[0].read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["tickers"] == []
    assert not driver.tabs
