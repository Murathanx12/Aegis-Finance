# NIGHT-13 — TRANSACTION-ENSEMBLE-1: his record, bounded without his records

**Trial:** TRANSACTION-ENSEMBLE-1 · **Prereg:** `Aegis module/TRIALS/PREREG_TRANSACTION_ENSEMBLE_1.md`, frozen at **c5b81aa** before any member was generated · **Accrues ZERO** — this is a measurement instrument; it can promote nothing.

> **EVERYTHING BELOW IS SYNTHETIC.** No member of this ensemble is Murat's
> history. 200 transaction histories were generated, each consistent with a
> DECLARED subset of the known anchors; only conclusions that hold across the
> ensemble are adopted. **The range IS the result.** No member is promoted,
> quoted alone, or labelled "most likely" — that would be the outcome-shopping
> his instruction ("choose the best outcome") licenses only in this form.

Run: `python scripts/run_transaction_ensemble.py` · master seed 20260811,
member *i* uses `default_rng([20260811, i])` · **N = 200 accepted members over
240 slots** (8 declared-subset arms × 2 QUBT arms × 15) · 41,671 rejected
attempts, every one counted by reason · code
`backend/services/transaction_ensemble.py`, tests
`backend/tests/test_transaction_ensemble.py` (offline; the silent-fragility
check asserts the ensemble actually VARIES where data is unknown).

## 0. What a member is, and what the gap parameter is

A member is a shares-ledger history over the covered price window (2025-11-07
→ 2026-08-10): constant shares per holding episode with optional two-tranche
entries; entries funded from cash + sale proceeds (an unfundable purchase is a
rejection, not an adjustment); the three annotated exits (TVTX @34.4, ALMS
@10, SLDP @8.1) land only on days whose close is consistent with the stated
fill — tolerance **measured** per name from the demonstrated mismatch between
his own sheet marks and the adjusted panel (TVTX/ALMS 6%, **SLDP 24%**,
because his 8.5 Nov mark sits 24% from the same-day adjusted close); APLT has
no surviving bars, so its collapse date inside Nov→Jan is a **sampled
dimension** (0.80 sheet mark → 0.09 Jan sheet mark → $0.088 takeout).
The 2026-07-11 conviction-log share counts pin the book — and therefore the
**dollar scale** of every member — from July onward.

Price bars start 2025-10-27; anchors 7/8/9 reach back to mid/early 2025. The
uncovered months enter as **one bounded free parameter per anchor** — the
book's return over the gap, bounded to [−50%, +150%] — and every member
records the gap return its anchors require. An anchor satisfiable only
outside those bounds is inconsistent for that member. **How much work the gap
does is reported below, prominently, because it turns out to be the answer.**

Histories with intra-episode trims, invisible round-trips between sheet
dates, or external cash contributions are OUTSIDE this family. The bounds
below are bounds on this family, stated as such.

## 1. Q2 — the anchor-consistency matrix (the finding that frames the rest)

Anchors 7 ("+73.7% / +$15,165 ~1yr"), 8 ("2025 +115%") and 9 ("$25k→$45k")
are mutually unreconciled. Which subsets admit ANY consistent history?

| declared arm | QUBT 300 | QUBT 200 | required gap, anchor 7 | anchor 8 | anchor 9 |
|---|---|---|---|---|---|
| `{}` (always-on only) | 15/15 | 15/15 | — | +0.90..+1.49 | +1.25..+1.43 |
| `{7}` | 11/15 | 7/15 | +1.22..+1.49 | — | — |
| `{8}` | 15/15 | 15/15 | — | +0.95..+1.45 | — |
| `{9}` | 15/15 | 15/15 | — | — | +0.96..+1.50 |
| `{7,8}` | 9/15 | 11/15 | +0.96..+1.50 | +0.86..+1.20 | — |
| `{7,9}` | 10/15 | 10/15 | +1.15..+1.49 | — | +0.77..+1.05 |
| `{8,9}` | 15/15 | 15/15 | — | +0.87..+1.50 | +0.74..+1.49 |
| `{7,8,9}` | **11/15** | **11/15** | +1.09..+1.49 | +0.93..+1.25 | +0.72..+1.05 |

**Every subset admits a consistent history, including all three anchors
jointly** — the maximal consistent subset is **{7,8,9}**. The anchors do not
contradict each other. But look at the price of consistency:

1. **The gap does the work.** Every consistent history requires the book to
   have returned roughly **+72% to +150% in the months BEFORE 2025-11-07** —
   pinned against the +150% plausibility ceiling. The unfilled slots (40, all
   in anchor-7 arms) died mostly against that ceiling and against anchor 7's
   dollar level. If his headlines are true, **they were substantially earned
   before the first PIT sheet exists.** No covered-window arrangement of his
   documented trades produces them.
2. **Anchor 7's end level ($35,742) is touched almost only inside the June
   war drawdown.** The July log counts force end-of-window equity to ~$40.4k
   (QUBT 300), so a "+73.7% over ~1yr" statement marks either to a war-dip
   day in Jun/Jul-2026 or to the very bottom of the cash band — 2,985
   attempts were rejected because the book never touched the level at all.
3. **Anchors 7 and 9 are mutually coherent** through the same story: $20.6k
   (mid-2025, anchor 7's implied start) and $25k (anchor 9's start, slightly
   later) both roughly doubling into a ~$46–51k Nov-7 book, which then LOSES
   money over the covered nine months and ends near $45k equity+cash.

## 2. What is now ensemble-robust about his record

Graded by the frozen rule (prereg §4): `ensemble_robust` iff sign AND
magnitude class (|x|<5 small, 5–20 moderate, ≥20 large) agree across every
member of every arm. Counts are member-values (a member's within-history
ambiguity contributes both endpoints, so it must agree with itself too).

**Q1 — the +73.7% headline decomposes, robustly (n=178 values, 89 members):**

| component | label | range (pts of headline) |
|---|---|---|
| selection (EW buy-and-hold of his 13 Nov picks, covered window) | `ensemble_robust` | **+20.2 .. +43.1** |
| weighting / trading (as-traded minus selection) | `ensemble_robust` | **−66.0 .. −29.3** |
| uncovered gap (residual the pre-Nov months must supply) | `ensemble_robust` | **+76.2 .. +106.1** |

Reading: in every history consistent with his own anchors, **his
weighting/trading subtracted 29–66 points** from what equal-weight
buy-and-hold of his own picks would have done over the covered window, and
**the uncovered pre-November months must supply more than the entire
headline** (+76 to +106 of the 73.7). NIGHT-12's "most of his headline was
weighting/trading" is now sharpened: over the documented window the
weighting/trading contribution is robustly **negative**; the headline lives
in the undocumented months.

*selection_pts is a basket return, NOT a skill claim: his non-picks did
+33.0% over the same window, the picks-minus-pool difference (+1.6pts) sits
under CONVICTION-REPLAY-1's measured 80-pt MDE, and that verdict —
UNRESOLVED — stands (§19).*

**Q4 — as-traded bounds for FACTORIAL-PM-1 (n=200):**

| statistic (2025-11-07 → 2026-08-10) | label | range |
|---|---|---|
| total return | `DATA_NEEDED` | **−35.2% .. +4.9%** (p50 −14.9%) |
| max drawdown | `ensemble_robust` | **−45.0% .. −23.6%** |
| war-window drawdown (2026-06-04→07-29) | `ensemble_robust` | **−24.3% .. −13.9%** |
| terminal wealth ratio | `ensemble_robust` (sub-1x in class) | 0.65x .. 1.05x |

The war-window range brackets NIGHT-12's measured −22.9% for his book — the
ensemble reproduces the episode it never saw. FACTORIAL-PM-1's B1 as-traded
column consumes these **as a range with the label attached, never a point**
(its prereg §1 already says so).

**Q3 — the three exits, in NAV terms (n=200): signs are robust, sizes are not.**

| exit | label | cost, pts of terminal NAV (+ = the exit cost him) |
|---|---|---|
| TVTX @34.4 | `DATA_NEEDED` (sign robust +, class spans) | **+2.0 .. +21.8** |
| ALMS @10 | `DATA_NEEDED` (sign robust +, class spans) | **+7.6 .. +96.6** |
| SLDP @8.1 | `DATA_NEEDED` (sign robust −, class spans) | **−14.0 .. −1.3** |
| total | `DATA_NEEDED` | −1.7 .. +98.1 |

Directionally this confirms NIGHT-12's per-share audit (ALMS and TVTX exits
cost, SLDP's saved) in NAV terms — but the magnitudes hinge on position
sizes no source carries, and the ALMS range alone spans "annoying" to
"half the terminal book". Exits do NOT grade uniformly early (SLDP is
robustly a good exit); the "exits too early" self-diagnosis stays a
per-position question.

**Q1 — the "+115%" headline (n=400 values, 200 members):** selection over
the covered Nov→Dec-31 stub is `ensemble_robust` **small negative** (−1.5);
the gap is `ensemble_robust` **+99.7 .. +128.9** — i.e. *effectively the
entire calendar-2025 claim precedes the first sheet*; weighting/trading is
**`DATA_NEEDED`** (−12.5 .. +16.8, sign flips with weights and exit dates).

## 3. DATA_NEEDED — and the one ask that remains

Every `DATA_NEEDED` above carries the same minimal ask, so the "still yours"
list compresses to **one item**, and the ensemble affirms it genuinely
matters (it is not a formality — real conclusions flip inside the family):

> **Broker CSV export — every transaction (date, ticker, shares, fill, cash
> movement), Aug-2025 → Aug-2026. ~2 minutes.**
> Resolves: the as-traded covered return's sign (Q4), all three exit-cost
> magnitudes (Q3), the +115% weighting/trading share (Q1) — and, if it
> reaches back to mid-2025, replaces the gap parameter that currently
> supplies his entire headline with a measurement.

Nothing else on his record is worth asking for: cash level, exit dates,
weighting, APLT's collapse date and the QUBT arm all moved INSIDE the
ensemble without flipping any conclusion labelled robust above.

## 4. Rejection statistics (nothing hidden)

41,671 attempts rejected across 240 slots (accept rate ~0.5%, by design —
rejection sampling IS the consistency search): `cash_band_jan` 35,216 (the
0–30% cash band at the Jan sheet date is the binding constraint on cash
arrangements), `anchor7_end_level` 2,985, `cash_band_jul` 2,775,
`anchor7_gap_bounds` 301, `cash_infeasible` 197, `anchor9_end_level` 180,
`anchor9_gap_bounds` 11, `anchor8_gap_bounds` 6. Unfilled slots: 40, all in
anchor-7 arms — anchor 7 is the expensive one. One generator defect was
caught during the build by the accept-time re-validation (an ELF entry
deferring past the Jan sheet that lists it) — fixed before any production
run; the test suite pins the class.

## 5. What this may not do

- **Never enters** `murat_book.yaml`, `book_lanes.yaml`, the conviction log,
  any lane, ledger or NAV table. Output lives in this file,
  `docs/conviction_replay/transaction_ensemble_1.json`, and the member
  checkpoint (`transaction_ensemble_members_checkpoint.json` — raw rows,
  never quote one).
- **Trains nothing.** Members are bounds, not data.
- **CONVICTION-REPLAY-1's UNRESOLVED stands.** Nothing here measures
  selection skill against its pool; the 80-pt measured MDE still owns that
  question, and the 24-month forward-lane rule still owns any skill claim.
- **No member model escape:** conclusions are bounds on the stated family
  (constant-shares episodes, no external contributions). A history outside
  the family — e.g. mid-window deposits — could evade them; the broker CSV
  settles that too.
- The mutual consistency of {7,8,9} is **not** a verification of any of the
  three figures. It says only: no contradiction is provable from what the
  repo holds, provided the account roughly doubled before the record begins.
