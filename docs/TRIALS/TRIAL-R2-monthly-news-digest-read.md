# TRIAL-R2 — a local 7B reading one month of anonymised news, pre-registered before the widening

**Registered 2026-09-10, BEFORE the widened (PANEL-B) read is taken.** At the
moment of writing, `llama-server` is not listening on `127.0.0.1:8080` and no
widened cell has been asked of any model — the commitment therefore precedes the
data, which is the only property that makes it worth anything.
**Family:** the monthly news-digest read (R2). One prompt, one digest
construction, one model, one horizon. **Licence:** `PRODUCT_EXPERIMENT`;
`RESEARCH_CLAIM` requires everything in §"What this rule may NOT do".
**Accrues zero arms. Places nothing. Seals nothing.**

## 0. Corpse check

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`
(result recorded in §7).

- Resurrects: nothing refuted. The nearest live objects are TRIAL-LLM-AMNESIA-1
  (2026-08-08 — *can you tell an LLM to forget?*), whose canary is imported here
  as a gate rather than re-derived, and the R7 news-representation lane, which
  closed a **from-scratch encoder** (it loses to TF-IDF in every era) and not the
  question of whether a *pretrained* reader can read.
- New instrument, relative to the 2026-09-08 read: the E1 panel
  (`text_return_panel/news_returns_2025_26.parquet`, 339,657 text-and-return
  cells over 3,031 symbols, 2025-01-02..2026-09-08). The prior best joined panel
  was 9,457 cells over 135 names. That is a 22× widening of the cross-section
  and a calendar span the 2015-2024 read never saw.

## 1. Hypothesis

> A local 7B model given **only** an anonymised digest of one calendar month's
> news about one company calls that company's **next-month market-adjusted
> direction** better than the identical pipeline reading a digest from a random
> **other** month — on a panel it was never selected on.

**Honest prior, stated as weakly as the evidence deserves.** PANEL-A
(`night_factory_2026-09-08/R2_monthly_llm_2015_2024_run01.json`, 2015-2024, 135
names, 112 monthly blocks) measured the arm at +21.845%/yr against the shuffled
control's +5.656%/yr, a difference of **+16.189%/yr, t 3.922**, sign accuracy
0.542 vs 0.4911, with the AMNESIA canary passing (**−0.0041**: the masked read is
marginally *better* than the real-name read, so the model is reading rather than
recalling). Its own amendment (`R2_verdict_amendment.json`) records why that is
CONDITIONAL and not a claim: **gross of costs at the level**, a 135-name panel
that is mega-cap skewed (NVDA/SPY/AMD dominate the document counts), and **a
prompt that was not registered when it ran**. So the prior admits three
alternatives that PANEL-B can separate: the effect may be the 135 names, may be
the 2015-2024 era, or may be a prompt search that is not on the record. This
registration cannot retroactively rescue PANEL-A. It exists so the next read is
one a prompt search cannot quietly have preceded.

## 2. The two panels, and which one decides

| | PANEL-A (already read — REPORTED, never deciding) | PANEL-B (the decision — UNREAD at registration) |
|---|---|---|
| source | `r7_news_representation/panel.parquet` + `docs_masked.parquet` | `text_return_panel/news_returns_2025_26.parquet` (E1) + `prices_2025_26/bars.parquet` |
| span | 2015-02 .. 2024-11 | 2025-01 .. 2026-07 (entry months) |
| names | 135 | up to 3,031 symbols |
| blocks | 112 monthly | **19 monthly** |
| forward label | `excess_vw_1m` (CRSP value-weighted market excess) | open-to-open month return **minus SPY's**, entry at the first open of M+1, exit at the first open of M+2 |
| market proxy | CRSP VW index | **SPY** — a declared deviation: CRSP ends 2024-12 and there is no VW index on this span |
| status | read 2026-09-09, CONDITIONAL | run ONCE after this registration's commit |

The market-proxy and label changes are **named here rather than discovered
later**. They are why PANEL-B is a *widening of the question*, not a replication:
it asks whether the mechanism survives a different cross-section, a different
era, a different market proxy and a different return convention. A mechanism that
does not is not thereby refuted — but it is not the general thing the 135-name
read read like either.

**PIT by construction.** Every document of month M is published before the first
session of M+1 opens, and the position is taken at that open. E1 already enforces
"first open strictly after publication" at the document level. No cell can act on
text it had not seen.

## 3. Primary metric — the ONE deciding number

`read_minus_shuffled_control`: the mean over monthly **DATE BLOCKS** (canon §58 —
names inside one month share the market and are not independent draws) of
(arm month return − control month return), where **each leg is NET**:

```
w_t          direction × confidence inside month t, normalised so Σ|w| = 1
gross_t      w_t · forward_excess_t
turnover_t   Σ_i |w_{t,i} − w_{t−1,i}|,  w_{−1} = 0
cost_t       turnover_t × 25 bps / 1e4          (the repo constant, night_factory_jobs.COST_BPS)
net_t        gross_t − cost_t
```

annualised ×12, with a **Newey-West lag-2** t on the 19 differenced blocks.

Everything else is **reported, never deciding**: gross beside net; turnover per
rebalance for the arm and the control separately; each leg's own level; sign
accuracy; the share of FLAT calls; refusals by class; the DeepSeek-equivalent
price of the tokens; PANEL-A's numbers.

A flat charge per date is not a cost model. On 2026-09-09 the C2 job charged 100
bps every day and printed −237%/yr net for a monthly book; costs go on **realised
turnover, with the turnover printed** beside the net line, always.

**PANEL-A has no net line, and will not get one without a re-run.** Its 09-08 job
held ~15,000 per-cell answers in memory, graded them once and wrote a summary; the
answers were never persisted, so its monthly weights — and therefore its realised
turnover — cannot be reconstructed. What can be said without them is arithmetic
and is recorded in `night_factory_2026-09-08/R2_cost_amendment.json`: a gross-1
book cannot turn over more than 2.0 a rebalance, so at 25 bps a side the arm's
+21.845%/yr is **at worst +15.845 net**, the control's +5.656 **at worst −0.344**,
and the difference lies in **[+10.189, +22.189] %/yr**. That bound on the
*difference* is deliberately loose — it assumes the two turnovers are maximally
mismatched when in fact both books rebalance the same cells on the same dates.
From 2026-09-10 every answer is appended to an answers file as it arrives, so any
future run re-grades at any cost rate with `--regrade`, without the model.

## 4. Power, declared before the read (canon §64)

Every number below was computed on 2026-09-10 by
`python -m scripts.night_r2_monthly_llm --panel widened` **before any model was
asked anything** — `llama-server` was not listening, the run stamped itself
`PENDING_MODEL`, and its receipt
(`night_factory_2026-09-10/R2_widened_panelB_run01.json`) is the evidence that
the design was fixed before the read. What was read to get them is the *marginal*
dispersion of the forward label, which is a design quantity; no digest was built
into a prediction and no arm was graded.

- slice_purpose: CONFIRM
- slice_securities: the 3,031 symbols of the E1 2025-26 text-and-return panel that carry a monthly forward label and ≥ 3 documents in the month
- slice_period: 2025-02-01 .. 2026-09-01
- information_cutoff: 2026-09-08 (the last bar in `prices_2025_26/bars.parquet`); no document published after 2026-07-31 enters an entry month with a completed label
- selection_period: 2015-02-01 .. 2024-11-30
- parent_trial: R2_monthly_llm PANEL-A (night_factory_2026-09-08)
- hypothesis_source: R2_monthly_llm PANEL-A, the 2015-2024 read of 2026-09-08
- hypothesis_source_period: 2015-02-01 .. 2024-11-30
- dependence_unit: one monthly date block of the long-short book; ~975 cells a month collapse into ONE observation because the names inside a month share the market
- event_frequency_per_year: 12
- corpus_years: 1.6
- outcome_horizon_days: 21
- outcome_dispersion: 1.82 pp
- declared_effect_size: 1.20 pp

`slice_period` is the **position** window: the first read month is 2025-01, its
position is entered at the open of 2025-02-03 and closed at the open of
2025-03-03, and the last read month is 2026-07, closing at the open of
2026-09-01. The digests themselves start on 2025-01-02, which is still 33 days
after the parent's last labelled month ends and inside no window the parent was
fitted on. `selection_period` is the PARENT's window, inherited: PANEL-A was
searched over 2015-2024, and a descendant carries its parent's selection window
whether or not it likes the arithmetic.

**Reading those in plain units.** The panel resolves 19 monthly blocks over
18,501 cells, median 912 names a month, median cross-sectional sd of the forward
excess 17.39%. A confidence-weighted long-short over a leg of ~182 names has an
implied monthly sd of **1.82 pp**, so 19 blocks resolve **1.17 pp a month at 80%
power and α 0.05 — 14.0%/yr**, and the declared smallest effect worth acting on
is set one notch above it at **1.20 pp/month = +14.4%/yr net**.

That is the *conservative* reading, and deliberately so. The same estimator on
PANEL-A overstated the standard error by **1.61×** (it assumes names inside a
month are independent draws, which the 09-09 amendment measured and corrected);
if it overstates PANEL-B's by the same factor the design really resolves about
**8.7%/yr**. The threshold stays at the conservative number — a power check is a
DESIGN quantity, and a threshold that moves after the data is metric
substitution — but the realised standard error is printed in the receipt beside
the verdict, and a CONDITIONAL between 8.7 and 14.4 will be read for what it is.

**Why this panel can confirm and PANEL-A's own arithmetic could not.** PANEL-A
measured +16.189%/yr. PANEL-B resolves +14.4%/yr on a *fifth* of the blocks,
because 912 names a month buy far more than 60 do: the leg's idiosyncratic noise
falls with the square root of its width. Widening is not decoration here; it is
the only thing that makes 19 blocks a test at all.

## 5. Decision rule

- **Adopt** (→ a 12-month **zero-capital** forward leg; never an arm, never capital):
  net difference **≥ +14.4%/yr** (the declared effect size, §4) AND NW t
  **≥ 2.0** AND the AMNESIA gap **≤ +0.02** AND the sign positive in **both**
  calendar years present (2025 and the 2026 part-year). Earliest capital
  question **2027-09-10**.
- **Reject:** net difference **≤ 0** OR NW t **< 1.0** OR the AMNESIA gap
  **> +0.05** (the read is recall, not reading) OR the shuffled control's own net
  level exceeds the arm's (the machinery manufactures the spread).
- **Anything in between is CONDITIONAL**: reported, published, and sent to the
  forward leg unadopted. It does not widen what PANEL-A claims.
- **Minimum window / earliest decision:** the PANEL-B read is ONE computation,
  run ONCE by the named job `R2_monthly_llm --panel widened`, after this file's
  commit. If it adopts, the forward leg runs a minimum of 12 further monthly
  blocks, judged quarterly on the same primary metric against the same control.
- **Crash-event override:** if SPY draws down ≥ 20% from its in-window peak
  during the forward leg, no decision until ≥ 6 months past the trough.
- **Contamination clause:** any defect in the panel — a symbol-basis error, a
  timestamp error, or a **mask leak** (the company nameable from the masked
  digest) — voids the read; the panel is rebuilt, the read is re-run once, and
  the registration date moves to that commit.

## 6. Frozen parameters

Nothing below may be tuned mid-trial. The hashes are computed from
`backend/services/portfolio_intelligence/r2_trial.py`, which is the single source
of the prompt; the running script imports it and **refuses** to run if the hashes
have moved (`FrozenPromptViolation`), and
`backend/tests/test_r2_prereg_and_costs.py` requires this document, that module
and the receipt to carry the same three hashes.

| what | value |
|---|---|
| system prompt sha256 | `51ebe4fe45c6ab598383f3959c4f2029921d70147ae70aeab7fd431367a2371b` |
| user prompt sha256 | `0189e97eebdf43b6692d91dea64c6a821417b1f14f42b67601ac8e2b404b2ce7` |
| digest spec sha256 | `0e16923e20725ccf102a5107d912dbd884cc67a987521b3dc2fb4895bd854e65` |
| model file | `Qwen2.5-7B-Instruct-Q4_K_M.gguf`, 4,683,074,240 bytes |
| model sha256 | `65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423` |
| server | llama-server 0.3.0-dev (build 10645, commit `c5fc7e348`), Clang 20.1.8, Windows x86_64 |
| decoding | temperature 0.0, max_tokens 48 |
| digest | ≥ 3 docs per cell, ≤ 8 docs in the digest, ≤ 320 chars a doc, `- ` prefixed, newline joined |
| ordering | PANEL-B: ascending `published_utc`, then `uid`, then head(8) |
| anonymisation | `r7_news_representation.mask_company` over `tokenise`: ticker + distinctive CRSP issuer-name tokens → `[co]` |
| control | same cells, digest drawn from a different month, rng seed `20260909` |
| costs | 25 bps a side on realised turnover Σ\|Δw\| |
| t | Newey-West, lag 2, on monthly blocks |

The prompt text itself, verbatim:

```
SYSTEM: You are a careful financial analyst. You read only the text you are given and you never guess the company. Answer in English, in the exact format requested, and nothing else.

Below are news items about one company from a single month.

{digest}

Based ONLY on these items, state what you expect this company's stock to do over the NEXT month
relative to the overall market.

Answer on two lines, exactly:
DIRECTION: UP or DOWN or FLAT
CONFIDENCE: a number from 0.0 to 1.0
```

**A model swap is a NEW ARM, not an upgrade.** Qwen2.5-7B-Instruct-Q4_K_M at the
sha256 above is the reader this trial registers. A 14B, a different quantisation
of the same weights, or a different server build is a different reader and gets
its own registration and its own place in the multiplicity count.

## 7. Corpse-check result

`python scripts/lint_prereg.py <this file>` from `C:/Users/mrthn/Aegis module`,
2026-09-10, against 358 prior experiments:

```
TRIAL-R2-monthly-news-digest-read.md: PASS  (vs 358 prior experiments)
  no close match in 148 graveyard rows, the trial registry or the prereg folder.
  R13: n_required 18  n_available 19  smallest resolvable effect 1.2pp
  R13e: CALENDAR_DISJOINT  selection 2015-02-01..2024-11-30  slice 2025-02-01..2026-09-01  gap 63d (need 44d)
  R13f: HYPOTHESIS_SOURCE_DISJOINT  source R2_monthly_llm PANEL-A, the 2015-2024 read of 2026-09-08
   [near     ] 0.184  prereg    REGISTERED             PREREG_TEACHER_LIBRARY_1
```

PASS means UNMATCHED, not novel — it compares wording against what this
programme has recorded and knows nothing about the literature. Two earlier
refusals on the way here are part of the record and are worth naming, because
both were the linter catching a real defect rather than a formality:

1. `MISSING_POWER_FIELDS` — the first draft declared an adopt threshold of
   **+6%/yr** that 19 blocks cannot resolve, the same mistake TRIAL-H5's first
   draft made with +8%/yr on 252 blocks. The threshold moved to the effect the
   design can actually see (+14.4%/yr), which is *below* PANEL-A's +16.189 and
   therefore still a real test.
2. `SELECTION_WINDOW_CONTRADICTS_PARENT` — the draft claimed
   `selection_period: none` while naming PANEL-A as its parent. A descendant
   inherits its parent's selection window; declaring it made the disjointness
   check meaningful (63 days of gap against the 44 the horizon requires) instead
   of vacuous.

## What this rule may NOT do

- **No prompt search.** One prompt, hashed above. A second prompt is a second
  arm, registered separately, and the family then carries Holm across arms
  (canon §63: SCREEN = BH-FDR, EXPORT = Holm).
- **No metric substitution.** The primary is the **net**, control-differenced,
  block-mean number on PANEL-B. Not the gross. Not the arm's level. Not sign
  accuracy. Not PANEL-A.
- **No re-reading PANEL-B** beyond the single registered run. A re-run is only
  permitted under the contamination clause, and moves the registration date.
- **No restating PANEL-A.** Whatever PANEL-B says, the 135-name read keeps
  exactly the claim its own amendment gave it: CONDITIONAL, gross at the level,
  135 names, unregistered prompt. A widened result is filed as its own receipt.
- **No buy/sell framing, no seal, no arm, no capital** until the forward leg
  passes, and promotion stays ATTENDED regardless of what any interim number
  says. No LLM has authority over real capital, in this trial or any other.
- **No skill claim before 24 months** of forward evidence, whatever the interim
  numbers are.

## Registry

`rule_experiments` row `r2-monthly-news-digest-read`, decision rule embedded in
`notes`, registered idempotently by
`backend/services/portfolio_intelligence/r2_trial.py::ensure_r2_trial`. Until the
row exists, this document and that module are the commitment, and their git
commit timestamp is the evidence.

---

# ADDENDUM (UNSIGNED) — `R2-Qwen3`, a NEW ARM beside R2

**Written 2026-09-13, chunk 9 item L4. UNSIGNED: no Qwen3 digest has been read,
the model server was never started by this work, and the arm's numbers do not
exist.** This section registers the arm and freezes what the run will be, which
is the only thing section 6's rule permits before the first read.

Section 6 of this document is the rule being obeyed, not bent: *"A model swap is
a NEW ARM, not an upgrade... a different quantisation of the same weights, or a
different server build is a different reader and gets its own registration and
its own place in the multiplicity count."* `R2` keeps every claim it has.
`R2-Qwen3` starts with none.

## The reader

| what | value |
|---|---|
| hub repo | `Qwen/Qwen3-30B-A3B-Instruct-2507` (30.5B params, ~3.3B active, MoE) |
| licence | `apache-2.0` |
| build | the **plain Instruct** build. Not the base model, not an abliterated community fine-tune |
| GGUF repo | `bartowski/Qwen_Qwen3-30B-A3B-Instruct-2507-GGUF` |
| model file | `Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf`, 18,556,686,752 bytes (18.56 GB decimal = 17.28 GiB) |
| model sha256 | `6c997b8af17debdfb01d890214400ccbab00db6acc0ba8da5de1cc906c4774d0` |
| quant | Q4_K_M — the same level the incumbent runs, so the comparison is apples to apples |

The sha256 above IS this arm's frozen identity, on the same rule the incumbent's
`65b8fcd9...` is. A re-download that produces different bytes is a different arm.

## What is held identical to R2

PANEL-B (18,501 cells over **19 monthly blocks** — PANEL-B's count, confirmed
from `night_factory_2026-09-10/R2_widened_panelB_run01.json`; **not 112**, which
is PANEL-A's), the same anonymisation, the same shuffled-digest control at rng
seed `20260909`, the same `read_minus_shuffled_control` primary, the same
Newey-West lag-2 t on monthly blocks, the same 25 bps a side on realised
turnover, and the same three frozen prompt hashes (`51ebe4fe...`, `0189e97e...`,
`0e16923e...`) imported from `r2_trial`, never retyped.

## Decision rule

Adopt `R2-Qwen3` over `R2` **only if both**:

1. `R2-Qwen3`'s OWN `read_minus_shuffled_control` beats `R2`'s own, on the SAME
   blocks, at the same bar `R2` uses; **and**
2. its **Lookahead Propensity** (lane X, item L3) is **not worse** than `R2`'s.

A pass on (1) alone is reported as `CONDITIONAL_ON_LAP`, never `ADOPTED`. A
bigger, differently-trained model reading the same anonymised digest may simply
have memorised more pre-cutoff fact, and a win driven by that is not a win.

## Is it even runnable — the number, before any token is spent

From R2 PANEL-A's own usage block (5,098,607 prompt tokens and 216,677
completion tokens over 15,433 calls in 5,854.2 s): mean prompt **330.4 tokens**,
mean completion **14.0 tokens**. PANEL-B is 37,002 calls (arm + control).

| reader | seconds per call | PANEL-B wall time |
|---|---|---|
| Qwen2.5-7B-Instruct-Q4_K_M (measured) | 0.379 | **3.9 hours** |
| Qwen3-30B-A3B at the CONTENDED 5.6 tok/s prompt eval | 59.7 | **25.6 days** |

The contended figures come from `HANDOFF_2026-09-10` §3 and were taken while a
PyInstaller build saturated all 20 cores; that document calls them a lower
bound. **The idle re-measurement is therefore not tidiness — it is the
difference between an arm that can be run and one that cannot.** If idle
prompt-eval does not improve by roughly an order of magnitude, `R2-Qwen3` is not
a nightly arm at any `--n-cpu-moe`, and the honest outcome is to say so.

## The protocol, frozen

`scripts/night_l4_qwen3_measure.py` writes it in full to its receipt:
idle precondition (the shared `scripts/gpu_guard` check, > 3 GB held by another
process refuses) · sweep `--n-cpu-moe ∈ {48, 40, 32, 24}` via
`AEGIS_LLAMA_N_CPU_MOE`, `stop()`/`start()` by PID between settings and never by
image name, stopping once VRAM is within 500 MiB of the 6,866 MiB usable · at
each setting VRAM, load seconds, **prompt-eval tok/s** (the decisive number) and
generation tok/s on R2's own frozen prompts · then the refusal rate over **200**
PANEL-B digests, a refusal being an unparseable reply, a declined answer, or
`llm_language.refuse()` firing on a >10% non-Latin-script reply, compared
against Qwen2.5-7B's rate on the SAME 200 prompts rather than against zero.

**That job never starts or stops `llama-server`.** With the reader down it
writes `PENDING_MODEL` plus this protocol and the file check, so the run that
happens when the desktop shell brings the server up asks this question and not
a similar one.
