# TRIAL-NEWS-OVERLAY-1: news risk-overlay gross scalar vs its untilted twin (CH-14b)

- **Licence:** PRODUCT_EXPERIMENT (internal simulation only: no broker, no order, no LLM authority).
  No significance gate and no preregistration are required for this licence; the four never-relax
  rules hold (public-before-use, no target leakage, costs never omitted, frozen once forward).
- **Contract:** `docs/TRIALS/CONTRACT_NEWS_OVERLAY_v1.json`, `policy_hash ce686058847fdbc7`
  (pinned by `backend/tests/test_news_overlay_book.py::test_the_committed_contract_is_the_rule_in_code`).
- **Mapping declared:** 2026-11-12T09:13Z in `backend/config.py` (`NEWS_OVERLAY_*`), committed in
  `225a3afa` before the first replay (run `20261112T091714Z`). Mappings tried: 1.
- **Base book:** `book:9d62cc74239b435d` (random_universe twin of the BHJ book; 50 names EW from the
  US $3M+ dollar-volume band, monthly, 5+1 bps per side).
- **Twin:** the same book at scalar 1.0 (identical names, relative weights, re-target moments, costs).
- **Rule:** F = source-weighted mean `themes[].tone.fear_greed` of the newest world digest stamped
  strictly before 15:30 ET on session t; B = median F of the previous 12 valid digests (>= 4 needed);
  d = F - B; raw = 1 - 5 x max(0, -d - 0.02); scalar = clip(round to 0.05, 0.5, 1.0). Stale (> 36 h),
  empty (< 3 toned themes), or baseline-less digests give 1.0 with a named degradation. Fill = close of t.
- **Objective:** terminal NAV of overlay vs twin (BALANCED personality), same notional and costs; read
  daily, by date block, raw lines first.
- **Status:** BUILT, NOT SEEDED. `NEWS_OVERLAY_BOOK_ENABLED = False`. Forward evidence starts only at the
  attended seed; the 2026-11-12 replay is BACKFILL and is not forward evidence.
