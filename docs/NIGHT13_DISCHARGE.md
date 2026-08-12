# NIGHT-13 DISCHARGE — the owed list, automated; the questions, answered

**2026-08-11. Contract: `docs/NIGHT13_BRIEFING.md`. Trials frozen at
Aegis module `c5b81aa` before compute.**

## 0. The owed list — every item, its automation, its status

| owed item | automation | status |
|---|---|---|
| 5 kill-condition rulings | `backend/services/kill_conditions.py` single source; auto-adopted into the reconciled book with `kill_condition_provenance: auto_adopted_default` + empty `murat_override:` slot; IC + mirror-challenge emit `ACTIVE_DEFAULT`; thesis labels only, never an armed exit (CANON §15) | **DONE** |
| `confirmed: true` | retired as a gate. `Book.evidence_grade` = `MURAT_CONFIRMED` / `BEST_EVIDENCE_UNCONFIRMED`; `actionable` no longer contains confirmation anywhere; the book prices tickets at best-evidence grade | **DONE** — Murat is not a blocker |
| cash figure | `Book.cash: Optional` — unknown is `None`, never a silent 0; equity-only NAV labelled `nav_basis: equity_only`; `CASH_SENSITIVITY_GRID` sweep, wealth numbers become ranges; grid-report-never-pick | **DONE** |
| transactions | TRANSACTION-ENSEMBLE-1 (accrues 0): 200 anchor-consistent histories; conclusions graded `ensemble_robust` / `DATA_NEEDED` | **DONE** — see §1 |
| ANTHROPIC_API_KEY | dropped from the list per ruling; DeepSeek did all 87 forecasts | **DONE** |
| graceful degradation | IC is now a live surface: `GET /api/ic/committee` + `/investment-committee` page; benchmark core + evidence-scaled tilts (CVLG 2%, INDV 0.5% at $40k), every position labelled `evidence-led` / `benchmark-core`, all 7 archetype refusals printed as the reason tilts are small, ruin beside dream, complete book at $10k/$40k/$1m | **DONE** — never an empty page |
| seeding the books | shadow registry still positions-unseeded; **deliberately NOT seeded tonight** — the shadow seeding path (`load_registry`/seed function) does not exist in code yet and inventing it at 3am is how silent fragility ships; carried as the top NIGHT-14 item. Paper LANES stay env-gated attended per `seed-a-lane` | **CARRIED, stated** |

**The "still yours" list after tonight: one item.** Broker CSV export,
Aug-2025 → Aug-2026, ~2 minutes — and the ensemble PROVED it matters
(conclusions genuinely flip inside the family without it; see §1).

## 1. What is ensemble-robust about his record (Q1–Q4, n=200, all SYNTHETIC-labelled)

- **The three headline figures (+73.7%, "+115%", $25k→$45k) are mutually
  consistent — but only if the book returned +72%..+150% in the months BEFORE
  the first PIT sheet (2025-11-07).** The undocumented gap supplies more than
  the entire headline (+76..+106 pts of the +73.7%; +100..+129 pts of the
  +115%). `ensemble_robust`.
- **Over the documented window, selection contributed +20.2..+43.1 pts while
  his weighting/trading subtracted 29.3..66.0 pts** vs holding his own picks.
  `ensemble_robust`, both QUBT arms. (A basket return, not a skill grade —
  CONVICTION-REPLAY-1's UNRESOLVED vs its 80-pt MDE stands.)
- **War-window drawdown −24.3%..−13.9%** — brackets NIGHT-12's measured
  −22.9% (the ensemble reproduced an episode it never saw). `ensemble_robust`.
- SLDP was a good exit (robust). TVTX/ALMS exit costs are positive but their
  magnitudes are `DATA_NEEDED`. As-traded total return is `DATA_NEEDED`
  (−35.2%..+4.9%).

## 2. Does mechanical management beat his as-traded management? (FACTORIAL-PM-1)

**H1 DIRECTION_REJECTED on this window** (registered fallback comparator
B1×M1; the ensemble's as-traded arm is DATA_NEEDED): vol-targeting and
mirror-rules both REDUCED the picks book's return on this one bull path
(−20.5 / −21.0 pts, both far below their 100/150-pt MDEs — a sign report, not
a detected effect). **H3 MET:** vol-targeting cut the war drawdown 9.5 pp
(−8.5% vs −18.0% on the M1 book). H2 (does management help his picks more than
random books): NOT_DETECTABLE, as registered. M3 kill-condition management:
**REFUSED_NOT_MECHANIZABLE — 0 of 61 names** have point-in-time checkable
conditions in the frozen data; no thesis text was converted into an invented
rule. The honest sentence for the product: *on a bull path, management costs
return; what it buys is the path — and the path is where accounts die.*

## 3. What would the book-keyed controller have done? (EXPOSURE-CONTROL-1)

Verdict **UNRESOLVED by the frozen rule** — the war-episode drawdown leg
PASSED (−8.94% managed vs −22.87% unmanaged, +13.9 pp avoided, 2.3× its
measured MDE, at 1.6 bps turnover cost) but the terminal-wealth bar missed by
**1.4 bps** (0.849863 vs 0.85; the rule decides on the point). Calibration:
6/6 episode coverage, dd avoided +29.5..+53.4 pp on the six proxy drawdowns.
Two control findings that matter more than the verdict:
- The index-keyed V0 corpse sat at exposure 1.0 all 188 days while the
  book-keyed ladder de-risked on 159 of them — **book-keying is the entire
  difference**.
- **Constant half-exposure beat the ladder** on both drawdown AND wealth.
  The licensed sentence: *half exposure on a beta-2.15 book, however arrived
  at, does the work; the timing ladder adds nothing detectable over it.*
  Sizing, not timing — for the third time in the programme's history.

## 4. Does the revision family survive turnover? (REVINFO-2, Aegis module f181d31)

**UNRESOLVED at trial level; monthly cells NET_DEAD.** At the parent's monthly
ranking the book churns 10.61× — reproducing ANALYST-IBES-1's prior exactly —
and nets −4.3 to −6.1 %/yr. At 3/6-month holding the net is positive
(+0.1..+1.9 %/yr) but far below MDEs of 7.7–10.3. H3's registered direction
(slower is better) held in all four comparisons (m3−m1 ≈ +4.1..+4.4 %/yr,
t up to 2.9) but below its MDE — no survivor declared. The turnover-matched
noise control lost −9.4 %/yr and was the only number in the trial above its
MDE: the instrument can see; the edge, at this design's power, cannot be seen.
No product candidate. The registered expectation (UNRESOLVED or NET_DEAD) held.

## 5. The learning loop — every clock now actually runs

- **The ledger can now resolve.** `resolve_all` existed with NO caller — the
  house failure mode, live. Now: `pi_ledger_resolve` scheduler job (daily
  16:30 ET), injectable clock, fresh price fetch with unpriceable-ticker
  accounting that keeps the canary DEGRADED instead of skipping silently,
  top-level health no longer hardcoded `"ok"`, prod-monitor pages on ledger
  degradation. First resolution: **2026-09-12** (20td — the briefed "5 days"
  was false; the printer now prints the measured minimum).
- **Calibration scaffold shipped:** `GET /api/optimus/calibration` —
  specialist × observable × horizon cross-tab, sparse cells print n and None,
  pending never scored.
- Descendant generation: waits for the first RESOLVED outcomes by design.

## 6. Defects found tonight, each already worth the night

1. **CORRECTED AT CLOSEOUT — the "fabricated commit" finding was itself a
   verification defect.** `bd7b403` ("Resolve QUBT share count to 300 from
   owner confirmation") exists on origin/main, pushed by another session and
   never pulled locally; this session checked only the local clones and
   reported "exists in neither repo". The claim in the pasted handoff was
   TRUE. Two lessons, both recorded: (a) a commit-existence check must fetch
   before it concludes; (b) that upstream commit edits `book_lanes.yaml` in
   place — exactly what lane-integrity invariant 1 forbids mid-stream, since
   the book config hash is segment identity. Bytes are not reverted (a revert
   would corrupt contiguity a second time); the live check that no spurious
   book-lane rebalance fired is in §9 below.
2. **The prereg linter could not parse any hyphenated corpse ident** — the
   `Resurrects:` regex stopped at the first hyphen, so no closed family
   (TRIAL-COND-VT, …) could ever be legitimately resurrected. Fixed + pinned.
3. **No ledger resolution caller** (§5 above).
4. **`resolve_one` KeyError on a missing benchmark** would have killed a whole
   resolution batch — guarded.
5. **`book_lanes.get("confirmed")` was structurally always False** (dead read,
   silent) — deleted in favour of the real evidence grade.
6. **`mirror_challenge`/docs carried divergent copies of the kill texts** —
   collapsed to one source.

## 7. Silent-fragility audit (run before commit; all fix-now items closed)

- **F1 (fixed):** the IC funnel artifact lived under `docs/`, which is
  dockerignored — the flagship page would have been permanently degraded in
  every prod image while green locally, with no canary. Artifact now ships at
  `backend/data/funnel_night10.json`, `IC_FUNNEL_PATH` points there, and
  `/api/health/full` carries an `investment_committee` row folded into
  `degraded_reasons` (pinned by test).
- **F2+F4 (fixed):** `resolve_one` graded BEATS_BENCHMARK on however many
  benchmark bars existed — a frozen CSV ending mid-window beside a fresh
  ticker would have written a permanently wrong outcome with status ok. Both
  legs now require `horizon_days + 1` bars; the resolver's per-ticker CSV
  fallback additionally requires last-bar coverage so staleness lands in
  `unpriceable`, loudly, instead of pending forever.
- **F3 (fixed):** the IC honesty block still said kill conditions "await
  Murat's ruling" after tonight's auto-adopt ruling — now states
  ACTIVE_DEFAULT, overridable, never armed.
- **F6 (fixed):** the resolver's yfinance fetch carries a 30s timeout.
- **Backlog, recorded:** F7 ledger persistence across redeploys (ephemeral FS
  reverts resolved records — loud via overdue/DEGRADED, but a persistence plan
  is owed before resolutions accumulate, first due 2026-09-12); F8 dead
  defensive except in `investment_committee.py`; F9 cached-object mutation in
  `committee()`; F10 a standing unpriceable ticker holds the prod-alert issue
  open by design.

## 8. Registry accounting

EXPOSURE-CONTROL-1 (+1 arm, UNRESOLVED) · FACTORIAL-PM-1 (+1 arm,
DIRECTION_REJECTED on H1 / H3 met) · TRANSACTION-ENSEMBLE-1 (+0, instrument) ·
REVINFO-2 (+1 arm, UNRESOLVED/NET_DEAD). All registered before compute at
`c5b81aa`; REVINFO-2 verdict at `f181d31`.
