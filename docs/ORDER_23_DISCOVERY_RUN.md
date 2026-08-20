# ORDER 23 — THE 8-HOUR DISCOVERY RUN (next session)

Ordered by Murat 2026-08-20 morning: "run an 8-hour backtest with
multiple lanes to find trends and correlations, use LLM to review the
strategies formed from tests, mix supervised and unsupervised learning,
produce training material and weights for the NN — and come up with
better tests." This document is the executable version, with the
discipline built in so 8 hours of compute cannot manufacture 8 hours of
self-deception.

## Phase 0 — freeze before anything runs (30 min)

- MEGA-SWEEP-2 grammar DECLARATION (the m): signals now include the new
  substrate — a declared subset of JKP characteristics (~30, chosen by
  THEME coverage, not by peeking), options features (iv_atm, skew,
  pc50), IBES revision breadth/dispersion, iid liquidity (turnover
  imbalance, dollar-volume trend) — × weightings (equal, inverse_vol,
  rank) × winner-handling (trim, exempt) × top-N (50, 100) ×
  BOTH ERAS. Expect ~1,500–3,000 books. m frozen in the declaration.
- **Slice plan per family, declared up front (§60):** for families
  never tested (all JKP-char signals): GENERATE on modern era, CONFIRM
  on early era, Holm on the confirm slice only. Families already spent
  (momentum, value_bm, streaks) run for the correlation map but are
  barred from confirmation claims.
- LLM review budget declared: ≤ $2, deepseek-v4-flash, every call
  logged to llm_calls.jsonl.

## Phase 1 — the sweep itself (3–4 h, resumable jsonl)

Run all books, persist EVERY book's monthly return series (that corpus
IS the training material). Screen stats vs same-handling baseline,
BH-FDR at the declared m. Risk panel for every book regardless of p.

## Phase 2 — unsupervised structure (1–2 h, runs while sweep finishes)

This is the "find trends and correlations" layer, done honestly:
1. **Strategy taxonomy:** hierarchical clustering of book return
   series (correlation distance). Deliverable: how many GENUINELY
   different strategies exist among thousands of variants — pseudo-
   diversity exposed. Cluster medoids become the candidate set.
2. **Regime map from OBSERVABLE data only:** rolling PCA/absorption +
   correlation structure over the 153 JKP factor returns and the
   stock panel; regime states defined by trailing windows ending at t
   (never centered, never ex-post labels — the classic trap, named).
   Deliverable: a dated regime-state series both eras long.
3. **Feature clustering:** correlation blocks among the ~450 available
   features → the deduplicated feature set the NN actually needs.

## Phase 3 — supervised layer + NN weights (2 h)

1. **REGIME-CONDITIONAL-RETURN-1 (prereg, then run):** does the
   Phase-2 regime state, known at t, predict WHICH months the return
   models work? (The era-dependence finding made this the program's
   top open question.) Generate modern / confirm early, declared.
2. **Risk head v2 artifact:** train LGBM (and one NN twin) on
   numeric+options features, BOTH eras, targets fwd_vol — save
   weights + a training manifest (data shas, feature list, hyperparams,
   seed, era split) under `backend/data/optimus/models/`. This is the
   versioned artifact the G2 risk lane transport pins.
3. **Book-outcome NN (the factory's student):** train on Phase-1's
   (rule-grammar features + regime state) → (vol, maxDD, cost drag)
   tuples. Risk outcomes first (§59). Save weights + manifest. Its
   test: predict the EARLY-era books from modern-era training.

## Phase 4 — the LLM reviewer (1 h, budget-capped)

Feed the LLM: top/bottom cluster medoids' receipts, the regime map,
the NN's worst prediction errors. Three tasks, each output structured:
(a) explain failures (autopsy), (b) propose new grammar cells or
features WITH mechanism sentences, (c) flag anything that smells like
leakage or survivorship. Every proposal lands as a HYPOTHESIS with
declared priors in the daemon queue — LLM output is a lead generator,
never a verdict. (This is the gym autopsy→rule machinery pointed at
the factory.)

## Phase 5 — synthesis (30 min)

Receipts, BH survivors → registration drafts, handoff leading NEW
INFORMATION ACQUIRED, memory, gate, deploy verify.

## Standing constraints carried

Quiesce 16:15 HKT if this is a day run (N4+ fires 17:00); no lane
write-paths; no skill claims; SIMULATION labels everywhere; screen
survivors get registrations, never promotions; the early era is a
CONFIRMATION asset — spend it deliberately, one family at a time.

## Also in the queue (not this run's job)

G2 signature (09-08 window) · Friday 08-21 first 396 grades · NAV
stamp fix after a clean scheduled firing · expectation backfill retry ·
STREAK-ENTRY-TIMING-1 design (execution layer) · Order 22 world-sensor
arc (after the discovery run digests the substrate we already bought).
