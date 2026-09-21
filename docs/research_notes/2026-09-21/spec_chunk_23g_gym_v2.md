# Chunk 23g — Gym v2: the market-structure brief and the four roles

Spec by Fable, 2026-09-21, from Murat's Part 1 (`feedback_murat_review_2026-09-21_morning.md`)
and the Sonnet read `research_multi_role_llm_forecasting.md` (§4 holds the
brief's field table, the five prompts and the 2×2 design; this spec fixes the
decisions and does not repeat the text). Builder: Opus, after 23a. $0: local
model only.

## Decisions

1. **A new job, not an edit of S2.** `scripts/night_scenario_gym_v2.py` =
   night job `S3_scenario_gym_v2`, importing S2's machinery unchanged
   (`build_case`, the six arms, sign-matched controls, `parse_decision`,
   `movement`, `calibration_block`, `adoption`). S2 keeps running as the
   one-voice / no-brief baseline; v2 never rewrites its receipts.
2. **The brief is a service.** `backend/services/market_brief.py`:
   `build(case) -> Brief` with the fields of the read's §4.1 — coverage level
   and breadth trend, target dispersion and its change, attention volume
   trend, dominant typed event, thematic membership — each `{value, source,
   asof, status}` where `status ∈ {PRESENT, MISSING}` and MISSING carries the
   reason (one analyst snapshot; no typed event; …). **The headline field
   "is the market growing or shrinking / what substitute is forming" ships as
   MISSING with `reason = "no on-disk source; PROBE-lane acquisition owed"`**
   — never a return-based proxy, which would answer the question with the
   thing being forecast. Every field is PIT: dated before the case's
   information cutoff, or MISSING. The live consensus fetch is NOT used (not
   PIT). The brief renders to ≤ 900 characters of plain text with each
   MISSING field printed as such.
3. **Five prompts, one schema.** ATTACK, RESEARCH, DEFEND, ALTERNATIVE, then
   ARBITRATE over the four JSON answers; text as in the read's §4.2, each
   answering S2's frozen `DECISION_SCHEMA`. All five system prompts are
   fingerprinted on the receipt as S2 does (`prompt_fingerprint`), and the
   schema must be present in each (S2's 2026-09-13 lesson, pinned by test).
4. **The 2×2 on the SAME cases.** Conditions: `one_voice_brief`,
   `four_role_no_brief`, `four_role_brief`; the fourth cell
   (`one_voice_no_brief`) is S2 run01, read from its answers file by case
   key — the receipt refuses if a case key is absent there. First run
   `N = 100` cases (`SCENARIO_GYM_V2_N`), all six arms for every condition,
   box 75 min (`SCENARIO_GYM_V2_BOX_MINUTES`); resumable per (case, arm,
   condition, role) like S2's answers file.
5. **The receipt's new blocks.** (a) `paired_roles`: four-role vs one-voice
   sign accuracy and Brier, brief held constant, on the same cases, with the
   discordant-pair rate and a McNemar exact p; (b) `paired_brief`: brief vs
   no-brief, one-voice held constant, same statistics; (c) `within_case_rho`:
   the correlation of the two conditions' errors — the number the read says
   nobody has measured; (d) `arbiter_recoverable_by_majority`: the share of
   cases where ARBITRATE equals the majority direction of the four roles;
   (e) per-role sign accuracy and Brier; (f) the six-arm movement and the
   sign-matched control lifts, per condition, exactly as S2 prints them;
   (g) `brief_field_coverage`: how often each field was PRESENT.
6. **Adoption unchanged.** `adoption(n_graded, calib, n_blocks=…)` as S2:
   n ≥ 300 AND blocks ≥ 12 AND a forward record. N=100 cannot adopt and the
   receipt says so; its purpose is to measure ρ and the discordant rate so the
   powered N is pre-registered from a number, not a guess.
7. **Refusals.** `--backend deepseek` is REFUSED by name in this job (the cap
   is not yet proven on a paid run; §16.3 row 22c's second half). A case whose
   brief is entirely MISSING still runs (the no-brief condition is its
   control), but the receipt counts them.

## Tests (tmp_path; no model calls — stub the backend as S2's tests do)

1. `market_brief.build` on a case with one analyst snapshot → breadth and
   dispersion MISSING with the reason; the headline field MISSING with the
   PROBE-lane reason; nothing dated after the cutoff is ever PRESENT.
2. All five prompts contain the schema's field names and the direction enum.
3. A stubbed run over 6 synthetic cases produces the three conditions, reads
   the fourth from a synthetic S2 answers file, and refuses when a case key is
   missing there.
4. `paired_roles` / `paired_brief` compute McNemar on a hand-built 2×2
   discordant table; `arbiter_recoverable_by_majority` on hand-built votes.
5. `--backend deepseek` refuses before any call.

## The closing line (§16.1)

`BELIEF_CHANGED: sign accuracy one-voice → four-role X → Y (paired, n=…,
discordant …, McNemar p …), Brief no → yes A → B; within-case ρ = …;
arbiter recoverable by majority in Z% of cases. Capital moves when …` — or
`HYPOTHESIS_KILLED: roles add nothing` under the read's §5 condition
(indistinguishable AND arbiter recoverable by majority), in which case the
cheap half (brief only) is what ships forward.
