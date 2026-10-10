# ATLAS — LLM Portfolio v3

October 10,2026 SGT · **Inactive discussion draft; owner review pending.**

This refresh preserves the human-reviewed v2 portfolio (`5d137b013692a737`) and its record. Proposed weights carry forward that review, cap VRT from 12% to 10%, and move the two percentage points to cash: 96% stocks / 4% cash. They are declared review weights, not a newly calibrated optimizer result. No book is frozen, activated or ordered. SPY has zero portfolio weight and appears only as a separate comparator.

The draft horizon is 126 trading sessions (approximately six months). Aegis’s available component estimates below use their own 21-session horizon. Analyst target ranges are provider snapshots whose target horizon is not recorded; they are research context and never a 21-session forecast. The existing negative result on ranking by analyst target-level upside remains binding. Net raises are 90-calendar-day context, not a demonstrated directional edge.

Prices are the existing October 9 daily unadjusted closes, not live quotes or entry prices. Each source pull timestamp is retained in the companion JSON. The global-price contract excludes dividends and FX. Prices are shown in cached quote units; instrument class, listing venue and quote currency remain unverified in the bounded identity inventory. Confirm those fields and corporate actions before an entry. Analyst observations are independently timestamped and may predate the close.

## Proposed weights and dated market context

|Name|Weight / Δ vs v2|Close / session|Analyst low–median–high / observed|90d raises–cuts (net)|Existing E[r21] / source|
|---|---|---|---|---|---|
|VRT|10.0% / -2.0pp|242.78 / 2026-10-09|236.00–340.00–427.00 / 2026-10-09T14:10:13|0–4 (-4)|unavailable; not zero|
|GEV|9.0% / +0.0pp|1,004.73 / 2026-10-09|940.00–1,250.00–1,450.00 / 2026-10-09T13:34:43|8–0 (+8)|unavailable; not zero|
|MU|9.0% / +0.0pp|1,029.00 / 2026-10-09|361.00–1,550.00–3,000.00 / 2026-10-09T13:48:50|7–3 (+4)|unavailable; not zero|
|TSM|7.0% / +0.0pp|453.31 / 2026-10-09|440.00–538.50–700.00 / 2026-10-09T14:07:26|7–0 (+7)|+0.000% / equal|
|HOOD|7.0% / +0.0pp|109.02 / 2026-10-09|57.00–140.00–170.00 / 2026-10-09T13:38:07|17–5 (+12)|unavailable; not zero|
|NVT|6.0% / +0.0pp|167.43 / 2026-10-09|136.00–210.00–240.00 / 2026-10-09T13:51:27|6–0 (+6)|unavailable; not zero|
|AVGO|6.0% / +0.0pp|361.54 / 2026-10-09|215.88–535.00–715.00 / 2026-10-09T13:16:19|6–4 (+2)|unavailable; not zero|
|CLS|5.0% / +0.0pp|362.16 / 2026-10-09|375.00–480.00–550.00 / 2026-10-09T13:23:22|3–2 (+1)|unavailable; not zero|
|BE|4.0% / +0.0pp|280.50 / 2026-10-09|97.00–303.00–390.00 / 2026-10-09T13:17:43|8–6 (+2)|unavailable; not zero|
|MP|4.0% / +0.0pp|46.14 / 2026-10-09|53.00–73.00–100.00 / 2026-10-09T13:48:01|0–5 (-5)|unavailable; not zero|
|LEU|2.0% / +0.0pp|142.44 / 2026-10-09|167.00–217.00–340.00 / 2026-10-09T13:44:03|2–4 (-2)|unavailable; not zero|
|CCJ|2.0% / +0.0pp|88.06 / 2026-10-09|82.95–130.57–168.75 / 2026-10-09T13:21:50|1–2 (-1)|unavailable; not zero|
|NOVT|3.0% / +0.0pp|141.28 / 2026-10-09|194.00–194.50–195.00 / 2026-10-09T13:50:38|0–0 (+0)|unavailable; not zero|
|IONQ|1.0% / +0.0pp|39.89 / 2026-10-09|41.85–62.50–100.00 / 2026-10-09T13:40:27|0–0 (+0)|unavailable; not zero|
|VRTX|4.0% / +0.0pp|510.08 / 2026-10-09|350.00–578.00–672.00 / 2026-10-09T14:10:15|9–0 (+9)|unavailable; not zero|
|WST|3.0% / +0.0pp|366.00 / 2026-10-09|340.00–410.00–459.00 / 2026-10-09T14:12:04|5–0 (+5)|unavailable; not zero|
|COGT|3.0% / +0.0pp|31.00 / 2026-10-09|45.00–55.00–62.00 / 2026-10-09T13:24:11|2–0 (+2)|unavailable; not zero|
|VKTX|3.0% / +0.0pp|28.51 / 2026-10-09|38.00–95.00–125.00 / 2026-10-09T14:09:43|2–2 (+0)|unavailable; not zero|
|AGIO|2.0% / +0.0pp|31.81 / 2026-10-09|32.00–43.50–73.00 / 2026-10-09T13:12:10|4–3 (+1)|unavailable; not zero|
|RGEN|1.0% / +0.0pp|173.88 / 2026-10-09|145.00–200.00–235.00 / 2026-10-09T13:58:15|4–0 (+4)|unavailable; not zero|
|BBIO|1.0% / +0.0pp|65.35 / 2026-10-09|80.00–110.00–156.00 / 2026-10-09T13:17:20|10–2 (+8)|unavailable; not zero|
|PRAX|1.0% / +0.0pp|259.86 / 2026-10-09|188.00–575.00–1,201.00 / 2026-10-09T13:56:05|5–0 (+5)|unavailable; not zero|
|DKNG|3.0% / +0.0pp|19.58 / 2026-10-09|20.00–32.50–76.00 / 2026-10-09T13:27:39|5–12 (-7)|unavailable; not zero|
|CASH|4.0% / +2.0pp|USD review reserve|—|—|—|

The E[r] receipt is production dated October 9, written 21:07:49UTC. Equal component weights are not evidence of learned skill; asleep or absent components remain unavailable. News-digest forecasts are shadow evidence and the news-to-E[r] bridge remains unverified. The validated learning trace currently retains zero news trust, so the draft does not increase a weight to manufacture a news effect.

## Reasons, catalysts, risks and proposed review exits

Every row retains a126-session review horizon; dated catalysts below are separate checkpoints. The exits are proposed thesis review conditions, not automatic stop orders. Regulatory targets may change, and binary-event losses can jump past a quoted stop. Bloomberg WLS eligibility is **UNVERIFIED for every stock** until the authentic Terminal export is captured.

|Name|Dated primary-source context and reason to retain for review|Catalyst / date|Risk and proposed exit review|
|---|---|---|---|
|VRT|Q2 release guides Q3 organic sales growth to 34–36%; execution and capacity remain the test. [Company/filing source](https://investors.vertiv.com/news/news-details/2026/Vertiv-Reports-Strong-Second-Quarter-2026-with-Diluted-EPS-Growth-of-53-Adjusted-Diluted-EPS-Growth-of-60-Raises-Full-Year-2026-Guidance-Across-All-Key-Metrics/default.aspx)|Q3 result date not independently verified here|Review reducing/exiting if organic growth misses the stated guide or backlog conversion stalls.|
|GEV|Company calendar confirms the Q3 earnings webcast on October 28. [Company/filing source](https://www.gevernova.com/investors/events)|2026-10-28, 07:30 EDT|Review reducing/exiting if turbine reservations fail to convert, orders slow or cash guidance is cut.|
|MU|September 30 FQ4 results are now reported. The earlier upcoming-print thesis is obsolete; AI memory demand remains the operating premise. [Company/filing source](https://investors.micron.com/news/press-release/2026/Micron-Technology-Inc--Reports-Record-Fiscal-Fourth-Quarter-and-Full-Year-2026-Results/)|Next earnings date unverified; monitor subsequent fiscal 2027 guidance|Review reducing/exiting on a material guidance cut or deterioration in memory pricing; prior September 30 event is already past.|
|TSM|October 8 filing reports September revenue up 54.6% year over year and down 0.6% month over month. These comparisons have different baselines. [Company/filing source](https://www.sec.gov/Archives/edgar/data/1046179/000104617926000680/tsm-revenue20261008.htm)|October 15 Q3 date remains prior-book context pending a current official calendar capture|Review reducing/exiting on a capex-guide cut or deterioration in the operating margin outlook; Taiwan and ADR risks remain.|
|HOOD|October 1 announcement sets Q3 results for October 27 after close; it supersedes the old book's November 4 date. [Company/filing source](https://investors.robinhood.com/news-releases/news-release-details/robinhood-markets-inc-announce-third-quarter-2026-results)|2026-10-27 after US close|Review reducing/exiting on adverse event-contract regulation or deterioration in funded-customer economics.|
|NVT|October 1 announcement confirms Maverick Power acquisition completed for$1.75 bn, subject to adjustments. Closing is no longer a future catalyst. [Company/filing source](https://investors.nvent.com/press-releases/press-release-details/2026/nVent-Completes-Acquisition-of-Maverick-Power/default.aspx)|Next results date unverified; monitor acquisition integration|Review reducing/exiting on integration failure, organic-order deterioration or margin pressure; remove the obsolete November 20 close condition.|
|AVGO|September 2 Q3 release reports revenue$29.6 bn and guides Q4 revenue to about$34.8 bn. Custom accelerators/networking remain the operating thesis. [Company/filing source](https://investors.broadcom.com/news-releases/news-release-details/broadcom-inc-announces-third-quarter-fiscal-year-2026-financial)|Next fiscalQ4 result date unverified|Review reducing/exiting on AI revenue-guide cuts or major custom-silicon customer/program losses.|
|CLS|Company calendar lists Q3 results and investor/analyst day on October 27. August equity offering makes dilution part of the capital-allocation review. [Company/filing source](https://corporate.celestica.com/)|2026-10-27, Q3/investor day|Review reducing/exiting on hyperscaler order delays, margin compression or dilution without adequate growth conversion.|
|BE|July 28 Q2 filing raises full-year revenue guidance to$3.9–4.2 bn. The behind-the-meter thesis still depends on installations becoming profitable revenue. [Company/filing source](https://www.sec.gov/Archives/edgar/data/1664703/000162828026050150/ex991_q226financialresults.htm)|Q3 date unverified|Review reducing/exiting on margin/guidance cuts or persistent commissioning and supply delays.|
|MP|October 8 announcement sets Q3 results for November 5. Strategic magnet-production thesis remains prior reviewed context, not a new verified contract claim. [Company/filing source](https://investors.mpmaterials.com/investor-news/news-details/2026/MP-Materials-Announces-Date-for-Third-Quarter-2026-Financial-Results-and-Webcast/default.aspx)|2026-11-05 after US close|Review reducing/exiting if supported production/offtake economics weaken or material legal/policy protections are withdrawn.|
|LEU|September 17 Antares HALEU contract and September 9 equity/warrant financing are recorded company announcements. Private offtake does not eliminate dilution or government-contract risk. [Company/filing source](https://investors.centrusenergy.com/news-releases)|Build-out and offtake delivery milestones; next print unverified|Review reducing/exiting if offtake fails to convert or financing/production execution materially deteriorates.|
|CCJ|The 2026 Q2 release schedules Q3 results before market open on October 30. [Company/filing source](https://www.sec.gov/Archives/edgar/data/1009001/000119312526326768/d125942dex991.htm)|2026-10-30 before markets open|Review reducing/exiting on sustained production/delivery misses or adverse contract economics; do not treat unverified acid-supply headlines as facts.|
|NOVT|August 5 Q2 filing reports 10.3% revenue growth and 9.3% organic growth. The prior humanoid order thesis has not been independently reconfirmed in this packet. [Company/filing source](https://www.sec.gov/Archives/edgar/data/1076930/000119312526335356/novt-ex99_1.htm)|Next Q3 date unverified; prior November 10 estimate excluded as confirmed date|Review reducing/exiting if the hypothesized robotics order fails to convert or organic growth/backlog weakens.|
|IONQ|September 22 company announcement describes an end-to-end real-time decoder. A corporate announcement is not independent replication or commercial-scale fault tolerance. [Company/filing source](https://investors.ionq.com/news/news-details/2026/IonQ-Demonstrates-Industrys-First-End-to-End-Real-Time-Quantum-Error-Decoder/default.aspx)|Independent replication and subsequent delivery evidence; dates unverified|Review reducing/exiting on nonreplication, unmet delivery milestones or material dilution.|
|VRTX|August 3 Q2 release raises annual revenue guidance and records povetacicept's FDA target action date. Regulatory acceptance is not approval. [Company/filing source](https://investors.vrtx.com/news-releases/news-release-details/vertex-reports-second-quarter-2026-financial-results)|2026-11-30 PDUFA target, subject to FDA change|Review reducing/exiting on CRL, materially narrower label or operating guidance deterioration.|
|WST|October 8 notice sets Q3 results before market open on October 29. The old broker target is not used as the sizing signal. [Company/filing source](https://www.investor.westpharma.com/news-releases/news-release-details/west-host-third-quarter-2026-conference-call)|2026-10-29, 08:00 EDT call|Review reducing/exiting on component destocking or sustained margin/guidance deterioration.|
|COGT|The Q2 corporate update records November 30 GIST and December 30 NonAdvSM PDUFA targets. Both are regulatory deadlines, not guaranteed approvals. [Company/filing source](https://investors.cogentbio.com/news-releases/news-release-details/cogent-biosciences-reports-recent-business-highlights-and-11)|2026-11-30 and 2026-12-30, FDA target dates|Review reducing/exiting on CRL, material safety concerns or adverse regulatory changes; binary gap risk cannot be bounded by a stop.|
|VKTX|October 6 announcement starts oral-maintenance dosing study; September 28 financing announcement follows the maintenance-data release. Trial initiation is not efficacy confirmation. [Company/filing source](https://ir.vikingtherapeutics.com/)|Maintenance trial progress; no confirmed next data date in this packet|Review reducing/exiting on adverse tolerability/durability results or materially unfavourable dilution.|
|AGIO|Q2 update records mitapivat sickle-cell Priority Review and November 1 PDUFA goal date, with a confirmatory Phase 3 trial underway. [Company/filing source](https://investor.agios.com/news-releases/news-release-details/agios-reports-second-quarter-2026-financial-results-and-provides)|2026-11-01 FDA goal date; November 5 results call listed on company news page|Review reducing/exiting on CRL, narrower commercial opportunity or adverse confirmatory evidence.|
|RGEN|July 28 Q2 release raises organic-growth guidance to 10.5–13.5% and describes the proposed BioLife acquisition. Growth and integration remain separate risks. [Company/filing source](https://investors.repligen.com/press-releases/news-details/2026/Repligen-Reports-Second-Quarter-2026-Financial-Results-and-Updates-Full-Year-2026-Financial-Guidance/default.aspx)|Next Q3 date unverified|Review reducing/exiting on order deterioration, book-to-bill below 1 or failed integration economics.|
|BBIO|October 5 release presents exploratory cardiac data and reiterates BBP-418's November 27 FDA target. Exploratory biomarkers do not independently establish long-term clinical benefit. [Company/filing source](https://investor.bridgebio.com/news/news-details/2026/BBP-418-Demonstrates-Potential-to-Be-Disease-Modifying-Therapy-Restoring-Cardiac-and-Disease-Markers-to-Unaffected-Levels/default.aspx)|2026-11-27 PDUFA target|Review reducing/exiting on CRL or material safety/efficacy weakness; binary gap risk remains.|
|PRAX|August 6 update identifies December 27 as relutrigine's extended PDUFA date; ulixacaltamide is January 29,2027. The compound and horizon must stay distinct. [Company/filing source](https://ir.praxismedicines.com/news-releases/news-release-details/praxis-precision-medicines-provides-corporate-update-and-20)|2026-12-27 relutrigine;2027-01-29 ulixacaltamide|Review reducing/exiting on CRL, further adverse review findings or materially negative EMERALD data.|
|DKNG|Company July 15 announcement confirms the regulated sports/event-contract business scope and August Q2 reporting. Current Q3 date and the old growth/hold claims remain unverified here. [Company/filing source](https://ir.aboutdraftkings.com/news/news-details/2026/DraftKings-to-Release-Second-Quarter-2026-Results-on-August-6-2026-and-Host-Conference-Call-on-August-7-2026/default.aspx)|Q3 date unverified; next earnings checkpoint required|Review reducing/exiting on sustained hold compression or adverse event-contract regulation; do not promote old target upside into evidence.|

## Changes, comparators and evidence limits

VRT 12→10%; cash 2→4%; all other review weights are unchanged. MU’s September 30 earnings and nVent’s October 1 closing move from future catalysts to reported events. HOOD’s event moves from the old November 4 assumption to the announced October 27 date. PRAX’s December 27 date is explicitly relutrigine; ulixacaltamide’s target is January 29, 2027. TSM’s September revenue is a reported October 8 filing, not an upcoming event. Unverified earnings estimates are labelled rather than promoted into confirmed dates.

The 23-stock draft retains substantial common AI/power/semiconductor exposure; a collection of different tickers does not remove common-factor risk. Proposed caps reduce one-name concentration but do not certify the portfolio risk. A single 10% name going to zero loses 10% of the starting portfolio; biotech gaps, correlated declines, liquidity and valuation remain review issues. There is no measured126-session alpha or calibrated aggregate downside claim here.

SPY is the separate broad-market comparator, alongside the earlier declared equal-weight/sector/random-band comparisons where their original contracts permit. The prior v1/v2 and external reviewer portfolio continue as recorded. Their future sealed/scheduled reads are not opened to select v3 weights. This draft does not choose Bloomberg’s contest policy; membership, scoring, approval and actual fills still require Monday receipts.

Revision-flow membership is separately preserved as a 20-name engine sleeve receipt. Its names are not silently merged into this thematic portfolio or ranked by target upside. The companion evidence file retains all 45 inspected instruments so the user/reviewer can compare the thematic draft, current engine sleeve and SPY without claiming their horizons or costs are interchangeable.

Before a reviewed freeze: corroborate missing catalyst dates, confirm the exact weight mandate and benchmark/cost contract, retain source hashes, run the existing freeze guard and pre-registration procedure, and have the owner review the final draft. No activation follows from this document.

## Evidence receipt

Private coordinator bundle: `atlas-v3-review.json`, `atlas-inputs-readonly.json`, `atlas_source_notes.json`. Read-only source hashes cover original books, analyst snapshots/revisions and cached prices; current public primary links above were checked October 10. Source lists do not certify an exhaustive news search, and the older factual contexts remain dated as shown.


## Dated review status — October 10, 21:54 SGT

The original draft above has now received independent acceptance as an inactive discussion draft. Its original SHA-256 is45f6e025e7a7b6623edcfecbf8004dfb7781a6257d5ada9b3593d8f96d5428a3 and the unchanged original bytes are preserved privately. All23 weights and45 selected input records were checked. Top-six concentration is48%; the stated power/semiconductor cluster is56%, and healthcare is18%. These are allocation summaries, not risk estimates. No weight, price, horizon, prior portfolio or gate changed during this review.

The private atlas-v3-review-supplement.json binds the original book, engine, membership, analyst, revision and price hashes and the primary-source capture inventory:10 captures saved,13 inaccessible. Successful capture does not certify semantic correctness or historical availability. Owner review of the mandate, measurable exit rules, costs and comparison contract is still required before a frozen forward trial. Bloomberg eligibility remains unverified pending Monday. No activation or order is authorised by this review status.

## Comparison with v1 and v2 ? October 11, 01:55 SGT

The original September 25 books remain intact: v1 `a20a2b972988eec6` is marked `DRAFT_NOT_FROZEN`; v2 `5d137b013692a737` is marked `HUMAN_REVIEWED`. Both record horizons of 1, 5, 21 and 126 sessions. The historical `frozen_utc` field in v1 does not establish a freeze. This v3 proposal selects the 126-session review horizon and remains inactive. No sealed comparison outcomes were opened to choose these weights.

| Name | v1 weight | v2 weight | v3 proposal |
|---|---:|---:|---:|
| AGIO | 1% | 2% | 2% |
| ALB | 2% | 0% | 0% |
| AVGO | 0% | 6% | 6% |
| BE | 0% | 4% | 4% |
| CAPR | 1% | 0% | 0% |
| CASH | 3% | 2% | 4% |
| CLS | 0% | 5% | 5% |
| COGT | 1% | 3% | 3% |
| ENS | 4% | 0% | 0% |
| GILD | 2% | 0% | 0% |
| HOOD | 8% | 7% | 7% |
| LEU | 3% | 2% | 2% |
| NOVT | 6% | 3% | 3% |
| NVT | 5% | 6% | 6% |
| PRAX | 2% | 1% | 1% |
| QUBT | 1% | 0% | 0% |
| RGEN | 2% | 1% | 1% |
| RGTI | 1% | 0% | 0% |
| SLI | 2% | 0% | 0% |
| TER | 2% | 0% | 0% |
| TSM | 5% | 7% | 7% |
| VKTX | 2% | 3% | 3% |
| VRT | 12% | 12% | 10% |
| VRTX | 3% | 4% | 4% |

GEV, MU, CCJ, IONQ, WST, BBIO and DKNG have unchanged weights across all three versions. Each allocation, including cash, totals 100%. The table reports historical decisions and the current proposal; it does not attribute them to a newly fitted model or demonstrate investment skill.

The private `atlas-prior-version-comparison.json` binds the original records and both hash bases. Its SHA-256 is `f375e794adfdfca338b27132b0b01f7f186364f97e6b86b12427d1ab6bd8d65e`; original inventory bytes and the hash-label correction are preserved in `atlas-prior-version-comparison-errata.json`.

## Instrument checks and short definitions ? October 11 SGT

The existing primary captures identify the following displayed company names. They do not by themselves establish the legal issuer, share class, ADR ratio, listing venue or quote currency. Those fields remain unverified for all 23 names in the private identity inventory; confirm them against the actual instrument before any reviewed entry. The price table retains cached quote units. Currency or ADR conversion must not be inferred from the ticker.

| Ticker | Name displayed by captured company source |
|---|---|
| VRT | Vertiv Holdings Co. |
| GEV | GE Vernova |
| MU | Micron Technology, Inc. |
| NVT | nVent Electric plc |
| MP | MP Materials |
| IONQ | IonQ |
| VKTX | Viking Therapeutics |
| RGEN | Repligen Corporation |
| BBIO | BridgeBio Pharma Inc. |
| DKNG | DraftKings |

The bounded capture inventory does not verify displayed names for TSM, HOOD, AVGO, CLS, BE, LEU, CCJ, NOVT, VRTX, WST, COGT, AGIO, PRAX. The earlier company links remain research leads; missing capture access is not an empty or disproved company record.

An **ADR** is a depositary instrument representing shares of a foreign issuer; the share ratio and applicable fees require instrument-specific checks. [SEC investor bulletin](https://www.sec.gov/investor/alerts/adr-bulletin.pdf)

A **PDUFA date** is a regulatory review goal date, not guaranteed approval. A **CRL** (Complete Response Letter) means the application is not ready for approval in its current form. [FDA review goals](https://www.fda.gov/media/151712/download), [FDA explanation of CRLs](https://www.fda.gov/drugs/laws-acts-and-rules/complete-response-letter-final-rule)

**HALEU** is uranium fuel enriched above 5% and below 20% uranium-235. Fuel classification does not establish a company's contract value or eligibility. [US Department of Energy](https://www.energy.gov/ne/articles/what-high-assay-low-enriched-uranium-haleu)

These definitions were checked against primary sources October 11 SGT. The dated private `atlas-instrument-identity-inventory.json` has SHA-256 `b7ccf2ab55983c62d64e233c82cb6ab90f7e0b0699fa6c4ae075e800d459de02`. No weights, prices, prior books or activation gates changed.
