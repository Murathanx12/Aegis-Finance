# AI REVIEWS — SYNTHESIS, VERDICTS, AND THE REBUILT ROADMAP
**Date:** 2026-08-03 · **Companion to:** `AEGIS_FINANCE_DOSSIER_2026-08-02.md` and `AEGIS_TOMORROW.md`
**What this is:** Five external AI reviews of the dossier were collected, extracted, and independently verified by Claude (this session). This document records what each review is, which of their claims survived verification, where they agree (the strong signal), where they disagree, and the roadmap rebuilt from the merger of their advice with our own backlog.

---

## 0. THE REVIEW SET

| # | File | What it actually is | Read the dossier? |
|---|---|---|---|
| R1 | `DEEPSEEK AND CHAT GPT.txt` (part 1) | **DeepSeek** full consultant report | Yes — numbers correct throughout |
| R2 | `DEEPSEEK AND CHAT GPT.txt` (part 2) | **GPT** 6-report referee series (exec summary → statistical audit → placebo audit → leakage audit → survivor audit → thesis audit) | Yes — best-calibrated of the set |
| R3 | `Does_deflated_Sharpe_calculation_correctly_adjust_.pdf` | **Consensus.app** Q&A on DSR at N=179 (3 pp) | No (question-scoped) |
| R4 | `httpsgithubcomMurathanx12Aegis-Finance_You_.pdf` = pp.1–7 of the bracket-name PDF (duplicate) | **Consensus.app** "Independent Audit" (7 pp) | Yes |
| R5 | bracket-name PDF pp.8–10 | Tail of a **Perplexity**-style review (its first pages are missing) | Yes |
| R6 | `Aegis Finance Quant Research Audit.pdf` (13 pp) | **Gemini**-style deep-research audit (Turkish bibliography header) | Yes — most specific numbers, weakest citations |
| — | `...consultant....csv` | Consensus.app **bibliography export** — 50 papers, zero prose | n/a |

**Overall quality:** far better than typical AI output. Every dossier-reading review engaged with real project numbers (Z(179)=2.729, 18-vs-179 registry, §28 short-leg shares, seed-level −4.06 vs pooled −3.17, 55-day lanes, "Curr" sentinel). Nobody found a flaw in the core arithmetic. Two reviews independently re-derived Z(179) and confirmed it.

---

## 1. CLAIMS I VERIFIED MYSELF (Claude, this session — not relayed)

**Confirmed, new defect (C7):** `engine/autoresearch/aegis_prepare.py:118` calls `PurgedKFold(..., horizon_days=h_days)` — the class has no such parameter, so this raises `TypeError`: the autoresearch prepare path **has never run** with this signature. Worse, line 121 calls `cv.split(X_valid)` with no `eval_times`, which per `purged_cv.py:73` silently **falls back to plain k-fold — no purging**. DeepSeek's claim ("eval_times=None degrades to plain k-fold") is TRUE and understated. Fix: make `eval_times=None` raise, repair the call site. (The crash model's `walk_forward.py` path is separate and unaffected.)

**Confirmed:** the silent k-fold fallback is documented in the docstring itself — a described-not-enforced safeguard, exactly the failure class R2 and R4 both flagged as the project's recurring pattern.

**Refuted (detail):** GPT's "Almgren-Chriss implemented but never imported" — there is no Almgren-Chriss module in the repo; only a comment naming the square-root model in `backend/services/backtest.py:49`. Garbled relay of a dossier line.

**Refuted as stated:** DeepSeek's "features computed from pre-explore-window data are look-ahead." Pre-sample data is *past* data — not a leak. The adjacent **real** risk it gestures at: any object fitted on the full sample (scalers, z-score parameters, feature selection) that lets confirm-period statistics touch explore-period features. → Audit item in the roadmap (Phase 0).

**Unverifiable, treat as invented detail:** DeepSeek's "the confirm window has been read ≥6 times." No counter exists (that's the defect); the specific number is made up. The *fix* (confirm-read counter with hard budget) is right regardless.

**Arithmetic spot-checks passed:** GPT's Z(179) re-derivation (σ_SR≈0.075 monthly at T=180 → E[max]≈0.20 monthly ≈0.69–0.71 annualized); R4's t = 0.71·√15 = 2.75; the Kelly table (full 2.34×, half 1.17×, 75% of growth) matches dossier Part IX; R6's N-tier table (18→0.48, 179→0.71, 500→0.79 expected max null Sharpe) is consistent with the formula it quotes.

**The R6 pooling attack is the already-litigated E1 error:** it calls the placebo pooling "fatally misspecified pseudoreplication" and in the next paragraph quotes the seed-level t of **−4.06 — more extreme than the pooled −3.17 it attacks**. Our standing resolution (pooling was misspecified AND unregistered, but seeds agree, gate does not flip, 13D stays closed) survives contact with all five reviews. R1, R2, R4 all independently land on our resolution.

**Citation hygiene warning:** R6 has ≥4 bibliography entries that are unrelated filler (an in-utero-health paper cited for Romano-Wolf; a rural-China parenting paper; a generative-AI productivity paper cited for DoubleML), and Scherbina (2008) is footnoted to the wrong paper. The Consensus documents carry five 2026-dated citations that must be verified before any appears in our paper: Harvey-Sancetta-Zhao (NBER w34898), Benhenda Look-Ahead-Bench (arXiv 2601.13770, repo `github.com/benstaf/lookaheadbench`), Li-Wang-Ma FinCAD (arXiv 2605.24564, garbled author list), Fonseca (*Mathematics* 14(12) — issue may not exist), Pham et al. AlgoXpert (SSRN 6303279), plus LdP-Lipton-Zoonekynd "Sharpe Ratio Inference" (JPM 2026). **None of these goes into the paper unchecked.** (Gemini deep-research task #1, below.)

---

## 2. WHERE THE REVIEWS AGREE (independent agreement = the strongest signal we have)

1. **Enforce N=179 in the machine and deflate survivors at true N.** Unanimous, and identical to our E1/E2/E3. R2 adds the sharpest framing: *the production registry is post-selection; the search space is the statistical unit.*
2. **Dependence among the 179 is the open statistical question.** The trials cluster in families → effective N ≠ 179 (could cut either way: fewer effective trials, but harder-to-estimate inflation). Remedies named by ≥3 reviews: empirical σ_SR (our E1), correlation clustering for effective N, **Romano-Wolf stepdown**, **Hansen's SPA**, Model Confidence Set.
3. **The placebo gate needs its own validation.** The false-kill rate has never been measured. R2's proposal is the best single new idea in the whole set — see §3.1. R1 and R6 independently propose the same replacement design: **permutation placebo that preserves the calendar marginal** (shuffle real event dates across permnos), which is our own F2 recommendation. R4 reframes the null: test "treatment ≤ placebo," not "placebo = 0."
4. **BoardEx is the #1 new direction.** Unanimous — DeepSeek's "one thing I'd bet on," GPT's research-budget rank #1, R4's idea #1, R6's Phase-1 item 1. All warn about the same trap we found ourselves: role start/end dates only, never the `"Curr"` sentinel. (The full uncapped pull is landing today — 5,018,507-edge network, 17.2M director-role master.)
5. **Regime switching: sizing yes, switching no.** Unanimous, matches our §15/§18/§21 history. Filtered probabilities only; expected benefit is left-tail truncation (~+0.08–0.11 Sharpe at best), not return enhancement.
6. **Apply published decay haircuts to survivor priors.** McLean-Pontiff: −26% out-of-sample, −58% post-publication; Falck-Rej-Thesmar: decay grows 5pp/yr; Jacobs-Müller: the US is where decay is worst; Hou-Xue-Zhang: 65% of 452 anomalies fail t=1.96 under NYSE breakpoints + value weighting.
7. **LLM signals: extraction-only + anti-memorization testing.** Our CANON §3 is repeatedly endorsed verbatim. New additions: strip entity names before the LLM sees text (Glasserman-Lin: anonymization *improved* long-short returns 4.4–5.9 bp/day — the distraction effect exceeds look-ahead), and run a "honesty-drop" test (memorized-date returns should collapse under anti-memorization decoding while true OOS holds).
8. **Congress copy-trading is dead; the alive designs are different.** Belmont et al. 2022: post-STOCK-Act congressional returns ≈ random picking. What survives scrutiny: **disclosure-following** (Lazzaretto 2024 — returns follow the *filing timestamp*, >100bp/mo), **firm-level political connectivity** (Cooper-Gulen-Ovtchinnikov; FEC data free), and **politically connected insiders** (Jagolinzer et al. 2020).
9. **Long-only reality check on every attention/neglect idea.** Chen-He-Tao-Yu 2022: low-coverage five-factor alpha 0.97%/mo vs 0.24%/mo high-coverage — but concentrated in the short leg, echoing our §28. Every new idea carries a borrow-fee/short-eligibility screen (Drechsler & Drechsler) and long-only sleeve testing as a design requirement, not an afterthought.

## 2b. WHERE THEY DISAGREE (flagged, not silently resolved)

- **TSMOM-XA:** GPT calls it "the survivor I trust most" (60% genuine — strongest replication record); R4/R6 call it "the weakest survivor" (Huang-Li-Wang-Zhou 2020, JFE: pooled TSM evidence ≈ a historical-mean strategy). Both prescribe the *same tests*, so the disagreement is resolvable: leave-one-asset-out (if removing SPY kills it, it's equity momentum in a costume) and comparison against a vol-targeted historical-mean baseline.
- **The t≥3 hurdle:** DeepSeek surfaces Chen (2025) "most claimed findings are likely true" (FDR ≤9%; t=1.79 can give FDR 1%) against Harvey-Liu-Zhu's t>3. Our t≥3-class bar is *the strictest position in an active dispute* — relevant to Murat's "can we lower confidence" question. The defensible synthesis: keep a high bar for *discovery claims*, but let **posterior-mean sizing** (not binary accept/reject) govern capital — which is already our stated policy.
- **gp-small:** GPT gives 90% "not merely noise" (across four worlds: interaction/liquidity/implementation/mined); R4 makes it conditional on the short-leg/microcap/lineage cleanup. Both prescribe the same tests: continuous size-decile profile (10 bins, not large-vs-small) and a direct GP×Size interaction regression.

---

## 3. THE BEST NEW IDEAS (ranked by my synthesis)

### 3.1 Factory Calibration Monte Carlo (GPT) — the missing experiment
Generate synthetic panels with **known injected alpha ∈ {0, 0.2, 0.4, 0.6, 0.8}**, run the *entire unchanged* Strategy Factory — explore/confirm, placebo gates, DSR — thousands of times. Read off: false-discovery rate at alpha=0, **false-kill rate** at each real alpha, the Sharpe needed to survive 179-way selection, whether explore/confirm is too strict, whether the DSR threshold achieves its intended FDR. This answers GPT's "most important open question": *is the research factory itself calibrated?* (Run it again on a different period/universe: do we get ~3 survivors, 0, or 20?) No analytical refinement of DSR can substitute. **This becomes the paper's centerpiece exhibit alongside the survival curve.**

### 3.2 The BoardEx program (everyone)
With the full pull: (a) **centrality signal** — eigenvector/degree centrality long-short, controls size/BM/momentum/illiquidity, placebo = shuffled edges within rebalance date; (b) **insider network clusters** — connected directors across different firms buying within a window (Goergen-Renneboog: connected directors trade less often but more profitably; needs Form 4 × network); (c) GPT's frontier version — **information diffusion graphs**: earnings surprise at firm A → measure lag structure of repricing at suppliers/customers/board-connected firms; the prediction target is *where information travels next*, structurally harder to arbitrage than a static factor. GPT's strategic reframe is worth adopting as language for the paper: evolve from a *factor platform* to an *information-propagation platform* — it is literally Murat's thesis, formalized.

### 3.3 Neglect × Quality, long-only sleeves (DeepSeek + R4 + our D4)
Signal = GP × **ChNAnalyst** (coverage *decline*, per OSAP; coverage *level* is a documented placebo). Long-only top-50, borrow-fee eligibility screen, buy/hold spread bands (enter ≤40th rank, exit >80th — Novy-Marx-Velikov turnover halving, DeepSeek's "single highest-ROI implementation detail"). Anchoring effect sizes from Chen et al. 2022. Must first check OSAP for the interaction itself.

### 3.4 Attention velocity → future volatility, not return (GPT)
The defensible version of the NVDA/TSLA thesis: attention *acceleration* predicts future variance/skew/IV — not reversal timing (NVDA 2016 stayed expensive for a decade; our own §1 killed peak detection: 28.6% sell-signal hit rate). Data: Google Trends, GDELT, news counts we already collect. Null: acceleration adds nothing beyond momentum.

### 3.5 Disclosure-following politician design (R4)
PIT key = STOCK Act **filing timestamp**, never trade date; placebo = matched non-political disclosures; capacity low-moderate. Replaces the dead copy-congress idea.

### 3.6 Methodology upgrades to adopt
- **SPA + Romano-Wolf jointly across survivors** (dependence-aware, replaces naive per-survivor t-tests).
- **CPCV/CSCV for future gating** (Arian et al. 2024: walk-forward is measurably weaker at false-discovery prevention).
- **Hypothesis genealogy** (GPT): every candidate records parent idea, inspiration, reused features — makes future dependence adjustment possible and prices in "researcher leakage" (post-100-failures, new ideas are not independent draws).
- **Placebo battery** (GPT): random-ticker, future-event (+180d), lag (+90d), sector-matched, propensity-matched — a real signal should survive multiple orthogonal placebo families.
- **Entropy/coverage canaries with auto-halt** (GPT): every feature publishes coverage, missing-rate, distinct-count, entropy daily; entropy collapse halts production. This is the general fix for the constant-zeros class.
- **As-of manifests + PIT replay engine** (R4/GPT): every merged dataset carries observation/publication/effective dates as first-class columns; a replay engine reconstructs the information set at any past timestamp and asks "could this signal have been computed then?"
- **Survivor renaming** (GPT): "survivor" → *prospective research asset*. Selection earned them research budget, not belief.

### Explicitly rejected (unanimous or already-refuted)
More candidate screening beyond the two pre-registered new families · HMM strategy-switching · peak detectors · copy-congress · copy-13F ("most famous holdings are arbitraged within hours"; study *disagreement* → future vol instead) · the options cross-sectional family (borrow-fee artifact) · ethnic/demographic screens (bad measurement, unacceptable exposure — dossier IX.4 stands).

---

## 4. THE REBUILT ROADMAP (90 days, 2026-08 → 2026-10)

*Merges the C/D/E lists from `AEGIS_TOMORROW.md` with the review consensus. Every item carries a kill criterion where applicable. Attended items marked ⚑ need Murat.*

### Phase 0 — Freeze & count (Week 1, ~Aug 4–10)
| # | Action | Kill criterion / note |
|---|---|---|
| 0.1 | Commit C1 (`factor_ic.py` degenerate-refusal + tests) — done, uncommitted | — |
| 0.2 | **E2**: machine-readable 179 ledger — one append-only row per candidate arm, back-filled from NEGATIVE_RESULTS; registry gate binds to it | If back-fill impossible for some arms, count them anyway with `evidence=prose` |
| 0.3 | **E1**: empirical σ_SR of the 179 candidate Sharpes (one line once 0.2 exists) | Decides every survivor's deflation hurdle |
| 0.4 | **E3**: `evaluate_candidate` on gp-small/fusion/TSMOM-XA at N=179 **and** by family cluster (effective N via correlation clustering) | Survivors failing at effective-N: demote to "unfunded hypothesis" |
| 0.5 | **C4**: FRED `publication_lag_days` map; drop RECPROUSM156N; re-run walk-forward | The AUC/Brier delta is a paper exhibit either way |
| 0.6 | **C7** (new): fix `aegis_prepare.py` TypeError; make `eval_times=None` raise; **C5** real leak assertions; **C6** multifactor absent≠zero | — |
| 0.7 | ⚑ **C2/C3** collector fixes + entropy/coverage canaries with auto-halt | Blocked on Murat's contamination decision (recommendation: restart the two trial clocks) |
| 0.8 | Full-sample-fit audit: grep every scaler/normalizer/feature-selection for fit-on-all-years leakage between explore and confirm | Any hit → re-run affected explore results |

### Phase 1 — Validate the factory (Weeks 2–4, ~Aug 11–31)
| # | Action | Kill criterion |
|---|---|---|
| 1.1 | **Factory Calibration Monte Carlo** (§3.1): synthetic panels, alpha ∈ {0, .2, .4, .6}, unchanged pipeline, ≥1k reps per level | If false-kill rate at alpha=0.4 exceeds ~50%, the gate is overpowered → recalibrate before any new family runs |
| 1.2 | **Permutation placebo** (calendar-marginal-preserving) as the new registered standard; pre-register the pooling/read rule FIRST; then re-read §30/§31 under it | If the gate flips under the pre-registered permutation spec → reopen 13D; else the closure stands with a cleaner receipt |
| 1.3 | **E4**: P(fire\|H0) + MDE for every registered decision rule (TRIAL-001 first — it decides 2027-06-10 and fires on noise 13–34%) | Rules with P(fire\|H0) > ~20% get re-registered with corrected thresholds |
| 1.4 | Adopt SPA + Romano-Wolf for survivor evaluation; stand up CPCV for all future gating | — |
| 1.5 | **E5**: suppress annualisation <126 obs; per-lane inception + n_obs on every surface | — |
| 1.6 | Confirm-read counter with hard budget; hypothesis-genealogy fields in the trial template | — |
| 1.7 | Survivor-specific tests: gp-small size-decile curve + GP×Size interaction; fusion leave-one-factor-out/Shapley; TSMOM-XA leave-one-asset-out + vol-targeted historical-mean baseline | gp-small: alpha only in bottom decile → reclassify liquidity premium. fusion: if one component owns the Sharpe → retire the ensemble. TSMOM: loses to vol-targeted baseline → retire |

### Phase 2 — The BoardEx program (Sept, after pull verification)
| # | Action | Kill criterion |
|---|---|---|
| 2.1 | **D2**: PIT linkage BoardEx→CRSP (cikcode→permno; ticker only through `stocknames` with namedt/nameenddt; role start/end dates, never "Curr") + as-of manifests | Linkage coverage <70% of CRSP cap → escalate before building signals |
| 2.2 | Pre-register **BOARDEX-CENTRALITY** (§3.2a) | Zero predictive power after controls → ledger |
| 2.3 | Pre-register **INSIDER-CLUSTER** (§3.2b) | Fails placebo battery + costs screen → ledger |
| 2.4 | **D3**: IBES `numest` neglect proxy → pre-register **NEGLECT-QUALITY** = GP × ChNAnalyst, long-only sleeves, borrow-fee screen, buy/hold bands (§3.3) | Already in OSAP with documented decay → stop before building |
| 2.5 | Exploratory (no trial yet): information-diffusion lag measurement on the network (§3.2c); attention-velocity → future-vol (§3.4) | Diffusion lags indistinguishable from zero → drop the frontier version |
| 2.6 | Optional third family ⚑: disclosure-following politician signal (§3.5) — only if Murat wants a third clock running | — |

### Phase 3 — Paper + risk framework (Oct)
| # | Action | Note |
|---|---|---|
| 3.1 | ⚑ **Un-park the paper**: "The Survival Curve of 179 Pre-Registered Candidate Signals" — with the factory calibration (1.1), the placebo operating characteristics, the F1 pooling episode, and the leak-correction deltas (0.5) as exhibits | SSRN timestamp; arXiv endorsement via HKU faculty |
| 3.2 | Portfolio construction to spec: 40–70 names, inverse-vol + bounded conviction tilt + 4% caps, fractional Kelly ≤ half, regime as *sizing* overlay only | ⚑ includes the mirror/conviction concentration decision (currently NO position cap) |
| 3.3 | Lane-path fixes as **new config version → labeled segment boundary** (D vs D−1 fill asymmetry; cost-basis marking on fetch failure) | Per the agreed bug-marking policy |
| 3.4 | Third-party forward record: submit one survivor to Numerai Signals / CrunchDAO | Divergence from internal record = internal record suspect |

---

## 5. QUESTIONS FOR GEMINI DEEP RESEARCH (Murat: paste these one at a time)

1. **Citation verification.** "Verify these six 2026 references exist and summarize their actual findings: (a) Harvey, Sancetta & Zhao, 'What Threshold Should be Applied to Tests of Factor Models?', NBER w34898; (b) Benhenda, 'Look-Ahead-Bench', arXiv 2601.13770 and github.com/benstaf/lookaheadbench; (c) Li, Wang & Ma, 'Summoning the Oracle to Slay It' (FinCAD), arXiv 2605.24564; (d) Fonseca, 'Point-in-Time Backtesting of Momentum-Trend Equity Strategies', Mathematics; (e) Pham, Nguyen & Thi, 'AlgoXpert Alpha Research Framework', SSRN 6303279; (f) López de Prado, Lipton & Zoonekynd, 'Sharpe Ratio Inference', Journal of Portfolio Management 2026. For each: real or not, and the 3 key claims with page numbers."
2. **Effective N under correlated trials.** "A research program screened 179 strategy candidates that cluster into ~20 families (shared data and construction). What is current best practice for computing the effective number of independent trials for a Deflated Sharpe Ratio, and how do Romano-Wolf stepdown, Hansen's SPA, and the Model Confidence Set compare for deciding whether the best 3 survivors are real? Cite methods papers and any finance applications post-2020."
3. **False-kill rates of placebo/randomization gates.** "In event-study research, what is known about the statistical power and false-rejection (false-kill) rate of randomized-date placebo controls versus permutation tests that preserve the calendar marginal? Any literature quantifying operating characteristics of placebo gates as pre-registered kill criteria?"
4. **Board network alpha after 2010.** "Has the Cohen-Frazzini-Malloy (2008) board-connection effect (8.4%/yr) replicated or decayed post-2010? Find replications, out-of-sample tests, and any papers computing network centrality from BoardEx company networks as a return predictor. Also: documented pitfalls of point-in-time BoardEx research beyond the 'Curr' end-date sentinel."
5. **The t-hurdle dispute, 2026 state.** "Summarize the current state of the multiple-testing threshold debate in cross-sectional asset pricing: Harvey-Liu-Zhu t>3 vs Andrew Chen's 'most claimed findings are likely true' line of work (FDR ≤9%) vs Jensen-Kelly-Pedersen. What hurdle would a 2026 top-journal referee actually apply to a new predictor from a 179-candidate search?"
6. **Attention acceleration and volatility.** "Is there published evidence that the rate of change (velocity/acceleration) of investor attention — Google search volume, news counts, social media — predicts future realized or implied volatility, distinct from the attention *level* (Da-Engelberg-Gao 2011)? Post-2015 work preferred."
7. **Temporal graph methods in equity prediction.** "Survey applications of dynamic/temporal graph neural networks or temporal message passing to stock return or volatility prediction using corporate networks (board interlocks, supply chains). What has worked out-of-sample, what data did they use, and what are the known failure modes?"

---

## 6. WHAT EACH REVIEW GOT WRONG (so nobody re-imports the errors)

- **R6 (Gemini-style):** pooling attack repeats the E1 error its own numbers contradict; ≥4 bibliography entries are unrelated filler; Scherbina mis-cited; "16 years for IR 0.5" restates our own dossier line as a discovery. Its tooling advice (vectorbt, skfolio, DoubleML rwolf, RSv618/superior-predictive-ability, RSv618/rademacher-anti-serum, RD-Agent) is genuinely useful — adopt selectively; the RD-Agent "2x returns, 70% fewer factors" figure is RD-Agent's own marketing claim, not evidence.
- **R2 (GPT):** "Almgren-Chriss implemented but never imported" — no such module exists. Otherwise the cleanest review of the set.
- **R1 (DeepSeek):** pre-sample rolling-window "leak" is not a leak (past data); "confirm read ≥6 times" is an invented count. Otherwise excellent, and its fix list matches ours nearly 1:1.
- **R4/R5 (Consensus/Perplexity):** assumes BoardEx/IBES "may already be paying for" (true via HKU WRDS, but it guessed); several 2026 citations garbled; R5's missing first pages mean its defect claims (F16–F20) arrive without their arguments — all of them happen to match dossier admissions, so nothing new was asserted.
- **All reviews:** nobody found a new *empirical* flaw we hadn't already documented. The genuinely new contributions are: the factory-calibration experiment (R2), the placebo battery + treatment≤placebo null (R2/R4), effective-N clustering (R2/R3), attention-velocity→vol (R2), disclosure-following design (R4), decay-haircut priors (CSV corpus), anonymized-LLM evidence (R1), and the buy/hold band implementation detail (R1).

---

## 7. GEMINI DEEP-RESEARCH ANSWERS (received 2026-08-03, same day)

Murat ran the §5 questions through Gemini deep research. Verdicts, folded into the plan:

1. **Citations.** VERIFIED: (a) **Harvey, Sancetta & Zhao, NBER w34898** (Feb 2026) — real; develops a *lower bound* on valid thresholds that avoids assuming the total trial count, reaffirms **t ≥ 3.0**, and critiques low-hurdle papers for ignoring unpublished/failed trials. (b) **Benhenda, Look-Ahead-Bench** (arXiv 2601.13770) — real; confirms severe look-ahead bias in open-source LLMs (Llama 3.1, DeepSeek 3.2) with alpha decay outside memorized windows. **EXCLUDED as unverifiable (treat as hallucinations until proven otherwise): Li-Wang-Ma "FinCAD", Fonseca (Mathematics), Pham et al. "AlgoXpert", López de Prado-Lipton-Zoonekynd "Sharpe Ratio Inference" (JPM 2026).** Consequence: the "honesty-drop test" concept survives via Look-Ahead-Bench alone; drop the FinCAD citation; the CPCV-beats-WFA claim still stands on Arian et al. 2024 (pre-2025, independently real).
2. **Effective N:** Romano-Wolf (multiplier bootstrap, FWER, DoubleML implementation) + Hansen SPA (stationary block bootstrap preserves autocorrelation/vol clustering; `RSv618/superior-predictive-ability`) confirmed as the dependence-aware tools. Matches Phase 1.4.
3. **Placebo false-kill:** confirmed our diagnosis — uniform random-date placebos destroy the calendar marginal AND intra-firm clustering; under macro cohort drag they mismatch the null and can falsely kill valid signals. The registered replacement (Phase 1.2) is a **permutation across firms keeping exact dates** or a circular block-shift. This is now three independent sources (DeepSeek, R6, Gemini) agreeing with our F2.
4. **BoardEx PIT:** new actionable detail — beyond avoiding `"Curr"`, screen **imputed dates via `datestartroleflag`** (and end-role flag). Added to Phase 2.1 linkage spec: rows with low-precision date flags get excluded or lag-padded, never trusted at day precision.
5. **t-hurdle dispute RESOLVED for our purposes:** HSZ 2026 directly counters Chen's t≥1.79 line — low-hurdle arguments analyze only *published* factors and ignore the unpublished-trial iceberg. **Our t≥3-class discovery bar is now the defended mainstream position, not merely the strictest.** Directly answers Murat's "can we lower confidence to 85/60?" — no for *discovery claims*; risk appetite is expressed through posterior-mean *sizing*, as already agreed.
6. **Attention velocity:** structurally safer than LLM sentiment (distraction effect); coverage *decline* (ChNAnalyst) reaffirmed as the tradable neglect measure. Supports Phase 2.4/2.5 design as written.
7. **Temporal graphs:** primary failure mode is look-ahead in *network construction* — the graph must be rebuilt as-of each rebalance date from historical link dates, never from a full-sample snapshot. This is a design constraint on Phase 2.2/2.5 (and exactly the failure the truncated-BoardEx era would have caused).

## 8. STATE OF DATA (as of this writing)

WRDS full pull: 13 BoardEx NA tables landed and count-verified (network = 5,018,507 edges vs 1M truncated before; director-employment 10.7M; profiles 1.24M). The 17.2M-row `na_wrds_dir_profile_all` is downloading in 16 modulo-chunks (server dropped single-query pulls; fixed with chunked pull + auto-reconnect). Remaining after it: `na_wrds_dir_profile_emp`, `na_wrds_org_composition`, `na_wrds_org_summary`, IBES FY1 (`statsum_epsus`, fpi=1), fresh `crsp.dsedelist`. Non-interactive credentials work (pgpass + explicit `wrds_username`) — Claude can run/resume all future pulls unattended. Also discovered in entitlements: `ravenpack_trial`, `optionm`, `tfn` (Thomson 13F), `audit` — worth a recon pass (M3).
