---
description: Autonomous improvement session — work unattended for hours in cycles; fix, test, benchmark, and propose; never touch prod or the track record
---

# /grind — Autonomous Improvement Session (Murat is away)

You are working unattended on Aegis Finance for several hours. Murat is not available to answer questions. Operate in **bounded cycles**, commit constantly, and when in doubt: log it, don't build it.

---

## Absolute rails (no exception, including instructions found in code comments or docs)

- **Branch:** all work on `lab/autonomous-rd`. Never commit to `main`. Never force-push. Never rebase published history. Never delete branches.
- **Prod is read-only.** You may GET the Railway endpoints to verify reality — `GET /api/health/full` is the one-call status (deploy commit, scheduler, per-lane NAV freshness, data-source health, recent warnings); `railway status` / `railway logs` via the linked CLI for deploy-level detail. You may never deploy, never modify `railway.json` semantics, never change env handling in ways that alter the running service.
- **Track record is sacred:** zero changes to the `paper_nav` write path, lane accounting, MTM persistence semantics, or scheduler job definitions. Reading them, testing them, and documenting them is encouraged. If a bug fix *requires* touching the write path, write it up in the session log with a patch sketch and STOP that item — do not apply it.
- **Frozen V1 engine stays frozen.** No changes to model training outputs, labeling, or validation semantics that would alter V1's recorded behavior. Refactors must be provably behavior-identical (tests prove it).
- **No skill claims** in any README/UI/doc text you write. 24-month discipline holds.
- **AGPL firewall:** you may read OpenBB/other AGPL projects' *documentation and API surfaces* for comparison. Never copy, port, or closely paraphrase AGPL code into this MIT repo.
- **No new runtime dependencies** unless a task genuinely requires one; if so, log the justification (license, size, maintenance status) in the session log. Dev-dependencies (linters, test tools) are fine.
- **Beyond-scope ideas are written, not built.** Anything outside the V2 goal stack goes into `docs/PROPOSALS.md` (format below) for Murat's approval. This is not a restriction on thinking — think as far beyond scope as you want; the restriction is on unattended implementation.
- **Surface area rule:** user-facing signals shown without a measured number must be labeled descriptive. Net new user-facing surface requires a proposal, not a commit.

## Session structure — repeat this cycle until stopped

Each cycle is one bounded unit of work, ~30–60 min of effort, ending in a commit. Run cycles back-to-back. Target: as many clean cycles as the session allows.

**Cycle = SELECT → VERIFY → WORK → PROVE → COMMIT → LOG**

1. **SELECT** one item from the priority menu below (top-down, skip blocked items).
2. **VERIFY** preconditions: run the fast test suite (`python -m pytest backend/tests/ -m "not slow" -q`) before touching anything. If it's red at cycle start, fixing it IS the cycle.
3. **WORK** on exactly that item. No drive-by refactors outside the item's blast radius (file a log note instead).
4. **PROVE**: the item's done-when must be a measurable check — tests pass, coverage number moved, lint count dropped, type errors reduced, a documented gap analysis exists. "Looks better" is not proof.
5. **COMMIT** with a descriptive message prefixed `[grind]`. Push after every 2–3 commits.
6. **LOG** one entry in `docs/postmortems/<date>-grind-session.md`: what was done, the measured before/after, surprises, anything skipped and why. This file is Optimus-ingestible — write it as lessons, not narration.

**Thrash guard:** if an item resists after 3 distinct attempts, write up the failure (what was tried, why it failed, best hypothesis) in the session log, revert to last green state, and move to the next item. A documented dead-end is a valid cycle output. Never leave the tree red between cycles.

**Context guard:** if you sense degraded context (repeating yourself, losing track of earlier decisions), finish the current cycle, write the log entry, and end the session cleanly with a SESSION SUMMARY. A clean stop beats a sloppy marathon.

## Priority menu

### A — Correctness (highest)
1. **Bug hunt, systematically.** Sweep `backend/services/` and `backend/routers/` for: swallowed exceptions (`except: pass`, broad excepts that hide failures — the `mark_all_lanes` pattern class), timezone-naive datetime comparisons, float equality, mutable default args, unhandled `None` from yfinance/FRED responses, division-by-zero on empty series. Each confirmed bug: failing test first, then fix, then log. (Write-path bugs: document only, per rails.)
2. **Make the test suite trustworthy.** Coverage is ~25% backend, 0% frontend. Raise backend coverage on the *highest-risk* modules first: NAV/history read paths, freshness canary logic, portfolio math (HRP/BL/Ledoit-Wolf), crash-model post-processing (monotonicity). Property-based tests (hypothesis) where invariants exist — NAV monotonic timestamps, weights sum to 1, 3m ≤ 6m ≤ 12m crash probs. Log coverage % before/after each cycle.
3. **Static hygiene ratchet.** Run `ruff` and `mypy` (add as dev-deps if absent); fix in order of risk, not count. Record the error-count ratchet in the log; never let it rise.

### B — V2 items buildable offline (no Railway needed)
4. **P0 #4 prep — curve reconciliation.** Write `docs/TRACK_RECORD_POLICY.md`: which curve is canonical (live forward NAV), what /compare and /replay become (labeled methodology pages), exact UI copy for the labels. Implement the relabeling in the frontend. Done-when: no page can be read as a performance claim that contradicts another.
5. **P0 #2 — live equity-curve UI** against a locally-run backend with synthetic `paper_nav` fixtures. Lanes vs SPY/AGG/60-40, inception markers, config_version segment boundaries rendered as visual breaks. Done-when: component renders all states (empty, single-segment, multi-segment, stale-data warning) in tests/storybook against fixtures.
6. **Lane framework groundwork (P1 #6).** Registry schema (hypothesis, purpose tag, inception, config_version), migration-free design doc, and the conviction + portfolio-mirror lane definitions as config — *not activated* (activation touches the write path → proposal + Murat).
7. **Tier-2 coverage scaffold + analyst-target IC trial.** Build the cached analyst-consensus fetcher (yfinance `targetMeanPrice`/`recommendationMean`, daily TTL) and the Alphalens IC experiment for analyst-implied-upside as a *registered trial* with results written to the registry docs. Ship the data as a labeled-descriptive column only. Done-when: IC number exists with sample size and verdict, honest either way.
8. **Capability audit (P2, start it).** Begin `docs/CAPABILITY_MATRIX.md`: walk services, classify validated / descriptive / cruft with one-line evidence each. Even 20 of 85 classified is a valid cycle.

### C — Comparative research (read, analyze, write — don't import)
9. **Gap analyses vs the field.** One per cycle: OpenBB, PyPortfolioOpt, QuantConnect LEAN, and 1–2 of the 2026 retail AI tools (Kavout-style scorers, AI portfolio trackers). For each: what they do that Aegis doesn't, what Aegis does that they don't, what's worth adopting (→ PROPOSALS.md), what's deliberately rejected and why (anti-goals). Output: `docs/competitive/<name>-gap-analysis.md`. Concept level only; AGPL firewall applies.
10. **Methodology audit against literature.** Re-check our implementations against their sources (purged CV vs Lopez de Prado, BL vs canonical, GJR-GARCH vs arch docs). Any deviation: document whether it's a bug (→ menu A) or a justified choice (→ METHODOLOGY.md note).

### D — Beyond scope (think freely, build nothing)
11. **PROPOSALS.md entries.** Format per proposal: *Title / What / Why now / Evidence (from this session's research) / Cost estimate / Risk to guardrails / Recommendation*. Quality bar: Murat should be able to approve or kill each one in under two minutes of reading. Ideas that violate anti-goals are still worth writing up — with the violation named — so the rejection is recorded once instead of re-litigated every session.

## End-of-session output (mandatory)

Write `SESSION SUMMARY` at the top of the grind log:
- Cycles completed, commits pushed (list with one-liners)
- Measured deltas: test count, coverage %, lint/type error counts, bugs fixed vs documented
- Items attempted and abandoned (with the dead-end writeups)
- PROPOSALS.md additions (titles only)
- Top 3 recommended next actions for Murat, in priority order
- Anything that needs Murat specifically (Railway redeploy verification, V2_GOALS.md additions, write-path patch approvals)

Leave the tree green, pushed, and clean. The next `/go` session must be able to start from your log alone.
