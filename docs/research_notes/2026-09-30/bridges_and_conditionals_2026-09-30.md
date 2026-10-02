# The last library rules on CRSP, and ten conditional questions: nothing beats the market (2026-09-30)

Licence `PRODUCT_EXPERIMENT`. $0.00. No LLM, no network, no broker call. No book, ledger row or earlier
receipt was changed. **Nothing was registered: no rule and no cell met the registration line.**

Every number below is in a receipt under `backend/data/optimus/crsp_rebuild/`:

- bridges: `pit_{si,f13,eightk,analyst2,fund}_PB_2026-09-29T1420Z.{parquet,json}`, plus the row-by-row timing
  check `pit_analyst2_rowcheck_PB_2026-09-29T1420Z.json`
- library declaration `bridges_DECLARATION_BD_2026-09-29T1530Z.json`, sha **`04ad6dfa6a4fc869`**, written
  before any rule ran
- runs `library_rules_BR_FLAT_2026-09-29T1535Z.jsonl` and `library_rules_BR_CS_2026-09-29T1545Z.jsonl`
  (series in `library_series_<run>/`)
- turnover `bridges_turnover_BT_2026-09-29T1555Z.json`
- board `bridges_board_BR_FLAT_2026-09-29T1535Z__2026-09-29T140355Z.json`
- conditional declaration `conditionals_DECLARATION_CD_2026-09-29T1410Z.json`, sha **`4b50bdb5cc28425e`**,
  written before any cell ran
- conditional results `conditionals_RESULTS_CD_2026-09-29T1410Z.json`, series in
  `conditionals_series_CD_2026-09-29T1410Z/`

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** Both results are negative, with evidence.

| line | tonight |
|---|---|
| Best historical net strategy vs the market | **Unchanged: none.** Of 85 newly runnable rules, **0 reach t 2 against the market in 2009-2016** with turnover-scaled spreads. **12 of 85 are positive at all** (36 at flat costs). |
| Rules run on CRSP | **216 before + 85 tonight = 301 of 312.** The 11 left need news (5 rules, no history before 2026-09-11) or FINRA short volume (6 rules, starts 2009 and is not on disk). |
| Library verdicts (declared line) | **SURVIVES 2** (`quality_composite`, `cash_lowvol`) · CANNOT_DISTINGUISH 68 · FAILED_VARIANT 9 · NOT_DECIDABLE 6 (the 8-K rules). **Registration candidates: 0.** Both survivors beat their twin at t about 6 and DSR 0.98, and are **+0.07 and +0.03%/mo against the market in validation (t 0.34 / 0.15), with 4 of 8 years positive.** |
| Conditional cells | **10 declared, 10 read once.** CANDIDATE 0 · CANNOT_DISTINGUISH 2 · FAILED_VARIANT 8. |
| Search count used | **42,666** = 42,416 before tonight + 170 library cells (85 rules x 2 cost schemes) + 80 conditional looks (10 cells x (1 + 4 size bands + 3 eras)). |
| Registrations (job 3) | **None.** Nothing met "validate vs the market net of costs at t >= 2 with a majority of positive years". |
| Independent selector count | Unchanged. |
| Best forward paper strategy | Unchanged. Nothing matures before 2026-10-26. |
| New actionable finding | **The twin drag is the whole story, again.** Quality beats its matched twin by +0.6 to +1.0%/mo at t 6, while the twin trails the market by about as much. **Revision flow is state-dependent against its twin** (trend-on months +0.56%/mo gross, t 3.3; trend-off months -0.77 in validation), and none of it pays against the market after costs. |
| External execution drag | Not measured. |
| LLM spend | $0.00. |

## 1. The bridges: `backend/services/crsp_pit_bridges.py`

This is a new module. `crsp_rebuild.py` and `crsp_event_bridge.py` were **not edited**. The runner is
`scripts/bridges_on_crsp.py` (the bridge parts) with `scripts/bridges_on_crsp_run.py` (declare, run,
turnover, board). There are 19 offline tests in `backend/tests/test_crsp_pit_bridges.py`. Each one pins a
timing rule: an input dated after the decision date, or used before its lag has run, must never reach a
column.

| source | on disk | the timing rule | link | from (declared) |
|---|---|---|---|---|
| Short interest | Compustat `sec_shortint` + legacy, already joined to permno (`short_interest/comp_sec_shortint`) | `datadate` is the **settlement** date. A print is usable from **datadate + 26 days**, the top of the measured 10-26 day publication lag. The panel's own +14 is the median, so it would be early about half the time; it is not used. Stale after 60 days. | CCM (in the panel) | 1991-01. NYSE/AMEX only until 2003. |
| 13F | Thomson s34, 1996-2024 | Quarter q is usable from **q + 45 days (the filing deadline) + 1 business day**. Only rows whose vintage equals the quarter are counted (fdate == rdate), so a stale carry-forward never counts. | CRSP `dsenames` ncusip, name interval containing rdate (89.7%) | 1996-08 |
| 8-K items | EDGAR submissions, 2013-2026 | Acceptance time in New York; usable from the next business day. | the file's permno, else a dated CRSP ticker | **description only** |
| Analyst timing and skill | IBES `ptgdet` 12-month USD targets | The event day is max(anndats, actdats), used from +1 business day. LEAD/CHASE read the 10 sessions **ending the session before** the event day. FIRST MOVER means no raise by any broker in [day-30, day). A raise enters a broker's SKILL record only after its 63rd session is <= d. | `ibcrsphist` on the event date | timing 1999-09, skill 2000-12 |
| Fundamentals | Compustat `fundq` (INDL/STD/C/D) + CRSP `msf` | Usable from **max(rdq, datadate + 45 days for Q1-3 or 90 days for Q4) + 2 days**. These are the pre-2003 deadlines, so the rule is conservative in every era. TTM flows; "a year earlier" means four quarters back. Stale after 460 days. | CCM row active on datadate (LC/LU, P/C) | 1991-01 |

**Row by row.** For lead/chase and first-mover (an earlier vendor version was a look-ahead), 15 sampled raises
were recomputed from raw CRSP daily returns and IBES. The recomputation reads 10 sessions before the event day
for `ret10` and checks for any raise in the prior 30 days. **15 of 15 agree.** The last return used is always
strictly before the event day.

**The skilled share is not "everyone".** The median share of active brokers that count as skilled is **0.50 to
0.61 from 2001**. So skill is not a relabelled count of all raises, which was the 2026-09-26 review's worry.

**ANALYST-SKILL-1 was not re-run and its weights were not reused.** Its broker skills were estimated on
2013-2018, which is a look-ahead for any decision before 2019. The `analyst_skill_weight` column here is
`pit_features.skill_features`, walk-forward, with IBES revisions as claims. A claim resolves only after its 63rd
session.

### Coverage: names per month, mean within the year

| year | `dtc` (SI) | `inst_breadth_chg` (13F) | `lead_raises_90` | `analyst_skill_weight` | `ope_be` (Compustat) | `rd_intensity` | `n8k_90` |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1991 | 1,501 | - | - | - | 4,138 | 1,303 | - |
| 1996 | 2,001 | 6,465* | - | - | 5,564 | 1,925 | - |
| 2000 | 2,016 | 6,092 | 3,492 | 1,170* | 5,305 | 2,069 | - |
| 2004 | 4,748 | 4,697 | 3,222 | 1,641 | 4,245 | 1,786 | - |
| 2008 | 4,444 | 4,426 | 3,345 | 1,951 | 3,916 | 1,687 | - |
| 2013 | 3,586 | 3,435 | 2,877 | 1,951 | 3,232 | 1,396 | 391* |
| 2016 | 3,641 | 3,523 | 3,073 | 1,983 | 3,200 | 1,515 | 888 |
| 2024 | 3,882 | 3,788 | 3,273 | 2,123 | 3,281 | 1,866 | 2,038 |

\* The receipt counts the whole year; months before the declared start (13F 1996-08, skill 2000-12, 8-K
2014-01) are set to NaN on the panel. The full series are in the bridge receipts.

**The 8-K bridge exists, but it cannot decide anything.** The pull covered **2,594 CIKs chosen from today's
tickers** and starts in 2013: dead issuers are absent and there is no design window. The six 8-K rules ran as
description and are **NOT_DECIDABLE**.

## 2. The library rules: what was declared, what was run

The engine is `library_on_crsp.part_run`, **unchanged**: the rule's own k, costs on, and the 21-draw matched
twin with two seed sets. It ran twice, at flat band costs and with the per-name Corwin-Schultz spread charged
as a full round trip each month.

The board applies the reviewer's lesson. The spread is **scaled by each rule's measured monthly turnover**:
rule net = flat - turnover x (flat - full CS). The twin is at full CS, and the market is costless.

**Split (hold month):** design 1991-2008, validate 2009-2016 (read once), 2017-2024 last and as description.
2017-2024 is **not clean** for library rules: they were written on the 2016-2026 vendor calendar.

**Declared line (hashed before any rule ran).** A rule SURVIVES iff, on the turnover-scaled variant, all of
these hold:

- rule - twin > 0 in design and in validate;
- rule - market > 0 in design and in validate;
- rule - twin t >= 2 over 1991-2016;
- DSR >= 0.95 at the full count.

It becomes a **registration candidate** only if it also reaches rule - market t >= 2 in validation, with at
least 5 of 8 years positive.

**Failure reasons (a rule can fail several):**

| reason | rules |
|---|---:|
| DSR < 0.95 | 76 |
| rule - market <= 0 in validate | **67** |
| rule - market <= 0 in design | 63 |
| rule - twin t < 2 over 1991-2016 | 36 |
| rule - twin <= 0 in validate | 15 |
| rule - twin <= 0 in design | 11 |
| NOT_DECIDABLE (8-K) | 6 |

### The leaders

All figures are %/mo on the turnover-scaled variant, keyed on the hold month, with t on 3-month blocks. MDE is
over 1991-2016. Dollar volume is the median pick ADV by decade.

| rule | vs twin D / V / H | twin t (MDE) | vs market D / V / H | mkt t in V (yrs +) | V vs mkt: flat / full CS | DSR @42,586 | turnover | pick ADV $M |
|---|---|---|---|---|---|---:|---:|---|
| **`quality_composite`** SURVIVES | +0.95 / +0.69 / +0.77 | **6.3** (0.38) | +0.32 / +0.07 / -0.05 | 0.34 (4/8) | +0.14 / -0.49 | **0.983** | 11% | 11 → 42 |
| **`cash_lowvol`** SURVIVES | +0.88 / +0.58 / +0.59 | **6.0** (0.37) | +0.40 / +0.03 / -0.19 | 0.15 (4/8) | +0.11 / -0.44 | **0.985** | 15% | 9 → 108 |
| `ope_be` | +0.79 / +1.04 / +1.00 | 6.1 (0.40) | +0.15 / **+0.50** / +0.02 | **1.85 (5/8)** | +0.60 / -0.19 | 0.90 | 13% | 10 → 78 |
| `quality_composite_ivw` | +0.75 / +0.61 / +0.70 | 5.9 | +0.27 / +0.07 / -0.05 | 0.38 | | 0.947 | 11% | |
| `quality_composite_secrel` | +1.27 / +0.56 / +1.06 | 5.6 | +0.83 / -0.07 / +0.10 | -0.40 | | 0.958 | 14% | |
| `div_lead_earn_mom` | +1.39 / +0.97 / +0.81 | 4.6 | +0.48 / -0.27 / -0.25 | -0.56 | | 0.75 | 53% | |
| `short_covering` | +0.51 / +0.66 / +0.34 | 4.0 | -0.18 / -0.01 / -1.02 | -0.02 | +0.49 / -0.20 | 0.50 | 72% | 7 → 28 |
| `low_dtc_gp` | +0.74 / +0.76 / +0.70 | 4.0 | -0.18 / -0.02 / -0.56 | -0.06 | | 0.46 | 47% | |
| `qc761_ebit_ev_ebit_ic_large_annual` | +0.78 / +0.56 / +0.61 | 3.8 | -0.21 / +0.18 / -0.18 | 1.01 (5/8) | +0.48 / -0.15 | 0.42 | 47% | 154 → 214 |
| `lead_minus_chase` | +0.59 / +0.59 / -0.07 | 3.6 | -0.14 / -0.04 / -0.67 | -0.14 | +0.34 / -0.39 | 0.18 | 53% | |
| `ibes_skill_net_raises` | +0.75 / +0.70 / +0.90 | 3.5 | +0.07 / -0.06 / +0.30 | -0.22 | +0.26 / -0.45 | 0.16 | 44% | 105 → 515 |
| `first_mover_raises` | +1.08 / +0.37 / +0.80 | 3.4 | +0.24 / -0.23 / -0.21 | -0.78 | | 0.31 | 51% | |
| `skill_raises_large` | +0.50 / +0.64 / +0.86 | 3.4 | -0.41 / -0.00 / +0.17 | -0.00 (5/8) | | 0.08 | 40% | 204 → 521 |

**Reading the two survivors honestly.**

1. **The survival is against the twin, not the market.** In validation, `quality_composite` beats the twin by
   +0.69%/mo but the market by only +0.07. That puts the twin about 0.6%/mo below the market: the same twin drag
   as 2026-09-29 (-0.85%/mo there). The long quality leg avoids small, high-volatility junk, and the twin does
   not.
   - By year against the market in validation: +2.3, +9.3, +9.2, -7.1, -1.5, -8.2, -3.6, +6.0.
   - The leave-one-year-out worst against the twin is +0.81 (dropping 2000).
2. **The inputs carry a known second-order leak.** Compustat stores the current vintage of each value, and
   restatements are not as-first-reported. `gp_at` and `debt_at` are also WRDS-ratio proxies. A t of 6 against
   the twin is plausible for the published profitability/low-risk premium. Some of it may be restatement.
3. **Capacity and costs are not the problem.** Turnover is 11-15%/month, and median picks trade $10-100M/day.
   The problem is that the premium over a junk-heavy twin is not a premium over the market.

**By family (turnover-scaled; SU = survives, CA = cannot distinguish, FA = failed variant):**

- quality: 1 SU, 4 CA;
- fundamental inflection (rev/margin acceleration, turns): 10 CA, 1 FA;
- short interest: 6 CA, 1 FA (`short_squeeze`);
- lead/chase: 6 CA;
- analyst skill: 6 CA;
- 13F breadth: 2 FA;
- distance to default: 3 FA;
- value (`ebit_ev`, `earnings_yield`): 2 CA;
- intangibles: 2 CA;
- 8-K: 6 NOT_DECIDABLE.

**Verdicts in the project's vocabulary:**

- **Quality / profitability (`quality_composite`, `cash_lowvol`, `ope_be`):** SURVIVES the declared line
  against the twin. **DEPRIORITIZED as a capital idea**: it does not beat the market out of sample net of costs
  (t 0.3). Not rejected as a ranking.
- **Short interest (days-to-cover, covering):** CANNOT_DISTINGUISH. The twin t is 4 but the market spread is
  zero. Consistent with NEGATIVE_RESULTS §24 ("real gross, dead net"). `short_squeeze`: FAILED_VARIANT.
- **Lead/chase, first mover, analyst skill:** CANNOT_DISTINGUISH. These are relative rankings among covered
  names (twin t 3.4-3.6) and none survives costs against the market. This closes these implementations.
- **13F breadth (`inst_breadth_up`, both bands):** FAILED_VARIANT.
- **Distance to default rising (all three):** FAILED_VARIANT.
- **8-K rules:** NOT_DECIDABLE on the data on disk.

## 3. Conditional questions (job 2)

**The engine was declared before any cell ran:**

- monthly decisions, one-month hold, equal weight over every eligible name that meets the condition;
- fewer than 5 names means the cell holds the market;
- the **matched twin** is the cell-mean of non-selected names in the same size band x vol x 12-1 cell, read
  gross vs gross;
- **costs** charge each traded weight half of max(Corwin-Schultz, the flat band): era-realistic, and scaled by
  actual turnover;
- the **market** is FF mkt + rf.

**Decision rule.** A cell is a CANDIDATE iff, in validation, net - market > 0 at t >= 2 with 5 of 8 years
positive, **and** in design net - market > 0 and gross - twin > 0.

All figures are %/mo.

| cell | question | net - market D / **V** / H | V t (MDE) | V yrs + | gross - twin D / V / H (full t) | names | cost bps/mo | verdict |
|---|---|---|---|---|---|---:|---:|---|
| C01 | revision flow right after a positive surprise | -0.09 / **-0.48** / -1.13 | -2.54 (0.52) | 1/8 | +0.46 / +0.18 / -0.14 (1.7) | 144 | 80 | FAILED_VARIANT |
| C02 | 3+ insiders buying in 30 days after a -40% drawdown | -1.41 / **+0.26** / -0.76 | 0.46 (1.58) | 4/8 | +0.97 / +0.71 / +0.29 (1.2) | 16 | 115 | CANNOT_DISTINGUISH |
| C03 | heavily shorted + rising targets + up month | -0.65 / **-0.97** / -0.47 | -3.50 (0.78) | 1/8 | -0.41 / -0.33 / +0.53 (-0.4) | 41 | 71 | FAILED_VARIANT |
| C04 | new position by a concentrated 13F manager | -0.45 / **+0.14** / -0.23 | 0.60 (0.65) | 5/8 | -0.19 / +0.23 / +0.28 (0.9) | 590 | 18 | CANNOT_DISTINGUISH |
| C05 | target raise with <= 2 brokers | +0.25 / **-0.34** / -0.71 | -1.31 (0.72) | 3/8 | +0.30 / +0.03 / -0.04 (1.1) | 150 | 46 | FAILED_VARIANT |
| C06 | top net raises, market trend ON | +0.46 / **-0.04** / -0.22 | -0.30 (0.34) | 5/8 | **+0.56 / +0.13 / +0.34 (3.3)** | 363 | 22 | FAILED_VARIANT |
| C07 | top net raises, market trend OFF | +0.01 / **-0.24** / +0.03 | -1.75 (0.38) | 1/8 | -0.00 / -0.77 / -0.44 (-1.4) | 326 | 43 | FAILED_VARIANT |
| C08 | top net raises, high-vol market | +0.30 / **-0.26** / +0.02 | -1.64 (0.44) | 0/8 | +0.42 / -0.29 / +0.23 (0.9) | 350 | 35 | FAILED_VARIANT |
| C09 | top net raises, low-vol market | +0.18 / **-0.03** / -0.19 | -0.29 (0.30) | 4/8 | +0.21 / +0.15 / +0.14 (1.7) | 356 | 21 | FAILED_VARIANT |
| C10 | a lead raise in a name 30%+ below its high | -1.24 / **-0.75** / -1.28 | -1.29 (1.64) | 3/8 | -0.12 / -0.21 / -0.16 (-1.0) | 137 | 59 | FAILED_VARIANT |

**Where it lives (the size band, gross - twin over the full sample, t):**

- **The revision signal's relative edge is a small-cap, trend-on phenomenon.**
  - Trend on: small +0.71 (t 4.9) vs mid +0.28, large +0.21.
  - Low-vol market: small +0.55 (t 4.7).
  - Trend off: every band negative.
  - The state dependence is real **against the twin**, and it is not an edge against the market: small-name
    costs and the market's own return take it back.
- **C01's relative edge is modest** (+0.46 in design, t 1.7 full). It turns over 91% a month at 80 bps. Net of
  that it loses to the market in 7 of 8 validation years.
- **C02 (insider clusters after drawdowns) is underpowered, not refuted.**
  - It holds about 16 names and had a 2.5-year design window; the validation MDE is 1.58%/mo.
  - Against the twin it is +0.97 / +0.71 / +0.29.
  - It lives in small names (small +0.46 against the twin; large and mid negative).
  - CANNOT_DISTINGUISH is the honest word.
- **C04 (13F concentrated initiations)** is broad (590 names) and cheap (18 bps). It is about zero everywhere.

**Conditional verdicts:**

- **Revision flow, conditioned on regime or surprise:** FAILED_VARIANT against the market in every declared
  condition.
- **The squeeze condition:** FAILED_VARIANT, and it is the worst cell (t -3.5).
- **Insider clusters after drawdowns and 13F concentrated initiations:** CANNOT_DISTINGUISH.
- **These close the tested conditions, not the mechanisms.** The global negative now has its conditional
  companion for ten situations. Revision flow is a trend-on, small-cap relative signal that costs and the
  market consume.

## 4. Job 3: registration

**Nothing registered.**

- No library rule reached t >= 2 against the market in validation.
- No conditional cell was a CANDIDATE.
- `scripts/shadow_bayes_rule.kill_rule_from_measured_gap` was not called.

For the record, if the owner wants a free shadow of the best near-miss (`ope_be`, validate +0.50%/mo vs the
market, t 1.85, 5 of 8 years), the turnover-scaled gap sd against the market is 3.27%/mo. A 126-session kill line
from that sd would sit near -1.645 x 3.27 x sqrt(6) ≈ -13%. That line can only catch a disaster.

## 5. Files

| role | path |
|---|---|
| bridge functions (pure) | `backend/services/crsp_pit_bridges.py` |
| bridge runner | `scripts/bridges_on_crsp.py` |
| declare / run / turnover / board | `scripts/bridges_on_crsp_run.py` |
| conditional cells | `scripts/conditionals_on_crsp.py` |
| tests (offline, synthetic) | `backend/tests/test_crsp_pit_bridges.py` (19), `backend/tests/test_bridges_and_conditionals.py` (8) |
| receipts | `backend/data/optimus/crsp_rebuild/` as listed at the top (parquets are local) |

- `test_signal_reachability` passes: the new module is reached through the scripts.
- `backend/config.py` is untouched. The constants live in the module, as in `crsp_event_bridge`.
- Nothing is committed.

## WHAT WORKS

- **The point-in-time discipline, end to end.**
  - Five new sources are bridged to permno, each with its own lag.
  - The declarations were hashed before any rule or cell ran.
  - The row-by-row check agreed 15 of 15.
  - The whole library except 11 rules now runs on survivor-free CRSP.
- **Quality/profitability as a relative ranking.** Twin t about 6, DSR 0.98 at 42,586. It is cheap to hold
  (11-15% turnover).
- **Measuring the twin drag.** It is the single most important correction to every "beats its twin" number
  the project holds.

## WHAT DOES NOT

- **Any of the 85 newly runnable library rules as a stand-alone book against the market.** 0 reach t 2 in
  validation, and 12 of 85 are even positive.
- **Every declared conditional variant of revision flow**: surprise, regime (both), volatility (both), low
  coverage and lead-in-beaten-down.
- **The short-squeeze condition.**
- **13F breadth and distance-to-default rules.**
- **The 8-K pull as a research instrument.** It is survivor-selected and starts in 2013.

## HIGHEST-EV EXPERIMENT

**Stop benchmarking against a junk-heavy twin, and test quality as a market-tracking overlay.**

- **The test.** Take a top-500-by-dollar-volume cap-weighted base, which is already market-like, and tilt it by
  `quality_composite` / `ope_be`. Use the revision-tilt construction of 2026-09-29, **pre-declared**: design
  1991-2008, validate 2009-2016 against the market only, turnover-scaled CS costs, and count 42,666 + the new
  cells.
- **Why it ranks first.** Quality is the only family tonight with a relative edge (t 6) that is also cheap to
  hold. The revision tilt failed on a large-cap base because the signal was weak there. Quality's edge must be
  checked the same way before anyone calls it an edge.
- **The honest prior is low.** Large-cap `quality_composite_large` is +0.61 against the twin but -0.03 against
  the market in validation.
- **Cost and odds.** About 1 hour, $0. P(changes the roadmap) is about 0.15.
- **Second, a harder rerun of the survivors.** Use as-first-reported fundamentals: Compustat `fundq`
  point-in-time vintages are not on disk, but the SEC facts history is, for 2009+. That would tell how much of
  the t 6 is restatement.

## CONTINUE FROM HERE

```bash
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_crsp_pit_bridges.py backend/tests/test_bridges_and_conditionals.py -q
python -m scripts.bridges_on_crsp --part si|f13|eightk|analyst2|fund --run-id <new id>     # ~5 s .. ~9 min each
python -m scripts.bridges_on_crsp --part declare --run-id <id>                             # set BRIDGE_RUN first
python -m scripts.bridges_on_crsp --part run --declaration <id> --run-id <id> [--cs]       # ~6 min each
python -m scripts.bridges_on_crsp --part turnover --declaration <id> --run-id <id>         # ~3 min
python -m scripts.bridges_on_crsp --part board --declaration <id> --flat-run <id> --cs-run <id> --turnover-run <id>
python -m scripts.conditionals_on_crsp --part declare --run-id <id> --prior-count 42416 --library-cells 170
python -m scripts.conditionals_on_crsp --part run --declaration <id>                       # ~2 min, reads once
```

**Commit together:**

- the four code files;
- the two test files;
- this note;
- the `pit_*.json`, `bridges_*.json`, `conditionals_*.json` and `library_rules_BR_*.jsonl` receipts.
