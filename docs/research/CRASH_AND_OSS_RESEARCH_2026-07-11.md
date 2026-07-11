# Crash-Engine Improvement Plan + OSS Borrow-Scan — 2026-07-11

> Research deliverable only (no code changes). Context read: `docs/BACKLOG.md`
> SECTION T + M3/V1, `docs/TRIALS/TRIAL-CRASH-fragility-composite.md`,
> `backend/services/portfolio_intelligence/fragility.py`, `REFERENCES.md`,
> CLAUDE.md. Ground truth on current state: the retrained `crash_model.pkl` is
> provenanced but **non-discriminating** (val AUC=nan on sparse events, outputs
> ~0.066 in every regime — M3 "remaining" note); the working crisis read is the
> descriptive fragility composite (8 active inputs, 5 logged candidates — VIX
> term structure, put skew, IPO issuance, mega-cap concentration, crash
> narrative — the latter three already collecting forward), with TRIAL-CRASH
> accruing forward Brier vs climatology.

---

## PART 1 — Crash-prediction improvement plan

### 1a. Target definitions that beat binary crash labels

The M3 failure (AUC=nan, degenerate calibrator) is exactly what the literature
predicts for a binary "≥20% drawdown" label: ~7 positive events in the whole
training history is unlearnable. Four better-documented alternatives, roughly
ranked for this project:

1. **Continuous stress-index target, predicted as a distribution (BIS-style).**
   [BIS WP 1250](https://www.bis.org/publ/work1250.pdf) (Aldasoro, Hördahl,
   Schrimpf, Zhu, Mar 2025) predicts the *full distribution* (quantiles) of
   market-condition indicators rather than a binary event; tree ensembles beat
   linear models by up to ~27% OOS on **tail** stress specifically, with
   Shapley attribution to funding liquidity / investor overextension / global
   financial cycle ([CEPR summary](https://cepr.org/voxeu/columns/how-ai-can-help-detect-warning-signs-financial-market-stress)).
   Every period supplies a label → no rare-event starvation. The free-data
   analogue: regress future h-day quantiles of a stress proxy (NFCI, STLFSI4,
   or realized SPY drawdown depth) with LightGBM quantile objectives — the
   stack already in-house.
2. **Multi-threshold / ordinal drawdown exceedance.** Instead of one binary
   P(DD≥20%), predict the exceedance curve P(maxDD ≥ x within h) for
   x ∈ {5,10,15,20%} × h ∈ {30,60,90d}. The 5–10% thresholds have 10–20× more
   events (learnable), and monotonicity across thresholds/horizons is a free
   structural check (same discipline as the 3m≤6m≤12m rule). The 20% cell
   remains the headline but is anchored by the dense cells.
3. **Regime-state probabilities as an intermediate target.** Statistical jump
   models ([Shu/Mulvey line, arXiv 2402.05272](https://arxiv.org/html/2402.05272v2))
   and causal HMM variants ([arXiv 2603.04441](https://arxiv.org/html/2603.04441))
   show OOS drawdown reduction from *state* prediction rather than event
   prediction; regime persistence makes the label dense. This is adjacent to
   the existing HMM/regime_detector — the improvement is a leakage-safe online
   inference path and calibrated state probabilities, not a new concept.
4. **Vol-scaled barrier labels (triple-barrier).** Lopez de Prado-style labels
   with volatility-scaled barriers rather than a fixed −20% produce balanced
   classes ([Korean-market evidence, arXiv 2504.02249](https://arxiv.org/html/2504.02249v2)).
   Also relevant: the ["Label Horizon Paradox" (arXiv 2602.03395)](https://arxiv.org/abs/2602.03395)
   — the optimal *training* label horizon often differs from the inference
   target, which licenses training on dense short-horizon severity and
   evaluating on the sparse 20%/90d cell (evaluation target stays
   pre-registered; only the supervision signal changes).

**Recommendation:** target = the exceedance/severity distribution (options 1+2
combined: LightGBM quantile on forward max-drawdown depth, read out as
threshold probabilities), with regime-state probability as a feature, not a
target. Binary-20% survives only as the TRIAL-CRASH *evaluation* cell.

### 1b. Free leading indicators with documented forward skill

| Indicator | Free source | Evidence grade (honest) |
|---|---|---|
| **Near-term forward spread** (18m-fwd 3m rate − spot 3m) | FRED (computable from CMT curve) | Strong — statistically dominates 10y−3m for recessions ([Engstrom–Sharpe, Fed Notes](https://www.federalreserve.gov/econres/notes/feds-notes/dont-fear-the-yield-curve-20180628.html)). Not yet an input; cheap add. |
| **Excess bond premium (EBP)** | Fed publishes monthly CSV (Gilchrist–Zakrajšek) | Strong for recessions/credit stress ([Fed Notes 2016](https://www.federalreserve.gov/econresdata/notes/feds-notes/2016/recession-risk-and-the-excess-bond-premium-20160408.html)); episode-dependent for equity drawdowns ([2026 episode study](https://www.sciencedirect.com/science/article/pii/S3050700626000514)). Superior to raw HY/IG OAS (strips expected default). |
| HY/IG OAS percentile | FRED (already active) | Coincident-to-slightly-leading; keep, but EBP is the upgrade. |
| **NFCI / ANFCI** | Chicago Fed weekly, FRED | Broad conditions composite (105 series); documented as risk-off *state* indicator, weaker as an equity-drawdown *timing* lead. Use as feature + benchmark. |
| **STLFSI4 / KCFSI / OFR FSI** | FRED / OFR daily | Free professionally-maintained stress indices — primarily valuable as **benchmarks the composite must beat**, not as inputs ([STLFSI4](https://fred.stlouisfed.org/series/STLFSI4)). |
| ICSA (initial claims) | FRED weekly | Best-documented *macro* lead (already a crash-model feature); recession lead, not crash-timing. |
| **Margin debt** (FINRA) | FINRA monthly (~25d lag) | Peaks preceded S&P tops by 0–6 months in 2000/2007/2018/2021/2025 ([Advisor Perspectives series](https://www.advisorperspectives.com/dshort/updates/2026/06/24/margin-debt-finra)) — but the peak is only knowable ~2 months late; treat as leverage *level* percentile (V1 already lists it). |
| **VIX term structure** (VIX/VIX3M) | CBOE via yfinance (^VIX, ^VIX3M — no futures curve needed) | Persistent backwardation (5d+) associates with deeper drawdowns; contango carries little timing signal ([Macrosynergy](https://macrosynergy.com/research/vix-term-structure-as-a-trading-signal/)). Already a logged candidate — the index-ratio form removes the "flaky futures fetch" blocker. |
| SKEW / put-skew | CBOE ^SKEW | **Weak/mixed** — literature finds poor short-horizon predictive power ([NAJEF 2020](https://www.sciencedirect.com/science/article/abs/pii/S1062940820302370)). Keep as candidate, low prior. |
| Breadth (% > 200dma, A/D) | computable from existing universe | Documented in practitioner literature, thin academic support; fine as a *tested* candidate only. |

### 1c. Calibration + evaluation discipline for rare events

- **Keep Brier-vs-climatology as primary** (TRIAL-CRASH already pre-registers
  it — do not change the primary metric mid-trial). Report event count + block-
  bootstrap CI everywhere (`brier_with_ci` exists; M2).
- **Add PR-AUC, drop ROC-AUC as a gate for the 20% cell.** With huge negative
  classes, ROC-AUC flatters models that generate constant false alarms;
  PR-AUC tracks what matters ([PMC review](https://pmc.ncbi.nlm.nih.gov/articles/PMC12667734/),
  [imbalance-robust framework, arXiv 2512.00916](https://arxiv.org/pdf/2512.00916)).
  Note: the CLAUDE.md "walk-forward AUC≥0.70" health check is the wrong gate
  for this label; propose PR-AUC vs prevalence + Brier skill instead.
- **Event-based verification (meteorology-style):** for each historical stress
  episode, score hit / miss / false alarm inside a pre-declared lead window
  (30/60/120d before the drawdown peak) and report precision/recall/F1 per
  window — the exact harness fatcrash uses (406 crash windows, below). This is
  the honest complement to per-day Brier: it answers "did it warn *before* the
  episodes, and how often did it cry wolf."
- **Calibration:** reliability diagrams on held-out folds only (house rule
  already forbids fitting the calibrator on its own data); with <30 matured
  events per cell, report `insufficient_forward_data` rather than a curve —
  the trial doc's rarity caveat generalizes.
- Multi-threshold targets partially *solve* the rarity problem rather than
  just measuring around it: calibration earns statistical power at 5–10%
  thresholds long before the 20% cell matures.

### 1d. Should crash become its own subsystem?

**Yes as a module boundary; no as a deployed service.** Justified: crash logic
is now smeared across `crash_model`, `fragility.py` (inside
portfolio_intelligence), `survival_model`, `crash_timeline`, `bubble_detector`,
`systemic_risk`, `anomaly_detector`, `regime_detector` — consolidation into a
`backend/services/crash/` package with one registry of inputs (each carrying
source, lead/lag label, trial status), one evaluation harness, and one API
surface would end the drift between them. **Not** justified: a separate
process/deploy — the API is stateless, shares the PIT store and cache, has no
independent scaling need, and a second Railway service would double the
verify-prod surface for zero benefit. Precedent: portfolio_intelligence is
already a package-not-service and it works.

### Phased plan (house rules: pre-registered, forward-validated, descriptive-until-proven, never auto-arms)

**P1 — Consolidate + benchmark + finish the candidates (1–2 sessions).**
Create `services/crash/` package (mechanical move, no math changes; grep-guard
test that no lane path imports it stays). Wire VIX/VIX3M ratio candidate
collector (unblocks the logged candidate without futures data). Add EBP +
near-term-forward-spread as candidate collectors (FRED/Fed CSV, fail-loud).
Add STLFSI4/NFCI as *benchmarks* in the fragility API response ("our composite
vs the Fed's"). Extend the eval harness to multi-threshold (5/10/15/20%) ×
multi-horizon Brier + PR-AUC + event-window hit/false-alarm table — filed as a
**pre-registered addendum** (TRIAL-CRASH-2) so the original primary metric is
untouched. Effort: mostly plumbing on existing patterns (pit_score_collector,
fragility candidates).

**P2 — Retrain on a learnable target (2–4 sessions, offline).**
LightGBM quantile/ordinal model of forward max-drawdown severity (1a rec),
trained walk-forward with purged CV + embargo, evaluated per 1c (PR-AUC +
Brier skill + event windows), monotonicity enforced across thresholds and
horizons. Ship with the meta.json sidecar discipline from M3. Gate: beats
climatology AND the STLFSI4-as-predictor baseline on held-out folds — else it
stays dark like today. Output surfaces as *descriptive* exceedance curves
("P(≥10% DD in 60d): 14%"), never "crash imminent." Pre-register before the
first fit.

**P3 — Forward promotion only (calendar time, not effort).**
Candidates (IPO froth, VIX term, concentration, narrative, EBP…) enter the
composite only after their individual forward IC/Brier trial reads positive —
the TRIAL-CRASH decision rule as written. The P2 model earns UI promotion only
on forward Brier skill > 0 across horizons; anything that could ever inform a
lane is a **separate** registry trial and remains behind the never-auto-arm
hard stop. Expected reality check: most candidates will read null; publishing
that is the differentiator.

**Honest uncertainty:** short-horizon crash *timing* skill ≈ 0 remains the
canon prior (A5); nothing found this pass overturns it. The literature supports
predicting *stress distributions* and *fragility states*, not crash dates. The
margin-debt and VIX-term evidence is practitioner-grade, not peer-review-grade;
episode studies show credit-spread lead relationships are regime-dependent.

---

## PART 2 — OSS borrow-scan (new/changed since REFERENCES.md; 15 prior verdicts not re-litigated)

| Project | What to borrow (pattern, not dependency) | License | Verdict |
|---|---|---|---|
| [**fatcrash**](https://github.com/unbalancedparentheses/fatcrash) (Rust+Python, data through 2025) | The **event-window evaluation harness**: 406 crash / 1,061 non-crash windows across 37+ assets, precision/recall/F1 at 30/60/120d pre-crash — the exact 1c pattern. Also its estimator menu (Taleb kappa, Hill tail index, critical-slowing-down on vol — all cheap on daily data) and its *negative* results (DFA/Hurst/GSADF disabled for poor F1; LPPLS confidence top F1 ≈ 0.48 — corroborates our "descriptive-only" LPPLS stance). | **No license file** → all-rights-reserved; code must never be copied | **Borrow-pattern** (eval harness + candidate list), re-implement clean-room |
| [**jumpmodels**](https://github.com/Yizhan-Oliver-Shu/jump-models) (Shu/Mulvey, sklearn-style, `predict_proba_online`) | Statistical jump models for regime ID — more label-stable than HMM, with an explicitly *online/causal* inference API (the leakage trap our HMM path shares). Small, focused, peer-reviewed lineage. | Apache-2.0 (MIT-compatible w/ attribution) | **Candidate pip dependency** for P2 regime features — the one item this scan would actually install |
| [BIS WP 1250](https://www.bis.org/publ/work1250.htm) (paper) | Quantile-forest-on-stress-distribution method + Shapley grouping into funding/overextension/cycle themes. Already a CLAUDE.md reference; the *new* borrow is the target design (1a). | paper | **Borrow-method** (drives P2) |
| [**TradingAgents**](https://github.com/tauricresearch/tradingagents) (TauricResearch, ~80k stars) | The structured **bull-vs-bear debate + risk-team veto** prompt pattern → conviction-lane decision logging (forces an explicit counter-thesis per decision, complements the FactFin counterfactual prompting already in canon A2). Not the framework, not the trading premise (profit-mirage firewall applies in full). | Apache-2.0 | **Borrow-pattern** (debate prompt for conviction lane); skip framework |
| [**ai-hedge-fund**](https://github.com/virattt/ai-hedge-fund) (virattt, ~43k stars) | Investor-persona agents (Graham/Burry/…) — entertaining, epistemically identical to LangAlpha (no registry, no forward record). Nothing here Aegis lacks. | MIT | **Skip** |
| [**RD-Agent / RD-Agent-Quant**](https://github.com/microsoft/qlib) (Microsoft, wired into qlib 2025) | Automated factor/model R&D loop with hypothesis memory — the industrial cousin of `lab/rd_loop.py`. Borrow: hypothesis-dedup and factor-library bookkeeping ideas for the lab loop. Qlib-the-framework verdict (2026-06-20: learn-from, don't adopt) unchanged. | MIT | **Watch**; pattern-mine when lab loop next evolves |
| [**openassetpricing**](https://www.openassetpricing.com/data/) (Chen–Zimmermann, Oct 2025 first all-Python release, 212 predictors) | Signal *definitions* + published t-stats as the sanity harness for T8/T12 factor work (already on the backlog as "CZ harness" — the 2025 Python release makes it materially easier). Data for research use; check per-signal terms before redistribution. | code GPL-2.0 (repo), data academic | **Borrow-definitions** (already planned; do not vendor GPL code) |
| [**edgartools**](https://github.com/dgunning/edgartools) (active through 2026) | Previously rejected as a runtime dependency (50-min hang, T9) — that stands. New note: its **N-PORT parsing** docs/schema are the reference for the T12 N-PORT collector (monthly fund holdings = the free ETF-flow proxy). Read their parser, re-implement thin + hang-proof on the existing `_sec_get` choke-point. | MIT | **Borrow-pattern** (N-PORT schema), dependency still rejected |
| [**kadoa-org/congress-trading-monitor**](https://github.com/kadoa-org/congress-trading-monitor) (2025, 54k+ transactions, 2012–present) | Independent congressional-trades dataset → **cross-check for T11's FMP feed** (catch FMP contract drift / gaps without adding a scraper). The senate/house-stock-watcher dumps remain dead (T11 verdict stands). | check repo (dataset provenance = official disclosures) | **Watch** (validation source only, never primary) |
| [**OpenBB / Open Data Platform**](https://openbb.co/blog/license-change-openbb-platform-goes-agpl/) (active, May 2026 PyPI release) | Still AGPL → house rule: **no code, ever**. Their ODP provider-standardization direction is worth watching against our provider registry; nothing new to take this pass. | AGPL-3.0 | **Watch** (ideas only) |
| Ghostfolio / Lumibot / AlgoVault | Portfolio tracking (AGPL), broker-execution framework, crypto Merkle track-record. Nearest miss: nobody found does *pre-registered paper-lane forward records* — the spine remains uncopied, which is the moat confirmation, not a gap. | AGPL / Apache / n/a | **Skip** |

**License hygiene reminder:** fatcrash (no license) and openassetpricing code
(GPL-2.0) are the two contamination risks in this table — patterns and
definitions only, re-implemented, credited in REFERENCES.md when taken.

### Sources (primary)
BIS WP 1250: https://www.bis.org/publ/work1250.pdf · CEPR column: https://cepr.org/voxeu/columns/how-ai-can-help-detect-warning-signs-financial-market-stress ·
Fed near-term forward spread: https://www.federalreserve.gov/econres/notes/feds-notes/dont-fear-the-yield-curve-20180628.html · EBP: https://www.federalreserve.gov/econresdata/notes/feds-notes/2016/recession-risk-and-the-excess-bond-premium-20160408.html ·
Episode heterogeneity (2026): https://www.sciencedirect.com/science/article/pii/S3050700626000514 · Rare-event metrics: https://pmc.ncbi.nlm.nih.gov/articles/PMC12667734/ · Imbalance-robust eval: https://arxiv.org/pdf/2512.00916 ·
Label Horizon Paradox: https://arxiv.org/abs/2602.03395 · Jump models: https://arxiv.org/html/2402.05272v2, https://github.com/Yizhan-Oliver-Shu/jump-models · VIX term structure: https://macrosynergy.com/research/vix-term-structure-as-a-trading-signal/ · SKEW: https://www.sciencedirect.com/science/article/abs/pii/S1062940820302370 ·
Margin debt: https://www.advisorperspectives.com/dshort/updates/2026/06/24/margin-debt-finra · STLFSI4: https://fred.stlouisfed.org/series/STLFSI4 · NFCI: https://www.chicagofed.org/research/data/nfci/about ·
fatcrash: https://github.com/unbalancedparentheses/fatcrash · TradingAgents: https://github.com/tauricresearch/tradingagents · ai-hedge-fund: https://github.com/virattt/ai-hedge-fund · qlib/RD-Agent: https://github.com/microsoft/qlib ·
OpenAssetPricing: https://www.openassetpricing.com/data/ · edgartools: https://github.com/dgunning/edgartools · congress-trading-monitor: https://github.com/kadoa-org/congress-trading-monitor · OpenBB AGPL: https://openbb.co/blog/license-change-openbb-platform-goes-agpl/
