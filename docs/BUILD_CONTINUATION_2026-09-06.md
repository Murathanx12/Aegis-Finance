# BUILD — CONTINUATION 2026-09-06 (Opus 5 as builder, six parallel agents)

Mandate: `docs/CONTINUATION_2026-09-06_OPUS_PROMPT.md`. Nothing pushed, sealed,
ordered, deployed or changed on Railway. Every number below has a receipt path.

---

## RESULTS SCOREBOARD

*(filled at the end of the session — see the sections below for the receipts)*

| KPI | This session |
|---|---|
| Best historical net strategy vs the market | — |
| Best forward paper strategy | — |
| Independent selector count | — |
| Farm candidates tested / promoted | — |
| New actionable finding | — |
| External execution drag | — |
| LLM spend / cost per gradeable output | — |

---

## 0. THE CUDA QUESTION — ANSWERED: a different interpreter, not a downgrade

`W3_neural_long_run13` recorded `torch 2.11.0+cu128`, `cuda_available: true`,
RTX 5060, `sm_120`, while `.venv/Scripts/python` reports `2.11.0+cpu`. The
review offered two hypotheses. It was the first, and the filesystem settles it:

| evidence | value |
|---|---|
| `.venv/.../torch-2.11.0.dist-info/RECORD` mtime | 2026-03-31 11:22 |
| `.venv/Lib/site-packages/` directory mtime | 2026-08-27 17:35 |
| entries in that directory newer than 2026-09-01 | **0** |
| system Python 3.12 `torch-2.11.0+cu128.dist-info/RECORD` mtime | **2026-09-05 11:49** |
| first CUDA-stamped W3 receipt | 2026-09-05 13:30 |

A directory's mtime moves when an entry is added or removed. `site-packages`
has not moved since 27 Aug, so nothing was installed into or removed from the
venv on 5 Sep: **the venv's torch has been the CPU build continuously since
31 March and was never downgraded.** The CUDA wheel went into
`C:\Users\mrthn\AppData\Local\Programs\Python\Python312`, one hour and
forty-one minutes before W3 ran. `resolve_device()` was honest at the time
(`git show da82992`), so **the GPU numbers are real**.

**The real defect was that the device block named the torch build and never the
interpreter**, so the receipt could not answer the question it existed to
answer. Three fixes, committed:

1. `learner/neural_long.py` — every device block now carries
   `python_executable`, `python_version`, `torch_file`.
2. `requirements-gpu.txt` — pins `torch==2.11.0+cu128` with its `--index-url`,
   names the designated interpreter and the `AEGIS_GPU_PYTHON` override, and
   carries the filesystem receipt in its header.
3. `backend/tests/test_gpu_environment_pin.py` — 4 tests. **FAILS** on a host
   with an NVIDIA GPU whose designated interpreter stops reporting CUDA;
   **SKIPS** on a GPU-less host, because a GPU assertion on a GPU-less runner
   is a broken gate, not a strict one.

**The caveat that must travel with every W3 number:** it ran on system Python
3.12 (numpy 2.4.6, sklearn 1.9.0), an environment the fast suite has never
exercised.

Receipt: `backend/data/optimus/continuation_2026-09-06/S0_cuda_drift_run01.json`

---

## S1 / S2 — TWO OF THE REVIEW'S THREE SETTLEMENT ITEMS WERE ALREADY DONE; I PUBLISHED THE THIRD

`REVIEW_2026-09-06_ATTACK_ON_THE_WEEKEND.md` was written against `f6b96e3`
(13:07 +0800). Three things were named as settling CLAIM 1 and CLAIM 6.

**(a) Null `target_rev_1m` on `cfacpr` moves — ALREADY DONE, and as a REBASE.**
`35915db` (13:23) rebases the prior target by `cfacpr(t)/cfacpr(t-h)`
(`dataset.py:799-809`), which cancels every factor after `t` and keeps the
observation rather than throwing it away; the panel was rebuilt at 13:51.
Measured on the panel every job in this session reads:

| | review at f6b96e3 | panel on disk |
|---|---|---|
| rows with a `cfacpr` move | 4,303 | 4,359 |
| mean `target_rev_1m` on them | **+3.12** | **+0.0675** |
| max | +359 | +31.5 |

A 46x reduction in the mean. Still open: 2.04% of those rows report a >100%
one-month consensus move and the panel-wide max is +141.5 — a rebase cannot
repair two IBES vintages that disagree about the share basis, and nothing
bounds those rows.

**(b) The share-basis gate that could not go red — ALREADY FIXED** in the same
commit: `learner/long_panel.py` now tests the LEVEL against a 0.95 floor and
carries an `_injection_self_test` that re-runs it against the injected
2026-09-04 defect (0.978 real vs 0.853 injected).

**(c) Re-run W9 with `n_trials` populated — ALREADY DONE.** I got this wrong
first: I read `run09`, the receipt the review quoted, and called it open. There
are 31 W9 receipts and `run40` (09:00Z, after the review's tree at 05:07Z)
carries `n_trials_used_for_the_DSR` **307** and returns **DSR 0.1239,
WITHIN_SELECTION_NOISE**; SPA p 0.0679; PBO 0.1429; MDE 8.0%/yr; t=2 needs
36.3 years against 25.67 observed. The review estimated 0.2022 at 277 trials —
same direction, further. *Absence of a fix in the receipt you were handed is
not evidence of absence.*

**(d) The size-matched control table — GENUINELY OPEN, so I built it.**
`scripts/size_matched_control.py`. The reviewer computed it in a scratch
session and quoted it in prose; every headline number belongs in a receipt.
`target_rev_1m__xs`, top-50 VW, 10 bps, 308 months, on the panel on disk:

```
book net TW 85.324 | VW market 13.031 | EW market 57.183 | cap-matched 11.127

vs VALUE-weighted market   +11.52%/yr  t 2.407   eras 2.774 / 1.784 / 0.094
vs EQUAL-weighted market   + 4.01%/yr  t 0.859   eras 0.823 / 0.629 / 0.167
vs CAP-DECILE-MATCHED draw +11.55%/yr  t 2.496   eras 2.525 / 2.160 / 0.272
```

**The claim survives the right control and dies against an equal-weighted
market.** The decay is real relative to cap-matched peers and absent relative
to EW, because against EW there was never anything to decay. And it still
reaches no verdict: **DSR of book-minus-control is 0.3326** over the weekend's
own 307 trials — WITHIN_SELECTION_NOISE. The control pays the BOOK's cost
series so the comparison isolates selection.

Note for anyone comparing with the review: it quoted TW 56.655 / t 2.055 at
`f6b96e3`; `evaluate.book` on the rebuilt panel returns 85.324 / 2.407, and so
does W9 `run40`. Both are correct for their own tape. **Cleaning the share
basis made the arm stronger**, which is why contamination explains nothing.

Receipts: `.../continuation_2026-09-06/S1_panel_split_contamination_recheck_run01.json`,
`.../S2_size_matched_control_run01.json`

---

## THE REVIEW'S SIX RANKED NEXT MOVES — where they stand

| # | move | state |
|---|---|---|
| 1 | re-run W9 on the code on disk, publish `n_trials_used_for_the_DSR` | **DONE before this session** — `W9_survivor_books_run40_v0.json`, 307 trials, DSR 0.1239 |
| 2 | replace the share-basis gate's gap test with a level test, prove it by injection | **DONE before this session** — `long_panel.py` `LEVEL_FLOOR = 0.95` + `_injection_self_test` |
| 3 | null `target_rev_1m`/`target_rev_3m` across a `cfacpr` move; re-issue | **DONE before this session, as a REBASE** — mean on split rows 3.12 -> 0.0675 |
| 4 | add the EW-market and cap-matched-control rows | **DONE THIS SESSION** — `S2_size_matched_control_run01.json` |
| 5 | re-run W10 through the runner so it has a durable receipt | **STILL OPEN.** Not attempted: the house rule is one lab job at a time and the GPU pass held the slot |
| 6 | downgrade "clear as an exclusion" (claim 4) or re-issue at the $2 floor | **DONE THIS SESSION** — struck at the point of use in `BUILD_WEEKEND_LAB_2026-09-06.md` FINDING 7; the exclusion leg is t −0.93, negative in 3 of 3 eras, and that is consistent-with, not established |

Three corrections to the continuation prompt itself, each verified against a
receipt rather than argued:

- *"W4 was CANNOT DETERMINE"* — the module's word is
  `CANNOT DETERMINE (underpowered)`, but the **receipt's** verdict, after the
  runner re-derives it through the screen bar, is **NOISE**
  (`W4_graph_momentum_run40_v0.json`). A feature screen cannot reach NOVEL and
  this one did not clear anything: 0 of 9 features reach |t| >= 2 with controls
  and one sign in 2 of 3 eras.
- *"MARKET-GRAPH-1 edges cover 12 of 26 panel years"* — true, and the window is
  **2014-2024**, not an early one. The panel-row match rate for the graph
  features is **1.1-2.8%**. So the 1999-2013 extraction §2a asks for is exactly
  the complementary window, and the honest bar for it is a match rate, not an
  edge count.
- *"Friday's L10 built the scaffolding"* — **false**, and independently
  confirmed by the agent that needed it: `BUILD_NIGHT_LAB_2026-09-05.md` lists
  L10 among the jobs NOT run and `night_lab_2026-09-05/` holds no L10 receipt.
  The scaffolding was built this session.

---

## 2a. SUPPLY-CHAIN EDGES BOUGHT — and the scope excuse is answered NEGATIVELY

`scripts/companyworld_extract.py` (a copy of the third repo's `mg1_*`, never an
import across repos) read **1,486 10-K filings** from EDGAR — 10-K bodies were
not on this machine and were fetched at 8 req/s with a declared UA; no corpus
substitution — and wrote
`backend/data/optimus/graph/companyworld_v1.parquet`:

**2,020 resolved edges over 945 distinct permnos, 1999-2011**, 93.9% carrying a
verbatim quote present in the excerpt that was sent. Resolution to CRSP 31.1%,
within a point of mg1's own 30.6%; the residue is the same and is not a bug —
**4,138 of 6,753 mentions are not in CRSP at the date, because the supply chain
is mostly not US-listed.**

| year | 99 | 00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| edges | 13 | 174 | 144 | 196 | 238 | 185 | 185 | 202 | 205 | 148 | 134 | 146 | 50 |

customer 854 · competitor 761 · supplier 284 · shared_technology 102 ·
regulatory_exposure 18 · shared_end_market 1. Panel coverage **945 of 8,981
names** (939 of the 6,546 that survive the floors) against MARKET-GRAPH-1's
**386**.

### W4's new verdict: CANNOT DETERMINE (underpowered) on all three arms — and the direction is the finding

Floors applied to the **training** universe before any regression
($3m/day AND close >= $5): 925,757 -> **530,447 rows (57.3%)**, 8,981 -> 6,546
names.

| arm | months | best controlled FM t | family-max Sidak p | SPA p | PBO |
|---|---|---|---|---|---|
| `companyworld_only` (1999-2013, never seen) | 40 | `cust_mom_ew` **0.297** | 0.96 | 0.61 | **0.957 OVERFIT** |
| `market_graph_1_only` (2014-24, W4's own) | 105 | `cust_mom_ew` **1.447** | 0.74 | 0.11 | 0.343 FRAGILE |
| `pooled` | 145 | `cust_mom_ew` **0.989** | 0.97 | 0.17 | 0.514 OVERFIT |

Family size 9 per arm. DSR 0.186 / 0.376 / 0.616 — all `WITHIN_SELECTION_NOISE`.
Years-to-t2 32.3 / 23.5 / 14.5 against 12.1 observed.

**Same prompt, same taxonomy, same liveness rule; only the years changed, and
customer momentum fell from t 1.45 to t 0.297.** "The graph is too small" was
W4's stated reason for not concluding. It is now answered rather than
outstanding: **more tape made it weaker.** This closes the scope excuse, not
financial graphs.

**Cost: $2.12 of the $10.00 cap**, 3,462 calls, every one priced. The provider
balance moved 13.38 -> 10.21 = $3.17, which is an **upper bound and not this
job's cost** — §2b was drawing on the same key over the same window. The pilot
projected $0.0988/100 filings, i.e. $11.71 for the full 11,850-filing worklist,
so the **sample was cut rather than the cap exceeded**.

Receipts: `W4b_companyworld_extract_pilot.json`,
`W4b_companyworld_extract_run01.json`, `W4b_companyworld_rerun_run01.json`,
`W4b_cost_reconciliation_run01.json`, `S3_graph_receipt_provenance_run01.json`

---

## 2b. THE LLM READING TEST — 192 windows, four arms, and every one of them is negative

The prompt said "Friday's L10 built the scaffolding". **It did not** — L10 was
never run; there is no L10 receipt in `night_lab_2026-09-05/`. The scaffolding
was built this session.

2016-01..2019-12, **192 windows** (all of them, not the 200 ceiling), 8 names
per window, top 3 held, gpt-5-nano rewriter at `reasoning_effort="minimal"`
(`temperature` is a 400 on that model and is not sent), DeepSeek decider at
T=0, **rank graded only** — the LLM never sees or produces a price — benchmarked
against the equal-weight basket of **the same 8 anonymised names in the same
month**, 10 bps, $3m/day and $5 floors.

| arm | windows | mean IC | t (month blocks) | mean net top−EW |
|---|---|---|---|---|
| fantasy, no diary | 192 | −0.0314 | −0.964 | −0.393% |
| fantasy, diary | 192 | −0.0259 | −0.811 | −0.127% |
| real-anon, no diary | 190 | −0.0427 | −1.294 | −0.308% |
| real-anon, diary | 190 | −0.0530 | −1.621 | −0.518% |

Family size 4, **family-max p 0.729**, min p 0.175, **nothing survives BH at
0.05**. DSR of the best arm **0.0205**. Nulls 1-3 all one-sided p > 0.72, and
null 3 — the same-day paired statistic, which is the primary one because the
month effect cancels — is **−0.449%, t −0.678**.

**The memorisation canary is clean: 0 of 192 exact-year hits against a 0.25
chance rate, 0% company-named.** When the model did guess a year it said 2023
(75) or 2024 (24) — i.e. it guessed its own training era, not the era it was
reading. That is the control working.

**Reading: on 2016-19, a DeepSeek decider reading rewritten filings ranks
WORSE than the equal-weight basket of the same names, in all four arms, and the
diary does not help.** The fantasy-vs-real-anon contrast — the memorisation
question — is not answerable here, because neither arm is above zero.

One defect worth more than the table: `rewriter_integrity` shows
**195 of 382 bundles preserved every magnitude**; the rest silently dropped
numbers (e.g. 104 expected, 96 found). A rewriter that drops magnitudes has
changed the information the decider sees, and it is a confound on any future
positive result from this rig.

**Cost: $0.3175** — gpt-5-nano $0.1587 (215 calls, telemetry; OpenAI exposes no
balance endpoint) + DeepSeek $0.1589 (724 calls) — against a $4.50 working cap.

Receipts: `L10_era_replay_windows.json`, `L10_era_replay_v2_pilot.json`,
`L10_era_replay_v2_run01.json`

---

## 2c. THE NEURAL ARM UNDER THE FLOOR — **B10 NOT EARNED**

The decision rule was written to disk and hashed **before** the run
(`W3b_neural_floored_run01_declaration.json`, sha `428a7148f61942b0…`), and the
object judged is the **seed-mean ensemble**, never the best cell.

Floored **training** universe (not only grading): 530,447 of 925,757 rows.
251 months, 8 seeds x 2 arms x 21 folds, on the CUDA interpreter
(`python_executable` = system Python 3.12, torch 2.11.0+cu128, RTX 5060).

| arm | TW net @10bps | vs market |
|---|---|---|
| market | 14.378 | — |
| `lgbm_clf` (mandatory baseline) | 22.608 | — |
| `lgbm` (W3's own incumbent) | **36.245** | — |
| nn seed-mean ensemble | 24.134 | +4.58%/yr, t 1.318 |
| nn_pre_causal seed-mean ensemble | 49.008 | +8.14%/yr, t 2.243 |

The pretrained ensemble clears three of the four declared clauses — (a) positive
against both incumbents at both cost rates, (c) TW ahead of both, (d) sign in
2 of 3 eras — and **fails the family-corrected one**: DSR vs `lgbm_clf`
**0.1726** against a 0.95 bar, SPA p 0.108, PBO 0.343, paired t 1.24. It is only
+0.83%/yr over `lgbm` (t 0.23). The supervised `nn` arm fails (a), (b) and (c)
outright: **−2.74%/yr against `lgbm` at 10 bps** (its DSR vs `lgbm_clf` is
0.0294).

Seed spread over 8 seeds at 10 bps: `nn_pre_causal` TW **26.0 / 54.1 / 105.0**
(min / median / max), sd 23.9. The best cell is twice the median seed — which is
exactly why the rule declared beforehand judged the ensemble. Its own inference
looks strong in isolation (DSR 0.8621, SPA p 0.004, PBO 0.1429, MDE 7.35%/yr,
t=2 needs 8.0y against 20.92 observed, 3 of 3 eras positive) and it is **not
promoted**, because a maximum over eight seeds is not a choice a desk could
have made.

Proof the floor bound the FIT and not just the book: the grading floor then
removed **0 of 454,708** gradeable rows, and every graded book has a median
holding trading **$17-29m/day at $27-41 a share, 0% under $5, 0% under
$1m/day** (`floor_at_grading_is_a_noop.pass: true`).

**"B10 not earned" is written into the receipt. The neural loop stops. No
champion frozen, no shadow accrual, and the best cell (TW 105.0) is explicitly
not promoted.**

**The finding that outranks the verdict:** five months carry **83.6% of
`lgbm_clf`'s entire 251-month excess**, and without them the incumbent is
**BEHIND the market** (7.78 vs 8.18). The baseline the neural arm failed to
beat is itself five months wearing twenty-one years — the same shape as the
weekend's own champion (54.3% in five months) and the night lab's L1.

Receipts: `W3b_neural_floored_run01_declaration.json`,
`W3b_neural_floored_run01.json`

---

## 2e. EVIDENCE MEMORY -> REGISTRY

`backend/data/signal_registry.yaml` gains a `conditional_evidence:` block:
**12 rows over 3 families and 4 cells** — `weekend-W3-supervised` (SUPPORTED),
`weekend-W5-options-iv` (SUPPORTED), `weekend-W7b-archetype-book`
(COST_KILLED) — each at four eras (ALL / 1999-2007 / 2008-2015 / 2016-2024)
with `{n, sharpe, dsr, spa_p, pbo, verdict}`. It reconciles exactly against the
snapshot: 327 cells = 4 exported + 15 withheld with the excluded family + 308
IDEA.

**The load-bearing exclusion:** `weekend-W7-matched-loser` is SUPERSEDED by the
matched-control leak, and **9 of the memory's 12 SUPPORTED cells live in that
family**. Every one of them survives the *row-level* rule, because the
supersession boundary (05:40) predates the corrected re-runs and only 101 of
6,199 observations are removed. So the export excludes the family **and names
the count** rather than dropping it silently.

**The superseded-cannot-vote test was proved red, not asserted green.**
`live_rows` was temporarily reverted to the pre-fix behaviour and **5 of 11
tests went red**; the file was restored byte-identical (sha `8ce96ba0b61ea443`
before and after), and `test_the_fixture_can_actually_vote` asserts the pre-fix
SUPPORTED so the others cannot pass vacuously.

**What `e6ce604` did not cover, and this did:** its filter lived inside
`snapshot()` alone, while `read_all` and `state_of` are public and unfiltered —
so this export, the *second* consumer, would have read the whole leaked store
green. Three further silent holes closed: `read_supersessions()` used to skip
unparseable rule lines (skipping an observation costs one data point; skipping
a supersession re-admits a retracted experiment); `before_utc: "2026-09-05"`
excluded **nothing** because the comparison is lexicographic; and a rule
matching zero rows now carries a WARNING instead of reading as "applied, no
effect".

Inert for the PM, proved rather than asserted: `Registry.__dataclass_fields__`
has five keys and no sixth, and
`test_no_reader_of_the_registry_consumes_conditional_evidence` greps every `.py`
in the repo — asserting **>500 files were actually scanned**, because an empty
search is not evidence. Idempotent: three runs, sha `3224a851…` each time, no
wall clock in the block, everything outside the two markers byte-identical
including CRLF.

Open for a human: `weekend-W7b-archetype-book` IS exported while
`weekend-W7-matched-loser` is not — the supersession rule names only the
latter, and W7b is the archetype *book* built on W7's candidates. If the
control-pool fix touches it, that needs a second rule. **The job did not invent
a retraction.**

Receipt: `B6_evidence_to_registry_run01.json` · tests 11 + 32 passed

---

## 2f. THE REVISION BOOK CONTRACT — DRAFTED, NOT FROZEN

`docs/CONTRACT_DRAFT_2026-09-06_REVISION_BOOK.md`. Six `REQUIRED_FIELDS` filled
from the terminal repo's real `alpha/contract.py`: horizon 126, min hold 42,
per-cohort `thesis_expiry`, three revision-specific falsifiers, ~$27/name risk
budget, and the real six emergency exit reasons quoted verbatim. Licence asked
for: **`PRODUCT_EXPERIMENT`**.

The power line, as written: *the tape says this needs ~36 years to reach t = 2
at its own Sharpe; we hold 25.7; forward paper cannot adjudicate the alpha
claim, not this year and not this decade; the book exists to test holding
discipline and regret, not alpha.* Followed by the tail — 54.28% of the excess
in five months, +3.128%/yr at t 0.844 without them.

**Two blockers it found, neither fixed, both Murat's call:**
1. `alpha/contract.defaults_for` branches on
   `TRACKER_BOOKS = ("hack3","hack4","hack6")`. **hack2 falls through to the
   EVENT defaults — horizon 3, min hold 0, `profit_target_frac` 0.025** — so a
   hack2 seal today gets a 3-session contract with a +2.5% target and holds
   nothing.
2. `alpha/fleet.py:104` gives hack2 profile `aggressive` = a **3% stop**, the
   exact "stop inside the noise is a fee" failure its own header names.
   There is also no cohort id field, so the ledger cannot group by cohort.

It also **refused a number**: `net_rev_4w` **under the tradable floor is NOT IN
A RECEIPT** — W9 run40's `cells` rows all carry `tradable_floor_usd: null`, and
its power/tail/era blocks are computed on the *champion* arm, not on
`net_rev_4w`. Unfloored, `net_rev_4w|high|10bps` is TW 22.859 vs market 13.182,
**+2.53%/yr t 1.038**; at 25 bps it is **−0.98%/yr, t −0.402**. The entire
result is the cost assumption, and the draft says so in its own scoreboard.

---
