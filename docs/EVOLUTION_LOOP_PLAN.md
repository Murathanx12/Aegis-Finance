# Guarded Rule-Evolution Loop — Design & Build Plan

> **Decision (2026-06-14, Murat):** stand up the guarded rule-evolution loop
> (V2_GOALS Goal 2 / go.md P1 #10) as the honest form of "run paper accounts
> since 2000 and learn." Backtests propose **rules**, never feed the LLM;
> leakage-safe to what free point-in-time data honestly supports.

## The firewall (non-negotiable, from V2_GOALS A2 + verified research)

- Backtests may inform **rules only**, via this guarded loop, on **as-of** data.
- Backtest P&L / "experience" **never** feeds the LLM conviction lane or Optimus
  decision-making. Optimus ingests **process** (postmortems, adopted/rejected
  trials, rationale) — not returns. (Profit-mirage: ~37% leakage, p=0.033.)
- No rule is adopted on a backtest win alone — only if it survives **DSR/PBO
  deflated against the cumulative trial count** (incl. T2 effective-N).
- "Beats SPY on a backtest" is worth ~nothing (overfitting + survivorship). The
  moat is the **forward** record. The loop's success metric is *not* a high
  backtest Sharpe — it is: **≥1 adopted improvement holds up FORWARD, and
  rejected trials far outnumber adopted ones.**

## What already exists (reuse — do NOT rebuild)

| Piece | Location | Status |
|---|---|---|
| Acceptance: DSR/PBO deflated vs cumulative trials | `experiment_registry.evaluate_candidate` / `record_trial` | ✅ complete (T2) |
| Effective-N (reported) | `experiment_registry.effective_independent_trials` | ✅ complete (T2) |
| Overfitting math | `engine/validation/overfitting.py` (DSR, expected_max_sharpe, PBO/CSCV, CPCV) | ✅ |
| Purged CV + embargo | `engine/validation/purged_cv.py` (`PurgedKFold`) | ✅ |
| **Leakage-safe replay** (as-of prices, as-of crash prob, equity curve, Sharpe) | `replay.ReplayEngine.run(lane_id, start, end, ...)` | ✅ — **but reads lane config from YAML; no candidate override** |
| Leakage-safe weights (caller owns as-of bound) | `rules.compute_target_weights` | ✅ |
| Rule params (all tunable, SHA-versioned) | `paper_portfolios.yaml` (drift, frequency, optimizer, lookback, crash thresholds, sleeve %, caps) | ✅ |
| 3-file autoresearch contract (ML model, not lane rules) | `engine/autoresearch/aegis_{prepare,train}.py` | ✅ but separate (ratchet, not statistical gate) |

## What's missing (build)

1. **Candidate-override hook** on `ReplayEngine.run()` — accept a `lane_config_override: dict | None` so a candidate (current config with one param changed) can be backtested without mutating YAML.
2. **Orchestrator** `rule_evolution.py` — propose → backtest grid (leakage-safe replay) → compute cross-candidate Sharpe variance → `evaluate_candidate` (deflate vs cumulative trials) → `record_trial` (adopt/reject) → optionally emit a config-version bump for an adopted change (the existing `apply_config_change_rebalances` segment-boundary machinery).
3. **Honest universe scoping** (the survivorship gap): phase the loop by what's backtestable leakage-free.

## Leakage / survivorship scoping (the honest constraint Murat accepted)

- **Phase A — survivorship-safe NOW (since ~2001):** evolve params over a **broad-ETF + macro** universe (SPY/QQQ/sector ETFs/AGG that survived and are clean proxies) + FRED. Backtestable params: `rebalance_trigger_drift`, `rebalance_frequency`, `optimizer_params.lookback_days`/`min_observations`, `crash_overlay.crash_prob_threshold`/`equity_cut_pct`, sleeve %. **No individual-stock universe** (using today's tickers back to 2001 = survivorship).
- **Phase B — needs as-of data (later):** individual-stock & smart-money lanes require **as-of S&P constituents + delisted-ticker prices** and **SEC EDGAR 13F/Form-4 with filing timestamps** (free, back to ~2001 — the gold). Insider *opportunistic* (~82 bps/mo) and long-horizon 13F value cloning are the durable edges; lagged 13F cloning / routine insider are not (verified research). These enter as pre-registered lanes/features only after the as-of data layer exists.
- News/sentiment (GDELT): ~2015+ only → risk-off gate (Goal 5), never backtested as alpha pre-2015.

## Build chunks (one per session; plan-first each)

- **Chunk 1 — single-param loop, end-to-end.** Add `lane_config_override` to `ReplayEngine.run()`. New `rule_evolution.evolve_param(lane_id, param, value_grid, start, end, dry_run=True)`: backtest each grid value (leakage-safe), compute `sr_variance` across the grid, `evaluate_candidate(best_returns, sr_variance, batch_trials=len(grid))`, `record_trial` (unless dry-run). Returns a summary. Tests: override changes weights/returns; leakage guard (future rows can't move a past backtest); a deliberately-overfit grid gets REJECTED by deflation; dry-run records nothing. **Done-when:** one param evolved on real ETF+macro data since 2001, verdict recorded, rejected-by-deflation test green.
- **Chunk 2 — multi-param proposer + read-only surfacing.** A small candidate generator over the Phase-A param space; `/api/pi/registry` already shows trials; add an evolution-run summary surface. Loop runs a batch, records all trials (adopted + rejected). **Done-when:** a batch run records N trials with adopted ≪ rejected, all deflated vs cumulative count.
- **Chunk 3 — autonomous cadence + Optimus process ingestion.** Wire the batch into the existing `lab/` overnight cadence (or a scheduled job); write each run's outcome (what was proposed, why rejected/adopted) to the Optimus-ingestible postmortem corpus. **Done-when:** an overnight run proposes/tests/records autonomously; Optimus can answer "what rule changes were tried and rejected, and why."
- **Chunk 4 (Phase B) — as-of data layer.** As-of S&P constituents + delisted prices; SEC EDGAR 13F/Form-4 as-of parsers. Unlocks smart-money lanes/features as pre-registered trials. Largest; gated on data sourcing.

## Forward-truth guard (so adopted ≠ overfit)

An adopted rule is a **config-version bump** (new SHA segment) measured **forward** like any lane. The backtest only earns it a *trial*; the forward segment earns it *trust*. If forward disagrees with the backtest, the loop reverts it as the next config version (roll forward, never in place — see the Step-#2 postmortem rollback note).
