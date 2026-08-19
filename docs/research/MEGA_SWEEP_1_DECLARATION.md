# MEGA-SWEEP-1 — declaration (frozen BEFORE any book runs)

Declared 2026-08-19 ~21:10 HKT under Murat's overnight order ("run a
mega test to learn with backtests"). This document freezes the
enumeration so m is honest. Nothing in this sweep decides anything:
every output is SCREEN (BH-FDR 0.10, m = the full grid below);
survivors become candidate REGISTRATIONS with their own §64 audits.

## Substrate

CRSP PIT daily panel 2013–2024 (delistings charged), PIT-eligible
universe at formation, finratio monthly ratios joined on
`public_date <= formation` (never datadate), flat 3bp one-way declared
cost. Window 2014-06-30 .. 2024-11-30.

## Grammar (the full m)

- **Signals (7):** mom_12_1 · mom_63 (3m momentum) · rev_21 (short-term
  reversal: buy last month's losers) · low_vol (lowest vol_63) ·
  value_bm (finratio `bm`, high) · quality_roe (finratio `roe`, high) ·
  streak_7_avoid (exclude names mid up-streak ≥7 — tonight's reversal
  lean, deliberately included so the sweep can embarrass it)
- **Weightings (3):** equal · inverse_vol · rank
- **Winner handling (2):** trim · exempt
- **Top-N (2):** 50 · 100

m = 7 × 3 × 2 × 2 = **84 books**, plus 1 baseline book per
winner-handling (equal-weight ALL eligible, no signal) = 86 runs.

## The screen statistic

Per book: paired monthly net-return difference vs the baseline book
with the same winner-handling; date-block bootstrap
(`bootstrap_block_dates(dates, 21)`); two-sided normal-approx p.
BH-FDR 0.10 across the 84 hypotheses. Risk panel (vol, maxDD,
turnover, cost drag) reported for every book regardless of p — §59:
the risk column is the readable one.

## May NOT

- Promote any cell (§37) — survivors get their own preregs with
  mean-masked §64 audits on FRESH formulations, and the G2 preregs
  already drafted are NOT re-specified by tonight's output.
- Quote any book's return as a track record (SIMULATION label carried
  on every receipt).
- Add cells after this commit. A missing cell (e.g. a signal whose
  inputs refuse) is REPORTED missing, never silently re-specified.

— frozen pre-run; the sweep script cites this document's grid verbatim
