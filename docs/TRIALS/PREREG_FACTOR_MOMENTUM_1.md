# PREREG — FACTOR-MOMENTUM-1

SIGNED-BY: Murat Abdullaev — recorded overnight handoff approval
2026-08-19 ("I want you to run these tests ... I handoff to you"),
given AFTER the design was registered and BEFORE any outcome existed;
recorded by the working session.

**Status: SIGNED. §64 audit complete (below), run follows. Dataset:
`jkp/usa_all_factors_monthly_vw_cap.csv` (sha b47dcdb54d208e45, 153
factors, 1926–2025, provenance in the meta).**

**§64 power (mean-masked, receipt `fm1_power_audit_2026-08-19.json`,
run before any mean was seen):** 877 usable months (310 thin months
dropped — the pre-fundamentals era), 73 effective 12-month blocks,
monthly MDE 0.00143 (≈1.71%/yr). The 0.5%/yr economic bar is BELOW the
MDE, therefore declared prospectively: **STATIC_NONINFERIOR is
NOT_ANSWERABLE_AT_N** — reachable verdicts are MOMENTUM_WINS (a net
effect ≥ its run-time MDE; the literature's gross claim of 2–4%/yr
would clear it if real and cost-surviving) and NOT_ESTABLISHED. The
bar is not shrunk. Rehearsal gate passed pre-run: persistent ⇒
MOMENTUM_WINS, null ⇒ STATIC_NONINFERIOR, reverting ⇒ never a win
(receipt in the run log).**

Origin: Murat's question ("why can't we make capital-shifting toward
winners work?"). The LIVE-fleet version stays rejected
(`DECISION_QUARTERLY_LANE_GENERATIONS.md`): 10 lanes × 90 days cannot
distinguish luck from skill. This trial asks the same question where it
IS answerable: ~150 strategies × ~70 years.

## Question

Does periodically reallocating toward recently-winning FACTORS beat
holding all factors at equal weight, net of costs? (The academic prior:
"factor momentum" — Ehsani–Linnainmaa and successors — reports yes,
gross. A published result is a PRIOR, never an Aegis receipt.)

## Data (to be assembled before signature)

- JKP US long-short factor return series, monthly, capped-value-weighted
  (jkpfactors.com/data public download; 153 factors, 13 themes).
  Fallback if unusable: build from `contrib_global_factor.global_factor`
  per JKP methodology (heavier; documented substitution, not silent).
- Construction-vintage caveat recorded on the dataset meta: the series
  are modern-methodology backfills — acceptable here because the
  QUESTION is about reallocation among a FIXED strategy set, not about
  discovering the strategies; the set must be frozen to the full 153
  (no dropping factors that "wouldn't have been known" without a
  declared PIT sub-analysis).

## Primary (ONE deciding cell)

- Rule: each month, rank factors by trailing 12-1 month return; hold the
  top tercile at equal weight ("factor-momentum book") vs the all-153
  equal-weight book ("static book").
- Deciding number: paired monthly return difference (momentum book −
  static book), net of a declared turnover cost (one-way bps × measured
  turnover; rate declared at signature from TAQ-informed bands).
- Inference: date-block bootstrap; block derived from the panel's own
  spacing to cover the 12-month formation overlap
  (`bootstrap_block_dates(dates, 252)`), never a hardcoded month.
- Verdicts (three-way, committed now): MOMENTUM_WINS / STATIC_NONINFERIOR
  (one-sided: momentum's advantage bounded below the economic bar) /
  NOT_ESTABLISHED. Economic bar: 0.5%/yr net — below that, the machinery
  is not worth the turnover. Bar never shrinks.
- §64: mean-masked power audit on the exact primary before signature;
  each verdict limb declared ANSWERABLE / NOT_ANSWERABLE_AT_N.

## SCREEN (reported, never deciding; BH-FDR 0.10, m = cells run)

Formation windows 1/3/6/12 months; top-quintile vs tercile; theme-level
vs factor-level; regime blocks (§58 date blocks); drawdown/vol of each
book (the §59 risk read).

## May NOT

- Promote a screen cell (§37). Feed any lane before a G-generation
  prereg transports it (quarterly-generations rule 2). Claim the result
  applies to picking OUR 10 lanes by 90-day returns — the trial's n is
  the reason the live version stays rejected; §60 scope.

— design registered 2026-08-19; priors: MODERATE for gross effect
(literature), UNKNOWN net of costs at our bar
