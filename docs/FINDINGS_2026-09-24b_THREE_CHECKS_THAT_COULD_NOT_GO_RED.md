# 2026-09-24 (afternoon) — a positive result, killed by the cheapest test I owned

Everything measured from the venue or from panels on disk. **LLM spend $0.00.**

---

## RESULTS SCOREBOARD

| line | state |
|---|---|
| best historical net strategy vs market | **none.** §59 stands, and the horizon route out of it is now CLOSED |
| best forward paper strategy | fleet **$450,994 of $500,000, −9.8%** |
| new actionable finding | **the decision funnel was a 44-day-old file and its health row said `ok`** |
| independent selector count | unchanged |
| LLM spend | **$0.00** |

---

## 1. The owed sweep, and how it went

I owed a sweep of `composite_prior` across horizons, having swept `lgbm_full` —
the model §59 had already ranked worst of four. The horizon hypothesis ("the toll
is paid per round trip, so a longer hold pays it over more time") has no force on
a model that loses money before costs.

Ran it. Survivorship-free, purge scaled to H, worst cell of the breadth sweep:

| H | gross/hold | net/yr (worst k) | strictly indep. blocks |
|---|---:|---:|---:|
| 21 | +0.13% | **−2.57%** | 32 |
| 42 | +0.50% | +0.98% | 15 |
| 63 | +0.77% | +1.74% | 9 |
| **126** | **+2.38%** | **+4.09%** | **4** |

H=21 reproduces §59 exactly, which is the run's validity check. Then gross grows
tenfold to H=126 while the toll stays at 34 bps. Every book size positive at
H≥42. **The first positive cell this programme has produced.**

## 2. Two things wrong with it, in order of how much they mattered

### The error bar was wrong in my favour — real, and it turned out not to matter

`top_k_backtest` computed its t by grouping dates into **calendar months**. At
H=21 that is about right. At H=126 each block's forward return overlaps the next
five almost entirely, so the standard error is understated by ~√6 — **and the
understatement grows with H, which is the axis being swept.** The t column rising
monotonically (−0.24 → +0.58 → +0.67 → **+2.83**) was partly the estimator
flattering long holds.

Fixed: `t_nonoverlap` blocks on `horizon` consecutive rebalance dates.

| | t monthly | t non-overlap | blocks |
|---|---:|---:|---:|
| H=21 k=200 | −0.24 | −0.26 | 63 |
| H=126 k=200 | **+2.83** | **+1.33** | 7 |

It agrees with the old statistic exactly where the old statistic was right, and
diverges only where it was wrong. Still optimistic — blocks of width H share half
their span, and strict independence needs 2H, which leaves **four blocks**, so
`n_blocks_strict` now travels on every receipt.

### And then leave-one-year-out killed the result outright

843 rebalance dates, 2021-05 to 2026-03:

| year | mean net/hold | dropped | mean net/hold |
|---|---:|---|---:|
| 2021 | **−7.82%** | 2021 | +5.11% |
| 2022 | +2.59% | 2022 | +2.63% |
| 2023 | **−1.17%** | 2023 | +3.34% |
| 2024 | +2.26% | 2024 | +2.74% |
| 2025 | **+13.55%** | **2025** | **+0.12%** |
| 2026 | **+13.29%** | 2026 | +1.91% |

**Drop 2025 and +2.62% becomes +0.12%.** Three of six years negative or flat.
Top 5% of dates carry 53.8% of the total.

And the mechanism is not mysterious: `composite_prior` is short liquidity, long
illiquidity, short skew, short reversal — a small-and-speculative tilt, in a
regime that rewarded exactly that. **§59 had already written the sentence: the
edge IS the illiquidity.** The longer holding period did not change what is being
bought. It compounded one regime into a larger number while reducing the sample
to four blocks.

**The horizon route out of §59 is closed.** Not because holding longer fails to
raise gross — it does — but because what it raises is exposure to a factor whose
payoff over this panel is one bull market in small speculative names.

### The lesson, at my own expense

I spent the afternoon correcting an error bar. The correction was real and
**irrelevant to whether the result was true.** One `groupby(year).mean()` over
data already in memory settled it, and I ran it last instead of first.

**When a number is positive, the first question is not how precise it is. It is
which part of the sample it is.** `top_k_backtest` now computes leave-one-year-out
and date concentration unconditionally, and the sweep's verdict checks the regime
condition BEFORE it discusses significance — it now prints `ONE REGIME, NOT AN
EDGE` on this data.

## 3. Three checks that could not go red

All three were live, none was a crash, and all three failed silently to the
branch that looked healthy.

### The funnel was 44 days old and its health row said `ok`

`ic_health` **read** `generated_at`, **printed** it, and never compared it to
anything. A row that prints a date and cannot go red is decoration.

- `FUNNEL_STALE_DAYS = 10`; an undateable stamp is **UNKNOWN**, never fresh.
- The advertised remedy was itself a no-op: `python -m
  backend.services.opportunity_funnel` had `run()` and **no `__main__`**, so it
  imported the module and exited 0. An operator following the instruction printed
  in `pm_actions` saw the file unchanged and no error. It now has a CLI that
  writes atomically, archives the previous snapshot to `funnel_history/`, and
  **refuses without overwriting** on a stage failure.
- The test asserted `status == "ok"` on the shipped file — encoding *"the shipped
  funnel will never get old"*. It got old. Derived from the file now.

Then ran it: universe **5,339 → 1,500 → 250 → 40 → 25 candidates**, dated today.
**Thirteen of the 25 were absent from the August snapshot** — SNDR ALLE GMAB ADUS
CHD CHH BR ALG STNG TS ARCO PAGS SON. For six weeks they could not be chosen; not
because they ranked low, but because nobody offered them.

### The fleet audit undercounted its own headline

`entry_dates` asked for `/v2/orders?status=closed&limit=500&direction=asc` — the
**oldest 500**. `fleet_trade_autopsy` had already measured 500 fills across this
fleet, so the request sat exactly on the cap, and any position opened after a
book's 500th order came back with no entry date. The next line read

    "stale": (age is not None and age > STALE_DAYS)

**so an undateable position counted as fresh.** "11 of 18 positions older than 14
days" was a lower bound published as a count, failing in the direction that
flatters the fleet. Now paged with an `after` cursor; `age_unknown` tracked
separately; coverage travels on the receipt; the verdict says **LOWER BOUND**
whenever any age is unknown.

Re-audited: 11 of 18 stale, **2 unknown** — hack5's two option legs, one of which
is a short with no BUY to find — order history complete for all five books.

### And yesterday's verdict overclaim

`fleet_audit._verdict()` ORs a capacity condition and a staleness condition, then
asserted the *capacity* conclusion ("improving the ranker cannot help, nothing it
produces can enter the portfolio") whenever **either** fired. Fleet gross is 38%;
nothing is blocked from entering. The two failures have opposite remedies — stop
adding vs start exiting — and it named the wrong one in the case that actually
fires.

## 4. The fleet, and one thing worth your attention

| book | equity | vs $100k | pos | gross | stale |
|---|---:|---:|---:|---:|---:|
| hack1 | 92,537 | −7.5% | 2 | 52% | 2 |
| hack2 | 98,820 | −1.2% | **0** | 0% | 0 |
| hack4 | 82,593 | −17.4% | 2 | 46% | 1 |
| hack5 | 93,304 | −6.7% | 2 | 17% | 0 |
| hack6 | 83,741 | −16.3% | 12 | 82% | 8 |
| **FLEET** | **450,994** | **−9.8%** | 18 | 38% | 11 (+2 unknown) |

**hack2 is alive and refuses everything.** Its Railway loop ran to the close; its
own counterfactual reports 1 taken trade (−$1,142) against **3,186 refusals**,
and prints:

    refusal_edge_on_risk   -3.6263
    refusal_verdict        the gate is discarding edge -- loosen it or explain it

**Do not act on that verdict yet.** Its refused losers cluster at −104%, −103.7%,
−103.4% of risk; its refused winners at +1,392%, +1,399%, +1,401%. Both
`pair_short_vs_iwm`, both marked at a median 292 elapsed hours. A symmetric
holding rule does not produce a loss tail capped at 1× risk and a gain tail
running to 14×. In `aegis-alpha-terminal/alpha/counterfactual.py`:

    if pnl_pu < -per_unit_loss * 1.05:     ->  unmarkable, pnl = 0
    if pnl_pu > per_unit_loss * 20.0:      ->  unmarkable, pnl = 0

**The loss floor is 1.05× and the gain ceiling is 20×.** That is defensible for a
defined-risk spread, which genuinely cannot lose more than its max loss — so a
larger loss really is a bad quote. It is *not* defensible for a short stock
against an index hedge, whose loss is unbounded. For pair rows the loss
distribution is truncated at 1.05× and the gain distribution at 20×, censored
asymmetrically, in the direction that makes refusing look expensive.

The file's own comments record that an earlier version of this reported
**+1,226,583% of risk** and printed *"loosen the gate"*. The guard was added at
20×; the pair case walks under it at 14×.

That is a small change in the **other repo** (`aegis-alpha-terminal`) and I have
not made it — say the word. What it would change is whether a live paper book
keeps advising that a refusal gate be loosened, which is the same move that cost
the fleet $46,401 realised.

## 5. Receipts

| file | what |
|---|---|
| `xs_ranker/horizon_sweep_composite_2026-09-24.json` | 4 horizons × 4 k, LOO + strict blocks per cell |
| `xs_ranker/horizon_sweep_2026-09-24.json` | the lgbm_full run, kept as the record of the wrong question |
| `fleet_audit/fleet_audit_2026-09-24.json` | paged order history, `age_unknown`, coverage |
| `backend/data/funnel_night10.json` | 25 candidates, generated today |
| `backend/data/funnel_history/funnel_2026-09-24.json` | the archive the CLI now keeps |
| `NEGATIVE_RESULTS.md` §61 | the full entry, including the version written before LOO |
