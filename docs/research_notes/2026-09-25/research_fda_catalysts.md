# FDA Catalysts, Free Data Sources, and Analyst-Signal Literature
Research compiled 2026-09-25. All web research; no repo files modified.

---

# PART 1 — Upcoming FDA Catalysts (Oct 2026 – Jan 2027) and Base Rates

## Source accessibility check

| # | Source | Result |
|---|---|---|
| 1 | FDA.gov Advisory Committee Calendar | Fetched successfully but the page is a live search form (Start/End Date, Committee, Center) with no meetings pre-populated in static HTML. One future meeting (Sydnexis, Oct 30 2026) was found indirectly via news search, confirming meetings exist even though the static page shows none without running the interactive form. |
| 2 | BiopharmCatalyst | Blocked. Both `/calendars/fda-calendar` and `/calendars/pdufa-calendar` returned only cookie-notice/nav boilerplate — table renders via JS and/or sits behind sign-in. No free teaser content retrievable via static fetch. |
| 3 | RTTNews FDA calendar | Partially accessible — static fetch showed entries only through late Sept 2026 (Telix, Ionis, Mirum, Zealand); pagination is JS-driven, Oct 2026–Jan 2027 rows not reachable this way. |
| 4 | Benzinga / Seeking Alpha FDA calendar | Not directly retrieved within search budget; only an old (2017) Benzinga article surfaced. |
| 5 | Fierce Biotech | No dedicated Q4-2026 preview article found; one relevant item (Regenxbio RGX-121 PDUFA delay to Feb 8 2027) falls outside the window. |
| 6 | BioSpace | Accessible but no populated forward catalyst calendar found; a dated "Biotech Catalysts to Watch" blog post surfaced BioXcel/Capricor/Inovio/Tiziana items. |
| 7 | Evaluate / Evaluate Vantage | Accessible, not paywalled, but no forward PDUFA calendar content — it's a webinar/thought-leadership hub, not a catalyst tracker. |
| 8 | Company IR pages / SEC 8-Ks | Most productive source — confirmed the large majority of dated catalysts below. |

Two free/lightly-gated aggregators not on the original list, found via search and useful for cross-checking: **MarketBeat** (`marketbeat.com/fda-calendar/upcoming/`), **Assyro** (`assyro.com/tools/pdufa-calendar/2026/...`), and **pdufa.bio** (`pdufa.bio/calendar`) — all rendered free tabular data on static fetch. Used to build the candidate list, then cross-checked the largest names against primary sources.

## Catalyst list — verified against primary sources (company PR / SEC filing)

| Ticker | Company | Drug | Indication | Event | Date | Source | Class |
|---|---|---|---|---|---|---|---|
| INO | Inovio Pharmaceuticals | INO-3107 | Recurrent respiratory papillomatosis (adults) | PDUFA (BLA) | 2026-10-30 | [ir.inovio.com](https://ir.inovio.com/news/news-details/2025/FDA-Accepts-for-Review-INOVIOs-BLA-for-INO-3107-for-the-Treatment-of-Adults-with-Recurrent-Respiratory-Papillomatosis-RRP/default.aspx) | Primary |
| BTAI | BioXcel Therapeutics | IGALMI (dexmedetomidine) sNDA | Acute agitation, bipolar/schizophrenia, at-home use | PDUFA (sNDA) | 2026-11-14 | [globenewswire.com](https://www.globenewswire.com/news-release/2026/04/01/3266468/0/en/bioxcel-therapeutics-announces-food-drug-administration-acceptance-of-supplemental-new-drug-application-for-use-of-igalmi-in-the-at-home-setting.html) | Primary |
| ~~CYTK~~ **CORRECTED 2026-09-25 by Fable: the cited press release (05-01-2025) states the NDA PDUFA was Dec 26, 2025; the company's pipeline page shows MYQORZO "Approved in U.S." for oHCM. No 2026-11-14 sNDA date is supported by a primary source. Not a Q4-2026 catalyst.** | Cytokinetics | Aficamten (MYQORZO) | Obstructive hypertrophic cardiomyopathy | ~~PDUFA (sNDA)~~ already approved | ~~2026-11-14~~ | [ir.cytokinetics.com](https://ir.cytokinetics.com/press-releases/press-release-details/2025/Cytokinetics-Announces-New-PDUFA-Date-for-Aficamten-in-Obstructive-Hypertrophic-Cardiomyopathy-05-01-2025/default.aspx) | Primary |
| AGIO | Agios Pharmaceuticals | Mitapivat sNDA | Sickle cell disease (accelerated approval) | PDUFA (sNDA) | 2026-11-01 | [investor.agios.com](https://investor.agios.com/news-releases/news-release-details/us-fda-grants-priority-review-agios-snda-mitapivat-sickle-cell) | Primary |
| CAPR | Capricor Therapeutics | Deramiocel (CAP-1002) | Duchenne muscular dystrophy cardiomyopathy | PDUFA (BLA, extended) | 2026-11-22 | [capricor.com](https://www.capricor.com/investors/news-events/press-releases/detail/354/capricor-therapeutics-announces-extension-of-pdufa-target); [cureduchenne.org](https://cureduchenne.org/research/capricors-pdufa-date-for-fda-to-review-deramiocel-has-been-extended-to-november-22-2026/) | Primary |
| NUVL | Nuvalent | Neladalkib (NVL-655) | TKI-pretreated advanced ALK+ NSCLC | PDUFA (NDA) | 2026-11-27 | SEC 8-K / investors.nuvalent.com | Primary |
| VRTX | Vertex Pharmaceuticals | Povetacicept | IgA nephropathy (accelerated approval) | PDUFA (BLA) | 2026-11-30 | [news.vrtx.com](https://news.vrtx.com/news-releases/news-release-details/vertex-announces-us-fda-acceptance-biologics-license-application) | Primary |
| MLYS | Mineralys Therapeutics | Lorundrostat | Uncontrolled/resistant hypertension | PDUFA (NDA) | 2026-12-22 | [ir.mineralystx.com](https://ir.mineralystx.com/news-events/press-releases/detail/93/mineralys-therapeutics-announces-fda-acceptance-of-nda-for) | Primary |
| CORT | Corcept Therapeutics | Relacorilant | Cushing's syndrome (resubmission after Dec 2025 CRL) | CRL resubmission decision | ~mid-Dec 2026 (secondary aggregator: Dec 17) | [ir.corcept.com](https://ir.corcept.com/news-releases/news-release-details/corcept-resubmits-new-drug-application-relacorilant-treatment) (resubmission fact, primary); exact date secondary | Mixed |
| GILD (via Arcellx) | Gilead Sciences | Anitocabtagene autoleucel (anito-cel) | 4th-line relapsed/refractory multiple myeloma | PDUFA (BLA) | 2026-12-23 | [kitepharma.com](https://www.kitepharma.com/news/press-releases/2026/2/gilead-sciences-to-acquire-arcellx-to-maximize-long-term-potential-of-anito-cel); SEC 8-K | Primary |
| PRAX | Praxis Precision Medicines | Relutrigine (PRAX-562) | SCN2A/SCN8A developmental & epileptic encephalopathies | PDUFA (NDA, extended) | 2026-12-27 | [investors.praxismedicines.com](https://investors.praxismedicines.com/news-releases/news-release-details/praxis-precision-medicines-announces-extension-period) | Primary |

## Catalyst list — secondary aggregators only (not independently re-verified; cross-check before use)

| Ticker | Company | Drug | Indication | Event | Date | Source |
|---|---|---|---|---|---|---|
| MRK | Merck | Ifinatamab deruxtecan (I-DXd) | Pretreated extensive-stage SCLC | PDUFA (BLA) | 2026-10-10 | marketbeat.com |
| PHAR | Pharming Group | Leniolisib | APDS, label expansion | PDUFA | 2026-10-24 | pdufa.bio |
| RHHBY | Roche | Enspryng (satralizumab) | Thyroid eye disease | PDUFA | 2026-10-15 | pdufa.bio |
| SVRA | Savara Inc. | Molgramostim (molgradex) | Autoimmune pulmonary alveolar proteinosis | PDUFA (BLA) | 2026-11-22 | marketbeat.com / assyro.com |
| BBIO | BridgeBio Pharma | BBP-418 | Limb-girdle muscular dystrophy type 2i | PDUFA (NDA) | 2026-11-27 | marketbeat.com / assyro.com |
| COGT | Cogent Biosciences | Bezuclastinib (± sunitinib, PEAK) | Non-advanced systemic mastocytosis / GIST | PDUFA (NDA) | 2026-11-30 and/or 2026-12-30 (conflicting duplicate dates across sources) | marketbeat.com |
| SMMT | Summit Therapeutics | Ivonescimab + chemo | EGFR-mutated NSCLC combo | PDUFA (BLA) | 2026-11-14 | assyro.com |
| SNY | Sanofi | Venglustat | Type 3 Gaucher disease | PDUFA (NDA) | 2026-11-25 | assyro.com |
| ZYDL | Zydus Therapeutics | Saroglitazar | Primary biliary cholangitis | PDUFA (NDA) | 2026-11-27 | assyro.com |
| PYPD | PolyPid | D-PLEX100 | Prevention of surgical site infections | PDUFA (NDA) | 2026-11-28 | assyro.com |
| EXEL | Exelixis | Zanzalintinib (XL092) + atezolizumab | Colorectal cancer | PDUFA | 2026-12-03 | pdufa.bio |
| VNDA | Vanda Pharmaceuticals | Imsidolimab (licensed from AnaptysBio) | Generalized pustular psoriasis | PDUFA (BLA) | 2026-12-12 | pdufa.bio |
| ARGX | argenx SE | Efgartigimod (new indication, unspecified) | — | PDUFA | 2027-01-03 | pdufa.bio |
| NUVB | Nuvation Bio | Taletrectinib (IBTROZI) sNDA | Advanced ROS1+ NSCLC | PDUFA (sNDA) | 2027-01-04 | marketbeat.com / pdufa.bio |
| INSM | Insmed | ARIKAYCE | NTM lung disease (MAC), expanded use | PDUFA (sNDA) | 2027-01-28 | marketbeat.com |

**Correction found during verification**: one aggregator (assyro.com) listed Vera Therapeutics' (VERA) atacicept PDUFA as Oct 6 2026, but the actual BLA PDUFA was **July 7, 2026** (already passed) — illustrates why aggregator dates need cross-checking rather than direct use.

## AdCom meetings

| Company | Drug | Indication | Date | Source | Class |
|---|---|---|---|---|---|---|
| Sydnexis, Inc. (private, no ticker) | SYD-101 | Pediatric progressive myopia | 2026-10-30 | [BioSpace](https://www.biospace.com/press-releases/sydnexis-announces-fda-advisory-committee-meeting-date-to-review-nda-for-syd-101-for-pediatric-progressive-myopia) | Primary |
| Inovio (INO) | INO-3107 | RRP | FDA stated **no AdCom currently planned** | — | Primary |
| Praxis (PRAX) | Relutrigine | DEE | FDA stated **no AdCom planned** (per mid-cycle meeting) | — | Primary |
| Capricor (CAPR) | Deramiocel | DMD | AdCom already held July 2026 (context for the Nov 22 PDUFA, not a forward catalyst) | — | Primary |

No broader FDA AdCom slate for Nov 2026–Jan 2027 could be confirmed beyond Sydnexis; FDA's own calendar requires an interactive date-range search not executable via static fetch.

## Phase 3 topline readouts (not PDUFA-tied)

| Ticker | Company | Drug | Indication | Event | Date | Source |
|---|---|---|---|---|---|---|
| OCGN | Ocugen | OCU400 | Retinitis pigmentosa (gene-agnostic) | Phase 3 topline (liMeliGhT) | expected Q1 2027 | [ophthalmologytimes.com](https://www.ophthalmologytimes.com/view/ocugen-completes-enrollment-in-limelight-phase-3-trial-of-ocu400-for-retinitis-pigmentosa) |
| VERA | Vera Therapeutics | Atacicept | IgA nephropathy (full-approval sBLA) | Regulatory submission (not yet a PDUFA) | sBLA target Q4 2026 | ir.veratx.com |
| TLSA | Tiziana Life Sciences | Intranasal foralumab | Non-active secondary progressive MS | Phase 2a data | ~Oct 2026 (approximate) | biopharmawatch.com blog (secondary) |

**Coverage**: ~28 distinct named catalysts (11 primary-verified + ~17 secondary), spanning Oct 30 2026 – Jan 28 2027.

## Base rates and stock-reaction patterns

**1. FDA approval rates**
- First-cycle approval rate for NMEs 2013–2023: **87%**; eventual approval rate (first cycle or after resubmission): **94%**. Prior cohort (2000–2012): first-cycle approval only **73.5%** — a real process improvement (PDUFA VI), not noise. Source: [ScienceDirect S1359644626001443](https://www.sciencedirect.com/science/article/pii/S1359644626001443) (statistic via search snippet; full text 403-blocked — flagged for re-verification).
- First-cycle Complete Response (CR) rate for original NDAs/BLAs has hovered ~30% in recent years (declining FY2008→FY2024 with year-to-year variability); of first-cycle CR recipients, roughly 15–20 additional percentage points eventually gain approval on a later cycle.
- Primary source for full verification: [FDA PDUFA Performance Reports index](https://www.fda.gov/about-fda/user-fee-performance-reports/pdufa-performance-reports) (confirmed live, FY2015–FY2025 PDFs; not individually parsed this pass — the FY2021 PDF at fda.gov/media/156077/download returned corrupted text on extraction).
- BIO/Informa/QLS "Clinical Development Success Rates 2011–2020" report exists at [bio.org](https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020) but numeric rates require the full PDF (not pulled this session).

**2. Stock reaction: approval vs. CRL** — the weakest-sourced sub-task; no rigorous quantified approval-vs-CRL comparison was retrieved within budget. What is in hand:
- Hwang (2013), *PLoS ONE*, "Stock market returns and clinical trial results of investigational compounds" (large-cap biopharma, Jan 2011–May 2013; PMID 23951273): median announcement-day CAR **+0.8%** for positive news vs **−2.0%** for negative (asymmetric, losses bigger); positive effect fades by day +1 (+0.4%, ns), negative persists through (−2,+2) window (−1.2%, still significant). Sample is large-cap, so magnitudes are far smaller than typical small/micro-cap binary biotech swings (widely described informally as 30–100%+, but not rigorously sourced this session).
- Singh, Rocafort, Cai, Siah, Lo (2022), *PLoS ONE*, "The reaction of sponsor stock prices to clinical trial outcomes: An event study analysis" (13,807 trials, 2000–2020; PMID 36054103) — existence confirmed via PubMed, full text not retrieved (wrong DOI guess resolved to an unrelated paper). Flagged for a follow-up pull.
- BiopharmCatalyst/GlobalData/Evaluate compilations of approval-vs-CRL magnitude: confirmed inaccessible this session (paywalled/JS-rendered or no such content on the accessible pages).

**3. "Run-up then sell-the-news" pattern**
- **Rothenstein, Tomlinson, Tannock, Detsky (2011)**, *JNCI* 103(20):1507, "Company Stock Prices Before and After Public Announcements Related to Oncology Drugs" (Jan 2000–Jan 2009; oncology only). Retrieved in full — [academic.oup.com/jnci/article/103/20/1507](https://academic.oup.com/jnci/article/103/20/1507/912515):
  - 120-day pre-announcement run-up ahead of Phase III readouts: **+13.7%** for companies that went on to report positive trials vs **−0.7%** for eventual-negative (p=.09); tighter 60-day window: **+9.4%** vs **−4.5%** (p=.03, significant).
  - For FDA regulatory decisions specifically, pre-announcement price trends did **not** differ significantly between eventual-positive and eventual-negative outcomes in this sample — the anticipatory-drift effect held for trial readouts, not PDUFA decisions, here.
  - Authors interpret the trial-readout divergence as consistent with possible information leakage/anticipatory trading.
- Hwang (2013) explicitly tested for pre-announcement run-up in its (larger-cap, later) sample and found **none** — a genuine tension with Rothenstein rather than a settled number; the discrepancy is probably sample composition (oncology/smaller caps vs. large diversified biopharma) and time period (pre- vs. post- various PDUFA reforms).

**Session constraint**: WebSearch budget (200 calls) was exhausted during this research; DuckDuckGo HTML fallback was CAPTCHA-blocked. A follow-up pass should prioritize (a) verifying the 15 "secondary" catalysts against their own IR pages, (b) locating the full Singh et al. (2022) text, and (c) a rigorous approval-vs-CRL magnitude study.

---

# PART 2 — Free / Cheap Machine-Readable Data Sources

*"Verified" = fetched live during this research session. "From documentation/knowledge" = not independently fetchable (blocked by bot-protection/403/timeout/SPA) but stated from well-established public docs — flagged where confidence is lower.*

## 1. FDA / clinical trial calendars

| Source | Endpoint | Format | Rate limit | Cost | PIT safety |
|---|---|---|---|---|---|
| openFDA (general) | `api.fda.gov/{drug\|device\|food}/{endpoint}.json` | JSON | Verified: 240 req/min + 1,000/day, no key; 240/min + 120,000/day with free key | Free | Point-in-time archive of FDA submissions, updated daily Mon–Fri |
| Drugs@FDA | `api.fda.gov/drug/drugsfda.json` | JSON | Same | Free | Verified live: `submissions[]` carries `submission_status_date` per historical action — genuinely reconstructable approval history |
| Adverse Events | `api.fda.gov/drug/event.json` | JSON | Same | Free | Each event has `receiptdate`; good for PIT if filtered on receipt date |
| Drug Label | `api.fda.gov/drug/label.json` | JSON | Same | Free | Serves **current/most-recent label by default** — labels revised in place; historical versions unreliable without careful `effective_time` filtering. PIT risk: treat as latest-snapshot unless verified. |
| FDA Advisory Committee Calendar | `fda.gov/advisory-committees/advisory-committee-calendar` | HTML only | N/A | Free | No dedicated RSS/API; FDA only offers a generic sitewide RSS. This is a scraping target, not an API. Third-party trackers (FDATracker, Citeline Pink Sheet) republish it but are paid. |
| ClinicalTrials.gov API v2 | `clinicaltrials.gov/api/v2/studies` | JSON (CSV too) | No published numeric limit; community consensus ~50 req/min informally observed, no key required | Free | Filter primary completion date via `AREA[PrimaryCompletionDate]` range operators; `hasResults` flag for results-posted. **Caveat: live/mutable registry — no history/diff endpoint. To detect "results posted as of date X" you must poll and diff yourself; querying today is not retroactively reliable.** |

## 2. Analyst price targets / upgrade-downgrade, beyond yfinance

| Source | Endpoint(s) | Free tier | Individual analyst NAME? | PIT notes |
|---|---|---|---|---|
| Finnhub | `/stock/recommendation`, `/stock/price-target`, `/stock/upgrade-downgrade` | 60 calls/min free | **No** — `upgrade-downgrade` returns `company` (brokerage firm), not a person | `gradeTime` timestamped; usable for backtest with date filter |
| Financial Modeling Prep (FMP) | Price Target / Analyst Estimates APIs | 250 req/day free (Basic) | Not confirmed exposed; likely brokerage-level only | Free EOD data is T-1, not real-time |
| **Benzinga** | Analyst Insights (`analyst_id`, `firm`, no name) vs. **Analyst Ratings** (`GET /ratings` — has `analyst` personal name field, e.g. "Atif Malik", distinct from `firm`) | **No published free tier; paid/sales-contact only** | **Yes — the one confirmed source with individual analyst identity** | Ratings changes posted pre-market and intraday — good PIT if self-archived |
| TipRanks | No public REST API for general use; new `mcp.tipranks.com` connector, tiers unconfirmed | Unclear/likely paid | Yes on-site (their core product — "Top Analysts" leaderboard) but ToS **explicitly bans scraping/reuse beyond the documented API** | N/A |
| MarketBeat | No public API; third-party scrapers describe per-rating pages with analyst name + a "Ratings Screener" sortable by analyst | Free to browse, no API | Yes on-page, but scraping legality unconfirmed (check robots.txt/ToS before automating) | N/A |
| Nasdaq.com analyst research | HTML only, no API found | Free to browse | Not confirmed | N/A |
| Alpha Vantage | No confirmed price-target endpoint; `EARNINGS_ESTIMATES` flagged Premium | 25 req/day, 5/min free (thin, has shrunk over time from 500→100→25/day) | No | N/A |

**Bottom line**: Benzinga's `GET /ratings` is the cleanest machine-readable source that names the individual analyst (not just the brokerage) — but it's paid with unpublished pricing. TipRanks/MarketBeat expose analyst identity on-site but scraping likely violates ToS (explicit for TipRanks). Finnhub/FMP/Alpha Vantage stay at the same brokerage-only granularity as yfinance.

## 3. Earnings calendars and estimates

| Source | Endpoint | Format | Free tier | PIT notes |
|---|---|---|---|---|
| Nasdaq.com (undocumented) | `api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD` | JSON | No key, undocumented/unofficial, needs a browser User-Agent (corroborated by `finance_calendars` PyPI wrapper) | Date-parameterized, but Nasdaq's own consensus estimates reflect current, not as-of-date, consensus |
| Alpha Vantage `EARNINGS_CALENDAR` | `alphavantage.co/query?function=EARNINGS_CALENDAR&horizon=3month&apikey=KEY` | CSV default, JSON via `datatype=json` | 25 req/day, 5/min free | Forward-looking only, no historical calendar archive — must snapshot yourself |
| Finnhub earnings calendar | `/calendar/earnings` | JSON | Believed accessible at standard 60/min tier (not independently confirmed) | Same snapshot caveat |
| yfinance | `Ticker(x).calendar` / `.earnings_dates` | Python objects | Free, unofficial, unpublished throttling | Current/most-recent only, no vintage history; schema has broken historically |

## 4. Congress trades, 13F, Form 4, ARK holdings

| Source | Access | Format | Cost | PIT notes |
|---|---|---|---|---|
| House Clerk PTR | `disclosures-clerk.house.gov/public_disc/financial-pdfs/{YYYY}FD.zip` (verified live — valid ZIP with index XML/TXT; per-filing trade data still requires opening linked PDF/XML by DocID) | ZIP→index; per-filing PDF/XML | Free | Filing date embedded and reliable; disclosures required within 30–45 days of trade — use filing date, not trade date, as info-available timestamp |
| Senate eFD | `efdsearch.senate.gov/search/` | HTML/POST form, no confirmed JSON API (403/405 on GET); historically requires session/CSRF + ToS agreement, no bulk redistribution | N/A | Same filing-vs-trade-date structure as House |
| Quiver Quantitative | `api.quiverquant.com` | JSON | Free tier existence unconfirmed this session; web Premium plan seen at $25/mo | Mirrors underlying House/Senate PIT quality |
| Capitol Trades | Blocked (403); no confirmed public API | HTML | Free to browse | N/A |
| Unusual Whales | `unusualwhales.com/api`, blocked (403) | JSON | Paid only, pricing not retrieved | N/A |
| SEC EDGAR (submissions/XBRL) | `data.sec.gov/submissions/CIK##########.json`, `.../api/xbrl/companyfacts/...`, `.../frames/...` (verified live) | JSON | Free, requires descriptive `User-Agent` header; **10 req/sec fair-access limit, enforced** | Near-real-time updates with accession/acceptance timestamps — good PIT source |
| Form 13F structured data sets | `sec.gov/data-research/sec-markets-data/form-13f-data-sets`, quarterly ZIPs (verified live) | Flattened XML→tabular | Free | Traceable to accepted filing date; real PIT constraint is the inherent 45-day post-quarter reporting lag |
| Form 4 | No confirmed dedicated real-time RSS found this session; structured XML per filing via EDGAR accession URL; bulk via `sec.gov/Archives/edgar/full-index/` | XML per filing; daily bulk index | Free, same 10 req/sec limit | Filed within 2 business days of transaction — good PIT if keyed on acceptance-datetime |
| ARK daily holdings CSV | Not independently confirmed this session (guessed URLs 404/403'd); historically on `ark-funds.com`, mirrored at `cathiesark.com`/stockanalysis.com — **re-verify exact current URL** | CSV | Free | If archived daily, one of the better PIT sources surveyed — an as-of-date file, not a mutable "current state" endpoint |

## 5. Prediction markets

| Source | Access | Auth | FDA/Fed/election coverage | PIT notes |
|---|---|---|---|---|
| Kalshi | `docs.kalshi.com` (moved from old readme.io); base API historically `trading-api.kalshi.com/trade-api/v2/...`. **Live test this session: `/markets` and `/exchange/status` both returned 401 even for reads that should be public** — either auth is now required for all reads, or WAF filtering. Treat as requiring signup/key until re-verified. | Required (per live test) | Fed rate decisions, elections flagship; FDA-approval markets exist opportunistically, not guaranteed coverage | Immutable historical price series once resolved — good PIT if usable |
| **Polymarket** | **Verified live, no auth**: `gamma-api.polymarket.com/markets?limit=N` returns full market objects (question, resolution criteria, current/24h/7d/30d/1y prices, volume, liquidity) | None for Gamma API reads | Politics, macro/Fed, crypto; FDA markets opportunistic | No native historical time-series-by-timestamp endpoint on free tier — must poll repeatedly to build your own history |

## 6. Government policy signals

| Source | Access | Format | Cost | PIT notes |
|---|---|---|---|---|
| Federal Register API | `federalregister.gov/api/v1/documents.json?...` — **verified live**, real JSON with pagination. Note: the human-facing site has Cloudflare bot-protection, but `/api/v1/` JSON endpoints work directly | JSON | Free, no key, no documented hard rate limit | Excellent — every document has `publication_date`/`document_number`, immutable once published |
| Executive orders | Same API, filter `conditions[type][]=PRESDOCU` + `presidential_document_type=executive_order` (filter confirmed working) | JSON | Free | Same as above |
| Section 232 investigations (Commerce/BIS) | Best captured via Federal Register API filtered to agency `industry-and-security-bureau` — verified returns real notices (anthracite coal, robotics/industrial machinery, steel/aluminum derivatives). BIS's own site redirects without a distinct feed. | JSON | Free | Same immutable-register property |
| DOE Loan Programs Office | Could not confirm a feed; `energy.gov/lpo/listings/lpo-announcements` and `/lpo/articles` both 404'd. Likely press-release HTML only; check `energy.gov/lpo/newsroom` directly, or catch loan-guarantee notices via Federal Register as backstop | HTML (unconfirmed) | Free | N/A |
| USTR tariff notices | `ustr.gov/.../press-releases` — verified live, HTML-only, no RSS, only an email subscribe form. Formal Section 301/tariff actions also typically hit the Federal Register. | HTML (site) / JSON (via Federal Register cross-reference) | Free | Prefer the Federal Register route for structured, PIT-safe access |
| CHIPS Act grants (Commerce/NIST) | Could not confirm a dedicated feed (`nist.gov/chips/funding-opportunities` 404'd). Likely Commerce.gov/NIST press releases (HTML); cross-check Federal Register for formal NOFO filings. | HTML (unconfirmed) / JSON via Federal Register | Free | N/A |

## Summary: access tiers

**Free, no signup**: Federal Register API (all endpoints), SEC EDGAR submissions/XBRL/13F bulk data (User-Agent required, 10 req/sec), House Clerk PTR bulk ZIP, Nasdaq.com undocumented calendar JSON, Polymarket Gamma API, openFDA (rate-limited without key).

**Free tier with signup/key**: openFDA (key raises 1,000/day → 120,000/day — the single highest-value free upgrade found), Finnhub (60/min), FMP (250/day), Alpha Vantage (25/day, 5/min — thin and shrinking), Kalshi (unconfirmed if reads now require a key).

**Paid only / no meaningful free tier**: Benzinga Analyst Ratings/Insights API (the one source with individual analyst names), Quiver Quantitative API (web product has a $25/mo-ish tier; API-specific free tier unconfirmed), Unusual Whales, TipRanks (ToS bans reuse of any scraped data regardless of tier).

**Delayed/latest-snapshot-only data — PIT risk flagged**: Alpha Vantage/Finnhub/FMP consensus estimates and price targets (current consensus only, no as-of-date history endpoint on free tiers), yfinance `earnings_dates`/`calendar` (latest-state only), FDA drug label endpoint (current text by default), ClinicalTrials.gov v2 (no native history/diff API for "results posted" status changes).

**Access-tooling caveat**: Several vendor sites (Finnhub, FMP, Capitol Trades, Unusual Whales, TipRanks generic pages, Kalshi's trading-api domain) are React/SPA or bot-protected and returned only titles or 403s to a generic fetcher this session — re-verify their exact rate limits/pricing with an authenticated session or real browser before committing pipeline code to figures quoted here from secondary sources.

---

# PART 3 — Analyst Target Prices, Implied Upside, and Revision Literature

## A. Mechanics of "consensus target-implied upside" from yfinance-style data

Standard formula: `upside % = targetMeanPrice / currentPrice − 1`. Variants: median-based (`targetMedianPrice`, more robust to outliers, not always exposed by vendors); dispersion measures using `targetHighPrice`/`targetLowPrice` (e.g. `(high − low) / mean`), which turn out to be *more* informative than the level itself (see B.4 below); `numberOfAnalystOpinions` typically used as a coverage/reliability filter (require ≥3–5 analysts) rather than a weight, since raw vendor means are unweighted by analyst skill (contrast with StarMine, C.4).

Known data-quality caveats relevant to a yfinance pipeline:
1. **Stale/withdrawn targets not flagged** — yfinance's snapshot has no per-analyst timestamp; analysts slow to cut a too-high target after bad news are exactly the mechanism Palley-Steffen-Zhang (B.4) show drives dispersion up and flips implied-upside informativeness negative.
2. **Small analyst counts** → a single stale/idiosyncratic target can dominate the "consensus," especially in small/mid caps.
3. **Anchoring/round-number bias** — general behavioral-finance point; published targets become anchors for later revisions.
4. **Targets reissued concurrently with a big price move** — a target-implied-upside computed right after a large gap can reflect an old target against a new price rather than a genuine re-derivation (a short-horizon version of the staleness problem; motivates why Brav & Lehavy study the *revision* event rather than the level on an arbitrary day).
5. **Structural optimism bias** baked into the level itself, per the entire literature below (targets average 20–30%+ above current price as a persistent regularity).

## B. Target-price LEVEL: optimism bias, poor-to-negative predictive power

- **Brav & Lehavy (2003)**, *Journal of Finance* 58(5):1933–1967, "An Empirical Analysis of Analysts' Target Prices." Significant short-term market reaction to target-price issuance (incremental to recommendation/EPS revisions), but the average 1-year target is **28% above current price** — a persistent optimism wedge; long-run target/price co-movement much weaker than the short-term reaction. [JF](https://onlinelibrary.wiley.com/doi/10.1111/1540-6261.00593) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=266180) · [author PDF](https://webuser.bus.umich.edu/rlehavy/BL.pdf).
- **Bradshaw, Brown & Huang (2013)**, *Review of Accounting Studies* 18(4), "Do Sell-Side Analysts Exhibit Differential Target Price Forecasting Ability?" 12-month implied returns exceed actual returns by ~15% on average; absolute forecast errors average 45%; only 38% of targets hit at 12 months (64% hit at some point during the year); differential analyst skill is statistically significant but economically weak. [SSRN](https://www.ssrn.com/abstract=2535100) · [Springer](https://link.springer.com/article/10.1007/s11142-012-9216-5) · [free PDF](http://assets.csom.umn.edu/assets/37727.pdf).
- Related Bradshaw work: "Analyst Target Price Optimism Around the World" (41 countries — optimism larger where investment-banking/incentive benefits of biased research are greater) [ResearchGate](https://www.researchgate.net/publication/256032053_Analyst_Target_Price_Optimism_Around_the_World); "The Effects of Analyst-Country Institutions on Biased Research: Evidence from Target Prices," *JAR* 57(1), 2019 — optimism linked to weaker investor protection/legal enforcement [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/1475-679X.12245).
- **Bilinski, Lyssimachou & Walker (2013)**, *The Accounting Review* 88(3):825–851, "Target Price Accuracy: International Evidence" — 16 countries; accuracy varies with disclosure quality, legal origin, IFRS adoption; importantly finds **persistent analyst-level accuracy differences** (experience, breadth, country specialization, broker size) — seeds the "who revised" angle. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1915082).
- **Da & Schaumburg (2011)**, *Journal of Financial Markets* 14(1):161–192, "Relative Valuation and Analyst Target Price Forecasts" — key distinction: **within-industry relative valuation implicit in targets IS informative; the absolute level is not.** A strategy sorting on industry-relative implied valuation (1997–2004, S&P 500) earns significant abnormal returns. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1386418110000364) · [free PDF](https://academicweb.nd.edu/~zda/TP2.pdf).
- **Dechow & You (2020)**, *The Accounting Review* 95(6):125–149, "Understanding the Determinants of Analyst Target Price Implied Returns" — closest academic analogue to the repo's own backtest. Decomposes implied returns into (i) genuine future returns, (ii) fundamentals-forecast error, (iii) errors mapping expected return to risk proxies (the **largest** component, ~a quarter of cross-sectional variance), (iv) incentive bias; investors don't fully back the bias out. A naive long-short replication (paperswithbacktest.com, 1990–2026) nets ~0.05%/yr, Sharpe 0.04, max drawdown −31.6% — consistent with the level being near-worthless standalone once costs/risk are included. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2574727) · [AAA](https://publications.aaahq.org/accounting-review/article/95/6/125/4230).

**Direct anomaly literature — high implied-upside underperforms:**
- **Palley, Steffen & Zhang (2024)**, *Management Science* 71(3):2264–2288, "The Effect of Dispersion on the Informativeness of Consensus Analyst Target Prices" — likely the best explanation for the repo's own t −3.6 to −7.2 finding. Implied-return/realized-return correlation is **positive under low dispersion, strongly negative under high dispersion**: incentive-driven analysts leave stale (too-high) targets after bad news, dispersion rises mechanically as price falls, so in high-dispersion names the highest-implied-upside stocks are precisely the ones about to underperform. A dispersion-conditioned long/short earns >11%/yr. [Management Science/INFORMS](https://pubsonline.informs.org/doi/10.1287/mnsc.2021.03549) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3467800) · [free PDF](http://www.asapalley.com/uploads/4/7/5/0/47502723/palleysteffenzhang2021dispersionanalysttargetprices.pdf) · [Yale SOM summary](https://insights.som.yale.edu/insights/the-key-information-hiding-behind-consensus-target-stock-prices).
- **Han, Kang & Kim (2022)**, *Journal of Financial Markets* 59(B), "Betting Against Analyst Target Price" — initial price reaction matches direction, then price **drifts in the opposite direction** for an extended period; long-short exploiting the reversal earns ~0.75%/mo (~10%/yr), 1999–2020 US, stronger among large/liquid names. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1386418121000562) · [free PDF](https://durham-repository.worktribe.com/OutputFile/1239036).
- **Li, Feng, Yan & Wang (2021)**, *North American Journal of Economics and Finance* 56:101385 — target-price **dispersion itself** (not level) positively predicts returns up to 24 months (high-minus-low decile spread >2%/month), framed as risk-based — a distinct mechanism from Palley-Steffen-Zhang's staleness story; both can be true simultaneously. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S106294082100022X).
- **Grinblatt, Jostova & Philipov**, NBER WP 31094, "Explaining (Some) Anomalies: The Role of Analyst Bias" — predictable earnings-forecast bias explains 14 known low-return anomalies concentrated in hard-to-forecast names (high credit risk, high idiosyncratic vol); highest-predicted-bias quintile underperforms lowest by 6–19%/yr risk-adjusted. [UCLA Anderson PDF](https://anderson-review.ucla.edu/wp-content/uploads/2021/03/Grinblatt_SSRN-id2653666.pdf).

**Synthesis**: the literature is essentially unanimous that (a) target-price *level* carries a large, incentive/institution-driven optimism bias, and (b) once conditioned on dispersion or examined for reversal dynamics, the naive unconditional implied-upside signal can go strongly **negative** cross-sectionally — a specific economic mechanism matching the repo's own measured t-stats of −3.6 to −7.2. The one place genuine positive information survives is **industry-relative** valuation embedded in targets (Da & Schaumburg), not the absolute number.

## C. Revision momentum and analyst-level skill persistence (the more promising angle)

- **Womack (1996)**, *Journal of Finance* 51(1):137–167, "Do Brokerage Analysts' Recommendations Have Investment Value?" — foundational revision-momentum result: buy-change announcement drift +2.4% (short-lived); sell-change drift −9.1% (persists ~6 months). [JF](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1996.tb05205.x).
- **Gleason & Lee (2003)**, *The Accounting Review* 78(1):193–225, "Analyst Forecast Revisions and Market Price Discovery" — market underreacts more to low-innovation (toward-consensus) revisions than high-innovation ones; price discovery is faster when the revising analyst is an Institutional Investor All-Star, even relative to more-accurate-but-obscure analysts — direct precedent for "who revised" mattering independent of the number. [AAA](https://meridian.allenpress.com/accounting-review/article-abstract/78/1/193/53357) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=370425).
- **Mikhail, Walther & Willis (1997)**, *Journal of Accounting Research* 35:131–157, "Do Security Analysts Improve Their Performance with Experience?" — firm-specific experience improves accuracy (learning-by-doing); market weights more-experienced analysts' forecasts more heavily. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=56568). Follow-on: "Do Security Analysts Exhibit Persistent Differences in Stock Picking Ability?" *JFE* 74(1):67–91, 2004 — extends to recommendation-profitability persistence.
- **Cooper, Day & Lewis (2001)**, *Journal of Financial Economics* 61(3):383–416, "Following the Leader: A Study of Individual Analysts' Earnings Forecasts" — ranks analysts by forecast **timeliness**, abnormal volume triggered, and accuracy; "lead" analysts (by timeliness) have significantly greater price impact than "follower" analysts who revise toward already-known information. Direct precedent for weighting revisions by analyst identity/timeliness. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X01000678).
- **StarMine (Refinitiv/LSEG) methodology** (public whitepapers, no academic paper): **SmartEstimate** reweights I/B/E/S consensus excluding stale/erroneous estimates and weighting remaining analysts by historical accuracy + recency (5-star analysts weighted highest) — the commercial analogue of Cooper-Day-Lewis/Mikhail-Walther-Willis. **Predicted Surprise** = simple consensus − SmartEstimate; LSEG claims |Predicted Surprise| > 2% correctly signs the actual earnings surprise ~70% of the time. **Analyst Revisions Model (ARM)** predicts future changes in analyst sentiment/earnings momentum on a 1–100 scale. [LSEG whitepaper PDF](https://www.lseg.com/content/dam/data-analytics/en_us/documents/white-papers/lseg-starmine-smart-forecast-model-whitepaper.pdf) · [SmartEstimates catalogue](https://www.lseg.com/en/data-catalogue/analytics/quantitative-analytics/starmine-smartestimates).
- **2024–2026 LLM-on-analyst-text papers**:
  - **"Do Sell-side Analyst Reports Have Investment Value?"** (arXiv 2502.20489, 2025) — most directly relevant: embeds narrative text of ~1.2M analyst reports (2000–2023) with LLMs, fits ML forecasts of long-horizon returns from the embeddings; portfolios formed on narrative-derived forecasts earn sizable performance **incremental to** the analyst's own numerical outputs (target price/EPS) — the text contains alpha the numbers don't capture. Directly supports a pivot toward "who/how revised, and what they wrote" over the raw level. [arXiv](https://arxiv.org/abs/2502.20489).
  - **"The Promise and Peril of Generative AI: Evidence from GPT as Sell-Side Analysts"** (arXiv 2412.01069, 2024) — GPT's own post-earnings forecasts show human-like but not more-accurate narrative attention; caution against assuming LLM-*generated* forecasts are automatically good (distinct from LLM-*extracted*-signal-from-human-text, above). [arXiv PDF](https://arxiv.org/pdf/2412.01069).
  - **"AI in Investment Analysis: LLMs for Equity Stock Ratings"** (arXiv 2411.00856, ACM ICAIF 2024) — GPT-4-32k with fundamentals/market/news generating multi-horizon ratings; methodology reference, weaker as alpha evidence. [arXiv](https://arxiv.org/abs/2411.00856).
  - "The Value of Information from Sell-side Analysts" (arXiv 2411.13813) — surfaced, not independently verified this session; flagged for follow-up.

**Assessment**: the classical revision/analyst-identity literature (Womack, Gleason-Lee, Mikhail-Walther-Willis, Cooper-Day-Lewis) is substantially better-supported for a positive signal than the target-LEVEL literature, and the mechanism is coherent with the repo's negative level result: revisions (especially high-innovation ones, and ones from experienced/timely/skilled analysts) carry real incremental price-discovery information that the raw consensus level, contaminated by optimism/staleness/incentive bias (Part B), does not. StarMine's commercial methodology and the 2025 LLM-embedding paper both operationalize exactly this "who/how, not just what" distinction.

---

# Open follow-ups if a second research pass is wanted
1. Re-verify the ~15 secondary-aggregator-only FDA catalysts against each company's own IR page before using them in a receipt.
2. Pull full text of Singh et al. (2022) PLoS ONE (PMID 36054103) for a rigorous approval-vs-CRL stock-reaction magnitude, and a dedicated FDA-approval-vs-CRL event study if one can be found.
3. Verify whether Kalshi's public market-read endpoints now genuinely require authentication (401 seen live this session) before building around them; Polymarket's Gamma API is confirmed no-auth.
4. Confirm the current ARK Invest daily-holdings CSV URL directly (site/CDN structure has changed multiple times; guessed URLs 404/403'd this session).
5. Pull Benzinga's actual Analyst Ratings API pricing (sales-contact-gated) to weigh against building an analyst-identity dataset in-house from MarketBeat/TipRanks HTML (ToS risk noted).
