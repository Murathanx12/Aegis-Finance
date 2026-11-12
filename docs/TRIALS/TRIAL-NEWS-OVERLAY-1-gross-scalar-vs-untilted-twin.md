# TRIAL-NEWS-OVERLAY-1: news risk-overlay gross scalar vs its untilted twin (CH-14b)

- **Licence:** PRODUCT_EXPERIMENT (internal simulation only: no broker, no order, no LLM authority).
  No significance gate and no preregistration are required for this licence; the four never-relax
  rules hold (public-before-use, no target leakage, costs never omitted, frozen once forward).
- **Contract (current):** `docs/TRIALS/CONTRACT_NEWS_OVERLAY_v3.json`, **`policy_hash c777f997289240e4`**
  (pinned by `backend/tests/test_news_overlay_book.py::test_the_committed_contract_is_the_rule_in_code`;
  `test_v3_keeps_every_v2_mapping_parameter` pins that only the base changed).
- **v3 (2026-11-12, after PR #125):** same mapping and timing as v2; new base **LIQUID-RANDOM-50**
  (derived from the bars panel, never stored: on the first XNYS session D of each month, 50 names drawn by
  `paper_books._draw` with a recorded seed int(sha256("20261112:D")[:8], 16) from names with median
  63-session dollar volume >= $50M, price >= $5, >= 252 bars, newest bar <= 3 sessions old, no
  SUSPECT_CORPORATE_ACTION in 252 sessions, not an ETF; all from bars strictly before D; equal weight at D's
  close). Why random: CH-11 showed the strategy books are mostly one bet and the volatility band explains
  their results; a random liquid base isolates how much is held. It is not a strategy. A second base,
  **SPY alone, is for comparison only** and never graded. Stale base bars now REFUSE the day at 1.0
  (STALE_BASE_BARS) when > 10% of base weight is on names with a newest bar > 5 sessions old (v2 only
  flagged). v2 `2d85fa126b83f4ac` was superseded because its base was unreadable (30 of 32 replay days
  on stale bars, a probable unadjusted split as its largest loss). Bases tried = 2; tone mapping declared
  once (v2's MAPPINGS_TRIED = 2 counts its age bound and is kept). The v2 replay had been seen before v3.
- **Contract v2 (superseded):** `docs/TRIALS/CONTRACT_NEWS_OVERLAY_v2.json`, `policy_hash 2d85fa126b83f4ac`.
- **History:** v1 `ce686058847fdbc7` (`CONTRACT_NEWS_OVERLAY_v1.json`, declared 2026-11-12T09:13Z, replay
  `20261112T091714Z`) was superseded the same day by the review of PR #125: unbounded baseline age, a
  missed session held the last scalar, the forward step dated sessions by the machine's local date, no
  early-close handling. v1 was never seeded. The reason is kept inside the v2 contract (`history`).
- **Disclosure (also in the contract):** mappings tried = 2 (v1, and v2 = v1 + the baseline-age bound,
  chosen from a reviewer's correctness finding, not from returns). The range of the tone input
  (about -0.21 .. +0.05) had been seen before SLOPE and DEADBAND were chosen; no return had been seen.
- **Base book (v1/v2 only):** `book:9d62cc74239b435d` (random_universe twin of the BHJ book; 50 names EW
  from the US $3M+ dollar-volume band, monthly, 5+1 bps per side). Replaced in v3 by LIQUID-RANDOM-50.
- **Twin:** the same book at scalar 1.0 (identical names, relative weights, re-target moments, costs).
- **Rule:** F = source-weighted mean `themes[].tone.fear_greed` of the newest world digest stamped
  strictly before min(15:30 ET, close - 30 min) on XNYS session t; B = median F of the previous 12 valid
  digests no older than 7 days before it (>= 4 needed); d = F - B; raw = 1 - 5 x max(0, -d - 0.02);
  scalar = clip(round to 0.05, 0.5, 1.0). Stale (> 36 h), empty (< 3 toned themes), no-digest or
  baseline-less -> 1.0, named. Fill = close of t.
- **Forward path:** one `step` per session inside 15:30-16:00 ET (America/New_York date; refuses a
  non-session day or a run outside the window); `--date` other than today's ET session = BACKDATED,
  never graded; one FORWARD row per session. `grade`: FORWARD rows only; a session with no row = 1.0
  (NO_DECISION_ROW); a base holding with no real bar for > 5 sessions marks the day DEGRADED.
- **Objective:** terminal NAV of overlay vs twin (BALANCED personality), same notional and costs; read
  daily, by date block, raw lines first.
- **Status:** BUILT, NOT SEEDED. `NEWS_OVERLAY_BOOK_ENABLED` (env `AEGIS_NEWS_OVERLAY_BOOK=1`) is off.
  Forward evidence starts only at the attended seed; the replays are BACKFILL, not forward evidence.
