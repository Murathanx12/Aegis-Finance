# The momentum lead on CRSP: rebuilt from 1991, and why the vendor panel showed an edge (2026-09-29)

Licence `PRODUCT_EXPERIMENT`. $0.00, no LLM, no network, no broker call. No frozen book, ledger row,
bar file or past receipt was changed. Every number below is in a receipt under
`backend/data/optimus/crsp_rebuild/` (run id in every file name).

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NEGATIVE.** The project's only surviving historical lead does not survive a second
source. Rebuilt on CRSP total returns from 1991 to 2024 with the same engine, `mom_12_1_q` beats its
matched twin by **+0.10%/mo (t 0.33, MDE 0.83%/mo)**. The vendor panel's edge of +0.92%/mo is
reproduced on CRSP by one thing: **the vendor's universe rule.** That rule keeps a living stock only if
it was liquid on 2026-09-01. Applied to CRSP, it lifts the same book from +0.18 to +0.93%/mo on
2017-2024.

| item | value |
|---|---|
| best historical net strategy vs the market | none of the four leads beats the market on CRSP 1991-2024. `mom_12_1_q`, calendar-neutral, net: **CAGR 5.2%** vs the market's 10.9%, max drawdown **-91%**. |
| the lead vs its matched twin, CRSP 1991-2024 | **+0.10%/mo, t 0.33, MDE 0.83%/mo.** The vendor claim (+0.92%/mo) is above that MDE, so this test could have seen it. It did not. |
| the same, 2017-2024 only (the vendor's window) | CRSP **+0.22%/mo (t 0.37)**. Vendor **+1.09%/mo (t 1.97)**. CRSP with the vendor's universe rule **+0.93%/mo (t 1.63)**. |
| where the positive part of 34 years sits | 1991-2000: +1.14%/mo. 2001-2016: negative. Four months of 1998-2000 carry **242%** of the 34-year total. Leaving out **1998** alone takes the mean to **-0.04%/mo**. |
| four-factor alpha (Fama-French 3 + UMD), net | **-0.78%/mo, t -2.27.** That is an ALPHA_DETECTED reading with a NEGATIVE sign: the book earns less than its momentum, size and market loadings predict. |
| the academic benchmark, same panel | equal-weight 12-1 decile spread **+0.78%/mo (t 1.84)** for 1991-2024. Published Fama-French UMD: +0.39%/mo for 1991-2024, **+0.26%/mo for 2017-2024**, +1.21%/mo for 2025 to June 2026. |
| best forward paper strategy | unchanged. No forward read is due before 2026-10-26. |
| independent selector count | unchanged. The four leads are **one bet**: the median pairwise correlation of monthly net returns is 0.94, and they form one cluster at rho 0.7. |
| farm candidates tested / promoted | 4 rules re-tested on a second source, 0 promoted |
| new actionable finding | **The vendor living universe is survivor-selected on end-of-sample liquidity.** It is a 2026-09-01 universe floored at $3M median dollar volume measured then. A stock that won, crashed, and stayed listed at low volume is in neither the living pull nor the delisted pull. Every library backtest on this panel inherits this. |
| external execution drag | not measured here |
| LLM spend | $0.00 |

## 1. What was built

A bridge (`backend/services/crsp_rebuild.py`) turns CRSP daily files into the dictionary the library's
engine reads. It covers every permno in the PIT universe files (share codes 10/11, NYSE, AMEX and
NASDAQ, dead names included), 1990-2024. The engine then runs **unchanged**:

- `night_backtest_factory.build_panel` builds the panel;
- `strategy_library.run_strategy` runs each rule at each quarterly offset, with band costs on;
- `calendar_offsets.twin21` builds the twin: size band x vol_63 tercile x 12-1 tercile, with two
  disjoint sets of 21 draws;
- `calendar_offsets.classify` applies the declared v2 calendar rule.

The bridge makes five choices, and each is printed on the panel receipt:

1. **Close** is a total-return index built from CRSP `ret`, so dividends are included.
2. **Open** is CRSP `openprc` put on that index. Where CRSP has no open, it is the previous
   close. There is no open before 1992, 60% coverage in 1990-1997, and 92-98% after that.
3. **Delisting return.** It is booked on the session after the last trade, using CRSP `dlret`. A
   missing dlret with a 400-599 code takes the library's -30% fill. That happened 22-340 times per
   era. The engine then runs with no fill of its own.
4. **Volume** is set so that close x volume equals the true dollar volume. The price floor reads
   the actual |prc|.
5. **The market leg** is the Fama-French daily market (mktrf + rf). It is **not SPY**: SPY is not a
   CRSP common stock and does not exist before 1993.

Panel receipt: `crsp_rebuild/panel_2026-09-29T041550Z.json`. It holds 2,033,164 rows, 408 month-ends
from 1991-01-31 to 2024-12-31, and 18,184 permnos. The median eligible count per date is **653 in
1991-95**, rising to 1,900-2,040 after 2006. The floors are nominal, so the early 1990s universe is
smaller.

**The panel checks out against the published factor.** Our equal-weight decile spread correlates
**0.88** with the published Fama-French UMD month by month.

The leads receipt is `crsp_rebuild/momentum_on_crsp_2026-09-29T042053Z.json`, with its monthly series
and decile parquets.

## 2. The table

All four rules are at k = 20 and calendar-neutral (one third in each quarterly offset), costs on.
"Rule - twin" is the mean monthly difference against the 21-draw matched twin. The t uses
non-overlapping 3-month blocks, and the MDE (2.8 x SE) is shown beside every t. Years are keyed on the
**hold** month.

| rule | CRSP 1991-2024 | pre-vendor 1991-2016 (foreign slice) | CRSP 2017-24 | vendor 2017-24 | CRSP 2017-24 with the vendor universe rule |
|---|---|---|---|---|---|
| `mom_12_1_q` | **+0.10** (t 0.33, MDE 0.83) | +0.06 (t 0.17, MDE 0.96) | +0.22 (t 0.37, MDE 1.66) | +1.09 (t 1.97, MDE 1.55) | **+0.93** (t 1.63, MDE 1.61) |
| `mom_12_1_q_trend` | +0.01 (t 0.03, MDE 0.75) | +0.05 (t 0.15, MDE 0.87) | -0.11 (t -0.21, MDE 1.50) | +1.11 (t 2.13, MDE 1.46) | +0.70 (t 1.30, MDE 1.51) |
| `qc470_mom252_quarterly_riskparity` | +0.26 (t 0.90, MDE 0.82) | +0.20 (t 0.58, MDE 0.94) | +0.48 (t 0.81, MDE 1.67) | +1.00 (t 2.14, MDE 1.31) | +1.01 (t 1.89, MDE 1.50) |
| `disp_short_avoid` (1999-2024) | -0.14 (t -0.43, MDE 0.90) | -0.35 (t -0.92, MDE 1.06), 1999-2016 | +0.34 (t 0.55, MDE 1.72) | +0.82 (t 1.69, MDE 1.36) | not run |

Beside it:

| rule | calendar verdict on CRSP (offset t: jajo / fman / mjsd) | LOO-worst rule - twin (year dropped) | FF3+UMD alpha, net (t, MDE) | twin gap after UMD (t) | CAGR net vs market |
|---|---|---|---|---|---|
| `mom_12_1_q` | CANNOT_DISTINGUISH (1.72 / 0.00 / -0.87) | -0.04%/mo (1998) | **-0.78%/mo (t -2.27, MDE 0.97)** | -0.31 (t -1.17), UMD beta 0.43 | 5.2% vs 10.9% |
| `mom_12_1_q_trend` | CANNOT_DISTINGUISH (0.91 / 0.29 / -1.10) | -0.10%/mo (1999) | -0.36 (t -0.95, MDE 1.05) | -0.24 (t -1.00) | 5.2% vs 10.9% |
| `qc470_mom252_quarterly_riskparity` | CANNOT_DISTINGUISH (1.94 / 0.48 / 0.03) | +0.10%/mo (1999) | -0.64 (t -1.94, MDE 0.92) | -0.11 (t -0.41) | 7.6% vs 10.9% |
| `disp_short_avoid` | CANNOT_DISTINGUISH (0.96 / -1.11 / -0.84) | -0.23%/mo (2019) | **-1.05 (t -2.83, MDE 1.04)** | -0.47 (t -1.67) | -0.5% vs 8.6% (1999-2024) |

**`disp_short_avoid` against its own registered control.** Paired with `mom_12_1_q` on the same
1999-2024 panel, it beats that control by **+0.01%/mo (t 0.18, MDE 0.23)**. The dispersion screen
changes nothing, and the test had the power to see a 0.23%/mo difference.

The dispersion input is `target_cv_180`, rebuilt from IBES split-adjusted 12-month USD targets
(`wrds/bulk/ibes__ptgdet`). It uses each broker's latest target in the 180 days before the date,
with at least 3 brokers. It covers **41%** of eligible names in 1999 and 67-91% from 2000. The rule
therefore starts in 1999.

### Verdicts, in the project's vocabulary

Each verdict is derived by a rule written in code before this run, except where marked.

| rule | calendar (v2 rule) | vs twin, full sample | factor (FF3+UMD, net) | headline (judgement, evidence in the row) |
|---|---|---|---|---|
| `mom_12_1_q` | CANNOT_DISTINGUISH | CANNOT_DISTINGUISH (mean > 0, t < 2) | ALPHA_DETECTED, **negative sign** | **FAILED_VARIANT.** See below. |
| `mom_12_1_q_trend` | CANNOT_DISTINGUISH | CANNOT_DISTINGUISH (mean +0.01) | CANNOT_DISTINGUISH | **FAILED_VARIANT** |
| `qc470_mom252_quarterly_riskparity` | CANNOT_DISTINGUISH | CANNOT_DISTINGUISH | CANNOT_DISTINGUISH | **FAILED_VARIANT** (weakest of the negatives; its best offset reaches t 1.94) |
| `disp_short_avoid` | CANNOT_DISTINGUISH | **FAILED_VARIANT** (mean <= 0) | ALPHA_DETECTED, **negative sign** | **FAILED_VARIANT.** The screen adds 0.01%/mo to its control. |

**The case for FAILED_VARIANT on `mom_12_1_q`** needs evidence, as a negative does. There are four
pieces:

1. The CRSP test's MDE (0.83%/mo) is **below** the claimed effect (0.92%/mo), and the estimate is
   +0.10.
2. The pre-vendor slice (1991-2016) was never seen by the library's development. It reads +0.06.
3. After the UMD factor, the twin gap is negative (-0.31%/mo), because the twin is matched on the
   12-1 *tercile* and the top 20 carry more momentum than their twins.
4. The vendor's +1.09 on 2017-2024 is reproduced (+0.93) by applying the vendor's own universe rule
   to CRSP (section 3).

This closes **this implementation**: top-20, 12-1, quarterly, equal weight, on this panel. It does
**not** close momentum. That verdict (`MECHANISM_REJECTED`) is not made here. The known premium exists
on the same data (section 4).

No rule is ROBUST_TO_CALENDAR on CRSP. The vendor's CALENDAR_ARTEFACT label for `mom_12_1_q` becomes
CANNOT_DISTINGUISH, because no offset reaches t 2. The jajo offset is still the best: t 1.72 for
`mom_12_1_q` and 1.94 for `qc470`.

### What carries any positive number

- **`mom_12_1_q`, rule - twin by hold year, summed** (percentage points):
  - 1991 +31.9, 1995 +13.6, **1998 +55.8**, **1999 +44.2**, 2000 +19.4, 2019 +33.6, 2024 +18.2.
  - 2009 -33.8, 2020 -19.1, 2021 -19.3.
  - 19 of 34 years are negative.
- **Concentration.** The top 1% of months (1998-05, 1999-11, 2000-05, 2000-01) carry **242%** of the
  total, and the top 5% carry 373%. The 34-year positive is the dot-com run-up.
- **The same years carry the other rules.** Top months for `qc470`: 1998-05, 1999-11, 2020-12.
  For `mom_12_1_q_trend` the top 1% of months carry 2,750% of a total near zero.
- **The vendor window (2017-2024) on CRSP.** The 2019 (+33.6) and 2024 (+18.2) gains are cancelled
  by 2017, 2020 and 2021 (-9.7, -19.1, -19.3).

## 3. Vendor vs CRSP, slot by slot, and why they differ

Receipt: `crsp_rebuild/slots_2026-09-29T042802Z.json`.

**The comparison.** At every month-end both panels share (2016-12 to 2024-12, 96 dates), take the
top 20 by 12-1 among eligible names on each panel. Vendor symbols are mapped to CRSP permnos. The
vendor files a renamed company's whole history under its **current** ticker (2017's FB is `META`),
so the mapping follows a ticker to the permno that took it later.

Two earlier slot receipts, `...042327Z` and `...042607Z`, used a date-only ticker map or lacked the
profile. They are superseded and kept unchanged.

**The count: 816 of 1,920 slots differ (42%).** The share by year is 55% in 2017, 36-40% in
2018-2019, 50% in 2020, **62% in 2021**, 35-40% in 2022-2023 and 23% in 2024. Those slots split as
follows.

**CRSP-only slots (807):**

| reason | slots | mean next-month return |
|---|---:|---:|
| C1 absent from the vendor panel | **751** (742 with a forward return) | **-1.4%** (median -3.1%) |
| C2 ineligible on the vendor panel | 16 | -3.4% |
| C3 / C4 / C5 (score missing, score differs, rank margin) | 49 | mixed |

Of the C1 names, **98% (204 of 208) were never in the vendor panel at all**:

- **61%** of their slots belong to names still listed at the end of 2024 (MVIS, OCGN, AMTX, KIRK,
  SUNW, MPU, DXLG, ...). Those slots earn **-1.8%** a month (median -4.2%).
- Median price $17.75, median dollar volume $15.7M a day. They were tradable when the rule bought
  them.

**Vendor-only slots (816):**

| reason | slots | mean next-month return |
|---|---:|---:|
| V7 same score, ranked just outside CRSP's top 20 (pushed out by the C1 names) | 363 | +2.3% |
| V1 no CRSP common-stock name: ADRs, foreign ordinaries, tickers the map cannot follow | 255 | +0.8% |
| V3 permno not in the CRSP panel that month | 158 | +2.8% |
| V4 ineligible on CRSP | 20 | |
| V6 score differs between sources, mostly VIVO (a CRSP-confirmed defect: 12-1 of +1,247% vendor vs +162% CRSP) | 14 | |
| V2 not a CRSP common stock | 6 | |

**Same names, same prices.** Of the 1,104 shared slots, only **14** differ by more than 2% in
next-month return between the two sources. The gap between the books is **which names are in them,
not how they are priced**. Vendor-only slots earn **+2.6%** a month on vendor bars; CRSP-only slots
earn **-1.5%** on CRSP bars.

**Why the vendor lacks them.** `prices_deep/pull_receipt.json` holds the living panel's membership:
the `HIGH_DISPERSION_US_v1` universe **as of 2026-09-01** (9,668 members), cut to **3,056** by a
$3M median dollar volume floor **measured on 2026-09-01**. The delisted pull adds names that stopped
trading.

A name that won, then crashed but stayed listed at low volume is in neither pull. It is the momentum
book's natural loser. This is look-ahead in universe membership: survivorship by end-of-sample
liquidity, not by delisting. The 2026-09-22 survivorship fix (the delisted pull) could not see it,
because these names never delisted.

**The mechanism, tested.** Receipt: `crsp_rebuild/emulate_vendor_universe_2026-09-29T043122Z.json`.

**The rule, applied to CRSP.** Keep every permno that died before the end. Keep a living permno only
if its median dollar volume on 2024-12-31 is at least $3M. This drops **1,690 alive-but-shrunk
permnos** and keeps 14,353 dead and 2,141 alive-and-liquid.

**The result:**

| rule, 2017-2024, rule - twin | CRSP all names | CRSP with the vendor universe rule | vendor panel |
|---|---:|---:|---:|
| `mom_12_1_q` | +0.18 (t 0.33) | **+0.93** (t 1.63) | +1.09 (t 1.97) |
| `mom_12_1_q_trend` | -0.16 (t -0.38) | +0.70 (t 1.30) | +1.11 (t 2.13) |
| `qc470_mom252_quarterly_riskparity` | +0.41 (t 0.73) | **+1.01** (t 1.89) | +1.00 (t 2.14) |

Under this rule the calendar verdict for `mom_12_1_q` becomes **CALENDAR_ARTEFACT** (jajo t 2.25),
which is exactly the vendor's label.

About **80%** of the vendor's `mom_12_1_q` gap over CRSP is explained by the universe rule
((0.93 - 0.18) / (1.09 - 0.18)). The rest is the ADR and foreign names (V1) plus the remaining data
defects.

The same rule applied to the whole 1991-2024 history, screened at 2024-12, lifts the full-sample
`mom_12_1_q` gap from +0.10 to +0.35%/mo. The bias is largest in the years nearest the screen date.
That matches the vendor's own year pattern: large in 2018-2022, small in 2024-26. It also matches
its near-zero sealed window (+0.26%/mo): the screen date is closest there, so the bias has the
least room.

## 4. The academic benchmark on the same panel: is it just the momentum premium, and has it decayed?

Deciles of 12-1 among eligible names, equal-weight, rebalanced monthly, gross. This is the academic
convention. Our books are net of costs, about 6 bps a month.

| series, %/mo (t) | 1991-2024 | 1991-2000 | 2001-2010 | 2011-2016 | 2017-2024 | 2020-2024 |
|---|---:|---:|---:|---:|---:|---:|
| EW decile spread D10 - D1 | **+0.78** (1.84) | +1.99 (2.26) | -0.48 (-0.51) | +0.76 (1.23) | +0.88 (1.29) | +1.14 (1.20) |
| top decile - EW universe | +0.30 (1.16) | +1.20 (1.70) | -0.44 (-1.27) | -0.08 (-0.28) | +0.39 (0.97) | +0.53 (0.92) |
| top decile, 3-month overlapping (JT) - EW | +0.19 (0.79) | +0.90 (1.34) | -0.48 (-1.56) | -0.07 (-0.24) | +0.35 (0.93) | +0.50 (0.95) |
| Fama-French UMD (published, VW, NYSE breakpoints) | +0.39 (1.68) | +1.09 (2.96) | -0.09 (-0.15) | +0.23 (0.63) | +0.23 (0.56) | +0.23 (0.40) |

The published UMD by period, as a monthly mean:

| period | UMD %/mo |
|---|---:|
| 1927-1990 | +0.73 |
| 1991-2000 | +1.11 |
| 2001-2010 | -0.03 |
| 2011-2016 | +0.21 |
| 2017-2024 | +0.26 |
| 2025 to June 2026 | **+1.21** |

**What this says.**

- **It is the premium.** The long-only momentum top decile beats the equal-weight universe by
  +0.30%/mo over 34 years (t 1.16), and nearly all of that is 1991-2000. The four leads correlate
  0.94 with that top decile, and their twin gap loads 0.43 on UMD.
- **Their net return sits below what those loadings predict.** The FF3+UMD alpha is negative. The
  extreme top 20 is a worse way to hold momentum than the diversified factor.
- **The premium has decayed.** Since 2001 it has been small, with one negative decade (2001-2010).
  The 2025-26 rebound in the published factor (+1.21%/mo) falls outside CRSP on disk. It is also the
  period where the vendor panel's bias is weakest, and the vendor's own 2025-26 twin gap is +4.9 pp
  in 2025 and -2.2 in 2026.
- **The vendor's +0.92%/mo was not the known premium.** It was three times the published UMD for
  its own window.

**Bet-count curve** (from the momentum_on_crsp receipt, `bet_count_curve`):

- **Raw net returns.** The four leads and the top decile form **1 cluster at rho 0.5-0.7** and 2 at
  0.8-0.9. The median pairwise rho is 0.94.
- **Rule - twin, or top - EW.** 1 cluster at rho 0.5-0.6, 2 at 0.7-0.8 and 4 at 0.9.

The four leads are one bet.

## 5. Caveats (stated, not tuned)

- **CRSP universe vs vendor universe.** CRSP here is share codes 10/11 on NYSE, AMEX and NASDAQ.
  The vendor adds ADRs and foreign ordinaries (V1, 255 slots). They earn +0.8% a month in the vendor
  book, so they explain part of the remaining gap, not the main one.
- **Nominal floors in the early 1990s.** The $3 price floor and the $3M dollar-volume floor are
  nominal, so they are stricter in 1991-95 (median 653 eligible names). The same frozen floors are
  used everywhere and were not re-tuned.
- **Open-to-open vs close-to-close.** Before 1992 there is no CRSP open, and before 1998 open
  coverage is partial. Those periods are close-to-close for the affected names, which moves a
  monthly period by at most one session.
- **HINDSIGHT.** Every rule was registered on 2026-09-26. Years 1991-2016 are a foreign slice for
  these rules, but momentum itself was published in 1993, so 1991-2024 is not out of sample for the
  mechanism.
- **CRSP ends 2024-12-31.** The vendor's 2025-26 months, including the sealed window, have no second
  source here.

## 6. Files

| role | path |
|---|---|
| the bridge + the benchmark, slot and universe-rule helpers | `backend/services/crsp_rebuild.py` |
| the runner (`--part panel / run / slots / emulate`) | `scripts/momentum_on_crsp.py` |
| tests (16, offline, synthetic) | `backend/tests/test_crsp_rebuild.py` |
| CRSP panel receipt (panel parquet is local, gitignored) | `backend/data/optimus/crsp_rebuild/panel_2026-09-29T041550Z.json` |
| leads, benchmark, factors, bet count | `backend/data/optimus/crsp_rebuild/momentum_on_crsp_2026-09-29T042053Z.json` |
| vendor vs CRSP slots | `backend/data/optimus/crsp_rebuild/slots_2026-09-29T042802Z.json` |
| the vendor universe rule on CRSP | `backend/data/optimus/crsp_rebuild/emulate_vendor_universe_2026-09-29T043122Z.json` |
| trial amendment | `docs/TRIALS/TRIAL-LIB-FWD-TWIN-1-library-vs-matched-twin.md` (AMENDMENT 2026-09-29 b) |

Reproduce:

- `python -m scripts.momentum_on_crsp --part panel` (about 5 minutes);
- then `--part run`, `--part slots` and `--part emulate`, each with `--panel-run 2026-09-29T041550Z`.

## WHAT WORKS / WHAT DOES NOT / HIGHEST-EV EXPERIMENT

**WHAT WORKS.**

- **The CRSP bridge runs the library's own engine unchanged.** It covers 34 years, delisting returns
  and dead names, at about 20 seconds per rule with twins. It agrees with the published UMD at 0.88
  correlation. Any price- or volume-based library rule can now be read on a survivorship-free second
  source.
- **The slot comparison found the cause, and the emulation proved it.** 42% of slots differ. The
  same names price the same. The difference is which names exist, and the vendor's membership rule
  reproduces about 80% of the gap.

**WHAT DOES NOT.**

- **All four leads, as implementations.** On CRSP 1991-2024 none beats its matched twin (best: qc470
  +0.26%/mo, t 0.90). None is robust to the calendar. Two carry significantly negative four-factor
  alphas. The only positive stretch is 1998-2000.
- **`disp_short_avoid`'s dispersion screen** adds +0.01%/mo to its control, with an MDE of 0.23.
- **The vendor panel as a historical testbed for anything that buys past winners or volatile small
  names.** Its living names were chosen for being liquid in 2026.

**HIGHEST-EV EXPERIMENT.** Re-run the whole price/volume library (all 288 candidate rules) through
this bridge on CRSP 1991-2024, and re-read the 2026-09-27 leaderboard against it.

- **Cost:** about 2 hours of attended compute, $0.
- **Why it is highest-EV:** every row on that board was measured on the same end-liquidity-selected
  panel. The bias favours exactly the rules the board ranked highest: momentum, volatile, small.
  Rules it penalises may be under-ranked.
- **P(changes the roadmap) is high.** It decides whether any library row, or its 30 frozen forward
  books, has a historical reason to exist.

**Second, and cheaper.** Put the alive-but-shrunk names into the vendor panel. That means the members
of `HIGH_DISPERSION_US_v1` cut by the 2026 floor, or all listed names. Then have the reader refuse any
backtest whose living-universe floor is dated after the decision date.

## CONTINUE FROM HERE

The session ended at a deadline. Everything above is computed and in receipts; nothing is half-run.
The panel parquet is local (gitignored). If it is missing, rebuild it first.

```bash
# 0. my tests (offline, ~5 s)
AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_crsp_rebuild.py -q

# 1. the CRSP panel (~5 min; writes crsp_rebuild/panel_<new id>.parquet + .json)
python -m scripts.momentum_on_crsp --part panel

# 2. the leads, benchmark, factors, bet count (~2 min)
python -m scripts.momentum_on_crsp --part run --panel-run 2026-09-29T041550Z

# 3. vendor vs CRSP top-20 slots (~1-2 min; loads the vendor panel)
python -m scripts.momentum_on_crsp --part slots --panel-run 2026-09-29T041550Z

# 4. the vendor universe rule on CRSP (~1.5 min)
python -m scripts.momentum_on_crsp --part emulate --panel-run 2026-09-29T041550Z
```

Not done, in order of value:

1. **The whole price/volume library on CRSP.** Extend `run_rule_set` to take any rule id,
   `LEADS` -> every rule whose `requires` is covered by `PANEL_COLS`; add the missing panel columns
   to `PANEL_COLS` (the panel builder already computes them all). One new run id; compare against
   `strategy_library/leaderboard_2026-09-27T082553Z.json` row by row.
2. **Put the alive-but-shrunk names into the vendor panel.** Pull bars for the
   `HIGH_DISPERSION_US_v1` members cut by the 2026 floor (other repo's universe file, read-only),
   then re-run `scripts.calendar_offset_triplet` on the widened panel.
3. `backend/services/crsp_rebuild.py` is reached from `scripts/`; the reachability test passes.
   The new files are uncommitted (brief: do not commit).
