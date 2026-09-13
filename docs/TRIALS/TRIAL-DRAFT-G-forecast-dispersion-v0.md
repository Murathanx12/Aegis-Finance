# TRIAL-DRAFT-G — analyst forecast dispersion, long-only-avoid (`forecast_dispersion_v0`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-13, before any read. It is not in
`rule_experiments` and has not incremented `cumulative_trials`: registration is
the attended step. This draft licenses a `PRODUCT_EXPERIMENT` READ only; a
`RESEARCH_CLAIM` stays attended.

**Family:** `NIGHT_JOB_BOOKS_2026_09_13` — **four** primary-metric tests (E, F,
G, and Book C's v1 re-read) sharing one multiplicity budget, Holm across the
declared four inside the job. A NEW family declared at size 4 before the read.

**Licence:** `PRODUCT_EXPERIMENT`. Accrues zero capital. Places nothing.

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(verdict recorded in §7).

- **Resurrects: nothing refuted.** The IBES consensus panel has been read once
  in this repository, by Book C's v0 event sign, which used `numup` and
  `numdown` — a revision COUNT. `stdev`, `meanest` and `numest` have never been
  read by any book here. A disagreement LEVEL and a revision DIRECTION are
  different columns and different mechanisms, and the distinction is what this
  draft turns on.
- **The corpse this book must be read against is Book A.** `A_corner_run01`
  (2026-09-13) closes `si_low_turnover_high_v1` as **FAILED_VARIANT**:
  −0.9368%/month at the $3M floor over 168 confirm blocks, NW lag-2 t −2.0877,
  with the $10M cell at −0.2527%/month (t −0.6377). Low short interest is a
  short-sale-constraint proxy and Miller (1977) is the mechanism BOTH books
  claim, so a low-dispersion book that is really a low-short-interest book is
  standing on a cell this family has already read and closed. §5 clause 3 is
  that test.
- **New instrument:** the dispersion columns themselves —
  `backend/data/optimus/wrds/ibes_consensus_monthly_early.parquet` (3,682,004
  rows, 1990-2012) and `ibes_consensus_monthly.parquet` (1,554,570 rows,
  2013-2024), columns `stdev`, `meanest`, `numest`, `statpers`, `fpi`,
  `measure`, `permno` — schemas read directly on 2026-09-13, not assumed.

## 1. Hypothesis

> The BOTTOM tercile of `|stdev / meanest|` — the coefficient of variation of
> the one-year-ahead EPS consensus, restricted to names with `numest >= 3` —
> inside the $3M-dollar-volume, $5-price eligible CRSP cross-section restricted
> to names carrying that ratio, beats a turnover-matched random-universe twin
> drawn from that same covered band by more than the MDE in §4, over monthly
> date blocks 1990-2024.

**Honest prior.** Diether, Malloy & Scherbina (*Journal of Finance*
57(5):2113-2141, 2002): the highest-dispersion quintile underperforms the
lowest by **0.79%/month (9.48%/year)** in the month after formation, on a
1983-2000 sample, concentrated in small stocks and past losers. **That is a
long-short spread on a pre-2005 sample.** Two haircuts apply before it becomes
a prior for THIS book, and both are applied rather than mentioned:
(a) McLean-Pontiff-style post-publication decay of roughly 50%, implying about
0.40%/month; (b) a **long-only-avoid** construction captures only the long
half of a long-short spread by design. The 2026-09-13 research note records
that **no post-2010 replication number was found** — marked NOT FOUND, not
filled in. So the working prior for this construction is **below** the declared
effect in §4, and §4 says so instead of hiding it: this book may well fail its
own power check, and that is a property of the honest arithmetic and not a
reason to inflate the declared effect.

**Why long-only-avoid and not a short book.** `NEGATIVE_RESULTS.md`'s banked
finding (Muravyev, Pearson & Pollet 2025, cited in `ROADMAP...11c`'s
banked-negatives list) is that 162 anomalies go from +0.14%/month to
−0.01%/month **after borrow fees**. The short leg of DMS's own spread is
exactly the leg that finding warns about, and this repository does not get to
assume it survives. The book therefore holds the low-disagreement names and
systematically avoids the high-disagreement ones, and the high-dispersion leg
is reported as a diagnostic, never traded and never deciding.

**And it is a LOSER-side hypothesis.** CLAUDE.md Rule 4 asks that losers be
studied as hard as winners; of the family's four books this is the one whose
entire content is "which names to stay out of".

## 2. The window and the PIT stamp

The read is **1990-2024**: the IBES consensus panel begins 1990-01-18 and the
CRSP daily files begin 1990. Eras `(1990-1999, 2000-2009, 2010-2016,
2017-2024)` are REPORTED.

The consensus row's stamp is **`statpers`**, the consensus date — the same
column Book C's v0 sign keys on. A row stamped in month `m` is read at the
close of month `m` and the earliest return it can touch is `m+1`'s. `statpers`
is a monthly IBES snapshot date, not a filing date, and there is no vendor lag
behind it to get wrong; `anndats_act` (the announcement date on the same table)
is a DIFFERENT column for a different book and is not used here.

`numest >= 3` is frozen at 3, not 2: a two-analyst standard deviation is a
single pairwise difference, and a "dispersion" built on one disagreement is a
noise measurement. The threshold is declared before the read and may not move
after it.

## 3. Primary metric — the ONE deciding number

`net_monthly_excess_vs_random_twin`: the mean over **monthly date blocks** of

    (book's net monthly return) - (turnover-matched random twin's net monthly return)

both legs net of the flat 25 bps-per-side interim ruler
(`cost_curve: flat_25bps_pending_5c`, `zero_cost_diagnostic=False`), NW lag-2 t
on the block series, at the **$3M primary floor**.

**The twin is drawn from the SAME COVERED POOL** — names with `numest >= 3` and
a computable ratio that month — so the twin cannot lose merely by lacking the
analyst coverage the book requires. Turnover is matched by the replay engine's
own `_turnover_matched_draw`, so the cost term cancels out of the difference.

**Reported, never deciding:** the **$10M secondary floor** cell with its twin
re-drawn at that floor; the per-era split at both floors; the HIGH-dispersion
tercile's own excess (the leg the book avoids); realised turnover; median names
selected; the family Holm block.

Two of the reported legs are **`FAILED_VARIANT` triggers** (§5).

## 4. Power — §64, computed BEFORE the confirmation

Receipt: `backend/data/optimus/first_books/mde_receipt.json`. Same k, same
engine, same monthly CRSP panel as Book C, so the same arithmetic:

| quantity | value |
|---|---|
| median cross-sectional monthly return sd | **0.167186** |
| k | 30 |
| implied book monthly sd (`cs_sd / sqrt(k)`) | 0.030524 |
| book-minus-twin monthly sd (`x sqrt(2)`) | **0.043167** |
| monthly blocks, nominal | **360** |
| **MDE at 80% power, alpha 0.05, two-sided, at 360 blocks** | **0.637%/month** |
| the same MDE deflated by the measured lag-1 rho 0.1268 (n_eff 278.98) | **0.724%/month** |

**Declared effect size: 0.65%/month**, one notch above the nominal MDE.

**The uncomfortable line, stated rather than buried:** the haircut-adjusted
literature prior for a long-short spread is about 0.40%/month, and a
long-only-avoid construction captures less than that. **The declared effect is
therefore ABOVE the honest prior, which means this book is underpowered for the
effect it most plausibly has.** The declaration stays at 0.65% because it is
the family's convention (one notch above the MDE) and because inventing a lower
threshold after seeing that arithmetic would be choosing a threshold to pass.
What follows is that a null result here is **weak evidence of absence** and the
verdict must say so: an outcome between 0 and 0.65% is `CONDITIONAL`, not a
rejection of the mechanism.

Both MDE figures are stated. **The MDE is recomputed from this book's own
realised difference series before the decision and the recomputation is
reported.** The independence caveat of TRIAL-DRAFT-A §4 applies: 0.637% is the
optimistic bound.

declared_effect_size: 0.65% mean net monthly excess of the bottom-dispersion-tercile long-only-avoid book over a turnover-matched random twin drawn from the same numest>=3 covered band (one notch above the nominal-360-block MDE of 0.637%/month; the autocorrelation-deflated figure is 0.724%/month; the haircut-adjusted literature prior for the LONG-SHORT spread is about 0.40%/month and this construction captures less, so the book is declared underpowered for its own most plausible effect and a null here is weak evidence of absence)
event_frequency_per_year: 12 (a monthly rebalance; 360 nominal monthly date blocks, n_effective 278.98 at the lag-1 rho of 0.1268 measured on this same panel for TRIAL-DRAFT-C; this book's own rho is re-measured from its own difference series before the decision)
outcome_dispersion: 0.0432 (the book-minus-twin monthly sd implied by a measured median cross-sectional monthly return sd of 0.167186 at k=30; the independence caveat above says this is the optimistic bound)
outcome_horizon_days: 21 (one trading month; DMS measure the month AFTER formation and this book earns exactly that month)
dependence_unit: ONE CALENDAR MONTH of the whole cross-section -- the 30 names held in a month share the market and are not 30 independent draws, so one independent observation is one monthly book-minus-twin difference and never one name-month
cross_sectional_k: 30
cross_sectional_rho: 0.1938 (MEASURED, not assumed: mean pairwise correlation of monthly name returns over 1995-2024, 250 names, 31,125 pairs, seed 20260912 -- receipt backend/data/optimus/first_books/mde_receipt.json, the same panel and k this book uses)
slice_purpose: CONFIRM -- 1990-2024 is the whole read and the whole decision. No slice of the dispersion columns has been read by any Aegis session; Book C's v0 read `numup`/`numdown` on the same table, which is a different column and a different mechanism
selection_window_note: none. The tercile cut, the `numest >= 3` threshold, the coefficient-of-variation normalisation and the long-only-avoid direction were all fixed BEFORE any read, from Diether-Malloy-Scherbina's own construction and from this repository's banked borrow-cost negative. Nothing in §6 was chosen after looking at this column's payoff
slice_securities: CRSP common stock above a $3M median dollar-volume floor and a $5 price minimum that ALSO carry an IBES one-year-ahead EPS consensus with `numest >= 3` and a non-zero `meanest` at that month's `statpers`; the twin is drawn from the identical covered band
slice_period: 1990-01-01 .. 2024-12-31
information_cutoff: the IBES consensus row's own `statpers` (the monthly consensus snapshot date). A row stamped in month m is read at that month's close and the earliest return it can touch is month m+1's
selection_period: none
parent_trial: none
hypothesis_source: NONE -- the question comes from the published literature (Diether, Malloy & Scherbina, Journal of Finance 57(5):2113-2141, 2002) and from the 2026-09-13 research note's observation that `stdev`/`numest`/`meanest` were already on disk and unread. Book A's closed FAILED_VARIANT cell is quoted in section 0 as a corpse to test against, not as a result that suggested this one

## 5. Decision rule

Evaluated **once**, when the replay job's receipt exists. Earliest decision
date: immediately.

- **`PRODUCT_PROMISING`** — the $3M net block-mean >= +0.65%/month at NW lag-2
  t >= 2.0, **AND** both falsifiers pass, **AND** the sign is positive in at
  least 3 of the 4 reported eras, **AND** the $10M cell is also positive.
- **`FAILED_VARIANT`** — **any one** of:
  1. the $3M net block-mean over the registered slice is **<= 0**, whatever the
     falsifiers did;
  2. **the effect does not survive outside the smallest names.** DMS's own
     paper reports the effect concentrated in small stocks; re-run the book
     inside the TOP HALF of the eligible band by median dollar volume (its own
     twin re-drawn there) and require the net excess to stay positive. If the
     whole payoff lives in the smallest names of a $3M-floor universe, this is
     small-cap beta and not a disagreement premium;
  3. **dispersion dies with short interest on the right-hand side.** In a
     Fama-MacBeth cross-sectional regression of next month's return on
     `z(-dispersion)` and `z(si_ratio)` over the same universe (the
     short-interest panel `backend/data/optimus/short_interest/
     comp_sec_shortint/<year>.parquet`, joined on `observed_at <= close`),
     dispersion's own payoff must survive at |t| >= 2.0. Miller (1977) is the
     mechanism BOTH this book and Book A claim, and Book A's cell is already
     closed FAILED_VARIANT at −0.94%/month; a low-dispersion book that is a
     low-short-interest book in costume is standing on that corpse.
- **`CONDITIONAL`** — clears the primary metric but fails an era-stability or
  floor check, or NW t in [1.0, 2.0), or the block-mean lands between 0 and the
  declared effect. **Per §4, an outcome in (0, 0.65%) is CONDITIONAL and is
  explicitly NOT a rejection of the mechanism**: this construction is
  underpowered for its own most plausible effect and the verdict must carry
  that sentence.
- **`CANNOT_DETERMINE`** — a falsifier that could not be computed is not a
  falsifier that passed. If the short-interest panel does not cover the read
  window, or if dispersion's own RAW payoff is not alive (|t| < 2.0 before any
  control is added), clause 3 is **untestable, not passed**, and the receipt
  says so in those words.
- **Contamination clause.** If the covered band (`numest >= 3`, computable
  ratio) in any year falls below 0.10 of that year's eligible names, or below
  3 x k names in the median month of that year, the year is EXCLUDED and the
  exclusion is reported before the number is.
- **Crash override.** A decision that would land within six months of an SPY
  trough >= -20% is deferred to >= 6 months past the trough.

## 6. Frozen parameters

The selector `forecast_dispersion_v0` exactly as
`scripts/night_books_efg_replay.py` constructs it, hashed at the registration
commit. Also frozen: the ratio `|stdev / meanest|`; `numest >= 3`; `fpi == '1'`
and `measure == 'EPS'`; the **bottom tercile** (low disagreement) as the held
leg and the top tercile as avoided and never shorted; k = 30; a monthly
rebalance with a one-month holding period; the $3M primary and $10M secondary
floors; the $5 price minimum; the flat 25 bps per-side cost ruler; the
turnover-matched random twin drawn from the covered band; 1990-2024.

## 7. Corpse-check result

Run 2026-09-13 against **358 prior experiments**:

```
PASS   (n_required 347, n_available 1958, smallest resolvable effect 0.27pp)
R13e `CALENDAR_DISJOINT_BY_CONSTRUCTION`, R13f `NO_HYPOTHESIS_SOURCE_DECLARED`
```

`PASS` means UNMATCHED, not novel. `CALENDAR_DISJOINT_BY_CONSTRUCTION` is a
claim on the record: if any threshold, tercile boundary or universe in §6 was in
fact chosen after looking at this corpus, that declaration is false and the
result is not a confirmation.

## 8. What this rule may NOT do

- No short leg. The high-dispersion tercile is REPORTED and never traded; a
  short-side number from this job may not be quoted as a strategy return,
  because the borrow cost that killed 162 anomalies is not in the cost ruler.
- No moving `numest` off 3, and no swapping the coefficient of variation for a
  price-scaled dispersion, after the first read. Either is a separate
  amendment naming only the input.
- No quoting the $3M-floor number as the result if the $10M cell disagrees;
  both are printed or neither is.
- No restating DMS's 0.79%/month as this book's result, and no quoting the
  haircut-adjusted 0.40%/month as a measured number — it is an arithmetic prior
  and is labelled one.
- No reading a null here as `MECHANISM_REJECTED`. §4 declares this construction
  underpowered for its own most plausible effect; a global negative from an
  underpowered read is `FAILED_VARIANT` for this implementation at most.
- No `RESEARCH_CLAIM` from this registration alone.

## 8b. Amendment 1 (proposed, UNSIGNED) — the denominator becomes PRICE

**Proposed 2026-09-13 by the chunk-15b build session, AFTER run 01 and BEFORE
the amended read. NOT ADOPTED.** Fable adopts it in the morning if it names only
the input, as Book C's Amendment 2 did. Until then this section licenses a
`PRODUCT_EXPERIMENT` read and nothing else; `forecast_dispersion_v0`'s own
verdict is untouched by it.

§8 forbids "swapping the coefficient of variation for a price-scaled dispersion,
after the first read" inside this registration, and says the swap is "a separate
amendment naming only the input". **This is that amendment.**

**What changes, in one sentence.** Dispersion becomes

    |stdev / price|

where `price` is the **panel's own PIT CRSP close of the selection month**
(`eom`) — the same `price` column the eligibility band and the $5 minimum are
already computed from, so no new table, no new stamp and no new lag are
introduced. `numest >= 3` is unchanged. Everything else in §6 is v0's, field for
field: `fpi == '1'`, `measure == 'EPS'`, the **bottom tercile** held and the top
avoided and never shorted, k = 30, the monthly rebalance and one-month hold, the
$3M primary and $10M secondary floors, the $5 price minimum, the flat 25 bps
per-side ruler, the turnover-matched twin, 1990-2024, both falsifiers of §5 and
the contamination clause.

**The covered band is v0's, unchanged, including `meanest != 0`.** That clause
stays a MEMBERSHIP test even though `meanest` is no longer the denominator, so
the amendment ranks exactly the names v0 ranked and its twin is drawn from
exactly the same pool. Only the **score** moves. If the covered band moved too,
the two reads would differ by coverage as well as by construction and neither
number would be comparable to the other — which is the mistake this whole
paragraph exists to prevent.

**Why the input is wrong today, stated as the reason rather than as a
preference.** Run 01's own receipt (`B_books_efg_replay_run01`, 2026-09-13):

| | $3M | $10M | 2017-2024 at $10M |
|---|---|---|---|
| `forecast_dispersion_v0` | **+0.89%/month, t 4.82** | +0.72%/month, t 4.42 | **+0.02%/month, t 0.07** |

**+0.89%/month exceeds Diether-Malloy-Scherbina's published 0.79%/month
LONG-SHORT spread**, and §1 of this registration declares that a long-only-avoid
construction captures only the long half of that spread by design, on a sample
whose post-publication decay §1 already haircuts by about 50%. A half cannot
exceed its own whole. Something other than disagreement is being paid for.

The candidate mechanism is named rather than left as a suspicion: `|stdev /
meanest|` divides by **forecast EPS**, so the ratio explodes wherever consensus
EPS is near zero, and near-zero forecast EPS is an **earnings-LEVEL** condition,
not a disagreement condition. The bottom tercile of that ratio is therefore
tilted towards high-EPS-per-share names, which is a profitability/value tilt
riding inside a variable labelled "dispersion". Scaling by price removes that
channel: price is bounded away from zero by this band's own $5 minimum, so
`|stdev / price|` is forecast uncertainty per dollar of share price and nothing
else. (It is also the normalisation that is homogeneous with the return the book
earns, which is a per-dollar quantity.)

**What this amendment does NOT claim.** It does not claim that the price-scaled
read is the true one, that v0's number was wrong arithmetic, or that a smaller
number under the amendment would refute the mechanism. It claims that **v0's
denominator carries a channel the registration never intended to trade**, and
that the cheapest way to find out how much of the payoff that channel was is to
change the denominator and nothing else.

**How it is read.** `scripts/night_books_efg_replay.G_price_scaled`, registered
as the night job `G_price_scaled`, label `forecast_dispersion_price_scaled_v1`.
It is **its own declared family of ONE**, `NIGHT_JOB_G_PRICE_SCALED_2026_09_13`
— it does **not** join `NIGHT_JOB_BOOKS_2026_09_13`, whose four primaries are
read and whose multiplicity budget is spent; a fifth leg added after that
family's numbers were seen would be a family that grew to fit a result. The
receipt additionally prints a **two-construction Holm** against v0's own primary
p-value, because one mechanism has now been read twice on one panel and that
correction is what a reader is owed. That block is REPORTED; the decision rule
is §5's, applied to this construction's own numbers.

**§4's power arithmetic is unchanged and still binds**, including its
uncomfortable line: the declared effect of 0.65%/month is above the honest
prior, this construction is underpowered for the effect it most plausibly has,
and an outcome in (0, 0.65%) is `CONDITIONAL` and explicitly **not** a rejection
of the mechanism.

**What would make this amendment wrong.** If the price-scaled read comes back at
or above v0's +0.89%/month, the earnings-level explanation of the excess is not
supported and the amendment has changed the input without changing the finding —
in which case the thing to explain is still why a long-only half beats a
published long-short whole, and the next candidate is the cost ruler or the
covered band, not the denominator.

## 8c. The amended read, 2026-09-13 — and the amendment's own explanation FAILS

Receipt: `backend/data/optimus/night_factory_2026-09-13/G_price_scaled_run01.json`
(61 s, CPU, `NIGHT_RUN_DATE=2026-09-13`, 419 monthly blocks 1990-2024, no year
excluded by the contamination clause at either floor). **UNSIGNED. Nothing is
adopted by this section; it records what the read said.**

| | $3M | $10M | 1990s | 2000s | 2010-16 | 2017-24 |
|---|---|---|---|---|---|---|
| **v0** `stdev / meanest` (run 01) | +0.89% t 4.82 | +0.72% t 4.42 | +0.96 | +1.09 | +0.65 | **+0.02 (t 0.07)** |
| **Amendment 1** `stdev / price` | **+1.02% t 5.65** | **+1.19% t 6.07** | +1.35 t 4.70 | +1.56 t 3.52 | +0.83 t 2.90 | **+0.83 (t 1.78)** |

(Amendment rows are the $10M cell's eras; the $3M eras are +1.48 / +1.14 / +0.88
/ +0.41 with t 5.41 / 2.77 / 3.10 / 1.04. Falsifiers, both passed: the big-half
cell is +1.11%/month t 6.32, so the payoff is not in the smallest names; with
`si_ratio` on the right-hand side dispersion survives at t 5.40 against a raw
5.46, so it is not Book A's closed short-interest cell in costume. The avoided
high-dispersion leg is **−2.47%/month t −7.82**, the largest leg in this book.
MDE recomputed from the book's own realised difference series: 0.509%/month at
$3M (n_eff 384.8, rho 0.043), 0.563% at $10M — both BELOW the registration's
modelled 0.637%, so the read is better powered than declared, not worse.)

**§8b's own falsification clause fires against §8b.** It said: *"If the
price-scaled read comes back at or above v0's +0.89%/month, the earnings-level
explanation of the excess is not supported and the amendment has changed the
input without changing the finding."* It came back **higher at both floors**.
So:

- the hypothesis that v0's excess was an earnings-LEVEL tilt smuggled in by the
  `meanest` denominator is **NOT SUPPORTED**. Removing that channel raised the
  excess;
- the original puzzle is **UNRESOLVED and is now larger**: a long-only-avoid
  half of a spread now returns +1.02%/month where the published LONG-SHORT whole
  is 0.79%/month. The next candidates are the ones §8b named as the fallbacks —
  the flat 25 bps cost ruler (which cannot see that a $3M name and a $10M name
  pay different spreads; chunk 5c's TAQ curve is the instrument) and the covered
  band itself — **not** a third denominator;
- **what the amendment DID buy, and it is the interesting part:** the current
  era. v0's 2017-2024 cell at the tradable floor is +0.02%/month, t 0.07 — a
  decayed 1990s effect. The price-scaled cell is **+0.83%/month, t 1.78** on 96
  blocks: below |t| 2, still `CONDITIONAL` by §5, and the first version of this
  book that is not simply dead where we trade.

**Verdict under §5, on this construction's own numbers: `PRODUCT_PROMISING`**
(primary +1.02%/month ≥ the declared 0.65% at t 5.65 ≥ 2.0; both falsifiers
passed; 4/4 eras positive; the $10M cell positive). **It is not a claim.** It is
one read of one construction on one cost ruler, unsigned, under a flat-cost
interim ruler that the repository's own `NEGATIVE_RESULTS` §25 records two other
rulers disagreeing with by 3.4-9.1×, and the era row that matters most is the
one that does not clear |t| 2.

**Holm.** The amendment's own declared family is size 1 (p_raw < 1e-6, rejects).
Reported beside it, because one mechanism has now been read twice on one panel:
Holm over BOTH constructions — price-scaled at alpha 0.025 and v0 at 0.05, both
reject.

**What must happen before any of this moves capital:** adoption of §8b by a
human (it is UNSIGNED), the TAQ cost curve replacing the flat ruler, and a
2017-2024 cell that clears |t| 2 at the $10M floor. None of the three has
happened.

## 9. Registry

`rule_experiments` row `forecast-dispersion-v0`, **not yet written** — the same
state TRIAL-DRAFT-A/B/C/D/E/F stand in. Signing is the attended step; this file
and its commit timestamp are the tamper evidence that the rule existed before
the read.
