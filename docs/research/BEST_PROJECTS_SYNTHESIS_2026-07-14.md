# Best-Aligned Projects Synthesis — 2026-07-14

> Three-agent web survey: (A) LLM/agent trading systems + the 2025-26 critique
> literature, (B) quant research/validation infrastructure + survivorship-free
> data economics, (C) HKUDS/Vibe-Trading deep-dive (file-level). Full agent
> reports summarized; sources cited inline in the session transcript.
> Companion to `CRASH_AND_OSS_RESEARCH_2026-07-11.md` (15 prior verdicts not
> re-litigated).

## The headline finding

**Aegis's validation architecture is already ahead of ~90% of the field — and
the field converged on our protocol in 2025-26.** A survey of 19 LLM-trading
studies found only 2 with time-consistent splits, 1 modeling transaction
costs, 1 handling survivorship, 15/19 irreproducible (arXiv 2605.19337).
GPT-4o recalls in-cutoff S&P closes to <1% error — much published "LLM alpha"
is memorization (arXiv 2605.24564). Every leakage-controlled LIVE evaluation
(DeepFund, StockBench, Agent Market Arena, Alpha Arena real-money) finds most
frontier LLMs LOSE money trading. The field's new consensus protocol —
forward, post-cutoff, paper-money, costs disclosed — is what our lanes +
pre-registered trials have done since June. The moat is real; nobody surveyed
runs pre-registered paper-lane forward records.

**Implication:** do NOT absorb "LLM picks stocks" (fails every controlled
test). Absorb components: factor-discovery loops with ratchets, layered
memory with temporal embargo, risk-triggered reflection, debate-as-audit,
and third-party verification infrastructure.

## Vibe-Trading (HKUDS) — the direct answer

**What it is:** HKU Data Science Lab's "vibe-coding for markets" (MIT, 21.5k
stars in 3.5 months, PyPI v0.1.x): natural language → LLM agent plans →
pulls data through a 30-loader fallback registry → WRITES strategy code →
runs it in an AST-sandboxed custom backtest engine → reports via CLI/web/16
IM channels. Extras: 450-ish factor "alpha zoo" with IC benchmarking,
research memory, multi-agent swarms, opt-in bounded live trading (Robinhood
verified). Marketing says LangGraph; the hot path is actually a hand-rolled
ReAct loop with excellent 5-layer context compression.

**Is it better than Aegis?** Different species — it's a research *toolbox*,
Aegis is an opinionated *product with a track record*. Where it beats us:
agent UX (NL→backtest in one loop), data resilience (IP-ban-ordered fallback
chains), factor library engineering (per-factor metadata + mass IC bench),
16-channel delivery, sandboxing, distribution. Where we beat it — and it's
the part that matters for ROI claims: **its validation is statistically
shallow** (permutation + bootstrap + fake "walk-forward" that just slices one
equity curve; NO purged CV, NO DSR/PBO, NO survivorship handling, NO forward
record, NO pre-registration; its alive/dead t>2 factor screen is a textbook
data-mining machine). Aegis has purged CV, PSR/DSR/PBO/CPCV, calibration with
CIs, conformal intervals, crash/regime/copula/GARCH risk modeling (they have
~none), and a deployed forward record.

**Catch-up plan (their strengths, our discipline):**
1. Loader fallback chains (`agent/backtest/loaders/registry.py` pattern) →
   our provider registry (matches silent-fragility doctrine; their fail-loud
   local-loader rule is our pattern already).
2. Alpha-zoo registration pattern (`factors/registry.py`: one factor per
   file, `__alpha_meta__` with citations/decay/warmup, AST-discovered,
   output-validated) as the scaffold for our forward-IC factor collectors.
3. IC bench harness (`factors/bench_runner.py` process-pool, alive/reversed/
   dead buckets) — but run on FORWARD PIT snapshots, making ours honest
   where theirs is mined.
4. AST sandbox (`backtest/runner.py`) if the lab loop ever executes
   generated strategy code.

## Ranked absorb list (across all three surveys)

| # | Absorb | From | Effort | Value |
|---|---|---|---|---|
| 1 | **Alpaca paper-account mirror of 1-2 flagship lanes** — third-party-computed NAV via Portfolio History API; never-reset policy; divergence monitor vs internal NAV | Alpaca (free, paper-only, no US KYC) | M | Converts "forward track record" from self-reported to third-party-verifiable — the single biggest trust upgrade available |
| 2 | **alphalens-reloaded on existing PIT forward snapshots** (insider, revisions, momentum, composite, congress, ARK) | stefan-jansen (maintained, Dec 2025) | S | Every forward-IC trial upgrades from one IC number to IC decay + quantile monotonicity + turnover; publication-ready |
| 3 | **Survivorship-free dataset: check HKU WRDS/CRSP first ($0 for Murat!)**; else Sharadar SEP ~$35-40/mo or Norgate Platinum ~$53/mo | HKU library / Nasdaq Data Link / Norgate | M | Retires T7 from "permanent ban" to "solved" — robustness backtests become legitimate (still under DSR/PBO, still not certification) |
| 4 | **RD-Agent(Q)-style hypothesis memory + ratchet in lab loop** — structured store of every tried hypothesis + OOS result; factors admitted only on beating incumbent library, post-LLM-cutoff windows only | Microsoft RD-Agent (MIT); the one surveyed system with credible evidence (test window chosen AFTER LLM cutoffs) | M | The credible ROI lever: LLM writes/screens quant code, gate decides — composes with our pre-registration instead of bypassing it |
| 5 | **QuantConnect free-cloud re-run of 2-3 lane mandates** — survivorship-free 1998+ data, shareable result URLs = third-party attestation of historical robustness | LEAN/QC free tier ($0) | M | Complements #1: Alpaca attests forward, QC attests history |
| 6 | **FinCon-style risk-triggered reflection** — lane drawdown/CVaR breach → structured postmortem (market-error vs decision-error split per FinAgent) → brain context for future conviction decisions | FinCon (NeurIPS 2024) | S-M | Turns the track record from scoreboard into training signal; never touches the NAV write-path |
| 7 | **Vibe-Trading loader fallback chains + alpha-zoo/IC-bench patterns** (above) | HKUDS (MIT) | S-M | Data resilience + factor-research productivity |
| 8 | **Alpha Illusion P1-P6 disclosure protocol on every trial page** (data timestamps vs model cutoffs, cost model, window + Sharpe CI, buy-and-hold baseline) | arXiv 2605.16895 | S | Near-free credibility: states in the field's vocabulary what we already do |
| 9 | **FinMem layered memory with class-specific decay + temporal embargo** for news/brain retrieval | FinMem (MIT) | M | Better LLM context; embargo inoculates against the field's #1 bug |
| 10 | **Bull/bear debate as explanation layer** on signal pages (LLM argues both sides of the computed signal; numeric signal unchanged) | TradingAgents (Apache-2.0) | S-M | Trust/UX; the one part of the 93k-star framework that survives adversarial review |

**Explicit do-NOT-absorb:** end-to-end LLM trade decisions (fails every live
test; TradeTrap shows agents wrecked by fake news/state tampering — keep the
NAV write-path LLM-free as it is), persona-investor ensembles (vocabulary,
not skill), qlib-as-platform (US collectors broken 2026; inherits T7),
OpenBB (AGPL router, not data), backtrader (dead since ~2018), any backtest
of an LLM over its own training window.

## What this means for "best ROI"

The evidence says ROI comes from: (1) disciplined factor research under a
ratchet (absorb #4) validated forward (our lanes), (2) risk control that
cuts tail losses (our exit-overlay trial, absorb #6), (3) NOT from LLMs
making trade decisions. Our differentiator vs every surveyed project is the
honest forward record — absorbs #1/#5/#8 make that record externally
verifiable, which is what lets it compete with firms' claims.
