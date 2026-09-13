# TRIAL-DRAFT-H — executive option-grant opportunistic timing (`option_grant_timing_v0`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-14, **before any read**. It is not in
`rule_experiments` and has not incremented `cumulative_trials`: registration is
the attended step, and a draft that registered itself would make the attended
step decorative. This draft licenses a `PRODUCT_EXPERIMENT` READ only; a
`RESEARCH_CLAIM` stays attended.

**Family:** `NIGHT_JOB_BOOKS_2026_09_14` — **two** primary-metric tests (H and
I) sharing one multiplicity budget, Holm across the declared two inside the job.
A NEW family declared at size 2 **before either read**. It does not extend
`NIGHT_JOB_BOOKS_2026_09_13` (E, F, G, C_v1), whose four primaries are read and
whose budget is spent, nor `NIGHT_JOB_BOOKS_2026_09` (A, B, C, D).

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital. Places nothing.

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(verdict recorded in §7).

- **Resurrects: nothing refuted.** `TRIAL-INSIDER-IC` and `TRIAL-CMP-INSIDER-IC`
  are `trans_code == 'P'` (open-market purchases) only and exclude grants by
  construction; Book B (insider clusters, `FAILED_VARIANT`) is also code `P`;
  the research registry's rows #30/#31 cover both. **This is the first book in
  this repository on `trans_code == 'A'`.** The registry's own "management
  motivation" line names option-grant timing as a gap where "no research exists
  yet" (`docs/research_notes/2026-09-13/research_registry.md`).
- **New instrument:** `backend/data/optimus/sec_insider/parsed/<YYYYqN>.parquet`,
  82 files, 2006q1..2026q2, read DIRECTLY. The distilled
  `insider_events_v1.parquet` is **not** the right input:
  `scripts/sec_insider_bulk_load.py` filters it to
  `is_open_market_purchase | is_open_market_sale`, discarding every
  `GRANT_AWARD` row at that step. The grant code has been on disk, unread, since
  the August pull.

## 1. Hypothesis

> Among US issuers whose insiders have a measurable OWN HISTORY of
> opportunistic option-grant timing — strictly-prior derivative grant awards
> whose mean market-adjusted 20-session pre-grant return is NEGATIVE and whose
> mean market-adjusted 20-session post-grant return is POSITIVE — the top
> tercile by that history statistic, inside the $3M-dollar-volume, $5-price
> eligible CRSP cross-section restricted to names carrying such a history,
> beats a turnover-matched random-universe twin drawn from that same covered
> band by more than the MDE in §4, over monthly date blocks 2006-2024.

**The precursor is the history, never the grant being priced** (invariant 2 of
CLAUDE.md's mission section). Every grant that enters a name's score was FILED
strictly before the month in which the name is selected. The grant currently
being priced contributes nothing to its own score.

**Honest prior.** Daines, McQueen & Schonlau and the surrounding option-timing
literature find that scheduled grants create an incentive to depress or to time
the grant price rather than to backdate it, with an economic magnitude quoted
per grant (≈ $451,748) and **never as a portfolio monthly spread**. The
2026-09-13 spec records that ruler as **NOT FOUND** in mean-spread form; the
per-grant dollar figure is used in this draft only as a plausibility check that
selected names' dollar moves are of a sane order, and is **never** a return
target. This book's honest prior is therefore weak, and §4's declared effect
sits BELOW its own MDE for exactly that reason — which §4 states rather than
hides.

## 2. The data and the PIT rule, MEASURED before the read

Measured on disk 2026-09-14, before this draft was written:

| quantity | measured |
|---|---|
| `parsed/*.parquet` files | **82**, 2006q1..2026q2 |
| rows with `trans_code == 'A'` and `table == 'DERIV'` | **1,276,210** |
| of those, carrying a resolved `permno` | **0.7992** |
| distinct issuers | **7,728** |
| distinct (`issuer_cik`, `owner_cik`) pairs | **139,983** |
| pairs with ≥ 4 grants (i.e. ≥ 3 strictly-prior for the 4th) | **70,885** |
| `plan_10b5_1 == 'YES'` among DERIV grants | **0.734%** (7,483 rows) |
| grants per filing-year | 77,347 (2006) falling to 41,686 (2024) |

Every row of that table below the `permno` line is counted on the
**resolved-permno subset** (1,019,995 rows of the 1,276,210): a grant this book
cannot link to a CRSP name cannot enter a score, so counting issuers and pairs
over unlinkable rows would overstate the band the book actually trades. The
unrestricted counts are 11,014 issuers and 175,706 pairs, and the gap between
the two pairs of numbers IS the link's coverage.

`table == 'DERIV'` is the frozen restriction: those are stock-option awards.
`table == 'NONDERIV'` code-`A` rows are RSU / restricted-stock grants — a
different instrument with no strike and no grant-price-timing incentive — and
they are **excluded from the book and reported as a separate diagnostic only**.

**The PIT rule, and the column that does not exist.** The parsed table carries
an `acceptance_datetime_utc` column and it is **100% NULL on this vintage**
(measured on 2015q1: 0.0000 non-null). It was checked rather than assumed. The
usable stamp is therefore `observed_at_utc`, which every row carries with
`observed_at_basis == "FILING_DATE_EOD_CONSERVATIVE"` — `filing_date` at 22:00
America/New_York. **Every date this book gates on is `filing_date`, never
`trans_date`**: the transaction happens up to two business days before anyone
outside the issuer can see it, and this table's whole PIT defence rests on that
gap being honoured. A grant enters a name's history only in months whose
selection close is strictly after its `filing_date`.

The pre/post windows around a grant are measured around the grant's
**`trans_date`** — that is where the mechanism lives — but a grant is only ever
READ into a score after its `filing_date` has passed, so no window that has not
yet been disclosed can influence a selection. Both dates are on the receipt.

The read is **2006-2024** (the span where the grant table and the CRSP daily
files overlap). Because a scoreable pair needs three strictly-prior grants, the
first month with a selection is expected around 2009; the receipt prints the
first and last block actually formed. Eras `(1990-1999, 2000-2009, 2010-2016,
2017-2024)` are REPORTED with their block counts; the first is empty here by
construction and says so.

## 3. Primary metric — the ONE deciding number

`net_monthly_excess_vs_random_twin`: the mean over **monthly date blocks** of

    (book's net monthly return) - (turnover-matched random twin's net monthly return)

both legs net of the flat 25 bps-per-side interim ruler
(`cost_curve: flat_25bps_pending_5c`, `zero_cost_diagnostic=False`), NW lag-2 t
on the block series, at the **$3M primary floor**.

**The twin is drawn from the SAME COVERED POOL** — issuers carrying at least one
resolved-permno DERIV grant filed in the trailing 36 months AND at least one
insider with ≥ 3 strictly-prior grants — so the book cannot beat its control by
requiring a grant history the control does not have. Turnover is matched by the
engine's own `_turnover_matched_draw`.

**Reported, never deciding:** the **$10M secondary floor** cell with its twin
re-drawn at that floor; the per-era split at both floors; the NONDERIV
(RSU/restricted-stock) variant as an instrument diagnostic; the 10b5-1-flagged
subset (see §5 for why it is reported and not deciding); realised turnover;
median names selected; the family Holm block over the declared two.

Two of the reported legs are **`FAILED_VARIANT` triggers** (§5).

## 4. Power — §64, computed BEFORE the confirmation

The family's shared power baseline (`backend/data/optimus/first_books/mde_receipt.json`,
the same k, engine and monthly CRSP panel Books C/E/F/G were read under):

| quantity | value |
|---|---|
| median cross-sectional monthly return sd | **0.167186** |
| k | 30 |
| implied book monthly sd (`cs_sd / sqrt(k)`) | 0.030524 |
| book-minus-twin monthly sd (`x sqrt(2)`) | **0.043167** |
| the family baseline block count (E/F/G, 1990-2024) | 360 |
| the family baseline MDE at 360 blocks | 0.637%/month |
| the same, deflated by the measured lag-1 rho 0.1268 | 0.724%/month |

**This book does not get 360 blocks.** The grant table starts 2006q1 and a
scoreable pair needs three strictly-prior grants, so the nominal block count is
**≈ 180** (2010-2024), and the arithmetic that matters here is:

| quantity | value |
|---|---|
| nominal monthly blocks | **≈ 180** |
| **MDE at 80% power, alpha 0.05, two-sided, at 180 blocks** | **0.901%/month** |
| the same, deflated by rho 0.1268 (n_eff 139.5) | **1.023%/month** |

**Declared effect size: 0.65%/month** — the same conservative figure Book F
declared, for the same reason (no mean-spread ruler exists to size against).
**It is BELOW this book's own MDE.** That is stated here, before the read, and
it binds §5: this construction is **underpowered for the effect it most
plausibly has**, an outcome in (0, 0.65%/month) is `CONDITIONAL` and explicitly
**not** a rejection of the mechanism, and a null here may never be read as
`MECHANISM_REJECTED`. **The MDE is recomputed from this book's own realised
difference series, its own block count and its own measured lag-1 rho before
the decision, and the recomputation is reported.**

declared_effect_size: 0.65% mean net monthly excess of the top-grant-timing-history tercile over a turnover-matched random twin drawn from the same covered band (BELOW this book's own nominal-180-block MDE of 0.901%/month and its deflated 1.023%/month; both are stated, and the book is declared underpowered for its own declared effect rather than sized to clear a bar cosmetically)
event_frequency_per_year: 12 (a monthly rebalance; approximately 180 nominal monthly date blocks over 2010-2024, n_effective 139.5 at the lag-1 rho of 0.1268 measured on this same panel for TRIAL-DRAFT-C; this book's own rho is re-measured from its own difference series before the decision)
outcome_dispersion: 0.0432 (the book-minus-twin monthly sd implied by a measured median cross-sectional monthly return sd of 0.167186 at k=30; the independence caveat of TRIAL-DRAFT-A section 4 applies and this is the optimistic bound)
outcome_horizon_days: 21 (one trading month; the grant-timing history is a slow-moving governance characteristic and the book is re-formed every month)
dependence_unit: ONE CALENDAR MONTH of the whole cross-section -- the 30 names held in a month share the market and are not 30 independent draws, so one independent observation is one monthly book-minus-twin difference and never one name-month
cross_sectional_k: 30
cross_sectional_rho: 0.1938 (MEASURED, not assumed: mean pairwise correlation of monthly name returns over 1995-2024, 250 names, 31,125 pairs, seed 20260912 -- receipt backend/data/optimus/first_books/mde_receipt.json, the same panel and k this book uses)
slice_purpose: CONFIRM -- 2006-2024 is the whole read and the whole decision. No slice of trans_code == 'A' has been read by any Aegis session, so there is no earlier fit for a confirm slice to be disjoint FROM, and the draft says so rather than manufacturing a holdout
selection_window_note: none. The 20-session pre/post windows, the three-prior-grant minimum, the DERIV restriction and the top-tercile cut were all chosen BEFORE any read, from the Daines option-timing literature's own event-window convention and from the minimum history the mechanism requires -- not from anything seen in this column's payoff. The 2026-09-14 measurements in section 2 are COVERAGE counts; no return was computed before this draft was written
slice_securities: CRSP common stock above a $3M median dollar-volume floor and a $5 price minimum that ALSO carry at least one resolved-permno DERIV GRANT_AWARD filed in the trailing 36 months and at least one insider with three or more strictly-prior such grants; the twin is drawn from the identical covered band
slice_period: 2006-01-01 .. 2024-12-31
information_cutoff: each grant's own `filing_date` at 22:00 America/New_York (`observed_at_basis == FILING_DATE_EOD_CONSERVATIVE`). The `acceptance_datetime_utc` column exists on the table and is 100% NULL on this vintage -- checked, not assumed. A grant enters a score only in months whose selection close is strictly after its filing date
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from the published option-grant-timing literature (Daines-McQueen-Schonlau and the 2015 Journal of Corporate Finance grant-timing study) and from the 2026-09-13 spec's observation that trans_code == 'A' was already on disk and excluded from the distilled events table. No Aegis trial's OUTCOMES motivated it

## 5. Decision rule

Evaluated **once**, when the replay job's receipt exists. Earliest decision
date: immediately.

- **`PRODUCT_PROMISING`** — the $3M net block-mean >= +0.65%/month at NW lag-2
  t >= 2.0, **AND** both falsifiers pass, **AND** the sign is positive in at
  least 3 of the reported eras that carry blocks, **AND** the $10M cell is also
  positive.
- **`FAILED_VARIANT`** — **any one** of:
  1. the $3M net block-mean over the registered slice is **<= 0**, whatever the
     falsifiers did. (The TRIAL-DRAFT-C Amendment-1 clause, carried into this
     draft from the start rather than added after a read.)
  2. **the random-date placebo ALSO pays.** The same score recomputed with each
     grant's `trans_date` relabelled to a pseudo-date drawn 90-180 days away
     from the true one (same insider, same issuer, same filing-date gate, same
     seed discipline) must be indistinguishable from zero at the |t| >= 2.0
     line. If ranking issuers on pre/post windows around a date where NOTHING
     happened pays as well as ranking them on the real grant date, what was
     measured is name-level return persistence in the insider's firms and not
     grant-timing skill, and the book is closed.
  3. **the effect does not live in the UNSCHEDULED subset.** Grants are split by
     the CMP routine/opportunistic rule already pinned in this repository
     (`sec_insider_bulk.classify_routine_opportunistic`, behaviourally identical
     to `cmp_insider.classify_buy`): an insider who granted in the SAME calendar
     month in each of the three strictly-prior years is **SCHEDULED**, otherwise
     **UNSCHEDULED**; no history is UNCLASSIFIABLE and is never defaulted to
     either. The book's payoff must be carried by the UNSCHEDULED subset. If the
     SCHEDULED subset pays as well (its net block-mean positive at |t| >= 2.0
     and at least as large as the unscheduled subset's), the effect is
     scheduled-grant calendar mechanics and not a governance signal, the
     "opportunistic" framing is falsified, and the book is closed even if the
     pooled number clears.
- **`CONDITIONAL`** — clears the primary metric but fails an era-stability or
  floor check, or NW t in [1.0, 2.0), or the block-mean lands between 0 and the
  declared effect. **§4 makes this the most likely honest outcome of a real
  effect at this sample size and it is not a euphemism for failure.**
- **`CANNOT_DETERMINE`** — a falsifier that could not be computed is not a
  falsifier that passed, stated in those words. If either subset of clause 3
  cannot produce a readable block mean over at least 24 blocks, clause 3 is
  **untestable, not passed**.
- **The 10b5-1 split is REPORTED and NOT deciding, and the reason is measured.**
  Only **0.734%** of DERIV grants carry `plan_10b5_1 == 'YES'` (§2), the
  checkbox exists as a filed field only from 2023 Q2 and pre-2023 rows carry
  `plan_10b5_1_source == 'ABSENT'` or `'FOOTNOTE_TEXT'` and never a silent
  False. A deciding falsifier that can structurally never produce a
  cross-section would be a gate that cannot go green — CLAUDE.md's own rule —
  so the planned-grant subset is printed with its coverage beside it and blocks
  no verdict. If a later vintage raises that coverage, the split becomes a
  registered falsifier by amendment and not by reinterpretation of this line.
- **Contamination clause.** If the covered band (issuers carrying a scoreable
  grant history) in any year falls below 0.10 of that year's eligible names, or
  below 3 x k names in the median month of that year, the year is EXCLUDED and
  the exclusion is reported before the number is.
- **Crash override.** A decision that would land within six months of an SPY
  trough >= -20% is deferred to >= 6 months past the trough.

## 6. Frozen parameters

The selector `option_grant_timing_v0` exactly as
`scripts/night_books_hi_replay.py` constructs it, hashed at the registration
commit. Also frozen: `trans_code == 'A'` with `table == 'DERIV'`; the
20-trading-session pre-window `[-20, -1]` and post-window `[+1, +20]` around a
grant's `trans_date`, both market-adjusted by the equal-weight cross-sectional
mean of the same sessions; the **minimum of three strictly-prior grants** per
(`issuer_cik`, `owner_cik`) pair; the qualifying condition `mean pre < 0 AND
mean post > 0`; the history statistic `mean(post) - mean(pre)`; aggregation to
the issuer by the **median** of its qualifying insiders' statistics; the
36-month grant-recency requirement in the pool filter; the **top tercile** cut;
k = 30; a monthly rebalance with a one-month holding period; the $3M primary and
$10M secondary floors; the $5 price minimum; the flat 25 bps per-side cost
ruler; the turnover-matched random twin drawn from the covered band; 2006-2024;
the placebo's 90-180 day offset band and its seed.

## 7. Corpse-check result

Run 2026-09-14 against the recorded corpus, before the read
(`python scripts/lint_prereg.py` from `C:/Users/mrthn/Aegis module`):

```
PASS   (vs 358 prior experiments)
R13: n_required 347  n_available 1958  smallest resolvable effect 0.27pp
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
nearest: 0.224 PREREG_TEACHER_LIBRARY_1 | 0.193 PREREG_REVISION_FORECASTER_1
         0.188 TRIAL-BRAIN-003-opportunistic-insider (REJECTED)
         0.180 TRIAL-EVENT-13DG
```

`PASS` means UNMATCHED, not novel: it compares wording against what this
programme has recorded and knows nothing about the literature.
`CALENDAR_DISJOINT_BY_CONSTRUCTION` is a claim on the record — if any threshold
or window in §6 was in fact chosen after looking at this table's payoff, that
declaration is false and the result is not a confirmation.

**The nearest recorded corpse is named rather than left at a similarity
score.** `TRIAL-BRAIN-003-opportunistic-insider` (2026-07-21, REJECTED) is the
Cohen-Malloy-Pomorski routine/opportunistic split on **non-derivative
open-market PURCHASES, `TRANS_CODE='P'`, 10b5-1 excluded** — it shares this
draft's vocabulary and none of its instrument. This book reads `trans_code ==
'A'` derivative GRANTS, a code BRAIN-003 discards by construction, and its
mechanism is the issuer's grant-price timing rather than the insider's
conviction in a purchase. It borrows only the CMP routine/unscheduled RULE, as
§5 clause 3, and says so there.

## 8. What this rule may NOT do

- No window search after the first read. `[-20,-1]`/`[+1,+20]` is the frozen
  pair; reading `[-40,-1]`, `[+1,+60]` or a CAR against a factor model for a
  better number would be several books wearing one registration's clothes.
- No moving the three-prior-grant minimum, and no dropping the `mean pre < 0
  AND mean post > 0` qualifying condition, after the first read. Either is a
  separate amendment naming only the input.
- No promoting the NONDERIV (RSU) diagnostic or the 10b5-1 subset to primary.
- No quoting the $3M-floor number as the result if the $10M cell disagrees;
  both are printed or neither is.
- No restating the $451,748-per-grant magnitude as this book's result, and no
  converting it into an implied monthly spread.
- No reading a null here as `MECHANISM_REJECTED`. §4 declares this construction
  underpowered for its own declared effect; a global negative from an
  underpowered read is `FAILED_VARIANT` for this implementation at most.
- No short leg. The bottom tercile is REPORTED and never traded.
- No `RESEARCH_CLAIM` from this registration alone.
- No reporting the book's absolute return as an alpha: the claim is a
  DIFFERENCE, and no LEVEL under a placeholder cost ruler may be quoted as
  measured.

## 9. Registry

`rule_experiments` row `option-grant-timing-v0`, **not yet written** — the same
state TRIAL-DRAFT-A/B/C/D/E/F/G stand in. Signing is the attended step; this
file and its commit timestamp are the tamper evidence that the rule existed
before the read.

## 10. The first read, 2026-09-14 — what it said

Receipt: `backend/data/optimus/night_factory_2026-09-14/B_books_hi_replay_run01.json`
(75 s, CPU, `NIGHT_RUN_DATE=2026-09-14`, 227 monthly blocks 2006-2024, no year
excluded by the contamination clause at either floor, `honours_the_registration:
true`). **UNSIGNED. Nothing is adopted by this section; it records what the read
said.**

| | $3M | $10M | 1990s | 2000s | 2010-16 | 2017-24 |
|---|---|---|---|---|---|---|
| `option_grant_timing_v0` @ $3M | **-0.091%/mo t -0.29** | | empty | +0.36 (t 0.73) | -0.14 (t -0.40) | **-0.27 (t -0.42)** |
| the same @ $10M | | **+0.347%/mo t 1.06** | empty | +0.33 (t 0.66) | +0.36 (t 0.87) | **+0.35 (t 0.54)** |

**Verdict under §5: `FAILED_VARIANT`, on clause 1** — the $3M primary is on the
wrong side of zero (-0.091%/month, t -0.29 over 227 blocks). That clause was
carried into this draft from the start rather than added after a read, and it
closes the book whatever the rest of the receipt says.

**Both falsifiers PASSED, and the pass is uninformative — which has to be said
rather than quietly banked.** The random-date placebo is **-0.350%/month, t
-0.94** (it does not pay, so clause 2 does not fire) and the scheduled subset is
**-0.194%/month, t -0.59** against the unscheduled subset's **-0.289%/month, t
-0.82** (the scheduled leg does not out-earn the unscheduled one, so clause 3
does not fire). But *neither leg pays at all*, so what the two clauses actually
establish is that nothing here is alive to be explained away. A falsifier that
passes is not evidence FOR the book, and a falsifier that passes because every
leg is flat is not even a falsifier that ran on a live effect. This is the same
shape as Book C's 2026-09-13 momentum falsifier, which "passed" with raw
momentum at t 0.15 and nothing alive to subsume.

**The floors disagree, and §8 governs how that may be quoted.** The $10M cell is
**+0.347%/month at t 1.06** with all three populated eras positive; the $3M cell
is negative. §8 forbids quoting either floor alone, so both are above. It does
NOT license reading the $10M cell as a result: it is half the declared 0.65%
effect, at a t of 1.06, on a book whose registered primary metric is the $3M
cell, and promoting it would be choosing the corner after seeing it.

**Power, recomputed from the book's own realised series** (as §4 promised):
0.887%/month at $3M (227 blocks, realised difference sd 0.0483, measured lag-1
rho **-0.011**, n_eff 232.1) and 0.921%/month at $10M. Both land essentially on
the registered 0.901% nominal figure, so the sample was as powered as declared —
and §4's uncomfortable line still binds: the declared 0.65% effect sits BELOW
that MDE, a null here is weak evidence of absence, and **this result may not be
read as `MECHANISM_REJECTED`**. It closes THIS construction of option-grant
timing.

**Coverage and instrument, measured on the run:** 1,019,988 DERIV code-`A` rows
read, **986,195 (96.7%) carried a computable 20/20-session window**; 139,983
(issuer, insider) pairs; 529,521 pair state rows expanded to 11,308,425
pair-months over 228 months. Grant classes: **612,147 UNCLASSIFIABLE / 250,228
routine / 157,613 opportunistic** — the unclassifiable majority is the CMP
rule's three-strictly-prior-years requirement biting on a table that starts in
2006, and those rows are in NEITHER leg of clause 3. Covered share inside the
eligible band: 0.238 in 2006 (519 covered names at the median month), 0.722 in
2015 (1,396), 0.682 in 2024 (1,365). No year fell below the 0.10 / 3k clause.

**The current era at the tradable floor, asked and answered plainly:** the
2017-2024 cell at $10M is **+0.35%/month at t 0.54 over 96 blocks**. It is
positive, it is roughly half the declared effect, and it is nowhere near the
|t| >= 2 line. **The current era does not carry this effect.**
