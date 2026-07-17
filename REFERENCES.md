# REFERENCES — external projects we study, and what we take from each

> **2026-07-17: the machine-readable successor to this file is
> `docs/KNOWLEDGE/projects.jsonl`** (104 entries, injected into every lab
> cycle; human-readable view in `docs/PROJECT_LANDSCAPE.md`). New
> examinations go THERE, in the same commit as the examining work
> (CANON §11). This file stays as narrative background for the early
> study-closely set.

> Policy: **patterns, re-implemented — never vendored code.** Copying other
> repos in would be license contamination (Aegis is MIT), bloat, and a dilution
> of the one thing that is ours (the honest forward record + the private brain).
> This file doubles as the competitive-landscape doc: it records which external
> project informed which decision, so credit is honest and rabbit holes aren't
> re-explored. Libraries that earn it enter as normal pip dependencies, not
> copies.

## Study closely (highest value)

### LangAlpha — `github.com/ginlix-ai/LangAlpha` (Apache-2.0)
The closest existing product to the Aegis vision: "Claude Code for investing" —
persistent research workspaces, tiered data ecosystem (Polygon → FMP →
yfinance), ~23 finance skills (DCF, thesis-tracker, catalyst-calendar,
earnings), and a full research-workbench front-end (TradingView embeds, inline
charts, provenance panel).
**Take:** data-tier architecture and programmatic tool-calling pattern (Branch 1);
the entire front-end surface as reference (Branch 4); their agent.md +
long-term-memory store as an Optimus comparison point. The catalyst-calendar
skill is the reference for our "explain the 300% move" feature.
**Do not take:** their epistemics. LangAlpha is a research assistant with no
forward track record, no experiment registry, no 24-month discipline, no
DSR/PBO gate. That spine is our moat — borrow their surface, keep our spine.

### anthropics/financial-services (official Anthropic)
Official finance-domain agent patterns and skills; LangAlpha itself adapts from
it. **Take:** skill structure and prompt patterns for financial analysis tasks;
on-domain, high quality, low license risk.

### stefan-jansen/machine-learning-for-trading (ML4T)
The ML-for-trading reference text-as-repo. **Take:** feature engineering,
factor construction, alt-data handling for the multi-factor work (T8).
**Guardrail:** everything it teaches about backtesting is governed by T7 —
direction-checks only on our data; validation stays forward.

## Borrow patterns for Optimus + dev workflow

### affaan-m/ECC (MIT)
A Claude Code "agent OS." **Take:** the continuous-learning "instincts" pattern
(auto-extract patterns from sessions with confidence scoring) and the
memory-persistence hooks (save/load context across sessions) — both are mature
references for what Optimus's postmortem→brain loop should become.
**Do not:** wholesale-install; it is sprawling and finicky. Extract patterns.

### thedotmack/claude-mem
A Claude memory system. **Take:** ideas to compare against Optimus (retrieval,
distillation cadence). Optimus is the private moat — compare, don't replace.

### obra/superpowers · vercel-labs/skills (find-skills)
Claude Code skill/workflow pattern libraries. **Taken (2026-07-08):** the
SKILL.md authoring pattern (frontmatter + imperative procedural body) was
studied and re-implemented as five Aegis-specific discipline skills in
`.claude/skills/` — verify-prod-after-deploy, lane-integrity-check,
seed-a-lane, pre-register-trial, silent-fragility-audit. Our skills codify
Aegis's own paid-for lessons; no external framework vendored.

### farion1231/cc-switch
Model/provider switcher for Claude Code. Tooling convenience only; nothing
enters the repo.

## Tooling (candidate pip dependencies)

### kernc/backtesting.py
Clean single-file backtesting library. **Take:** possibly as a dependency for
direction-check harnesses (cleaner than hand-rolled loops). **Guardrail:** a
nicer backtester cannot fix a survivors-only universe (T7); its output is
direction-grade, never alpha-grade.

### Qlib (Microsoft) — via V3_RESEARCH_SYNTHESIS verdict
**Take:** the PIT-database schema ideas (vintage handling, field-level
revisions) to harden `pit_observations` (IMPROVEMENT_BACKLOG B8). Verdict
2026-06-20: learn-from, keep our own loop — do not adopt the framework.

## Reference with caution — profit-mirage risk

### NousResearch/hermes-agent · asavinov/intelligent-trading-bot · demasterr/investing-bot
LLM-agent and ML-predict-then-trade projects. **Take:** architecture ideas only
(agent loops, feature pipelines). **Do not take:** their core premise —
"agent/model learns from backtests to trade better" is precisely the
backtest-to-alpha loop Aegis disproved (CANON §2–§4). Any pattern borrowed from
these must pass through the pre-registered-forward-trial discipline.

## Indexes (discovery only, nothing to adopt)

- georgezouq/awesome-ai-in-finance — discovery index for future scans.
- github.com/topics/investment-strategies, /topics/quant-trading-bot — browse
  pages, not projects.

## Already-held reference code (read-only, local)

| Repo | Path | Used for |
|---|---|---|
| PyPortfolioOpt | `C:\Users\mrthn\reference-codes\PyPortfolioOpt` | BL, HRP, Ledoit-Wolf |
| MLFinLab | `C:\Users\mrthn\reference-codes\mlfinlab` | Purged CV, triple-barrier, fracdiff |
| Autoresearch | `C:\Users\mrthn\reference-codes\autoresearch` | Experiment-loop ratchet pattern |

## License hygiene

Aegis is MIT. Apache-2.0/MIT sources are pattern-safe with attribution here.
**AGPL code (e.g. OpenBB) never enters this repo** in any form. When a pattern
is re-implemented from a specific source, note it in the implementing module's
docstring and keep this catalog current.
