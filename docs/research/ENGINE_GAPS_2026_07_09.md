# Engine Gaps — deep-research synthesis (2026-07-09)

> Question: what separates a state-of-the-art retail quant equity engine from a
> good amateur one, and which capabilities are buildable on free data?
> Method: 5-angle web fan-out → source fetch → **3-vote adversarial
> verification per claim**. 81/106 agents completed before the API spend limit
> cut the run; 14 claims CONFIRMED, 3 REFUTED, and the volatility-targeting
> verification cluster + final synthesis died on the limit (synthesized
> manually here). Coverage gaps stated at the bottom — honesty over polish.

## Confirmed findings (3-0 votes unless noted)

### Signals & evidence base
1. **Most published factors replicate and work out-of-sample** (Jensen–Kelly–
   Pedersen, J. Finance; 93 countries). Running published signals is not a
   fool's errand — with deflation discipline. [jofi.13249]
2. **The US is the only market with reliable post-publication anomaly decay**
   (241 anomalies, 39 markets). Prior for every US signal we run: expect decay
   from the published magnitude. [S0304405X19301618]
3. **PEAD (post-earnings-announcement drift)**: historically ~4%/quarter,
   **declining through the 2010s**; strongest in small/high-cost stocks;
   **net-of-cost profitability in liquid large caps is disputed**. Surprise
   *definition* matters: analyst-forecast-based > time-series SUE; a two-way
   sort of both is stronger; announcement-window abnormal return works as a
   third, comprehensive measure — all free-data computable.
   [S2214635020303750] ⚠ REFUTED companion claim: "PEAD is distinct and
   subsumes momentum" did NOT survive verification (0-3) — treat PEAD as
   correlated with, not superior to, our momentum sleeve.
4. **Chen–Zimmermann Open Source Asset Pricing**: monthly long-short returns
   for **212 published predictors + 209 firm-level characteristics, free**
   (pip `openassetpricing`). CRSP-derived — i.e. a survivorship-curated
   benchmark we cannot build ourselves from yfinance (T7). Usable as a
   zero-cost **direction-check bench** for any signal we define.
   [openassetpricing.com]
5. **edgartools** parses Form 3/4/5 (2-1 vote), XBRL financials (10-K/10-Q),
   and 8-K sections/full-text — the free substrate for quality composites and
   event signals. ⚠ House caveat stands: edgartools hung ~50 min in our T9
   work; anything using it needs the hang-safe wrapper (NEGATIVE_RESULTS
   discipline) — or we compute from yfinance financials instead.
6. ORJ (a simple alternative earnings-surprise measure) earned 6.78%/quarter
   long-only — **in Chinese data**; evidence PEAD-class signals stay alive in
   less-arbitraged markets, weak transfer prior to US large caps.

### Exits/sizing — the refutations are the finding
7. **REFUTED (0-3): Moreira–Muir "volatility-managed portfolios produce large
   alphas"** — and CONFIRMED (2-0): across **103 equity strategies, managed
   beats unmanaged in only 53/103 with just 8 significant** [S0304405X2030132X].
   Consistent with our own 2026-06-15 finding (vol-management = drawdown
   control at ~flat Sharpe, universe-independent). **Do not build more
   vol-timing alpha machinery; the ATR/vol-target overlay stays what it is:
   risk control, honestly labeled.**

## Refuted claims (do not cite, do not build on)
- PEAD subsumes momentum / is a distinct unsubsumed anomaly (0-3).
- Vol-scaling produces large alphas + big Sharpe gains (0-3).
- Vol-management generalizes across factors as an alpha overlay (0-3).

## Coverage gaps (spend limit — NOT evidence of absence)
- Behavioral/guidance UX (Q3) and event-type short-horizon relevance (Q4)
  angles searched but their claims never reached verification. The
  disposition-effect literature (Odean 3.4pp/yr) is already canon from the
  2026-06-15 research; per-position guidance below leans on that, not on new
  claims. Event-type relevance (8-K items, index adds) remains UNVERIFIED —
  revisit before building event-driven signals beyond descriptive context.

## Build map (this session, in order)
| # | Item | Verified basis | Discipline |
|---|---|---|---|
| 1 | **TRIAL-PEAD-IC** — earnings-surprise composite (analyst-based + announcement-window return, two-way), forward collector | Findings 3, 2 | pre-registered; honest prior "decayed, disputed net-of-cost in large caps"; descriptive until forward IC |
| 2 | **TRIAL-QUALITY-IC** — gross profitability + F-score subset from yfinance financials (the T8 deferred quality slot) | Findings 1, 5 | own trial — the in-flight TRIAL-MULTIFACTOR composite is NOT amended |
| 3 | **Per-position guidance** endpoint — signal + ATR stop distance + move state + fragility context + disposition-effect nudges per holding | Product goal; Odean (canon) | read-only, descriptive, no buy/sell unless a gate has been passed (none has) |
| 4 | (stretch) Chen–Zimmermann bench harness for direction-checking signal definitions | Finding 4 | direction-check only, never an alpha claim for OUR implementation |

## What this does NOT change
"Beat SPY by a good margin" remains something the forward record must earn —
no research finding shortcuts the 24-month discipline, T7, or the profit-
mirage firewall. What this adds: two more evidence-backed selection candidates
accruing forward, and the guidance surface that makes the engine useful for a
real account while the record accrues.
