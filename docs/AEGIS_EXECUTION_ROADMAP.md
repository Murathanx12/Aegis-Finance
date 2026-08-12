# AEGIS EXECUTION ROADMAP — BACKTEST + IMPLEMENTATION

> **2026-08-12 — SEQUENCING SUPERSEDED FOR THE LLM/LEARNING ARC.**
> `ROADMAP_LEARNING_LOOP_2026-08-12.md` carries the current ordering and
> dependency graph. **The standards in THIS document still bind** — the Gate
> D/M certification logic, the discovery bar, the posterior sizing ladder and
> the objective function are unchanged and are not up for renegotiation because
> a newer document is more exciting. What changed is only what gets built next
> and in what order.

**Date:** 2026-08-03 · **Supersedes** the §4 ordering in `AI_REVIEWS_SYNTHESIS_2026-08-03.md` (same content, now gated)
**Design constraint (Murat):** we cannot afford to test for months and then discover the data or the method was bad.
**Design answer:** *certify before you spend.* Three certification gates run FIRST, each takes days and has a pre-registered kill criterion. Nothing downstream starts until its gate is green. A bad foundation costs at most one week, never a quarter.

**Source credit:** merges the GPT decision-theory review (2026-08-03), the Gemini response (note: Gemini largely restates our own dossier — treated as a consistency check, not independent evidence), the five earlier AI reviews, and our own backlog.

---

## THE DECISION THAT RESOLVES THE CONFIDENCE DEBATE

GPT's separation is correct and we adopt it formally:

- **Question A — "should we accept weaker evidence that an edge EXISTS?" → NO.** The discovery bar stays at the t≥3 class (Harvey-Sancetta-Zhao 2026 defended this against the low-hurdle literature; our own registry defect is a live example of why the unpublished-trial iceberg matters).
- **Question B — "should capital scale with confidence instead of binary in/out?" → YES.** Adopt the **posterior sizing ladder**: <60% posterior → 0×; 60–70% → 0.25×; 70–80% → 0.5×; 80–90% → 0.75×; >90% → 1.0×; hard cap 1.25× (inside the half-Kelly book ceiling). Confidence changes *size*, never *whether the idea exists in the book*.
- The posterior itself must be **calibrated, not vibes** — that's what Gate M produces (the factory calibration maps "our pipeline said X" → "probability it's real"). Until Gate M is done, the ladder cannot be used honestly. This is why method certification precedes trading logic.
- **Objective function** (already agreed, now official): expected log wealth under estimation uncertainty — g = μ − σ²/2, fractional Kelly ≤ half, systematic risk through a 40–70 name book, idiosyncratic concentration rejected (the mirror lane's −22% at β≈1 is the house receipt).
- GPT's "all 179 get continuous capital monthly" version is **rejected as scope creep**: it multiplies implementation surface by 60× for tail positions of 0.1%. The ladder applies to *qualified* candidates (survivors + new-family graduates). Revisit at real-money scale.

---

## GATE D — DATA CERTIFICATION (Days 1–4; kills in hours)

The insurance against "the data was bad." Every dataset must reproduce a *known answer* before any novel test touches it.

| # | Check | Kill criterion (pre-registered) |
|---|---|---|
| D1 | **Pull verification** (tonight): row counts vs source, no `!! MISMATCH`, chunk-sum = 17,197,215, `boardid`/`directorid` cardinality ≫ the truncated era's 3,240, date ranges span 1999→2026 | Any table failing → re-pull that table before it is ever read |
| D2 | **PIT linkage certification**: BoardEx→CRSP via cikcode→permno + ticker-through-`stocknames` (namedt/nameenddt); exclude/lag-pad rows with imputed-date flags (`datestartroleflag`); `"Curr"` string banned at parse time (assert it never survives ingestion) | Linked coverage < ~70% of CRSP market cap → STOP, fix linkage; do not build signals on a half-linked graph |
| D3 | **Known-result replication on the new stack** — the critical anti-restart test: (a) gross-profitability decile spread on CRSP/Compustat must reproduce the Chen-Zimmermann/French published pattern (sign, monotonicity, magnitude ±50%); (b) small-cap decile returns WITH vs WITHOUT `dsedelist` must show the documented delisting-bias gap; (c) one known BoardEx descriptive fact (board-size distribution / network density growth) must match published figures | Any replication fails → the pipeline is broken **today**, at a cost of 2 days — this is precisely the failure that would otherwise surface after 3 months of signal work |
| D4 | **IBES sanity**: `numest` coverage counts vs known aggregate analyst-coverage time series; `statpers` monotone; no future `fpedats` leakage | Fails → IBES ingestion quarantined; NEGLECT-QUALITY blocked, others proceed |

## GATE M — METHOD CERTIFICATION (Days 3–14; overlaps Gate D)

The insurance against "the method was bad." Certifies the judge before the trials.

| # | Check | Kill criterion / output |
|---|---|---|
| M1 | **Factory Calibration Monte Carlo**: synthetic panels, injected alpha ∈ {0, 0.2, 0.4, 0.6}, run the UNCHANGED pipeline (explore/confirm + placebo gate + DSR) ≥1k reps per level. Design: `GATE_M1_FACTORY_CALIBRATION_DESIGN.md` (DGP-A factor-residual — block-bootstrap-with-relabel is NOT a null, firms keep their own momentum). Harness calls `scan_signal` directly — `run_batch` swallows scan crashes into months=0 rows (explore.py:158), which under calibration would count crashes as kills and inflate false-kill | Outputs the two numbers we've never had: false-discovery rate at α=0 and **false-kill rate** at each real α. If false-kill at α=0.4 > ~50% → recalibrate gates BEFORE any new family runs. Also outputs the evidence→posterior mapping that powers the sizing ladder |
| M2 | **Permutation placebo standard** (spec registered 2026-08-04, verdicts doc §3): permute event dates ACROSS firms, calendar marginal preserved; **B = 5,000**; p = (1 + #{stat_perm ≥ stat_real}) / (B+1). Under this p there is **no pooling step** — the §29-31 F1 pooling error is structurally unexpressible and "seed-level vs pooled" is no longer a post-hoc choice. Then re-read §30/§31 | Gate flips under the registered spec → reopen 13D; else closure stands with a clean receipt |
| M3 | **The 179 machine ledger** (E2) → empirical σ_SR (E1) → survivors deflated at N=179 and family-clustered effective N (E3), SPA + Romano-Wolf jointly. **E1 rule: σ²_SR = max(empirical, 0.01), report both** — our kills happen before a return series exists, so observed dispersion is left-truncated and the empirical value (≈0.0056) would LOOSEN the gate vs the 0.01 default (adoption.py:25). Also audit: `evaluate_candidate` without a `perf_matrix` returns pbo=None and can never ADOPT — verify the production survivors were actually evaluated with one | Survivor failing at effective N → demoted to "unfunded hypothesis" (still tracked, 0× on the ladder) |
| M4 | **C4 FRED publication-lag fix + walk-forward re-run**; C5 real assertions; C6 absent≠zero; C7 purged-CV repair (`aegis_prepare` TypeError + raise on `eval_times=None`); full-sample-fit audit (scalers/feature-selection fitted across the explore/confirm wall) | The AUC/Brier delta is a paper exhibit either way; any full-sample fit found → re-run affected explore results |
| M5 | ⚑ Contamination decision (insider/smartgrowth clocks) → C2/C3 collector fixes + entropy/coverage canaries with auto-halt | Recommendation stands: restart the two clocks |

## STAGE T — THE TESTS (Weeks 3–8; each time-boxed to 2 weeks, pre-registered, explore→confirm read ONCE)

Priority order = expected ROI per week. Every trial carries: permutation placebo (M2 spec), placebo battery where events exist (random-ticker / +180d future-event / +90d lag / sector-matched), KO cost model, borrow-fee & short-eligibility screen, long-only sleeve reported separately, buy/hold band implementation (enter ≤ rank 40, exit > rank 80).

| # | Trial | Data | Null hypothesis | Kill criterion |
|---|---|---|---|---|
| T1 | **INSIDER-CLUSTER** — clustered opportunistic buys by *connected* directors (across firms, ≤40-day window) vs isolated buys | Form 4 × BoardEx network (Gate D2) | Cluster buys ≤ isolated buys after size/BM/mom controls | Fails placebo battery or spread lives in untradeable names → ledger |
| T2 | **DIRECTOR-DEPARTURE screen** — ≥2 independent-director exits within 90 days as a long-only *avoidance* rule | `dir_profile_all` role end-dates (date-flag screened) | Departure-flagged names perform no worse | Avoidance saves < costs of the screen → ledger. NOTE: short-leg problem does not apply — we simply don't hold |
| T3 | **NEGLECT-QUALITY** — GP × ChNAnalyst (coverage *decline*; level is an OSAP placebo), long-only top-50 sleeves | Compustat GP + IBES numest (Gate D4) | Interaction ≤ GP and ChNAnalyst separately | Already in OSAP with documented decay → stop before building; alpha only in microcaps → reclassify |
| T4 | **ATTENTION-ACCELERATION EXIT** — reduce exposure when attention *acceleration* peaks; tested head-to-head vs ATR Chandelier trailing stop (current incumbent) | **GDELT per-ticker counts ONLY** — Trends leg dropped (2026-08-04 audit: SVI never archived, renormalized/repainted, not PIT). Prereq: GDELT stability canary (same historical window queried twice ≥2wk apart) | Acceleration exit ≤ trailing stop net | Canary shows GDELT drift → T4 needs forward accrual, postpone. Loses to the trailing stop → keep the stop, ledger the idea. (Peak *prediction* stays banned — §1's 28.6% hit rate) |
| T5 | **INSTITUTIONAL-ATTENTION MISMATCH** — retail attention ↑ while institutional ownership ↓ (and the quiet-accumulation mirror) | TFN 13F (entitled — recon first) × **GDELT counts** (same canary prereq as T4; Trends not PIT) | Divergence predicts nothing beyond momentum/size | 13F staleness kills PIT validity → ledger. Target = future *vol* first, returns second |
| T6 | **BOARDEX-CENTRALITY** — Larcker-So-Wang 2013 (JAE) board-centrality premium, 4.68%/yr risk-adjusted in-sample. Upgraded 2026-08-04: **13-year post-publication OOS window with no known replication** — this is an explicit OOS replication test where BOTH outcomes are publishable | BoardEx network (Gate D2 link) | Centrality premium = 0 post-2013 | No kill-to-ledger asymmetry: decay confirmed = a publishable McLean-Pontiff datapoint; survival = a tradable candidate |

**Measurement studies (no trial clock, no capital implications):** lead-lag diffusion on the network (does an earnings surprise at A rerate connected firms with a measurable lag? — if yes, THEN register a trial); executive-reputation sample-size check (how many multi-firm CEO moves exist post-linkage? — if <300 usable events, the idea is unmeasurable, say so and stop).
**Deferred (new data collection required):** Narrative Diffusion Index (multi-community attention) — good idea, wrong quarter.
**Permanently rejected:** demographic/ethnic screens (measure political closeness DIRECTLY: lobbying spend, PAC contributions, federal contracts, revolving-door hires — all free public data, all already in the political-access design); copy-13F (GURU's record is the receipt); copy-congress (Belmont null; leadership-conditioned version may enter a later batch); peak prediction.

## STAGE I — IMPLEMENTATION (Weeks 6–10, overlapping Stage T)

| # | Item | Note |
|---|---|---|
| I1 | **Decision engine v1**: posterior ladder (calibrated by M1) + g-objective + half-Kelly book cap + 4% position caps + buy/hold bands + borrow-fee screen | The engine outlives any strategy — GPT's "best decision engine, not best strategy" is now the architecture principle |
| I2 | ⚑ New paper lanes for T-graduates via `seed-a-lane` (env-gated, human flips flags); lane-path fixes ship as **new config version → segment boundary** (D/D−1 fill, cost-basis marking) | Bug-marking policy per 2026-08-02 agreement |
| I3 | **LLM extractor** (structured-context spec): enum/count outputs only, entity names stripped (Glasserman-Lin distraction effect), verbatim span citation, temperature 0, hand-labeled validation set before any feature ships; DeepSeek budget $20/mo | "Structured context, not narratives." EVENT-INTEL gets a scheduler job or gets deleted — no more prod-dead subsystems |
| I4 | **Leverage: not now.** Sequence fixed: research process validated (M1) → live process validated (2 clean quarters of lanes) → fractional-Kelly sizing → only then modest leverage if the edge is stable | GPT sequence adopted verbatim |
| I5 | ⚑ Paper drafting in parallel (no dependency): survival curve of 179 + factory calibration + placebo operating characteristics + leak-correction deltas. Internal rename adopted: **Market Intelligence** — "who knows what, when, how it spreads, what's ignored, how confident to act" | SSRN timestamp, then arXiv via HKU |

## THE FAILURE-COST TABLE (why this can't cost months)

| If this is broken… | …we find out | Cost |
|---|---|---|
| WRDS pull corrupted | tonight (D1) | hours |
| BoardEx linkage unusable | day 2–3 (D2) | 2 days |
| CRSP/Compustat pipeline wrong | day 3–4 (D3 replication fails) | 3 days |
| Placebo gate miscalibrated | week 2 (M1) | 2 weeks, and every later test inherits the fix |
| A signal idea is dead | its own 2-week box (T kill criteria) | 2 weeks, ledgered, next test starts |
| Survivors were luck | week 2 (M3 at effective N) | 0 wasted forward capital — ladder sets them to 0× |

⚑ = attended (Murat): contamination decision (M5), lane seeding (I2), paper unparking (I5), mirror/conviction cap (standing), TSMOM rebalance verification (standing).
