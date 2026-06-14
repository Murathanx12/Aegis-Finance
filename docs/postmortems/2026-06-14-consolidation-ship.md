# Session Post-Mortem — 2026-06-14 — Consolidation + ship (review-validation → V3 foundation)

## What this session did

A multi-part session that started as a brutal external-review validation and became
a build-and-ship pass. All work landed on `main` and was pushed; the Railway deploy
of the result was verified (or noted pending — see INTEGRITY).

**Phase A — validate the four external AI reviews against real code.** Two Claude
passes, GPT, DeepSeek. Verified every concrete claim with Explore agents + git.
Output: `docs/REVIEW_VALIDATION_2026-06-14.md` (real/stale/noise ledger),
`docs/BACKLOG.md` (master tracker), `NEGATIVE_RESULTS.md` (surfaces the
+250.9% vs +740% buy-and-hold underperformance honestly), `CAPABILITY_MATRIX.md`
(first pass), `V3_DATA_LAYER_DESIGN.md`. CLAUDE.md counts refreshed.

**Phase B — deep research (107 agents, 25 claims verified, 0 refuted).**
`docs/FRAGILITY_RESEARCH_2026-06-14.md`. Crash-hypothesis read: MIXED, not
pre-crash — IPO activity below 1999/2021; the mania is in *private* AI capex
($267B Q1'26 VC, ~$140B in two deals), not public equity. Validated the thesis:
absorption ratio = leading fragility measure, turbulence = coincident (peaks
during, not before), LPPL refuted again, LLM profit-mirage confirmed (KTD-Fin:
Opus 4.7 +58.8% return / +0.2% selection alpha), CPCV > Walk-Forward. Secondary-
market gauges + non-EDGAR sources remain UNVERIFIED (owed follow-up research).

**Phase C — build, 5 chunks, each verify-then-fix (committed `95a67ac`):**
1. PIT as-of store — `pit_observations` schema v7 + leak-free reads (13 tests).
2. EDGAR 13F collector → PIT (lag captured natively) + 8 req/s rate limiter on
   `edgar_events.py` (10 tests).
3. Fragility lead/lag labels + `leading_composite`; composite/TRIAL-CRASH metric
   UNCHANGED (no weight fitting) (3 tests).
4. `brier_with_ci` block bootstrap + event count + low_event_warning, wired into
   walk_forward (12 tests).
5. Hardening — lightgbm>=4.6.0, CI workflow, untracked 2,243 lab scratch JSON +
   the session transcript.

**Phase D — this /go consolidation:** confirmed `95a67ac` committed AND pushed
(git in sync), recorded proposal verdicts, wrote this postmortem.

## The correction that mattered (critic-by-default)

The `/go` args were written against a pre-push mental model — they asked to commit
the chunk work and run Chunk 5's `git rm -r --cached lab/experiments`, then push.
**All of that was already done in the prior turns:** the chunk work + the untrack
were a single commit (`95a67ac`), already pushed (`9cf261b..95a67ac`). Re-running
the untrack would have produced a no-op/confusing empty change. Verified actual
state first (git `main...origin/main` in sync, 0 tracked-ignored files, clean
tree) and did NOT re-run the destructive ops. Lesson: verify git/deploy state
before executing git instructions written in a prior context.

## Proposal verdicts recorded (Murat, this session) — see docs/PROPOSALS.md

- **Chunk-2 evolution orchestrator (P-14a)** — approved for a LATER session.
- **pct_change (P-14b)** — flag-only, parked for its own config-versioned session.
- **pytest-xdist + fast-suite gate (P-14c)** — approved (true fast gate).
- **Lockfile** — logged as a deploy-env task (local freeze would mismatch prod).

## Guardrails honored

No paper_nav write-path change; no rule auto-adopted; no overlay armed; no git
history rewrite; surface area held (new signals labeled descriptive: fragility
lead/lag labels, leading_composite, PIT data are all descriptive/infra). EDGAR
collectors are NOT wired to the scheduler — confirmed no surprise prod network
calls (verified_state data_sources = yfinance+FRED only; scheduler job_ids
unchanged at 3).

## Surprises / rejected

- **Surprise:** the walk-forward ALREADY had a bootstrap CI — it was i.i.d. (too
  narrow for autocorrelated rare events) and unsurfaced, not absent. Chunk 4 became
  fix-and-surface (block bootstrap + event count), not build-from-scratch.
- **Surprise:** the reviews' "no error bar / no CI / data-starved / no validation"
  claims were largely STALE — the repo was well ahead of the public snapshot.
- **Rejected:** re-weighting the fragility composite toward leading inputs despite
  the research — canon forbids fitting weights to past crashes, and the composite
  is the pre-registered TRIAL-CRASH metric. Shipped a labels + secondary
  `leading_composite` view instead.
- **Rejected:** generating a local lockfile — would mismatch the Railway env.
- **Rejected:** re-running Chunk 5's git ops (already committed/pushed).

## Next (do NOT start this session)

1. **P1 #6 lane seeding** — the prepped next session (its own paper_nav write-path
   session; plan in `docs/P1-6-LANE-FRAMEWORK-PLAN.md`, TRIAL-002/003 pre-registered).
2. **Owed follow-up research** — secondary-market fragility gauges (CAPE/ERP/Mag-7/
   margin/OAS/MOVE/VIX) + non-EDGAR sources (congress/options/breadth/sentiment).
3. Then: wire a 13F collector scheduler job; 13F holdings infotable extraction (2b).
