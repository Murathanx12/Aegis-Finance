# GATE M — RESEARCH VERDICTS (G1–G4)
**Date:** 2026-08-04 · **Inputs:** Consensus.app synthesis + Gemini deep-research answers to `docs/RESEARCH_PROMPTS_GATE_M.md`
**Companion:** `docs/GATE_M1_FACTORY_CALIBRATION_DESIGN.md` (the O1 deliverable)
**Rule applied:** nothing enters the paper unchecked. Every claim below carries a status: **VERIFIED** (I confirmed it this session or the repo already certified it), **CREDIBLE** (real anchor, claim plausible, not independently confirmed), **UNVERIFIED** (asserted by one or both AI sources with no citable support found), **REJECTED**.

---

## 0. THE HEADLINE FINDINGS

Three things in these two documents actually change what we do:

1. **E1 (empirical σ_SR) would LOOSEN our gate, not tighten it.** `adoption.py:25` currently defaults `sr_variance = 0.01`. The dossier's empirical cross-candidate σ_SR ≈ 0.075 monthly implies variance ≈ **0.0056 — below the default**. Since `E[max SR] ∝ √V`, substituting the empirical value *lowers* the deflation bar. Gemini independently identifies the mechanism (left-truncation: candidates killed at early gates never produce a Sharpe, so the observed dispersion is measured on a truncated sample and understates the true spread). **Decision: E1 adopts `sr_variance = max(empirical, 0.01)` and reports both. E1 may never lower the hurdle.** Without this, "we finally measured σ_SR" would have quietly made three survivors easier to pass.
2. **The M2 permutation spec structurally retires the §29–31 pooling controversy.** Under a permutation gate the read is `p = (1 + #{stat_perm ≥ stat_real}) / (B+1)` — there is no pooling step, so the F1 pooling error cannot recur and "seed-level vs pooled" ceases to be a choice an analyst can make after seeing results. That is a bigger win than the false-kill fix that motivated it.
3. **Board centrality has a 13-year clean out-of-sample window and no known replication.** Larcker-So-Wang (2013) is VERIFIED; every claim either source made about its post-2013 decay is UNVERIFIED. That makes BOARDEX-CENTRALITY a genuine post-publication OOS test (McLean-Pontiff design) where *both* outcomes are publishable — a better trial than "another centrality factor."

---

## 1. G1 — FACTORY CALIBRATION (feeds M1)

### What both sources agree on (adopted)
| Claim | Status | Consequence |
|---|---|---|
| Preserve **cross-sectional dependence** above all — it is the realism failure that most distorts FDR/false-kill, because the gates are cross-candidate | VERIFIED as a principle (Harvey-Liu 2020/2021; Li-Ji 2005 on Meff under dependence) | DGP must reproduce the real within-month correlation structure, not just marginals |
| Fat tails / vol clustering matter second; mild autocorrelation error matters least | CREDIBLE | Vol-clustering fidelity is a *reported gap*, not a build blocker (see design §2.4) |
| Stationary bootstrap (Politis-Romano 1994) is the right baseline for weak time dependence | VERIFIED (real, canonical) | Used for the calendar draw |
| Injection must vary along persistence / breadth / factor-alignment / capacity axes; constant-diffuse-orthogonal-large-cap is "easy mode" that lets a broken pipeline look calibrated | CREDIBLE (Consensus labels its own version SPECULATION; Gemini asserts it; the logic is sound and cheap to honour) | Four injection designs, and I1-constant is explicitly **not** the headline number |
| Posterior = likelihood of the evidence vector under each α, times a **sparse prior heavily weighted to zero** — not the raw pass rate | VERIFIED as method (Talts et al. 2018 SBC is real; Harvey-Liu 2020 is real) | Posterior map ships with a pre-registered prior + two sensitivity priors |
| 1,000 reps → binomial SE 1.58pp at p≈0.5 → ±3.1pp at 95% | VERIFIED (arithmetic; both derive it identically) | Adequate for ranking designs, not for 47% vs 50% |
| Common random numbers across α levels | CREDIBLE (Consensus flags it as carryover, Gemini asserts it; standard simulation practice) | Adopted — same null panel per rep across all α, so the false-kill-vs-α *curve* is paired |

### Where they disagree, and the call
- **Generative models (GANs/VAEs) as a panel source.** Gemini promotes them; Consensus rates them "supplementary benchmark, easy to overtrust." **Rejected for M1.** A GAN panel would need its own calibration certificate before it could certify anything else — that is a gate inside a gate.
- **Precedent for "evaluating the evaluator."** Consensus offers Talts (SBC), Lei-Sudijono (semisynthetic placebo injection for synthetic controls), Harvey-Liu, AlphaEval. Gemini offers OpenSTEF/BEAM (energy forecasting) and "DeFi actuarial Monte Carlo validation frameworks" — **UNVERIFIED and, on the face of it, not analogous**; do not cite them. The honest paper claim: *we found no published finance system that injects known alpha through an unchanged discovery pipeline to measure its own false-kill rate.* The nearest verified analogue is Lei & Sudijono's semisynthetic treatment-effect injection in synthetic-control inference.

### Rejected outright
- Any DGP that reuses real firm return histories column-consistently. A relabelled real panel still contains real momentum/quality structure, so it is not a null. See design §2.2 for why the obvious "block bootstrap + shuffle tickers" construction leaks alpha inside blocks.

---

## 2. G2 — DEPENDENCE-AWARE MULTIPLE TESTING AT N=179 (feeds M3)

### Decisions
| Question | Tool | Status |
|---|---|---|
| Did *anything* in the 179 beat the benchmark? | **Hansen SPA** (2005), studentized, stationary-block bootstrap | VERIFIED anchor (Hansen 2005 JBES; Hsu-Hsu-Kuan 2010 step-SPA) |
| Which of the 4 survivors survive jointly? | **Romano-Wolf stepdown** | VERIFIED anchor (List-Shaikh-Xu 2019; Harvey-Liu 2020) |
| How conservative is raw N=179? | Eigenvalue **N_eff**, reported, never gating | Already our rule — `discipline/overfitting.py:118` docstring pre-commits it |
| Model Confidence Set | **Dropped from M3** | Consensus cannot verify it from its corpus; Gemini describes it correctly but it answers a model-selection question we are not asking. Removing it is a scope reduction, not a gap. |

**Implementation call:** Gemini's named packages (`PyFixest`, `wildrwolf`, Stata `rwolf2`) are built for *regression coefficients* with cluster bootstraps. Our object is a T×N matrix of monthly candidate excess returns. Bending PyFixest to that shape costs more than writing the stepdown directly over the matrix (~40 lines, stationary-block resampling of rows). **Write it in `aegis_brain/discipline/`, test it against a known-answer simulation.** Same for SPA.

**The 179-minus-return-series problem.** Both sources converge on dual accounting, and it matches what our code already enforces:
- DSR deflation keeps **raw N = 179** (search intensity; the conservative direction, unchanged).
- RW/SPA run only on the subset with full monthly series; **M3 must state that subset's size explicitly** — a Romano-Wolf result over ~40 series is not a statement about 179 trials, and the paper must not let it read as one.
- N_eff is computed on that same subset and reported alongside, never used to loosen.

**σ_SR bias — the two sources disagree on the sign and Gemini is right for our ledger.** Consensus argues selection *inflates* dispersion (interesting candidates are kept alive longer). Gemini argues early kills *truncate from below* and compress it. For our pipeline the killed arms die before producing a Sharpe at all, and they die because they looked bad — so the observed sample is truncated on the left and σ̂_SR understates. That is the dangerous direction (a smaller σ_SR means a lower `E[max SR]` bar). Hence §0 finding 1.

**HSZ 2026 (NBER w34898):** Consensus reports it as unverifiable — correctly, it is outside their corpus. **Our repo already verified it** (`AI_REVIEWS_SYNTHESIS_2026-08-03.md` §7.1): real, February 2026, lower-bound framework, reaffirms t ≥ 3.0. Both sources agree on the substantive point regardless: **a complete private ledger does not buy a lower hurdle**, because the ideas themselves were drawn from a contaminated shared literature. No change to the t≥3-class bar.

---

## 3. G3 — PERMUTATION PLACEBO SPEC (this is M2's pre-registration content)

The spec below is what M2 should register verbatim. Every line is a decision, not a menu.

| Element | Registered value | Basis |
|---|---|---|
| Permutation unit | Each **real event date** is reassigned to a **different firm**; the calendar marginal is preserved exactly | Both sources; our own F2; fixes cohort drag by construction |
| Per-firm event count | **Preserved** (a firm with 4 events gets 4 permuted events) | Both sources — otherwise treatment intensity changes |
| Stratification | Permute **within size-quintile × sector** cells | Gemini asserts; Consensus labels it speculation grounded in Athey-Imbens (2016) stratified randomization. Adopted because it can only make the placebo a *fairer* comparison — it removes both a false-positive channel (placebo firms less volatile than event firms) and a false-kill channel |
| B (permutations) | **5,000** | Sources conflict: Gemini says B=499 minimum, Consensus says 5,000–10,000. 499 is the minimum for a *valid* exact test; it is not a *stable* one. MC SE of p≈0.05 is 0.69pp at B=999 vs 0.31pp at B=5,000. This is a kill criterion at a boundary — buy the precision |
| Direction | **One-sided**, direction fixed in the registration | Both sources; we have directional hypotheses |
| The read | `p = (1 + #{stat_perm ≥ stat_real}) / (B + 1)` — **no pooling step, no per-seed reads** | This is the upgrade that retires §29–31 (see §0 finding 2) |
| Anti-forking protocol | Statistic, direction, B, seed, stratification keys, and the pooling-free read all hashed into `TRIALS/` **before** the run; the run writes the full permutation distribution to disk for audit | Both sources; matches our `pre-register-trial` skill |
| Operating characteristics | Measured by M1 Stage 5 (inject a known event-day effect, sweep effect size, measure the gate's kill rate) | G3 Q4 → reuses the M1 machinery wholesale |

**One correction to carry forward.** Consensus cites Nguyen & Wolf for "permutation tests do not suffer meaningful power loss at 5%." I verified the paper (*Empirical Economics*, published 2024; UZH WP 425, 2023) — but it is about **single-firm event studies with very few event instances**. Its power result does not transfer to our large multi-firm cohort design. **Cite it for the permutation-inference framing only, never for a power claim about our gate.** Our own Stage-5 measurement is the power evidence.

---

## 4. G4 — SOCIAL-ALPHA AUDIT (feeds T1, T2, T5, and the BoardEx program)

Verified this session where marked. **Gemini's G4 answer contains two misattributions and several invented effect sizes** — flagged inline so they do not propagate into trial designs.

### 4.1 Connected-director insider clusters (T1)
- **VERIFIED anchors:** Cohen-Frazzini-Malloy (2008, JPE) — board connections and *mutual fund* returns, not director trading. Cohen-Frazzini-Malloy (2010, JF) *Sell-Side School Ties* — effect materially weakened post-Reg FD in the US, persisted in the UK. Cohen-Malloy-Pomorski (2012, JF) *Decoding Inside Information* — routine trades ≈ no predictive power; opportunistic trades carry it.
- **REJECTED attribution:** Gemini cites "Cziraki, Lyandres & Michaely (2021)" for insider *networks*. That paper is about insider trading around **repurchases and SEOs**, not networks. The network-insider anchor is Goergen-Renneboog (UK), already in our §7b.
- **Design consequence:** the *routine-vs-opportunistic filter* is the part with the strong replication record; the *network overlay* is the novel, weakly-evidenced part. Build T1 so opportunistic-only is the **baseline arm** and the network overlay is the incremental claim. Then T1 has an informative null even if the network adds nothing.
- **Skeptic's kill / cheapest control:** microcap-liquidity provision → run in `largemid` (top-1000 dollar volume) only; and Form 4 **filing timestamp**, never trade date.
- Carried from §7b: centrality may proxy for individual skill → within-director comparison + director fixed effects (the 17.2M role-history master supports it).

### 4.2 Independent-director departures (T2)
- **VERIFIED anchor (checked this session):** Fahlenbrach, Low & Stulz, *Do Independent Director Departures Predict Future Bad Events?*, **RFS 30(7), 2017, 2313–2358**. Surprise departures → worse stock and operating performance, more restatements, shareholder litigation, extreme negative return events, worse M&A; identification uses director **deaths** as exogenous variation; announcement returns to surprise departures are negative.
- **REJECTED attribution:** Gemini names "Agrawal & Chen (2017)" as the anchor. That is a different paper (boardroom disputes). FLS 2017 is the anchor.
- **UNVERIFIED numbers:** Gemini's "+20–32% restatement probability, +29–35% class-action probability" — do not quote until read out of FLS's own tables.
- **Design consequence:** take FLS's operational definition of "surprise" before inventing our own survival-model version (§7b). Use theirs as the pre-registered primary and ours as a secondary.
- **Skeptic's kill / control:** it is a lagging momentum indicator → neutralize trailing 12-1 momentum.

### 4.3 Board network centrality (BOARDEX-CENTRALITY)
- **VERIFIED (checked this session):** Larcker, So & Wang, *Boardroom Centrality and Firm Performance*, **JAE 55(2–3), 2013, 225–250**: long most-central / short least-central earns ~**4.68%/yr** risk-adjusted; central-board firms show higher future ROA growth; analysts underreact; effects concentrated in high-growth-opportunity firms and firms facing adverse circumstances.
- **UNVERIFIED:** *every* claim either source made about post-2013 decay or small-cap concentration. I searched and found no replication or OOS study.
- **Design consequence — this is an upgrade.** We hold a clean 13-year post-publication window (2013–2026) and certified BoardEx. Pre-register the trial as an explicit **post-publication out-of-sample test of a published premium** (McLean-Pontiff design), where "the premium decayed" and "the premium held" are both publishable results. That is a stronger paper contribution than another centrality factor.
- **Skeptic's kill / control:** size. Continuous size-decile profile (10 bins) + value-weighted portfolios (the Hou-Xue-Zhang lesson from §2.6), not a large-vs-small split.

### 4.4 Institutional vs retail attention divergence (T5 / T4)
- **VERIFIED anchor:** Ben-Rephael, Da & Israelsen (2017, RFS) — institutional attention (Bloomberg-based AIA) leads; retail search attention (SVI) follows.
- **The pitfall that matters to us most, both sources flag it:** Google Trends SVI is **re-normalized over time and repaints**. Any backtest ingesting today's SVI history absorbs look-ahead.
- **Action item (audit, not a trial):** determine whether our Trends collector archives **raw snapshots with capture timestamps**. If it does not, the attention side of T4/T5 is not PIT and the trials must be re-scoped or the collector fixed first. This is a Gate-D-class data question that Gate D did not cover.
- **Skeptic's kill / control:** 1-month short-term reversal, then momentum.

### 4.5 Political alignment
- **VERIFIED anchor:** Cooper, Gulen & Ovtchinnikov (2010, JF) — corporate political contributions and stock returns (PAC).
- **CREDIBLE / UNVERIFIED split:** "PAC gives multi-year slow drift while government contract awards price instantly" is a plausible Gemini assertion with no citation — do not state it as fact.
- **Data:** FEC, LDA filings, USAspending are all free and legal for a retail researcher — confirms the design already in the roadmap (§59: measure political closeness directly).
- **Skeptic's kill / control:** sector beta (defense/health/energy concentration) → sector-neutral construction.

### 4.6 The haircut that applies to all five
McLean-Pontiff (2016, JF): −26% out-of-sample, −58% post-publication. Already our §2.6 rule; it is the prior that goes into the M1 posterior map (design §4.3).

---

## 5. WHAT THE TWO SOURCES GOT WRONG (so nobody re-imports it)

- **Gemini:** misattributed the director-departure anchor (Agrawal-Chen for FLS 2017) and the insider-network anchor (Cziraki et al.); invented effect sizes for director departures; offered OpenSTEF/BEAM and "DeFi actuarial validation" as evaluator-evaluation precedent (not analogous, unverified); asserted board-centrality decay with no source; B=499 permutations is a floor quoted as a recommendation.
- **Consensus:** reference list conflates Cohen-Frazzini-Malloy 2008 with the 2010 *Sell-Side School Ties* DOI; cited Nguyen-Wolf's small-N single-firm power result as though it covered our cohort design; several 2026 arXiv items (Alswaidan HMM, Huh MarketGANs) are low-value for our purpose and should not be cited; correctly flagged HSZ as unverifiable from its corpus, but our repo had already certified it.
- **Both:** treated "1,000 reps → ±3.1pp" as settled (it is, and they derive it identically) but neither costed the compute for the grid that would need. See design §3.4 — this is the binding constraint, not statistics.

---

## 6. ADDENDUM (same day) — Trends PIT audit: NOT PIT, and not retroactively fixable

The open question from §above ("does our Trends collector archive raw
snapshots with capture timestamps?") — audited 2026-08-04, answer is **no on
every count**:

- `backend/services/trends_sentiment.py` fetches live via pytrends into the
  in-memory TTL cache. **No parquet, no SQLite, no `observed_at`, no archival
  of any kind.** There is no trends code in the Aegis module repo at all
  (grepped: zero hits for pytrends/SVI).
- Worse: the service itself documents that **pytrends fails ~always from
  Railway** (datacenter-IP block, 6h cooldown, signal disclosed as
  unavailable). So nothing is accruing forward either — prod has effectively
  never had this signal.
- Google renormalizes SVI within every requested window and repaints history;
  a later re-query is not what an observer would have seen at the time.
  **Backtesting on re-queried SVI is a look-ahead by construction.**

What IS archived PIT: the market-level fragility composite (which includes a
GDELT crash-narrative z-score) goes through `pit_score_collector` with UTC
`observed_at`, weekly. Per-ticker attention counts are not archived anywhere.

**Consequences for the trials (re-scope before their clocks start):**

1. **T4 (attention-acceleration exit)** — drop the Trends leg. Rebase the
   attention series on GDELT DOC-API per-ticker article counts: article
   timestamps are fixed history, so past counts are approximately
   reconstructable — *approximately* is a claim to test, not assume. Register
   a **stability canary** first: query identical historical windows twice,
   ≥2 weeks apart; material drift → GDELT counts are also out and T4 needs
   its own forward accrual period.
2. **T5 (institutional-attention mismatch)** — same re-basing for the retail
   -attention leg, same canary dependency. The 13F institutional leg is
   unaffected.
3. **If Trends is ever wanted forward**: new PIT collector storing raw SVI
   snapshots + capture timestamp per query window (and it cannot run from
   Railway — needs a residential-IP path or it stays dead). Minimum ~6-12
   months of accrual before any trial reads it. Not a current-quarter task.
