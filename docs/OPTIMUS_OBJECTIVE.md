# OPTIMUS — what this system is for

**Written 2026-08-11 (NIGHT-10) on Murat's ruling. Binding until he changes it.**

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
