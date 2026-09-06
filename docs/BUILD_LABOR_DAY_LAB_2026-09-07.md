# BUILD — LABOR DAY LAB, 2026-09-07

Mandate `CONTINUATION_2026-09-07_LABOR_DAY_LAB_OPUS_PROMPT.md`. Four lanes,
thirteen items, both repos, **local commits only — nothing pushed, sealed,
ordered, deployed or changed on Railway.** Receipts:
finance `backend/data/optimus/labor_day_lab_2026-09-07/`,
terminal `state/labor_day_lab_2026-09-07/`.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE under the RESEARCH_CLAIM ruler.** No cell in any
lane survives its own family correction. What moved is the *machine*: the
research pipeline was tested against planted worlds it had never seen, the
fleet loop was tested against fourteen faults it had never been shown, and
every credential and connection in both repos now has a probe with a failure
class instead of an assumption.

| Lane | The one number | The one null |
|---|---|---|
| **A1** shadow grader | nn_pre_causal − lgbm_clf, beta-matched, 10 bps: **+2.827%/yr, t 0.748** over 251 months; the two books share **8.32 of 50 names** (excess corr **0.255**) — different errors, as claimed | family 6, family-min p **0.1245**, **nothing survives Holm**. Both nightly vintages absent: `lgbm_clf` REFUSED (schema `fd48dbc7` sealed vs `7f01cbe4` live), `nn_pre_causal` PENDING_ARTEFACT |
| **A2** retrain cadence | monthly minus frozen-once: **+5.751pp** beta-matched at 10 bps (**+5.388pp** at 25 bps); TW 27.17 vs 6.77. **The information is not static.** Reproduction gate ran first: annual reproduces W3b's `lgbm_clf` column over **454,708 rows, max dev 3e-08** | family 8, family-min p **0.05703**, best Holm **0.456** — **0 of 8 survive**. Quarterly covers only 95 of 251 months and is not comparable on TW |
| **A3** CPCV / PBO | 32-cell learner grid pooled PBO **0.0143**; the **neural family's champion is an individual SEED in 15 of 15 partitions**, never the seed-mean (PBO 0.5143 at 10 bps = SELECTION_IS_OVERFIT) | **at 1 month — the horizon the books trade — PBO 0.5286 against a 0.5 baseline: AT THE COIN FLIP.** 18 of 40 neural cells are not reconstructible; their stage parquets are gone |
| **A4** holding × selector | hysteresis is the largest lever in lane A: **19 of 20 rungs beat the no-hysteresis monthly control**. Best cell `nn_pre_causal hold_k=150 10bps` **+8.139%/yr t 2.393** vs MDE 6.802 ⇒ SEPARATED FROM ZERO | family **40**, family-max p **0.7794**, **0 cells survive Holm**. `lgbm_clf`'s +5.073pp at 25 bps is **turnover, not signal** — turnover 0.904 → 0.527, cost line 5.336% → 3.16%/yr |
| **B1** known-answer battery | the machine recovers **3 of 3** planted worlds (linear / regime / graph) with correct sign at Holm p **0.0000**, and returns **NOISE + REFUTED** on the null; the allocator gives the null world **weight 0.0** and parks the residual in the benchmark. **ALL_PASS** | two defects in the machine, both found by the fast pass: `verdict_from` has **no word for "significant, did not clear the deflation bar"** (a real planted edge at Holm p 0.0154 is called NOISE), and **`learner/evaluate.ERAS` is hard-coded 2016-2024** — a 1999-2024 panel is graded on its last nine years without a refusal |
| **B2** fantasy exams | **40 of 40 pairs monotone**, on all three of `p_up`/`exp_return`/`downside`, on **three independent draws**; mean |Δp_up| **0.370** | **canary rate 0.125** — one causally irrelevant pair in eight still moved the forecast by more than 0.05 of probability. The share means something only against that |
| **B3** bridge coverage | maps-to-nothing **40.0% → 26.7%** under the ownership standard the 09-04 receipt used | **40.0%, UNCHANGED**, under a panel-overlap standard. *companyworld_v1 gives us the concept and not the dates.* Grades identical by construction (0 of 20); the **18 of 20 that moved are a PANEL REBUILD**, not the map — a sealed receipt from 09-04 no longer reproduces |
| **C1** fault injection | **14 faults, 12 PASS, 53 checks**; five defects fixed *before* the venue found them (stop-id day salt, seal hash verification, sealed contract read, torn-ledger refusal, exit-failure stop re-place) | **clock skew is unguarded: every ET gate reads the LOCAL clock.** +20 min disarms the opening-range gate, −20 min manufactures a false refusal, and the curfew fires 20 minutes early. Reported, not fixed — it touches the entry gate of six live services |
| **C2** exit adversary | 1,200 synthetic paths, 6 profiles: **0 violations** on all three assertions — no close before min hold without a typed reason, every stop fires at the profile width and books HARD_RISK_LIMIT | `hack2`'s contract **IS** the EVENT defaults field-for-field (horizon 3, min hold 0, target 2.5%), and the min-hold rule is **vacuous on three of six books** — hack1/2/5 have `min_normal_hold_sessions = 0`, so 19% of hack1's paths close on session 1 or 2 |
| **C3** fragility sweep | **19 findings, 2 fixed**: `spend()` returned a truthy dict of ZEROS for a ledger it never read (which **re-authorises the whole LLM ceiling at the moment the accounting breaks**), and the provenance checker counted a file it could **not find** as a file it opened | 17 reported not fixed — all outside the lane's file ownership or attended by nature (the DELTA-STRESS gate that cannot fire, a missing decisions ledger that reads as "the book held", `except OSError: pass` on the spend ledger) |
| **C4** secrets & surface | **0 unadjudicated key-shaped hits** across 996 files committed since 2026-09-01 in both repos; seal-authority verified **GET/HEAD only, POST → 501, books dir only**, checked without a network call | `.env.bak.*` safe in both repos (ignored, never tracked, never in history, read by no code path) with **one low-severity gitignore gap in finance**. Nothing requires rotation |
| **D1** connections | finance **16 ok / 4 FAIL / 1 CANNOT DETERMINE of 21**; terminal **16 ok / 0 FAIL of 16**. Every failure names a class | **NVIDIA NIM CANNOT_DETERMINE at 30.2 s from finance and ok at 380 ms from terminal on the same fingerprinted key** — the finance probe's timeout, not the provider. WRDS not measured today (network) |
| **D2** key inventory | **44 credentials, 0 dead weight, 1 empty, 4 correctly refused**; six pairs proved the SAME object across repos by fingerprint | **the near-miss**: the first pass called **eleven live fleet keys DEAD** because `alpha/config.py` builds their names at runtime. Acting on that verdict disarms the whole fleet. Fixed with a derived rule (find the constructing `getenv`), not an exemption list |
| **D3** Tuesday re-arm | the deploy arms **hack2..hack6**; hack1 stays disarmed by `Mandate.manage_only` | **`AAT_MANAGE_ONLY=1` is read by nothing in this repository** — appendix B.2's hold-back line is inert, and `AAT_MANDATE_END_UTC` is set on **no service at all** |

## The connection table

Finance (21 surfaces): FRED · Finnhub · FMP · Polygon · AlphaVantage · EODHD ·
DeepSeek · HF router · OpenAI · EDGAR · Kalshi · Polymarket · CBOE · website
`/api/health/full` · seal-authority · Railway **ok**; **FAIL** Featherless
(`absent` — no key in this repo), Alpaca finance-mirror/arena (`auth` —
revoked in S36, confirmed), WRDS (`network`), GDELT (`quota`); **CANNOT
DETERMINE** NVIDIA NIM (`cannot_determine`, 30.2 s).
Terminal (16): six paper accounts ACTIVE/unblocked/flat (hack1 $98,859 · hack2
$98,821 · hack3 $90,499 · hack4 $99,476 · hack5 $96,455 · hack6 $91,469),
Alpaca data (iex bars, v1beta1 news, indicative options, screener), seal
artery, DeepSeek, NVIDIA, HF, OpenAI, Featherless, Finnhub, FRED, Railway —
**all ok**. Full tables: `D1_connection_table.md`,
`D1_connection_table_terminal.md`.

Railway `loving-elegance`: hack1-6 Online, **`aat-loop-staging` Failed** (its
long-standing state, named so nobody re-diagnoses it Tuesday), seal-authority
Online.

## The fault-injection table (C1, terminal, `AAT_TEST_MODE=1`, mock venue)

| fault | verdict | fix |
|---|---|---|
| venue 5xx on ENTRY | PASS | — |
| venue 5xx on EXIT | PASS | fixed 2026-09-05 (stop re-placed) |
| venue 5xx on STOP PLACEMENT | PASS | — |
| colliding stop `client_order_id` across sessions (BUR 422) | PASS | **FIXED** — `protect.stop_client_order_id` salts the digest with the ET session day |
| stale / tampered seal (sha mismatch) | PASS | **FIXED** — `tracker_portfolio.sealed_holdings` verifies `content_sha256` before returning |
| seal missing a contract | PASS | **FIXED** — `sealed_holdings` exposes `portfolios[book].contract`; `runner.contract_for` reads it |
| torn ledger line under a live entry | PASS | **FIXED** — `exits._evaluate_shares` refuses EXECUTION_CORRECTION while `ledger.MALFORMED` is non-empty |
| **clock skew ±20 min** | **FAIL (REPORTED)** | every ET gate reads the local clock; a venue-clock skew probe touches six live services — attended |
| empty corpus / absent sealed book | PASS | — |
| a name halted mid-session | PASS | — |
| partial fill (order qty ≠ position qty) | PASS | — |
| gap THROUGH the stop at the open | PASS | — |
| venue 5xx on the re-entry guard's own read | PASS | falls back to the local protective-stop audit, never fails open |
| refusal typing across every fault | PASS (gap) | `refusal_classes` has **no VENUE_REJECTED state** — a 503 from the venue is bucketed with prose from a gate nobody typed; the daily census cannot separate "the venue refused us" from "a rule of ours refused us" |

## Claims for Fable to attack

1. **A2's +5.751pp is freshness, not survivorship.** All four cadences run one
   pipeline over one panel; only the refit boundary moves. If the gap is real,
   the incumbent's annual clock is costing ~5pp/yr — and yet its Holm is 0.456.
2. **A4's hysteresis result is a cost result wearing a signal's clothes.**
   `lgbm_clf|25bps` gains 5.073pp while its cost line falls 5.336 → 3.16%/yr.
   Attack: is *any* of the 19-of-20 ladder gross of costs?
3. **A3's seed finding kills the neural ensemble's promotion logic.** If an
   individual seed wins 15 of 15 CPCV partitions and the seed-mean never does,
   the object W3b judged is not the object that wins — and PBO 0.514 says the
   winning seed is not choosable in advance either.
4. **A1's "different errors" is 0.255 correlation on 251 months** — attack the
   standard error of a correlation on overlapping monthly excesses before
   calling two books independent.
5. **B1 passes because its worlds are generous.** Planted effects are 6-11× the
   machine's own MDE. A battery that only plants edges the machine cannot miss
   proves the wiring, not the sensitivity. What is the smallest planted edge it
   still recovers?
6. **B2's 40/40 with a 0.125 canary rate.** One irrelevant pair in eight moves
   the forecast. Is 40/40 monotonicity distinguishable from a decider that
   moves confidently in whatever direction the last clause pointed?
7. **B3's 26.7% is NOMINAL.** The ownership standard counts a field as mapped
   when a concept exists; the panel-overlap standard, which asks whether the
   dates line up, says 40.0% unchanged. Which standard should the bridge be
   graded under?
8. **The 18-of-20 panel-rebuild drift is a reproducibility failure we have not
   named.** A receipt sealed on 09-04 no longer reproduces because the panel
   grew 519 rows and 8 names. Every sealed receipt in the repo has this shape.
9. **C2 says the min-hold rule is vacuous on hack1/2/5** — three of six live
   books have `min_normal_hold_sessions = 0`. B2 shipped the rule; half the
   fleet is exempt from it.
10. **D3: the runbook's disarm does not disarm.** Anyone following appendix B.2
    on Tuesday sets `AAT_MANAGE_ONLY=1`, sees `hack2 ARMED` in §4, and has to
    decide in the ten minutes before the open whether the check or the variable
    is lying.

## Test counts, spend, provenance

- Finance fast suite: **6869 passed, 14 skipped, 122 deselected in 487.04s, exit 0**
  (`AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300`).
  `backend/tests/test_labor_lane_a.py` — **37 passed** (7 new on A2).
- Terminal: **80 suites / 3,669 checks, ALL PASS (from 3,503 on 2026-09-05)** (`python run_tests.py`). Labor lane alone:
  4 suites / **165 checks** (`tests_smoke_labor_connections.py` 74 new,
  `tests_smoke_labor_faults.py` 53, `tests_smoke_labor_fantasy.py` 21,
  `tests_smoke_labor_exits_adversary.py` 17).
- **LLM spend: $0.03** of a $6.00 cap, all DeepSeek, all in lane B2 —
  `B2_probe.json` $0.000317 (2 calls), `B2_fantasy_exams_run02.json` $0.014856
  (96 calls), `B2_fantasy_exams.json` $0.014829 (96 calls), dry run $0.00
  (6 calls, no wire). **200 calls, 60,818 tokens, $0.030002 → $0.03.**
  Lane D issued **5 LLM probes** (nvidia, hf_router, openai, featherless from
  finance; featherless from terminal) at **5 output tokens each** — the D1
  receipts record no dollar figure because the amount is below the ledger's
  cent. Lanes A, C and B1/B3: **$0.00**.
  Provider balance $9.36 before and after — below its own reporting granularity,
  which is the expected reading at three cents.
- Every receipt carries `argv`, resolved config, and the SHA-256 of every input
  actually opened (`backend/services/receipt_provenance.py`, the Cb §6 rule).
- Read-only calls only: `/v2/account`, `/v2/clock`, `/v2/positions`,
  `railway status`, `railway variables`. No order, seal, deploy or variable set.

## What is queued, not done

Clock-skew guard (C1) · a `VENUE_REJECTED` refusal state (C1) · the 17 reported
fragility findings (C3) · `learner/evaluate.ERAS` hard-coded to 2016-2024 (B1)
· a verdict word between NOVEL and NOISE (B1) · `lgbm_clf`'s stale daily shadow
(schema mismatch, retraining is attended) · the finance `.gitignore` gap (C4)
· 18 of 40 neural cells whose stage parquets no longer exist (A3).
