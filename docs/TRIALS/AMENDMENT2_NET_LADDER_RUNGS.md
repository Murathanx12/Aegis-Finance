# AMENDMENT 2 — NET ablation ladder: +options and +expectations rungs

Parent: `PREREG_AEGIS_NET_TOURNAMENT_1.md` ("rungs run only as their
PIT stores materialize, each as an amendment naming this document as
parent"). Stores materialized 2026-08-19 night: OptionMetrics 30-day
surfaces (12 years, opcrsphist-linked) and IBES consensus
(statsum_epsus, ibcrsphist-linked). Declared 2026-08-20 ~00:45 HKT,
BEFORE any rung feature was computed. SIGNED under Murat's recorded
overnight order ("don't wait, do the tests overnight till 8am").

## Basis (declared, with the §60 disclosure)

The rungs run on the **PIT monthly panel** (the
UNIVERSE-SURVIVAL-STRESS basis: ~2,000 eligible names/month,
delist-inclusive targets), NOT the parent's 182-name panel — the
universe stress showed the 182 selection distorts orderings, so the
honest ladder question is asked at scale. This is a declared basis
CHANGE relative to the parent's family-1 run and is disclosed on every
receipt; rung INCREMENTS (not absolute ICs) are the deliverable.

## Frozen rung features

- Rung 0 `numeric` (7): the stress test's FEATURES, verbatim.
- Rung 1 `+options` (3, from vsurfd 30d via opcrsphist validity):
  `opt_iv_atm` = mean IV at |delta|=50 across C/P, last obs ≤ t;
  `opt_skew` = IV(25Δ P) − IV(25Δ C), last obs ≤ t;
  `opt_pc50` = IV(50Δ P) − IV(50Δ C), last obs ≤ t.
  Staleness cap: obs must be within 10 trading days of t, else NaN.
- Rung 2 `+expectations` (3, from statsum fpi='1' via ibcrsphist):
  `exp_breadth` = (numup − numdown) / numest, latest statpers ≤ t;
  `exp_disp` = stdev / |meanest| (NaN when |meanest| < 0.01);
  `exp_chg` = (meanest_t − meanest_{t−1 statpers}) / |meanest_{t−1}|.
- Ladder = cumulative: numeric → numeric+options →
  numeric+options+expectations. Missing rung values stay NaN (LGBM
  native; ridge/MLP behind median impute as in the frozen arms).

## What is measured (all SCREEN, BH-FDR 0.10, m = cells run)

Arms ridge + LGBM (MLP dropped for the overnight run — declared, not
silent), targets fwd_ret + fwd_vol, walk-forward test 2017–2024.
Deliverable per (arm, target): the PAIRED per-date IC increment of
each rung over the previous rung, date-block bootstrap. A rung that
adds nothing prints as such; a rung that helps names WHICH information
class paid.

## May NOT

Tune arms; reorder rungs after results; treat any rung increment as a
verdict about the parent's primary (different basis — disclosed);
promote screen cells. §61 cap.

— frozen pre-computation

---

## RESULTS (run 2026-08-20 ~01:00, appended post-run)

Receipt `net_tournament/ladder_rungs_2026-08-20.json`. Coverage:
options features ~0.6-0.7 of panel rows, expectations ~0.8.

**BH-FDR survivors (m=8): the +options rung on BOTH vol arms.**
ridge vol +0.0735 dIC (p~0), LGBM vol +0.0402 (p~0) - best vol IC now
LGBM 0.787. +expectations adds ~nothing beyond options for vol
(+0.00005) and ns for returns. Return-ranking: NO rung helps (era
consistent with the anti-momentum finding). Honest caveat carried:
opt_iv_atm is itself a market vol forecast - the survivors mean the
risk head ABSORBS the options market's information, not that alpha was
found. Consequence drafted into the G2 risk lane notes: v2 model =
LGBM WITH the options rung, pending its own transport prereg.
