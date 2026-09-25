
# AEGIS - stock lists, 2026-09-26

Prepared 2026-09-26 for Murat, read-only from the Aegis-Finance repo. No LLM calls were made to build this document; every table is parsed directly from a named file and every number carries the file it came from (the Appendix lists every path and date). Analyst counts in section 4 were fetched from Yahoo Finance via yfinance on 2026-09-26 where the stored snapshot did not carry them, and each such row is marked 'yf live'.

**Read this before section 4.** The repo's own measurement says analyst target-LEVEL upside is a PERVERSE cross-sectional signal: NEGATIVE_RESULTS.md §17 (TRIAL-TGT-REBUILD) - high-upside names underperformed by −90 bps/month in large/mid caps (t −3.62) and −199 bps/month in small caps (t −7.21). A name with +100% implied upside has, on the historical evidence, been more likely to lag than to lead. Section 4 is therefore a CANDIDATE LIST TO RESEARCH, not a buy list. The 2026-09-25 research (research_themes.md Theme 10) also caught a public 'upside screener' inventing numbers by roughly 4-20x, so a row here is a pointer, not a verified fact.

Contents: 1. CHOSEN - the frozen books · 2. CONSIDERED - the thesis cards · 3. THE POTENTIAL LIST (union of the 2026-09-25 research tables) + Murat's holdings · 4. ANALYST-IMPLIED UPSIDE ≥ 50% / ≥ 100% · 5. Appendix.


---


# 1. CHOSEN - the frozen books

Source: `backend/data/optimus/llm_portfolio/books.jsonl`. Twin records (kind == twin: the ew / sector_etf / random / spy comparators) are skipped; the last record per book name is shown. Weights are fractions of the $1,000,000 notional book; positions sorted by weight.


## human_ai_thematic_v2 - book_id 5d137b013692a737

kind personal · frozen 2026-09-25T09:58:15+00:00 · 24 positions · max weight 12.0% · cash 2.0% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session (6-month) return vs SPY; graded beside ew / sector_etf / random_same_band / spy twins; v1 keeps running as the un-reviewed control  
**Model:** fable-5.1 draft v2 = v1 + the external review Murat forwarded 2026-09-25 evening (human side)

**Strategy:** Same five themes as v1 (AI power bottleneck, memory/foundry, prediction markets, strategic resources/nuclear, biotech catalysts) with fewer stories: 22 names instead of 28. The review's rule adopted: a very good thesis should not fight for capital against many weak ones. Core VRT 12 / GEV 9 / MU 9 / TSM 7 / HOOD 7 / NVT 6, plus three operating AI-infrastructure names the review preferred over quantum and project-stage lithium: AVGO (custom accelerators already monetising), CLS (UBS-preferred picks-and-shovels), BE (behind-the-meter power). Pharma keeps VRTX (Nov 30) and WST, raises COGT to 3 (two PDUFAs, PFS 16.5 vs 9.2 months, ~$866M cash) and VKTX to 3 (September durability data), keeps AGIO 2, BBIO 1, PRAX 1, RGEN 1. Removed: QUBT (card against/high; the human holding is a separate matter), CAPR (card against; PDUFA already extended), SLI (project-finance, not earnings), ALB (wrong horizon), ENS (immaterial line), TER (replaceable), RGTI (do not own both quantum names), GILD (a stabiliser; this book is not for stabilisers). Rejected from the review: AMZN -- a mega-cap is a sensor, not the six-month asymmetry this book buys. DKNG stays at 3 as HOLD pending Q3.

| Ticker | Weight | Theme | Thesis | Falsifier |
|---|---|---|---|---|
| VRT | 12.0% | power_grid | AI power/cooling; UtilityInnovation acquisition moves it into onsite generation and microgrid control; deferred revenue $1.81B->$3.63B. | Q3 organic growth below the 34-36% guide, or backlog growth stalls. |
| GEV | 9.0% | power_grid | Generation/grid side of the same bottleneck; 116 GW turbine backlog; Q3 Oct 28. | slot reservations fail to convert to signed orders by Oct 28. |
| MU | 9.0% | semis | HBM/DRAM pricing and allocation; FQ4 print Sep 30 -- an expectation-risk event, sized for it. | Sep 30 print misses the ~86% gross-margin guide or spot DRAM/NAND rolls over. |
| TSM | 7.0% | semis | Participates whichever accelerator wins; Sep monthly sales Oct 8, Q3 Oct 15. | Q3 gross margin below the 65% floor or a capex-guide cut. |
| HOOD | 7.0% | gambling | Event contracts a material business (13.6B contracts Q2; revenue > crypto); the listed winner of the handle leak; Q3 Nov 4. | state or federal action forcing event contracts under state gambling licensing. |
| NVT | 6.0% | power_grid | Q2 sales +53%, EPS +69% on data-center electrical infrastructure; Maverick Power acquisition. | Maverick fails to close by the Nov 20 outside date; fall cooling launch slips. |
| AVGO | 6.0% | semis | AI chip revenue outlook raised to ~$115B FY2027; custom accelerators and networking already monetising (review's replacement for quantum). | a hyperscaler custom-silicon program slips or is in-sourced; AI revenue guide cut. |
| CLS | 5.0% | semis | UBS-preferred AI-infrastructure name; ~70% revenue growth tied to custom-chip/data-center programs. | hyperscaler order push-outs at the next print. |
| BE | 4.0% | power_grid | Behind-the-meter power for data centers -- the most direct expression if the bottleneck is power. | no new data-center power contracts announced by year end; margin guide cut. |
| MP | 4.0% | materials | Government floor price + offtake; strategic magnets. | legal challenge to the equity-taking authority succeeds; China's state group buys Shenghe and the exposure bites. |
| VRTX | 4.0% | biotech | Q2 revenue +12%, guidance raised; povetacicept PDUFA Nov 30 on strong Phase 3 data -- an operating company plus a catalyst. | CRL or a narrower label than IgAN accelerated approval. |
| NOVT | 3.0% | robotics | Servo-drive order for humanoids disclosed Aug 6; three analysts, negative momentum, growth partly acquired -- a hypothesis, sized like one. | order absent from backlog at the ~Nov 10 print. |
| WST | 3.0% | biotech | GLP-1 components; Morgan Stanley upgrade, UBS target $415. | GLP-1 component destocking at Q3. |
| COGT | 3.0% | biotech | GIST Phase 3 median PFS 16.5 vs 9.2 months; PDUFAs Nov 30 and Dec 30; ~$866M cash. The review's most-underweighted name. | CRL on the first PDUFA. |
| VKTX | 3.0% | biotech | September data: VK2735 durability with biweekly/monthly dosing and good tolerability -- a product-quality signal; ObesityWeek Nov. | tolerability signal at the November data. |
| DKNG | 3.0% | gambling | HELD. Consensus ~60% upside is real; CAC falling; Predictions ~2.5x July; targets trimmed; Q3 in November decides. | second quarter of hold compression, or Predictions forced to unwind in a state. |
| LEU | 2.0% | nuclear | HALEU with private prepayments now; DOE has said it will not exercise the old option -- the thesis is not risk-free. | no non-DOE offtake converts; further dilution after the $500M raise. |
| CCJ | 2.0% | nuclear | Uranium; Kazakh sulfuric-acid export ban threatens 2027 supply. | acid supply resolved; spot/equity divergence widens against it. |
| AGIO | 2.0% |  | Commercial business ($44.7M Q2 mitapivat), ~$965M cash, Nov 1 priority review. | CRL. |
| CASH | 2.0% |  | declared |  |
| IONQ | 1.0% | quantum | Quantum optionality; real-time decoder + NVIDIA 09-23. | no third-party replication; dilution. |
| RGEN | 1.0% | biotech | Bioprocessing; positive revisions but rich valuation. | book-to-bill < 1 at Q3. |
| BBIO | 1.0% | biotech | BBP-418 PDUFA Nov 27. BINARY. | CRL. |
| PRAX | 1.0% | biotech | PDUFA Dec 27 (extended). BINARY, low confidence. | the extension precedes a CRL. |


## human_ai_thematic_v1 - book_id a20a2b972988eec6

kind personal · frozen 2026-09-25T07:19:10+00:00 · 29 positions · max weight 12.0% · cash 3.0% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session (6-month) return vs SPY; graded beside ew / sector_etf / random_same_band / spy twins  
**Model:** fable-5.1 draft v1 (AI side after the social + pharma reads) + Murat (human side, owed)

**Strategy:** Murat's rules for v1: 6-month ROI, no per-name cap when the evidence is strong, keep his DKNG and QUBT positions under review rather than out, add pharma. The core is the AI power bottleneck (VRT/GEV/NVT), memory allocation (MU), TSMC, and HOOD as the listed winner of betting's migration to prediction markets. Pharma enters as three sleeves: dated large-cap catalysts (VRTX Nov 30, GILD Dec 23), platform names with primary-sourced momentum (WST, RGEN, VKTX), and small binary PDUFAs sized 1-2% each for the CRL tail (PRAX Dec 27, COGT Nov 30/Dec 30, BBIO Nov 27, CAPR Nov 22, AGIO Nov 1). DKNG stays at 3%: the ~60% consensus upside is real from primary sources, CAC is falling and Predictions volume is ~2.5x July, but Q2 missed, hold rate had its worst quarter and management reinvests the savings; ADD only if Q3 (November) shows hold normalising with EBITDA conversion. QUBT stays at 1%: revenue $5.6M, opex +114% YoY, the net-loss improvement is a derivative accounting artefact, targets $10-$32; ADD only on two quarters of accelerating revenue with opex growth below revenue growth. Not bought: MCD (five cuts 09-24), FLUT (same leak as DKNG, no Predictions hedge), OKLO/SMR, SERV, SMMT (consensus Hold), NVO (Street turned after REDEFINE 4), pump-shaped retail names (RKLB, NBIS, BB, BYND, DNUT), and anything chosen because a screener said +50-300% (NEGATIVE_RESULTS 17).

| Ticker | Weight | Theme | Thesis | Falsifier |
|---|---|---|---|---|
| VRT | 12.0% | power_grid | AI power/cooling; $2.6B Utility Innovations deal 09-03; deferred revenue $1.81B->$3.63B. | MW shipped/backlog growth stalls at Q3 (late Oct). |
| GEV | 9.0% | power_grid | 116 GW gas-turbine backlog; DOE Speed to Power $5.25B 09-24. | slot reservations fail to convert to signed orders. |
| MU | 9.0% | semis | HBM4 allocation ~20% of NVIDIA; retail crowding confirms attention but the thesis is allocation, not mentions. | HBM share loss in TrendForce data; 2027 capex-digestion guide. |
| HOOD | 8.0% | gambling | Event-contract revenue $156M Q2 > crypto revenue; Q3 Nov 4; the listed winner of the AGA-documented handle leak. | CFTC/state orders constrain sports event contracts (NV/MI/CT precedents). |
| NOVT | 6.0% | robotics | Disclosed humanoid servo-drive order, hundreds of robots in testing (Aug 6 call); Baird $194. | order absent from backlog at ~Nov 10 earnings. |
| NVT | 5.0% | power_grid | Guide raised to 37-39%; fall cooling launch. | launch slips. |
| TSM | 5.0% | semis | Q3 earnings Oct 15; the capacity gate for every AI name. | capex guide cut. |
| ENS | 4.0% | lithium | Lithium data-center backup line decouples from the EV cycle. | segment share ~0% at Dec earnings. |
| MP | 4.0% | materials | Government floor price + offtake; the policy-stake template. | legal challenge to the equity-taking authority succeeds (INTC case). |
| LEU | 3.0% | nuclear | $900M DOE HALEU order; SMR offtakes. | DOE remains the only customer. |
| VRTX | 3.0% | biotech | Povetacicept PDUFA Nov 30 (primary); no MFN deal = tariff exposure to price. | CRL or a label narrower than IgAN accelerated approval. |
| WST | 3.0% | biotech | Cleanest listed GLP-1 supply-chain proxy; primary, dated, positive momentum. | GLP-1 component destocking at Q3. |
| DKNG | 3.0% | gambling | HELD (150 sh). ~60% consensus upside is real (Citizens JMP 09-24 +64.7%); CAC falling >80% after app integration; Predictions ~2.5x July. Q2 missed, hold rate worst quarter, savings reinvested. | Q3 (Nov) shows a second quarter of hold compression, or a state ruling forces Predictions to unwind. ADD trigger: hold back toward 9.8% with EBITDA conversion. |
| CASH | 3.0% |  | declared; absorbs binary-event losses without a forced sale |  |
| SLI | 2.0% | lithium | DOE FONSI; Trafigura/LGES offtakes. | FID slips; UBS cut 2027 China lithium price 40% on 09-22 is the bear tape. |
| ALB | 2.0% | lithium | Section 232 critical-minerals decision overdue. | no tariff and spot keeps falling. |
| CCJ | 2.0% | nuclear | Uranium; Kazakh sulfuric-acid export ban (09-12) threatens 2027 supply. | acid supply resolved; spot/equity divergence widens against it. |
| TER | 2.0% | robotics | Robotics + test; Q3 Oct 27. | Advantest keeps HBM/photonics test wins. |
| RGEN | 2.0% | biotech | Bioprocessing tools; primary-sourced order momentum. | book-to-bill < 1 at Q3. |
| VKTX | 2.0% | biotech | Oral obesity; ObesityWeek Nov data. | tolerability signal at the November data. |
| GILD | 2.0% | biotech | Anito-cel PDUFA Dec 23 (primary, via Arcellx). | CRL / manufacturing hold. |
| PRAX | 2.0% | biotech | PDUFA Dec 27 (extended); 18/20 Buy. BINARY. | the extension precedes a CRL. |
| IONQ | 1.0% | quantum | Real-time decoder + NVIDIA 09-23. | no third-party replication; dilution. |
| RGTI | 1.0% | quantum | $100M Commerce equity stake 09-04. | 10-Q shows a grant, not equity. |
| COGT | 1.0% | biotech | Two PDUFAs: GIST Nov 30, NonAdvSM Dec 30 (both primary). BINARY. | CRL on the first. |
| BBIO | 1.0% | biotech | BBP-418 PDUFA Nov 27 (primary). BINARY. | CRL. |
| CAPR | 1.0% | biotech | PDUFA Nov 22; adcom 9-3 against the original label. BINARY, coin flip. | no label granted. |
| AGIO | 1.0% | biotech | PDUFA Nov 1, priority review. BINARY. | CRL. |
| QUBT | 1.0% | quantum | HELD (300 sh). Revenue $5.6M from $61K; $1.3B cash; backlog $42.5M; targets $10-$32. | another large ATM raise without backlog; ADD trigger: two quarters of accelerating revenue with opex growth below revenue growth. |


## reviewer_opus_2026-09-25 - book_id 919892d54f6e3190

kind personal · frozen 2026-09-25T10:08:04+00:00 · 11 positions · max weight 14.0% · cash 0.0% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY; the adversarial reviewer's own book, graded like every other arm (docs/reviews/REVIEW_2026-09-25_CHUNK0_THE_DAYS_BUILD.md section 6)  
**Model:** claude-opus-5-5 reviewer, 2026-09-25

**Strategy:** The reviewer's ten: the AI power/memory chain at its Asian and European source (SK Hynix, Advantest, Siemens Energy, LS Electric), the US grid names (GEV, NVT), prediction markets (HOOD), one operating biotech with a Q4 readout (ARGX), and European/Korean defence (Hanwha Aerospace, Leonardo). Every name carries its thesis card's falsifier. Worst case stated by the reviewer: about -$220k on a -35% AI/power drawdown. 60% of the book is non-USD and is graded in local currency until the FX leg exists (chunk 5) -- the caveat travels with the grade.

| Ticker | Weight | Theme | Thesis | Falsifier |
|---|---|---|---|---|
| 000660.KS | 14.0% | semis | HBM leader; 3Q26 print 2026-10-27. | 3Q26 shows HBM/DRAM ASPs falling. |
| GEV | 12.0% | power_grid | 116 GW backlog; Q3 Oct 28. | reservations fail to convert by Oct 28. |
| 6857.T | 10.0% | semis | HBM/AI test leader. | FY26 Q2 (Oct 28) gross margin below Q1. |
| HOOD | 10.0% |  | event contracts; Q3 Nov 4. | state/federal action on event contracts. |
| ARGX | 10.0% | biotech | EMPASSION Phase 3 topline Q4 2026. | EMPASSION misses its primary endpoint. |
| ENR.DE | 9.0% | power_grid | grid/turbines; FY results Nov 11. | comparable growth below the 14-16% guide. |
| 010120.KS | 9.0% |  | switchgear/transformers; Q3 Oct 28. | order intake below the raised KRW 6.0tn. |
| 012450.KS | 9.0% | defense | defence exports. | ground-systems operating margin below 10%. |
| LDO.MI | 9.0% | defense | European defence; 9M results Nov 5. | free operating cash flow still negative. |
| NVT | 8.0% | power_grid | data-center electrical; Maverick close by Nov 20. | Maverick fails to close; launch slips. |
| CASH | 0.0% |  | declared: the reviewer runs fully invested |  |


## cards_supports_2026-09-25 - book_id 89761b53e2cd82ba

kind personal · frozen 2026-09-25T10:07:43+00:00 · 21 positions · max weight 4.9% · cash 2.0% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY; the pure-evidence arm: every thesis card that came back 'supports' on 2026-09-25, equal weight, no human override  
**Model:** thesis_card v1 (engine + OpenClaw + DeepSeek synthesis), 2026-09-25

**Strategy:** 20 names whose card verdict is supports, equal weight, no human edits. Exists because the reviewer found v2 left nine supports names out and added three un-carded ones. Graded beside v1, v2 and the reviewer's book: if this beats them, the human side cost money.

| Ticker | Weight | Theme | Thesis | Falsifier |
|---|---|---|---|---|
| 000660.KS | 4.9% | semis | card: supports / med | 3Q26 earnings on 2026-10-27 showing HBM or DRAM average selling prices falling versus 2Q26, or operating profit below the KRW 60.54T reported for 2Q26. |
| 010120.KS | 4.9% |  | card: supports / med | Q3 2026 earnings on 2026-10-28 showing order intake below the raised KRW 6.0tn annual run-rate or operating margin under 11.3%. |
| 012450.KS | 4.9% |  | card: supports / med | Q3 2026 ground systems operating margin reported below 10% (versus 35-39% export margin), or a Poland K9 EC3 award slipping past 2026-12-31. |
| 2330.TW | 4.9% | semis | card: supports / high | 3Q26 earnings on 2026-10-15 showing gross margin below the guided 65% floor or 3Q26 revenue under US$44.6bn. |
| 6857.T | 4.9% |  | card: supports / med | FY2026 Q2 results on 2026-10-28 showing gross margin below Q1 FY2026 and no repeat of the inventory-obsolescence reversal, with guidance not raised again. |
| 8035.T | 4.9% | semis | card: supports / med | FY2027 Q2 earnings on 2026-10-30 showing gross margin below Q1 FY2027 and no H2 recovery, or H1 net sales under the raised 1,620B yen guidance. |
| ARGX | 4.9% |  | card: supports / med | The Q4 2026 EMPASSION MMN readout (empasiprubart) fails its primary endpoint, or the Q3 2026 report on 2026-10-22 shows product sales growth decelerating below |
| ENR.DE | 4.9% |  | card: supports / med | FY2026 results on 2026-11-11 show comparable revenue growth below the guided 14-16 pct or Siemens Gamesa back at a loss. |
| ENS | 4.9% | lithium | card: supports / med | The lithium data-center-backup line staying near 0% of segment revenue by the Dec earnings call would falsify the decoupling thesis -- the book's own stated fal |
| GEV | 4.9% | power_grid | card: supports / med | Turbine-backlog slot reservations failing to convert into signed orders by the 2026-10-28 Q3 print would falsify the bull case -- again the book's own stated fa |
| HOOD | 4.9% | gambling | card: supports / med | A state or federal action forcing Robinhood's event contracts under state gambling licensing (raising costs / restricting states) would falsify the bull thesis; |
| LDO.MI | 4.9% |  | card: supports / med | 9M 2026 results on 5 Nov 2026 showing free operating cash flow still negative and no further FY2026 guidance raise. |
| LLY | 4.9% |  | card: supports / med | Q3 2026 earnings on 2026-10-29 (unconfirmed) showing worldwide realized price decline worse than Q2's 13 pct while volume growth falls below 40 pct, or FY2026 r |
| MP | 4.9% | materials | card: supports / med | A successful legal or legislative challenge to the government's equity-taking/floor-price authority, or NdPr volume growth stalling well below the 127% y/y pace |
| MU | 4.9% | semis | card: supports / med | The 2026-09-30 FQ4 print missing the ~86% gross-margin guide, or DRAM/NAND spot pricing rolling over shortly after, would falsify the pricing-cycle bull case. |
| NOVT | 4.9% | robotics | card: supports / low | The servo-drive order being cancelled, or absent from disclosed backlog, at the ~2026-11-10 Q3 call would falsify the bull case -- the thematic book's own state |
| NVT | 4.9% | power_grid | card: supports / med | The Maverick Power acquisition failing to close by its 2026-11-20 outside date (or extending to Feb 2027, signaling deal friction) would be the first concrete n |
| RGTI | 4.9% | quantum | card: supports / low | If the 10-Q/8-K terms show the government's $100M as a grant/award rather than an actual equity stake -- the book's own stated falsifier for this position -- or |
| TSM | 4.9% | semis | card: supports / med | Q3-2026 gross margin reported below 65% on 2026-10-15, or September monthly sales (2026-10-08) showing YoY growth decelerating below 30%. |
| VRT | 4.9% | power_grid | card: supports / med | A confirmed Q3 (Oct, date unconfirmed on IR) organic growth print below the 34-36% guide, or evidence that MW backlog is not converting to signed/shipped orders |
| CASH | 2.0% |  | declared |  |


## Factory books - personal (pers_*, 10)


### pers_ai_power_global_2026-09-25 - book_id 994aa4afda4fa2d1

kind personal · frozen 2026-09-25T07:26:45+00:00 · 14 positions · max weight 11.0% · cash 6.0% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** Bet that the AI capex bottleneck is physical: power generation, grid gear, cooling, and the memory and litho tools that capex buys, plus a few dated healthcare and uranium catalysts. Every name has a dated observable inside the six-month window (GEV/VRT/NVT orders, ASML Oct 14, TSM Oct 15, TER Oct 27, MRK Oct 10, ARGX Oct 22, EVO Oct 23, CCJ Nov 3-4). I am wrong if a hyperscaler capex pause hits the whole chain at once, if memory pricing rolls over, or if any single PDUFA prints a CRL.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| GEV | 11.0% | Q2 orders +88% organically to $24.2B and backlog $176B (research_notes) with inflection_flag true and 8 net raises | Q3 orders or backlog growth stalls when reported in late Oct 2026 |
| VRT | 10.0% | $2.6B Utility Innovations deal Sept 3 2026 plus 31% sales growth guidance (research_notes) and rev_qoq 0.2358 | Q3 backlog or liquid-cooling revenue per MW flat at the late-Oct 2026 print |
| NVT | 9.0% | Q1 2026 sales +53% YoY, FY guide raised to 37-39%, inflection_flag true and 6 net raises | Fall-2026 modular liquid-cooling launch slips past Nov 2026 |
| MU | 9.0% | HBM4 shortage with DRAM inventory under 10 days and rev_yoy 3.4572 with inflection_flag true | HBM4 allocation share loss or a 2027 capex digestion signal by Dec 2026 earnings |
| ASML | 8.0% | Q3'26 earnings confirmed Oct 14 2026 with Q3 revenue guide $12.8-14.0bn vs Street $11.3bn and 5 net raises | Order intake or 2027 guidance cut on the Oct 14 2026 call |
| TSM | 8.0% | FY26 capex guide raised to $60-64B and Q3 earnings confirmed Oct 15 2026 (catalysts) | Capex guidance cut or gross margin below the 65-67% guide on Oct 15 2026 |
| TER | 7.0% | Q3'26 earnings confirmed Oct 27 2026 with ~70% AI-related revenue and 6 net raises | Robotics-segment growth decelerates below 33% or Advantest qualification wins stall at the Oct 27 print |
| AME | 6.0% | 12 net raises with zero lowers and a $5B deal (news_14d) plus rev_yoy 0.1498 | Deal integration charges or order growth turning negative in the Q3 print |
| MRK | 6.0% | 22 net raises from 17 firms and I-DXd PDUFA Oct 10 2026 (catalysts) | CRL on the I-DXd BLA on Oct 10 2026 |
| CASH | 6.0% | declared cash |  |
| ARGX | 5.0% | 17 net raises from 14 firms and Q3'26 results confirmed Oct 22 2026 (catalysts) | EMPASSION Phase 3 topline miss or Q3 guidance cut on Oct 22 2026 |
| CCJ | 5.0% | Q3'26 earnings Nov 3-4 2026 (catalysts) with uranium term price at a record $96/lb | Production guidance cut or uranium spot falling below $80/lb by Nov 2026 |
| WST | 5.0% | 7 net raises with zero lowers and HVP Delivery Devices +27-30% organic on the GLP-1 supply chain | GLP-1 device orders decelerating at the late-Oct/early-Nov 2026 print |
| EVO.ST | 5.0% | Q3'26 report confirmed Oct 23 2026 (catalysts) with Americas +9.5% and LatAm +26.3% growth | Asia revenue declines more than 3.7% QoQ in the Oct 23 2026 report |

**What it did not buy:** ALB|12 net lowers and lithium spot down 16% in a month; INTC|Government equity stake carries live legal-authority lawsuit risk; OKLO|Zero revenue, analyst targets dispersed $55-$150 in one week; SMR|Six net lowers and revenue down 99% YoY; FLUT|15 net lowers and four guidance cuts in 2026; IONQ|35x forward sales with chronic ATM dilution and 71% share count growth; SERV|Revenue guidance cut sharply on weaker Uber Eats volumes; QUBT|Opex +114% YoY and analyst targets dispersed $10-$32


### pers_asia_supply_chain_2026-09-25 - book_id f97957221662a8b9

kind personal · frozen 2026-09-25T07:22:03+00:00 · 14 positions · max weight 11.9% · cash 5.9% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** Bet that the AI capex chain's Q3 prints confirm tightness rather than digestion, concentrated in the physical chokepoints: leading-edge foundry and HBM memory (2330.TW, 000660.KS, 005930.KS, MU), the semicap tools that gate capacity (ASML, 8035.T, 6857.T, 6146.T, TER, AMKR), and the AI server/power layer one step down (2317.TW, 2382.TW, 2308.TW). Every name has an earnings or sales print inside the next six months, so relative return is driven by real numbers, not theme momentum. I would be wrong if any hyperscaler signals capex digestion, if HBM4 share shifts decisively to Samsung against SK Hynix, or if a China export-control headline hits the tool names simultaneously.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| 2330.TW | 11.9% | Q3'26 earnings Oct 15 and FY26 capex raised to $60-64B with >40% sales growth (research_themes Theme 2) | Oct 15 call guides capex below $60B or gross margin under 60% |
| 000660.KS | 9.9% | Bernstein Sept 22 flags HBM4 ramp lagging Samsung while consensus Q3 op profit ~KRW78.1tn record (research_global_candidates) | Q3 print shows HBM4 share loss to Samsung or DRAM contract prices rolling over |
| 005930.KS | 8.9% | Bernstein Sept 22 raised Q3 HBM revenue estimate 23% to ~$11.4bn, +72% QoQ (research_global_candidates) | Oct 8 prelim guidance misses and HBM4 mix stays below 30% |
| ASML | 8.9% | Q3'26 earnings confirmed Oct 14 with Q2 guiding Q3 revenue $12.8-14.0bn vs Street $11.3bn (research_global_candidates) | Oct 14 bookings disappoint or 2027 guidance implies order digestion |
| 6857.T | 7.9% | Raised FY26 sales guide +21% to JPY1,714bn on AI inference test demand (research_global_candidates) | Late-Oct FY26 Q2 orders show Advantest test demand rolling over |
| 8035.T | 6.9% | WFE spend cycle and advanced-node tool share into late-Oct/early-Nov FY26 Q2 results (research_global_candidates) | China export-control headline or FY26 Q2 bookings decline sequentially |
| 2317.TW | 6.9% | Aug revenue +52% YoY record and Hon Hai Tech Day Oct 30-31 confirmed (research_global_candidates) | Tech Day or Q3 print shows AI server rack ramp slipping versus guidance |
| 2308.TW | 6.9% | Named the liquid-cooling/800V DC power leader for AI infrastructure at Computex (research_global_candidates) | Monthly sales decelerate or component cost inflation compresses AI power margins |
| 2382.TW | 5.9% | Custom-ASIC server volume production this quarter with order visibility into 2027 (research_global_candidates) | Early-Nov Q3 print shows AI server revenue below the custom-ASIC ramp plan |
| CASH | 5.9% | declared cash |  |
| 6146.T | 5.0% | Advanced packaging and HBM dicing demand into late-Oct FY26 Q2 results (research_global_candidates) | FY26 Q2 orders fall on China capex slowdown or HBM dicing demand stalls |
| AMKR | 5.0% | $2.5-3B 2026 capex with 65-70% into the Arizona campus and ~80k CoWoS wafers of 2026 demand (research_themes Theme 2) | Arizona ramp milestones slip or TSMC in-house CoWoS capacity displaces OSAT need |
| TER | 5.0% | Q3'26 earnings confirmed Oct 27 after close with ~70% AI-related revenue and H2 device qualifications (research_themes Theme 2) | Oct 27 print shows no new device qualification wins versus Advantest |
| MU | 5.0% | HBM4 shortage with Samsung/SK Hynix DRAM inventory under 10 days and ~20% of NVIDIA HBM4 allocation (research_themes Theme 2) | HBM pricing rolls over or a 2027 memory capex digestion is guided |

**What it did not buy:** NVDA|199 headlines, no dated catalyst, crowded mega-cap beta; INTC|Government equity stake legal challenge is unresolved binary risk; ALB|Net 12 target cuts and lithium spot normalizing, negative revision flow; SMR|Six downgrades and revenue down 99% YoY, negative evidence name; OKLO|Zero revenue, analyst targets dispersed $55-$150 in one week; FLUT|Net 15 target cuts, four 2026 guidance cuts, near 52-week low; LAC|Down 71% from 52w high, no dated catalyst in evidence; SERV|Guidance cut on weaker Uber Eats volumes, clean falsifying datapoint


### pers_catalyst_calendar_2026-09-25 - book_id 56daa7269d142603

kind personal · frozen 2026-09-25T07:27:04+00:00 · 22 positions · max weight 6.8% · cash 4.5% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** Only names with a hand-verified dated catalyst inside the six-month horizon: PDUFAs (MRK Oct 10, AGIO Nov 1, SMMT Nov 14, CAPR-adjacent names, BBIO Nov 27, VRTX Nov 30, COGT Nov 30/Dec 30, CORT Dec 17, GILD Dec 23, PRAX Dec 27), earnings (ASML Oct 14, TSM Oct 15, SAAB/EVO Oct 23, TER Oct 27, KOG Oct 29, 2317.TW Oct 30, CCJ Nov 3, NVO Nov 4, RHM/HAG Nov 5, ALL.AX Nov 12), spread so no single day decides the book. I am wrong if the dated events slip, or if CRLs cluster in the small-cap PDUFA sleeve where the downside tail is 2-4x the approval pop. [factory: weights and cash rescaled from a stated total of 1.3300 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| VRTX | 6.8% | povetacicept BLA PDUFA Nov 30 2026 (catalysts) with 9 net raises and zero lowers (revision_flow_90d) | CRL on CMC grounds before Nov 30 2026 |
| MRK | 6.8% | ifinatamab deruxtecan PDUFA Oct 10 2026 (catalysts) plus 22 net raises from 17 firms (revision_flow_90d) | FDA action delayed past Oct 10 2026 or a manufacturing CRL |
| GILD | 6.0% | anito-cel BLA PDUFA Dec 23 2026 (catalysts) on a large liquid name at only -0.2% 63d drawdown (briefing) | CRL or facility-inspection finding before Dec 23 2026 |
| CORT | 6.0% | relacorilant NDA resubmission PDUFA Dec 17 2026 (catalysts) with 4 net raises and rev_qoq +55% (briefing) | second CRL on the resubmission around Dec 17 2026 |
| ASML | 6.0% | Q3'26 earnings Oct 14 2026 (catalysts) with 5 net raises from 4 firms (revision_flow_90d) | order guidance cut on the Oct 14 2026 print |
| AGIO | 5.3% | mitapivat sickle-cell sNDA PDUFA Nov 1 2026 (catalysts) with 5 net raises and rev_yoy +259% (briefing) | narrow or negative label decision on Nov 1 2026 |
| COGT | 5.3% | two bezuclastinib PDUFAs Nov 30 and Dec 30 2026 (catalysts) give two shots 30 days apart | either NDA rejected, starting with the Nov 30 2026 GIST decision |
| BBIO | 5.3% | BBP-418 NDA PDUFA Nov 27 2026 (catalysts) with 9 net raises from 11 firms (revision_flow_90d) | CRL on the LGMD2I filing on Nov 27 2026 |
| TSM | 5.3% | Q3'26 earnings Oct 15 2026 (catalysts) with 6 net raises and zero lowers (revision_flow_90d) | capex guide cut on the Oct 15 2026 call |
| SMMT | 4.5% | ivonescimab BLA PDUFA Nov 14 2026 (catalysts) with 8-K filings in the last 14 days (news_14d) | FDA requests more OS data, pushing past Nov 14 2026 |
| PRAX | 4.5% | relutrigine NDA PDUFA Dec 27 2026 (catalysts) with 5 net raises and zero lowers (revision_flow_90d) | second major-amendment delay past Dec 27 2026 |
| TER | 4.5% | Q3'26 earnings Oct 27 2026 (catalysts) with 6 net raises and rev_yoy +104% (briefing) | robotics and test orders miss on the Oct 27 2026 print |
| CASH | 4.5% | declared cash |  |
| CCJ | 3.8% | Q3'26 earnings Nov 3-4 2026 (catalysts) on the uranium supply theme | production or contract guidance cut on the Nov 3 2026 report |
| NVO | 3.8% | Q3'26 results Nov 4 2026 (catalysts) after the CagriSema readout | further share-loss guidance on the Nov 4 2026 call |
| RHM.DE | 3.8% | Q3'26 results Nov 5 2026 (catalysts) on the European rearmament theme | order intake miss on the Nov 5 2026 report |
| HAG.DE | 3.0% | 9-month 2026 results Nov 5 2026 (catalysts) with a >EUR10bn backlog | negative free cash flow worsens on the Nov 5 2026 report |
| SAAB-B.ST | 3.0% | Q3'26 report Oct 23 2026 (catalysts) on the Gripen export pipeline | order or delivery slip on the Oct 23 2026 report |
| KOG.OL | 3.0% | Q3'26 report Oct 29 2026 (catalysts) on missile and defense demand | margin or order miss on the Oct 29 2026 report |
| EVO.ST | 3.0% | Q3'26 report Oct 23 2026 (catalysts) on live-casino growth | Asia revenue decline accelerates on the Oct 23 2026 report |
| ALL.AX | 3.0% | FY26 annual results Nov 12 2026 (catalysts) on Anaxi and digital growth | digital gaming guidance cut on the Nov 12 2026 print |
| 2317.TW | 3.0% | Hon Hai Tech Day Oct 30-31 2026 (catalysts) on AI server rack demand | no new AI server customer disclosed at the Oct 30 2026 event |

**What it did not buy:** ALB|12 target cuts, no raises, lithium price falling; VRT|4 net lowers and no dated catalyst in evidence; GEV|no dated catalyst in the evidence; FLUT|15 net lowers, four 2026 guidance cuts; SMR|6 net lowers, revenue down 99% YoY; OKLO|4 net lowers, zero revenue, no dated catalyst; QUBT|opex +114% YoY, $10-$32 target dispersion; SERV|guidance cut, 3 net lowers, no dated catalyst


### pers_ensemble_2026-09-25 - book_id 4fe78b33214899cc

kind personal · frozen 2026-09-25T07:28:23+00:00 · 20 positions · max weight 10.5% · cash 10.5% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** I only hold names that at least two independent lenses would pick, and I say which two for each. The core is revision flow plus a dated catalyst: MRK, VRTX, GILD, AGIO, COGT and BBIO all carry net-positive analyst target actions into a primary-sourced PDUFA before late March, so the book is paid for real prints rather than theme momentum. Semis (ASML, TSM, NVDA, MU) and software (OKTA, SNOW, CRWD, PANW) are the revision-flow extremes with earnings inside the window. I am wrong if the Q4 PDUFA cluster produces CRLs, or if a single AI-capex digestion headline hits the semis and power names together, since those positions are correlated. [factory: weights and cash rescaled from a stated total of 1.1400 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| CASH | 10.5% | declared cash |  |
| MRK | 7.9% | net_raises 22 of 22 firms with median target change +0.1244 (revision_flow_90d) plus Oct 10 I-DXd PDUFA (catalysts) | CRL on the I-DXd BLA on Oct 10 or a Keytruda LOE headline before late March |
| VRTX | 7.0% | net_raises 9 of 9 firms, zero lowers (revision_flow_90d), with Nov 30 povetacicept PDUFA (catalysts) | povetacicept CRL on Nov 30 or a disclosed MFN/tariff hit on the CF franchise |
| GILD | 6.1% | rev_yoy +0.1018 and gross_margin_chg +0.0053 (briefing) with Dec 23 anito-cel PDUFA (catalysts) | anito-cel CRL on Dec 23 or the net_raises -3 revision trend worsening past -6 |
| ASML | 6.1% | net_raises 5 of 5 firms with median target change +0.1364 (revision_flow_90d) into the Oct 14 Q3 earnings (catalysts) | a 2027 order-book cut or China export-control tightening disclosed on Oct 14 |
| TSM | 6.1% | net_raises 6 of 6 firms with median target change +0.1021 (revision_flow_90d) into Oct 15 Q3 earnings (catalysts) | a capex guide cut or gross-margin guide below 60% on Oct 15 |
| AGIO | 5.3% | net_raises 5 with median target change +0.0968 (revision_flow_90d) into the Nov 1 mitapivat sickle-cell PDUFA (catalysts) | mitapivat sNDA CRL on Nov 1 or a narrow all-genotype label that caps the sickle-cell opportunity |
| NVDA | 5.3% | net_raises 16 of 16 firms across 21 distinct firms (revision_flow_90d) with rev_yoy +1.0585 (briefing) | a hyperscaler capex digestion headline or a data-center revenue guide-down at the next print |
| COGT | 4.4% | net_raises 2 of 2 firms, zero lowers (revision_flow_90d) ahead of two 2026 PDUFAs, Nov 30 GIST and Dec 30 SM (catalysts) | either bezuclastinib NDA drawing a CRL, or both decisions slipping past Dec 30 |
| BBIO | 4.4% | net_raises 9 of 10 firms with median target change +0.0408 (revision_flow_90d) plus Nov 27 BBP-418 PDUFA (catalysts) | BBP-418 CRL on Nov 27 or a guidance cut at the next quarterly print |
| MU | 4.4% | inflection_flag true with rev_qoq +0.7375 and gross_margin_chg +0.1015 (briefing) | HBM4 pricing rolling over or DRAM inventory days rebuilding above 20 |
| AME | 4.4% | net_raises 12 of 12 firms with median target change +0.0666 (revision_flow_90d) and rev_yoy +0.1498 (briefing) | a Q3 order slowdown or the $5B deal closing on terms that dilute the margin guide |
| WST | 4.4% | net_raises 7 of 7 firms with median target change +0.0959 (revision_flow_90d) and gross_margin_chg +0.0266 (briefing) | GLP-1 device orders normalizing below high-teens growth at the late-Oct print |
| RGEN | 3.5% | net_raises 4 of 4 firms with median target change +0.0636 (revision_flow_90d) and mom_63 +0.4277 (briefing) | bioprocessing orders turning negative or the FY26 EPS guide being trimmed |
| CCJ | 3.5% | net_raises -1 but 2 raises vs 3 lowers (revision_flow_90d) with the Nov 3-4 Q3 print (catalysts) on the uranium term-price cycle | a production cut below the 19.5-21.5Mlb guide or spot uranium breaking below $80/lb |
| OKTA | 3.5% | net_raises 63 of 63 firms across 32 distinct firms (revision_flow_90d), the strongest revision flow in the panel | a billings deceleration or a security-incident headline that resets the identity narrative |
| SNOW | 3.5% | net_raises 47 of 47 firms across 33 distinct firms (revision_flow_90d) with rev_yoy +0.3509 (briefing) | product revenue growth decelerating below 30% or net retention falling under 120% |
| CRWD | 3.5% | net_raises 44 with 49 raises vs 5 lowers across 35 firms (revision_flow_90d) | a platform-consolidation loss to a rival or net-new ARR growth dropping below 20% |
| PANW | 3.5% | net_raises 34 of 35 firms with median target change +0.1765 (revision_flow_90d) | a firewall refresh cycle miss or platformization bookings decelerating at the next print |
| GEV | 2.6% | inflection_flag true with rev_qoq +0.189 and gross_margin_chg +0.0218 (briefing) plus net_raises 8 of 8 firms (revision_flow_90d) | a backlog cancellation or a hyperscaler pausing gas-turbine slot reservations |

**What it did not buy:** ALB|net_raises -12, twelve lowers and no raises; FLUT|net_raises -15 with sixteen lowers across fifteen firms; SMR|net_raises -6 and rev_yoy -0.9907; OKLO|net_raises -4 with no raises and no revenue; CAPR|adcom voted 9 of 12 against the cardiomyopathy claim; SERV|net_raises -3 and guidance cut on Uber Eats volumes; NVO|net_raises 0 across a single firm, no revision support; QUBT|gross_margin -0.2101 and opex up 114% YoY


### pers_pharma_binary_basket_2026-09-25 - book_id 4a07e3bfc1fa7d7c

kind personal · frozen 2026-09-25T07:27:26+00:00 · 20 positions · max weight 11.9% · cash 11.9% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** Bet on dated Q4-2026/Q1-2027 FDA decisions and readouts, sized so no single binary exceeds 8% and the CRL tail (roughly -33% over five days) cannot break the book. The core is large-cap pharma with one-sided revision flow (MRK 22 net raises, ABBV 20, LLY 13, AMGN 26) plus VRTX's povetacicept PDUFA on 2026-11-30; the satellites are small-cap PDUFAs (AGIO, COGT, BBIO, SMMT, SVRA, CAPR, PRAX) and platform names (WST, RGEN, VKTX, DHR). I am wrong if a cluster of CRLs lands in November-December, if the 2026-09-29 Section 232 pharma tariff go-live hits unshielded names (VRTX, ARGX), or if a broad risk-off de-rates small-cap biotech regardless of data.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| CASH | 11.9% | declared cash |  |
| VRTX | 7.9% | povetacicept BLA PDUFA 2026-11-30 (catalysts) plus 9 net raises with zero lowers (revision_flow_90d) | CRL or CMC delay on povetacicept announced on or before 2026-11-30 |
| MRK | 7.9% | ifinatamab deruxtecan PDUFA 2026-10-10 (catalysts) with 22 net raises from 17 firms (revision_flow_90d) | I-DXd CRL on the 2026-10-10 PDUFA date |
| LLY | 6.9% | 13 net raises, 14 up vs 1 down, and inflection_flag true on 47.7% rev_yoy (briefing) | Q3 print shows rev_yoy decelerating below 30% or a 2026-10/11 target cut |
| ABBV | 6.9% | 20 net raises from 21 firms with zero lowers (revision_flow_90d) and drawdown_63 of only -0.0056 (briefing) | Two or more of the 21 firms cut targets before the Q3 print |
| GILD | 5.9% | anito-cel BLA PDUFA 2026-12-23 (catalysts) with drawdown_63 -0.0022 and rev_yoy 10.2% (briefing) | Anito-cel CRL or manufacturing finding on 2026-12-23 |
| AGIO | 5.0% | mitapivat sickle cell PDUFA 2026-11-01 (catalysts) with 5 net raises from 6 firms (revision_flow_90d) | FDA grants only a narrow genotype label or issues a CRL on 2026-11-01 |
| COGT | 5.0% | two bezuclastinib NDAs 2026-11-30 and 2026-12-30 (catalysts) with 2 net raises (revision_flow_90d) | Either bezuclastinib NDA draws a CRL on 2026-11-30 or 2026-12-30 |
| BBIO | 5.0% | BBP-418 PDUFA 2026-11-27 (catalysts) with 9 net raises from 11 firms (revision_flow_90d) | BBP-418 CRL on 2026-11-27 |
| SMMT | 4.0% | ivonescimab BLA PDUFA 2026-11-14 (catalysts) and two 8-K filings in news_14d | CRL or an FDA request for more OS data on 2026-11-14 |
| AMGN | 4.0% | 26 net raises from 22 firms (revision_flow_90d) and inflection_flag true on 16.7% rev_qoq (briefing) | Q3 print shows rev_qoq below 10% or a cluster of target cuts |
| WST | 4.0% | 7 net raises with zero lowers (revision_flow_90d) and gross_margin_chg +0.0266 (briefing) | Late-Oct earnings cut FY26 guidance or GLP-1 device orders stall |
| RGEN | 4.0% | 4 net raises with zero lowers (revision_flow_90d) and mom_63 +0.4277 (briefing) | Oct 27/Nov 3 earnings show bioprocessing orders turning negative |
| VKTX | 4.0% | positive Phase 1 maintenance-dosing data 2026-09-22 (research_pharma) and oral Phase 3 start Q4 2026 | Oral VK2735 Phase 3 start slips past 2026 or discontinuation rate stays above 20% |
| SVRA | 3.0% | molgramostim BLA PDUFA 2026-11-22 (catalysts), extended 3 months from Aug 22 | Inhaled-biologic CMC finding or CRL on 2026-11-22 |
| CAPR | 3.0% | deramiocel PDUFA 2026-11-22 (catalysts) after the narrower upper-limb resubmission | FDA rejects the narrower label and issues a CRL on 2026-11-22 |
| PRAX | 3.0% | relutrigine PDUFA 2026-12-27 (catalysts) with 5 net raises from 6 firms (revision_flow_90d) | Major-amendment review ends in a CRL on 2026-12-27 |
| REGN | 3.0% | cemdisiran+pozelimab gMG NDA PDUFA November 2026 (research_pharma) with 4 net raises (revision_flow_90d) | Manufacturing-inspection delay pushes the November 2026 PDUFA past the window |
| DHR | 3.0% | Q3 earnings 2026-10-20 (research_pharma) with bioprocessing orders up mid-teens in Q2 | Q3 core Biotech revenue growth stays below 4% on 2026-10-20 |
| INSM | 3.0% | ARIKAYCE sNDA PDUFA 2027-01-28 (catalysts) and rev_yoy 2.9611 (briefing) | ENCORE sNDA CRL on 2027-01-28 or a brensocatib pipeline setback |

**What it did not buy:** NVO|Hold/Sell-leaning Street after REDEFINE 4 non-inferiority failure; ALB|12 target cuts, zero raises, lithium spot normalizing; VRT|4 target cuts, zero raises, mom_63 -0.299; FLUT|15 net lowers, down ~69% from year-ago peak; OKLO|4 net lowers, zero raises, no revenue; SMR|6 net lowers, rev_yoy -0.9907; BYND|Meme pop with no fundamental news cited; QUBT|$10-$32 target dispersion, opex +114% YoY


### pers_policy_geopolitics_2026-09-25 - book_id 9ed2fedf51df1bbc

kind personal · frozen 2026-09-25T07:20:46+00:00 · 14 positions · max weight 10.0% · cash 6.0% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** I bet on the policy variables that move fastest over 126 sessions: US government equity stakes and critical-minerals nationalism (INTC, MP, TMQ), European defense rearmament into confirmed Q3 prints (RHM.DE, SAAB-B.ST, KOG.OL, HAG.DE), nuclear fuel security (CCJ, LEU), the AI power-grid bottleneck (GEV, NVT), and two dated FDA catalysts (VRTX, MRK). I would be wrong if a legal ruling strikes down executive equity-taking authority, a Ukraine de-escalation headline compresses the defense premium, or a hyperscaler capex pause hits the grid names simultaneously.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| INTC | 10.0% | US government holds a ~10% CHIPS-tied equity stake worth ~$45B (Sept 13 2026) and revision_flow_90d shows net_raises +11 with median target change +22.9% | A court ruling against executive equity-taking authority or a Q3 print that fails to justify the +32% 21-day move |
| RHM.DE | 9.0% | German defense budget +30% YoY to ~$150bn in 2026 with Bernstein Buy PT EUR1,900 (Sept 18-21); Q3'26 results confirmed Nov 5 2026 | Q3 order intake misses or the analyst split resolves toward the MWB EUR1,050 bear case |
| GEV | 9.0% | Q2 2026 orders +88% organically to $24.2B with a $176B backlog and inflection_flag true; Bernstein Buy PT $1,298 (Sept 2026) | Backlog cancellation rate rises or a hyperscaler capex pause hits the 116GW turbine slot reservations |
| MP | 8.0% | DoD holds a ~15% as-converted stake plus a 10-year magnet offtake at a fixed price floor (Jul 2025 template), the purest Section 232 critical-minerals beneficiary | Section 232 negotiation resolves without price floors or the DoD offtake volume undershoots the fixed floor |
| SAAB-B.ST | 8.0% | European rearmament beneficiary with Q3'26 report confirmed Oct 23 2026 and a Gripen export pipeline | Q3 order bookings disappoint or a Ukraine de-escalation headline compresses the whole rearmament premium |
| KOG.OL | 8.0% | Nordic missile/defense systems demand with Q3'26 report confirmed Oct 29 2026 | Q3 margins miss on FX or a defense-budget pause in Norway |
| CCJ | 8.0% | Uranium term price hit a record $96/lb (Sept 10 2026) and BofA sees $130/lb in 2027; Q3'26 earnings Nov 3-4 2026 | Uranium spot rolls over or the production shortfall versus delivery commitments forces expensive purchases |
| HAG.DE | 7.0% | Order backlog above EUR10bn and book-to-bill 2.4x in H1, with 9-month 2026 results confirmed Nov 5 2026 | Negative free cash flow worsens beyond the seasonal pattern or backlog conversion slips |
| NVT | 7.0% | Q1 2026 sales +53% YoY, FY26 guide raised to 37-39% growth, inflection_flag true and net_raises +6 | The fall-2026 modular liquid-cooling launch slips or data-center sales fail to exceed $2B in 2026 |
| VRTX | 6.0% | Povetacicept BLA PDUFA Nov 30 2026 with net_raises +9 and zero lowers across 8 firms | A CRL on CMC/manufacturing grounds removes the first nephrology product leg |
| CASH | 6.0% | declared cash |  |
| LEU | 5.0% | Sole US HALEU producer with a finalized $900M DOE task order (July 2026) and 900kg delivered two weeks early | A non-DOE HALEU offtake fails to materialize or the 2029 capacity target slips |
| MRK | 5.0% | Ifinatamab deruxtecan PDUFA Oct 10 2026 with net_raises +22 across 17 firms and median target change +12.4% | A CRL on the Daiichi ADC manufacturing facility delays the franchise |
| TMQ | 4.0% | US government closed a 10% stake for $35.6M on Sept 14 2026 (Dept of War) backing the Ambler Metals JV in Alaska | Ambler Road federal permitting stalls or the stake terms are unwound |

**What it did not buy:** ALB|net_raises -12 with 12 lowers and no raises; lithium forecast cut 40%; SMR|net_raises -6, revenue -99% YoY, consensus Hold with stacked downgrades; OKLO|Zero revenue and a $55-$150 one-week analyst target dispersion; FLUT|net_raises -15 with 16 lowers and four 2026 guidance cuts; SERV|net_raises -3 with median target change -55.6% after a guidance cut; BYND|Meme-cluster spike with no fundamental news and -95% from 52-week high; QUBT|Operating expenses +114% YoY; $10-$32 analyst target dispersion; 2330.TW|Semis exposure already covered; no policy catalyst in the evidence


### pers_quality_momentum_2026-09-25 - book_id 101b75d7f1f78dd5

kind personal · frozen 2026-09-25T07:27:45+00:00 · 16 positions · max weight 8.9% · cash 5.4% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** Buy liquid quality-momentum: names with strong 6-12 month relative momentum, positive gross-margin change, and broad analyst net raises, concentrated in biotech PDUFA names with dated Q4 catalysts and in semis/power-grid where the AI capex chain still shows margin expansion. I avoid names far above their 200-day with falling margins (ALB, VRT, LEU, OKLO, SMR, FLUT) and unprofitable quantum/meme tickers. I would be wrong if a single AI-capex digestion headline hits the semis and power names together, or if several Q4 PDUFAs return CRLs, which the base rates say are 2-4x larger than approval pops. [factory: weights and cash rescaled from a stated total of 1.1200 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| NVDA | 8.9% | net_raises 16 of 16 firms across 21 and gross_margin_chg +0.0004 with mom_63 +9.1% | a hyperscaler capex digestion signal or gross margin guide cut |
| VRTX | 8.0% | net_raises 9 of 9 firms with median target +3.3% and mom_252_21 +39.5% on a large liquid book | povetacicept CRL or a Q3 miss on the Nov 30 PDUFA date |
| MRK | 8.0% | net_raises 22 with zero lowers across 17 firms and mom_252_21 +87% | I-DXd CRL on the Oct 10 PDUFA or Keytruda LOE guidance worsening |
| TSM | 8.0% | net_raises 6 of 6 firms with median target +10.2% and vs_ma200 +17.6% | a capex guidance cut at the Oct 15 Q3 earnings |
| GILD | 7.1% | mom_252_21 +28.6% with gross_margin_chg +0.0053 and drawdown_63 only -0.2% | anito-cel CRL on Dec 23 or further net target cuts beyond -3 |
| ASML | 7.1% | net_raises 5 of 5 firms with median target +13.6% and mom_252_21 +89.7% | an order cut or China restriction headline at the Oct 14 Q3 print |
| CORT | 6.2% | mom_252_21 +51.7% with gross_margin 98.4% and net_raises 4 of 4 firms | relacorilant resubmission rejected at the Dec 17 PDUFA |
| MU | 6.2% | inflection_flag true with gross_margin_chg +10.2pp and rev_yoy +346% | HBM pricing rolls over or the next print shows inventory building |
| AMD | 6.2% | net_raises 22 of 22 firms and mom_252_21 +197% with drawdown_63 at 0.0% | an AI accelerator order cut or gross margin guide below 54% |
| BBIO | 5.4% | net_raises 9 of 11 firms and rev_yoy +120% with gross_margin 93.8% | BBP-418 CRL at the Nov 27 PDUFA or a wider Q3 loss |
| GEV | 5.4% | inflection_flag true with net_raises 8 of 8 firms and gross_margin_chg +2.2pp | backlog cancellation or an AI data-center pause headline before Q3 |
| CASH | 5.4% | declared cash |  |
| SMMT | 4.5% | net_raises 1 with mom_21 +36% into the Nov 14 ivonescimab PDUFA | HARMONi OS data fails to show superiority and the BLA is rejected |
| TER | 4.5% | net_raises 6 of 6 firms with median target +13.6% and mom_252_21 +223% | the Oct 27 Q3 print shows robotics and test orders rolling over |
| NVT | 4.5% | inflection_flag true with net_raises 6 of 6 firms and gross_margin_chg +2.1pp | the fall liquid-cooling launch slips or data-center orders stall |
| AME | 4.5% | net_raises 12 of 12 firms with median target +6.7% and vol_63 only 23.9% | the $5B deal integration disappoints or Q3 organic growth stalls |

**What it did not buy:** ALB|net_raises -12 with mom_63 -27.7% and falling gross margin; VRT|net_raises -4 and mom_63 -29.9% despite AI narrative; LEU|net_raises -4 with median target change -12.9%; OKLO|net_raises -4 and zero revenue, pre-commercial story stock; SMR|net_raises -6 and rev_yoy -99%; FLUT|net_raises -15 with mom_252_21 -64.7%; IONQ|no revision data and mom_252_21 -37.8% with dilution risk; BYND|mom_252_21 -82.6% and pump-shaped with no fundamental news


### pers_retail_attention_contrarian_2026-09-25 - book_id 66433be8ce92d0f8

kind personal · frozen 2026-09-25T07:21:06+00:00 · 14 positions · max weight 8.9% · cash 5.9% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** I fade the retail-attention crowd: I avoid the names whose only evidence is a headline-count spike (IONQ, RGTX, QBTS, QUBT, RKLB, NBIS, BB, SNDT-style meme pops, BYND/DNUT/GPRO) and buy where the analyst flow is one-sided and dated catalysts sit inside the 126-session window. The book is Q4-2026 FDA decisions (VRTX, MRK, GILD, COGT, AGIO, BBIO) plus AI power/grid and semicap names with net_raises and inflection_flag true (GEV, NVT, TSM, ASML, MU, AME, WST). I am wrong if a CRL cluster or a single hyperscaler capex pause hits the power/semis sleeve at once, or if the PDUFA approvals are already priced in and sell the news.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| VRTX | 8.9% | net_raises 9 of 9 firms with median target +3.3% into Nov 30 povetacicept PDUFA (revision_flow_90d) | CRL on the povetacicept BLA on or before Nov 30 2026 |
| MRK | 8.9% | net_raises 22 with zero lowers across 17 firms into Oct 10 I-DXd PDUFA (revision_flow_90d) | I-DXd CRL on manufacturing grounds on Oct 10 2026 |
| GILD | 7.9% | rev_yoy +10.2% with drawdown_63 only -0.2% and Dec 23 anito-cel PDUFA (briefing) | anito-cel CRL or a guidance cut at the Q3 print in late Oct 2026 |
| GEV | 7.9% | inflection_flag true with net_raises 8 of 9 firms and rev_yoy +21.9% (briefing) | backlog cancellation or book-to-bill below 1.0 disclosed at the next report |
| TSM | 7.9% | net_raises 6 of 7 firms, median target +10.2%, into Oct 15 Q3 earnings (revision_flow_90d) | capex guide cut on the Oct 15 2026 earnings call |
| COGT | 6.9% | two PDUFAs Nov 30 and Dec 30 with net_raises 2 of 4 firms and no lowers (revision_flow_90d) | either bezuclastinib NDA rejected, first on Nov 30 2026 |
| AGIO | 6.9% | net_raises 5 of 6 firms, median target +9.7%, into Nov 1 mitapivat sickle cell PDUFA (revision_flow_90d) | mitapivat sNDA CRL on Nov 1 2026 |
| BBIO | 6.9% | net_raises 9 of 11 firms with rev_yoy +120% into Nov 27 BBP-418 PDUFA (revision_flow_90d) | BBP-418 CRL on Nov 27 2026 |
| NVT | 6.9% | inflection_flag true, rev_yoy +52.8%, net_raises 6 of 5 firms with no lowers (briefing) | the fall-2026 modular liquid-cooling launch slips past Dec 2026 |
| ASML | 6.9% | net_raises 5 of 5 firms, median target +13.6%, into Oct 14 Q3 earnings (revision_flow_90d) | 2027 order book guided down on Oct 14 2026 |
| MU | 6.9% | inflection_flag true with rev_yoy +346% and gross_margin_chg +10.2pp (briefing) | HBM pricing or allocation cut disclosed before the Dec 2026 print |
| AME | 5.9% | net_raises 12 of 10 firms with zero lowers and rev_yoy +15.0% (revision_flow_90d) | the $5B deal closes with FY27 margin guidance cut |
| CASH | 5.9% | declared cash |  |
| WST | 5.0% | net_raises 7 of 6 firms, median target +9.6%, on GLP-1 device demand (revision_flow_90d) | management flags GLP-1 device orders normalizing at the late-Oct print |

**What it did not buy:** IONQ|headline spike only, no revision_flow_90d data at all; QUBT|gross_margin -21% and $10-$32 target dispersion, attention-only; RGTI|no revision_flow signal, pure quantum sentiment beta; QBTS|rev_yoy -0.6% and no analyst revision flow; RKLB|mention surge with no dated catalyst found; NBIS|+160% mention surge, no dated catalyst, beta 5.0; FLUT|net_raises -15, sixteen lowers, four guidance cuts; ALB|net_raises -12 with twelve lowers, lithium price cut


### pers_revision_flow_leaders_2026-09-25 - book_id 784d2831c530f113

kind personal · frozen 2026-09-25T07:27:14+00:00 · 15 positions · max weight 9.0% · cash 5.0% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** Buy the names where the 90-day analyst revision flow is most one-sidedly positive across many distinct firms, not the names with the biggest target upside. The bet is that broad, firm-diverse net raises (OKTA 63/32 firms, SNOW 47/33, CRWD 44/35, PANW 34/30, CRM 33/29) reflect real estimate momentum that persists over 126 sessions. I would be wrong if the flow reverses: any name printing a net-lower revision cluster, a guidance cut, or a momentum break gets cut, since the whole edge is the flow, not the level.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| OKTA | 9.0% | net_raises 63 across 32 firms with zero lowers (revision_flow_90d) | any net-lower print or momentum reversal before the next earnings date |
| SNOW | 8.0% | net_raises 47 across 33 firms, zero lowers (revision_flow_90d) | a single net-negative revision week or a data-cloud consumption guide cut |
| CRWD | 8.0% | net_raises 44 across 35 firms (revision_flow_90d) with price at 52w high | a net-lower revision cluster or a billings deceleration headline |
| PANW | 7.0% | net_raises 34 across 30 firms, zero lowers (revision_flow_90d) | any guidance cut or net-lower revision before the next print |
| CRM | 7.0% | net_raises 33 across 29 firms (revision_flow_90d) with mom_63 0.58 | a net-negative revision week or an agent-monetization disappointment |
| TGT | 7.0% | net_raises 30 across 19 firms, zero lowers (revision_flow_90d) | a net-lower revision or a gross-margin reversal in the next report |
| ABNB | 7.0% | net_raises 28 across 29 firms and inflection_flag true (briefing) | a net-lower revision cluster or a nights-booked guide cut |
| NET | 6.0% | net_raises 27 across 19 firms, zero lowers (revision_flow_90d) | a net-lower revision or a large-enterprise deal slippage headline |
| AFRM | 6.0% | net_raises 27 across 23 firms, zero lowers (revision_flow_90d) | a net-lower revision or a funding-cost/credit deterioration headline |
| AMGN | 6.0% | net_raises 26 across 22 firms and inflection_flag true (briefing) | a net-lower revision cluster or a MariTide timeline slip |
| DELL | 6.0% | net_raises 24 across 18 firms, zero lowers (revision_flow_90d) | a net-lower revision or an AI-server backlog decline |
| DT | 6.0% | net_raises 23 across 18 firms, zero lowers (revision_flow_90d) | a net-lower revision or an ARR growth deceleration |
| S | 6.0% | net_raises 23 across 20 firms, zero lowers (revision_flow_90d) | a net-lower revision or a net-retention miss |
| FTNT | 6.0% | net_raises 23 across 17 firms, zero lowers (revision_flow_90d) | a net-lower revision or a billings guide cut |
| CASH | 5.0% | declared cash |  |

**What it did not buy:** ALB|net_raises -12, twelve lowers, no raises; FLUT|net_raises -15, sixteen lowers, no flow support; SMR|net_raises -6, revenue collapsing, no raises; OKLO|net_raises -4, pre-revenue story stock, no raises; LEU|net_raises -4, six lowers, flow negative; CEG|net_raises -6, seven lowers, flow negative; VRT|net_raises -4, four lowers, zero raises; GILD|net_raises -3, six lowers, flow negative


### pers_small_cap_catalyst_2026-09-25 - book_id a5e835dd553d7071

kind personal · frozen 2026-09-25T07:28:03+00:00 · 15 positions · max weight 9.1% · cash 9.1% · benchmark SPY · horizons [1, 5, 21, 126]  
**Objective:** maximise 126-session return vs SPY, net of costs  
**Model:** deepseek-flash

**Strategy:** Concentrate in small/mid-cap biotech with primary-sourced Q4 2026 PDUFA dates, where the evidence shows dated catalysts and positive revision flow (net_raises) rather than narrative. AGIO, COGT, BBIO, SVRA, INSM, VRTX, MRK, CORT, PRAX and SMMT all carry hand-verified FDA decisions between Oct 10 and Jan 28, and WST, RGEN, VKTX and DHR add dated earnings or data inside the window. I would be wrong if the CRL tail materializes on several of these names at once, if the Section 232 pharma tariff go-live on Sep 29 hits unshielded names like VRTX, or if small-cap risk appetite collapses and the whole sleeve de-rates regardless of the binary outcomes. [factory: weights and cash rescaled from a stated total of 1.1000 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| CASH | 9.1% | declared cash |  |
| AGIO | 8.2% | net_raises 5 of 6 firms with median target change +9.7% into Nov 1 mitapivat sickle-cell PDUFA | CRL or narrow all-genotype label on Nov 1 |
| COGT | 8.2% | two primary-sourced PDUFAs Nov 30 and Dec 30 with Wedbush Outperform reiterated Sep 16 | either bezuclastinib NDA gets a CRL in Nov or Dec |
| VRTX | 8.2% | net_raises 9 with zero lowers across 8 firms into Nov 30 povetacicept PDUFA | CRL on povetacicept on Nov 30 |
| BBIO | 7.3% | net_raises 9 with 11 firms and median target change +4.1% into Nov 27 BBP-418 PDUFA | CRL on BBP-418 on Nov 27 |
| MRK | 7.3% | net_raises 22 with 17 firms and median target change +12.4% into Oct 10 I-DXd PDUFA | CRL on I-DXd on Oct 10 |
| SVRA | 6.4% | PDUFA Nov 22 extended 3 months with FDA disclaiming safety/efficacy/manufacturing concerns | CRL on molgramostim on Nov 22 |
| INSM | 6.4% | ARIKAYCE sNDA PDUFA Jan 28 2027 filed Sep 21 with label-expansion base rate | CRL or delay on the ENCORE sNDA |
| CORT | 6.4% | net_raises 4 with zero lowers and rev_qoq +55% into Dec 17 relacorilant resubmission | second CRL on relacorilant on Dec 17 |
| WST | 6.4% | net_raises 7 with zero lowers and GLP-1 delivery-device guidance raised twice | Q3 organic growth decelerates below high-teens in late Oct |
| DHR | 6.4% | Goldman raised target to $250 Sep 22 with Q3 earnings Oct 20 | Q3 core biotech growth stays below 4% on Oct 20 |
| PRAX | 5.5% | net_raises 5 with zero lowers into Dec 27 relutrigine PDUFA after major-amendment extension | CRL on relutrigine on Dec 27 |
| RGEN | 5.5% | net_raises 4 with zero lowers and bioprocessing recovery beats in Q1 and Q2 | Q3 core growth turns negative in late Oct |
| SMMT | 4.5% | PDUFA Nov 14 ivonescimab BLA with HARMONi OS data at WCLC Sep 15 | CRL on ivonescimab on Nov 14 |
| VKTX | 4.5% | Sep 22 positive Phase 1 maintenance-dosing data with oral Phase 3 starting Q4 2026 | oral VK2735 Phase 3 start slips past Q4 2026 |

**What it did not buy:** CAPR|9-of-12 negative adcom vote and vol_63 2.14; ALB|net_raises -12 with 12 lowers and lithium price cuts; FLUT|net_raises -15 with 16 lowers and four 2026 guidance cuts; SMR|net_raises -6 with 6 lowers and revenue down 99% YoY; OKLO|zero revenue with analyst targets dispersed $55 to $150; QUBT|opex +114% YoY and analyst targets dispersed $10 to $32; SERV|net_raises -3 with 3 lowers and 2026 guidance cut; NVO|net_raises 0 and mom_252_21 -22.9%


## Factory books - competition (comp_*, 10)


### comp_ai_power_global_2026-09-25 - book_id b23cf2a9aee04289

kind competition · frozen 2026-09-25T07:28:55+00:00 · 21 positions · max weight 7.0% · cash 1.6% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Bet that the AI-capex bottleneck is physical: power generation, grid gear, cooling, transformers, turbines and the memory/HBM that the build-out consumes, plus defense and gambling names with confirmed in-window prints. Every holding has a dated observable (earnings, Tech Day, PDUFA) between Oct 12 and Nov 13, so relative P&L is driven by real reports rather than theme momentum. I would be wrong if a hyperscaler capex-digestion headline, a China export-control shock, or a de-escalation in defense risk premia hits the whole book at once, or if ASML/TSM guide capex down on Oct 14-15. [factory: weights and cash rescaled from a stated total of 1.2800 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| GEV | 7.0% | Q2 orders +88% to $24.2B and $176B backlog (research_themes) | Q3 order growth decelerates below 20% when reported |
| VRT | 6.3% | $2.6B Utility Innovations deal Sep 3 extends grid-to-chip (research_themes) | Q3 backlog growth stalls or deal integration slips in late Oct |
| NVT | 6.3% | Q1 sales +53% YoY and FY26 guide raised to 37-39% (research_themes) | Fall-2026 modular liquid-cooling launch slips past Nov 13 |
| ASML | 6.3% | Q3'26 earnings confirmed Oct 14, 2026 (catalysts) | Order intake or 2027 guidance cut on Oct 14 |
| TSM | 6.3% | Q3'26 earnings confirmed Oct 15 before open (catalysts) | Capex guide cut or gross margin below 65% on Oct 15 |
| MU | 6.3% | HBM4 shortage with ~20% of NVIDIA allocation (research_themes) | HBM pricing or allocation commentary weakens at next print |
| AMD | 5.5% | 22 net raises over 90 days, median target +13.4% (revision_flow_90d) | MI-series AI revenue guide disappoints at next earnings |
| NVDA | 5.5% | 16 net raises from 21 firms, median target +5% (revision_flow_90d) | Hyperscaler capex pause headline before Nov 13 |
| DELL | 4.7% | 24 net raises, median target +11.4%, rev_yoy +57.8% (revision_flow_90d) | AI server order backlog commentary weakens at next print |
| TER | 4.7% | Q3'26 earnings confirmed Oct 27 after close (catalysts) | Robotics segment growth falls below 33% on Oct 27 |
| MRK | 4.7% | 22 net raises from 17 firms, median target +12.4% (revision_flow_90d) | I-DXd CRL on manufacturing on Oct 10 |
| ARGX | 3.9% | 17 net raises from 14 firms, median target +6.2% (revision_flow_90d) | EMPASSION Phase 3 MMN topline misses in Q4 |
| CCJ | 3.9% | Q3'26 earnings Nov 3-4 confirmed by multiple sources (catalysts) | Uranium spot or contract pricing rolls over before Nov 3 |
| SAAB-B.ST | 3.9% | Q3'26 report confirmed Oct 23, 2026 (catalysts) | Gripen order pipeline stalls or margin guide cut on Oct 23 |
| RHM.DE | 3.9% | Q3'26 results confirmed Nov 5, 2026 (catalysts) | Order intake misses or 2026 guidance trimmed on Nov 5 |
| KOG.OL | 3.9% | Q3'26 report confirmed Oct 29, 2026 (catalysts) | Missile/defense order intake disappoints on Oct 29 |
| EVO.ST | 3.9% | Q3'26 report confirmed Oct 23, 2026 (catalysts) | Asia revenue decline accelerates on Oct 23 |
| ALL.AX | 3.9% | FY26 annual results confirmed Nov 12, 2026 (catalysts) | Anaxi/digital growth misses FY26 consensus on Nov 12 |
| 2317.TW | 3.9% | Hon Hai Tech Day confirmed Oct 30-31, 2026 (catalysts) | AI server rack guidance disappoints at Tech Day |
| 2330.TW | 3.9% | Q3'26 earnings Oct 15, also TSM ADR (catalysts) | Monthly sales or capex commentary weakens in October |
| CASH | 1.6% | declared cash |  |

**What it did not buy:** ALB|12 net lowers, lithium spot falling, no dated catalyst; OKLO|Zero revenue, analyst targets dispersed $55-$150; SMR|Six net lowers, revenue collapsed, consensus Hold; LEU|Six lowers vs two raises, median target -12.9%; FLUT|16 lowers vs 1 raise, down 69% from peak; NVO|Morgan Stanley Sell, CagriSema missed non-inferiority vs tirzepatide; SERV|Guidance cut, three lowers, median target -55.6%; QUBT|Opex +114% YoY, $10-$32 target dispersion, no dated catalyst


### comp_asia_supply_chain_2026-09-25 - book_id 2c606bb5b74479c4

kind competition · frozen 2026-09-25T07:24:31+00:00 · 13 positions · max weight 9.8% · cash 2.0% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Bet that the AI capex chain's Q3 prints (Oct 14 ASML through early Nov) surprise up across Taiwan foundry/ODM, Korean memory and Japanese semicap, all of which report inside the Oct 12-Nov 13 window. Every name has a dated catalyst, so relative P&L is driven by real numbers, not theme drift. I would be wrong if a single hyperscaler capex-digestion headline, a China export-control action, or an HBM4 ramp disappointment hits the whole correlated stack at once - this book is one factor wearing twelve tickers' clothing.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| 2330.TW | 9.8% | Q3'26 earnings Oct 15 (catalysts) with capex guide raised to $60-64B per research_global_candidates | Oct 15 capex guide cut or CoWoS capacity-easing signal |
| 000660.KS | 9.8% | HBM leader with record Q3 op profit ~KRW78.1tn consensus per research_global_candidates | Bernstein Sept 22 HBM4 ramp-lag vs Samsung confirmed in Q3 print |
| 005930.KS | 8.8% | Bernstein Sept 22 raised Q3 HBM revenue est 23% to ~$11.4bn per research_global_candidates | Q3 HBM4 mix or foundry profitability misses the raised bar |
| 8035.T | 8.8% | FY26 Q2 results late Oct (research_global_candidates) on WFE spend cycle | China export-control headline or order pushout in FY26 Q2 print |
| 6857.T | 8.8% | FY26 sales guide raised +21% to JPY1,714bn Jul 29 (research_global_candidates) | AI test order lumpiness shows in late-Oct FY26 Q2 results |
| ASML | 8.8% | Q3'26 earnings Oct 14 confirmed (catalysts) after Q2 guided Q3 rev $12.8-14.0bn | Oct 14 order bookings or 2027 guidance disappoint vs the raised bar |
| 2317.TW | 8.8% | Hon Hai Tech Day Oct 30-31 confirmed (catalysts); Aug revenue +52% YoY record | Tech Day reveals no new AI server rack content or Q3 margin dilutes |
| 2308.TW | 7.8% | Liquid-cooling/800V DC power leader for AI infra per research_global_candidates | Component cost inflation (T-glass, substrates) compresses Q3 margin |
| 6669.TW | 7.8% | Hyperscaler direct AI server ODM exposure per research_global_candidates | Q3 earnings early Nov show customer concentration or margin miss |
| 6146.T | 6.9% | FY26 Q2 results late Oct (research_global_candidates) on HBM dicing/grinding demand | China capex slowdown hits advanced-packaging dicing orders |
| 6920.T | 5.9% | FY27 Q1 results late Oct (research_global_candidates) on EUV mask-inspection monopoly | Lumpy order book produces a guidance cut in the late-Oct print |
| 2454.TW | 5.9% | Won Google TPU-related order in 2026 per research_global_candidates | Smartphone SoC pricing pressure offsets AI ASIC design-win narrative |
| CASH | 2.0% | declared cash |  |

**What it did not buy:** NVDA|US mega-cap, not Asia supply chain, and no dated in-window print; MU|Already crowded WSB name; memory cycle risk overlaps SK Hynix; TSM|Same exposure as 2330.TW but ADR, no incremental edge; AMKR|Arizona ramp is 2026-2030, no clean in-window catalyst; TER|Q3 Oct 27 confirmed but robotics segment too small vs semi-test cycle; VRT|US power name, revision flow net -4, outside Asia mandate; GEV|US power name, outside Asia supply-chain mandate; IONQ|Quantum, no dated in-window catalyst, extreme dilution risk


### comp_catalyst_calendar_2026-09-25 - book_id 4a3864b2140550ce

kind competition · frozen 2026-09-25T07:29:15+00:00 · 26 positions · max weight 5.8% · cash 1.3% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Own only names with a dated catalyst inside Oct 12-Nov 13, 2026, plus a tail of late-Nov/Dec PDUFAs whose run-up window overlaps the contest. Dates are spread across the calendar (Oct 14, 15, 22, 23, 27, 29, 30; Nov 1, 3, 4, 5, 12) so no single print decides the book, and themes are diversified across semicap, defense, gambling, nuclear and biotech. I am wrong if a macro shock or a single hyperscaler capex pause hits the semis/defense cluster at once, or if the PDUFA tail produces clustered CRLs (approvals are largely priced in pre-date, CRLs are not). [factory: weights and cash rescaled from a stated total of 1.5600 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| ASML | 5.8% | Q3'26 earnings Oct 14 (catalysts) with net_raises 5 of 5 firms (revision_flow_90d) | Q3 bookings miss or 2027 guidance cut on Oct 14 |
| TSM | 5.8% | Q3'26 earnings Oct 15 (catalysts) with net_raises 6 of 6 firms (revision_flow_90d) | capex guide cut or gross margin below 65% on Oct 15 |
| ARGX | 5.1% | Q3'26 results Oct 22 (catalysts) with net_raises 17 of 18 firms (revision_flow_90d) | EMPASSION MMN topline slips or misses in Q4 window |
| SAAB-B.ST | 5.1% | Saab Q3'26 report Oct 23 (catalysts) | Q3 order intake falls below prior-year run-rate on Oct 23 |
| EVO.ST | 5.1% | Evolution AB Q3'26 report Oct 23 (catalysts) | Asia revenue declines again or new regulatory action disclosed Oct 23 |
| TER | 5.1% | Q3'26 earnings Oct 27 after close (catalysts) with net_raises 6 of 6 firms (revision_flow_90d) | robotics segment growth decelerates below 20% in the Oct 27 print |
| KOG.OL | 5.1% | Kongsberg Gruppen Q3'26 report Oct 29 (catalysts) | missile/defense order backlog growth stalls on Oct 29 |
| 2317.TW | 4.5% | Hon Hai Tech Day Oct 30-31 (catalysts) | AI server guidance disappoints at Tech Day Oct 30 |
| AGIO | 4.5% | mitapivat sickle cell PDUFA Nov 1 (catalysts) with net_raises 5 of 7 firms (revision_flow_90d) | CRL or narrow all-genotype label exclusion on Nov 1 |
| CCJ | 4.5% | Cameco Q3'26 earnings Nov 3-4 (catalysts) | production or contract-mix guidance cut on Nov 3 |
| NVO | 4.5% | Novo Nordisk Q3'26 results Nov 4 (catalysts) | CagriSema US obesity decision slips past Q4 on Nov 4 |
| RHM.DE | 3.8% | Rheinmetall Q3'26 results Nov 5 (catalysts) | order intake or FY guidance disappoints on Nov 5 |
| HAG.DE | 3.8% | Hensoldt 9-month 2026 results Nov 5 (catalysts) | book-to-bill falls below 1.5x on Nov 5 |
| ALL.AX | 3.8% | Aristocrat FY26 annual results Nov 12 (catalysts) | Anaxi/digital growth misses FY26 consensus on Nov 12 |
| SMMT | 3.2% | ivonescimab BLA PDUFA Nov 14 (catalysts) with net_raises 1 net of lowers (revision_flow_90d) | CRL or FDA request for more OS data on Nov 14 |
| CAPR | 3.2% | deramiocel BLA PDUFA Nov 22 (catalysts) | CRL after the 9-of-12 negative adcom vote on Nov 22 |
| SVRA | 3.2% | molgramostim BLA PDUFA Nov 22 (catalysts) | CMC or manufacturing CRL on Nov 22 |
| BBIO | 3.2% | BBP-418 NDA PDUFA Nov 27 (catalysts) with net_raises 9 of 10 firms (revision_flow_90d) | CRL on LGMD2I/R9 filing on Nov 27 |
| NUVL | 3.2% | neladalkib NDA PDUFA Nov 27 (catalysts) | CRL on TKI-pretreated ALK+ NSCLC on Nov 27 |
| VRTX | 3.2% | povetacicept BLA PDUFA Nov 30 (catalysts) with net_raises 9 of 9 firms (revision_flow_90d) | CRL on accelerated-approval CMC grounds on Nov 30 |
| COGT | 3.2% | bezuclastinib GIST PDUFA Nov 30 (catalysts) with net_raises 2 of 2 firms (revision_flow_90d) | CRL on the GIST NDA on Nov 30 |
| CORT | 2.6% | relacorilant NDA resubmission PDUFA Dec 17 (catalysts) with net_raises 4 of 4 firms (revision_flow_90d) | second CRL after the Dec 2025 rejection on Dec 17 |
| GILD | 2.6% | anito-cel BLA PDUFA Dec 23 (catalysts) | CMC or facility-inspection CRL on Dec 23 |
| PRAX | 2.6% | relutrigine NDA PDUFA Dec 27 (catalysts) with net_raises 5 of 5 firms (revision_flow_90d) | CRL after the major-amendment extension on Dec 27 |
| MLYS | 1.9% | lorundrostat NDA PDUFA Dec 22 (catalysts) | CRL on uncontrolled/resistant hypertension on Dec 22 |
| CASH | 1.3% | declared cash |  |

**What it did not buy:** NVDA|no dated catalyst in the window; MU|no dated catalyst in the window; ALB|net_raises -12, no catalyst date; OKLO|net_raises -4, no dated catalyst; SMR|net_raises -6, no dated catalyst; FLUT|net_raises -15 of 16 lowers; ORCL|net_raises -5, no dated catalyst; VRT|net_raises -4, no dated catalyst


### comp_ensemble_2026-09-25 - book_id f1365ea29aeb1be2

kind competition · frozen 2026-09-25T07:30:41+00:00 · 23 positions · max weight 6.4% · cash 1.4% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Only names at least two independent lenses would pick: semis where revision flow (net raises) and the confirmed Oct 14-15 earnings calendar overlap (ASML, TSM, NVDA, MU, AMD, INTC, 2317.TW); power/grid where the briefing inflection flag and backlog growth overlap (GEV, NVT); pharma where net raises and dated PDUFA/readout catalysts overlap (MRK, LLY, AMGN, ABBV, WST, ARGX); uranium/defense/gambling where confirmed in-window earnings dates overlap sector momentum (CCJ, RHM.DE, SAAB-B.ST, KOG.OL, HAG.DE, EVO.ST, ALL.AX). I would be wrong if a single macro shock (hyperscaler capex digestion, China export controls, or a de-escalation headline) hits the correlated semis and defense sleeves at once. [factory: weights and cash rescaled from a stated total of 1.4100 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| ASML | 6.4% | Q3'26 earnings confirmed Oct 14 (catalysts) plus net_raises 5/5 firms (revision_flow_90d) | Order intake or 2027 guidance cut on the Oct 14 print |
| TSM | 6.4% | Q3'26 earnings Oct 15 (catalysts) with net_raises 6/6 and mom_252_21 +0.558 (revision_flow_90d) | Capex guide cut or gross margin below 60% on Oct 15 |
| NVDA | 6.4% | net_raises 16 with 21 firms and rev_yoy +1.06 (revision_flow_90d) | Any hyperscaler capex digestion headline before Nov 13 |
| MU | 5.7% | inflection_flag true with rev_qoq +0.74 and gross_margin_chg +0.10 (briefing) | HBM pricing or DRAM inventory data turning negative in October |
| AMD | 5.7% | net_raises 22 with 27 firms and mom_21 +0.311 (revision_flow_90d) | Any AI accelerator order pushout or guide cut before Nov 13 |
| GEV | 5.7% | inflection_flag true with rev_yoy +0.219 and net_raises 8/9 (briefing) | Backlog cancellation or book-to-bill below 1.0 in the Q3 print |
| INTC | 5.0% | net_raises 11 with 20 firms and mom_21 +0.322 (revision_flow_90d) | Adverse ruling in the shareholder lawsuit over the government equity stake |
| NVT | 5.0% | inflection_flag true with rev_yoy +0.528 and net_raises 6/6 (briefing) | Fall-2026 liquid-cooling launch slips past November |
| MRK | 5.0% | net_raises 22 with 17 firms and PDUFA Oct 10 (revision_flow_90d) | CRL on the I-DXd BLA on Oct 10 |
| LLY | 5.0% | inflection_flag true with rev_yoy +0.477 and net_raises 13/14 (briefing) | Retatrutide tolerability disappoints at EASD or the Q1 2027 filing slips |
| AMGN | 4.3% | inflection_flag true with net_raises 26 with 22 firms (briefing) | MariTide Phase 3 timing slips past the book window |
| ABBV | 4.3% | net_raises 20 with 21 firms and vs_52w_high -0.011 (revision_flow_90d) | Immunology franchise guidance cut before Nov 13 |
| WST | 4.3% | net_raises 7 with 6 firms and vs_ma200 +0.216 (revision_flow_90d) | GLP-1 device orders normalize below high-teens growth |
| ARGX | 4.3% | net_raises 17 with 14 firms and Q3'26 results Oct 22 (revision_flow_90d) | EMPASSION Phase 3 topline miss in Q4 2026 |
| CCJ | 3.5% | Q3'26 earnings Nov 3-4 (catalysts) with uranium term-price strength | Production guidance cut or uranium spot breaking below $80/lb |
| RHM.DE | 3.5% | Q3'26 results Nov 5 confirmed (catalysts) with Bernstein Buy EUR1,900 | Order intake miss or German budget headline reversal before Nov 5 |
| SAAB-B.ST | 3.5% | Q3'26 report Oct 23 confirmed (catalysts) | Gripen export pipeline delay disclosed on Oct 23 |
| KOG.OL | 3.5% | Q3'26 report Oct 29 confirmed (catalysts) | Missile/defense order intake miss on Oct 29 |
| HAG.DE | 2.8% | 9-month 2026 results Nov 5 confirmed (catalysts) | Negative free cash flow worse than seasonal on Nov 5 |
| EVO.ST | 2.8% | Q3'26 report Oct 23 confirmed (catalysts) | Asia revenue decline accelerating on Oct 23 |
| ALL.AX | 2.8% | FY26 annual results Nov 12 confirmed (catalysts) | Anaxi/digital growth miss on Nov 12 |
| 2317.TW | 2.8% | Hon Hai Tech Day Oct 30-31 confirmed (catalysts) | AI server rack order guidance cut at Tech Day |
| CASH | 1.4% | declared cash |  |

**What it did not buy:** FLUT|net_raises -15 with 16 lowers and four 2026 guidance cuts; VRT|net_raises -4 with 4 lowers and mom_63 -0.299; SMR|net_raises -6 with 6 lowers and rev_yoy -0.99; OKLO|net_raises -4 with 4 lowers and no revenue; ALB|net_raises -12 with 12 lowers and lithium price cut; NVO|Hold/Sell-leaning after REDEFINE 4 non-inferiority failure; SERV|net_raises -3 with 3 lowers and guidance cut; GME|meme rally with no fundamental news hook


### comp_pharma_binary_basket_2026-09-25 - book_id e781e41e79e56323

kind competition · frozen 2026-09-25T07:23:48+00:00 · 19 positions · max weight 9.0% · cash 2.0% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Own the dated Oct-Dec 2026 FDA calendar: large-cap pharma ballast (MRK, VRTX, LLY, ABBV, AMGN, GILD, REGN, ARGX) funded by 90-day net-raise breadth, plus small-cap PDUFA binaries sized at 3-5% each because a CRL averages -33% over five days while approvals are largely priced in by the pre-date run-up. Catalyst dates, not narratives, drive relative P&L in a five-week window. I would be wrong if a cluster of CRLs hits the binary sleeve simultaneously, if a Section 232 pharma tariff headline lands Sept 29, or if the large-cap prints sell off on the news despite beats.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| MRK | 9.0% | 22 net target raises over 90d and Oct 10 I-DXd PDUFA (revision_flow_90d, catalysts) | CRL on the I-DXd BLA announced on or before Oct 10 |
| VRTX | 8.0% | 9-for-9 net raises and Nov 30 povetacicept PDUFA (revision_flow_90d, catalysts) | CRL on povetacicept BLA on or before Nov 30 |
| LLY | 8.0% | 13 net raises and inflection_flag true with rev_yoy 0.4767 (briefing, revision_flow_90d) | Retatrutide filing slips past Q1 2027 or Q3 print cuts guidance |
| ABBV | 7.0% | 20 net raises with zero lowers over 90d (revision_flow_90d) | Q3 print shows Skyzima/Rinvoq erosion steeper than guided |
| AMGN | 7.0% | 26 net raises and inflection_flag true (revision_flow_90d, briefing) | MariTide MARITIME readout slips past Jan 21 2027 or Q3 misses |
| GILD | 6.0% | Dec 23 anito-cel PDUFA with 845.8M dollar_vol (catalysts, briefing) | CRL or facility-inspection finding on the anito-cel BLA |
| REGN | 6.0% | November cemdisiran+pozelimab PDUFA month (catalysts) | Manufacturing-inspection delay pushes the gMG NDA past November |
| ARGX | 6.0% | 17 net raises over 90d and Oct 22 Q3 earnings (revision_flow_90d, catalysts) | EMPASSION MMN Phase 3 topline misses in Q4 2026 |
| AGIO | 5.0% | Nov 1 mitapivat sickle-cell PDUFA with 5 net raises (catalysts, revision_flow_90d) | FDA grants only a narrow genotype label or issues a CRL Nov 1 |
| COGT | 5.0% | Two bezuclastinib NDAs Nov 30 and Dec 30 (catalysts) | Either bezuclastinib NDA draws a CRL on Nov 30 or Dec 30 |
| PRAX | 5.0% | Dec 27 relutrigine PDUFA with 5 net raises (catalysts, revision_flow_90d) | Major-amendment review ends in CRL on Dec 27 |
| WST | 5.0% | 7 net raises and vs_ma200 0.2156 on GLP-1 device demand (revision_flow_90d, briefing) | Late-Oct earnings show GLP-1 device orders decelerating |
| SMMT | 4.0% | Nov 14 ivonescimab BLA PDUFA (catalysts) | CRL or FDA request for more OS data on Nov 14 |
| BBIO | 4.0% | Nov 27 BBP-418 PDUFA with 9 net raises (catalysts, revision_flow_90d) | CRL on the BBP-418 NDA on Nov 27 |
| RGEN | 4.0% | 4 net raises and mom_63 0.4277 bioprocessing recovery (revision_flow_90d, briefing) | Oct 27/Nov 3 print shows order recovery stalling |
| SVRA | 3.0% | Nov 22 molgramostim PDUFA extended 3 months (catalysts) | Inhaled-biologic CMC finding yields a CRL on Nov 22 |
| INSM | 3.0% | Jan 28 ARIKAYCE sNDA with rev_yoy 2.9611 (catalysts, briefing) | ENCORE sNDA CRL on Jan 28 or Q3 revenue miss |
| CAPR | 3.0% | Nov 22 deramiocel PDUFA after 3-for-9 adcom (catalysts) | FDA rejects the narrower upper-limb label on Nov 22 |
| CASH | 2.0% | declared cash |  |

**What it did not buy:** NVO|Street Hold/Sell-leaning after REDEFINE 4 non-inferiority failure; ALB|12 net target cuts and lithium spot down 16% in a month; FLUT|15 net target cuts and four 2026 guidance cuts; SMR|6 net target cuts and revenue down 99% YoY; OKLO|4 net target cuts and zero revenue pre-commercial; LEU|6 net target cuts and gross margin down 12.7pp; VRT|4 net target cuts and mom_63 -0.299; QUBT|$10-$32 target dispersion and widening cash opex


### comp_policy_geopolitics_2026-09-25 - book_id ae32ba0af99ce972

kind competition · frozen 2026-09-25T07:29:52+00:00 · 18 positions · max weight 7.0% · cash 1.6% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Bet that the fastest-moving policy variables in the Oct 12-Nov 13 window are defense rearmament (German budget +30% YoY), US government equity stakes in critical minerals and chips (Intel/MP/Trilogy template), nuclear fuel security, and the AI power-grid bottleneck - expressed through names with confirmed earnings or events inside the window. I am wrong if a de-escalation headline (Ukraine ceasefire progress, US-China trade detente) compresses the geopolitical risk premium, if the Intel equity-stake lawsuit produces an adverse ruling hitting every government-stake name at once, or if a hyperscaler capex digestion quarter breaks the power-grid and semis legs simultaneously. [factory: weights and cash rescaled from a stated total of 1.2800 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| RHM.DE | 7.0% | Bernstein reiterated Buy PT EUR1,900 (Sept 18-21) into Q3'26 results Nov 5 (catalysts) | Q3 order intake misses and PT dispersion widens below EUR1,300 |
| GEV | 7.0% | inflection_flag true with Q2 orders +88% to $24.2B and $176B backlog (research) | Backlog cancellation or book-to-bill below 1 on hyperscaler capex pause |
| HAG.DE | 6.2% | 9-month 2026 results Nov 5 (catalysts) with book-to-bill 2.4x H1 per research | Negative free cash flow worsens at the Nov 5 print |
| SAAB-B.ST | 6.2% | Q3'26 report Oct 23 (catalysts) on Gripen export pipeline | Q3 order bookings fall short of rearmament run-rate on Oct 23 |
| KOG.OL | 6.2% | Q3'26 report Oct 29 (catalysts) on missile/defense order visibility | Q3 margin or order intake disappoints on Oct 29 |
| INTC | 6.2% | 10% US government stake now worth ~$45B (Sept 13, 2026) plus 11 net raises in revision_flow_90d | Adverse ruling in the shareholder lawsuit against the CHIPS-tied equity taking |
| CCJ | 6.2% | Q3'26 earnings Nov 3-4 (catalysts) with BofA uranium $130/lb 2027 forecast | Production stays below delivery commitments and term contracting stalls |
| NVT | 6.2% | inflection_flag true, Q1 sales +53% and FY guide raised to 37-39% (research) | Fall-2026 modular liquid-cooling launch slips past the window |
| TSM | 6.2% | Q3'26 earnings Oct 15 (catalysts) after FY26 capex guide raised to $60-64B | Capex guidance cut or gross margin misses 65-67% guide on Oct 15 |
| 012450.KS | 5.5% | Q3'26 report early Nov (research) after Q3'25 sales +147% YoY comp | Q3 YoY growth turns negative versus the record 2025 comp |
| MP | 5.5% | ~15% as-converted government stake plus 10-yr DoD magnet offtake at fixed floor (research) | Magnet offtake volumes undershoot the fixed-price floor commitment |
| 267260.KS | 5.5% | Q3'26 report mid-Nov (research) on 765kV transformer export boom to US grid | US tariff action or Q3 order slowdown hits transformer exports |
| ASML | 5.5% | Q3'26 earnings Oct 14 (catalysts) with 5 net raises in revision_flow_90d | Q3 bookings miss and 2027 guidance is cut on Oct 14 |
| TMQ | 4.7% | US government closed 10% stake for $35.6M on Sept 14, 2026 (research) | Ambler Road federal permitting stalls or is reversed |
| LEU | 4.7% | $900M DOE task order finalized July 2026, total $1.07B contract (research) | No non-DOE HALEU offtake signed from SMR developers by year-end |
| 2330.TW | 4.7% | Same Oct 15 Q3'26 earnings as TSM (catalysts), local-line exposure | Taiwan geopolitical shock or CoWoS capacity-easing signal |
| 2317.TW | 4.7% | Hon Hai Tech Day Oct 30-31 (catalysts) with Aug revenue +52% YoY record | Tech Day reveals no new AI server rack ramp and Q3 misses Street |
| CASH | 1.6% | declared cash |  |

**What it did not buy:** FLUT|16 target cuts in 90 days, four 2026 guidance cuts; SMR|Six net lowers and revenue down 99% YoY; OKLO|Zero revenue, analyst targets dispersed $55-$150; ALB|Twelve net target cuts, lithium price forecast cut 40%; VRT|Four net target cuts, negative skew, no dated catalyst; ORCL|Eight net lowers, data-center force-majeure headline Sept 24; LAC|No catalyst, 71% below 52-week high, thin liquidity; SERV|Guidance cut on Uber Eats volumes, three net lowers


### comp_quality_momentum_2026-09-25 - book_id a0ab004a8709c745

kind competition · frozen 2026-09-25T07:30:13+00:00 · 23 positions · max weight 6.8% · cash 1.7% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Bet on liquid global quality-momentum: semis/memory with rising gross margins (MU, NVDA, TSM, AMD, ASML, AVGO), AI power/grid names with positive estimate revisions and margin expansion (GEV, NVT), large-cap pharma with unanimous net raises (MRK, ABBV, LLY, AMGN, VRTX, ARGX), and European defense primes with confirmed in-window Q3 prints (SAAB-B.ST, RHM.DE, HAG.DE, KOG.OL). I would be wrong if a single macro shock (hyperscaler capex digestion, China export-control headline, or Ukraine de-escalation) hits the correlated AI and defense sleeves at once, or if a PDUFA CRL lands on a top-10 name. [factory: weights and cash rescaled from a stated total of 1.1700 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| MU | 6.8% | rev_yoy 3.46 and gross_margin_chg +0.1015 with inflection_flag true (briefing) | HBM pricing or DRAM inventory data weakens before Dec quarter print |
| NVDA | 6.8% | net_raises 16 of 16 firms and rev_yoy 1.06 with gross margin 0.75 (briefing) | hyperscaler capex guide cut or gross margin slips below 0.74 |
| TSM | 6.8% | net_raises 6 of 6 firms, median target +10.2%, Q3 earnings Oct 15 (catalysts) | capex guide cut or margin guide below 65% on Oct 15 call |
| AMD | 6.0% | net_raises 22 of 22 firms, median target +13.4%, rev_yoy 0.50 (briefing) | data-center GPU guide disappoints at next print |
| ASML | 6.0% | net_raises 5 of 5 firms, median target +13.6%, Q3 earnings Oct 14 (catalysts) | order bookings miss or 2027 guidance trimmed on Oct 14 |
| AVGO | 5.1% | net_raises 47 of 47 firms, median target +23.3%, rev_yoy 0.35 (briefing) | product revenue growth decelerates below 20% |
| DELL | 5.1% | net_raises 24 of 24 firms, rev_yoy 0.58, mom_252_21 2.33 (briefing) | AI server backlog conversion slips or margin guide cut |
| MRK | 5.1% | net_raises 22 of 22 firms, median target +12.4%, I-DXd PDUFA Oct 10 (catalysts) | CRL on I-DXd manufacturing or Keytruda LOE guidance worsens |
| ABBV | 5.1% | net_raises 20 of 20 firms, median target +7.6%, gross_margin_chg +0.029 (briefing) | Skyrizi/Rinvoq growth decelerates below 15% |
| LLY | 5.1% | net_raises 13 of 14 firms, gross_margin_chg +0.038, inflection_flag true (briefing) | retatrutide tolerability data disappoints at EASD or filing slips past Q1 2027 |
| AMGN | 4.3% | net_raises 26 of 28 firms, median target +5.4%, inflection_flag true (briefing) | MariTide Phase 3 timing slips or Sjogren's launch underwhelms |
| GEV | 4.3% | net_raises 8 of 8 firms, rev_yoy 0.22, gross_margin_chg +0.022, inflection_flag true (briefing) | gas-turbine backlog cancellation rate rises or book-to-bill falls below 1.0 |
| NVT | 4.3% | net_raises 6 of 6 firms, rev_yoy 0.53, gross_margin_chg +0.021, inflection_flag true (briefing) | fall-2026 liquid-cooling launch slips or data-center orders slow |
| WST | 4.3% | net_raises 7 of 7 firms, median target +9.6%, vs_ma200 0.216 (briefing) | GLP-1 delivery-device orders normalize faster than guided |
| RGEN | 3.4% | net_raises 4 of 4 firms, mom_63 0.43, vs_ma200 0.269 (briefing) | bioprocessing orders turn negative or FY26 EPS guide cut |
| VRTX | 3.4% | net_raises 9 of 9 firms, mom_252_21 0.40, povetacicept PDUFA Nov 30 (catalysts) | CRL on povetacicept CMC grounds on Nov 30 |
| ARGX | 3.4% | net_raises 17 of 18 firms, median target +6.2%, Q3 earnings Oct 22 (catalysts) | EMPASSION Phase 3 MMN topline misses in Q4 |
| CCJ | 2.6% | net_raises 8 of 8 firms, median target +2.7%, Q3 earnings Nov 3-4 (catalysts) | uranium spot falls below $80/lb or Westinghouse JV execution slips |
| SAAB-B.ST | 2.6% | Q3'26 report Oct 23 primary-sourced (catalysts), European rearmament order pipeline | Gripen export order slips or Q3 margin misses on Oct 23 |
| RHM.DE | 2.6% | Q3'26 results Nov 5 primary-sourced (catalysts), German defense budget +30% YoY | order intake misses or 2027 guidance trimmed on Nov 5 |
| HAG.DE | 2.6% | 9-month 2026 results Nov 5 primary-sourced (catalysts), book-to-bill 2.4x H1 | free cash flow turns more negative than seasonal or backlog stalls |
| KOG.OL | 2.6% | Q3'26 report Oct 29 primary-sourced (catalysts), missile/defense order visibility | Q3 order intake misses or NOK FX drag exceeds guidance |
| CASH | 1.7% | declared cash |  |

**What it did not buy:** FLUT|net_raises -15, sixteen lowers, down 69% from peak; ALB|net_raises -12, twelve lowers, lithium price forecast cut; CEG|net_raises -6, seven lowers, revenue -32.5% QoQ; OKLO|net_raises -4, zero revenue, target dispersion $55-$150; SMR|net_raises -6, revenue -99% YoY, stacking downgrades; LEU|net_raises -4, six lowers, gross margin -12.7pp; MP|net_raises -3, four lowers, no dated catalyst; VRT|net_raises -4, four lowers, mom_63 -0.30


### comp_retail_attention_contrarian_2026-09-25 - book_id 986780f4fa0f0119

kind competition · frozen 2026-09-25T07:23:37+00:00 · 20 positions · max weight 8.0% · cash 2.0% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** I fade the retail-attention crowd: names whose headline counts spiked with no analyst confirmation (SNDK, INTC, ORCL, RKLB, NBIS, BB, BYND, DNUT, GPRO, GME) are excluded, and I buy where revision_flow_90d shows near-unanimous net raises into dated Q3 prints inside the Oct 12-Nov 13 window. The book is software/cyber (OKTA, SNOW, CRWD, PANW, FTNT, DDOG, NET), semis (ASML, TSM), power grid (GEV, NVT) and large/mid biotech (ARGX, MRK, AMGN, ABBV, LLY, WST, RGEN, COGT). I am wrong if a single hyperscaler capex pause or a broad risk-off shock hits the correlated software/semis sleeve at once, or if the crowded PDUFA names draw CRLs.

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| ASML | 8.0% | net_raises 5 of 5 firms with median target +13.6% into confirmed Oct 14 Q3 earnings | Q3 bookings miss or 2027 litho guide cut on Oct 14 |
| TSM | 8.0% | net_raises 6 of 6 firms, median target +10.2%, into Oct 15 Q3 print | Oct 15 capex guide cut below the raised $60-64B range |
| ARGX | 7.0% | net_raises 17 of 18 firms, median target +6.2%, into confirmed Oct 22 Q3 results | EMPASSION MMN topline slips past Q4 2026 or misses |
| MRK | 7.0% | net_raises 22 of 22 firms, median target +12.4%, into Oct 10 I-DXd PDUFA | CRL on the Oct 10 ifinatamab deruxtecan BLA |
| AMGN | 6.0% | net_raises 26 of 28 firms, median target +5.4%, inflection_flag true | MariTide MARITIME-1/2 timing slips past Jan 21 2027 |
| ABBV | 6.0% | net_raises 20 of 20 firms, median target +7.6%, vs_52w_high only -1.1% | Skyrizi/Rinvoq guidance cut at the next print |
| LLY | 6.0% | net_raises 13 of 14 firms, median target +6.6%, inflection_flag true | Retatrutide Q1 2027 filing slips or EASD tolerability disappoints |
| OKTA | 5.0% | net_raises 63 of 63 firms, median target +19.4%, mom_63 +65% | Identity growth decelerates below 10% yoy at next print |
| SNOW | 5.0% | net_raises 47 of 47 firms, median target +23.3%, rev_yoy +35% | Product revenue guide cut or consumption growth stalls |
| CRWD | 5.0% | net_raises 44 of 49 firms, median target +6.2%, at 52w high | Net-new ARR guide cut at the next print |
| PANW | 5.0% | net_raises 34 of 35 firms, median target +17.6%, rev_yoy +34% | Platformization bookings miss or billings guide cut |
| FTNT | 4.0% | net_raises 23 of 23 firms, median target +34.4%, at 52w high | Firewall refresh cycle stalls, billings guide cut |
| DDOG | 4.0% | net_raises 22 of 23 firms, median target +15.4%, rev_yoy +36% | Usage growth decelerates or FY guide trimmed |
| NET | 4.0% | net_raises 27 of 27 firms, median target +19.4%, at 52w high | Large-enterprise net retention falls below 115% |
| GEV | 4.0% | net_raises 8 of 8 firms, median target +2.7%, inflection_flag true | Gas-turbine backlog cancellation or hyperscaler order pause |
| NVT | 4.0% | net_raises 6 of 6 firms, median target +6.4%, inflection_flag true | Fall-2026 modular liquid-cooling launch slips |
| WST | 4.0% | net_raises 7 of 7 firms, median target +9.6%, vs_ma200 +21.6% | GLP-1 device orders normalize below high-teens growth |
| RGEN | 3.0% | net_raises 4 of 4 firms, median target +6.4%, mom_63 +42.8% | Bioprocessing orders turn negative at the next print |
| COGT | 3.0% | net_raises 2 of 2 firms into two NDAs, Nov 30 GIST and Dec 30 SM | Either bezuclastinib NDA draws a CRL in Nov or Dec |
| CASH | 2.0% | declared cash |  |

**What it did not buy:** SNDK|+15x 252d move, only 1 net raise, pure retail attention; INTC|36 headlines, 6 lowers, no dated in-window catalyst; ORCL|25 headlines, net -5 raises, data-center force-majeure news; RKLB|+550% mention surge, no dated catalyst found; NBIS|+160% mention surge, no dated catalyst found; BB|+83% mention surge, no dated catalyst found; BYND|+95% one-day meme pop, no fundamental news; GME|top WSB mention count, no analyst flow, no catalyst


### comp_revision_flow_leaders_2026-09-25 - book_id 308c1895b710fa8d

kind competition · frozen 2026-09-25T07:29:32+00:00 · 23 positions · max weight 6.0% · cash 1.5% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** I bet on analyst revision flow, not target-level upside: every name here has net target raises across at least 3 distinct firms in the trailing 90 days, with the software/security cluster (OKTA 63, SNOW 47, CRWD 44, PANW 34, CRM 33) and big pharma (AMGN 26, MRK 22, ABBV 20) carrying the heaviest, cleanest flow. I would be wrong if the flow reverses before Nov 13, if a single hyperscaler capex or AI-monetization headline hits the correlated software/AI sleeve at once, or if the PDUFA/earnings prints inside the window (MRK Oct 10, ASML Oct 14, ARGX Oct 22) break the thesis that revisions lead price. [factory: weights and cash rescaled from a stated total of 1.3400 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| MRK | 6.0% | net_raises 22 across 17 firms (revision_flow_90d) with I-DXd PDUFA Oct 10 (catalysts) | PDUFA slips past Oct 10 or net_raises turns negative by late Oct |
| ABBV | 6.0% | net_raises 20 across 21 firms (revision_flow_90d), no lowers | any net target cut reported before Nov 13 |
| AMGN | 6.0% | net_raises 26 across 22 firms (revision_flow_90d) after positive Sjogren data | Q3 print misses and net_raises falls below 10 by Nov 13 |
| LLY | 5.2% | net_raises 13 across 13 firms (revision_flow_90d) with retatrutide filing planned Q1 2027 | EASD retatrutide tolerability data disappoints late Sep |
| OKTA | 5.2% | net_raises 63 across 32 firms (revision_flow_90d), strongest flow in the panel | any net target cut or identity-demand slowdown headline before Nov 13 |
| SNOW | 5.2% | net_raises 47 across 33 firms (revision_flow_90d), zero lowers | product-revenue guide trimmed at next print |
| CRWD | 5.2% | net_raises 44 across 35 firms (revision_flow_90d) | net_raises falls below 20 by Nov 13 |
| PANW | 4.5% | net_raises 34 across 30 firms (revision_flow_90d) | billings guide cut at next print |
| CRM | 4.5% | net_raises 33 across 29 firms (revision_flow_90d) | agentic-AI narrative reverses, net_raises turns negative |
| GTLB | 4.5% | net_raises 29 across 21 firms (revision_flow_90d), zero lowers | any net target cut before Nov 13 |
| ESTC | 4.5% | net_raises 28 across 21 firms (revision_flow_90d) | cloud growth decelerates at next print |
| NET | 4.5% | net_raises 27 across 19 firms (revision_flow_90d), zero lowers | any net target cut before Nov 13 |
| AFRM | 3.7% | net_raises 27 across 23 firms (revision_flow_90d), zero lowers | funding-cost pressure forces a guidance cut |
| DELL | 3.7% | net_raises 24 across 18 firms (revision_flow_90d), zero lowers | AI-server margin guide trimmed at next print |
| S | 3.7% | net_raises 23 across 20 firms (revision_flow_90d), zero lowers | net_raises falls below 10 by Nov 13 |
| DT | 3.7% | net_raises 23 across 18 firms (revision_flow_90d), zero lowers | any net target cut before Nov 13 |
| FTNT | 3.7% | net_raises 23 across 17 firms (revision_flow_90d), zero lowers | billings deceleration headline before Nov 13 |
| ARGX | 3.7% | net_raises 17 across 14 firms (revision_flow_90d) into Oct 22 earnings | EMPASSION Phase 3 topline misses in Q4 2026 |
| NVDA | 3.7% | net_raises 16 across 21 firms (revision_flow_90d), zero lowers | any hyperscaler capex digestion headline before Nov 13 |
| AME | 3.7% | net_raises 12 across 10 firms (revision_flow_90d), zero lowers | net_raises falls below 5 by Nov 13 |
| WST | 3.7% | net_raises 7 across 6 firms (revision_flow_90d), zero lowers | GLP-1 device demand normalization headline |
| ASML | 3.7% | net_raises 5 across 4 firms (revision_flow_90d) into Oct 14 earnings | Q3 order intake disappoints on Oct 14 |
| CASH | 1.5% | declared cash |  |

**What it did not buy:** FLUT|net_raises -15, 16 lowers across 15 firms; ALB|net_raises -12, 12 lowers across 11 firms; CEG|net_raises -6, 7 lowers across 7 firms; SMR|net_raises -6, 6 lowers across 7 firms; LEU|net_raises -4, 6 lowers across 9 firms; OKLO|net_raises -4, 4 lowers across 6 firms; VRT|net_raises -4, 4 lowers across 5 firms; GILD|net_raises -3, 6 lowers across 8 firms


### comp_small_cap_catalyst_2026-09-25 - book_id a978a7d6c8b1a962

kind competition · frozen 2026-09-25T07:31:40+00:00 · 25 positions · max weight 5.4% · cash 1.3% · benchmark URTH · horizons [1, 5, 21, 126]  
**Objective:** Relative P&L vs WLS, 2026-10-12 to 2026-11-13  
**Model:** deepseek-flash

**Strategy:** Bet on dated, primary-sourced catalysts landing inside Oct 12-Nov 13: FDA PDUFAs (AGIO Nov 1, SMMT Nov 14, CAPR Nov 22), confirmed earnings (ASML Oct 14, TSM Oct 15, TER Oct 27, EVO/SAAB Oct 23, KOG Oct 29, RHM/HAG Nov 5, ALL Nov 12), and Hon Hai Tech Day Oct 30-31. Every name has a hard date, so relative P&L is driven by prints, not theme drift. I would be wrong if a macro shock or a single hyperscaler capex pause hits the semis/power sleeve simultaneously, or if the small-cap PDUFA names draw CRLs (the documented -33% five-day tail) instead of approvals. [factory: weights and cash rescaled from a stated total of 1.4900 to 1.0 -- the model's arithmetic, not its intent]

| Ticker | Wt | Thesis | Falsifier |
|---|---|---|---|
| AGIO | 5.4% | net_raises 5 of 6 firms over 90d into Nov 1 mitapivat sickle-cell PDUFA | catalyst slips past Nov 13 or CRL on Nov 1 |
| VRTX | 5.4% | net_raises 9 of 9 firms over 90d into Nov 30 povetacicept PDUFA | accelerated-approval BLA draws a CMC-based CRL |
| MRK | 5.4% | net_raises 22 of 22 firms and Oct 10 I-DXd PDUFA inside the window | Daiichi ADC facility CRL delays the Oct 10 decision |
| ARGX | 5.4% | net_raises 17 of 18 firms and Oct 22 Q3 earnings inside the window | EMPASSION MMN topline slips or misses at the Oct 22 print |
| ASML | 5.4% | Oct 14 confirmed Q3 earnings with net_raises 5 of 5 firms | order book disappoints on Oct 14 and High-NA commentary sours |
| TSM | 5.4% | Oct 15 Q3 earnings with net_raises 6 of 7 firms and capex raised to $60-64B | Oct 15 capex guide cut signals AI-capex digestion |
| COGT | 4.7% | two primary-sourced PDUFAs Nov 30 and Dec 30 with Wedbush Outperform $55 | either bezuclastinib NDA draws a CRL or slips past Nov 13 |
| BBIO | 4.7% | net_raises 9 of 11 firms and Nov 27 BBP-418 PDUFA on FORTIFY data | LGMD2I filing delayed or CRL on Nov 27 |
| TER | 4.7% | Oct 27 confirmed Q3 earnings with net_raises 6 of 7 firms and ~70% AI revenue | robotics-segment growth stalls or Advantest qualification slips |
| CAPR | 4.0% | B Riley upgrade to $21 Sept 14 ahead of Nov 22 deramiocel PDUFA | adcom 9-of-12 negative carries into a Nov 22 CRL |
| SMMT | 4.0% | HARMONi OS consistent at WCLC Sept 15 into Nov 14 ivonescimab PDUFA | Barclays/UBS Hold reiterations hold and Nov 14 brings a CRL |
| INSM | 4.0% | Sept 21 ENCORE sNDA filing with 25 analysts averaging ~$200 | patient-reported endpoint read narrowly and Jan 28 slips |
| PRAX | 4.0% | net_raises 5 of 6 firms into Dec 27 relutrigine PDUFA after major amendment | FDA issues a second major amendment pushing past the window |
| NVT | 4.0% | inflection_flag true with net_raises 6 of 6 firms and rev_yoy 0.53 | fall-2026 liquid-cooling launch slips past the window |
| GEV | 4.0% | inflection_flag true with net_raises 8 of 9 firms and orders +88% organic | backlog cancellation or hyperscaler pause hits the Q3 print |
| SVRA | 3.4% | Nov 22 molgramostim PDUFA extended 3 months with FDA disclaiming safety issues | inhaled-biologic CMC finding forces another major amendment |
| CCJ | 3.4% | Nov 3-4 Q3 earnings with uranium term price at record $96/lb | production shortfall versus delivery commitments disclosed Nov 3 |
| EVO.ST | 3.4% | Oct 23 confirmed Q3 report with Americas +9.5% and LatAm +26.3% growth | Asia volatility worsens and the Oct 23 print misses |
| SAAB-B.ST | 3.4% | Oct 23 confirmed Q3 report with Gripen export pipeline intact | order intake disappoints on Oct 23 and the re-rating unwinds |
| KOG.OL | 3.4% | Oct 29 confirmed Q3 report with missile demand and Nordic order visibility | Q3 order intake misses on Oct 29 |
| RHM.DE | 3.4% | Nov 5 confirmed Q3 results with Bernstein Buy at EUR1,900 | order timing pushes revenue recognition past Nov 5 |
| HAG.DE | 2.7% | Nov 5 confirmed 9-month results with book-to-bill 2.4x H1 | negative free cash flow worsens at the Nov 5 print |
| ALL.AX | 2.7% | Nov 12 confirmed FY26 annual results with Anaxi digital growth | Australian pokies regulation headlines hit the Nov 12 print |
| 2317.TW | 2.7% | Oct 30-31 confirmed Hon Hai Tech Day with Aug revenue +52% YoY | AI server rack guidance disappoints at Tech Day |
| CASH | 1.3% | declared cash |  |

**What it did not buy:** ALB|net_raises -12 with 12 lowers and no dated catalyst; LAC|net_raises -1 and no catalyst in the window; SLI|no catalyst and 35bps cost on thin volume; NVO|no analyst raises and CagriSema only beat low tirzepatide dose; SMR|net_raises -6 with revenue down 99% YoY; OKLO|net_raises -4 and no revenue or dated catalyst; FLUT|net_raises -15 with 16 lowers and four 2026 guidance cuts; MGM|Diller withdrew the $18B buyout bid on Sept 24


---


# 2. CONSIDERED - the 84 thesis cards (2026-09-25)

Source: `backend/data/optimus/thesis_cards/2026-09-25/*.json` (_run_receipt.json skipped). Verdicts: supports 21, neutral 57, against 6. Consensus is what the card's web pass recorded (consensus_source URL in each card); a mean target in local currency (KRW, JPY, TWD...) is printed as recorded, and implied upside is '-' where the card did not compute it. 'Net raises 90d' = engine_net_raises_90d (target raises minus cuts in the dated revision ledger; blank = not in the engine's panel).

| Ticker | Kind | Verdict | Conf | Next dated event | Consensus n / mean tgt / upside | Net raises 90d | Falsifier |
|---|---|---|---|---|---|---|---|
| 000660.KS | competition | supports | med | 2026-10-27 \| earnings \| 3Q26 earnings release and conference call expected | n 38 / 3,184,025.00 / - |  | 3Q26 earnings on 2026-10-27 showing HBM or DRAM average selling prices falling versus 2Q26, or operating profit below the KRW 60.54T reported for 2Q26. |
| 010120.KS | competition | supports | med | 2026-10-28 \| earnings \| Q3 2026 earnings release expected, company IR page publishes no calendar so date is m… | n 23 / 275,813.00 / - |  | Q3 2026 earnings on 2026-10-28 showing order intake below the raised KRW 6.0tn annual run-rate or operating margin under 11.3%. |
| 012450.KS | competition | supports | med | 2026-10-07 \| product launch \| Nuriho KSLV-II 5th launch window at Naro Space Center | n 22 / 1,665,238.00 / - |  | Q3 2026 ground systems operating margin reported below 10% (versus 35-39% export margin), or a Poland K9 EC3 award slipping past 2026-12-31. |
| 2330.TW | competition | supports | high | 2026-10-08 \| monthly sales \| TSMC Monthly Sales September 2026 | n 34 / 3,236.00 / - |  | 3Q26 earnings on 2026-10-15 showing gross margin below the guided 65% floor or 3Q26 revenue under US$44.6bn. |
| 6857.T | competition | supports | med | 2026-09-30 \| dividend record date \| record date for the distribution of interim dividend | n 21 / 42,138.00 / - |  | FY2026 Q2 results on 2026-10-28 showing gross margin below Q1 FY2026 and no repeat of the inventory-obsolescence reversal, with guidance not raised again. |
| 8035.T | competition | supports | med | 2026-09-29 \| dividend \| ex-dividend date for interim dividend of 384 yen | n 23 / 76,809.00 / - |  | FY2027 Q2 earnings on 2026-10-30 showing gross margin below Q1 FY2027 and no H2 recovery, or H1 net sales under the raised 1,620B yen guidance. |
| ENR.DE | competition | supports | med | 2026-09-30 \| governance \| Matthias Rebellius steps down from the Supervisory Board | n 25 / 196.32 / - |  | FY2026 results on 2026-11-11 show comparable revenue growth below the guided 14-16 pct or Siemens Gamesa back at a loss. |
| LDO.MI | competition | supports | med | 2026-11-05 \| earnings \| Board of Directors approves Results for the Nine Months 2026 | n 19 / 69.41 / - |  | 9M 2026 results on 5 Nov 2026 showing free operating cash flow still negative and no further FY2026 guidance raise. |
| ARGX | personal | supports | med | 2026-09-08 \| investor conference \| Wells Fargo 21st Annual Healthcare Conference fireside chat, Boston | n 23 / 1,181.00 / 20% | 17 | The Q4 2026 EMPASSION MMN readout (empasiprubart) fails its primary endpoint, or the Q3 2026 report on 2026-10-22 shows product sales growth decelerating below… |
| AVGO | personal | supports | med | 2026-09-30 \| dividend \| Quarterly cash dividend of $0.65 per share payable to holders of record 2026-09-21 | n 50 / 531.85 / 47% | 2 | Any named hyperscaler (Google, Meta, Anthropic, OpenAI, ByteDance) publicly pushes out or cancels a custom XPU program before the Q4 FY2026 report. |
| ENS | personal | supports | med | 2026-10-02 \| dividend \| Q2 FY2027 quarterly cash dividend of $0.2875/share payable (record date 2026-09-18);… | n 5 / 252.58 / 41% | 0 | The lithium data-center-backup line staying near 0% of segment revenue by the Dec earnings call would falsify the decoupling thesis -- the book's own stated fa… |
| GEV | personal | supports | med | 2026-10-28 \| earnings \| Q3 2026 Earnings Webcast, 7:30-8:30 am EDT (GE Vernova leadership team) | n 36 / 791.53 / -16% | 8 | Turbine-backlog slot reservations failing to convert into signed orders by the 2026-10-28 Q3 print would falsify the bull case -- again the book's own stated f… |
| HOOD | personal | supports | med | 2026-09-28 \| investor update \| Anticipated date of Robinhood September month-to-date trading color (posted 4:… | n 29 / 130.08 / 6% | 13 | A state or federal action forcing Robinhood's event contracts under state gambling licensing (raising costs / restricting states) would falsify the bull thesis… |
| LLY | personal | supports | med | 2026-10-29 \| earnings \| Q3 2026 earnings date, estimated by MarketBeat not confirmed by the company | n 30 / 1,325.00 / 14% | 13 | Q3 2026 earnings on 2026-10-29 (unconfirmed) showing worldwide realized price decline worse than Q2's 13 pct while volume growth falls below 40 pct, or FY2026… |
| MP | personal | supports | med | 2026-11-05 (estimated; NOT confirmed on IR or in filings) \| earnings \| Q3 2026 results + conference call (pri… | n 19 / 61.71 / 23% | -3 | A successful legal or legislative challenge to the government's equity-taking/floor-price authority, or NdPr volume growth stalling well below the 127% y/y pac… |
| MU | personal | supports | med | 2026-09-30 \| earnings \| Fiscal Q4 2026 results, released after market close (management call 2:30 p.m. Mounta… | n 49 / 1,515.00 / 40% | 0 | The 2026-09-30 FQ4 print missing the ~86% gross-margin guide, or DRAM/NAND spot pricing rolling over shortly after, would falsify the pricing-cycle bull case. |
| NOVT | personal | supports | low | 2026-10-05 \| IR \| Q2 2026 earnings-call webcast replay availability ends | n 3 / 94.00 / -30% | 0 | The servo-drive order being cancelled, or absent from disclosed backlog, at the ~2026-11-10 Q3 call would falsify the bull case -- the thematic book's own stat… |
| NVT | personal | supports | med | 2026-09-29 \| financing \| Expected closing of the $800.0M 6.150% senior notes due 2036 offering by Hoffman Sch… | n 22 / 110.59 / -31% | 6 | The Maverick Power acquisition failing to close by its 2026-11-20 outside date (or extending to Feb 2027, signaling deal friction) would be the first concrete… |
| RGTI | personal | supports | low | 2026-11-09 \| earnings \| Q3 2026 financial results - estimated date from Nasdaq/Zacks algorithm, NOT company-c… | n 12 / 21.67 / 31% | 0 | If the 10-Q/8-K terms show the government's $100M as a grant/award rather than an actual equity stake -- the book's own stated falsifier for this position -- o… |
| TSM | personal | supports | med | 2026-10-08 \| monthly sales \| TSMC September 2026 monthly sales report | n 21 / 552.26 / 24% | 6 | Q3-2026 gross margin reported below 65% on 2026-10-15, or September monthly sales (2026-10-08) showing YoY growth decelerating below 30%. |
| VRT | personal | supports | med | 2026-09-24 \| dividend_payment \| Q3 2026 cash dividend $0.0625/share paid to holders of record 2026-09-14 | n 29 / 256.93 / 2% | -4 | A confirmed Q3 (Oct, date unconfirmed on IR) organic growth print below the 34-36% guide, or evidence that MW backlog is not converting to signed/shipped order… |
| 005930.KS | competition | neutral | low | 2026-09-28 \| dividend \| last day to buy shares to qualify for 3Q26 dividend | n 36 / 478,628.00 / - |  | The 3Q26 earnings release on Oct 29 2026 showing operating profit below KRW107tn or HBM4 revenue not tripling QoQ would prove the bull case wrong. |
| 034020.KS | competition | neutral | low |  | n 0 / 130,333.00 / - |  | Any company disclosure or filing before 31 Dec 2026 showing H2 2026 order intake below H1 2026, or a confirmed slip of the US nuclear awards past 2027. |
| 1772.HK | competition | neutral | med | 2026-11-03 \| earnings \| Q3 2026 results expected per TipRanks | n 7 / 69.71 / - |  | Q3 2026 results on 2026-11-03 showing lithium chemical segment gross margin below 42% or a net loss, proving the H1 profit swing was a price spike already reve… |
| 2308.TW | competition | neutral | med | 2026-10-28 \| earnings \| Q3 2026 results and analyst meeting, Yahoo estimated earnings date | n 22 / 2,470.00 / - |  | Q3 2026 results on 2026-10-28: gross margin below 34.3% or an EPS miss would show AI power and cooling demand is not converting into the guided margin expansio… |
| 267260.KS | competition | neutral | med | 2026-10-22 \| earnings \| 3Q 2026 earnings release estimated; company IR page lists only past releases, no forw… | n 22 / 1,171,760.00 / 66% |  | 3Q26 earnings on 2026-10-22 showing operating margin below 25% or backlog below USD8.49B would prove the bull case wrong. |
| 6669.TW | competition | neutral | low | 2026-11-14 \| earnings \| Q3 2026 financial results statutory filing deadline under TWSE rules; company board d… | n 18 / 2,785.00 / - |  | Q3 2026 results (TWSE filing deadline 2026-11-14) showing gross margin below 7.5% or revenue growth below 26% YoY. |
| 7011.T | competition | neutral | med | 2026-09-29 \| dividend ex-date \| ex-date for JPY14.00 cash dividend (interim) | n 16 / 5,451.00 / - |  | Any FY2026 quarterly disclosure showing order intake below the JPY7.0tn guidance run-rate, or a guidance cut, e.g. at the Q2 FY2026 results due early November… |
| ALL.AX | competition | neutral | med | 2026-11-11 \| earnings \| Report (Prelim) forecast | n 17 / 66.39 / - |  | FY26 results on 2026-11-12 show group revenue decline and NPATA below FY25, or the US 1B dollar FY29 Interactive target is cut. |
| ASML.AS | competition | neutral | med | 2027-06-10 \| investor day \| Capital Markets Day, ASML to update longer-term views | n 42 / 2,045.00 / - |  | Any ASML disclosure of 2026 order pushouts or cancellations, or a cut to the FY2026 EUR43-45bn sales / 54-56% margin outlook, on or before the 2027-06-10 Capit… |
| EVO.ST | competition | neutral | med | 2026-10-23 \| earnings \| Evolution AB Q3'26 report | n 16 / 752.00 / - |  | Q3 2026 report on 23 Oct 2026 shows group revenue still negative y/y and EBITDA margin below 65%, proving the recovery thesis wrong. |
| HAG.DE | competition | neutral | med | 2026-11-05 \| earnings \| Hensoldt 9-month 2026 results | n 15 / 92.17 / - |  | The 2026-11-05 9M 2026 statement shows FY26 revenue below about EUR 2750m or adjusted EBITDA margin below 18.5%, or free cash flow still negative. |
| KAP.IL | competition | neutral | med | 2026-10-06 \| shareholder meeting \| Deadline 18:00 GMT+5 for absentee EGM ballots on major China and Russia ur… | n 14 / 90.73 / - |  | Kazatomprom cuts 2027 production guidance below 27,500 tU (100% basis), or states Russian sulphuric-acid volumes for 2027 are not secured, on or before the 20… |
| KOG.OL | competition | neutral | med | 2026-10-29 \| earnings \| Kongsberg Gruppen Q3'26 report | n 11 / 395.45 / - |  | Q3 2026 report on 29 Oct 2026 showing EBIT margin below 16pc or order intake below NOK 17,067m would break the growth-and-margin bull case. |
| NOVO-B.CO | competition | neutral | low | 2026-11-04 \| earnings \| Q3 2026 quarterly results, first nine months 2026 | n 23 / 307.56 / - |  | Q3 2026 results on 2026-11-04 showing adjusted sales growth below 0% CER, or CagriSema FDA rejection in Q4 2026. |
| ONC | competition | neutral | med |  | n 17 / 402.71 / 10% | 8 | Q3 2026 US BRUKINSA net revenue below $893M quarterly run rate, or FY26 revenue guidance cut below $6.6B, reported on the Q3 2026 earnings date. |
| RHM.DE | competition | neutral | med | 2026-11-05 \| earnings \| Rheinmetall Q3'26 results | n 21 / 1,641.29 / - |  | Q3 2026 results on 2026-11-05 show 2026 sales guidance below EUR 13.7bn or group operating margin below 15%, or operating free cash flow still negative. |
| SAAB-B.ST | competition | neutral | med | 2026-10-23 \| earnings \| Saab Q3'26 report | n 14 / 629.21 / - |  | Q3 2026 report on 2026-10-23 showing order bookings below SEK 28,403m or another negative quarterly operating cash flow. |
| ABSI | holding | neutral | low | 2026-09-15 \| investor_conference \| H.C. Wainwright 28th Annual Global Investment Conference fireside chat | n 11 / 14.40 / 47% | 2 | ABS-201 pattern-hair-loss interim proof-of-concept data, guided 2H 2026, missing or showing no efficacy signal by 2026-12-31. |
| AMSC | holding | neutral | med | 2026-11-04 \| earnings \| estimated Q2 fiscal 2026 results date for quarter ended September 30 2026, after mark… | n 4 / 61.75 / 104% | -1 | Q2 FY26 results (estimated 2026-11-04) showing revenue below 85M or gross margin still near 26 pct would prove the bull case wrong. |
| DKNG | holding | neutral | med | 2026-09-30 \| webcast_replay_expiry \| DKNG Q2 2026 earnings-call audio webcast replay available on IR site unt… | n 43 / 34.86 / 59% | -2 | A confirmed Q3 print (expected ~early Nov, unconfirmed) showing handle/EBITDA reacceleration together with the 30-day net-revision count turning positive would… |
| HUBS | holding | neutral | med | 2026-09-30 \| promotion deadline \| AI Growth Bundle for new accounts: 65% off HubSpot Starter and credits, buy… | n 33 / 250.37 / 17% | -8 | Q3 2026 reported revenue growth below 14% year over year, or customer count growth below 14%, when results are released. |
| KYTX | holding | neutral | med | 2026-09-29 \| medical conference \| KYSA-6 Phase 2 longer-term follow-up oral presentation at AANEM Annual Meet… | n 6 / 30.40 / 327% |  | The rolling SPS BLA is not completed in Q4 2026, or the 2027 miv-cel launch slips past 2027-12-31. |
| NTLA | holding | neutral | med | 2026-11-05 \| earnings \| Q3 2026 earnings release and call, estimated before market open | n 19 / 24.00 / 96% | 3 | FDA issues a complete response letter for the lonvo-z BLA on or before the 2027-03-10 PDUFA date, or the label requires HLA/liver monitoring. |
| PRCH | holding | neutral | med | 2026-11-04 \| earnings \| Q3 2026 earnings date estimated from past reporting schedule; not confirmed by the co… | n 7 / 20.50 / 23% | 5 | Q3 2026 results (est. 2026-11-04) showing Reciprocal statutory surplus below $169.9M or policy growth decelerating from 38% YoY would prove the bull case wrong. |
| SOC | holding | neutral | med | 2026-09-30 \| operations \| Platform Hondo restart targeted within September 2026, no exact day disclosed | n 4 / 9.75 / 125% | -2 | Platform Hondo fails to restart by 2026-09-30, or Q3 2026 net sales come in below 40,000 Boe/d, showing the ramp and throughput cap bind. |
| ABBV | personal | neutral | med | 2026-10-15 \| dividend record date \| Quarterly dividend of 1.73 USD per share record date | n 30 / 278.61 / 5% | 20 | Q3 2026 adjusted EPS reported below the guided 3.84-3.88 range, or 2026 adjusted EPS guided below 13.87, would show the growth story is not converting to earni… |
| AGIO | personal | neutral | med | 2026-11-01 \| pdufa \| mitapivat sNDA, sickle cell disease, priority review (accelerated approval) | n 10 / 45.75 / 35% | 5 | FDA issues a CRL or delays the mitapivat sickle cell sNDA past the Nov 1 2026 PDUFA date. |
| ALB | personal | neutral | med |  | n 22 / 171.56 / 52% | -12 | If lithium prices hold near the Q1 2026 average of about $20/kg, FY2026 adjusted EBITDA should land at $2.4-2.6B; a reported FY2026 adjusted EBITDA below $1.5B… |
| AMGN | personal | neutral | med | 2026-11-04 \| earnings \| Q3 2026 results expected, date not yet announced on IR calendar | n 30 / 383.46 / -2% | 26 | Q3 2026 results (expected 2026-11-04) showing product sales growth below 9% or non-GAAP EPS below $22.30 guidance floor would prove the growth-driver offset is… |
| AMKR | personal | neutral | med |  | n 11 / 76.40 / 46% | 0 | Q3 2026 gross margin below the guided 18.5-19.5% or Q3 sales under $1.95B, reported on the Q3 2026 earnings date. |
| BBIO | personal | neutral | med | 2026-10-08 \| investor day \| BridgeBio Commercial Day in New York City on commercial readiness and launch stra… | n 22 / 109.10 / 64% | 9 | BBP-418 receives a CRL on or before its 2026-11-27 PDUFA date, or Attruby sequential US net product revenue fails to grow from $222.4M in Q3 2026. |
| BE | personal | neutral | med | 2026-09-28 \| legal \| deadline to move for lead plaintiff in Bloom Energy securities class action covering cla… | n 29 / 280.24 / 3% | 3 | Oracle terminates or formally suspends the Project Jupiter master agreement, or Bloom discloses a scandium supply disruption, on or before the Q3-2026 earnings… |
| CCJ | personal | neutral | med | 2026-11-03 \| earnings \| Cameco Q3'26 earnings, Nov 3-4 (also CCO.TO) | n 21 / 127.77 / 37% | -1 | Cameco's Q3 2026 report on Nov 3-4 2026 shows another production or delivery cut, or Westinghouse equity earnings still negative, versus unchanged 2026 guidanc… |
| CEG | personal | neutral | med | 2026-11-09 \| earnings \| Q3 2026 earnings release before market open, date estimated not confirmed by company | n 22 / 353.14 / 35% | -6 | Q3 2026 earnings (est. 2026-11-09) showing FY adjusted EPS guidance below $11.50 or another GAAP EPS decline with nuclear output down again. |
| CLS | personal | neutral | med | 2026-10-01 \| Leadership \| Mandeep Chawla becomes Group President Global Markets and Todd Ankenmann becomes CFO | n 21 / 471.20 / 37% | 1 | Q3 2026 results (Oct 26-27 2026) showing revenue below the raised $20.5B annual run-rate or adjusted operating margin under 8.2%. |
| COGT | personal | neutral | med | 2026-11-06 \| earnings \| Q3 2026 earnings date estimated | n 12 / 55.82 / 74% | 2 | A complete response letter or delay announced for the Nov 30 2026 GIST PDUFA, or the Dec 30 2026 NonAdvSM PDUFA, would break the bull case. |
| DHR | personal | neutral | med | 2026-10-01 \| leadership \| Julie Sawyer Montgomery becomes President and CEO as Rainer Blair retires | n 26 / 230.83 / 7% | -4 | Q3 2026 earnings on 2026-10-21: core growth below the guided 2-3% or a cut to the FY26 adjusted EPS range of 8.45-8.60. |
| GENI | personal | neutral | med | 2026-12-08 \| shareholder meeting \| 2026 Annual General Meeting | n 20 / 11.03 / 91% | 6 | FY2026 revenue reported below $1.005B or adjusted EBITDA below $285M, or year-end cash under $260M, when results are released (guidance reaffirmed or cut at th… |
| GILD | personal | neutral | med | 2026-10-29 \| earnings \| Q3 2026 earnings estimated after market close | n 29 / 158.78 / 5% | -3 | Q3 2026 earnings on 2026-10-29 showing HIV growth below 12% or further cash decline below $3.2B would prove the bull case wrong. |
| GPCR | personal | neutral | med | 2026-11-05 \| earnings \| Q3 2026 earnings, estimated date not confirmed by company | n 16 / 105.78 / 187% | -2 | ACCG-2671 MAD topline, due 1H 2027, showing dose-limiting GI discontinuations or no meaningful weight loss versus the 3.3% single-dose SAD signal. |
| INSM | personal | neutral | med | 2026-10-29 \| earnings \| estimated third-quarter 2026 financial results, before market open | n 23 / 199.55 / 65% | 1 | Q3 2026 results on 2026-10-29 show BRINSUPRI revenue below the pace needed for the $1.25-1.40B 2026 guidance, forcing a guidance cut. |
| INTC | personal | neutral | med | 2026-10-22 \| earnings \| estimated Q3 2026 earnings date after market close, not confirmed by company | n 49 / 116.37 / -4% | 11 | Q3 2026 earnings on the estimated 2026-10-22 date showing Intel Foundry revenue growth below 31% YoY or no named external 14A anchor customer would prove the f… |
| IONQ | personal | neutral | med | 2026-09-30 \| warrant-expiry \| IONQ public warrants expire, last trading day Sep 29 2026 | n 13 / 67.14 / 66% |  | Q3 2026 earnings (est. Nov 4 2026) showing FY26 revenue guidance below 450M USD or organic growth under 100%, or gross margin below 33%. |
| LEU | personal | neutral | med | 2026-12-31 \| operational milestone \| Complete first new centrifuge in Oak Ridge, Tennessee, per full-year 202… | n 19 / 247.40 / 60% | -4 | First new Oak Ridge centrifuge not completed by 2026-12-31, or DOE FY2027 budget omits HALEU cascade funding, killing about 0.8B USD Technical Solutions backlo… |
| MRK | personal | neutral | med | 2026-10-10 \| pdufa \| ifinatamab deruxtecan (I-DXd) BLA, 2L+ extensive-stage SCLC | n 28 / 152.96 / 2% | 22 | I-DXd fails to win FDA approval on the 2026-10-10 PDUFA date, or Q3 2026 results on 2026-10-29 show FY2026 non-GAAP EPS guidance cut below $2.66. |
| PRAX | personal | neutral | low | 2026-11-05 (estimated; not yet announced as of 2026-09-25) \| earnings \| Q3 2026 financial results and corpora… | n 19 / 638.68 / 114% | 5 | A second PDUFA extension or a Complete Response Letter on 2026-12-27 would falsify the bull case; an on-time approval would confirm it. This is a binary event… |
| QNT | personal | neutral | med |  | n 13 / 97.17 / 90% | 1 | Any company disclosure before 2027 showing FY2026 revenue below the $28M guidance floor, or a confirmed slip of the 2027 Sol launch date. |
| REGN | personal | neutral | med | 2026-10-30 \| earnings \| Q3 2026 financial and operating results, conference call 8:30 AM ET | n 28 / 849.32 / 6% | 4 | Q3 2026 results on 2026-10-30 showing EYLEA US net sales down more than 45 pct year over year or a GAAP EPS miss versus Q2 2026. |
| RGEN | personal | neutral | med | 2026-09-30 \| board retirement \| Director Karen A. Dawes retires from the board | n 23 / 189.48 / 5% | 4 | BioLife stockholders fail to approve the merger at the 2026-10-05 special meeting, or Q3 2026 GAAP operating margin stays near 6.8% with no accretion progress. |
| SLI | personal | neutral | med | 2026-09-29 \| investor conference \| Lytham Partners Fall 2026 Investor Conference, virtual, Sep 29 to Sep 30 2… | n 6 / 4.51 / 112% | 0 | No Final Investment Decision on the South West Arkansas Project announced by December 31 2026, or an equity raise priced below USD 2.06 before FID. |
| SMMT | personal | neutral | med | 2026-10-19 \| earnings \| Q3 2026 earnings, estimated before market open, conference call 8:00 AM ET | n 17 / 28.81 / 70% | 1 | A complete response letter on the 2026-11-14 PDUFA for ivonescimab plus chemotherapy in EGFR-mutated NSCLC post-TKI, or a HARMONi-3 squamous-cohort PFS miss in… |
| SVRA | personal | neutral | med | 2026-11-22 \| pdufa \| molgramostim BLA, autoimmune PAP; extended 3 months from Aug 22 | n 8 / 10.94 / 101% |  | A Complete Response Letter for the molgramostim BLA on or before the 2026-11-22 PDUFA date, or FDA requiring a re-inspection of the Fujifilm drug-substance sit… |
| TER | personal | neutral | med | 2026-09-25 \| dividend \| Quarterly cash dividend of $0.13 per share payable to shareholders of record 2026-09-… | n 17 / 446.47 / 17% | 6 | Q3 2026 earnings on 2026-10-27 showing revenue below $1,200M or Semiconductor Test down sequentially, proving the AI and memory order cycle has rolled over. |
| TMQ | personal | neutral | med | 2026-09-27 \| conference \| Denver Gold Mining Forum Americas, Colorado Springs, CEO Tony Giardini speaking, ru… | n 6 / 6.53 / 96% |  | A company-dated disclosure before Oct 2027 showing the USACE NEPA schedule slipped past the Oct 2027 draft EIS target, or Ambler Road litigation halting access. |
| VKTX | personal | neutral | med | 2026-09-25 \| offering settlement \| 7,857,143 common shares at 35.00 dollars and 225 million dollars of 2.00 p… | n 20 / 94.61 / 214% | 1 | VANQUISH-1 or VANQUISH-2 78-week topline readout missing its primary efficacy or tolerability endpoint, or oral VK2735 Phase 3 failing to begin by Q4 2026. |
| VRTX | personal | neutral | med | 2026-11-02 \| earnings \| Q3 2026 financial results and conference call | n 32 / 570.32 / 12% | 9 | FDA rejects or delays the povetacicept BLA on or before its Nov 30, 2026 PDUFA date, removing the renal-franchise launch that underpins the five-pillar thesis. |
| WST | personal | neutral | med |  | n 17 / 405.38 / 12% | 7 | Q3 2026 reported net sales growth below 1.9 pct year over year, or an FY26 guidance cut, disclosed on the Q3 2026 earnings date. |
| AARD | holding | against | med | 2026-10-13 \| legal \| securities class action lead plaintiff deadline | n 12 / 11.11 / - |  | If the promised Q3 2026 unblinded HERO and OLE assessment, unreported as of 2026-09-25, shows ARD-101 efficacy and safety and the FDA lifts the hold, the bear… |
| BHVN | holding | against | med | 2026-10-01 \| clinical_data \| BHV-1530 Phase 1 data at ESMO Congress, stated as October 2026 window, exact day… | n 17 / 21.27 / 50% | 0 | If the FDA escalates the Sep 4, 2026 partial hold to a full clinical hold on BHV-7000, or RISE3 topline slips past the stated 2H 2026 window, the bull case fai… |
| QUBT | holding | against | high | 2026-11-09 \| earnings (EXPECTED, NOT YET ANNOUNCED) \| Q3 2026 financial results and shareholder call; cadence… | n 6 / 18.67 / 108% | 1 | A quarter (next expected ~2026-11-09, unconfirmed) in which the LSI/NHanced legacy lines stop shrinking AND consolidated gross margin turns positive would fals… |
| SLDP | holding | against | med |  | n 2 / 6.88 / 177% |  | If no Korean commercial-scale electrolyte JV is announced by 2026-12-31, or the continuous pilot line misses its Q4 2026 startup, the management timeline is br… |
| CAPR | personal | against | med | 2026-09-29 \| conference \| WMS 2026 late-breaking poster: Deramiocel HOPE-3 OLE delayed-start analysis and 2-y… | n 10 / 27.00 / 203% | 1 | A complete response letter for deramiocel on or before the 2026-11-22 PDUFA date, or the FDA refusing the refined upper-limb-function indication. |
| SRAD | personal | against | med | 2026-11-04 \| earnings \| Q3 2026 results date, estimated and not company-confirmed | n 23 / 18.32 / 46% | -12 | Q3 2026 results on 2026-11-04 showing FY2026 revenue guidance below EUR 1,518m or Adjusted EBITDA margin contraction would prove the bull case wrong. |


---


# 3. THE POTENTIAL LIST - 139 distinct names

Union of the candidate tables in `docs/research_notes/2026-09-25/`: research_themes.md FINAL 'HUMAN + AI' table (38 rows), research_global_candidates.md candidate table (66 rows), research_pharma.md bucket tables 1-3 (17 rows; the note's own 'suggested 17' is a weighted subset of these), research_social.md §3 retail crowding + §4 gambling basket (25 rows). 146 source rows collapse to 139 distinct names; a name found in more than one table shows the first table's text and lists every source. 'Verdict (note)' is blank where the source table has no verdict column (global, social). 'Card' = the 2026-09-25 thesis-card verdict/confidence where one exists.

| Ticker | Theme | Catalyst & date | Analyst action | Bear case / falsifier | Verdict (note) | Card | Source |
|---|---|---|---|---|---|---|---|
| ALB | Lithium (Large) | Q3 earnings ~late Oct 2026 | Mizuho cut $160→$140 Neutral (9/17) | 21.5% YTD decline on price normalization \| separating obs: Rally on 232-negotiation news vs spot lithium | Neutral | neutral/med | themes |
| LAC | Lithium (Mid) | Thacker Pass Phase 1, 2027 | Not found | Construction/execution risk, pre-revenue \| separating obs: DOE loan/restructure news vs lithium spot | Neutral |  | themes |
| SLI | Lithium (Small-mid) | FID/construction 2026, output 2029 | Not found | Long pre-revenue runway \| separating obs: Offtake announcements (Trafigura, LGES) | Evidence supports (policy) | neutral/med | themes |
| ABAT | Lithium (Small) | Tonopah Flats Phase 1 construction | Not found | Grant/appeal-dependent, thin balance sheet \| separating obs: Federal-appeal reinstatement is policy-specific | Evidence supports (policy) |  | themes |
| ENS | Lithium/AI-power (Mid-large) | Next earnings ~Dec 2026 | 4 Buy/2 Hold, mean target $199.89 | 0% share in new lithium DC-backup segment \| separating obs: AI-backup narrative decouples from EV-lithium cycle | Evidence supports | supports/med | themes |
| VRT | Semis/AI-energy (Large) | Q3 earnings ~late Oct 2026 | Dispersion $338-$500; Bernstein OP $416 | Valuation already reflects AI narrative \| separating obs: Cooling revenue/MW shipped vs backlog growth | Evidence supports | supports/med | themes |
| GEV | Semis/AI-energy (Large) | Q3 2026 date TBD | Bernstein Buy $1,298 (9/2026) | Slot reservations ≠ signed orders \| separating obs: Backlog cancellation rate on 116GW | Evidence supports | supports/med | themes |
| NVT | Semis/AI-energy (Mid) | Fall-2026 cooling-platform launch | Consensus ~$194.80, 10 analysts Buy | Small base, single-vertical \| separating obs: Whether the fall launch ships on schedule | Evidence supports | supports/med | themes |
| MU | Semis/memory (Large) | Q4 FY26 earnings ~Dec 2026 | Consensus Buy, avg $1,297 (9/24) | Memory cyclicality; 2027 capex digestion risk \| separating obs: HBM allocation share (TrendForce) vs SK Hynix/Samsung | Evidence supports | supports/med | themes, social§3 |
| AMKR | Semis/packaging (Mid) | Arizona ramp 2026-2030 | No named firm/date found | TSMC in-house CoWoS could ease OSAT need \| separating obs: Arizona construction milestones (US onshoring) | Neutral | neutral/med | themes |
| TER | Semis/robotics (Mid-large) | Q3 earnings confirmed Oct 27, 2026 | SA fair-value ~$310 (unnamed model) | Advantest still dominant in HBM/photonics test \| separating obs: Device-qualification wins vs Advantest, H2 2026 | Neutral | neutral/med | themes |
| TSM | Semis/foundry (Large) | Q3 earnings confirmed Oct 15, 2026 | Margin guide below some hopes | Capex-guidance cut = deceleration signal \| separating obs: Margin trajectory vs capex growth | Evidence supports | supports/med | themes |
| IONQ | Quantum (Mid) | Q3 earnings TBD (~early-mid Nov) | Strong Buy consensus, avg ~$69; Wedbush $75 (9/22) | 397M diluted shares, chronic dilution, ~35x fwd sales \| separating obs: Third-party replication of the Sept 23 decoder claim | Neutral | neutral/med | themes, global |
| RGTI | Quantum (Small) | Q3 earnings ~early Nov | Consensus Buy, $21.67-$28.81 | Govt equity stake signals cash burn; dilution history \| separating obs: Government-equity (not grant) structure in next 10-Q | Evidence supports (policy) | supports/low | themes |
| QBTS | Quantum (Small) | Qubits Asia 2026 conference | Not found | Annealing has narrower advantage case \| separating obs: CGI deal converting to disclosed revenue | Neutral |  | themes |
| QUBT | Quantum (Small) | N/A | Split: $10 vs $32 targets | Tiny, lumpy revenue; promotional history \| separating obs: The target dispersion itself is the tell | Evidence against | against/high | themes |
| QNT | Quantum (Mid (new IPO)) | DARPA Stage B interim disclosures | Strong Buy, avg $97 (12 analysts) | Newly public, high volatility \| separating obs: Stage B milestones vs IPO-lockup volatility | Neutral | neutral/med | themes |
| HSYDF/NCTKY | Robotics/actuators (Small (illiquid OTC ADR)) | N/A | Not found | Thin OTC liquidity, wide spreads \| separating obs: The purest actuator play named, but only via illiquid ADR | Neutral (access-constrained) |  | themes |
| NOVT | Robotics (Mid) | Q3 earnings ~Nov 10, 2026 | Baird raised to $194, Outperform; consensus Strong Buy | Testing-phase orders can be cancelled \| separating obs: Disclosed, backlog-verifiable servo-drive order (Aug 6 call) | Evidence supports | supports/low | themes |
| ROK | Robotics (Large) | Ongoing rollout | Not found | No disclosed humanoid-specific revenue yet \| separating obs: Narrative-only until revenue is broken out | Neutral |  | themes |
| SYM | Robotics (Mid) | N/A | Needham/Barclays cut targets (9/8, 9/15); Weiss upgraded to Hold (9/21) | Walmart concentration; stacked PT cuts despite EBITDA beat \| separating obs: Divergence between EBITDA growth and analyst cuts | Neutral |  | themes |
| SERV | Robotics (Small) | N/A | Not found | Guidance cut on Uber Eats weakness, realized \| separating obs: The guidance cut is the clean falsifier | Evidence against |  | themes |
| CEG | AI-energy/nuclear (Large) | Crane restart, as early as 2027 | Not captured this pass | NRC review slips \| separating obs: Actual EA publication date | Neutral | neutral/med | themes |
| CCJ | AI-energy/uranium (Large) | Ongoing ramp | 21-analyst avg $127.77 (+45%) | Uranium spot cyclicality \| separating obs: Spot/equity divergence | Neutral | neutral/med | themes, global |
| LEU | AI-energy/HALEU (Small) | New capacity 2029; $900M DOE order (Jul 2026) | Not found | DOE single-customer concentration \| separating obs: Non-DOE SMR-developer offtakes | Evidence supports (policy) | neutral/med | themes |
| OKLO | AI-energy/SMR (Mid) | No fixed criticality date | GS Neutral $117; Wedbush $150; Seaport downgrade to Hold, same week (9/22-25) | Zero revenue, pre-commercial \| separating obs: Week-over-week target dispersion | Evidence against (near-term; speculative) |  | themes |
| SMR (NuScale) | AI-energy/SMR (Small) | N/A | RBC cut to $10; Citi cut to $6.50 | Stacking downgrades \| separating obs: Already negative on its face | Evidence against |  | themes |
| INTC | Trump-policy (Large) | Lawsuit outcome pending | Not found this pass | Legal challenge to equity-taking authority \| separating obs: Lawsuit ruling date | Neutral (binary event risk) | neutral/med | themes |
| MP | Trump-policy (Mid) | Ongoing offtake | Not found this pass | Same legal-authority risk as INTC \| separating obs: Magnet offtake volume vs fixed floor price | Evidence supports | supports/med | themes |
| TMQ | Trump-policy (Small) | 10% stake closed Sept 14, 2026 | Not found this pass | Tiny company, Ambler Road permitting risk \| separating obs: Ambler Road federal permitting timeline | Neutral (early, headline-beta) | neutral/med | themes |
| PFE | Trump-policy/MFN (Large) | Ongoing MFN rollout | Market read MFN as de-risking (event study) | Multi-year price-pressure mechanism \| separating obs: 2027 realized net pricing vs model | Neutral |  | themes |
| CAPR | Pharma FDA (Small) | PDUFA Nov 22, 2026 | B. Riley upgrade, $5→$21 (9/14); Oppenheimer Outperform (9/17) | 9-of-12 negative adcom vote on original indication \| separating obs: Does Nov 22 grant the narrower label, not the original claim | Neutral (genuine coin-flip-or-better) | against/med | themes |
| SMMT | Pharma FDA (Mid) | PDUFA Nov 14, 2026 | UBS/Barclays reiterate Hold/Neutral | Consensus Hold despite hype; "consistent" ≠ superior \| separating obs: Any pre-Nov-14 upgrade citing OS superiority vs Keytruda | Neutral | neutral/med | themes, pharma |
| PRAX | Pharma FDA (Small-mid) | PDUFA Dec 27, 2026 (extended) | Moderate Buy, 20 analysts, avg $612 vs $282 (9/21) | Major-amendment extensions can precede a CRL \| separating obs: 18-of-20 buy-side conviction despite the delay — asset-specific or pipeline-wide? | Evidence supports | neutral/low | themes |
| DKNG | Gambling (Large) | Q3 earnings TBD | Mixed Aug 2026 round, ~54% avg upside implied | Legal handle flat industry-wide; Predictions cannibalizes own book \| separating obs: DKNG Predictions GGR growth vs shrinking core handle | Neutral | neutral/med | themes |
| HOOD | Gambling/prediction mkts (Large) | Q3 earnings Nov 4, 2026 | Not found this pass | CFTC rulemaking risk (CT/NV pushback) \| separating obs: Structurally on the WINNING side of the AGA leakage story | Evidence supports | supports/med | themes, social§4 |
| MCD | McDonald's (Large) | Next earnings ~Nov 4, 2026 | 5-firm target-cut cluster Sept 24, 2026 (Baird, Oppenheimer, JPM, RBC, BTIG) | Same-store sales near-zero 2 quarters running, in mgmt's own words \| separating obs: Nov 4 same-store-sales trend + franchisee reaction to the $800K remodel mandate | Evidence against (near-term); Neutral longer-term value case |  | themes |
| ZG | Analyst-ROI screen (veto list) (Mid-large) | N/A | Consensus +63.37% upside, 25 analysts (verified) | This is exactly the target-upside signal the user's own data says is negative \| separating obs: Passes the mechanical screen — the point is to distrust it, not act on it | Evidence against (as a screen-driven buy) |  | themes |
| 2330 TT / TSM US | Semis/AI - TSMC, Taiwan, cap ~$1,100bn | Q3'26 earnings Oct 15 [EST., unconfirmed]; Sept sales Oct 8; Oct sales Nov 10 | GS raised PT to NT$2,330 from NT$1,720, Conviction Buy (Sept 2026); consensus PT ~$552, Strong Buy | Any 3nm/CoWoS capacity-easing signal or China/Taiwan geopolitical shock \| bull: AI wafer/CoWoS capacity tight through 2027, GM guided >60% |  | supports/high | global |
| 000660 KS | Memory/AI - SK Hynix, Korea, cap ~$150-200bn | Q3'26 earnings ~late Oct [EST.] | Consensus Q3 op. profit ~₩78.1tn record; Bernstein Sept 22 flags slower HBM4 ramp vs Samsung | HBM4 ramp lagging Samsung per Bernstein export-data model \| bull: HBM leader (50% share), record profit cycle |  | supports/med | global |
| 005930 KS | Memory/AI - Samsung Electronics, Korea, cap ~$400-450bn | Q3'26 prelim guidance ~Oct 8 [EST.], full results ~Oct 30 [EST.] | Bernstein Sept 22: Q3 HBM rev est. raised 23% to ~$11.4bn (+72% QoQ) | Won strength, HBM4 mix vs. price \| bull: HBM4 share gain to >30%, foundry may turn profitable H2 |  | neutral/low | global |
| 8035 JP | Semicap - Tokyo Electron, Japan, cap ~$120-140bn | FY26 Q2 results ~late Oct/early Nov [EST.] | — | China export-control exposure \| bull: WFE spend cycle, advanced-node tool share |  | supports/med | global |
| 6857 JP | Semicap (test) - Advantest, Japan, cap ~$90-100bn | FY26 Q2 results, formally "Oct" per IR calendar [EST. late Oct] | Raised FY26 sales guide +21% to ¥1,714bn (Jul 29) | Post-rally valuation, order lumpiness \| bull: AI inference test demand exceeding forecasts |  | supports/med | global |
| 6146 JP | Semicap (dicing/grinding) - Disco Corp, Japan, cap ~$40-50bn | FY26 Q2 results ~late Oct [EST.] | — | China capex slowdown \| bull: Advanced packaging/HBM dicing demand |  |  | global |
| 6920 JP | Semicap (EUV mask inspection) - Lasertec, Japan, cap ~$15-20bn | FY27 Q1 results (FY ends June) ~late Oct [EST.] | — | Extremely lumpy order book \| bull: Effective EUV mask-inspection monopoly |  |  | global |
| ASML NA / ASML US | Semicap (lithography) - ASML, Netherlands, cap ~$380-420bn | Q3'26 earnings Oct 14, 2026 [CONFIRMED] | Q2 guided Q3 rev $12.8-14.0bn vs. Street $11.3bn | Order lumpiness, China restrictions \| bull: 2026/27 capacity tightness, High-NA adoption |  | neutral/med | global |
| BESI NA | Semicap (hybrid bonding) - BE Semiconductor Industries, Netherlands, cap ~$13-16bn | Q3'26 results ~late Oct [EST.] | — | Rich valuation, customer concentration \| bull: Hybrid bonding for HBM/advanced packaging |  |  | global |
| ASM NA | Semicap (ALD) - ASM International, Netherlands, cap ~$20-25bn | Q3'26 results ~Oct 21 [EST.] | — | Cyclicality, capex timing risk \| bull: ALD deposition tool share on leading nodes |  |  | global |
| 2454 TT | Fabless/AI ASIC - MediaTek, Taiwan, cap ~$55-65bn | Q3'26 earnings + Oct sales ~late Oct/early Nov [EST.] | Won Google TPU-related order (2026) | Smartphone chip pricing pressure \| bull: AI ASIC design wins beyond core smartphone SoC |  |  | global |
| 0981 HK / 688981 SH | Foundry - SMIC, China, cap ~$50-60 (HK line)bn | Q3'26 results ~Nov 13-14 [EST., right at/just past window edge] | Q3 guide (Aug 13): rev +2-4% QoQ, GM 26-28% | Low margins, US export-control risk; date may fall just outside window — verify \| bull: China chip self-sufficiency push |  |  | global |
| 3661 TT | ASIC design - Alchip Technologies, Taiwan, cap ~$10-15bn | Q3'26 earnings + Oct sales ~early Nov [EST.] | Aug revenue +181.8% YoY (Taiwan AI Supply Pulse data) | Customer concentration (AWS), valuation \| bull: AWS Trainium3 ASIC ramp, closest AWS design partner |  |  | global |
| 688256 SH | AI chip (domestic) - Cambricon Technologies, China, cap ~$40-50bn | Q3'26 report ~Oct [EST.] | — | STAR Market A-share — A-shares often excluded from WLS; extreme valuation \| bull: China domestic AI-chip substitution theme |  |  | global |
| 2317 TT | AI servers (ODM) - Hon Hai / Foxconn, Taiwan, cap ~$100-110bn | Sept sales ~Oct 8; Hon Hai Tech Day Oct 30-31, 2026 [CONFIRMED]; Q3 earnings ~mid-Nov | Aug revenue +52% YoY, record; mgmt guided Q3 to beat Street | Thin EMS margins, tariff/geopolitics \| bull: #1 AI server rack maker, Vera Rubin ramp in Q3 |  |  | global |
| 2382 TT | AI servers (ODM) - Quanta Computer, Taiwan, cap ~$50-55bn | Monthly sales; Q3 earnings ~early Nov [EST.] | Q1 order visibility into 2027 per mgmt | Customer concentration, margin \| bull: Custom-ASIC server volume production this quarter |  |  | global |
| 6669 TT | AI servers (ODM) - Wiwynn, Taiwan, cap ~$20-25bn | Monthly sales; Q3 earnings ~early Nov [EST.] | FY25 sales +163% YoY | Valuation after huge run, customer concentration \| bull: Hyperscaler (AWS/Google/Meta/MSFT) direct exposure |  | neutral/low | global |
| 2308 TT | Power/cooling for AI - Delta Electronics, Taiwan, cap ~$45-50bn | Monthly sales; Q3 earnings ~early Nov [EST.] | "Most important AI infra exhibitor outside ODMs" — Computex commentary | Component cost inflation (T-glass, substrates) \| bull: Liquid-cooling/800V DC power leader |  | neutral/med | global |
| 267260 KS | Power grid (HV transformers) - HD Hyundai Electric, Korea, cap ~$20-25bn | Q3'26 report ~mid-Nov [EST., near window edge] | Q3 op. profit consensus ₩316.6bn (+10% QoQ) | Valuation after huge re-rating, US tariff risk \| bull: 765kV transformer export boom to US grid, 25% H1 margin |  | neutral/med | global |
| 010120 KS | Power grid (switchgear/distribution) - LS Electric, Korea, cap ~$8-11bn | Q3'26 report ~mid-Nov [EST.] | Q3 op. profit consensus ₩185.3bn | Lower margin than peers \| bull: Data-center distribution + HV transformer orders, record backlog ₩7.0tn |  | supports/med | global |
| 034020 KS | Nuclear/gas turbines - Doosan Enerbility, Korea, cap ~$15-20bn | Q3'26 report ~mid-Nov [EST.] | — | Execution/large-project risk \| bull: SMR/nuclear restart + gas turbine cycle |  | neutral/low | global |
| ENR GY | Grid/power - Siemens Energy, Germany, cap ~$120-140bn | Q4 FY26 results (FY ends Sep 30) ~mid-Nov [EST., near/at window edge] | Q3 orders record €17.9bn, book-to-bill 1.57x | Siemens Gamesa execution risk \| bull: Grid Technologies record backlog (€51bn), US data-center transformer orders |  | supports/med | global |
| SU FP | Grid/data-center power - Schneider Electric, France, cap ~$130-150bn | Q3'26 trading update ~Oct 20 [EST.] | — | Valuation, European industrial cyclicality \| bull: Data-center electrification capex beneficiary |  |  | global |
| PRY IM | HV cables - Prysmian, Italy, cap ~$22-26bn | Q3'26 results ~Nov 5 [EST.] | — | Input-cost inflation, execution on mega-projects \| bull: HV/submarine cable backlog, grid buildout |  |  | global |
| NEX FP | Cables - Nexans, France, cap ~$7-9bn | Q3'26 revenue ~Oct 22 [EST.] | — | Smaller scale vs. Prysmian, cyclicality \| bull: Electrification/grid capex |  |  | global |
| 6954 JP | Robotics/FA - Fanuc, Japan, cap ~$25-30bn | Q2 FY26 results ~late Oct [EST.] | FY26 sales guided to first-ever >¥800bn | China EV capex slowdown, yen sensitivity \| bull: 1,000+ CRX Physical-AI orders booked, NVIDIA collab |  |  | global |
| 6506 JP | Robotics/motion control - Yaskawa Electric, Japan, cap ~$13-16bn | Q2 FY26 results ~late Oct [EST.] | Q1 orders +29% YoY | ERP-transition cost drag on margin \| bull: Data-center cooling drives + semicap orders |  |  | global |
| 6861 JP | FA sensors/vision - Keyence, Japan, cap ~$110-130bn | Q2 FY27 results (FY ends March) ~mid-Oct [EST.] | FY26 (ended Mar-26) net sales +10.4%, div raised | Very rich multiple \| bull: Premium FA/vision play, humanoid "eyes" thesis |  |  | global |
| 6324 JP | Robotics (precision gearing) - Harmonic Drive Systems, Japan, cap ~$4-6bn | H1 FY26 results ~early Nov [EST.] | Named as "muscles/joints" of humanoid thesis (Saxo, Aug 2026) | Small float, thin liquidity, thematic-hype risk \| bull: Pure-play precision-gearing for humanoid arms/legs |  |  | global |
| 6268 JP | Robotics (reduction gears) - Nabtesco, Japan, cap ~$2.5-3.5bn | Q3 FY26 results (FY ends Dec) ~early Nov [EST.] | — | Small cap, thin liquidity \| bull: Reduction-gear demand for industrial/humanoid robots |  |  | global |
| 6273 JP | Pneumatics/FA - SMC Corp, Japan, cap ~$30-35bn | H1 FY27 results ~late Oct [EST.] | — | Cyclical capex exposure \| bull: Broad-based pneumatic automation demand |  |  | global |
| 1772 HK / 002460 SZ | Lithium - Ganfeng Lithium, China, cap ~$10-14 (HK)bn | Q3'26 report ~late Oct [EST.] | UBS cut 2027 China lithium price forecast 40% (Sept 22) — bearish read-through | Lithium carbonate spot down ~16% in a month (Sept) \| bull: Swung to profit H1'26, revenue nearly tripled |  | neutral/med | global |
| 9696 HK / 002466 SZ | Lithium - Tianqi Lithium, China, cap ~$7-9 (HK)bn | Q3'26 report ~late Oct [EST.] | Same UBS Sept 22 cut applies sector-wide | Same price-volatility risk as Ganfeng \| bull: H1'26 profit surged ~49x YoY |  |  | global |
| PLS AU | Lithium - Pilbara Minerals, Australia, cap ~$9bn | Sept-Q production report ~mid-Oct [EST.]; AGM | FY26 revenue +152%, EBITDA margin 59% | Spodumene price pullback from May peak (CNY200k→~135k/t) \| bull: Largest hard-rock lithium op, dividend resumed |  |  | global |
| SQM US | Lithium - SQM, Chile, cap ~$13-16bn | Q3'26 earnings ~mid-Nov [EST., near window edge] | — | Chile royalty/JV overhang, price risk \| bull: Global lithium demand, Chile brine cost curve |  |  | global |
| 300750 SZ / 3750 HK | Battery - CATL, China, cap ~$200-230bn | Q3'26 report ~Oct [EST.] | April 2026 H-share listing (raised ~HK$39.2bn) broadens access | Price competition, margin compression \| bull: EV+ESS demand, global capacity buildout |  |  | global |
| 1211 HK / 002594 SZ | EV - BYD, China, cap ~$90-110 (HK)bn | Q3'26 earnings ~Oct 29-30 [EST., based on FY25 pattern] | — | Domestic price-war margin compression \| bull: Global EV export growth, vertical integration |  |  | global |
| 9988 HK / BABA US | China tech/AI - Alibaba, China, cap ~$280-320bn | Q2 FY27 earnings ~Nov 25, 2026 [EST.] — OUTSIDE WINDOW | — | Regulatory; not an in-window catalyst — exclude from Book B \| bull: AI cloud monetization |  |  | global |
| 0700 HK | China tech/gaming/AI - Tencent, China, cap ~$550-600bn | Q3'26 earnings ~Nov 12, 2026 [EST.] | Q3'25 beat: rev $27.18bn vs. $26.32bn est | Regulatory, ad-market softness \| bull: Gaming + AI capex monetization |  |  | global |
| 1810 HK | EV/consumer AI hardware - Xiaomi, China, cap ~$140-160bn | Q3'26 earnings ~mid-to-late Nov [EST., verify vs. window] | — | Date may fall after Nov 13 — verify before using as catalyst \| bull: EV ramp (YU7/SU7), smartphone AI |  |  | global |
| EVO SS | Gambling (live casino) - Evolution AB, Sweden, cap ~$13-16bn | Q3'26 report Oct 23, 2026 [CONFIRMED] | — | Asia volatility/cybercrime (-3.7% QoQ), UK GC settlement (£4.75m) closed \| bull: Ex-Asia live-casino growth (Americas +9.5%, LatAm +26.3%) |  | neutral/med | global |
| ENT LN | Gambling - Entain, UK, cap ~$5-6bn | Q3 trading update ~early Nov [EST.] | H1'26: FY guide reiterated, EBITDA £910-960m | UK online gambling tax hike, CEE exit execution \| bull: BetMGM JV scale, CEE 20% divestment closing Q4 |  |  | global |
| FLUT US/LN | Gambling - Flutter Entertainment, Ireland/UK/US, cap ~$35-40bn | Q3'26 results ~early Nov [EST.] | Early Q3 trading "ahead of expectations" (Aug 5 update) | New CEO transition (Dan takes over end-Q3), US state tax risk \| bull: FanDuel US momentum, World Cup knockout-stage betting |  |  | global, social§4 |
| LNW US | Gambling (land-based/social) - Light & Wonder, US, cap ~$7-9bn | Q3'26 earnings ~early Nov [EST.] | — | Leverage, competitive slot-content cycle \| bull: Land-based + social casino diversification |  |  | global |
| ALL AU | Gambling - Aristocrat Leisure, Australia, cap ~$48-52bn | FY26 annual results Nov 12, 2026 [CONFIRMED] | — | Australian pokies regulation \| bull: Anaxi/digital gaming growth |  | neutral/med | global |
| NOVO B DC / NVO US | Pharma (obesity/diabetes) - Novo Nordisk, Denmark, cap ~$280-320bn | Q3'26 results Nov 4, 2026 [CONFIRMED] | Post-Capital Markets Day share slump despite CagriSema win (Sept 22) | CagriSema only beat low tirzepatide dose; FDA obesity decision due Q4'26 (binary, possibly after window) \| bull: CagriSema beat tirzepatide 5mg on weight loss (REIMAGINE 5, Sept 21) |  | neutral/low | global |
| ARGX US / Euronext | Biotech (immunology) - argenx, Belgium, cap ~$42-48bn | Q3'26 results Oct 22, 2026 [CONFIRMED] | — | Pipeline readout misses, valuation \| bull: Vyvgart franchise expansion into new indications | Supports — 3% | supports/med | global, pharma |
| ONC US | Biotech (oncology) - BeOne Medicines (fka BeiGene), China/Switzerland, cap ~$38-45bn | Q3'26 results ~Nov 4-5, 2026 [EST./semi-confirmed] | Q2'26 beat: EPS $3.84 vs $1.44 est | Pipeline/competitive risk in BTK class \| bull: Brukinsa scale, first profitable China-origin big biotech |  | neutral/med | global |
| 4568 JP | Pharma (ADCs) - Daiichi Sankyo, Japan, cap ~$85-95bn | H1 FY26 results ~early Nov [EST.] | — | Trial readout/safety risk \| bull: Enhertu/ADC franchise royalty growth |  |  | global |
| 4519 JP | Pharma - Chugai Pharmaceutical, Japan, cap ~$65-75bn | Q3'26 results ~late Oct [EST.] | — | Lower beta than pure biotech (less of a "catalyst" name) \| bull: Roche royalty stream, steady cash generator |  |  | global |
| RHM GY | Defense - Rheinmetall, Germany, cap ~$55-70bn | Q3'26 results Nov 5, 2026 [CONFIRMED] | Bernstein reiterated Buy, PT €1,900 (Sept 18/21); MWB upgraded Sell→Hold (Sept 21); Deutsche Bank Buy PT €1,800 (Sept 1) | Stock down ~35% YTD, order-timing uncertainty, valuation dispersion (PT range €1,050-1,900) \| bull: German defense budget +30% YoY to ~$150bn 2026; Bernstein: German equipment spend +13%/yr… |  | neutral/med | global |
| HAG GY | Defense (sensors) - Hensoldt, Germany, cap ~$9-12bn | 9-month 2026 results Nov 5, 2026 [CONFIRMED] | — | Negative free cash flow (seasonal, but a real risk) \| bull: Order backlog >€10bn, book-to-bill 2.4x H1 |  | neutral/med | global |
| LDO IM | Defense/aerospace/space - Leonardo, Italy, cap ~$28-35bn | Q3'26 results ~early Nov [EST., historically ~Nov 5-6] | Morgan Stanley Overweight; RBC Outperform PT €70; Bernstein PT €65 (Sept 18-21) | Program execution risk on large platforms \| bull: Diversified defense+space (Thales Alenia stake), FY guidance upgraded twice in 2026 |  | supports/med | global |
| SAAB B SS | Defense - Saab AB, Sweden, cap ~$28-32bn | Q3'26 report Oct 23, 2026 [CONFIRMED] | — | Valuation after multi-year re-rating \| bull: Gripen export pipeline, European rearmament beneficiary |  | neutral/med | global |
| KOG NO | Defense/maritime - Kongsberg Gruppen, Norway, cap ~$22-26bn | Q3'26 report Oct 29, 2026 [CONFIRMED] | — | Valuation, FX (NOK) \| bull: Missile/defense systems demand, Nordic order visibility |  | neutral/med | global |
| 012450 KS | Defense/aerospace - Hanwha Aerospace, Korea, cap ~$35-45bn | Q3'26 report ~early Nov [EST.] | Q3'25 comp: sales +147% YoY, op profit +79% YoY | Very high YoY comps get harder; KRW volatility \| bull: K9/export deals, GTF engine + space (Nouri rocket) exposure |  | supports/med | global |
| KAP LI (GDR) | Uranium - Kazatomprom, Kazakhstan, cap ~$14-18bn | Q3'26 trading update ~late Oct/Nov [EST.] | Term price hit record $96/lb (Sept 10) | Russia sulfuric-acid export ban threatens 2027 output (~-3Mlb risk) \| bull: ~40% of global primary uranium supply; term-price leverage |  | neutral/med | global |
| YCA LN | Uranium (physical holding co.) - Yellow Cake, UK, cap ~$1.0-1.3bn | NAV updates; no earnings catalyst per se | — | Pure spot-price proxy, no operating leverage, small cap \| bull: Direct physical U3O8 exposure at spot ~$90/lb |  |  | global |
| 8058 JP | Trading house - Mitsubishi Corp, Japan, cap ~$75-90bn | H1 FY26 results ~early Nov [EST.] | Q1 FY27 profit ¥445.3bn (+339% YoY, one-off heavy) | Commodity-price cyclicality \| bull: Diversified commodity/energy, Berkshire stake interest |  |  | global |
| 8031 JP | Trading house - Mitsui & Co, Japan, cap ~$55-65bn | H1 FY27 results ~early Nov [EST.] | Q1 FY27 profit record for a Q1, ¥294.1bn; ¥200bn buyback announced (Aug 4) | Cyclicality across Mineral & Metal / Energy \| bull: Record Q1, buyback signal, energy contribution ramping Q2+ |  |  | global |
| 8001 JP | Trading house - Itochu, Japan, cap ~$70-80bn | H1 FY26 results ~early Nov [EST.] | 5-for-1 stock split effective Jan 1, 2026 | Cyclicality, FX \| bull: Diversified non-resource trading model |  |  | global |
| 6501 JP | Grid/nuclear/digital infra - Hitachi, Japan, cap ~$140-160bn | H1 FY26 results ~early Nov [EST.] | — | Conglomerate discount, complexity \| bull: Grid equipment + nuclear + GlobalLogic AI/digital |  |  | global |
| 7011 JP | Defense/nuclear/gas turbines - Mitsubishi Heavy Industries, Japan, cap ~$85-100bn | H1 FY26 results ~early Nov [EST.] | — | Large-program execution risk \| bull: Japan defense budget increase, nuclear restart, gas-turbine cycle |  | neutral/med | global |
| RELIANCE IN | Conglomerate (energy/telecom/retail) - Reliance Industries, India, cap ~$210-230bn | Q2 FY27 earnings ~mid-to-late Oct 2026 [EST., unconfirmed as of Sept 8] | — | O2C margin volatility, capex-driven FCF drag \| bull: Jio tariff hikes, retail margin recovery, new-energy capex optionality |  |  | global |
| VRTX | Pharma - Vertex Pharma | Povetacicept (IgA nephropathy), accelerated-approval BLA — PDUFA Nov 30, 2026 (primary, Vertex/BioSpace PR 2026-06-02) | 31–56 analysts / ~$559–569 / +10–12% ; Morgan Stanley Buy, maint. $665, 2026-09-15 | CRL on CMC/manufacturing grounds (accelerated-approval BLAs draw more scrutiny) — would remove the "first Vertex nephrology product" leg without touching the CF cash-flow base | Supports — 4% | neutral/med | pharma |
| GILD (Arcellx) | Pharma - Gilead Sciences | Anitocabtagene autoleucel (anito-cel), BCMA CAR-T, 4L R/R myeloma — BLA PDUFA Dec 23, 2026 (primary, Gilead PR + SEC 8-K Ex-99.1, 2026-02-23) | 58 analysts (VCP) / ~$150–158 / flat-to-+9% ; — | Competitive displacement from earlier-line CAR-Ts already established (Carvykti, Abecma); facility inspection finding | Supports — 3% | neutral/med | pharma |
| REGN | Pharma - Regeneron | Cemdisiran+pozelimab, gMG NDA, Priority Review — PDUFA "November 2026" (month-only; primary, Regeneron PR 2026-06-22; exact day not company-disclosed) | 19–49 analysts / ~$820–840 / +1–6% ; — | Regeneron has disclosed its own manufacturing-inspection delays elsewhere (Q2 2026 call) — a company-specific execution risk, not just an FDA-decision risk | Supports, modestly — 2% | neutral/med | pharma |
| MRK | Pharma - Merck | Ifinatamab deruxtecan (I-DXd), 2L+ extensive-stage SCLC ADC — PDUFA Oct 10, 2026 (primary — merck.com + Daiichi Sankyo PR 2026-04-13; correction: thi… | 28–38 analysts / ~$150–158 / +2–6% ; Leerink Buy, raised PT to $161, 2026-09-09 | CRL on manufacturing (Daiichi facility) — would delay, not kill, the franchise; at MRK's scale this single indication is not a stock-mover regardless — Keytruda LOE remains the dominant mul… | Supports, modestly — 2% | neutral/med | pharma |
| LLY | Pharma - Eli Lilly | CORRECTED: orforglipron (Foundayo) is already FDA-approved (2026-04-01) and commercially launched — not a forward catalyst as the brief assumed. Real… | 30–45 analysts / ~$1,290–1,343 / +12–15% ; Jefferies Buy, maint. $1,440, 2026-09-22 | Retatrutide GI-tolerability/discontinuation data disappoints at EASD (Sep 28–Oct 2, 2026) or the Q1 2027 filing slips further into 2027 | Neutral-supportive — 3% (own for pipeline breadth, not for this one e… | supports/med | pharma |
| COGT | Pharma - Cogent Biosciences | Bezuclastinib two separate NDAs off positive Phase 3 (PEAK: GIST, HR 0.50 vs. sunitinib; SUMMIT: non-advanced systemic mastocytosis) — PDUFA GIST Nov… | 10–12 analysts / ~$51.6 / +64% ; Wedbush reiterated Outperform $55, 2026-09-16 | Both catalysts land within one month — concentrates rather than diversifies timing risk even though they're two distinct FDA decisions | Supports — best risk/reward of the bucket given dual clean-data catal… | neutral/med | pharma |
| BBIO | Pharma - BridgeBio Pharma | BBP-418 (ribitol) NDA, LGMD2I/R9, off positive Phase 3 FORTIFY — PDUFA Nov 27, 2026 (primary, 8-K) | 22–23 analysts / ~$101.5–112 / +33–40% ; J.P. Morgan Buy, PT $100→$111, 2026-08-11 | LGMD2I/R9 addressable population is tiny (~7,000 US) — the $100+ consensus PT already prices broad pipeline success, diluting this filing's idiosyncratic weight; also has an MFN deal (2026-… | Supports, modest idiosyncratic weight — 2% | neutral/med | pharma |
| SVRA | Pharma - Savara | Molgramostim BLA, autoimmune pulmonary alveolar proteinosis — PDUFA Nov 22, 2026 (primary, extended 3 months from Aug 22 in April; FDA extension lett… | 8 analysts / ~$10.0–10.9 / +97–115% ; Piper Sandler maint. Buy $16, 2026-08-26 | Inhaled-biologic CMC is historically fragile; an FDA-requested "major amendment," even a benign one, is still evidence the first pass wasn't clean | Supports — 2% | neutral/med | pharma |
| INSM | Pharma - Insmed | ARIKAYCE sNDA (earlier-line MAC lung disease, Phase 3b ENCORE) — PDUFA Jan 28, 2027 (primary, PR Newswire/IR, filed 2026-09-21) | 25 analysts / ~$200–206 / +62–66% ; Multiple Buy/Overweight boosts through Aug 2026 (BofA, Morgan Stanley, Cantor, JPM) | Primary endpoint is a patient-reported symptom scale, not a hard outcome — a mild interpretive risk; INSM's cap is now driven mostly by the broader pipeline (brensocatib), diluting this cat… | Supports (high base rate), low idiosyncratic weight — 2% | neutral/med | pharma |
| WST | Pharma - West Pharmaceutical Services | Direct delivery-device/elastomer supplier to Lilly/Novo; raised FY26 guidance twice in 2026 (Feb, Jul); HVP Delivery Devices +27–30% organic in Q1/Q2… | 17 analysts / ~$319.79 (Apr 2026 print, likely stale-low given two subsequent guide raises) / ~+17%+ ; Consensus Buy/Strong Buy (4.47/5.0) | Management itself flags GLP-1 growth "normalizing" off 2025 highs; format transition (pens/auto-injectors/orals) could compress mix if injectable volumes disappoint post-oral-launch | Supports — the single cleanest, most explicitly management-confirmed… | neutral/med | pharma |
| RGEN | Pharma - Repligen | Pure bioprocessing-recovery bellwether (chromatography resins, filtration, single-use); two consecutive earnings beats (Q1/Q2 2026, +$0.09 each); FY2… | 18–23 analysts / ~$168–190 (range $145–225, wide dispersion) / Buy/Strong Buy ; UBS initiated Buy $225, 2026-09-09 | Canaccord Hold $145 (implies −22%) — flags that "recovery" is still order-driven, not fully in revenue, against a 35x+ P/E that punishes any air pocket | Supports — cleanest pure-play read on bioprocessing volume recovery,… | neutral/med | pharma |
| VKTX | Pharma - Viking Therapeutics | Sep 22, 2026: positive Phase 1 maintenance-dosing data — 17.7–21.7% weight loss at 21–33wk, 83–97% retention on step-down dosing; oral Phase 3 to beg… | 17–20 analysts / ~$92–99 (post-data; Oppenheimer $120, Truist $87) / further upside even after the +36% single-day pop ; Multiple raises post-Sept-22 data | Oral VK2735 had a 20% AE-discontinuation rate in Phase 2 — oral tolerability is the open falsifier; this is a "de-risking rally," not a resolution, for this specific 6-month window | Supports — real, dated Sept data + a Q4 2026 oral Phase 3 start insid… | neutral/med | pharma |
| DHR | Pharma - Danaher | Q3 earnings Oct 20, 2026; bioprocessing orders grew mid-teens in Q2 but core Biotech revenue only +2.5% (~$100M resin shipments pushed to 2027 at cus… | 25 analysts / ~$228.91–230.23 / +13–15% ; Goldman raised $210→$250, 2026-09-22; UBS initiated Buy $250, 2026-09-09 | If Q3 core growth stays <4% or orders turn negative, the "timing, not demand-destruction" thesis breaks (FY guide already cut high-single→mid-single digit in Q2) | Supports — GLP-1-adjacent bioprocessing recovery not fully priced giv… | neutral/med | pharma |
| GPCR | Pharma - Structure Therapeutics | Aleniglipron 16.2% weight loss at 72wk OLE (2026-09-08); three interim readouts explicitly dated Q4 2026 — body-composition, T2DM/obesity, and SWITCH… | No single clean consensus table sourced this pass — bullish sell-side sentiment (Seeking Alpha Strong Buy, ~$42 fair value pre-rally vs. ~$52+ spot) — treat target as un… | William Blair: "premature to call it best-in-class" vs. Lilly's orforglipron; burn rate roughly doubled YoY as trials scale | Supports — three genuinely dated Q4 2026 catalysts inside the window… | neutral/med | pharma |
| NTLA | Pharma - Intellia Therapeutics | Update since June: lonvo-z (HAE) PDUFA now dated March 10, 2027 (Priority Review, no AdCom, BLA formally accepted ~Sep 18, 2026) — a real de-risking.… | 23 analysts / ~$21 mean PT vs. ~$12.22 spot (~+70% implied) but rating itself is Hold (10 buy/8 hold/4 sell/1 strong buy) — a genuinely split Street ; HC Wainwright Buy… | Stock is down ~28% from the June 30, 2026 close ($16.92→$12.22) despite the HAE program actually de-risking further — the nex-z HLA signal is real and not yet resolved | Neutral — hold current size, do not add until nex-z patient-selection… | neutral/med | pharma |
| GME | Retail crowding (social §3) | Yes — insider buy + options surge, both dated Sept 24 | mentions: 2,311 wk mentions (AltIndex, #1, though −20% WoW); unusual options Sept 24 (+72% call volume); sentiment Bullish | why: Ryan Cohen $26.4M insider buy; eBay-deal speculation |  |  | social§3 |
| ORCL | Retail crowding (social §3) | Yes — force-majeure notice on a data-center project, dated Sept 24 (negative, but retail bought the dip) | mentions: 32 mentions but +3,100% surge; sentiment Mixed | why: "Oracle calls" YOLO despite bad news |  |  | social§3 |
| GOOGL/GOOG | Retail crowding (social §3) | Yes — Gemini 4 flagship model release imminent | mentions: 54/43 ApeWisdom; sentiment Bullish | why: AI model cycle |  |  | social§3 |
| NVDA | Retail crowding (social §3) | Weak — Huang comment about doubling chip sales, no new dated print this window | mentions: 30 ApeWisdom, 24 AltIndex; sentiment Neutral/Bullish | why: AI capex |  |  | social§3 |
| SPCX (SpaceX, synthetic/pre-IPO exposure) | Retail crowding (social §3) | Yes — confirmed Nasdaq-100 rebalance weight | mentions: 23 AltIndex (+23.3%); sentiment Bullish | why: Space/AI halo |  |  | social§3 |
| BYND | Retail crowding (social §3) | Dated but pump-shaped: no fundamental news cited by any source found | mentions: not on trackers' top list but +95% single session (Sept 17); sentiment Bullish/mania | why: "2021 throwback" meme rally |  |  | social§3 |
| DNUT | Retail crowding (social §3) | Pump-shaped, no company-specific news | mentions: same cluster, +20% (Sept 17–19); sentiment Bullish/mania | why: Rode BYND's coattails |  |  | social§3 |
| GPRO | Retail crowding (social §3) | Real underlying catalyst exists (Starman Optical take-private/relist deal) but the spike pre-dated clean news flow — partly pump-shaped | mentions: same cluster, +14% (Sept 17–19); sentiment Bullish/mania | why: Same meme cluster |  |  | social§3 |
| RKLB | Retail crowding (social §3) | No identified dated catalyst — flag as pump-shaped (mention surge with no news hook found) | mentions: AltIndex #1 by WoW change, +550% mentions; sentiment Bullish | why: Space-sector momentum |  |  | social§3 |
| NBIS (Nebius) | Retail crowding (social §3) | No dated catalyst found this window — flag as pump-shaped | mentions: 52 ApeWisdom, +160%; sentiment Bullish | why: AI cloud/GPU-neocloud narrative |  |  | social§3 |
| BB (BlackBerry) | Retail crowding (social §3) | No dated catalyst found — flag as pump-shaped | mentions: 44 ApeWisdom, +83%; sentiment Bullish | why: QNX auto-software revival narrative |  |  | social§3 |
| SNDK (SanDisk) | Retail crowding (social §3) | Narrative-only in this window — Murat's own repo (Aegis-Finance) already built and then refuted a "SanDisk archetype" by dose-response (per session m… | mentions: 43/24 on trackers; sentiment Neutral | why: Flash/HBM memory shortage |  |  | social§3 |
| AMD | Retail crowding (social §3) | Narrative-only, no new dated print this window | mentions: 52 ApeWisdom (−38% off a prior spike); sentiment Neutral | why: AI-chip beta to NVDA |  |  | social§3 |
| PLTR | Retail crowding (social §3) | Narrative-only, no new dated print this window | mentions: 27/19 on trackers; sentiment Neutral | why: Recurring gov't/AI narrative |  |  | social§3 |
| MGM | Gambling / fast-money basket (social §4) |  | social: Not on retail trackers; pure M&A-arb story | Stock fell 9–10% on Sept 24 after Barry Diller's People Inc. withdrew an $18B buyout bid — a collapsed-deal story, not an operating one. |  |  | social§4 |
| CZR (Caesars) | Gambling / fast-money basket (social §4) |  | social: Not on retail trackers | Per Truist (Sept 21), a separate M&A/consolidation process ("Caesars' deal is progressing") is the live catalyst, distinct from Q4 operating trends which Truist calls a "seesaw." |  |  | social§4 |
| PENN | Gambling / fast-money basket (social §4) |  | social: Not found in this session's data — flag as a genuine gap, not "quiet by inference" | No fresh (last-30-day) fact retrieved this session; needs a follow-up look before using this basket entry. |  |  | social§4 |
| RSI (Rush Street Interactive) | Gambling / fast-money basket (social §4) |  | social: Not found in this session's data — same flag | Same as above. |  |  | social§4 |
| GENI (Genius Sports) | Gambling / fast-money basket (social §4) |  | social: Not found in this session's data — same flag | Same as above. |  | neutral/med | social§4 |
| SRAD (Sportradar) | Gambling / fast-money basket (social §4) |  | social: Not found in this session's data — same flag | Same as above. |  | against/med | social§4 |
| IBKR | Gambling / fast-money basket (social §4) |  | social: Not on retail trackers (small ~3M-account retail base is itself the point) | Only public name that owns the exchange outright (ForecastEx, a CFTC-regulated DCM) rather than distributing someone else's contracts — captures exchange-level (listing/data/clearing) econo… |  |  | social§4 |
| COIN | Gambling / fast-money basket (social §4) |  | social: Not on retail trackers as a PM-specific mention, but scaling fastest of the group | Prediction-market revenue +106% sequentially in Q2 2026, crossed $100M annualized within two months of full 50-state Kalshi-embedded launch — the fastest product ramp cited in Coinbase's hi… |  |  | social§4 |


## Murat's own holdings (murat_book.yaml) beside the card verdicts

Source: `backend/data/murat_book.yaml` (reconciled 2026-08-11; confirmed: False; cash unrecoverable). Card verdicts from `backend/data/optimus/thesis_cards/2026-09-25`; '(no card)' means no card was written for that name on 2026-09-25.

| Ticker | Shares | Cost | Thesis (logged) | Kill condition | Card verdict / conf | Card falsifier |
|---|---|---|---|---|---|---|
| AARD | 1000 | 10 | 5/5 consensus, unanimous outperform | coverage drops below four analysts or the consensus cracks | against / med | If the promised Q3 2026 unblinded HERO and OLE assessment, unreported as of 2026-09-25, shows ARD-101 efficacy and safety and the FDA lifts the hold,… |
| ABSI | 600 | missing | (from the conviction log, 2026-07-11) These are the stocks I bought months ago. My decisions were based on tr… | cash runway falls below 12 months, or a lead programme is discontinued without a named successor | neutral / low | ABS-201 pattern-hair-loss interim proof-of-concept data, guided 2H 2026, missing or showing no efficacy signal by 2026-12-31. |
| AMSC | 50 | missing | (from the conviction log, 2026-07-11) These are the stocks I bought months ago. My decisions were based on tr… | two consecutive quarters of declining grid-segment backlog, or the largest customer concentration exceeds 40%… | neutral / med | Q2 FY26 results (estimated 2026-11-04) showing revenue below 85M or gross margin still near 26 pct would prove the bull case wrong. |
| BHVN | 300 | 8 | post-CRL refocus on late-stage neuro; consensus target ~3x mark | a second regulatory setback on the core pipeline | against / med | If the FDA escalates the Sep 4, 2026 partial hold to a full clinical hold on BHV-7000, or RISE3 topline slips past the stated 2H 2026 window, the bul… |
| DKNG | 150 | 29 | analyst upside + federal prediction-markets optionality; FY25 guide raised | consensus target falls below entry, or two quarters of negative revisions | neutral / med | A confirmed Q3 print (expected ~early Nov, unconfirmed) showing handle/EBITDA reacceleration together with the 30-day net-revision count turning posi… |
| HUBS | 10 | missing | (from the conviction log, 2026-07-11) These are the stocks I bought months ago. My decisions were based on tr… | net revenue retention falls below 100% for two consecutive quarters | neutral / med | Q3 2026 reported revenue growth below 14% year over year, or customer count growth below 14%, when results are released. |
| KYTX | 250 | missing | (from the conviction log, 2026-07-11) These are the stocks I bought months ago. My decisions were based on tr… | a lead clinical programme misses its primary endpoint, or cash runway falls below 12 months | neutral / med | The rolling SPS BLA is not completed in Q4 2026, or the 2027 miv-cel launch slips past 2027-12-31. |
| NTLA | 250 | 13 | in-vivo CRISPR; ATTR programme restart | further clinical holds or serious adverse events | neutral / med | FDA issues a complete response letter for the lonvo-z BLA on or before the 2027-03-10 PDUFA date, or the label requires HLA/liver monitoring. |
| PRCH | 200 | 10 | insurance-attach turnaround, high analyst upside | loss ratios deteriorate again | neutral / med | Q3 2026 results (est. 2026-11-04) showing Reciprocal statutory surplus below $169.9M or policy growth decelerating from 38% YoY would prove the bull… |
| QUBT | 300 | 13 | quantum theme, pre-revenue narrative exposure | narrative rotation; dilution at these levels | against / high | A quarter (next expected ~2026-11-09, unconfirmed) in which the LSI/NHanced legacy lines stop shrinking AND consolidated gross margin turns positive… |
| SLDP | 600 | missing | (from the conviction log, 2026-07-11) These are the stocks I bought months ago. My decisions were based on tr… | a named OEM partnership lapses without replacement, or cash runway falls below 12 months | against / med | If no Korean commercial-scale electrolyte JV is announced by 2026-12-31, or the continuous pilot line misses its Q4 2026 startup, the management time… |
| SOC | 700 | 5 | 5/5 consensus, target well above mark | consensus breaks below the mark | neutral / med | Platform Hondo fails to restart by 2026-09-30, or Q3 2026 net sales come in below 40,000 Boe/d, showing the ramp and throughput cap bind. |


---


# 4. ANALYST-IMPLIED UPSIDE ≥ 50% and ≥ 100%

**CAVEAT (the screen's own line):** target-LEVEL upside is a perverse cross-sectional signal in this repo's data - NEGATIVE_RESULTS.md §17: −90 bps/mo large/mid (t −3.62), −199 bps/mo small (t −7.21). Every row below is a name to research, not a buy. High implied upside most often means the price has fallen and the targets have not caught up.

Source: `backend/data/optimus/analyst/target_snapshots.parquet` (3100 tickers; latest observed_at per ticker, observed 2026-09-24; pit_safe is False on these rows - a current snapshot, not point-in-time history). Screen: implied_upside ≥ 0.50 and price ≥ $2 → **710** names (233 of them at ≥ 100%). Analyst count and recommendation mix: `backend/data/analyst_snapshots.jsonl` where present (marked 'stored', 18 names), else yfinance Ticker.info numberOfAnalystOpinions / recommendationKey and Ticker.recommendations (current month) fetched 2026-09-25 UTC / 2026-09-26 HKT (marked 'yf live', 692 names). 710 of 710 names have a count. The two tables keep names with n ≥ 5 analysts: **166** at ≥ 100% and **365** at 50-100%; the 179 names with fewer than 5 analysts or no count are listed compactly in 4c. Recommendation = strong-buy / buy / hold / sell+strong-sell counts, then Yahoo's key. Liquidity band = median daily dollar volume over the last 63 sessions in `backend/data/optimus/prices_2025_26/bars.parquet` (through 2026-09-21) with xs_ranker.liquidity_band thresholds (mega ≥ $1B, large ≥ $100M, mid ≥ $20M, else small). '[yf target ... differs]' flags a row where Yahoo's live mean target is more than 25% away from the stored one - check it before reading the upside.


## 4a. Implied upside ≥ 100% with n ≥ 5 analysts - 166 names

| Ticker | Price | Mean target | Median / high | Implied upside | n analysts | Recommendation (SB/B/H/S) | Liquidity band (med $vol) | Count source |
|---|---|---|---|---|---|---|---|---|
| WING | 97.64 | 196.96 | 200.00 / 265.00 | 102% | 27 | SB 5 / B 19 / H 5 / S 0 (buy) | large ($151.8M) | yf live 2026-09-25 |
| WULF | 16.50 | 33.85 | 32.00 / 62.50 | 105% | 23 | SB 5 / B 17 / H 1 / S 0 (strong_buy) | large ($555.8M) | yf live 2026-09-25 |
| ARRY | 3.88 | 8.60 | 8.50 / 13.00 | 122% | 22 | SB 1 / B 9 / H 13 / S 0 (buy) | mid ($31.4M) | yf live 2026-09-25 |
| KTOS | 46.80 | 102.76 | 104.00 / 150.00 | 120% | 21 | SB 4 / B 15 / H 2 / S 0 (strong_buy) | large ($182.7M) | yf live 2026-09-25 |
| OKLO | 38.41 | 77.12 | 78.00 / 130.00 | 101% | 20 | SB 6 / B 9 / H 9 / S 1 (buy) | large ($380.3M) | yf live 2026-09-25 |
| VKTX | 35.88 | 94.82 | 95.00 / 125.00 | 164% | 19 | SB 5 / B 13 / H 2 / S 0 (strong_buy) | mid ($65.9M) | yf live 2026-09-25 |
| PRAX | 281.96 | 638.68 | 575.00 / 1,201.00 | 127% | 19 | SB 3 / B 14 / H 1 / S 1 (strong_buy) | large ($114.2M) | yf live 2026-09-25 |
| RUN | 7.91 | 15.87 | 15.00 / 30.00 | 101% | 19 | SB 3 / B 9 / H 9 / S 0 (buy) | mid ($83.7M) | yf live 2026-09-25 |
| QXO | 12.27 | 29.11 | 27.00 / 50.00 | 137% | 18 | SB 4 / B 14 / H 0 / S 0 (none) | large ($245.0M) | yf live 2026-09-25 |
| XENE | 37.00 | 74.87 | 74.50 / 100.00 | 102% | 18 | SB 3 / B 15 / H 1 / S 0 (strong_buy) | mid ($45.3M) | yf live 2026-09-25 |
| WVE | 3.89 | 18.53 | 15.00 / 42.00 | 376% | 17 | SB 2 / B 14 / H 2 / S 0 (strong_buy) | small ($15.2M) | yf live 2026-09-25 |
| IRD | 4.68 | 13.00 | 12.00 / 20.00 | 177% | 17 | SB 3 / B 15 / H 0 / S 0 (strong_buy) | small ($3.4M) | yf live 2026-09-25 |
| JANX | 16.43 | 36.24 | 29.00 / 75.00 | 121% | 17 | SB 2 / B 14 / H 1 / S 1 (strong_buy) | small ($13.5M) | yf live 2026-09-25 |
| NTLA | 11.98 | 24.00 | 17.00 / 61.00 | 100% | 17 | SB 1 / B 9 / H 6 / S 3 (buy) | mid ($46.8M) | stored 2026-08-10 |
| PONY | 7.16 | 20.12 | 18.65 / 32.80 | 181% | 16 | SB 3 / B 14 / H 1 / S 0 (strong_buy) | mid ($23.2M) | yf live 2026-09-25 |
| QBTS | 17.20 | 34.65 | 36.00 / 43.00 | 101% | 16 | SB 1 / B 14 / H 2 / S 0 (strong_buy) | large ($298.8M) | yf live 2026-09-25 |
| GPCR | 35.42 | 105.78 | 101.00 / 145.00 | 199% | 15 | SB 4 / B 11 / H 1 / S 0 (strong_buy) | mid ($33.8M) | yf live 2026-09-25 |
| DYN | 16.36 | 37.20 | 37.00 / 50.00 | 127% | 15 | SB 3 / B 13 / H 0 / S 1 (strong_buy) | mid ($49.3M) | yf live 2026-09-25 |
| NAMS | 22.45 | 50.77 | 51.00 / 59.56 | 126% | 15 | SB 3 / B 12 / H 1 / S 0 (strong_buy) | mid ($31.0M) | yf live 2026-09-25 |
| LFTO | 16.04 | 33.40 | 34.00 / 42.00 | 108% | 15 | SB 5 / B 8 / H 4 / S 0 (buy) | small ($13.3M) | yf live 2026-09-25 |
| CATX | 2.48 | 12.29 | 13.00 / 18.00 | 394% | 14 | SB 2 / B 13 / H 1 / S 0 (strong_buy) | small ($3.8M) | yf live 2026-09-25 |
| APLD | 27.06 | 66.18 | 72.50 / 109.00 | 145% | 14 | SB 2 / B 10 / H 2 / S 0 (strong_buy) | large ($493.5M) | yf live 2026-09-25 |
| FRVO | 16.62 | 40.31 | 43.00 / 51.00 | 143% | 14 | SB 4 / B 10 / H 0 / S 0 (strong_buy) | mid ($69.6M) | yf live 2026-09-25 |
| VERA | 32.74 | 77.50 | 81.50 / 100.00 | 137% | 14 | SB 1 / B 12 / H 1 / S 0 (strong_buy) | mid ($73.9M) | yf live 2026-09-25 |
| CLYM | 11.69 | 27.57 | 26.50 / 40.00 | 136% | 14 | SB 2 / B 13 / H 0 / S 0 (strong_buy) | small ($19.0M) | yf live 2026-09-25 |
| CLDX | 31.22 | 62.50 | 62.00 / 100.00 | 100% | 14 | SB 2 / B 12 / H 1 / S 0 (strong_buy) | mid ($33.2M) | yf live 2026-09-25 |
| STRO | 15.57 | 47.23 | 50.00 / 61.00 | 203% | 13 | SB 3 / B 10 / H 0 / S 1 (strong_buy) | small ($5.7M) | yf live 2026-09-25 |
| ALHC | 7.47 | 22.23 | 22.00 / 28.00 | 198% | 13 | SB 3 / B 9 / H 2 / S 0 (strong_buy) | mid ($73.2M) | yf live 2026-09-25 |
| TSHA | 4.73 | 13.00 | 12.00 / 19.00 | 175% | 13 | SB 3 / B 10 / H 0 / S 0 (strong_buy) | small ($14.2M) | yf live 2026-09-25 |
| LEGN | 18.38 | 46.90 | 48.00 / 74.00 | 155% | 13 | SB 5 / B 3 / H 5 / S 0 (buy) | mid ($41.1M) | yf live 2026-09-25 |
| MPLT | 10.65 | 26.54 | 25.00 / 43.00 | 149% | 13 | SB 1 / B 11 / H 2 / S 0 (none) | small ($10.9M) | yf live 2026-09-25 |
| SLDB | 7.53 | 18.62 | 18.00 / 26.00 | 147% | 13 | SB 5 / B 8 / H 0 / S 0 (strong_buy) | small ($8.7M) | yf live 2026-09-25 |
| MLTX | 12.21 | 28.54 | 30.00 / 50.00 | 134% | 13 | SB 1 / B 10 / H 2 / S 2 (buy) | mid ($21.4M) | yf live 2026-09-25 |
| BEAM | 24.20 | 52.15 | 45.00 / 80.00 | 116% | 13 | SB 1 / B 12 / H 2 / S 0 (strong buy) | mid ($52.7M) | stored 2026-08-10 |
| KC | 9.77 | 20.21 | 20.07 / 26.44 | 107% | 13 | SB 3 / B 11 / H 0 / S 0 (none) | small ($12.1M) | yf live 2026-09-25 |
| CWH | 5.17 | 10.56 | 10.00 / 15.00 | 104% | 13 | SB 2 / B 9 / H 2 / S 0 (strong_buy) | small ($12.2M) | yf live 2026-09-25 |
| IVA | 3.17 | 14.87 | 13.50 / 26.00 | 370% | 12 | SB 1 / B 11 / H 0 / S 0 (strong_buy) | small ($4.0M) | yf live 2026-09-25 |
| RCKT | 2.81 | 8.85 | 9.50 / 15.00 | 216% | 12 | SB 1 / B 6 / H 5 / S 2 (buy) | small ($5.0M) | yf live 2026-09-25 |
| KURA | 10.86 | 32.00 | 28.00 / 76.00 | 195% | 12 | SB 2 / B 12 / H 1 / S 0 (none) | small ($17.2M) | yf live 2026-09-25 |
| AVTX | 15.16 | 44.08 | 40.50 / 60.00 | 191% | 12 | SB 2 / B 12 / H 0 / S 0 (strong_buy) | small ($15.9M) | yf live 2026-09-25 |
| MAZE | 27.08 | 61.50 | 54.00 / 110.00 | 127% | 12 | SB 1 / B 12 / H 0 / S 0 (strong_buy) | small ($10.7M) | yf live 2026-09-25 |
| STUB | 5.28 | 11.12 | 11.00 / 16.00 | 111% | 12 | SB 0 / B 8 / H 5 / S 1 (buy) | mid ($43.2M) | yf live 2026-09-25 |
| ENOV | 18.26 | 38.33 | 36.50 / 52.00 | 110% | 12 | SB 2 / B 10 / H 1 / S 0 (none) | mid ($27.0M) | yf live 2026-09-25 |
| AUR | 5.84 | 12.05 | 12.50 / 18.00 | 106% | 12 | SB 2 / B 6 / H 5 / S 0 (buy) | large ($164.0M) | yf live 2026-09-25 |
| CELC | 78.59 | 160.75 | 161.50 / 177.00 | 105% | 12 | SB 3 / B 10 / H 0 / S 0 (strong_buy) | mid ($84.9M) | yf live 2026-09-25 |
| IMCR | 31.07 | 62.50 | 60.00 / 100.00 | 101% | 12 | SB 1 / B 2 / H 0 / S 0 (none) | small ($15.3M) | yf live 2026-09-25 |
| EYPT | 3.69 | 25.91 | 20.00 / 68.00 | 603% | 11 | SB 1 / B 6 / H 6 / S 0 (buy) | mid ($20.7M) | yf live 2026-09-25 |
| SGMT | 8.94 | 29.60 | 28.50 / 56.00 | 231% | 11 | SB 2 / B 9 / H 0 / S 1 (strong_buy) | small ($9.5M) | yf live 2026-09-25 |
| RGNX | 7.23 | 23.73 | 19.00 / 50.00 | 228% | 11 | SB 3 / B 6 / H 2 / S 0 (none) | small ($13.3M) | yf live 2026-09-25 |
| PHAT | 7.03 | 20.45 | 21.00 / 29.00 | 191% | 11 | SB 2 / B 8 / H 2 / S 0 (none) | small ($10.7M) | yf live 2026-09-25 |
| OCUL | 9.73 | 27.09 | 28.00 / 34.00 | 178% | 11 | SB 4 / B 7 / H 0 / S 0 (strong_buy) | mid ($21.3M) | yf live 2026-09-25 |
| BCRX | 8.47 | 20.82 | 17.00 / 32.00 | 146% | 11 | SB 3 / B 7 / H 1 / S 0 (strong_buy) | mid ($35.1M) | yf live 2026-09-25 |
| PRME | 3.06 | 7.11 | 7.00 / 11.00 | 133% | 11 | SB 1 / B 10 / H 3 / S 0 (strong_buy) | small ($9.6M) | yf live 2026-09-25 |
| WRD | 5.83 | 13.38 | 12.02 / 20.11 | 129% | 11 | SB 4 / B 8 / H 0 / S 0 (strong_buy) | small ($11.7M) | yf live 2026-09-25 |
| TYRA | 22.18 | 47.45 | 50.00 / 59.00 | 114% | 11 | SB 2 / B 12 / H 1 / S 0 (strong_buy) | small ($16.3M) | yf live 2026-09-25 |
| CGEM | 15.69 | 33.55 | 33.00 / 42.00 | 114% | 11 | SB 1 / B 11 / H 0 / S 0 (strong_buy) | small ($12.9M) | yf live 2026-09-25 |
| SNDX | 17.62 | 37.55 | 37.00 / 57.00 | 113% | 11 | SB 2 / B 10 / H 0 / S 0 (strong_buy) | mid ($28.0M) | yf live 2026-09-25 |
| ALM | 12.67 | 25.56 | 25.12 / 32.55 | 102% | 11 | SB 0 / B 10 / H 1 / S 0 (strong_buy) | mid ($86.5M) | yf live 2026-09-25 |
| TRAX | 35.72 | 71.82 | 65.00 / 100.00 | 101% | 11 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | mid ($22.6M) | yf live 2026-09-25 |
| UNCY | 4.74 | 29.60 | 27.50 / 50.00 | 525% | 10 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | small ($4.4M) | yf live 2026-09-25 |
| LXEO | 3.38 | 20.30 | 20.00 / 30.00 | 500% | 10 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($3.7M) | yf live 2026-09-25 |
| CRBP | 7.33 | 34.02 | 34.00 / 48.00 | 364% | 10 | SB 0 / B 9 / H 0 / S 0 (strong_buy) | small ($3.6M) | yf live 2026-09-25 |
| LRMR | 3.46 | 14.40 | 13.00 / 26.00 | 317% | 10 | SB 2 / B 9 / H 0 / S 0 (strong_buy) | small ($5.1M) | yf live 2026-09-25 |
| OLMA | 8.90 | 36.50 | 38.00 / 59.00 | 310% | 10 | SB 2 / B 9 / H 1 / S 0 (none) | small ($10.7M) | stored 2026-08-10 |
| OCS | 9.36 | 36.66 | 39.05 / 43.94 | 292% | 10 | SB 3 / B 7 / H 0 / S 0 (strong_buy) | small ($3.1M) | yf live 2026-09-25 |
| ENVX | 2.96 | 11.35 | 10.00 / 21.00 | 284% | 10 | SB 0 / B 8 / H 3 / S 1 (none) | mid ($24.2M) | yf live 2026-09-25 |
| ARDX | 3.46 | 12.90 | 13.50 / 18.00 | 273% | 10 | SB 1 / B 10 / H 0 / S 0 (none) | small ($15.1M) | yf live 2026-09-25 |
| HELP | 12.46 | 40.09 | 43.25 / 68.80 | 222% | 10 | SB 1 / B 10 / H 0 / S 0 (strong_buy) | small ($15.0M) | yf live 2026-09-25 |
| KRMN | 34.15 | 89.70 | 85.00 / 135.00 | 163% | 10 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | large ($132.6M) | yf live 2026-09-25 |
| NKTR | 58.09 | 141.40 | 150.50 / 192.00 | 143% | 10 | SB 1 / B 9 / H 2 / S 0 (strong_buy) | mid ($50.6M) | yf live 2026-09-25 |
| NUVB | 5.68 | 13.10 | 12.50 / 21.00 | 130% | 10 | SB 3 / B 6 / H 1 / S 0 (strong_buy) | mid ($35.0M) | yf live 2026-09-25 |
| EH | 4.46 | 9.96 | 7.97 / 20.49 | 123% | 10 | SB 1 / B 5 / H 3 / S 2 (buy) | small ($3.5M) | yf live 2026-09-25 |
| EDIT | 2.65 | 5.90 | 5.00 / 15.00 | 122% | 10 | SB 0 / B 8 / H 3 / S 2 (buy) | small ($6.0M) | yf live 2026-09-25 |
| PLTK | 2.15 | 4.78 | 4.00 / 14.00 | 122% | 10 | SB 0 / B 2 / H 9 / S 0 (none) | small ($4.1M) | yf live 2026-09-25 |
| WYFI | 19.70 | 40.50 | 39.00 / 50.00 | 106% | 10 | SB 2 / B 7 / H 1 / S 0 (strong_buy) | mid ($53.3M) | yf live 2026-09-25 |
| FTAI | 179.44 | 364.10 | 337.50 / 600.00 | 103% | 10 | SB 4 / B 6 / H 0 / S 0 (strong_buy) | large ($267.4M) | yf live 2026-09-25 |
| ALT | 3.06 | 17.11 | 17.00 / 28.00 | 460% | 9 | SB 2 / B 7 / H 1 / S 0 (strong_buy) | small ($10.9M) | yf live 2026-09-25 |
| KDK | 2.83 | 10.50 | 11.00 / 13.00 | 270% | 9 | SB 1 / B 7 / H 1 / S 0 (strong_buy) | small ($3.9M) | yf live 2026-09-25 |
| ONDS | 7.61 | 19.42 | 19.00 / 25.00 | 155% | 9 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | large ($573.0M) | yf live 2026-09-25 |
| ZNTL | 2.77 | 6.89 | 6.00 / 10.00 | 149% | 9 | SB 0 / B 5 / H 5 / S 0 (buy) | small ($3.9M) | yf live 2026-09-25 |
| FATE | 2.31 | 5.74 | 7.00 / 8.00 | 148% | 9 | SB 1 / B 4 / H 6 / S 0 (none) | small ($4.3M) | yf live 2026-09-25 |
| OVID | 2.42 | 5.92 | 5.00 / 9.00 | 144% | 9 | SB 0 / B 10 / H 0 / S 0 (strong_buy) | small ($3.7M) | yf live 2026-09-25 |
| AMPX | 9.71 | 23.00 | 22.00 / 30.00 | 137% | 9 | SB 1 / B 9 / H 0 / S 0 (none) | mid ($55.6M) | yf live 2026-09-25 |
| STTK | 6.33 | 14.67 | 15.00 / 18.00 | 132% | 9 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | small ($6.4M) | yf live 2026-09-25 |
| USAR | 15.46 | 35.56 | 35.00 / 45.00 | 130% | 9 | SB 1 / B 8 / H 0 / S 0 (strong_buy) | large ($190.1M) | yf live 2026-09-25 |
| ZVRA | 11.13 | 25.00 | 24.00 / 35.00 | 125% | 9 | SB 2 / B 7 / H 0 / S 0 (none) | small ($11.4M) | yf live 2026-09-25 |
| TE | 3.92 | 8.78 | 9.00 / 16.00 | 124% | 9 | SB 1 / B 5 / H 3 / S 0 (buy) | large ($154.7M) | yf live 2026-09-25 |
| DMRA | 20.43 | 44.67 | 45.00 / 51.00 | 119% | 9 | SB 1 / B 9 / H 0 / S 0 (strong_buy) | small ($12.7M) | yf live 2026-09-25 |
| PICS | 8.90 | 19.01 | 18.74 / 23.93 | 114% | 9 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($3.4M) | yf live 2026-09-25 |
| HAWK | 15.91 | 32.56 | 33.00 / 41.00 | 105% | 9 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | small ($19.4M) | yf live 2026-09-25 |
| CABA | 2.15 | 13.25 | 13.50 / 30.00 | 517% | 8 | SB 1 / B 7 / H 2 / S 0 (strong_buy) | small ($10.8M) | yf live 2026-09-25 |
| BIOA | 7.34 | 35.62 | 30.00 / 73.00 | 385% | 8 | SB 2 / B 5 / H 2 / S 0 (buy) | small ($9.1M) | yf live 2026-09-25 |
| CTMX | 2.77 | 12.25 | 12.00 / 16.00 | 343% | 8 | SB 3 / B 5 / H 0 / S 0 (strong_buy) | small ($9.5M) | yf live 2026-09-25 |
| ALMS | 7.33 | 32.12 | 32.00 / 46.00 | 339% | 8 | SB 1 / B 8 / H 1 / S 0 (strong_buy) | mid ($29.1M) | yf live 2026-09-25 |
| FRMI | 4.57 | 17.12 | 13.50 / 35.00 | 275% | 8 | SB 1 / B 5 / H 2 / S 0 (buy) | mid ($97.9M) | yf live 2026-09-25 |
| ABEO | 5.46 | 18.88 | 17.00 / 30.00 | 246% | 8 | SB 0 / B 7 / H 0 / S 0 (strong_buy) | small ($8.0M) | yf live 2026-09-25 |
| JBIO | 14.98 | 50.12 | 47.00 / 77.00 | 235% | 8 | SB 0 / B 10 / H 0 / S 0 (none) | small ($17.6M) | yf live 2026-09-25 |
| TECX | 24.00 | 76.62 | 78.00 / 93.00 | 219% | 8 | SB 1 / B 8 / H 0 / S 0 (strong_buy) | small ($5.2M) | yf live 2026-09-25 |
| EVMN | 8.58 | 24.12 | 24.00 / 30.00 | 181% | 8 | SB 3 / B 5 / H 2 / S 0 (buy) | small ($6.9M) | yf live 2026-09-25 |
| LFMD | 2.96 | 8.12 | 7.50 / 15.00 | 174% | 8 | SB 0 / B 8 / H 0 / S 0 (strong_buy) | small ($2.6M) | yf live 2026-09-25 |
| MGTX | 11.20 | 29.43 | 27.00 / 50.00 | 163% | 8 | SB 2 / B 5 / H 1 / S 0 (strong_buy) | small ($9.1M) | yf live 2026-09-25 |
| MNKD | 3.27 | 7.97 | 7.50 / 13.00 | 144% | 8 | SB 0 / B 7 / H 1 / S 0 (none) | small ($14.3M) | yf live 2026-09-25 |
| RCAT | 6.77 | 16.50 | 15.00 / 25.00 | 144% | 8 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | mid ($64.8M) | yf live 2026-09-25 |
| SVRA | 5.00 | 10.94 | 10.25 / 16.00 | 119% | 8 | SB 2 / B 6 / H 0 / S 0 (none) | small ($8.6M) | yf live 2026-09-25 |
| HIVE | 3.27 | 7.12 | 7.25 / 10.00 | 118% | 8 | SB 0 / B 7 / H 1 / S 0 (strong_buy) | mid ($49.9M) | yf live 2026-09-25 |
| COLL | 22.54 | 49.00 | 48.50 / 60.00 | 117% | 8 | SB 2 / B 5 / H 1 / S 0 (strong_buy) | small ($17.8M) | yf live 2026-09-25 |
| VOR | 18.20 | 39.00 | 40.00 / 50.00 | 114% | 8 | SB 1 / B 7 / H 1 / S 0 (none) | small ($18.4M) | yf live 2026-09-25 |
| XE | 16.09 | 34.38 | 36.50 / 57.00 | 114% | 8 | SB 2 / B 4 / H 2 / S 1 (buy) | mid ($92.6M) | yf live 2026-09-25 |
| METC | 8.97 | 18.88 | 18.00 / 30.00 | 110% | 8 | SB 0 / B 5 / H 3 / S 0 (none) | mid ($22.3M) | yf live 2026-09-25 |
| LAR | 5.68 | 11.69 | 10.75 / 19.80 | 106% | 8 | SB 4 / B 3 / H 1 / S 0 (buy) | small ($11.7M) | yf live 2026-09-25 |
| AADX | 12.85 | 25.75 | 24.50 / 30.00 | 100% | 8 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | mid ($21.0M) | yf live 2026-09-25 |
| REAL | 8.99 | 18.00 | 18.00 / 20.00 | 100% | 8 | SB 0 / B 7 / H 2 / S 0 (strong_buy) | mid ($28.4M) | yf live 2026-09-25 |
| LENZ | 3.69 | 24.00 | 10.00 / 60.00 | 550% | 7 | SB 0 / B 5 / H 2 / S 0 (none) | small ($3.8M) | yf live 2026-09-25 |
| UPB | 5.17 | 31.14 | 25.00 / 75.00 | 502% | 7 | SB 1 / B 4 / H 2 / S 0 (none) | small ($3.7M) | yf live 2026-09-25 |
| ANNX | 3.81 | 15.29 | 14.00 / 27.00 | 301% | 7 | SB 2 / B 6 / H 2 / S 0 (none) | small ($15.5M) | yf live 2026-09-25 |
| SION | 5.32 | 21.00 | 6.00 / 63.00 | 295% | 7 | SB 0 / B 2 / H 10 / S 0 (hold) | small ($17.6M) | yf live 2026-09-25 |
| DBVT | 11.45 | 39.06 | 44.79 / 54.74 | 241% | 7 | SB 1 / B 5 / H 0 / S 1 (buy) | small ($3.1M) | yf live 2026-09-25 |
| SANA | 2.94 | 8.43 | 7.00 / 12.00 | 187% | 7 | SB 2 / B 6 / H 1 / S 0 (none) | small ($9.0M) | yf live 2026-09-25 |
| CRVS | 11.72 | 33.14 | 32.00 / 42.00 | 183% | 7 | SB 1 / B 7 / H 0 / S 0 (none) | small ($12.7M) | yf live 2026-09-25 |
| SERV | 4.42 | 12.14 | 10.00 / 22.00 | 175% | 7 | SB 0 / B 7 / H 1 / S 0 (none) | small ($17.3M) | yf live 2026-09-25 |
| TMC | 4.03 | 10.90 | 10.00 / 12.30 | 170% | 7 | SB 3 / B 3 / H 0 / S 0 (strong_buy) | small ($18.3M) | yf live 2026-09-25 |
| NGNE | 31.05 | 80.43 | 65.00 / 166.00 | 159% | 7 | SB 0 / B 9 / H 0 / S 0 (none) | small ($6.4M) | yf live 2026-09-25 |
| BETR | 11.35 | 25.71 | 25.00 / 35.00 | 127% | 7 | SB 1 / B 5 / H 2 / S 0 (none) | small ($7.2M) | yf live 2026-09-25 |
| NNE | 16.70 | 37.57 | 45.00 / 50.00 | 125% | 7 | SB 1 / B 5 / H 2 / S 0 (buy) | mid ($33.4M) | yf live 2026-09-25 |
| LASR | 40.77 | 88.86 | 90.00 / 100.00 | 118% | 7 | SB 1 / B 7 / H 1 / S 0 (strong_buy) | mid ($60.8M) | yf live 2026-09-25 |
| JKS | 9.57 | 20.44 | 16.00 / 32.61 | 114% | 7 | SB 0 / B 2 / H 4 / S 1 (none) | small ($10.5M) | yf live 2026-09-25 |
| SOUN | 6.11 | 12.57 | 12.00 / 17.00 | 106% | 7 | SB 0 / B 6 / H 2 / S 0 (strong_buy) | large ($184.1M) | yf live 2026-09-25 |
| CCCC | 2.92 | 13.33 | 11.00 / 30.00 | 357% | 6 | SB 1 / B 6 / H 0 / S 0 (none) | small ($8.9M) | yf live 2026-09-25 |
| ZURA | 4.02 | 18.00 | 18.00 / 26.00 | 348% | 6 | SB 1 / B 6 / H 0 / S 0 (strong_buy) | small ($5.4M) | yf live 2026-09-25 |
| IMRX | 4.26 | 17.17 | 15.50 / 30.00 | 303% | 6 | SB 2 / B 5 / H 0 / S 0 (strong_buy) | small ($3.4M) | yf live 2026-09-25 |
| NB | 3.54 | 11.12 | 12.00 / 15.00 | 214% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($12.0M) | yf live 2026-09-25 |
| SLN | 11.55 | 33.00 | 29.50 / 75.00 | 186% | 6 | SB 1 / B 5 / H 0 / S 1 (buy) | small ($8.3M) | yf live 2026-09-25 |
| GLUE | 11.64 | 28.50 | 27.00 / 37.00 | 145% | 6 | SB 2 / B 6 / H 0 / S 0 (none) | small ($19.4M) | yf live 2026-09-25 |
| BUR | 3.58 | 8.71 | 6.39 / 22.50 | 143% | 6 | SB 0 / B 4 / H 2 / S 0 (buy) | small ($7.9M) | yf live 2026-09-25 |
| IPX | 19.73 | 45.50 | 52.50 / 55.00 | 131% | 6 | SB 0 / B 6 / H 0 / S 0 (none) | small ($5.9M) | yf live 2026-09-25 |
| TREE | 24.35 | 56.00 | 56.50 / 70.00 | 130% | 6 | SB 3 / B 3 / H 0 / S 0 (none) | small ($10.3M) | yf live 2026-09-25 |
| KOD | 30.90 | 69.60 | 69.00 / 85.00 | 125% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | mid ($23.1M) | yf live 2026-09-25 |
| IMTX | 8.23 | 17.63 | 17.00 / 25.00 | 114% | 6 | SB 0 / B 8 / H 0 / S 0 (none) | small ($3.9M) | yf live 2026-09-25 |
| VRRM | 3.31 | 7.00 | 6.00 / 10.00 | 112% | 6 | SB 0 / B 0 / H 8 / S 0 (none) | small ($18.0M) | yf live 2026-09-25 |
| IE | 10.08 | 21.25 | 20.00 / 28.50 | 111% | 6 | SB 4 / B 3 / H 0 / S 0 (buy) | small ($18.5M) | yf live 2026-09-25 |
| ADTN | 6.97 | 14.67 | 14.50 / 21.00 | 110% | 6 | SB 1 / B 6 / H 2 / S 0 (none) | small ($17.3M) | yf live 2026-09-25 |
| QUBT | 9.18 | 18.67 | 18.00 / 32.00 | 103% | 6 | SB 0 / B 4 / H 2 / S 0 (buy) | mid ($67.5M) | stored 2026-08-10 |
| ARTV | 7.33 | 35.80 | 40.00 / 41.00 | 388% | 5 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($3.7M) | yf live 2026-09-25 |
| KYTX | 6.89 | 30.40 | 32.00 / 33.00 | 341% | 5 | SB 2 / B 4 / H 0 / S 0 (strong buy) | small ($6.5M) | stored 2026-08-10 |
| KLRA | 12.04 | 42.40 | 41.00 / 57.00 | 252% | 5 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($9.9M) | yf live 2026-09-25 |
| ELDN | 2.65 | 9.00 | 8.00 / 12.00 | 240% | 5 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($3.4M) | yf live 2026-09-25 |
| TDUP | 2.24 | 7.24 | 6.50 / 10.00 | 223% | 5 | SB 0 / B 6 / H 1 / S 0 (none) | small ($7.6M) | yf live 2026-09-25 |
| CAPR | 8.41 | 27.00 | 25.00 / 54.00 | 221% | 5 | SB 1 / B 3 / H 6 / S 0 (buy) | mid ($32.2M) | yf live 2026-09-25 |
| AIOT | 2.85 | 8.40 | 7.00 / 13.00 | 195% | 5 | SB 1 / B 5 / H 1 / S 0 (strong_buy) | small ($4.5M) | yf live 2026-09-25 |
| AURA | 6.02 | 16.60 | 15.00 / 23.00 | 176% | 5 | SB 1 / B 5 / H 0 / S 0 (none) | small ($4.0M) | yf live 2026-09-25 |
| PRTA | 8.38 | 21.40 | 20.00 / 36.00 | 155% | 5 | SB 2 / B 1 / H 2 / S 1 (none) | small ($4.2M) | yf live 2026-09-25 |
| MRT | 2.00 | 5.04 | 6.00 / 7.00 | 152% | 5 | SB 0 / B 4 / H 1 / S 0 (strong_buy) | not in panel | yf live 2026-09-25 |
| GRRR | 14.02 | 34.40 | 39.00 / 44.00 | 145% | 5 | SB 0 / B 3 / H 0 / S 0 (strong_buy) | small ($13.3M) | yf live 2026-09-25 |
| VNDA | 5.00 | 11.75 | 11.00 / 20.00 | 135% | 5 | SB 0 / B 4 / H 1 / S 0 (strong_buy) | small ($4.2M) | yf live 2026-09-25 |
| AIRJ | 4.12 | 9.55 | 9.00 / 12.00 | 132% | 5 | SB 0 / B 5 / H 1 / S 0 (strong_buy) | small ($5.1M) | yf live 2026-09-25 |
| ELVA | 6.42 | 14.60 | 14.00 / 20.00 | 127% | 5 | SB 0 / B 6 / H 0 / S 0 (none) | small ($3.8M) | yf live 2026-09-25 |
| ASMB | 23.77 | 52.00 | 52.00 / 62.00 | 119% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($6.4M) | yf live 2026-09-25 |
| MEC | 16.83 | 36.80 | 36.00 / 40.00 | 119% | 5 | SB 0 / B 5 / H 0 / S 0 (strong_buy) | small ($13.3M) | yf live 2026-09-25 |
| CBIO | 14.06 | 30.60 | 28.00 / 35.00 | 118% | 5 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | small ($4.0M) | yf live 2026-09-25 |
| UUUU | 11.36 | 24.15 | 25.00 / 32.50 | 113% | 5 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | mid ($86.8M) | yf live 2026-09-25 |
| PCT | 5.03 | 10.60 | 10.00 / 17.00 | 111% | 5 | SB 0 / B 2 / H 3 / S 0 (none) | mid ($25.5M) | yf live 2026-09-25 |
| SFIX | 2.19 | 4.60 | 5.00 / 6.00 | 110% | 5 | SB 0 / B 1 / H 4 / S 1 (hold) | small ($4.9M) | yf live 2026-09-25 |
| LINC | 23.94 | 50.20 | 50.00 / 56.00 | 110% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | mid ($23.5M) | yf live 2026-09-25 |
| REAX | 14.64 | 29.90 | 35.00 / 65.00 | 104% | 5 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($11.2M) | yf live 2026-09-25 |
| EVLV | 4.87 | 9.85 | 10.00 / 11.25 | 102% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($9.7M) | yf live 2026-09-25 |
| AEVA | 14.94 | 30.00 | 27.00 / 42.00 | 101% | 5 | SB 0 / B 3 / H 2 / S 0 (none) | mid ($26.5M) | yf live 2026-09-25 |


## 4b. Implied upside 50-100% with n ≥ 5 analysts - 365 names

| Ticker | Price | Mean target | Median / high | Implied upside | n analysts | Recommendation (SB/B/H/S) | Liquidity band (med $vol) | Count source |
|---|---|---|---|---|---|---|---|---|
| AVGO | 349.54 | 531.85 | 535.00 / 715.00 | 52% | 45 | SB 7 / B 37 / H 4 / S 0 (strong buy) | mega ($7,934.8M) | stored 2026-08-10 |
| ORCL | 138.89 | 237.97 | 240.00 / 400.00 | 71% | 41 | SB 8 / B 29 / H 6 / S 1 (buy) | mega ($4,439.5M) | stored 2026-08-10 |
| BABA | 111.61 | 185.45 | 187.91 / 238.43 | 66% | 39 | SB 8 / B 30 / H 1 / S 1 (strong_buy) | mega ($1,131.4M) | yf live 2026-09-25 |
| CRWV | 87.67 | 140.95 | 145.00 / 317.00 | 61% | 37 | SB 8 / B 21 / H 8 / S 3 (buy) | mega ($1,949.5M) | yf live 2026-09-25 |
| BKNG | 156.93 | 238.78 | 240.00 / 301.00 | 52% | 37 | SB 6 / B 26 / H 7 / S 0 (buy) | mega ($1,093.3M) | yf live 2026-09-25 |
| DKNG | 21.27 | 35.17 | 33.00 / 76.00 | 65% | 35 | SB 5 / B 24 / H 6 / S 1 (buy) | large ($248.0M) | stored 2026-08-10 |
| PINS | 18.48 | 29.05 | 29.00 / 42.36 | 57% | 35 | SB 2 / B 17 / H 19 / S 0 (buy) | large ($237.0M) | yf live 2026-09-25 |
| FLUT | 82.74 | 136.12 | 121.90 / 360.00 | 65% | 32 | SB 4 / B 18 / H 10 / S 1 (buy) | large ($249.4M) | yf live 2026-09-25 |
| BIDU | 88.05 | 146.68 | 155.07 / 206.84 | 67% | 31 | SB 6 / B 20 / H 5 / S 1 (buy) | large ($213.7M) | yf live 2026-09-25 |
| APP | 318.35 | 498.37 | 475.00 / 790.00 | 57% | 31 | SB 7 / B 20 / H 6 / S 0 (buy) | mega ($2,125.6M) | yf live 2026-09-25 |
| BILI | 14.89 | 26.74 | 26.56 / 36.10 | 80% | 30 | SB 6 / B 23 / H 1 / S 0 (strong_buy) | mid ($41.8M) | yf live 2026-09-25 |
| FSLR | 176.15 | 272.10 | 270.00 / 402.00 | 54% | 29 | SB 9 / B 14 / H 11 / S 2 (buy) | large ($402.7M) | stored 2026-08-10 |
| NBIX | 138.51 | 208.40 | 214.00 / 253.00 | 50% | 29 | SB 4 / B 20 / H 4 / S 0 (strong_buy) | large ($181.3M) | yf live 2026-09-25 |
| NXT | 79.80 | 139.18 | 146.00 / 175.00 | 74% | 28 | SB 7 / B 19 / H 3 / S 0 (strong_buy) | large ($233.1M) | yf live 2026-09-25 |
| TME | 8.30 | 13.19 | 11.68 / 26.76 | 59% | 28 | SB 2 / B 16 / H 11 / S 0 (buy) | mid ($58.1M) | yf live 2026-09-25 |
| SE | 101.84 | 157.11 | 154.00 / 195.00 | 54% | 28 | SB 6 / B 22 / H 1 / S 0 (strong_buy) | large ($471.9M) | yf live 2026-09-25 |
| ENPH | 32.89 | 51.79 | 44.00 / 212.00 | 57% | 27 | SB 3 / B 10 / H 15 / S 2 (buy) | large ($157.3M) | yf live 2026-09-25 |
| BROS | 38.58 | 75.19 | 78.00 / 95.00 | 95% | 26 | SB 4 / B 21 / H 1 / S 1 (strong_buy) | large ($192.9M) | yf live 2026-09-25 |
| XPEV | 10.29 | 19.09 | 18.65 / 25.25 | 85% | 26 | SB 7 / B 14 / H 3 / S 2 (buy) | mid ($78.6M) | yf live 2026-09-25 |
| CCL | 22.09 | 34.49 | 33.50 / 43.00 | 56% | 26 | SB 5 / B 18 / H 6 / S 0 (buy) | large ($467.5M) | yf live 2026-09-25 |
| AS | 26.93 | 47.65 | 48.20 / 67.00 | 77% | 25 | SB 6 / B 19 / H 1 / S 0 (strong_buy) | large ($163.6M) | yf live 2026-09-25 |
| CAVA | 53.26 | 83.12 | 85.00 / 110.00 | 56% | 25 | SB 4 / B 15 / H 9 / S 1 (buy) | large ($202.2M) | yf live 2026-09-25 |
| GRAB | 3.14 | 5.78 | 5.80 / 8.00 | 84% | 24 | SB 5 / B 20 / H 0 / S 0 (strong_buy) | large ($147.0M) | yf live 2026-09-25 |
| NIO | 3.63 | 6.31 | 6.02 / 10.11 | 74% | 24 | SB 5 / B 12 / H 6 / S 1 (buy) | large ($117.7M) | yf live 2026-09-25 |
| CRH | 84.31 | 134.35 | 136.00 / 165.00 | 59% | 24 | SB 5 / B 17 / H 1 / S 0 (strong_buy) | large ($415.4M) | yf live 2026-09-25 |
| MBLY | 7.78 | 11.96 | 11.50 / 27.00 | 54% | 24 | SB 5 / B 7 / H 12 / S 1 (none) | mid ($42.3M) | yf live 2026-09-25 |
| INSM | 120.09 | 199.55 | 196.50 / 243.00 | 66% | 23 | SB 5 / B 19 / H 0 / S 0 (strong_buy) | large ($249.0M) | yf live 2026-09-25 |
| IONS | 43.89 | 83.64 | 85.00 / 105.00 | 91% | 22 | SB 9 / B 9 / H 5 / S 0 (buy) | large ($162.7M) | yf live 2026-09-25 |
| ZG | 28.90 | 47.23 | 47.00 / 80.00 | 63% | 22 | SB 5 / B 7 / H 13 / S 0 (buy) | mid ($34.6M) | yf live 2026-09-25 |
| GFS | 46.54 | 76.00 | 73.50 / 140.00 | 63% | 22 | SB 4 / B 10 / H 7 / S 1 (buy) | large ($207.8M) | yf live 2026-09-25 |
| CHWY | 18.62 | 28.82 | 29.00 / 36.00 | 55% | 22 | SB 7 / B 11 / H 8 / S 0 (buy) | large ($174.2M) | yf live 2026-09-25 |
| DECK | 78.91 | 120.41 | 118.50 / 184.00 | 53% | 22 | SB 5 / B 8 / H 11 / S 3 (none) | large ($225.8M) | yf live 2026-09-25 |
| BZ | 14.32 | 21.72 | 21.80 / 27.08 | 52% | 22 | SB 5 / B 16 / H 2 / S 0 (strong_buy) | mid ($61.6M) | yf live 2026-09-25 |
| CHYM | 26.27 | 39.41 | 40.00 / 50.00 | 50% | 22 | SB 6 / B 15 / H 2 / S 0 (strong_buy) | large ($170.8M) | yf live 2026-09-25 |
| GENI | 5.73 | 11.03 | 10.50 / 20.00 | 92% | 21 | SB 3 / B 15 / H 3 / S 0 (strong_buy) | mid ($34.1M) | yf live 2026-09-25 |
| CIFR | 18.30 | 30.74 | 28.00 / 69.00 | 68% | 21 | SB 5 / B 14 / H 2 / S 0 (strong_buy) | large ($586.6M) | yf live 2026-09-25 |
| BBIO | 66.25 | 109.10 | 110.00 / 157.00 | 65% | 21 | SB 5 / B 14 / H 3 / S 0 (strong_buy) | large ($175.4M) | yf live 2026-09-25 |
| KLAR | 12.61 | 19.97 | 18.00 / 38.30 | 58% | 21 | SB 1 / B 9 / H 14 / S 0 (none) | mid ($71.1M) | yf live 2026-09-25 |
| HUT | 102.19 | 158.38 | 150.00 / 273.00 | 55% | 21 | SB 6 / B 14 / H 1 / S 0 (strong_buy) | large ($421.1M) | yf live 2026-09-25 |
| MTZ | 215.40 | 413.80 | 409.50 / 518.00 | 92% | 20 | SB 3 / B 17 / H 1 / S 0 (strong_buy) | large ($378.5M) | yf live 2026-09-25 |
| CORZ | 18.10 | 34.35 | 35.00 / 55.00 | 90% | 20 | SB 3 / B 16 / H 2 / S 0 (strong_buy) | large ($213.5M) | yf live 2026-09-25 |
| TNDM | 15.57 | 28.70 | 26.50 / 50.00 | 84% | 20 | SB 3 / B 11 / H 10 / S 0 (buy) | mid ($32.5M) | yf live 2026-09-25 |
| CYTK | 65.86 | 109.90 | 107.50 / 146.00 | 67% | 20 | SB 7 / B 13 / H 2 / S 0 (strong buy) | large ($132.3M) | stored 2026-08-10 |
| WYNN | 79.92 | 132.00 | 133.00 / 144.00 | 65% | 20 | SB 4 / B 17 / H 0 / S 0 (strong_buy) | large ($137.4M) | yf live 2026-09-25 |
| KVYO | 16.41 | 26.65 | 26.50 / 36.00 | 62% | 20 | SB 4 / B 16 / H 2 / S 0 (strong_buy) | mid ($89.2M) | yf live 2026-09-25 |
| BIRK | 31.50 | 50.78 | 50.22 / 69.41 | 61% | 20 | SB 5 / B 13 / H 5 / S 0 (buy) | mid ($69.3M) | yf live 2026-09-25 |
| ALB | 109.21 | 171.56 | 172.50 / 225.00 | 57% | 20 | SB 3 / B 10 / H 9 / S 0 (buy) | large ($275.3M) | yf live 2026-09-25 |
| YUMC | 41.10 | 61.91 | 61.00 / 77.00 | 51% | 20 | SB 6 / B 14 / H 1 / S 0 (strong_buy) | mid ($64.4M) | yf live 2026-09-25 |
| RARE | 14.79 | 28.05 | 28.00 / 40.00 | 90% | 19 | SB 2 / B 9 / H 9 / S 0 (buy) | mid ($54.3M) | yf live 2026-09-25 |
| HSAI | 16.34 | 28.35 | 28.77 / 36.22 | 74% | 19 | SB 5 / B 15 / H 0 / S 0 (strong_buy) | mid ($26.6M) | yf live 2026-09-25 |
| FICO | 868.67 | 1,434.89 | 1,525.00 / 1,750.00 | 65% | 19 | SB 5 / B 9 / H 6 / S 1 (buy) | large ($306.0M) | yf live 2026-09-25 |
| AXON | 441.19 | 704.11 | 700.00 / 830.00 | 60% | 19 | SB 8 / B 10 / H 3 / S 0 (buy) | large ($468.8M) | yf live 2026-09-25 |
| PENN | 15.34 | 24.39 | 25.00 / 30.00 | 59% | 19 | SB 3 / B 9 / H 8 / S 0 (buy) | mid ($52.7M) | yf live 2026-09-25 |
| VST | 138.81 | 217.58 | 221.00 / 305.00 | 57% | 19 | SB 4 / B 15 / H 0 / S 1 (strong_buy) | large ($610.0M) | yf live 2026-09-25 |
| CHTR | 116.85 | 179.11 | 150.00 / 380.00 | 53% | 19 | SB 0 / B 5 / H 11 / S 6 (hold) | large ($311.3M) | yf live 2026-09-25 |
| LVS | 38.84 | 59.07 | 60.00 / 71.50 | 52% | 19 | SB 3 / B 11 / H 7 / S 0 (buy) | large ($208.0M) | yf live 2026-09-25 |
| SHLS | 7.46 | 11.32 | 12.00 / 15.00 | 52% | 19 | SB 4 / B 8 / H 6 / S 1 (none) | mid ($41.0M) | yf live 2026-09-25 |
| IREN | 46.19 | 77.97 | 80.00 / 131.00 | 69% | 18 | SB 2 / B 13 / H 4 / S 0 (buy) | mega ($1,674.5M) | yf live 2026-09-25 |
| PRVA | 19.07 | 31.67 | 31.00 / 40.00 | 66% | 18 | SB 5 / B 13 / H 1 / S 0 (strong_buy) | mid ($24.8M) | yf live 2026-09-25 |
| CPNG | 14.19 | 23.51 | 24.00 / 30.00 | 66% | 18 | SB 4 / B 10 / H 3 / S 1 (buy) | large ($270.6M) | yf live 2026-09-25 |
| CRSP | 55.05 | 87.56 | 80.00 / 291.00 | 59% | 18 | SB 4 / B 9 / H 9 / S 0 (buy) | mid ($76.0M) | stored 2026-08-10 |
| ATAT | 32.42 | 49.81 | 47.20 / 60.18 | 54% | 18 | SB 4 / B 16 / H 0 / S 0 (strong_buy) | mid ($27.6M) | yf live 2026-09-25 |
| APTV | 43.70 | 66.61 | 67.50 / 78.00 | 52% | 18 | SB 5 / B 11 / H 4 / S 0 (buy) | large ($163.0M) | yf live 2026-09-25 |
| DFTX | 36.66 | 71.65 | 70.00 / 91.00 | 95% | 17 | SB 4 / B 14 / H 0 / S 0 (strong_buy) | mid ($78.9M) | yf live 2026-09-25 |
| LGN | 52.97 | 102.53 | 103.00 / 130.00 | 94% | 17 | SB 2 / B 14 / H 1 / S 0 (strong_buy) | mid ($65.7M) | yf live 2026-09-25 |
| LEU | 148.88 | 247.40 | 218.00 / 340.00 | 66% | 17 | SB 2 / B 10 / H 7 / S 0 (buy) | large ($113.9M) | yf live 2026-09-25 |
| PLNT | 40.69 | 67.54 | 64.00 / 106.00 | 66% | 17 | SB 3 / B 9 / H 6 / S 0 (buy) | mid ($87.7M) | yf live 2026-09-25 |
| GXO | 43.94 | 68.71 | 65.00 / 90.00 | 56% | 17 | SB 4 / B 12 / H 1 / S 0 (none) | mid ($62.7M) | yf live 2026-09-25 |
| STNE | 9.24 | 14.42 | 13.92 / 23.33 | 56% | 17 | SB 2 / B 7 / H 7 / S 1 (buy) | mid ($41.2M) | yf live 2026-09-25 |
| TLN | 302.63 | 460.59 | 470.00 / 560.00 | 52% | 17 | SB 6 / B 9 / H 2 / S 0 (buy) | large ($262.2M) | yf live 2026-09-25 |
| NRG | 99.00 | 188.56 | 187.00 / 270.00 | 90% | 16 | SB 3 / B 10 / H 3 / S 0 (buy) | large ($319.0M) | yf live 2026-09-25 |
| VRDN | 20.43 | 36.75 | 36.50 / 50.00 | 80% | 16 | SB 3 / B 14 / H 0 / S 0 (strong_buy) | mid ($32.7M) | yf live 2026-09-25 |
| DNLI | 20.05 | 36.06 | 35.00 / 42.00 | 80% | 16 | SB 2 / B 17 / H 1 / S 0 (strong_buy) | mid ($33.2M) | yf live 2026-09-25 |
| CMPS | 13.22 | 23.75 | 21.00 / 65.00 | 80% | 16 | SB 3 / B 12 / H 1 / S 0 (strong_buy) | mid ($35.1M) | yf live 2026-09-25 |
| MNSO | 8.94 | 14.88 | 14.55 / 21.20 | 66% | 16 | SB 2 / B 11 / H 4 / S 0 (none) | small ($7.4M) | yf live 2026-09-25 |
| UPST | 24.60 | 40.00 | 39.50 / 61.00 | 63% | 16 | SB 1 / B 6 / H 7 / S 1 (buy) | large ($110.3M) | yf live 2026-09-25 |
| GLXY | 25.32 | 40.62 | 41.50 / 57.00 | 60% | 16 | SB 5 / B 9 / H 2 / S 0 (buy) | large ($130.5M) | stored 2026-08-10 |
| BWXT | 141.19 | 223.63 | 230.00 / 290.00 | 58% | 16 | SB 3 / B 11 / H 4 / S 0 (buy) | large ($153.7M) | yf live 2026-09-25 |
| PCG | 12.31 | 19.22 | 19.50 / 24.00 | 56% | 16 | SB 2 / B 6 / H 9 / S 0 (buy) | large ($387.7M) | yf live 2026-09-25 |
| VVV | 28.34 | 43.69 | 45.00 / 49.00 | 54% | 16 | SB 1 / B 10 / H 4 / S 0 (buy) | mid ($68.6M) | yf live 2026-09-25 |
| GDS | 33.39 | 50.61 | 50.35 / 63.01 | 52% | 16 | SB 3 / B 13 / H 1 / S 0 (strong_buy) | mid ($50.7M) | yf live 2026-09-25 |
| MP | 49.46 | 74.29 | 75.00 / 100.00 | 50% | 16 | SB 5 / B 13 / H 0 / S 0 (strong buy) | large ($287.8M) | stored 2026-08-10 |
| ETOR | 26.63 | 47.73 | 46.00 / 90.00 | 79% | 15 | SB 2 / B 8 / H 5 / S 0 (buy) | mid ($29.4M) | yf live 2026-09-25 |
| TRIP | 8.22 | 13.87 | 13.00 / 21.00 | 69% | 15 | SB 1 / B 4 / H 8 / S 4 (hold) | mid ($36.6M) | yf live 2026-09-25 |
| PTON | 4.75 | 7.90 | 7.00 / 20.00 | 66% | 15 | SB 0 / B 8 / H 10 / S 2 (buy) | mid ($45.0M) | yf live 2026-09-25 |
| TTAN | 59.95 | 97.53 | 100.00 / 110.00 | 63% | 15 | SB 3 / B 12 / H 2 / S 0 (strong_buy) | large ($103.3M) | yf live 2026-09-25 |
| BHVN | 13.18 | 21.27 | 20.00 / 42.00 | 61% | 15 | SB 4 / B 9 / H 3 / S 1 (buy) | mid ($33.1M) | stored 2026-08-10 |
| PRIM | 74.02 | 117.80 | 115.00 / 165.00 | 59% | 15 | SB 3 / B 8 / H 5 / S 0 (none) | large ($101.2M) | yf live 2026-09-25 |
| NAVN | 19.45 | 30.87 | 30.00 / 38.00 | 59% | 15 | SB 4 / B 11 / H 0 / S 0 (strong_buy) | mid ($81.1M) | yf live 2026-09-25 |
| KGS | 52.48 | 83.13 | 83.00 / 93.00 | 58% | 15 | SB 5 / B 10 / H 0 / S 0 (strong_buy) | large ($105.7M) | yf live 2026-09-25 |
| PVLA | 146.96 | 230.53 | 232.00 / 270.00 | 57% | 15 | SB 0 / B 15 / H 0 / S 0 (strong_buy) | mid ($28.8M) | yf live 2026-09-25 |
| CX | 9.60 | 14.81 | 15.00 / 20.00 | 54% | 15 | SB 7 / B 4 / H 4 / S 0 (buy) | mid ($66.3M) | yf live 2026-09-25 |
| DNTH | 91.65 | 140.80 | 134.00 / 200.00 | 54% | 15 | SB 1 / B 15 / H 0 / S 0 (strong_buy) | mid ($81.2M) | yf live 2026-09-25 |
| YMM | 8.23 | 12.55 | 12.14 / 16.26 | 52% | 15 | SB 4 / B 9 / H 2 / S 0 (none) | mid ($52.0M) | yf live 2026-09-25 |
| VNET | 6.93 | 13.63 | 13.41 / 25.04 | 97% | 14 | SB 4 / B 9 / H 0 / S 1 (strong_buy) | mid ($25.7M) | yf live 2026-09-25 |
| ARVN | 7.43 | 13.93 | 13.00 / 21.00 | 87% | 14 | SB 2 / B 5 / H 8 / S 1 (buy) | small ($5.3M) | yf live 2026-09-25 |
| PHVS | 32.70 | 57.88 | 60.69 / 77.33 | 77% | 14 | SB 3 / B 10 / H 1 / S 0 (strong_buy) | small ($17.7M) | yf live 2026-09-25 |
| BOOT | 126.44 | 221.50 | 213.50 / 282.00 | 75% | 14 | SB 2 / B 13 / H 1 / S 0 (strong_buy) | mid ($97.3M) | yf live 2026-09-25 |
| ALGT | 75.95 | 127.50 | 123.00 / 165.00 | 68% | 14 | SB 2 / B 9 / H 3 / S 0 (buy) | mid ($47.8M) | yf live 2026-09-25 |
| PTCT | 61.93 | 101.79 | 101.00 / 137.00 | 64% | 14 | SB 4 / B 8 / H 1 / S 1 (buy) | mid ($74.4M) | yf live 2026-09-25 |
| JBS | 11.28 | 18.09 | 17.97 / 20.65 | 60% | 14 | SB 5 / B 7 / H 2 / S 0 (buy) | mid ($61.9M) | yf live 2026-09-25 |
| IMNM | 22.50 | 36.00 | 36.00 / 40.00 | 60% | 14 | SB 3 / B 12 / H 0 / S 0 (strong_buy) | mid ($24.9M) | yf live 2026-09-25 |
| MKSI | 258.72 | 410.86 | 405.00 / 600.00 | 59% | 14 | SB 3 / B 9 / H 1 / S 1 (buy) | large ($382.0M) | yf live 2026-09-25 |
| ATEC | 9.95 | 15.79 | 15.00 / 24.00 | 59% | 14 | SB 3 / B 11 / H 0 / S 0 (none) | small ($17.5M) | yf live 2026-09-25 |
| IRTC | 111.13 | 176.14 | 177.50 / 196.00 | 59% | 14 | SB 2 / B 13 / H 0 / S 0 (strong_buy) | mid ($62.6M) | yf live 2026-09-25 |
| SARO | 22.57 | 35.24 | 35.00 / 42.40 | 56% | 14 | SB 2 / B 9 / H 4 / S 0 (buy) | mid ($89.1M) | yf live 2026-09-25 |
| MIRM | 88.98 | 138.21 | 137.00 / 183.00 | 55% | 14 | SB 4 / B 10 / H 0 / S 0 (strong_buy) | mid ($61.3M) | yf live 2026-09-25 |
| QFIN | 7.53 | 14.80 | 14.04 / 23.02 | 97% | 13 | SB 3 / B 5 / H 3 / S 2 (buy) | small ($15.4M) | yf live 2026-09-25 |
| STOK | 25.73 | 46.46 | 44.00 / 60.00 | 81% | 13 | SB 2 / B 12 / H 0 / S 0 (none) | mid ($20.6M) | yf live 2026-09-25 |
| BTDR | 12.14 | 21.77 | 21.00 / 35.00 | 79% | 13 | SB 3 / B 9 / H 1 / S 0 (strong_buy) | large ($126.0M) | yf live 2026-09-25 |
| BCAX | 19.73 | 34.54 | 35.00 / 45.00 | 75% | 13 | SB 3 / B 10 / H 2 / S 0 (none) | small ($13.2M) | yf live 2026-09-25 |
| SMMT | 16.37 | 28.55 | 32.73 / 40.77 | 74% | 13 | SB 1 / B 10 / H 6 / S 0 (buy) | mid ($62.7M) | yf live 2026-09-25 |
| BOBS | 13.63 | 22.92 | 22.00 / 28.00 | 68% | 13 | SB 4 / B 7 / H 2 / S 0 (none) | small ($12.8M) | yf live 2026-09-25 |
| CLSK | 14.24 | 23.81 | 24.00 / 27.00 | 67% | 13 | SB 4 / B 9 / H 0 / S 0 (strong_buy) | large ($250.4M) | yf live 2026-09-25 |
| ARWR | 66.23 | 110.00 | 106.00 / 126.00 | 66% | 13 | SB 4 / B 9 / H 1 / S 0 (strong_buy) | large ($131.5M) | yf live 2026-09-25 |
| FUN | 12.50 | 20.69 | 22.00 / 28.00 | 66% | 13 | SB 2 / B 6 / H 5 / S 1 (buy) | mid ($34.1M) | yf live 2026-09-25 |
| EVH | 3.56 | 5.77 | 6.00 / 8.00 | 62% | 13 | SB 4 / B 8 / H 3 / S 0 (none) | small ($11.7M) | yf live 2026-09-25 |
| LBRT | 18.21 | 29.42 | 29.00 / 36.00 | 62% | 13 | SB 3 / B 5 / H 5 / S 0 (buy) | mid ($76.2M) | yf live 2026-09-25 |
| ORIC | 13.12 | 21.08 | 22.00 / 27.00 | 61% | 13 | SB 2 / B 12 / H 1 / S 0 (strong_buy) | small ($15.3M) | yf live 2026-09-25 |
| AGL | 75.28 | 118.08 | 116.00 / 146.00 | 57% | 13 | SB 0 / B 5 / H 10 / S 1 (buy) | mid ($26.8M) | yf live 2026-09-25 |
| SLGN | 35.95 | 55.31 | 57.00 / 61.00 | 54% | 13 | SB 3 / B 9 / H 1 / S 0 (none) | mid ($41.6M) | yf live 2026-09-25 |
| RLAY | 17.62 | 27.08 | 26.00 / 32.00 | 54% | 13 | SB 3 / B 11 / H 0 / S 0 (strong_buy) | mid ($51.5M) | yf live 2026-09-25 |
| IONQ | 44.11 | 67.14 | 65.00 / 100.00 | 52% | 13 | SB 1 / B 10 / H 2 / S 0 (strong_buy) | large ($728.4M) | yf live 2026-09-25 |
| LBTYA | 9.58 | 14.58 | 12.00 / 25.00 | 52% | 13 | SB 0 / B 4 / H 8 / S 1 (buy) | mid ($21.2M) | yf live 2026-09-25 |
| WSE | 11.21 | 16.94 | 16.90 / 19.50 | 51% | 13 | SB 3 / B 9 / H 1 / S 0 (strong_buy) | small ($14.1M) | yf live 2026-09-25 |
| MLCO | 4.68 | 7.06 | 7.00 / 9.40 | 51% | 13 | SB 2 / B 7 / H 4 / S 0 (buy) | small ($9.8M) | yf live 2026-09-25 |
| JACK | 13.32 | 20.00 | 20.00 / 36.00 | 50% | 13 | SB 1 / B 3 / H 13 / S 0 (none) | small ($10.8M) | yf live 2026-09-25 |
| FTH | 28.62 | 56.67 | 56.00 / 70.00 | 98% | 12 | SB 3 / B 11 / H 0 / S 0 (strong_buy) | small ($7.7M) | yf live 2026-09-25 |
| QNT | 49.41 | 97.17 | 94.00 / 155.00 | 97% | 12 | SB 2 / B 10 / H 1 / S 0 (strong_buy) | mid ($83.4M) | yf live 2026-09-25 |
| RAPP | 32.87 | 62.88 | 59.00 / 80.00 | 91% | 12 | SB 1 / B 12 / H 0 / S 0 (strong_buy) | small ($13.2M) | yf live 2026-09-25 |
| RSI | 19.51 | 35.83 | 36.00 / 40.00 | 84% | 12 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | mid ($64.8M) | yf live 2026-09-25 |
| ORKA | 85.25 | 155.00 | 155.50 / 200.00 | 82% | 12 | SB 2 / B 11 / H 0 / S 0 (strong_buy) | mid ($74.2M) | yf live 2026-09-25 |
| BRBR | 8.12 | 14.71 | 14.50 / 20.00 | 81% | 12 | SB 2 / B 6 / H 5 / S 1 (buy) | mid ($40.5M) | yf live 2026-09-25 |
| ACHV | 7.73 | 13.83 | 12.50 / 21.00 | 79% | 12 | SB 3 / B 8 / H 0 / S 0 (none) | small ($10.3M) | yf live 2026-09-25 |
| RGTI | 16.34 | 28.81 | 30.00 / 40.00 | 76% | 12 | SB 1 / B 8 / H 4 / S 0 (buy) | large ($317.8M) | stored 2026-08-10 |
| DCH | 5.30 | 9.30 | 9.00 / 17.00 | 75% | 12 | SB 2 / B 4 / H 7 / S 0 (buy) | small ($16.6M) | yf live 2026-09-25 |
| ABVX | 94.15 | 164.00 | 164.00 / 181.00 | 74% | 12 | SB 4 / B 8 / H 0 / S 0 (strong_buy) | large ($124.6M) | yf live 2026-09-25 |
| PUMP | 9.69 | 16.62 | 17.75 / 21.00 | 72% | 12 | SB 4 / B 5 / H 4 / S 0 (buy) | mid ($38.0M) | yf live 2026-09-25 |
| CSIQ | 10.76 | 17.85 | 16.07 / 30.00 | 66% | 12 | SB 1 / B 3 / H 6 / S 2 (hold) | mid ($29.0M) | yf live 2026-09-25 |
| COMP | 9.32 | 15.42 | 15.50 / 18.00 | 65% | 12 | SB 3 / B 6 / H 3 / S 0 (buy) | large ($128.1M) | yf live 2026-09-25 |
| CHDN | 79.37 | 130.83 | 128.00 / 157.00 | 65% | 12 | SB 3 / B 9 / H 0 / S 0 (strong_buy) | mid ($79.1M) | yf live 2026-09-25 |
| AESI | 11.13 | 18.17 | 18.00 / 25.00 | 63% | 12 | SB 2 / B 4 / H 4 / S 2 (buy) | mid ($39.5M) | yf live 2026-09-25 |
| IRON | 65.42 | 103.17 | 100.00 / 128.00 | 58% | 12 | SB 1 / B 12 / H 0 / S 0 (strong_buy) | mid ($29.7M) | yf live 2026-09-25 |
| SPXC | 173.68 | 270.67 | 280.00 / 310.00 | 56% | 12 | SB 1 / B 10 / H 1 / S 0 (strong_buy) | mid ($86.6M) | yf live 2026-09-25 |
| AEIS | 275.79 | 429.08 | 412.50 / 535.00 | 56% | 12 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | large ($167.8M) | yf live 2026-09-25 |
| WHR | 32.67 | 50.67 | 42.50 / 137.00 | 55% | 12 | SB 0 / B 1 / H 9 / S 3 (hold) | mid ($85.0M) | yf live 2026-09-25 |
| GSHD | 44.48 | 68.92 | 72.00 / 100.00 | 55% | 12 | SB 3 / B 3 / H 6 / S 1 (none) | mid ($24.2M) | yf live 2026-09-25 |
| ZYME | 26.70 | 41.23 | 38.00 / 60.00 | 54% | 12 | SB 2 / B 10 / H 0 / S 0 (strong buy) | small ($14.3M) | stored 2026-08-10 |
| RCUS | 25.16 | 38.75 | 42.50 / 47.00 | 54% | 12 | SB 0 / B 11 / H 3 / S 0 (strong_buy) | mid ($33.8M) | yf live 2026-09-25 |
| AN | 163.55 | 245.67 | 249.00 / 300.00 | 50% | 12 | SB 4 / B 7 / H 2 / S 0 (buy) | mid ($79.2M) | yf live 2026-09-25 |
| AMTM | 19.71 | 29.58 | 28.00 / 40.00 | 50% | 12 | SB 2 / B 3 / H 6 / S 1 (buy) | mid ($38.6M) | yf live 2026-09-25 |
| FDMT | 13.94 | 27.82 | 28.00 / 37.00 | 100% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | small ($9.4M) | yf live 2026-09-25 |
| TRVI | 14.37 | 28.18 | 25.00 / 40.00 | 96% | 11 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | mid ($31.9M) | yf live 2026-09-25 |
| ACRS | 5.24 | 10.18 | 10.00 / 16.00 | 94% | 11 | SB 1 / B 10 / H 1 / S 0 (strong_buy) | small ($9.4M) | yf live 2026-09-25 |
| CCOI | 7.87 | 15.27 | 12.00 / 30.00 | 94% | 11 | SB 0 / B 4 / H 6 / S 2 (buy) | small ($16.7M) | yf live 2026-09-25 |
| ESAB | 68.32 | 128.73 | 130.00 / 145.00 | 88% | 11 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | mid ($56.5M) | yf live 2026-09-25 |
| TNGX | 24.01 | 45.18 | 40.00 / 69.00 | 88% | 11 | SB 1 / B 10 / H 1 / S 0 (strong_buy) | mid ($57.3M) | yf live 2026-09-25 |
| FWRG | 10.25 | 19.27 | 20.00 / 22.00 | 88% | 11 | SB 1 / B 10 / H 0 / S 0 (strong_buy) | small ($12.4M) | yf live 2026-09-25 |
| DY | 277.84 | 520.91 | 525.00 / 625.00 | 87% | 11 | SB 1 / B 10 / H 0 / S 0 (strong_buy) | large ($191.8M) | yf live 2026-09-25 |
| COGT | 31.06 | 55.82 | 55.00 / 62.00 | 80% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | mid ($63.4M) | yf live 2026-09-25 |
| MWH | 25.20 | 44.55 | 43.00 / 55.00 | 77% | 11 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | mid ($45.8M) | yf live 2026-09-25 |
| QURE | 38.82 | 68.31 | 68.74 / 92.99 | 76% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | mid ($52.0M) | yf live 2026-09-25 |
| ADNT | 17.14 | 29.55 | 26.00 / 64.00 | 72% | 11 | SB 2 / B 6 / H 3 / S 1 (buy) | small ($16.7M) | yf live 2026-09-25 |
| EYE | 16.49 | 28.18 | 27.00 / 35.00 | 71% | 11 | SB 1 / B 8 / H 3 / S 0 (buy) | mid ($36.3M) | yf live 2026-09-25 |
| TIGR | 4.68 | 7.71 | 7.30 / 14.50 | 65% | 11 | SB 2 / B 8 / H 0 / S 1 (buy) | small ($9.9M) | yf live 2026-09-25 |
| SAH | 61.75 | 98.55 | 98.00 / 139.00 | 60% | 11 | SB 2 / B 4 / H 4 / S 2 (buy) | small ($19.9M) | yf live 2026-09-25 |
| PATK | 67.74 | 108.00 | 114.00 / 130.00 | 59% | 11 | SB 2 / B 6 / H 2 / S 1 (buy) | mid ($43.9M) | yf live 2026-09-25 |
| ALGM | 34.72 | 54.82 | 55.00 / 62.00 | 58% | 11 | SB 2 / B 9 / H 1 / S 0 (strong_buy) | mid ($89.4M) | yf live 2026-09-25 |
| HGV | 35.44 | 55.45 | 51.00 / 74.00 | 56% | 11 | SB 1 / B 3 / H 7 / S 0 (none) | mid ($47.6M) | yf live 2026-09-25 |
| PGY | 18.49 | 28.91 | 27.00 / 36.00 | 56% | 11 | SB 2 / B 9 / H 0 / S 0 (strong_buy) | mid ($48.9M) | yf live 2026-09-25 |
| RBA | 82.59 | 128.64 | 130.00 / 152.00 | 56% | 11 | SB 5 / B 6 / H 1 / S 0 (buy) | large ($134.5M) | yf live 2026-09-25 |
| SVV | 9.13 | 14.23 | 14.00 / 20.00 | 56% | 11 | SB 0 / B 8 / H 4 / S 0 (buy) | small ($9.9M) | yf live 2026-09-25 |
| PRMB | 19.66 | 30.36 | 31.00 / 35.00 | 54% | 11 | SB 5 / B 5 / H 2 / S 0 (buy) | mid ($80.1M) | yf live 2026-09-25 |
| WOOF | 2.31 | 3.56 | 3.50 / 5.00 | 54% | 11 | SB 1 / B 1 / H 8 / S 2 (none) | small ($4.4M) | yf live 2026-09-25 |
| PAM | 79.62 | 121.09 | 118.00 / 160.00 | 52% | 11 | SB 2 / B 7 / H 2 / S 0 (buy) | small ($13.2M) | yf live 2026-09-25 |
| WY | 20.56 | 31.00 | 30.00 / 38.00 | 51% | 11 | SB 2 / B 7 / H 3 / S 0 (none) | large ($120.4M) | yf live 2026-09-25 |
| INIO | 19.30 | 38.20 | 40.00 / 47.00 | 98% | 10 | SB 4 / B 4 / H 2 / S 0 (buy) | large ($105.2M) | yf live 2026-09-25 |
| AMRC | 21.63 | 42.70 | 39.00 / 62.00 | 97% | 10 | SB 1 / B 7 / H 4 / S 0 (buy) | small ($14.0M) | yf live 2026-09-25 |
| PL | 17.45 | 33.40 | 35.00 / 50.00 | 91% | 10 | SB 1 / B 6 / H 4 / S 0 (buy) | large ($142.7M) | yf live 2026-09-25 |
| BLDP | 2.11 | 4.02 | 3.55 / 6.50 | 91% | 10 | SB 0 / B 3 / H 8 / S 1 (hold) | small ($10.0M) | yf live 2026-09-25 |
| EQPT | 17.47 | 33.20 | 35.00 / 55.00 | 90% | 10 | SB 1 / B 6 / H 4 / S 0 (buy) | mid ($48.7M) | yf live 2026-09-25 |
| UEC | 9.46 | 17.38 | 16.50 / 26.75 | 84% | 10 | SB 2 / B 6 / H 2 / S 0 (none) | mid ($80.6M) | yf live 2026-09-25 |
| PTLO | 3.63 | 6.22 | 5.50 / 11.00 | 71% | 10 | SB 1 / B 3 / H 9 / S 0 (none) | small ($5.1M) | yf live 2026-09-25 |
| NEXN | 8.57 | 14.64 | 13.00 / 25.40 | 71% | 10 | SB 5 / B 4 / H 0 / S 0 (none) | small ($4.3M) | yf live 2026-09-25 |
| FLY | 22.72 | 38.60 | 36.00 / 50.00 | 70% | 10 | SB 1 / B 6 / H 3 / S 0 (buy) | mid ($65.0M) | yf live 2026-09-25 |
| GGAL | 39.70 | 67.37 | 60.00 / 103.00 | 70% | 10 | SB 3 / B 3 / H 4 / S 0 (none) | mid ($35.2M) | yf live 2026-09-25 |
| INTR | 5.07 | 8.57 | 8.79 / 11.60 | 69% | 10 | SB 2 / B 5 / H 2 / S 1 (buy) | mid ($23.7M) | yf live 2026-09-25 |
| MNTN | 10.89 | 18.10 | 18.00 / 22.00 | 66% | 10 | SB 3 / B 6 / H 1 / S 0 (none) | small ($10.2M) | yf live 2026-09-25 |
| RRX | 150.47 | 248.20 | 242.50 / 275.00 | 65% | 10 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | large ($207.5M) | yf live 2026-09-25 |
| WSC | 17.84 | 29.40 | 29.00 / 37.00 | 65% | 10 | SB 0 / B 3 / H 7 / S 0 (buy) | mid ($51.0M) | yf live 2026-09-25 |
| KEEL | 3.92 | 6.45 | 6.00 / 10.00 | 65% | 10 | SB 2 / B 8 / H 1 / S 0 (strong_buy) | large ($126.5M) | yf live 2026-09-25 |
| ELVN | 45.56 | 73.90 | 74.00 / 82.00 | 62% | 10 | SB 1 / B 11 / H 0 / S 0 (none) | mid ($48.1M) | yf live 2026-09-25 |
| MBX | 54.79 | 88.10 | 88.00 / 121.00 | 61% | 10 | SB 3 / B 8 / H 0 / S 0 (strong_buy) | mid ($35.5M) | yf live 2026-09-25 |
| MMYT | 46.94 | 75.40 | 75.00 / 85.00 | 61% | 10 | SB 0 / B 10 / H 0 / S 0 (strong_buy) | mid ($39.6M) | yf live 2026-09-25 |
| PPLI | 36.18 | 57.50 | 54.00 / 70.00 | 59% | 10 | SB 2 / B 6 / H 4 / S 0 (buy) | mid ($36.9M) | yf live 2026-09-25 |
| ARCT | 14.05 | 22.30 | 21.00 / 41.00 | 59% | 10 | SB 1 / B 10 / H 2 / S 0 (strong_buy) | small ($4.4M) | yf live 2026-09-25 |
| CSQR | 18.00 | 28.50 | 26.50 / 46.00 | 58% | 10 | SB 3 / B 6 / H 1 / S 0 (none) | mid ($20.7M) | yf live 2026-09-25 |
| BV | 9.96 | 15.45 | 15.00 / 24.00 | 55% | 10 | SB 1 / B 7 / H 2 / S 1 (buy) | small ($10.1M) | yf live 2026-09-25 |
| VTEX | 3.60 | 5.57 | 4.75 / 12.00 | 55% | 10 | SB 1 / B 3 / H 6 / S 0 (none) | small ($3.0M) | yf live 2026-09-25 |
| STRZ | 23.02 | 35.20 | 36.00 / 45.00 | 53% | 10 | SB 2 / B 4 / H 4 / S 0 (buy) | small ($4.4M) | yf live 2026-09-25 |
| LCII | 84.30 | 127.70 | 122.50 / 175.00 | 51% | 10 | SB 1 / B 4 / H 6 / S 0 (none) | mid ($32.4M) | yf live 2026-09-25 |
| KTB | 64.53 | 97.50 | 104.00 / 136.00 | 51% | 10 | SB 2 / B 5 / H 2 / S 1 (buy) | mid ($54.0M) | yf live 2026-09-25 |
| AVBP | 29.69 | 44.70 | 45.00 / 50.00 | 51% | 10 | SB 0 / B 11 / H 0 / S 0 (strong_buy) | small ($13.8M) | yf live 2026-09-25 |
| LAC | 2.83 | 5.61 | 4.50 / 10.00 | 99% | 9 | SB 2 / B 1 / H 9 / S 0 (hold) | mid ($26.6M) | yf live 2026-09-25 |
| EOSE | 3.29 | 6.50 | 5.00 / 10.00 | 98% | 9 | SB 1 / B 3 / H 7 / S 0 (buy) | mid ($96.8M) | yf live 2026-09-25 |
| VIR | 10.52 | 20.78 | 20.00 / 30.00 | 98% | 9 | SB 3 / B 7 / H 0 / S 0 (none) | small ($16.7M) | yf live 2026-09-25 |
| AQST | 4.73 | 9.33 | 10.00 / 11.00 | 97% | 9 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($9.8M) | yf live 2026-09-25 |
| HROW | 33.00 | 65.00 | 60.00 / 88.00 | 97% | 9 | SB 0 / B 9 / H 0 / S 0 (strong_buy) | small ($19.5M) | yf live 2026-09-25 |
| AVEX | 16.95 | 32.78 | 34.00 / 45.00 | 93% | 9 | SB 4 / B 5 / H 1 / S 0 (buy) | mid ($24.5M) | yf live 2026-09-25 |
| RZLT | 3.98 | 7.67 | 6.00 / 14.00 | 93% | 9 | SB 2 / B 6 / H 2 / S 0 (buy) | small ($5.8M) | yf live 2026-09-25 |
| PCVX | 56.73 | 109.00 | 110.00 / 163.00 | 92% | 9 | SB 1 / B 9 / H 1 / S 0 (strong_buy) | mid ($61.8M) | yf live 2026-09-25 |
| LCID | 4.17 | 7.94 | 7.00 / 17.00 | 91% | 9 | SB 0 / B 1 / H 7 / S 3 (hold) | mid ($56.2M) | yf live 2026-09-25 |
| ACHR | 5.65 | 10.61 | 11.00 / 18.00 | 88% | 9 | SB 2 / B 4 / H 3 / S 0 (none) | large ($148.9M) | yf live 2026-09-25 |
| VSTM | 7.84 | 14.67 | 14.00 / 18.00 | 87% | 9 | SB 1 / B 9 / H 0 / S 0 (strong_buy) | small ($13.4M) | yf live 2026-09-25 |
| FN | 401.77 | 734.11 | 750.00 / 850.00 | 83% | 9 | SB 3 / B 4 / H 2 / S 0 (buy) | large ($374.2M) | yf live 2026-09-25 |
| AKTS | 19.84 | 35.39 | 35.00 / 40.00 | 78% | 9 | SB 1 / B 9 / H 0 / S 0 (none) | small ($6.8M) | yf live 2026-09-25 |
| GHRS | 24.22 | 42.89 | 40.00 / 65.00 | 77% | 9 | SB 2 / B 7 / H 0 / S 0 (none) | small ($5.0M) | yf live 2026-09-25 |
| ERAS | 13.94 | 24.11 | 22.00 / 33.00 | 73% | 9 | SB 2 / B 5 / H 2 / S 0 (none) | mid ($67.8M) | yf live 2026-09-25 |
| AERO | 15.54 | 26.82 | 27.00 / 30.00 | 73% | 9 | SB 4 / B 4 / H 1 / S 0 (buy) | small ($3.9M) | yf live 2026-09-25 |
| JOBY | 6.21 | 10.68 | 11.50 / 18.00 | 72% | 9 | SB 1 / B 2 / H 5 / S 3 (hold) | large ($227.9M) | yf live 2026-09-25 |
| MAIR | 24.66 | 41.89 | 41.00 / 49.00 | 70% | 9 | SB 1 / B 8 / H 2 / S 0 (none) | mid ($58.4M) | yf live 2026-09-25 |
| KRUS | 38.25 | 64.89 | 65.00 / 85.00 | 70% | 9 | SB 0 / B 6 / H 4 / S 0 (buy) | small ($9.5M) | yf live 2026-09-25 |
| ITG | 10.44 | 17.56 | 17.00 / 20.00 | 68% | 9 | SB 1 / B 8 / H 0 / S 0 (none) | small ($3.0M) | yf live 2026-09-25 |
| OI | 5.89 | 9.59 | 9.00 / 13.00 | 63% | 9 | SB 0 / B 5 / H 3 / S 1 (buy) | mid ($20.4M) | yf live 2026-09-25 |
| STEP | 43.76 | 69.56 | 65.00 / 92.00 | 59% | 9 | SB 3 / B 5 / H 1 / S 0 (none) | mid ($53.2M) | yf live 2026-09-25 |
| COUR | 5.15 | 8.17 | 8.00 / 10.00 | 59% | 9 | SB 3 / B 4 / H 4 / S 0 (none) | mid ($27.7M) | yf live 2026-09-25 |
| FLOC | 19.32 | 30.56 | 31.00 / 34.00 | 58% | 9 | SB 3 / B 5 / H 1 / S 0 (buy) | small ($9.9M) | yf live 2026-09-25 |
| BMA | 71.27 | 111.88 | 108.49 / 149.32 | 57% | 9 | SB 3 / B 5 / H 1 / S 0 (buy) | mid ($20.3M) | yf live 2026-09-25 |
| RELY | 20.70 | 32.33 | 32.00 / 36.00 | 56% | 9 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | mid ($72.8M) | yf live 2026-09-25 |
| ARCO | 7.27 | 11.29 | 11.50 / 14.00 | 55% | 9 | SB 4 / B 4 / H 1 / S 0 (none) | small ($8.3M) | yf live 2026-09-25 |
| OLED | 74.36 | 115.37 | 115.00 / 158.00 | 55% | 9 | SB 1 / B 5 / H 3 / S 0 (none) | mid ($58.0M) | yf live 2026-09-25 |
| ESTA | 66.39 | 102.44 | 105.00 / 117.00 | 54% | 9 | SB 2 / B 7 / H 0 / S 0 (none) | mid ($34.0M) | yf live 2026-09-25 |
| ASTH | 33.98 | 51.67 | 53.00 / 65.00 | 52% | 9 | SB 2 / B 7 / H 1 / S 0 (strong_buy) | small ($19.6M) | yf live 2026-09-25 |
| CIGI | 91.65 | 139.22 | 145.00 / 160.00 | 52% | 9 | SB 4 / B 5 / H 4 / S 0 (buy) | mid ($22.6M) | yf live 2026-09-25 |
| SGI | 62.10 | 93.44 | 95.00 / 105.00 | 50% | 9 | SB 2 / B 8 / H 0 / S 0 (strong_buy) | large ($178.4M) | yf live 2026-09-25 |
| GIL | 41.23 | 82.00 | 82.00 / 111.00 | 99% | 8 | SB 5 / B 6 / H 2 / S 0 (buy) | mid ($55.6M) | yf live 2026-09-25 |
| CADL | 11.01 | 21.75 | 22.50 / 29.00 | 98% | 8 | SB 0 / B 9 / H 0 / S 0 (strong_buy) | small ($12.6M) | yf live 2026-09-25 |
| IMMX | 11.48 | 22.52 | 24.00 / 27.00 | 96% | 8 | SB 3 / B 4 / H 0 / S 0 (strong_buy) | small ($16.2M) | yf live 2026-09-25 |
| INDI | 3.02 | 5.72 | 6.00 / 8.00 | 89% | 8 | SB 1 / B 5 / H 2 / S 0 (buy) | small ($18.6M) | yf live 2026-09-25 |
| LUNR | 15.79 | 29.50 | 29.00 / 43.00 | 87% | 8 | SB 0 / B 8 / H 0 / S 1 (none) | large ($134.3M) | yf live 2026-09-25 |
| EROC | 12.10 | 22.50 | 22.50 / 28.00 | 86% | 8 | SB 4 / B 4 / H 0 / S 0 (none) | mid ($22.0M) | yf live 2026-09-25 |
| MLYS | 26.30 | 48.50 | 52.00 / 56.00 | 84% | 8 | SB 0 / B 9 / H 1 / S 0 (none) | mid ($22.5M) | yf live 2026-09-25 |
| PAR | 14.11 | 25.31 | 26.50 / 33.00 | 79% | 8 | SB 1 / B 6 / H 2 / S 0 (buy) | small ($15.3M) | yf live 2026-09-25 |
| TLRY | 4.11 | 7.34 | 5.50 / 17.00 | 79% | 8 | SB 0 / B 1 / H 2 / S 0 (buy) | small ($15.7M) | yf live 2026-09-25 |
| AORT | 23.57 | 42.15 | 42.00 / 48.00 | 79% | 8 | SB 2 / B 6 / H 0 / S 0 (strong_buy) | small ($16.5M) | yf live 2026-09-25 |
| ZBIO | 26.36 | 47.00 | 45.00 / 59.00 | 78% | 8 | SB 0 / B 7 / H 1 / S 0 (strong_buy) | mid ($21.1M) | yf live 2026-09-25 |
| FUBO | 9.63 | 17.00 | 17.00 / 23.00 | 77% | 8 | SB 3 / B 5 / H 2 / S 0 (buy) | small ($13.3M) | yf live 2026-09-25 |
| GMRS | 10.77 | 18.88 | 17.50 / 30.00 | 75% | 8 | SB 2 / B 5 / H 1 / S 0 (strong_buy) | small ($7.0M) | yf live 2026-09-25 |
| LMRI | 10.05 | 17.57 | 17.00 / 23.00 | 75% | 8 | SB 2 / B 7 / H 0 / S 0 (strong_buy) | small ($4.0M) | yf live 2026-09-25 |
| KNF | 52.94 | 91.44 | 90.00 / 118.00 | 73% | 8 | SB 1 / B 4 / H 2 / S 1 (buy) | mid ($44.1M) | yf live 2026-09-25 |
| HLMN | 7.02 | 12.12 | 12.00 / 14.00 | 73% | 8 | SB 2 / B 4 / H 2 / S 0 (buy) | small ($9.6M) | yf live 2026-09-25 |
| ANAB | 51.25 | 88.50 | 79.50 / 140.00 | 73% | 8 | SB 3 / B 5 / H 0 / S 0 (strong_buy) | mid ($24.1M) | yf live 2026-09-25 |
| BRSL | 9.77 | 16.61 | 16.50 / 21.00 | 70% | 8 | SB 0 / B 6 / H 3 / S 0 (buy) | small ($17.3M) | yf live 2026-09-25 |
| INR | 13.31 | 22.12 | 22.50 / 26.00 | 66% | 8 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | small ($3.5M) | yf live 2026-09-25 |
| BKSY | 23.27 | 38.42 | 36.00 / 50.00 | 65% | 8 | SB 0 / B 5 / H 1 / S 0 (strong_buy) | mid ($26.2M) | yf live 2026-09-25 |
| SGHC | 11.94 | 19.50 | 19.50 / 22.00 | 63% | 8 | SB 2 / B 6 / H 0 / S 0 (strong_buy) | mid ($32.6M) | yf live 2026-09-25 |
| TROX | 4.13 | 6.75 | 6.75 / 11.00 | 63% | 8 | SB 0 / B 1 / H 4 / S 3 (hold) | small ($13.6M) | yf live 2026-09-25 |
| UMAC | 24.07 | 39.00 | 40.00 / 45.00 | 62% | 8 | SB 3 / B 5 / H 0 / S 0 (none) | mid ($66.9M) | yf live 2026-09-25 |
| HAPN | 15.33 | 24.75 | 25.00 / 29.00 | 61% | 8 | SB 4 / B 4 / H 0 / S 0 (strong_buy) | mid ($23.8M) | yf live 2026-09-25 |
| MNR | 10.56 | 17.00 | 17.00 / 20.00 | 61% | 8 | SB 0 / B 7 / H 2 / S 0 (strong_buy) | small ($3.7M) | yf live 2026-09-25 |
| RXST | 4.77 | 7.57 | 6.65 / 11.00 | 59% | 8 | SB 1 / B 0 / H 7 / S 2 (hold) | small ($4.5M) | yf live 2026-09-25 |
| BRSP | 4.00 | 6.34 | 6.50 / 7.00 | 58% | 8 | SB 2 / B 4 / H 0 / S 2 (none) | small ($6.5M) | yf live 2026-09-25 |
| CXM | 5.34 | 8.44 | 8.00 / 12.00 | 58% | 8 | SB 1 / B 2 / H 5 / S 1 (hold) | small ($17.8M) | yf live 2026-09-25 |
| BLBD | 56.62 | 89.12 | 89.50 / 95.00 | 57% | 8 | SB 2 / B 6 / H 0 / S 0 (strong_buy) | mid ($30.1M) | yf live 2026-09-25 |
| CRS | 398.15 | 625.88 | 614.00 / 700.00 | 57% | 8 | SB 1 / B 6 / H 1 / S 0 (none) | large ($335.7M) | yf live 2026-09-25 |
| LQDA | 68.85 | 107.75 | 109.00 / 130.00 | 56% | 8 | SB 1 / B 5 / H 2 / S 0 (none) | mid ($95.2M) | yf live 2026-09-25 |
| PTRN | 18.09 | 28.12 | 28.50 / 31.00 | 55% | 8 | SB 2 / B 6 / H 1 / S 0 (none) | mid ($37.0M) | yf live 2026-09-25 |
| DEC | 13.75 | 21.25 | 20.00 / 32.00 | 55% | 8 | SB 0 / B 9 / H 1 / S 0 (strong_buy) | small ($11.3M) | yf live 2026-09-25 |
| EXTR | 21.69 | 33.50 | 34.00 / 38.00 | 54% | 8 | SB 1 / B 6 / H 1 / S 0 (none) | mid ($40.0M) | yf live 2026-09-25 |
| BBUC | 25.24 | 38.81 | 40.75 / 45.00 | 54% | 8 | SB 4 / B 2 / H 1 / S 1 (buy) | small ($9.5M) | yf live 2026-09-25 |
| OFRM | 16.46 | 25.25 | 22.00 / 38.00 | 53% | 8 | SB 1 / B 5 / H 3 / S 0 (none) | small ($7.1M) | yf live 2026-09-25 |
| ALH | 21.04 | 32.25 | 32.00 / 37.00 | 53% | 8 | SB 1 / B 6 / H 1 / S 0 (none) | small ($18.6M) | yf live 2026-09-25 |
| NXST | 161.24 | 246.75 | 249.50 / 290.00 | 53% | 8 | SB 2 / B 6 / H 0 / S 0 (none) | mid ($58.6M) | yf live 2026-09-25 |
| ACMR | 75.77 | 115.88 | 112.50 / 166.00 | 53% | 8 | SB 2 / B 6 / H 1 / S 0 (strong_buy) | mid ($72.9M) | yf live 2026-09-25 |
| YSWY | 19.39 | 29.62 | 30.00 / 32.00 | 53% | 8 | SB 2 / B 4 / H 3 / S 0 (buy) | small ($6.4M) | yf live 2026-09-25 |
| FIGS | 12.30 | 18.62 | 19.00 / 22.00 | 51% | 8 | SB 1 / B 4 / H 4 / S 0 (buy) | mid ($31.9M) | yf live 2026-09-25 |
| JBTM | 111.87 | 169.19 | 170.00 / 210.00 | 51% | 8 | SB 2 / B 5 / H 0 / S 1 (buy) | mid ($63.7M) | yf live 2026-09-25 |
| PLAY | 6.75 | 13.14 | 13.00 / 22.00 | 95% | 7 | SB 0 / B 3 / H 8 / S 0 (buy) | small ($15.2M) | yf live 2026-09-25 |
| CTNM | 11.59 | 22.29 | 22.00 / 28.00 | 92% | 7 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | small ($5.6M) | yf live 2026-09-25 |
| OMCL | 32.80 | 57.86 | 60.00 / 70.00 | 76% | 7 | SB 1 / B 6 / H 1 / S 0 (none) | mid ($24.9M) | yf live 2026-09-25 |
| SBET | 9.78 | 17.14 | 14.00 / 30.00 | 75% | 7 | SB 1 / B 6 / H 0 / S 0 (strong_buy) | mid ($54.8M) | yf live 2026-09-25 |
| KOPN | 4.85 | 8.43 | 7.00 / 12.00 | 74% | 7 | SB 0 / B 7 / H 0 / S 0 (strong_buy) | small ($15.3M) | yf live 2026-09-25 |
| ICHR | 56.49 | 95.86 | 98.00 / 115.00 | 70% | 7 | SB 1 / B 5 / H 1 / S 0 (strong_buy) | mid ($60.6M) | yf live 2026-09-25 |
| NVCR | 16.04 | 27.14 | 25.00 / 52.00 | 69% | 7 | SB 1 / B 3 / H 3 / S 0 (none) | small ($18.7M) | yf live 2026-09-25 |
| FIGR | 32.70 | 55.29 | 55.00 / 70.00 | 69% | 7 | SB 3 / B 3 / H 1 / S 0 (none) | large ($116.2M) | yf live 2026-09-25 |
| STRL | 518.80 | 876.00 | 950.00 / 1,000.00 | 69% | 7 | SB 0 / B 8 / H 0 / S 0 (strong_buy) | large ($354.9M) | yf live 2026-09-25 |
| OPEN | 2.56 | 4.27 | 4.50 / 7.00 | 67% | 7 | SB 1 / B 1 / H 5 / S 2 (hold) | large ($134.1M) | yf live 2026-09-25 |
| MAMA | 13.40 | 22.29 | 22.00 / 25.00 | 66% | 7 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | small ($9.5M) | yf live 2026-09-25 |
| VIAV | 37.06 | 61.43 | 65.00 / 70.00 | 66% | 7 | SB 1 / B 6 / H 1 / S 0 (strong_buy) | large ($175.1M) | yf live 2026-09-25 |
| AIP | 23.92 | 39.43 | 40.00 / 50.00 | 65% | 7 | SB 0 / B 7 / H 0 / S 0 (strong_buy) | small ($17.9M) | yf live 2026-09-25 |
| GROY | 3.14 | 5.18 | 5.00 / 7.00 | 65% | 7 | SB 4 / B 3 / H 0 / S 0 (buy) | small ($5.4M) | yf live 2026-09-25 |
| MAX | 9.39 | 15.43 | 15.00 / 19.00 | 64% | 7 | SB 2 / B 3 / H 3 / S 0 (buy) | small ($9.6M) | yf live 2026-09-25 |
| IPGP | 76.88 | 126.21 | 125.00 / 152.00 | 64% | 7 | SB 2 / B 4 / H 2 / S 1 (buy) | mid ($34.6M) | yf live 2026-09-25 |
| PRG | 32.59 | 53.43 | 50.00 / 64.00 | 64% | 7 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | mid ($20.2M) | yf live 2026-09-25 |
| TATT | 38.03 | 60.71 | 61.00 / 66.00 | 60% | 7 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($5.1M) | yf live 2026-09-25 |
| AHCO | 5.64 | 9.00 | 9.00 / 10.00 | 59% | 7 | SB 1 / B 6 / H 0 / S 0 (strong_buy) | small ($14.6M) | yf live 2026-09-25 |
| MOD | 196.97 | 310.29 | 302.00 / 355.00 | 58% | 7 | SB 1 / B 7 / H 0 / S 0 (strong_buy) | large ($257.0M) | yf live 2026-09-25 |
| HLNE | 85.32 | 133.43 | 130.00 / 181.00 | 56% | 7 | SB 2 / B 4 / H 1 / S 0 (none) | mid ($62.2M) | yf live 2026-09-25 |
| VCEL | 39.05 | 60.57 | 59.00 / 72.00 | 55% | 7 | SB 0 / B 7 / H 1 / S 0 (strong_buy) | mid ($21.3M) | yf live 2026-09-25 |
| ROAD | 92.13 | 142.57 | 139.00 / 165.00 | 55% | 7 | SB 0 / B 5 / H 1 / S 0 (strong_buy) | mid ($68.2M) | yf live 2026-09-25 |
| HMH | 18.82 | 28.71 | 30.00 / 32.00 | 53% | 7 | SB 2 / B 5 / H 0 / S 0 (none) | small ($3.5M) | yf live 2026-09-25 |
| FUL | 48.65 | 73.29 | 75.00 / 80.00 | 51% | 7 | SB 1 / B 5 / H 1 / S 0 (strong_buy) | mid ($36.1M) | yf live 2026-09-25 |
| CECO | 72.52 | 109.14 | 111.00 / 130.00 | 51% | 7 | SB 2 / B 5 / H 0 / S 0 (none) | mid ($56.4M) | yf live 2026-09-25 |
| CRMD | 7.70 | 15.33 | 15.00 / 19.00 | 99% | 6 | SB 3 / B 3 / H 0 / S 0 (strong_buy) | small ($7.5M) | yf live 2026-09-25 |
| UTI | 20.77 | 40.83 | 40.00 / 48.00 | 97% | 6 | SB 1 / B 5 / H 0 / S 0 (none) | mid ($36.9M) | yf live 2026-09-25 |
| DPRO | 5.50 | 10.71 | 10.59 / 13.80 | 95% | 6 | SB 2 / B 4 / H 0 / S 0 (strong_buy) | small ($3.6M) | yf live 2026-09-25 |
| DQ | 11.48 | 22.35 | 22.00 / 31.87 | 95% | 6 | SB 2 / B 3 / H 1 / S 1 (buy) | small ($10.9M) | yf live 2026-09-25 |
| TPB | 61.02 | 118.50 | 120.50 / 140.00 | 94% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | mid ($24.4M) | yf live 2026-09-25 |
| RXRX | 3.72 | 7.22 | 7.00 / 10.00 | 94% | 6 | SB 2 / B 1 / H 4 / S 0 (buy) | mid ($51.5M) | yf live 2026-09-25 |
| SVCO | 8.09 | 15.17 | 14.50 / 18.00 | 87% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($2.8M) | yf live 2026-09-25 |
| CALX | 33.27 | 62.33 | 60.00 / 85.00 | 87% | 6 | SB 2 / B 4 / H 1 / S 0 (buy) | mid ($39.1M) | yf live 2026-09-25 |
| RMIX | 12.45 | 23.17 | 23.50 / 25.00 | 86% | 6 | SB 0 / B 6 / H 0 / S 0 (strong_buy) | small ($4.9M) | yf live 2026-09-25 |
| VYX | 7.00 | 12.96 | 13.50 / 15.00 | 85% | 6 | SB 2 / B 3 / H 1 / S 0 (buy) | small ($19.4M) | yf live 2026-09-25 |
| CXDO | 5.91 | 10.92 | 11.00 / 12.00 | 85% | 6 | SB 1 / B 5 / H 0 / S 0 (none) | small ($2.4M) | yf live 2026-09-25 |
| DC | 6.57 | 12.09 | 10.88 / 16.00 | 84% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($6.2M) | yf live 2026-09-25 |
| CDRE | 26.48 | 47.50 | 45.00 / 62.00 | 79% | 6 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | small ($10.5M) | yf live 2026-09-25 |
| ORN | 8.60 | 15.32 | 15.00 / 16.00 | 78% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($4.5M) | yf live 2026-09-25 |
| UPBD | 15.88 | 28.25 | 27.25 / 41.00 | 78% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($16.5M) | yf live 2026-09-25 |
| DSGN | 12.11 | 21.00 | 21.00 / 22.00 | 73% | 6 | SB 2 / B 5 / H 0 / S 0 (none) | small ($8.2M) | yf live 2026-09-25 |
| CTGO | 18.04 | 31.17 | 31.00 / 35.00 | 73% | 6 | SB 3 / B 3 / H 0 / S 0 (strong_buy) | small ($6.8M) | yf live 2026-09-25 |
| ABX | 8.16 | 14.08 | 14.00 / 16.00 | 72% | 6 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($4.8M) | yf live 2026-09-25 |
| BKD | 11.20 | 19.25 | 18.25 / 23.00 | 72% | 6 | SB 2 / B 4 / H 0 / S 0 (strong_buy) | mid ($60.5M) | yf live 2026-09-25 |
| MFA | 8.22 | 14.00 | 10.75 / 31.00 | 70% | 6 | SB 1 / B 2 / H 4 / S 0 (none) | small ($13.1M) | yf live 2026-09-25 |
| BLZE | 13.58 | 22.83 | 23.00 / 25.00 | 68% | 6 | SB 2 / B 4 / H 1 / S 0 (buy) | mid ($33.1M) | yf live 2026-09-25 |
| EVER | 17.63 | 29.50 | 28.50 / 34.00 | 67% | 6 | SB 3 / B 3 / H 2 / S 0 (buy) | small ($14.3M) | yf live 2026-09-25 |
| Z | 28.16 | 46.00 | 41.50 / 62.00 | 63% | 6 | SB 1 / B 1 / H 5 / S 0 (hold) | large ($117.1M) | yf live 2026-09-25 |
| ARLO | 13.02 | 21.00 | 21.00 / 25.00 | 61% | 6 | SB 2 / B 5 / H 0 / S 0 (strong_buy) | small ($16.5M) | yf live 2026-09-25 |
| LTRX | 6.66 | 10.58 | 10.50 / 12.00 | 59% | 6 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($4.5M) | yf live 2026-09-25 |
| TBN | 36.01 | 56.67 | 56.50 / 75.00 | 57% | 6 | SB 1 / B 5 / H 0 / S 0 (none) | small ($4.5M) | yf live 2026-09-25 |
| REPL | 12.44 | 19.50 | 19.50 / 24.00 | 57% | 6 | SB 2 / B 5 / H 0 / S 1 (buy) | mid ($33.9M) | yf live 2026-09-25 |
| YOU | 38.55 | 59.67 | 61.50 / 75.00 | 55% | 6 | SB 2 / B 2 / H 1 / S 1 (buy) | mid ($71.6M) | yf live 2026-09-25 |
| LOVE | 14.98 | 23.17 | 20.00 / 35.00 | 55% | 6 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | small ($3.4M) | yf live 2026-09-25 |
| SEZL | 109.00 | 168.00 | 167.50 / 196.00 | 54% | 6 | SB 1 / B 3 / H 3 / S 0 (none) | mid ($72.4M) | yf live 2026-09-25 |
| AGX | 372.81 | 573.00 | 582.50 / 800.00 | 54% | 6 | SB 1 / B 3 / H 1 / S 1 (buy) | large ($176.2M) | yf live 2026-09-25 |
| GVA | 112.23 | 171.67 | 177.50 / 200.00 | 53% | 6 | SB 0 / B 4 / H 0 / S 1 (buy) | mid ($75.3M) | yf live 2026-09-25 |
| ECG | 115.27 | 176.00 | 176.00 / 200.00 | 53% | 6 | SB 0 / B 5 / H 2 / S 0 (buy) | mid ($66.2M) | yf live 2026-09-25 |
| PAX | 10.07 | 15.17 | 15.00 / 20.00 | 51% | 6 | SB 1 / B 2 / H 2 / S 1 (buy) | small ($11.3M) | yf live 2026-09-25 |
| SHAZ | 58.09 | 110.00 | 110.00 / 124.00 | 89% | 5 | SB 0 / B 5 / H 0 / S 0 (strong_buy) | large ($119.1M) | yf live 2026-09-25 |
| EOLS | 7.93 | 15.00 | 13.00 / 20.00 | 89% | 5 | SB 1 / B 4 / H 1 / S 0 (strong_buy) | small ($5.4M) | yf live 2026-09-25 |
| JBI | 4.12 | 7.62 | 9.00 / 9.00 | 85% | 5 | SB 1 / B 2 / H 2 / S 0 (buy) | small ($7.6M) | yf live 2026-09-25 |
| USAU | 15.52 | 27.95 | 27.50 / 33.25 | 80% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($3.1M) | yf live 2026-09-25 |
| JMIA | 6.80 | 12.19 | 11.84 / 17.75 | 79% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | small ($9.6M) | yf live 2026-09-25 |
| UCTT | 76.71 | 137.00 | 140.00 / 150.00 | 79% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | mid ($96.4M) | yf live 2026-09-25 |
| CEPU | 13.38 | 23.81 | 24.00 / 28.00 | 78% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | small ($3.0M) | yf live 2026-09-25 |
| COAG | 34.74 | 61.20 | 60.00 / 65.00 | 76% | 5 | SB 0 / B 5 / H 0 / S 0 (none) | small ($14.9M) | yf live 2026-09-25 |
| GENB | 15.71 | 27.00 | 27.00 / 30.00 | 72% | 5 | SB 2 / B 4 / H 0 / S 0 (none) | small ($12.7M) | yf live 2026-09-25 |
| GRNT | 4.54 | 7.80 | 7.00 / 11.00 | 72% | 5 | SB 0 / B 3 / H 2 / S 0 (buy) | small ($4.0M) | yf live 2026-09-25 |
| SATL | 5.95 | 10.20 | 10.00 / 11.00 | 71% | 5 | SB 0 / B 5 / H 0 / S 0 (strong_buy) | mid ($22.7M) | yf live 2026-09-25 |
| ANGX | 4.79 | 8.20 | 9.00 / 9.00 | 71% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | small ($5.3M) | yf live 2026-09-25 |
| INVA | 20.54 | 35.00 | 35.00 / 46.00 | 70% | 5 | SB 0 / B 4 / H 0 / S 1 (buy) | small ($14.4M) | yf live 2026-09-25 |
| TBLA | 3.44 | 5.80 | 5.50 / 7.00 | 69% | 5 | SB 1 / B 4 / H 2 / S 0 (buy) | small ($10.6M) | yf live 2026-09-25 |
| MUX | 18.52 | 31.20 | 31.00 / 37.00 | 68% | 5 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($17.8M) | yf live 2026-09-25 |
| NVCT | 21.27 | 35.40 | 35.00 / 40.00 | 66% | 5 | SB 2 / B 4 / H 0 / S 0 (strong_buy) | small ($4.6M) | yf live 2026-09-25 |
| SUPV | 7.54 | 12.36 | 12.50 / 15.00 | 64% | 5 | SB 2 / B 0 / H 3 / S 0 (none) | small ($4.1M) | yf live 2026-09-25 |
| CSV | 31.89 | 51.80 | 50.00 / 65.00 | 62% | 5 | SB 2 / B 3 / H 0 / S 0 (none) | small ($4.3M) | yf live 2026-09-25 |
| AAOI | 100.69 | 163.40 | 178.00 / 220.00 | 62% | 5 | SB 2 / B 1 / H 3 / S 0 (none) | large ($999.4M) | yf live 2026-09-25 |
| ANGI | 4.93 | 8.00 | 6.00 / 14.00 | 62% | 5 | SB 0 / B 2 / H 5 / S 1 (hold) | small ($3.6M) | yf live 2026-09-25 |
| QNST | 14.27 | 22.80 | 23.00 / 24.00 | 60% | 5 | SB 1 / B 5 / H 0 / S 0 (strong_buy) | small ($12.8M) | yf live 2026-09-25 |
| PPTA | 23.20 | 36.90 | 37.00 / 43.50 | 59% | 5 | SB 3 / B 5 / H 0 / S 0 (strong_buy) | mid ($23.4M) | yf live 2026-09-25 |
| PHIN | 59.62 | 94.00 | 95.00 / 105.00 | 58% | 5 | SB 1 / B 3 / H 1 / S 0 (none) | mid ($22.9M) | yf live 2026-09-25 |
| LPTH | 10.07 | 15.80 | 15.50 / 17.00 | 57% | 5 | SB 1 / B 4 / H 0 / S 0 (strong_buy) | mid ($33.4M) | yf live 2026-09-25 |
| MDXG | 4.78 | 7.40 | 8.00 / 8.00 | 55% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | small ($4.8M) | yf live 2026-09-25 |
| DCTH | 15.69 | 24.00 | 22.00 / 32.00 | 53% | 5 | SB 1 / B 4 / H 0 / S 0 (none) | small ($5.8M) | yf live 2026-09-25 |
| LMB | 50.58 | 77.20 | 85.00 / 95.00 | 53% | 5 | SB 1 / B 3 / H 0 / S 1 (none) | small ($16.5M) | yf live 2026-09-25 |
| LOMA | 9.45 | 14.30 | 14.50 / 15.00 | 51% | 5 | SB 2 / B 3 / H 0 / S 0 (none) | small ($3.6M) | yf live 2026-09-25 |


## 4c. Passed the screen but fewer than 5 analysts or no count - 179 names

NRXP 1143% (n 4); DFNS 743% (n 2); XNDU 561% (n 3); SPRY 441% (n 4); SIDU 381% (n 1); QTTB 363% (n 4); TNXP 354% (n 4); RZLV 344% (n 4); ASPI 340% (n 3); NEOV 323% (n 4); GOGO 280% (n 2); BW 256% (n 4); CABO 224% (n 4); FIP 221% (n 4); TOYO 218% (n 2); AGEN 215% (n 3); DRUG 199% (n 3); SLDP 194% (n 2); KARD 192% (n 4); BTQ 189% (n 2); SLS 184% (n 2); CDZI 181% (n 3); RLMD 181% (n 4); KULR 180% (n 1); DUOT 173% (n 2); CUE 173% (n 3); SWMR 168% (n 1); RUM 167% (n 1); IMSR 164% (n 3); ABAT 163% (n 2); BRUN 161% (n 4); INBX 159% (n 3); OGG 159% (n 1); LAES 157% (n 2); SLSR 150% (n 1); VIVO 148% (n 1); SOC 146% (n 3); SLGL 144% (n 2); ECC 143% (n 4); ALTO 142% (n 2); WRN 135% (n 2); NN 134% (n 3); VISN 133% (n 3); ATOM 131% (n 1); SHEN 129% (n 2); UAMY 128% (n 4); GLIBA 127% (n 1); ITRG 125% (n 2); AVLN 123% (n 4); SUJA 118% (n 4); DERM 117% (n 4); SLI 117% (n 4); GLAS 115% (n 3); WATT 115% (n 1); ADUR 115% (n 4); CYD 114% (n 4); HIMX 114% (n 2); OPFI 113% (n 4); QUIK 110% (n 3); VELO 109% (n 4); CDNL 109% (n 4); OSS 105% (n 3); AMSC 105% (n 4); DGXX 103% (n 1); AMPG 103% (n 1); AVR 101% (n 3); ARIS 100% (n 1); ALOY 100% (n 2); TMQ 99% (n 3); ARKO 99% (n 2); USAS 98% (n 1); CERS 97% (n 4); SA 96% (n 4); GAU 95% (n 2); PESI 95% (n 1); HNRG 94% (n 3); PDYN 94% (n 4); FWRD 94% (n 2); WNC 94% (n 2); GILT 92% (n 2); TTI 92% (n 4); HYLN 92% (n 3); PGEN 91% (n 3); CPS 91% (n 3); LWLG 90% (n 1); POET 90% (n 1); ROCK 90% (n 4); LGIH 90% (n 1); BGSI 88% (n 4); ODTX 88% (n 4); WINA 86% (n 1); REZI 86% (n 4); MNTS 86% (n 1); DAKT 85% (n 3); BBAR 85% (n 4); IMMR 85% (n 1); NG 84% (n 2); NNBR 83% (n 3); ASM 82% (n 4); ALMU 81% (n 2); CENX 81% (n 4); SRTA 81% (n 4); SGML 80% (n 3); CTRN 80% (n 2); IA 80% (n 4); ALIT 79% (n 3); ADMA 79% (n 4); CMCL 78% (n 3); BULL 77% (n 4); NXE 76% (n 2); MMS 76% (n 2); DNN 75% (n 2); NPKI 75% (n 3); RPC 74% (n 4); RFIL 74% (n 2); ADEA 73% (n 4); IIIV 73% (n 4); INOD 73% (n 4); MATV 72% (n 1); WLDN 72% (n 2); DIOD 72% (n 2); DMC 71% (n 1); NMAX 71% (n 2); TCMD 71% (n 3); NGS 70% (n 3); EXK 70% (n 3); TWI 70% (n 4); BBW 69% (n 4); MLKN 69% (n 1); SPIR 67% (n 4); RERE 67% (n 4); ASTE 67% (n 4); PWP 66% (n 4); KRNT 66% (n 4); HCKT 66% (n 3); EGY 66% (n 3); BMNR 65% (n 3); GSIT 64% (n 1); EBS 64% (n 2); NBTX 62% (n 3); CLPT 62% (n 2); AOSL 62% (n 4); TBBK 62% (n 3); AAON 62% (n 4); MATW 62% (n 3); TGLS 60% (n 4); PURR 60% (n 4); CMCO 60% (n 4); NTGR 59% (n 3); TSSI 59% (n 2); DDD 59% (n 2); RELX 58% (n 2); RYAM 58% (n 2); TTMI 58% (n 4); VZLA 57% (n 1); MNRO 57% (n 4); PRM 56% (n 4); UVV 56% (n 1); DBD 56% (n 3); BNED 56% (n 2); APPS 56% (n 2); CRML 56% (n 2); AGNT 56% (n 2); CRAI 55% (n 2); CVLG 55% (n 4); RTO 55% (n 4); BELFA 55% (n 2); POWI 55% (n 4); NUAI 54% (n 2); WD 54% (n 3); VTOL 52% (n 3); AEBI 52% (n 2); SUNS 51% (n 4); CODI 51% (n 3); IBRX 51% (n 4); MEI 51% (n 4); IDR 51% (n 1); TRUP 51% (n 4); GRFS 50% (n 2)


---


# 5. APPENDIX - where every number came from

| Item | File / source | Date |
|---|---|---|
| Frozen books | backend/data/optimus/llm_portfolio/books.jsonl | frozen 2026-09-25 (per-book frozen_utc above) |
| Thesis cards | backend/data/optimus/thesis_cards/2026-09-25/*.json | asof 2026-09-25 |
| HUMAN + AI table | docs/research_notes/2026-09-25/research_themes.md (FINAL table) | 2026-09-25 |
| Global candidates | docs/research_notes/2026-09-25/research_global_candidates.md | 2026-09-25 |
| Pharma | docs/research_notes/2026-09-25/research_pharma.md (bucket tables 1-3) | 2026-09-25 |
| Retail crowding + gambling | docs/research_notes/2026-09-25/research_social.md §3-§4 | 2026-09-25 |
| Murat's holdings | backend/data/murat_book.yaml | reconciled 2026-08-11 |
| Analyst targets, price, implied upside | backend/data/optimus/analyst/target_snapshots.parquet | 2026-09-24 |
| Analyst count (stored) | backend/data/analyst_snapshots.jsonl | snapshots 2026-08-10 |
| Analyst count + rec mix (live) | yfinance Ticker.info / Ticker.recommendations | 2026-09-25 UTC (2026-09-26 HKT) |
| Liquidity band | backend/data/optimus/prices_2025_26/bars.parquet (63-session median close×volume) + xs_ranker.liquidity_band | bars through 2026-09-21 |
| §17 finding | NEGATIVE_RESULTS.md §17 (TRIAL-TGT-REBUILD) | standing |
| §64 finding | docs/HANDOFF_2026-09-24_THE_LEDGER_WAS_THE_ANSWER.md | 2026-09-24 |
| Revision flow | docs/HANDOFF_2026-09-25_EVENING_THE_MACHINE_FORECASTS_AGAIN.md; backend/data/optimus/analyst/revision_flow_sweep_2026-09-25.json | 2026-09-25 |


## Standing findings (three lines)

1. **§17 - target LEVEL is perverse:** high analyst-implied upside underperformed, −90 bps/mo large/mid (t −3.62), −199 bps/mo small (t −7.21). Section 4 is a research list for that reason.

2. **§64 - a process forecasts, a persona does not:** on 14,703 frozen forecasts graded held-out, the 'investigator' process showed +8.97% skill while nine thematic personas scored −27.98% (optimal weight zero); skill is at h=1 and gone by h=5.

3. **Revision flow is not a result yet:** the month-end rule (top-20 by net raises × n firms, ≥ 3 firms, 21d hold) beat SPY by +0.32%/hold, +0.02% with its worst year left out, t 0.94 on 121 holds - a positive sign, frozen as revision_flow_v0 (cb8d492bb8bf9ade) for forward grading.
