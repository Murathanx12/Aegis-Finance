# FINDING — 2026-08-24: the analyst graph replicates. Every extension we hoped for does not.

**Trial** `ANALYST-COCOVERAGE-GRAPH-1` · **licence** PRODUCT_EXPERIMENT (SCREEN)
**spec_hash** `0e1578bd0410653b` — frozen before the first number existed
**amendment-1** `f06c80b8a53c055f` · **amendment-2** `f0d458966f4a14eb` — both POST-HOC
**Receipt** `backend/data/optimus/graph/cocoverage_receipt.json`
**n_effective = 131 MONTHS** (CANON §58 — date blocks, never the 556,669 firm-months)

---

## 0. Why this ran first

`ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md` forbids a GNN until simple graph
propagation beats a non-graph baseline. This is that test. It cost one groupby
over data already on disk, and it was designed to be **allowed to fail** — the
declared rule said the graph programme STOPS if nothing cleared the bar.

The AEGIS-specific bet was that weighting an analyst edge by that analyst's
**measured reliability** would beat raw co-coverage. Reliability is the one
thing this project has that no published version of this has, because
`FINDING_2026-08-23_ANALYST_RELIABILITY.md` measured it.

That bet lost, cleanly, and knowing so cost a day instead of a quarter.

---

## 1. The result

| arm | IC | t | p | MDE₈₀ | bar | BH | |
|---|---|---|---|---|---|---|---|
| `own_ret_1m` *(control)* | +0.0072 | 0.77 | 0.44 | 0.026 | ✗ | ✗ | own momentum |
| **`peer_eq`** | **+0.0228** | **2.35** | **0.020** | 0.027 | ✓ | ✓ | equal-weighted peers |
| `peer_shared` | +0.0226 | 2.31 | 0.023 | 0.027 | ✓ | ✓ | shared-analyst-count weighted |
| `peer_leader` | +0.0186 | 2.12 | 0.036 | 0.025 | ✓ | ✓ | better-covered peers only |
| `peer_laggard` | +0.0160 | 1.92 | 0.057 | 0.023 | ✓ | ✓ | less-covered peers only |
| `peer_rel` | +0.0047 | 0.34 | 0.73 | 0.038 | ✗ | ✗ | **starved — see §3** |
| `peer_rel_tilt` ᴾ | +0.0227 | 2.32 | 0.022 | 0.027 | ✓ | ✓ | reliability as a tilt |
| `peer_eq_near_high` ᴾ | −0.0006 | −0.05 | 0.96 | 0.031 | ✗ | ✗ | 52-week-high slice |
| `sic2_peer` ᴾ | +0.0138 | 1.59 | 0.11 | 0.024 | ✓ | ✗ | industry, **no graph** |
| `peer_eq_xsic` ᴾ | +0.0159 | 2.05 | 0.042 | 0.022 | ✓ | ✓ | **cross-industry links only** |

ᴾ = post-hoc (amendments 1–2), in their own BH-FDR family so they cannot move
the primary arms' thresholds after the fact.

**Primary verdict: CONTINUE** — four arms cleared the declared 0.01 bar and
survived BH-FDR at q ≤ 0.10.

---

## 2. What survived, including its two obvious confounds

The paired comparisons matter more than the levels, because every arm shares the
same good and bad months and that is most of the variance.

| comparison | paired diff | SE | t |
|---|---|---|---|
| `peer_eq` − `own_ret_1m` | **+0.0156** | 0.0060 | **+2.58** |
| `peer_eq` − `sic2_peer` | **+0.0090** | 0.0039 | **+2.30** |

**It is not own momentum**, and **it is not industry momentum.** The second was
the likelier mundane explanation — analysts cover firms in the same sector, so
"connected by shared analysts" is largely "in the same industry" — and it does
not hold: the graph beats a plain SIC2 peer-return baseline by 0.0090 paired,
and the graph computed over **only cross-industry links** still clears the bar
on its own (+0.0159, p = 0.042).

So there is real cross-firm information in shared analyst coverage, in this
window, beyond sector.

---

## 3. What failed — and one of them was nearly a false negative

### 3.1 Reliability weighting adds nothing (and the first test of it was invalid)

`peer_rel` returned +0.0047 (p = 0.73). The obvious reading is "reliability
carries nothing". **That reading would have been wrong**, and the diagnosis is
the reason this section exists:

| year | analysts covering | with a measured weight | **share of coverage weighted** |
|---|---|---|---|
| 2014 | 2,583 | 5 | **0.1%** |
| 2019 | 2,183 | 426 | 19.2% |
| 2024 | 2,077 | 674 | 28.0% |

`max(0, edge)` deleted two populations at once — every analyst without 30 prior
graded claims, and every analyst whose measured edge was negative. The arm's
graph was nearly empty. **It was starved, not refuted**, and reporting it as a
result would have been correct arithmetic against the wrong world.

Amendment-1 re-posed it properly: reliability as a **tilt** around an intact
graph (`w = clip(1 + 2·edge, 0.25, 4)`, unknown analysts keep w = 1). Now it is
a real test, and the answer is unambiguous:

> `peer_rel_tilt` − `peer_eq` = **−0.00008, SE 0.00052, t = −0.16** over 131
> paired months.

That is not an uncertain zero. It is a **precisely measured** zero. Knowing an
analyst is reliable does not improve which firms their coverage links together.

**This is the session's most useful negative.** The reliability layer remains
valid for grading *claims* (§FINDING 2026-08-23); it simply carries no extra
information about *relationships*. Those are different questions and only one of
them is answered.

### 3.2 Direction does not replicate as an asymmetry

The leader→laggard conduit story predicts better-covered firms lead. Measured:

> `peer_leader` − `peer_laggard` = **+0.0026, SE 0.0037, t = 0.69**

Both directions work, about equally. The asymmetry is not detectable here.

### 3.3 The 52-week-high interaction adds nothing

−0.0006 (t = −0.05) on the arm that works. *(The primary run attached this slice
to `peer_rel` — the starved arm — which measured nothing about 52-week highs.
That was a mis-specification, corrected in amendment-2, and it is recorded
rather than quietly re-run.)*

---

## 4. The honest caveat: this is under-powered by its own design

Every passing arm's IC sits **below its own 80%-power MDE**:

```
peer_eq        IC 0.0228   MDE₈₀ 0.0271
peer_eq_xsic   IC 0.0159   MDE₈₀ 0.0217
```

131 months detects an effect this size at roughly 60–70% power, not 80%. The
result is p < 0.05 and it is *not* the effect size the design was built to
resolve. CANON §64 — a power check before any confirmation — says this licenses
building, not believing. Longer history would tighten it; 2013 is where IBES
coverage and the CRSP schema both become usable here.

---

## 5. What this licenses, and what it does not

**Licensed:** a `GRAPH_PROPAGATION_v1` selector as its own PRODUCT_EXPERIMENT
book, using plain equal-weighted co-coverage peer returns. Nothing more
elaborate has earned its place.

**And it can be computed at a granularity production could supply** —
AMENDMENT-3 (`estimid`, the brokerage firm, rather than `amaskcd`, the
individual analyst). 8,336 analysts vs 589 firms, median coverage 4 names vs
14, so a firm graph is far denser and survival was a real question. It survives
and is *better measured*: `peer_eq` +0.0218 at **t 3.05** against +0.0228 at
t 2.35, with the control still flat.

**The remaining executability gap, named:** `estimid` is *standing coverage*;
the live yfinance feed gives upgrade/downgrade **actions**, a subset. A bank
covering a name quietly all year is in IBES and not in an actions feed.
Granularity is not the blocker — that is what this tested. Whether an actions
feed reconstructs the coverage graph is untested, and it is the thing to check
before building.

**Not licensed:**

* **the GNN.** The roadmap gated it on simple graph features paying. They pay —
  but the three refinements that a GNN would exploit (reliability-weighted
  edges, edge direction, state conditioning) each measured **zero**. A model
  whose advantage is learning richer edge structure has just been told the
  richer edge structure is not there. The gate is not met in spirit.
* **any claim of alpha.** This is an IC screen: no costs, no capacity, no
  turnover limit, no portfolio. An IC of 0.023 monthly with high turnover is not
  obviously tradable, and this run says nothing about whether it survives costs.

---

## 6. Method notes

* **PIT.** Coverage at month *t* uses recommendations issued strictly before
  *t*; reliability applied in year *Y* is estimated only on claims announced
  before *Y* (expanding window); the signal is the peer return realised in *t*
  and the target is the firm's own return in *t+1*.
* **Graph.** `A` = analysts × firms incidence; `C = AᵀA` gives shared-analyst
  counts; `B = C > 0` the unweighted graph; `C_rel = A_wᵀA`. Verified against a
  four-firm hand-worked example before the first real run.
* **Sample.** 200,357 linked US recommendations, 556,669 firm-months,
  2014–2024, ~4,000 firms per month.
* **The forward month is exactly t+1.** `shift(-1)` takes the next month a name
  APPEARS in, so a halted or relisted firm would carry a return three months
  later labelled as next month's. Measured at 109 of 549,775 rows (0.02%) and
  nulled rather than tolerated — a target that is silently the wrong month is
  not a thing to be approximately right about. Re-running with it pinned moved
  every number in the fifth decimal and changed no conclusion.
* **Refusals.** CRSP files before 2013 carry no split factor, and the run
  REFUSES those years rather than defaulting `cfacpr` — an unadjusted price
  makes every split look like a crash against the 52-week high.
