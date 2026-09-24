# Backtest — TRIAL-CONGRESS-IC leadership split, 2026-09-20

**Licence:** `PRODUCT_EXPERIMENT`. **Stage:** screen. **llm_spend_usd:** 0.0.
**Script:** `scripts/research_congress_leadership_split.py`. **Receipt:**
`backend/data/optimus/night_factory_2026-09-20/congress_leadership_split_backtest.json`.

## Verdict: REFUSED: UNDERPOWERED

**leadership purchases = 0, non-leadership purchases = 0** (floor: 30/group).
No forward-return computation, no Newey-West t, no null draws were run — the
power check refused before the backtest body executed, per its
pre-registration in this script.

## Why the idea (context)

`docs/research_notes/2026-09-20/research_horizon_and_winners.md` §5 item 1
ranked "congressional leadership-conditioning" as the #1 cheapest test by
expected information/hour, reasoning that `TRIAL-CONGRESS-IC`'s "already-
accruing snapshot table" could be split by leadership at zero new-collector
cost (Belmont et al., NBER w26975, and Wei & Zhou both flag leadership status
as the literature's most-cited unaddressed conditioning variable). That
framing turned out to rest on two false premises, both verified against
actual state rather than assumed:

## What was actually checked (two independent data sources, both dry)

1. **Local PIT store** (`backend/data/aegis_pi.db`, table `pit_observations`,
   key prefix `congress_score:`): **0 rows**, ever. The collector
   (`congress_collector.collect_congress_scores`, registered 2026-07-11,
   nominally weekly-throttled) has exactly **one** job receipt on disk
   (`backend/data/optimus/job_receipts/congress_morning_collect/2026-09-07T113001_910368Z.json`),
   dated **2026-09-07** — two months after registration — status `"ran"`,
   `"exception": null`, but `"writes": null`. The trial has been silently
   not accruing since inception; this is a separate, reportable defect in
   the collector/scheduler wiring, independent of this backtest's question.
2. **Structural gap, orthogonal to (1):** even a fully-populated PIT store
   could never answer this question. `compute_congress_scores`
   (`backend/services/congress_trades.py`) snapshots only the aggregate
   `n_buy_members − n_sell_members` per ticker; member identity is
   aggregated away before the PIT write. A leadership-vs-rank-and-file split
   needs the member-level record (who traded what, when), which the
   pipeline as built discards. Splitting "the already-accruing snapshot
   table" was not possible even in principle — the table doesn't carry the
   field the split needs.
3. **One live fallback fetch** (`congress_trades.fetch_congress_trades`
   equivalent, budget-aware, `priority=True` per the trial's own reserved
   slice): **FMP 402 — daily quota exhausted** before this script's first
   call completed (`fmp_budget`'s in-process ledger had counted only 1 spend
   when the live 402 arrived, confirming the account-level quota, not this
   script, was already exhausted by other traffic today). No raw
   disclosures were retrieved.

Net: **0 purchases** in either group from either source. The 30-purchase
floor is not close — it is a 100% data-availability failure, not a marginal
sample-size problem.

## What was built anyway (for reuse once data exists)

- A hand-built, explicitly-marked-as-constructed leadership/committee-chair
  roster for the 119th Congress (2025-2026), 32 names — chamber leaders
  (Speaker, Majority/Minority Leader and Whip in both chambers, President
  pro tempore) plus a sample of full-committee chairs in both chambers.
  **Not** a complete roster (no subcommittee chairs, no mid-term
  reassignments modeled). Sources (via web search, 2026-09-20):
  - https://www.congress.gov/browse
  - https://www.senate.gov/senators/leadership.htm
  - https://www.senate.gov/general/committee_assignments/assignments.htm
  - https://www.acr.org/News-and-Publications/New-Congressional-Committee-Leadership-Named-as-119th-Congress-Begins
  - https://scalise.house.gov/press-releases/Scalise-Applauds-Committee-Chairs-for-119th-Congress
- A raw fetcher that preserves `firstName`/`lastName` (the collector's own
  normalization drops these for Senate rows in favor of an opaque
  `senateID`, which cannot be matched to the roster).
- The full forward-return / Newey-West / circular-shift-null methodology,
  gated behind the power check, ready to run once (a) the collector is
  fixed to actually accrue, or (b) a member-level table is added alongside
  the aggregate score.

## What this implies for the roadmap item

`research_horizon_and_winners.md` §5 item 1 should be read as
**BLOCKED_ON_COLLECTOR**, not as a cheap same-day test. Two prerequisites,
neither done here (out of scope — no edits to existing files, no orders):

1. Fix `congress_morning_collect` so it actually writes (`writes: null` on
   its only-ever receipt is itself worth a `silent-fragility-audit` pass —
   the job reports `"status": "ran"` with no exception while writing
   nothing, which is exactly the house failure mode CLAUDE.md names: code
   that runs green and does nothing).
2. Persist member identity (name + chamber + committee, if a mapping is
   ever added) alongside the aggregate score, or add a parallel
   member-level table — the aggregate-only design is adequate for the
   registered IC trial but insufficient for this or any other
   member-conditioned question.

Until then, this idea has **no data to test on**, independent of leadership
status being a real-or-fake effect.

## Headline numbers (all zero — see verdict)

| Metric | Value |
|---|---|
| PIT store `congress_score:*` rows | 0 |
| Job receipts ever for the collector | 1 (2026-09-07, `writes: null`) |
| Live fetch status | `error` — FMP 402 (daily quota exhausted) |
| Purchases, leadership group | 0 |
| Purchases, non-leadership group | 0 |
| Floor required per group | 30 |
| Backtest run? | No — refused before execution |
| llm_spend_usd | 0.0 |
