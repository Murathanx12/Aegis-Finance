# Postmortem: the NAV re-book defect (2026-06-10 → 2026-07-26)

**Severity:** P0 — track-record integrity (CANON §5 territory).
**Found:** 2026-07-26, attended session with Murat, during seed-a-lane due
diligence for the TSMOM-XA lane (reading the rebalance write path before
mirroring it).
**Fixed:** commit `36c8ece` (write path) + `AEGIS_RECONSTRUCT_NAV=1` attended
one-boot reconstruction (archive + splice + open-book rescale).

## What happened

`_get_portfolio_notional` returned the static `inception_value` ($100k), and
nothing in the codebase ever updated that column. Every non-initialization
rebalance — monthly/weekly cadence, drift, config-change, conviction
decisions, ATR overlay — closed the open book and re-opened it at
$100k − costs. The lane's NAV teleported toward inception at every rebalance
boundary; gains and losses were erased instead of compounding.

## The receipts (prod, before the fix)

- **2026-07-09** (SPY **+0.85%**, QQQ +1.66%): the day after their 07-08
  rebalances, aggressive "fell" **−2.79%** (from 102,017 — its +2.0% erased)
  and balanced "fell" −1.45%. Impossible as market moves.
- **2026-07-16**: aggressive "gained" **+1.26%** (98,890 → 100,138) the day
  after its 07-15 rebalance while balanced (no rebalance) moved +0.16% —
  pulled UP toward $100k from below. Markets don't mean-revert your NAV to
  your inception value; a fixed-notional re-book does exactly that, from
  both directions.
- Since-inception figures were effectively "return since last rebalance."
  Blast radius: every lane except smallmid-quality (buy-and-hold, never
  rebalanced). Conviction (12 decision re-books) most affected.

## Why tests didn't catch it

735 PI tests were green throughout. No test pinned the invariant "a rebalance
is value-neutral except costs" — every rebalance test asserted weights,
events, and position rewrites, not value conservation across the boundary.
The function's docstring said "current notional value," so every reviewer
(human and model) read the call sites as correct. The 2026-06-11 audit that
created `_apply_rebalance_positions` fixed *positions not being rewritten* —
and baked in the wrong notional while doing it.

## Why it was findable today

Reading the write path before building on it (seed-a-lane step 3) + live NAV
vs real market moves. The tell was cross-lane: a lane's post-rebalance day
return was inconsistent with both the market and its unrebalanced siblings.

## The fix

1. `36c8ece`: rebalances re-book at the open book's CURRENT marked value
   (shares × live price, cost_basis fallback, CASH at par); inception_value
   only before first build. 8 regression tests pin value-neutrality.
2. `paper_nav` history reconstruction (attended, env-gated, idempotent):
   between-boundary marks were always honest, and a re-book only mis-scaled
   notional, so the true chain = booked chain × per-boundary factor
   k = (last honest mark before the reset)/100k, compounded. Originals
   archived byte-for-byte in `paper_nav_archive_20260726`; open books
   rescaled by the cumulative factor so future MTM continues the corrected
   chain. Residual error: cost second-order terms + one ambiguous-band
   boundary class (documented in `nav_reconstruction.py`), bounded at bps.
3. NAV rows now stamp the lane's OWN config_version (`24fb250`) — the
   2026-07-24 finding (b), same family: shared write path assuming the
   reference lanes are the world.

## Lessons

- **A sacred write path needs its invariants as tests, not as reviews.** The
  value-neutrality invariant existed in everyone's head and nowhere in CI.
- **NAV series should be reconciled against market moves routinely** — a
  daily "lane return vs holdings-implied return" residual check would have
  caught this on 2026-06-11. (Follow-up candidate: wire it into
  `nav_freshness` as a residual alarm.)
- **since_inception_pct was the headline number on every surface** and it
  was wrong for 7 weeks. Cross-checking one lane's curve against SPY on one
  suspicious day was all it took — do it whenever a curve looks odd.
- The forward clocks survive: inceptions and daily marks are real; the
  corrected chain preserves the full 48-day record with an auditable trail.
