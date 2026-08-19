# EXTERNAL REVIEW ADJUDICATION — 2026-08-18 (round 2)

Three external responses to `docs/EXTERNAL_REVIEW_BRIEF_2026-08-18.md` were
returned (call them A, B, C in the order received: A = the long review with a
draft Order 20; B = the architectural review; C = the next-steps/table
review). Every material claim is scored against the ledger, ranked by
decision impact. Verdict vocabulary: **CONFIRMED** (checked against receipts,
acted on) · **ACCEPTED** (adopted, sometimes amended) · **ALREADY BUILT/CANON**
(no change; receipt cited) · **REJECTED** (with the receipt that kills it) ·
**NOTED** (not adjudicable yet).

The two reviews disagree with each other on the single most decision-relevant
internal number (see A6 vs B1) — which is itself a finding: the cross-arm
replay is the only thing that settles it, and it is queued.

---

## Highest decision impact: two factual defects, both real

**A1 — "2026-08-21 is Friday, not Thursday." CONFIRMED.** Checked against the
calendar (Aug 18 = Tuesday). The operational sequence is Wed 08-19 Night 3 ·
Thu 08-20 Night 4 · **Fri 08-21 first resolutions**. Fixed in
`docs/HANDOFF_2026-08-19_SESSION_START.md` (six occurrences) and in
`scripts/dress_rehearsal_0821.py`, whose operator-facing prints told the
person running the rehearsal that "Thursday's sequence runs." An erratum is
recorded in the handoff's own failure ledger: the retrospective about
eliminating the stale-summary failure mode shipped carrying it.

**A2 — "The brief pairs the pre-recovery TAQ split with n=182." CONFIRMED.**
Ground truth is `docs/TAQ_COST_CALIBRATION.md` items 1/13 and
`docs/SESSION_2026-08-18_EVENING.md` §"Resolved the same evening": after the
GOOGL/CMCSA re-pull the split is **16 below / 137 inside / 29 above of 182
retired names** (median 2.726bp one-way). The brief said 15/136/29 (= 180)
against "182 tickers". Fixed in the brief and the handoff before any further
external consumption.

---

## Reviewer A (long review + draft Order 20)

**A3 — "IIF ops must stop determining the research engine's development
order." ACCEPTED as a standing rule.** This is Order 17's own words ("IIF =
bounded ops track, the research engine is the bandwidth") — the review's
service is noticing the last two days drifted from it. Order 20 §RESULTS
makes it enforceable: session reports open with RESULTS PRODUCED, not
INFRASTRUCTURE BUILT.

**A4 — "Start the integrated AEGIS-NET experiment now." ACCEPTED, amended by
canon §6.** The tournament does not run before its pre-registration is signed
(attended). What starts now is the draft, the panel materialization, and the
coverage audit — all admissible tonight. "Now" means "not gated on IIF
resolutions", which is correct: the tournament touches no reserved window.

**A5 — Competing-risks/hazard formulation for the barrier head. ACCEPTED
into the prereg draft.** Genuinely new this round, cheap, and correct: the
label already carries `days_to_barrier`; a three-class classifier throws that
away, and `neither` is censoring, not a loser class. Enters the tournament as
a baseline family (cause-specific hazards for upper/lower barrier vs
fixed-horizon multinomial). The survival machinery (lifelines, Cox) already
exists in-repo.

**A6 — The 14-point mirror gap attributes to EQUAL WEIGHTING, and A treats
it as the biggest internal diagnostic. CONFIRMED as our own finding** (brief
Q6 states it); the cross-arm replay (conviction book × mirror weighting and
vice versa, same rebalance schedule, then timing/exits one at a time) is
queued and is the next cut. A's "dissect every basis point now" is accepted —
with the standing caveat that 70 days licenses mechanism attribution, not a
verdict on anyone's skill.

**A7 — "95 years must stay a claim-specific power calculation, not
doctrine." ALREADY CANON, worth restating.** §58/§59 derive it for one claim:
+3%/yr terminal-return on a co-moving equity slice. Canon §59's actual rule
is "choose the outcome before concluding the question is unanswerable" —
which is the opposite of doctrine. Any quote of the 95-year figure carries
its scope.

**A8 — "k_eff ≈ 1–2 for eight books should be measured, not assumed."
ALREADY CANON.** ρ̄ is `MEASURED` or `DECLARED_CONSERVATIVE`, no third branch;
§58 measured 1.81/block for the eight-ETF panel. Any new panel measures its
own.

**A9 — "The PC should work constantly on *distinct* questions; bootstrap
tells you about the estimator, not the world." ACCEPTED; matches mission
rule 5 and the shared-resamples lesson** (unpaired ρ̄ 0.002 vs shared 0.920 —
it was measuring the RNG). The daemon's admissibility rules (reserved
windows refused at submit, priorities frozen at submission) are the
implementation; Order 20 gives it its first real queue.

**A10 — PURE-NEWS-RESIDUAL-1. ACCEPTED as the round's best new import.**
Tagged `hypothesis_source` (§61: caps the claim at
ADAPTIVE_HISTORICAL_VALIDATION), pre-registered before accrual, and gated on
a PIT-clean news representation — the expected-news model must be trained
strictly before each article's timestamp or the residual is contaminated by
construction. Kill: residualized news fails to beat raw-news and no-news
baselines under identical folds/MDE.

**A11 — IMPLIED-REVISION-1. ACCEPTED with its own data gate, expected
SHELF.** PIT analyst-report text is the binding input; the catalogue-vs-
entitlement lesson (`ibes.det_guidance`) says verify entitlement by probe
before any build. A's own rule stands: no PIT text ⇒ SHELF immediately, no
approximation with current reports.

**A12 — The remaining hypothesis families (processing-gap, options/equity
dislocation, reaction-gap, news×flow, sequence-of-evidence, disagreement,
half-life, cross-entity-lag). ACCEPTED as daemon candidates**, each through
`pre-register-trial` with its corpse named (G5 for anything conditional;
MARKET-GRAPH-1's closed minimum-variance route for graph work; the dead
target-level corpse for anything analyst-flavored). Priority is set by the
daemon's frozen scoring, not by review enthusiasm.

**A13 — Bloomberg facts. ACCEPTED.** 2023 HKU global win and the 2025 window
(Oct 13–Nov 14) are documented; **no 2026 window is verifiable as of
08-18** — matches our UNVERIFIED stance. BLOOMBERG-CHALLENGE-SIM-1 enters as
P2 with provisional parameters replaced on publication, and the standing
rule that production Aegis is not tuned to contest incentives.

**A14 — "conviction −2.9%" (A) vs "−2.6%" (brief). NOTED.** Lane NAV is a
dated quantity; both numbers can be true on different read dates. The object
is the ~14-point gap, and the autopsy replays from the NAV tables, not from
either summary decimal.

---

## Reviewer B (architectural)

**B1 — "The optimizer is losing to naive EW by 14 points ⇒ error maximizer;
fix with Ledoit-Wolf shrinkage." REJECTED as a misreading of the finding.**
The finding is the reverse: the **equal-weighted arm is the one 14 points
behind**, and the first autopsy cut attributes the gap to equal weighting,
*not* the optimizer (brief Q6, Order 19). There is no covariance estimate
inside equal weighting to shrink; Ledoit-Wolf is also already available in
the stack (PyPortfolioOpt) for the lanes that do optimize. Adopting this
remedy would have "fixed" the lane that isn't broken. Kept only as: the
cross-arm replay must report turnover per arm (B's transaction-cost
intuition is right to demand it).

**B2 — "Decompose the Brier via Murphy on resolution day." ALREADY BUILT,
and AMENDED by the read gate.** The grader has had BSS vs PIT climatology +
Murphy decomposition with night-as-the-unit since before the first
resolution. But Friday licenses **resolution mechanics only** — the paired
contrast read is licensed at 40 graded nights, and `MODE_POWER` deletes
outcome fields rather than promising not to read them. Murphy on the H1
contrast happens at the licensed read, not Friday.

**B3 — Fault-injection test of the night pipeline (network drop, corrupted
feed ⇒ halt, not partial accrual). ACCEPTED as a bounded ops job.** Pieces
exist (derived refusals, canaries, the network-blocked test world); what's
missing is an injected-fault test of the *sequence* — the dress rehearsal's
lesson applied to failure paths.

**B4 — Satellite nightlights / port congestion data. REJECTED on the
daemon's own score.** No entitlement, heavy ingestion build, and it feeds
the crash-model track, which is not the binding constraint. Fails
`P(changes the roadmap) × value − cost` at current priors.

**B5 — Form 4 × predicted-variance conjunction. NOTED as a registrable
hypothesis.** The insider signal exists (`insider_trading.py`); the
conjunction claim goes through prereg like everything else.

**B6 — Single-fault injection for the cancelled-errors class. ALREADY
CANON** ("test comparisons on constructed inputs; assert the real thing in
BOTH worlds"), applied to the serial guard in the O19 evening work. The
principle is restated in Order 20's ops section because B is right that this
class is the most dangerous.

**B7 — Quoted→effective ratio drift under regime shift. ACCEPTED into the
Holden–Jacobsen join spec** (already the named next daemon job): the join
ships with a recalibration cadence and a drift check, not a one-shot ratio.

---

## Reviewer C (next-steps tables)

**C1 — "Run a resolver dry-run tonight against mocked records." ALREADY
BUILT, stronger than requested.** `scripts/dress_rehearsal_0821.py` (Order
18 §3.2) runs the full four-stage sequence on a copy with fabricated prices
drawn at the measured base rate, and **hashes the real ledger before and
after — the rehearsal fails if they differ**. Separately,
`scripts/campaign_resolution_readiness.py` answers what `--dry-run` cannot
(it stops before price fetch). C's instinct was correct; the build predates
the advice.

**C2 — "Screenshot the unanswerable cell at signing." NO CHANGE NEEDED.**
`NOT_ANSWERABLE_AT_N` is recorded machine-readably at reservation time and
committed — stronger evidence than a screenshot. Harmless if Murat wants the
visual for the signature commit.

**C3 — "Check pairing integrity and timestamp coherence before P&L."
ACCEPTED IN SPIRIT; enforced harder than requested.** The registered read
gate makes the P&L-first mistake structurally unavailable on Friday: nothing
beyond resolution mechanics is readable before 40 nights.

**C4 — "Commit a pre-mortem: if edge < −1% we don't tweak." SUPERSEDED by
design.** The frozen surface cannot be tweaked mid-campaign, and the edge is
not readable at first resolution, so the temptation the pre-mortem guards
against has already been removed by the read gate + freeze. Writing it
anyway would be a promise where a mechanism already exists.

**C5 — "Arm at 0.5: generate the receipt but pause for a Telegram confirm
before firing orders." REJECTED on a factual premise.** There are no orders:
nights collect forecasts and write receipts against paper lanes. The
graduated buffer already exists and is the acceptance test itself — 3
consecutive clean SCHEDULED receipts while unarmed, arming attended after.
Inserting a human confirm into the "unattended" state reintroduces the
attended property the test exists to retire (and "attended" is a property of
an action, not a topic).

**C6 — "Add max_quote_age_ms=500ms and recalibrate the band intra-day."
REJECTED as a scope error.** The TAQ panel is an offline daily-NBBO
calibration for a cost band applied to overnight-horizon paper forecasts;
there is no live execution path with 500ms exposure. The legitimate kernel —
quote staleness inside daily medians — is folded into the H-J effective-
spread join spec (B7) where it belongs.

**C7 — "Symbol survivorship audit (BRK.B etc.)." LARGELY BUILT.** The
sym_root probe established the 4-char rule (the hyphen convention is a
special case of it, not the rule); `taq_calibrate.py` exits 3 with a named
canary while any actionable absence remains; GOOGL/CMCSA re-pulled; the
remaining absences are classified (MMC unexplained · PXD delisted · SQ
trades as XYZ — a universe-staleness item already in the daemon queue).

**C8 — "Pre-build a cumulative Brier-vs-time-to-resolution dashboard before
Friday." REFUSED for now, kept for the licensed read.** Watching cumulative
Brier accrue by resolution time *is* the incremental peek the read gate
exists to prevent, and the "front-runs the close" inference needs the paired
design, not an eyeballed curve. Build it as a 40-night diagnostic.

**C9 — "Have the other AIs compute the microseconds of clock skew that flip
a 0.5bp edge." REJECTED.** Records are overnight h∈{1,5} probabilistic
forecasts graded on daily closes; the clock-skew scale that flips an outcome
here is hours (the two-clocks lesson), not microseconds. The brief's Q1/Q3
already point reviewers at the real weak links (variance estimator, quote-
trade alignment conventions).

---

## What this round changes

1. Two doc defects fixed before external consumption (A1, A2) — plus the
   same weekday error found and fixed in the rehearsal script's prints,
   which no reviewer saw.
2. The NET tournament prereg draft gains a competing-risks head (A5).
3. PURE-NEWS-RESIDUAL-1 enters as the top new P1 import (A10);
   IMPLIED-REVISION-1 enters gated, expected SHELF (A11).
4. Order 20 issued: RESULTS-first standing rule, tonight's admissible
   background queue, and the rejected list recorded so dead remedies don't
   get re-imported next round.
5. The B1-vs-A6 contradiction is itself logged as the reason the cross-arm
   replay outranks every other autopsy: two competent reviewers read the
   same 14-point gap in opposite directions; only the replay settles it.

---

**ERRATUM (added 2026-08-18 late night, grind session).** B1's supporting
sentence — "the equal-weighted arm is the one 14 points behind" — quoted the
live lanes as if the gap's mechanism attribution were settled. The cross-arm
replay (`docs/conviction_replay/LANE_AUTOPSY_CROSS_ARMS.md`) found the
authoritative conviction NAV diverges from YAML-seed buy-and-hold by up to
11.2% in discrete jumps, and the live mirror lane sits ~27 points below its
own rules replayed on the current book — so NEITHER circulating reading of
the 14-point gap (A6's or B1's) is reconciled. The B1 rejection stands on
its other leg (no covariance estimate ever ran; HRP fell back to equal
weight at the 252-day gate). The positions read (attended,
lane-integrity-check) decides the rest.

— brain, 2026-08-18 night
