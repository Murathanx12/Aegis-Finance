# BUILDER REPORT — against the review of Order 5's report

```
written_at:     2026-08-16
target_session: 2026-08-17
spend:          $0.00 (no paid API calls)
tests:          aegis-finance 4390 passed / 0 failed  ·  Aegis module 719 / 0
pushed:         NO — a push redeploys; that is Murat's call
```

The review asked for seven things in order and corrected three overclaims.
Everything below is what the measurements said, including where they said I was
wrong.

---

## 1. The headline: the direct policy test ran, and its own diagnostic killed it

N21. Frozen N9 rules (598, `sha256 8093cf73`), vote at a train-calibrated
threshold, **eight securities no trial in the register had ever read**
(`XRT XHB KRE XOP ITB SMH IBB IGV`), 2006–2026, slice claimed `CONFIRM` before
a price was fetched.

**Registered primary — `POLICY_REDUCES_DRAWDOWN`:**

| | value |
|---|---|
| observed | **−6.843pp** per 6-month block |
| registered placebo | median −3.211, 5th pct −6.579 |
| p | **0.0312** |
| material floor | 3.0pp — cleared |

**And it is a false positive.** The registered placebo de-risks the *same
number of days* in windows placed **uniformly at random**. Real fires cluster
in volatile periods, and clustering alone lowers drawdown with no predictive
skill at all. The correct null is a **circular block shift of the actual fire
mask** — count, run lengths and clustering preserved exactly, only the
alignment between state and outcome destroyed:

```
shifted null:  median −5.272   5th pct −11.890   observed −6.843   p = 0.3381
```

Randomly shifting the fires in time produces drawdown reductions **larger** than
the real ones. The clustering does the work; the timing contributes nothing
detectable.

Both are recorded. The registered verdict stands as what the committed rule
produced and **must not be cited**; the diagnostic says which is right. §37 —
a new instrument's first positive is the one that looks like it working, and
this one looked exactly like it.

> **A matched-EXPOSURE placebo is not a matched-CLUSTERING placebo.** Standing
> requirement for any de-risking null from here.

The cost side, registered unpowered in advance and unable to produce a verdict,
points the same way: **−83.31pp pooled log growth, 1 of 8 securities improved.**

**Five independent routes now agree** — N4's coverage null, N9's transfer lift
below break-even, N20's estimand moving the wrong way, N21's direct
measurement, and the cost side. The precursor library does not carry deployable
tail-timing information.

---

## 2. The arithmetic that says terminal wealth could never have answered it

Found at N21's power stage, **before** the test, and it is the more important
half. The effective cross-section is measured as a design effect
`k / (1 + (k−1)ρ̄)` on a policy-free surrogate, not assumed:

| outcome | ρ̄ | effective cross-section | n_eff | 80%-power MDE |
|---|---|---|---|---|
| **terminal log growth** | 0.488 | **1.81** of 8 | 74 | **3.23pp/block = 6.45pp/yr** |
| max drawdown | 0.691 | 1.37 of 8 | 56 | 1.85pp/block |
| worst day | 0.753 | 1.27 of 8 | 52 | 0.63pp/block |
| downside semideviation | 0.797 | 1.22 of 8 | 50 | 0.10pp/block |

> Resolving this programme's own **+3%/yr** execution standard on terminal log
> growth needs **172 years**. The slice holds 20.

And widening the cross-section cannot rescue it: the effective count is bounded
by `1/ρ̄ ≈ 2` however many equity ETFs are added. **Any objective containing a
terminal-return term is unresolvable on 20 years of equity data at the standard
we set ourselves.** Only pure-risk outcomes are resolvable — and by a wide
margin, because dispersion falls far faster than correlation rises.

This is N8 one level up: it is not that crises are rare, it is that **an equity
path is one observation**.

**The strategic consequence, which is new:** a policy's *risk reduction* can be
demonstrated long before its *utility improvement* can. The utility claim then
has to come from the risk reduction plus a **declared preference**, not from
measurement. That is a defensible position and it is the first time the
arithmetic has been able to state it. It also reframes G6: sizing rules can be
validated on risk; their utility benefit is a matter of the declared λ.

---

## 3. Your three corrections, applied

### "Refuted" → the exclusion test N20 owed

You were right that a `NOT_DETECTABLE` verdict cannot support "the lever is
closed". Registered the exclusion test first (`71fb670`), then ran it:

| block | cost | required | LCB₉₅(Δ) | verdict |
|---|---|---|---|---|
| 10 | 0.0010 | −0.642 | −0.329 | RULED_OUT |
| 20 | 0.0010 | −0.642 | −0.465 | RULED_OUT |
| 40 | 0.0010 | −0.642 | −0.590 | RULED_OUT |
| **40** | **0.0000** | −0.527 | −0.590 | **NOT_EXCLUDED** |

Excluded at **every block length at the declared cost**. The single failing
cell assumes trading is free — and cost is a parameter of the very action being
priced. Weakest-cell reporting is inherited, so the **verdict is
`RESCUE_NOT_EXCLUDED`** and I am not promoting the declared-cost result to the
headline after seeing which cell failed.

Structural note worth keeping: **the grid's adversarial direction flips between
the two tests.** On the `L_min` axis the weakest cell is the highest cost; on
the exclusion axis it is the lowest. A grid whose hard end moves with the
question can be used to pick, so the failing cell is named in the output.

**And the mechanism I asserted is refuted by its own diagnostic.** I wrote that
precursors fire in high-vol states which rebound hardest. Stratifying by rv20
tercile, Δ **reverses sign**:

```
rv20 tercile 0 (calm)      −0.414pp     <- the rescue direction
rv20 tercile 1 (mid)       −0.707pp     <- the rescue direction
rv20 tercile 2 (stressed)  +2.922pp     <- and it dominates the pool
```

The pooled +0.198pp is the average of a sign reversal, not a property. That
sentence was a guess and is withdrawn. It does **not** license reading a
state-conditional `L_min` off this table — `|μ_tail|` and the lift both differ
by stratum — and picking the two favourable terciles after seeing them is
selection. It is a hypothesis for a fresh registered trial.

### "Powered negative" → withdrawn, and what replaces it is stronger

You were right that 92,988 rows are not 92,988 experiments. The bootstrap was
blocking over 40 consecutive **rows** in a date-sorted, ~18-wide panel — which
spans **2.2 days**, not 40.

| | before | after |
|---|---|---|
| n_effective | 2,325 | **129** (5,166 dates × ~18) |
| MDE (WM0) | 2.48% | **6.56%** of baseline loss |
| MDE (WM0B) | 3.06% | **9.57%** |

Both observed effects (6.15% / 8.48%) are now **below their own MDE**. The
intervals still exclude zero, so "worse" stands — "powered negative" does not,
and is withdrawn.

What replaces it is the equivalence test against the prereg's own 2% economic
floor: a worthwhile improvement is a difference of −0.02310; LCB₉₅ is **+0.03316
(WM0) / +0.04173 (WM0B)** ⇒ **`MEANINGFUL_IMPROVEMENT_EXCLUDED`, both arms.**
"No worthwhile improvement was available from this architecture on this data"
is the claim that closes something, and it is established.

**Climatology is clean** — `climatology_quantiles(y[tr], …)` and
`scaled_empirical(y[tr], rv[tr], rv[te], …)` are train-only inside each fold,
with a 40-day embargo. Now pinned by a test that poisons every non-training row
by +500 and asserts the output is byte-identical, rather than by reading the
code.

### The 2×2 — and it refutes my estimator hypothesis too

|  | mean pinball | tail | vs empirical shape |
|---|---|---|---|
| empirical shape / estimated scale | 1.15492 | 0.83021 | — |
| learned shape / estimated scale | 1.25282 | 0.92248 | −8.48% |
| empirical shape / **oracle** scale | 1.13164 | **0.65255** | — |
| learned shape / **oracle** scale | 1.27349 | 0.79040 | **−12.53%** |

Handed a perfect scale, learned shape gets **worse**, not better.
`NO_INCREMENTAL_SHAPE_INFORMATION`. The estimator-bottleneck hypothesis is not
supported, and neither is "conditional shape exists but was masked".

> Session 1: "it cannot extrapolate volatility" — refuted by WM0B.
> Session 2: "the estimator shrinks the tails" — refuted by the oracle.
> I keep producing mechanism stories that survive exactly until measured.

**The one positive, and it is the useful part:** perfect *scale* buys a **21.4%
tail-pinball improvement** (0.83021 → 0.65255) with shape held fixed and
empirical. That bounds the headroom in the volatility-forecasting rung — the
rung N11 called commoditised **by ranking**. Ranking cannot climb it. It is an
upper bound from an unattainable oracle and evidence for nothing deployable,
but it says where the next head should look. **No WM0C.**

---

## 4. R13c, and the audit you asked to see as a list

You were right that non-overlap is necessary, not sufficient. `effective_sample`
now applies each reduction separately and returns the whole chain — `n_raw →
temporal_nonoverlap_n → cross-sectional → cluster → effective` — because
hardcoding `n_eff = n_nonoverlap` would have built §41 into R13 a second time.

New declarations: `dependence_unit` (one sentence naming what ONE independent
observation is), `cross_sectional_n`, `cluster_size`. Placeholders — `n/a`,
`TBD`, `-`, `?` — do not parse as declarations.

**Undeclared dependence blocks only below 20× headroom.** Rationale, not taste:
the widest cross-section this programme has pooled is 18 and clusters run 2–5,
so an undeclared dependence can cost about an order of magnitude. More headroom
cannot be flipped by one; less can, and that is how N20 got through.

**The sweep** (`scripts/audit_r13_passes.py`) — 121 documents, 7 ever scored by
R13, 114 predate it:

| class | count | which |
|---|---|---|
| **CHANGED_VERDICT** | **3** | N20 (2.0× headroom), WM0 (1.3×), WM0B (1.3×) — all now `UNDECLARED_DEPENDENCE_UNIT` |
| IMMATERIAL | 4 | N4B 293×, N12 385×, N9 3658×, N9B 3658× |

**So it is three, and all three are mine from the last two days.** "Every prior
pass is suspect" was too broad and would have manufactured a retrospective
crisis out of arithmetic that never mattered — N9's 3658× headroom cannot be
flipped by any plausible dependence correction. Your wording was the right one.

And WM0's registration-time refusal **agrees** with what the corrected bootstrap
measured independently. The cheap number and the expensive number land in the
same place again.

---

## 5. OptionMetrics: you were right to make me check, and I was wrong

The month-end sampling is a **`WHERE` clause we wrote**. From our own
`fetch_wrds_optionm.py:128`:

```sql
from optionm.vsurfd{yr}
where days in (30, 91) and delta in (25, 50, -25, -50)
  and date in (select max(date) from optionm.vsurfd{yr}
               group by date_trunc('month', date))
```

`optionm.vsurfd<year>` is the **daily** standardised surface. The month-end
restriction, the two maturities and the four deltas are all our filters. Read
entitlement to the daily table is **proven**, not assumed: 23/23 years pulled,
zero errors.

**Twice now I have written a property of our extraction as a property of the
data** — first "~87 rows means not daily", then "month-end means the rung is
monthly". The second would have sent the next session to build a monthly ladder
that cannot be compared like-for-like against N11's daily rungs. The correct
plan is the **daily IV rung on the same decision dates and folds** as the
realised-vol ladder; scoped to a trial universe rather than ~6,000 secids, the
re-pull is cheap. `test_optionm_provenance.py` asserts this against the pull
script, so the next person to change the extraction rechecks the registry.

---

## 6. The ex-post boundary

Taken. `ExPostScale` stops a slip; it cannot argue with intent. Hindsight now
lives in `research_gym.evaluation_only`, and `test_ex_post_boundary.py` fails if
anything under `backend/routers` or `backend/services` imports it. The allowlist
is named files, and a third test fails if an entry points at a deleted file.
`ExPostArray` added for per-row hindsight — the more dangerous case, since
`preds * oracle` broadcasts silently — refusing both `__array__` and `__iter__`.
The oracle scale in §3 was born inside that boundary.

---

## 7. Two corrections found while building, neither asked for

- **N9's selection has a 20-day embargo leak.** It slices to `TRAIN_END` *after*
  computing `fwd_20`, so late-2015 training rows carry forward returns built
  from 2016 prices. N21's freeze cannot commit it (it never downloads past the
  cutoff), hence 598 rules against N9's 582 — and reproducing N9's download
  window returns **exactly 582**, which is how the cause was established rather
  than guessed. 0.5% of rows; N9's headline was on six other securities over
  2016–2026. Recorded because "small and probably immaterial" is how a leak
  survives.
- **LightGBM was not reproducible.** `random_state` alone does not fix it —
  multithreaded histogram construction sums floats out of order. Re-running WM0
  unchanged moved the pooled loss 1.22617 → 1.22598. Too small to move a
  verdict, too large for a registry that records exact numbers as evidence.
  Fixed with `deterministic=True, force_row_wise=True`.

---

## 8. What I did not do

- **Not pushed.** 20 commits in aegis-finance, 2 in `Aegis module`.
- **N11's level losses** (QLIKE / MZ / tail error / sizing utility) — not
  added. §3's oracle result raises their value: the headroom is in scale.
- **The daily OptionMetrics pull** — established as available, not executed. It
  needs WRDS credentials and a declared trial universe.
- **G4 / the winner–matched-loser factory** — untouched.
- **The register still is not mandatory at registration.** N21 calls it; nothing
  forces a trial to.

---

## 9. Recommended order

1. **The daily IV rung** on N11's own dates and folds, with level losses. Two
   review items collapse into one trial, and §3 says scale is where the
   headroom is.
2. **G5's next head on a risk outcome** — drawdown or co-movement change, cheap
   baseline first, one NN attempt, one registered improvement attempt. §2 says a
   risk outcome is resolvable on data we have and a return outcome is not.
3. **The winner–matched-loser factory and G4.** §1's five-route convergence is
   the strongest argument yet that the constraint is the information, not the
   model.
4. **Make the slice claim mandatory in the prereg linter.**
