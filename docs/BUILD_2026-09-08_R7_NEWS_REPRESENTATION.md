# BUILD 2026-09-08 — R7: LEARN A REPRESENTATION OF NEWS WITHOUT RETURNS, THEN ASK IT ABOUT RETURNS

**Mandate (Murat):** *"train more on news data."* The standing mistake is to
supervise everything on returns. Return labels are scarce and noisy; unlabelled
news is not. So the unlabelled text pays for the representation and the scarce
labels are spent only on a small head.

**Licence:** `RESEARCH_CLAIM` discipline applied to a `PRODUCT_EXPERIMENT`-scale
question — pre-declared family, walk-forward folds, embargo, three eras never
pooled, MDE before the confirmation. **No order, no deploy, no seal, no push,
no git state change. DeepSeek spend: $0.00** — every LLM call in this lane went
to the local 7B on the laptop's own GPU.

*Written incrementally as each piece landed; sections appear in the order they
were produced.*

---

## 0. RESULT, FIRST PARAGRAPH

**RESULT IMPROVEMENT: NONE on any book.** No strategy moved, no lane changed,
nothing is promoted. What this lane produced is five measurements that did not
exist yesterday:

1. **The labelled overlap is 9,457 (permno, month) cells over 115 months and
   135 names** — and that is the whole ceiling, because CRSP/`train_table`
   forward returns end **2024-12** while the dense whole-market news coverage is
   **2025–2026**. The years with coverage have no prices; the years with prices
   have ~1% coverage (E1 §4 measured 0.8–1.2% per year for 2015-2024). Every
   return number below is therefore computed on a ~83-name monthly cross-section
   of mostly large caps, and the MDE is printed beside every null.
2. **The self-supervised representation learns business structure — but the
   honest multiple is 1.2–2.2×, not 18×.** On documents the encoder has never
   seen it picks the other article about the same company out of 256 candidates,
   from company-masked text, at 7.4–11.5% against a 0.39% chance floor. *A
   random-init encoder of the identical architecture scores 5.3–6.4%* — a random
   projection of a token bag is already a locality-sensitive hash — so the claim
   is **trained-over-random**, and it is 1.16× / 1.69× / 2.17× as the
   pre-training corpus grows from 25k to 141k documents. **TF-IDF beats the
   neural encoder until ~140k documents** (§4). I wrote "18× chance" in a draft
   of this paragraph before the control ran; the control is why it does not
   say that now.
3. **The company mask holds; the calendar does not.** A separate model asked to
   name the issuer from the masked text answers `UNKNOWN` 353 times in 400 and
   scores 1.75% against a 0.74% floor (exact binomial p = 0.031). Asked the
   *year*, it scores **29.75% against a 10% floor (p < 1e-8)**. Masked financial
   news leaks its era loudly and its issuer barely.
4. **No memory drop at the model's training cutoff** — 52.0% pre vs 50.3% post,
   a 1.7pp fall against an **11.4pp MDE**. That is `CANNOT_DETERMINE` dressed
   as a pass, and it is labelled as such rather than quoted as a clean bill.
5. **THE RETURN COMPARISON: TF-IDF WINS, AND NOTHING SURVIVES MULTIPLICITY.**
   Best arm on the primary metric is **`tfidf_svd`**, not the pre-trained
   encoder. Across all 83 test months TF-IDF-SVD scores mean rank-IC **0.0417
   (t 2.98)** against the PIT encoder's **0.0055 (t 0.39)** and the
   no-pre-training control's **0.0044 (t 0.36)**. Per era — which is the ruler,
   because three eras are never pooled — the family of 21 tests has minimum
   p = 0.0105 and **BH-FDR keeps nothing and Holm keeps nothing**. Every arm's
   long-short book is negative net of costs except one, and every DSR is
   `WITHIN_SELECTION_NOISE`. **The pre-trained 6M-parameter transformer does not
   beat TF-IDF on this task at this sample size, and that is the result.**

Section §6 is the section that decides the lane and it decides it against the
neural arm.

---

## 1. THE DESIGN, AND WHY IT IS SHAPED THIS WAY

| | |
|---|---|
| Unlabelled documents used for pre-training | **528,223** news documents, 2015-02 → 2026-12 |
| Labelled cells used for supervision | **9,457** (permno, month), 2015-02 → 2024-11 |
| Ratio | **56 unlabelled documents per labelled cell** |
| Returns seen by the pre-training | **zero** — pinned by a test that greps the source of every pre-training function for `TRAIN_TABLE`, `excess_vw`, `TARGET`, `ret_1m`, `mkt_vw` |

The pre-training corpus is the terminal repo's news corpus
(`aegis-alpha-terminal/state/corpus/observations/*.jsonl`, read-only from here),
after the E1/E2 pull that added 158,614 rows on 2026-09-07/08. **61% of
documents carry no body at all** (321,843 of 528,223), so this is
**headline-level** modelling and every number below should be read that way.

### What I actually did — and the honest alternative I did not do

The brief allowed *"an embedder plus a small trainable head"* where a full
pre-train is too heavy for an 8 GB card. **I did the full pre-train instead**,
from scratch, because the card turned out to support it: the model is 2.4–6.1 M
parameters and 6,000 optimisation steps cost 11–109 minutes on a GPU that was
simultaneously hosting a 7B chat server. Training my own encoder also removes
the one thing a downloaded embedder would have smuggled in — **somebody else's
training cutoff over an unknown corpus** — which is precisely the leak §5
exists to measure.

`nemotron-3-embed-1b` (NVIDIA NIM, free, dim 2048) is reachable and was **not**
used: the free tier returns HTTP 429 under load (BUILD_2026-09-07b §1) and this
lane needs 528k embeddings, not 500.

---

## 2. THE PRE-TRAINING TASK

Two self-supervised objectives on one encoder, **neither of which can see a
return**:

1. **Masked-token reconstruction.** 15% of non-pad, non-`[CLS]` tokens replaced
   by `[MASK]`; cross-entropy over the vocabulary, output head tied to the
   input embedding.
2. **Same-company contrastive (InfoNCE, in-batch negatives).** A positive pair
   is two documents about the **same company within ±45 days**. Temperature
   0.07, symmetric loss, 255 in-batch negatives.

### Company-identity masking, and why it is not optional

Every document's **own ticker and issuer-name tokens are replaced by `[co]`**
before anything else happens — in *all* arms, including the TF-IDF baseline, so
the comparison is level.

* It removes the trivial shortcut. A representation that encodes *"this is
  Apple"* lets a returns head learn a per-company constant — a fixed effect
  dressed as a news signal.
* It makes the contrastive task mean something: the only way left to match two
  documents to the same company is to recognise the **business**.
* It is the canary's condition (§5).

Generic corporate words (`inc`, `corp`, `group`, `holdings`, `plc`, …) are
**not** masked — masking them would delete ordinary English from every headline
for no gain. Measured effect: **474,769 of 12,796,188 tokens masked (3.71%)**,
touching **241,829 of 528,223 documents (45.8%)**. The other 54% of headlines
never named their own subject in the first place — *"10 Information Technology
Stocks With Whale Alerts In Today's Session"* is a real row.

**A limit, stated:** only the document's OWN issuer is masked. Co-mentioned
companies survive, so an AAPL headline can still read *"…tesla nvidia…"*. §5
measures what that costs.

---

## 3. MODEL, HARDWARE, THROUGHPUT

| | |
|---|---|
| Architecture | 4-layer pre-norm transformer encoder, `d_model` 192, 4 heads, FFN 512, GELU, dropout 0.1, learned positions, `[CLS]` pooling, tied MLM head |
| Sequence length | 48 word-level tokens (median document is 17 tokens, p95 is 55) |
| Vocabulary | per-slice, ≤ 24,000, min count 5, built **only on that slice's own text** — a vocabulary fitted on future text is itself a leak, and a quiet one |
| Framework | PyTorch **2.11.0+cu128** |
| GPU | **NVIDIA GeForce RTX 5060 Laptop, 8,151 MiB**, sharing the card with `llama-server` (Qwen2.5-7B-Q4_K_M, 5.3 GiB resident, PID 115608, untouched) |
| VRAM used by this lane | ≈ **1.9 GiB** peak; the job ran with 700–2,900 MiB free on the card and never OOM'd |
| Optimiser | AdamW, lr 3e-4, weight decay 0.01, 6% linear warmup, grad-norm clip 1.0, batch 256 |
| **Optimisation budget** | **6,000 steps for every slice** — so a difference between encoders is a difference in DATA, never in how long each was trained |
| Cost | **$0.00** |

### The four encoders

| slice | pre-training text | documents | vocab | params | epochs @ 6k steps | wall clock | UNK rate | final MLM loss | final contrastive top-1 |
|---|---|---|---|---|---|---|---|---|---|
| `pit2018` | `< 2018-01` | 25,522 | 5,014 | 2,424,278 | 61 | 839 s | 9.04% | 3.885 | **0.793** |
| `pit2021` | `< 2021-01` | 83,187 | 12,849 | 3,936,433 | 19 | 1,046 s | 4.94% | 4.471 | 0.690 |
| `pit2023` | `< 2023-01` | 140,669 | 19,339 | 5,189,003 | 11 | 662 s | 3.46% | 4.168 | 0.552 |
| `full` | **everything, incl. 2025-26** | 528,223 | 24,000 | 6,088,576 | 3 | 6,532 s | 3.41% | 4.618 | 0.329 |

Throughput, from the receipts (`documents seen ÷ wall clock`):
**6,677,024 docs/hr** (`pit2018`) · 5,441,234 (`pit2021`) · **8,419,984**
(`pit2023`) · **873,342** (`full`). The eight-fold fall on `full` is **not** the
GPU: it is the positive-pair sampler doing an `rng.choice` over a 500k index on
every step. Named because a future session will otherwise re-measure it, and
because it is the one cheap speed-up left in this module.

**Read the contrastive column carefully.** It falls with slice size because a
fixed 6,000-step budget buys 61 passes over 25k documents and 3 passes over
528k. It is a training-set number. The held-out version is §4 and it does not
have this problem.

### An initialisation bug I wrote and fixed before it reached a result

The first run reported an MLM loss of **27.3** against a chance floor of
`ln(5014) = 8.52` — the model spent its whole budget undoing its own
initialisation, and the contrastive head never left chance (loss 5.53 ≈
`ln(256)`, top-1 1.2%). Cause: `nn.Embedding`'s torch default is `N(0,1)`,
which through a **tied** 192-dim output head produces logits of sd ≈ 14.
BERT-style `N(0, 0.02)` init plus warmup fixed it; the same slice then reached
MLM 3.885 and contrastive top-1 0.793. **A model that is "training" while its
loss sits above the chance floor is not training**, and the chance floor is
`ln(V)` — cheap to print, and it is now printed.

---

## 4. WHAT THE REPRESENTATION LEARNED — MEASURED WITHOUT A SINGLE RETURN

**The probe.** Take documents the encoder has never seen (strictly after its own
cutoff), sample 30,000 same-company pairs within ±45 days, and ask: does the
`[CLS]` vector of document A pick document B out of **256 candidates**, from
**company-masked** text? Chance is 1/256 = **0.391%**. Same-company distractors
inside a batch are excluded from the argmax — grading a correct match as a miss
would understate the probe. 10,240 trials per row.

Receipt: `backend/data/optimus/r7_news_representation/R7_match_battery.json`.

| slice | pre-train docs | scorer | top-1 | hits / trials | **trained ÷ this** | z |
|---|---|---|---|---|---|---|
| `pit2018` | 25,522 | **trained** | **7.383%** | 756 / 10,240 | — | — |
| `pit2018` | — | random-init, same architecture | 6.377% | 653 / 10,240 | **1.16×** | +2.84 |
| `pit2018` | — | TF-IDF → SVD-192 | **10.889%** | 1,115 / 10,240 | **0.68×** | **−8.72** |
| `pit2021` | 83,187 | **trained** | **9.854%** | 1,009 / 10,240 | — | — |
| `pit2021` | — | random-init | 5.830% | 597 / 10,240 | **1.69×** | +10.74 |
| `pit2021` | — | TF-IDF → SVD-192 | 10.039% | 1,028 / 10,240 | 0.98× | −0.44 |
| `pit2023` | 140,669 | **trained** | **11.504%** | 1,178 / 10,240 | — | — |
| `pit2023` | — | random-init | 5.293% | 542 / 10,240 | **2.17×** | +16.12 |
| `pit2023` | — | TF-IDF → SVD-192 | 9.434% | 966 / 10,240 | **1.22×** | **+4.84** |

**Three things, and the third is the one worth keeping.**

1. **The random-init control is not a floor of zero.** A frozen random
   projection of a token bag retrieves the right company 5.3–6.4% of the time —
   13–16× chance — because it is a locality-sensitive hash over shared rare
   tokens. Any paper that quotes "N× chance" without this control is quoting the
   hash. My own first draft did exactly that, at 18×; the honest number is
   **1.16× / 1.69× / 2.17× over random**, and pre-training is doing real work.
2. **The advantage over random GROWS monotonically with the pre-training
   corpus** — 25k → 83k → 141k documents buys 1.16× → 1.69× → 2.17× at a
   *fixed* 6,000-step optimisation budget. So the constraint is data, not
   compute, and the 2025-26 pull (which added 317k documents that cannot be
   scored on returns) is nonetheless the right thing to have done.
3. **TF-IDF beats the encoder until roughly 140k documents.** At 25k it wins
   decisively (z −8.7). At 83k it is a statistical tie. At 141k the encoder
   finally overtakes it (z +4.8). *That crossover point is the most useful
   number in this document*, because it says what a bigger corpus buys and
   roughly when.

This is a claim about **text**, not about money. It is stated separately from
every return number below, because they are different claims and the whole
failure mode of this lane would be to let the first one vouch for the second.
§6 shows that it does not.

---

## 5. THE LEAK GATE — RUN, AND ONE HALF OF IT FAILED

Receipt: `backend/data/optimus/r7_news_representation/R7_leak_gate.json`.
Backend `local_gguf` (Qwen2.5-7B-Instruct-Q4_K_M), 1,400 calls, 145,909 tokens
in / 4,517 out, **482 s wall clock, $0.00**, zero provider failures.

### 5a. Canary — can a separate model recover what the mask removed?

| question | n | hits | accuracy | floor | exact binomial p (greater) | verdict |
|---|---|---|---|---|---|---|
| **Which company is this masked headline about?** | 400 | 7 | **1.75%** | 0.74% (uniform over the 135-name labelled universe) | **0.031** | mask mostly holds — 353 of 400 answers were `UNKNOWN` |
| **What year was it published?** | 400 | 119 | **29.75%** | 10% | **< 1e-8** | **the calendar LEAKS, loudly** |

The company line is a *pass with a caveat*: 2.4× a uniform floor, p = 0.031,
inside a 1.20pp 80%-power MDE. The most common non-`UNKNOWN` guesses were `GS`
(5) and `MS` (4) — the model reaches for a plausible mega-cap, which is a prior,
not a recovery.

**The year line is the finding, and it is a warning about every arm in §6.** A
representation trained on masked financial news knows what era it is in — from
vocabulary drift (`covid`, `ai`, `crypto`, ticker fashions) — and *era is
regime*. A model that has learned the calendar has learned something that
correlates with market state without being news about a company. This is
exactly why §6 carries a `full` encoder (which has read 2025-26) beside PIT
encoders (which have not): the gap between them prices the leak instead of
assuring it away.

### 5b. Memory — Gao-Jiang-Yan pre/post cutoff

Qwen2.5's published data cutoff is **2023-10**. Each document is handed to the
model **unmasked, with its ticker and its date** — the memory-maximal condition
— and the model is asked whether the stock beat or lagged the market over the
following month.

| window | n graded | accuracy | share answered BEAT | base rate actually positive |
|---|---|---|---|---|
| **PRE-cutoff** (≤ 2023-10) | 300 | **52.0%** | 79.3% | 49.3% |
| **POST-cutoff** (2024-01 … 2024-11) | 300 | **50.3%** | 78.0% | 44.3% |

| | |
|---|---|
| accuracy drop at the cutoff | **+1.67pp** |
| **MDE at 80% power** | **11.44pp** |
| verdict | **NO MEMORY DROP DETECTED — which is not the same as no memory** |

Two things must be read together or the row lies. The model answers **BEAT
about 79% of the time in both windows**, so its accuracy is very nearly its
answer's base rate; and the 1.67pp fall is **one seventh** of the smallest drop
this sample could have detected. The honest verdict is *"we could not tell"*,
and the receipt says so in those words. The prior evidence stands unchanged:
AMNESIA-1 measured that instructing a model to forget does **nothing** (15.8%
vs 15.8%), so nothing here was instructed away — it was measured, at $0.

**What this licenses:** nothing built on this model's direction call. No arm in
§6 uses an LLM output as a feature. The gate was run because the lane would be
dishonest without it, and it came back `CANNOT_DETERMINE` at the sample size
the wall clock allowed.

---

## 6. THE COMPARISON THAT DECIDES THE LANE — AND TF-IDF WINS IT

Receipt: `backend/data/optimus/r7_news_representation/R7_evaluate.json`
(+ one `per_month_<arm>.csv` per arm).

### 6a. The arms

| arm | what it is |
|---|---|
| `pit_mean` | the **PIT** pre-trained encoder, mean-pooled per cell — **coverage-NORMALISED** |
| `pit_sum` | the same encoder, sum-pooled — **NOT coverage-normalised** |
| `full_mean` | the encoder pre-trained on **all** text including 2025-26 — the deliberately **LEAKY** comparator, so the leak gets a price rather than an assurance |
| `rand_mean` | the identical architecture, identical vocabulary, identical tokenisation, **frozen at random init** — the *no-pre-training* control (a) |
| `tfidf_svd` | TF-IDF → SVD to the **same 192 dimensions** — baseline (b), dimension-matched |
| `tfidf_raw` | TF-IDF, ridge straight onto the 20,000-dimension sparse matrix |
| `coverage` | the **document count alone** (n, log1p n, distinct independence groups) — baseline (c), Murat's standing warning made into an arm |

Every arm shares the head (ridge, alpha picked on the *tail* of the training
window), the folds, the target, the cost model and the company-masked text.
TF-IDF is re-fitted **on training months only** inside every fold.

### 6b. Primary metric — mean monthly cross-sectional rank-IC, per era

**E1 (2018-2020, 36 months)**

| arm | n months | names/mo | mean rank-IC | t | p |
|---|---|---|---|---|---|
| `pit_mean` | 36 | 73.5 | -0.01403 | -0.853 | 0.3993 |
| `pit_sum` | 36 | 73.5 | 0.01171 | 0.559 | 0.57956 |
| `full_mean` | 36 | 73.5 | 0.02511 | 1.251 | 0.2192 |
| `rand_mean` | 36 | 73.5 | 0.00307 | 0.194 | 0.84756 |
| `tfidf_svd` | 36 | 73.5 | 0.04274 | 2.297 | 0.02775 |
| `tfidf_raw` | 36 | 73.5 | 0.03541 | 1.199 | 0.2386 |
| `coverage` | 36 | 73.5 | -0.03002 | -1.27 | 0.21248 |

**E2 (2021-2022, 24 months)**

| arm | n months | names/mo | mean rank-IC | t | p |
|---|---|---|---|---|---|
| `pit_mean` | 24 | 100.0 | -0.01873 | -0.588 | 0.56243 |
| `pit_sum` | 24 | 100.0 | -0.03359 | -1.294 | 0.20836 |
| `full_mean` | 24 | 100.0 | -0.01473 | -0.416 | 0.68119 |
| `rand_mean` | 24 | 100.0 | -0.02424 | -0.932 | 0.36113 |
| `tfidf_svd` | 24 | 100.0 | 0.01192 | 0.384 | 0.70448 |
| `tfidf_raw` | 24 | 100.0 | 0.00929 | 0.335 | 0.74077 |
| `coverage` | 24 | 100.0 | 0.01046 | 0.328 | 0.74585 |

**E3 (2023-2024, 23 months)**

| arm | n months | names/mo | mean rank-IC | t | p |
|---|---|---|---|---|---|
| `pit_mean` | 23 | 110.0 | 0.0615 | 2.16 | 0.04194 |
| `pit_sum` | 23 | 110.0 | 0.05398 | 2.064 | 0.05105 |
| `full_mean` | 23 | 110.0 | 0.02767 | 0.751 | 0.46048 |
| `rand_mean` | 23 | 110.0 | 0.0364 | 1.525 | 0.14153 |
| `tfidf_svd` | 23 | 110.0 | 0.07122 | 2.8 | 0.01045 |
| `tfidf_raw` | 23 | 110.0 | 0.07562 | 2.616 | 0.01577 |
| `coverage` | 23 | 110.0 | 0.02243 | 0.811 | 0.42611 |

**All 83 test months pooled — reported for completeness and NOT the ruler**

| arm | n months | names/mo | mean rank-IC | t | p |
|---|---|---|---|---|---|
| `pit_mean` | 83 | 97.0 | 0.00554 | 0.385 | 0.70144 |
| `pit_sum` | 83 | 97.0 | 0.01033 | 0.73 | 0.46726 |
| `full_mean` | 83 | 97.0 | 0.0143 | 0.853 | 0.39635 |
| `rand_mean` | 83 | 97.0 | 0.00441 | 0.36 | 0.71993 |
| `tfidf_svd` | 83 | 97.0 | 0.04172 | 2.976 | 0.00383 |
| `tfidf_raw` | 83 | 97.0 | 0.039 | 2.275 | 0.02549 |
| `coverage` | 83 | 97.0 | -0.00378 | -0.239 | 0.81145 |

**Read it in this order.**

* **TF-IDF is the best text arm in every era.** `tfidf_svd` scores +0.043 /
  +0.012 / +0.071 against `pit_mean`'s −0.014 / −0.019 / +0.062.
* **The no-pre-training control is not cleanly beaten.** `rand_mean` scores
  +0.003 / −0.024 / +0.036 against `pit_mean`'s −0.014 / −0.019 / +0.062. The
  pre-trained encoder is **worse than random init in E1**, better by a whisker
  in E2, and better in E3 — and in no era does it beat *both* controls, because
  TF-IDF is ahead of it in all three.
* **The pre-trained encoder's one nominally significant cell is E3**
  (IC 0.0615, t 2.16, p 0.042) — and `tfidf_svd` and `tfidf_raw` beat it in the
  same era at p 0.010 and p 0.016. It is the third-best number in its own row.
* **Coverage alone is noise** (−0.030 / +0.010 / +0.022, |t| ≤ 1.27), which is
  the reassuring half of Murat's warning. §7 has the other half.

### 6c. Beta FIRST, then the book, then the costs

Turnover is measured name by name from actual quintile membership, month over
month. `house` = 6 bp one-way (`config.py`: slippage 5 + commission 1);
`stress` = 25 bp one-way (the construction-tax stress, S38 2026-09-07).

**All 83 test months**

| arm | **beta (LS)** | **beta (long-only)** | LS gross %/mo | LS net 6bp %/mo | LS net 25bp %/mo | t (net) | Sharpe ann (net) | cost %/mo |
|---|---|---|---|---|---|---|---|---|
| `pit_mean` | -0.2464 | 0.2799 | -1.679 | -1.8465 | -2.3768 | -2.329 | -0.886 | 0.1675 |
| `pit_sum` | -0.3377 | 0.2251 | -0.2129 | -0.3835 | -0.9235 | -0.436 | -0.166 | 0.1705 |
| `full_mean` | 0.0811 | 0.3477 | -1.0345 | -1.1903 | -1.6835 | -1.448 | -0.551 | 0.1558 |
| `rand_mean` | 0.0564 | 0.3733 | -1.3869 | -1.5715 | -2.156 | -2.544 | -0.967 | 0.1846 |
| `tfidf_svd` | -0.0922 | 0.4121 | 0.6121 | 0.4358 | -0.1223 | 0.572 | 0.218 | 0.1763 |
| `tfidf_raw` | 0.0042 | 0.4027 | -0.187 | -0.3623 | -0.9175 | -0.436 | -0.166 | 0.1753 |
| `coverage` | 0.1703 | 0.4067 | -0.6277 | -0.7935 | -1.3182 | -0.945 | -0.359 | 0.1657 |

Beta is printed first because it is the only column that is reliably non-zero.
The long-short book's loading on the CRSP value-weight market runs −0.34 to
+0.17 — **a dollar-neutral quintile book is not a market-neutral one** once the
quintiles tilt — and the long-only leg carries beta 0.23–0.41 against a market
whose own return is already subtracted from the target. Mean cost is
~0.17%/month at 6 bp, i.e. **~2%/yr, which on its own exceeds every gross edge
in the table**.

### 6d. Multiplicity — the family was declared before the arms were read

Family = **7 arms × 3 eras = 21 tests** on the primary metric. The pooled `ALL`
rows and the two diagnostic arms of §6f are **not** in the family.

| | |
|---|---|
| family size | **21** |
| family min p | **0.01045** (`tfidf_svd` E3) |
| family max p | 0.84756 |
| **SCREEN — BH-FDR (q = 0.05)** | survivors: **[]** |
| **EXPORT — Holm (α = 0.05)** | survivors: **[]** |
| screened-not-exported | [] |

**Nothing survives screening, so nothing reaches export.** BH-FDR would need
p ≤ 0.0024 at rank 1 and the smallest p in the family is 0.0105.

### 6e. Deflated Sharpe, at the declared 21 trials

| arm | Sharpe (monthly, net) | n periods | DSR | verdict |
|---|---|---|---|---|
| `pit_mean` | -0.2557 | 83 | 0.0 | WITHIN_SELECTION_NOISE |
| `pit_sum` | -0.0479 | 83 | 0.0094 | WITHIN_SELECTION_NOISE |
| `full_mean` | -0.1589 | 83 | 0.0002 | WITHIN_SELECTION_NOISE |
| `rand_mean` | -0.2793 | 83 | 0.0 | WITHIN_SELECTION_NOISE |
| `tfidf_svd` | 0.0628 | 83 | 0.0877 | WITHIN_SELECTION_NOISE |
| `tfidf_raw` | -0.0479 | 83 | 0.0096 | WITHIN_SELECTION_NOISE |
| `coverage` | -0.1037 | 83 | 0.0019 | WITHIN_SELECTION_NOISE |

Every arm is `WITHIN_SELECTION_NOISE`. `tfidf_svd` is the only positive Sharpe
in the table and its DSR is 0.088 against a 0.95 bar.

### 6f. The harness could have seen an effect — a null owes two tests

A null is a finding only if the machine that produced it can detect a real
signal. Two diagnostic arms run through the *identical* ridge, standardisation,
folds, costs and metrics — and are excluded from the family above:

| arm | era | n months | mean rank-IC | t | LS net %/mo | Sharpe ann |
|---|---|---|---|---|---|---|
| `planted_signal` | E1 | 36 | 0.89424 | 293.726 | 32.8809 | 12.176 |
| `planted_signal` | E2 | 24 | 0.8978 | 188.701 | 34.2917 | 19.095 |
| `planted_signal` | E3 | 23 | 0.89578 | 294.976 | 43.4929 | 7.912 |
| `planted_signal` | ALL | 83 | 0.8957 | 433.741 | 36.2295 | 9.731 |
| `pure_noise` | E1 | 36 | 0.00647 | 0.35 | -0.079 | -0.045 |
| `pure_noise` | E2 | 24 | -0.00293 | -0.163 | -1.412 | -1.008 |
| `pure_noise` | E3 | 23 | -0.01879 | -1.043 | -1.3493 | -1.045 |
| `pure_noise` | ALL | 83 | -0.00325 | -0.303 | -0.8165 | -0.531 |

`planted_signal` (the fold's own target rank plus noise, a deliberate leak)
scores IC 0.90 at t 294. `pure_noise` scores IC −0.003 at t −0.30. **The harness
works.** The null in §6b is a null about the data, not about the plumbing.

---

## 7. COVERAGE NORMALISATION — WITH AND WITHOUT

Three arms answer this directly, and the answer is not the one the warning
usually implies.

| mean rank-IC | E1 | E2 | E3 | ALL |
|---|---|---|---|---|
| `pit_mean` — **normalised** (mean pool) | −0.0140 | −0.0187 | **+0.0615** | +0.0055 |
| `pit_sum` — **NOT normalised** (sum pool) | +0.0117 | −0.0336 | +0.0540 | +0.0103 |
| `coverage` — the count **alone** | −0.0300 | +0.0105 | +0.0224 | −0.0038 |

**The finding: at this sample size normalisation flips the sign in two of three
eras and is not decidable.** Mean-pool wins E2 and E3, sum-pool wins E1 and the
pooled row; the largest gap (E2, 0.0149 IC) is a sixth of that era's 0.089 MDE.
The honest verdict is **CANNOT_DETERMINE which pooling is better**, with two
asymmetries worth keeping:

* the **un-normalised** arm's book swings hardest between eras (−0.71%, −2.01%,
  +1.82% net per month) because sum-pooling makes the feature scale with
  document count, and document count is a *market-wide* variable that moves with
  the news cycle. That is the mechanism behind Murat's warning, visible even
  where the IC cannot separate the two;
* the **count alone** carries no return information here (|t| ≤ 1.27 in every
  era) — a name with more news is indeed not a name with more signal, at least
  on a 135-name large-cap panel where every name is well covered.

**This test would be far sharper on the 2025-26 whole-market corpus**, where
coverage per name spans three orders of magnitude instead of one. It cannot be
run there, because there are no forward returns after 2024-12.

---

## 8. THE WALK-FORWARD DESIGN, AND THE MDE

| | |
|---|---|
| unit | (permno, month) cell carrying ≥ 1 news document |
| target | `excess_vw_1m` — forward 1-month return in excess of the CRSP value-weight market |
| folds | **annual refit, expanding**: train months ≤ (Y−1)-11, **embargo (Y−1)-12**, test all of Y |
| purge rationale | the target at month *m* is the return over *m+1*, so one embargo month puts a clear month between the last training target window and the first test one |
| CV | **calendar walk-forward only.** A test asserts the module contains no `KFold`, `train_test_split` or `ShuffleSplit` |
| test years | 2018–2024 (2015-2017 are training-only; the panel starts 2015-02) |
| eras | E1 2018-2020 · E2 2021-2022 · E3 2023-2024. **Never pooled for the verdict.** |
| PIT encoder per era | E1 ← text `< 2018-01` · E2 ← `< 2021-01` · E3 ← `< 2023-01`, **vocabulary included** |
| min names per month | 20 |
| **n_effective** | **TEST MONTHS (date blocks)**: 36 / 24 / 23. Name-months (2,646 / 2,428 / 2,517) are in the receipt under the key `n_name_months_DO_NOT_USE_AS_N` |

### MDE and power — printed BEFORE the confirmation

| arm | era | **n_eff = date blocks** | name-months (NOT n) | IC sd | **MDE mean IC** | observed IC | **MDE LS %/mo** | observed LS net %/mo |
|---|---|---|---|---|---|---|---|---|
| `pit_mean` | E1 | 36 | 2646 | 0.0987 | 0.0461 | -0.01403 | 2.7351 | -2.5524 |
| `pit_mean` | E2 | 24 | 2428 | 0.1561 | 0.0893 | -0.01873 | 3.3507 | -1.6082 |
| `pit_mean` | E3 | 23 | 2517 | 0.1366 | 0.0798 | 0.0615 | 5.91 | -0.9901 |
| `pit_sum` | E1 | 36 | 2646 | 0.1256 | 0.0587 | 0.01171 | 4.3255 | -0.7057 |
| `pit_sum` | E2 | 24 | 2428 | 0.1271 | 0.0727 | -0.03359 | 4.1816 | -2.0077 |
| `pit_sum` | E3 | 23 | 2517 | 0.1255 | 0.0733 | 0.05398 | 3.6357 | 1.8158 |
| `full_mean` | E1 | 36 | 2646 | 0.1204 | 0.0562 | 0.02511 | 2.4846 | 0.9393 |
| `full_mean` | E2 | 24 | 2428 | 0.1734 | 0.0992 | -0.01473 | 3.9216 | -1.5956 |
| `full_mean` | E3 | 23 | 2517 | 0.1767 | 0.1032 | 0.02767 | 5.7961 | -4.1005 |
| `rand_mean` | E1 | 36 | 2646 | 0.0951 | 0.0444 | 0.00307 | 1.7285 | -0.3776 |
| `rand_mean` | E2 | 24 | 2428 | 0.1274 | 0.0729 | -0.02424 | 3.132 | -0.718 |
| `rand_mean` | E3 | 23 | 2517 | 0.1145 | 0.0669 | 0.0364 | 4.2854 | -4.3308 |
| `tfidf_svd` | E1 | 36 | 2646 | 0.1117 | 0.0521 | 0.04274 | 3.0846 | 0.6307 |
| `tfidf_svd` | E2 | 24 | 2428 | 0.1521 | 0.087 | 0.01192 | 3.3459 | -0.5329 |
| `tfidf_svd` | E3 | 23 | 2517 | 0.122 | 0.0713 | 0.07122 | 4.9811 | 1.1416 |
| `tfidf_raw` | E1 | 36 | 2646 | 0.1772 | 0.0827 | 0.03541 | 3.2149 | 0.431 |
| `tfidf_raw` | E2 | 24 | 2428 | 0.136 | 0.0778 | 0.00929 | 3.4441 | 0.0135 |
| `tfidf_raw` | E3 | 23 | 2517 | 0.1386 | 0.081 | 0.07562 | 5.7273 | -1.9964 |
| `coverage` | E1 | 36 | 2646 | 0.1418 | 0.0662 | -0.03002 | 3.3426 | -1.9779 |
| `coverage` | E2 | 24 | 2428 | 0.1562 | 0.0893 | 0.01046 | 4.1223 | 0.4405 |
| `coverage` | E3 | 23 | 2517 | 0.1327 | 0.0775 | 0.02243 | 5.1602 | -0.2271 |

**How to read a null here.** In E1 the pre-trained arm could only have detected
a mean rank-IC of **0.046** or a long-short of **2.74%/month**; in E3 the bars
are **0.080** and **5.91%/month**. Observed effects are a fraction of those.
`learner.inference.power_note` on the best arm's book says `tfidf_svd` E1 would
need **36.6 years** of tape to reach t = 2 and has 3.0; E3 would need **18.6
years** and has 1.92. **These are underpowered cells, not demonstrated zeros.**
The correct verdict for the return question is `CANNOT_DETERMINE` for every
effect smaller than the MDE column — and none is larger.

---

## 9. WHAT DID NOT WORK, AND WHAT I GOT WRONG

1. **The pre-trained encoder does not beat TF-IDF on returns.** Not in any era,
   not pooled, not normalised, not un-normalised. A 6M-parameter transformer
   pre-trained on 528,223 headlines loses to a bag of words with an SVD on it.
   That is the lane's headline and it is not softened anywhere in this document.
2. **I over-claimed the representation result before the control ran.** A draft
   of §0 said the encoder retrieves the same company at "18× chance". It does —
   and so does a **random-init encoder of the identical architecture**, at 13–16×
   chance, because a random projection of a token bag is a locality-sensitive
   hash. The defensible multiple is **trained ÷ random = 1.16× / 1.69× / 2.17×**.
   A "× chance" number with no untrained control is a number about tokenisation.
3. **A fixed step budget flatters the small slices and starves the big one.**
   6,000 steps is 61 epochs over 25k documents and 3 epochs over 528k. It is the
   right control for *"does more DATA help"* and the wrong one for *"how good can
   this get"*. The `full` encoder is undertrained and should not be read as the
   ceiling of the architecture.
4. **The masked text leaks its YEAR at 3× chance (p < 1e-8).** Company identity
   is masked; the calendar is not maskable. A representation that knows the era
   knows the regime, and on a 115-month panel regime *is* most of the variance.
   This is the strongest argument against believing any positive result this
   lane could have produced, and it is why the PIT/`full` split exists.
5. **The leak gate came back `CANNOT_DETERMINE`, not clean.** 1.67pp against an
   11.44pp MDE. 600 graded answers is what 8 minutes of local 7B buys; a real
   Gao-Jiang-Yan reading needs thousands. The direction call is unusable either
   way — the model answers BEAT 79% of the time in both windows.
6. **An initialisation bug cost the first pre-training run.** MLM loss 27.3
   against an `ln(V)` chance floor of 8.52, contrastive stuck at chance. Torch's
   `nn.Embedding` default `N(0,1)` through a tied output head. Fixed with
   BERT-style `N(0, 0.02)` and warmup. **Print the chance floor beside the loss**
   — it is one line and it turns "training" into "not training".
7. **`independence_group` was not carried into the masked table** and the first
   run of the arm builder died on a `KeyError` after loading 528k rows. Caught by
   a dry run against a temp output directory *before* the real encoders existed,
   which is the only reason it cost two minutes instead of an hour.
8. **What I did NOT do:** no per-fold re-pre-training (three PIT encoders at era
   boundaries instead of seven, which is conservative but coarse); no
   next-event-prediction and no temporal-ordering objective (the year leak in §5
   makes an explicit ordering objective actively dangerous here); no NVIDIA
   embedder (rate-limited); no daily-frequency test (the repo has no CRSP daily
   file — only `crsp__msf`); no use of the 2025-26 corpus for supervision,
   because there are no returns there.

---

## 10. THE STRUCTURAL FINDING, WHICH OUTLASTS THE NULL

> **The years with news coverage have no prices, and the years with prices have
> no news coverage.**

| | 2015-2024 | 2025-2026 |
|---|---|---|
| news documents | 206,728 | 321,495 |
| distinct symbols with news | 96 → 151 per year | 5,620 → 5,660 per year |
| universe coverage (E1 §4) | **0.8% – 1.2%** | **43.7% – 46.1%** |
| forward returns in `train_table` | **yes, to 2024-12** | **none** |
| labelled (permno, month) cells | **9,457** | **0** |

Every return number in this document is computed on **135 large-cap names**.
That is not a whole-market test of news and it cannot be made into one by any
modelling choice. Two things would change it, in order of value:

1. **Extend the return panel past 2024-12.** The 2025-26 corpus is 5,600 names
   deep and completely unusable today. This is the single highest-value unblock
   in the lane and it is a data job, not a research job.
2. **Run the 2015-2024 whole-market Alpaca pull** (E1 §8: ~50 h, resumable,
   wants a deliberate attended start). That converts 0.8-1.2% coverage into
   something a cross-sectional test can use on the years that *do* have returns.

Until one of those lands, the correct verdict on "does news text predict
returns" from this repository is **CANNOT_DETERMINE at any effect smaller than
a mean rank-IC of about 0.05 per era**, and the representation work is best
judged on §4's text metrics, where the sample is 30,000 pairs rather than 83
months.

---

## 11. TESTS

`backend/tests/test_r7_news_representation.py` — **60 tests, all offline**, no
torch import at module import time, no GPU required, no network. They pin:

| group | what it stops |
|---|---|
| text handling (4) | HTML entities and tags surviving into the corpus; an unbounded body |
| company masking (5) | the mask silently doing nothing; generic corporate words being deleted from every headline; a missing `crsp__stocknames_v2` being a skip instead of a refusal |
| vocabulary / encoding (4) | specials moving off 0-3; `min_count` / `max_vocab` drifting; a missing `[CLS]`; truncation without padding |
| **the PIT ticker join (3)** | a ticker reused by a later company inheriting the earlier permno; an unmatched ticker being dropped instead of left unresolved; one document producing two rows |
| **coverage normalisation (2)** | mean-pool and sum-pool becoming the same thing |
| monthly metrics / costs (5) | one row per *name-month* instead of per *month*; a thin month being scored; **costs being omitted from the net column** |
| statistics (6) | a t on n < 3; a beta that does not recover a planted loading; an MDE that does not fall with n |
| **the walk-forward boundary (4)** | the embargo month vanishing; a test year with no era; an era's PIT encoder cut off *after* its own first test month |
| **no return reaches the pre-training (3)** | asserted on the SOURCE of `build_docs`, `pretrain`, `run_pretrain`, `prepare_masked`, `mask_company`, `build_vocab` for `TRAIN_TABLE` / `excess_vw` / `TARGET` / `ret_1m` / `mkt_vw` |
| refusals (5) | a missing corpus, an empty corpus, a missing docs table, a missing checkpoint or a too-thin slice being a silent skip |
| the leak gate's grading (5) | a provider failure graded as a wrong answer; accuracy printed without the BEAT share and the base rate; a null printed without its MDE |
| the match battery (3) | a same-company distractor graded as a miss; the first N pairs (one era) being taken instead of a uniform sample |
| the arm list + no random k-fold (3) | an arm quietly disappearing; `KFold` / `train_test_split` / `ShuffleSplit` entering the module |

**Whole fast suite, after every change in this lane:**

```
AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -q -m "not slow" -p no:randomly --timeout=300
7821 passed, 20 skipped, 124 deselected, 501 warnings in 519.88s (0:08:39)
```

**0 failed.** The lane's starting baseline was 7,410 passed; the difference is
this lane's 60 plus other agents' tests landing in the same tree during the
session.

**Guard-contract enrolment:** not required. `backend/tests/guard_contract.py`
discovers refusal exceptions under `backend/services/` only, and this lane lives
entirely in `scripts/` — which is also why `signal_reachability` needs no entry.
`R7Refusal` is nonetheless contract-tested five times above, by hand, because
the rule is the point rather than the discovery mechanism.

---

## 12. FILES AND RECEIPTS

**New (mine):**

```
scripts/r7_news_representation.py                       the whole lane, one module
backend/tests/test_r7_news_representation.py            60 offline tests
backend/data/optimus/r7_news_representation/
    R7_docs_receipt.json          528,223 documents, per-year census, 142 shard hashes
    R7_masking_receipt.json       474,769 of 12,796,188 tokens masked
    R7_panel_receipt.json         9,457 labelled cells, 135 permnos, 115 months
    R7_pretrain_{pit2018,pit2021,pit2023,full}.json     loss curves, throughput, VRAM
    R7_match_battery.json         held-out same-company retrieval, 3 scorers x 3 slices
    R7_leak_gate.json             canary + Gao-Jiang-Yan, 1,400 local calls, $0.00
    R7_evaluate.json              7 arms x 3 eras + adjudication + power + MDE
    per_month_<arm>.csv           83 monthly rows per arm (IC, book, cost, holdings)
    docs.parquet, docs_masked.parquet, panel.parquet    intermediates
    encoder_*.pt, vocab_*.json    four encoders, 2.4M-6.1M params
```

### Which paths are DATA and which are RECEIPTS

| path | kind | size | in git? |
|---|---|---|---|
| `encoder_*.pt` | **DATA** — four checkpoints, regenerable in 11-109 min each | **70 MB** | **gitignored** (one line added to `.gitignore`) |
| `docs.parquet`, `docs_masked.parquet`, `panel.parquet` | **DATA** — intermediates | 110 MB | **gitignored** by the repo-wide `*.parquet` |
| `vocab_*.json` | **PROVENANCE** — the only way to check later whether a PIT encoder's vocabulary was fitted on future text | 1.0 MB | **tracked** |
| `R7_*.json` | **RECEIPTS** — every headline number in this document | 128 KB | **tracked** |
| `per_month_<arm>.csv` | **RECEIPTS** — the IC, book, cost and holdings of every test month | 240 KB | **tracked** |

**Edited:** `.gitignore` (one appended block, above) and nothing else outside
those two files. **No git command that changes
state was run.** No order, no deploy, no seal, no push. **DeepSeek spend:
$0.00.**

**Processes:** my own jobs ran as PIDs 137836 (pre-training) and 126180 (leak
gate) and exited on their own. The news puller PID 50240 and `llama-server`
PID 115608 were left alone and were both alive at the end of the session; the
Finnhub puller PID 139180 completed on its own during the session and was not
touched by me. **Nothing was killed by image name.**

---

## 13. WHAT THE NEXT SESSION SHOULD DO WITH THIS

1. **Do not fold any of this into `arena_composite`.** Nothing here earned a
   book. A new mechanism arrives as its own `PRODUCT_EXPERIMENT` book and this
   one has no mechanism yet.
2. **The reusable asset is §4's crossover**: the encoder overtakes TF-IDF at
   ~140k pre-training documents and the gap over random init grows monotonically
   with corpus size. If the corpus reaches 500k *labellable* documents, this
   experiment is worth re-running — and only then.
3. **The blocking job is returns after 2024-12**, not more modelling. §10.
4. **Re-use the harness, not the conclusion.** `--evaluate` takes any per-cell
   feature matrix and returns beta-first books, per-era ICs, turnover costs at
   two rates, a declared family, BH/Holm, DSR, MDE and a planted-signal check.
   That is the part of this lane with a longer half-life than its null.
