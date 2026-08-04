# Prompt — M1 completion (paste into a fresh Opus session)

> You are in the aegis-finance repo; the Strategy Factory and calibration
> package live in the sibling repo `C:\Users\mrthn\Aegis module` (venv:
> `.venv\Scripts\python.exe`). Read first, in order:
> `docs/GATE_M1_FACTORY_CALIBRATION_DESIGN.md` (the design, incl. §6 staged
> plan), `Aegis module/aegis_brain/calibration/panel_gen.py` (docstring =
> v1-v5 iteration history), `Aegis module/runs/GATE-M1/stage1_fidelity.json`
> (current state: F8 payoff-null PASS at v5; F1 pairwise-corr worst 22.9%
> vs 20% tol; F3 pooled kurtosis 939 vs real 494), and
> `docs/GATE_M_RESEARCH_VERDICTS_2026-08-04.md`.
>
> Standing decisions already made — do not relitigate:
> - Injected signal enters as the **21st candidate, always present at every
>   α including α=0 (k=0)** — 42 candidates per cell, CRN pairing exact.
>   Track **cap_crowded_out** as a terminal state in Table 2 (a true signal
>   out-ranked by five lucky nulls at the top-5 cap dies at the cap, not at
>   a statistical gate).
> - Registered descope: **n=250 per cell, ±6.2pp Wilson, stated on every
>   table** (Stage 0 measured ~10s/scan, loop-bound).
> - F8 gates on the **payoff null** (mean top-decile excess; kill >3 SE,
>   warn 2-3 SE); rank-IC is a reported diagnostic only.
> - β-defaulted diagnostic (already run): 319 defaults = 5.6% of small
>   tercile vs 2.3% large — real but too small to carry F1-small's 23%
>   error. Re-standardization is the primary fix candidate.
>
> Work items, in order, each with its kill criterion:
>
> 1. **Close F1/F3** with per-month cross-sectional re-standardization of z
>    (divide month-t z cross-section by its own sd, multiply by the real
>    month-t cross-sectional sd of z) — provably F8-neutral: a single
>    positive constant per month cannot change within-month ranks, and
>    E[c_t·excess_t] = c_t·0 = 0. Do NOT scale by contemporaneous rolling σ
>    (reintroduces the v4 conditioning channel). Rerun stage1_run: require
>    F1 ≤20%, F3 kurtosis ≤30% rel err, F8 still PASS. If re-standardization
>    alone can't close F3, report the residual gap and its direction — do
>    not add knobs beyond this without writing the rationale into the
>    module docstring first.
> 2. **Stage 2 — injection** (`calibration/inject.py`): AR(1) φ=0.9
>    characteristic X, S_observed = ρ·X + √(1−ρ²)·noise (ρ_sig 0.5
>    headline, {0.3, 1.0} sensitivity); Δr = k·2·(pct_rank(X)−0.5),
>    k = S_ann·σ̂/(0.9·√12) with σ̂ = 0.0097 (Stage 0). Injection is GROSS.
>    S2 gate: perfect-foresight book on X must realize target Sharpe ±20%
>    at every α, and (r_injected − r_null) nonzero for ≥99% of eligible
>    cells — a no-op injector must be impossible.
> 3. **Stage 3 — the grid** (`calibration/run_grid.py`): per rep, per α ∈
>    {0, 0.2, 0.4, 0.6} × designs I1-I4 (I2 decaying τ=60m is the headline):
>    scan_signal directly (NEVER run_batch — it swallows crashes into
>    months=0), 21 signals largemid + graduation rule (t_net≥1.5 AND
>    t_ic≥2.0, top-5 cap), confirm read, evaluate_candidate WITH the T×42
>    perf_matrix (pbo=None must raise), DSR at n_trials 42 AND 179. Every
>    rep writes seed + terminal state ∈ {no_graduate, cap_crowded_out,
>    confirm_fail, dsr_fail, pbo_fail, adopt}; counts must sum to n_reps or
>    the aggregation raises. CRN: same null panel per rep across α levels.
>    ProcessPoolExecutor across cores; overnight budget. Outputs Tables 1-2.
> 4. **Stage 4 — posterior map + exhibits** (`calibration/posterior.py`,
>    `exhibits.py`): likelihood over the evidence buckets, prior
>    π = {0: .85, .2: .09, .4: .045, .6: .015} + the two sensitivity priors;
>    ship `posterior_map.json` ONLY if the posterior is monotone in the
>    evidence ordering. Exhibits A (operating characteristics per gate
>    stage) and B (posterior heatmap with ladder bands).
> 5. If the grid lands early: **Stage 5** — inject a known event-day effect
>    and measure the M2 permutation placebo's own kill curve (spec:
>    verdicts doc §3, B=5,000, p=(1+#{perm≥real})/(B+1)).
>
> Constraints: production pipeline stays byte-unchanged
> (assert_production_constants runs at every entry point and must pass);
> seeded rng only (SEED_BASE + rep); no network in tests; every silent
> path raises. Commit to the Aegis module repo per stage with the stage's
> verdict in the message. Report at the end: fidelity table, S2 gate
> result, Tables 1-2 headline numbers (false-kill at α=0.4 is THE Gate M
> criterion — >~50% ⇒ recalibrate gates before any new family runs),
> cap_crowded_out share, and whether the posterior map shipped.
