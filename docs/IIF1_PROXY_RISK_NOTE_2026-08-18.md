# IIF-1 proxy-risk note — recorded BEFORE any licensed look

**2026-08-18, written on the review's P1 #8 order: "identify the exact frozen
magnitude loss, classify it against Patton 2011, record the caveat before any
licensed outcome inspection. No metric amendment."**

**H1 remains unread. Nothing below inspects an outcome — the first IIF-1 record
does not resolve until 2026-08-21, and the read gate opens at 40 graded nights.**

---

## 1. What the frozen pre-registration actually declares

Read from the frozen config via `iif1_prereg.load_frozen_config`:

```
PRIMARY_CONTRAST        ('A_snapshot', 'B_tools')
PRIMARY_OBSERVABLES     (('abs_move_exceeds', 5, 0.05),
                         ('abs_move_exceeds', 1, 0.03))
SECONDARY_UNDERPOWERED  (('return_sign', 5, None), ('beats_benchmark', 5, None))
MDE_Z 2.8 · NW_LAGS 2 · READ_SCHEDULE ((40, 4.312), (80, 3.295), (120, 2.845))
```

**There is no `LOSS`, `METRIC`, or `SCORING_RULE` parameter in the frozen set.**
The loss is implied by the observable and fixed in code rather than declared in
the registration — worth recording as a registration gap in its own right, and one
that cannot be amended now.

The implied loss is the **Brier score**, from `belief_state`:

```python
Observable.ABS_MOVE_EXCEEDS = "abs_move_exceeds"   # P(|return| > threshold)
rec["brier"] = float((rec["probability"] - outcome) ** 2)   # outcome in {0, 1}
```

So the primary metric is **Brier on a binary threshold event**, with
`climatology_brier = base·(1−base)` reported beside it.

## 2. Classification against Patton (2011) — the concern does not bind here

The review's framing assumed a volatility forecast scored against a noisy
volatility proxy:

> "With an imperfect but conditionally unbiased volatility proxy such as squared
> daily returns, forecast rankings can change merely because of proxy noise…
> If the frozen IIF magnitude loss is MSE or QLIKE, the single-`r²` proxy is
> extremely noisy…"

**IIF-1 does not forecast volatility and uses no proxy.** `abs_move_exceeds(5d,
5%)` is a **directly observable binary event**: take the realized 5-day return,
check whether `|r| > 0.05`. There is no latent σ² standing behind it and nothing
is being estimated in the target. The realized outcome is the quantity itself.

Patton's result concerns loss functions evaluated against a *proxy* `σ̂²` for a
*latent* `σ²`, and identifies the class (MSE and QLIKE among the nine examined)
whose expected ranking is unaffected by that proxy's noise. **With an exact
target there is no proxy noise for the ranking to be sensitive to, so the
robustness question is moot rather than satisfied.**

A nuance worth stating precisely, because it is the thing most likely to be
misremembered later: **Brier on a binary outcome *is* MSE** — squared error where
the target happens to be in `{0, 1}`. So one could say "the frozen loss is MSE,
which is in Patton's robust class". That sentence is true and misleading: it would
be invoking a robustness property to solve a problem this design does not have.
Recorded here so nobody later cites Patton as reassurance about IIF-1 and thinks a
risk was retired.

**Verdict: `NOT_APPLICABLE — EXACT TARGET, NO PROXY`.** No metric amendment,
consistent with the order.

## 3. The risk that *does* bind, and it is power, not ranking

Replacing the proxy-noise concern with the real one, recorded now so it cannot be
discovered after a disappointing read:

* **The primary events are rare, and rarity caps Brier resolution.**
  `P(|r| > 5%` over 5 days`)` and `P(|r| > 3%` over 1 day`)` on a
  trigger-selected universe are low-base-rate events. Brier decomposes as
  reliability − resolution + uncertainty, and `uncertainty = base·(1−base)` shrinks
  toward zero as the base rate does. Two arms can differ meaningfully in judgement
  while their Brier difference sits inside the noise, because there is very little
  outcome variance for either to explain.
* **The base rate is not yet measurable**, and that is the honest state: nothing
  resolves until 2026-08-21. It must be reported *with* the read, because the
  same Brier gap means different things at a 3% base rate and a 30% one.
* **The pre-registration already priced direction out for this reason** (σ_π 0.0036
  vs 0.1183 — a direction primary never resolves at any n), which is why the
  primary is magnitude. That decision is consistent with this note; the residual
  risk is that magnitude at these thresholds is *also* thinner than the MDE
  assumed.
* **The paired structure is the mitigation** — `night × ticker × observable ×
  horizon × threshold`, so both arms face the identical realized outcome and the
  event's rarity cancels in the *difference* even though it caps each arm's
  absolute score. This is the argument that the design still has power, and it is
  an argument about the contrast, not about the level.
* **`MDE_Z 2.8` and `NW_LAGS 2` are frozen**, so the MDE will be computed as
  registered whatever this note says. Per §19 the MDE must be printed beside the
  result, and per §64 it should have been checked forward at reservation time.

## 4. What would falsify this note

If, at the licensed read, the primary observables' realized base rate is high
enough that `base·(1−base)` is comparable to the paired Brier difference's
standard error, then rarity was not the binding constraint and this note's §3 was
the wrong worry. That is checkable from the same numbers the read produces, and it
should be checked rather than assumed — a caveat recorded in advance still has to
be scored.

## 5. Out of reach from this repository

`iif1_read_gate.check_read` enrolment in the missing-input/refusal scan is the
review's P1 #7 and **cannot be done here**: the gate and the frozen artifact live
in the `Aegis module` sibling, which this repo deliberately does not carry (the
deployed image does not either, which is why a paying night cannot run in prod).
Flagged, not attempted. It remains a hard prerequisite before night 40 licenses a
read.
