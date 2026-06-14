# P1 #6 — Lane framework + mirror & conviction lanes (attended build plan)

> **Why this is a plan, not a grind commit:** seeding new lanes writes `paper_nav`
> inception rows and adds lane accounting — the track-record write path. Murat
> granted a *controlled* write-path exception for this, but it is the highest-risk
> work and must be done attended, plan-first per Phase 3, with the same
> NAV-continuity + garbage-weight protections as Step #2. The grind session built
> only the SAFE, write-path-free pieces (below); this plan is the rest.

## Already built (safe, on `lab/autonomous-rd`)
- **Trials pre-registered:** `docs/TRIALS/TRIAL-002-mirror-vs-rules.md`, `TRIAL-003-conviction-vs-rules.md` (decision rules committed BEFORE inception — tamper-evidence).
- **Conviction decision capture** (`da71109`): immutable `personal_decisions` log + `late_entry` (schema v6) + `POST /api/pi/conviction/decision` + `GET .../decisions` + `scripts/log_conviction.py` CLI. Logs a decision in <10s. (This is the LOG; the lane that *applies* decisions is below.)

## What the attended session must build (write-path)

1. **Lane-framework generalization.** Today `REFERENCE_LANES` is derived from YAML
   lanes that have `target_equity_pct` (ETF-sleeve + optimizer lanes). The mirror &
   conviction lanes are **individual-stock books** (explicit share counts, no sleeve,
   no universe optimizer for conviction). Generalize the lane abstraction to carry a
   `purpose` tag (`benchmark | optimizer-variant | portfolio-mirror | conviction`) and
   a holdings spec, WITHOUT breaking the 4 existing lanes (their config hash must not
   change → no new segment on them). Prove behavior-identical for the existing 4.

2. **Seeding (the controlled write-path exception).** A seeding routine: take the 12
   share counts → fetch CURRENT prices at seed time → current-market-value weights →
   normalize to $100k → write a TODAY-dated inception `paper_nav` row + open positions.
   Reuse Step #2's garbage-weight gate (NaN/zero-sum/degenerate → fail loud, never seed
   junk) and NAV-continuity discipline. **Inception = today; never a reconstructed past
   (look-ahead). Murat's prior return never enters the record.**

3. **Per-ticker MTM for ~12 small/mid-caps.** The existing hourly MTM marks the
   ETF-sleeve lanes; verify it batch-fetches the 12 individual names and that a SINGLE
   bad ticker degrades gracefully (cost-basis fallback, loud canary) — the
   `real_analyzer` / `mark_all_lanes` bug class (one bad symbol must not flat-line or
   crash the whole MTM). Add a test that injects one un-fetchable ticker.

4. **Mirror lane management.** After seeding, manage by config v2 (HRP, balanced
   cadence) forward — reuse `compute_target_weights` on the book.

5. **Conviction lane management.** Positions change ONLY via `personal_decisions`
   (already captured). Wire the lane to apply logged decisions at the next MTM/rebalch
   tick (enter/add/trim/exit → share deltas). No auto-trading; it just reflects Murat's logged moves.

6. **Register TRIAL-002/003 in the registry at seeding** (cumulative trials 3→5).
   **Verify T2 effective-N:** these two lanes are correlated (same book) — confirm raw
   N is the gate floor (→5) AND `effective_independent_trials` reports them as ~1
   independent stream pair (N_eff ≪ raw), since they share holdings. Add the pinning assertion.

7. **UI + track-record page.** Both lanes appear on the track-record page with the
   note: *"Inception 2026-06-14 at current holdings; prior personal performance is not
   part of this record."* No-skill-claims footnote stays.

## Done-when (attended)
Both lanes live with TODAY-dated inception rows at real current weights; visible on
the track-record page; `/api/pi/registry` shows 5 trials; a conviction decision is
loggable from the terminal in <10s (already true); per-ticker MTM handles a bad
ticker gracefully (tested). Then it deploys (Murat's merge to main) and accrues forward.

## Risk / discipline
- Seeding writes `paper_nav` — do it once, idempotently (re-running must not double-seed),
  with the Step #2 migration pattern (`apply_config_change_rebalances`-style startup hook).
- The 4 existing lanes' config hashes must be untouched (no spurious segment boundaries).
- ~12 concentrated small-caps → mirror/conviction/balanced diverge wildly for months;
  the comparison means nothing until ~24 months. Display accordingly.
