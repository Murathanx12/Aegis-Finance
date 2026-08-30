# A DOCUMENTATION `git mv` DISARMED A BUDGET GATE, AND CI SAID ONE TEST FAILED

**Found:** 2026-08-30, investigating six consecutive red CI runs.
**Introduced:** 2026-08-29, commit `17cb099` — the 92-document archive move.
**Fixed:** `backend/config.build1_path()` + `backend/tests/test_build1_paths.py`.

---

## 0. WHAT CI SAID, AND WHAT WAS ACTUALLY WRONG

CI reported:

```
FAILED backend/tests/test_pm_build11.py::test_19_the_source_coverage_matrix_is_committed_with_receipts
  AssertionError: the coverage matrix must be committed
  where exists = PosixPath('.../docs/BUILD1/ANALYST_SOURCE_COVERAGE.md').exists
1 failed, 6018 passed, 38 skipped, 118 deselected
```

One test of 6,018, about a missing markdown file. Read at face value it is a
docs-hygiene nit, and it had been red on **every push since 2026-08-29 13:18**
— six runs — while sessions shipped work past it.

The actual state was this. `17cb099` moved 92 dated documents into
`docs/archive/`, and took the whole of `docs/BUILD1/` with them. That directory
is **not prose**. It holds fourteen artefacts that code reads and writes:

| artefact | consumer |
|---|---|
| `llm_ledger.jsonl` | `llm_research.spent_usd()` → enforces `CAMPAIGN_BUDGET_USD` |
| `funnel_night10.json` | `investment_committee`, `mirror_challenge` (read) |
| `mirror_challenge.json` | `mirror_challenge` (write) |
| `ANALYST_SOURCE_COVERAGE.md` + `analyst_source_probe_DKNG.json` | `pm_catalysts` provenance |

## 1. THE PART THAT DID NOT FAIL LOUDLY

```python
def spent_usd(ledger_path=None):
    p = ledger_path or LEDGER_PATH
    if not p.exists():
        return 0.0          # <-- a moved ledger and a spent-nothing ledger are the same thing
```

So the move did not raise. It **reset the recorded campaign spend from 71 calls
to zero**, and the `$30.00` gate at `llm_research.py:187` would have
re-authorised the full budget. The exposure here was small — `$0.0422` of `$30`
— but the size is an accident of when it happened. Had the ledger held `$29`,
the same `git mv` would have silently granted another `$30`.

Three further consumers were pointed at a directory that no longer existed:
`investment_committee` would have read a missing funnel; `mirror_challenge`
would have written its output into a freshly created empty `docs/BUILD1/`.

**Nothing about the move was wrong.** Every consumer that hardcoded the path
was.

## 2. THE LESSON, WHICH THE CODE HAD ALREADY WRITTEN DOWN

`llm_research._mirror`'s docstring, written before any of this:

> This module's own `llm_ledger.jsonl` predates the unified one and stays: it is
> what enforces `CAMPAIGN_BUDGET_USD`, and **re-pointing a budget gate during an
> instrumentation change is how budgets stop being enforced.**

That is exactly what happened, by a route the author did not anticipate — not an
instrumentation change, a documentation clean-up. **A warning in a comment
cannot enforce itself.** The same shape as `reference_gate_that_cannot_go_green`
and `feedback_silence_is_not_evidence`: the output that should have screamed was
a `0.0` that looked like an answer.

It also joins the standing rule from CLAUDE.md — *a guard DERIVES its inputs or
REFUSES* — with a corollary this incident earned: **a test that pins a PATH is
not testing the FACT.** `test_19` asserts that the coverage matrix is committed
with its receipts. That fact never stopped being true. The test died on a
directory rename.

## 3. THE FIX

`backend/config.build1_path(name)` searches live-then-archive and returns the
artefact wherever it currently is. An **existing** file wins, so an append-only
ledger keeps appending to its own history instead of forking into an empty twin.
Four consumers now resolve instead of assume.

`backend/tests/test_build1_paths.py` pins three things, and only the third is
the real fix:

1. every BUILD1 artefact that code touches is locatable;
2. `spent_usd()` agrees with the file it claims to read, and that file is not
   empty — *"an empty ledger and a moved ledger are indistinguishable to the
   gate"*;
3. **no module under `backend/`, `scripts/` or `engine/` builds a filesystem
   path from a docs directory that now exists only in `docs/archive/`.**

(3) is written over *every* directory, not `BUILD1` specifically, so the next
reorganisation is caught by CI rather than by a budget quietly resetting. The
resolver itself is exempt, because naming both locations is its entire job.

## 4. WHAT TO DO WITH THIS

- Six red CI runs is the finding underneath the finding. A one-line failure
  beside 6,018 passes reads as noise, which is the same reader-fatigue problem
  as `monday_gate_check`'s permanent red line. **A red suite is red.**
- `docs/BUILD1/` should probably not live under `docs/` at all — it is state,
  not documentation, and it was archived precisely because a human reading the
  directory listing saw documents. That is a larger change and is not made the
  night before an open; the resolver removes the urgency.
