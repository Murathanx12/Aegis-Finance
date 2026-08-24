# FINDING — 2026-08-24: the co-coverage graph's density was measuring the NULL

**Measurement** `GRAPH-BACKBONE-1` (declared before its numbers, commit `1ec2128`) ·
`GRAPH-BACKBONE-2` (round 2, declared before its numbers)
**Receipt** `backend/data/optimus/graph_propagation/backbone_receipt.json`
**Coverage snapshot** `backend/data/optimus/graph_propagation/coverage_snapshot_2026-08-21.json`
**Script** `scripts/graph_backbone_measure.py` — the declaration and the code are the same file

## Verdict

**Still NOT BUILDABLE on this universe — for a different and much better reason.**
`GRAPH-PROPAGATION-DENSITY-1`'s verdict survives. Its *reason* does not.

---

## 1. The objection

The density finding rests on

```
complete graph  =>  peer_eq_i = (S - r_i)/(n - 1)  =>  corr(peer_eq, own) = -1
```

which is correct algebra with a missing antecedent. That identity needs the
weights to be **uniform** as well as the graph to be complete, and it then holds
at *any* n and *any* density. What forces the correlation to -1 is not that the
graph is large — it is that **every name's neighbourhood is identical**, so the
only thing distinguishing `peer_i` across names is the subtraction of `r_i`.

The sweep that produced the verdict varied `min_shared`, which changes **which
edges exist**. It never varied **what an edge is worth**. Those are different
objects, and only the second one is in the antecedent.

## 2. The number that reframes it

| | |
|---|---|
| names with coverage | 176 |
| firm pool | **94** |
| median covering firms per name | 17 |
| median EXPECTED overlap under a degree-preserving null | **3.43 shared brokers** |
| observed binary edge density at `min_shared=1` | 100.0% |
| **expected binary edge density under that null** | **95.8%** |

**100% density is 95.8% predicted by chance.** With 176 names each drawing ~17
firms from a pool of 94, "these two names share at least one broker" is a
birthday-paradox certainty. The licensed `min_shared = 1` admits pairs whose
overlap is *below* what random coverage predicts — and the sweep's correlation
begins to move at `min_shared` 3-4, which is exactly where it crosses 3.43.

So the density figure was a fact about the threshold, not about the data.

**And that says why the parameter did not travel.** "At least one shared broker"
means something different where the median name has 4 covering firms than where
it has 17. "More shared brokers than the null predicts" means the same thing in
both, and is not a parameter at all. Expressing the edge rule against the null
*removes* a degree of freedom rather than adding one.

## 3. Weighting rescues the degeneracy the sweep could not

Six arms, all declared before the numbers existed. 200 random return draws.

| arm | density | corr(score, own ret) | universe ranked |
|---|---|---|---|
| A0 `peer_eq` *(licensed control)* | 1.0000 | **-1.0000** | 100% |
| A1 `peer_idf` inverse-breadth weights | 1.0000 | -0.4416 | 100% |
| A2 `peer_svn` hypergeometric backbone, FDR 0.01 | 0.8890 | **-0.1976** | 100% |
| A3 `peer_svn_idf` | 0.8890 | -0.2001 | 100% |
| A4 `peer_sig` weights = -log10 p | 1.0000 | **-0.2336** | 100% |
| A5 `peer_jaccard` | 1.0000 | -0.3696 | 100% |

A2 and A4 clear the `assert_graph_informative` bar of 0.25 — **borrowed, not
invented here, precisely so it could not be tuned** — at **100% of the universe
still rankable**. No point in the `min_shared` sweep managed that: `min_shared=10`
reached -0.058 but ranked 52% of pairs and dropped names entirely.

Nothing was thresholded to taste. The SVN's cut is a false-discovery rate fixed
in advance, which is the objection the density finding correctly raised against
sparsifying — and it is a fair objection to `min_shared` and not to this.

## 4. And then the graph fails anyway, on the question that matters

Reaching a non-degenerate correlation is necessary, not sufficient. A weighted
graph can dodge the reversal identity while still having neighbourhoods that
discriminate nothing. The test: effective peer count `n_eff = (sum w)^2 / sum w^2`,
against **the same construction on graphs that preserve both degree sequences**
— 10 draws.

| arm | n_eff observed | null mean ± sd | z | ratio |
|---|---|---|---|---|
| A0 | 175.00 | 175.00 ± 0.00 | — | 1.000 |
| A1 | 162.72 | 162.65 ± 0.26 | +0.3 | 1.000 |
| A2 | 162.00 | 165.15 ± 1.11 | -2.8 | 0.981 |
| A3 | 152.29 | 154.59 ± 0.71 | -3.2 | 0.985 |
| **A4** | **151.77** | **156.35 ± 0.43** | **-10.6** | **0.971** |
| A5 | 165.78 | 167.68 ± 0.27 | -7.0 | 0.989 |

**The structure is real and it is negligible.** A4 rejects the null at z = -10.6
— this is not a failure to detect — and lands 97% of the way from a
discriminating graph back to a random one: 151.8 effective peers out of 175
possible, against a null of 156.4.

That is an **equivalence** result, which is what the standing canon asks a null
to owe. The declared bar was ratio <= 0.80; the observed 0.97 is nowhere near
it, so the verdict does not hinge on where that bar was put.

## 5. Two corrections to this measurement's own instrument

* **Round 1's gate 2 was mis-specified.** `n_eff` equals the degree when every
  weight is 1, so for the binary arms it re-asked the density question under
  another name and could not test what it was written to test. Found by running
  it. Round 2 measures against the null instead — the question the SVN already
  asks about *edges*, asked about *weights*.
* **One null draw is not a comparison.** Round 2 first reported "162.00 vs
  164.00" with no dispersion, which is the house failure mode (*quote the cost
  rate or don't quote the count*). The ensemble is what turns that into
  z = -10.6 and makes "real but negligible" sayable at all.

## 6. What ships

`graph_propagation.graph_beats_null()` — the precondition, and the point is that
it **transports**. Density and own-return correlation are proxies whose meaning
depends on the universe's coverage depth; "does this graph concentrate more than
its own degree-preserving null" does not. Any candidate universe can be run
through it for the cost of one coverage pull, **before** anything is spent on it.

Its live verdict is `NEGLIGIBLE_VS_NULL` — deliberately not
"indistinguishable", because at z = -8.9 it is emphatically distinguishable.
A label that contradicts its own number is the same error as reading 17 covering
firms as a rich graph.

## 7. What this changes for the successor

The review's `GRAPH_PROPAGATION_MIDCAP_v2` is unchanged in direction and now has
a **gate it must pass first, and a cheap one**. A mid/small-cap universe is a
hypothesis about *selectivity*, and selectivity is exactly what
`graph_beats_null` measures. Run it on the candidate universe before pulling a
single price.

And the edge rule that goes with it is no longer `min_shared = k` for a k chosen
somewhere. It is "overlap above the degree-preserving null at a declared FDR" —
the same mechanism the screen validated, expressed so that it means the same
thing on a universe it has not seen.

## 8. The successor was run the same day, and it closes the mechanism

**`GRAPH-MIDCAP-SCREEN-1`** · receipt `midcap_screen_receipt.json` · declared in
`scripts/graph_midcap_screen.py` before its numbers existed.

§7 said the successor needed a universe whose coverage is *selective*, and that
`graph_beats_null()` could screen one for the cost of one coverage pull. That
run happened.

**Universe:** a liquidity BAND of the arena's own scan source — same parquet,
same eligibility rule — at dollar-volume rank 700–1600, 300 names sampled at a
fixed seed. 254 usable (30 EMPTY, 16 STALE — the panel is as of 2024-11-29 and
delisted names drop out).

**The selectivity hypothesis is confirmed as a description of the data:**

| | mega-cap (rank 0–180) | mid-cap band (rank 700–1600) |
|---|---|---|
| median dollar volume | $15.8bn | **$0.5–1.1bn** |
| median covering firms per name | 17 | **6** |
| firm pool | 94 | 79 |
| n_eff observed | 151.8 | 112.4 |
| n_eff null mean ± sd | 156.4 ± 0.4 | 121.6 ± 0.9 |
| z | −10.6 | −10.0 |
| **ratio to null** | **0.972** | **0.924** |
| verdict | NEGLIGIBLE_VS_NULL | **NEGLIGIBLE_VS_NULL** |

Coverage really is three times thinner down there, and the graph really does
concentrate more relative to its own null than the mega-cap graph did. **The
hypothesis pointed the right way and it does not get remotely far enough.**
0.924 against a bar of 0.80, with the ratio moving 0.048 for a roughly threefold
drop in coverage breadth.

**So the verdict is the stronger one: the mechanism is closed on live-tradeable
US equities generally, not on mega-caps specifically.** That retires the
successor the external review kept open, and it retires it on a measurement
rather than on an argument.

*Extrapolating that 0.048-per-threefold rate is not a result and is not offered
as one* — but it does say the daylight is large, and that any universe thin
enough to close it would be one where liquidity and borrow costs decide the
outcome long before the graph does.

**What survives**: `graph_beats_null()` itself. It screened a candidate universe
end-to-end for one coverage pull and no price data, and returned a verdict that
would otherwise have cost a full trial to reach. That is the transportable
part, and it is the part §6 said it was.

## 9. The lesson, which is the density finding's own lesson pointed one level up

That finding closed with *"measuring an input's abundance is not measuring its
information."* Correct — and it then used **abundance of edges** as its evidence
of failure. 100% density read as "no graph" for the same reason 17 covering
firms read as "rich graph": a count reported without the question it answers.

**The question a graph statistic must answer is "compared to what?"** Here the
answer was 95.8%, and it was available the whole time.
