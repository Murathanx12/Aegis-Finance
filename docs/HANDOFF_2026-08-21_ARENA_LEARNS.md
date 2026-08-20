# HANDOFF — 2026-08-21: the arena learns, the substrate is being refilled

Written after the session of 2026-08-20 late. Read
`docs/FINDINGS_2026-08-20_SESSION_AUDIT.md` first — it is the *why* for most
of what changed, and it is the honest list of what was wrong.

**Commits are LOCAL on `main`, not pushed.** A push deploys to Railway and the
house procedure (`verify-prod-after-deploy`) needs someone present. Nothing
here touches the sacred lanes or `paper_nav`.

---

## PRODUCT INTELLIGENCE ACQUIRED

Measured this session, not asserted:

1. **The arena ranks 99.5% of its cross-section on one factor.** Live
   `coverage_histogram: {"1": 206, "6": 1}`. Not the 12-of-180 the audit
   modelled — one name of 207 carries the five PIT families.
2. **Widening coverage is worth ~20× fixing the aggregation** (+0.239 vs
   +0.012 in latent-skill units), and **diverse coverage is worth ~4× cheap
   coverage** (+0.355 at ρ=0.2 vs +0.086 at ρ=0.75, where price-derived
   features sit). The large prize is universe-wide fundamentals / options /
   expectations — i.e. the WRDS substrate.
3. **The WRDS substrate was 21% present while the record said "completed".**
   281 of 1,327 tables. 86% of the 1,127 failures were self-inflicted
   (a 90-second timeout against a server that allows 2 days; a DNS outage
   booked as 235 per-table failures).
4. **The LLM was setting its own prior in the call that used it**, and ran on
   ~1 session in 20.
5. **Two collectors have no caller**: `event_intel` (news/8-K/earnings —
   prod says `events_extracted: 0`) had only the unscheduled `daily_brief`.

## WHAT AEGIS CAN DO TOMORROW THAT IT COULD NOT DO YESTERDAY

| capability | before | now |
|---|---|---|
| Grade its own LLM forecasts | never resolved | resolved every daily pass |
| Tell a belief from a tradable return | one close→close number | two legs, `schema_version: 2` |
| Say what it has been right about | nothing | `/api/arena/reliability`, refuses thin cells |
| Learn from what it passed on | nothing | `/api/arena/regret`, unpaired legs counted |
| Remember yesterday's belief | model invented it | read from `beliefs.jsonl` |
| Think on a non-trading day | no | every session |
| See news / filings / earnings | no | `LLM_EVENTS_v1`, frozen into the decision hash |
| Find a name outside the watchlist | **impossible** | 28 nominated on the live smoke test |
| Notice its own scores changed meaning | no | `policy_fingerprint` refuses to run |
| Refuse to trade a broken fetch | no | `min_priced_fraction` 0.80 |

**Live smoke test (real prices, temp root, LLM stubbed):** core 180 + scan 149
→ 232 observed → 125 observations → **28 nominations** (TEAM, SNOW, MARA,
UPST, DELL, WDAY, TPL, HIMS, RKLB, MSTR …) → 7 books decided → 105
experiences → `priced_fraction` 0.9944 → 0 reliability cells (correct on
day 1).

---

## 1. FIRST 20 MINUTES

1. `session_briefing()` + `aegis_verified_state()`.
2. **The WRDS catch-up is probably still running or has stopped on its
   budget.** `python -m scripts.wrds_pull_catchup --dry-run` prints exactly
   what is left, split TERMINAL vs RETRYABLE. Re-run to continue:
   `python -m scripts.wrds_pull_catchup --workers 4 --timeout-s 1800
   --max-seconds 43200`. It is resumable and refuses to write `completed_at`
   while anything retryable is outstanding.
3. **Fri 08-21 17:00 was the first IIF-1 SELF-launch** —
   `backend/data/optimus/iif1_launches/2026-08-21.json`. `LAUNCHED` = the
   machine runs its own nights. `REFUSED` = read the code, a refusal is a
   finding. **NO FILE = investigate Task Scheduler history first.**
4. **Fri 08-21 also lands the first 396 forward resolutions.** Mechanics only
   — `scripts/iif1_read_gate.py` licenses nothing before 40 graded nights.
5. Decide the push (§5).

## 2. THE STATE OF THE PULL

| | |
|---|---|
| planned | 1,327 |
| on disk at handoff | ~305 parquet files |
| TERMINAL (never retry) | **134** — 106 not entitled, 28 absent from server |
| RETRYABLE outstanding | ~920 |

TERMINAL is written to `backend/data/optimus/wrds/pull_terminal_failures.json`
as an entitlement addendum. Those are facts about the account, not bugs.

**Known open defect in the catch-up**: a handful of wide Compustat tables
fail with `ArrowNotImplementedError: Unsupported cast from double to null`
and `ArrowInvalid: Decimal value does not fit in precision 6`. Root cause is
per-chunk type inference; the fix (`_pg_types` + `_coerce`, taking dtypes
from `information_schema` instead of from the first chunk) is committed and
was being verified when the session ended. **Re-run the dry-run first: if
those tables are still listed, the fix needs its verification finished before
another long run.**

Throughput is bandwidth-bound: 6 workers was WORSE than 4. Do not raise it.

## 3. THE QUEUE, IN ORDER

### Q1 — the coverage hole (the +0.239 item)
Universe-wide **diverse** features. The trackers built this session are
price-derived and deliberately excluded from the score; they buy discovery,
not composite quality. The build is: derive fundamentals / expectations /
options features for the whole arena universe from the WRDS substrate,
arena-local and PIT-clean, and add them to `COMPOSITE_WEIGHTS` — bumping
`discovery.COMPOSITE_VERSION`, which the policy fingerprint now enforces.
**This is why finishing the pull is on the critical path, not beside it.**

### Q2 — do not build the complex allocator yet
The order asks for a multi-criteria substitution engine (correlation, tail
risk, catalyst timing). **Deliberately not built.** The arena has zero
forward data, the standing rule is that a complex allocator must beat the
simple rule on evidence, and `substitution_check`'s docstring already
records why cost is not netted against a z-score (different units). Build it
when there is a reliability ledger with real cells to beat.

### Q3 — the known-answer battery (flips G1 OPERATIONAL → PASSED)
Unchanged from the previous handoff. The arena adds a surface to calibrate:
plant a synthetic edge in a fake day-state and verify the reliability ledger
recovers it at the declared rate.

### Q4 — supervised learning on the substrate
Only once Q1's pull is closed. Risk-head retraining harness → Order-24
subspace test on any new family → models, each naming the simplest admissible
baseline it must beat by more than its own MDE.

### Q5 — the router
Design + prereg only. The counting brain now exists as the baseline it must
beat; the >100k gate is unchanged.

## 4. WHAT BINDS (do not re-derive)

- Arena = `PRODUCT_EXPERIMENT` / SIMULATION, never evidence of skill, never
  touches `paper_nav`.
- **No training on same-day P&L.** Reliability updates only from matured
  outcomes.
- **Never join the two horizon grids.** Decisions mature at 1/5/21/63/126,
  LLM forecasts at 1/2/5/20/60/120/252. "A month" is 21 in one and 20 in the
  other; `/api/arena/reliability` says so in every payload.
- **Never pool outcome schema v1 and v2.** `reliability.py` drops and counts
  v1 rows.
- Tracker features may **never** enter `COMPOSITE_WEIGHTS` (a test pins it) —
  short-horizon winner-chasing is a Holm-surviving ANTI-signal.
- Registered collectors' cross-sections are **not** widened.
- A material policy change is a NEW book id, and the estimator is now part of
  identity via `policy_fingerprint`.

## 5. ATTENDED (Murat only)

1. **The push.** ~10 commits sit local on `main`. Pushing deploys.
2. **`AEGIS_SEED_ARENA=1` for one boot** — *after* the push, and it should be
   the LAST thing. Every schema change above was free because the books are
   unseeded and expensive the moment they are not. **Seed last.**
3. NAV stamp fix **P-day-2026-08-19a** — still needs his go.
4. G2 prereg signature before 2026-09-08.
5. Laptop plugged in 16:55–17:05 daily (the ~2-min margin).
6. **Queue items now VERIFIED DONE — remove them**: amended NET prereg
   (SIGNED 08-19), Brier-bar signature (SIGNED 08-19), merge review of
   `lab/autonomous-rd` (0 ahead / 94 behind). Remaining real: positions read,
   LOSS amendment, Track E prereg, 08-27 resolve.

## 6. COST

LLM spend this session: **$0** (every rehearsal stubbed the model). WRDS
egress only. No prod writes.
