# FINDING — 2026-08-24: the rank idea is spent, and the decision rule is why we know

**Amendment** `EVENT-RESPONSE-2/AMENDMENT-2` · hash `3e4c2c744895a856`
**Parent** `EVENT-RESPONSE-2`, spec_hash `534124d8bd63f4f4` (unchanged)
**Receipt** `event_response_v2_amendment2_receipt.json`
**Declared and committed BEFORE any of its numbers existed** (commit `22cb81d`)

## Verdict: **RANK_DOES_NOT_RESCUE_IT.** `EVENT_RESPONSE_v1` stays `NEEDS_CALIBRATION`.

---

## 1. The blocker it tried to remove

The model is FIT on OptionMetrics `stdopd` and would be SERVED on yfinance
chains. `iv_put_minus_call_30d` does not transfer — live median −0.0237 against
+0.0019, 25% positive against 55%, only 15% of live names clearing the screen's
borrow cut instead of 20%. A gradient-boosted tree splits on **absolute
thresholds**, so a systematic offset moves every split rather than degrading
gracefully. Dropping the column costs 0.0087 IC at 1d.

The idea: a **cross-sectional rank is invariant to any monotonic transform**, so
if the live residual is the research one shifted and rescaled, ranking removes
the problem *without fitting anything*. A calibration map would need its own
validation and could drift; a rank cannot.

The rank had to be PIT-safe, and the obvious choice is not: ranking within the
event **month** uses events that have not happened yet. Ranking within the
event's own **date**, across every name carrying option state that day, is
PIT-safe and is exactly what the live collector computes from its daily
universe snapshot — available on day one, no accumulated history needed. The
join covered **100.0%** of events.

## 2. What came back

| arm | drift1 IC | t | vs A | drift5 IC | t | vs A |
|---|---|---|---|---|---|---|
| **A** full raw | 0.03147 | 3.19 | — | 0.02883 | 2.61 | — |
| **B** drop borrow | 0.02275 | 2.52 | −0.0087 ± 0.0074 ✗ | 0.02486 | 2.30 | −0.0040 ± 0.0063 **✓** |
| **C** rank borrow only | 0.01974 | 2.20 | −0.0117 ± 0.0076 ✗ | 0.02246 | 2.03 | −0.0064 ± 0.0060 ✗ |
| **D** rank ALL option | 0.02531 | 2.69 | −0.0062 ± 0.0083 **✓** | 0.01107 | 0.96 | −0.0178 ± 0.0098 ✗ |

Declared rule: servable iff an arm lands within one paired SE of A at **both**
horizons. None does.

**Arm C is worse than deleting the column.** Ranking one member of a family
while its siblings stay raw gives the tree an incoherent scale across features
that describe the same surface — a real result, and not one I would have
predicted.

**Arm D is the best non-baseline arm at 1d and collapses at 5d** (t 2.69 → 0.96).

## 3. The reason this is a finding and not a failed attempt

**Each candidate passes at exactly one horizon and fails the other.** Three arms,
two horizons, one pass each. That is what chance produces.

Had the rule named only `drift1`, arm D passes and the model ships. Had it named
only `drift5`, arm B passes and the model ships. Two different models, each
justified by a real number, each selected by which horizon was written down
first.

The both-horizons requirement was declared before any of these numbers existed,
and it is the only thing standing between this session and a servable model
chosen by a coin flip. That is the second time in two days that **the decision
rule, not the analysis, was what prevented a wrong ship** — the first being
AMENDMENT-1's opposite-tail control.

## 4. What is actually going on underneath

The arms are being distinguished at low resolution. Paired SEs run 0.006–0.010
against effects of ~0.03, and every arm's IC sits at or under its own MDE₈₀:

* A: 0.0315 vs MDE₈₀ 0.0276 at 1d — the one that clears it
* B: 0.0228 vs 0.0253 · C: 0.0197 vs 0.0252 · D: 0.0253 vs 0.0264

So the honest statement is not "ranking fails". It is **"no reduced feature set
is distinguishable from the full one at the resolution this sample supports,
and the horizon disagreement shows the differences being measured are near
noise."**

## 5. What is left, and none of it is free

1. **A fitted calibration map** — quantile-map the live residual onto the stdopd
   distribution. It owes its own validation and can drift, which is exactly what
   the rank was chosen to avoid.
2. **Serve arm B and state the caveat.** It is within one SE at 5d, clears the
   0.01 economic bar, and sits under its own MDE₈₀ at 1d. Defensible under a
   `PRODUCT_EXPERIMENT` licence, which needs no significance gate — but it must
   be *said*, not rounded away.
3. **Match the rate and dividend assumptions properly.** The matched-strike fix
   moved the median only −0.0254 → −0.0237, so the remainder is a genuine
   solver/convention difference and this is the untried root-cause route.

**What stays untestable:** whether the two vendors *order* names the same way. A
rank fixes a monotonic distortion only. `stdopd` ends 2019 and the live chains
are 2026, so the two sources never observe the same name on the same day. This
was declared as a limitation in advance and remains one.
