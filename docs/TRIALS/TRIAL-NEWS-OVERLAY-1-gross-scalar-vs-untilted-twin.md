# TRIAL-NEWS-OVERLAY-1: news risk-overlay gross scalar vs its untilted twin (CH-14b)

- **Licence:** PRODUCT_EXPERIMENT (internal simulation only: no broker, no order, no LLM authority).
  No significance gate and no preregistration are required for this licence; the four never-relax
  rules hold (public-before-use, no target leakage, costs never omitted, frozen once forward).
- **Contract (current):** `docs/TRIALS/CONTRACT_NEWS_OVERLAY_v2.json`, **`policy_hash 2d85fa126b83f4ac`**
  (pinned by `backend/tests/test_news_overlay_book.py::test_the_committed_contract_is_the_rule_in_code`).
- **History:** v1 `ce686058847fdbc7` (`CONTRACT_NEWS_OVERLAY_v1.json`, declared 2026-11-12T09:13Z, replay
  `20261112T091714Z`) was superseded the same day by the review of PR #125: unbounded baseline age, a
  missed session held the last scalar, the forward step dated sessions by the machine's local date, no
  early-close handling. v1 was never seeded. The reason is kept inside the v2 contract (`history`).
- **Disclosure (also in the contract):** mappings tried = 2 (v1, and v2 = v1 + the baseline-age bound,
  chosen from a reviewer's correctness finding, not from returns). The range of the tone input
  (about -0.21 .. +0.05) had been seen before SLOPE and DEADBAND were chosen; no return had been seen.
- **Base book:** `book:9d62cc74239b435d` (random_universe twin of the BHJ book; 50 names EW from the
  US $3M+ dollar-volume band, monthly, 5+1 bps per side). Small-cap inclusive and noisy; a macro-tone
  overlay may be swamped by it.
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
