# External Review Brief — the gate-calibration arc (2026-08-07)

**Audience:** external reviewers (human or AI agent). This document is
self-contained: the research repo ("Aegis module") is private, so every
number you need is inlined here. Public artifacts are linked. You are asked
to be adversarial — §8 lists the specific claims we want attacked.

**Repos & surfaces**
- Public platform + ledger: https://github.com/Murathanx12/Aegis-Finance
  (start at `NEGATIVE_RESULTS.md`, `docs/CANON.md`, `AGENTS.md`,
  machine-readable summary at `frontend/public/llms.txt`)
- Private research factory: https://github.com/Murathanx12/investing-test-module
  (CRSP/WRDS-licensed data — cannot be public; key results inlined below)
- Live app: https://aegis-finance-six.vercel.app · API health:
  https://aegis-finance-production.up.railway.app/api/health
- Author: Murathan Abdullaev (HKU), mrthnabdullaev@gmail.com

---

## 1. What we are doing, and why

Aegis is a quant research program with one design constraint above all
others: **it must not be able to lie to itself.** Every hypothesis is
pre-registered before it touches data (hypothesis, primary metric, decision
rule, earliest decision date). Evaluation runs behind an explore(2004-2018)
/ confirm(2019-2024) wall on survivorship-free CRSP monthly data. Event
designs carry placebo controls. Adopted strategies earn conviction only
through forward paper NAV (10 lanes, inception 2026-06-08), and the project
makes **no skill claims before 24 months** of forward record. Failures are
published in a top-level ledger — 34 entries and counting.

Between 2026-07 and 2026-08 the factory examined **179 candidate signals**
(GKX-style price/fundamental factors, insider filings, analyst revisions,
PEAD, FDA approvals, 13D/G events, option-implied, institutional ownership,
macro/regime overlays, and more). It adopted approximately **none of them**.

The question that started this arc: *is the market really that efficient,
or are our gates killing everything regardless of truth?*

## 2. How the promising theories were killed — the ladder, measured

The decision ladder every candidate faced ("BRAIN-008", frozen 2026-07-22):

```
explore:  t(net excess) >= 1.5 AND t(rank-IC) >= 2.0, large/mid segment only,
          top-5 cap ranked by t_net, 25 bps flat cost
confirm:  held-out 2019-2024, t_ic >= 1.5, t_net >= 0.8, sign gates
adoption: Deflated Sharpe Ratio (DSR) >= 0.95 at n_trials deflation,
          Probability of Backtest Overfitting (PBO, CSCV) < 0.5
```

In 2026-08 we did what we should have done first: **ran the ladder against
synthetic markets with known injected edges** (GATE-M1 / RECAL-1). Null
panels are built from the real CRSP panel with returns replaced by a
provably-null generator (DGP-A v6 — real betas, real vol surfaces, real
universe attrition, factor months permuted, residuals re-standardized;
certified by 8 fidelity gates including a payoff-null leak gate). Edges are
injected at known strength (annualized Sharpe 0.2/0.4/0.6) under four
designs: I1 constant, I2 decaying (τ=60m), I3 small-cap-only, I4
size-correlated. 250 common-random-number panels per cell.

**Result: the ladder adopts a TRUE Sharpe-0.6 constant edge with
probability 0.000.** Per-stage autopsy:

- The explore t-bars killed 93–99% of decaying (I2) edges before confirm.
- **DSR ≥ 0.95 was unreachable by construction**: on a 72-month
  single-signal book it requires SR_ann ≈ 1.5; a true α=0.6 edge delivers
  ≈ 0.03 through a top-decile book. Turnover engineering buys ≈ 0.24.
- **PBO < 0.5 was a coin flip**: on a 42-book batch of which 41 are null,
  PBO measured 0.514 on a pure-null cell and 0.586 on a cell containing a
  true α=0.6 edge. It measures the batch, not the candidate.
- **The small segment was structurally invisible** (I3): a real
  small-cap-only edge is adopted at exactly the null rate (0.016) at every
  injected strength — the segment filter decided before the data could.

So: **the 0-for-179 record was inevitable and carries almost no
information about the candidate pool.** The market may still be efficient;
our experiment could not have told us.

## 3. The methodology for bringing theories back

We did **not** reopen everything. The recovery is structured in five parts:

**(a) Recalibrate the whole ladder on the simulator, pre-registered.**
A 1800-member ladder family (explore/confirm IC thresholds × segments ×
books × DSR/PBO thresholds) searched on the even-numbered reps, validated
on the held-out odd reps, objective = power at α=0.4 subject to FDR ≤ 5%
with a Wilson-upper ≤ 8% confidence rule. A parametric prediction of the
outcome was registered before the grid ran (it was correct, including
which rule the runner-up would fail). The frozen result ("BRAIN-009"):

```
explore t_ic >= 1.5 (rank by IC, largemid, top-5) ->
confirm t_ic >= 0.5 + IC sign gate -> DSR/PBO inert (reported, not gating)
Measured: per-candidate FPR 1.6% [Wilson 0.62-4.04%, n=250], P(adopt) = 16.4% / 43.6% / 79.6%
at true Sharpe 0.2 / 0.4 / 0.6; held-out half reproduces (44.0%, 1.6%).
```

(All FDR/power numbers in this brief are conditional statements: "under
DGP-A v6 and the registered selection mechanism" — they are properties of
the simulator × pipeline × rule, not of the strategy universe.)

**(b) Classify every past kill by mechanism** (kill audit, 2026-08-07):
- Kills backed by their own receipts **stand** — placebo gates that fired,
  confirm-window sign flips, zero-cost bounds ("could this graduate if
  trading were free?" — the best rank-real large/mid reject reached gross
  t 1.48), direct negative measurements. Recalibration cannot un-fire a
  control.
- Kills whose only evidence was the 0%-power threshold are re-labeled
  **unmeasured** — not "probably true."
- Small-cap candidates were **never examined at all**.

**(c) A single, one-shot replay** of the 179 candidates' banked explore
scans under the frozen recalibrated ladder. One run, no iteration, no
re-tuning — the ledger records whatever comes out.

**(d) The family-null veto** — the new defence that makes (c) honest.
While certifying the null generator we re-derived a known-but-underweighted
fact quantitatively: **zero alpha does not imply zero rank-IC**. Under
heteroskedastic right-skew, volatility/liquidity/price-level signals print
mean |t(IC)| ≈ 1.8 **on pure noise**, with P(t_ic ≥ 1.5) ≈ 70% (null 95th
percentile ≈ 3.0 in large/mid, ≈ 4.2–4.5 in small). The measured 1.6% FDR
applies to candidates whose IC is generic noise — not to that family. So
the replay requires each candidate to clear
`t_ic >= max(1.5, its family's null 95th percentile)`, with the mapping
fixed by construction-inspection before statistics are seen, and gross-t /
short-leg decomposition printed as receipts next to every survivor. Without
this, the replay would "resurrect" volatility artifacts and we would be
manufacturing the very false positives the project exists to prevent.

**(e) Evidence-conditioned sizing, not conviction.** Adopted candidates
are sized by a coarse evidence ladder (no confirm read → 0×; confirm
t_ic < 1.5 → 0.25×; ≥ 1.5 → 0.75×), shipped only because it is monotone on
selection AND held-out halves independently; the finer 5-band map failed
its monotonicity gate and was not shipped.

Contamination is disclosed: during run 2 a preview of real large/mid
candidates against the 1.5 threshold was run (before the replay), so the
*threshold* choice is contaminated for large/mid; the small-segment rows
of the candidate bank remain deliberately unexamined until the replay.

## 4. What run 2 added (2026-08-07, design sweep)

| cell | P(graduate) | P(adopt) |
|---|---|---|
| null | 0.032 | 0.016 |
| α=0.4 constant (I1) | 0.596 | 0.436 |
| α=0.4 decaying (I2) | 0.564 | 0.232 |
| α=0.4 small-only (I3) | 0.032 | 0.016 |
| α=0.4 size-corr (I4) | 0.516 | 0.368 |

- The decaying-edge explore kill is fixed (0.564 vs the old 1-7%).
  Low end-to-end I2 adoption is *correct*: a τ=60m edge decays to 9.2%
  strength inside the confirm window — confirm should be skeptical.
- I3 confirms total small-segment blindness under the frozen ladder.
- A post-hoc variant (both segments + top-10 cap) weakly dominates the
  freeze on every measured cell (large/mid power unchanged at 0.432,
  I3 0.424, held-out FDR identical at 0.016) — documented as post-hoc,
  dated before the 1000 fresh null panels (running now) existed, and held
  as an *attended decision*, not silently adopted.

## 5. Methods from the literature and other projects we declined — and why

| Method | Source | Our verdict |
|---|---|---|
| DSR ≥ 0.95 as a fixed adoption gate | Bailey & López de Prado | Unreachable by construction on 72-month single-signal books (needs SR≈1.5). Kept as a *reported diagnostic*; the multiple-testing defence is now a **measured** FDR. The theorem is fine; inheriting the constant was not. |
| PBO (CSCV) < 0.5 as a fixed gate | Bailey et al. | Measures the batch, not the candidate (0.51 on null cell vs 0.59 on a cell with a true edge, when 41/42 books are null). Reported, not gating. |
| Standard k-fold CV on time series | common practice | Replaced by purged CV with embargo + walk-forward (López de Prado). |
| Backtested alpha claims on free data | common practice | Survivorship is uncorrectable on yfinance-class data (of 20 real delisted names, 1 recoverable). Backtests are direction checks; the track record is forward-only paper NAV. Ledger §4. |
| LPPLS bubble timing | Sornette | Predictive skill refuted twice in adversarial tests; kept as a descriptive flag only. Ledger §3. |
| Vol-managed / conditional vol targeting | Moreira-Muir; Bongaerts et al. | Confirm-stage REJECT — the 2020 crash outran the monthly signal. Ledger §21. |
| Residualisation (of momentum, of institutional ownership, of option skew) | standard academic hygiene | Three independent receipts that it *subtracted the information*: the fitted leg carried the IC. Ledger §23, §26, §27. House rule: residualisation needs 3 receipts before use. |
| IC-only graduation / IC-weighted ensembles | practitioner shortcut | Structural false-positive channel for σ-correlated families (t_ic≈1.8 on noise). Any IC gate needs a family-specific null. Ledger §32 + §34. |
| LLM-directed trading (FinRL-style agents, LLM stock-picking) | multiple 2025-26 papers | Comprehensively dead on external receipts; our canon bans LLM allocation — the LLM narrates, the engine computes. Ledger §19. |
| RL / online learning on P&L | various | Banned by canon (§4): at this signal-to-noise it learns noise; nothing may adapt to its own P&L. |
| Uniform random-date placebos | our own earlier design | Falsely kills real signals under cohort drag; replaced by calendar-preserving permutation across firms. Ledger §30-§31. |
| 12-month crash prediction, incl. our own model | BIS-style ML stress papers | Our model's offline skill was two leaks (FRED reference-vs-publication dates; full-sample feature selection). Honest AUC ≈ 0.46-0.53 at all horizons. Overlay disabled. Ledger §33. |

## 6. The three findings we believe are genuinely reusable

1. **Calibrate the ruler before trusting the kills.** Run your full
   decision ladder against synthetic data with known injected effects. If
   P(adopt | true edge) ≈ 0, your negative results are about your gates.
2. **Zero alpha ⇏ zero rank-IC** under heteroskedastic skew — with numbers
   (t≈1.8 on noise, 70% false-pass at a 1.5 bar) and a concrete fix
   (family-conditional null quantiles).
3. **DSR/PBO must be calibrated slots, not inherited constants** — check
   reachability (what SR does your book length imply?) and batch
   composition before letting them gate.

## 7. Known weaknesses we have already disclosed (attack these too)

- The simulator injects edges whose IC and alpha are *coupled*; it cannot
  model the "IC-real, book-dead" failure mode it later diagnosed in real
  data — the family-null veto is defended by ledger receipts, not by the
  simulator.
- The explore-threshold choice is contaminated for large/mid (a preview
  was run before the replay); the cap and small-segment choices are not.
- n=250 nulls gives FDR only to Wilson [0.4%, 5.7%]; a 1000-rep null
  extension is running as of this writing.
- Forward record is ~60 days: it proves operations, not skill
  (SE of annualized Sharpe ≈ ±2.1 at that length).
- All engineering was done by AI agents (Claude) under human direction;
  two silent-failure bugs in the calibration harness itself were caught
  only by coverage assertions added after the fact. Ledger §34 meta-lesson.

## 8. What we want from reviewers

1. Is the **family-null veto** (t_ic ≥ max(1.5, family null p95), mapping
   fixed by construction before statistics are seen) a sound correction —
   or does it re-introduce researcher degrees of freedom?
2. Is replacing DSR/PBO gating with a **simulator-measured FDR** defensible
   as a multiple-testing control? What failure modes does a
   simulator-calibrated FDR have that analytic deflation does not?
3. The **post-hoc top-10/both-segments variant** weakly dominates the
   frozen ladder on every measured cell. We froze anyway and left the swap
   as an attended decision. Right call, or false rigor?
4. Our claim that killing decayed (I2) edges at confirm is *correct
   behaviour* — do you buy the arithmetic (τ=60m ⇒ 9.2% strength in
   2019-24), or is the confirm window itself the design error?
5. Is the coarse sizing ladder (0×/0.25×/0.75× by confirm IC) defensible,
   or is posterior-from-simulator sizing circular?
6. Anything in `NEGATIVE_RESULTS.md` §1-§34 where you believe we fooled
   ourselves — in either direction (a false kill we defend, or a stated
   "stand" that should reopen).

Please cite specific sections/numbers when disagreeing. Reviews are
cross-verified against the artifacts before adoption
(`docs/AI_REVIEWS_SYNTHESIS_2026-08-03.md` shows the format — five prior
AI reviews, each with its errors flagged).
