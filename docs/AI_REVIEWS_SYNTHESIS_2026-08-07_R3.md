# AI Review Synthesis — round 3 (2026-08-07 night, RESEARCH_CHALLENGE responses)

Inputs: Gemini (corrected re-review), Gemini (new full report), DeepSeek,
and an Opus session with repository execution access. Every checkable claim
was verified against artifacts before adoption. Result: **the one-shot
replay is BLOCKED** (Kill Audit Amendment 3) — this round did exactly what
the challenge asked.

## 1. Per-review verdicts

### Opus (repo access) — VERIFIED; the most consequential review of the project to date

Every claim I could check, checked out:

| claim | verification |
|---|---|
| "FDR" = per-candidate FPR (select.py tracks only the injected candidate) | TRUE — structural reading of `evaluate()`/`select.rate()`, consistent with what our own kill audit §3 said without drawing the batch consequence |
| E[qualifiers/rep] on sim null = 4.54 vs top-5 cap; cap never bound (p_cap_crowded_out = 0) | recomputed from `family_null_tic_r1_frozen.json` + frozen tables: **4.54 exact** |
| Real bank: ~21-22 of ~67-70 largemid candidates clear t_ic ≥ 1.5; cap binds ~4:1 | recomputed: 21 of 70 distinct fresh (their 22/67 = dedup-rule difference, same substance) |
| Top-5 by t_ic contain zero σ-family members (veto inert) | recomputed: conc_low 4.46, tgt_upside_low 3.67, inst_persist_low 3.35, si_chg_low 3.11, comp_issue_5y 2.86; σ-family at ranks 11/13/17 |
| n_feasible = 1798 of 1800 ("decorative constraint") | TRUE in `brain009_frozen.json` (noting the constraint DID reject the top-power ladder — decorative is rhetorical, 1798/1800 is fact) |
| Confirm null pass measured on 4 events (2 adopt / 4 graduates) | TRUE in frozen held-out table2 |
| REAL-NULL-1: real-data persistent null P(t_ic ≥ 1.5) = 0.082 [0.0735, 0.0905] vs simulator 0.036 | artifacts located and read (`PREREG_REAL_NULL_1.md`, results JSON): pre-registration with declared mechanism/kill/prior written before compute; guard reproduced banked vol_12m_low 1.89 and price_level 2.12 exactly; φ-grid matches the reported table; **and it self-reports its declared mechanism as WRONG** (IC autocorrelation ≈ −0.01; the true channel is persistence-linked heteroskedasticity) — the exact discipline we demand of ourselves, demonstrated by a reviewer |
| I2 decay 9.2% recomputation | matches ours (claimed no novelty, correctly) |

Consequence: Kill Audit **Amendment 3** — replay blocked; REPLAY-2 must
pre-register batch-level error control, cap semantics, a correlation-
indexed (not lineage-indexed) veto or a restored calibrated gross leg,
real-data-based explore floor, and joint ladder+sizing calibration.

Its §2/§3 ideas adopted into the queue with credit: BH step-up on
empirical p-values from measured null CDFs (evaluate on existing bank);
correlation-surface veto with the R² ≥ 0.7 ship gate; calibrated
gross-money leg as a family axis; **the §28 exclusion-book conversion**
(universe-minus-bottom-decile ≈ 0.111 × mirror spread ⇒ ~16.7 bps/mo gross
long-only for io_level, with mandatory random-decile placebo gate); the
"Ruler Benchmark" paper (publish measured operating characteristics of
DSR/PBO/Harvey-Liu/BH/naive rules on a common panel — the citable
experiment); EDGAR as-filed restatement diagnostic; Rule 605 spreads for
the §25 KO-vs-CS dispute; USAspending with §31-style placebo; EDGAR log
attention conditioner (2003-2017, no-graduation clause); WRDS entitlement
audit (1 hour, closes a standing unknown); the `/api/null/t_ic` and
`/api/ledger` endpoints as the retention product.

### DeepSeek — VERIFIED, solid round; two adopted catches

- **Wilson conflation caught (real):** our brief quoted the n=125
  half-sample interval [0.44%, 5.65%] beside the n=250 point estimate;
  the correct n=250 interval is [0.62%, 4.04%]. Brief corrected; F6.
- **Sizing thresholds never jointly calibrated (real):** the 0×/0.25×/0.75×
  breakpoints were not part of the calibrated decision rule. Folded into
  REPLAY-2 (joint ladder+sizing registration).
- Regime-stratified FDR diagnostic: accepted as a *diagnostic* candidate
  (regime definitions pre-registered), not as an adoption rule yet.
- Hash-chained pre-registrations (OpenTimestamps): adopted to roadmap —
  cheap, and it converts "checked" into "impossible to fake."
- Its WORLD-8 sketch is weaker than the Opus jackpot-compensation design;
  the Opus construction (per-firm zero-mean by construction, monotone
  median via jackpot probability) is the one going into the WORLD-8 spec.
- Rejected: "run the replay under two thresholds" (already rejected round
  2 — breaks one-shot; the single output prints both columns instead).

### Gemini (corrected re-review) — ADEQUATE, little new

Grounded this time (BRAIN-008/009, DGP-A v6 all real). Its six §8 answers
land where rounds 1-2 landed; no new adoptions. Its closing question —
"how confident are you in DGP-A's fidelity for fat-tailed, non-stationary
vol clustering producing false rank-ICs?" — was answered *empirically* by
REAL-NULL-1 in the same round: not confident enough; measured 2.3×
optimistic for persistent candidates.

### Gemini (new full report) — DISCARDED; hallucination round 2

Describes "Aegis-Finance" as a ZetaChain/Internet-Computer DeFi platform
with Three.js spatial UI, reads "DGP" as *Dual-Granularity Prompting*,
re-derives our FDR 1.6% as a *UI-testing false-divergence target*, and
proposes zk-SNARK veto agents. It passed the letter of the §0 gate by
quoting "1.6%" and "0-for-179" while attaching them to fictional systems.
**Gate hardened (§3 below).** Nothing adopted.

## 2. Scoreboard of this round

The challenge asked reviewers to break the project. One reviewer broke the
replay design (five verified defects), one caught a real statistical
presentation error plus an uncalibrated sizing rule, one was adequate, one
reviewed a fictional project twice. Net effect on the project: the most
valuable single review round so far — and the strongest evidence yet for
the standing rule that **review quality is bimodal and verification is
not optional.**

## 3. Proof-of-reading gate, hardened (supersedes §0 of the challenge)

1. Three verbatim quotes that `grep` finds in our files, cited file+line.
2. One recomputation **from stated inputs** that we can re-run.
3. Any architecture claim must cite a file path that exists in the repo;
   one nonexistent path invalidates the review's project-specific content.
4. Reviews with execution access must ship their pre-registration file,
   code, and result artifacts — we located and re-read all three for
   REAL-NULL-1 before believing a number.

## 4. What happens next (order is load-bearing)

1. Wave 3 completes → score BRAIN-010 E1–E3 exactly as registered
   (simulator-null statements, now carrying F4's conditional language).
2. Write and pre-register **REPLAY-2** (Amendment 3 requirements). The
   candidate error-control designs are evaluated on the EXISTING bank +
   REAL-NULL-1 machinery — no new grid nights needed.
3. Run the R² correlation-surface diagnostic (20 min) to settle the veto
   index before REPLAY-2 freezes.
4. Only then: the one-shot replay, with expected-false-adoption accounting
   printed at the top of its output.
