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
