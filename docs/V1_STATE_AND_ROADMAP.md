# V1 — State and Roadmap (2026-07-08)

> Consolidated "where we are, what's live, and what the four branches are."
> Generated from ground truth: `aegis_verified_state` (live prod), the
> experiment registry, BACKLOG.md, STATE_OF_THE_REPO.md, NEGATIVE_RESULTS.md,
> INTEGRITY_STATUS.md, all postmortems and TRIALS, and the 2026-06-20
> research/audit deliverables. Guardrails live in [`CANON.md`](./CANON.md);
> external references in [`../REFERENCES.md`](../REFERENCES.md).
> **Branch work does not start until Murat has reviewed this doc, CANON.md,
> and REFERENCES.md.**

---

## 1. Where we are (verified live, 2026-07-08)

- **Prod (Railway):** commit `0e329e2`, v0.2.0, up since 2026-06-18, scheduler
  running (daily check / hourly MTM / weekly aggressive), cache ready.
- **Forward track record:** inception **2026-06-08, now 30 days old**. All
  **7 lanes fresh** (`nav.all_fresh: true`):

  | Lane | NAV | Since inception | What it tests |
  |---|---|---|---|
  | conservative | 100,132 | +0.13% | reference mandate |
  | balanced (HRP) | 100,607 | +0.61% | TRIAL-001 arm |
  | balanced-ew-control | 100,126 | +0.13% | TRIAL-001 control |
  | aggressive | 101,591 | +1.59% | reference mandate |
  | mirror | 91,553 | −8.45% | TRIAL-002: rules on Murat's book |
  | conviction | 105,527 | +5.53% | TRIAL-003: Murat's decisions |
  | conservative-atr | (accruing) | — | TRIAL-EXIT: ATR exit overlay |

  **No conclusions from any of this — 24-month discipline.** (The conviction
  +5.5% vs mirror −8.4% spread on a ~12-name book at 30 days is noise by
  construction.)
- **Registry:** 6 trials, 0 rejected-yet, all pre-registered with decision
  rules (earliest decision on TRIAL-001: 2027-06-10). Three forward-IC trials
  (insider T9, revisions T10, multifactor T8) wired and accruing weekly PIT
  snapshots; IC measurement pending a matured forward window.
- **Fragility read:** all quiet (LPPLS 0.0 / no bubble; composite descriptive,
  never arms). Crash overlay **DARK by design** on prod.
- **Data sources:** yfinance 100% batch success; FRED 23/23 series loading.
- **Integrity:** no 🔴 known-bypass remains (INTEGRITY_STATUS.md); fast test
  suite ~2500 offline + un-hangable; PI suite 517+ green.

### ⚠ Two live issues found in this orientation pass

1. **Local `main` is 20 commits ahead of `origin/main` — the entire V3
   build sprint is UNDEPLOYED.** Prod is missing: the M3 crash-model artifact
   fix + provenance sidecar (which is *why* prod overlay still says
   `model_not_deployed` — the fixed artifact returns `status=evaluated`
   locally), the data-integrity gate, forward-IC scorecard, exposure
   multiplier, cross-asset rotation core, the F1/F2/F3/B2/B5 integrity fixes,
   and all AFK-audit docs. **First action of the next work session: review +
   push, verify deploy via `aegis_verified_state`.**
2. **`detect_regime` import failure in prod** since 2026-07-01:
   `reference_engine` logs `cannot import name 'detect_regime' from
   backend.services.regime_detector` on daily checks — the reference lanes'
   regime fetch silently degrades. Small fix, but it's the silent-fragility
   class (CANON §8): diagnose, fix, and add the canary.

Also pending on Murat: unset `AEGIS_SEED_CONSERVATIVE_ATR` (seed is idempotent
but attended discipline says unset); Optimus brain re-ingest after the push
(corpus currently fresh at `cb01d8b`, 15 commits behind local).

## 2. What is built — do not rebuild

- **The honesty spine (the moat):** forward `paper_nav` (7 lanes, uncopyable),
  experiment registry with DSR/PBO/effective-N adoption gate (never
  auto-adopt), pre-registered TRIALS with tamper-evident git timestamps,
  TRACK_RECORD_POLICY + methodology banners, NEGATIVE_RESULTS published,
  INTEGRITY_STATUS dashboard, data-integrity gate (directional vs
  sizing-grade), PIT data layer (`pit_observations`, schema v7, leak-free
  reads), Optimus MCP (verified-state / canon / registry / postmortems /
  brain).
- **The engine surface (~104 services):** crash model (artifact fixed +
  provenanced, still non-discriminating → DARK), fragility composite
  (descriptive, as-of bound, exposure multiplier), Monte Carlo, HRP/BL/CVaR
  portfolio construction, factor models (FF5+Mom), exit engine (ATR
  Chandelier, vol-target, Kelly), signal engine, screener, options/earnings/
  insider/news intelligence, macro dashboard, and the long tail —
  classification in CAPABILITY_MATRIX.md (~5 validated, ~10+ descriptive
  groups, ~60 unaudited).
- **Forward measurement instruments:** conviction decision capture
  (endpoint + CLI, immutable log), book-lane active management (Plan 3, wired
  into `_daily_check`), forward-IC collectors (insider / revisions /
  multifactor, weekly, SEC rate-limiter hardened), forward-IC scorecard
  reader, `brier_with_ci`.
- **Frontend:** Next.js 14 dashboard (12+ pages) incl. track-record equity
  curve; deployed on Vercel.

## 3. What we know that constrains everything (measured, closed)

See CANON.md for the full list. The load-bearing four:
1. **T7:** survivorship-free backtests are impossible on free data → selection
   signals validate **forward only**.
2. **Profit mirage:** LLM/brain strategies are never backtested — the
   conviction lane is the only honest test of "pick the future early."
3. **Crash timing ≈ 0 IC** → fragility (descriptive, exposure-scaling) is the
   surviving form of the instinct.
4. **Silent fragility** is the house failure mode → live prod verification
   after every deploy, fail-loud everywhere.

## 4. The four branches of V1

### Branch 1 — Core: engine + Optimus
*The engine does the thinking for an average investor; Optimus makes every
session smarter than the last.*

Open work, in leverage order:
1. **Ship the sprint:** push the 20 commits, verify live, fix `detect_regime`,
   re-ingest the brain. (Everything else is blocked on a clean deploy.)
2. **Crash-model discrimination** (own chunk, gated): current model outputs
   ~0.066 in every regime (val AUC=nan, sparse events). Richer labels /
   features / walk-forward AUC ≥ 0.70 before it is even a candidate; arming
   only ever on a new pre-registered lane.
3. **Fragility candidate inputs as registered trials** (BACKLOG V1/B9): IPO
   froth, VIX term structure, put-skew, CAPE/ERP, concentration, margin debt,
   extra FRED credit series — each clears a forward bench or ships descriptive.
4. **Hardening backlog:** B1 (NaN composite producer), B6, B10, H5 swallower
   audit (~70 sites), H2 lockfile, H1 untrack lab scratch.
5. **Optimus deepening (V5):** postmortem auto-distill (the deferred LLM
   layer), **calibration memory** — every brain/conviction call stored with
   its forward outcome so the brain gets its own reliability curve. This is
   the honest version of "it stores what worked and trains itself":
   process memory + graded forward calls, never P&L training (CANON prime rule).

### Branch 2 — Paper accounts + informed money
*Invest like an investor, not a day-trader (day-trading: closed, BACKLOG V4).
The lanes are the racers; more pre-registered hypotheses = faster learning,
honestly.*

1. **Log conviction decisions** — Murat's #1 next-session focus. The seeded
   conviction lane is the only forward test of his stock-picking; it needs his
   decisions flowing through the capture endpoint/CLI (and a low-friction UI).
2. **Let the IC clocks accrue** (T8/T9/T10) and surface the forward-IC
   scorecard once windows mature; widen the 12-name cross-section.
3. **Informed-money data, API-first, in evidence order** (V3 data priorities):
   insider Form 4 clusters (✅ wired) → **13F collector scheduling** (built,
   unscheduled; descriptive, 45-day lag) → **congressional trading** (new API:
   Quiver Quantitative or Capitol Trades; strictly descriptive, disclosure-lag
   labeled) → options positioning → breadth/sentiment.
4. **V4 alert engine + event-driven lane:** rules table evaluated each
   scheduler tick, Telegram/Discord delivery, risk-awareness framing; then a
   new pre-registered lane that *acts on the alerts* — the forward answer to
   "does acting on Aegis beat ignoring it."
5. **"Train on past data" — the honest form:** replay/backtest stays a
   direction-check guillotine (kills bad rules, proves none); what compounds
   is the registry + postmortems + forward records. No RL on P&L (CANON §4).

### Branch 3 — Reference / benchmark
*Compare Aegis to the field; mine patterns, keep the spine.*

1. ✅ REFERENCES.md written (this session) — the catalog + license policy.
2. **Pattern adoption chunks:** quantstats tearsheets for lanes (B7), Qlib
   PIT-schema hardening (B8), LangAlpha data-tier + catalyst-calendar mining,
   ECC-style instinct extraction for Optimus.
3. **Weakness review:** a recurring "what do they do better / what do only we
   do" pass against LangAlpha, OpenBB, ML4T-derived stacks → feeds branch 1/4
   backlogs. Aegis's unique ground: forward track record, registry,
   NEGATIVE_RESULTS, PIT store, the brain.

### Branch 4 — User side / front-end / product
*The spec is Murat's own pain points; ship it, use it on the real book, then
decide on public.*

1. **Portfolio guidance surface:** portfolio in → labeled risk, crash
   exposure, factor tilts, rebalance suggestions out (V2 canon A5 end-state).
   Server-side persistence of the real book already exists via the mirror
   seed; the UI needs to read it.
2. **Exit discipline in the UI** — the SOC $5→$20→$4 fix: surface the ATR
   trailing-stop level ("your winner is rolling over; here's the trim level")
   from the existing exit engine. Descriptive framing until TRIAL-EXIT reads
   out.
3. **Explain-the-move** — the "+300% and I don't know why" fix: event/news/
   filing/options context assembled per ticker (LangAlpha catalyst-calendar
   pattern), every claim labeled per the capability matrix.
4. **One-screen health + lead-with-the-answer framing** (V6) and the
   README repositioning (M4 — lead with the honesty infrastructure).
5. **Public launch decision** — only after Murat has used it on his own book;
   feedback loop lands in the conviction/postmortem pipeline.

## 5. Sequencing

Phase 0 (attended, ~1 session): ship + verify + fix the two live issues.
Then branches proceed **1 → 2 → 4**, with 3 running as a background lens
(reference passes feed the others). Detailed chunk plans are proposed at the
start of each phase and approved before code — per the phase-discipline
feedback rule.

| Phase | Branch | First chunks |
|---|---|---|
| 0 | — | Push 20 commits → verify live → fix `detect_regime` → brain re-ingest |
| 1 | Core | Crash-model discrimination plan · fragility candidates as trials · B1/B6/B10+H5 hardening · Optimus calibration memory |
| 2 | Paper accounts | Conviction-decision logging UX · 13F scheduling · congressional collector · V4 alerts + event lane |
| 3 | Reference | B7 tearsheets · B8 Qlib PIT schema · LangAlpha mining pass |
| 4 | Product | Guidance surface · exit-discipline UI · explain-the-move · README · public decision |
