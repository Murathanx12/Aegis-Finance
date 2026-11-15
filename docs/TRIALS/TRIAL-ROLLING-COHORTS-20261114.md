# Rolling live cohorts of the branching population: strategy contract, 2026-11-14

**Contract version 2** (2026-11-15, the PR #147 review fix round). It supersedes version 1, whose
text hashed to `51b298ec65fa993d98e7ea6a609de06121f6a06cc3baaf15b11e1c9ef2d4c348` (sha256,
LF-normalised; commit 3cf70c2c).

No cohort was ever born forward under version 1. The only cohorts that existed were dry runs in a
builder's report folder. So no book that entered forward paper is changed by this version.

This file's LF sha256 is part of every population's frozen config snapshot (`contract_sha256_lf`).
A population declared under one version refuses to run under another.

What changed from version 1:
- One clock instead of two.
- Strict 2 x horizon blocks, a Student t, a 6-block floor and BH-FDR, instead of z = 2.8 on
  horizon-wide blocks.
- Costs <= 0 are refused, and the grading config is frozen.
- Ages and "due" run on the exchange calendar, with an 18 h price grace and late births.
- Cutoff-first news dedupe.
- Input drift is recorded.
- Rows now carry flags for the adjusted-price filter, the unversioned revisions file and the
  panel's universe date.

**Licence: `PRODUCT_EXPERIMENT`** (internal simulated paper books, not broker accounts). This is a
frozen strategy contract, not a pre-registration: no significance gate, no MDE gate, no 24-month
floor. It permits internal simulation only. It does not permit any claim of skill, any promotion
to `CAPITAL_CANDIDATE`, or any order.

Row: CH-16 / M3 (branching population). Owner decision 2026-11-14: keep every population live,
re-enter on the 21-session rhythm, collect data points that later backtests can read; fixed
weights cannot be a test.

## Policy identity (the hash a book is frozen under)

- Spec file: `docs/TRIALS/ROLLING-COHORTS-SPECIFICATIONS-v2.json`, schema `rolling_population_specs/2`.
  It is UNCHANGED by contract version 2: same file, same ids, same meaning.
  - A spec's `max_age_days` still means "the newest qualifying event is at most N days old at the
    decision".
  - What version 2 defines is the decision clock itself (below). That is a contract-level
    definition, so no spec id changes.
- **Policy manifest hash** (sha256 of the parsed spec document, sorted keys, compact separators,
  the `branch_population.digest` rule): `3505cb4f370a94506d8ef31568a43c40b24da959dd4d72c7518bb3ecab0a3c4f`.
- Parent manifest (the 2026-10-15 file, unchanged): `395304089d999350f9a510978cb801f83bb4f39cffab86a9e68559e9d12bbce1`.
- 1,137 specs, in two groups:
  - The runnable 10-15 specs, with their ORIGINAL policy ids and semantic hashes: news_only 261,
    revision_flow 364, net_raises 108, hybrid_news_revision 260.
  - Two families that need only bars: `low_risk` 72 and `momentum_12_1` 72.
- Excluded, with a recorded reason: the three `no_news_control` cash books (replaced by the
  controls below), and four research-only families with no dated input adapter.
- A born book's id is `digest([spec semantic_sha256, cohort id, inputs hash])[:24]`.
- `declaration.json` freezes three things: the spec manifest, the grading-config snapshot (every
  `ROLLING_COHORT_*` grading key, `xs_ranker.COST_BPS_BY_BAND`, `xs_ranker.MIN_PRICE`, and this
  file's hash) and its `config_hash`.
- A later run is refused (exit 2) in three cases:
  - the manifest differs;
  - any spec no longer hashes to its declared semantic hash;
  - any grading-config key differs. The refusal names each differing key.
- Operational knobs (lock wait, price grace, staleness cadences) are not part of the grading config.
- Every cohort and every mark row carries `config_hash` and `code_version` (the git sha, when
  it is knowable).

## Cohorts and the one clock

- Anchor: cohort date 2026-10-15 (the 10-15 freeze day). Cadence: every 5 XNYS sessions after it
  (`ROLLING_COHORT_CADENCE_SESSIONS`), counted on the EXCHANGE calendar, never on the dates
  present in the bars file. Every spec is entered once per cohort.
- Fill convention:
  - Entry is at the OPEN of the first session E after the decision date D (the `llm_portfolio`
    rule). Buy and hold: no rebalance, no stop.
  - A name with no valid open at E waits in cash at 0% until its first valid open (grade rule v2).
    It is never re-weighted onto the other names.
  - A halted or delisted name is held flat at its last close.
- Marks are at 5, 10, 15, 21, 42, 63, 84, 105 and 126 sessions (the close of session E+k−1).
  Each book is marked only up to its own declared horizon (21, 63 or 126). Random controls are
  marked to 126.
- **One clock**: the cutoff is E at 00:00 UTC.
  - A row is admitted only if it is dated AND first seen strictly before the cutoff:
    - bars dated <= D;
    - revisions with `event_date` (naive UTC) and `first_seen_utc` before the cutoff;
    - news with `cached_utc`, `first_seen_utc` and `published_utc` before the cutoff.
  - The same cutoff is the reference for every `max_age_days`. So "fresh in the last day" means
    the 24 h before the cutoff.
  - Version 1 admitted revisions before D 00:00 but aged them from D 21:00. That left a 1-day spec
    a 3-hour window.
- News versions are deduplicated only AFTER the cutoff is applied. A re-typing cached later can
  never change an earlier cohort.
- Forward birth happens only between D's bars arriving and E's opening bell.
- **The evening price wait.** When the exchange has closed a session the bars do not have yet:
  - Within `ROLLING_COHORT_PRICE_GRACE_H` (18 h) of that close, the step reports WAIT_PRICES with
    rc 0.
  - Past the grace it reports STALE_PRICES ("bars have not advanced since <date>"), and the health
    readers go DEGRADED.
- **Missed slots.** A scheduled slot whose entry opens before its bars can be read is listed as
  MISSED. When the bars return, the newest missed slot is born LATE:
  - it is decided on the newest bars, its true `decision_date`;
  - it enters at the next open;
  - it carries `born_late: true`;
  - it is never backdated.
- A cohort whose entry has opened is never born forward. It can be backfilled, and every
  backfilled row carries `backfilled: true`. Backfilled rows are **never forward evidence** (the
  "no backfilled forward evidence" rule) and are excluded from the forward view of every
  scoreboard. They are usable as backtest data.

## Inputs (all local, dated, $0 LLM, no network)

- **Bars:** `prices_2025_26/bars.parquet`.
  - The panel is survivor-selected. Its symbol list came from a universe file dated
    `ROLLING_COHORT_PANEL_UNIVERSE_ASOF` (2026-09-01). Every bars-only book carries
    `panel_universe_asof`.
  - Features: 63-session volatility; 252-session beta to SPY with its SE; 12-1 momentum; and the
    63-session median dollar volume, which gives the `xs_ranker` liquidity band.
  - Eligible means: last bar within 5 days of D, close >= $3, not an ETF or index proxy.
  - The panel is adjusted (`adjustment=all`), so in a backfill the $3 filter reads a price
    adjusted for events after D. Backfilled and late-born books carry
    `price_filter_uses_adjusted: true`. Each cohort counts the names within a factor of 2 of the
    threshold (`n_names_min_price_ambiguous`).
- **Revisions:** `analyst/target_revisions.parquet`, through `revision_flow.compute`: a 90-day
  window at the cutoff, and a whole-frame `pit_safe` refusal.
  - The family is WAIT_INPUT when there are fewer than 200 events, or when the newest
    `first_seen_utc` is more than 6 days before the cutoff.
  - The writer keeps the newest values under the oldest `first_seen` (pull_analyst_targets.py,
    outside this contract). So every backfilled revision book carries
    `revisions_file_not_versioned: true`.
- **Typed news sentiment:** `news_corpus/_digest_cache/extract_wd_v1.jsonl`, with the 10-15
  adapter's admission rules. It is UNVERIFIED model context, not fact.
  - The family is WAIT_INPUT when fewer than 50 usable items fall in the 5 days before the
    cutoff, or when the newest cached row is more than 2 days old.
- A WAIT_INPUT is a row in the cohort with its count. It is never a silent skip, and never an
  entry on stale news.
- **Input drift.** A backfill re-derives the inputs of every existing cohort in its range, and a
  step re-derives the newest cohort. A differing hash is written as an `input_drift` row with the
  old and new hash. The born book is never changed.
- Input snapshots are written temp then replace. They are reused only when the size and sha256
  match the record.

## Mechanisms

- The 10-15 families use `branch_population.targets()` unchanged: a 95% gross target, a 5%
  per-name cap, no renormalisation after clipping. So ten names hold 50% invested and 50% cash.
- `low_risk`: the lowest quintile of `vol63` (or of positive `beta252`) inside the liquidity
  segment, then the `max_names` lowest. Equal weight or inverse-vol, with the same clipping.
- `momentum_12_1`: the top quintile of 12-1 momentum, then the `max_names` highest.
  - With `hedge: spy_beta` the book also shorts SPY at Σ wᵢβᵢ (pre-entry 252-session betas),
    clipped to [0, 1.5].
  - With `hedge: none` it is the long leg alone. The two form a declared pair.

## Costs (never omitted)

- Each name pays the `xs_ranker` band round trip for its band at birth (mega 6, large 10, mid 18,
  small 35 bps): half at entry, half at the mark.
  - `ret_net` is the round-trip net.
  - `ret_net_entry_only` follows the `llm_portfolio` convention.
- A SPY short leg pays SPY's 6 bps round trip, plus a borrow fee of 30 bps a year accrued per
  session held. Cash and short collateral earn nothing, which is conservative.
- **Any cost <= 0 is refused** (bands, SPY, borrow), unless
  `ROLLING_COHORT_ZERO_COST_DIAGNOSTIC` is set. When it is, every cohort and every mark row carries
  `zero_cost_diagnostic: true`.

## Controls

- SPY at the SAME invested share (long gross minus short gross), net of SPY's cost.
  `excess_same_share` is the unit the scoreboard reports.
- 5 random portfolios per DISTINCT holding set per cohort.
  - Each replaces names one for one with live names from the same liquidity band, and keeps the
    same weights and the same short leg.
  - When a band runs out, the draw comes from any live name (`band_fallbacks` counts these).
  - Seeds are `sha256(tag|cohort|holdings|k)[:15 hex]`, tag `rolling-cohorts-v2|2026-11-14`.
    That is far above every literal seed in the repository, so no seed is reused.
- Declared pairs are reported only where the holdings actually differ (hybrid vs its no-news twin;
  hedged vs unhedged momentum). Pairs with identical holdings are counted and excluded.

## Objective and what is reported

- Objective: terminal wealth relative to SPY at the same invested share, per spec, measured
  across many entry dates.
- One append-only table: `marks/part-<run>.parquet`, one row per (book or control, mark). One
  pass runs at a time (`run.lock`). Duplicate (book_id, mark_k) rows fail loud and are never
  counted.
- **Scoreboard** at 21, 63 and 126 sessions:
  - **One test per DISTINCT portfolio series.** Specs whose holdings agree in every cohort are one
    test, which lists its specs.
  - **SE method: strict blocks.** Block means on non-overlapping blocks of 2 x horizon sessions of
    the entry date. A hold cannot reach two blocks ahead, so blocks two apart are independent.
    Adjacent blocks still share a few sessions.
  - Mean of the block means; a Student t with n_blocks − 1 df; MDE = (t₀.₉₇₅ + t₀.₈₀) x SE.
    `n_blocks_strict` is printed.
  - Also printed per test: by-month means, the leave-one-cohort-out range, the distinct-portfolio
    count, and the excess over the random controls.
  - **No label below 6 strict blocks**: the verdict reads "CANNOT DETERMINE (n blocks of 6)".
  - **Multiplicity.** BH-FDR at q = 0.05 across the distinct tests of one run. The header prints
    "crossings expected by chance: x; observed: y".
  - Measured under pure noise (400 to 2,000 null specs per cell):
    - Labelled share: 0.000 to 0.003, against 0.003 to 0.115 under version 1's rule.
    - Raw p < 0.05 share: 4.1 to 5.4% with independent holds; 6 to 8% with overlapping weekly
      21-session holds (adjacent blocks share sessions).
    - It is the floor and BH that keep the labels below the nominal rate.
  - Labels are `OBSERVED(n)` only. There is no promotion logic here: stopping weak specs from
    being re-entered is CH-16 proper, a separate change.

## What never relaxes

- No information acted on before it was public: the one clock. A test with poisoned future rows
  pins it.
- No target leakage.
- Costs are never omitted.
- A born book is immutable: write-once files, refused on rewrite.
- No LLM authority, no broker call, no order.
