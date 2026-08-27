# A refusing lane and a dead lane wrote the same file for fourteen days

*2026-08-28. `backend/services/copy_lab/sentinel.py`,
`python -m scripts.copy_lab_sentinel`.*

## The failure

Both copy-lab lanes refused every run from 2026-08-14 to 2026-08-28 because
`autocrlf` rewrote 247 line endings and the config hash stopped matching the
seed (`FINDING_2026-08-28_A_LINE_ENDING_IS_NOT_A_CONFIGURATION.md`). Nobody
noticed for two weeks, and the reason is not that nobody looked:

```
a lane that REFUSED to run wrote        cash 100000, positions {}, last_nav null
a lane that RAN and found nothing wrote cash 100000, positions {}, last_nav null
```

Identical bytes, opposite meanings. One is a broken engine; the other is a
working engine correctly declining to trade. And when the hash bug was fixed, a
**second** stoppage appeared behind it — the Form 4 source had been stale since
12 August and the 13D source returns zero events — which had been invisible for
exactly the same reason.

The failure is not local to copy-lab.
`FINDING_2026-08-28_THE_ENGINE_NEVER_TRADED.md` found no `nav.jsonl` anywhere in
the estate: ten arena books, no NAV rows, and *"demonstrated edge is 0%"* turned
out to mean **no evidence** rather than evidence of no edge.

## The rule

**Absence of activity is benign only when something positive says the engine ran
and chose not to act.** Six quantities separate the two worlds without reading
code: `ran_at`, `refusals` by reason, `candidates`, `forecasts`,
`source_age_days`, `nav_rows`.

Classification:

| condition | status |
|---|---|
| zero positions and **no receipt** | FAIL — nothing says the engine ever ran |
| zero positions, last run > 5 days ago | FAIL — a stopped engine and a flat book are the same file |
| zero positions, recent receipt | ELEVATED — this is a **refusal**, which is a finding |
| **no NAV rows ever** | FAIL — the book has no track record at all |
| any source older than 5 days | FAIL — a stale feed reads as "no events" |
| config hash ≠ seed hash | FAIL — reported here rather than swallowed by the runner |

## The mistake I made building it, which is the same mistake in miniature

The first sweep classified all fourteen lanes and reported the twelve dormant
ones as `FAIL: NOT SEEDED`. True, and useless. Seeding is attended and env-gated
by canon, so those lanes are correctly unseeded and always will be until a human
seeds them. **Twelve permanent red lines standing beside two real ones is
`reference_gate_that_cannot_go_green` again** — a guard that cannot go green
teaches the reader to skim red.

`DORMANT` is now its own status, excluded from the exit code and from the WORST
line. The sweep reports what it inspected and what it deliberately did not.

## Current state

```
WORST (of 2 active, 12 dormant): ELEVATED
  [ELEVATED] CORPORATE_INSIDER_CLUSTER   nav_rows 10, n_positions 0
  [ELEVATED] ACTIVIST_13D                nav_rows 10, n_positions 0
      -> zero positions, but a recent receipt exists -- this is a REFUSAL,
         which is a finding, not a fault
```

Both active lanes are marking NAV again after the hash fix, and both are holding
nothing. That is now a *statement* rather than a silence — which was the entire
point.

## Status

Engineering guard, added because an actual failure demonstrated it was needed
rather than on principle. Pinned by four tests in `backend/tests/test_copy_lab.py`.
