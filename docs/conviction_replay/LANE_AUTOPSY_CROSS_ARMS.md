# LANE-AUTOPSY CROSS-ARMS — the reconciliation failed, and that IS the finding

2026-08-18 night (grind, `lab/autonomous-rd`). Receipt:
`cross_arms_1.json` · prod NAV snapshot:
`track_record_snapshot_2026-08-18.json` (read-only GET, provenance-stamped).
Runner: `scripts/lane_autopsy_cross_arms.py` — hermetic
(`conviction_prices.csv`), both window starts, reconciliation before any
economic sentence, per Order 20 §5.

## 1. The reconciliation Order 20 demanded — FAILED, informatively

Buy-and-hold of the YAML seed (12 names, seeded at authoritative inception
2026-06-16 at NAV 100,041.38) does **not** reproduce the authoritative
conviction curve: max |divergence| **11.23%**, mean 3.75%, against a declared
2% tolerance. The divergence arrives in **discrete jumps**, not a drift:

| date | divergence jump | plausible cause (unverified) |
|---|---|---|
| 2026-07-30 | **+11.68%** | the 2026-07-26 NAV re-book correction (`nav_reconstruction.py`, multiplicative) |
| 2026-07-14 | +7.54% | the decision log's 12 `enter` rows are dated 2026-07-11, `late_entry: true` |
| 2026-06-24 | +6.93% | unknown — predates both |

A steady drift would implicate the price source; jumps implicate **discrete
events the YAML-seed reconstruction does not model** — decisions, re-books,
accounting. Conclusion: *the authoritative conviction path is not
buy-and-hold of the current YAML book*, and no rules replay on that book can
be reconciled against either live lane without the recorded positions.

**The missing input is `paper_positions` / `rebalance_events` for `mirror`
and `conviction`.** They exist only in the prod volume DB and are not
exposed by any API (`/api/pi/reference/{lane}/history` 404s for book lanes).
Reading them is an attended `lane-integrity-check` item — queued for Murat.

## 2. What the factorial DOES establish (rules on these prices, not lanes)

Both lanes hold the same book, so the cross-arms are
{seed weights, equal weights} × {never, monthly}, plus the full mirror rules.
Authoritative window (2026-06-16 → 2026-08-10, 38 rows):

| cell | total | rebalances | turnover |
|---|---:|---:|---:|
| conviction (seed × never) | +2.92% | 0 | 0.000 |
| EW at seed × never | +6.19% | 0 | 0.348 |
| seed weights × monthly | +5.19% | 2 | 0.452 |
| EW × monthly | +7.44% | 2 | 0.732 |
| mirror rules (full) | **+10.27%** | 3 | 0.806 |

- Every managed cell beats seed-hold on this book and window; **ordering is
  stable across both window starts** (the Order 18 replay's 2026-06-08 start
  predates authoritative inception by 8 days and shifts cells by ±3.6%
  without flipping any ordering — the window artifact is real but small).
- The diagonal separates the two EW claims: **EW-at-seed** (+3.3pp over
  seed-hold) carries most of the weighting effect; **monthly re-equalisation
  adds ~+1.3pp more** on this window. Bet-sizing at seed, not
  winner-selling, is the larger term here.
- 70 days, 12 names, one window: mechanism attribution only, no verdicts.

## 3. The contradiction, resolved into a sharper question

The live lanes say mirror −16.8% vs conviction −2.6% (rules-managed lane 14
points BEHIND). The rules replay says mirror rules +10.27% vs seed-hold
+2.92% on the same book (rules AHEAD). Both are true statements about
**different objects**: the live mirror lane's recorded path differs from its
own rules replayed on the current book by **~27 points**, which no window
artifact explains. Candidate causes, decidable only from positions:
composition at seed differing from today's YAML book, the June drawdown
(live mirror lost ~9.5% by 06-30 while conviction gained ~6.6%), the re-book
correction, decision-log timing.

**Until the positions read happens, "the 14-point gap is EQUAL WEIGHT, not
HRP" is UNRECONCILED and may not be quoted as a fact about the live lanes.**

## 4. Erratum to the 08-18 adjudication (B1) — mine

Adjudication B1 rejected reviewer B's Ledoit-Wolf remedy partly on the
ground that "the equal-weighted arm is the one 14 points behind." That
sentence quoted the live lanes as if the gap's mechanism attribution were
settled; this replay shows the live gap is not currently attributable to any
rule mechanism at all. The **rejection stands** — no covariance estimate ran
(HRP's 252-day gate fell back to equal weight), so shrinkage still targets a
nonexistent computation — but the supporting sentence overstated what was
reconciled, in the same way Order 18's opposite-sign sentence did. Both
readings of the gap were premature; the positions read decides.

— grind, 2026-08-18 night
