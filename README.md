# Aegis Finance

<p align="center">
  <a href="https://aegis-finance-six.vercel.app"><img alt="Live app" src="https://img.shields.io/badge/live-aegis--finance-0891b2?style=flat-square"></a>
  <img alt="Tests" src="https://img.shields.io/badge/tests-3%2C800%2B%20passing-2ea44f?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="Next.js" src="https://img.shields.io/badge/next.js-14-000000?style=flat-square&logo=nextdotjs">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-backend-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="Forward record" src="https://img.shields.io/badge/forward%20record-since%202026--06--08-blueviolet?style=flat-square">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square"></a>
</p>

Aegis Finance is a free, open-source **self-improving investment intelligence
system** that measures itself in public and tells you when it is wrong. Its
objective is compound return under explicit survival constraints — not
classification accuracy, not a pretty backtest. It searches the *whole* market
rather than the famous part of it, treats an LLM as something that proposes
causal hypotheses while deterministic engines compute and grade them, and keeps
its own corpses: a refused strategy with a written reason is an asset here, not
an embarrassment. Every idea is pre-registered before it touches data, tested on
live forward paper portfolios (running since **2026-06-08**), and published
whether it works or not — the failures live in
[NEGATIVE_RESULTS.md](NEGATIVE_RESULTS.md), at the top level, where a skeptic
finds them first. Around that spine sits a full market dashboard: crash-risk and
fragility measurement, Monte Carlo projections, portfolio construction, factor
analysis, and point-in-time data collectors — all on free data sources.
The twelve original + four added invariants are in
[`docs/AEGIS_STRATEGIC_INVARIANTS.md`](docs/AEGIS_STRATEGIC_INVARIANTS.md); they
outrank any roadmap in this repo.

**This is an educational tool, not financial advice.**

## Start here — the skim → read ladder

Five rungs. **Stop at the one that answers your question**; each is a strict
superset of the one above it. This is the same ladder for a human skimming on a
phone and for an agent about to change something.

| Rung | Read | Cost | You leave knowing |
|---|---|---|---|
| **1** | this README | 5 min | what Aegis is, the headline results, what it refuses to claim |
| **2** | [`docs/INDEX.md`](docs/INDEX.md) | 3 min | which of 268+ docs answers your question |
| **3** | **TIER 0** — [invariants](docs/AEGIS_STRATEGIC_INVARIANTS.md) · [the vision, verbatim](docs/AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md) · [objective §0](docs/OPTIMUS_OBJECTIVE.md) · [CLAUDE.md](CLAUDE.md) | 30 min | the constraints that outrank every plan |
| **4** | the **ONE** current TIER 1 roadmap (INDEX names it; today [`ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md`](docs/ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md)) | 30 min | what is being built now and what gates it |
| **5** | **the receipt** named beside the number | varies | whether the number survives being looked at |

**Rung 5 is not optional for a number you are about to act on.** Every headline
in this repo names a JSON receipt; prose is the summary, the receipt is the
fact. A number that lives only in prose has already burned us once (`corr =
0.516` turned out to be a filtered subset nobody had named).

**Agents, additionally:** run `session_briefing()` + `aegis_verified_state()`
(Optimus MCP) *before* reading code, and `brain_query` / `aegis_postmortems`
*before* proposing any research — the idea may already have a corpse with
receipts. Big datasets that are deliberately **not** committed are catalogued in
[`docs/DATA_MANIFEST.md`](docs/DATA_MANIFEST.md); check there before concluding
something was never pulled. Execution — the six live paper books — is a
**separate repo**, entered at `aegis-alpha-terminal/docs/INDEX.md`. There is no
`docs/HANDOFF.md` in this repo, on purpose.

## Three licences — what a result is allowed to claim

The single most useful thing this project did in 2026 was stop applying one
evidence standard to everything. Research rigour determines what Aegis is
allowed to **claim**; it must not determine what Aegis is allowed to **test** in
paper. Every artefact here names one of these:

| Licence | Permits | Required before it starts | Significance gate? |
|---|---|---|---|
| `PRODUCT_EXPERIMENT` | internal simulation + external **paper** brokerage | a frozen strategy contract *before the first decision*: policy hash, timestamp, inputs, costs, fill convention, objective | **No.** No MDE, no multiplicity control, no 24-month floor |
| `CAPITAL_CANDIDATE` | candidacy for **real money** | matured forward evidence, realistic costs, calibration, utility improvement, drawdown/ruin bounds | Yes — and promotion stays **attended** by a human |
| `RESEARCH_CLAIM` | "this is alpha" — a paper, a public skill claim | full pre-registration, MDE, multiplicity control, matched controls, holdout | Yes — every standing evidence rule binds |

Four things never relax at any licence, and they are enforced in code rather
than by intention: **no information acted on before it was public**; **no target
leakage**; **costs are never omitted** (`portfolio_farm.Policy` *refuses* zero
costs unless `zero_cost_diagnostic=True`, and the flag travels onto every result
row); and **once a candidate enters forward paper, its version is frozen**.
No LLM ever has authority over real capital.

## Live

| Surface | URL |
|---|---|
| Web app | https://aegis-finance-six.vercel.app |
| API | Railway (FastAPI backend, auto-deployed from `main`) |
| Optimus brain showcase | https://optimus-brain-alpha.vercel.app |

## The newest results (September 2026)

*Every figure below is generated from the frozen run artifacts and the live API
by [`tools/readme_charts.py`](tools/readme_charts.py) — numbers are read from
JSON, never retyped. Regenerate with `python tools/readme_charts.py`.*

### 1. The skill lives where the engine is silent

🔵 **BACKTEST · `PRODUCT_EXPERIMENT`** — receipt:
[`backend/data/optimus/tracker_backtest/learner_v1.json`](backend/data/optimus/tracker_backtest/learner_v1.json)

![LEARNER v1: rank IC by arm, and the champion's IC split by what the engine already said](docs/assets/learner_v1_engine_is_silent.png)

LEARNER v1 asked whether a machine-learned model can add anything on top of the
engine's own banded prior. It was pre-registered on 2026-09-02 *before any model
was fitted*, then run walk-forward over **441,278 name-months / 144 months /
5,713 names**, twelve arms, with a shuffled-target null running the identical
pipeline. Three things came out, and only one of them is a good headline:

- **The ordering is real.** Champion `lgbm_clf` reaches mean monthly rank IC
  **0.0954, t 8.21** (t on months, n = 107) while the shuffled-target null sits
  at **0.0046 (t 0.81)**. The null is clean.
- **The money is not — yet.** The champion's top-50 value-weighted book is
  **t 1.49** paired against the market. That is one arm of twelve, on one draw
  of a correlated set. *IC is not P&L*, and this README does not claim it is.
- **The interesting result is conditional.** Split by the engine's own bands,
  the champion's IC is **0.137 (t 8.79)** where the engine has **no opinion**,
  **0.058 (t 5.58)** in the band the engine calls toxic — and **0.002 (t 0.10)**
  inside ratio 3–5, *the band the engine actually buys*. The learner is not
  improving the engine's picks. It is seeing in the dark where the engine is
  blind.

### 2. The prior is a 12-month object running on a 1-month clock

🔵 **BACKTEST** — same receipt (`scoreboard_other_horizons.prior`)

![BAND_PRIOR v2 rank IC by forecast horizon: t 12.7 at 1m rising to t 34.5 at 12m](docs/assets/band_prior_by_horizon.png)

The engine's banded analyst-target prior ranks the cross-section monotonically
*better* the further out you look — **t 12.7 at one month rising to t 34.5 at
twelve**, with all 96 twelve-month windows positive. The live books rebalance
**monthly**. A signal being strongest at a horizon nobody trades it at is a
construction bug, not a discovery, and the trial that separates "twelve-month
prior sampled too often" from "beta exposure wearing a selection label" is
running now (`scripts/band_horizon_run.py`, `PREREG_BAND_IS_BETA_1`).
⚠ The 2013–2024 band constants were fitted in full sample, so the prior is
**flattered** in this chart — read `prior.in_sample_warning` in the receipt
before quoting it.

### 3. The forward record, unedited

🟢 **LIVE FORWARD** — source: the public
[track-record API](https://aegis-finance-production.up.railway.app/api/pi/track-record)

![Ten paper lanes, one panel each, each against SPY rebased to that lane's own start](docs/assets/lanes_small_multiples.png)

Ten paper lanes, $100k each, marked daily since **2026-06-08**, configs
hash-pinned so tampering is detectable. **The ordering here is noise** — at this
window the standard error on an annualized Sharpe is about 2.1, which is wider
than every gap on the chart, including the gap to SPY. What is *not* noise is
that the record exists and cannot be edited backwards. The deeply underwater
`mirror` lane stays on the chart on purpose: it is this project's own receipt
for what concentrated idiosyncratic risk does to a book.

### 4. What a month of data buying actually bought

🔶 **EXPLORATORY** — receipt:
[`backend/data/optimus/tracker_backtest/month_retro_20260902.json`](backend/data/optimus/tracker_backtest/month_retro_20260902.json)
· writeup: [`docs/RETRO_2026-09-02_THE_MONTH_OF_DATA.md`](docs/RETRO_2026-09-02_THE_MONTH_OF_DATA.md)

August 2026 acquired roughly **6.0 GB across 31 dataset families**. Only
**12,233 rows** of it are point-in-time-clean *forward* observations; everything
else is substrate or hindsight. The month's largest single loss was a name our
own rule had **refused** (`claims: false`, rank 576 of 766) and the book held at
10% anyway — and it was the only company-specific loss that day. The other
twelve holdings were leverage: **mean market beta 2.10** into a −0.687% SPY.
Two forward sessions exist; n = 2 decides nothing. That is the honest state.

Related, same window: holder-provenance H2/H3 on the full 13F panel
([`holder_h2_h3.json`](backend/data/optimus/tracker_backtest/holder_h2_h3.json))
found holder identity **thin** (t 2.24, ~5 bps per 1sd — under costs), the
long-duration-holder intuition **inverted**, and a manager's own top-decile
stake **adverse** (−1.21pp per 252 sessions, t −3.95). Three intuitions, three
adjudications, none of them the one we expected. That is the system working.

## The honesty machine

Most retail finance tools show you a backtest and ask you to trust it. Aegis assumes backtests lie (ours did — see below) and runs the discipline instead:

- **Pre-registered trials.** Every signal, strategy, or overlay gets a written hypothesis, primary metric, decision rule, and earliest decision date *before* it accrues data (`docs/TRIALS/`). If it isn't pre-registered, it didn't happen.
- **Forward paper lanes.** Ten paper portfolios ($100k each) marked to market daily since inception **2026-06-08**: four reference lanes (conservative, balanced-HRP, aggressive, equal-weight control), two book lanes (mirror + conviction), an ATR exit-overlay lane, a small/mid-quality lane, and a TSMOM overlay pair (treatment + 60/40 control). NAV accrues only with elapsed time and cannot be cherry-picked.
- **Decision clocks, not vibes.** TRIAL-001 (HRP vs equal-weight) reads out no earlier than **June 2027**. The project makes **no skill claims before 24 months** of forward record. Period.
- **Published negative results.** The signal engine *loses* to buy-and-hold as a timing tool. The 12-month crash model has no skill. LPPLS bubble timing was refuted twice. A survivorship-free backtest universe is not buildable on free data — so no backtested alpha claim here is trustworthy, and we say so. [Read them all.](NEGATIVE_RESULTS.md)
- **Overfitting guards — themselves calibrated.** Deflated Sharpe, PBO, Harvey-Liu thresholds, and purged cross-validation are computed for every candidate. In Aug 2026 we ran the whole decision ladder against synthetic markets with *known* injected edges (GATE-M1) and found our own gates had ~0% power — so the ladder was recalibrated to a **measured** 1.6% false-discovery rate, with DSR/PBO reported as diagnostics rather than pretending they gate ([NEGATIVE_RESULTS §34](NEGATIVE_RESULTS.md)). Even a "pass" goes to human review, never auto-adoption.

Every idea walks the same gauntlet — and most die, cheaply and on the record:

```mermaid
flowchart LR
    IDEA([Idea]) --> CORPSE{Corpse check vs<br/>335+ prior trials}
    CORPSE -->|match found| DEAD[Refused —<br/>it already has a corpse]
    CORPSE -->|pass| PREREG[Pre-registration<br/>frozen in a commit<br/>BEFORE any data]
    PREREG --> RUN[Run — every arm prints<br/>its own 80%-power MDE]
    RUN --> PLACEBO{Placebos<br/>clean?}
    PLACEBO -->|no| VOID[VOID — disclosed<br/>with its numbers,<br/>never deleted]
    PLACEBO -->|yes| BAR{Clears its<br/>own MDE?}
    BAR -->|no| NR[NEGATIVE_RESULTS.md /<br/>NOT_DETECTABLE]
    BAR -->|yes| FWD[Forward paper lane —<br/>reality decides,<br/>24-month clock]
    style DEAD fill:#7f1d1d,color:#fff
    style VOID fill:#7f1d1d,color:#fff
    style NR fill:#78350f,color:#fff
    style FWD fill:#14532d,color:#fff
```

## The brain, in one picture

The system is converging on a specific architecture: **the LLM perceives, the
engine computes, learned models forecast, Aegis referees, and reality grades
everyone** — in a loop.

```mermaid
flowchart TB
    subgraph WORLD["🌍 The world"]
        NEWS[News · SEC filings ·<br/>public disclosures]
        MKT[Prices · options ·<br/>fundamentals · revisions]
        MACRO[FRED macro ·<br/>net liquidity]
    end
    subgraph PERCEIVE["🧠 Perception (LLM)"]
        EV[Event extraction<br/><i>what changed?</i>]
        REL[Relation graph<br/><i>who affects whom?</i>]
        IIF[Autonomous investigator<br/><i>IIF-1 — armed, 0/40 valid nights</i>]
    end
    subgraph ENGINE["⚙️ Engine (numbers)"]
        PIT[Point-in-time store<br/><i>nothing peeks at the future</i>]
        TEACH[Teacher Library<br/><i>insiders · funds · politicians</i>]
        MODELS[ML: crash · Monte Carlo ·<br/>factors · regimes]
    end
    subgraph REFEREE["⚖️ Aegis (the referee)"]
        DISC[Pre-registration · MDE ·<br/>placebos · read gates]
    end
    LANES[📈 Paper lanes — daily NAV,<br/>hash-pinned configs,<br/>since 2026-06-08]
    REALITY([Reality grades everything])
    WORLD --> PERCEIVE
    WORLD --> ENGINE
    PERCEIVE --> ENGINE
    ENGINE --> DISC
    PERCEIVE --> DISC
    DISC --> LANES
    LANES --> REALITY
    REALITY -->|resolved outcomes<br/>feed back| PERCEIVE
    REALITY -->|calibration| ENGINE
```

## How to read the evidence here

This project mixes four very different kinds of evidence, and confusing them
is how finance projects mislead people. Every claim on this page carries one
of these badges:

| Badge | Meaning |
|---|---|
| 🟢 **LIVE FORWARD** | Happened *after* the rule was frozen. No hindsight possible. |
| 🟡 **FORWARD TRIAL** | Pre-registered experiment currently collecting evidence — verdict pending. |
| ⚪ **ARMED** | Machinery built and pre-registered, but **nothing has accrued yet**. Distinct from 🟡 on purpose: "the apparatus runs" and "evidence is arriving" are different claims, and conflating them is how a project sounds further along than it is. |
| 🔵 **BACKTEST** | Historical simulation. Useful for direction-finding, vulnerable to hindsight. Never an alpha claim here. |
| 🟣 **ORACLE** | A deliberately *impossible* benchmark that is allowed to see the future. Measures the ceiling on how valuable an information source could ever be — not performance. |
| 🔴 **REFUTED** | Tested and failed its pre-defined bar. Kept public. |
| 🔶 **EXPLORATORY** | Interesting observation, not yet evidence. |

## The story so far, in one paragraph

We built a market timer 🔵. It detected danger correctly — and still lost
badly to buy-and-hold, because *recognizing risk* and *predicting returns*
turned out to be different problems. So we rebuilt the project around finding
where useful information actually lives: measurement showed **magnitude and
risk look far more forecastable than direction**; an LLM reading SEC filings
turned out to know **how companies are economically connected** in ways price
history doesn't 🟡→✅; an oracle test 🟣 then showed one obvious use of that
knowledge (better covariance matrices) is a dead end even with perfect
information — so the live experiments now test the uses that remain. Paper
portfolios 🟢 will eventually say whether any of it makes money. No verdict
before its clock.

## Scoreboard — what the research has actually established (through Aug 2026)

The questions this project has spent real compute answering, with the honest
verdicts. Receipts for every row live in [`docs/`](docs/README.md).

| Question | Verdict | Receipt |
|---|---|---|
| Can an LLM pick stocks directly? | 🔴 No evidence — measured role: presentation & research assistance | 16,320 graded decisions 🔵; ablation p=0.105–0.185; ~40% of apparent effect reproduced by permuted noise |
| Do 14 specialist LLM personas beat one generic agent? | 🔴 No — retired | 0.49 vs 0.85 effective distinct ideas, at 5.2× the calls |
| Does the LLM know **economic relationships** the correlation matrix doesn't? | ✅ **Yes — the campaign's one clean positive** 🔵 (architecture result, not a trading claim) | MARKET-GRAPH-1: t = 4.35 vs its own MDE, every placebo intact |
| Does that graph improve a covariance/risk model? | 🔴 Closed, for $0 — even a cheating model that *sees* future correlations ties the ordinary trailing matrix 🟣 | GRAPH-COVARIANCE-1: oracle vs sample \|t\| = 0.23; industry diagonal −86.6% |
| Does autonomous internet investigation beat a data snapshot? | ⚪ **Armed — first valid night pending (0/40 graded).** Night 1 spent $0.066 and VOIDed itself on its own information guard; nothing has accrued | INTERNET-INVESTIGATOR-FWD-1 · [receipt](backend/data/optimus/iif1_nights/2026-08-14.json) |
| Do public actors' disclosed trades carry structure? | ⚪ **Paper lanes seeded — production ingestion pending.** 2 lanes live, 12 declared inactive; no production collector yet, so no new teacher signal can arrive | Track E + COPY-LAB |
| Where does Aegis currently see the strongest forecasting opportunity? | 📐 **Magnitude, volatility and risk appear substantially more promising than return direction** — three independent measurements point the same way | exposure-oracle gap 🟣 · covariance closure 🟣 · σ_π decomposition 🔵 |
| When a decision failed, can Aegis say *where* it failed? | ⚪ **Machinery built, first dataset dissected.** Every decision becomes an episode replayed under 17 alternative policies; failures are classified perception / inference / action / timing / sizing / cost | [RESEARCH-GYM-1](docs/RESEARCH_GYM_1.md) — **Gym output is never evidence**, by charter and by a type that refuses to render as a claim |

### The findings, in pictures

*Same generator as the September figures above:
[`tools/readme_charts.py`](tools/readme_charts.py) — numbers are read, never retyped.*

![The one clean positive: the semantic graph clears its MDE while both placebos sit at zero](docs/assets/finding_market_graph.png)

![The honest closure: perfect foresight of forward correlation ties the trailing sample matrix](docs/assets/finding_covariance_ladder.png)

<details>
<summary><b>What is an "oracle" and why test one? (plain English)</b></summary>

An oracle 🟣 is a deliberately **impossible** model — it's allowed to see the
future. It is not Aegis, not a strategy, and can never be traded. Its job is
to answer one question before money gets spent: *even if God told us this
particular variable, would knowing it actually help?*

Weather-stand version: before spending six months building a temperature AI
for your ice-cream stand, hand the system *tomorrow's actual temperature*.
If profits barely move, temperature wasn't the valuable information — no
forecaster can beat the oracle that already knew the answer.

Aegis has run this test twice, with opposite answers:

- **Covariance oracle** (chart above): a portfolio built with *perfect
  knowledge of future correlations* was statistically **tied** with one
  built from ordinary trailing history (\|t\| = 0.23). Verdict: stop
  researching correlation predictors for this objective — the information
  itself isn't worth enough. Door closed for $0.
- **Exposure oracle**: knowing *when to take market risk* was worth
  **+21.6 pp/yr** — over ten times its detection bar — but our best
  real-world (non-cheating) controller captured only ~7% of it. Verdict:
  the information is enormously valuable and remains mostly uncaptured —
  keep researching.

Same test, two doors: one closed forever, one confirmed worth walking
through. That's what oracles are for.

</details>

![Why Aegis is prioritizing magnitude over direction](docs/assets/finding_direction_vs_magnitude.png)

<details>
<summary><b>What does "magnitude vs direction" mean? (plain English)</b></summary>

**Direction** asks: *which way* will the stock move? ("NVDA will be UP over
the next 5 days.")

**Magnitude** asks: *how big* will the move be, either way? ("NVDA will
probably move more than 5% this week" — +8% and −8% both count.)

The chart shows why the distinction matters: across 927,423 stock-day
observations, the true probability of a big move varies hugely from stock to
stock (some names have a 5% chance of a >5% week, others 44%), while the
probability of an *up* move barely varies at all (roughly 52% for
everything). Simply: **predicting whether a stock will move a lot appears
much easier than predicting whether it moves up or down.**

Knowing magnitude without direction is still valuable — it drives position
sizing, options pricing, risk limits, hedging, stop distances, and expected
drawdown. And if any other signal supplies even a weak directional lean,
magnitude multiplies its value. This is why the project moved from "AI
predicts BUY/SELL" toward "AI + numeric models describe the *distribution*
of what might happen."

</details>

## Historical backtests: what worked, what didn't

> 🔵 **HISTORICAL BACKTEST — NOT FORWARD PERFORMANCE.** Shown because the
> failure taught the project more than a win would have. Full numbers:
> [`backend/BACKTEST_RESULTS.md`](backend/BACKTEST_RESULTS.md) ·
> [`NEGATIVE_RESULTS.md §1`](NEGATIVE_RESULTS.md)

| Historical experiment (2020-01 → 2025-06) | Aegis | Benchmark | What we learned |
|---|---:|---:|---|
| Signal-engine timing strategy, total return | **+250.9%** | **+740.0%** (buy & hold) | Stress detection ≠ market timing |
| Sharpe ratio | 0.675 | 0.921 | Sitting out rebounds costs more than dodging drawdowns saved |
| Buy-signal 3-month hit rate | **67.4%** | target >60% ✓ | Some real directional information on entries |
| Sell-signal 3-month hit rate | **28.6%** | target >55% ✗ | Sell signals fired at VIX>25 — historically the *best buying opportunities* |

The mechanism of the failure is the interesting part. The engine was
genuinely good at detecting that the market was under stress — and then made
the classic mistake of translating *"the market is dangerous right now"*
into *"therefore sell."* Those are different predictions. April 2020: the
engine issued SELL at VIX 57; the next three months returned **+26.1%**. By
the time stress is extreme enough to scream, expected forward returns are
often improving, not deteriorating.

That failure split one question into two, and the split now organizes the
whole project:

1. **Can Aegis recognize danger?** — yes, measurably.
2. **Can Aegis make money *because* it recognized danger?** — that is a
   different claim, it failed here, and nothing on this page asserts it.

The engine survives as a **risk-awareness system**, not a timing system —
and the research program went hunting for where information actually lives
instead (see the scoreboard above).

## What it does

**Market intelligence**
- Macro risk dashboard: 9-factor composite score from FRED data, regime detection (Bull/Bear/Volatile/Neutral)
- Fragility composite: LPPLS + systemic stress + Sahm rule + turbulence + net liquidity + credit spreads (descriptive — it never fires trades)
- News intelligence (GDELT + FinBERT sentiment), economic surprise index, net liquidity tracker

**Stock analysis**
- Per-ticker Monte Carlo projections (Merton jump-diffusion, GJR-GARCH vol, Student-t innovations)
- SHAP explainability on every prediction — you see *why*, not just *what*
- Screener with signals across 150+ names; options-implied intelligence (IV skew, put/call, max pain); earnings, insider, technicals, valuation

**Portfolio tools**
- Builder: Black-Litterman, Hierarchical Risk Parity, Mean-CVaR, Risk Parity (riskfolio-lib), goal-based templates
- Analytics: Brinson-Fachler attribution, MCTR risk budgeting, FF5+momentum factor decomposition, drawdown recovery, stress testing (GFC, COVID, dot-com replays)
- Retirement: Monte Carlo simulation with contributions/withdrawals, safe-withdrawal-rate calculator

**The forward track record**
- 10 paper lanes with daily NAV, tamper-evident config hashes, and a public track-record API
- Forward information-coefficient trials on selection signals: insider Form 4 clusters, analyst revision momentum, multi-factor composite

**Data collectors (point-in-time, leak-free)**
- SQLite PIT store with `observed_at` stamps so nothing can peek at the future
- Congressional trading disclosures (Senate + House, by disclosure date), **ARK daily fund flows** (6 funds), EDGAR 13F, SEC Form 4 insider filings — all validated forward, never by backtest

**Behavioral guidance**
- Per-position guidance: levels, signals, and nudges against the classic mistakes (selling winners early, averaging into losers)

## What it does NOT do

- **Not financial advice.** Educational tool, disclaimers everywhere, consult a professional.
- **Not a trading bot.** No execution, no live orders, no position sizing for real money.
- **No alpha claims.** The pre-registered clocks haven't matured; until they do, the honest answer to "does it beat the market?" is *we don't know yet, and here's the live experiment that will tell us*. Our own backtest showed the timing signals underperforming buy-and-hold — we published it: [NEGATIVE_RESULTS.md](NEGATIVE_RESULTS.md).
- **Not real-time.** Data refreshes hourly, not tick-by-tick.

## Quickstart

Prerequisites: Python 3.12+, Node.js 20+, a free [FRED API key](https://fred.stlouisfed.org/docs/api/api_key.html).

```bash
git clone https://github.com/Murathanx12/Aegis-Finance.git
cd aegis-finance
cp .env.example .env   # add your FRED_API_KEY

# Backend
cd backend && pip install -r requirements.txt && cd ..
uvicorn backend.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:3000 — API health at http://localhost:8000/api/health.

Or run the full stack with Docker: `docker compose up --build`

### Environment keys

| Key | Required | Enables | Get it |
|-----|----------|---------|--------|
| `FRED_API_KEY` | **Yes** | Macro data (the core) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) (free) |
| `DEEPSEEK_API_KEY` | No | AI news summaries | [platform.deepseek.com](https://platform.deepseek.com/) |
| `FINNHUB_API_KEY` | No | Extra fundamentals | [finnhub.io](https://finnhub.io/) |
| `FMP_API_KEY` | No | Congressional trades collector | [financialmodelingprep.com](https://financialmodelingprep.com/) |

### Tests

```bash
# Fast suite (~3,800 tests, offline — network calls are blocked by design)
python -m pytest backend/tests/ -m "not slow"

# Everything (slow tests need network)
python -m pytest backend/tests/
```

## Architecture

```
Next.js 14 (Vercel)  ──REST──►  FastAPI (Railway)
                                 ├─ 28 routers / 130+ endpoints
                                 ├─ 100+ services (MC, crash, portfolio, factors…)
                                 ├─ APScheduler → daily lane marks + PIT collectors
                                 └─ SQLite PIT store + paper-lane NAV (persistent volume)
Data: Yahoo Finance · FRED · SEC EDGAR · GDELT · Kenneth French · Polygon · FMP · ARK
```

- **Frontend:** Next.js 14 (App Router), shadcn/ui, Tailwind, Recharts
- **Backend:** FastAPI, Python 3.12, in-memory TTL cache, stateless except the track record
- **ML/stats:** LightGBM, scikit-learn, SHAP, GJR-GARCH, HMM, copulas, riskfolio-lib, FinBERT
- **Track record:** APScheduler marks the paper lanes daily; lane configs are hash-pinned so any tampering is detectable
- **Offline research:** `engine/` (training, purged CV, walk-forward) — not served by the API

## The track record, precisely

![Paper lanes vs SPY, all ten on one axis](docs/assets/paper_lanes_vs_spy.png)

🟢 **LIVE FORWARD** — *the same data as the small-multiples chart above, on one
axis. Regenerated from the public track-record API by `tools/readme_charts.py`.
Read the title's caveat before reading the lines: at this window the standard
error on an annualized Sharpe is ±2.1, so ordering is noise — including against
SPY.*

| Fact | Value |
|---|---|
| Paper lanes | 10 ($100k each, daily NAV) |
| Inception | 2026-06-08 |
| First decision date | TRIAL-001 (HRP vs EW): June 2027 |
| Skill-claim policy | None before 24 months of forward record |
| Registry | All trials pre-registered in `docs/TRIALS/` + experiment registry |

Replay and comparison endpoints are methodology backtests, not the track record — the policy is written down in [`docs/TRACK_RECORD_POLICY.md`](docs/TRACK_RECORD_POLICY.md).

## Repo map — where things live

```
aegis-finance/
├── README.md              ← rung 1 of the ladder (you are here)
├── CLAUDE.md              ← operating rules for agents; TIER 0
├── NEGATIVE_RESULTS.md    ← 35+ documented dead ends. The most reusable artifact here.
│
├── backend/               FastAPI service — what the website actually runs
│   ├── main.py            app + APScheduler (daily lane marks, PIT collectors)
│   ├── config.py          EVERY parameter lives here — never hardcode in a service
│   ├── routers/           28 routers / 130+ endpoints (track record, health, screener…)
│   ├── services/          100+ stateless services (Monte Carlo, crash, factors, portfolio)
│   ├── tests/             the fast suite — OFFLINE and un-hangable by design
│   └── data/optimus/      RECEIPTS. Every headline number in this repo resolves here.
│       └── tracker_backtest/   learner_v1 · holder H2/H3 · analyst grades · band prior
│
├── learner/               the learned layer: dataset, prior, models, calibration,
│                          shadow scoring, unsupervised states. Driven by scripts/learner_run.py
├── engine/                offline research — training, purged CV, walk-forward. Not served.
├── scripts/               one-shot research runs, each writing ONE receipt
│                          (portfolio_farm_run · learner_run · band_horizon_run · llm_cost_audit)
├── lab/                   the autonomous overnight R&D loop
├── tools/                 readme_charts.py — every figure in this README
├── sdk/                   pip-installable Python client for the REST API
├── frontend/              Next.js 14 app (Vercel), shadcn/ui + Tailwind + Recharts
└── docs/                  268+ files. ENTER AT docs/INDEX.md, never by grep.
    ├── INDEX.md           the tiered map — rung 2
    ├── AEGIS_STRATEGIC_INVARIANTS.md   TIER 0, outranks every roadmap
    ├── DATA_MANIFEST.md   what is deliberately NOT committed, and how to rebuild it
    ├── TRIALS/            pre-registrations with decision dates
    ├── assets/            generated figures (never hand-edited)
    └── archive/           a diary, not a source of truth
```

**The one repo-shaped thing to know:** live execution — the six paper books, the
ledger, the order path — is a **different repository**
(`aegis-alpha-terminal` locally, `github.com/Murathanx12/investing-bot-test-`
public). Commits move between the two by hand, and a commit hash quoted in a
handoff belongs to whichever repo that handoff lives in.

## Research corpus — start here (humans and AI agents)

This repo doubles as an open research record. If you're studying retail-scale quant research discipline — or you're an AI agent asked to review, extend, or learn from this project — read in this order. (For the short version, use the [skim → read ladder](#start-here--the-skim--read-ladder) at the top; this table is the by-question index.)

| You want… | Read |
|---|---|
| **The tiered map of everything — the one entry point** | [`docs/INDEX.md`](docs/INDEX.md) · [`docs/README.md`](docs/README.md) (older topic map, kept for its campaign tables) |
| **The invariants that outrank every roadmap** | [`docs/AEGIS_STRATEGIC_INVARIANTS.md`](docs/AEGIS_STRATEGIC_INVARIANTS.md) |
| **The newest results and their receipts** | INDEX → "NEWEST" section · [`learner_v1.json`](backend/data/optimus/tracker_backtest/learner_v1.json) · [`RETRO_2026-09-02_THE_MONTH_OF_DATA.md`](docs/RETRO_2026-09-02_THE_MONTH_OF_DATA.md) · [`HYPOTHESES_2026-09-02_HARVEST.md`](docs/HYPOTHESES_2026-09-02_HARVEST.md) · [`REDTEAM_2026-09-02_ENGINE_AUDIT.md`](docs/REDTEAM_2026-09-02_ENGINE_AUDIT.md) |
| The complete project state: timeline, all 179 screened candidates, every bug found, testing infrastructure | [`docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md`](docs/AEGIS_FINANCE_DOSSIER_2026-08-02.md) |
| What did NOT work (35+ documented dead ends — the most reusable artifact here) | [`NEGATIVE_RESULTS.md`](NEGATIVE_RESULTS.md) |
| The current research direction | [`docs/INDEX.md`](docs/INDEX.md) — TIER 1 names the one active roadmap. (The old link here, `docs/ROADMAP_BRAIN_V3_2026-08-14.md`, moved to [`docs/archive/`](docs/archive/ROADMAP_BRAIN_V3_2026-08-14.md) and is no longer current.) |
| Which large datasets exist but are deliberately not committed, and how to rebuild them | [`docs/DATA_MANIFEST.md`](docs/DATA_MANIFEST.md) |
| The older gated fail-fast roadmap (data cert → method cert → trials) — superseded by TIER 1, kept as a receipt | [`docs/AEGIS_EXECUTION_ROADMAP.md`](docs/AEGIS_EXECUTION_ROADMAP.md) |
| Five external AI reviews of this project, cross-verified, with their errors flagged | [`docs/AI_REVIEWS_SYNTHESIS_2026-08-03.md`](docs/AI_REVIEWS_SYNTHESIS_2026-08-03.md) + raw inputs in [`docs/external-reviews/`](docs/external-reviews/) |
| The house rules (pre-registration, placebo gates, LLM-narrates-engine-computes) | [`docs/CANON.md`](docs/CANON.md) · [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) |
| Pre-registered trials with decision dates | [`docs/TRIALS/`](docs/TRIALS/) |
| A ready-made hostile-review prompt to point your own AI at this repo | [`docs/AI_RESEARCH_PROMPT.md`](docs/AI_RESEARCH_PROMPT.md) |

Reusable findings that cost us weeks so they can cost you minutes: LIMIT-truncated WRDS extracts look complete but aren't (count at source, always); `rank(method="first")` + `qcut` fabricates quantile spreads from constant factors (alphabetically); FRED series must be aligned on *publication* date, not reference date; a collector that writes zeros on failed fetches will pass every unit test and poison every downstream trial; and uniform random-date placebo gates can falsely kill real signals under cohort drag — permute across firms, keep the calendar.

## Contributing

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). One house rule above all: nothing touches the paper-lane NAV write path, and no strategy gets evaluated without pre-registration. Deeper docs live in `docs/` (`METHODOLOGY.md`, `STATE_OF_THE_REPO.md`, `CAPABILITY_MATRIX.md`, `BACKLOG.md`).

## License

[MIT](LICENSE)

---

*All outputs are probabilistic estimates with significant uncertainty. Past performance does not guarantee future results. The negative results are not a reason to distrust this project — they are the reason to trust it.*
