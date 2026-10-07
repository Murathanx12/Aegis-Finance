# CARD: markowitz-1952-portfolio-selection

## Index fields
- topic: Portfolio construction: mean-variance optimisation vs equal weight (1/N)
- mechanism_class: estimation_error, methodology
- dataset_status: DOCUMENTED_NOT_TRACKED

## Citation
Harry Markowitz (1952), "Portfolio Selection," *The Journal of Finance*, 7(1): 77-91.
DOI 10.1111/j.1540-6261.1952.tb01525.x. Verified by fetching
`https://econpapers.repec.org/RePEc:bla:jfinan:v:7:y:1952:i:1:p:77-91` (2026-10-07; title,
author, journal, volume 7, issue 1, pages 77-91 confirmed directly) and cross-checked against the
Wiley DOI listing surfaced independently in search (`onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1952.tb01525.x`,
403 on direct fetch but the citation agrees). Companion paper, same card: Victor DeMiguel, Lorenzo
Garlappi, Raman Uppal (2009), "Optimal Versus Naive Diversification: How Inefficient Is the 1/N
Portfolio Strategy?," *The Review of Financial Studies*, 22(5): 1915-1953, DOI 10.1093/rfs/hhm075.
Verified via the SSRN abstract page and independently corroborated by the LBS Research Online
repository and two ScirP reference records, all agreeing on journal/volume/pages/DOI
(2026-10-07; direct fetch of the SSRN page 403'd, search-tool fetch of its content returned the
same citation twice independently).

## The claim, in one sentence
Markowitz: a rational investor should choose portfolio weights that sit on the
mean-variance-efficient frontier (maximum expected return for a given variance, or minimum
variance for a given expected return), rather than diversifying by any other rule — **this is a
construction rule, not a return predictor**, and it makes no claim that any asset or factor
outperforms. DeMiguel-Garlappi-Uppal (2009): out-of-sample, naive equal-weighting (1/N) matches or
beats 14 optimized mean-variance variants (including Markowitz's own sample-based estimator) on
Sharpe ratio, certainty-equivalent return, and turnover, across most of the datasets tested,
because estimation error in the inputs (expected returns especially, but also the covariance
matrix) overwhelms the theoretical gain from optimizing.

## Mechanism: why the inefficiency could exist, and who is on the other side
Markowitz's own paper is not an inefficiency claim at all — it is a normative theory of how to
combine assets given their means, variances and covariances, built to formalize "don't put all your
eggs in one basket" into a quantitative rule. There is no counterparty to take the other side of a
construction *method*; the question that can be falsifiable is downstream: does estimating the
inputs **statistically** (sample mean/covariance) and optimizing on them outperform **not**
estimating them (equal weight) once you must use finite, noisy historical data? DeMiguel et al.'s
answer is a mechanism in its own right: **estimation error** in the sample mean (the hardest moment
to estimate precisely, requiring decades of data for many assets to pin down with useful precision)
propagates nonlinearly through the optimizer's matrix inversion, so a theoretically-optimal
portfolio computed on noisy inputs can be *less* efficient than a rule that uses no information at
all. The "other side" is not a trader exploiting Markowitz's followers; it is the optimizer's own
sensitivity to estimation noise acting against the optimizer's user.

## Assumptions
Markowitz: investors care only about mean and variance of portfolio return (not higher moments);
returns and covariances are known (or can be estimated); assets are infinitely divisible; no
transaction costs or taxes; a single period. DeMiguel-Garlappi-Uppal: these assumptions are tested
by RELAXING the "known" one — moments are estimated from a rolling historical window of finite
length (typically 60-120 months), and the comparison is which estimator (including 1/N, which
estimates nothing) is more robust to that estimation error, with transaction costs considered
separately as a sensitivity.

## Measurable variables: the precursor observable BEFORE the move
There is no "move" to predict here — Markowitz and 1/N-vs-optimization are about **weights**, not
**direction**. The analogous precursor for AEGIS's version of the question is: at each rebalance
date, what is the realized estimation error of the trailing sample covariance/mean matrix (e.g. the
condition number of the covariance matrix, or the number of assets N relative to the estimation
window length T — DeMiguel et al.'s own headline informal rule of thumb is that with momentsestimated
from about 10 years of monthly data, N needs to be in the 3,000+ range before a mean-variance
rule reliably beats 1/N)? That ratio is observable BEFORE any weight is chosen, which is exactly
why it is testable as a precursor to "does optimizing pay this month" rather than as a return
precursor in the usual Mission-rule-2 sense.

## Sample period and markets
Markowitz (1952): no empirical test — the paper is theoretical/normative, with a worked numerical
illustration, not a backtest. DeMiguel-Garlappi-Uppal (2009): seven empirical datasets of monthly
returns, varying by number of assets (N = 3 to 1,500+ via industry portfolios, international
indices, and individual-stock samples) and sample windows generally spanning multiple decades
through the mid-2000s (dataset-dependent; the paper's own appendix gives exact start/end dates per
dataset). Out-of-sample testing uses rolling-window re-estimation, not a single fixed split.

## Effect size as published
DeMiguel-Garlappi-Uppal: out-of-sample Sharpe ratio of 1/N is statistically indistinguishable from
(and in most datasets numerically higher than) 14 optimized strategies including sample-based
mean-variance, Bayesian shrinkage, and minimum-variance portfolios, net of the fact that 1/N's
turnover (and hence transaction costs) is also typically far lower. The paper does not report one
single "effect size" — its result is a cross-dataset ranking, with the main quoted finding being
that **none** of the 14 optimized models consistently beats 1/N by a statistically or economically
significant margin out-of-sample.

## Known failure modes and post-publication decay
This is not a "decaying anomaly" in the McLean-Pontiff/Harvey-Liu-Zhu sense (McLean & Pontiff 2016,
"Does Academic Research Destroy Stock Return Predictability?," *Journal of Finance* 71(1): 5-32,
DOI 10.1111/jofi.12365; Harvey, Liu & Zhu 2016, "...and the Cross-Section of Expected Returns,"
*Review of Financial Studies* 29(1): 5-68 — both cited here as the standing decay/multiplicity
references for this card family, not independently re-verified for this specific claim since
neither paper covers portfolio-construction rules) — there is no return premium to decay, because
the claim is about estimation robustness, not about an asset class or signal earning excess
return. The known failure mode is the opposite of decay: DeMiguel et al.'s own result is
**conditional on N and T** — as the number of assets available to estimate falls relative to the
window length (small N, long T), optimization's advantage over 1/N grows, so the "1/N wins"
result is itself regime-dependent on the N/T ratio, not a universal law. Later literature
(not independently verified this pass) on shrinkage estimators (Ledoit-Wolf) and robust/Bayesian
covariance estimation claims to narrow but not eliminate this gap.

## What AEGIS has on disk to test it
CRSP/Compustat daily and monthly bars across the full repo-wide panel (`backend/data/optimus/
aegis_panel/aegis_panel_v2.parquet`, 4,157,680 rows, 1926-01-30..2024-12-31, per
`docs/DATA_CATALOG.md`) give decades of monthly return history for however many names are chosen as
the comparison universe — directly sufficient to replicate DeMiguel et al.'s rolling-window
design on a US-equity sleeve. `backend/data/optimus/wrds/jkp_full/` and `jkp_global_factor_usa.parquet`
supply characteristic-sorted portfolios as an alternative, smaller-N universe (closer to the
original paper's industry-portfolio tests). `docs/TRIALS/TRIAL-001-hrp-vs-ew.md` is the directly
relevant existing machinery: a live, pre-registered forward comparison of Hierarchical Risk Parity
(a correlation-based, non-mean-variance alternative to both Markowitz and 1/N) against equal-weight
on the paper book's equity sleeve, decision window opening 2027-06-10. The "benchmark-core" work in
`docs/research_notes/2026-10-07/six_roles_and_benchmark_core_2026-10-07.md` (sizing a passive SPY
core against active sleeves under a worst-case gross constraint) is the live portfolio-construction
question this card's testable question feeds into.

## The falsifiable question and the declared primary metric, with costs
*Does a mean-variance-with-shrinkage portfolio (e.g. Ledoit-Wolf covariance shrinkage, or a
Bayesian-James-Stein mean shrinkage, applied to a rolling window on AEGIS's own equity universe)
produce a higher net Sharpe ratio than equal weight, out-of-sample, after the engine's realistic
cost model (flat-bps or Corwin-Schultz-based, per the house convention in `revision_tilt_2026-09-29.md`),
over a multi-year rolling-window test, on the SAME universe TRIAL-001 already uses for HRP-vs-EW?*
Primary metric: out-of-sample net Sharpe ratio, with turnover and the N/T ratio of the estimation
window reported alongside (since DeMiguel et al.'s own finding is that the answer depends on N
relative to T, this ratio must be printed, not buried, per CLAUDE.md protocol 11's "print by year /
print the regime before believing a positive").

## Whether a corpse already exists here
Not the same question, but the adjacent construction question (HRP vs equal-weight) is already a
LIVE, pre-registered trial: `docs/TRIALS/TRIAL-001-hrp-vs-ew.md`, decision window opens
2026-06-10 + 12 months, earliest decision 2027-06-10, primary metric full-window net Sharpe. No
existing trial or `NEGATIVE_RESULTS.md` entry was found this pass for mean-variance-with-shrinkage
specifically vs equal-weight on AEGIS's own data — this is a genuinely open, adjacent question to
TRIAL-001, not a duplicate of it (HRP is a correlation-clustering heuristic, not a mean-variance
optimization, so a "does shrinkage-MV beat EW" trial would be a third arm, not a resurrection).

## Needs evidence
- Post-DeMiguel-Garlappi-Uppal (2009) literature specifically on shrinkage-MV vs equal-weight
  (not HRP vs EW, already TRIAL-001's question) -- whether a more recent paper has already run
  the comparison this card proposes, on a comparable universe/cost model, before AEGIS re-derives
  it from zero.
- Whether any paper quantifies the TURNOVER cost crossover at which shrinkage-MV's lower
  variance stops paying for its higher turnover vs EW, which is the specific "net of costs"
  question this card's falsifiable question asks and DeMiguel et al.'s own abstract does not
  settle on its own.

## hyp_lab family
`family_unmapped` — none of the fixed `HYP_LAB_FAMILIES` (macro_readthrough_*, event_readthrough_*,
size_*, llm_*, investable_spread, risk_timing, data_vintage, insider_event, digest_forward,
vol_compression, official_disclosure, price_location, earnings_streak) describes a portfolio-
CONSTRUCTION-method comparison; all of them describe return-predicting SIGNALS. This card is a
structural gap in the taxonomy, not a mis-filed signal, and should be flagged to whoever next
revises `HYP_LAB_FAMILIES` rather than forced into a signal family it doesn't fit.

## Verdict
**NEEDS_DATA** (the specific comparison — shrinkage-MV vs equal-weight, net of costs, on AEGIS's
panel — has not been run; the data to run it already exists and no new pull is required, so the
"NEEDS_DATA" here is a build-and-run gap, not a missing-source gap). The adjacent HRP-vs-EW question
is already `READY_TO_CELL`-and-running as TRIAL-001; this card's question should be designed as a
sibling arm reusing TRIAL-001's construction, not a fresh pre-registration from zero.

## needs_evidence
- Does a mean-variance portfolio with shrinkage (Ledoit-Wolf covariance or James-Stein mean
  shrinkage) beat equal weight on out-of-sample net Sharpe after the engine's cost model, on the
  universe TRIAL-001 uses for HRP-vs-EW?
- How does that answer move with the N/T ratio of the estimation window on AEGIS's own panel,
  the ratio DeMiguel, Garlappi & Uppal (2009) say decides it?
- Does the shrinkage and robust-covariance literature (Ledoit-Wolf and successors), not verified
  this pass, actually narrow the 1/N gap out of sample?
