# C18 build note: reputation-weighted analyst consensus and the snowball shadow series (2026-10-07)

> **AMENDED AFTER REVIEW** (`docs/reviews/REVIEW_2026-10-07_C18_ANALYST_REPUTATION.md`, 52/100: mergeable
> as plumbing, not as a signal). The amendment section directly below supersedes §1-§4 wherever they
> disagree. §1-§4 are kept as written so the record of the first pass stays readable.

## AMENDMENT (review F1-F11)

**RESULT IMPROVEMENT: NONE.** The reputation weight **does not persist out of sample**. It is now
labelled everywhere it appears: **`REPUTATION_WEIGHT: NOT_PERSISTENT_OOS (rho -0.32; -0.28 month x
direction)`**. It is computed as plumbing and is not presented as skill.

### F1: persistence receipt

Receipt: `backend/data/optimus/analyst/reputation_persistence_20261006T230005Z.json`, produced by
`analyst_reputation.persistence_test`.

**Method.**

- Split at the median event date, 2025-10-17: 72,108 claims, 36,054 in each half.
- Claims are clustered by (firm, ticker, month, direction), so one ticker-month counts as one outcome.
- Firm edges are scored two ways: against the pooled direction base rate, and against the matched
  month x direction base rate.

**Split-half rank correlation of firm edges, first half vs second half:**

| min clusters per half | firms | Spearman, pooled base | Spearman, month x direction |
|---:|---:|---:|---:|
| 20 | 52 | -0.247 | -0.091 |
| 50 | 46 | -0.359 | -0.187 |
| 100 | 41 | -0.313 | -0.169 |

**The module's own weights.** I ran the full weighting on the first half alone and scored it against
the second half's edges (48 firms, at least 50 clusters each in the second half):

- Spearman **-0.32** against the pooled-base edge.
- Spearman **-0.28** against the month x direction edge.
- Firm-bootstrap 95% CI: **[-0.53, +0.01]** (n_boot 500, seed 7,100,020).
- Verdict: **NOT_PERSISTENT_OOS**.

The label sits on the weights receipt, on every Explorer row (`analyst_reputation.label`), in the
Explorer `legend` and `inputs`, and first in the page tooltip.

### F2: point-in-time status, printed on the weights receipt

The weights receipt is `reputation_weights_2026-10_20261006T230005Z.json`, schema
`analyst_reputation/2`. What its `pit` block records:

- **99.93%** of rows carry `pulled_at` 2026-10-06.
- The file has no `first_seen_utc` column, so `status: NOT_PIT`. PIT rests on the vendor's `event_date`
  alone.
- At any past as-of, the first-seen filter admits only rows the vendor stopped confirming. That sample
  is adversely selected.

`scripts/pull_analyst_targets.py` already writes `first_seen_utc` with MIN semantics (lines 300-317).
The column name is confirmed and the loader uses it. The column will exist from the next pull, so no
pull edit was needed.

### F3-F6: what the Explorer shows

**Removed from the upside cell:** `n_effective`, `weighted_upside`, `weight_bearing_firms` and the
"n_eff X of Y firms" wording. `weighted_stance` is also gone from `analyst_stance`.

**Now shown:** the row's `analyst_reputation` block, every number from the revision file. On the page
it reads "revision file: N firms, sum w S". The label leads the tooltip, and firm weights are captioned
"not skill". The yfinance count `n_targets` stays where it was and is never set against the
revision-file numbers.

**Weighted target and upside.**

- The weighted target uses only firms whose latest row is at most 90 days old. Otherwise it is null
  with `stale_target`. With a single firm it is null with `single_firm`.
- The weighted upside exists only in the receipt, as `weighted_upside_DIAGNOSTIC_ONLY`. It is never
  displayed.

**The owner's names now** (roi_v3 rows, receipt `opportunities_2026-10-06_20261006T225957Z.json`; all
five are still `EXCLUDED_BY_v3.2_RULE`):

| ticker | yfinance count (shown as before) | revision-file firms | sum of weights | weighted target |
|---|---:|---:|---:|---|
| QUBT | 6 | 6 | 6.72 | diagnostic only (not shown) |
| KYTX | 5 | 4 | 4.52 | null: stale_target |
| SOC | 4 | 5 | 5.77 | diagnostic only (not shown) |
| SLDP | 2 | 2 | 2.09 | null: stale_target |
| NOVT | 2 | 1 | 1.11 | null: stale_target |

### F8: the frozen weight map

The weights receipt's `map_note` records that slope 10 and clip (0.5, 1.5) were frozen on 2026-09-26
for an edge shrunk toward zero. Under this module's shrinkage:

- 12.5% of cells sit at the lower clip and 12.0% at the upper clip.
- The review measured 37.6% of displayed firm weights at a clip.

The map was not re-tuned.

### F9: snowball base rate and summary

The base rate is now a declared trailing 24-month window (`SNOWBALL_BASE_WINDOW_MONTHS`). The ledger
moved to schema 1.1.0. The 1.0.0 ledger was renamed, not edited:
`snowball_shadow_schema1.0.0_20261006T230044Z.jsonl`.

`summary()` now reports REPLAY and FORWARD separately:

| | rows | graded | Brier | constant-rate baseline (look-ahead) |
|---|---:|---:|---:|---:|
| REPLAY | 23,362 | 22,733 | **0.2091** | 0.2098 |
| FORWARD | 8 | 0 | n/a | n/a |

The all-history base rate had scored 0.2110. The forward rows are open, with first grades due
2027-01-05/06.

### F10: power line on the rho receipt

Receipt: `snowball_rho_20261006T230108Z.json`. It supersedes the 214926Z receipt, which stays on disk.

- rho = **0.0196**, CI [0.0102, 0.0267]. The first receipt read 0.0199 on the same data; the cause of
  the difference was not investigated.
- Measured sd = 12.12pp, so n_required ≈ **7,207**.
- On yfinance's **14.8 years** there are about **6,493** usable observations (about 5,163 at the upper
  rho). Verdict: **NOT_RELINTABLE_ON_THIS_CORPUS**.
- The 11k figure holds only if the IBES t0 count supports 26 years.
- The declared 0.4pp effect is about the size of the ~35 bps 21-day toll. The surrogate's own mean is
  -0.67% per 21 sessions vs SPY.

### F11: receipts are immutable

- Weights receipts now carry a run id. A month's receipt is read back only if it has the current
  schema; an older-schema receipt stays on disk and is never rewritten. The 2026-10 `/1` file is kept
  untouched.
- `opportunities_build --dry-run` now writes nothing (`monthly_receipt(write=False)`).
- Writes refuse an existing path.

### Tests

The "thin coverage" test now asserts the actual ordering under unequal weights (A 1.5 before B 0.5,
weighted stance `(wa - wb) / (wa + wb)`). New tests:

- `n_covering_firms` never exceeds the firms in the file.
- Stale and single-firm targets are null.
- Persistence reads synthetic persistent and reversed firms correctly.
- A dry run writes nothing, and receipts are never overwritten.
- The trailing base-rate window works.
- The summary never blends forward rows into replay.

---

## First pass (as written before the review)

**RESULT IMPROVEMENT: NONE.** Nothing here trades and nothing is registered. This chunk shipped three things.
The Explorer now prints `n_effective` beside the raw analyst count for every row, instead of a cliff at
n >= 5. A free shadow series of the snowball follow-through leg now writes rows. The `cross_sectional_rho`
that the snowball draft owed has been measured, so its return leg can be re-linted honestly. Licence:
`PRODUCT_EXPERIMENT`. Spend: $0, no LLM, no network.

Spec: `docs/research_notes/2026-10-07/analyst_reputation_spec_2026-10-07.md`. Constants were frozen in
`backend/config.py` (`ANALYST_REP_*`, `SNOWBALL_*`) before any weight or row was read:

- K1 = `pit_features.SKILL_SHRINK_K` = 20, reused and not redeclared.
- K_SUB = 40.
- Snowball: gap 90 days, history 90 days, horizon 63 XNYS sessions, threshold 2, prior pseudo-count 20, forward lag 3 days.
- rho: seed 7,100,018 and 1,000 month-block bootstraps.

## Receipts

| what | path |
|---|---|
| monthly reputation weights (as of 2026-10-06T21:39 UTC) | `backend/data/optimus/analyst/reputation_weights_2026-10.json` |
| Explorer rebuild (one run) | `backend/data/optimus/opportunities/opportunities_2026-10-06_20261006T214339Z.json` |
| snowball shadow ledger | `backend/data/optimus/analyst/snowball_shadow.jsonl` (23,370 rows, 13.7 MB) |
| cross_sectional_rho | `backend/data/optimus/analyst/snowball_rho_20261006T214926Z.json` |
| owner-name rows pinned for the test | `backend/tests/fixtures/analyst_reputation/explorer_owner_rows.json` |

## 1. The weight distribution

**Claims.** Every dated target raise or lower on `target_revisions.parquet` counts as a claim, if the row was
first seen before the as-of. Its outcome is sign x (stock − SPY) over 63 sessions, measured from the close
of the first session strictly after the event day, on `prices_2025_26/bars.parquet`. That gives
**71,843 resolved claims from 110 firms** across 49 sectors and 1,866 (firm, sector) cells. The track
record is about 1.5 years of yfinance revisions (2025-01 onward), not IBES history. The horizon level is
degenerate: every target on disk is 12-month.

**Overall spread.**

- Firm headline weight (claims-weighted mean over the firm's cells): mean 1.003, median 0.99, quartiles 0.81 / 1.22.
- Cells: 12.0% sit at the upper clip (1.5) and 12.5% at the lower clip (0.5).
- **Saturation is a property of the frozen map, not of this chunk.** `SKILL_SLOPE = 10` reaches the clip at
  |edge| = 0.05. So a firm with one or two resolved claims, in a sector whose prior has the same sign, can
  land on the clip. This was not retuned, because that would be a parameter chosen after looking. The
  top-10 list below is therefore mostly thin firms, and the list worth reading is the one restricted to
  n >= 200.

**Top 10 by weight** (firm, n resolved claims, raw edge, weight):

| firm | n | raw | weight |
|---|---:|---:|---:|
| Hovde Group | 8 | +0.384 | 1.500 |
| WestPark Capital | 5 | +0.320 | 1.500 |
| Zelman & Assoc | 4 | +0.509 | 1.500 |
| Noble Capital Markets | 3 | +0.528 | 1.500 |
| BNP Paribas Exane | 1 | +0.453 | 1.500 |
| Brookline Capital | 1 | +0.565 | 1.500 |
| LifeSci Capital | 1 | +0.565 | 1.500 |
| Lynx Global | 1 | +0.565 | 1.500 |
| CIBC | 146 | +0.114 | 1.500 |
| Wolfe Research | 30 | +0.128 | 1.493 |

**Bottom 10 by weight:**

| firm | n | raw | weight |
|---|---:|---:|---:|
| Freedom Capital Markets | 10 | −0.246 | 0.500 |
| Daiwa Capital | 9 | −0.250 | 0.500 |
| Monness, Crespi, Hardt | 3 | −0.176 | 0.500 |
| Alembic Global | 2 | −0.547 | 0.500 |
| Itau BBA | 1 | −0.547 | 0.500 |
| Zero One | 1 | −0.435 | 0.500 |
| D. Boral Capital | 6 | −0.306 | 0.509 |
| Arete Research | 3 | −0.435 | 0.527 |
| Berenberg | 8 | −0.241 | 0.537 |
| Argus Research | 123 | −0.068 | 0.540 |

**Firms with n >= 200 claims** (45 firms):

- Lowest: Macquarie 0.571 (n 223), JMP 0.638 (300), Telsey 0.808 (286), Canaccord 0.815 (903), Deutsche Bank 0.827 (354).
- Highest: Wedbush 1.435 (551), HC Wainwright 1.366 (834), Benchmark 1.364 (567), Roth 1.280 (275), Stephens 1.213 (402).

**What a weight is.** It is a 63-session directional hit rate on 2025-26 revisions, relative to the
direction base rate. It is not a skill claim. ANALYST-SKILL-1 found that this kind of weighting
attenuates an anti-signal consensus rather than adding signal.

**Two point-in-time facts measured while building:**

1. The file has **no `first_seen_utc` column yet**. Rows carry `pulled_at`, which is the time of the LAST
   pull. The first receipt, written with the as-of normalised to midnight, admitted **279 of 395,115
   rows**, because the 10-06 re-pull restamped almost everything. That receipt was deleted and the as-of is
   now kept to the minute. Until `first_seen_utc` exists, a receipt written before the day's pull is thin.
   The run admits rows only, so this cannot leak.
2. Claims count only after their exit session has closed. This is `firm_reliability`'s own filter, called
   three times with three grouping keys. `pit_features.py` is not modified, and its output is pinned
   byte-for-byte in `backend/tests/fixtures/analyst_reputation/firm_reliability_pinned.json`.

## 2. What changed on the Explorer for the owner's names (roi_v3 rows)

| ticker | raw n (yfinance) | covering firms (365 d) | n_effective | weighted stance | weighted upside | dispersion |
|---|---:|---:|---:|---:|---:|---:|
| QUBT | 6 | 6 | 5.52 | +0.63 (flat +0.67) | +101.5% | 0.42 |
| KYTX | 5 | 4 | 3.84 | +1.00 | +295.6% | 0.12 |
| SOC | 4 | 5 | 4.63 | +0.76 (flat +0.80) | +188.2% | 0.05 |
| SLDP | 2 | 2 | 1.87 | +1.00 | +204.4% | 0.00 |
| NOVT | 2 | 1 | 1.00 | +1.00 | +14.9% | n/a (one target) |

- **All five appear with `n_effective` printed.** Before this chunk, each row showed only "N analysts" and an
  `excluded` badge.
- **SLDP, SOC and NOVT were excluded by the n < 5 cliff.** Their rows now carry `upside.cliff_replaced`, with
  the old rule, the raw count and `n_effective`.
- **The frozen v3.2 list's own `EXCLUDED_BY_v3.2_RULE` eligibility is kept.** It is a fact about that list, and
  the list is not re-ranked here. The research-note veto on KYTX, QUBT, SLDP and SOC is unrelated to coverage
  and still stands.
- **Weight-bearing firms.**
  - KYTX: HC Wainwright 1.41 (48 graded in sector), Wells Fargo 1.30 (327), Morgan Stanley 0.92, JP Morgan 0.90.
  - QUBT: Ascendiant 1.50 (5), Lake Street 1.15, Rosenblatt 1.07, Northland 0.54. Wedbush is 1.50 but holds a 0 stance.
- **`weighted_upside` is not the snapshot median.** It is the weighted median of the covering firms' latest
  targets on the revisions file. KYTX: +296% weighted vs +406% at the snapshot median. Both are printed,
  and target-level upside remains the measured-perverse screen it was.
- **On the page.** The upside cell gains a line "n_eff X of Y firms". Its tooltip gives the formula, the
  weighted stance, the old rule and the weight-bearing firms.
- **Coverage across the receipt.** `analyst_reputation` is present on 662 of 700 `analyst_upside_v3` rows and
  63 of 65 `roi_v3` rows. A missing row says why: no firm with a dated action in 365 days.

## 3. The snowball follow-through shadow series: first rows

`backend/services/snowball_shadow.py` builds one row per (ticker, t0 day). t0 means
`crsp_pit_bridges.first_movers(raises, gap_days=90)` on the live file, plus the coverage-start exclusion.
Each row predicts P(>= 2 other distinct firms raise within 63 XNYS sessions).

**Base rate.** The probability is an expanding window: (k + 10) / (n + 20) over t0 events whose window
**closed strictly before** the row's t0 day. It is never the full-sample rate.

**Tonight's run.**

- **23,370 rows**: 22,733 graded REPLAY, 629 open REPLAY, and **8 FORWARD**.
  - The FORWARD rows are AMR, BANC, ECO, FORM, OIS, PCVX and RDN (t0 2026-10-05), and FCFS (t0 2026-10-06).
  - Each has probability ≈ 0.30 and resolves on 2027-01-05/06. These are the **first real grades, 63 sessions from now**.
  - Only FORWARD rows carry the t0 broker's reputation weight. On a REPLAY row, today's weights would be a look-ahead.

**Rows by t0 year:**

| 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 189 | 1,004 | 1,222 | 1,095 | 1,184 | 1,004 | 1,405 | 1,413 | 1,698 | 1,742 | 2,000 | 2,249 | 2,654 | 2,557 | 1,954 |

**What the replay shows.** These are REPLAY numbers, never forward evidence.

- The graded follow-through rate is **29.96% overall**. It rises from 16-25% (2015-18) to 37-41% (2024-26).
- The PIT probability lags that rise: mean 0.27 in 2024 against a realised 0.378.
- Brier, expanding window: **0.2110**. A constant at the full-sample rate scores 0.2098, but that constant
  uses future rows, so it is a look-ahead benchmark and not an admissible one.

**For the signer, not resolved here.** The draft's coverage-start rule is ambiguous. Read literally
(history >= 90 days **before the quiet window**, so first raise <= t0 − 180 d), it gives **23,370 events**,
and that is what was built. Read loosely (history >= 90 days before t0), it gives **24,076**. The loose
reading reproduces the draft's own "10.5% cut" (24,323 on the older file). I did not choose the friendlier
reading. Two smaller differences also lower the rate from the note's 35.9%:

- Same-day co-raisers are all treated as t0 brokers, so none of them counts as a follower.
- Windows are counted in XNYS sessions.

**Grading.** The forecast ledger's resolver reads prices only, so the series has its own grader
(`grade_due`). The test pins that `belief_state.resolve_one` does not grade this observable. The daily caller
is `python -m scripts.task_keeper catalog`, which now runs the `snowball` job after the catalog. It writes
its own keeper row and does not change the catalog's exit code. No new scheduled task was needed.
`task_keeper snowball` runs it by hand.

## 4. cross_sectional_rho, and what it implies for n_required

**What was measured.**

- **Surrogate:** every dated raise, one per (ticker, month). The policy-free surrogate the draft names. Not t0-selected.
- **Return:** 21-session return minus SPY, winsorised 1/99.
- **Grouping:** by event month.
- **Sample:** 18,963 events over 21 months (2025-01 to 2026-09), about 903 per month.

**Result: ICC rho = 0.0199** (month-block bootstrap 95% CI **0.0108 to 0.0274**, n_boot 1,000).

**What it implies.**

- At the draft's own R13 inputs (1,500 events/yr, so 125 per month, over 26 corpus-years), the design effect
  is 1 + 124ρ ≈ 3.5.
- That gives **n_available ≈ 11,241** (CI 8,864 to 16,705), against **n_required 7,064**. The month cap
  allowed only 312.
- The smallest resolvable effect scales to roughly 1.9pp × sqrt(312 / 11,241) ≈ **0.32pp**, below the
  declared 0.4pp.
- On this measurement the return leg plausibly moves from `UNPOWERED_AT_REGISTRATION` to `RESOLVABLE`.
  **That is for `lint_prereg.py` to say on a re-lint with `cross_sectional_rho` declared, not for this note.**

**Caveats** (also on the receipt):

1. 21-session windows that start late in one month overlap the next month's, so month grouping understates
   dependence across adjacent months.
2. The surrogate is all raises. t0 events may cluster differently.
3. rho comes from 2025-26 yfinance only, and the linter's 26 corpus-years are assumed to share it.
4. `outcome_dispersion = 12pp` is still the house preset, not a measured value.

Nothing was signed and the return leg is unchanged. It stays `RETIRED_FROM_CURRENT_SEARCH` until the re-lint.

## Not done, on purpose

- `scripts/contest_direction.py` and `scripts/contest_rehearsal.py` are untouched (the contract hash covers
  their code). Any contest-facing use is a new `ROT5_DIR_v3` shadow book, as the spec §3 says.
- `scripts/stock_lists_v3_build.py`'s `n_an < 5` gate is untouched. The v3.2 list is a frozen, reviewed
  artefact, and this chunk is Explorer-only. `N_EFFECTIVE_MIN` was not added because nothing gates on it.
- `scripts/analyst_skill_1 --run` was not re-run (WRDS, heavy). `pit_features.py` has no diff, and the pinned
  fixture test covers `firm_reliability`.
- `opportunities_build --dry-run` writes the month's reputation receipt if it is absent. A month's receipt is
  never overwritten.
