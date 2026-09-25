# Spec — chunk 2 — the expected-return layer (`backend/services/expected_return.py`)

From `ROADMAP_2026-09-25_CHUNKS_AND_THE_REVIEW_LOOP.md` §2 row 2, adjudication
rows 2 and 5 (`docs/reviews/ADJUDICATION_2026-09-25_CHUNK0.md`), and the
research note `research_signal_fusion_and_timeline_panel.md` Part A. Written
2026-09-25 evening so the builder starts the moment chunk 1 (PROBE) lands.

## What it must do
For every candidate name on a date and a horizon h ∈ {5, 21, 63}, one number
`E[r_h]` (expected relative return vs the universe median), **decomposed by
component**, with weights that come from forward grades and an equal-weight
blend printed beside it as the standing control (the forecast-combination
puzzle: estimated weights beat equal weights by little and lose when n is
small).

```
E[r_h] = Σ_c  w_{c,h} · x_{c,h}          (linear; Shapley is then exact: φ_c = w_c·(x_c − E[x_c]))
```

## Components (each a column; each may be ASLEEP on a given date — a sleeping component is excluded and the weights of the awake ones are renormalised; the receipt records `components_awake`)
| c | source | x_c (units: expected relative return at h, or a z-score mapped through its own calibration curve) | PIT rule |
|---|---|---|---|
| `ranker` | `xs_ranker.rank_asof` score → `top_k_backtest`'s calibration (rank decile → mean net relative return at h) | as `ranking.json` | bars ≤ date |
| `revision_flow` | `revision_flow.compute` (`net_raises`, `n_firms`, `median_target_change`) → the month-end rule's decile table from `revision_flow_sweep_<date>.json` | strictly `event_date < date` | |
| `investigator_dir` | `investigator:*` rows with **`observable == beats_benchmark`** only, at h; p → return via `forecast_reputation.calibration_curve` (decile → realised relative return) | rows `made_at ≤ date` | **magnitude arms (`abs_move_exceeds`) NEVER enter here** (adjudication row 2) |
| `investigator_mag` | `abs_move_exceeds` p → predicted |move| — used ONLY in sizing/vol scaling, not in E[r] | same | |
| `thesis_card` | `thesis_card:v1` rows (supports/neutral/against × confidence) → mapped through their own calibration once ≥30 graded; until then x=0 (asleep) with the p carried on the receipt | card `asof ≤ date` | |
| `catalyst` | days to the next dated event from the catalyst YAML and the cards' `upcoming_dates`; sign from the event kind (PDUFA: break-even p≈0.87 on the CRL tail, so x is NEGATIVE unless the card's p_approval exceeds it) | event date known before `date` | |
| `source_reliability` | per-actor weight from `forecast_reputation` and the IBES analyst reliability corpus (`actor_corpus/ibes_graded.parquet`) applied as a multiplier to `revision_flow` | | |
| `regime` | `market_sensor` state (SPY/VIX) → a scalar that scales every component's weight (not a name-level term) | | |

## Weights
- `w_{c,h}` = `forecast_reputation.weights(...)` over each component's OWN forward grade (its rows in the decision ledger / predictions ledger keyed `(component, observable=beats_benchmark, h)`), shrink `n/(n+k)`, **floor 0**, γ, normalised; refit in `u_grade`; a component with n < 30 graded outcomes is shrunk to the prior (equal weight × 0.5), not zeroed (research Part A).
- The receipt prints `weights_source: reputation|equal` and `oos_advantage_reputation_vs_equal` (rolling, held out by date) — if the reputation blend does not beat equal-weight out of sample, `u_plan` uses **equal**.

## Where it plugs in
- `u_plan` (after chunk 1): EXPLOIT names = top of `E[r_21]` where the blend's own forward grade is positive with ≥21 sessions; PROBE = the shortlist as chunk 1 built it; sizes scaled by `investigator_mag` and the regime scalar; the worst-case dollars line stays.
- Every decision-ledger row carries `er_by_component` (the φ_c vector), `weights`, `weights_source`, `components_awake`, `regime`, so `decision_autopsy` can print "which component was wrong" per row and per week.
- Leaderboard (adjudication row 5): from session 21, R² of each book's daily return on its `sector_etf` twin.

## Tests (write first)
1. A planted world where only `revision_flow` carries signal → after 60 graded dates its weight dominates; equal-weight is printed beside it; with n<30 everything is at the prior.
2. A magnitude-only arm with perfect |move| skill and zero direction skill gets **weight 0 in E[r]** and non-zero in sizing.
3. A sleeping component on a date is excluded and the awake weights renormalise to 1; the receipt lists it.
4. Shapley attribution sums to `E[r] − E[baseline]` exactly.
5. The PDUFA catalyst term is negative when p_approval < 0.87 and positive above.
6. `u_plan` with `E[r]` present and `weights_source=equal` still refuses EXPLOIT until the blend's own 21-session grade exists, and still places PROBE.

## Receipts
`backend/data/optimus/expected_return/er_<date>.json` (per name: E[r] by h, φ vector, awake set, weights, source) and a 10-line print in the plan receipt.

## Not in scope
No new data collectors. No LLM calls. No change to `xs_ranker.FEATURES`.
