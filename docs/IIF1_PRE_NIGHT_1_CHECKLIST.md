# INTERNET-INVESTIGATOR-FWD-1 — the pre-Night-1 checklist

**Status: Review-3's six orders DONE and registered (§1–§7). The follow-up
review's P0s DONE (§8). The entrypoint and feature layer DONE and rehearsed on
real data for $0.00 (§9). Night 1 is runnable and has not been run — the two
things left are a full-universe dry run and the funding decision (§10).**

Source of the orders: `DISCHARGE_OPUS5_2026-08-14.md` → *FABLE REVIEW 3*,
"Binding pre-Night-1 orders", plus the follow-up integrity review. This file is
the status board for those, and nothing else. It is deliberately not a design
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

---

## 8. The follow-up review's integrity holes — **DONE** (`d7e6876`)

Seven defects, each verified against the code before it was touched. All seven
were real. They share a shape: the night **worked**, and that was never the
question. The question is whether a night that works is the trial that was
registered.

### 8.1 A production invocation could be reshaped by its own arguments

`verify_or_refuse()` compares module CONSTANTS. It cannot see arguments. So this
passed every check:

```python
run_night(k=10, arms=("A_snapshot", "B_tools"), max_usd=100)
```

The verifier read `TRIGGERS_PER_NIGHT == 40`, a complete `ARMS` and a $12
ceiling, reported the trial as registered — and the run then executed ten
triggers across two arms at a hundred dollars. **A frozen parameter a caller can
override is not frozen; it is a default.**

Worse, injection and accrual shared one path. An injected `llm_call` skipped
verification on the theory that it spends nothing — but `dry_run` defaults to
`False`, so a real paid client passed through that argument would have written
the evidence ledger with no pre-registration check at all.

`sandbox` is now an explicit, load-bearing keyword:

| | production (`sandbox=False`, default) | sandbox (`sandbox=True`) |
|---|---|---|
| frozen params | must equal the registered rule | anything |
| injected deps | refused | allowed |
| pre-registration | must be readable | not required |
| evidence ledger | may write | **never**, whatever `dry_run` says |
| receipts | `iif1_nights/` | `iif1_nights_sandbox/` |

`sandbox` outranks `dry_run` deliberately: forgetting one keyword must not turn a
rehearsal into forward evidence.

### 8.2 Pairing was asserted on tickers; the statistic is computed on cells

`assert_arms_share_cells` only proved every arm *attempted* the same tickers.
Malformed forecasts are dropped — correctly, since coercing one scores a
judgement nobody made — so arm A could hold `NVDA/abs_move/5d/5%` while arm B
lost exactly that cell, and the guard saw five arms that all "did NVDA".

Cells are now keyed `night × ticker × observable × horizon_days × threshold`.
Only the cross-arm **intersection** is minted; a cell missing anywhere is dropped
everywhere, symmetrically, so the removal cannot favour an arm. Zero shared cells
**voids** the night. Per-arm drop rates are reported, not repaired — a
differential malformed-output rate is itself an architectural result.

### 8.3 Provenance

`hash(inv.dossier)` was worse than an ugly identifier. `input_snapshot` is not
stored — the ledger stores `input_snapshot_hash` — so a process-salted hash
inside that dict made the **entire snapshot hash non-reproducible**. Replay the
same night, get a different hash; no record could ever be tied back to the input
that produced it, which is the field's only job. Now SHA-256, pinned at the
source because the symptom is invisible within one interpreter.

`model_version` took `sorted(served_models)[0]` — whichever name sorts first
across five microtasks. Now the **forecast call's** served model; the others stay
on the receipt.

`RECEIPTS_DIR` sat under the repo while the ledger it describes lives on the
persistent volume — **NIGHT-14 defect F7 reproduced in the file that documents
it**. A deploy would have kept every prediction and destroyed the evidence of how
it was produced.

### 8.4 The ceiling was approximate

The gate checked `spent >= ceiling` *before* the request, so at $11.99 against a
$12 cap it permitted one more call. A worst-case cost is now reserved before
transmission (`WORST_CASE_CALL_USD = 0.05`, ~68x MARKET-GRAPH-1's measured
$0.00073/call).

`backend/tests/test_investigator_integrity.py` — its own file, because these are
not about whether a night works.

---

## 9. The entrypoint and the feature layer — **DONE** (`d0274f1`)

`run_night()` had twenty-four tests and no caller, and nothing produced the six
features its trigger rule consumes.

**`backend/services/iif1_features.py`.** A forward trial gets point-in-time
discipline almost free, but only if it takes the offer. What we can fetch at
21:00 tonight *is* what was knowable at 21:00 tonight — **provided the result is
frozen and never recomputed.** Recomputing next month would silently substitute a
corrected earnings calendar, a restated filing index and retroactively
split-adjusted prices for what the model actually saw. So `assemble()` writes
`iif1_features/<date>.json` and **refuses to overwrite it**. The snapshot, not
the code, is the point-in-time record.

Every feature carries `value / status / source / published_at / observed_at /
fetched_at`, with the house tri-state: `OK_DATA` / `OK_EMPTY` / `UNAVAILABLE`.
*"No filing in two days"* and *"SEC lookup failed"* score identically the moment
those two collapse, and then a throttled feed becomes a trigger list of quiet
names. `UNAVAILABLE` features are omitted, which `score_candidate` already
discloses rather than reading as zero.

Two point-in-time decisions worth naming:

- **`decision_ts` is New York time**, and a naive string is read as NY, not UTC.
  Guessing UTC for something a human typed while thinking about the close shifts
  every boundary five hours in the direction that leaks.
- **A filing is public at its SEC acceptance timestamp**, not its filing date.
  One accepted at 18:05 was available to nobody during that session. Where
  acceptance is missing the fallback is end-of-day and the note says so —
  assuming a time the source did not give us is inventing precision.

The residual is market-adjusted: on a day the index falls 3% every security
prints an unusual move and the trigger list becomes a list of large caps.

**`backend/services/iif1_run.py`** — three modes, one of which can spend:

```
--rehearse       sandbox + deterministic stub model, $0.00
--assemble-only  real data, frozen snapshot, no model at all
(default)        production
```

Features are frozen to disk **before** any vendor call. Assembling inside the run
would make the inputs a side effect of it, so a crash halfway would leave a night
whose inputs no longer exist and whose partial spend bought nothing auditable.

**Verified end to end on real data, $0.00 spent:**

```
6 names · 36 features · OK_DATA 36 / OK_EMPTY 0 / UNAVAILABLE 0
triggers: JPM 2.79 · UNH 2.72 · AAPL 1.94 · NVDA 1.78 · XOM 1.09 · MSFT 0.76
5 arms · 18 cells produced · 18 paired · 0 dropped unpaired
0 records written — sandbox, as designed
cost: UNKNOWN, not $0.00
```

That last line is the tri-state earning its keep where it matters most: a
rehearsal made no vendor call, so its cost is *unmeasured*, and printing zero
would project a free 40-night trial.

**One defect found by that first rehearsal:** the report crashed on a cp1252
console encoding box characters — *after* the night had run. A production night
would have spent the money, written the receipt, and then died printing it.
Pinned.

---

## 10. What is left before the first dollar

1. **A full-universe real-data dry run.** Measures the true `UNAVAILABLE` rate
   across the 182-name universe and whether 40 triggers are actually reachable.
   Costs nothing and must happen before anyone pays for a night.
2. **The funding decision, at Murat's desk.** Once `measured_cost_night_1 × 40`
   is a real number against $37.12. $0.928/night is the planning average; a $4
   night is not "under budget", it is nine fundable nights out of forty.
3. **Night 1 itself — locally and attended**, per the ruling. The deployed image
   deliberately cannot run a paying night: it has no `Aegis module` sibling, so
   `verify_or_refuse()` refuses. Packaging the frozen artifact with a content
   hash is the automation step, earned after the pilot is stable rather than
   designed in before the first night.

Interpret nothing from Night 1 but operations: valid paired cells, arm
completion, tool-failure rates, model provenance, calls, spend, projection.

---

## FABLE ORDERS — next tasks (2026-08-14, Murat away for a few hours, interim authority delegated to the brain)

Murat's standing instruction for this window: keep working; the new tasks
follow. His added note on TEACHER-COPY: personal/research use only, not sold —
noted; the `public_at` discipline stays anyway because it is what makes the
lane's numbers mean anything, not a legal posture.

### Order 1 — read the 182-name probe, then gate

When the availability probe lands, read it against two thresholds: the
UNAVAILABLE rate, and whether the frozen per-night trigger count is actually
reachable from the real universe. If either fails, STOP — report and hold for
Murat; do not run a paid night against an infeasible pool. The probe's serial
runtime (~25+ min observed) is itself an operational input: state what the
nightly schedule has to accommodate, and whether simple caching keeps it
inside the window. No re-architecture.

### Order 2 — RUN NIGHT 1. One night. Authorised now.

Murat authorised the paid pilot when the read schedule froze; the schedule is
frozen, the checklist is closed, the rehearsal ran clean. Conditions:

- Locally, this session attending. `sandbox=False` stated explicitly in the
  invocation; the frozen config verified by `verify_or_refuse()` on the real
  path; every ceiling binding.
- The receipt must print the full budget block from SERVED responses:
  `measured_cost_night_1`, `projected_40_night_cost`, `current_balance`,
  `funding_gap_or_surplus`. "UNKNOWN" was the right answer before a paid
  night; after one it is a defect.
- **STOP after one night.** Night 2 is Murat's funding decision, made on the
  printed block when he returns. No accrual schedule is committed.
- If anything voids the night (guard, drift, encoding, tooling), the void
  reason on disk IS the deliverable — report it, do not retry-spend the same
  night without stating what changed.

### Order 3 — while waiting or after Night 1: Track E groundwork, $0, data engineering only

In priority order, all vendor-spend-free:

1. **Form 4 tri-state source contract** — `OK_EMPTY` / `OK_DATA` /
   `UNAVAILABLE` through `fetch_open_market_buys()` and its consumers, with a
   silent-fragility pass over the collector. This is the pre-registered
   prerequisite for everything else in Track E.
2. **Canonical public-action ledger** — schema + ingestion skeleton for the
   free Tier-1 sources (SEC bulk insider transactions first). `public_at` is
   the only signal timestamp; provenance and data-quality status on every
   row. **Data engineering only: no IC, no outcome joins, no signal
   evaluation of any kind** — the moment a number could grade a hypothesis,
   pre-registration comes first (`pre-register-trial`).
3. **TEACHER-COPY lane spec** — a seed-ready YAML + one-page spec per roadmap
   Track E item 8 (public_at entries, risk-matched benchmark + SPY,
   `PRODUCT_LANE` label). **Spec only — seeding is attended; Murat flips the
   flag.**
4. **Track A hook** — the `ABLATION_FWD` auto-append for the first forward
   resolutions on 2026-08-16, if it is not already wired.

### What is NOT authorised in this window

Night 2 or any accrual commitment; seeding any lane; any paid data purchase;
any IIF-1 design change beyond what Night 1's own void reasons force; reading
any IIF-1 outcome (the read gate answers this anyway).

— Fable
