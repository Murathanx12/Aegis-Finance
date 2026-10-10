# AEGIS Beta measured results — 10 October 2026

This report indexes existing frozen evidence and the independently reviewed replay repair. It does not replace original forecasts, NAVs, fills, costs or earlier failed receipts. PRODUCT_EXPERIMENT only; no alpha claim or activation.

The original paired report is retained in the private evidence bundle as `budgeted-20261010/paired-final/paired_results.json`, SHA256 `564bc54f0943930dc96620dcb4b74c8682059ce8b1c98e3dda83dee9cb4368f4`. Its recorded September 26 inputs reconstruct 51 forecast cells from 18 claims: 17 per horizon. Probabilities mean **beats SPY**, not absolute price direction. The probability-0.50 comparison is a retrospective ablation, not a separately timestamped original forecast. Lower Brier is better.

| Original horizon | Cells | Graded | Not yet due | Original Brier | p=0.50 ablation Brier | Original minus control |
|---|---:|---:|---:|---:|---:|---:|
| 1 session | 17 | 17 | 0 | 0.277647 | 0.250000 | +0.027647 |
| 5 sessions | 17 | 17 | 0 | 0.265882 | 0.250000 | +0.015882 |
| 20 sessions | 17 | 0 | 17 | unavailable | unavailable | unavailable |

These are 11 source-URL clusters and one decision-date cluster. Horizons overlap and must remain separate. The longer horizon's recorded due date is October 28; calendar due dates alone do not establish a complete session-price window. The original report preserves theoretical policy returns and entry costs, but its survivor-selected unadjusted panel lacks dividends, complete fills and fee attribution. It must not be relabelled broker performance or fresh forward evidence.

The October 10 isolated planner comparison uses five source documents, five tickers, 97 selected revision events, and 15 forecast cells per variant. Actual full, without-news and without-analyst planner receipts now all match their decision-story replays after repairing the replay's 10% name cap. Removing analyst inputs changes forecasts and the intended book. Removing news changes neither: news is not read by this forecast/planner path. Every variant was nonacting with zero sends, and original forecasts and books stayed unchanged. Exact repair evidence: `beta-through-monday/ablation-reviewer-packet.json` and `ablation-after/trace.json` (SHA256 `0b70a8569473cc02810befbc7db461b9399445150aeff6b61cd6de4e94c546e5`). The original mismatch receipt remains preserved.

The existing world-digest grader and news-tilt consumer were also exercised on frozen original outcomes that predate the plan cutoff. Learning was actually read by the next consumer: its evidence changes from zero dates without outcomes to five direction dates and six size dates with outcomes. Trust remains zero and weights remain unchanged under the existing flag and two-key guards. Legacy date-only resolution metadata supports descriptive prior-day inspection, not historical intraday availability certification.

| Digest task / horizon | Original graded rows | Distinct dates | Brier improvement over each row's control | Trust |
|---|---:|---:|---:|---:|
| Direction / 1 session | 7 | 5 | -0.05964 | 0 |
| Direction / 5 sessions | 126 | 1 | -0.00597 | 0 |
| Magnitude / 1 session | 24 | 6 | -0.01349 | 0 |
| Magnitude / 5 sessions | 120 | 1 | -0.00976 | 0 |

Exact evidence: `beta-through-monday/news-pipeline-repair1/trace.json`, SHA256 `251b9e3c532d09b448d02e291e8e25b278d3100dbf86a8101ce4e33b2f8f4c7b`, accepted with limits in `news-repair1-independent-packet.json`. Source/cache binding is not semantic interpretation certification; 55 current digest forecast IDs are still awaiting outcomes. A failed CACC settlement-date interpretation is rejected, not corrected into invented evidence.

Historical checkpoint, before the later canonical operation: the separate catch-up private clone reproduced 22 additional canonical grades and added zero on rerun, with immutable forecasts preserved. Its runtime executor had failed further independent boundary checks and was undergoing its final allowed repair cycle. At that checkpoint, **no runtime catch-up write was accepted yet**. Missing DBRG/WBD price evidence remained unknown. These rows were not pooled with other forecast populations or incompatible horizons. The dated operational delta below supersedes that execution status and preserves the earlier failed receipts.

The earlier next steps were frozen-source release checks, the catch-up writer's final review, and isolated news-consumer qualification. For current owners and remaining work, use the [persistent dependency queue](BETA_DEPENDENCY_QUEUE_2026-10-10.json). Trust, activation and ownership guards remain binding.


Dated operational delta: [22 original campaign forecasts graded and consumed by a subsequent isolated native forecast](BETA_LEARNING_CATCHUP_2026-10-10.md). This separate writer/horizon report preserves the original51-cell report and its probability/input basis; the cohorts are not pooled.
