# OPUS HANDOFF — Decision-Engine Research Phase (post-M1)
**Date:** 2026-08-05 · **Author:** Fable session (M1 completion run)
**Inputs reconciled here:** Murat's 2026-08-05 directive + three external AI
docs (GPT "decision engine", DeepSeek "consultant response", Gemini "H-1B
pipeline") + the M1 wave-1 measurement.
**House rule applied throughout:** nothing enters a design unchecked; every
external claim below carries a status. If it isn't pre-registered, it didn't
happen (CANON §6).

---

## 0. WHAT M1 JUST MEASURED (the evidence everything else builds on)

Wave 1 final, n=250/cell, I2-decaying, ρ_sig=0.5 (commit `79aa4da`, Aegis
module; tables in `runs/GATE-M1/stage3_tables.json`, sweep in
`threshold_sweep.json`):

- **FDR at α=0: 0/250** (Wilson ≤1.5%). The pipeline adopts no junk.
- **False-kill: 100% at every injected α** (0.2/0.4/0.6). Graduation rates
  0.4% / 2.0% / 6.4%; **zero confirm passes in 1,000 cells**; DSR/PBO never
  reached; cap_crowded_out 0.
- **Mechanism:** null decile book E[t_net] = **−0.91** (turnover cost drag);
  a TRUE α=0.4 edge averages t_net **−0.23** but t_ic **+1.67**. The
  t_net≥1.5 explore bar demands cost-beating proof the implementation cannot
  deliver even when the edge is real. Costs never touch rank-IC.
- **Counterfactual sweep:** IC-only gates transform the operating point:
  t_ic≥2.0 → FDR 0.8%, power 38% at α=0.4; t_ic≥1.5 → FDR 3.6%, power 59%.
  Loosening the joint gate maxes out at ~22% power. See sweep.py.
- **Posterior map NOT shipped** (pre-registered monotonicity gate caught a
  sparse-bucket violation). Re-estimate after recalibration, when evidence
  actually flows through the gates.
- Wave 2 (I1 constant / I3 small-only / I4 size-correlated) was still
  running at handoff — **read `runs/GATE-M1/stage3_tables.json` after the
  chain completes** for the full Tables 1-2 and regenerate exhibits. I1 is
  the cell that tests whether the confirm wall is a second independent
  killer for non-decaying edges.

## 1. DO NOT RELITIGATE (standing decisions)

1. Search phase CLOSED at 179 candidates. No new family runs until the Gate
   M recalibration is ratified — new signals below are FUTURE trials, to be
   pre-registered, not scanned ad hoc.
2. Paper lanes only; forward clocks are the only scorecard; no skill claims
   before 24 months; no real-money execution; real leverage: NO (paper
   sleeves may model it).
3. LLM narrates / engine computes. Every control-armed design carries a
   random-date placebo gate. Residualisation needs 3 receipts.
4. **No identity-based signals.** The diversity thesis proceeds via
   mechanism variables only (H-1B/LCA intensity, foreign-born inventor
   share, international board experience, network centrality, foreign
   sales). This is settled with Murat (2026-08-05): his hypothesis was
   always about networks and global talent, and the mechanism version is
   the stronger, testable form of it.
5. New scraped sources get PIT archival with capture timestamps FROM DAY
   ONE (the Google Trends autopsy: no PIT, no backtest, forever).

## 2. THE ONE DECISION THAT UNBLOCKS EVERYTHING (Murat-attended)

**Gate M recalibration proposal, evidence-based, awaiting ratification:**

- Explore gate becomes **information-gated**: t_ic ≥ 2.0 (headline
  candidate; 1.5 as the sensitivity), t_net demoted from gate to reported
  diagnostic.
- The cost hurdle moves to the **implementation/sizing layer**: turnover
  engineering (hold-band widths, rebalance frequency, netting across
  signals) + graded capital via the posterior sizing ladder (<60%→0×,
  60-70→0.25×, 70-80→0.5×, 80-90→0.75×, >90→1×).
- Confirm wall and DSR/PBO stay (they were never the binding constraint —
  they were never even reached).
- After ratification: re-run the M1 grid on the NEW gate (cheap — the same
  machinery, one overnight) so the recalibrated pipeline has its own
  measured FDR/power/posterior map BEFORE any new family runs.

All three external AIs independently endorsed this same move. It is also
the honest answer to Murat's "we falsely kill everything" worry: the fix is
measured, not vibes.

## 3. VERDICTS ON THE THREE EXTERNAL DOCS

### Adopt (consistent with our evidence and canon)
- **GPT:** decision-engine framing (signals + costs + uncertainty +
  reasoning → sized action); geometric-growth objective for the sizing
  layer; "learn what funds are discovering, don't copy holdings"; political
  exposure via contracts/lobbying/policy-support rather than trade-copying
  (matches our T11/congress findings: disclosed-trade copying is weak).
- **DeepSeek:** gate-on-IC + size-on-net (their §1 = our sweep); bull
  sleeve as a SEPARATE pre-registered paper lane rather than changing the
  defensive lanes; product phase after methodology is sealed; data-mining
  microservice with PIT stamps off-Railway.
- **Gemini:** LCA/H-1B data pipeline shape (DOL LCA ingest → entity
  resolution to tickers → intensity + occupational-exposure features →
  cross-sectional quintiles + event-CAAR risk layer). The PIPELINE is
  sound; its NUMBERS are not verified (below).

### Verify before design (claims that must be sourced or measured first)
- **Gemini's effect sizes are UNVERIFIED**: "8.78% higher annual abnormal
  returns top-vs-bottom quintile", "0.45% CAAR loss on visa restrictions".
  No checkable citation given. The H-1B literature is genuinely MIXED —
  Doran-Gelber-Isen (lottery-based) find modest firm-level effects;
  Dimmock-Huang-Weisbenner find entrepreneurship effects. First task of the
  labor program: literature verification pass with real citations, then
  pre-register with our own priors, NOT Gemini's numbers.
- **DeepSeek's "fix the foundation" list is partly STALE**: FRED
  publication lags were fixed (aegis-finance `bed{...}` C4 commit), the
  insider collector 403 was root-fixed in June (`_sec_get`), EVENT-INTEL
  prod-dead is a known backlog item. Opus session: check
  `aegis_verified_state` + recent commits BEFORE re-fixing anything.
- **GPT's "attention acceleration" model**: depends on the GDELT
  per-ticker stability canary (registered in the 2026-08-04 verdicts doc
  §6) — that canary must pass before any attention trial reads history.

### Reject (with reasons, so they stay rejected)
- Chasing 400%/yr exemplars as design targets (survivorship-selected
  outliers; distorts the engine toward ruin risk — GPT itself rejects this).
- Real leverage now (estimation error dominates; Bayesian-Kelly shrinkage
  says size DOWN under uncertainty; paper sleeves may model 1.2× to
  measure it).
- Ethnicity-as-category features in any form (see §1.4).
- Copying disclosed politician/fund trades as a primary signal (measured
  weak in-house; the *why* extraction is the adoptable part).
- DeepSeek's "raise daily_call_cap" as stated — spend guards exist for a
  reason; any cap change is its own attended decision with cost math.

## 4. THE RESEARCH PROGRAM (in order, each gated)

1. **Close M1**: wave 2 tables + final exhibits + the paper section
   ("operating characteristics of a strategy factory" — the FDR≈0 /
   false-kill≈100% result is publishable on its own).
2. **Ratify + re-run**: Gate M recalibration (§2) → overnight re-grid on
   the new gate → new posterior map (monotonicity gate again).
3. **LABOR-MOBILITY program** (the mechanism version of Murat's thesis):
   literature verification pass → DOL LCA ingest with PIT stamps → entity
   resolution → two features (H-1B intensity, occupational exposure) →
   pre-register ONE trial with OSAP cross-check and a placebo gate. BoardEx
   internationalization (foreign-experience share of board) rides the same
   pre-registration wave as a second arm.
4. **BOARDEX-CENTRALITY** (already certified data, 13-year clean OOS
   window, McLean-Pontiff design — both outcomes publishable).
5. **BULL-SLEEVE paper lane**: 200-day MA regime switch (Faber 2007) between
   aggressive momentum/attention book and conservative-atr; trailing stop;
   pre-registered decision rule; attended seed (Murat flips the flag).
   This is the honest answer to "we can't keep up with the bull."
6. **Decision-engine product phase** (after 1-2): daily portfolio advisor
   (position-level buy/hold/sell with reasoning + decision journal), chat
   via brain_query, watchlist from top signals, event-graph layer (market
   state → structural events → diffusion → sized action), data-mining
   microservice with PIT archival. Scope per DeepSeek's effort table;
   sequence per Murat's priorities.

## 5. OPERATIONAL NOTES FOR THE OPUS SESSION

- Grid machinery lives in `Aegis module/aegis_brain/calibration/` (venv
  `.venv\Scripts\python.exe`). Rep files are seeded + idempotent; resume by
  rerunning `scripts\run_m1_overnight.cmd [workers]`. 15 workers need
  ~18GB — on a daytime-loaded machine use 4-8. Machine must be LOCKED, not
  signed out, for overnight runs (a sign-out killed the first run).
- Process filters: spawn workers match `multiprocessing.spawn`, not the
  launcher name.
- Negative results already banked this run (do not re-derive): cross-segment
  scan reuse is invalid (segment-migration leak); v6 re-standardization
  c_t must stay deterministic (docstring in panel_gen.py); the posterior
  bucket likelihood is too sparse to ship at n=250 in the current-gate
  regime.
