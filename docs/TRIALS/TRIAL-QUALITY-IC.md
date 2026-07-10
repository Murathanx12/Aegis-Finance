# TRIAL-QUALITY-IC — gross profitability as a forward IC trial

> Pre-registered 2026-07-09, before any forward data accrued (collector ships
> with this doc; first snapshot on the next deploy's daily check). Git
> timestamp = tamper evidence. This fills the quality slot T8 deferred when
> edgartools hung — via the hang-safe yfinance path.

## Hypothesis

Cross-sectionally, higher gross profitability (GP/A = Gross Profit / Total
Assets, Novy-Marx 2013) predicts higher forward returns over 63/126 trading
days within the tracked universe. Basis: quality/profitability is among the
factors the JKP replication study confirms out-of-sample
(docs/research/ENGINE_GAPS_2026_07_09.md finding 1); the standing US
post-publication-decay prior applies (finding 2).

**Honest prior:** moderate; quality is a slow factor — the 21d horizon is
reported but NOT primary (too short for a fundamentals signal).

## Signal definition (frozen)

`backend/services/quality_signal.py::compute_quality_score` — the score IS
GP/A from the most recent annual statements, alone. The Piotroski-subset
checks (ROA>0, CFO>0, CFO>NI, gross margin improving) are payload diagnostics
only — zero tunable weights. Missing fundamentals → explicit status, score 0.

## Decision rule

- **Primary metric:** forward rank-IC (Spearman) of `quality_score:{ticker}`
  PIT snapshots vs realized forward returns at **63 and 126 trading days**,
  bootstrap CI, via the `forward_ic` scorecard; all-zero periods excluded.
- **Secondary (reported, never deciding):** 21td IC; IC of the Piotroski
  n_checks_passed diagnostic; rank correlation with the momentum and revisions
  scores.
- **Adoption threshold:** IC > 0 with CI excluding 0 at BOTH primary horizons
  on a matured forward window → candidacy via `evaluate_candidate` (DSR/PBO
  deflated against the cumulative count).
- **Reject/park:** CI straddles 0 after ≥ 39 weeks of matured snapshots
  (quality needs the longer runway) → NEGATIVE_RESULTS.
- **Hard constraints:** descriptive-only; never arms a lane; no buy/sell
  language; NOT added to the in-flight TRIAL-MULTIFACTOR composite — a v2
  composite including quality would be its own pre-registered trial.

## What this rule may NOT do

No switching the score to a different quality definition (ROE, margins,
composite) after data accrues; no weight introduction; no horizon
cherry-picking. Annotations yes, rule changes no.
