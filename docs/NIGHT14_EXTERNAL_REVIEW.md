# NIGHT-14 — Murat's prompts and the external review, archived verbatim

Filed 2026-08-12. This document is EVIDENCE, not analysis. It holds what Murat
asked and what the external reviewer said, unedited, so that later sessions can
check what was actually requested against what was actually built. The
programme's own commentary on it lives in `NIGHT14_BRIEFING.md`; nothing in this
file is a decision.

Two things are worth flagging before the text, because they change how the
review should be read:

* The reviewer's **factual claims about the repo were checked** and were largely
  right — `llm_analyzer.py` really does firewall the LLM out of the numerical
  signal; the general LLM service really does carry a 150-call/day guard and a
  500-token response cap; `aegis_canon` really does serve a fixed list of older
  canonical files; the prediction ledger really did have its first resolution
  due 2026-09-12. Those are not flattery, they are audit findings that
  reproduced.
* The reviewer's **model-pricing figures are unverified** and the Fable-vs-Opus
  cost ratio quoted below should not be treated as settled. See
  `MODEL-ORCHESTRATOR-BENCH-1` for what the programme can and cannot conclude
  about that — the honest answer involves measuring, not quoting a price sheet.

---

## Part 1 — Murat's prompts (2026-08-12), verbatim

> why we are not using/testing the LLM, we should do more api calls and tests.
> for example my portfolio dropped a bit yesterday, lost 1k. why did this
> happen, llm should try to reason multiple times and compare it self to reality
> on why. this is the learning we want. it increased a lot this week why? bc of
> iran war getting to a close forexample. its not spesific to this instance but
> shows the improtance of geopolitical tension.

> here are the results of this night fable worked, used all the credits btw i
> dont have anything against it. I just want to compare if fable worked better
> than opus for the credits that has been used. normally if I have to do a
> research etc I use opus and fable for the brain.

> and I also want to ask this, I remember I took the bloomberg 2026 competetion
> and in 5 weeks alone a lot of teams made a lot of returns it doesnt seem real
> even looks luck but i dont think so, when I look at the winning team it is
> also clear to me the profesor was doing all the heavy lifting since the team
> is composed of 1 year students. can we check these winning portfolios, doesnt
> have to be from the competition any winning portfolio and see how their
> succes was made and how can we learn from this pattern for our paper accounts
> and own investmetns.

> these were my prompts and here is the external review / feedback, save them
> update the roadmap and then lest continue working, I wont be here for multiple
> hours so run very long simulations and shells, calls from api to learn and
> build the network. dont let it sit still, continues learning is key, make it
> test and learn at my absence.

### Standing rulings this does NOT override

Recorded here because the temptation to read "make up sensible data or tests"
as a licence recurs every few nights, and it has already been ruled on:

* Fabricated data and outcome-shopping remain **REFUSED** (NIGHT-13 ruling).
  The licensed substitute is the labelled ENSEMBLE — bounds over all histories
  consistent with the anchors, never a point fabrication, never "choose the best
  outcome and validate it".
* CANON §19 is unchanged by any volume of new API calls: every arm prints its
  own 80%-power MDE, and a number below its MDE is not detectable and never a
  kill.
* More inference does not lower the bar for a promotion. It raises the count of
  things that must be deflated against.

---

## Part 2 — External review #1: "we are not using the LLM aggressively enough"

*Archived verbatim. Section numbering is the reviewer's own.*

### TL;DR

Aegis should become two tightly connected systems.

**Optimus = the player.** It reads news and data, searches the web, reasons
repeatedly, builds beliefs about companies and the market, chooses portfolios,
explains daily P&L, proposes exits/re-entries, manages risk, and learns from
every prediction and decision.

**Aegis = the referee.** It determines whether Optimus is actually learning
rather than memorizing history, overfitting a backtest, chasing P&L or fooling
itself.

We should **not build one giant neural network right now**. The right system is
hybrid:

`LLM reasoning + supervised ML + unsupervised regime learning + contextual
bandits + offline RL + evolutionary search + deterministic risk/portfolio math +
forward calibration.`

And every LLM call should eventually produce something gradeable. Your
screenshot shows 8,936 API requests and more than 40 million tokens for $5.26. I
am not worried about making many calls at that price. I am worried about calls
that produce no learning sample.

The next project objective should be:

> **Every dollar of inference should create either a useful decision, a new
> hypothesis, or a labeled experience that makes the next generation better.**

### 1. Your "why did I lose $1k yesterday?" example is exactly what we should build

Interestingly, your geopolitical interpretation is not imaginary. On August 11,
Reuters reported that U.S. equities fell as optimism about a U.S.-Iran peace
agreement faded; Brent rose, energy stocks gained, and major technology stocks
weakened. The S&P 500 fell about 0.3% and the Nasdaq about 0.6%.

But that doesn't establish why **your portfolio** lost $1,000.

And that is the distinction I want Optimus to learn.

We should create a new permanent subsystem: **WHY-MOVED / Causal Attribution
Engine.**

Every night it first does deterministic accounting:

`Yesterday P&L = -$1,037` / `QUBT contribution = ...` / `SOC = ...` / `BHVN =
...` / `NTLA = ...` / `market beta = ...` / `sector/factor residual = ...`

Then it launches several independent LLM investigations: one agent investigates
company-specific news; one macro/rates; one geopolitical developments; one
sector/factor rotation; one options/volatility; one analyst/revision changes;
one deliberately argues that the other agents are wrong.

They don't simply write explanations. Each submits hypotheses like:

> H1: deterioration in U.S.-Iran peace probabilities raised oil/inflation/rate
> expectations, hurting high-duration technology exposure.
> Confidence: 0.61.
> Expected corroboration: oil up, yields up, Nasdaq < S&P, long-duration growth
> < energy.
> Main contradiction: ...
> Evidence timestamps: ...
> What would falsify this explanation: ...

Then the synthesizer compares the hypotheses. Now we have something
**scoreable**. If geopolitical explanations repeatedly predict the cross-asset
reaction correctly, their reliability increases. If an agent keeps blaming
geopolitics whenever markets move but its expected corroborating moves don't
happen, its weight falls. That is learning.

And crucially, we should distinguish **"What caused today's move?"** from **"What
does today's information predict next?"** The first is difficult to prove
causally. The second can be resolved mechanically. So every explanation should
generate one or more predictions.

### 2. This should run every day, not wait until September

NIGHT-13 fixed an important defect: the 87 DeepSeek forecasts finally have a
scheduler that can resolve them, and `/api/optimus/calibration` exists. But the
first resolutions in the current ledger are not due until September 12. That's
much too slow to be the only learning clock.

Add several clocks: **intraday / close-to-close** (what explains the move?);
**1 day** (did the hypothesized event propagation continue?); **5 days** (was
the initial reaction over/under-reaction?); **20 days** (did the investment
thesis have information?); **60/120/252 days** (did the security-level
expectation discrepancy actually matter?).

An LLM can therefore accumulate hundreds of resolved reasoning experiences
before a long-horizon portfolio result becomes meaningful. This also solves one
of our statistical problems: one 12-stock portfolio gives almost no power,
whereas thousands of daily security x event x forecast observations create a
much larger research instrument.

### 3. What should actually "learn"?

Not one model. Right now Aegis's production learning mechanism is deliberately
primitive: append a `LearningSample`, wait for enough observations, then make
small deterministic reliability adjustments capped at 0.05. That's excellent as
a production firewall but it is not a serious learning laboratory.

I would build five kinds of learning beside it.

**Supervised learning** learns questions where we know the later answer:
outperforming SPY in 20 days, realized volatility, drawdown, estimate revision,
earnings surprise, trial outcome, whether a news event generated persistent
returns. LightGBM should be the first baseline; neural nets only need to enter
when they beat it.

**Unsupervised/self-supervised learning** discovers market states we haven't
labeled: geopolitical-risk clusters, liquidity regimes, narrative clusters,
types of earnings reactions, correlations between seemingly unrelated companies.

**Contextual bandits** decide where to spend research budget. Microsoft's
RD-Agent already uses a multi-armed-bandit scheduler for adaptive
research-direction selection.

**Offline reinforcement learning** is appropriate for sequential
portfolio-management problems: HOLD vs ADD vs TRIM vs SELL, exposure control,
re-entry, replacement and position sizing.

**Evolutionary learning** lets hundreds or thousands of complete investment
policies compete across different market worlds.

So no, I would **not** currently say "Aegis is building a learning NN." I would
say: **Aegis/Optimus is becoming a hybrid continual-learning investment system.
Neural networks will be individual organs, not the brain itself.**

### 4. Why the research leg becomes more important, not less

If we let an LLM replay 2010-2025 over and over until it finds something
profitable, eventually it will become brilliant at 2010-2025. That does not mean
it learned investing.

Recent leakage-controlled work demonstrates how serious this is: when historical
identity/calendar information is masked and returns are attributed properly,
much LLM trading performance can be explained by market beta and style exposures
rather than persistent stock-selection alpha. A newer paper argues that passive
historical backtests alone cannot cleanly distinguish legitimate temporal
knowledge from leakage without an external reference/control.

A 2026 audit of agentic-trading research found that only 2 of 19 primary studies
had extractable time-consistent split protocols, only one explicitly modelled
transaction costs, and none reached the survey's highest reproducibility level.

So keep protected holdouts, point-in-time data, negative-results registry,
MDE/power, search denominators, costs, forward shadow books, known-answer
simulations, reproducible receipts. But use them to enable aggressive
experimentation instead of preventing experimentation.

**Research Gym can be reckless. Production must earn promotion.**

### 5. The "Portfolio Gym" is now the highest-value build

Create something like an OpenAI Gym environment for investing. Give it: date,
capital, available securities, PIT market data, PIT news, PIT filings, PIT
estimates, PIT options, current positions, cash, risk constraints.

The agent chooses: BUY / ADD / HOLD / TRIM / SELL / HEDGE / CASH / REPLACE. Then
time advances.

Reward should not just be tomorrow's return. Something closer to: compound
wealth - severe drawdown penalty - ruin penalty - transaction costs -
concentration penalty - liquidity penalty + calibration quality. Different user
modes simply change the utility function.

But we should add something they generally do not have: **LLM-generated belief
states and causal event reasoning.**

### 6. Then run the portfolio thousands of different ways

For every historical decision: HOLD 100%, TRIM 20%, TRIM 50%, SELL to cash, SELL
to SPY, SELL to best candidate, ADD, reduce portfolio beta, hedge, rotate
sector. Evaluate every branch at 1/5/20/60/120 days. Do this for millions of
candidate states — not only your positions.

Then ask: Under what observable state does trimming winners improve compound
wealth? When should a 150% winner be left alone? When does buying a 20% dip
work? When does geopolitical uncertainty justify lowering beta? Which post-crash
states justify rapid re-entry?

The NIGHT-12 "cash never won in 60 cases" result becomes only one tiny sample in
this much larger environment. That's the way around its limitation.

### 7. LLM explanations themselves should evolve

Projects like FinMem already give LLM financial agents layered memory, and
FinCon uses verbal reinforcement/self-critique to modify agent beliefs.
TradingAgents has multi-agent financial roles and persistent decision logs.
FinRobot divides financial research among specialized analysis agents.

Therefore simply adding "five financial agents" is no longer novel. Our version
needs the missing piece: **Every piece of reasoning becomes a prediction
contract.**

An agent doesn't get rewarded for sounding insightful. It gets rewarded because
its cited evidence existed at the time, its causal map was coherent, its
expected cross-asset responses occurred, its next observable resolved correctly,
its security forecast calibrated, and adding that information improved the
portfolio relative to a deterministic baseline.

Then Optimus can learn: `geopolitical specialist x energy x 5d = 0.81
reliability`; `geopolitical specialist x biotech = 0.49`; `DeepSeek
semiconductor specialist x 60d = 0.68`; `Fable skeptic x event-driven = 0.76`.
That is much more useful than one universal "LLM score."

### 8. We need to use the APIs much more intelligently

40,094,206 tokens and 8,936 requests cost $5.26 on that provider dashboard. That
means **DeepSeek inference is cheap enough to treat multiple independent
reasoning runs as an experimental resource.**

I would stop maintaining a simple "daily calls <= 150" mindset as the master
constraint. The existing general LLM service still has a default 150-call/day
guard and 500-token response limit.

Instead build an **LLM Budget Controller**. Cheap model: thousands of
screening/extraction/hypothesis calls. Expensive/deeper model: only
disagreements, difficult reasoning, experiment design and reviews. Then a bandit
learns which tasks deserve which model.

Every call gets logged with: model, version, prompt_hash, context_hash,
tools_available, input tokens, output tokens, latency, cost, schema validity,
prediction IDs produced, eventual score, incremental value over baseline.

Now we can calculate **information gained per dollar**. That is much more
meaningful than token count.

### 9. Fable versus Opus: we do not yet know which was better

The NIGHT-13 work looks productive. It delivered the Investment Committee,
automated owed items, multiple preregistered experiments, ledger scheduling,
calibration endpoints, production verification and caught several silent
failures.

But NIGHT-13 cannot fairly be compared with an Opus night because the tasks were
different. Also, the screenshot you posted is a downstream API-usage dashboard.
It does not tell us whether Fable or Opus created more value.

There is a substantial price difference if we compare direct Claude API pricing:
Anthropic currently lists Fable 5 at $10/M input and $50/M output, versus Opus
4.8 at $5/M and $25/M — effectively 2x per token before caching/batch discounts.
Anthropic positions Fable specifically for very long-running autonomous
projects, while Opus is also positioned for serious agentic/coding work.

So don't guess. Run **MODEL-ORCHESTRATOR-BENCH-1**: same starting repository,
same 20-30 tasks, same DeepSeek budget, same hidden tests, same time budget, 3
independent runs/model, neither sees the other's output.

Measure: success rate, bugs introduced, silent bugs caught, hidden tests passed,
useful hypotheses generated, human interventions, wall-clock time, DeepSeek
calls, Claude tokens/cost, and eventually downstream research results.

The most important metrics: **valid task completions / $**, **defects caught /
$**, **licensed discoveries / $**, **forward performance added / $**.

Fable should be used where its extra cost earns enough extra
correctness/autonomy. If not, Opus should be the default and Fable the
escalation model.

### 10. Optimus MCP needs another audit

The MCP architecture itself is sensible. It exposes five read-only tools: live
Aegis state, registry, canon, postmortems and `brain_query`; retrieval has
explicit abstention and finance-domain scoping.

But I found two things I would test immediately.

First, `aegis_canon` still has a fixed list containing old canonical files such
as V2_GOALS, TRACK_RECORD_POLICY and TRIAL-001. The latest NIGHT-11/12/13
reasoning therefore relies more heavily on postmortems and the separate brain
corpus rather than a current dynamic canon endpoint.

Second, Optimus has a `refresh_aegis.py` script specifically because the brain
previously went weeks stale. Its own documentation says to run it after research
sessions or schedule it — but I don't see evidence in the current repo that this
refresh is itself continuously enforced.

So add `brain_source_head`, `brain_ingested_head`, `brain_age`,
`latest_session_seen`, `latest_registry_trial_seen`, `context_health` to MCP
health. A stale brain must return `DEGRADED`.

Then run adversarial MCP tests: old fact vs new fact, contradictory docs, deleted
fact, finance query with robotics contamination, missing latest NIGHT document,
MCP restart, Aegis unavailable, brain unavailable, corrupt page, stale ingestion.

This matters because an agent with stale context can execute perfectly and still
do the wrong research.

### 11. The consumer product already exists in embryo

NIGHT-13 actually answered your question "can it create a portfolio based on the
money I input?" **Yes, partially already.** The live Investment Committee accepts
capital and currently produces complete portfolios at $10k, $40k and $1m. At the
verified $40k example, it produced six benchmark-core positions plus small
evidence-led tilts, rather than returning an empty page when the stronger
strategies refused.

But this is not yet the product you are imagining. The desired user experience
should become: user enters "$40,000. I want high growth. I tolerate 30%
drawdowns. Five-year horizon. I don't know what to buy." Optimus returns three
genuinely different choices: **Core Growth** (highest confidence, lower tracking
error), **Aggressive** (more concentrated, higher beta, higher expected
dispersion), **Convex/Moonshot** (small high-positive-skew positions around
potentially transformative outcomes).

The underlying evidence doesn't become weaker between modes. Only sizing/risk
changes.

Then the user can choose: **Advisor** (tell me what you would do); **Copilot**
(recommend changes, I approve); **Autonomous Paper** (manage everything
automatically in a live paper account); **Attended Live** (prepare real orders,
but require approval).

Full autonomy should first be proven in paper/shadow; real-dollar autonomous
execution should remain separately enabled rather than accidentally following
from research automation.

### 12. Where Aegis stands versus competitors

| System | They are substantially better today | Our potential differentiation |
|---|---|---|
| **Bloomberg** | Institutional data, real-time news, proprietary research, cross-asset coverage, PORT/risk, execution and now agentic ASKB. Bloomberg even publishes an ASKB example asking which portfolio sectors were harmed by U.S. intervention in Iran and requesting primary/secondary volatility drivers. | Don't compete on raw data. Compete on a persistent self-evaluating investment brain whose hypotheses and explanations are frozen, scored and used in future learning. |
| **InvestingPro** | Polished consumer experience, AI picks, Fair Value, screeners, AI research assistant, broad global coverage and 1,200+ metrics. | More transparent evidence provenance, personalized belief state, experiments, causal learning and portfolio-management feedback. |
| **Bloom** | Very good UX for "I have an idea -> turn it into a portfolio"; backtesting and mirroring Wall Street/politicians are already productized. | Go much deeper: don't only mirror managers — learn what observable behavior from which manager contains information, with disclosure-lag controls. |
| **Midas** | Actual brokerage, multi-market access, low-friction trading, news and consumer-friendly "why did it rise/fall?" content. | Explain the user's exact portfolio, generate competing causal hypotheses and measure whether those explanations predict anything. |
| **Two Sigma** | Massive institutional infrastructure and research depth. Publicly, it describes independent real-time forecasts being combined into a consensus and then into target allocations after trading costs and risks. | We should explicitly copy this architecture: specialist forecasts -> calibrated consensus -> costs/risk -> portfolio. Add LLM-generated qualitative forecasts and open auditability. |
| **Man AHL** | Decades of systematic investing, large data/model infrastructure, ML in live strategies, execution and cost modelling. Its public process moves ideas from simulation into live paper trading before deployment. | Aegis already resembles its scientific philosophy. Our possible novelty is coupling that rigor to autonomous LLM research, persistent memory and continuous hypothesis generation. |

This also tells us what **not** to build. Do not try to recreate Bloomberg's data
terminal. Connect high-quality data sources and build the intelligence layer
above them.

### 13. Where I think the actual breakthrough could be

Not "LLM picks stocks." Not "RL trades stocks." Not "multi-agent finance." All
of those exist.

The interesting combination is a **Causal Event Graph**. News becomes:
`Iran talks deteriorate` -> `Hormuz closure probability up` -> `oil expected
price up` -> `inflation tail up` -> `rate-cut probability down` -> `long-duration
equity valuation down` -> sector/company-level effects.

Then the LLM predicts every edge. Every edge can earn or lose reliability.

Now add a **Market Belief Graph** (what is already priced?), then an **Optimus
Belief Graph** (where does it disagree?), then a **Portfolio Utility Graph**
(where should capital move because of that disagreement?), then an **Experience
Graph** (which previous reasoning pattern resembled this one, and what
happened?).

Microsoft's RD-Agent shows that autonomous feedback-driven quant R&D is viable
as an architecture. What I haven't found in the reviewed systems is our exact
combination of a persistent causal security belief state + PIT web reasoning +
counterfactual portfolio-management learning + evolutionary research + an
independent statistical referee. That is where I would put the research thesis.

### 14. Tests I would run next

1. **LLM-ATTRIB-1** — every day's portfolio move gets 5-10 independent causal explanations; score evidence quality and predictions implied by each explanation.
2. **GEO-1** — build a PIT geopolitical-risk/event dataset; test whether LLM-extracted change in conflict probabilities adds anything beyond oil/VIX/trend/rates.
3. **ORCHESTRATOR-BENCH-1** — Fable vs Opus with equal tasks and downstream DeepSeek budgets.
4. **MCP-CONTEXT-1** — adversarially test stale/contradictory/missing memory and exact context that reaches each specialist.
5. **PORTFOLIO-GYM-1** — create synthetic worlds with known optimal rules. Before we trust RL to "discover" exits, prove it can rediscover planted rules.
6. **EXIT-RL-1** — learn ADD/HOLD/TRIM/SELL/REPLACE across thousands of stocks and episodes rather than 60 branches from one portfolio.
7. **RISK-BUDGET-2** — compare static beta targeting, dynamic book-risk targeting, learned RL exposure and no intervention across many crises and bull markets.
8. **LLM-DISAGREEMENT-1** — test whether disagreement between DeepSeek/Fable/Opus/specialists is itself a useful uncertainty signal.
9. **EVENT-GRAPH-1** — test first- and second-order beneficiaries of news rather than ticker sentiment.
10. **TEACHER-1** — compare raw hedge-fund/politician copying versus inferred specialist behavior with correct public-disclosure delays.
11. **EVOLUTION-1** — 500-5,000 investment-policy genomes across training worlds; extract common survivor mechanisms, then validate descendants on unseen worlds.
12. **RD-AGENT-BASELINE** — actually install/reference Microsoft's RD-Agent + Qlib and benchmark our research automation against it rather than reinventing the entire loop.
13. **FINRL-BASELINE** — run standard PPO/SAC/A2C portfolio-management policies so our "self-learning" claims have strong public baselines.
14. **TRADINGAGENTS/FINMEM BASELINES** — reproduce comparable LLM-agent approaches and test whether Optimus's memory/referee improves them.

The key rule: **synthetic tests prove machinery; PIT historical tests generate
hypotheses; untouched holdouts test them; forward predictions determine whether
Optimus deserves real trust.**

### 15. The reviewer's proposed NIGHT-14/15 brief

*(Reproduced in condensed form — the full P0-P13 list is the reviewer's own
structure and is answered item by item in `NIGHT14_BRIEFING.md` §2.)*

**Objective:** Move Aegis/Optimus from a quant research system with an attached
LLM into a **self-evaluating investment brain**. Optimus is the player. Aegis is
the independent referee. Do not weaken the research standards to make the
product more active — increase the amount and quality of experimentation
instead.

- **P0** — close NIGHT-13 infrastructure risks first: ledger persistence across
  deploys; scheduler job-set health canary; seed forward shadow books; audit
  Optimus freshness (`refresh_aegis.py` enforced, not merely callable); MCP
  context-health fields; verify a clean session receives latest state through
  MCP. *Do not proceed if the agent's context can silently be stale.*
- **P1** — WHY-MOVED / Causal Attribution Ledger (deterministic first, then
  isolated LLM specialists producing structured hypotheses; grade through
  falsifiable consequences; run for the full opportunity universe, not only
  Murat's book).
- **P2** — expand the Prediction Ledger: 1d/5d/20d/60d/120d/252d, prices AND
  intermediate observables. "The objective is thousands of resolved forecasts,
  not 87 long-horizon anecdotes."
- **P3** — centralized LLM telemetry and model economics; contextual-bandit
  research router. *Do not optimize for few calls. Optimize for useful
  information per dollar.*
- **P4** — MODEL-ORCHESTRATOR-BENCH-1, pre-registered, hidden acceptance tests.
- **P5** — Portfolio Gym with PIT state, full action set, compound-wealth reward
  with drawdown/ruin/cost/concentration/liquidity penalties. Synthetic
  known-answer worlds FIRST.
- **P6** — learning stack: supervised, unsupervised, bandits, offline RL,
  evolutionary, deterministic risk math, LLM reasoning, forward calibration.
  *Do NOT build one monolithic neural network.* Benchmark against Qlib,
  RD-Agent, FinRL, FinMem, TradingAgents, FinRobot/FinCon.
- **P7** — EXIT-RL / replacement learning across thousands of securities.
- **P8** — GEO-1 geopolitical/event intelligence (probability CHANGES, not
  labels). *Do not tune a war rule on one known war.*
- **P9** — Event Graph / second-order beneficiaries.
- **P10** — evolutionary investment policies with preserved search denominators.
- **P11** — teacher library with correct public-disclosure delays; raw copying
  as the control.
- **P12** — product: interactive investment manager, three risk budgets from the
  same evidence, four modes (Advisor / Copilot / Autonomous Paper / Attended
  Live).
- **P13** — forward tournament seeded contemporaneously against SPY, QQQ, equal
  weight, random, deterministic Aegis, LLM-only, evolved policy, blended
  Optimus, prior generation, user lanes.

**Stop rule:** "Do not spend the session writing only architecture documents.
After correctness infrastructure is fixed, execute independent nonblocked
phases. Use the available DeepSeek budget aggressively when calls generate
structured, gradeable outputs. Do not optimize for low API usage. Optimize for
information gained, defects removed, predictions resolved, and investment
decisions improved per dollar."

> The biggest conceptual shift is this: **stop treating the LLM as a narrator
> that sits beside the engine. Make it a population of forecasters and
> researchers living inside an environment that relentlessly grades what they
> say.**

---

## Part 3 — External review #2: the Bloomberg competition winners

*Archived verbatim.*

### What the 2025 winner actually says it did

The team captain describes the strategy as **stock selection and execution
rather than forecasting the market**. She says they concentrated on stocks
showing clear momentum, strong volume and clean price action, and actively
adjusted entries and exits using price reactions, news flow and intraday
behaviour. She also describes false breakouts, reversals and drawdowns as things
they actively navigated rather than simply buying a basket and waiting.

That is considerably more specific than CUHK's institutional announcement, which
describes the approach as active and disciplined, with daily portfolio
monitoring, real-time analysis and risk management across global equities.

So the crude model of their process looks something like: **theme/opportunity
discovery -> momentum confirmation -> volume confirmation -> news/event
interpretation -> entry timing -> watch price reaction -> actively exit/rotate
when the response changes.**

That is extremely relevant to what we have been discussing for Optimus. It is
almost exactly the layer Aegis is missing between "This company has an
interesting long-run thesis" and "Buy/hold/sell this amount today."

### I would not conclude that the professor secretly did the trading

There is no public evidence supporting that conclusion. Professor Haynes Yung is
certainly well positioned to provide useful guidance: he teaches investment
analysis and portfolio management, has derivatives as a research interest, and
has published on GARCH option pricing and trading systems.

But the captain's account attributes her own role very specifically to stock
selection and execution and describes the professor as providing guidance and
encouragement.

So the defensible conclusion is: **experienced faculty guidance probably helped
provide a framework, but the available evidence does not show that the professor
was making the trades.**

And the fact that three members were first-years doesn't invalidate the result.
A five-week trading competition does not require decades of valuation experience
if the dominant strategy is momentum/event trading with Bloomberg tools.

### Past winners show a repeated pattern

The **2024 RIT global winner** is especially revealing. Their captain literally
described their strategy as **"betting on volatility."** They concentrated mostly
on foreign stocks and deliberately accepted enormous risk because the tournament
rewarded being first rather than preserving capital. He explicitly said luck
played a large role and that they could have finished last. He also said their
lesson from the previous year was essentially to maximize money without worrying
about losses — something he acknowledged would not be sensible as a normal
investment policy. They nevertheless led for five of the six weeks.

The **2021 UConn winner** followed a somewhat different implementation but a
related philosophy: speculative companies with high potential, "underdog" names
rather than only obvious megacaps, diversified exposure to whatever themes the
market was reacting to, and continuous monitoring of changing market conditions.
Their professor explicitly encouraged students to take more chances.

The **2023 HKU global winner** described building the portfolio allocation
before the competition, going through trial-and-error to find the strategy,
studying macroeconomic events, and continuously updating the portfolio. One team
member specifically emphasized objective analysis and trade execution rather than
attributing the result purely to luck.

The **2025 Drexel North America winner** is another revealing control. They made
about 23% using a concentrated U.S. biotech portfolio. Their professor
deliberately encouraged high-volatility stocks because the competition objective
rewards extreme outcomes; he explicitly said this is the opposite of how one
would construct a steady diversified portfolio. Another Drexel team stayed in
the global top ten for much of the competition and then collapsed into the
bottom 5% near the end.

And a more systematic 2025 Imperial team used something very different:
**quality momentum**. They screened liquid stocks for recent performance,
filtered using fundamentals such as ROE and debt, backtested in Python,
rebalanced daily, and used GARCH/correlation dynamics to build a more
sophisticated covariance model.

That diversity is important. There isn't one "Bloomberg competition trick." But
several characteristics keep recurring: **momentum, volatility, changing market
themes, aggressive opportunity selection, global breadth, active reaction to
information, and — critically — choosing a portfolio style appropriate to the
objective being optimized.**

### On the screenshots

I would be careful with one distinction: those Bloomberg tables appear to be
**aggregate results from all competitors**, not Bear Bull's private portfolio.
So NVIDIA's $9.8M aggregate P&L does **not** mean the winning team held NVIDIA.

But the aggregate information contains something extremely valuable. The obvious
winners were the first-wave theme: NVIDIA, AMD, Palantir, Micron, Amazon,
Broadcom. But the "unexpected" leaders were often **second-order beneficiaries**:
SK Hynix, SanDisk, Western Digital, Kioxia, Vicor — along with less crowded
idiosyncratic bets such as Praxis Precision Medicine, Bloom Energy and RTX.

That pattern is almost exactly your own reasoning about investing in the
companies **supporting** major technological transitions rather than merely the
obvious headline company: AI demand -> GPU leaders -> memory -> storage -> power
-> electrical components -> cooling -> networking -> data-center infrastructure
-> raw materials.

This is potentially a much more interesting LLM problem than "predict NVDA." It
is: **Once Optimus recognizes a major economic theme, can it construct the causal
supply-chain graph and identify second- and third-order beneficiaries before the
market fully prices them?**

### Why the competition results look almost unbelievable

The tournament's objective function is very different from a real investor's.

Public copies of the 2025 handbook describe the competition as long-only, no
leverage, more than 10,000 WLS stocks, with no single stock allowed to exceed
20% of the portfolio. Teams are ranked relative to the WLS benchmark.

So this is **not** simply someone levering a $1M portfolio 10x. But there are
around 2,600 teams. That means we observe the **maximum outcome among thousands
of competitors**.

If everyone adopts moderate-risk diversified portfolios, nobody gets +400%. To
win, there is a huge incentive to choose a portfolio with very high positive
dispersion: maybe you go +150%, maybe you go -60%. The +150% portfolio wins.
Nobody remembers its identical cousin that lost 60%. RIT's winning captain
effectively admitted that this was their optimization strategy.

So I think the proper interpretation is: **The extraordinary leaderboard return
contains some skill + some strategy design + substantial favorable path
dependence/winner selection.**

That doesn't make the strategy useless. It means we need to extract the
**information-generating component** from the **risk-taking component**. That is
precisely something Aegis can do.

### `WINNER-GENOME` as a new research program

This shouldn't just study CUHK. I would make it a cross-year, cross-competition,
cross-investor experiment:

1. **Build a Teacher Portfolio Corpus.** Bloomberg global/regional winners and
   high finishers from 2021-2025, public student fund winners, investment
   competitions, selected professional portfolios, specialist hedge funds and
   other public investment records. Record only information that would have been
   available contemporaneously. Most importantly, include mediocre and losing
   portfolios whenever possible — we cannot learn exclusively from winners.
2. **Infer the strategy genome.** Rather than just collecting holdings, classify
   each portfolio along dimensions such as momentum, volatility, quality,
   valuation, event exposure, thematic concentration, sector concentration,
   turnover, foreign-market exposure, news responsiveness, volume confirmation,
   holding period, entry behaviour and exit behaviour.
3. **Reconstruct the tournament.** Use the actual WLS-like universe, dates,
   long-only restriction and position limits. Reproduce families such as RIT
   volatility, CUHK momentum+volume+news, Imperial quality-momentum, Drexel
   biotech/high-volatility, UConn underdog/event and ordinary
   benchmark/quality/value/momentum controls.
4. **Run thousands of versions.** Randomize portfolio selections, thresholds,
   rebalancing, risk budgets and start states. Determine whether a strategy
   family produces a distribution shifted upward or merely produces enormous
   variance with a lucky maximum.
5. **Separate selection from sizing.** If CUHK-like stock selection is useful but
   its tournament sizing is dangerous, run the same selections at 20%, 10%, 5%,
   inverse-vol, risk-parity, fractional Kelly and Aegis risk budgets. This tells
   us whether the *idea* is valuable even when the leaderboard gamble is removed.
6. **Train the execution brain separately.** Give Optimus contemporaneous
   momentum, volume, price action, news and portfolio state, then ask
   ADD/HOLD/TRIM/SELL/REPLACE. Train/evaluate it across millions of stock-days
   rather than twelve personal positions.
7. **Cross-year validation.** Discover using 2021-2024 winner archetypes, freeze
   the rules, and ask whether they would have performed well in the 2025
   competition without knowing 2025. Then reverse/rolling tests.

That's a scientifically useful design because we're no longer asking "Why did
the winner win?" We're asking: **"Which observable behaviours occur
disproportionately among successful portfolios, survive controls for volatility
and luck, and continue working in periods that were not used to discover them?"**

### THEME-CASCADE / SECOND-WAVE-1

An LLM continuously identifies major economic narratives (AI compute, quantum,
grid/electricity, defense, biotech platforms, GLP-1, nuclear, robotics, energy
geopolitics). Then it constructs the economic dependency graph: `AI capex` ->
GPUs -> HBM -> DRAM/NAND -> storage -> networking -> power generation ->
transformers -> cooling -> electrical equipment -> materials.

Aegis then calculates for every node: price momentum, volume acceleration,
earnings revisions, analyst revisions, valuation rerating, news acceleration,
options state, institutional attention, theme crowding.

Then look for: **economic exposure accelerating + revisions improving + momentum
beginning + significantly less crowding/rerating than the theme leader.**

Your Bloomberg screenshot's SK Hynix/SanDisk/WDC/Kioxia/Vicor grouping is an
almost textbook example of why that hypothesis is worth testing. Importantly, we
should preregister it now rather than look backward and claim those names prove
it.

### The missing system CUHK points at

**LLM Event Intelligence + quantitative execution confirmation.** The LLM does
not decide "Momentum = 72 therefore buy." Instead:

LLM: "New information materially improves the storage-demand thesis. This
appears more important than consensus expected because X/Y/Z."
Quant engine: price confirms / abnormal volume confirms / breadth confirms /
revisions confirm.
Execution brain: initial 4% position.

Then: news improves + price confirms -> ADD. News improves but price fails ->
investigate. Price surges while thesis unchanged -> reconsider expected return.
Momentum breaks + negative event -> TRIM/EXIT. Better opportunity emerges ->
REPLACE.

And unlike a five-week competition, Aegis can overlay proper risk sizing.

### The lesson for Murat's own portfolio

The Bloomberg evidence actually reinforces rather than contradicts what we've
been discovering. You appear drawn toward many of the same **high-dispersion
opportunity classes** that win short competitions: biotech, quantum,
semiconductors, energy, emerging technology.

The problem may not be that those assets are intrinsically wrong. The problem is
that **the same high dispersion that produces huge winners produces catastrophic
round trips if position management does nothing.**

So perhaps the winning architecture is not **less risk**. It is: **high-quality
high-dispersion selection + intelligent execution + adaptive sizing.**

That is a subtly but radically different objective from the conservative signal
engine we started with.

### Strongest next recommendation

Add `WINNER-GENOME-1`, `THEME-CASCADE-1`, and `MOMENTUM-EVENT-EXECUTION-1` to
the next Aegis campaign. And don't judge them only on Sharpe. Measure: compound
return, benchmark excess, upside capture, downside capture, winner retention,
profit given back from peak, entry efficiency, exit efficiency, turnover,
drawdown, ruin probability, and whether the result survives risk normalization.

If the **selection mechanism** repeatedly finds enormous winners but the original
competition implementation is too dangerous, that is not failure. It means we
found the alpha source and need Aegis to solve the portfolio-management problem
around it.

---

## Part 4 — sources cited by the reviewers

Recorded so later sessions can check them rather than inherit them. **None of
these has been independently verified by the programme**; several are load-
bearing for the reviewer's argument (particularly the leakage papers and the
model price sheet) and should be read before being relied on.

Microsoft R&D-Agent-Quant · Microsoft Qlib · AI4Finance FinRL ·
FinMem (arXiv/GitHub) · TradingAgents · FinRobot / FinCon ·
"From Knowing to Doing: A Memory-Controlled Benchmark for LLM Trading Agents"
(arXiv 2605.28359) · "Temporal Leakage in LLM Backtesting" (arXiv 2608.02985) ·
"Agentic Trading: When LLM Agents Meet Financial Markets" (arXiv 2605.19337) ·
Reuters 2026-08-11 (US-Iran peace optimism fades; S&P -0.3%, Nasdaq -0.6%) ·
Anthropic model pricing page · Bloomberg ASKB roadmap announcement ·
CUHK Business School / LinkedIn (2025 winner) · RIT (2024 winner) ·
UConn Today (2021 winner) · HKU Business School (2023 winner) ·
Drexel LeBow (2025 North America winner) · Imperial College (2025 quality
momentum) · 2025 Bloomberg Trader's Handbook (long-only, no leverage, 20% cap,
10,000+ WLS stocks) · PR Newswire (participation record, ~2,600 teams).
