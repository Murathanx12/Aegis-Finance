# Beta V1 Portfolio — 11 October 2026 review draft

**New, inactive conditional draft.** Decision timestamp: `2026-10-11T11:53:25.981049Z` (19:53:25 Singapore). This book has no fills or forward P&L. Existing RF, net-raises and Hack2 results are reported [separately](BETA_SPRINT_MEASURED_RESULTS_2026-10-11.md); they are not assigned to this portfolio.

The primary H21 expected-return fit is unfinished. This draft therefore shows a separately labelled **ordinal priority view over 21 sessions**, not calibrated expected returns or a completed adaptive allocation. It is a useful current candidate artifact for owner review, not approval to take exposure. SPY has zero strategic weight and remains a separate comparator.

## How these names were selected

Start from the genuine 103-instrument examined subset, qualify 100 under the original baseline eligibility rule, then apply the reviewed common-pool/native instrument constraints. Ninety-five names qualify for this ordinal comparison. The current features use a 90-calendar-day event window, excluding the as-of calendar day and requiring first-seen availability by the original feature cutoff. This does not reconstruct six months of historical analyst availability.

The revision-flow input is net raises multiplied by firm count, with positive support from at least three firms. The other input is net raises. Each is ranked within the same qualified pool, and priority is `0.5 × RF percentile + 0.5 × NR percentile`, with deterministic tie handling. This new common-pool experiment does not add RF's firm gate to the old standalone net-raises policy. The ten highest positive candidates receive fixed 3% review slots; a missing slot is left unallocated, never redistributed to force exposure.

Effective component weights are **RF 50% / net raises 50%, SHRUNK_PRIOR**. Both learned masses are zero; there are zero independent training blocks/labels for this new ordinal objective. These are declared priors, not measured optimal weights. Current analyst information changes the candidate output: without it the comparison is unavailable, not a fabricated zero prediction. Descriptive context produces identical numerical results because no calibrated numerical mapping is admitted. Neither result establishes future profitability.

## Conditional allocation and source prices

Every row has a 21-session review horizon and a 3% hypothetical slot. Prices are cached native instrument reference observations dated October 9; some timestamps are after the regular close. They are not live executable quotes, simulated fills, total-return prices or verified corporate-action-adjusted prices. `USD` is the normalized request/output currency; native listing-currency semantics remain unknown. IEX exchange volume is a lower bound, not consolidated market volume.

| Company / ticker | Venue | Weight | Reference price / UTC on Oct 9 | Net raises / firms | RF score | Ordinal priority |
|---|---|---:|---|---:|---:|---:|
| Okta / OKTA | NASDAQ | 3% | 232.16 / 19:59 | 73 / 35 | 2,555 | 1.000000 |
| CrowdStrike / CRWD | NASDAQ | 3% | 274.89 / 20:08 | 50 / 37 | 1,850 | 0.989474 |
| Zscaler / ZS | NASDAQ | 3% | 233.95 / 19:59 | 47 / 31 | 1,457 | 0.978947 |
| Palo Alto Networks / PANW | NASDAQ | 3% | 418.92 / 19:59 | 34 / 30 | 1,020 | 0.968421 |
| Amgen / AMGN | NASDAQ | 3% | 414.79 / 19:59 | 30 / 22 | 660 | 0.952632 |
| Airbnb / ABNB | NASDAQ | 3% | 165.85 / 19:59 | 26 / 30 | 780 | 0.942105 |
| Marvell Technology / MRVL | NASDAQ | 3% | 274.99 / 20:19 | 28 / 23 | 644 | 0.942105 |
| Cloudflare / NET | NYSE | 3% | 360.77 / 19:59 | 27 / 19 | 513 | 0.926316 |
| Advanced Micro Devices / AMD | NASDAQ | 3% | 607.29 / 20:38 | 22 / 28 | 616 | 0.915789 |
| Datadog / DDOG | NASDAQ | 3% | 293.14 / 19:59 | 21 / 22 | 462 | 0.894737 |

Total conditional gross is **30%**; **70% is unallocated**, not an engine decision to hold cash. The primary expected-return consumer separately reports `RETURN_INPUTS_UNAVAILABLE`, with cash null and no holdings. No shares, dollar notionals, turnover fills or trades are inferred from these review weights.

For **each of these ten names**, analyst low/median/high targets and their horizons are unavailable in the admitted feature contract, verified future catalyst dates are unavailable, expected H21 return is unavailable, and an active exit contract is unavailable. Those fields are not set to zero or borrowed from another company/book. Do not use an old target range with an unknown horizon as a 21-session forecast. Company names are shortened here from the exact bound broker metadata labels; issuer/venue/request-currency qualification remains scoped to the native receipts.

The selection reason for each row is its current combined ordinal standing shown above. AMGN ranks above ABNB because its stronger net-raises percentile offsets ABNB's stronger RF percentile; ABNB and MRVL tie on combined priority and retain the reviewed deterministic order. This is a signal explanation, not a newly researched company thesis. Fundamental reasoning and independent analyst lead/lag research remain [deferred](DEFERRED_INDEPENDENT_INVESTMENT_REASONING_2026-10-11.md).

## Risks, invalidation and exits

The main risks are correlated source information, shared business/factor exposure, revisions already reflected in prices, unknown adjustment/corporate-action basis, reference-price versus actual execution differences, and unverified future catalysts. Different tickers do not establish diversification. Portfolio covariance/risk calibration and a fitted return/cost objective are unavailable; 30% gross is not a certified risk budget.

Reject the conditional preview if an input hash, identity, qualification or availability clock changes or fails; rerank from freshly qualified inputs rather than edit the frozen table. Loss of positive revision support or instrument eligibility is opposing evidence for a later reviewed decision, not an automatically armed sell instruction. A 21-session horizon is not an actual exit date without a defined prospective inception. Do not invent stops or inherit another book's exit terms. Owner review must define the entry/exit/cost mandate before activation.

Worst-case arithmetic only: one 3% slot going to zero loses 3% of reference equity; all ten going to zero lose 30%, before costs. On an illustrative $100,000 reference book that is $3,000 per slot and $30,000 total. No such notional was allocated and no stop bounds that loss. SPY is a separate comparison with no strategic allocation.

## Differences from earlier books

This is a new construction, not a renamed ATLAS. None of the ten selected names appears in the 23-stock ATLAS v3 draft. The books have different mandates/horizons and no transition orders are implied.

| Comparison group | Earlier ATLAS v3 proposal | New Beta conditional draft | Explanation |
|---|---|---|---|
| OKTA, CRWD, ZS, PANW, AMGN, ABNB, MRVL, NET, AMD, DDOG | 0% each | 3% each | Selected anew by the current common-pool ordinal path |
| VRT, GEV, MU, TSM, HOOD, NVT, AVGO, CLS, BE, MP, LEU, CCJ, NOVT, IONQ, VRTX, WST, COGT, VKTX, AGIO, RGEN, BBIO, PRAX, DKNG | 23 stocks, 96% total | 0% in this separate draft | Not among these ten selections; this is not a negative fundamental verdict or liquidation |
| Reserve | 4% proposed cash | 70% unallocated | Different states; unavailable return inputs are not a cash recommendation |
| Horizon | 126-session ATLAS review | 21-session ordinal review | Comparisons are descriptive, not matched return tests |

[ATLAS v3 and its v1/v2 comparison](ATLAS_LLM_PORTFOLIO_V3_2026-10-10_REVIEW.md) remain unchanged. Original standalone RF/net-raises top-20 policies and genuine paper histories remain separate. The new H21 fit failure does not disable them. A current winning name is not automatically copied into a contest book.

## Artifact and activation gates

The bounded real preview completed in 1.062 seconds, with a 152,887,296-byte owned aggregate peak under the existing 256 MiB/30-second limits. Its ten conditional rows derive from the native input contract; all 663 original witness clock records were retained. Source review and actual admission are separate receipts; no protected outcomes were opened or old forecasts rewritten.

Independent actual admission passed in `rank-fallback-draft/r6/actual-review.json`, SHA `a0494c3811091ecb5282aa3d2c4e6d31da8e51f68765257692bb81f4c7bb6531`, within conditional review-only scope. It verifies byte bindings, new decision chronology, direct worker identity, retained-handle resource proof and reap; it does not approve return calibration or trading.

Private source artifact: `rank-fallback-draft/r6/runs/root-actual-r6-20261011/ordinal-review-draft.json`, byte SHA `ba061bdad0a58260450b7e8211ab967fb3df65d2a2e80fa4e9c4a6470c3cecca`; with-analyst logical hash `c235d78df008ab29344801f7d70be194aaf372bcc1894fb5408ae3bc76465d23`. Root input manifest SHA `13fec16195cd2e266ffb88188a283d76eb1e8eebc1c53c58a3ee76a8b0ef17e9`. Independent source review SHA `9b75df9b9ff1a173cfcb709593cd1b3d0784449e8f1fde0ecba456cb2ed5c85b`. The selected-only reporting projection preserves those bindings and does not rerank or fit.

Authentic Bloomberg WLS eligibility is **unverified for every name**. [The separate contest-horizon view](BETA_V1_CONTEST_VIEW_2026-10-11.md) and [Monday Terminal packet](BLOOMBERG_MONDAY_TERMINAL_PACKET_2026-10-12.md) retain their gates. This review draft is not activated, submitted or ordered.
