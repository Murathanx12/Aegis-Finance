# Data Options — free coverage vs. paid Sharadar (decision aid)

**Date:** 2026-06-20 · **Type:** DECISION AID ONLY — no code, no deps, no wiring changed.
**Companions:** [`DATA_INTEGRITY.md`](DATA_INTEGRITY.md) (the directional-vs-sizing gate),
[`V3_RESEARCH_SYNTHESIS_2026_06_20.md`](V3_RESEARCH_SYNTHESIS_2026_06_20.md) (the strategy).
**Gate it must respect:** `backend/services/data_integrity.py` (`SOURCE_GUARANTEES`).

## 0. The frame (do not skip)

Aegis decided **2026-06-20: stay on free/yfinance, directional-only.** Forward paper
lanes (the 24-month rule) are the **only sizing-grade truth.** This document answers a
narrow question:

> Which **free** sources extend coverage **without** reintroducing survivorship bias or
> point-in-time (PIT) violations — and exactly what **paid Sharadar** would unlock?

The hard, honest constraint that governs every verdict below:

- **Survivorship bias and restated (non-PIT) fundamentals are NOT fixable with free data.**
  Only a delisted-inclusive, as-reported feed (i.e. paid Sharadar/Tiingo/Norgate/CRSP)
  removes them. Our own **T7 audit** proved free price feeds can build a
  survivorship-free universe for only **1/20** delisted names.
- Therefore the *only* free data that is safe to add is data whose grade **does not
  depend on cross-sectional equity survival or fundamental PIT-ness**:
  - **Macro time-series** (FRED) — one series per economy, nothing to "survive."
  - **PIT-by-construction filings** (EDGAR) — stamped with the filing date.
- Any free *equity-cross-section* data (prices, restated fundamentals) stays
  **DIRECTIONAL** in the gate — it may **kill** a candidate, never **size** a position.
- **Everything new enters as a TESTED candidate (forward-IC), never asserted.** Adding a
  source is not adding a signal; the signal must earn a lane forward (t > 3.0, IC, DSR/
  effective-N), exactly as T8/T9/T10 did.

What is already wired (so we don't double-count): ~23 FRED series in
`backend/config.py` (`fred_series`), incl. `hy_oas` (BAMLH0A0HYM2), `ig_oas`
(BAMLC0A0CM), `nfci` (NFCI), `yield_spread` (T10Y3M), `lei` (USSLIND), `sahm_rule`
(SAHMREALTIME), `initial_claims` (ICSA), `initial_claims_4wk` (IC4WSA), SLOOS
(`sloos_ci`/`sloos_cc`), `tips_10y` (DFII10), `recession_prob` (RECPROUSM156N), VIX
(VIXCLS), plus **net-liquidity** (WALCL, WTREGEN, RRPONTSYD via `net_liquidity.py`).
Price/fundamentals = yfinance (DIRECTIONAL). EDGAR = `edgartools` (13F collector live).

---

## 1. Extra FRED credit / macro series — **SAFE TO ADD** (with a PIT caveat)

**Verdict: SAFE-TO-ADD.** FRED is single-series macro: there is no equity cross-section,
so **no survivorship bias** and no fundamental-restatement problem. These are free, deep
(decades of history), and several are genuinely *leading*.

**The one honest caveat — vintage / revision (a mild PIT issue):**
Our fetch path uses `fred.get_series(...)` (see `net_liquidity.py`, `data_fetcher.py`),
which returns the **latest-revised** value for every historical date. Many macro series
are revised after first release (GDP, payrolls, LEI, industrial production, even NFCI is
re-estimated). So a backtest reading today's revised series at an old date is
**reading a value that wasn't knowable then** — a real, if mild, lookahead.

- **Truly PIT macro requires ALFRED vintages** (FRED's archive: `realtime_start` /
  `realtime_end`, or the `…_vintage` ALFRED endpoints). `fredapi` exposes
  `get_series_first_release` / `get_series_as_of_date` / `get_series_all_releases` for
  this. We do **not** use them today.
- **Severity is series-dependent.** Market-priced / financial-conditions series
  (`hy_oas`, `ig_oas`, `nfci`, `T10Y3M`, `VIXCLS`, OAS family) are **near-final at
  release** → the revision lookahead is negligible; treat as effectively PIT.
  **Survey/estimated/national-accounts** series (`lei`, `recession_prob`, `INDPRO`,
  payroll-derived) revise materially → for those, a sizing-grade backtest should pull the
  **first-release vintage**, not the revised line.
- **Practical rule for this repo:** free FRED is fine for the **descriptive crisis/
  fragility overlay** (a continuous exposure multiplier read *live*, where "latest
  revised = latest known" is correct by construction). For any **historical single-stock
  backtest** that uses a revised macro series as a feature, flag it and prefer the
  first-release vintage — otherwise stamp the result DIRECTIONAL like everything else.

### Concrete series worth adding (free, leading, NOT yet loaded)

| Series ID | Name | What it adds | Revision caveat |
|---|---|---|---|
| `BAMLH0A0HYM2EY` | HY effective **yield** (level) | Complements `hy_oas` spread; absolute funding cost for distressed issuers | Market-priced → ~PIT-clean |
| `BAMLC0A4CBBB` / `BAMLH0A3HYC` | BBB OAS / CCC-&-lower OAS | **Credit-quality term structure** — CCC-minus-BBB blowout is the cleanest "credit stress is migrating down the stack" tell; leads broad HY | Market-priced → ~PIT-clean |
| `BAMLEMCBPIOAS` | EM corporate OAS | Cross-border credit / dollar-funding stress (contagion channel) | Market-priced → ~PIT-clean |
| `TEDRATE` *(discontinued)* / `SOFR`–`DFEDTARU` spread | Money-market funding stress | Bank/funding stress proxy (TED is dead; build a SOFR-OIS-style proxy from existing rate series) | Market-priced → ~PIT-clean |
| `T10Y2Y` | 10Y–2Y term spread | We have `T10Y3M`; the 2Y version is the more-cited recession curve and inverts/dis-inverts on a different schedule | Market-priced → ~PIT-clean |
| `T10YIE` / `T5YIFR` | 10Y breakeven / 5y5y fwd inflation | Forward inflation expectations (regime input for the rotator's duration sleeve) | Market-priced → ~PIT-clean |
| `STLFSI4` / `KCFSI` | St. Louis / KC Fed Financial Stress Index | Composite financial-conditions stress — orthogonal construction to NFCI; good cross-check | Mild revision (estimated) |
| `ANFCI` | **Adjusted** NFCI | NFCI with the business-cycle component removed → cleaner "financial stress beyond what growth explains" | Mild revision |
| `DRTSCIS` / `SUBLPDCLCT` | SLOOS demand / spreads detail | Deepens the credit-tightening read we already use (`sloos_ci`/`sloos_cc`) | Quarterly, revised |
| `USEPUINDXD` / `GEPUCURRENT` | Economic Policy Uncertainty (daily / global) | The FRED-hosted uncertainty proxy that **replaces the removed `gpr_world`** (GPR was never FRED-hosted — see config note). **Crisis-engine volatility input only, never alpha** (GPR-class signals are weak for returns — synthesis §5). | News-index, ~PIT |
| `WALCL`,`WTREGEN`,`RRPONTSYD` | *(already via `net_liquidity.py`)* | Net liquidity = WALCL − TGA − RRP | Weekly, ~PIT |

**Net add:** the highest-value cluster is the **credit-quality term structure**
(`BAMLC0A4CBBB`, CCC OAS, EM OAS) plus **`ANFCI`/`STLFSI4`** as orthogonal
financial-conditions cross-checks. These directly strengthen the descriptive crisis/
fragility multiplier (synthesis §1, §7) where credit spreads are rated STRONG and free.
**Each still enters as a registered overlay candidate, validated forward — not asserted.**

---

## 2. Stooq — **CAUTION** (use as a data-quality cross-check, not a survivorship fix)

**Verdict: CAUTION / narrow use.** Stooq offers free daily OHLCV (CSV-downloadable,
broad global incl. US equities, ETFs, indices, FX, commodities) with no API key.

- **Does it fix survivorship?** **No.** Stooq is a current-listings price archive like
  yfinance; it does not provide a clean, delisted-inclusive, PIT *membership* universe.
  Whatever delisted history it incidentally retains is partial and unverified — it does
  **not** clear `survivorship_probe` / `assert_survivorship_safe`. It would register
  **DIRECTIONAL** (`survivorship_free=False`), same grade as yfinance.
- **What it IS good for:** a **second independent price source** to **cross-check
  yfinance data quality** — detect bad splits/dividends, stale bars, off-by-a-day
  alignment, suspicious gaps. A cheap robustness check on the directional inputs we
  already trust only directionally.
- **Risk if misused:** treating Stooq as "another universe" would silently re-introduce
  survivorship bias under a new name. It must **not** be registered sizing-grade, and any
  backtest run on it stays DIRECTIONAL-stamped.

**Recommendation:** keep Stooq on the shelf as an *optional QA cross-check vs yfinance*.
It does not move the integrity needle and is not a priority.

---

## 3. EDGAR full-text / filings — **SAFE TO ADD** (genuinely PIT, free)

**Verdict: SAFE-TO-ADD (genuinely PIT).** `edgartools` is already a dependency and the
13F collector is live. EDGAR filings are **timestamped by their actual filing date** →
**PIT by construction**: an 8-K read at its filing date is exactly what was knowable then.
There is **no survivorship issue** for the *text* (a filing exists for the date it was
filed regardless of whether the issuer later delisted), and **no restatement lookahead**
if you key on `filing_date`. This is the cleanest free alt-data Aegis can add.

**What it unlocks (synthesis §4 rates edgartools ADOPT):**
- **8-K event mining** — material events, guidance, management changes, restructurings;
  filed promptly → fast, dated signal.
- **10-K / 10-Q risk-factor diffs** — year-over-year change in Item 1A language is a
  well-studied leading risk tell; PIT because each filing is dated.
- **Guidance / MD&A language mining** — capex-guidance and backlog/supply-chain language
  is **Murat's demonstrated causal edge** (semis→tech lead-lag; synthesis §5 rates it
  STRONG & causal). EDGAR is the PIT-clean substrate for it.
- **As-reported financials via the filing itself** — pulling fundamentals from the actual
  10-K/10-Q (keyed to `filing_date`/`datekey`) is the *one* way free data gets toward PIT
  fundamentals — but it is **single-issuer, hand-built, and does not solve the
  cross-sectional survivorship problem** (you still can't enumerate the past universe
  including delisted names). So it helps PIT-ness for a *named* stock, not universe-level
  sizing grade.

**The hang-safety caveat (already in the repo, must carry forward):** the `edgartools`
path has **hung before** (MEMORY notes Piotroski/quality deferred because "edgartools
hangs"; synthesis §4 says "keep the hang-safe wrapper"). Any expansion past 13F must go
through a **timeout-bounded, hang-safe wrapper** and respect the **shared SEC rate
limiter** — recall the **2026-06-17 prod-403 incident** where raw unpaced `requests.get`
to `www.sec.gov/Archives/` tripped SEC's 10/s cap and failed 100% silently in prod
(green offline, dead live). All SEC fetches must route through the single `_sec_get`
choke-point with the `_RATE_LIMITER` and `SEC_USER_AGENT`.

**Recommendation:** EDGAR text (8-K events, risk-factor diffs, guidance mining) is the
**best free PIT extension** and the natural substrate for the capex/backlog causal-chain
thesis. Build hang-safe + rate-limited; validate any derived signal forward-IC.

---

## 4. Sharadar (PAID) — exactly what it unlocks

**Verdict: the one source that actually flips DIRECTIONAL → SIZING.** Already registered
**SIZING** in `SOURCE_GUARANTEES` (`survivorship_free=True, point_in_time_fundamentals=True`)
— pending only the adapter + key. Distributed via **Nasdaq Data Link**.

| Product | What it is | Why it matters |
|---|---|---|
| **SEP** | Sharadar Equity Prices — daily OHLCV **including delisted tickers** | **Removes survivorship bias.** This is the half free data cannot supply: every name that went to zero is present, so a backtest "over the universe" stops being a backtest over the winners. Passes `survivorship_probe`. |
| **SF1** | Core US Fundamentals, **as-reported / point-in-time** | **Removes the restatement lookahead.** Each row carries `datekey` (the filing date); filtering `datekey <= as_of` means the model only ever sees what was knowable then. This is the PIT half. |
| **SF3 / SFP / TICKERS / actions / index membership** | 13F holdings, fund prices, ticker metadata, corporate actions, **PIT index membership** | PIT universe construction (e.g. "S&P 500 *as of* 2008-09-12") — needed so a cross-sectional ranker selects from the *then*-investable set, not today's. |

**Why both halves are required:** the gate (`SourceGuarantees.grade`) makes a source
SIZING only if `survivorship_free AND point_in_time_fundamentals`. SEP gives the first,
SF1 the second. A source with only one stays DIRECTIONAL by construction — which is
exactly why all the free options above cannot reach sizing grade.

**Cost ballpark:** ~**low hundreds of USD/year** (the Sharadar bundle on Nasdaq Data
Link; far below CRSP/Compustat institutional pricing). Synthesis §3 lists **Tiingo** and
**Norgate** as comparable affordable-clean alternatives; **CRSP/Compustat = skip
(institutional-priced)**.

**One-session adapter path (already documented in `DATA_INTEGRITY.md`):**
1. Subscribe (Nasdaq Data Link / Sharadar); put `NASDAQ_DATA_LINK_API_KEY` in `.env`.
2. Implement `SharadarProvider(BaseProvider)` in `backend/services/providers/` serving
   `get_equity_history` (SEP, delisted-inclusive) and `get_fundamentals` (SF1, filtered
   `datekey <= as_of` for PIT) — mirroring existing provider adapters.
3. Point the backtest price source at `"sharadar"`. The gate then passes sizing-grade and
   **every single-stock backtest becomes sizing-grade with no other change** — and
   `assert_survivorship_safe(survivorship_probe(...))` will pass instead of being the
   gate that holds the line.

**Until then (current decision):** all single-stock backtests are **directional-only
(falsification).** Forward paper lanes remain the only sizing-grade evidence (24-month
rule). This document does **not** recommend buying Sharadar now — only documents that it
is the single clean lever if/when Aegis goes sizing-grade.

---

## 5. If adding ONE thing next (free) — ranked recommendation

> **Caveat that overrides the ranking:** none of these "fix" survivorship. Free data
> cannot. Each enters as a **TESTED candidate validated FORWARD (forward-IC, t > 3.0,
> DSR / effective-N), never asserted.** Adding a *source* is not adding a *signal*.

1. **EDGAR 8-K / risk-factor-diff / guidance text (free, genuinely PIT).** Best
   risk-adjusted free extension: PIT by construction, no survivorship issue for the text,
   `edgartools` already a dep, and it is the substrate for **Murat's capex/backlog causal
   edge** (synthesis §5: STRONG & causal). **Condition:** hang-safe wrapper + shared SEC
   rate limiter (the 403 lesson). Enters as a forward-IC candidate alongside T8/T9/T10.

2. **Credit-quality term-structure FRED series** (`BAMLC0A4CBBB` BBB OAS, CCC OAS,
   `BAMLEMCBPIOAS` EM OAS) **+ `ANFCI`/`STLFSI4`.** Free, leading, market-priced
   (~PIT-clean), and they sharpen the **descriptive crisis/fragility multiplier** where
   credit spreads are rated STRONG. Lowest-effort add; descriptive overlay only (never a
   binary crash call — the n≈2 problem).

3. **Stooq as a yfinance QA cross-check.** Real but minor value (data-quality robustness);
   **does not** improve integrity grade. Shelf item, not a priority.

**Not recommended now:** buying Sharadar. It is the *correct* lever for sizing-grade, but
it contradicts the 2026-06-20 directional-only decision. Document it (done, §4) and
revisit only when a single-stock candidate has survived enough forward evidence to
justify paying to size it.

---

### Honest bottom line

Free data can **extend coverage** (more leading macro/credit series; PIT filing text) and
can **cross-check quality** (Stooq), but it **cannot** make single-stock backtests
sizing-grade — survivorship bias and fundamental PIT-ness are removable **only** by a
delisted-inclusive, as-reported feed (Sharadar/Tiingo/Norgate). The directional-vs-sizing
gate in `data_integrity.py` is the enforcement of exactly this truth, and forward paper
lanes remain the only sizing-grade evidence Aegis has.
