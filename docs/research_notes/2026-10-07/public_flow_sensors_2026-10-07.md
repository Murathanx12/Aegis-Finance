# Public flow sensors: government buying, lobbying, politician trading, prediction markets, crypto, fiscal seasonality (2026-10-07)

Researcher pass (Sonnet, read-only + web). No code run, no file written other than this one. Each
source below is framed as a **sensor with provenance and latency**, per the brief — never a trade
signal by itself. Per `CLAUDE.md` §2 item 10 and `ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md`
row 11: **identity groups (who someone is) are never a variable; the measurable economics underneath
(dollars of contracts, dollars of lobbying, dollars of PAC flow) are.** Nothing below proposes a
religious/ethnic/political-affiliation feature of any kind — every spec keys on firm-level dollar
amounts, filing dates and public disclosures.

Consulted first: `docs/DATA_MANIFEST.md`, `docs/DATA_CATALOG.md`, `backend/services/official_sources.py`
(2,213 lines, read to line 1055 plus the schema/SOURCES/REFUSED_SOURCES tables), `backend/routers/
prediction_markets.py`, `backend/services/prediction_markets.py`, `backend/services/crypto_market.py`,
`backend/services/congress_trades.py`, and `docs/research_notes/2026-10-06/
snowball_and_theory_objects_2026-10-06.md` §3 (rows 4, 5, 6, 9, 11a, 11b are the `NEEDS_DATA` /
`READY_TO_CELL` rows this note operationalizes). **Nothing proposed here re-pulls data already on
disk** — confirmed against the manifest and catalog before each spec.

---

## 0. What already exists (do not re-build)

| Already built | Where | Status |
|---|---|---|
| SEC Form 4/8-K/13D-G/13F, House PTRs, CFTC COT, FINRA short interest, Federal Register, 7 central-bank/White House/Treasury RSS feeds | `backend/services/official_sources.py` (free, no key, robots-respecting, day-capped, cooling on bot-check) | LIVE — 250+ receipts in the last week |
| Polymarket + Kalshi daily PIT snapshots | `backend/services/prediction_markets.py`, `prediction_market_matching.py`, `event_probability_surface.py` | LIVE, `TRIAL-PREDMARKET-1/2` — **barred from any scoring path until a successor trial passes** |
| Crypto spot/mcap/volume, top-20 coins, 7-30d history | `backend/services/crypto_market.py` (CoinGecko v3 free, no key) | LIVE, UI rollup only, not fed into any signal |
| Congress trades (House + Senate via FMP) | `backend/services/congress_trades.py` | Registered (`TRIAL-CONGRESS-IC`) but **collector confirmed broken** (zero rows ever written — audit `docs/research_notes/2026-09-20/audit_congress_collector.md`, F1-F4, not fixed) |
| Senate eFD direct read | `official_sources.REFUSED_SOURCES["senate_efd"]` | REFUSED: 403 bot-check + agreement form, not submitted |
| Compustat segment data (`comp_fundq`, `compseg__*`) | WRDS bulk, `backend/data/optimus/wrds/bulk/compseg__*.parquet` (204 MB, 1976-06 .. 2026-06, 11 tables) | ON DISK — this is the "10-K segment data" piece of ask #6, no pull needed |

---

## 1. Government buying / industrial policy — USAspending.gov

**URL / endpoints:** `https://api.usaspending.gov/api/v2/search/spending_by_award/` (POST, filters:
`recipient_search_text`, `naics_codes`, `agencies`, `time_period.action_date`), `/api/v2/
recipient/children/<DUNS_OR_UEI>/`, `/api/v2/bulk_download/awards/` (async zip), and the static
archive `https://www.usaspending.gov/download_center/award_data_archive` (full annual CSV dumps).
**Auth:** **none** — "Endpoints do not currently require any authorization" (official docs). **Rate
limit:** a documented global **1,000 requests / 300 seconds** on most endpoints (community report,
confirmed against a live GitHub issue); the bulk-download endpoints are more aggressively limited —
sequential, not parallel, pulls recommended. **Terms:** public-domain US government data, no
commercial-use or redistribution restriction found anywhere in the docs. **Delay/latency:** `action_date`
is the transaction date; USAspending itself lags live awards by **2-4 weeks** (agencies have a
contractual window to report into FPDS/USASpending) — so `action_date` is **not** the PIT-safe field;
use `last_modified_date` (when USAspending's own record changed) as the public-knowledge timestamp,
the same discipline `official_sources.py` already applies everywhere else (never the underlying event
date). **PIT fields:** `Base Obligation Date`, `Last Modified Date`, `action_date`, `date_signed` all
present; `Last Modified Date` is the one to stamp `public_utc` from. **Coverage:** every federal
contract/grant award back to FY2001 (full detail from FY2008 via the search API; FY2001+ via bulk
download), ~$7T/year, all 50 states + territories. **Size per pull:** a `recipient_search_text` +
`naics_codes` + monthly `time_period` query against ~40 known contractor names returns low thousands
of rows/month — a few MB/month, trivially within a free-tier day budget; the full annual archive is
multi-GB and not needed for a name-targeted pull.

**Ticker-mapping (the hard part, confirmed no free ready-made crosswalk exists):** `Recipient UEI` and
`Recipient DUNS Number` are on every award row, but **no public dataset maps UEI/DUNS to SEC CIK/
ticker** — every crosswalk found in this search (Obscura's `gov_contract_tickers`/`gov_recipient_
tickers`, GovConAPI, Empire Data Solutions' "UEI → Ticker Bridge") is a **paid commercial product**,
none free, none open-source. The buildable free path, in order of cost:
1. **Hand-curated list** (cheapest, most reliable for the names that matter): ~50-100 known large
   public federal contractors (LMT, RTX, NOC, GD, LHX, BAH, SAIC, LDOS, KBR, CACI, J, HII, TXT, and
   the CHIPS/IRA/DOE-loan recipients named in the review) mapped by hand to ticker/CIK once. This is
   the "explore dirty" first pass and covers the overwhelming majority of contract dollars by value
   (federal prime-contract spend is extremely concentrated).
2. **Fuzzy name join** (stretch, broader recall): normalize `Recipient Name` (uppercase, strip
   INC/CORP/LLC/CO) and join against SEC's own free `https://www.sec.gov/files/company_tickers.json`
   (already pulled by `official_sources.sec_tickers`) on normalized name equality — this is literally
   what the paid Obscura product does; building it in-house costs one afternoon, not a subscription.
   Flag low-confidence/ambiguous matches for manual review rather than guessing (same discipline as
   the commercial product's `needs_review` status).
3. CHIPS Act / IRA / DOE loan guarantees specifically: DOE's own Loan Programs Office publishes its
   portfolio (public, no pull needed beyond a periodic page read — `energy.gov/lpo`); CHIPS Act
   awards are filterable in USAspending by `funding_agency` = Department of Commerce / NIST.

**5-line pull-script spec** (for an Opus builder):
- Module: `backend/services/usaspending_awards.py`. Function `fetch_awards(recipient_names: list[str],
  naics: list[str] | None, since: date) -> list[dict]` — POST to `spending_by_award/`, paginate,
  stamp `public_utc` = `Last Modified Date` 23:59 ET (conservative), `public_ts_basis =
  "USASPENDING_LAST_MODIFIED"`.
- Receipt: one row per award keyed `row_id = f"usaspending:{Award ID}"`, append-only jsonl under
  `backend/data/optimus/official/tables/gov_awards.jsonl` (extends the existing `TABLES` tuple in
  `official_sources.py` rather than a new subsystem).
- Schedule: weekly (awards don't move intraday; USAspending's own lag makes daily pointless) via the
  existing `--due` scheduler pattern in `official_sources.py`.
- Refusal: HTTP 5xx / malformed JSON raises before any write (same fail-loud contract as every other
  `official_sources` collector); a `day_cap` of ~200 requests/day keeps it well under the 1,000/300s
  ceiling even with retries.
- Ticker join: a frozen `GOV_CONTRACTOR_TICKERS: dict[str, str]` constant (step 1 above), with the
  fuzzy-join stretch gated behind a separate `--expand-universe` flag so the cheap path ships first.

---

## 2. Lobbying expenditure — Senate LDA (primary), FEC (PAC flows), OpenSecrets (do not use)

### Senate LDA (`lda.senate.gov` / `lda.gov`)
**URL:** `https://lda.senate.gov/api/` (REST, JSON), legacy query UI retiring **2026-06-30** (already
past — the API is now the only path). **Auth:** two tiers — **anonymous, no signup: 15 requests/
minute**; **registered API key: 120 requests/minute**. The anonymous tier alone is enough for a daily
or weekly pull of a few hundred filings. **Terms:** no commercial-use or redistribution restriction in
the ToS; the one obligation is a citation line ("Senate Office of Public Records cannot vouch for the
data...after retrieved from LDA.gov") on any republished analysis, and the Senate Seal may not be used.
**Delay/latency:** filings are **quarterly** (LD-2, due 20 days after quarter-end) plus LD-203
semiannual contribution reports; the API serves filings as soon as they post, so `dt_posted` is the
PIT-safe timestamp (not the quarter it covers). **PIT fields:** `filing_type`, `filing_year`,
`filing_period`, `dt_posted` (posting datetime), `income`/`expenses` (dollar amounts), `client` (the
company paying for lobbying — this is the ticker-mappable entity), `registrant` (the lobbying firm),
`lobbying_activities[].general_issue_area`. **Coverage:** every registered lobbying client since 1999,
~15-20k active registrations. **Size per pull:** a client-name-filtered query for ~100-200 named
public companies, quarterly, is a few hundred KB/quarter.

### FEC — PAC and contribution flows (`api.open.fec.gov`)
**Auth:** `DEMO_KEY` works immediately with **no signup**, at a lower (unpublished but shared) rate;
a personal key (free signup via a web form) raises the limit to **1,000 calls/hour, 100 results/page**;
emailing `APIinfo@fec.gov` can raise it further to 7,200/hour. **Per the standing rule, a free key
signup is Murat's call, not a session's — flagged below.** **Terms — important caveat for the "public
open-source tool" branch of the mission:** the FEC's Acceptable Use Policy explicitly states campaign-
finance data from the API may **not** be used "for commercial purposes including, but not limited to,
training data for large language models, machine learning models or artificial intelligence models" —
this likely does not block a read-only internal research sensor, but **would** block shipping FEC-
derived PAC numbers as a feature inside a tool others run commercially, and definitely blocks any
LLM-training use of the raw rows. Aegis should treat FEC data as **internal/paper research only**, not
as a feature in the public open-source release, until this is re-read with counsel or a narrower use
is confirmed compliant. **Delay/latency:** data updated nightly; committee-level summaries (Form 3X)
file quarterly, individual contributions (Schedule A) are itemized and often reported within the
filing period, with a bulk weekly dump (`fec.gov/files/bulk-downloads/`) updated every Sunday — no
signup needed for the bulk dump at all. **PIT field:** use the filing's own `receipt_date`/`load_date`,
never the `contribution_receipt_date` being described. **Coverage:** every PAC, every federal
candidate committee, since 1979 (full detail from the 1990s).

### OpenSecrets — **do not use as a data source**
**Its API was discontinued 2026-04-15** (the page now reads "our API offerings have been discontinued").
Bulk data downloads still exist but require account registration (owner approval needed) and the
site's Terms and Conditions **explicitly prohibit any commercial use or redistribution** of
OpenSecrets-derived materials ("Except as expressly permitted by OpenSecrets, any use...for
unauthorized or commercial purposes is strictly prohibited"). Since LDA + FEC together already cover
the same ground (lobbying dollars, PAC dollars) **for free, from the primary government source, with
fewer restrictions**, OpenSecrets is **not recommended** — it would be the weakest link in the chain
for a tool meant to ship publicly.

**Ticker-mapping:** both LDA's `client` field and FEC's committee/contributor-employer fields are
free-text company names — same hand-curated-list-first, fuzzy-join-second approach as §1.

**5-line pull-script spec (LDA, the one to build first — needs no signup at all):**
- Module: `backend/services/lda_lobbying.py`. Function `fetch_filings(clients: list[str], since:
  date) -> list[dict]` — GET `lda.senate.gov/api/v1/filings/?client_name=<name>&posted_after=<date>`,
  paginate at 15 req/min (anonymous), stamp `public_utc = dt_posted`.
- Receipt: `row_id = f"lda:{filing_uuid}"`, appended to a new `lobbying_filings` table following the
  exact `TABLES`/`SCHEMAS`/`append_rows` pattern already in `official_sources.py` (same file, new
  entry — not a new subsystem).
- Schedule: `every_s = 6*3600` (quarterly filings don't need hourly polling) via the existing
  `SOURCES` dict and `--due` runner.
- Refusal: malformed JSON or non-200 raises before write; `day_cap` conservatively set below
  15 req/min × 1440 min to leave headroom for other callers on the shared anonymous IP budget.
- Ticker join: same frozen hand-curated dict as §1 (one shared crosswalk module, not two).

---

## 3. Politician trading — House PTRs already pulled; Senate mirror options

House PTRs are **already live and free** via `official_sources.house_ptr` (the Clerk's own ZIP + each
PTR PDF's text, no signup). Senate eFD direct access is **REFUSED** (403 bot-check + unsigned
agreement form — correctly not worked around per the standing rule). Checked third-party mirrors for
a lawful, free-enough Senate-inclusive alternative:

| Mirror | Senate coverage | Free tier | Commercial/redistribution | Verdict |
|---|---|---|---|---|
| **Capitol Trades** (capitoltrades.com, run by 2iQ) | Yes — explicitly sources "Senate Financial Disclosures (eFD) and...the Clerk of the U.S. House" | Entire site is free, no API offered; ToS has no anti-scraping clause found, but there's also no sanctioned bulk/API path | Unclear — "AS IS" disclaimer only, standard web ToS | Respectful, robots.txt-checked scraping is **plausible** but unverified — needs a quick robots.txt/ToS re-read before building, not a clean API |
| **Quiver Quantitative** (official `api.quiverquant.com`) | Yes | None meaningful — "a subscription is required for full access"; an unofficial third-party wrapper (Parse.bot) offers 200 credits/mo free but is not the vendor's own terms | Paid tiers only for real use | Not free enough |
| **Unusual Whales** | Yes (implied, general congress-trading product) | API is paywalled (`unusualwhales.com/pricing?product=api`) | Paid | Not free |
| **Disclosed Capitol** (disclosedcapitol.com) | Yes — "sourced from official U.S. House and Senate STOCK Act filings" | **Free tier exists**: recent 90 days of trades, "reasonable rate limits", self-serve API key at signup | Explicitly states **"commercial use is allowed and encouraged on every self-serve plan...unlike several alternatives"** | **Best free+lawful Senate-inclusive option found** — but it is a small/new vendor (first seen 2026-06), re-verify data quality against the known-good House-PTR numbers before trusting its Senate rows |

**Recommendation:** House stays on the existing free official collector. For Senate, **do not re-attempt
the direct eFD scrape**; instead pilot **Disclosed Capitol's free tier** against known House-PTR
trades (cross-check a few members who serve in Congress's overlap periods, or compare its House rows
to the official collector's House rows as a sanity check before trusting its Senate rows) — this is a
free signup (self-serve, no payment), which per the standing rule is still **the owner's call**, not
because it costs money but because any new external account is attended per the seed-a-lane /
discipline-skill norms in this repo.

**PIT discipline if built:** use `disclosure_date`, never `trade_date`, exactly as `congress_trades.py`
and `official_sources.house_ptr` already do — this is the one rule every source in this note repeats.

---

## 4. Prediction markets — already flowing; the finding here is a ToS risk, not a new pull

`backend/services/prediction_markets.py` already pulls **Kalshi** (via the unauthenticated
`external-api.kalshi.com/trade-api/v2` public market-data endpoints) and **Polymarket** (Gamma +
Data API) into daily PIT snapshots, correctly firewalled from every scoring path by `TRIAL-PREDMARKET-
1/2`'s own docstring and the `prediction_markets.py` router banner.

**New finding, worth the owner's attention:** Kalshi's own **Developer Agreement** (`kalshi.com/
developer-agreement`) states API use is "expressly limited to facilitating a members own trading,"
explicitly **prohibits** "collecting, caching, aggregating, or storing data...except for purposes of
facilitating your own trading," and separately Kalshi's **Data Terms of Service** (the website-level
terms) prohibit **any** use of Kalshi data for machine learning / AI training or for "archived or
cached data sets" shared with another party, even internally. The repo's own daily persisted snapshot
(`backend/data/optimus/...` presumably, per the "daily PIT snapshots" docstring) is arguably exactly
the kind of caching both documents forbid, **even though no scoring path reads it and no execution
happens** — the restriction is about **storing the data at all**, not about trading on it. This is
lower urgency than a trading violation but is a real ToS exposure for anything that might be published
(a public GitHub repo with persisted Kalshi snapshots). **Recommended fix, not performed here:**
either (a) stop persisting raw Kalshi rows beyond same-day (keep only derived, aggregated statistics,
which is closer to "fair use" territory), or (b) drop Kalshi and lean on Polymarket alone, whose Gamma/
Data API terms carry **no equivalent storage/AI-training prohibition** found in this pass (only
standard Cloudflare rate limits). Flag to Murat; do not silently delete the Kalshi collector.

**Polymarket** (unchanged recommendation): Gamma API `gamma-api.polymarket.com` and Data API
`data-api.polymarket.com`, both public, no auth, generous IP-based rate limits (4,000 req/10s general
on Gamma). This is the cleaner of the two venues to keep building on.

**Metaculus** (not yet in the repo): aggregate "Community Prediction" data is **no longer generally
available** via API (changed 2026-03-09 specifically to stop unauthorized commercial/bot use) except
on ~50 test questions free, or ~250 questions via a "bot-maker tier" that requires **emailing
`api-requests@metaculus.com`** — an owner-signup/contact item, not a code change. Low priority: it adds
one more macro-regime venue but at real friction cost for modest incremental coverage beyond Kalshi/
Polymarket.

**Mapping to regime variables:** rates → Fed-funds-path contracts (Kalshi has these natively);
recession → Kalshi "will there be a recession" series; elections → both venues, heavily covered;
tariffs → Polymarket has had active tariff-specific markets. No new build needed here beyond what
`event_probability_surface.py` already does — this section is a terms-of-service finding, not a pull
spec.

---

## 5. Crypto as a risk-appetite sensor — cheapest of the seven, build first

Three free, no-key, no-signup pieces, all buildable in one module extending the existing
`crypto_market.py`:

1. **Spot + market cap** — already done (`crypto_market.fetch_markets`, CoinGecko v3 free tier,
   ~30 req/min, already cached 3 min TTL).
2. **Stablecoin supply** — **DeFiLlama** free API, `https://api.llama.fi/stablecoins` and
   `/stablecoincharts/all` (historical mcap sum of all stablecoins) and `/stablecoinchains` (supply
   by chain). **No auth, no key, explicitly "free to use," citation appreciated.** Updates hourly.
   This is the single cheapest net-new pull in this whole note.
3. **Funding rates** (risk appetite / leverage in the futures market) — **Binance** `GET
   https://fapi.binance.com/fapi/v1/fundingRate` and **OKX** `GET https://www.okx.com/api/v5/public/
   funding-rate` are both **public, unauthenticated, no key** (metered per-IP: Binance ~2,400 req/min,
   OKX ~20 req/2s). Settlement every 8h; funding history back to 2019 on Binance. A third-party
   aggregator (xoomar.com) exists if a single normalized multi-venue call is wanted, but the two
   exchange-native endpoints are free, official, and sufficient — no new dependency needed.

**Terms:** DeFiLlama's own ToS only restricts using *other* (non-official) APIs programmatically —
irrelevant here since only the free, official endpoint is used; citing "DefiLlama" is requested, not
required. Binance/OKX public market-data endpoints carry no commercial-use restriction found.

**PIT fields:** CoinGecko/DeFiLlama both timestamp at point of fetch (no filing-lag concept — these are
live market data, same discipline as the existing bars panel: `first_seen_utc` is the PIT stamp).
Funding-rate settlement times are exchange-published and exact.

**5-line pull-script spec:**
- Module: extend `backend/services/crypto_market.py` with `fetch_stablecoin_supply() -> dict` (DeFiLlama)
  and `fetch_funding_rates(symbols: list[str]) -> list[dict]` (Binance + OKX).
- Receipt: a `crypto_risk_sensor.jsonl` row per fetch: `{total_stablecoin_mcap, btc_funding_8h,
  eth_funding_8h, fetched_at}` — a handful of numbers, not a new data store.
- Schedule: daily (risk-appetite regime variables don't need intraday resolution for this use).
- Refusal: any `None`/non-200 from either source raises or is logged `DEGRADED`, never silently
  zero-filled (same silent-fragility discipline as everywhere else in this repo).
- Explicit "we do not trade it" banner in the module docstring, matching the owner's own framing and
  `prediction_markets.py`'s existing banner pattern.

---

## 6. Fiscal-year-end spending seasonality — same USAspending substrate, a theory-cell spec

**Data needed:** USAspending `spending_by_award` **grouped by month × awarding agency** (the federal
fiscal year ends Sept 30; agencies famously spend down unobligated balances in August-September) —
same API as §1, filtered to `award_type_codes` for contracts, grouped by `action_date` month, for the
named contractor universe. **Contractor revenue exposure:** already on disk — `compseg__*` (Compustat
segment data, 1976-2026, on WRDS) carries segment-level revenue by SIC/NAICS-adjacent classification,
so "what fraction of this company's revenue is federal" is answerable from data already pulled, no new
vendor needed; it needs a one-time join (ticker → CIK → `gp/comp` segment rows flagged "US Government"
as a customer/segment where disclosed) rather than a new pull.

**Theory cell spec** (for `hyp_lab`, following the existing `macro_lead_lag` cell shape already used
for the oil-shock/yield-shock cells in `docs/research_notes/2026-09-30/hypothesis_lab_2026-09-30.md`):
- **Mechanism:** federal agencies obligate unspent fiscal-year funds in the August-September window
  ("use it or lose it" budgeting), producing a real order-flow/revenue uptick for federal-exposed
  contractors concentrated in that window.
- **Precursor at decision time:** the calendar itself (Aug 1 each year) plus the contractor's own
  federal-revenue-exposure percentile (observable from last year's 10-K segment disclosure, fully
  PIT-safe — it's public well before the next fiscal year-end).
- **Universe:** the same hand-curated federal-contractor ticker list from §1, cross-referenced against
  Compustat segment revenue concentration already on disk.
- **Falsifier:** the Aug-Sept effect must beat the SAME names' own other-month baseline AND the
  market, across at least 5 fiscal years (2021-2025 already fully resolved) — a single good year is
  not a seasonality, per the `print by year` standing rule.
- **Already-tried corpse to cite:** none found specific to fiscal-year-end government spend; the
  closed oil-shock/yield-shock `macro_lead_lag` cells are the nearest sibling mechanism-class (both
  CANNOT_DISTINGUISH), so the honest prior going in is modest, not zero.

---

## 7. Price-location features — confirmed nothing to pull

Per the 2026-10-06 theory-object table row 12: `px_vs_52w_high/low`, day-range/ATR position are
**already coded** in `backend/services/strategy_library.py`, `xs_ranker.py`, and
`technical_analysis.py`, using bars already on disk (`prices_2025_26/bars.parquet`, 1.27M bars,
3,060 symbols). Nothing to build here; the open item is a standalone CRSP run of the existing feature
(already flagged `READY_TO_CELL` in the prior note), not a data pull.

---

## Ranking: P(changes the roadmap) × value − cost, and the three to build first

| # | source | P(changes roadmap) | value if it works | cost to build | owner signup needed? | net rank |
|---|---|---|---|---|---|---|
| 1 | USAspending government contracts | Med — explicitly named in roadmap §2 item 10, row 29 | Med-High (closes 2 asks at once: #1 and #6) | Low (no auth; crosswalk is the only real work, and a hand list covers most of the dollar value for free) | **No** | **1st** |
| 2 | Senate LDA lobbying | Med — explicitly named, theory-table row 5 | Med (lobbying $ as a firm-level economic variable, clean mechanism) | Low (anonymous tier needs zero signup) | No (registered tier optional, higher limit) | **2nd** |
| 3 | Crypto risk-appetite sensor (stablecoin supply + funding rates) | Low-Med — explicitly asked, declared non-tradeable | Low-Med (regime context only, owner said "we do not trade it") | **Lowest of all seven** — zero auth anywhere, extends existing module | No | **3rd** |
| 4 | FEC PAC flows | Med | Med | Low-Med (DEMO_KEY works with no signup; real key is free but still a signup) | Yes (free key, for sustained use) | 4th |
| 5 | Politician trading Senate mirror (Disclosed Capitol) | Low-Med — closes a known gap (House-only today) | Med (completes the politician-trading picture) | Med (new small vendor, needs cross-validation against known-good House rows before trusting) | Yes (free self-serve signup) | 5th |
| 6 | Prediction markets as lead-lag sensor | Low (mostly already built; this is a ToS-risk finding, not new data) | Med if the lead-lag cell works (untested) | Low (reuses existing snapshots) but **carries a Kalshi ToS exposure to resolve first** | No (but a Kalshi storage-policy decision is owner's) | 6th (do the ToS fix, not a new pull) |
| 7 | OpenSecrets | — | — | — | — | **Not recommended** — API discontinued, bulk data commercial-use-prohibited, fully superseded by LDA+FEC |

**The three to build first:** USAspending (government contracts + fiscal-year-end seasonality
together), Senate LDA lobbying (free even anonymously), and the crypto risk-appetite sensor (cheapest,
zero friction, extends code that already exists). All three need **no owner account signup** to reach
a working first version.

**Sources that need the owner's signup/approval before going further**, per the standing rule that a
free API key signup is attended, not a session's call:
- **FEC** — a free personal API key (`api.open.fec.gov`, signup form) to move past `DEMO_KEY`'s shared
  limit; also flag the AUP's ban on using FEC data to train ML/AI models or for commercial use of
  contributor lists before this goes anywhere near the public open-source release.
- **Senate LDA registered tier** — optional; the anonymous 15/min tier may already be enough.
- **Disclosed Capitol** — a free self-serve signup, needed only if the owner wants Senate-trade
  coverage beyond the already-free House PTRs.
- **Metaculus bot-maker tier** — requires emailing `api-requests@metaculus.com`; low priority, skip
  unless Kalshi+Polymarket prove insufficient for the regime variables wanted.
- **Kalshi — not a new signup, but an owner decision**: whether to keep persisting raw Kalshi snapshots
  given its Developer Agreement and Data ToS both restrict storage/caching and (separately) any
  ML/AI use of the data.
