# Cycle 23 — Phase B: BUILD

## Hypothesis
Wiring the existing 3-state Gaussian HMM (backend/models/hmm.py) into all Monte Carlo
call sites will activate the dead hmm_drift_blend/hmm_vol_blend parameters, producing
regime-conditioned simulations with probabilistic drift/vol blending instead of the
current rule-based binary regime assignments.

## What Was Built

### 1. HMM-to-MC Bridge (regime_detector.py)
- Added `fit_hmm_for_mc(data)` function that calls `fit_hmm_regimes()` and returns
  MC-ready dict: `{state_means, state_vols, regime_probs, current_regime, success}`
- Added `_hmm_fallback()` for graceful degradation when HMM fitting fails
- No changes to existing `detect_regimes()` return type (backward compatible)

### 2. Wiring: SP500 Simulation (routers/simulation.py)
- Added HMM fitting in `_run_sp500_projection()` and `_compute_scenarios()`
- Passes `hmm_state_means`, `hmm_regime_probs`, `hmm_state_vols` to both
  `run_monte_carlo()` and `simulate_paths()`

### 3. Wiring: Per-Stock MC (routers/stock.py + services/stock_analyzer.py)
- Added `hmm_state_means/probs/vols` params to `analyze_stock()` signature
- Screener fits HMM once in `_compute_market_signal()`, passes to all per-stock MCs
- Single-stock and signal endpoints also receive HMM data

### 4. Wiring: Sector MC (routers/sector.py + services/sector_analyzer.py)
- Added HMM params to `analyze_sectors()` signature
- Sector router fits HMM and passes through to all 11 sector simulations

### 5. Bug Fix: drift_detector.py Reproducibility
- Replaced `np.random.uniform()` (legacy global RNG) with `self._rng.uniform()`
- Added `seed` parameter to `DriftDetector.__init__()`
- KS test results are now deterministic across identical inputs

### 6. Tests (12 new)
- `test_hmm_regime.py`:
  - TestHMMModelFitting (5 tests): fitting, prob sum, state ordering, fallback, transition matrix
  - TestFitHMMForMC (4 tests): keys, success, fallback, MC compatibility
  - TestDriftDetectorReproducibility (2 tests): determinism, drift detection
  - +1 test: None HMM inputs don't crash MC

## Files Modified (8)
1. `backend/services/regime_detector.py` — Added fit_hmm_for_mc(), _hmm_fallback()
2. `backend/routers/simulation.py` — HMM wiring for SP500 + scenarios
3. `backend/routers/stock.py` — HMM wiring for screener + single stock + signal
4. `backend/routers/sector.py` — HMM wiring for sector analysis
5. `backend/services/stock_analyzer.py` — Added HMM params to analyze_stock()
6. `backend/services/sector_analyzer.py` — Added HMM params to analyze_sectors()
7. `backend/services/drift_detector.py` — Fixed np.random reproducibility bug
8. `backend/tests/test_hmm_regime.py` — 12 new tests (NEW FILE)

## Test Results
- **227 passed**, 92 deselected (slow), 0 failed
- Previous: 215 passed → +12 new tests
- Total test functions: ~246 (14 files)

## Impact
- Every MC simulation in the system (SP500, per-stock, sector) now receives
  probabilistic regime information from a fitted 3-state Gaussian HMM
- The MC engine blends HMM drift/vol at 15% weight (config: hmm_drift_blend=0.15,
  hmm_vol_blend=0.15) — these were dead parameters before this cycle
- Graceful fallback: if HMM fitting fails, None values are passed and MC
  operates exactly as before (no regression risk)
