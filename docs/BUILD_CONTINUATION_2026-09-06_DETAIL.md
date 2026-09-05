# BUILD — CONTINUATION 2026-09-06 — DETAIL

**The 2-page deliverable is `BUILD_CONTINUATION_2026-09-06.md`.** This file is
its appendix: the full tables, the mechanisms, and the in-session retractions.

Mandate: `docs/CONTINUATION_2026-09-06_OPUS_PROMPT.md`. Nothing pushed, sealed,
ordered, deployed or changed on Railway. Every number below has a receipt path.

---

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** Nothing reached NOVEL. Two of the three research
questions closed NEGATIVE with the evidence to say so, one closed
CANNOT DETERMINE, and the strongest new number is about the **baseline**, not
about any candidate.

| KPI | This session |
|---|---|
| Best historical net strategy vs the market | unchanged: `target_rev_1m__xs` top-50 VW, TW **85.324** vs VW market 13.031 (t 2.407) — but **+4.01%/yr t 0.859** vs an EW market and **DSR 0.1239** over its own 307-trial search. Still not a finding. |
| Best forward paper strategy | none. The books are flat by design; hack3/4/6 are dry-run only this session |
| Independent selector count | **unchanged at 1.** Nothing promoted. The neural arm was refused, the graph arm did not replicate, the LLM arm is negative |
| Farm candidates tested / promoted | **3 tested / 0 promoted** (companyworld graph features, floored neural encoder, LLM era-replay decider) |
| New actionable finding | **the mandated baseline is five months.** 83.6% of `lgbm_clf`'s 251-month excess sits in five months, and without them it is BEHIND the market (7.78 vs 8.18). Every "beats/loses to lgbm" statement in this repo is a comparison against a beta-timing artefact |
| External execution drag | not measured this session — no orders, no seals, no deploys |
| LLM spend / cost per gradeable output | **$4.14 of a $15.00 cap.** DeepSeek $3.98 provider-measured; gpt-5-nano $0.16 telemetry. 4,598 calls. **$2.12 bought 2,020 supply-chain edges (~$0.00105/edge) and $0.48 bought 768 graded LLM rank decisions (~$0.00063/decision).** And a defect: our ledger prices only **56%** of what the provider charged |

### The five things a reader should take away

1. **The CUDA question is answered and it was a different interpreter, not a
   downgrade.** The GPU numbers were always real; the receipt could not say
   whose they were, and now it can.
2. **Buying more supply-chain tape made the graph result WEAKER**, not
   stronger. Customer momentum: FM t 1.447 on MARKET-GRAPH-1's own 2014-24
   window, **t 0.297** on the never-seen 1999-2013 window. The scope excuse is
   answered rather than outstanding.
3. **B10 is not earned and the neural loop is stopped**, on a rule declared and
   hashed before the first fit, judged on the seed-mean ensemble.
4. **The LLM cannot read 2016-19 filings into a rank that beats the equal-weight
   basket of the same names** — all four arms negative, family-max p 0.729,
   memorisation canary clean at **0 of 768 decisions**. Blinded, the decider
   assumes it is NOW: of 243 year guesses, 190 said 2023 and 53 said 2024, and
   **not one said 2016-2019**.
5. **Four of the adversarial review's six ranked next moves were already closed
   before this session started, and I called one of them open by reading the
   receipt the review quoted instead of the newest one.** The correction is in
   the receipt.

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
| 5 | re-run W10 through the runner so it has a durable receipt | **DONE — and it was already done before this session.** 29 `W10_decay_autopsy_run*.json` exist, 13:30-17:00 on 09-05; the review's filesystem check was true at 13:07 and stale sixteen minutes later. I ran one more at 20:21 on the rebuilt panel to confirm |
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

| arm | IC | t(IC) | net vs EW %/mo | t | TW book | TW EW | ratio | canary |
|---|---|---|---|---|---|---|---|---|
| fantasy, no diary | −0.031 | −0.96 | −0.393 | −1.05 | 1.549 | 1.939 | 0.799 | 0.000 |
| fantasy, diary | −0.026 | −0.81 | **−0.127** | −0.35 | 1.759 | 1.939 | 0.907 | 0.000 |
| real-anon, no diary | −0.046 | −1.34 | −0.353 | −1.00 | 1.577 | 1.939 | 0.813 | 0.000 |
| real-anon, diary | −0.053 | −1.58 | −0.530 | −1.39 | 1.459 | 1.939 | 0.752 | 0.000 |

Family size 4, **family-max p 0.729**, min p 0.175, **nothing survives BH-FDR
at 0.05**. DSR **0.081** WITHIN_SELECTION_NOISE, SPA p **1.00**, PBO 0.386. Nulls 1-3 all one-sided p > 0.72, and
null 3 — the same-day paired statistic, which is the primary one because the
month effect cancels — is **−0.449%, t −0.678**.

**The memorisation canary is clean: 0 of 768 decisions named the true year,
0% company-named.** When the model did volunteer a year — 243 times of 768 — it
said **2023 (190) or 2024 (53)**, and **not once 2016-2019**. Blinded, it
assumes it is now. That is the control working, and it is the first time the
blind has been measured on a pre-2023 era.

**Reading: on 2016-19, a DeepSeek decider reading rewritten filings ranks
WORSE than the equal-weight basket of the same names, in all four arms, and the
diary does not help.** The fantasy-vs-real-anon contrast — the memorisation
question — is not answerable here, because neither arm is above zero.

~~One defect worth more than the table: `rewriter_integrity` shows 195 of 382
bundles preserved every magnitude~~ — **RETRACTED 2026-09-06, in-session, by the
agent that produced it.** That number was the CHECKER's bug, not the rewriter's:
the first checker regexed the whole fact card and counted field NAMES as data,
so "12-1 momentum" contributed a 12 and a -1, "4 weeks" a 4, "rating 3.33 of 5"
a 5, "60d volatility" a 60 — and a **perfect** rewrite scored 0%. Against the
actually emitted values, preservation is **97.9% (fantasy) / 98.4% (real-anon),
arm gap 0.005**, and `leak_check` is clean on **384 of 384** bundles. The
confound does not exist, and **the arm gap is the number that decides whether
the 2x2 is comparable at all** — which is why it was the right thing to ask.

Two sibling defects, both of which also failed silently and were caught by the
same integrity pass: `deepseek-chat` abbreviates "Company A" to "A", which lost
**every** real-anon window while the table still printed; and `gpt-5-nano` keys
its JSON on the whole heading line, which lost 11 of 20 bundles.

Three things that DO survive, and are better than the arms table:

1. **The blind held: 0 of 768 decisions named the true year.** First time
   measured on a pre-2023 era.
2. **Blinded, `deepseek-chat` assumes it is NOW.** Of 243 year guesses, 190
   said 2023 and 53 said 2024; not one said 2016-2019.
3. **The diary SUPPRESSES the canary** — 191 of 192 no-guess with a diary
   against 93 and 50 without. **An in-band canary is weaker evidence than it
   looks**, and the next replay must ask it in a separate call.

One loud refusal: the **EDGAR 8-K item tape was refused as a source.** Its own
manifest resolves the universe through `company_tickers.json`, i.e. CURRENT
registrants, so 8-K presence in 2016-19 correlates with survival to 2026 — a
forward-looking leak straight into the prompt. The refusal travels in the
window receipt.

And the null that matters: a **random ranking already loses about −0.20%/mo**,
because a top-3-of-8 book pays turnover the basket does not. So null 1 is the
real test, and its p-values are 0.72 / 0.41 / 0.68 / 0.85 — three arms rank
*worse* than chance and the fourth is chance.

Verdict **NOISE**: TW ratio 0.75-0.91 against the same-name basket, DSR
**0.081** WITHIN_SELECTION_NOISE, SPA p **1.00**, PBO 0.386, **MDE 8.75%/yr on
48 month blocks**. NOISE here means *not detectable on four years*, not
*absent*; the three-era table is CANNOT DETERMINE because one era was run.

**Cost: $0.4817** of the $5.00 cap — gpt-5-nano $0.3032 (telemetry; OpenAI
exposes no balance endpoint to this key) + DeepSeek $0.1785. About **$0.0006
per graded rank decision**. Money was never the constraint; independent months
were.

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

**Verified independently from `robustness.*.tail` in the receipt** — and the
nuance matters more than the headline:

| object | 5 best months | share of total excess | TW without them | market without them |
|---|---|---|---|---|
| `lgbm_clf` (mandated baseline) | 2020-05, 2020-03, 2008-11, 2009-03, 2018-12 | **83.55%** | **7.78** | **8.18** (BEHIND) |
| `lgbm` (W3's incumbent) | 2020-05, 2009-03, 2008-11, 2024-04, 2023-11 | 69.12% | 9.89 | 9.41 |
| `nn` seed-mean | 2009-02, 2009-03, 2020-03, 2022-07, 2022-06 | 68.54% | 8.01 | 8.31 (BEHIND) |
| `nn_pre_causal` seed-mean | 2020-03, 2020-05, 2009-03, 2022-07, 2023-11 | **33.51%** | **17.27** | 8.25 |

Both incumbents' tails are the GFC and COVID bottoms. **The arm that failed the
family correction is by far the LEAST tail-dependent object in the comparison**
— 33.5% against the baseline's 83.6%, and it is still ahead of the market with
its five best months removed. That does not earn B10, and the declared rule was
not softened for it. It does mean the thing the ladder is built on is worse than
the thing that failed to climb it.


Receipts: `W3b_neural_floored_run01_declaration.json`,
`W3b_neural_floored_run01.json`

---

## 2d. MONDAY MUST LEARN — and the dry run found the thing that would have gone wrong

Terminal repo, four commits (`5e27070`, `c253ede`, `c01043d`, `d28742b`).
**`python run_tests.py` -> 76 suites, 3,483 checks, ALL PASS** (session-start
baseline 74 suites / 3,367 checks), from a run that completed after the
`taskkill` and was re-run after the last commit with the same numbers.
Nothing sealed, ordered, deployed or pushed.

### 1. Every CANNOT DETERMINE on the learning report now names whose fault it is
Each refusal carries `cause`: **PLUMBING** (our wiring failed to deliver an
input that exists) or **NO_DATA_YET** (a correct refusal that stays). The
header prints `REFUSALS: n OUR PLUMBING | m no data yet`. Wired: live-equity
fallback (reads `GET /v2/account` per role, and **only** uses it when the
account's own session day IS the report day, so today's equity can never be
stamped onto an earlier day — pinned by test), the counterfactual marker, the
shadow path (`AEGIS_SHADOW_DIR`, then two fallbacks, because a rename or a
case-sensitive mount is not a missing shadow), the tracker path, and **one SPY
close source** (`alpha/spy.py`, `feed=sip`). There were **four readers on two
tapes**: this report used `config.stock_feed()` = `iex` while
`move_decomposition` and `logic_brain` used `sip`. Same page, same day: SPY
genesis close **769.28 (iex) vs 769.35 (sip)**. And the report was parsing all
**1.07 GB** of `counterfactual.jsonl` on every run — now a bounded 64 MB tail.

**Measured on 2026-09-04: the counterfactual marker last wrote 2026-08-28 —
eight days dead.** The page had been reporting that as "either nothing was
refused, or the marker did not run", which is exactly the undifferentiated red
line that teaches a reader to skim. Likewise `books_vs_fills` printed "normal
for non-tracker roles" for all three tracker books on a day when **no seal
existed at all**.

What still says CANNOT DETERMINE, and which kind: **honest** — the shadow,
because the finance repo's learner wrote 09-02 and no later day and owes the
terminal nothing. **Plumbing, and not this session's to fix** — the
counterfactual marker and the tracker refresh, which are the stopped Railway
loops; reviving them is `fleet --deploy --up`, attended.

Also found on the way: **`python run_tests.py` was writing into two PRODUCTION
ledgers** — `state/decisions.jsonl` (six fictional PANW/NVDA exit rows, from
`tests_smoke_contract.py` calling `exits.manage(dry_run=False)`, which the
learning report was counting as real exits) and `state/llm_spend.jsonl`
(caller `tests.smoke`, i.e. **inside the budget gate's own input**). Fixed with
a per-run `AAT_LEDGER_DIR` plus a before/after fingerprint tripwire. **The rows
already written were NOT deleted** — the hash chain has been torn since 25 Aug
and repairing it *is* the tampering.
(`B3_1b_test_suite_wrote_production_ledgers.json`.)

### 2. `daily_autopsy` writes a receipt every night, and the misses are typed
Every exit path of both scripts now writes `state/autopsy/<day>.json`, including
the empty and refused paths; the session day is derived from
`alpha.exits.session_day()` — the repo's one clock — and the bars only confirm
it. `alpha/recall.py` is new and pure: one row per mover in
`state/opportunity_recall/<day>.jsonl`, typed `NOT_OBSERVED` (repair =
COVERAGE) / `GENERATED_NOT_RANKED` (repair = MODEL) / `RANKED_NOT_BOUGHT` /
`BOUGHT_SOLD_EARLY`, **both sides of the tape** — `winner_recall` is reported
beside `loser_avoidance`, because either alone is maximised by a book with no
discipline.

**"The whole market" was seven names.** The venue's mover screener returned 7
names at or above $3 for 2026-09-04, missing NX +22.2%, GWRE −19.9%,
LULU −17.4%, FICO −16.7%, PATH −16.6%, ADSK −8.3% and a five-name
LOSS:Technology cluster. The union with our own universe gives **23**. And of
those 23, **16 were NOT_GENERATED** — *not one of the day's sixteen biggest
movers was on the candidate list, in either direction.*

The recall status for the day is **CANNOT DETERMINE** and that is the guard
working: judging day had no seal after the 10:45 liquidation, so `ranked` is
UNKNOWN, not empty, and the ledger refused to type 23 names
`GENERATED_NOT_RANKED` and blame a stage.

### 3. THE MONDAY DRY RUN — and hygiene-only, implemented literally, EMPTIES hack6

Tracker vintage 2026-09-02, replayed under both band modes. **Nothing sealed,
nothing ordered, nothing published.** Full printout:
`backend/data/optimus/continuation_2026-09-06/B3_3_monday_dry_run_printout.txt`,
attached to `docs/RUNBOOK_2026-09-08_REARM.md`.

| book | k | RETURNS mode | HYGIENE_ONLY mode | binding constraint under hygiene-only |
|---|---|---|---|---|
| hack3 | 10 | **10 admitted**, 83% gross, worst case −6.64% | **5** | `exp_return not positive` — 799 of 810 fail it, 413 fail *only* it |
| hack4 | 5 | **5 admitted**, 50% gross, worst case −3.00% | **5** (same names) | `exp_return not positive` — 20 fail only it |
| hack6 | 15 | **15 admitted**, 90% gross, worst case −2.70% | **0** | `exp_return not positive` — 185 fail only it |

**This is the decision Murat has to make and did not know he was making, and
the mechanism is exact.** Decision B.1 §4a retires the band's four *return
constants* and keeps hygiene. But those constants were not only an exclusion
rule — **they were the SOURCE of `exp_return` for every name they covered.**
Without them `score()` falls back to `(2 * p_up - 1) * claimed` off the
152-name panel, whose **unconditional `p_up` is 0.4615**, i.e. negative for
everything the rule does not fire on. **799 of 810 candidates then fail the
coherence floor, against 35 of 806 today** — hack3 10 → 5 with an entirely
different five (LOVE, RZLT, RFIL, LAES, AVAV), hack4 5 → 5, hack6 **15 → 0**.
Hygiene-only is not a loosening; on this vintage it is the tightest rule in the
stack, and implementing 4a literally on Monday arms three books and fills one
and a half of them.

**Hygiene itself is innocent**: it excludes 33 of 810 and its `fails_only` is
**ZERO in all three books**. So §4a needs one companion decision from Murat —
*what feeds `exp_return`*, or *whether the coherence floor should apply to a
transferred base rate at all*. `AAT_BAND_MODE=hygiene_only` exists, is **OFF by
default**, the live fleet is byte-identical without it, and both modes are
pinned by tests.

**Two more things Monday would have hit.** The 10:01 pass, run dry against the
live venue, returns **EXIT=2 on all three books** — *"no sealed book for
2026-09-05 … Declining rather than re-deriving"*. That is the artery working as
built, and it is also the whole Monday risk in one line: **no seal, no
entries.** And `RUNBOOK §6b` told the reader to pass `--dry-run` to `run_pass`;
**that flag does not exist** (`error: unrecognized arguments`). Both corrected
in the appendix.

The dry run used vintage **2026-09-02**, the newest on disk — a seal dated today
is correctly refused at 3 sessions stale, and the agent **declined to run
`--refresh`**, because a half-finished refresh leaves a fresh-*looking* partial
vintage that Monday would seal on. Reproduce:
`AAT_ACCOUNT_ROLE=hack1 python -m scripts.monday_dry_run --compare`.

The binding constraint is reported as `only` (names failing **nothing else**),
not as first-fired — `fails` vs `only` diverge by an order of magnitude
(hack6 returns-mode: 543 fail the 20% downside cap; **375** fail only it).

**Entry authority, and an honest refusal:** hack1 DISARMED (`manage_only`);
hack2, hack3, hack4, hack5, hack6 **ARMED**. Two of the four possible disarms
are **Railway variables and invisible from this machine** — the block says so
and refuses to guess.

**hack2 is ARMED and is not a tracker book.** `contract.defaults_for` branches
on `TRACKER_BOOKS = (hack3, hack4, hack6)`, so hack2 falls through to the EVENT
defaults: **horizon 3 sessions, min hold 0, `profit_target_frac` 0.025** — one
armed book with no minimum hold and a +2.5% target, which is precisely the
churn the whole minimum-hold build was written to stop. Independently found by
the §2f agent from the other side. **Not fixed: which defaults hack2 gets is
Murat's call.**

Receipts: `B3_1_learning_report_plumbing.json`,
`B3_1b_test_suite_wrote_production_ledgers.json`,
`B3_2_autopsy_and_opportunity_recall.json`, `B3_3_monday_dry_run.json`,
`B3_3_monday_dry_run_printout.txt`

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

## W10 RE-RUN ON THE REBUILT PANEL (review item 5)

`W10_decay_autopsy_run01_v0.json`, 20:21. Same conclusion, better book:

```
gross TW 4.3086 vs market 4.8636 in 2016-2024   (the review's scratchpad: 3.6944 vs 4.8636)
not_a_size_migration      equal-weighted t -0.381 in 2016-2024
dispersion_intact         within-month sd 0.1065 vs 0.1048 (1.02x)
still_alive_at_3m         3-month decile-spread t 3.78 in 2016-2024
slower-rebalance cells alive in 2016-2024 at t >= 2: NONE
verdict: AUTOPSY (arbitraged_away)
```

The market leg is identical to the digit (4.8636); only the book moved, and the
share-basis rebase moved it **up**. The mechanism reading is unchanged: the
signal still separates deciles at 3 months and no slower-rebalance book can
monetise it.

---

## CLAIMS FOR FABLE TO ATTACK

Ranked by how much would change if the claim is wrong. Each names the receipt
that carries it.

1. **The CUDA numbers were always real; the receipt just could not say whose
   they were.** The directory-mtime argument is the whole proof — if
   `site-packages`' mtime can move without an add/remove on Windows (an
   antivirus rewrite, a `pip check`, a metadata touch), the argument fails and
   the downgrade hypothesis returns. `S0_cuda_drift_run01.json`.
2. **`target_rev_1m__xs` beats a cap-decile-matched draw at t 2.496 and an
   equal-weighted market at t 0.859.** The control replaces each holding with a
   uniform draw from the same within-month cap decile at identical weights, and
   pays the BOOK's cost series. Attack the decile construction
   (`qcut` on `rank(method="first")`, ties broken arbitrarily) and the choice to
   hold cost fixed. `S2_size_matched_control_run01.json`.
3. **More supply-chain tape made customer momentum WEAKER** — FM t 1.447 on
   2014-24 to 0.297 on the never-seen 1999-2013. Attack the extraction:
   resolution is 31.1%, and the 68.9% that does not resolve is assumed to be
   non-US-listed rather than a resolver failure. If the unresolved mentions are
   systematically the *large* counterparties, the new arm is a different graph,
   not the same graph on a different era. `W4b_companyworld_rerun_run01.json`.
4. **B10 is not earned.** The pretrained ensemble is +8.14%/yr with t 2.243 and
   fails only on the family correction (DSR 0.1726). Attack the family: it is
   every cell across both arms and both cost rates from this job alone. A
   reader who thinks the family should be *larger* makes the verdict stronger;
   one who thinks it should be per-arm makes it weaker. Say which.
   `W3b_neural_floored_run01.json`.
5. **The mandated baseline is itself five months.** 83.6% of `lgbm_clf`'s
   251-month excess, and behind the market without them. If true, every
   "beats/loses to lgbm" statement in this repo's history is a comparison
   against a beta-timing artefact. Same receipt.
6. **The LLM cannot read 2016-19 filings into a rank that beats the equal-weight
   basket of the same names.** All four arms negative, family-max p 0.729,
   canary clean at 0 of 768 decisions. The rewriter-degradation confound I first
   published here was **retracted in-session** — a checker bug; true preservation
   is 97.9%/98.4%. Attack the POWER instead: MDE is **8.75%/yr on 48 month
   blocks**, so this reads "not detectable on four years", and anyone taking it
   as "LLMs cannot read filings" is over-reading it.
   `L10_era_replay_v2_run01.json`, `docs/FINDING_2026-09-06_ERA_REPLAY_V2.md`.
7. **Nine of the evidence memory's twelve SUPPORTED cells are in a superseded
   family, and all nine survive the row-level rule** because the supersession
   boundary predates the corrected re-runs. The export excludes the family
   wholesale. Attack that: is wholesale exclusion right, or should the
   corrected re-runs be allowed back in under a narrower rule?
   `B6_evidence_to_registry_run01.json`.
8. **W4b's three receipts named the wrong edge file** and only `source_rows`
   disagreed. Fixed and proved red. Attack whether any *other* receipt in this
   repo stamps a module default in place of an argument — I checked
   `features_graph` and nothing else. `S3_graph_receipt_provenance_run01.json`.
9. **All six of the adversarial review's ranked next moves are closed, and four
   of them were closed before this session began.** If any of the four is
   actually still open, the correction record above is wrong in the same way I
   was wrong about W9 the first time. `S1_...json` (`CORRECTION_...` field).
10. **The venue screener called seven names "the whole market".** The union with
    our own universe gives 23, and not one of the day's sixteen biggest movers
    was on the candidate list in either direction.
    `B3_2_autopsy_and_opportunity_recall.json`.

---

## LLM SPEND, TO THE CENT — and a defect in how we count it

| provider | measured how | this session |
|---|---|---|
| DeepSeek | **provider balance**, 13.36 -> 9.38 | **$3.98** |
| gpt-5-nano | telemetry (OpenAI exposes no balance endpoint to this key) | **$0.16** |
| **TOTAL** | | **$4.14 of a $15.00 cap** |

By purpose (telemetry attribution): `companyworld_edges` **$2.12** of its $10
sub-cap, `era_replay_v2.decide` **$0.48** of its $5 sub-cap, everything else
**$0.00**. 4,598 calls. Unit economics: **$0.00105 per supply-chain edge** and
**$0.00063 per graded LLM rank decision**.

**The defect: our ledger prices only 56% of what DeepSeek charged.** Telemetry
totals $2.22 across 4,201 calls, 12.83M input and 1.43M output tokens; the
provider took $3.98. If the table's 1:2 in/out ratio holds, the implied rate is
**$0.2535/Mtok in — 1.81x** the $0.14 in
`backend.config.LLM_PRICE_PER_MTOK["deepseek-v4-flash"]`.
`research_budget.require()` enforces its DOLLAR ceiling against that ledger, so
a $10 dollar-gate would in fact stop near $17.90 of real spend. **The CALL
ceiling is the hard one for exactly this reason, and it is what held here.**
Not fixed from an inferred constant — the fix is to read the published price
list with the network available and re-derive both legs.

Receipt: `S4_llm_spend_reconciliation_run01.json`

---

## WHAT I COULD NOT DO, AND WHY

1. **The full 11,850-filing 10-K worklist was not extracted.** The pilot
   projected $11.71 against a $10.00 sub-cap, so the sample was cut to 1,486
   filings rather than the cap exceeded. Coverage is 1999-2011; **2012-13 are
   absent.** The verdict is not sensitive to it — the direction is already
   down — but the window is not what §2a asked for.
2. **B5 §3-§5 (the 8-K event schema, the case-company FACT rows, the first
   consumers) were not started.** §2 (the historical permno-CIK link) fell out
   as a by-product: 30,638 of 51,001 filings linked, 60.1%.
3. **B7 §3-§4 (the fantasy stress exams and the live pre-open bridge) were not
   started.** One era ran, so the three-era table is CANNOT DETERMINE by
   construction.
4. **The Optimus MCP server was down for most of the session** — collateral
   damage from the `taskkill`. `session_briefing()` and
   `aegis_verified_state()` ran at the start; `brain_query` was unavailable
   afterwards. `python tools/refresh_aegis.py` ran at the end and succeeded
   (aegis-finance sha `da8875d`, 245 session-memory pages, 470 doc pages).
5. **Nothing was pushed, sealed, ordered, deployed or changed on Railway**, by
   design.
6. **A branch note that needs a decision.** The working tree is on
   `lab/weekend-2026-09-06`, not `main` — `main` was at `c45a825` when this
   session opened and the branch was already checked out. All 20 commits landed
   on the branch. `main` is a strict ancestor, so a fast-forward is lossless and
   is what the mandate ("commit locally on `main`") intends; it is applied at
   the end of the session and both refs then point at the same commit. Nothing
   is rewritten and nothing is pushed.

---

## THE ONE-LINE VERDICT

Three mechanisms were bought, built and measured this weekend and **none of
them beat what we already had.** The most useful thing produced is not a
candidate — it is the discovery that **the incumbent we measure candidates
against is itself five months of beta timing**, which means the whole
comparison ladder has been resting on an artefact. That is worth more than any
of the three arms, and it is the first thing the next session should act on.


## ONE MORE, AT MY OWN EXPENSE: I WROTE A GATE THAT COULD NOT GO RED

Waiting for the final suite, I wrote a poll loop around

```bash
if ! tasklist /FI "PID eq 109648" | grep -q 109648; then echo "pytest exited"; fi
```

`tasklist` with a non-matching filter prints `INFO: No tasks are running...` and
**exits 0**, and in Git Bash the filter did not match a live PID at all, so the
loop reported "pytest exited" at t=0 while the process was sitting at 958 MB and
still collecting. It is the same shape as `reference_gate_that_cannot_go_green`
and as the share-basis gate this session verified: **a check whose negative
branch is unreachable is not a strict check, it is an absent one.** The
replacement asks the OS directly and compares to a literal:

```bash
powershell -NoProfile -Command "if (Get-Process -Id $PID) {'ALIVE'} else {'GONE'}"
```

Recorded because it happened in the same session that shipped two guards against
exactly this, which is the useful part of the anecdote.
