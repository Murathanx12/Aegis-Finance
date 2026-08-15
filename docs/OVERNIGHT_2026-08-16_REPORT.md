# Overnight report — 2026-08-15 into 08-16

Against the protocol committed at `f091809` **before any number existed**.
Reported in the accounting the order asked for, including the entries that hurt.

---

## The accounting

| | |
|---|---|
| **dollars spent** | **$0.00** — zero paid LLM calls, as declared |
| serious distinct hypotheses attempted | **5** (N8, N2, N4, N6, D4) |
| cheap kills | **2** (D4; the reactive-corpus hope) |
| unresolved / underpowered | **1** (N8's headline, which could not be identified) |
| survivors | **1** (N6, with a large caveat) |
| findings that changed architecture | **3** (N6's ordering, N2's build order, the atlas grammar) |
| defects found | **2**, one of them armed to fire in six hours |
| **new investment candidates** | **ZERO** |

That last line is the one the order insisted be visible. Tonight produced no
new tradeable signal. What it produced is a specification for what would count
as one, and the removal of two things that would have stopped the programme
shipping.

---

## The one economically meaningful positive

**N6: the second-moment regularity is real.** One feature set, one model class,
one set of embargoed walk-forward folds, twelve securities, 82,954 rows, three
targets differing only in which moment they ask about:

| horizon | sign (AUC) | abs return (IC) | realised vol (IC) |
|---|---|---|---|
| 5d | 0.4967 *(MDE 0.025)* | **0.294** | **0.531** |
| 20d | 0.5092 *(MDE 0.034)* | **0.244** | **0.622** |
| 60d | 0.5014 *(MDE 0.051)* | **0.169** | **0.567** |

SUPPORTED at every horizon by the rule declared before the run, and it survives
shrinking `n_effective` from six folds to three. The four earlier results that
pointed this way were not four coincidences.

**And the check on it is the more useful half.** Volatility is persistent, so a
model handed `rv20` can score a large IC by copying it. Measured against the
free predictor — trailing 20-day realised vol, alone, no model, paired by fold:

> **model minus baseline: −0.085 to +0.025. Not detectable anywhere.**

A gradient-boosted model with fourteen features on 83,000 rows does not beat one
trailing volatility number at any horizon for either target, and at sixty days
it is materially worse.

**So the architectural consequence sharpens rather than softens.** Build the
volatility head — it works and costs nothing, and it feeds sizing, ruin
constraints and the `gamma*` machinery immediately. Do not expect ML to add to
it. And *"we forecast volatility better"* is **not** the defensible product: if
risk is where the signal is, the product has to be built on what a single
trailing number cannot express — **co-movement structure, conditional tails,
regime transitions, drawdown shape.**

---

## The corpus question, now answered with numbers

**N8** asked how many independent episodes would resolve the library's
mechanisms. The declared kill fired — median 305 against a threshold of 200 —
and then §37 was applied to the kill and changed the answer: `n_required` scales
as `1/d²` and `d` is measured on `n_effective ≈ 2`, so the requirement spans
**0.9 to 1,534 episodes**. The corpus cannot determine how much corpus it needs.

The reframe is what makes it actionable. Dispersion IS well estimated, so
corpus size becomes a **decision**:

| minimum effect worth acting on | episodes needed (crisis) | (calm) |
|---|---|---|
| 3pp | 273 | 2 |
| 5pp | 98 | 1 |
| **10pp** | **25** | — |

**The scarcity is dispersion, not history**, and it is concentrated entirely in
the states every mechanism is about. Crisis dispersion is ~12× calm, `n` goes as
`sd²`, so the same edge costs **144× more episodes** exactly where we keep
asking.

**N2** then measured the supply. Twelve markets, thirty-six years, threshold
fixed as a *frequency* before any count was read: 152 raw episodes — and

* by correlation on stress days (ρ̄ = 0.466): twelve slices are worth **1.96**,
  supplying **24.8 independent episodes, 1.31× the US alone**;
* by timing: **80 of 152** episodes begin more than 42 days from any US crisis.

The two disagree by 3×, and the answer survives it: **a 10pp minimum effect is
reachable on both measures; 5pp is reachable on neither.** That is the first
specification TRANSFER_ATLAS_V1 has ever had.

**Build order changes: Asia first, Europe last.** India 75% novel crises, Korea
60%, Hong Kong 59%, Japan 53% — against France 25% and Germany/UK/Switzerland
36%. Europe's crises are the US's crises.

---

## Two defects, one of them armed

**A CI time bomb pointed at the deploy gate.** `test_the_live_ledger_canary_is_healthy`
asserted `status == "ok"` against the real ledger. The campaign's first
forecasts fall due 2026-08-16:

```
2026-08-15   ok        0 overdue     <- CI was green here, 17:14 UTC
2026-08-16   DEGRADED  110 overdue
2026-08-17   DEGRADED  201 overdue
```

CI runs in UTC and would have turned red at midnight, **on no commit, from no
code change**. Railway gates deploys on CI. Worse than this morning's two:
those could be fixed by editing code, while this clears only when a human runs
an attended irreversible resolution — so the pipeline would have frozen until
someone woke up, with every unrelated fix stuck behind another person's chores.

Fourth instance this week of **one** defect: a test asserting the state of the
world rather than the behaviour of the code. The CI world, the calendar's, the
clock's, and now the operational backlog's.

**And the atlas was unreachable in principle.** Every precursor is written over
`vix`; exactly one market has one. `stress_pctile` (expanding-window, so a rank
never sees its own future) is now in the vocabulary. Faithfulness was checked
*before* reach and is only moderate — recall 72.5%, precision 48.4%, Jaccard
40.9% — so it is a **related state selector, not a synonym**, and every result
computed through it carries that. Episodes evaluable outside the US: **0 → 101**.

---

## Ready for you, not done

**The campaign resolution.** `scripts/campaign_resolution_readiness.py` runs the
resolver against a byte-identical **copy** and verifies the real ledger's
SHA-256 before and after, so the decision could be prepared without touching
anything. As of 2026-08-16:

> **110 due · 110 would resolve · 0 unpriceable · health returns to `ok`**
> priced from a fresh fetch · real ledger SHA-256 unchanged

The irreversible step stays yours:
`python -m scripts.resolve_campaign_ledger --commit`

**The paid night.** Window opens **2026-08-16 19:30 UTC**, latest safe start
**08-17 12:20 UTC** (11:25 at p90). Neither 08-15 nor 08-16 is a session.

**The LIVE_FORWARD quarantine.** Untouched — irreversible and outward-facing.

---

## SHAs

| | |
|---|---|
| `f091809` | the protocol, declared before any number |
| `fe5a966` | **N8** — the corpus cannot size itself; the design curve |
| `0a0781b` | **N2** — twelve markets are worth 1.3× the US |
| `a6ff2ff` | **N4** — 85% of exceptional moves had no warning |
| `59d953b` | **N6** supported, its predictability free; **D4** killed |
| `b2f429b` | the atlas grammar unblocked; the CI time bomb defused |

**4,314 fast tests green locally, 4,303 in the CI-simulated world.**

---

## What I would do next, and why

The night's three biggest results point the same way and it is not the way the
roadmap currently points.

N4 says **85% of exceptional moves have no precursor at all**. N8 says the
mechanisms we do have need **273 crisis episodes** to resolve at a 3pp bar. N2
says the entire world supplies **25 to 80**. Those three numbers together say
that validating crisis-conditioned mechanisms harder cannot work — not because
the discipline is wrong, but because the sample does not exist and never will.

N6 says where the sample *does* exist: second moments, measurable at IC 0.5-0.6,
on every security and every day rather than on a dozen crises. **The
cross-sectional, second-moment question has thousands of independent
observations. The crisis-conditioned, first-moment question has twenty-five.**

I would put the next phase there — and I would treat "what does a risk model
know that a trailing volatility number does not" as the specific opening
question, because tonight's check says that is exactly where the free answer
stops.
