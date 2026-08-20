# ORDER 25 — LIVE LEARNING ARENA, GENERATION 1 (adopted 2026-08-20, evening)

Murat's instruction (2026-08-20, verbatim intent): *"the current LLM plus the
engine should constantly be on the paper accounts with multiple accounts, and
it should constantly learn and improve itself... every time we have a new
strategy, a new methodology, we should [test it forward]... this is your
sandbox... make the best decisions that will result in max ROI."* An external
review (GPT) proposed "ORDER 25 — PAPER ARENA GENERATION 1"; per the standing
rule an external review is ADJUDICATED, not imported. This document is the
adjudication and the adopted order.

## 0. The verdict on the diagnosis

**Murat is right, and the audit quantifies it.** The complaint was "we build
intelligence and never wire it into the paper process." Measured 2026-08-20:

- Of the 20 collectors in `_daily_check` (scheduler.py:570-841), **4 arm
  lanes and 16 are descriptive-only with no consumer of any kind**. The PIT
  store accrues daily; nothing reads it to make a decision.
- The EXPERIENCE record (designed 2026-08-09, implemented in
  `Aegis module\aegis_brain\night3\experience.py`, 16,320 graded rows) has
  **no forward writer**. Not one live decision has ever minted an Experience.
- `llm_analyzer.py` outputs are cache-only + a telemetry hash. **Nothing the
  product LLM says is gradeable later.**
- COPY-LAB — the one existing PRODUCT_EXPERIMENT arena — was seeded
  2026-08-14 and **never scheduled**: one engine pass ever, one signal row,
  no positions.json, no nav.jsonl. Six days of seeded lanes doing nothing.
  This is the house failure mode (silent green) applied to the product loop.

The architectural error was real but is NOT "the methodology is too strict."
It is: **we forced every forward account through the certification standard,
and the one legitimate escape hatch we built (PRODUCT_EXPERIMENT) was left
unwired.** The fix is to finish the escape hatch, not to weaken the
certification lanes.

## 1. What is adopted, what is amended, what is rejected

### Adopted (from the review, adapted to house machinery)

1. **Two simultaneous systems**: immutable evidence lanes (Generation-0, the
   10 lanes since 2026-06-08, untouched, keep running) + a continuously
   evolving **product arena**. The arena is a new namespace `arena`, built on
   the copy_lab pattern: own YAML + whole-file hash, own file ledger under
   `OPTIMUS_LEDGER_DIR/arena/`, **never touches `paper_nav`, never a lane
   YAML, never the order path**. CANON §5 is not weakened one line.
2. **Three grades, machine-checkable** (already in the codebase; now used):
   `RESEARCH_SCREEN` → `PRODUCT_EXPERIMENT` → `CERTIFIED_FORWARD`.
   Every arena artifact stamps `validation_status: PRODUCT_EXPERIMENT`,
   `simulation: true`. Nothing from the arena may be cited as evidence of
   skill, ever — same sentence copy_lab already carries.
3. **The lifecycle** IDEA → HISTORICAL SCREEN → KNOWN-ANSWER/LEAK/COST CHECK
   → **ARENA BOOK (forward paper, next day)** → EXPERIENCE accrual →
   CHAMPION COMPARISON → PROMOTE (to a real lane at a generation window) /
   SHELF / KILL. The step we were missing is the arena book; it is now the
   default landing place for any surviving screen.
4. **The daily experience loop**: every arena decision — chosen AND rejected
   near-miss — writes a forward EXPERIENCE record (schema-compatible with
   the night3 store: information_state_hash, model ids, thesis, direction,
   confidence, expected return, invalidation, horizon, policy version).
   Outcomes matured at 1/5/21/63/126 trading days by the same job. Rejected
   alternatives get counterfactual outcomes → opportunity cost becomes a
   label. **No training on same-day P&L; reliability updates only from
   matured outcomes.** This is the corpus the NN eventually trains on — the
   training unit is decision/security/information-state, never portfolio-day.
5. **DISCOVERY_UNIVERSE**: the 16 orphaned collectors become the candidate
   feed. Daily aggregation of: current book holdings, reference universe,
   insider/CMP-insider scores, revision movers, multifactor/PEAD/quality
   scores, ARK/13F/congress context, top movers. Every candidate goes
   through one opportunity funnel; the daily question is **capital
   substitution** ("better than the weakest current use of capital after
   costs?"), not isolated ranking.
6. **LLM in the decision pipeline, never in sizing.** The LLM perceives
   (what changed, does it contradict the thesis, probability revision with
   bounds); a deterministic allocator converts the full information state
   into weights under hard caps. LLM belief revisions are written as
   gradeable prediction records (belief_state schema) — fixing "nothing the
   product LLM says is gradeable."
7. **Policy versioning**: a material change never edits a live arena book;
   it creates `<BOOK>_v(N+1)` with a segment receipt, and the old version
   keeps running as a shadow comparator for a declared overlap. Lineage is
   the product ("what actually improved Aegis"), not a mutating account.
8. **Four learning cadences**: daily = calibration/reliability bookkeeping
   from matured outcomes only; weekly = versioned model refresh (challenger,
   never champion-in-place); drift-triggered = spawn an adapted challenger;
   generation = promotion to real lanes. Nothing retrains on an afternoon.

### Amended (where the review conflicts with measured results or standing decisions)

1. **"AEGIS-CURRENT-BEST uses everything we currently believe is useful"** —
   amended to *everything that has survived measurement*. The honest v1 stack
   is: trailing-63d-vol inverse sizing (the baseline that beat the model five
   ways), the +40 winner-exemption (CONVEXITY-PRESERVATION-1,
   Holm-surviving), streak-avoid and factor-reversal-avoid screens (the two
   Holm-surviving anti-signals), cost-aware substitution. NOT included as
   drivers: the LGBM risk head as a sizer (five routes lost to trailing
   vol), return prediction (nothing clears the bar), regime routing (oracle
   ceiling +0.24%/yr). Those enter as *challenger books*, so their marginal
   value is measured, not assumed.
2. **Champion/challenger cadence** — the 2026-08-19 quarterly-generations
   decision REJECTED continuous real-lane launches and adaptive
   capital-shifting, and ADOPTED shadow books as the complement. This order
   implements exactly that split: **challengers are arena books (shadow,
   unlimited, next-day), promotions are quarterly real lanes** (next window
   2026-09-08, per `seed-a-lane`, Murat flips the flag). The review's
   "spawn a challenger paper lane immediately" happens in the arena, not in
   `paper_portfolios.yaml`. Correlated books are counted honestly: the
   arena reports effective dimensionality next to book count.
3. **"The NN router"** — staged, not started. The >100k-graded-experiences
   gate (2026-08-09 decision) stands, but the arena is precisely the machine
   that makes it reachable: forward experiences at hundreds/day + the
   existing 16,320 replay experiences + nightly IIF-1 records as they grade
   (first 195 resolve 2026-08-21). The first learned component is the
   reliability/calibration table (per specialist, per state), which is just
   counting — the contextual-router NN comes when the corpus exists.
4. **UI headline change** (Current Best surfaced above generation-0 lanes) —
   agreed in direction; ships only after the arena has run long enough to
   have something to show, and with PRODUCT_EXPERIMENT labeling. Not a
   tonight deliverable.

### Rejected

1. **Retiring or demoting the Generation-0 lanes now.** They keep running
   untouched (standing rule: old generations are the baseline the new one
   must beat in the open; retiring is attended, recorded).
2. **Any arena write to `paper_nav`, lane YAMLs, the registry, or the order
   path.** The arena is JSONL under its own namespace, full stop.
3. **Training anything on portfolio NAV or same-day P&L.** ~250
   portfolio-days/year is memorization bait; the decision corpus is the
   training set (this was already the design; it stands).
4. **"Run 50–100 shadow portfolios."** Start at 6 with a factorial shape.
   Effective dimensionality of everything we own is 3–7 (Order 24); 100
   correlated books are theater. Books are added when a screen survives,
   not to look busy.

## 2. Generation-1 arena books (the factorial)

| book_id | isolates | rule (v1) |
|---|---|---|
| `ENGINE_BASELINE_v1` | control twin | discovery universe → top-K by frozen composite (multifactor PIT score), equal weight, monthly + drift rebalance, 5+1 bps costs |
| `RISK_SIZED_v1` | sizing finding | same selection, weights ∝ 1/trailing-63d vol |
| `WINNER_EXEMPT_v1` | convexity finding | baseline + position up ≥40% since entry exempt from trims 60 trading days |
| `ANTI_SIGNAL_v1` | streak/factor-reversal findings | baseline + exclude candidates in ≥5-day up-streaks and last-month factor-chase leaders |
| `LLM_PERCEPTION_v1` | incremental LLM value | baseline + LLM daily belief revisions (bounded ±20% multiplicative tilt via deterministic mapper; every revision written as a gradeable prediction record) |
| `CURRENT_BEST_v1` | the composed product | risk-sized + winner-exempt + anti-signal + LLM perception + capital-substitution funnel |

Benchmarks: SPY, QQQ, and `ENGINE_BASELINE_v1` itself. Same universe clock,
same notional ($100k), same cost model, same execution rule (next-session
open after decision, the copy_lab convention). Correlation between books is
reported weekly; nobody pretends 6 books are 6 independent experiments.

## 3. What runs where (the automation answer)

- **The arena runs on Railway**, inside the existing backend scheduler —
  new job `pi_arena_daily` (17:45 ET, after collectors and close marks).
  Zero new services, zero new monthly cost beyond pennies of DeepSeek
  (arena LLM budget: 25 calls/day, drawn under the research governor, hard
  cap). It runs when the PC is off — this is the "runs even if my laptop is
  closed" half of the request.
- **COPY-LAB gets scheduled** (`pi_copy_lab_run`, 10:00 ET) — closing the
  six-days-seeded-zero-runs gap. Engine pass only; seeding stays attended.
- **The IIF-1 night stays local and frozen.** It needs the sibling repo,
  the receipt corpus, and a residential IP; a cloud fork would silently
  break one-attempt-per-night and the equivalence chain (mapped 2026-08-20).
  Robustness fixes applied tonight instead: WakeToRun on,
  battery-blocking flags off, arming verified at User scope, stdin fix
  confirmed, tree clean. Migration to cloud is a post-40-night decision.

## 4. Answers to the review's ten questions

1. *Unused components?* 16 of 20 collectors, the EXPERIENCE store, the
   research_gym counterfactual surface, llm_analyzer outputs, COPY-LAB
   engine — all previously uncalled; the arena is their caller.
2. *What does CURRENT_BEST consume that Gen-0 does not?* Discovery universe
   (insider/revisions/multifactor/PEAD/quality PIT scores), the three
   verified rules, LLM perception records, experience memory.
3. *Ablation differences?* Exactly one rule per book vs `ENGINE_BASELINE_v1`
   (§2 table); CURRENT_BEST is the composition.
4. *What information creates each trade?* The frozen daily snapshot:
   discovery candidates + PIT scores + prices + (for LLM books) the
   perception record. All hashed into `information_state_hash` before
   outcomes exist.
5. *How does a challenger enter?* Surviving screen + known-answer/cost
   check → new book YAML entry + spec receipt → runs next day. No
   signature needed below CERTIFIED; the YAML hash is the commitment.
6. *How does it graduate?* Quarterly generation window, pre-registered
   real-lane pair (treatment + control twin), Murat signs and flips —
   unchanged from the 2026-08-19 decision.
7. *How does the brain learn from chosen AND rejected?* Every funnel
   decision writes chosen + best-rejected experiences; the rejected leg
   gets counterfactual outcomes at maturation; regret is a label.
8. *What adapts at which cadence?* §1-adopted-8. Daily: nothing but
   bookkeeping. Weekly: versioned challenger refresh. Generation:
   promotion. Champion specs never mutate in place.
9. *How many independent strategies?* Reported, not assumed: weekly
   effective-dimension estimate over book return panels (the Order 24
   machinery), printed next to the book count.
10. *Reconstructable months later?* Every decision stores snapshot hash,
    config hash, policy version, model versions, prompt hashes; stores are
    append-only write-once. Same discipline as the night receipts.

## 5. Tonight's build (this session) — DONE unless marked

1. `backend/services/arena/` — spec/store/discovery/policies/experience/
   perception/engine + `backend/routers/arena.py` (read-only surface).
2. `backend/data/arena/arena_books_v1.yaml` — the six Gen-1 books.
3. Scheduler: `pi_arena_daily` (17:45 ET) + `pi_copy_lab_run` (10:00 ET),
   EXPECTED_JOB_IDS in lockstep, canary green.
4. `scripts/arena_run.py` — --status / --seed / --run.
5. Tests: 25 offline arena tests + full fast suite.
6. G2 prereg draft carries a 08-20 drafting note (arena books shadow-run the
   two G2 rules from today).
7. This document; `docs/AUDIT_PRODUCT_INTEGRATION_2026-08-20.md`; memory.

### Selection-signal decision made during the build (recorded)

The six PIT score collectors all run on the ~12-name book cross-section, and
widening them would change their z-scores mid-trial (registered forward-IC
clocks). So the arena computes its OWN composite (`arena_composite`) over its
own ~180-name universe: **12-1 momentum from prices (last month excluded — the
anti-chase findings)** blended with whatever PIT families a name has, via the
same frozen pure estimator (`compute_multifactor_scores`). Registered trials
untouched; the PIT stores become components instead of gates. A live
rehearsal (throwaway root) confirmed: 180/180 scored, six differentiated
12-position books, 90 experiences written and matured, LLM perception minting
gradeable records. A breadth guard (`insufficient_breadth`, min 5 names)
refuses the degenerate one-stock book the first rehearsal produced.

Deploy note: everything lands as local commits on `main`. **Pushing deploys
Railway** — that is a one-command attended step for Murat (~30 local commits
ship together; `verify-prod-after-deploy` applies). After deploy: set
`AEGIS_SEED_ARENA=1` for ONE boot, confirm `/api/arena/status`, unset.

## 6. What stays sacred (unchanged by this order)

CANON §5 (paper_nav write path) · seed-a-lane (real lanes attended,
env-gated) · pre-register-trial for anything that will be *evaluated* ·
§63 screen/export discipline · the 24-month no-skill-claims floor · IIF-1's
frozen surface · the quarterly generation cadence · "the LLM narrates, the
engine computes" (arena LLM tilts are bounded, deterministic, logged, and
themselves graded).
