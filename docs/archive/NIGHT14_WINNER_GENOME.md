# WINNER-GENOME-1 — how the Bloomberg leaderboard was actually produced

**Pre-registered** `Aegis module/TRIALS/PREREG_WINNER_GENOME_1.md` @ `4aa03aa`,
committed **before** the simulator produced a number. Runner
`Aegis module/scripts/run_winner_genome_1.py`; receipts
`Aegis module/data/factory/winner_genome_1_results.json` and
`winner_genome_1_perturbation.json` (untracked — `/data/` is gitignored).

> ## Verdict: **DISPERSION_ONLY.**
> Across 220 non-overlapping 5-week windows on CRSP daily 2002-2024, with
> 2,600 simulated teams per arm per window under the real tournament rules,
> **not one of the five winner strategy families shifted its return
> distribution's median above its own volatility-matched random control by
> more than that difference's measured 80%-power MDE.** Two families —
> concentrated-sector and speculative-underdogs — measurably **widened both
> tails** (p95 up, p5 down by almost exactly as much) while leaving the centre
> where it was. That is the arithmetic signature of risk-taking, not selection.
>
> The only detectable family effects anywhere in the trial are on the
> **maximum**: sector concentration raises the leaderboard number (+1.92 pp
> vs its matched control, MDE 1.09), while momentum-filtering and quality-
> screening measurably **lower** it (−3.02 and −7.26). Every effect this trial
> can see is about the tail, and none of them is about the middle.
>
> Re-running the identical selections at six position budgets: **all 30
> family-minus-control comparisons stay below their own MDE** — the picks add
> nothing at any budget — while **the budget itself dominates**: swapping the
> tournament's 20% cap for inverse-volatility weighting raised compound return
> AND cut drawdown AND cut ruin probability in all five families, in one case
> from a 24.5% to a 6.7% chance of losing half the account.
>
> **This does NOT say the winners had no skill.** It says the *published*
> component of what they described — which names to pick — is below this
> instrument's resolution, while the *dispersion* component is measured and
> large. The part the CUHK captain says mattered most — active intraday entry
> and exit — this design structurally cannot see. See §8.

---

## 1. The question, and the thing we do not have

Murat entered the Bloomberg Global Trading Challenge, watched teams post
enormous 5-week returns, and said: *"it doesnt seem real even looks luck but i
dont think so."*

The honest form of that question is not "why did the winner win." It is:

> **Which observable portfolio-construction behaviours occur disproportionately
> among winning portfolios, survive controls for volatility and
> winner-selection, and continue to work in periods not used to discover them?**

**Stated first, because everything downstream depends on it: we do not have the
winning teams' holdings.** The Bloomberg tables in the screenshots are
**aggregate across all ~2,600 competitors**. NVIDIA's aggregate P&L is the sum
over every team that held it; it is not evidence that the winning team held
NVIDIA. No portfolio is reconstructible from those tables and this trial does
not pretend otherwise.

What *is* reconstructible is the **strategy family** each winning captain
described publicly. Those descriptions are the input.

| id | family | source |
|---|---|---|
| F1 | momentum + volume + clean price action | CUHK 2025 captain |
| F2 | "betting on volatility" — deliberately maximum dispersion | RIT 2024 captain |
| F3 | quality momentum (momentum screened on ROE and debt) | Imperial 2025 |
| F4 | concentrated sector bet (biotech was their instance) | Drexel 2025 |
| F5 | speculative underdogs — small, low-priced, high-potential | UConn 2021 |

## 2. The instrument

- **Spine:** CRSP daily stock file 2002-2024, 5,789 trading days × 11,145
  permnos, already restricted at the source pull to common US stock
  (`shrcd` 10/11) on NYSE/AMEX/NASDAQ.
- **Death is modelled.** 7,283 real delistings (`dlstcd >= 200`) are spliced
  into the return matrix on the first trading day after the last quote, with
  Shumway −0.30 for the 228 performance delists that carry no `dlret`. During
  the simulation **1,601 held positions were terminated by a delisting**. This
  is why CRSP was used rather than a yfinance fetch of today's index members:
  a universe of names that were still trading at the end is a machine for
  manufacturing skill.
- **Windows are a tiling, not a selection.** The calendar is cut into
  consecutive non-overlapping 25-trading-day blocks: 231 blocks, of which
  **220 are evaluable** (the first 11 lack the 252-day formation history).
  There is no seasonal, regime or event choice available to the analyst.
- **Universe per window:** price ≥ $5, ≥252 days of history, 63-day median
  dollar volume ≥ $1m, top 1,500 by dollar volume. Median universe: **1,500**.
- **Tournament rules honoured exactly** (2025 handbook): long-only, no
  leverage (weights sum ≤ 1, remainder in cash at `rf`), **no position above
  20%**, ranked on total return over the window. Cap violations: **0**.
- **Teams:** 2,600 per arm per window — the real field size. Position count
  `k ~ U{5..25}`, weights `~Dirichlet(1)` water-filled to the 20% cap,
  rebalance ∈ {buy-and-hold, every 5 days} with p = 0.5. Costs: 10 bps one-way
  decides; 0 and 25 bps reported. `np.random.default_rng` throughout.
- **No-lookahead proof:** on a named window (block 120, formation 2013-11-29)
  every return, price, volume and market-cap cell after T0 was replaced with
  garbage and the universe and all five pools came back **bit-identical**.
  `perturbation_proof: PASS`.

### The control that is the trial

**C3 — random selection at matched volatility.** For each family, C3 keeps the
*same* team: same `k`, same weight vector, same rebalance draw, same window.
Only the names change — drawn to reproduce that family's own realised
distribution of constituent-volatility percentile buckets. Selection
information is destroyed; the volatility profile is preserved by construction.

The match is not decorative: the mean absolute gap between a family's and its
control's volatility-bucket histogram was **0.07 percentage points** (the
prereg voided any arm above 2.0), and realised annualised portfolio volatility
came out within a percentage point or two on every family.

Also run: **C1** equal-weight the whole 1,500-name universe, **C2** equal-weight
the top-100 by market cap (with CRSP `vwretd` beside it), **C4** random
selection at unmatched market volatility.

---

## 3. The primary result — one number per family

**Δmedian** = mean over the 220 windows of [family's median 5-week net return −
its matched control's median], in percentage points per 5-week window, at
10 bps. **The sampling unit is the window (n = 220), not the team** — 2,600
teams inside one window share a market factor and counting them as independent
observations would manufacture significance out of a common shock. MDE =
2.80 × max(Newey-West, IID) SE, per CANON §19.

| family | Δmedian (pp) | its MDE | t | blocks | halves agree | **verdict** |
|---|---:|---:|---:|:--:|:--:|---|
| F1 momentum+volume | **+0.079** | 0.402 | +0.55 | 5/8 | no | UNRESOLVED |
| F2 bet-on-volatility | **−0.023** | 0.033 | −1.94 | 7/8 | yes | UNRESOLVED |
| F3 quality momentum | **−0.033** | 0.392 | −0.24 | 4/8 | no | UNRESOLVED |
| F4 concentrated sector | **−0.010** | 0.116 | −0.24 | 5/8 | no | **DISPERSION_ONLY** |
| F5 speculative underdogs | **−0.080** | 0.314 | −0.71 | 4/8 | yes | **DISPERSION_ONLY** |

**Nothing clears its ruler.** The largest effect in the table is 8 basis points
per five weeks against a ruler of 40. Per §19 these are **not detectable**, and
none of them is reported as a kill.

The F2 row deserves its own sentence. Its ruler is **0.033 pp** — by far the
tightest measurement in the trial, because the paired design leaves almost no
between-window dispersion in the difference. Against that ruler the answer is
still nothing. **Deliberately selecting the most volatile fifth of the market
does exactly as well as selecting random names of the same volatility, in every
regime block but one.** F2's entire visible effect *is* its volatility.

### The tails, which is where the families actually live

| family | Δp95 (pp) | MDE | Δp5 (pp) | MDE |
|---|---:|---:|---:|---:|
| F1 momentum+volume | +0.03 | 0.50 | +0.35 | 0.45 |
| F2 bet-on-volatility | −0.00 | 0.09 | −0.00 | 0.07 |
| F3 quality momentum | −0.56 | 0.49 | **+0.44** | 0.41 |
| F4 concentrated sector | **+1.82** | 0.48 | **−2.00** | 0.40 |
| F5 speculative underdogs | **+0.58** | 0.44 | **−0.56** | 0.34 |

F4 is the cleanest object in the trial. Concentrating into one sector, against
a control holding names of *identical volatility* spread across sectors, moved
the 95th percentile up 1.82 pp and the 5th percentile down 2.00 pp — both
comfortably detectable — and the median by −0.01 pp against a ruler of 0.12.
It is a symmetric widening. The vol-matcher matches *constituent* volatility;
what sector concentration adds is **correlation**, and correlation is pure
variance with no expected-return term attached.

F3 is the mirror image and the only family that did anything defensible: quality
screening **narrowed** the distribution (p95 down, p5 up by roughly equal
amounts) at an unchanged median. Quality momentum bought a smaller lottery
ticket. In a tournament that is a losing move; in a book it is not obviously one.

### The one-line mechanism

| arm | mean 5-week return | median 5-week return |
|---|---:|---:|
| C1 equal-weight the whole 1,500-name universe | **+1.16%** | **+1.85%** |
| C4 random 5-25 names at market volatility | **+1.16%** | **+1.50%** |
| C2 equal-weight top-100 by market cap | +1.04% | +1.82% |
| CRSP value-weighted index | +1.16% | +2.09% |

Identical means, different medians. Individual stock returns are right-skewed,
so concentration preserves your expected return and destroys your *typical*
one. Every family in this trial sits somewhere on that trade, and the
tournament rewards precisely the end of it that a saver should avoid.

---

## 4. The number the leaderboard actually reports

A leaderboard does not report a median. It reports the **maximum over ~2,600
draws**, which is an order statistic, and order statistics of fat-tailed
distributions are enormous whether or not anybody was skilled.

Per family, the maximum over its own 2,600 teams **within each window** — the
like-for-like leaderboard number, since the real field is ~2,600 — and the same
statistic for its volatility-matched random control:

| family | median max over 2,600 | mean | p90 window | best single window | its control's median max | **Δmax** | MDE |
|---|---:|---:|---:|---:|---:|---:|---:|
| F1 momentum+volume | +20.8% | +22.6% | +35.6% | **+194.5%** | +22.5% | **−3.02** | 1.99 |
| F2 bet-on-volatility | **+27.0%** | +31.6% | **+51.0%** | **+195.7%** | +27.5% | +0.17 | 1.14 |
| F3 quality momentum | +14.6% | +15.0% | +24.8% | +36.2% | +20.5% | **−7.26** | 2.29 |
| F4 concentrated sector | +23.0% | +25.7% | +40.1% | +185.2% | +20.8% | **+1.92** | 1.09 |
| F5 speculative underdogs | +25.5% | +28.7% | +47.3% | **+207.6%** | +26.6% | −1.65 | 1.87 |

Δmax is the only place in this trial where a family is measurably different
from its matched control, and the signs are worth reading slowly. **Only F4
raises the maximum** (+1.92 pp against a ruler of 1.09) — sector concentration
really does buy a bigger leaderboard number, because correlated names move
together. **F1 and F3 measurably *lower* it** (−3.02 and −7.26): momentum
filtering and quality screening both throw away exactly the lottery tickets a
tournament needs. F2 and F5 are indistinguishable from random names of the
same volatility — their maxima are large, and entirely explained by the
volatility they selected for.

Every family's single best window is the same one: **2020-12-18 → 2021-01-26**,
the SPAC/meme melt-up. The ~+200% simulated "winners" are one window out of
220, and even they have a same-window worst sibling in the field.

Pooling the whole simulated field (28,600 teams per window — 11× the real field
size, so these are upper bounds on the real event):

| | value |
|---|---:|
| winning team's 5-week return, median window | **+31.6%** |
| winning team, mean window | +36.0% |
| winning team, 90th-percentile window | +56.0% |
| winning team, best window in 23 years | **+223.6%** |
| **same field's worst team, median window** | **−23.3%** |
| same field's worst team, worst window | **−59.1%** |

The two bold rows are the same tournament. The reviewer's line — "nobody
remembers its identical cousin that lost 60%" — is now a measured number rather
than a rhetorical one.

**The Drexel biotech instance, separately.** The concentrated-biotech sub-arm
(SIC 2833-2836, 8731) came back with a median of **+1.16%** against C4's
+1.50%, wider tails on both sides (p5 −12.2% vs −10.9%, p95 +14.6% vs +11.9%),
and — notably — a *lower* median per-window maximum than random names at market
volatility (+19.7% vs +21.5%). Over 2002-2024, concentrating into biotech
bought the extra variance without even buying the bigger leaderboard number.
Their professor's reasoning was sound for the objective; the specific sector
was not what made it work.

**P(this family produces the field winner)**, from 220 windows × 200 bootstrap
fields assembled in equal parts from the seven stochastic arms plus the two
deterministic controls:

| arm | P(produces the winner) |
|---|---:|
| F2 bet-on-volatility | **0.325** |
| F5 speculative underdogs | **0.259** |
| C3 vol-matched **random** (pooled) | **0.142** |
| F4 concentrated sector | 0.125 |
| F1 momentum+volume | 0.075 |
| C4 random at market volatility | 0.042 |
| F3 quality momentum | 0.032 |
| C1 equal-weight universe | **0.000** |
| C2 large-cap | **0.000** |

Read those two rows at the bottom carefully. In **44,000 simulated tournament
fields**, a sensible diversified portfolio won **zero** of them. And read the
third row too: **random selection at matched volatility wins 14% of
tournaments** — more often than three of the five named winner strategies.

That is the whole answer to "does it seem real, or is it luck." It is neither,
and the decomposition is mechanical: **choosing a high-dispersion style buys
you a large probability of producing the leaderboard's maximum; the choice of
names within that style does not measurably add to it.** The style choice was
deliberate — the RIT captain said so outright. The name-picking is where the
evidence runs out.

---

## 5. Selection versus sizing — what transfers

Each family's **selections were re-run unchanged** under six sizing rules. A
career here plays one arm and one sizing rule in every consecutive window with
an independent team draw each time — 220 windows ≈ 21.8 years.
**Ruin is defined explicitly: career NAV below 0.50 of its start at any
window-end mark.**

| family | sizing | median 5-wk | career CAGR | median career maxDD | return/vol | **ruin** |
|---|---|---:|---:|---:|---:|---:|
| F1 momentum+volume | 20% cap (tournament) | 1.47% | 9.92% | −50.8% | 0.51 | 0.4% |
| | 10% cap | 1.52% | 10.14% | −49.4% | 0.53 | 0.0% |
| | 5% cap | 1.55% | 10.27% | −48.6% | 0.54 | 0.0% |
| | inverse-vol | **1.60%** | **10.60%** | **−44.8%** | **0.59** | **0.0%** |
| | ERC risk parity | 1.54% | 10.22% | −46.3% | 0.57 | 0.0% |
| | half-Kelly | 1.42% | 10.26% | −50.0% | 0.55 | 0.2% |
| F2 bet-on-volatility | 20% cap (tournament) | 1.05% | 4.31% | −75.1% | 0.30 | **36.6%** |
| | 10% cap | 1.11% | 4.62% | −73.5% | 0.31 | 30.6% |
| | 5% cap | 1.15% | 4.85% | −72.5% | 0.32 | 26.8% |
| | inverse-vol | 1.23% | 5.53% | −70.8% | 0.34 | **19.1%** |
| | ERC risk parity | 1.22% | 5.49% | −70.4% | 0.34 | 21.2% |
| | half-Kelly | **1.37%** | **7.15%** | −72.8% | **0.38** | 24.7% |
| F3 quality momentum | 20% cap (tournament) | 1.52% | 9.21% | −49.9% | 0.50 | 1.5% |
| | inverse-vol | **1.67%** | **9.86%** | **−46.7%** | **0.57** | **0.0%** |
| F4 concentrated sector | 20% cap (tournament) | 1.41% | 8.88% | −59.0% | 0.50 | 3.8% |
| | inverse-vol | **1.49%** | **9.67%** | **−54.7%** | **0.56** | **1.4%** |
| F5 speculative underdogs | 20% cap (tournament) | 1.06% | 5.21% | −72.5% | 0.33 | **24.5%** |
| | 10% cap | 1.10% | 5.48% | −70.6% | 0.34 | 18.0% |
| | 5% cap | 1.14% | 5.70% | −69.6% | 0.35 | 15.5% |
| | inverse-vol | **1.32%** | **7.62%** | **−66.1%** | **0.41** | **6.7%** |
| | ERC risk parity | 1.25% | 6.92% | −66.4% | 0.39 | 9.0% |
| | half-Kelly | 1.19% | 6.54% | −72.5% | 0.37 | 25.3% |

(Full 30-row table in the receipt; the rows above are every family at the
tournament budget plus its best alternative, and F1/F2/F5 in full.)

Two things fall out, and only one of them is a null.

**(a) The selection still adds nothing at any budget.** The paired
family-minus-matched-control difference was recomputed at all six sizing rules
— 30 comparisons — and **all 30 sit below their own MDE**. The largest is
F1 at the 5% cap, +0.109 pp against a ruler of 0.404. There was no budget at
which a family's name-picking became visible. Per the prereg's H3, that is the
answer: these families were bets, not signals.

**(b) The sizing is not a null at all, and it is monotone.** In every one of
the five families, replacing the tournament's 20% cap with inverse-volatility
weighting **simultaneously raised the median 5-week return, raised the compound
career return, shallowed the drawdown, raised return-per-unit-volatility, and
cut ruin probability.** F5 goes from a **24.5%** chance of losing half the
account to **6.7%** while its CAGR rises from 5.21% to 7.62%. F2 goes from
**36.6%** to 19.1% while CAGR rises from 4.31% to 5.53%.

There is no trade being made there. The tournament budget is simply dominated
once the objective stops being "produce the field maximum." That is not
surprising — the 20% cap was designed to make a leaderboard interesting — but it
is worth having measured on the same paths, because it is the fourth
independent night in this programme to point at position management rather than
picks (NIGHT-12's `sell_to_cash` null and beta-2.15 sizing finding, NIGHT-13's
FACTORIAL-PM-1 and the constant-half-exposure result, now this).

---

## 6. Robustness the verdict rests on

- **Costs.** At 0 / 10 / 25 bps one-way the family medians move by roughly
  0.27 pp per five weeks and no verdict changes. The *differences* against the
  matched controls are close to cost-invariant by construction: a family and
  its control hold the same number of names and rebalance on the same days, so
  the only cost asymmetry is second-order drift between rebalances.
- **Regime blocks.** The eight pre-declared blocks (2002-03, 2004-06, 2007-09,
  2010-12, 2013-15, 2016-18, 2019-21, 2022-24) are reported per family in the
  receipt. Two are drawdown regimes. F2's Δmedian is negative in 7 of 8; F4's
  and F5's signs flip across blocks, which is what "no effect" looks like.
- **Sample halves.** Pre-2014 vs post-2014 disagree in sign for F1, F3 and F4 —
  a further reason nothing here is promotable.
- **Assertions (all pass).** Delisting path fired (1,601 terminations,
  26 silent terminations counted separately); volatility-match gap 0.07 pp;
  zero cap violations; Compustat coverage for F3 averaged 96.5% (5 early
  windows below 40%, all in 2003-04 where `comp_funda` begins); one arm skipped
  (F3, one window with too thin a pool).

## 7. Search denominator

**72 arm × parameter configurations were executed** and are all in the receipt:
12 base arms (5 families, 5 volatility-matched controls, C4, and the biotech
sub-arm) plus 60 sizing configurations (10 selection sets × 6 budgets); each
base arm additionally ran at 3 cost levels. Two deterministic controls (C1, C2)
and the CRSP value-weighted benchmark run alongside. **1 configuration was
skipped** (F3, one window). Total simulated team-window portfolio paths:
**≈ 55 million** (20.6M base arms × 3 cost levels + 34.3M sizing runs; ~5.7M of
those are the S1 budget re-running an identical configuration to the base arm,
and reproduce it exactly, which is itself a check).

Nothing was dropped for being unflattering, and nothing was added after seeing
a result. The one post-hoc addition to this document relative to the first
completed run was the **per-window maximum** order statistic, which is
reported-never-deciding under prereg §5; the run was repeated end to end from
the same seeds and every deciding number reproduced exactly.

---

## 8. What this cannot tell us

Read this section before quoting any number above.

1. **It cannot say anything about any actual team.** We do not have their
   holdings. Every verdict is about a *described strategy class*, simulated in a
   US CRSP universe — not about CUHK, RIT, Imperial, Drexel or UConn.
2. **It structurally cannot measure execution, which is the part the winner
   said mattered most.** The CUHK captain describes actively adjusting entries
   and exits on price reaction, news flow and intraday behaviour, and navigating
   false breakouts and reversals. This design forms a portfolio on day 0 and
   either holds it or rebalances to fixed weights every five days. **A null on
   selection is not a null on execution.** If the winners' edge is where they
   say it is, this trial was looking in a different place — and that is the
   single most important limitation here.
3. **It is not the real tournament.** Ours is US-only and ~1,500 liquid names;
   the real event is global with >10,000 WLS names, which is a strictly wider
   dispersion pool. A wider pool makes the maximum *larger*, so the
   winner-selection component measured here is if anything an understatement.
4. **These are simulations on historical data — direction checks, never alpha
   evidence.** No Sharpe claim, no money claim, no skill claim. Nothing here
   licenses a change to any live or paper lane, any position size, any product
   default, or any buy/sell language. No skill claims before 24 months of
   forward record.
5. **"It was all luck" is refused as firmly as "it was all skill."** The
   correct statement is narrower: the *selection* component of these five
   described styles is below this instrument's resolution, while the
   *dispersion* component is measured and large, and the *style choice itself*
   is the thing that drives P(winning) — which the RIT captain described as a
   deliberate decision, i.e. as skill applied to the tournament's objective
   rather than to the market.
6. **Below-MDE is not a kill.** Five families came back UNRESOLVED or
   DISPERSION_ONLY on the median. None of them is refuted. A better instrument
   — one that can see execution — could still find something.
7. **One statistical caveat on the tightest number.** F2's ruler (0.033 pp) is
   tight *because* the paired control tracks it so closely. That is a strength
   for the median comparison and a warning against reading the same precision
   into anything else in the table.

## 9. What Murat asked, answered in four sentences

The leaderboard number is the maximum of ~2,600 draws, and a portfolio built to
be sensible has an essentially **zero** chance of producing it — we measured
0.000 in 44,000 simulated fields. Choosing a high-dispersion *style* is what
buys the chance of being first, and the RIT captain said plainly that this was
the deliberate optimisation; **that** part is real and repeatable. Which names
you pick *within* that style did not measurably move the middle of the
distribution in any of the five styles, in any regime block, at any position
budget — the only measurable name-picking effects were on the *maximum*, and
two of the three were in the wrong direction. And the same high dispersion that
produces a +195% cousin produces a −59% one in the same window — which is the
part nobody interviews, and the part that turns into a 24-37% chance of losing
half the account when the tournament's 20% budget is run for twenty years
instead of five weeks.

**For his own book, the one transferable line:** three nights have now measured
the same thing from three directions — NIGHT-12 (a beta-2.15 book, drawdown
22.9% vs SPY's 8.9%, `sell_to_cash` never best in 60 rows), NIGHT-13 (his
selection added +20 to +43 points while his management subtracted 29 to 66),
and now this. **The high-dispersion opportunity classes he is drawn to are not
the problem; the position budget applied to them is.** That claim is still not
proven forward, and nothing here changes a lane.

---

*Registry: `WINNER-GENOME-1` and `VERDICT-WINNER-GENOME-1` in
`Aegis module/TRIALS/registry.jsonl`. Accrues zero arms; counts against every
future promotion.*
