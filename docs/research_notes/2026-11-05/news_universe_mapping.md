# News/universe mapping candidate - 5 November 2026

Status: Astra r1 audit **FAIL (C1-C3)**; narrow reader correction PASS. This
follow-up awaits independent re-review; not pushed, integrated or activated. Base:
`7fe85006406f2e9cf56cda15e49da6d53aa43214`. No digest or decision was run.
This is an engineering audit under [CANON](../../CANON.md), not an alpha claim.

## Three distinct universe layers

| Layer | Saved coverage | Evidence boundary |
|---|---:|---|
| Rolling reader discovery | 133 names | Coordinator-reported `dowjones_pull.rolling_names()`, latest wide file + books; no active-pool expansion attempted. |
| Tracker / issuer CSV | 3,056 symbols | Agent B's saved inspection; distinct from the reader's list and the global proxy. Not verified fresh whole-market coverage. |
| Contest proxy, Nov 1 selection | 17,261 market+symbol keys | Observed parquet; embedded screened Oct 31, historical vintage unverified. All `UNCONFIRMED_MEMBERSHIP`; no WLS claim. |

Held symbols are an optional **supplied safe-list input**; no broker/private files
are read or holdings/amounts embedded. Agent B's saved count of 31 supersedes
earlier five-name observations; neither establishes current ownership/relevance.

## CLI and evidence contract

[CLI](../../../scripts/news_universe_audit.py) reads dated, one-level
`news_corpus/<source>/<date>.jsonl` using actual registry fields; it does not
read raw full-text Dow Jones JSON or call its collectors. Requires pyarrow.
Run from this candidate worktree, with `$data` pointing at supplied local data:

```powershell
$data = 'C:\Users\mrthn\aegis-finance\backend\data\optimus'
python -B -m scripts.news_universe_audit --corpus-root "$data/news_corpus" `
  --date 2026-11-05 --universe "$data/contest/universe/universe_2026-11-01.parquet" `
  --sec-tickers "$data/edgar_8k/company_tickers.json" --source sec_edgar_8k_ex99_body
```

Omit `--source` for all supported sources on that explicit date. Optional
`--held-safe-list safe.json` accepts only an array such as `["US:QCOM","SPY"]`;
`--held-as-of <timezone-aware-clock>` supplies its separate snapshot clock.
Outside-proxy held instruments remain visible; no constituent look-through.

Schema v2 includes relative source file, physical line, exact-line SHA-256 **including
newline**, bounded file-prefix SHA-256, separate first-seen/publication clocks,
candidate symbols, reason codes, and filing groups. No title, body, URL,
private identity, sentiment, forecast, or portfolio action is emitted.
`digest_ran=false`, `decision_ran=false`, `spend_units=0` are explicit.

`DIRECT` means **issuer identification only**: complete unique multiword issuer
name in the title, or SEC URL/tag CIK/accession plus local cache agreement.
It never certifies a security/event relation: that field remains REVIEW_REQUIRED.
Bare symbols, shortened names, inherited tags, body/sidebar mentions, multiple issuers,
share classes and market ambiguity cannot establish DIRECT. Analyst Estimates
pages are `NO_EVENT_RECURRING_ESTIMATES`; other headlines are EVENT_UNASSESSED.
SEC groups are filing candidates, not a count of typed economic events.

The SEC master preserves CIK-to-many-symbol candidates; inverse symbol-to-CIK
conflicts refuse after CIK normalization. The `official` cache remains explicitly
incomplete for share classes. SEC URL/tags must agree; accession prefixes may
name filing agents. Document/sibling clocks and distinct accessions survive.
Each candidate's `mapping_source_refs` identifies its actual mapping inputs.
Both snapshots are `OBSERVED_BYTES_UNVERIFIED_VINTAGE`, with observed hashes/clocks;
`reported_cache_utc` and `reported_screened_on` never certify availability.
`archive_date` and every `mapping_known_at_first_seen` remain null, even for
same-count path overrides. `expected_archive_date` is an input constraint only.
No verified-manifest interface is provided; sibling receipts do not date bytes.

Default ceilings: 10,000 rows, 64 files, 256 directory entries, 256 KiB/line,
32 MiB news, 16 MiB serialized output, 32 candidates/row, 30 seconds cooperative
deadline including metadata reads. Parquet is capped at 16 MiB on disk / 64 MiB
expanded metadata size and 20,000 rows (exact archive count also checked).
Memory is bounded by those limits plus Python/Arrow overhead. Errors/limits/partial
lines return sanitized REFUSED JSON, exit 2; success exits 0. Later appends are
excluded. This is not an atomic corpus snapshot or point-in-time holdings replay.

## Verification and remaining gap

Fourteen follow-up regressions cover C1 Partners/full-name controls, C2 inverse
CIK conflicts, and C3 unrelated clocks/same-count alternate proxies. Existing
mistag, homonym, reference-page, filing, redaction and refusal checks remain.
Read-only smoke: Nov 4, 1,577 rows / 101 estimates pages; reported META, GOOGL,
PSNL and GEV mistags all REVIEW_REQUIRED. Follow-up Nov 5 capture: 33 saved rows, including 21 SEC
exhibits / 18 filing groups; tagless WU/KVYO/OTF recovered, FSLY 3 documents in
2 filings, CCI 2 in 1. Counts are captured observations, not future freshness.
Weather regression is synthetic; its reported real producing row is unresolved.

The unchanged reader fix keeps queue tickers out of article tags for all pool
reads, preserving `reached_by.ticker`. Full-page `tickers_named` remains a mention
heuristic. Historical raw records are untouched; no active reader was restarted.

Follow-up: 55 audit/reader regression checks pass. Broader run: 145 pass, one
existing fake-client guard fails with zero fake opens. Astra r1 localized that
environment-sensitive failure to a shared lease before `_read_article`; source unchanged.

```powershell
$env:AEGIS_IGNORE_DOTENV='1'
python -B -m pytest backend/tests/test_news_universe_audit.py backend/tests/test_reader_discovery_tickers.py backend/tests/test_reader_pool.py backend/tests/test_reader_browse_lane.py backend/tests/test_web_reader_publication_clock.py -q --timeout=30 -p no:cacheprovider
```

Unresolved: `world_digest.collect` reads raw full-page `tickers_named`;
`type_row` and `_ticker_in_text` admit mentions without subject/body segmentation.
A synthetic Qualcomm title + AAPL sidebar reproduces admission. Digest semantics,
spend preflight, forecasts, decisions and consumers remain uncertified/unrepaired; article-context admission needs separate review.
