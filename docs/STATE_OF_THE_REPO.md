# State of the Repo — Verified Inventory (2026-06-15)

> **V3 build sprint 2026-06-20 (commits `069bec6`..`1e92ef9`, on `main`, NOT pushed):**
> Chunk 1 foundation (alphalens+quantstats installed/pinned). Chunk 2 crash-model
> artifact FIXED (M3): provenance sidecar + fail-loud feature-hash guard + replay
> 67-vs-30 fix; model loadable but DARK (no discrimination — follow-up). Chunk 3
> `services/data_integrity.py` (directional vs sizing grade; survivorship probe;
> proven vs live yfinance 0/5 delisted). Chunk 4 `portfolio_intelligence/forward_ic.py`
> (reads T8/T9/T10 PIT snapshots back, grades via factor_ic; ReplayResult now stamped
> `data_grade`). Chunk 5 `fragility.exposure_multiplier` (continuous, descriptive, never
> arms). Chunk 6 `portfolio_intelligence/cross_asset_rotation.py` (pure rotator core,
> inverse-vol + fragility tilt, no hindsight; NEW lane seed DEFERRED/attended).
> Decisions: data source stays FREE (directional-only); ranker is a forward-IC slice
> NOT a backtest-to-adopt (postmortem 2026-06-15 survivorship trap). Targeted tests
> green (forward_ic 7, data_integrity 13, exposure 10, rotation 10, crash provenance 3).
> See docs/V3_RESEARCH_SYNTHESIS_2026_06_20.md + docs/DATA_INTEGRITY.md.


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
1. **🟢 crash_model.pkl ARTIFACT FIXED 2026-06-20** (BACKLOG M3) — root cause was
   two bugs: (a) `replay.py` passed the full 67-col as-of matrix as
   `external_features` into a 30-feature model → "67 != 30"; (b) the loader
   swallowed load failures with no provenance (the prod `model_not_deployed`).
   Fixes: retrained on the current pipeline (selects 20 features), added
   `crash_model.meta.json` provenance sidecar (train date, sklearn/lgb/numpy/joblib
   versions, feature count + **ordered feature-hash** + file sha256), load-time
   verification that **fails loud on feature-hash mismatch** (refuses to mark
   trained → overlay stays safely dark), a clear width-error in `_blend_scores`,
   and the replay pre-selects `feature_names`. Live overlay path now returns
   `status=evaluated` (was `model_not_deployed`); both consumers run end-to-end.
   ⚠️ **CAVEAT — model still DARK, do NOT arm:** trained on sparse crash events →
   val AUC=nan and the calibrator is degenerate (outputs ~0.066 across 2008/2022/2024
   alike — no regime discrimination). The artifact is now a sound *precondition* for
   arming, NOT an armable signal. Arming needs a discriminating model on a
   pre-registered lane (TRIAL-001). See follow-up: crash-model discrimination.
2. ✅ **Book lanes SEEDED 2026-06-16** — registry 3→5, mirror+conviction at today's
   live MV weights under book hash `d0d0eaf…`; the 4 reference lanes intact (config
   `628456e…`, inceptions 06-08/06-10, no spurious segment — TRIAL-001 held);
   `all_fresh: True`. **Plan-3 active mgmt** wired into `_daily_check` (runs the
   mirror cadence + conviction decisions nightly). **Visibility fix 2026-06-16:**
   seeded book lanes were marked-to-market + on `/api/health/full` but INVISIBLE on
   `/api/pi/track-record` (hardcoded to `REFERENCE_LANES`) → fixed to include seeded
   book lanes. Remaining gaps (deliberate, documented): `/api/pi/compare` and the
   per-lane `/reference/{id}/*` endpoints still reference-only (book lanes are a
   different shape — needs a separate decision, not a silent union).
3. **Optimus brain re-ingest** (Plan 4a) — corpus stale at `9c2a0e5`.
4. **Factor grades** not Alphalens-validated (`FACTOR_VALIDATION.md` partial).
5. **Per-stock news-as-measured-flag** (Goal 5) — not built.
6. **except-Exception swallower audit** (~70 sites, BACKLOG H5); dep lockfile (H2);
   13F-collector scheduling; secondary-market + non-EDGAR PIT collectors.

## Anti-goals (unchanged)
No real-money execution · no RL on P&L · no backtest "experience" feeding the
accounts · no skill claims before 24 months · no Bloomberg-parity push · OpenBB
(AGPL) never enters this MIT repo.
