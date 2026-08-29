# Report against the continue order — the leak was not the defect

**2026-08-16.** aegis-finance `32c07a7`→`118a55d` (4 commits), `Aegis module`
`9c04820`, `e15da55`. **Not pushed.** $0.00 in API spend. Tests **4,425 pass /
0 fail** (aegis-finance, fast) and **all pass** (`Aegis module`).

---

## §1 — P0. N9's lineage: repaired, and it was not carrying the result

The order made the 20-day embargo leak priority zero and froze N9B/N20/N21
behind it. Both halves of that were done, and the answer to the first is
undramatic.

**The guard.** `research_gym.lineage` makes four timestamps explicit —
`feature_cutoff_ts`, `label_start_ts`, `label_end_ts`, `split_cutoff_ts` — and
**derives `label_end_ts` from the index** rather than accepting a declared one.
`verify_declared` exists for callers that build labels elsewhere and refuses on
disagreement instead of believing them. Purge is **per horizon**; there is no
API that produces one embargo for a multi-horizon frame, and a mutation control
pins that a 20-bar purge still leaves 40 rows of a 60-bar label leaking.

One design correction worth naming: `split_cutoff` and `eval_start` are two
timestamps. The first version of the audit checked labels against the bar after
the cutoff, which scores an embargoed design as if the embargo bought nothing —
it reported three false leaks before I noticed.

**The audit, as a list.** `scripts/audit_temporal_lineage.py`, measured against
the real 1999–2026 NYSE grid:

| design | verdict | |
|---|---|---|
| `n9_mine_the_85` | **LEAKS** | 80 training dates, to 2016-02-01 / 2016-03-30 |
| `n21_policy_utility --freeze` | CLEAN | download truncated at the cutoff; 20 dates starve rather than leak |
| `n11_vol_baseline_ladder` | CLEAN | on its own six boundaries |
| `n6_moments` | CLEAN | on its own six boundaries |
| `wm0_train` | CLEAN | all 21 annual folds |
| n4 · n4b · n20 · wm0_inference · gym_dissect_timing | NO_SPLIT | nothing to leak across — stated, not omitted |

**One leak, and it is the one already known.** But the audit found a second
thing neither embargo rule states: **20 trading bars span 29.0 calendar days
and up to 35.** So n11's and n6's `1.5·H` *calendar*-day embargo against a
*trading-bar* label is too short on **15.7%** of possible boundaries at H=20
and 18.0% at H=5. It holds on their actual folds by luck. WM0's `2·H` is never
short. Counting bars removes the dependence on the holiday schedule entirely.

**The repair changed almost nothing:**

| | pre-repair | repaired |
|---|---|---|
| admissible train rows, H=20 / H=60 | 12,828 / 12,828 | 12,768 / 12,648 |
| **confirmation lift, H=20** | **1.271, p = 0.015** | **1.279, p = 0.015** |
| confirmation lift, H=60 | 1.330, p = 0.075 | 1.326, p = 0.065 |

That is worth stating as plainly as a leak that mattered would be. A defect
found is not automatically a defect that carried the result.

## §2 — What did carry it, and this is the session's finding

N9's amendment 1 confirmed the frozen rules on six securities in neither prior
slice — `DIA XLV XLI XLP XLU XLB` — over **1999–2026**. Different tickers, the
**same calendar**. Rules selected on SPY/XLF/XLE through 2015, scored on other
index ETFs through the same 2008, the same 2011, the same 2015.

Split at the selection boundary. Same securities, same rules, same placebo:

| confirmation slice | H=20 | H=60 |
|---|---|---|
| **1999–2015 — calendar-OVERLAPPING** | **1.464, p = 0.010** | **1.437, p = 0.020** |
| full history, as registered | 1.279, p = 0.015 | 1.326, p = 0.065 |
| **2016+ — calendar-DISJOINT** | **0.765, p = 0.771** | **0.693, p = 0.806** |

> **Holding out securities is not holding out data when the securities
> co-move.**

**§37 — the kill checked as hard as a pass.** Three reasons this is not "the
shorter slice could not see it": the disjoint slice scores **461** rules against
the overlapping slice's **527**, comparable rather than a fraction; the point
estimates sit on opposite sides of 1.0 and the p-values on opposite sides of
0.5; and "2016+ has no tail structure" is refuted by N9's own foreign slice,
also 2016+, at **1.412, p = 0.040**.

**That last one is the honest complication and I have not resolved it.** On
calendar-disjoint data the set transfers on three securities (QQQ IWM XLK) and
does not on six others. Which is what an effective cross-section of ~1.4 says
you should be unable to distinguish — **six confirmation securities were never
six observations**, and this is the same arithmetic as §4 arriving from the
other direction.

**Status changes:**
- **N9 → `TRANSFER_NOT_ESTABLISHED_CALENDAR_CONFOUNDED`.** 1.271 withdrawn.
- **N9B → `INHERITS_PARENT_CONFOUND`.** It measured a *difference* between two
  vocabularies on this same confounded slice; the difference inherits the
  confound. "The vocabulary is not the ceiling" needs re-running before it is
  quoted.
- **N20 / N21 unaffected in substance.** They used the frozen *rules*, not the
  confirmation number, and N21's freeze audits CLEAN.

The programme's one surviving positive is gone, and it did not go the way the
order predicted. **Demonstrated edge remains 0%.**

## §3 — P0.5. The Null Invariance Contract, and it found more than clustering

`research_gym.null_invariance`. A `NullSpec` declares which properties of the
real treatment it preserves — frequency, turnover, run lengths, clustering,
seasonality, cross-sectional sync — `verify` measures them, and **`p_value`
refuses to compute anything from an ensemble that violates its own
declaration.** No skip flag. Declaring nothing raises.
`declared_invariants_for(outcome)` derives the requirement from the outcome's
*shape*: path-dependent outcomes are moved by the arrangement of exposure and
force clustering and run lengths; a mean forward return is a sum and does not.

Run against N21's registered placebo (worst security XRT, δ = 0):

| invariant | real | placebo | |
|---|---|---|---|
| frequency | 0.3822 | 0.3178 | **FAIL** — 17% low |
| run length mean / max | 77.4 / 310 | 24.7 / 60.8 | **FAIL** — 3.1× / 5.1× short |
| turnover | 0.0099 | 0.0257 | **FAIL** — 2.6× high |
| clustering lag 1 | 0.979 | 0.941 | ok |
| clustering lag 5 / 10 / 20 | 0.902 / 0.811 / 0.647 | 0.713 / 0.451 / −0.004 | **FAIL** |

Three things I did not know before running it:

1. **The matched-exposure placebo did not match exposure.** `n_off/H` windows
   of length `H` placed uniformly overlap, so they cover fewer days than
   `n_off`. It missed by 17% on the one property it was named for.
2. **The bias has a measured direction.** The placebo is de-risked *less* than
   the real policy, and less exposure-off means less mechanical drawdown
   reduction — so the comparison flattered the real policy on the exposure axis
   as well as the clustering axis.
3. **A shallow check would have cleared it.** Indistinguishable at **lag 1**,
   diverging only beyond one window length. "It has runs too" is exactly the
   reassurance a reader would have accepted.

The circular block shift passes every check on every security.

**N21 re-marked, as two fields rather than one:**

```
verdict          = POLICY_REDUCES_DRAWDOWN            (what the committed rule produced)
inference_status = PRIMARY_INFERENCE_INVALIDATED_BY_NULL_MISSPECIFICATION
```

The verdict is not rewritten. The rule ran as registered — a fact about the
trial. The instrument does not support the reading — a different fact.
Overwriting the first to record the second destroys what pre-registration
exists to create. The block-shift null stays a **diagnostic**: designed after
seeing the false positive, decisive about the registered null's inadequacy, not
a confirmatory negative.

## §4 — P7. You were right about the cross-section, and there is an arithmetic error under it

**The prose was wrong; the code was not.** "Eight equity ETFs are 1.81
observations" is wrong — they are 1.81 observations *per block*, and there are
forty blocks. N21's own code computed 40 × 1.81 = 72 correctly. The compression
into memory dropped the temporal dimension.

**And the 172-year figure is an arithmetic error.** The power stage did:

```python
need  = ((z_a + z_p) * sd_block / 1.5) ** 2   # ~343 EFFECTIVE observations
years = need * BLOCK_MONTHS / 12.0            # = 172   <-- divides by 2 blocks/yr
```

This slice supplies `2 blocks/yr × 1.81 = 3.62` effective observations per
year, not 2. **The honest figure is ~95 years.** 172 = 95 × 1.81: the effective
cross-section used once as a multiplier to get `n_eff` and then dropped
converting back — the same quantity counted once and forgotten once, in the
direction that made the finding louder. Both numbers now print side by side.

**What survives:** 95 against 20 is still unreachable, so *this design* cannot
resolve +3%/yr in terminal log growth, and drawdown on the same blocks remains
resolvable by a wide margin.

**What is withdrawn:** the generalisation *"any objective containing a
terminal-return term is unresolvable on 20 years of equity data"*. `1/ρ̄ ≈ 2` is
a property of things that move together, not of equity data.
`design_effect_n(100, 0.10) = 9.2` against `design_effect_n(100, 0.488) =
2.03`. Market-level directional claims live at the high-ρ̄ end;
**cross-sectional and relative claims do not**, and that is now arithmetic
rather than assertion.

**And the λ conclusion is withdrawn.** Under `U = E[R] − λ·Risk`, λ prices a
trade-off between two *measured* quantities; it cannot supply the one that
could not be measured. A large enough λ would otherwise make anything safer
automatically better — the cash degeneracy G3 already found. What a declared λ
*can* do is convert a measured risk reduction into a **break-even return
sacrifice**, and then the question is whether the return interval excludes it.
Same shape as `L_min`, and an honest use of a preference parameter.

**R13d** ships this: `design_effect_n(k, ρ̄)` as a *multiplier*, the
`cross_sectional_k` / `cross_sectional_rho` pair, and two new refusals —
`UNMEASURED_CROSS_SECTIONAL_DEPENDENCE` (k declared without a measured ρ̄; the
width is measurable on a policy-free surrogate *before* the test, so it is not
something to assume) and `AMBIGUOUS_CROSS_SECTIONAL_DECLARATION`.

## §5 — "Five independent routes" withdrawn

They are not independent. N4, N9, N20 and N21 interrogate the same precursor
family and share the N9-derived rule set. The defensible sentence is:

> **Several analyses of the same precursor family have failed to establish an
> economically useful de-risking signal, and the one that appeared to succeed
> is explained by calendar overlap with its own selection window.**

## §6 — The slice claim moved to registration

The register can only refuse trials that call it, and the trial that will not
call it is the one that needs refusing. `check_slice_declaration` now runs
inside `lint`, on by default: `UNDECLARED_SLICE_PURPOSE` (EXPLORE is a fine
answer, and it costs the confirmation claim — which is the point of saying it)
and `UNIDENTIFIED_CONFIRMATION_SLICE` (a CONFIRM must name securities, period
**and** information cutoff; the cutoff is required separately because two
trials can share a price window and differ in what they were allowed to know
inside it). The template carries all of it, and still refuses itself blank.

## §7 — P6. LightGBM: the seed was never the fix

`WM.fingerprint` hashes the exact arrays consumed, feature names in the same
digest so a permuted matrix is a different input; `provenance()` records the
library version, every hyperparameter and the flags. Asserted on **predictions,
not the metric** — two runs can round to the same loss from different trees.

**Measured, and it changes the advice:** with no row or column subsampling —
LightGBM's default and this model's configuration — `random_state` has nothing
to randomise. `seed=1` and `seed=999983` produce byte-identical predictions. So
the 1.22617 → 1.22598 drift never had anything to do with the seed, and "pin
the seeds" would have closed the ticket without fixing anything. It was
multithreaded histogram summation. Both dead mutation controls (seed, and
`num_leaves` 15 vs 63 — capped by `min_child_samples=200` on 900 rows) are
recorded in the test rather than deleted.

## §8 — Not done, and why

- **Daily OptionMetrics / `IV-ORACLE-GAP-1` (P1).** Not started. It needs WRDS
  credentials and a declared trial universe, and I would rather register it
  against the new slice-claim and null-specification fields than run it first.
- **N11's level losses (P2).** Not started.
- **G4 expectation layer (P3), winner/matched-loser factory (P4), P5's five
  novel trials.** Not started. §2 changes what P4 should be built against —
  the matched-loser design must hold out *time*, not only *names*.
- **N9B re-run on calendar-disjoint data.** Owed by §2, not done.

## §9 — Seven claims most likely wrong

1. That the 2016+ confirmation failure is about calendar overlap rather than
   about which six securities. The foreign slice's 1.412 at p = 0.040 is
   consistent with either, and I cannot separate them at ~1.4 effective series.
2. That `1.412, p = 0.040` on the foreign slice is real at all — it is one of
   eight aggregates computed, and ~0.4 are expected at 5% by chance.
3. That N9B "inherits the confound" rather than being independently
   informative. Not measured; asserted from lineage.
4. That the ~95-year figure is right. It reuses `sd_block` from a design whose
   dispersion estimate has its own interval.
5. That `declared_invariants_for` puts the right invariants on the right
   outcomes. The path-dependent/sum split is defensible and it is still a
   hand-written rule.
6. That n11's and n6's calendar embargoes are clean. They are clean on the
   boundaries their current `np.array_split` produces; change the fold count
   and 15.7% of boundaries are short.
7. That the pre-repair artifacts are genuinely immutable. The script refuses to
   overwrite; nothing stops `--overwrite`.

## §10 — Attended, and still yours

Nothing here touches production. **Not pushed** — 23 commits in aegis-finance
(`4784faa..118a55d`; the previous report said "20" for what was then 18, and
both counts were wrong — this one is `git rev-list --count`), 4 in
`Aegis module`. The campaign `--commit`, the
`LIVE_FORWARD` quarantine and Monday's paid IIF-1 attempt (~10:30 UTC /
18:30 MYT, one attempt, no H1 read) are unchanged and untouched. Per your own
note, I have not deployed anything ahead of the paid night.
