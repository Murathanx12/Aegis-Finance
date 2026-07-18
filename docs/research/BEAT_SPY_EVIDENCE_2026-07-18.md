# Can we beat SPY? The evidence sweep (2026-07-18)

Murat's ask: "look for projects that claim their backtests beat SPY, adopt
and learn from them." Two research agents swept exactly that — allocation
strategies and stock-selection strategies — scored not on their backtests
but on what happened AFTER publication. Full agent reports informed
findings **F-022** (allocation) and **F-023** (selection) in
`docs/KNOWLEDGE/findings.jsonl`.

## The scoreboard nobody advertises

**Allocation strategies, live vs claim:** GEM Dual Momentum — claimed
~17%/yr / −18% DD, delivered 5.9%/yr / −34% DD post-publication. Keller VAA
— Sharpe 1.10 claimed, −11.2% in 2022 when its protection mattered. HFEA —
−71% peak-to-trough. Professional tactical funds: 30 of 34 lost to a static
60/40 (Morningstar). **Meta-numbers:** published edges decay ~26% out of
sample and ~58% post-publication (McLean-Pontiff, JoF 2016); Sharpe halves
post-publication (Jensen-Kelly-Pedersen).

**Stock selection, live fund records vs SPY over each fund's life:**
1 win — MTUM (+1.5pp/yr, 13y). 2 ties — AVUV, SPHQ. 6 losses — QVAL
(−5pp/yr), QMOM (−3pp/yr), SYLD, VLUE, QUAL, USMV. The people who wrote the
best backtest books run the funds that trail SPY the most. Piotroski's
exact 2000 criteria: −9.5%/yr the following decade.

**The regime fact:** 2015-2026 SPY was itself a momentum-weighted mega-cap
machine — equal-weight RSP trailed it by ~3pp/yr. Any strategy not
overweighting the Mag-7 "lost to SPY" almost by construction. This is why
"pick winners and hold" reads as obvious backward and is unidentifiable
forward.

## What survives, honestly
1. **Trend rule (10-mo SMA) as drawdown insurance** — ~19y OOS record of
   halving max drawdown at a 1-3pp/yr bull-market cost. Matches the ATR
   exit-overlay lane philosophy already running forward. It buys survival,
   not outperformance.
2. **Long-only 12-1 momentum** — the one selection factor with surviving
   academic + live-fund evidence. Realistic net edge +0.5-2pp/yr with
   tracking error and crash risk. Now pre-registered as
   **TRIAL-MOM-BACKTEST** (frozen spec, ONE run, on the survivorship-free
   2017+ panel being harvested) — see
   `docs/TRIALS/TRIAL-MOM-BACKTEST-12-1-momentum.md`.
3. **Quality as a filter** — ~market returns with better crisis behavior;
   an ingredient, not a strategy.

## What we will NOT adopt (and why it's load-bearing)
- Multi-parameter canary TAA (VAA/BAA/HAA family): flagged for overfitting
  by their own trackers; the variant with live history already failed.
- Static leverage stacks (HFEA-style): regime beta, not strategy; one
  correlation flip converted a 40-year backtest into −71%.
- Any strategy adopted on its published backtest without pre-registration —
  the decay meta-evidence IS the justification for the registry discipline.

## The honest answer to "we should beat SPY"
A rules-based public-information strategy has roughly a 20-35% chance of
beating SPY's raw CAGR over a random decade, concentrated in decades
containing a 2008-scale crash. The realistic prize Aegis can play for:
**match SPY ± a small margin with materially smaller drawdowns** (the
mandates already do this — see the replay), plus a possible +0.5-2pp/yr
momentum tilt IF the pre-registered direction-check and then the forward
record support it. Anyone promising more than that, the live evidence says,
is selling their backtest.
