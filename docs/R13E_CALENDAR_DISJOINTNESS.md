# R13e — the slice register had the wrong axis

**Built 2026-08-16**, directly out of the N9 withdrawal
(`docs/TRIALS/ERRATUM_N9_CONFIRMATION_CALENDAR_OVERLAP.md`).

---

## 1. What was wrong

The slice register was built to stop a confirmation reading data a prior trial
had read. Its reuse identity is

```python
is_same_slice = shared_securities AND period_overlaps AND same_horizon
```

Both, not either. So a confirmation on **fresh tickers over a spent calendar**
is clean by construction — which is exactly what N9's Amendment 1 was:

| | |
|---|---|
| selection | SPY XLF XLE, 1999 → **2015-12-31** |
| confirmation | DIA XLV XLI XLP XLU XLB, **1999 → 2026** |
| `prior_readers` | `[]` — clean on the securities axis |

and the number that came out of it, 1.271 (p=0.015), was the programme's only
surviving positive for four days. Split at the selection boundary:

| confirmation slice | H=20 | H=60 |
|---|---|---|
| 1999–2015, calendar-OVERLAPPING | **1.464, p = 0.010** | 1.437, p = 0.020 |
| 2016+, calendar-disjoint | **0.765, p = 0.771** | 0.693, p = 0.806 |

The register named ten replacement candidates after the withdrawal. All ten
were clean **by security** and unexamined on the axis that had just killed the
result.

## 2. What was built

**Registration gate (`Aegis module`).**
`prereg_power.check_calendar_disjointness` — R13e, wired into
`prereg_lint.lint` after the slice claim and into `lint_prereg`'s REFUSALS, so
the exit code carries it.

Two new fields for `slice_purpose ∈ {CONFIRM, TRANSFER, FOREIGN}`:

```
- selection_period: 1999-01-01 .. 2015-12-31   (or NONE)
- parent_trial:     N9                          (or NONE)
```

| verdict | blocks | when |
|---|---|---|
| `UNDECLARED_SELECTION_WINDOW` | yes | a transfer claim that never says what selected it |
| `SELECTION_WINDOW_CONTRADICTS_PARENT` | yes | `NONE` declared beside a named parent |
| `UNPARSEABLE_WINDOW` | yes | two dates cannot be read out of the declaration |
| `CALENDAR_OVERLAPPING_CONFIRMATION` | yes | the windows intersect |
| `CONFIRMATION_WINDOW_ABUTS_SELECTION` | yes | disjoint, but inside the label reach |
| `CALENDAR_OVERLAPPING_FOREIGN_SLICE` | **no** | FOREIGN is still looking — recorded, `may_claim_transfer=False` |
| `CALENDAR_DISJOINT` / `..._BY_CONSTRUCTION` | no | passes |

**The gap is measured, not chosen.** Zero overlap is necessary and not
sufficient: labels run forward, so the last selection rows carry outcomes
formed inside the next window. `audit_temporal_lineage` measured the 1.5×
calendar heuristic failing on **15.7%** of 20-bar boundaries against the real
NYSE calendar, so R13e uses `7/5 × H + 14` — 42 days at H=20 where 1.5× allows
30. It does **not** replace the purge `research_gym.lineage` derives from the
index at run time, and says so in its own refusal text.

**Register (`aegis-finance`).** `SliceIdentity.calendar_overlaps` ignores
securities entirely. `SliceRegister.check` gains `parents`, and for a CONFIRM:

* `parents is None` → `UNDECLARED_LINEAGE`. Silence is not `()`. The register
  cannot check a calendar without knowing whose calendar to check, and the
  design that will not name a parent is the one whose parent matters.
* any consumption by `parents ∪ {trial}` at the same horizon whose window (plus
  its label reach) intersects → `CALENDAR_CONFOUNDED`, naming the years and
  the date a clean window would start.

Scoped to **lineage**, not to everyone: otherwise the first EXPLORE at a
horizon spends that calendar for every unrelated mechanism forever, and a guard
that expensive gets deleted the week it first costs somebody a slice. The
trial's own prior searching consumptions are added without being declared —
that half is derivable, and a declaration that can be omitted will be.

`clean_confirmation_windows` reports **both axes**, because "clean" reported on
one axis is how this happened twice in one day.

## 3. Receipts

```
$ python -m scripts.seed_slice_register --force

N9's design, replayed: THREE UNREAD securities, full calendar.
  securities axis — prior readers: []  (clean)
  calendar axis   — allowed=False  CALENDAR_CONFOUNDED  confounds=['N9', 'N9']
  clean window starts: 2026-09-27
  and with the lineage undeclared: allowed=False  UNDECLARED_LINEAGE
  both axes: unread=['EEM', 'EFA', 'GLD', 'TLT']  usable window=None
```

```
$ python -m scripts.lint_prereg <N9's design, in fields>
CALENDAR_OVERLAPPING_CONFIRMATION   exit 1
  R13e: ... overlaps the selection window on 6209 calendar days ...
$ # same document, window moved to 2016-03-01
PASS                                exit 0
  R13e: CALENDAR_DISJOINT  gap 61d (need 42d)
```

**`clean window starts: 2026-09-27` is a finding in its own right.** N9's
lineage has now read 1999–2015 (selection) and 2016–2026 (the foreign slice).
At H=20 **there is no clean window left on this corpus for any N9 descendant** —
only forward time or a genuinely foreign market can confirm that family. That
is a stronger statement than "N9 is withdrawn", and it was not visible until
the selection consumption was in the register.

Tests: 25 in `Aegis module/tests/test_prereg_calendar_disjoint.py`, 11 added to
`backend/tests/test_slice_register.py`. Suites green both sides — 762 module,
4436 fast backend.

## 4. The retroactive sweep, and what it cannot see

`python -m scripts.audit_r13e_calendar` over 124 pre-registrations:

```
REFUSED_NOW=0  UNDECLARED=0  LEGACY_TRANSFER_CLAIM=41  CLEAN=0  NOT_APPLICABLE=83
```

`REFUSED_NOW=0` is **not** a clean bill and the script refuses to print it as
one. `slice_purpose` is younger than every document in the corpus, so R13e can
score none of them; the 41 are documents whose *prose* makes a transfer or
holdout claim, matched on keywords and reported as a **reading list**. Among
them: `PREREG_N9_MINE_THE_85`, `PREREG_N9B_WIDER_VOCABULARY`,
`PREREG_N20_CONDITIONAL_MU_REST`, `PREREG_WM0_WORLD_MODEL_V0`,
`PREREG_WINNER_GENOME_1`, `PREREG_PORTFOLIO_ARENA_1`, `TRIAL-EVENT-13DG`,
`TRIAL-COND-VT`.

A sweep that reported zero because it could read nothing would be the house
failure mode wearing a report, so the count prints with that sentence attached.

## 5. One design refused by the new gate, and left refused

**N21.** Its rules were re-derived from N9's train securities through
`TRAIN_END = 2015-12-31`; its evaluation window is `EVAL_START = 2006-07-01`.
Nine and a half years inside the selection calendar. `scripts/n21_policy_utility.py`
now declares `parents=("N9",)` and the register refuses it.

It is **left** refused rather than repaired. The run happened, its headline was
already withdrawn by its own null-invariance diagnostic (p=0.031 against a
uniform-window placebo, p=0.338 against a clustering-preserving one), and
re-scoring it on 2016+ would be a new experiment, not a correction.
`--skip-slice-claim` still reproduces the run and now prints the R13e verdict
first.

So the calendar confound was **not** unique to N9. It is two for two on the
designs that ever claimed transfer from that family, and neither was noticed by
a reader — one was found by splitting the result, the other by a gate that did
not exist that morning.

## 6. The correction this makes to the erratum

`ERRATUM_N9_CONFIRMATION_CALENDAR_OVERLAP.md` §4 says the register "already
detects overlap on period" and "does not need to" require the varying
coordinate, because the slice claim moved to registration. That is wrong on
both halves. The register detected period overlap only *in conjunction with*
shared securities, and the registration lint required the slice to be
**identified**, never the selection window to be **named** — so N9's design
would have passed the lint that was shipped the same day it was withdrawn.

The erratum is not edited; it is a record of what was believed when it was
written. This is the amendment.

## 7. What this does not fix

* R13e reads **declarations**. `selection_period: NONE` is a claim on the
  record; a false one passes. The one derivation available at registration is
  the parent contradiction, and it is used.
* The gap is arithmetic on calendar days, not the real exchange calendar. It is
  conservative by construction and still not the derived purge.
* Nothing here reaches the 41 legacy documents. Any of them cited as transfer
  evidence needs its two windows written down first.
