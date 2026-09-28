# Outside methods compared — 2026-09-28

Requested by Murat, via an outside reviewer's unscored "fit" ratings (Numerai
MMC 97, QuantConnect LEAN 96, Microsoft RD-Agent+Qlib 95, StockBench 90,
TradingAgents 82, FinMem 80, out of 100, no evidence shown): *"see if there
are better options, better handling, another project and methodology, compare
and rate everything over 100 and the roadmap should focus on them."*

**Licence: `PRODUCT_EXPERIMENT` research note.** Nothing here is a
`RESEARCH_CLAIM`. Every claimed number about an outside project is that
project's OWN figure or a primary-source citation, never Aegis-measured.
This note recommends nothing be added to the TIER 1 roadmap by itself —
per CLAUDE.md, "new guards/new work are no longer roadmap work by default;
add one when an actual failure shows it is necessary." Read this, then decide.

**Check-the-trials-folder pass, done first.** Before writing a single fact
sheet, this session searched `docs/`, `docs/research_notes/`, `docs/reviews/`,
`backend/services/`, `backend/tests/`, the Optimus memory folder, and the
sibling `Aegis module` TRIALS/verdicts for prior art. Result: **most of the
reviewer's six items are already researched here**, in depth, with live data
where possible:

- `docs/research_notes/2026-09-26/research_ssrn_arxiv_signals_and_oss_comparison.md`
  §3 already compares Aegis against Qlib, LEAN, freqtrade, zipline-reloaded,
  vectorbt, backtrader, FinRL, OpenBB, TradingAgents, FinGPT, ai-hedge-fund,
  Vibe-Trading, LangAlpha, and TradingAgents-CN — **live GitHub API stars/
  licence/last-push, fetched that session**, not from memory. It already
  named the ONE thing to copy from each (Qlib's IC-decay chart shape, LEAN's
  adapter design, freqtrade's single-code-path pattern) and already flagged
  TradingAgents' bull/bear/risk-manager structure against Aegis's own
  thesis-card design.
- `docs/research_notes/2026-09-26/research_value_proposition_and_competitor_ranking.md`
  already scored Numerai, TradingAgents, ai-hedge-fund, FinRL, and QuantConnect
  against Aegis on a 10-criterion rubric and found Numerai's own FUND (not
  tournament score) underperformed SPY 2023-2026 per an independent 13F-based
  analysis — a finding this note's Numerai fact sheet below independently
  reaches from different sources.
- `docs/EXTERNAL_2026-09-07_FIVE_REPOS.md` and
  `docs/EXTERNAL_2026-09-07_LANDSCAPE_WHAT_WE_MISSED.md` cover earlier rounds
  of the same exercise.
- What genuinely was **not** already in the repo: a primary-source deep-dive
  on Numerai's MMC/TC *mechanics* (as opposed to its fund performance), a
  fact sheet on StockBench (2025, post-dates the 09-26 note), FinMem,
  AlphaAgents, RD-Agent(Q) specifically (vs. Qlib generally), NautilusTrader,
  alphalens/pyfolio-reloaded, mlfinlab's current (paid) status, and Kronos.
  Those are this note's actual new contribution; the rest below restates and
  cross-checks the existing survey rather than duplicating its legwork.
- What already exists in-house that materially **overlaps the reviewer's
  Tier-0 idea** (before the fact sheets, because it reframes all six ratings):
  `backend/services/family_pool.py` (correlation-adjusted effective-N,
  `n_eff = n/(1+(n-1)ρ)`, pooling a family's monthly returns), CLAUDE.md's own
  confirmation that purged CV / DSR / PBO / Harvey-Liu are already computed
  in-house and were even measured to have ~0% gate power before recalibration
  (`README.md` overfitting-guards paragraph, GATE-M1), and per-rule
  `falsifier` + `controls` fields in `backend/services/strategy_library_ext.py`
  (a manual, one-rule-at-a-time subsumption check). None of these compute a
  generic "residual value after conditioning on the live composite," which is
  the literal MMC/TC mechanic — see §2 below.

---

## 1. Fact sheets

Each states: what it is; licence/cost; hardware/data; evidence strength
(strict); the one idea worth taking; overlap with what exists here; honest
effort in days for one person; failure mode.

### 1.1 Numerai — Meta Model Contribution (MMC) and True Contribution (TC)

**What it is.** A weekly stock-prediction tournament where thousands of
data-scientist "predictors" submit rankings on Numerai's own obfuscated
features; a stake-weighted meta-model of all submissions runs a real
market-neutral hedge fund, and each submission is scored by how much it would
move that meta-model's portfolio if it were added or removed.

**MMC's exact mechanic** (still live in payouts as of the current docs):
tie-kept-rank the submission and the meta-model, gaussianize both, regress
(orthogonalize) the submission against the meta-model, multiply the residual
by the centered live target, and average — a **covariance-of-the-residual**
score. [docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc](https://docs.numer.ai/numerai-tournament/scoring/meta-model-contribution-mmc)

**TC's exact mechanic** (announced 2022 as MMC's successor; current payout
docs list `score = corr20 + mmc20` with **no TC term** — this session could
not resolve whether TC was quietly rolled back or is scored outside the
payout formula; flagged, not resolved): the **gradient of the stake-weighted
portfolio's realized return with respect to each user's stake**, computed by
differentiating through Numerai's own convex portfolio optimizer
(`cvxpylayers`), averaged over 100 trials of 50%-stake dropout for stability.
[forum.numer.ai/t/true-contribution-details/5128](https://forum.numer.ai/t/true-contribution-details/5128)

**Assumptions this needs to mean anything**: a large, stable cross-section
scored every era (Numerai's 2021 "Super Massive" release: **679 weekly eras**,
1,050 features); thousands of quasi-independent submissions whose correlation
structure IS the meta-model being conditioned on (~13,000 unique
models/month, ~5,000-6,500 actively staked);
[nmrdash.com/articles/state-of-numerai-2026](https://nmrdash.com/articles/state-of-numerai-2026)
obfuscated, pre-standardized, stationary features so one fixed pipeline
applies across all eras without re-fitting. **No primary source gives the
exact number of stocks scored per era** — unverified, flagged.

**Licence/cost**: free to submit and build an unstaked track record; staking
uses real NMR tokens, payout/burn capped at ±5% of stake per round.

**Evidence of real net returns — strict.** Tournament CORR/MMC/TC are NOT
fund returns. Numerai's own 2022 blog post (self-reported) claimed the fund
beat AQR Market Neutral by 29.6pp cumulatively over ~2 years from 2019; **13F
filings (which exclude the short book, so cannot reconstruct a market-neutral
fund's true return) show ~$1.0-1.2B AUM** but no clean net-return number;
unverified secondary/community reporting says both Numerai funds were down
17-22% in 2023, after which Numerai stopped publishing monthly performance.
[13foresight.com/fund/numerai-gp-llc](https://13foresight.com/fund/numerai-gp-llc) ·
This independently corroborates `research_value_proposition_and_competitor_ranking.md`'s
earlier finding (2023-2026 annualized 6.2% vs SPY 21.3% per a different
13F-based analysis) from a different search this session — **two independent
passes now agree the live fund has not obviously beaten the market**, even
though the scoring TECHNIQUE is the most rigorous outcome-reweighting
mechanism surveyed anywhere in this note.

**Hardware/data**: must use Numerai's own obfuscated Parquet features (no
bring-your-own-equity-data route for the main tournament); v5.1 validation
data is 3.8GB and Numerai's own release notes warn full-feature models near
v5.0's memory ceiling will OOM on v5.1 without subsetting — a real
consideration on 32GB RAM. No GPU required; most competitive models are
CPU-trained GBDTs on tabular data.

**Idea worth taking**: the residual-after-the-composite computation itself
(§2 formalizes this for Aegis). **Overlap here**: moderate — `family_pool.py`
already does the correlation-adjusted effective-N arithmetic, `forecast_reputation.py`
already does shrinkage-weighted-by-skill pooling, but nothing computes a
signal's value net of the CURRENT live composite score. **Effort**: 3-5 days
to build a generic "conditional value" module reusing `family_pool.py`'s
variance machinery. **Failure mode**: building the module is cheap; having
enough independent date-blocks to power it is the real constraint — see §2.

### 1.2 QuantConnect LEAN (local, open source)

**What it is**: an open-source, event-driven backtesting/live-trading engine
(C#/.NET core, Python 3.11 algorithm API) that enforces a strict
"Time Frontier" against look-ahead bias and ships granular per-brokerage fill
and fee models. [github.com/QuantConnect/Lean](https://github.com/QuantConnect/Lean)

**Licence/cost**: **Apache-2.0**, confirmed on the repo `LICENSE` file.
Self-hosted CLI (`pip install lean`, Docker) is free. Cloud tiers, fetched
live from [quantconnect.com/pricing](https://www.quantconnect.com/pricing):
Free $0; Researcher $84/mo; Team $168/mo; Trading Firm $480/mo; Institution
$1,272/mo — none of which are required to run it locally.

**Hardware/data**: the free cloud backtest-node spec (2 cores, 8GB RAM, no
GPU) is comparable to a modest laptop, so a local CLI run is not
resource-bound by Aegis's hardware. It does NOT ship free US-equity data for
offline use beyond what the QC platform's paid Dataset Market provides —
running fully local means formatting Aegis's own bars into LEAN's expected
layout, a real (bounded) integration cost.

**Evidence — strict**: LEAN is an execution ENGINE, not a strategy, so the
relevant evidence is fill/slippage/corporate-action realism versus a
vectorized pandas/vectorbt engine, not "returns." Its fill-model and
survivorship-bias-free marketing claims are **vendor-stated, not
independently audited** in anything found this session. GitHub issues show
past bugs in the statistics-report layer (fixed:
[PR #3979](https://github.com/QuantConnect/Lean/pull/3979),
[#6810](https://github.com/QuantConnect/Lean/issues/6810)) — spot-check its
own performance numbers rather than trust them blindly if used as a
cross-check engine.

**Idea worth taking**: exactly the one `research_library_expansion_and_lean.md`
§2.5 already scoped — a `PythonData` custom-data adapter that replays
`top10_for_replication_<date>.json` through LEAN as a second, architecturally
independent engine to catch bugs the vectorized engine can't see itself.
**Overlap**: low by design — the whole point is architectural independence
from the existing pandas engine, so redundancy is deliberately small.
**Effort**: 2-4 days (data formatting + the adapter; the design already
exists on paper). **Failure mode**: becomes a second codebase to maintain
forever for a one-person team; a C#/.NET core is a real context-switch, and
its own statistics layer has had bugs, so it must not be trusted uncritically
as ground truth.

### 1.3 Microsoft Qlib

**What it is**: an MIT-licensed quant research platform — a point-in-time
data server, a declarative feature-expression DSL (Alpha158/Alpha360), and a
20+-model "model zoo" (LightGBM through Transformer/TFT) for factor research.
[github.com/microsoft/qlib](https://github.com/microsoft/qlib)

**Licence/cost**: MIT, free.

**Hardware/data**: ships primarily **China A-share** data; its own officially
hosted datasets are currently disabled per the repo. **No free US-equity
data ships with it** — Aegis would have to reformat its own bars into Qlib's
binary layout before any of this is usable on its actual universe. GPU is
useful for the DL models, not required for the GBDT models.

**Evidence — strict**: every headline IC/RankIC/backtest number found (e.g.
IR ~1.99, annualized return ~0.178) is the **authors' own backtest on their
own China-market splits**, evaluated inside Qlib's own engine. No
independent replication or live-money confirmation was found anywhere.

**Idea worth taking**: `qlib/contrib/report/analysis_model/...`'s
IC-decay-by-horizon chart SHAPE, already flagged in
`research_ssrn_arxiv_signals_and_oss_comparison.md` as "copy the chart shape,
not the code," into `LEADERBOARD.md`'s generator. **Overlap**: moderately
high — Aegis's own by-year/LOO-worst honesty fields already do a version of
"don't trust the aggregate," so the marginal gain is presentational, not
new information. **Effort**: <1 day for the chart; 3-5 days minimum to get
any US data into Qlib's format before the model zoo itself is usable, and
that's before validating any of its 20+ models add anything the project's
own bottleneck (one composite signal, 99.5% momentum, per
`AEGIS_STRATEGIC_INVARIANTS.md`) actually needs. **Failure mode**: the
0% demonstrated edge here is diagnosed as a SELECTOR-DIVERSITY problem, not a
model-scarcity problem — adding 20 more ML models to rank the same
momentum-dominated feature set does not address the diagnosed bottleneck.

### 1.4 Microsoft RD-Agent(Q)

**What it is**: an LLM-driven, multi-agent "autonomous R&D" loop (hypothesis
→ factor/model construction → backtest → feedback) built on top of Qlib;
paper: **"R&D-Agent-Quant"**, arXiv:2505.15155.
[github.com/microsoft/RD-Agent](https://github.com/microsoft/RD-Agent)

**Licence/cost**: MIT code, free; LLM inference billed separately. The
paper's own experiments used **GPT-4o, o1-preview-class o3/o3-mini, and
GPT-4.1** — not DeepSeek. The repo's config layer supports DeepSeek via
LiteLLM, but nothing in the paper validates DeepSeek in this role.

**Hardware/data**: hard-dependent on Qlib for data handling and backtesting;
paper's experiments use Qlib's China A-share data with a genuine walk-forward
split (train 2008-14 / validate 2015-16 / test 2017-20) and modeled costs
(buy 5bp / sell 15bp) — better hygiene than a bare IC screen, but still a
historical backtest, not live money.

**Evidence — strict**: 100% backtest-on-own-sample. Headline claim ("up to 2×
annualized return using 70% fewer factors than classical factor libraries")
is a backtest-vs-backtest comparison. The repo itself disclaims: users "should
prepare their own financial data and independently assess...risks" before any
real deployment. Reported LLM cost was "under $10" for the full experiment
— at OpenAI pricing, on OpenAI models, not disaggregated per iteration.

**Idea worth taking**: the research→build→backtest→feedback LOOP STRUCTURE
is close to what Aegis's own Sonnet-research/Opus-build/adversarial-review
chunk process already does by hand
(`docs/ROADMAP_2026-09-25_CHUNKS_AND_THE_REVIEW_LOOP.md`). **Overlap**: high
— the human-supervised version of this loop already exists and already has
guardrails (an adversarial investor review, licence discipline) RD-Agent(Q)
does not claim to have. **Effort**: 5+ days minimum just to port off Qlib's
default China pipeline and re-validate the agent loop against DeepSeek
instead of the OpenAI-tier reasoning models the paper actually used — high
uncertainty given StockBench's own finding (below) that DeepSeek underperforms
other models specifically on sequential trading-style decisions. **Failure
mode**: autonomous LLM-driven factor mining with no PIT/leakage guard built
by a third party is exactly the shape of risk CLAUDE.md's canon already
guards against ("generation is free; promotion is rationed") — importing it
would need the same guardrails re-derived from scratch.

### 1.5 StockBench

**What it is — verified, and the distinction matters**: StockBench is an
**evaluation benchmark for LLM trading agents, not a strategy or tool to
adopt**. "StockBench: Can LLM Agents Trade Stocks Profitably In Real-world
Markets?", arXiv:2510.02209 (Oct 2025).
[github.com/ChenYXxxx/stockbench](https://github.com/ChenYXxxx/stockbench)

**Licence/cost**: Apache-2.0 repo; costs are your LLM API bill plus free-tier
Polygon.io (prices) and Finnhub.io (news) — no benchmark fee.

**Hardware/data**: none beyond API access; it's an orchestration harness, not
model training.

**Evidence — strict, and this is the one methodologically careful entry in
the whole set**: test window **March 3 - June 30, 2025**, deliberately chosen
to fall after mainstream LLMs' training cutoffs to avoid the contamination
problem every other LLM-trading paper in this note has. The authors flag
(Appendix C) that no per-model cutoff audit is published, so this is asserted,
not proven, for each of the ~14 tested models — but it is a genuinely
date-gated design, the strongest anti-leakage posture surveyed here. The
benchmark's own headline finding is **mostly negative**: most models fail to
beat buy-and-hold. **DeepSeek-V3 ranked 11th of ~14 (0.2% return, Sortino
0.0144)** — near the bottom, specifically on this sequential-decision task.
Top model: Kimi-K2 (1.91% return, Sortino 0.0420).

**Idea worth taking**: rerun this exact harness against Aegis's own DeepSeek
setup as an independent, cheap calibration check on whether DeepSeek's
sequential-trading-decision quality specifically (not its text-extraction
quality, which Aegis already uses successfully) is a real constraint.
**Overlap**: low-moderate — nothing like a generic cross-model trading
benchmark exists in-house, though the philosophy (grade a forecast against
outcome) matches the project's own forecast ledger. **Effort**: <1 day to
clone, point at DeepSeek + free-tier data, and run. **Failure mode**: a
4-month, 20-DJIA-name window is thin evidence to generalize from in either
direction — treat a rerun as one more data point, not a verdict.

### 1.6 TradingAgents

**What it is**: a multi-agent LLM trading-firm simulation — analyst agents,
bull/bear researcher debate, a trader agent, and a risk-management team that
approves or overrides the trade. arXiv:2412.20138.
[github.com/TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
— 108,724 stars, Apache-2.0, active 2026-09-25 (per the 09-26 survey).

**Licence/cost**: Apache-2.0. Uses `gpt-4o-mini`/`gpt-4o` for retrieval and
`o1-preview`-class reasoning for decisions — on the order of 10+ LLM calls
per name per day, several at the expensive reasoning tier.

**Evidence — strict, and this is the load-bearing negative finding**: the
paper reports single-name Sharpe ratios of **6.4-8.2** over a 5-month 2024
window — implausible on their face for a single-equity strategy.
**Independently verified this session**: GitHub issue #203, "Clear look
ahead bias" (opened 2025-08-17, closed), reports that replicating the paper's
own recommended backtest surfaced the agent's tool calls pulling **live/
future-dated data during the "historical" simulation**, and that this
produced a BUY signal on every single day of the test window — a direct,
confirmed mechanism for exactly the kind of inflated Sharpe reported. The
issue's closure reason (fixed vs. won't-fix vs. stale) could not be confirmed
from the rendered page.

**Idea worth taking**: the bull/bear-debate-plus-risk-veto PATTERN as one
extra structured call layered on an existing signal — not the framework.
**Overlap**: high — Aegis's own thesis-card `bull/bear/falsifier/verdict/
confidence` structure is already a close analogue
(`research_value_proposition_and_competitor_ranking.md` §1.1), explicitly
minus the part where an LLM places the order, which the three-licence system
forbids outright ("no LLM authority over real capital"). **Effort**: 1-2 days
to prototype the debate-plus-veto pattern as an additional DeepSeek call on
top of an existing forecast. **Failure mode**: its flagship evidence is
compromised by a verified leak, and its core differentiator (an LLM deciding
the trade) is the one thing this project's own canon already refuses to do.

### 1.7 FinMem

**What it is**: an LLM trading agent with a layered, human-like memory
(working / short-term / long-term, recency-and-relevance-weighted retrieval)
and a fixed "profiling module" risk persona. arXiv:2311.13743.
[github.com/pipiku915/FinMem-LLM-StockTrading](https://github.com/pipiku915/FinMem-LLM-StockTrading)

**Licence/cost**: MIT. Requires OpenAI's `text-embedding-ada-002` for memory
retrieval (mandatory in the default path) plus GPT-3.5/4 for decisions; a
HuggingFace/TGI path exists for self-hosting the backbone if a GPU is
available.

**Evidence — strict**: default example backtests TSLA over a single
~3.5-month window (Jun 30-Oct 11, 2022). The paper's abstract makes only
qualitative claims ("leading trading performance"); this session could not
extract numeric return/Sharpe figures from the accessible text — treat any
specific percentage attributed to FinMem elsewhere as unverified.

**Idea worth taking**: the layered-memory retrieval design. **Overlap**:
high — Aegis already runs an ExpeL-style distillation into
`brain/LEARNED_<month>.md` with hindsight-safe retrieval (lane M,
`docs/ROADMAP_2026-09-11_ROOT_FIRST...md`), which is the same concept
already built and running. **Effort**: <1 day to extract the idea; not worth
adopting the repo itself given the mandatory OpenAI embedding dependency on a
DeepSeek-only project. **Failure mode**: the numeric evidence is too thin to
justify adopting anything beyond the idea — this is a "screener number is not
evidence"-shaped trap if repeated uncritically.

### 1.8 AlphaAgents (BlackRock)

**What it is**: a role-based multi-agent LLM system (Fundamental / Sentiment
/ Valuation agents) feeding a declared risk-tolerance persona
(risk-averse vs. risk-neutral) that picks stocks from a 15-name tech
universe. arXiv:2508.11152, BlackRock, Inc. authors, Aug 2025. **No public
code repository exists** — this is a closed research artifact.

**Licence/cost**: nothing to license; not runnable. Uses GPT-4o.

**Evidence — strict**: test window **Feb-May 2024**, GPT-4o's training data
plausibly overlaps this window — the paper does not address or rule out
contamination. Results are mixed: the multi-agent system beat the benchmark
in the risk-neutral case but **all variants underperformed the benchmark in
the risk-averse case**. Single 4-month window, one 15-name universe, no
walk-forward, no cost/turnover accounting.

**Idea worth taking**: explicit, separately labeled risk personas feeding one
underlying agent stack — directly mirrors Aegis's own declared four
personalities. **Overlap**: high, and this is where the project's own
measured evidence actively argues against copying it: §64 (memory,
`NEGATIVE_RESULTS.md`) found nine thematic PERSONA arms have **negative**
held-out discrimination (optimal weight zero) against a PROCESS arm's
positive skill — Aegis has already run this exact experiment on its own data
and gotten the opposite of AlphaAgents' framing win. **Effort**: nothing to
build (no code); reading the paper's framing is the whole cost. **Failure
mode**: treating a single, likely-contaminated, mixed-result 4-month backtest
as a transferable finding, when Aegis's own larger and more careful test of
the same idea (persona vs. process) already falsified the persona half.

### 1.9 NautilusTrader

**What it is**: a Rust-core, Python-API algo-trading platform designed so
the SAME strategy code runs in backtest, paper, and live venues.
[github.com/nautechsystems/nautilus_trader](https://github.com/nautechsystems/nautilus_trader)

**Licence/cost**: **LGPL-3.0-only**, free; contributors sign a CLA.

**Hardware/data**: standard CPU; needs Rust ≥1.98.1 and Clang to build from
source, Python 3.12-3.14, optional Redis. A real added-toolchain cost for a
Python-centric one-person project — heavier to stand up than LEAN's Docker
CLI.

**Evidence**: the unified-codebase design is a stated engineering claim
("reduces deployment divergence"), candidly caveated that live venues still
introduce behavior a simulation can't reproduce; no independent audit of its
backtest-vs-live tracking error was found.

**Idea worth taking**: single-codebase backtest/live parity — but Aegis has
**already independently diagnosed and begun closing exactly this gap** on
its own execution path (the 2026-09-25 finding that `u_plan` is the ONLY
caller of `pc_broker.submit()`, and the 09-26 note's explicit borrow of
freqtrade's single-entry-point PATTERN for the same reason). **Overlap**:
moderate-to-high at the concept level, though the tool itself is unused.
**Effort**: 5+ days to stand up a second full execution engine — a large lift
relative to finishing the in-progress, cheaper fix to the existing gap.
**Failure mode**: duplicate effort — solving a problem the project is already
solving a cheaper way.

### 1.10 alphalens-reloaded and pyfolio-reloaded

**What they are**: community-maintained (Stefan Jansen) forks of Quantopian's
factor-analysis (`alphalens`, IC/quantile-return/turnover tearsheets) and
portfolio-analysis (`pyfolio`, drawdown/tail-risk/rolling-metric tearsheets)
libraries. [github.com/stefan-jansen/alphalens-reloaded](https://github.com/stefan-jansen/alphalens-reloaded),
[.../pyfolio-reloaded](https://github.com/stefan-jansen/pyfolio-reloaded)

**Licence/cost**: both Apache-2.0, free.

**Evidence**: **neither makes or needs an OOS-returns claim** — these are
pure reporting tools with no strategy of their own, and that distinction
matters: nothing here is "evidence," it is presentation.

**Idea worth taking**: the standardized IC-by-quantile / IC-decay tearsheet
as a visual complement to `LEADERBOARD.md`'s existing by-year/LOO-worst text
fields. **Overlap**: moderate-high — the project's own receipt culture
already reports most of the same underlying numbers in text form; the gain
is legibility, not new information. **Effort**: <1 day. **Failure mode**:
none material — lowest-risk item in this note, also lowest-information.

### 1.11 mlfinlab-style tooling (purged CV, embargo, triple-barrier, DSR, PBO)

**Status**: the original open-source `mlfinlab` is **no longer free** — the
GitHub repo is now only an issue tracker pointing to Hudson & Thames'
commercial products (`PortfolioLab`/`mlfinlab`, **£100/month per user**
Business tier, custom Enterprise).
[github.com/hudson-and-thames/mlfinlab](https://github.com/hudson-and-thames/mlfinlab)
A free MIT alternative, `timeseriescv` (purged walk-forward + combinatorial
purged K-fold), exists but is thinly maintained (~290 stars).
[github.com/sam31415/timeseriescv](https://github.com/sam31415/timeseriescv)
No currently maintained free package implementing Deflated Sharpe Ratio or
Probability of Backtest Overfitting as a standalone library was found —
these are typically hand-reimplemented from Bailey & López de Prado's papers.

**Evidence**: the underlying TECHNIQUES are established, peer-reviewed
statistics, not strategies — nothing to distrust here on the merits.

**Overlap — the decisive fact**: **CLAUDE.md already states purged CV,
embargo, walk-forward splits, DSR, PBO, and Harvey-Liu thresholds are built
in-house**, and were even stress-tested against synthetic markets with known
injected edges (GATE-M1), found to have ~0% gate power, and recalibrated to a
measured 1.6% false-discovery rate (`README.md`). This is not a gap to fill;
it is a gap already closed, with more scrutiny applied to it than the paid
package's own marketing gives its version. **Effort**: <1 day, only to
cross-check the in-house DSR/PBO formulas line-by-line against the
Bailey/López de Prado pseudocode as a one-time correctness audit — not to
adopt any package. **Failure mode**: paying £1,200/yr for a capability
already built and already more rigorously validated than most published
uses of the paid version.

### 1.12 Kronos (time-series foundation model)

**What it is**: a 2025 foundation model pretrained on 12B+ financial K-line
records from 45 exchanges, for zero-shot OHLCV forecasting. arXiv:2508.02739.
[github.com/shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos)

**Licence/cost**: MIT, free. Open variants: Kronos-mini (4.1M params),
-small (24.7M), -base (102.3M) — all comfortably fit an 8GB-VRAM laptop GPU
(Kronos-large, 499M, is closed-source).

**Evidence — strict**: the repo's own example is explicitly labeled "not a
production-ready quantitative trading system." Published comparisons are
**forecasting-accuracy benchmarks only** (RankIC +93% vs. other time-series
foundation models, volatility-MAE -9%) — no trading P&L claim exists anywhere
in the primary source. This is the general pattern for time-series
foundation models and it holds here without exception.

**Idea worth taking**: a genuinely novel, zero-API-cost, GPU-local
complementary forecaster to ensemble against existing signals — one of the
best hardware/cost fits of anything surveyed, and the ONLY item in this note
that adds a capability class (a pretrained sequence model) Aegis has none of.
**Overlap**: low. **Effort**: 1-2 days to download weights and run zero-shot
walk-forward on Aegis's own universe with costs, before trusting anything.
**Failure mode**: the RankIC gains are a post-hoc, full-sample, foreign-panel
comparison — precisely the shape CLAUDE.md's own canon warns against ("a
prior chosen after the diagnostic is not a prior"); must be re-earned on
Aegis's own walk-forward panel, not imported as a finding.

---

## 2. Marginal Decision Contribution — is it estimable here?

The reviewer called this Tier 0. It deserves a straight, numbers-based
answer, not a restatement of enthusiasm.

**(1) How Numerai computes it today, precisely.** MMC = covariance of a
submission's meta-model-orthogonalized residual with the live target. TC =
the gradient of the stake-weighted portfolio's realized return with respect
to each user's stake, via differentiable convex optimization. **Both need**:
a large, simultaneously-scored cross-section every period (Numerai: hundreds
of weekly eras, thousands of quasi-independent submissions forming the
meta-model being conditioned on) and a live composite/meta-model to condition
against in the first place. See §1.1 for full citations.

**(2) Does this project have the data to estimate it at all?** Use its own
numbers, not a hypothetical:

| Candidate series | Rows | Independent unit | Actual count of that unit | What's needed |
|---|---|---|---|---|
| Forecast ledger | ~14,700 graded (2026-09-24) | distinct decision DATE (per house convention: `source_scorecard.MIN_DATE_BLOCKS`, memory canon "§58 n_effective counts DATE BLOCKS") | on the order of tens (daily-cadence pipeline, serious accrual only since ~late August) | hundreds+ for a small partial correlation |
| Strategy library | ~200+ rules / 34 families, monthly since 2020 | monthly block, SEALED (look-ahead-honest) window | **32** (2024-26) | the project's OWN measured single-rule MDE on this window is already **~2.46%/month** (`family_pool.py` docstring; `docs/reviews/REVIEW_2026-09-27_SIGNAL_STRUCTURE_ROUND2_BRIDGE.md` §8) — a real, already-computed ceiling, not a guess |
| Dow Jones source scorecard | ~40 claims (WSJ) | publication DATE | **9** today; `MIN_DATE_BLOCKS = 10` is the code's own hard floor | ~110, per the 2026-09-28 handoff's own estimate (§4, §7) |
| Analyst revisions | ~392,000-393,000 dated rows since 2025 | distinct announcement date | likely hundreds-to-low-thousands over ~18-20 months (revisions post most trading days across thousands of names) | this is the one series plausibly close to Numerai's own scale |

**The row count is not the sample size.** This is the single most important
correction to make before answering the reviewer: 14,700 graded forecasts is
NOT 14,700 independent observations for a cross-sectional marginal-value
regression, for the same reason the reader-night handoff already found WSJ's
16 claims collapse to 9 independent publication dates, not 16.

**(3) What already approximates it, and what's actually missing.**
`family_pool.py`'s `n_eff = n/(1+(n-1)ρ)` is the right ARITHMETIC for "how
much does correlation eat your sample," but applied WITHIN a family (deduping
near-duplicate rules), never between a candidate signal and the system's full
live composite. `forecast_reputation.py`'s shrinkage-weighted, floored-at-zero
reputation is a Numerai-stake-like WEIGHTING of forecasters, not a
residual-after-conditioning CONTRIBUTION test. `signal_structure.py`'s
ALPHA_DETECTED/CANNOT_DISTINGUISH/BETA_EXPLAINS is a beta-decomposition
against a small number of NAMED factors, not against the live composite
itself. `strategy_library_ext.py`'s per-rule `falsifier`/`controls` fields
are a manual, one-candidate-at-a-time subsumption check, done by a human
picking the control, not an automated general procedure. **What's missing**:
a single reusable module that takes the system's current composite score at
decision time, regresses/rank-neutralizes a new signal against it
per date-block, and reports whether the residual still predicts the outcome
— the literal MMC mechanic, generalized. Building it (reusing
`family_pool.py`'s variance code) is a 3-5 day job; the harder problem is (2).

**(4) Minimum detectable marginal contribution, plainly.** For a partial
correlation `r` estimated over `n` independent date-blocks (two-sided
α=0.05, power=0.80, Fisher-z approximation): `MDE(n) ≈ 2.8/√(n-3)`. This
is illustrative scaling, not a substitute for the project's own measured
return-level MDEs above — it exists only to show WHY small `n` is
structurally hopeless: n=9 (today's Dow Jones cell) cannot detect anything
meaningful; n=110 (the handoff's own stated target) still leaves MDE≈0.27,
large by cross-sectional-return standards (a real edge is often r≈0.02-0.05);
n=30 (roughly today's forecast-ledger date-block count) gives MDE≈0.52.
Going from 9 to 110 dates buys roughly a 3.5x tightening — necessary, nowhere
near sufficient, for a small effect.

**Honest answer, stated exactly as the brief asked for it**: **Marginal
Decision Contribution is estimable, at large-effect resolution only, for
strategy rules** (32-80 monthly blocks; the project already has a measured
MDE, ~2.46%/month, on the window it trusts) **and for analyst revisions**
(the one series plausibly close to Numerai's own eras-and-cross-section
scale). **It is NOT estimable for months for individual Dow Jones news
sources** (9 of an estimated 110 needed publication dates — an order of
magnitude short) **and is NOT yet estimable for the forecast ledger's own
day-to-day marginal-source value at cross-sectional granularity**, because
the ledger's row count is not its date-block count, and the date-block count
is still on the order of tens.

---

## 3. Ranking — four separate columns, never blended

Scored 0-100. **A** = evidence of real net OOS value. **B** = fit to one
person on one laptop. **C** = overlap with what exists here (high =
redundant). **D** = expected information per day of work. One fact beside
each score.

| Method | A: evidence | B: fit (1 person/1 laptop) | C: overlap (high=redundant) | D: info/day |
|---|---|---|---|---|
| Numerai MMC/TC (technique) | **15** — 13F/community data suggest the live fund itself hasn't clearly beaten SPY since 2023 | **10** — needs Numerai's own obfuscated platform; the technique must be rebuilt from scratch on Aegis's own data | **55** — `family_pool.py`/`forecast_reputation.py` cover adjacent ground, not this | **35** — cheap to build, but MDE math in §2 caps its near-term payoff |
| QuantConnect LEAN | **20** — it's an engine; no returns evidence attaches to the tool itself | **70** — free, local, modest hardware spec, adapter design already scoped | **20** — deliberately independent of the existing engine, by design | **55** — bounded engineering, real bug-catching value, already partly planned |
| Microsoft Qlib | **15** — own-sample China-market backtest only, no independent replication | **25** — no free US data; another paradigm/DSL to learn | **60** — its one useful piece (chart shape) is already flagged as "copy, don't build" | **25** — full platform adoption doesn't address the diagnosed bottleneck (selector diversity, not model count) |
| Microsoft RD-Agent(Q) | **10** — pure backtest-vs-backtest on own China sample | **10** — validated only on OpenAI-tier reasoning models, not DeepSeek | **20** — genuinely different capability | **20** — Aegis's own human-supervised chunk loop already approximates this, with guardrails RD-Agent(Q) lacks |
| StockBench | **20** — careful anti-leakage design, but its own headline finding is mostly negative for the whole category | **60** — cheap, free-tier data, DeepSeek already tested in it | **30** — no in-house generic cross-model benchmark exists | **55** — cheap, fast, already tells Aegis DeepSeek ranked 11th/~14 on this exact task type |
| TradingAgents | **8** — flagship Sharpe 6-8 numbers traced to a confirmed look-ahead leak (issue #203) | **15** — real OpenAI-tier spend, and its core act (LLM places the trade) is forbidden by Aegis's own canon | **65** — Aegis's thesis-card structure already covers the debate pattern, minus the forbidden part | **15** — compromised evidence, forbidden core mechanic |
| FinMem | **12** — numeric claims unverifiable from the accessible text; ~3.5-month single-ticker window | **35** — mandatory OpenAI embedding dependency on a DeepSeek-only project | **70** — Aegis's `LEARNED_<month>.md` ExpeL-style memory already does this | **15** — high redundancy, thin evidence |
| AlphaAgents (BlackRock) | **12** — 4-month window, likely GPT-4o cutoff overlap, mixed/negative in risk-averse case, no code | **20** — no code exists; GPT-4o-class model assumed | **55** — Aegis's own four-personality design already covers the framing | **20** — Aegis's OWN §64 finding (personas: negative held-out skill) already contradicts AlphaAgents' persona-win framing |
| NautilusTrader | **15** — unified-codebase claim is a design statement, not an audited result | **35** — free, but needs a Rust/Clang toolchain most Python-only teams don't carry | **15** — a real gap, but one Aegis is already closing more cheaply on its own path | **20** — large lift, duplicate-effort risk |
| alphalens-reloaded + pyfolio-reloaded | **5** — by design, no strategy, no OOS claim | **75** — trivial, free, pure pandas | **60** — the project's own receipt culture covers most of the same numbers in text | **40** — cheap visual upgrade, low new information |
| mlfinlab-style tooling (purged CV/DSR/PBO) | **70** — the underlying statistics are established and peer-reviewed | **50** — cheap to hand-implement; paid tiers (~£1,200/yr) are a poor fit for a $0-budget project | **90** — CLAUDE.md confirms this is already built AND already stress-tested (GATE-M1) | **15** — only a one-time correctness audit remains valuable |
| Kronos | **15** — forecasting-accuracy benchmarks only; explicitly not a trading system | **65** — MIT, free, small variants fit an 8GB-VRAM laptop, zero API cost | **10** — the only item here that adds a genuinely new capability class | **45** — novel and cheap to try, but its RankIC gains are a post-hoc foreign-panel comparison that must be re-earned on Aegis's own data |

### The reviewer's six numbers, scored

| Reviewer score | Item | Verdict | Why |
|---|---|---|---|
| Numerai MMC 97 | AGREE on the IDEA's importance; **TOO HIGH** as a "fit" score | The scoring TECHNIQUE is genuinely the most rigorous surveyed, but the platform itself is not reusable (obfuscated data, own tournament), the live fund's own real-money record is contested/unverified since 2023, and Aegis's own data cannot yet power the technique at a meaningful resolution (§2). A "fit for one person on one laptop" score should reflect that almost none of Numerai's actual infrastructure transfers. |
| QuantConnect LEAN 96 | **AGREE**, roughly | Free, runs locally on modest hardware, Apache-2.0, adapter design already scoped by a prior session — this is a genuinely good fit; 96 slightly overstates how bounded the integration effort is (data reformatting, a second C#/.NET codebase to maintain, a statistics layer with a bug history), but the direction is right. |
| Microsoft RD-Agent+Qlib 95 | **TOO HIGH** | Qlib ships no free US data; RD-Agent(Q) is validated only on OpenAI-tier reasoning models the project doesn't use (DeepSeek is the only provider here, and StockBench independently found DeepSeek underperforms specifically on sequential trading decisions); all evidence is own-sample backtest; the useful piece (a chart shape) was already extracted in a prior session without needing the platform. |
| StockBench 90 | **TOO HIGH** if read as adoptable infrastructure; a fair score for "worth reading and rerunning cheaply" | It's a benchmark, not a tool that produces returns; its own headline finding is mostly negative for the category, and it should be read as a caution (and a free calibration check on DeepSeek) rather than a build target. |
| TradingAgents 82 | **TOO HIGH** | Its flagship evidence is traced to a verified, confirmed look-ahead leak, and its core mechanic (LLM places the trade) is exactly what Aegis's own three-licence canon forbids. The debate PATTERN is worth a cheap prototype; the framework is not. |
| FinMem 80 | **TOO HIGH** | Numeric evidence is unverifiable from the accessible primary text, the window is short and single-name, and Aegis already runs a comparable layered-memory mechanism (`LEARNED_<month>.md`) — most of what FinMem would add is already built. |

No score in the reviewer's list should read as TOO LOW; every one overstates
either the evidence quality, the fit to a one-person/one-laptop/DeepSeek-only
constraint set, or both, once checked against primary sources and against
what this repo already has running.

---

## 4. What this note recommends, ranked by D net of A and C

This is a research note's recommendation, not a roadmap commitment — it still
needs the ONE current TIER 1 roadmap's owner to decide whether it earns a
slot, per CLAUDE.md's "new work is not roadmap work by default."

1. **Kronos** (local, free, novel capability class, 1-2 days) — try it
   zero-shot on Aegis's own walk-forward panel with costs before trusting
   anything from its own paper.
2. **StockBench rerun against Aegis's own DeepSeek setup** (<1 day, free) —
   cheap independent confirmation or refutation of whether DeepSeek's
   sequential-decision quality specifically is a constraint.
3. **QuantConnect LEAN adapter** (2-4 days, already scoped on paper) — the
   one item here that is genuinely "finish what a prior session already
   designed," not new research.
4. **The Marginal Decision Contribution module**, scoped honestly to what §2
   says is actually estimable today (strategy rules, analyst revisions) — not
   news sources, not the forecast ledger's per-date value yet. 3-5 days,
   reusing `family_pool.py`.
5. **Do not** adopt Qlib, RD-Agent(Q), TradingAgents, FinMem, AlphaAgents, or
   NautilusTrader as platforms. Extract the one cheap idea from each (already
   done in most cases by the 2026-09-26 survey) and stop there.
6. **Do not** pay for mlfinlab/PortfolioLab. The in-house purged-CV/DSR/PBO
   stack is already built, already stress-tested against synthetic markets,
   and already found once to have near-zero power before recalibration — more
   scrutiny than the paid package's marketing shows for its own version.
