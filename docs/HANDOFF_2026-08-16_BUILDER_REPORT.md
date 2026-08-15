# BUILDER → BRAIN — report against the order of 2026-08-16 (`4c9f938`)

Written in the order §7 asked for. Executed 2026-08-15, ~12:40–15:00 UTC.

**P0, P2, P3 complete. P1, P4 are date-bound to 08-16. P5–P10 not started.**

One thing outranked the entire order and is reported first, because it made
everything else undeliverable.

---

## 0. THE ORDER COULD NOT HAVE SHIPPED — CI had been red for three commits

`§0` of the order records "`a355fa6`+, clean, pushed. 4,153 tests green." That
was true and it was not the whole picture. **CI had been failing since
`6e8c13a` (07:31 UTC), Railway gates deploys on CI, and production was sitting
on `5d7ae15` — three commits behind.** The §39 timing guard, written
specifically to protect a paid night, **was never in production.**

The cause is worth carrying: CI checks out ONE repo, so `../Aegis module` —
which holds the frozen IIF-1 pre-registration — is genuinely absent there. Two
tests I wrote on 08-15 depended on it being present:

- one asserted `readiness_report` returns `0`, but without the sibling
  `verify_or_refuse()` raises, the report correctly reports a blocker, and it
  returns `1`. `verify_or_refuse` ignores `AEGIS_IIF1_PREREG_ABSENT_OK` **on
  purpose** — a context that cannot read the registered rule must not certify a
  night against it;
- the other expected `NightWouldSpanTheOpen`, but `assert_production_invocation`
  runs first and raised `FrozenPreregMissing`. That ordering is correct.

**In both cases the code was right and the test asserted the local machine.**
The two green signals — 4,153 locally and the one gating production — were
measuring different worlds, and only one of them was being looked at.

The second failure was found only because the whole suite was re-run in the
simulated world instead of stopping at the first fix. `backend/tests/ci_env_sim.py`
now makes CI's world reachable locally in ~3 minutes:

```bash
python -m pytest backend/tests/ -m "not slow" -q -p backend.tests.ci_env_sim
```

It does not replace checking CI. Nothing replaces checking CI, and I did not.

---

## A. HEAD / tests / deploy

| | |
|---|---|
| `aegis-finance` | **`e53bb95`**, clean, pushed |
| `Aegis module` | **`70d529f`**, clean, pushed |
| tests | **4,219 fast** — green with the sibling present *and* hidden |
| CI | **green** (`bfb5e09`, `7cd5a24`, `5344e54` all pass) |
| deploy | **flipped to `bfb5e09`**, `nav.all_fresh` true, 7 jobs, 10 lanes fresh |

## B. IIF — time semantics, parallelism, Night 1

**Time-semantics audit (P2): no point-in-time defect. The evidence for that was
broken.** Measured on the real 2026-08-14 production snapshot, 1,092 rows:

```
decision_ts   11:50:25 UTC, stamped at assembly START
fetched_at    11:50:25 -> 12:03:54 UTC   -- 13.5 min of retrieval after it
observed_at   ONE distinct value across all 1,092 rows: decision_ts
published_at  prices   max 2026-08-13     (last completed bar -- cut)
              filings  max 08-14 03:43 ET (same morning -- cut)
              earnings max 2026-11-13     (THREE MONTHS AFTER the decision)
```

Content is genuinely cut: `_history_upto` filters bars to `<= decision_ts`,
`_filing_within` skips post-decision acceptances. **The trial is not comparing
timestamp labels.** But `observed_at` is *assigned* the decision time on every
row — the field that should evidence the cut is a copy of the thing it checks —
and `earnings_within_5d` stored a **scheduled future** date in `published_at`,
so the only field that could prove the cut reported a max three months out. The
new check, run against the real snapshot as frozen, **refuses 170 rows of a
clean snapshot**; re-homed to a new `event_at` field it **passes**, newest
information 03:43 ET against a 07:50 ET decision.

Now: `snapshot_started_at` / `snapshot_frozen_at` / `information_cutoff_at`
recorded separately, and `assert_snapshot_pit_safe` runs **at the freeze, before
the immutable file exists**. It reads `published_at` only — never `fetched_at`
(legitimately later; would refuse every real snapshot) and never `observed_at`
(satisfiable by assignment).

**Parallelism amendment (P3): built, registered, rehearsed. And the approval's
first act was to find that the ceiling would not survive it.**

`_spend_since` reads the telemetry ledger, and a row lands there only after its
call is served. Five arms read the same `$11.99` before any writes. Measured,
five threads off a barrier with room for exactly one worst-case call:

| | granted | refused |
|---|---|---|
| read-then-act (as written) | **5** | 0 |
| `SpendGovernor` | **1** | 4 |

**`$12.00` would have been `$60.00`** at five-way concurrency, with every
individual check correct. Also fixed: one shared chain cursor across arms
(telemetry filed under whichever arm wrote last), and an unguarded
`counter["calls"] += 1`.

All your binding conditions are met: one chain cursor per arm, no shared mutable
state, deterministic submission in frozen arm order, atomic spend reservation
released in a `finally`, bounded concurrency, per-arm start/end timestamps,
**max arm-start skew recorded per cell**, nothing written until the paired cell
completes, symmetric drop. `EXECUTION_MODE` and `MAX_ARM_CONCURRENCY` are on the
frozen surface in **both** repos, and an unregistered value refuses to accrue.

Known-response harness first, then the five-arm rehearsal, as ordered:

```
execution_mode  cells_sequential_arms_concurrent
peak in flight  5
arm start skew  max 1.0 ms across 10 cells   (serial: the sum of four arms)
dropped cells   none;  30 paired / 30 produced
```

The timing guard now divides by concurrency: **40×5 goes from 2.3h to ~28 min**,
never dividing by more than the arms it has.

**Measured latency:** unchanged from the ledger — mean 8.7s, p90 15.6s. No new
vendor calls were made concurrently.

**Valid Night 1: NOT RUN, correctly.** It was already 14:00 UTC when P2 went
green — past the 13:30 open — and the guard refuses. Tomorrow at or before
**~11:10 UTC** (mean) / **~09:20 UTC** (p90); under concurrency the safe start
moves much later, but I have not relaxed the guard's constants on the strength
of a stubbed rehearsal. **H1 not read.**

## C. Forward evidence

**Not done — date-bound to 08-16 and attended.** Campaign resolutions are not
due until tomorrow, and the `LIVE_FORWARD` quarantine is irreversible and
outward-facing, so it waits for Murat as you specified. Collector idempotency is
answerable for free from tomorrow's 06:00 EDT overlap.

## D. COPY-LAB

Not started. Blocked behind P4, which is blocked behind tomorrow's collector run.

## E. Teacher Library

Unchanged. R12 approved; backfill not started (P5).

## F. Conditionality

**Built and applied. The defect was exactly as you described it in code.**
`Autopsy` required `expected_unaffected_states`, validated them, wrote them to
`LineageRow.params["unaffected"]` — and `adjudicate()` derived its verdict from
`TransferTest.n_independent_slices_passed()`, a flat count with no notion of
scope. The declaration changed no outcome.

`ScopedVerdict` (nine verdicts, `revisit_when` required on every non-support,
`STRUCTURALLY_CLOSED` needs a ground from a closed list), scope-aware
adjudication with the **sign inverted** in unaffected regions, §18 enforced as a
detectable interaction, and a scope-aware corpse check where **only the two
closing verdicts block anything**.

**Global vs conditional: 0 global, 6 `CONDITIONAL_OPEN`-or-weaker, 0 closed.**

## G. Transfer Atlas

Not started (P6). But the re-run produced its requirement: see K.

## H. T4 — not started.
## I. Known-answer worlds — not started.
## J. Mechanism graph — not started.

## K. Defects found BY RUNNING CHECKS

Five, all found by running rather than reading, four of them in the
**kill-inflating** direction.

1. **CI red for three commits; production three commits behind** (§0 above).
2. **§40 — the Gym threw away the discriminating half of every hypothesis.**
3. **§41 — every refutation the new standard produced was manufactured by its
   own denominator.** First scoped run: `REFUTED_IN_SCOPE 5`. Under §37 the
   kills were checked before being reported, and `n_effective` was `n` — for
   probes sampled **monthly** over a **63-day** window across **six co-moving
   ETFs**. Separately, `se_pp` used raw `n` while `mde_pp` used `n_effective`:
   two beliefs about one sample, invisible while they were equal. Corrected,
   hypotheses held fixed via a new `--reuse-autopsies` path:

   | | before | after |
   |---|---|---|
   | REFUTED_IN_SCOPE | **5** | **0** |
   | TRANSFER_PENDING | 1 | 0 |
   | NOT_DETECTABLE_IN_SCOPE | 0 | **5** |
   | UNPOWERED_IN_SCOPE | 0 | **1** |

   **All six moved. Nothing is closed.** The GFC affected cell went from MDE
   4.7pp on "n=54" to **24.7pp on n_effective ≈ 3**.
4. **§42 — the PIT audit trail confirmed itself** (B above).
5. **§43 — the hard ceiling would have gone soft by the concurrency factor**
   (B above).

## L. Exact SHAs

| | |
|---|---|
| `bfb5e09` | CI unblock — two green signals, different worlds |
| `c3ae219` | the re-run protocol, declared **before** running it |
| `7cd5a24` | **P0** — scope-aware verdicts + the five manufactured refutations |
| `5344e54` | **P2** — the PIT cut was real; the evidence was not |
| `e53bb95` | **P3** — arms concurrent, `SpendGovernor` |
| `70d529f` | `Aegis module` — execution mode registered before the first valid night |

## M. Next bottleneck

**The transfer corpus, and it is now measured rather than suspected.**

The honest statement of the re-run is narrower than either pass: **the corpus
cannot resolve any of the six mechanisms in either direction.** Affected cells
carry `n_effective` between 1 and 3 against MDEs of 10–50pp. That is not a
finding about de-risking; it is a measurement of the instrument.

So TRANSFER_ATLAS_V1 (P6) is the binding constraint, and the re-run says what it
must supply: **more independent stress *episodes*** — not more rows, and not
more co-moving tickers inside the same months. Six ETFs across nine months of
the GFC is roughly three observations however it is counted.

Two things I did **not** do, deliberately:

- **I did not relax the conservative treatment of correlated tickers.** Counting
  six co-moving ETFs as fully redundant is conservative; the principled middle
  (an effective number of independent assets from the correlation matrix) is a
  refinement I flagged rather than guessed, because every plausible guess moves
  every MDE in the kinder direction, and I had just finished deleting five kills
  that came from a denominator that was too kind.
- **I did not expand the corpus in reaction to the re-run**, for the reason R11
  was refused.

**One item for you:** the timing guard's constants are still the *serial*
measurements (8.7s mean, 4.8 calls/cell). Under concurrency the projection
divides by five, which is right in principle, but the divisor has only been
exercised against a stub. The first concurrent paid night should be treated as
the measurement that either earns those constants or replaces them — and until
it exists, the guard's window is the honest one to obey.

— builder, 2026-08-15
