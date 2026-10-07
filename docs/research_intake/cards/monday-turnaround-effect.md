# CARD: monday-turnaround-effect

## Index fields
- topic: Monday / weekend effect and "Turnaround Tuesday" (day-of-week seasonality)
- mechanism_class: behavioural_bias, limits_to_arbitrage
- dataset_status: DOCUMENTED_NOT_TRACKED

## Citation
Frank Cross (1973), "The Behavior of Stock Prices on Fridays and Mondays," *Financial Analysts
Journal*, 29(6): 67-69. Verified via independent corroborating search records (ScirP reference
listing; direct FAJ/Taylor-Francis fetch not attempted this pass — FAJ issue-level DOIs from 1973
are not reliably resolvable, and the citation is corroborated identically across three independent
secondary sources). Kenneth R. French (1980), "Stock Returns and the Weekend Effect," *Journal of
Financial Economics*, 8(1): 55-69. Verified by cross-checking the EconPapers/RePEc listing
(`ideas.repec.org/a/eee/jfinec/v8y1980i1p55-69.html`, title/journal/volume/pages/date confirmed,
2026-10-07). Josef Lakonishok, Edwin Maberly (1990), "The Weekend Effect: Trading Patterns of
Individual and Institutional Investors," *The Journal of Finance*, 45(1): 231-243. DOI
10.1111/j.1540-6261.1990.tb05089.x. Verified via the Wiley Online Library listing surfaced
independently in search, title/journal/volume/pages/DOI all agreeing. Decay evidence: Geoffrey
Smith, Russell Robins, "No More Weekend Effect," *Critical Finance Review* (year not independently
re-extracted this pass beyond the ASU press summary). Verified by fetching
`https://news.asu.edu/20170201-discoveries-asu-research-debunks-myth-stock-market-weekend-effect`
(2026-10-07; CRSP data, 1,000 stocks, 1926-2014, directly confirmed).

## The claim, in one sentence
US stock returns are systematically lower (historically, negative on average) on Mondays and
higher on Fridays than on other weekdays (Cross 1973, French 1980), the effect is distinct from an
ordinary non-trading-day effect and is at least partly driven by individual (retail) investors
trading disproportionately, and net-selling, on Mondays (Lakonishok & Maberly 1990) — and, per the
most thorough later re-estimate found this pass, the effect in US broad-index data had **already
mostly disappeared by 1975**, a full generation before most of the retail "Turnaround Tuesday" /
calendar-reversal content built on this literature's name could have been observed live.

## Mechanism: why the inefficiency could exist, and who is on the other side
The behavioral story (Lakonishok & Maberly 1990): individual investors disproportionately execute
trades on Mondays — plausibly because they review their portfolios and act on news/thinking
accumulated over the weekend, when they are not at work and markets are closed — and they are, net,
sellers on that day. If retail order flow systematically leans toward selling at the Monday open,
and institutional/market-maker liquidity does not immediately and fully absorb that imbalance, the
average Monday return is pushed down mechanically by aggregate order-flow pressure, not by any new
information. The "other side" would be whoever supplies liquidity against that retail selling
imbalance (market makers, contrarian institutional flow) — the mechanism predicts their own
realized return should be structurally higher on Mondays as compensation, which is testable and
was not independently re-verified this pass.

## Assumptions
Requires a meaningful population of retail investors transacting with day-of-week-correlated
timing preferences, and requires that institutional/arbitrage capital does not fully absorb the
resulting imbalance (a limits-to-arbitrage assumption — otherwise the pattern would be competed
away immediately). The mechanism assumes the imbalance is **persistent and predictable enough in
aggregate** to show up in average returns across a large cross-section and many years, not merely a
property of individual names.

## Measurable variables: the precursor observable BEFORE the move
The entire precursor here is the **calendar day itself** — day-of-week is trivially PIT-observable
(known with certainty in advance, unlike almost every other variable this intake routine will
encounter). This is simultaneously the cleanest possible precursor (zero measurement risk) and the
reason the mechanism, if real, should be the most heavily arbitraged of all calendar effects —
anyone can condition on it with no data cost at all, which is exactly consistent with Smith &
Robins's finding that it had vanished by the mid-1970s, within a couple of decades of being
plausibly tradable at scale.

## Sample period and markets
Cross (1973): S&P index, 1953-1970. French (1980): NYSE/CRSP-based daily returns, a multi-decade
pre-1980 sample (exact start/end not independently re-extracted this pass beyond the EconPapers
listing). Lakonishok & Maberly (1990): NYSE trading-volume/transaction data, used to study
investor-type trading patterns rather than returns directly, sample period centered on the 1980s
(exact dates not independently re-extracted this pass). Smith & Robins (the decay study): CRSP,
1,000 stocks, **1926-2014** — the longest and most recent window found this pass, and the one that
actually speaks to whether the effect survives into the modern era.

## Effect size as published
Cross (1973): S&P closed up on only **39.2%** of Mondays vs. **62%** of Fridays, 1953-1970; a down
Friday was followed by a down Monday at roughly a 3:1 ratio. Smith & Robins (decay study): Monday
returns averaged **-18.1 points** 1926-1974, vs. only **-5 points**, not statistically significant,
1975-2014 — i.e. the effect's own best later re-measurement finds it roughly **3.6x smaller and
statistically dead** in the post-1975 sample.

## Known failure modes and post-publication decay
This is the single clearest pre-registered-style decay case the owner's brief could ask for, and it
predates McLean-Pontiff/Harvey-Liu-Zhu's general publication-decay framework by decades: the
effect's own later, larger, more careful re-estimate (Smith & Robins, using nearly a century of
CRSP data rather than the ~17-20 year windows of the original 1970s-80s papers) finds it
**effectively gone after 1975** — meaning French (1980) and Lakonishok & Maberly (1990) were
published describing and explaining a phenomenon that, per this later evidence, had already
mostly disappeared by the time of publication or shortly after. A ScienceDirect paper on "the
evolution of the weekend effect in US markets" could not be fetched past a paywall in the prior
research pass that first surfaced this material (403) and remains **unverified** — not relied on
here. International evidence (not independently checked this pass) is reported elsewhere as mixed
by country and decade, which is consistent with a US-specific arbitrage-driven decay rather than a
universal non-effect.

## What AEGIS has on disk to test it
`DIA` (SPDR Dow Jones Industrial Average ETF) and `SPY`/`QQQ` daily bars. DIA itself is a
recognized index proxy in `backend/services/xs_ranker.py`'s `INDEX_PROXIES` but its own daily bars
were not directly located in `docs/DATA_CATALOG.md`'s summary this pass (the catalog page is a
summary of the 40 biggest files and duplicate findings, not an exhaustive listing — a one-time
daily yfinance pull of DIA, same mechanism as every other ETF already on disk, e.g.
`backend/data/optimus/contest/bars/bars_FX.parquet` which already carries SPY alongside FX, closes
this gap at zero marginal cost). `backend/data/optimus/wrds/bulk/` CRSP daily common-stock bars
(1990-2024, per `FINDING_2026-08-23_OVERNIGHT_INTRADAY.md`'s panel description) give the full
cross-section needed to re-test the ORIGINAL day-of-week claim (not just a single index), which is
the more statistically powerful version of this test and does not require any new data pull at
all.

## The falsifiable question and the declared primary metric, with costs
*Does the US equity cross-section (or a single large index — DIA/SPY) exhibit a statistically
distinguishable, economically tradable Monday-vs-other-weekdays return gap in the MODERN sample
(post-2000, say), net of a flat round-trip cost, once blocked by ISO week (the correct dependence
unit for a weekly-recurring effect, per CANON §58 and the 2026-09-24 t-stat lesson in CLAUDE.md
already paid for once this programme)?* Primary metric: mean Monday return minus mean return on
all other weekdays, t-statistic computed on the weekly-blocked series (not daily, which would
overstate degrees of freedom for a once-a-week effect), reported by year (CLAUDE.md protocol 11)
against a random-weekday control of the same trade frequency. **Honest prior entering this test,
stated before any run, per Mission rule 1's sequential-learning discipline: the best available
re-estimate of this exact effect already says it is dead since 1975 — this is not a fresh question,
it is a replication of a null, and the test should be designed and read accordingly.** The
specific "Turnaround Tuesday on US30, 25-day SMA, Tuesday 23:15 close" rule from the owner's social
intake (`docs/research_notes/2026-10-07/social_media_theories_2026-10-07.md` §2) remains
`NOT_A_HYPOTHESIS_YET` until its entry/exit condition is recovered verbatim from the source — the
25-day SMA's role (direction filter? sizing? unused context?) and what specifically triggers a
Tuesday entry were never given, and three incompatible public "Turnaround Tuesday" rule variants
were found this pass sharing the same name, so no version may be invented by analogy.

## Whether a corpse already exists here
No `NEGATIVE_RESULTS.md` or `docs/TRIALS/` entry was found this pass for a Monday-effect /
day-of-week test on AEGIS's own CRSP panel — this is open. The social-intake pass on the same date
(`docs/research_notes/2026-10-07/social_media_theories_2026-10-07.md` §2) already did this exact
literature review and reached the same `NOT_A_HYPOTHESIS_YET` verdict for the specific reel's rule,
for the same reason (entry condition never given); that pass should be cited, not re-run, and this
card adds the un-conditioned, literature-only version of the question (does a modern Monday effect
exist on AEGIS's own data at all, independent of any specific reel's rule) as the open, testable
remainder.

## hyp_lab family
`family_unmapped` — no calendar/seasonality family exists in the fixed `HYP_LAB_FAMILIES` tuple.
`TRIAL-DRAFT-F-calendar-seasonality-v0.md` exists in `docs/TRIALS/` as a draft trial, which is the
closer home for this mechanism than any hyp_lab family; this card's finding should be routed there
if pursued.

## Verdict
**NOT_A_HYPOTHESIS_YET** as a capital idea, because the best available evidence already says the
mechanism died 50 years ago and nothing found this pass updates that prior for the US modern era.
**READY_TO_CELL** as a cheap, data-already-on-disk replication of the null (confirming or
overturning Smith & Robins on AEGIS's own 1990-2024 CRSP panel costs nothing new to run and would
either close the question definitively for this programme or surface a genuine, currently-unknown
re-emergence worth a second look) — the value of running it is almost entirely in closing the
question cleanly, not in expecting a positive.

## needs_evidence
- Does AEGIS's 1990-2024 CRSP panel (or DIA/SPY) show a Monday-minus-other-weekdays return gap
  after 2000, with a week-blocked t-statistic printed by year, net of a flat round-trip cost and
  against a random-weekday control?
- When and where was Smith & Robins's "No More Weekend Effect" published, and what does the
  unverified ScienceDirect paper on the evolution of the weekend effect actually report?
- What exactly are the entry and exit conditions of the owner's "Turnaround Tuesday" reel rule
  (the 25-day SMA's role, what triggers the Tuesday entry), recovered verbatim from the source?
