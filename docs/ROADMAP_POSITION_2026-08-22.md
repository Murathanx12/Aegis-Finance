# ROADMAP POSITION — 2026-08-22 (the training gate opened, and told the truth)

Successor to `docs/ROADMAP_POSITION_2026-08-21.md`. Covers the ORDER 28
adjudication and the two sessions that executed it. HEAD at writing:
`0786731`; all receipts referenced live in `backend/data/optimus/aegis_panel/`
and `backend/data/optimus/wrds/`.

## WHAT AEGIS LEARNED FROM 45+ GB THAT IT COULD NOT KNOW YESTERDAY

1. **The characteristics do not rank returns at this scale and era.** 412
   JKP characteristics vs the 7-feature price floor, LGBM, 2016–2024,
   230,640 PIT stock-months with delistings: paired dIC **−0.0025** (MDE
   0.021), full-arm pooled IC **−0.0007**. Registered
   (RETURN-PANEL-TOURNAMENT-1), null-world-first, §64-audited.
2. **…and the instrument itself can only see large signals.** Planted
   sensitivity worlds (a factor of IC 0.03, sparse AND dense) are
   recovered at dIC +0.001..+0.003 — the arithmetic (R² ~0.001 vs 419
   features on ~10⁵ rows) makes the tournament blind at realistic effect
   sizes. **The null above bounds only unrealistically large signals.**
   The panels where supervised return ML demonstrably resolves
   (GKX-class) are ~100× ours: all caps, 60 years. Scale is the
   successor instrument, and it is one named-consumer pull (in flight).
3. **The one family with a pulse is risk, and it is era-bound.**
   RISK_PRICE alone: +0.0157 IC modern (and +0.0299 with own-construction
   features — above that cell's MDE, still SCREEN) — while 1994–2012,
   same definitions, gives a **tight zero** (−0.0005, SE 0.0051, 215
   dates). Registered (RISK-PRICE-EARLY-1, TRANSFER). If real, it is a
   2016–2024 regime fact. Licensed follow-up: the SAME-ERA foreign
   cross-section confirm — never another US backtest.
4. **The panel and its stamping are sound.** JKP PIT spot-audit PASS
   (2,479 accounting-change events: the 4-month availability rule holds
   exactly; 3 late-filer edge cases are JKP's own uniform rule; 0 genuine
   lookahead). Label agrees with JKP's independent construction at corr
   0.99987. Vol cross-check 0.744→0.779 restates RISK-HEAD-AT-SCALE-1
   through the new join.
5. **Model ordering on returns: nothing.** ridge ≈ LGBM ≈ 0; MLP the only
   arm touching the bar (+0.0100, inside noise); **LambdaRank actively
   hurts** (−0.0405). The risk head remains LGBM (unchanged, both eras).

## ACCEPTED from ORDER 28 (executed)

Substrate receipt (§1) · canonical panel as a JOIN (§2) · labels declared
before tuning (§3) · null + sensitivity worlds (§5, extended beyond the
order) · economic promotion standard (§6 — already canon, restated) ·
staged sequencing: NN/Transformer only after baselines (§10–11) ·
allocator/router gating (§13–14) · "don't wait" (§15).

## REJECTED / CORRECTED from ORDER 28

"Build MODEL_TOURNAMENT_V1" — it existed; we registered a successor on
the frozen machinery instead · "no data problems" — semantics remain, owned
by named consumers · LLM factorial — already registered as ABLATION-1 with
contamination discipline · unsupervised challengers now — corpse-checked
(MP-denoising hurts; latents must beat raw features), deferred behind the
supervised baseline · CatBoost/XGB/Transformer arms now — deferred by the
order's own logic · new validation framework — reuse, not reinvent.

## VERDICTS REGISTERED TODAY (all receipts committed)

| trial | verdict | scope note |
|---|---|---|
| RETURN-PANEL-TOURNAMENT-1 primary | NOT_ESTABLISHED (dIC −0.0025, MDE 0.021) | bounds only signals ≫ realistic scale (see calibration annotation) |
| — null world | clean (no win on noise) | also caught the prereg's own verdict-literal bug pre-run |
| — sensitivity worlds | instrument blind ≤ planted 0.03 | TOURNAMENT-2 must show planted detectability BEFORE its registered run counts |
| RISK-PRICE-EARLY-1 primary (1994–2012) | NOT_ESTABLISHED, point ≈ 0 (−0.0005 ± 0.0051) | the modern lead did not transfer |
| — modern consistency cell | +0.0299 (MDE 0.0248), SCREEN | own-construction reproduces the JKP lead; the ERA is the difference |

Portfolio stage: **UNLICENSED** (correctly — no IC survived).
Demonstrated edge: **still 0%.** The risk product remains the validated
asset; the return question now has honest instruments and honest nulls.

## HARDENING SHIPPED (fragility audit on the new modules)

A failed JKP join REFUSES (all-NaN full arm would run as "no signal") ·
screen-cache entries carry the panel hash (claimed delete-on-rebuild never
existed) · substrate-receipt families that glob zero files REFUSE · two
guard-contract enrollments (the contract caught its own author twice in
one day — working as designed) · resumable screen stage (background shells
die at ~10 min; bounded runs converge).

## IN FLIGHT

`scripts/wrds_pull_jkp_full.py` (detached loop, log-monitored): USA JKP
1926–2012 all columns (consumer **AEGIS-PANEL-2**) + 13 developed markets
2013–2024 risk-family subset (consumer **RISK-PRICE-FOREIGN-CONFIRM-1**).
Completion census appended below when it lands.

**PAUSED by Murat 2026-08-22 ~21:40 HKT at 16/45 chunks** (USA complete
through 1980-81; foreign not started). Fully resumable — chunk filenames
are the resume key; the panel-2 builder REFUSES until the plan is
complete. To resume: relaunch the two detached loops
(`jkp_full/pull_loop.ps1` for USA ~6 h remaining;
`jkp_full/pull_foreign.ps1` for the ~1 h foreign subset) or invoke
`python -m scripts.wrds_pull_jkp_full` repeatedly.

## NEXT SESSIONS (ordered)

1. **Verify the JKP chunks** (row sanity, no at-cap fills, meta audit) and
   extend TRAINING_SUBSTRATE receipt to v1.1 with the new families.
2. **AEGIS-PANEL-2**: full-history all-cap US panel (~3M stock-months,
   1926/1963–2024), delistings, floor features recomputed full-history.
3. **Planted-world detectability gate at panel-2 scale** — the declared
   precondition: no TOURNAMENT-2 registered run counts until the
   instrument demonstrably recovers its declared effect size in synthetic
   worlds (including a heteroskedastic-noise world, which is the right
   place to test the z-label training variant that today's homoskedastic
   worlds could not).
4. **RETURN-PANEL-TOURNAMENT-2** registration + run on panel-2.
5. **RISK-PRICE-FOREIGN-CONFIRM-1** registration + run (13 countries,
   same era, §64 from measured foreign n).
6. **ORDER 27 carry-overs, unchanged:** why_moved day-guard then retry
   slots · G1 correlated-worlds battery before router capital authority ·
   P9 alpha-diversity books (gated on a surviving signal — none yet) ·
   PROFIT_ALLOCATOR_v2 (gated on true OOS forecasts) · EVENT_IMPACT
   bridge · diffusion baselines behind their corpse check.
7. **Murat's calendar (his keyboard only):** 08-27 resolve run · 09-08 G2
   lane-flag flips (design SIGNED+FROZEN) · weekday 16:55–17:05 laptop
   window for IIF · Monday: arena fills first positions; first bar-dated
   NAV rows under P-day-2026-08-19a semantics.

## ADDENDUM — same day, second session (while the JKP pull runs)

Two queue items moved from "declared" to "enforced", both ungated by the
pull; fast suite 5,322/0 (+19 tests):

1. **The planted-world detectability gate now EXISTS as code**
   (`backend/services/detectability_gate.py`, next-sessions item 3).
   TOURNAMENT-1 wrote sensitivity receipts that NOTHING read — a
   TOURNAMENT-2 could have been registered over a demonstrably blind
   instrument with the blindness receipt sitting next to its panel.
   `assert_detectable(receipt_dir, panel_hash=…, declared_ic=…,
   min_recovery=…)` refuses on a missing receipt, a foreign panel_hash
   (panel-1 evidence licenses nothing about panel-2), a planted effect
   larger than the declared one, or failed recovery (best full-arm mean ≥
   min_recovery × planted IC AND ci_lo > 0, per world, hetero world
   required by name). `declared_ic`/`min_recovery` have NO defaults — the
   TOURNAMENT-2 prereg declares them. A live pin test asserts the shipped
   panel-1 receipts FAIL the gate at their own hash (the true state); if
   that test ever passes green-side-up, the gate has inverted. Enrolled in
   the guard contract (`DetectabilityRefused`). **The TOURNAMENT-2 runner
   must call `assert_detectable` before its registered run counts — this
   is now buildable as a refusal, not a memory.**
2. **why_moved day-guard + catch-up retries SHIPPED** (ORDER 27 carry-over,
   item 6, and it was urgent: the TypeError fix landed this morning and
   2026-08-22 IS a Saturday — TONIGHT's 17:15 firing would have been the
   first weekend run to walk back to Friday and mint Friday's records a
   SECOND time. Verified live post-deploy: pi_why_moved's next run moved
   from 2026-08-22T17:15 to 2026-08-24T17:15 ET). The trigger is
   now mon-fri 17:15/18:15/19:15 ET (the arena/MTM restart-resilience
   pattern); retries are idempotent via `skip_if_minted`, which derives
   from the ledger itself. That required making the ledger able to answer
   "was this session already minted?" — the snapshot carrying `as_of` is
   stored only as a hash — so **belief-state schema 1.3.0** adds
   `session_as_of` (optional, purely additive, the session a record is
   ABOUT vs `made_at` = when written), stamped by why_moved's mint path.
   Pre-1.3.0 records carry None and never match: the worst that buys is
   one legitimate re-ask of a pre-stamp day, never a suppressed first ask.

Also this session: `DESIGN_REVIEW_2026-08-22_NEWS_ENGINE_AND_RULES.md`
stands as the ORDER 29 candidate (event store → sensor → playbook loops;
ingestion-24/7, decisions event-conditional, trading NOT continuous) and
the rules audit awaiting Murat's read; the optimus MCP `brain_query` tool
is erroring server-side (a path-repetition bug in the aegis-health page
name — optimus repo, not this one); prediction-ledger quarantine (25
overdue campaign copies) remains the standing attended item degrading
health.

## THE POSITION IN ONE PARAGRAPH

The acquisition phase is closed with receipts, the canonical panel exists
and is PIT-verified, and the supervised return question has been asked
properly twice — both answers are nulls, and for the first time the
programme can say exactly *how much* null they are: the instrument sees
nothing because at this scale nothing of realistic size is visible. The
risk result keeps replicating through every new join. The road forward is
not a cleverer model; it is the ~100× panel now downloading, a
detectability gate that must pass before any new verdict is read, and a
same-era foreign confirm for the one era-bound lead. Everything else —
books, allocator, router authority — stays correctly gated behind a
signal that has not yet earned it.
