# MODEL-ORCHESTRATOR-BENCH-1 — Fable 5 vs Opus, bounded

**Run 2026-08-12 (NIGHT-14).** Murat asked directly: *"I just want to compare if
fable worked better than opus for the credits that has been used."*

**Headline: at matched effort on this task class the two are indistinguishable
in quality. The benchmark saturated at both difficulty tiers. It therefore
CANNOT rank them, and the overnight-autonomy question Murat actually cares about
is not what this design measures.** Details below, including two places where my
own answer key was wrong and both models out-reasoned it.

---

## Design

Ground truth was written and sealed **before** any arm ran
(`scratchpad/bench_truth/`). Arms never saw it and were told not to read
anything but their task file.

**Tier 1 — 8 tasks.** Every one is a defect this programme actually shipped and
later found: the insider collector DOA on a 100%-null field under 12 passing
tests; the horizon-monotonicity clip; benchmark window truncation writing
permanent wrong outcomes; a 14-way tie published as a ranking; the
percent-vs-fraction threshold that produced six guaranteed-wrong records; the
rolling-deploy jobstore that ate a scheduler job; the fake-NAV cost-basis
fallback; and a below-MDE kill. Using real defects means the benchmark cannot be
dismissed as artificial.

**Tier 2 — 6 harder tasks**, built after tier 1 saturated. Contains a **trap
with no defect at all** (a Merton jump-diffusion that looks like it is missing
its compensator but is fully correct), items whose obvious answer is a
distractor, and items requiring arithmetic rather than gesture.

Arms: `fable_A`, `fable_B`, `opus_A`, `opus_B` on tier 1; one each on tier 2.

---

## Results

### Tier 1 — total saturation

| Arm | Mechanism score | Format compliance |
|---|---|---|
| fable_A | **8 / 8** | full |
| fable_B | **8 / 8** | full |
| opus_A | **8 / 8** | full |
| opus_B | **8 / 8** | **dropped the required Confidence field on all 8** |

Effort was near-identical: 50.7k / 50.2k tokens for Fable, 50.5k / 49.6k for
Opus; 84–97 seconds; 2 tool calls each.

**A tier where every arm scores full marks has zero discriminating power.** The
one asymmetry is format: 3 of 4 runs followed the output contract, and the
deviation was Opus's. At n=2 per model that is an anecdote, not a rate.

### Tier 2 — also saturated, but the arms got there differently

| Arm | Score | Trap (H1) | Effort |
|---|---|---|---|
| fable | **6.0 / 6.0** | correctly **NO DEFECT** | not measurable — see below |
| opus | **6.0 / 6.0** | correctly **NO DEFECT** | 78.0k tokens, 441s, 9 tool calls |

Neither fell for the trap. Both correctly identified that the Merton
compensator IS present, that the compound-Poisson jump aggregation
`n*μ + √n*σ*Z` is exactly right, and that the "suspicious" reuse of `jump_mu`
in both the compensator and the jump mean is correct because it is the same
parameter.

The interesting difference is **method, not accuracy**:
- **Opus verified numerically.** It ran Monte Carlo to confirm
  `E[S_T] = s₀e^{μT}` across three parameterisations, and *simulated the H2
  leakage on pure-noise features* to show full-sample selection manufactures
  walk-forward AUC 0.58–0.65 versus 0.49 for correct nested selection.
- **Fable reasoned analytically** and reached the same answers with fewer tool
  calls, in roughly a fifth of the wall-clock on tier 1.

Both produced quantitatively identical conclusions where a number existed
(H3 true drawdown ≈ −16.5% vs −16.6%; H6 residual edge +3.5pp ≈ 0.50 SE).

---

## Two places my answer key was wrong, and both models beat it

This is worth more than the score table, because it is a measurement of the
*benchmark*, not the models.

1. **H3 direction.** My sealed key asserted the `cumsum` drawdown made the
   reported −0.18 "too good". That does not survive the arithmetic: if simple
   returns sum to −0.18, the compounded peak-to-trough ratio is
   ≈ exp(−0.1805) ≈ 0.835, i.e. about **−16.5%** — the reported figure is
   slightly **conservative**, not flattering. Both arms computed this
   independently and both got it right. I corrected the key *before* grading and
   recorded the correction in it.
2. **H4 "single most likely overturner."** My key named deflation against the
   cumulative trial count. Fable named the missing 2019–2026 holdout, arguing
   the hypothesis was necessarily formed in 2026 with post-2018 hindsight, so a
   0.4pp margin inside 1 SE rarely replicates. That is at least as defensible as
   my answer. **It was my opinion graded as fact**, which is a defect in the
   rubric.

A benchmark whose author is wrong twice out of fourteen items, and whose
subjects catch both, is not measuring what it claims with the precision the
score table implies. Recording that is the point.

---

## What broke: Fable ran out of credits mid-run

The tier-2 Fable arm **wrote its complete 6-answer file and then failed on its
next call: "You're out of usage credits."** So the answers are valid and graded,
but its token/latency figures are unrecoverable and no replication was possible.

This is directly relevant to Murat's question — he noted Fable "used all the
credits" — but it is an observation about *budget consumption over a whole
night*, which this benchmark does not measure and cannot attribute.

---

## What this can and cannot conclude

**Can:**
- On defect detection and statistical review, at both an easy and a
  deliberately hard tier, **quality is indistinguishable** (14/14 vs 14/14 on
  the paired items).
- Neither model false-alarms on a clean implementation — both passed the
  no-defect trap, which tier 1 could not test.
- On tier 1, token consumption and latency were **near-identical**. Where
  quality and token use match, the cheaper model is the rational default and the
  more expensive one has to earn its premium somewhere this benchmark does not
  look.

**Cannot:**
- **Rank them.** Both ceilings mean the instrument has no resolving power here.
  Reporting a winner from 14/14 vs 14/14 would be exactly the below-MDE
  reasoning that H8 exists to catch, and doing it in the writeup of a benchmark
  containing that item would be embarrassing.
- **Say anything about whole-night autonomous research**, which is what Murat
  actually buys. That has n=1 night per model, no controls, and different tasks
  each time. NIGHT-13 (Fable) versus any Opus night is **not a comparison**.
- **Settle cost.** Per-token prices quoted in the external review are unverified
  here. Token counts are reported above so the conclusion can be recomputed when
  the real rate is known.

## What would actually answer the question

A harder tier that does not saturate — the obvious direction is tasks with **no
known answer**, scored on whether the finding survives adversarial verification,
since both models are at ceiling on tasks with one. Plus matched multi-hour
autonomous runs on equivalent-but-disjoint work, scored on defects introduced,
silent defects caught, and licensed findings per dollar. Both are multi-night
builds.

## Practical reading for now

Use Opus as the default and Fable where a long autonomous run is the job — which
is roughly what Murat already does ("normally if I have to do a research etc I
use opus and fable for the brain"). **Tonight's evidence does not contradict
that split, and does not confirm it either.** It rules out one thing only: a
large per-task quality gap in either direction on this class of work.
