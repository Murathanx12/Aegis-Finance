# HYPOTHESES 2026-09-02 — the harvest

**Status: HYPOTHESIS GENERATION ONLY.** Nothing here is pre-registered except
the three drafts named in §3, nothing is traded, no lane is seeded, no order was
placed. Licence sought per item; the default is `PRODUCT_EXPERIMENT`.

**Method.** Every receipt produced 2026-08-30 → 2026-09-02 was read and mined for
observations that are (a) surprising, (b) *precursor-bearing* — something is
observable **before** the outcome, and (c) killable. House rules applied
throughout: intuition GENERATES, data ADJUDICATES; every intuition owes the
question *what observation separates this from ordinary factor beta*; study
losers as hard as winners; **a hypothesis without a falsifier is not a hypothesis
yet**; and `n_effective` counts DATE BLOCKS.

**Sources mined (every number below traces to one of these):**

| Receipt / doc | What it contributed |
|---|---|
| `tracker_backtest/exp_return_cross_section.json` | band constants, the 2×2 disagreement, within-region Fama-MacBeth (all six \|t\|<1.5), by-year excess |
| `tracker_backtest/analyst_target_grades.json` (+ `.parquet`, 1.33m rows) | bias persists ρ 0.376, accuracy does not ρ 0.087, pooled IC 0.029 |
| `tracker_backtest/time_machine_arena.json` | era scoreboard, the **8,679** AEGIS-avoid/street-buy cells, AXSM 2018-12 |
| `tracker_backtest/topn_concentration.json` | TOP-n regime-conditional; TOP1 **0.874×** the market over 1993-2024 |
| `tracker_backtest/holder_fingerprint_summary.json` | 372,831 fingerprints, 12,311 managers, 115 quarters |
| `tracker_backtest/holder_h2_h3.json` | 23.3m events; H2 t 2.24 / 5bps; H3 NULL; anomaly ADVERSE; **the EW/VW sign flip** |
| `tracker_backtest/month_retro_20260902.json` + `docs/RETRO_2026-09-02_...` | selector dissent, β 2.10, 127/127 admission failure |
| `docs/CASE_2026-09-02_GPRO_HOLDER_ATTENTION.md` | the `IN` enum, filing lag, the seven-session unpriced window, the six-case base rate |
| terminal `state/scenario_lab/latest_summary.json` | 9 L2 LLM-disagreement leads + 2 L1 engine findings |
| terminal `state/decomposition/2026-09-01.json` | β 2.10, `mean_market_share_of_move` 1.49 |
| terminal `docs/HANDOFF.md` SESSION 34 | what is already adopted, so a "new" idea is not a re-label |

**Corpse check run before writing** (`brain_query` ×6). Two live corpses bear on
this harvest and are named where they bite: **REVISION-FORECASTER-1** (closed the
revision-mediated route) and **TEACHER-LIBRARY-1 / COPY-LAB** (owns 13D/13G copy
lanes). Neither closes the specific instruments proposed below, but H9 in
particular sits close enough to REVISION-FORECASTER-1 that a corpse hit is the
expected outcome and would itself be the answer.

---

## §0 — The five observations this harvest is built on

Stated first because every hypothesis below is a way of attacking one of them.

1. **The engine beats the street by EXCLUSION, not selection.** Over 2015-2024
   `AEGIS_avoid_toxic` is **−35.81%/yr at 12m, t −26.1** on 167 names/month,
   while `AEGIS_admissible` is **+2.32%/yr, t 2.02** on 422. The thing we can
   measure with certainty is what NOT to own. We only run long books.
2. **Inside the admitted region nothing works.** All six within-region
   Fama-MacBeth features over 143 months come back \|t\| < 1.5 (upside 1.357,
   ret_12m 1.46, consensus 0.122, drawdown 0.15, log_coverage −1.06,
   log_dollar_vol −0.004). The band prior's entire content is the **boundary**,
   not the ordering inside it.
3. **The band 3-5 book's +16.55%/yr is carried by three years.** By-year:
   2013 +31.2 · 2014 **−5.8** · 2015 **−16.2** · 2016 +43.8 · 2017 +24.4 ·
   2018 **−5.4** · 2019 +39.6 · 2020 **+61.7** · 2021 +1.7 · 2022 +7.1 ·
   2023 +20.0 · 2024 **−5.4**. Four negative years, and 2016/2019/2020 carry
   the mean. 2020 is the tell.
4. **Two selectors, one book, no adjudication.** 25 of 30 hack3+hack6 holdings
   on 09-02 are names the per-name generator declined; RZLV lost −17.30% at 10%
   notional while its own row read `claims: false`, rank 576/766, failing
   `b_rating` by **0.017**. And the counter-evidence: on 09-01 hack3's six
   declined names averaged −0.55% against −3.54% for its three claimed names.
5. **Every pooled holder number sign-flips on the benchmark.** 23.3m 13F events
   at 63 sessions: **−1.74% vs EW (t −5.10)** and **+0.06% vs VW (t 0.16)**.
   The entire pooled "13F events underperform" result is a size artefact. Only
   matched differences are readable at this panel size.

---

## §1 — The candidates

Seventeen. Each carries NAME · falsifiable statement + honest prior · PRECURSOR ·
FALSIFIER · MATCHED CONTROL (the one we would not naturally choose) · POWER
SKETCH · LICENCE.

---

### H1 · TRIAL-CLAUSE-MARGIN-1 — dissent is not one thing; the clause is

**Statement.** A holding the per-name generator declined by a *near-miss on a
continuous clause* (`b_rating` 4.083 vs a 4.1 bar; `e_drawdown` 1.3pp over)
underperforms a claimed holding, while a holding declined for a *categorical
absence* (`d_catalyst` = no dated catalyst readable) does not. **Honest prior:
50/50 and probably noise** — the two graded sessions give opposite answers, and
the whole sample is n=2 date blocks.

**PRECURSOR.** `state/predictions/2026-09-0*.json` already carries, per name,
`claims`, `failed_clauses`, `clause_inputs` and `rank`. The margin —
`clause_input − threshold` — is derivable today for every clause with a numeric
bar. Nothing new is collected; this is a join, exactly as retro E1 is.
The 09-01 failed-clause histogram is already `{e_drawdown: 2, d_catalyst: 5}`
for hack3 and `{b_rating: 1, e_drawdown: 1}` for hack4's RZLV.

**FALSIFIER.** After 60 graded overlapping days, the paired excess of
near-miss-declined vs categorically-declined holdings is inside the round-trip
spread. Then dissent is one thing after all and E1's uniform haircut is right.

**MATCHED CONTROL.** Not "claimed vs declined" — that is E1. The control we
would not choose: **claimed holdings whose winning clause also passed by a
near-miss margin.** If a 4.11 rating behaves like a 4.083 rating, the *bar* is
the artefact and neither side of the dissent is informative.

**POWER SKETCH.** Effect guess 1.5pp/month paired; dispersion ~4pp/month paired
(2-4 differing slots × small-cap idiosyncratic vol); ~250 sealed days/yr but
`n_effective` = date blocks and the 21-session horizon caps it at 12/yr.
`n_required ≈ (2.8×4/1.5)² ≈ 56` months. **~4.7 years forward. Not resolvable
inside 2 years prospectively**; report-only accumulator, or run it historically
against the 2013-2024 panel by reconstructing clause margins.

**LICENCE.** `PRODUCT_EXPERIMENT` (report-only; changes nothing that trades).

---

### H2 · TRIAL-DISSENT-SIZE-HAIRCUT-1 — price the dissent (retro E1, typed)

**Statement.** Sealed holdings the generator declined earn a lower forward
return than sealed holdings it claimed, by more than the round-trip spread.
**Honest prior: unknown, genuinely.** 08-31 says yes (declined −2.69% vs claimed
+1.65%); 09-01 says no (declined −0.55% vs claimed −3.54%). Two date blocks,
two opposite verdicts.

**PRECURSOR.** The `claims` verdict is written in the same sealed JSON as the
holding, before the session opens. `month_retro_20260902.json
§2.selector_disagreement` already computes both arms for both graded days.

**FALSIFIER.** 21+ sessions with the declined arm at or above the claimed arm.
Then dissent is decoration and `34f08ca`'s "recorded, not enforced" stands
unqualified.

**MATCHED CONTROL.** Same-day, same-book, same-notional pairs only. The control
we would not choose: **days on which the two arms hold the same sector**. If the
gap is sector, not adjudication, this is a sector bet wearing an epistemics hat.

**POWER SKETCH.** As H1 (~4-5 years to t=2 forward). Already adopted as P1a in
SESSION 34, so P(changes roadmap) is *low* — it is already changing it.

**LICENCE.** `PRODUCT_EXPERIMENT`.

---

### H3 · TRIAL-ADMISSION-RANK-1 — did we rank tomorrow's movers at all?

**Statement.** Names that print an extreme move on session D+1 sit
**significantly higher than uniform** in the D tracker-file ranking, even though
none of them was admitted. **Honest prior: near-uniform, i.e. we genuinely had
no information** — 149 of 150 extreme movers had `engine.candidate = null` and
`candidates_right_way = 0` on all four autopsy days.

**PRECURSOR.** `state/tracker/2026-*.jsonl` (12,233 PIT rows and growing daily)
carries a full ordering of ~3,059 names pre-open. `state/autopsy/*.json` labels
the movers. Both already exist; this is a rank-distribution test, not a model.

**FALSIFIER.** The rank distribution of next-day extreme movers is
indistinguishable from uniform (KS, blocked by day). Then the 127/127 result is
an **information** failure, not an admission failure, and every admission-rule
fix on the roadmap is aimed at the wrong layer.

**MATCHED CONTROL.** The control we would not choose: **extreme DOWN movers**.
If we rank tomorrow's crashes as highly as tomorrow's rips, the ranking is
detecting *volatility*, not direction, and it should be sold as a risk sensor
rather than a selector.

**POWER SKETCH.** ~15-20 extreme movers per session × 250 sessions/yr, but
`n_effective` = days. A rank-mean shift of 0.05 (on a 0-1 scale) against a
within-day dispersion of 0.29 needs ~265 days ≈ **13 months**. **Resolvable
inside a year**, and partially resolvable *today* on the four archived autopsy
days as a pilot. Cheapest high-value test in this document.

**LICENCE.** `PRODUCT_EXPERIMENT`.

---

### H4 · TRIAL-RANK-VS-EXPRETURN-1 — the two orderings disagree, and only one can be right

**Statement.** Inside a fixed admitted set, ordering by the engine's
`exp_return` produces a different terminal wealth from ordering by
`upside × consensus` rank, and the difference is not zero. **Honest prior: the
rank wins on ordering and `exp_return` wins on nothing** — under BAND_PRIOR v2
`exp_return` takes exactly **four** band constants while `rank` takes 766
distinct values, so the two disagree by construction, and S33 measured the
coherence floor emitting one value (−0.011550) across 379 of 766 names.

**PRECURSOR.** Both fields are sealed side by side in
`state/predictions/<day>.json` before the open, and the historical analogue is
`exp_return_cross_section.json`'s admissible region (54,177 name-months, 143
months) where both orderings can be reconstructed.

**FALSIFIER.** Paired monthly excess of rank-ordered vs exp_return-ordered
top-50 books, over the same admitted set, is inside noise. Then the question
that has been open since S31 ("the next seal must resolve rank-vs-exp_return")
is answered NO-DIFFERENCE and both can be kept.

**MATCHED CONTROL.** Same admitted set, same k, same weights, same day — the
pair IS the design. The control we would not choose: **a random ordering of the
same admitted set.** If random matches both, the admitted set is the whole
signal and *all* our ranking work is theatre. Given §0.2 this is the outcome to
bet on.

**POWER SKETCH.** Monthly, 2013-2024 = 144 months; paired dispersion ~2.0pp/mo;
effect worth acting on 0.5pp/mo (6pp/yr) ⇒ `n_required ≈ 125`. **Resolvable on
the panel we hold.** Forward it is report-only: at 1.2pp/day paired dispersion
the daily version needs ~4,500 sessions.

**LICENCE.** `PRODUCT_EXPERIMENT`. **PREREG DRAFTED — §3.3.**

---

### H5 · TRIAL-BAND-IS-BETA-1 — the month's best decision may be leverage *(self-attack)*

**Statement.** BAND_PRIOR v2's admitted set carries a mean market beta
materially above 1, and **at least 6pp/yr of the band 3-5 book's +16.55%/yr is
the beta leg, not alpha**. **Honest prior: I expect this to be TRUE.** Three
independent pieces of evidence point the same way — the live book's mean
β **2.10** with `mean_market_share_of_move = 1.49`; the band's best year being
**2020 (+61.7%)**, the single largest beta-recovery year in the sample; and the
band's own construction (high target/price ratio + drawn-down + small = high
beta by selection).

**PRECURSOR.** Beta is estimable from a trailing 120-session fit **before** the
month starts — `move_decomposition.py` already does it live, and CRSP
1993-2024 supports it historically. Nothing about this is hindsight.

**FALSIFIER.** After neutralising the market leg at each name's pre-period beta,
the band 3-5 excess stays above +10pp/yr with t ≥ 2. Then the band is alpha and
the beta reading is wrong.

**MATCHED CONTROL.** The control we would not choose: **a beta-matched basket
drawn from OUTSIDE the band** — same beta decile, same size decile, same month,
ratio < 1.5. If it earns the same, the band is a beta sort with an analyst
target painted on it.

**POWER SKETCH.** Paired (band book minus its own beta-neutralised twin), so the
dispersion is the beta leg's own: ≈ 2.2pp/month. Effect worth acting on
0.5pp/mo = 6pp/yr ⇒ `n_required ≈ 152`. Available: IBES targets + CRSP support
2005-2024 ⇒ ~228 months. **Resolvable now, headroom 1.5×.**

**LICENCE.** `PRODUCT_EXPERIMENT` for the paper consequence;
would need `RESEARCH_CLAIM` gates to publish "the band is alpha".
**PREREG DRAFTED — §3.1.**

---

### H6 · TRIAL-BAND-YEAR-STATIONARITY-1 — four constants fitted once, applied every day *(self-attack)*

**Statement.** The four band constants (<1.5 +2.41% · 1.5-3 +5.74% ·
3-5 +16.55% · ≥5 −37.77%) are **not stationary across the years they were fitted
on**, and the 3-5 constant in particular is a three-year artefact. **Honest
prior: TRUE for the 3-5 band, FALSE for the ≥5 band.** The toxic band is
negative in **12 of 12** years (worst −75.7% in 2021, best −9.4% in 2020) — that
is a law. The 3-5 band is negative in **4 of 12** and its mean is carried by
2016/2019/2020.

**PRECURSOR.** Purely a re-read: `exp_return_cross_section.json`
`annualised_excess_by_year` is already on disk for all nine books. The forward
version is the constant's own out-of-sample year.

**FALSIFIER.** A rolling-origin refit (fit on years ≤ Y, apply in Y+1) produces
band constants whose *sign* is stable and whose magnitude varies by less than
half. Then "in-sample thresholds" is a caveat, not a defect.

**MATCHED CONTROL.** The control we would not choose: **the ≥5 toxic band run
through the identical rolling refit.** If toxic is stable and 3-5 is not, then
the honest product is *the exclusion*, not the inclusion — which is exactly
what §0.1 already says and what we are not building.

**POWER SKETCH.** 12 annual blocks. A sign-stability test on 12 blocks resolves
today; a *magnitude* claim on 12 blocks does not and never will. **Answer
available this week; it will be a qualitative verdict, not a t-statistic.**
Cheapest test in the harvest and it bears directly on the month's headline
decision.

**LICENCE.** `PRODUCT_EXPERIMENT` (REANALYSIS of a receipt we own).

---

### H7 · TRIAL-EXCLUSION-SHORT-1 — sell the thing we can actually predict

**Statement.** The `engine_toxic AND analyst_no` cell (**−43.36%/yr, t −9.21**,
92 names/month, terminal wealth **0.010×** over 143 months) survives as a
tradeable SHORT after borrow, hard-to-borrow exclusion and the small-cap
round-trip spread. **Honest prior: FALSE — borrow eats it.** These are sub-$5,
high-ratio, heavily-shorted microcaps; that is precisely the population where
borrow runs 10-100%/yr and the names are often unshortable. But the effect is
**−43%/yr**, which is a very large number to leave unexamined.

**PRECURSOR.** Band membership (`target/price ≥ 5`) and consensus rating are
both known at month-end from IBES/Finnhub. Shortability and borrow are
observable at decision time from the venue (`shortable` is already a field in
`state/company_state/*.jsonl`).

**FALSIFIER.** Net of a measured borrow rate and the quoted round-trip, the cell
returns ≤ 0 excess; or the shortable subset is < 20% of the cell. Either kills
the book. (Both are likely.)

**MATCHED CONTROL.** The control we would not choose: **the same names held
LONG in the one year the band was least toxic (2020, −9.4%)**. A short book that
loses 60% in a single reflation year is a ruin path regardless of its mean.

**POWER SKETCH.** 92 names/month, 143 months, effect −43pp/yr with monthly
dispersion ~13pp ⇒ the *gross* result is already resolved at t −9.21. The open
question is entirely the **cost rate**, which is measured, not estimated.
**Resolvable in weeks** — and the answer is probably "unshortable".

**LICENCE.** `PRODUCT_EXPERIMENT` for a paper short book; the borrow measurement
is prerequisite and is a data task, not an experiment.

---

### H8 · TRIAL-BIAS-CORRECTED-BAND-1 — correct the target before you band it

**Statement.** Replacing the raw consensus target with a **per-analyst
bias-corrected** target moves a material fraction of names across the 1.5 / 3 /
5 band boundaries, and the re-banded book beats the raw-banded book.
**Honest prior: a real but modest improvement, most of it in the toxic
boundary.** Bias persists across an analyst's own halves at ρ **0.376**
(decile 1 −2.8pp → decile 10 **+80.3pp**) while accuracy does not (ρ 0.087) —
so bias-correction is the only per-analyst adjustment the data supports. And the
counter-evidence, stated up front: the arena's `SKILL_STREET_top_quintile` is
**−3.56%/yr (t −4.01)** against plain `STREET_target_top_quintile` at
**−10.45%/yr** — skill-weighting improved a bad signal by ~6.9pp/yr and left it
negative. So the expected mechanism is **re-classification across a boundary**,
not a better ranking.

**PRECURSOR.** `wrds/analyst_target_grades.parquet` — 1,333,683 graded targets,
5,365 gradeable analysts, `amaskcd` following a person across firms. The bias
estimate must be **expanding-window PIT** (an analyst's bias through month M−1
only), which the panel supports because every row is dated.

**FALSIFIER.** Fewer than 5% of admissible name-months change band under
correction; **or** the re-banded book's paired excess is inside noise; **or**
the improvement is entirely the ≥5 boundary, in which case the finding is
"bias-correction is a better toxicity filter" and the lane is renamed rather
than defended.

**MATCHED CONTROL.** The control we would not choose: **coverage-count-corrected
targets** — re-band using the same machinery but adjusting for the *number* of
analysts rather than their bias. If a naive coverage adjustment moves the same
names, the per-analyst identity was never the mechanism. (Precedent:
[[feedback-the-count-was-a-different-variable]] — Finnhub's analyst count is
1.80× IBES and that alone flipped a hack6 bucket 0 → 508.)

**POWER SKETCH.** Paired monthly books over 2008-2023 (3 years of burn-in for
the expanding bias estimate) = 192 months. Paired dispersion ~1.5pp/mo (the two
books share most names); effect worth acting on 0.4pp/mo = 4.8pp/yr ⇒
`n_required ≈ 110`. **Resolvable now, headroom ~1.75×.**

**LICENCE.** `PRODUCT_EXPERIMENT`. **PREREG DRAFTED — §3.2.**

---

### H9 · TRIAL-TARGET-VELOCITY-1 — the derivative, where the level is empty

**Statement.** Inside the admissible region, the **rate of change** of the
consensus price target over the trailing 60 days carries forward information
where the **level** does not. **Honest prior: LOW, and a corpse hit is the
expected outcome.** All six within-region level features are \|t\| < 1.5 over
143 months, and `REVISION-FORECASTER-1` already closed the revision-mediated
route. The one thing that makes this not a duplicate is the instrument:
`tr_ibes.ptgdetu` gives **4,658,468 individual analyst targets, 1,348 brokers,
33,043 analysts**, so velocity can be computed **per analyst and
bias-corrected**, which the closed trial could not do.

**PRECURSOR.** `ptgdetu` announcement dates give a PIT revision series per
name. `n_target_notes_90d` / `n_target_firms_90d` already exist in the live
corpus feature rows, so the live analogue is buildable.

**FALSIFIER.** Fama-MacBeth \|t\| < 1.5 within the admissible region across 143
months — the same bar the six level features failed. **If it fails, it joins
them and the region is declared featureless, which is itself worth writing
down.**

**MATCHED CONTROL.** The control we would not choose: **the velocity of the
*price*** over the same 60 days. If target velocity works only where price
velocity works, this is 12-1 momentum in analyst clothing — the exact bottleneck
CLAUDE.md names (99.5% of composite names carry one factor, and it is momentum).

**POWER SKETCH.** 143 months, within-region monthly cross-section ~379 names.
A per-sd coefficient of 0.005 against a monthly dispersion of 0.03 needs ~280
months. **NOT resolvable on the 2013-2024 window**; extending to 2005-2024 gives
~228 and is still short. Honest verdict: **underpowered at the effect sizes this
region produces**, which is the same reason the six level features returned
\|t\|<1.5 rather than clean zeros.

**LICENCE.** `RESEARCH_CLAIM` if ever claimed; `PRODUCT_EXPERIMENT` to build.
**Expect BLOCKED or DUPLICATE against REVISION-FORECASTER-1.**

---

### H10 · TRIAL-HOLDER-BENCHMARK-ARTEFACT-1 — kill our own only positive holder result *(self-attack)*

**Statement.** The manager-identity result (H2 of `holder_h2_h3.json`: Fama-
MacBeth β **0.0209, t 2.24**, NW t 1.99; tercile spread 0.226%/quarter t 2.38)
**does not survive re-benchmarking to value-weighted excess**, because the whole
panel's sign is set by the benchmark: pooled 63-session excess is **−1.74% vs
EW (t −5.10)** and **+0.06% vs VW (t 0.16)**. **Honest prior: the tercile spread
probably survives (it is a within-quarter difference and differences are
readable) but the level statements do not.**

**PRECURSOR.** Everything is on disk: `holder_fingerprints.parquet`,
`holder_qsnap.parquet`, `holder_events`, and CRSP for both benchmarks. This is a
re-run with the LHS swapped, not a new collection.

**FALSIFIER.** The FM β on the manager-history score keeps t ≥ 2 with VW excess
as the dependent variable **and** the tercile spread keeps t ≥ 2. Then manager
identity is real and the benchmark was never the story.

**MATCHED CONTROL.** The control we would not choose: **the same FM run on a
manager-history score computed from a SHUFFLED event history** (permute which
manager owns which prior event, within quarter). If the shuffle scores, the
0.0209 is plumbing. Canon: a null owes two tests.

**POWER SKETCH.** 111-115 quarters, already computed once. The re-run is hours
of compute on data we hold. **Resolvable this week.** But note the economics
before spending anything: the measured effect is **5.05 bps per 1sd of score**.
Even if it survives every control, it is below the round-trip cost of trading a
45-day-stale ownership signal. **Read as: the roadmap value is in *closing* this
lane, not opening it.**

**LICENCE.** `PRODUCT_EXPERIMENT` (REANALYSIS).

---

### H11 · TRIAL-HOLDER-INTENT-1 — the enum, not the form number

**Statement.** `typeOfReportingPerson` (`IN` = natural person vs
`HC`/`IA`/`FI`/`CO`) carries more forward information than the 13F
position-change grain, and more than the 13D-vs-13G form distinction that our
own `ACTIVIST_13D` lane is built on. **Honest prior: the `IN` cut is real and
tiny; the form-number cut is real and already priced** (Brav-Jiang-Partnoy-
Thomas: professional activist 13D ≈ +5-7% announcement, no reversal;
institutional 13G ≈ 0).

**PRECURSOR.** Structured `primary_doc.xml` on every post-2024 13D/G, and a
mechanical cover-page parse for the 1994-2024 era. Free, PIT by filing date.
The GPRO filing proved the fields parse: `IN`, Rule 13d-1(c), `classPercent`
8.5, event date 2026-07-13, filed 2026-08-20.

**FALSIFIER.** `IN`-filer events matched to institutional events on the same
name-quarter, same drawdown decile, same cap decile, same short-interest tercile
show indistinguishable t+5 → t+26 returns. (This is the GPRO case's own F1.)

**MATCHED CONTROL.** The control we would not choose — and it is the *better*
hypothesis: **ALL `IN` filers, unfiltered by fame or by distress** (the case
file's Control D). If ordinary unknown individuals do just as well, the
mechanism is not celebrity reach, it is *insider-adjacent individual
accumulation is unpriced*, which is a bigger and cleaner claim.

**POWER SKETCH.** Unknown until the EDGAR sweep counts the population — and the
case file already warns the *famous* subpopulation is **two filings in fourteen
years**, which is `NOT_ANSWERABLE_AT_N`. The Control-D population is orders of
magnitude larger. **Count first, mean-masked, before designing anything.**

**LICENCE.** `PRODUCT_EXPERIMENT`. **Blocked on a live defect first:**
`ACTIVIST_13D` has recorded `events_considered: 0` for its entire life with
`ineligible_reasons = {}` — never presented, not refused. Fix the adapter before
any 13D/G hypothesis is graded on it.

---

### H12 · TRIAL-CO-ENTRY-SPECIALIST-1 — one specialist is noise, three is a fact

**Statement.** The informative holder event is not any single filer's action but
the **co-entry of ≥3 concentrated specialists** (low `sector_entropy_nats`, high
`pct_of_portfolio_median`) into the same name in the same quarter. **Honest
prior: LOW.** The single-filer version has already been measured and it is
adverse: a manager's own **top-decile** stake size returns **−0.10pp vs matched
ordinary (t −0.58)**, with fraction-positive 41.6% against 43.7% for ordinary.

**PRECURSOR.** `holder_qsnap.parquet` + `holder_fingerprints.parquet` give, per
quarter, every filer's sector entropy, portfolio concentration and position
size, stamped from filings through q−1 only. The co-entry count is a groupby.

**FALSIFIER.** Co-entry cells matched on quarter, cap tercile and momentum show
the same forward excess as single-entry cells. **Or** — the more likely kill —
co-entry is mechanically driven by index reconstitution, which the receipt
already flags as the confound behind H3's inverted duration result.

**MATCHED CONTROL.** The control we would not choose: **co-entry by ≥3
*diversified* filers** (high sector entropy). If diversified co-entry works
equally, "specialist" is decoration and the signal is crowding.

**POWER SKETCH.** 115 quarters; `n_effective` = quarters, never events. A
0.5pp/quarter effect against ~1.7pp/quarter dispersion (the anomaly cell's own
SE scale) needs ~90 quarters. **Marginally resolvable on the panel** — but note
that 13F is **45 days stale by construction**, so even a positive result is a
research finding rather than a trade.

**LICENCE.** `PRODUCT_EXPERIMENT`.

---

### H13 · TRIAL-EXIT-VELOCITY-1 — the trade with a fuse

**Statement.** A filer's own **exit-velocity fingerprint** (`dur_p90_qtrs`,
`exit_freq`) bounds how long a follower can hold before the filer's
later-disclosed exit destroys the position; conditioning the follower's horizon
on the filer's median spell length turns a negative D252 into a positive one.
**Honest prior: LOW as stated, because the duration cut has already been
measured and it came back NULL** — the long-minus-short duration spread on
NEW_POSITION is **−0.04pp, t −0.73**, and long-duration filers' new positions
*underperform*. But that measured *entry* returns by duration tercile; this asks
a different question — **exit timing conditional on having entered** — and the
case file supplies the motivating losers: 2 of 6 individual filers fully exited,
and BBBY's filer booked ~+$59m while a holder went to −99.5% and then zero.

**PRECURSOR.** `holder_fingerprints.parquet` carries per-manager
`median_holding_duration_qtrs` (p50 = 2.0 quarters; p90 ladder to 41) and
`exit_freq` (p50 0.103), stamped PIT from filings through q−1.

**FALSIFIER.** Forward excess graded at `min(252 sessions, filer's median spell)`
is no better than at a fixed 252 sessions. Then duration is not a fuse length
and the two horizons are the same trade.

**MATCHED CONTROL.** The control we would not choose: **grade from the filer's
exit-DISCLOSURE date rather than the exit date.** The follower cannot see the
exit; he can only see the amendment 45 days later. If the advantage lives
entirely between those two dates, the mechanism is *front-running a person who
will front-run you* and it is unharvestable by construction.

**POWER SKETCH.** 115 quarters; effect guess 1pp/252 sessions against
~10.8pp dispersion (the h252 pooled SE scale) ⇒ far beyond 115 quarters.
**Not resolvable inside 2 years, and probably not resolvable at all on 13F
grain.** Its value is as a *design constraint* on H11, not as a standalone test.

**LICENCE.** `PRODUCT_EXPERIMENT` (study, not book).

---

### H14 · TRIAL-OVERNIGHT-SEAL-1 — we may be entering at exactly the wrong moment

**Statement.** The sealed book's forward edge, if any, is realised
**close-to-open** and is destroyed by the current open-entry convention
(09:30-09:45 no-share-entry guard, then market entry). **Honest prior:
STRONGLY TRUE at the market level and UNKNOWN at ours.** The house already
measured the whole-market decomposition — 164.64× overnight against 0.09×
intraday, dying above ~1.5bps of cost — and our books enter *after* the
overnight leg has happened.

**PRECURSOR.** Every tracker day file stamps the **prior** session's close, and
the venue supplies the open. So for every sealed holding on every day we already
have close→open and open→close separately, from data written before the
decision. No new collection.

**FALSIFIER.** Over 60 sealed sessions, the sealed book's close-to-open excess
is ≤ its open-to-close excess. Then entry timing is not the leak and the retro's
"admission and beta" diagnosis stands unqualified.

**MATCHED CONTROL.** The control we would not choose: **the same split on the
names the book DECLINED.** If declined names also carry their whole move
overnight, this is a property of the small-cap tape, not of our selection, and
the correct response is a cost model — not an entry change.

**POWER SKETCH.** Daily paired, dispersion ~1.5pp/day; the effect at stake is
the *whole* daily excess, so guess 0.3pp/day ⇒ `n_required ≈ 196` sessions ≈
**10 months**. Resolvable. **Caveat that decides the value: the measured
whole-market version dies above ~1.5bps, and our names are small-caps with a
median quoted round-trip far above that.** So the likely finding is "the edge is
overnight and unreachable", which is still a roadmap-changing answer because it
retires an entire class of proposed fixes.

**LICENCE.** `PRODUCT_EXPERIMENT` (shadow measurement; changes nothing on day one).

---

### H15 · TRIAL-LEADERSHIP-BREADTH-1 — a sensor, and only a sensor

**Statement.** A PIT leadership-breadth statistic (trailing 126-session ratio of
top-N value-weighted return to top-500 equal-weighted return) predicts **which of
our own books works next month**. **Honest prior: it is a regime descriptor and
will not be a rule.** `topn_concentration.json` is explicit: verdict
**REGIME-CONDITIONAL**, TOP1 is **0.874×** the market over 1993-2024, and
2000-2012 reverses every ordering (TOP1 0.427×). The concentration grid is a
*spike at n=2-3* (42.6 / 43.5) inside a flat plateau of ~26-30 from n=5 to
n=500 — a lucky draw's shape, not a mechanism's.

**PRECURSOR.** CRSP daily, month-end permco cap ranks — the exact pipeline that
built the receipt, run with a trailing window instead of a full sample.

**FALSIFIER.** Conditioning our books on the sensor produces no spread in
forward excess beyond the unconditional. **Or** the sensor's own sign flips
inside its estimation window, which on 4 eras it plausibly will.

**MATCHED CONTROL.** The control we would not choose: **the sensor computed on a
period the books were not fitted on (1993-2012)**. Our band constants come from
2013-2024, the single most concentration-favourable stretch in the sample.

**POWER SKETCH.** 383 months but `n_effective` ≈ **4 regimes**. A regime claim on
four regimes is unresolvable in principle, not just in practice. **Honest verdict:
build it as a *reported sensor* with no decision authority. Do not attempt to
resolve it.**

**LICENCE.** `PRODUCT_EXPERIMENT` (sensor only; explicitly never a gate).

---

### H16 · TRIAL-EVENT-STATE-INTERACTION-1 — the interaction, since the main effects are empty

**Statement.** A news event type's forward return is conditional on the name's
**prior state**, and the interaction carries signal where the main effects do
not: e.g. `analyst_rating` events on names with `coverage_baseline_90d` in the
bottom tercile behave differently from the same events on well-covered names.
**Honest prior: LOW, and multiplicity is the enemy.** S23 measured 7 of 29
features clearing zero on 23 hand-picked names and **0 of 29 on 152**; the
corpus is **81% SEC filings** and only **18.8% wire news** in August 2026, so
"our news coverage shows X" is a claim about EDGAR unless `kind == "news"` is
filtered.

**PRECURSOR.** `state/corpus/features/*.jsonl` already carries, per name-day:
`event_type_counts_20d` (11 types), `attention_z`, `novelty_5d`,
`source_independence`, `coverage_baseline_90d`, `n_items_{1,5,20}d`,
`drawdown_from_60d_high`, `realised_vol_20d`, plus a `derivable` map that says
which fields were actually computable. All PIT.

**FALSIFIER.** No interaction cell survives BH-FDR across the 11 × 3 grid
(canon §63: SCREEN = BH-FDR, EXPORT = Holm). And the honest pre-commitment: the
grid is declared **before** the run, all 33 cells reported, winners and losers.

**MATCHED CONTROL.** The control we would not choose: **the same grid on the
`filing` subset rather than the `news` subset.** 81% of the corpus is EDGAR; if
filings show the same interactions, the "news" framing is wrong and the signal
is disclosure cadence.

**POWER SKETCH.** 152 feature files today; the corpus spans 2025-08 → 2027-02
with **8,523 future-dated calendar rows that are not news**. Per cell the
effective n is a handful of date blocks. **Not resolvable inside 2 years on the
forward corpus.** The only route with power is the historical panel, and the
historical panel does not carry these features. **Honest verdict: DEPRIORITIZE
until the corpus has ≥ 12 months of `kind == "news"` rows across ≥ 500 names.**

**LICENCE.** `RESEARCH_CLAIM` if ever claimed. Not registrable today.

---

### H17 · TRIAL-FILING-MEDIA-LAG-1 — the market prices the story, not the filing

**Statement.** For a structured, free, public ownership filing, the harvestable
variable is the **lag between the filing date and the first media mention**, not
the filing itself. **Honest prior: the mechanism is real and the population is
too small to trade.** GPRO is the demonstration: the 13G was public and
structured on EDGAR from 2026-08-20, and over the next five sessions the stock
returned **−1.63% on 1.03× normal volume**. It took a Bloomberg newsletter on
2026-08-30 to produce **+46%**. Seven trading sessions of an unpriced, free,
machine-readable fact — closed by a media outlet, not by the filing.

**PRECURSOR.** EDGAR filing timestamp (`state/research/ownership/*.jsonl`, live
since the 09-02 watcher) **and** the first corpus mention date
(`state/corpus/observations/*.jsonl`). Both PIT, both now collected daily. The
lag is computable at t+5, which is also when the muted-reaction condition
becomes observable — no leakage.

**FALSIFIER.** Any of the case file's F1-F6. In priority order, and the first
two are the ones I expect to fire: **F2 — it is short interest** (Fischbach's
13.5m shares were **54% of GPRO's short interest**, 16.46% of float); **F3 — it
is the pending M&A catalyst** (a banker-run, publicly announced, "later stages"
sale process had been live for **102 days** before the 13G). Then the lane is
renamed `FLOAT-SHOCK-1` or retired, not defended.

**MATCHED CONTROL.** The control we would not choose: **filings that got media
coverage on day 1.** In the six-case analogue set, condition (7) (muted
reaction) vetoes A1 — GME/Cohen 2020 — which then returned **+198% at D63 and
+2,093% at D126**. The muted-reaction condition costs the single largest winner
in the visible set. It is a **bet, not a free filter**, and the sweep must run
with and without it, declared as a SCREEN cell before the run.

**POWER SKETCH.** The narrow (famous natural person, distressed small-cap)
population is **two filings in fourteen years**. `NOT_ANSWERABLE_AT_N`.
The Control-D population (all `IN` filers, any target) is orders of magnitude
larger and is the only version with power. **Count the population, mean-masked,
before writing a design.** Prospective accumulation started 2026-09-02 and is
worth continuing purely because prospective time cannot be parallelised.

**LICENCE.** `PRODUCT_EXPERIMENT` for observation; nothing may be claimed at n=1.
GPRO is the **parent and is barred from every confirmation slice**.

---

## §2 — Ranking

Scored `P(changes the roadmap) × value of the decision improved − cost`, per
CLAUDE.md's information-per-dollar rule. "Cost" is analyst-days plus compute;
every item below runs on data already on disk unless stated.

| # | Hypothesis | P(changes roadmap) | Value if true | Cost | Resolvable? | Score |
|---|---|---|---|---|---|---|
| **1** | **H5 TRIAL-BAND-IS-BETA-1** | **HIGH** | decides whether the month's headline decision is alpha or leverage | low (panel held) | yes, 1.5× headroom | **★★★★★** |
| **2** | **H6 TRIAL-BAND-YEAR-STATIONARITY-1** | **HIGH** | same target, one afternoon, qualitative verdict | **lowest in the set** | partially, today | **★★★★★** |
| **3** | **H8 TRIAL-BIAS-CORRECTED-BAND-1** | **HIGH** | a genuinely new selector from the week's strongest measured fact | medium | yes, 1.75× headroom | **★★★★☆** |
| **4** | **H4 TRIAL-RANK-VS-EXPRETURN-1** | **HIGH** | resolves an open question that governs today's 30 holdings | low | yes historically | **★★★★☆** |
| **5** | **H3 TRIAL-ADMISSION-RANK-1** | **HIGH** | decides whether the 127/127 failure is admission or information | low | yes, ~13 months | **★★★★☆** |
| 6 | H14 TRIAL-OVERNIGHT-SEAL-1 | MED-HIGH | retires a class of entry-timing fixes either way | low | ~10 months | ★★★☆☆ |
| 7 | H10 TRIAL-HOLDER-BENCHMARK-ARTEFACT-1 | MED-HIGH | *closes* a lane cheaply (5bps is below cost regardless) | low | this week | ★★★☆☆ |
| 8 | H1 TRIAL-CLAUSE-MARGIN-1 | MEDIUM | sharpens an already-adopted experiment | very low | not forward | ★★★☆☆ |
| 9 | H7 TRIAL-EXCLUSION-SHORT-1 | MEDIUM | −43%/yr is too big to leave unexamined; probably unshortable | low | weeks | ★★★☆☆ |
| 10 | H11 TRIAL-HOLDER-INTENT-1 | MEDIUM | the enum is the right cut and a live lane is starved | medium | count first | ★★☆☆☆ |
| 11 | H2 TRIAL-DISSENT-SIZE-HAIRCUT-1 | LOW (already adopted) | already P1a | very low | not forward | ★★☆☆☆ |
| 12 | H12 TRIAL-CO-ENTRY-SPECIALIST-1 | LOW | 13F is 45 days stale by construction | medium | marginal | ★★☆☆☆ |
| 13 | H17 TRIAL-FILING-MEDIA-LAG-1 | LOW now / HIGH later | prospective clock cannot be parallelised | low (observe) | not at narrow n | ★★☆☆☆ |
| 14 | H15 TRIAL-LEADERSHIP-BREADTH-1 | LOW | sensor only, never a gate | low | **no — 4 regimes** | ★☆☆☆☆ |
| 15 | H13 TRIAL-EXIT-VELOCITY-1 | LOW | a design constraint on H11, not a test | medium | **no** | ★☆☆☆☆ |
| 16 | H9 TRIAL-TARGET-VELOCITY-1 | LOW | expected corpse hit vs REVISION-FORECASTER-1 | medium | **no — underpowered** | ★☆☆☆☆ |
| 17 | H16 TRIAL-EVENT-STATE-INTERACTION-1 | LOW | corpus is 81% EDGAR; 33-cell multiplicity | high | **no, not inside 2y** | ★☆☆☆☆ |

### TOP 5

1. **H5 · TRIAL-BAND-IS-BETA-1** — is BAND_PRIOR v2 alpha or leverage?
2. **H6 · TRIAL-BAND-YEAR-STATIONARITY-1** — are the four constants stationary?
3. **H8 · TRIAL-BIAS-CORRECTED-BAND-1** — band the bias-corrected target.
4. **H4 · TRIAL-RANK-VS-EXPRETURN-1** — which of our two orderings is real?
5. **H3 · TRIAL-ADMISSION-RANK-1** — was 127/127 admission, or information?

**Why the top two are both attacks on our own best decision.** BAND_PRIOR v2 is
described in SESSION 34 as "the month's best decision", it now governs the
opportunity set of all three live books, and its evidence is **two forward
sessions plus an in-sample fit its own receipt disclaims**. The two cheapest
tests in this document both attack it, and both run on receipts already on disk.
That is the highest information-per-dollar available this week.

**Deliberately NOT proposed.** A learned router over the existing selectors —
`COMPOSITE_WEIGHTS` is momentum 1.0 + multifactor 1.0 + four 0.5s with coverage
`{"1": 206, "6": 1}`, and CLAUDE.md is explicit that a router comes *after*
several independent selectors exist, not before. Today there is arguably still
one.

---

## §3 — Pre-registration drafts (top 3)

Written to `C:\Users\mrthn\Aegis module\TRIALS\`, corpse-checked with
`python scripts/lint_prereg.py`.

| Draft | File (in `C:\Users\mrthn\Aegis module`) | Linter verdict |
|---|---|---|
| TRIAL-BAND-IS-BETA-1 | `TRIALS/PREREG_BAND_IS_BETA_1.md` | **PASS** |
| TRIAL-BIAS-CORRECTED-BAND-1 | `TRIALS/PREREG_BIAS_CORRECTED_BAND_1.md` | **PASS** |
| TRIAL-RANK-VS-EXPRETURN-1 | `TRIALS/PREREG_RANK_VS_EXPRETURN_1.md` | **PASS** |

A **corpse hit is a FINDING, not a failure** — it means a prior experiment
already answered the question and the roadmap should read that result instead of
paying for it again. None of the three hit one; the near-neighbour report is in
§4 and it is the more useful output.

---

## §4 — Linter verdicts, in full

Command: `cd "C:/Users/mrthn/Aegis module" && python scripts/lint_prereg.py TRIALS/<file>`

### 4.1 TRIAL-BAND-IS-BETA-1 — **PASS** (vs 354 prior experiments)

```
no close match in 148 graveyard rows, the trial registry or the prereg folder.
R13: n_required 152  n_available 228  smallest resolvable effect 0.41pp
 [near] 0.242  prereg  REGISTERED  PREREG_AGREE_CELL_TILT_1
```

Headroom 1.5x. Resolves a 6pp/yr beta leg; **cannot resolve a 3pp one**, and the
document says so in its own body.

### 4.2 TRIAL-BIAS-CORRECTED-BAND-1 — **PASS** (vs 355 prior experiments)

```
no close match in 148 graveyard rows, the trial registry or the prereg folder.
R13: n_required 110  n_available 192  smallest resolvable effect 0.3pp
 [near] 0.318  prereg  REGISTERED  PREREG_BAND_IS_BETA_1
 [near] 0.221  prereg  REGISTERED  PREREG_AGREE_CELL_TILT_1
 [near] 0.206  prereg  REGISTERED  PREREG_ANALYST_SKILL_1
```

**The near-neighbour is the useful part of this verdict.** `PREREG_ANALYST_SKILL_1`
was registered 2026-08-31 and asks whether **broker identity adds RANKING
information over the equal-weighted consensus** — a per-source *accuracy
weighting*. This trial asks whether per-analyst **optimism** shifts the target's
**LEVEL** across a band boundary. The distinction is exactly the one the
1.33m-row grading receipt forces: bias persists (rho 0.376) and accuracy does
not (rho 0.087), so the weighting question and the correction question have
different expected answers and must not be pooled.

**And there is already an interim read on the sibling that this trial must not
ignore:** the arena's `SKILL_STREET_top_quintile` earns **−3.56%/yr (t −4.01)**
against `STREET_target_top_quintile`'s **−10.45%/yr**. Skill-weighting the
street improved a bad signal by ~6.9pp/yr and left it negative. That is written
into this trial's honest prior rather than discovered afterwards.

### 4.3 TRIAL-RANK-VS-EXPRETURN-1 — **PASS** (vs 356 prior experiments)

```
no close match in 148 graveyard rows, the trial registry or the prereg folder.
R13: n_required 126  n_available 144  smallest resolvable effect 0.47pp
 [near] 0.328  prereg  REGISTERED  PREREG_BAND_IS_BETA_1
 [near] 0.309  prereg  REGISTERED  PREREG_AGREE_CELL_TILT_1
 [near] 0.286  prereg  REGISTERED  PREREG_BIAS_CORRECTED_BAND_1
```

**Headroom 1.15x — the thinnest in the batch, and it is declared as thin in the
document body.** A null from this design means "no ordering advantage of at
least 6pp/yr", never "no ordering advantage". `PREREG_N1_RANKER_VS_COMPOSITE`
(2026-08-10) did not surface as a near match: it compares a *ranker against a
composite* on a 150-name pool at an annual clock, while this compares **two
orderings of one identical admitted set**. Different instrument, different
clock, different pool.

---

## §5 — Two things this harvest deliberately does not do

- **It does not propose a learned router.** `COMPOSITE_WEIGHTS` is momentum 1.0
  plus multifactor 1.0 plus four 0.5s with coverage `{"1": 206, "6": 1}` — 99.5%
  of names carry one factor. A router comes after several independent selectors
  exist. Today there is arguably still one.
- **It does not treat a negative as an absence.** Four of the seventeen
  candidates (H9, H13, H15, H16) are declared **unresolvable inside two years**
  at the effect sizes their own populations produce. That is an answer, and
  writing it here is cheaper than discovering it in nine months dressed as a
  null.
