# Social-strategy data sources — verdicts (Opus live-verified + Gemini, reconciled)

**Date:** 2026-08-04 · Inputs: Opus session (live-fetched every reachable
source, downloaded the actual SEC files, measured the 13F lag distribution
from raw data) + Gemini deep research (secondary sourcing; two genuinely new
finds). Where they conflict, the live-verified claim wins and the conflict is
recorded.

## Verdict table

| Source | Verdict | PIT field | The build |
|---|---|---|---|
| **SEC Form 4** (T1) | **GREEN** | `acceptanceDateTime` (submissions API); bulk quarterly ZIPs 2006+ are date-only | Quarterly Insider Transactions Data Sets (8 TSVs, verified by download) + per-issuer submissions JSON for timestamps. CMP routine/opportunistic rule verbatim from w16454 — natively PIT (classified each Jan from history only). `AFF10B5ONE` flag (2023+) = better routine filter than the CMP proxy for the modern era. **Trap: forms accepted until 22:00 ET count as same-day filed — trading close-to-close on filingDate is a leak; require next-open after acceptance** |
| **13F holdings** (T5) | **GREEN 2013+** | `FILING_DATE` in SUBMISSION.tsv (exact, free) | Free SEC Form 13F Data Sets beat Thomson s34 for 2013+: measured lag distribution (2026Q1, n=8,741): median 37d, p25 23d, 19.2% file exactly day 45, 1.9% late. "Quarter-end+45" convention wastes ~3 weeks of signal on half the filers. s34 `fdate` is Thomson's vintage date, NOT the EDGAR filing date. Gemini adds the confidential-treatment trap: Thomson silently backfills delayed holdings into historical quarters (Agarwal-Jiang-Tang-Yang 2013) — one more reason to prefer the SEC sets |
| **8-K Item 5.02** (T2, revolving door) | **GREEN** | `acceptanceDateTime` | Standout find: `data.sec.gov/submissions/CIK.json` carries an `items` field per filing — **event detection needs no text parsing at all** (filter form=8-K, '5.02' in items). Text parsing only to classify departure-vs-appointment and name the person (edgartools / EDGAR-CRAWLER as tools). Trap runs opposite to Form 4: 8-Ks accepted after 17:30 ET are next-day filed — always key off acceptance. 8-K due within 4 business days of the event |
| **Lobbying (LDA)** | **AMBER** | `dt_posted` (live-verified; Gemini's `filing_dt_posted` name not confirmed) | lda.gov REST API (old host sunsets mid-2026). Corrupt values exist in the wild (a 2000 filing stamped 1940) — guard `dt_posted >= filing period`. Amendments reuse filing lineage — dedupe to latest. Ticker link = LobbyView→gvkey, whose match method is **unpublished by its own authors** → the linkage gets a placebo gate, not trust. Bonus: `lobbyist_covered_position` = free structured revolving-door flag (lobbyists only) |
| **PAC / FEC** | **AMBER** | none in bulk; join to API `/v1/filings/` `receipt_date` (date-only, null on legacy) | Bulk cm.txt (committee→connected org, verified rows) + transaction files. Gemini's real find: the **Christensen FEC-to-Compustat link table** (hand-verified CMTE_ID→gvkey incl. subsidiary tiers) — verify and use instead of building fuzzy matching from scratch. ~48h processing delay → assume +2 business days conservatively |
| **Federal contracts (USAspending)** | **RED for backtests** | none trustworthy | `action_date` = signing date, not publication; **DoD enforces a 90-day publication blackout** (verbatim on fpds.gov) — every defense name's awards appear ~3 months late, so an action_date backtest manufactures fake alpha; `award_latest_action_date` mutates retroactively (open API issue); `initial_report_date` exists only in bulk with unverified fill rate. Usable FORWARD-only with our own capture timestamps. Sub-awards: self-reported, ~25% duplicates, skip |
| **Revolving-door hires** | **DEFER** | — | No free structured PIT feed exists. Pragmatic path for us: BoardEx (already certified) + 8-K 5.02 stream; LDA covered_position for the lobbyist subset. OpenSecrets = scrape-only until someone verifies the bulk terms (Cloudflare-blocked this round; Gemini's "API discontinued 2025" unverified) |

## Consequences for the trial designs

1. **T1 (INSIDER-CLUSTER) data path is fully certified, free, and deeper than
   planned**: 2006→present with acceptance timestamps, the CMP rule
   pre-registered verbatim, and AFF10B5ONE as a modern robustness leg.
2. **T5's 13F leg switches from Thomson s34 to the free SEC sets** for
   2013+; s34 only if we extend pre-2013 (with the fdate + backfill caveats
   documented). The measured lag distribution goes into the trial spec.
3. **T2 gains a fast-event stream** (8-K 5.02 acceptance-stamped, days ahead
   of BoardEx's update cycle) on top of BoardEx role-end dates.
4. **Political-access design re-scoped**: lobbying + PAC proceed (AMBER
   controls: placebo-gate the LobbyView linkage, +2-day FEC conservatism);
   the federal-contracts leg is **out of any backtest** — 90-day DoD
   blackout — and can only accrue forward with our own capture stamps.
5. Both AMBER linkage shortcuts (LobbyView gvkey map, Christensen table) are
   third-party artifacts with unaudited/unknown match rates → each gets a
   random-linkage placebo before any signal built on them is read.
