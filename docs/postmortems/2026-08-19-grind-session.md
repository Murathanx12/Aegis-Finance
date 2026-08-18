# Grind session 2026-08-18 night → 2026-08-19 (12h unattended, Order 20)

SESSION SUMMARY — (written at end; placeholder until then)

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
