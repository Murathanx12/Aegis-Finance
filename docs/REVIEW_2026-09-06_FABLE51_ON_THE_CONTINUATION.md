# REVIEW — 2026-09-06 — Fable 5.1 on the continuation session's ten claims

**Object:** `BUILD_CONTINUATION_2026-09-06.md` §"CLAIMS FOR FABLE TO ATTACK" and the
receipts under `backend/data/optimus/continuation_2026-09-06/`. Every verdict
below names what was re-read or re-derived. One re-derivation changes a
headline (claim 5); one verdict is reversed in its consequence (claim 4).

## Scoreboard of verdicts

| # | claim | verdict | what decided it |
|---|---|---|---|
| 1 | The CUDA numbers were always real (site-packages mtime unmoved) | **CONFIRMED** | NTFS directory mtime moves on any direct-child add/remove/rename; a torch wheel swap renames `torch-*.dist-info`. An in-place edit inside a subdirectory would not move it, but that is not how pip replaces torch. The venv-shadows-base finding is the useful part; the pin test closes it. |
| 2 | `target_rev_1m__xs` beats a cap-matched draw (t 2.50) and not an EW market (t 0.86) | **CONFIRMED, and the honest sentence is the right one** | `S2_size_matched_control_run01.json`: the control pays the book's own cost series and replaces each holding with a same-cap-decile draw, so it isolates within-decile selection — that is the correct control. What it also shows: DSR 0.33 over the weekend's 307 trials, within selection noise. The arm is powered for its own effect and unsearched it is not. Nothing to trade; one more row for the revision family in the registry. |
| 3 | More supply-chain tape made customer momentum weaker | **CONFIRMED as measured; the bias question is OPEN** | FM t 1.447 → 0.297 on never-seen 1999-2011 tape is a clean out-of-sample failure of the *feature as built*. But 31.1% counterparty resolution with the residue *assumed* foreign/private is the same 69% MARKET-GRAPH-1 measured, so the extractor is behaving as before, not worse. What is not yet known: whether resolved counterparties skew small. Cheap test for the next session: cap-decile histogram of resolved counterparties vs the panel; if resolved edges over-represent small caps, customer momentum (a large-customer → small-supplier effect in Cohen-Frazzini) was tested on the wrong half of the graph. Until then: CANNOT DETERMINE for the mechanism, CONFIRMED for the implementation. |
| 4 | B10 not earned | **CONFIRMED as a RESEARCH_CLAIM verdict; REFUTED as a reason to stop the arm** | The rule was hashed before the fit and the ensemble failed (b): DSR 0.17 vs lgbm_clf against a 0.95 bar, SPA p 0.108. Right verdict for *capital* and for *claims*. But `nn_pre_causal` passed (a), (c) and (d): +4.75%/yr over lgbm_clf at 10 bps and +5.06% at 25 bps, TW 49.0 vs 22.6 and 36.2, positive in 3 of 3 eras, on a training universe that was already floored ($3m/day, ≥ $5, floor-at-grading a proven no-op). The three licences say a `PRODUCT_EXPERIMENT` shadow needs a frozen contract, not a significance gate. **Stopping the loop is right; refusing shadow accrual is over-closing.** Freeze the 8-seed `nn_pre_causal` ensemble (seeds and rule hash already recorded) as a zero-capital shadow book alongside `lgbm_clf`; it is the first candidate for a second independent selector since the bottleneck was diagnosed, precisely because its errors are different (see claim 5). |
| 5 | The mandated baseline is five months (83.55% of lgbm_clf's excess) | **REFUTED as evidence of beta timing; CONFIRMED that the baseline is low-Sharpe** | Re-derived: lgbm_clf's monthly excess has mean ≈ 0.28% and sd ≈ 3.6% (from +3.39%/yr, t 1.225, 251 months). Monte Carlo of a series with exactly those moments and no structure at all: the top-5 months carry ≥ 83.55% of the sum in **31% of draws** (normal) to **40%** (t₄ tails), and the series turns negative without its top 5 in **25-31%** of draws. A top-heavy sum is what *any* Sharpe-0.08 series looks like; the market's 21.9% is because its Sharpe is 0.24, not because it is better behaved. That the five months are GFC/COVID bottoms says the book has beta > 1 (a VW top-50 of high-upside names does), which is a different claim and testable: re-grade against `benchmark.beta_matched` and regress monthly excess on the market return; if the intercept is ~0 and the loading > 1, it is beta, and the fix is the benchmark, not the model. **Every "beats/loses to lgbm" sentence in the repo is fine as a relative statement; the absolute baseline needs the beta-matched ruler.** |
| 6 | The LLM cannot read 2016-19 filings into a beating rank | **CONFIRMED, with the cost story attached** | 192 windows, 48 month blocks, all four arms negative net, IC −0.03 (windows t −1.05), null-1 p 0.41, blind held 0/768. MDE 8.75%/yr — underpowered for anything small, and the LLM is not small-positive, it is at random. Note the receipt's `mean_turnover 0.9965`: the decider rebuilds the whole top-k every month, so 10 bps/side costs ~0.2%/mo of the −0.39%/mo net. Add a HOLD arm (keep the prior month's names unless the rank leaves the top 2k) before spending another dollar on the decide step. A second era is worth more than more windows in the same one — windows within a month share the month. |
| 7 | Nine of twelve SUPPORTED cells are in the superseded W7 family | **CONFIRMED — wholesale exclusion is right** | The leak was in the *control construction* shared by every W7 cell, not in one feature, so every observation written before the fix is contaminated regardless of cell. Corrected re-runs after the timestamp count normally. A narrower rule would readmit contaminated votes. The registry export withholding the 15 cells (`B6_evidence_to_registry_run01.json`) is the correct state. |
| 8 | W4b stamped a module default in place of an argument | **CONFIRMED; generalise it** | The fix (record `source_rows`, prove red) is local. The general rule: every receipt writer records `sys.argv`, the resolved config, and the SHA-256 of every input file it opened; a provenance test compares the stamped input paths with the paths actually opened (strace-free version: the loader appends to a `_inputs_opened` list). One afternoon, and it closes the class. |
| 9 | Four of the review's six moves were already closed | **ACCEPTED** | Not re-derived; the correction record names its own error (reading `run09` instead of the newest of 31) and that is what the record is for. |
| 10 | The venue screener called seven names "the whole market" | **CONFIRMED and important** | 7 → 23 movers by union with the tradable-universe ranking; LULU −17.4%, ADSK −8.3%, NX +22.2%, FICO −16.7% were missed by the screener alone. **Opportunity-recall baseline for 2026-09-04: 0 of the 16 biggest movers were on our candidate list in either direction.** That number is the KPI; it should print every night. |

## What changes because of this review

1. **Freeze `nn_pre_causal` as a shadow book** (PRODUCT_EXPERIMENT, zero
   capital, frozen seeds + rule hash), graded nightly beside `lgbm_clf`. The
   neural *research* loop stays stopped.
2. **Re-grade both incumbents against the beta-matched benchmark** and a
   market-regression intercept before anyone quotes "beats lgbm" again. If
   lgbm_clf's excess is beta, the comparison ladder is re-based, not broken.
3. **Fix the DeepSeek price table from the provider balance**, never from
   telemetry (`S4_llm_spend_reconciliation_run01.json`: ledger prices 56% of
   the charge). The dollar gate must bind at real dollars.
4. **Era replay:** HOLD arm + second era before any more decide spend.
5. **Counterparty resolution bias check** before the graph is declared
   uninformative.
6. **Receipt provenance rule** (claim 8) into the receipt writer.
7. Monday: the two decisions in `DECISIONS_2026-09-05_PLAIN_LANGUAGE.md` plus
   the two Monday risks in `BUILD_CONTINUATION_2026-09-06_DETAIL.md` (hack6
   emptied by literal hygiene-only; hack2 armed with event defaults).

*Nothing here is an alpha claim. Two of the ten claims were over-stated in the
direction of caution (4, 5); the program's habit of closing too hard is the
one this review corrects.*
