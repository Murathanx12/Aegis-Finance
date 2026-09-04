# FINDING — the tape rebuilt: one share basis, delisting returns merged

**Date:** 2026-09-04 (built), 2026-09-05 (this write-up).
**Roadmap:** `ROADMAP_2026-09-04_PROFIT_ENGINE.md` B1 tasks 3 and 6 — the gate item.
**Licence:** the rebuild is infrastructure. The numbers below are *census and
provenance*, not alpha claims. Strategy results on this panel are B1 task 4.
**Receipts:** `backend/data/optimus/tracker_backtest/panel_rebuild_20260904.json`
· `signal_engine_backtest_20260904.json` · `docs/DATA_MANIFEST.md`.
**Adjudication of the review this rests on:**
`VERIFICATION_2026-09-04_OPUS5_ON_FABLE51.md`.

---

## 1. The defect, in one line

`learner/dataset.py` divided IBES's **split-ADJUSTED** consensus (`ibes__ptgsum`,
restated in *end-of-sample* share terms) by the **raw** CRSP close. The numerator
knew about every split after time *t*; the denominator did not.

    ratio_used  ≈  true_ratio / cfacpr(t)

`cfacpr(t)` is a future quantity, so a name that **later reverse-splits**
(`cfacpr < 1`) had its ratio inflated and landed in `toxic_ge_5`, while a name
that later forward-split was pushed down into `lt_1_5`. Reverse splits are what
collapsing companies do. **`toxic_ge_5` was a future-collapse detector.**

The hand-check that settles it, and the row every future basis audit should copy:

| AAPL, `statpers` 2013-06-20 | value |
|---|---|
| `ibes__ptgsum.meanptg` (adjusted) | **19.323** |
| `ibes__ptgsumu.meanptg` (unadjusted) | **541.04** |
| ratio of the two | **28.0** — exactly AAPL's 7:1 (2014) × 4:1 (2020) |
| raw CRSP close (panel, one lagged session) | 413.50 |
| ratio the old tape computed | **0.0467** |
| ratio the rebuilt panel computes | **1.30844** |

---

## 2. Before and after

### 2a. The band census — the structural change

| band | old tape (name-months) | rebuilt panel | change |
|---|---|---|---|
| `lt_1_5` | 285,173 | **298,356** | +13,183 |
| `b_1_5_3` | 48,289 | **59,376** | +11,087 |
| `b_3_5` | 5,888 | **8,264** | +2,376 |
| `toxic_ge_5` | **24,358** (prior.py cross-section) / **26,199** (split-free universe) | **2,123** | **−92%** |
| `no_opinion` (hygiene) | — | 73,678 | now a first-class label |

Where the 26,199 old "toxic" rows actually belong under a point-in-time ratio
(reproduced **cell for cell**, twice, independently): **2,965** stay toxic,
**11,072** are really 1.5–3, **3,339** are 3–5, and **8,823** are **below
1.5** — the opposite end of the scale. Under the panel's full hygiene the
surviving toxic cell is 2,122–2,123 rows.

### 2b. Where the old "toxic" return came from

Split the ORIGINAL toxic band by whether a future split exists:

| subset | 1m EW excess vs VW | t | names/mo |
|---|---|---|---|
| `cfacpr == 1` (no future split) | **−13.38%/yr** | −1.65 | 40 |
| `cfacpr < 1` (future reverse split) | **−48.88%/yr** | −7.14 | 147 |
| the published constant | −37.77%/yr | −7.75 | — |

**74.35%** of the original toxic rows carry a future reverse split, against
**0.09%** of `lt_1_5`. The −37.77 constant is the second row of that table
leaking into the first.

### 2c. The four receipts now void

`band_horizon_20260903` · `toxic_band_short_20260904` ·
`holding_period_policy_20260903` · `revision_6m_cohorts_20260904`, plus
`exp_return_cross_section`, `upside_band_decontamination`,
`ibes_status_rules_2013_2024`, `time_machine_arena`, and every `ratio`-bearing
learner feature set. Each keeps a `SUPERSEDED_BY` sidecar; none is edited or
deleted.

### 2d. B1 task 4 — the four receipts re-issued (2026-09-05)

Re-run on the clean panel. Each new receipt carries `supersedes`, a canonical
`learner.benchmark` stamp, a family size with the correction declared **PENDING**
(B4 does not exist), and a per-row zero-cost flag; each sealed receipt now
carries a `<name>.SUPERSEDED_BY.json` sidecar recording **both** sha256s. Pinned
by `backend/tests/test_reissued_tape_receipts.py` (47 tests).

**The direction of every correction is the same: the ratio screen was buying
different names than the receipts said, and the corrected screen loses.**

| object (1m, 10bps unless noted) | void | re-issued |
|---|---|---|
| `lt_1_5` excess vs VW | −0.82%/yr, t_b −0.37 | **−2.17%/yr, t_b −0.96** |
| `b_1_5_3` excess vs VW | +3.80%/yr, t_b +0.64 | **−6.82%/yr, t_b −1.15** |
| `b_3_5` excess vs VW | +18.93%/yr, t_b +1.65 | **−5.26%/yr, t_b −0.47** |
| `toxic_ge_5` excess vs VW | −37.03%/yr, t_b −6.25, 168 names/mo | **+40.07%/yr, t_b +1.97, 7 names/mo** |
| …the same cell at **close ≥ $5** | — | **−34.29%/yr, t_b −1.46, 2 names/mo** |
| BH-FDR screen survivors (32-cell family) | 8, all of them the toxic cell | **0** |
| toxic short, 1m, `hedged_beta` | +61.94%/yr "hedged gross", t_b 6.85 | **−32.29%/yr, t_b −2.07** (`−resid` on Reg-T capital; `beta_matched` leg +18.78%/yr) |
| …its best line, `liq_floored_hedged_beta` | +76.63%/yr, t_b 7.24 | **−29.25%/yr, t_b −0.88** (`beta_matched` leg +34.89%/yr) |
| `rev_top50/fixed_H6m_25bps` (the S36 champion) | TW 3.743, excess +1.67pp/yr, t +0.69 | **TW 1.284, excess −10.08pp/yr, t −1.00** |
| best arm of 150 at 25bps, by excess CAGR | several positive | **−6.33pp/yr** (none positive) |
| VW market TW over the same window | 3.41 | **3.41 — unchanged** |

The last row is the control: the ruler did not move, the selection did, which is
exactly what a share-basis defect inside an *admission threshold* does.

Two results the re-issue **adds** rather than corrects:

- **The toxic cell must never be quoted alone.** +40.07%/yr comes from a
  population whose median close is **$3.08**, 84.2% of it under $5 and 86.1%
  below $3m/day; its **median** monthly excess is **−0.60%** against a +2.85%
  mean (a right tail, not a location shift); 2022-24 is **+0.66%/yr, t 0.03**;
  and a $5 floor flips the sign. Both toxic-bearing receipts now carry a
  `MANDATORY_TOXIC_BAND_DISCLOSURE` block, and a test fails if either loses it.
- **Revision ranking and revision money are different questions.** Over the
  **full PIT hygiene universe** (363,684 name-months, 5.4× the old admissible
  pool), `target_rev_1m` gives TW 2.937 and `net_rev_1m` TW 3.102 against a
  market 3.236 at 25bps — excess CAGR −1.10pp and −0.48pp, t_NW(5) 0.19 and
  0.07: **neither beats the market.** Yet both beat **all 64** permutation draws
  from their own pool (percentile 1.000; p = 1/65 is the add-one **floor**, a
  censored bound, not a measurement). The two definitions *agree*, and the one
  that cannot inherit a share-basis defect (`net_rev_1m`, a count of up/down
  revisions that touches no price) is the marginally better of the two. So the
  ranking carries information and the pool does not carry a premium.

**The dying-name limitation, quantified rather than named.** `build_monthly`
drops a row whose `fwd_1m` has no next monthly row, so a dying name's final month
is absent. Measured on the rebuilt panel: **3,251 of 441,797 rows (0.736%)** carry
no `fwd_1m`, and the per-band incidence is **0.68% / 0.69% / 0.79% / 1.37%** for
`lt_1_5` / `b_1_5_3` / `b_3_5` / `toxic_ge_5`. The mechanism removes terminal
losers, so every band's LEVEL is mildly generous — but the band-to-band **spread**
in incidence is under **0.7pp**, which cannot move a band contrast of tens of
percent. `holding_period_policy` and `revision_6m_cohorts` do not read `fwd_*` at
all (they simulate off the daily CRSP return matrix), so there the limitation
bites only *admission*: a name in its final month is never bought, equally in
every arm and in every null draw.

Receipts: `band_horizon_20260905.json` · `toxic_band_short_20260905.json` ·
`revision_6m_cohorts_20260905.json` · `holding_period_policy_20260905.json`.

---

## 3. What else the rebuild fixed

### 3a. Delisting returns are now merged (they never were)

`crsp.dsf.ret` is **not** delisting-inclusive: of 1,114 performance delistings
with a `dsf` bar on `dlstdt`, only **4** have `ret == dlret`. Mean `dsf.ret` on
that bar is −9.2% against a `dlret` of −19.6%. Longs were flattered; the panel
was survivorship-free in *membership*, not in *returns*.

`crsp__dsedelist.parquet` was on disk and never joined. Now merged, 2013-24:

| category | `dlstcd` | n | mean `dlret` |
|---|---|---|---|
| performance | `{500} ∪ [520,584]` | **866** | **−24.63%** |
| liquidation | 400-489 | 223 | −0.74% (separate category, no fill) |
| merger / exchange | 200-399 | 1,975 | +0.91% |
| other | — | 25 | — |

Shumway (1997) fills applied to **53** rows with a performance code and no
`dlret` (39 NASDAQ at −55%, 14 NYSE/AMEX at −30%). Applied to 2,683 permnos,
mean terminal factor 0.92079, zero out-of-range. Filled rows carry a 1m mean
forward return of **−9.65%** against **+1.17%** for the rest — the merge is not
cosmetic.

**Note the direction this cuts.** The old toxic band had the *lowest* 1m
delisting incidence of any band (0.26%), because its members were future
reverse-*splitters*, i.e. survivors. The corrected toxic band has the
**highest** (1.79%). So merging `dlret` makes the corrected toxic cell *worse*,
not better.

Two comments in the code said otherwise and are fixed:
`scripts/tracker_ibes_backtest.py:278` claimed "delisting return included" —
flatly false. `:256` was hedged. **`learner/dataset.py:55-57` was already the
honest caveat** and was extended, not corrected — the S38 review had cited the
one place that got it right as a place that got it wrong.

### 3b. Hygiene moved into the dataset, once

`hygiene_ok` is True on **368,119 of 441,797** rows (83.3%). Failures: 62,801 on
the price/coverage floors, 275 on `ratio ≥ 50`, 15,919 on split-year. Failing
rows are **kept**, with `ratio`/`upside`/`log_ratio` NULLed (mirrored in the
`miss__*` columns), `band` set to `no_opinion`, and the raw value preserved in
`ratio_unhygienic`. That distinction is deliberate: *"no opinion"* is a
different statement from *"historically bad"*, and below $2 the prior was
measured **uninformative** (t 0.39), not negative.

### 3c. The universe claim was wrong, and no re-pull is needed

The CRSP daily pull holds **6,894** distinct permnos 2013-24; a full
`shrcd ∈ {10,11}` ∧ `exchcd ∈ {1,2,3}` screen gives **6,909**. **Zero** pulled
permnos fall outside the screen and **15** (0.22%) are missing — they are named
in the receipt. It is a **99.78%-complete subset**, not the "screened superset"
the review described. `assert_universe_coverage()` refuses below 99%.

### 3d. 58.52 GiB of substrate is now on record, and 14.25 GiB of it is duplicate

`docs/DATA_MANIFEST.md` named exactly **two** objects under `wrds/`, both JSON
(54.5 MiB). The tree holds **1,378 parquet files / 58.52 GiB / 1.93 bn rows / 84
families**. So the manifest was missing 99.9% of the bytes it was supposed to
cover, not the ~93% the review estimated — the review **undercounted**.

The duplication has a named cause: `scripts/wrds_pull_everything.py` keys its
resumability on the output **filename** (`{schema}__{table}.parquet`), and WRDS
exposes several libraries under two names, so each was pulled in full twice and
neither run could see the other. It is visible in the manifest's own table —
`ibes__*` and `tr_ibes__*` are both 3.39 GiB / 239,972,895 rows; `optionm__*`
and `optionm_all__*` both 2.94 GiB / 227,529,431 rows.

- library-alias duplicates: **294 files, 13.90 GiB** (23.7% of the tree)
- upstream-identical under two table names: 18 files, 0.35 GiB
- `bulk/_quarantine_truncated/`: 23 files, 1.45 GiB, stopped at round counts
  (`optionm__*` at exactly 144,000,000 rows) — the round numbers are the tell

Verified by footer SHA-256 with full-file hashes on seven pairs. Method note:
`crsp__dsenames` vs `crsp__msenames` differ by **3 bytes** and are genuinely
different content, so size-matching alone would have been wrong. **Deletion is
Murat's call**; the forward fix is an alias table in the puller.

---

## 4. What this does NOT establish

**No band premium survives a point-in-time ratio.** The corrected `toxic_ge_5`
cell measures +37.44%/yr t 1.94 on ~7 names/month and must not be read as a
long: 84.1% of it trades under $5 (median close $3.08); a $5 price floor **flips
the sign to −31.6%/yr t −1.41**; its median monthly excess is **−0.86%** against
a +2.69% mean; 2022-24 is +0.7%/yr t 0.03; and 27.6% still carries a future
reverse split, with the estimate moving **+56pp** when those rows are dropped.
Full argument: `VERIFICATION_2026-09-04_OPUS5_ON_FABLE51.md` §4.

Consequences, both recorded in the panel receipt as `prior_status: VOID`:

1. `BAND_PRIOR` v2's four constants are now applied to a *corrected* ratio and
   are therefore meaningless. `prior_*` and `resid_*` columns are carried for
   schema continuity only and **nothing may read them as an expected excess
   return**. The attended proposal is
   `PROPOSAL_2026-09-04_BAND_PRIOR_TO_HYGIENE_ONLY.md`.
2. The learner v2 champion carried `ratio`, `log_ratio`, `ratio__xs` and
   `band_code` among its 49 features, and subtracted a full-window in-sample
   prior from a value-weight excess against an equal-weight-benchmarked prior.
   It must be refitted, and only after B4 exists — its t 2.64 already sat at the
   maximum of its own 64-draw noise distribution, and the family correction over
   its ~44 cells is not merely uncomputed but **not computable** from any stored
   draws (no per-arm null exists for 11 of the 16 arms).

**And a shortcut that does not work:** `ratio × cfacpr(t)` is not a fix. It
agrees with the true PIT ratio on only **93.0067%** of the 441,223 rows that
carry a ratio, and used as a band it leaves toxic at −20.3%/yr t −2.70 — because
`cfacpr(t)` is itself a future quantity. The column survives as
`ratio_adj_check`, a **diagnostic** whose disagreement rate is printed at build
time, and nothing else.

---

## 5. Open items this rebuild leaves

| item | status |
|---|---|
| Re-issue the four tape receipts on the clean panel | **DONE 2026-09-05** — §2d; four new receipts, four sidecars, `test_reissued_tape_receipts.py` (46 tests) |
| The `sensitivity_splits_kept` arm of the band study is now **degenerate** | structural: split-year hygiene moved *into* `learner/dataset.py`, so all 15,919 `split_prior_year` rows are labelled `no_opinion` and cannot enter a band. The arm is identical to primary cell-for-cell. Re-asking the question means re-banding from `ratio_unhygienic`, which is a different study and needs its own receipt |
| The scored window was **not** pinned across selection pools until this task | `hpp.run_fixed` scored each cohort from its own 24th rebalance, so two pools came back against market terminal wealths of 3.2362 and 3.41 — the difference would have read as a result. Fixed with an optional `start_day`; the revision receipt now checks the invariant and records it |
| `build_monthly` drops a dying name's final month (`fwd_1m` needs a next monthly row) | named in code and receipt; deliberately not fixed — fixing it means re-issuing that script's receipts |
| 14.25 GiB of duplicate WRDS parquet | Murat's call; forward fix is an alias table in `wrds_pull_everything.py` |
| The 15 missing permnos (0.22%) | named in the receipt; no re-pull warranted |
| Live band thresholds on the six paper books | attended — and note they read **Finnhub unadjusted** targets, a *different object* from this tape, whose thresholds were imported from the corrupted tape and have therefore never been tested on the data they actually consume |

## 6. Provenance

Panel: 441,797 rows × 142 columns, 144 months, 5,721 permnos, 61 s to build,
`SCHEMA_VERSION = "learner-train-table-2"`. The v1 schema receipt was moved
aside to `train_table_schema_learner-train-table-1_SUPERSEDED.json`, verified
byte-identical to the committed copy — nothing was clobbered.

Fast suite after the rebuild: **6,327 passed, 17 skipped, 0 failed**.
`backend/tests/test_ibes_target_share_basis.py` — written as `xfail(strict=True)`
to pin the defect — is now a **plain passing test**. An xfail that survives its
own fix becomes a green line nobody reads.
