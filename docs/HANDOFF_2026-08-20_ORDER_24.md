# HANDOFF — 2026-08-20, ORDER 24 discovery run (day session)

Order 23 was not executed verbatim. Two independent reviews landed first,
both making the same objection — eight hours of compute could produce an
impressive dataset without producing eight hours of evidence — and the
run was restructured around their amendments
(`docs/ORDER_24_DISCOVERY_RUN_REVISED.md`). Every headline below is a
measurement, and three of them close a line of work rather than opening
one, which is the point.

---

## NEW INFORMATION ACQUIRED

### 1. Aegis DOES beat the options market on risk — but only with options, and only on ordering

`OPTION-INCREMENTAL-RISK-1`, the test both reviews named as top priority.
Nine arms on identical rows, folds and missingness; QLIKE primary, rank
IC secondary, bias carried explicitly. Modern era (226,228 stock-months,
8 folds 2017-2024):

| arm | QLIKE | MSE(log var) | rank IC | bias | %under |
|---|---|---|---|---|---|
| iv_only | 0.3118 | 0.7543 | 0.7510 | −0.3227 | 31.3% |
| har_iv | 0.3783 | 0.5827 | 0.7665 | +0.0284 | 51.2% |
| iv_scaled | 0.3853 | 0.6431 | 0.7510 | +0.0332 | 52.6% |
| **lgbm_options** | 0.5003 | **0.4991** | **0.7978** | +0.0420 | 49.7% |
| mlp_options | 0.5870 | 0.5169 | 0.7934 | +0.0318 | 49.0% |
| har | 0.6700 | 0.7740 | 0.6584 | +0.1177 | 54.9% |
| lgbm_numeric | 0.7093 | 0.6123 | 0.7587 | +0.0583 | 49.5% |
| rv_m | 0.8042 | 0.9654 | 0.6587 | −0.0282 | 48.2% |

Raw implied variance wins QLIKE. It wins it by **over-forecasting**: bias
−0.32 in logs, under-forecasting only 31% of the time. That is the
variance risk premium, and QLIKE punishes under-forecasting ~linearly
while punishing over-forecasting only ~logarithmically, so the asymmetry
pays it. On the symmetric loss the ordering inverts:

| contrast (MSE log var) | modern | early |
|---|---|---|
| lgbm_options vs iv_scaled | +0.144 (MDE 0.064) **CLEARS** | +0.064 (MDE 0.016) **CLEARS** |
| lgbm_options vs numeric twin | +0.113 (MDE 0.062) **CLEARS** | +0.064 (MDE 0.016) **CLEARS** |
| har vs iv_scaled | −0.131 **CLEARS** (IV wins) | −0.169 **CLEARS** (IV wins) |
| **lgbm_numeric vs iv_scaled** | +0.031, **below MDE** | −0.000, **below MDE** |

Read the last row carefully. **Without options features the model family
does not clear the IV baseline at all.** Options are not a refinement;
they are the reason there is an edge over the market's own estimate.

Two corrections to the standing story:
- **HAR-RV is not the baseline that threatens us.** The review was right
  to demand it and wrong about which way it would cut: HAR loses to IV
  in both eras and beats only trailing realized variance. The baseline to
  beat is **IV-scaled**.
- **"0.79" was always a rank IC on a volatility target, never accuracy.**
  It survives — 0.7978 modern, 0.7991 early — and it is an *ordering*
  claim. Anything consuming the LEVEL must use the calibrated model.

Reproduced out of era: the entire ladder repeats on 1990–2012
(261,158 rows, folds 2001-2012).

### 2. Shift-invariance PASSES — the risk finding is not living on same-instant information

Every feature lagged one extra month. All arms degrade **gracefully**
(rank IC −0.04, no collapse) and every comparative conclusion holds:
lgbm_options still beats iv_scaled (+0.110 CLEARS) and its numeric twin
(+0.050 CLEARS). A result that collapsed here would have been living on
information it should not have had.

### 3. A single stock-month is 70% of ridge's entire loss

Early era, per-arm QLIKE tail:

| arm | mean QLIKE | p99 | max single row | share of total |
|---|---|---|---|---|
| lgbm_options | 0.319 | 3.77 | 902 | 1.1% |
| ridge_numeric | 581.3 | 4.53 | 105,935,854 | **69.8%** |
| mlp_options | 585.5 | 3.86 | 105,935,854 | **69.3%** |

Ridge and the MLP have *ordinary* p99s and *healthy* MSE(log var). One
row of unbounded extrapolation to a near-zero variance forecast produces
~70% of their total loss. **Fine on average, ruinous in the tail that
sizing actually cares about.** This is why the shipped artifact is LGBM
despite the MLP's competitive rank IC — and it is a general warning about
judging risk models by average losses.

### 4. Perfect regime foresight is worth +0.24%/yr — the family closes

`REGIME-ORACLE-CEILING-1`. Lead with the oracle instead of building a
predictor and discovering the ceiling afterwards. 153 JKP US factors ×
420 months; regime = contemporaneous quartile of realized market vol (the
oracle's private knowledge); compared against a null regime sequence with
the **same transition matrix**.

| policy | gross gap | switch drag | NET gap | null p95 | p |
|---|---|---|---|---|---|
| oracle | +9.97%/yr | 3.63% | +6.34% | +2.87% | 0.000 |
| oracle_loo (honest) | +4.33%/yr | 4.09% | **+0.24%** | −0.77% | 0.032 |

Excess over the selection null: **+1.00%/yr** against a 3%/yr economic
bar. `CEILING_STATISTICALLY_PRESENT_BUT_ECONOMICALLY_NEGLIGIBLE`.

The null is the experiment: picking the best of 153 factors four times
over manufactures a large gap from nothing (the naive oracle's null p95
alone is +2.87%/yr). And switching costs eat essentially the whole honest
gross gap. **Perfect** state knowledge nets +0.24%/yr; a real predictor
is imperfect and pays the same costs.

**Scope:** this closes regime-conditional **factor selection** on this
zoo. It does not close regime conditioning of **risk/sizing**, where §59
says the clock runs ~30× faster. That is the surviving redirect.

### 5. 86 books are 3.5 behaviours — so MEGA-SWEEP-2 was replaced

`STRATEGY-EFFECTIVE-DIMENSION-1`, on the existing corpus at zero new
simulation cost:

| view | participation ratio | effective rank | top eigenvalue share | n for 90% |
|---|---|---|---|---|
| return | 2.36 | 3.53 | 0.610 | 3 |
| style-residual | 2.41 | 3.63 | 0.598 | 3 |
| co-crash tail | 2.67 | 4.81 | 0.590 | 6 |

Consensus clusters 6/3/3/2 at cuts 0.2/0.3/0.4/0.5; stability 0.903.
Running 1,500–3,000 more combinations of the same seven signals cannot
raise a dimensionality the signal set has already exhausted. It buys a
longer leaderboard and a worse selection problem — precisely what the
reviews predicted. **The blind mega-sweep was cancelled on this evidence**
and the compute redirected to §6.

Selection-overfit battery on the same corpus: best book
`low_vol|inverse_vol|trim|50`, Sharpe 0.918; matched null (demeaned,
block-bootstrapped rows preserving cross-book correlation) max-Sharpe p95
0.682 → p=0.0050; **deflated Sharpe 0.8367, FAILS at 0.95**; PBO 0.2197.
The two disagree informatively — the matched null respects the corpus's
effective n (~3.5), DSR charges nearer the nominal 86. Honest reading: a
*family* is showing, not a book, and one family out of ~3.5 independent
behaviours is weak evidence. Note the winner is a **low-vol** book.

### 6. No new information class opens a new direction — the bottleneck is construction, not data

`INFORMATION-DIMENSION-1`, 216 books over 18 signals in 6 classes.
Owned (price + fundamental, 72 books) effective rank **3.694**. Each
candidate class is compared against **size-matched** random subsets of an
extra-price-signal control pool, because effective rank rises mechanically
with the number of series added:

| class | books | increment | control (same n) | excess | p | verdict |
|---|---|---|---|---|---|---|
| price_extra | 48 | +0.299 | — | — | — | CONTROL POOL |
| options | 36 | +0.159 | +0.283 | −0.124 | 1.000 | no new direction |
| expectations | 36 | **−0.247** | +0.283 | −0.530 | 1.000 | no new direction |
| liquidity | 24 | +0.191 | +0.245 | −0.054 | 0.925 | no new direction |

None beats a matched dose of *more price signals*. Expectations actively
**collapses** the space.

Corroboration from an independent route: clustering all **216** books —
18 signals spanning six information classes — at correlation distance 0.3
yields **3 clusters**. Six times the signal families of mega-sweep-1
produced fewer distinct behaviours than mega-sweep-1's own 86 books did
(which gave 3 at the same cut). Adding information classes did not add
behaviours.

**Put §1 and §6 together and you get the most useful thing learned
today.** Options carry real, replicated information at the security-risk
level (+0.113 / +0.064 MSE log var, CLEARS in both eras). The same
options carry **no new behavioural direction** once poured through a
top-N long-only monthly-rebalance grammar. The information is real; the
portfolio construction destroys it. **The binding constraint is the
construction layer, not the data feed.**

That is a direct argument for *deferring* Order 22's world-sensor
expansion. Adding ACLED, FIRMS, shipping and prediction markets buys more
information classes; this run says our construction layer cannot express
the ones we already bought.

### 7. Every grammar decision is a risk decision, not a return decision

`RULE-INTERVENTION-1`, matched paired contrasts (each pair differs in
exactly one coordinate, so signal/universe/dates/costs cancel; unit of
evidence is the date block):

| contrast | dRet/yr | ret? | dVol | vol? | dMaxDD | dd? |
|---|---|---|---|---|---|---|
| inverse_vol − equal | −1.24% | ns | −6.93% | sig | +6.10% | sig |
| rank − equal | +1.47% | ns | +8.26% | sig | −3.94% | ns |
| rank − inverse_vol | +2.70% | ns | +15.19% | sig | −10.04% | sig |
| exempt − trim | −1.66% | ns | −3.78% | sig | +2.08% | ns |
| top_n 50 − 100 | +2.44% | ns | +8.01% | sig | −4.60% | ns |

Not one decision moves return detectably (return MDEs of 5–18%/yr dwarf
the 1–3%/yr effects). All five move volatility significantly. §59 on the
grammar itself.

---

## WHAT DIED

- **Regime-conditional factor selection.** Closed by ceiling, not by a
  failed predictor. Cost: one run.
- **The blind 1,500–3,000-book MEGA-SWEEP-2.** Cancelled by the effective
  dimension measurement before it consumed the session.
- **"HAR-RV is the baseline to beat".** It is not; IV is.
- **The MLP as a risk-head candidate.** Loses to LGBM on both losses,
  degrades worst under lag, and blows up in the tail.
- **Expectations/liquidity/options as sources of new portfolio-behaviour
  diversity** *under this grammar*. Not as sources of information.

## WHAT REMAINS NOT ESTABLISHED

- Whether the options-augmented head's advantage survives to a forward
  lane. Nothing here is forward evidence.
- Whether a better construction layer recovers the information §6 shows
  is being destroyed. That is now the top open question.
- Whether regime conditioning helps **risk/sizing** (untested; §59 says
  it resolves ~30× faster than the selection question that just closed).
- Any return claim about the new signal families. INFORMATION-DIMENSION-1
  measured structure only and deliberately printed no leaderboard.

---

## INTEGRITY: two audits, two real defects

**WRDS-META-INTEGRITY-1** — all **119** dataset metas claimed
`window = [2013-01-01, 2024-12-31]`, including every 1990–2012 slice and
every per-year 13F/OptionMetrics file, because `_write()` stamped module
constants instead of reading the frame. Verdict **LABELS_ONLY**: 0/119
row-count mismatches. The pulls were right, the labels lied. Window and
universe now derive from the data; metas regenerated with the stale claim
preserved under `metadata_correction`. The derived metadata immediately
surfaced what the constant hid — `compustat_fundq`'s `rdq` runs to
2026-03-26 against `datadate ≤ 2024` (legitimate late/restated filings).

**CHRONOLOGY-AUDIT-1** — 9 checks, 2 FAIL:
- **C1 PASS** — the options risk head is chronologically clean. 307,924
  joins, lag(formation − opt_date) min 0, p50 0, max 30, **zero
  negatives**. The review's top suspicion (IV at t joined to vol over
  t..t+h) is **refuted by measurement**. The live `lag > 14` filter is a
  staleness cap and is one-sided, so both consumers now assert the sign
  rather than relying on it holding by luck.
- **C2 PASS** — `fwd_vol[t] == std(ret[t+1..t+21])`, excludes formation day.
- **C4 FAIL** — `tr_13f.s34` `fdate` is a **vintage stamp, not an SEC
  filing date**: `fdate == rdate` on 97.2% of 76.9M rows and every
  `fdate` is a quarter-end. The table carries **no public-availability
  column**; treating `fdate` as knowledge time grants the full 45-day
  statutory filing window of lookahead.
- **C7 FAIL** — `manager_actions_quarterly_v1`'s meta claims "features key
  on fdate, never rdate", but `fdate` was never propagated into the
  artifact. Its only time column is `q`, derived from **rdate** — which
  the meta itself forbids. The claim was **unsatisfiable by construction**.
- **C3/C5 QUANTIFIED** — 99.9% (modern) / 99.4% (early) of IBES rows
  carrying an `actual` have `anndats_act` *after* `statpers` (median 161d
  / 167d of lookahead if read at `statpers`). Compustat `rdq` is NULL on
  7.1% of rows — no honest knowledge date; drop, never impute.

**Consequence:** `MANAGER-WINNER-HOLDING-1`, `MANAGER-ADD-TO-WINNER-1`,
`MANAGER-DRAWDOWN-BEHAVIOR-1`, `MANAGER-CONVICTION-PERSISTENCE-1` stay
**BLOCKED** until a v2 library gates on `rdate + 45d`. On top of the
already-declared split-adjustment limit, not instead of it.

---

## ARTIFACTS

**`risk_head_vol_lgbm_options@2.0.0@31b9b8d62c777e97`** — the model layer
was the programme's unpinned surface. Now:
`model.txt · features.json · calibration.json · train_window.json ·
model_card.md · MANIFEST.sha256`. A lane may reference a model only by
`name@semver@sha256` and refuses if the hash does not resolve. The model
card states what it beat, on which loss, and **how it fails**.

Held out 2022–2024 (fit <2020, calibrate 2020–21, all disjoint):

| arm | QLIKE | MSE(log var) | rank IC | bias |
|---|---|---|---|---|
| model (raw) | 0.5580 | 0.3963 | 0.8140 | +0.0870 |
| model (calibrated) | 0.5000 | 0.3890 | 0.8140 | −0.0159 |
| iv_only baseline | 0.2668 | 0.7373 | 0.7530 | −0.3151 |

**The calibration caught itself being a no-op.** The first build fitted
the level offset on the fit rows — where the booster had already driven
the mean residual to ~0 — so "raw" and "calibrated" came out
byte-identical while still printing a calibrated column. Green and empty,
the house failure mode. Three disjoint spans in time order fixed it; the
offset is +0.1030 and does real work.

**Datasets** (Tier PRIVATE per the new receipt policy, each with a public
stub in `docs/datasets/`): `STOCK_RISK_DATASET_V1_modern`,
`STRATEGY_STATE_DATASET_V1`. Every row carries a `date_weight` summing to
1.0 within its date; the strategy dataset splits weight by **cluster**
first, so 216 books spanning ~4 behaviours cannot vote 216 times.

---

## FOR MURAT (three minutes)

1. **The G2 risk lane hold is resolved by measurement.** The review asked
   to hold it because the options head was unbenchmarked against HAR-RV
   and unaudited for the timestamp bug class. Both are now done: it beats
   the baseline that actually threatens it (IV, not HAR), in both eras,
   and the chronology audit passes with zero negative lags. **One
   condition:** anything consuming the LEVEL must use the calibrated
   prediction, not the raw one. Pin
   `risk_head_vol_lgbm_options@2.0.0@31b9b8d62c777e97`.
2. **Order 22's world-sensor arc should wait.** Not because the idea is
   wrong, but because §6 says our construction layer cannot express the
   information classes we already bought. Buying more feeds before fixing
   that spends money on a bottleneck we have now measured.
3. **The manager/teacher library needs a v2 before any behaviour claim.**
   Its PIT column does not exist in the artifact and would not be a
   knowledge date if it did.
4. **`NEGATIVE_RESULTS.md` #4 amended** — survivorship "not buildable on
   free data" is still true on free data and is no longer the operative
   constraint. Recorded as an amendment, never a deletion, with what does
   NOT change listed.
5. **Two decisions await you:** the WRDS receipt policy
   (`docs/DECISION_WRDS_RECEIPT_POLICY.md`) and the benchmark-restamp
   acceptance criteria added to P-day-2026-08-19a.

## NEXT 10 MACHINE JOBS

1. `CONSTRUCTION-BOTTLENECK-1` — the top open question. Does a
   construction layer that can express security-level risk information
   (sizing by predicted vol, continuous tilts rather than top-N,
   risk-parity over signal blocks) recover the direction §6 shows being
   destroyed? Same signals, different grammar, effective dimension as the
   readout.
2. `REGIME-RISK-CONDITIONING-1` — the surviving half of the regime
   question, on the §59 clock: does state conditioning improve **vol/
   drawdown** prediction, where the oracle ceiling was never measured?
3. Manager library **v2**: `rdate + 45d` knowledge gate, `cfacshr`
   split adjustment, v1-vs-v2 transition matrix diff. Unblocks four
   MANAGER-* trials.
4. Persist per-book **holdings and turnover paths** in the next sweep —
   two of the five similarity views are currently unanswerable.
5. Early-era artifact twin of the risk head + era-transfer both
   directions with the ratio reported.
6. `REENTRY-OPTION-VALUE-1` design (hold / trim / exit / exit+confirmation
   re-entry variants), all triggers declared before outcomes.
7. Frozen PIT-CRSP replication of `CONVEXITY-PRESERVATION-1`.
8. `STREAK-MECHANISM-1` — is five-up-day reversal concentrated in
   abnormal volume, skew, lottery/MAX state, attention, illiquidity?
   Target distinction: transient winner vs structural winner.
9. Add `reproducibility` fields to receipt writers, and enforce the
   stub-on-withhold rule in code rather than by checklist.
10. Prequential state estimator (filtered probabilities only) — only if
    §2 above finds a ceiling worth predicting.

---

## LANE RAIL

Nightly IIF launcher fires **17:00 local** and is mid-receipt-clock
(clean-clock firing #1 tonight). All heavy compute for this run
checkpointed and stopped before it. No lane write-paths were touched, no
NAV/positions deployment, SIMULATION labels throughout. Screen survivors
earned registrations, never promotions.
