# PREREG — CONVEXITY-CRSP-REPLICATION-1 (design FROZEN pre-parent-read)

SIGNED-BY: (unsigned — queued; design frozen 2026-08-19)

**Status: DESIGN FROZEN 2026-08-19, deliberately BEFORE the parent
CONVEXITY-PRESERVATION-1's registered result was read.** Purpose of the
early freeze: if the 182-name large-cap result is dramatic in either
direction, this replication cannot be unconsciously redesigned to
reproduce or soften it. Committed by content hash in git history at the
freeze commit; any post-freeze edit to the frozen section below is an
amendment and says so.

## FROZEN PROTOCOL (no edits after the parent result is read)

- **Parent:** `PREREG_CONVEXITY_PRESERVATION_1.md` (as amended, Amendment 1).
- **Question, unchanged:** does the daily-close 20% trailing exit
  (`close_trail_20`) destroy per-dollar terminal wealth vs `hold` on
  +40-crossing winners? Same 60-trading-day outcome horizon. Same arms.
- **Universe:** the CRSP PIT panel (`crsp_pit_universe_pull.py` substrate:
  shrcd 10/11, exchcd 1–3, price ≥ $5, monthly $vol ≥ $100M, monthly
  membership as of each crossing date, PERMNO identity). **Delistings
  included:** a delisting inside an episode's window terminates the path
  at the delist-return-adjusted value (dlret compounded, CRSP dsedelist);
  a delisting is an OUTCOME, never an exclusion.
- **Sample window:** crossings 2013-01 .. 2024-08 (episode end + 60
  trading days must complete before the entitled vintage ends 2024-12-31).
- **Decision rule:** identical to the parent as amended — three-way
  verdict, Holm across the m = 5 non-hold arms, economic margin 0.005
  (NEVER shrunk), one-sided noninferiority
  (lower 90% CI of stop − hold > −0.005).
- **Dependence:** `bootstrap_block_dates(dates, OUTCOME_DAYS)` on THIS
  panel's own crossing-date spacing. No hardcoded block.
- **§64 gate:** the mean-masked exact-primary power audit runs FIRST; each
  verdict limb is declared ANSWERABLE / NOT_ANSWERABLE_AT_N at
  reservation, before any aggregate read.
- **Costs:** per-name measured TAQ one-way where a calibration exists for
  the PERMNO's ticker; otherwise a declared 10 bp one-way band (CRSP
  breadth reaches far less liquid names than the 182 large caps — the
  band is deliberately wider than the parent's 3 bp).
- **No tuning between universes:** arm definitions, thresholds, matching
  caliper, horizon and margins are byte-identical to the parent. If the
  two universes disagree, the disagreement IS the finding (§60 slice
  identity) — it is reported, not reconciled by re-specification.
- **May not:** promote non-declared cells (§37); quote large-cap base
  rates as market base rates or vice versa; feed any lane or surface
  (§61 cap ADAPTIVE_HISTORICAL_VALIDATION).

## Runbook (mechanical, non-frozen)

1. Materialize CRSP episodes with the parent's builder pointed at the PIT
   panel (PERMNO join via `security_identity`).
2. Run the masked power audit; record answerability per limb.
3. Present for signature with the audit receipt. Run only when signed.

— frozen 2026-08-19 15:1x HKT, parent result unread at freeze time
