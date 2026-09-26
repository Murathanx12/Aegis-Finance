# Murat's session brief — 2026-09-26 afternoon (verbatim substance)

"Do not build a new roadmap. The TIER 0 one-pipeline strategy is now the roadmap.
The objective of this session is to improve the pipeline by finding profitable
information already present in AEGIS, explaining recent wins and failures,
expanding the strategy tournament, and eliminating unnecessary runtime cost."

Sonnet for discovery; OpenClaw for live web incl. the authenticated X account;
DeepSeek and NVIDIA as named comparison/adjudication models only; Opus to
implement; after every meaningful chunk a separate Opus reviewer argues the
builder is wrong and proposes a more profitable alternative.

A — FAST-MOVER FORENSICS: every forward position that moved >= 5% abs or >= 2σ
within 1/5 sessions of entry (prioritise the ~10% books); rebuild the state AT
ENTRY with no later evidence; record ranker state, revisions, analyst
identities, forecast p, thesis card, pre-entry news, X/social, search
attention, product/customer/supplier, political/regulatory, insider/holder,
sector move, benchmark move; the real ex-post catalyst; classify
PREDICTED_MECHANISM / RIGHT_STOCK_WRONG_REASON / SECTOR_BETA /
UNFORESEEABLE_NEWS / ATTENTION_REFLEXIVITY / ANALYST_CASCADE / PRODUCT_DEMAND /
SUPPLY_CONSTRAINT / POLICY / OTHER; a reusable feature per true hit; no credit
for accidental hits; matched controls.

B — SOURCE/ACTOR GRAPH: read-only source hierarchy (company, CEO/founder,
engineers, sell-side, fund managers, journalists, industry specialists,
government, retail influencers, Reddit communities); every source an empirical
track record (lead time, fact accuracy, forecast accuracy, short/long-horizon
return after claims, sector specialisation, false-positive rate,
crowding/reversal signature); social is an attention layer, not a truth layer;
X/Reddit never generate orders.

C — INTERDISCIPLINARY FAMILIES (Sonnet): innovative efficiency, patent
acceleration, R&D hiring, government contracts, promise-vs-delivery, CEO
execution reliability, management-language change, pivots, PMF inflection,
capacity constraints, pricing power, network effects, switching costs, China
capacity entry, supply-chain lead/lag, attention shocks, search acceleration,
social crowding, lottery preference, disposition effect, FOMO/reversal,
analyst-skill persistence, analyst first-mover, estimate-revision cascades —
every concept an observable PIT feature.

D — LIBRARY → ≥200 genuinely different strategies; every row prints dev return,
SPY, sealed/OOS return, DSR, LOO-worst, top-5-month share, turnover, cost, max
DD, recent-period return; objective MAXIMISE SEALED NET RETURN; cross-check the
top 10 in a second engine (investigate QuantConnect LEAN first; independent
replication, not replacement).

E — BACKTEST → FORWARD BRIDGE: freeze code+params, $1M local paper book,
declared expected behaviour, forward run; report makes historical expectation
vs current result visually obvious; a forward failure is investigated
(REGIME_SHIFT / CROWDING / FACTOR_DECAY / DATA_LEAK / IMPLEMENTATION / COST /
UNIVERSE_CHANGE / RANDOMNESS / UNKNOWN), not deleted.

F — OPENCLAW as research sensor (candidate monitoring, X reads, launches,
earnings language, patents, hiring, contracts, supplier/customer links,
bottlenecks, CEO statements, contradiction search, missed-winner autopsy) with
the twelve questions; every result = structured evidence + timestamp +
forecast + future grade.

G — MODEL ROUTING: llama-server not permanently resident; OpenClaw
localService; idle shutdown; Telegram /nav /status /books /forecasts
deterministic; /ask local on demand; /research OpenClaw + local; /deep
DeepSeek or NVIDIA; /compare all three frozen and graded; cost and incremental
accuracy per provider.

H — RAILWAY COST REVIEW (no production mutation): why five loops need separate
high-memory containers (hack1 3.18 GB, hack6 2.33, hack5 1.38, hack4 0.97,
hack2 0.50; low CPU); compare current vs one multi-mandate process vs
scheduled workers vs serverless; monthly cost each; never compromise broker
ownership or ledger isolation.

I — DAILY LEARNING REPORT: what resolved; which sources gained/lost
credibility; which books beat SPY; fast movers predicted/missed and why they
moved; did AEGIS predict the mechanism; which strategy would have captured
them; best historical / sealed / forward strategy; features surviving matched
controls; data nobody consumed; more/less compute tomorrow; and the three
sentences: WHAT CURRENTLY WORKS? WHAT DOES NOT? THE SINGLE HIGHEST-EV NEXT
EXPERIMENT. Not a roadmap.


---

## Murat's ORIGINAL prompt (13:30 HKT) — this outranks the GPT list above
"I'm going out for five hours ... use OpenClaw again because I logged into X ...
work on the market analysis more, find demands, review the forecasts and the
reviews and the analysis — anything we manufactured — grade them, what was true,
what was not. Some of the paper cards moved so much — the ones that moved 10%,
and they are very new. Why did they move this fast? Why are they this good?
What can we learn, how can we improve them? There is no roadmap left; find ways
to improve, using Sonnet, OpenClaw, DeepSeek and everything built in. I will be
reading the PDF over the weekend and make my own review. Work more on the
backtest: the GitHub still says Aegis is ~30% on the backtest and the benchmark
~110%. We need to show 'we made 700% on the backtest and this correlates to
this on paper'. Till Monday focus on backtests; use OpenClaw to access the
website we used at the beginning to find backtest strategies and upload ours;
OpenClaw can research Reddit and GitHub — we are not utilising it. Telegram:
the bot should respond using the local model, but the local model should not
always run (4 GB VRAM); message OpenClaw, it opens X, uses all our files.
Review Railway, make it cheaper, look at other projects, copy from them. Our
value proposition: (1) a cheap, accessible tool for the average person — a
small hedge fund for people who don't know how to invest, educational, guidance
— how do we make revenue; (2) my investing tool — beat the S&P 500, manage my
money without me involved much. Continuous learning. We don't have a solid
strategy we can say wins. Use all the news: articles, patents, politicians,
insider-trading news — Trump's insider-trading leak, the Goldman Sachs list
leak — documents we can utilise. From news, demand, forecasts and analysis, an
LLM plus our infrastructure makes investments more profitable than the S&P: a
human investor, but better, with infinite data. Review and rank us against
competitors, firms, projects: why we are better, what to focus on. Be
interdisciplinary: patents, research papers, anything we can utilise."
