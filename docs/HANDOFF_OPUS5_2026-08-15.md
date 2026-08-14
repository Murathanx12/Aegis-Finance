# HANDOFF — Fable → Opus 5, written 2026-08-14 (for the 2026-08-15 session)

**Author: Fable (brain). Executor: Opus 5 (builder). Ratifier: Murat.**
This document is the binding work order for the next session. It supersedes
`HANDOFF_OPUS5_2026-08-14.md`, whose milestones all shipped. Read
`IIF1_PRE_NIGHT_1_CHECKLIST.md` and `TEACHER_LIBRARY_COPY_LAB.md` before
touching anything they govern.

---

## 0. Verified state at handoff (checked live, 2026-08-14 ~13:15 UTC)

- Both repos clean and pushed: `aegis-finance` @ `250dc3f`, `Aegis module` @ `4cc308d`.
- Deploy live on `250dc3f`, all 10 lanes NAV-fresh through 2026-08-13, scheduler
  6/6 jobs, FRED 23/23 series (ICSA recovered), yfinance 23/23.
- IIF-1: **armed, 0 valid graded nights.** Night 1 VOID after $0.066464 /
  224 calls / 34 min — the information guard stopped it after 5 consecutive
  barren B_tools cells. This is machinery working. Accrual has not started;
  the read-schedule clock is untouched.
- COPY-LAB: seeded (2 lanes live, 12 declared inactive), **no production
  collector** — it cannot accrue new teacher signals yet.
- Balance: $37.05. First forward resolutions: **2026-08-16, attended.**

## 1. Review verdict

Operationally the 08-14 session was the best of the arc. Scientifically the
brain did not advance: zero valid graded nights, zero resolved forward
predictions, COPY-LAB structurally correct but input-starved. The honest
one-line state: **research machinery strong, research evidence early,
investment intelligence still weak, and systematic learning-from-mistakes is
now the architecture problem.** Murat has read the arc, agrees with the
direction, and issued a directive this handoff digests into rulings below.

New defects found verifying the record for this handoff (none previously logged):

| # | Defect | Where | Severity |
|---|---|---|---|
| D1 | On-disk void receipt says `spend_usd: 0.0`; true cost $0.066464 lives only in telemetry | `backend/data/optimus/iif1_nights/2026-08-14.json` | Known, ordered fixed (Order 1) |
| D2 | `llm_calls.jsonl` contains **3 unparseable lines** out of 43,020 (truncated JSON fragments, e.g. `"1.0.0"}`) — a cost/audit ledger that silently loses rows is the exact silent-fragility shape | `backend/data/optimus/llm_calls.jsonl` lines 5910, 7198, +1 | NEW — Order 1 |
| D3 | Receipt rows for barren cells carry `status: no_forecast, error: ""` — the closed drop-reason vocabulary exists but **is not surfaced per-row**, so diagnosing a barren cell requires a manual join against `llm_calls.jsonl` | `iif1_nights` receipt schema | NEW — Order 2 |
| D4 | Deploy warns: container-local ledger holds **19,961 records absent from the persisted ledger** at `/data/optimus/predictions.jsonl` (which holds 112). The migration guard correctly refused to copy; nobody has adjudicated what those 19,961 rows are | `belief_state` startup warning | NEW — Order 3 |
| D5 | README overclaims: line 70 "forward trial LIVE", line 133 "Forward trial live", line 134 "paper copy-lanes accruing 🟢" | `README.md` | Known, ordered fixed (Order 1) |

## 2. Rulings (RATIFIED — Murat's directive of 2026-08-14, digested)

**R1 — Funding rule APPROVED.** If the first VALID night measures **≤ $0.60
all-in**, the 40-night IIF-1 accrual self-funds from the current balance with
no further asks (worst case ≈ $24). Above $0.60, the top-up decision goes to
Murat. Murat has additionally removed top-up friction ("don't worry about the
cost, I will top up") — this changes the *escalation cost*, not the
discipline: the $12/night ceiling stays armed, the $0.60 rule stays the
automatic/attended boundary. Money is never the excuse for skipping a gate.

**R2 — The Research Gym charter.** Historical data is hereby designated the
**Gym**; forward data is the sole **certification** surface. Inside the Gym,
aggressive search is licensed: thousands of policy variants, counterfactual
replay, evolutionary mutation, deliberate overfitting to study *what*
overfits. Three hard walls:

1. **Nothing inside the Gym is evidence.** No Gym number may ever appear in a
   README claim, a track-record surface, or a funding argument. Gym output is
   hypotheses, not results.
2. **Every search leaves a lineage row.** One adaptive-search ledger per Gym
   campaign: candidate N exists because candidate N−1 failed in a recorded
   way. Un-ledgered searches taint the campaign (§20 applies to the Gym).
3. **Export requires transfer + prereg + forward.** A mechanism leaves the Gym
   only by (a) surviving transfer tests on slices that generated none of the
   hypothesis, then (b) a frozen pre-registration, then (c) forward
   certification. The episode/period that inspired a rule is **barred from
   proving it.**

This reconciles "pre-register or it didn't happen" with 100,000 backtests:
the *Gym campaign* is the registered trial; its internal variants are
ledgered, not individually pre-registered, and are never citable.

**R3 — The Decision Episode is the canonical learning record.** Every
important decision (historical or forward) becomes an episode: full PIT state
at decision time, beliefs (P(up), P(|move|>3%), vol/drawdown/rebound
estimates), the action taken, the stated reason, and — in the Gym — the full
counterfactual response surface (HOLD / SELL 25/50/100 / BUY / delayed
re-entry / drawdown-triggered re-entry / vol-reversal re-entry / hedge /
scale-in). Record the **whole surface**, never just the best answer.

**R4 — Failure attribution taxonomy.** Every resolved bad episode is
classified: forecast failure · action-mapping failure · timing failure ·
sizing failure · regime-transition failure · concentration failure · cost
failure. The prize insight this enables: "perception was correct; the policy
layer converted it into the wrong action" — which is exactly what the timing
backtest already shows (stress detection real; stress→zero-exposure mapping
wrong; 28.6% sell hit rate vs 67.4% buy).

**R5 — AUTOPSY → HYPOTHESIS → RULE → TRANSFER.** Optimus performs the autopsy
on resolved episodes and emits *structured* hypotheses: contemporaneous
evidence, post-outcome evidence (kept separate), proposed mechanism,
executable rule. An explanation is never knowledge because it explains its
parent well. The rule is evaluated only on foreign crashes / stocks /
decades. If it only explains its parent event, it dies, and the death is
ledgered.

**R6 — Teacher Library epistemics: explicit vs inferred.** A Form 4 says an
insider bought; it does not say why. Optimus may *assemble* contemporaneous
evidence into an inferred hypothesis ("first open-market buy in 4 years,
stock −38%, revisions stabilizing → possibly unusual internal conviction")
and must label it INFERRED, never narrate it as the actor's stated reason.
Aegis then tests whether the inferred *mechanism* transfers (CEO vs CFO vs
director, clusters, post-drawdown first buys, 10b5-1 vs discretionary,
post-disclosure copyability). **Losers are studied with the same machinery as
winners** — otherwise this is reverse-engineered hagiography.

**R7 — World model, not an LLM-weighted action net.** The LLM does not author
weights. Division of labor stays: **LLM teaches meaning, market teaches
weights, Aegis judges truth.** WORLD-MODEL-v1, when it comes, is multi-task:
return distributions (1d/5d/20d/60d), P(up), P(|r|>3%), P(|r|>5%), forward
vol, max drawdown, rebound probability, regime-transition probabilities —
with a separate policy layer consuming those distributions. Self-supervised
representation learning is licensed for latent-state discovery (capitulation,
quiet accumulation, liquidity shock, recovery transition), but realized
outcomes supervise the heads. **Building it is NOT authorized this session**
(Order 7 gate).

**R8 — Historical data is contaminated and we say so.** We have tested
hundreds of hypotheses against most of the history; Optimus has read it; we
have read it. No "fresh historical test set" claim is ever made again. The
Gym/certification split (R2) is the *consequence* of this admission, and it
is why the machine-separated forward populations (CAMPAIGN_FORWARD vs
LIVE_FORWARD, never pooled) are the most valuable asset in the program.

**R9 — Gym optimizer objective.** The search never optimizes prettiest
Sharpe. Fitness is robustness: performance across independent regime slices,
cross-sectional breadth, parameter-perturbation stability, cost survival,
and P&L concentration penalties (an 800% COVID-only policy loses to a 250%
seven-slice policy). Matched controls ride along by construction.

## 3. Build orders for Opus 5, in order

**Order 1 — Operational truth (do first, small, finish completely).**
- Append-only cost amendment to the Night 1 receipt: measured $0.066464,
  source telemetry, amendment dated; original `spend_usd: 0.0` stays visible.
- UTF-8 pinned by a test on every receipt/ledger write path (the mojibake was
  a read-side cp1252 artifact — pin both sides).
- Repair policy for D2: a ledger-integrity check that counts unparseable
  lines in `llm_calls.jsonl` and fails loud above zero; quarantine the 3 bad
  lines to a sidecar with their line numbers, never silently drop.
- README truthfulness: line 70/133 → "armed — first valid night pending
  (0/40)"; line 134 → "paper lanes seeded — production ingestion pending."
- Acceptance: tests green, README diff shows exactly those claims weakened.

**Order 2 — Diagnose → rehearse → one paid retry (the ratified sequence).**
- Diagnose **B_tools 2/10** AND **A_snapshot 25/40**. Leading suspect from
  the prior session: a size bound expressed in percent where a fraction is
  required. The receipt rows won't tell you (D3) — join against
  `llm_calls.jsonl` on the barren cells (B_tools cells spent 7 calls + 7 tool
  calls each and emitted zero forecasts with `error: ""`).
- Fix D3 while you are in there: every receipt row carries its terminal
  drop reason from the closed vocabulary. A cell that dies silently is a
  defect even when the night succeeds.
- Pin the root cause with a test. Then the **full five-arm sandbox
  rehearsal**; the simulation must now model chains (the zero-yield gate
  cannot see a CHAIN — IIF-1 mints only after the last arm; this is the
  known simulation/reality divergence from Night 1).
- Only if rehearsal is clean: **exactly one paid night, hard stop.** If it
  voids again, the void reason is again the deliverable — diagnose, do not
  retry a third time without Murat's word.
- Apply R1: if the valid night comes in ≤ $0.60, print the funding
  declaration into the receipt and accrual proceeds without asking.

**Order 3 — Adjudicate the ledger divergence (D4).**
- Determine what the 19,961 container-local records are (era, populations,
  whether any are the 112 persisted rows' ancestors). Ruling options:
  archive-and-declare-dead, or merge under a dated migration receipt. The
  current state — a warning nobody reads, forever — is not a state.
- Constraint: the persisted ledger at `/data` stays authoritative; nothing
  is copied without a receipt.

**Order 4 — Verify the resolvers, don't assume them.**
- The 20:30 UTC `pi_ledger_resolve` run (04:30 Malaysia, Aug 15): verify the
  actual persistent-volume mutation and receipt **after** it fires. An
  unverified first scheduled run is the exact silent-fragility shape.
- Aug 16: first CAMPAIGN_FORWARD resolutions, **attended**, with
  `--population campaign_forward`, dated receipt, ABLATION_FWD /
  CAMPAIGN_FORWARD headline. The two forward populations are never pooled.

**Order 5 — Teacher Library ingestion before COPY-LAB is called alive.**
- Bulk Form 3/4/5 ingestion → forward collector → schedule it → **prove one
  real production collection cycle** (a receipt showing real events landing
  in prod, not a local dry run).
- Then CORPORATE_INSIDER_CLUSTER may receive new eligible events.
  ACTIVIST_13D stays blocked with its stated reason until 13D ingestion
  exists. No historical backfills; public-availability timestamps only —
  the existing refusals are correct, keep them.

**Order 6 — RESEARCH-GYM-1, phase 1 only: the episode substrate.**
- Implement the canonical `DecisionEpisode` schema (R3) and a
  `CounterfactualPolicyEngine` that replays a historical decision under the
  policy menu and records the full response surface.
- **Dataset zero: the failed timing backtest.** Dissect those exact episodes
  first — the 28.6%-sell-hit-rate SELLs. First question the engine must be
  able to answer mechanically: was each failure a forecast failure or an
  action-mapping failure (R4)?
- Every replay writes a lineage row (R2 wall 2). The campaign registers
  ONCE in the registry as RESEARCH-GYM-1 with its charter; internal variants
  are ledgered, not pre-registered, and are never citable (R2 wall 3).
- AUTOPSY-TO-RULE-1 (R5) starts only after episodes exist to autopsy — it is
  in scope this session *if* Orders 1–5 are done, otherwise it is the next
  session's headline.

**Order 7 — NOT authorized.**
- WORLD-MODEL-v1: blocked until the episode/counterfactual dataset exists
  and RESEARCH-GYM-1 has produced its first transfer-tested mechanism
  candidates. Do not scaffold it "while we're here."
- No new covariance descendants (GRAPH-COVARIANCE-1 closed the family).
- No pooling of forward populations. No reads of accruing trials
  (TRIAL-CONGRESS-IC etc.). No third paid IIF night without Murat.

## 4. The sentence to keep

The goal is no longer "make the backtest look better." It is: **can Aegis
explain why a decision succeeded or failed, generate the alternative actions,
extract a transferable mechanism, learn it numerically across thousands of
episodes, and then show it still works where neither Optimus nor the
optimizer has seen the answer.** Optimus stays extremely creative; Aegis
stays extremely difficult to convince. The Gym exists so both can be true at
full intensity at the same time.

— Fable, 2026-08-14
