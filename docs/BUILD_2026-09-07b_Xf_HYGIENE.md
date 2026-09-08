# BUILD 2026-09-07b — block X hygiene (finance), rows X2 / X5 / X6 / X7 / X8 / X9

**Lane:** `docs/ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 block X, the six
finance rows. **Licence:** hygiene — no book, no claim, no seal, no order, no
deploy, no Railway change, **no LLM call ($0.00)**, and no state-changing git
command. The lead session owns every commit.

**RESULT IMPROVEMENT: NONE.** Nothing here moves the demonstrated edge, and
nothing here is meant to. What moved is that six numbers a reader could have
believed are now either correct or refused, and each is held in place by a test
that has been shown to fire on the case it was written for.

---

## 1. Test counts

| | passed | failed | skipped | deselected | wall |
|---|---|---|---|---|---|
| **baseline** (before any edit by this lane) | 7,137 | **2** | 20 | 123 | 699.09 s |
| **final** | 7,364 | **7** | 20 | 124 | 614.22 s |

Command both times: `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300`.
`.env` was never moved. Output was captured to a file, never through `| tail`.

**+227 tests. Zero failures owned by this lane.** The failure accounting, in
full, because "2 → 7" read on its own is the wrong conclusion:

| failure | at baseline? | owner |
|---|---|---|
| `test_guard_missing_input_contract::test_every_guard_is_enrolled` | **yes** | another agent's new service. At baseline it named `sec_insider_bulk`; at the end it names `scrape_store` — that agent enrolled the first and added a second. This lane added no service module. |
| `test_signal_reachability::test_every_orphan_is_classified` | **yes** | another agent's unclassified module; **fixed by them during the session** — it passes at the end. |
| 6 × `test_arena_brain.py` | no | **transient, not real.** `backend/services/arena/beliefs.py` was being edited by another agent while the suite ran (mtime 22:41, mid-run). Re-run in isolation immediately afterwards: **62 passed, 0 failed**. Nothing in this lane touches `arena/`. |

The baseline was run twice: an earlier full-suite run (started before any edit)
exited **0** — the two baseline failures appeared mid-flight as other agents
added modules. Both baseline runs are therefore consistent, and both say the
same thing about this lane: it inherited its failures and it added none.

---

## 2. Row status

| row | status | the test that proves it |
|---|---|---|
| **X2** stale NAV excluded from beta | **PARTIAL** — repaired for the failure a NAV series can see; **REFUSED, with the beta stamped inadmissible, for the one it cannot** | `backend/tests/test_x2_stale_nav_marks.py` — 12 checks, incl. the Dimson lead/lag known answer **and** the known answer for the case that is *not* repairable |
| **X5** `SEPARATED_NOT_SURVIVING` | **DONE** | `backend/tests/test_x5_separated_not_surviving.py` — 11 checks; B1 battery re-run (fast **and** full), receipts regenerated, both `ALL_PASS` |
| **X6** `evaluate.ERAS` callers | **DONE** | `backend/tests/test_x6_era_grid_callers.py` — 8 checks, incl. an AST sweep of every `grade_by_era` call site in the repo |
| **X7** one price table | **DONE** | `backend/tests/test_one_price_table.py` — 7 checks, incl. the retired literal re-created and caught |
| **X8** `STATE_SEMANTICS` | **DONE** | `backend/tests/test_x8_state_semantics_header.py` — 7 checks, incl. the written vintage round-trip |
| **X9** stale doc numbers | **DONE** | `backend/tests/test_x9_doc_numbers.py` — 9 checks, every number read out of its receipt **first** |

### X2 — the stale NAV mark

`scripts/growth_g7_forward_lanes.py` gains `mark_freshness()` and
`admissible_returns_from_nav()`. A NAV level identical to the previous mark on a
session when |SPY TR| > **10 bps** (`STALE_MARK_MARKET_MOVE`, declared, not
inline) was not re-marked at the official close. **Two** sessions are dropped per
carried mark, not one:

* the carried session, whose return is a fabricated 0.0%;
* the session **after** it, whose return spans the gap — a multi-session return
  regressed on a one-session market. Keeping it *moves* the bias instead of
  removing it, which is the mistake that makes this kind of fix look done.

Every count travels on the row (`stale_marks_excluded`: marks, stale marks,
share, returns before/after/excluded, first and last stale date), and `run()`
now feeds both the website lanes and the hack accounts through it.

**The known answer** (`test_carried_marks_hide_beta_and_exclusion_gives_it_back`):
planted β 1.20, half the marks carried. Raw, the book reports **β 0.65** with a
sixth of its loading on yesterday's market. After exclusion the lagged loading
falls to a **twentieth** of the contemporaneous one and β comes back to **1.18**.
That is the roadmap's test — the lagged loading below the contemporaneous one —
on a world where the answer was planted.

**What X2 does NOT repair, stated because a reader would otherwise assume it
did.** There are two physical failures and a `(date, level)` series can only see
one:

| failure | visible in the NAV? | X2 |
|---|---|---|
| the price cache returned the same level again → the mark **repeats** | yes | dropped, β recovered |
| every mark is **one session old** → the level changes daily, nothing repeats | **no** | not repairable by dropping rows |

`test_a_uniformly_one_session_old_mark_is_reported_not_repaired` plants the
second and measures it: raw contemporaneous 0.35 / lagged 0.84, and after
exclusion 0.45 / 0.74 — better, not fixed. For that case the row is stamped
**`beta_admissible_as_exposure = False`** and the headline already says
`[STALE MARKS: …]`, so a consumer gates on a typed field instead of on a
sentence. **Which failure `conviction` actually has CANNOT BE DETERMINED from
the NAV series alone** — it needs the marking timestamps, and the track-record
snapshot does not carry them.

**Measured, not written.** `G7.run()` was executed under the new exclusion
(it writes nothing) purely to report the effect:

| lane | β before | β after | stale marks | returns excluded | `beta_admissible_as_exposure` |
|---|---|---|---|---|---|
| `conviction` | 0.7163 | **0.7592** | 1 | 2 | **False** (residual lead/lag is the one-session-old kind) |
| `mirror` | — | 0.5685 | 2 | 4 | **False** |
| `conservative-atr` | — | 0.0371 | 1 | 2 | True |

**`G7_forward_lanes.json` was deliberately NOT regenerated.** Re-issuing it
would move numbers this session has just corrected across three documents
(0.6072 / 1.3990), and re-issuing a published receipt is the growth-book lane's
act, not a hygiene lane's. The code path is live; the receipt is the owner's
call.

### X5 — the word between NOVEL and NOISE

`scripts/weekend_lab_jobs.verdict_from` gains a keyword-only `holm_p` and a
declared `SEPARATION_ALPHA = 0.05`. A verdict is `SEPARATED_NOT_SURVIVING` when
the arm **resolved itself** on this tape (`power.powered_for_observed_effect`),
its **family-corrected p ≤ 0.05**, and it did **not** clear the export bar — and
the string names which leg failed (`short of the export bar on DSR 0.9313`).

`learner.evidence_memory` gains the word in `VERDICT_VOCABULARY` **and** in
`_CAPPING_WORDS`: a recorded `SEPARATED_NOT_SURVIVING` binds exactly as `NOISE`
does, so nothing can be promoted through it. `_derive_verdict` never emits it —
a stored observation carries no family — so the word only ever arrives from a
job that actually computed a correction.

**The B1 battery, re-run.** `--fast`, the linear world, before and after:

| cell | t | Holm p | DSR | before | after |
|---|---|---|---|---|---|
| `linear::ridge` | 2.9551 | 0.01543 | 0.9277 | `NOISE` | `SEPARATED_NOT_SURVIVING (…; short of the export bar on DSR 0.9277)` |
| `linear::lgbm` | 3.0147 | 0.01543 | 0.9313 | `NOISE` | `SEPARATED_NOT_SURVIVING (… DSR 0.9313)` |
| `linear::lgbm_clf` | 2.9766 | 0.01543 | 0.9459 | `NOISE` | `SEPARATED_NOT_SURVIVING (… DSR 0.9459)` |
| all three `null::*` | 0.16–0.82 | 1.0 | 0.13–0.32 | `CANNOT DETERMINE (underpowered…)` | **unchanged** |

`ALL_PASS: True`, and the null world did not acquire a word that sounds like a
finding — the one direction of error this change could have made. The **full**
battery was re-run too (four worlds, 240 OOS months): `ALL_PASS: True`, linear /
regime / graph still `NOVEL` at Holm 0.0000 and `SUPPORTED`, null still `NOISE`
and `REFUTED`. The battery's own finding text now emits `RESOLVED [linear]` and
keeps the old check as a **regression guard**: if the middle of the vocabulary is
ever removed again, it fires again.

### X6 — no caller refuses on a long panel

`learner/evaluate.py` gains `eras_covering(df)`: the narrowest **canonical** grid
that describes the frame — `ERAS` if it fits (so every sealed 2016-2024 receipt
reproduces byte for byte), else `long_eras()`, else a **refusal**, never a third
grid invented at a call site. Both named callers now pass it:
`scripts/learner_run.py:236` and `scripts/learner_v2_run.py:345`.

The known answer is in the file: bare, on a 1999-2024 panel, `grade_by_era`
returns `{"_coverage": "REFUSED…"}` and **no era buckets at all** — so the first
repair had converted a silently *wrong* answer into a silently *absent* one. An
AST sweep asserts every `grade_by_era` call site outside `evaluate.py` passes
`eras=`.

### X7 — one price table

`backend/services/llm_research.PRICE_PER_MTOK` was the **published list** rates
(`deepseek-chat 0.27 / 1.10`), copied by hand. `config.LLM_PRICE_PER_MTOK` was
re-derived from the provider's own **balance** on 2026-09-05 and says
**0.169413 / 1.284835**. The two disagreed by **1.59× on the input leg and
1.16× on the output leg** for every call this module ledgered — and
`scripts/llm_cost_audit.py` reconciled that ledger against `config`'s table, the
one the ledger had never used, so the audit could not see the gap it exists to
find.

`PRICE_PER_MTOK` is now the config object itself and `_price()` re-reads
`_config.LLM_PRICE_PER_MTOK` at call time. The guard parses (never imports) every
module under `backend/ scripts/ learner/ lab/ engine/` for a module-level
rate-table-shaped dict literal and fails if a second one prices a model `config`
already prices. `scripts/era_replay_v2.NANO_PRICE_PER_MTOK` is the one permitted
extra — `gpt-5-nano` has no row in `config` and its receipts call their totals a
lower bound — and it is pinned to hold **nothing** `config` prices, so it turns
the guard red the moment it grows a DeepSeek row.

### X8 — the states are CANNOT_DETERMINE and informational-only

`learner/potential_universe.STATE_SEMANTICS` ended with *"4 OOS states, k=4,
**p=0.000 vs 200 random partitions**"* — that p is **null 1**, the legacy
within-month shuffle `learner/nullbar.py` records as mis-specified, quoted alone,
inside the header of every potential-universe vintage. `N5_states_third_null.json`'s
own `demotion` block names this file and asks for this correction in as many
words.

The block now leads with `status: CANNOT_DETERMINE` and
`admissibility: INFORMATIONAL-ONLY — never a sizing, admission or routing
input`, carries all three nulls together (null 1 p 0.000 clears / **null 2
p 1.000 FAILS** / null 3 p 0.005 clears), labels the `"0"` tag as **descriptive**,
and cites the adjudication receipt. The test asserts the verdict reaches the
built vintage header **and survives the JSONL round-trip** — the constant being
right matters only if it reaches the file a reader opens.

### X9 — the stale doc numbers

Every number was read out of its receipt **before** it was written into prose.
See §3 for the discrepancies, including one where the brief and the receipt
disagreed.

---

## 3. Doc-vs-receipt discrepancies found

Nine, all corrected in place with a dated note saying what the number used to be.
**The receipt won every time.**

| # | doc | said | receipt says |
|---|---|---|---|
| 1 | `BUILD_NIGHT_LAB_2026-09-07.md` construction table | one table: 25 bps control **3.66** beside 10 bps broad **29.27**, "one column, two constructions" | `N1_construction_books.json`: those are two cost rates. Same-cost pairs are **3.66 → 18.14 at 25 bps** (4.96×) and **8.96 → 29.27 at 10 bps** (3.27×). The 8.0× line was ~5.0× construction and the rest cost rate |
| 2 | same, N4 | "993,005 rows, **2015-2024**" | `N4_coverage_by_year.json`: span **2015-2026**; 2015-2024 holds **789,277** (verified by summing the by-year rows; 2025 = 107,986, 2026 = 95,742; total reconciles to `rows_written` 993,005) |
| 3 | same, N5 | "**127,157** → **97,949**, ratio 1.298" | `N5_event_compression.json`: **137,190 → 105,494, ratio 1.3005** |
| 4 | same, N1.3 | hedge "correctly (realised β **0.00–0.05**)" | `index_hedged_long_short`: **−0.0605 … 0.4254**, and **six** of twenty are outside ±0.05 |
| 5 | same, N6.2 | canary "**0/8**" | `N6b_fantasy_exams_round2.json`: that is the **END** arm. **END 0/8, FRONT 1/8** (`CANARY-045-front` moved) |
| 6 | `ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6 N1 | "hedge works (β 0.00-0.05)" | as #4 |
| 7 | `ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6 G7 | `conviction` "loads **0.66** today and **1.50** yesterday" | `G7_forward_lanes.json`: **0.6072** and **1.3990** joint (Dimson sum 1.9313, lagged univariate 1.4259, OLS β 0.7163) |
| 8 | `BUILD_GROWTH_BOOK_2026-09-07.md` §G7 | as #7 | as #7 |
| 9 | the NVIDIA embedder | roadmap §6 N5 had said **ABSENT** | `nemotron_probe`: **OK**, 935.9 ms, 3 embeddings, **dim 2048**. *(Already corrected by the 09-07 Fable session; verified here and now held by a test that allows the phrase only inside quotes — a retired number must stay quotable in order to be corrected.)* |

### LOUD: two places where the brief itself was wrong

1. **The brief's X5 gloss does not match the receipt.** The roadmap row reads
   *"the t clears the MDE but Holm does not"* and the task brief repeats *"it is
   separated from the null but does not survive family correction"*. The receipt
   says **Holm p = 0.01543458, which clears 0.05.** What fails is the
   **deflation** bar (DSR 0.9277–0.9459 < 0.95 on 36 months). So the implemented
   condition is *separated after Holm, short of the export bar* — which is also
   exactly what the battery's own finding text asked for ("no word for
   'significant, did not clear the deflation bar'"). Written this way in the
   function docstring and in the test, with the disagreement named.
2. **"0.00–0.05 was false for four cells" is itself wrong — it is six.** My own
   first correction said four (`ridge` ×2, `encoder` ×2). The receipt scan in the
   new test caught it before it was committed: `momentum` is **−0.0601 /
   −0.0605** at both cost rates and is also outside the band. **14 of 20** cells
   hedge, not 16. Corrected in both documents.

### The guard on #1

`test_no_doc_puts_3_66_and_29_27_in_one_table` flags any markdown table block
that carries `3.66` on one row and `29.27` on **another** row of the same table.
That is the defect shape and only that shape — prose which names the pair in
order to disavow it keeps both on one line and is not flagged, because a guard
that cannot tell a correction from an assertion makes corrections unwritable,
which is how a wrong number survives. `test_the_detector_fires_on_the_table_as_it_actually_stood`
reproduces the pre-fix table verbatim and asserts the detector fires on it.

---

## 4. What did not work, and what was deliberately not done

1. **X2 is PARTIAL and the shortfall is structural, not effort.** A `(date,
   level)` NAV series cannot distinguish "every mark is one session old" from a
   real one-day-lagged book. Dropping rows cannot repair it (measured: lag
   0.84 → 0.74). The honest output is a **refusal** —
   `beta_admissible_as_exposure = False` — not a repair. Fixing it properly
   needs the **marking timestamps**, which `track_record_full.json` does not
   carry. That is the next lane's dependency, and it belongs with H5
   (terminal-state reader) rather than here.
2. **`G7_forward_lanes.json` not regenerated** — see X2 above. The effect was
   measured and reported instead. `conviction` β 0.7163 → 0.7592 and still
   inadmissible as exposure.
3. **My first X2 planted world was wrong and the test caught it.** I assumed a
   carried mark would put the loading on *yesterday*. It does not: carrying
   biases the contemporaneous and lagged loadings **symmetrically** (measured:
   raw b0 0.65, b_lag 0.24 for a planted 1.20). The lag-dominant shape needs the
   *one-session-old* failure. Both worlds are now in the file, with the measured
   numbers, rather than one world and a wrong story.
4. **`_derive_verdict` was left alone.** Teaching the export path to derive
   `SEPARATED_NOT_SURVIVING` would change the verdict of stored observations
   that already carry a `holm_p`, i.e. rewrite history in the evidence memory.
   The word arrives only from a job that computed the correction; the export
   caps on it and never invents it.
5. **`evaluate.ERAS` itself did not move**, on purpose — a sealed receipt is
   sealed at its bucket names as well as its numbers. X6 fixes the *callers*.
6. **Two shell heredocs mangled a Python payload** containing `'` and `\n`
   escapes and silently wrote nothing on one occasion (the assertion inside the
   payload failed, exit 1, and the surrounding `;` chain carried on). Caught
   because the following test run still failed on the old assertion. Every
   subsequent scripted edit asserts the old text is present before replacing it.
7. **Not touched, and reported instead of applied:** nothing in this lane needed
   a file outside it. `backend/config.py`, `backend/main.py`,
   `backend/services/model_provider.py`, `backend/services/arena/`,
   `backend/tests/guard_contract.py` were all being edited by other agents
   during the session and were left alone.

---

## 5. Files changed

**Source** — `learner/evaluate.py` (+`eras_covering`), `learner/evidence_memory.py`
(vocabulary + capping), `learner/potential_universe.py` (`STATE_SEMANTICS`),
`backend/services/llm_research.py` (one price table),
`scripts/growth_g7_forward_lanes.py` (mark freshness + exclusion + admissibility
stamp), `scripts/weekend_lab_jobs.py` (`verdict_from`),
`scripts/labor_b1_known_answer_battery.py` (passes `holm_p`; findings),
`scripts/learner_run.py`, `scripts/learner_v2_run.py` (explicit era grid).

**Tests (new)** — `test_x2_stale_nav_marks.py` (12), `test_x5_separated_not_surviving.py`
(11), `test_x6_era_grid_callers.py` (8), `test_one_price_table.py` (7),
`test_x8_state_semantics_header.py` (7), `test_x9_doc_numbers.py` (9). **54 new
checks.**

**Docs** — `BUILD_NIGHT_LAB_2026-09-07.md`, `ROADMAP_2026-09-04_PROFIT_ENGINE.md`,
`BUILD_GROWTH_BOOK_2026-09-07.md`, and this file.

**Receipts regenerated** — `B1_known_answer_battery.json`,
`B1_known_answer_battery_fast.json` (both `ALL_PASS: True`). The battery
redirects `evidence_memory.STORE` to a scratch file for the duration of its run,
so the real evidence memory was not written by it.
