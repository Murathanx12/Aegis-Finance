# PREREG — ABLATION-1: what does the language model actually add, and can a shuffled placebo produce the same thing?

**Registered 2026-08-12, GRAND-ARENA-1 chunk 9, BEFORE any historical LLM call
in this campaign is issued and before any ablated portfolio path exists.**
**Family:** component ablation / placebo-controlled architecture test.
**Grade:** split in two by Amendment A6 — `ABLATION-HIST` runs now and is
`ARCHITECTURE_RESULT_ONLY`; `ABLATION-FWD` accrues from **2026-08-16** and is
the only class that can ever certify. **ACCRUES ZERO ARMS.**

**This is the chunk the campaign exists for.** Chunks 3 and 7 exist to make it
possible. Its purpose is not to show that the language model helps. Its purpose
is to find out, with a ladder of placebos designed so that the flattering
answer is the hardest one to get.

---

## 0. Corpse check

`python scripts/lint_prereg.py TRIALS/PREREG_ABLATION_1.md`

- Resurrects: PREREG_LLM_AMNESIA_1 — new instrument: amnesia asked whether the model could be made to forget a name's identity; this asks whether its SEMANTIC CONTENT survives a distribution-preserving permutation of its own scores across ticker and date, which is a different null and needs no amnesia to be tested.
- Resurrects: PREREG_N4_LLM_VETO_CAL — new instrument: the veto trial graded a binary override on one book; this grades a continuous score inside a complete monthly-rebalanced portfolio against a six-arm placebo ladder and a risk-matched no-LLM twin.
- Resurrects: NIGHT-3 (LLM earns no role in stock selection, 16,320 decisions) — new instrument: that null was measured on the engine's own funnel with a single generic prompt and no placebo ladder. This runs a fourteen-role architecture reduced to five declared roles against a generic single agent, with shuffled and time-shifted controls that NIGHT-3 never had, and it is explicitly permitted to reproduce NIGHT-3's null.

**Standing:** a null here is a finding and is reported in the words Amendment A4
pre-declares, not softened.

---

## 1. The three outcomes, all publishable, written before the data

Amendment A4 fixes the wording so that it cannot be negotiated afterwards:

- **Full ≫ no-LLM**, surviving risk matching AND the shuffled placebo → *we have
  something.*
- **Full ≈ no-LLM** → **the LLM is currently presentation and research
  assistance.** Those words, verbatim.
- **Full < no-LLM** → the LLM layer needs redesign.
- **LLM helps only in a narrow domain or horizon** → **that is a success, not a
  consolation**: it tells us to stop asking it to do everything.

---

## 2. Hypotheses

**H1 (primary).** The Full system's net excess CAGR exceeds the no-LLM system's
by more than the MDE of the paired monthly difference, at the base position
budget, **after** the five A3 matchings.

**H2 (the decisive one, A4 arm 1).** Full exceeds **shuffled-LLM** — the exact
same multiset of scores and confidences, permuted across (ticker, date) — by
more than the MDE of that paired difference. *If Full ≈ shuffled, the model's
CONTENT is doing nothing and only its NOISE is moving weights.* Every other arm
is subordinate to this one.

**H3 (architecture).** The five-role specialist swarm exceeds one generic
DeepSeek agent by more than the MDE of that difference. *Directional prior:
LOW. Chunk 3 measured the fourteen roles at a mean pairwise probability spread
of 0.059 on 3,901 contested cells — largely one forecaster with fourteen system
prompts.*

**H4 (component ablation).** At least one single-component removal produces a
detectable degradation. Components, one removed at a time from Full: **LLM ·
news/event · geopolitical lens · revisions · options · regime state ·
WHY-MOVED experience · specialist reliability · quant signals · specialists
(replaced by one generic agent)**.

**H5 (information vs money).** The LLM score carries detectable cross-sectional
rank information about the forward one-month return (pooled per-date Spearman
IC against its own MDE) **and** that information converts into detectable
money. *These are reported as two separate results. NIGHT-9's standing rule
applies: a rank-IC result may NOT be used to corroborate a null money result,
and the converse is equally refused.*

---

## 3. The placebo ladder — all six arms, none optional

| # | arm | construction |
|---|---|---|
| 1 | **shuffled-LLM** | the observed scores and confidences, **exact same distribution**, permuted across (ticker, date) under a fixed seed. 200 permutations; the arm's statistic is the full permutation distribution, not one draw. **THE DECISIVE ARM.** |
| 2 | time-shifted LLM | each date's score vector applied to the eligible set **k months later**, k ∈ {1, 3, 12}. Preserves within-date structure, destroys the timing. |
| 3 | random-text | live DeepSeek calls whose snapshot is replaced by structurally-identical noise: same fields, same units, values drawn from the cross-sectional distribution but belonging to no security. Measures what the model says when it is shown nothing. |
| 4 | one generic DeepSeek agent | a single un-specialised analyst prompt, same contract, same parser, same ledger. |
| 5 | the specialist swarm | the five declared roles, aggregated with **neutral/equal** weights (A5). |
| 6 | Full Optimus | swarm + quant composite + regime + event, the complete system. |

Arms 4 vs 5 force the specialist architecture to justify itself. Arms 1 and 2
cost no vendor calls and are computed from the arm-5/6 outputs; arm 3 does cost
calls and is subsampled, with the subsample size declared in §5.

---

## 4. A6 — the verdict splits in two, and they are different evidence classes

**`ABLATION-HIST`** — runs now on CRSP 2002-2024 with historical LLM calls.
**Every result carries the label `ARCHITECTURE_RESULT_ONLY`.** The foundation
model may know later history; a good historical result is unfalsifiably
contaminated and certifies nothing. What it CAN do is compare architectures
against each other and against placebos under identical contamination — which
is exactly what an ablation is for.

**`ABLATION-FWD`** — the harness and accrual path are built now and left
**stated-empty**. It fills automatically as the swarm's 1d/2d/5d records resolve
from **2026-08-16**. **Its numbers are not fabricated, estimated, extrapolated
or previewed.** The report prints the date and the empty table.

---

## 5. The historical LLM panel — declared in full, including what was cut

Cost and wall-clock force a smaller panel than chunk 3's. Every reduction is
declared HERE, before any call:

- **Dates:** month-ends **2015-01-30 → 2024-11-29**, n = 119 (the last month is
  dropped because its forward return does not exist in the data).
- **Names per date:** **40**, drawn by a **seeded stratified sample across
  market-cap quintiles (8 per quintile)** from the eligible set, fixed by
  `default_rng(20260812)` before any score exists. Every system in the ablation
  chooses from these 40 and only these 40.
- **Roles:** **five** of chunk 3's fourteen — `company_fundamental`,
  `analyst_revisions`, `execution_momentum`, `geopolitical`, `skeptic`. Chosen
  to span the component ablations that must be runnable (revisions,
  geopolitical lens, quant/momentum, and the one role that can lower the
  panel's confidence). **The reduction from fourteen to five is a limitation,
  not a design improvement, and it is stated as one.**
- **Budgeted calls:** ≤ 24,000 swarm + ≤ 5,000 generic + ≤ 1,500 random-text.
  The existing `research_budget` governor (60,000 calls / $150 / 40% zero-yield
  brake) is **not modified for this trial**; if it refuses, the campaign stops
  and the refusal is reported.
- **Point-in-time enforcement:** the price panel is truncated at the decision
  date before any snapshot field is computed, via the existing
  `llm_swarm.snapshot_from_panel`, and the ticker shown is the CRSP ticker
  valid at that date. A no-lookahead perturbation proof is required to PASS
  before any score is used.
- **Ledger isolation:** historical records are written to a SEPARATE ledger
  file. They may never enter the forward ledger, whose first resolution is
  2026-08-16 and whose integrity this trial must not touch.

---

## 6. Ablation arms that CANNOT be run, declared now rather than quietly dropped

| arm | status | reason |
|---|---|---|
| no options | expected `DECLARED_NON_RUN` | there is no point-in-time options-implied panel joined to this spine; OptionMetrics files exist but are not linked into the arena cache, and inventing one is not permitted |
| no WHY-MOVED experience | expected `DECLARED_NON_RUN` | the experience memory is a forward artefact of 2026; there is no 2015-2024 memory to remove |
| no specialist reliability | expected `NULL_BY_CONSTRUCTION` | A5 fixes reliability at neutral/equal until forward records resolve, so removing it removes nothing. Reported as identical-by-construction, with the number printed to prove it |

**A check that did not run is not a check that passed.** Each of these is
printed in the report with this status and this reason.

---

## 7. The ruler

- Sampling unit: **the month** (n = 119 for the LLM panel).
- **MDE = 2.80 × max(Newey-West, IID) SE** of the paired monthly difference,
  annualised, per CANON §19. Below its MDE is NOT DETECTABLE and never a kill.
- The shuffled arm additionally reports an exact **permutation p-value** over
  200 seeded permutations, because a permutation test needs no distributional
  assumption and is the natural instrument for arm 1.
- **§20:** the effective number of distinct ideas is computed for every LLM
  arm with the same rule chunk 3 used, and every claim about the swarm is
  divided by that denominator, not by the raw call count.
- **§18:** "the swarm beats the generic agent by more than quant beats random"
  is tested as a difference-of-differences with its own SE and MDE.

---

## 8. Decision rules — frozen

| outcome | condition |
|---|---|
| `LLM_ADDS` | H1 and H2 both clear their MDEs, sign consistent in ≥5 of 8 regime blocks and both halves, and survives all five A3 matchings — and even then it is `ARCHITECTURE_RESULT_ONLY` |
| `PRESENTATION_AND_RESEARCH_ASSISTANCE` | Full ≈ no-LLM within the MDE **or** Full ≈ shuffled within the MDE |
| `LLM_SUBTRACTS` | Full − no-LLM detectably negative |
| `NARROW_DOMAIN` | detectable in a pre-declared subset (size quintile, horizon, or sector) and not overall — **reported as a success** |
| `NOT_DETECTABLE` | below the MDE; reported with the MDE, never as a kill |

**A11:** only outcome `LLM_ADDS`, surviving risk matching AND the shuffled
placebo, may be called a breakthrough — and one spectacular backtest is
explicitly not sufficient.

---

## 9. What this cannot tell us, written before the answers

1. **`ARCHITECTURE_RESULT_ONLY`.** Historical LLM reasoning cannot certify
   alpha. Whatever the numbers say, they compare architectures under shared
   contamination.
2. Five roles, not fourteen. A null on five roles is not a null on the full
   swarm, and the effective-distinct-ideas ratio is reported so the reader can
   see how much independence was ever there.
3. 40 names per date. The portfolio comparison is UNDERPOWERED by construction
   and its MDE will say so in numbers; the cross-sectional information test is
   the powered one, and the two are never merged.
4. One vendor, one model family. This is a test of DeepSeek-as-configured, not
   of language models.
5. A component whose ablation is not detectable is not thereby shown to be
   useless — it is shown to be below this instrument's resolution, and the MDE
   states how large it would have had to be.
