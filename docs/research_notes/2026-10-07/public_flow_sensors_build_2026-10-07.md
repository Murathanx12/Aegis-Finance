# Public-flow sensors: build receipts (chunk C16, 2026-10-07; revised after review)

Builder pass (Opus) on the Sonnet spec `public_flow_sensors_2026-10-07.md`, revised the same night after the
adversarial review `docs/reviews/REVIEW_2026-10-07_C16_PUBLIC_FLOW_SENSORS.md` (64/100, "merge with fixes";
F1-F12 applied below). The licence for the sensors themselves is PRODUCT_EXPERIMENT. Nothing here is a trade
signal: every row is a SENSOR reading with provenance and latency, and no scoring path reads it. Identity
attributes of any person or group are not a field anywhere (roadmap 2026-10-06 §2 item 10). The variables
are dollars: contract obligations and lobbying spend.

**RESULTS:**

| source | rows |
|---|---|
| USAspending transactions | **2,061** in the table: 2,059 from the action-date backfill (re-keyed after F2/F4) plus 2 from the reconciled last-modified re-pull |
| USAspending agency x month | **175** |
| Senate LDA | **0**, **REFUSED** (`ACCESS_DENIED`, an edge block) |
| crypto | **1** snapshot, OK |

**Publication latency: NOT YET MEASURED.** The backfill's "41 days" was the age of a 90-day window (F3) and
is withdrawn. The re-pull's 2 rows predate the target's coverage, so they are not a reading either.

**Fiscal cell: UNPOWERED_AT_DECLARATION at the fiscal-year unit.** The dose re-declaration is unpowered too.

**RESULT IMPROVEMENT: NONE.**

**The `AegisPublicFlow` task is NOT to be registered** until the coordinator signs off on these fixes. The
code only prints the registration; nothing was registered.

## 1. What was built

| piece | file | caller |
|---|---|---|
| shared plumbing: dated crosswalk loader + matcher, paced HTTP client with refusal classes, append-only tables with REVISIONS, PIT check, receipts, the DEGRADED rule (with federal holidays exempted) | `backend/services/public_flow_common.py` | the three sensors |
| USAspending: transactions by LAST-MODIFIED date (daily) or action date (backfill), reconciled per recipient against the count endpoint; agency x month snapshots with per-row `partial` / `settled` and an as-of reader | `backend/services/usaspending_awards.py` | `task_keeper public_flow` |
| Senate LDA lobbying filings, with amendment-aware, self-filer-aware totals | `backend/services/lobbying_lda.py` | `task_keeper public_flow` (weekly, by its own receipt stamp) |
| crypto risk-appetite sensor (DeFiLlama stablecoin supply, Binance + OKX funding, CoinGecko BTC/ETH spot) | `backend/services/crypto_market.py` (appended) | `task_keeper public_flow` (daily) |
| Kalshi storage mode, default **`none`** | `backend/services/prediction_markets.py`, `config.PREDMARKET_KALSHI_STORAGE` | the existing `pi_prediction_markets` job |
| hand-curated, DATED crosswalk: 91 entries / 68 tickers, `confidence` and `valid_from` / `valid_to` per entry, UEIs only from the live pull | `backend/data/crosswalks/usaspending_recipient_ticker.yaml` | both pulls, the fiscal cells |
| theory cells `fiscal_year_end_spending` and `fiscal_year_end_dose`, DECLARED ONLY; both refused at the FY unit | `scripts/hyp_theory_cells.py` | hyp_lab ledger row `H-5c26e79507` |
| the owner `AegisPublicFlow` + health reader + cadence | `scripts/task_keeper.py`, `backend/services/task_receipts.py`, `config.HEALTH_TASK_CADENCE_H` | NOT registered (see above) |

Tables live under `backend/data/optimus/public_flow/tables/` and are **gitignored** (F9): the crypto rows
carry CoinGecko, Binance and OKX market data whose terms restrict redistribution. Receipts (counts,
statuses, citations) stay tracked.

## 2. Review findings and what changed

| finding | fix |
|---|---|
| F1: a 14-day action-date window can never see DoD (~90-day publication delay) | The daily pull filters on **`last_modified_date`** over `USASPENDING_MODIFIED_LOOKBACK_DAYS` (3). Rows are stored when their action date is inside a rolling `USASPENDING_ACTION_WINDOW_DAYS` (120); older modifications are counted only. `first_seen_utc` semantics are unchanged. The API accepts the date type: verified live, the count for GD over 90 days was 637 by action date and 7,587 by last-modified date. |
| F2: 637 read vs 635 stored for GD, receipt OK | **Measured cause: unstable paging on a tied sort.** Re-reading GD sorted by "Mod" served 635 distinct of 637, with 2 rows twice. Sorted by "Award ID" it served 637 distinct. Pages now sort on `Award ID`. Every recipient is reconciled against `spending_by_transaction_count`. On a mismatch it is re-read once in the opposite order and unioned; if it still does not reconcile, the recipient is **REFUSED and none of its rows are written**. |
| F2/F4: the key included the amount | Identity = `generated_internal_id | Mod`. The API exposes no transaction id, and `internal_id` is the award's. A later read with different content is a **revision** (`<identity>#v<k>`, `supersedes`). Totals read `latest_versions` only. |
| F3: "median latency 41 d" was window age | Withdrawn. A recipient's first contact, and every action-mode pull, labels its rows `latency: NOT_MEASURABLE_BACKFILL`. A row first seen later whose action date precedes the target's existing coverage is `NOT_MEASURABLE_BEFORE_COVERAGE`. The latency summary uses only the remaining rows. |
| F5: receipt dollars included duplicates ($149,700) | Receipt dollars are computed from the table, as the latest version per identity read in that pull (`obligation_basis` says so). LDA likewise. |
| F6: agency-month PIT was half done | Each row carries `period_start`, `partial` and `settled` (fetch date >= month end + `USASPENDING_SETTLE_DAYS`: DoD 100, others 45). The PIT check is now "the month had started by the fetch date", not a tautology. `q4_share` **refuses** more than one snapshot. `agency_months_as_of(t)` returns the latest snapshot fetched on or before `t`, and a test pins that a later snapshot cannot change an earlier read. |
| F7: undated crosswalk, confidence contradictions, prefix false positives | `valid_from` / `valid_to` per entry. Renames and acquisitions became separate **medium** entries: RTX (Raytheon from 2020-04-03, Collins and Rockwell Collins from 2018-11-26), LHX (L3 from 2019-06-29, Aerojet from 2023-07-28), LMT (Sikorsky from 2015-11-06), LDOS (old SAIC to 2013-09-26), ELV, VVX, J / AMTM (Jacobs Technology moves 2024-09-27), CVS / Aetna, CI / Express Scripts, ORCL / Cerner, GE / GEHC / GEV. Removed: LDA `MERCK` (now `MERCK AND CO`), bare `ANTHEM`, LDA `JACOBS`. HONEYWELL FEDERAL MANUFACTURING and FLUOR MARINE PROPULSION are **low** (M and O). Added **Dynetics -> LDOS** (from 2020-01-31). UEI matches apply only on or after 2022-04-04. |
| F7: the fiscal universe reused tickers | Linked by **permco**: the company that holds the ticker most recently, with all its name rows (ABC, HRS, UTX count) and no other permco (Cortex as COR, MDRNA as MRNA, Protective Life as PL are gone). One permno per company (HEI counted once). Months before the crosswalk window are dropped. |
| F8: the gate passed on name-months | Re-gated at the **fiscal year** (section 5). |
| F9: Kalshi default, gitignore, factual error | Default **`none`**. Tables gitignored. The note's claim that raw Kalshi data sat in a public repository was **wrong**: `prediction_markets/` is gitignored, and no Kalshi snapshot was ever committed. Locally one snapshot day exists (2026-08-21). |
| F10: LDA double counting | `lobbying_totals`: the latest filing per (client, registrant, period) supersedes amendments, and outside-firm income is never added to a self-filer's expenses. |
| F11: LDA class | A 401/403 is now `ACCESS_DENIED` (the earlier receipt said `BOT_CHECK`; that receipt predates the fix). |
| F12: status gaps | A target with expected activity (>= 5 rows from its prior-90-day rate, or a >= 60-day first contact) that returns 0 is `DEGRADED_ZERO_ROWS`. US federal holidays are exempt from the weekday rule. 429 is tested as fatal. |

The table written before the review was **migrated offline**, not re-pulled. 2,059 rows were re-keyed to the
identity with 0 collisions and re-matched with the dated crosswalk: 1,947 high, 5 medium (Dynetics), 107 not
mapped. Every migrated row is labelled `NOT_MEASURABLE_BACKFILL`. The 175 agency rows received `partial` and
`settled` offline. Pre-migration copies are kept in the session scratchpad, not in the repo.

## 3. Receipts

### The reconciled re-pull: `receipts/usaspending_20261006T230713Z.json` (status DEGRADED)

Mode `modified`: last-modified 2026-10-03..10-06, action window from 2026-06-08, tickers LMT, RTX, GD, BA,
NOC, LDOS, HUM, CNC, BAH and PLTR. Each search is one crosswalk entry valid in the window. **32 requests, all
OK; every recipient reconciled.**

| search | status | read | distinct | API count | repeats | pages | stored |
|---|---|---|---|---|---|---|---|
| LOCKHEED MARTIN | OK | 32 | 32 | 32 | 0 | 1 | 1 |
| SIKORSKY AIRCRAFT | OK | 13 | 13 | 13 | 0 | 1 | 1 (same row, cross-search overlap) |
| RTX CORP | OK | 15 | 15 | 15 | 0 | 1 | 0 |
| RAYTHEON | OK | 0 | 0 | 0 | 0 | 1 | 0 |
| PRATT AND WHITNEY | OK | 0 | 0 | 0 | 0 | 1 | 0 |
| COLLINS AEROSPACE | OK | 0 | 0 | 0 | 0 | 1 | 0 |
| GENERAL DYNAMICS | OK | 3 | 3 | 3 | 0 | 1 | 0 |
| BOEING | OK | 71 | 71 | 71 | 0 | 1 | 1 |
| NORTHROP GRUMMAN | OK | 5 | 5 | 5 | 0 | 1 | 0 |
| LEIDOS | OK | 1 | 1 | 1 | 0 | 1 | 0 |
| DYNETICS | OK | 0 | 0 | 0 | 0 | 1 | 0 |
| HUMANA | OK | 0 | 0 | 0 | 0 | 1 | 0 |
| CENTENE | OK | 0 | 0 | 0 | 0 | 1 | 0 |
| HEALTH NET FEDERAL SERVICES | OK | 0 | 0 | 0 | 0 | 1 | 0 |
| BOOZ ALLEN HAMILTON | **DEGRADED_ZERO_ROWS** | 0 | 0 | 0 | 0 | 1 | 0 |
| PALANTIR | OK | 0 | 0 | 0 | 0 | 1 | 0 |

* 140 transactions were modified in the window. **137 had action dates older than 120 days** (old records
  touched) and were counted, not stored. One was found by two searches. **2 new identities** were stored,
  with action dates 2026-06-11 and 06-23.
* The receipt's latency line (n = 2, median 111 days) was computed before the coverage rule existed. Both
  rows' action dates precede the targets' coverage start (2026-07-08), so **it is not a latency**. The two
  rows were relabelled `NOT_MEASURABLE_BEFORE_COVERAGE` the same night. This receipt's latency line is
  superseded by this paragraph.
* BAH is DEGRADED by the new floor: its prior rate (~533 rows / 90 days, so ~18 expected in 3 days) against
  0 returned. That is the F12 rule firing, possibly on a quiet weekend window. Re-check on the next weekday
  pull.
* HUMANA again returned 0. That is not flagged in a 3-day first contact (under 60 days), but its 90-day
  backfill was also 0, and that is now DEGRADED by rule (tested).

### Earlier receipts, read with the corrections above

* `usaspending_20261006T214522Z.json`: the first pull, keyed on the award id. 742 rows were dropped and the
  receipt said OK. **Superseded.**
* `usaspending_20261006T215032Z.json`: the 90-day action-date backfill. Its row count stands (2,061 read,
  2,059 stored). Its dollar figure ($6,591,346,587.55) included 2 duplicate reads; the table figure is lower
  by $149,700.01 (F5). **Its latency section is withdrawn** (F3).
* `usaspending_agency_months_20261006T215149Z.json`: 175 rows. It predates `settled` / `partial`; read its
  q4 shares through the migrated table. Q4 share of contract obligations, settled FY2025 vs FY2026 one week
  after year end:

  | agency | FY2025 | FY2026 |
  |---|---|---|
  | DoD | 36.3% | 1.0% (unsettled) |
  | DHS | 56.2% | 30.4% (unsettled) |
  | HHS | 49.4% | 47.2% |
  | NASA | 41.7% | 41.1% |

  All FY2026 shares are unsettled lower bounds.
* `senate_lda_20261006T215232Z.json`: REFUSED. It is labelled `BOT_CHECK` there; it is an edge
  `ACCESS_DENIED` (F11).
* `crypto_risk_sensor_20261006T215233Z.json`: OK.
  - USD stablecoin supply $314.07 B (+0.56% over 7 days).
  - BTC funding 2.7e-5 per 8 h (Binance/OKX average), ETH 3.7e-5.
  - BTC $85,583, ETH $2,696.

## 4. Latency: what can and cannot be said

Not yet measured. The only defensible statement from the backfill is a **lower bound**: no transaction dated
in the 4 days before the pull was published. The DoD lag shows indirectly: 9 DoD rows in 90 days across six
defence primes, and DoD's FY2026 Q4 share at 1.0% one week after year end. The distribution will come from
daily last-modified pulls, over rows whose action date falls inside an already-read window. The first such
rows will exist after the second daily pull on a weekday.

## 5. The fiscal-year-end cells: the gate's verdict

The first declaration (`TC_C16_2026-10-07`, sha `bc92b200ab317920`, ledger `H-5c26e79507`) passed the
name-month gate: split 16.8/83.2, MDE >= 0.83% vs a 1.0% bar. **That pass was on the wrong unit (F8).**
Re-gated at the **fiscal year**, with the per-FY sd taken from the DESIGN fold (FY2009-2016) and 8 validate
FYs:

| cell | statistic per FY | design sd | MDE | bar (2 x 0.5%) | verdict |
|---|---|---|---|---|---|
| `fiscal_year_end_spending` | EW GOVDOM basket: Aug-Sep compounded excess vs FF market minus 2 x mean Oct-Jul monthly excess | 1.49% | **1.47%** | 1.0% | **REFUSED: UNPOWERED_AT_DECLARATION** |
| `fiscal_year_end_dose` (re-declared as the within-year dose test the review asked for) | top minus bottom tercile of federal revenue share (GOVDOM / segment sales, last 10-K year before Aug 1) | 5.03% | **4.98%** | 1.0% | **REFUSED: UNPOWERED_AT_DECLARATION** |

Gate receipts:
- `hyp_lab/theory_fiscal_year_end_spending_GATE_REFUSED_TC_C16R_2026-10-07.json`
- `hyp_lab/theory_fiscal_year_end_dose_GATE_REFUSED_TC_C16R_2026-10-07.json`

Ledger row `H-5c26e79507` is updated with `powered: false` and the summary `UNPOWERED_AT_DECLARATION` (status
stays DECLARED; hyp_lab has no unpowered status). The dose test is less readable than the basket, not more:
cross-sectional terciles of about 15 names are noisier than the basket.

**Precursor, corrected (F8).** Fiscal-Q4 agency obligations are NOT knowable on Aug 1. This is a **calendar
effect conditional on federal exposure**. The agency-month snapshots are a forward diagnostic of the
mechanism, never its precursor, and the declaration says so.

**Disclosure.** While building the FY gate I printed the per-FY statistic for all FYs 2009-2024, validate
included. The history validate fold is therefore **seen**. Both declarations record this, and no history read
of these cells can confirm anything; a positive would need forward fiscal years (FY2027+). Since both cells
are unpowered at 8 FYs anyway, the honest closure is **DEPRIORITIZED: unpowered on the available history**,
not a negative about the mechanism.

## 6. NOT_MAPPED (and not built)

Subsidiaries the API returned under a parent search remain **not mapped**: QTC Medical (Leidos, 30 rows),
Jeppesen ForeFlight (Boeing until its 2025 sale), Thunderyard (BAH JV), Magellan Federal and Foundation Care
(Centene), North Wind Portage and Kahu JV (Leidos), Metro Machine, CSRA, DynPort and Jet Aviation (GD),
Millennium Space, VeroCel, HRL, Liquid Robotics and Bell Boeing JPO (BA / JV), Zeta and Astrotech (LMT),
Remotec and Scaled Composites (NOC).

Only Dynetics was added, at the review's request. Adding the others is a dated crosswalk edit with a
confidence each, and it is owed. Until then, per-ticker dollars are systematically low for LDOS, GD, BA and
BAH.

Not built: the fuzzy EDGAR-name join, CIKs in the crosswalk, and per-name federal share outside the gate.
LDA has no live rows.

## 7. Owner decisions

**D18: Kalshi storage.** Kalshi's Developer Agreement is quoted as barring "collecting, caching,
**aggregating**, or storing" API data except to facilitate one's own trading. That quote is **unverified
first-hand**: the reviewer's fetch got a 429. Its Data Terms bar ML/AI use. Default is now **`none`** (the
receipt only). Existing files were not deleted, and Polymarket is unchanged.

| option | what is stored | cost |
|---|---|---|
| (a) `none` (**default**) | the daily receipt (counts, pages) | no Kalshi leg for TRIAL-PREDMARKET-1/2 going forward. The trial was not accruing Kalshi rows locally anyway (one day on disk). |
| (b) `derived_only` | per FOMC meeting the implied distribution and expected bps change, plus category counts and open interest; no contract rows | the Fed-path regime variable survives, but a persisted aggregate may itself be "aggregating" |
| (c) Polymarket alone | Polymarket raw rows as today | one venue. PREDMARKET-2's divergence measurement ends. |

`raw` restores the pre-10-07 behaviour (`AEGIS_PREDMARKET_KALSHI_STORAGE=raw`).

**D19: FEC (not pulled).** FEC needs an owner key. Its Acceptable Use Policy bars use of the data "for
commercial purposes including, but not limited to, training data for large language models, machine learning
models or artificial intelligence models", which conflicts with the public open-source branch. Options:
(1) not used (default); (2) internal paper research only, after the owner reads the AUP; (3) the weekly bulk
files (no key) under the same AUP. OpenSecrets is not used: its API was discontinued 2026-04-15 and its bulk
terms prohibit redistribution.

**Also the owner's:**
* LDA from this machine is an edge `ACCESS_DENIED`. A US-hosted weekly run (Railway) is the likely fix; an
  API key may not lift a geographic edge rule.
* Registering `AegisPublicFlow` waits for the coordinator's sign-off on these fixes.

## 8. Tests

```
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest
  backend/tests/test_public_flow_sensors.py backend/tests/test_guard_missing_input_contract.py
  backend/tests/test_signal_reachability.py backend/tests/test_prediction_markets.py
  backend/tests/test_hyp_theory_cells.py backend/tests/test_task_receipts_c8.py -q
```

**245 passed.** The earlier wider set, which also includes test_crypto, test_automation_fixes_2026_10_02 and
test_prediction_market_matching, gave **299 passed**. `test_public_flow_sensors.py` has **45 tests**. They now
cover each test the review listed as missing:

* in-recipient repeats reconciled by a reverse read;
* an unreconciled recipient refused, with nothing written;
* a corrected amount stored as a revision, with totals not double-counted;
* receipt dollars equal to table dollars;
* `q4_share` refusing mixed snapshots;
* the as-of reader not moved by a later snapshot;
* 429 fatal;
* holiday exemption;
* zero-row target DEGRADED;
* backfill and before-coverage latency exclusion;
* the dated crosswalk (owners by date, prefix false positives, UEI era);
* LDA amendments and self-filer totals;
* the FY-unit gate.

The full suite was not run, on purpose: another suite was running.
