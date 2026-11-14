# Rolling live cohorts of the branching population: strategy contract, 2026-11-14

**Licence: `PRODUCT_EXPERIMENT`** (internal simulated paper books, not broker accounts). This is a
frozen strategy contract, not a pre-registration: no significance gate, no MDE gate, no 24-month
floor. It permits internal simulation only. It does not permit any claim of skill, any promotion
to `CAPITAL_CANDIDATE`, or any order.

Row: CH-16 / M3 (branching population). Owner decision 2026-11-14: keep every population live,
re-enter on the 21-session rhythm, collect data points that later backtests can read; fixed
weights cannot be a test.

## Policy identity (the hash a book is frozen under)

- Spec file: `docs/TRIALS/ROLLING-COHORTS-SPECIFICATIONS-v2.json`, schema `rolling_population_specs/2`.
- **Policy manifest hash** (sha256 of the parsed spec document, sorted keys, compact separators,
  the `branch_population.digest` rule): `3505cb4f370a94506d8ef31568a43c40b24da959dd4d72c7518bb3ecab0a3c4f`.
- Parent manifest (the 2026-10-15 file, unchanged): `395304089d999350f9a510978cb801f83bb4f39cffab86a9e68559e9d12bbce1`.
- 1,137 specs: the runnable 10-15 specs with their ORIGINAL policy ids and semantic hashes
  (news_only 261, revision_flow 364, net_raises 108, hybrid_news_revision 260), plus two families
  that need only bars: `low_risk` 72 and `momentum_12_1` 72. Excluded with a recorded reason: the
  three `no_news_control` cash books (replaced by the controls below) and four research-only
  families with no dated input adapter.
- A born book's id is `digest([spec semantic_sha256, cohort date, inputs hash])[:24]`.
- A changed spec file is a NEW population with its own output folder. The runner refuses (exit 2)
  when the manifest differs from the one in `declaration.json`, or when any spec no longer hashes
  to its declared semantic hash.

## Cohorts and timestamps

- Anchor: cohort date 2026-10-15 (the 10-15 freeze day). Cadence: every 5 XNYS sessions after it
  (`ROLLING_COHORT_CADENCE_SESSIONS`). Every spec is entered once per cohort.
- Fill convention: entry at the OPEN of the first session E after the cohort date D (the
  `llm_portfolio` rule). Buy and hold, no rebalance, no stop. A name with no valid open at E waits
  in cash at 0% until its first valid open (grade rule v2), never re-weighted onto the others; a
  halted or delisted name is held flat at its last close.
- Marks at 5, 10, 15, 21, 42, 63, 84, 105, 126 sessions (close of session E+k−1), each book only
  up to its own declared horizon (21, 63 or 126). Random controls are marked to 126.
- Two clocks per cohort:
  - `available_before_utc` = E at 00:00 UTC, the information cutoff. Bars dated <= D; revisions
    with `event_date < D` and `first_seen_utc` before the cutoff; news with `cached_utc`,
    `first_seen_utc` and `published_utc` before the cutoff.
  - `decision_utc` = D at 21:00 UTC, the reference for each spec's `max_age_days` freshness.
- Forward birth only between D's bars arriving and E's opening bell. A cohort whose entry has
  opened is never born forward. It can be backfilled, and then every row carries
  `backfilled: true`.
- Backfilled rows are **never forward evidence** (the "no backfilled forward evidence" rule) and
  are excluded from the forward view of every scoreboard. They are usable as backtest data.

## Inputs (all local, dated, $0 LLM, no network)

- Bars: `prices_2025_26/bars.parquet` (survivor-selected panel: see `xs_ranker.survivorship_audit`).
  Features: 63-session volatility, 252-session beta to SPY with SE, 12-1 momentum, 63-session
  median dollar volume giving the `xs_ranker` liquidity band. Eligible means: last bar within
  5 days of D, close >= $3, not an ETF or index proxy.
- Revisions: `analyst/target_revisions.parquet` through `revision_flow.compute` (90-day window,
  strict prior-date events, whole-frame `pit_safe` refusal). Family WAIT_INPUT when fewer than
  `ROLLING_COHORT_REVISION_MIN_EVENTS` (200) events, or when the newest `first_seen_utc` is more
  than `ROLLING_COHORT_REVISION_MAX_STALE_DAYS` (6) days before the cutoff.
- Typed news sentiment: `news_corpus/_digest_cache/extract_wd_v1.jsonl`, with the 10-15 adapter's
  admission rules. It is UNVERIFIED model context, not fact. Family WAIT_INPUT when fewer than
  `ROLLING_COHORT_NEWS_MIN_ITEMS` (50) usable items fall in the 5 days before the decision, or when
  the newest cached row is more than 2 days old. A WAIT_INPUT is a row in the cohort with the
  count, never a silent skip and never an entry on stale news.

## Mechanisms

- The 10-15 families use `branch_population.targets()` unchanged: 95% gross target, 5% per-name
  cap, no renormalisation after clipping, so ten names hold 50% invested and 50% cash.
- `low_risk`: the lowest quintile of `vol63` (or of positive `beta252`) inside the liquidity
  segment, then the `max_names` lowest. Equal weight or inverse-vol, same clipping.
- `momentum_12_1`: the top quintile of 12-1 momentum, then the `max_names` highest. With
  `hedge: spy_beta` the book also shorts SPY at Σ wᵢβᵢ (pre-entry 252-session betas), clipped to
  [0, 1.5]. With `hedge: none` it is the long leg alone. The two form a declared pair.

## Costs (never omitted)

- Each name pays the `xs_ranker` band round trip for its band at birth (mega 6, large 10, mid 18,
  small 35 bps): half at entry, half at the mark. `ret_net` is round-trip net;
  `ret_net_entry_only` follows the `llm_portfolio` convention.
- A SPY short leg pays SPY's 6 bps round trip, plus a borrow fee of
  `ROLLING_COHORT_SHORT_BORROW_BPS_YR` (30 bps a year) accrued per session held. Cash and short
  collateral earn nothing, which is conservative.

## Controls

- SPY at the SAME invested share (long gross minus short gross), net of SPY's cost.
  `excess_same_share` is the unit the scoreboard reports.
- `ROLLING_COHORT_RANDOM_CONTROLS` (5) random portfolios per DISTINCT holding set per cohort.
  Each replaces names one for one with live names from the same liquidity band, keeping the same
  weights and the same short leg. When a band runs out, the draw comes from any live name
  (`band_fallbacks` counts these). Seeds are `sha256(tag|cohort|holdings|k)[:15 hex]`, tag
  `rolling-cohorts-v2|2026-11-14`. That is far above every literal seed in the repository, so no
  seed is reused.
- Results are reported per distinct portfolio and per declared pair that actually differs
  (hybrid vs its no-news twin; hedged vs unhedged momentum). Pairs with identical holdings are
  counted and excluded.

## Objective and what is reported

- Objective: terminal wealth relative to SPY at the same invested share, per spec, measured
  across many entry dates. One table, append-only: `marks/part-<run>.parquet`, one row per
  (book or control, mark).
- Scoreboard per spec and per family at 21, 63 and 126 sessions: number of cohorts, mean excess,
  SE on NON-OVERLAPPING cohort-date blocks (block = horizon in sessions, so overlapping cohorts are
  not counted as independent), MDE = 2.8 × SE, by-month means, leave-one-cohort-out range,
  distinct-portfolio count, excess over the random controls. Label `OBSERVED(n)` only. The verdict
  is "CANNOT DETERMINE" until there are at least two blocks and |mean| exceeds the MDE. There is
  no promotion logic here: stopping weak specs from being re-entered is CH-16 proper, a separate
  change.

## What never relaxes

No information acted on before it was public (the two clocks; a test with poisoned future rows
pins it). No target leakage. Costs never omitted. A born book is immutable: write-once files,
refused on rewrite. No LLM authority, no broker call, no order.
