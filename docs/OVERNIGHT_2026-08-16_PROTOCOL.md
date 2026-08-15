# Overnight protocol — declared BEFORE any number exists

Written and committed 2026-08-15, before running anything, for the same reason
`c3ae219` was: **an acceptance criterion chosen after seeing the numbers is not
an acceptance criterion.** Three times this week a first run produced results
that looked like the instrument working and were artefacts of its own
denominator (§41), its own objective (§45), its own n (§46). The protocol below
fixes what would count as a finding while nothing is known.

## What this night is and is not

**The paid IIF-1 night cannot run.** The window is 2026-08-16 19:30 UTC →
2026-08-17 12:20 UTC (11:25 at p90); this session ends long before it opens, and
neither 08-15 nor 08-16 is a session. **Zero paid LLM calls are authorised
tonight** — not a budget judgement, a supervision one: unattended spend against
a trial ceiling is exactly the thing the `SpendGovernor` exists to bound, and a
governor is not a substitute for someone being awake.

Everything below is **compute and free market data only**, and everything below
is **Gym output: hypotheses, never claims** (R2 wall 1). Nothing here certifies
anything, nothing here is citable, and no forward evidence is written.

---

## N8 — how big must the transfer corpus be?

**Question.** The six autopsied mechanisms carry affected-cell `n_effective`
between 0 and 12 against MDEs of 17-40pp. How many INDEPENDENT affected
episodes would be needed to resolve an effect of the size actually observed?

**Method.** For each mechanism and slice with a measured affected effect `d`
and dispersion `sd`, the episodes required at 80% power, two-sided 5%:

```
n_required = ((Z_alpha + Z_power) * sd / d)^2      Z sum = 2.8016
```

Reported per mechanism, then as a distribution. **Declared before running:** the
headline number is the MEDIAN across mechanisms, not the minimum. Taking the
minimum would pick the mechanism with the largest observed effect, which on this
sample size is a maximum over noisy draws — G1 one more time.

**Kill condition, declared now.** If the median `n_required` exceeds **200
independent affected episodes**, the honest conclusion is not "collect harder".
It is that **these mechanisms are not resolvable by episode collection at all**,
and the programme must change the question — to a cross-sectional one where the
sample is names rather than crises. That would be a finding about the research
design, and it would outrank every mechanism in the library.

---

## N2 — do candidate transfer slices actually SUPPLY affected episodes?

**Question, sharpened by N5.** Two of the five existing slices contain **zero**
VIX>=35 episodes, so a "five-slice corpus" is three. The atlas's binding
constraint is not history, rows or tickers — it is **slices in which the
precursor fires**. Which candidates supply them, and how many?

**Candidate slices, fixed now and not revisable after seeing the counts:**

| region | proxy | era |
|---|---|---|
| US | `^GSPC` | 1990-2026 (the incumbent) |
| Japan | `^N225` | 1990-2026 |
| Europe | `^STOXX50E` / `^GDAXI` | 1990-2026 |
| UK | `^FTSE` | 1990-2026 |
| Hong Kong / China | `^HSI` | 1990-2026 |
| EM | `EEM` | 2003-2026 |
| Korea | `^KS11` | 1997-2026 |
| Australia | `^AXJO` | 1992-2026 |

**The stress precursor outside the US, declared before measurement.** Non-US
indices have no VIX. Fitting a local threshold to make episodes appear is the
obvious way to manufacture a corpus, so the mapping is fixed in advance:

1. measure the unconditional frequency `f` with which the US series satisfies
   the incumbent precursor (VIX >= 35) over the common era;
2. for every other market, set its stress threshold at **the same percentile
   `f`** of its OWN trailing-20d annualised realised-volatility distribution.

The threshold is therefore never chosen to produce episodes; it is chosen to
produce the SAME RATE as the incumbent. A market that was calmer than the US
gets a lower absolute bar and the same frequency, which is the point — the
scarce resource is independent crises, not high numbers.

3. episodes counted with the existing 21-trading-day gap rule
   (`power.count_episodes`), the same rule the incumbent slices use.

**Acceptance, declared now.** A candidate slice QUALIFIES if it supplies at
least **`K` independent affected episodes**, where `K` is taken from N8's
median `n_required` divided across slices, and is written down before the
counts are read. A slice supplying zero is recorded as **supplying zero** and
does NOT count toward any slice tally — that is the whole lesson of N5.

**The check that stops this repeating §41.** Candidate slices must be
INDEPENDENT of the incumbent, not merely elsewhere. So each candidate reports
the **correlation of its stress-period returns with the US** over overlapping
dates, and the count is discounted by `1 / (1 + (m-1) * rho)` exactly as N1's
was. A slice whose crises are the US crises with a different ticker is one
observation, however many rows it has. **2008 will be in every market.**

---

## N4 — Precursor Coverage Index

**Question.** For every top-decile forward move, did ANY precursor in the
library fire beforehand? If coverage is near zero, the validity of individual
mechanisms barely matters and the roadmap is about coverage, not rigour. This
is the Micron test as a programme metric.

**Method.** Over the US corpus, at each decision date, evaluate every compiled
`affected_precursor` from the six autopsied mechanisms against the state.
Label the forward H-day return as top-decile / bottom-decile / neither, per
security, per horizon.

```
PCI = P(at least one precursor fired | move was top-decile)
```

**The number that makes it meaningful, declared now.** PCI alone is
uninterpretable: a precursor that fires 40% of the time "covers" 40% of moves
by chance. The reported metric is **coverage LIFT** — `PCI / P(any precursor
fires)` — with its own interval. Lift ~1.0 means the library has no coverage
whatever its PCI looks like.

**Kill condition.** If lift is indistinguishable from 1.0 at both tails, the
library's precursors do not mark exceptional moves, and no amount of per-
mechanism validation changes that.

---

## N6 / D4 — second moments vs first moments, then magnitude-gated direction

**Question (N6).** The regularity claim: second moments keep being detectable
and first moments keep not being. MARKET-GRAPH-1 was co-movement.
GRAPH-COVARIANCE-1 closed. IIF-1 chose magnitude over direction. NIGHT-3 found
no LLM selection edge. If that is real rather than a story told over four
results, the world model's vol / co-movement heads should be built first and
direction demoted — and a risk-model product may be the defensible one.

**Method.** One feature set, one model class, one set of walk-forward splits,
three targets at each horizon:

| target | moment | scored by |
|---|---|---|
| `sign(r_H)` | first | AUC-ROC |
| `abs(r_H)` | second | Spearman IC |
| `realised_vol_H` | second | Spearman IC |

Purged walk-forward with embargo, never random k-fold. Every score prints its
own MDE; below it is not detectable and never a kill (SS19).

**Declared verdict rule.** The regularity is SUPPORTED only if the second-moment
targets clear their MDEs **and** the first-moment target does not, in the same
splits on the same features. If both clear, the claim is wrong and direction is
predictable here too. If neither clears, the test was underpowered and says
nothing — which must be reported as saying nothing.

**D4.** Then: does a weak directional edge become economically useful when
deployed ONLY where the predicted move is large? Compare, on portfolio utility
rather than accuracy:

* unconditional directional policy
* magnitude-only policy (size by predicted magnitude, no direction)
* direction conditioned on predicted top-quintile magnitude

Scored with the P0.5 machinery — terminal wealth, max drawdown, ruin, and
`gamma*` — because "useful" is a statement about utility and the whole point of
P0.5 is that it must name which one.

**Declared null.** If the gated policy's utility edge does not clear the MDE of
its difference against the unconditional one (SS18 — the DIFFERENCE, with its
own SE), D4 is NOT_DETECTABLE and is reported as such.

---

## What will be reported in the morning

Per the order's experiment-accounting rule, and including the ones that hurt:

* dollars spent (expected: **$0.00**)
* serious distinct hypotheses attempted
* cheap kills
* unresolved / underpowered
* survivors
* findings that changed architecture
* **and explicitly: whether the night produced zero new investment candidates**,
  because a session whose only output is five new guardrails can be valuable
  and must still show that number.
