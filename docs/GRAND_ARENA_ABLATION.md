# GRAND-ARENA-1 · Chunk 9 — ABLATION-1

**Thirteen arms, a six-rung placebo ladder, 119 month-end decisions on a
40-name panel, 2015-01-30 → 2024-11-29. 16,032 historical DeepSeek calls
(12,906 swarm · 2,475 generic · 651 random-text) yielding 45,268 directional
forecasts, of which 36,468 are the swarm's. 0 new calls made tonight.**

Pre-registered `TRIALS/PREREG_ABLATION_1.md`, committed **before a single
historical LLM call in this campaign was issued** (`58857e9` / `46d3d95`).
Runner `scripts/run_ablation_1.py`, `arena_llm_hist.py`, `arena_llm_score.py`,
`ablation_fwd.py`; supplements `ablation_placebo_matched.py`,
`ablation_family_check.py`. Receipts `data/factory/ablation_{1,2}.json`,
`ablation_2_{no,only}famous.json`, `ablation_placebo_matched.json`,
`ablation_family_check.json`, `ablation_fwd.json` (untracked — `/data/` is
gitignored).

Binding law: `docs/GRAND_ARENA_1_AMENDMENT_A.md`. **A3** (raw AND matched),
**A4** (the six-arm ladder), **A5** (neutral specialist priors), **A6** (HIST and
FWD are separate evidence classes), **A8** (complete denominator, DSR for the
family), **A11** (what may be called a breakthrough).

---

> ## Verdict: **`PRESENTATION_AND_RESEARCH_ASSISTANCE` — the frozen words. Full Optimus is not distinguishable from its own shuffled scores under any risk matching, and the fourteen-persona architecture is beaten on its own information metric by one generic agent.**
>
> **H2, the decisive arm.** Full Optimus returns **−2.97 %/yr** excess. Its own
> scores, permuted across ticker and date so the distribution is exactly
> preserved, return **−5.73 %/yr** on average — and the observed value sits
> **inside** that permutation distribution, at **p = 0.105**. Beta-matched:
> **p = 0.125**. Volatility-matched: **p = 0.145**. On the leakage-clean
> subsample: **p = 0.185**. *The gap between Full and no-LLM is +3.37 pp/yr; the
> gap between shuffled-LLM and no-LLM is +1.37. Roughly forty per cent of what
> the language model appears to add is reproduced by permuted noise with the
> same distribution.* Neither number clears its MDE of 8.23.
>
> **H1.** Full − no-LLM = **+3.37 pp/yr against an MDE of 8.23** (t = 1.15,
> 4/4 blocks, halves agree). NOT DETECTABLE, and NOT a kill — the instrument
> cannot see an LLM effect below roughly 8 pp/yr here.
>
> **H3 — the specialist architecture does not justify itself.** Swarm-only minus
> generic-only is **−0.60 pp/yr [MDE 9.69]**: the point estimate is *negative*.
> On the cross-sectional information axis the single generic analyst scores
> **IC 0.0686** against the best of five specialists at **0.0716** and the
> swarm aggregate at **0.0465**. **The best arm in the entire family by Sharpe
> is `llm_only_generic`** — one un-specialised prompt. Chunk 3 measured the
> fourteen roles at a mean pairwise probability spread of 0.059; this is what
> that number costs.
>
> **H5 — information without money, exactly as NIGHT-9 warned.** The LLM-only
> score clears its own IC ruler (**0.0465 vs 0.0445**) while earning
> **−0.08 %/yr against an MDE of 10.60**. Under the standing rule the two are
> reported separately and **neither corroborates the other**.
>
> **The narrow-domain cuts produced three DETECTABLE cells — and the leakage
> control dissolves all three.** Long-horizon forecasts (IC 0.0502 vs MDE
> 0.0452), the `company_fundamental` role (0.0716 vs 0.0625) and
> `generic_analyst` (0.0686 vs 0.0639) all clear on the full sample. Drop the
> 19 decision months inside the leakage canary's famous-event windows and all
> three fall below their rulers. **But that is not evidence of leakage either:
> on those same 19 months the `no_llm` arm — which contains no language model
> at all — rises from IC 0.0326 to 0.0537, and the random-text arm rises from
> −0.020 to +0.065. Famous months are cross-sectionally easier for everything.**
>
> **§20: thirteen arms are 1.77 effective distinct arms**, and two of the
> thirteen (`no_quant`, `llm_only_swarm`) are byte-identical by construction —
> one arm wearing two names, found tonight.
>
> **§A8: the best arm in the family does not survive deflation at any
> denominator.** DSR = **0.29** at 13 trials, **0.53** at the effective 2,
> **0.11** against the campaign's 336. The threshold is 0.95.
>
> **A11: nothing here may be called a breakthrough.** Clause 1 requires LLM
> incremental value surviving risk matching AND the shuffled placebo. It
> survives neither.
>
> **`ARCHITECTURE_RESULT_ONLY` under A6. ABLATION-FWD is `STATED_EMPTY`: 20,073
> records, 0 resolved, first resolution 2026-08-16. No promotion, no
> certification, nothing shipped.**

---

## 0. Which checks ran, and which did not

Stated first, because a report that buries this has already failed CANON.

| check | status |
|---|---|
| six-arm placebo ladder (A4), all rungs | **RAN** — §2 |
| shuffled-LLM, 200 seeded permutations | **RAN** — §3 |
| shuffled-LLM under beta / vol / turnover matching (A3) | **RAN** — §3.2, added tonight; the pre-registered runner reported the placebo raw-only |
| time-shifted LLM, k ∈ {1, 3, 12} | **RAN** — §2 |
| random-text arm | **RAN, BUT ONLY 13.6% COVERED** — §5.2 |
| generic single agent vs specialist swarm | **RAN** — §4 |
| A3 raw + matched on the four principal arms | **RAN** — §6 |
| A3 matched on the nine secondary arms | **NOT RUN** — the pre-registered runner matches four arms; the other nine are reported raw and 0×-gross only, and their gross exposure, concentration and turnover are equal by construction (§6.1) |
| rank-IC with its own MDE, all 13 arms | **RAN** — §7 |
| narrow-domain cuts (size quintile, horizon, role) | **RAN** — §8 |
| famous-event-window flagging | **RAN, AND FLAGGED — not excluded from the primary** — §9 |
| famous-event exclusion + famous-only complement | **RAN as sensitivities** — §9 |
| §20 effective distinct arms | **RAN** — §10 |
| §A8 DSR for the family at three denominators | **RAN** — §10 |
| §A8 PBO / CSCV | **NOT RUN** — §10.3, with the reason |
| §18 difference-of-differences on the famous-month lift | **NOT COMPUTED WITH ITS OWN SE** — §9.3, with the reason |
| no-lookahead perturbation proof | **RAN — PASS**, inherited from chunk 7 §1.5 (13/13 feature columns, 40/40 LLM snapshots bit-identical) |
| ABLATION-FWD | **RAN, and correctly EMPTY** — §11 |
| `no options` arm | **DECLARED_NON_RUN** — §12 |
| `no WHY-MOVED experience` arm | **DECLARED_NON_RUN** — §12 |
| `no specialist reliability` arm | **NULL_BY_CONSTRUCTION**, difference exactly 0.0 — §12 |
| new LLM calls tonight | **ZERO.** Every arm is a re-permutation of stored records; `research_budget.require()` was never reached because no batch was issued |

---

## 1. The instrument, and the one thing that changed since the first run

### 1.1 The panel

| property | value |
|---|---|
| decision dates | 119 month-ends, **2015-01-30 → 2024-11-29** |
| names per date | **40**, seeded stratified sample, 8 per market-cap quintile, fixed by `default_rng(20260812)` before any score existed |
| roles | **five** of chunk 3's fourteen: `company_fundamental`, `analyst_revisions`, `execution_momentum`, `geopolitical`, `skeptic`. **A limitation, not a design improvement.** |
| position budget | K = 10 of 40, `wmax` 0.20, monthly rebalance, G7 costs |
| specialist weights | **neutral/equal (A5)** — the 20,073 forward records are unresolved and pricing reliability off them would be invented authority |
| benchmark | CRSP value-weighted total return |
| ruler | month; MDE = 2.80 × max(Newey-West, IID) SE, annualised (§19) |

### 1.2 The panel was still filling when the first run happened — both runs are reported

The historical harness `scripts.arena_llm_hist` **appends to the calls file while
the ablation reads it.** The first ablation ran at 21:13 against 7,215 calls; the
same command forty minutes later would have seen 15,691. That is not a
reproducible experiment, and the fix is in the runner now: `--calls` takes a
frozen snapshot.

| | **v1** (21:13, `ablation_1.json`) | **v2** (`arena_llm_calls_snap_2153.jsonl`, `ablation_2.json`) |
|---|---:|---:|
| calls | 7,215 | **16,032** |
| swarm cell coverage | 75.25 % | **97.90 %** |
| generic coverage | 22.75 % | **51.32 %** |
| random-text coverage | 6.49 % | **13.55 %** |

**Both are printed throughout.** v2 is the reading, because it is the one whose
panel is nearly complete and whose input is frozen. v1 is printed beside it
because reporting only the run that came second, after seeing both, is exactly
the outcome-shopping this campaign refuses.

**And the comparison earns its keep.** The architecture contrast H3 **changes
sign** between them: swarm − generic is **+3.69 pp/yr at 75 % coverage and
−0.60 at 98 %.** Neither is detectable, and that is the point — *the sign of the
headline architecture result was a function of how much of the panel had been
filled in.* Any reading of the 75 % run that treated +3.69 as "the swarm is
ahead but underpowered" would have been reading fill order.

Uncovered cells are filled **neutral** (`z()` maps a missing leg to 0.0), so a
partially-covered arm is "full with a neutral LLM where the calls were not
made", not "full with noise". At 13.6 % coverage the random-text arm is
**86 % neutral**, and §5.2 says what that costs.

---

## 2. The A4 ladder — all six rungs, in one table

Net excess CAGR %/yr against CRSP VW, K = 10, raw pass, v2.

| # | rung | arm | excess %/yr | its MDE | verdict |
|---|---|---|---:|---:|---|
| 6 | **Full Optimus** | `full` | **−2.97** | 10.24 | NOT DETECTABLE |
| 5 | specialist swarm alone | `llm_only_swarm` | −0.08 | 10.60 | NOT DETECTABLE |
| 4 | one generic agent alone | `llm_only_generic` | **+0.52** | 11.23 | NOT DETECTABLE |
| 4 | generic swapped into Full | `generic_instead_of_swarm` | −4.49 | 10.77 | NOT DETECTABLE |
| 3 | random-text alone | `randtext` | −6.03 | 14.41 | NOT DETECTABLE |
| 3 | random-text swapped into Full | `full_randtext` | −7.09 | 12.33 | NOT DETECTABLE |
| 2 | time-shifted, k = 1 | | −7.25 | 12.41 | NOT DETECTABLE |
| 2 | time-shifted, k = 3 | | −7.09 | 12.45 | NOT DETECTABLE |
| 2 | time-shifted, k = 12 | | −6.72 | 12.46 | NOT DETECTABLE |
| 1 | **shuffled-LLM**, 200 perms | | **−5.73** mean | see §3 | **p = 0.105** |
| — | no LLM at all | `no_llm` | −7.10 | 12.43 | NOT DETECTABLE |

**Nothing in this table is detectable at its own ruler.** The levels are all
negative because the sub-arena forces ~98 % one-way turnover on every arm (the
40 names are redrawn independently every month), which costs roughly 7 %/yr and
is identical across arms — so it cancels in every paired difference and in
nothing else. Chunk 7 §5 established this; the `0× gross` column in §6 is the
readable level.

### 2.1 The paired differences, which is where the ladder actually decides

| contrast | v1 Δ %/yr | v2 Δ %/yr | v2 MDE | t | blocks | halves | verdict |
|---|---:|---:|---:|---:|:--:|:--:|---|
| **H1** Full − no-LLM | +3.13 | **+3.37** | 8.23 | 1.15 | 4/4 | yes | NOT DETECTABLE |
| Full − no-LLM, **gross** | +2.96 | +3.13 | 8.20 | 1.07 | 3/4 | yes | NOT DETECTABLE |
| **H3** swarm − generic | +3.69 | **−0.60** | 9.69 | −0.17 | 2/4 | no | NOT DETECTABLE, **sign flipped on coverage** |
| swarm − generic, **gross** | +3.18 | −0.88 | 9.70 | −0.25 | 2/4 | no | NOT DETECTABLE |
| Full − generic-in-Full | +1.10 | +1.21 | 5.60 | 0.60 | 2/4 | no | NOT DETECTABLE |
| LLM-only − random-text | +7.67 | +4.36 | 12.87 | 0.95 | 2/4 | yes | NOT DETECTABLE |
| Full − Full-with-random-text | +3.47 | +3.38 | 8.06 | 1.18 | 3/4 | yes | NOT DETECTABLE |
| Full − time-shift k=1 | +3.18 | +3.51 | 8.20 | 1.20 | 4/4 | yes | NOT DETECTABLE |
| Full − time-shift k=12 | +3.13 | +2.98 | 8.29 | 1.01 | 3/4 | yes | NOT DETECTABLE |
| P8 − P7 (confidence weighting) | +0.38 | **−1.04** | 2.66 | −1.10 | 3/4 | no | NOT DETECTABLE, sign flipped |
| Full − no-news | −0.38 | −0.66 | 6.51 | −0.28 | 2/4 | yes | NOT DETECTABLE |
| Full − no-geopolitical | −0.24 | +1.60 | 5.66 | 0.79 | 3/4 | yes | NOT DETECTABLE |
| Full − no-revisions | −0.27 | +0.24 | 7.03 | 0.10 | 2/4 | no | NOT DETECTABLE |
| Full − no-regime | −0.93 | +0.01 | 7.36 | 0.00 | 2/4 | no | NOT DETECTABLE |
| Full − no-quant | −1.79 | −3.01 | 11.74 | −0.72 | 2/4 | no | NOT DETECTABLE |

**H4 — no single-component removal produces a detectable degradation.**
Twenty-two paired contrasts, zero detectable, and **two change sign** between
the 75 % and 98 % panels. The largest single-component effect (`no_quant`,
−3.01) is a quarter of its own ruler.

**The time-shift rung deserves one sentence.** Shifting the score vector by one
month, three months or twelve months changes Full's excess by less than
0.6 pp/yr across the three. A score whose *timing* can be destroyed by twelve
months with no measurable consequence is not carrying month-specific
information about these names.

---

## 3. Arm 1 — the shuffled-LLM placebo, which is what this chunk is for

The construction: the exact multiset of swarm scores, permuted across
(ticker, date) under `default_rng(20260812)`, 200 permutations, re-run through
the identical portfolio code. **The distribution is preserved to the last value;
only the pairing of a score to a security-date is destroyed.** If Full ≈
shuffled, the model's *content* is doing nothing and only its *noise* is moving
weights.

### 3.1 Raw

| | v1 (75 % panel) | **v2 (98 % panel)** | v2, leakage-clean (n=100) |
|---|---:|---:|---:|
| observed Full | −3.438 | **−2.973** | −2.503 |
| shuffled mean | −5.276 | **−5.733** | −4.615 |
| shuffled sd | 1.846 | 2.290 | 2.318 |
| shuffled 95th pct | −2.378 | **−2.007** | −0.797 |
| observed − shuffled mean | +1.838 | **+2.760** | +2.112 |
| **permutation p (one-sided)** | 0.155 | **0.105** | 0.185 |

**In every column the observed value sits below the shuffled 95th percentile —
inside its own placebo's distribution.**

### 3.2 Matched (A3) — added tonight, because the pre-registered runner reported the placebo raw-only

Chunk 5 is the reason this could not be left out: its one detectable arm was
mostly beta (0.787 vs 0.656) and dissolved on matching. Leaving the *decisive*
arm of chunk 9 unmatched would have left the campaign's central comparison on
the one dimension it has repeatedly been wrong about. Same seed, same pool, same
code path, 200 permutations each.

| matching | observed | shuffled mean | obs − shuffled | **p** | obs gross / shuf gross | obs vol / shuf vol |
|---|---:|---:|---:|---:|---:|---:|
| raw | −2.973 | −5.733 | +2.760 | **0.105** | 1.000 / 1.000 | 18.92 / 20.38 |
| **beta-matched** | −3.937 | −6.741 | +2.804 | **0.125** | 1.011 / 0.982 | 20.30 / 21.41 |
| **vol-matched** | −4.244 | −6.216 | +1.972 | **0.145** | 0.819 / 0.784 | 16.50 / 16.92 |
| turnover-matched | −2.973 | −5.733 | +2.760 | 0.105 | 1.000 / 1.000 | 18.92 / 20.38 |

**Matching does not rescue it — it makes it slightly worse.** The volatility
match costs the largest single chunk of the apparent edge (+2.76 → +1.97),
which says roughly a third of the gap between Full and its own shuffle is Full
carrying 1.5 volatility points less than the average permutation.

**The turnover match is a no-op here and is reported as one.** The budget
resolves to 1.00 one-way/month because every arm in this sub-arena already turns
over ~98 %; a check that binds nothing is not a check that passed.

### 3.3 What the shuffled arm decomposes

| quantity | pp/yr |
|---|---:|
| Full − no-LLM (the whole apparent LLM contribution) | **+3.37** |
| shuffled-LLM − no-LLM (**what a distribution-matched noise feature contributes**) | **+1.37** |
| Full − shuffled (**what semantic content contributes**) | **+2.76**, p = 0.105 |

*(The two components do not sum to the first because the first is a paired
arithmetic mean of monthly differences and the others are differences of
compounded CAGRs; both are printed in the units their own instrument produced.)*

**Roughly 40 % of what the language model appears to add is reproduced by
permuted noise with the same distribution.** The rest does not clear a
permutation test at any matching. Under A4's frozen wording, that is
`PRESENTATION_AND_RESEARCH_ASSISTANCE`.

---

## 4. Arms 4 vs 5 — the specialist architecture, forced to justify itself

| statistic | five-role swarm | one generic agent |
|---|---:|---:|
| excess %/yr, LLM-only | −0.08 [MDE 10.60] | **+0.52** [MDE 11.23] |
| excess %/yr, gross | +6.35 | +7.32 |
| monthly Sharpe of excess | +0.0211 | **+0.0335** |
| rank IC | 0.0465 [MDE 0.0445] | **0.0471** [MDE 0.0440] |
| single-role IC, best | 0.0716 (`company_fundamental`) | **0.0686** |
| effective distinct ideas | 17,898 / 36,468 = **0.49** | 5,853 / 6,913 = **0.85** |
| calls spent | 12,906 | 2,475 |

**swarm − generic = −0.60 pp/yr [MDE 9.69], and the generic agent is the best
arm in the whole family by Sharpe.** The swarm is not detectably worse either —
the ruler is 9.69 wide — but the direction of the point estimate is against the
architecture, on the frozen sample, at 5.2× the call cost.

**The `effective distinct ideas` row is the mechanism.** Five personas produce
36,468 forecasts that reduce to 17,898 distinct ideas — a ratio of **0.49**,
against **0.85** for the single generic agent. *Half of what the swarm emits is
five voices saying one thing.* Chunk 3's 0.059 mean pairwise probability spread
across fourteen roles said this in a different unit; this is the portfolio
consequence.

**H3 is DIRECTION_REJECTED and NOT DETECTABLE.** Both, and they are different
statements: the prereg's directional prior was LOW and the data agreed with the
prior while lacking the power to prove it.

---

## 5. What the arms were fed — the distributions, printed so the ladder can be read

### 5.1 Score distributions

| source | n cells | mean | sd | 5th | 95th | share positive |
|---|---:|---:|---:|---:|---:|---:|
| swarm | 4,660 | 0.036 | 0.124 | −0.20 | 0.227 | 65.3 % |
| generic | 2,443 | 0.114 | 0.155 | −0.25 | 0.300 | **79.9 %** |
| random-text | 645 | 0.022 | 0.152 | −0.25 | 0.250 | 60.5 % |

The generic agent is **three times more bullish on average** than the swarm and
says "up" four times in five. Its higher Sharpe is therefore partly a long tilt
in a market that rose — which is exactly why the money contrast is reported
beside the IC and why neither is allowed to certify the other.

**The random-text arm is not a null score.** Shown structurally identical
numbers belonging to no security, the model still says "up" **60 %** of the
time. Its rank information is nil (IC −0.0059), but its *sign bias* survives
having nothing to read.

### 5.2 The random-text arm is 13.6 % covered, and that is a real limitation

The prereg capped random-text at ≤1,500 calls; 646 were made, covering 645 of
4,760 cells. The other **86 % are neutral-filled**. So rung 3 of the ladder
tests "what happens when a seventh of the LLM leg is fabricated and the rest is
neutral", not "what happens when the whole LLM leg is fabricated". Its
contrasts (`llm_only − randtext` = +4.36 [12.87]) are reported and are not
detectable, and this is the first reason to distrust them even if they had been.

### 5.3 The call census

| | swarm | generic | random-text |
|---|---:|---:|---:|
| ok | 12,773 | 2,459 | 646 |
| zero-yield | 128 | 16 | 5 |
| abstained | 5 | 0 | 0 |

**Zero-yield 0.93 % overall, against the governor's 40 % brake.** Forecast
rejections by the contract parser, 2,188 in total: recommendation language
1,149 · horizon not frozen 894 · missing required field 40 · unparseable JSON
40 · forecasts past cap 39 · coin-flip filler 18 · evidence without a
first-public timestamp 6 · wrong security 1 · no evidence 1.

**The largest rejection class is the model trying to give advice** (1,149) and
the second is it trying to choose its own horizon (894). Both are refused by the
contract, and both are properties of the instrument worth carrying forward.

---

## 6. A3 — raw and matched, on the four principal arms

Excess CAGR %/yr, v2. Every column also carries gross exposure, concentration,
volatility and turnover.

| arm | raw | β-matched | vol-matched | turnover-matched | 0× gross | vol %/yr (raw) | gross | eff N | turnover |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `full` | −2.97 | −3.94 | −4.24 | −2.97 | +3.24 | 18.92 | 1.000 | 10.0 | 0.979 |
| `no_llm` | −7.10 | −8.18 | −7.27 | −7.10 | −0.82 | 21.36 | 1.000 | 10.0 | 0.982 |
| `llm_only_swarm` | −0.08 | −1.68 | −1.81 | −0.08 | +6.35 | 20.95 | 1.000 | 10.0 | 0.984 |
| `generic_instead_of_swarm` | −4.49 | −5.21 | −4.69 | −4.49 | +1.75 | 19.75 | 1.000 | 10.0 | 0.984 |

**Full − no-LLM survives matching in sign and rough size** (+4.13 raw, +4.24
beta-matched, +3.03 vol-matched on CAGR levels) — and is below its MDE of 8.23
in all of them. Matching neither creates nor destroys this contrast; the ruler
refuses it either way.

### 6.1 Three of A3's five dimensions are equal by construction, and that is stated rather than claimed as a pass

A3 requires matching on beta, volatility, **gross exposure, concentration and
turnover**. In this instrument:

- **gross exposure** is 1.000 in every raw arm — the ablation simulator applies
  no leverage on the raw pass;
- **concentration** is effective-N 10.0 in every arm — every arm holds the top
  K = 10 of the same 40 names at equal weight;
- **turnover** is 0.979–0.992 in every arm — forced by the independent monthly
  redraw of the 40-name panel.

So only **beta and volatility** were ever free to differ, and those are the two
that are matched. **This is a property of the design, not a check that was
performed**, and it is written here so that "A3 satisfied" is not read as
"five independent confounds were controlled".

### 6.2 What was not matched

The nine secondary arms (`no_news`, `no_geopolitical`, `no_revisions`,
`no_regime`, `no_quant`, `llm_only_generic`, `randtext`, `p8_confidence_weighted`,
`full_randtext`) are reported **raw and 0×-gross only**. The pre-registered
runner matches four arms. Their gross exposure, concentration and turnover are
equal by construction as above; their beta and volatility are not matched, and
that is a gap. It is recorded here rather than papered over, and it is the
cheapest item owed from this chunk.

---

## 7. H5 — the information axis, reported separately from the money axis

Per-date Spearman IC of each arm's score against the forward one-month return,
against its own MDE in IC units.

| arm | IC v1 | **IC v2** | its MDE | t | blocks | halves | verdict |
|---|---:|---:|---:|---:|:--:|:--:|---|
| `llm_only_generic` | 0.0255 | **0.0471** | 0.0440 | 3.00 | 4/4 | yes | **DETECTABLE** |
| `no_quant` ≡ `llm_only_swarm` | 0.0282 | **0.0465** | 0.0445 | 2.93 | 4/4 | yes | **DETECTABLE** |
| `no_regime` | 0.0504 | **0.0518** | 0.0506 | 2.87 | 4/4 | yes | **DETECTABLE** |
| `p8_confidence_weighted` | 0.0417 | 0.0494 | 0.0554 | 2.50 | 4/4 | yes | NOT DETECTABLE |
| `no_geopolitical` | 0.0394 | 0.0474 | 0.0544 | 2.44 | 4/4 | yes | NOT DETECTABLE |
| **`full`** | 0.0429 | **0.0474** | 0.0554 | 2.40 | 4/4 | yes | NOT DETECTABLE |
| `generic_instead_of_swarm` | 0.0411 | 0.0473 | 0.0561 | 2.36 | 4/4 | yes | NOT DETECTABLE |
| `no_news` | 0.0385 | 0.0442 | 0.0566 | 2.19 | 4/4 | yes | NOT DETECTABLE |
| `no_revisions` | 0.0421 | 0.0401 | 0.0584 | 1.93 | 3/4 | yes | NOT DETECTABLE |
| `no_llm` | 0.0360 | 0.0360 | 0.0567 | 1.78 | 3/4 | yes | NOT DETECTABLE |
| `full_randtext` | 0.0364 | 0.0335 | 0.0561 | 1.67 | 3/4 | yes | NOT DETECTABLE |
| `randtext` | 0.0013 | **−0.0059** | 0.0493 | −0.33 | 2/4 | no | NOT DETECTABLE |

**Three cells clear their own MDE, and the shuffled permutation agrees:** Full's
IC of 0.0474 exceeds the 95th percentile of 40 shuffled permutations (0.0412),
where its *money* result did not exceed the 95th percentile of 200.

**And three readings are refused:**

1. **NIGHT-9's standing rule.** A rank-IC result may not corroborate a null
   money result, and the converse is equally refused. `llm_only_swarm` is
   simultaneously the clearest information result here (IC 0.0465 > MDE 0.0445)
   and a **−0.08 %/yr [MDE 10.60]** money result. Both stand; neither speaks for
   the other.
2. **Multiplicity.** Twelve distinct arms tested on the IC axis. Three clear at
   t = 2.87–3.00; a Bonferroni threshold over twelve is t ≈ 2.94. **Two of the
   three sit under it.** The MDE rule is a per-arm 80 %-power statement, not a
   family-wise test, and §20 says the family is what matters.
3. **§9.** All three lose detectability when the 19 famous-event months are
   dropped — and so does an arm with no LLM in it.

**The one clean thing this table says:** `randtext` has an IC of −0.0059 and
everything with a real security in front of it has an IC of 0.034–0.052. **The
model is reading the snapshot rather than emitting noise.** That is a genuine
finding about the instrument, and it is much weaker than "the model is
informative about returns".

---

## 8. Narrow domain — pre-declared cuts, reported as A4 requires whether or not the overall answer is null

The cuts were added to the runner **before any full-panel result existed**
(`357fef9`), because A4 makes "helps only in a narrow domain" a **success**, and
a cut invented after seeing an overall null is a search.

| cut | IC v1 | **IC v2** | MDE | t | blocks | halves | verdict |
|---|---:|---:|---:|---:|:--:|:--:|---|
| horizon **> 20 td** | 0.0314 | **0.0502** | 0.0452 | 3.11 | 4/4 | yes | **DETECTABLE** |
| horizon ≤ 20 td | 0.0315 | 0.0238 | 0.0468 | 1.42 | 3/4 | no | NOT DETECTABLE |
| role `company_fundamental` | 0.0637 | **0.0716** | 0.0625 | 3.21 | 4/4 | yes | **DETECTABLE** |
| role `generic_analyst` | 0.0861 | **0.0686** | 0.0639 | 3.01 | 4/4 | yes | **DETECTABLE** |
| role `geopolitical` | 0.0327 | 0.0461 | 0.0846 | 1.52 | 3/4 | yes | NOT DETECTABLE |
| role `analyst_revisions` | 0.0358 | 0.0425 | 0.0610 | 1.95 | 4/4 | yes | NOT DETECTABLE |
| role `execution_momentum` | −0.0327 | 0.0187 | 0.0571 | 0.92 | 3/4 | yes | NOT DETECTABLE |
| role `skeptic` | 0.0181 | 0.0115 | 0.0655 | 0.49 | 2/4 | no | NOT DETECTABLE |
| size Q1 (small) | 0.0122 | 0.0491 | 0.1071 | 1.28 | 2/4 | yes | NOT DETECTABLE |
| size Q3 | **0.0979** | **0.0160** | 0.0867 | 0.52 | 3/4 | yes | NOT DETECTABLE |
| size Q5 (large) | 0.0284 | 0.0438 | 0.0999 | 1.23 | 4/4 | yes | NOT DETECTABLE |
| small half | 0.0251 | 0.0385 | 0.0600 | 1.80 | 2/4 | no | NOT DETECTABLE |
| large half | 0.0496 | 0.0395 | 0.0660 | 1.68 | 4/4 | yes | NOT DETECTABLE |

**The size-quintile cuts are noise and can be shown to be.** Q3 was the biggest
number in the v1 table at 0.0979 (t = 2.33) and is **0.0160** in v2. A cut whose
point estimate moves by a factor of six when the panel fills is not measuring a
domain.

**Sixteen cuts, three detectable, all three dissolved by §9.** Under the frozen
decision table this does **not** reach `NARROW_DOMAIN`: that outcome requires a
detectable subset, and none of the three survives its own leakage control.

**One methodological caveat on the horizon cut, stated because it is
load-bearing.** The "long" band aggregates forecasts with horizons above 20
trading days and grades them against the forward **one-month** return. A 60-day
forecast scored on a 21-day outcome is a horizon mismatch; the cut measures "the
score built from long-horizon questions", not "the model's long-horizon
accuracy". ABLATION-FWD grades each horizon against its own.

---

## 9. Leakage — the canary changed what HIST may claim, and then the control changed it back

`LLM-LEAKAGE-PROBE-1` (`32e23a6`) established that recall is **concentrated, not
uniform**: 7 of 10 famous moves recalled with **7/7 correct direction**
(Lehman · COVID top · COVID bottom · GME · NVDA · META · SVB), against **0 of
419** on ordinary securities on ordinary dates. So historical grading is usable
with famous-event windows **flagged or excluded rather than assumed harmless**.

### 9.1 What was done: FLAGGED in the primary, excluded as a sensitivity

Seven canary events fall in or near 2015-2024. A decision at *T* forecasts
*[T, T+1m]*, so a ±45-calendar-day half-width around each event covers both the
forward window and the immediate aftermath. **19 of 119 decision months are
flagged:**

`2020-01-31 · 2020-02-28 · 2020-03-31 · 2020-04-30 · 2020-07-31 · 2020-08-31 ·
2020-09-30 · 2020-12-31 · 2021-01-29 · 2021-02-26 · 2021-12-31 · 2022-01-31 ·
2022-02-28 · 2023-01-31 · 2023-02-28 · 2023-03-31 · 2023-04-28 · 2023-05-31 ·
2023-06-30`

**The primary runs on all 119 months with these flagged.** Two sensitivities run
the identical code: `--exclude-famous` (n = 100) and `--only-famous` (n = 19).

### 9.2 Exclusion kills every detectable cell — and so would have been the wrong thing to do silently

| statistic | all 119 | clean 100 | verdict change |
|---|---:|---:|---|
| Full − no-LLM | +3.37 [8.23] | +1.55 [8.56] | still NOT DETECTABLE |
| shuffled-LLM p | 0.105 | **0.185** | still not significant |
| IC `full` | 0.0474 [0.0554] | 0.0407 [0.0604] | still NOT DETECTABLE |
| IC `llm_only_swarm` | 0.0465 [0.0445] **DET** | 0.0407 [0.0484] | **DETECTABLE → not** |
| IC `llm_only_generic` | 0.0471 [0.0440] **DET** | 0.0396 [0.0463] | **DETECTABLE → not** |
| IC horizon > 20 td | 0.0502 [0.0452] **DET** | 0.0441 [0.0492] | **DETECTABLE → not** |
| IC `company_fundamental` | 0.0716 [0.0625] **DET** | 0.0649 [0.0691] | **DETECTABLE → not** |
| IC `generic_analyst` | 0.0686 [0.0639] **DET** | 0.0578 [0.0682] | **DETECTABLE → not** |

Every detectable cell in the chunk lives on the flagged months. On that evidence
alone the reading would be "the model's apparent information is its memory of
famous events".

### 9.3 The control refuses that reading

The complement — the same code on **only** the 19 flagged months:

| arm | clean 100 | **famous 19** | lift |
|---|---:|---:|---:|
| `full` | 0.0407 | 0.0828 | +0.042 |
| `llm_only_swarm` | 0.0407 | 0.0767 | +0.036 |
| `llm_only_generic` | 0.0396 | 0.0865 | +0.047 |
| **`no_llm` — contains no language model at all** | 0.0326 | **0.0537** | **+0.021** |
| **`randtext` — shown numbers belonging to no security** | −0.0200 | **+0.0654** | **+0.085** |
| role `generic_analyst` | 0.0578 | 0.1255 | +0.068 |
| role `company_fundamental` | 0.0649 | 0.1069 | +0.042 |

**An arm with no language model in it gains 0.021 of IC on the flagged months,
and an arm reading fabricated numbers gains 0.085.** Neither can be recalling
Lehman. **Famous-event months are cross-sectionally easier months for every
scoring rule** — high dispersion, strong momentum, wide winner/loser gaps — and
that, not memory, is the dominant term in the lift.

**The LLM arms gain more than the no-LLM control** (`full` +0.042 vs `no_llm`
+0.021, a difference of differences of +0.021), which is the shape leakage would
take. **§18 requires that difference to be tested with its own SE, and it was
not computed.** The reason is that at n = 19 the IC MDE for a single cell is
**0.114 to 0.177**; a difference of 0.021 is an order of magnitude below what
that subset can resolve, and computing an SE for it would dress an
unmeasurable quantity in a number. **Not run, and why, rather than run and
over-read.**

### 9.4 The licensed statement

> **The flagged months are flagged, not excluded, and the reader is given the
> exclusion, the complement and a no-LLM control.** The three detectable IC
> cells depend on months that are (a) demonstrably recalled by the model and
> (b) demonstrably easier for scoring rules that cannot recall anything. **This
> instrument cannot separate those two, and neither reading is adopted.** What
> it can say is that the chunk's headline verdicts — H1, H2, H3 — are NOT
> DETECTABLE on all 119 months, on the clean 100, and on the flagged 19.

---

## 10. §20 and A8 — the family, not the arm

### 10.1 Thirteen arms are 1.77 arms

Correlation of the monthly excess series across all thirteen arms: **mean
absolute pairwise |ρ| = 0.528**, giving
`n / (1 + (n−1)·|ρ|)` = **1.77 effective distinct arms**. The A4 ladder alone
(`full`, `llm_only_swarm`, `llm_only_generic`, `randtext`) gives **1.84 from 4**.

The collapse is in line with the campaign: chunk 6 got 2.02–2.40 from 47
configurations, chunk 5 got 5.60 from 36. **Thirteen ablations of four legs on
one panel are, statistically, about two chances.**

### 10.2 A duplicate arm, found tonight

`no_quant` and `llm_only_swarm` have **identical drop-sets, identical roles and
identical sources** in the `ARMS` table. They are one arm with two names, and
every number they produce is byte-identical (−0.08 %/yr, IC 0.0465, Sharpe
+0.0211) in both v1 and v2. **The ladder's raw count of thirteen is really
twelve**, and the report counts twelve wherever a count is used. Recorded, not
tidied away: the duplicate is real and semantically defensible (removing all
quant legs *is* LLM-only), but printing it twice in a table of thirteen
overstates the search by one.

### 10.3 Deflated Sharpe for the family

Best arm in the family by monthly Sharpe of excess: **`llm_only_generic`, SR =
+0.0335/month** (three of thirteen arms have a positive excess Sharpe; the other
ten are negative). Cross-arm variance of SR = 0.00246.

| search denominator | n trials | SR₀ | **DSR** |
|---|---:|---:|---:|
| raw arm count | 13 | 0.0845 | **0.290** |
| §20 effective arm count | 2 | 0.0258 | **0.534** |
| campaign denominator (chunk 7's 323 + these 13) | 336 | 0.1454 | **0.112** |

**The threshold is 0.95. The best arm in the family clears none of the three
denominators, and the DSR of the best bounds the family from above.** All three
are printed together because choosing one after seeing which flatters is exactly
what A8 exists to prevent.

**PBO/CSCV was NOT run.** CSCV needs the strategy family evaluated on
combinatorially split sub-samples, and at n = 119 months a 16-fold CSCV yields
in-sample halves of ~60 months per configuration — below the point where a
monthly Sharpe estimate means anything, on a family whose effective size is 1.77.
**A PBO computed there would be a number, not a diagnostic.** It is owed for
chunk 8, whose genome family is large enough to need it.

---

## 11. ABLATION-FWD — the only path that can ever certify, and it is correctly empty

```
evidence_class                  ABLATION_FWD
records_total                   20,073
records_resolved                0
earliest_possible_resolution    2026-08-16
status                          STATED_EMPTY
overall                         n=0, brier=null, mde=null, INSUFFICIENT_N
shuffled_placebo_forward        n=0 — "the decisive arm needs resolved
                                records; it has none"
arms_not_run_forward            generic_agent_vs_specialist_swarm — the forward
                                ledger holds swarm records only; the contrast
                                needs forward records from a single generic
                                agent, which have not been minted
```

**Nothing here is fabricated, estimated, extrapolated or previewed.** With zero
resolved records the correct output is an empty table and a date, and that is
what it is.

**The two classes are never merged.** Everything in §1–§10 is
`ARCHITECTURE_RESULT_ONLY`: it compares architectures against each other and
against placebos under *identical* contamination, which is what an ablation is
for, and it certifies nothing. Only ABLATION-FWD can show DeepSeek is adding new
information rather than reconstructing what it already knows, and it begins on
**2026-08-16**.

**One thing this chunk owes forward:** the generic-agent contrast has no forward
arm. H3 will not be answerable forward until generic-agent records are minted
alongside the swarm's.

---

## 12. Arms that could not run — declared, not quietly dropped

| arm | status | reason |
|---|---|---|
| `no options` | **DECLARED_NON_RUN** | there is no point-in-time options-implied panel joined to this spine. OptionMetrics files exist in `data/wrds_raw` but are not linked to the arena cache, and the production stack's `options_iv` weight (0.12) is one of the five branches chunk 7 §1.6 records unavailable. Inventing the panel is not permitted. |
| `no WHY-MOVED experience` | **DECLARED_NON_RUN** | the experience memory is a 2026 forward artefact. There is no 2015-2024 memory to remove, so the arm cannot be run and is not simulated. |
| `no specialist reliability` | **NULL_BY_CONSTRUCTION** | A5 fixes specialist reliability at neutral/equal until forward records resolve, so removing it removes nothing. The arm is identical to `full` **by construction** and its difference is exactly **0.0** — printed rather than simulated, because simulating it would imply it could have come out otherwise. |

**A check that did not run is not a check that passed.**

---

## 13. Search denominator (A8)

| stage | configurations | note |
|---|---:|---|
| arms, v1 panel (75 % coverage) | 13 | raw + 0× gross each |
| arms, v2 panel (98 % coverage) | 13 | raw + 0× gross each |
| A3 matchings | 24 | 4 arms × 3 matchings × 2 panels |
| shuffled placebo | 400 | 200 permutations × 2 panels |
| shuffled placebo, matched (supplement) | 600 | 200 × 3 matchings |
| time-shifted | 6 | 3 shifts × 2 panels |
| rank-IC | 26 | 13 arms × 2 panels |
| narrow-domain cuts | 32 | 16 cuts × 2 panels |
| leakage sensitivity, exclude | 13 | full arm set, n = 100 |
| leakage sensitivity, only | 13 | full arm set, n = 19 |
| §20 / A8 family check | 1 | |
| ABLATION-FWD | 1 | STATED_EMPTY |
| **total** | **1,142** | 0 skipped, 0 voided, 0 dropped |
| **of which effective distinct arms (§20)** | **1.77** | |

Nothing was dropped for being unflattering. The v1 panel is printed beside v2
throughout even though v1 contained the campaign's only positive H3 estimate;
the three detectable IC cells are printed with the control that dissolves them;
the duplicate arm is named; and the arm that came out best — a single generic
DeepSeek prompt — is the one that most embarrasses the architecture this
programme has been building.

---

## 14. Defects found tonight, recorded rather than tidied away

1. **The ablation read a file that was being appended to while it read.**
   `scripts.arena_llm_hist` was still running at 48 workers when the 21:13
   ablation started; it saw 7,215 calls where the same command minutes later saw
   15,691. The run was not a function of its inputs. **Fixed:** `--calls` now
   takes a frozen snapshot and the artefact records the file name and call count.
   **Both runs are reported**, and the comparison found the sign flip in §2.1.
2. **`no_quant` and `llm_only_swarm` are the same arm.** Identical drop-set,
   roles and source; identical output to the last digit. Counted twice in a
   thirteen-arm ladder. **Recorded**, not renamed — see §10.2.
3. **The decisive arm was reported raw-only.** The pre-registered runner applies
   A3 matchings to four arms and the shuffled placebo was not among them, so the
   comparison the whole chunk turns on had no risk matching. **Fixed tonight**
   by `ablation_placebo_matched.py`; the answer does not change (§3.2).
4. **The turnover match binds nothing in this sub-arena**, because the budget
   resolves to 1.00 against arms that already turn over ~98 %. It runs, it
   returns numbers identical to raw, and reading it as a passed check would be
   wrong.
5. **`rank_ic` reported its MDE through the return ruler**, which annualises and
   multiplies by 100 — correct for a return series, wrong for a correlation.
   Fixed in `357fef9` before any full-panel result existed; the MDEs in §7 and
   §8 are in IC units.
6. **The famous-event control was not in the runner** when the primary ran — the
   leakage canary's positive control landed at 21:15, two minutes after the
   ablation finished. **Added tonight**, and it changed the reading of §8 twice
   (§9.2 then §9.3).

---

## 15. What this cannot tell us — read before quoting any number above

1. **`ARCHITECTURE_RESULT_ONLY` (A6).** Historical LLM reasoning cannot certify
   alpha. These numbers compare architectures under shared contamination.
2. **Five roles, not fourteen.** A null on five roles is not a null on the full
   swarm. The effective-distinct-ideas ratio (0.49) is printed so the reader can
   see how much independence was ever there.
3. **Forty names per date.** The money comparison is **underpowered by
   construction** and its MDEs (8–16 pp/yr) say so in numbers. The IC test is the
   powered one and the two are never merged.
4. **One vendor, one model family.** This is a test of DeepSeek-as-configured,
   not of language models.
5. **A component whose ablation is not detectable is not shown to be useless.**
   It is shown to be below this instrument's resolution, and the MDE states how
   large it would have had to be (§19).
6. **The sub-arena's ~98 % forced turnover** makes the levels uninhabitable. Only
   paired differences and the 0×-gross column are readable.
7. **Under A7, 2002-2024 is not a pristine holdout**, and the leakage canary now
   gives a concrete mechanism for why. Certification comes from the forward
   paper tournament.
8. **Nothing is promoted.** No lane, no position size, no product default, no
   buy/sell surface, no registry row changes because of this chunk.

---

## 16. What the campaign now owes

| item | owed by |
|---|---|
| A3 matching on the nine secondary arms | next ablation pass |
| forward generic-agent records, so H3 has a forward arm | before 2026-08-16 accrual is read |
| PBO/CSCV on a family large enough to need it | chunk 8 |
| ABLATION-FWD first resolutions | **2026-08-16** |
| re-run once `arena_llm_hist` completes generic and random-text coverage | when the harness stops |

**Budget:** zero LLM calls were issued by this chunk. Every arm — including all
600 matched permutations — is a re-permutation of stored records, exactly as
A12-R predicted when it said the remaining campaign costs approximately nothing.
`research_budget.require()` was never reached because no batch was ever issued.
