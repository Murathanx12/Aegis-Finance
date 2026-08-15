# ORDER — brain → builder, for the 2026-08-16 session

Binding. Single order — supersedes the "what needs you" lists in
`HANDOFF_2026-08-15_BUILDER_REPORT.md` and ingests the principal's review of
2026-08-15. Verified against code and production, not against any report.

---

## 0. Verified state

`aegis-finance` @ `a355fa6`+, clean, pushed. 4,153 tests green. Eight commits
landed 08-15. Deploy carries `f2c7b6b`+ (receipt enrichment live before the run).
`Aegis module` @ `f5367f0` (RESEARCH-GYM-1 registered once).

| | |
|---|---|
| M1 | **VERIFIED LIVE.** 2026-08-15T10:02:43Z, 163.7s. 1,252 index rows → 589 unique accessions → **589/589 fetched, coverage 1.000, 0 parse errors**. 593 SELL / 109 BUY / 1,044 mechanical. 525 actors, 317 tickers, 1,746 events. **Not the T9 shape — Railway's egress reaches EDGAR.** |
| M2 | **CORRECTLY NOT RUN.** 960 serial calls × 8.7s mean = 2.3h against a 13:30 UTC open. Refused in code (§39) before the first paid call. **IIF-1 still has ZERO valid graded nights.** |
| M3/M4/M5 | Complete. Three denominators, calibrated gate, autopsy→rule, 425-cell regret tensor. |
| T1 | Measured, **data-blocked** — median actor has 1 observation; 234 of 485 have exactly one. |
| T3 | Matched controls built *before* any winner exists to interpret. Correct order. |
| T4 | Deliberately deferred, reason recorded. Correct. |

## 1. Verdict

Accepted without reservation. Five defects, one shape: **a number that looked
like a measurement and was an artifact of what it was divided by, compared
against, or never multiplied with.** Regret against a best-of-17 had a +17pp
null; a 1.0pp gate convicted 93% of blameless holds; n=353 was n_eff 5.6; a
units error cost 75% of a findings table; a pre-open window could never have
finished pre-open.

Three of those were **false-kill machinery**, and that is the thread of this
order. The autopsy pipeline reported DEAD for fifteen cells it had never
evaluated — confident, plausible, and wrong in *the direction that looks
rigorous*, which is the hardest direction to notice.

Carry forward the result nobody asked for: **the 67.4% BUY hit rate scores
−0.57pp against simply holding.** A hit rate counts being directionally right;
it does not measure being *usefully* right. It belongs in the README beside the
sell-side number.

Both escalations were called right and are ratified below.

## 2. THE BINDING METHODOLOGICAL RULING — scope-aware verdicts

**Do not kill a broad idea because it failed in one environment.** This does not
lower the evidence bar. It narrows what a negative result is allowed to *claim*.

### 2.1 The defect, confirmed in code

`Autopsy` **requires** `expected_unaffected_states` — validated non-empty,
validated non-overlapping, written into `LineageRow.params["unaffected"]`.

`adjudicate()` **never tests it.** The verdict comes from `CH.request_export` →
`transfer.n_independent_slices_passed()`, a **flat count** of slices where
`passed` is true, with **no notion of which slices the mechanism itself declared
it should work in.** The unaffected list is documentation; it changes no outcome.

So a correctly conditional mechanism — real in its declared regime, correctly
silent outside — scores its silent slices as *failed* slices and is `REFUSED —
survived 1 of 3`. The machinery cannot distinguish *does not generalise* from
*is conditional, exactly as declared*. And it emits `DEAD` where §19 says
`NOT_DETECTABLE`, which is how 195 existing kills already became
absence-of-evidence.

**The discriminating half of every hypothesis is collected and thrown away.**
Firing everywhere is what beta does.

### 2.2 Scope is part of a hypothesis' identity

An idea is no longer a global object. It is:

`mechanism × environment × action × horizon × objective × universe × data_grade`

"De-risk when VIX is high" is not one hypothesis. These are four, and one can be
right while three are wrong:

- reduce exposure when volatility is high **and accelerating**
- increase exposure when volatility is extreme **but decelerating**
- reduce exposure on high vol **+ widening credit + worsening breadth**
- increase exposure after extreme stress **+ improving breadth + falling vol-of-vol**

### 2.3 The verdict vocabulary

Replace the flat pass/fail and the generic `DEAD`:

| verdict | meaning |
|---|---|
| `SUPPORTED_IN_SCOPE` | detectable evidence in the declared environment |
| `REFUTED_IN_SCOPE` | **powered** evidence against this exact rule in this environment |
| `NOT_DETECTABLE_IN_SCOPE` | ran, fired, below its own MDE — §19, never a kill |
| `UNPOWERED_IN_SCOPE` | too little effective sample to have resolved it |
| `UNTESTED` | never actually evaluated (vocabulary failure — already correct, keep) |
| `DATA_BLOCKED` | the necessary data does not exist yet |
| `CONDITIONAL_OPEN` | global result weak or null, state dependence untested |
| `TRANSFER_PENDING` | transferred partly, not enough |
| `STRUCTURALLY_CLOSED` | genuine impossibility only |

`STRUCTURALLY_CLOSED` is reserved for: mathematical impossibility · an oracle
establishing no economically meaningful headroom **in the same objective** ·
exact duplicate of a corpse · infeasible source · a fully powered exact rule
exhausted across its declared scope. GRAPH-COVARIANCE-1 qualifies; almost
nothing else will. **Only `REFUTED_IN_SCOPE` and `STRUCTURALLY_CLOSED` close
anything, and the first closes only its own scope.**

Every non-support carries **`revisit_when`** — the condition that would make
re-testing worthwhile (`n_effective > X`, the regime recurs, the corpus gains a
feature). A kill without a resurrection condition is how a project loses ideas
it never disproved.

### 2.4 Two guards so this does not become subgroup mining

**(a) §18 binds, and it is the load-bearing one.** *"Significant in A,
insignificant in B" is NOT evidence of conditionality.* Test the **A−B
interaction directly, with its own SE and its own MDE.** Without this, the
conditionality program becomes a machine for manufacturing regimes.

**(b) Post-hoc condition mining is not evidence.** The Gym may discover
conditional structure aggressively. Promotion still requires: Gym discovery →
explicit declared condition → foreign transfer → frozen prereg → forward.
Discovering a condition in the sample that suggested it confers **zero**
certification.

### 2.5 Scope-aware adjudication — what to build

- Label every transfer slice `AFFECTED` / `UNAFFECTED` / `OUT_OF_SCOPE` from the
  autopsy's **frozen** declaration, so labels cannot be chosen after results.
- Export requires **both halves**: clears MDE in ≥k `AFFECTED` slices **and**
  shows no detectable effect in `UNAFFECTED`.
- **Invert the sign where it belongs.** Failing in a declared-`UNAFFECTED` slice
  is **confirming**. Firing strongly there is **disconfirming** — the thing found
  is broader and dumber than the mechanism claimed. This makes the unaffected
  list a placebo family built into the hypothesis, which is what canon has always
  asked for ("carry your corpse as control") and has never had structurally.
- Emit an **effect surface** per mechanism, not a scalar: SUPPORTED_IN state A /
  horizon B, REFUTED_IN state C, UNPOWERED_IN state D. A mechanism may be
  positive in one state and negative in another. That is allowed.

### 2.6 Scope-aware corpse check — more precise, not weaker

- Exact failed rule → **blocked**.
- Same mechanism, identical environment, cosmetic threshold change → **blocked
  or resurrection tax**.
- Mechanistically distinct, **prospectively declared** state-conditioned
  descendant → **allowed as a NEW hypothesis, with the parent corpse as a
  MANDATORY control**.

Re-scope the existing register accordingly. Concretely: the 2020–2025 signal
mapping stays refuted; **state-dependent exposure control is not dead**. Direct
LLM stock scoring stays weak; LLM perception / event understanding / relationship
extraction stays open. Semantic graph → min-variance covariance stays
`STRUCTURALLY_CLOSED` in that objective; semantic graph → reaction propagation is
open. Mechanical trailing exits stay weak; state-dependent exit/re-entry is open.
Naive insider copying is **untested forward**; conditional actor surprise ×
role × state × disclosure lag is wide open.

## 3. Rulings on the escalations

### R10 — PARALLELISE THE NIGHT. Approved — but **after** §4/P2, not before.

Ratified in principle. The licence that covered `MAX_TOKENS` and cell-major
covers this identically: **zero valid nights have accrued, so there are no
results to change the rules after.** The scientific case is stronger than the
operational one — cell-major exists so the five arms see the same world, and
concurrency makes them *more* simultaneous, sharpening the primary contrast.
The operational case is that serial is fragile in a compounding way: 2.3h mean /
4.2h p90 against a 13:30 UTC open means a fraction of 40 nights self-refuse and
each refusal costs a calendar day.

**Design: cells stay sequential; the five arms within one cell run
concurrently.** This preserves the paired comparison and minimises information-age
skew. Binding conditions: one isolated chain cursor per arm, no mutable state
shared between arms, deterministic arm ids and cell ordering, async-safe
telemetry, **atomic** spend reservation and USD ceiling, bounded provider
concurrency, per-arm retry and rate-limit classification, per-arm start/end
timestamps, **max arm-start skew recorded per cell**, no evidence write until the
paired cell completes, symmetric drop policy, no arm sees another's result,
`B_anon` stays truly anonymised. Register execution mode and max concurrency in
the frozen surface **before** the first valid night. Build a known-response
concurrency harness first, then the full five-arm rehearsal concurrently.

**If concurrency is unsafe, do not force it.** Fallback: two-phase assembly —
slow immutable history prepared early, fast PIT finalisation immediately before
decision. Any cache must preserve `observed_at` / `public_at`.

### R11 — Reactive corpus expansion. Refusal UPHELD.

Right, and for the right reason. Replace it with **TRANSFER_ATLAS_V1**, defined
**once, before re-running anything**, applied symmetrically to all six existing
mechanisms and every future one. Generic economically-motivated axes (security
family · era · trend state · volatility state · drawdown state · liquidity ·
crisis vs ordinary · sector · cap class · rate/inflation regime where PIT-safe).
**Do not explode into thousands of tiny bins** — use partial pooling,
hierarchical models, continuous interaction terms, and print `n_effective` and
MDE on every cell.

### R12 — Per-actor Form 3/4/5 backfill. APPROVED.

The blocker is measured, not assumed: `P(action | actor history)` on a median of
one observation restates the action.

This is **Gym / baseline history** — a reference distribution, exactly like the
1990–2026 price history behind the base rates. It is **not** COPY-LAB history,
**not** forward performance, **not** a reconstructed paper track record. Enforce
in **code**, not convention: no signal derived from a backfilled event may enter
COPY-LAB or any forward lane; COPY-LAB's pre-inception refusal stays intact.

Prefer **official SEC bulk datasets** over millions of individual fetches.
Preserve: actor CIK · issuer · role · officer title · transaction code ·
BUY/SELL/mechanical · shares · ownership before/after · 10b5-1 tri-state ·
`filed_at` · `accepted_at`/`public_at` · `transaction_at` · accession ·
amendment status. PIT-safe throughout: an actor's baseline as of *d* uses only
filings public before *d*. **Never define "normal behaviour" using future
actions.**

## 4. Priority order

Do not start sixteen projects. This is the sequence.

**P0 — the conditionality standard (§2).** ScopedVerdict layer, scope-aware
adjudication, §18 interaction guard, scope-aware corpse check. Re-run all six
existing mechanisms through it and restate `RESEARCH_GYM_1.md`; report every
verdict that moves. **Blocks P6 and P8.**

**P1 — 2026-08-16 forward-evidence hygiene. ATTENDED. Date-bound, cannot slip.**
- **(a)** First `CAMPAIGN_FORWARD` resolutions — the first time in the program's
  history that reality grades a forward prediction. Dry run first. Record:
  records due · resolvable · unresolved · source availability · hash before ·
  hash after · dated receipt. `--population campaign_forward`. **Never pooled
  with `LIVE_FORWARD`.** Resolution is licensed; interpretation is not. **No
  interim slice mining for new hypotheses. No H1 read.**
- **(b)** `LIVE_FORWARD` quarantine. Preserve a byte-identical backup and
  SHA-256 receipt first. Move the 112 rows to
  `quarantine/campaign_copies_from_live_volume/<dated>`. **Do not destroy them.**
  Receipt states: 112 rows · source hash · destination hash · reason · campaign
  correspondence · **zero genuine live rows removed**. Then verify
  `pi_ledger_resolve` sees a clean empty live population rather than refusing
  forever on known contamination. Attended — it is irreversible and
  outward-facing.

**P2 — IIF decision-time semantics audit. Before any concurrency change.**
This is the order I did not write and the principal did; it outranks
parallelism because parallelism changes exactly these timings.

Assembly takes ~20 minutes. **Measure, do not assume:** `snapshot_started_at` ·
`snapshot_frozen_at` · `decision_ts` · max `observed_at`/`public_at` across all
snapshot inputs · per-cell start · per-arm start/end · tool retrieval timestamps.

The question: **does `decision_ts` represent the moment at which all information
in the snapshot was genuinely public?** If it is stamped at assembly *start*
while some observations are retrieved after it, that is a PIT defect and the
trial compares timestamp labels rather than information sets. Prefer explicit
`snapshot_started_at` / `snapshot_frozen_at` / `information_cutoff_at` /
`max_input_observed_at`, and enforce `every datum observed_at <=
information_cutoff_at`. Record real retrieval timestamps for tools. Commit the
audit and any fix before a valid night.

**P3 — IIF parallelism amendment, then ONE valid night.** Only after P2 is
green. Fresh snapshot, all timing assertions green, registered execution mode,
no post-open data, one attempt, hard stop. If VALID, accrual Night 1 starts —
**operational receipt only, do not read H1.** If VOID, the void reason is the
deliverable; do not immediately try a third architecture.

Budget is not a blocker. Balance ~$57.12, expected ≈$1/night against a $1.43
break-even. Keep the hard ceilings armed. **Escalate to Murat only above
~$2/night or on runaway spend** — the superseded $0.60 planning rule is not a
reason to stop useful research.

**P4 — collector idempotency (free, from tomorrow's overlap) → COPY-LAB
production wiring.** Verify duplicate accessions absorbed · TeacherEvents not
duplicated · amended filings still expressible · new events append · receipt
counts reconcile. **Idempotency is not established until a real overlapping
production cycle proves it.** Then wire `pi_ownership_collect` → TeacherEvent →
COPY-LAB eligibility → paper signal → next-session fill → NAV/receipt, and
**schedule COPY-LAB after the collector** so an empty collector run cannot look
like a healthy strategy run. `CORPORATE_INSIDER_CLUSTER` accrues **forward
only** — no pre-inception, no historical fills. Add `FORM4_MATCHED_CONTROL` as a
shadow lane: product telemetry, **not** a scientific verdict. Everything stays
labelled `PRODUCT_EXPERIMENT / NOT VALIDATED ALPHA`. `ACTIVIST_13D` stays
blocked until real 13D events exist.

**P5 — Form 4 backfill (R12) → Actor Surprise with partial pooling.** Do **not**
mint `CEO_X = 0.82` from three events. Estimate `P(action | actor history, role,
issuer context, market state)` with **hierarchical shrinkage**: rare actors
borrow strength from role / sector / action type / issuer state, high-history
actors earn individual weight. Features: first discretionary buy or sell in N
years · size vs own history · ownership-adjusted size · CEO/CFO/director ·
independent multi-insider cluster · opposing insiders · 10b5-1 status ·
post-drawdown action · earnings proximity · revision state · volatility state.
Build `ACTOR_SURPRISE` as a **feature**. No alpha evaluation until matched
controls and a prereg permit it.

**P6 — TRANSFER_ATLAS_V1 (R11), all six mechanisms symmetrically.** After P0.

**P7 — Known-answer worlds v1. Higher priority than before, because they now
protect against false kills as well as false discoveries.** Minimum set:
`WORLD-NULL` (vol clustering, no edge) · **`WORLD-CONDITIONAL` — positive policy
edge in state A, negative in state B, global average ≈ zero.** That world is the
critical one: the evaluator must **not** conclude "no edge"; it must recover
conditional structure. Plus `WORLD-EXPOSURE`, `WORLD-SELECTION`,
`WORLD-TEACHER-MAG`. For every world measure: false positive rate · **FALSE KILL
rate** · conditional-effect recovery · state localisation · MDE behaviour · scope
verdict. This is the entrance exam for AegisEvolve, RL, policy learners and any
world-model decision head.

**P8 — T4 state transitions, not levels.** After P0. The question: is the old
stress logic failing because it keys on **level** where the action should depend
on **transition**? Continuous features (VIX level, ΔVIX, acceleration, term
structure, vol-of-vol, drawdown depth and speed, breadth, credit, liquidity,
dispersion, correlation spike, trend, reversal, revision direction, event
proximity). Candidate states CALM / DETERIORATING / PANIC / CAPITULATION /
STABILISING / RECOVERY are **hypotheses, not labels of truth**. Baselines in
order: threshold → linear interaction → spline/GAM → LightGBM → HMM if
justified. **No neural model here.** Test interactions directly (§18); never
infer conditionality from two differing subgroup point estimates.

**P9 — Mechanism Graph.** Persistent structured mechanism memory: node
(id, description, economic rationale, originating episodes, affected states,
unaffected states, falsifier, precursor, **status by scope**, search lineage);
edges `SUPPORTS` / `CONTRADICTS` / `REFINES` / `CONDITIONAL_ON` / `GENERALISES_TO`
/ `FAILS_IN` / `TRANSFERS_TO`. A mechanism carrying "SUPPORTED_IN: stress
transition A, REFUTED_IN: calm, UNPOWERED_IN: crisis C" is worth far more than a
global scalar.

**P10 — REACTION-GAP-1, only if clean capacity remains.** Measurement study
only, no trading rule. Do not reopen covariance.

**Still gated: WORLD-MODEL-v1.** Authorised in principle; the
correctly-denominated-substrate gate was cleared 08-15. It may start only once
known-answer worlds demonstrate: planted global effects recovered · absent
effects not invented · **planted conditional effects recovered even when the
global average is zero** · acceptable false-kill rate. Then simple baselines
first (base rate → linear/logistic → GAM → LightGBM), only then self-supervised
representation and neural fusion. Yesterday's labels would have trained it on
inflated regret, false failure classes, bad n_effective and fabricated kills —
and it would have looked like it was working.

## 5. Process rule — check kills harder than passes

This session proved why. **A positive bug looks suspicious; a kill bug looks
disciplined.** Every `REFUTED_IN_SCOPE` or `STRUCTURALLY_CLOSED` gets an
adversarial check: did the rule actually execute · was the feature observable ·
was `n_effective` real · did the instrument have the MDE to see it · was the
control matched · did missing data become zero · did an exception become "did not
fire" · did global averaging erase opposite conditional effects · was the
environment inside the rule's declared scope.

No idea is protected from failure. **No idea is killed by a measurement that
never had the ability to see it.**

## 6. Standing

`GymResult.as_claim()` keeps raising. No Gym number is an alpha claim. 10 lanes
at 69 days against a 24-month floor — no skill claims. LLM spend is not the
constraint ($17.65 lifetime, **$0.00103 per structured autopsy**); schemas that
refuse untestable output are what convert spend into evidence, so build the
schema before buying the volume. **14.2% of calls still produce nothing
gradeable — measure that per arm before spending more.**

## 7. Report back

A. HEAD / tests / deploy · B. IIF — time-semantics audit, parallelism amendment
or refusal, measured latency, valid Night 1 status (operational only, no H1) ·
C. Forward evidence — campaign resolutions, live-ledger quarantine, collector
idempotency · D. COPY-LAB — wiring, eligible signals, fills, controls, no
historical fill · E. Teacher Library — backfill coverage, actor-history depth,
Actor Surprise availability · F. Conditionality — ScopedVerdict, corpse-check
changes, count of global vs `CONDITIONAL_OPEN` hypotheses · G. Transfer Atlas —
all six rerun symmetrically, scope matrix, no selective expansion · H. T4 ·
I. Known-answer worlds — planted effects, conditional recovery, false positives,
**false kills** · J. Mechanism graph · K. Defects found **by running checks** ·
L. Exact SHAs · M. Next bottleneck.

---

**The principle, stated once:** Aegis should be hard to convince — and equally
hard to convince that something is dead. A positive requires evidence. A
negative requires evidence. **A global negative does not answer a conditional
question that was never asked.**

This applies to the eventual model too. It should not learn one universal best
action. It should learn `P(outcome | state, action, horizon)` and then
`a*(s) = argmax_a E[U | s, a]` — so the question stops being *"does selling
work?"* and becomes *"in which states does selling, holding, adding, hedging or
replacing improve the objective, and how sure are we the current state is one of
them?"*

— brain, 2026-08-15
