# Research v3 — demand, CEO, competition, profitability, street, crowd (2026-09-27)

**Licence: PRODUCT_EXPERIMENT.** Nothing here is a claim of alpha and none of it is an order. Every field is
sourced or marked `n/a: <why>`. Tooling: WebFetch (fast, unlimited this session) against stockanalysis.com,
finviz.com, investing.com and SEC EDGAR for financials/insiders/street; OpenClaw browser
(`backend/services.openclaw_client.browser`, `muratclaw` profile) for reddit/X and one company IR page; repo
files (`predictions.jsonl`, `books.jsonl`, the dress-rehearsal book, `mw_analyst_snapshot.jsonl`,
`pc_plan/*.json`) for the demand theses that Aegis had already dated and sourced. All prices/targets/insider
rows below were read live on 2026-09-27 unless a date is given in the text.

**Companion document.** `docs/research_notes/2026-09-27/stock_lists_2026-09-27_v3.md` (a parallel session,
quant-formula ROI list) was rendered before this note landed and says so in its §3b. Read the two together:
that file supplies `σ63`-bounded upside and card conviction; this file supplies the qualitative demand / CEO /
competition / crowd layer neither file had alone. **That file's own §17 standing caveat applies to every
upside number quoted below**: analyst target-level upside is a measured **perverse** cross-sectional signal in
this repo's own tested data — large/mid caps **-90 bps/month** (t -3.62), small caps **-199 bps/month**
(t -7.21) once you rank on it. The upside percentages in this note are a **research input to look at**, not
a signal to buy. Every top-15 entry below carries a mechanism and a falsifier for exactly this reason.

**A crowd-check limitation, disclosed rather than hidden.** Partway through this pass the `muratclaw` browser
profile showed eight open tabs driven by a different, concurrent Aegis session (VRTX IR press releases, a
Celestica-competitor Bing search, Robinhood/Broadcom/Micron investor-relations pages, `x.com/BloomEnergy`,
`x.com/KRSridhar`) — the same shared automation profile this note was told to use. Two of my own reddit reads
landed on stale or foreign tabs as a result (`no tab`, or a Sep-25-vintage X login wall). Rather than report
contaminated crowd reads, most small/mid names below carry `crowd: n/a — shared browser profile was in
concurrent use by another session; not independently completed this pass`. Five crowd reads are clean and
dated: **NVEC** and **PRAX** and **SLDP** (read fresh, this session — PRAX and SLDP came back after this
note's first draft, once a queued background reddit-check script finally finished; both are folded into
their entries below), and **DKNG** and **QUBT** (read 2026-09-25, reused here with that date —
old.reddit.com "new / past month" search, per `scratchpad/log_dkng_reddit.json` and
`log_qubt_reddit.json`). A further eleven tickers (VKTX, AGIO, BBIO, MP, IONQ, COGT, NOVT, AGYS, PRGS, HELE,
BHVN, PSNL, BSP, SOC, ABSI, HUBS, NVEC-dup, AMSC, NTLA, LEU, CCJ, KYTX, SMPL, TEM, AARD) were attempted in
the same queued script but returned `net::ERR_ABORTED`, `frame was detached`, or `tab not found` — direct
evidence of the concurrent-session collision, not a clean "no chatter" result, so they stay `n/a`.

---

## The shortlist (68 tickers after de-duplication across six sources)

| Source | Tickers |
|---|---|
| `human_ai_thematic_v2` book (24 pos. incl. cash), `books.jsonl` id `5d137b013692a737`, `docs/BOOK_2026-09-25_HUMAN_AI_THEMATIC_V0.md` §10 | VRT, GEV, MU, TSM, HOOD, NVT, AVGO, CLS, BE, MP, LEU, CCJ, NOVT, IONQ, VRTX, WST, COGT, VKTX, AGIO, RGEN, BBIO, PRAX, DKNG |
| Bloomberg dress rehearsal (10), `docs/BOOK_2026-09-27_BLOOMBERG_DRESS_REHEARSAL.md` | NVEC, MAN, RHI, ACI, PEGA, IRDM, HELE, SMPL, PRGS, AGYS |
| Murat's holdings | DKNG (dup), QUBT, AARD, BHVN, SLDP |
| WSJ Heard on the Street rows, `predictions.jsonl` (`specialist: source:wsj_heard_on_the_street`, 48 rows, 15 tickers, made 2026-09-26) | LEU (dup), AAPL, AMGN, BA, CRM, HWM, LNG, NOW, NVO, PSNL, SNOW, TEM, VG, WDAY, BSP |
| Barron's Stock Picks rows, `predictions.jsonl` (3 rows, 1 ticker) | BN |
| `mw_analyst_snapshot.jsonl` (`backend/data/optimus/news_corpus/dowjones/_structured/`, 15 tickers) | AARD (dup), ABSI, AMSC, BHVN (dup), DKNG (dup), GEV (dup), HUBS, KYTX, MU (dup), NTLA, PRCH, QUBT (dup), SLDP (dup), SOC, VRT (dup) |
| Latest `pc_plan` PROBE shortlist, `backend/data/optimus/decisions/pc_plan/2026-09-26.json` (10 tickers) | AAPL (dup), AMZN, AVPT, GOOG, GOOGL, INCY, JAZZ, META, NVDA, SNDR |

**68 distinct tickers** (GOOG/GOOGL counted separately, as the file lists them). Tiered below: **Tier 1**
(33 names — small/mid caps and the names most likely to carry real six-month asymmetry) gets the full
demand/CEO/competition/profitability/street/crowd/ROI treatment; **Tier 2** (35 names — mega/large caps and
macro-thesis Dow Jones picks, where the "mega-cap is a SENSOR, not the trade" invariant applies) gets a
compact version of the same fields. Every number in both tiers is sourced.

---

# TIER 1 — full profiles

### NVEC — NVE Corporation (spintronics/semis, dress rehearsal #1)
- **Demand:** Sensors/couplers for factory automation and medical devices; TTM revenue growth **+24.07%**, FY2026 revenue $26.33M (stockanalysis.com/stocks/nvec/financials, read 2026-09-27). A fresh, unpaid-for signal: a 1-month-old r/NVEC post quotes CEO Pete Eames tying spintronics explicitly to "advanced humanoid robotics, data centers, and highly automated fourth-wave factories" on the Q1 earnings call (old.reddit.com/search/?q=NVEC, read 2026-09-27) — a demand-mix shift the dress-rehearsal book's earnings-date construction did not capture.
- **How it feeds it:** 42 employees, high-margin licensed IP model; capacity is R&D/design-win driven, not a factory ramp. Next dated catalyst: Q3 8-K item 2.02 estimated **2026-10-21** (`rehearsal_2026-09-27.json`).
- **CEO:** **Dr. Peter G. Eames**, President & CEO (stockanalysis.com/stocks/nvec/company, read 2026-09-27) — this is a change from what finviz's insider table shows as the most recent CEO-tagged seller, **Daniel A. Baker, "President & CEO,"** selling through Sep 8, 2026 (finviz.com/quote.ashx?t=NVEC). Aegis's own data has not caught up to the transition; flagged in §D.
- **Competition:** Honeywell and TE Connectivity in magnetic sensors; Allegro Microsystems in automotive/industrial sensor ICs. NVEC's moat is its spintronic IP, not scale.
- **Profitability:** Gross margin **79.26%**, operating margin **62.07%** TTM, FCF **$15.6M** TTM (+27.24%), net cash **$43M** (stockanalysis.com, read 2026-09-27).
- **Street:** No analyst consensus on investing.com ("Analysts Sentiment: Currently not supported"); finviz shows a lone **Hold (3.00)**, target **$79.00** vs. current **$109.13** — **-27.6% implied downside**, i.e. the street (thin coverage) is already behind the stock.
- **Crowd:** Read fresh 2026-09-27 on old.reddit.com — one substantive post (1 point, 1 comment, "1 month ago") on the earnings-call language shift; otherwise thin. No pump language seen.
- **ROI read:** The demand mix-shift (robotics/data-center framing on the last call) is real and undated in the rehearsal book's own construction; but the lone analyst target is already below spot, so this is a story stock, not a street-validated re-rate. Falsifier: no confirmation of the robotics/data-center revenue mix in the Oct 21 print.

### MAN — ManpowerGroup (staffing, dress rehearsal #2)
- **Demand:** Global staffing volumes; TTM revenue growth **+6.72%**, but gross margin only **16.23%**, operating margin **1.85%** (stockanalysis.com/stocks/man/financials, read 2026-09-27) — a low-margin, cyclical, white-collar-hiring proxy.
- **How it feeds it:** No product lever; demand is a macro-hiring pass-through. Next dated catalyst: Q3 8-K est. **2026-10-15** (`rehearsal_2026-09-27.json`).
- **CEO:** Not disclosed by name in the insider table pulled (finviz.com/quote.ashx?t=MAN shows 0.00% insider transaction, no named rows); `n/a: not independently verified this pass`.
- **Competition:** Randstad, Adecco, Robert Half (also in this list) — ManpowerGroup is the #2-3 player in a fragmented, low-differentiation industry.
- **Profitability:** Net debt **$1,239M** vs. FCF **$68.9M** TTM — a levered balance sheet on thin margins.
- **Street:** Buy consensus (2.54), target **$57.33** vs. current **$57.41** — **-0.14%**, essentially priced in. Goldman upgraded Sell→Neutral (target $30) on 2026-03-18, well below the current consensus, i.e. the Street is split.
- **Crowd:** `n/a — shared browser profile in concurrent use; not completed this pass.`
- **ROI read:** Flat-to-target with negative operating leverage; nothing here beats a macro-hiring bet with no company-specific edge. Falsifier already effectively fired (target = spot). **Low ROI candidate.**

### RHI — Robert Half (staffing, dress rehearsal #3)
- **Demand:** Revenue **declining** — TTM growth **-4.95%**, FY2025 **-7.20%** (stockanalysis.com/stocks/rhi/financials, read 2026-09-27); white-collar contract staffing has been in a two-year downturn.
- **How it feeds it:** No product lever, pure macro pass-through. Next catalyst: Q3 8-K est. **2026-10-22**.
- **CEO:** `n/a — not disclosed in the sources pulled`; insider table shows only a **director** (Dirk A. Kempthorne) selling.
- **Competition:** ManpowerGroup (above), Randstad, Adecco; RHI is a premium-fee player losing share as demand contracts.
- **Profitability:** Operating margin collapsed to **0.20%** TTM from 13.47% (FY2022); FCF still positive **$215M** TTM on a net-cash balance sheet.
- **Street:** **Hold** (11 analysts), target **$35.00** vs. current **$36.89** — **-5.1% downside** (stockanalysis.com/stocks/rhi, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Declining revenue, negative-margin trend, and the Street's own target is below spot. **No case for this list**; this is a name a staffing-cycle bottom-caller would need to justify separately.

### ACI — Albertsons Companies (grocery, dress rehearsal #4)
- **Demand:** Grocery retail; TTM revenue growth **+2.75%**, FY2026 **+3.46%** — slow but positive (stockanalysis.com/stocks/aci/financials, read 2026-09-27).
- **How it feeds it:** Store-level execution, no growth lever beyond same-store sales; next catalyst Q3 8-K est. **2026-10-22**.
- **CEO:** **Susan Morris** (CEO) — she **bought** 39,409 shares at **$11.42** on 2026-07-28, days after a downward guidance revision; President & CFO **Sharon McCollam** bought 9,000 at $11.48 the same week; EVP M&A **Thomas Moriarty** bought 170,500 shares at $11.51 (finviz.com/quote.ashx?t=ACI, read 2026-09-27) — a real, sizeable, coordinated post-guidance-cut insider buy from the top three executives.
- **Competition:** Kroger (pending/former merger partner), Walmart, Costco on price; a scale-disadvantaged #2 grocer.
- **Profitability:** Operating margin **1.99%** TTM (thin, typical of grocery), FCF **$564M** TTM, but P/E **156** on depressed earnings and **substantial** leverage (total debt $15.7B vs. cash $308M).
- **Street:** **Hold** (2.55, 19 analysts), target **$14.19** vs. current **$11.67** — **+21.6% upside** (stockanalysis.com/stocks/aci, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** The CEO/CFO/EVP buying in size right after the guidance cut, at levels below today's price, is the single most credible insider signal found in this whole pass — insiders bought the exact dip the market is still digesting. **Falsifier:** Q3 (Oct 22) same-store sales miss again, or the buy cluster proves to be routine 10b5-1 timing rather than discretionary (needs Form 4 footnote check, not done this pass).

### PEGA — Pegasystems (enterprise software, dress rehearsal #5)
- **Demand:** CRM/BPM software; TTM revenue growth only **+3.60%**, decelerating from FY2025 ($1,746M→$1,736M TTM) (stockanalysis.com/stocks/pega/financials, read 2026-09-27).
- **How it feeds it:** Subscription/cloud transition; next catalyst Q3 8-K est. **2026-10-20**.
- **CEO:** `n/a — not named in the insider table pulled` (COO/CFO Kenneth Stillwell Jr., Chief Product Officer Kerim Akgonul, and an SVP were the named sellers).
- **Competition:** Salesforce (Tier 2 below), Pega's own niche is complex-workflow BPM vs. Salesforce's broader CRM — a smaller player facing a much larger, better-capitalized rival in adjacent categories.
- **Profitability:** Gross margin **75.57%**, operating margin **11.32%**, FCF margin **28.36%** TTM — genuinely profitable, but growth has stalled.
- **Street:** **Neutral** (2.21 — recent downgrades from JPMorgan, William Blair, Loop Capital), target **$42.50** vs. current **$33.75** — **+25.95% upside** (stockanalysis.com/stocks/pega, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Consistent, broad insider selling (COO, CPO, SVP, all September 2026) into a name that just took three analyst downgrades — the insider signal and the Street signal agree, and both are negative. The +26% "upside" is against a target that itself just moved down. **Weak candidate.**

### IRDM — Iridium Communications (satellite comms, dress rehearsal #6)
- **Demand:** Satellite connectivity; TTM revenue growth only **+3.10%** (stockanalysis.com/stocks/irdm/financials, read 2026-09-27) — mature, low-growth.
- **How it feeds it:** Existing constellation, no major capacity step-change disclosed; next catalyst Q3 8-K est. **2026-10-21/22**.
- **CEO:** **Matthew J. Desch** — notably **bought** 20,000 shares at **$17.33** in October 2025; the stock has since roughly **tripled** to ~$49-50, at which price five other named executives/directors sold in mid-August 2026 (finviz.com/quote.ashx?t=IRDM, read 2026-09-27) — a clean "CEO bought the bottom, everyone else sold the top" pattern.
- **Competition:** Globalstar, Viasat, and increasingly **SpaceX Starlink direct-to-cell** — the single biggest competitive threat to IRDM's core business, not mentioned in the book.
- **Profitability:** Gross margin **71.85%**, operating margin **23.76%**, FCF margin **32.61%** TTM — strong margins on mature revenue.
- **Street:** **Buy** (2.83, target $48.00) vs. current **$48.75** — **-1.5%**, i.e. priced at fair value already (stockanalysis.com/stocks/irdm, read 2026-09-27 shows current $48.75 vs target $42.00 on a separate pull — the two pulls disagree by ~$6, evidence the consensus itself is unsettled; flagged, not resolved, this pass).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Already re-rated 3x off the CEO's own buy price; the Starlink direct-to-cell threat is real and not in the book's falsifier. **Priced for perfection; not a fresh ROI candidate at spot.**

### HELE — Helen of Troy (consumer products, dress rehearsal #7)
- **Demand:** Household/personal-care brands (OXO, Hydro Flask, etc.); revenue **declining** — TTM **-2.46%**, FY2026 **-6.36%** (stockanalysis.com/stocks/hele/financials, read 2026-09-27); Q1 FY2026 "fell short of estimates."
- **How it feeds it:** Tariff exposure explicitly cited as a headwind; no growth catalyst disclosed. Next catalyst Q3 8-K est. **2026-10-07/08**.
- **CEO:** **George Scott Uzzell**, appointed **August 2025** — a CEO barely a year into the seat, mid-turnaround.
- **Competition:** Newell Brands, Spectrum Brands, Conair in the same fragmented consumer-durables space.
- **Profitability:** Gross margin **45.44%** (healthy), but operating margin compressed to **9.24%** TTM; P/E n/a (negative earnings).
- **Street:** **Hold/Neutral** (2.80, 4 analysts — thin), target **$31.00** vs. current **$28.63** — **+8.3% upside** (stockanalysis.com/stocks/hele, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Declining revenue, tariff overhang, a CEO one year into a turnaround, thin analyst coverage. **Not a top-ROI name**; a value/turnaround bet at best, not a 6-month mover.

### SMPL — The Simply Good Foods Company (packaged foods, dress rehearsal #8)
- **Demand:** Nutrition bars/snacks (Quest, Atkins); TTM revenue **-4.48%** but FY2025 **+8.98%** — noisy (stockanalysis.com/stocks/smpl/financials, read 2026-09-27); stock down **-52.19% YTD** on OWYN-integration litigation.
- **How it feeds it:** No new capacity story; the OWYN acquisition is the current overhang, not a lever. Next catalyst Q3 8-K est. **2026-10-08/09**.
- **CEO:** `n/a — not named in the insider rows pulled` (Chief Commercial Officer Michael Clawson, CFO Christopher Bealer named).
- **Competition:** General Mills (Quaker), Mondelez, and private-label bars — a crowded, low-differentiation snack category.
- **Profitability:** Gross margin **33.27%**, operating margin **13.89%** TTM, FCF **$119.4M** — still solidly profitable despite the litigation.
- **Street:** **Buy-leaning** (2.20, 10 analysts), target **$14.38** vs. current **$9.60** — **+49.8% upside** (stockanalysis.com/stocks/smpl, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **Insider signal:** Two **directors bought** in Apr/May 2026 (Clayton Daley Jr. $11.78, James Kilts $12.39) — both now underwater at $9.60, i.e. the buy didn't call the bottom, but it shows director-level conviction pre-litigation-driven crash.
- **ROI read:** A real value gap (-52% YTD, +50% to target) sitting on a litigation overhang the falsifier needs to name explicitly (OWYN outcome). **Speculative value candidate**, not a growth story.

### PRGS — Progress Software (infra software, dress rehearsal #9)
- **Demand:** Enterprise infrastructure/dev-tools software via acquisition roll-up; TTM revenue growth **+15.50%** (stockanalysis.com/stocks/prgs/financials, read 2026-09-27) — the fastest grower of the three software names in the dress-rehearsal book.
- **How it feeds it:** Acquisitive model (recent Citigroup upgrade cited); next catalyst Q3 8-K est. **2026-10-21**.
- **CEO:** `n/a — not named in the insider rows pulled` (CFO Anthony Folger, two EVP/GMs, Chief Legal Officer named as sellers).
- **Competition:** Progress competes piecemeal across dev-tools/infrastructure categories against much larger players (Microsoft, Salesforce, HashiCorp/IBM) in each sub-segment — a scale disadvantage offset by M&A-driven niche leadership.
- **Profitability:** Gross margin **85.57%**, operating margin **18.54%**, FCF margin **30.41%** TTM — genuinely strong cash generation; net debt **$1,224M** from the acquisition strategy.
- **Street:** **Strong Buy** (1.33, upgraded by Citigroup Oct 2025), target **$56.20** vs. current **$39.34** — **+45.4% upside** (stockanalysis.com/stocks/prgs, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Real growth acceleration, strong FCF, Strong Buy with a large upside gap, and a dated catalyst inside the rehearsal window. Consistent insider selling (routine, spread across the year) is the only caution. **Solid Tier-1 ROI candidate.**

### AGYS — Agilysys (hospitality software, dress rehearsal #10)
- **Demand:** Point-of-sale/property-management software for hotels/resorts/casinos; TTM revenue growth **+14.38%**, most recent quarter **+15.85%** — accelerating (stockanalysis.com/stocks/agys/financials, read 2026-09-27).
- **How it feeds it:** Cloud-migration mix shift within existing hospitality client base; next catalyst Q3 8-K est. **2026-10-26** (the very last day of the rehearsal window).
- **CEO:** **Ramesh Srinivasan** — sold **~$21.3M** across multiple dates in August 2026 at $106.62-$109.63, a large discretionary-looking sale.
- **Competition:** Oracle Hospitality (MICROS), Shiji Group, and legacy on-prem vendors — Agilysys is a share-gainer in cloud-native hospitality tech against Oracle's larger but slower-modernizing incumbent stack.
- **Profitability:** Gross margin **63.06%**, operating margin **11.98%** (improving), FCF **$80.4M** TTM, net cash **$105M** — clean balance sheet.
- **Street:** **Strong Buy** (1.33, 8 analysts), target **$134.50** vs. current **$99.64** — **+35.0% upside** (stockanalysis.com/stocks/agys, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Accelerating growth, Strong Buy, real upside, clean balance sheet — the CEO's $21M August sale is the one thing to watch, but it followed a run-up, not a warning sign disclosed elsewhere. **Solid Tier-1 ROI candidate**, with the Oct 26 print landing right at the rehearsal book's own check date.

### NOVT — Novanta (photonics/robotics, v2 book #13, 3%)
- **Demand:** Photonics/motion-control components for medical, industrial and robotics; TTM revenue growth **+7.61%** (stockanalysis.com/stocks/novt/financials, read 2026-09-27); v2's own thesis (disclosed humanoid servo-drive order, "hundreds of robots in testing," Aug 6 call) is the more specific demand claim, not independently re-verified this pass.
- **How it feeds it:** Component maker riding the humanoid-robotics buildout; next earnings ~Nov 10 (v2's falsifier date).
- **CEO:** **Matthijs Glastra**, CEO & Chairman — sold on four separate dates through 2026 (Feb-Jul, $145-$169/share), a consistent selling pattern.
- **Competition:** Coherent, IPG Photonics in photonics; a fragmented, high-mix components market where Novanta competes on integration breadth.
- **Profitability:** Gross margin **44.55%**, operating margin **11.59%**, FCF **$114.3M** TTM, net cash **$433M** — healthy.
- **Street:** **Strong Buy/Outperform** (1.25, only **3 analysts** — thin), target **$194.50** vs. current **$143.93** — **+35.1% upside** (stockanalysis.com/stocks/novt, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Real robotics-demand story, but the analyst base is thin (3 names) so the target is not well-triangulated, and the CEO has sold consistently all year. **Tier-1 candidate with a coverage-thinness caveat.**

### COGT — Cogent Biosciences (biotech, v2 book #17, 3%)
- **Demand:** Pre-revenue biotech (bezuclastinib, systemic mastocytosis / GIST programs); no product revenue.
- **How it feeds it:** Clinical readouts are the entire demand story; $792M cash funds the runway.
- **CEO:** `n/a — not named in the sources pulled` (CFO John Green, CMO Dr. Jessica Sachs, CSO Dr. John Robinson named as sellers, all late-Dec-2025; Fairmount Healthcare Fund II, a director-affiliated fund, sold **10.5M shares for ~$370M** Jan-Mar 2026 — a large fund-level de-risking, not an operating-executive signal).
- **Competition:** Blueprint Medicines (Ayvakit, an approved rival in the same mastocytosis space) is the direct competitive threat; COGT is the challenger, not the incumbent.
- **Profitability:** Pre-revenue; FCF **-$309M** TTM; net cash **$548M**.
- **Street:** **Strong Buy** (1.17, 12 analysts), target **$55.82** vs. current **$32.31** — **+72.8% upside** (stockanalysis.com/stocks/cogt, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Broad analyst coverage (12), Strong Buy, a large cash runway, and a direct but named competitive threat (Blueprint's approved drug). **Tier-1 candidate**; falsifier is a Blueprint share-loss/label expansion in the same indication.

### VKTX — Viking Therapeutics (biotech, v2 book #18, 3%)
- **Demand:** Pre-revenue biotech; obesity/metabolic drug VK2735 is the whole story. September durability data (per v2's thesis) drove Oppenheimer's target raise to $120 (stockanalysis.com/stocks/vktx, read 2026-09-27, cites the Oppenheimer note directly).
- **How it feeds it:** Clinical readouts and eventual partnership/launch; company just raised **$500M** in equity+convertible notes (announced Sept 24, 2026) — dilutive, and insiders (CEO, CFO, COO) all sold immediately after, on **Jul 29, 2026**, at $33.32-33.47.
- **CEO:** **Brian Lian**, President & CEO.
- **Competition:** Novo Nordisk and Eli Lilly (the incumbent GLP-1 duopoly) — Viking is a clinical-stage challenger in the single most competitive drug category in pharma.
- **Profitability:** Pre-revenue; cash **$501.7M** (down 38.3% from FY2025-end), FCF **-$418M** TTM — a real cash-burn/dilution risk despite the raise.
- **Street:** **Strong Buy** (20 analysts — the broadest coverage of any Tier-1 biotech here), target **$94.61** vs. current **$35.56** — **+166.1% upside** (stockanalysis.com/stocks/vktx, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** The single largest raw upside number and the broadest analyst base in this entire list, against the two best-capitalized rivals in pharma (Novo, Lilly) and a fresh dilution event the insiders sold straight into. **Top-tier ROI candidate on the data, with the dilution/competition risk as the explicit falsifier.**

### BBIO — BridgeBio Pharma (biotech, v2 book #21, 1%; new candidate for the broader list)
- **Demand:** Attruby (acoramidis, ATTR-CM) is an **approved, revenue-generating** drug — TTM revenue **$713M**, growth **+202.4%** (stockanalysis.com/stocks/bbio/financials, read 2026-09-27) — the rare biotech on this list actually selling a product at scale.
- **How it feeds it:** Commercial ramp of Attruby plus a broader genetic-disease pipeline; next catalyst not independently dated this pass.
- **CEO:** **Neil Kumar** — sold at $69-83/share across Aug-Sep 2026 (routine-looking, spread out).
- **Competition:** Pfizer's **Vyndaqel/Vyndamax** is the dominant incumbent in the same ATTR-CM (cardiac amyloidosis) market — the single biggest named competitive fact in this whole document: BBIO is taking share from a Pfizer franchise, not creating a new market.
- **Profitability:** Gross margin **94.44%**, but operating margin **-67.01%** (heavy commercial-launch spend), FCF **-$435M** TTM, cash **$720M**.
- **Street:** **Buy** (22 analysts — broad coverage), target **$109.10** vs. current **$65.57** — **+66.4% upside** (stockanalysis.com/stocks/bbio, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Real, fast-growing product revenue (not a binary readout), broad coverage, large upside, against a named, large incumbent (Pfizer) it is already taking share from. **Top-tier ROI candidate** — arguably the best risk-adjusted name in this note because the growth is already revenue, not a future readout.

### RGEN — Repligen (bioprocessing tools, v2 book #20, 1%)
- **Demand:** Bioprocessing consumables/equipment for biologics manufacturing; TTM revenue growth **+16.49%** (stockanalysis.com/stocks/rgen/financials, read 2026-09-27).
- **How it feeds it:** Picks-and-shovels supplier to the biologics industry; no single dated catalyst identified this pass.
- **CEO:** **Olivier Loeillot** — exercised options and sold on Sep 4, 21 and 24, 2026, at $165.90-$190.00, i.e. selling right up to and at the current price.
- **Competition:** Sartorius, Danaher (Cytiva), Thermo Fisher — RGEN is the smallest of the major bioprocessing-tools players.
- **Profitability:** Gross margin **53.84%**, operating margin **8.32%** (down from 24.45% in FY2022 — margin compression), FCF **$112M** TTM, net cash **$120M**.
- **Street:** **Strong Buy** (23 analysts) label, but target **$189.48** vs. current **$189.68** — **-0.11%**, i.e. the rating hasn't caught up to the fact that the stock is already AT target (stockanalysis.com/stocks/rgen, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Margin compression, a CEO selling at the exact current price, and a "Strong Buy" that is functionally a Hold once you read the actual target. **Drop candidate** — see §B.

### IONQ — IonQ (quantum computing, v2 book #14, 1%)
- **Demand:** Quantum-computing-as-a-service; TTM revenue growth **+370.6%** off a tiny base (stockanalysis.com/stocks/ionq/financials, read 2026-09-27); v2's thesis cites a real-time decoder collaboration with **NVIDIA** announced 2026-09-23.
- **How it feeds it:** Enterprise/government quantum contracts; gross margin actually **fell** to 30.85% from 42.06% (rising delivery costs as it scales).
- **CEO:** **Niccolo de Masi** (President, CEO, Chairman) — filed a **proposed** sale of 17,690 shares at $37.78 on Sep 11, 2026, alongside the CFO/COO and Chief Administrative Officer on the same day (a coordinated, likely 10b5-1-plan cluster).
- **Competition:** IBM, Google, Rigetti — named directly in v2's own falsifier ("no third-party replication" of the NVIDIA-decoder claim); IonQ is one of several credible quantum players, not the leader by any independent measure found this pass.
- **Profitability:** Operating margin **-381.6%**, FCF **-$484M** TTM; net cash **$2.06B** — a fortress balance sheet funding years of losses.
- **Street:** **Strong Buy** (13 analysts), target **$67.14** vs. current **$45.48** — **+47.6% upside** (stockanalysis.com/stocks/ionq, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Real, dated, NVIDIA-adjacent news (not yet independently replicated per v2's own falsifier), broad-ish coverage, large upside. **Tier-1 candidate**, with the "no third-party replication yet" falsifier doing the real work.

### MP — MP Materials (rare earths, v2 book #10, 4%)
- **Demand:** Rare-earth mining/magnets for EVs, robotics, defense; TTM revenue growth **+71.9%** (stockanalysis.com/stocks/mp/financials, read 2026-09-27) — the fastest revenue growth of any non-biotech Tier-1 name.
- **How it feeds it:** Government floor-price/offtake arrangement (per v2's thesis); a Section 232 critical-minerals tariff decision is overdue.
- **CEO:** **James Litinsky**, Chairman/CEO — sold **~$60M+** May-Jun 2026 at $64-69/share, well below today's $48.83, i.e. he sold into a HIGHER price than today's — not a red flag at spot. COO Michael Rosenthal **bought** 10,000 shares at $54.30 in June 2026 — also above spot.
- **Competition:** Lynas Rare Earths (Australia) is the main Western-aligned rival; China's state rare-earth complex is the dominant global supplier MP is positioned as the domestic alternative to.
- **Profitability:** Gross margin **42.33%**, but operating margin **-17.77%** (still unprofitable at scale), FCF **-$505M** TTM (heavy capex), net cash **$471M**.
- **Street:** **Strong Buy** (19 analysts), target **$74.29** vs. current **$48.83** — **+52.1% upside** (stockanalysis.com/stocks/mp, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Fastest real revenue growth in the list, broad coverage, large upside, a named policy catalyst (Section 232) still pending, insider selling that happened at HIGHER prices than today. **Top-tier ROI candidate.**

### LEU — Centrus Energy (HALEU/uranium enrichment, v2 book #11, 2%; also a WSJ pick today)
- **Demand:** Domestic uranium enrichment for nuclear fuel and DOE's HALEU program; TTM revenue growth **+8.47%** but operating margin compressed to near-zero (**0.11%**, from 9.67%) (stockanalysis.com/stocks/leu/financials, read 2026-09-27). **WSJ Heard on the Street, 2026-09-26 (dated today's shortlist source)**: "Centrus deserves a premium valuation because of its unique position in domestic uranium enrichment" (`predictions.jsonl`, prediction_id `fe3cba96471bf174`, p=0.6, url wsj.com/finance/investing/a-safer-way-to-bet-on-nuclear-2d9064f6).
- **How it feeds it:** $900M DOE order (Jul 2026, per v2) plus SMR offtakes; the WSJ piece is a fresh, independent confirmation of the same thesis Aegis already held.
- **CEO:** **Amir Vadim Vexler**, President & CEO — exercised options in Dec 2025; SVP/CFO **Todd Tinelli** sold a small block ($62K) in May 2026. No large discretionary CEO sale found.
- **Competition:** Urenco, Orano, Rosatom (the last effectively closed to US buyers by sanctions) — Centrus is the only US-based enrichment supplier at scale, which is the entire bull case in one sentence.
- **Profitability:** Gross margin **23.66%**, FCF **-$164M** TTM (capex-heavy expansion), net cash **~$691M** (large cash cushion).
- **Street:** **Buy** (19 analysts), target **$247.40** vs. current **$147.07** — **+68.2% upside** (stockanalysis.com/stocks/leu, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** A real monopoly-supplier position (domestic HALEU), independently reaffirmed by WSJ the same day this shortlist was built, broad coverage, large upside, and no red-flag insider selling. **Top-tier ROI candidate.**

### CCJ — Cameco (uranium majors, v2 book #12, 2%)
- **Demand:** Uranium mining/nuclear fuel; TTM revenue **declining -2.68%** (CAD), though this is a large, diversified major rather than a pure enrichment play like LEU (stockanalysis.com/stocks/ccj/financials, read 2026-09-27).
- **How it feeds it:** Nuclear-restart demand (v2's thesis); no single dated catalyst found this pass.
- **CEO:** **Timothy S. Gitzel** — filed proposed sales through Dec 2025-Mar 2026 at $89.99-$108.04, all **below** today's $88.07-ish... actually the current price is $88.07 (stockanalysis.com/stocks/ccj, read 2026-09-27), i.e. Gitzel's sales were mostly at similar or slightly higher levels than today.
- **Competition:** Kazatomprom (Kazakhstan, the world's largest producer by volume) and Centrus/LEU (above, enrichment vs. mining are different links in the same chain) — Cameco is a mining major, Centrus an enrichment monopoly; they are complements more than direct rivals.
- **Profitability:** Gross margin **35.11%**, operating margin **13.64%** (down from 16.68%), FCF (CAD) **$556M** TTM (down 38.3%).
- **Street:** **Buy** (21 analysts), target **$127.77** vs. current **$88.07** — **+45.1% upside** (stockanalysis.com/stocks/ccj, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Broadest coverage of the nuclear-theme names, real upside, but revenue and margins are both **declining** this year — a valuation/re-rate bet on the nuclear cycle, not a growth story. **Tier-1 candidate**, slightly weaker fundamentally than LEU or MP.

### WST — West Pharmaceutical Services (pharma packaging, v2 book #16, 3%)
- **Demand:** Injectable drug-delivery components (vials, stoppers, syringe systems) — a picks-and-shovels supplier to the entire injectable-drug industry, including the GLP-1 boom; TTM revenue growth **+12.38%**, accelerating from 6.25% (stockanalysis.com/stocks/wst/financials, read 2026-09-27).
- **How it feeds it:** Capacity expansion tied to GLP-1/biologics demand; **leadership change**: new CEO **Michel Lagarde** (ex-Thermo Fisher) took over **2026-08-31**, succeeding longtime CEO Eric Green — a very recent transition not in v2's thesis.
- **CEO:** **Michel Lagarde**, effective Aug 31, 2026.
- **Competition:** Gerresheimer, Datwyler, SGD Pharma in pharma packaging/components.
- **Profitability:** Gross margin **36.79%**, operating margin **21.97%** (strong), FCF **$436.9M** TTM (+27.0%), net cash **$119M**.
- **Street:** **Strong Buy** (17 analysts), target **$407.56** vs. current **$370.44** — **+10.0% upside** (stockanalysis.com/stocks/wst, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Solid fundamentals but a brand-new, unproven CEO and only ~10% upside to target — not enough asymmetry for a 6-month ROI-maxing bet. **Weak Tier-1 candidate** — see §B (trim, don't drop).

### AGIO — Agios Pharmaceuticals (biotech, v2 book #19, 2%)
- **Demand:** Pyrukynd (PK deficiency, approved) generating real revenue — TTM $98.3M, growth **+140.6%** (stockanalysis.com/stocks/agio/financials, read 2026-09-27); v2's thesis cites a Nov 1 PDUFA (mitapivat/thalassemia, priority review + accelerated-approval path).
- **How it feeds it:** Commercial ramp of Pyrukynd plus the pending mitapivat approval; catalyst **2026-11-01**.
- **CEO:** **Brian Goff** — sold 19,068 shares at $34.71 on Apr 2, 2026 (modest, routine-looking).
- **Competition:** No other approved PK-activator on the market — Agios effectively has the category to itself for now; the competitive risk is a future entrant, not an incumbent.
- **Profitability:** "Gross margin" reads -270.79% and operating margin -466.78% TTM because R&D/SG&A dwarfs the still-small revenue base; cash **$965M** funds years of runway.
- **Street:** **Buy** (10 analysts), target **$46.25** vs. current **$32.58** — **+42.0% upside** (stockanalysis.com/stocks/agio, read 2026-09-27).
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** A real, growing, first-in-category revenue base plus a dated binary catalyst 5 weeks out, decent coverage, modest insider selling. **Tier-1 candidate.**

### PRAX — Praxis Precision Medicines (biotech, v2 book #23, 1%)
- **Demand:** Pre-revenue (FY2024 revenue was $8.55M); the whole story is the **Dec 27, 2026 PDUFA** date v2 flagged, now independently confirmed by the street's own target gap (below).
- **How it feeds it:** Pipeline in epilepsy/CNS disorders; company holds **$1.37B** cash (up from $926M in Dec 2025 — a recent large raise) funding the runway regardless of the PDUFA outcome.
- **CEO:** **Marcio Silva De'Souza** (President, CEO, Director) — no CEO sale found in the rows pulled; the named sellers were a director (option-exercise sale) and General Counsel/an accounting officer, both routine post-exercise sales from late 2025.
- **Competition:** No single named incumbent found this pass in the specific indication; v2's own falsifier ("extension precedes a CRL") is the operative risk, i.e. the competitive risk here is regulatory, not commercial.
- **Profitability:** Pre-revenue; gross profit **-$291M** TTM, operating margin **-2340%** (meaningless on a near-zero revenue base), FCF **-$305M** TTM.
- **Street:** **Strong Buy** (19 analysts — broad coverage), target **$638.68** vs. current **$280.78** — **+127.5% upside** (stockanalysis.com/stocks/prax, read 2026-09-27) — this nearly exactly reproduces v2's own already-cited "18/20 Buy at avg $612 vs $282" framing from two days earlier, i.e. two independent reads agree.
- **Crowd:** Read 2026-09-27 (old.reddit.com/search/?q=PRAX). The ticker collides with a character named "Prax" in r/TheExpanse (a sci-fi show) — every visible result is spoiler threads about that character, not the stock. **No substantive retail discussion of PRAX-the-stock found**, same shape as QUBT's earlier finding: a name that would show up as "attention" in a naive mention-count would be entirely noise here.
- **ROI read:** The single largest, most broadly-covered, most internally-consistent upside number in this whole document, on a dated binary catalyst three months out, funded through the outcome either way by a fresh $1.37B cash pile. **Top-ranked ROI candidate**, with "extension precedes a CRL" as the exact falsifier already on file.

### QUBT — Quantum Computing Inc. (Murat's holding, also in mw_analyst_snapshot)
- **Demand:** Photonics-based quantum computing; TTM revenue growth **+3,635%** off a near-zero base (now $9.82M) (stockanalysis.com/stocks/qubt/financials, read 2026-09-27) — the growth rate is a base-effect artifact, not a demand signal on its own.
- **How it feeds it:** No single dated capacity/contract catalyst found this pass; next earnings ~**2026-03-31** (`mw_analyst_snapshot.jsonl`).
- **CEO:** **Dr. Yuping Huang** (CEO, President, Chairman) — this **updates** the company profile from an earlier assumption; CFO/GC Christopher Roberts exercised and sold ~78,000 shares at $7.85 in March 2026 (well below today's $9.16).
- **Competition:** IonQ, Rigetti, D-Wave — QUBT is a smaller, less-differentiated player among several quantum names on this list; v2's own AI draft explicitly **vetoed** QUBT: *"target dispersion $10 vs $32 is the tell; promotional history."*
- **Profitability:** Gross margin **-18.92%**, operating margin **-700%**, FCF **-$51.5M** TTM; net cash **$931M** (a large recent raise funds years of runway).
- **Street:** **Buy-leaning** (1.50, 8 analysts), target **$18.86** vs. current (mw_analyst_snapshot) **$9.16** — **+105.9% upside**, but the underlying analyst dispersion is wide ($10-$32) — exactly the tell v2 already flagged.
- **Crowd:** Read **2026-09-25** (2 days old, reused here): old.reddit.com "new/past month" search returned almost **no substantive QUBT-specific content** — mostly off-topic substring matches, no r/wallstreetbets or r/pennystocks threads found in that window (`scratchpad/log_qubt_reddit.json`). No pump language observed, but also no real crowd conviction either way.
- **ROI read:** The raw upside number is large but rests on the same wide-dispersion, thin-fundamentals base v2's own AI draft already vetoed, and the crowd check found essentially no fresh retail conviction to offset that. **Excluded from the top 15** on the house's own prior finding, not a fresh one — see §B.

### AARD — Aardvark Therapeutics (biotech, Murat's holding)
- **Demand:** Pre-revenue biotech; lead candidate **ARD-101** hit an **FDA clinical hold in May 2026** — the falsifier has already fired.
- **How it feeds it:** n/a — clinical hold means no near-term regulatory path without a resolution not found this pass.
- **CEO:** **Tien-Li Lee** — **bought** 7,000 shares at $14.48 on Dec 11, 2025 (pre-hold, now deeply underwater); CFO/COO **Nelson Sun** **sold** 62,000 + 14,754 shares at $5.00-5.18 on Sep 10-11, 2026 (post-hold, near today's price) — the CEO's buy and the CFO's sell bracket the exact event that broke the thesis.
- **Competition:** Rhythm Pharmaceuticals and other rare-obesity/hyperphagia players — AARD is a small challenger in an increasingly crowded metabolic-disease space.
- **Profitability:** Pre-revenue; FCF **-$69.4M** TTM, cash **$73.9M** — a shrinking runway.
- **Street:** **Hold-leaning** (2.36, downgraded multiple times in March 2026), target **$10.13** vs. current (mw_analyst_snapshot) **$5.55** — **+82.5% upside**, but this reads as a **stale-target artifact**: the stock is **down ~61% YTD** and multiple analysts downgraded in March, so a target that still implies +82% has likely not been fully re-based to the post-hold reality.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** The falsifier ("FDA clinical hold") already fired before this research pass began. **Exclude** — this is exactly the "explaining a winner after the fact" trap in reverse: a loser whose thesis already broke, dressed in a stale upside number.

### BHVN — Biohaven (biotech, Murat's holding)
- **Demand:** Pre-revenue-focused pipeline; the flagship epilepsy program **BHV-7000 hit an FDA clinical hold**, but the company just signed a **$795M licensing deal with SK Biopharmaceuticals** for a different asset, opakalim (epilepsy) — a partial offset, not a full one.
- **How it feeds it:** The SK deal is the live catalyst; BHV-7000's path is the open question.
- **CEO:** **Vladimir Coric** — notably, director **John W. Childs bought 3,333,333 shares for $24.99M**, and Coric himself bought 666,666 shares for $4.99M, both on **2026-11-13** — a very large, discretionary-looking insider buy cluster, though dated **before** the clinical-hold news (timing relative to the hold not resolved this pass).
- **Competition:** UCB, Jazz Pharmaceuticals (also on this list), SK Life Science in epilepsy — a crowded therapeutic category.
- **Profitability:** Pre-revenue-style losses; operating income **-$530M** TTM, FCF **-$512M** TTM, cash **$268M** (declining), and the company has **shifted from net cash to net debt** (-$29.2M, a -92.3% swing) — the weakest balance-sheet trend of any biotech in this list.
- **Street:** **Buy-leaning** (1.71, 14 analysts), target **$23.08** vs. current (mw_analyst_snapshot) **$13.19** — **+75.0% upside**.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** A large historical insider buy is a real positive signal, but it's not clear it postdates the clinical hold, and the balance sheet just flipped to net debt with a shrinking cash pile. **Speculative, not top-15** — the SK deal is the thing to watch, not a reason to size up yet.

### SLDP — Solid Power (solid-state batteries, Murat's holding)
- **Demand:** Solid-state EV battery materials/licensing; TTM revenue **collapsed -64.32%** (from +17.91% growth in FY2025) (stockanalysis.com/stocks/sldp/financials, read 2026-09-27) — a real, sharp demand deterioration.
- **How it feeds it:** No dated capacity/contract catalyst found this pass; next earnings ~**2026-03-02**.
- **CEO:** **John Van Scoter**, President & CEO — no recent sale found; two directors sold in 2025-2026, both at prices well above today's.
- **Competition:** QuantumScape, Toyota's internal program — Solid Power is a smaller, licensing-model player against better-funded rivals with their own manufacturing.
- **Profitability:** Gross margin **-105.06%**, operating margin **-1,445%** TTM — catastrophic on a shrinking revenue base; cash **$242M**.
- **Street:** **Strong Buy (1.00)**, but only **2 analysts** cover it (mw_analyst_snapshot), target **$6.88** vs. current **$2.35** — **+192.8% upside**, which is the largest raw number in the entire document and the least reliable, given the 2-analyst base and the collapsing revenue.
- **Crowd:** Read 2026-09-27 (old.reddit.com/search/?q=SLDP) — a real, dedicated r/SLDP community exists (5 years old). One substantive, non-promotional post found: 12 days old, 16 points/14 comments, summarizing an **8-K filing** disclosing a roadmap to "pre-commercial 500MT" production in 2027 and "2,000+MT" later, with falling electrolyte costs. No pump language observed; low engagement (mid-teens points) suggests this is a small, technically-literate niche audience, not a hype crowd — consistent with the "no fresh retail conviction" read elsewhere in this section.
- **ROI read:** Textbook "screener number is not evidence" — a huge upside percentage on a 2-analyst target sitting on top of a 64% revenue collapse and a -1,445% operating margin. **Exclude from the top 15** on fundamentals, not on the target.

### ABSI — Absci Corporation (AI drug design, new candidate from mw_analyst_snapshot)
- **Demand:** AI-designed antibody/biologics platform; revenue is trivial ($1.56M TTM, declining -62.3%) — the company is a platform/partnership play, not a product-revenue story yet.
- **How it feeds it:** Partnership deals with pharma (not independently dated this pass); next earnings ~**2027-03-23**.
- **CEO:** **Sean McClain** — exercised options (no discretionary sale flagged); more notably, **three separate insiders BOUGHT** in 2026: director Mary Szela ($148,866, Jun 30), director Menelas Pangalos ($200,748, May 13, in **multiple** buys), and Chief Innovation Officer Andreas Busch ($229,000, Mar 12) — a genuine cluster of open-market insider buying, unusual in this whole document.
- **Competition:** Recursion Pharmaceuticals, Isomorphic Labs (Alphabet-backed) — ABSI is a small player in a space dominated by much larger, better-funded AI-drug-design rivals.
- **Profitability:** Deeply unprofitable on a trivial revenue base; cash **$201M** (up from $144M), net cash **$197M**.
- **Street:** **Strong Buy** (1.18, 11 analysts), target **$14.40** vs. current **$10.35** — **+39.1% upside**.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** The insider-buying cluster (three separate people, open-market, sized in six figures each) is the standout signal here, against a real competitive-scale disadvantage. **Tier-1 candidate**, sized for the insider signal more than the tiny revenue base.

### AMSC — American Superconductor (grid tech, new candidate from mw_analyst_snapshot)
- **Demand:** Grid-resiliency/superconductor products (a direct AI-power-buildout beneficiary, adjacent to v2's VRT/GEV/NVT power theme but not currently in the book); TTM revenue growth **+25.9%**, operating margin turned positive **+4.5%** (a real turnaround) (stockanalysis.com/stocks/amsc/financials, read 2026-09-27).
- **How it feeds it:** Grid-hardening and superconductor cable products for utilities and data-center power infrastructure; next earnings ~**2027-06-02**.
- **CEO:** **Daniel McGahn**, Chairman/President/CEO — sold at $37-42/share in June 2026 (routine, well above today's $30.01).
- **Competition:** Siemens Energy, Hitachi Energy, GE Vernova (also on this list) in grid equipment — AMSC is the small specialist against much larger grid-equipment majors.
- **Profitability:** Gross margin **29.02%**, operating margin **+4.50%** (a turnaround from negative), FCF **+$20.5M** TTM, net cash **$140M** — debt-free.
- **Street:** **Strong Buy** (1.00), but only **4 analysts**, target **$61.75/61.40** vs. current **$30.01** — **+105.8% upside**.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** A genuine margin turnaround, debt-free balance sheet, and a direct line into the AI-power-grid theme this whole shortlist is built around — but only 4 analysts back the huge upside number. **Tier-1 candidate**, thin-coverage caveat noted.

### HUBS — HubSpot (SaaS CRM, new candidate from mw_analyst_snapshot)
- **Demand:** SMB-focused CRM/marketing software; TTM revenue growth **+21.11%**, first year of **positive operating margin (+3.94%)** after years of losses (stockanalysis.com/stocks/hubs/financials, read 2026-09-27).
- **How it feeds it:** AI-feature-driven seat/tier upsell (not independently detailed this pass); next earnings ~**2027-02-17**.
- **CEO:** **Yamini Rangan** — no sale found in the rows pulled; co-founder/director **Brian Halligan** sold 8,500 shares monthly in Aug/Sep 2026 (a steady, plan-like cadence), while director **Gerald Dischler bought** 925 shares Aug 10.
- **Competition:** Salesforce (also on this list, far larger), Zoho, Microsoft Dynamics — HubSpot is the SMB-focused challenger against Salesforce's enterprise scale.
- **Profitability:** Gross margin **83.25%**, FCF **$797.5M** TTM (+27.3%), net cash **$1.1B**.
- **Street:** **Moderate Buy** (2.26, thinner conviction than most names here), target **$249.63** vs. current **$221.56** — **+12.7% upside**.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Real profitability inflection, but a modest ~13% upside — not asymmetric enough for a 6-month ROI-maxing list. **Tier-1 name, not top-15.**

### KYTX — Kyverna Therapeutics (cell therapy, new candidate from mw_analyst_snapshot)
- **Demand:** Pre-revenue CAR-T-adjacent cell therapy for autoimmune disease; stock has **collapsed** — from insider sale prices near $9.25-9.53 in April 2026 to **$6.99** today (mw_analyst_snapshot).
- **How it feeds it:** Clinical pipeline; next earnings ~**2027-04-01**.
- **CEO:** **Warner Biddle** (stockanalysis.com/stocks/kytx/company, read 2026-09-27) — no sale by name found; a director (Beth Seidenberg) **bought** 133,333 shares at $7.50 in Dec 2025 (essentially at today's price).
- **Competition:** Cabaletta Bio, Bristol Myers Squibb's cell-therapy franchise in the same autoimmune-CAR-T space — a well-capitalized incumbent (BMS) plus smaller direct rivals.
- **Profitability:** Pre-revenue; FCF **-$159M** TTM, cash **$199M** (declining from $279M).
- **Street:** **"Strong Buy" (1.00)**, only **6 analysts**, target **$30.40** vs. current **$6.99** — **+334.8% upside** — the single largest raw number in the whole document, and the least credible: a target this far from spot on 6 thin analyst names, on a stock that has already fallen roughly 25% since the April insider sales, reads as a **stale target that has not been re-based to the sell-off** rather than a real opportunity.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** **Exclude.** This is the clearest "target dispersion is the tell" case in the whole document — almost identical in shape to v2's own QUBT veto.

### NTLA — Intellia Therapeutics (gene editing, new candidate from mw_analyst_snapshot)
- **Demand:** In-vivo CRISPR gene-editing platform; TTM revenue **+12.58%** ($59.5M, mostly collaboration revenue, not product sales) (stockanalysis.com/stocks/ntla/financials, read 2026-09-27).
- **How it feeds it:** Partnership milestones (Regeneron collaboration, not independently detailed this pass); next earnings ~**2027-02-25**.
- **CEO:** **John M. Leonard** — sold $293,641 at $12.60-13.00 in Aug 2026 (modest); director **Fred E. Cohen bought** $1.4M at $9.35 in Jan 2026 — a real, sizeable insider buy below today's $12.16.
- **Competition:** CRISPR Therapeutics, Editas Medicine, Beam Therapeutics — a crowded gene-editing field where clinical/regulatory news, not commercial execution, moves the stock.
- **Profitability:** Deeply unprofitable (operating margin -712%); FCF **-$349M** TTM, cash **$628M**.
- **Street:** **Buy/Overperform** (2.26, 19 analysts — decent coverage), target **$23.81** vs. current **$12.16** — **+95.8% upside**.
- **Crowd:** `n/a` (see limitation note). Short float **34.85%** — the highest of any name in this document, a real squeeze setup if a positive catalyst lands.
- **ROI read:** Broad coverage, a real director buy below spot, and the highest short interest here — a genuine gene-editing binary-catalyst candidate, though the specific near-term catalyst wasn't independently dated this pass. **Tier-1 candidate**, catalyst-date gap noted as the thing to fill before sizing.

### PRCH — Porch Group (insurtech, new candidate from mw_analyst_snapshot)
- **Demand:** Home-services/insurance-data platform; TTM revenue growth **+16.10%**, operating margin turned positive (**+7.87%**), and the company reported "record profitability" in Q2 2026 (stockanalysis.com/stocks/prch/financials, read 2026-09-27).
- **How it feeds it:** Insurance-data monetization tied to the home-services marketplace; next earnings ~**2027-03-02**.
- **CEO:** **Matt Ehrlichman** (Founder/CEO) — sold in April-May 2026 at $6.84-11.12, well below today's $16.47, i.e. sold before the rally, not into it.
- **Competition:** Angi (IAC), Thumbtack in home-services marketplaces; a differentiated insurance-data angle vs. pure lead-gen rivals.
- **Profitability:** Gross margin **72.10%**, operating margin **+7.87%** (real turnaround), FCF **$95.6M** TTM (+905.5%), net debt **-$187M**.
- **Street:** **Buy** (1.25, 8 analysts), target **$20.69** vs. current **$16.47** — **+25.6% upside**.
- **Crowd:** `n/a` (see limitation note). Recent COO/director selling in September 2026 (post-rally profit-taking) is the one caution flag.
- **ROI read:** A real profitability turnaround already reported, decent coverage, modest but real upside. **Tier-1 candidate, not top-15** — the easy money (April lows to today) has already been made.

### SOC — Sable Offshore (oil & gas, new candidate from mw_analyst_snapshot)
- **Demand:** California offshore oil restart; financials show a **distressed** profile — FCF **-$559M** TTM, net debt **-$966M**, total debt **$988M** against only **$21.6M** cash (stockanalysis.com/stocks/soc/financials, read 2026-09-27).
- **How it feeds it:** Restart of previously-shuttered offshore platforms; no dated near-term catalyst found this pass.
- **CEO:** **James C. Flores** (Chairman & CEO) — sold **$1.87M** at $13.33-13.56 in late April 2026, alongside the President/COO, CFO and an EVP, all the same two days — a coordinated executive sale at a price **more than 3x** today's $3.97.
- **Competition:** Chevron, other Pacific-coast operators — SOC is a small, single-asset restart story, not a diversified producer.
- **Profitability:** Deeply negative across every metric; short float **27.49%** (high, consistent with a broken/distressed name).
- **Street:** **Buy (1.29)**, target **$9.40** vs. current **$3.97** — **+136.8% upside**, but the target has clearly not caught up to a stock that has fallen more than 70% since the executives sold at $13-14.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** **Exclude.** The insiders sold at 3x today's price before the thesis broke; the "upside" is a stale target on a name whose falsifier has already fired.

### AVPT — AvePoint (SaaS data-governance, pc_plan PROBE list)
- **Demand:** Microsoft-365/data-governance SaaS; TTM revenue growth **+24.95%**, gross margin **73.45%** (stockanalysis.com/stocks/avpt/financials, read 2026-09-27).
- **How it feeds it:** Cross-sell into the Microsoft ecosystem; next earnings not independently dated this pass.
- **CEO:** **Tianyi Jiang** — exercised options (Oct 2025), no discretionary sale flagged; Chief Legal Officer Brian Brown sold repeatedly Aug-Sep 2026; Executive Chairman Xunkai Gong exercised a large option block in June.
- **Competition:** Microsoft's own native governance tooling is the long-run competitive risk; Veeam and Rubrik in adjacent data-protection.
- **Profitability:** Operating margin **9.89%**, FCF **$101M** TTM (+24.5%), net cash **$391M**.
- **Street:** **Buy** (1.57, 14 analysts), target **$16.80** vs. current **$13.00** — **+29.2% upside**.
- **Crowd:** `n/a` (see limitation note).
- **ROI read:** Solid growth and margins, real but moderate upside. **Tier-1 name, not top-15** — the Microsoft-platform-risk competitive note is the thing worth watching most.

---

# TIER 2 — compact profiles (mega/large-cap and macro-thesis names)

*Format: Demand/catalyst · CEO · Competition · Profitability (TTM) · Street (rating, target, current, upside) · Crowd · ROI read.*

**VRT — Vertiv** (v2 book, 12%): AI-datacenter power/cooling; $2.6B Utility Innovations deal, deferred revenue $1.81B→$3.63B; Q3 print ~Oct 28. CEO **Giordano Albertazzi** (stockanalysis.com/stocks/vrt/company). Competes with Schneider Electric, Eaton. Rev growth +26.2%, op margin 20.0%, FCF $2.93B. Street: Strong Buy (34 analysts, mw), target $339.21 vs current $245.30 (mw_analyst_snapshot) → **+38.3% upside**. Crowd n/a. ROI read: real backlog growth, genuine AI-power beneficiary, large upside — a credible large-cap complement to the small-cap AI-power names (NVT, AMSC) above; excluded from top-15 only on the "mega-cap is a sensor" house rule, not on fundamentals.

**GEV — GE Vernova** (v2 book, 9%): Turbine backlog 116 GW; Q3 print ~Oct 28. CEO **Scott Strazik**. Competes with Siemens Energy, Mitsubishi Power. Rev growth +13.0%, FCF $12.4B (+359%). Street: Overweight (41 analysts), target $1,214.37 vs current $955.04 (mw) → **+27.1% upside**. Crowd n/a. ROI read: real, large, already-recognized theme; sensor not the trade.

**MU — Micron** (v2 book, 9%): HBM4 allocation ~20% of NVIDIA; FQ4 print **2026-09-30** (3 days out). CEO **Sanjay Mehrotra** — sold ~$38.7M in Aug 2026 (part of a 279% YTD rally). Competes with Samsung, SK Hynix. Rev growth +167%, gross margin 72.6%. Street: Strong Buy (57 analysts), target $1,575.88 vs current $1,080.53 (mw) → **+45.8% upside**, with the print landing in 3 days. Crowd n/a. ROI read: genuinely large near-term catalyst on a mega-cap; the one Tier-2 name arguably belonging in a top-15 discussion — see §A.

**TSM — Taiwan Semiconductor**: Q3 print confirmed Oct 15. CEO **Dr. C.C. Wei**. Competes with Samsung Foundry, Intel Foundry. Rev growth +30.6%, op margin 56.1%. Street: Buy, target $543.66 vs current $450.61 → **+20.6% upside**. Crowd n/a. ROI read: real but modest for a $2.3T name; sensor not the trade.

**HOOD — Robinhood** (v2 book, 7%): Event-contract revenue $156M in Q2 > crypto revenue; Q3 print ~Nov 4. CEO **Vlad Tenev** — sold ~$60M+ across Sep 21-22, 2026, two days in a row, right before this pass. Competes with Kalshi/Polymarket (prediction markets) and traditional brokers. Rev growth +38.3%, op margin +46.0%. Street: Buy, target $133.77 vs current n/a this pass. Crowd: reused from 2026-09-25 read — DKNG's reddit thread references HOOD/Kalshi regulatory tailwind narrative indirectly; no direct HOOD read this pass. ROI read: heavy, back-to-back CEO selling right into this window is the single most concerning insider signal on any v2 holding; **trim candidate**, not an add.

**AVGO — Broadcom** (v2 book, 6%): custom AI accelerators already monetizing. CEO **Hock Tan**. Competes with Marvell, Nvidia (adjacent). Rev growth +48.7%, gross margin 75.5%. Street: Strong Buy, target $533.94 vs current $352.81 → **+51.3% upside**. Crowd n/a. ROI read: real upside number for a mega-cap; sensor not the trade, but the magnitude is worth flagging.

**CLS — Celestica** (v2 book, 5%): AI-server ODM/manufacturing. CEO **Robert Mionis** — heavy insider selling (-30.8% insider transaction score, the most negative in this document) including a Feb 2026 sale of 100,000 shares. Competes with Quanta, Foxconn (per the concurrent session's own Bing search seen mid-pass). Rev growth +47.3%, op margin 8.9%. Street: Strong Buy, target $463.82 vs current ~$360 → **+28.8% upside**. Crowd n/a. ROI read: fastest-growing ODM name here, but the -30.8% insider-selling score is a real caution.

**BE — Bloom Energy** (v2 book, 4%): behind-the-meter power for data centers. CEO **K.R. Sridhar** — sold 200,000 shares at $170 in Feb 2026 (well below today's ~$270, i.e. sold before the run, not into it). Competes with Fuel Cell Energy, on-site gas gensets. Rev growth +91.0%, newly profitable at op margin +11.7%. Street: Buy, target $287.26 vs current n/a this pass, but P/E **393x** — an extremely rich valuation. Crowd: an X handle (`x.com/BloomEnergy`) was open in the shared browser session mid-pass (another agent's read, not independently summarized here). ROI read: real turnaround to profitability, but priced very richly; **trim/hold**, not an add at this valuation.

**NVT — nVent Electric** (new v2 name for the book, not in the 24; found via `mw_analyst_snapshot`/the companion doc's card): grid/cooling, guide raised to 37-39%. CEO **Beth Wozniak**. Competes with Eaton, Schneider Electric. Rev growth +46.2%, FCF +49.9%. Street: Buy, target $212.88 vs current n/a this pass → the companion doc's own formula ranks NVT **#1** on its σ-bounded score (+24.8%). Crowd n/a. ROI read: agrees with the companion quant list — a credible large-cap AI-power name.

**DKNG — DraftKings** (v2 book HOLD, 3%; Murat's holding): sportsbook + prediction-market exposure; AGA forecasts a flat legal handle (v2's own falsifier). CEO **Jason Robins**. Competes with FanDuel/Flutter, and increasingly Kalshi/Polymarket in prediction markets. Rev growth +15.0%, op margin -2.7% (near breakeven). Street: Buy, target $34.33 vs current $21.27 (mw) → **+61.4% upside**. **Crowd (read 2026-09-25, reused):** dominant retail narrative is bullish — "mispriced," targets $50-$100+, Kalshi/Polymarket regulatory-crackdown tailwind, "pivoted to profitability" — drawn mostly from low-engagement r/DKNG posts plus older WSB hype, not fresh high-volume conviction (`scratchpad/log_dkng_reddit.json`). ROI read: the crowd and the target agree directionally, but v2's own flat-handle falsifier is the thing to watch before sizing up from HOLD.

**AAPL — Apple** (WSJ pick, "iPhone revenue +17% this year," 2026-09-26): CEO **Tim Cook**. Rev growth +14.2%, FCF $136.7B. Street: Buy, target $337.68 vs current n/a. Crowd n/a. ROI read: a real, dated bullish claim from a primary source, but Apple's scale makes it a sensor, not a 6-month ROI mover.

**AMGN — Amgen** (WSJ pick, negative — "investors doubted the Lp(a) approach," 2026-09-26): CEO **Robert Bradway**. Rev growth +9.1%, op margin 33.4%. Street: Buy, target $396.93. ROI read: WSJ's own read is negative; not a candidate.

**BA — Boeing** (WSJ picks, negative x2 — Spirit AeroSystems "bleeding red ink"; a new 737 MAX navigation software glitch, both 2026-09-26): CEO **Robert (Kelly) Ortberg**. Rev growth +24.8% but op margin -5.4%, FCF -$210M. Street: Buy, target $273.59. ROI read: two independent negative dated claims same day; not a candidate.

**BSP — Bending Spoons** (WSJ pick, negative — "rising rates will make acquisition funding harder... stock likely to fall," 2026-09-26): Italian tech roll-up (Airtable $1.285B Aug 2026, Miro $1.355B Sep 2026 acquisitions), IPO'd 2026-07-01. CEO **Luca Ferrari**. Rev growth +427.5%(!), op margin 34.5%. Street: Buy-leaning, target $48.25. ROI read: real growth but the primary-source thesis today is bearish on funding risk for exactly this acquisition-fueled model; **not a candidate**, flagged as a fresh WSJ-sourced risk on a name otherwise easy to mistake for a growth story.

**CRM — Salesforce** (WSJ pick, "undervalued... good bargain," 2026-09-26): CEO **Marc Benioff** — director G. Mason Morfit bought $25M in Dec 2025. Rev growth +11.2%, FCF margin 34.5%. Street: Buy, target $282.78 vs current n/a. ROI read: dated bullish primary-source claim plus a real insider buy; a large-cap value name, not a 6-month mover on its own.

**HWM — Howmet Aerospace** (WSJ pick, "SpaceX's entry does not weaken the long-term case," 2026-09-26): CEO **John C. Plant**. Rev growth +18.1%, op margin 27.3%. Street: Buy, target $343.43. ROI read: WSJ's own framing is defensive (rebutting a competitive threat), not a fresh bull case.

**LNG — Cheniere Energy** (WSJ pick, "benefits from higher LNG prices if Europe needs spot supplies," 2026-09-26): CEO **Jack A. Fusco**. Competes/complements Venture Global (below) as the other major US LNG exporter. Rev growth +14.8%, op margin 30.5%. Street: Strong Buy, target $312.33. ROI read: real, dated, weather/geopolitics-contingent catalyst; a large-cap macro bet.

**VG — Venture Global** (WSJ pick, same LNG-price thesis as LNG, 2026-09-26): CEO **Michael A. Sabel**. Rev growth +100.7%(!) but FCF **-$7.0B** (massive capex on new terminals) and net debt **$39.7B** — much more levered and earlier-stage than Cheniere. Street: Buy, target $16.67. ROI read: same catalyst as LNG with far more balance-sheet risk; LNG is the better risk-adjusted way to play the same WSJ-sourced thesis.

**NOW — ServiceNow** (WSJ pick, "strong sales growth supports a positive view," 2026-09-26): CEO **Bill McDermott**. Rev growth +22.2%, FCF margin 31.1%. Street: Buy, target $145.87 (unusually low vs. typical historical ServiceNow price levels — flagged as a possible data inconsistency, not resolved this pass). ROI read: real, dated bullish claim; large-cap.

**NVO — Novo** (WSJ pick, negative — "inflammation drug failed to prevent cardiovascular events," 2026-09-26): **rebranded from "Novo Nordisk" to "Novo" on 2026-09-14**; new CEO **Mike Doustdar**; Morgan Stanley downgraded to Underweight 2026-09-11; stock **-23.74% YTD**. Competes with Eli Lilly (the obesity-drug duopoly rival to VKTX's target). Rev growth +5.6% (decelerating from 25% in FY2024), op margin 49.0%. Street: target $44.50, rating 3.40 (weak). ROI read: multiple independent negative signals same window; **not a candidate**, and directly relevant as the "large incumbent under pressure" context for VKTX's bull case above.

**PSNL — Personalis** (WSJ pick, "shares trading above the $16.25 deal price signal investors expect a higher bid," 2026-09-26): being **acquired by Tempus AI** (TEM, below) — Tempus built a ~13M-share stake Nov-Dec 2025 ahead of the deal. CEO **Christopher Hall** — sold at $16.22 on Sep 18, 2026 (right at the deal price). Rev declining -13.3%. Street: Hold (downgraded Aug 2026), target $16.25 vs current n/a. ROI read: a genuine merger-arb situation — the WSJ's own framing ("signal investors expect a higher bid") is the entire thesis; falsifier is the deal closing at $16.25 with no bump.

**SNOW — Snowflake** (WSJ pick, "raised sales forecast signals a positive outlook," 2026-09-26): CEO **Sridhar Ramaswamy**. Rev growth +32.0%, FCF margin 22.0%. Street: Buy, target $440.54 vs current n/a. Heavy insider selling (co-founder, director, multiple execs, -24.3% insider score) right after a 23% post-earnings surge. ROI read: real, dated bullish claim, but the insider-selling pattern right into the rally is a caution.

**TEM — Tempus AI** (WSJ pick, "sequencing revenue... an opportunity barely reflected in Tempus stock," 2026-09-26): CEO **Eric Lefkofsky** — sold ~$19.4M Sep 22, 2026 (part of a pattern following the PSNL acquisition announcement). Rev growth +50.4%, still unprofitable (op margin -19.1%). Street: Neutral-leaning (2.30), target $67.94. ROI read: the WSJ thesis (sequencing revenue underappreciated) is real and dated, but heavy CEO selling right after the PSNL deal is a genuine tension with the bull case; the safer way to play the same idea may be PSNL itself (the arb) rather than TEM (the acquirer with a selling CEO).

**WDAY — Workday** (WSJ pick, "strong results and growing AI adoption support a positive view," 2026-09-26): CEO **Carl Eschenbach** (co-founder David Duffield selling steadily via trust, not an operating signal). Rev growth +13.4%, FCF $2.84B. Street: Buy, target $211.14. ROI read: real, dated bullish claim; large-cap, modest expected magnitude.

**BN — Brookfield Corp** (Barron's pick, "undervalued, trading at a discount to asset value," 2026-09-26): CEO **Bruce Flatt**. Rev growth +3.1% only, FCF -$9.4B (capex-heavy). Street: Buy, target $54.14 vs current $36.87 → **+46.8% upside**. ROI read: a real, dated value thesis from a primary source with a large upside number; the growth rate itself is slow, so this is a re-rating bet, not a growth bet.

**AMZN, GOOG/GOOGL, META, NVDA** (pc_plan PROBE mega-caps): all four are exactly what the "mega-cap is a sensor" invariant describes — AMZN (CEO **Andy Jassy**, rev +15.8%, FCF **-$11.6B** on $173B capex), Alphabet (CEO **Sundar Pichai**, rev +20.1%, FCF $53.3B), Meta (CEO **Mark Zuckerberg**, rev +27.7%, FCF $41.0B, insiders selling steadily), NVIDIA (CEO **Jensen Huang**, rev +83.4%, gross margin 74.7%, target $333.47 vs current ~$220-225 from insider-sale prices → modest upside for a $5.4T company). None of the four is a top-15 ROI candidate at this size; all four are read this pass **as sensors** for the AI-capex cycle the small/mid names above are actually monetizing.

**INCY — Incyte**: TTM rev +26.9%, FCF $1.92B. CEO not confirmed this pass. Street: target $128.91. Insider selling across R&D/medical leadership. ROI read: solid large-cap biopharma, not asymmetric.

**JAZZ — Jazz Pharmaceuticals**: rev +12.6%, FCF margin 34.6%. CEO **Renee Gala**. Street: Strong Buy, target $296.20. ROI read: steady, well-covered, not a 6-month mover on the data gathered.

**SNDR — Schneider National**: rev +6.3%, thin margins (op margin 3.0%). CEO **Jim Filter** (Mark Rourke moved to Executive Chairman). Street: Buy, target $37.50 vs current n/a. ROI read: a trucking-cycle proxy, not an asymmetric bet.

---

# (A) The ROI-maxing shortlist — top 15

**Read this list beside the companion doc's §17 caveat: raw analyst-target upside has measured NEGATIVE
forward return in this repo's own tested cross-section. Every entry below earns its place on a named
mechanism and a falsifier, not on the upside percentage alone — the percentage is printed because Murat
asked for it, not because it is validated evidence.**

| # | Ticker | Mechanism | Upside (target vs. spot, 2026-09-27 reads) | Falsifier | Crowd flag |
|---|---|---|---|---|---|
| 1 | **PRAX** | Dec 27 PDUFA binary; $1.37B cash funds either outcome; 19-analyst Strong Buy independently reproduces v2's own two-days-earlier number | +127.5% | "extension precedes a CRL" (v2's own falsifier) | n/a — not checked |
| 2 | **BBIO** | Approved, +202% revenue-growth drug (Attruby) taking share from Pfizer's Vyndaqel franchise — growth is already revenue, not a readout | +66.4% | Pfizer defends share faster than expected; CEO's routine selling accelerates | n/a — not checked |
| 3 | **VKTX** | Obesity data (Sept durability) vs. Novo/Lilly duopoly; broadest biotech coverage here (20 analysts) | +166.1% | Sept 24 $500M dilution round + insiders sold straight into it — dilution risk is live | n/a — not checked |
| 4 | **LEU** | Domestic HALEU-enrichment monopoly; WSJ independently reaffirmed the exact thesis same day (2026-09-26) | +68.2% | DOE stays the only customer (v2's own falsifier) | n/a — not checked |
| 5 | **MP** | Fastest real revenue growth (+72%) of any non-biotech name here; government floor-price/offtake; insiders sold at HIGHER prices than today | +52.1% | Section 232 tariff never lands; INTC-style legal challenge to the equity stake | n/a — not checked |
| 6 | **CCJ** | Broadest nuclear-theme coverage (21 analysts); complements LEU (mining vs. enrichment) | +45.1% | Revenue and margins both declining this year — a cycle bet, not a growth bet | n/a — not checked |
| 7 | **COGT** | 12-analyst Strong Buy, $792M cash runway, named competitive threat (Blueprint's approved Ayvakit) is explicit, not hidden | +72.8% | Blueprint share-loss/label expansion in the same indication | n/a — not checked |
| 8 | **AGIO** | Real, +141%-growing first-in-category revenue (Pyrukynd) + Nov 1 PDUFA five weeks out | +42.0% | CRL on mitapivat | n/a — not checked |
| 9 | **AMSC** | Genuine margin turnaround (op margin flipped positive), debt-free, direct AI-power-grid beneficiary | +105.8% | Only 4 analysts back the number — thin-coverage caveat is the falsifier's other half | n/a — not checked |
| 10 | **IONQ** | Dated NVIDIA-decoder collaboration (Sep 23, 2026), fortress balance sheet ($2.06B net cash) | +47.6% | v2's own falsifier: "no third-party replication" | n/a — not checked |
| 11 | **MU** | FQ4 print in **3 days** (2026-09-30); HBM4 allocation story; the one Tier-2 name whose near-term magnitude arguably overrides the "mega-cap sensor" rule | +45.8% | Print misses $49.0B revenue / 86% gross margin / $31.00 EPS bar (companion doc's own falsifier) | n/a — not checked |
| 12 | **AGYS** | Accelerating revenue (+16% latest quarter), Strong Buy, clean balance sheet, catalyst lands exactly at the rehearsal book's own Oct 26 check date | +35.0% | CEO's $21.3M August sale turns out to be a warning, not routine | n/a — not checked |
| 13 | **PRGS** | Fastest software grower here (+15.5%), 30%+ FCF margin, Strong Buy, Oct 21 catalyst | +45.4% | Acquisition-roll-up model stumbles on integration | n/a — not checked |
| 14 | **NOVT** | Direct humanoid-robotics-servo demand claim (v2's own thesis); healthy balance sheet | +35.1% | Only 3 analysts — thin coverage; CEO sold all year | n/a — not checked |
| 15 | **ABSI** | Rare, genuine three-person open-market insider-buying cluster (director, director, CIO) against a real competitive-scale disadvantage | +39.1% | Recursion/Isomorphic Labs out-execute on partnership deals | n/a — not checked |

**Just outside the 15, for the record:** BN (+46.8%, real value thesis, slow growth), NVT (agrees with the
companion doc's own #1 rank), NTLA (highest short float in the document, +95.8%, but catalyst date not
pinned down this pass), AGYS's dress-rehearsal sibling PRGS already included, HOOD (real growth, but the
CEO's two-day, ~$60M sale right into this window is a stronger signal than the +61% target gap).

---

# (B) Names to drop from v2 (with reason)

- **RGEN** — the "Strong Buy" label is stale relative to its own target: $189.48 target vs. $189.68 spot is
  **-0.11%**, and the CEO sold at $190 and $180 the same week this research ran. There is no more asymmetry
  left in this name at these levels.
- **WST** — only +10.0% upside, and a brand-new, unproven CEO (Michel Lagarde, in the seat five weeks) who
  wasn't in v2's thesis at all. Trim, don't add to; not enough asymmetry to justify fresh capital.
- **QUBT** (Murat's personal holding, separate from the v2 book which already excludes it) — this pass's own
  research reproduces v2's original veto almost exactly: wide analyst dispersion, thin fresh crowd
  conviction (2026-09-25 reddit read found essentially no substantive QUBT discussion), and no new
  demand fact found to overturn the "promotional history" flag.
- **HOOD** — not a drop from the book (still a real, growing business), but flagged for a **trim**: CEO Vlad
  Tenev sold roughly **$60M across two consecutive days (Sep 21-22, 2026)**, the single most concentrated
  insider-selling event found anywhere in this pass, landing right before this research ran.

# (C) New candidates found on the way (with source)

- **BBIO** — found via the v2 book itself (already a 1% holding) but re-graded up hard on this pass: it is
  the only name in the whole document with real, approved, +202%-growing product revenue rather than a
  future readout. Source: stockanalysis.com/stocks/bbio (read 2026-09-27).
- **AMSC** — found via `mw_analyst_snapshot.jsonl`; a genuine margin-turnaround, debt-free AI-power-grid name
  adjacent to VRT/GEV/NVT but not currently in any Aegis book. Source: `backend/data/optimus/news_corpus/
  dowjones/_structured/mw_analyst_snapshot.jsonl` + stockanalysis.com/finviz (read 2026-09-27).
- **ABSI** — found via `mw_analyst_snapshot.jsonl`; the insider-buying cluster (three separate people, all
  open-market, all 2026) is unusual enough to be worth a dedicated look outside this note. Same sources.
- **PSNL/TEM merger arb** — found via the WSJ Heard on the Street row for PSNL (`predictions.jsonl`,
  made 2026-09-26): a live, dated, sourced arbitrage situation (Tempus AI's pending acquisition of
  Personalis, shares trading above the $16.25 deal price) that is not currently a position in any book.
- **AGYS / PRGS / NOVT** — already in Aegis's universe (dress rehearsal book, v2 book respectively) but
  worth flagging as *new to the ROI-maxing frame specifically*: none of the three had been read for
  demand/CEO/competition/crowd before this pass.

# (D) What changed since 2026-09-26

- **NVEC:** the company profile now names **Peter Eames** as CEO; Aegis's own insider-trading pull still
  shows the most recent CEO-tagged Form 4 under **Daniel Baker**. A leadership transition appears to have
  happened that the repo's data has not caught up to — worth a dedicated Form-4/8-K check before the next
  read.
- **WST:** **Michel Lagarde** became CEO effective **2026-08-31**, succeeding Eric Green — inside the last
  four weeks, and not reflected in v2's thesis text.
- **NVO:** rebranded from "Novo Nordisk" to "**Novo**" on **2026-09-14**; Mike Doustdar is CEO; Morgan
  Stanley downgraded to Underweight **2026-09-11**; WSJ's 2026-09-26 piece adds a fresh negative catalyst
  (failed cardiovascular trial for an inflammation drug) on top of an already -23.7% YTD stock.
- **QUBT:** CEO is **Dr. Yuping Huang**, not an earlier-assumed name; a new Chief Revenue Officer (Susan
  Hunt) was a recent appointment per the company profile.
- **PSNL/TEM:** the Tempus acquisition of Personalis, and PSNL trading above the $16.25 deal price
  "signaling investors expect a higher bid," is a 2026-09-26-dated WSJ claim not previously in any Aegis
  book.
- **BSP (Bending Spoons):** a fresh, dated (2026-09-26) WSJ bear case — rising rates threaten the
  acquisition-funded growth model — arrived the same day Aegis's own predictions ledger picked it up as a
  Dow Jones row for the first time.
- **The Bloomberg dress-rehearsal book itself** (NVEC, MAN, RHI, ACI, PEGA, IRDM, HELE, SMPL, PRGS, AGYS)
  was frozen **2026-09-27**, entering **2026-09-28** — every dress-rehearsal name in this note is being
  read for demand/CEO/competition for the first time.
- **The 2026-09-27 committee PROBE contract** (`backend/data/optimus/decisions/2026-09-27.json`, chunk 18)
  is far larger than the pc_plan file this note's brief pointed to (97 rows, 92 PROBE, capital $40,000,
  mandate **REFUSED** on capital/cap disagreements) and adds names not otherwise in this shortlist (ADUS,
  ALG, ARCO, BR, CHD, CHH, GMAB, MSFT, PAGS, PDS, STNG, TS) — out of scope for this pass by the brief's own
  instruction to use the pc_plan file specifically, but worth knowing the funnel is fresher and larger than
  the 10-name file alone suggests.
- **The companion quant document** (`stock_lists_2026-09-27_v3.md`) landed the same day and independently
  confirms two of this note's own findings: NVT ranks #1 on its σ-bounded formula (matching this note's
  Tier-2 read), and it carries the standing §17 caveat this note has folded into every upside number above.

---

## Appendix — tooling notes for the next session

- **WebFetch** handled stockanalysis.com, finviz.com, investing.com and SEC EDGAR cleanly and fast — no
  pacing needed, no browser-profile contention. Prefer it over OpenClaw browser for every financial-data
  site in the brief; it was materially cheaper here.
- **OpenClaw browser + `old.reddit.com/search/?q=<TICKER>`** works when the URL has **no `&`**: the
  `openclaw_client._run()` wrapper runs `shell=True` on Windows, so a query string like
  `?q=X&sort=new&t=month` gets torn apart by `cmd.exe`'s `&` operator before it reaches the browser. Drop
  the extra parameters; a single `?q=<TICKER>` still returns real content (proven on NVEC this session).
- **The `muratclaw` browser profile is shared across concurrent Aegis sessions.** This pass collided with
  another session's live browsing (8 open tabs mid-pass: VRTX IR, a Celestica-competitor Bing search,
  Robinhood/Broadcom/Micron IR, two X handles) and it broke this session's own tab-matching logic (`no tab`,
  a wrong stale tab). A future crowd-check pass should either serialize with any concurrent session or
  accept the same `n/a` outcome documented throughout this note.
- **WebSearch's session budget (200 calls) was already exhausted** before this pass could use it for CEO
  bios — likely consumed by other work earlier the same day. Company `/company/` sub-pages on
  stockanalysis.com (e.g. `stockanalysis.com/stocks/<ticker>/company/`) turned out to be a reliable, fast
  WebFetch-only substitute for CEO/executive-team lookups and should be the default next time, ahead of
  WebSearch.
