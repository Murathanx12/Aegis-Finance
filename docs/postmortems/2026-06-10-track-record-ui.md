# Session Post-Mortem — 2026-06-10 (night) — P0 #2: Live Track-Record UI

## Context

V2_GOALS.md is now canon (installed into docs/ this session from Murat's
draft — A6 confirms observability-before-optimization). PROPOSALS verdicts:
#1 (UTC TTL), #4 (PI-scoped mypy), #5 (F841 sweep) approved → queued for the
next grind session; #2 (np.bool_) landed here as warm-up; #3 intent gaps →
first evolution-loop candidates (recorded in V2_GOALS Goal 2).

## What shipped

1. **`GET /api/pi/track-record`** — the canonical-record endpoint: all three
   lanes' real `paper_nav` series (per-point `config_version`), SPY/AGG/60-40
   overlays normalized to $100k at inception (60/40 = daily-rebalanced blend,
   labeled), freshness via `nav_freshness()`, and `intraday_date` when the
   latest row is today's still-re-marking mark. Benchmarks cached 30 min.
   Read-only; zero write-path changes.
2. **`/portfolio-intelligence/track-record` page** — lanes solid/colored,
   benchmarks muted-dashed underneath, inception ReferenceLine,
   config-change boundaries as labeled purple dashed lines, loud STALE
   banner when `all_fresh` is false ("treat the tail as missing, not flat"),
   intraday notice ("movement in the last point is the market, not noise"),
   per-lane summary cards with since-inception delta, 24-month no-skill-claims
   footnote. Linked as the first (canonical-badged) card on the PI landing.
3. **Warm-up (proposal #2):** `RegimeValidation` now casts numpy bools at the
   dataclass boundary.

## Decisions

- **Stale warning driven by the endpoint's own `all_fresh`** (same
  `nav_freshness()` source as `/api/health/full`) rather than a second
  health call — one fetch, no divergence between two freshness readings.
- **Benchmarks computed server-side** and normalized at inception — the
  frontend never computes finance; one endpoint feeds the page.
- **Intraday honesty as copy + flag, not visual trickery:** the moving
  last point is explained (re-marks hourly until 16:30 ET close) instead of
  being smoothed or hidden.
- Day-2 chart is sparse by construction; the page is built for the series it
  will become.

## Surprises / friction

- Disk cache outlives `cache_clear()` in tests — track-record tests patch
  `cache_get` for determinism (same class of issue as earlier sessions).
- recharts Tooltip formatter types: `(v: number, name: string)` fails the
  Next.js build; use untyped params + `Number(v ?? 0)`.
- `hasData &&` doesn't narrow `data` for TS — guard with `data && hasData`.

## Rejected approaches

- Driving the page from `/api/health/full` + `/history` × 3 lanes (4 calls,
  client-side merging) — one purpose-built endpoint is simpler and cacheable.
- Rendering benchmark MetricPacks from `/api/pi/compare` — that's the
  methodology page's data; mixing it into the canonical record would
  recreate the two-stories problem P0 #4 just fixed.

## Live verification (post-deploy, 2026-06-10)

Deployed at `277b238`. `GET /api/pi/track-record` on prod: `all_fresh: true`;
balanced lane 100,000 → 100,618.85 → 100,070.90 (06-08/09/10, all stamped
config `82be14cb…`); SPY overlay normalized correctly (100,000 → 99,706.45
on 06-09). Day-2 curiosity, NOT a claim: lanes are slightly up while SPY is
slightly down — meaningless at this sample size, which is exactly what the
page's 24-month footnote says.

## State for next session

- Ship: merged to main → auto-deploy; live verification above.
- Next on stack: **Step #2 leakage-safe optimization** (P0 #5) — first
  versioned config change; the segment-boundary rendering shipped here will
  visualize it. Grind queue: UTC TTL, PI mypy, F841 sweep.
