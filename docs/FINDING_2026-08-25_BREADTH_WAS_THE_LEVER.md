# FINDING 2026-08-25 — breadth was the lever, and the 12-year breadth verdict was itself a regime

## RESULTS SCOREBOARD

| | |
|---|---|
| best historical net strategy vs market | `mom_12_1 k=20 h=5` — **4.41x** the market over 1993-2024, `t` 1.99, **does not resolve** (61 yrs needed) |
| best forward paper strategy | unchanged — none promoted |
| independent selector count | **1** (unchanged — `profit_roe` is a CANDIDATE, one test short: §3) |
| farm candidates tested / promoted | 18 signals x 7 breadths x 4 windows / **0 promoted** |
| new actionable finding | **Nothing in the farm beats a book of the hundred oldest listings, resolvably.** `profit_roe` clears it by +1.53%/yr and needs 126 years; `mom_12_1` at k=20 clears it by +9.23%/yr and needs 72. The near-miss against the MARKET (31.2 vs 30.88 years) does not survive the sharper question |
| external execution drag | n/a — nothing seeded |
| LLM spend | $0 this batch (farm is numerical) |

**RESULT IMPROVEMENT: YES, and it is a measurement improvement, not a
demonstrated edge.** Nothing here is promotable and nothing here is alpha.

## 1. The 12-year breadth verdict was wrong, and wrong in the informative direction

`docs/FINDING_2026-08-25_THIRTY_TWO_YEARS_DID_NOT_RESOLVE_IT.md` closed on the
single queued question: does the excess fall faster than tracking error as `k`
rises? On 2013-2024 it did — `mom_12_1` slope **-0.40**, peak `t` at the
narrowest book — and the honest reading was that momentum is a handful of large
winners rather than a cross-sectional effect.

**On 1993-2024 that reverses.**

    signal          k     median$     te%  excess%      t  mde80%  yrs_need
    mom_12_1        5     116,997    45.2    10.04   1.23   22.80      159
    mom_12_1       10     614,277    34.4    10.82   1.75   17.33       79
    mom_12_1       20     971,252    27.5     9.87   1.99   13.86       61   <- peak t AND peak $
    mom_12_1       30     759,837    24.1     7.96   1.84   12.12       72
    mom_12_1       50     696,872    19.7     6.39   1.81    9.91       74
    mom_12_1      100     623,712    14.4     4.67   1.81    7.24       75
    mom_12_1      200     391,074     8.7     2.16   1.37    4.41      127
      -> slope +0.02 over k=10..50, peak t at k=20: SCALES with breadth

The best book by **terminal wealth** and by **`t`** is the same book, and it is
not the narrowest one. k=20 beats k=10 on both — $971k vs $614k — while
tracking error falls from 34.4% to 27.5%. The 12-year window said the opposite
because 2013-2024 was a mega-cap decade in which concentration paid.

**This is the fifth time the instrument moved the answer more than the strategy
did, and the second time in two days that a verdict flipped when the window
widened.** The rule that keeps earning itself: *a farm number read off one
window is a regime, not an edge.*

**It does not rescue resolvability.** k=20 needs 61 years against 30.88
available. Breadth bought 79 → 61; it did not buy 79 → 30.

## 2. Breadth cleanly separates a signal from a description of a decade

The same diagnostic run on `liquid` — which carried the best `t` on the
12-year grid and turned out to be a FAANG list — does the opposite:

    liquid          5     688,682    23.8     8.08   1.89
    liquid         10     430,885    16.7     4.71   1.56
    liquid         20     156,169    12.7     0.45   0.20
    liquid         30     126,598    10.1    -0.78  -0.43
    liquid         50     179,352     7.5    -0.13  -0.09
      -> slope -1.11 over k=10..50, peak t at k=10: does NOT scale

**`liquid`'s entire excess is ten names.** By k=20 it is gone; by k=30 it is
negative. The holdings census said the same thing in words (MSFT 123/124
samples, GOOG 87, AAPL 81); the breadth curve says it in a number, without
anyone having to look at the tickers.

So the test works as a discriminator, and that is worth as much as any single
verdict it produced: **breadth is now the cheap first screen on every farm
candidate, run before the holdings census rather than after it.**

## 3. `profit_roe` — reached its detection threshold against the market, and not against the right benchmark

    signal          k     median$     te%  excess%      t  mde80%  yrs_need
    profit_roe      5     122,639    17.4    -0.60  -0.19    8.75        -
    profit_roe     10     430,447    11.2     2.24   1.12    5.62      194
    profit_roe     20     481,001     8.4     2.51   1.67    4.21       87
    profit_roe     30     357,552     7.2     1.55   1.19    3.65      172
    profit_roe     50     524,542     6.2     2.77   2.47    3.14       40
    profit_roe    100     492,811     5.1     2.56   2.79    2.57     31.2   <- window is 30.88
    profit_roe    200     437,810     4.2     2.10   2.78    2.11     31.2
      -> slope +0.69 over k=10..50, peak t at k=50: SCALES with breadth

At k=100 the observed excess is **2.56%/yr** and the effect this window can
detect at 80% power is **2.57%/yr**. It misses by **0.01 percentage points —
about four months of history.**

That is the closest anything in five months of this project has come to being
resolvable, and it arrives from the first data source that is not a column of
`crsp.dsf`.

Four properties that make it worth the next session rather than a curiosity:

1. **The breadth curve is monotone in `t`** (1.12 → 1.67 → 2.47 → 2.79) and
   flattens rather than turning over. That is the Grinold shape. `liquid` and
   `size_large` do not have it; `mom_12_1` has a weak version of it.
2. **It keeps its sign and rough size in both halves** — 1993-2008 excess
   +2.59%, 2009-2024 +1.82%. See §4: almost nothing else does.
3. **The holdings are recognisable quality and rotate**: CL 67/124, AVP 45,
   MCO 39, CLX 37, AZO 28, LMT 28, UST 27, MHP 26, YUM 25, HD 24, ORLY 22,
   WU 21. Zero overlap with the momentum book or the FAANG book.
4. **Its excess is not one crisis.** Top-10 sessions spread over 1997, 2000 x6,
   2002, 2011, 2020 — versus `value_bm`, whose ten best sessions are seven days
   in autumn 2008.

### The test that could have killed it, and did not

**At k=100 a book holds 20% of a 500-name universe against a CAP-WEIGHTED
benchmark, so part of that 2.56% could be the equal-weight/size tilt rather
than ROE.** That is the obvious way this result dies, so it was run before the
result was written up. Same window, same construction, three nulls:

    k=100                    excess%     t   slope k=10..50
    random                     -4.35  -5.45      -1.45
    random_persistent          +0.25  +0.33      -0.80
    equal                      +1.12  +1.12      -0.38
    profit_roe                 +2.56  +2.79      +0.69

**Every null decays with breadth. `profit_roe` is the only signal on the entire
grid whose `t` rises.** The construction does not merely fail to produce the
monotone shape — it produces the opposite one, in all three nulls, including the
turnover-matched `random_persistent` that is the correct control for a k=100
book. Against that control `profit_roe` adds **+2.31%/yr**.

So the near-resolvable result is not "wide books beat a cap-weighted index".

### The confound was measured, and it takes most of the result

`equal` at k=100 returns **+1.12%/yr** — and `equal` is not equal-weighting, it
is *the hundred lowest permnos*, i.e. the hundred oldest surviving listings.
High-ROE names in a large-cap universe **are** old names: CL, CLX, AVP, LMT,
UST and MHP are among the most venerable listings in CRSP. Quality and listing
age are correlated by how the industry is built, not by accident.

Comparing each book's excess-over-market cannot settle that, because the two
excesses are not independent — they share the market, the construction, and
some holdings. The quantity that decides it is the tracking error of the
DIFFERENCE, and nothing in the farm computed one, because every power check
compared to the cap-weighted market. So `scripts/portfolio_farm_paired_power.py`
was written and run:

    1993-2024, same construction, phase matched pairwise, median phase

    comparison                              te%   excess%     t   mde80%  yrs   resolves
    profit_roe vs equal        k=100       6.11     +1.53  1.39     3.08  126   0/5
    profit_roe vs random_pers. k=100       5.33     +2.22  2.32     2.68   45   0/5
    mom_12_1   vs equal        k= 20      27.92     +9.23  1.84    14.07   72   0/5

**`profit_roe` beats the age book, and cannot be shown to.** The sign is stable
across all five rebalance phases (+1.10% to +1.56%), so it is not a calendar
artefact — but at 1.53%/yr against a 3.08%/yr detection threshold it needs 126
years. Against the market it needed 31.2 and the window is 30.88; against the
age book the target moves back out by a factor of four.

Roughly **40% of the k=100 excess over the market is matched by a book selected
on listing age alone**, and the remainder is not resolvable on the data that
exists.

**The incumbent is in exactly the same position.** `mom_12_1` at its best
breadth clears the age book by +9.23%/yr and needs 72 years. So this is not a
verdict about characteristics versus price — it is the same verdict twice, and
the age book is a harder benchmark than the farm has ever used.

`profit_roe` is a **candidate for a second selector**, promoted from
"curiosity" and not to "selector".

### Pairing was the HARDER test, which was not the expectation

The script was written asserting that a paired comparison cancels the drag both
books share and is therefore easier. Its own first three runs refute that:

    profit_roe k=100    te vs market  5.10%    te vs equal   6.11%
    mom_12_1   k= 20    te vs market 27.50%    te vs equal  27.92%

Pairing cancels the shared market exposure and **adds the difference in
holdings**, and for two books drawn from one 500-name universe the second term
is the larger. Which way it goes is a fact about overlap, not a property of
pairing — so the script now measures both tracking errors and prints them side
by side instead of asserting which is easier.

The claim survived from writing the docstring to reading the output, which is
the same distance every other unmeasured claim in this project has travelled
before being caught.

## 4. Split-half stability: every price signal flips or halves; two do not

1993-2008 vs 2009-2024, k=10, excess vs market:

    signal          1993-2008   2009-2024   verdict
    mom_12_1          +16.72       +8.26    halves
    mom_6_1           +17.02      +10.55    halves
    mom_12_0           +9.52       +6.19    halves
    mom_3_1            +9.65       -6.74    SIGN FLIP
    reversal_1w        +6.43       -5.81    SIGN FLIP
    trend_200          -3.72       +7.82    SIGN FLIP
    liquid             +3.42       +6.45    grows (the mega-cap decade)
    value_bm           -7.88       -0.14    negative in BOTH
    equal (null)       +7.60       +0.66    collapses
    size_large         +0.89       +1.26    HOLDS
    profit_roe         +2.59       +1.82    HOLDS

Neither half resolves anything — 0 of 15 non-null signals clear their MDE in
either. But **sign stability is a separate question from significance, it is
free, and it orders the library differently.** The two signals that hold are
the two with the lowest tracking error on the board, and one of them is the
non-price one.

`mom_3_1`, `reversal_1w` and `trend_200` changing sign across halves is the
cleanest available argument that the short-horizon price signals are fitting
regimes. That is consistent with the standing Holm-surviving result that
short-horizon winner-chasing is an anti-signal.

## 5. `value_bm` is negative in value's own era — the construction, not the signal

`value_bm` returns **-7.88%/yr over 1993-2008**, which contains the entire
documented run of the value premium. A signal cannot contradict thirty years of
literature; a *construction* can.

The breadth curve says which: excess is **-4.19% at k=5, -0.94% at k=30, -0.78%
at k=200.** The damage is monotone in concentration. The ten highest
book-to-market names in a large, liquid universe are not "value" — they are
**large caps in distress whose book value has not been written down yet**, and
the published premium is measured on quintiles and deciles of a broad universe,
never on the extreme ten.

Its ten best sessions are 2008-09-16, 09-18, 09-30, 10-01, 10-10, 10-14, 11-24,
2009-03-23, 08-05 and 2020-11-09 — seven days in the autumn of 2008 plus the
vaccine-announcement day. That is a distress book being marked back up, not a
value premium being earned.

**Status: `FAILED_VARIANT`, not `MECHANISM_REJECTED`.** What is closed is
"top-10 by raw book-to-market in a top-500 liquid universe". Book-to-market as
a *sorted quantile* has never been tested here and is a different object.

## 6. What is settled and what is not

**Settled — the breadth-monotone shape belongs to `profit_roe`, not to wide
books.** All three nulls have NEGATIVE slope and peak at k=10 (`random` -1.45,
`random_persistent` -0.80, `equal` -0.38). The construction produces the
opposite shape from the one `profit_roe` has.

**Settled — the construction has a measured cost floor.** The `random` null is
significantly negative at every breadth (-4.35%/yr, t=-5.45 at k=100). Every
`excess%` in every farm table should be read against that floor rather than
against zero.

**Settled — neither `profit_roe` nor `mom_12_1` beats an age-selected book
resolvably.** 126 years and 72 years respectively. See §3.

**Not settled — whether the residual over age is real.** +1.53%/yr with the
sign stable across five phases is suggestive and is not evidence.

**Not settled — anything out of sample.** Nothing here is a holdout.
`profit_roe` was registered on 2026-08-25 and evaluated on the same 32 years
that were pulled in order to evaluate it. `value_bm` and `profit_roe` are two
characteristics tried, and the breadth grid adds 63 cells of search that no
multiplicity control here has priced.

## 7. What this licenses

- `PRODUCT_EXPERIMENT`: `profit_roe` at k=50-100 may be built and paper-traded
  under a frozen contract. No significance gate applies, and the exploration
  licence is the whole point — 126 years to demonstrate does not forbid
  running it in paper, it forbids calling the result alpha.
- `CAPITAL_CANDIDATE`: nothing. Not `mom_12_1` at k=20 (61 years vs market, 72
  vs the age book), not `profit_roe` (126 years vs the age book).
- `RESEARCH_CLAIM`: nothing. White's reality check over the 18-signal table
  gives p=0.168 for the best row on 32 years, and the breadth grid adds
  14 more cells of search that no multiplicity control here has priced.

## 8. Four defects found and fixed while doing this

**1. The breadth receipt clobbered itself.**
`farm_breadth_power_{start}_{end}.json` was keyed on the window alone, so a run
with `--signals a b` silently deleted rows a previous run had written for
`--signals c d`. Two batteries ran overnight and only the second one's signals
survived in the receipt; the first four existed solely in a log file. Now
merges on `(signal, top_k)` and REFUSES to merge across a different holding
period, sizing, reduction or `clean_max_k` — a table that mixes constructions
is worse than one that is visibly partial. **This is the standing rule (*a
headline number belongs in a receipt, never prose alone*) failing through the
receipt rather than through the prose.**

**2. The breadth verdict called two loss-making signals "SCALES with breadth".**
`value_bm` runs `t` -0.77 → -0.39 over k=10..50 and `low_vol` -1.09 → -0.84.
Both slopes are positive, both peaks sit away from the narrowest book, so both
passed — while losing to the market at every breadth on the grid. A rising `t`
on a NEGATIVE excess is a loss being diluted, not an edge being diversified,
and the two produce an identical slope. The verdict now requires a positive
excess to be applicable at all. **Exactly two signals are scored as scaling
after the fix: `profit_roe` and `mom_12_1`.**

**3. The paired script asserted pairing is the easier test.** It is not — see
§3. Written into the docstring and into the conclusion line, refuted by the
script's own first three runs. Now measured and printed rather than assumed.

**4. `monday_gate_check` reported a FAIL that no state of the system could
clear.** "seed migration → book-v1: 0/9 stamped" has been red for weeks.
`engine.status()` never emitted `fingerprint_scheme`; the gate reads it off
that payload, so the count could only ever be 0/N. Verified against production
2026-08-25 — the keys served per book were `last_nav, nav_rows, positions,
seeded, seeded_at, validation_status`, and nothing else.

The seeds' actual migration state was never failing. It was **invisible**, and
a check with no input reported the absence as a failure.

Fixed on both sides, and the second matters more: `status()` now serves
`fingerprint_scheme`, `book_fingerprint` and `composite_version`; and the gate
now reports **CANNOT DETERMINE** when no book carries the key, per the standing
rule that *guards derive their inputs or refuse*. A red line that cannot go
green teaches a reader to skim red lines, which is worse than the missing check.
