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

**Paper accounts, 2026-09-26:** 229 tracked; 39 priced — $4,679,959 on $4,733,154 (**-1.12%**); 7 ahead of SPY over their own window, 32 behind, 182 pending. Every row: [`docs/PAPER_ACCOUNTS.md`](docs/PAPER_ACCOUNTS.md) · [chart](#the-track-record-precisely) · `GET /api/pi/paper-accounts`. None of it is a claim.

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

> 🔵 **HINDSIGHT BACKTEST — NOT FORWARD PERFORMANCE.** Every rule below was written down on 2026-09-26, after every month it is scored on. The quotable record starts at registration. Receipt for every number in this section: `backend/data/optimus/strategy_library/leaderboard_2026-09-26T093458Z.json` at commit `1dd91a78` (run `2026-09-26T093458Z`; rendered as `backend/data/optimus/strategy_library/LEADERBOARD.md`, which the next run refreshes -- the receipt it cites is never overwritten); forward results: `docs/BRIDGE.md`.

The strategy library (277 rules in 31 families, 834 cells at k = 10/20/50 plus each rule's own k) was run on survivorship-free bars net of a band round-trip cost, with a split declared in code before the ranking: **dev** = monthly periods entered through 2023-12-31, and the **2024-26 selection window (split declared, data seen)** = entered from 2024-01-01 (32 monthly blocks). Every rule was written in 2026, so the second window is where the board SORTS, not a holdout. Sorted by net return vs SPY in that window (`backend/data/optimus/strategy_library/leaderboard_2026-09-26T093458Z.json`, `top_by_sealed_vs_spy`):

| rule (k=20) | dev CAGR | SPY dev | 2024-26 CAGR | SPY 2024-26 | 2024-26 − SPY | DSR (834 cells) | LOO-worst mean active/mo | top-5-month share | max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `mom_12_1_liqw` | +7.0% | +13.2% | +89.4% | +21.0% | **+68.4%** | 0.034 | +0.67% | 0.91 | -70.6% |
| `qc372_oversold_snapback_mega` | +12.2% | +13.2% | +80.4% | +21.0% | **+59.4%** | 0.072 | +0.96% | 0.52 | -68.7% |
| `rev_5d` | +2.8% | +13.2% | +69.4% | +21.0% | **+48.4%** | 0.005 | +0.10% | 1.08 | -66.5% |
| `qc623_mom63_liquidity_weighted` | +12.2% | +13.2% | +67.3% | +21.0% | **+46.3%** | 0.026 | +0.92% | 0.74 | -58.9% |
| `mom_12_1_q` | +34.2% | +13.2% | +58.9% | +21.0% | **+37.9%** | 0.202 | +1.52% | 0.44 | -35.9% |
| `skill_mom` | +17.9% | +13.2% | +58.0% | +21.0% | **+37.0%** | 0.101 | +0.69% | 0.40 | -27.3% |
| `margin_mom` | +14.0% | +13.2% | +57.9% | +21.0% | **+36.9%** | 0.037 | +0.33% | 0.58 | -51.0% |
| `qc395_sharpe252_above_trend_large` | +26.8% | +13.2% | +56.2% | +21.0% | **+35.2%** | 0.116 | +1.10% | 0.48 | -32.6% |
| `illiquid` | -2.0% | +13.2% | +55.9% | +21.0% | **+34.9%** | 0.002 | -0.25% | 1.44 | -80.7% |
| `qc470_mom252_quarterly_riskparity` | +25.9% | +13.2% | +52.1% | +21.0% | **+31.1%** | 0.090 | +1.03% | 0.51 | -47.7% |

Random controls (k=20 names drawn at random each month, never ranked) land at -10.6% to -1.8% vs SPY in the 2024-26 window: that is the luck bar (`backend/data/optimus/strategy_library/leaderboard_2026-09-26T093458Z.json`, `controls`, family `control`).

- **The one out-of-sample number the backtest holds:** choosing the top 10 rules by dev (pre-2024) results alone gave **+4.5 pp/yr** mean vs SPY in the 2024-26 selection window (split declared, data seen) (median **-1.6 pp**; 5 of 10 beat SPY); dev-to-2024-26 rank Spearman **0.17** over 277 rules; at a median active sigma of 5.4%/month, 32 blocks give an MDE of 2.7%/month at 80% power -- the window can kill a rule, not certify one (`backend/data/optimus/strategy_library/leaderboard_2026-09-26T093458Z.json`, `dev_selected_sealed_evaluated`). No forward day graded yet; the first 21-session reading is the 2026-10-26 close.
- **Nothing passes the multiplicity bar (best DSR 0.20 at 834 cells, `mom_12_1_q`, vs 0.95).** Ranking 834 cells on 32 months of the 2024-26 window selects luck as readily as skill (`backend/data/optimus/strategy_library/leaderboard_2026-09-26T093458Z.json`, `multiplicity`).
- **104 of 277 rules beat SPY in the 2024-26 window, median -3.9%** (`backend/data/optimus/strategy_library/leaderboard_2026-09-26T093458Z.json`, `all_rows[].sealed_vs_spy`).
- **62 of 277 rules beat SPY in both windows** (dev and 2024-26); 35 of them also have a top-5-month share < 0.6 and max DD better than -40%. Only `mom_12_1_q`, `skill_mom`, `qc395_sharpe252_above_trend_large`, `qc470_mom252_quarterly_riskparity` are in both the 2024-26 top-10 and the full-window DSR top-10. The 2024-26 top rows with a top-5-month share near or above 1 made their return in a handful of months, and several were flat or negative in dev (`backend/data/optimus/strategy_library/leaderboard_2026-09-26T093458Z.json`).
- **6 of these 10 rows have a $1M forward paper book frozen 2026-09-26; entry is the 2026-09-28 open** (`qc372_oversold_snapback_mega`, `qc623_mom63_liquidity_weighted`, `qc395_sharpe252_above_trend_large`, `qc470_mom252_quarterly_riskparity` entered this top-10 after the freeze and have none) (books in `backend/data/optimus/llm_portfolio/books.jsonl`, `lib_<id>_sealed_2026-09-26` with ew / sector-ETF / SPY / random-same-band twins; `mom_12_1_q`'s is the 02:00 factory's `lib_mom_12_1_q_2026-09-26`, same names; freeze log `backend/data/optimus/bridge/freeze_2026-09-26.json`). `docs/BRIDGE.md` shows expectation vs result. The freeze gate (selection, construction and timing booleans, `backend/data/optimus/bridge/freeze_gate_2026-09-26.json`) passes 0 of 20 library books (bridge receipt `backend/data/optimus/bridge/bridge_2026-09-26.json`); the rest are CONTROLs, not headlines. `lib_mom_12_1_liqw_sealed_2026-09-26` was **voided before entry** (VOID_BEFORE_ENTRY: concentration (effN 2.0, MU 60.3% + SNDK 37.2% = 97.5%, rho 0.90, MU prints 09-30 inside the first 5 sessions)); its `__ew` twin is the strategy test.
- The 2024-26 top-10 monthly series were recomputed from their holdings and the raw bars -- a re-implementation of the arithmetic from raw bars, not an independent engine (shares holdings, fills, cost formula): `backend/data/optimus/strategy_library/replication_vectorbt_2026-09-26T093458Z.json`.

### History: the timing strategy (not the library)

The row this section used to lead with measured the 2020-01 → 2025-06 signal-engine TIMING strategy, not any library rule (receipt `backend/BACKTEST_RESULTS.md`, re-measured 2026-09-04):

| Historical experiment (2020-01 → 2025-06) | Aegis | Benchmark | What we learned |
|---|---:|---:|---|
| Signal-engine timing strategy, total return (`backend/BACKTEST_RESULTS.md`) | **+28.3%** net | **+114.8%** (SPY total return) | Stress detection ≠ market timing — the strategy keeps a quarter of the market |

The engine was good at detecting that the market was under stress and then translated *"the market is dangerous"* into *"therefore sell"* — two different predictions. It survives as a **risk-awareness system**, not a timing system (`backend/BACKTEST_RESULTS.md`, [`NEGATIVE_RESULTS.md §1`](NEGATIVE_RESULTS.md)).

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

![Every priced paper account vs SPY over its own window](docs/assets/paper_accounts_roi_latest.png)

🟢 **LIVE FORWARD** — every paper account Aegis runs, one row each, ROI since the account's *own* inception against SPY compounded over the *same* window (`learner.benchmark`, the one ruler). Regenerated by `python -m scripts.paper_accounts_roi`; full table (all 229 rows, including the control twins and the `llm_portfolio` books) in [`docs/PAPER_ACCOUNTS.md`](docs/PAPER_ACCOUNTS.md); receipt [`roi_2026-09-26.json`](backend/data/optimus/paper_accounts/roi_2026-09-26.json); API `GET /api/pi/paper-accounts`.

**Measured 2026-09-26.** All 39 priced accounts: **$4,679,959** vs **$4,733,154** started (**-1.12%**); excluding control twins (25): **-1.53%**. Of 39 priced accounts with an own-window SPY leg, 7 are ahead of SPY and 32 behind (excluding control twins: 5 ahead, 20 behind); 182 are PENDING (not yet entered), 7 UNGRADED, 1 CREDENTIAL_INVALID, 0 UNPRICED.

| account | family | inception | start | equity | ROI | SPY same window | vs SPY | status |
|---|---|---|---:|---:|---:|---:|---:|---|
| conservative-atr | website_lane | 2026-06-17 | $100,000 | $104,851 | +4.85% | +3.32% | +1.53 pp | LIVE |
| aggressive | website_lane | 2026-06-08 | $100,000 | $102,760 | +2.76% | +3.56% | -0.80 pp | LIVE |
| tsmom-overlay | website_lane | 2026-07-27 | $100,000 | $102,401 | +2.40% | +3.31% | -0.91 pp | LIVE |
| conservative | website_lane | 2026-06-08 | $100,000 | $101,867 | +1.87% | +3.56% | -1.70 pp | LIVE |
| balanced | website_lane | 2026-06-08 | $100,000 | $101,755 | +1.75% | +3.56% | -1.81 pp | LIVE |
| tsmom-6040-control | website_lane | 2026-07-27 | $100,000 | $100,964 | +0.96% | +3.31% | -2.35 pp | LIVE |
| balanced-ew-control | website_lane | 2026-06-10 | $100,000 | $100,555 | +0.56% | +5.53% | -4.97 pp | LIVE |
| smallmid-quality | website_lane | 2026-07-22 | $100,000 | $94,022 | -5.98% | +2.16% | -8.14 pp | LIVE |
| conviction | website_lane | 2026-06-16 | $100,000 | $91,745 | -8.26% | +2.03% | -10.28 pp | LIVE |
| mirror | website_lane | 2026-06-16 | $100,000 | $77,842 | -22.16% | +2.03% | -24.19 pp | LIVE |
| hack2 | alpaca_fleet | 2026-08-28 | $100,000 | $98,820 | -1.18% | +0.28% | -1.46 pp | LIVE |
| hack5 | alpaca_fleet | 2026-08-28 | $100,000 | $95,053 | -4.95% | +0.28% | -5.23 pp | LIVE |
| hack1 | alpaca_fleet | 2026-08-28 | $100,000 | $91,527 | -8.47% | +0.28% | -8.75 pp | LIVE |
| hack6 | alpaca_fleet | 2026-08-28 | $100,000 | $82,298 | -17.70% | +0.28% | -17.98 pp | LIVE |
| hack4 | alpaca_fleet | 2026-08-28 | $100,000 | $79,828 | -20.17% | +0.28% | -20.45 pp | LIVE |
| hack3 | alpaca_fleet | — | $100,000 | — | — | — | — | CREDENTIAL_INVALID |
| PC-PAPER | pc_paper | 2026-09-22 | $1,000,000 | $999,054 | -0.10% | -0.28% | +0.18 pp | LIVE |
| Cash/index by default; deviate only above a  [b109c886] | night_books | 2026-09-11 | $100,000 | $110,099 | +10.10% | +1.46% | +8.64 pp | LIVE |
| Always invested - Book D's primary comparato [3b3e7049] | night_books | 2026-09-11 | $100,000 | $110,099 | +10.10% | +1.46% | +8.64 pp | LIVE |
| 12-1 momentum, k=12, equal weight, monthly [8dbbb73b] | night_books | 2026-09-11 | $100,000 | $103,978 | +3.98% | +1.46% | +2.52 pp | LIVE |
| Low short interest, high turnover, long-only [1934ec97] | night_books | 2026-09-11 | $100,000 | $100,000 | +0.00% | +1.46% | -1.46 pp | LIVE |
| Insider SAME-DAY clusters - the falsifier ar [4359eba8] | night_books | 2026-09-11 | $100,000 | $100,000 | +0.00% | +1.46% | -1.46 pp | LIVE |
| Insider cluster buys, 4-5 day clusters, long [625c3919] | night_books | 2026-09-11 | $100,000 | $100,000 | +0.00% | +1.46% | -1.46 pp | LIVE |
| Good-news names in the top overhang tercile, [a82e6e45] | night_books | 2026-09-11 | $100,000 | $100,000 | +0.00% | +1.46% | -1.46 pp | LIVE |
| The UNCONDITIONED reaction book - Book C's p [c3adfbc0] | night_books | 2026-09-11 | $100,000 | $100,000 | +0.00% | +1.46% | -1.46 pp | LIVE |
| First hour after a natively-stamped headline [f64e8d99] | night_books | 2026-09-12 | $100,000 | — | — | — | — | UNGRADED |
| murat_live | murat_book | 2026-08-11 | $33,154 | $32,477 | -2.04% | +0.63% | -2.67 pp | LIVE |
| AGENCY_BOOK:aggressive | agency | — | — | — | — | — | — | UNGRADED |
| AGENCY_BOOK:balanced | agency | — | — | — | — | — | — | UNGRADED |
| AGENCY_BOOK:extreme_growth | agency | — | — | — | — | — | — | UNGRADED |

Not in the table above: 17 night-book control twins (in aggregate -0.15%) and 182 `llm_portfolio` books + twins ($1M each), all **PENDING — entry 2026-09-28**. The website lanes' NAV was last marked **2026-09-18** on the deploy (it expected 2026-09-25, `all_fresh: false`), so their rows are a week stale. hack3 was retired on 2026-09-22 and its key now answers 401 — reported as `CREDENTIAL_INVALID`, not $0.

**Read these before the numbers.** Nothing here is a claim: every account runs under `PRODUCT_EXPERIMENT`, and at windows of weeks to months the standard error is wider than every gap, including the gap to SPY. `mirror`'s −22% is its book's real performance — concentrated idiosyncratic risk — and stays on the record on purpose. The Alpaca fleet (hack1–6) are the competition books of the separate `aegis-alpha-terminal` repo.

| Fact | Value |
|---|---|
| Website paper lanes | 10 ($100k each, daily NAV), inception 2026-06-08 |
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
