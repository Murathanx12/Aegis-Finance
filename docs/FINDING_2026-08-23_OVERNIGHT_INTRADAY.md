# FINDING — 2026-08-23: the overnight/intraday decomposition

**Verdict: `ANOMALY_CONFIRMED / STRATEGY_REJECTED`.**
**Licence: none requested.** No paper book is launched from this result.

Reproduce: `python -m scripts.overnight_intraday_study --stage both`
Receipts: `backend/data/optimus/overnight_study/{panel_receipt,results}.json`

---

## 1. The claim under test

> "If you bought MU at the market close every day and sold at market open,
> since 1990 you'd be up over 138 billion percent. Do the exact opposite and
> you'd be down 99.2%. And the same pattern shows up in hundreds of other
> stocks across global markets."

The mechanism offered: market-moving news lands outside regular hours, hedge
funds trade it in thin pre-market liquidity, prices get inflated into the open,
then revert once real liquidity returns.

This is a **lead, not evidence**. The phenomenon has genuine literature
(Cooper/Cliff/Gulen 2008; Berkman et al. 2012; Lou/Polk/Skouras 2019;
Bogousslavsky 2019). The specific numbers are socially sourced.

## 2. Data and method

CRSP daily, common stock (`shrcd` 10/11) on NYSE/AMEX/Nasdaq (`exchcd` 1/2/3),
eligibility evaluated **as of each row's own date** via the `dsenames` interval
join — not a permno-level filter, which would apply 2024's status to 2013's
rows.

```
r_overnight(t) = (openprc_t / cfacpr_t) / (prc_{t-1} / cfacpr_{t-1}) - 1
r_intraday(t)  = prc_t / openprc_t - 1
```

CRSP stores bid/ask averages as negative prices, so every price is `|p|` and
non-positive prices are dropped rather than imputed. Gaps over 7 days are halts
or relistings, not overnights, and are excluded.

**Reconciliation gate.** `(1+r_on)(1+r_id) - 1` must equal CRSP's own `retx`.
It does on **11,297,441 of 11,297,614 rows — 173 failures, 0.0015%**. The
script *exits* rather than reports if this exceeds 0.5%.

### Declared window limit

The claim says "since 1990". **We cannot test that.** The pre-2013 CRSP years
on disk were pulled with a narrow column set and carry no `openprc`, so the
decomposition is undefined there. Everything below is **2013–2024**: 3,019
sessions, 11.3M stock-days. The script records the skipped years in its receipt
and labels them absence of evidence, not evidence of absence.

## 3. The phenomenon is real

| slice | overnight | t (NW) | intraday | t (NW) |
|---|---|---|---|---|
| **MU** (permno 53613) | 13.24 bps/day, **+3,306%** cumulative | 4.15 | −0.80 bps/day, −62.7% | **−0.21** |
| all common stock | 10.73 bps/day | 8.71 | 0.06 bps/day | 0.01 |
| price ≥ $5 | 4.47 bps/day | 3.57 | −0.08 bps/day | −0.05 |

t-statistics are Newey-West on the time series of **daily equal-weighted
cross-sectional means**. n_effective is 3,019 *dates*, not 11.3M stock-days
(CANON §58).

MU's direction matches the claim. The universe-wide result is large and highly
significant. So far the lead looks good.

## 4. It is not a microstructure artifact

The standard deflation is bid-ask bounce: if the day's last trade tends to
print at the bid and the next morning's first at the ask, a spurious positive
"overnight return" appears from nothing. That story predicts the effect
concentrating in **illiquid, wide-spread** names.

The data says the opposite.

| dollar-volume quintile | overnight | t | intraday | t |
|---|---|---|---|---|
| q1 (least traded) | 0.43 bps | 0.51 | −6.37 bps | −5.10 |
| q2 | 4.48 bps | 3.46 | −4.41 bps | −2.32 |
| q3 | 4.54 bps | 3.19 | 0.88 bps | 0.46 |
| q4 | 4.64 bps | 3.22 | 3.19 bps | 1.76 |
| **q5 (most traded)** | **8.25 bps** | **5.94** | **6.30 bps** | **3.88** |

Same story by size: weakest in the smallest quintile (1.75 bps), roughly flat
across q2–q5. **The effect lives where liquidity is deepest.** Bid-ask bounce
is rejected as the explanation.

By era it is not decaying either: 2.45 bps (2013–2017) → **5.91 bps**
(2018–2024).

## 5. And the strategy is still dominated

Here is where the lead dies, and it dies *before costs*.

Most-liquid quintile, equal-weighted, 3,019 sessions:

| one-way cost | overnight-only | buy-and-hold |
|---|---|---|
| 0 bps | 22.17%/yr, Sharpe 1.69 | **41.61%/yr, Sharpe 1.86** |
| 1 bps | 16.17%/yr, Sharpe 1.28 | 41.61%/yr, Sharpe 1.86 |
| 2 bps | 10.46%/yr, Sharpe 0.87 | 41.61%/yr, Sharpe 1.86 |
| 5 bps | **−5.04%/yr** | 41.61%/yr, Sharpe 1.86 |
| 10 bps | **−26.20%/yr** | 41.61%/yr, Sharpe 1.86 |

Buy-and-hold wins **at zero cost**, on both return and Sharpe. The reason is
visible in §4: in the liquid names you could actually trade, the intraday leg
is *also* strongly positive (+6.30 bps, t=3.88) — and that is exactly the leg
the strategy sits out. Breakeven one-way cost is 4.13 bps for a book that pays
**504 executions a year**, and even winning that race only gets you to a
strategy that loses to holding.

**The viral version generalises from the one name where intraday is negative to
a universe where it is not.**

Every net figure above is an **upper bound**: cost is modelled as flat bps per
execution and does not price the market impact of demanding that much liquidity
in the opening auction with ~600 names.

## 6. The most dramatic number is volatility drag

"Do the opposite and you'd be down 99.2%" is the claim's rhetorical peak. For
MU, 2013–2024:

| | |
|---|---|
| realised intraday cumulative | **−62.73%** |
| pure vol drag at a mean of *exactly zero* | **−52.49%** |
| contribution of the mean (t = −0.21, insignificant) | −21.40% |

MU's intraday mean is **statistically indistinguishable from zero**. A
zero-mean series with 222 bps daily volatility loses ~52% over 3,019 sessions
by compounding alone: `exp(−σ²T/2)`.

The claim reads a mechanical consequence of geometric compounding as evidence
of a negative intraday edge. It is not one.

## 7. What survives, and what to do with it

**Survives:** the overnight premium is real, robust to the penny-stock
confound, strongest in liquid names, not decaying — and it carries the equity
premium at roughly **4× lower volatility** than the intraday session (69 vs 293
bps daily, universe EW).

**Deployable now, at zero cost, no new book:** an *execution* rule for books
that already exist — **when reducing exposure, reduce it during the session,
not overnight.** The intraday leg carries approximately zero mean with ~4× the
variance. This is a timing refinement to existing lanes, not a new strategy
needing a new evidence clock.

**Not deployable:** any long-overnight/flat-intraday book. The market-neutral
version (long overnight, short intraday) is worse still: the q5 spread is
8.25 − 6.30 ≈ 1.95 bps/session against two round trips.

## 7b. The earnings-conditioned slice — mechanism CONFIRMED, trade still not

The claim's *mechanism* is specific: news lands out of hours, thin pre-market
liquidity inflates the price into the open, and it reverts once real liquidity
returns. That predicts something the unconditional test cannot see — the
reversal should appear **on earnings gaps and not otherwise**.

Tested directly. Compustat `rdq` linked to permno through `ccmxpf_lnkhist`
(LC/LU links, P/C primary issues, date-range matched). `rdq` carries no time of
day, so a report stamped day D was announced either before D's open or after
D's close; **both** readings are kept and both candidate gaps are flagged.
Being generous here can only *dilute* a real effect toward the baseline, never
manufacture one. 344,329 flagged stock-days = **3.05%** of the panel.

Price ≥ $5:

| session type | overnight | t | intraday | t |
|---|---|---|---|---|
| **earnings gap** | **+9.70 bps** | 3.15 | **−5.89 bps** | **−1.98** |
| no earnings | +4.30 bps | 3.44 | −0.09 bps | −0.05 |

**This is the mechanism, and it is there.** On earnings gaps the overnight jump
is 2.3× larger *and* the intraday leg flips from statistically zero to
significantly negative. Prices really do gap up out of hours and give some of
it back during the session — but **only** when there is an announcement in the
gap. The unconditional intraday return is flat precisely because this small,
real effect is diluted by the 97% of sessions with no news.

**And it still does not produce a trade, for a reason worth stating plainly:**

| | overnight mean | overnight vol | **Sharpe** |
|---|---|---|---|
| earnings gap | 9.70 bps | 164.6 bps | **0.94** |
| no earnings | 4.30 bps | 70.8 bps | **0.96** |

Conditioning on earnings **more than doubles the mean and doubles the
volatility**, leaving the risk-adjusted return indistinguishable. You are not
finding a better trade; you are finding a bigger one. The mechanism explains
*where the variance is*, not where an edge is.

The genuinely tradable-looking leg is the intraday **short** on earnings-gap
sessions (−5.89 bps). It does not survive scrutiny either:

- **t = −1.98 is p ≈ 0.048**, and this session ran roughly 20 slice
  comparisons (3 universes × 2 legs, 5 size quintiles, 5 dollar-volume
  quintiles, 2 eras, 2 earnings conditions). Under CANON §63 screening
  (BH-FDR, m = run) it does not survive.
- it requires **shorting**, whose borrow cost is not modelled anywhere above and
  is worst on exactly the high-attention names that gap hardest;
- it trades 3% of the panel, so the book is thin and concentrated in whichever
  names happened to report.

**Verdict unchanged: `ANOMALY_CONFIRMED / STRATEGY_REJECTED`** — now with the
mechanism confirmed rather than assumed. The right follow-up is *not* a bigger
version of this test; it is intraday timestamps (was the reversal in the first
30 minutes?), which needs TAQ, which is on disk.

## 8. What would change this verdict

- **The missing window.** 1990–2012 open prices are one narrow WRDS pull away.
  If the effect is much larger pre-2013 the *decay* story changes, though the
  cost arithmetic does not.
- **A conditional slice.** The universe-wide comparison is not the only one.
  Overnight conditioned on an *earnings release in the gap* is a different and
  much smaller population, and is the version the mechanism story actually
  predicts. That is a real follow-up and it is cheap — it needs the earnings
  calendar the event store is being built for anyway.
- **Real execution data.** Opening and closing auctions are the day's deepest
  liquidity events; a measured effective spread there, rather than a flat bps
  grid, could move the breakeven materially. It would have to move it past
  buy-and-hold's zero-cost lead, which is the harder problem.

None of these are blockers on anything else. Filed and moving on.
