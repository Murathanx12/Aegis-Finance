# GRAND-ARENA-1 · Chunk 3 — LLM-SWARM-1

**Run 2026-08-12T09:47:33+00:00 · observation timestamp 2026-08-11 · 59.3 min wall · 24 workers.**

> **ARCHITECTURE_RESULT_ONLY.** The foundation model may know history that overlaps any backtest, so nothing in this artifact certifies alpha. Every record here is about a future that has not happened; forward resolution is the only evidence, and the earliest of it is 2026-08-16.

## The headline is the zero-yield rate, not the call count

| number | value |
|---|---|
| calls attempted | 8014 |
| **produced a gradeable record** | **7897** |
| abstained (counted, not discarded) | 27 |
| parsed but minted nothing | 90 |
| failed on the wire | 0 |
| retries | 0 |
| **zero-yield rate** | **1.5%** |
| cost (ESTIMATE, list prices 2026-08-12) | $12.03523 |
| cost per gradeable output | $0.00152 |
| tokens in / out | 2,331,838 / 9,806,084 |
| predictions minted | 22607 (19961 distinct) |
| earliest pending resolution | 2026-08-16 |

Cost is reconstructed from the dated list prices in `config.LLM_PRICE_PER_MTOK`, not from a billed amount.
It is a **LOWER BOUND**: 2 ledger line(s) are unreadable and their spend is simply gone (see Defects).

## The universe, and how it was chosen

**459 securities**, all of which had at least 252 trading days of history at the observation timestamp — a name we cannot price cannot be forecast about, and its records could never resolve.

| source (all pre-dating this campaign) | names |
|---|---|
| `config.stock_universe.sector_stocks` | 181 |
| `funnel_night10.candidates` | 40 |
| `murat_book.positions+watchlist` | 43 |
| `paper_portfolios.yaml` | 0 |
| `theme_baskets.yaml` | 51 |
| `conviction_prices.csv columns` | 67 |
| `funnel_cache.universe (seeded random sample of 5,324)` | 220 |
| `dropped_for_insufficient_history` | 30 |

**Sources that contributed ZERO names: `paper_portfolios.yaml`.** A zero is either a genuinely empty source or an extractor that no longer matches the file's shape — indistinguishable from outside, so it is flagged rather than summed silently.

Selection used only information available at the observation timestamp: the snapshot panel is truncated at `as_of` before any field is computed, so no specialist saw a number from after the date it was forecasting from.

## What was refused, and why

A rejection is not an error log. It is the measurement of how much of the spend bought ungradeable output.

| reason | n |
|---|---|
| `recommendation_language` | 526 |
| `horizon_not_frozen` | 348 |
| `unparseable_json` | 33 |
| `missing_required_field` | 31 |
| `forecasts_past_cap` | 18 |
| `coin_flip_filler` | 6 |
| `no_counter_thesis` | 2 |
| `unknown_observable` | 2 |
| `evidence_without_first_public_timestamp` | 2 |
| `no_evidence` | 1 |
| `wrong_security` | 1 |

## The p=0.50 monoculture is gone

The first WHY-MOVED batch was 23 of 25 one-day `return_sign` claims at exactly 0.50. This run:

| observable | n |
|---|---|
| `abs_move_exceeds` | 7681 |
| `return_sign` | 7047 |
| `beats_benchmark` | 6769 |
| `drawdown_exceeds` | 1110 |

| horizon (trading days) | n |
|---|---|
| 1 | 89 |
| 2 | 92 |
| 5 | 5236 |
| 20 | 9336 |
| 60 | 5985 |
| 120 | 1152 |
| 252 | 717 |

| stated probability (rounded to 0.1) | n |
|---|---|
| 0.0 | 4 |
| 0.1 | 45 |
| 0.2 | 118 |
| 0.3 | 430 |
| 0.4 | 4066 |
| 0.6 | 15131 |
| 0.7 | 2702 |
| 0.8 | 111 |

Exact 0.50 is refused at parse time (`SWARM_COIN_FLIP_EPS`), and a batch that collapses onto one (observable, horizon) pair is refused whole (`monoculture_batch`). The abstain channel is where 'no view' is supposed to go.

## CANON §20 — asking one model 8,000 times is not n=8,000

**22607 forecasts → 6772 effective distinct ideas (ratio 0.2996).** Same rule `optimus_specialists.effective_distinct_ideas` uses, so the two surfaces are comparable: one idea is one (security, observable, probability-to-0.05) bucket.

Distinct tickers 459 · observables 4 · horizons 7.

**This ratio is the honest denominator for anything said about the swarm.** Volume bought exploration diversity. Only market outcomes supply evidence.

### Do fourteen roles say fourteen different things?

```json
{
 "n_contested_cells": 3901,
 "mean_specialists_per_cell": 4.68,
 "mean_probability_stdev": 0.0592,
 "mean_probability_range": 0.1465,
 "share_of_cells_where_every_role_lands_in_one_0_05_bucket": 0.1182,
 "reading": "a small spread means the fourteen roles are one forecaster with fourteen system prompts; separation prevented contagion, it did not create independence"
}
```

Separation prevents contagion between the roles. It cannot manufacture independence the underlying model does not have, and this is the number that says which of those happened.

### The same role, asked the same question twice

```json
{
 "n_repeated_cells": 2544,
 "n_matched_forecast_slots": 2710,
 "n_slots_only_one_pass_asked": 9137,
 "mean_abs_probability_difference": 0.0658,
 "reading": "a small probability difference on matched slots means the second pass bought little new information; a large share of unmatched slots means the passes explored differently, which is the only thing extra passes can honestly buy"
}
```

## Per specialist

| specialist | calls | ok | abstain | zero-yield | fail | records | forecasts | eff. ideas | ratio | mean conf |
|---|---|---|---|---|---|---|---|---|---|---|
| `accounting_forensics` | 683 | 672 | 2 | 9 | 0 | 1909 | 1909 | 1702 | 0.8916 | 0.531 |
| `analyst_revisions` | 681 | 671 | 1 | 9 | 0 | 1927 | 1927 | 1727 | 0.8962 | 0.552 |
| `behavioral_narrative` | 675 | 658 | 2 | 15 | 0 | 1910 | 1910 | 1724 | 0.9026 | 0.559 |
| `biotech_pharma` | 169 | 164 | 0 | 5 | 0 | 481 | 481 | 431 | 0.896 | 0.541 |
| `company_fundamental` | 688 | 676 | 3 | 9 | 0 | 1944 | 1944 | 1724 | 0.8868 | 0.555 |
| `energy_materials` | 120 | 118 | 1 | 1 | 0 | 326 | 326 | 280 | 0.8589 | 0.588 |
| `event_news` | 687 | 678 | 2 | 7 | 0 | 1931 | 1931 | 1723 | 0.8923 | 0.546 |
| `execution_momentum` | 673 | 668 | 2 | 3 | 0 | 1935 | 1935 | 1712 | 0.8848 | 0.562 |
| `geopolitical` | 696 | 690 | 1 | 5 | 0 | 1970 | 1970 | 1767 | 0.897 | 0.58 |
| `macro_rates` | 678 | 672 | 2 | 4 | 0 | 1902 | 1902 | 1697 | 0.8922 | 0.585 |
| `options_volatility` | 674 | 667 | 1 | 6 | 0 | 1909 | 1909 | 1693 | 0.8869 | 0.553 |
| `ownership_flow` | 679 | 674 | 0 | 5 | 0 | 1928 | 1928 | 1737 | 0.9009 | 0.541 |
| `semis_technology` | 243 | 238 | 0 | 5 | 0 | 658 | 658 | 590 | 0.8967 | 0.588 |
| `skeptic` | 668 | 651 | 10 | 7 | 0 | 1877 | 1877 | 1681 | 0.8956 | 0.491 |

## The ledger refused what the swarm duplicated

22607 forecasts were accepted; **19961 distinct records reached the ledger**. The other 2646 were byte-identical claims — same security, specialist, observable, horizon, snapshot and prompt — produced when the second pass reproduced the first exactly. `belief_state.append` refused them by `prediction_id`, which is the correct outcome and worth stating plainly: **a repeated forecast is not a second piece of evidence**, and scoring it twice would silently double that forecaster's weight in its own calibration. The duplicate rate is itself a §20 measurement.

## Calibration prior: this batch looks overconfident

The probability histogram is not centred. Stated credences pile up between 0.55 and 0.70, with very little mass below 0.30 — a forecaster that is confident about almost every security it is shown. That is the failure mode `docs/TRIALS/TRIAL-SWARM-CAL-specialist-calibration.md` **pre-registered as the expected one**, before any of these records could resolve. It is stated here as a description of the inputs, NOT as a result: whether the confidence is earned is exactly what the forward Brier will decide, and nothing before the minimum window may be read as an answer.

The `skeptic` carries the lowest mean confidence of the fourteen roles and abstained more than any other, which is what its prompt asks for. That is instruction-following, not evidence of judgment — the ledger will say which.

## Defects this run exposed (all fixed or disclosed)

- **Two telemetry rows were TORN by concurrent appends.** 24 threads writing `llm_calls.jsonl` produced two unparseable lines (`"1.0.0"}` and `"}`). A single short `write()` is atomic on POSIX by convention and not guaranteed on Windows. `read_calls` counted them and downgraded every total to a LOWER BOUND, which is the only reason it was visible. `append` is now serialised by a process-level lock in both `llm_telemetry` and `belief_state`, with a regression test that runs 16 threads; the lock does NOT cover two processes sharing a volume, and says so.
- **The budget governor cost 0.31s per gate at scale.** `research_budget` called `llm_telemetry.summary()`, which joins every claimed prediction id against a 25MB ledger — irrelevant to the decision. A governor that is expensive to consult is one somebody eventually consults less often, so `spend()` now serves the gate with the same four inputs and none of the join.
- **A universe source silently returned zero names.** The `paper_portfolios.yaml` extractor only understood `{"ticker": ...}` records and that file holds bare strings, so an 81-name source read as empty and looked exactly like an empty file. Fixed for future runs; the frozen universe used here predates the fix, and the provenance table flags every zero-yielding source for precisely this reason.
- **The ledger resolver fetched every due ticker in ONE request.** Correct at a dozen names; with hundreds in the ledger a single timeout would mark every due record unpriceable and page on a problem that is not in the ledger. Now chunked, so a bad chunk strands only its own names.
- **`ResearchBudgetExhausted` was being absorbed into the per-cell failure count** in an early draft of `run_cell`, which would have made an exhausted budget look like vendor flakiness while the pool kept submitting work. It is now re-raised.

## What this does and does not license

- It licenses nothing about skill. Every record is unresolved.
- The first grade falls on `2026-08-16`, and CANON §19 applies to every slice of it: each prints its own n and its own MDE.
- A 1-day Brier is mostly noise. The short horizons exist to accrue n fast, not to be read early.
- Abstentions are honestly counted as producing no gradeable output, because they do not. That is what keeps the zero-yield brake able to see the campaign it watches.
