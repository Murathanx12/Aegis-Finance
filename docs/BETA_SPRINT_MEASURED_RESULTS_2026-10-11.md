# Beta sprint measured results — 2026-10-11

## Money results first

These are dated historical paper or simulator results from existing books, not results from the new Beta cohort. They show outperformance over the stated windows; they do not establish that a strategy always works. Exact dollars and fills are unavailable and are not inferred here.

| Existing book | Window and mode | Book | SPY | Difference | Additional evidence |
|---|---|---:|---:|---:|---|
| RF `revision_flow_v0` | Sep 28–Oct 9; 10 sessions; SIM PERSONAL | +10.599% | +1.330% | +9.269 pp | No matched-random result available. Top gross active names before costs: MDB and ZS. |
| NR `lib_net_raises_2026-09-26` | Same 10-session window; SIM LIB | +9.759% | +1.330% | +8.429 pp | Matched-random same-band gap: 7.066 pp. Top names: OKTA and GTLB. |
| Broker Hack2 | Aug 28–Oct 9; 30-session window | +5.517% | +1.219% | +4.298 pp | Actual series available for 10 of 30 sessions. ZS leads open unrealized P&L; closed-lot results are unknown. |

Retained loser comparisons are website lane `mirror`, June 16–October 9, −24.547% versus +4.289% SPY; broker paper `hack4`, August 28–October 9, −22.048% versus +1.219%; and broker paper `hack6`, August 28–October 9, −18.183% versus +1.219%. These are separately dated original records, not a pooled comparison.

RF, NR, and Hack2 are separate old books and baselines, not the new Beta. The RF and NR numbers are simulator returns; Hack2 is a broker paper series with only 10/30 sessions available. Do not combine these books or infer exact dollars, fills, or a realized cash result. The approved review is [baseline-current-review.json](../../aegis-recovery-evidence/beta-build-sprint-20261011/baseline-current-review.json); the earlier descriptive preview is preserved in [baseline-current/manifest.json](../../aegis-recovery-evidence/beta-build-sprint-20261011/baseline-current/manifest.json). Later qualification admitted 100 of that original 103-name subset. Its actual-metadata review is [baseline-actual-metadata-review.json](../../aegis-recovery-evidence/beta-build-sprint-20261011/baseline-actual-metadata-review.json), pinned at SHA-256 `d4105c77aa3de853b50ce6e3cce5d57fbe35b83d8316db7ccd9ad845d8c7a01d`. These evidence links are local private receipts; their payloads are intentionally absent from GitHub.

## What the strategy rules imply

RF selects the top 20 revision-flow names by net raises multiplied by the number of firms, requires at least three firms, rebalances on a 21-session cadence, and historically used 5% per name. NR selects the top 20 by net raises without the three-firm gate, rebalances monthly at month end, and historically used 5% per name. The original 126/63 policy is preserved.

Broker Hack2 v1 makes no new entries, uses a five-weekday horizon, and has a 4–8% stop range. Hack2 v2 is **proposed only**: a 21-session horizon from fill with a 4–12% stop range. No policy choice or activation is recorded. The full baseline universe, authentic WLS MEMB gate, TMSG rules capture, and contest window remain unverified.

## Probability evidence and consumer acceptance

The independent actual-semantic review reports:

| Forecast cohort | Pairs | Brier | Log loss |
|---|---:|---:|---:|
| H1 IEF | 1 | 0.28579716 | 0.76485803 |
| H1 SPY | 490 (3 unavailable) | 0.266844789 | 0.727409249 |
| H2 SPY | unavailable | unavailable | unavailable |
| H5 SPY | 472 (9 unavailable) | 0.254055932 | 0.701450250 |

A constant 0.5 forecast has Brier 0.25, so these SPY cohorts are worse on that measure. Equal, adaptive, and without-analyst variants are numerically identical. Without-news, RF, and NR controls abstain; abstentions are not zero forecasts. Aligned historical analyst inputs are unavailable. These are probability scores, not P&L, fills, or portfolio results. The review is [actual-review.json](../../aegis-recovery-evidence/beta-build-sprint-20261011/consumer-semantic-cycle2/r2/actual-review.json), SHA-256 `d6789a043a03b2cf6c7a7b42fc61321fde07b2436e2cbbe48c6b45d9528cd36c`.

The original forecast as of `2026-10-11T07:03:24.082354Z` was reprocessed at `2026-10-11T11:25:55.111093Z`; reprocessing is not a new point-in-time forecast. The primary consumer reports `RETURN_INPUTS_UNAVAILABLE`, with null cash and zero holdings. H5 derived return count is zero because outcome availability starts Oct 7, after the last forecast on Oct 1.

The new Beta H21 fit is PARKED after two memory refusals: the second attempt reached an observed 3,235,880,960-byte process peak against a 3 GiB limit. This is not a cash signal and does not disable the older baselines. Six months of authenticated point-in-time coverage is not established for this joined cohort. The current analyst first-seen window is 90 days (Jul 13–Oct 11); it does not provide six months of retrospectively qualified data.

## Learning receipts and coverage limits

The protected-stream projection reports 1,510 graded, 4,343 pending with due qualification unavailable, 5 void, and 2 WBD blocked records. Pending does not establish that a record is not yet due. The replay covers 1,510 original grades: 989 policy entries and 976 decisions; 1,469 older grades are available, of which 989 are verified and 480 are original-only; 41 are unavailable (40 basis unknown adjustments and 1 outside-window). Keep these populations separate; do not add them together.

The actual learning trace records 22 new grades with two licensed versus zero without. Fit/build ran with `write=False`; weights remained equal. This is a learning-process result, not historical P&L evidence.

The accepted output census remains partial: 519 family buckets and 791 task/horizon cells, `complete=false`. Inaccessible and protected coverage means unknown, not empty; pending is not a verified not-yet-due count. The detailed family/cell coverage packet is [beta-coverage-learning-acceptance-v2.json](../../aegis-recovery-evidence/beta-build-sprint-20261011/coverage-release-packet/beta-coverage-learning-acceptance-v2.json), SHA-256 `ca96f9761d7c45b0dacdc78195ae136885b78fd11e3686f8713f921f4b44c071`. These counts do not establish that all outputs are reconciled.


