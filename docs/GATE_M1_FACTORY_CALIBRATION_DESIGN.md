# GATE M1 — FACTORY CALIBRATION MONTE CARLO: IMPLEMENTATION DESIGN
**Date:** 2026-08-04 · **Status:** DESIGN ONLY — no code written yet
**Answers:** O1 brief · **Research basis:** `docs/GATE_M_RESEARCH_VERDICTS_2026-08-04.md` §1
**Gate criterion (from `AEGIS_EXECUTION_ROADMAP.md` M1):** false-kill rate at α=0.4 > ~50% → recalibrate gates before any new family runs.

---

## 0. TWO CORRECTIONS TO THE BRIEF'S PREMISE

The O1 brief locates the Strategy Factory in `engine/` and `lab/`, and puts config in `backend/config.py`. Both are wrong, and building against them would produce a design for code that does not exist.

**The factory lives in the `Aegis module` repo, not `aegis-finance`:**

| Component | Real location | Role in M1 |
|---|---|---|
| Explore scan (the gate that graduates) | `aegis_brain/factory/explore.py` — `scan_signal`, `ScanConfig` | Run **unchanged** |
| Walk-forward harness | `aegis_brain/harness/runner.py` — `run_walk_forward` | Run unchanged (fusion/model arms only) |
| Adoption gate (DSR + PBO) | `aegis_brain/gate/adoption.py` — `evaluate_candidate` | Run **unchanged** |
| DSR arithmetic | `aegis_brain/discipline/overfitting.py` | Run unchanged |
| Trial count | `aegis_brain/gate/registry.py` — `cumulative_trial_count` | Read, overridden explicitly per §3.3 |
| Panel type (**the only seam**) | `aegis_brain/data/eodhd_panel.py` — `Panel` | Substituted with synthetic instances |
| Certified real panel | `data/crsp_panel_2002/{monthly_ret,month_end_price,monthly_dollar_vol}.parquet` — 276 months, 11,098 permnos, 3,120 mean eligible names/mo | Calibration source + target |
| Frozen protocol | `docs/STRATEGY_FACTORY.md` | The rules M1 must reproduce byte-for-byte |

**Config therefore goes in `aegis_brain/calibration/config.py`,** not `backend/config.py` — `backend/` is the web API and has no bearing on the factory. Everything else in the O1 constraints (seeded `np.random.default_rng`, no network in tests, silent-failure paths must raise) applies unchanged.

**Second correction:** `crsp_msf_full.parquet` (certified 2026-08-04, 1963→) is the *wrong* source for the headline run. The 179 candidates were evaluated on `crsp_panel_2002`. Calibrating the pipeline on a different panel than the one it judged would answer a question we did not ask. `crsp_msf_full` is used only in Stage 6 (out-of-era realism check: does the calibration hold in 1963–2001?).

---

## 1. THE ARCHITECTURAL FACT THAT MAKES THIS CHEAP

`scan_signal(panel, sig, segment, cfg)` and `evaluate_candidate(returns, ...)` take a `Panel` dataclass and plain arrays. `Panel` is four fields:

```
monthly_ret          # months × symbols
month_end_price      # months × symbols   (drives eligibility floor)
monthly_dollar_vol   # months × symbols   (drives eligibility + segment)
delist_month         # dict symbol → last valid month
```

**A synthetic panel is just a `Panel`.** Nothing in the gate, the cost model, the hold band, the graduation rule, or the DSR arithmetic needs to know it is synthetic. There is no data loader to mock, no monkeypatching, no test double — the calibration harness constructs a `Panel` and calls production functions. This is the strongest possible version of "run the UNCHANGED pipeline."

---

## 2. THE SYNTHETIC PANEL GENERATOR

### 2.1 Requirements
A null panel must simultaneously:
- **(N)** carry *zero* cross-sectional return predictability for any signal the factory can compute;
- **(R1)** reproduce real within-month cross-sectional dependence (the realism failure that most distorts FDR — G1 verdict);
- **(R2)** reproduce fat tails and the real calendar (crisis months, the market path);
- **(R3)** reproduce cross-sectional heteroskedasticity — firms must differ in risk, or vol/illiquidity signals get unrealistically low dispersion and the FDR is understated;
- **(R4)** preserve eligibility/segment structure, so `min_names_per_month`, the $-volume floor and the largemid/small split behave as they do in production.

### 2.2 Why the obvious construction fails (record this — it is the trap)
"Block bootstrap the calendar, then shuffle ticker labels" preserves realism beautifully and **is not a null**. Relabelling is column-consistent: a firm keeps its own history, so momentum, reversal, quality and vol structure survive intact inside every block. A 12-month block still contains 12 months of real momentum. Any DGP that reuses whole real firm-histories leaks real alpha into the α=0 cell and would make our false-discovery rate look catastrophic for reasons that have nothing to do with our gates.

**To kill alpha you must break the link between a firm's past and its own future at monthly granularity.** That forces a factor-residual construction.

### 2.3 DGP-A (PRIMARY) — factor path + scale-preserved residual permutation

For firm *i*, month *t*:

```
r*[i,t] = β[i] · f[t]  +  σ[i] · z*[i,t]
```

| Term | Construction | Which requirement it serves |
|---|---|---|
| `f[t]` | The **real** factor returns for month *t* — MKT, SMB, HML, RMW, CMA, UMD from the pinned vintage `data/ff_factors.parquet` (`ff_factors_VINTAGE.json`) | R2: the real calendar, real crisis months, real market fat tails, exactly |
| `β[i]` | Real full-sample loadings of firm *i* from the real panel, **held time-invariant** | R1: realistic cross-sectional dispersion of systematic exposure → realistic pairwise correlation. Time-invariance guarantees no beta-timing alpha exists |
| `σ[i]` | Real residual vol of firm *i* (full-sample), time-invariant | R3: firms keep their risk identity, so ivol/illiq signals retain realistic dispersion |
| `z*[·,t]` | Standardized real residuals, **permuted across firms within month t**, fresh permutation per month per replication | N: destroys every firm-past→firm-future link while preserving the exact month-*t* cross-sectional residual distribution (dispersion, skew, kurtosis) |

`month_end_price` and `monthly_dollar_vol` are **regenerated consistently** from the synthetic return path: price compounds from the real month-0 price of the firm whose slot it occupies; dollar volume is carried from the real panel column (volume is not a return, it carries no return-predictability once returns are re-drawn, and carrying it preserves R4 exactly). Delisting: a firm's synthetic history is truncated at its real `delist_month` and stamped with the real delisting return, so survivorship structure and universe attrition are preserved.

**Why this is a genuine null:** conditional on month *t*, the assignment of residual to firm is a uniform random permutation independent of every formation-month characteristic. So for *any* signal `S` computed from information through month *m*, `E[rank-IC(S_m, r*_{m+1})] = 0` exactly. Not approximately — by construction.

**The known realism gap, stated up front:** firm-level residual **vol clustering** is destroyed (only factor-driven clustering survives). Measured and reported in the fidelity table, never hidden. The direction of the resulting bias is toward *understating* the FDR (less persistent idiosyncratic vol → fewer lucky-streak candidates), which we state as a caveat on the α=0 number.

### 2.4 Fidelity gate (Stage 1's deliverable — real vs synthetic)
| # | Target | Tolerance | If it fails |
|---|---|---|---|
| F1 | Mean pairwise correlation of monthly returns, overall and per size tercile | within 20% relative | DGP rejected |
| F2 | Median and p95 of within-month cross-sectional return dispersion | within 15% | DGP rejected |
| F3 | Pooled excess kurtosis and skew of monthly returns | kurtosis within 30%, skew same sign | DGP rejected |
| F4 | Distribution of firm-level 60-month realized vol (KS distance) | KS < 0.10 | DGP rejected |
| F5 | Market path identical | exact assert | Build bug |
| F6 | Mean eligible names/month, largemid & small counts | within 5% of 3,120 | R4 broken → DGP rejected |
| F7 | Autocorrelation of \|returns\| at lags 1–6 | **reported, not gating** | Known gap (§2.3) — report the number |
| **F8** | **Null check: mean rank-IC of all 20 batch-1 signals on α=0 panels** | \|mean IC\| ≤ 2 × MC-SE for every signal | **DGP leaks alpha → STOP.** This is the single most important assertion in the build |

### 2.5 DGP-B (FALLBACK / CROSS-CHECK) — label permutation
Keep the real panel entirely; permute the mapping from formation-month cross-section to test-month realized returns. Exactly zero alpha by construction, every marginal preserved, and it is the same logic as the shuffled-CV demo already run in round 16.
- **Limitation:** cannot support controlled-Sharpe alpha injection (there is no coherent panel to inject into), so it gives the FDR only, not the false-kill curve.
- **Use:** the FDR from DGP-A at α=0 must agree with the DGP-B FDR within Monte Carlo error. If they disagree, DGP-A has a realism defect that matters. Cheap, and it turns "trust our simulator" into a testable claim.

---

## 3. ALPHA INJECTION

### 3.1 The injected characteristic
Add one synthetic column-block `X[i,m]` to the panel — a formation-month characteristic with realistic persistence (AR(1), φ = 0.9 monthly, cross-sectionally standardized). The factory does **not** see `X` directly. It sees a library signal correlated with it:

```
S_observed = ρ_sig · X  +  √(1−ρ_sig²) · noise
```

`ρ_sig` is a first-class parameter, default **0.5**. This is the honesty knob: injecting alpha onto a characteristic the library measures *perfectly* (ρ=1) makes discovery trivial and would produce a flatteringly low false-kill rate. Report the headline grid at ρ_sig = 0.5 and a sensitivity row at ρ_sig ∈ {0.3, 1.0}.

### 3.2 Magnitude → Sharpe mapping
The factory's unit of evaluation is the **top-decile long book's monthly net excess vs segment EW**. Injection is linear in the cross-sectional percentile of `X` and **mean-zero across the cross-section**, so the market/EW benchmark is unchanged (otherwise we would be injecting a level effect the benchmark absorbs):

```
Δr[i, m+1] = k · 2 · (pct_rank(X[i,m]) − 0.5)
```

A top-decile book holds mean `pct_rank ≈ 0.95` → per-month payoff ≈ `0.9 · k`; the EW universe gets ≈ 0. Given σ̂ = the measured monthly vol of a decile book's excess return on the null panel (Stage 0 measures it; expect 1.5–2.5%/mo):

```
target μ_m = S_ann · σ̂ / √12          k = μ_m / 0.9
```

Worked: `S=0.4, σ̂=2.0%/mo → μ_m ≈ 23 bps/mo → k ≈ 26 bps`.

**Injection is specified GROSS.** The pipeline's own 25bps one-way cost model then eats part of it (a hold-band decile book turns over ~15–30%/mo one-way → 4–8 bps/mo). That erosion is exactly what we are trying to measure; pre-netting it would hide the cost model's contribution to false kills. Both gross-injected and realized-net Sharpe are reported per cell.

### 3.3 The four injection designs
| ID | Design | What it tests | Note |
|---|---|---|---|
| **I1** | Constant, diffuse, largemid, orthogonal to size/factors | Baseline power | **"Easy mode" — explicitly NOT the headline number.** A pipeline with a broken confirm wall or a dead cost model still finds this |
| **I2** | Decaying: `α_t = α_0 · exp(−t/τ)`, τ = 60 months, calibrated so *full-sample* Sharpe hits the target | **The highest-value cell.** Our confirm window is the last 6 years — a decaying real edge is precisely what an explore/confirm wall would falsely kill | If false-kill here is far above I1, the wall (not the DSR) is the overpowered gate |
| **I3** | Sub-universe: alpha only in the `small` segment | Segment structure + tradability screens | Connects to §28's short-leg/microcap history |
| **I4** | Factor-correlated: `corr(X, size) = 0.5` | Do our controls kill real non-orthogonal alpha? | The realistic case — real anomalies are rarely orthogonal |

**Injection-design traps, named so we do not fall into them:** constant + diffuse + large-cap + orthogonal + no decay = the configuration under which a miscalibrated pipeline looks calibrated. Any headline claim drawn only from I1 is inadmissible. Second trap: a slow-moving `X` (φ→1) understates false-kill for fast signals because turnover cost never bites — φ is fixed at 0.9 and stated.

### 3.4 Trial count for the DSR
Each replication runs the frozen batch-1 scan (**20 signals × 2 segments = 40 explore candidates**, per `STRATEGY_FACTORY.md`), applies the frozen graduation rule (largemid `t_net_excess ≥ 1.5` AND `t_ic ≥ 2.0`, top-5 cap), then evaluates graduates on the confirm window with `evaluate_candidate`. Two deflation variants are recorded per rep:
- `n_trials = 40` (the trials actually run inside this experiment), and
- `n_trials = 179` (our production deflation).

**The delta between them is itself a paper exhibit:** it quantifies what deflating against the full search history costs a real edge.

---

## 4. HARNESS INTEGRATION

### 4.1 What is touched and what is not
**Touched:** panel construction only.
**Must NOT be touched — asserted at run start, not merely promised:** `ScanConfig` (top_frac 0.10, hold_band_frac 0.30, cost_bps_one_way 25.0, min_names_per_month 100, window 2004-01-31 … 2018-12-31), the graduation rule constants, `DSR_SHIP_THRESHOLD = 0.95`, `PBO_REJECT_THRESHOLD = 0.5`, `DEFAULT_SR_VARIANCE = 0.01`, `expected_max_sharpe`, `probabilistic_sharpe_ratio`. The harness imports these and compares them to values frozen in `calibration/config.py`; **a mismatch raises**. Otherwise a future edit to the gate would silently change what the calibration means, and the posterior map would keep being consumed as if nothing happened.

### 4.2 The silent-failure paths, and how each is made to raise
House rule: *code that runs green and does nothing is the enemy.* Enumerated:

| # | Silent path | Fix |
|---|---|---|
| S1 | **`run_batch` swallows scan exceptions** (`explore.py:158-161` catches `Exception`, logs, and emits a row with `months=0`). Under calibration a crashed scan would silently count as "not discovered" and inflate the false-kill rate | The calibration harness calls `scan_signal` **directly** and lets it raise. `run_batch` is not used |
| S2 | An injection that changes nothing (k=0, wrong column alignment, injected into the wrong month) would make every α level look like α=0 — reading as "our pipeline is terrible" instead of "our injector is broken" | Post-injection assert: `(r_injected − r_null)` is non-zero for ≥99% of eligible cells, and the **perfect-foresight book** on `X` realizes the target Sharpe within ±10% (Stage 2 gate) |
| S3 | `evaluate_candidate` returns `pbo=None` when no `perf_matrix` is supplied, and then the candidate can never ship — a silent 100% false-kill | The harness always supplies the T×40 batch `perf_matrix` (it has it naturally). If `perf_matrix` is None at call time → raise. **Side finding for M3: check whether production survivors were ever evaluated with a perf_matrix; if not, the production ship path has never been able to return ADOPT** |
| S4 | Fidelity gate silently skipped when a target can't be computed | Every fidelity metric returns a value or raises; no `try/except` around F1–F8 |
| S5 | Reps that produced zero graduates vs reps that errored are indistinguishable in an aggregate | Every rep writes a row with an explicit terminal state ∈ {`no_graduate`, `confirm_fail`, `dsr_fail`, `pbo_fail`, `adopt`} plus its seed; counts must sum to n_reps or the aggregation raises |

### 4.3 Seeding and common random numbers
`seed = SEED_BASE + rep_index`, one `np.random.default_rng(seed)` per replication, seed written into every output row so any single rep replays standalone.

**CRN:** rep *r* uses the **same null panel** for every α level and every injection design; only the injection differs. Consequence to state on the exhibits: marginal FDR / false-kill estimates keep their binomial SE (±3.1pp at n=1,000, p≈0.5), but *differences across α* are paired and far more precise. This is what makes the power curve smooth enough to read at affordable rep counts.

### 4.4 Compute budget — the binding constraint
Neither research source costed this, and it is what actually sizes the experiment.

Rough shape: one `scan_signal` = 180 test months × sort/rank over ~3,000 eligible names. 40 scans per rep. If a rep costs 60 s, the full 4 α × 4 designs × 1,000 reps grid = 16,000 reps = **267 core-hours** — not a laptop night.

Levers, in order of application: (a) subset the panel to eligible columns once per rep rather than carrying 11,098 dense columns; (b) precompute the signal matrices that do not depend on the injection; (c) largemid-only for the headline grid (the graduation rule is largemid-only anyway — the `small` scans exist to fill the 40-candidate count and can be computed but not re-derived per α under CRN); (d) `ProcessPoolExecutor` across cores (÷8 on this machine).

**Pre-registered sizing rule (fixed before results):**
- Headline cells — α ∈ {0, 0.2, 0.4, 0.6} × **I2-decaying**, ρ_sig = 0.5: **n = 1,000** (±3.1pp).
- I1, I3, I4 at the same α grid: **n = 250** (±6.2pp), stated on the table.
- ρ_sig sensitivity: n = 250.
Every table cell prints its n and its Wilson 95% interval. **If Stage 0 measures a per-rep cost that makes even this infeasible, the descope is stated in advance: drop to n=250 everywhere and say so — never silently truncate coverage** (the "no silent caps" rule).

---

## 5. OUTPUTS

### Table 1 — Discovery operating characteristics
Rows: α × injection design. Columns: `P(graduate at explore)`, `P(pass confirm)`, `P(DSR≥0.95 | n=40)`, `P(DSR≥0.95 | n=179)`, `P(ADOPT-CANDIDATE)`, each with Wilson 95% CI and n.
- The **α = 0 row is the false-discovery rate** — a number this project has never had.
- The **α > 0 rows give false-kill = 1 − P(ADOPT)**.

### Table 2 — Stage attribution of kills *(the actionable one)*
Of the reps that failed at α = 0.4: what fraction died at the explore t-bar, at confirm, at DSR, at PBO. Tells us **which gate** is overpowered — "recalibrate the gates" is not an instruction until we know which one.

### Table 3 — Evidence → posterior map *(what the sizing ladder consumes)*
Likelihood `L(E | α)` estimated from the simulation over a discretized evidence vector `E = (explore-t bucket, confirm-t bucket, DSR bucket)`, combined with a **pre-registered prior**:

```
π(α=0) = 0.85   π(0.2) = 0.09   π(0.4) = 0.045   π(0.6) = 0.015
```

justified by McLean-Pontiff decay, Harvey-Liu FDR, and our own 4-of-179 survival rate. Two sensitivity priors (mass 0.75 and 0.95 at zero) ship alongside, because the ladder's inputs *are* prior-sensitive and hiding that would be dishonest.

Output artifact: `posterior_map.json`, consumed by I1 (decision engine). **Stated on the artifact and in the paper:** this is `P(α ≥ 0.2 | E)` *under this DGP and this prior*. It is not a universal probability of edge-realness.

Sanity gate: the map must be **monotone** in the evidence ordering (higher t → higher posterior). Non-monotonicity means the likelihood estimate is too noisy → do not ship to the ladder.

### The two paper exhibits
- **Exhibit A — "Operating characteristics of a strategy factory."** x = injected annualized Sharpe, y = P(discover); one line per cumulative gate stage (explore-only → +confirm → +DSR@179). The intercept at x = 0 is the false-discovery rate; the gap between lines is what each gate costs a real edge. One small-multiple panel per injection design.
- **Exhibit B — "What the verdict is worth."** Heatmap of `P(real | evidence bucket)` with the sizing-ladder bands (0×, 0.25×, 0.5×, 0.75×, 1.0×) overlaid. This is the exhibit that connects the methodology to the capital decision, and it is the answer to "should capital scale with confidence."

---

## 6. STAGED BUILD PLAN (kill criterion per stage, Gate-philosophy style)

| Stage | Scope | Deliverable | **Kill criterion** |
|---|---|---|---|
| **0** *(½ session)* | Seam audit + cost measurement. Time `scan_signal` on the real cached panel; measure σ̂ (decile-book excess vol); confirm `Panel` substitution works end-to-end with a trivially perturbed real panel | Timing table + σ̂ | **One rep > 10 s after the §4.4 optimizations → the 1k grid is unaffordable; descope to n=250 and state the precision, or fall back to DGP-B for the FDR alone** |
| **1** *(one session — sized to land)* | DGP-A generator + fidelity gate F1–F8 | Real-vs-synthetic fidelity table; zero-alpha IC assertion over all 20 batch-1 signals | **Any batch-1 signal shows \|mean rank-IC\| > 2 MC-SE on α=0 panels, or F1/F2 miss by >30% → DGP-A rejected; fall back to DGP-B and report that alpha-injection power analysis is unsupported** |
| **2** | Injection + magnitude calibration | Perfect-foresight book on `X` realizes target Sharpe per α level | **Realized Sharpe outside ±20% of target at any α → mapping broken, fix before any grid run** (this is the S2 guard: a no-op injector would otherwise masquerade as a terrible pipeline) |
| **3** *(overnight)* | The grid | Tables 1 and 2 | **The Gate M criterion itself: false-kill at α=0.4 > ~50% → recalibrate gates before any new family runs.** Table 2 says which gate |
| **4** | Posterior map + exhibits | `posterior_map.json`, Exhibits A and B | **Non-monotone posterior in the evidence ordering → do not ship to the sizing ladder** |
| **5** *(reuses 1–3)* | M2 permutation-placebo operating characteristics: inject a known event-day effect, sweep effect size, measure the gate's kill rate | Placebo power curve | Answers G3 Q4; the placebo's own false-kill rate is a paper exhibit either way |
| **6** *(optional)* | Out-of-era realism check on `crsp_msf_full.parquet` (1963–2001) | Does the calibration transfer? | Divergence is a finding, not a failure — report it |

**Stage 1 is the one sized to land in a single session**, per the brief. Stages 0 and 1 together are the honest minimum before anyone quotes an M1 number.

---

## 7. FILE PLAN (no code yet — this is the target shape)

```
aegis_brain/calibration/
├── config.py        # frozen dataclasses: DGP params, injection grid, rep counts,
│                    #   SEED_BASE, and the PRODUCTION_CONSTANTS snapshot asserted in §4.1
├── panel_gen.py     # DGP-A generator → Panel;  DGP-B label-permutation null
├── fidelity.py      # F1–F8, each raises rather than returning a sentinel
├── inject.py        # X generation, ρ_sig blending, k calibration, the S2 assertions
├── run_grid.py      # one rep = build null → for each α: inject → scan_signal ×40 →
│                    #   graduate → confirm → evaluate_candidate; writes one row per rep
├── posterior.py     # likelihood estimation, priors, monotonicity gate, posterior_map.json
└── exhibits.py      # Exhibits A and B
tests/test_calibration.py   # in-memory fixture panel, no network, no parquet reads
```

Outputs land in `runs/GATE-M1/` alongside every other trial run, with the seed and the config hash in the run manifest.

---

## 8. WHAT THIS DOES NOT ANSWER

Stated so the paper does not overclaim:
- The calibration is conditional on **DGP-A being a good enough world**. If the true return process differs in a way that matters (firm-level vol clustering is the known gap), the operating characteristics shift. The DGP-B cross-check bounds this partially; nothing eliminates it.
- The posterior map is conditional on a **stated prior**. It converts "the pipeline said X" into "probability the edge is real *given our beliefs about how rare edges are*." Different prior, different ladder.
- It certifies the **factory**, not the **data**. Gate D certifies the data; a signal built on a broken linkage will be evaluated impeccably and still be wrong.
- It says nothing about whether an edge **survives live** — that is the forward paper clocks, and they remain the only scorecard.
