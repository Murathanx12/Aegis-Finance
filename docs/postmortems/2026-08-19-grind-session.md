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

Note for next attended session: `gh` CLI is not installed on this machine —
the prod-monitor ≥19:00 firing check needs the Actions UI or a token.
