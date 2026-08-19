# Grind session 2026-08-18 night → 2026-08-19 (12h unattended, Order 20)

## SESSION SUMMARY

**RESULTS PRODUCED** (the Order 20 standing rule, honored in the ordering):

1. **The 14-point mirror gap is UNRECONCILED** — authoritative conviction
   NAV diverges from YAML-seed buy-and-hold by up to 11.2% in discrete
   jumps; the live mirror sits ~27 points below its own rules replayed.
   Neither circulating reading survives. What stands: on this book,
   EW-at-seed carries +3.3pp, monthly re-equalisation only +1.3pp.
   **Blocked on the attended positions read.** Erratum filed on my own
   adjudication sentence (B1).
2. **The daemon's guard was permissive in the live tree its whole life**
   (absent reservations file → `[]`); it now DERIVES windows from the
   confirmation-budget ledger and refuses absent inputs. First real queue
   loaded (13 declared jobs), first nightly receipt written.
3. **MMC solved (renamed MRSH 2026-01-14), SQ/XYZ re-pulled → TAQ quoted
   panel 184/185 (16/139/29), canary exit 0.** Only dead PXD keeps a band.
4. **EA is DELISTED (2026-08-04, PIF buyout)** — caught because trades
   vanish while quotes ghost on for 8 days; its quoted row is flagged as
   measured-through-08-04. A quotes panel cannot see death; a trades panel
   can.
5. **Effective spreads measured for the whole panel** (4,224 name-days via
   wct prevailing-NBBO): median effective/quoted 0.369, median effective
   one-way 1.076bp, 84/98/2 vs the band on an EFFECTIVE basis — stated as
   SENSITIVITIES; the daemon verdict is DEFERRED to the trade-condition
   conventions (external review Q3).
6. **Three datasets materialized for the registered trials**: NET panel
   (24,911 rows × 145 monthly blocks, PIT-tested), convexity episodes
   (23,011 with matched non-winners, no aggregates), relative-value pair
   labels (72,495 pairs, cost-gated, 5 sensitive).
7. **Tournament harness + UNSIGNED prereg draft**; full-shape synthetic
   rehearsal green in 23s; the signed path refuses until Murat signs.
8. Night-sequence fault injection: transport death and corrupted feeds
   halt cleanly; one registered-semantics tightening proposed (below).
   Fragility fix: survival_model's broken-model path now announces its
   substitution.

**INFRASTRUCTURE BUILT:** 6 new services/scripts modules, 5 new test files.

**Measured deltas:** fast suite 4,949 → **5,010 passed** (+61 tests, closing
run 2026-08-19, 3m42s, 0 failures); ruff clean on every new file; 0
regressions; 11 commits on `lab/autonomous-rd`, pushed.

**Needs Murat specifically:**
1. Attended positions read (`paper_positions`/`rebalance_events` for the
   book lanes, prod volume DB, under lane-integrity-check) — the ONLY
   thing that resolves the 14-point contradiction.
2. NET tournament prereg signature (draft at
   `docs/TRIALS/PREREG_AEGIS_NET_TOURNAMENT_1.md`; the runner refuses
   until signed; delete the pins-unsigned test on signing).
3. Trigger-eligibility tightening decision (registered rule; cycle G).
4. Wednesday 17:00 Night 3 attended + Brier-bar signature; the schtask
   `< NUL` fix remains the arming blocker.
5. Merge review of this branch to main (docs addenda included — the TAQ
   split superseded to 16/139/29 of 184 while the brief sits with
   reviewers).

**Top 3 recommended next actions:** the positions read · sign + run the
tournament (2 min of compute per head) · refine the effective-spread
computation with the conventions the external reviews return.

Branch: `lab/autonomous-rd`, fast-forwarded to main @ `9be7e4d` at session
start (it was 498 commits behind, 0 ahead — clean ff). Nothing lands on main
tonight; the next attended session reviews and merges. Rails honored: prod
read-only · paper_nav write path untouched · IIF frozen surface untouched ·
attended items (signatures, arming, resolutions, lane flags) left for Murat.

Planned cycles (Order 20 §2–§7, priority order):
1. Lane-autopsy cross-arm replay (P1 §5 — outranks all other autopsies)
2. Daemon first real queue + nightly receipt (§2.1, §2.5)
3. NET panel materialization + coverage audit (§2.3)
4. NET tournament harness + prereg DRAFT (§3 — synthetic smoke only;
   does not run on the registered basis without Murat's signature)
5. CONVEXITY episode construction (§2.2)
6. NEURAL-RELATIVE-VALUE-1 label builder (§4)
7. Fault-injection sequence test, night pipeline (§7)
8+. Silent-fragility sweep of recently-touched services

## Cycle log

Baseline at session start: **4,949 passed / 11 skipped, 3m48s** (fast suite).

### Cycle A (`dce2f4d`) — daemon guard derivation + first real queue
- **Found:** the reserved-window guard read a file no producer writes
  (`reserved_windows.json`), and absent returned `[]` — "the most important
  line in this module" passed every job unconditionally in the live tree for
  the daemon's whole life, while the real reservations (M4, IV) sat in
  `confirmation_budget.jsonl` unread. The module's own docstring stated the
  right contract; the code contradicted it.
- **Fix:** `derive_reserved_windows()` — every declared EXPORT budget window
  becomes a `ReservedWindow`; absent ledger REFUSES; malformed window_id
  REFUSES. `reserved=None` derives, `reserved=[]` is a written declaration.
  6 new tests incl. one against the LIVE ledger (both worlds).
- **Delivered:** Order 20 §2.1/§2.5 — first real queue (13 declared jobs,
  every prior declared before any data read), first nightly receipt
  (`backend/data/optimus/research_daemon/receipt_2026-08-18.json`). Bandit
  ranking sensible: HJ effective spreads first; IMPLIED-REVISION-1 last at
  p_resolves 0.15. Ops chores deliberately excluded (no p-value → no place
  in an m-counting ledger). 37/37 daemon tests green.

### Cycle B (`eef1eda`) — cross-arm replay: the reconciliation FAILED, informatively
- **The sign contradiction found in survey:** Order 18's replay said EW rules
  +15pp AHEAD; the live lanes say mirror 14pp BEHIND. Both in committed docs.
- **Reconciliation (Order 20 §5, done FIRST):** authoritative conviction NAV
  (prod snapshot, provenance-stamped) diverges from YAML-seed buy-and-hold
  by up to **11.23%**, in discrete jumps (07-30 +11.7% ≈ re-book correction;
  07-14 +7.5% ≈ late-entered decisions; 06-24 +6.9% unknown). Live mirror is
  **~27 points below its own rules replayed** on the current book.
  **The 14-point gap is UNRECONCILED** — no rule mechanism may currently be
  quoted as its cause. Missing input: `paper_positions`/`rebalance_events`
  for the book lanes — prod volume DB, attended (lane-integrity-check).
- **What stands:** on this book and window (both starts; ordering stable),
  every managed cell beats seed-hold; **EW-at-seed carries +3.3pp, monthly
  re-equalisation only +1.3pp** — bet-sizing at seed, not winner-selling, is
  the larger term. Statement about rules on prices, not about live lanes.
- **Erratum:** appended to adjudication B1 — my sentence "the EW arm is the
  one 14 points behind" quoted the live lanes as if attribution were
  settled. The B1 rejection stands on its other leg (no covariance ran).
- New: `scripts/lane_autopsy_cross_arms.py` (hermetic, reconciles before any
  economic sentence, refuses live-lane claims beyond declared 2% tolerance).

### Cycle C (`53de007`) — AEGIS-NET-PANEL-1 materialized
- The label library got its supplier: 24,911 rows × **145 monthly date
  blocks** (§58 unit printed everywhere), 165–179 names/date, from the
  in-repo 182-name panel = the TAQ universe (measured costs join for free).
- PIT enforced by test: post-t prices mutated → features byte-identical;
  `assert_pit_partition` got its first production caller.
- Coverage audit DECLARES absent families (options/expectations/event/
  semantic) so the ablation ladder knows its floor is the data's.
- **Finding for the prereg:** at h=20 the up75/down30 barrier fires on 0.6%
  of rows; up40/20 on 2.7% — big-barrier competing-risk cells are
  NOT_ANSWERABLE at this horizon and the draft records it.

### Cycle D (`e2c0c79`, `0f31b7f`) — tournament harness + UNSIGNED prereg
- Five frozen arms; paired loss contrast vs ridge with date-block bootstrap;
  competing-risks head (cause-specific Cox; `neither` = censoring;
  sub-30-event causes refuse). `assert_signed` refuses the registered panel
  until the prereg's SIGNED-BY names a human; one test pins the live draft
  as unsigned (delete it when Murat signs — that is the lifecycle).
- Prereg draft: §61-capped SCREEN; G5 confronted (non-directional heads);
  power block records economic bar ΔIC 0.01 vs MDE ≈0.023 ⇒
  NOT_ANSWERABLE_AT_N at the economic bar, recorded at registration.
- The guard-enrollment scanner caught both new refusal types within one
  cycle — enrolled.

### Cycle E (`1393e0f`) — CONVEXITY-EPISODES-1
- 23,011 episodes (+20: 13,956 · +40: 6,198 · +75: 1,845 · +100: 1,012),
  first-touch within 252d of month-end entries, 6 arms with exact
  per-dollar accounting, matched non-winner per episode (§16; 86% matched,
  misses counted by reason). A PIT bug (matching on the crossing month's
  own month-end) was caught by test before shipping.
- NO aggregates anywhere — a test asserts the meta contains no verdict
  language; trim-vs-hold belongs to CONVEXITY-PRESERVATION-1's
  registration (queued in the daemon, unrun).

### Cycle F (`15cadce`) — NEURAL-RELATIVE-VALUE-1 labels
- 72,495 pairs on 145 date blocks (n_date_blocks printed beside n_pairs in
  every artifact), beats_net balanced 35,941/36,554, only 5
  COST_MODEL_SENSITIVE — the dividend of 179/182 measured TAQ names.
- Joint switch cost = both one-way legs; a band leg makes the joint a band
  with the weaker provenance; sensitive pairs excluded-and-counted, never
  resolved by picking an end; `improvement_net` is None on a band.

### Cycle G — fault injection for the night sequence (B3)
- Network death mid-night / at first call: CLEAN (no partial `ok`, no
  ledger append). Wholly corrupted feed: void with reason. String-typed
  drift: never reaches an arm.
- **PROPOSAL for Murat (registered-rule amendment, attended):** a NaN
  z-score is treated as MISSING; a name with only its booleans measured
  stays eligible at score 0, so a score-0 name can enter the night when
  k ≥ eligible, and the per-name missing-components disclosure is stripped
  from the night receipt (`run_night` drops `selected` rows). Options:
  (a) require ≥1 measured continuous component for eligibility, or
  (b) carry the disclosure onto the receipt. Either changes a registered
  selection rule ⇒ attended; pinned as-is by test meanwhile.

### Cycle H (`140125f` + follow-ups) — MMC solved; TAQ panel 184/185; runner rehearsal
- **The "unexplained" MMC absence was a RENAME**: Marsh McLennan switched
  NYSE ticker MMC → MRSH on 2026-01-14 (rebrand to Marsh) — verified live
  in TAQ (MRSH: 10,583 quotes on 08-14) and by news search. The calibration
  window is entirely post-rename, so `sym_root='MMC'` was the right company
  at the wrong symbol; yfinance 404s for the same reason. The absence trio
  is now FULLY explained: PXD delisted · SQ→XYZ · MMC→MRSH.
- Re-pulled both renamed names for all 23 sessions (direct WRDS psycopg2 —
  port 9737 was open, no tunnel needed; same declared measure).
  `taq_calibrate`: **184/185 retired, 16/139/29, canary exit 0** — only the
  genuinely dead name keeps its band. MMC ≈ 4.5bp one-way, SQ ≈ 2.4bp.
- Dated addenda added to the external brief and Order 20 §0 (the brief is
  already in reviewers' hands — annotate, don't rewrite). config.py sector
  lists: MMC→MRSH, SQ→XYZ, PXD removed (deploys only on attended merge).
- Tournament runner + full-shape synthetic REHEARSAL: green in 23s
  (9 folds, 17,340 rows; ridge recovers the planted linear IC, nonlinear
  arms recover less of a purely-linear world). Signed path refuses.

### Cycle I (in progress at log time) — EFFECTIVE spreads, the daemon's #1 job
- Discovery: `taqm_2026.wct_*` (WRDS computed trades) carries every trade
  with the PREVAILING NBBO already matched — the trade-quote alignment is
  server-side, so effective spreads are one GROUP BY per day (~78s), not a
  hand-rolled Holden–Jacobsen join.
- Probe receipt: **AAPL 08-14 — effective 0.471bp full median vs
  quoted-at-trade 0.656bp: ratio 0.719**, inside the documented 0.5–0.9.
  Marginal costs are ~28% inside even the measured quoted numbers.
- `scripts/wrds_taq_effective_pull.py`: resumable per-day JSONL, v1
  DELIBERATELY without tr_scond/odd-lot conventions — those are what
  external review Q3 is out asking; **the daemon job's verdict is NOT
  recorded from v1**; the dataset is kept for the refined computation to
  re-derive against (a moved number would itself be a conventions finding).

Note for next attended session: `gh` CLI is not installed on this machine —
the prod-monitor ≥19:00 firing check needs the Actions UI or a token.

---

# DAY-FACTORY SESSION 2026-08-19 (Fable, unattended, Murat away ~3h)

Follows the overnight grind above; external review round 3 (GPT audit)
adjudicated, not imported. Full handoff: docs/HANDOFF_2026-08-19_DAY_FACTORY.md.

## RESULTS (one line each; receipts linked in the handoff)
1. 14-pt gap NARROWED from allowed prod GETs: conviction NAV tracks neither
   seed nor decision log (clean-day corr +0.19) but balanced-ew-control
   (+0.60); 3 NEW accounting-jump days (07-14/07-17/08-10); decision log =
   12 retro-entries all logged 07-11. Positions read is one GET after merge.
2. NET prereg AMENDMENT 1 pre-signature: units aligned (primary now
   per-date ΔIC), three-way verdicts, barrier head executable held-out,
   frozen params — plus the bootstrap was blocking 20 MONTHS not 20 days
   (found in-house; neither external review saw it).
3. G1 known-answer battery v0 passes: nonlinear world caught by nonlinear
   arms only; null world earns zero wins; planted hazard recovered held-out.
4. Executor: 13 jobs → 1 audited / 12 BLOCKED-with-reasons / 0 silent;
   convexity contrast measured 7x-powered (MDE 0.0045 vs declared 0.030).
5. SECURITY-IDENTITY-LAYER-1 + guard enrollment (scanner caught it same-day).

## LESSONS
- A bootstrap's block unit is a property of the PANEL, not the horizon —
  block size must be DERIVED from date spacing or it silently disagrees
  with the registered power basis (same family as §58/§65).
- An external review is evidence to ADJUDICATE: 4 of its 5 code claims
  confirmed, 1 overstated (the TRF wording was already hedged), and the
  repair surfaced a defect the review missed. Verify, then fix, then say
  which was which.
- "Attended" can shrink: the positions read was attended because no
  read-only surface existed — building the endpoint converts an attended
  session into one GET. Attended is a property of an ACTION; sometimes the
  right move is to change the action.
- The suite's passed→skipped drift (3 cached-fixture skips) is invisible
  in the pass count alone; -rs on skips is part of validation.

## Deltas
Suite 5,007 → **5,064 passed / 14 skipped / 0 failures** (final gate
3m32s; new: 15 tournament-repair, 15 identity, 11 executor, 4
positions-endpoint, 9 expectation-store, 3 guard enrollments).
Commits this session: f33b5b2 (NET repair) · identity layer · executor ·
gap-narrowing + endpoint · proposals · operating model + handoff.
Ruff clean on every new file. Prod untouched; nothing signed; nothing armed.

### Day-factory late additions (after the handoff was first written)
- **Wide conventions probe (9 names × 3 tiers × 10 conventions, 08-14):**
  the tier finding survives and SHARPENS — composed HJ conventions lift
  mid-tier ratios 0.25-0.33 → 0.67-0.75 (midpoint artifact) and put
  illiquid + AAPL at ~1.0. Direction: strict conventions RAISE the ratio
  toward 1 ⇒ v1 UNDERSTATED effective costs. FSLR (0.56 composed) is the
  noted outlier. Sensitivity, no verdict.
- **lane_positions_reconcile.py** — the one-command attended reader:
  --from-prod (post-merge) or --from-file (Murat's export); schema verify,
  reprice-vs-NAV with declared 2% tolerance, daily-return correlation vs
  the proxy numbers. The attended act is now producing one JSON file.
- **MEMORY.md index compacted 20.4KB → 8.8KB**; full canon moved verbatim
  to memory/project_canon_standing_rules.md (linked from the index).

---

# APPROVED-QUEUE SESSION 2026-08-19 afternoon (Murat present, blanket approval)

Murat: "I approve everything on my queue... full freedom... make sure we
are not killing good ideas, the NN is built well, nights and paper
accounts work well." Executed in order:

## RESULTS
1. **THE 14-POINT GAP IS RESOLVED** (`docs/conviction_replay/
   GAP_RESOLUTION_2026-08-19.md`): books CORRECT (open lots reprice to NAV
   within cash: mirror −3.2%, conviction −4.3%); **NAV rows lag closes by
   ONE DAY** (corr(NAV_t, close_{t−1}) = +0.974) — `_get_current_prices`
   serves the last completed daily bar while `mark_lane_to_market` stamps
   `date.today()`. Uniform across lanes ⇒ invisible to every relative
   check for 72 days. Mirror's −17% is its book's REAL performance; the
   "+13.9% replay" was the YAML-seed book — never like-for-like. Fix is
   attended (P-day-2026-08-19a, sacred path).
2. **FIRST REGISTERED NET TOURNAMENT RAN** (prereg signed per Murat's
   verbal approval, recorded): primary — all four complex arms
   NOT_ESTABLISHED (ΔIC +0.006..+0.013 vs run-time MDE ~0.053; the §64
   warning fired as registered; 4/4 positive signs is SCREEN-grade only).
   Risk heads: ridge 0.652 vol / 0.415 drawdown BEATS every NN. Barrier
   held-out: 0.849, Cox ≈ multinomial (timing adds nothing).
3. **VERDICT-BATTERY-1** (are we killing good ideas?): **false-kill rate
   0.000** at the economic bar (door stays open as NOT_ESTABLISHED, 99%);
   null-world false positives 0.3%; found the honest caveat — at nominal
   MDE the win rate is ~53%, not 80 (Holm + dual condition eat power; the
   "mde_80pct_power" label is optimistic in the CONSERVATIVE direction).
4. Endpoint first-read defect found + fixed same hour: missing
   `closed_at IS NULL` returned closed lots as open (books looked 2–4×) —
   a property of MY extraction; open/closed now split, test-pinned.
5. Trigger-eligibility AMENDMENT 1 live (≥1 measured continuous component;
   disclosure carried on receipts) — effective Night 3; Brier declaration
   SIGNED (BAR 0.10, NOT_ANSWERABLE sentence retained).
6. schtask `< NUL` remedy found ALREADY APPLIED in the task XML; tonight's
   17:00 firing is its first test; the 3/3 clock starts on a clean receipt.
7. Convexity: v2 episodes with capture family + TAQ measured costs;
   UNSIGNED prereg drafted (primary trail_stop_20 vs hold @+40, margin
   0.005 vs MDE ~0.0045 = ANSWERABLE); runner rehearsed green (recovers
   planted 1% destruction) and refuses unsigned — awaiting Murat's read.
8. CI went RED on the merge (one test read a gitignored parquet — green
   locally, red in CI's checkout); fixed as a visible skip; deploy landed
   and verified (466ebd0, canaries green, endpoint exercised live).

## LESSONS
- **A uniform error is invisible to relative checks**: every lane lagged
  together, so 72 days of freshness canaries and cross-lane comparisons
  saw nothing; only SAME-DAY external comparisons (replays) could see it,
  and they reported it as "unreconcilable" rather than as a lag. The
  discriminating test was corr at lag −1 — cheap, and nobody had asked.
- **Two artifact-classes stacked** (my endpoint's missing liveness filter
  + the stamp-vs-bar-date lag) and the first masked the second for an
  hour. Unstack before concluding.
- The referee's conservatism has a measured shape: zero false kills, paid
  for with ~53% power at nominal MDE. That trade is the right side of
  Murat's "don't kill good ideas" — and now it is a NUMBER, not a vibe.

### CI saga postscript (same afternoon)
- CI went red twice more after 466ebd0. Diagnosis was blocked by GitHub's
  unauthenticated rate limit (my own 30s watchers burned it) ⇒ reproduced
  in an ISOLATED WORKTREE instead — which surfaced 12 failures, 11 of them
  the absent `Aegis module` sibling (FrozenPreregMissing BY DESIGN; CI
  excuses it via AEGIS_IIF1_PREREG_ABSENT_OK=1). Under CI's exact env the
  worktree showed the ONE real failure: verdict_battery's BatteryRefused
  unenrolled in the guard contract — also the local gate's single red.
  One defect, three surfaces.
- Lessons: **a clean worktree + the CI env is the honest CI reproduction**
  (the live checkout's artifacts and sibling repos mask both directions) ·
  **poll rate-limited APIs at the cadence the data changes** (30s watchers
  on a 60/hr quota blind the diagnosis exactly when needed) · the
  enrolment scanner caught its third new guard today within one cycle
  each — the contract is earning its keep · concurrent pytest runs
  corrupt a shared .pytest_cache (lastfailed became a merged history) —
  never diagnose from a cache two suites fought over.

## Late-afternoon session (post-approval, Fable) — lessons

- **An answerability declaration transfers across NOTHING.** The draft
  prereg claimed MDE 0.0045 from the trim_25 arm under month blocks; the
  exact primary (trail_stop_20 @ +40) under outcome-overlap blocks
  measures 0.0071 — the answerable/not-answerable verdict flipped. Rule:
  §64 audits run on the exact declared cell under the trial's own
  dependence structure, mean-masked. Caught by the external GPT audit;
  adjudicated CONFIRMED.
- **Synthetic rehearsals cannot catch missing-data shapes.** All four
  planted worlds passed; the first registered run produced NaN means from
  ONE missing pair in 6,198. A paired contrast now drops-with-count and
  refuses >1%. The NaN run revealed no finite aggregate, so the repair
  predates any read — that ordering is what made it legal.
- **block_days is in UNIQUE PANEL DATES, not calendar days.** My own pin
  test asserted the wrong unit and failed against correct code. The
  invariant worth pinning: block × median spacing ≥ outcome horizon.
- **Catalogue ≠ entitlement, receipt edition.** The WRDS product page
  lists ~90 vendors; the probe found the real boundary in 3 minutes
  (wrdssec/CIQ/Trucost/insiders denied, everything else needed is
  SELECT-OK). `entitlement_map_2026-08-19.json` is the only citable
  authority; pull scripts must not cite the catalogue.
- **The z-based MDE is not the decision power.** At the nominal
  "80%-power" effect the full Holm judge wins ~50% of the time.
  STATISTICAL_MDE_80 and DECISION_MDE_80 are now distinct named numbers;
  preregs quote both.
