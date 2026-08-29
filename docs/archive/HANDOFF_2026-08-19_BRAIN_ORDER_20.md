# AEGIS — ORDER 20: THE FACTORY MUST NOW PRODUCE RESULTS

Issued 2026-08-18 night, after adjudicating external review round 2
(`docs/EXTERNAL_REVIEW_ADJUDICATION_2026-08-18.md` — read it first; the
rejected list at the bottom of this order is binding so dead remedies do not
get re-imported). Handoff boundary: the corrections commit that follows
`5e5f486`. Orders 15–19 remain in force where not superseded here.

## §0 Corrections already applied (this session)

1. **2026-08-21 is FRIDAY.** Sequence: Wed 08-19 Night 3 · Thu 08-20
   Night 4 · Fri 08-21 first resolutions. Fixed in the 08-19 handoff and in
   `scripts/dress_rehearsal_0821.py`'s operator-facing prints.
2. **TAQ post-recovery split is 16/137/29 of 182 retired names** (median
   2.726bp one-way). The stale 15/136/29 (n=180) is never again paired with
   n=182. Fixed in the external brief and the handoff, with an erratum in
   the handoff's failure ledger.
   *(Superseded 08-18 late night, grind: MMC was renamed MRSH on
   2026-01-14 and SQ trades as XYZ; both re-pulled under their current
   roots — the panel is now **16/139/29 of 184**, with only dead PXD
   keeping the declared band. Every doc quoting 182 was correct at its
   write time.)*

## §1 Standing rule (from Order 17, now enforceable)

**IIF-1 is a bounded ops track. It does not determine the research engine's
development order.** From this order forward, every session report opens
with **RESULTS PRODUCED** — hypotheses tested, tournaments completed,
autopsies resolved, information sources proven incremental — and only then
INFRASTRUCTURE BUILT. A night's operational health is one line, not a
section.

**"Nothing tonight" means nothing attended — not an idle machine.**
Admissible background work: historical/offline, touches no reserved
confirmation window, touches nothing on the IIF frozen surface, enters
through the daemon (priority frozen at submission, reserved windows refused
at `submit()`). Compute utilization is not the objective; **resolved
information per compute/dollar is** (mission rule 5). No API spend to look
busy.

## §2 Tonight's / next session's background queue

1. Daemon's first real queue loaded and running: Holden–Jacobsen
   effective-spread join on the TAQ overlap (spec gains a recalibration
   cadence + regime-drift check, per adjudication B7) · universe hygiene
   (SQ→XYZ, MMC unexplained) · floor-sweep leftovers.
2. CONVEXITY-PRESERVATION episode construction (already specified, O19).
3. AEGIS-NET canonical panel materialization + feature coverage/missingness
   audit — the dataset work that needs no signature.
4. LANE-AUTOPSY cross-arm reconstruction (see §5).
5. Nightly machine-readable daemon receipt: proposed / duplicates / corpse
   matches / underpowered / screened / failed / promoted / spend.

## §3 P0 — AEGIS-NET becomes an experiment

Deliverable is a scoreboard, not a module. **Draft the tournament
pre-registration now; it runs only after Murat signs** (canon §6).

Frozen in the draft: regularized linear · LightGBM · MLP-1 · MLP-2 · MLP-3.
Same universe, PIT inputs, purged walk-forward folds, missingness handling,
declared costs. Heads: cross-sectional residual rank · forward magnitude ·
realized vol · forward max drawdown · continuation/reversal · barriers.

**New this round (adjudication A5): the barrier head is also formulated as
competing risks** — cause-specific hazards for upper/lower barrier with
`neither` as censoring, vs fixed-horizon multinomial. The label already
carries `days_to_barrier`; throwing the timing away is waste. Survival
machinery exists in-repo (lifelines).

Primary question, declared before scoring: does any complex model beat the
simplest admissible baseline OOS by more than its own MDE, after costs?
LightGBM wins if LightGBM wins; linear wins if linear wins. Feature-family
ablations reported: numeric → +options → +expectations → +event/LLM →
+semantic. §63 applies: SCREEN under BH-FDR (m = tests run), any EXPORT
under Holm (m = declared budget). n_effective counts date blocks.

## §4 P0 — NEURAL-RELATIVE-VALUE-1

The model is the actual decision: incumbent A vs candidate B. Heads:
P(B beats A net of declared costs, horizon H) · E[B−A residual] · relative
barrier outcomes · drawdown delta. Compare pairwise logistic baseline ·
LightGBM ranking · shared-weight MLP. Pair count is never n — n_effective
from independent date blocks × security dependence. **G5 confronted by
name in the registration:** what G5 never contained is pairwise capital
substitution, incumbent-candidate interaction, and the event/expectation
information families. Labels are unblocked (TAQ-calibrated + surviving-band
names).

## §5 P1 — LANE-AUTOPSY cross-arms (outranks everything else in P1)

Two competent external reviewers read the 14-point mirror gap in opposite
directions (adjudication A6 vs B1). Only the replay settles it. Full
factorial: {conviction book, mirror book} × {actual weights, equal weights},
identical rebalance schedule; then timing/entry/exit/trim differences one
at a time; contribution attribution (Shapley-style if interactions are
large). **Reconcile reconstructed NAV against the authoritative paper NAV
before any economic sentence.** Report turnover per arm (B's one legitimate
point inside a rejected remedy). The question: which concentration
decisions produced the regret, and was the concentration compensated by
ex-ante information? 70 days licenses mechanism attribution, not verdicts.

## §6 P1 — imports from review round 2 (all `hypothesis_source`, §61 cap)

Each enters through `pre-register-trial`, names its corpse, and dies at its
own declared kill:

- **PURE-NEWS-RESIDUAL-1** (top import). Model expected news from PIT
  characteristics; the residual (observed − expected representation) is the
  signal candidate. Gate: the expected-news model trains strictly before
  each article timestamp. Kill: fails to beat raw-news and no-news baselines
  under identical folds/MDE.
- **IMPLIED-REVISION-1** (expected SHELF). Binding input is PIT
  analyst-report text; entitlement verified by probe, not catalogue. No PIT
  text ⇒ SHELF, no approximation with current reports. Corpse: dead/perverse
  target levels, named.
- **INFORMATION-PROCESSING-GAP-1**. Attention/processing-load state at
  event time; does identical surprise resolve differently by load?
- **OPTIONS/EQUITY-DISLOCATION-1**. Event-conditioned disagreement state
  only; strict timestamp synchronization; the generic options-alpha corpse
  named.
- **EVENT-RESOLUTION-CURVE-1 / INFORMATION-HALF-LIFE-1** — already
  specified in Orders 15–17; unchanged, §62 applies (tradable fraction or
  not reportable; no ratio whose denominator is under its own MDE).
- **REACTION-GAP-1**. The surviving MARKET-GRAPH-1 relation information
  pointed at propagation, not covariance; min-variance route stays closed.

P2 shelf (daemon-scored, not scheduled): NEWS×FLOW (credible PIT retail
proxy or SHELF) · SEQUENCE-OF-EVIDENCE-1 (simple sequence baselines before
any Transformer; G5 confronted) · MODEL-DISAGREEMENT-1 ·
CROSS-ENTITY-LAG-1 (simple propagation before any GNN) ·
BLOOMBERG-CHALLENGE-SIM-1 (provisional 2025-format config; replaced by real
2026 rules on publication; production Aegis is not tuned to contest
incentives).

## §7 Bounded ops (they do not consume the research day)

- Fault-injection test of the night pipeline as a SEQUENCE (network drop,
  corrupted feed ⇒ halt, never partial accrual) — adjudication B3.
- The `< NUL` schtask remedy (attended) and the 3/3 acceptance clock.
- Write-only telemetry backlog (167/806) · AGK spread-convention audit ·
  min-meaningful-Brier signature · early-fire-and-hold launcher variant.

## §8 Operations calendar (attended items are Murat's)

- **Wed 08-19**: Night 3 attended (`--dry-run` first, launch on its
  number); first clean SCHEDULED acceptance receipt expected; Brier BAR
  0.10 signature when handed (the `NOT_ANSWERABLE_AT_N` sentence staying in
  is the point).
- **Thu 08-20**: Night 4 attended.
- **Fri 08-21**: first h=1 resolutions (396). Resolution is mechanics only:
  the read gate licenses nothing on the H1 contrast before 40 graded
  nights; `MODE_POWER` deletes what a promise would merely not read.
- **~Sun/Mon**: arm `AEGIS_IIF1_LAUNCHER_ARMED=1` after 3/3 (attended).
- NET tournament prereg signature when the draft is handed.

## §9 Rejected this round (do not re-import)

- Ledoit-Wolf shrinkage as the fix for the 14-point gap — misreads the
  finding; the EW arm is the one behind (B1).
- Murphy/BSS on the H1 contrast on resolution day — read gate; licensed at
  40 nights (B2).
- Satellite nightlights / port congestion ingestion — fails the daemon's
  own value score (B4).
- Half-arming with a human confirm before "firing orders" — there are no
  orders; the acceptance test is the graduated buffer (C5).
- `max_quote_age_ms` intra-day band recalibration — offline daily
  calibration has no 500ms exposure; staleness folded into the H-J join
  spec (C6).
- Pre-40-night cumulative Brier dashboard — the incremental peek the gate
  exists to prevent; build at the licensed read (C8).
- Microsecond clock-skew analysis for overnight forecasts — wrong scale;
  the two-clocks lesson is about hours (C9).

— brain, 2026-08-18 night
