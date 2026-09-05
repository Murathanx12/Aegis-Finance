# CONTINUATION b — 2026-09-06 (Sat night HK) — act on Fable's review of the ten claims

**Read first:** `REVIEW_2026-09-06_FABLE51_ON_THE_CONTINUATION.md` (the mandate
is its §"What changes because of this review"), then
`BUILD_CONTINUATION_2026-09-06.md`, `ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6,
`DECISIONS_2026-09-05_PLAIN_LANGUAGE.md`. The Optimus MCP may be down (a
taskkill took it out); if `session_briefing()` fails, read
`docs/INDEX.md` TIER 0 and continue — do not wait on it.

## Rules
Same as `CONTINUATION_2026-09-06_OPUS_PROMPT.md` §1, plus: **LLM cap $0 this
session** (every item below is arithmetic on data and decisions we already
have); never kill a process by image name (CLAUDE.md rule 6); either the lab
runner or a standalone job, never both; nothing pushed, sealed, ordered,
deployed or changed on Railway; commit locally on `main` per job; fast suite
at the end.

## The seven items, in priority order

1. **Beta-matched re-grade of both incumbents and the neural ensemble.**
   Using `learner/benchmark.py`'s beta-matched benchmark and a monthly
   regression of each book's excess on the VW market return (report
   intercept, loading, t of each, and the intercept's DSR over the family),
   re-grade `lgbm_clf`, `lgbm_raw` and the `nn_pre_causal` 8-seed ensemble on
   the floored 1999-2024 folds from `W3b_neural_floored_run01.json`. The
   question is one sentence: **is the incumbents' excess an intercept or a
   loading?** Also compute the top-5-month share under the beta-matched
   benchmark. Receipt + a Monte Carlo null for the top-5 share at each
   series' own mean/sd (Fable's: 31-40% of noise draws exceed 83.55%).
2. **Freeze `nn_pre_causal` as a zero-capital shadow book** (PRODUCT_EXPERIMENT):
   frozen 8 seeds, the rule hash `428a7148…`, floored training universe,
   monthly cadence, graded nightly beside `lgbm_clf`'s shadow by the same
   grader (`scripts/learner_shadow_seal.py` or its successor), receipt every
   night even when empty. No capital, no order path. Register it in the
   signal registry as SHADOW with `first_grade_date`.
3. **DeepSeek price table from the provider balance.** Reconcile
   `LLM_PRICE_PER_MTOK` against `deepseek_balance.jsonl` deltas over the
   sessions with known token counts; set the constant from the measured
   rate, record the derivation, and make the dollar gate bind at real
   dollars. Test: a synthetic ledger + balance delta must reproduce the rate.
4. **Era replay HOLD arm, $0.** Re-grade the existing 192-window decisions
   under a hold rule (keep last month's names unless their rank leaves the
   top 2k), same nulls, same costs; report turnover, net excess and the
   family with the four existing arms (family size 8). Write the second-era
   window build (2010-13 from EDGAR only) but do NOT run the decide step.
5. **Counterparty resolution bias check.** Cap-decile histogram of resolved
   counterparties vs the panel, and a 50-name random sample of unresolved
   counterparties with a regex/alias pass against CRSP `stocknames` to
   estimate how many were in fact US-listed. Receipt says whether customer
   momentum was tested on the small half of the graph.
6. **Receipt provenance rule.** Every receipt writer records `sys.argv`, the
   resolved config, and `_inputs_opened` (path + SHA-256 of every input file
   the loader opened); a test compares stamped inputs with opened inputs and
   fails on a module default stamped in place of an argument. Apply to the
   weekend/continuation job wrappers.
7. **Monday prep, read-only.** Re-run `B3_3_monday_dry_run` with the two
   decisions applied as *proposals*: (a) band-derived `exp_return` kept as an
   UNVALIDATED INDICATOR stamped on the seal so hack6 is not empty; (b) hack2
   marked manage-only in the runbook. Attach the new printout to
   `aegis-alpha-terminal/docs/RUNBOOK_2026-09-08_REARM.md`. Do not change
   Railway variables.

## Deliverable
`docs/BUILD_CONTINUATION_2026-09-06b.md`, ≤ 2 pages, RESULTS SCOREBOARD
first; the one-sentence answer to item 1; the shadow-book registration; the
corrected price constant with derivation; the HOLD-arm table; the bias
histogram; claims for Fable to attack (3-8); test counts; LLM spend ($0.00
expected). Update roadmap §6, session memory (one file, one fact each; one
`MEMORY.md` line < 200 chars), and run `python tools/refresh_aegis.py` in the
Optimus repo if it is reachable.
