# OVERNIGHT PROMPTS — Portfolio Factory campaigns (written 2026-08-08)

Murat: paste NIGHT-1 into a fresh heavy-model session (your usual fresh
`/model opus` pattern — Fable also fine) and let it run. NIGHT-2 goes
the following night, after NIGHT-1's receipts exist. Each prompt is
self-contained; the session must read the referenced docs before
computing anything.

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
