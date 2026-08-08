# DESIGN — The Daily Learning Loop ("the brain that updates itself")

**Status: DRAFT design, 2026-08-08. Not a registration. Implements D3 from
`SESSION_HANDOFF_2026-08-08_NEXT_PHASE.md` and answers Murat's directive:
"how the LLM interacts with the brain to learn and build a NN in a way —
it should learn every day and update itself."**

---

## 1. The one constraint the design is built around

A real, excellent edge (~0.6 annualized Sharpe — better than almost every
fund) produces a daily return signal of roughly **+3–5 bps against daily
noise of 100–200 bps**. That is why SPY itself only prints t≈1.1 over 72
months, and why KTD-Fin measured 9/10 LLM agents that self-train on their
own P&L ending with *negative* selection alpha: at daily granularity, P&L
is almost pure noise, and anything that updates weights on it learns the
noise. **Daily P&L cannot be the teacher.**

But the system can still genuinely learn every day — because P&L is not
the only ground truth that resolves daily. **Predictions resolve daily.**
An event-direction call ("FDA approval → +5d abnormal return positive"),
a risk flag ("earnings this week, elevated gap risk"), a materiality call
("this news is noise") — these resolve in days, and the system makes many
of them per week. Hundreds of graded resolutions per month is real
statistical power. **The daily gradient comes from prediction resolution,
not P&L.** Money-grading stays on the lane/registered-trial clock, where
it has power.

## 2. The NN mapping (this is literally the architecture)

| Neural net concept | Aegis implementation |
|---|---|
| Neurons | Claim-types × context buckets (e.g. "FDA approval / small biotech", "insider cluster ≥3 / smallcap", "analyst PT raise / megacap", "geopolitical supply-chain event / semis") |
| Weights | Posteriors with uncertainty — Beta(α,β) for hit-rates, hierarchical Normal for effect sizes. Never point estimates. |
| Forward pass | Each morning: events → LLM emits structured claims → claims scored against current posteriors → daily brief ranks and confidence-labels everything |
| Loss function | Brier score / calibration error on resolved claims (never P&L) |
| Backprop | Nightly Bayesian update of every posterior touched by today's resolutions |
| Regularization | Hierarchical shrinkage: small-n buckets shrink toward their family prior, so an n=5 hot streak cannot dominate |
| Frozen output layer | Weights gate **information flow, confidence labels, and watchlist priority** — never position sizes. Capital changes only through registered gates and lanes. |

The brain's behavior genuinely changes every day — what it surfaces, how
confidently it speaks, what it tells Murat to watch — as a function of
graded experience. That is "updates itself," with the one connection that
is measured to fail (P&L → weights) left out by design.

## 3. Components

### 3.1 Claim ledger (append-only JSONL, hash-frozen per day)
Every LLM output that asserts anything about the future becomes a claim:

```json
{"claim_id": "...", "ts": "...", "type": "event_direction",
 "class": "fda_approval", "ticker": "XYZ", "direction": "+",
 "p": 0.70, "horizon_days": 5,
 "resolve_rule": "abn_ret_5d_vs_sector > 0",
 "provenance": ["8-K:...", "PR:..."], "abstain": false}
```

Rules:
- **A claim without a machine-resolvable `resolve_rule` is rejected at
  write time.** This is micro-pre-registration — CANON §6 at claim scale.
- The day's ledger file is hashed at close of emission. No retro-edits.
- The PDUFA ledger (7 calls, scoring ~Aug 24) is the working prototype of
  exactly this object.

### 3.2 Resolver (nightly, deterministic engine code)
Grades every matured claim against market data. **The LLM never grades
itself.** Callable entry point + unit tests (house rule for guards).
Outputs: per-claim outcome, Brier contribution, bucket assignment.

### 3.3 Posterior store (the weights)
Per claim-type × context bucket: hit-rate Beta posterior, effect-size
hierarchical Normal, n, last-update. Nightly update is the learning step.
Every save appends a diff line — "what the brain changed its mind about
today" — into the Optimus corpus, so the learning is inspectable.

### 3.4 Attention/routing layer (the forward pass consumer)
Daily brief v2 renders each claim with its bucket's live skill label:
- "This claim-type has hit 68% over n=41 [CI 53–80]" → surfaced with
  confidence, ranked high.
- "Unproven — n=6, CI too wide" → shown, honestly labeled.
- Demoted buckets get folded into the appendix, not silently dropped.

### 3.5 Attribution writer (the "why" with receipts)
Nightly decomposition of the day's lane/portfolio moves into computed
components (selection / timing / sizing / cost). The LLM writes the
narrative journal entry — "this worked because X" — but **every 'because'
must cite one of the computed decomposition numbers via enum**. Narrative
without a number is rejected (LLM narrates / engine computes).

### 3.6 Promotion gate (the bridge to money)
When a bucket's posterior clears a **pre-registered bar** (e.g. n ≥ 40,
calibration within band, effect-size CI excluding zero), it graduates to
a candidate for the registered ML track (EXT-ML-1) or a lane overlay —
via `pre-register-trial`, like everything else. This is the ONLY path
from daily learning to capital.

## 4. The daily cycle

**Pre-open:** collectors + EVENT-INTEL fire → LLM emits claims into the
ledger (or explicit ABSTAINs) → brief v2 renders holdings verdicts +
claims with posterior confidence labels.

**Post-close:** resolver grades matured claims → posteriors update →
attribution engine decomposes the day → LLM writes the journal entry
(enum-anchored) → brain diff lands in Optimus → tomorrow's forward pass
uses the new weights.

**Weekly:** reliability curves per bucket; promotion/demotion checks
against the pre-registered bars; calibration report into docs/.

## 5. Guards (the house failure modes, pre-empted)

1. **LLM never grades itself** — resolver is deterministic, tested.
2. **No claim without a resolve_rule** — rejected at write time.
3. **No posterior touches position sizing** — promotion gate only.
4. **Hierarchical shrinkage** — hot streaks at small n shrink to family.
5. **Coverage/abstain guard (the subtle one):** the LLM must emit a claim
   or an explicit ABSTAIN for *every* event its triggers fire on, and
   abstention rates are tracked per bucket. Otherwise it farms calibration
   by only claiming easy things. Selective claiming = the calibration
   version of look-ahead.
6. **Calibration graded out-of-sample of any recalibration fit** (existing
   canon rule, carried in).
7. Every component fails loud; silent no-op is the house failure mode.

## 6. What this answers in Murat's vision

- **"Think like an investor, not a statistician":** investors hold graded
  beliefs and update them on evidence. That is exactly what a posterior
  store is. Ideas are never binary-killed here — the kill machinery
  applies only at the money boundary. Inside the brain, everything is a
  weight with uncertainty that can rise as evidence arrives.
- **"We kill too many ideas":** claim-types that fail money gates keep
  their information posteriors. GP is the template: information-confirmed,
  money-unproven, still the best-evidenced candidate in the project.
- **"News to numbers":** every LLM output is a claim with a probability,
  a horizon, and a resolve rule — a number with provenance, never a vibe
  (D6, extended).
- **"NN that learns every day":** §2. Real weights, real daily updates,
  real behavior change — with the one measured-to-fail connection cut.

## 7. Build order (fits P1 as task 3, expanded)

1. Claim schema + ledger writer + reject-without-resolve-rule (small).
2. Resolver + 3 starter claim classes: earnings-direction, FDA/PDUFA
   (ledger exists), insider-cluster follow-through (collector exists).
3. Posterior store + nightly update + Optimus diff writer.
4. Brief v2 integration (confidence labels).
5. Attribution writer (needs P1 portfolio store first).
6. Promotion-gate spec → pre-registered before the first promotion check
   ever runs.

Priors for the starter classes should come from published event-study
effect sizes (research request R3) so day 1 is not flat.
