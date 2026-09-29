# TRIAL-STRADDLE-FWD-1: choosing straddles by our move-size forecast vs by trailing volatility, forward on live quotes

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE yet.** This builds a forward test. No entry exists yet, so nothing
has been graded.

| item | value |
|---|---|
| best historical net strategy vs the market | unchanged |
| best forward paper strategy | unchanged (nothing has been graded) |
| independent selector count | +1 candidate in the forward log: straddle **selection** by the size forecast. It is a new alpha source (option-implied size), not a weight in `arena_composite` |
| farm candidates tested / promoted | 0 / 0 |
| new actionable finding | **real costs are larger than the lab assumed.** At the 2026-09-28 closing quotes, only 164 of the 400 most liquid optionable names passed the quote filters. Their median straddle spread was **11.5% of mid** (p90 18.2%), and across all quoted names it was **21.2%**. Buying at the ask alone costs half of that, about **5.8% of premium**. The lab assumed 10% of premium for a full round trip, which looks optimistic for anything beyond the top ~100 names |
| external execution drag | measured, not assumed: see the line above. Closing quotes are wider than intraday quotes, and the in-session observations collected before the first entry will say by how much |
| LLM spend / cost per gradeable output | $0.00 / $0.00. No LLM is used anywhere |

- **Contract:** `backend/data/optimus/straddle_forward/contract_v1.json`, **policy hash
  `a0f7e02d84444332`**, frozen 2026-09-29T03:44:12Z, before any entry.
- **Frozen size model:** `model_ridge_pit_v1.json`, **model sha `6d65591f62156cae`**.
- **First entry:** session 2026-10-16, on the 2026-11-20 monthly expiry.
- **First grade:** the 2026-11-20 expiry close.
- **First formal read:** after 12 graded expiries (about 2027-10).
- **Confirmation:** needs about 44 expiries.

Licence: `PRODUCT_EXPERIMENT`. It is a paper log: no broker, no orders and no money. It
licenses no claim. A good first read would make it a candidate for a longer forward record,
nothing more.

## Where this comes from

`docs/research_notes/2026-09-29/sizing_on_move_size_2026-09-29.md` §5 (CRSP x OptionMetrics,
2014-2024):

- The point-in-time size forecast carries information the option market had not priced. Its
  rank coefficient on next month's |move|, **beyond implied vol**, is +0.21 (t 20.8) and was
  positive in every year.
- Straddles picked by the forecast against implied vol beat straddles picked by trailing vol by:

| names per leg | edge over the trailing-vol pick (bp of equity a month) | t |
|---|---|---|
| 20 | +4.1 | 1.45 (CANNOT_DISTINGUISH) |
| 100 | +8.2 | 4.75 |
| quintile | +6.8 | 5.28 |

**Four reasons this is a candidate and not a result:**
- The breadth sweep was declared *after* the 20-name read, and its worst cell cannot
  distinguish.
- The premia were synthetic (ATM IV × √T × 0.798) and the cost was assumed (10% of premium).
- Neither book beats cash robustly. Most of the absolute P&L is the variance risk premium on
  the short leg.
- OptionMetrics ends in 2024-12.

**What is left to learn:**
- the real quoted cost;
- whether the relative edge holds forward.

Only live chains can answer either question, so this trial exists to collect them.

## The design (frozen in the contract; the code is `backend/services/straddle_forward.py`)

**Signal.** The size model is the lab's point-in-time ridge.
- Target and inputs: |r21| from 8 price columns, plus past earnings-move size and the
  projected earnings-in-window flag.
- The fit: refitted once on every CRSP decision date whose target had closed (258,712 rows,
  2013-01 to 2024-10), then frozen.
- It matches the walk-forward's last fit to about 3 decimals (printed in
  `model_fit.log`).
- Walk-forward out-of-sample IC with |r21| was 0.368.

**Point-in-time earnings.** Only report dates strictly before the pull time are stored. The
next report is projected from the last completed one in 91-day steps. The scheduled future
date is never read: the fetch discards it, and the feature code drops and counts any report
dated after the decision close.

**Universe.** The top 400 names in the bars file by 63-session median dollar volume, with price
at least $5. Known ETFs are excluded, and the underlying's `quoteType` must be EQUITY.

**Expiry.** The standard monthly expiry (the third Friday, or the session before it) that sits
21-35 calendar days out. Monthly expiries are 28-35 days apart, so about half of all sessions
have no such expiry. On those days the pass takes an `OBSERVE_ONLY` snapshot (costs and
coverage), which is never graded.

**Entry.**
- When: once per XNYS session, on the first pass inside 10:45-15:30 America/New_York.
  The window is computed in ET, so DST changes the UTC hour, not the rule.
- Strike: the listed strike nearest spot that both a call and a put carry.
- Fills: **long straddles at call ask + put ask; short straddles at call bid + put bid.**

**Quote refusals.** Each refusal is recorded per name with its reason:
- a missing or zero bid or ask;
- a crossed quote;
- a leg spread above 50% of its mid, or a straddle spread above 20% of its mid;
- a strike more than 5% from spot;
- open interest below 10 on a leg;
- a leg's last trade older than 5 days;
- in-session, an underlying quote older than 30 minutes;
- a mid outside the no-arbitrage band, so no IV can be inverted.

**Implied move.**
- `iv_atm` = the mean of the call and put IVs inverted from the **mid**, using European BSM
  with r = 4% and q = 0.
- `implied_move = iv_atm × √T × √(2/π)`.

**Rank.**
- `gap = log(forecast E|r21| × √(sessions to expiry / 21) / implied move)`.
- LONG takes the largest gaps; SHORT takes the smallest.
- Breadths are **20, 50 and 100 per leg**. A cell runs only with at least 2 × breadth + 10
  usable names.
- **Primary cell:** 100 per leg if it ran on at least 80% of the entry sessions in the read,
  otherwise 50. This is declared before the first entry and is mechanical. The closing-quote
  dry run could not fill the 100 cell.

**Twin.** The same usable names on the same quotes, ranked by trailing 63-session vol ×
√(21/252) × √(2/π) instead of the size forecast.

**Exit.**
- Held to expiry and marked at **intrinsic value, |S_T − K|**, from the bars close on the
  expiry session.
- A split is rescaled. A dividend adjustment is not, because options are not dividend-adjusted.
- No exit cost is charged. The sensitivity run charges 5% of intrinsic.

**Objective.**
- Primary: log utility of equity at 2% of equity in premium per leg:
  `log(1 + b·ls_ridge) − log(1 + b·ls_vol)`, where `ls = (long + short)/2` is the return on
  premium.
- Secondary: the forecast-picked book against cash at quoted costs.

**Statistics.** One observation per **expiry**: cohorts that share an expiry share one terminal
shock. t, SE and MDE (2.8 SE) come from `move_size_sizing.block_stats` over expiry blocks.

**Power.**
- The 100-per-leg history is +8.2 bp a month with a monthly sd of about 19.5 bp.
- An MDE equal to the historical effect needs **about 44 expiries (about 3.7 years)**. At
  12 blocks the MDE is about 15.8 bp, roughly twice the effect.
- Forward, 100 per leg out of ~300-400 names is roughly a tercile. The lab's 100 per leg was
  about 6% of 1,755 names. The closest historical cell is the quintile: +6.8 bp, t 5.28.

**Kill rule.**
- From 6 expiry blocks on, at every grade: if the primary-cell diff has mean ≤ 0 and t ≤ −1
  (FAILED_VARIANT), the selector is `RETIRED_FROM_CURRENT_SEARCH`.
- At 6 blocks this fires on a true zero about 16% of the time per look, and on the historical
  +8.2 bp about 2% of the time.
- It is a reversal detector and cannot confirm anything.

**Promotion.** None from this contract. `CAPITAL_CANDIDATE` would need matured forward evidence
**and** a defined-risk form.

## Worst case in dollars (protocol item 4)

**Setup.** From the 2026-09-28 dry run: $1,000,000 equity and 2% in premium per leg, i.e. a
$20,000 credit on the short leg and $20,000 paid on the long leg.

**The long leg can lose at most its premium, −$20,000.**

**The short leg (forecast-picked, 20 or 50 names) has unbounded loss.** For sized moves over
the hold:

| move | per name at 20/leg (max) | per name at 50/leg (max) | whole leg, every name at once |
|---|---|---|---|
| 3σ | −$3,416 | −$1,367 | **−$62,008 (−6.2% of equity)** at 20; −$61,449 at 50 |
| 10σ | −$12,912 | −$5,183 | **−$248,426 (−24.8% of equity)** at 20; −$247,177 at 50 |

These are sized moves, not bounds. A short straddle's loss grows without limit.

**The real-money form, if it ever comes to that, must be defined-risk:**
- long straddles only; or
- every short straddle wrapped in long wings (an iron butterfly), whose maximum loss is the
  wing width minus the credit.

The paper log keeps naked short legs only because they are the measurement the history was
taken on.

## Scheduling

Task `AegisStraddleForward`:
- runs `pythonw -m scripts.straddle_forward` every 30 minutes, windowless;
- logs to `backend/data/optimus/straddle_forward/straddle_forward.log`;
- writes a receipt in `runs/` for every non-idle pass.

Each pass grades whatever has expired, then enters or observes if the pass is inside the window
and the session has not been handled yet. Two refusals:
- the decision close in the bars file is not the previous session;
- no contract has been frozen.

Pause the task with `backend/data/optimus/straddle_forward/STOP`, or remove it with
`schtasks /Delete /TN "AegisStraddleForward" /F`.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS**
- The pipeline runs end to end on free, live chains at $0. On 2026-09-28 it produced 400
  names quoted, 164 usable, IVs inverted ourselves from the mid, point-in-time features, a
  frozen model, both books with their twins, and the worst case, in 3.5 minutes.
- The size forecast and the implied move agree on rank (Spearman 0.92), as expected from
  complements. Its disagreement with trailing vol is large: the rank correlation of the two
  gaps is 0.31, and at 20 per leg only 3 of 20 long names are shared. So the test is not
  measuring the same trade twice.

**WHAT DOES NOT**
- The lab's cost assumption. A 10% round trip was optimistic. At closing quotes the median
  usable straddle's entry half-spread alone is about 5.8% of premium, and spreads widen fast
  down the liquidity ranking:

| liquidity rank | median straddle spread |
|---|---|
| top 50 | 7% |
| ranks 51-100 | 16% |
| ranks 101-400 | 22-30% |

- At the close the 100-per-leg cell cannot run, because 164 names are usable and it needs 210.

**HIGHEST-EV EXPERIMENT**
- Read the in-session `OBSERVE_ONLY` snapshots the task takes between now and 2026-10-16. They
  cost $0 and come before any entry.
- If intraday spreads on the usable set are still above about 10% of mid, the absolute
  (vs-cash) question is already answered NO for anything beyond the top ~100 names. The
  relative question (forecast vs trailing vol, same names, same quotes) would then be the only
  one worth the 44 expiries.
- That decision can be made in two weeks, not three years.
