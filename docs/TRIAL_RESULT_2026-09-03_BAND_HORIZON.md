# TRIAL RESULT 2026-09-03 — BAND HORIZON / SELF-ATTACK

**Licence:** `PRODUCT_EXPERIMENT`. Nothing here trades, sizes, seals or orders.
The beta-neutralised series is a MEASUREMENT, not a book.

**Executes:** `PREREG_BAND_IS_BETA_1` (primary) and the random-ordering control
arm of `PREREG_RANK_VS_EXPRETURN_1`, both in `Aegis module/TRIALS/`.
`PREREG_BIAS_CORRECTED_BAND_1` was **NOT RUN** — see §8.

**Receipt (every headline number below is in it):**
`backend/data/optimus/tracker_backtest/band_horizon_20260903.json`
**Code:** `scripts/band_horizon_run.py`, `learner/beta.py`
**Data:** `backend/data/optimus/learner/train_table.parquet` (the learner's PIT
table, 441,278 rows × 134 cols, 2013-2024, REUSED not rebuilt) +
`backend/data/optimus/learner/beta_panel.parquet` (built here, 11.06m
name-date betas).

---

## 0 · RESULTS SCOREBOARD

| | |
|---|---|
| New actionable finding | **Three, and they are corrections, not discoveries.** (i) the prior's "IC t 34.5 at 12m" is an OVERLAP ARTEFACT — `n_effective` is 8, not 96, and the block t is FLAT across horizons; (ii) the famous **+16.55%/yr** is an excess over the *analyst-covered panel's own equal-weighted mean*, not over the market — against the VW market the same book earns **+18.93%/yr with t 1.65**, and against the panel **t 2.25**; (iii) the 3-5 band is **not** a beta/size effect: a beta-and-cap-matched outside-band basket earns **+1.02%/yr**. |
| Best historical net strategy vs the market | 3-5 band, 1-month clock, EW, net 10bps: terminal **17.06×** vs market **6.63×** over 2013-2024 — at a **−47.5%** max drawdown against the market's **−33.3%**, and **t_block 1.54**. Not significant. Drop the prereg's contamination clause and the same book is **+13.84%/yr, t 1.32** (§10). |
| Independent selector count | Unchanged. |
| Farm candidates tested / promoted | 0 / 0. |
| External execution drag | n/a (no orders). |
| LLM spend | **$0.00.** No model was called; this is entirely numerical. |
| **RESULT IMPROVEMENT** | **NONE in return terms.** What moved is the *description* of the incumbent overlay, which was wrong in three places. |

---

## 1 · What was asked, and the four-way answer

> Is BAND_PRIOR v2 (a) an exclusion rule, (b) a 12-month expected-return prior,
> (c) a beta/size exposure, or (d) a genuine 1-month selector?

**(a) EXCLUSION — yes, and it is the only part that survives multiplicity.**
BH-FDR at q=0.05 over the 32-test screen family returns **eight survivors and
they are all `toxic_ge_5`** — every horizon, both universes. The 3-5 band
survives at no horizon. Holm on the export family (the eight 3-5 claims)
returns **zero survivors**.

**(b) A 12-MONTH OBJECT ON A 21-SESSION CLOCK — NO. Refuted, and the evidence
that suggested it was an artefact.** The money runs the *other* way:

| horizon | 3-5 band excess vs VW | t_block | n_eff | beta-neutral | prior IC | t_naive | t_block | n_eff |
|---|---|---|---|---|---|---|---|---|
| 1m | **+18.93%/yr** | 1.647 | 130 | +13.82 | 0.0642 | 14.63 | **14.63** | 143 |
| 3m | +10.39 | 0.908 | 42 | +7.13 | 0.0937 | 22.97 | **13.95** | 47 |
| 6m | +5.55 | 0.532 | 20 | +1.93 | 0.1228 | 33.11 | **13.84** | 23 |
| 12m | +7.30 | 0.647 | 9 | +4.29 | 0.1638 | 44.17 | **13.58** | 11 |

Two things happen at once and they were being read as one. The IC **level**
does rise with horizon (0.064 → 0.164). The IC **evidence** does not: the naive
t climbs 14.6 → 44.2 purely because a 12-month return sampled monthly is
counted 12 times, and once `n_effective` counts DATE BLOCKS the t is flat at
~13.6-14.6. The learner's headline `t_stat: 34.518` on `months: 96` is that
same statistic with n=96 where the honest n is **8**.

And the IC level's rise is *sub-√h*: a 12-month object sampled monthly would
show `IC_12m ≈ √12 × IC_1m = 0.222`; observed is **0.164**. The per-month
information **decays** with horizon. In money the decay is unambiguous:
+18.93 → +10.39 → +5.55 → +7.30 pp/yr. **The one-month clock is the best clock
this overlay has**, which is the opposite of what the horizon-IC curve was
being read to say.

**(c) BETA / SIZE — NO, and this was the honest prior going in.**
`PREREG_BAND_IS_BETA_1` recorded *"I expect the hypothesis to be SUPPORTED"*
with three independent readings pointing that way. It is not supported.

* Mean pre-period beta of the 3-5 book is **1.27** (whole panel ≈1.07), so the
  tilt is real but modest — nothing like the live book's 2.10 on 2026-09-01.
* The beta leg is **+4.54 pp/yr of the +18.93** (24% of the excess). That is
  above the prereg's qualitative "at least a sixth" and **below** its declared
  6 pp/yr decision threshold. The rule does not fire.
* The required matched control — the comparison the design would not have
  chosen — settles it. A basket from *outside* the region (ratio < 1.5) matched
  on **beta decile × cap decile × month**, mean beta **1.25**, 5.1% of admitted
  names unmatched, earns **+1.02%/yr, t 0.23** at 1m (+0.86 / +2.22 / +3.41 at
  3/6/12m). Same beta, same size, same months, none of the return.
  **The ratio screen is not decoration on a beta sort.**

**(d) A GENUINE 1-MONTH SELECTOR — NOT PROVEN, AND NOT DISPROVEN.**
+18.93%/yr gross, +17.65 net at 10bps, +15.75 net at 25bps, terminal 17.06×
against the market's 6.63× — and **t_block 1.647, p 0.102**, which clears
neither the trial's bar nor Holm. This is the same verdict the 3-5 band has
always had, restated at the correct benchmark: **a large point estimate that
has never been separated from zero.**

---

## 2 · Both of `PREREG_BAND_IS_BETA_1`'s declared rules failed to fire

Stated plainly because "unresolved" is a result and must not be dressed up.

| declared rule | threshold | observed (1m, the traded clock) | fires? |
|---|---|---|---|
| beta leg ≥ 6 pp/yr ⇒ "OPPORTUNITY SET + LEVERAGE TILT", beta budget becomes a required field | 6.00 pp | **4.54 pp** | **no** |
| neutralised excess > 10 pp/yr **and** t ≥ 2 ⇒ hypothesis REFUTED, the band is selection | 10 pp & t 2 | **13.82 pp** but **t 1.23** | **no** |

The neutralised excess is comfortably over the 10 pp bar and misses entirely on
the t. So the trial's verdict is **UNRESOLVED AT THE DECLARED THRESHOLDS**, and
the prereg said in advance this could happen: it declared its headroom "thin"
(n_required ≈ 152 monthly observations, ≈228 available) and stated it "can
resolve a 6pp per year beta leg and cannot resolve a 3pp one". The beta leg is
4.54 pp. **The design landed inside its own blind spot**, which is a power
outcome, not a data outcome, and no amount of re-slicing fixes it.

What *is* resolved, because it did not depend on that threshold: the matched
control (§1c). The prereg required it "whether or not the primary result is
interesting", and it is the only leg of this trial that returns a clean answer.

---

## 3 · The benchmark finding — the +16.55% is not an excess over the market

This cost three attempts to reproduce and it changes how every downstream
document should read the number.

`scripts/tracker_ibes_backtest.py:564` sets
`market = lab.groupby("month")["fwd_1m"].mean()` — the benchmark is the
**equal-weighted mean of the analyst-covered panel itself** (~3,060 names per month with
both a target and a rating). It is neither the VW market nor the CRSP EW
market. Two further specifics: band membership is measured on rows *without* a
split in the prior year (S30b), while the benchmark leg includes them; and the
annualisation is **linear (×12)**, not compounded.

Run that exact recipe and the constants come back:

| band | reproduced (linear, gross) | published | t |
|---|---|---|---|
| `lt_1_5` | +2.36%/yr | +2.41 | 1.24 |
| `b_1_5_3` | +6.62 | +5.74 | 2.15 |
| `b_3_5` | **+15.86** | **+16.55** | 2.03 |
| `toxic_ge_5` | −39.34 | −37.77 | −7.89 |

Residual is the published series' cost netting (which lifts the toxic band and
lowers the others — exactly the observed sign pattern) plus a 0.9% panel
difference from the learner's maturity guard. **The pipeline is pinned.**

Now change only the benchmark, same book, same months:

| benchmark | 3-5 band, 1m | t_block |
|---|---|---|
| analyst-covered panel EW (**the incumbent's**) | +20.92%/yr | **2.254** |
| CRSP equal-weighted | +19.34 | 2.104 |
| **CRSP value-weighted (prereg-frozen, primary)** | **+18.93** | **1.647** |

The point estimate barely moves; **the t does**, and it crosses 2 in exactly
one direction — the one where the benchmark is a covered-universe average
rather than the market. Every document that reports "+16.55%/yr, t 2.20" is
quoting a number that is true of that benchmark and is not a market excess.
This is the same shape as [[feedback-a-benchmark-relative-number-in-an-absolute-structure]]:
print the raw line beside the excess line and say which one the trade earns.

The raw line, printed: the 3-5 book earned **+43.44%/yr** at 1m while the VW
market earned **+20.93%/yr** over the same months.

---

## 4 · Cost, turnover, wealth and drawdown — the numbers a sizing decision needs

Costs are never omitted. `zero_cost_diagnostic: false` on every row.

| horizon | Σ\|Δw\| per rebalance (median) | gross excess | net 10bps | net 25bps | terminal net10 | market | max DD | market DD |
|---|---|---|---|---|---|---|---|---|
| 1m | 0.909 | +18.93 | **+17.65** | +15.75 | **17.06×** | 6.63× | **−47.5%** | −33.3% |
| 3m | 1.347 | +10.39 | +9.82 | +8.97 | 6.97× | 4.50× | −50.7% | −20.8% |
| 6m | 1.541 | +5.55 | +5.23 | +4.76 | 3.71× | 3.94× | −49.3% | −19.1% |
| 12m | 1.687 | +7.30 | +7.13 | +6.88 | 3.67× | 3.35× | −41.7% | −14.0% |

Turnover at the 1-month clock is ~45% one-way per month → ~1.1%/yr at 10bps,
so **costs are not what kills this book**. Two things in this table matter more
than the returns:

1. **At 6 months the book loses to buy-and-hold** (3.71× net vs 3.94×) while
   still carrying a −49% drawdown. Terminal wealth, not the mean, is the
   ranking criterion (S18), and at 6m it ranks the book *below* the market.
2. **The drawdown is 1.4× to 2.9× the market's at every horizon.** A 1.27 beta
   does not explain a −47.5% drawdown against −33.3%; the residual is
   idiosyncratic small-name risk. Any sizing conversation about this overlay
   starts here, not at the +18.93.

---

## 5 · Era splits and leave-one-year-out — the band is dead in the current era

| era | 3-5 excess vs VW (1m) | t_block | beta-neutral |
|---|---|---|---|
| 2013-2019 | +20.55%/yr | 1.505 | +13.75 |
| 2020-2021 | +41.91 | 1.020 | +46.07 |
| **2022-2024** | **+2.32** | **0.122** | **−4.25** |

By year (1m, excess vs VW): 2013 +40.4 · 2014 −1.7 · 2015 **−28.3** · 2016
**+93.1** · 2017 +35.4 · 2018 +0.0 · 2019 +25.7 · 2020 **+119.2** · 2021 −9.6 ·
2022 +8.3 · 2023 −1.4 · 2024 +0.2.

Leave-one-year-out is the one piece of good news: no single year carries the
result. Dropping 2020 leaves **+11.56%/yr (t 1.05)**; dropping 2016 leaves
**+13.09 (t 1.18)**; every other year leaves 17-24%. So this is not a
one-year artefact — but it *is* a two-regime object, and the regime it is
currently in has produced **+2.3%/yr with a negative beta-neutral leg over
three years**. The live books trade it today.

At 6m and 12m the 2022-2024 era is negative outright (−3.4%, −5.3%).

---

## 6 · The ordering arena — `PREREG_RANK_VS_EXPRETURN_1` resolves NO-DIFFERENCE

Three arms, identical admitted set (ratio 1.5-5, hygiene), top-50
value-weighted, monthly, 143 months, seeded `default_rng(20260904)`:

| arm | annualised excess vs VW | t_block | terminal wealth |
|---|---|---|---|
| score order (ratio × consensus) | +3.72% | 0.483 | 5.88× |
| expectation order (sealed prior field) | −0.98% | −0.114 | 2.94× |
| **random order** (100 draws/month) | −0.87% | −0.166 | **4.21×** |
| **VW market** | — | — | **6.75×** |

Paired score − expectation: **+4.74%/yr, t_block 0.833** → the declared rule
("t ≥ 2 AND higher terminal wealth AND above the cost of the differing slots")
does not fire. **Recorded verdict: NO-DIFFERENCE.** Both orderings are kept and
the open question is closed as answered, exactly as the prereg specified.

The prereg's honest prior — *"NO DIFFERENCE, and the reason is measured"* —
holds. Two details it did not anticipate, both worth keeping:

* **Random (4.21×) beats the sealed expectation ordering (2.94×).** The
  expectation field is not merely uninformative as a ranker; over this window
  it ranked *worse than a coin*. The mean rank correlation between the two
  orderings is only 0.51 and mean slot overlap 0.58, so they genuinely disagree
  on ~21 of 50 slots every month and the disagreement is not paying.
* **All three arms lose to buy-and-hold VW.** A top-50 value-weighted book
  drawn from the admitted region under-performs the market on terminal wealth
  under every ordering tested, including the best one. The admitted set is not
  the entire product — it is a *negative* product at k=50 VW. (It is not
  negative equal-weighted across all names; see §1. Concentration and weighting
  are doing the damage, consistent with S18's "concentration is a
  negative-return decision".)

`degenerate_months_expectation_constant: 0` — the expectation field took more
than one value inside the admitted set in every month, so this comparison never
degenerated into score-versus-random.

---

## 7 · A correction to the session index

MEMORY S35 records *"within the 3-5 band the prior ranks BACKWARDS (IC −0.022,
t −2.93)"*. The learner receipt's own key for that number is
`by_band → ADMISSIBLE_REGION_ratio_1_5_to_5`. It is the **whole admissible
region (ratio 1.5-5)**, not the 3-5 band. Reproduced here on the full 143
months: admissible-region ratio IC **−0.0264, t −2.82**; inside the 3-5 band
specifically **+0.0120, t 0.74**.

The distinction is load-bearing. "The ratio ranks backwards inside 1.5-5" is a
statement about the **1.5-3 vs 3-5 boundary being the wrong way round in the
ordering** while the *band means* run the right way. "The ratio ranks backwards
inside 3-5" would have been an argument for reversing the sort inside the top
band, and there is no evidence for that (t 0.74). Nothing was built on the
mis-labelled version; the cheap fix is this paragraph.

---

## 8 · What was NOT run, and why that is a decision

`PREREG_BIAS_CORRECTED_BAND_1` was read and **not executed**. It needs a
per-contributor optimism panel built from `tr_ibes.ptgdetu` (4,658,468
analyst-level targets, 1,348 brokers, 33,043 analysts) with a 20-resolved-forecast
floor per contributor and three years of burn-in before the first scored month.
That is a separate build, and running half of it would produce a number its own
prereg would not accept. Declared here so the absence is a decision and not an
omission.

Its primary falsifier is cheap to check first when it *is* run — "fewer than
five per cent of admissible name-months change band" ends the ordering claim
before any return is computed.

---

## 9 · Scope — what this does and does not settle

Written scope-aware on purpose, because a negative at one horizon does not
refute another.

**Settled by this run:**
* the toxic band's exclusion value, at all four horizons, surviving BH-FDR (the
  only thing that does);
* that the 3-5 band is not a beta-decile × cap-decile effect (matched control);
* that the horizon-IC curve does not license a 12-month instrument;
* that the two orderings inside the admitted set are indistinguishable, and
  that the sealed expectation field is beaten by random;
* that the +16.55 headline is a covered-panel excess, not a market excess.

**NOT settled, and not claimed either way:**
* whether the 3-5 band carries alpha at all. Every horizon's t is inside noise
  against VW. **This is under-powered, not negative** — at the observed
  monthly dispersion (se 0.884%/month) the minimum detectable effect at t 2 is
  **+23.4 pp/yr**, and the point estimate is +18.9. The design cannot see its
  own best case.
* whether the *live* book's beta of 2.10 (2026-09-01) is a property of the band
  or of that book's construction. This trial measures the **band**, whose beta
  is 1.27. The gap between 1.27 and 2.10 is a construction question — k, weights,
  the liquidity floor — and is not answered here.
* whether a bias-corrected consensus moves names across the boundary (§8).
* anything about horizons beyond 12 months, or about a hold-to-target exit
  rule. Only fixed-horizon rebalancing was tested.

**The one thing a reader should not take away:** that the band was disproven.
It was re-benchmarked, matched-controlled, and found under-powered. Those are
three different findings and none of them is "MECHANISM_REJECTED".

---

## 10 · Method notes that would otherwise have to be re-derived

* **Beta**: OLS of daily return on the daily VW market over the 120 sessions
  ending at the last session **strictly before** `entry_date`, ≥60 usable
  sessions, winsorised at the pooled 1st/99th percentile of daily return
  (−9.80% / +11.18%). `rf = 0`, declared — it cancels from a daily slope.
  Coverage 99.13% of panel rows.
* **The contamination clause is not free, and it is more binding on a small
  band.** The prereg's rule — >5% of a month's admitted names lacking a beta ⇒
  month excluded from BOTH arms — removes **0 months from `lt_1_5` and 13 from
  `b_3_5`**, because on a ~30-name band *two* missing betas is 6.7%. Almost all
  13 are 2013-2014, where the beta panel's own 120-session warm-up bites. It is
  declared in advance so it stays primary, but it moves the headline and the
  without-clause number is therefore printed beside it
  (`contamination_clause_sensitivity_b_3_5`):

  | horizon | with clause (primary) | without clause |
  |---|---|---|
  | 1m | +18.93%/yr, t 1.647, 130 mo | **+13.84%/yr, t 1.321, 143 mo** |
  | 3m | +10.39, t 0.908 | +6.59, t 0.623 |
  | 6m | +5.55, t 0.532 | +4.11, t 0.415 |
  | 12m | +7.30, t 0.647 | +5.73, t 0.554 |

  The horizon shape — money highest at 1m, decaying out — is unchanged. The
  *level* is 5pp lower and the t is lower at every horizon, so nothing in §1's
  verdict flips, and the honest headline range for the 3-5 band's 1-month
  excess over the VW market is **+13.8% to +18.9%/yr, t 1.3 to 1.6**.
* **The decomposition is exact**, not a regression:
  `excess_vw = (β_pre − 1)·mkt_vw + resid`, per name, per month.
* **`t_block`** is the non-overlapping-block t averaged over the h phase
  offsets; `n_effective` is the block count. The naive t is printed only so
  nobody re-derives it and believes it.
* **Terminal wealth** is computed on single-phase non-overlapping chains — a
  strategy someone could actually have run — with the median over the h phases
  reported and the min/max stored.
* **Turnover** compares a cohort against the cohort it replaces with the old
  weights *drifted* by their realised holding-period return; `Σ|Δw|` already
  counts the sell leg and the buy leg, so one multiplication by bps-per-side is
  the whole round trip.
* **No result here groups, neutralises or matches on `sector`.** Stated
  because a cross-agent finding the same day showed the panel's sector column is
  contaminated: CRSP SIC 9000-9999 is **98.8% code 9999 = NONCLASSIFIABLE**, and
  `tracker_ibes_backtest.SIC_DIVISIONS` labels that whole range *"Public
  Administration"*, so ~99,334 of 441,278 rows (**22.5%**) carry a sector label
  that means UNKNOWN. The matched control matches on **beta decile × cap decile
  × month** and nothing else — the prereg names those three and no industry leg.
  If a sector leg is ever added to this design, the 9999 block must be its own
  honest UNCLASSIFIED bucket and never folded into Public Administration.
* **Primary universe** excludes `split_prior_year` rows (S30b: a stale target
  across a split is not an opinion). The entire sweep is repeated with them
  kept as `sensitivity_splits_kept` — the 3-5 band's 1m headline falls from
  +18.93 to +13.03, so this is a 6pp choice and is declared rather than
  assumed.
