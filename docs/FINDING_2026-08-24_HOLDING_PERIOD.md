# FINDING 2026-08-24 — the holding-period question, and the three instrument defects that had to be fixed before the answer meant anything

> **SUPERSEDED IN PART, 2026-08-25 — every dollar figure below was computed
> before the split-adjustment fix.** `replay` carried SHARE COUNTS and marked
> them at raw `abs(prc)`, so every split in the sample was booked as a return.
> One reverse split (permno 85035, 2015-01-02, cfacpr 0.25 -> 1.00) was worth
> +36.34% of single-day "excess" and was the largest session in the whole
> series for both momentum signals. See
> `docs/FINDING_2026-08-25_THE_SAMPLE_YOU_CAN_ACTUALLY_GET.md` and
> `backend/tests/test_portfolio_farm_split_adjustment.py`.
>
> Re-measured on the same policy and window:
>
> | | before | after |
> |---|---|---|
> | terminal median (5 phases) | $77,002 | **$85,482** |
> | market, same warmup | $38,960 | **$39,951** |
> | 2013-2018 vs market | 1.01x | **1.00x** |
> | 2019-2024 vs market | 1.75x | **2.07x** |
> | phase spread | 3.75x (k=12 grid) | **2.12x** (this policy) |
>
> **Every CONCLUSION below survives, and the one-regime one is stronger.** The
> bug was worth about -0.3%/yr net to this policy, because reverse splits gave
> and forward splits took. What it did change is the RANKING of the signal grid
> — `liquid` went from t=0.26 to t=2.55 — because forward splits are commonest
> among large liquid names.


**Licence:** `PRODUCT_EXPERIMENT`. Historical replay, post-hoc, one window,
~1,200 policies tried. **Not an alpha claim** and may not be cited as one.

**Receipts** (`backend/data/optimus/portfolio_farm/`):
`farm_subperiod_candidate.json` — **read this one FIRST; it is the check that
largely takes the candidate back** · `farm_breadth_phase_2013_2024.json` ·
`farm_phase_measured_delist.json` (holding period x phase) ·
`farm_holding_2013_2024.json` · `farm_breadth_2013_2024.json` ·
`farm_delisting_2013_2024.json`.
**Engine:** `backend/services/portfolio_farm/` · **Runner:**
`python -m scripts.portfolio_farm_run --preset phase --start 2013 --end 2024`

> **THIS FILE WAS REWRITTEN THREE TIMES IN ONE NIGHT.** Each rewrite was forced
> by a measurement, and the sequence is the point:
>
> 1. **"$38,815, `hold=63` wins."** That was the MAXIMUM of the rule's
>    rebalance-phase distribution, whose median is $16,633. The calendar,
>    reported as the strategy.
> 2. **"$35,228, loses to the market."** True under a **declared -30% delisting
>    assumption** that had never been varied. Varying it moved the same rule
>    across an 18x band that straddled the benchmark.
> 3. **The delisting data was already on disk.** `crsp__dsedelist.parquet`, in
>    the WRDS bulk pull, unjoined. With the ACTUAL delisting returns the answer
>    is below — and it is not what any earlier version said.
>
> Then the sub-period check showed the whole thing is **1.01x against the market
> over 2013-2018** and 1.75x over 2019-2024 — one regime, not an edge.
>
> The instrument was wrong four times, and each error moved the result by more
> than the result itself. **That** is the finding to remember, not the number.

---

## The question

> "We talked about a case with Micron and how buying and selling it every day
> was creating so much profit than other."

Nobody had ever charged that intuition for its trading.

## The world it was measured in

| | |
|---|---|
| Data | CRSP daily (`crsp.dsf`) 2013-2024, 3,020 sessions x 6,894 PERMNOs, plus `crsp.dsedelist` |
| Universe | 500 most liquid eligible names at each formation date (trailing dollar volume), price >= $5, real trade that day |
| Book | 12 names, equal weight, 20% single-name cap, $10,000 start |
| Execution | decide at the close of day `i`, **fill at the open of day `i+1`** |
| Costs | 5 bps + 1 bp slippage one way (**12 bps round trip**), plus a round-trip cash reserve so the book cannot be fully invested AND pay commission |
| Dividends | credited as CASH (`ret - retx`), never free-reinvested |
| Delisting | **MEASURED** per event from `crsp.dsedelist` (97%+ coverage); the declared -30% is only the fallback |
| Benchmark | CRSP value-weighted market, buy and hold, pinned Fama-French |

## THE ANSWER

12-1 momentum, k=12, net of costs, delisting measured, median across rebalance
phases:

| hold | phases | **median** | min | max | phase spread |
|---:|---:|---:|---:|---:|---:|
| **1** | 1 | **$80,943** | — | — | 1.00 |
| **5** | 5 | **$80,825** | **$45,458** | $92,122 | 2.03x |
| 21 | 7 | $23,601 | $15,190 | $33,465 | 2.20x |
| 63 | 7 | $28,358 | $19,204 | $62,360 | 3.25x |
| 126 | 7 | $15,343 | $12,436 | $22,042 | 1.77x |
| 252 | 7 | $25,863 | $23,630 | $42,048 | 1.78x |

**Market, buy and hold: $38,960.**

At `hold=5` **every phase beats the market** — the worst alignment returns
$45,458. Both leaders clear the 90th percentile of BOTH nulls at 100.0/100.0.

### The Micron intuition is correct, and costs do not overturn it

| hold | frictionless | net | costs | turnover |
|---:|---:|---:|---:|---:|
| 1 | $92,349 | **$80,943** | $9,076 | 45.2x/yr |
| 5 | $92,986 | **$85,975** | $5,062 | 20.8x/yr |
| 63 | $63,772 | $62,360 | $1,412 | 4.8x/yr |
| 252 | $37,164 | $36,766 | $391 | 1.8x/yr |

Faster is better gross AND net. Costs take ~12% of the frictionless result at
daily frequency — real, and much smaller than the edge it buys. **Trading the
signal fresh is worth more than the spread it costs**, at $10,000 and on the
500 most liquid names.

## AND NOW THE PART THAT MATTERS MORE THAN THE HEADLINE

(The k=12 book, which is where the holding-period sweep ran. The breadth sweep
below finds a better one at k=10 and it tells exactly the same story.)

| | `mom_12_1 / h=1 / k=12` | market |
|---|---:|---:|
| terminal wealth | **$80,943** | $38,960 |
| CAGR | **21.15%** | 13.55% |
| volatility | 41.8% | 17.8% |
| **Sharpe** | **0.63** | **0.72** |
| **Sortino** | **0.63** | **0.67** |
| **Calmar** | **0.37** | **0.40** |
| max drawdown | **-57.0%** | -34.2% |
| longest underwater | **927 sessions (3.7 yrs)** | 530 (2.1 yrs) |
| information ratio | 0.39 | — |

**It doubles terminal wealth and is WORSE on every risk-adjusted measure.**
Sharpe, Sortino and Calmar all favour the market. This is not risk-adjusted
alpha; it is more risk, taken deliberately, which paid over this window. It
behaves roughly like a levered market position with a modest IR of 0.39.

Which is exactly why CLAUDE.md requires that **every ranked comparison names the
objective it was computed under**:

> **Under terminal wealth it is 2.08x the market. Under any risk-adjusted
> objective it is worse than the market.**

For the DECLARED `extreme growth` personality that is the right answer. For
`balanced` or `preservation` it is not, and no amount of terminal wealth makes a
57% drawdown and 3.7 years underwater the right answer for them.

## The three instrument defects, each worth more than the strategy

### 1. Rebalance phase — worth up to 3.75x

Formation dates are set by an arbitrary alignment. `hold=63` returned $62,360 at
one offset and $19,204 at another: same signal, same universe, same costs.
`Policy.phase_offset` is now part of the identity and `farm.across_phases`
reports the MEDIAN with the spread beside it. **A rule whose phase spread is
wider than its edge has not been shown to have one.**

### 2. The delisting assumption — worth 18x, and the data was already here

`crsp.dsf` carries no delisting returns, so the simulator applied a declared
-30%. The sensitivity sweep gave $4,290 / $35,228 / $83,649 at -1.0 / -0.30 /
0.0 — straddling the benchmark. Then `crsp__dsedelist.parquet` turned out to be
sitting in the WRDS bulk pull, unjoined. Measured over 3,089 real events in this
window:

| code family | n | `dlret` median | mean |
|---|---:|---:|---:|
| **2xx mergers** | 1,962 | **+0.0004** | +0.0089 |
| 3xx exchange | 13 | +0.0053 | +0.0347 |
| 4xx liquidation | 223 | +0.0005 | -0.0074 |
| **5xx dropped / performance** | 891 | **-0.2000** | -0.2444 |
| all | 3,089 | **0.0000** | -0.0636 |

60.5% of delistings return at or above zero. A merged shareholder receives the
deal consideration, so -30% was the wrong number for two thirds of the
population — and momentum is *especially* exposed, because **12-1 momentum
systematically selects acquisition targets** (a target runs up into its
announcement). 35 exits over twelve years, each ~1/12 of the book: a wrongly
imposed -30% compounds to destroying 57% of terminal wealth.

`dlstcd = 100` means STILL ACTIVE and those rows are excluded — 3,866 of them
against 3,089 real events, so that filter is not a detail.

**With the measured returns the fallback stops mattering**: sweeping it from 0.0
to -1.0 now moves `h=1` only from $83,047 to $76,032 — **1.09x instead of 18x.**
That collapse is the proof the join worked.

### 3. Implicit leverage — silent and recurring

A held name with no open price cannot be sold, and the fill step allocated the
new book against total equity anyway: buying with capital still locked in the
old position, driving cash negative with no borrow cost. `openprc` is missing on
~2.2% of rows, so a 12-name book met one roughly every fourth rebalance.
`min_cash_usd` and `stuck_capital_usd` are now on every receipt.

## Why "clears both nulls" is the column that decides

`random` re-draws every formation date, so at `hold=1` it turns over **492x/yr**
and pays **29.5%/yr** in costs; momentum's ranks barely move, so it turns over
45x. Beating that null at a short holding period can mean nothing more than
"traded less than a coin flip would". `random_persistent` — ONE fixed random
12-name basket held twelve years, near-zero turnover — brackets the other end,
and the bar is the 90th percentile of **both**. `reversal_1m` at `hold=1` clears
the churning null (100.0) and fails the persistent one (0.0), which is exactly
the distinction one null hid.

## Breadth, settled: k=10 is the peak, and every single-phase reading was wrong

Breadth was read three times and the first two were artefacts. `--preset
breadth` sweeps k at ONE rebalance offset, and an offset is worth up to 3.75x,
so a k-ranking read off one phase is a ranking of draws. `--preset
breadth_phase` crosses k with the phase at `hold=5` (a strong alignment) and
benches every (k, sizing) cell against its own nulls — 368 policies:

| k | sizing | median | min across phases | phase spread | phases clearing BOTH nulls |
|---:|---|---:|---:|---:|:--|
| 5 | equal / inv | $33,548 | $14,681 | 3.06x | **2 of 5** |
| **10** | equal | $76,727 | $40,812 | 2.19x | **5 of 5** |
| **10** | **inverse vol** | **$77,002** | **$58,411** | **1.89x** | **5 of 5** |
| 20 | equal / inv | $45,484 / $47,597 | $41,081 / $40,900 | 1.40x | 5 of 5 |
| 50 | equal / inv | $40,615 / $39,054 | $33,367 / $31,038 | 1.31x | 4 of 5 |

**There is an interior optimum at k=10.** Not k=5 (inside chance in 3 of 5
phases) and not k=50 (which the single-phase run had crowned). And the phase
spread narrows monotonically with breadth — 3.06x at k=5 down to 1.31x at k=50
— which is the mechanism stated plainly: **more names average the idiosyncratic
variance down, and past k=20 they also average the signal away.**

k=5 equal-weight and inverse-vol return identical numbers, because a 20% cap
makes a five-name book all-at-the-cap and sizing has nothing left to decide.

## THE CANDIDATE

`mom_12_1 / hold 5d / k=10 / inverse_vol / top-500-liquid / 12 bps round trip`,
all five rebalance phases:

| phase | terminal | CAGR | vol | Sharpe | maxDD | IR |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | $58,411 | 17.57% | 42.8% | 0.55 | -60.9% | 0.30 |
| 1 | $100,556 | 23.58% | 42.6% | 0.67 | -60.0% | 0.44 |
| 2 | $110,419 | 24.65% | 42.4% | 0.69 | -59.9% | 0.47 |
| 3 | $62,604 | 18.32% | 42.7% | 0.57 | -59.6% | 0.32 |
| 4 | $77,002 | 20.59% | 42.6% | 0.61 | -55.9% | 0.38 |
| **median** | **$77,002** | **20.59%** | 42.6% | **0.61** | **-59.9%** | 0.38 |
| **market** | **$38,960** | **13.55%** | 17.8% | **0.72** | **-34.2%** | — |

**Every phase beats the market on terminal wealth** — the worst is $58,411,
still 1.5x — and **every phase is below the market's Sharpe.** The result is
consistent, and so is its price: ~2.4x the market's volatility and a 60%
drawdown.

That is the same sentence the k=12 book gave, now robust across breadth, phase
and holding period:

> **Momentum at this breadth converts more risk into more wealth, at slightly
> worse risk-adjusted efficiency.** Under terminal wealth it is ~2x the market.
> Under Sharpe, Sortino or Calmar it is worse. Right for the DECLARED `extreme
> growth` personality; wrong for `balanced` or `preservation`.

## AND THE SUB-PERIOD CHECK LARGELY TAKES IT BACK

`python -m scripts.portfolio_farm_subperiod` runs the candidate — and its nulls
— independently in each half of the replayable window, at every phase:

| window | median | worst phase | market | ratio (median) | phases clearing BOTH nulls |
|---|---:|---:|---:|---:|:--|
| **2013-2018** | $15,737 | $15,107 | $15,613 | **1.01x** | **2 of 5** |
| **2019-2024** | $33,844 | $26,676 | $19,330 | **1.75x** | **5 of 5** |

**The edge lives almost entirely in the second half.** Over 2013-2018 the
candidate is a coin-flip against buy-and-hold — 1.01x, worst phase BELOW the
market, and inside its own nulls in three phases of five. Over 2019-2024 it is
1.75x with every phase clearing.

So the twelve-year headline is an average of a thing and a nothing, which is
precisely the failure mode this check exists to catch. It does not kill the
candidate — 2013-2018 contains the 2015-2016 momentum unwind and the Q4-2018
drawdown, and six years is a small sample — but it does mean:

> **This is a ONE-REGIME result. It has not been shown to work in a regime where
> momentum was not paying.**

This is NOT a holdout. The candidate was chosen after seeing the whole window,
so neither half is out-of-sample and no significance may be read off the split.
It answers only the cheapest question, and the answer was informative.

**What this promotes to first priority:** re-pulling `openprc`/`retx`/`shrout`
for CRSP **1990-2012**. It was second priority when the question was precision;
it is first now that the question is *whether there is anything here at all
outside 2019-2024*. Three more decades contain the dot-com unwind, the GFC and
the 2009 momentum crash — the regimes that would actually test this.

## THE POWER CHECK, WHICH EXPLAINS EVERY OTHER RESULT AT ONCE

Canon §64 requires a power check **before** any confirmation. The farm ran
~1,700 policies without one. Done afterwards on the leading candidate:

| | |
|---|---:|
| tracking error | **35.7%/yr** |
| standard error of the mean excess | **10.81%/yr** over 10.9 years |
| observed excess | 16.64%/yr |
| **implied t** | **1.54** |
| MDE at 80% power, 5% two-sided | **30.3%/yr** |
| **years needed to resolve the observed effect** | **36** |

**The sample cannot resolve the effect.** Not "the strategy is weak" — the
question was unanswerable with twelve years at this tracking error, before a
single number was computed.

And that one fact IS all four of the other results:

* the **3.75x rebalance-phase spread** — that variance, showing up as calendar
  sensitivity;
* the **1.01x vs 1.75x sub-period disagreement** — the same variance, split in
  half;
* the **bootstrap CI**, which contains zero in every phase (excess +10.9% to
  +16.6%/yr, CIs spanning roughly -10% to +40%, P(excess<=0) = 0.07 to 0.16);
* **White's Reality Check p = 0.126** across the 45 policies in that run — the
  best one does not survive its own search.

Four independent instruments, one underlying quantity. None of them is a defect
in the strategy or in the simulator.

### And it prices the fix exactly

Thirty-six years is what this question needs. **CRSP 1990-2024 is thirty-five.**
The pre-2013 re-pull is not "nice to have for regimes" — it is very nearly the
precise amount of data required, which is why it is the first priority and why
nothing else on the board substitutes for it.

`backend/services/portfolio_farm/bootstrap.py` — `power_check`,
`excess_interval` (stationary block bootstrap, Politis & Romano 1994) and
`reality_check` (White 2000). Run the power check FIRST from now on; a farm row
whose `sample_can_resolve_observed_effect` is False is a row that answered
nothing, whatever it returned.

## What this is, and what it is not

It **is** the first thing in this programme to beat a properly-costed benchmark
on a replay with next-open fills, measured delisting returns and both nulls
cleared in every rebalance phase of the full window. That is worth something: it
is a plausible hypothesis, cheaply produced.

It is **not a finding**, and the power check says why in one line: **t = 1.54,
and the sample would need thirty-six years to resolve the effect it reports.**

It is **NOT** ready for a forward book. The sub-period split above is the
reason: 1.01x against the market over 2013-2018, clearing its nulls in two
phases of five. A rule that only works in the half of history where its factor
paid is not a candidate; it is a hypothesis about regimes. **Do not seed a lane
on this.** The next act is the 1990-2012 pull, not a promotion.

It is **not** alpha:

* **one window, one path, and the two halves DISAGREE.** See the sub-period
  section: 1.01x over 2013-2018, 1.75x over 2019-2024. The pre-2013 CRSP pull
  lacks `openprc`/`retx`/`shrout` and the loader refuses it by name.
  **And that gap is invisible to the machinery that would fix it:**
  `wrds_pull_catchup` skips any table whose parquet EXISTS, so twenty-three
  files that exist with the wrong columns will never be re-pulled by any number
  of catch-up nights. `python -m scripts.wrds_column_completeness` makes it
  visible and exits non-zero; the pull itself spends a credentialed WRDS session
  and stays attended.
* **~1,600 policies were tried.** The best of 1,600 is high because 1,600 is
  large, and nothing here controls for that. The partial defence is that the
  candidate is not a single best row: it clears both nulls in 5 of 5 phases and
  its WORST phase still beats the market. That is a weaker claim than a
  multiplicity correction and a stronger one than a maximum.
* **small k is dominated by idiosyncratic variance** — chance spans
  $473-$85,419 across 492 draws at k=12, and k=5 fails its own nulls in 3 of 5
  phases. The k=10 optimum sits close to that cliff.
* **risk-adjusted it loses to the market**, on Sharpe, Sortino and Calmar alike.
* **the universe rests on a 6,894-PERMNO screened superset — AUDITED, and it
  cannot bind.** The superset admits any permno that ever cleared **$100M per
  month** in 2013-2024. The farm's own 500th-ranked name trades **$76M-$137M
  per DAY**, i.e. $1.6B-$2.9B per month — a **15.4x minimum margin** over the
  inclusion bar (median 20.4x), with 2,770-3,439 names eligible per date against
  a 500-name cut. A name excluded for missing that bar could not have ranked
  into a book on any date. `python -m scripts.portfolio_farm_universe_audit`.
  What this does NOT clear is the `shrcd`/`exchcd` restriction — common stocks
  on NYSE/AMEX/NASDAQ is a DECLARED universe choice, and every farm result is a
  result about that universe.
* **long only, no shorts, no leverage, no borrow, flat costs, no market impact
  beyond 1 bp.** At $10,000 that impact assumption is realistic; at $1,000,000
  it is not.
