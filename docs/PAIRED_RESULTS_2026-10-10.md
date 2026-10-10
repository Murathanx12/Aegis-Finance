# Original forecasts and paired frozen-rule results — 2026-10-10

Licence: `PRODUCT_EXPERIMENT`. These are descriptive original-record measurements
and `RETROSPECTIVE_PIT_REPLAY`, with no promotion or new forward record.
The source commit is `97f1c62906fc9fd702714c0dd1f31d070a738ca7` plus the isolated
runner `scripts/budgeted_paired_results.py`. Runtime inputs remain read-only.

## Original September source forecasts

The existing `original_evidence_audit.forecast_census` reproduces all **51/51**
frozen September 26 forecasts from 18 original stored claims. Original IDs,
probabilities, source hashes and made times match. The probabilities mean
**P(beats SPY)**: 36 are 0.60 and 15 are 0.40. They are not probabilities of an
absolute gain, and the original forecasts charge no costs.

An isolated in-memory regrade clears resolution fields on copies before calling
the original resolver: **34 recomputed outcomes match 34 recorded outcomes**.
Original runtime rows stay untouched. The initial passthrough check was rejected
by independent review and its private receipt is preserved as superseded.

| Horizon | Frozen rows | Scored | Beats SPY | Does not beat SPY | Brier | p=0.50 comparison |
|---|---:|---:|---:|---:|---:|---:|
| 1 session | 17 | 17 | 8 | 9 | 0.27765 | 0.25000 |
| 5 sessions | 17 | 17 | 7 | 10 | 0.26588 | 0.25000 |
| 20 sessions | 17 | 0 | — | — | unavailable | unavailable |
| Resolved total | 51 | 34 | 15 | 19 | 0.27176 | 0.25000 |

The 17 unresolved rows retain their original October 28 resolution dates.
There are zero void rows in this selected cohort; void and unresolved coverage
remain explicit. Calibration on resolved rows: the ten p=0.40 rows realised
0.50; the twenty-four p=0.60 rows realised 0.41667. The source forecasts' mean
Brier loss is **0.02176 worse** than the retrospective p=0.50 ablation on the
same rows. This does not establish that all news is useless.

The 34 rows share 11 source-URL clusters and **one decision-date cluster**.
Different names, repeat claims and overlapping horizons are not independent
trials. No standard error, significance test or skill claim is made.

## Original-policy reproduction and the paired challenger

Original-policy reproduction uses the frozen September 25 revision-flow book
`cb8d492bb8bf9ade` and its exact random twin `e74c9063d451e316`. The existing
`llm_portfolio.grade` enters at the September 28 open. Through October 9 it
reproduces revision flow **+10.59945% net**, SPY **+1.33012%**, excess
**+9.26933 percentage points**, over ten sessions. The original twin is
**−0.68158% net**. These results are separate from actual broker execution.

The paired replay uses the **first recorded shadow decision after the existing
SHADOW_NEWS_v0 contract freeze**, without choosing by outcome. That decision is
September 29 at 03:03:06 UTC, before the US open, using the September 28 price
vintage. Frozen revision-flow positions are the baseline; the challenger calls
the existing `world_digest.shadow_decision` with the recorded signal snapshot
and recorded historical direction/size trusts of **0/0**. The recipe is written
before replay outcome prices are read. There is no new model inference or
parameter tuning.

Both arms enter at the September 29 open and mark through October 9: nine US
sessions. `llm_portfolio.grade` charges its empirical liquidity-band **entry
half round-trip** cost once. It compares net portfolio returns with gross SPY,
preserving the original convention. Rebalancing turnover is zero; one-way
initial deployment is 100% of the sleeve. No terminal liquidation cost is added.

| Same-window arm | Net return | SPY | Net excess | Net maximum drawdown | Entry cost |
|---|---:|---:|---:|---:|---:|
| Frozen revision baseline | +8.19497% | +1.53098% | +6.66399 pp | −0.88176% | 4.3 bps |
| News + analyst challenger | +8.19497% | +1.53098% | +6.66399 pp | −0.88176% | 4.3 bps |
| Without news | +8.19497% | +1.53098% | +6.66399 pp | −0.88176% | 4.3 bps |
| Frozen random-twin alternative | −0.61202% | +1.53098% | −2.14300 pp | −1.86875% | 8.7 bps |

News causes **zero economic weight or return change** at the recorded trusts.
The random twin trails the revision baseline by **8.80699 pp**. This alternative
is an original frozen control portfolio, not a reconstructed analyst-free
ranking or a causal estimate of analyst value. The decision trace reports the
separate actual consumer ablation.

Top baseline contributions: GTLB **+0.98554 pp**, ZS **+0.89918 pp**, AFRM
**+0.85296 pp**. All names and losses remain in the private contribution table;
none is dropped to improve the result. All paired sleeves have full priced
weight, with no unpriceable or deferred-entry names in this window.

## Execution coverage and limitations

The existing latest fleet common-window check **REFUSES** with
`fleet grade session chain has a gap`; this refusal is retained. The frozen
portfolio replay therefore does not certify broker performance. The partial
execution census includes 381 hack2 decision rows: 40 DRY, 98 REFUSED, 117 LIVE,
126 without a mode. Partial run snapshots contain 26 unique orders with nonzero
filled quantity: 25 filled, one partially filled. These snapshots are not a full
fill/fee ledger or a census of all rejected orders.

The panel is survivor-selected and its bars are unadjusted. Dividends, exact
fills and complete fees are unavailable. The original source cohorts use their
actual recorded information clocks, not article publication as detection time.
The news replay uses its recorded signal snapshot rather than a fresh
revalidation of every historical article. One short window and one source
decision-date cluster cannot establish reliability or alpha.

## Reproduction and result artifacts

Run from the isolated checkout with the project Python environment:

```powershell
$env:AEGIS_PERSONAL_MODE='0'
$env:AEGIS_IGNORE_DOTENV='1'
python -m scripts.budgeted_paired_results --data-root <runtime-ledger> --out-dir <fresh-private-directory> --asof 2026-10-09
```

The private directory contains `recipe.json` (frozen plans, exact historical
shadow input and policy), and `paired_results.json` (source hashes and captured
prefix lengths, coverage, original outcomes, scoring, isolated regrade audit,
all daily paths, contributions and refusals). Local machine paths and private
execution receipts stay outside public Git. See the session handoff for the
exact local artifact and review pin.
