# INTEGRITY_STATUS — the safety layer's own dashboard

**Updated:** 2026-06-20 (post integrity-fix session). One-page map of every
safety/integrity guard with its REAL state. The anti-silent-fragility check on the
safety layer itself: a guard that looks present but is bypassable is worse than no
guard.

State: **🟢 enforced** (no known bypass) · **🟡 conditional** (safe under a stated
condition) · **🔴 has-known-bypass**.

| Guard | State | Where | Real behavior / condition |
|---|---|---|---|
| **data_grade stamp** | 🟢 enforced | `ReplayResult`, `forward_ic`, `evaluate_candidate` verdict | Every backtest result AND the DSR/PBO verdict carry `data_grade` (default directional). **B2 closed this session** — the verdict was previously un-stamped. No graduation decision is gradeless. |
| **feature-hash guard** | 🟢 enforced | `crash_model.load_model` | Rejects a tampered feature contract (fatal). **F3 closed this session**: a missing OR unreadable sidecar now REFUSES to load (was a legacy fall-through bypass). Provenance is a hard precondition for arming. |
| **crash-model provenance sidecar** | 🟢 enforced | `crash_model.save/load` | sha256 + feature-hash + versions written on save; verified on load. sha drift / version drift = loud WARN (benign); feature-hash / missing / unreadable = REFUSE. |
| **`require_sizing_grade`** | 🟡 conditional | `data_integrity` | Fails loud on every registered directional path (exhaustive bypass tests). Condition: registry-only — a source registered sizing without a real adapter would pass; the **survivorship_probe is the mandatory second gate** (two-gate contract). `None` source → AttributeError (loud but ungraceful). → backlog B6. |
| **survivorship probe** | 🟢 enforced | `data_integrity.assert_survivorship_safe` | Empirically fails loud if a SIZING-registered source can't serve delisted names. Proven vs live yfinance (0/5). Minor: `len()` robustness on a malformed fetch → B10. |
| **lookahead — forward_ic** | 🟢 enforced | `forward_ic.build_signal_panel` | Factor read via `get_series_observable` (observed_at ≤ cutoff); forward return is the realized label, strictly after as_of. |
| **lookahead — fragility composite** | 🟢 enforced | `fragility.compute_fragility_index(as_of_ts=…)` | **Fixed this session**: as_of_ts slices every input ≤ as_of, so percentiles/values are leak-proof when backtested; live (None) unchanged. Caveat: the `net_liquidity` leg fetches its own live series and is NOT as-of bound — network-gated, absent in offline backtests (documented) → 🟡 for that one leg. |
| **lookahead — cross_asset_rotation** | 🟡 conditional | `cross_asset_rotation` | Pure function; leak-safety is a documented **caller-as-of contract** (the window must be sliced by whatever lane consumes it). No consumer exists yet, so no live risk. |
| **lookahead — replay** | 🟢 enforced | `MarketDataAtTimestamp` | As-of slicing is the sole defense; enforced for every check date. |
| **fail-loud / no silent-wrong** | 🟢 enforced | exposure_multiplier, forward_ic, rotation | NaN composite → unavailable (F1); all-NaN panel → insufficient_history (F2); degenerate returns → empty (not NaN/negative). All test-pinned. |
| **overfitting guard (DSR/PBO/eff-N)** | 🟢 enforced | `evaluate_candidate` | Deflates against CUMULATIVE trials; ship bar DSR≥0.95 AND PBO<0.5. **Limit (by design):** guards multiple-testing, NOT a biased universe — the data_grade stamp + survivorship gate cover the universe axis (postmortem lesson). |
| **overlay arming** | 🟢 enforced (dark) | scheduler / reference_engine | Crash overlay is `model_not_deployed`; the retrained model does not discriminate (AUC=nan) so it stays DARK. Arming requires a discriminating model on a pre-registered lane. |
| **LLM firewall** | 🟢 enforced | (architecture) | No LLM touches an allocation/sizing decision. |
| **descriptive-only (never-arm)** | 🟢 enforced | LPPLS, fragility composite, exposure_multiplier | All carry `arms_lane=False`; no code path to a trade. |

## Net state after this session
- **Three gaps CLOSED:** the sidecar-deletion bypass (F3 → 🟢), the un-stamped verdict
  (B2 → 🟢), and the composite lookahead (→ 🟢, with one network-gated leg noted).
- **Remaining 🟡 (conditional, documented, no live risk):** `require_sizing_grade`
  registry-only confidence (two-gate contract; B6), the cross-asset caller-as-of contract
  (no consumer yet), and the `net_liquidity` fragility leg (not as-of, network-gated).
- **No 🔴 known-bypass remains** in the safety layer.
- **Open hardening proposals** (not implemented; need sign-off): B1 (composite can still emit a
  NaN *composite* if an input normalizes to NaN — F1 hardened the consumer, the producer is
  next), B6 (require_sizing_grade None-handling + one-call two-gate enforcement), B10
  (probe robustness). See IMPROVEMENT_BACKLOG.md.
