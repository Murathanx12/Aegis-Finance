# Long-horizon mandate direction-check — 73 years, 1953-05 → 2026-05

> `engine/research/long_horizon_mandates.py` (results:
> `engine/research/output/long_horizon_mandates.json`). Run 2026-07-18.
>
> **What this is:** the three reference-lane mandates replayed at
> ASSET-CLASS level over 877 months — Kenneth French market factor
> (equity, total-return, survivorship-clean at index level), 10Y Treasury
> total returns approximated from FRED GS10 yields (Swinkels-style
> duration approximation), gold from the datahub monthly LBMA series,
> monthly rebalance, no costs.
>
> **What this is NOT (CANON §2/§5):** an alpha claim, a stock-selection
> backtest (T7 forbids those on free data), or a license to touch the
> in-flight lanes. Grade: **DIRECTIONAL**. Findings may only inform NEW
> pre-registered lanes. Panel starts 1953 because GS10 does; pre-1971
> gold is the fixed-price era (~0 return — conservative for the alt
> sleeve). 1929 is honestly out of reach at monthly bond resolution.

## Headline table (1953-05 → 2026-05)

| Mandate | CAGR | Vol | Sharpe | MaxDD | Longest underwater | Worst 10y CAGR | $100 grows to |
|---|---|---|---|---|---|---|---|
| conservative 40/50/10 | 8.2% | 7.3% | 0.57 | **−18.3%** | 32 mo | **+3.4%** | $32k |
| balanced 70/25/5 | 9.9% | 10.9% | 0.56 | −34.4% | 50 mo | +0.7% | $102k |
| aggressive 95/5/0 | 11.2% | 14.3% | 0.53 | −48.0% | 66 mo | −2.0% | $231k |
| **S&P 500 (100% eq)** | 11.4% | 15.1% | 0.53 | −50.3% | 72 mo | −2.5% | $273k |
| classic 60/40 | 9.2% | 9.7% | 0.54 | −30.7% | 41 mo | +1.3% | $62k |

## Stress windows (total return, peak-to-window-end)

| Window | conservative | balanced | aggressive | S&P | 60/40 |
|---|---|---|---|---|---|
| 1973-74 stagflation | −13.5% | −31.8% | −44.7% | −46.5% | −30.7% |
| Dot-com bust 2000-02 | **−2.6%** | −24.2% | −39.0% | −41.8% | −16.0% |
| GFC 2007-09 | −12.9% | −33.2% | −46.9% | −49.3% | −27.6% |
| **2022 rate shock** | **−18.3%** | −21.5% | −24.4% | −24.8% | −21.1% |

## Findings (mechanics, not alpha)

1. **The mandates behave as designed in equity crashes.** Conservative cut
   the dot-com bust to −2.6% and the GFC to −12.9% vs S&P's −42/−49%.
   The risk ladder orders correctly in every window. The lane design is
   structurally sound across 73 years including regimes none of us lived
   through.
2. **The one historical failure mode of "conservative" is 2022-shaped.**
   Its worst drawdown of the ENTIRE 73 years was the 2022 rate shock
   (−18.3%) — nearly matching aggressive (−24.4%) — because a 50% sleeve
   of 10Y-duration bonds is a rates bet, not a safety sleeve, when
   inflation regime shifts. In 1973-74 the same mechanism kept it to
   −13.5% only because yields rose more slowly. **Candidate NEW lane** (if
   ever pre-registered, own YAML + hash + inception): a
   `conservative-short-duration` variant (bond sleeve split across
   duration buckets or T-bill-heavy) to test whether the 2022 failure
   mode is removable without giving up crash protection. NOT an edit to
   the live conservative lane.
3. **Aggressive ≈ S&P with slightly better tail** (−48% vs −50%, worst
   10y −2.0% vs −2.5%): the 5% bond sleeve does almost nothing. Its value
   vs the baseline is behavioral (rebalancing discipline), not
   statistical — the honest way to present that lane.
4. **Sharpe is flat (~0.53–0.57) across the ladder.** Allocation moves
   you along the risk-return line, it does not beat it. This is exactly
   the "allocation ≠ alpha" message the product should keep displaying.
5. **Every mandate spent 3-6 YEARS underwater at least once** (32-72
   months). The forward lanes are 39 DAYS old. This is the strongest
   possible "too early to read" calibration for the track-record page
   (F-019): at 73-year scale, nothing about day-39 NAV means anything.

## What this licenses / forbids

- ✅ Present these as mandate-mechanics context (with DIRECTIONAL grade +
  methodology note) — e.g. on the track-record or builder pages.
- ✅ Pre-register a short-duration conservative variant as a NEW lane
  (T13-style, Murat flips the seed flag) if we want to act on finding 2.
- ❌ Any change to in-flight lanes (CANON §5). ❌ Any "our mandates beat
  X" claim (they don't, and shouldn't — finding 4). ❌ Extending this to
  stock selection (T7 stands until a survivorship-free panel lands).
- NN/ML training on this panel: pointless at n=5 asset-class series and
  still forbidden for selection until TRIAL-NN-1's data gate clears.
