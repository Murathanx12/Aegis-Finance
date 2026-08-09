# OVERNIGHT PROMPTS — Portfolio Factory campaigns (written 2026-08-08)

Murat: paste NIGHT-1 into a fresh heavy-model session (your usual fresh
`/model opus` pattern — Fable also fine) and let it run. NIGHT-2 goes
the following night, after NIGHT-1's receipts exist. Each prompt is
self-contained; the session must read the referenced docs before
computing anything.

**STATUS UPDATE 2026-08-09:** NIGHT-1 was executed 2026-08-08 (Murat ran
it directly) and its work was independently validated on 2026-08-09:
branch `factory/night-1` in `Aegis module`, 35/35 tests pass, harness
calibration receipt exact (Δt = 0.00 vs banked CBOperProf), holdout
refusal enforced in code + tested, FF5+UMD numbers verified against
scorecard JSONs, 448-experiment denominator honest, pre-registrations
committed before compute, no lane/NAV files touched, late placebo bands
(INSIDER-TILT, RISK-SAT-1) completed post-verdict and confirm no verdict
change. Verdict: `docs/PF1_CAMPAIGN_VERDICT_2026-08-08.md` +
`docs/AMNESIA_VERDICT_2026-08-08.md` (both in Aegis module).
**The original NIGHT-2 prompt below is SUPERSEDED by the revised NIGHT-2
and NIGHT-3 prompts at the bottom of this file** — the amnesia trials
already answered the masking questions the old prompt was designed to
ask, and PF-2 is now the higher-value night.

---

## NIGHT-1 PROMPT — build the factory harness, re-run PF-1 under it

You are running an unattended overnight build-and-test campaign for the
Aegis Portfolio Factory. Binding context, read in this order before any
compute: `docs/EXECUTION_STANDARD_2026-08-08.md` (the frozen rule),
`docs/ROADMAP_PORTFOLIO_BRAIN_2026-08-08.md` §3 (the PF-1 menu),
MEMORY current state, and the pre-register-trial skill. Canon applies in
full: pre-register every experiment before computing it; every variant
gets an immutable registry ID (PF-<STRAT>-NNN); placebo/control arms are
gates, not diagnostics; no lane seeding, no flag flipping, no touching
paper_nav or the 10 live lanes — this is research compute only.

MISSION, in order, stopping cleanly wherever time runs out:

1. BUILD the factory harness (engine/factory/): a runner that takes a
   frozen strategy spec (universe, signal, construction, rebalance
   schedule, concentration, cost model, benchmark, dates, seed) and
   produces the full scorecard from EXECUTION_STANDARD §3: CAGR, cum/
   annual returns, SPY + excess, max DD, vol, Sharpe/Sortino/Calmar, win
   rate, avg win/loss, turnover, costs, exposure, concentration, best/
   worst year, time underwater, catastrophic-loss probability, terminal
   wealth distribution, and PER-REGIME blocks (pre-2008, GFC, post-crisis
   bull, COVID, 2022 bear, 2023+). Data: the 63yr survivorship-free
   panel (CRSP spine + post-2002) with delisting returns flowing through;
   KO cost model; yfinance forbidden for money claims. Controls built in:
   SPY B&H, equal-weight universe, random-selection-with-identical-
   turnover (≥100 draws, seeded), and factor controls where the strategy
   claims a mechanism. Unit tests + a loud-failure audit on every
   collector/loader (silent no-op is the house failure mode).
2. VALIDATE the harness before trusting it: reproduce one known result
   (CBOperProf small flat-25 → expect net t ≈ 4.3 over 1985-2001) and
   one known null (a random signal → expect placebo-band performance).
   If either fails, STOP and write the discrepancy report — do not run
   the campaign on an uncalibrated instrument (NEGATIVE_RESULTS #34).
3. REGISTER then RUN the PF-1 six (GP-small, PROF-COMPOSITE,
   ENGINE-ALPHA, INSIDER-TILT, REGIME-SWITCH, RISK-SAT-1) exactly as
   frozen in the roadmap, each with: the base configuration + a
   pre-registered variation grid (rebalance monthly/quarterly; top-N
   concentration 10/25/50; cost flat-25/KO; universe small/largemid/all)
   — grid frozen per strategy BEFORE the first run. ENGINE-ALPHA's
   placebo (random top-N, identical turnover) is a hard gate.
   REGIME-SWITCH must use walk-forward regime labels only.
4. THEN combinations: pairwise overlays among survivors of step 3 +
   the full stack, reporting standalone / marginal / interaction
   contribution per signal. A signal weak alone but additive in
   combination is a finding, not a failure.
5. HOLDOUTS: designate and DO NOT TOUCH the final holdout block per
   registration (default: most recent 24 months of the panel). Nothing
   in tonight's run reads it. Holdout firing is a separate attended
   step.
6. RECEIPTS: per experiment — registry entry, frozen spec, scorecard
   JSON + one-page markdown; per night — a campaign summary with the
   TOTAL experiment count printed (the multiple-testing denominator),
   the WINNERS / UNRESOLVED / FAILED split (UNRESOLVED = test could not
   answer, with the reason class), and a ranked table by excess terminal
   wealth under the ruin constraint. Commit to a research branch
   (factory/night-1), never main. End with a STATUS handoff doc.

Hard limits: no network beyond data providers already configured; no
key changes; if a step's assumptions break (missing data, harness
defect), record and skip forward rather than improvising a weaker test
silently. Honesty over completeness: a night that ends with "harness
validated, 2 of 6 strategies run cleanly" and true receipts beats six
scorecards with a silent defect.

---

## NIGHT-2 PROMPT — LLM historical event-replay harness (first classes)

Prereq: NIGHT-1 receipts exist. Read EXECUTION_STANDARD §5.1-5.2 (the
contamination protocol and PIT hierarchy) first; they are binding.

MISSION: build the masked event-replay environment and produce the first
graded historical forecasting dataset — earnings, FDA/PDUFA, insider
clusters.

1. EVENT SPINE from immutable PIT sources: SEC EDGAR full-text (8-K,
   Form 4, earnings releases) + FDA archives + GDELT timestamps. Every
   record: publication/availability/retrieval timestamps, source,
   version hash. Sample sizes pre-registered per class (default 200
   events/class, stratified across 2010-2024 and cap segments).
2. MASKING: anonymize tickers/entities, mask absolute dates (relative
   time only), scrub identifying details. CANARY GATE: on a 10% holdout
   of masked contexts, ask the model to identify company/period/outcome;
   if identification exceeds chance materially, tighten masking and
   re-run canaries before ANY forecasting. Burned samples are logged,
   never reused.
3. ELICITATION (from R1, frozen): structured claim schema with numeric
   anchor, median-of-10 samples, no extremization, fixed Platt α=√3
   applied downstream, external abstain gates. First forecast per event
   immutable — no self-revision.
4. BASELINE BANK graded on the identical events: historical base rate,
   logistic regression on event features, analyst consensus where
   available. The LLM is evaluated as a forecaster FIRST (Brier, log
   loss, calibration curve, ECE, coverage, abstention, sharpness) and
   only then economically (abnormal-return prediction quality, ranking).
   "Predicts events but can't convert to trades" vs "doesn't understand
   events" must be distinguishable in the output.
5. MEMORY ABLATION (pre-register first): arms A no-memory / C structured
   event memory / D calibrated claim-type memory on the same event
   stream, out-of-sample sequencing (memory built only from events
   resolved before t). This is the field's missing experiment — receipts
   publishable either way.
6. RECEIPTS: dataset manifest + per-class calibration reports + LLM-vs-
   baseline table + ablation verdicts + spend log (guards on; cache all
   responses keyed by masked-context hash). Branch factory/night-2.
   STATUS handoff at end.

Same hard limits as NIGHT-1. The replay's output is bounds and
baselines — evidence about the LLM layer's information content, never a
standalone alpha claim; the forward claim ledger remains the gold
standard.

---

# ADDED 2026-08-09 — the next two nights, built from NIGHT-1's receipts

## NIGHT-2 (REVISED) PROMPT — PF-2: the successor campaign

You are running an unattended overnight campaign for the Aegis Portfolio
Factory, continuing from a validated NIGHT-1. Work in the `Aegis module`
repo on a new branch `factory/night-2` cut from `factory/night-1` (which
holds the calibrated harness — do NOT rebuild it; extend it). Read in
order before any compute: `docs/PF1_CAMPAIGN_VERDICT_2026-08-08.md`,
`docs/AMNESIA_VERDICT_2026-08-08.md`,
`aegis-finance/docs/EXECUTION_STANDARD_2026-08-08.md`, MEMORY current
state, the pre-register-trial skill. Canon applies in full. The
2023-01..2024-12 holdout stays unread (the loader already refuses it).

MISSION, in order, stopping cleanly wherever time runs out:

1. AMEND THE STANDARD (dated, forward-only — never retro-rescore PF-1):
   append to EXECUTION_STANDARD a 2026-08-09 amendment: (a) G4 gains a
   FACTOR GATE — any claim of engine skill requires FF5+UMD alpha
   materially positive (register the exact bar before running; suggested:
   ann. alpha ≥ +2%/yr with t ≥ 2.0 on the full window); a strategy that
   fails it but passes everything else may still graduate labelled
   FACTOR-HARVEST PRODUCT, never engine skill; (b) verdict taxonomy gains
   NEAR-MISS(gate) — failed exactly one gate with placebo passed;
   (c) record the measured lesson that turnover-matched placebos test
   construction artifacts, not factor exposure (random books −2..−3%/yr).
2. REGISTER the PF-2 batch (predictions + grids frozen BEFORE compute):
   - PF-ENGINE-ALPHA-2 — same five-sleeve construct, judged under the new
     factor gate. Pre-register variations that target its two failed
     regime blocks WITHOUT market timing (timing has now failed every
     test): e.g. a fixed core-satellite blend (X% market portfolio +
     (1−X)% ENGINE-ALPHA, X frozen in the grid), and a mega-cap-inclusive
     sleeve variant. The registered question: does ANY construction hold
     net excess ≥ +3%/yr AND ≥4/5 evaluable regime blocks — and does any
     construction carry real FF5+UMD alpha, or is the honest end-state
     "best-in-class factor-harvest product"?
   - PF-ENGINE-ALPHA-PRODUCT — the product track, registered honestly as
     factor harvest: benchmark it against what an average person could
     actually buy (equal-weight universe, a simple value+profitability
     screen, and a naive multifactor mix), net of costs. Product bar:
     beats those investable alternatives on excess terminal wealth under
     the ruin constraint. This is allowed to graduate AS A PRODUCT.
   - PF-PROF-COMPOSITE-150 — the breadth variant (N=150) as a fresh
     registration with its own prediction (NIGHT-1 receipts say +4.67%/yr,
     ruin 0.102 — the registered question is whether it clears ALL gates
     as a pre-declared candidate rather than a post-hoc rescue).
   - PF-INSIDER-2-TIEAWARE — successor, only if cheap: tie-aware insider
     construction (magnitude/recency-weighted, not raw buyer counts).
     One base + small grid; a second clean failure closes the family.
   - PF-META-1 — Murat's "11th account" idea, tested in backtest FIRST:
     treat the PF-1 base strategies as assets and run a meta-portfolio
     that allocates to whichever strategies "have been working"
     (trailing-window winner selection; frozen grid: lookback 6/12/24
     months, hold top-1/top-2, monthly review). Controls: equal-weight
     of the same strategies, and the best single strategy held
     throughout. REGISTERED HOUSE PREDICTION: selection-by-trailing-
     performance does NOT beat equal-weighting the strategies — it is
     market timing at the strategy level, and timing has failed every
     test to date. If the prediction is wrong, that is exactly what
     pre-registration is for. Cheap to run; answers whether the
     winner-copying paper account should ever exist.
3. RUN under the calibrated harness with the full NIGHT-1 rule set:
   placebo bands where evaluable, equal-weight-universe control, FF5+UMD
   regression on every run, per-regime blocks, denominator printed on
   every scorecard, receipts per experiment, campaign summary with
   WINNERS / NEAR-MISS / UNRESOLVED / FAILED.
4. IF any strategy clears all gates: write (do not execute) the holdout
   firing plan — holdout reads remain a separate ATTENDED one-shot step.
5. RECEIPTS + STATUS handoff doc; commit to `factory/night-2`, never main.

Hard limits unchanged: no lane seeding, no flag flips, no paper_nav, no
key changes, no holdout reads, honesty over completeness.

---

## NIGHT-3 PROMPT (REVISED 2026-08-09) — masked DECISION replay + the
## lesson brain ("what we imagined vs what happened", at scale)

Murat's directive (2026-08-09, binding for this night): use DeepSeek
volume aggressively; replay masked historical situations as actual
buy/hold/sell decisions, not just event forecasts; record expected-vs-
actual for every decision; distill the deltas into a retrievable
"lesson brain" the LLM consults next time; the METHOD must be
model-agnostic (the learning lives in the brain, the LLM is a swappable
component); the LLM must be consistent (no noise re-rolls) and aware of
its own earlier claims WITHIN a run.

Prereq: PF-2 receipts exist. Work in `Aegis module`, branch
`factory/night-3` cut from the latest factory branch. Read first:
`docs/AMNESIA_VERDICT_2026-08-08.md` (binding),
`docs/PF1_CAMPAIGN_VERDICT_2026-08-08.md`, EXECUTION_STANDARD §5.1-5.2,
MEMORY current state, pre-register-trial skill.

Already settled — do NOT re-test: instruction-based "forgetting" does
nothing; masking works (0/240); synthetic scenarios ≈ masked (ΔBrier
0.0004) so scenario manufacture from the 63yr panel is unlimited;
contamination is sparse but near-perfect where it fires ⇒ CANARIES GATE
PER-CASE, never on aggregates. And the standing warning: on digested
numeric percentiles the masked LLM LOST to logistic regression — the
LLM only gets a chance to add value on RAW TEXT and on decision
integration, so those are the two registered questions.

MISSION (each stage pre-registered before its compute):

1. EVENT SPINE from immutable PIT sources (SEC EDGAR full text primary;
   FDA archives; GDELT timestamps): earnings releases, FDA/PDUFA,
   insider clusters. ~200 events/class, stratified 2010-2024 and by cap
   segment. Every record: publication/availability/retrieval timestamps
   + version hash.
2. MASKING (validated protocol: entity-scrubbed, relative dates,
   percentile-expressed numbers) + PER-CASE canaries — any case the
   model identifies (company, period, or outcome) is BURNED and logged;
   famous-name classes get double-strength probes.
3. EVENT FORECASTS, two arms per event: TEXT (raw masked filing text)
   vs NUMBERS (digested percentiles only). The TEXT−NUMBERS delta is
   measurement #1: "does reading help?" Elicitation frozen per R1:
   structured claims, numeric anchor, median-of-10, no extremization,
   Platt α=√3 downstream, explicit ABSTAIN tracked per bucket, first
   forecast immutable.
4. DECISION REPLAY (new — Murat's core ask): at masked historical
   rebalance points, present the LLM with a candidate slate (the
   engine's screener output at time t, masked) + each name's engine
   numbers + any live masked events, and elicit BUY/HOLD/SELL with
   conviction and a one-enum reason. Grade against realized forward
   returns AND against the engine's own numeric signal acting alone.
   Measurement #2: does LLM decision-making add anything over the
   numeric engine that already prints +5.21%/yr? Every decision writes
   an expected-vs-actual row (the "what happened vs what we imagined"
   ledger).
5. THE LESSON BRAIN (new): distill graded decisions into structured
   lesson records — {situation fingerprint (numeric features + event
   class + regime context), what was claimed, what happened, error
   size, attributed reason enum}. Retrieval = k-nearest-neighbour over
   situation fingerprints (kNN: "find the most similar past situations
   and their outcomes" — deterministic engine code, model-agnostic).
   Then the ablation that answers "does learning from mistakes help",
   with strict out-of-sample sequencing (lessons available at t only if
   resolved before t):
     arm A no-memory / arm C structured event memory / arm D calibrated
     claim-type memory (ABN posteriors) / arm E lesson-retrieval (kNN).
   Feed all resolutions into the ABN (`aegis_brain/abn/`) — its first
   at-scale workload; report the promotion gate's per-bucket verdicts.
6. CONSISTENCY PROTOCOL (frozen): temperature 0; median-of-10 for
   probability elicitation; every response cached immutably keyed by
   (model_id, masked-context hash) — the same question can never be
   silently re-rolled; within a run the model SEES its own prior claims
   and their resolutions (resolved-before-t only) via the ledger, so it
   is self-consistent per instance, exactly as Murat asked.
7. MODEL-AGNOSTIC BY CONSTRUCTION: every claim/lesson/posterior row
   carries model_id; the brain, resolver, lesson store and gates are
   pure engine code that would work identically with any LLM. OPTIONAL
   model-swap probe: IF an Anthropic key is present, re-run a paired
   subset (≤100 events, spend hard-capped at $15, spend log printed) on
   a Claude model to measure whether model quality changes the verdict.
   Skip silently if no key — never block the night on it.
8. BASELINE BANK on identical events/decisions: class base rate,
   logistic on event features, the numeric engine alone, and (where
   available) analyst consensus. Forecaster metrics first (Brier, log
   loss, calibration, ECE, coverage, abstention, sharpness), economics
   second. The LLM earns attention only above the best cheap baseline.
9. RECEIPTS: dataset manifest, per-class calibration reports,
   TEXT-vs-NUMBERS delta table, DECISION-vs-ENGINE delta table, ablation
   verdicts (A/C/D/E), burned-canary log, lesson-store dump + schema,
   spend log. Branch `factory/night-3`. STATUS handoff at end.

Same hard limits as always (no lanes, no flags, no holdout, no key
changes). Replay output = bounds and baselines on the LLM layer, never
a standalone alpha claim; the forward claim ledger stays the gold
standard. If the LLM does NOT beat the engine/baselines, that is a
publishable receipt, not a failed night — it tells us the brain should
route LLM attention to narration and event triage, not stock selection.

---

## NIGHT-3 REVISION 2026-08-09 — six adopted deltas (binding)

Adjudicated from Murat's home-session review. Full spec:
`docs/DESIGN_MEMORY_TAXONOMY_2026-08-09.md`, which is binding and is read
before building. These REPLACE the corresponding parts of the NIGHT-3
prompt above; everything not mentioned stands unchanged.

1. **EXPERIENCE replaces "lesson record"** as the canonical unit of
   learning — one record per GRADED DECISION, ~20 required fields
   (information state, walk-forward regime, fingerprint, model_id,
   brain_version, thesis enums, expected return + horizon, target,
   invalidation, realized outcome, abnormal return, error, attribution
   enum, outcome class, lesson text, embedding). Deterministic writer,
   loud-fail on missing fields, unit tests, append-only. Stage 5's kNN
   retrieval (arm E) runs over these.
2. **Two memories, separately ablatable.** EPISODIC = the experience
   store (kNN over fingerprints, arm E). SEMANTIC = ABN posteriors +
   distilled generalizations (arm D). Hard rule: a semantic
   generalization must CITE the n experiences it was distilled from and
   print n; generalizations without receipts are rejected at write time,
   exactly as claims without resolve_rules are today.
3. **Decision persistence.** Every position/candidate carries a
   persistent state object; every re-review forces the elicitation
   schema OLD BELIEF → NEW EVIDENCE → BELIEF UPDATE → NEW BELIEF →
   reason enum. Update-appropriateness is graded deterministically,
   flagging BOTH overreaction and underreaction. This is the
   consistency mechanism — never prompt "be consistent."
4. **Policy-coherence battery (new stage, runs BEFORE any economics).**
   Pre-register monotone response directions; perturb ONE variable per
   pair on synthetic scenarios (valuation ±, earnings beat→miss, regime
   bull→bear, geopolitical risk ±, revisions ±); report per-direction
   pass rates. A reasoner that fails monotonicity fails cheap. This
   gates the LLM layer; it is never evidence of alpha.
5. **NAME-ONLY arm** added to the identity ablation — real ticker + real
   date, minimal/no numeric data, same 120-situation set. It measures
   what the model does on memory ALONE, which is the contamination
   ceiling for any unmasked diagnostic. Do NOT re-run named /
   named+instructed / masked / synthetic — already measured.
6. **Anti-reward-hacking guard on every decision arm:** report exposure
   (fraction invested), abstention rate, and opportunity cost of
   abstention beside accuracy/Brier. An arm that "wins" by hiding in
   cash must be visible as exactly that. Applies to PF-META-1's
   scorecard too (already satisfied — every PF-2 meta book runs at 0.0%
   mean cash; receipt `runs/PF2/META_COMMON_WINDOW.json`).

**REJECTED / DEFERRED — do not build, recorded so they are not
re-proposed:** multi-agent debating personas (may return later ONLY as a
single-LLM vs role-ensemble ablation, and only after the single-LLM path
shows value above baselines); ten new experimental paper accounts (arms
live in the historical lab; nothing seeds a lane except through the
frozen gates); neural/learned representations (deferred until >100k
graded experiences make shrinkage posteriors saturate — a milestone, not
a date); P&L-learning arms (stays its own registered trial — one
campaign, one question).

Registry rows for the two new pre-registered pieces —
`TRIAL-COHERENCE-BATTERY-1` and `TRIAL-NAME-ONLY-1` — are committed
before their compute, per canon.
