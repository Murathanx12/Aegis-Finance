# FINDING — 2026-08-24: the licensed graph signal is short-term reversal on this universe

**Measurement** `GRAPH-PROPAGATION-DENSITY-1`
**Receipt** `backend/data/optimus/graph_propagation/density_receipt.json`
**Module** `backend/services/graph_propagation.py`

## Verdict: **NOT BUILDABLE ON THIS UNIVERSE.** The vendor can supply the data; the data cannot supply a graph.

---

## 1. The number

Measured on the live 179-name universe at 2026-08-21, at the `min_shared = 1`
the screen validated:

| | |
|---|---|
| names with coverage | 176 |
| edge density | **100.0%** |
| names that are peers of *everything* | **176 of 176** |
| corr(`peer_eq`, own return) | **−1.0000** |
| sd of that corr over 200 random return draws | **0.0000** |

Not approximately. Exactly. In a complete graph

```
peer_eq_i = (S − r_i) / (n − 1)
```

which is a strictly decreasing linear function of the name's own return. The
ranking is the exact reverse of own return — **short-horizon reversal**, and
short-horizon winner-chasing is a Holm-surviving **ANTI-signal** in this
programme. Shipping it would not have been a weak selector. It would have been
a harmful one, dressed as the session's only licensed mechanism.

## 2. Why the graph is complete

Every major brokerage covers every mega-cap. Goldman covers all 176. So does
Morgan Stanley. Co-coverage is *universal*, and a relation that holds between
all pairs cannot distinguish any pair.

The screen never met this. It ran on thousands of CRSP names where a **median
analyst covers 4 firms** — coverage was selective, so an edge carried
information. `AMENDMENT-3` established that firm-level attribution survives, and
that was the right question to ask, but it was asked *on that same large
universe*, where a firm-level graph is still sparse **relative to its size**.

A 179-name mega-cap universe is the one setting where the mechanism cannot work.
Nothing in the screen was wrong; it was applied to a population it never saw.

## 3. Sparsifying does not rescue it

| min_shared | density | corr with own return | names ranked |
|---|---|---|---|
| **1** *(licensed)* | 100.0% | **−1.0000** | 176 |
| 2 | 100.0% | −1.0000 | 176 |
| 3 | 99.8% | −0.8800 | 176 |
| 4 | 99.1% | −0.6527 | 176 |
| 5 | 97.2% | −0.3835 | 176 |
| 6 | 93.6% | −0.2949 | 175 |
| 8 | 77.0% | −0.1176 | 175 |
| 10 | 52.1% | −0.0581 | 170 |
| 12 | 28.8% | −0.0538 | 157 |
| 15 | 9.7% | −0.0702 | 96 |
| 20 | 2.1% | −0.0457 | 39 |

The correlation only becomes small around 8–12 shared brokerages, and by then
11–45% of the universe is unrankable.

But the decisive objection is not the cost — it is that **"an edge requires 10
shared brokerages" is not the mechanism the screen validated**. `peer_shared`,
which weights edges by shared-coverer count, was an arm in that screen and it
did **not** beat `peer_eq`. There is no evidence for the sparsified variant, and
picking the threshold that makes the correlation go away is choosing a parameter
because it produces the answer we want. That is the thing the whole methodology
exists to prevent.

## 4. What was done

`assert_graph_informative` refuses above 60% edge density or |corr with own
return| > 0.25. The module's health surface leads with
`BLOCKED_UNIVERSE_TOO_DENSE`, not with the sequencing wait — because the
sequencing wait resolves itself on Monday and this does not.

A defect surfaced while measuring: `peer_scores` divided by zero for an isolated
name when `min_peers=0`, since `0 < 0` is False and the guard fell through.
Found by measuring, not by a test; now has one.

## 5. What would make it work

A universe whose coverage is **selective** — mid and small caps, where a name is
followed by a handful of brokers rather than by all of them. That is where
co-coverage says something, and it is what the screen's own graph looked like.

That is a **universe change, not a parameter change**, and it needs its own
declaration: a different candidate set, different liquidity and cost
assumptions, and a re-run of the vendor-depth measurement on names where
yfinance's coverage is much thinner than it is for mega-caps.

## 6. The lesson

The vendor-depth measurement earlier the same night returned **VIABLE** — 98.3%
of names carry a usable graph row, median 17 covering firms, denser than the
IBES graph the screen validated on.

Every one of those numbers is correct, and together they pointed the wrong way.
**Density was reported as evidence of health.** 17 covering firms per name reads
as a rich graph; it is in fact the symptom that destroys the signal, because
what a co-coverage graph needs is not many edges but *discriminating* ones.

The integration run that caught it was not testing for this. It printed
`corr(peer_eq, own_ret)` as a sanity line with the comment "a value near 1.0
would mean the graph is a mirror" — guarding against the wrong sign. The value
came back −1.000, and the guard was only useful because the number was printed
at all.

**Measuring an input's abundance is not measuring its information.** That is the
same failure as the earlier `n_effective 168` and `corr = 0.516` cases: a
quantity that sounds like evidence, reported without the question it answers.
