# Next Session — V5 kickoff (updated 2026-07-18)

**NEW: `docs/ROADMAP_V5_2026-07-18.md` is the V5 plan of record.** EODHD
Phase 1 gate PASSED 16/20 (subscribe justified); Alpaca paper account
verified ACTIVE ($100k, unseeded). Next session starts at Chunk 1 (Phase 2
acceptance with the paid token), then loader → honest replay → QuantConnect.

---


**V4 is CLOSED.** The full audit — what shipped, what's live-verified, the
adversarial gap list (validation / product / data / trust), Murat's
5-minute checklist, and the paste-ready V5 kickoff prompt — lives in
**`docs/V4_CLOSEOUT.md`**. Use the prompt at the bottom of that file to
start the next session.

Short position summary:
- All V4 build chunks shipped 2026-07-16/17 (commits `f935df1`..`bfbf1ca`),
  each CI-gated; congress-IC quota fix live-verified; chunks 1-5 deployed
  behind the CI queue at close-out — next session's Phase 0 live-verifies
  their surfaces.
- Blocked on Murat: Alpaca seed keys, EODHD subscription (phase 2), FMP key
  rotation (leaked to logs), tour/casual-mode eyeball, RAM glance.
- Knowledge base: `docs/KNOWLEDGE/findings.jsonl` now has 20 fact-checked
  findings (F-016..F-020 added 2026-07-17: FMP-quota incident + compare-round
  2 verdicts on robo UX, factor-lens, uncertainty display, aggregation).
- V5 leverage order: EODHD panel → F-019 uncertainty playbook on the
  track-record page → factor-lens presentation → FMP budget ledger →
  builder absorbs.

Standing constraints unchanged: six forward clocks is the cap, no LLM near a
trade, no skill claims before 24 months, EODHD offline-validation-only.
