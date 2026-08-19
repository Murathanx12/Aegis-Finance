# THE 14-POINT GAP — RESOLVED (2026-08-19, positions read via deployed endpoint)

Three sessions of refusals ("no rule mechanism may be quoted as the cause")
ended today because the refusals were correct: none of the circulating
mechanisms was the cause. The books were never corrupted and no rule
"lost" 14 points. Two measurement artifacts stacked:

## 1. The books are CORRECT (the read was finally possible)

`paper_positions` uses `closed_at IS NULL` liveness; rebalances close old
lots and open new ones. Both lanes' open books reprice to their
authoritative NAVs within cash tolerance:

- mirror: NAV 82,553 vs open-book equity 79,888 (−3.2%, ≈ cash sleeve)
- conviction: NAV 97,289 vs open-book equity 93,107 (−4.3%)

(The endpoint's FIRST read looked like every name was duplicated — that
was the endpoint missing the `closed_at` filter, fixed same hour. A
property of the extraction, not the data.)

## 2. The NAV date rows LAG the market by one day

`corr(NAV_t, book-close_{t−1})` = **+0.974** (conviction) / +0.78 (mirror)
vs ~0 at lag 0. Mechanism, located in code:
`reference_engine._get_current_prices` returns `series.iloc[-1]` of a
DAILY-bar fetch (which, at the 16:30 ET mark and behind the shared
15min–1hr cache, is routinely the PREVIOUS session's close), while
`mark_lane_to_market` stamps the row `date.today()`. So a NAV row dated t
usually carries close(t−1). Every lane shifts together — relative lane
comparisons were unaffected, which is why 72 days of freshness canaries
never saw it; only same-day replay comparisons did, as "unreconcilable"
divergence jumps.

## 3. What the "gap" actually was

- The −17% mirror lane is the REAL performance of its live HRP book over
  its 12 smallcap names, marked one day late but marked correctly.
- "Its own rules replayed +13.9%" (cross-arms cell) was computed on the
  YAML-SEED book from a different start date — a different portfolio. The
  comparison the reviews were arguing about was never like-for-like, which
  is exactly what the cross-arms script's refusal said, without yet being
  able to say why.
- The "accounting jump days" (06-24/07-14/07-17/07-30/08-10) are the
  booking events (seed → decision-log application → re-books) seen through
  a one-day-shifted lens.

## Write-path patch sketch (ATTENDED — not applied; CANON §5)

The honest fix is one semantic change in `mark_lane_to_market`:
stamp the NAV row with **the price bar's own date** (`series.index[-1]`),
not `date.today()`; the freshness canary then expects bar-date semantics
(fresh = last completed session, which is what the data actually is).
Alternative (bigger): fetch true live quotes at mark time. Either changes
the sacred write path ⇒ Murat's call, proposed as P-day-2026-08-19a in
PROPOSALS.md. Historical rows need NO rewrite — the offset is uniform and
documented; rewriting history would be worse than annotating it.

## Standing consequences

- Same-day comparisons of lane NAV against market closes are off by one
  day; any future replay/autopsy must align on `NAV_t ↔ close_{t−1}`
  until the stamp is fixed (the cross-arms and reconcile scripts now
  document this).
- `nav.all_fresh` is one day more optimistic than the data it certifies.
- The §16/§59 questions about the mirror book's economics are now OPEN and
  answerable: the book is real, the marks are real (shifted), and the
  right comparison is lane-vs-lane (shared lag cancels).
