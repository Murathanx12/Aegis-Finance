# Next Session — Roadmap Position + Kickoff Prompt (written 2026-07-16)

## Where the V4 roadmap stands

| # | Chunk | Status |
|---|---|---|
| 1 | Screener/stock-page bug (NameError + numpy-serialization) | ✅ DONE, live-verified |
| 2 | Railway cost levers (FinBERT unload, off-hours warm, cache sweep, MALLOC_ARENA_MAX, close-only MTM) | ✅ DONE — **verify RAM drop in Railway Metrics ~2026-07-17** |
| 3 | Wall Street View (targets, ratings, firm actions) | ✅ DONE, live-verified |
| 3b | TRIAL-FORECAST-LEDGER (model vs street, registry #11) | ✅ ACCRUING, matures 2027-07 |
| — | Brain findings ledger (docs/KNOWLEDGE/findings.jsonl → lab prompts) | ✅ DONE, fact-checked |
| — | Collector honesty (GDELT stale-serve, Trends cooldown) + model-vs-firms card + next_runs | ✅ DONE, live-verified |
| — | Alpaca paper mirror (third-party NAV) | ✅ BUILT+DEPLOYED — **waiting on Murat: Railway env keys + one-boot seed flag** |
| 4 | Survivorship-free data (EODHD, $19.99/mo USD) | 🟡 Phase-1 PASSED 16/20 — **waiting on Murat: subscribe → run phase 2 → build loader** |
| 5 | Alpaca mirror seed + divergence monitoring live | 🟡 blocked on the env vars above |
| 6 | alphalens/quantstats rigor layer on lanes + PIT snapshots | ⬜ next build |
| 7 | Casual/advanced UI switch + driver.js first-run tour | ⬜ next build (biggest product chunk) |
| 8 | Screener presets ("Analyst Strong Buys" etc.) | ⬜ |
| 9 | FRED economic calendar card | ⬜ |
| 10 | Bull/bear two-sided card (DeepSeek live) | ⬜ |
| — | quantstats lane tearsheets + PyBroker bootstrap-CI pattern | ⬜ NEW top absorbs (2026-07-16 fact-check agent) |
| — | TRIAL-NN-1 (GKX-style net vs LightGBM) | ⛔ gated on survivorship-free panel |

Standing constraints: no new signals (6 clocks is the cap), no LLM near a
trade, no skill claims before 24 months, EODHD offline-validation-only.
Canonical knowledge: `docs/KNOWLEDGE/findings.jsonl` (15 fact-checked
findings). Full context: `docs/ROADMAP_V4_2026-07-16.md`,
`docs/research/DATA_SOURCES_AND_BASELINES_2026-07-16.md`, memory
`project_session_2026_07_16.md`.

## Murat's pre-session checklist (5 min)

1. Railway → Variables: `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`,
   `EODHD_API_TOKEN`; then ONE boot with `AEGIS_SEED_ALPACA_MIRROR=1`,
   verify, unset. (Rotate both keys afterward — they passed through chat.)
2. EODHD: upgrade to All World $19.99/mo when ready.
3. Glance at Railway Metrics → Memory (expect the 4.2 GB plateau down).

## Paste-ready kickoff prompt for the next Fable session

```
/go

This session finishes the V4 roadmap (docs/SESSION_PROMPT_NEXT.md has the
position table; docs/ROADMAP_V4_2026-07-16.md the detail). Work in this order:

PHASE 0 — verify yesterday's levers (30 min):
- aegis_verified_state: confirm the 16:30 ET close-only MTM stamped
  yesterday's NAV for all 7 lanes (next_runs + last_mtm), zero screener
  warnings, forecast-ledger collected on the last daily check.
- railway metrics: report RAM avg vs the 4.2 GB baseline (the $40 question).
- If I set the Alpaca env vars + seed flag: verify the seed
  (registry annotation alpaca-mirror-verification, orders placed,
  alpaca:equity PIT row), then remind me to unset the flag.
- If I set EODHD_API_TOKEN + subscribed: run
  python -m engine.research.eodhd_acceptance --phase 2 (bar >=16/20) and
  report PASS/FAIL. On PASS: design the eodhd_loader (engine/research only,
  offline validation ONLY — personal license, nothing EODHD-derived on the
  public site).

PHASE 1 — compare & absorb FIRST (before building):
- Launch research agents to find and analyze 3-5 MORE projects/firms we
  haven't covered (already done — do NOT redo: Vibe-Trading, qlib,
  RD-Agent, FinGPT, ML4T, alphalens, OpenBB, gs-quant, quantstats, skfolio,
  vectorbt, PyBroker, FinRL, TradingAgents, FinMem, FinCon). Angles worth
  hunting: portfolio-advice UX for novices (retail robo-advisors' risk
  questionnaires), open banking/brokerage aggregation, factor-lens tools
  (Portfolio Visualizer's feature set), anything doing honest uncertainty
  display. Fact-check anything that will be cited. Fold verdicts into
  docs/ROADMAP_V4_2026-07-16.md and docs/KNOWLEDGE/findings.jsonl (same
  commit as evidence).

PHASE 2 — finish the roadmap chunks, in order, each with tests + CI green +
verify-prod-after-deploy on the changed surface (cache-busted):
1. quantstats HTML tearsheets per paper lane (from paper_nav; skip its
   yfinance utilities) + PyBroker-style BCa bootstrap CIs on lane
   Sharpe/Sortino/maxDD ("Sharpe 1.1 [95% CI: 0.2-1.9]").
2. Casual/advanced UI switch (localStorage, casual default; advanced =
   the dense analytics surfaces) + driver.js first-run tour (MIT; ~6 coach
   marks max, skippable, never forced).
3. Screener presets (Analyst Strong Buys / High dividend safety / Momentum
   leaders) — filters over the existing screener payload.
4. FRED economic calendar card (Actual/Forecast-trend/Previous +
   importance stars; economic_surprise service already computes the core).
5. Bull/bear two-sided card (DeepSeek under existing spend guards; argues
   both sides of the COMPUTED signal; numeric signal untouched; no
   buy/sell language).
6. If phase-2 EODHD passed: eodhd_loader + rerun survivorship_audit
   against it + a PIT-safe delisted-inclusive panel schema; then draft
   (do NOT run) the TRIAL-NN-1 pre-registration for my review.

PHASE 3 — close-out (mandatory, budget 45 min for it):
- Rerun the full fast suite + PI suite; lane-integrity check if anything
  touched the lane path.
- Audit ALL work done across V4 (git log since fb21378 + the roadmap
  table): what shipped, what's verified live, what's still open.
- Write docs/V4_CLOSEOUT.md: what's next, what we LACK (be adversarial —
  gaps in validation, product, data, trust), what needs to be done, and
  the next session's kickoff prompt (this same pattern).
- Update memory + MEMORY.md.

Discipline unchanged: pre-register before anything accrues; six forward
clocks is the CAP (no new signals); no LLM near a trade path; EODHD
offline-only; read docs/KNOWLEDGE/findings.jsonl before proposing
hypotheses; every deploy CI-gated + live-verified on the changed module.
```
