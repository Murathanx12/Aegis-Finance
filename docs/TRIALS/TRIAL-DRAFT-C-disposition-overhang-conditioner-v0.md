# TRIAL-DRAFT-C — the disposition-overhang conditioner (`disposition-overhang-conditioner-v0`)

**STATUS: UNSIGNED DRAFT.** Written 2026-09-12, before any read. Not in
`rule_experiments`; `cumulative_trials` unchanged.

**Family:** `NIGHT_JOB_BOOKS_2026_09` (four primary tests, one budget; Holm at
export). **Licence:** `PRODUCT_EXPERIMENT`. Zero capital.

## 0. Corpse check — this one has a NAMED PARENT and must be read against it

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`.
The linter should be checked for a `SELECTION_WINDOW_CONTRADICTS_PARENT`-style
flag, because TRIAL-H5 is a named parent and this draft re-slices its
population.

- **Parent closure, cited in full rather than gestured at.** The event-level
  reaction learner at a five-session hold (TRIAL-H5) is **REJECTED by its own
  registered rule**: t 1.14 < 1.5 at the $10M floor; the control's own
  seed-median +17.64%/yr against a +4.0%/yr ceiling; sign unstable by era
  (+23.3 / −7.7 / +42.0 %/yr); drawdown −78% against a −45% budget; and the RW2
  random-window null (`RW2_event_windows_run01.json`, 240 seeded windows) has
  the learner beating its own control in **44%** of 1999-2007 starts and **46%**
  of 2016-2024 starts. `H5|all` is closed and no successor was registered.
- **Why this is not a resurrection.** Per CLAUDE.md's scope-aware-verdicts rule
  and `HANDOFF_2026-08-16` §2, that closure answers *"does the reaction drift,
  pooled over all holders?"* It never asked *"does it drift conditional on the
  holder base's unrealised gain or loss?"* This draft asks the second question
  **on the same closed population, as a re-slice**, and may not restate the
  pooled claim as its own result.
- **New instrument:** the capital-gains overhang itself
  (`book_signals.capital_gains_overhang`), Grinblatt-Han's price-and-turnover
  reference price, computed for the first time in this repository. H5 had no
  holder-side variable of any kind.

## 1. Hypothesis

> Within the population TRIAL-H5 closed, the subset of **good-news** names
> (positive monthly consensus revision, v0) that sit in the **top tercile of
> capital-gains overhang** beats the **unconditioned** book — the same event-sign
> universe, the same hold, without the overhang conditioning, run **fresh on the
> identical window** — by more than the MDE in §4, over monthly date blocks.

**Honest prior.** Frazzini (*JF* 61(4):2017-2046, 2006): post-event drift is
most severe where capital gains and news share a sign; overhang spread ≈
2.43%/month, t 6.60; the sign-flipped placebo ≈ 0. Grinblatt & Han (*JFE*
78(2):311-339, 2005): with overhang on the right-hand side, intermediate-horizon
momentum **disappears** — the literature's claim is that overhang subsumes
momentum, not the reverse. **Both use pre-2000 data.** "Still alive after 2010"
is the open question, and this repository has been burned three times by an
effect that was really 1999-2007.

## 2. The reference price, frozen verbatim

    RP_t  = (1/k) · Σ_{n=1..T} [ V_{t−n} · Π_{τ=1..n−1}(1 − V_{t−n+τ}) · P_{t−n} ]
    CGO_t = (P_{t−1} − RP_t) / P_{t−1}

`P` is price, `V_t` is period `t`'s turnover (`vol_t / (shrout_t × 1000)`, the
same computed column Book A uses), `k` normalises the weights to sum to 1, and
`T = 1260` trading days (Grinblatt-Han's 260 weeks, adapted to a daily panel).
**PIT by construction:** every input is the name's own past price and volume,
known entirely as of `t−1`. There is no vendor lag here and therefore no excuse
for a leak.

**Event sign, v0 (what is registered):** the sign of the monthly consensus
revision from `learner/dataset.py`'s existing IBES columns (`net_rev_1m`,
`target_rev_1m`, `consensus_rev_1m`). **v1 (gated on L2's typed events) is a
separate registration amendment naming only the event-sign input** — the
overhang construction does not move.

## 3. Primary metric — the ONE deciding number

`conditioned_minus_unconditioned`: the mean over monthly date blocks of

    (top-overhang-tercile good-news book, net) − (unconditioned good-news book, net, run fresh on the identical window)

NW lag-2 t. The comparator is **the unconditioned book re-run**, not a number
quoted from H5's closed receipt: a scope-aware verdict needs a live comparator
or the claim "the conditional question was never asked" is rhetoric rather than
a falsifiable statement. Per the house standard the book ALSO carries a
random-universe twin and a beta-matched twin; those are secondary here.

**Reported, never deciding:** the sign-flip placebo; the
momentum-orthogonalisation regression; the per-era split with a decay t; the
$10M-floor re-measurement; the v0-vs-v1 comparison once L2 lands.

Two of those are **`FAILED_VARIANT` triggers** and not merely diagnostics (§5).

## 4. Power — §64, computed BEFORE the confirmation

Receipt: `backend/data/optimus/first_books/mde_receipt.json`.

| quantity | value |
|---|---|
| median cross-sectional monthly return sd, 1995-2024 | **0.167186** |
| k | 30 |
| implied book monthly sd | 0.030524 |
| book-minus-comparator monthly sd | **0.043167** |
| monthly blocks | 360 |
| measured lag-1 ρ | **0.1268** |
| n_effective | **278.98** |
| **MDE at 80% power, α 0.05, two-sided** | **0.724%/month** |

**Declared effect size: 1.00%/month**, one notch above the MDE and well below
Frazzini's 2.43%.

Two caveats travel with the number. (a) The independence caveat of
TRIAL-DRAFT-A §4 applies identically; 0.724% is the **optimistic** bound.
(b) The comparator is a highly correlated book, not the market, so the realised
difference series will have a **smaller** sd than the table's — which pushes the
true MDE the other way. Both directions are stated because quoting only the
flattering one is how a power check becomes decoration. The MDE is recomputed
from the realised difference series before the decision and the recomputation
is reported.

The 1995 start is a **declared deviation**: the CGO lookback is 1,260 sessions
and the CRSP daily files begin 1990, so the first five years are warmup.

declared_effect_size: 1.00% mean net monthly excess of the top-overhang-tercile good-news book over the unconditioned book run fresh on the identical window (one notch above the computed MDE of 0.724%/month and well below Frazzini's 2.43%/month)
event_frequency_per_year: 12 (a monthly rebalance; 360 monthly date blocks over 1995-2024, n_effective 278.98 after the measured lag-1 rho of 0.1268)
outcome_dispersion: 0.0432 (the book-minus-comparator monthly sd implied by a measured median cross-sectional monthly return sd of 0.167186 at k=30; both directions of its bias are stated above)
outcome_horizon_days: 63 (a three-month hold, in trading days, reviewed monthly)
dependence_unit: ONE CALENDAR MONTH of the whole cross-section; and because the comparator is the unconditioned book on the SAME names, the two legs share their market exposure almost entirely, which is what makes a difference series the right unit
cross_sectional_k: 30
cross_sectional_rho: 0.1938 (MEASURED: mean pairwise correlation of monthly name returns over 1995-2024, 250 names, 31,125 pairs, seed 20260912)
slice_purpose: REANALYSIS -- this is an explicit re-slice of TRIAL-H5's closed population by a conditioning variable that trial never carried, and it says so rather than presenting itself as a fresh confirmation. It may not restate H5's pooled claim as its own
selection_window_note: TRIAL-H5 and RW2 read 1999-2024 on this population, so NO window here is unread and the draft does not pretend otherwise. What is unread is the CONDITIONING: no session has computed a capital-gains overhang on any window, so the overhang tercile split has never been looked at, in-sample or out. The parent's closure is cited in full in section 0 and the comparator is the unconditioned book RE-RUN, not the parent's receipt
slice_securities: CRSP common stock with 1,260 sessions of price and volume history and a non-zero monthly IBES consensus revision, above a $3M median dollar-volume floor and a $5 price minimum
slice_period: 1995-01-01 .. 2024-12-31
information_cutoff: price and turnover strictly before the decision close for the overhang; the IBES revision as of the month already closed. No input has a vendor lag to get wrong
selection_period: 1999-01-01 .. 2024-12-31
parent_trial: TRIAL-H5

## 5. Decision rule

Earliest decision date: v0 runs as soon as the CGO computation is built against
the existing price/volume panel — no external wait. v1 is gated on L2.

- **`PRODUCT_PROMISING`** — the primary metric clears 1.00%/month, NW t ≥ 2.0,
  the sign-flip placebo is indistinguishable from 0, momentum **dies** under
  orthogonalisation while overhang's t survives, and the sign is stable in at
  least 2 of the 3 eras tested.
- **`FAILED_VARIANT`** — the sign-flip placebo **also pays** (it is drift, i.e.
  momentum again, not disposition) **OR** momentum survives orthogonalisation
  (it was momentum in costume). **Either clause alone closes it**, whatever the
  primary metric did.
- **`CONDITIONAL`** — clears the primary metric but fails an era-stability or
  floor check.
- **Crash override** and contamination clause as in TRIAL-DRAFT-A §5.

**Amendment 1 (2026-09-13, written BEFORE the registered read, after run 1 and one smoke):**
- **`FAILED_VARIANT`** — the primary metric's net block-mean over the registered slice
  (1995-2024, 60-month warm-up) is **≤ 0**, whatever the falsifiers did — the same clause
  TRIAL-DRAFT-A §5 carries, which v0 omitted because its CONDITIONAL clause assumed the primary
  had cleared. What was seen before this was written: run 1's +0.40%/mo on a construction that
  warmed the overhang at 24 months and started in 1990 (not the registered construction), and a
  5-second smoke under the registered construction on 2019+ × 200 names at −0.40%/mo over 71
  blocks (`C_falsifiers --smoke`). Neither is the registered read. The clause is symmetric with
  the family's and adds no new way for the book to pass.

**Amendment 2 (proposed, UNSIGNED) — 2026-09-13: v1 names ONLY the input.**

§8 forbids swapping the event sign inside this registration and says the swap is "a
separate amendment naming only the input". This is that amendment. It is **UNSIGNED**,
nothing has been run on it, and no job calls the v1 builder
(`test_night_first_books_replay.test_the_v1_sign_is_not_wired_into_any_book_yet` fails
if one starts to).

**What changes, in one sentence.** The conditioned universe is currently split by
`v0: sign(numup − numdown)`, the IBES monthly consensus revision at `statpers`. v1
replaces it with `sign of the [−1,+1] session CRSP-daily return around the earnings
announcement`. Nothing else moves: the Grinblatt-Han overhang recursion, its 1,260-session
(60-month) window, the top-tercile cut, k = 30, the unconditioned twin, the $3M primary
and $10M secondary floors and the flat 25 bps ruler are v0's, unchanged, and v1 is built
by calling v0's own `book_c_overhang` rather than a second implementation.

**Why the input is wrong today, stated as the reason rather than as a preference.**
Frazzini (JF 2006) conditions on the **announcement-window return**, which is the market's
own reaction; a revision count is a proxy for it that nobody in that literature uses. §0's
scope-aware claim is that the conditional question was never asked — asking it with a
different conditioner than the paper's is asking a third question.

**The input, and the evidence it exists** (probe receipt
`backend/data/optimus/night_factory_2026-09-13/probe_announcement_dates.json`, which names
every table read including the ones that did not help):

| | |
|---|---|
| table | `backend/data/optimus/wrds/bulk/ibes__act_epsus.parquet` |
| column | `anndats` (the announcement date), filtered `pdicity == 'QTR'`, `measure == 'EPS'` |
| PIT stamp | `actdats` — when the row entered IBES, **not** the announcement date |
| rows 1990-2024 | **866,372** over **35** years (min 17,327 in a year, max 32,768) |
| distinct IBES tickers | 22,759; **92.6%** of rows sit on a ticker `link_ibes_crsp` knows |
| link to permno | `link_ibes_crsp.parquet` (ticker → permno with `sdate`/`edate`, 37,662 rows) |

Rejected, and why, so the choice is reviewable: `compustat_fundq.parquet` carries `rdq`
and is 92.9% non-null but **starts 2013-02-12** and cannot reach 1990; the full
`bulk/comp__fundq.parquet` (2.13M rows, 648 columns) does carry `rdq` further back but is
gvkey-keyed and needs `link_ccm`, and it is kept as the **cross-check**, not the input;
`ibes_consensus_monthly*.parquet` carries `statpers` only, which is exactly why v1 needs a
different table.

**The PIT rule this forces, and it is not the obvious one.** `actdats − anndats` has a
**median of 0 days and a 95th percentile of 91**. "Usable from the month after the
announcement" is therefore true for the median row and **false for the tail**. v1 attributes
a sign to the month it became **knowable** — `max(the +1 session, actdats)` — and the
selection that reads it happens at that month's close, so the earliest return the sign can
touch is the following month's. A window that runs off either end of a name's own tape is
**dropped, not truncated** (a two-session window and a three-session window are different
measurements). Two announcements knowable in one month keep the later one, because the
close knows both.

**What this amendment does NOT do.** It does not touch the overhang, the tercile, k, the
twin, the floors, the cost ruler, the primary metric, the falsifiers or Amendment 1's ≤ 0
clause. It creates **no new way for the book to pass**: v1 is a second reading of the same
hypothesis, and if it is signed, the v0-vs-v1 comparison stays what §3 already calls it —
**reported, never deciding**. A v1 that pays where v0 did not is a finding about the
conditioner's input and is not a promotion; the family's declared size of four does not
change, because v1 replaces v0's primary rather than adding a fifth.

**What signing it authorises:** one historical read on the registered construction
(60-month warm-up, 1995-2024, $3M primary with the $10M cell beside it), queued as a night
job, with the same two falsifiers re-run on the v1 sets.

## 6. Frozen parameters

The `Strategy` object `disposition_overhang_conditioner_v0` as
`scripts/seed_first_books.py` constructs it, hashed at the registration commit.
Also frozen: the Grinblatt-Han formula above; `T = 1260`; the top **tercile**
cut; the v0 IBES-revision-sign definition; k = 30; the $3M primary and $10M
secondary floors; a 3-month hold with monthly review.

## 7. Corpse-check result

Run 2026-09-12 against **358 prior experiments**:

```
PASS   (n_required 146, n_available 653, smallest resolvable effect 0.47pp)
R13e and R13f do not fire on a `REANALYSIS` purpose; the parent (`TRIAL-H5`) and its window are declared anyway
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

- **No claiming the pooled H5 result was "really" this conditional result.**
  H5 is closed on its own terms and this trial cannot reopen it.
- No dropping the sign-flip placebo or the momentum control because the primary
  metric alone looks good. They are triggers, not decorations.
- No swapping the event-sign input (v0 → v1) inside this registration. That is
  a separate amendment naming only the input.
- No reporting the conditioned leg's absolute return as an alpha: the whole
  claim is a DIFFERENCE against the unconditioned book.
- No `RESEARCH_CLAIM` from this registration alone.

## 9. Registry

`rule_experiments` row `disposition-overhang-conditioner-v0`, **not yet
written**.
