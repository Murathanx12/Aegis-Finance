# NIGHT-10 — SESSION BRIEFING FOR OPUS

**8-hour autonomous campaign. 2026-08-11. Written by the brain session, ruled on by Murat.**

Work autonomously the whole window. Do not stop after one build, one null, or
green tests. If a task blocks, record why and move to the next independent
task. Do not wait for Murat unless a genuinely indispensable secret is missing
— and per standing feedback, never say "blocked" until the endpoint has been
called and the status code printed.

---

## 0. Read first (15 minutes, no more)

1. `docs/HANDOFF_ARENA1.md` — the four numbers and the printed contradiction
2. `docs/RESEARCH_PM_FLYWHEEL.md` — the architecture you are executing
3. `mcp: session_briefing()` + `aegis_verified_state()` — live state
4. This file, to the end, before writing code

The Aegis module repo is `C:\Users\mrthn\Aegis module` (research engine,
WRDS/CRSP panels, trial harness). This repo is the product. Both are clean at
`cdf5a45` / `481ea47`.

---

## 1. THE REORIENTATION (Murat's ruling, binding)

Last night drifted toward "audit Murat's $45k book." That is not the product.

**The product: given ANY amount of capital — $10k, $40k, $1m, $50m — Optimus
searches the investable US market, identifies the highest expected-return
opportunities it can JUSTIFY, constructs portfolios, manages them, and tries
to outperform the market and professional investors — with the ruin number
always printed beside the dream number.**

Murat's MIRROR book is one live laboratory for this. It is not the objective.
Do not spend the night on his cost bases. Do not optimize his 12 positions and
call it done.

Write `docs/OPTIMUS_OBJECTIVE.md` stating this, including: Research discovers
exploitable information → the deterministic PM converts evidence into
portfolios → the Arena searches implementations → forward books generate new
evidence → the LLM expands the hypothesis space. The LLM narrates and
hypothesizes; the engine computes and allocates.

**Three rulings embedded in Murat's directive, now in force:**

1. **Iterative search is LICENSED** — inside exploration data only (§4).
   "Don't overfit" was never supposed to mean "don't search."
2. **The LLM is a component, not a luxury.** $0 spend is a defect from
   tonight forward. Budget: **$30 for the campaign** (§3).
3. **The heresy sleeve is APPROVED as the HERESY LAB** — research-only,
   never production (§6). This closes the open ruling from the handoff.

**Risk and evidence are different dimensions.** A credible 35%-vol strategy is
not inferior to a 12%-vol one; a leaky 35% one is worthless. Never hide a
high-return portfolio because volatility is high — hide it only when the
evidence is bad. Report both dimensions separately, always.

---

## 2. PHASE 0+1 — VALIDATE, THEN FIX THE PRODUCT'S PRINTED CONTRADICTION

**Phase 0 (≤30 min): validate ARENA-1 on disk before building on it.** The
home handoff requires it: genome-freeze commit `d0ab548` predates scoring; the
four numbers have receipts under `Aegis module/runs/ARENA1/`; one-pass check.
If validation fails, that becomes P0 and the rest of this briefing waits.

**Phase 1: the EVIDENCE CONFLICT (HIGH).** `backend/services/daily_brief.py`
still ranks new-buy candidates by analyst-implied upside — measured last night
at **−8 to −18%/yr gross over 21 years of PIT IBES**. First task, no
substitutes:

- The candidate list becomes the output of `opportunity_funnel.py`.
- The recommendation engine must consume `signal_registry.py`. A signal
  graded CLOSED / NEGATIVE / RISK_INPUT / FILTER_ONLY must be structurally
  unable to dominate a BUY ranking — enforced in code, with a test that
  fails if a closed signal leads.
- Do not merely hide the warning; keep the conflict detector alive as a
  permanent invariant check.

Build the recommendation decomposition (per ticker): recommendation, ranking
score, expected-return **only if calibrated** (else say "not calibrated" and
give percentile + interval), confidence, evidence grade, signal contributions,
catalysts ±, risk factors, kill condition, size candidate, reason-for-rank,
better alternatives. **Never invent an expected return.** The distinction
between "calibrated ER" and "relative alpha score" is printed, not implied.

---

## 3. USE THE LLM — SERIOUSLY, INSIDE THE FIREWALL

Budget **$30**. Deploy has DeepSeek wired (150 calls/day cap, breaker off);
Claude API for the calls where reasoning quality is the point. Every call goes
in an **LLM call ledger** (model, purpose, cost, output hash). Ask in basis
points, not prose (NIGHT-3: 5/5 vs 3/5 coherence).

Roles — market research scientist, never price oracle:

- **Hypothesis generation**: feed it the signal registry, the graveyard
  (NEGATIVE_RESULTS.md, 148-row census), data inventory, ARENA-1 results.
  Demand per proposal: mechanism, economic rationale, why the market
  underreacts, PIT data required, horizon, expected turnover, best
  falsification, **closest existing corpse and why this is genuinely
  different**. Proposals that can't name their corpse go straight to the
  linter anyway (§4).
- **Adversarial portfolio review**: separate pass, "why is this portfolio
  probably overfit or wrong?"
- **Cross-source contradiction mining**: price vs revisions vs insiders vs
  options vs guidance. Contradictions are candidate mispricings.
- **Failure diagnosis + descendant design** on explore results only (§4).
- **Structured extraction** from filings/events where it feeds a measurable
  fundamental prediction — never "trade the sentiment."

Hard lines (standing, unchanged): the LLM never assigns production weights,
never sees validation/confirmation data before its strategy is frozen, never
grades its own experiment as passed. Entity masking where the protocol
requires it — instruction-based forgetting does nothing (NIGHT-1).

---

## 4. ALPHA FACTORY v2 — SEARCH IS REOPENED, UNDER PARTITION

The search closed at 195. **Murat's directive reopens it** — with the
discipline that made ARENA-1's null credible, now arranged so iteration is
possible instead of forbidden:

```
EXPLORE data  →  LLM + engine iterate freely: backtest, diagnose, mutate,
                 combine, abandon. Every descendant recorded with genealogy
                 (hypothesis_id, parent_id, mechanism_family, generation).
FREEZE        →  definitions frozen, committed, hashed — before validation.
VALIDATE      →  frozen strategies only, once.
CONFIRM       →  untouched holdout. The existing holdout REMAINS UNREAD
                 tonight. Nothing earns a confirm pass in one night.
FORWARD       →  survivors seed shadow books, measured against the random
                 control that ranked 4th of 384.
```

Non-negotiables carried over intact:

- **Pre-register before compute; power-check before compute** — a test that
  cannot see its own prior does not run. `Aegis module/scripts/lint_prereg.py`
  runs before any trial registers; the corpse check is code, not a norm.
- **The false-discovery bar**: +4.87%/yr for best-of-384. A new pool size
  gets a newly computed bar; no best-of-N claim below its bar means anything.
  Bonferroni or better on anything selected.
- **A new mechanism carries the corpse it is not as a control arm.**
- **Turnover-sensitive claims route through G7** — and G7 cannot price
  impact, so every capacity number is a delay-only lower bound; say so.
- **Cost comparisons need a denominator that is not the winner's** (§16).
- **Rank-IC may describe ordering, may NOT corroborate a money result**
  (NIGHT-9). Money claims are settled in simple returns on the book.
- Benchmark: CRSP VW total return, buy-and-hold compounding. Remember
  scoring-pass-1: a monthly-rebalanced EW "benchmark" printed 18–26%/yr and
  voided the pass. The control-genome arm is what caught it — keep controls
  in every scored pool.

GPT proposed 300–800 hypotheses. Do not chase the count. The corpse linter
cut 6 arms to 2 last night before a number was computed; expect the same
ratio. **Target: as many ECONOMICALLY DISTINCT, pre-registered, powered
hypotheses as 8 hours honestly supports — and log every one that the linter
or power gate kills, because the kill list is a deliverable.**

**Failure decomposition is mandatory** for every dead strategy:
NO_INFORMATION / WRONG_DIRECTION / TOO_WEAK / TURNOVER_KILLED / COST_KILLED /
CAPACITY_KILLED / REGIME_SPECIFIC / CLOCK_SENSITIVE / OVERFIT / DATA_QUALITY /
DELIVERY_FAILURE / UNKNOWN. This feeds **informative corpse harvesting**: the
graveyard census holds 31 POWER and 29 IMPL deaths — strategies that may have
had information and bad delivery. The trailing stop is the type specimen: dead
as an execution rule (−3.08%/yr under G7), but its TRIGGER carries information
the vehicle cannot deliver (NIGHT-7). Re-delivery of a dead signal through a
new vehicle is a NEW pre-registered trial with the original corpse as control
— never a quiet resurrection.

---

## 5. PRIORITY EXPERIMENT — ANALYST REVISIONS: SOLVE THE DELIVERY

The most actionable finding in the program right now: target revisions earn
+1.5 to +6.1%/yr gross and die at their natural 10× turnover — and the two
revision constructions disagree in sign in small caps, so the object is not
yet identified. Dedicated campaign on the IBES panel already on disk
(`ibes.ptgsumu` et al., 9.6M rows, PIT):

1. First resolve the identification: why do the two constructions disagree?
   Until they agree or one is shown defective, "revisions work" is not a
   licensed sentence.
2. Then the delivery sweep — economically motivated variants only, each
   pre-registered as one family with arms, not threshold-mined: revision
   persistence / acceleration; consensus breadth; magnitude normalized by
   historical analyst error; alignment with earnings revisions; revision +
   price non-reaction; revision + profitability; monthly and quarterly
   implementation; minimum holding periods; delayed scheduled rebalance.
3. The questions to answer: does the information survive 1m/3m/6m holds?
   Where is the alpha half-life? Does delay preserve the signal? Can monthly
   delivery clear costs? All net numbers through G7, delay-only caveat
   attached.

---

## 6. HERESY LAB (approved tonight — research-only, forever)

ARENA-1's honest limit: the genome pool is generated FROM the registry, so
the search can confirm what the lab believes and can never overturn it. The
planted +8%/yr analyst effect was undetectable by design.

Build the heresy sleeve: a set of deliberately forbidden genomes (signals the
registry grades CLOSED/RISK_INPUT leading a book), run through the same Arena
machinery, **excluded from selection, reported separately, never eligible for
production or shadow seeding**. Controls included: raw analyst target level
should fail again — if a heresy unexpectedly clears its own false-discovery
bar under a materially different design, that is an INVESTIGATION, not a
promotion. Purpose: distinguish "mechanism absent" from "wrong
implementation / horizon / cost model / power."

---

## 7. PORTFOLIO FACTORY + CAPITAL FRONTIER

The system must build portfolios, not just rank stocks. Archetypes from the
same evidence with different explicit risk budgets: BALANCED, AGGRESSIVE,
MAX_GROWTH, HIGH_CONVICTION, DIVERSIFIED_ALPHA, LOW_TURNOVER, EVENT_DRIVEN.

Weighting ladder (make complexity earn its keep): equal weight → signal
strength → uncertainty-shrunk ER → inverse vol → risk contribution →
fractional/robust Kelly (shrunk μ, capped, never raw μ/σ² from noisy point
estimates) → drawdown-constrained optimization. Equal weight is the control
in every comparison — winner-copying already lost to it once (PF-2).

**Parameterize by capital.** Evaluate each finalist at $10k / $40k / $100k /
$1m / $10m / $50m / $250m: position sizes, ADV fraction, spread cost
(Corwin-Schultz per G7 — the range is not the spread), days to enter/exit,
viable universe count. A strategy excellent at $40k and unusable at $100m is
a finding, not a failure. Output: **RETURN FRONTIER BY CAPITAL** —
`docs/NIGHT10_CAPITAL_FRONTIER.md`. Impact numbers carry the G8/delay-only
caveat explicitly.

Evaluation always reports, prominently: terminal wealth, CAGR, excess CAGR,
max drawdown, probability of material loss, expected log growth — then
Sharpe/Sortino/Calmar/captures/turnover/cost/beta/factor alpha/regime
stability/clock sensitivity (date luck is worth 2.45 pt/yr — report the
range, never one start date). Rank by excess terminal wealth under a ruin
constraint, never Sharpe-max (Execution Standard, frozen).

Benchmarks must be operational: CRSP VW, large growth, small cap, relevant
style index, cash. No "beats hedge funds" without a licensed series — if none
exists, print that sentence.

---

## 8. MIRROR CHALLENGE (paper only)

Use MIRROR as one laboratory — it is at **−18.6% since inception**, which is
exactly why this matters. Two arms:

- **MIRROR_CURRENT_UNIVERSE**: resize/sell existing holdings only.
- **OPTIMUS_OPEN_UNIVERSE**: same capital, full investable US universe —
  "if Optimus were handed this money today, what would it own?"

Produce a PAPER proposal comparing Murat-conviction / current Mirror /
holdings-only Optimus / open-universe Optimus. **No trade, no lane touched,
no flag flipped.** Carry the known discrepancies visibly (QUBT 300 vs 200 —
run both or the conservative one, print the fork; cash unknown — state it),
never resolve them silently. The five names with no kill condition (ABSI,
AMSC, HUBS, KYTX, SLDP) get PROPOSED kill conditions, labeled as proposals
awaiting Murat.

---

## 9. THE MORNING OUTPUT — INVESTMENT COMMITTEE PAGE

The brief graduates from research status to a decision page. Machine- and
human-readable **TOP OPPORTUNITIES**: ranked top 20+ (top 50 preferred),
detailed top 10 — per name: rank, ticker, price, thesis, top signals ±,
catalysts with dates, kill condition, portfolio role, aggressive/balanced
weights, liquidity/capacity, why-it-beats-the-next-candidate, and the
calibrated-ER-or-explicit-ranking-score distinction from §2. Rejections with
reasons are part of the page ("rejected DDD despite +80% analyst upside:
stale level, deteriorating breadth, priced catalyst").

The end-state behavior this builds toward: *"I have $1m, maximize ROI"* →
ranked opportunities, a concrete allocation, ER distribution, drawdown
expectation, per-name theses and kill conditions, and a different book at
$100m because capacity binds. Tonight ships the first honest version of that
page — honest meaning: where the engine has only ordering evidence, the page
says so.

---

## 10. SYNTHETIC LAB (calibration harness, time permitting)

Expand only after §2–§7 are real. Worlds: NULL, MOMENTUM, REVERSAL, QUALITY,
ANALYST_REVISION, EVENT_UNDERREACTION, CRASH, STRUCTURAL_BREAK,
LOOKAHEAD_TRAP, SURVIVORSHIP_TRAP, plus adversarial (signal works in explore,
reverses in validation — the machinery should learn distrust). **First test
of every synthetic world: verify the plant actually landed** — last night's
generator cancelled its own plant and every known-answer test would have run
on a null world. Measure: true/false discovery rates, mechanism
identification, selection regret, OOS degradation. **Synthetic success is
never evidence of real-market alpha** (standing).

---

## 11. DO NOT

- Spend the night reconstructing the $45k account or asking for what's in
  the repo (it's there three times over).
- Read the locked holdout. At all.
- Mine thresholds until one passes; every family pre-registers its arms.
- Reactivate dead strategies without the corpse as control (linter enforces).
- Let the LLM assign weights, see post-freeze data, or grade its own tests.
- Count synthetic alpha as real, or a null as a verdict on search itself.
- Declare "nothing works" from one arena generation — ARENA-1 is
  Generation 1, and its null is the floor the next generation stands on.
- Call a strategy invalid because volatility is high; call it invalid
  because evidence is low.
- Trade anything. Paper/shadow only. No lane flag flips (attended-only).
- Confuse statistical confidence with portfolio risk — separate columns,
  both printed.

---

## 12. REQUIRED OUTPUTS

Docs: `OPTIMUS_OBJECTIVE.md`, `NIGHT10_ALPHA_FACTORY_REPORT.md`,
`NIGHT10_LLM_RESEARCH_REPORT.md`, `NIGHT10_ANALYST_REVISION_DELIVERY.md`,
`NIGHT10_MIRROR_CHALLENGE.md`, `NIGHT10_CAPITAL_FRONTIER.md`.

Machine-readable: hypothesis genealogy, portfolio results, top-opportunity
ranking, LLM call ledger, failure-decomposition ledger, linter/power-gate
kill list, new shadow definitions, freeze manifests + hashes.

Answer these first in the handoff, in order:

1. The 10 best opportunities Optimus sees now, and why each.
2. The portfolio it would build today at $40k / $1m / $50m.
3. What it would change in the MIRROR book (paper).
4. Which strategies showed real evidence; which had no information; which
   had information but failed on delivery.
5. Did the LLM generate any genuinely new testable mechanism?
6. Did anything survive VALIDATION (not explore)? Best ER estimate ±
   uncertainty?
7. Most aggressive credible portfolio; highest-confidence portfolio.
8. What Optimus wants to test next; what is preventing it from being
   materially better than it is today.

## 13. CLOSEOUT

Full fast suite (`python -m pytest backend/tests/ -v -m "not slow"`, ~3,225
tests) → `silent-fragility-audit` → claim/referee audit on any new verdicts →
verify manifests → preserve every negative result → commit both repos → push
→ verify clean → `python tools/refresh_aegis.py` → handoff doc + memory.

Murat still owes (carry forward, do not block on): cash figure, QUBT 300 vs
200, rulings on proposed kill conditions, `confirmed: true` on the book.
