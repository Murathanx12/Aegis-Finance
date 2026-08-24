# FINDING 2026-08-24 — the holding-period question, and what phase did to it

**Licence:** `PRODUCT_EXPERIMENT`. Historical replay, post-hoc, one window,
hundreds of policies tried. **Not an alpha claim** and may not be cited as one.

**Receipts:** `backend/data/optimus/portfolio_farm/farm_holding_2013_2024.json`
(516 policies, phase 0) · `..._phase_2013_2024.json` (every rebalance phase) ·
`..._breadth_2013_2024.json` (k = 3..50).
**Engine:** `backend/services/portfolio_farm/` · **Runner:**
`python -m scripts.portfolio_farm_run --preset phase --start 2013 --end 2024`

> **THIS FILE WAS REWRITTEN THE SAME NIGHT.** Its first version reported
> `mom_12_1 / hold 63d` at **$38,815** as the best net result. That number is
> real and it is the **MAXIMUM of that rule's rebalance-phase distribution**,
> whose median is **$16,633**. The first version was measuring the calendar and
> reporting the strategy. What follows is the corrected reading; the correction
> is the more useful finding.

---

## The question

> "We talked about a case with Micron and how buying and selling it every day
> was creating so much profit than other."

Nobody had ever charged that intuition for its trading.

## The world it was measured in

| | |
|---|---|
| Data | CRSP daily (`crsp.dsf`), 2013-2024, 3,020 sessions x 6,894 PERMNOs |
| Universe | 500 most liquid eligible names at each formation date, trailing dollar volume, price >= $5, real trade that day |
| Book | 12 names, equal weight, 20% single-name cap, $10,000 start |
| Execution | decide at the close of day `i`, **fill at the open of day `i+1`** |
| Costs | 5 bps + 1 bp slippage one way (**12 bps round trip**), plus a round-trip cash reserve so the book cannot be 100% invested AND pay commission |
| Dividends | credited as CASH (`ret - retx`), never free-reinvested |
| Delisting | a holding gone 5 sessions is resolved at **-30%** (declared, variable) |
| Benchmark | CRSP value-weighted market, buy and hold, pinned Fama-French |

## THE HEADLINE

**At 12 names, the rebalance PHASE moves terminal wealth by 1.8x to 3.8x — more
than any difference between the strategies being compared.** Every single-phase
ranking on this board, including the one this document first published, is a
draw from that spread.

12-1 momentum, net of costs, across every offset in each rebalance cycle:

| hold | phases | **median** | min | max | spread |
|---:|---:|---:|---:|---:|---:|
| 1 | 1 | **$35,228** | — | — | 1.00 |
| 5 | 5 | **$34,948** | $20,275 | $41,197 | 2.03x |
| 21 | 7 | $12,623 | $6,816 | $15,400 | 2.26x |
| 63 | 7 | $16,633 | $10,352 | **$38,817** | **3.75x** |
| 126 | 7 | $11,455 | $9,459 | $16,811 | 1.78x |
| 252 | 7 | $21,270 | $20,043 | $35,661 | 1.78x |

**Market, buy and hold: $39,951.**

That `$38,817` in the h=63 max column is the number this document originally
led with.

## The Micron question, answered

**Directionally, the intuition is right — and it does not survive costs.**

| hold | frictionless | net | costs paid | turnover |
|---:|---:|---:|---:|---:|
| **1** | **$47,908** | **$35,228** | **$4,983 (26%)** | 45.5x/yr |
| 5 | $44,051 | $38,191 | $2,819 | 21.0x/yr |
| 63 | $40,083 | $38,817 | $584 | 4.8x/yr |
| 252 | $32,425 | $32,029 | $163 | 1.8x/yr |

* **Gross, faster IS better, monotonically.** $47,908 > $44,051 > $40,083 >
  $32,425. The Micron intuition is a real property of the signal.
* **Costs take a quarter of it at daily frequency** — $4,983 of a $47,908
  frictionless result, at 45x annual turnover and 12 bps round trip.
* **Net, daily and weekly are still the best medians** ($35,228 and $34,948),
  and everything slower is worse. *This reverses what the first version of this
  file said*, which ranked h=63 top on the strength of one lucky phase.
* **And none of them beat simply owning the market.** $35,228 against $39,951.

So: trade fast if you trade this signal — but the whole exercise is behind
buy-and-hold at this breadth, and the honest programme headline is unchanged:
**demonstrated independent edge remains 0%.**

## Why "clears both nulls" is the column that matters

The first leaderboard had ONE null — `random`, re-drawn at every formation date
— and momentum sat at the 100th percentile of it at every holding period. That
was mostly an artefact:

* `random` re-ranks the universe daily, so at `hold=1` it turns over **492x/yr**
  and pays **29.5%/yr** in costs. Its median terminal is **$1,070**.
* 12-1 momentum's ranks barely move day to day: **45x/yr**, ~2.7%/yr.

Beating that null at a short holding period can mean nothing more than "traded
less than a coin flip would". `random_persistent` — ONE fixed random 12-name
basket held for twelve years, near-zero turnover — brackets the other end, and
the bar is now the 90th percentile of **both**. `reversal_1m` at `hold=1` clears
the churning null (100.0) and fails the persistent one (0.0), which is exactly
the distinction one null hid.

## Breadth: it does not rescue the result

`--preset breadth`, k = 3..50 at `hold=21`, each k benched against its own
nulls in its own sizing: momentum's best is **k=50 at $26,804** (85th/80th
percentile of chance) and every smaller k is worse. Concentration is not what
was missing.

Note k=3 and k=5 return identical results under both sizings: at a 20%
single-name cap those books are all-at-the-cap, so the sizing rule has nothing
left to decide. That is correct behaviour, not a bug — but it means "sizing" is
not an independent axis at high concentration.

## Three defects the instrument had, found by looking at what it measured

1. **Implicit leverage.** A held name with no open price cannot be sold, and the
   engine allocated the new book against total equity anyway — buying with money
   still locked in the old position, driving cash negative with no borrow cost.
   `openprc` is missing on ~2.2% of CRSP daily rows, so a 12-name book met one
   about every fourth rebalance. `min_cash_usd` is now on every receipt.
2. **The single-name cap silently stopped applying.** Cap-then-renormalise
   converges to 1/n, so 3 names under a 20% cap came back at 33% each — over the
   cap the receipt claimed to enforce.
3. **The null comparison pooled incompatible groups.** The `breadth` sweep varied
   `top_k` and `sizing`, and every real policy was scored against one pooled
   null spanning all of them. Grouping on the full settings tuple made the
   inverse-vol policies print `nan` — which is what "this has no control" looks
   like when it stops being hidden.

## Known limitations, stated rather than discovered later

* **One window, 2013-2024.** The pre-2013 CRSP pull lacks
  `openprc`/`retx`/`shrout`, so the next-open convention is not executable
  there and the loader refuses those years by name. Widening it is a WRDS
  re-pull.
* **Long only.** No shorts, no leverage, no borrow. `reversal_1m` losing is a
  statement about a long book of last month's losers.
* **Delisting is an assumption** (-30%); re-run at 0.0 and -1.0 to bound it.
  Nobody has.
* **Costs are flat** — no market impact beyond 1 bp, which flatters the fast
  policies, and they still did not beat the market.
* **Hundreds of policies were tried.** The best of hundreds is high because
  hundreds is large.
* **Phase medians rest on 5-7 offsets**, not the full cycle, for h >= 21.
