# SPEC — Chunk 9: E1-E4 heads vs GBM, L4 Qwen3-30B-A3B arm, the stage contract

Roadmap: `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
§3 (lane E), §9 (Lane M, M5), §11 (Qanat joins), §12 (chunk 9 row: *"E1-E4 heads
against GBM · L4 Qwen3 as a new arm · the stage contract (big) | a head beats
GBM and its three controls, or the result is filed"*).

Licence for every item below: `PRODUCT_EXPERIMENT` (internal sim + PAPER only).
No claim of alpha is made or permitted. Frozen strategy contract required
before the first decision each item makes (policy hash, timestamp, inputs,
costs, fill convention, objective) — reuse `backend/strategy/contract.py`'s
`Strategy`/`Objective`/`CostModel` dataclasses, do not invent a second schema.

Gate inherited from every one of N3's two `FAILED_VARIANT` runs (2026-09-10,
2026-09-11): an arm that does not beat SHUFFLE has found the calendar, not the
text. Nothing in this chunk is exempt from that control, including the new
mandatory GBM control from Lane M item M5 (Gu-Kelly-Xiu 2020: "trees and
shallow nets lead; no attention/memory architecture has beaten that bar on
cross-sectional returns" — GBM is a *control*, not a candidate to beat it).

---

## 1. E1 — the typed-event tabular head

### 1.1 Why this shape (read before building)

L2 (spec `docs/research_notes/2026-09-11/spec_events_and_calibration.md`) is
the upstream contract: 39 event types + `no_event`, each row carrying
`event_type, direction ∈ {-1,0,+1}, magnitude_bucket ∈ {NEGLIGIBLE..EXTREME},
confidence ∈ [0,1], scope (ticker), evidence_span`. E1 consumes L2's *output*,
not raw text — this is the thing N3 (frozen sentence embedding) already
FAILED_VARIANT'd twice on the same panel (2026-09-10 IC −0.0035, 2026-09-11
IC −0.0032, neither beating SHUFFLE), so E1 is a genuinely different feature
family, not a resubmission of the same text under a new name. If E1 also loses
to SHUFFLE, the finding is "the calendar/universe carries the return, not
information *about* the news" and stands independent of representation choice.

### 1.2 Feature table

Unit: same as N3 — one row per `(symbol, entry_date)` cell (a cell, not a
headline: the label is a property of the session).

**Event features** (from L2's typed rows, joined by `symbol` + a lookback
window ending at `entry_date - 1` session, PIT by construction because L2's
own `entry_date` anchoring already enforces "first open strictly after
publication"):
- one-hot `event_type × direction` (39 types × 3 directions = 117 columns,
  most zero per cell — this is exactly the sparse-count table LightGBM's
  native categorical/NaN handling is suited to; do NOT `fillna(0)` the
  *magnitude/confidence* companions, only the presence indicators are 0/1 by
  construction)
- `magnitude_bucket` mapped to its ordinal index (0-4) per active event
- `confidence` (mean per event_type if 2+ same-type events land in one
  window)
- counts of each event_type over three trailing windows: 1, 5, 21 sessions
  ending at `entry_date - 1` (three separate columns per type — this is where
  most of the 117×3 columns come from; cap the practical width by dropping
  event types with fewer than 30 occurrences panel-wide, logged in the
  receipt as `dropped_sparse_types`)
- `recency`: sessions since the most recent event of each type (capped at the
  panel's max lookback so a name with no history is not `inf`; a large
  sentinel — e.g. 252 — with a companion `is_censored` bool, never `fillna(0)`
  which would claim "an event happened today")

**PIT price features** (reuse N3's `_price_features`, `scripts/night_n3_frozen_embedding_head.py:143-159`,
verbatim — same shift-by-1 discipline, same 21-session rolling median dollar
volume): `pit_dv_21`, `mom_21`, `mom_5`. Do not recompute independently; import
the function.

**Label**: `x_oc` (SPY-excess open-to-close on the first session opening after
publication) for the 5-session and 21-session horizon variants — this means
building TWO label columns off the E1 panel's bars (`x_oc_h5`, `x_oc_h21`:
cumulative excess return from `entry_date` open to `entry_date + h` session's
close, h ∈ {5, 21}), not reusing the single-session `x_oc` N3 used. State this
explicitly in the receipt (`horizon_sessions`) because it is the one thing
that must NOT silently drift between E1 and E2 (see §2).

### 1.3 Models

**Mandatory control: LightGBM** (`learner/models.py`'s existing wrapper,
`import lightgbm as lgb`, NaN-native — do not impute). This is not "a control
among controls" here, it is Lane M item M5's standing rule: *"GBM is the
mandatory control for any net."* Any StockMixer-class result that does not
beat LightGBM on the SAME feature table and SAME splits is not reportable as
"the head works" — only as "the feature engineering may or may not carry
signal, independent of architecture."

**Candidate: StockMixer-class head.** Cite: Wang et al., *"StockMixer: A
Simple yet Strong MLP-Based Architecture for Stock Price Forecasting,"* AAAI
2024, DOI `10.1609/aaai.v38i8.28681`, code `github.com/SJTU-DMTai/StockMixer`
(official) — an MLP-mixer over `X ∈ R^(N×T×F)` (N = stocks, T = time steps, F
= features) doing indicator-mixing → time-mixing → stock-mixing, no
attention, no recurrence; picked in the roadmap's own research note
(`research_notes/2026-09-11/research_nn.md` §3: "cheap, strong, good 8GB
fit") over MASTER (same authors, AAAI 2024, cross-stock attention — heavier,
not laptop-first) and StockFormer (predictive-coding+RL hybrid, out of scope
for a `PRODUCT_EXPERIMENT`).

Laptop-feasible config for this repo's shape: E1's feature width after the
sparsity floor is expected ~150-250 columns (F), T = 1 (E1's table is
cross-sectional per date, not a sequence per name — **this is a deliberate
simplification of StockMixer's original T-dimension**: no lagged panel of
per-name feature histories is built for chunk 9, so T-mixing degenerates to a
no-op and only indicator-mixing (an MLP over F) + stock-mixing (an MLP over
the N names present that date, i.e. cross-sectional) are used. Name this
explicitly as `StockMixer_T1` in the receipt so nobody mistakes it for the
paper's full temporal variant). N = the tradable names on that date (variable,
~200-800 per the E1 panel's `median_names_per_date`). Two hidden layers, width
64-128, dropout 0.1-0.2, Adam, batch = one trading date (or a few dates
concatenated if a date has too few names for a stable batch-norm — floor at
`MIN_NAMES_BOOK = 20` from N3's constants, reused). This is a "cheapest thing
that was never tried" scope, matching N3's own framing — not a from-scratch
sequence encoder (which S45 already showed loses to TF-IDF for text; the
prior for architecture novelty on this panel's scale is not favorable).

### 1.4 Splits

Purged expanding walk-forward by month, **21-session embargo** (not N3's
5-session — the item's horizon is up to 21 sessions, so the embargo must at
least equal the horizon or the test month's early labels overlap train's
late-window features; use `max(EMBARGO_SESSIONS, horizon_sessions)`).
`MIN_TRAIN_MONTHS = 6` as N3 used. Never k-fold (`learner/dataset.py`'s own
`walk_forward_splits` docstring: "a random fold puts next quarter's news in
this quarter's training set").

### 1.5 The three controls (plus the GBM/StockMixer cross)

Same three-controls discipline N3 established, run for BOTH models (GBM and
StockMixer_T1) — six numbers, not three:
- **TF-IDF head**: same TF-IDF→SVD pipeline as N3 (`_tfidf_svd`, fit on TRAIN
  rows only per fold) applied to the raw headline text of the same cells
  (requires re-joining L2's source documents — do not regenerate typed events
  for this arm, use the text directly, exactly as N3 did).
- **Shuffled-event head**: the 117+ event columns globally permuted across
  `(symbol, entry_date)` cells, PIT price features held fixed (same logic as
  N3's `SHUFFLE`: labels/dates/universe unchanged, only the event-to-cell link
  cut). Seed pinned, `fixed_points` reported (N3's receipt convention).
  **This is the decisive control**: an arm that does not beat SHUFFLE has
  found the calendar and universe, not the events.
- **No-text head**: PIT price features only (same three columns N3's `NOTEXT`
  used) — measures how much of any margin is liquidity/momentum wearing an
  event-type's clothes.

### 1.6 Per-era reporting

2025-26 only (the E1 panel's full span, per its receipt: 2025-01-02 to
2026-09-08/11) — **say so explicitly in every receipt's `panel` block**, the
way N3 did (`"date_range": [...]"`). No claim of a second era or a
generalization beyond 2025-26 is permitted (invariants §9: "nothing
text-based gets a third era until the backfill reaches 2015").

### 1.7 Receipt schema (extends N3's, does not replace it)

```json
{
  "job": "E1_event_tabular_head",
  "licence": "PRODUCT_EXPERIMENT",
  "question": "...",
  "design": {
    "horizon_sessions": 5,
    "embargo_sessions": 21,
    "feature_family": "typed_event_onehot_x_direction + magnitude + confidence + counts_1_5_21 + recency + pit_price",
    "dropped_sparse_types": ["..."],
    "models": ["GBM", "StockMixer_T1"],
    "arms": ["EVENT", "TFIDF", "SHUFFLE", "NOTEXT"],
    "seed": 20260910
  },
  "panel": {"date_range": ["2025-01-02", "..."], "note": "2025-26 only"},
  "results": {"eras": {"ALL": {"arms": {"GBM": {...}, "StockMixer_T1": {...}}, "vs_controls": {...}}}},
  "holm_adjusted_p_all_era_ic": {},
  "family_max_p": null,
  "verdict": "FAILED_VARIANT | PRODUCT_PROMISING (CONDITIONAL)",
  "headline": "..."
}
```

**Verdict rule** (Holm within the family of `{GBM,StockMixer_T1} ×
{TFIDF,SHUFFLE,NOTEXT}` comparisons = 6 tests, same Holm procedure as N3's
`grade()`): `FAILED_VARIANT` if NO arm (either model) beats SHUFFLE at
Holm-adjusted p < 0.05. If some arm beats SHUFFLE but StockMixer_T1 does not
beat GBM on the identical table, the verdict is `FAILED_VARIANT` **for the
architecture question** but the feature table itself may still be
`PRODUCT_PROMISING (CONDITIONAL)` under GBM — report both lines, do not
collapse them into one verdict string (this is the M5 distinction: "a head
beats GBM and its three controls" per §12's gate literally requires clearing
GBM, not just SHUFFLE).

### 1.8 Known-answer tests

1. **Planted-effect recovery**: synthesize a panel where `event_type = "X"` at
   `direction=+1` deterministically adds +2% to `x_oc_h5` for the affected
   cell and nothing else carries signal (pure noise elsewhere). Both GBM and
   StockMixer_T1 must recover a positive, statistically distinguishable
   coefficient/split-importance on that event type's one-hot column, and both
   must beat SHUFFLE on this synthetic panel by a wide margin (sanity that the
   pipeline can find an effect it was given, before trusting it can't find one
   in the real panel that isn't there).
2. **Shuffled recovers nothing**: on the SAME synthetic panel, the SHUFFLE arm
   (event columns permuted) must show near-zero IC/margin — a test that fails
   if the permutation code accidentally shuffles rows in a way that preserves
   the residual association (e.g. permuting within groups that still align
   with the planted effect).
3. **No leakage across the embargo**: a unit test constructs a synthetic panel
   where a test-month cell's `recency` feature computed WITHOUT the embargo
   would encode information from inside the embargo window, and asserts the
   feature builder truncates at `entry_date - embargo - 1`, not `entry_date - 1`.

---

## 2. E2 — the frozen embedding at 5/10/21 sessions

### 2.1 Scope discipline

`scripts/night_n3_frozen_embedding_head.py` becomes parameterised on
`horizon_sessions ∈ {5, 10, 21}` (N3 today is effectively horizon=1, same-
session open-to-close). **Nothing else changes**: same encoder
(`BAAI/bge-small-en-v1.5`, pinned revision
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`), same ridge head, same TF-IDF/
SHUFFLE/NOTEXT controls, same cost model (`night_g3_evolve_v2.COST_BPS`
imported, never retyped), same PIT assertion (`_assert_pit`). The label
changes from `x_oc` (single-session) to a cumulative `x_oc_h{5,10,21}`
(entry-open to entry+h-close, minus SPY over the same window) and the embargo
becomes `max(5, horizon_sessions)`.

**Enforcement test** (explicitly required by the roadmap item's own wording,
"a test diffs the config against N3's receipt and asserts only `horizon`
differs"): a test loads N3's most recent receipt
(`backend/data/optimus/night_factory_2026-09-11/N3_frozen_embedding_head_run01.json`)
and the new E2 script's `design` block, and asserts every key EXCEPT
`horizon_sessions`, `embargo_sessions`, and the label name matches byte-for-
byte (`MODEL_ID`, `MODEL_REVISION`, `EMBED_DIM`, `MAX_TOKENS`, `ALPHAS`,
`SVD_COMPONENTS`, `TFIDF_MAX_FEATURES`, `SEED`, `COST_BPS` source, `DECILE`,
`MIN_NAMES_BOOK`). This is a config-diff test, not a numerical-outcome test —
it fails loudly the moment someone "improves" the encoder or the head while
touching this file, which is exactly the silent-scope-creep this roadmap item
exists to prevent.

### 2.2 GPU-contention rule (the 130s vs 40,059s lesson)

The two existing N3 receipts are the evidence: the 2026-09-10 run embedded
162,548 texts in **129.7s** (1,252.9 texts/s, GPU free); the 2026-09-11 run
embedded 163,284 texts in **40,059.4s** (4.1 texts/s — an 11-hour run) because
it contended with `llama-server`. E2 (and any re-embedding) MUST:
1. Check `nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits`
   before starting the encode loop.
2. **Refuse to embed** if any process other than the current one holds more
   than 3 GB of VRAM (a threshold chosen to allow the encoder's own ~1-2 GB
   fp16 footprint headroom while catching `llama-server`'s multi-GB
   residency), printing which PID/process holds it (cross-reference
   `backend/services/llama_server.py`'s `vram()` / `pid_on_port` helpers
   rather than re-parsing `nvidia-smi` text a second way) and exit non-zero
   with a receipt `status: "REFUSED_GPU_CONTENTION"` naming the contending
   process.
3. This check runs ONCE at start and is NOT a polling loop mid-encode (a job
   that starts clean and is later joined by a contending process should
   finish, not abort mid-checkpoint — checkpointing already exists via
   `Checkpoint`/`atomic_write_json` for that case).

### 2.3 Embedding cache: reuse, not rebuild

Embeddings are **horizon-independent** (the encoder reads only the day's
headline text; the horizon changes only the label/window). N3 already caches
per-corpus at `backend/data/optimus/text_return_panel/emb_bge_small_en_v1_5/
n{len(texts)}_{digest[:12]}/`, keyed by `_sha1(f"{len(texts)}|" +
_sha1("\x00".join(texts[::997])))` (a coarse subsample digest, not a full
corpus hash — note this in the receipt, it is a known weak point: two corpora
of identical length sampled identically every 997th text collide, though this
is astronomically unlikely at this corpus's scale and the `Checkpoint` class's
own config-drift check on `n_texts` + `model_id` + `revision` + `max_tokens`
is the actual safety net, not the digest).

**Invalidation key for E2**: `(MODEL_ID, MODEL_REVISION, MAX_TOKENS,
corpus_digest)` — identical to N3's existing cache key. E2 for horizon=5, 10,
and 21 must all resolve to the SAME cache directory (same corpus → same
embeddings) and skip re-embedding entirely after the first horizon runs; only
the walk-forward/label/book stage differs per horizon. A test asserts that
running E2 at horizon=10 after horizon=5 has already populated the cache
performs **zero** calls into `embed_corpus`'s chunk-encoding branch (mock
`AutoModel.from_pretrained` and assert it is never invoked on the second
call).

---

## 3. E3 — adaptive conformal intervals

### 3.1 The exact update (ACI)

Gibbs & Candès, *"Adaptive Conformal Inference Under Distribution Shift,"*
NeurIPS 2021 (proceedings.neurips.cc/paper/2021/hash/
0d441de75945e5acbc865406fc9a2559-Abstract.html). The update, applied once per
realized outcome at each date block t:

```
err_t = 1[y_t not in C_t(α_t)]        # miscoverage indicator for the realized outcome
α_{t+1} = α_t + γ (α - err_t)
```

where `α` is the target miscoverage (e.g. 0.10 for 90% intervals), `γ` is a
step size trading off adaptability vs. volatility of `α_t` (Gibbs & Candès'
own framing), and `C_t(α_t)` is the prediction interval built from the head's
residual distribution using the CURRENT `α_t` (clipped to `[0.001, 0.999]` to
keep the quantile lookup well-defined — this clip is an implementation
necessity Gibbs & Candès' paper does not need to state because it works in
continuous idealization; document the clip in the receipt as a deviation).

### 3.2 The non-exchangeable weighted variant

Barber, Candès, Ramdas, Tibshirani, *"Conformal Prediction Beyond
Exchangeability,"* Annals of Statistics 51(2), 816-845, 2023 (DOI
`10.1214/23-AOS2276`; arXiv:2202.13415). Core idea for E3: replace the
uniform-weight empirical quantile of past nonconformity scores with a
recency-weighted quantile, weights `w_i = ρ^{(t-i)}` for a decay `ρ ∈ (0,1)`
(a single tuning knob, swept e.g. `{0.90, 0.95, 0.99, 1.0}` where `ρ=1.0`
recovers the unweighted/exchangeable case — the naive-coverage control in
§3.4 IS this `ρ=1.0` setting, so the sweep already contains its own control
point, no separate code path needed). Applied on top of the same residual
pool the plain-ACI interval draws from; the two mechanisms (ACI's α-tracking
and the recency weighting) are used TOGETHER, not as alternatives — ACI
adapts the target miscoverage level while the weighting adapts which past
residuals count toward the current quantile.

### 3.3 Which head gets an interval

Applied to whichever of E1/E2's arms has a **positive control-adjusted IC**
(i.e. `EMBED_minus_SHUFFLE` or `EVENT_minus_SHUFFLE` mean > 0 at the loosest
reasonable bar — reuse the verdict logic's `beats_shuffle` boolean from N3
`verdict()`/E1 §1.7, do not invent a second threshold). If NEITHER E1 nor E2
clears that bar (the likely outcome given N3's two `FAILED_VARIANT`s), E3
runs on the **GBM control arm itself** (E1's `NOTEXT` or the full-feature GBM,
whichever the receipt shows the more defensible IC for) so the machinery is
exercised and receipted even under a chunk-9 global negative — a refusal to
report an interval because "nothing beat shuffle" would be the CANON §6
grep-shaped-guard failure mode (a check that cannot go green is broken); E3's
own verdict can and should say "interval mechanics validated on a control
arm; no head has a signal worth intervalizing yet."

### 3.4 Receipt headline: realised coverage per vol regime

Terciles of trailing **21-session SPY volatility** (reuse
`learner.growth_lab._trailing_vol`, the repo's own existing helper, do not
reimplement) computed at each test date, splitting the walk-forward's test
dates into LOW/MID/HIGH vol terciles. For each tercile × {naive (fixed-α
conformal), ACI, ACI+non-exchangeable-weighted}, report:
- `nominal_coverage` (1 − α, or 1 − α_t averaged over the tercile for ACI)
- `realised_coverage` (fraction of test dates where the true outcome fell
  inside the interval)
- `mean_interval_width`
- `n_date_blocks`

This table (3 methods × 3 vol terciles = 9 cells + ALL) IS the receipt's
headline, per the roadmap's own phrasing ("the realised coverage per vol
regime as the receipt's headline"), not a footnote below a point estimate.

### 3.5 Naive-coverage control

Plain split conformal with a FIXED α (no ACI update, no recency weighting) —
this is the method `docs/research_notes/2026-09-11/research_nn.md` §4 already
flags by its known failure mode ("conformal coverage degrades in high-vol
regimes for daily stock returns (~90%→50%) per search summary"). The naive
arm's own coverage collapse in the HIGH-vol tercile is the demonstration ACI
is answering, not an incidental baseline — report it prominently.

### 3.6 Board rendering

Interval (`[lo, hi]` on the return scale, or on price if the board already
shows price targets — match O11's 52-week-target page convention rather than
inventing a second display unit) plus the realised-coverage-per-regime table,
with the currently-active vol tercile highlighted (today's trailing-21-session
SPY vol tells the viewer which coverage number is live). No point estimate is
shown without its interval, matching invariant 28 ("a method with no backtest
of its own past errors prints CANNOT DETERMINE ... it does not print a bare
point").

### 3.7 Known-answer test

Synthetic AR(1)-with-noise series with a **planted regime shift** at a known
index (variance triples, or the mean residual shifts, at `t = 500` of 1000).
Assert:
1. Plain conformal's realised coverage in the post-shift window (`t >
   500 + burn_in`) falls measurably below its nominal target (e.g. from ~90%
   nominal to < 75% realised in a window right after the shift).
2. ACI's realised coverage in a window `k` steps after the shift recovers to
   within a stated tolerance of nominal (e.g. within 5 points) — sweep `k`
   and report the smallest `k` at which recovery holds for the chosen `γ`,
   rather than hardcoding one `k` and hoping.
3. The non-exchangeable weighted variant recovers at least as fast as plain
   ACI (weights should help, not hurt, on a series where recent history is
   more informative post-shift) — report the comparison, do not silently
   assume it and skip the check.

---

## 4. E4 — ADWIN-gated refit

### 4.1 Method

Bifet & Gavaldà, *"Learning from Time-Changing Data with Adaptive
Windowing,"* Proc. 2007 SIAM International Conference on Data Mining, 443-448
— maintains a variable-size window of the error stream and cuts it (signals
drift) whenever two sub-windows' means differ by more than a bound derived
from a Hoeffding-style tail inequality, giving false-positive/false-negative
rate guarantees without a hand-picked window length.

### 4.2 Library choice

**`river`** (PyPI: `river`, BSD-3-Clause license — confirmed via PyPI/GitHub
`online-ml/river`, a permissive license fully compatible with this repo's
existing stack) ships `river.drift.ADWIN` directly. **Not currently in
`backend/requirements.txt`** (confirmed absent by grep) — add it there rather
than vendoring. `river` requires Python ≥3.11; this repo runs 3.12.10
(confirmed), so no interpreter conflict. If `river`'s transitive dependency
footprint is judged too heavy for a one-class need (check at implementation
time — `river` is a full online-ML framework, ADWIN is one detector in it), a
**40-line implementation** is the fallback: maintain a list of `(bucket_mean,
bucket_count)` pairs merging same-size adjacent buckets (the standard ADWIN2
bucket-compression trick, described in the paper's §3 and reproduced in
`github.com/monochromegane/adwin`'s Go implementation as a compact reference
for the algorithm's shape, not for its license) and cut when any split of the
buckets breaches the Hoeffding bound. **Decision rule for which path to take**:
default to `river` unless its install is refused by CI's dependency-audit step
(some corp/offline CI environments block new heavy deps); the fallback exists
so E4 is never BLOCKED on a packaging decision.

### 4.3 The comparison

On whichever head E1/E2 selected for E3 (same head, so E3 and E4 are graded
on a shared object, not two different arbitrary choices): maintain the head's
**rolling absolute error** (or squared error) stream across the walk-forward's
test date blocks. Two refit policies, graded on the SAME splits:
- **ADWIN-gated**: refit the head (re-run `_fit_ridge`/GBM/StockMixer training)
  only when ADWIN signals a change point on the error stream since the last
  refit.
- **Fixed-window monthly**: refit every month regardless (this is what N3/E1/
  E2 already do by construction — the existing walk-forward IS the fixed-
  window control, so E4 does not need a separate fixed-window run, it reuses
  E1/E2's own daily/fold output as the control arm).

Receipt reports: number of refits triggered by ADWIN vs. the fixed monthly
count, wall-clock/compute saved or spent, and IC/net performance of the
ADWIN-gated arm vs. the fixed-window arm on IDENTICAL test dates (a date
where ADWIN chose not to refit uses the STALE model's prediction — this must
be logged per date so a reviewer can see which predictions came from a stale
vs. fresh model).

### 4.4 Known-answer test

Synthetic error stream: constant low error for 200 steps, then a step
increase in error variance/mean for the next 200 (a manufactured "concept
drift"). Assert ADWIN fires within a bounded number of steps after the
change point (per the paper's own false-negative-rate guarantee, not an
arbitrary "should be fast") and does NOT fire spuriously in the stable
segment beyond ADWIN's stated false-positive rate at the chosen confidence
parameter.

---

## 5. L4 — Qwen3-30B-A3B as a new arm

### 5.1 Model identity (verified live via Hugging Face Hub, 2026-09-12)

- `Qwen/Qwen3-30B-A3B-Instruct-2507` — 30.5B params, ~3.3B active (MoE),
  **license apache-2.0** (confirmed on the Hub page). This is the **plain
  Instruct build**, per the roadmap's explicit instruction ("plain Instruct
  first, abliterated only if refusals > 0") — NOT the base
  `Qwen/Qwen3-30B-A3B` (also apache-2.0) and NOT an abliterated/uncensored
  community fine-tune (the HANDOFF doc's own caution: *"Uncensored" is
  probably wrong for this job. Abliteration costs benchmark [performance]*).
- GGUF quant: `bartowski/Qwen_Qwen3-30B-A3B-Instruct-2507-GGUF` (Q4_K_M, the
  same quant level `Qwen2.5-7B-Instruct-Q4_K_M.gguf` uses today, for a fair
  apples-to-apples file-size/VRAM comparison). Download this specific file,
  compute its sha256 at download time, and record it in the receipt exactly
  as `TRIAL-R2-monthly-news-digest-read.md` records
  `Qwen2.5-7B-Instruct-Q4_K_M.gguf`'s (`65b8fcd9...`) — **the file's sha256
  IS the frozen identity**, per that trial's own rule ("A model swap is a NEW
  ARM ... R2's pre-registration freezes the model file's sha256 for precisely
  this reason").

### 5.2 Idle measurement protocol

The HANDOFF_2026-09-10 measurements (17.28 GB file, `--n-cpu-moe 48` → 1,854
MiB VRAM, 19.8 tok/s generation, 5.6 tok/s prompt eval) were taken **while
PyInstaller saturated all 20 CPU cores** — the doc calls this a "lower bound"
and names the next session's first task as re-measuring idle. L4 does that
measurement, not a repeat of the contended one:

1. Confirm machine is idle: no PyInstaller build, no night-factory job, no
   other `llama-server`/`python` process holding CPU or the 5060's VRAM
   (reuse `backend/services/llama_server.py`'s `vram()`/`pid_on_port` to
   check the GPU side; `Get-Process | Sort CPU -Descending | Select -First 5`
   or equivalent to eyeball CPU).
2. Sweep `--n-cpu-moe ∈ {48, 40, 32, 24}` (the roadmap's own stated sweep,
   descending — more MoE layers kept on GPU as the number falls) via
   `AEGIS_LLAMA_N_CPU_MOE`, restarting `llama-server` cleanly between each
   value (`stop()` then `start()`, PID-owned per the standing rule — never
   `taskkill /IM`).
3. At each setting, measure: VRAM used (`vram()`), load time, **prompt-eval
   tok/s** (the number the roadmap flags as decisive: "the prompt-eval rate is
   the number that decides whether it can read a digest at all" — R2's
   digests are a full month of anonymised news per name, i.e. long prompts,
   so generation speed is nearly irrelevant next to prompt-eval speed) and
   generation tok/s, on a fixed benchmark prompt (reuse R2's own frozen
   `user_prompt` — sha256 `0189e97e...` per `TRIAL-R2-monthly-news-digest-
   read.md` §"the model" table — so the L4 measurement is directly comparable
   to R2's numbers, not a differently-shaped prompt).
4. Stop sweeping once VRAM is "near full" (the roadmap's own stop condition) —
   defined operationally as within 500 MiB of the 5060's usable budget minus
   the OS/desktop floor already characterized in the HANDOFF doc (~1,285 MiB
   floor implied by 8,151 − 6,866 MiB reported there).
5. Receipt: a table of `{n_cpu_moe: {vram_mib, load_s, prompt_eval_tok_s,
   generation_tok_s}}`, plus the explicit **idle vs. HANDOFF-contended**
   comparison line (5.6 tok/s contended → X tok/s idle) so nobody re-derives
   the "was it just contention" question again.

### 5.3 Refusal-rate test

Run the plain Qwen3-30B-A3B-Instruct-2507 build over **R2's frozen prompts**
(system prompt sha256 `51ebe4fe...`, user prompt template sha256 `0189e97e...`
— reuse verbatim, do not paraphrase) on **200 digests** drawn from the same
E1/R2 corpus construction R2 uses (PANEL-B's per-name-month digests, or a
200-digest subsample if PANEL-B's full run is smaller than 200 — state which).
A "refusal" is defined exactly as `event_intel.py`'s/`llm_language.py`'s
existing conventions define a failed/refused LLM read (non-JSON reply, the
model declining to answer, or `llm_language.refuse()` firing on a >10%
non-Latin-script reply — the language pin applies here too, this is a
DeepSeek-only rule's local-model analogue and should be checked even though
Qwen3 is not the "sole provisioned provider": a local model that code-switches
or refuses is still a bad reader). Report `refusals / 200` and the refusal
TYPE breakdown (declined vs. malformed-JSON vs. language-drift). **Decision
rule**: if refusal rate is 0 (or negligibly low, e.g. ≤1%, matched against
Qwen2.5-7B's own baseline refusal rate on the same 200 prompts as the
comparison point — do not compare to an absolute zero if the incumbent model
itself has a nonzero rate), proceed with plain Instruct; only if refusals
exceed the incumbent's rate materially does an abliterated variant become a
NEW arm to consider (`R2-Qwen3-abliterated`), never a silent swap-in.

### 5.4 Registering `R2-Qwen3`

New arm beside R2 in the trial registry, same family (the monthly news-digest
read), same PANEL-B, same **shuffled control** (the identical control R2
already runs — do not build a second shuffle scheme), same **112 blocks**
PANEL-A/PANEL-B's block count references (`TRIAL-R2-monthly-news-digest-
read.md` §2: PANEL-A is 112 monthly blocks, PANEL-B is 19 — confirm which
block count R2-Qwen3 actually runs against at implementation time and state
it; do not silently assume 112 when PANEL-B is smaller — reproduce §3's exact
`read_minus_shuffled_control` metric definition, Newey-West lag-2 t, realised
turnover costed at `night_factory_jobs.COST_BPS`/25 bps). Pre-register this
BEFORE the first Qwen3 digest is read, per the same corpse-check discipline
`TRIAL-R2-...md` itself models (§0: "the commitment therefore precedes the
data").

### 5.5 Decision rule

Adopt `R2-Qwen3` over `R2` (Qwen2.5-7B) **only if**:
1. `R2-Qwen3`'s `read_minus_shuffled_control` (its OWN control-adjusted
   number, not R2's) beats R2's own control-adjusted number on the SAME
   blocks, with the same significance bar R2 itself uses; AND
2. `R2-Qwen3`'s **Lookahead Propensity** (lane X item L3) is **not worse**
   than R2's — a bigger/differently-trained model reading the same
   anonymised digest could have a higher propensity to have memorized
   pre-cutoff facts, and a win on (1) driven by (2) getting worse is not a
   win.
Both conditions are graded in the SAME receipt; a pass on (1) alone is
reported as `CONDITIONAL_ON_LAP`, not `ADOPTED`.

### 5.6 Wall-time honesty

State plainly: at 19.8 tok/s generation (idle-measured number from §5.2
supersedes this if it differs) vs. Qwen2.5-7B's 41.4 tok/s, and at whatever
idle prompt-eval tok/s §5.2 measures vs. the 5.6 tok/s contended figure, the
wall time for 112 (or 19, per §5.4's actual count) digests is
`digests × (prompt_tokens/prompt_eval_tok_s + completion_tokens/generation_tok_s)`.
Compute this number with R2's own actual average prompt/completion token
counts (available from R2's existing run logs — do not guess token counts)
and print BOTH the Qwen2.5-7B wall time and the Qwen3 wall time side by side
in the receipt, so "is this arm even practical to run nightly" is answered by
a number, not a vibe.

---

## 6. The stage contract (Qanat's join, §11 — scoped honestly)

### 6.1 What a typed stage contract would enforce

Per §11's own framing (Qanat, MIT, `fidetolabs/qanat`): **raw is source-only**
(a raw-stage table is never itself a tradable weight); **data flows forward
only** (no stage reads a table produced by a LATER stage — the structural
leakage-prevention Qanat gets "for free" from its DAG); **one weights stage
per book** (a book's final position weights come from exactly one producer,
not several merged ad hoc); **no book reads another's weights** (book B's
sizing cannot depend on book A's current positions — prevents accidental
shared-state coupling that would make two "independent" paper books secretly
correlated by construction rather than by the market); **every table has a
producer** (no orphan artefact with an unknown origin — this is
`signal_reachability.py`'s own rule, "give every new module a caller,"
generalized from modules to data artefacts).

### 6.2 What already enforces (most of) this

`backend/strategy/contract.py`'s `Strategy` dataclass is already an ordered
pipeline of typed stages: `Universe` (which names could have been bought —
the denominator, i.e. Qanat's "raw is source-only" analogue) → `Signal` →
`Construction` → `HoldRule`/`Sizing` → `CostModel` → `Objective`/`Benchmark`.
Each stage is its own frozen dataclass with `__post_init__` validation
(`Signal.__post_init__`, `Construction.__post_init__`, etc.), and
`Strategy.fingerprint()` hashes the whole pipeline — so "one weights stage per
book" is already true by construction (`backend/services/paper_books.py`'s
`PaperBook` holds exactly one `Strategy`, `book_id_for(strategy)` derives the
book's identity FROM that one strategy, not from a merge of several).
`PaperBook`'s NAV/positions write path is CANON-§5-sacred (per
`lane-integrity-check`), which already gives "no book reads another's
weights" teeth for the live paper layer specifically. `CostModel.round_trip_bps`
being computed via a delegated method ("DELEGATED, not re-implemented," per
its own docstring) is the repo's existing version of "every table has a
producer" for the cost dimension.

**What is NOT yet enforced**: the FARM side (`portfolio_farm.Policy`,
`scripts.portfolio_farm_run`, the hundreds-of-strategies backtest sweep) and
the ARM/LANE side (paper books) are, per the roadmap's own diagnosis, **two
separate stacks** ("today two stacks") — a farm candidate's promotion to a
paper book re-implements its weights logic rather than the SAME `Strategy`
object flowing from farm evaluation straight into `PaperBook.create()`. There
is no cross-stack type that says "this farm weights table is THE producer for
this book," so a promotion could (and per the roadmap's framing, historically
has had room to) silently diverge between what was backtested and what is
traded.

### 6.3 The smallest first step

Do NOT attempt the full farm↔book unification in chunk 9 (§11 itself scopes
this "big," gated on lane B's `PaperBook` landing first, which chunk 9 is
downstream of per the chunk table). The smallest test-backed step:

1. Add a `stage: Literal["raw","features","signal","weights","paper"]` field
   to every receipt-writing job's output schema touched by this chunk (E1,
   E2, E3, E4, L4's `R2-Qwen3` receipt) — a cheap, additive field, not a
   schema migration of anything existing.
2. A single new test,
   `backend/tests/test_stage_contract_no_forward_read.py`, that:
   - collects every receipt JSON under `backend/data/optimus/night_factory_*/`
     that carries a `stage` field and every `inputs`/`reads_from`/`panel.path`
     reference inside it,
   - builds a stage-order map (`raw < features < signal < weights < paper`),
   - asserts no receipt's declared inputs point at a path whose OWN receipt
     (if one exists for that path) declares a stage **later** than the
     reading receipt's own stage.
   This is deliberately narrow — it catches the "E2 accidentally reads a
   paper-book's realized fill price as a feature" class of bug, not a general
   DAG verifier — and it is a refusal-shaped test per the standing rule (if no
   receipt in the corpus carries `stage` yet, the test reports `CANNOT
   DETERMINE`, not a false green, exactly as `monday_gate_check`'s
   `fingerprint_scheme` lesson requires).
3. Do not add a `stage` field to `Strategy`/`PaperBook` themselves this
   chunk — that IS the "big" unification, and forcing it in now would be new
   roadmap-scale work the roadmap's own "new guards are no longer roadmap
   work by default" rule advises against absent an actual failure it
   prevents. The receipt-level field is the cheap, tamper-evident down
   payment; the dataclass-level unification is future work explicitly
   deferred to "after lane B."

---

## 7. Build order, receipts, GPU scheduling

### 7.1 Build order (cheapest test first)

1. **E2 horizon parameterisation + config-diff test** (§2.1) — cheapest: no
   new feature engineering, no new model, reuses N3's embeddings from cache
   (§2.3) if the corpus is unchanged since 2026-09-11, so the FIRST run costs
   ~0 GPU seconds and only the ridge-head walk-forward at three horizons runs.
   Receipt: `E2_frozen_embedding_head_h{5,10,21}_run01.json` (one per
   horizon, same shape as N3's).
2. **GPU-contention refusal check** (§2.2) as a standalone unit (mock
   `nvidia-smi`/`vram()` outputs) BEFORE wiring it into E2's main loop — this
   is the piece most likely to have an untestable failure mode (a real GPU
   query in CI) so it gets its own fast, mocked test first.
3. **E4 ADWIN mechanics + known-answer test** (§4.4) on synthetic data only —
   no dependency on E1/E2's real panel results yet, so it can be built and
   verified in isolation before being wired to a real head.
4. **E1 feature table + known-answer tests** (§1.8) on synthetic data, THEN
   the real walk-forward against LightGBM + StockMixer_T1 + three controls.
   Receipt: `E1_event_tabular_head_h{5,21}_run01.json`.
5. **E3 ACI mechanics + known-answer test** (§3.7) on synthetic data, THEN
   wired to whichever real head (E1/E2/GBM-control) qualifies per §3.3.
   Receipt: `E3_adaptive_conformal_run01.json`.
6. **E4 wired to the real head** chosen in step 5, graded against the fixed-
   window control already implicit in E1/E2's own walk-forward output.
   Receipt: `E4_adwin_gated_refit_run01.json`.
7. **L4 idle measurement sweep** (§5.2) — can run in parallel with 1-6 (it
   needs the machine idle, not any other chunk-9 artefact) but MUST be
   scheduled so it does NOT overlap with E1/E2's GPU-bound steps (see §7.3).
8. **L4 refusal-rate test + R2-Qwen3 registration + run** (§5.3-5.5) — after
   step 7 gives a usable `--n-cpu-moe` setting.
9. **Stage-contract receipt field + the one narrow test** (§6.3) — last,
   cheap, and touches every receipt schema written by 1-8, so it is easiest
   to add once their shapes are settled rather than mid-flight.

### 7.2 Receipts (summary table)

| item | receipt path | grading artefact |
|---|---|---|
| E1 | `night_factory_<date>/E1_event_tabular_head_h{5,21}_run01.json` | `..._daily.csv` |
| E2 | `night_factory_<date>/E2_frozen_embedding_head_h{5,10,21}_run01.json` | `..._daily.csv` |
| E3 | `night_factory_<date>/E3_adaptive_conformal_run01.json` | per-vol-tercile coverage table (§3.4) inline |
| E4 | `night_factory_<date>/E4_adwin_gated_refit_run01.json` | refit-timeline log inline |
| L4 idle sweep | `night_factory_<date>/L4_qwen3_idle_measurement_run01.json` | `{n_cpu_moe: {...}}` table inline |
| L4 refusal test | `night_factory_<date>/L4_qwen3_refusal_rate_run01.json` | per-digest refusal log |
| R2-Qwen3 | `night_factory_<date>/R2_Qwen3_monthly_llm_run01.json` | same shape as `R2_widened_panelB`'s receipt |
| stage contract | (test only, no receipt) | `backend/tests/test_stage_contract_no_forward_read.py` |

Every job above registers in `scripts/night_factory_jobs.py`'s `JOBS` dict via
the existing `_lazy(module, attr)` pattern (one line each, matching N3's own
registration: `"E1_event_tabular_head": _lazy("scripts.night_e1_event_tabular_head", "E1_event_tabular_head")`),
so the night factory's existing checkpoint/resume/receipt-writing
infrastructure (`Checkpoint`, `atomic_write_json`) is inherited rather than
reimplemented — this is the same lesson `night_checkpoint.py` and
`night_n3_frozen_embedding_head.py`'s own docstrings encode (a job that writes
incrementally survives a crash; one that holds results in memory and writes
once at the end, like PANEL-A's original R2 run, does not).

### 7.3 GPU scheduling rule

**Never embed while `llama-server` holds the card** — this is not a new rule,
it is the 2026-09-11 N3 run's own lesson (129.7s idle vs. 40,059.4s
contended, an ~309× slowdown) turned into a checked precondition (§2.2). The
night factory's own GPU line (whatever job-ordering mechanism currently
serializes GPU-bound night jobs — confirm at implementation time whether
`night_factory.py`/`night_factory_jobs.py` already has a GPU-affinity or
mutex concept, or whether jobs today simply run sequentially and the
contention only arises from a manually-started `llama-server` left running
across a night run) must treat E2's embedding step and L4's Qwen3
measurement/inference steps as mutually exclusive with each other AND with
any embedding job — both want the GPU, and per §5.2's own idle-measurement
requirement, Qwen3 measurement explicitly needs the machine otherwise idle,
which is a strictly stronger constraint than "just don't run two GPU jobs at
once." The cheapest enforcement: L4's idle sweep script performs the SAME
`nvidia-smi`/`vram()` contention check as E2 (§2.2) before starting, reusing
one shared helper (do not write the check twice) rather than each script
growing its own ad hoc version — this is also the "every guard belongs on the
DeepSeek path" lesson's general form: one guard, every caller uses it, not
inline heuristics duplicated per script.
