# PREREG — RISK-HEAD-AT-SCALE-1 (frozen before any early-era model IC
# existed)

SIGNED-BY: Murat Abdullaev — recorded overnight order 2026-08-19
("don't wait, do the tests overnight till 8am"), recorded by the
working session.

**Status: SIGNED under the recorded blanket. Gate: `assert_signed` +
the mean-masked §64 audit below on disk before any verdict.**

## Provenance honesty

The 1990–2012 panel was loaded tonight for BOOK and STREAK
computations (OUT-OF-ERA-CONFIRM-1). No model has been trained and no
IC computed on it — the MODEL-ORDERING question this trial asks is
untouched there. Declared before any such computation ran.

## Question

The modern-era screen (UNIVERSE-SURVIVAL-STRESS-1, 2017–2024) found
LGBM 0.747 > ridge 0.680 on 21-day-forward volatility IC — a flip of
the 182-name tournament's risk-head ordering. Does that ordering hold
on 1994–2012 walk-forward, same frozen features and hyperparameters?

## Primary (ONE deciding cell)

- Per-date Spearman IC of 21d-forward vol predictions, walk-forward
  (train 1990..y−1, test year y, y ∈ 1994..2012), monthly formation.
- Deciding number: paired per-date IC difference **LGBM − ridge**;
  date-block bootstrap, block from `bootstrap_block_dates(dates, 21)`.
- Declared direction: POSITIVE (LGBM wins). Economic bar: 0.01 IC
  (the tournament's registered bar). Three-way verdict:
  LGBM_WINS / RIDGE_NONINFERIOR (one-sided: LGBM's edge bounded below
  the bar) / NOT_ESTABLISHED. §64 mean-masked audit first; limbs
  declared answerable or not at that point.

## SCREEN (reported, never deciding)

MLP vs both; RETURN-target ICs for all arms (the modern era was
anti-momentum — whether ridge's return IC turns positive in the
90s-era is hypothesis-generating only); yearly IC paths.

## May NOT

Tune anything (hyperparams are the tournament's, verbatim); promote a
screen cell; feed any lane. §61 cap. Verdict sentences carry the
nominal-screen drift note.

— frozen 2026-08-19 night, pre-computation on the declared slice
