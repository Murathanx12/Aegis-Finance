
# AEGIS - stock lists v3.1, 2026-09-27

Prepared 2026-09-27 (HKT) for Murat from the Aegis-Finance repo. v2 was 2026-09-26 (`docs/research_notes/2026-09-26/stock_lists_2026-09-26.md`). Every table is parsed from a named file; the Appendix lists every path and run id. The only LLM spend behind this document is the thesis-card run of section 2 (Appendix). **v3.1** (same day): +10 cards (JAZZ, BBIO, ABSI, HUBS, KYTX, NTLA, PRCH, SOC, ENS, TER) added to section 2 and scored in section 3; spend restated at the provider-calibrated price ($2.37); the 09-27 books' entry corrected to Monday 09-28. Licence of every list here: PRODUCT_EXPERIMENT - nothing in this document is a claim of alpha and none of it is an order.


## 0. What changed since v2, and why it changes how to read every list below

| # | What the review loop found (2026-09-26 to 09-27) | How to read the lists because of it |
|---|---|---|
| 1 | Broker identity is a coin flip: 320,809 directional analyst claims hit 50.1% at 5 days, 50.2% at 21 days; a firm's skill in the first half predicts its second half at rho -0.11. | An analyst's NAME adds nothing. Section 5 prints counts and mixes, not who said it. |
| 2 | First-mover target raises were look-ahead: point-in-time first-minus-follower -0.06% at 21d (t -0.26); the +1.34% (t 8.7) version knew the followers were coming. | A fresh raise is not a reason on its own. The 'net raises 90d' column is context, not a signal. |
| 3 | The analyst-skill filter (skill_mom) is 2025: ex-2025 it is -18.1 pp vs unskilled momentum; all of the gap is one year (+32.7 pp). | Do not rank on 'skilled analysts like it'. ANALYST-SKILL-1 stays at trivial effect. |
| 4 | 'The momentum win is semis beta' was WITHDRAWN - not because it was false but because 32 blocks cannot tell (median alpha SE 0.88%/mo, MDE 2.46%/mo). All 30 of the 2024-26 top-30 rules are CANNOT_DISTINGUISH. | No backtest in this repo can yet separate a 1%/month edge from zero. Every ranking below is a HYPOTHESIS list. |
| 5 | A calendar defect: by-year / leave-one-year-out was keyed on the DECISION date, not the hold month; 29 LOO verdicts flip; a '2020' result was January 2021 (the meme squeeze). | Year-by-year numbers quoted before 09-27 are superseded by the re-keyed receipts (`leaderboard_2026-09-26T164302Z.rekeyed.json`, then `T032801Z`). |
| 6 | The panel tilts small: random portfolios drawn from our own universe load 0.65-0.92 on IWM. Rules beating the benchmark in both windows: 69 of 288 vs SPY / 119 vs IWM / 139 vs the panel's random portfolio (`T032801Z`). | 'Beat SPY' overstates a small/mid list's skill when small caps rally and understates it when they lag. Section 3 prints each row's liquidity band. |
| 7 | 51 Dow Jones forecast rows are on the clock (48 WSJ Heard on the Street, 3 Barron's picks), made 2026-09-26, graded from Monday by the existing grader. | Section 6 is new. Every column there has n graded = 0 today: attention, not evidence, until the rows resolve. |
| 8 | The liquidity-weighted momentum book was VOIDED before entry (97.5% in MU + SNDK, rho 0.90, MU prints 09-30). | Concentration and an earnings print inside 5 sessions are checked before a book is frozen (freeze_gate); section 3 prints both flags. |

**The books.** 279 frozen books are PENDING their first session; the llm_portfolio grader enters each at the OPEN of the first session after its as-of date, i.e. **Monday 2026-09-28**. That includes the two books frozen with as-of 2026-09-27 - the Bloomberg dress rehearsal and Murat's core-satellite: they also enter **Monday 2026-09-28** (v3 printed a 09-29 label from the ROI report; fixed in `3204eb4d`, `docs/PAPER_ACCOUNTS.md` re-rendered). Of the 39 accounts already priced: **7 ahead of SPY, 32 behind**; all priced accounts together -1.31% (P&L $-62,258). First grades 09-29; the first 21-session read of the dress rehearsal is **2026-10-26** and it tests calibration and declared exposure, not the return.

**The honest benchmark sentence.** Our universe tilts small (random controls' IWM beta 0.65-0.92), so a list built from it looks good against SPY in a small-cap rally for reasons that are not skill. The dress rehearsal declares it: SPY beta 0.89, IWM-SPY 0.94, and an unplanned MTUM-SPY of -0.73 (anti-momentum). Read every 'vs SPY' here beside 'vs IWM'.

**What v3 learned from v2 (three changes of method).** (1) The ROI list is a declared formula bounded by each name's own volatility, instead of a union of research tables; (2) every name carries its sigma63-predicted move - the one input with measured skill (+10.0% held out at h=1 vs the LLM's +5.5%) - so an 'upside' can be read against what the stock normally moves; (3) the news columns are forecasts with an id and a grading date, not prose.

**Standing caveat (§17).** Analyst target-LEVEL upside is a PERVERSE cross-sectional signal in this repo's data: high-upside names underperformed by -90 bps/month in large/mid caps (t -3.62) and -199 bps/month in small caps (t -7.21). Sections 3 and 5 use it because Murat asked for it - as a list to research, with the falsifier beside it, never as a buy list.

Contents: 1. CHOSEN - the frozen books · 2. THESIS CARDS v3 · 3. ROI-MAXING HYPOTHESIS LIST · 4. Murat's holdings · 5. ANALYST UPSIDE · 6. NEWS-FORECAST STOCKS (new) · 7. Appendix.


---


# 1. CHOSEN - the frozen books: holdings, exposure, stops, paper status

Source: `backend/data/optimus/llm_portfolio/books.jsonl` (last record per name; twins and void rows listed separately). Weights are fractions of a $1,000,000 paper book. Status: `backend/data/optimus/paper_accounts/roi_2026-09-27.json` (generated 2026-09-27T00:02Z). The last column is the sigma63-predicted |move| over 21 sessions (section 2 defines it).


## bloomberg_rehearsal_2026-09-27 - book_id 4d0cebfeb8867fb8

kind competition · frozen 2026-09-26T19:59:52+00:00 · as-of 2026-09-27 · 10 positions · max weight 10.0% · benchmark URTH · paper status **PENDING** (grader entry: first session after 2026-09-27 = 2026-09-28 open)  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Exposure / stop / worst case:** NEW 09-27. The Bloomberg dress rehearsal (competition, benchmark URTH as the WLS proxy). Declared: sigma 8.31%/21 sessions absolute, 8.39% vs SPY; E[rel] 0 +/- 8.4%; betas SPY 0.89+/-0.21, IWM-SPY 0.94+/-0.22, SMH-SPY -0.03+/-0.17, MTUM-SPY -0.73+/-0.24. Stop: act only if z = cumulative relative P&L / (1.83% x sqrt(t)) < -2 (-3.7% at session 1, -8.2% at 5, -11.6% at 10, -16.8% at 21); no per-name stop. Worst case: one name to zero -$100k; a 3-sigma book day -$54k. 10-26 checks: move-size rank rho >= 0.3; realised exposure within +/-0.3; fills vs plan.

**Twins (graded beside it):** random_same_band `672d2b4cdcdb76a0` (FSS, EMN, PCRX, BLSH, CNR, ESQ, UEC, HIMX, NAT, CBT); next_k `d1b5b566e58b9b39` (BMI, IMAX, WRLD, ALK, NE, LAZ, WFRD, HAPN, MOH, SCHL); iwm `e1211de4cbd952c0`; spy `dbc218ccb553a6ba`

| Ticker | Weight | Theme | Thesis | Falsifier | σ63 move 21s |
|---|---|---|---|---|---|
| NVEC | 10.0% | semis | rank 1 by sigma63-predicted \|21-session move\| 23.9% (sigma63 6.54%/day); fundamentals proxy 0.76 >= median; Q3 print est 2026-10-21 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 23.9% |
| MAN | 10.0% |  | rank 2 by sigma63-predicted \|21-session move\| 16.5% (sigma63 4.52%/day); fundamentals proxy 0.70 >= median; Q3 print est 2026-10-15 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 16.5% |
| RHI | 10.0% |  | rank 3 by sigma63-predicted \|21-session move\| 14.3% (sigma63 3.90%/day); fundamentals proxy 0.84 >= median; Q3 print est 2026-10-22 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 14.3% |
| ACI | 10.0% |  | rank 4 by sigma63-predicted \|21-session move\| 13.6% (sigma63 3.71%/day); fundamentals proxy 0.71 >= median; Q3 print est 2026-10-22 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 13.6% |
| PEGA | 10.0% |  | rank 5 by sigma63-predicted \|21-session move\| 13.1% (sigma63 3.57%/day); fundamentals proxy 0.73 >= median; Q3 print est 2026-10-20 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 13.0% |
| IRDM | 10.0% |  | rank 6 by sigma63-predicted \|21-session move\| 12.6% (sigma63 3.45%/day); fundamentals proxy 0.64 >= median; Q3 print est 2026-10-21 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 12.6% |
| HELE | 10.0% |  | rank 7 by sigma63-predicted \|21-session move\| 12.3% (sigma63 3.38%/day); fundamentals proxy 0.57 >= median; Q3 print est 2026-10-07 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 12.3% |
| SMPL | 10.0% |  | rank 8 by sigma63-predicted \|21-session move\| 12.0% (sigma63 3.28%/day); fundamentals proxy 0.64 >= median; Q3 print est 2026-10-08 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 12.0% |
| PRGS | 10.0% |  | rank 9 by sigma63-predicted \|21-session move\| 11.9% (sigma63 3.26%/day); fundamentals proxy 0.59 >= median; Q3 print est 2026-10-21 (last 8-K 2.02 20… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 11.9% |
| AGYS | 10.0% |  | rank 10 by sigma63-predicted \|21-session move\| 10.6% (sigma63 2.91%/day); fundamentals proxy 0.70 >= median; Q3 print est 2026-10-26 (last 8-K 2.02 2… | its realised \|move\| to 2026-10-26 ranks in the bottom half of the book's predicted order, or no 8-K 2.02 is filed by 2026-10-26 | 10.6% |


## murat_core_satellite_2026-09-27 - book_id 5517aa50a29bc95b

kind personal · frozen 2026-09-26T19:59:52+00:00 · as-of 2026-09-27 · 12 positions · max weight 80.0% · benchmark SPY · paper status **PENDING** (grader entry: first session after 2026-09-27 = 2026-09-28 open)  
**Objective:** terminal wealth, balanced: 80% SPY + 20% fundamentals sleeve; tracking error ~4.1%/yr vs SPY; graded at 21 and 126 sessions  
**Exposure / stop / worst case:** NEW 09-27. Murat's money as a book: 80% SPY core (never stops) + 10 x 2% fundamentals-proxy sleeve. TE 4.09%/yr; book beta 0.95; sleeve beta 0.76. Stop: satellite minus its random-sleeve twin, z < -2 at the 126-session check only (about -5.8% of the book); never on 21 days. Worst case: one name to zero -$20k; sleeve to zero -$200k.

**Twins (graded beside it):** spy `923e79dbd12a963a`; random_sleeve `c05861aebd4361c0` (SPY, AVR, GSAT, PSX, CW, WAY, AMRC, MATV, CORZ, GWW, SLDE)

| Ticker | Weight | Theme | Thesis | Falsifier | σ63 move 21s |
|---|---|---|---|---|---|
| SPY | 80.0% |  | core: the market | none: the core never stops |  |
| PDD | 2.0% |  | fundamentals proxy rank 1 of the eligible universe, score 0.991 (3 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check |  |
| FIZZ | 2.0% |  | fundamentals proxy rank 2 of the eligible universe, score 0.961 (5 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check |  |
| MANH | 2.0% |  | fundamentals proxy rank 3 of the eligible universe, score 0.954 (4 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check |  |
| BZ | 2.0% |  | fundamentals proxy rank 4 of the eligible universe, score 0.951 (3 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check | 11.9% |
| CMG | 2.0% |  | fundamentals proxy rank 5 of the eligible universe, score 0.941 (4 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check |  |
| EXPO | 2.0% |  | fundamentals proxy rank 6 of the eligible universe, score 0.932 (3 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check |  |
| EXEL | 2.0% |  | fundamentals proxy rank 7 of the eligible universe, score 0.926 (5 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check |  |
| LZ | 2.0% |  | fundamentals proxy rank 8 of the eligible universe, score 0.918 (5 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check |  |
| REAL | 2.0% |  | fundamentals proxy rank 9 of the eligible universe, score 0.917 (3 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check | 10.5% |
| BBW | 2.0% |  | fundamentals proxy rank 10 of the eligible universe, score 0.906 (3 legs) | the sleeve trails its random-sleeve twin by more than 2 sigma of their difference at the 126-session check | 18.1% |
| CASH | 0.0% |  | declared: fully invested | n/a |  |


## human_ai_thematic_v2 - book_id 5d137b013692a737

kind personal · frozen 2026-09-25T09:58:15+00:00 · as-of 2026-09-25 · 24 positions · max weight 12.0% · benchmark SPY · paper status **PENDING** (grader entry: first session after 2026-09-25 = 2026-09-28 open)  
**Objective:** maximise 126-session (6-month) return vs SPY; graded beside ew / sector_etf / random_same_band / spy twins; v1 keeps running as the un-reviewed control  
**Exposure / stop / worst case:** v2 personal book (unchanged since 09-25). Benchmark SPY, 126 sessions. No price stop declared: each name carries a dated falsifier. Largest name to zero: VRT 12% = -$120k.

**Twins (graded beside it):** ew `e02b91c77e5f51c4`; sector_etf `ac85112e5328973d`; spy `2846d8d12db2346e`; random_same_band `4204177563615b9a` (RNG, ASML, NI, BKNG, FITB, INFY, KB, GWW, CRWD, LITE, CINF)

| Ticker | Weight | Theme | Thesis | Falsifier | σ63 move 21s |
|---|---|---|---|---|---|
| VRT | 12.0% | power_grid | AI power/cooling; UtilityInnovation acquisition moves it into onsite generation and microgrid control; deferred revenue $1.81B->$3.63B. | Q3 organic growth below the 34-36% guide, or backlog growth stalls. | 16.5% |
| GEV | 9.0% | power_grid | Generation/grid side of the same bottleneck; 116 GW turbine backlog; Q3 Oct 28. | slot reservations fail to convert to signed orders by Oct 28. | 12.2% |
| MU | 9.0% | semis | HBM/DRAM pricing and allocation; FQ4 print Sep 30 -- an expectation-risk event, sized for it. | Sep 30 print misses the ~86% gross-margin guide or spot DRAM/NAND rolls over. | 18.0% |
| TSM | 7.0% | semis | Participates whichever accelerator wins; Sep monthly sales Oct 8, Q3 Oct 15. | Q3 gross margin below the 65% floor or a capex-guide cut. | 9.2% |
| HOOD | 7.0% | gambling | Event contracts a material business (13.6B contracts Q2; revenue > crypto); the listed winner of the handle leak; Q3 Nov 4. | state or federal action forcing event contracts under state gambling licensing. | 16.4% |
| NVT | 6.0% | power_grid | Q2 sales +53%, EPS +69% on data-center electrical infrastructure; Maverick Power acquisition. | Maverick fails to close by the Nov 20 outside date; fall cooling launch slips. | 12.2% |
| AVGO | 6.0% | semis | AI chip revenue outlook raised to ~$115B FY2027; custom accelerators and networking already monetising (review's replacement for quantum). | a hyperscaler custom-silicon program slips or is in-sourced; AI revenue guide cut. | 9.1% |
| CLS | 5.0% | semis | UBS-preferred AI-infrastructure name; ~70% revenue growth tied to custom-chip/data-center programs. | hyperscaler order push-outs at the next print. | 18.6% |
| BE | 4.0% | power_grid | Behind-the-meter power for data centers -- the most direct expression if the bottleneck is power. | no new data-center power contracts announced by year end; margin guide cut. | 24.8% |
| MP | 4.0% | materials | Government floor price + offtake; strategic magnets. | legal challenge to the equity-taking authority succeeds; China's state group buys Shenghe and the exposure bites. | 14.6% |
| VRTX | 4.0% | biotech | Q2 revenue +12%, guidance raised; povetacicept PDUFA Nov 30 on strong Phase 3 data -- an operating company plus a catalyst. | CRL or a narrower label than IgAN accelerated approval. | 6.7% |
| NOVT | 3.0% | robotics | Servo-drive order for humanoids disclosed Aug 6; three analysts, negative momentum, growth partly acquired -- a hypothesis, sized like one. | order absent from backlog at the ~Nov 10 print. | 11.4% |
| WST | 3.0% | biotech | GLP-1 components; Morgan Stanley upgrade, UBS target $415. | GLP-1 component destocking at Q3. | 5.8% |
| COGT | 3.0% | biotech | GIST Phase 3 median PFS 16.5 vs 9.2 months; PDUFAs Nov 30 and Dec 30; ~$866M cash. The review's most-underweighted name. | CRL on the first PDUFA. | 10.5% |
| VKTX | 3.0% | biotech | September data: VK2735 durability with biweekly/monthly dosing and good tolerability -- a product-quality signal; ObesityWeek Nov. | tolerability signal at the November data. | 18.8% |
| DKNG | 3.0% | gambling | HELD. Consensus ~60% upside is real; CAC falling; Predictions ~2.5x July; targets trimmed; Q3 in November decides. | second quarter of hold compression, or Predictions forced to unwind in a state. | 11.0% |
| LEU | 2.0% | nuclear | HALEU with private prepayments now; DOE has said it will not exercise the old option -- the thesis is not risk-free. | no non-DOE offtake converts; further dilution after the $500M raise. | 17.7% |
| CCJ | 2.0% | nuclear | Uranium; Kazakh sulfuric-acid export ban threatens 2027 supply. | acid supply resolved; spot/equity divergence widens against it. | 9.6% |
| AGIO | 2.0% |  | Commercial business ($44.7M Q2 mitapivat), ~$965M cash, Nov 1 priority review. | CRL. | 12.2% |
| CASH | 2.0% |  | declared |  |  |
| IONQ | 1.0% | quantum | Quantum optionality; real-time decoder + NVIDIA 09-23. | no third-party replication; dilution. | 18.1% |
| RGEN | 1.0% | biotech | Bioprocessing; positive revisions but rich valuation. | book-to-bill < 1 at Q3. | 10.4% |
| BBIO | 1.0% | biotech | BBP-418 PDUFA Nov 27. BINARY. | CRL. | 10.0% |
| PRAX | 1.0% | biotech | PDUFA Dec 27 (extended). BINARY, low confidence. | the extension precedes a CRL. | 13.2% |


## human_ai_thematic_v1 - book_id a20a2b972988eec6

kind personal · frozen 2026-09-25T07:19:10+00:00 · as-of 2026-09-25 · 29 positions · max weight 12.0% · benchmark SPY · paper status **PENDING** (grader entry: first session after 2026-09-25 = 2026-09-28 open)  
**Objective:** maximise 126-session (6-month) return vs SPY; graded beside ew / sector_etf / random_same_band / spy twins  
**Exposure / stop / worst case:** v1 = the un-reviewed control of v2. No price stop declared. Largest name to zero: VRT 12% = -$120k.

**Twins (graded beside it):** ew `4ed704b8349cfebb`; sector_etf `36e15745ede143bc`; spy `d1aaf40c7abfa3fe`; random_same_band `5e8df95b9c56a050` (RNR, CBOE, NI, CELC, FITB, JBS, IP, HP, COST, KGS, BABA)

| Ticker | Weight | Theme | Thesis | Falsifier | σ63 move 21s |
|---|---|---|---|---|---|
| VRT | 12.0% | power_grid | AI power/cooling; $2.6B Utility Innovations deal 09-03; deferred revenue $1.81B->$3.63B. | MW shipped/backlog growth stalls at Q3 (late Oct). | 16.5% |
| GEV | 9.0% | power_grid | 116 GW gas-turbine backlog; DOE Speed to Power $5.25B 09-24. | slot reservations fail to convert to signed orders. | 12.2% |
| MU | 9.0% | semis | HBM4 allocation ~20% of NVIDIA; retail crowding confirms attention but the thesis is allocation, not mentions. | HBM share loss in TrendForce data; 2027 capex-digestion guide. | 18.0% |
| HOOD | 8.0% | gambling | Event-contract revenue $156M Q2 > crypto revenue; Q3 Nov 4; the listed winner of the AGA-documented handle leak. | CFTC/state orders constrain sports event contracts (NV/MI/CT precedents). | 16.4% |
| NOVT | 6.0% | robotics | Disclosed humanoid servo-drive order, hundreds of robots in testing (Aug 6 call); Baird $194. | order absent from backlog at ~Nov 10 earnings. | 11.4% |
| NVT | 5.0% | power_grid | Guide raised to 37-39%; fall cooling launch. | launch slips. | 12.2% |
| TSM | 5.0% | semis | Q3 earnings Oct 15; the capacity gate for every AI name. | capex guide cut. | 9.2% |
| ENS | 4.0% | lithium | Lithium data-center backup line decouples from the EV cycle. | segment share ~0% at Dec earnings. | 10.0% |
| MP | 4.0% | materials | Government floor price + offtake; the policy-stake template. | legal challenge to the equity-taking authority succeeds (INTC case). | 14.6% |
| LEU | 3.0% | nuclear | $900M DOE HALEU order; SMR offtakes. | DOE remains the only customer. | 17.7% |
| VRTX | 3.0% | biotech | Povetacicept PDUFA Nov 30 (primary); no MFN deal = tariff exposure to price. | CRL or a label narrower than IgAN accelerated approval. | 6.7% |
| WST | 3.0% | biotech | Cleanest listed GLP-1 supply-chain proxy; primary, dated, positive momentum. | GLP-1 component destocking at Q3. | 5.8% |
| DKNG | 3.0% | gambling | HELD (150 sh). ~60% consensus upside is real (Citizens JMP 09-24 +64.7%); CAC falling >80% after app integration; Predictions ~2.5x July. Q2 missed,… | Q3 (Nov) shows a second quarter of hold compression, or a state ruling forces Predictions to unwind. ADD trigger: hold back toward 9.8% with EBITDA c… | 11.0% |
| CASH | 3.0% |  | declared; absorbs binary-event losses without a forced sale |  |  |
| SLI | 2.0% | lithium | DOE FONSI; Trafigura/LGES offtakes. | FID slips; UBS cut 2027 China lithium price 40% on 09-22 is the bear tape. |  |
| ALB | 2.0% | lithium | Section 232 critical-minerals decision overdue. | no tariff and spot keeps falling. | 9.9% |
| CCJ | 2.0% | nuclear | Uranium; Kazakh sulfuric-acid export ban (09-12) threatens 2027 supply. | acid supply resolved; spot/equity divergence widens against it. | 9.6% |
| TER | 2.0% | robotics | Robotics + test; Q3 Oct 27. | Advantest keeps HBM/photonics test wins. | 19.8% |
| RGEN | 2.0% | biotech | Bioprocessing tools; primary-sourced order momentum. | book-to-bill < 1 at Q3. | 10.4% |
| VKTX | 2.0% | biotech | Oral obesity; ObesityWeek Nov data. | tolerability signal at the November data. | 18.8% |
| GILD | 2.0% | biotech | Anito-cel PDUFA Dec 23 (primary, via Arcellx). | CRL / manufacturing hold. |  |
| PRAX | 2.0% | biotech | PDUFA Dec 27 (extended); 18/20 Buy. BINARY. | the extension precedes a CRL. | 13.2% |
| IONQ | 1.0% | quantum | Real-time decoder + NVIDIA 09-23. | no third-party replication; dilution. | 18.1% |
| RGTI | 1.0% | quantum | $100M Commerce equity stake 09-04. | 10-Q shows a grant, not equity. | 18.1% |
| COGT | 1.0% | biotech | Two PDUFAs: GIST Nov 30, NonAdvSM Dec 30 (both primary). BINARY. | CRL on the first. | 10.5% |
| BBIO | 1.0% | biotech | BBP-418 PDUFA Nov 27 (primary). BINARY. | CRL. | 10.0% |
| CAPR | 1.0% | biotech | PDUFA Nov 22; adcom 9-3 against the original label. BINARY, coin flip. | no label granted. | 60.3% |
| AGIO | 1.0% | biotech | PDUFA Nov 1, priority review. BINARY. | CRL. | 12.2% |
| QUBT | 1.0% | quantum | HELD (300 sh). Revenue $5.6M from $61K; $1.3B cash; backlog $42.5M; targets $10-$32. | another large ATM raise without backlog; ADD trigger: two quarters of accelerating revenue with opex growth below revenue growth. | 15.1% |


## reviewer_opus_2026-09-25 - book_id 919892d54f6e3190

kind personal · frozen 2026-09-25T10:08:04+00:00 · as-of 2026-09-25 · 11 positions · max weight 14.0% · benchmark SPY · paper status **PENDING** (grader entry: first session after 2026-09-25 = 2026-09-28 open)  
**Objective:** maximise 126-session return vs SPY; the adversarial reviewer's own book, graded like every other arm (docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md section 6)  
**Exposure / stop / worst case:** The adversarial reviewer's own book. 60% non-USD, graded in local currency until the FX leg exists. Worst case stated by the reviewer: about -$220k on a -35% AI/power drawdown.

**Twins (graded beside it):** ew `246554898399f66a`; sector_etf `87b34e493fb2c2e7`; spy `2a89263475691f0d`; random_same_band `054f40d663ae49a6` (ROAD, CACC, NIC, CIVB, FIVE, IT, JPM, HD, ECHO, KHC, CASH)

| Ticker | Weight | Theme | Thesis | Falsifier | σ63 move 21s |
|---|---|---|---|---|---|
| 000660.KS | 14.0% | semis | HBM leader; 3Q26 print 2026-10-27. | 3Q26 shows HBM/DRAM ASPs falling. |  |
| GEV | 12.0% | power_grid | 116 GW backlog; Q3 Oct 28. | reservations fail to convert by Oct 28. | 12.2% |
| 6857.T | 10.0% | semis | HBM/AI test leader. | FY26 Q2 (Oct 28) gross margin below Q1. |  |
| HOOD | 10.0% |  | event contracts; Q3 Nov 4. | state/federal action on event contracts. | 16.4% |
| ARGX | 10.0% | biotech | EMPASSION Phase 3 topline Q4 2026. | EMPASSION misses its primary endpoint. |  |
| ENR.DE | 9.0% | power_grid | grid/turbines; FY results Nov 11. | comparable growth below the 14-16% guide. |  |
| 010120.KS | 9.0% |  | switchgear/transformers; Q3 Oct 28. | order intake below the raised KRW 6.0tn. |  |
| 012450.KS | 9.0% | defense | defence exports. | ground-systems operating margin below 10%. |  |
| LDO.MI | 9.0% | defense | European defence; 9M results Nov 5. | free operating cash flow still negative. |  |
| NVT | 8.0% | power_grid | data-center electrical; Maverick close by Nov 20. | Maverick fails to close; launch slips. | 12.2% |
| CASH | 0.0% |  | declared: the reviewer runs fully invested |  |  |


## cards_supports_2026-09-25 - book_id 89761b53e2cd82ba

kind personal · frozen 2026-09-25T10:07:43+00:00 · as-of 2026-09-25 · 21 positions · max weight 4.9% · benchmark SPY · paper status **PENDING** (grader entry: first session after 2026-09-25 = 2026-09-28 open)  
**Objective:** maximise 126-session return vs SPY; the pure-evidence arm: every thesis card that came back 'supports' on 2026-09-25, equal weight, no human override  
**Exposure / stop / worst case:** Pure-evidence arm: every 09-25 'supports' card, equal weight, no human override. No stop declared.

**Twins (graded beside it):** ew `3355b6c8ed3a69f1`; sector_etf `6122fde7397415da`; spy `6c3747cd512b3b29`; random_same_band `df55d0a76fdd48fd` (ROAD, CAC, NI, CION, FWONK, ISRL, IOT, HMC, DXPE, JPM, BABA)

| Ticker | Weight | Theme | Thesis | Falsifier | σ63 move 21s |
|---|---|---|---|---|---|
| 000660.KS | 4.9% | semis | card: supports / med | 3Q26 earnings on 2026-10-27 showing HBM or DRAM average selling prices falling versus 2Q26, or operating profit below the KRW 60.54T reported for 2Q2… |  |
| 010120.KS | 4.9% |  | card: supports / med | Q3 2026 earnings on 2026-10-28 showing order intake below the raised KRW 6.0tn annual run-rate or operating margin under 11.3%. |  |
| 012450.KS | 4.9% |  | card: supports / med | Q3 2026 ground systems operating margin reported below 10% (versus 35-39% export margin), or a Poland K9 EC3 award slipping past 2026-12-31. |  |
| 2330.TW | 4.9% | semis | card: supports / high | 3Q26 earnings on 2026-10-15 showing gross margin below the guided 65% floor or 3Q26 revenue under US$44.6bn. |  |
| 6857.T | 4.9% |  | card: supports / med | FY2026 Q2 results on 2026-10-28 showing gross margin below Q1 FY2026 and no repeat of the inventory-obsolescence reversal, with guidance not raised a… |  |
| 8035.T | 4.9% | semis | card: supports / med | FY2027 Q2 earnings on 2026-10-30 showing gross margin below Q1 FY2027 and no H2 recovery, or H1 net sales under the raised 1,620B yen guidance. |  |
| ARGX | 4.9% |  | card: supports / med | The Q4 2026 EMPASSION MMN readout (empasiprubart) fails its primary endpoint, or the Q3 2026 report on 2026-10-22 shows product sales growth decelera… |  |
| ENR.DE | 4.9% |  | card: supports / med | FY2026 results on 2026-11-11 show comparable revenue growth below the guided 14-16 pct or Siemens Gamesa back at a loss. |  |
| ENS | 4.9% | lithium | card: supports / med | The lithium data-center-backup line staying near 0% of segment revenue by the Dec earnings call would falsify the decoupling thesis -- the book's own… | 10.0% |
| GEV | 4.9% | power_grid | card: supports / med | Turbine-backlog slot reservations failing to convert into signed orders by the 2026-10-28 Q3 print would falsify the bull case -- again the book's ow… | 12.2% |
| HOOD | 4.9% | gambling | card: supports / med | A state or federal action forcing Robinhood's event contracts under state gambling licensing (raising costs / restricting states) would falsify the b… | 16.4% |
| LDO.MI | 4.9% |  | card: supports / med | 9M 2026 results on 5 Nov 2026 showing free operating cash flow still negative and no further FY2026 guidance raise. |  |
| LLY | 4.9% |  | card: supports / med | Q3 2026 earnings on 2026-10-29 (unconfirmed) showing worldwide realized price decline worse than Q2's 13 pct while volume growth falls below 40 pct,… |  |
| MP | 4.9% | materials | card: supports / med | A successful legal or legislative challenge to the government's equity-taking/floor-price authority, or NdPr volume growth stalling well below the 12… | 14.6% |
| MU | 4.9% | semis | card: supports / med | The 2026-09-30 FQ4 print missing the ~86% gross-margin guide, or DRAM/NAND spot pricing rolling over shortly after, would falsify the pricing-cycle b… | 18.0% |
| NOVT | 4.9% | robotics | card: supports / low | The servo-drive order being cancelled, or absent from disclosed backlog, at the ~2026-11-10 Q3 call would falsify the bull case -- the thematic book'… | 11.4% |
| NVT | 4.9% | power_grid | card: supports / med | The Maverick Power acquisition failing to close by its 2026-11-20 outside date (or extending to Feb 2027, signaling deal friction) would be the first… | 12.2% |
| RGTI | 4.9% | quantum | card: supports / low | If the 10-Q/8-K terms show the government's $100M as a grant/award rather than an actual equity stake -- the book's own stated falsifier for this pos… | 18.1% |
| TSM | 4.9% | semis | card: supports / med | Q3-2026 gross margin reported below 65% on 2026-10-15, or September monthly sales (2026-10-08) showing YoY growth decelerating below 30%. | 9.2% |
| VRT | 4.9% | power_grid | card: supports / med | A confirmed Q3 (Oct, date unconfirmed on IR) organic growth print below the 34-36% guide, or evidence that MW backlog is not converting to signed/shi… | 16.5% |
| CASH | 2.0% |  | declared |  |  |


## probe_equal_2026-09-26 - book_id 132d0d6c0d445bbb

kind personal · frozen 2026-09-26T08:59:40+00:00 · as-of 2026-09-26 · 12 positions · max weight 9.1% · benchmark SPY · paper status **PENDING** (grader entry: first session after 2026-09-26 = 2026-09-28 open)  
**Objective:** Relative P&L vs SPY over 21 sessions, long-only, $1M: the same PROBE names weighted three ways  
**Exposure / stop / worst case:** The PROBE names, equal weight (one of three weighting twins - equal / inverse-vol / big-move tilt - read against USMV on 10-26). No stop declared.

**Twins (graded beside it):** ew `412ef852862efa6b`; sector_etf `c04909d702257aa4`; spy `9a6cfc0d97c6ca62`; random_same_band `4cc06b99879645f5` (T, SU, WDC, SNN, TSLA, MRK, ASX, SEDG, JPM, WFC, CARG)

| Ticker | Weight | Theme | Thesis | Falsifier | σ63 move 21s |
|---|---|---|---|---|---|
| NVDA | 9.1% | semis | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0252/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 8.9% |
| INCY | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0210/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 7.0% |
| AAPL | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0198/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 6.5% |
| SNDR | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0200/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 7.2% |
| META | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0315/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 11.5% |
| AVPT | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0266/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 9.4% |
| AMZN | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0264/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 9.2% |
| GOOGL | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0218/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 8.2% |
| GOOG | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0215/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains |  |
| ALLE | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0198/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains |  |
| JAZZ | 9.1% |  | PROBE name from 2026-09-25.json; equal weight; sigma_63 0.0176/day | the arm trails probe_equal after 21 sessions by more than its USMV beta explains | 6.4% |
| CASH | 0.0% |  | declared: fully invested | n/a |  |


## Every other frozen book (compact): top holdings, freeze gate, status

| Book | book_id | Kind | n | Max w | Top holdings (weight %) | Freeze gate | Status |
|---|---|---|---|---|---|---|---|
| comp_ai_power_global_2026-09-25 | b23cf2a9aee04289 | competition | 21 | 7% | GEV 7, VRT 6, NVT 6, ASML 6, TSM 6, MU 6 |  | PENDING |
| comp_asia_supply_chain_2026-09-25 | 2c606bb5b74479c4 | competition | 13 | 10% | 2330.TW 10, 000660.KS 10, 005930.KS 9, 8035.T 9, 6857.T 9, ASML 9 |  | PENDING |
| comp_catalyst_calendar_2026-09-25 | 4a3864b2140550ce | competition | 26 | 6% | ASML 6, TSM 6, ARGX 5, SAAB-B.ST 5, EVO.ST 5, TER 5 |  | PENDING |
| comp_ensemble_2026-09-25 | f1365ea29aeb1be2 | competition | 23 | 6% | ASML 6, TSM 6, NVDA 6, MU 6, AMD 6, GEV 6 |  | PENDING |
| comp_pharma_binary_basket_2026-09-25 | e781e41e79e56323 | competition | 19 | 9% | MRK 9, VRTX 8, LLY 8, ABBV 7, AMGN 7, GILD 6 |  | PENDING |
| comp_policy_geopolitics_2026-09-25 | ae32ba0af99ce972 | competition | 18 | 7% | RHM.DE 7, GEV 7, HAG.DE 6, SAAB-B.ST 6, KOG.OL 6, INTC 6 |  | PENDING |
| comp_quality_momentum_2026-09-25 | a0ab004a8709c745 | competition | 23 | 7% | MU 7, NVDA 7, TSM 7, AMD 6, ASML 6, AVGO 5 |  | PENDING |
| comp_retail_attention_contrarian_2026-09-25 | 986780f4fa0f0119 | competition | 20 | 8% | ASML 8, TSM 8, ARGX 7, MRK 7, AMGN 6, ABBV 6 |  | PENDING |
| comp_revision_flow_leaders_2026-09-25 | 308c1895b710fa8d | competition | 23 | 6% | MRK 6, ABBV 6, AMGN 6, LLY 5, OKTA 5, SNOW 5 |  | PENDING |
| comp_small_cap_catalyst_2026-09-25 | a978a7d6c8b1a962 | competition | 25 | 5% | AGIO 5, VRTX 5, MRK 5, ARGX 5, ASML 5, TSM 5 |  | PENDING |
| lib_big_dv_2026-09-26 | 5c21859739b26b6f | personal | 21 | 5% | MU 5, NVDA 5, SNDK 5, AAPL 5, TSLA 5, AMD 5 |  | PENDING |
| lib_book_f_seasonality_11_20_v0_2026-09-26 | 974d5067e835c006 | personal | 31 | 3% | LNG 3, VG 3, EVC 3, WTW 3, XPO 3, UAL 3 |  | PENDING |
| lib_disp_short_avoid_2026-09-27 | d93fbf2c301248ca | personal | 21 | 5% | AKTS 5, LIFE 5, SNDK 5, JAN 5, AXTI 5, WOLF 5 | PASS | PENDING |
| lib_forecast_dispersion_v1_2026-09-26 | 5ab343d6b1bc62a4 | personal | 21 | 5% | ABUS 5, AEBI 5, AES 5, ALX 5, AMPG 5, ARIS 5 |  | PENDING |
| lib_frog_in_pan_2026-09-26 | 50e6cb3b0657464d | personal | 21 | 5% | ASX 5, TER 5, VICR 5, WDC 5, AMAT 5, CLMT 5 |  | PENDING |
| lib_illiquid_sealed_2026-09-26 | 8f989a4bf3f759cf | personal | 21 | 5% | SDOT 5, CHRN 5, BKCH 5, ITG 5, DBVT 5, RFIL 5 |  | PENDING |
| lib_inflection_flow_2026-09-26 | bec77d696dfa91e0 | personal | 21 | 5% | MU 5, MRVL 5, STX 5, IOT 5, ESTC 5, TEAM 5 |  | PENDING |
| lib_low_asset_growth_sealed_2026-09-26 | 6d36d70c4ae56556 | personal | 21 | 5% | ARI 5, BZ 5, FUTU 5, KDK 5, TK 5, CALY 5 |  | PENDING |
| lib_low_dtc_mom_sealed_2026-09-26 | 58440bc63a0cbcb1 | personal | 21 | 5% | SNDK 5, MLPI 5, MU 5, NEXA 5, INTC 5, TGB 5 |  | PENDING |
| lib_margin_mom_sealed_2026-09-26 | 139145a5269b8fd9 | personal | 21 | 5% | KOPN 5, SNDK 5, MU 5, SLN 5, MRVL 5, BB 5 |  | PENDING |
| lib_mom_12_1_2026-09-26 | 5d01fa2898e2cb72 | personal | 21 | 5% | AKTS 5, AXTI 5, LIFE 5, SNDK 5, JAN 5, NUAI 5 |  | PENDING |
| lib_mom_12_1_liqw_sealed_2026-09-26 | 76ea751d6ef35ab5 | personal | 21 | 60% | MU 60, SNDK 37, AXTI 1, SYRE 0, PRAX 0, JAN 0 |  | VOIDED |
| lib_mom_12_1_q_2026-09-26 | e41dbb1e06a12088 | personal | 21 | 5% | AKTS 5, AXTI 5, LIFE 5, SNDK 5, JAN 5, NUAI 5 |  | PENDING |
| lib_mom_12_1_secrel_sealed_2026-09-26 | 132c0abc5b9f366f | personal | 21 | 5% | AKTS 5, ALM 5, ATEX 5, AXTI 5, DAR 5, ENLT 5 |  | PENDING |
| lib_mom_12_1_small_2026-09-26 | eb6fa721a4c5f995 | personal | 21 | 5% | AKTS 5, DMRA 5, QTTB 5, ANRO 5, CLYM 5, IMMX 5 |  | PENDING |
| lib_mom_flow_2026-09-26 | 40c6ffdf6c238d60 | personal | 21 | 5% | RVMD 5, MU 5, DELL 5, AMD 5, GH 5, DFTX 5 |  | PENDING |
| lib_mom_flow_ivw_2026-09-27 | 68ba5c780776be27 | personal | 21 | 5% | RVMD 5, DELL 5, AMD 5, GH 5, STX 5, MRVL 5 | PASS | PENDING |
| lib_mom_no_downgrades_2026-09-26 | f0517a9aa6ab0bce | personal | 21 | 5% | AKTS 5, AXTI 5, LIFE 5, SNDK 5, JAN 5, NUAI 5 |  | PENDING |
| lib_mom_no_downgrades_small_2026-09-27__control | 36d2c89bd8f45b59 | control | 21 | 5% | AKTS 5, ANRO 5, QTTB 5, CLYM 5, DMRA 5, IMMX 5 | CONTROL | PENDING |
| lib_net_raises_2026-09-26 | a92c21d829544aa7 | personal | 21 | 5% | OKTA 5, SNOW 5, CRWD 5, CRM 5, PANW 5, TGT 5 |  | PENDING |
| lib_qc395_sharpe252_above_trend_large_2026-09-27 | 69dc804d44b74f12 | personal | 11 | 10% | SNDK 10, AXTI 10, TXG 10, TWST 10, MU 10, RVMD 10 | PASS | PENDING |
| lib_qc470_mom252_quarterly_riskparity_2026-09-27__control | 7a65d45f09962ead | control | 21 | 5% | AKTS 5, LIFE 5, SNDK 5, AXTI 5, JAN 5, WOLF 5 | CONTROL | PENDING |
| lib_resid_mom_12_1_large_sealed_2026-09-26 | 485a857d5b45847c | personal | 21 | 5% | WOLF 5, AXTI 5, PRAX 5, SNDK 5, MRNA 5, SYRE 5 |  | PENDING |
| lib_rev_5d_sealed_2026-09-26 | f94720b48278bf55 | personal | 21 | 5% | ALHC 5, XENE 5, SION 5, SWMR 5, ENVA 5, ARTV 5 |  | PENDING |
| lib_skill_mom_2026-09-27 | 2f3dd36e85505710 | personal | 21 | 5% | RVMD 5, STX 5, ERAS 5, AMD 5, CLYM 5, GH 5 | PASS | PENDING |
| lib_skill_mom_sealed_2026-09-26 | 775b9951e0b67e4b | personal | 21 | 5% | RVMD 5, MU 5, DFTX 5, STX 5, MRVL 5, AMD 5 |  | PENDING |
| lib_trend_quality_2026-09-26 | 46762e2bf28c238c | personal | 21 | 5% | CORT 5, ANF 5, SNDK 5, CDNA 5, QMCO 5, IBTA 5 |  | PENDING |
| pers_ai_power_global_2026-09-25 | 994aa4afda4fa2d1 | personal | 14 | 11% | GEV 11, VRT 10, NVT 9, MU 9, ASML 8, TSM 8 |  | PENDING |
| pers_asia_supply_chain_2026-09-25 | f97957221662a8b9 | personal | 14 | 12% | 2330.TW 12, 000660.KS 10, 005930.KS 9, ASML 9, 6857.T 8, 8035.T 7 |  | PENDING |
| pers_catalyst_calendar_2026-09-25 | 56daa7269d142603 | personal | 22 | 7% | VRTX 7, MRK 7, GILD 6, CORT 6, ASML 6, AGIO 5 |  | PENDING |
| pers_ensemble_2026-09-25 | 4fe78b33214899cc | personal | 20 | 11% | CASH 11, MRK 8, VRTX 7, GILD 6, ASML 6, TSM 6 |  | PENDING |
| pers_pharma_binary_basket_2026-09-25 | 4a07e3bfc1fa7d7c | personal | 20 | 12% | CASH 12, VRTX 8, MRK 8, LLY 7, ABBV 7, GILD 6 |  | PENDING |
| pers_policy_geopolitics_2026-09-25 | 9ed2fedf51df1bbc | personal | 14 | 10% | INTC 10, RHM.DE 9, GEV 9, MP 8, SAAB-B.ST 8, KOG.OL 8 |  | PENDING |
| pers_quality_momentum_2026-09-25 | 101b75d7f1f78dd5 | personal | 16 | 9% | NVDA 9, VRTX 8, MRK 8, TSM 8, GILD 7, ASML 7 |  | PENDING |
| pers_retail_attention_contrarian_2026-09-25 | 66433be8ce92d0f8 | personal | 14 | 9% | VRTX 9, MRK 9, GILD 8, GEV 8, TSM 8, COGT 7 |  | PENDING |
| pers_revision_flow_leaders_2026-09-25 | 784d2831c530f113 | personal | 15 | 9% | OKTA 9, SNOW 8, CRWD 8, PANW 7, CRM 7, TGT 7 |  | PENDING |
| pers_small_cap_catalyst_2026-09-25 | a5e835dd553d7071 | personal | 15 | 9% | CASH 9, AGIO 8, COGT 8, VRTX 8, BBIO 7, MRK 7 |  | PENDING |
| probe_bigmove_tilt_2026-09-26 | 23ac8d562416f388 | personal | 12 | 13% | META 13, AVPT 11, AMZN 10, NVDA 10, GOOGL 9, GOOG 9 |  | PENDING |
| probe_inverse_vol_2026-09-26 | 61fa183ee45aa10a | personal | 12 | 11% | JAZZ 11, AAPL 10, ALLE 10, SNDR 10, INCY 10, GOOG 9 |  | PENDING |
| revision_flow_v0 | cb8d492bb8bf9ade | personal | 20 | 5% | OKTA 5, SNOW 5, CRWD 5, PANW 5, CRM 5, ABNB 5 |  | PENDING |
| revision_flow_v0_random_twin | e74c9063d451e316 | personal | 20 | 5% | ACAD 5, ARES 5, ASND 5, BTGO 5, CASY 5, CCEP 5 |  | PENDING |

58 non-twin books and 222 twins (ew / sector_etf / spy / random_same_band / next_k / iwm / random_sleeve comparators) are in the ledger; one book is VOIDED (`lib_mom_12_1_liqw_sealed_2026-09-26`: MU 60.3% + SNDK 37.2% = 97.5%, rho 0.90, MU prints 09-30 inside the first 5 sessions). The library books (lib_*) failed the freeze gate's TIMING check on 09-26 (09-21 bars for a 09-26 decision); they trade Monday as declared and are labelled CONTROL in docs/BRIDGE.md until re-frozen on fresh bars.


## Paper accounts already priced (roi_2026-09-27.json)

| Account | Family | Since | Status | ROI % | SPY same window % | vs SPY pp | Last mark | Note |
|---|---|---|---|---|---|---|---|---|
| conservative-atr | website_lane | 2026-06-17 | LIVE | 4.85 | 3.32 | 1.53 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| aggressive | website_lane | 2026-06-08 | LIVE | 2.76 | 3.56 | -0.80 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| tsmom-overlay | website_lane | 2026-07-27 | LIVE | 2.40 | 3.31 | -0.91 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| conservative | website_lane | 2026-06-08 | LIVE | 1.87 | 3.56 | -1.70 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| balanced | website_lane | 2026-06-08 | LIVE | 1.75 | 3.56 | -1.81 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| tsmom-6040-control | website_lane | 2026-07-27 | LIVE | 0.96 | 3.31 | -2.35 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| balanced-ew-control | website_lane | 2026-06-10 | LIVE | 0.56 | 5.53 | -4.97 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| smallmid-quality | website_lane | 2026-07-22 | LIVE | -5.98 | 2.16 | -8.14 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| conviction | website_lane | 2026-06-16 | LIVE | -8.26 | 2.03 | -10.28 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| mirror | website_lane | 2026-06-16 | LIVE | -22.16 | 2.03 | -24.19 | 2026-09-18 | NAV last marked 2026-09-18; the deploy expected 2026-09-25 (all_fresh=False) |
| hack2 | alpaca_fleet | 2026-08-28 | LIVE | -1.18 | 0.28 | -1.46 | 2026-09-25 |  |
| hack5 | alpaca_fleet | 2026-08-28 | LIVE | -4.95 | 0.28 | -5.23 | 2026-09-25 |  |
| hack1 | alpaca_fleet | 2026-08-28 | LIVE | -8.47 | 0.28 | -8.75 | 2026-09-25 |  |
| hack6 | alpaca_fleet | 2026-08-28 | LIVE | -17.70 | 0.28 | -17.98 | 2026-09-25 |  |
| hack4 | alpaca_fleet | 2026-08-28 | LIVE | -20.17 | 0.28 | -20.45 | 2026-09-25 |  |
| hack3 | alpaca_fleet |  | CREDENTIAL_INVALID |  |  |  |  | HTTP 401 on /v2/account -- the key is revoked or wrong, NOT a $0 account. retired 2026-09… |
| PC-PAPER | pc_paper | 2026-09-22 | LIVE | -0.10 | -0.28 | 0.18 | 2026-09-25 | first trades 2026-09-25 |
| Cash/index by default; deviate only above a [b109… | night_books | 2026-09-11 | LIVE | 7.04 | 1.17 | 5.87 | 2026-09-25 | 3 marks |
| Always invested - Book D's primary comparato [3b3… | night_books | 2026-09-11 | LIVE | 7.04 | 1.17 | 5.87 | 2026-09-25 | 3 marks |
| 12-1 momentum, k=12, equal weight, monthly [8dbbb… | night_books | 2026-09-11 | LIVE | 3.19 | 1.17 | 2.01 | 2026-09-25 | 3 marks |
| Low short interest, high turnover, long-only [193… | night_books | 2026-09-11 | LIVE | 0.00 | 1.17 | -1.17 | 2026-09-25 | 3 marks |
| Insider SAME-DAY clusters - the falsifier ar [435… | night_books | 2026-09-11 | LIVE | 0.00 | 1.17 | -1.17 | 2026-09-25 | 3 marks |
| Insider cluster buys, 4-5 day clusters, long [625… | night_books | 2026-09-11 | LIVE | 0.00 | 1.17 | -1.17 | 2026-09-25 | 3 marks |
| Good-news names in the top overhang tercile, [a82… | night_books | 2026-09-11 | LIVE | 0.00 | 1.17 | -1.17 | 2026-09-25 | 3 marks |
| The UNCONDITIONED reaction book - Book C's p [c3a… | night_books | 2026-09-11 | LIVE | 0.00 | 1.17 | -1.17 | 2026-09-25 | 3 marks |
| First hour after a natively-stamped headline [f64… | night_books | 2026-09-12 | UNGRADED |  |  |  |  | no paper_nav rows: the book has never been marked |
| murat_live | murat_book | 2026-08-11 | LIVE | -5.09 | 0.35 | -5.44 | 2026-09-25 | window return of the recorded share counts since as_of 2026-08-11 (confirmed: False; cash… |
| AGENCY_BOOK:aggressive | agency |  | UNGRADED |  |  |  |  | a PROPOSAL (authority EXPLORE, expected_payoff NOT CALIBRATED); no paper_books entry hold… |
| AGENCY_BOOK:balanced | agency |  | UNGRADED |  |  |  |  | a PROPOSAL (authority EXPLORE, expected_payoff NOT CALIBRATED); no paper_books entry hold… |
| AGENCY_BOOK:extreme_growth | agency |  | UNGRADED |  |  |  |  | a PROPOSAL (authority EXPLORE, expected_payoff NOT CALIBRATED); no paper_books entry hold… |

By family (ROI over each account's own window): website_lane -2.12% (n priced 10); alpaca_fleet -10.49% (n priced 5); pc_paper -0.10% (n priced 1); night_books +2.16% (n priced 8); night_books_twin -0.23% (n priced 14); murat_book -5.09% (n priced 1). The priced night-book twins are omitted from the table. Website-lane NAVs were last marked 2026-09-18 (the Railway backend sleeps when idle; an attended fix is owed).


---


# 2. THESIS CARDS v3 - the shortlist re-carded on 2026-09-27

Runs on 2026-09-27 (all `python -m scripts.thesis_cards run --only ... --date 2026-09-27`; OpenClaw managed browser profile `muratclaw` for the web pass + DeepSeek `deepseek-flash` for the synthesis): (a) the v3 shortlist of 60 - the v2 book's 23 + the dress rehearsal's 10 + Murat's DKNG/QUBT/AARD/BHVN/SLDP + the 16 Dow Jones forecast tickers + the 9 distinct PROBE names (GOOG = GOOGL): 58 carded, TEM and JAZZ refused; (b) a spend test that carded JAZZ and BBIO again; (c) the price-calibration batch that carded ABSI, HUBS, KYTX, NTLA, PRCH, SOC (Murat's other holdings) and ENS, TER (v1 book). v3.1 therefore prints 67 cards. Still refused: AMSC (REFUSED_EMPTY_LOG), TEM (REFUSED_UNPARSEABLE_WEB) - no v3 card for those. Spend: $2.37 for the day at the provider-calibrated price (Appendix).

Columns. **σ63 move 21s** = the sigma63-predicted |move| over 21 sessions = σ63 x sqrt(21) x sqrt(2/π), σ63 = the daily log-return s.d. over the 63 sessions to the 2026-09-25 bars (`rehearsal_book.predicted_abs_move`; the vol prior with measured skill). **Fund.** = the five-ratio fundamentals PROXY (percentile-rank mean of gp_at+, ope_be+, ni_be+, at_gr1-, debt_at-, SEC filed+2d, >= 3 legs) ranked within the 2,890-name eligible universe - NOT the LightGBM that measured +39 bps/month (its panel ends 2024-12); blank = fewer than 3 legs (foreign filers, recent IPOs). **Upside** = the 2026-09-27 analyst snapshot's mean-target implied upside (§17: perverse). **vs 09-25** = the change from the previous card (09-26 for MU).

| Ticker | From | Verdict / conf | Next dated catalyst (card) | Falsifier (v3 card) | σ63 move 21s | Fund. | Upside | vs 09-25 |
|---|---|---|---|---|---|---|---|---|
| AGYS | rehearsal | supports/med | not found - Agilysys investor relations events page is JavaScript-rendered and returned a 404 shell on 2026-0… | Q2 FY27 report (late Oct 2026) showing subscription growth below the guided ~30%, or any cut to FY27 revenue 368-373M, or FY27 adjusted EBITDA below 24%. | 10.6% | 0.71 | 35% | new (no 09-25 card) |
| AMZN | PROBE | supports/med | 2026-10-06 \| event \| Prime Big Deal Days runs October 6-7 2026 | Q3 2026 results due 2026-10-29: AWS growth below ~28% or backlog below 450B USD would prove the bull case wrong. | 9.2% | 0.55 | 32% | new (no 09-25 card) |
| CLS | v2 book | supports/med | 2026-10-27 \| investor_day \| 2026 Investor and Analyst Day, virtual presentation plus in-person lunch forum in… | Q3 2026 results on 2026-10-27: revenue below $5.25B or adjusted operating margin below 8.4%. | 18.6% | 0.46 | 29% | neutral/med -> supports/med |
| CRM | DJ forecast | supports/med | not found - investor relations page investor.salesforce.com was blocked by Cloudflare (403) on 2026-09-27; no… | Q3 FY27 results (~Dec 2026) showing cRPO growth below the guided ~14%, or no second-half organic revenue reacceleration. | 13.2% | 0.51 | 20% | new (no 09-25 card) |
| GEV | v2 book | supports/med | 2026-10-28 \| Earnings \| 3rd Quarter 2026 Earnings Webcast, 7:30 am EDT | At the 2026-10-28 Q3 print, gas equipment under contract fails to progress toward at least 125 GW by year-end 2026, or FY26 revenue 45.5-46.5B / FCF 11.5-12.5B guidance… | 12.2% | 0.31 | 29% | same |
| GOOGL | PROBE | supports/med | 2026-10-01 \| product_event \| Project Suncatcher first orbital TPU test launch, company says next month, Reute… | Q3 2026 results due about 2026-10-28: Google Cloud year-over-year growth below 50%, or total operating margin below 32%, or declining Cloud backlog. | 8.2% | 0.52 | 25% | new (no 09-25 card) |
| HWM | DJ forecast | supports/high |  | Q3 2026 results (about November 2026): Adjusted EBITDA margin below roughly 32%, or FY2026 Adjusted EPS guidance cut below 5.23, or revenue below the 10.0B low end. | 8.8% | 0.45 | 45% | new (no 09-25 card) |
| INCY | PROBE | supports/med | 2026-09-30 \| conference \| Incyte inflammation and autoimmunity data at EADV 2026 Congress, Vienna, September… | Q3 2026 report (late Oct/early Nov 2026) cutting FY26 total net sales below $5,130M or Opzelura below $1,050M, or Jakafi net sales below the $3,220-3,270M guide. | 7.0% | 0.33 | 3% | new (no 09-25 card) |
| IONQ | v2 book | supports/med | 2026-11-04 \| earnings \| Q3 2026 earnings call (estimated) | Q3 2026 earnings, est. 2026-11-04: FY26 revenue guidance cut below $450M, or organic growth under 100%, or gross margin below 33%. | 18.1% | 0.16 | 48% | neutral/med -> supports/med |
| JAZZ | PROBE | supports/med | 2026-09-30 \| trial readout \| Second interim overall survival from HERIZON-GEA-01 doublet expected during 3Q26… | A 2026 revenue print below the $4.60B guidance floor, or a negative second interim overall survival from HERIZON-GEA-01 doublet due 3Q26 (company-stated 2026-08-03). | 6.4% | 0.59 | 23% | new (no 09-25 card) |
| KYTX | Murat (other) | supports/med | 2026-09-29 \| conference \| AANEM Annual Meeting oral presentation of longer-term KYSA-6 Phase 2 gMG data | Any reported high-grade CRS, ICANS or IEC-HS case in miv-cel, or the rolling SPS BLA not completed by 2026-12-31. | 15.6% | 0.38 | 346% | neutral/med -> supports/med |
| LNG | DJ forecast | supports/med | 2026-12-31 \| milestone \| CCL Stage 3 Train 7 first LNG and substantial completion expected fall 2026 | FY2026 Consolidated Adjusted EBITDA reported below the raised 7.90B floor, or any guidance cut, in the Q4 2026 8-K. | 7.2% | 0.59 | 16% | new (no 09-25 card) |
| NOVT | v2 book | supports/med | 2026-11-02 \| earnings \| Q3 2026 earnings, next estimated date, before market open | At the Q3 2026 call (est. 2026-11-02), FY2026 organic growth below about 7 percent or gross margin below about 47 percent, or no humanoid servo-drive order disclosure. | 11.4% | 0.40 | 35% | supports/low -> supports/med |
| NOW | DJ forecast | supports/med | 2026-10-28 \| earnings \| Q3 2026 earnings, estimated before market open | Q3 2026 report (~2026-10-28): FY2026 subscription guidance cut below $15.76B, or subscription growth under ~22% YoY, or AI ACV not tracking toward $1.5B. | 13.0% | 0.48 | 7% | new (no 09-25 card) |
| NTLA | Murat (other) | supports/med | 2027-03-10 \| regulatory \| FDA PDUFA target action date for the lonvo-z BLA in hereditary angioedema | An FDA complete response letter for the lonvo-z BLA on or before the 2027-03-10 PDUFA date, or a label requiring HLA or liver monitoring or a boxed warning. | 14.5% | 0.27 | 104% | neutral/med -> supports/med |
| NVDA | PROBE | supports/high | 2026-10-01 \| dividend \| quarterly cash dividend of 0.25 usd per share payable to shareholders of record 2026-… | Q3 FY27 results on 2026-11-18: revenue below 105.8B usd or GAAP gross margin below 73.5pct would prove the bull case wrong. | 8.9% | 0.69 | 46% | new (no 09-25 card) |
| NVEC | rehearsal | supports/med | 2026-10-21 \| earnings \| Q2 FY2027 results for quarter ended 2026-09-30 and conference call (estimated) | Q2 FY2027 results due about 2026-10-21 showing revenue below Q1's $11.0M, gross margin back toward 78-80%, or disclosure that Q1 growth was one-off stock-building or Abb… | 23.9% | 0.76 |  | new (no 09-25 card) |
| NVT | v2 book | supports/high | 2026-09-29 \| offering close \| $800M senior notes offering expected to close | Q3 2026 print on 2026-10-30 showing organic growth below 32% or adjusted EPS below $1.35, or gross margin below 36%. | 12.2% | 0.48 | 25% | supports/med -> supports/high |
| PSNL | DJ forecast | supports/med | 2026-09-30 \| contract \| New VA MVP task order becomes effective, value up to $18.3M | The Personalis special meeting fails to adopt the Tempus merger, or Tempus Class A closes below $46.00 giving Personalis a termination right (SEC 425, 2026-09-15). | 14.7% | 0.24 | -6% | new (no 09-25 card) |
| SNOW | DJ forecast | supports/med |  | Q3 FY27 results (late Nov-early Dec 2026): product revenue below 1,588M usd, or FY27 guidance cut below 36% growth, or NRR at/below 120% (was 126%). | 10.6% | 0.29 | 27% | new (no 09-25 card) |
| TER | v1 book | supports/med | 2026-10-27 \| earnings \| Q3'26 earnings, after close | Q3-26 earnings 2026-10-27: revenue below $1,200M or Semiconductor Test revenue down sequentially would show the AI/memory order cycle has rolled over. | 19.8% | 0.65 | 12% | neutral/med -> supports/med |
| TSM | v2 book | supports/high | 2026-10-08 \| monthly sales \| TSMC Monthly Sales - September 2026 | 2026-10-15 Q3 gross margin below 65% (guidance floor) or Q3 revenue below US$44.6B, or a cut to the US$60-64B 2026 capex. | 9.2% |  | 23% | supports/med -> supports/high |
| VKTX | v2 book | supports/med | 2026-09-27 \| note \| Viking IR Webcasts and Presentations Upcoming Events section shows no events to display | By 2026-12-31, no oral VK2735 Phase 3 initiation announced on Viking IR, per the company's own 2026-07-29 guidance. | 18.8% | 0.40 | 167% | neutral/med -> supports/med |
| VRTX | v2 book | supports/med | 2026-11-02 \| earnings \| Vertex third quarter 2026 earnings call with Crinetics accounting and financial impac… | FDA rejects or delays the povetacicept BLA on or before its 2026-11-30 PDUFA date, removing the renal-franchise launch. | 6.7% | 0.48 | 8% | neutral/med -> supports/med |
| WDAY | DJ forecast | supports/med | 2026-10-05 \| leadership \| Sarah Kennedy Ellis becomes chief marketing officer | Q3 FY2027 results (estimated 2026-11-24) with subscription revenue below the guided 2.515B USD or non-GAAP margin below 30.0%, or total backlog growth at or under 10%. | 14.7% | 0.65 | 10% | new (no 09-25 card) |
| WST | v2 book | supports/med |  | Q3 2026 earnings: reported net sales growth below 1.9% year over year, or organic growth below the guided +7.0-8.9%, or an FY26 guidance cut. | 5.8% | 0.67 | 10% | neutral/med -> supports/med |
| AAPL | DJ forecast/PROBE | neutral/med |  | Q4 FY26 gross margin materially below about 48pct excluding tariff refunds, or iPhone revenue growth under 10pct y/y, reported late October 2026. | 6.5% | 0.71 | -4% | new (no 09-25 card) |
| ABSI | Murat (other) | neutral/med | 2026-12-31 \| data readout \| Interim proof-of-concept data for ABS-201 in pattern hair loss, guided 2H 2026 | ABS-201 interim pattern-hair-loss proof-of-concept data, guided 2H 2026, missing or showing no efficacy signal by 2026-12-31. | 19.5% | 0.28 | 48% | neutral/low -> neutral/med |
| AGIO | v2 book | neutral/med | 2026-11-01 \| pdufa \| mitapivat sNDA, sickle cell disease, priority review (accelerated approval) | FDA issues a CRL or delays the mitapivat sickle cell sNDA past the 2026-11-01 PDUFA date. | 12.2% | 0.52 | 42% | same |
| AMGN | DJ forecast | neutral/med | 2026-09-27 \| note \| Company IR calendar could not be read: investors.amgen.com and amgen.com did not resolve… | Q3 2026 results on 2026-11-03 showing FY non-GAAP EPS below the $22.30 guidance floor or product-sales growth under 9%. | 7.9% | 0.57 | -6% | same |
| AVGO | v2 book | neutral/med | 2026-09-30 \| dividend \| Quarterly cash dividend $0.65 per share payable to stockholders of record 2026-09-21 | Q4 FY2026 AI semiconductor revenue below $21.7B, or FY2027 AI target cut below ~$100B, when Broadcom reports around December 2026. | 9.1% | 0.39 | 51% | supports/med -> neutral/med |
| AVPT | PROBE | neutral/med |  | Q3 2026 results (due about early November 2026): total revenue below $128.2m or non-GAAP operating income below $21.0m, or FY2026 ARR below $522.1m. | 9.4% | 0.40 | 29% | new (no 09-25 card) |
| BA | DJ forecast | neutral/med | 2026-10-06 \| labor \| SPEEA contract expiry and potential strike deadline | 737 MAX 10 certification slipping past 2026, or FAA/EASA action on the navigation glitch, or a SPEEA strike after the 2026-10-06 contract expiry. | 7.5% | 0.17 | 38% | new (no 09-25 card) |
| BBIO | v2 book | neutral/med | 2026-09-30 \| trial \| First participant dosed in RECLAIM-HP Phase 3 in Q3 2026 | BBP-418 receives a CRL on or before its 2026-11-27 PDUFA date, or Q3 2026 Attruby U.S. net product revenue fails to grow above $222.4M. | 10.0% | 0.22 | 66% | same |
| BE | v2 book | neutral/med | 2026-09-28 \| legal \| Securities class action lead plaintiff deadline | Oracle terminates or formally suspends the Project Jupiter master agreement, or Bloom discloses a scandium-oxide supply disruption, on or before the Q3 2026 earnings cal… | 24.8% | 0.14 | -3% | same |
| BHVN | Murat | neutral/med |  | An FDA escalation of the 2026-09-04 partial hold to a full clinical hold on BHV-7000, or RISE3/BHV7000-303 topline slipping past 2026-12-31. | 18.2% | 0.33 | 64% | against/med -> neutral/med |
| BN | DJ forecast | neutral/med | 2026-09-29 \| dividend \| Q3 2026 common dividend 0.07 USD per share payable | Q3 2026 DE before realizations per share reported on 2026-11-12 below 0.61 USD, or quarterly fundraising under 77B USD. | 5.0% |  | 48% | new (no 09-25 card) |
| BSP | DJ forecast | neutral/med | 2026-11-06 \| earnings \| Q3 2026 results estimated, before market open | Q3 2026 revenue reported about 2026-11-06 outside the guided $733M-$745M range, or organic growth at or below 3%. | 19.6% |  | 44% | new (no 09-25 card) |
| CCJ | v2 book | neutral/med | 2026-10-30 \| earnings \| Upcoming investor event October 30 2026 before markets open (Q3 2026 results expected) | Q3 2026 results on 2026-10-30 showing 2026 production below 19.5 Mlb (our share), another delivery cut, or Westinghouse equity earnings still negative versus unchanged g… | 9.6% |  | 45% | same |
| COGT | v2 book | neutral/med | 2026-11-30 \| pdufa \| bezuclastinib NDA #1, GIST (PEAK) | A complete response letter or delay to the 2026-11-30 GIST PDUFA (or the 2026-12-30 NonAdvSM PDUFA) would prove the bull case wrong. | 10.5% | 0.14 | 73% | same |
| DKNG | v2 book/Murat | neutral/med | 2026-09-29 \| promotion \| PGA TOUR responsible-play sweepstakes entry window closes | Q3-2026 print (est. 2026-11-05) showing Sports Net Revenue Margin still below 8% with FY2026 Adjusted EBITDA guided under $700M. | 11.0% | 0.43 | 59% | same |
| ENS | v1 book | neutral/med | 2026-10-02 \| dividend payment \| $0.2875 per share payable | Q2 FY27 adjusted EPS ex-45X below $1.95 or sales below $955M, reported about early November 2026 (SEC 8-K 2026-08-12 guidance). | 10.0% | 0.66 | 41% | supports/med -> neutral/med |
| HELE | rehearsal | neutral/med | 2026-10-08 \| earnings \| Q2 fiscal 2027 results before market open, conference call 9:00 a.m. ET | The 2026-10-08 Q2 FY27 report: H1 adjusted EPS not near 20% of the $3.25-3.75 guide, or Q2 gross margin falling beyond the guided tariff path. | 12.3% | 0.58 | 8% | new (no 09-25 card) |
| HOOD | v2 book | neutral/med | 2026-09-28 \| IR event \| Anticipated Date of Robinhood September Month-to-Date Trading Color, 4:05 PM EDT | Q3 2026 print (est. 2026-11-04) shows event-contract revenue below Q2's $156M, or another large state orders withdrawal beyond Missouri's 2026-09-16 order. | 16.4% |  | 9% | supports/med -> neutral/med |
| HUBS | Murat (other) | neutral/med | 2026-11-04 \| earnings \| Q3 2026 earnings call, estimated after market close | Q3 2026 results on 2026-11-04: as-reported revenue growth below the guided 14%, or net new customers below the guided 5,000-6,000, would prove the durable-growth case wr… | 19.3% | 0.54 | 17% | same |
| IRDM | rehearsal | neutral/med | 2026-12-31 \| product launch \| Iridium NTN Direct commercial availability in Q4 2026 | Regulatory approval denied or the Rocket Lab merger terminated or renegotiated before the guided mid-2027 close, or the $54.00 spread widening materially on deal risk. | 12.6% | 0.64 | -14% | new (no 09-25 card) |
| LEU | v2 book/DJ forecast | neutral/med |  | First new Oak Ridge centrifuge not completed by 2026-12-31, management's own deadline (2026-08-05 8-K outlook). | 17.7% | 0.34 | 68% | same |
| MAN | rehearsal | neutral/med | 2026-10-15 \| earnings \| Q3 2026 results, estimated before market open | Q3 2026 results (est. 2026-10-15) diluted EPS outside the guided 0.96-1.06, or gross margin below ~16%, would prove the bull case wrong. | 16.5% | 0.70 | -0% | new (no 09-25 card) |
| META | PROBE | neutral/med | 2026-10-28 \| earnings \| Q3 2026 earnings release estimated after market close | Q3 2026 results on 2026-10-28: revenue below the 61B usd guidance floor, or FY2026 capex above 145B usd, or free cash flow still near zero (SEC 8-K 2026-07-29). | 11.5% | 0.58 | 5% | new (no 09-25 card) |
| MP | v2 book | neutral/med | 2026-11-05 \| earnings \| Q3 2026 results, estimated after market close | No commercial GM magnet shipment announced by 2026-12-31, or Q3 2026 NdPr sales below the guided 1,000 MT run rate when reported 2026-11-05. | 14.6% | 0.41 | 52% | supports/med -> neutral/med |
| MU | v2 book | neutral/med | 2026-09-30 \| earnings \| Fiscal Q4 2026 results and conference call at 2:30 p.m. Mountain time | The FQ4 FY2026 print due 2026-09-30: revenue below $49.0B, GAAP gross margin below ~86%, or non-GAAP EPS below $31.00 would prove the bull case wrong. | 18.0% | 0.40 | 40% | supports/med -> neutral/med |
| NVO | DJ forecast | neutral/med | 2026-11-04 \| earnings \| Novo Nordisk Q3'26 results (also NOVO-B.CO) | Q3 2026 results on 2026-11-04 showing adjusted sales growth outside the 0% to -6% CER guidance, or US weekly Wegovy pill prescriptions below the ~265k baseline of 2026-0… | 9.1% |  | 20% | new (no 09-25 card) |
| PRAX | v2 book | neutral/med | 2026-12-27 \| pdufa \| relutrigine (PRAX-562) NDA, SCN2A/SCN8A DEE, extended PDUFA | A Complete Response Letter or a second PDUFA extension for relutrigine on or before 2026-12-27. | 13.2% |  | 127% | neutral/low -> neutral/med |
| PRCH | Murat (other) | neutral/med | 2026-11-04 \| earnings \| Q3 2026 results (estimated, unconfirmed by company) | Q3 2026 results (est. 2026-11-04) showing Reciprocal policies written growth below 38% YoY or statutory surplus under $169.9M. | 14.4% | 0.22 | 26% | same |
| PRGS | rehearsal | neutral/med | 2026-09-30 \| earnings \| Fiscal Q3 2026 financial results and conference call 5pm ET | The 2026-09-30 Q3 print: revenue below the $244-250M high end or non-GAAP EPS below $1.59 would prove the bull case wrong. | 11.9% | 0.59 | 38% | new (no 09-25 card) |
| QUBT | Murat | neutral/med | not found | Q3 2026 report (~November 2026) showing consolidated gross margin still negative AND sequential revenue flat excluding acquisitions, or a goodwill impairment charge. | 15.1% | 0.42 | 108% | against/high -> neutral/med |
| RGEN | v2 book | neutral/med | 2026-10-05 \| special meeting \| BioLife stockholders vote to adopt the merger agreement | BioLife stockholders fail to adopt the merger at the 2026-10-05 special meeting, or Q3 2026 GAAP operating margin (due ~2026-10-27) stays near 6.8% with no accretion lin… | 10.4% | 0.37 | -0% | same |
| SLDP | Murat | neutral/med | 2026-12-31 \| guidance \| Expect to announce a Korea JV for commercial-scale electrolyte production by YE 2026 | No Korea commercial-scale electrolyte JV announced by 2026-12-31, or the continuous pilot line misses Q4 2026 startup or the 75 MT/y target. | 12.5% | 0.34 | 188% | against/med -> neutral/med |
| SNDR | PROBE | neutral/med | 2026-10-09 \| dividend \| 0.10 per share payable to holders of record 2026-09-11 | Q3 2026 results (est. 2026-10-29): FY2026 adjusted EPS guidance cut below 0.90, or Truckload operating ratio back above 93.6%, or revenue ex-fuel down year over year. | 7.2% | 0.61 | 20% | new (no 09-25 card) |
| SOC | Murat (other) | neutral/med | 2026-09-30 \| operations \| Platform Hondo expected to come online in September 2026 | Platform Hondo fails to come online by 2026-09-30, or Q3 2026 net sales fall below 40,000 Boe/d versus 2H 2026E guidance of 40,000-45,000. | 46.2% | 0.25 | 151% | same |
| VG | DJ forecast | neutral/med | 2026-09-30 \| dividend \| Quarterly cash dividend of 0.04 dollars per share payable (record date 2026-09-15) | Plaquemines Phase 1 COD not achieved by 2026-12-31, or FY2026 Adjusted EBITDA guided below 8.7B dollars, or Q3-2026 realised fixed liquefaction fee far under 12.50 dolla… | 14.6% | 0.26 | 32% | new (no 09-25 card) |
| VRT | v2 book | neutral/med | 2026-12-31 \| acquisition close \| UtilityInnovation Group (UIG) ~$1.45B acquisition expected to close in Q4 20… | Q3 2026 organic growth below the guided 34-36pc, or any cut to FY26 $13.8-14.2B sales / $6.65-6.75 EPS, reported at the October 2026 Q3 print. | 16.5% | 0.49 | 34% | supports/med -> neutral/med |
| AARD | Murat | against/high | 2026-09-30 \| clinical \| Q3 2026 assessment of unblinded HERO and OLE data, a company promise, with no release… | By 2026-09-30, Aardvark releases unblinded HERO and OLE data showing meaningful hyperphagia reduction with no cardiac QRS signal, and the FDA lifts the 2026-05-14 full c… |  |  |  | against/med -> against/high |
| ACI | rehearsal | against/high | 2026-10-13 \| earnings \| Q2 FY2026 results estimated, before market open | Q2 FY2026 results due about 2026-10-13: identical sales above 0.0% and Adjusted EBITDA at or above $3.625bn would prove the weak-traffic bear case wrong. | 13.6% | 0.71 | 22% | new (no 09-25 card) |
| PEGA | rehearsal | against/high | 2026-10-01 \| dividend record date \| Q4 2026 cash dividend record date | Q3 2026 results showing FY2026 ACV growth below the ~10% the CFO indicated on 2026-09-08, or Pega Cloud ACV growth under 20% versus 22% at 2026-07-21. | 13.0% | 0.74 | 19% | new (no 09-25 card) |
| RHI | rehearsal | against/med |  | Q3 2026 results, due late October 2026: revenue below USD1.31B or EPS below USD0.43, or Protiviti adjusted revenue down more than 8% YoY. | 14.3% | 0.84 | -5% | new (no 09-25 card) |
| SMPL | rehearsal | against/med | 2026-10-13 \| legal \| Lead plaintiff deadline in the SMPL securities class action | Q4 FY26 results around late Oct 2026: net sales outside $322-332M or adjusted EBITDA outside $52-57M, or a further FY27 guidance cut (2026-07-09 8-K). | 12.0% | 0.64 | 50% | new (no 09-25 card) |
| AMSC | Murat (other) | - | 2026-11-04 \| earnings \| estimated Q2 fiscal 2026 results date for quarter ended September 30 2026, after mark… |  | 14.0% | 0.49 | 106% | REFUSED_EMPTY_LOG on 2026-09-27 (09-25: neutral/med) |
| TEM | DJ forecast | - |  |  | 20.6% | 0.20 | -19% | REFUSED_UNPARSEABLE_WEB on 2026-09-27 |

Verdicts on 67 v3 cards: neutral 36, supports 26, against 5. Against the previous card: new 31, verdict changed 17, same 13, confidence changed 6. A verdict is about the EVIDENCE (supports / neutral / against the bull case), not a price call; 'high' confidence needs dated primary-source evidence (the card prompt's rule).


---


# 3. ROI-MAXING LIST - a declared, reproducible HYPOTHESIS ranking

**Formula (printed so it can be re-run):** score = clip(U, -B, +B) x K x (0.5 if crowded else 1), where U = the analyst mean-target implied upside from the 2026-09-27 snapshot (`target_snapshots.parquet`, observed 2026-09-26T17:14Z); B = 2 x σ63 x sqrt(126) = the two-sigma 6-month move of the name's own recent volatility - no name is credited with more upside than two standard deviations of what it moves in 126 sessions; K = card conviction: supports/high 1.0, supports/med 0.75, supports/low 0.5, neutral 0.25, against 0 (an against card removes the name); crowded = on the v2 retail-crowding list (research_social.md §3: AMD, BB, BYND, DNUT, GME, GOOG, GOOGL, GPRO, MU, NBIS, NVDA, ORCL, PLTR, RKLB, SNDK) or read as retail-crowded in the 09-27 research note's clean crowd reads (DKNG; the note's other crowd reads are 'n/a - not checked'). Universe = the shortlist names (v3.1: the 60 plus ABSI, HUBS, KYTX, NTLA, PRCH, SOC, AMSC, ENS, TER) with a v3 card, a σ63 and a snapshot upside (a name with no analyst mean target, e.g. NVEC, cannot be scored and is listed below the table); ranked by score. The score is an expected-upside PROXY, not a forecast.

**Why this is a HYPOTHESIS list.** U is target-level upside, which §17 measured as perverse (-90 / -199 bps/month). The card conviction is an LLM verdict about evidence, and LLM DIRECTION measured -7.9% skill (n = 780). The σ63 bound is the one term with measured skill, and it is a MAGNITUDE term, not a direction. So each row carries its falsifier and its 2026-10-26 check: at 21 sessions the realised |move| should rank with the predicted |move| (Spearman >= 0.3 over the list), and a row whose card falsifier fires by then is removed. The list is graded against the same names' SPY and IWM legs, not only SPY.

| # | Ticker | Score | U (analyst) | B = 2σ 126s | Card | K | Crowd | Band | σ63 move 21s | Fund. | Next print (source) | Falsifier | Research note |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | VKTX | +86.6% | 167% | 116% (binds) | supports/med | 0.75 |  | mid | 18.8% | 0.40 | 2026-10-28 (EDGAR+91d) | By 2026-12-31, no oral VK2735 Phase 3 initiation announced on Viking IR, per the company's own 2026-07-29 guidance. | top-15 #3 |
| 2 | KYTX | +71.7% | 346% | 96% (binds) | supports/med | 0.75 |  | small | 15.6% | 0.38 | 2026-11-10 (EDGAR+91d) | Any reported high-grade CRS, ICANS or IEC-HS case in miv-cel, or the rolling SPS BLA not completed by 2026-12-31. |  |
| 3 | NTLA | +66.6% | 104% | 89% (binds) | supports/med | 0.75 |  | mid | 14.5% | 0.27 | 2026-11-05 (EDGAR+91d) | An FDA complete response letter for the lonvo-z BLA on or before the 2027-03-10 PDUFA date, or a label requiring HLA or liver mon… |  |
| 4 | HWM | +45.3% | 45% | 54% | supports/high | 1.00 |  | large | 8.8% | 0.45 | 2026-11-05 (EDGAR+91d) | Q3 2026 results (about November 2026): Adjusted EBITDA margin below roughly 32%, or FY2026 Adjusted EPS guidance cut below 5.23,… |  |
| 5 | SOC | +37.8% | 151% | 283% | neutral/med | 0.25 |  | mid | 46.2% | 0.25 | 2026-11-12 (card) | Platform Hondo fails to come online by 2026-09-30, or Q3 2026 net sales fall below 40,000 Boe/d versus 2H 2026E guidance of 40,00… |  |
| 6 | IONQ | +35.7% | 48% | 111% | supports/med | 0.75 |  | large | 18.1% | 0.16 | 2026-11-04 (card) | Q3 2026 earnings, est. 2026-11-04: FY26 revenue guidance cut below $450M, or organic growth under 100%, or gross margin below 33%. | top-15 #10 |
| 7 | NOVT | +26.4% | 35% | 70% | supports/med | 0.75 |  | mid | 11.4% | 0.40 | 2026-11-02 (card) | At the Q3 2026 call (est. 2026-11-02), FY2026 organic growth below about 7 percent or gross margin below about 47 percent, or no… | top-15 #14 |
| 8 | AGYS | +26.2% | 35% | 65% | supports/med | 0.75 |  | mid | 10.6% | 0.71 | 2026-10-26 (EDGAR+91d) | Q2 FY27 report (late Oct 2026) showing subscription growth below the guided ~30%, or any cut to FY27 revenue 368-373M, or FY27 ad… | top-15 #12 |
| 9 | NVT | +24.8% | 25% | 75% | supports/high | 1.00 |  | large | 12.2% | 0.48 | 2026-10-30 (card) | Q3 2026 print on 2026-10-30 showing organic growth below 32% or adjusted EPS below $1.35, or gross margin below 36%. |  |
| 10 | AMZN | +24.0% | 32% | 56% | supports/med | 0.75 |  | mega | 9.2% | 0.55 | 2026-10-29 (card) | Q3 2026 results due 2026-10-29: AWS growth below ~28% or backlog below 450B USD would prove the bull case wrong. |  |
| 11 | QUBT | +23.2% | 108% | 93% (binds) | neutral/med | 0.25 |  | mid | 15.1% | 0.42 | 2026-11-09 (EDGAR+91d) | Q3 2026 report (~November 2026) showing consolidated gross margin still negative AND sequential revenue flat excluding acquisitio… |  DROP/TRIM |
| 12 | NVDA | +22.8% | 46% | 55% | supports/high | 1.00 | yes | mega | 8.9% | 0.69 | 2026-11-18 (card) | Q3 FY27 results on 2026-11-18: revenue below 105.8B usd or GAAP gross margin below 73.5pct would prove the bull case wrong. |  |
| 13 | TSM | +22.6% | 23% | 56% | supports/high | 1.00 |  | mega | 9.2% |  | 2026-10-15 (card) | 2026-10-15 Q3 gross margin below 65% (guidance floor) or Q3 revenue below US$44.6B, or a cut to the US$60-64B 2026 capex. |  |
| 14 | GEV | +21.9% | 29% | 75% | supports/med | 0.75 |  | mega | 12.2% | 0.31 | 2026-10-28 (card) | At the 2026-10-28 Q3 print, gas equipment under contract fails to progress toward at least 125 GW by year-end 2026, or FY26 reven… |  |
| 15 | CLS | +21.7% | 29% | 114% | supports/med | 0.75 |  | large | 18.6% | 0.46 | 2026-10-27 (card) | Q3 2026 results on 2026-10-27: revenue below $5.25B or adjusted operating margin below 8.4%. |  |
| 16 | PRAX | +20.2% | 127% | 81% (binds) | neutral/med | 0.25 |  | large | 13.2% |  | 2026-11-05 (EDGAR+91d) | A Complete Response Letter or a second PDUFA extension for relutrigine on or before 2026-12-27. | top-15 #1 |
| 17 | SNOW | +19.9% | 27% | 65% | supports/med | 0.75 |  | mega | 10.6% | 0.29 | 2026-12-02 (EDGAR+91d) | Q3 FY27 results (late Nov-early Dec 2026): product revenue below 1,588M usd, or FY27 guidance cut below 36% growth, or NRR at/bel… |  |
| 18 | SLDP | +19.1% | 188% | 76% (binds) | neutral/med | 0.25 |  | small | 12.5% | 0.34 | 2026-11-03 (EDGAR+91d) | No Korea commercial-scale electrolyte JV announced by 2026-12-31, or the continuous pilot line misses Q4 2026 startup or the 75 M… |  |
| 19 | JAZZ | +17.3% | 23% | 39% | supports/med | 0.75 |  | large | 6.4% | 0.59 | 2026-11-02 (EDGAR+91d) | A 2026 revenue print below the $4.60B guidance floor, or a negative second interim overall survival from HERIZON-GEA-01 doublet d… |  |
| 20 | LEU | +17.1% | 68% | 109% | neutral/med | 0.25 |  | large | 17.7% | 0.34 | 2026-11-04 (EDGAR+91d) | First new Oak Ridge centrifuge not completed by 2026-12-31, management's own deadline (2026-08-05 8-K outlook). | top-15 #4 |
| 21 | COGT | +16.0% | 73% | 64% (binds) | neutral/med | 0.25 |  | mid | 10.5% | 0.14 | 2026-11-09 (EDGAR+91d) | A complete response letter or delay to the 2026-11-30 GIST PDUFA (or the 2026-12-30 NonAdvSM PDUFA) would prove the bull case wro… | top-15 #7 |
| 22 | BHVN | +15.9% | 64% | 112% | neutral/med | 0.25 |  | mid | 18.2% | 0.33 | 2026-11-09 (EDGAR+91d) | An FDA escalation of the 2026-09-04 partial hold to a full clinical hold on BHV-7000, or RISE3/BHV7000-303 topline slipping past… |  |
| 23 | BBIO | +15.4% | 66% | 62% (binds) | neutral/med | 0.25 |  | large | 10.0% | 0.22 | 2026-11-09 (EDGAR+91d) | BBP-418 receives a CRL on or before its 2026-11-27 PDUFA date, or Q3 2026 Attruby U.S. net product revenue fails to grow above $2… | top-15 #2 |
| 24 | CRM | +15.1% | 20% | 81% | supports/med | 0.75 |  | mega | 13.2% | 0.51 | 2026-11-25 (EDGAR+91d) | Q3 FY27 results (~Dec 2026) showing cRPO growth below the guided ~14%, or no second-half organic revenue reacceleration. |  |
| 25 | MP | +13.0% | 52% | 90% | neutral/med | 0.25 |  | large | 14.6% | 0.41 | 2026-11-05 (card) | No commercial GM magnet shipment announced by 2026-12-31, or Q3 2026 NdPr sales below the guided 1,000 MT run rate when reported… | top-15 #5 |
| 26 | AVGO | +12.7% | 51% | 56% | neutral/med | 0.25 |  | mega | 9.1% | 0.39 | 2026-12-02 (EDGAR+91d) | Q4 FY2026 AI semiconductor revenue below $21.7B, or FY2027 AI target cut below ~$100B, when Broadcom reports around December 2026. |  |
| 27 | ABSI | +12.0% | 48% | 120% | neutral/med | 0.25 |  | mid | 19.5% | 0.28 | 2026-11-10 (EDGAR+91d) | ABS-201 interim pattern-hair-loss proof-of-concept data, guided 2H 2026, missing or showing no efficacy signal by 2026-12-31. | top-15 #15 |
| 28 | LNG | +11.6% | 16% | 44% | supports/med | 0.75 |  | large | 7.2% | 0.59 | 2026-11-05 (EDGAR+91d) | FY2026 Consolidated Adjusted EBITDA reported below the raised 7.90B floor, or any guidance cut, in the Q4 2026 8-K. |  |
| 29 | CCJ | +11.2% | 45% | 59% | neutral/med | 0.25 |  | large | 9.6% |  | 2026-10-30 (card) | Q3 2026 results on 2026-10-30 showing 2026 production below 19.5 Mlb (our share), another delivery cut, or Westinghouse equity ea… | top-15 #6 |
| 30 | BSP | +11.0% | 44% | 120% | neutral/med | 0.25 |  | mid | 19.6% |  | 2026-11-06 (card) | Q3 2026 revenue reported about 2026-11-06 outside the guided $733M-$745M range, or organic growth at or below 3%. |  |
| 31 | AGIO | +10.5% | 42% | 75% | neutral/med | 0.25 |  | mid | 12.2% | 0.52 | 2026-10-29 (EDGAR+91d) | FDA issues a CRL or delays the mitapivat sickle cell sNDA past the 2026-11-01 PDUFA date. | top-15 #8 |
| 32 | ENS | +10.3% | 41% | 61% | neutral/med | 0.25 |  | mid | 10.0% | 0.66 | 2026-11-11 (EDGAR+91d) | Q2 FY27 adjusted EPS ex-45X below $1.95 or sales below $955M, reported about early November 2026 (SEC 8-K 2026-08-12 guidance). |  |
| 33 | PRGS | +9.5% | 38% | 73% | neutral/med | 0.25 |  | small | 11.9% | 0.59 | 2026-09-30 (card) <=5 SESS | The 2026-09-30 Q3 print: revenue below the $244-250M high end or non-GAAP EPS below $1.59 would prove the bull case wrong. | top-15 #13 |
| 34 | BA | +9.5% | 38% | 46% | neutral/med | 0.25 |  | mega | 7.5% | 0.17 | 2026-10-27 (EDGAR+91d) | 737 MAX 10 certification slipping past 2026, or FAA/EASA action on the navigation glitch, or a SPEEA strike after the 2026-10-06… |  |
| 35 | GOOGL | +9.3% | 25% | 50% | supports/med | 0.75 | yes | mega | 8.2% | 0.52 | 2026-10-28 (card) | Q3 2026 results due about 2026-10-28: Google Cloud year-over-year growth below 50%, or total operating margin below 32%, or decli… |  |
| 36 | TER | +9.1% | 12% | 121% | supports/med | 0.75 |  | large | 19.8% | 0.65 | 2026-10-27 (card) | Q3-26 earnings 2026-10-27: revenue below $1,200M or Semiconductor Test revenue down sequentially would show the AI/memory order c… |  |
| 37 | VRT | +8.4% | 34% | 101% | neutral/med | 0.25 |  | mega | 16.5% | 0.49 | 2026-10-28 (EDGAR+91d) | Q3 2026 organic growth below the guided 34-36pc, or any cut to FY26 $13.8-14.2B sales / $6.65-6.75 EPS, reported at the October 2… |  |
| 38 | VG | +8.0% | 32% | 90% | neutral/med | 0.25 |  | large | 14.6% | 0.26 | 2026-11-09 (card) | Plaquemines Phase 1 COD not achieved by 2026-12-31, or FY2026 Adjusted EBITDA guided below 8.7B dollars, or Q3-2026 realised fixe… |  |
| 39 | BN | +7.7% | 48% | 31% (binds) | neutral/med | 0.25 |  | large | 5.0% |  | 2026-11-12 (card) | Q3 2026 DE before realizations per share reported on 2026-11-12 below 0.61 USD, or quarterly fundraising under 77B USD. |  |
| 40 | WDAY | +7.6% | 10% | 90% | supports/med | 0.75 |  | large | 14.7% | 0.65 | 2026-11-24 (card) | Q3 FY2027 results (estimated 2026-11-24) with subscription revenue below the guided 2.515B USD or non-GAAP margin below 30.0%, or… |  |
| 41 | WST | +7.5% | 10% | 36% | supports/med | 0.75 |  | large | 5.8% | 0.67 | 2026-10-22 (EDGAR+91d) | Q3 2026 earnings: reported net sales growth below 1.9% year over year, or organic growth below the guided +7.0-8.9%, or an FY26 g… |  DROP/TRIM |
| 42 | DKNG | +7.4% | 59% | 68% | neutral/med | 0.25 | yes | large | 11.0% | 0.43 | 2026-11-05 (card) | Q3-2026 print (est. 2026-11-05) showing Sports Net Revenue Margin still below 8% with FY2026 Adjusted EBITDA guided under $700M. |  |
| 43 | AVPT | +7.3% | 29% | 58% | neutral/med | 0.25 |  | mid | 9.4% | 0.40 | 2026-11-05 (EDGAR+91d) | Q3 2026 results (due about early November 2026): total revenue below $128.2m or non-GAAP operating income below $21.0m, or FY2026… |  |
| 44 | PRCH | +6.4% | 26% | 88% | neutral/med | 0.25 |  | mid | 14.4% | 0.22 | 2026-11-04 (card) | Q3 2026 results (est. 2026-11-04) showing Reciprocal policies written growth below 38% YoY or statutory surplus under $169.9M. |  |
| 45 | VRTX | +6.3% | 8% | 41% | supports/med | 0.75 |  | large | 6.7% | 0.48 | 2026-11-02 (card) | FDA rejects or delays the povetacicept BLA on or before its 2026-11-30 PDUFA date, removing the renal-franchise launch. |  |
| 46 | NOW | +5.2% | 7% | 80% | supports/med | 0.75 |  | mega | 13.0% | 0.48 | 2026-10-28 (card) | Q3 2026 report (~2026-10-28): FY2026 subscription guidance cut below $15.76B, or subscription growth under ~22% YoY, or AI ACV no… |  |
| 47 | MU | +5.0% | 40% | 111% | neutral/med | 0.25 | yes | mega | 18.0% | 0.40 | 2026-09-30 (card) <=5 SESS | The FQ4 FY2026 print due 2026-09-30: revenue below $49.0B, GAAP gross margin below ~86%, or non-GAAP EPS below $31.00 would prove… | top-15 #11 |
| 48 | SNDR | +5.0% | 20% | 44% | neutral/med | 0.25 |  | mid | 7.2% | 0.61 | 2026-10-29 (card) | Q3 2026 results (est. 2026-10-29): FY2026 adjusted EPS guidance cut below 0.90, or Truckload operating ratio back above 93.6%, or… |  |
| 49 | NVO | +4.9% | 20% | 56% | neutral/med | 0.25 |  | large | 9.1% |  | 2026-11-04 (card) | Q3 2026 results on 2026-11-04 showing adjusted sales growth outside the 0% to -6% CER guidance, or US weekly Wegovy pill prescrip… |  |
| 50 | HUBS | +4.2% | 17% | 119% | neutral/med | 0.25 |  | large | 19.3% | 0.54 | 2026-11-04 (card) | Q3 2026 results on 2026-11-04: as-reported revenue growth below the guided 14%, or net new customers below the guided 5,000-6,000… |  |
| 51 | INCY | +2.3% | 3% | 43% | supports/med | 0.75 |  | large | 7.0% | 0.33 | 2026-10-27 (EDGAR+91d) | Q3 2026 report (late Oct/early Nov 2026) cutting FY26 total net sales below $5,130M or Opzelura below $1,050M, or Jakafi net sale… |  |
| 52 | HOOD | +2.2% | 9% | 100% | neutral/med | 0.25 |  | mega | 16.4% |  | 2026-11-04 (card) | Q3 2026 print (est. 2026-11-04) shows event-contract revenue below Q2's $156M, or another large state orders withdrawal beyond Mi… |  DROP/TRIM |
| 53 | HELE | +2.1% | 8% | 76% | neutral/med | 0.25 |  | small | 12.3% | 0.58 | 2026-10-08 (card) | The 2026-10-08 Q2 FY27 report: H1 adjusted EPS not near 20% of the $3.25-3.75 guide, or Q2 gross margin falling beyond the guided… |  |
| 54 | META | +1.3% | 5% | 71% | neutral/med | 0.25 |  | mega | 11.5% | 0.58 | 2026-10-28 (card) | Q3 2026 results on 2026-10-28: revenue below the 61B usd guidance floor, or FY2026 capex above 145B usd, or free cash flow still… |  |
| 55 | RHI | -0.0% | -5% | 88% | against/med | 0.00 |  | mid | 14.3% | 0.84 | 2026-10-22 (EDGAR+91d) | Q3 2026 results, due late October 2026: revenue below USD1.31B or EPS below USD0.43, or Protiviti adjusted revenue down more than… |  |
| 56 | ACI | +0.0% | 22% | 83% | against/high | 0.00 |  | mid | 13.6% | 0.71 | 2026-10-13 (card) | Q2 FY2026 results due about 2026-10-13: identical sales above 0.0% and Adjusted EBITDA at or above $3.625bn would prove the weak-… |  |
| 57 | PEGA | +0.0% | 19% | 80% | against/high | 0.00 |  | mid | 13.0% | 0.74 | 2026-10-20 (EDGAR+91d) | Q3 2026 results showing FY2026 ACV growth below the ~10% the CFO indicated on 2026-09-08, or Pega Cloud ACV growth under 20% vers… |  |
| 58 | SMPL | +0.0% | 50% | 74% | against/med | 0.00 |  | mid | 12.0% | 0.64 | 2026-10-31 (card) | Q4 FY26 results around late Oct 2026: net sales outside $322-332M or adjusted EBITDA outside $52-57M, or a further FY27 guidance… |  |
| 59 | RGEN | -0.0% | -0% | 64% | neutral/med | 0.25 |  | large | 10.4% | 0.37 | 2026-10-27 (card) | BioLife stockholders fail to adopt the merger at the 2026-10-05 special meeting, or Q3 2026 GAAP operating margin (due ~2026-10-2… |  DROP/TRIM |
| 60 | MAN | -0.0% | -0% | 102% | neutral/med | 0.25 |  | mid | 16.5% | 0.70 | 2026-10-15 (card) | Q3 2026 results (est. 2026-10-15) diluted EPS outside the guided 0.96-1.06, or gross margin below ~16%, would prove the bull case… |  |
| 61 | BE | -0.7% | -3% | 152% | neutral/med | 0.25 |  | mega | 24.8% | 0.14 | 2026-10-29 (card) | Oracle terminates or formally suspends the Project Jupiter master agreement, or Bloom discloses a scandium-oxide supply disruptio… |  |
| 62 | AAPL | -0.9% | -4% | 40% | neutral/med | 0.25 |  | mega | 6.5% | 0.71 | 2026-10-29 (EDGAR+91d) | Q4 FY26 gross margin materially below about 48pct excluding tariff refunds, or iPhone revenue growth under 10pct y/y, reported la… |  |
| 63 | AMGN | -1.5% | -6% | 48% | neutral/med | 0.25 |  | mega | 7.9% | 0.57 | 2026-11-03 (card) | Q3 2026 results on 2026-11-03 showing FY non-GAAP EPS below the $22.30 guidance floor or product-sales growth under 9%. |  |
| 64 | IRDM | -3.5% | -14% | 78% | neutral/med | 0.25 |  | mid | 12.6% | 0.64 | 2026-10-21 (EDGAR+91d) | Regulatory approval denied or the Rocket Lab merger terminated or renegotiated before the guided mid-2027 close, or the $54.00 sp… |  |
| 65 | PSNL | -4.7% | -6% | 90% | supports/med | 0.75 |  | mid | 14.7% | 0.24 | 2026-11-03 (EDGAR+91d) | The Personalis special meeting fails to adopt the Tempus merger, or Tempus Class A closes below $46.00 giving Personalis a termin… |  |

Not scored (no v3 card, no σ63, or no analyst mean target in the 09-27 snapshot): NVEC (no target), AARD (no σ63, against), TEM (card REFUSED_UNPARSEABLE_WEB), AMSC (card REFUSED_EMPTY_LOG)

**Construction checks on the top 10 as an equal-weight 10% book** (the freeze gate's construction rules, `scripts/night_backtest_factory.freeze_gate`, run on the 2026-09-25 bars): see the gate line below. Rows marked '<=5 SESS' print inside the first five sessions after entry (by 2026-10-02): at >10% weight the gate would refuse them; at 10% they pass but the first week is a coin flip on the print (the voided liqw book's lesson).

**Gate result:** max_name_weight_le_0.15 = True; effective_n_ge_8 = True; no_rho_0_8_cluster_above_40pct = True; no_name_gt_10pct_printing_in_first_5_sessions = True; largest_name_to_zero_le_150k = True; timing: {'bars_le_1_session_old': True}; effective N 10.0, largest name to zero $100,000, max rho>0.8 cluster [] (0.0). Earnings passed to the gate: VKTX NOT_DUE; KYTX NOT_DUE; NTLA NOT_DUE; HWM NOT_DUE; SOC NOT_DUE; IONQ NOT_DUE; NOVT NOT_DUE; AGYS NOT_DUE; NVT NOT_DUE; AMZN NOT_DUE.


## 3b. The research note's top-15 and drops (attributed: Sonnet research note, 2026-09-27)

Source: `docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md` - demand / how the company feeds it / CEO / competition / profitability / street / crowd / ROI read per name. Its rows are copied as written; the 'In the formula list' column says where the same name ranks in section 3 (blank = not carded or no snapshot upside).


### (A) The note's ROI-maxing top 15 (its own ranking: mechanism + falsifier; every crowd flag reads 'n/a - not checked')

| # | Ticker | Mechanism | Upside (target vs. spot, 2026-09-27 reads) | Falsifier | Crowd flag | In the formula list |
|---|---|---|---|---|---|---|
| 1 | PRAX | Dec 27 PDUFA binary; $1.37B cash funds either outcome; 19-analyst Strong Buy independently reproduces v2's own two-days-earlier number | +127.5% | "extension precedes a CRL" (v2's own falsifier) | n/a — not checked | #16 |
| 2 | BBIO | Approved, +202% revenue-growth drug (Attruby) taking share from Pfizer's Vyndaqel franchise — growth is already revenue, not a readout | +66.4% | Pfizer defends share faster than expected; CEO's routine selling accelerates | n/a — not checked | #23 |
| 3 | VKTX | Obesity data (Sept durability) vs. Novo/Lilly duopoly; broadest biotech coverage here (20 analysts) | +166.1% | Sept 24 $500M dilution round + insiders sold straight into it — dilution risk is live | n/a — not checked | #1 |
| 4 | LEU | Domestic HALEU-enrichment monopoly; WSJ independently reaffirmed the exact thesis same day (2026-09-26) | +68.2% | DOE stays the only customer (v2's own falsifier) | n/a — not checked | #20 |
| 5 | MP | Fastest real revenue growth (+72%) of any non-biotech name here; government floor-price/offtake; insiders sold at HIGHER prices than today | +52.1% | Section 232 tariff never lands; INTC-style legal challenge to the equity stake | n/a — not checked | #25 |
| 6 | CCJ | Broadest nuclear-theme coverage (21 analysts); complements LEU (mining vs. enrichment) | +45.1% | Revenue and margins both declining this year — a cycle bet, not a growth bet | n/a — not checked | #29 |
| 7 | COGT | 12-analyst Strong Buy, $792M cash runway, named competitive threat (Blueprint's approved Ayvakit) is explicit, not hidden | +72.8% | Blueprint share-loss/label expansion in the same indication | n/a — not checked | #21 |
| 8 | AGIO | Real, +141%-growing first-in-category revenue (Pyrukynd) + Nov 1 PDUFA five weeks out | +42.0% | CRL on mitapivat | n/a — not checked | #31 |
| 9 | AMSC | Genuine margin turnaround (op margin flipped positive), debt-free, direct AI-power-grid beneficiary | +105.8% | Only 4 analysts back the number — thin-coverage caveat is the falsifier's other half | n/a — not checked |  |
| 10 | IONQ | Dated NVIDIA-decoder collaboration (Sep 23, 2026), fortress balance sheet ($2.06B net cash) | +47.6% | v2's own falsifier: "no third-party replication" | n/a — not checked | #6 |
| 11 | MU | FQ4 print in 3 days (2026-09-30); HBM4 allocation story; the one Tier-2 name whose near-term magnitude arguably overrides the "mega-cap sensor" rule | +45.8% | Print misses $49.0B revenue / 86% gross margin / $31.00 EPS bar (companion doc's own falsifier) | n/a — not checked | #47 |
| 12 | AGYS | Accelerating revenue (+16% latest quarter), Strong Buy, clean balance sheet, catalyst lands exactly at the rehearsal book's own Oct 26 check date | +35.0% | CEO's $21.3M August sale turns out to be a warning, not routine | n/a — not checked | #8 |
| 13 | PRGS | Fastest software grower here (+15.5%), 30%+ FCF margin, Strong Buy, Oct 21 catalyst | +45.4% | Acquisition-roll-up model stumbles on integration | n/a — not checked | #33 |
| 14 | NOVT | Direct humanoid-robotics-servo demand claim (v2's own thesis); healthy balance sheet | +35.1% | Only 3 analysts — thin coverage; CEO sold all year | n/a — not checked | #7 |
| 15 | ABSI | Rare, genuine three-person open-market insider-buying cluster (director, director, CIO) against a real competitive-scale disadvantage | +39.1% | Recursion/Isomorphic Labs out-execute on partnership deals | n/a — not checked | #27 |


### (B) Names the note drops or trims from v2

| Ticker | Reason (the note's words, trimmed) | In the formula list |
|---|---|---|
| RGEN | the "Strong Buy" label is stale relative to its own target: $189.48 target vs. $189.68 spot is -0.11%, and the CEO sold at $190 and $180 the same week this research ran. There is no more asymmetry left in this name at these levels. | #59 |
| WST | only +10.0% upside, and a brand-new, unproven CEO (Michel Lagarde, in the seat five weeks) who wasn't in v2's thesis at all. Trim, don't add to; not enough asymmetry to justify fresh capital. | #41 |
| QUBT | (Murat's personal holding, separate from the v2 book which already excludes it) this pass's own research reproduces v2's original veto almost exactly: wide analyst dispersion, thin fresh crowd conviction (2026-09-25 reddit read found essentially no substantive QUBT discussion), and no new demand fact found to overturn the "prom… | #11 |
| HOOD | not a drop from the book (still a real, growing business), but flagged for a trim: CEO Vlad Tenev sold roughly $60M across two consecutive days (Sep 21-22, 2026), the single most concentrated insider-selling event found anywhere in this pass, landing right before this research ran. | #52 |


### (C) New candidates the note found

| Ticker | Why / source (the note's words, trimmed) | In the formula list |
|---|---|---|
| BBIO | found via the v2 book itself (already a 1% holding) but re-graded up hard on this pass: it is the only name in the whole document with real, approved, +202%-growing product revenue rather than a future readout. Source: stockanalysis.com/stocks/bbio (read 2026-09-27). | #23 |
| AMSC | found via mw_analyst_snapshot.jsonl; a genuine margin-turnaround, debt-free AI-power-grid name adjacent to VRT/GEV/NVT but not currently in any Aegis book. Source: backend/data/optimus/news_corpus/ dowjones/_structured/mw_analyst_snapshot.jsonl + stockanalysis.com/finviz (read 2026-09-27). |  |
| ABSI | found via mw_analyst_snapshot.jsonl; the insider-buying cluster (three separate people, all open-market, all 2026) is unusual enough to be worth a dedicated look outside this note. Same sources. | #27 |
| PSNL/TEM merger arb | found via the WSJ Heard on the Street row for PSNL (predictions.jsonl, made 2026-09-26): a live, dated, sourced arbitrage situation (Tempus AI's pending acquisition of Personalis, shares trading above the $16.25 deal price) that is not currently a position in any book. |  |
| AGYS / PRGS / NOVT | already in Aegis's universe (dress rehearsal book, v2 book respectively) but worth flagging as *new to the ROI-maxing frame specifically*: none of the three had been read for demand/CEO/competition/crowd before this pass. | #8 |


### (D) What the note found changed since 2026-09-26

| Item | Change (the note's words, trimmed) | In the formula list |
|---|---|---|
|  | NVEC: the company profile now names Peter Eames as CEO; Aegis's own insider-trading pull still shows the most recent CEO-tagged Form 4 under Daniel Baker. A leadership transition appears to have happened that the repo's data has not caught up to — worth a dedicated Form-4/8-K check before the next read. |  |
|  | WST: Michel Lagarde became CEO effective 2026-08-31, succeeding Eric Green — inside the last four weeks, and not reflected in v2's thesis text. |  |
|  | NVO: rebranded from "Novo Nordisk" to "Novo" on 2026-09-14; Mike Doustdar is CEO; Morgan Stanley downgraded to Underweight 2026-09-11; WSJ's 2026-09-26 piece adds a fresh negative catalyst (failed cardiovascular trial for an inflammation drug) on top of an already -23.7% YTD stock. |  |
|  | QUBT: CEO is Dr. Yuping Huang, not an earlier-assumed name; a new Chief Revenue Officer (Susan Hunt) was a recent appointment per the company profile. |  |
|  | PSNL/TEM: the Tempus acquisition of Personalis, and PSNL trading above the $16.25 deal price "signaling investors expect a higher bid," is a 2026-09-26-dated WSJ claim not previously in any Aegis book. |  |
|  | BSP (Bending Spoons): a fresh, dated (2026-09-26) WSJ bear case — rising rates threaten the acquisition-funded growth model — arrived the same day Aegis's own predictions ledger picked it up as a Dow Jones row for the first time. |  |
|  | The Bloomberg dress-rehearsal book itself (NVEC, MAN, RHI, ACI, PEGA, IRDM, HELE, SMPL, PRGS, AGYS) was frozen 2026-09-27, entering 2026-09-28 — every dress-rehearsal name in this note is being read for demand/CEO/competition for the first time. |  |
|  | The 2026-09-27 committee PROBE contract (backend/data/optimus/decisions/2026-09-27.json, chunk 18) is far larger than the pc_plan file this note's brief pointed to (97 rows, 92 PROBE, capital $40,000, mandate REFUSED on capital/cap disagreements) and adds names not otherwise in this shortlist (ADUS, ALG, ARCO, BR, CHD, CHH, GMA… |  |
|  | The companion quant document (stock_lists_2026-09-27_v3.md) landed the same day and independently confirms two of this note's own findings: NVT ranks #1 on its σ-bounded formula (matching this note's Tier-2 read), and it carries the standing §17 caveat this note has folded into every upside number above. |  |


---


# 4. Murat's holdings vs the v3 verdicts

Source: `backend/data/murat_book.yaml` (reconciled 2026-08-11; confirmed: False; cash unrecoverable). The recorded share counts are -5.09% since 2026-08-11 vs SPY +0.35% (-5.44 pp; `roi_2026-09-27.json`, AARD unpriced - absent from the bars panel). All twelve are carded on 2026-09-27 except AMSC (card refused, REFUSED_EMPTY_LOG) and AARD (no bars: no σ63), which keep their 09-25 card where one exists. MW = the MarketWatch analyst snapshot read 2026-09-26 (Dow Jones bundle).

| Ticker | Shares | Cost | Card (v3, else 09-25) | Changed | σ63 move 21s | Fund. | MW analyst snapshot | Card falsifier | Kill condition (logged) |
|---|---|---|---|---|---|---|---|---|---|
| AARD | 1000 | 10 | against/high | against/med -> against/high |  |  | Overweight, n 11, mean 10.13 (lo 3.00 / hi 28.00) vs px 5.55; next EPS 04/05/2027 | By 2026-09-30, Aardvark releases unblinded HERO and OLE data showing meaningful hyperphagia reduction with no cardiac QRS signal, and the FDA lifts t… | coverage drops below four analysts or the consensus cracks |
| BHVN | 300 | 8 | neutral/med | against/med -> neutral/med | 18.2% | 0.33 | Overweight, n 14, mean 23.08 (lo 10.00 / hi 42.00) vs px 13.19; next EPS 03/08/2027 | An FDA escalation of the 2026-09-04 partial hold to a full clinical hold on BHV-7000, or RISE3/BHV7000-303 topline slipping past 2026-12-31. | a second regulatory setback on the core pipeline |
| DKNG | 150 | 29 | neutral/med | same | 11.0% | 0.43 | Overweight, n 42, mean 34.33 (lo 20.00 / hi 76.00) vs px 21.27; next EPS 02/18/2027 | Q3-2026 print (est. 2026-11-05) showing Sports Net Revenue Margin still below 8% with FY2026 Adjusted EBITDA guided under $700M. | consensus target falls below entry, or two quarters of negative revisions |
| QUBT | 300 | 13 | neutral/med | against/high -> neutral/med | 15.1% | 0.42 | Overweight, n 8, mean 18.86 (lo 10.00 / hi 32.00) vs px 9.16; next EPS 03/31/2027 | Q3 2026 report (~November 2026) showing consolidated gross margin still negative AND sequential revenue flat excluding acquisitions, or a goodwill im… | narrative rotation; dilution at these levels |
| SLDP | 600 | missing | neutral/med | against/med -> neutral/med | 12.5% | 0.34 | Buy, n 2, mean 6.88 (lo 6.75 / hi 7.00) vs px 2.35; next EPS 03/02/2027 | No Korea commercial-scale electrolyte JV announced by 2026-12-31, or the continuous pilot line misses Q4 2026 startup or the 75 MT/y target. | a named OEM partnership lapses without replacement, or cash runway falls below 12 months |
| ABSI | 600 | missing | neutral/med | neutral/low -> neutral/med | 19.5% | 0.28 | Buy, n 11, mean 14.40 (lo 10.00 / hi 17.00) vs px 10.35; next EPS 03/23/2027 | ABS-201 interim pattern-hair-loss proof-of-concept data, guided 2H 2026, missing or showing no efficacy signal by 2026-12-31. | cash runway falls below 12 months, or a lead programme is discontinued without a named su… |
| AMSC | 50 | missing | neutral/med | (not re-carded) | 14.0% | 0.49 | Buy, n 5, mean 61.40 (lo 54.00 / hi 71.00) vs px 30.42; next EPS 06/02/2027 | Q2 FY26 results (estimated 2026-11-04) showing revenue below 85M or gross margin still near 26 pct would prove the bull case wrong. | two consecutive quarters of declining grid-segment backlog, or the largest customer conce… |
| HUBS | 10 | missing | neutral/med | same | 19.3% | 0.54 | Overweight, n 38, mean 249.63 (lo 190.00 / hi 327.00) vs px 221.56; next EPS 02/17/2027 | Q3 2026 results on 2026-11-04: as-reported revenue growth below the guided 14%, or net new customers below the guided 5,000-6,000, would prove the du… | net revenue retention falls below 100% for two consecutive quarters |
| KYTX | 250 | missing | supports/med | neutral/med -> supports/med | 15.6% | 0.38 | Buy, n 6, mean 30.40 (lo 25.00 / hi 33.00) vs px 6.99; next EPS 04/01/2027 | Any reported high-grade CRS, ICANS or IEC-HS case in miv-cel, or the rolling SPS BLA not completed by 2026-12-31. | a lead clinical programme misses its primary endpoint, or cash runway falls below 12 mont… |
| NTLA | 250 | 13 | supports/med | neutral/med -> supports/med | 14.5% | 0.27 | Overweight, n 19, mean 23.81 (lo 8.00 / hi 61.00) vs px 12.16; next EPS 02/25/2027 | An FDA complete response letter for the lonvo-z BLA on or before the 2027-03-10 PDUFA date, or a label requiring HLA or liver monitoring or a boxed w… | further clinical holds or serious adverse events |
| PRCH | 200 | 10 | neutral/med | same | 14.4% | 0.22 | Buy, n 8, mean 20.69 (lo 16.50 / hi 25.00) vs px 16.47; next EPS 03/02/2027 | Q3 2026 results (est. 2026-11-04) showing Reciprocal policies written growth below 38% YoY or statutory surplus under $169.9M. | loss ratios deteriorate again |
| SOC | 700 | 5 | neutral/med | same | 46.2% | 0.25 | Buy, n 7, mean 9.40 (lo 8.00 / hi 11.00) vs px 3.97; next EPS 03/22/2027 | Platform Hondo fails to come online by 2026-09-30, or Q3 2026 net sales fall below 40,000 Boe/d versus 2H 2026E guidance of 40,000-45,000. | consensus breaks below the mark |

Reading: an 'against' card is a statement about the evidence for the bull case, not an instruction to sell; the kill condition is Murat's own logged exit condition (auto-adopted defaults for ABSI, AMSC, HUBS, KYTX, SLDP), never an armed order.


---


# 5. ANALYST-IMPLIED UPSIDE >= 50% and >= 100% (from the 2026-09-27 pull)

**CAVEAT (§17):** target-LEVEL upside is a perverse cross-sectional signal in this repo's data: -90 bps/mo large/mid (t -3.62), -199 bps/mo small (t -7.21). High implied upside most often means the price fell and the targets have not caught up. Every row is a name to research, not a buy.

Source: `backend/data/optimus/analyst/target_snapshots.parquet` (latest row per ticker; this pull observed 2026-09-26T16:18Z - 2026-09-26T17:14Z = 2026-09-27 ~01:14 HKT; `analyst_pull_2026-09-27.json`: 3,096 snapshots, 0 failed). Screen: implied_upside >= 0.50 and price >= $2 -> **700** names (229 at >= 100%). Analyst count and strong-buy/buy/hold/sell mix: yfinance Ticker.info numberOfAnalystOpinions + Ticker.recommendations (current month), fetched 2026-09-27 for this version (v2 fetched 2026-09-25). Band = median 63-session dollar volume on the bars panel (mega >= $1B, large >= $100M, mid >= $20M, else small). 'vs v2' = the band this name had in v2 (A = >= 100%, B = 50-100%, C = < 5 analysts) and v2's upside.


## 5a. Implied upside >= 100% with n >= 5 analysts - 167 names

| Ticker | Price | Mean target | Median / high | Upside | n | Mix SB/B/H/S (key) | Band (med $vol) | σ63 move 21s | vs v2 |
|---|---|---|---|---|---|---|---|---|---|
| WULF | 15.74 | 33.69 | 31.50 / 62.50 | 114% | 24 | SB 5 / B 18 / H 1 / S 0 (strong_buy) | large ($540.0M) | 21% | same band (v2 105%) |
| ARRY | 4.03 | 8.60 | 8.50 / 13.00 | 113% | 22 | SB 1 / B 9 / H 13 / S 0 (buy) | mid ($30.3M) | 13% | same band (v2 122%) |
| KTOS | 45.62 | 102.76 | 104.00 / 150.00 | 125% | 21 | SB 4 / B 15 / H 2 / S 0 (strong_buy) | large ($180.1M) | 13% | same band (v2 120%) |
| OKLO | 38.04 | 76.42 | 78.00 / 130.00 | 101% | 20 | SB 6 / B 9 / H 9 / S 1 (buy) | large ($368.3M) | 19% | same band (v2 101%) |
| VKTX | 35.56 | 94.82 | 95.00 / 125.00 | 167% | 19 | SB 5 / B 13 / H 2 / S 0 (strong_buy) | mid ($66.7M) | 19% | same band (v2 164%) |
| PRAX | 280.78 | 638.68 | 575.00 / 1,201.00 | 127% | 19 | SB 3 / B 14 / H 1 / S 1 (strong_buy) | large ($118.6M) | 13% | same band (v2 127%) |
| QXO | 12.43 | 28.94 | 27.00 / 50.00 | 133% | 18 | SB 4 / B 14 / H 0 / S 0 (strong_buy) | large ($247.7M) | 13% | same band (v2 137%) |
| XENE | 36.94 | 74.87 | 74.50 / 100.00 | 103% | 18 | SB 3 / B 15 / H 1 / S 0 (strong_buy) | mid ($45.3M) | 19% | same band (v2 102%) |
| WVE | 3.78 | 18.53 | 15.00 / 42.00 | 390% | 17 | SB 2 / B 14 / H 2 / S 0 (strong_buy) | small ($14.9M) | 13% | same band (v2 376%) |
| IRD | 4.76 | 13.00 | 12.00 / 20.00 | 173% | 17 | SB 3 / B 15 / H 0 / S 0 (strong_buy) | small ($3.4M) | 20% | same band (v2 177%) |
| JANX | 16.30 | 36.24 | 29.00 / 75.00 | 122% | 17 | SB 2 / B 14 / H 1 / S 1 (strong_buy) | small ($13.5M) | 11% | same band (v2 121%) |
| NTLA | 11.75 | 24.00 | 17.00 / 61.00 | 104% | 17 | SB 1 / B 9 / H 6 / S 3 (none) | mid ($45.7M) | 14% | same band (v2 100%) |
| PONY | 6.89 | 20.12 | 18.65 / 32.80 | 192% | 16 | SB 3 / B 14 / H 1 / S 0 (strong_buy) | mid ($23.5M) | 12% | same band (v2 181%) |
| GPCR | 35.93 | 105.78 | 101.00 / 145.00 | 194% | 15 | SB 4 / B 11 / H 1 / S 0 (strong_buy) | mid ($33.8M) | 13% | same band (v2 199%) |
| APLD | 26.25 | 66.43 | 70.00 / 109.00 | 153% | 15 | SB 2 / B 11 / H 2 / S 0 (strong_buy) | large ($474.7M) | 20% | same band (v2 145%) |
| DYN | 16.03 | 37.20 | 37.00 / 50.00 | 132% | 15 | SB 3 / B 13 / H 0 / S 1 (strong_buy) | mid ($49.5M) | 13% | same band (v2 127%) |
| NAMS | 22.58 | 50.89 | 51.08 / 59.65 | 125% | 15 | SB 3 / B 12 / H 1 / S 0 (strong_buy) | mid ($31.0M) | 12% | same band (v2 126%) |
| LFTO | 15.91 | 33.40 | 34.00 / 42.00 | 110% | 15 | SB 5 / B 8 / H 4 / S 0 (buy) | small ($13.1M) | 19% | same band (v2 108%) |
| CATX | 2.52 | 12.29 | 13.00 / 18.00 | 388% | 14 | SB 2 / B 13 / H 1 / S 0 (strong_buy) | small ($3.9M) | 16% | same band (v2 394%) |
| FRVO | 15.18 | 39.07 | 40.50 / 51.00 | 157% | 14 | SB 4 / B 10 / H 0 / S 0 (strong_buy) | mid ($69.2M) | 30% | same band (v2 143%) |
| VERA | 32.54 | 77.50 | 81.50 / 100.00 | 138% | 14 | SB 1 / B 12 / H 1 / S 0 (strong_buy) | mid ($63.0M) | 14% | same band (v2 137%) |
| CLYM | 11.66 | 27.57 | 26.50 / 40.00 | 136% | 14 | SB 2 / B 13 / H 0 / S 0 (strong_buy) | small ($19.0M) | 17% | same band (v2 136%) |
| VNET | 6.64 | 13.62 | 13.41 / 25.03 | 105% | 14 | SB 4 / B 9 / H 0 / S 1 (strong_buy) | mid ($25.7M) | 19% | B -> A (v2 97%) |
| CLDX | 31.10 | 62.50 | 62.00 / 100.00 | 101% | 14 | SB 2 / B 12 / H 1 / S 0 (strong_buy) | mid ($33.3M) | 11% | same band (v2 100%) |
| STRO | 15.98 | 47.23 | 50.00 / 61.00 | 196% | 13 | SB 3 / B 10 / H 0 / S 1 (strong_buy) | small ($5.2M) | 15% | same band (v2 203%) |
| TSHA | 4.67 | 13.00 | 12.00 / 19.00 | 178% | 13 | SB 3 / B 10 / H 0 / S 0 (strong_buy) | small ($14.2M) | 14% | same band (v2 175%) |
| ALHC | 8.21 | 22.23 | 22.00 / 28.00 | 171% | 13 | SB 3 / B 9 / H 2 / S 0 (strong_buy) | mid ($76.6M) | 21% | same band (v2 198%) |
| SLDB | 7.29 | 18.62 | 18.00 / 26.00 | 155% | 13 | SB 5 / B 8 / H 0 / S 0 (strong_buy) | small ($8.7M) | 14% | same band (v2 147%) |
| MPLT | 10.46 | 26.54 | 25.00 / 43.00 | 154% | 13 | SB 1 / B 11 / H 2 / S 0 (none) | small ($9.3M) | 63% | same band (v2 149%) |
| LEGN | 19.11 | 46.90 | 48.00 / 74.00 | 145% | 13 | SB 5 / B 3 / H 5 / S 0 (buy) | mid ($40.6M) | 14% | same band (v2 155%) |
| MLTX | 12.04 | 28.54 | 30.00 / 50.00 | 137% | 13 | SB 1 / B 10 / H 2 / S 2 (buy) | mid ($21.4M) | 12% | same band (v2 134%) |
| BEAM | 24.27 | 52.15 | 45.00 / 80.00 | 115% | 13 | SB 1 / B 12 / H 2 / S 0 (strong_buy) | mid ($48.2M) | 15% | same band (v2 116%) |
| KC | 9.66 | 20.21 | 20.07 / 26.44 | 109% | 13 | SB 3 / B 11 / H 0 / S 0 (none) | small ($11.8M) | 16% | same band (v2 107%) |
| QFIN | 7.30 | 14.80 | 14.04 / 23.02 | 103% | 13 | SB 3 / B 5 / H 3 / S 2 (buy) | small ($15.4M) | 14% | B -> A (v2 97%) |
| IVA | 3.37 | 14.87 | 13.50 / 26.00 | 341% | 12 | SB 1 / B 11 / H 0 / S 0 (strong_buy) | small ($4.3M) | 13% | same band (v2 370%) |
| RCKT | 2.60 | 8.85 | 9.50 / 15.00 | 241% | 12 | SB 1 / B 6 / H 5 / S 2 (buy) | small ($5.0M) | 15% | same band (v2 216%) |
| KURA | 10.76 | 32.00 | 28.00 / 76.00 | 197% | 12 | SB 2 / B 12 / H 1 / S 0 (none) | small ($18.9M) | 13% | same band (v2 195%) |
| AVTX | 15.47 | 44.08 | 40.50 / 60.00 | 185% | 12 | SB 2 / B 12 / H 0 / S 0 (strong_buy) | small ($15.7M) | 14% | same band (v2 191%) |
| MAZE | 26.05 | 61.50 | 54.00 / 110.00 | 136% | 12 | SB 1 / B 12 / H 0 / S 0 (strong_buy) | small ($10.7M) | 15% | same band (v2 127%) |
| ENOV | 18.46 | 38.33 | 36.50 / 52.00 | 108% | 12 | SB 2 / B 10 / H 1 / S 0 (none) | mid ($28.7M) | 19% | same band (v2 110%) |
| STUB | 5.44 | 11.12 | 11.00 / 16.00 | 105% | 12 | SB 0 / B 8 / H 5 / S 1 (buy) | mid ($41.3M) | 15% | same band (v2 111%) |
| IMCR | 30.72 | 62.50 | 60.00 / 100.00 | 103% | 12 | SB 1 / B 2 / H 0 / S 0 (none) | small ($14.4M) | 8% | same band (v2 101%) |
| FTH | 28.00 | 56.67 | 56.00 / 70.00 | 102% | 12 | SB 3 / B 11 / H 0 / S 0 (strong_buy) | small ($8.7M) | 23% | B -> A (v2 98%) |
| CELC | 79.52 | 160.75 | 161.50 / 177.00 | 102% | 12 | SB 3 / B 10 / H 0 / S 0 (strong_buy) | mid ($83.2M) | 15% | same band (v2 105%) |
| EYPT | 3.62 | 25.91 | 20.00 / 68.00 | 616% | 11 | SB 1 / B 6 / H 6 / S 0 (buy) | mid ($20.3M) | 55% | same band (v2 603%) |
| RGNX | 7.40 | 23.73 | 19.00 / 50.00 | 221% | 11 | SB 3 / B 6 / H 2 / S 0 (buy) | small ($11.8M) | 23% | same band (v2 228%) |
| SGMT | 9.24 | 27.55 | 28.00 / 56.00 | 198% | 11 | SB 2 / B 9 / H 0 / S 1 (strong_buy) | small ($9.7M) | 16% | same band (v2 231%) |
| OCUL | 9.65 | 27.09 | 28.00 / 34.00 | 181% | 11 | SB 4 / B 7 / H 0 / S 0 (strong_buy) | mid ($20.7M) | 12% | same band (v2 178%) |
| PHAT | 7.30 | 20.45 | 21.00 / 29.00 | 180% | 11 | SB 2 / B 8 / H 2 / S 0 (none) | small ($10.5M) | 19% | same band (v2 191%) |
| PRME | 2.90 | 7.11 | 7.00 / 11.00 | 145% | 11 | SB 1 / B 10 / H 3 / S 0 (strong_buy) | small ($9.6M) | 20% | same band (v2 133%) |
| WRD | 5.53 | 13.37 | 12.01 / 20.11 | 142% | 11 | SB 4 / B 8 / H 0 / S 0 (strong_buy) | small ($11.7M) | 12% | same band (v2 129%) |
| BCRX | 8.59 | 20.64 | 17.00 / 32.00 | 140% | 11 | SB 2 / B 7 / H 2 / S 0 (none) | mid ($32.4M) | 11% | same band (v2 146%) |
| CGEM | 14.81 | 33.45 | 35.00 / 42.00 | 126% | 11 | SB 1 / B 11 / H 0 / S 0 (strong_buy) | small ($13.0M) | 17% | same band (v2 114%) |
| TYRA | 21.76 | 47.45 | 50.00 / 59.00 | 118% | 11 | SB 2 / B 12 / H 1 / S 0 (strong_buy) | small ($18.4M) | 20% | same band (v2 114%) |
| TRAX | 34.42 | 71.82 | 65.00 / 100.00 | 109% | 11 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | mid ($24.1M) | 28% | same band (v2 101%) |
| WYFI | 19.62 | 40.50 | 39.00 / 50.00 | 106% | 11 | SB 2 / B 8 / H 1 / S 0 (strong_buy) | mid ($51.2M) | 29% | same band (v2 106%) |
| SNDX | 18.20 | 37.55 | 37.00 / 57.00 | 106% | 11 | SB 2 / B 10 / H 0 / S 0 (strong_buy) | mid ($28.2M) | 10% | same band (v2 113%) |
| UNCY | 4.70 | 29.60 | 27.50 / 50.00 | 530% | 10 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | small ($4.2M) | 27% | same band (v2 525%) |
| LXEO | 3.31 | 20.30 | 20.00 / 30.00 | 513% | 10 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($3.6M) | 14% | same band (v2 500%) |
| CRBP | 7.14 | 34.02 | 34.00 / 48.00 | 377% | 10 | SB 0 / B 9 / H 0 / S 0 (strong_buy) | small ($4.0M) | 16% | same band (v2 364%) |
| LRMR | 3.08 | 14.40 | 13.00 / 26.00 | 368% | 10 | SB 2 / B 9 / H 0 / S 0 (strong_buy) | small ($4.9M) | 17% | same band (v2 317%) |
| OLMA | 8.75 | 36.50 | 38.00 / 59.00 | 317% | 10 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | small ($10.7M) | 13% | same band (v2 310%) |
| ENVX | 2.87 | 11.35 | 10.00 / 21.00 | 295% | 10 | SB 0 / B 8 / H 3 / S 1 (none) | mid ($23.1M) | 21% | same band (v2 284%) |
| OCS | 9.27 | 36.61 | 39.01 / 43.89 | 295% | 10 | SB 3 / B 7 / H 0 / S 0 (strong_buy) | small ($2.7M) | 11% | same band (v2 292%) |
| ARDX | 3.42 | 12.90 | 13.50 / 18.00 | 277% | 10 | SB 1 / B 10 / H 0 / S 0 (none) | small ($14.9M) | 11% | same band (v2 273%) |
| HELP | 12.61 | 40.07 | 43.23 / 68.76 | 218% | 10 | SB 1 / B 10 / H 0 / S 0 (strong_buy) | small ($15.0M) | 21% | same band (v2 222%) |
| KRMN | 35.69 | 89.70 | 85.00 / 135.00 | 151% | 10 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | large ($134.9M) | 16% | same band (v2 163%) |
| NKTR | 57.06 | 141.40 | 150.50 / 192.00 | 148% | 10 | SB 1 / B 9 / H 2 / S 0 (strong_buy) | mid ($51.3M) | 12% | same band (v2 143%) |
| EDIT | 2.58 | 5.90 | 5.00 / 15.00 | 129% | 10 | SB 0 / B 8 / H 3 / S 2 (buy) | small ($6.2M) | 17% | same band (v2 122%) |
| NUVB | 5.74 | 13.10 | 12.50 / 21.00 | 128% | 10 | SB 3 / B 6 / H 1 / S 0 (strong_buy) | mid ($34.3M) | 13% | same band (v2 130%) |
| PLTK | 2.13 | 4.78 | 4.00 / 14.00 | 124% | 10 | SB 0 / B 2 / H 9 / S 0 (none) | small ($3.7M) | 17% | same band (v2 122%) |
| EH | 4.51 | 9.96 | 7.97 / 20.49 | 121% | 10 | SB 1 / B 5 / H 3 / S 2 (buy) | small ($3.4M) | 12% | same band (v2 123%) |
| FTAI | 175.06 | 364.10 | 337.50 / 600.00 | 108% | 10 | SB 4 / B 6 / H 0 / S 0 (strong_buy) | large ($267.4M) | 14% | same band (v2 103%) |
| ALT | 3.06 | 17.11 | 17.00 / 28.00 | 459% | 9 | SB 2 / B 7 / H 1 / S 0 (strong_buy) | small ($11.1M) | 11% | same band (v2 460%) |
| KDK | 2.43 | 10.50 | 11.00 / 13.00 | 332% | 9 | SB 1 / B 7 / H 1 / S 0 (strong_buy) | small ($4.0M) | 16% | same band (v2 270%) |
| ZNTL | 2.70 | 6.89 | 6.00 / 10.00 | 155% | 9 | SB 0 / B 5 / H 5 / S 0 (buy) | small ($3.8M) | 19% | same band (v2 149%) |
| ONDS | 7.64 | 19.42 | 19.00 / 25.00 | 154% | 9 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | large ($557.2M) | 18% | same band (v2 155%) |
| OVID | 2.40 | 5.92 | 5.00 / 9.00 | 146% | 9 | SB 0 / B 10 / H 0 / S 0 (strong_buy) | small ($3.7M) | 12% | same band (v2 144%) |
| FATE | 2.35 | 5.74 | 7.00 / 8.00 | 144% | 9 | SB 1 / B 4 / H 6 / S 0 (buy) | small ($4.1M) | 17% | same band (v2 148%) |
| STTK | 6.07 | 14.67 | 15.00 / 18.00 | 142% | 9 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | small ($6.4M) | 15% | same band (v2 132%) |
| AMPX | 9.75 | 23.00 | 22.00 / 30.00 | 136% | 9 | SB 1 / B 9 / H 0 / S 0 (none) | mid ($51.6M) | 18% | same band (v2 137%) |
| USAR | 15.18 | 35.56 | 35.00 / 45.00 | 134% | 9 | SB 1 / B 8 / H 0 / S 0 (strong_buy) | large ($190.1M) | 18% | same band (v2 130%) |
| TE | 3.78 | 8.78 | 9.00 / 16.00 | 132% | 9 | SB 1 / B 5 / H 3 / S 0 (buy) | large ($138.1M) | 25% | same band (v2 124%) |
| DMRA | 20.66 | 46.89 | 45.00 / 60.00 | 127% | 9 | SB 1 / B 9 / H 0 / S 0 (strong_buy) | small ($13.8M) | 17% | same band (v2 119%) |
| ZVRA | 11.04 | 25.00 | 24.00 / 35.00 | 126% | 9 | SB 2 / B 7 / H 0 / S 0 (none) | small ($11.1M) | 17% | same band (v2 125%) |
| PICS | 8.69 | 19.00 | 18.74 / 23.91 | 119% | 9 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($3.4M) | 14% | same band (v2 114%) |
| RZLT | 3.90 | 8.33 | 7.00 / 14.00 | 114% | 9 | SB 2 / B 6 / H 2 / S 0 (buy) | small ($5.7M) | 14% | B -> A (v2 93%) |
| EOSE | 3.17 | 6.50 | 5.00 / 10.00 | 105% | 9 | SB 1 / B 3 / H 7 / S 0 (buy) | mid ($97.4M) | 24% | B -> A (v2 98%) |
| LAC | 2.75 | 5.61 | 4.50 / 10.00 | 104% | 9 | SB 2 / B 1 / H 9 / S 0 (hold) | mid ($25.5M) | 12% | B -> A (v2 99%) |
| AVEX | 16.07 | 32.78 | 34.00 / 45.00 | 104% | 9 | SB 4 / B 5 / H 1 / S 0 (buy) | mid ($21.4M) | 20% | B -> A (v2 93%) |
| HAWK | 16.10 | 32.56 | 33.00 / 41.00 | 102% | 9 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | small ($19.4M) | 16% | same band (v2 105%) |
| CABA | 2.07 | 13.25 | 13.50 / 30.00 | 540% | 8 | SB 1 / B 7 / H 2 / S 0 (none) | small ($11.9M) | 16% | same band (v2 517%) |
| BIOA | 7.05 | 35.62 | 30.00 / 73.00 | 405% | 8 | SB 2 / B 5 / H 2 / S 0 (buy) | small ($8.1M) | 49% | same band (v2 385%) |
| CTMX | 2.70 | 12.25 | 12.00 / 16.00 | 354% | 8 | SB 3 / B 5 / H 0 / S 0 (strong_buy) | small ($8.8M) | 15% | same band (v2 343%) |
| ALMS | 7.10 | 32.12 | 32.00 / 46.00 | 352% | 8 | SB 1 / B 8 / H 1 / S 0 (strong_buy) | mid ($28.7M) | 41% | same band (v2 339%) |
| FRMI | 4.52 | 17.12 | 13.50 / 35.00 | 279% | 8 | SB 1 / B 5 / H 2 / S 0 (buy) | mid ($90.4M) | 25% | same band (v2 275%) |
| ABEO | 5.40 | 18.88 | 17.00 / 30.00 | 250% | 8 | SB 0 / B 7 / H 0 / S 0 (strong_buy) | small ($7.7M) | 14% | same band (v2 246%) |
| JBIO | 14.42 | 50.12 | 47.00 / 77.00 | 248% | 8 | SB 0 / B 10 / H 0 / S 0 (none) | small ($16.0M) | 13% | same band (v2 235%) |
| TECX | 23.67 | 76.62 | 78.00 / 93.00 | 224% | 8 | SB 1 / B 8 / H 0 / S 0 (strong_buy) | small ($5.2M) | 18% | same band (v2 219%) |
| EVMN | 8.49 | 24.12 | 24.00 / 30.00 | 184% | 8 | SB 3 / B 5 / H 2 / S 0 (buy) | small ($5.7M) | 29% | same band (v2 181%) |
| LFMD | 2.97 | 8.12 | 7.50 / 15.00 | 174% | 8 | SB 0 / B 8 / H 0 / S 0 (strong_buy) | small ($2.5M) | 15% | same band (v2 174%) |
| MGTX | 10.91 | 27.75 | 23.50 / 50.00 | 154% | 8 | SB 2 / B 5 / H 1 / S 0 (strong_buy) | small ($9.2M) | 12% | same band (v2 163%) |
| RCAT | 6.66 | 16.50 | 15.00 / 25.00 | 148% | 8 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | mid ($62.2M) | 19% | same band (v2 144%) |
| MNKD | 3.34 | 7.97 | 7.50 / 13.00 | 139% | 8 | SB 0 / B 7 / H 1 / S 0 (none) | small ($14.5M) | 13% | same band (v2 144%) |
| XE | 15.08 | 34.38 | 36.50 / 57.00 | 128% | 8 | SB 2 / B 4 / H 2 / S 1 (buy) | mid ($92.6M) | 21% | same band (v2 114%) |
| HIVE | 3.16 | 7.12 | 7.25 / 10.00 | 125% | 8 | SB 0 / B 8 / H 1 / S 0 (strong_buy) | mid ($46.8M) | 21% | same band (v2 118%) |
| SVRA | 5.00 | 10.94 | 10.25 / 16.00 | 119% | 8 | SB 2 / B 6 / H 0 / S 0 (none) | small ($8.5M) | 10% | same band (v2 119%) |
| COLL | 22.53 | 49.00 | 48.50 / 60.00 | 117% | 8 | SB 2 / B 5 / H 1 / S 0 (strong_buy) | small ($18.4M) | 13% | same band (v2 117%) |
| LAR | 5.52 | 11.69 | 10.75 / 19.80 | 112% | 8 | SB 4 / B 3 / H 1 / S 0 (buy) | small ($11.5M) | 15% | same band (v2 106%) |
| VOR | 18.52 | 39.00 | 40.00 / 50.00 | 111% | 8 | SB 1 / B 7 / H 1 / S 0 (none) | small ($19.0M) | 17% | same band (v2 114%) |
| METC | 9.02 | 18.88 | 18.00 / 30.00 | 109% | 8 | SB 0 / B 5 / H 3 / S 0 (none) | mid ($20.4M) | 19% | same band (v2 110%) |
| IMMX | 10.97 | 22.52 | 24.00 / 27.00 | 105% | 8 | SB 3 / B 4 / H 0 / S 0 (strong_buy) | small ($16.5M) | 19% | B -> A (v2 96%) |
| REAL | 8.83 | 18.00 | 18.00 / 20.00 | 104% | 8 | SB 0 / B 7 / H 2 / S 0 (strong_buy) | mid ($27.7M) | 11% | same band (v2 100%) |
| AADX | 12.64 | 25.75 | 24.50 / 30.00 | 104% | 8 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | mid ($20.8M) | 17% | same band (v2 100%) |
| GIL | 40.98 | 82.00 | 82.00 / 111.00 | 100% | 8 | SB 5 / B 6 / H 2 / S 0 (buy) | mid ($55.6M) | 10% | B -> A (v2 99%) |
| LENZ | 3.92 | 24.00 | 10.00 / 60.00 | 513% | 7 | SB 0 / B 5 / H 2 / S 0 (none) | small ($3.7M) | 16% | same band (v2 550%) |
| UPB | 5.36 | 31.14 | 25.00 / 75.00 | 481% | 7 | SB 1 / B 4 / H 2 / S 0 (none) | small ($3.2M) | 13% | same band (v2 502%) |
| ANNX | 3.64 | 15.29 | 14.00 / 27.00 | 320% | 7 | SB 2 / B 6 / H 2 / S 0 (none) | small ($14.3M) | 16% | same band (v2 301%) |
| SION | 5.23 | 21.00 | 6.00 / 63.00 | 302% | 7 | SB 0 / B 2 / H 10 / S 0 (hold) | small ($16.5M) | 115% | same band (v2 295%) |
| DBVT | 11.56 | 39.11 | 44.85 / 54.81 | 238% | 7 | SB 1 / B 5 / H 0 / S 1 (buy) | small ($3.1M) | 12% | same band (v2 241%) |
| SANA | 2.94 | 8.43 | 7.00 / 12.00 | 186% | 7 | SB 2 / B 6 / H 1 / S 0 (none) | small ($9.0M) | 17% | same band (v2 187%) |
| CRVS | 11.62 | 33.14 | 32.00 / 42.00 | 185% | 7 | SB 1 / B 7 / H 0 / S 0 (none) | small ($12.5M) | 12% | same band (v2 183%) |
| NGNE | 28.31 | 80.43 | 65.00 / 166.00 | 184% | 7 | SB 0 / B 9 / H 0 / S 0 (none) | small ($7.2M) | 16% | same band (v2 159%) |
| TMC | 3.93 | 10.90 | 10.00 / 12.30 | 177% | 7 | SB 3 / B 3 / H 0 / S 0 (strong_buy) | small ($18.3M) | 18% | same band (v2 170%) |
| SERV | 4.45 | 12.14 | 10.00 / 22.00 | 173% | 7 | SB 0 / B 7 / H 1 / S 0 (none) | small ($16.7M) | 16% | same band (v2 175%) |
| BETR | 10.45 | 25.71 | 25.00 / 35.00 | 146% | 7 | SB 1 / B 5 / H 2 / S 0 (none) | small ($7.2M) | 31% | same band (v2 127%) |
| NNE | 16.99 | 37.57 | 45.00 / 50.00 | 121% | 7 | SB 1 / B 5 / H 2 / S 0 (buy) | mid ($33.3M) | 18% | same band (v2 125%) |
| LASR | 40.33 | 88.86 | 90.00 / 100.00 | 120% | 7 | SB 1 / B 7 / H 1 / S 0 (strong_buy) | mid ($56.2M) | 25% | same band (v2 118%) |
| JKS | 9.67 | 20.44 | 16.00 / 32.61 | 111% | 7 | SB 0 / B 2 / H 4 / S 1 (none) | small ($10.5M) | 12% | same band (v2 114%) |
| SOUN | 6.05 | 12.57 | 12.00 / 17.00 | 108% | 7 | SB 0 / B 6 / H 2 / S 0 (strong_buy) | large ($176.4M) | 14% | same band (v2 106%) |
| CCCC | 2.98 | 13.33 | 11.00 / 30.00 | 347% | 6 | SB 1 / B 6 / H 0 / S 0 (strong_buy) | small ($8.5M) | 13% | same band (v2 357%) |
| ZURA | 4.04 | 18.00 | 18.00 / 26.00 | 346% | 6 | SB 1 / B 6 / H 0 / S 0 (none) | small ($5.8M) | 16% | same band (v2 348%) |
| IMRX | 4.27 | 17.17 | 15.50 / 30.00 | 302% | 6 | SB 2 / B 5 / H 0 / S 0 (none) | small ($3.2M) | 12% | same band (v2 303%) |
| NB | 3.54 | 11.12 | 12.00 / 15.00 | 214% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($11.4M) | 17% | same band (v2 214%) |
| SLN | 11.18 | 33.00 | 29.50 / 75.00 | 195% | 6 | SB 1 / B 5 / H 0 / S 1 (buy) | small ($8.1M) | 19% | same band (v2 186%) |
| GLUE | 11.77 | 28.50 | 27.00 / 37.00 | 142% | 6 | SB 2 / B 6 / H 0 / S 0 (none) | small ($17.5M) | 19% | same band (v2 145%) |
| BUR | 3.64 | 8.71 | 6.39 / 22.50 | 139% | 6 | SB 0 / B 4 / H 2 / S 0 (buy) | small ($7.9M) | 10% | same band (v2 143%) |
| IPX | 19.61 | 45.50 | 52.50 / 55.00 | 132% | 6 | SB 0 / B 6 / H 0 / S 0 (none) | small ($5.8M) | 18% | same band (v2 131%) |
| TREE | 24.62 | 56.00 | 56.50 / 70.00 | 127% | 6 | SB 3 / B 3 / H 0 / S 0 (none) | small ($11.1M) | 14% | same band (v2 130%) |
| VRRM | 3.24 | 7.00 | 6.00 / 10.00 | 116% | 6 | SB 0 / B 0 / H 8 / S 0 (none) | small ($17.1M) | 14% | same band (v2 112%) |
| IMTX | 8.37 | 17.63 | 17.00 / 25.00 | 111% | 6 | SB 0 / B 8 / H 0 / S 0 (none) | small ($3.9M) | 10% | same band (v2 114%) |
| QUBT | 8.96 | 18.67 | 18.00 / 32.00 | 108% | 6 | SB 0 / B 4 / H 2 / S 0 (none) | mid ($67.5M) | 15% | same band (v2 103%) |
| ADTN | 7.13 | 14.67 | 14.50 / 21.00 | 106% | 6 | SB 1 / B 6 / H 2 / S 0 (none) | small ($15.2M) | 15% | same band (v2 110%) |
| SHAZ | 54.68 | 110.00 | 110.00 / 124.00 | 101% | 6 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | large ($118.6M) | 30% | B -> A (v2 89%) |
| UTI | 20.30 | 40.83 | 40.00 / 48.00 | 101% | 6 | SB 1 / B 5 / H 0 / S 0 (none) | mid ($37.4M) | 23% | B -> A (v2 97%) |
| DPRO | 5.35 | 10.70 | 10.59 / 13.79 | 100% | 6 | SB 2 / B 4 / H 0 / S 0 (strong_buy) | small ($3.6M) | 18% | B -> A (v2 95%) |
| ARTV | 6.99 | 35.80 | 40.00 / 41.00 | 412% | 5 | SB 1 / B 5 / H 0 / S 0 (none) | small ($3.6M) | 15% | same band (v2 388%) |
| KYTX | 6.81 | 30.40 | 32.00 / 33.00 | 346% | 5 | SB 2 / B 4 / H 0 / S 0 (strong_buy) | small ($6.5M) | 16% | same band (v2 341%) |
| KLRA | 11.21 | 42.40 | 41.00 / 57.00 | 278% | 5 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($10.5M) | 15% | same band (v2 252%) |
| ELDN | 2.65 | 9.00 | 8.00 / 12.00 | 240% | 5 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($3.4M) | 12% | same band (v2 240%) |
| CAPR | 8.36 | 27.00 | 25.00 / 54.00 | 223% | 5 | SB 1 / B 3 / H 6 / S 0 (buy) | mid ($29.4M) | 60% | same band (v2 221%) |
| TDUP | 2.25 | 7.24 | 6.50 / 10.00 | 222% | 5 | SB 0 / B 6 / H 1 / S 0 (none) | small ($7.1M) | 34% | same band (v2 223%) |
| AIOT | 2.80 | 8.40 | 7.00 / 13.00 | 200% | 5 | SB 1 / B 5 / H 1 / S 0 (strong_buy) | small ($4.5M) | 21% | same band (v2 195%) |
| AURA | 6.00 | 16.60 | 15.00 / 23.00 | 177% | 5 | SB 1 / B 5 / H 0 / S 0 (none) | small ($4.3M) | 12% | same band (v2 176%) |
| PRTA | 8.29 | 21.40 | 20.00 / 36.00 | 158% | 5 | SB 2 / B 1 / H 2 / S 1 (none) | small ($3.8M) | 9% | same band (v2 155%) |
| GRRR | 14.01 | 34.40 | 39.00 / 44.00 | 146% | 5 | SB 0 / B 3 / H 0 / S 0 (strong_buy) | small ($11.6M) | 24% | same band (v2 145%) |
| MRT | 2.15 | 5.04 | 6.00 / 7.00 | 134% | 5 | SB 0 / B 4 / H 1 / S 0 (strong_buy) |  |  | same band (v2 152%) |
| AIRJ | 4.09 | 9.55 | 9.00 / 12.00 | 133% | 5 | SB 0 / B 5 / H 1 / S 0 (strong_buy) | small ($4.7M) | 22% | same band (v2 132%) |
| VNDA | 5.05 | 11.75 | 11.00 / 20.00 | 133% | 5 | SB 0 / B 4 / H 1 / S 0 (strong_buy) | small ($4.3M) | 9% | same band (v2 135%) |
| ELVA | 6.35 | 14.60 | 14.00 / 20.00 | 130% | 5 | SB 0 / B 6 / H 0 / S 0 (none) | small ($3.6M) | 28% | same band (v2 127%) |
| LINC | 22.46 | 50.20 | 50.00 / 56.00 | 124% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | mid ($23.6M) | 18% | same band (v2 110%) |
| ASMB | 23.67 | 52.00 | 52.00 / 62.00 | 120% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($5.8M) | 14% | same band (v2 119%) |
| CBIO | 13.99 | 30.60 | 28.00 / 35.00 | 119% | 5 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | small ($4.2M) | 18% | same band (v2 118%) |
| MEC | 17.16 | 36.80 | 36.00 / 40.00 | 114% | 5 | SB 0 / B 5 / H 0 / S 0 (strong_buy) | small ($12.1M) | 12% | same band (v2 119%) |
| UUUU | 11.35 | 24.15 | 25.00 / 32.50 | 113% | 5 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | mid ($86.3M) | 15% | same band (v2 113%) |
| PCT | 5.02 | 10.60 | 10.00 / 17.00 | 111% | 5 | SB 0 / B 2 / H 3 / S 0 (none) | mid ($24.4M) | 16% | same band (v2 111%) |
| EVLV | 4.79 | 9.85 | 10.00 / 11.25 | 106% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($9.7M) | 10% | same band (v2 102%) |


## 5b. Implied upside 50-100% with n >= 5 analysts - 355 names

| Ticker | Price | Mean target | Median / high | Upside | n | Mix SB/B/H/S (key) | Band (med $vol) | σ63 move 21s | vs v2 |
|---|---|---|---|---|---|---|---|---|---|
| AVGO | 352.81 | 531.85 | 535.00 / 715.00 | 51% | 47 | SB 7 / B 40 / H 3 / S 0 (strong_buy) | mega ($7,910.8M) | 9% | same band (v2 52%) |
| ORCL | 137.10 | 237.97 | 240.00 / 400.00 | 74% | 41 | SB 8 / B 27 / H 7 / S 1 (buy) | mega ($4,428.0M) | 12% | same band (v2 71%) |
| BABA | 109.74 | 185.44 | 187.90 / 238.42 | 69% | 39 | SB 8 / B 30 / H 1 / S 1 (strong_buy) | mega ($1,108.7M) | 10% | same band (v2 66%) |
| CRWV | 87.59 | 141.08 | 145.00 / 317.00 | 61% | 38 | SB 8 / B 22 / H 8 / S 3 (buy) | mega ($1,959.2M) | 24% | same band (v2 61%) |
| DKNG | 22.02 | 35.12 | 33.00 / 76.00 | 59% | 36 | SB 5 / B 25 / H 6 / S 1 (buy) | large ($250.5M) | 11% | same band (v2 65%) |
| PINS | 18.90 | 29.05 | 29.00 / 42.36 | 54% | 35 | SB 2 / B 17 / H 19 / S 0 (buy) | large ($235.6M) | 11% | same band (v2 57%) |
| FLUT | 83.23 | 136.12 | 121.90 / 360.00 | 64% | 32 | SB 4 / B 18 / H 10 / S 1 (buy) | large ($243.1M) | 12% | same band (v2 65%) |
| BIDU | 87.33 | 145.86 | 154.19 / 206.83 | 67% | 31 | SB 6 / B 20 / H 5 / S 1 (buy) | large ($226.6M) | 11% | same band (v2 67%) |
| APP | 310.75 | 498.37 | 475.00 / 790.00 | 60% | 31 | SB 7 / B 20 / H 6 / S 0 (buy) | mega ($2,108.7M) | 16% | same band (v2 57%) |
| FSLR | 177.71 | 272.10 | 270.00 / 402.00 | 53% | 31 | SB 10 / B 16 / H 8 / S 2 (buy) | large ($410.7M) | 12% | same band (v2 54%) |
| BILI | 14.89 | 26.74 | 26.55 / 36.09 | 80% | 30 | SB 6 / B 23 / H 1 / S 0 (strong_buy) | mid ($40.5M) | 9% | same band (v2 80%) |
| NBIX | 138.40 | 208.40 | 214.00 / 253.00 | 51% | 29 | SB 4 / B 20 / H 4 / S 0 (strong_buy) | large ($181.3M) | 8% | same band (v2 50%) |
| NXT | 80.85 | 139.18 | 146.00 / 175.00 | 72% | 28 | SB 7 / B 19 / H 3 / S 0 (strong_buy) | large ($212.8M) | 14% | same band (v2 74%) |
| SE | 99.55 | 156.65 | 154.00 / 195.00 | 57% | 28 | SB 6 / B 22 / H 1 / S 0 (strong_buy) | large ($474.8M) | 11% | same band (v2 54%) |
| TME | 8.39 | 13.19 | 11.68 / 26.76 | 57% | 28 | SB 2 / B 16 / H 11 / S 0 (buy) | mid ($59.6M) | 9% | same band (v2 59%) |
| ENPH | 32.40 | 51.71 | 44.00 / 212.00 | 60% | 27 | SB 3 / B 10 / H 15 / S 2 (buy) | large ($155.1M) | 13% | same band (v2 57%) |
| WING | 99.07 | 197.88 | 200.00 / 265.00 | 100% | 26 | SB 4 / B 19 / H 5 / S 0 (strong_buy) | large ($150.8M) | 14% | A -> B (v2 102%) |
| XPEV | 10.12 | 19.09 | 18.65 / 25.25 | 89% | 26 | SB 7 / B 14 / H 3 / S 2 (buy) | mid ($76.4M) | 10% | same band (v2 85%) |
| CCL | 22.25 | 33.99 | 33.50 / 43.00 | 53% | 26 | SB 5 / B 18 / H 6 / S 0 (buy) | large ($467.5M) | 8% | same band (v2 56%) |
| BMRN | 60.26 | 91.62 | 90.00 / 124.00 | 52% | 26 | SB 6 / B 14 / H 7 / S 0 (buy) | large ($105.3M) | 7% | NEW |
| BROS | 37.89 | 75.48 | 79.00 / 95.00 | 99% | 25 | SB 4 / B 21 / H 0 / S 1 (strong_buy) | large ($192.4M) | 13% | same band (v2 95%) |
| AS | 27.77 | 47.65 | 48.20 / 67.00 | 72% | 25 | SB 6 / B 19 / H 1 / S 0 (strong_buy) | large ($166.4M) | 9% | same band (v2 77%) |
| GRAB | 3.13 | 5.76 | 5.80 / 8.00 | 84% | 24 | SB 5 / B 20 / H 0 / S 0 (strong_buy) | large ($149.1M) | 10% | same band (v2 84%) |
| NIO | 3.58 | 6.30 | 6.02 / 10.11 | 76% | 24 | SB 5 / B 12 / H 6 / S 1 (buy) | large ($114.1M) | 8% | same band (v2 74%) |
| CAVA | 51.58 | 82.75 | 85.00 / 110.00 | 60% | 24 | SB 3 / B 15 / H 9 / S 1 (buy) | large ($202.2M) | 13% | same band (v2 56%) |
| CRH | 85.04 | 133.18 | 135.00 / 165.00 | 57% | 24 | SB 5 / B 17 / H 1 / S 0 (strong_buy) | large ($414.8M) | 7% | same band (v2 59%) |
| INSM | 117.83 | 199.04 | 195.00 / 243.00 | 69% | 23 | SB 5 / B 19 / H 0 / S 0 (strong_buy) | large ($246.3M) | 16% | same band (v2 66%) |
| IONS | 44.50 | 83.64 | 85.00 / 105.00 | 88% | 22 | SB 9 / B 9 / H 5 / S 0 (buy) | large ($164.1M) | 16% | same band (v2 91%) |
| CIFR | 17.73 | 30.93 | 28.00 / 69.00 | 74% | 22 | SB 5 / B 15 / H 2 / S 0 (strong_buy) | large ($577.2M) | 29% | same band (v2 68%) |
| HUT | 96.82 | 157.09 | 146.50 / 273.00 | 62% | 22 | SB 6 / B 15 / H 1 / S 0 (strong_buy) | large ($417.8M) | 24% | same band (v2 55%) |
| ZG | 29.30 | 47.23 | 47.00 / 80.00 | 61% | 22 | SB 5 / B 7 / H 13 / S 0 (buy) | mid ($34.0M) | 12% | same band (v2 63%) |
| CHWY | 18.27 | 28.82 | 29.00 / 36.00 | 58% | 22 | SB 7 / B 11 / H 8 / S 0 (none) | large ($174.2M) | 11% | same band (v2 55%) |
| GFS | 49.00 | 76.00 | 73.50 / 140.00 | 55% | 22 | SB 4 / B 10 / H 7 / S 1 (buy) | large ($203.7M) | 14% | same band (v2 63%) |
| BZ | 14.11 | 21.72 | 21.79 / 27.08 | 54% | 22 | SB 5 / B 16 / H 2 / S 0 (strong_buy) | mid ($65.6M) | 12% | same band (v2 52%) |
| DECK | 78.67 | 120.41 | 118.50 / 184.00 | 53% | 22 | SB 5 / B 8 / H 11 / S 3 (none) | large ($227.7M) | 9% | same band (v2 53%) |
| CORZ | 17.34 | 33.90 | 35.00 / 55.00 | 96% | 21 | SB 3 / B 17 / H 2 / S 0 (strong_buy) | large ($207.0M) | 20% | same band (v2 90%) |
| GENI | 6.44 | 10.88 | 10.50 / 20.00 | 69% | 21 | SB 3 / B 15 / H 3 / S 0 (strong_buy) | mid ($36.0M) | 17% | same band (v2 92%) |
| BBIO | 65.57 | 109.10 | 110.00 / 157.00 | 66% | 21 | SB 5 / B 14 / H 3 / S 0 (strong_buy) | large ($181.5M) | 10% | same band (v2 65%) |
| KLAR | 12.80 | 19.97 | 18.00 / 38.30 | 56% | 21 | SB 1 / B 9 / H 14 / S 0 (none) | mid ($71.1M) | 15% | same band (v2 58%) |
| CELH | 27.99 | 42.29 | 41.00 / 64.00 | 51% | 21 | SB 6 / B 12 / H 6 / S 0 (buy) | large ($239.4M) | 17% | NEW |
| MTZ | 212.85 | 413.80 | 409.50 / 518.00 | 94% | 20 | SB 3 / B 17 / H 1 / S 0 (strong_buy) | large ($355.1M) | 17% | same band (v2 92%) |
| TNDM | 15.72 | 28.55 | 26.50 / 50.00 | 82% | 20 | SB 3 / B 11 / H 10 / S 0 (buy) | mid ($32.5M) | 15% | same band (v2 84%) |
| CYTK | 64.66 | 109.90 | 107.50 / 146.00 | 70% | 20 | SB 7 / B 13 / H 2 / S 0 (strong_buy) | large ($130.2M) | 8% | same band (v2 67%) |
| KVYO | 15.80 | 26.65 | 26.50 / 36.00 | 69% | 20 | SB 4 / B 16 / H 2 / S 0 (none) | mid ($91.7M) | 17% | same band (v2 62%) |
| WYNN | 81.12 | 132.00 | 133.00 / 144.00 | 63% | 20 | SB 4 / B 17 / H 0 / S 0 (strong_buy) | large ($142.7M) | 6% | same band (v2 65%) |
| ALB | 109.73 | 171.56 | 172.50 / 225.00 | 56% | 20 | SB 3 / B 10 / H 9 / S 0 (buy) | large ($269.6M) | 10% | same band (v2 57%) |
| BRZE | 24.37 | 37.30 | 36.00 / 50.00 | 53% | 20 | SB 6 / B 15 / H 0 / S 0 (none) | mid ($55.5M) | 18% | NEW |
| YUMC | 40.47 | 61.91 | 61.00 / 77.00 | 53% | 20 | SB 6 / B 14 / H 1 / S 0 (strong_buy) | mid ($63.7M) | 6% | same band (v2 51%) |
| BIRK | 33.60 | 50.94 | 50.30 / 69.51 | 52% | 20 | SB 5 / B 13 / H 5 / S 0 (buy) | mid ($69.3M) | 11% | same band (v2 61%) |
| RUN | 8.11 | 15.87 | 15.00 / 30.00 | 96% | 19 | SB 3 / B 9 / H 9 / S 0 (buy) | mid ($82.9M) | 14% | A -> B (v2 101%) |
| RARE | 14.50 | 28.05 | 28.00 / 40.00 | 93% | 19 | SB 2 / B 9 / H 9 / S 0 (buy) | mid ($55.3M) | 29% | same band (v2 90%) |
| HSAI | 16.25 | 28.35 | 28.77 / 36.21 | 74% | 19 | SB 5 / B 15 / H 0 / S 0 (strong_buy) | mid ($23.4M) | 15% | same band (v2 74%) |
| FICO | 863.09 | 1,434.89 | 1,525.00 / 1,750.00 | 66% | 19 | SB 5 / B 9 / H 6 / S 1 (buy) | large ($316.7M) | 16% | same band (v2 65%) |
| AXON | 430.11 | 704.11 | 700.00 / 830.00 | 64% | 19 | SB 8 / B 10 / H 3 / S 0 (buy) | large ($448.8M) | 17% | same band (v2 60%) |
| CHTR | 112.91 | 178.05 | 150.00 / 380.00 | 58% | 19 | SB 0 / B 5 / H 11 / S 6 (hold) | large ($331.5M) | 13% | same band (v2 53%) |
| VST | 138.46 | 217.58 | 221.00 / 305.00 | 57% | 19 | SB 4 / B 15 / H 0 / S 1 (strong_buy) | large ($616.5M) | 9% | same band (v2 57%) |
| PENN | 15.65 | 24.39 | 25.00 / 30.00 | 56% | 19 | SB 3 / B 9 / H 8 / S 0 (buy) | mid ($52.4M) | 8% | same band (v2 59%) |
| ACAD | 20.68 | 32.16 | 33.00 / 49.00 | 56% | 19 | SB 4 / B 11 / H 4 / S 1 (buy) | mid ($39.4M) | 10% | NEW |
| LVS | 38.99 | 59.07 | 60.00 / 71.50 | 51% | 19 | SB 3 / B 11 / H 7 / S 0 (buy) | large ($202.3M) | 6% | same band (v2 52%) |
| SHLS | 7.47 | 11.32 | 12.00 / 15.00 | 51% | 19 | SB 4 / B 8 / H 6 / S 1 (none) | mid ($38.4M) | 19% | same band (v2 52%) |
| MGM | 32.58 | 49.33 | 48.30 / 57.00 | 51% | 19 | SB 2 / B 8 / H 11 / S 2 (buy) | mid ($96.4M) | 7% | NEW |
| IREN | 44.12 | 77.97 | 80.00 / 131.00 | 77% | 18 | SB 2 / B 13 / H 5 / S 0 (buy) | mega ($1,620.3M) | 25% | same band (v2 69%) |
| CPNG | 13.88 | 23.51 | 24.00 / 30.00 | 69% | 18 | SB 4 / B 10 / H 3 / S 1 (buy) | large ($264.5M) | 9% | same band (v2 66%) |
| CRSP | 54.23 | 87.56 | 80.00 / 291.00 | 61% | 18 | SB 5 / B 8 / H 9 / S 0 (buy) | mid ($77.4M) | 13% | same band (v2 59%) |
| ATAT | 32.23 | 49.80 | 47.20 / 60.18 | 55% | 18 | SB 4 / B 16 / H 0 / S 0 (strong_buy) | mid ($27.6M) | 9% | same band (v2 54%) |
| DFTX | 36.17 | 71.65 | 70.00 / 91.00 | 98% | 17 | SB 4 / B 14 / H 0 / S 0 (strong_buy) | mid ($78.9M) | 13% | same band (v2 95%) |
| LGN | 52.52 | 102.53 | 103.00 / 130.00 | 95% | 17 | SB 2 / B 14 / H 1 / S 0 (strong_buy) | mid ($60.8M) | 17% | same band (v2 94%) |
| LEU | 147.07 | 247.40 | 218.00 / 340.00 | 68% | 17 | SB 2 / B 10 / H 7 / S 0 (buy) | large ($111.4M) | 18% | same band (v2 66%) |
| PRVA | 19.71 | 31.47 | 31.00 / 40.00 | 60% | 17 | SB 5 / B 12 / H 1 / S 0 (strong_buy) | mid ($25.1M) | 7% | same band (v2 66%) |
| PLNT | 42.68 | 67.54 | 64.00 / 106.00 | 58% | 17 | SB 3 / B 9 / H 6 / S 0 (buy) | mid ($90.5M) | 10% | same band (v2 66%) |
| STNE | 9.30 | 14.41 | 13.92 / 23.32 | 55% | 17 | SB 2 / B 7 / H 7 / S 1 (buy) | mid ($40.0M) | 9% | same band (v2 56%) |
| MP | 48.83 | 74.29 | 75.00 / 100.00 | 52% | 17 | SB 5 / B 13 / H 1 / S 0 (strong_buy) | large ($270.1M) | 15% | same band (v2 50%) |
| GXO | 45.20 | 68.71 | 65.00 / 90.00 | 52% | 17 | SB 4 / B 12 / H 1 / S 0 (none) | mid ($61.8M) | 9% | same band (v2 56%) |
| TLN | 304.42 | 460.59 | 470.00 / 560.00 | 51% | 17 | SB 6 / B 9 / H 2 / S 0 (buy) | large ($248.9M) | 12% | same band (v2 52%) |
| QBTS | 17.41 | 34.65 | 36.00 / 43.00 | 99% | 16 | SB 1 / B 14 / H 2 / S 0 (strong_buy) | large ($294.9M) | 20% | A -> B (v2 101%) |
| NRG | 100.37 | 188.56 | 187.00 / 270.00 | 88% | 16 | SB 3 / B 10 / H 3 / S 0 (buy) | large ($312.7M) | 13% | same band (v2 90%) |
| CMPS | 13.06 | 23.75 | 21.00 / 65.00 | 82% | 16 | SB 3 / B 12 / H 1 / S 0 (strong_buy) | mid ($34.6M) | 16% | same band (v2 80%) |
| VRDN | 20.47 | 36.75 | 36.50 / 50.00 | 80% | 16 | SB 3 / B 14 / H 0 / S 0 (strong_buy) | mid ($35.1M) | 11% | same band (v2 80%) |
| DNLI | 20.39 | 36.06 | 35.00 / 42.00 | 77% | 16 | SB 2 / B 17 / H 1 / S 0 (strong_buy) | mid ($33.3M) | 11% | same band (v2 80%) |
| MNSO | 8.78 | 14.88 | 14.55 / 21.20 | 69% | 16 | SB 2 / B 11 / H 4 / S 0 (none) | small ($7.2M) | 11% | same band (v2 66%) |
| UPST | 23.81 | 40.00 | 39.50 / 61.00 | 68% | 16 | SB 1 / B 6 / H 7 / S 1 (buy) | large ($110.3M) | 11% | same band (v2 63%) |
| GLXY | 24.24 | 40.62 | 41.50 / 57.00 | 68% | 16 | SB 5 / B 9 / H 2 / S 0 (none) | large ($127.7M) | 21% | same band (v2 60%) |
| BWXT | 138.47 | 222.07 | 230.00 / 290.00 | 60% | 16 | SB 3 / B 11 / H 4 / S 0 (buy) | large ($153.4M) | 9% | same band (v2 58%) |
| PCG | 12.34 | 19.22 | 19.50 / 24.00 | 56% | 16 | SB 2 / B 6 / H 9 / S 0 (buy) | large ($412.4M) | 13% | same band (v2 56%) |
| GDS | 32.77 | 50.60 | 50.34 / 63.01 | 54% | 16 | SB 3 / B 13 / H 1 / S 0 (strong_buy) | mid ($50.2M) | 11% | same band (v2 52%) |
| VVV | 28.92 | 43.69 | 45.00 / 49.00 | 51% | 16 | SB 1 / B 10 / H 4 / S 0 (buy) | mid ($69.7M) | 8% | same band (v2 54%) |
| ETOR | 26.39 | 47.73 | 46.00 / 90.00 | 81% | 15 | SB 2 / B 8 / H 5 / S 0 (buy) | mid ($29.4M) | 11% | same band (v2 79%) |
| TTAN | 58.05 | 97.53 | 100.00 / 110.00 | 68% | 15 | SB 3 / B 12 / H 2 / S 0 (strong_buy) | large ($108.0M) | 22% | same band (v2 63%) |
| PVLA | 138.16 | 230.53 | 232.00 / 270.00 | 67% | 15 | SB 0 / B 15 / H 0 / S 0 (strong_buy) | mid ($28.5M) | 18% | same band (v2 57%) |
| TRIP | 8.41 | 13.87 | 13.00 / 21.00 | 65% | 15 | SB 1 / B 4 / H 8 / S 4 (hold) | mid ($37.0M) | 17% | same band (v2 69%) |
| BHVN | 12.99 | 21.27 | 20.00 / 42.00 | 64% | 15 | SB 3 / B 9 / H 4 / S 1 (buy) | mid ($33.1M) | 18% | same band (v2 61%) |
| PRIM | 72.65 | 117.80 | 115.00 / 165.00 | 62% | 15 | SB 3 / B 8 / H 5 / S 0 (none) | mid ($96.9M) | 13% | same band (v2 59%) |
| PTON | 4.92 | 7.90 | 7.00 / 20.00 | 61% | 15 | SB 0 / B 8 / H 10 / S 2 (buy) | mid ($44.0M) | 12% | same band (v2 66%) |
| DNTH | 88.55 | 140.80 | 134.00 / 200.00 | 59% | 15 | SB 1 / B 15 / H 0 / S 0 (strong_buy) | mid ($80.5M) | 12% | same band (v2 54%) |
| NAVN | 19.41 | 30.87 | 30.00 / 38.00 | 59% | 15 | SB 4 / B 11 / H 0 / S 0 (strong_buy) | mid ($81.1M) | 18% | same band (v2 59%) |
| KGS | 52.91 | 83.13 | 83.00 / 93.00 | 57% | 15 | SB 5 / B 10 / H 0 / S 0 (strong_buy) | large ($105.7M) | 12% | same band (v2 58%) |
| YMM | 8.13 | 12.55 | 12.14 / 16.25 | 54% | 15 | SB 4 / B 9 / H 2 / S 0 (none) | mid ($51.8M) | 8% | same band (v2 52%) |
| CX | 9.71 | 14.81 | 15.00 / 20.00 | 53% | 15 | SB 7 / B 4 / H 4 / S 0 (buy) | mid ($68.1M) | 6% | same band (v2 54%) |
| BTDR | 11.51 | 21.79 | 21.50 / 35.00 | 89% | 14 | SB 3 / B 10 / H 1 / S 0 (strong_buy) | large ($124.5M) | 27% | same band (v2 79%) |
| ARVN | 7.59 | 13.93 | 13.00 / 21.00 | 84% | 14 | SB 2 / B 5 / H 8 / S 1 (buy) | small ($5.4M) | 11% | same band (v2 87%) |
| PHVS | 32.02 | 57.96 | 60.78 / 77.44 | 81% | 14 | SB 3 / B 10 / H 1 / S 0 (strong_buy) | small ($19.7M) | 10% | same band (v2 77%) |
| BOOT | 123.30 | 221.50 | 213.50 / 282.00 | 80% | 14 | SB 2 / B 13 / H 1 / S 0 (strong_buy) | mid ($95.0M) | 11% | same band (v2 75%) |
| CLSK | 13.95 | 23.89 | 24.00 / 27.00 | 71% | 14 | SB 4 / B 10 / H 0 / S 0 (strong_buy) | large ($246.4M) | 22% | same band (v2 67%) |
| IMNM | 21.41 | 36.00 | 36.00 / 40.00 | 68% | 14 | SB 3 / B 12 / H 0 / S 0 (strong_buy) | mid ($25.8M) | 13% | same band (v2 60%) |
| PTCT | 62.67 | 101.79 | 101.00 / 137.00 | 62% | 14 | SB 4 / B 8 / H 1 / S 1 (buy) | mid ($72.1M) | 9% | same band (v2 64%) |
| IRTC | 110.38 | 176.14 | 177.50 / 196.00 | 60% | 14 | SB 2 / B 13 / H 0 / S 0 (strong_buy) | mid ($60.9M) | 11% | same band (v2 59%) |
| ALGT | 79.09 | 124.93 | 115.50 / 165.00 | 58% | 14 | SB 2 / B 9 / H 3 / S 0 (buy) | mid ($45.8M) | 11% | same band (v2 68%) |
| MKSI | 260.82 | 410.86 | 405.00 / 600.00 | 58% | 14 | SB 3 / B 9 / H 1 / S 1 (buy) | large ($376.2M) | 17% | same band (v2 59%) |
| JBS | 11.57 | 18.09 | 17.97 / 20.66 | 56% | 14 | SB 5 / B 7 / H 2 / S 0 (buy) | mid ($61.7M) | 8% | same band (v2 60%) |
| ATEC | 10.12 | 15.79 | 15.00 / 24.00 | 56% | 14 | SB 3 / B 11 / H 0 / S 0 (none) | small ($17.3M) | 14% | same band (v2 59%) |
| MIRM | 89.70 | 138.21 | 137.00 / 183.00 | 54% | 14 | SB 4 / B 10 / H 0 / S 0 (strong_buy) | mid ($61.3M) | 11% | same band (v2 55%) |
| SARO | 22.74 | 34.89 | 35.00 / 42.40 | 53% | 14 | SB 2 / B 9 / H 4 / S 0 (buy) | mid ($85.9M) | 8% | same band (v2 56%) |
| SFM | 62.49 | 94.50 | 97.50 / 114.00 | 51% | 14 | SB 3 / B 6 / H 6 / S 1 (buy) | large ($143.5M) | 11% | NEW |
| CWH | 5.39 | 10.56 | 10.00 / 15.00 | 96% | 13 | SB 2 / B 9 / H 2 / S 0 (strong_buy) | small ($12.2M) | 14% | A -> B (v2 104%) |
| STOK | 24.80 | 46.46 | 44.00 / 60.00 | 87% | 13 | SB 2 / B 12 / H 0 / S 0 (none) | mid ($20.6M) | 11% | same band (v2 81%) |
| SMMT | 15.61 | 28.63 | 32.76 / 40.81 | 83% | 13 | SB 1 / B 10 / H 6 / S 0 (buy) | mid ($63.0M) | 16% | same band (v2 74%) |
| BCAX | 19.21 | 34.54 | 35.00 / 45.00 | 80% | 13 | SB 3 / B 10 / H 2 / S 0 (none) | small ($13.2M) | 14% | same band (v2 75%) |
| FUN | 12.32 | 20.69 | 22.00 / 28.00 | 68% | 13 | SB 2 / B 6 / H 5 / S 1 (buy) | mid ($31.1M) | 15% | same band (v2 66%) |
| BOBS | 13.75 | 22.92 | 22.00 / 28.00 | 67% | 13 | SB 4 / B 7 / H 2 / S 0 (none) | small ($12.9M) | 15% | same band (v2 68%) |
| ARWR | 65.92 | 107.23 | 104.00 / 126.00 | 63% | 13 | SB 4 / B 9 / H 1 / S 0 (strong_buy) | large ($131.5M) | 14% | same band (v2 66%) |
| ORIC | 13.16 | 21.08 | 22.00 / 27.00 | 60% | 13 | SB 2 / B 12 / H 1 / S 0 (strong_buy) | small ($15.6M) | 17% | same band (v2 61%) |
| ZYME | 26.52 | 41.23 | 38.00 / 60.00 | 55% | 13 | SB 2 / B 11 / H 0 / S 0 (strong_buy) | small ($14.4M) | 11% | same band (v2 54%) |
| LBRT | 18.94 | 29.42 | 29.00 / 36.00 | 55% | 13 | SB 3 / B 5 / H 5 / S 0 (buy) | mid ($75.7M) | 17% | same band (v2 62%) |
| LBTYA | 9.45 | 14.66 | 12.00 / 25.00 | 55% | 13 | SB 0 / B 4 / H 8 / S 1 (buy) | mid ($21.8M) | 7% | same band (v2 52%) |
| RLAY | 17.47 | 27.08 | 26.00 / 32.00 | 55% | 13 | SB 3 / B 11 / H 0 / S 0 (strong_buy) | mid ($51.8M) | 11% | same band (v2 54%) |
| SLGN | 35.91 | 55.31 | 57.00 / 61.00 | 54% | 13 | SB 3 / B 9 / H 1 / S 0 (none) | mid ($42.3M) | 9% | same band (v2 54%) |
| VERX | 11.37 | 17.15 | 16.00 / 25.00 | 51% | 13 | SB 3 / B 4 / H 8 / S 0 (none) | small ($19.8M) | 14% | NEW |
| AUR | 6.04 | 12.05 | 12.50 / 18.00 | 99% | 12 | SB 2 / B 6 / H 5 / S 0 (buy) | large ($167.4M) | 15% | A -> B (v2 106%) |
| QNT | 49.53 | 97.17 | 94.00 / 155.00 | 96% | 12 | SB 2 / B 10 / H 1 / S 0 (strong_buy) | mid ($83.4M) | 21% | same band (v2 97%) |
| BRBR | 7.91 | 14.71 | 14.50 / 20.00 | 86% | 12 | SB 2 / B 6 / H 5 / S 1 (buy) | mid ($39.0M) | 13% | same band (v2 81%) |
| RAPP | 33.91 | 62.88 | 59.00 / 80.00 | 85% | 12 | SB 1 / B 12 / H 0 / S 0 (strong_buy) | small ($13.9M) | 14% | same band (v2 91%) |
| ORKA | 84.46 | 155.00 | 155.50 / 200.00 | 84% | 12 | SB 2 / B 11 / H 0 / S 0 (strong_buy) | mid ($74.2M) | 13% | same band (v2 82%) |
| ACHV | 7.54 | 13.83 | 12.50 / 21.00 | 83% | 12 | SB 3 / B 8 / H 0 / S 0 (none) | small ($10.1M) | 13% | same band (v2 79%) |
| RSI | 19.87 | 35.83 | 36.00 / 40.00 | 80% | 12 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | mid ($66.3M) | 13% | same band (v2 84%) |
| ABVX | 91.06 | 164.00 | 164.00 / 181.00 | 80% | 12 | SB 4 / B 8 / H 0 / S 0 (strong_buy) | large ($124.6M) | 18% | same band (v2 74%) |
| PUMP | 9.59 | 16.62 | 17.75 / 21.00 | 73% | 12 | SB 4 / B 5 / H 4 / S 0 (buy) | mid ($38.0M) | 14% | same band (v2 72%) |
| RGTI | 16.66 | 28.52 | 30.00 / 40.00 | 71% | 12 | SB 1 / B 8 / H 4 / S 0 (buy) | large ($310.9M) | 18% | same band (v2 76%) |
| DCH | 5.46 | 9.30 | 9.00 / 17.00 | 70% | 12 | SB 2 / B 4 / H 7 / S 0 (buy) | small ($16.5M) | 13% | same band (v2 75%) |
| CSIQ | 10.80 | 17.85 | 16.07 / 30.00 | 65% | 12 | SB 1 / B 3 / H 6 / S 2 (hold) | mid ($28.0M) | 15% | same band (v2 66%) |
| COMP | 9.38 | 15.42 | 15.50 / 18.00 | 64% | 12 | SB 3 / B 6 / H 3 / S 0 (buy) | large ($131.4M) | 13% | same band (v2 65%) |
| CHDN | 79.77 | 130.83 | 128.00 / 157.00 | 64% | 12 | SB 3 / B 9 / H 0 / S 0 (strong_buy) | mid ($79.1M) | 8% | same band (v2 65%) |
| WHR | 31.71 | 50.67 | 42.50 / 137.00 | 60% | 12 | SB 0 / B 1 / H 9 / S 3 (hold) | mid ($85.0M) | 12% | same band (v2 55%) |
| EVH | 3.61 | 5.75 | 6.00 / 8.00 | 59% | 12 | SB 4 / B 7 / H 3 / S 0 (buy) | small ($11.4M) | 19% | same band (v2 62%) |
| IRON | 65.24 | 103.17 | 100.00 / 128.00 | 58% | 12 | SB 1 / B 12 / H 0 / S 0 (strong_buy) | mid ($29.7M) | 8% | same band (v2 58%) |
| SPXC | 172.79 | 270.67 | 280.00 / 310.00 | 57% | 12 | SB 1 / B 10 / H 1 / S 0 (strong_buy) | mid ($86.6M) | 10% | same band (v2 56%) |
| RCUS | 24.97 | 38.75 | 42.50 / 47.00 | 55% | 12 | SB 0 / B 11 / H 3 / S 0 (strong_buy) | mid ($33.8M) | 11% | same band (v2 54%) |
| AMTM | 19.19 | 29.58 | 28.00 / 40.00 | 54% | 12 | SB 2 / B 3 / H 6 / S 1 (buy) | mid ($37.3M) | 10% | same band (v2 50%) |
| AEIS | 279.68 | 429.08 | 412.50 / 535.00 | 53% | 12 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | large ($161.8M) | 18% | same band (v2 56%) |
| GSHD | 45.23 | 68.92 | 72.00 / 100.00 | 52% | 12 | SB 3 / B 3 / H 6 / S 1 (none) | mid ($24.5M) | 17% | same band (v2 55%) |
| CCOI | 7.69 | 15.27 | 12.00 / 30.00 | 99% | 11 | SB 0 / B 4 / H 6 / S 2 (buy) | small ($15.7M) | 20% | same band (v2 94%) |
| ACRS | 5.15 | 10.18 | 10.00 / 16.00 | 98% | 11 | SB 1 / B 10 / H 1 / S 0 (strong_buy) | small ($9.6M) | 13% | same band (v2 94%) |
| TRVI | 14.41 | 28.18 | 25.00 / 40.00 | 96% | 11 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | mid ($28.5M) | 14% | same band (v2 96%) |
| FDMT | 14.47 | 27.82 | 28.00 / 37.00 | 92% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | small ($9.7M) | 16% | same band (v2 100%) |
| DY | 271.52 | 520.91 | 525.00 / 625.00 | 92% | 11 | SB 1 / B 10 / H 0 / S 0 (strong_buy) | large ($174.1M) | 14% | same band (v2 87%) |
| TNGX | 24.92 | 45.18 | 40.00 / 69.00 | 81% | 11 | SB 1 / B 10 / H 1 / S 0 (strong_buy) | mid ($57.1M) | 15% | same band (v2 88%) |
| QURE | 38.23 | 68.42 | 68.84 / 93.13 | 79% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | mid ($50.1M) | 12% | same band (v2 76%) |
| ALM | 13.72 | 24.34 | 25.01 / 32.52 | 77% | 11 | SB 0 / B 10 / H 1 / S 0 (strong_buy) | mid ($89.4M) | 22% | A -> B (v2 102%) |
| MWH | 25.20 | 44.55 | 43.00 / 55.00 | 77% | 11 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | mid ($44.9M) | 15% | same band (v2 77%) |
| ESAB | 71.91 | 126.91 | 128.00 / 145.00 | 76% | 11 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | mid ($56.8M) | 11% | same band (v2 88%) |
| COGT | 32.31 | 55.82 | 55.00 / 62.00 | 73% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | mid ($64.7M) | 10% | same band (v2 80%) |
| EYE | 16.53 | 28.18 | 27.00 / 35.00 | 70% | 11 | SB 1 / B 8 / H 3 / S 0 (buy) | mid ($36.7M) | 10% | same band (v2 71%) |
| KEEL | 3.80 | 6.45 | 6.00 / 10.00 | 70% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | large ($124.0M) | 26% | same band (v2 65%) |
| ADNT | 17.63 | 29.55 | 26.00 / 64.00 | 68% | 11 | SB 2 / B 6 / H 3 / S 1 (buy) | small ($16.8M) | 12% | same band (v2 72%) |
| TIGR | 4.64 | 7.71 | 7.30 / 14.50 | 66% | 11 | SB 2 / B 8 / H 0 / S 1 (none) | small ($9.2M) | 10% | same band (v2 65%) |
| PGY | 17.62 | 28.91 | 27.00 / 36.00 | 64% | 11 | SB 2 / B 9 / H 0 / S 0 (strong_buy) | mid ($48.9M) | 16% | same band (v2 56%) |
| PATK | 68.49 | 108.00 | 114.00 / 130.00 | 58% | 11 | SB 2 / B 6 / H 2 / S 1 (buy) | mid ($43.3M) | 8% | same band (v2 59%) |
| WOOF | 2.27 | 3.56 | 3.50 / 5.00 | 57% | 11 | SB 1 / B 1 / H 8 / S 2 (none) | small ($4.3M) | 10% | same band (v2 54%) |
| RBA | 82.49 | 128.64 | 130.00 / 152.00 | 56% | 11 | SB 5 / B 6 / H 1 / S 0 (buy) | large ($132.8M) | 10% | same band (v2 56%) |
| BKV | 21.81 | 34.00 | 35.00 / 39.00 | 56% | 11 | SB 1 / B 10 / H 0 / S 0 (strong_buy) | mid ($22.2M) | 11% | NEW |
| PRMB | 19.50 | 30.36 | 31.00 / 35.00 | 56% | 11 | SB 5 / B 5 / H 2 / S 0 (buy) | mid ($80.1M) | 9% | same band (v2 54%) |
| MIR | 15.59 | 24.27 | 24.00 / 29.00 | 56% | 11 | SB 2 / B 8 / H 1 / S 0 (strong_buy) | mid ($54.6M) | 12% | NEW |
| PAM | 77.82 | 121.09 | 118.00 / 160.00 | 56% | 11 | SB 2 / B 7 / H 2 / S 0 (buy) | small ($13.2M) | 6% | same band (v2 52%) |
| WY | 20.01 | 31.00 | 30.00 / 38.00 | 55% | 11 | SB 2 / B 7 / H 3 / S 0 (none) | large ($121.6M) | 7% | same band (v2 51%) |
| SVV | 9.34 | 14.23 | 14.00 / 20.00 | 52% | 11 | SB 0 / B 8 / H 4 / S 0 (buy) | small ($10.3M) | 12% | same band (v2 56%) |
| SAH | 64.95 | 98.55 | 98.00 / 139.00 | 52% | 11 | SB 2 / B 4 / H 4 / S 2 (buy) | mid ($21.4M) | 13% | same band (v2 60%) |
| INIO | 19.12 | 38.20 | 40.00 / 47.00 | 100% | 10 | SB 4 / B 4 / H 2 / S 0 (buy) | large ($105.2M) | 20% | same band (v2 98%) |
| AMRC | 21.48 | 42.70 | 39.00 / 62.00 | 99% | 10 | SB 1 / B 7 / H 4 / S 0 (buy) | small ($13.6M) | 19% | same band (v2 97%) |
| FWRG | 10.14 | 19.50 | 20.00 / 22.00 | 92% | 10 | SB 0 / B 10 / H 0 / S 0 (strong_buy) | small ($11.8M) | 10% | same band (v2 88%) |
| PL | 17.43 | 33.40 | 35.00 / 50.00 | 92% | 10 | SB 1 / B 6 / H 4 / S 0 (buy) | large ($142.7M) | 15% | same band (v2 91%) |
| EQPT | 17.35 | 33.20 | 35.00 / 55.00 | 91% | 10 | SB 1 / B 6 / H 4 / S 0 (buy) | mid ($49.6M) | 18% | same band (v2 90%) |
| BLDP | 2.13 | 4.02 | 3.55 / 6.50 | 89% | 10 | SB 0 / B 3 / H 8 / S 1 (hold) | small ($9.2M) | 13% | same band (v2 91%) |
| UEC | 9.41 | 17.38 | 16.50 / 26.75 | 85% | 10 | SB 2 / B 6 / H 2 / S 0 (none) | mid ($77.5M) | 14% | same band (v2 84%) |
| GGAL | 38.74 | 67.37 | 60.00 / 103.00 | 74% | 10 | SB 3 / B 3 / H 4 / S 0 (none) | mid ($35.7M) | 10% | same band (v2 70%) |
| NEXN | 8.70 | 14.64 | 13.00 / 25.40 | 68% | 10 | SB 5 / B 4 / H 0 / S 0 (none) | small ($4.3M) | 9% | same band (v2 71%) |
| INTR | 5.11 | 8.57 | 8.79 / 11.60 | 68% | 10 | SB 2 / B 5 / H 2 / S 1 (buy) | mid ($22.9M) | 10% | same band (v2 69%) |
| CSQR | 17.01 | 28.50 | 26.50 / 46.00 | 68% | 10 | SB 3 / B 6 / H 1 / S 0 (none) | mid ($20.7M) | 11% | same band (v2 58%) |
| ARCT | 13.85 | 23.20 | 20.00 / 41.00 | 68% | 10 | SB 1 / B 10 / H 2 / S 0 (strong_buy) | small ($6.1M) | 22% | same band (v2 59%) |
| STRZ | 21.07 | 35.20 | 36.00 / 45.00 | 67% | 10 | SB 2 / B 4 / H 4 / S 0 (buy) | small ($4.7M) | 15% | same band (v2 53%) |
| ELVN | 44.75 | 73.90 | 74.00 / 82.00 | 65% | 10 | SB 1 / B 11 / H 0 / S 0 (none) | mid ($46.7M) | 9% | same band (v2 62%) |
| WSC | 18.17 | 29.90 | 29.00 / 37.00 | 65% | 10 | SB 0 / B 3 / H 7 / S 0 (buy) | mid ($51.7M) | 9% | same band (v2 65%) |
| MNTN | 11.01 | 18.10 | 18.00 / 22.00 | 64% | 10 | SB 3 / B 6 / H 1 / S 0 (none) | small ($9.2M) | 14% | same band (v2 66%) |
| MBX | 53.63 | 88.10 | 88.00 / 121.00 | 64% | 10 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | mid ($35.3M) | 14% | same band (v2 61%) |
| MMYT | 46.75 | 75.40 | 75.00 / 85.00 | 61% | 10 | SB 0 / B 10 / H 0 / S 0 (strong_buy) | mid ($39.6M) | 12% | same band (v2 61%) |
| RRX | 156.18 | 248.20 | 242.50 / 275.00 | 59% | 10 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | large ($200.6M) | 13% | same band (v2 65%) |
| FLY | 24.36 | 38.60 | 36.00 / 50.00 | 58% | 10 | SB 1 / B 6 / H 3 / S 0 (buy) | mid ($62.7M) | 18% | same band (v2 70%) |
| AVBP | 28.45 | 44.70 | 45.00 / 50.00 | 57% | 10 | SB 0 / B 11 / H 0 / S 0 (strong_buy) | small ($13.8M) | 12% | same band (v2 51%) |
| HGV | 35.77 | 55.90 | 52.50 / 74.00 | 56% | 10 | SB 1 / B 3 / H 6 / S 0 (buy) | mid ($45.7M) | 10% | same band (v2 56%) |
| YSS | 9.57 | 14.85 | 14.50 / 18.00 | 55% | 10 | SB 1 / B 4 / H 7 / S 0 (buy) | mid ($27.1M) | 22% | NEW |
| VTEX | 3.61 | 5.57 | 4.75 / 12.00 | 54% | 10 | SB 1 / B 3 / H 6 / S 0 (none) | small ($3.0M) | 9% | same band (v2 55%) |
| LCII | 84.51 | 127.70 | 122.50 / 175.00 | 51% | 10 | SB 1 / B 4 / H 6 / S 0 (none) | mid ($30.5M) | 8% | same band (v2 51%) |
| AQST | 4.68 | 9.33 | 10.00 / 11.00 | 99% | 9 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($9.8M) | 11% | same band (v2 97%) |
| HROW | 33.07 | 65.00 | 60.00 / 88.00 | 97% | 9 | SB 0 / B 9 / H 0 / S 0 (strong_buy) | small ($18.9M) | 10% | same band (v2 97%) |
| LCID | 4.07 | 7.94 | 7.00 / 17.00 | 95% | 9 | SB 0 / B 1 / H 7 / S 3 (hold) | mid ($53.7M) | 25% | same band (v2 91%) |
| VIR | 10.66 | 20.78 | 20.00 / 30.00 | 95% | 9 | SB 3 / B 7 / H 0 / S 0 (none) | small ($16.7M) | 11% | same band (v2 98%) |
| PCVX | 56.21 | 109.00 | 110.00 / 163.00 | 94% | 9 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | mid ($61.8M) | 9% | same band (v2 92%) |
| VSTM | 7.74 | 14.67 | 14.00 / 18.00 | 89% | 9 | SB 1 / B 9 / H 0 / S 0 (strong_buy) | small ($13.6M) | 14% | same band (v2 87%) |
| ACHR | 5.61 | 10.61 | 11.00 / 18.00 | 89% | 9 | SB 2 / B 4 / H 3 / S 0 (none) | large ($146.1M) | 18% | same band (v2 88%) |
| AKTS | 19.43 | 35.39 | 35.00 / 40.00 | 82% | 9 | SB 1 / B 9 / H 0 / S 0 (none) | small ($6.8M) | 15% | same band (v2 78%) |
| GHRS | 23.84 | 42.89 | 40.00 / 65.00 | 80% | 9 | SB 2 / B 7 / H 0 / S 0 (none) | small ($4.9M) | 11% | same band (v2 77%) |
| PTLO | 3.50 | 6.25 | 5.50 / 11.00 | 79% | 9 | SB 0 / B 3 / H 9 / S 0 (buy) | small ($5.1M) | 11% | same band (v2 71%) |
| FN | 417.39 | 734.11 | 750.00 / 850.00 | 76% | 9 | SB 3 / B 4 / H 2 / S 0 (buy) | large ($347.2M) | 19% | same band (v2 83%) |
| AERO | 15.82 | 26.82 | 27.00 / 30.00 | 70% | 9 | SB 4 / B 4 / H 1 / S 0 (buy) | small ($4.0M) | 10% | same band (v2 73%) |
| ERAS | 14.25 | 24.11 | 22.00 / 33.00 | 69% | 9 | SB 2 / B 5 / H 2 / S 0 (none) | mid ($67.8M) | 15% | same band (v2 73%) |
| JOBY | 6.32 | 10.68 | 11.50 / 18.00 | 69% | 9 | SB 1 / B 2 / H 5 / S 3 (hold) | large ($215.6M) | 14% | same band (v2 72%) |
| ITG | 10.48 | 17.56 | 17.00 / 20.00 | 68% | 9 | SB 1 / B 8 / H 0 / S 0 (none) | small ($3.0M) | 20% | same band (v2 68%) |
| MAIR | 25.16 | 41.89 | 41.00 / 49.00 | 66% | 9 | SB 1 / B 8 / H 2 / S 0 (none) | mid ($58.4M) | 13% | same band (v2 70%) |
| OI | 5.86 | 9.59 | 9.00 / 13.00 | 64% | 9 | SB 0 / B 5 / H 3 / S 1 (buy) | mid ($20.3M) | 15% | same band (v2 63%) |
| BMA | 68.86 | 111.44 | 108.06 / 148.73 | 62% | 9 | SB 3 / B 5 / H 1 / S 0 (buy) | mid ($20.3M) | 10% | same band (v2 57%) |
| COUR | 5.05 | 8.17 | 8.00 / 10.00 | 62% | 9 | SB 3 / B 4 / H 4 / S 0 (none) | mid ($27.3M) | 13% | same band (v2 59%) |
| FLOC | 19.14 | 30.56 | 31.00 / 34.00 | 60% | 9 | SB 3 / B 5 / H 1 / S 0 (buy) | small ($9.6M) | 10% | same band (v2 58%) |
| STEP | 44.36 | 69.56 | 65.00 / 92.00 | 57% | 9 | SB 3 / B 5 / H 1 / S 0 (none) | mid ($51.8M) | 12% | same band (v2 59%) |
| ARCO | 7.24 | 11.29 | 11.50 / 14.00 | 56% | 9 | SB 4 / B 4 / H 1 / S 0 (none) | small ($8.3M) | 5% | same band (v2 55%) |
| ESTA | 65.97 | 102.44 | 105.00 / 117.00 | 55% | 9 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | mid ($31.7M) | 11% | same band (v2 54%) |
| CIGI | 90.42 | 139.22 | 145.00 / 160.00 | 54% | 9 | SB 4 / B 5 / H 4 / S 0 (buy) | mid ($22.7M) | 8% | same band (v2 52%) |
| RELY | 21.36 | 32.33 | 32.00 / 36.00 | 51% | 9 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | mid ($74.5M) | 12% | same band (v2 56%) |
| GEN | 21.62 | 32.56 | 32.00 / 46.00 | 51% | 9 | SB 0 / B 4 / H 6 / S 0 (buy) | large ($142.6M) | 11% | NEW |
| CADL | 11.02 | 21.75 | 22.50 / 29.00 | 97% | 8 | SB 0 / B 9 / H 0 / S 0 (strong_buy) | small ($12.3M) | 15% | same band (v2 98%) |
| INDI | 3.02 | 5.72 | 6.00 / 8.00 | 89% | 8 | SB 1 / B 5 / H 2 / S 0 (buy) | small ($17.9M) | 21% | same band (v2 89%) |
| LUNR | 15.61 | 29.50 | 29.00 / 43.00 | 89% | 8 | SB 0 / B 8 / H 0 / S 1 (none) | large ($130.5M) | 18% | same band (v2 87%) |
| MLYS | 25.86 | 48.50 | 52.00 / 56.00 | 88% | 8 | SB 0 / B 9 / H 1 / S 0 (none) | mid ($22.5M) | 12% | same band (v2 84%) |
| AORT | 22.63 | 42.15 | 42.00 / 48.00 | 86% | 8 | SB 2 / B 6 / H 0 / S 0 (strong_buy) | small ($15.6M) | 10% | same band (v2 79%) |
| PAR | 14.06 | 25.31 | 26.50 / 33.00 | 80% | 8 | SB 1 / B 6 / H 2 / S 0 (buy) | small ($15.0M) | 12% | same band (v2 79%) |
| EROC | 12.60 | 22.50 | 22.50 / 28.00 | 79% | 8 | SB 4 / B 4 / H 0 / S 0 (none) | mid ($22.5M) | 27% | same band (v2 86%) |
| SBET | 9.63 | 17.14 | 14.00 / 30.00 | 78% | 8 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | mid ($56.1M) | 18% | same band (v2 75%) |
| TLRY | 4.13 | 7.34 | 5.50 / 17.00 | 78% | 8 | SB 0 / B 1 / H 2 / S 0 (buy) | small ($15.7M) | 11% | same band (v2 79%) |
| FUBO | 9.64 | 17.00 | 17.00 / 23.00 | 76% | 8 | SB 3 / B 5 / H 2 / S 0 (buy) | small ($13.3M) | 17% | same band (v2 77%) |
| ZBIO | 26.95 | 47.00 | 45.00 / 59.00 | 74% | 8 | SB 0 / B 7 / H 1 / S 0 (strong_buy) | mid ($20.3M) | 13% | same band (v2 78%) |
| ANAB | 51.00 | 88.50 | 79.50 / 140.00 | 74% | 8 | SB 3 / B 5 / H 0 / S 0 (strong_buy) | mid ($24.2M) | 14% | same band (v2 73%) |
| LMRI | 10.21 | 17.62 | 17.50 / 23.00 | 73% | 8 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($4.0M) | 11% | same band (v2 75%) |
| KRUS | 38.91 | 67.00 | 65.50 / 85.00 | 72% | 8 | SB 0 / B 6 / H 3 / S 0 (buy) | small ($9.5M) | 12% | same band (v2 70%) |
| HLMN | 7.05 | 12.12 | 12.00 / 14.00 | 72% | 8 | SB 2 / B 4 / H 2 / S 0 (buy) | small ($9.5M) | 10% | same band (v2 73%) |
| GMRS | 11.06 | 18.88 | 17.50 / 30.00 | 71% | 8 | SB 2 / B 5 / H 1 / S 0 (strong_buy) | small ($7.1M) | 13% | same band (v2 75%) |
| INR | 13.06 | 22.12 | 22.50 / 26.00 | 69% | 8 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | small ($3.7M) | 10% | same band (v2 66%) |
| TROX | 4.03 | 6.75 | 6.75 / 11.00 | 67% | 8 | SB 0 / B 1 / H 4 / S 3 (hold) | small ($12.9M) | 13% | same band (v2 63%) |
| BRSL | 9.96 | 16.61 | 16.50 / 21.00 | 67% | 8 | SB 0 / B 6 / H 3 / S 0 (buy) | small ($17.6M) | 9% | same band (v2 70%) |
| CXM | 5.07 | 8.44 | 8.00 / 12.00 | 66% | 8 | SB 1 / B 2 / H 5 / S 1 (hold) | small ($17.6M) | 13% | same band (v2 58%) |
| BKSY | 23.25 | 38.42 | 36.00 / 50.00 | 65% | 8 | SB 0 / B 5 / H 1 / S 0 (strong_buy) | mid ($23.7M) | 18% | same band (v2 65%) |
| PTRN | 17.02 | 28.12 | 28.50 / 31.00 | 65% | 8 | SB 2 / B 6 / H 1 / S 0 (none) | mid ($37.2M) | 13% | same band (v2 55%) |
| HAPN | 15.03 | 24.75 | 25.00 / 29.00 | 65% | 8 | SB 4 / B 4 / H 0 / S 0 (strong_buy) | mid ($23.8M) | 9% | same band (v2 61%) |
| MNR | 10.40 | 17.00 | 17.00 / 20.00 | 63% | 8 | SB 0 / B 7 / H 2 / S 0 (strong_buy) | small ($4.1M) | 6% | same band (v2 61%) |
| SGHC | 11.97 | 19.50 | 19.50 / 22.00 | 63% | 8 | SB 2 / B 6 / H 0 / S 0 (strong_buy) | mid ($31.8M) | 9% | same band (v2 63%) |
| RXST | 4.66 | 7.57 | 6.65 / 11.00 | 62% | 8 | SB 1 / B 0 / H 7 / S 2 (hold) | small ($4.7M) | 15% | same band (v2 59%) |
| UMAC | 24.05 | 39.00 | 40.00 / 45.00 | 62% | 8 | SB 3 / B 5 / H 0 / S 0 (none) | mid ($66.9M) | 28% | same band (v2 62%) |
| CRS | 396.84 | 625.88 | 614.00 / 700.00 | 58% | 8 | SB 1 / B 6 / H 1 / S 0 (none) | large ($316.6M) | 9% | same band (v2 57%) |
| LQDA | 68.43 | 107.75 | 109.00 / 130.00 | 57% | 8 | SB 1 / B 5 / H 2 / S 0 (none) | mid ($92.3M) | 14% | same band (v2 56%) |
| KNF | 54.58 | 85.38 | 82.50 / 118.00 | 56% | 8 | SB 1 / B 4 / H 2 / S 1 (buy) | mid ($44.1M) | 11% | same band (v2 73%) |
| EXTR | 21.52 | 33.50 | 34.00 / 38.00 | 56% | 8 | SB 1 / B 6 / H 1 / S 0 (none) | mid ($38.4M) | 14% | same band (v2 54%) |
| OFRM | 16.26 | 25.25 | 22.00 / 38.00 | 55% | 8 | SB 1 / B 5 / H 3 / S 0 (none) | small ($6.5M) | 15% | same band (v2 53%) |
| BRSP | 4.09 | 6.34 | 6.50 / 7.00 | 55% | 8 | SB 2 / B 4 / H 0 / S 2 (none) | small ($6.5M) | 6% | same band (v2 58%) |
| DEC | 13.79 | 21.25 | 20.00 / 32.00 | 54% | 8 | SB 0 / B 9 / H 1 / S 0 (strong_buy) | small ($10.7M) | 8% | same band (v2 55%) |
| TGS | 26.62 | 40.88 | 39.50 / 54.00 | 54% | 8 | SB 2 / B 5 / H 0 / S 1 (buy) | small ($5.9M) | 8% | NEW |
| BLBD | 58.12 | 89.12 | 89.50 / 95.00 | 53% | 8 | SB 2 / B 6 / H 0 / S 0 (strong_buy) | mid ($30.1M) | 11% | same band (v2 57%) |
| YSWY | 19.32 | 29.62 | 30.00 / 32.00 | 53% | 8 | SB 2 / B 4 / H 3 / S 0 (buy) | small ($6.3M) | 11% | same band (v2 53%) |
| BBUC | 25.46 | 38.81 | 40.75 / 45.00 | 52% | 8 | SB 4 / B 2 / H 1 / S 1 (buy) | small ($9.2M) | 8% | same band (v2 54%) |
| NXST | 162.10 | 246.75 | 249.50 / 290.00 | 52% | 8 | SB 2 / B 6 / H 0 / S 0 (strong_buy) | mid ($57.6M) | 8% | same band (v2 53%) |
| JBTM | 110.09 | 167.06 | 168.00 / 210.00 | 52% | 8 | SB 2 / B 5 / H 0 / S 1 (buy) | mid ($60.2M) | 8% | same band (v2 51%) |
| CTNM | 12.56 | 22.14 | 22.00 / 28.00 | 76% | 7 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | small ($5.8M) | 15% | same band (v2 92%) |
| FIGR | 31.90 | 55.29 | 55.00 / 70.00 | 73% | 7 | SB 3 / B 3 / H 1 / S 0 (none) | large ($117.6M) | 20% | same band (v2 69%) |
| OMCL | 33.66 | 57.86 | 60.00 / 70.00 | 72% | 7 | SB 1 / B 6 / H 1 / S 0 (none) | mid ($23.8M) | 11% | same band (v2 76%) |
| NVCR | 15.84 | 27.14 | 25.00 / 52.00 | 71% | 7 | SB 1 / B 3 / H 3 / S 0 (none) | small ($18.2M) | 18% | same band (v2 69%) |
| STRL | 512.29 | 876.00 | 950.00 / 1,000.00 | 71% | 7 | SB 0 / B 8 / H 0 / S 0 (strong_buy) | large ($339.9M) | 19% | same band (v2 69%) |
| KOPN | 4.99 | 8.43 | 7.00 / 12.00 | 69% | 7 | SB 0 / B 7 / H 0 / S 0 (strong_buy) | small ($15.1M) | 23% | same band (v2 74%) |
| MAMA | 13.35 | 22.29 | 22.00 / 25.00 | 67% | 7 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | small ($9.1M) | 13% | same band (v2 66%) |
| MAX | 9.27 | 15.43 | 15.00 / 19.00 | 66% | 7 | SB 2 / B 3 / H 3 / S 0 (buy) | small ($9.6M) | 11% | same band (v2 64%) |
| OPEN | 2.57 | 4.27 | 4.50 / 7.00 | 66% | 7 | SB 1 / B 1 / H 5 / S 2 (hold) | large ($119.1M) | 16% | same band (v2 67%) |
| ICHR | 57.94 | 95.86 | 98.00 / 115.00 | 65% | 7 | SB 1 / B 5 / H 1 / S 0 (strong_buy) | mid ($51.7M) | 24% | same band (v2 70%) |
| AIP | 23.89 | 39.43 | 40.00 / 50.00 | 65% | 7 | SB 0 / B 7 / H 0 / S 0 (strong_buy) | small ($17.6M) | 21% | same band (v2 65%) |
| GROY | 3.16 | 5.18 | 5.00 / 7.00 | 64% | 7 | SB 4 / B 3 / H 0 / S 0 (buy) | small ($5.2M) | 10% | same band (v2 65%) |
| PRG | 32.68 | 53.43 | 50.00 / 64.00 | 63% | 7 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($19.9M) | 8% | same band (v2 64%) |
| TATT | 37.57 | 60.71 | 61.00 / 66.00 | 62% | 7 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($5.1M) | 11% | same band (v2 60%) |
| AHCO | 5.64 | 9.00 | 9.00 / 10.00 | 60% | 7 | SB 1 / B 6 / H 0 / S 0 (strong_buy) | small ($14.3M) | 25% | same band (v2 59%) |
| IPGP | 78.12 | 124.14 | 125.00 / 152.00 | 59% | 7 | SB 2 / B 4 / H 2 / S 1 (buy) | mid ($34.6M) | 14% | same band (v2 64%) |
| MOD | 198.07 | 310.29 | 302.00 / 355.00 | 57% | 7 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | large ($252.9M) | 15% | same band (v2 58%) |
| HLNE | 86.21 | 133.43 | 130.00 / 181.00 | 55% | 7 | SB 2 / B 4 / H 1 / S 0 (none) | mid ($59.6M) | 9% | same band (v2 56%) |
| VCEL | 39.71 | 60.57 | 59.00 / 72.00 | 53% | 7 | SB 0 / B 7 / H 1 / S 0 (strong_buy) | mid ($21.2M) | 7% | same band (v2 55%) |
| CECO | 73.50 | 111.86 | 118.00 / 130.00 | 52% | 7 | SB 2 / B 5 / H 0 / S 0 (none) | mid ($53.4M) | 15% | same band (v2 51%) |
| ROAD | 93.71 | 142.57 | 139.00 / 165.00 | 52% | 7 | SB 0 / B 5 / H 1 / S 0 (strong_buy) | mid ($68.3M) | 14% | same band (v2 55%) |
| VIAV | 40.68 | 61.43 | 65.00 / 70.00 | 51% | 7 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | large ($171.8M) | 19% | same band (v2 66%) |
| ALKT | 13.80 | 20.71 | 21.00 / 25.00 | 50% | 7 | SB 2 / B 4 / H 1 / S 1 (buy) | mid ($22.8M) | 14% | NEW |
| IE | 10.56 | 20.92 | 20.00 / 28.50 | 98% | 6 | SB 4 / B 3 / H 0 / S 0 (buy) | small ($18.3M) | 16% | A -> B (v2 111%) |
| KOD | 32.35 | 64.00 | 63.50 / 85.00 | 98% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | mid ($23.2M) | 12% | A -> B (v2 125%) |
| PLAY | 6.62 | 13.00 | 11.00 / 22.00 | 96% | 6 | SB 0 / B 3 / H 7 / S 0 (buy) | small ($15.2M) | 18% | same band (v2 95%) |
| CRMD | 7.85 | 15.33 | 15.00 / 19.00 | 95% | 6 | SB 3 / B 3 / H 0 / S 0 (strong_buy) | small ($7.3M) | 12% | same band (v2 99%) |
| RXRX | 3.74 | 7.22 | 7.00 / 10.00 | 93% | 6 | SB 2 / B 1 / H 4 / S 0 (buy) | mid ($55.2M) | 17% | same band (v2 94%) |
| TPB | 62.07 | 118.50 | 120.50 / 140.00 | 91% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | mid ($24.4M) | 11% | same band (v2 94%) |
| CALX | 33.14 | 62.33 | 60.00 / 85.00 | 88% | 6 | SB 2 / B 4 / H 1 / S 0 (buy) | mid ($37.4M) | 8% | same band (v2 87%) |
| DQ | 11.47 | 21.31 | 20.50 / 31.87 | 86% | 6 | SB 2 / B 3 / H 1 / S 1 (buy) | small ($10.5M) | 13% | same band (v2 95%) |
| VYX | 7.07 | 12.96 | 13.50 / 15.00 | 83% | 6 | SB 2 / B 3 / H 1 / S 0 (buy) | small ($19.4M) | 15% | same band (v2 85%) |
| DC | 6.61 | 12.09 | 10.88 / 16.00 | 83% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($6.3M) | 13% | same band (v2 84%) |
| SVCO | 8.36 | 15.17 | 14.50 / 18.00 | 81% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($2.9M) | 22% | same band (v2 87%) |
| CDRE | 26.39 | 47.50 | 45.00 / 62.00 | 80% | 6 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | small ($10.5M) | 11% | same band (v2 79%) |
| CXDO | 6.09 | 10.92 | 11.00 / 12.00 | 79% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($2.1M) | 12% | same band (v2 85%) |
| ORN | 8.58 | 15.32 | 15.00 / 16.00 | 79% | 6 | SB 1 / B 5 / H 0 / S 0 (none) | small ($4.4M) | 16% | same band (v2 78%) |
| RMIX | 13.05 | 23.17 | 23.50 / 25.00 | 78% | 6 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($4.8M) | 12% | same band (v2 86%) |
| UPBD | 16.09 | 28.25 | 27.25 / 41.00 | 76% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($16.0M) | 9% | same band (v2 78%) |
| DSGN | 12.12 | 21.00 | 21.00 / 22.00 | 73% | 6 | SB 2 / B 5 / H 0 / S 0 (none) | small ($7.7M) | 13% | same band (v2 73%) |
| BKD | 11.11 | 19.25 | 18.25 / 23.00 | 73% | 6 | SB 2 / B 4 / H 0 / S 0 (strong_buy) | mid ($56.6M) | 8% | same band (v2 72%) |
| BLZE | 13.19 | 22.83 | 23.00 / 25.00 | 73% | 6 | SB 2 / B 4 / H 1 / S 0 (buy) | mid ($32.0M) | 22% | same band (v2 68%) |
| MFA | 8.17 | 14.00 | 10.75 / 31.00 | 71% | 6 | SB 1 / B 2 / H 4 / S 0 (none) | small ($13.1M) | 4% | same band (v2 70%) |
| ABX | 8.29 | 14.08 | 14.00 / 16.00 | 70% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($5.5M) | 12% | same band (v2 72%) |
| CTGO | 18.55 | 31.17 | 31.00 / 35.00 | 68% | 6 | SB 3 / B 3 / H 0 / S 0 (strong_buy) | small ($6.2M) | 14% | same band (v2 73%) |
| ARLO | 12.84 | 21.00 | 21.00 / 25.00 | 64% | 6 | SB 2 / B 5 / H 0 / S 0 (strong_buy) | small ($16.8M) | 10% | same band (v2 61%) |
| Z | 28.43 | 46.00 | 41.50 / 62.00 | 62% | 6 | SB 1 / B 1 / H 5 / S 0 (hold) | large ($117.2M) | 12% | same band (v2 63%) |
| TBN | 35.11 | 56.67 | 56.50 / 75.00 | 61% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($4.4M) | 9% | same band (v2 57%) |
| EVER | 18.64 | 29.50 | 28.50 / 34.00 | 58% | 6 | SB 3 / B 3 / H 2 / S 0 (buy) | small ($15.0M) | 14% | same band (v2 67%) |
| REPL | 12.36 | 19.50 | 19.50 / 24.00 | 58% | 6 | SB 2 / B 5 / H 0 / S 1 (none) | mid ($33.8M) | 44% | same band (v2 57%) |
| AGX | 364.29 | 573.00 | 582.50 / 800.00 | 57% | 6 | SB 1 / B 3 / H 1 / S 1 (none) | large ($164.3M) | 17% | same band (v2 54%) |
| LOVE | 15.19 | 23.17 | 20.00 / 35.00 | 53% | 6 | SB 1 / B 4 / H 0 / S 0 (none) | small ($3.4M) | 13% | same band (v2 55%) |
| SMG | 50.89 | 77.17 | 77.50 / 82.00 | 52% | 6 | SB 1 / B 4 / H 3 / S 0 (buy) | mid ($50.7M) | 9% | NEW |
| NMRK | 13.06 | 19.75 | 19.50 / 22.00 | 51% | 6 | SB 4 / B 2 / H 1 / S 0 (none) | small ($19.9M) | 10% | NEW |
| LTRX | 7.01 | 10.58 | 10.50 / 12.00 | 51% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($4.5M) | 15% | same band (v2 59%) |
| SEZL | 111.38 | 168.00 | 167.50 / 196.00 | 51% | 6 | SB 1 / B 3 / H 3 / S 0 (none) | mid ($72.4M) | 24% | same band (v2 54%) |
| APEI | 41.66 | 62.83 | 63.00 / 70.00 | 51% | 6 | SB 1 / B 5 / H 1 / S 0 (strong_buy) | small ($13.7M) | 12% | NEW |
| YOU | 39.60 | 59.67 | 61.50 / 75.00 | 51% | 6 | SB 2 / B 2 / H 1 / S 1 (buy) | mid ($74.3M) | 10% | same band (v2 55%) |
| ECG | 116.94 | 176.00 | 176.00 / 200.00 | 51% | 6 | SB 0 / B 5 / H 2 / S 0 (none) | mid ($60.1M) | 15% | same band (v2 53%) |
| INFQ | 14.51 | 21.83 | 22.00 / 25.00 | 50% | 6 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | large ($100.6M) | 19% | NEW |
| AEVA | 15.35 | 30.00 | 27.00 / 42.00 | 95% | 5 | SB 0 / B 3 / H 2 / S 0 (none) | mid ($24.7M) | 28% | A -> B (v2 101%) |
| EOLS | 7.97 | 15.00 | 13.00 / 20.00 | 88% | 5 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($5.3M) | 14% | same band (v2 89%) |
| REAX | 16.43 | 29.90 | 35.00 / 65.00 | 82% | 5 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($12.8M) | 23% | A -> B (v2 104%) |
| JBI | 4.21 | 7.62 | 9.00 / 9.00 | 81% | 5 | SB 1 / B 2 / H 2 / S 0 (buy) | small ($7.6M) | 9% | same band (v2 85%) |
| CEPU | 13.18 | 23.81 | 24.00 / 28.00 | 81% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | small ($2.8M) | 9% | same band (v2 78%) |
| USAU | 15.59 | 27.95 | 27.50 / 33.25 | 79% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($3.0M) | 11% | same band (v2 80%) |
| GENB | 15.15 | 27.00 | 27.00 / 30.00 | 78% | 5 | SB 2 / B 4 / H 0 / S 0 (none) | small ($13.4M) | 18% | same band (v2 72%) |
| JMIA | 6.88 | 12.21 | 11.85 / 17.78 | 77% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | small ($9.7M) | 12% | same band (v2 79%) |
| UCTT | 77.69 | 137.00 | 140.00 / 150.00 | 76% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | mid ($90.3M) | 25% | same band (v2 79%) |
| COAG | 34.74 | 61.20 | 60.00 / 65.00 | 76% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($15.8M) | 18% | same band (v2 76%) |
| GRNT | 4.44 | 7.80 | 7.00 / 11.00 | 76% | 5 | SB 0 / B 3 / H 2 / S 0 (none) | small ($4.3M) | 8% | same band (v2 72%) |
| NVCT | 20.22 | 35.40 | 35.00 / 40.00 | 75% | 5 | SB 2 / B 4 / H 0 / S 0 (strong_buy) | small ($4.4M) | 26% | same band (v2 66%) |
| ANGX | 4.80 | 8.20 | 9.00 / 9.00 | 71% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | small ($5.6M) | 17% | same band (v2 71%) |
| SUPV | 7.24 | 12.36 | 12.50 / 15.00 | 71% | 5 | SB 2 / B 0 / H 3 / S 0 (none) | small ($4.1M) | 12% | same band (v2 64%) |
| INVA | 20.74 | 35.00 | 35.00 / 46.00 | 69% | 5 | SB 0 / B 4 / H 0 / S 1 (buy) | small ($14.4M) | 5% | same band (v2 70%) |
| TBLA | 3.48 | 5.80 | 5.50 / 7.00 | 67% | 5 | SB 1 / B 4 / H 2 / S 0 (buy) | small ($10.0M) | 17% | same band (v2 69%) |
| SATL | 6.17 | 10.20 | 10.00 / 11.00 | 65% | 5 | SB 0 / B 5 / H 0 / S 0 (strong_buy) | mid ($22.7M) | 23% | same band (v2 71%) |
| MUX | 19.02 | 31.20 | 31.00 / 37.00 | 64% | 5 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($17.5M) | 13% | same band (v2 68%) |
| SRZN | 29.54 | 48.40 | 52.00 / 54.00 | 64% | 5 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($3.6M) | 38% | NEW |
| SFIX | 2.15 | 3.50 | 3.50 / 4.00 | 62% | 5 | SB 0 / B 1 / H 4 / S 1 (hold) | small ($5.0M) | 17% | A -> B (v2 110%) |
| CSV | 31.94 | 51.80 | 50.00 / 65.00 | 62% | 5 | SB 2 / B 3 / H 0 / S 0 (none) | small ($4.5M) | 9% | same band (v2 62%) |
| AAOI | 101.40 | 163.40 | 178.00 / 220.00 | 61% | 5 | SB 2 / B 1 / H 3 / S 0 (none) | large ($933.8M) | 28% | same band (v2 62%) |
| MDXG | 4.67 | 7.40 | 8.00 / 8.00 | 58% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | small ($4.8M) | 7% | same band (v2 55%) |
| LPTH | 9.98 | 15.80 | 15.50 / 17.00 | 58% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | mid ($32.7M) | 26% | same band (v2 57%) |
| QNST | 14.41 | 22.80 | 23.00 / 24.00 | 58% | 5 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($13.1M) | 19% | same band (v2 60%) |
| PPTA | 23.49 | 36.90 | 37.00 / 43.50 | 57% | 5 | SB 3 / B 5 / H 0 / S 0 (strong_buy) | mid ($23.0M) | 15% | same band (v2 59%) |
| DCTH | 15.60 | 24.00 | 22.00 / 32.00 | 54% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | small ($5.8M) | 13% | same band (v2 53%) |
| LOMA | 9.35 | 14.30 | 14.50 / 15.00 | 53% | 5 | SB 2 / B 3 / H 0 / S 0 (none) | small ($3.7M) | 8% | same band (v2 51%) |
| PHIN | 62.04 | 94.00 | 95.00 / 105.00 | 52% | 5 | SB 1 / B 3 / H 1 / S 0 (none) | mid ($21.9M) | 10% | same band (v2 58%) |


## 5c. Passed the screen but fewer than 5 analysts or no count - 178 names

NRXP 1177% (n 4); DFNS 734% (n 2); XNDU 563% (n 3); SPRY 451% (n 4); QTTB 382% (n 4); SIDU 372% (n 1); RZLV 359% (n 4); TNXP 351% (n 4); NEOV 345% (n 4); ASPI 344% (n 3); GOGO 270% (n 2); BW 251% (n 4); CABO 248% (n 4); DRUG 223% (n 3); FIP 218% (n 4); TOYO 213% (n 2); AGEN 208% (n 3); BTQ 190% (n 2); SWMR 189% (n 1); SLDP 188% (n 2); KULR 187% (n 1); KARD 186% (n 4); CDZI 183% (n 3); RLMD 181% (n 4); CUE 180% (n 3); SLS 180% (n 2); DUOT 179% (n 2); IMSR 171% (n 3); INBX 168% (n 3); ABAT 165% (n 2); RUM 163% (n 1); BRUN 155% (n 4); OGG 153% (n 1); SLSR 152% (n 1); SOC 151% (n 4); LAES 150% (n 2); ECC 143% (n 4); VIVO 143% (n 1); ALTO 141% (n 2); WRN 137% (n 2); VISN 136% (n 3); GLAS 135% (n 3); NN 134% (n 3); SHEN 134% (n 2); UAMY 132% (n 4); ATOM 130% (n 1); GLIBA 128% (n 1); SLGL 128% (n 2); DERM 124% (n 4); ITRG 123% (n 2); AVLN 122% (n 4); ADUR 114% (n 4); OPFI 112% (n 4); QUIK 110% (n 3); AMPG 110% (n 1); HIMX 109% (n 2); SUJA 109% (n 4); VELO 106% (n 4); AMSC 106% (n 4); OSS 105% (n 3); TMQ 104% (n 3); WATT 103% (n 1); PDYN 99% (n 4); AVR 99% (n 3); ARKO 99% (n 2); DGXX 96% (n 2); CERS 96% (n 4); ARIS 95% (n 1); SA 95% (n 4); CDNL 94% (n 4); HNRG 92% (n 3); PESI 92% (n 1); USAS 92% (n 1); TTI 91% (n 4); ALOY 91% (n 2); FWRD 91% (n 2); GAU 91% (n 2); BBAR 90% (n 4); POET 90% (n 1); HYLN 90% (n 3); CPS 89% (n 3); GILT 89% (n 2); MNTS 89% (n 1); LWLG 88% (n 1); DAKT 88% (n 3); REZI 87% (n 4); SGML 86% (n 3); LGIH 86% (n 1); BGSI 86% (n 4); CTRN 86% (n 2); ROCK 86% (n 4); IMMR 85% (n 1); WINA 84% (n 1); NG 83% (n 2); NNBR 82% (n 3); ADMA 81% (n 4); ASM 81% (n 4); BULL 81% (n 4); CENX 80% (n 4); SRTA 79% (n 4); CMCL 79% (n 3); CYD 79% (n 4); NXE 79% (n 2); INOD 77% (n 4); ALMU 77% (n 2); DNN 77% (n 2); MATV 76% (n 1); PGEN 76% (n 3); IA 76% (n 4); MMS 76% (n 2); RFIL 75% (n 2); ODTX 74% (n 4); WLDN 74% (n 2); PURR 74% (n 4); NPKI 73% (n 3); SPIR 73% (n 4); WNC 73% (n 2); TCMD 72% (n 3); IIIV 71% (n 4); NGS 71% (n 3); NMAX 70% (n 2); EGY 70% (n 3); TWI 70% (n 4); DIOD 70% (n 2); DMC 69% (n 1); RPC 69% (n 4); ADEA 69% (n 4); RERE 68% (n 4); TSSI 67% (n 2); BBW 67% (n 4); BMNR 66% (n 3); HCKT 66% (n 3); CRML 66% (n 2); MATW 65% (n 3); EXK 65% (n 3); NBTX 65% (n 3); MLKN 65% (n 1); RYAM 63% (n 2); ASTE 63% (n 4); EBS 62% (n 2); CHRN 61% (n 1); KRNT 61% (n 4); GSIT 60% (n 1); MNRO 60% (n 4); TBBK 59% (n 3); CVLG 59% (n 4); NTGR 59% (n 3); CLPT 58% (n 2); RELX 58% (n 2); SCZM 58% (n 1); UVV 58% (n 1); TGLS 57% (n 4); TTMI 57% (n 4); DBD 57% (n 3); AOSL 57% (n 4); VZLA 56% (n 1); NUAI 56% (n 2); RTO 55% (n 4); CRAI 55% (n 2); AEBI 55% (n 2); CMCO 54% (n 4); ALIT 54% (n 3); BELFA 54% (n 2); DDD 54% (n 2); PWP 54% (n 4); APPS 53% (n 2); BNED 52% (n 2); LWAY 52% (n 3); AMSF 52% (n 3); MEI 52% (n 4); SUNS 51% (n 4); AAON 51% (n 4); CODI 51% (n 3); IBRX 51% (n 4); VTOL 51% (n 3); PUK 51% (n 4); PRM 50% (n 4); WD 50% (n 3)


## 5d. What moved vs v2

v2 (snapshot 2026-09-24, counts 2026-09-25): A 166 / B 365 / C 179 = 710 names. v3 (snapshot 2026-09-27, counts 2026-09-27): A 167 / B 355 / C 178 = 700 names. **Entered the screen: 23**; **left it: 33**; **changed band: 23**. Names without a count this pass: 0. A name leaves when its price rose toward the target or the target was cut below +50%; it enters when the price fell or a target was raised. The price moves dominate over 3 days - that is the §17 mechanism in miniature.

| Change | Names |
|---|---|
| entered (23) | ACAD 56%, ALKT 50%, AMSF 52%, APEI 51%, BKV 56%, BMRN 52%, BRZE 53%, CELH 51%, CHRN 61%, GEN 51%, INFQ 50%, LWAY 52%, MGM 51%, MIR 56%, NMRK 51%, PUK 51%, SCZM 58%, SFM 51%, SMG 52%, SRZN 64%, TGS 54%, VERX 51%, YSS 55% |
| left (33) | ACMR (v2 53%, now 50%), AESI (v2 63%, now 42%), AGL (v2 57%, now 47%), AGNT (v2 56%, now 48%), ALGM (v2 58%, now 49%), ALH (v2 53%, now 48%), AN (v2 50%, now 47%), ANGI (v2 62%, now 48%), APTV (v2 52%, now 49%), ASTH (v2 52%, now 42%), BKNG (v2 52%, now 46%), BV (v2 55%, now 48%), CHYM (v2 50%, now 47%), FIGS (v2 51%, now 39%), FUL (v2 51%, now 40%), GRFS (v2 50%, now 48%), GVA (v2 53%, now 49%), HMH (v2 53%, now 50%), IDR (v2 51%, now 48%), IONQ (v2 52%, now 48%), JACK (v2 50%, now 48%), KTB (v2 51%, now 49%), LMB (v2 53%, now 50%), MBLY (v2 54%, now 46%), MLCO (v2 51%, now 49%), OLED (v2 55%, now 49%), PAX (v2 51%, now 48%), POWI (v2 55%, now 48%), PPLI (v2 59%, now 42%), SGI (v2 50%, now 46%), SLI (v2 117%, now 141%, price now < $2), TRUP (v2 51%, now 48%), WSE (v2 51%, now 47%) |
| band changed (23) | AEVA A->B, ALM A->B, AUR A->B, AVEX B->A, CWH A->B, DPRO B->A, EOSE B->A, FTH B->A, GIL B->A, IE A->B, IMMX B->A, KOD A->B, LAC B->A, QBTS A->B, QFIN B->A, REAX A->B, RUN A->B, RZLT B->A, SFIX A->B, SHAZ B->A, UTI B->A, VNET B->A, WING A->B |


---


# 6. NEWS-FORECAST STOCKS (new in v3) - what the Dow Jones columns forecast

Sources: the Dow Jones corpus `backend/data/optimus/news_corpus/dowjones/` (35 stored articles read 2026-09-26 in Murat's MuratClaw window at human pace: WSJ Heard on the Street, Barron's stock picks, the Barron's Big Money poll, and MarketWatch analyst pages), the claims extracted from them (`_claims/2026-09-26.jsonl`, 22 claims) and the forecast rows written from those claims into `backend/data/optimus/predictions.jsonl` (**51 rows**: specialist `source:wsj_heard_on_the_street` / `source:barrons_stock_picks`, observable beats_benchmark vs SPY at 1 / 5 / 20 sessions, p 0.60 for 'up' and 0.40 for 'down' - a fixed 0.5 +/- 0.10 by stated direction; the column earns its weight only through `forecast_reputation`). Licence: personal research reads; headlines, metadata and our own one-line claims are stored, no full-text redistribution - so a 'reason' below is our paraphrase with at most a short quote.

**Reliability so far: n graded = 0 for every column** (made 2026-09-26; the first 1-session rows resolve after the 09-28/29 sessions, the 20-session rows around 2026-10-26). **PIT caveat:** every row is pit_grade 'first_seen_only' - the forecast is stamped when WE read the article, and the articles were published 1 to 24 days earlier, so part of any move the column 'predicted' may already be in the price. The grader scores from made_at, which is the honest clock for us, not for the columnist.

| Ticker | Column | Dir. | Reason (our paraphrase of the article) | Published / horizon | Potential upside | Street snapshot | Forecast rows | Our v3 card | Column record |
|---|---|---|---|---|---|---|---|---|---|
| BN | Barron's pick | up | Barron's picks Brookfield as undervalued, trading at a discount to asset value with upside to analyst targets. | 2026-09-25 / 252d stated / rows 1/5/20 | stated: Brookfield is his top pick among the major alternative managers, and he carries a price target of $61 a share. | yf n 10, SB 5 / B 5 / H 0 / S 1 (buy); mean tgt 54.40 (lo 31.00 / hi 61.00) = 48% | 3 rows, p 0.60, made 2026-09-26 | neutral/med | n 0 / hit - |
| AAPL | WSJ HOTS | up | Wall Street analysts expect Apple's iPhone revenue to rise 17% this year. | 2026-09-23 / 252d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 252d = 23% (the bound we credit) | yf n 39, SB 6 / B 19 / H 13 / S 6 (buy); mean tgt 328.22 (lo 215.00 / hi 405.00) = -4% | 3 rows, p 0.60, made 2026-09-26 | neutral/med | n 0 / hit - |
| AMGN | WSJ HOTS | down | Amgen shares plunged as investors doubted the Lp(a) approach. | 2026-09-12 / 63d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 63d = 14% (the bound we credit) | yf n 29, SB 4 / B 8 / H 17 / S 5 (hold); mean tgt 389.22 (lo 225.00 / hi 457.00) = -6% | 3 rows, p 0.40, made 2026-09-26 | neutral/med | n 0 / hit - |
| BA | WSJ HOTS | down | The Spirit acquisition's hidden liabilities are another headwind for Boeing shareholders, who have suffered repeated setbacks. | 2026-09-03 / 252d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 252d = 26% (the bound we credit) | yf n 26, SB 5 / B 18 / H 4 / S 0 (strong_buy); mean tgt 273.50 (lo 246.00 / hi 305.00) = 38% | 3 rows, p 0.40, made 2026-09-26 | neutral/med | n 0 / hit - |
| BA | WSJ HOTS | down | The software glitch may hinder airline adoption of Boeing's newest 737 MAX models, a negative for the company. | 2026-09-26 / 63d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 63d = 13% (the bound we credit) | yf n 26, SB 5 / B 18 / H 4 / S 0 (strong_buy); mean tgt 273.50 (lo 246.00 / hi 305.00) = 38% | 3 rows, p 0.40, made 2026-09-26 | neutral/med | n 0 / hit - |
| BSP | WSJ HOTS | down | Rising rates will make acquisition funding harder, pressuring Bending Spoons' growth and lofty valuation, so the stock is likely to fall. | 2026-09-11 / 252d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 252d = 68% (the bound we credit) | yf n 12, SB 1 / B 7 / H 3 / S 1 (buy); mean tgt 47.92 (lo 36.00 / hi 72.00) = 44% | 3 rows, p 0.40, made 2026-09-26 | neutral/med | n 0 / hit - |
| CRM | WSJ HOTS | up | Salesforce stock is undervalued and looks like a good bargain. | 2026-09-08 / 252d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 252d = 46% (the bound we credit) | yf n 53, SB 6 / B 32 / H 14 / S 2 (buy); mean tgt 281.08 (lo 160.00 / hi 475.00) = 20% | 3 rows, p 0.60, made 2026-09-26 | supports/med | n 0 / hit - |
| HWM | WSJ HOTS | up | The author says SpaceX's entry does not weaken the long-term investment case for Howmet. | 2026-09-02 / 252d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 252d = 30% (the bound we credit) | yf n 21, SB 4 / B 16 / H 3 / S 0 (strong_buy); mean tgt 337.74 (lo 256.56 / hi 375.00) = 45% | 3 rows, p 0.60, made 2026-09-26 | supports/high | n 0 / hit - |
| LEU | WSJ HOTS | up | Centrus deserves a premium valuation because of its unique position in domestic uranium enrichment. | 2026-09-21 / 252d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 252d = 61% (the bound we credit) | yf n 17, SB 2 / B 10 / H 7 / S 0 (buy); mean tgt 247.40 (lo 168.77 / hi 340.00) = 68% | 3 rows, p 0.60, made 2026-09-26 | neutral/med | n 0 / hit - |
| LNG | WSJ HOTS | up | Cheniere Energy would benefit from higher LNG prices if Europe needs spot supplies later this year. | 2026-09-09 / 126d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 126d = 18% (the bound we credit) | yf n 21, SB 5 / B 15 / H 2 / S 0 (strong_buy); mean tgt 310.19 (lo 255.00 / hi 340.00) = 16% | 3 rows, p 0.60, made 2026-09-26 | supports/med | n 0 / hit - |
| NOW | WSJ HOTS | up | ServiceNow's strong sales growth supports a positive view of the stock. | 2026-09-08 / 63d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 63d = 22% (the bound we credit) | yf n 46, SB 10 / B 35 / H 2 / S 2 (strong_buy); mean tgt 144.99 (lo 72.00 / hi 248.00) = 7% | 3 rows, p 0.60, made 2026-09-26 | supports/med | n 0 / hit - |
| NVO | WSJ HOTS | down | Novo Nordisk's stock declined after its inflammation drug failed to prevent cardiovascular events. | 2026-09-12 / 63d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 63d = 16% (the bound we credit) | yf n 12, SB 0 / B 3 / H 10 / S 1 (hold); mean tgt 46.39 (lo 39.73 / hi 62.87) = 20% | 3 rows, p 0.40, made 2026-09-26 | neutral/med | n 0 / hit - |
| PSNL | WSJ HOTS | up | Personalis shares trading above the $16.25 deal price signal investors expect a higher bid or bidding war. | 2026-09-04 / 63d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 63d = 25% (the bound we credit) | yf n 4, SB 0 / B 2 / H 3 / S 0 (none); mean tgt 15.44 (lo 13.00 / hi 16.25) = -6% | 3 rows, p 0.60, made 2026-09-26 | supports/med | n 0 / hit - |
| SNOW | WSJ HOTS | up | Snowflake's raised sales forecast signals a positive outlook for the stock. | 2026-09-08 / 63d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 63d = 18% (the bound we credit) | yf n 47, SB 9 / B 34 / H 6 / S 1 (strong_buy); mean tgt 425.19 (lo 110.00 / hi 525.00) = 27% | 3 rows, p 0.60, made 2026-09-26 | supports/med | n 0 / hit - |
| TEM | WSJ HOTS | up | Analysts see sequencing revenue of at least $50 million, potentially over $600 million, as an opportunity barely reflected in Tempus stock. | 2026-09-04 / 252d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 252d = 71% (the bound we credit) | yf n 18, SB 2 / B 8 / H 9 / S 1 (buy); mean tgt 68.56 (lo 35.00 / hi 100.00) = -19% | 3 rows, p 0.60, made 2026-09-26 | refused | n 0 / hit - |
| VG | WSJ HOTS | up | Venture Global would benefit from higher LNG prices if Europe needs spot supplies later this year. | 2026-09-09 / 126d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 126d = 36% (the bound we credit) | yf n 18, SB 4 / B 6 / H 8 / S 0 (buy); mean tgt 16.67 (lo 14.00 / hi 22.00) = 32% | 3 rows, p 0.60, made 2026-09-26 | neutral/med | n 0 / hit - |
| WDAY | WSJ HOTS | up | Workday's strong results and growing AI adoption support a positive view. | 2026-09-08 / 63d stated / rows 1/5/20 | no stated target; σ63-predicted \|move\| over the stated 63d = 25% (the bound we credit) | yf n 38, SB 5 / B 15 / H 19 / S 3 (buy); mean tgt 208.68 (lo 92.00 / hi 275.00) = 10% | 3 rows, p 0.60, made 2026-09-26 | supports/med | n 0 / hit - |
| NVDA | Barron's Big Money poll | up | Money managers view Nvidia favorably, with one calling it uniquely positioned to keep growing as an AI bellwether. | 2025-10-23 / 252d stated | no stated target; σ63-predicted \|move\| over the stated 252d = 31% (the bound we credit) | yf n 59, SB 10 / B 48 / H 2 / S 1 (strong_buy); mean tgt 327.70 (lo 180.00 / hi 515.00) = 46% | NOT a forecast: archive article (published 2025-10-23, > 30 days before first seen) | supports/high | n 0 / hit - |
| PLTR | Barron's Big Money poll | down | A money manager expects a potential shakeout in Palantir and other highflying tech stocks. | 2025-10-23 / 252d stated | no stated target; σ63-predicted \|move\| over the stated 252d = 57% (the bound we credit) | yf n 26, SB 1 / B 19 / H 9 / S 2 (buy); mean tgt 195.57 (lo 80.00 / hi 255.00) = 3% | NOT a forecast: archive article (published 2025-10-23, > 30 days before first seen) | - | n 0 / hit - |
| TSLA | Barron's Big Money poll | down | Many managers consider Tesla the market's most overvalued stock, implying downside risk from its rich valuation. | 2025-10-23 / 252d stated | no stated target; σ63-predicted \|move\| over the stated 252d = 45% (the bound we credit) | yf n 38, SB 4 / B 15 / H 20 / S 4 (buy); mean tgt 396.62 (lo 125.00 / hi 600.00) = 7% | NOT a forecast: archive article (published 2025-10-23, > 30 days before first seen) | - | n 0 / hit - |
| DELL | WSJ HOTS | up | The article notes Dell's stock has risen sharply this year along with other PC makers. | 2026-09-23 / 252d stated | no stated target; σ63-predicted \|move\| over the stated 252d = 64% (the bound we credit) | yf n 25, SB 6 / B 14 / H 9 / S 0 (buy); mean tgt 577.36 (lo 480.00 / hi 735.00) = 3% | NOT a forecast row (claim only) | - | n 0 / hit - |
| HOOD | WSJ HOTS | none | Robinhood charges a subscription fee for Gold, offering a 3.6% yield on uninvested cash. | 2026-09-24 / 63d stated | no stated target; σ63-predicted \|move\| over the stated 63d = 28% (the bound we credit) | yf n 27, SB 6 / B 18 / H 3 / S 2 (buy); mean tgt 130.08 (lo 57.00 / hi 170.00) = 9% | NOT a forecast: direction none | neutral/med | n 0 / hit - |


## The Big Money poll (index level) and the MarketWatch analyst pages

| Index | Direction | Bullish % | Bearish % | Neutral % | Horizon | Published | First seen by us | Note |
|---|---|---|---|---|---|---|---|---|
| SPX | up | 57 | 19 | 34 | unstated | 2025-10-23 | 2026-09-26 | ARCHIVE: published ~11 months before we read it; context only, not a forecast row |

A second Big Money poll article (published 2026-04-27) is stored without a structured row. The same 2025-10 poll produced three stock claims - NVDA up, PLTR down, TSLA down ('the market's most overvalued stock') - which were NOT turned into forecast rows because the article is an archive by the corpus PIT rule (published > 30 days before first seen).

| Ticker | MW consensus | n | Price | Mean tgt | Low | High | Mean upside | Next earnings | EPS FY est | Read (UTC) |
|---|---|---|---|---|---|---|---|---|---|---|
| AARD | Overweight | 11 | 5.55 | 10.13 | 3.00 | 28.00 | 83% | 04/05/2027 |  | 2026-09-26T18:38 |
| ABSI | Buy | 11 | 10.35 | 14.40 | 10.00 | 17.00 | 39% | 03/23/2027 |  | 2026-09-26T19:07 |
| AMSC | Buy | 5 | 30.42 | 61.40 | 54.00 | 71.00 | 102% | 06/02/2027 | 0.88 | 2026-09-26T19:18 |
| BHVN | Overweight | 14 | 13.19 | 23.08 | 10.00 | 42.00 | 75% | 03/08/2027 |  | 2026-09-26T19:27 |
| DKNG | Overweight | 42 | 21.27 | 34.33 | 20.00 | 76.00 | 61% | 02/18/2027 | 0.12 | 2026-09-26T16:15 |
| GEV | Overweight | 41 | 955.04 | 1,214.37 | 470.00 | 1,450.00 | 27% | 01/27/2027 | 30.64 | 2026-09-26T20:40 |
| HUBS | Overweight | 38 | 221.56 | 249.63 | 190.00 | 327.00 | 13% | 02/17/2027 | 13.29 | 2026-09-26T19:36 |
| KYTX | Buy | 6 | 6.99 | 30.40 | 25.00 | 33.00 | 335% | 04/01/2027 |  | 2026-09-26T19:46 |
| MU | Buy | 57 | 1,080.53 | 1,575.88 | 361.00 | 2,200.00 | 46% | 09/30/2026 | 73.77 | 2026-09-26T16:06 |
| NTLA | Overweight | 19 | 12.16 | 23.81 | 8.00 | 61.00 | 96% | 02/25/2027 |  | 2026-09-26T19:55 |
| PRCH | Buy | 8 | 16.47 | 20.69 | 16.50 | 25.00 | 26% | 03/02/2027 | 0.02 | 2026-09-26T20:04 |
| QUBT | Overweight | 8 | 9.16 | 18.86 | 10.00 | 32.00 | 106% | 03/31/2027 |  | 2026-09-26T20:12 |
| SLDP | Buy | 2 | 2.35 | 6.88 | 6.75 | 7.00 | 193% | 03/02/2027 |  | 2026-09-26T20:22 |
| SOC | Buy | 7 | 3.97 | 9.40 | 8.00 | 11.00 | 137% | 03/22/2027 |  | 2026-09-26T20:31 |
| VRT | Buy | 34 | 245.30 | 339.21 | 245.00 | 427.00 | 38% | 02/24/2027 | 6.72 | 2026-09-26T20:37 |


---


# 7. APPENDIX - where every number came from

| Item | File / source | Date / run id |
|---|---|---|
| Frozen books, twins, void | backend/data/optimus/llm_portfolio/books.jsonl | 281 records; rehearsal 4d0cebfeb8867fb8, core-satellite 5517aa50a29bc95b frozen 2026-09-26T19:59:52Z |
| Paper-account status | backend/data/optimus/paper_accounts/roi_2026-09-27.json | 2026-09-27T06:44:32+00:00 |
| Dress rehearsal design | docs/BOOK_2026-09-27_BLOOMBERG_DRESS_REHEARSAL.md; backend/data/optimus/rehearsal/rehearsal_2026-09-27.json | 2026-09-27 |
| Review verdicts | docs/HANDOFF_2026-09-26_WAVE2_THE_REVIEW_LOOP_CLOSED_FOUR_IDEAS.md §§1-16; docs/reviews/ADJUDICATION_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md | 2026-09-26/27 |
| Factory receipt of record | backend/data/optimus/strategy_library/leaderboard_2026-09-26T164302Z(.rekeyed).json; T032801Z | 69/119/139 of 288 |
| Thesis cards v3 | backend/data/optimus/thesis_cards/2026-09-27/*.json + _run_receipt.json + DIGEST.md | 67 cards (three runs); model deepseek/deepseek-flash + OpenClaw muratclaw |
| Thesis cards v2 (previous) | backend/data/optimus/thesis_cards/2026-09-25/*.json (MU: 2026-09-26) | 2026-09-25 |
| σ63, predicted move, fundamentals proxy, EDGAR earnings estimate | backend/services/rehearsal_book.py (sigma63, predicted_abs_move, fundamentals_composite, earnings_estimates) over prices_2025_26/bars.parquet, fundamentals_sec/sec_facts_history.parquet, edgar_8k/eightk_items.parquet | bars through 2026-09-25; universe 2890 |
| Freeze-gate construction check | scripts/night_backtest_factory.py freeze_gate (construction + timing) | on the section-3 top 10 |
| Analyst targets | backend/data/optimus/analyst/target_snapshots.parquet (+ target_revisions.parquet) | pull 2026-09-27 (observed 2026-09-26T17:14Z); analyst_pull_2026-09-27.json |
| Analyst counts + mix | yfinance Ticker.info / Ticker.recommendations | fetched 2026-09-27 (v2: 2026-09-25) |
| Dow Jones corpus + claims | backend/data/optimus/news_corpus/dowjones/ (wsj, barrons, marketwatch, _claims, _structured) | read 2026-09-26 |
| News forecast rows | backend/data/optimus/predictions.jsonl (specialist source:wsj_heard_on_the_street / source:barrons_stock_picks) | 51 rows, made 2026-09-26 |
| Source claims | backend/data/optimus/sources/claims.jsonl | 2026-09-26 |
| Murat's holdings | backend/data/murat_book.yaml | reconciled 2026-08-11 |
| Research note | docs/research_notes/2026-09-27/research_v3_demand_ceo_competition.md | landed |

**LLM spend (the day's thesis cards, all three runs): $2.37 at the provider-calibrated price** (`backend/data/optimus/llm_price/calibration_2026-09-27.json`, commit `201b8402`: deepseek-flash priced from the provider's own balance delta, k = 0.615 [0.590, 0.639] vs the old price table; the run receipt's `spend_repriced_usd` 2.368 from `thesis_cards/2026-09-27/spend_repriced.json`). The two figures v3 printed over-state the provider: the old price table read $3.82 (1.61x) and OpenClaw's own per-quest figure $4.89 (2.01x); v3's $3.38 / $4.33 were partial sums of those rulers. Everything else in this document: $0.


## Standing findings (updated)

1. **§17 - target LEVEL is perverse:** high analyst-implied upside underperformed, -90 bps/mo large/mid (t -3.62), -199 bps/mo small (t -7.21). Sections 3 and 5 are research lists for that reason; section 3 bounds the upside by 2σ and weights it by the card, which does not make it a signal.

2. **What forecasts:** the free σ63 vol prior on MAGNITUDE (+10.0% held out at h=1 vs the LLM investigator's +5.5%); LLM DIRECTION does not (-7.9%, n = 780); broker identity is a coin flip (50.1%); first-mover raises were look-ahead; the analyst-skill filter is 2025 only. A process forecasts, a persona does not (§64).

3. **Nothing is distinguishable yet:** no rule survives multiplicity (best DSR 0.617 at the honest denominator vs 0.95) and the 32-block window's MDE is 2.46%/month; the panel tilts small (IWM beta 0.65-0.92), so 69 / 119 / 139 of 288 rules beat SPY / IWM / the random panel in both windows. The first forward read that can say something is 2026-10-26, and it reads calibration and exposure, not return.
