# nn_lab: universe hygiene and two SIZE members (2026-09-30 night, JOB4)

Licence `PRODUCT_EXPERIMENT`. No broker authority. Nothing trades. $0 LLM spend, no graphics card used.
Receipts: `backend/data/optimus/nn_lab/receipts/size_20260929T141548Z.json` (size walk-forward on the
rebuilt table), `table_20260929T141339Z.json` (the rebuild), `prices_deep/delisted_crsp_receipt.json`,
`prices_deep/raw_monthly_receipt.json`, `nn_lab/universe_meta/etf_exclusions.json`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: one SIZE result, no return result.** The earnings-cadence member adds to the
size forecast in 6 of 7 test years; nothing here changes a direction forecast or a book.

| line | tonight |
|---|---|
| Best historical net strategy vs market | unchanged (nothing here is a strategy) |
| Best forward paper strategy | unchanged |
| Independent selector count | unchanged; +1 forward-graded MAGNITUDE member (`vol_earn`), weight 0 until forward blocks earn it |
| New actionable finding | An earnings release expected inside the hold window (from 8-K item 2.02 cadence, known beforehand) adds **+0.0067 rank IC** to the 5-session size forecast over trailing vol (**t 5.76**, 81 blocks), +0.0051 over the fitted ridge magnitude baseline (t 5.78); positive 6/7 years (2021 -0.0005). 21-session: +0.0023 (t 2.27), 2020-21 negative |
| Negative finding | The TF-IDF text member (next-session size model, averaged over 7 days) HURTS 5- and 21-session size: -0.0010 (t -2.4) and -0.0008 (t -3.0), 2026 test year, every month but one. Not rostered |
| Survivorship | Dead names in the table by last year: 2023 **4 -> 117**, 2024 **3 -> 80** (CRSP-recovered, return-verified). 2025-26 deaths still missing |
| Universe | 45 ETF/ETN/fund symbols removed from the table (VXX, OILU, SILJ, BKCH, ...); 9 companies whose ticker a fund later reused are kept (EV = Eaton Vance, INFO = IHS Markit, KEM, FLOW, ...) |
| External execution drag / LLM spend | n/a / **$0.00** |

## 1. Review items (REVIEW_2026-09-29_NN_LAB MUST-FIX), status measured in code tonight

| item | status |
|---|---|
| F1 future-split leak in mcap / yields / price floor | **landed before tonight** (features NaN without `close_raw`; floor only on raw). Tonight: a real `close_raw` exists behind `USE_CLOSE_RAW` (default OFF), see §4 |
| F2 analyst missing flag | landed (no flag for later-pull groups; analyst NaN before the first snapshot) |
| F3 death coverage | **tonight**: CRSP-recovered 2016-2024 deaths (§3); reused dead tickers renamed `SYM#d` when histories do not overlap. 2025-26 still open |
| F5 nightly re-roll / promotion | landed (refit only on a new labelled grid date, train+val; no validation promotion) |
| F6 shrink guard | landed (table-level); tonight extended: ETF rows leaving the universe are dropped and counted, not a shrink |
| F7 grader | landed (sha verified, value hash, delisted exit at last close). Universe ETFs: **tonight** |
| status line STALE_BARS | landed. **Alert channel for a FAILED/REFUSED night: still not wired** (only nightly.log + exit code) |
| F8 fitted magnitude baseline | landed (`ridge_abs`); used as the bar below |
| F9 comparative-period join | landed (latest period end on a shared filing date) |
| F10 variant chosen on test | not re-checked tonight |

## 2. ETFs / ETNs out (`nn_lab/universe_filter.py`, flag `EXCLUDE_ETFS=True`)

Sources, recorded per symbol: the terminal universe files' asset NAMES (their `etf_like` flag marks
Healthcare Realty Trust and WisdomTree Inc., two companies, so the flag alone is not used), a strict
fund-name pattern on SEC company tickers, and Alpaca's inactive-asset names (list fetched
tonight). A name is a fund only on words like ETF/ETN/ProShares/iShares/3X/VIX; "Trust" alone is not.
Tickers a fund reused after a company died are **kept** when CRSP lists the ticker as a common stock
during the table rows' months (EV = Eaton Vance, FLOW, KEM, SHLD, ...) plus two checked by hand
(INFO = IHS Markit, RESI = Front Yard). Exact symbols only: a renamed earlier segment `SYM#k` is never
excluded. 5,686 symbols in the list; 45 were in the table (0 after the rebuild). Tests: `test_universe_hygiene.py`.

## 3. Deaths after 2022 (`nn_lab/deaths_crsp.py`, flag `USE_CRSP_DEATHS=True`)

**Diagnosis.** `bars_delisted.parquet` is Alpaca's list of INACTIVE assets, which is not a death
history. Against CRSP daily (6,254 screened PERMNOs 2016-2024) it holds 8/284 of the 2016 deaths,
3/248 of 2017, most of 2019-22, and **4/400 of 2023, 4/343 of 2024**. The bars endpoint still serves
those tickers (probed SGEN, ATVI, SPLK, PXD, SIVB, ANSS, WBA); only the list lacked them.

**Fix.** 1,778 CRSP-dead tickers pulled over their own CRSP life (parallel, 21 min, $0). A bar is kept
only inside the PERMNO's life, and a ticker only when Alpaca's daily returns match CRSP `ret`
(median |diff| < 1%, corr > 0.9): 1,459 matched, 262 mismatched (another company under the ticker),
52 too short, 20 no bars. 24 more were dropped as the same listed series under a new PERMNO
(JCI 2016, DOW, FOX: a merger that kept the ticker is not a death). 14 collisions kept as `SYM#c`.
Result: **1,435 dead names, 1.17M bars**, `prices_deep/bars_delisted_crsp.parquet`.

Table after the rebuild (`nn_lab/rebuild.py`: builds aside, checks, backs up, swaps): 1,198,474 rows
(was 1,131,454), 4,258 symbols (was 3,610), 1,252 dead. Dead by last year: 2016 65, 2017 127,
2018 142, 2019 146, 2020 118, 2021 241, 2022 199, **2023 117, 2024 80**, 2025 7, 2026 10. PIT audit 0
violations; no labelled grid date lost. Backup: `table/train_table_before_20260929T141339Z.parquet`.

**Still missing:** 2025-26 deaths (no free list on disk; CRSP vintage ends 2024-12).

## 4. Unadjusted prices (`nn_lab/raw_prices.py`, flag `USE_CLOSE_RAW=False`)

Free and cheap: Alpaca `adjustment=raw` MONTHLY bars, 474,514 bars for 6,212 tickers in 15 minutes.
`close_raw(t) = adjusted_close(t) x raw/adjusted at the latest month-end <= t`. A split after t scales
both factors equally and cancels (planted-split test); a split inside the last month is past
information and mis-scales for under a month. Checked: NVDA 2019-03 $94.8B (adjusted basis read
$2.3B), AAPL $825B, CMG 2023-03 $41B, TSLA $51B. Coverage 99.3% of bars. **Left OFF**: the nightly has no
monthly raw refresh, so live rows would lack what training rows have. (Queued evaluation of the
mcap features' value: see §6.)

## 5. SIZE members (`nn_lab/size_members.py`; nightly flag `SIZE_MEMBERS_NIGHTLY=True`, roster `("vol_earn",)`)

**Earnings-cadence prior.** From SEC 8-K item 2.02 ("Results of Operations"; 97,545 releases, 2,567
tickers, 2013-2026), a release is EXPECTED in [session t+1, t+1+h] when a release known strictly
before t, shifted 364 days, or the last one + 91 days, lands in the window (+/- 3 days). Graded
against the realised release: h=5 precision 0.46, recall 0.87; h=21 precision 0.75, recall 0.95.
Expected rows move 1.30x (h5) / 1.22x (h21) their trailing vol vs the rest (median ratio).
Member: `vol_earn = exp(a + b log vol_63 + c earn_expected)`, fitted per fold (c = +0.23..+0.27 at
h5, +0.16..+0.19 at h21, every fold: the same +0.24 the ft_lab event table measured).

**Walk-forward, size target |y_h| (excess vs cross-sectional median), per-date rank IC, SE over
blocks of max(h,21) sessions, test years 2020-2026, rebuilt table:**

| model | h5 IC | h21 IC |
|---|---|---|
| trailing vol | 0.3381 | 0.3469 |
| vol_earn | 0.3448 | 0.3491 |
| ridge on |y| (F8 fitted baseline) | 0.3538 | 0.3623 |
| ridge on |y| + earnings flag | **0.3590** | **0.3638** |

| increment | h5 | h21 |
|---|---|---|
| vol_earn - vol | **+0.0067 (se 0.0012, t 5.76, 81 blocks)**; by year 2020 +.0020, 2021 -.0005, 2022 +.0054, 2023 +.0101, 2024 +.0119, 2025 +.0113, 2026 +.0066 | +0.0023 (t 2.27); 2020 -.0050, 2021 -.0043, then +.0011..+.0088 |
| living names only | +0.0076 (t 6.42) | +0.0038 (t 3.86) |
| ridge+earn - ridge | +0.0051 (t 5.78) | +0.0015 (t 2.60) |

Coverage caveat: the 8-K pull (2026) covers 84% of living and 3% of dead names; an uncovered name
reads "no earnings expected" and no coverage flag is ever a feature.

**TF-IDF text member.** ft_lab's T2 recipe refit at 2025-06, 2025-12 and 2026-06 cutoffs (fit only on
cells entered 15+ days before; inner-validation corr 0.09-0.14), scored out of sample, averaged over
cells entered in the 7 days up to t. News exists only from 2025, so it is tested on the 2026 year
with its coefficient fitted on 2025-06..10 rows: **h5 -0.0010 (t -2.43), h21 -0.0008 (t -3.03)**
all rows; on news rows -0.0023 / -0.0023; unfitted (k=1) worse. The text's size information is
next-session only (ft_lab's +0.0069); over 5-21 sessions it is noise that moves news names away from
their vol rank. **FAILED_VARIANT** for multi-session size. Code kept; not rostered.

**How the member reaches the nightly.** New step `size_members` (after `append`) rebuilds the sidecar
(~30 s; a failure is recorded, never fails the night). `freeze` writes `vol_earn` as a MAGNITUDE
model beside trailing_vol / ridge_abs / nn_width; `grade` scores it; `trust` gives it a posterior of
(abs IC - trailing vol's abs IC) from FORWARD blocks only (it is absent from `wf_record`'s name map on
purpose: the walk-forward above never seeds it). `choose_magnitude` can only pick it once that forward
posterior is positive. Dry run on a copy of the nn_lab state: FROZEN 5,898 rows (2,949 names x 2
horizons), trust `prior_only`, improvement 0.0, nothing else changed.

## 6. Not run (stopped on the owner's pause order, 22:5x local)

Queued behind a free-memory gate (the machine sat below it all night; figures recorded locally), and stopped by its STOP
file before starting: (a) direction walk-forward without the network on the rebuilt table
(`run_id hyg_20260930_nonn`); (b) the same with `close_raw` market-cap features. A first attempt at
(a) was stopped by its recorded process id at fold 2023 when free memory fell below the measured memory floor. Run ids start
with `hyg_` so `nightly.wf_record` never reads them.

## Will the 08:30 nightly run on the improved table?

The table was swapped at 22:14 local and the nightly path with the member was dry-run end to end on a
copy (vol_earn FROZEN 5,898 rows, trust `prior_only` 0.0, status DEGRADED as expected in a sandbox).
**But the owner paused everything: `backend/data/optimus/nn_lab/STOP` is present, so the 08:30 run
will REFUSE by name.** Once STOP is removed, the next run uses the rebuilt table and the member.
nn_lab tests: 54 pass.

## CONTINUE FROM HERE

```powershell
# tests
$env:AEGIS_IGNORE_DOTENV="1"; $env:AEGIS_PERSONAL_MODE="0"; nn_lab\.venv\Scripts\python.exe -m pytest nn_lab/tests -q -p no:cacheprovider
# size walk-forward again (after any table change)
nn_lab\.venv\Scripts\python.exe -m nn_lab.size_members build; nn_lab\.venv\Scripts\python.exe -m nn_lab.size_members evaluate
# the members off: nn_lab/config.py SIZE_MEMBERS_NIGHTLY = False ; the ETF list off: EXCLUDE_ETFS = False
# revert the table: copy table\train_table_before_20260929T141339Z.parquet over table\train_table.parquet
# resume the queued evaluations (memory-gated, run only above the free-memory gate):
#   nn_lab\.venv\Scripts\python.exe -m nn_lab.walkforward --no-nn --run-id hyg_20260930_nonn
#   then build a close_raw variant (config USE_CLOSE_RAW=True) into table\variant_close_raw\ and rerun
#   the walk-forward on it with run-id hyg_20260930_closeraw_nonn
# the nightly: delete backend\data\optimus\nn_lab\STOP when the owner lifts the pause
```

Owed: (1) a monthly raw refresh in the nightly, then `USE_CLOSE_RAW = True` if the mcap walk-forward
earns it; (2) 2025-26 deaths (no free list); (3) an alert on a FAILED/REFUSED night; (4) read
`vol_earn`'s forward grades from the first 5-session maturity (the 2026-10 earnings season is the
first real test: the member only differs from vol when a release is expected).

## WHAT WORKS
- A known-beforehand earnings calendar from 8-K item 2.02 cadence: a cheap, stable size increment.
- Recovering deaths from CRSP with a return-identity check (1,459 of 1,778 verified).
- Monthly raw bars as a leak-free unadjusted close.

## WHAT DOES NOT
- A next-session text model as a 5-21 session size member.
- Alpaca's inactive-asset list as a death history; the terminal `etf_like` flag as a fund test.

## HIGHEST-EV EXPERIMENT
Grade `vol_earn` forward through the October earnings season (free, already frozen nightly), and in
the meantime give the contest desk / straddle log the same earnings flag: the size increment is
largest exactly where the contest and the straddle log spend risk.
