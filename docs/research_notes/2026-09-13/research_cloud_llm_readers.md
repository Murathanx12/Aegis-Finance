# Cloud LLM readers for L2_typed_events, and the news-API gap

Research note, 2026-09-13. Sonnet research agent. Written for an Opus builder starting
within the hour. Web prices are as scraped today (2026-09-13); NVIDIA and DeepSeek both
publish pricing pages that have moved mid-2026, so re-check before wiring a bill.

Licence: `PRODUCT_EXPERIMENT` (no significance gate). The four invariants still bind —
PIT discipline, no leakage, costs never omitted, frozen-once-forward. Every cloud-model
read over a pre-cutoff row owes an L3 Lookahead Propensity result (roadmap rule 21).

## 0. What's already true in this repo (read, not researched)

- **One wired cloud provider: DeepSeek.** `backend/services/llm_analyzer.py::_call_llm`
  tries Claude first (`_ANTHROPIC_API_KEY`, always empty in `.env` — dormant, untested
  live), then DeepSeek (`_DEEPSEEK_API_KEY`, live). `SOLE_PROVISIONED_PROVIDER =
  "deepseek"`, pinned by `backend/tests/test_llm_provider_declaration.py`. `_LANGUAGE_PIN`
  is appended centrally to every system prompt; a reply >10% non-Latin script is refused
  (not repaired/retried), counted per-provider in `llm_usage()`.
- **Local reader**: `backend/services/llama_server.py` (llama.cpp). Qwen2.5-7B incumbent
  measured 41.4 tok/s generation / 5.6 tok/s prompt-eval (contended). Qwen3-30B-A3B
  measured 19.8 tok/s generation, same prompt-eval rate
  (`L4_qwen3_measure_run01.json`, itself flagged a **lower bound** — 20 cores were
  saturated by a concurrent PyInstaller build when taken).
- **The actual backlog**, from today's frozen receipt
  (`backend/data/optimus/night_factory_2026-09-13/L2_typed_events_run01.json`):
  - **6,020 rows PENDING_MODEL**, 0 already typed, from 5 label sources
    (`alpaca_benzinga_news`, `gdelt_doc_v2`, `sec_edgar_8k_current_atom`,
    `yfinance_ticker_news`, `finnhub_company_news`).
  - System prompt: **2,735 chars**, byte-identical every call (~684 tokens at 4
    chars/token).
  - Tokens for the whole backlog: prompt ≈ **5,048,981** (no cache) / **933,490**
    (system-prefix accounted once) at 4 chars/token; output ≈ **722,400**
    (`EST_OUT_TOKENS_PER_ROW = 120`, itself an estimate pending the first real run's
    `usage.tokens_out / rows`).
  - Local wall-time projection in the receipt: **51–261 hours** total depending on
    model (Qwen3-30B-A3B) and whether prefix caching applies — worse than the
    "4.9–10 h" figure CLAUDE.md cites once prefill without a cache is counted honestly.
  - `KAPPA_ROWS = 50` is the inter-rater control actually run today (spec asks 500);
    this is the natural home for a cloud-vs-local 200-row overlap (§4).
- **News registry already has 26 sources** (`backend/data/news_sources.yaml`, not the
  "17" in the task brief, which is stale), including several the brief asked to check:
  `alpaca_benzinga_news` (Benzinga via Alpaca), `sec_edgar_8k_current_atom` (EDGAR 8-K
  current-events feed), `finnhub_company_news`. Plus Google News RSS ×10 locales, Nikkei,
  Reddit ×2, Quantocracy, AKShare ×2, HKEXnews, `finnhub_recommendation_trends`,
  `yfinance_recommendations`, Wikipedia pageviews, `greenhouse_lever_ashby_ats` (hiring
  signal). GDELT DOC 2.0 confirmed present. **Not present**: Exa, Tavily, Brave Search,
  Marketaux, Finnhub's general `/news` (market-news) endpoint — only `company-news` is
  registered. See §7.

## 1. NVIDIA NIM / build.nvidia.com

- **Base URL**: `https://integrate.api.nvidia.com/v1`, OpenAI-compatible
  (`OpenAI(base_url=..., api_key=...)` works with the `openai` SDK ≥1.0).
  [theneuralbase.com](https://theneuralbase.com/nvidia-nim/learn/advanced/openai-client-direct/)
- **Models served**: catalogue of 100+ open models — full Llama 3.1 family (8B/70B/405B),
  NVIDIA's own Nemotron series (Nemotron Nano 9B V2, Nemotron Super 49B, Llama-3.1-
  Nemotron-70B/Ultra-253B), Qwen, Mistral, DeepSeek, GLM, MiniMax, Gemma.
  [sidsaladi.substack.com](https://sidsaladi.substack.com/p/free-llm-api-nvidia-nim),
  [dev.to](https://dev.to/turacthethinker/i-got-access-to-136-ai-models-for-free-nvidia-nim-api-deep-dive-111o).
  **DeepSeek-R1 itself specifically confirmed hosted**: not independently verified from a
  primary NVIDIA page in this pass — one secondary source names a competitor (MiniMax
  M2.7) as benchmarked against R1 rather than confirming R1 is on the catalogue; treat
  "R1 on NIM" as **plausible, not confirmed** and check `build.nvidia.com/models` live.
- **Free tier**: no credit card, sign up via the NVIDIA Developer Program. Reported
  figures conflict across sources — some cite 1,000 credits at signup (up to 5,000
  total), others say credit caps were removed and only the **40 requests/minute** rate
  limit remains (200 RPM as a stated upgrade tier).
  [freellm.net](https://freellm.net/providers/nvidia-nim),
  [decodethefuture.org](https://decodethefuture.org/en/nvidia-nim-api-pricing-limits-guide/),
  [yangmao.ai](https://yangmao.ai/en/providers/nvidia-build/free-tier/). **Not found**:
  one authoritative current number — NVIDIA's own account dashboard is the only
  reliable source; the AAT `.env` already carries `AAT_NVIDIA_API_KEY` (non-empty) so
  this is checkable directly rather than inferred from blogs.
- **JSON / structured output**: NIM's OpenAI-compatible endpoints support
  `/v1/chat/completions` with streaming, JSON mode, and function calling.
  [apirank.vip](https://apirank.vip/tutorials/nvidia-nim-api-review/). Per-model support
  for strict `json_schema` (vs. loose `json_object`) is **not confirmed** — varies by
  the underlying model's own template; check per model before depending on strict mode.
- **Training cutoffs per model**: **not found** as a consolidated NVIDIA-published
  table for this pass — cutoffs are the underlying model vendor's own (e.g. Llama
  3.1's is Meta's, Nemotron's is NVIDIA's). Pull per-model from each vendor's card
  before running L3 lookahead probes.
- **Paid-tier price examples** (per 1M tokens, from third-party trackers, **not** an
  official NVIDIA price list — confirm at build.nvidia.com before billing against
  these): Nemotron Nano 9B V2 ≈ $0.04/1M input; Nemotron Super 49B ≈ $0.10/1M input,
  $0.40/1M output; Llama-3.1-Nemotron-70B-Instruct ≈ $1.20/1M (both directions);
  Llama-3.1-Nemotron-Ultra-253B ≈ $1.60/1M.
  [deepinfra.com](https://deepinfra.com/blog/nvidia-nemotron-api-pricing-guide-2026),
  [tokencost.app](https://tokencost.app/blog/nvidia-nemotron-3-super-pricing). NVIDIA
  itself does not publish one universal per-token rate card; pricing is
  model-by-model and changes; the hosted catalogue is explicitly positioned as
  free-for-prototyping with production metered separately.
  [costbench.com](https://costbench.com/software/llm-api-providers/nvidia-nim/)

**Bottom line for L2**: at 40 RPM, 6,020 calls take **~150 minutes (2.5 h)** minimum —
regardless of model choice, since the free tier is rate- not token-limited — which beats
every local wall-time estimate and is free if the credit cap doesn't bind. The credit-cap
uncertainty above is the one thing to verify before counting on it for the whole backlog.

## 2. Featherless.ai

- **Plans** (flat monthly, unlimited tokens, concurrency-gated): Basic $10/mo (models
  ≤15B, 2 concurrent slots), Premium $25/mo (thousands of models, 4 concurrent slots),
  Scale $75/mo (concurrency tiered by model size, e.g. 8 concurrent for smaller
  models), Agent Standard $100/mo, Agent Pro $200/mo.
  [featherless.ai/docs/plans](https://featherless.ai/docs/plans),
  [aimultiple.com](https://aimultiple.com/flat-rate-llm-api). No tokens-per-minute cap —
  the constraint is concurrent in-flight requests, not throughput, so wall time scales
  with `n_rows / concurrency × latency_per_call` rather than with tokens billed.
- **Catalogue**: ~30,000 models. Qwen 3 (9.9k model variants/finetunes indexed), Qwen 2
  (8.8k), Llama family (2/3/3.2, thousands each), Mistral (3.2k), DeepSeek variants
  including the full R1 (671B MoE, DeepSeek V3 architecture) and its distilled
  1.5B–70B variants. [featherless.ai/models](https://featherless.ai/models),
  [featherless.ai/blog/best-open-source-llms-2026](https://featherless.ai/blog/best-open-source-llms-2026).
  Qwen3-30B-A3B (our local model) is very likely in-catalogue given Qwen3 coverage, but
  **not individually confirmed by id** in this pass — check `featherless.ai/models`
  before assuming parity with the local weights.
- **OpenAI compatibility**: fully OpenAI-compatible `/v1/chat/completions`, plus an
  Anthropic-compatible `/v1/messages` endpoint.
  [featherless.ai/blog/running-open-source-llms-in-popular-ai-clients-with-featherless-a-complete-guide](https://featherless.ai/blog/running-open-source-llms-in-popular-ai-clients-with-featherless-a-complete-guide).
- **Structured outputs / JSON**: **not found** in this pass — Featherless's docs were
  not directly reachable with search; since it proxies open-weight models through an
  OpenAI-shaped API, JSON-mode fidelity is whatever the underlying model does with
  `response_format`, likely `json_object` only (no vendor-level schema enforcement
  layer reported anywhere found). Verify empirically with one row before batching.
- **Cutoffs**: per-model, same caveat as NIM — not a Featherless-specific figure.

**Bottom line for L2**: Premium ($25/mo, 4 concurrent, unlimited tokens) types the whole
6,020-row backlog for a flat $25 regardless of token count, at whatever the model's
real latency allows across 4 concurrent slots — likely the **worst $/row choice** here
since DeepSeek's metered price for the same job is $1–2 (§4), but Featherless is the
one place that can run the **exact same Qwen3-family weights** as the local server on
someone else's GPU, which matters more for the reproducibility-arm question than for
cost.

## 3. DeepSeek pricing and behaviour today

Fetched directly from `api-docs.deepseek.com/quick_start/pricing` (2026-09-13).
Both `deepseek-chat`/`deepseek-reasoner` aliases were retired 2026-07-24 15:59 UTC in
favor of `deepseek-v4-flash` / `deepseek-v4-pro`
([digitalapplied.com](https://www.digitalapplied.com/blog/deepseek-api-alias-retirement-july-24-migration-2026)) —
**this repo's `_DEEPSEEK_MODEL` config default (`deepseek-chat`) is likely a dead alias
and should be checked/updated before the next real run**, separately from this task.

| | Input, cache hit | Input, cache miss | Output |
|---|---|---|---|
| `deepseek-v4-flash` (off-peak) | $0.003 /1M | $0.15 /1M | $0.60 /1M |
| `deepseek-v4-flash` (peak) | $0.006 /1M | $0.30 /1M | $1.20 /1M |
| `deepseek-v4-pro` (off-peak) | $0.022 /1M | $0.66 /1M | $1.98 /1M |
| `deepseek-v4-pro` (peak) | $0.044 /1M | $1.32 /1M | $3.96 /1M |

Peak hours: 01:00–04:00 and 06:00–10:00 UTC, Monday–Friday
([api-docs.deepseek.com/quick_start/pricing](https://api-docs.deepseek.com/quick_start/pricing)).
Context window on flash: 1M tokens. **Knowledge cutoff: not stated on the pricing
page** — third-party trackers say ~2024-07 for the retired `deepseek-chat` alias
([aiknowledgecutoff.com](https://aiknowledgecutoff.com/deepseek/deepseek-v3.1-terminus));
this repo's own `night_l3_lookahead.py::MODEL_CUTOFFS` already carries `deepseek-chat:
2024-07-01, confidence LOW` and `deepseek-reasoner: None, confidence LOW` — consistent
with what's found here, no update warranted from this pass.

- **Rate limits**: DeepSeek does not publish a fixed RPM; effective throughput is
  concurrency-based and adjusts to account traffic. Reported concurrency ceilings:
  `deepseek-v4-flash` ~2,500 concurrent, `deepseek-v4-pro` ~500 concurrent
  ([wavespeed.ai](https://wavespeed.ai/blog/posts/blog-deepseek-v4-rate-limits/)) — not
  an official page, treat as indicative.
- **JSON mode**: `response_format: {"type": "json_object"}` plus the literal word
  "json" somewhere in the prompt; only `json_object`, **not** OpenAI's stricter
  `json_schema` structured outputs
  ([api-docs.deepseek.com/guides/json_mode](https://api-docs.deepseek.com/guides/json_mode/),
  [milvus.io](https://milvus.io/ai-quick-reference/does-deepseekv32-support-structured-json-mode)).
  `night_l2_typed_events.py`'s validator is already `"hand"` (per the run receipt),
  i.e. not relying on schema enforcement — compatible either way.
- **The Chinese code-switch problem**: already guarded centrally
  (`_LANGUAGE_PIN` + `_refuse_non_english`, §0) — nothing new to add for DeepSeek
  specifically, but a **new provider (NIM/Featherless) call site must inherit the same
  pin and refusal**, not re-derive it (see §6).

## 4. The plan to type 6,020 rows today for under $5

**Headline: DeepSeek alone, metered, costs well under $5 for the whole backlog —
cost was never the constraint; wall time and GPU risk were.**

Using the repo's own token estimate (5,048,981 prompt tokens no-cache /
933,490 system-prefix-cached-once; 722,400 output tokens; §0), on
`deepseek-v4-flash` off-peak:

- **No caching credited at all** (conservative — assumes DeepSeek's own disk cache
  never hits, which is unlikely for 6,019 repeats of a byte-identical 2,735-char
  prefix run back-to-back): 5,048,981 × $0.15/1M + 722,400 × $0.60/1M ≈ **$0.76 + $0.43
  = $1.19** off-peak (≈$2.38 at peak rates).
- **System prefix credited as cache-hit after the first call** (the realistic case —
  DeepSeek's context caching is automatic and keyed on exact-prefix match): system
  tokens ≈ 684 × 6,020 ≈ 4.12M, of which ~4.12M are cache-hit after row 1
  (4,116,996 × $0.003/1M ≈ $0.012) and unique per-row user tokens ≈ 933,490 total
  (933,490 × $0.15/1M ≈ $0.14 cache-miss) + output 722,400 × $0.60/1M ≈ $0.43. Total
  ≈ **$0.59** off-peak.

Either way, **the whole 6,020-row backlog costs $0.60–$2.40 on DeepSeek**, an order of
magnitude under the $5 budget, and the steady-state ~800 rows/day costs **$0.08–$0.32/
day** — call it $2–10/month. This changes the framing of the roadmap's own numbers:
CLAUDE.md's cited local wall time (4.9–10 h) undercounts prefill, and the honest local
range is 51–261 h (§0); DeepSeek's own dollar cost for the same job is trivial by
comparison. **The bottleneck was never $ — it was GPU wall time and TDR risk on an
unattended machine (CLAUDE.md rule 9's incident), which cloud API calls sidestep
entirely.**

**Recommended split**:
- **Backlog (6,020 rows, today)**: DeepSeek `deepseek-v4-flash`, off-peak hours if the
  job can be scheduled (01:00–04:00 / 06:00–10:00 UTC are *peak*, so run **outside**
  those windows for the cheaper off-peak rate — i.e. UTC 10:00–01:00 or the Sat/Sun
  windows entirely off-peak per the docs). With N concurrent workers (repo already
  measured 0.379 s/call sequential on local Qwen2.5-7B for comparison; DeepSeek's own
  per-call latency was not measured in this pass — **not found**, budget for
  measurement on the first 50-row run), even N=10 concurrent finishes in well under an
  hour; DeepSeek's ~2,500-concurrency ceiling on flash is not remotely a constraint at
  this volume.
- **Steady state (~800 rows/day)**: same provider, same model — trivial marginal cost,
  no reason to split providers for volume this small.
- **Local model kept as the reproducibility arm**: type a **200-row overlap set**
  (Murat's number; the spec's own `KAPPA_ROWS_SPEC = 500` is the fuller target, `50` is
  what today's run affords) with **both** DeepSeek and the local Qwen server, at the
  same two prompt hashes the repo already computes (`prompt_hash_A`/`prompt_hash_B`),
  and score agreement with the existing kappa protocol
  (`event_type`: unweighted Cohen's κ, 40-way; `direction`/`magnitude_bucket`: weighted
  κ, linear weights over the ordinal scale) against the contract's **κ ≥ 0.61** gate
  (`night_l2_typed_events.py`'s own kappa machinery, reused, not reinvented — it
  already runs cloud-vs-local as "prompt A vs prompt B"; here it becomes "provider A
  (local) vs provider B (DeepSeek)" on the identical 200 rows). This is cheap: 200
  rows × ~155 s/row locally ≈ 8.6 h worst case, or run only the 200-row overlap
  locally overnight rather than the full 6,020.

## 5. Lookahead Propensity per cloud model

- **DeepSeek `deepseek-v4-flash`/`deepseek-v4-pro`**: cutoff not officially published;
  the repo's own LOW-confidence estimate for the retired `deepseek-chat` alias is
  **2024-07-01** (`night_l3_lookahead.py::MODEL_CUTOFFS`). If the flash/pro rename is a
  genuinely newer base model (V4 vs V3), the cutoff may have moved forward and **is not
  yet re-verified** — before running any L3 probe on `deepseek-v4-flash`, re-derive the
  cutoff (the paper's own method: a date-only recall probe under an accuracy/cutoff
  split) rather than reusing the V3-era estimate.
- **NIM/Featherless-hosted open models** (Llama 3.1, Nemotron, Qwen3, etc.): cutoffs are
  each vendor's own and were **not consolidated in this pass** — pull from each model's
  card before running L3.
- **Corpus split**: the 2015 backfill (Alpaca/Benzinga, 3,799 rows per the
  `document_date` docstring's own account) is **pre-cutoff for every candidate model**
  by a wide margin (9+ years) — every one of those reads owes L3. The 2025–26 live
  rows straddle each model's cutoff and are the split the paper's design actually needs
  (pre- vs post-cutoff inside the same panel, like R2's PANEL-A already does).
- **50-row leakage probe, concrete design** (mirrors `night_l3_lookahead.py`'s existing
  `LAP_PROBE_SYSTEM`/`LAP_PROBE_USER` almost verbatim, applied to the 2015 rows
  specifically): sample 50 of the 2015-backfill documents, run the **unmasked recall
  probe** ("For {ticker} in {month}, state what you recall happened to its stock price
  that month relative to the market... you are given no documents") against DeepSeek
  and against whichever NIM/Featherless model is chosen, score `LAP_i` with the
  existing `lap_of()` function (confidence-when-correct, zero otherwise), and compare
  the **typed-event confidence field** on those same 50 documents' *actual* L2 read
  (which DOES see the document) against `LAP_i` — a typed-row confidence that tracks
  `LAP_i` rather than tracking the document's own evidence span is the signature the
  paper's β2/β3 test is built to catch, applied here as a cheap pre-check before
  spending the full backlog's money on a contaminated model. This is new work relative
  to the existing L3 job (which grades *forecasts*, not typed-event extractions) —
  flag it as its own small addendum to L3 rather than silently folding it in, per the
  "new mechanism arrives as its own experiment" rule.

## 6. Provider abstraction — minimal change to `llm_analyzer.py`

Today `_call_llm` is a two-branch if/elif hardwired to `_get_provider()`'s single
active choice (§0). The minimal change that doesn't disturb the sole-provider
declaration test's *intent* (only its scope):

1. **Add a `provider: str | None = None` kwarg to `_call_llm`** (and to any public
   helper that wants to pin one). `None` keeps today's behaviour (`_get_provider()`
   resolves it, DeepSeek). An explicit value (`"nvidia_nim"`, `"featherless"`) routes to
   a new lazy-init client function (`_get_nvidia_client()`, `_get_featherless_client()`)
   built the same way `_get_openai_client()` is — `OpenAI(api_key=..., base_url=...)`,
   since both are OpenAI-compatible (§1, §2).
2. **The language pin and refusal call travel unchanged.** `system_prompt +
   _LANGUAGE_PIN` and `_refuse_non_english(provider_name, purpose, text)` are already
   provider-parametrized (they take a provider string for telemetry) — extending them
   to new provider names is a one-line addition to whatever accepts the provider
   string, not a new mechanism. This is the exact bug CLAUDE.md warns about
   (`explain_move.py` fixed the language pin at its own call site instead of
   centrally) — a new provider must NOT get its own bespoke pin.
3. **Cost accounting**: `_record()` already takes `provider` and `model`; add a
   `PROVIDER_COST_PER_1M` table (input/output, cache-hit where applicable) keyed by
   `(provider, model)` next to `_llm_cfg`, and have `llm_telemetry.extract_usage`
   multiply through — mirroring how DeepSeek's usage block is already parsed. New
   provider clients report usage in the same OpenAI `usage.prompt_tokens` /
   `usage.completion_tokens` shape, so `extract_usage` needs a provider-name branch
   added, not a rewrite.
4. **Spend guards** (`_acquire_call_budget`, the billing breaker) should key on
   `(provider,)` rather than being global, so a NIM free-tier RPM cap tripping doesn't
   silently disable DeepSeek, and vice versa — currently `_spend_state` is one shared
   dict; splitting it per-provider is the one structural change beyond "add a branch."
5. **The declaration test changes shape, not spirit**: rename
   `SOLE_PROVISIONED_PROVIDER` → `PROVISIONED_PROVIDERS: dict[str, bool]` (or a
   frozenset of names with non-empty keys), and change
   `test_llm_provider_declaration.py`'s assertions from "`active` equals the one sole
   name" to "`active ⊆ PROVISIONED_PROVIDERS` and every key with a real key is in
   `configured`". Keep a `PRIMARY_PROVIDER` (still `"deepseek"`, since it remains the
   cheapest and already-live default for anything not explicitly routed elsewhere) so
   existing callers that don't pass `provider=` keep today's behaviour byte-for-byte —
   this is the same "guards derive their inputs or refuse" principle CLAUDE.md states,
   applied to "which providers exist" instead of "which one is sole."
6. **Typed-row schema addition** (`night_l2_typed_events.py`'s output row and
   `event_extraction.py`'s writer): add `model_id` (e.g. `"deepseek-v4-flash"`),
   `provider` (e.g. `"deepseek"`, `"nvidia_nim"`, `"local_gguf"` — the receipt already
   uses `"backend": "local_gguf"` at the job level; push it to row level too), `cutoff`
   (the `MODEL_CUTOFFS` value used, with its `confidence` tag carried through — not
   just the date), and `lookahead_propensity_ref` (a pointer — run id + row index — into
   the L3/§5-probe output that covers this row's document-date × model pair, `null`
   until that probe has run for this model). This makes "which rows still owe an L3
   result" a query over the typed-events file itself rather than a fact someone has to
   remember.

## 7. News beyond the registered 26 sources

**None of NVIDIA NIM, Featherless, or DeepSeek offer web search or news retrieval as a
product** — all three are pure inference APIs (chat completions over models you name);
none has a search/retrieval endpoint. Say so plainly, as asked: **not applicable**, and
no amount of prompting turns an inference-only API into a news feed with PIT provenance.

Registered already (§0), so **not gaps**: Alpaca/Benzinga, GDELT DOC 2.0, SEC EDGAR
8-K, Finnhub `company-news`, Google News RSS ×10 locales, Reddit, Quantocracy, AKShare,
HKEXnews, Wikipedia pageviews, Greenhouse/Lever/Ashby.

**Actually-missing, cost/limits/PIT-safety as found today**:

| Source | Cost | Limits | PIT-safety | Verdict |
|---|---|---|---|---|
| **Marketaux** | Free tier: 100 req/day, no card. Paid tiers add history/filters (price not itemized in this pass — **not found**). | 100/day free. | **Not confirmed** — no first-seen/ingestion stamp documented in this pass distinct from the article's own publish time; would need the same `index_state` vs `native_stamp` classification the registry already applies to every source before it could carry `label_source: true`. [marketaux.com/documentation](https://www.marketaux.com/documentation) | Cheap to add as tier-3 (non-labeling) breadth; **not yet PIT-classified** — do that before any use beyond browsing. |
| **Finnhub general `/news` (market-news)** | Same account as the already-registered `finnhub_company_news` — likely free-tier-includable (60 calls/min free). | 60/min free tier. | Same PIT question as `finnhub_company_news`, whichever grade that source already carries in the registry — check `backend/data/news_sources.yaml` for `finnhub_company_news`'s `pit_grade` and mirror it. | **Cheapest true gap to close** — same key already provisioned (`AAT_FINNHUB_API_KEY`), same vendor, near-zero marginal integration cost. Recommend **first**. |
| **SEC EDGAR full-text search** (`efts.sec.gov`, distinct from the already-registered 8-K *current-events* atom feed) | Free, no key; requires a `User-Agent` header with name+email. | 10 req/sec hard cap across all EDGAR domains (data.sec.gov + efts.sec.gov + www.sec.gov combined), 10-min IP block on breach. [tldrfiling.com](https://tldrfiling.com/blog/sec-edgar-api-rate-limits-best-practices) | `native_stamp` in spirit (SEC's own filing timestamp) — same PIT grade class as the already-registered 8-K feed, but full-text search covers **all filing types** (10-K/10-Q/S-1/etc.), not just 8-Ks. | **Second gap to close** — free, no key, PIT-clean by construction, and widens coverage past just current-events 8-Ks. Recommend **second**. |
| **Alpaca news (Benzinga)** | Already registered (`alpaca_benzinga_news`) — restating for completeness per the brief's own list: free with the existing Market Data subscription; 200 calls/min on Free plans; up to 250 full articles + 900 real-time headlines/day. [alpaca.markets](https://alpaca.markets/blog/introducing-news-api-for-real-time-fiancial-news/) | Already in use. | Already classified in the registry. | **Not a gap.** |
| **Brave Search API** | Free plan (5,000 queries/mo) was **removed Feb 2026**; new accounts now get $5 signup credit, then metered. [brave.com/learn/best-search-api-2026](https://brave.com/learn/best-search-api-2026/) | Metered post-credit. | Web search results carry no first-seen guarantee of their own — would need the registry's own crawl-timestamp discipline, same as any general web search. | Lower priority — general web search, not finance-native, and no longer meaningfully free. |
| **Exa** | Search-with-contents $7/1,000 requests; Deep $12/1,000; reasoning variant $15/1,000 (2026-03 repricing). [menuagentic.com](https://menuagentic.com/blogs/brave-vs-exa-vs-tavily-vs-parallel-search-apis) | Credit/request-based, multi-factor billing (depth, crawled pages). | Same as Brave — general web retrieval, no PIT stamp of its own. | Useful for one-off qualitative research, not a systematic PIT-safe news feed at this price. |
| **Tavily** | PAYG $0.008/credit; monthly plans $0.005–$0.0075/credit; Bootstrap $100/mo for 15,000 credits. [buildmvpfast.com](https://www.buildmvpfast.com/api-costs/ai-search) | Credit-based. | Same caveat as Brave/Exa. | Same verdict as Exa — not a first pick for the labeling pipeline. |

**Recommended two to add first**: **Finnhub `/news` general market feed** (zero new
key, zero new vendor relationship, likely free-tier-includable) and **SEC EDGAR
full-text search** (free, no key, PIT-clean, widens filing-type coverage past 8-Ks).
Both integrate through the existing `news_registry.py` contract with no new
infrastructure — the actual work is one new `NewsSource` YAML row each plus a parser,
not a new subsystem.

## 8. What would change the roadmap

The dollar cost of typing the backlog was never the blocker — DeepSeek alone clears the
whole 6,020-row backlog for **$0.60–$2.40**, and the roadmap's framing of this as a
GPU-hours problem (CLAUDE.md's "4.9–10 h" / the TDR-crash history) is solving the wrong
constraint. **The one change worth making today is routing `L2_typed_events` through
DeepSeek instead of waiting on the local GPU**, which retires the TDR-crash risk
entirely and finishes the backlog in under an hour of wall time instead of 2–11 days.
That requires the minimal provider-parametrization in §6 (DeepSeek is already wired —
only the row-level `provider`/`model_id`/`cutoff` fields need adding, not a new
client), plus the 200-row local-vs-cloud kappa check (§4) to confirm the swap doesn't
silently degrade label quality, plus one fresh L3 lookahead probe on whichever DeepSeek
model id actually gets used (§5) before the 2015 backfill rows are trusted. NVIDIA NIM
is the second-best option if DeepSeek's language-refusal rate or kappa disagreement
turns out too high on the 200-row check — it's free at 40 RPM (2.5 h for the whole
backlog) with a wider model catalogue to swap into if Qwen/DeepSeek-family agreement is
poor. Featherless is not cost-competitive for this job (flat $25/mo vs. DeepSeek's ~$1)
and belongs only in the reproducibility-arm conversation, not the production path.
