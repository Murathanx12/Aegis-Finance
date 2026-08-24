# FINDING 2026-08-24 — the holding-period question, answered with costs

**Licence:** `PRODUCT_EXPERIMENT`. This is a historical replay, post-hoc, over
one window, with 516 policies tried. **It is not an alpha claim** and may not be
cited as one — `RESEARCH_CLAIM` needs preregistration, MDE, multiplicity control
and a holdout, and none of that was done here. What it IS: a measured answer to
a question that had only ever been answered from memory.

**Receipt:** `backend/data/optimus/portfolio_farm/farm_holding_2013_2024.json`
(every policy, every metric, every null draw).
**Engine:** `backend/services/portfolio_farm/` · **Runner:**
`python -m scripts.portfolio_farm_run --preset holding --start 2013 --end 2024`

---

## The question

> "We talked about a case with Micron and how buying and selling it every day
> was creating so much profit than other."

Nobody had ever charged that intuition for its trading. So: make the holding
period a searched axis, run it against costs, and run it against chance.

## The world it was measured in

| | |
|---|---|
| Data | CRSP daily (`crsp.dsf`), 2013-2024, 3,020 sessions x 6,894 PERMNOs |
| Universe | 500 most liquid eligible names at each formation date, trailing dollar volume, price >= $5, real trade that day |
| Book | 12 names, equal weight, 20% single-name cap, $10,000 start |
| Execution | decide at the close of day `i`, **fill at the open of day `i+1`** |
| Costs | 5 bps commission + 1 bp slippage one way (**12 bps round trip**) |
| Dividends | credited as CASH (`ret - retx`), never free-reinvested |
| Delisting | a holding gone 5 sessions is resolved at **-30%** (declared, and a sensitivity axis) |
| Benchmark | CRSP value-weighted market, buy and hold, from the pinned Fama-French file |

## The answer

12-1 momentum, `top_k=12`, by rebalance frequency:

| hold | net terminal | turnover/yr | frictionless twin | **cost of speed** | clears both nulls |
|---:|---:|---:|---:|---:|:--|
| **1 day** | $36,623 | 45.5x | $49,782 | **-$13,159 (-26%)** | YES |
| **5 days** | $38,184 | 21.1x | $44,027 | -$5,843 (-13%) | YES |
| 21 days | $13,473 | 10.2x | $14,436 | -$963 (-7%) | no |
| **63 days** | **$38,815** | 4.8x | $40,083 | -$1,268 (-3%) | YES |
| 126 days | $16,802 | 3.1x | $17,151 | -$349 (-2%) | no |
| 252 days | $32,030 | 1.8x | $32,425 | -$395 (-1%) | YES |

**Market, buy and hold: $39,951.**

### Three things follow, and the third is the uncomfortable one

**1. Trading daily is not where the money is.** It is the WORST of the three
frequencies that clear their nulls once costs are paid, and it pays 26% of its
terminal wealth for the privilege. Frictionless it looks best ($49,782); net it
is $2,192 behind quarterly rebalancing. The Micron intuition is real and it is
a frictionless intuition — the gap between the two columns is exactly the part
that was never charged for.

**2. The cost of speed is measurable and steep.** 45x annual turnover at 12 bps
round trip is ~2.7%/yr of drag, which compounds to a quarter of the account over
twelve years.

**3. NOT ONE of these beat simply owning the market.** The best net policy is
$38,815 against the market's $39,951. Momentum at 12 names clears CHANCE
comfortably and still does not clear SPY-equivalent. That is the honest headline
and it is consistent with the programme's standing position: **demonstrated
independent edge remains 0%.**

## Why "clears both nulls" is the column that matters

The first version of this table had one null — `random`, re-drawn at every
formation date — and momentum sat at the 100th percentile of it at every
holding period. That was mostly an artefact:

* `random` re-ranks the universe daily, so at `hold=1` it turns over **492x/yr**
  and pays **29.5%/yr** in costs. Its median terminal collapses to $1,069.
* 12-1 momentum's ranks barely move day to day: **45x/yr**, 2.7%/yr.

Beating that null at a short holding period can mean nothing more than "traded
less than a coin flip would". So a second null was added —
`random_persistent`, ONE fixed random 12-name basket held for twelve years,
near-zero turnover — and the bar is now the 90th percentile of **both**.
`reversal_1m` clears the churning null at `hold=1` (100.0) and fails the
persistent one (5.0), which is precisely the distinction the single null hid.

## The result nobody asked for, which may be the most important one

**At 12 names, the rebalance PHASE alone swings terminal wealth by 3x.**
`hold=21` returned $13,473 and `hold=63` returned $38,815 — the same signal, the
same universe, the same costs, differing only in which sessions were chosen as
formation dates. And chance at these settings spans **$473 to $85,419** across
492 draws.

A 12-name book's terminal wealth is dominated by idiosyncratic path variance.
That has a direct consequence for the arena: **terminal wealth on ONE path
cannot rank selectors at k=12.** The next question is not "which signal wins" —
it is "at what breadth does selection become measurable at all". The `breadth`
preset exists for exactly that and has not been run.

## Known limitations, stated rather than discovered later

* **One window, 2013-2024.** Twelve years, one regime-ish. The pre-2013 CRSP
  pull lacks `openprc`/`retx`/`shrout`, so the next-open convention is not
  executable before 2013 — the loader REFUSES those years by name rather than
  silently switching to close-to-close. Widening the window is a WRDS re-pull.
* **Long only, no shorts, no leverage, no borrow.** `reversal_1m` losing is a
  statement about a long book of last month's losers, not about the anomaly.
* **Delisting is an assumption** (-30%), because `crsp.dsf` carries no delisting
  returns. Re-run at 0.0 and -1.0 to bound it; nobody has yet.
* **Costs are flat.** No market impact beyond 1 bp, which flatters the fast
  policies — the direction that matters here, and it still did not save them.
* **516 policies were tried.** The best of 516 is high because 516 is large.
