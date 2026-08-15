# OPTIMUS — what this system is for

**Written 2026-08-11 (NIGHT-10) on Murat's ruling.**
**AMENDED 2026-08-15 on Murat's ruling — §0 below supersedes where it conflicts.
Everything from §1 down remains binding as constraint, not as mission.**

---

# §0 — THE MISSION (2026-08-15 amendment)

> **Build a self-improving investment intelligence system whose objective is
> maximising real-world portfolio utility — risk-adjusted or deliberately
> risk-seeking, by declared choice — using numerical models, LLM reasoning,
> internet-scale information, observed expert behaviour, simulation, and
> continual outcome feedback.**

**The methodology is the guardrail. It is not the mission.** Everything below
§1 — pre-registration, MDE, corpses, matched controls, the refusal to publish —
exists to stop a self-learning machine from learning nonsense. It does not exist
to conclude that nothing works.

## §0.1 Three deliverables from one system

1. **Murat's own capital** — genuinely useful for making money and managing a
   real portfolio, at an aggressive utility function of his choosing.
2. **A public open-source system** other people can run on their own portfolios,
   at their own utility function. His personality is not the product's default.
3. **A research paper** through HKU, *if* the work produces a novel and
   defensible result. Not a reason to overclaim; a reason to aim high.

## §0.2 The central reframe — investing is a sequential learning problem

Stop treating "find alpha" as a bag of independent hypothesis tests. The
question is no longer only *"does signal X predict returns?"* It is:

> Given everything known at time *t*, what action should I take, what was the
> alternative, what happened afterwards, **why** did it happen, and what should
> the system change because of that observation?

**The Micron test.** If MU runs +100%, recording `MU = +100%` is worthless.
Reconstruct the episode: what demand chain was shifting, what memory pricing
showed, what hyperscaler capex implied, what analysts were revising, what
comparables moved first, how insiders behaved, what options implied, which
narratives existed — then ask the only question that matters:

> **Could the system have recognised enough of that state BEFORE the move to
> justify owning more?**

Explaining a winner afterwards is trivial. **Finding precursors observable
beforehand is the research problem.** `Autopsy.executable_precursor` +
foreign-slice transfer is the mechanised form of exactly this, and it is why
that pipeline matters more than any single mechanism it produces.

## §0.3 Competing explanations, scored longitudinally

Do not ask only *"why did the book lose $1,000?"* Emit a hypothesis set —
biotech factor drawdown · rates repricing · geopolitical risk · concentrated
high-beta exposure · company-specific catalyst · random residual — where the
**engine quantifies exposures**, the **LLM investigates context**, and Aegis
assigns probabilities. Then grade those explanations when the outcome resolves.

What accumulates is the asset: **a longitudinal database of the system's own
reasoning errors.** That is worth incomparably more than a store of prompts.

## §0.4 Learning is plural — there is no LLM-vs-NN choice to make

```
World → Perception → Hypotheses → Numerical verification → Decision
      → Portfolio → Outcome → Attribution → Learning → Memory → next decision
```

Seven distinct learners, each with its own job:

| learner | learns by |
|---|---|
| LLM | retrieved episodic memory — *"I have seen something like this"* |
| statistical models | parameter updates |
| policy model | which actions work in which states |
| calibration layer | whether LLM confidence means anything |
| mechanism graph | which causal explanations survived |
| portfolio optimiser | the utility consequences of decisions |
| Research Gym | aggressive search for entirely new patterns |

The foundation model's weights are **not** retrained. The learning system is
built *around* a stable LLM.

## §0.5 Teacher — Researcher — Trader — Critic

- **Researcher** observes episodes and generates hypotheses.
- **Teacher** is reality plus observed decisions: insiders, executives,
  politicians, disclosed institutional portfolios, indices, great historical
  investors, **failed traders**, Aegis itself, synthetic portfolios.
- **Trader** must act on information available at the time.
- **Critic** decomposes the result into: selection · timing · sizing · portfolio
  interaction · thesis · catalyst · regime · execution/cost · calibration ·
  unavoidable randomness.

That decomposition is the training data.

## §0.6 Study losers as aggressively as winners — contrastive by construction

Looking only at Buffett, winning funds, and +500% stocks builds a beautiful
selection-biased fiction. The informative dataset is **winner vs matched
loser**:

- Why did company A explode while economically similar company B did not?
- Why did fund A survive while fund B with similar exposures collapsed?
- Why did two investors hold the same stock and earn different returns?
- Why did one concentrated portfolio succeed where 20,599 similar ones failed?

Much of the discriminating information is **semantic, not tabular** —
management language, technological inflections, supplier and regulatory
relationships, capital allocation, second-order effects. That is the LLM's real
job. The engine then decides whether the apparent semantic insight carries
measurable information. **That relationship is worth far more than asking a
model "which stock goes up".**

## §0.7 The Observed Decision Library

Not "copy politicians". Every observed decision records: actor · asset · action
· size · portfolio context · information available · **public disclosure time** ·
market state · company state · subsequent return · subsequent risk ·
counterfactual alternatives · actor's historical skill · similar prior decisions.

Then the questions become answerable: does this actor have skill at *selection*,
*timing*, *holding through volatility*, *sizing*, *industry specialisation*,
*buying after drawdowns*, *selling before deterioration*? **Does the apparent
skill survive disclosure delay?** Is it just beta? Would copying the portfolio
work, or is the entry price essential? **Is an actor's unusual behaviour more
informative than their ordinary trades?** — Actor Surprise is one piece of this.

## §0.8 Compute posture — maximise information per dollar

Murat is willing to spend. The objective is **not** "minimise API calls"; it is
**information gained per dollar**. A $30 experiment that eliminates six
architectures is cheap. Ten thousand slightly-different prompts asking the same
weak question is expensive at any price.

Design experiments as information acquisition, and score them:

> **EV(experiment) = P(changes the roadmap) × value of the decision improved
> − experiment cost**

## §0.9 The objective is terminal wealth, not classification accuracy

System A is directionally right 60% of the time and earns tiny gains. System B
is right 52%, catches the rare 50–300% opportunities, sizes them, avoids
catastrophic loss, and stays invested through noise. **We want B.**

So evaluation moves toward **portfolio utility**: expected geometric growth,
CAGR under drawdown constraints, Sortino, expected shortfall, probability of
ruin — or explicitly aggressive forms such as *maximise expected log wealth
subject to a maximum tolerable catastrophic-loss probability*.

**One brain, several utility functions** → operating personalities: capital
preservation · balanced · aggressive · extreme growth. Murat's own book may run
aggressive without the public system inheriting one universal risk profile.

## §0.10 The paper

Not *"can an LLM predict stocks?"* — saturated and uninteresting. The candidate:

> **Does structured post-outcome reflection improve prospective portfolio
> decisions when reflections are converted into falsifiable mechanisms rather
> than natural-language memories?**

Most reflective agents tell the model what happened and ask it to remember a
lesson. Aegis does the harder thing: outcome → explanation → measurable
precursors → did the precursors exist beforehand → matched controls → foreign
transfer → structured memory → retrieval at the next decision → reality grades
whether using it helped. That is **machine scientific discovery inside a
sequential financial decision environment**, not LLM trading.

## §0.11 What this changes about the discipline

Nothing is relaxed. The search space is about to get much larger, which makes
the guardrails matter more, not less. But their purpose is stated correctly
from here on:

> The discipline does not exist to say *"sorry, nothing works."*
> It exists to stop the self-learning machine from learning bullshit.

**Aegis does not contain one investment strategy. Aegis is a machine for
creating, testing, combining, remembering and continuously improving investment
strategies.**

---

# §1 — The NIGHT-10 objective (still binding as constraint)

## The objective

> Given ANY amount of capital — $10k, $40k, $1m, $50m — Optimus searches the
> investable US market, identifies the highest expected-return opportunities it
> can **justify**, constructs portfolios, manages them, and tries to outperform
> the market and professional investors — with the ruin number always printed
> beside the dream number.

The objective is **not** "manage Murat's twelve holdings". His MIRROR book is
one live laboratory for the objective. It is not the objective.

## The division of labour

```
Aegis Research      discovers exploitable information, and kills most of it
        │
        ▼
Signal Registry     records what is licensed, for which role, in which universe
        │
        ▼
The deterministic PM converts licensed evidence into positions and sizes them
        │
        ▼
The Portfolio Arena searches implementations, against a false-discovery bar
        │
        ▼
Forward books       generate the only evidence that was never fitted
        │
        ▼
The LLM             expands the hypothesis space and attacks the conclusions
```

**The LLM narrates and hypothesises. The engine computes and allocates.** That
line does not move. It is not a stylistic preference: NIGHT-3 graded 16,320 LLM
stock-selection decisions and found no edge (M1 t 0.04, M2 t 0.93), and the
same prompt at temperature 0.7 flipped 21.6% of its own answers.

## What "justify" means, operationally

A name may enter a BUY ranking only through a signal the registry grades as a
PICKER, inside the universe that signal was measured in. Everything else —
closed mechanisms, risk inputs, filters — is computed, printed, and structurally
prevented from ordering the list. This is enforced by
`recommendation.assert_registry_discipline`, which **refuses to publish a
ranking** rather than printing a warning next to a compromised one.

The cost of that honesty is visible and is meant to be: on 2026-08-11 the engine
screened 5,324 US names, carried 40 to the candidate stage, and could justify
exactly **one BUY**.

## The two dimensions that must never merge

**Risk and evidence are different axes.** A credible 35%-volatility strategy is
not inferior to a 12%-volatility one; a leaky 35% one is worthless. Optimus may
never hide a high-return portfolio because volatility is high — only because the
evidence is bad. Both columns print, always, separately.

## What Optimus refuses to say

* **An expected return it cannot calibrate.** The permitted pickers are graded
  SUPPORTED, not VALIDATED, and no map from picker composite to a 12-month
  return exists. So the page prints an ordering and a percentile and says
  `NOT_CALIBRATED`. A number that looks like an expected return and is not one
  is worse than no number, because something will multiply it.
* **A capacity figure that includes market impact.** G7 prices the same 31.00
  bps at ADV multiples from 1e6 to 1, so this programme cannot price impact at
  all. Every capacity number is a **delay-only lower bound** and says so.
* **"Beats hedge funds"**, without a licensed hedge-fund return series. There
  isn't one, so the claim is not available.
* **A kill condition Murat has not ruled on**, as though it were adopted. Those
  print as `PROPOSED_AWAITING_MURAT` on every line.

## The standing constraints this inherits

* Pre-register before compute; power-check before compute. A test that cannot
  see its own prior does not run.
* The corpse check is code (`scripts/lint_prereg.py`), not a norm — and since
  NIGHT-10, `lint_batch` also checks a batch against *itself*, because ten
  proposals generated in one sitting each passed history while being one idea.
* A new mechanism carries the corpse it is not, as a control arm.
* Turnover-sensitive claims route through G7; cost comparisons need a
  denominator that is not the winner's.
* Rank-IC may describe ordering; it may not corroborate a money result.
* Equal weight is the control in every portfolio comparison.
* Synthetic performance is never evidence of alpha.
* No skill claims before 24 months of forward record.

## The end state this is building toward

> *"I have $1m. Maximize ROI."*
>
> — ranked opportunities, a concrete allocation, the expected-return
> distribution where one exists and an explicit refusal where it does not, the
> drawdown expectation, per-name theses and kill conditions, the reason each
> name beats the next candidate, and **a different book at $100m because
> capacity binds.**

`scripts/investment_committee.py` ships the first honest version of that page.
Honest meaning: where the engine has only ordering evidence, the page says so;
where it has nothing, it says that too.
