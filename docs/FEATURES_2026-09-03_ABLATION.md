# Ownership and analyst-identity features: a 16-cell negative

**Date** 2026-09-03 · **Licence** `PRODUCT_EXPERIMENT` · **Receipt**
`backend/data/optimus/tracker_backtest/feature_ablation_20260903.json`
**Code** `learner/features_ext.py` (features) · `scripts/feature_families_run.py`
(ablation) · `backend/tests/test_feature_families.py` (19 offline tests)

## RESULT IMPROVEMENT: NONE

Three families of 13F-ownership and analyst-identity features were built and
ablated against the learner's existing base. **Not one of them added
out-of-sample value at either horizon under either model.** The paired delta in
monthly rank IC is negative in **16 of 16 cells**.

| set | 1m ridge | 1m lgbm | 12m ridge | 12m lgbm |
|---|---|---|---|---|
| `base` (mean IC) | +0.07101 | +0.06680 | +0.14046 | +0.15961 |
| `+analyst` ΔIC | **−0.00934** (t −3.74) | −0.00599 (t −1.65) | −0.01714 (t −4.49) | −0.01259 (t −3.46) |
| `+holder` ΔIC | −0.00352 (t −1.82) | −0.01012 (t −2.29) | −0.00498 (t −2.42) | −0.01345 (t −4.79) |
| `+analyst+holder` ΔIC | −0.01115 (t −3.02) | −0.00793 (t −2.11) | −0.01888 (t −4.28) | −0.01901 (t −4.38) |
| `+interaction` ΔIC | **−0.01445** (t −3.54) | −0.01047 (t −2.34) | −0.02035 (t −4.82) | **−0.03435** (t −7.64) |

n is MONTHS (143 at 1m, 132 at 12m), never name-months. At 12m the monthly
formations overlap, so `n_effective_blocks ≈ 11` and the block-adjusted t is
reported beside the naive one; **after that correction the 12m incremental steps
are not significant, though every one of them still points the same way.** At
1m, where there is no overlap, the negatives are significant on their own.

The direction is monotone down the ladder: each family added subtracts more.
The worst single cell is the interaction family at 12m under LightGBM,
ΔIC −0.03435, t −7.64.

## What was built, and what was deliberately not

Standing evidence said the *standalone* versions of these things are thin or
dead, so nothing here re-runs a closed negative:

- **NOT built — sentiment / novelty / attention.** T12 measured that only 7.7%
  of corpus news is a new dated fact, and Benzinga's 390:1 coverage ratio makes
  "requires news" a mega-cap filter wearing a sentiment costume.
- **NOT built — accuracy-weighted consensus.** Analyst *accuracy* does not
  persist (Spearman 0.087). The design is dead before it is written.
- **Built — bias-corrected consensus**, because analyst *bias* does persist
  (Spearman 0.376, decile means −2.8pp to +80pp).

**A. analyst family** (13 features) — from the row-level graded-target panel
(1,333,683 targets, 9,158 analysts, `amaskcd` following a person across firms):
PIT per-analyst bias, bias-corrected consensus, revision acceleration, coverage
thinness at the measured edge band (coverage <= 10, <= 3).

**B. holder family** (19 features) — built from Thomson `s34` over 52 quarters
(45,018,857 positions to 171,822 name-quarters, 7,152 names): holder-count
change, institutional ownership, entry/exit fractions split by **filer-duration
cohort**, complete-exit flag, **stake size versus the filer's own history**
(the adverse signal), specialist-holder concentration, top-5 crowding.

**C. interaction family** (9 features) — products of legs whose main effects are
both already in `base+analyst+holder`, so the ablation asks an interaction
question rather than a disguised main-effect one.

## The single best interaction feature

`x_holder_anom_x_thincov` — the filer's own-history stake anomaly x coverage
thinness.

| horizon | mean IC | t | block-adj t | months | coverage |
|---|---|---|---|---|---|
| 1m | **+0.02060** | +4.12 | +4.12 | 143 | 0.92 |
| 12m | **+0.03851** | +7.81 | +2.25 | 132 | 0.92 |

It is the best because it is the only interaction that is (a) consistently
signed across both horizons, (b) stronger than its own holder leg
(`h_stake_anom_mean`: +0.01222 t +2.27 at 1m), and (c) the specific hypothesis
the brief posed. **And it still did not help the model** — LightGBM gave it a
gain share of 0.00056, the *lowest* of all nine interactions, and the family it
belongs to subtracts in all four cells. A univariate IC says what a feature
knows; it says nothing about whether the model already knew it.

## The one genuinely new finding: the adverse stake effect is a TAIL, not a line

The holder receipt's adverse result replicates here, independently — and
sharpens:

| feature | 1m IC | t | 12m IC | t | block-adj t |
|---|---|---|---|---|---|
| `h_stake_anom_top_decile_frac` | **−0.02739** | −4.14 | **−0.05999** | −8.24 | −2.38 |
| `h_stake_anom_mean` | **+0.01222** | +2.27 | +0.01607 | +3.03 | +0.88 |

The two have **opposite signs**. A moderately-large-for-that-manager stake is
mildly good; the fraction of holders sitting in *their own top decile* is
clearly bad. So the `-1.21pp/252s t -3.95` adverse result is not a linear
stake-size effect that happens to be measured at the extreme — it is a **tail
effect**, and a model fed the linear version is fed the wrong variable. That is
worth carrying forward even though the family failed.

## Why the families failed: they are the popularity corpse

The holder features that score best univariately are exactly the ones the base
model already owns through size and liquidity:

| feature | 1m IC | t |
|---|---|---|
| `h_n_holders` / `h_log_n_holders` | +0.08470 | +8.01 |
| `h_top5_share` | −0.08342 | −9.52 |
| `h_inst_own` | +0.07175 | +9.91 |

These are the **13F-popularity corpse** — a known non-signal that restates
market cap and float. `log_market_cap`, `log_dollar_vol_20d` and their
cross-sectional ranks are already base features, so the family contributes
collinear restatement plus estimation noise. That is the mechanism of the
negative, and it is why LightGBM spent only 5.7% of its gain on the holder
family and 4.1% on the interactions while the base kept 85.2%.

## The controls, so the negative is a negative and not an artefact

- **Shuffled-target null** (permuted WITHIN each month, never across — a
  shuffled *date* null controls for the calendar, which was S24's mistake):
  mean IC **−0.01001**, t −1.608 over 107 months; book terminal wealth 3.24
  against a market of 4.86. Nothing scores. The plumbing is clean.
- **Missingness control.** A family that is NaN on a third of the table is
  handicapped for a reason that is not about the mechanism, so the 1m ablation
  was re-run on the **complete-case subsample** — 373,963 rows (84.8%), 141
  months, every family present. The verdict survives: ΔIC negative in 7 of 8
  cells, the single exception being `base+holder`/ridge at **+0.00064, t 0.347**
  — which is zero.
- **`base+holder` is in the ladder on purpose.** A purely nested ladder cannot
  say *which* family a joint loss came from, and a negative has to be
  attributable to be worth recording.

## Stated limitations

1. **Terminal-wealth deltas are reported but NOT paired-tested.** A difference
   of two terminal wealths is one draw of a correlated pair. This does not
   overturn the verdict, because **the base book itself does not beat the
   market**: t 1.215 (ridge) and 0.599 (lgbm) over 107 months. Every wealth
   delta is therefore noise on noise. The fix is queued and cheap —
   `evaluate.book(..., return_series=True)` already returns the monthly net
   series and `evaluate.hac_t` / `block_t` handle the 12m overlap.
2. **The Thomson vintage check did NOT pass cleanly**, and is reported as such:
   2,156 of 45,018,857 positions (0.005%) carry a vintage later than their
   report quarter, so `vintage_reduction_valid` is **false**. Those rows push
   their name's public date out to the later vintage rather than being ignored.
   91% of panel rows carry no extra lag; the rest are 1-4 quarters stale. The
   bias is toward *less* information, never more.
3. **Specialist features read SIC 9999 as an industry.** `sector_entropy` treats
   NONCLASSIFIABLE as a bucket, so a filer concentrated in UNKNOWN reads as
   concentrated. Treat `h_specialist_frac` and `x_specialist_x_thincov` as
   noisier than the rest.

## The PIT rules these numbers rest on

- **13F** is public at `quarter_end(max(rdate, latest Thomson vintage)) + 45
  calendar days`, joined as-of BACKWARD on the trade date with a 190-day
  staleness tolerance. `attach()` **refuses** rather than reports if any row is
  joined inside the 45-day statutory window. Measured minimum lag after quarter
  end across 441,278 rows: exactly 45 days.
- **Analyst bias** is the expanding mean of the errors of targets that had
  already RESOLVED (`anndats + 365d`) before the month opened; a target is live
  only from the month AFTER its announcement. Using an unresolved target's error
  would be target leakage wearing a per-analyst hat.
- **Every cross-sectional standardisation is within-month.** A full-sample z
  would not be PIT.

Match rates: holder 92.4%, analyst 96.8%. Both broken out by year in the
receipt — the holder join dips to 0.655 in 2014 (vintage staleness) and the
analyst join to 0.897 in 2024 (the grades panel ends at `anndats` 2023-12 by
construction, since a 12-month outcome must exist to grade).

## Status

`FAILED_VARIANT` — not `MECHANISM_REJECTED`. What closed is *these* 41 features
against *this* base under a ridge and a LightGBM. Ownership structure is not
refuted; the popularity-collinear encoding of it is. The two things worth
carrying forward are the **tail-shaped** adverse stake effect and
`x_holder_anom_x_thincov`, neither of which is a reason to add a feature today.
