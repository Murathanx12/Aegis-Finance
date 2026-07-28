# Data strategy under a $100/month ceiling — findings and decision (2026-07-28)

Own research (118 tool calls, live vendor pages and API probes). **Recommendation:
spend $0.** Reasoning below, plus five findings that matter more than the purchase
decision.

---

## 1. The purchase decision: DON'T

The agent's costed basket was **$70.58/mo** — Sharadar Bundle Full History
($41.58/mo annual) + Massive Stocks Starter ($29). Its own stated justification,
after correcting itself, narrowed to: **survivorship-free delisted prices +
`permaticker`**, because free `companyfacts` + DERA now cover PIT fundamentals
from 2009 forward.

**We already have that, for free, and better.** The module holds `crsp_msf`
(1.14M rows, survivorship-free, with delisting codes and returns) plus the CCM
link, via HKU's WRDS entitlement. The agent flagged "check WRDS entitlement" as
the highest-value action in its exercise; it is already answered — four WRDS
harvest batches are on disk.

**And there is a blocker that would have made the purchase self-defeating:**
Sharadar's terms **§8 forbids publishing conclusions derived from the data without
written approval.** The deliverable of this program is a paper. Buying data that
restricts publication to support a publication is incoherent.

Remaining genuine gap: **daily CRSP (`crsp.dsf`) for the general universe** — the
constraint that forced today's monthly-resolution departure on
TRIAL-EVENT-8K-FILTER. That is an **attended WRDS tap, not a purchase.** No vendor
in the $100 tier sells a survivorship-free daily panel back to 2004.

**Decision: no subscription. Keep the $100 unspent.** Revisit only if a registered
trial is blocked by a specific, named field that WRDS does not carry.

## 2. Our 8-K freeze rule is now vendor-documented, not merely inferred

TRIAL-EVENT-8K-FILTER bans full/quarterly indexes as an event source on the
grounds that they are retroactively rebuilt. **SEC's own webmaster FAQ confirms
it verbatim:** the full and quarterly index files are *"rebuilt weekly, early on
Saturday mornings, so that any post-acceptance correction (PAC) deletes or updates
are incorporated."* The daily index is frozen at build time and **retains deleted
filings.**

Everyone uses full-index because it is convenient. It is the contaminated one.
**This upgrades a design choice into a citable methods point for the paper**, and
it retroactively justifies the `master.YYYYMMDD.idx` regex pin that the near-miss
forced earlier today.

Related: `1993/QTR1` is a 4-filing stub whose accessions carry a
`9999999997-05-…` prefix — paper filings backfilled in 2004. Real daily-index
coverage starts **1994Q1**.

## 3. The finding that is itself a paper contribution: Ken French data is not stable

French published exactly one frozen vintage (`ftp_202412/`). Diffing all **1,182
overlapping months** against today's file:

| Series | Months changed |
|---|---|
| **HML** | **92.8%** |
| **SMB** | **91.5%** |
| **Mkt-RF** | **61.2%** |

Across every decade **including the 1920s**. Full-sample HML premium moved
4.143% → 4.062%/yr; t-stat 3.334 → 3.266. The 1995-2004 subsample moved ~30 bps/yr.

**That is one 18-month vintage step. Same filename, same URL, different numbers.**
Wayback is not a substitute — it returns zero snapshots for the zip because
crawlers skip binaries.

Consequences for us, in order:
1. **INSTR-HARNESS-VALID** validated our proxy factors against French bars
   (0.927 / 0.778 / 0.645). Those correlations were measured against **a vintage**.
   The validation stands, but the paper must state which vintage and date it.
2. `data/ff_factors.parquet` is a snapshot of unknown vintage. **Hash it and
   record the download date** before it is cited.
3. Every factor-model alpha in the ledger inherits this. It does not change any
   verdict — the effect is basis points — but "we regressed on the Ken French
   factors" is an under-specified sentence and our paper should not write it.

**The opportunity:** nobody maintains a public Fama-French vintage archive. Start
hashing monthly now and in three years that is a genuine contribution — and it
costs a cron job.

## 4. yfinance: not survivorship bias — fabrication

`yfinance` returns **BBBY** as a clean continuous series through 2026 with
`longName: "Bed Bath & Beyond, Inc."` — **but the prices are Overstock's**,
showing $18-20 in April 2023 when the real BB&B traded ~$0.25 into Chapter 11.
`OSTK` and `BYON` both 404.

This is the concrete mechanism behind **T7's rejection** (yfinance cannot build a
survivorship-free universe) and it is worse than T7 assumed: the failure is not
absence, it is **wrong data wearing the right name**. Our existing ban on yfinance
for historical delisted names is correct and now has a receipt.

**Checked against our code:** the reported `range=max&interval=1d` →
silent-quarterly-bars bug does **not** apply to us — `market_treemap.py` uses
`period="1y"`. Not a live defect here. The "bankrupt ticker returns HTTP 200 with
zero bars" pattern is worth a targeted audit of the yfinance paths, since a bare
`try/except` would drop the name silently — the house failure mode.

## 5. FRED point-in-time: a real hazard for any backtest path

- `output_type=4` on `fred/series/observations` returns each observation **as
  first published**. The default (`output_type=1`) returns **fully revised** data.
- `pandas-datareader`'s FRED reader **cannot do PIT at all** — it scrapes
  `fredgraph.csv`, no realtime params, silently revised. **Checked: we do not use
  it for FRED.** No `get_data_fred` anywhere in the backtest path.

**But the grep found a different, more relevant exposure.**
`backend/services/factor_model.py:57-58` uses `pandas_datareader` against the
**`famafrench`** source — i.e. it re-downloads whatever vintage French is
currently publishing, on every call. Given §3 (92.8% of HML months change across
one vintage step), this means **the same portfolio analysed twice, months apart,
gets different factor alphas with no code change and no error.** For a live
descriptive attribution that is tolerable; it is not reproducible, and any figure
lifted from this surface into the paper must be pinned to a stored vintage first.
This is the FF-vintage problem showing up in our own code, not the FRED one.
- **NFCI is not a market series.** The Chicago Fed re-estimates and **rewrites it
  in full, weekly.** Using today's NFCI in a 2008 backtest is severe lookahead.
  NFCI is in our 9-factor risk score (`config.py:166`).

**Calibration, so this is not overstated:** our risk score runs **live**, where
today's NFCI is the correct current value — that is not lookahead. The hazard is
confined to **backtest and replay paths**. Measured vintage floors (ICSA 2009-05,
NFCI 2011-05) also mean genuine PIT crash-model validation spans ~17 years and
barely more than one recession — which is worth stating plainly whenever the crash
model's validation is described.

Also: **CFTC's 2018-19 shutdown left no visible gap** — collection continued and
the data was backfilled, so the weekly series looks regular while ~9 weeks were
unknowable in real time. Anything built on COT needs that hard-coded.

## 6. Free sources worth taking (all $0)

- **OSAP `PredictorsIndiv.zip`** — 209 firm-level characteristics, ~1.6 GB, **no
  WRDS required** (only `Price`, `Size`, `STreversal` excluded, all rebuildable).
- **`companyfacts` is vintage-reconstructable** — every fact carries `accn` +
  `filed` + `form`, so filtering `filed <= D` gives a true as-of-D view. Proven on
  a real restatement: AAPL 2008 assets restated −$3.4B in a 10-K/A filed 15 months
  later. Taking the last value per period silently hands you the restated figure
  plus a year of lookahead. ⚠️ The `frames` API is **not** PIT-safe (no `filed`).
- **DERA financial statement data sets** — PIT *schema*, but **not an immutable
  archive**: every file inside `2009q1.zip` bears an internal timestamp of
  **2024-11-21**. A 2009 vintage was physically rewritten in late 2024. Hash your
  own snapshots.
- **NYSE `ftp.nyse.com/ShortData/`** — free, open, back to 2009, no roll-off.
  Strictly better than FINRA RegSHO, which silently rolls off at ~8 years.
- **SEC Form 25/25-NSE** via `form.idx` — authoritative, dated, **CIK-keyed**
  delisting record. ⚠️ Not a delisting list raw: 2023Q2 has 562 including 3M and
  AT&T, which are **bond redemptions** under Rule 12d2-2(a)(2). Drop that rule
  code and it separates cleanly.
- **`github.com/rreichel3/US-Stock-Symbols`** — 1,415 daily commits since
  2021-01-30; **the git history is a daily PIT ticker archive.** Verified: ATVI
  present 2023-09-15, absent today; SIVB and BBBY absent, matching Form 25 dates.
- **SEC fails-to-deliver** — free vintage-dated CUSIP↔ticker map back to Feb 2004;
  recovers dead-ticker mappings `company_tickers.json` has erased.
- **Damodaran's archive** — annual as-published snapshots **1999→2025**, the only
  free dataset treating vintages as a first-class product. Industry × annual only.
- **ICI weekly ETF net issuance** — the only genuinely free flow series; broad
  categories, never per-fund, and **superseded by monthly actuals**, so snapshot
  weekly or you backtest revised data.

**Don't build on:** N-PORT monthly-public (delayed to 2027/2028, and on 2026-02-23
the SEC proposed reverting to quarterly entirely) or Form SHO (exempted until
2028-01-02 — there is nothing to collect).

## 6b. Measured limits (audits run, not vendor copy taken on trust)

- **Bigdata.com / RavenPack has no individual archive tier.** Public news is a
  **5-year rolling window**; the metered model was confirmed empirically when the
  connected account returned "You've used up your credits." It cannot serve a
  2004-2024 study at any individual price.
- **Massive** $29/mo reaches back to **2016**; **Benzinga** $99/mo reaches **2001**
  but consumes the whole budget. Best depth-per-dollar is Massive, and it still
  does not reach our explore window's start.
- **SEC `company_tickers.json` is proven survivorship-filtered** — measured, not
  inferred. This retroactively validates the name-link design choice in
  `aegis_brain/events/name_link.py`, which rejected it on exactly this suspicion.
- **EDGAR full-text search is empirically bounded at 2001** — consistent with the
  TRIAL-TEXT-LAZY spec's refusal to use it (that refusal was made on the
  100-result cap, and the date bound is a second independent reason).
- **Polygon/Massive delisted coverage: 8 of 11** exchange-listed test names, and
  **recycled tickers return the wrong entity** — the same defect class as the
  yfinance BBBY/Overstock fabrication in §4.
- **ALFRED per-series vintage floors cap genuine PIT macro backtests at ~2011.**

## 6c. A methods lesson from the audit itself — worth more than the pricing

The agent's first Polygon sweep returned **0 of 20** names and was **entirely
false misses**: silent rate-limiting returning **HTTP 200 with an empty array**.
Its FINRA start-date measurement was wrong the same way — a query on a non-settlement
date returned empty and was read as "data absent."

**An empty 200 is not evidence of absence.**

This is our house failure mode in a new costume, and the agent connected it to the
right receipt unprompted: it is the same mechanism that inflated **EODHD phase-1
to 16/20 before phase-2 came back 14/20** (NEG_RESULTS §8). Any future data audit
must pace its requests and assert against a **known-good control** before
recording an absence. Add to the silent-fragility checklist.

## 7. Actions

1. **No purchase.** Keep the $100.
2. **Hash and date `data/ff_factors.parquet`** before any paper citation; start a
   monthly French snapshot.
3. **Cite the SEC webmaster FAQ** in the paper's methods section as the receipt
   for the daily-index rule.
4. **Audit yfinance paths** for the zero-bars-with-HTTP-200 pattern (silent
   fragility skill).
5. **Note in the crash-model writeup** that PIT validation is bounded by vintage
   floors (ICSA 2009-05, NFCI 2011-05) — ~17 years, ~one recession.
6. `polygon.io/pricing` now 301s to `massive.com`; `backend/services/polygon_client.py`
   is worth a look before it breaks on someone else's schedule.
