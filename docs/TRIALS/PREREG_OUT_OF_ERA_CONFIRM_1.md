# PREREG — OUT-OF-ERA-CONFIRM-1 (frozen BEFORE the confirmation data
# existed locally)

SIGNED-BY: Murat Abdullaev — recorded overnight handoff approval
2026-08-19 ("run a mega test to learn ... I approve everything"),
recorded by the working session; this protocol was frozen while the
1990–2012 pull was still in flight, so no aggregate of the
confirmation era could have shaped it.

**Status: SIGNED under the recorded blanket. Runner gates on
`assert_signed` + the mean-masked §64 audits below being on disk
before any verdict.**

## What this confirms

Three leads were GENERATED tonight on 2013–2024 (mega-sweep + streak
screens). §37 forbids confirming on the generating sample; the
confirmation slice is **1990–2012** (held-out TIME, §60), pulled under
byte-identical frozen filters. The JKP factor screens are NOT in this
family — their generating sample already spanned the early era, and a
"confirmation" there would be recycled data wearing a new name
(declared here so it cannot drift in later).

## The m = 4 declared cells (Holm FWER 0.05 across exactly these)

Each cell: identical book/event machinery, early-era panel, flat 3bp
cost, paired monthly (books) or per-event (streaks) differences,
blocks derived from the panel's own spacing; three-way verdicts with
the same relabeling as the parent screens. Direction DECLARED from the
2013–2024 screen — a confirmation asks "same sign, clears its
run-time MDE"; an opposite-sign result at MDE is an ANTI-confirmation
and must be reported as such.

1. `mom63_book`: mom_63 | rank | trim | 50 vs baseline.
   Declared direction: NEGATIVE (screen: −26%/yr, p 0.0005).
2. `value_exempt_book`: value_bm | inverse_vol | exempt | 50 vs
   baseline. Declared direction: POSITIVE (screen: +6.5%/yr, p 0.21 —
   the weakest declared cell, included deliberately: a lead this soft
   confirming out-of-era would mean far more than tonight's p).
3. `streak_up7`: ≥7-up-day events vs matched controls, 21d forward.
   Declared direction: NEGATIVE (screen: −0.25%, primary
   NOT_ESTABLISHED with reversal lean).
4. `streak_up5`: same, length 5 (screen: −0.15%, p 0.066, n 78,762).

## Gates before any verdict

- §64 mean-masked power audit per cell on the EARLY panel; each cell's
  limbs declared ANSWERABLE / NOT_ANSWERABLE_AT_N at that point.
- Economic bars carried from the parents: books 0.005/yr-fraction
  monthly bar as in MEGA-SWEEP screens is not defined — bars here:
  book cells use the G2 margin logic (0.5%/yr, never shrunk); streak
  cells 0.25% per 21d.
- The early era's NOMINAL screen drift (a $5/$100M cut is stricter in
  1990) rides every verdict sentence.

## May NOT

Add/substitute cells; re-tune any parameter against early-era output;
quote a confirmation as a tradable edge (§61 cap
ADAPTIVE_HISTORICAL_VALIDATION); treat an underpowered miss as either
confirmation or refutation.

— frozen 2026-08-19 ~21:30 HKT, early-era pull in flight, no early-era
byte read by any Aegis computation at freeze time

---

## RESULTS (registered run 2026-08-19 night, appended post-run)

Receipt `lane_factory/out_of_era_trial_2026-08-19.json`; §64 audit
written first (`out_of_era_audit_2026-08-19.json`).

| cell | declared | mean | MDE | p | verdict |
|---|---|---|---|---|---|
| `streak_up5` | NEG | **−0.366%/21d** | 0.246% | ~0.0000 | **CONFIRMED** |
| `streak_up7` | NEG | −0.345%/21d | 0.372% | 0.0093 | NOT_ESTABLISHED (misses MDE by 0.03%) |
| `mom63_book` | NEG | −10.2%/yr | ~16%/yr | 0.0706 | NOT_ESTABLISHED |
| `value_exempt_book` | POS | +3.1%/yr | ~9.5%/yr | 0.3562 | NOT_ESTABLISHED |

**The confirmed sentence (scope-aware):** on 1990–2012 US
PIT-eligible names under the frozen nominal screen, a stock that
closed up ≥5 consecutive days went on to LAG its momentum/vol-matched
same-date twin by 0.37% over the next 21 trading days — same sign as
the 2013–2024 generating screen (−0.15%), larger in the early era,
surviving Holm at m=4 and clearing the 0.25% economic bar. This is a
short-horizon REVERSAL/avoidance regularity, the program's second
Holm-surviving effect (after CONVEXITY-PRESERVATION-1) and its first
OUT-OF-ERA confirmation. §61 cap: ADAPTIVE_HISTORICAL_VALIDATION — a
candidate negative rule (avoid buying right after streaks; defer
entries), never a standalone trading signal. SCREEN note: 4/4 cells
matched their declared signs (P = 1/16 under independence).
Descendants: STREAK-AVOID-RULE-1 (does deferring entries after
streaks improve a real book net of costs?) and the G3-generation
transport, each with fresh preregistration.
