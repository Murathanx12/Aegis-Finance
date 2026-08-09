# DESIGN ADDENDUM 2026-08-09 — the EXPERIENCE object and the two memories

Addendum to `docs/DESIGN_DAILY_LEARNING_LOOP_2026-08-08.md`. Adopted from
Murat's home-session review of external AI feedback, adjudicated 2026-08-09.
**Supersedes** the lighter "lesson record" described in the NIGHT-3 prompt.

Binding context that does NOT get rebuilt: masking is measured-valid
(AMNESIA — 0/240 identifications, synthetic ≈ masked ΔBrier 0.0004,
instruction-based forgetting does nothing); `aegis_brain/abn/` is the semantic
memory and calibration layer; holdout refusal is coded and tested; canon
unchanged — the LLM never grades itself, no posterior touches position sizes,
pre-register before compute.

---

## 1. EXPERIENCE — the canonical unit of learning

One record per **graded decision**. Not per event, not per claim: the thing we
want to learn from is a decision that had a consequence.

| field | meaning |
|---|---|
| `experience_id` | stable hash of (information_state, decision, model_id) |
| `ts` | decision timestamp (simulated clock in replay) |
| `information_state_hash` | hash of everything the decider could see |
| `market_regime` | walk-forward label only — never fitted on the future |
| `fingerprint` | numeric features + event class; the kNN retrieval key |
| `model_id` | which model decided (DeepSeek, Claude, logistic, engine-only) |
| `brain_version` | which brain/prompt/spec produced it |
| `thesis` | enum set, not free text |
| `direction` | BUY / HOLD / SELL |
| `confidence` | elicited, pre-calibration |
| `expected_return`, `horizon` | the falsifiable part |
| `target`, `invalidation` | the exit conditions declared up front |
| `realized_outcome`, `abnormal_return` | what actually happened |
| `error` | realized − expected |
| `attribution` | enum: why it went the way it did |
| `outcome_class` | success/failure class enum |
| `lesson_text` | human-readable, never parsed by the engine |
| `embedding` | vector over the fingerprint, for retrieval |

Requirements: deterministic writer, loud failure on a missing required field
(never a silent default), unit tests, append-only.

**Why enums and not free text:** free text is ungradeable and invites the model
to narrate rather than commit. `lesson_text` exists for humans to read; every
field the engine acts on is an enum or a number.

## 2. Two memories, named separately because they must be ablatable separately

| | EPISODIC | SEMANTIC |
|---|---|---|
| what | the experience store | ABN posteriors + distilled generalizations |
| retrieval | kNN over situation fingerprints | claim-type posterior lookup |
| answers | "what happened the last time it looked like this?" | "how often is this KIND of call right?" |
| ablation arm | E | D |

**Hard rule — receipts or rejection:** a semantic generalization MUST cite the
`n` episodic experiences it was distilled from, and `n` is printed wherever the
generalization is shown. A generalization without receipts is **rejected at
write time**, the same way a claim without a `resolve_rule` is rejected today.
This is the mechanism that stops the brain from inventing folklore about
itself.

## 3. Decision persistence — how consistency is enforced, not requested

Every position and live candidate carries a persistent state object: thesis,
original probability, target, invalidation, evidence-for, evidence-against,
current probability, and the full belief history.

On every re-review the elicitation forces the schema:

> **OLD BELIEF → NEW EVIDENCE → BELIEF UPDATE → NEW BELIEF → reason enum**

Update-appropriateness is graded **deterministically**: did the probability move
in the direction the resolved evidence implies, and by a defensible amount?
Both failure modes are flagged — **overreaction** (moved far on weak evidence)
and **underreaction** (didn't move on strong evidence).

Never prompt "be consistent." Consistency that comes from asking is theatre;
consistency that comes from showing the model its own prior claim and grading
the delta is a measurement.

## 4. Policy-coherence battery — a cheap gate that runs BEFORE economics

Using the validated synthetic-scenario machinery, perturb exactly ONE variable
per pair and test pre-registered monotone response directions:

| perturbation | required direction of expected return / conviction |
|---|---|
| valuation cheaper / richer | up / down |
| earnings beat → miss | down |
| regime bull → bear | down |
| geopolitical risk up | down |
| analyst revisions up | up |

Report per-direction pass rates. **A reasoner that cannot keep its own
directions straight fails here, cheaply, before any return-based testing.**

This is a gate on the LLM layer. It is never evidence of alpha — passing it
means the model is coherent, not that it is right.

## 5. NAME-ONLY arm — measuring the contamination ceiling

AMNESIA already measured named / named+instructed / masked / synthetic. **Those
are not re-run.** One new arm is added on the same 120-situation set:

**NAME-ONLY** — real ticker and real date, minimal or no numeric data. It
measures what the model can do on memory alone. That number **is** the
contamination ceiling for any unmasked diagnostic we might ever quote.

Pre-registered, cache-keyed, small.

## 6. Anti-reward-hacking guard — on every decision arm

Alongside accuracy and Brier, every arm reports:

- **exposure** (fraction invested),
- **abstention rate**,
- **opportunity cost of abstention** (what the passed-on decisions did).

An arm that "wins" calibration by hiding in cash must be visible as exactly
that. This applies to **PF-META-1 too**: its scorecard must show time-in-cash.
*(Already measured for PF-2 — every meta book runs at 0.0% mean cash, so the
meta result is not a cash-hiding artifact. Receipt:
`runs/PF2/META_COMMON_WINDOW.json`.)*

---

## 7. REJECTED / DEFERRED — recorded so they are not re-proposed

| item | disposition | reason |
|---|---|---|
| Multi-agent personas (Analyst/Risk/Trader/Reflection debating) | **REJECTED for now** | risk limits and execution stay deterministic engine code; personas are unmeasured API-cost multiplication. May be registered later as a single-LLM vs role-ensemble ablation **only if** the single-LLM path first shows measurable value above baselines. |
| Ten new experimental paper accounts | **REJECTED** | the arms live inside the historical lab. Nothing seeds a paper lane except through the frozen graduation gates; the existing 10 lanes keep their clocks untouched. |
| Neural / learned representations | **DEFERRED** | until the experience database is large enough that shrinkage-based posteriors demonstrably saturate. Milestone condition, not a date: **> 100k graded experiences**. |
| P&L-learning arms | **DEFERRED to its own trial** | already queued as a separate registered trial (resolution-trained vs P&L-trained under leakage control). One campaign, one question — not folded into NIGHT-3. |

## 8. The experiment framing, unchanged

Same LLM, same information, **arm A (no memory)** vs **arms C / D / E**
(semantic / calibrated / episodic retrieval). Does the brain make the model
better — component-attributable, out-of-sample sequenced, locked final era
untouched.

If memory does not help, that is a publishable receipt, not a failed night.

---

## 9. AMENDMENT 2026-08-09 (evening) — elicitation resolution, measured

Added after `TRIAL-COHERENCE-BATTERY-1` and `DIAG-COHERENCE-RESOLUTION-1`.
Forward-only; it changes how future elicitations are written, and re-scores
nothing.

**Finding.** Asked for expected excess return as a decimal, `deepseek-chat` at
temperature 0 answers in coarse whole-percent steps. Across 500 single-variable
perturbation pairs it never once moved in the wrong direction — **0 wrong out of
500** — but it gave *identical* answers to both sides of a pair 115 times. Those
ties are what failed the coherence gate on valuation and earnings, the two
variables whose true effect over one horizon is smallest.

Re-asking the identical scenarios in **integer basis points**, with an explicit
note that 25 bp differences are meaningful, cut ties from 115/500 to 35/500 and
took the battery from 3/5 to 5/5 directions passing.

The same signature appears independently in `DIAG-NAME-ONLY-FORCED-1`: 120
probability elicitations produced **5 distinct values** spanning 0.35-0.55.

**Standing rules from this, binding on future elicitation design:**

1. **Ask for integer basis points, not decimals**, for any quantity whose
   interesting variation is smaller than a whole percent. Say in the prompt that
   small differences are meaningful.
2. **Report output resolution as a diagnostic** wherever an elicitation is
   graded — number of distinct values, and their range. A model answering on a
   five-point grid cannot express a small effect, and any null result from it is
   partly a measurement failure rather than a finding about the world.
3. **Ties are not the same defect as reversals** and must never be merged into
   one "failure" count. A grader that cannot distinguish them will report a
   coherent model as incoherent, which is what happened here before the
   decomposition was read.

**What this does NOT do:** it does not re-score `TRIAL-COHERENCE-BATTERY-1`,
which was pre-registered with the decimal format and stands at 3/5, INCOHERENT,
prediction N3 MISS. A gate re-run in a friendlier format until it passes is not
a gate.
