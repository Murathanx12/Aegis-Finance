# Lane X spec — the LLM inside the backtest (chunk 7 build spec)

Source: roadmap `docs/ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`
§10 (Lane X reopened) + §12 chunk 7: `X1-X4 LLM-in-backtest workarounds under P1-P6 +
L3 Lookahead Propensity + the anonymisation gap`; gate to chunk 8 = "each receipt carries
LAP and the flip test." Licence throughout: `PRODUCT_EXPERIMENT` (roadmap header). Nothing
here promotes anything; MUST NOT REGRESS #24: "An LLM read over history carries P1-P6, its
LAP score and its anonymisation gap, or it is not quoted."

---

## 0. What already exists (read, not re-derived)

- **`scripts/night_r2_monthly_llm.py`** (901 lines) — the only live X-shaped lane. Four
  arms per run, tagged in the answers jsonl: `read_MASKED` (the real mechanism),
  `control_SHUFFLED` (digest drawn from a random other month, same cells — rng seed
  `20260909`), `canary_REAL_names` / `canary_MASKED` (the AMNESIA canary, same subset of
  cells read with real company names vs masked names). PANEL-B run (`--panel widened`)
  as of this writing has run the canary (300+300 cells) and `read_MASKED` (474 cells so
  far, growing) but **`control_SHUFFLED` has not yet been asked of the model** — the
  answers file `night_factory_2026-09-10/R2_widened_panelB_answers.jsonl` (1,074 rows as
  of 2026-09-12, growing nightly; roadmap's "600" is stale) carries only
  `{tag, name, month, dir, conf, fwd}` per row for the tags that have run.
  `R2_widened_panelB_run01.json` was written BEFORE any model call (`verdict:
  "PENDING_MODEL"` — `llama-server` was not listening) and freezes: 18,501 cells / 19
  monthly blocks, mask hit rate 0.4191, power declaration (n_required 18, n_available 19,
  smallest resolvable effect 1.2pp/month = 14.4%/yr net, NW-lag-2, per canon §58/§64).
  `--regrade` re-derives net at any cost rate from the persisted answers without the model.
- **`docs/TRIALS/TRIAL-R2-monthly-news-digest-read.md`** freezes: system prompt sha256
  `51ebe4fe…`, user prompt sha256 `0189e97e…`, digest-spec sha256 `0e169…`, model file
  `Qwen2.5-7B-Instruct-Q4_K_M.gguf` (4,683,074,240 bytes) sha256 `65b8fcd9…`, server
  `llama-server 0.3.0-dev build 10645`, decoding temp 0.0 / max_tokens 48, digest
  construction (≥3 docs/cell, ≤8 docs, ≤320 chars/doc, ascending `published_utc` then
  `uid`, head(8)), masking via `r7_news_representation.mask_company`, costs 25bps/side on
  realised turnover, PANEL-A (2015-2024, 135 names) vs PANEL-B (E1, 2025-01..2026-07, up
  to 3,031 symbols) — PANEL-B decides, PANEL-A is reported never deciding. Decision rule:
  adopt at net ≥14.4%/yr AND NW t≥2.0 AND AMNESIA gap ≤+0.02 AND positive both years;
  reject at net ≤0 OR t<1.0 OR AMNESIA gap >+0.05 OR control beats arm gross.
  **A model swap is a NEW ARM** — a 14B, a different quantisation, a different server
  build all re-register.
- **`backend/data/optimus/night_factory_2026-09-08/C1_counterfactual_news.jsonl`** — now
  6,935 rows (grew past the roadmap's stated 1,962; 6,676 `OK`, 180 `REFUSED_SCHEMA`, 79
  `REFUSED_UNPARSEABLE`), one row per real headline: `{uid, effective_at, symbols, source,
  backend, utc, latency_s, tokens_in, tokens_out, status, anon, event_type, direction,
  magnitude, counterfactuals:[{kind, changed, text, direction}]}`. `counterfactuals` is
  1-3 entries per row, kinds `sign_flip` (6,674), `escalation` (6,026), `actor_timing`
  (6,602) — not every row has all three (schema/parse refusals reduce the count per row).
  `anon` is already the masked/anonymised real headline; each counterfactual carries its
  own rewritten `text` (also anonymised, since it is a transform of `anon`) and a
  `direction` label the generating model assigned to the counterfactual itself.
- **`docs/research_notes/2026-09-11/spec_events_and_calibration.md`** — §1 freezes 39
  event types + `no_event` (snake_case ids, `direction∈{-1,0,1}` always relative to the
  named scope never the market, `magnitude_bucket` ∈{NEGLIGIBLE,SMALL,MODERATE,LARGE,
  EXTREME} on expected |abnormal return| over 1-2 sessions — LARGE floor is 5%
  ABSOLUTE per invariant 14, not scaled by market cap — `confidence`∈[0,1] as a
  probability the (event_type,direction) pair is the correct reading, NOT the same axis
  as `extraction.tier`). §2 freezes the JSON-schema (draft-07) output row:
  `{event_type, direction, magnitude_bucket, confidence, evidence_span}`, system+user
  prompt text, golden set (20 rows) + 3 adversarial rows for regression. §3 has
  `backend/services/calibration.py::brier_decomposition` (Murphy 1973: BS = reliability −
  resolution + uncertainty) already live — this is the ECE/Brier utility X-lane receipts
  call, not something to reimplement. §4 the `PredictionRecord` 1.4.0 schema ALREADY
  DECLARES `LAP_score`, `anonymization_gap`, `era_tag`, `licence`,
  `n_effective_trials_at_time`, `control_twin_id`/`control_construction`,
  `costs_charged`/`cost_rate_bps`, `calibration_bucket` — all optional/additive, default
  `None`, bumping `SCHEMA_VERSION` `1.3.0`→`1.4.0`. Governing rule already written into
  that spec (invariant 21, quoted there): *"a number from an LLM read over dates before
  that model's cutoff carries its LAP result or is not quoted."* X-lane chunk 7 build =
  make that rule enforced in code, not merely declared in the schema.
- **`docs/research_notes/2026-09-11/research_learning_loop.md` §3** — the paper survey
  behind L3/anonymisation-gap (arXiv:2605.16895 Alpha Illusion P1-P6; arXiv:2512.23847
  Gao-Jiang-Yan LAP; arXiv:2511.15364 anonymisation gap; arXiv:2502.21206 ChronoBERT/
  ChronoGPT; arXiv:2601.13770 Look-Ahead-Bench, tests DeepSeek 3.2 directly: standard
  LLMs incl. DeepSeek show lookahead-driven alpha decay, PIT "Pitinf" models do not and
  improve with scale). Six-item "accepted control set" synthesised there is the checklist
  X-lane receipts are built against.
- **`backend/services/free_inference.py::complete(backend="local_gguf", ...)`** — the ONE
  local call path (`Backend` registry, price table `LLM_PRICE_PER_MTOK` with zeros for
  free models, `FreeReply(backend, model, text, latency_s, tokens_in, tokens_out,
  cost_usd, cost_class)`). Raises `ProviderRefusal` / `LanguageRefused` rather than
  returning junk; every call — refused or not — is recorded via `_tel.record_call`
  (denominator for a refusal RATE). Language pin/refusal (`backend/services/
  llm_language.py`: `LANGUAGE_PIN = " Respond in English only."`, `NON_LATIN_BAR`,
  `refuse()`/`guard()`) is applied centrally inside the transport, not per call site —
  X-lane scripts must NOT re-implement it, must go through `free_inference.complete` or
  `model_provider`, same as `night_r2_monthly_llm.py` already does.
- **`NEGATIVE_RESULTS.md` §19** — "LLM/agent trading alpha is comprehensively dead"
  closes the family for: (1) Kim-Muhn-Nikolaev flagship withdrawn 2025-02-20; (2)
  FINSABER (KDD 2026) kills the agent literature broadly, 2004-2024, 100+ symbols,
  post-commission, regime-asymmetric failure; (3) Glasserman-Lin: profitable only gross,
  daily-rebalanced, short-heavy, "not a feasible strategy" — **and anonymising tickers
  IMPROVED returns** (their finding is the opposite valence from arXiv:2511.15364's
  "anonymisation costs more than it saves" — §2 below states how X-lane adjudicates
  between the two on OUR data rather than picking a side by citation count). Standing
  rule reaffirmed there: LLM narrates, deterministic engine computes, nothing
  LLM-derived allocates (= X5, already invariant 5).
- **C2 curriculum-transfer verdict** (`docs/ROADMAP_2026-09-10_MODEL_NEWS_AND_THE_EVENT_NET.md`
  line 128, `docs/HANDOFF_2026-09-10_OPUS_BUILDER_MAP.md` §2.2): BASELINE +30.6%/yr t1.78
  > CONTROL +19.5 > TRANSFER +15.0 net (**net figures are a cost-model artefact** — flat
  100bps/day charge — do not re-quote the net numbers; the surviving finding is
  representational: the net DID learn the curriculum, 61.5% vs 48.4% shuffled accuracy,
  **and pre-training on a made-up-news proxy task then transferring discarded
  return-relevant information**). Relevant to X-lane only as the standing closure: C2
  closed "pre-training a representation on made-up news," not text reading in general —
  X2-X4 read REAL news at inference time, a different mechanism, and are not blocked by
  C2's corpse.
- **Regime sensor**: grepped `backend/services/*.py` for `sensor`/`NVDA.*SPY`/`regime` —
  **no dedicated sensor module exists**. `AEGIS_STRATEGIC_INVARIANTS.md` invariant 4
  ("NVDA/SPY/QQQ... can be sensors") is a conceptual invariant, not yet code. X4 (§5
  below) therefore specs the FALLBACK the roadmap names: 21-day SPY trend + VIX level
  from FRED, built fresh in chunk 7, not retrofitted from a nonexistent module.

---

## 1. L3 — Lookahead Propensity on OUR reads

### 1.1 The paper's test (Gao, Jiang, Yan, arXiv:2512.23847 / SSRN 5985277, "A Test of
Lookahead Bias in LLM Forecasts", rev. Jun 2026 — full PDF not fetchable this session,
abstract + secondary summary only; **the builder's first task under this item is to
fetch the PDF once `pdftoppm`/a text-capable fetch exists and confirm the exact
regression specification below is not a paraphrase drift**)

- **LAP itself**: "the probability that the LLM has internalized information about the
  realized outcome," measured per firm-date pair via **date-only recall queries** — i.e.
  a separate, cheap probe prompt that asks the model to state or reconstruct the outcome
  (or closely-dated facts) for a given firm/date WITHOUT being shown the news text at
  all, and scores how much of the true realized outcome the model can produce from the
  date/firm identifier alone. High recall ⇒ high LAP ⇒ the model "already knows the
  answer" for that cell independent of whatever text it is given.
- **The test statistic**: a positive **interaction term between LAP and the LLM's
  forecast in an accuracy regression** — schematically
  `accuracy_i = β0 + β1·forecast_i + β2·LAP_i + β3·(forecast_i × LAP_i) + ε_i`
  (interaction sign/significance is the object of interest, not the levels). A
  significant, positive `β3` means the forecast is MORE accurate exactly where LAP is
  high — i.e., the "skill" concentrates where memorisation is most likely, which is
  diagnostic of lookahead rather than genuine reading.
- **Sample split**: pre-cutoff (inside the model's training window, LAP materially
  positive) vs post-cutoff (after the training-data cutoff, LAP collapses toward zero
  because the events did not exist yet when the model was trained). **The decision rule
  IS the split**: `β3` significant pre-cutoff AND losing significance post-cutoff is the
  paper's own validation that the interaction is measuring lookahead, not just "good
  forecasters do better on easy names."
- **Null hypothesis**: `β3 = 0` in both regimes (no interaction — accuracy is unrelated
  to memorisation propensity at any cutoff position). Rejecting the null pre-cutoff while
  failing to reject it post-cutoff is "contaminated." Failing to reject in EITHER regime
  is "clean, underpowered, or genuinely LAP-independent" — the receipt must distinguish
  these (§1.5).

### 1.2 What "high-memorisation-likelihood prompts" means operationally for our
anonymised digests

R2's digest is masked (`mask_company`: ticker + distinctive CRSP issuer-name tokens →
`[co]`). The paper's date-only recall probe as literally stated assumes the model is
told WHICH firm/date pair it is being asked about — which R2's own read never does (the
company is never named to the reading model). So the LAP probe for our lane is a
SEPARATE, un-masked probe run only for the purpose of measuring memorisation, never fed
into the graded forecast:

```
LAP_PROBE_SYSTEM = "You are a financial-history assistant. Answer only from what you
already know; you are given no documents."
LAP_PROBE_USER   = "For {ticker} in {month} ({firm's real name, ungasked}), state what
you recall happened to its stock price that month relative to the market: UP, DOWN, or
FLAT, and your confidence 0.0-1.0. If you do not recall, say UNKNOWN."
```

Run this probe **once per (name, month) cell already in R2's PANEL-B universe**, at
temperature 0.0, decoupled from the masked read. `LAP_i` for that cell is the probe's
own confidence when its stated direction matches the REALISED forward label (`fwd` in
the answers jsonl), else 0 (a confident-but-wrong recall is not evidence of lookahead —
it is evidence of a bad recall, and must not inflate LAP). A cell where the probe says
UNKNOWN gets `LAP_i = 0`. This makes "high-LAP" operational without needing membership-
inference machinery: it is "the model, asked directly and given nothing, already knows
the right answer with stated confidence."

### 1.3 Per-model cutoffs, with source

| model | stated cutoff | source | confidence |
|---|---|---|---|
| Qwen2.5-7B-Instruct | **2024-06-30** (some secondary sources say "April 2024") | not an official Alibaba cutoff date page; triangulated from OpenRouter/Puter provider pages and community cutoff trackers (`github.com/HaoooWang/llm-knowledge-cutoff-dates`) — **not independently verified against Qwen's own model card in this session**; builder should re-check `Qwen/Qwen2.5-7B-Instruct`'s HF README before freezing | MEDIUM |
| DeepSeek-V3 | **~2024-07** per an extracted system prompt (unofficial); no official published date | third-party extraction (`knostic.ai` blog), not a DeepSeek-published figure | LOW |
| DeepSeek-R1 | **~2023-10 to 2024** — the model itself has reported 2023-10 in some sessions while demonstrating knowledge into 2024, i.e. **inconsistent self-report**, consistent with R1 being distilled/RL-tuned on top of a V3-family base with a blended cutoff | community reports (`x.com/yi_ding`, GitHub issue `deepseek-ai/DeepSeek-R1#615`) | LOW |

**Consequence for the split (§1.1):** R2's live reader is Qwen2.5-7B, cutoff ~2024-06/07.
PANEL-A (2015-02..2024-11) straddles this cutoff **inside its own window** — the last
~5 months of PANEL-A (2024-07..2024-11) are POST-cutoff for this specific model, and the
rest is pre-cutoff. PANEL-B (2025-01..2026-07) is **entirely post-cutoff** for
Qwen2.5-7B — every PANEL-B cell already qualifies as the post-cutoff arm of the L3 split,
which is why PANEL-B is also the natural L3 confirmatory slice: if PANEL-B's own edge
(§ TRIAL-R2 §3 primary metric) survives while LAP on PANEL-B cells is near zero
throughout, that is consistent with genuine reading; L3 does not need a SEPARATE
post-cutoff slice carved out of PANEL-B, because the whole panel already is one. The
useful split is instead WITHIN PANEL-A: pre-2024-07 vs 2024-07..2024-11 cells, to
replicate the paper's own before/after design once, cheaply, on data already read.

For DeepSeek reads elsewhere in the repo (`llm_analyzer.py`, any DeepSeek-backed
forecast), the cutoff is far less certain (LOW confidence, ~2024 midyear at best) — any
receipt quoting a DeepSeek-authored pre-2024 forecast must carry a wider LAP uncertainty
band and should not claim a clean pre/post split until DeepSeek's cutoff is pinned down
better than a scraped system prompt.

### 1.4 Script shape — `scripts/night_l3_lookahead.py`

```
python -m scripts.night_l3_lookahead --panel {A|B} [--max-cells N] [--smoke]
```

1. Load the panel's persisted answers jsonl (PANEL-A has none persisted per §0 — L3
   on PANEL-A requires a NEW read using the frozen R2 prompt if answers are to be
   re-derived; flag this and default `--panel B`, since PANEL-B's answers.jsonl already
   accrues incrementally).
2. For every `(name, month)` cell with a `read_MASKED` answer AND a realised `fwd`,
   run the LAP probe (§1.2) through `free_inference.complete(backend="local_gguf",
   purpose="l3_lap_probe")` — a SEPARATE `purpose` string so its spend/refusal telemetry
   never mixes with R2's own `purpose="r2_monthly_read"` line.
3. Compute `LAP_i` per cell (§1.2).
4. Fit the accuracy-interaction regression (§1.1) on whichever slice is being tested
   (PANEL-A pre/post-2024-07 split; PANEL-B as the all-post-cutoff confirmatory slice).
   `accuracy_i` = 1 if `sign(dir_i) == sign(fwd_i)` else 0 (matches R2's own sign-accuracy
   convention already reported in its receipts).
5. Report `β3`, its standard error (cluster by monthly block, same dependence-unit
   convention as canon §58/TRIAL-R2 §4 — cells inside one month are not independent),
   and whether it is significant at the pre-registered α (reuse R2's α=0.05).
6. Write `LAP_score` back onto EVERY `PredictionRecord` this feeds (per the 1.4.0
   schema field, §0) keyed by `prediction_id`, so any downstream leaderboard read of a
   pre-cutoff record can print it (§6).

### 1.5 Receipt fields (new file, `night_l3_lookahead_run{NN}.json`)

```
job, licence="PRODUCT_EXPERIMENT", panel, model, model_cutoff_date, model_cutoff_source,
model_cutoff_confidence,
n_cells_pre_cutoff, n_cells_post_cutoff,
beta3_pre, beta3_pre_se, beta3_pre_t, beta3_pre_p,
beta3_post, beta3_post_se, beta3_post_t, beta3_post_p,
verdict ∈ {CONTAMINATED (β3 sig. positive pre-cutoff AND loses significance post-cutoff),
           CLEAN (β3 not significant in EITHER regime),
           INCONCLUSIVE_UNDERPOWERED (n too small to resolve the declared MDE — compute
             the MDE the same way TRIAL-R2 §4 does, before reading; report it even when
             CLEAN so a CLEAN verdict cannot hide behind zero power),
           AMBIGUOUS (significant in both, or significant only post-cutoff — the paper's
             own falsification pattern did not hold; do not force this into CLEAN)},
lap_mean_pre, lap_mean_post, lap_probe_purpose_tag, lap_probe_spend_usd (0.00, local),
written_utc
```

`LAP` as it travels onto a `PredictionRecord` (§0's 1.4.0 field) is the CELL-level
`LAP_i`, not the regression's `β3` — `β3` is a study-level verdict, `LAP_score` is a
per-record diagnostic. A leaderboard row for a single pre-cutoff forecast prints
`LAP_score` (the cell's own memorisation propensity); a receipt for the L3 STUDY itself
prints `beta3_*`.

### 1.6 ChronoGPT/ChronoBERT as the same-era control (2015-2024 reads)

- **What exists on the Hub**: `manelalab/chrono-bert-v1-{YYYYMMDD}` (ModernBERT-architecture
  bidirectional encoder, "as-of" checkpoints spanning 1999-2024, e.g.
  `chrono-bert-v1-20001231`, `-20181231`, `-20201231`, `-20241231`) and
  `manelalab/chrono-gpt-v1-{YYYYMMDD}` (modded-NanoGPT-architecture autoregressive
  decoder, same date range, e.g. `-19991231`, `-20031231`, `-20111231`, `-20201231`,
  `-20221231`, `-20241231`). The date suffix is the point-in-time training cutoff for
  that checkpoint (per the NBER/arXiv:2502.21206 "yearly incremental releases" design) —
  **this specific mapping (suffix = cutoff, not release date) is stated with MEDIUM
  confidence**: the fetched model card for `chrono-gpt-v1-20241231` does not explicitly
  confirm it in its own text, though it follows directly from the paper's design and the
  naming pattern; builder should confirm against the arXiv paper's methodology section
  before quoting this in a receipt.
- **ChronoGPT-v1-20241231 size (fetched from its model card)**: ~1.55B parameters,
  embedding dim 1,536, 26+26 encoder/decoder layers (self-described; note this reads as
  an odd architecture description for a stated "autoregressive decoder" — likely a
  model-card artefact worth a second read, not taken at face value), context 1,792
  tokens, GPT2Tokenizer. **Loading path: `transformers` with `trust_remote_code=True`
  via a custom `ChronoGPT` class — NOT distributed as GGUF, and NOT a stock
  architecture llama.cpp recognises out of the box.** No official GGUF conversion was
  found.
- **RTX 5060 8GB feasibility**: at ~1.55B params, fp16 weights are ~3.1GB — comfortably
  under 8GB VRAM via `transformers` directly (no quantisation needed for inference), so
  it CAN run locally, but **only via `transformers`, not via `llama.cpp`/GGUF** unless
  someone writes a GGUF conversion for the custom `ChronoGPT` architecture first (a
  nontrivial side project, not scoped into chunk 7). `chrono-bert-v1-*` (ModernBERT,
  encoder-only, no generation) is even smaller and trivially fits, but is not a
  generative forecaster — it is usable only as a masked-LM / classification-head control
  (e.g., fine-tune-free zero-shot direction scoring via a prompted cloze), not as a
  drop-in replacement for R2's generate-DIRECTION-and-CONFIDENCE prompt.
- **Use as the same-era control for 2015-2024 reads (PANEL-A)**: pick the ChronoGPT
  checkpoint whose "as-of" date is the LAST DAY BEFORE the read month begins (e.g. for a
  2016-03 cell, use `chrono-gpt-v1-20160229`... if that exact checkpoint exists — the
  known checkpoints are sparser than monthly per the search results, e.g. `-19991231`,
  `-20031231`, `-20111231`; **the builder must first enumerate the FULL checkpoint list**
  via `hf_fs`/`hub_repo_search` under `manelalab/`, not assume monthly density) and run
  the IDENTICAL R2 masked-digest prompt through it via `transformers`. Because ChronoGPT
  at that checkpoint was never trained on anything after its as-of date, ANY skill it
  shows on a pre-2024 cell is by construction not lookahead — it is the "genuinely
  same-era" comparator the roadmap asks for, orthogonal to and stronger than the
  shuffled-digest control (which controls for "is there information in the text at all"
  but not "is the reader's skill coming from memorising the FUTURE relative to the
  read date").
- **Cost of standing this up**: new script (`scripts/night_l3_chronogpt_control.py`),
  new dependency path (`transformers`, `trust_remote_code=True` — a supply-chain note:
  custom code execution from the Hub should be pinned to a specific commit sha, not
  `main`), and a new digest-format adapter (ChronoGPT's 1,792-token context is smaller
  than the 48-max-token-OUTPUT / much-larger-input R2 prompt allows for on Qwen — the
  8-doc/320-char digest may need truncation to fit). **This is scoped as an OPTIONAL,
  SEPARATE deliverable inside chunk 7**, not a blocker to L3's own regression (§1.1-1.5),
  which uses only the LAP probe and needs no ChronoGPT call.

---

## 2. The anonymisation gap

### 2.1 The measurement

R2's frozen prompt (system+user sha256 already pinned in TRIAL-R2 §6) run on the SAME
cells three ways:
1. **`read_MASKED`** — already run, the live arm (masked digest, real month).
2. **`read_RAW`** (NEW) — identical digest construction, IDENTICAL cells and months, but
   built from `docs.parquet`/`docs_real` (the real, un-anonymised company name and text)
   instead of `docs_masked.parquet`. Same prompt, same decoding params, same grading.
3. **`control_SHUFFLED`** — already specced in TRIAL-R2 (digest from a random other
   month), run against BOTH the masked and raw digest constructions if budget allows, or
   against masked only (already the plan) with the raw-arm's own shuffled control run
   once cheaply if `read_RAW` is adopted as a permanent second arm.

**anonymisation_gap** = `net_ann_pct(read_RAW) − net_ann_pct(read_MASKED)`, computed
identically to TRIAL-R2's own primary metric (Newey-West lag-2 t on monthly date blocks,
net of 25bps/side realised turnover), reported WITH ITS OWN t-statistic on the paired
per-block difference (raw month t vs masked month t, same block, paired), not just a
level subtraction. A positive gap with a significant t means anonymisation IS costing
signal on our data; a gap indistinguishable from zero, or negative, means it is not (or
is net protective once weighed against the AMNESIA-canary risk it controls).

### 2.2 The rule for which arm the lane adopts

The literature disagrees by DESIGN, not by noise: arXiv:2511.15364 (credit-downgrade
prediction) finds anonymisation degrades performance and the degradation typically
EXCEEDS the lookahead bias it prevents; Glasserman-Lin (already closed in
`NEGATIVE_RESULTS.md` §19) find the OPPOSITE — anonymising tickers IMPROVED returns on
their daily sentiment long-short. **Adjudicate on OUR data by a two-part test, not by
citation count**:

1. Compute `anonymisation_gap` (§2.1) on PANEL-B (the only panel with both a live
   `read_MASKED` history AND enough remaining budget to add `read_RAW` cheaply — local,
   $0). This settles the SIGN and SIZE question empirically for this specific model,
   prompt, and cross-section — it does not need to agree with either paper, because
   neither paper ran this model on this data.
2. Cross-check against the AMNESIA canary (already run, §0): if `read_RAW`'s accuracy
   exceeds `read_MASKED`'s BUT the AMNESIA gap (real-name vs masked-name accuracy on the
   identical canary subset, already measuring exactly this) is ALSO large and positive,
   the raw arm's apparent edge is presumptively memorisation, not information, and MASKED
   is adopted regardless of the raw arm's raw score. If the AMNESIA gap stays small
   (≤+0.02, TRIAL-R2's own adopt threshold) while `read_RAW` still beats `read_MASKED`,
   the extra accuracy is more plausibly genuine entity/relationship information
   (arXiv:2511.15364's mechanism: sector peers, supply-chain links, absolute price
   levels that masking destroys) and RAW may be preferred going forward — but every
   receipt from that point prints BOTH numbers and the AMNESIA cross-check, permanently,
   never just the winner.
3. **Default while PANEL-B's raw arm has not yet run**: stay on `read_MASKED` (the
   status quo, already the registered TRIAL-R2 arm) — do not switch to raw on a
   citation from either paper; switch only on a measured, block-paired
   `anonymisation_gap` receipt from our own PANEL-B.

### 2.3 Receipt (new file, `night_x2_anonymisation_gap_run{NN}.json`)

```
job, licence, panel, cells_compared, months,
net_ann_pct_masked, net_ann_pct_raw, net_ann_pct_shuffled_control,
anonymisation_gap_pct_pt, gap_nw_t, gap_paired_blocks,
amnesia_gap (imported from R2's own canary receipt, not re-derived),
adopted_arm ∈ {MASKED, RAW, CONDITIONAL_INSUFFICIENT_DATA},
adoption_rule_text (verbatim §2.2 rule, so a reader never has to re-derive why),
written_utc
```

---

## 3. X2 — belief elasticity as a feature

### 3.1 The construction, from C1's rows

For each C1 row (real headline `anon`, its `event_type`/`direction`/`magnitude`, and 1-3
`counterfactuals`), and for each counterfactual `c`:

1. Build TWO single-document "digests" in R2's exact digest format (§0): one containing
   only `anon` (the real anonymised headline), one containing only `c["text"]` (the
   counterfactual's anonymised rewrite). Both already exist verbatim in the C1 file — no
   new extraction needed.
2. Run BOTH through the frozen R2 prompt (same system/user template, same decoding) via
   `free_inference.complete`, `purpose="x2_belief_elasticity"`.
3. Parse `DIRECTION`/`CONFIDENCE` from each reply exactly as `night_r2_monthly_llm.py`
   already parses R2 replies (reuse its parser function, do not re-implement).
4. Convert each reply to a signed probability-like scalar `p = confidence if
   direction==UP else (-confidence if direction==DOWN else 0.0)` for `p_real` and
   `p_cf`.
5. `elasticity = (p_cf − p_real) / Δ_event`, where `Δ_event` is a SIGNED per-counterfactual-
   kind scale:
   - `sign_flip`: `Δ_event = c["direction"]_signed − real_direction_signed` (the C1
     row's own `direction`/counterfactual `direction` fields, mapped {POSITIVE:+1,
     NEGATIVE:-1, UNCLEAR: excluded — a counterfactual whose OWN direction is UNCLEAR
     cannot anchor a denominator and the cell is dropped, not zero-filled}). For a clean
     sign flip this is typically ±2.
   - `escalation`: `Δ_event = +1` fixed (escalation always tags POSITIVE-in-the-C1-schema
     sense of "more of the same stated direction," per the file's own generation
     convention observed in the sampled rows) — **the builder should re-verify this
     against a larger sample before freezing**, since the sampled rows show escalation
     `direction` sometimes equal to the real row's own direction and sometimes not.
   - `actor_timing`: **excluded from elasticity by default** — it changes WHO or WHEN,
     not the event's sign/magnitude, so `Δ_event` has no principled scale; it is kept
     only for the direction-flip test (§3.5), not for the elasticity feature itself.
6. `elasticity` is a per-(cell, counterfactual) number. Aggregate to a per-`uid` (i.e.
   per real headline) feature by taking the `sign_flip`-kind elasticity as the PRIMARY
   belief-elasticity feature (best-defined denominator) and reporting the `escalation`
   one as a secondary/diagnostic column, never fused into one number without the
   sign_flip leg present.

### 3.2 Placebo elasticity from a date-shifted pair

For the same `uid`, build a THIRD digest: the real `anon` text, but presented as if it
were news from a DATE-SHIFTED month (reuse the existing shuffled-digest machinery's rng
convention — same seed family, `20260909`, applied to counterfactual pairing rather than
month pairing) paired against a counterfactual drawn from an UNRELATED `uid`'s
counterfactual set (same `kind`, different underlying headline). Compute the same
elasticity formula on this mismatched pair. A real mechanism should show elasticity
concentrated on the TRUE (headline, its own counterfactual) pairs and near-zero on the
placebo (headline, unrelated counterfactual) pairs; the placebo distribution's mean is
the null the true-pair distribution is compared against (paired or two-sample t,
whichever the receipt's own diagnostics table needs — report both).

### 3.3 PIT rule

The elasticity feature for a given `uid`/date can only enter the tabular head (E1) for a
prediction whose OWN decision date is on or after `effective_at` (C1's own field, the
real headline's publication date) — this is already E1's general PIT contract (first
open strictly after publication), unchanged by X2; the only new thing X2 adds is that
BOTH the real-headline forecast AND the counterfactual-substituted forecast for a given
`uid` must be computed and available before `effective_at`'s trading decision, which they
trivially are (the counterfactual call needs no future information — it needs only the
already-published real headline it perturbs).

### 3.4 How it enters E1's tabular head

`belief_elasticity_sign_flip` (float, primary), `belief_elasticity_escalation` (float,
secondary), `belief_elasticity_placebo_null` (float, the date-shifted control's own
value for the SAME uid — carried alongside so a consumer of the feature table can net
the real elasticity against its own placebo rather than a pooled benchmark), joined onto
E1's existing text-and-return panel by `(symbol, effective_at)` — a left join, `NaN` when
C1 has no counterfactual row for that (symbol, date) pair (most cells: C1 covers 6,935
headlines, E1's panel covers 339,657 text-and-return cells). LightGBM handles the NaN
natively (per this repo's own DO/DO-NOT rules — no `fillna(0)`).

### 3.5 Direction-flip test (P3) as pass/fail per cell

Per the Alpha Illusion's P3 (Counterfactual Robustness): for a `sign_flip`
counterfactual, the model's forecast direction on the counterfactual digest MUST differ
from its forecast direction on the real digest in the SAME sign as the counterfactual's
own direction change, or the cell FAILS the flip test. Formally:
`flip_pass = 1 if sign(p_cf − p_real) == sign(Δ_event) else 0` (ties, `p_cf == p_real`,
count as FAIL — a model that does not move at all on a sign-flipped input is not
demonstrating sensitivity to content). The per-cell pass/fail rate, aggregated over all
`sign_flip` counterfactuals in a receipt, is P3's headline number; the roadmap's MUST NOT
REGRESS #24 requires this pass/fail rate on every X-lane receipt (§6).

### 3.6 Cost

C1 has 6,935 rows (grew from the roadmap-stated 1,962) with up to 3 counterfactuals
each (2 real forward calls needed per counterfactual actually used: one for `anon`,
reusable across that uid's counterfactuals since the real-headline call is the same
digest every time — cache it — and one per counterfactual text). Using only `sign_flip`
(6,674 available) for the primary elasticity plus one real-headline call per uid
(6,935, but cacheable to ~6,935 unique real calls since `anon` repeats per uid, not per
counterfactual): **≈13,609 local calls** for the primary pass (real + sign_flip), rising
to **≈19,302** if `escalation` is added as the secondary leg, plus the placebo pairs
(§3.2, roughly one placebo call per uid used ≈6,935 more). At Qwen2.5-7B's measured
~41.4 tok/s (7B figure from S52 memory) or the ~19.8 tok/s measured for the 30B-A3B
variant (not the model in use here — 7B's own rate is the relevant one), a 48-max-token
reply plus ~400-500 prompt tokens at 7B generation speed (measured elsewhere in this
repo at roughly 4-12s/call in the C1 file's own `latency_s` field, median ~5-6s from the
sampled rows) puts full elasticity construction (primary + secondary + placebo, ~26,000
calls) at **roughly 36-43 hours of wall time on the laptop GPU serially** — this is an
OVERNIGHT-SCALE job, not a chunk-7-afternoon job, and should be scoped as a
multi-night `night_factory` batch with checkpoint/resume (per S51/S52's own
checkpoint-carry lesson), not a single blocking run. Cost in dollars: $0.00 (local_gguf).

### 3.7 Receipt

`night_x2_belief_elasticity_run{NN}.json`: `job, licence, n_uids, n_counterfactual_calls,
n_real_calls_cached, elapsed_s, elasticity_sign_flip_mean, elasticity_sign_flip_sd,
elasticity_placebo_mean, elasticity_placebo_sd, paired_t_true_vs_placebo,
flip_test_pass_rate, flip_test_n, refusals_by_class, deepseek_equivalent_price_usd,
cost_usd=0.00, written_utc`.

---

## 4. X3 — scenario forecasts

### 4.1 Prompt contract (JSON schema) for k=3 next-session scenarios

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "aegis://schemas/scenario_forecast_row.json",
  "title": "AegisScenarioForecastRow",
  "type": "object",
  "additionalProperties": false,
  "required": ["scenario_set_id", "symbol", "as_of", "scenarios"],
  "properties": {
    "scenario_set_id": {"type": "string", "description": "uuid or content-hash, one per (symbol, as_of) call"},
    "symbol": {"type": "string"},
    "as_of": {"type": "string", "description": "ISO date, the last session's close this forecast is made after"},
    "scenarios": {
      "type": "array", "minItems": 1, "maxItems": 3,
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["headline", "probability", "event_type", "direction", "magnitude_bucket"],
        "properties": {
          "headline": {"type": "string", "maxLength": 200, "description": "a plausible next-session headline, not the actual future"},
          "probability": {"type": "number", "minimum": 0.0, "maximum": 1.0},
          "event_type": {"type": "string", "description": "one of the 39 typed-event ids from spec_events_and_calibration.md §1.2, or no_event"},
          "direction": {"type": "integer", "enum": [-1, 0, 1]},
          "magnitude_bucket": {"type": "string", "enum": ["NEGLIGIBLE","SMALL","MODERATE","LARGE","EXTREME"]}
        }
      }
    }
  }
}
```
`Σ probability` across the set need NOT equal 1.0 exactly (the k scenarios are not
required to be exhaustive — "these are the things that might happen," Murat's own
framing, roadmap §10 X3) but the receipt must print the sum so a set that is wildly
over/under 1.0 (e.g. 3 scenarios each claimed at 0.9) is visible as a calibration defect
rather than hidden.

### 4.2 Engine pricing by historical analogue

For each scenario, look up the (`event_type`, `era_tag`) cell in the typed-event/era
base-rate table (built once from the corpus of ALREADY-RESOLVED typed events — reuse
§0's `spec_events_and_calibration.md` §1.2 vocabulary and whatever historical event
panel already carries typed-event labels, e.g. `event_table_v1.parquet` — the builder
should confirm this parquet already carries `event_type` in the 39-id vocabulary or
needs a backfill pass) and read off that cell's OWN historical mean/median forward
abnormal return and its dispersion. `priced_return_i = historical_mean_return(event_type,
era) `. This is a LOOKUP, never a model-generated number — the LLM proposes the scenario
and its event-type/direction/magnitude classification; the deterministic engine (not the
LLM) supplies the dollar-shaped price, per invariant 5/X5.

### 4.3 `PredictionRecord` shape for a scenario set

One row PER SCENARIO, all sharing `scenario_set_id` (new grouping key — add to the 1.4.0
schema alongside the fields §0 already lists, since none of the existing 1.4.0 additions
carry a set-level grouping id):
```
prediction_id (unique per scenario), scenario_set_id (shared), symbol, made_at, as_of,
probability (from the model), event_type, direction, magnitude_bucket,
priced_return (from §4.2's lookup), mechanism_id="x3_scenario_forecast_v1",
licence="PRODUCT_EXPERIMENT", costs_charged=False (informational forecast, not yet a
sized position — costs apply only if/when E1 sizes off it), era_tag (assigned at write
time per the 1.4.0 convention).
```

### 4.4 Grading rule

At `as_of + 1 session`, pull the realised next-day corpus rows for `symbol` (whatever
typed-event extraction chunk 3/N-lane produces per day) and match by `event_type`: the
scenario whose `event_type` equals the realised day's DOMINANT typed event for that
symbol (ties broken by highest-magnitude realised event, matching §2.4's "one row per
document, extract the dominant one" convention from spec_events_and_calibration.md) is
the one "reality picked." If NO scenario's `event_type` matches any realised event that
day (including the case where the realised day is itself `no_event`), and none of the
k scenarios declared `no_event`, the set is graded as a **miss for all k** — this must
not be silently excluded from the Brier computation (a set that never includes the true
outcome as an option is a genuine calibration failure, not a data gap). Brier of the
set: standard multi-class Brier `(1/k) Σ (probability_i − outcome_i)²` where
`outcome_i = 1` for the matched scenario (if any) and `0` for the rest, PLUS a residual
mass term for "none matched" scored against an implicit `no_event`-or-other bucket at
probability `1 − Σ probability_i`.

### 4.5 Base-rate scenario control

For the same `(symbol, as_of)` cells, construct a control scenario set using ONLY the
era's unconditional event-type frequencies (no LLM call: pick the top-k most frequent
event types for that symbol's sector/era from the historical panel, assign each the
era's own unconditional frequency as its probability) and grade it identically. The
LLM-generated set is compared against this control's Brier, never against zero — same
"never against zero" discipline as R2's shuffled-digest control (§0, D1 lesson already
in this repo's canon).

---

## 5. X4 — regime routing

### 5.1 The sensor

No dedicated sensor module exists in `backend/services/` today (confirmed by grep — see
§0). Build the FALLBACK the roadmap itself names: **21-day SPY trend** (sign and
magnitude of SPY's trailing 21-trading-day return, computed from whatever bars source
E1/N-lane already ingests — `prices_2025_26/bars.parquet` has SPY already, per R2's own
`MARKET_SYMBOL = "SPY"` constant) **+ VIX level from FRED** (series `VIXCLS`; FRED is
free, no key required for the CSV download endpoint — confirm against whatever FRED
client this repo already has, if any, before adding a new one). Regime label, 2×2:
`{TREND_UP, TREND_DOWN} × {VIX_LOW (<20), VIX_HIGH (≥20)}` — 20 is FRED/CBOE's own
conventional VIX regime line, not a fitted threshold, kept fixed to avoid the "a min-
names filter selects the regime" failure mode already in this project's memory
(feedback: a threshold chosen by looking at the result is not a threshold).

### 5.2 The route rule

Route X-lane reads (R2's monthly read, X2's elasticity feature, X3's scenario forecasts)
through the sensor: an X-lane forecast is ADMITTED to the graded book only in regimes
where the mechanism's OWN prior evidence showed it working — for R2 specifically, this
requires first SPLITTING PANEL-B's existing 19 monthly blocks by the sensor's regime at
each block's start and checking whether the read-minus-control edge concentrates in one
regime (this is a look at ALREADY-COLLECTED data, permitted under `PRODUCT_EXPERIMENT`'s
"explore dirty" licence, §EXPLORE DIRTY PROMOTE CLEAN — but the resulting routing rule,
once chosen, is then evaluated OUT OF SAMPLE on new blocks under the routed/unrouted
control below, not treated as already proven by the exploratory split).

### 5.3 The unrouted control

The routed book's net return, block by block, is compared against the SAME mechanism
run UNROUTED (every block, no regime gate) over the identical evaluation window — not
against a naive benchmark. This isolates the ROUTING's own contribution rather than
re-measuring whether the base mechanism works at all (that is TRIAL-R2's job).

### 5.4 RW1 windows

RW1 is referenced in the roadmap (§10 X4: "Reuses RW1 windows") but not located in the
files read this session — the builder should grep `RW1` under `backend/services/` and
`scripts/` before this item ships; if it does not exist yet either (plausible, given the
sensor module also does not exist), RW1 must be built as: rolling windows of a fixed
length (this repo's convention elsewhere is 12- or 24-month rolling windows for
walk-forward splits — reuse whichever the nearest existing rolling-window evaluator in
`backend/services/backtest.py` or `portfolio_farm/` already uses, rather than inventing
a new window length un-anchored to the rest of the codebase) over which the routed-vs-
unrouted comparison (§5.3) is repeated, so a single lucky window is not mistaken for a
routing effect — same walk-forward discipline this repo already mandates for all ML
validation (project CLAUDE.md: "Use walk-forward temporal splits, never random k-fold").

---

## 6. The P1-P6 checklist as a receipt schema

Every X-lane receipt (`night_l3_*`, `night_x2_*`, a future `night_x3_*`/`night_x4_*`)
must carry a `P1_P6` block. Proposed shape, one boolean/value per protocol item, matching
arXiv:2605.16895's own six:

```json
"P1_P6": {
  "P1_temporal_integrity": {"anonymised": true, "date_shifted_placebo_run": true,
    "time_locked_control_run": false, "time_locked_control_model": null,
    "cutoff_stated": true, "cutoff_source": "...", "cutoff_confidence": "MEDIUM|LOW|HIGH"},
  "P2_dynamic_universe": {"universe_vintage_respected": true, "delisting_handled": true|false,
    "note": "..."},
  "P3_direction_flip": {"pass_rate": 0.0, "n": 0, "test": "sign_flip counterfactual, per §3.5"},
  "P4_calibration_ece": {"ece": 0.0, "n_bins": 10, "brier": 0.0, "brier_decomposition":
    {"reliability": 0.0, "resolution": 0.0, "uncertainty": 0.0}},
  "P5_full_frictions": {"cost_bps_per_side": 25, "costed": true, "gross_reported_separately": true},
  "P6_disaggregation": {"single_agent_baseline_run": true|false, "homogeneity_metric": null|float}
},
"LAP": {"score": null|float, "study_verdict": null|"CONTAMINATED|CLEAN|INCONCLUSIVE_UNDERPOWERED|AMBIGUOUS",
  "applies": true|false, "reason_if_not_applicable": null|"post-cutoff panel, LAP not required per §1.3"},
"anonymisation_gap": {"value_pct_pt": null|float, "t": null|float, "adopted_arm": null|"MASKED|RAW"}
```

### The refusal test

`test_x_lane_receipt_completeness.py` (new): load every `night_l3_*.json`, `night_x2_*.json`,
future `night_x3_*`/`night_x4_*` receipt under `backend/data/optimus/night_factory_*/`
whose filename matches an X-lane job pattern; assert `P1_P6` is present with all six
keys, `LAP` is present (even if `applies: false`, WITH a stated reason — silently
omitting the key is refused, an explicit non-applicability is not), and
`anonymisation_gap` is present for any receipt whose lane reads free text (R2/X2; X3/X4
receipts that never touch anonymised text state `anonymisation_gap.value_pct_pt: null`
with `reason: "no anonymised-text arm in this lane"`, not a bare omission). A receipt
failing any of these assertions is REFUSED by "the leaderboard sync" — since no
dedicated `leaderboard.py` module exists in this repo yet (grepped, absent), this is
scoped as: whatever function currently reads X-lane receipts into `daily_digest.py`'s
`reliability` section (the nearest existing consumer, §0) must call this same
completeness check before ingesting a row, and the test pins that call exists (an
`AST`-level check per this repo's own "grep-shaped guard" lesson — check the function
BODY calls the completeness checker, not merely that a docstring near it mentions P1-P6).

---

## 7. Order of build in chunk 7 — cheapest test first

| step | item | why first/here | known-answer test |
|---|---|---|---|
| 1 | **P1-P6 receipt schema + refusal test** (§6) | Zero model calls, pure schema/test work; every other item in this chunk needs somewhere to write its P1_P6 block, so building the schema after the science is built means re-touching every receipt writer twice | Feed the test a hand-built receipt missing `P4_calibration_ece` → assert REFUSED; feed it a complete one → assert PASS. Feed a receipt with `LAP: {applies: false}` and no `reason_if_not_applicable` → REFUSED. |
| 2 | **Anonymisation-gap measurement, `read_RAW` arm** (§2) | Reuses 100% of `night_r2_monthly_llm.py`'s existing machinery (digest builder, grader, parser) with one new data source (`docs.parquet` instead of `docs_masked.parquet`) and zero new statistical machinery beyond a paired t already used elsewhere in R2 | On a synthetic panel where `read_RAW` and `read_MASKED` are fed IDENTICAL digests (mask a no-op), `anonymisation_gap` must compute to exactly 0.0 ± floating-point epsilon and `gap_nw_t` must be `None`/`NaN` (zero variance) rather than crashing. |
| 3 | **L3 Lookahead Propensity** (§1) | New probe prompt (small, cheap: ~3-4 calls per cell already-answered, no new digest construction) and a regression the repo's own `statsmodels`/`numpy` stack already supports; needed before X2/X3 can honestly claim their forecasts are "not quoted" without a LAP field per MUST NOT REGRESS #24 | Feed the regression a SYNTHETIC dataset where `accuracy = 0.9` whenever `LAP > 0.5` and date is pre-2024-07, and `accuracy = 0.5` (coin flip) everywhere else (post-cutoff, or LAP≤0.5 pre-cutoff) → assert `verdict == "CONTAMINATED"` and `beta3_post` is NOT significant. Feed a dataset where `accuracy` is independent of `LAP` everywhere → assert `verdict == "CLEAN"`. |
| 4 | **X2 belief elasticity, sign_flip leg only** (§3.1-3.5, escalation deferred) | Reuses R2's exact prompt/parser again; the only new code is the elasticity arithmetic and the flip-test pass/fail, both pure functions testable without any model call | On a synthetic pair where `p_real = -0.6`, `p_cf = +0.6`, `Δ_event = +2` (a clean sign flip from DOWN to UP): assert `elasticity == 0.6`, `flip_pass == 1`. On a pair where `p_cf == p_real` (no movement at all): assert `flip_pass == 0`. |
| 5 | **X4 regime routing (sensor build only, no live routing yet)** (§5.1) | The sensor (21-day SPY trend + FRED VIX) has zero dependency on any LLM call and can be built and tested purely against `bars.parquet` + a FRED fetch, in parallel with steps 2-4; routing itself (§5.2-5.4) waits until PANEL-B's edge is confirmed (TRIAL-R2's own decision rule, not yet resolved as of this writing) — routing an unconfirmed mechanism is premature | Feed the sensor a synthetic SPY series with a known 21-day return and a fixed VIX level → assert the regime label matches the hand-computed 2×2 cell exactly at the 20-VIX boundary (test both `19.99` and `20.00` land on the documented side of the fixed threshold). |
| 6 | **X3 scenario forecasts** (§4) | Needs the typed-event/era base-rate lookup table (§4.2), which depends on confirming `event_table_v1.parquet` already carries the 39-id vocabulary (an open dependency, §5.4-style) — likely the LONGEST pole in this chunk, scheduled last | Feed the grading function a scenario set with one scenario whose `event_type` exactly matches the realised day's dominant event at `probability=0.7` and two others at `0.15` each → assert Brier computes to `(1-0.7)^2 + (0-0.15)^2 + (0-0.15)^2 = 0.135`. Feed a set where NONE match → assert the residual-mass term is included, not silently dropped. |

Note on sequencing vs the roadmap's own listed order (X1→X4 then L3): X1 (horizon/hold
rule) is NOT separately re-specced above because it is already fully live as
`night_r2_monthly_llm.py`'s own design (5/21-session hold, per §0) — nothing in chunk 7
needs to build X1, only to make its RECEIPTS carry the P1-P6/LAP/anonymisation-gap
fields retroactively (step 1's schema, applied to R2's next run). The heaviest wall-clock
item (X2's full elasticity sweep, §3.6, ~36-43 hours) should be KICKED OFF as an
overnight batch as soon as step 4's pure-function tests pass, running in the background
while steps 5-6 are built during the day — do not block chunk 7's human-visible progress
on X2's own multi-night completion.
