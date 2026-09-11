# Lane N parser fixtures

One small sample per source, used by `backend/tests/test_news_pull.py` so every
parser is exercised offline. **What these are, exactly:**

The 2026-09-11 lane-N probe
(`docs/research_notes/2026-09-11/lane_n/`) saved its results as PARSED rows —
`{title, link, pubDate, ...}` JSONL — not as raw payloads. These fixtures are
therefore *reconstructions*: the **field values are real** (titles, links,
accession numbers, timestamps, `seendate` strings, `sourcecountry` values, all
copied verbatim out of `probes/*.jsonl`), wrapped in the document envelope each
provider actually serves. They are cut to 2-3 items each.

Saying that plainly matters, because a fixture that is only *believed* to be a
byte-for-byte capture is a test that passes for the wrong reason. What each one
pins is the **shape** the probe found the hard way:

| file | pins |
|---|---|
| `google_news_rss_en_hk.xml` | RSS 2.0: `<item>` under `<channel>`, RFC 822 `pubDate` |
| `nikkei_asia_rss.xml` | RSS **1.0 / RDF** — `{http://purl.org/rss/1.0/}item`, `dc:date`. A namespace-naive `.//item` returns ZERO here, which is what the probe's first attempt did |
| `sec_edgar_getcurrent.atom` | `action=getcurrent` Atom, with a real Item 2.02 (Kroger) so the `8-K:2.02` tag has a true positive, and a real Item 8.01 (Exelixis) so it has a true negative |
| `gdelt_doc.json` | `articles[]` with `seendate` as `YYYYMMDDTHHMMSSZ`, Korean-language rows from `sourcecountry:KS` |
| `reddit_algotrading.atom` | Reddit's `.rss` is **Atom**, not RSS 2.0 |
| `alpaca_news.json` | the `news[]` + `next_page_token` envelope, `created_at`, `symbols[]` — reconstructed from the documented schema, since no key resolved in this environment to probe it |
| `yfinance_ticker_news.json` | the nested `{id, content:{title, summary, pubDate, canonicalUrl, provider}}` shape |

The Alpaca fixture is the one with no probe behind it at all — the keys are
absent here — and its row therefore says so rather than implying a capture.
