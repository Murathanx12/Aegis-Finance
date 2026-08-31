# FINDING — 2026-08-31 — the thin-coverage edge is real, and not buyable at monthly turnover

**Receipt:** `backend/data/optimus/wrds/taq_spread_by_liquidity_band.json`
**Code:** `scripts/taq_spread_by_liquidity_band.py`
**Licence:** RESEARCH input — this constrains what may be CLAIMED and what may be traded.

---

## The question, and why it could be answered today

The IBES + CRSP 2013-24 test put the analyst-upside edge in a **liquidity band**,
roughly $100k-$10m/day, at **+6.98%/yr (t 2.22)**. It charged **10-50 bps a
side**. Nobody had checked whether names in that band actually cost that.

Two decisions waited on the answer:

- `universe.MIN_DOLLAR_VOLUME = 3_000_000` makes the thin end **unobservable**,
  not merely unbought — the tracker holds zero names below $3.0m/day.
- A forward lane was proposed to log `spread_bps` daily and "decide after the
  contest". It would take months, and on the current universe it has **no names
  to measure**.

Both are now moot: **TAQ millisecond NBBO is readable on our WRDS subscription**
(`entitlement_probe.json`), so the cost is measurable from history.

## What was measured

Quoted spread `(ask − bid) / mid` in bps, regular hours, aggregated server-side.
Bands cut on median dollar volume from `crsp.dsf` (June 2024); 30 names per band
sampled **evenly across** the band, not the top N — taking a band's most liquid
members measures its easiest corner and calls it the band. Three trading days.

| band | median bps | round-trip | p25–p75 | no quotes |
|---|---|---|---|---|
| **$100k–1m** | **148.9** | **297.7** | 88.5–203.3 | 2 of 30 |
| $1m–5m | 38.7 | 77.4 | 28.9–60.1 | 0 |
| $5m–10m | 21.0 | 42.0 | 15.0–31.1 | 0 |
| $10m–50m | 20.2 | 40.5 | 9.2–28.3 | 0 |
| $50m+ | 6.7 | 13.4 | 3.7–9.4 | 0 |

## The result

The backtest's **10-50 bps a side is only realistic at $10m/day and above.** In
the band where the edge was found, the true quoted cost is **3–15× the
assumption**.

Against the measured edge, at monthly rebalancing (12 full turnovers/yr):

| band | round-trip | cost/yr @12× | edge %/yr | **net %/yr** | break-even rebalances/yr |
|---|---|---|---|---|---|
| $100k–1m | 297.7 bps | 35.7% | +6.98% | **−28.74%** | **2.3** |
| $1m–5m | 77.4 bps | 9.3% | +6.98% | **−2.31%** | 9.0 |
| $5m–10m | 42.0 bps | 5.0% | +6.98% | **+1.94%** | 16.6 |
| $10m–50m | 40.5 bps | 4.9% | +5.79% | **+0.93%** | 14.3 |
| $50m+ | 13.4 bps | 1.6% | +5.79% | **+4.18%** | 43.2 |

**Two of the three bands the edge was attributed to lose money once the spread
is real.** The thinnest band loses by a factor of five.

## What follows — and the part that is not "don't touch it"

1. **Do NOT widen `MIN_DOLLAR_VOLUME` to chase the thin band at monthly
   turnover.** The current $3m floor is roughly right; for a monthly strategy
   the *tradable* floor is better at **$5m**, where the net first turns positive.
2. **The thin band is not refuted — its HOLDING PERIOD is.** The edge can pay
   for **2.3 turnovers a year**, i.e. a ~5-month hold. A $100k–1m name is a
   6-month position or it is nothing. That is a testable, specific claim
   (`T24_HOLD_REUNDERWRITE`), not a closure.
3. **Observation still widens.** These names should get a `CompanyState` row, a
   status and a forecast; they must not get a monthly order. Observation
   universe ⊃ execution universe, exactly as the roadmap has it — this finding
   sets the execution floor, not the observation floor.
4. **The forward `spread_bps` lane is cancelled.** It would have spent months
   arriving here.
5. **Every future backtest in this family must charge the band's own cost**, not
   a flat 10-50 bps. A flat cost assumption across bands silently manufactures
   the thin-name edge.

## Limits, stated rather than discovered later

- **Quoted, not effective.** Marketable orders can execute inside the quote, so
  these are an **upper bound**. For thin names it is the relevant bound, because
  size walks the book rather than improving on it.
- **Excludes market impact**, which binds hardest exactly where the spread is
  widest: at $6-8k a ticket, a $500k/day name is 1-2% of a day's volume. The
  true cost in the thin band is **worse** than shown, not better.
- **CRSP ends 2024-12-31**, so both legs use 2024. The question is structural.
- **3 days, 30 names per band.** Enough to separate 149 bps from 6.7 bps; not
  enough for a precise per-band point estimate. The rank ordering is the result.
- Quotes are equal-weighted, and 2 of 30 names in the thinnest band **did not
  quote at all** on a sampled day — recorded as absent, never as a zero spread.
