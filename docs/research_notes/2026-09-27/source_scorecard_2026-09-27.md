# Source scorecard: WSJ, Barron's, MarketWatch, and the analyst-revision history (2026-09-27)

Receipt: `backend/data/optimus/source_scorecard/source_scorecard_2026-09-27_150809.json`
(run id `2026-09-27_150809`, the first run, not committed). Re-run it with `python -m scripts.source_scorecard`.
Licence: PRODUCT_EXPERIMENT diagnostics. LLM calls: 0. Cost: $0.00. Bars run through 2026-09-25 and were 2 days old at run time.

## RESULTS SCOREBOARD

| | |
|---|---|
| Dow Jones units in the corpus | **62**: 22 LLM claims, 39 MarketWatch consensus snapshots, 1 Big Money index call. They come from 61 stored articles. |
| Dow Jones units graded at any horizon | **22**: 17 WSJ, 4 Barron's Big Money, 1 Barron's pick. All 39 MarketWatch snapshots are OPEN or UNGRADEABLE. |
| Dow Jones cells with a verdict other than TOO_FEW | **0**. The best-covered cell is WSJ "Heard on the Street" at 1 day: 16 claims over **9 publication dates**. The threshold is 10. |
| yfinance analyst-revision leg (a different source) | 92,897 units since 2025-01-01 and 92,637 graded at 1 day. **No ALPHA_DETECTED cell.** |
| Share of Dow Jones claims published after a move above 2 sigma | **4.5%** (1 of 22). Under a random walk you would expect 4.6%. |
| Share of analyst revisions published after a move above 2 sigma | **15.9%**, about 3.4x the random-walk rate. 33.9% point in the direction of a prior move above 1 sigma. |
| Proposed source weights above zero | **0 of 60** cells. The weights are a proposal only: nothing live reads them. |
| **RESULT IMPROVEMENT** | **NONE.** The scorecard now exists and re-runs, but it has found nothing to follow yet. |

## What was graded, and how

**Unit.** A unit is one dated claim about one ticker, with a direction (up, down or none).

**Entry.** Entry is the **open** of the first session that opens after publication, using New York time. A claim published before 09:30 ET on a session day enters that session. A date-only stamp enters on the next session. So do yfinance event dates, because their time zone is not stated.

**Exit.** Exit at horizon h is the **close** of session entry+h-1. We report h = 1, 5, 21 and 63.

**OPEN and UNGRADEABLE.** A horizon that has not elapsed is OPEN and is counted. A ticker with no bars is UNGRADEABLE_NO_BARS_FOR_TICKER, recorded by name.

**Three returns per unit:**
- raw;
- the excess over SPY;
- the excess over a matched control. The control is the equal-weight mean of every other name in the unit's `matched_twins` cell (size band x 63-session vol tercile x 12-1 momentum tercile), as of the close before entry.

**Statistics.** Standard errors are clustered by publication date (CR1), and the MDE is 2.8 x the clustered SE.

**One extra control, added after the first run showed it was needed.** It is the source's own common drift. That drift is the mean excess over the control of every graded unit from the same source at the same horizon, whatever its direction. A "down" call is credited only with what it adds beyond that drift.

Ideas already closed by measurement are cited, not re-derived:
- broker identity (hit 50.1%, firm-skill rho -0.11);
- first-mover raises (-0.06% at 21 days point-in-time; the +1.34% version was look-ahead);
- the `skill_mom` analyst filter (a 2025-only effect).

Source: `docs/reviews/ADJUDICATION_2026-09-26_WAVE*.md`. The yfinance leg is graded **by claim type only, never by firm**.

## Corpus at run time, by source

| source / column | units | graded at >= 1 horizon | OPEN | UNGRADEABLE |
|---|---|---|---|---|
| WSJ `wsj_heard_on_the_street` (reader-lane label) | 17 (16 directional, 1 neutral) | 17 (h1); 14 (h5); 0 (h21/h63) | 3 at h5; 17 at h21 | 0 |
| WSJ `wsj_news` (relabelled "Exclusive" page) | 1 | 0 | 1 | 0 |
| Barron's `barrons_big_money_poll` | 4 (3 manager picks + 1 index call) | 4 at every horizon | 0 | 0 |
| Barron's `barrons_stock_picks` | 1 (BN, up) | 1 (h1) | 1 at h5 | 0 |
| MarketWatch `mw_analyst_estimates` | 39 consensus snapshots | **0**: dated by when Aegis saw the page (09-26 and 09-27) | 37 at every horizon | 2 (AARD: no bars) |
| yfinance revisions (history leg) | 92,897 | 92,637 (h1); 77,774 (h63) | 139 (h1); 2,997 (h21) | 76 no bars, 45 missing entry bar |

Nine articles produced no unit:
- 7 WSJ pages were extracted but held no directional claim;
- 1 WSJ page is still waiting for extraction;
- 1 Big Money poll (2026-04-27, "Barron's Big Money Poll: Where Investing Pros See the Stock...") had no bull/bear majority that `parse_big_money` could read.

**Column caveat.** None of the 19 stored WSJ URLs carries a heard-on-the-street marker, so the WSJ column label is the reader lane's, not the page's. Every WSJ unit carries `column_evidence`.

## The scorecard

### Dow Jones (every cell is TOO_FEW; the table shows the few cells that have anything)

| cell | h | n | tickers | dates | hit (95% CI) | mean signed vs control | clustered SE | MDE | t | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| WSJ HotS directional | 1 | 16 | 16 | 9 | 0.56 (0.33-0.77) | +0.18% | 0.53% | 1.48% | 0.34 | TOO_FEW (needs ~110 dates) |
| WSJ HotS directional | 5 | 14 | 14 | 8 | 0.57 (0.33-0.79) | +0.11% | 1.66% | 4.65% | 0.07 | TOO_FEW (needs ~203 dates) |
| Big Money manager picks | 21 | 3 | 3 | 1 | 1.00 | +4.54% | none | none | none | TOO_FEW (needs ~258 dates) |
| Big Money manager picks | 63 | 3 | 3 | 1 | 0.67 | +3.39% | none | none | none | TOO_FEW (needs ~193 dates) |
| Big Money index call (SPY up) | 63 | 1 | 1 | 1 | 1.00 (SPY +3.5% raw) | -1.7% vs SPY's own drift | none | none | none | TOO_FEW |
| Barron's pick (BN) | 1 | 1 | 1 | 1 | 0.00 | -0.38% | none | none | none | TOO_FEW |

Notes on the table:
- **"Needs ~N dates"** is the number of publication dates needed for an MDE of 0.5%, 1%, 2% or 4% at h = 1, 5, 21 or 63. It is computed at the current dispersion of date-block means.
- **WSJ at 5 days is carried by a few claims.** The top-5 share of the total signed excess is 16.8x, so the rest net to a loss.
- **The WSJ cells come from a single month (2026-09).** A leave-one-month-out check cannot be computed yet.

Per-unit detail, the Dow Jones claims graded at 5 days (signed excess vs the matched control):
- **right:** NOW +6.1%, BSP (down) +6.2%, VG +5.4%, CRM +4.1%, WDAY +3.6%, SNOW +2.2%;
- **wrong:** HWM -10.1%, TEM -4.9%, BA (down) -3.3%, PSNL -2.3%, AMGN (down) -2.1%, LNG -1.7%, NVO (down) -1.6%.

Four of the six "right" calls (CRM, NOW, SNOW, WDAY) come from **one** article: WSJ 2026-09-08, "AI Is Disrupting Software Companies--but Not as Fast as Many Feared". That is one observation, not four.

**BSP needs checking.** It is the extractor's ticker for "At Bending Spoons, the Numbers Are the Real Mind-Bender" (WSJ 2026-09-11) and has not been checked against the security master.

### yfinance analyst revisions since 2025-01-01 (a different source: the history leg)

| claim type | h | n | dates | hit vs SPY (95% CI) | mean / median signed vs control | t vs control | net of source drift (t) | by year (mean signed vs control) | verdict |
|---|---|---|---|---|---|---|---|---|---|
| target_raise | 21 | 45,540 | 439 | 0.454 (0.450-0.459) | -0.31% / -0.79% | -2.43 | +0.04% (0.32) | 2025 -0.65%, 2026 +0.08% | CANNOT_DISTINGUISH (anti-signal flag) |
| target_raise | 63 | 38,361 | 394 | 0.439 (0.434-0.444) | -0.73% / -2.36% | -2.80 | +0.38% (1.45) | 2025 -1.39%, 2026 +0.41% | CANNOT_DISTINGUISH (anti-signal flag) |
| target_lower | 21 | 30,757 | 429 | 0.526 (0.520-0.531) | +0.43% / +0.79% | 3.16 | +0.09% (0.64) | 2025 +0.54%, 2026 +0.27% | **BETA_EXPLAINS** |
| target_lower | 63 | 27,475 | 385 | 0.548 (0.542-0.554) | +1.77% / +2.72% | 5.24 | +0.67% (1.98) | **2025 +2.67%, 2026 -0.02%** | **BETA_EXPLAINS** |
| upgrade | 63 | 4,143 | 369 | 0.440 (0.425-0.455) | -1.24% / -2.42% | -2.61 | -0.13% (-0.28) | 2025 -1.79%, 2026 -0.14% | CANNOT_DISTINGUISH (anti-signal flag) |
| downgrade | 63 | 3,714 | 372 | 0.530 (0.514-0.546) | -1.04% / +2.00% | -0.98 | -2.15% (-2.02) | 2025 -0.70%, 2026 -1.67% | CANNOT_DISTINGUISH |
| initiation | 63 | 4,081 | 365 | 0.453 (0.438-0.468) | -1.56% / -4.50% | -2.08 | -0.54% (-0.72) | 2025 -1.88%, 2026 -0.93% | BETA_EXPLAINS (beats SPY, t 2.86, but not its cell) |
| all types | 63 | 77,774 | 404 | 0.483 | +0.07% / -0.57% | 0.41 | +0.28% (1.66) | 2025 +0.07%, 2026 +0.07% | CANNOT_DISTINGUISH |

Horizons 1 and 5 are CANNOT_DISTINGUISH for every claim type (|t| < 2). The full grid is on the receipt.

**How to read the table.** Every name an analyst revises, raised or lowered, drifts below its size/vol/momentum cell: the source's common drift is -0.35% at 21 days and -1.10% at 63 days. The "target_lower" row is that drift reflected in a mirror.

A downgrade call "wins" against the control because the named stock falls, and a raise on the same kind of stock loses by the same amount. **Net of that drift, no claim type clears t = 2.** The largest is target_lower at 63 days, t 1.98, and it is a **2025-only** effect (2026: -0.02%). That is the same shape as the `skill_mom` result that closed on 09-26.

Mean and median disagree in sign in several rows. The tail is extreme: WOLF at -1,870% and AGL at +867% signed at 63 days. These look like corporate-action or bar artefacts on a survivor-selected panel. **Read the medians and the hit rates, not the means.**

## Winner vs matched loser (what was knowable BEFOREHAND)

**Dow Jones, h = 5.** Top tercile versus bottom tercile, 6 claims each (n is far too small, so this is anecdote):

| | top tercile | bottom tercile |
|---|---|---|
| agrees with the 90-day yfinance revision consensus | **83%** | 33% |
| gave a number | 0% | 33% |
| stock moved more than 1 sigma in the 5 sessions before | 0% | 17% |
| up calls | 83% | 50% |
| mean signed excess vs control | +5.3% | -4.6% |

"Agrees with consensus" is the only contrast worth a pre-registered test, because it is observable at publication.

**yfinance, h = 63.** Terciles of 25,924 each:
- moved more than 1 sigma before: 44.3% vs 43.8%;
- agrees with consensus: 61.6% vs 62.1%.

Neither separates winners from losers. Losers are more often up calls (66% vs 52%), which is the raised-names drift again.

**Already moved.** Of the 22 Dow Jones claims with bars:
- 18.2% came after a move above 1 sigma (random walk: 31.7%);
- 4.5% came after a move above 2 sigma (random walk: 4.6%).

Those rates do not look like explaining a move after it happened. Analyst revisions do: 43.3% came after a move above 1 sigma and 15.9% after one above 2 sigma.

## What this does not yet do

- **MarketWatch history.** Consensus snapshots are dated when Aegis saw the page, so they cannot be graded before 2026-09-28 (h = 1) and about 2026-12-23 (h = 63). The history leg is the yfinance data, labelled as a different source.
- **Big Money S&P 500 level forecasts** are not graded. They need an SPX level series, and only SPY exists in the bars. The direction call is graded against SPY's unconditional drift.
- **Archive articles** (the Oct-2025 Big Money poll) are graded from their publication time. The LLM that extracted their claims read them afterwards, so a lookahead-propensity check is owed (CLAUDE.md S53).
- **The panel is survivor-selected** (CLAUDE.md 2026-09-22). A dead name is UNGRADEABLE, and control cells skip names with no exit bar.

**WHAT WORKS:** Nothing yet, measurably. No source, column or claim type beats its matched control net of its own source's common drift. The one Dow Jones cell with any depth, WSJ Heard on the Street, sits at hit 0.56 on 9 publication dates with an MDE of 1.5% at one day.

**WHAT DOES NOT:** Directional analyst revisions do not beat their size, vol and momentum cells at 1-63 sessions once the drift shared by every revised name is removed. The apparent "target cuts are right" result (t 5.2 vs the control) is that drift plus 2025. Revisions also chase moves: 15.9% come after a move above 2 sigma.

**HIGHEST-EV EXPERIMENT:** Pre-register "a WSJ or Barron's stance that AGREES with the prior-90-day revision consensus beats one that disagrees, net of source drift, at 5 and 21 sessions". Let the running reader accrue the ~110-200 publication dates the MDE needs, re-running this script weekly. At about 5 dated columns a day, that is 5-8 weeks and $0 beyond the extraction already paid.
