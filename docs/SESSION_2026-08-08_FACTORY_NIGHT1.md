# SESSION — Factory NIGHT-1 executed + the amnesia question answered + the brain built

**Date:** 2026-08-08 (late). **Branch:** `factory/night-1` in the Aegis module
repo (`C:\Users\mrthn\Aegis module`). Nothing on `main`, no lane seeded, no flag
flipped, no holdout read.

This session executed the NIGHT-1 prompt rather than handing it over, answered
Murat's LLM-memory question with a measurement, and built the belief network.

---

## 1. The portfolio factory harness (N1) — built and CALIBRATED

`aegis_brain/pf/` — spec in, EXECUTION_STANDARD §3 scorecard out.

- **`panel63.py`** — stitches `crsp_panel_1962_2001` + `crsp_panel_2002` into
  one survivorship-free monthly panel (715 months, 25,890 permnos, real
  delisting returns), with the benchmark question answered honestly: **"beat
  SPY" over 63 years is measured against the CRSP value-weighted total return**
  (Ken French `mktrf+rf`, pinned vintage) — the index SPY tracks, extended back
  to 1963, because SPY itself only starts in 1993. The loader **refuses** any
  window reaching into the registered holdout (2023-01+) unless a holdout
  firing explicitly opts in.
- **`engine.py`** — a real portfolio, not a decile scan: N names, weights drift
  between rebalances, delisted names force-liquidated to cash with costs
  charged, cash earns the bill rate, book inception starts when the universe is
  actually investable (a small-cap strategy sitting in cash in 1965 is not
  performance, and pretending otherwise would have made every small-cap
  strategy look terrible for 20 years).
- **`scorecard.py`** — every metric the standard asks for plus per-regime
  blocks, leave-one-year-out robustness, and a **paired stationary block
  bootstrap** for the ruin constraint (P(max DD worse than 60%)) and the
  terminal-wealth distribution.
- **`controls.py`** — the random-selection-with-identical-turnover placebo,
  turnover-matched by searching the persistence ρ of an AR(1) random score.
- **`regimes.py`** — walk-forward regime labels only (trailing 12-month market
  sign + vol brake, closed months).
- 13 unit tests on the mechanics (cost arithmetic, drift, forced liquidation,
  turnover ordering, loud failures).

**PF-HARNESS-VALID (`runs/PF/VALIDATION.json`) — VERDICT PASS.** Before the
harness judged anything:

- **V1 stitch fidelity: EXACT.** Running the existing banked code path on the
  new stitched panel reproduced INSTR-ERA-BACKTEST-1 to the decimal —
  CBOperProf/small 1985-2001, gross t **5.23**, net t **4.30** at flat-25,
  deltas **0.00** on both.
- **V2 construction differential measured**, not hand-waved: the decile-breadth
  portfolio prints t 3.99 vs the scan's 4.30; the gap is weight drift + 269
  forced liquidations + fixed-N. Same signal at N=25 prints t 2.11 — breadth,
  not signal, explains most of it.
- **V3 known null:** turnover-matched random books print mean t −0.96 to −2.32
  vs their own universe (cost drag). No leakage.

## 2. PF-1 campaign — pre-registered, running

`TRIALS/PREREG_PF1_FACTORY.md`, sealed by commit before any registered compute.
Six strategies × 8 one-at-a-time configurations = 48 runs + 6 placebo bands
(100 draws each). Frozen decision rule: **net excess CAGR vs the CRSP VW
benchmark** as the primary metric; G1 ≥ +3%/yr, G4 placebo p95 as a hard gate,
G6 ex-best-year ≥ +1.5%, ≥4 of 5 evaluable regime blocks, G3 ≥6 of 8 grid
configs positive, G8 P(DD > 60%) ≤ 0.20. Verdict classes WINNER / UNRESOLVED /
FAILED, ranked by excess terminal wealth under the ruin constraint.

**Status at handoff:** Phase A running (`runs/PF/CAMPAIGN_PF1.json`, written
incrementally; log at `runs/PF/campaign_pf1.log`). First completed grid:

| PF-GP-SMALL config | net excess CAGR | t | window |
|---|---|---|---|
| base (small, N=25, monthly, flat25) | **+1.79%** | 1.39 | 40.2y |
| N=10 | +1.15% | 1.19 | 40.2y |
| N=50 | +2.43% | 1.68 | 40.2y |
| N=150 | +2.18% | 1.70 | 40.2y |
| quarterly | +2.52% | 1.67 | 40.2y |
| KO costs (2002+) | −0.89% | 0.42 | 21.0y |
| largemid | +0.79% | 1.16 | 59.5y |
| all | +1.03% | 1.33 | 59.5y |

Read it honestly: **7 of 8 positive, none material.** GP-small is real and
small — roughly +2%/yr before the placebo gate, not the +3% bar — and the base
config's bootstrapped **P(drawdown worse than 60%) is 0.56**, which is exactly
the kind of thing the ruin constraint exists to surface. Concentration (N=10)
made it worse on both axes.

**Two defects were caught by the harness failing loud, both fixed:**
1. The benchmark-hole guard fired on the leading formation month (FF starts
   1963-07). Fixed to require coverage over the scored window only.
2. The OSAP loader keyed its grid to the first strategy's column list, so
   PROF-COMPOSITE and ENGINE-ALPHA (which need new characteristics) failed all
   16 configs. Fixed to build the mapping once from the key columns and read
   each characteristic separately; **verified against an independent pivot,
   max abs difference 2.3e-7.**

## 3. "Can we force the LLM not to remember?" — measured, answered

Full receipts: `docs/AMNESIA_VERDICT_2026-08-08.md` (module repo). 1,080
DeepSeek calls, two pre-registered trials, every prompt and response cached.

- **The instruction does nothing.** With and without a strong "you are standing
  in {date}, do not use later knowledge" instruction, self-reported recall was
  **15.8% vs 15.8%** and Brier moved +0.0035 (the instructed arm slightly
  *worse*). Telling a model to forget changes what it says, not what it knows.
- **Masking works.** Across 240 masked/synthetic canaries the model identified
  the company **zero times** and never guessed a year.
- **Synthetic scenarios ≈ masked** (Brier gap 0.0004). Murat's "change the
  company names and dates" idea is now a *validated* instrument: we can
  generate unlimited scenarios from the 63-year panel that provably cannot be
  in any training corpus, and the model behaves the same on them.
- **Memory is real but sparse and self-selecting.** Asked outright, the model
  declined on 95.8% of cases — but on the 5 it answered it was **5 of 5
  correct**, every one a famous collapse (PYPL, CHK, GOEV, THQI, BTU). So a
  naive unmasked replay would produce a handful of spectacular calls that are
  pure memory, while the *aggregate* Brier barely moves (+0.007). **Therefore
  contamination must be gated per-case with canaries, never inferred from an
  aggregate score.**
- **Stated limitation:** on this task (12-month relative return from five
  percentiles) neither the LLM nor a logistic baseline has any skill —
  everything sits at the climatology Brier of 0.25. The task is retired for LLM
  evaluation; AMNESIA-2 moves to 5-day event-window reactions where the
  baseline bank has measurable signal.

## 4. The brain — Aegis Belief Network, built and running

`aegis_brain/abn/` implements the P2 design with the R1–R4 frozen parameters.

- **`core.py`** — claim schema (numeric anchor required for size claims,
  conjunction flag, per-claim window, external abstain reasons) and a
  **hash-chained ledger**: tamper-evident, write-once claims and resolutions,
  **outcome embargo** on retrieval (a resolution is invisible until its window
  has actually closed) and **ticker-blind retrieval** by default.
- **`posterior.py`** — two timescales: fast Beta hit-rates with a 75-resolution
  half-life, slow Normal effect sizes with **no decay** and BOCPD-style
  *partial* resets (ESS ×0.5, τ²×2). Correlated same-day resolutions are
  deflated (η = 1/DEFF, ρ=0.2). Per-cell effect estimates below n_eff 1000 are
  **refused** and fall back to pooled.
- **The architectural rule is a type check, not a comment:** `update()` accepts
  a `Resolution` and nothing else, so a P&L number cannot reach a belief.
  `ExposureBrake` gives P&L its only legitimate job — cutting exposure — with
  no write path back. There is a test named
  `test_pnl_cannot_write_a_belief`.
- **`calibration.py`** — fixed Platt α=√3 on log-odds, no extremization, clamp
  [0.02, 0.98], refuses to refit below 300 resolutions, and reports
  **selection-adjusted** calibration next to coverage.
- **`gate.py`** — lfdr-anchored promotion bar t ≈ 4.0 that **structurally
  refuses to promote retrospective evidence**: given `evidence_source=backtest`
  or `replay` it returns INSUFFICIENT with the reason, whatever the t-stat.

**End-to-end demo on real data** (`runs/ABN/abn_amnesia_demo.json`): the 480
amnesia forecasts became 480 claims → 465 resolutions → posteriors by market
context → calibration → gate. Chain verified. Embargo demonstrated (resolution
invisible one month in, visible after the window). Calibration earned its keep:
**ECE 0.076 → 0.029** on the named arm. The gate returned **INSUFFICIENT** with
three reasons, which is the correct answer.

## 5. What Murat needs to do

**Nothing is blocked on him tonight.** The standing sign-off list is unchanged
(GP lane flag, RISK-SAT-1 flag, per-winner seed flags, key rotation) and all of
them now wait on factory scorecards, per the frozen sequencing.

On his two optional items: the Kensho `spglobal-agent-skills` repo he linked is
a *skills* package, not a replacement for the failed MCP auth — worth wiring
only if we need S&P fundamentals we don't already have from WRDS/Compustat,
which we do have. **No spend needed.** Bigdata.com credits are likewise not
needed for the current work: the replay spine is SEC EDGAR + FDA + CRSP, all
free and all point-in-time. If a later event class needs tagged historical news
at scale, that is the moment to spend the $20, not now.

## 6. Next session picks up here

1. **Collect the campaign** — `runs/PF/CAMPAIGN_PF1.json` (verdicts land in
   Phase C). Write the campaign summary doc with the total experiment count as
   the multiple-testing denominator.
2. **PF-2 registration** — the breadth finding (N=150 beats N=25 on t for the
   same signal) and the KO-costs finding belong in the next grid, plus the
   combination phase (pairwise overlays among survivors, standalone / marginal
   / interaction contribution).
3. **AMNESIA-2** — 5-day event windows (earnings, PDUFA), masked, with the
   positive control and famous-case stratification built in from the start.
4. **N3 daily simulator** (G7) — the last gate before any strategy can reach a
   paper lane under the frozen standard.
5. The resurrection queue (si_chg_low, 22 largemid KO re-adjudications) is
   untouched and still first in line for research compute.
