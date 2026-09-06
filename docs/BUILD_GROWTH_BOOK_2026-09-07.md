# BUILD — THE GROWTH BOOK LAB, 2026-09-07

Mandate `CONTINUATION_2026-09-07b_GROWTH_BOOK_OPUS_PROMPT.md` under
`ROADMAP_2026-09-07_GROWTH_BOOK_AMENDMENT.md`. G1 was already done (commit
`4cd2101`); **G2 → G7 are this session.** Local commits only — nothing pushed,
sealed, ordered, deployed or changed on Railway. Receipts:
`backend/data/optimus/growth_book/`.
Declaration sha256 **`0397b9bfae7d53c1333afe89228c962ee08a1cbf81d04a40d5a33216d6a57655`**.

---

## RESULTS SCOREBOARD

### The sealed-era sentence, beta first

> **beta 0.6681** (intercept **+4.907%/yr, HAC t 0.968**): on **2016-2024,
> unseen in development**, `m12_quality_mom|dd` returned **3.6684×** against
> SPY TR **3.6707×** after **25 bps**, at maxDD **−29.66%** against SPY's
> **−30.99%**. **Sized to the same drawdown budget** the book runs 1.3027× for
> **4.6616×** and levered SPY runs 1.2471× for **4.4823×**. Leverage-neutral TW
> **3.6044** — *below* SPY. `sealed_era_openings: 1`.

**RESULT IMPROVEMENT: a real one, and it is not alpha.** Unlevered, the book
delivered SPY's terminal wealth at two-thirds of SPY's beta and a smaller
drawdown; sized to the same budget it beat levered SPY by 0.18× of terminal
wealth. That is the one wealth condition amendment §5 names, and it is met.
Two conditions are not: **DSR 0.0046 over 128 cells** (bar 0.95) and **family
PBO 0.6429** (`SELECTION_IS_OVERFIT`). Development eras: 1999-2007 **+0.340%/mo
POSITIVE**, 2008-2015 **+0.756%/mo POSITIVE**, 2016-2024 CANNOT DETERMINE by
construction. Amendment §5 gate: **NOT MET.**

### Leverage-neutral top 10 — the COMBINED family after G3, development 2004-01..2015-12, 144 months

Ranked by leverage-neutral TW (the book at SPY's own realised vol, financing
charged). `m*` rows are G3 mutations; the rest are generation 0. SPY over the
same months: **TW 2.0935**.

| # | cell | **beta** | LN-TW | raw TW | maxDD | L@budget | raw p | DSR |
|---|---|---|---|---|---|---|---|---|
| 1 | `m06_lgbm_clf\|dd` 10bps | 0.663 | **4.7893** | 5.3529 | −0.287 | 2.00 | 0.0162 | 0.201 |
| 2 | `m12_quality_mom\|dd` 10bps | 0.767 | 4.5081 | 5.3842 | −0.357 | 1.81 | 0.0184 | 0.247 |
| 3 | `m17_quality_mom\|dd` 10bps | 0.318 | 4.4763 | 3.1996 | −0.222 | 2.00 | 0.0300 | 0.020 |
| 4 | `lgbm_clf\|dd` 10bps (gen 0) | 0.776 | 4.4310 | 4.4116 | −0.445 | 1.45 | 0.0146 | 0.278 |
| 5 | `quality_mom\|dd` 10bps (gen 0) | 0.779 | 4.2154 | 4.9241 | −0.393 | 1.65 | 0.0168 | 0.254 |
| 6 | `m02_quality_mom\|dd` 10bps | 0.757 | 4.1724 | 4.9326 | −0.327 | 1.92 | 0.0251 | 0.191 |
| 7 | `m12_quality_mom\|dd` 25bps | 0.765 | 4.1027 | 4.8165 | −0.363 | 1.79 | 0.0334 | 0.184 |
| 8 | `m20_lgbm_clf\|dd` 10bps | 0.450 | 4.0080 | 3.0399 | −0.253 | 2.00 | 0.0744 | 0.019 |
| 9 | `m16_lgbm_clf\|dd` 10bps | 0.745 | 3.9966 | 4.4117 | −0.313 | 2.00 | 0.0437 | 0.147 |
| 10 | `m17_quality_mom\|dd` 25bps | 0.316 | 3.9883 | 2.9492 | −0.226 | 2.00 | 0.0518 | 0.014 |

**Every one of the top ten carries the `dd` overlay, and every one has beta
below 0.8.** Family-min raw p 0.0146, **best Holm 1.0**, best BH-FDR 0.5098,
best DSR 0.278. Nothing survives the family correction. Every cell's verdict
names *which* bar it failed rather than collapsing three questions into "NOISE"
— e.g. `FAILS: FAMILY_HOLM+DSR_DEFLATION`.

### NN sizing vs trailing-vol sizing (G5), development 1999-2015, at equal drawdown

| arm | **beta** | TW at budget | leverage | DSR |
|---|---|---|---|---|
| **constant 1× (the null)** | 0.7224 | **5.6264** | 1.332× | 0.4206 |
| trailing vol (Moreira-Muir) | 0.8970 | 3.7599 | 0.992× | 0.3380 |
| NN seed-mean, quarter-Kelly | 0.6035 | **1.0546** | 1.142× | 0.0073 |

**NN sizing is worse than the baseline and both are worse than doing nothing.**
`MATURED = False`. Seed spread of TW at the budget across eight seeds:
**0.7275 / median 1.5789 / 5.7383** — an eight-fold range on identical data, and
the seed-mean sits *below* the median seed. CUDA used (RTX 5060, sm_120, torch
2.11.0+cu128, base interpreter — recorded because the repo `.venv` is CPU-only).

### Forward-lane beta table (G7)

| **beta** | Dimson β | R² | lane | n | raw exc pp | LN exc pp | maxDD | SPY maxDD |
|---|---|---|---|---|---|---|---|---|
| −0.0416 | 0.116 | 0.006 | conservative | 47 | −2.497 | −1.862 | −2.33% | −3.38% |
| −0.0317 | 0.111 | 0.004 | balanced | 47 | −2.311 | −1.495 | −2.24% | −3.38% |
| −0.0267 | 0.137 | 0.002 | aggressive | 47 | −1.064 | −0.097 | −2.59% | −3.38% |
| 0.0972 | 0.690 | 0.015 | balanced-ew-control | 45 | −6.107 | −6.333 | −5.99% | −3.38% |
| 0.5563 | 1.211 | 0.047 | mirror | 41 | −22.148 | −10.217 | −24.65% | −3.38% |
| 0.7163 | 1.931 | 0.050 | conviction | 41 | −7.680 | −3.566 | −21.28% | −3.38% |
| 0.0389 | 0.125 | 0.006 | conservative-atr | 40 | **+0.144** | +3.307 | −1.51% | −3.38% |
| — | — | — | smallmid-quality / tsmom-overlay / tsmom-6040-control | 17/14/14 | CANNOT DETERMINE — below the 20-observation floor |
| — | — | — | hack1…hack6 | 4 each | CANNOT DETERMINE — **account age**, not readability: frozen at genesis 2026-08-28 |

**The question "why do conservative-ATR and aggressive beat SPY" now has a
number.** conservative-atr is the only positive raw excess — **+0.144 pp at beta
0.039** — in a window where SPY rose ~2%. It did not out-select SPY; it sat the
window out. The two lanes with real beta both lost heavily. And the beta column
itself is **biased toward zero**: R² vs SPY is 0.0015-0.05 on all seven, which
is not credible for an equity book, and Dimson lead/lag says why — `conviction`
loads 0.66 on today's market and **1.50 on yesterday's**. A book cannot react a
day late; its **marks** can. The lane NAV is marked on stale prices, and a stale
mark *hides* beta — the one thing §2.2 forbids.

---

## Ten claims for Fable to attack

1. **The sealed-era win is 0.18× of terminal wealth over nine years and one
   draw.** 4.6616 vs 4.4823 at the budget is +4.0% of terminal wealth across
   107 months. What is the standard error of that difference on one path?
2. **The gate was corrected after the sealed numbers were visible.** As first
   written it compared the unlevered book to levered SPY. The correction is on
   the receipt (`amendment_gate_5._correction`) and changes one sub-condition
   without changing the verdict — but it *was* made after seeing the numbers.
3. **The champion is a mutation, and the mutation round is a DRAW.** Three
   DeepSeek calls at temperature 0.0 returned three different proposal sets;
   round 2's leader was *higher* (LN-TW 5.4803) and is not claimed. `n_trials =
   128` is a lower bound on the deflation this search deserves.
4. **`quality_mom` is ROE, not gross profitability.** `gprof` starts 2013-01 in
   this repo's WRDS pull. Is rank(ROE) + rank(momentum) the quality-momentum
   recipe the literature means, or a different signal wearing its name?
5. **Every top-ten cell carries the `dd` overlay.** The overlay raises
   leverage-neutral TW by lowering the drawdown, which buys a larger admissible
   size at the same budget. Is that a real mechanism or a drawdown-targeting
   rule fitted to two crises (2000-02, 2008-09) that are 60% of the sample?
6. **The development window is 144 months, not 202.** The model genomes'
   walk-forward warm-up forced a common window of 2004-2015 for the
   leaderboard. Does the ranking change on 1999-2015 for the genomes that can
   be graded there?
7. **The 25-bps cost is a constant, not a model.** Mean turnover 0.205/month on
   110 names in a $3m/day universe. Is 25 bps a side plausible for the *small*
   half of that universe in 2000-2004?
8. **P(lose half) is 0.232 at 1×.** From a stationary block bootstrap of the
   book's own months. Does a block bootstrap of a series whose overlay is a
   function of its own history preserve the right dependence?
9. **G5's null beats both sizing rules** — but the null is the champion, whose
   `bsc` overlay *already* targets volatility. Is "flat 1×" really flat, or is
   the comparison two vol-targeting rules against a third?
10. **G7's stale-mark finding invalidates the lane beta column it appears in.**
    If the marks are stale, the leverage-neutral column (SPY vol ÷ book vol) is
    an upper bound on all seven rows. The table should probably not be quoted
    until the lane weights are repriced at the official close.

## Three defects this session found in its own work

- **The stage join was positional and should have been by label.** The first
  G2 loader did `reset_index(drop=True)` then `reindex(range(len(df)))` against
  W3b's `_row`, which stores the *original panel index label*. 57.3% of labels
  existed — exactly the floor's `share_kept` — so every prediction column looked
  fully populated **while sitting on the wrong rows**. The only tell was a
  non-null `lgbm_clf` in 2002 and 2003, before the first test year of the fit
  that produced it. The loader now joins by label and refuses on either symptom.
- **The provenance record named a file that had been opened, at a path that did
  not exist.** `_rf_daily` stamped `bm.provenance["path"]` under `REPO / p`,
  but that path is relative to the repo's *parent*, so the tracker recorded
  `aegis-finance/aegis-finance/backend/data/ff_daily_pinned.csv.gz` and
  `check_receipt` correctly returned `INPUTS_MISSING_ON_DISK` for a file the
  loader really had read. That is the W4b defect in miniature — the record
  described the open instead of naming what was opened. It now takes
  `benchmark._PINNED_CSV`, the constant the loader itself reads, and **every
  growth receipt except one is now provenance-clean (0 hard findings)**. The
  exception is `G4_CHAMPION_DECLARATION.json`, which keeps the pre-fix path
  because **G4 cannot be re-run without re-opening the sealed era** — the latch
  binding on its author is the intended behaviour, and the file it names was in
  fact opened. A second defect in the same area: the first `--regate` called
  `RP.attach` on the finished receipt and **replaced the run's input list with a
  one-entry list naming the receipt itself** — a correction that erased the
  record of what it was correcting. Fixed; the run's list is preserved beside
  the regate stamp.
- **`grade_by_era` described nine years of a twenty-six-year panel in silence.**
  `evaluate.ERAS` is hard-coded 2016-2024; a 1999-2024 panel put 65.38% of its
  rows in no bucket and nothing said so. `era_coverage` + `long_eras()` now
  derive-or-refuse; the constant did not move and the 2016-2024 numbers are
  proved byte-identical by a test carrying a verbatim copy of the pre-fix loop.

## What is queued, not done

The sizer's **sealed-era** test (deliberately: the champion's contract is not
frozen by Murat yet) · repricing the lane NAVs at the official close, which G7
says every forward beta depends on · a second sealed window when 2025 is on
disk, the only clean answer to PBO 0.6429 · `learner_run.py:236` and
`learner_v2_run.py:345` still pass no `eras=`, so a long-panel run there now
*refuses* rather than silently reporting nine years — the follow-up is to pass
`E.long_eras()` at both sites.

## Counts, spend, provenance

- **Finance fast suite: 6,984 passed, 14 skipped, 122 deselected in 541.58 s, exit 0** (`AEGIS_IGNORE_DOTENV=1 python -m pytest
  backend/tests/ -m "not slow" -q --timeout=300`; an earlier pass before the
  provenance fixes gave the same 6,984 / 14 / 122 in 560.90 s). Two
  complementary `-k` slices of the same tree sum to exactly 6,984 (644 + 6,340).
  New this session: `test_growth_lab.py` **25**, `test_growth_g3_validator.py`
  **20**, `test_growth_g4_seal.py` **12**, `test_growth_sizer.py` **15**,
  `test_growth_g7_lanes.py` **18**, `test_growth_eras.py` **7** — **97 new**,
  on top of G1's `test_growth_ruler.py` (18).
- **LLM spend: $0.0132** of a $3.00 job cap — three DeepSeek `deepseek-v4-flash`
  calls (round 1 $0.004644 all-refused, round 2 $0.004101 unreproducible, round
  3 $0.004492 recorded), 3,555 prompt tokens, 11,161 completion tokens, every
  output hash in the ledger. **$0.0132 for 20 evaluated mutations = $0.00066 per
  gradeable cell.** G2, G4, G5, G7: **$0.00**.
- **Zero network calls** outside those three: SPY is a pinned CSV, RF is the
  pinned Fama-French vintage, the learner predictions are W3b stage parquets.
  No Railway write, no order, no seal, no deploy, no `.env` touched.
- **Reading `sealed_era_openings` on G2/G3/G5:** it is a count of how many
  times the sealed era has EVER been opened, read live from
  `SEALED_ERA_OPENINGS.jsonl`, so it reads **1** on receipts regenerated
  after G4 ran. Whether the job itself looked is the separate flag
  `sealed_era_touched_by_this_job`, **false** on all three. The ledger has
  exactly one line.
- The frozen champion **rebuilds to its recorded hash** from a fresh panel
  build and the pinned tapes — `39ab3224c1a12e14…`, pinned by a `slow`-marked
  test added after the suite run below started (so the next fast run will
  read 123 deselected, not 122).
- Every receipt carries `_provenance` — argv, resolved config, and the SHA-256
  of every input actually opened (`backend/services/receipt_provenance.py`).
  `check_receipt(verify_hashes=False)` over all eight growth receipts: **0 hard
  findings on seven, 1 on `G4_CHAMPION_DECLARATION.json`** for the reason above.
- **7 local commits on `main`, nothing pushed** — `a2e0ea2` (the ERAS refusal, queued from Labor Day B1), `c906638` G2, `dd436b2` G3, `46c08d6` G7, `cf9b95e` G4, `0dcf72e` G5, and this document with G6.
