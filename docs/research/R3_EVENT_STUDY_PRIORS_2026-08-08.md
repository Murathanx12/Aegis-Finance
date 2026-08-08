# R3 — Published Event-Study Effect Sizes & Decay Horizons: Day-1 Bayesian Priors (deep-research receipt)

**Provenance:** produced 2026-08-08 by an autonomous Opus deep-research agent
(141 web fetches incl. local PDF extraction of publisher-blocked papers; the
agent issued two passes — this is its final compile). Every number marked
"verified" was obtained by fetching the paper/abstract; snippets-only numbers
are marked UNVERIFIED. Archived verbatim as the receipt behind
`RESEARCH_SYNTHESIS_2026-08-08_R1-R4.md`. Not a registration — priors go live
only through the registered claim-schema build (P1 task 3).

Evidence grades: **A** = published + replicated · **B** = published single study · **C** = working paper/preprint · **D** = practitioner/press.

---

## (a) Summary table

| # | Event class | Mean AR | Window | N | Period | Post-2015 status | Grade |
|---|---|---|---|---|---|---|---|
| 1a | Clinical readout, positive ("early positive outcome") | **+6.35%** (SE 0.28) | [0,+1] | 13,807 outcomes / 379 firms | 2000–2020 | Intact (sample runs to 2020) | B |
| 1a | Clinical readout, primary endpoint **met** | +0.54% (SE 0.03) | [0,+1] | same | 2000–2020 | Intact | B |
| 1b | Primary endpoint **not met** | **−2.71%** (SE 0.06) | [0,+1] | same | 2000–2020 | Intact | B |
| 1b | Lack of efficacy / safety event | −2.43% / −0.82% | [0,+1] | same | 2000–2020 | Intact | B |
| 1c | Firm-type differential: early biotech − big pharma | **+8.32pp** (day 0), **+10.95pp** ([0,+1]) | day 0 / [0,+1] | same | 2000–2020 | Intact | B |
| 1d | Large-biopharma trial news (small sample) | +0.8% / −2.0% (median, pos/neg) | [−2,0] | 24 events | 2011–2013 | — | B |
| 1e | **CRLs** | *no academic event study located* | — | — | — | Anecdotes only (−20% to −75%) | D |
| 1f | **PDUFA run-up** | *no academic study located*; practitioner claims +20–40% over 4–8 wks | — | — | — | UNVERIFIED | D |
| 2a | M&A **target** | **+14.61%** (median 12.34, 82.7% positive) | [−1,+1] | 9,298 | 1980–2005 | **Intact, if anything larger**: 20.7% (1990–2009) → **29.3%** (2010–2015) | A |
| 2b | M&A **acquirer** | +0.73% mean, **−0.05% median**, z = −2.53 | [−1,+1] | 15,987 | 1980–2005 | Public-target acquirer CAR flipped −1.08% → **+1.05%** (2010–15) | A |
| 2c | Acquirer, public vs private target | −0.87% vs **+1.76%** | [−1,+1] | 6,301 / 9,686 | 1980–2005 | Listing effect "no longer significant" (Meng-Sutton 2022) | A→B |
| 2d | Target, all-cash vs all-stock | **20.23%** vs 13.96% | [−1,+1] | 2,846 / 2,163 | 1980–2005 | Premium ≈46% stable 1980–2015 | A |
| 3 | **S&P 500 addition** | 3.4% (80s) → **7.6% (90s)** → 5.2% (00s) → **0.8% n.s. (2010s)** | [AD−1, ED+1] | 196/134/211/153 | 1980–2020 | **GONE** | A |
| 3 | **S&P 500 deletion** | −4.6% → −16.1% → −12.4% → **−0.6% n.s.** | same | 39/56/85/87 | 1980–2020 | **GONE** | A |
| 4a | Insider "opportunistic" buys | **+82 bps/month** (VW), routine ≈ 0 | monthly portfolio | — | 1986–2007 | Attenuated (general anomaly decay) | A |
| 4b | **Insider cluster buys** vs non-cluster | **3.8% vs 2.0%** (21 days); gap widens to +2.5pp at 90 days | 21d / 90d | 40% of all insider trades | 1986–2016 | Cluster *premium* grew post-SOX (faster disclosure) | C |
| 5a | PEAD hedge portfolio, net of costs | **≥14%/yr** after trading costs | 60d, quarterly | — | 1993–2002 | **DEAD**: non-existent for large stocks since **2006**, microcaps since **2016** | A→ gone |
| 5b | Post-announcement strategy returns | consistent with efficient pricing **after 2016** | intraday/jump | — | — | Gone | C |
| 5c | Management guidance revisions (firm-level CAR) | *no magnitude verified* | — | — | — | UNVERIFIED — gap | — |
| 6 | **Government contract award** (corporate–government) | **+0.54%** (significant) | [−1,0] | 1,963 | 1990–2000 | No post-2015 study located | B |
| 6 | Inter-corporate contract award (comparison) | +1.43% (contractor), +0.03% n.s. (awarder) | [−1,0] | 984 / 575 | 1990–2000 | — | B |
| 7a | **Export controls / entity list** (affected US supplier) | **−2.5%** ([−10,−1] = −0.6% n.s.) | [−10,+20] | 250 events / 156 suppliers | ~2018–2023 | This *is* the post-2015 evidence | C |
| 7b | **Tariff announcement** (US–China, 22 Mar 2018) | market mean **−2.6%**; China-exporters −1.1pp lower; slope −0.095 on China revenue share | [−1,+1] | 2,309 firms | 2018–2019 | Current | B/C |
| 7c | **CHIPS Act awards / reshoring subsidies** | *no published event study located* | — | — | — | **Evidence gap** | — |

---

## (b) Per-class detail

### 1. FDA / biotech regulatory

**Singh, Rocafort, Cai, Siah & Lo (2022), PLoS ONE 17(9):e0272851** — https://pmc.ncbi.nlm.nih.gov/articles/PMC9439234/ — Grade B (largest of its kind: 13,807 trial outcomes, 379 US-listed sponsors, 2000–2020, **Fama-French 5-factor** benchmark with constant-mean and market-model robustness). Day [0,+1]: early positive outcome **+6.35%** (SE 0.28); primary endpoints met +0.54% (SE 0.03); not met **−2.71%** (SE 0.06); lack of efficacy −2.43% (SE 0.13); safety/AE −0.82% (SE 0.12). Phase coefficients: phase 2/3 +1.95% (SE 0.16), phase 1/2 −1.11% (SE 0.14). Firm-type coefficients: early-stage biotech +6.31%, small pharma +1.69%, late-stage biotech +0.73%, big pharma −4.64% → **early biotech earns 10.95pp more than big pharma over [0,+1]**. Critically: **no drift** — "abnormal returns are not significant on the day after the event … implying that markets incorporate the information related to clinical trials."

**Hwang (2013), PLoS ONE 8(8):e71966** — https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0071966 — Grade B, tiny sample (24 events, 23 trials, 7 large biopharma firms, 2011–05/2013; market model, S&P 500, 300-day estimation window). Median CAR(−2,0): positive +0.8% (p=0.02), negative −2.0% (p=0.04); at (−2,+2) negative persists (−1.2%, p=0.04), positive does not. No significant difference by phase or biotech-vs-pharma **in this small sample** — the opposite of Singh et al., which is the sample-size story.

**CRLs — evidence gap.** No peer-reviewed event study of Complete Response Letters located. Expected: CRLs were not systematically public until FDA's 2024–25 transparency push. Available magnitudes are press anecdotes only (Grade D, single names): Corcept ≈ −50% intraday, Applied Therapeutics ≈ −75%, Replimune ≈ −20%. **Treat any CRL prior as essentially uninformed.**

**PDUFA run-up — UNVERIFIED.** Practitioner sources describe a 4–8 week run-up worth 20–40%; no academic study establishing it. Also UNVERIFIED: a Fast-Track-designation study reporting 5-day CAAR 21.59% / 30-day 38.34% / 1-yr 76.64% (abstract only, small sample).

### 2. M&A

**Betton, Eckbo & Thorburn (2008), "Corporate Takeovers," Handbook of Empirical Corporate Finance Vol. 2, ch. 15** — Tables 7–8, SDC control contests 1980–2005, value-weighted market model, windows runup [−41,−2] and announcement [−1,+1]. Verified by direct extraction:

- Target: runup **+6.80%**, announcement **+14.61%** (median 12.34%, **82.7% positive**, z=102.3, N=9,298).
- Initial bidder: runup +0.49%, announcement **+0.73% with z = −2.53**, median −0.05%, 49.4% positive, N=15,987. *Mean and z disagree in sign — the bidder distribution is left-skewed. Do not build a prior off the mean alone.*
- Public target → bidder −0.87% (z=−19.0); private target → bidder **+1.76%** (z=12.1).
- Bidder size: lowest mcap quartile **+4.04%**, highest **−0.49%**.
- Form: target 13.38% (merger) vs **18.81%** (tender offer).
- Payment: target **20.23%** all-cash vs 13.96% all-stock; combined CAR +2.85% all-cash vs **−0.30%** all-stock.
- Sub-period (Panel F): target 13.44% (1991–95) → 15.64% (1996–2000) — **no attenuation inside the sample**.
- **Offer premium: initial mean 43% / median 37% / SD 0.46; final mean 48% / median 39% / SD 0.47** (N=4,889, 1980–2002). The only directly published cross-sectional dispersion in the classics: **SD ≈ mean**.

**Andrade, Mitchell & Stafford (2001), JEP 15(2):103–120** — Grade A. Target [−1,+1] = **16.0% in every decade** (1973–79, 1980–89, 1990–98); acquirer −0.7% (n.s.); combined +1.8%*; over [−20, close]: target 23.8%, acquirer −3.8%. N=3,688. Stock deals: acquirer −1.5%* vs +0.4% n.s. non-stock; target 13.0% vs 20.1%.

**Moeller, Schlingemann & Stulz (2004 JFE; 2005 JF)** — Grade A. 12,023 deals 1980–2001: acquirer CAR(−1,+1) +1.10%; private +1.50%, public −1.02%, subsidiary +2.00%; **small acquirers +2.32% vs large +0.08%**. 1998–2001 aggregate acquirer loss **−$240bn** despite positive mean CAR; 87 large-loss deals (2.1% of deals) = 43.4% of dollars, mean CAR −10.6%.

**Malmendier, Opp & Saidi (2016), JFE 119:92–106** — verified from NBER WP w18211. Failed bids 1980–2008: announcement effect incl. 25-day run-up **+25% cash targets / +15% stock targets**; after failure cash targets stay **+15%**, stock targets revert to zero; failed stock **acquirers** −17.6%. Premium mean 46.2% (successful) / 46.6% (failed) — indistinguishable.

**Post-2015:** *Alexandridis, Antypas & Travlos (2017), JCF 45:632–650* (Grade B): 2010–2015 vs 1990–2009, target CAR **20.73% → 29.32%*** while premium is flat (45.91% → 46.44%, n.s.) — the wedge is **rising completion probability**, not a bigger premium; acquirer CAR on public targets flips −1.08%*** → **+1.05%***. *Ben-David, Bhattacharya, Huang & Jacobsen (JF 2026; NBER WP 27976)*: 28,710 acquirer CARs 1980–2018, mean +0.9%, median 0.3%, **SD 6.6%** (P10 −5.6 / P90 +8.0); completion 94.4% overall, 82% public targets. *Meng & Sutton (2022), JBF 143*: the listing effect "no longer has significant shareholder wealth implications." *Jetley & Ji (2010), FAJ 66(2)*: median day-1 merger-arb spread **6.39% (1990–95) → 4.62% (1996–01) → 1.91% (2002–07)** with completion rates flat — the arb spread collapsed, not the deal risk.

### 3. S&P 500 index inclusion — the canonical attenuation story

**Greenwood & Sammon, "The Disappearing Index Effect," Journal of Finance 80(2):657–698 (2025); NBER WP 30748** — Grade A. Window = last trading day before announcement to first trading day after implementation (avg AD→ED gap 4.8 days additions / 5.8 deletions). Verified from the NBER PDF:

> "The abnormal return … has fallen from an average of 3.4% in the 1980s and 7.6% in the 1990s to 0.8% over the past decade … A similar pattern has occurred for index deletions … only −0.6% between 2010 and 2020."

| Decade | Additions (total window) | N | Deletions | N |
|---|---|---|---|---|
| 1980s | 3.42%*** | 196 | −4.64%** | 39 |
| 1990s | **7.6%*** | 134 | **−16.1%*** | 56 |
| 2000s | 5.2%*** | 211 | −12.4%*** | 85 |
| **2010–20** | **0.8% (n.s.)** | 153 | **−0.6% (n.s.)** | 87 |

*(Published JF version: 7.4% for the 1990s, 0.3%/0.1% for the 2010s — small sample-update differences; WP numbers above were extracted directly.)* Mechanism: implied **price-impact multiplier fell ~20×** (6.75 → 0.37); >70% of modern additions are **migrations from the S&P MidCap 400** — in the 2010s direct additions still earned +5.4% while migrations earned **−1.8%**. Excluding Tesla, the 2020 average addition effect was **−3bps**.

Corroboration: *Bennett, Stulz & Wang (NBER WP 27593)* — additions [−5,+5]: **+4.7–4.9%*** (1997–2007) vs **+0.6–0.7% n.s.** (2008–2017); 12-month DGTW BHAR **−5.3%*** post-2008. *Vijh & Wang (2022, Financial Management)* — 2016–2020: migrations **−2.48%***, pure additions still **+4.16%***. *Patel & Welch (2017, RAPS)* — "Stocks no longer experience permanent shifts in investor demand." *S&P DJI (2021, Grade D)* — median additions +8.32% (1995–99) → −0.04% (2011–21). Classic baselines: Shleifer (1986 JF) ≈3%, Harris & Gurel (1986 JF) +3.13%, Chen-Noronha-Singal (2004 JF) +5.45% additions / −8.46% deletions (1989–2000). Methodology note: S&P raised the minimum unadjusted market cap $11.8bn → $13.1bn on 2021-06-03.

### 4. Insider cluster buys

**Cohen, Malloy & Pomorski (2012), Journal of Finance 67:1009–1043** — Grade A. Verified via NBER w16454: routine insider trading is predictable and uninformative; a strategy on the remaining **"opportunistic" traders yields value-weighted abnormal returns of 82 bps/month**, routine ≈ 0. (Sample period 1986–2007 UNVERIFIED — not stated on fetched pages.)

**Kang, Kim & Wang (2018), "Cluster Trading of Corporate Insiders"** — Grade C (working paper), verified by extraction. US insider data **1986–2016**. Cluster = multiple insiders, same direction, same day or consecutive days. **Over 40% of insider trades are clustered** (37% of purchases, 42% of sales; 34% of purchase dollar value). Returns: **21-day abnormal return 3.8% (cluster purchases) vs 2.0% (non-cluster)** — nearly 2×; gap **widens to 2.5pp at 90 days**. Cluster purchases have 0.26% higher transaction-date price impact. Post-SOX (2-day filing), the *second* disclosure in a cluster earns **+0.57% over 2 days and +0.52% over the next 20 days** more than a non-cluster disclosure — the cluster premium is a **disclosure-driven, post-2002 phenomenon**, unusually favourable for a live signal. Cluster **sales** are near-uninformative (blackout/vesting clustering). Cluster information is **orthogonal to CMP's routine/opportunistic split**.

**UNVERIFIED** (search snippets only): Jeng, Metrick & Zeckhauser (2003, REStat 85(2):453–471) purchases ">6%/yr", 52–68 bps/month over the first six months; Lakonishok & Lee (2001, RFS) heavy-insider-buying stocks +4.8% over 12 months.

### 5. Guidance revisions and PEAD

**PEAD, canonical magnitude:** *Battalio & Mendenhall (2006 draft; Notre Dame)* — verified: "between 1993 and 2002 an investor could have earned hedged-portfolio returns of **at least 14% per year after trading costs**." Also verified: getting the announcement *date/time* wrong changes hedge returns by **3.78%/quarter (>15%/yr)** — a methodological warning for any event pipeline.

**PEAD attenuation — Martineau (2022), Critical Finance Review 11(3–4):613–646, "Rest in Peace Post-Earnings Announcement Drift"** — Grade B, venue/pages verified; abstract partially verified: "In modern financial markets, stock prices fully reflect [earnings surprises on the announcement date]." Headline (search-snippet, **UNVERIFIED verbatim**): **PEAD non-existent for large stocks since 2006 and for microcaps since 2016**.

**Christensen, Timmermann & Veliyev (arXiv 2601.08962, Jan 2026)** — Grade C, abstract verified: earnings announcements "almost always induce jumps"; **"returns from a post-announcement trading strategy are consistent with efficient price formation after 2016."** Two independent methodologies put the death of PEAD in the mid-2000s–2016 window.

**Guidance revisions — evidence gap.** *Anilowski Cain, Feng & Skinner (2007), JAE 44(1–2):36–63* is about **aggregate** guidance and market returns; no firm-level guidance-up/down CAR magnitude verified from any fetchable source. **Do not seed a numeric prior for this class from literature.**

### 6. Government contract awards

**Elayan, Pukthuanthong & Roll (2005), "The Valuation Effect and Determinants of Corporate Contracting"** — Grade B/C (working-paper version verified by extraction; Dow Jones announcements, 1990-01-01 – 2000-12-31, market model with standardized cross-sectional test).

- **Corporate–government contractors: AAR over [−1, 0] = +0.54%, significant, N = 1,963.**
- Inter-corporate contractors +1.43% (N=984); contract-*granting* firms +0.03%, not significant (N=575).
- Their framing: "contractors gain **less** in market value from government than from corporate awards" (1.13% vs 0.54% on day −1).
- Cross-section (the part we actually need): announcement returns are **higher for larger contracts, longer-term contracts, and smaller firms** — the effect scales with *contract value relative to firm size*; also higher for firms with many competitors and riskier lines of business.

**Goldman, Rocholl & So (2010 WP)** — Grade C, verified: political connections of S&P 500 board members predict *allocation* of procurement contracts. Mechanism evidence, not an award-date CAR.

**No post-2015 government-contract event study located.** This class carries a stale-evidence penalty.

### 7. Geopolitical supply-chain events (young literature)

**Crosignani, Han, Macchiavelli & Silva, "Securing Technological Leadership? The Cost of Export Controls on Firms," FRBNY Staff Report 1096** — Grade C, verified by extraction. **250 events, 156 unique affected US suppliers** (92 Chinese entities added to BIS lists), CRSP daily, betas from [−150,−50], event window **[−10,+20]**, FF3 and FF5:

- **CAR ≈ −2.5%** (the decline happens *after* the announcement; **CAR[−10,−1] = −0.6%, n.s.**, CI [−1.5%, +0.3%]; CAR[−10,+2] = −2.7%).
- $857m average market-cap loss per affected supplier; **$130bn** total.
- Real effects: EBIT −25% of its mean; employment −6.6%; **no evidence of reshoring/friendshoring** in the medium term.

**Huang, Lin, Liu & Tang, "Trade Networks and Firm Value: Evidence from the U.S.-China Trade War"** (working-paper verified; published REStat 2023) — Grade B/C. Event: 2018-03-22 Section 301 memorandum. N=2,309 US firms, CAPM abnormal returns, [−1,+1]:

- Sample **mean CRR[−1,+1] = −2.6%** (median −2.9%); S&P 500 −2.5% on the day, −4.8% over Mar 21–23; **$911bn** lost over three days (~$395m per firm).
- Cross-section: **CAR coefficient on China revenue share = −0.095*** (a firm with 10% of revenue from China loses ~0.95pp extra); **Input_China (imports from China) = −0.96pp**; China-exporters **1.1pp lower** than non-exporters. Also transmits through supplier/customer networks.

**CHIPS Act / reshoring subsidies — evidence gap.** No published event study of individual CHIPS award announcements (awards began Sept 2024). One UNVERIFIED claim: semiconductor abnormal returns around the 2021-05-19 precursor bill, but "little evidence of a stock-market reaction" to USICA passage (2021-06-08) or CHIPS signing (2022-08-09) — which, if true, is itself the finding: **legislated subsidies are anticipated and priced well before the award date.**

### 8. Methodology — measurement noise, benchmark choice, decay

**Kothari & Warner (2007), "Econometrics of Event Studies," Handbook of Empirical Corporate Finance Vol. 1, ch. 1** — verified by extraction. The numbers needed to set within-event variance:

- **Daily return SD, all CRSP firms 1990–2002: mean 0.053.** By decile: **D1 0.014, D5 0.033, D9 0.069, D10 0.118.** Compare Brown & Warner (1985) 0.026 (NYSE/AMEX) and Campbell & Wasley (1993) 0.035 (NASDAQ) — "individual stocks have become more volatile over time."
- **Power:** 10% abnormal return concentrated in **one known day** → **N=6 detects it 100% of the time**; the same 10% spread over **six months** → **N=200 detects it only 65%** of the time. For a 1% one-day effect, decile-1 (low-vol) firms need **N=21** for 90% power; decile-10 firms need **N=60 even for a 5% effect**.
- **Benchmark choice barely matters at short horizons.** "Even if the event firm portfolio's beta risk is misestimated by 50% … the error … is small relative to the abnormal return of 1% or more typically documented in short-window event studies." Sensitivity of short-horizon specification to the return-generating model = **Low**; at horizons ≥12 months = **High**.
- **Long-horizon power is hopeless:** rejection under 50% even with 25% cumulative abnormal performance over 5 years in a sample of 200 (Jegadeesh & Karceski).
- **Event-induced variance** causes over-rejection and must be adjusted for.

**Harrington & Shrider (2007), JFQA 42(1):229–256** — abstract verified: *"cross-sectional variation in the effects of events, i.e., in true abnormal returns, **necessarily** produces event-induced variance increases, biasing popular tests for mean abnormal returns in short-horizon event studies."* Direct justification for a hierarchical-Normal with **non-degenerate τ**: heterogeneity in true θ is the norm.

**Kolari & Pynnönen (2010), RFS 23(11):3996–4025** — abstract verified: with **event-date clustering, "even relatively low cross-correlation among abnormal returns is serious in terms of over-rejecting."** Our event classes cluster hard (index rebalance dates, tariff days, PDUFA calendars, earnings season).

**Decay anchors:**
- *McLean & Pontiff*: the **published** JF 2016 version (71:5–32) reports **97 predictors, 26% out-of-sample decay, 58% post-publication decay** (**verified only via secondary sources** — Wiley 402/SSRN 403). The two working-paper versions actually fetched (2012, 2013) report **82 characteristics, ~10% OOS (n.s.) and ~35% post-publication**. Use the published figures knowing the WP numbers were smaller.
- *Chen & Velikov (2023), JFQA 58(3):968–1004* — fully verified: 204 anomalies. **Gross in-sample 68 bps/month → 44 bps net of costs → 9 bps adding post-publication → ~4 bps** adding post-2005. Post-publication decay: **~50% gross, 72% excluding pre-2005 data, 93% after trading costs.** 90th-percentile anomaly nets **6 bps/month**.
- *Chen & Zimmermann (FEDS 2021-037 / CFR)* — verified: **319 characteristics**; of the 161 clearly significant in the originals, **98% reproduce with t > 1.96**; slope 0.90, R² 0.83. Translation: **published effects are real; they just don't survive costs and crowding. Believe the sign, halve the size.**

---

## (c) Suggested day-1 priors (hierarchical-Normal)

Model per event class *c*: observed abnormal return `y_i ~ N(θ_i, σ_i²)`; true event effect `θ_i ~ N(μ_c, τ_c²)`; class mean `μ_c ~ N(m_c, s_c²)`.

**Set σ_i (measurement noise) from the firm, not the class.** Using Kothari-Warner's decile SDs and σ_window ≈ √L × daily SD:

| Firm bucket | daily SD | σ for 3-day window | σ for 21-day window |
|---|---|---|---|
| Mega/large cap (D1–D3) | 1.4–2.3% | **2.5–4.0%** | 6.5–10.5% |
| Mid cap (D5–D6) | 3.3–3.9% | **5.7–6.8%** | 15–18% |
| Small cap (D8–D9) | 5.5–6.9% | **9.5–12%** | 25–32% |
| Micro / clinical-stage biotech (D10) | 11.8% | **20%** | 54% |

These are 1990–2002 CRSP numbers; idiosyncratic vol for microcap biotech is if anything *higher* today — treat 20% as a floor for that bucket. **Do not use a single σ for a class** — a 3% CAR is a 1.2σ event for a mega-cap and a 0.15σ event for a clinical-stage biotech.

**Set τ_c (between-event heterogeneity) generously.** Anchors: BET's offer-premium **SD 0.46 against a mean of 0.43–0.48** (SD ≈ mean); Ben-David et al.'s acquirer-CAR **SD 6.6% against a mean of 0.9%** (SD ≈ 7× mean). **Default rule: τ_c = max(0.75·|m_c|, 0.5·σ_typical).** Harrington-Shrider says heterogeneity is guaranteed; τ = 0 is never defensible.

| Event class | m_c (prior mean) | s_c (SD on the mean) | τ_c (heterogeneity) | Reasoning |
|---|---|---|---|---|
| Positive clinical readout / approval, **micro-small biotech** | **+6%** | 3% | **12%** | Singh et al. +6.35% early-positive, +6.31pp early-biotech loading; τ large — outcomes range 0 to +100% |
| Positive readout, **large pharma** | **+0.5%** | 0.4% | 1.5% | Endpoints-met +0.54%; diversified pipeline damps it |
| Negative readout / endpoint miss, small biotech | **−12%** | 8% | **15%** | −2.71% pooled is dominated by large firms; scale by the ~10pp biotech-vs-pharma wedge; asymmetric-loss tail |
| **CRL, small biotech** | **−25%** | **20%** | **25%** | Grade **D only**. Prior near-uninformative by design; let the first 10 resolutions dominate |
| PDUFA run-up (pre-decision) | **0%** | 5% | 8% | No academic evidence. Do **not** encode the practitioner +20–40% claim as a mean |
| **M&A target**, [−1,+1] | **+16%** | 3% | **12%** | 14.6% (1980–2005) and 29.3% (2010–15) bracket it; 82.7% positive → left tail thin but real |
| M&A target, all-cash | **+20%** | 4% | 13% | BET 20.23% |
| **M&A acquirer**, [−1,+1] | **0.0%** | 0.5% | **6.5%** | Mean +0.73–1.1% but median ≈ 0 and z<0; Ben-David SD 6.6% used directly. **Prior mean 0 is the honest choice** |
| Acquirer, private/subsidiary target | +1.5% | 0.8% | 6.5% | Replicated 4× — but Meng-Sutton says fading; hence wide s_c |
| **S&P 500 addition** | **+0.5%** | 0.7% | **3%** | Greenwood-Sammon 0.8% n.s.; **feed migration-vs-direct as a covariate, not a wider τ** (migrations ≈ −2.5%, pure additions ≈ +4%) |
| **S&P 500 deletion** | **−0.5%** | 1.0% | 4% | −0.6% n.s.; historical −16% is a dead regime |
| **Insider cluster buy**, 1m | **+1.0%** | 0.7% | 2.5% | KKW 3.8%/21d cluster minus ~2% base ⇒ ~1.8pp edge; halved for the post-2005 Chen-Velikov haircut |
| Insider cluster buy, 3m | **+1.5%** | 1.0% | 3.5% | 2.5pp gap at 90d, halved |
| Insider cluster buy, 6m | +2.0% | 1.5% | 5% | Extrapolated beyond the paper's horizon → widen |
| **PEAD, large caps** | **0.0%** | 0.5% | 1.5% | Dead since 2006 (Martineau); 2016 (Christensen et al.). Centred on zero, tight |
| PEAD, microcaps | +0.5% | 0.8% | 2.5% | Died later (2016) → allow a little mass |
| Guidance revision (up / down) | **0% / 0%** | **4%** | **6%** | **No verified literature number.** Deliberately uninformative — first 20 resolutions should own this class |
| **Government contract award** | **+0.5%** | 0.5% | 1.5% | Elayan et al. 0.54%; **plus a slope term on (award value / market cap)** — the paper's cross-section says that is where the signal is |
| Government contract, award ≥5% of mcap | +2.0% | 1.5% | 4% | Extrapolated from the size/term cross-section → grade drops, widen |
| **Export control / entity-list hit (supplier)** | **−2.5%** | 1.2% | 4% | Crosignani et al. [−10,+20]; **the move is post-announcement — a [−1,+1] window will miss most of it** |
| **Tariff / trade-action announcement** | **−1.0%** default; **−0.095 × (China revenue share)** as a slope | 1.0% | 3% | Huang et al.; the cross-sectional slope is better identified than the mean |
| **CHIPS-style subsidy award** | **0.0%** | **3%** | **5%** | No evidence at all; the only signal is that legislated subsidies appear pre-priced |

**Global adjustment rules (apply after the table):**

1. **Grade penalty on s_c and τ_c:** ×1.0 for A, ×1.3 for B, ×1.7 for C, ×2.5 for D-or-none.
2. **Staleness penalty:** if the newest supporting sample ends before 2015, multiply s_c by 1.5 (class 6 and the classic halves of 1, 2, 4).
3. **Decay haircut — apply only to *tradable-edge* claims, not *reaction-size* claims.** Mechanical repricing (M&A target CAR, clinical-readout jump, entity-list hit) is not an arbitrage and is stable across decades. Predictive edges (insider clusters, PEAD, drift, run-ups) get **m_c × 0.5** baseline (Chen-Velikov ~50% gross post-publication decay, 72% post-2005) and **× 0.28** for a *net-of-cost* claim.
4. **Never let τ_c = 0** and never τ_c < 0.5·σ_typical for the class's firm bucket — Harrington-Shrider proves heterogeneity is mechanically present; a too-tight τ makes the resolver over-confident on the second observation.
5. **Window discipline:** priors are stated with their windows. Export controls are the cautionary case — [−10,−1] is −0.6% n.s. and the whole effect lands in [0,+20]. A grader that hard-codes [−1,+1] will score that class as "no effect."
6. **Clustered events need a correlation-robust standard error** (Kolari-Pynnönen). Index rebalances, tariff days and CHIPS batches hit many names on the same date; treating them as independent lets the posterior move far too fast.

---

## (d) Confidence notes

**Verified by direct fetch/extraction:** Singh et al. 2022; Hwang 2013; Betton-Eckbo-Thorburn 2008 Tables 6–8 (full Handbook PDF); Malmendier-Opp-Saidi (NBER w18211); Greenwood-Sammon (NBER w30748, full decade table + mechanisms); Cohen-Malloy-Pomorski abstract + 82 bps (NBER w16454); Kang-Kim-Wang 2018 (full WP); Battalio-Mendenhall 2006 (full WP); Martineau venue/pages + partial abstract; Christensen-Timmermann-Veliyev abstract; Elayan-Pukthuanthong-Roll 2005 (full WP); Goldman-Rocholl-So abstract; Crosignani et al. FRBNY SR 1096 (full); Huang-Lin-Liu-Tang (full WP); Kothari-Warner 2007 (full chapter); Harrington-Shrider abstract; Kolari-Pynnönen abstract; Chen-Velikov 2023 (full JFQA PDF); Chen-Zimmermann FEDS 2021 (full); McLean-Pontiff working-paper versions; Andrade-Mitchell-Stafford; Moeller-Schlingemann-Stulz; Alexandridis et al. 2017; Ben-David et al.; Meng-Sutton 2022; Jetley-Ji 2010; Bennett-Stulz-Wang; Vijh-Wang; Patel-Welch abstract.

**UNVERIFIED (no primary source fetched):** McLean-Pontiff published figures (97 / 26% / 58%); Martineau's specific years (2006/2016); CMP sample period; Jeng-Metrick-Zeckhauser; Lakonishok-Lee; FDA Fast Track CAARs; all PDUFA run-up magnitudes; all CRL magnitudes (press anecdotes); Barrot-Sauvagnat / Carvalho et al. magnitudes; the 2021-05-19 semiconductor claim; firm-level management-guidance CARs (none found at all).

**Genuine literature gaps (useful in themselves):** (i) no peer-reviewed CRL event study — the class starts from ignorance and should be the highest-learning-rate class in the ledger; (ii) no published PDUFA run-up study; (iii) no post-2015 government-contract event study; (iv) no CHIPS-award event study; (v) no M&A target decade table past 2018; (vi) cross-sectional SDs of CARs are almost never published — most τ values above are reasoned, not measured: the weakest part of this prior set.

**Two structural cautions for the grading system.** First, Kothari-Warner's power asymmetry: a 10% effect on a single known day needs **6** events; the same effect smeared over six months needs **200** for 65% power. Classes with precise timestamps (FDA decisions, tariffs, index effective dates) resolve an order of magnitude faster than fuzzy-timing classes (guidance, reshoring, contract pipelines) — do not interpret a slow-moving posterior in a fuzzy class as evidence of no effect. Second, **distinguish reaction-size claims from tradable-edge claims in the schema itself**: the former are stable across four decades, the latter have decayed 50–93%; a single "effect size" field that conflates them will systematically mis-set every prior in the table.
