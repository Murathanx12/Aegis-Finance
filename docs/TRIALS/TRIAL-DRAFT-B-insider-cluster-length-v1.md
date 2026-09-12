# TRIAL-DRAFT-B — insider cluster buys by cluster length (`insider-cluster-length-v1`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-12, before any read. Not in
`rule_experiments`; `cumulative_trials` unchanged. Signing starts the clock.

**Family:** `NIGHT_JOB_BOOKS_2026_09` (four primary tests, one budget; Holm at
export — see TRIAL-DRAFT-A §0). **Licence:** `PRODUCT_EXPERIMENT`. Zero capital.

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(verdict in §7).

- **Resurrects: nothing refuted.** `NEGATIVE_RESULTS.md` §46/N1 measured that
  the insider return does **not** accrue before disclosure on five filing days
  (event-day ρ 0.044 across names' daily returns), which LICENSES filing-date
  PIT entry rather than blocking it. The 13D/13G family stays NO CONCLUSION and
  is untouched here — a 13D is a different form, a different filer class and a
  different deadline.
- **New instrument:** cluster LENGTH, computed for the first time in this
  repository (`backend/services/book_signals.cluster_lengths`) from
  `backend/data/optimus/sec_insider/insider_events_v1.parquet` (3,127,624
  classified rows over an 11,522,229-row bulk tape, 2006q1-2026q2). Everything
  Aegis has previously done with Form-4 data treated a purchase as an event;
  nothing measured the SPAN of a multi-insider run of purchases, which is the
  entire conditioning variable.

## 1. Hypothesis

> Insider open-market purchase clusters — ≥ 2 distinct insiders (by CIK) at one
> issuer whose transaction dates form a run of consecutive trading sessions —
> **spanning 4-5 days**, entered at the **latest filing date** among the
> cluster's constituent Form-4s and held ≈ 90 trading days, beat a
> random-universe twin drawn each period from names with **any** Form-4
> open-market-purchase activity that period, over filing-month date blocks
> 2017-2024; **and** the same-day-cluster arm does not.

**Honest prior.** Kang, Kim & Wang (working paper, Nov 2018; **UNPUBLISHED — no
peer review**, flagged) on 1986-2016: 4-5-day clusters are followed by > 5%
higher BHAR(22,90) than non-cluster purchases, while **same-day clusters yield
0.72% LOWER**. Corroboration that is peer-reviewed: Alldredge & Blank (*JFR*
42(2):331-360, 2019), 1986-2014, > 2%/month abnormal return on clustered
purchases. **Decay past 2016/2014 is UNVERIFIED.** Cluster SALES are
uninformative (KKW) and are not shorted.

**The falsifier is named before the number.** The same-day arm is predicted to
LOSE to non-cluster purchases. If it wins, the length-conditioning claim is
refuted regardless of what the 4-5-day arm did, because "same-day gets priced
immediately, slow multi-day clusters do not" is the mechanism and not a
decoration on it.

## 2. The eras

| | 2006-2016 (REPORTED, never deciding) | 2017-2024 (**the decision**) | 2025-26 (REPORTED) |
|---|---|---|---|
| what it is | inside KKW's own sample; CMP classification usable from 2009 | the first genuinely post-KKW-sample slice | newer than any published sample |
| link | CRSP permno, 82-88% linked | same | **0% linked by construction** — the CRSP vintage ends 2024-12-31, a counted refusal (`REFUSED_OUTSIDE_CRSP_VINTAGE`), not a defect; graded on Alpaca bars against SPY, a declared deviation |
| blocks | 132 filing-months | **96 filing-months** | 20 filing-months |

## 3. Primary metric — the ONE deciding number

`net_bhar_22_90_vs_random_active_twin`: the mean over **filing-month date
blocks** 2017-01..2024-12 of

    (4-5-day-cluster book's net BHAR(22,90)) − (random Form-4-active twin's net BHAR(22,90))

market-adjusted against the CRSP value-weighted index through 2024, both legs
net of the declared `CostModel` (20.0 bps transaction + 5.0 bps slippage per
side — the harsher of the two cost rulers in `NEGATIVE_RESULTS.md` §25, which
measured 41.7-49.2 bps one-way by Corwin-Schultz against 11.6-13.1 bps by
Kyle-linear in exactly this micro-cap segment, a 3.4-4.2× disagreement; the
5 bps repo default is reported as an optimistic bound and never as the result).
Block t on the filing-month series, with ρ **measured on this panel** and not
inherited from N1's 0.044.

**Reported, never deciding:** the same-day-cluster diagnostic arm; the
executive-only (`insider_is_officer`) cut; the 2×2 against CMP
opportunistic/routine; the 2025-26 Alpaca-bars extension; the 10b5-1 plan
breakdown; the 1-3-day span bucket; post-floor name counts per year.

## 4. Power — §64, computed BEFORE the confirmation, and it FAILS

Receipt: `backend/data/optimus/first_books/mde_receipt.json`.

| quantity | value |
|---|---|
| median cross-sectional BHAR(22,90) sd, 2017-2024, $5 price floor | **0.257752** |
| windows measured | 64 |
| filing-month blocks 2017-2024 | 96 |
| measured lag-1 ρ | −0.0270 |
| n_effective | **101.32** |
| **MDE at 80% power, α 0.05, two-sided** | **7.17% per block** |
| KKW's published gap | 5.0% |

> **THIS BOOK IS UNDERPOWERED FOR ITS OWN PRIOR.** 7.17% > 5.0%. At 96
> filing-month blocks and a 25.8% per-name BHAR dispersion, the design cannot
> confirm the published effect at 80% power. That is a **finding computed before
> the read**, exactly as canon §64 requires, and it changes what the trial is
> allowed to conclude, not whether it runs.

Consequences, frozen here:

1. A **null is not evidence of absence** on this book. A non-significant
   2017-2024 result is `CONDITIONAL`, never `FAILED_VARIANT`, unless the point
   estimate is ≤ 0 — an underpowered design that reports "no effect" is
   reporting its own sample size.
2. The **falsifier stays fully powered** and is what can close the book: the
   same-day arm beating non-cluster purchases is a sign test on a mechanism,
   not a magnitude test, and it does not need 7.17%.
3. The honest route to power is MORE BLOCKS, i.e. time, or a wider event
   definition — and a wider event definition is a **new registration**, not an
   amendment.

declared_effect_size: 7.17% mean net BHAR(22,90) of the 4-5-day-cluster book over its random Form-4-active twin per filing-month block -- which is the computed MDE itself and is ABOVE Kang-Kim-Wang's published 5.0% gap, i.e. this design is UNDERPOWERED for its own prior and says so before the read
event_frequency_per_year: 12 filing-month blocks (96 over the 2017-2024 confirm slice, n_effective 101.32 after the measured lag-1 rho of -0.0270); the underlying cluster count per year is reported on the receipt and is the tradability gate (>= 20/year to promote, < 10/year closes the book)
outcome_dispersion: 0.2578 (the measured median cross-sectional sd of 69-session buy-and-hold returns net of their cross-sectional mean, $5 price floor, 2017-2024, 64 windows)
outcome_horizon_days: 69 (the BHAR(22,90) window, in trading days)
dependence_unit: ONE FILING MONTH -- clusters filed inside one month overlap the same 69-session market path and are one observation of the mechanism, not thirty; a per-event n would be the SS41 error this gate exists to catch
cross_sectional_k: 20 (the promote gate's own floor of qualifying names per year; the realised per-block count is unknown until the cluster panel is built and the receipt's count OVERRIDES this number at signature)
cross_sectional_rho: 0.2180 (MEASURED: mean pairwise correlation of monthly name returns over 2017-2024, 250 names, 31,125 pairs, seed 20260912)
slice_purpose: CONFIRM -- 2017-2024 is the confirm slice, chosen because it is the first period after Kang-Kim-Wang's sample ends, not because of anything observed in it; 2006-2016 and 2025-26 are reported and decide nothing
selection_window_note: 2006-2016 has been read by this programme in other forms (CMP opportunistic/routine classification, TRIAL-BRAIN-003 in the `Aegis module` repo, NEGATIVE_RESULTS §46/N1's five filing days). Cluster LENGTH has been read by nobody, in any window. The confirm slice is disjoint from every window any of those looked at as a selection window
slice_securities: US issuers with an SEC Form-4 open-market purchase cluster of >= 2 distinct insider CIKs, above a $3M median dollar-volume floor and a $5 price minimum; the realised count per year is the tradability gate and is reported on the receipt
slice_period: 2017-01-01 .. 2024-12-31
information_cutoff: each cluster is entered at the LATEST `observed_at_utc` (filing date, end of day America/New_York) among its constituent Form-4s; `event_time_utc` (the transaction date) defines the cluster's shape and is never a PIT stamp
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from Kang-Kim-Wang (2018, unpublished) and Alldredge & Blank (JFR 2019). TRIAL-BRAIN-003-opportunistic-insider (first non-reject, weak-positive prior) tested the CMP routine-versus-opportunistic split, a different conditioning variable on the same tape, and is quoted as context; it did not produce cluster length and did not motivate it

## 5. Decision rule

Earliest decision date: as soon as the cluster construction is built against the
existing tape — no new data pull, no forward waiting.

- **`PRODUCT_PROMISING`** — 2017-2024 net block-mean ≥ +7.17% (the computed
  MDE), block t ≥ 2.0, sign positive, **AND** the same-day arm does not beat
  non-cluster purchases (the falsifier survives), **AND** the post-floor name
  count is ≥ 20/year.
- **`FAILED_VARIANT`** — net block-mean ≤ 0, **OR** the same-day arm
  outperforms non-cluster purchases (mechanism falsified), **OR** post-floor
  attrition leaves < 10 names/year (tradability killed it — the research note's
  own predicted most-likely death).
- **`CONDITIONAL`** — anything between, including every "positive but
  underpowered" outcome, which §4 says is the modal case.
- **Crash override** and contamination clause as in TRIAL-DRAFT-A §5.

## 6. Frozen parameters

The `Strategy` object `insider_cluster_length_v1` as
`scripts/seed_first_books.py` constructs it, hashed at the registration commit.
Also frozen, and named here because they are the bucket boundaries a later
reader would be tempted to move: `MIN_CLUSTER_INSIDERS = 2` distinct CIKs;
`FRONTIER_SPAN_DAYS = (4, 5)`; `SAME_DAY_SPAN = 0`; the run definition (gaps of
at most one SESSION, not one calendar day); the entry date = **max**
`observed_at_utc` among constituents; the 31-day eligibility window;
BHAR(22,90); the 2017-2024 confirm slice; the 20+5 bps cost model.

## 7. Corpse-check result

Run 2026-09-12 against **358 prior experiments**:

```
PASS   (n_required 101, n_available 511, smallest resolvable effect 3.2pp)
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
```

`PASS` means UNMATCHED, not novel: the linter compares wording against the
graveyard, the registry and the prereg corpus, and knows nothing about the
literature. The nearest neighbours it found are named in §0 and are quoted
there as corpses to respect, not as results that motivated this one.

`CALENDAR_DISJOINT_BY_CONSTRUCTION` is a **claim on the record**: it says no
prior fit was declared, so there is no selection window to overlap. If any
threshold, bucket boundary or universe in §6 was in fact chosen after looking
at this corpus, that declaration is false and the result is not a confirmation.

## 8. What this rule may NOT do

- No re-bucketing cluster length after seeing results. 4-5 and 0 are frozen;
  1-3 is reported and untraded.
- No shorting cluster sales. KKW finds them uninformative and a short leg is a
  new arm with its own borrow cost, which `S49`'s lesson says must be compared
  to the stop AND the borrow.
- No claiming the executive-only cut without registering it separately.
- No reading a non-significant result as evidence the mechanism is absent
  (§4.1).
- No quoting the 5 bps cost model's number as the headline.
- No use of `event_time_utc` (the transaction date) as a PIT stamp anywhere.
  It defines the cluster's shape; `observed_at_utc` defines when it is visible.

## 9. Registry

`rule_experiments` row `insider-cluster-length-v1`, **not yet written**.
