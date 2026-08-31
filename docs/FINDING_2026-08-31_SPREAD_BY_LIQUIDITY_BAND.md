# FINDING — 2026-08-31 — only the THINNEST band fails at monthly turnover

> **CORRECTED the same day.** The first version doubled the round-trip cost and
> therefore retired a band that survives. A buy at the ask and a later sell at
> the bid costs **one** full quoted spread — `(ask − mid) + (mid − bid) = ask − bid`
> — not two. The raw per-name measurements were never wrong; the derived
> round-trip was. The verdict for **$1m–5m flips from −2.31%/yr to +2.34%/yr**,
> and the recommended execution floor drops from $5m to **$1m**. A costing error
> is a verdict error.

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

| band | round-trip (1 spread) | cost/yr @12× | edge %/yr | **net %/yr** | affordable round trips/yr | min hold |
|---|---|---|---|---|---|---|
| $100k–1m | 148.9 bps | 17.87% | +6.98% | **−10.89%** | 4.7 | ~2.6 months |
| $1m–5m | 38.7 bps | 4.64% | +6.98% | **+2.34%** | 18.0 | ~3 weeks |
| $5m–10m | 21.0 bps | 2.52% | +6.98% | **+4.46%** | 33.2 | ~1.5 weeks |
| $10m–50m | 20.2 bps | 2.42% | +5.79% | **+3.37%** | 28.7 | ~1.5 weeks |
| $50m+ | 6.7 bps | 0.80% | +5.79% | **+4.99%** | 86.4 | days |

**Only the thinnest band loses at monthly turnover.** $1m–5m survives with
+2.34%/yr — a thin margin, and one that market impact (excluded here) can still
erase, but it is positive rather than negative.

## What follows — and the part that is not "don't touch it"

1. **A $1m execution floor is defensible; $100k is not.** The net first turns
   positive in the $1m–5m band, so lowering `MIN_DOLLAR_VOLUME` from $3m toward
   **$1m** is supported — which is exactly the floor the 31 Aug brief chose and
   that I had called inert. It is not inert; it is roughly the right line.
2. **The thinnest band is not refuted — its HOLDING PERIOD is.** $100k–1m pays
   for **4.7 round trips a year**, i.e. a ~2.6-month hold. It is a quarterly
   position or it is nothing. That is a testable claim
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
