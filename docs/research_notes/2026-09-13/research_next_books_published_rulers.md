# Research note — published rulers, the next three books, and Book C's news sign

STATUS: COMPLETE first pass, 2026-09-13. Local-repo findings (§0, §4) are verified
directly against the parquet files on disk (schemas read with pandas/pyarrow, not
assumed). Web-sourced numbers (§1-§3, §5) come from WebSearch/WebFetch against the
publishers' own pages and the papers' abstracts/PDFs; every claim below names its
source and is marked NOT FOUND where a fetch failed rather than filled from memory.

## 0. The single biggest local finding, ahead of everything else

**We do not need to download OSAP or JKP from the web to get a published-style
factor ruler for most of this task — Jensen-Kelly-Pedersen's own firm-characteristic
panel is already on disk**, pulled from WRDS's `contrib_global_factor` schema (JKP's
own WRDS-contributed table, not a scrape, confirmed by reading the parquet schemas
directly):

- `backend/data/optimus/wrds/jkp_full/jkp_usa_1926_1930.parquet` ... `jkp_usa_2012_2012.parquet`
  — 5-year (2-year post-1966) chunks, **1926-2012**, USA, no permno pre-filter
  ("ALL US securities ... full-cap panel is the point," per the chunk's own meta.json).
- `backend/data/optimus/wrds/jkp_global_factor_usa.parquet` — the 2013-2024
  continuation, 558,369 rows, PIT-stamped on `eom` ("JKP characteristics are
  formation-date stamped; each char derives from data public by then per JKP
  construction — spot-audit before first trial use," per its own meta.json).
- Columns (340+): `be_me`, `gp_at`, `ni_at`, `ocf_at`, `resff3_12_1`/`resff3_6_1`
  (momentum **residualized to FF3** — literally the Grinblatt-Han-adjacent
  construction already computed), `qmj`/`qmj_prof`/`qmj_growth`/`qmj_safety`
  (quality-minus-junk, all four sub-scores), `age`, `rd_at`,
  `oaccruals_at`/`taccruals_at`, `mispricing_perf`/`mispricing_mgmt`
  (Stambaugh-Yuan composites), the full momentum family (`ret_12_1` ... `ret_60_36`),
  **seasonality** (`seas_1_1an`/`na` ... `seas_16_20an`/`na` — Heston-Sadka's own
  lag structure, already computed), liquidity/microstructure (`ami_126d`,
  `turnover_126d`, `zero_trades_252d`, `rvol_21d`, `ivol_capm_21d`/`ivol_ff3_21d`,
  `beta_60m`/`beta_252d`/`beta_21d`/`beta_dimson_21d`), and `ret_exc_lead1m`
  (forward excess return — the label column, PIT-dangerous if joined on the wrong
  date, but present).
- This is the **characteristic panel**, not JKP's own long-short factor-RETURN
  series (what jkpfactors.com serves for a side-by-side ruler — see §1). It is the
  raw material to build our own version of any of the 153 JKP-themed sorts on our
  own universe, costs and construction.

This reframes the task: the three books proposed in §3 all use JKP columns already
computed on disk back to **1926-1990**, in preference to building a new
characteristic from raw CRSP+Compustat, because the marginal engineering cost of
each is now "write the sort and the twin," not "build the feature."

## 1. The published rulers we can download

### Open Source Asset Pricing (Chen & Zimmermann) — openassetpricing.com

Fetched directly from `openassetpricing.com/data/` (October 2025 release) and the
`OpenSourceAP/CrossSection` GitHub repo's `SignalDoc.csv` (fetched raw from GitHub —
this file itself downloaded cleanly with no login).

- **Downloadable today, no login observed** (links are public Google Drive folders):
  (a) one wide CSV of **monthly long-short returns for 212 predictors**; (b) the
  same 212 as individual CSVs (one per predictor, e.g. `BM.csv`, `DivSeason.csv`);
  (c) **209 predictive firm-level characteristics in wide format, stock-level, 1.6 GB
  zipped CSV** (excludes Price/Size/STreversal — "available via CRSP" i.e. trivial to
  add ourselves); (d) a daily portfolio-returns folder; (e) `SignalDoc.csv`, the
  per-predictor metadata file.
- **`SignalDoc.csv` columns** (fetched verbatim): `Acronym, Cat.Signal, Predictability
  in OP, Signal Rep Quality, Authors, Year, LongDescription, Journal, Cat.Form,
  Cat.Data, Cat.Economic, SampleStartYear, SampleEndYear, Acronym2, Evidence Summary,
  Key Table in OP, Test in OP, Sign, Return, T-Stat, Stock Weight, LS Quantile,
  Quantile Filter, Portfolio Period, Start Month, Filter, Notes, Detailed Definition,
  GScholarCites202509`. So yes — **it names the original paper, its sample, its
  reported t-stat and return, per predictor**, exactly as asked. Example rows
  fetched: `REV6` (Chan-Jegadeesh-Lakonishok 1996, JF, analyst-forecast-revision
  category), `AnnouncementReturn` (same authors/paper, earnings-event category),
  `Mom12m`/`Mom6m` (Jegadeesh-Titman 1993), `DolVol`/`ShareVol` (volume category).
- **What a signal-return-CSV row looks like**: could not be pixel-verified (the
  fetch tool summarizes rather than dumps raw bytes), but by construction it is one
  row per month per predictor with the realised long-short portfolio return — the
  standard OSAP wide-CSV shape documented in their own paper and GitHub README.
- **Licence: NOT explicitly stated on the data page itself** (the fetch found no
  terms-of-use block there); the companion R download package
  (`OpenSourceAP.DownloadR`) **is MIT-licensed**, and the code repo
  (`OpenSourceAP/CrossSection`) is public on GitHub with no restrictive licence
  file found. Treat the DATA licence as unconfirmed-but-permissive pending a direct
  look at the Google Drive folder's own terms; the CODE is unambiguously open.
- **Pullable by script, no login**: yes, by the project's own `openassetpricing`
  PyPI package or a plain `requests`/`gdown` pull of the public Drive links.
- **Gives a per-predictor monthly long-short series to lay beside our own books**:
  yes, directly — this is exactly the comparator format TRIAL-DRAFT-A/C's `by_era`
  tables already use.

### JKP factor data — jkpfactors.com

Fetched directly from `jkpfactors.com/data`.

- **Downloadable today, format CC BY-NC 4.0 for data, MIT for code** (stated
  explicitly on the page — this is the one dataset here with an unambiguous
  licence). Non-commercial: fine for internal research/paper-trading, a caveat
  worth flagging before any public-skill claim built directly on JKP's own factor
  series (Aegis's own computed factors from the raw characteristics we already
  hold are not licence-encumbered; a re-publication of JKP's OWN long-short return
  numbers would be).
- **Content**: characteristic-managed portfolio returns for **153 characteristics
  across 13 themes, 93 countries / 4 regions**, plus the underlying low/mid/high
  sorted-portfolio legs, plus GICS/FF49 industry returns, plus NYSE-breakpoint and
  factor-name-mapping reference files — all as direct CSV/XLSX downloads, no login
  for the factor-return level (stock-level micro data requires a WRDS subscription,
  which we already have via the existing `wrds/` pulls).
- **US sample runs January 1926 to December 2023** per the master file
  (`jkp_master_global_monthly.csv`, covering 71 countries) — matches the local
  panel's 1926 start almost exactly (the December-2023 vs December-2024 gap versus
  our own `jkp_global_factor_usa.parquet` is one year, immaterial to using it as an
  external ruler).
- **Gives a per-predictor monthly long-short return series**: yes, directly, by
  design — this is JKP's OWN factor-construction of the SAME 153 characteristics
  whose raw stock-level inputs we already hold, so it is the correct thing to pull
  as **the external comparator for anything we build from the JKP characteristic
  panel** (§3's three books below): build our own sort on our own universe/costs,
  then diff against JKP's own published factor return for the identical
  characteristic over the identical months, which is a tighter apples-to-apples
  test than anything OSAP or HXZ can offer for these three mechanisms specifically.

### Hou-Xue-Zhang q-factors — global-q.org

Fetched via search results (global-q.org itself; no login-walled content found).

- **q-factor series (2015 RFS model) extend back to January 1967**; the q5
  (expected-growth-augmented) model's growth factor also starts 1967. **Updated
  through December 2025** per the site's own release notes.
- **Download**: direct from global-q.org, no login apparent; also wrapped by the R
  `tidyfinance::download_data_factors_q()` and the `getfactormodels` Python/R
  helper.
- **Does it give a per-predictor long-short series?** It gives the **factor
  returns** (ME, I/A, ROE, EG — the four/five q-factors themselves), not a
  per-anomaly-predictor panel the way OSAP or JKP do. Useful only as a **risk-model
  comparator** (a q-factor alpha check on any book we build) rather than as a
  source of individual anomaly rulers. Lower priority than OSAP/JKP for this task.

### Bottom line on §1

For the three new books in §3, **JKP's own published factor-return series
(jkpfactors.com) is the tightest available ruler** because it is literally the same
characteristic construction as the columns already sitting in
`backend/data/optimus/wrds/jkp_full/` and `jkp_global_factor_usa.parquet` — pull it
once (small: 153 characteristics × ~1,176 months × a handful of numeric columns,
almost certainly under 50 MB) and every book below diffs against its own named
column's JKP factor return, not a hand-matched proxy from a different paper's
sample.

## 2. Which predictors survive where we trade

**Honesty check first: an exact ranked "best post-2010 monthly return" table from
OSAP's own `SignalDoc.csv` was NOT independently re-derived here** — that requires
downloading and computing over the 1.6 GB signal file, which is out of scope for a
research-only pass that writes no code and runs no jobs. What follows instead is
grounded in (a) what the fetched `SignalDoc.csv` schema and JKP's own 13-theme
classification make constructible from OUR named tables, and (b) specific,
citable post-2005/post-2010 survival evidence per mechanism, found by search:

| Predictor / theme | Constructible from OUR tables? | Post-2005/2010 survival evidence | Needs Compustat fundamentals we don't have? |
|---|---|---|---|
| **Quality-minus-junk (QMJ)** | YES — `qmj`/`qmj_prof`/`qmj_growth`/`qmj_safety` already computed in `jkp_full/` + `jkp_global_factor_usa.parquet`, 1926-2024 | Asness-Frazzini-Pedersen (*Review of Accounting Studies* 2019 published version; working paper at econ.yale.edu/~shiller): Sharpe ratio **~1 after hedging** other factors; positive in **23 of 24 countries** studied, long U.S. sample. No 2010+ decay figure found in the fetched sources (flag as **not found**, not zero) | NO — comes pre-built in the JKP panel; the panel's own inputs are WRDS Compustat, but WE never touch raw Compustat, only the derived column |
| **Return seasonality (11-15/16-20 month lags)** | YES — `seas_11_15an`/`na`, `seas_16_20an`/`na` already computed, 1926-2024 | Heston & Sadka (*JFE* 87, 2008): annual cross-sectional autocorrelation at lags 12/24/36 up to 20 years; seasonal component alone implies an **annualized SD of 13.8%** in the cross-section of expected returns, positive in every calendar month, strongest Oct/Dec/Jan. A purely price-based, non-fundamental mechanism (same-calendar-month clientele/attention effect), not yet crowded out as of the original sample; no direct 2010+ update found (flag **not found**) | NO — price/volume only |
| **Analyst forecast dispersion** | YES — `stdev`, `numest`, `meanest` already in `ibes_consensus_monthly[_early].parquet`, 1990-2024 | Diether, Malloy & Scherbina (*JF* 57(5), 2002; PDF fetch to diether.org timed out, number corroborated independently via search): highest-dispersion quintile underperforms lowest-dispersion quintile by **0.79%/month (9.48%/year)** in the month after formation, concentrated in small/losers. Mechanism is Miller (1977) short-sale-constrained overpricing, not momentum | NO — IBES only |
| Accruals (`oaccruals_at`/`taccruals_at`) | YES, already in JKP panel | **EXCLUDE from the next-three list**: Green, Hand & Soliman ("Going, Going, Gone?", *Management Science* 2011) find the hedge return has decayed to **no longer positive** post-2003, attributed to hedge-fund arbitrage capital — this is a documented dead anomaly in exactly our post-2010 window, not a live candidate | NO |
| Gross profitability (Novy-Marx) | YES (`gp_at`) | Not separately searched this pass — likely correlated with `qmj_prof`, redundant with the QMJ book rather than a third independent mechanism | NO |
| Betting-against-beta | YES (`betabab_1260d` present) | Already banked as a **confirmed dead negative** in `ROADMAP...11c` ("BAB net alpha ≈ 0") — do not resurrect | NO |

**Ranking by expected post-2010 monthly effect, names above a $3M dollar-volume
floor, excluding anything needing Compustat fundamentals we lack (nothing on this
list does — the JKP panel already absorbs that dependency):**

1. Forecast dispersion — most directly quantified (0.79%/mo published spread,
   2002 sample) and cheapest to build (three IBES columns, no new join).
2. QMJ — best-established Sharpe (~1), but the published number is a
   risk-adjusted long-long-short factor return, not a raw monthly spread, so it is
   harder to compare apples-to-apples against our house convention (net block-mean
   vs a twin) without first pulling JKP's own factor series (§1) as the ruler.
3. Seasonality — largest headline magnitude (13.8% annualized SD) but the
   least "returns-in-dollars" citable number of the three; treat the MDE
   calculation, not the headline SD, as the honest expected-effect input.

## 3. Proposed next three books

All three share the family's existing conventions (TRIAL-DRAFT-A/C style): monthly
cadence, $3M primary / $10M secondary dollar-volume floor, $5 minimum price,
`PRODUCT_EXPERIMENT` licence, a random-universe twin AND — where a published
factor-return series exists (QMJ, seasonality) — the JKP factor return itself as a
SECOND, external comparator reported but not deciding. MDE per the task's own
instruction: `2.8 × 0.043 / sqrt(360) ≈ 0.64%/month` nominal; TRIAL-DRAFT-C's own
measured lag-1 autocorrelation (0.1268) cut its nominal-360 n_effective to 279 and
raised its own MDE from 0.64% to 0.724% — expect the same ~10-15% haircut here once
each book's real difference series is measured, and each sketch below states BOTH
numbers rather than only the flattering one, per that trial's own stated discipline.
**These are one-page SKETCHES for a builder to turn into a full `TRIAL-DRAFT` +
`Strategy` contract, not registrations themselves — none of this has been through
`pre-register-trial` or the corpse-check linter.**

---

### Book E — Quality-minus-junk, long-only tilt (`qmj_quality_tilt_v0`)

- **Mechanism**: leverage- and behaviorally-constrained investors underweight
  safe, profitable, growing, well-managed ("quality") firms relative to what a
  frictionless model implies, especially in market stress, per Asness-Frazzini-
  Pedersen (2019). This is a **profitability/safety/payout** mechanism — no
  momentum, no news-revision input, no disposition/overhang input. Different error
  from every book tested so far.
- **Precursor observable BEFOREHAND**: the composite `qmj` score itself, computed
  entirely from trailing accounting data with no forward information — precisely
  the kind of "typed hypothesis, tested before the fact" CLAUDE.md's Rule 2 asks
  for (quality is knowable at formation date `eom`, not inferred after the fact).
- **Construction from named columns**: `backend/data/optimus/wrds/
  jkp_global_factor_usa.parquet` + `jkp_full/jkp_usa_*.parquet`, column `qmj`
  (composite z-score of `qmj_prof`+`qmj_growth`+`qmj_safety`, JKP's own
  construction), formation date `eom`. Top-tercile `qmj` within the $3M-floor,
  $5-price eligible universe, equal-weighted, monthly rebalance, 3-month hold
  (matching Book C's cadence for cross-book comparability).
- **Twin**: (a) random-universe twin at the identical floor/k; (b) **JKP's own
  published QMJ factor return** (jkpfactors.com, `usa`/`theme=quality`), pulled
  once, reported not deciding — a genuine external-firm-style comparator per
  roadmap point 28 ("every result compared to outside firms").
- **Two falsifiers**: (i) a beta-neutralization check — QMJ's own paper reports a
  **negative market beta**; if our long-only tilt's realised beta to SPY is
  materially positive (>0.3) the tilt is capturing size/growth exposure, not
  quality, and should be re-cut market-neutral before any promotion; (ii) a
  profitability-only vs. full-composite split (`qmj_prof` alone vs. full `qmj`) —
  if `qmj_prof` alone captures all the effect, the book is a profitability book in
  quality's clothing (same shape as Book C's own momentum-in-costume falsifier)
  and should be renamed and re-scoped, not silently kept as "QMJ."
- **Published number as the ruler**: Sharpe ≈ 1 after hedging (AFP 2019,
  econ.yale.edu working-paper copy); positive in 23/24 countries. **No raw
  monthly-spread percentage found in the fetched sources** — the JKP factor pull
  (§1) supplies the actual number to compare against once built; do not invent one.
- **Expected net monthly effect / MDE**: declare **0.70%/month**, one notch above
  the nominal-360-block MDE of 0.64% (task's own sd=0.043 convention), pending the
  book's own measured autocorrelation, which will likely push the realised MDE
  toward TRIAL-DRAFT-C's ~0.72-0.75% band.
- **Decision rule**: `FAILED_VARIANT` if the primary net block-mean vs. the
  random-universe twin is ≤ 0, full stop, regardless of the JKP-factor comparison
  (Amendment-1-style clause, carried in from the start this time rather than
  patched on afterward). `PRODUCT_PROMISING` if it clears the MDE at NW-t ≥ 2.0
  AND the beta falsifier passes (|realised beta| stays economically small or the
  book is re-cut market-neutral) AND `qmj_prof` alone does not subsume the full
  composite. `CONDITIONAL` otherwise.

---

### Book F — Return seasonality, calendar-month long-short (`seasonality_11_20_v0`)

- **Mechanism**: stocks earn abnormally high (low) returns in the SAME calendar
  month every year, a pattern distinct from and superimposed on momentum/reversal
  (Heston & Sadka, *JFE* 2008). Proposed driver in the literature is
  clientele/attention/tax-timing effects tied to calendar recurrence, not a risk
  premium or a news-revision channel — a genuinely different error family from
  every book tested here, including momentum itself (seasonality nets OUT the
  intermediate-horizon return level and isolates the *same-month* component only).
- **Precursor observable BEFOREHAND**: the name's own return in the SAME calendar
  month over the trailing 1-5 years — entirely historical, no forward leakage, and
  exactly the kind of instinct-turned-typed-hypothesis Rule 3 in the invariants
  file asks for ("does this month look like last year's same month, systematically,
  across many names, not just this one").
- **Construction from named columns**: `seas_11_15an` and `seas_16_20an` (JKP's
  own annual, "same calendar month" seasonality composites, lags 11-15 and 16-20
  months — chosen over `seas_1_1*` and `seas_2_5*` specifically to AVOID overlap
  with the momentum window our other books already price, per the roadmap's own
  scratch-check finding that raw 12-1 momentum earns almost nothing on Book C's
  rows: a seasonality measure built from 11-20-month-old Januaries is mechanically
  disjoint from a 12-1 momentum signal). Top-minus-bottom tercile, monthly
  rebalance, 1-month hold (seasonality is a single-month effect by construction,
  unlike Book C's 3-month PEAD-shaped hold).
- **Twin**: random-universe twin at the same floor; JKP's own seasonality-theme
  factor return from jkpfactors.com, reported not deciding.
- **Two falsifiers**: (i) **January exclusion** — Heston-Sadka's effect is
  strongest in Oct/Dec/Jan; if the ENTIRE effect lives in the January cross-section
  (tax-loss-selling reversal, a confound Grinblatt-Han's own January table already
  flagged for Book C — see `research_overhang_literature_vs_book_c.md` §4), report
  the ex-January mean separately and require it to still clear NW t ≥ 1.5 before
  calling the mechanism "seasonality" rather than "January." (ii) **turnover-match
  against Book A's twin construction** — since both books draw on the same
  turnover-heavy universe, run the seasonality book's twin using Book A's
  turnover-matched draw (not permno-sort) to rule out a shared liquidity/turnover
  confound between the two "different" books, directly answering the standing
  house lesson "check whether the noise is shared."
- **Published number as the ruler**: 13.8% annualized SD of the seasonal
  component in expected returns (Heston-Sadka 2008); **no single decile-spread
  percentage found** in the fetched search results — flag as an SD-shaped ruler,
  not a mean-return-shaped one, and do not convert it to an implied monthly return
  without the paper's own portfolio table in hand.
- **Expected net monthly effect / MDE**: same nominal 0.64%/month MDE convention;
  given the ruler is SD-shaped rather than mean-shaped, declare the effect size
  more conservatively than Book E at **0.65%/month** (barely above the nominal
  MDE) — this book's honest prior is weaker precisely because no comparable mean
  spread number was found to sanity-check against.
- **Decision rule**: identical `primary ≤ 0 closes` clause. `PRODUCT_PROMISING`
  requires clearing the MDE AND the ex-January residual clearing NW t ≥ 1.5 AND
  the shared-turnover-twin check not collapsing the excess to zero.

---

### Book G — Analyst forecast dispersion, short-side or long-only-avoid (`forecast_dispersion_v0`)

- **Mechanism**: high dispersion in analyst EPS forecasts proxies for investor
  disagreement; under short-sale constraints (Miller 1977), prices reflect the
  optimists, so high-dispersion names are systematically overpriced and
  underperform (Diether-Malloy-Scherbina 2002). This is a **belief-disagreement**
  mechanism, mechanically distinct from momentum, quality, overhang, and calendar
  seasonality — and it is a genuine LOSER-side hypothesis (avoid or short the
  worst names), directly answering CLAUDE.md's Rule 4 ("study losers as hard as
  winners") in a way none of the other proposed books do.
- **Precursor observable BEFOREHAND**: `stdev` of the IBES consensus, normalized
  by `meanest` (coefficient of variation, the paper's own construction) or by
  price, known entirely as of `statpers` — no forward information.
- **Construction from named columns**: `backend/data/optimus/wrds/
  ibes_consensus_monthly.parquet` + `_early.parquet` (1990-2024), columns
  `stdev`, `meanest`, `numest` (require `numest ≥ 2` — a lone analyst has no
  "dispersion"), fpi='1' (one-year-ahead EPS). Bottom-tercile-vs-top-tercile of
  `|stdev/meanest|` within the eligible universe.
- **Recommended construction choice, house-specific**: build this as
  **long-only-avoid** (hold the low-dispersion tercile, systematically exclude
  the high-dispersion tercile, vs. a twin that includes both) rather than a
  short-side book, because `NEGATIVE_RESULTS.md`'s own banked finding
  (Muravyev-Pearson-Pollet 2025, cited in `ROADMAP...11c`'s banked-negatives list:
  "162 anomalies go from +0.14%/mo to −0.01%/mo after borrow fees") is a direct,
  pre-registered warning against assuming a short leg's gross return survives
  borrow costs — this book's own published number (§ below) is for a
  long-short spread and the short leg specifically should not be taken on faith.
- **Twin**: random-universe twin at the identical floor, drawn from the SAME
  `numest ≥ 2` eligible pool (so the twin cannot win merely by having analyst
  coverage the book requires and the twin doesn't).
- **Two falsifiers**: (i) **small-cap concentration check** — DMS's own paper
  reports the effect is "most pronounced in small stocks and stocks that have
  performed poorly" (i.e., partially a size/momentum confound); split by size
  tercile within the $3M-floor universe and require the effect to survive outside
  the smallest tercile before calling it a distinct disagreement effect rather
  than small-cap beta; (ii) **past-return orthogonalization** — since the paper
  itself flags "poor past performers," regress the dispersion signal's return on
  trailing 12-1 momentum; if the dispersion coefficient dies, this book is
  momentum in yet another costume (same falsifier shape as Book C's, applied to a
  new candidate before it is trusted, not after).
- **Published number as the ruler**: **0.79%/month (9.48%/year), highest- minus
  lowest-dispersion quintile**, month after formation (Diether-Malloy-Scherbina,
  *JF* 2002; sample 1983-2000 — pre-2005, so apply the same ~50% generic
  post-publication haircut CLAUDE.md's own §2 note applies to Book C before
  treating any of it as a floor). No independent post-2010 replication number was
  found this pass — mark as **not found**, and treat the ~50% McLean-Pontiff-style
  haircut (implied ≈0.40%/mo) as the working prior rather than the raw 0.79%.
- **Expected net monthly effect / MDE**: declare **0.65%/month**, barely above the
  nominal 0.64% MDE and explicitly BELOW the haircut-adjusted literature prior of
  ~0.40%/mo for the long-only-avoid construction specifically (a long-only-avoid
  book captures only part of a long-short spread by design) — i.e., this book's
  own declared effect size is deliberately conservative and may fail the power
  check when the real cross-sectional sd is measured; that arithmetic must be
  redone from the built panel before registration, per TRIAL-DRAFT-A/C's own
  standing caveat.
- **Decision rule**: `primary ≤ 0 closes`, identical clause. `PRODUCT_PROMISING`
  requires clearing the MDE AND surviving outside the smallest size tercile AND
  the momentum-orthogonalization falsifier not killing the coefficient.

---

## 4. Book C v1's news sign — Frazzini's earnings-window construction

**We can build this. IBES `anndats_act` gives the actual EPS-announcement date for
1990-2024, in both local files** (schemas read directly with pandas):

- `backend/data/optimus/wrds/ibes_consensus_monthly_early.parquet` — window
  1990-01-18 .. 2012-12-20, 3,682,004 rows, columns include `anndats_act`.
- `backend/data/optimus/wrds/ibes_consensus_monthly.parquet` — window 2013-01-17
  .. 2024-12-19, 1,554,570 rows; `anndats_act` non-null on 1,301,870 of 1,554,570
  rows (84%).
- Both files' own `pit_knowledge_column` metadata says it explicitly:
  "`anndats_act` is when the actual became known — never use `actual` before
  `anndats_act`." This is exactly the date Frazzini's 4-day CAR (t-2..t+1) needs,
  and it is **cleaner and more directly fit for purpose** than Compustat `rdq` for
  this book (IBES ties the date to the specific EPS actual that resolved the
  consensus, which is what a market-reaction window is centered on in the original
  paper).

**Compustat quarterly `rdq` also exists locally but is far too short a window to
be primary:** `backend/data/optimus/wrds/compustat_fundq.parquet` has a `rdq`
column, but the pulled window is **2013-02-12 .. 2026-03-26 only** (208,603 rows,
per its own meta.json) — it does not cover 1990-2012 at all and cannot support a
book that wants to replay the 1990s the way Books A/C do. **Recommendation: use
IBES `anndats_act` as the sole announcement-date source for the 1990-2024 window;
use `rdq` only as a 2013+ cross-check, never as the primary source.**

**Free source if IBES coverage gaps matter**: EDGAR full-text search covers 8-K
Item 2.02 (results-of-operations / earnings-release) filings from **2001 onward**
(the full-text search index starts 2001; structured item-tagging tightened after
the 2004 8-K overhaul) — strictly worse coverage than IBES's 1990-2024
`anndats_act` and unusable pre-2001. **Recommendation: do not build an EDGAR
fallback unless a coverage audit of the 16% `anndats_act`-null rows shows a
material, non-random gap.**

**Construction**: CRSP daily returns (`backend/data/optimus/wrds/
crsp_dsf_<year>.parquet`, columns `permno, date, ret`, 1990-2024 — the exact table
`_daily_returns()` in `scripts/night_first_books_replay.py` (line ~595) already
loads for Book B's BHAR windows) summed from `anndats_act − 2` trading days to
`anndats_act + 1` trading days (Frazzini's own 4-day window) per permno per
fiscal-quarter announcement. Sign = the raw 4-day CAR, matching Frazzini's own
two-step design (sort on raw CAR, then measure the resulting portfolio's FF3
alpha — replicate both steps rather than skipping to a risk-adjusted sort).

**Expected magnitude change from the literature**: switching Book C's news sign
from v0 (`sign(numup-numdown)`, a monthly, low-frequency IBES revision-count sign)
to the announcement-window CAR sign should **sharpen the conditioning
substantially**, not just relabel it. Frazzini's own comparator closest to "just
the news sign, unconditioned by overhang" is his single good-news quintile at
3-month hold: **FF3 alpha 0.618%/month, t = 4.45** (`research_overhang_
literature_vs_book_c.md` §1, fetched directly from the NYU Stern preprint) — a
sharper, higher-t comparator than what a monthly revision-count sign currently
produces on our own `unconditioned_reaction_book_v0` twin (0.79%/mo net, similar
order of magnitude but from a noisier construction per that note's §3 comparison
table). This news-sign swap is **explicitly gated by TRIAL-DRAFT-C's own §8 rule**
("No swapping the event-sign input (v0 → v1) inside this registration. That is a
separate amendment naming only the input") — it must ship as v1, not a silent edit
— and, being a change to an EXISTING, already-CONDITIONAL book rather than a new
mechanism, it is the single highest-leverage, already-fundable change available
right now, ahead of any of the three new books in §3.

## 5. What would change the roadmap

The single most decision-relevant finding this pass: **the roadmap does not need
new data infrastructure to open three new, mechanically distinct books — it
needs a builder to read three already-computed JKP columns and one already-pulled
IBES column.** `jkp_global_factor_usa.parquet` and `jkp_full/*.parquet` (1926-2024,
already on disk, PIT-stamped) carry quality (`qmj`), calendar seasonality
(`seas_11_15*`, `seas_16_20*`), and dozens of other themed characteristics that
have never been read by any book in this repo; `ibes_consensus_monthly[_early]
.parquet` carries `stdev`/`numest` (forecast dispersion, unused) and `anndats_act`
(the announcement date Book C's own v1 amendment needs, also unused). Every
existing book (A, B, C, D) required new panel-building work — short-interest
files, insider Form-4 clusters, a from-scratch Grinblatt-Han reference price. The
three sketched here, and Book C's own v1 news-sign fix, do not: the data has been
sitting in `backend/data/optimus/wrds/` since the 19-22 August pulls, unread.
Given CLAUDE.md's own bottleneck diagnosis ("all ten arena books select on ONE
signal... differ in portfolio treatment, not alpha source"), the fastest way to
add a genuinely different error type to the arena is not a new pull — it is
reading data this repo already paid for.
