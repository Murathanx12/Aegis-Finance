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

## NIGHT-3 PROMPT — LLM event replay, rebuilt on the amnesia receipts

Prereq: PF-2 receipts exist. Work in `Aegis module`, branch
`factory/night-3`. Read first: `docs/AMNESIA_VERDICT_2026-08-08.md`
(binding — it replaces guesswork with measurements),
EXECUTION_STANDARD §5.1-5.2, MEMORY current state.

What the amnesia trials already settled — do NOT re-test: instruction-
based "forgetting" does nothing; masking works (0/240 identifications);
synthetic scenarios (fake names/dates, jittered facts) score within
0.0004 Brier of real-masked, so scenario manufacture from the 63yr panel
is validated and unlimited; contamination is sparse but near-perfect
where it fires (5/5 correct on famous collapses) — so CANARIES GATE
PER-CASE, never on aggregate stats.

And the warning that shapes this night: on five pre-digested numeric
percentiles, the masked LLM LOST to a 5-feature logistic regression.
If NIGHT-3 feeds the LLM the same digested numbers, it will measure
nothing new. The registered question is therefore: does the LLM add
information ABOVE cheap baselines when given what only it can read —
the raw text (8-K bodies, earnings-release language, FDA letters,
insider filing context)?

MISSION:
1. EVENT SPINE from immutable PIT sources (SEC EDGAR full text primary;
   FDA archives; GDELT timestamps): earnings releases, FDA/PDUFA, insider
   clusters. ~200 events/class, stratified 2010-2024 and by cap segment,
   sample sizes pre-registered. Every record carries publication/
   availability/retrieval timestamps + version hash.
2. MASKING using the validated protocol (entity-scrubbed, relative dates,
   percentile-expressed numbers) + PER-CASE canaries: every masked
   context gets an identification probe; any case the model identifies
   (company, period, or outcome) is BURNED and logged. Famous-event
   classes (large biotech, household names) get double-strength probes.
3. ELICITATION (R1 frozen): structured claims, numeric anchor,
   median-of-10, no extremization, Platt α=√3 downstream, explicit
   ABSTAIN allowed and tracked per bucket, first forecast immutable.
   Two arms per event, pre-registered: TEXT arm (raw filing text, masked)
   vs NUMBERS arm (digested percentiles only). The delta between them is
   the measurement — "does reading help?"
4. BASELINE BANK graded on identical events: class base rate, logistic
   on event features, and where available analyst consensus direction.
   LLM evaluated as a forecaster first (Brier, log loss, calibration,
   ECE, coverage, abstention, sharpness), economics second (abnormal-
   return ranking). The LLM earns attention only above the best baseline.
5. MEMORY ABLATION (pre-register first): arms A no-memory / C structured
   event memory / D calibrated claim-type memory, memory built only from
   events resolved before t. Feed resolutions into the ABN
   (`aegis_brain/abn/`) — this doubles as its first real workload at
   scale; the promotion gate's verdict on each bucket goes in the report.
6. RECEIPTS: dataset manifest, per-class calibration reports, TEXT-vs-
   NUMBERS delta table, LLM-vs-baseline table, ablation verdicts, burned-
   canary log, spend log (guards on; cache keyed by masked-context hash;
   deepseek-chat temperature 0). Branch `factory/night-3`. STATUS
   handoff at end.

Same hard limits. Replay output = bounds and baselines on the LLM layer,
never a standalone alpha claim; the forward claim ledger stays the gold
standard.
