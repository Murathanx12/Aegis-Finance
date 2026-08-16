# ERRATUM — N21: two corrections, one to the inference and one to the arithmetic

**Filed 2026-08-16.** Neither changes the pre-registration, which stands as
written and as committed before the run. Both change what may be said about it.

---

## 1. The primary inference is invalidated by null misspecification

**Registered:** `POLICY_REDUCES_DRAWDOWN`, −6.843pp per 6-month block,
p = 0.0312 against a matched-exposure placebo, clearing the registered 3.0pp
material floor.

**Diagnostic run after it:** a circular block shift of the *actual* fire mask —
count, run lengths, autocorrelation and turnover preserved, only the alignment
between state and outcome destroyed — gives **p = 0.3381**, with a median
drawdown reduction *larger* than the observed one.

The registered placebo held the de-risked **day count** fixed and scattered the
windows uniformly. Real precursor fires cluster in volatile periods, and being
out of the market during a burst lowers drawdown with no predictive skill
whatever. So the registered null destroyed clustering along with alignment and
attributed the whole difference to alignment.

**Status recorded, and it is two fields rather than one:**

```
verdict          = POLICY_REDUCES_DRAWDOWN            (what the committed rule produced)
inference_status = PRIMARY_INFERENCE_INVALIDATED_BY_NULL_MISSPECIFICATION
```

The verdict is not rewritten. The rule ran as registered and that is a fact
about the trial; the instrument it ran on does not support the reading, and
that is a different fact. Overwriting the first to record the second destroys
the evidence that pre-registration exists to create.

**The block-shift null is a diagnostic, not a confirmatory negative.** It was
designed after seeing the false positive. It is decisive about the registered
null's inadequacy and is not itself a registered test.

### What was built so this cannot recur

`backend/services/research_gym/null_invariance.py`. A null declares which
properties of the real treatment it preserves — frequency, turnover, run
lengths, clustering, seasonality, cross-sectional synchronisation — and the
module **measures them and refuses to compute a p-value** from an ensemble that
violates its own declaration. `declared_invariants_for(outcome)` derives the
requirement from the outcome's shape rather than from taste: a path-dependent
outcome (drawdown, terminal growth, time under water) is moved by the
*arrangement* of exposure and so forces `clustering` and `run_lengths`; a mean
forward return is a sum and is not.

The check runs on the masks alone, costs nothing, and **could have run at
registration.** N21's registered placebo now fails it; the block shift passes
it. `test_null_invariance.py` asserts both, because a contract that passes the
design it was written because of has not been shown to do anything.

### What the contract found when it was actually run

Worse than clustering, and the placebo's name was part of the problem. Measured
on the re-run (`n21_policy_utility_contract.json`, worst security XRT, δ = 0):

| invariant | real mask | placebo mean | |
|---|---|---|---|
| frequency (share de-risked) | 0.3822 | 0.3178 | **FAIL** (17% low) |
| run length, mean (bars) | 77.4 | 24.7 | **FAIL** (3.1× short) |
| run length, max (bars) | 310 | 60.8 | **FAIL** (5.1× short) |
| turnover | 0.0099 | 0.0257 | **FAIL** (2.6× high) |
| clustering, lag 1 | 0.979 | 0.941 | ok |
| clustering, lag 5 | 0.902 | 0.713 | **FAIL** |
| clustering, lag 10 | 0.811 | 0.451 | **FAIL** |
| clustering, lag 20 | 0.647 | −0.004 | **FAIL** |

Three things follow.

1. **The matched-exposure placebo did not match exposure.** Placing `n_off / H`
   windows of length `H` uniformly produces fewer treated days than `n_off`,
   because the windows overlap. The one property it was named for is the one it
   was closest on and it still missed by 17%.
2. **The bias has a direction, and it is now measured rather than argued.** The
   placebo is de-risked *less* than the real policy (31.8% vs 38.2%), and less
   exposure-off means less mechanical drawdown reduction — so the comparison
   flattered the real policy on the exposure axis as well as the clustering
   axis.
3. **A shallow check would have cleared it.** The placebo is indistinguishable
   from the real mask **at lag 1** (0.979 vs 0.941) and diverges only at lags 5,
   10 and 20. Matching the window length buys the short-lag autocorrelation for
   free, so "it has runs too" is exactly the reassurance a reader would have
   accepted.

The circular block shift passes every one of these checks on every security.

## 2. The "172 years" figure is wrong; the honest number is ~95

The power stage measured the effective cross-section as a design effect on a
policy-free surrogate:

```
rho_bar = 0.488  ->  k / (1 + (k-1) rho) = 1.81 effective securities of 8
n_effective       = 40 blocks x 1.81 = 72   (the trial's own number, correct)
80%-power MDE     = 3.23pp/block = 6.45pp/yr of log growth
```

It then converted the required observation count to years by dividing by the
**block rate alone**:

```python
need  = ((z_a + z_p) * sd_block / 1.5) ** 2      # ~343 effective observations
years = need * BLOCK_MONTHS / 12.0               # = 172   <-- WRONG
```

`need` is a count of *effective* observations, and this slice supplies
`2 blocks/yr × 1.81 = 3.62` of them per year, not 2. The correct conversion is
`need / 3.62 ≈ **95 years**`. The error uses the effective cross-section once
as a multiplier when computing `n_effective` and then forgets it when
converting back — the same quantity counted and then dropped.

**The direction matters.** 172 is 95 × 1.81: the mistake inflated the headline
by exactly the factor being celebrated, and it ran the way that made the
finding louder.

**What survives:** 95 years against 20 held is still unreachable, so *this
design* cannot resolve a +3%/yr difference in terminal log growth, and max
drawdown on the same slice and blocks remains resolvable by a wide margin.

**What does not survive:** the generalisation *"any objective containing a
terminal-return term is unresolvable on 20 years of equity data"*. It was
stated from one design's dispersion and one cross-section's correlation, and
neither is a property of equity data. The bound `1/ρ̄ ≈ 2` applies to a
cross-section of things that move together; differencing the common factor away
changes ρ̄ by an order of magnitude, and `design_effect_n(100, 0.10) = 9.2`
against `design_effect_n(100, 0.488) = 2.03`. **Market-level directional claims
live at the high-ρ̄ end and are close to unresolvable on this corpus;
cross-sectional and relative claims do not, and the arithmetic says so.**

**And the utility conclusion is withdrawn.** "Risk reduction is demonstrable
long before utility, so the utility claim comes from a declared λ" does not
follow. Under `U = E[R] − λ·Risk`, λ prices a trade-off between two measured
quantities; it does not supply the one that could not be measured. A large
enough λ would otherwise make anything safer automatically better, which is the
cash degeneracy G3 already found. What a declared λ *can* do is convert the
measured risk reduction into a **break-even return sacrifice** — the largest
`E[R]` give-up at which the policy is still preferred — and then the question
is whether the return interval excludes it. That is the same shape as `L_min`
and it is an honest use of a preference parameter.

## 3. What changed in code

| | |
|---|---|
| `research_gym/null_invariance.py` | new — the contract, the generators, the refusal |
| `scripts/n21_policy_utility.py` | verifies both nulls; records `inference_status`; power-stage arithmetic corrected with the wrong figure printed beside the right one |
| `aegis_brain/discipline/prereg_power.py` | R13d — `design_effect_n`, `cross_sectional_k` / `cross_sectional_rho`, and a refusal for declaring `k` without a measured `rho` |
| artifacts | original `n21_policy_utility.json` untouched; re-run written to `n21_policy_utility_contract.json` |
