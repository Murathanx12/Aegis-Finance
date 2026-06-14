# State of the Repo — Verified Inventory (2026-06-15)

Snapshot from live verified state (Optimus `aegis_verified_state` + registry) and
the working tree. Purpose: stop a fresh session from re-discovering what exists or
rebuilding what's done. **Supersedes the 2026-06-06 version, whose "gaps" are all
now shipped.**

## Deploy + track record (live)
- **Deploy:** `main` auto-deploys to Railway. Live commit `1c91fa0` (v0.2.0).
- **Forward track record:** live `paper_nav` since **2026-06-08** — 4 reference
  lanes (conservative / balanced(HRP) / aggressive / balanced-ew-control), marked
  daily, `nav.all_fresh` true. **~5 trading days old — no skill claims before
  24 months (canon).** This is the only real performance record; replay/compare
  are methodology backtests, not the track record (`TRACK_RECORD_POLICY.md`).
- **Registry:** 3 trials (TRIAL-001 HRP-vs-EW, TRIAL-LPPLS, TRIAL-CRASH), 0 rejected.

## What is REAL and built — do NOT rebuild
- **Overfitting guards (was the #1 gap — now DONE):** PSR/DSR, PBO via CSCV,
  Harvey-Liu t≥3.0, **effective-N** (participation ratio, reported-not-gating) —
  wired into the adoption gate; candidate that passes → human review, not
  auto-adopt. `engine/validation/overfitting.py`, registry `evaluate_candidate`.
- **Portfolio Intelligence — DEPLOYED + forward.** Reference lanes, walk-forward
  replay (look-ahead-safe), comparator vs SPY/AGG/60-40, real-portfolio FF5
  analyzer, decision journal, guarded evolution loop. `services/portfolio_intelligence/`.
- **Optimus MCP — BUILT + in use** (`C:\Users\mrthn\optimus`): `aegis_verified_state`,
  `aegis_canon`, `aegis_registry`, `aegis_postmortems`, `brain_query`. `/go` Phase 0
  loads from it. **Caveat: the brain corpus is STALE — frozen at git `9c2a0e5`,
  18 pages; recent postmortems not ingested (Plan 4 re-ingest pending).**
- **Fragility composite (descriptive):** LPPLS + SOS + Sahm + turbulence +
  absorption + net-liquidity + HY/IG OAS, equal-weight, lead/lag-labelled, never
  arms a lane. TRIAL-CRASH pre-registered. `fragility.py`.
- **Crash-Brier honesty:** `brier_with_ci` block-bootstrap CI + event count.
- **PIT data layer (V3 foundation):** `pit_observations` (schema v7), leak-free
  reads; EDGAR 13F collector (built, **not scheduled**); `data/book_lanes.yaml`.
- **Book lanes (P1 #6):** mirror + conviction built; seeding **env-gated**
  (`AEGIS_SEED_BOOK_LANES=1`); active management (`book_management.py`) built but
  **dormant** (not scheduler-wired). See `P1-6-LANE-FRAMEWORK-PLAN.md`.
- Plus the long tail (fundamentals/EDGAR, factor grades+model, insider, earnings,
  valuation, screener, provider registry, options/IV, technicals, etc. — see
  `CAPABILITY_MATRIX.md` for validated-vs-descriptive).

## Real OPEN items (the actual work)
1. **🔴 crash_model.pkl is BROKEN** — feature mismatch (pipeline now builds 67
   features, model trained on 30) → `predict` raises; this is why the overlay is
   `model_not_deployed` and the replay falls back to a crash-prob stub. Needs
   **retrain + metadata sidecar** (BACKLOG M3). Confirmed live 2026-06-15.
2. **Book-lane seeding** not run (Murat flips the env flag) + **Plan-3 activation**
   (wire `run_all_book_management` into the daily check — the final go).
3. **Optimus brain re-ingest** (Plan 4a) — corpus stale at `9c2a0e5`.
4. **Factor grades** not Alphalens-validated (`FACTOR_VALIDATION.md` partial).
5. **Per-stock news-as-measured-flag** (Goal 5) — not built.
6. **except-Exception swallower audit** (~70 sites, BACKLOG H5); dep lockfile (H2);
   13F-collector scheduling; secondary-market + non-EDGAR PIT collectors.

## Anti-goals (unchanged)
No real-money execution · no RL on P&L · no backtest "experience" feeding the
accounts · no skill claims before 24 months · no Bloomberg-parity push · OpenBB
(AGPL) never enters this MIT repo.
