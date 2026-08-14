# INTERNET-INVESTIGATOR-FWD-1 — the pre-Night-1 checklist

**Status: 6 / 6 built, and the attended item in §7 is now REGISTERED. Night 1 is
unblocked.**

Source of the orders: `DISCHARGE_OPUS5_2026-08-14.md` → *FABLE REVIEW 3*,
"Binding pre-Night-1 orders (narrow; nothing else may change)". This file is the
status board for those six, and nothing else. It is deliberately not a design
document — the design is frozen and lives in
`Aegis module/TRIALS/PREREG_INTERNET_INVESTIGATOR_FWD_1.md` and
`Aegis module/scripts/iif1_config.py`.

The standing status line, adopted verbatim from Murat:

> **IIF-1: CONDITIONALLY GREEN-LIT — scientific design frozen;
> magnitude/volatility primary approved; Night 1 blocked only on executable
> 40/80/120 read-schedule enforcement and runner completion. No further
> architecture changes before pilot.**

---

## 1. Executable read-schedule enforcement — **DONE**

> *"`READ_CHECKPOINTS_GRADED_NIGHTS = (40, 80, 120)` frozen beside the floor,
> enforced in executable code — a read at 39, 41, 57, 79, 81, 119 or 121 is
> refused as firmly as at 39. Config text alone does not remove optional
> stopping."*

`Aegis module/scripts/iif1_read_gate.py`.

Before this file, the only executable check in the entire trial was
`register_internet_investigator_fwd_1.py:145` — `if n < 40: raise`. That refuses
39 and permits 41, 57, 79, 119 and 600. A floor is not a schedule.

| n | disposition | bar |
|---:|---|---:|
| 39 | `REFUSE` | — |
| **40** | **`READ`** | MDE_Z 4.312 |
| 41 | `REFUSE` | — |
| 79 | `REFUSE` | — |
| **80** | **`READ`** | MDE_Z 3.295 |
| 81 | `REFUSE` | — |
| 119 | `REFUSE` | — |
| **120** | **`READ`** | MDE_Z 2.845 |
| 121+ | `NEW_PREREG_REQUIRED` | — |

`require_read()` **raises**; it does not return "unlicensed" as a value for
callers to remember to check. Every path that can write a verdict, a registry
row or a headline goes through it. `verify_schedule_matches_receipt()` re-checks
the config's constants against `runs/INTERNET-INVESTIGATOR-FWD-1/boundaries.json`
on every verdict attempt, because `READ_SCHEDULE` retypes numbers that
`iif1_boundaries.py` simulated, and a bar retyped 5% loose is a false-positive
rate nobody notices.

## 2. Terminal rule frozen — **DONE**

> *"At 40/80 without the MDE → `INTERIM_UNDERPOWERED`, carrying no H1 win/kill
> reading. At 120 without detectability the prereg terminates `NOT_DETECTABLE`;
> accrual beyond 120 requires a new prospective amendment/pre-registration."*

`iif1_read_gate.classify(n, t)`:

| look | \|t\| ≥ bar | \|t\| < bar |
|---|---|---|
| 40, 80 | substantive verdict permitted | `INTERIM_UNDERPOWERED` — **not a win, not a kill, not a trend**; `substantive=False`, `terminal=False` |
| 120 | substantive verdict permitted | `NOT_DETECTABLE`, **`terminal=True`** — the pre-registration ends here |
| any | — | `t=None` → `INTERIM_UNDERPOWERED`; a statistic that could not be computed is never a verdict |

Two consequences worth stating because they are the point:

- A non-terminal look does **not** write a `VERDICT-` registry row. It writes
  `INTERIM-INTERNET-INVESTIGATOR-FWD-1-LOOK{k}`. Every licensed look leaves a
  ledger entry — that is what makes a hidden peek detectable — but an interim
  row calling itself a verdict would be read as a resolution by every future
  corpse check.
- `121` and `39` are refused with **different remedies**. 39 means *wait*. 121
  means *this pre-registration is over*. Collapsing them would let a null at 120
  quietly become "keep going until it isn't".

**Claim language is bound** (`CLAIM_LANGUAGE`, discharging Review 2's
condition 1): the only claim a positive H1 licenses is *"autonomous
investigation improves magnitude/volatility forecast calibration relative to an
engineered numerical snapshot."* `assert_claim_language_permitted()` refuses a
verdict line containing *alpha, Sharpe, outperform, tradable, profitable, skill,
stock picking*. The trial forecasts no return and holds no position, so no such
claim is available to it at any n — including a positive one at look 3.

## 3. Boundary tests — **DONE**

`Aegis module/tests/test_iif1_read_gate.py`, **37 tests, green**.

The referee's nine (39/40/41, 79/80/81, 119/120/121) plus the ones that matter
because a gate refusing at the right `n` while emitting the wrong verdict *at* a
licensed `n` has only moved the failure:

- an underpowered interim produces **neither** a positive nor a negative — both
  signs checked, because the failure mode is asymmetric in practice (an
  underpowered null reads as a kill to everyone who wasn't there);
- `t = 3.0` clears the flat house bar of 2.80 and is `INTERIM_UNDERPOWERED` at
  look 1 — the multiplicity correction doing the only job it has;
- the bars are strictly decreasing (if that ever inverts, the early peek has
  become the *cheapest* place to stop, which is backwards);
- an enormous `t` at n=41 cannot buy a look;
- the config's constants equal the simulated receipt.

**Refusal is the hardest thing in a codebase to test by accident:** loosen an
inequality by one and nothing fails, no output changes, and no downstream number
goes wrong. So the boundaries *are* the test.

## 4. The runner stays a boring orchestration layer — **DONE**

> *"Frozen trigger set selected once; identical cells to every arm, equality
> asserted before calls AND before grading; requested/served model, tokens,
> cost, tool failures, malformed/drop counts, arm completion — all durable; no
> trial-result statistics during the blind besides operational diagnostics."*

`backend/services/investigator_night.py`.

- **Equality before the calls.** The cell set is frozen once into a tuple and
  every arm's list is checked against `__frozen_trigger_set__` *before* that arm
  makes a single vendor call. The pre-existing end-of-night check catches an arm
  that dropped cells while running; it cannot catch an arm handed the wrong ones
  until all five arms have been paid for. Pinned by
  `test_the_frozen_cell_set_is_checked_before_any_arm_makes_a_call`, which
  asserts **zero** LLM calls were made.
- A pre-call divergence **voids** the night with its reason on disk rather than
  raising out of the runner. Same outcome for the trial, different outcome for
  knowing why.
- **The blind stays blind.** `test_the_receipt_carries_operational_diagnostics_and_no_trial_statistics`
  asserts the nightly receipt contains no `posterior`, `probability`,
  `threshold`, `observable`, `brier`, `rationale` or contrast, and pins the
  per-cell row's key set exactly. Counts (`n_forecasts`) are operational and
  stay; anything from which a forecast's *value* could be recovered does not.
  The receipt is read by a human every morning for 40 mornings.
- **Constant drift is now checked on the arms too.** Only the trigger rule was
  previously compared against the frozen config, which left `ARMS` — the thing
  the entire trial compares — unguarded, along with the model, benchmark and
  both ceilings.

## 5. Budget framing — **DONE**

> *"$37.12 ÷ 40 = $0.928/night is the funding average; $10–15 is a hard safety
> ceiling, not a planning budget."*

`investigator_night.project_funding()`, attached to every night receipt:

| field | meaning |
|---|---|
| `measured_cost_night_1` | read from served responses via the telemetry ledger, never estimated |
| `projected_40_night_cost` | measured × 40 |
| `current_balance` | $37.12, dated `2026-08-14`, overridable per run |
| `funding_gap_or_surplus` | balance − projection |
| `fundable_nights_at_this_rate` | **the number that actually decides** |
| `funding_average_per_night` | $0.928 — the planning number |
| `safety_ceiling_per_night` | $12.00 — a stop, not a plan |

Pinned by `test_a_night_under_the_ceiling_can_still_be_unfundable`: a $4.00
night is a third of the safety ceiling and buys **9** of the 40 nights required.
Under the ceiling and unfundable are not the same state, and the receipt says so
in the same breath.

A measured cost of `0.0` or `-1.0` (telemetry unreadable) reports
`measured_cost_status: "unknown"` and `None` projections — **never $0.00/night**.
A failed read and a free night must not arrive as the same value; that is the
house failure mode, and it is this trial's own tool-layer lesson (`ff3950e`).

## 6. CI skip-integrity — **DONE**

> *"A missing sibling config must fail conspicuously, never read as green SKIP."*

`backend/tests/iif1_prereg_check.py`.

The old code:

```python
if not cfg.exists():
    pytest.skip("Aegis module not present in this checkout")
```

A skip is green. On any checkout without the sibling — which is every CI
container that clones one repo — the single assertion standing between *"the
trial ran the registered rule"* and *"the trial ran some other rule"* reported
success while executing nothing.

Now: **default is failure.** The escape hatch is `AEGIS_IIF1_PREREG_ABSENT_OK=1`,
which must be set explicitly, prints a loud banner naming everything left
unverified, and accepts only the exact string `"1"`. A context with no sibling
tree may opt out, but only by *saying so* — it can no longer be inferred from a
missing directory, because a missing directory is also what a broken checkout
looks like. Both paths are pinned by tests, including the absence path, because
the failure it guards is invisible by construction.

---

## 7. The read-schedule amendment — **REGISTERED 2026-08-14T08:38:13Z**

**The read-schedule amendment is not on the registry.** The registered row
(`cd058fd`) froze a read *floor* of 40 nights and the flat house `MDE_Z = 2.80`.
Commit `cc0bb4c` replaced that with three licensed looks carrying
O'Brien-Fleming constants — **a change to the decision rule**, made before any
accrual (zero graded nights, zero trial LLM spend), currently documented only in
a config comment.

Under *pre-register or it didn't happen*, a decision rule that lives in a config
file and not in the registry has no tamper evidence. So:

```bash
python -m scripts.register_internet_investigator_fwd_1 --amend-read-schedule
```

was **run at Murat's decision, 2026-08-14T08:38:13Z**, before Night 1 and before
any accrual. The row `AMEND-INTERNET-INVESTIGATOR-FWD-1-READ-SCHEDULE` carries
the looks `[40, 80, 120]`, the per-look constants `[4.3117, 3.2955, 2.8452]`,
the achieved family-wise α, `graded_nights_at_amendment: 0`,
`llm_spend_at_amendment_usd: 0.0`, and the terminal rule as its kill condition.

It was left attended rather than taken unilaterally because registering
increments the cumulative multiple-testing count by one — the conservative
direction — and the registry has no delete API by design.

The bars that decide this trial now have tamper evidence rather than a config
comment.

---

## What is NOT in scope before Night 1

No further architecture changes. `TEACHER-LIBRARY-1` (Track E) begins **after**
Night 1 runs cleanly and its cost is reported — the pilot does not share its
builder with a new lane's build-out.
