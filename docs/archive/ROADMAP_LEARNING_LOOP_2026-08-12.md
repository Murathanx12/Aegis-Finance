# ROADMAP — the self-evaluating brain (NIGHT-14 onward)

> **SEQUENCING SUPERSEDED 2026-08-14** by `ROADMAP_BRAIN_V3_2026-08-14.md`
> (post-GRAND-ARENA pivot). The two dependency edges below — router waits for
> the reliability tensor, gym waits for known-answer worlds — are inherited by
> V3 and still bind.

**Written 2026-08-12.** Supersedes the sequencing (not the standards) of
`AEGIS_EXECUTION_ROADMAP.md` for the LLM/learning-loop arc. The certification
gates and the discovery bar in that document still bind; this one says what gets
built in what order and, more usefully, **what blocks what**.

Source: the external review archived in `NIGHT14_EXTERNAL_REVIEW.md`, Murat's
prompts of 2026-08-12, and three nights of results that all pointed the same
way.

---

## The organising claim

> **Optimus is the player. Aegis is the referee. The referee's job is to decide
> whether the player is learning or fooling itself.**

Everything below is an instrument for one of those two roles. An item that
serves neither does not belong on this roadmap.

The thing that made this arc possible was not a new model. It was noticing that
**explanations can be graded far faster than forecasts**, because an explanation
of yesterday makes claims about instruments whose prices are already known.
Grading latency went from 31 days to under a minute. Every item below assumes
that clock.

---

## Dependency order (this is the load-bearing part)

```
        [ledger persistence] ──┐
        [fast horizons 1d/2d] ─┼──> WHY-MOVED ──> reliability tensor ──┐
        [LLM telemetry] ───────┘    (specialist × domain × horizon)    │
                                                                        │
                                                    ┌───────────────────┘
                                                    v
                                          [contextual-bandit router]
                                                    │
   [synthetic known-answer worlds] ──> [Portfolio Gym] ──> [EXIT-RL]
                                                    │
   [PIT geopolitical event data] ──────────> [GEO-1]
        (collected BY why-moved)
```

Two edges in that graph are the ones previous plans got wrong:

1. **The bandit router cannot come before the reliability tensor.** A router
   allocates budget across specialists based on how reliable each has proven. On
   2026-08-12 there are zero resolved reliability estimates. A router built now
   routes on noise and then justifies its own allocation — the worst kind of
   plausible system.
2. **The Portfolio Gym cannot come before known-answer worlds.** Before trusting
   an RL learner to *discover* exit rules, prove it can *rediscover planted
   ones*. A learner that cannot recover a rule you put there by hand has not
   earned the right to be believed when it finds one you didn't.

---

## NIGHT-14 (tonight) — see `NIGHT14_BRIEFING.md`

Ships: fast horizons · ledger persistence · scheduler job-set canary · WHY-MOVED
· LLM telemetry · `WINNER-GENOME-1` · `THEME-CASCADE-1` (prereg) ·
`MODEL-ORCHESTRATOR-BENCH-1` (bounded).

---

## NIGHT-15 — make the loop wide, then let it run

**Goal: thousands of resolved reasoning experiences, not 87 anecdotes.**

| Item | Why now | Done when |
|---|---|---|
| WHY-MOVED across the **opportunity universe**, not just Murat's book | One 12-name book gives almost no power. The same machinery over 150+ names multiplies the sample by an order of magnitude per night at near-zero marginal cost. | Nightly run covers the screener universe; per-night gradeable-hypothesis count reported. |
| First **reliability tensor** read | The first 1d/2d corroboration grades will have landed. Slice specialist × domain × horizon, each with its own n and MDE. | Published with counts; every slice below its MDE labelled *not detectable*, never *bad*. |
| **Shadow-book seeding** (attended) | Carried since NIGHT-13. Needs Murat present; the seed path does not exist and inventing one unattended risks a fake inception. | Frozen inception state + controls, human-flipped flags. |
| **Ledger persistence verified across a real deploy** | Tonight's migration is tested but the proof is a redeploy with records surviving. | Record count identical before/after an actual Railway deploy. |
| **MCP context health** | An agent with stale context executes perfectly and does the wrong research. Add source HEAD, ingested HEAD, brain age, latest session/trial seen; stale ⇒ DEGRADED. | A clean session gets current state through MCP without reading repo files. |

---

## NIGHT-16 — the environment

| Item | Notes |
|---|---|
| **Synthetic known-answer worlds** | Plant a known-optimal policy (a rule that trims after a specific observable state) and verify the learner recovers it. This is Gate D logic applied to RL: certify the instrument before trusting its output. |
| **Portfolio Gym v0** | PIT state; actions BUY/ADD/HOLD/TRIM/SELL/REPLACE/HEDGE/exposure; reward = compound wealth − drawdown penalty − ruin penalty − costs − concentration − liquidity. Different user modes are different utility functions, not different engines. |
| **Counterfactual branch expansion** | The NIGHT-12 "cash never won in 60 rows" result is one tiny sample. Branch every historical decision across thousands of securities and dates, resolve at 1/5/20/60/120d. This is how that null gets its real denominator. |

---

## NIGHT-17+ — candidates, not commitments

- **EXIT-RL-1** — ADD/HOLD/TRIM/SELL/REPLACE learned across millions of
  stock-days rather than 60 branches from one book. Depends on the Gym.
- **GEO-1** — does LLM-extracted *change* in conflict probability add anything
  beyond oil/VIX/rates/trend? Depends on PIT event data, which WHY-MOVED starts
  collecting tonight. **Do not tune a war rule on the one war we know about.**
- **THEME-CASCADE-1 compute** — second-order beneficiaries. Pre-registered
  tonight precisely so the SK Hynix / SanDisk / WDC / Kioxia / Vicor pattern
  cannot be retrofitted into its own evidence.
- **LLM-DISAGREEMENT-1** — is disagreement between specialists itself a useful
  uncertainty signal? Nearly free once WHY-MOVED runs nightly: the disagreement
  is already being recorded.
- **Contextual-bandit router** — unblocked once the tensor has resolved
  estimates with usable n.
- **Public baselines** (Qlib / RD-Agent / FinRL / FinMem / TradingAgents) — the
  reviewer is right that "self-learning" claims are worth little without them.
  Reuse before rebuild.
- **Product: three risk budgets, four modes** — Core / Aggressive / Convex from
  the *same* evidence with different sizing; Advisor / Copilot / Autonomous
  Paper / Attended Live. Autonomous Paper becomes the primary learning lab.
  Real-dollar autonomy stays separately gated — it must never follow
  accidentally from research automation.

---

## What this roadmap refuses

- **One monolithic neural network.** Neural models are organs, not the brain.
  Each earns adoption only by beating a simpler baseline out-of-sample; LightGBM
  is the first baseline, not the fallback.
- **Replaying 2010–2025 until something profitable appears.** That produces a
  system brilliant at 2010–2025. Protected holdouts, PIT data, preserved search
  denominators and forward paper evidence are what separate a finding from a
  memory.
- **Letting call volume become the success metric.** The metric is gradeable
  output per dollar. A call that produces no learning sample is a cost with no
  offsetting entry — and the telemetry ledger exists to make that number
  impossible to look away from.
- **Lowering any bar because there is now more data.** §19 and §20 apply
  unchanged. Deflation is cumulative across every trial ever registered.

---

## The standing bet

Three nights have now measured the same thing from three directions:
NIGHT-12 (`sell_to_cash` never best in 60 rows; dd 22.9% vs SPY 8.9% at beta
2.15), NIGHT-13 (selection +20..+43 pts, management −29..−66 pts; constant
half-exposure beat the clever ladder), and the Bloomberg winner evidence
(high-dispersion selection plus active execution, with sizing chosen for the
objective).

> **The bet: the edge is in selection and the losses are in management.**

`WINNER-GENOME-1` was registered as the first real test of the bet. It could
fail, and then `EXIT-LAB-1` — the first instrument with a real denominator —
**failed half of it.**

### AMENDED 2026-08-12 after EXIT-LAB-1 (`bb676e1`)

1.58M position-states → 25.3M state-action rows → 152M outcome cells, 11,145
securities, 23 years. It supports the second half of the bet and **withdraws the
first**:

- *The losses are in management* — **supported.** Twenty pre-declared rules, six
  learned policies, sixteen single actions: **every point estimate negative**,
  several detectably so, and the ordering tracks how much each rule trades. The
  best baseline out-of-fold is `NEVER_SELL` itself, so learned-vs-baseline is
  learned-vs-doing-nothing, and doing nothing wins.
- *The edge is in selection* — **no evidence from the mechanisms tested.** Gross
  of costs, `SELL_BENCH` − `HOLD` is **−0.04 pp at 60 days and −0.14 pp at 252**.
  That is the same null NIGHT-14 found for tournament strategy families and
  NIGHT-10 found across 21 configurations, arriving from a third direction.

**The honest restatement after five nights (corrected per Amendment A0 — my
first version over-reached):**

> **No TESTED stock-selection mechanism has produced a large, reproducible,
> product-level advantage, while exposure/risk has repeatedly produced large
> effects.**

That is deliberately narrower than "selection does not matter." EXIT-LAB's
replacement arms were momentum/revision-ranked **proxies** and its holders were
**synthetic entry cohorts** — the report says outright that the momentum proxy
is not claimed to be the best available candidate selector. A null against that
proxy is a null against that mechanism, and the broader phrasing would close the
LLM opportunity-discovery question by assertion rather than by measurement.

That is a smaller claim than the one we started with, it is the one the receipts
support, and it is the least useful claim for anyone selling a strategy. It is
also the one that most changes what a saver should actually do.

**Consequence for this roadmap:** the highest-value build is no longer "the
execution and sizing layer between a good idea and a position size", because the
good-idea half is unevidenced. It is the **exposure** question — and chunk 6 of
GRAND-ARENA-1 is where that gets its own denominator. Note the warning from
KNOWN-WORLD-1's WORLD-L before starting it: a learner handed the exposure lever
**invented a timing edge in a world containing none**, and only
matched-average-exposure comparison and its own MDE refused it.
