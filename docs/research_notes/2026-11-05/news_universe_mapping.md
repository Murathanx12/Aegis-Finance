# News/universe mapping candidate - 5 November 2026

Status: local candidate for **Astra's independent review**, not integrated,
pushed, deployed, or adopted by the running reader. Base: origin/main
`7fe85006406f2e9cf56cda15e49da6d53aa43214`. No digest or decision was run.
This is an engineering audit under [CANON](../../CANON.md), not an alpha claim.

## Three distinct universe layers

| Layer | Saved coverage | Evidence boundary |
|---|---:|---|
| Rolling reader discovery | 133 names | Coordinator-reported `dowjones_pull.rolling_names()`, latest wide file + books; no active-pool expansion attempted. |
| Tracker / issuer CSV | 3,056 symbols | Agent B's saved inspection; distinct from the reader's list and the global proxy. Not verified fresh whole-market coverage. |
| Contest proxy, Nov 1 archive | 17,261 market+symbol keys | Direct parquet smoke; all `UNCONFIRMED_MEMBERSHIP`, screened Oct 31. No official WLS membership claim. |

Held symbols are a fourth, optional **supplied safe-list input**, never read
from broker/private identity files. No holdings/amounts are embedded here.
Agent B's newest saved snapshot count is 31; earlier five-name observations
are superseded. This does not establish current ownership or event relevance.

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

JSON includes relative source file, physical line, exact-line SHA-256 **including
newline**, bounded file-prefix SHA-256, separate first-seen/publication clocks,
candidate symbols, reason codes, and filing groups. No title, body, URL,
private identity, sentiment, forecast, or portfolio action is emitted.
`digest_ran=false`, `decision_ran=false`, `spend_units=0` are explicit.

`DIRECT` means **issuer identification only**: distinctive unique archived
issuer name in the title, or SEC URL/tag CIK/accession plus local cache agreement.
It never certifies a security/event relation: that field remains REVIEW_REQUIRED.
Bare symbols, inherited tags, body/sidebar `tickers_named`, multiple issuers,
share classes and market ambiguity cannot establish DIRECT. Analyst Estimates
pages are `NO_EVENT_RECURRING_ESTIMATES`; other headlines are EVENT_UNASSESSED.
SEC groups are filing candidates, not a count of typed economic events.

The complete `edgar_8k` SEC master preserves CIK-to-many-symbol candidates;
the alternative `official` cache is explicitly labelled incomplete for share
classes. Neither is alias history/PIT certification. Missing cache clocks stay
unknown. Validated SEC paths and tags must agree; accession prefixes may name
filing agents. Document hashes, sibling clocks and distinct accessions survive;
duplicate evidence rows do not inflate unique document counts.

Default ceilings: 10,000 rows, 64 files, 256 directory entries, 256 KiB/line,
32 MiB news, 16 MiB serialized output, 32 candidates/row, 30 seconds cooperative
deadline including metadata reads. Parquet is capped at 16 MiB on disk / 64 MiB
expanded metadata size and 20,000 rows (exact archive count also checked).
Memory is bounded by those inputs/output plus Python/Arrow object overhead.
Errors/limits/partial final lines return sanitized REFUSED JSON, exit 2;
success exits 0. Appends after each file's initial byte boundary are excluded.
This is not an atomic corpus snapshot or a point-in-time holdings replay.

## Verification and remaining gap

Synthetic checks cover the four reported publisher mistags, weather Snow/SNOW,
reference pages, issuer witnesses, CIK conflicts, share classes, source clocks,
filing/document deduplication, safe lists, redaction and resource refusal.
Read-only smoke: Nov 4, 1,577 rows / 101 estimates pages; reported META, GOOGL,
PSNL and GEV mistags all REVIEW_REQUIRED. Latest Nov 5 smoke: 29 saved rows, including 21 SEC
exhibits / 18 filing groups; tagless WU/KVYO/OTF recovered, FSLY 3 documents in
2 filings, CCI 2 in 1. Counts are captured observations, not future freshness.
Weather regression is synthetic; its reported real producing row is unresolved.

The separate reader source fix stops passing queue ticker to `finish_article`
for all pool reads, including stock_links, direct and stock-page reads, while
preserving `reached_by.ticker`. Full-page `tickers_named` remains a mention
heuristic. Historical raw records are untouched; no active reader was restarted.

Focused offline checks: 41 new tests; 131 checks pass with one existing guard
test deselected. The broader run failed that same guard test; restoring the
base `_read_article` in memory reproduced its zero-fake-open failure.

```powershell
$env:AEGIS_IGNORE_DOTENV='1'
python -B -m pytest backend/tests/test_news_universe_audit.py backend/tests/test_reader_discovery_tickers.py backend/tests/test_reader_pool.py backend/tests/test_reader_browse_lane.py backend/tests/test_web_reader_publication_clock.py -q --timeout=30 -k 'not test_no_guard_was_removed_per_action_on_the_pool_path'
```

Unresolved: `world_digest.collect` reads raw full-page `tickers_named`;
`type_row` and `_ticker_in_text` admit mentions without subject/body segmentation.
A synthetic Qualcomm title + AAPL sidebar reproduces admission. This candidate
does **not** repair or certify digest semantics, spend preflight, forecasts,
decisions, or existing consumers. Article-context admission needs separate review.
