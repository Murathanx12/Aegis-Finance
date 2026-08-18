# DECLARATION — the minimum meaningful paired Brier difference (IIF-1)

**Status: DRAFT FOR SIGNATURE. Unsigned.**
Drafted 2026-08-18, before the first licensed read (40 nights). Required signed
before 2026-08-21.

Signing this fixes ONE number per registered cell. After the number is fixed,
the campaign's result is interpretable; before it, a null is not a finding and a
positive is not a size.

---

## 1. What is being declared, exactly

The quantity is the **paired difference in Brier score between the treatment and
control arms, with the NIGHT as the unit**:

```
    delta = Brier(B_tools) - Brier(A_snapshot)      negative = tools are better
```

paired within `night x ticker x observable x horizon_days x threshold`, averaged
to one number per night, and standard-errored across nights with
`se = max(iid, HAC)`.

What is being declared is **the smallest |delta| that would change what we do.**
Not the smallest detectable one — that is the MDE, it is already measured, and
declaring it here would be circular: it would make "meaningful" true exactly
whenever the trial happens to detect something, which is a machine for
manufacturing findings.

## 2. Why this has to be signed BEFORE the read

§64: a power check that consumes no outcome is free and therefore obligatory
before any confirmation. It has been run. The result is section 4, and it says
something that cannot be un-said after the fact:

> **at the 40-night read, one of the two registered cells cannot detect the
> smallest difference that would matter, at any bar at or below 12%.**

If that is discovered *after* the read, the null from that cell will be argued
about. Declared now, the cell simply returns "not established at 40; the
question survives to 80", which is a real and useful outcome. This is §19 in its
forward-running form: below the MDE, a test returns "not established" whatever
the world does, and the window is gone with nothing learned.

## 3. The scale the bar is expressed in, and why not raw Brier

The two registered cells have **different base rates** — 9.7% and 19.6% — and
therefore different natural scales. Their uncertainty terms (the Brier of the
climatology forecast, `p(1-p)`) are:

| cell | base rate | uncertainty `p(1-p)` |
|---|---:|---:|
| `abs_move_exceeds \| h=1 \| thr=0.03` | 0.0972 | 0.0877 |
| `abs_move_exceeds \| h=5 \| thr=0.05` | 0.1963 | 0.1578 |

A single raw-Brier bar across both would be a **different demand** in each — 80%
stricter in the first cell than the second, for no reason anybody chose. The
same argument that forbids one pooled MDE across the thresholds forbids one
pooled bar.

So the bar is declared as a **fraction of the cell's own uncertainty**, which is
identical to declaring a **Brier Skill Score improvement over the measured
climatology**:

```
    minimum_meaningful_delta(cell) = BAR x p(1-p)      [BAR is what you sign]
```

`BAR = 0.10` reads: *"the tools arm must remove at least a tenth of the skill
that a climatology forecast leaves on the table, or we do not care."*

## 4. What each candidate bar implies — this is the decision

MDE at 40 nights, at the **measured** intra-night correlation
(`rho = 0.0737 / 0.0613`, design effect 3.88 / 3.39 at 39-40 cells per night,
`MEASURED_INTRACLASS_FROM_DAILY_EXCEEDANCE_COUNTS`), alpha 0.05, power 0.80:

| cell | MDE at rho=0 (floor) | **MDE at measured rho** |
|---|---:|---:|
| `h=1 \| thr=0.03` | 0.00536 | **0.01055** |
| `h=5 \| thr=0.05` | 0.00836 | **0.01540** |

| BAR | cell | min meaningful delta | detectable at 40? | nights needed |
|---:|---|---:|:--:|---:|
| 5% | `h=1 \| thr=0.03` | 0.00439 | **no** | 231 |
| 5% | `h=5 \| thr=0.05` | 0.00789 | **no** | 152 |
| **10%** | `h=1 \| thr=0.03` | 0.00877 | **no** | **58** |
| **10%** | `h=5 \| thr=0.05` | 0.01578 | yes | 38 |
| 15% | `h=1 \| thr=0.03` | 0.01316 | yes | 26 |
| 15% | `h=5 \| thr=0.05` | 0.02367 | yes | 17 |
| 20% | `h=1 \| thr=0.03` | 0.01755 | yes | 14 |
| 20% | `h=5 \| thr=0.05` | 0.03156 | yes | 10 |

Read the "nights needed" column against the registered read schedule
**(40, 80, 120)**.

## 5. Recommendation — `BAR = 0.10`

**Recommended, and the recommendation is not the comfortable one.**

At 10%, the `h=5` cell resolves at the 40-night read (needs 38) and the `h=1`
cell does not (needs 58) — it resolves at the **80-night** read with room to
spare. So a signed 10% bar produces, at 40 nights, an honest split verdict:
one cell answers, one cell says *"not established; the question is alive and
arrives at 80."*

Why not the bars that would make both cells resolve at 40:

- **15% and 20% are detectable because they are large, not because they are
  right.** They would be a bar chosen so the instrument can clear it, which is
  the same defect as tuning a threshold after seeing the data — §37 wearing a
  power calculation. A 20% skill improvement from swapping a snapshot for a
  toolset would be an enormous result; declaring it as the *minimum* worth
  noticing throws away every real effect smaller than enormous.
- **5% is honest but unreachable.** 152-231 nights is 4-6x the campaign, and
  declaring a bar the campaign provably cannot reach converts the whole trial
  into a pre-announced null. §39: a window is only a window if something fits
  in it.

10% is the largest bar that is not chosen for detectability and the smallest
that fits inside the registered schedule. That is the entire argument for it.

## 6. What the signed number does, mechanically

At each licensed read, per cell, the grader reports one of exactly four:

| condition | verdict |
|---|---|
| `delta` significant AND `\|delta\| >= min_meaningful` | **EFFECT** — reportable, sized |
| `delta` significant AND `\|delta\| < min_meaningful` | **REAL BUT IMMATERIAL** — the arms differ by less than we said we would care about |
| not significant AND `MDE <= min_meaningful` | **ABSENT** — a real null; the trial could have seen what mattered and did not |
| not significant AND `MDE > min_meaningful` | **NOT ESTABLISHED** — underpowered; not a kill (§19) |

The fourth row is the one this declaration buys. Without a signed number, every
null collapses into an argument about which of rows 3 and 4 it was.

## 7. Scope, stated so it cannot expand later

- Applies to **IIF-1 only**, to the two registered cells above, for the
  **frozen** loss observable `abs_move_exceeds`, comparing **`B_tools` against
  `A_snapshot`** and no other pair.
- Does **not** apply to the `return_sign` cell, which has no declared bar and
  is therefore exploratory at every read.
- The declared bar may be **tightened** later only with a written amendment
  carrying a reason, and never after a read.
- The measured `rho` may be re-measured. If it rises, the MDE rises and the
  table in section 4 shifts against us; that is a measurement, not a
  renegotiation, and it does not change the signed BAR.
- **`UNSTAMPED` night 1**: night 1's receipt carries no `implementation_version`
  and has NOT been coerced to 1. The within-version contrast has a hole exactly
  at the boundary the field exists to mark. This declaration governs the pooled
  and the within-version reads alike; it does not repair the hole.

---

## Signature

I declare the minimum meaningful paired Brier difference for IIF-1 as

    BAR = ______   (recommended: 0.10)

giving, at the measured base rates:

    h=1 | thr=0.03 :  ____________     (0.00877 at BAR = 0.10)
    h=5 | thr=0.05 :  ____________     (0.01578 at BAR = 0.10)

and I record that I have read section 4, in particular that at `BAR = 0.10`
the `h=1 | thr=0.03` cell is **expected to return NOT ESTABLISHED at the
40-night read** and to resolve at 80.

Signed: ............................................  Date: ................
        Murat Abdullaev

---

*Numbers in sections 3 and 4 are reproduced by
`python -m scripts.iif1_grade --power` and the stored measurements in
`backend/data/optimus/iif1_rho_h{1,5}_t{3,5}.json` and
`iif1_climatology_h{1,5}_t{3,5}.json`. They consumed no outcome.*
