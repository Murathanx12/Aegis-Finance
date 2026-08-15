# AUTOPSY-TO-RULE-1 and the REGRET_TENSOR

**Built** 2026-08-15 (brain order M4 + M5). **Code:**
`backend/services/research_gym/{autopsy,autopsy_llm,tensor}.py`.
**Tests:** `test_research_gym_autopsy.py` (30), `test_research_gym_tensor.py` (9).
**Runners:** `scripts/gym_autopsy_run.py`, `scripts/gym_build_tensor.py`.

> Everything here is **Gym output**: hypotheses, not results. No number may
> appear in a README claim, a track-record surface or a funding argument.
> `GymResult.as_claim()` raises; `adjudicate()` returns `citable: False`.

---

## 1. What an autopsy is, and what it is not

A failure taxonomy says *where* a decision went wrong. That is a label, and a
label does not generalise. The autopsy asks the next question — *what would have
had to be true about the world for this to be a repeatable mistake rather than
one bad afternoon* — and demands the answer in a form that can be run somewhere
else.

Optimus is **allowed to see the outcome**. That is what an autopsy is. The price
of that permission is that the output is a **type, not a paragraph**:

| field | why it is separate |
|---|---|
| `contemporaneous_evidence` | the only facts a rule may be built from |
| `post_outcome_evidence` | kept, because the autopsy genuinely used it — and kept apart, so the rule can be audited for leaning on it |
| `failed_assumption` | |
| `proposed_mechanism` | |
| `executable_precursor` | a closed-grammar predicate, not prose |
| `expected_affected_states` | |
| `expected_unaffected_states` | **the discriminating half** |
| `falsifier` | |
| `alternative_explanation` | the rival account, tested alongside |
| `proposed_action` / `default_action` | both named in advance, and required to differ |

`Autopsy.__post_init__` refuses anything missing. "The market was clearly
capitulating" is contemporaneous or post-hoc depending entirely on a fact the
sentence does not carry; the schema carries it.

### The four refusals, and why each exists

1. **No unaffected states → refused.** A mechanism that predicts every state
   predicts nothing. The absent list is what makes the present list falsifiable.
2. **Proposal equals control → refused.** Its edge is exactly zero on every
   slice. It would run, print a clean table of zeros, and be recorded as tested
   — the most expensive kind of null, because it looks like a measurement.
   *(Found by a test that used `hold` for both.)*
3. **A precursor reading the outcome → refused.** It fires on exactly what
   already happened and transfers to nothing.
4. **A precursor outside the shared vocabulary → refused.** See §3; this one
   cost a full run before it was understood.

## 2. The wall, wired rather than documented

`run_transfer` removes the origin episodes **itself**. "Remember not to include
the parent" is a rule that holds until the one time it does not, and a
contaminated transfer test looks *stronger*, so nothing downstream would notice.

A mechanism that was run outside its parent and never fired is **DEAD**, and the
death is ledgered — an unledgered death leaves this campaign's
multiple-comparison count understated and every deflation computed against it
too generous (§20).

Passing a slice requires the edge to clear **its own 80%-power MDE**, not merely
to be positive. Below the MDE is neither a pass nor a kill; it is an
undetectable test, and it says so (§19).

## 3. The defect the first live run produced — and it looked rigorous

The first end-to-end run reported, for every mechanism:

> **DEAD — the mechanism never fires outside the episodes that generated it.**

Confident, plausible, and **false**. The model wrote precursors over
`sp500_1m_return_pct` — a real field, present on every dataset-zero episode. The
transfer probes carried `vix` and `drawdown_pct`. Every lookup raised
`PrecursorRefused`, `evaluate_slice` swallowed each raise as `continue`, and
"could not be evaluated" became "did not fire".

The mechanisms were never **run**.

Note the direction of the error. It killed hypotheses, which reads as rigour —
the hardest direction in which to notice a bug. A layer below, a test already
pinned exactly this distinction (`a missing feature RAISES instead of evaluating
False`); the raise was correct and the caller discarded it.

Three fixes, at three depths:

- **symptom** — `SliceResult.n_unevaluable` is counted, and a mechanism that was
  never actually run reports **UNTESTED — a vocabulary failure, not a
  refutation**, never DEAD;
- **cause** — a declared `TRANSFERABLE_FEATURES` vocabulary, enforced when the
  `Autopsy` is *built*, so an untestable rule cannot be constructed;
- **corpus** — both the autopsied episodes and the transfer probes now carry
  that vocabulary, and `assert_probe_vocabulary` stops the run if they do not.

**A second defect fell out of the fix.** With the shared vocabulary in place the
episodes reported `realised_vol_20d = 0.0` for the first weeks of the sample: a
cold 20-day rolling window, NaN, filled with zero. A rule reading
`realised_vol_20d < 5` would have fired on all of them for a reason having
nothing to do with volatility. This repo already bans `fillna(0)` on feature
matrices; a state vector is a feature matrix with one row. Unmeasured features
are now `None`, the precursor **refuses to compare `None`**, and the features are
computed on long history so the windows are warm.

## 4. First real results — 6 autopsies, 5 foreign slices

Episodes: dataset zero, worst-first **by regret vs HOLD** (ordering by
regret-vs-best would rank subjects by how large the menu is in their state —
G1 choosing the study population). Slices: QQQ, IWM, XLF, XLE, XLK, EFA across
dotcom / GFC / eurocrisis / taper / late-cycle. Parent barred.

| | |
|---|---:|
| mechanisms proposed | **6** |
| replies dropped as untestable | 0 |
| explained only their parent (DEAD) | 0 |
| **exportable** | **0** |

The strongest — and the only one worth naming — came from the 2022-09-30 sell:

> **precursor** `vix >= 25 AND vix < 35 AND ret_1m_pct <= -5`
> **action** `buy_50` against a `hold` control

| slice | fired | edge vs hold | MDE | |
|---|---:|---:|---:|---|
| dotcom 2000–03 | 39 | +0.34pp | 3.44 | no |
| GFC 2007–10 | 8 | **+5.12pp** | 3.82 | **PASS** |
| eurocrisis 2011–13 | 11 | +3.13pp | 3.34 | no *(just short)* |
| taper 2014–16 | 6 | **+4.94pp** | 2.45 | **PASS** |
| late-cycle 2017–19 | 0 | — | — | never fired |

**2 of the 3 required slices**, on foreign securities and foreign decades, with
the parent excluded. It is still `REFUSED` — and would remain refused with a
third slice, because export additionally requires a frozen pre-registration and
forward certification. **The Gym cannot certify itself.**

Note also that a rule was genuinely *refuted*: the 2019-12-31 "sell into low
volatility and strong momentum" mechanism scored −8.82 / −2.99 / +2.17 / −0.29
across the slices where it fired. The machinery kills as well as it passes.

**§20 bookkeeping.** Six mechanisms were proposed and six lineage rows written.
This is a search of size six and must be deflated as one.

## 5. The REGRET_TENSOR

`state × action × horizon → regret distribution`, over SPY/QQQ/IWM/XLF/XLE/XLK,
1999–2026, weekly decisions, 10bp cost, horizons {5, 20, 60, 120, 252}.
**425 cells.** Each carries three numbers — the action's own return, the
ex-post-best regret (an upper bound, and the matched null other work subtracts),
and **the edge against a pre-declared HOLD**, which is the one that answers the
question and the only one that can be negative.

Each cell also carries its own `n_effective` and 80%-power MDE, because the
natural way to read a table of 425 cells is to scan for the largest number — a
maximum over 425 noisy draws, which is G1 one dimension up. `worst_actions()`
refuses to rank undetectable cells by default.

### What it says

**126 of 425 cells are detectable. Of those, 116 are negative.**

Every detectably-different de-risking action lost to holding, and the loss grows
with both stress and horizon:

| state | action | 20d | 60d | 120d | 252d |
|---|---|---:|---:|---:|---:|
| VIX 25–35 | `sell_100` | −2.07 | −5.89 | −8.82 | |
| VIX ≥ 35 | `sell_100` | | | −16.93 | **−38.84** |

The worst variant everywhere is `sell_100_reenter_down_5pct` — sell, then wait
for a *further* 5% fall before returning. Waiting for confirmation of the fall
was the most damaging thing in the menu.

### The ten positive cells, and the caveat that governs them

Only **10 of 425** cells are detectably positive. All are leveraged-long, and
they cluster in **VIX 25–35 — the moderate band, not the extreme one**:

| state | action | H | edge | MDE | n_eff |
|---|---|---:|---:|---:|---:|
| VIX ≥ 35 | buy_50 | 252 | +20.07 | 18.89 | **7.8** |
| VIX 25–35 | buy_50 | 120 | +4.13 | 4.02 | 45.0 |
| VIX 25–35 | buy_50 | 60 | +2.64 | 1.98 | 75.0 |
| VIX 25–35 | buy_50 | 20 | +0.85 | 0.62 | 296.0 |
| VIX < 15 | buy_50 | 20 | +0.27 | 0.23 | 622.0 |

Three things follow, and the third is the one that matters:

1. At the horizon dataset zero actually uses (63d), **VIX ≥ 35 cannot support
   the claim**: `buy_50` there is +2.82pp against an MDE of 5.14. The band that
   can is 25–35. The extreme-stress arm keeps failing to reach its own bar.
2. The single largest number in the table — +20.07pp at VIX ≥ 35 over a year —
   stands on **7.8 effective observations**. It is the U-shape's right arm
   wearing a different hat.
3. **`buy_50` is leveraged (1.5×), and this is an equity sample over a period
   with strong equity drift.** Leverage beats no leverage almost everywhere,
   including in calm markets. So "adding exposure wins" is not the claim; the
   claim can only be that it wins **more** in stress — which is a difference,
   and §18 requires it to be tested as one:

| H | stressed bucket | diff vs VIX<15 | SE | t | MDE | |
|---:|---|---:|---:|---:|---:|---|
| 20 | VIX 25–35 | +0.58 | 0.24 | **2.47** | 0.66 | not detectable |
| 60 | VIX 25–35 | +1.70 | 0.96 | 1.77 | 2.70 | not detectable |
| 120 | VIX ≥ 35 | +5.15 | 3.51 | 1.47 | 9.83 | not detectable |
| 252 | VIX ≥ 35 | +14.63 | 7.58 | 1.93 | 21.22 | not detectable |

**All eight comparisons point the same way; not one is detectable.** The largest,
`t = 2.47`, is nominally significant at 5% — and is one of eight overlapping,
non-independent comparisons, and sits below its own 80%-power MDE. (Those are
different bars: the MDE asks whether we *could* have seen an effect this size,
which is stricter than asking whether this sample's estimate clears a p-value.)

The honest summary: **consistent in sign, established nowhere.**

## 6. What is NOT built, stated rather than omitted

- `REPLACE_WITH_MARKET` / `REPLACE_WITH_SECTOR` are in the ordered action
  surface and are **not implemented**: both need a second asset's return path
  per episode, which is data plumbing rather than a policy.
- The tensor's state is the frozen VIX bucketing. Transition states
  (CALM/DETERIORATING/PANIC/CAPITULATION/RECOVERY) are the ordered next step
  (T4) and are **candidate representations, not labels asserted as truth**.
- No mechanism has been pre-registered. None is close to forward
  certification. Nothing here is evidence.

## 7. Running it

```bash
python -m scripts.gym_build_matched_null          # G1 null — first
python -m scripts.gym_dissect_timing --write      # dataset zero
python -m scripts.gym_autopsy_run --limit 6 --write
python -m scripts.gym_build_tensor --stride 5
```
