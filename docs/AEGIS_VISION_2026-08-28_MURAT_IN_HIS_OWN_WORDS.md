# AEGIS — THE VISION, IN MURAT'S OWN WORDS (2026-08-28)

**Status: TIER 0 / CANON.** Read after `AEGIS_STRATEGIC_INVARIANTS.md`, before any
roadmap. This file exists because the intent below was stated in conversation
at least four times across a week and each time the next session woke up
knowing how to ask whether NVDA should drift for one more day. The words are
kept close to verbatim on purpose; the corrections are marked as corrections.

---

## 1. What Murat asked for (28 Aug, after the first live session)

> "I thought we were searching the WHOLE news — Yahoo, investment news, earnings
> calls, FDA approval dates, companies joining showcases, any kind of news for
> any kind of company. We are so fixated on Nvidia and mega-caps because they
> make all the headlines and we have more data about them. That's why I said use
> data-science methods to NORMALISE them into comparable data against the
> smaller stocks. NVDA has every firm's price analysis; a small stock has three
> or five analysts. But with small stocks you can make more profit. That's my
> whole point."

> "Use the LLMs to pick news. See how the news has been, how the data has been,
> how it reflects on the market and on OUR portfolio: should we sell something,
> hold something, buy something."

> "I live in Asia. I am 12 hours ahead of New York. Anything that happens in Hong
> Kong, China, Japan, Korea happens 12 hours before the US opens and influences
> the US market a lot. Digest the market BEFORE what will happen; then when the
> market closes look back: these were the things we said would happen, these are
> the reasons we bought and sold. Was it validated? If not, why? Was it
> situational for THIS stock? Because most of the time it is situational — we
> cannot make rules that apply to every stock. That is where we are failing: we
> always try to make one rule that is right for everything."

> "Sometimes we just have to trust our instinct and buy. The engine is supposed
> to BREAK the instinct into proof of what it should buy."

> "The pre-market should support DAY TRADING — we process data every day, we can
> do options, we have a crazy amount of data (WRDS). I don't feel we do enough
> backtesting. I asked for a neural network; it is still not built."

> "Trackers: follow hedge funds — what they do, how they put options, their
> analyses of individual stocks. Insider trades (SEC). Find GEMS, not Apple or
> Nvidia. I am trying to find Micron, Marvell, Nvidia when they were small. Find
> future companies, hold them, make revenue."

> "My previous stock list is the evidence of how I think — see which stocks I
> chose, the correlation between them, why. I thought AI was the next thing; even
> if not, the world is digitalising and we need to POWER that: chips (TSM, NVDA,
> AMD, MU were always on my list). Next: embodied robotics, autonomy, quantum,
> energy — nuclear, renewables, batteries, lithium; rare-earth and raw metals;
> actuators for robots. Look at what GOVERNMENTS invest in and legislate for:
> military budget up → defence stocks; education; policy. There is a
> correlation, and the engine should find those signals the way a human does,
> and make decisions from them. That is why we need the LLM, the HF models, the
> Featherless credit, DeepSeek, the cloud engine, ChatGPT research feeding back."

> "Every night I spend $3 on DeepSeek — for processing EARNINGS CALLS. We could
> have done that once, with code. Novel approaches come from INTERDISCIPLINARY
> connections: neuropsychology, maths, finance, robotics, politics, corruption.
> Amazon/Microsoft lay people off — why, and how does it reflect? China does
> something — how does it hit the US market? All of these connect. That's why I
> wanted a neural network too — to think about this and make up its mind. Build a
> novel, better engine that works alongside a person or by itself."

> "We have so many roadmap and handoff files; I worry a lot is being lost.
> Organise them so Optimus can digest them. The local built-in model can do the
> NN work and Fable can be the OVERSEER — local is independent and cheaper."

> "No 'freeze the strategy during the contest'. In investing we must be agile and
> adapt — fix and improve on the spot before the open, and over the weekend."

## 2. What was actually running (the gap, stated plainly)

Intended (already written in `AEGIS_STRATEGIC_INVARIANTS.md` §sensors and the
26-Aug roadmap):

    WORLD SENSORS → EVIDENCE → CAUSAL GRAPH → MARKET EXPECTATIONS → DIVERGENCE
    → EXPRESSION → ADMISSION → REALITY → LEARNING

Running on 28 Aug at the open:

    earnings calendar (95 names) + 40 theme names → 3 brains → risk gates → orders

The research brain and the daily trading machine were not connected. The
141-name `premarket_digest` (built 28 Aug morning) is a step; it is still not
"the whole market" and it still spends the LLM on summarising headlines.

## 3. Corrections Murat should hear (and accepted where the data says so)

1. **Small ≠ bonus.** The 2013-2024 CRSP replay of "buy high-vol names down
   20-50%" loses (-0.31%/5d, t -2.35) and the ">50% down" cell was an artefact.
   Lower coverage means slower information diffusion AND worse data, worse
   liquidity, wider spreads, binary risk. So the engine does not add
   `SMALL_CAP = +`; it **normalises information**: a name that normally gets two
   articles a week and suddenly gets six independent ones, or three analysts
   revising at once, is MORE informative than NVDA's 300th article. The score is

       Impact × Novelty × (1 − AlreadyPriced) × EvidenceConfidence
       × InformationScarcity × Exposure × ValueCapture × Tradability
       × HistoricalSupport,   with uncertainty rising as evidence thins.

   That is how you look for the next MU/MRVL rather than biasing toward size.
2. **Instinct, yes — as a typed hypothesis.** Not "never trade without 10,000
   examples" and not "trust the gut". Every instinct becomes:
   `evidence → mechanism → alternatives → direction → magnitude → horizon →
   p_already_priced → uncertainty → falsifier`, gets a SMALL experimental
   allocation, and is graded. `scripts.thesis` is that wire; the pre-open
   prediction book (below) is where it is sealed.
3. **Conditional, not universal.** An FDA decision, a Chinese rare-earth
   restriction, a defence appropriation, a memory shortage and a retail miss do
   not share one response function. Model
   `regime × event type × industry × size/liquidity × company state × causal
   exposures` — a mixture of experts, not one rule.
4. **What day one measured.** Twelve theme names behaved as ONE bet: nine stopped
   at exactly -3.0% within eleven minutes of a Fed speech, on two books, while
   the index moved 0.1%. -$6.9k realised each. The fix shipped the same hour
   (stop width per profile, no same-session re-entry, basket authority 12×3%).
   This is the agility Murat asked for, applied to a receipt, not to a feeling.

## 4. The one missing artery (the priority, in order)

    GLOBAL EVENT MESH → CAUSAL GRAPH → UNDER-COVERED OPPORTUNITY GENERATOR
    → CONDITIONAL BACKTESTER → PREDICTION LEDGER → PORTFOLIO → AUTOPSY

Every sensor Murat named (FDA calendar, insider Form 4, 13F/hedge-fund
positioning, options skew, Chinese policy, robotics adoption, defence
procurement, rare earths, lithium, nuclear, AI capex, layoffs, supply chains,
government budgets) is a FEED into this one machine, not a separate feature.

### 4.1 The daily cycle (Asia → world → US)

    continuous collection (code, not LLM)
    → Asia session read (DeepSeek reads Chinese/Japanese/Korean sources)
    → Europe
    → US pre-market
    → causal propagation over the graph
    → whole-universe opportunity generation, coverage-normalised
    → historical evidence lookup (WRDS/CRSP conditional cells)
    → LLM causal + red-team analysis on the SHORTLIST only
    → PRE-OPEN PREDICTION BOOK (sealed 09:15 ET)
    → portfolio decisions → market
    → AFTER-CLOSE AUTOPSY → overnight research queue

### 4.2 The pre-open prediction book
At 09:15 ET the system seals, per name: direction, magnitude, probability,
horizon, p_already_priced, falsifier, and WHICH BOOK acts on it. After the close
the same rows are graded. No nicer story afterwards.

### 4.3 The autopsy asks two questions, not one
1. Did our predictions and trades validate? If not — situational or structural?
2. **What were today's biggest idiosyncratic winners and losers across the whole
   market, what evidence existed BEFORE their move, and did AEGIS generate the
   name at all?** A miss here is an *opportunity-discovery failure*, and it
   becomes a research task for the overnight queue. This is the single most
   important addition; it is what "find Micron before it was Micron" means as a
   test.

### 4.4 Cost rule
Code fetches, deduplicates, timestamps, entity-matches and extracts routine
numbers (earnings-call figures, filings, calendars). The LLM is spent ONLY on
questions code cannot ask: *"Chinese transformer exports accelerated, two
Taiwanese suppliers report unusual orders, US grid capex rising — which
US-listed names capture the bottleneck, which are already priced, what
second-order names are ignored, what contradicts this?"* $3/night on
transcripts is the wrong purchase. `alpha/spend.py` already refuses a call
whose justification names no decision; extend it to refuse a call whose job
code could do.

### 4.5 Division of labour
| who | does |
|---|---|
| local model on the laptop (RTX 5060, 8 GB) / Optimus | retrieval, clustering, entity linking, compression, per-agent context building, NN training runs |
| DeepSeek | multilingual Asian-source reading; hard causal synthesis |
| HF / Featherless models | independent disagreement in the council |
| Fable (Claude) | overseer / red team: attacks causal logic, leakage, attribution, promotions |
| nobody above | has broker authority. Orders come only from the bounded execution path. |

Laptop vs Railway: **both**. Railway runs the six loops (must not depend on a
laptop being awake). The laptop runs research, simulations, the local model and
the NN. The bridge between the two repos is a versioned **Intelligence Packet /
Prediction Packet**, not a markdown handoff.

### 4.6 The neural network — the progression that avoids learning fame
1. Clean point-in-time global event + prediction dataset (the ledger IS this).
2. Simple calibrated baselines per condition.
3. Mixture of experts by event type × industry.
4. **Temporal heterogeneous graph**: companies, products, suppliers,
   governments, countries, commodities, technologies, events; targets =
   direction, magnitude, volatility, horizon.
5. Shadow until it beats the baselines out of sample after costs.
Feeding thousands of articles + prices into one net to predict BUY/SELL learns
fame, beta, size and headline volume first. The graph is what lets it learn
`US AI capex ↑ → GPU demand ↑ → HBM shortage → MU expectations stale`.

## 5. Where the files live (so nothing is lost again)
- `Aegis-Finance` = strategic brain, research, farm, causal graph, NN, Optimus memory.
- `aegis-alpha-terminal` = execution brain, books, predictions, orders, audit.
- `docs/INDEX.md` in each repo ranks the documents: TIER 0 canon (rarely
  changes) · TIER 1 current roadmap · TIER 2 findings with receipts · ARCHIVE
  (dated handoffs/roadmaps, digest only). A new session reads TIER 0 and the
  current TIER 1, and retrieves TIER 2/ARCHIVE by question.

## 6. What Murat asked for on 2026-09-11 (after using the desktop app for two sessions)

Kept close to verbatim; the corrections and the plan are in
`ROADMAP_2026-09-11_ROOT_FIRST_THE_OPERATOR_BOARD_AND_THE_LEARNING_LOOP.md`.

> "We are always focusing on so much of the product, but never the problem.
> What are the problems? We need to go to the root with everything we are
> doing. From the root, step by step, decide what we are building on."

> "The exe: it shows like 30 news, some of the APIs don't seem connected, the
> UI was really difficult to understand. I don't want it to take the tour every
> time I open it — first time, then don't show it again. The product is not
> ready, so the app should always update itself when I want to use it; I want
> it to log everything. Make it much, much easier: a DEVELOPER BOARD where I can
> see the Python code files. Rather than opening VS Code and running the
> systems again — I open the PC, one click, it downloads all the news, anything
> it can find; click, it starts the simulations; I see the showcase of the NN."

> "I want to interact with an AI agent inside the dashboard: 'what do you
> think will happen today?', a summary; 'look at the project', 'look at the NN,
> what is it doing right now'. Use the local model. It can READ the project but
> not UPDATE anything. Data synthesis, questions about the basics of the
> project."

> "First: NEWS COVERAGE. All the news from Asia to the West, starting with
> Yahoo Finance. World Monitor on GitHub was great for this; there is a God's
> Eye repo; any repo about pulling all the news. When news happens, how do we
> learn it, pull it, have the built-in LLM process it and give sentiment, how do
> I talk to it and come to a conclusion, and how does that conclusion become
> NUMERICAL data automatically. I don't want to open Claude Code every time to
> input values with code. It should converse with me, make decisions, build the
> portfolio: 'I want a very high-risk, cheap, industry-focused portfolio' — it
> creates it and HOLDS it on a paper account. Every time I open the app on
> Wi-Fi it fetches new prices and says: with the current news and this
> portfolio, this is the action to take."

> "After news coverage: the neural network — self-learning, self-attention.
> Check open-source patents (Google, self-attention). Encoder-decoder — not an
> LLM, but news coverage and tokenisation might be useful. Improve the engine
> and the decision-making model much, much better. It should run infinite
> backtests and LEARN from all of them, because our backtest results are
> terrible — we are picking up on noise. Check how other projects' backtests won
> against the S&P 500: Alpaca hackathon winners, LinkedIn, GitHub."

> "Something very different with the news: not only all the important news and
> what Yahoo analysts do — what the holders' sentiment normally is, their
> average moves. One agent goes to LinkedIn and checks what companies are
> NEWLY HIRING, whether their focus is changing, whether they are making a new
> product. Adobe and Autodesk have dropped a lot because of AI; like GoPro they
> might pivot — they have the data and the infrastructure, they will focus on
> AI to make shareholders happy. Great companies with potential not yet
> discovered. There is so much uncertainty; this is a gamble, but if it works it
> pays a lot."

> "I want the engine to say: not 'I'm 90% confident this is happening' — THESE
> are the probabilities of what might happen, these are the signals, can it
> happen, will it happen, should we take the risk, is it worth it — and then
> decide with the portfolios it creates on the six paper accounts. I want MANY
> paper accounts, maybe thousands: some checked daily, some every 30 minutes,
> some every three months, so it's less computationally heavy, and it sees what
> it THOUGHT versus what it LEARNED. Not that more accounts is better — this is
> DATA ACCUMULATION: what we thought vs what happened, to relearn our progress."

> "First check all the services code we made, make sure everything is connected
> and up to date. I'm okay with spending more money now — detailed services,
> maybe an extra device for a larger model later; not now. Give the roadmap and
> the context to the Claude Code in my terminal; it works on the project, I do
> only what it can't. Don't give me tasks Claude Code can do better than me.
> Research agents on Sonnet so they don't spend credits; build on Opus."

**The two sentences the roadmap is built on:** *"go to the root"* and *"what we
thought versus what happened."* Everything else is an expression of one of
those two.

### 6b. The same day, an hour later — the problem statement, in his words

> "We need profit improvements. Research improvements are good, but my main
> point is not a research paper; it's an investing tool I can use, that can
> make investments on my behalf for good profits, and an engine I can interact
> with — like my own investing agency: I say I want to invest for X time with X
> money; it gives me options, guides me. Go to the problem statement. It's for
> an AVERAGE PERSON to invest, create a portfolio and protect their money. What
> investors with capital under $1M face: no data, no info, no experience, no
> time. The engine should control the portfolio by itself so it can make its own
> money. It learns through its own investments. I don't have the time nor a
> mind as big as an LLM, so I want to hand everything off to it, and control
> and maximise profits myself."

> "Check investment news, strategies, how hedge funds and investors move,
> patents, books, theories; check X, Threads, social media. The engine should
> do this by itself every time I open it, or daily. Or the person says 'help me
> create a portfolio' — with their input and Aegis's guidance a portfolio is
> created: allocation per stock, risk, hold time. Every day we review the
> market and the portfolios, gather data and help them: this stock is still
> hold, sell, or buy more, based on the news or the future events that might
> happen."

> "I want Aegis NOT to be afraid of making mistakes. Thousands of paper
> accounts, checked daily, all different, all testing a strategy — made up from
> the data we have acquired: news, backtests, historical data. We have news for
> the past and WRDS data; run thousands of backtests, random or with new
> theories, so every run it can learn; it can make a theory and find points;
> save the results after each run; at the end of the whole chunk of sims, where
> it beats the S&P 500 we look at what it did and whether it is actually real.
> Check negative results again — I don't want to kill any good ideas.
> Continuous learning, self-attention, memory."

> "Use the LLM in the backtests with the made-up news, so we can compare what
> it thought with what it did. The resulting data and math can be CONTEXT for
> the LLMs — feed Optimus or the brain module a text or md file with everything
> we learned — or the text-to-number data we got can build the NN or our model.
> We can't build an LLM and that's not what we're asking; see what
> methodologies are needed and what we can do."

> "Sonnet for research and data acquisition, Opus 5 for building, and you as
> the central unit check their work and validate. Divide the work into chunks
> and one by one let's move on with them."

**What changed in the objective:** nothing — `OPTIMUS_OBJECTIVE.md` §0 already
says portfolio utility under a declared personality for Murat's capital AND a
public tool others run at their utility. What changed in the **priority
order**: the tool for an average person is now the deliverable the roadmap is
measured against, and research is what keeps that tool from learning nonsense.
