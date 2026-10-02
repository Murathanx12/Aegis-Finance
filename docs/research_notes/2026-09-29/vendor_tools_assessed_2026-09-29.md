# Vendor tools assessed — 2026-09-29

Research only. Licence: `PRODUCT_EXPERIMENT` research note — nothing here is a
`RESEARCH_CLAIM`, and nothing here recommends itself onto the TIER 1 roadmap by
default (CLAUDE.md: "new work is not roadmap work by default"). Every number is
from a vendor's own current page or an independent paper, cited inline; anything
that could not be confirmed from a primary source is marked **UNVERIFIED**.
Triggered by Murat, 2026-09-28: *"I think we are under utilizing openclaw ...
use deepseek api as you wish and nvidia api. do you think bob from ibm is
useful, or any nvidia, microsoft, meta, amazon, oracle things we need to set up
and build."*

Context: one HKU student, one Windows laptop with a local graphics card, an on-device accelerator and
limited free memory (specifics in the local_pc record). Paid today: DeepSeek API (cheap, the only paid
LLM), Railway (~$60 last month, being reduced), news subscriptions. An NVIDIA
API key exists and is underused. OpenClaw runs locally.

Five general-purpose research agents did the web research in parallel (one per
vendor cluster: IBM · NVIDIA+Meta · Microsoft · Amazon+Oracle · Google+Others),
each instructed to cite primary sources and apply the same skepticism this note
applies below. Findings are compiled and cross-checked here, not re-verified
line by line — treat any single figure as re-checkable at the cited URL before
billing or planning against it.

---

## What we already evaluated (do not repeat)

| Item | Verdict | File |
|---|---|---|
| NVIDIA NIM (build.nvidia.com) | Already wired and paying off — free embeddings (`nemotron-3-embed-1b`) and free cluster labelling in production use; **underused beyond that**, which is this note's actual finding for NVIDIA | `docs/BUILD_2026-09-08_R3_ARCHETYPES.md`, `docs/BUILD_2026-09-07b_L_FREE_INFERENCE.md`, `docs/research_notes/2026-09-13/research_cloud_llm_readers.md` |
| RAPIDS | Judged not worth it on Windows | prior session, reaffirmed in this task's own brief |
| Microsoft Qlib | NOT ADOPTED — ships no free US-equity data; the one useful piece (IC-decay chart shape) already extracted | `docs/research_notes/2026-09-28/outside_methods_compared_2026-09-28.md` §1.3 |
| Microsoft RD-Agent(Q) | NOT ADOPTED — validated only on OpenAI-tier reasoning models, not DeepSeek; the in-house Sonnet-research/Opus-build/adversarial-review loop already approximates it, with guardrails RD-Agent(Q) lacks | same, §1.4 |
| Kronos (price TSFM, MIT, not IBM/Amazon/Google) | **TESTED 2026-09-28, FAILED_VARIANT** — QLIKE 0.746 vs a trailing-63-day realised-vol formula's 0.415, worse on **26 of 26** held-out dates (t +12.9); ranking edge +0.06%/mo vs random, t 0.07, not significant | `docs/research_notes/2026-09-28/lane_x_experiments_2026-09-28.md` |
| Chronos/TimesFM/Moirai/TimeGPT (general TSFMs, as a class) | Independent 2026 paper (arXiv 2606.27100): on 5 US mega-caps, beat random walk in only 2 of 10 cases (Diebold-Mariano); TimesFM specifically already tried live by a different hackathon team (NorthStar), **−7.04% for the week** | `docs/EXTERNAL_2026-09-07_LANDSCAPE_WHAT_WE_MISSED.md` §B |
| TradingAgents | NOT ADOPTED — flagship Sharpe traced to a confirmed look-ahead leak (GitHub issue #203); core mechanic (LLM places the trade) forbidden by the three-licence canon | `outside_methods_compared_2026-09-28.md` §1.6 |
| QuantConnect LEAN | Adapter design already scoped (2–4 days), not built | same, §1.2 |
| mlfinlab / PortfolioLab | NOT ADOPTED — original repo now paid (£100/mo/user); in-house purged-CV/DSR/PBO already built AND stress-tested (GATE-M1, ~1.6% measured false-discovery rate) | same, §1.11 |
| Numerai MMC/TC, FinMem, AlphaAgents, NautilusTrader, alphalens/pyfolio-reloaded | Each evaluated, each NOT ADOPTED or low-priority, each redundant with something already built | same, §1.1/1.7–1.10 |
| StockBench (LLM-trading benchmark, not a tool) | Rerun recommended (&lt;1 day, still not done); its own finding — **DeepSeek-V3 ranked 11th of ~14 models** on this exact sequential-trading-decision task — is the reason this note tests NVIDIA/Azure models as a second opinion, not a reason to adopt StockBench itself | same, §1.5 |
| OpenClaw (gateway, browser control, cron, nodes, memory, skills) | Deep runtime audit already done same day (2026-09-28); eight recommended config changes not yet applied | `docs/research_notes/2026-09-28/openclaw_runtime_done_right_2026-09-28.md` |
| Prophet Arena / LLM-forecast-calibration literature | Frontier LLMs match the market on Brier, beat it on ECE, but **none reach break-even on returns**; Economics & Business was the worst category measured | `docs/research/R1_LLM_FORECAST_CALIBRATION_2026-08-08.md` |
| ChromaDB/FAISS/Pinecone | "REFUSED at this corpus [size]" in one prior prior-check pass — a signal this note's FAISS verdict below independently reaches again from a different angle | `docs/research/AI_PANEL_2026-07-25C.md` |
| IBM Bob / watsonx.ai / Granite / TinyTimeMixers / watsonx Orchestrate | **NET NEW** — zero hits anywhere in `docs/` or the Optimus memory folder before this note | grep pass, this note |
| Azure for Students / AI Foundry / GitHub Student Pack / Foundry Local / DirectML | **NET NEW** | grep pass |
| AutoGluon, Amazon Chronos-Bolt specifically, AWS Educate/Bedrock/Free Tier | **NET NEW** (generic "Chronos"/"AWS" hits found were the Google-paper's TSFM class and unrelated AWS mentions, not these specific products) | grep pass |
| Oracle Cloud Always Free | **NET NEW** — the 60 "Oracle" hits in `docs/` are all false positives (Oracle Corp as a stock, Oracle Hospitality as a competitor, "oracle" meaning ground-truth/prediction-market oracle) | grep pass |
| Google TimesFM as a *product* (pricing/free tier), Gemini API free tier, Colab/Kaggle compute, GCP student credits | **NET NEW** as vendor-programme research; TimesFM's *forecasting quality* was already covered as one of the four TSFMs above | grep pass |
| Groq, Cerebras, Cloudflare Workers/D1, Modal, HF Spaces/ZeroGPU | **NET NEW** — no real in-house evaluation found | grep pass |
| Playwright as a browser driver vs OpenClaw's, specifically for this week's reader failures | **NET NEW comparison** — Playwright itself was previously only discussed as an MCP tool, never benchmarked against OpenClaw for this job | grep pass |

---

## 1. IBM

**Bob.** IBM's current "Bob" is an AI-first IDE / coding-and-modernization agent
covering the full SDLC (plan, code, test, deploy, and specifically legacy
modernization — COBOL, RPG, Java) with multi-model routing across Claude,
Mistral, and IBM Granite. GA since **2026-04-28**. Cloud SaaS only (`bob.ibm.com`),
no on-prem today. 30-day free trial, then paid: **Pro** (50 "Bobcoins"/mo),
Pro+, Ultra, **Enterprise** (~$500/mo per "RU," clients billed ~$20/user/mo).
No perpetual free tier. **Use here: none** — it is an enterprise
coding/legacy-modernization agent; this codebase is not COBOL/mainframe work,
and Claude Code already fills the coding-assistant role. **Effort**: ~1h if
curious. **Risk**: enterprise ToS, Bobcoins billing lock-in — moot given no fit.
**Verdict: NOT FOR US** — a paid enterprise SDLC/modernization agent with no
capability this project needs that it doesn't already have.

**watsonx.ai.** IBM's model-hosting/tuning/agent platform for Granite, Llama,
Mistral, DeepSeek and others. **Lite (free)**: 300,000 tokens/mo, 20 Compute
Usage Hours/mo, 100 docs/mo text extraction. **Essentials**: pay-as-you-go.
**Standard**: $1,110/mo flat (2,500 CUH). Cloud only. **Use**: marginal — the
Lite tier is real but far too small for nightly research volume, and DeepSeek
is already cheaper and already integrated. **Effort**: 1–2h to test.
**Risk**: IBM Cloud account lock-in, data leaves the machine. **Verdict: NOT
FOR US** — free tier is real but not big enough to matter next to DeepSeek.

**Granite models.** Open-weight, Apache 2.0, on Hugging Face
(`ibm-granite/*`). 2B/8B dense variants fit the local graphics card comfortably at
4-bit/8-bit GGUF, the same class as the models already run locally via
llama.cpp (Qwen2.5-7B, Qwen3-30B-A3B). IBM's own reported MMLU (65.5 for the
8B) is a **self-reported eval**, not independently verified — treat as
marketing until tested. **Use**: a possible offline/no-API-cost fallback LLM.
**Effort**: 2–3h to download and smoke-test one variant. **Risk**: low (open
weights, nothing leaves the machine if run locally). **Verdict: TRY ONE
EXPERIMENT** — free, local, low-risk, not urgent.

**Granite TinyTimeMixers (TTM).** Free, Apache 2.0, sub-1M-to-a-few-M
parameters, runs trivially on CPU. This is the item worth being most careful
about, because it directly follows tonight's Kronos failure. **IBM's own
published benchmarks for TTM are exclusively on non-financial datasets** (ETT,
weather, electricity, traffic) — no stock/return evaluation exists from IBM
anywhere. Independent 2025–2026 literature on the *class* TTM belongs to
(architecturally analogous zero-shot time-series foundation models) is now
unambiguous and lands on the identical conclusion the Kronos test reached
tonight: Rahimikia et al. (2025) find off-the-shelf TSFMs underperform
CatBoost/LightGBM and barely beat random walk zero-shot on daily excess
equity returns; a 2026 "Forecast Collapse" paper (Wan et al.) finds
TimesFM/Chronos predictions collapse to near-flat on 1,000 equities' *returns*
specifically (while the same models forecast trading *volume* fine — the
failure is return-specific, not architecture-specific); a LoRA-TimesFM equity
study finds zero directional skill over an always-up base rate. There is no
evidence, and no plausible mechanism, for TTM — smaller, less capacity,
non-financial pretraining — to do better than Kronos did. **Verdict: NOT FOR
US** — this is now a closed question across three independent papers, not an
open one; do not spend a day re-deriving a known negative.

**watsonx Orchestrate.** IBM's enterprise agent-orchestration/governance
platform. Cloud/on-prem, free trial + paid tiers (exact CUH/dollar figures for
Orchestrate specifically are **UNVERIFIED** — IBM's page names tiers without
publishing them the way it does for watsonx.ai). **Use**: none found beyond
what OpenClaw (an existing local agent gateway with browser control) already
does; Orchestrate's value-add is multi-team governance this one-person project
doesn't need. **Verdict: NOT FOR US.**

**Overall IBM verdict**: nothing is worth setting up this month except a single
bounded, free, local smoke-test of a small Granite instruct model as an
offline backup LLM. Bob, watsonx.ai, and Orchestrate are enterprise-shaped and
enterprise-priced; Granite TTM is a closed question, answered the same way
Kronos answered it tonight.

---

## 2. NVIDIA

**The NIM catalogue (build.nvidia.com), used further.** Already live in this
project for free embeddings and cluster labelling — the actual finding is that
it is underused past that.

- *A stronger reasoning model for the blinded forecasting test.* The catalogue
  serves the full Llama-Nemotron line — `llama-3.1-nemotron-nano-8b-v1`,
  `llama-3.3-nemotron-super-49b-v1.5`, `llama-3.1-nemotron-ultra-253b-v1`
  (Llama-3.1-405B derivative, 128K context), plus newer
  `nemotron-3-super-120b-a12b` / `nemotron-3-ultra-550b-a55b` (Mamba-Transformer
  MoE, 1M context) — all free via the API even though self-hosting them needs
  datacenter GPUs. StockBench (arXiv 2510.02209) — the same benchmark that
  ranked DeepSeek-V3 11th of ~14 (+0.2% return) — did **not** test any
  Nemotron model, and separately found reasoning-tuned variants do not reliably
  beat instruct variants on trading tasks (Qwen3-235B-Think had worse drawdown
  than its own Instruct sibling) — so "bigger reasoning model" is not a safe
  prior either. **Verdict: TRY ONE EXPERIMENT** — run Nemotron-Ultra-253B as a
  free second opinion alongside DeepSeek on the project's own blinded-forecast
  harness. Effort ~1–2h (same OpenAI-compatible endpoint already wired). Risk:
  data leaves the machine to NVIDIA's cloud; ToS position this as trial use,
  not licensed production without AI Enterprise.
- *Embedding + reranking for news dedup.* Beyond `nemotron-3-embed-1b`
  (already in use), NIM serves NeMo Retriever rerankers:
  `nvidia/nv-rerankqa-mistral-4b-v3` (512-token) and
  `nvidia/llama-3.2-nv-rerankqa-1b-v2` (8192-token, multilingual; deprecates
  2026-05-18 → `llama-3.2-nemoretriever-500m-rerank-v2`). This is a direct,
  currently-missing fit for news-deduplication retrieval. **Verdict: ADOPT
  NOW** — free, zero new infrastructure, same key already in `.env`.
- *Speech/transcripts.* Parakeet (`parakeet-tdt-0.6b-v2`,
  `parakeet-1.1b-rnnt-multilingual`) and `canary-1b-asr` — English plus 25
  languages, punctuation and timestamps. Usable for earnings-call transcripts.
  **Verdict: TRY ONE EXPERIMENT.**

**NIM containers run locally.** Downloadable, but sized for datacenter GPUs
(Nemotron-Ultra needs 8×H100). Nothing finance-relevant fits the local graphics card.
**Verdict: NOT FOR US** — API path only.

**TensorRT / TensorRT-LLM for the local model.** Best independent data found
(Jan/Menlo Research benchmarks) shows TensorRT-LLM 30–70% faster than
llama.cpp on a 7B int4 model — but measured on flagship desktop cards,
not on a card of the local class, and no verified benchmark at that class exists. Windows setup additionally
requires Python 3.10 only, MS-MPI, and per-GPU engine compilation (one
hobbyist repo left this "in progress" for exactly that reason). **Verdict: NOT
FOR US** — unverified gain on the local graphics card, real setup/maintenance cost.

**RAPIDS.** Already judged not worth it on Windows — not re-researched, stays
closed.

**NVIDIA finance-specific material.** Real, not just a marketing slide.
`build.nvidia.com/blueprints` lists a **"Quantitative Signal Discovery Agent"**
(open source, NeMo Agent Toolkit: an LLM proposes a signal → writes code →
backtests Rank IC on yfinance S&P 500 data → iterates — genuinely close to
what this project's own research loop does by hand), a **"Quantitative
Portfolio Optimization"** blueprint (cuOpt + RAPIDS, mean-CVaR — RAPIDS is
already closed here), and **"AI Model Distillation for Financial Data."**
**Verdict: TRY ONE EXPERIMENT** — read the Signal Discovery Agent's repo for
architecture ideas, not infrastructure; effort ~2–3h to read, not to adopt.

---

## 3. Microsoft

**Azure for Students.** $100 credit, valid 12 months, **no credit card
required** to sign up or renew annually — verified by school email; 65+
services stay free after the credit while enrolled. **Verdict: ADOPT NOW** —
trivial, free, no card, and it is the funding source for the Foundry
experiment below. Effort: 30 min.

**Azure AI Foundry model catalogue.** A hosted-inference marketplace — 10,000+
models including Claude, GPT, and DeepSeek "sold by Azure/partners," billed
per-token (serverless) or per-VM-hour. Consumed against the $100 student
credit; a **card is needed** once that's exhausted. **Use**: the credit funds
a small, bounded, comparison-only blinded-forecast run (Claude/GPT alongside
DeepSeek) to check whether DeepSeek's poor StockBench showing is
provider-specific — strictly a research read, never a production path, since
CLAUDE.md declares DeepSeek the sole provider by house rule. **Verdict: TRY
ONE EXPERIMENT** — bounded, credit-only, comparison-only; effort 2–4h.

**GitHub Student Developer Pack.** Free bundle for verified students: **free
Copilot Student** (unlimited completions + limited AI-credit chat/agent use),
free Pro-tier Codespaces, the same $100 Azure credit, $50 MongoDB Atlas
credit, JetBrains, GitHub Pro. No card. **Use**: marginal directly (Claude
Code is already the primary coding tool) but Codespaces is a spare cloud box
if the laptop's memory is maxed, and it's the cleanest path to claim the Azure
credit above. **Verdict: ADOPT NOW** — free, zero risk, treat as a bonus.
Effort: 30 min.

**Phi small models (Hugging Face).** `Phi-4-mini-instruct`: 3.8B, dense,
**MIT licence**, GGUF Q4/Q5 quantization fits comfortably on the local graphics card. No
evidence found that it beats what's already running locally (Qwen2.5-7B /
Qwen3-30B-A3B) — its edge is footprint and tool-use tuning, not demonstrated
reasoning superiority. **Verdict: TRY ONE EXPERIMENT** — mainly relevant as an
accelerator-offload candidate (below), not a reasoning upgrade. Effort: ~1h to
download a GGUF and spot-benchmark tok/s and quality vs Qwen2.5-7B.

**Windows ML / DirectML / Foundry Local (the on-device accelerator).** Foundry Local is a real,
shipping product (`winget install Microsoft.FoundryLocal`, stable
NuGet/pip packages), built on Windows ML/ONNX Runtime, targeting CPU, GPU and neural accelerators
via execution providers. **Neural-accelerator support is confirmed specifically for
Qualcomm/Snapdragon (QNN)**; hardware-optimized accelerator execution providers
are gated behind Windows 11 24H2 (build 26100)+. Whether the local
accelerator has a
working execution provider today is **UNVERIFIED** — must be checked directly
(`foundry model list` + Task Manager accelerator utilization) before crediting any
graphics-memory savings. **Use, if it works**: offload Phi-4-mini to the accelerator, freeing the
local graphics card for Qwen3-30B-A3B. **Verdict: TRY ONE EXPERIMENT** — check OS
build and accelerator vendor/EP availability first (2–3h bounded test); don't plan
around it until confirmed.

**Playwright vs OpenClaw's browser driver, for this week's actual reader
problem.** Playwright (already installed as an MCP server) drives Chromium via
accessibility-tree snapshots with no separate gateway process. For the narrow
job of loading a stable, non-paywalled page and extracting text, Playwright is
very likely **more reliable** than OpenClaw's Chrome-DevTools-MCP backend —
this week's OpenClaw failures (subprocess-tree-cleanup errors forcing full
gateway restarts, ~7 restarts in 3 hours some mornings) look like OpenClaw's
own process-supervision bug, not something inherent to browser automation that
a simpler driver would also hit. But OpenClaw's extra machinery — site
allowlists, human-pace throttling (20–90s jittered gaps), per-profile Chrome
isolation — is **not decorative**; it exists specifically to avoid
rate-limiting/blocking and to keep the automation Chrome separate from Murat's
own, and Playwright provides none of it natively. Swapping to bare Playwright
moves that policy logic into project code, it does not eliminate the need for
it. Dow Jones properties (WSJ/Barron's/MarketWatch) forbid automated access
regardless of which tool drives the browser — irrelevant to this comparison,
relevant only to which URLs either tool may touch. **Verdict: TRY ONE
EXPERIMENT** — pilot Playwright against the exact URLs OpenClaw failed/
restarted on this week; if it wins, replace only OpenClaw's browser backend
for non-authenticated free sources and keep (or port) its pacing/allowlist/
isolation layer, don't discard it. Qlib and RD-Agent(Q) stay closed per the
2026-09-28 evaluation, not re-researched here.

---

## 4. Amazon

**Chronos and Chronos-Bolt.** Chronos-Bolt is Amazon's distilled T5
encoder-decoder TSFM (direct multi-step regression, "up to 250× faster, 20×
more memory-efficient" than original Chronos per its own model card);
Chronos-2 (2025, 120M params) adds multivariate/covariate support neither
Chronos nor Bolt have. Free weights, Apache 2.0, no card; Bolt-Small (48M) /
Base (205M) run on CPU or trivially on the local graphics card. Amazon's own benchmarks are
aggregated over 27 generic GluonTS/Monash datasets — none are equity returns.
Independent evidence on real financial data already exists and reaches the
**same negative as tonight's in-house Kronos result**: Noguer i Alonso &
Pereira Franklin (arXiv, Jun 2026) benchmark Chronos/Chronos-2 on
AAPL/AMZN/GOOG/JPM/META vs a random-walk baseline and find gains "small and
sparse," concluding TSFMs are "useful practical priors," not alpha generators;
Marconi (arXiv, Jul 2025) finds classical specialized models matched or
exceeded Chronos on Treasury/FX/equity-spread forecasts. One outlier (Valeyre
& Aboura, Dec 2024) claims Chronos finds stat-arb alpha on single stocks, but
it is a single, unreplicated, pre-Bolt paper testing a *different* claim
(residual stat-arb, not directional return forecasting). **Verdict: NOT FOR
US** — no independent evidence anyone has found return-predicting signal in
any zero-shot TSFM on equities; a second TSFM test is the same experiment
Kronos already ran, not a new one. What *would* justify a future test is
Chronos-2's genuinely new multivariate/covariate mode on a narrow,
pre-registered question — a different experiment, not a Chronos-Bolt swap-in.

**AutoGluon.** An AutoML ensembler (`TabularPredictor`, stacking
LightGBM/CatBoost/XGBoost/NNs) — a **baseline tool, not an alpha source**.
Free, Apache 2.0, local, CPU or GPU. **Use**: run it over the exact feature
matrix the project's LightGBM/NN lab uses, as the "does the new architecture
actually beat a competent automated ensemble" gate before promoting anything —
directly serves the stated requirement that a new nightly-trained tabular
network must beat LightGBM. **Verdict: TRY ONE EXPERIMENT** — cheap, no
dependency risk, exactly a `PRODUCT_EXPERIMENT`-licensed one-day check. Effort
2–4h; bound with `presets='medium_quality'`/`time_limit` since `best_quality`
(bagging + multi-layer stacking) is slow/RAM-heavy on a box whose memory is often
nearly full.

**AWS Free Tier.** $200 signup credit ($100 immediate + up to $100 earned),
usable ~6 months, **card required**. Exact EC2 free-tier monthly-hour caps
were not retrievable from the fetched pages (**UNVERIFIED**). **Verdict: NOT
FOR US** as a Railway replacement — time-limited, not a durable $0 answer.

**AWS Educate.** Confirmed still live (no-card labs/badge platform), but the
current page carries **no mention of dollar credits** at all — a change from
its historical $30–100 starter-credit programme (absence noted, not an
explicit sunset statement from Amazon — **UNVERIFIED** as policy).
**Verdict: NOT FOR US** — it's training/badges now, not a credits channel.

**Bedrock.** Managed multi-vendor LLM API (Claude, Llama, Mistral, Gemma,
GPT-OSS, Nova, Cohere, and notably **DeepSeek** among others), billed per-token
or provisioned throughput. No free tier found; standard AWS card required.
Re-serving DeepSeek through Bedrock would be a redundant, likely-marked-up
path to a model already called directly. **Verdict: NOT FOR US** — new
SDK/IAM/billing surface for no clear gain, and directly against the
single-provider house rule.

---

## 5. Oracle

**Always Free (Arm Ampere A1 + the hosting question).** Permanent free tier.
Oracle's own current docs state the allowance as **1,500 OCPU-hours + 9,000
GB-hours/month**, which resolves to roughly **2 OCPUs / 12 GB total** usable
as one or two instances — smaller than the "4 OCPU / 24GB" figure widely
repeated online from 2021-2024; whether this is a real, recent reduction is
**UNVERIFIED** in this pass. A **card is required** at signup even though the
tier itself never charges without an explicit upgrade. **The decisive open
question is reliability, not the free numbers**: Oracle's Always Free Ampere
A1 tier has a widely-known history of "Out of host capacity" errors blocking
signups from actually provisioning the instance, and this session could not
pull live 2025–2026 community reports to confirm the current state
(**UNVERIFIED — must be re-checked before planning around it**). **Use, if
obtainable**: 2 vCPU / 12GB is plausibly enough to run the paper-trading loop
and the website backend at $0 instead of Railway's ~$60/month. **Verdict: TRY
ONE EXPERIMENT, strictly bounded** — one 30–60 minute signup-and-provision
attempt; abandon on repeated capacity failure rather than retry-looping, and
do not plan the Railway migration around this succeeding until an instance is
actually running.

**Oracle AI services.** Nothing relevant — OCI's AI/Generative-AI stack is
enterprise-tier and adds no capability beyond DeepSeek/NIM/HF already in use
or assessed above.

---

## 6. Google

**TimesFM.** Google Research's zero-shot TSFM; 2.5 is 200M params, Apache 2.0;
3.0 claims SOTA on fev-bench/TIME Benchmark/GIFT-Eval — all Monash/GluonTS-
style *generic* forecasting benchmarks, with no equity-return evaluation
anywhere in the repo. This is exactly the "generic benchmark ≠ trading value"
gap the already-cited independent 2026 paper (arXiv 2606.27100) measured
directly on 5 US mega-caps for this model family (beat random walk in only 2
of 10 cases) — and the same failure shape Kronos produced tonight in-house,
and TimesFM specifically already lost **−7.04% for the week** in a real
hackathon test (NorthStar). **Verdict: NOT FOR US** — the general question has
now been answered independently twice plus once in-house; a newer generic-
benchmark score from 3.0 is not new evidence for trading value.

**Gemini API free tier.** Exact RPM/TPM/RPD figures are account-specific and
not published as a flat table (viewable only in the AI Studio dashboard) —
treat any specific number as **UNVERIFIED** until read from the actual
console; confirmed limits: free Search grounding capped at 500 requests/day
(2.5) or 5,000/month (3.x). No card required for the free tier itself. **Real
flag, confirmed from Google's own terms**: on the *unpaid* tier, "Google uses
the content you submit... to provide, improve, and develop... products," and
"human reviewers may read, annotate, and process your API input and output" —
the opposite holds only on paid usage. **Use**: a free second opinion for the
project's blinded forecasting test, given DeepSeek's poor StockBench ranking —
but **only on backtested/historical prompts, never on live pre-decision
text**, given the data-use terms. **Verdict: TRY ONE EXPERIMENT**, scoped
strictly to historical data.

**Colab (free) / Kaggle Notebooks (free GPU).** Colab free: sessions "at most
12 hours, depending on availability," GPU class and idle-timeout undisclosed
by Google's own design. No card, cloud-only — the project's own bars/OHLC data
would have to leave the laptop, acceptable for public/synthetic data, not for
anything touching live positions under the project's own provenance rules.
Kaggle's widely-cited quota (~30 GPU-hrs/week, ~20 TPU-hrs/week, 9–12h session
cap) could not be confirmed from Kaggle's own docs page this session
(**UNVERIFIED**). **Verdict: TRY ONE EXPERIMENT** — only for a small,
non-sensitive fine-tune (e.g., text extraction on public news text), never
anything touching live book state. Effort 2–4h to script upload/train/
download.

**Google Cloud student credits.** The standard GCP free trial is $300/90 days
and **requires a card**. A separate `cloud.google.com/edu/students` programme
exists but its current dollar amount could not be confirmed by fetch this
session (**UNVERIFIED** — check with the HKU student email directly).
**Verdict: TRY ONE EXPERIMENT** only if the student page confirms a no-card
path; otherwise this is Murat's card decision.

---

## 7. Others (one paragraph each)

**Hugging Face.** Free accounts get only $0.10/month Inference Providers
credit (near-nothing) plus Spaces (free CPU tier) and ZeroGPU (5 min/day GPU,
up to 2 free ZeroGPU Spaces). Enough for occasional Kronos/Chronos-Bolt/
Granite-TTM demo calls, not a batch job; useful mainly for a small public demo
Space of the project itself. **TRY ONE EXPERIMENT** (public demo only).

**Groq / Cerebras.** Groq's free tier (model-dependent) is roughly 30 RPM /
14,400 RPD / 15k TPM / 500k TPD on sampled models, no card — fast enough for
bursty typed-event extraction as a release valve, not a primary swap given
DeepSeek is already cheap. **TRY ONE EXPERIMENT** (Groq). Cerebras offers only
a one-time $5 trial credit, not a standing free tier. **NOT FOR US** (Cerebras
specifically).

**Cloudflare Workers + D1.** Genuinely, permanently free: 100k requests/day
and 10ms CPU/invocation on Workers; D1 gives 5GB storage, 5M row-reads/day,
100k row-writes/day. The 10ms CPU cap rules out anything compute-heavy but is
plenty for a lightweight cron/status API — a real, free supplement (or partial
alternative) to Railway for a small public endpoint. **TRY ONE EXPERIMENT.**

**Modal.** $30/month free compute on the Starter plan; per-second GPU pricing
confirmed (T4 ≈$0.59/hr, A100-40GB ≈$2.10/hr) — the cheapest, lowest-commitment
way to run an evening fine-tune without a subscription. **TRY ONE EXPERIMENT**
— best-fit of the pay-per-second options for a short GPU burst.

**Kaggle (datasets).** Plentiful stock-price CSVs, but none point-in-time or
survivorship-bias-free per the project's own 2026-09-22 panel-bias finding.
**NOT FOR US** as a primary data source.

---

## 8. OpenClaw, used more fully

The full runtime audit already exists (`openclaw_runtime_done_right_2026-09-28.md`);
this section names the capabilities that audit found **not yet used**, each
weighed against the fact this machine holds paper-brokerage keys in `.env`.

- **Scheduled automations (`openclaw cron`) and heartbeat.** Confirmed real
  and general-purpose (persists jobs, wakes an agent-turn/command/script on a
  schedule or event trigger). **Not used** for OpenClaw's own reading jobs
  today — Aegis's own Python night-supervisor drives the reader instead, and
  that supervisor already carries bounded-retry/backoff logic OpenClaw cron
  does not replicate on its own. **Use**: worth considering only for a
  narrowly-scoped job (e.g., a single free-source pull) where Aegis's own
  supervisor logic is overkill — not as a wholesale replacement. Heartbeat's
  `notify: true` delivery path is deliberately **unused**: `channels: {}` and
  `ownerAllowFrom: []` are empty by design, preserving the post-WhatsApp-
  incident architecture (`OpenClaw → Aegis → Telegram`, never `OpenClaw →
  human` directly). **Do not** re-open that path without Murat explicitly
  deciding to.
- **Skills.** `SKILL.md` workspace skills exist as OpenClaw's documented way to
  encode "how and when to use tools," and this machine has none configured for
  OpenClaw itself. The prior 2026-09-26 research note flagged this as a
  **plausible root cause** of OpenClaw "sitting idle" — the full browser
  operating loop (open a tab inside MuratClaw, keep refs on the same tab, use
  `targetId`) currently lives only in the tool description, which a
  model-driven agent may not reliably pull in. **Use**: write one
  `<workspace>/skills/browser-automation/SKILL.md` encoding that exact loop.
  Low effort, low risk — pure documentation-as-config.
- **Memory (`memory.search.rememberAcrossConversations`).** Built-in
  SQLite-backed hybrid search across past conversations — the documented
  default for a long-running personal research agent. **Not clearly leaned on**
  today. High overlap with what Aegis already runs
  (`brain/LEARNED_<month>.md`, an ExpeL-style distillation with hindsight-safe
  retrieval) — and a second, less-governed memory path inside OpenClaw risks
  becoming exactly the "Oracle Fallacy" look-ahead vector the project's own
  R2 memory-ablation research already warned against for its own ledger
  (retrieving a past episode whose resolution wasn't knowable at decision
  time). **Recommendation**: leave OpenClaw's own memory off or minimal; keep
  `LEARNED_<month>.md` as the single governed memory system.
- **Multiple agents with different tool grants.** `tools.profile` can be
  scoped per agent (`coding` vs the implicit `full`). **Not used** — today the
  whole gateway runs the implicit `full` profile, meaning `exec`,
  `read`/`write`/`edit` (and `computer`, if ever enabled) are all *selectable*
  on a machine that holds live paper-brokerage keys, with no narrower research-
  only profile defined. This is the single most actionable, already-flagged
  risk in the runtime audit. **Use**: define a narrow "reader" profile (browser
  + `group:fs` read-only, no `exec`/`computer`) for the night-reading work, and
  set `tools.profile` explicitly instead of relying on the implicit default.
- **Downloads and file handling.** `download`/`waitfordownload` browser
  actions save to a temp root; a separate File Transfer plugin exists for
  paired nodes. **Not used** for a defined purpose today — the project has at
  least one instance of a research PDF found manually in the Downloads folder
  rather than through a managed path. **Use**: a swept, defined download
  directory for research PDFs/CSVs the reader collects, scoped well away from
  any credential-bearing path. Low-moderate effort, low risk if scoped.
- **Nodes** (paired-device capabilities: `computer.act`, camera, location,
  SMS, screen recording). The `cua-computer` plugin is **confirmed absent**
  from this machine's config, and `gateway.nodes.commands.allow` is empty.
  **No use identified** for an investing-research assistant — desktop control,
  camera, and SMS serve no job this project has. This is a **what-not-to-set-up
  item**: the runtime audit's own explicit recommendation is to keep it
  disabled given the paper-brokerage keys living on the same machine, and
  nothing in this pass changes that.

**Where "browser driver with its own guards" is the right call, and where it's
a waste.** Right call: authenticated or Google-sign-in-sensitive sessions where
a human needs to sign in once inside an isolated Chrome profile (MuratClaw),
and any page where the extra machinery (allowlist, pacing, isolation) is
actively earning its cost. Wasteful: the plain, non-authenticated, free-source
page reads that are this week's actual pain point — those are better served by
piloting Playwright (§3 above) and keeping OpenClaw's *policy layer*, not its
whole gateway-supervised Chrome-DevTools-MCP stack, in front of them.

---

## A. Free compute and credits, ranked by value

Card requirement flagged explicitly — anything needing one is **Murat's
decision**, not something to sign up for automatically.

| Rank | What | Sign-up | Needs | Card? |
|---|---|---|---|---|
| 1 | GitHub Student Developer Pack (Copilot Student, Codespaces, $100 Azure credit, $50 MongoDB Atlas, JetBrains, GitHub Pro) | education.github.com/pack | HKU school-email verification | No |
| 2 | Azure for Students ($100 credit/12mo) | azure.microsoft.com/en-us/free/students/ | School email | No |
| 3 | NVIDIA NIM (build.nvidia.com) — key already exists, just underused | build.nvidia.com (already done) | Nothing new | No |
| 4 | Groq free tier | console.groq.com | Email | No |
| 5 | Cloudflare Workers + D1 (permanently free tier) | dash.cloudflare.com | Email | No |
| 6 | Hugging Face (Spaces, ZeroGPU 5 min/day) — account already exists | huggingface.co | Nothing new | No |
| 7 | Gemini API free tier | ai.google.dev / aistudio.google.com | Google account; **flag**: free-tier data may be used for training — historical prompts only | No |
| 8 | Google Cloud student credits (amount UNVERIFIED) | cloud.google.com/edu/students | HKU school email | **Check before assuming; standard trial ($300/90d) needs one** |
| 9 | Modal ($30/mo free Starter compute) | modal.com | Email | UNVERIFIED, check at signup |
| 10 | Oracle Cloud Always Free (Arm A1, ~2 OCPU/12GB, reliability UNVERIFIED) | signup.oraclecloud.com | Email | **Yes** |
| 11 | AWS Free Tier ($200 credit, ~6 months) | aws.amazon.com/free | Email | **Yes** |
| 12 | Colab free / Kaggle Notebooks free GPU | colab.research.google.com / kaggle.com | Google/Kaggle account | No — but private data leaves the laptop |

---

## B. The five things to set up first, tied to this week's jobs

1. **NVIDIA NIM's reranker + Nemotron-Ultra-253B** — serves *two* jobs at once
   (news deduplication, and the blinded forecasting test that needs a stronger
   model than DeepSeek). Free, ongoing, the key already exists — the reranker
   is **ADOPT NOW**, the Nemotron-Ultra blinded-forecast run is **TRY ONE
   EXPERIMENT**. Highest priority because it costs nothing new to start.
2. **AutoGluon `TabularPredictor` run over the existing feature matrix** —
   serves the nightly-trained tabular-network-must-beat-LightGBM job directly,
   as the baseline gate before promoting any new architecture. Free, local,
   half a day.
3. **Claim GitHub Student Developer Pack + Azure for Students** — the enabling
   step (30 min, zero risk) that funds both the Azure AI Foundry blinded
   second-opinion comparison and, via Codespaces/Colab/Kaggle, a bounded
   fine-tune session for the small-model text-extraction job on data that
   isn't sensitive (public news text, not proprietary positions).
4. **One bounded Oracle Always Free attempt (30–60 minutes), with Cloudflare
   Workers+D1 as the near-guaranteed-free fallback** for at least the small
   cron/status-API slice of the hosting bill — serves the cheaper-hosting job.
   Abandon Oracle on repeated capacity failure; do not retry-loop or plan the
   Railway migration around it succeeding.
5. **Honest gap, stated plainly rather than forced**: nothing researched here
   addresses the Oct 12 Bloomberg contest's global-earnings-date need. The
   project's existing `earnings_intelligence.py` is yfinance-based and
   US-centric; none of IBM/NVIDIA/Microsoft/Amazon/Oracle/Google's products
   researched in this note are a global corporate-earnings-calendar data
   source. That is a data-source research question, not a compute/LLM-vendor
   one, and belongs in a separate note rather than a bad-fit vendor pick here.

---

## C. What not to set up, and why

- **IBM Bob, watsonx.ai, watsonx Orchestrate** — enterprise-priced,
  enterprise-shaped, no capability gap they'd fill for a one-person project.
- **Granite TinyTimeMixers, Amazon Chronos/Chronos-Bolt, Google TimesFM (as a
  second/third price-forecasting test)** — the general question ("does a
  zero-shot time-series foundation model contain return-predicting information
  on this project's own equity panel") is now answered, independently, at
  least three separate times (Kronos in-house tonight; Rahimikia et al. 2025 +
  "Forecast Collapse" 2026 + Noguer i Alonso & Pereira Franklin 2026 +
  Marconi 2025 on real financial data; NorthStar's real −7.04% week on
  TimesFM). Running another TSFM is the same experiment again, not a new one.
- **RAPIDS, Qlib, RD-Agent(Q)** — already evaluated, already closed, not
  re-opened by this note.
- **TensorRT-LLM, local NIM containers** — no verified gain on the local graphics card, and
  real Windows setup friction for TensorRT-LLM specifically.
- **Amazon Bedrock** — duplicates the existing DeepSeek integration via a
  markup layer, no free tier, card required, against the single-provider house
  rule for no offsetting gain.
- **AWS Educate, AWS Free Tier, and AWS Educate as a hosting answer** —
  time-limited and/or card-required; not a durable $0 hosting replacement.
- **Cerebras** — no standing free tier, one-time $5 trial only.
- **Meta Llama as a swap-in for the local model, Meta Prophet** — no verified
  reason to replace Qwen already running; Prophet is in maintenance mode
  (v1.4.0, "no new features planned") with no Meta successor.
- **Kaggle datasets as a primary data source** — not point-in-time or
  survivorship-bias-free, per the project's own measured panel-bias lesson.
- **Giving OpenClaw its own Telegram channel, enabling `cua-computer`, or
  populating `gateway.nodes.commands.allow`** — re-opens a deliberately closed
  incident (WhatsApp) and adds desktop/camera/SMS capability with no job on
  this project, on a machine that holds live paper-brokerage credentials.
