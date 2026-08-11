# NIGHT-10 — the capital frontier: the same evidence at $10k and at $250m

The product's mandate is not "manage $45k". Given any capital, what should be
owned — and what changes as the capital grows?

Receipts: `docs/BUILD1/capital_frontier.json`,
`backend/services/capital_frontier.py`.

---

## The frontier, on tonight's licensed names

Equal weight over the 20 highest-ranked names carrying licensed evidence.
Equal weight because it is the control in every comparison here (PF-2:
winner-copying lost to it; ARENA-1: a random book ranked 4th of 384) — and
because tonight the ranked archetypes **refused to build**, having only two
names with positive scores.

| capital | names tradeable | blocked | weight blocked | round-trip cost |
|---:|---:|---:|---:|---:|
| $10,000 | 20 | 0 | 0.0% | 0.400% |
| $40,000 | 20 | 0 | 0.0% | 0.400% |
| $100,000 | 20 | 0 | 0.0% | 0.400% |
| $1,000,000 | 20 | 0 | 0.0% | 0.400% |
| $10,000,000 | 20 | 0 | 0.0% | 0.400% |
| $50,000,000 | 20 | 0 | 0.0% | 0.400% |
| **$250,000,000** | **16** | **4** | **20.0%** | 0.400% |

**Capacity first binds between $50m and $250m**, where four names exceed the
5-day exit limit at 10% participation. Below $50m the book is unconstrained by
liquidity; the binding constraint at every level below that is **evidence**, not
capacity.

That is the honest headline of the whole exercise: *the engine runs out of
things it can justify long before it runs out of market to trade them in.*

---

## What these numbers are, and are not

**They are a DELAY-ONLY LOWER BOUND.** G7 prices the same 31.00 bps at ADV
multiples spanning six orders of magnitude — 1e6 down to 1 — which means this
programme's cost model is insensitive to size and **cannot price market impact
at all** (NIGHT-8, CANON §17).

So the table says how long you would be *in the market*, not what moving that
size would *cost* you. A real impact model makes every large-capital figure
worse, never better. The direction of the error is known; its magnitude is not.

**Spread** is estimated by Corwin-Schultz from the daily high-low range where a
range is available. The naive `(high−low)/2` is the intraday **range**, not the
spread, and understates costs by roughly an order of magnitude — the mistake
CANON §15 exists to prevent, and not repeated here. The 0.400% column above is
the fallback round-trip used where no spread could be estimated; it is
deliberately pessimistic, because an unknown spread is not a free one.

**Participation cap** 10% of median daily dollar volume. **Exit limit** 5 days.
Both are parameters, not laws; a patient book with a 20-day horizon would push
the binding point higher, and a 1-day liquidation requirement would pull it far
lower.

---

## The archetypes, and why most refused

`backend/services/portfolio_factory.py` builds seven archetypes from the same
evidence with different explicit risk budgets. Tonight, with two names carrying
a positive ranking score, **all seven refused**:

| archetype | refusal |
|---|---|
| OPTIMUS_BALANCED | 2 names cannot fill a book at a 10% cap — needs ≥10 |
| OPTIMUS_AGGRESSIVE | 2 names cannot fill a book at a 20% cap — needs ≥5 |
| OPTIMUS_HIGH_CONVICTION | 1 name clears MEDIUM confidence — needs ≥4 |
| OPTIMUS_DIVERSIFIED_ALPHA | 2 names at a 5% cap — needs ≥20 |
| OPTIMUS_LOW_TURNOVER | 2 names at a 10% cap — needs ≥10 |
| CONTROL_EQUAL_WEIGHT | 2 names at a 10% cap — needs ≥10 |
| OPTIMUS_MAX_GROWTH | **needs a CALIBRATED expected return, and none exists** |

**A refusal is a finding, not a failure.** The alternative — filling a 20-name
book from a 2-name evidence base — would produce a portfolio whose composition
was decided by the cap constraint rather than by anything measured.

The Kelly refusal is the one worth reading twice. A ranking score is an
**ordering**; Kelly needs a **magnitude**. Feeding the first to the second turns
a scoring artefact into a position size, which is how a display bug becomes
money. The factory refuses rather than substituting, and will keep refusing
until a calibrated picker→E[R] map exists.

---

## Weighting: what the ladder is for

The factory implements equal weight → signal strength → inverse volatility, with
risk parity and drawdown-constrained optimisation as the next rungs. Two rules
are enforced in code:

* **Equal weight is the control in every comparison.** A scheme that cannot beat
  EW on the same names is complexity with no payer.
* **An unknown volatility is not a low one.** Inverse-vol weighting falls back
  to the cross-sectional median for a missing reading, so the biggest weight
  can never land on the name we know least about. There is a test for it.

## What a $100m version of this product would need

1. **A market-impact model.** Not a refinement — the current one is provably
   size-blind, so every capacity claim above $50m is a lower bound of unknown
   looseness.
2. **More names carrying licensed evidence.** Capacity binds at 4 names out of
   20 at $250m; the fix is a wider licensed universe, not a cleverer optimiser.
3. **A calibrated expected return**, without which the entire aggressive half of
   the archetype ladder cannot be built at any capital level.
