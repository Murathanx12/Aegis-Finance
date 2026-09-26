# Book: the Bloomberg dress rehearsal and Murat's core-satellite (frozen 2026-09-27, entry 2026-09-28 open)

**PRODUCT_EXPERIMENT; nothing here is a claim.**

Source of the design: `docs/reviews/REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md` §9 (the
one-page strategy and the 2026-10-26 check). Fable accepted it as the dress rehearsal.
Selection logic: `backend/services/rehearsal_book.py` (tested in `backend/tests/test_rehearsal_book.py`).
Freeze script: `scripts/bloomberg_rehearsal_book.py --freeze`. Receipt:
`backend/data/optimus/rehearsal/rehearsal_2026-09-27.json`. Ledger:
`backend/data/optimus/llm_portfolio/books.jsonl` (append only, through `llm_portfolio.freeze` / `twins`).
LLM spend $0. No order was placed. Both books are paper books, $1M each.

## Book A: `bloomberg_rehearsal_2026-09-27`

- **book_id `4d0cebfeb8867fb8`**, kind `competition`, benchmark URTH (the WLS proxy).
- Objective: "Relative P&L vs WLS, 2026-10-12 to 2026-11-13". This record is the rehearsal, graded
  over the 21 sessions from 2026-09-28 to **2026-10-26**.

### Construction (as run)

| step | rule | names left |
|---|---|---|
| universe | xs_ranker eligibility on 2026-09-27: last bar ≤ 5 days old, $3 ≤ close ≤ $10k, median 63-session $-volume ≥ $3M, ≥ 126 bars, no ETF | 2,890 |
| size | small/mid: latest SEC `shares` (filed + 2d) × last close within $0.3B – $10B | 1,568 |
| tilt | fundamentals score ≥ its median (0.493) | 683 |
| event | Q3 print estimated inside the 21-session window (below) | 114 |
| rank | σ63-predicted \|21-session move\| = σ63 × √21 × √(2/π), descending | |
| crowd cap | ≤ 2 semiconductor names (GICS 453010; unclassified names by ρ(SMH, 63) ≥ 0.6) | |
| cluster | skip a name with ρ63 > 0.8 to a name already picked | |
| size | 10 names × 10%, long only, fully invested, no cash | 10 |

**The earnings estimate.** The source is EDGAR 8-K item 2.02 (`edgar_8k/eightk_items.parquet`, the
freeze gate's own source). The estimate is the last 2.02 plus 91 days.

A name qualifies only when:

- the estimate lands between 09-28 and 10-26; **and**
- the same-quarter-last-year cross-check lands there too, when it exists. The cross-check is last
  year's 2.02 nearest to (estimate − 364d), rolled forward.

`EARNINGS_UNKNOWN` never qualifies. That covers:

- no 2.02 history;
- a last 2.02 more than 150 days old;
- an estimate or cross-check that falls before the window.

The cross-check was added after the first dry run:

- **CNXC** read 09-28 on cadence, but last year's same quarter printed 09-24. That is inside the 8-K
  file's gap: the file ends 2026-09-03, 24 days before the freeze.
- **NVCR** read 10-22 on cadence, against 10-29 last year.
- **HZO** read 10-22 on cadence, against 11-12 last year.

All three are now out. Of the 2,890 names: 346 are IN_WINDOW, 1,954 OUTSIDE_WINDOW and 590
EARNINGS_UNKNOWN.

**The fundamentals score is a PROXY, and it is named as one.** The +39 bps/month was a walk-forward
LightGBM over 25 JKP features, on a panel that ends 2024-12. That model is not fitted live.

The live score is the within-universe percentile-rank average of five SEC ratios from
`fundamental_features`, joined at filed + 2d:

- `gp_at` +
- `ope_be` +
- `ni_be` +
- `at_gr1` −
- `debt_at` −

Rules applied to the ratios:

- A name needs at least 3 of the five legs.
- Return on equity is NaN on negative equity. The first cut read STRO's ni_be as +2.2 on a deficit.
- Asset growth outside −50% … +200% is read as a data defect. BZ read −77% and FUTU −70%; both are
  foreign filers.

### The ten names

| # | name | weight | σ63/day | σ over 21 sessions | predicted \|move\| | fund. | mkt cap | last 8-K 2.02 | Q3 estimate (+91d) | last-year check | session | sector |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | NVEC | 10% | 6.54% | 30.0% | 23.9% | 0.76 | $0.53B | 2026-07-22 | 2026-10-21 | 2026-10-21 | 18 | semis |
| 2 | MAN | 10% | 4.52% | 20.7% | 16.5% | 0.70 | $2.67B | 2026-07-16 | 2026-10-15 | 2026-10-15 | 14 | staffing |
| 3 | RHI | 10% | 3.90% | 17.9% | 14.3% | 0.84 | $3.78B | 2026-07-23 | 2026-10-22 | 2026-10-21 | 19 | staffing |
| 4 | ACI | 10% | 3.71% | 17.0% | 13.6% | 0.71 | $5.66B | 2026-07-23 | 2026-10-22 | 2026-10-13 | 19 | food retail |
| 5 | PEGA | 10% | 3.57% | 16.4% | 13.1% | 0.73 | $5.55B | 2026-07-21 | 2026-10-20 | 2026-10-20 | 17 | software |
| 6 | IRDM | 10% | 3.45% | 15.8% | 12.6% | 0.64 | $5.17B | 2026-07-22 | 2026-10-21 | 2026-10-22 | 18 | telecom |
| 7 | HELE | 10% | 3.38% | 15.5% | 12.3% | 0.57 | $0.67B | 2026-07-08 | 2026-10-07 | 2026-10-08 | 8 | household durables |
| 8 | SMPL | 10% | 3.28% | 15.0% | 12.0% | 0.64 | $0.85B | 2026-07-09 | 2026-10-08 | 2026-10-22 | 9 | food products |
| 9 | PRGS | 10% | 3.26% | 14.9% | 11.9% | 0.59 | $1.61B | 2026-07-22 | 2026-10-21 | none (cadence only) | 18 | software |
| 10 | AGYS | 10% | 2.91% | 13.3% | 10.6% | 0.70 | $2.81B | 2026-07-27 | 2026-10-26 | 2026-10-26 | 21 | software |

The earnings source for every row is "EDGAR 8-K item 2.02 (edgar_8k/eightk_items.parquet); last 2.02 + 91d".

Notes on the ten:

- One semiconductor name (NVEC). The cap of 2 did not bind.
- The freeze gate's construction and timing checks all passed:

  | check | value |
  |---|---|
  | max name ≤ 15% (k ≤ 10) | 10% |
  | effective N ≥ 8 | 10 |
  | no ρ > 0.8 cluster above 40% | none |
  | no name above 10% printing in the first 5 sessions | none |
  | largest name to zero ≤ $150k | $100k |
  | bars ≤ 1 session old | 2026-09-25 |

- Selection is not applied: this book is not a library rule, so it has no backtest row.
- Two names sit at the edge of the window:
  - AGYS's estimate is the last session.
  - PRGS has no same-quarter 2.02 last year, so it stands on cadence alone.

### Twins (all frozen with the parent)

| twin | book_id | holds |
|---|---|---|
| `next_k` (ranks 11–20, same filters, equal weight) | `d1b5b566e58b9b39` | BMI, IMAX, WRLD, ALK, NE, LAZ, WFRD, HAPN, MOH, SCHL |
| `random_same_band` (llm_portfolio.twins, seeded by name) | `672d2b4cdcdb76a0` | FSS, EMN, PCRX, BLSH, CNR, ESQ, UEC, HIMX, NAT, CBT |
| `iwm` | `e1211de4cbd952c0` | IWM 100% |
| `spy` | `dbc218ccb553a6ba` | SPY 100% |

### Declared on the freeze record (`declared` on the book's ledger row)

**Expected σ.** The basket σ is √(w′DRD). D is the names' σ63 and R is their realised 63-session
correlation, with an average pairwise ρ of 0.18.

| measure | value |
|---|---|
| daily σ | **1.81%** |
| σ over 21 sessions, absolute | **8.31%** |
| σ over 21 sessions, relative to SPY | **8.39%** |

The rank-11–20 twin's σ over 21 sessions is 4.61%. The review's back-of-envelope figure was ~12%
absolute; the names that qualified are calmer than its assumed 4%/day.

**Expected relative return.** It is **0 ± 8.4%** over 21 sessions. No directional edge is claimed.

**Factor exposure.** The factor fit is an OLS of the basket's daily return at its current weights,
over 126 sessions. Each value is shown as the beta ± its standard error.

| exposure | declared value |
|---|---|
| SPY | **0.89 ± 0.21** |
| IWM − SPY | **0.94 ± 0.22** |
| SMH − SPY | **−0.03 ± 0.17** |
| MTUM − SPY | **−0.73 ± 0.24** |
| daily alpha (in-sample, not a forecast) | +0.25% ± 0.14% |

The univariate betas are SPY 0.39, IWM 0.41 and SMH −0.11.

Comparison with the review's declared table:

- IWM − SPY ≈ +1 and SMH ≤ 0.3 match.
- MTUM is not ≈ 0. The basket is anti-momentum at −0.73. That is a style exposure the book did not
  choose, and it is declared here so that 10-26 can check it.

**Stop, in σ units.** The rule is:

z(t) = cumulative relative P&L at session t / (1.83% × √t)

Act only if z < −2 (2σ, **not a percent**). There is no per-name stop inside the window: the print
is the bet, and a −2% stop is ~0.5 daily σ on these names. For reading only, −2σ corresponds to
these relative returns:

| session | 1 | 5 | 10 | 21 |
|---|---|---|---|---|
| −2σ as a relative return | −3.7% | −8.2% | −11.6% | −16.8% |

**Worst case (protocol 4).**

- Gross is 10 × 10% = 100% of $1,000,000, gross/equity 1.00, long only.
- One name to zero = **−$100,000**.
- A 3σ book day = −5.44% = **−$54,426**.

**Rotation (declared, not automated).** Once a name has printed, the contest book rotates it into
the next un-printed name. The frozen rehearsal record does not rotate.

### The three 2026-10-26 checks, verbatim

1. **move-size rank correlation ≥ 0.3**. This is Spearman(σ63-predicted \|21-session move\|, realised
   \|move\|) over the book's and the rank-11–20 twin's names.
2. **realised factor exposure within ±0.3 of declared**. The betas checked are SPY, IWM − SPY and
   SMH − SPY over the 21 sessions.
3. **fills vs plan**. Names and weights at entry, and entry at the 2026-09-28 open.

Relative P&L is printed as a z-score and acted on only if z < −2.

Two honest caveats about check 2:

- The declared betas have SEs of ~0.2 on 126 sessions.
- A 21-session realised beta has an SE of roughly 0.2 × √(126/21) ≈ 0.5.

So ±0.3 will often fail by noise alone. Read a failure beside its SE, not as a verdict.

**Fallback** (review §9). The book falls back if, on 10-26, both hold:

- check 1 ≤ 0; **and**
- the realised book σ is < 0.5 × 8.31%.

The contest book then becomes 20 × 5% fundamentals-ranked, with a WLS β of ≈ 1.

## Book B: `murat_core_satellite_2026-09-27`

- **book_id `5517aa50a29bc95b`**, kind `personal`, benchmark SPY.
- The horizon is 126 sessions, graded beside the 21-session read.

| sleeve | holding | weight |
|---|---|---|
| core | SPY, one position; it never stops | 80% |
| satellite | fundamentals proxy top-10 over the whole eligible universe, equal weight, small caps allowed, no cap | 10 × 2% |
| cash | declared row | 0% |

The satellite names are:

| name | fundamentals score | legs | liquidity band |
|---|---|---|---|
| PDD | 0.99 | 3 | large |
| FIZZ | 0.96 | 5 | small |
| MANH | 0.95 | 4 | large |
| BZ | 0.95 | 3 | mid |
| CMG | 0.94 | 4 | large |
| EXPO | 0.93 | 3 | mid |
| EXEL | 0.93 | 5 | large |
| LZ | 0.92 | 5 | small |
| REAL | 0.92 | 3 | mid |
| BBW | 0.91 | 3 | small |

Two notes on this book:

- **Differs from the review.** The review sized the satellite at k = 25 and ≤ 1% per name. This book
  follows Murat's instruction instead: top-10 at 2% each, no cap.
- **Foreign filers.** PDD and BZ file in RMB. The ratios are same-currency, but see the
  asset-growth guard above.

**Tracking error.** It is computed from 252 realised sessions:

TE = 0.2 × σ(sleeve − SPY) = 0.2 × 20.4% = **4.09%/yr**

That is on the ≈ 4% target. The inputs:

| input | value |
|---|---|
| sleeve σ | 22.5%/yr |
| SPY σ | 13.0%/yr |
| ρ(sleeve, SPY) | 0.44 |
| sleeve β | 0.76 |
| book σ | 13.0%/yr |
| book β | 0.95 |

**Stop, in σ units.** The satellite is measured against its random-sleeve twin:

z = cumulative difference / (20.4% × 0.2 × √(t/252))

At the 126-session check, drop the satellite to SPY only if z < −2. That is ≈ −5.8% of the book at
126 sessions. The core never stops, and the stop is never read on 21 days.

**Worst case.** The largest name to zero = −2% = **−$20,000**. The sleeve to zero = −$200,000.

**Twins.**

| twin | book_id | holds |
|---|---|---|
| `spy` | `923e79dbd12a963a` | SPY 100% |
| `random_sleeve` | `c05861aebd4361c0` | SPY 80% + AVR, GSAT, PSX, CW, WAY, AMRC, MATV, CORZ, GWW, SLDE at 2% (same-band random, seeded) |

**On 10-26, Book B checks only** "realised factor exposure within ±0.3 of declared" and "fills vs plan".

## What was not done

- The contest's own rules are not verified against WLS membership: `wls_membership_checked: False`
  on the competition constraints. The book holds US listings only.
- Nothing rotates automatically after a print.
- The 8-K tape ends 2026-09-03. A name that pre-announced or printed between 09-04 and 09-27 is
  invisible to the estimate unless its cadence or last-year date fell before the window.

PRODUCT_EXPERIMENT; nothing here is a claim.
