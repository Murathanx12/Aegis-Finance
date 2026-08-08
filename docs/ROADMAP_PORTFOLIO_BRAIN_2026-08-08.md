# ROADMAP — The Portfolio Brain (P0–P4), with blind adjudication of five research documents

**Status: DRAFT for Murat's approval, 2026-08-08 evening. No code changes
made. Merges: the handoff roadmap (P1–P4), the learning-loop design
(`DESIGN_DAILY_LEARNING_LOOP_2026-08-08.md` + R1–R4 amendments), and five
externally-supplied research documents adjudicated blind in §1.**

---

## 1. Blind adjudication of the five documents

Murat supplied five findings documents without provenance. They were
judged claim-by-claim on verifiability and cross-source convergence, not
on which AI wrote them. (One of the five is recognizably our own R1–R4
synthesis restated; it was checked against the others like any source.)

### 1.1 Where all five converge (adopt with confidence)

| Claim | Convergence | Verdict |
|---|---|---|
| Daily portfolio P&L must not train the brain; prediction resolutions are the teacher | 5/5 (two add correct nuances, below) | **ADOPTED** (already in design) |
| LLM raw probabilities are inputs, not truth — separate calibration layer, graded out-of-sample | 5/5 | **ADOPTED** (Platt from day 1) |
| Structured/layered memory helps; unrestricted self-reflection memory hurts or does nothing | 5/5 | **ADOPTED** |
| Coverage/ABSTAIN accounting is mandatory, else the LLM farms calibration on easy claims | 4/5 (one adds: track *selection-adjusted* calibration) | **ADOPTED + amendment** |
| Event-study effects are real but heterogeneous, attenuating post-2015, and require class-specific decay | 5/5 | **ADOPTED** |
| Every live-money LLM-forecaster benchmark loses money; econ/business is LLMs' worst category | 3/5 (unopposed) | Carried as the standing expectation — the frozen output layer is the defense |

### 1.2 The right nuances (adopted as amendments)

1. **"Never P&L-train" is a tested empirical boundary, not a theorem.**
   One document correctly notes the supplied corpus does not *prove* a
   universal rule; our own R2 found the field is 0-for-19 on the direct
   ablation. Standing resolution: the rule holds on current evidence
   (Trade-R1, the 3.4× ECE outcome-reward experiment, ForecastCompass,
   "Honest Lying"), AND the two-arm resolution-vs-P&L posterior ablation
   stays queued as a registered trial. If evidence overturns it, the
   architecture changes. Same for RL-on-P&L: not prohibited forever —
   sandboxed as a registered experiment, never a default.
2. **Event-level realized abnormal returns ARE resolutions.** "Eventually
   let economic outcomes update beliefs" is already satisfied by the slow
   effect-size layer — a claim's realized 5d abnormal return is a
   resolution. What stays banned is *portfolio-level P&L* as a gradient.
   No design change needed; stated here to prevent re-litigation.
3. **P&L/CVaR may brake exposure** (cut positions, suspend a lane) but has
   **no write path to the posterior store** (the FinCon carve-out, already
   adopted from R2).
4. **Narrative memory never overwrites evidence memory.** Three stores —
   evidence (immutable ledger), belief (posteriors), narrative (LLM
   journal) — with one-way flow. Our design already has the three objects;
   the one-way rule is now explicit.
5. **Naming**: internally this is the **Aegis Belief Network (ABN)** — a
   hierarchical Bayesian online learner. The NN mapping stays as intuition;
   we do not claim backprop. A true learned model on top of posterior
   features is a later, registered addition.

### 1.3 Contradictions between the documents (resolved)

1. **Extremize vs anti-extremize.** One document recommends extremization
   (LLMs hedge toward 0.5); two others document rigid overconfidence at
   0.8–0.9 (27% error at 90% confidence). Both are real, in different
   regimes: *ensemble means* hedge toward 0.5; *single-shot news-anchored
   claims* (our regime) run overconfident. Resolution: **no extremization
   by default; the sign of the correction is estimated from our own
   resolutions** (the R1+R4 position stands; the blanket-extremize advice
   is rejected for our regime).
2. **Question decomposition prompts.** One corpus: improves Brier
   0.141→0.132 (Bosse et al.); another: a 38-prompt controlled study found
   decomposition prompts HURT by 0.02–0.03. Genuinely mixed evidence.
   Resolution: **downgraded from "default" to "testable lever"** — a cheap
   A/B inside the claim pipeline once volume exists. Retrieval, numeric
   anchors, ~10-sample median ensembles, and post-hoc calibration remain
   the levers with unambiguous support.
3. **KTD-Fin's meaning.** Two documents state it cleanly (proves *absence
   of selection skill* under leakage control, NOT harm from P&L-training —
   its agents run no P&L-reflection loop); one repeats the mis-attribution
   we already corrected. The corrected reading stands; the dated
   corrections in the design doc and handoff are already applied.
4. **M&A acquirer priors.** One source: +5.4–7.5% (7-day, *unanticipated
   deals only*, Tunyi 2021); another: +0.8–1.6% (Nordic/software, small
   samples); another: flat-to-negative (the classic US literature).
   Resolution: **generic acquirer prior ≈ 0 with wide σ; "anticipation"
   becomes a conditioning feature**, and the big number applies only to
   the unanticipated subclass. Never seed a generic prior from a
   conditioned subsample.
5. **CRL literature.** One document tables a −21.03% CRL prior; our R3
   agent found no academic event-study literature on CRLs (the −21% has
   industry-source, not peer-reviewed, provenance; the peer-reviewed
   clinical-trial studies — Singh/Lo 2022, Hwang 2013 — show large
   sponsor-type heterogeneity and much smaller large-pharma effects).
   Resolution: **CRL prior = strongly negative direction, very wide σ,
   flagged unverified-magnitude; our forward PDUFA/CRL ledger remains
   first-mover evidence and the real instrument.**

### 1.4 Genuinely new, high-value adoptions (came from the documents)

1. **P0 "portfolio truth" before everything** — holdings, cost basis,
   transactions, daily snapshots, benchmark-relative attribution, thesis
   IDs. You cannot attribute decisions you cannot reconstruct. (Sharpens
   the handoff's P1 task 1 into its own gating phase.)
2. **Three-bucket portfolio structure** — **Core** (compound + stabilize),
   **Conviction** (beat SPY), **Asymmetric** (outsized upside; small
   caps/geopolitical/biotech). The engine can then say "too much
   asymmetric exposure" without ever saying "don't take risk." RISK-SAT-1
   (D2) is the Asymmetric bucket's paper-lane twin.
3. **Asymmetric capital allocation, not lower evidence standards** — THE
   answer to "we play too safe": uncertainty prices the position size
   (0.5% → 8% as evidence strengthens); it never lowers the evidence bar.
   Objective: **expected long-term wealth subject to a ruin constraint**,
   not Sharpe alone and not raw return alone.
4. **Thesis IDs on every paper trade** with per-prediction attribution
   (P1 correct / P2 correct / P3 wrong → which belief earned the return).
   This is the claim ledger extended to trades — the "MU thesis has worked
   11/14 times in comparable contexts" output Murat asked for.
5. **Multi-condition sell logic** — price target, thesis break, valuation
   target, catalyst resolution, posterior collapse, expected-return-vs-SPY
   floor, risk-budget breach, better opportunity. Static price targets
   alone are rejected.
6. **Textual earnings surprise (PEAD.txt)** — numerical PEAD is heavily
   attenuated post-XBRL; the documented live variant is *text-based*
   surprise (management tone vs numbers; Philadelphia Fed WP). The
   earnings claim class gets a textual-tone variant. Magnitudes (2.9–8.0%)
   to be verified before any prior is seeded.
7. **Forecast consistency checks** (Paleka et al.) — logically-related
   claims checked for coherence *before* resolution; consistency predicts
   Brier. Cheap addition to the claim pipeline.
8. **Prior vintage/decay discounts** — every literature-seeded prior
   carries a vintage parameter; regional/small-market studies (Sweden,
   Helsinki, Indonesia, Nordic) inform *sign only*, never magnitude, for
   US large/mid caps. Index-inclusion prior ≈ 0 post-2015 (front-run).

### 1.5 Rejected

- Blanket extremization of LLM probabilities (§1.3.1).
- Seeding day-1 priors at published point estimates without decay/σ
  inflation ("published +2% → prior +2%" is explicitly rejected).
- Any LLM→trade→P&L→reinforcement loop as a production path (sandbox
  trial only).
- Treating the −21% CRL and precise (μ, σ²) prior tables in one document
  as verified — false precision; enter wide or not at all.

---

## 2. The roadmap (P0–P4)

**P0 — Portfolio truth (1 session).** Server-side store for Murat's real
holdings: positions, cost basis, transaction history, daily snapshots,
benchmark-relative P&L, thesis IDs. The PI SQLite design (V2) is the base.
Nothing above works without this substrate. *Deliverable: paste holdings →
the engine knows exactly what you own and what happened each day.*

**P1 — Portfolio Command (2–3 sessions).** The daily product:
- Per-holding verdict (BUY-MORE / HOLD / TRIM / SELL) from signal engine +
  regime + exit engine; multi-condition exits (§1.4.5), ATR stops.
- Three buckets (Core / Conviction / Asymmetric) with per-bucket risk
  budgets; sizing by evidence (§1.4.3); MC portfolio forecast fan.
- Daily brief v2: winners/losers, events per holding (EVENT-INTEL),
  analyst-forecast table WITH the §17 honesty label, candidate additions
  ranked by engine conviction.
- One "Portfolio Command" page — light mode, big fonts.

**P2 — The learning loop v1 / ABN (2 sessions).** Build order per the
design doc §7 with all R1–R4 + §1 amendments:
claim schema (numeric anchor, reaction_size vs tradable_edge, conjunction
flag, per-claim window) → hash-frozen ledger → deterministic resolver with
3 starter classes (earnings incl. textual-tone variant, PDUFA/FDA, insider
clusters) → two-timescale posterior store (fast Beta hit-rate h≈75 / slow
effect-size no-decay, BOCPD partial resets, Kish η≈0.5) → fixed Platt
α=√3 → coverage/abstain + selection-adjusted calibration → consistency
checks → Optimus brain diff. Guards: outcome embargo on retrieval,
ticker-blind state-keyed retrieval, narrative-never-overwrites-evidence.
Priors seeded per §1.3–1.4 (wide, vintage-discounted).

**P3 — News-to-numbers expansion (background cadence).** New EVENT-INTEL
classes: M&A (anticipation-conditioned), guidance/textual surprise,
government contracts, geopolitical/supply-chain (no literature — forward
ledger is first-mover). Every output a number with provenance (D6).

**P4 — Investor brain + capital (attended).** Posteriors + factors +
valuation + regime → expected-return distributions → allocator under the
ruin-constraint objective. Promotion bar t≈4.0 (lfdr-anchored) → forward
lanes only. RISK-SAT-1 registration + GP lane proposal (Murat's flags).
Registered experiments ride here: the two-arm resolution-vs-P&L ablation
(novel, publishable), RL-P&L sandbox, ML-1/kNN track.

**Unchanged non-negotiables:** pre-register before compute; placebo gates;
LLM narrates / engine computes; attended seeds; no skill claims before
24 months; fail loud. The research factory keeps running in parallel as
the truth police (D5 queue untouched).

---

## 3. PIVOT — Murat's directive, 2026-08-08 late (BINDING; supersedes P0/P1 priority)

Verbatim intent: *"mirror and conviction has my stocks with my prices
[1000 MRVL @ $180 added]. don't focus on my portfolio — create winning
portfolios, it should be able to choose stocks. create scenarios, test
them. you have full freedom. just tell me what I have to sign in for."*

**What changes:** the manage-HIS-portfolio product (old P0/P1) drops to
background — the mirror/conviction lanes already carry his holdings. The
new front is the **PORTFOLIO FACTORY**: engine-constructed portfolios,
scenario-tested, winners promoted to forward paper lanes. P2 (learning
loop) is unchanged and feeds the factory. Full freedom operates inside
the standing canon: pre-register before compute; lanes seed only on
Murat's attended env flags; backtests are direction checks; money is
proven forward.

**PF-1 first batch (scenario menu, frozen here statistics-blind; each
gets its own registration before any compute):**

1. **PF-GP-SMALL** — GP-ranked small-cap long-only. Already proposal-ready
   (best-evidenced candidate; info-confirmed/money-unproven label).
2. **PF-PROF-COMPOSITE** — small-segment profitability composite
   (GP + OperProfRD + CBOperProf, KO costs; era receipts: CBOperProf net
   t 4.30 over 17yr).
3. **PF-ENGINE-ALPHA** — the flagship "engine picks stocks": signal-engine
   composite top-N from the screener universe, risk-filtered; placebo arm
   = random top-N from the same universe, same turnover.
4. **PF-INSIDER-TILT** — insider cluster-buy tilt over a quality base
   (validates against the live insider lane).
5. **PF-REGIME-SWITCH** — regime-conditioned bucket weights (asymmetric
   sleeve up-weighted in confirmed bull, defensive in bear) — the
   era panel is the scenario lab (registered use, INSTR-ERA-CAL-1 rules).
6. **PF-RISK-SAT-1** — the high-conviction risky-growth satellite (D2),
   engine guardrails + ATR exits; measures whether conviction adds money.

Pipeline per scenario: registration → direction-check backtest with
placebo/control arm (era panel + modern panel under one-shot discipline)
→ verdict → survivors get lane YAML + hash → **Murat flips the seed
flag** → 24-month forward clock. Variations ("separately and together")
are new registrations, not silent edits.

**Murat's sign-off list (the ONLY things needed from him):**
1. **GP lane flag** — proposal ready; attended seed when he says go.
2. **RISK-SAT-1 flag** — same.
3. **One seed flag per PF winner** — YAMLs will be prepared; he flips.
4. **Key rotation still outstanding since 2026-07-17** (Alpaca/FMP/EODHD)
   — needed if factory lanes execute through Alpaca paper.
5. Optional: S&P Global MCP sign-in (failed 2026-08-08) — nice-to-have
   data, not blocking.

Registrations, harness builds, scenario runs, and verdicts need nothing
from him — sessions execute them under canon.
