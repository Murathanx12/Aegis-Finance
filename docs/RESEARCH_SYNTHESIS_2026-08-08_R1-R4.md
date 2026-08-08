# RESEARCH SYNTHESIS — R1–R4 Deep-Research Night (2026-08-08)

**Status: research synthesis, not a registration.** Four independent Opus
deep-research agents ran in parallel on 2026-08-08 (294 total web fetches),
each instructed to fetch primary sources, mark memory-only claims UNVERIFIED,
and end with an explicit verdict on the design assumptions in
`DESIGN_DAILY_LEARNING_LOOP_2026-08-08.md`. Full receipts (verbatim agent
reports with every table and citation):

- `research/R1_LLM_FORECAST_CALIBRATION_2026-08-08.md`
- `research/R2_LLM_AGENT_MEMORY_ABLATIONS_2026-08-08.md`
- `research/R3_EVENT_STUDY_PRIORS_2026-08-08.md`
- `research/R4_ONLINE_LEARNING_WEAK_SIGNAL_2026-08-08.md`

---

## 1. Headline: were our findings good?

**Yes — the architecture survives adversarial external review, and in two
places it is ahead of the published literature.** All four runs came back
SUPPORT on the load-bearing wall (daily learning from prediction resolutions,
never P&L), with one required citation correction, one required rule
sharpening, and a set of mechanism upgrades. No run found a reason to reopen
D3.

Independent convergences worth noting (the runs could not see each other):

- **R1 and R4 both conclude: do not extremize by default.** R1 because
  single-shot news-anchored claims are rigidly overconfident (PolyBench), R4
  because claim-types sharing macro drivers are the exact information
  structure where optimal aggregation *anti*-extremizes (Lichtendahl 2017).
- **R2 and R4 both land on the two-layer separation** — R2 from ablation
  evidence (risk gate ≠ belief store), R4 from power arithmetic (fast
  hit-rate layer ≠ slow effect-size layer).
- **R1, R2, and R4 all independently re-derive our UNDERPOWERED finding**:
  Alpha Illusion's Sharpe 1.51 ± 1.08; Trade-R1's skill-vs-luck argument;
  R4's lfdr bar t≈4.0 vs SPY's t≈1.1 over 72 months. Three literatures,
  same arithmetic, same conclusion as §34/§35 of our own ledger.
- **Alpha Illusion §5 (six authors, five institutions) independently
  prescribes our architecture**: LLMs upstream as auditable information
  interfaces, probability calibration as its own stage, final decision
  authority in non-LLM modules. "LLM narrates / engine computes," written by
  people who have never seen this repo.

---

## 2. THE CORRECTION — KTD-Fin was miscited (mechanism, not number)

**KTD-Fin is real**: Zhu et al. 2026, *From Knowing to Doing: A
Memory-Controlled Benchmark for LLM Trading Agents on Stock Markets*,
arXiv:2605.28359 (Tsinghua/Stepfun/SJTU/Adelaide). 10 frontier LLM agents,
CSI300, 548 trading days, leakage-controlled Barra attribution. **9 of 10
show negative stock-selection alpha (−0.7% to −77.8%; only Claude Opus 4.7
positive at +0.2%).** The number we cite is right.

**But the agents do not self-train or reflect on their own P&L.** The paper
contains no P&L-reflection loop at all — it is a masking/attribution study.
It proves *absence of selection skill* (returns are passive market/style
exposure + ticker-memory contamination), not *harm from P&L-based learning*.
Our June citations (CANON §3, BACKLOG, FRAGILITY_RESEARCH) were correct; the
mis-attribution crept into `DESIGN_DAILY_LEARNING_LOOP_2026-08-08.md` §1 and
`SESSION_HANDOFF_2026-08-08_NEXT_PHASE.md` D3 — **both corrected with dated
notes on 2026-08-08.**

**What actually carries the "never P&L-train" argument now (stronger than
before):**

1. **Trade-R1** (arXiv:2601.03948, Jan 2026) — the argument published in
   finance: outcome rewards "conflate skill with luck" at daily horizon.
   (Comparative tables unextracted — direction verified, magnitudes
   UNVERIFIED.)
2. **Singh, Reddy & Chopra** (arXiv:2607.00164) — controlled experiment, NFL
   win probability (better SNR than daily equities): outcome-based reward →
   ECE 0.10 and progressive drift; proper-scoring-rule reward → ECE 0.029,
   converged in 50 steps. **3.4× calibration gap.**
3. **ForecastCompass** (arXiv:2605.30858) — memory bakeoff on Brier:
   factor/calibration memory that *refuses to store resolved outcomes*
   0.075–0.187 vs Reflexion-style reflection memory 0.150–0.252 ≈ **no memory
   at all** (0.150–0.266).
4. **"Honest Lying"** (arXiv:2605.29463) — mechanism: under coarse binary
   feedback, 0/121 self-reflections identified the correct cause; confabulated
   memory causally *worse than no memory*; fix = programmatic feedback
   extraction (= our deterministic resolver).

**Honest residual:** no published study anywhere directly ablates
resolution-keyed vs P&L-keyed memory holding all else fixed (0 of 19 primary
studies in the field reach full reproducibility; none run this ablation). Our
claim ledger could run it as a cheap pre-registered two-arm trial — a
genuinely novel, publishable result either way. → proposed as a future
registration (Murat's queue).

---

## 3. Design amendments adopted into the build spec

These amend `DESIGN_DAILY_LEARNING_LOOP_2026-08-08.md` §7's build order
(claim schema → resolver → posterior store → brief v2). None change the
architecture; all change mechanisms inside it.

### A. The rule becomes two rules (R2)
> **(a) Learning signal:** posterior updates come only from resolved
> prediction quality (Brier/calibration/hit-rate vs pre-registered claims) —
> never realized P&L.
> **(b) Risk gating:** P&L/drawdown/CVaR MAY trigger exposure cuts, caps, and
> lane suspension — control actions with **no write path to the posterior
> store**. Enforce mechanically; test-pin the absence of the write path.

Without (b) the rule would forbid the best published ablation in the
literature (FinCon's CVaR brake, portfolio SR 3.27→1.14 when removed); with
(b), FinCon becomes evidence *for* the architecture.

### B. Claim schema additions (R1 + R3)
- **Mandatory numeric anchor field** on every claim (base rate, IV-implied
  probability, consensus). Worth ~0.01 Brier to −11% relative. No anchor →
  the coverage guard forces ABSTAIN.
- **`claim_kind: reaction_size | tradable_edge`** — reaction-size effects
  (M&A target CAR, trial readouts, entity-list hits) are stable across four
  decades; tradable-edge effects (PEAD, index pressure, insider
  follow-through) have decayed 50–93% (Chen-Velikov). One field conflating
  them mis-sets every prior.
- **Conjunction flag** — "A and B" claims are the LLMs' worst measured
  failure class (ForecastBench: superforecasters 0.071 vs LLMs 0.124).
  Decompose or downweight.
- **Window declared per claim**, and the resolver must honor it — export
  controls realize over [0,+20] with nothing in [−10,−1]; a hard-coded
  [−1,+1] grader would score the class as "no effect."

### C. Elicitation + aggregation defaults (R1)
Base-rate-first + frequency framing; NO sophisticated decomposition prompts
(measured harmful: +0.02–0.03 Brier); ~10 samples across ≥3 model families,
**median** aggregation; fixed Platt α=√3 on log-odds from day 1 (refit
per-family with pooling only after ~300 resolutions; never isotonic at our
n); clamp to [0.02, 0.98]; **no extremizing (a=1.0)** until the sign is
measured on our own resolutions; abstain via **external gates only**
(retrieval count <5, missing anchor, conjunction, imminent resolution) —
LLM self-abstention is a measured non-mechanism.

### D. Posterior store: two timescales + guards (R4)
- **Fast layer** (hit-rate Betas, calibration weights, attention): half-life
  ~75 resolutions. **Slow layer** (effect sizes, promotion evidence): **no
  decay**; BOCPD-gated *partial* resets only (ESS ×0.5, τ²×2 — never hard
  reset). BOCPD already exists in `anomaly_detector.py`.
- **Calibration needs a slope, not just a rate**: Beta posteriors fix
  frequency; the documented LLM failure is a log-odds slope error. Keep the
  Platt α as a separate pooled parameter.
- **Correlated-resolution deflation**: tempered updates with η = 1/DEFF,
  DEFF = 1+(m̄−1)ρ, day-1 ρ=0.2 (η≈0.5 at 6 same-day resolutions).
- **Per-cell effect sizes are unidentified** at our resolution rate
  (n≈3,600–7,200 needed for a 5bps effect): report pooled hierarchical means;
  per-cell effect estimates below n_eff≈1,000 are a category error.
- Full day-1 hyperparameter card (16 rows, each with citation): R4 receipt
  §(c). Priors: σ_θ = 0.75 in t-units (NOT Chen-Zimmermann's
  selection-filtered 3.0), effect prior N(0, (4bps)²) per Chen-Velikov's
  net-anomaly ceiling.
- **Attention bandit**: discounted Thompson (γ≈0.985/day on the Beta params)
  with a **randomized ε=0.20 attention floor** so unbiased pooled estimates
  always exist. Reward = information yield, never P&L (D3-consistent).

### E. Memory-retrieval guards the design was missing (R2)
- **Outcome embargo on the claim ledger's retrieval path**: an episode
  recorded at t must not expose its resolution to retrieval until now ≥ t+k
  (its realization lag). Without it the ledger itself becomes a look-ahead
  vector (the "Oracle Fallacy"). This is the memory-side analogue of our
  purge/embargo discipline — the harness has it; the retrieval path must too.
- **Retrieval keyed on market state/factors, never on ticker.** KTD-Fin's
  masking ablation: the ticker handle alone drives trades (bright-mode agent
  trades actively on ticker memory with zero data; blinded, holds cash at
  0.00%). Mask identifiers at retrieval time. Note honestly: blinding removes
  a contamination channel, it does not create skill (9/10 negative even
  blinded).

### F. Promotion bar (R4) — confirms and quantifies the standing rule
Efron local-FDR anchored on our own measured base rate (3/196 money legs ≈
π₁ 3%): **t ≈ 4.0 for lfdr ≤ 0.10**, on the block-bootstrapped,
cluster-deflated, EB-shrunk statistic, plus DSR > 0.95 on effective trial
count. SPY itself prints t≈1.1 over 72 months ⇒ **no 72-month window can
clear the bar** — the promotion gate must be specified against the forward
paper lane; the daily posterior layer is scoped to attention + calibration
only. This is D3 and the §35 UNDERPOWERED conclusion, now with external
arithmetic. Corollary: do not use Storey q-values at K≤32 cells (measured
biased); BH/Holm or the anchored lfdr only.

### G. Scoring
Brier **skill score vs per-claim-type climatology**, never raw Brier
(difficulty varies by class; ForecastBench needed two-way fixed effects to
compare at all). Pre-resolution health metric: negation-pair consistency
probes (Paleka et al., ICLR 2025 oral) — resolution feedback at 10–50
claims/week is too slow to be the only signal.

### H. Day-1 priors for the resolver's three starter classes (R3)
Full table in R3 receipt §(c) with grades and τ discipline. Starter classes:
- **Earnings**: PEAD is DEAD (large caps since ~2006, microcaps since ~2016)
  — prior mean 0 on any drift claim; announcement *reaction-size* claims are
  fine. Event-date precision matters more than the model (a 1-day date error
  = >15%/yr in measured hedge returns).
- **PDUFA/FDA**: readout reactions well-measured (small-biotech positive
  ≈ +6%, misses ≈ −12% scaled, big-pharma ≈ 0); **CRL and PDUFA-run-up
  classes start near-uninformed** (no academic literature exists — the
  highest-learning-rate classes in the ledger, and an area where our forward
  ledger can genuinely be first).
- **Insider clusters**: cluster buys ≈ 2× non-cluster (3.8% vs 2.0% at 21d,
  Grade C), premium is post-SOX disclosure-driven (favourable for a live
  signal); cluster *sales* are near-uninformative — encode the asymmetry.
  Priors carry the 50% predictive-edge haircut.
Also: index-inclusion effect is GONE (0.8% n.s. 2010s) except pure
non-migration additions (+4.2%); migrations are ≈ −2.5% — covariate, not a
single class mean.

---

## 4. Expectation-setting (for Murat, plainly)

Every live-money benchmark of LLM forecasters in the literature loses money
(Prophet Arena: none break even; PolyBench: 5/7 negative; Prediction Arena:
6/6 lost real capital on Kalshi), even when their Brier matches the market —
and Economics & Business is the measured *worst* category for LLM
forecasters. **Calibrated informativeness is achievable; profitable
informativeness is undemonstrated anywhere.** The loop's success metric is
Brier skill vs climatology — exactly what D3 already says. The honest upside:
our forward, timestamped, pre-registered claim design is *ahead* of the
field's evaluation practice (0/19 primary studies fully reproducible;
historical replay of claim generators is contamination-worthless), and two
prior classes (CRL, PDUFA run-up) have **no academic literature at all** —
a forward ledger there is first-mover evidence, not catch-up.

## 5. Follow-ups queued (not started)

1. **Two-arm ablation registration** (resolution-keyed vs P&L-keyed posterior
   updates on the same claims/resolver/window) — novel, publishable, settles
   D3 on receipts. Needs pre-registration before any compute.
2. Pull Trade-R1's comparative tables (5/12/14) before citing magnitudes.
3. Re-check TradingGroup Table 3 column orientation (the NFLX reversal).
4. LiveTradeBench (arXiv:2511.03628) — extraction failed; a live-market
   result would be the highest-value missing evidence.
5. R3 gap classes to watch for new literature: CRLs (FDA transparency batches
   2024–25 make a study likely soon), CHIPS awards, post-2015 government
   contracts.
