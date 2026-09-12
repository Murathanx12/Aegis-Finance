# THE STAGE CONTRACT — first step (2026-09-13, chunk 9)

Sibling of `docs/OPTIMUS_MCP_SURFACE.md`. Short on purpose: this is the **cheap,
tamper-evident down payment** on the farm↔book unification, not the unification.
That is scoped "big" in the roadmap (§11) and gated on lane B; forcing it here
would be roadmap-scale work wearing a test's name.

## The vocabulary

```
raw  <  normalized  <  features  <  signal  <  weights  <  pnl
```

Every receipt written by the night factory and by the cadence pass declares one.
`scripts/night_factory_jobs.STAGE_ORDER` is the order; `JOB_STAGES` is the map.

## The one rule enforced today

**No stage reads an artefact produced by a LATER stage.**

`backend/tests/test_stage_contract_no_forward_read.py` walks every receipt under
`backend/data/optimus/night_factory_*/`, builds "which stage produced this file"
from the receipts that declare one, and fails when a receipt's declared
`inputs` / `reads_from` / `panel.path` names a file a later stage produced.

This catches one class of bug and does not pretend to catch more: *"E2
accidentally reads a paper book's realised fill price as a feature."* A PIT
assertion on a single table cannot see it — every row in that table is
individually point-in-time, and the leak is in **where the table came from**.

## It is refusal-shaped, on the `monday_gate_check` lesson

- No receipt in the corpus carries a `stage` → **CANNOT DETERMINE**, not a pass.
  A check that can only ever pass is not a check.
- A receipt carries a stage but declares no inputs → it is **NAMED** in the test
  output, never silently counted as clean. On 2026-09-13 that list was 8 of 8,
  and saying so is the point: the contract had nodes and no edges until the
  chunk-9 jobs started declaring what they read.
- A registered job with no entry in `JOB_STAGES` gets `stage: None`, not a
  default. A default would make every unclassified job silently `signal`, and a
  contract whose rows are mostly guesses is a contract nobody can act on. 14 of
  the factory's jobs are in that state today and the test prints their names.
- `test_a_forward_read_would_actually_be_caught` plants a violation on a
  temporary corpus and requires the guard to fail on it. A guard that has never
  been shown to fire is a guard nobody has tested.

## What `Strategy` and `PaperBook` already enforce of Qanat's five rules

§11 names five properties a typed stage contract (Qanat, MIT, `fidetolabs/qanat`)
would give structurally. Most are already true here, by different means:

| Qanat's rule | status in this repo |
|---|---|
| **raw is source-only** — a raw table is never itself a tradable weight | **already true.** `backend/strategy/contract.py`'s `Strategy` is an ordered pipeline of frozen dataclasses — `Universe` → `Signal` → `Construction` → `HoldRule`/`Sizing` → `CostModel` → `Objective`/`Benchmark` — each with its own `__post_init__`. A universe cannot be a weight because it is a different type. |
| **data flows forward only** | **partly.** True inside a `Strategy` by construction; NOT structurally true across receipts, which is exactly the gap the test above closes for the night factory's artefacts. |
| **one weights stage per book** | **already true.** `backend/services/paper_books.PaperBook` holds exactly one `Strategy`, and `book_id_for(strategy)` derives the book's identity FROM that one strategy rather than from a merge of several. `Strategy.fingerprint()` hashes the whole pipeline. |
| **no book reads another's weights** | **already true for the live paper layer.** `PaperBook`'s NAV/positions write path is CANON §5-sacred (`lane-integrity-check`), and `decide_weights` reads that book's own signal frame and prices, never another book's positions. |
| **every table has a producer** | **partly.** `signal_reachability.py` enforces it for MODULES (a module no entry point reaches must be classified or the suite fails). The receipt-level `stage` field generalises it to ARTEFACTS; the `inputs` list is what makes a producer resolvable. |

## What is deliberately NOT done this chunk

- No `stage` field on `Strategy` or `PaperBook`. That is the unification, it is
  gated on lane B, and the roadmap's own "new guards are no longer roadmap work
  by default" rule says to wait for a failure that demands it.
- No general DAG verifier.
- No back-stamping of historical receipts. A stage asserted years later by
  whoever is reading is not a declaration; it is a guess with a git timestamp.

## The gap this exists to close, stated plainly

The farm (`portfolio_farm.Policy`, `scripts.portfolio_farm_run`) and the arms
(`PaperBook`) are two stacks. A farm candidate's promotion re-implements its
weights logic rather than flowing the SAME `Strategy` object from evaluation
into `PaperBook.create()`. There is no cross-stack type saying "this farm
weights table is THE producer for this book", so a promotion has room to diverge
between what was backtested and what is traded. The receipt-level stage field
does not close that. It makes the first divergence visible in a receipt instead
of in a return.
