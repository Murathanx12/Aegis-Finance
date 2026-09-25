# External research queue (GPT, 2026-09-24) — provenance copy

Murat pasted this into the 2026-09-25 planning session. It is an EXTERNAL
document: its claims about the repo are unverified until the audit in
`ROADMAP_2026-09-25_*` cites a receipt. Kept verbatim in substance so the
next session does not have to ask for it again. Citations in the original
(`chatgpt-content-reference`) were not resolvable and are dropped.

## Its headline claims about Aegis (to verify, not to trust)

1. `xs_ranker.FEATURES` is entirely price/volume/liquidity/volatility; the
   392,201 analyst revision rows do not reach the live ranker. **VERIFIED
   2026-09-25** — `backend/services/xs_ranker.py:146-152` lists 24 features,
   none from revisions, fundamentals, events or text.
2. OpenClaw is healthy but is not a sim unit.
3. The learn rota is mostly `survivorship_audit → breadth_check → idle`.
4. Modules that exist and are not on the decision path: congress_trades,
   ark_holdings, actor_intelligence, holder_fingerprint, short_interest,
   prediction_markets, earnings_intelligence, graph_propagation, world_model,
   investigator_agent.
5. Fleet on 2026-09-24 ~23:00 HKT: hack1 ~$91,154, hack2 $98,820,
   hack5 ~$90,783; hack4/hack6 active (BIOA, MAZE marked). Railway hitting the
   500 logs/sec limit.

## Its direction

- Analyst intelligence around revision FLOW and analyst IDENTITY
  (`analyst × sector × regime × horizon`), not target level. Bloomberg ANR /
  ANRP during the competition for analyst identity and rank.
- Do NOT fine-tune an LLM to BUY/SELL yet; train a deterministic
  forecast-quality/calibration layer on the graded ledger first. LLM extracts
  product / demand / team / competition / falsifiers; engine sizes.
- The forecast ledger becomes a reputation system over every actor: analysts,
  brokerages, insiders, 13F managers, ARK, Congress (45-day lag → delayed
  signal), CEOs, journalists, prediction-market participants, OpenClaw,
  DeepSeek, the local model, Aegis itself.
- OpenClaw as an investigator triggered by CHANGE (shortlist entry, rank jump,
  revision cluster, 8-K/10-Q, earnings, supplier/customer event, unexplained
  move, missed winner, thesis falsifier), returning strict JSON into
  `web_events`, ten fixed quests (what changed / not known yesterday / demand
  vs price vs volume vs mix / suppliers / customers / who loses / contradicting
  evidence / if management right / if wrong / 2nd-3rd order beneficiaries).
- DeepSeek only for adjudication (top candidates, local-vs-DeepSeek
  disagreement, causal chains, contradictions, missed-winner autopsy); every
  DeepSeek call paired with the local model, cost, latency, frozen answer,
  future grade.
- Product Thesis Card per serious candidate: PRODUCT / ECONOMICS /
  COMPETITION / TEAM / TECHNOLOGY INTENT / FORWARD CATALYST (+ falsifier).
- Bloomberg Global Trading Challenge (its dates: reg. Oct 4; Oct 12 – Nov 13,
  2026; $1M virtual; WLS universe; long only; no leverage; max 20%/name) —
  competition engine: WLS → catalyst → revision flow → investigator → product
  thesis → expected relative return → concentrated long-only. Past winners
  cited: 2025 global ~+400% in five weeks; 2024 RIT >$1.6M relative; 2023 HKU
  +67.7%; Iona (small caps into earnings); USF 2025 (earnings vol, NVDA during
  Huang's live remarks, STX on AI-storage); a 2025 top-5% team improved after
  concentrating. **All to be re-verified against primary sources** (see
  `research_bloomberg.md` in this folder).
- Repos: DMulajkar/Quantgress, LSEG RevisionsMomentum sample, luweihai/CARAG,
  kamendula/AlphaAgent, effective-p/FinAgent, xt2201/finmem, StockBench,
  Sunny-1991/13F-Tracker, kylemcdonald/ews, hiring-lab/job_postings_tracker.
- Fifteen experiments: ANALYST LEADER, FIRST MOVER, REVISION CASCADE,
  ANALYST × PRODUCT, NARRATIVE/FUNDAMENTAL DIVERGENCE, PRODUCT BOTTLENECK
  MIGRATION, MANAGEMENT EXECUTION SCORE, FOUNDER TRACK RECORD, SUPPLY RESPONSE
  CLOCK, CHINA CAPACITY SHADOW, IPO READTHROUGH, SMART-MONEY TRACK RECORD,
  MANAGEMENT LANGUAGE DELTA, QUESTION-ANSWER STRESS, ATTENTION ACCELERATION
  NORMALIZED.
- Deliverables it asked for at the end of the next session: PC-PAPER + Railway
  economics · service-utilization matrix · 20 unused capabilities · analyst
  skill leaderboard (past data only) · actor leaderboard · investigator
  leaderboard · top-20 WLS candidates with evidence cards · five frozen $1M
  books (event/earnings, analyst revision, product/bottleneck, LLM
  investigator, ensemble) · frozen forward predictions · weight changes ·
  DeepSeek cost and incremental value · hypotheses to continue/kill · one
  answer to WHAT CURRENTLY WORKS.

## Where it overlaps what the repo already banked

- "Revision flow not level" = `RESEARCH_QUEUE.md` Q-4 (precondition closed
  2026-09-24; still untested).
- "Product / bottleneck migration" = Q-5.
- "IPO readthrough" = Q-7. "China capacity shadow" = Q-8.
- "Investigator works, personas do not" = NEGATIVE_RESULTS §64 (the source of
  the claim, not a confirmation of it).
- Congress / insider / ARK / 13F as delayed actors = TRIAL-CONGRESS-IC,
  TRIAL-INSIDER-IC, TRIAL-CMP-INSIDER-IC, TRIAL-ARK-IC (accruing forward since
  August; `TEACHER-LIBRARY-1` prior = STOCK Act mean-politician null).
