# HANDOFF — 2026-08-21 (afternoon): what Murat wants, in his words, mapped to the machine

Written after Murat said there is a **misconnection**. This document is the
map every next session should load before choosing work: his asks, verbatim,
against what exists, so no session ever again builds the right thing without
telling him it is the thing he asked for.

## 1. The wants, verbatim → state

| Murat's words | What exists | Gap |
|---|---|---|
| *"make the paper accounts 3 months 3 months since we are updating and finding new methods"* | **His own decision, already adopted 2026-08-19**: `docs/DECISION_QUARTERLY_LANE_GENERATIONS.md` — every ~3 months a NEW generation of real lanes transports referee-verified findings. **G2 generation: 2026-09-08** (winner-hold pair + risk-sized pair). | G2 preregs drafted, need his signature before 09-08. Nobody had told him this decision *was* his "3-months" ask. |
| *"test the current always-updating engine as a paper account, maybe 10 of it running at the same time"* | **The arena.** Now **9 books** (was 7 — `AGGRESSIVE_TOP5_v1` + `DIVERSIFIED_TOP20_v1` added today, free while unseeded), current engine, daily decide/grade/learn pass at 17:45 ET in the cloud, deployed today. | **Unseeded.** `AEGIS_SEED_ARENA=1` for one boot — his, LAST. This flag is the entire remaining "waiting". |
| *"sector focused, strategy focused, very high risk, aggressive etc"* | Aggressive/diversified = the concentration axis, live today via the whitelisted per-book `overrides` (costs/benchmark stay common — the factorial's world). Strategy-focused = the finding-isolation books (risk-sized, winner-exempt, anti-signal, LLM×2). | **Sector books need a PIT sector source** (queue §3.1). Utility personalities (preservation→extreme growth) are a GRADING read on the ledger, never tuned — do not build them as books. |
| *"paper accounts are cheap, why are we waiting"* | Right, and the honest answer: books are cheap; the flag was attended-by-design. After the seed there is NO further waiting step in the daily loop. | Seed. |
| *"an engine that sees potential, creates a great portfolio, manages it, maximizes ROI"* | Sees: discovery over 400 liquid names (28 nominated live). Creates: composite → top-k under declared personality. Manages: monthly rebalance + daily substitution + winner exemption + LLM tilt. Maximizes: reliability/regret ledgers accrue what worked, quarterly generations transport it. | The "sees" is thin — composite is 99.5% momentum until WRDS-fed features land (Q1). The "maximizes" needs forward cells before a learned allocator may replace the simple rule (Q2 stands). |
| *"log every day what happened vs what we thought"* | `pi_daily_digest` (18:15 ET, deployed today) → `digest_corpus.jsonl` + `/api/optimus/digest`. | First row lands tonight; nothing else. |
| *"nights run even if the PC is closed"* | Tier 2 done (everything daily is cloud-side). Tier 1 hardened (WakeToRun pattern). | Tier 3: IIF shadow runner + 3-night receipt comparison → disclosed amendment (§3.4). |

## 2. What was deployed today (both pushes verified live)

- Push 1 (`0de7db5c`): the 25-commit arena backlog + `pi_daily_digest` + roadmap/rules audit.
- Push 2 (this one): 9-book arena (personality pair + `overrides` mechanism, refusal-tested), this handoff.
- Baselines: `all_fresh: true`, jobs `ok` (10), degraded only on pre-existing `prediction_ledger not ok`.

## 3. Queue for next sessions, in order

1. **Sector-focused books.** Needs an arena-local PIT sector map: live via a
   declared static config mapping (the 11-sector ticker lists in
   `backend/config.py` are already declared surface), historical via CRSP
   `siccd` from the substrate. Implement as a whitelisted per-book
   `universe_filter`, refuse-at-load for unknown sectors, control twin
   unchanged. Books are NEW ids in a NEW yaml version if the seed has
   happened by then.
2. **Q1 — WRDS-fed universe-wide features** once tonight's pull closes and
   `wrds_verify_substrate` passes. This is what turns "sees potential" from
   momentum-only into the diverse composite (+0.239, 20× the aggregation fix).
3. **G2 lane-generation preregs** ready for Murat's signature before 09-08.
4. **Tier-3 night runner shadow** (Railway/GH-Actions cron), 3 parallel
   nights, receipt diff, then the amendment. Never mid-clock without it.
5. **Known-answer battery** (G1 → PASSED) — the arena adds a surface: plant a
   synthetic edge in a fake day-state, verify the reliability ledger recovers
   it at the declared rate.
6. **Personality GRADING read**: the four declared utilities scored over the
   arena ledger (a read, not a book; preferences never tuned against history).

## 4. Attended (Murat) — the complete list, nothing hidden

1. `AEGIS_SEED_ARENA=1`, one boot, after today's second push. **This is the
   un-waiting.** 9 books start accruing the next 17:45 ET pass.
2. Laptop plugged in 16:55–17:05 daily (first self-launch TODAY 17:00).
3. MAX_ROWS cap decision (handoff `2026-08-21_ARENA_LEARNS` §2).
4. G2 prereg signatures before 2026-09-08.
5. NAV stamp fix P-day-2026-08-19a · positions read · LOSS amendment ·
   Track E prereg.

## 5. Late-afternoon update (Order 26 session, Murat away)

Built and pushed (`e4df73c`, `dd46dca`, `346b9f9`): **RELIABILITY_ROUTER_v1**
(the first grades→trust layer; known-answer battery 21/21; recommendation
receipt at `/api/arena/router`, consumed by nothing) and the **session-state
layer** (`scripts/session_state.py` + SessionStart hook — sessions now
measure state at start instead of trusting remembered handoffs). Order 26
adjudication in `docs/ROADMAP_POSITION_2026-08-21.md` §7.

**Postponed until after tonight''s night run (17:00 → ~21:30):**
- machine-loading local work (quiet window 16:45–17:05 is absolute)
- reading N4''s receipt — the FIRST SELF-LAUNCH receipt — at ~21:35
- WRDS catchup continuation (AegisWRDSPullNight fires 22:00 by design)

**Postponed until the WRDS pull closes (~10:00 tomorrow) AND
`wrds_verify_substrate` passes:**
- Q1 universe-wide diverse features → new `COMPOSITE_VERSION` (this is what
  fixes "sees potential = 99.5% momentum")
- Q4 / any NN or supervised training (risk heads first, §59)
- P2 source-catalog activation of anything feeding the composite

**Postponed to their own sessions:** Optimus MCP upgrade (send a User-Agent —
the edge resets bare urllib, measured today), teacher/investor-behaviour
engine on SEC as-filed timestamps, sector books (PIT sector source),
CURRENT_BEST_v2 challenger.

## 6. Order 26 round 2 (late afternoon) — the profit standard, and the allocator

**STANDING SENTENCE, adopted into every future handoff and review:**

> A component does not count as part of the profit engine until it can trace
> a causal path from new information → changed forecast → changed capital
> allocation → executed paper decision → graded outcome.

By that standard, as of `5235f14`:
- **PROFIT_ALLOCATOR_v1 built** — 10th book, the first whose mechanism is
  the ALLOCATION: declared Grinold/Kelly mapping, first book that can hold
  cash, gross exposure follows conviction, and it CONSUMES the trust router
  (quarter-Kelly until the ledger vouches). The causal path above is closed
  for this book from its first seeded day.
- RELIABILITY_ROUTER_v1: now consumed (by the allocator book only).
- Everything else GPT''s table lists as missing stays honestly missing:
  return-forecast layer (WRDS-gated), marginal-wealth substitution,
  conditional winner/re-entry model, independent alpha books,
  router v2 (independence-aware), pm_engine full integration.

**Murat''s new asks (this turn), adjudicated:**
- *"NN continuously learning from news"* — gated on substrate verify + the
  event corpus the arena is now accruing; the digest + experience ledgers
  ARE the training-row factory he is asking for. Queue: after WRDS Q1.
- *"LLM websearch for news without APIs"* — for FORWARD paper (arena) this
  is legitimate (forward = PIT by construction). Route: widen the typed
  event feed (event_intel) + LLM_EVENTS ablation measures its value. Raw
  websearch inside prod DeepSeek calls does not exist; a search-capable
  reviewer is a cost/API decision that is Murat''s.
- *"LLM improves the code itself"* — `lab/rd_loop.py` already does exactly
  this with Claude sessions (his "or i can just use this terminal");
  running it nightly is HIS call (subscription usage). DeepSeek stays out
  of code-modification, agreed.
- *"backtests + paper accounts as training data"* — that is the experience/
  outcome ledger design (arena) + the WRDS substrate (historical). The
  novel part he wants is exactly the closed loop now being assembled:
  graded forward experience feeding a learner that reallocates capital.

**Next sessions, revised order (GPT''s sequence, adjudicated):**
1. (Murat) seed — now seeds 10 books including the allocator.
2. After WRDS verify: return + risk forecast layer (return gets equal
   priority to risk now), universe-wide features, new COMPOSITE_VERSION.
3. Marginal-expected-wealth substitution (replaces z-margin) as a
   PROFIT_ALLOCATOR_v2 descendant — needs the return/risk distributions.
4. Conditional winner/re-entry model (P(continue), thesis-break detection).
5. Independent alpha books (revisions/event/teacher/sector) — each with its
   own selection signal so distinct_selection_signals finally rises.
6. RELIABILITY_ROUTER_v2 = reliability × effective independence × state.
