# BUILD — CONTINUATION b, 2026-09-05/06 (Opus 5 coordinating five agents)

Mandate `docs/CONTINUATION_2026-09-06b_OPUS_PROMPT.md`, acting on
`REVIEW_2026-09-06_FABLE51_ON_THE_CONTINUATION.md`. **Nothing pushed, sealed,
ordered, deployed or changed on Railway. LLM spend $0.00.** Every number has a
receipt under `backend/data/optimus/continuation_2026-09-06b/`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE — and the comparison ladder just got shorter.**

| KPI | This session |
|---|---|
| Best historical net strategy vs the market | **worse than reported.** Beta-matched, `lgbm_clf` is **+1.13%/yr t 0.349** (10 bps) and **−2.07%/yr** (25 bps); `lgbm_raw` +2.33% / −0.80%; `nn_pre_causal` +3.95% t 1.095 / +1.05% t 0.292. Three of six books lose to their own leverage on terminal wealth |
| Best forward paper strategy | none. Books flat by design; hack3/4/6 dry-run only |
| Independent selector count | **1 trading + 1 SHADOW** (`nn_pre_causal`, zero capital, accruing from 2026-09-05) |
| Farm candidates tested / promoted | **0 / 0** — this was a re-grade session, not a search |
| New actionable finding | **the incumbents' excess is a LOADING, not an intercept.** `lgbm_clf` β **1.1782**, t(β−1) 2.03 HAC; `nn_pre_causal` β **1.3294**, t(β−1) 4.24. The +8.14%/yr at t 2.243 that W3b reported was 1.33× market |
| External execution drag | not measured — no orders, no seals, no deploys |
| LLM spend / cost per gradeable output | **$0.00 / $0.00.** Zero API calls, zero network. Every item was arithmetic on data already on disk |

**Fast suite (final, exit 0): `6766 passed, 14 skipped, 122 deselected` in
427.05 s** (from 6,655 / 14 at session start). Terminal repo: **76 suites,
3,503 checks, ALL PASS** (from 76 / 3,483). **8 local commits** here, **1** in
the terminal repo. Nothing pushed.

## THE ONE-SENTENCE ANSWER TO ITEM 1

> **A LOADING.** `lgbm_clf`'s +3.393%/yr (t 1.225) against the raw VW market is
> +1.126%/yr at **t 0.349** against its own beta-matched leg (β 1.1782, t(β−1)
> 2.03 HAC) and **−2.074%/yr at 25 bps**; the 8-seed `nn_pre_causal` ensemble is
> the same shape and not the opposite — β 1.3294, t(β−1) 4.24, its t 2.243
> becoming t 1.095 — so every "beats/loses to lgbm" sentence in this repo is
> still fine as a *relative* statement and no absolute one survives the ruler.

The re-stage passed a **reproduction gate before anything was computed**: the
W3b stage parquets were gone, the fit was redone (universe fingerprint
`616fa0a5…` matches), and all six graded cells reproduce every field of W3b's
`cells` block exactly. `rf` is compounded over each book month's **own** holding
window — the row labelled `2020-02` is the book entered 2020-02-21 and held into
the −33.3% March, and a calendar-month rf would have been the wrong leg while
`benchmark.beta_matched` silently `fillna(0)`'d it.

**Fable's claim 5 reproduces.** 20,000 draws at each series' own realised
moments: `lgbm_clf`'s 0.8355 top-5 share is exceeded by **27.1%** of normal and
**35.5%** of t₄ draws (30.5% / 39.7% conditional on a positive total) — Fable's
31%/40%. Under the beta-matched leg the share stops being a share at all for
both LightGBM books (2.07 and 1.82; both go negative without their top five).
`nn_pre_causal` does not (0.457).

**The caveat that survives:** `nn_pre_causal`'s residual alpha is positive at
both cost rates and in all three eras (+0.10 / +0.10 / +0.63 %/mo) but at t
1.095 with MDE 6.86%/yr against a 3.95% effect it is **UNDERPOWERED, not
NOISE**. 251 months cannot separate it from zero.

## THE SHADOW-BOOK REGISTRATION (item 2)

`neural_pre_causal_ensemble_v1`, **evidence grade `SHADOW`**, role PICKER,
`allowed_in_pm: false`, `first_grade_date: 2026-09-05`, contract
`nn_pre_causal_shadow_v1` sha `16e7d4390686d4d0…`, rule hash `428a7148…`.

What is frozen is the **recipe, not a model file**: `run_neural` produces
walk-forward OOS predictions over 21 folds, so there is no single object to
persist and persisting the last fold would be a different experiment. The eight
seeds, every hyperparameter (snapshotted **by value**), the pre-training scope,
the $3m/day + $5 floor on the *training* universe, the seed-mean object judged,
the book and the grader are hashed. `verify_contract()` compares
`learner.neural_long`'s **live** constants against the frozen ones — a module
edit leaves the contract file byte-identical while changing what it means.

Cadence: **book monthly, receipt nightly.** It cannot be scored on the tracker
day file at all (14 mappable features vs 50 read), so a night with no new month
writes a heartbeat. Tonight's first receipt is `PENDING_ARTEFACT` and names the
command that produces the first book, so the gate can go green.

`SHADOW` carries three refusals, **all proved red**: no `first_grade_date`, no
`contract_sha256`, or `allowed_in_pm: true`. It is deliberately **not** in
`NEVER_PICKS` — a shadow is alive, and grouping it with the corpses makes the
graduation queue and the graveyard the same list.

*Incidental, not caused here:* **`lgbm_clf`'s daily shadow is REFUSED** — schema
hash mismatch (sealed `fd48dbc7`, current `7f01cbe4`). Coverage is fine at
2947/3056; the champion is stale. Retraining is attended and was not done.

## THE CORRECTED PRICE CONSTANT (item 3)

`LLM_PRICE_PER_MTOK["deepseek-v4-flash"]` (and its two aliases) moves from
`{in 0.14, out 0.28}` to **`{in 0.169413, out 1.284835}`** — derived from the
provider balance, never from telemetry. `LLM_PRICE_AS_OF = "2026-09-05"`;
`LLM_PRICE_DERIVATION` records the whole derivation machine-readably.

**A scalar multiple is refuted, and that is the finding.** Two balance windows
solved as a 2×2 (condition number 2.58): W1 needs **3.61×** the old table and W2
**1.81×** — so the **shape** was wrong, not the level. S4's "1.79–1.81×" was the
25-minute window read alone. Per leg: input **1.21×**, output **4.59×**.

**Table-wrong vs ledger-incomplete:** the gap is proportional to *output tokens*
(per-window spread 1.24×), not to calls (3.95×) or input tokens (9.11×) — and
missing ledger rows lose whole calls, which would look constant per call.
Verdict `TABLE_IS_WRONG_OUTPUT_LEG`. `cached_in` and `deepseek-v4-pro` are
**scaled, not measured**, and say so; the Anthropic rows are untouched.
Historical `llm_calls.jsonl` rows keep their historical price — repairing a
tamper-evident record is the tampering.

## THE HOLD-ARM TABLE (item 4)

Cache-only re-grade, 768/768 decisions recovered, **zero wire calls**. The
no-hold re-grade reproduces the sealed L10 receipt identically on all four arms.

| cell | turnover | net %/mo | t (48 blocks) | null-1 p |
|---|---|---|---|---|
| fantasy_nodiary (± hold) | 0.9965 | −0.3927 | −1.050 | 0.7205 |
| fantasy_diary | 1.0000 | −0.1269 | −0.348 | 0.4105 |
| fantasy_diary \| hold | 0.9983 | **−0.0676** | −0.179 | 0.3430 |
| realanon_nodiary (± hold) | 0.9983 | −0.3530 | −0.996 | 0.6835 |
| realanon_diary (± hold) | 0.9983 | −0.5301 | −1.385 | 0.8530 |

Family 8: family-min p 0.173, **family-max 0.859, nothing survives BH-FDR**
(adjusted ≥ 0.432), SPA p 1.0, PBO 0.286, DSR 0.0024–0.0507, MDE 8.50–9.19%/yr.
Three-era table **CANNOT DETERMINE BY CONSTRUCTION** (2016-19 only).

**The review's instruction was right and its diagnosis was wrong.** Turnover is
~1.0 not because the decider rebuilds the top-k but because **the window build
redraws the 8-name bundle from ~2,700 permnos every month**: 8 of 1,504
name-slots repeat across 188 transitions, a **0.53% repeat rate**. Hysteresis
cannot hold a name that is not on next month's menu. The largest cost saving
anywhere is **0.34 bps/month**, and of the one cell that moved, 0.00034pp is the
cost and 0.0589pp is one different name held once.

**The 2010-13 second era from EDGAR only: CANNOT BUILD.** The 8-K tape's
`filing_date_min` is 2013-01-02 — 2010, 2011, 2012 have literally zero rows.
The decide step is locked in code: `assert_decidable()` refuses any wire call
outside `FROZEN_DECIDE_ERA = (2016, 2019)`, checked on the data.

## THE BIAS HISTOGRAM (item 5) — the hypothesis is refuted in the other direction

Within-month cap deciles, resolved counterparties (n=1,733) against a panel that
is uniform 10% by construction:

| decile | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| share | 1.9% | 2.3% | 3.9% | 3.7% | 4.2% | 6.9% | 6.5% | 8.1% | 14.9% | **47.6%** |
| ratio | 0.19 | 0.23 | 0.39 | 0.37 | 0.42 | 0.69 | 0.65 | 0.81 | 1.49 | **4.76** |

χ² 2947.0 (9 df), KS D 0.4295. On **distinct** counterparty permnos (n=578) —
2,020 edges are not 2,020 independent draws — mean decile 6.62, χ² 106.6.
Median cap **$14.28bn resolved vs $1.92bn panel**; `customer` edges $20.27bn at
mean decile 8.51; the **filer/supplier side sits lower** at 6.47 / $2.86bn.
That is the Cohen-Frazzini shape, not its inverse.

**Customer momentum was tested on the LARGE half of the graph, not the small
one.** The 68.9% residue is foreign or private *by construction*:
`crsp__stocknames` carries share codes 10/11/12/18 and **zero ADR codes** —
Nortel, Alcatel, BP, SAP, Canon are not in the file. Of 4,656 unresolved
mentions, 90% of keys are never in CRSP at all and only **52** should have
resolved and did not. A 50-name regex sample gives 6 matched / 42 foreign-private
/ 2 ambiguous ⇒ implied true resolution **39.3% [34.9, 47.5]** against the 31.05%
headline — and the missed residue is *itself* mega-cap (mean decile 7.96), so
repairing the resolver makes the graph **more** large, not less.

*What it does not settle:* `graph_cust_mom_1m_ew` matched **1.74%** of panel
rows, so coverage is a third explanation for a small t, distinct from both bias
and absence.

## CLAIMS FOR FABLE TO ATTACK

1. **The incumbents' excess is a loading.** Attack the beta estimator: full
   sample, OLS on the panel's own `mkt_vw_1m`, HAC beside it, walk-forward
   variant agreeing (β mean 1.218/1.451/1.355). If a *conditional* beta is the
   right object, the intercept could return. `C1_beta_matched_regrade_run01.json`
2. **`nn_pre_causal` is UNDERPOWERED, not NOISE**, and therefore deserves a
   shadow rather than a stop. Attack the choice of MDE (6.86%/yr) and the
   family size of 40. Say whether a shadow that cannot reach significance in
   twenty more years is worth a nightly receipt. `C2_*`, `C1_*`
3. **The DeepSeek table was wrong in SHAPE, not level** — output 4.59×, input
   1.21×. Attack the identification: two windows, three legs, `cached_in`
   scaled not measured, and a shared key whose unledgered calls would inflate
   the same number. `C3_deepseek_price_derivation_run01.json`
4. **Era-replay turnover was never rank churn.** 0.53% of name-slots repeat
   month to month. If that is right, the review's HOLD instruction could never
   have helped, and the real lever is a persistent candidate universe. Attack
   the repeat-rate computation. `C4_era_replay_hold_run01.json`
5. **Customer momentum was tested on the large half.** Attack the within-month
   decile construction and the claim that zero ADR codes in `stocknames` makes
   the residue foreign *by construction* rather than by assumption.
   `C5_counterparty_resolution_bias_run01.json`
6. **One receipt writer in the repo still stamps a module default in place of
   an argument** (`scripts/investment_committee.py:41`), and thirteen do not.
   Attack the three AST detectors — a survey that under-detects is worse than
   none. `C6_receipt_provenance_rule_run01.json`
7. **`indicator` mode costs nothing in admissions and buys the label.** Attack
   the claim that an identical admitted set is not evidence the hygiene gate is
   inert. `C7_monday_prep_read_only_run01.json`
8. **The `SHADOW` grade should not be in the registry at all** — if a
   zero-capital arm with no forward record is indistinguishable from
   `HYPOTHESIS`, the grade is ceremony. Attack the distinction.

## WHAT I COULD NOT DO

- **The lgbm_clf champion was not retrained**, so the shadow it is graded beside
  is itself REFUSED on a schema hash mismatch. Attended.
- **No monthly `nn_pre_causal` book exists yet**, so the shadow's first receipt
  is `PENDING_ARTEFACT`. The producing command is named in it.
- **The 2010-13 EDGAR-only era cannot be built** — the tape starts 2013-01-02.
- **`nn_pre_causal`'s alpha stays UNDERPOWERED.** No amount of re-grading fixes
  251 months.
