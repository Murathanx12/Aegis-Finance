# DECLARATION — the registered loss of IIF-1 (closing the LOSS registration gap)

**Status: DRAFT FOR SIGNATURE — UNSIGNED.**
SIGNED-BY: *(awaiting Murat — signing is his act; this draft is a session's
work per `HANDOFF_2026-08-18_BRAIN_ORDER_15.md` §5)*
Drafted 2026-08-22, before any licensed read (the read gate opens at 40 graded
nights; nights 1–4 are `ok`, so the gate is weeks away). **Required signed
before the 40-night read.**

## 1. The gap being closed

The frozen IIF-1 registration (`iif1_prereg.load_frozen_config`) declares
`PRIMARY_CONTRAST`, `PRIMARY_OBSERVABLES`, `MDE_Z`, `NW_LAGS`, and
`READ_SCHEDULE` — but **no `LOSS`, `METRIC`, or `SCORING_RULE` parameter**.
The loss has been implied by the observable and fixed in code
(`belief_state`: `rec["brier"] = (probability − outcome)²`) rather than
declared in the registration. `IIF1_PROXY_RISK_NOTE_2026-08-18.md` recorded
this gap before any licensed look; this declaration closes it.

## 2. What is declared (and it changes NOTHING that is frozen)

1. **The registered loss is the Brier score on the exact binary target**,
   per primary cell `night × ticker × observable × horizon × threshold`:
   `brier = (p − outcome)²`, outcome ∈ {0, 1} read directly from realized
   returns. No proxy stands behind the target (Patton 2011 is
   `NOT_APPLICABLE — EXACT TARGET, NO PROXY`; and per the proxy-risk note,
   "Brier is MSE, which is Patton-robust" must never be cited as if a risk
   was retired — the robustness question is moot, not satisfied).
2. **Base-rate reporting is part of the registered read.** Every Brier
   number prints beside its cell's realized base rate and
   `climatology_brier = base·(1−base)`, because the same Brier gap means
   different things at a 3% base rate and a 30% one. A read that omits the
   base rate is not the registered read.
3. **The paired difference remains the deciding quantity** — delta =
   Brier(B_tools) − Brier(A_snapshot), paired within cell, averaged to one
   number per night, `se = max(iid, HAC)` across nights — under the SIGNED
   minimum-meaningful bar (`DECLARATION_IIF1_MINIMUM_MEANINGFUL_BRIER.md`:
   BAR = 0.10 of each cell's own p(1−p), including the standing
   `NOT_ANSWERABLE_AT_N` sentence for `h=1|thr=0.03` at 40 nights).

## 3. What this declaration may NOT do

- It may not amend any frozen parameter — observables, contrast, MDE_Z,
  NW_LAGS, read schedule, and the signed Brier bar all stand exactly as
  registered. This is a *declaration of what was already fixed in code*,
  made explicit before the first licensed read can be confounded by a
  post-hoc metric choice.
- It may not be cited as a new metric choice: if any future session finds
  the code's loss and this declaration in conflict, the CODE AS FROZEN at
  registration wins and the conflict is a finding.

## 4. Falsification hook (inherited, restated)

If at the licensed read the realized base rates are high enough that
`base·(1−base)` is comparable to the paired difference's standard error,
rarity was not the binding constraint and the proxy-risk note's §3 was the
wrong worry — check it from the same numbers, don't assume it.
