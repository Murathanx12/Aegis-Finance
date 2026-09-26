# ANALYST-SKILL-1: verdict (2026-09-26)

**Registered rule (§3): `ADOPT`.** ΔIC = **+0.00084**, paired t (NW-3) = **2.52**, 71 months.
**What the evidence says: the weighting mostly DAMPS the consensus rather than adding
information.** The effect is **1/12 of the declared 0.010**, the prereg's own §6 calls
the declared size "the adopt bar ... an effect worth building", and the ΔIC comes from
shrinking a consensus that is an anti-signal (mean IC −0.068). **Recommendation: do not
fund weeks of provenance engineering on this result.** Record it as *detectable, below
the worth-building bar, mechanism = attenuation*. The rule's word stays ADOPT. It is
not re-labelled.

Licence: PRODUCT_EXPERIMENT (the prereg's own). Nothing trades from this.

## Instrument: the registered one

The chunk brief allowed a yfinance fallback (`INSTRUMENT_DIFFERS`). It was not
needed. `tr_ibes.ptgdetu` is on disk as WRDS bulk parquet
(`backend/data/optimus/wrds/bulk/tr_ibes__ptgdetu.parquet`, 7,427,025 rows). CRSP
daily (`crsp_dsf_2012..2024`) and `crsp__dsedelist` (Shumway-filled) are on disk too.
This is the registered instrument.

- Prereg `C:\Users\mrthn\Aegis module\TRIALS\PREREG_ANALYST_SKILL_1.md`, sha256[:16]
  `3e8a6e04b0590e7c`. `lint_prereg.py` result: **PASS** (vs 357 prior experiments).
- Reproduce: `python -m scripts.analyst_skill_1 --run` (~1 min). It ran twice and
  gave identical numbers.
- Receipt: `backend/data/optimus/analyst/analyst_skill_1_receipt.json`. Monthly
  series: `analyst_skill_1_monthly.csv`. Broker table: `broker_skill.parquet`
  (local; parquet is gitignored).

## Data census

| | |
|---|---|
| targets (US firm, 12m horizon, USD, linked to permno by lowest-score `ibcrsphist`) | 1,032,849 (anndats 2012-06 → 2024-12) |
| estimation-window targets graded (2013–2018) | 467,221 of 476,318 |
| brokers with a measured skill | 364; grand-median skill −0.2131 (median \|log error\| 21%) |
| broker skill persistence, 2013–15 vs 2016–18 (≥20 targets each half, 141 brokers) | Spearman **0.763** |
| evaluation panel rows (month × name × broker) | 1,389,034; 332 brokers; 97.8% of rows from a measured broker |
| names per month (≥2 brokers) | 2,447 – 2,962 (mean 2,656) |
| contamination clause (cfacpr change between anndats and the cut) | 5,511 targets excluded from both arms |
| evaluable months | **71 of 72**. 2024-12 is MISSING: its forward month needs January 2025 CRSP, which is not on disk. It was not filled. |

## POWER gate (run first, as registered)

| | realised | assumed |
|---|---|---|
| sd(monthly ΔIC) | **0.00254** | 0.020 |
| NW-3 SE of mean ΔIC | 0.000334 | — |
| MDE = 2 × NW-3 SE | **0.00067** | (declared effect 0.010) |

**PASSED.** The paired difference is about 8× less dispersed than the prereg assumed,
so the design resolves effects far below its own declared size. That is the reason a
1/12-size effect can clear t = 2.

## By year and by size (printed before the t, per protocol 11)

| year | months | mean ΔIC | IC equal-wt | IC skill-wt | months ΔIC > 0 |
|---|---|---|---|---|---|
| 2019 | 12 | +0.00130 | −0.0461 | −0.0448 | 83% |
| 2020 | 12 | **−0.00123** | +0.0038 | +0.0025 | 33% |
| 2021 | 12 | +0.00156 | −0.0676 | −0.0660 | 67% |
| 2022 | 12 | +0.00099 | −0.1472 | −0.1462 | 83% |
| 2023 | 12 | +0.00162 | −0.0603 | −0.0586 | 83% |
| 2024 | 11 | +0.00080 | −0.0916 | −0.0908 | 64% |

Leave-one-year-out mean ΔIC ranges from +0.00068 to +0.00126. No single year carries
it. The only year the consensus IC was positive (2020) is the only year ΔIC is
negative.

| size (CRSP cap at the cut) | mean ΔIC | t NW-3 | names/month |
|---|---|---|---|
| small (< $2B) | +0.00057 | 1.63 | 1,393 |
| large/mid (≥ $2B) | +0.00084 | 2.10 | 1,264 |

**Primary:** mean ΔIC **+0.000841**, t_NW3 **2.52**. Mean IC equal-weighted −0.0678;
skill-weighted −0.0670. **§3 → ADOPT.**

## Why the ADOPT is not what it looks like (report-only; the verdict does not move)

Both arms rank names by consensus **upside**, and upside is an **anti-signal** here:
the mean monthly IC is −0.068, and −0.147 in 2022. This matches the standing closure
of `analyst_target_upside_xs` as PERVERSE. A positive ΔIC therefore means the
skill-weighted consensus is *slightly less wrong*. Regressing monthly ΔIC on the
equal-weighted IC separates damping from information
(`report_only.attenuation_diagnostic`):

| | |
|---|---|
| corr(ΔIC, IC_ew) | **−0.46** |
| slope of ΔIC on IC_ew | −0.0072, **t −4.98** |
| intercept: ΔIC in a month where the consensus carries nothing | **+0.00035, t 1.09** |
| months with IC_ew > 0 (21) → mean ΔIC | **−0.00089** (skill weighting HURTS when the consensus works) |
| months with IC_ew ≤ 0 (50) → mean ΔIC | +0.00157 |
| months where \|IC_sw\| < \|IC_ew\| | 70% |

Skill weighting moves weight toward accurate brokers, mostly the bulge brackets
(GOLDMAN, JPMORGAN, LAWRENCE, FRCLAYSC, RBCDOMIN at weight ~1.3). The measured
effect is that the skill-weighted IC sits closer to zero than the equal-weighted IC
in 70% of months. That helps when the consensus is perverse and hurts when it
works. *Why* it happens (for example, accurate brokers issuing less extreme targets)
is a hypothesis; it was not measured. The part not explained by
damping, the intercept, is +0.00035 with t 1.09, which is indistinguishable from
zero.

### Other report-only rows (never deciding)

- **Design leak, measured.** The frozen estimation window's 12-month outcomes run
  into 2019 and overlap the first evaluation year. Re-estimating skill only from
  targets resolved before 2019 (anndats ≤ 2017-12-31) gives ΔIC **+0.00077,
  t 2.35**, with the same year pattern. The leak is not what produced the result.
- **Analyst level (`amaskcd`).** ΔIC +0.00035, t 1.32. That would be REJECT had it
  been the deciding level, which it is not.
- **Target-accuracy skill vs. recommendation reliability.** Spearman **0.37** across
  169 brokers (actor corpus, `pit_features.firm_reliability` at 2019-01-01, ≥20
  claims each). The two skill notions agree moderately.

## What this decides, and what it does not

- The prereg's §3 word is **ADOPT**, recorded as such. Per §5, no "top analyst" or
  "star broker" surface ships, and any skill column enters only as a labelled
  descriptive feature.
- The recommendation is **not** to fund the provenance branch on this evidence. The
  effect is 8% of the declared worth-building size, and it is attenuation of an
  anti-signal, not added ranking information. A successor trial, ANALYST-SKILL-2
  (counted against the family), would have to test skill-weighting on a consensus
  object with a **positive** base IC, such as revision flow rather than upside
  level. Otherwise damping and information cannot be told apart. That is a design
  note, not a registration.
- Chunk C's library rules that this informs: `ibes_skill_net_raises`,
  `first_mover_leadership`, `skilled_leader` (`strategy_library_ext`). They weight
  revision FLOW by recommendation reliability, not target upside by target accuracy,
  so this verdict neither validates nor closes them. They go to the factory like any
  other rule.
- Not added to `NEGATIVE_RESULTS.md`: the registered verdict is not REJECT, and that
  file is outside this chunk's ownership.
