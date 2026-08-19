# HANDOFF — 2026-08-19 DAY FACTORY (unattended session, Murat away)

Session: Fable day session on `lab/autonomous-rd`, following the 12-hour
overnight grind and external review round 3 (GPT audit, adjudicated — not
imported). Rails held: prod read-only (GETs only) · paper_nav write path
untouched · frozen IIF surface untouched · nothing signed, nothing armed.
This document is written so an Opus session (or any session) can build from
it alone.

## RESULTS PRODUCED

1. **The 14-point gap narrowed decisively, from allowed prod reads alone.**
   The conviction lane's NAV tracks NEITHER the YAML seed (cross-arms,
   level jumps) NOR the prod decision log — post-07-15 daily-return
   correlation with the reconstructed 12-name decision book is **−0.03
   raw, +0.19 on clean days**, while correlation with balanced-ew-control
   is **+0.60 clean / +0.81 raw**. The decision log (12 retro-entries all
   logged 07-11 05:52–05:57, 4 late_entry) was most probably never (fully)
   booked into `paper_positions`; the lane appears to be marking a broad
   EW-like book. THREE new accounting-jump days found (NAV moved >4%, book
   <1%): 07-14 −6.3%, 07-17 −5.3%, 08-10 +4.9% — joining 06-24/07-30.
   Receipt: `docs/conviction_replay/decision_reconstruction_2026-08-19.json`.
   The attended positions read confirms in minutes; after merge it is one
   GET (`/api/pi/lane/{id}/positions`, built + tested this session).

2. **The NET prereg was repaired BEFORE signature** (amendment 1, in the
   unsigned draft — drafting, not tampering). Review round 3's four defects
   all verified against code and fixed, plus one neither review saw:
   the bootstrap blocked 20 *panel dates* = **20 months** on a month-end
   panel, silently tripling the run-time MDE against the registered power
   basis. Primary is now per-date rank-IC difference (one unit end to end);
   verdicts are three-way (an underpowered miss is never "linear"); the
   competing-risks barrier head is executable walk-forward held-out with a
   multinomial comparator; first_test_year/seeds/folds/imputation frozen.

3. **G1's known-answer battery started, and it passes.** Synthetic worlds
   with declared answers (`--world linear|nonlinear|null|barrier`):
   nonlinear world — ridge blind (+0.004) while all nonlinear arms recover
   the planted interaction (+0.24..0.26, COMPLEX_WINS); null world — zero
   wins; barrier world — planted up-hazard recovered held-out (0.649) vs
   signal-free down-cause at coin flip (0.510).

4. **The daemon is no longer only a queue.** AEGIS-RESEARCH-EXECUTOR-1:
   adapters declared per hypothesis, period/universe substitution refuses,
   INSTRUMENT_AUDIT never touches the result slot, dying adapters counted.
   First real receipt: **1 audited / 12 BLOCKED with reasons in words / 0
   silent**. The convexity audit produced a §38-class finding: on the
   ACTUAL 143 date blocks the registered contrast's MDE is **0.0045**
   terminal-wealth fraction vs declared effect 0.030 — the trial is
   answerable ~7× over the moment its prereg is signed.

5. **SECURITY-IDENTITY-LAYER-1 exists**: ticker = dated alias; the four
   proven cases (MMC→MRSH, SQ↔XYZ undated-by-honesty, EA dead 08-04 with
   ghost signature, PXD dead) are regression fixtures; `quote_ghost_scan`
   catches the EA class; unknown names pass through stamped ASSUMED_STABLE.

## CLAIMS KILLED
- "The conviction lane's divergence is explained by the late-entered
  decision log" — killed by measurement (corr +0.19 clean days).
- The prereg's "anything else adopts the linear verdict" — killed as a
  category error; three-way verdicts now.
- The draft's implicit "run-time MDE matches the registered power basis" —
  killed (20-month blocks); fixed and test-pinned.

## CLAIMS PROMOTED
- "Every managed variant beat seed-hold on this book" (cross-arms) —
  unchanged, still rules-on-prices only.
- Convexity contrast answerable at n (executor power audit) — promoted
  from assumed to measured.

## NOT ESTABLISHED
- What the conviction/mirror lanes are actually marking (needs the
  positions read — attended now, one GET after merge).
- Whether any nonlinear arm beats ridge on the real panel (signature).
- The effective-spread convention (external review Q3 / TRF latency).

## DATA ADDED
- `docs/conviction_replay/prod_reads_2026-08-19/`: conviction decisions,
  pm book, full track record, cached decision-book prices.
- Executor receipts under `backend/data/optimus/research_daemon/`.
- Rehearsal receipts for all four synthetic worlds.

## BUGS FOUND (all fixed + test-pinned this session)
1. Bootstrap block-unit conflation (panel dates vs trading days) —
   `bootstrap_block_dates` derives from spacing now.
2. Registered barrier head unexecutable + in-sample-only Cox concordance —
   `run_barrier_head` walk-forward held-out.
3. `fit_cause_specific` in-sample concordance now labeled diagnostic.
4. (Process) 3 fast-suite tests moved passed→skipped since the overnight
   run — cached-fixture-absent skips in regime_accuracy/risk_stress, plus
   3 stable polygon-client skips; benign but the skip-reason audit is now
   in the log.

## ROADMAP MOVEMENT (gates)
- G1: known-answer battery EXISTS and recovers planted truth in 4 declared
  worlds — the upgrade path from OPERATIONAL to PASSED is now concrete:
  extend worlds + declared false-kill rates (spec below).
- G3/G4: verified state (G3 substantially built; G4 V1 present, empty).
- G7: first resolutions Friday; nothing readable before 40 nights.
- Full position: `docs/ROADMAP_POSITION_2026-08-19.md`.

## MURAT-ONLY ACTIONS (everything else is machine-ready)
1. **Attended positions read** (until merge) OR **merge this branch** and
   hit `/api/pi/lane/conviction/positions` + `/api/pi/lane/mirror/positions`
   — then `scripts/lane_autopsy_cross_arms.py` re-runs with the real book
   and the 14-point gap resolves.
2. **Review + sign the AMENDED NET prereg** (read AMENDMENT 1 first — the
   primary metric changed; that is why signing was not pre-empted).
3. Wednesday 17:00 Night 3 (`--dry-run` first) · Thursday Night 4 ·
   Friday resolutions · schtask `< NUL` fix → 3/3 clock → arm.
4. Brier-bar signature · trigger-eligibility decision (cycle G, overnight
   log) · convexity outcome-family amendment approval (P-grind-2026-08-19e)
   before signing that prereg.
5. Optimus brain_query is BROKEN on this machine (health-snapshot filename
   grows recursively: `aegis-health-aegis-health-...`; `[Errno 2]` on
   every query). Fix lives in the optimus repo (`tools/refresh_aegis.py` /
   `health_snapshot.py`), outside this repo's rails.

## NEXT 10 MACHINE JOBS (for the next session — Opus or otherwise)
1. **CRSP PIT universe + UNIVERSE-SURVIVAL-STRESS-1 dataset**
   (P-grind-2026-08-19a; WRDS psycopg2 route proven; PERMNO-keyed; feeds
   security_identity to replace its curated table).
2. **EXPECTATION-BACKFILL-1** (P-…19b): PIT expectations store keyed on
   publication timestamps; unblocks 4 daemon jobs + the tournament's
   "+expectations" rung; wire through `g4_expectation`.
3. **PIT event store** (structured event vectors, source timestamp,
   public-at, novelty): unblocks EVENT-RESOLUTION-CURVE-1,
   REACTION-GAP-1, INFORMATION-PROCESSING-GAP-1, SEQUENCE-OF-EVIDENCE-1.
4. **Effective-spread conventions matrix** (review Q3): tr_scond filters ×
   odd-lots × venue × quote-age × timestamp-lag sweep × realized spread /
   price impact; v1 stays immutable sensitivity; verdict only when the
   convention is stable across liquidity tiers.
5. **G1 battery extension**: more declared worlds (planted false kill,
   planted regime break, planted survivorship), each with declared
   false-positive AND false-kill rates — the documented flip condition
   for G1 → PASSED.
6. **Relative-value hardening** (review round 3 §SIXTH): per-date weight
   constancy, security-degree caps, antisymmetry checks, unseen-security
   transfer split, richer labels (relative_return_net, P(B barrier before
   A), drawdown delta) — pre-freeze, since its prereg is unsigned.
7. **NAV-RULES-DRIFT-MONITOR** (P-…19d) once the branch merges.
8. **Convexity outcome-family extension** (P-…19e) into the episode
   builder + prereg draft; then the trial awaits only its signature (the
   executor says it is 7×-powered).
9. **Wire security_identity into the panel builders** (net_panel, TAQ
   pulls, relative-value): resolve(ticker, date) + ghost-scan quarantine.
10. **Daemon: post-signature adapters** for AEGIS-NET (run tournament →
    record per-arm verdicts under the declared criterion) and convexity —
    so each signature converts to results in one executor pass.

## Cadence
`docs/OPERATING_MODEL_DAY_NIGHT.md` adopted: day = factory (this session
is the template), 16:15 HKT quiesce, night = IIF + daemon + rd_loop,
morning = receipts. IIF is a clock, not the schedule.
