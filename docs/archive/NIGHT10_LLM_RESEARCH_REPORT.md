# NIGHT-10 — the LLM as a research component, and what it actually produced

**Murat's ruling: $0 LLM spend is a defect from tonight forward. Budget $30.**
Spend: **$0.0067**. That is not frugality — it is what two DeepSeek calls cost,
and the finding below is why a third would have bought nothing.

Receipts: `docs/BUILD1/llm_ledger.jsonl`, `llm_hypotheses.json`,
`llm_hypothesis_diversity.json`, `llm_adversarial_review.json`.

---

## What was wired

`backend/services/llm_research.py` — five roles, a hard budget the code
enforces, and a ledger recording model, purpose, tokens, cost, output hash and
latency for **every** call including failures.

| role | run tonight | outcome |
|---|---|---|
| hypothesis generation | ✅ | 10 proposals, $0.0048 — see below |
| adversarial portfolio review | ✅ | 10 concerns, $0.0019, 2 landed |
| cross-source contradiction mining | ❌ | needs a per-name options/guidance panel that is not assembled |
| failure diagnosis + descendants | built, not run | no explore-stage failure to diagnose tonight that the engine had not already classified |
| structured extraction | ❌ | no historical LLM extraction exists, and generating one over 252 months reads the future of every month it extracts (NIGHT-3) |

Availability was verified live, not assumed: **DeepSeek returned 200**;
`ANTHROPIC_API_KEY` is present in `.env` but **empty (length 0)**, so the
Claude path was unavailable and no call was attempted against it. Temperature
is pinned at 0.0 — NIGHT-1 measured 21.6% answer flips at 0.7 on an identical
prompt, so anything above zero has to be a deliberate, stated choice.

---

## THE FINDING: ten hypotheses, one idea

The model was given the signal registry, the graveyard, and the data inventory,
and asked for **10 economically distinct mechanisms**, each naming its closest
existing corpse and why it differs. It complied: 10 proposals, every one naming
a corpse, every one implementable from data on disk.

**All 10 passed the corpse linter** against 306 prior experiments. Strongest
near-match to anything in programme history: **~0.23**, well under the 0.30
block threshold.

Then they were checked against **each other** — which nothing in the machinery
had ever done:

| | |
|---|---:|
| pairs among the 10 | 45 |
| pairs at or above the linter's **block** threshold (0.30) | **37** |
| pairs above the **warn** threshold (0.18) | **45 — all of them** |
| pairs at the duplicate threshold (0.60) | 0 |
| median pairwise similarity | **0.362** |
| **effective distinct ideas** (connected components at 0.30) | **1** |

**The ten proposals resemble each other far more than any of them resembles the
entire recorded history of the programme.** Every one opens "Trade the
cross-sectional drift in…", every edge estimate lands in 240–350 bps, every
turnover in 2–6×. It is one mechanism template in ten costumes, and each costume
passed the corpse check individually because they are all novel *in the same
direction*.

### The hole this exposed in the discipline machinery

`lint_prereg.lint()` asks *"has this been tried before?"*. It cannot ask *"are
these ten proposals actually ten ideas?"*, because it sees one document at a
time. A batch generated in one sitting passes proposal-by-proposal while
collectively being a single bet — and **the denominator that bet is scored
against is then wrong by the batch size.** A best-of-10 bar computed over what
is really one idea is not a bar at all.

`lint_batch()` was added and **calibrated before its verdicts were trusted**, as
the house rule requires:

| batch | verdict | distinct ideas |
|---|---|---|
| 8 real preregs from different families | PARTIALLY_REDUNDANT | **6 of 8** — and the only group it merged was `TRIAL-EVENT-13DG` + its two HARVEST variants, which genuinely are one family |
| the 10 LLM hypotheses | **SINGLE_IDEA** | **1 of 10** |

Cross-family pairs among real trials score 0.18 and below. The instrument
discriminates, so its kill on the LLM batch is trustworthy.

---

## The adversarial review

A separate pass — never the same call that produced the thing — was asked
"why is this portfolio probably overfit or wrong?". Ten concerns, of which
**two landed**:

1. **"The `tied_with` field is null for all names, but EXPD, INCY, NBIX, AAPL,
   AMZN all have exactly the same score."** Correct, and it caught a real
   staleness bug: the page had been generated before the tie-handling fix
   landed. Regenerated; ties now share a rank.
2. **"The scores are point estimates with no confidence intervals or standard
   errors."** Correct, and it is the same defect the power audit found in the
   research layer. The ranking score carries no standard error today.

Several were wrong. It read the `NO_EVIDENCE` names as padding added to inflate
the book, when they are printed precisely to show what the engine cannot speak
to; and it asked for a growth-index comparison for names selected on
profitability. **LLM output is a hypothesis, not a finding** — two of ten is a
useful yield for $0.0019, and the eight misses are the reason the rule exists.

---

## Answering the briefing's question 5

> **Did the LLM generate any genuinely new testable mechanism?**

**No — it generated approximately one, ten times.** The mechanism family
("cross-sectional drift after an observable event, delivered at 2–6× turnover")
is not new to this programme; it is the shape of a large fraction of the 195
closed experiments. What the exercise produced that *is* new is the measurement
that exposed it, and the batch-diversity gate that will catch the next one.

That is the honest yield of the LLM tonight: **not a hypothesis, but a hole in
the hypothesis-checking machinery.** The corpse linter has been checking
proposals against the past since NIGHT-8 and has never once checked a batch
against itself.

## What would change this verdict

* A **different prompt shape**. The model was asked for ten mechanisms in one
  call, which invites a list with one template. Ten separate calls, each
  forbidden from the previous answers' vocabulary, is the obvious next design —
  and it is a testable claim about prompting, not about markets.
* A **stronger model**. The Claude path was unavailable tonight (empty key).
  NIGHT-3's negative result on LLM stock selection was measured on a different
  task, and this one — hypothesis generation, judged by a linter rather than by
  returns — has not been run against a frontier model.
* Note the asymmetry that makes both cheap to test: the whole exercise cost
  **two-thirds of one cent**. The constraint on LLM research here is not budget.
  It is that the output has to survive an instrument, and tonight's did not.
