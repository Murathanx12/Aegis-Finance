# HANDOFF — 2026-08-20 late → next session (Opus): BUILD THE BRAIN

Written after ORDER 25 shipped and `main` was pushed (`7ccfe4e`, 28 commits,
deploys Railway). Read `docs/ORDER_25_LIVE_ARENA_GEN1.md` and
`docs/AUDIT_PRODUCT_INTEGRATION_2026-08-20.md` first — this file is the work
queue, those are the why.

**The one-line state:** the flywheel now exists — arena books decide daily on
Railway, every decision (chosen AND rejected) becomes an EXPERIENCE record
with a frozen information-state hash, outcomes mature on 5 horizons, LLM
perceptions are gradeable predictions. The brain is whatever learns from that
corpus without being fooled by it. Nothing learns yet. That is this handoff.

---

## 0. First 20 minutes of the session (always)

1. `session_briefing()` + `aegis_verified_state()` — deploy commit must be
   `7ccfe4e` or later; scheduler must show **9 jobs** (now incl.
   `pi_copy_lab_run`, `pi_arena_daily`).
2. `GET /api/arena/status` — if books are NOT seeded, the attended flag
   hasn't been flipped yet (see §5); everything in §2 still proceeds, the
   arena just accrues later.
3. Check the night: Fri 08-21 17:00 was the first SELF-launch
   (`backend/data/optimus/iif1_launches/2026-08-21.json`). A receipt with
   `verdict: LAUNCHED` = the machine now runs its own nights. `REFUSED` =
   read the refusal code; a refusal is a finding. NO FILE = the task did not
   fire — that is the bad case, investigate Task Scheduler history first.
4. Fri 08-21 also lands the **first 396 forward resolutions ever**
   (mechanics only — the read gate licenses nothing before 40 graded nights;
   `scripts/iif1_read_gate.py` enforces). Verify `pi_ledger_resolve` ran and
   `resolved_at` fields exist; do NOT interpret outcomes.
5. WRDS pull: finished ~2026-08-20 late evening (~1,327 joinable tables
   planned into `backend/data/optimus/wrds/bulk/`). Verify the process ended
   and record final counts in the session log (manifest+plan are gitignored
   on purpose). Substrate facts: connection cap EXACTLY 7, one process, ≤5
   workers; `ps aux` cannot see detached Windows processes — use
   `Get-Process`.

## 1. Standing constraints that bind THIS work (do not re-derive)

- Arena = `PRODUCT_EXPERIMENT` / SIMULATION. Nothing it produces is evidence
  of skill, ever. It never touches `paper_nav` (static test pins it).
- **No training on same-day P&L. Reliability/model updates only from MATURED
  outcomes.** The training unit is decision/security/information-state,
  never portfolio-day. Lane NAV is never NN training data.
- **NN gate:** neural representations deferred until >100k graded
  experiences (2026-08-09 decision, reaffirmed in ORDER 25). The corpus
  machine now exists; the gate is unchanged. Counting/calibration layers are
  NOT gated — build those now.
- Do NOT widen the registered collectors' cross-sections (z-scores are
  cross-sectional; widening changes registered forward-IC trials). The
  arena's own composite is the extension point (`discovery.COMPOSITE_WEIGHTS`).
- Champion specs never mutate: a material policy change = new book id
  (`_v2`) in a new YAML version + segment receipt; old book keeps running as
  shadow comparator.
- Day work quiesces 16:15 HKT; nothing heavy near the 17:00 night launch.
  Local arena/LLM rehearsals append to TRACKED ledgers
  (`backend/data/optimus/llm_calls.jsonl`, `docs/BUILD1/llm_ledger.jsonl`) —
  **commit or don't rehearse after 16:00**, a dirty tree contaminates the
  night receipt.
- Pre-register anything that will be EVALUATED (CANON §6); §63
  screen-vs-export discipline; §64 power check before any confirmation.

## 2. THE BRAIN QUEUE (build order, with acceptance tests)

### P1 — the counting brain (no gate, start here)

**(a) Reliability ledger** — `backend/services/arena/reliability.py`.
From `experience_outcomes.jsonl` + the arena prediction ledger
(`<arena>/predictions.jsonl`, belief_state schema), compute per
(model_id | specialist) × horizon × coarse state (e.g. vol tercile at
decision): hit rate, Brier WITH base rate (reuse the
`brier_with_base_rate` refusal pattern from `iif1_grader`), calibration
curve, n. Append-only daily snapshot under `<arena>/reliability.jsonl`,
surfaced at `/api/arena/reliability`. **Refuses** below a minimum n per
cell (print the n, never a rate over 3 events). This is the input the
eventual router learns from — built as counting first, exactly so the
router has a non-NN baseline to beat.
*Acceptance:* offline test with synthetic experiences; a cell with n<20
returns REFUSED_THIN, not a number.

**(b) Regret reader** — pair REJECT legs with their `chosen_alternative`
by `information_state_hash`; emit paired (rejected_excess − chosen_excess)
per horizon. This is the "learn from passed opportunities" loop. Keep it a
READER over the two append-only files (the ledger stores no joined regret
by design — see `experience.py` docstring).
*Acceptance:* test that a GOOD_PASS and BAD_PASS produce correctly signed
regret; test that unmatched pairs are reported, not dropped.

**(c) Perception grading wire-up** — arena predictions resolve via
`belief_state.resolve_all(prices, path=<arena>/predictions.jsonl)`. Add
this to the arena maturation step (it is NOT wired yet — minted records
currently never resolve; that gap is the first thing this session should
close). One test: a matured BEATS_BENCHMARK record gets `outcome` and
`brier` filled from an injected panel.

### P2 — the known-answer battery (flips G1, unlocks trusting kills)

The single build that upgrades the referee from OPERATIONAL to PASSED:
plant known effects (and known nulls) through the FULL judge and measure
false-positive AND false-kill rates at declared levels, quoting
DECISION_MDE (simulated through the judge) not the z-label —
`verdict_battery_decision_mde_2026-08-19.json` is the precedent, the Opus
handoff (`docs/HANDOFF_OPUS5_2026-08-14.md`) has the spec. The arena adds a
new surface to calibrate: plant a synthetic edge in a fake day-state and
verify the reliability ledger recovers it at the declared rate.

### P3 — supervised learning on the historical substrate (WRDS is in)

The pull landed FF5 daily/monthly + momentum + Pastor-Stambaugh + 83 Fed
series + ~1,300 joinable tables on the 4,796-PERMNO panel (1990–2012 era:
6,988 eligible, 1,463 delistings, 33M rows). In order:
1. **Risk-head retraining harness**: reproduce
   `risk_head_vol_lgbm_options@2.0.0@31b9b8d` from the substrate with a
   versioned, receipted pipeline (train → pin → compare vs IV-scaled and
   trailing-63d baselines on the SYMMETRIC loss; era-transfer check both
   directions — the 1.001/0.992 result is the bar).
2. **Feature-family ablation on the new tables**: before spending on any
   model, run the Order 24 subspace test — does a candidate family add a
   dimension beyond the 3–7 shared factors (alignment vs 0.962/0.249
   baselines)? A family that doesn't is a re-measurement; skip it.
3. Only then model work. Ridge beat every NN on risk heads at tournament n;
   LGBM>ridge appears only at scale (UNIVERSE-STRESS flip, 0.747 vs 0.680).
   Any NN proposal must name the simplest admissible baseline it must beat
   by more than its own MDE, per the NET tournament framing.

### P4 — the router (design now, train later)

The eventual brain shape (adopted in ORDER 25): state → model-reliability
weights → forecasts → deterministic allocator. Prereg a design doc for a
contextual-bandit/router over {trailing-vol, LGBM-options head, IV-scaled,
abstain} with the reliability ledger as features. DO NOT train it until
(i) the ledger has real cells and (ii) the >100k gate or an explicit
Murat amendment. Drafting the prereg is unattended; registering it is not.

### P5 — trials on the shelf (highest information per dollar first)

1. **Frozen CRSP CONVEXITY replication** — substrate ready, design frozen,
   never run. The one that could CONFIRM rather than screen.
2. `REENTRY-OPTION-VALUE-1` — needs price-path replay arms.
3. `STREAK-MECHANISM-1` — is 5-up reversal concentrated in abnormal
   volume/skew/lottery/illiquidity state?
4. Manager library v2 (`rdate + 45d`, split-adjust `cfacshr`) — unblocks
   four MANAGER-* trials (13F `fdate` is a vintage stamp, not knowledge).

### P6 — arena v2 (only after P1 lands)

Unusual-volume tracker (greenfield; feeds DISCOVERY_UNIVERSE as a
*context* field, not a score) · 13F/ARK/congress as context fields ·
Current Best UI section (PRODUCT_EXPERIMENT-labeled, below the sacred
lanes) · weekly effective-dimension print over book return panels.

## 3. Commands

```bash
# fast suite (5,121 green at handoff; verify pytest_timeout is importable first)
python -m pytest backend/tests/ -q -m "not slow"
# arena, all offline
python -m pytest backend/tests/test_arena.py -q
# arena driver (local root is gitignored; Railway volume is authoritative)
python -m scripts.arena_run --status
# copy_lab (engine pass now also scheduled 10:00 ET)
python -m scripts.copy_lab_run --status
```

## 4. Architecture crib (what exists where)

- `backend/services/arena/` — spec (YAML hash = identity) · store
  (seed/decisions/orders/nav/receipts + write-once snapshots) · discovery
  (universe + `arena_composite` + frozen day state) · policies (pure:
  select/screen/size/exempt/tilt/substitute) · perception (LLM → gradeable
  records, arena-local ledger) · experience (forward writer + maturation) ·
  engine (daily pass; `insufficient_breadth` guard) — 25 tests.
- Historical experience corpus: `Aegis module\aegis_brain\night3\`
  (16,320 graded rows, kNN store with outcome embargo) — schema-compatible;
  the P1 reliability layer should read BOTH corpora but never pool them in
  one statistic without declaring it (evidence populations).
- Night (IIF-1): local + frozen, armed, WakeToRun/battery flags fixed
  08-20. Cloud migration REJECTED until post-40-nights (sibling repo,
  receipt-corpus-derived guards, residential IP).

## 5. ATTENDED (Murat only — queue, do not do these unattended)

1. **`AEGIS_SEED_ARENA=1`** on Railway for ONE boot (after this deploy is
   verified) → confirm `/api/arena/status` shows 6 seeded books → unset.
   Until then `pi_arena_daily` logs `no_seeded_books` (loud, by design).
2. NAV stamp fix **P-day-2026-08-19a** — decided, test-backed, sacred write
   path: needs his go. Until shipped, `all_fresh` stays one day optimistic.
3. G2 prereg signature before **2026-09-08** (draft:
   `docs/TRIALS/PREREG_LANES_G2_2026-09-08.md`; arena books have been
   shadow-running both rules since 08-20 — operational receipts only).
4. Laptop plugged in + idle-ish 16:55–17:05 daily (the ~2-min margin).
5. The older queue unchanged: positions read · amended NET prereg ·
   Brier-bar signature · LOSS amendment · Track E prereg · 08-27 resolve ·
   merge review of `lab/autonomous-rd`.

— 2026-08-20 late, after push `7ccfe4e`; prod verification recorded in the
session log that follows this commit.
