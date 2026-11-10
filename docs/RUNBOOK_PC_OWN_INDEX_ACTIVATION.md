# Runbook: activating PC-PAPER's own index (OD-10)

Owner decision 2026-11-10 (OD-10, `docs/ROADMAP.md` §3): PC-PAPER stops holding an
SPY core. *"It should go for specific stocks and make its own index."* SPY stays
the benchmark only. Cash, never SPY, fills an empty slot. This is a paper account
(Alpaca paper, no real money). Activation is **attended**: dry-run first, the owner
reads the would-be orders, then the flag is flipped.

Code: `backend/services/pc_own_index.py` (construction, frozen contract, sizing,
measurement), `scripts/pc_own_index.py` (dry-run / freeze / measure; it never
sends an order), the hook in `scripts/sim_run.py` `u_plan` (where the D14 core was
planned), and the config block `PC_OWN_INDEX*` in `backend/config.py`.
`PC_BENCHMARK_CORE` ships **True** and `PC_OWN_INDEX` ships False, so merging this
PR changes nothing any account holds. The SPY core is retired only by the attended
activation in §4, which sets both flags in ONE edit.

### Review fixes (2026-11-11, adversarial review of PR #89)

| finding | what the code now does | pinned by |
|---|---|---|
| R1: core OFF on main orphaned ~$474k of SPY (an EXIT the first EXPLOIT-acting session would send) | main ships `PC_BENCHMARK_CORE = True`. If the core is ever OFF without the own index, a held SPY is **HELD** (`benchmark_hold` on the receipt): never planned, never an EXIT | `test_pc_own_index_review.py::test_core_off_without_the_own_index_never_plans_a_spy_sell`, `test_main_ships_the_spy_core_on...` |
| R2: a contract that stops verifying (any edit to `pc_own_index.py` or a key it reads) turned the held index into EXITs | the held members are read from the membership file BEFORE the contract and HELD; the session sends **no order at all** (`send_block: own index contract REFUSED`); `u_plan` raises after writing its receipt (the plan unit is red); a `paper_profit` session with `PC_OWN_INDEX = True` and a non-verifying contract does not start (**rc 7**, `REFUSED_OWN_INDEX_CONTRACT`). Rollback (`PC_OWN_INDEX = False` with a membership on disk) HOLDS the members (`own_index_rollback_hold`) | `test_a_contract_that_stops_verifying_refuses_and_liquidates_nothing`, `test_rollback_flag_off_holds_the_index_names...`, `test_the_session_start_refuses_non_zero...` |
| R3: index buys went out when the SPY sell was skipped (open order) or failed: margin | index buys are sent LAST, only after **every** sell of the session was submitted and is confirmed `filled` (`order_by_client_id`, up to `PC_OWN_INDEX_SELL_FILL_WAIT_S` = 60 s); then the account is re-read and buys are cut to `cash - 1% buffer - other buys` and to `long market value + buys <= 99% of equity`, at plan price + 0.5%. A skipped, failed or unconfirmed sell, or an unreadable account: no index buy this session | `test_no_index_buy_when_the_spy_sell_is_skipped...`, `..._fails`, `..._not_confirmed_filled`, `test_index_buys_are_sized_from_cash_after_the_fills`, the `test_gate_*` tests |
| R4: a young listing dropped 2020 from the binding window and lifted the index 30% -> 60% | the gross never exceeds `PC_OWN_INDEX_MAX_GROSS` (**0.30**, raised only by an explicit config change + new version). The 21-session bound reads a FIXED window from `PC_OWN_INDEX_HISTORY_START` (2020-01-02); a member first priced more than 10 days after it is EXCLUDED (slot cash); the bound is min(all-priced, any-coverage) | `test_a_young_listing_is_excluded...`, `test_the_index_never_exceeds_the_owner_approved_share`, `test_the_plan_leaves_a_short_history_members_slot_in_cash` |
| O1: the ADV cap was inert for the index | each member's `median_dollar_vol` from the candidate file is stored in the membership row and passed to `pc_broker.plan_orders` (2% ADV cap) | contract text |
| O5: the dry-run models other sleeves coarsely | the dry-run prints that caveat | CLI |

Not changed: O3 (there is still no whole-book 21-session bound; the index and
revision_flow are each bounded at 10% separately, so a correlated month can cost
~19% plus the residual names).

### Second review fixes (2026-11-11, `REVIEW2` of PR #89)

| finding | what the code now does | pinned by |
|---|---|---|
| B1: a refused 21-session/one-day bound planned a full SELL of every held member (and of SPY) | a refusal of ANY kind holds EVERYTHING: no index sell, no leaver sell, no SPY sell. SPY is retired (`CORE_EXIT`) only in a plan that also BUYS the index; a leaver is sold only at a SUCCESSFUL rebuild (members chosen and sized); a held member excluded for short history is HELD. Both flags True: the held members HOLD (`own_index_rollback_hold`). `_plan_own_index` raising: the owned names HOLD | `test_pc_own_index_review2.py::test_no_refusal_of_any_kind_produces_a_sell_intent` (13 refusal paths through the real `u_plan`), `test_plan_refusal_plans_no_sell` (10 inputs to `plan()`), positive controls `test_a_leaver_is_sold_only_at_a_successful_rebuild`, `test_plan_success_retires_spy_and_sells_the_leaver` |
| O3 (first review) / review2 O3: a stale funnel sold SPY into cash | resolved by B1: a stale, empty or unreadable candidate file holds SPY too; the account stays as it is until a membership can be built and sized | `...[candidate_file_stale]` |
| R5: the 30% owner cap in `plan()` and `min(full, any)` were unpinned (mutants passed) | tests that fail under each mutation | `test_plan_caps_the_index_at_the_owner_approved_share`, `test_u_plan_never_sizes_the_index_above_the_owner_approved_share`, `test_the_bound_is_the_worse_of_full_and_any_coverage` |
| B2: the RUNTIME's `pc_broker` has no `order_by_client_id`, so the buy gate stalled 60 s and refused the index buys after the SPY sale | the gate confirms fills with `order_by_client_id` where it exists, else with `orders(status="all", limit=500)` (both broker versions have it, newest first); a broker with neither refuses at once. All-or-nothing in intent: with no lookup, `u_plan` refuses (everything HOLDS, no SPY sale), the session start returns **rc 7**, and the dry-run returns rc 2. The startup refusal runs BEFORE the lease is opened, so the patched `run()` calls no lease API on that path (the runtime's `close_lease` takes no `expected_nonce`) | `test_gate_confirms_fills_through_orders_when_the_broker_has_no_client_id_lookup`, `test_u_plan_on_a_runtime_shaped_broker_still_buys_the_index_after_the_spy_sell`, `test_the_session_start_refuses_when_the_broker_cannot_confirm_a_fill`, `test_dry_run_reads_the_fill_lookup_from_the_broker_source` |

Still open (owner/brain): O1 (one contract key halts every PC-PAPER sleeve with rc 7 -- loud, by design; see §5), O2 (REVISION_FLOW/PROBE/EXPLOIT buys are not funding-gated; pre-existing), O4 (the contract does not hash `scripts/sim_run.py`), N2-N6.

## 1. What runs today, and where

| piece | where it runs | version |
|---|---|---|
| `AegisSimOwner` (every 30 min) → `python -m scripts.task_keeper sim` → `scripts/sim_run.py` session, mode `paper_profit` | runtime checkout `C:\Users\mrthn\aegis-finance`, branch `wip/2026-10-07-day`, `.venv` | runtime `sim_run.py` is clean at the wip HEAD. It has no epoch code: main's `sim_run.py` carries 454 more lines, and runtime `pc_broker.py` is 572 lines shorter |
| PC-PAPER orders | `sim_run.u_plan` → `pc_broker.submit` (market DAY orders, whole shares, `aegispc-` client ids, session lease) | same checkout |
| `PC_BENCHMARK_CORE = True`, D22 exempt, revision_flow sleeve 30% | runtime `backend/config.py` (dirty, but the `PC_*` block matches main) | owner D14, 2026-10-07 |

On 2026-11-05 (the last plan receipt) the book was: revision_flow 30%, ten old
PROBE names held but not traded (20.6%; PROBE is MEASURED_NEGATIVE), and SPY at
48.4% (`benchmark core: ON ... delivers 48.40%`). Broker truth on 2026-11-10 14:10Z
was equity $948,802.98, cash $3,612.77, and SPY 633 sh = $473,718 (49.9%).

**Turning `PC_BENCHMARK_CORE` off alone does not sell SPY.** Before the review
fix a held SPY that no sleeve owned was state `EXIT`, which an acting EXPLOIT
would have sent the first day the ranker turned positive. Now it is HELD
(`benchmark_hold`) and only `PC_OWN_INDEX` retires it (`CORE_EXIT`).

The prepared no-index epoch on main (`pc_policy_epoch.py`, `ACTIVATION_ALLOWED =
False`, "pending independent review") would have filled the old core's slot with
cash. Its contract pins the source of 15 files as of 2026-10-10. This change edits
two of them, so that epoch now fails closed (`policy source changed`). It was
never activated and is superseded by OD-10.

## 2. The construction (frozen contract `own_index_v1`)

* **Members:** the opportunity funnel's candidates (`funnel_night10.json`: 5,323 →
  1,500 → 250 → 40 → 25, ranked by `profitability_small` and filtered by low
  volatility and liquidity). One line per issuer. SPY, broad index ETFs and the
  revision_flow names are excluded. Top 20 in funnel score order. The membership
  is frozen for 7 days and then rebuilt. The file may be at most 10 days old by its
  own `generated_at`, the age at which `u_funnel` rebuilds it.
* **Weights:** equal. `w = min(3%, G/20)`. When fewer than 20 names qualify, the
  empty slots stay cash.
* **Gross G:** the largest 5% step that fits in what the other sleeves leave (less
  a 1% cash buffer), never above `PC_OWN_INDEX_MAX_GROSS` = 30%, and passes two
  tests: (1) the whole book's one-day ρ=1 3σ loss is at most 10% of equity; (2) G
  × |the members' worst 21-session basket return over the fixed window from
  2020-01-02| is at most 10%. A member without that history is excluded (slot
  cash). An unknown bound fails.
* **One symbol, one sleeve:** a member that an *acting* sleeve holds is skipped.
  A member held by a non-acting sleeve is adopted and resized. A name that leaves
  the index at a SUCCESSFUL rebuild is sold (`OWN_INDEX_EXIT`); a held member
  excluded for short history is held.
* **Refusals:** each one is red, never falls back to SPY, and **sells nothing**
  (review2 B1). A stale, undateable, empty or unreadable candidate file, no
  qualifying member, an unknown or failing bound, or a broker that cannot confirm
  a fill: no index buy, held members `HOLD`, leavers `HOLD`, and SPY `HOLD`. SPY
  is retired only in a plan that also buys the index. With no valid frozen
  contract, nothing moves either. If `PC_BENCHMARK_CORE` and `PC_OWN_INDEX`
  are both True, the index is refused and the core plans as before. A contract
  that stops verifying holds EVERYTHING (no order of any sleeve; rc 7 at session
  start). The CLI exits 2 (stale/empty/receipt) or 3 (contract).

## 3. Worst case first (protocol item 4)

**Re-printed after the review fixes** (dry-run 2026-11-11 of this branch's code on
the runtime's files, read-only: broker receipt 2026-11-10T14:10Z, funnel
generated 2026-11-05T19:18Z (4.9 d old, 25 candidates -> 24 issuers), deep panel
2016-01-05..2026-11-09; no member was excluded for short history), equity $948,803:

> Source of these numbers: the read-only dry-run of this branch re-run after the
> second review's fixes at 2026-11-10T18:43Z (02:43 HKT 11-11) on the runtime's
> files (rc 0; same broker receipt, funnel 5.0 d old, 24 issuers): every line
> below reproduced, 3σ day **−$18,798**. The −$19,124 in the first fixer's report
> came from an earlier dry-run that treated the funnel's 25 rows as 25 issuers
> (no issuer map); the −$18,798 figure is the one kept.

* **Largest admissible index:** min(20 × 3.00% = 60%, owner max 30%) = **30% gross**.
  No stop is declared, so n × notional × stop = 20 × 1.50% × 100% = **−$284,641**
  (was −$569,282 before the fix). ρ=1 3σ day 30% × 3 × 2.20% = **−$18,798**. Worst
  21 sessions (−29.35%, to 2020-03-16, all 20 priced since 2020) = **−$83,551**.
* **Planned:** 20 × 1.50% = 30% gross, binding `owner_max_gross` (bound 2 alone
  would allow 34%). With the rest of the book (revision_flow 30% + residual
  5.85%): 3σ day **−$56,240 (5.93%)**; Σ|notional|/equity **0.66**; no-stop
  ceiling of the whole book 0.66 × $948,803 = −$626,210.
* Would-be orders: CORE_EXIT sell 633 SPY (~$473,718), 6 trims, 13 buys of
  ~$14.2k; sells $510,005, buys $184,341; cash after ~$329k (34.7%), gross ~65%.
  The buys go out only after the SPY sell is confirmed filled (R3).

The original numbers from the 2026-11-10 dry-run (before the fixes) follow.

* **Largest admissible index:** 20 × 3.00% = 60% gross. No stop is declared, so
  n × notional × stop = −$569,282. The ρ=1 3σ day is 60% × 3 × 2.20% = −$37,596.
  The worst 21 sessions (−29.35%, to 2020-03-16, all 20 priced, prices_deep
  2016..2026-11-09) = −$167,101.
* **Planned (both bounds):** 20 × 1.50% = 30% gross, with **bound 2 binding**.
  The 3σ day is −$18,798. With the rest of the book (revision_flow 30% + three
  untraded names 5.85%), the total is −$56,240 (5.93%). Σ|notional|/equity is 0.66.
  The worst 21 sessions on the index = −$83,551.
* **For comparison:** the retired SPY core at 49% × SPY's worst 21 sessions
  (−32.8%, 2020-03-23) = 16.1% of equity. It was never held to bound 2.

Would-be orders that day (sells first): CORE_EXIT sell 633 SPY (~$473,718). It
trims 6 adopted names (IRMD, AMZN, AAPL, UNFI, TXRH, META) to 1.5%. It buys 13
new names at ~$14.2k each (PBI, MRTN, NPKI, JBSS, GEN, RGR, ESE, INGR, SGI, MSFT,
FELE, GOOGL, TSM). Sells come to $510,005 and buys to $184,341. Cash after is about
$329k (34.7%) and gross is about 65%.

**Owner decision OD-10a (open):** keep the index at 30%? If yes (the shipped
default), about 35% of equity sits in cash. If the index is held only to the
one-day bound, as the SPY core was, it is 60% and about 5% is cash (3σ day
−$75,038 = 7.91%; worst 21 sessions −$167,101). A builder does not widen a bound.
Only the owner can, by raising `PC_OWN_INDEX_MAX_GROSS` (to 0.60) AND
`PC_OWN_INDEX_MAX_WORST_21_SESSION_LOSS_FRAC`, then bumping `PC_OWN_INDEX_VERSION`
and re-freezing. Neither can move on its own any more.

## 4. Runtime-side steps, in order (brain session, owner watching)

Never reset, stash, checkout, clean or pull in the runtime checkout. Apply the
change between sessions. The running sim imported its config at start, so a file
edit reaches the next session only. Read the current session and its
`planned_end` from `backend\data\optimus\sim\session.json` (do not rely on a
session id written here). The start window opens at 09:00 ET (14:00Z, 22:00 HKT).

0. **Check:** `backend\data\optimus\sim\session.json` must not be `RUNNING`, or
   wait for its `planned_end`. Do not kill it. A STOP file finishes the cycle.
1. **Back up the two runtime files** by copying them (not with git) to
   `C:\Users\mrthn\AEGIS_DOCUMENTS\od10_backup_<date>\`: `scripts\sim_run.py` and
   `backend\config.py`. Record `git -C C:\Users\mrthn\aegis-finance status
   --porcelain -- scripts/sim_run.py backend/config.py`.
2. **Copy the two new files** from the PR branch `s65/od10-own-index` into the
   runtime checkout: `backend/services/pc_own_index.py` and `scripts/pc_own_index.py`.
   The runtime's `backend/services/pc_broker.py` is NOT changed: it has no
   `order_by_client_id`, and the buy gate confirms fills with its `orders()`
   instead (review2 B2). The dry-run in step 4 prints `fill confirmation:
   pc_broker.orders` on the runtime; if it prints REFUSED, stop.
3. **Patch the two edited files.** The runtime is not main, so apply the PR's hunks
   instead of copying main's files:
   ```
   git -C C:\Users\mrthn\aegis-finance fetch origin
   git -C C:\Users\mrthn\aegis-finance diff origin/main...origin/s65/od10-own-index -- scripts/sim_run.py backend/config.py > od10.diff
   # three dots = from the merge base, so a main that moved on does not leak into the patch
   # the runtime files are CRLF: convert the diff (sed 's/$/\r/') then, from the runtime root:
   patch -p1 --binary --dry-run < od10_crlf.diff     # must report every hunk "succeeded"
   patch -p1 --binary < od10_crlf.diff
   ```
   Verified on 2026-11-11 AFTER the second review's fixes, against byte copies of
   the runtime's `scripts/sim_run.py` and `backend/config.py` (see the
   review2-fixes report for the hunk count and fuzz). Re-run the `--dry-run`
   anyway and stop at the first hunk that does not apply. After this step
   `PC_BENCHMARK_CORE = True` and `PC_OWN_INDEX = False`: the runtime plans exactly
   as before (the core is ON), so this intermediate state changes nothing.
4. **Dry-run.** The owner reads it:
   ```
   .venv\Scripts\python.exe -m scripts.pc_own_index dry-run --out backend\data\optimus\decisions\pc_plan\own_index_dryrun_<UTC>.json
   ```
   rc must be 0. It prints the broker receipt's age, the contract hash, the
   membership with the candidate file's age and size, the worst case in dollars,
   the random twin, and every would-be order with its state. rc 2 means a stale or
   empty candidate file or a stale broker receipt. Refresh with
   `python -m backend.services.opportunity_funnel` or let the sim's `u_funnel` do
   it, then re-run.
5. **Owner says yes.** Then freeze (once per version):
   ```
   .venv\Scripts\python.exe -m scripts.pc_own_index freeze
   ```
   This writes `backend\data\optimus\decisions\pc_plan\own_index_contract.json`.
   Write the policy hash into the roadmap changelog.
6. **Flip, both flags in ONE edit, between sessions:** in the runtime
   `backend\config.py` set `PC_BENCHMARK_CORE = False` AND `PC_OWN_INDEX = True`.
   This is the single planned transition that retires SPY. Never flip only one:
   core OFF alone HOLDS SPY (`benchmark_hold`), and both True refuses the index.
7. **First session** (paper_profit, venue open): check `pc_book\<day>\intended_book.json`.
   `own_index_line` should show `20 of 20 declared x 1.50%`. `sent` should show
   `CORE_EXIT` SPY and `OWN_INDEX` buys; `own_index.buy_gate.fill_lookup` should
   read `orders` on the runtime. `sendable_by_state` should carry `CORE_EXIT: 1`.
   If instead `own_index_line` says `REFUSED ... nothing is sold or bought`, SPY
   is still held: that is the intended refusal, not a half-done transition. After the next snapshot, `pc_book\state_latest.json` should show
   no SPY and cash of about 35% (or about 5% under OD-10a = one-day only).
8. **Watch** `decisions\pc_plan\own_index_members.json` (current membership +
   twin) and `own_index_members_history.jsonl` (every rebuild).

## 5. Rollback

* **Stop the index, keep the stocks:** set `PC_OWN_INDEX = False`. With the
  membership file on disk the held members are HELD (`own_index_rollback_hold`),
  never exited, even if EXPLOIT acts. Nothing is sold and SPY is not re-bought.
  Selling them later is a separate attended decision.
* **Undo OD-10 (owner only):** set `PC_BENCHMARK_CORE = True` and
  `PC_OWN_INDEX = False`. The D14 core buys SPY back to the residual on the next
  session. The held index members stay HELD and are owned by no sleeve until a
  separate attended decision sells them (review2 N5: with EXPLOIT or PROBE acting,
  the core's SPY target is then oversized on the receipt; the post-fill clip
  still caps gross at 99%).
* **A contract key changed (review2 O1):** with `PC_OWN_INDEX = True`, any edit to
  `backend/services/pc_own_index.py` or to a config key the contract hashes
  (`PC_OWN_INDEX_*`, `PROBE_WORST_CASE_SIGMA`, `FLEET_MANAGER_COST_BPS_PER_SIDE`,
  `FLEET_MANAGER_SIGMA_WINDOW`, `PC_WORST_CASE_MAX_FRAC_OF_EQUITY`) stops EVERY
  PC-PAPER sleeve: each session ends rc 7 (`REFUSED_OWN_INDEX_CONTRACT`) until
  someone bumps `PC_OWN_INDEX_VERSION` and re-freezes, or sets
  `PC_OWN_INDEX = False`. A CH-05 runtime merge that touches any of these must
  re-freeze in the same attended step.
* **Remove the code:** copy the two backed-up files back and delete the two new
  files. `own_index_contract.json` and the members files are inert without the
  code. Move them to `AEGIS_DOCUMENTS` and do not delete them; they are receipts.

## 6. How the result is measured (an observation, never a claim)

* `python -m scripts.pc_own_index measure`: the equal-weight buy-and-hold return
  of the current members from the membership-freeze close to the newest bar. It
  shows the index, its sigma-decile matched random twin (drawn at freeze, seed
  from `sha256(policy_hash + frozen_utc)`, pool = the bars panel) and SPY over
  the same window. This is gross of costs.
* **Per name:** `OWN_INDEX` sleeve decision rows (`sim_run.u_plan.own_index`,
  hypothesis `PC_SLEEVE_OWN_INDEX`) are graded by the nightly grader at 1/5/21
  sessions as excess over SPY.
* **Per account:** PC-PAPER broker NAV from `pc_book\nav.jsonl` (SPY sampled at
  the same instant) vs SPY, from the activation session.
* **Words:** "PC-PAPER is X% vs SPY Y% over N sessions since <date>; the random
  twin of the same size is Z%." Label it OBSERVED until `book_dna.evidence_label`
  raises it. The claim line stays `CLAIMS PROMOTED: none`. Known before
  activation: the PROBE shortlist built from this same funnel graded
  MEASURED_NEGATIVE at h=5 (−0.76% per decision day, 22 days). No selector on
  disk has positive held-out *directional* skill. The own index exists because the
  owner chose stocks over SPY, not because of evidence of edge.

## 7. Compatibility with the six-account reset (OD-11)

* The contract names the account by config key, not by number. A reset that
  rotates the account number (`AEGIS_PC_PAPER_ACCOUNT` / `PC_PAPER_ACCOUNT_NUMBER`)
  and keys does not change the policy hash. A reset is a new inception, so bump
  `PC_OWN_INDEX_VERSION` and re-freeze, which keeps the old track record separate.
* The own index is one rule-fixed, membership-dynamic selector on the funnel's
  quality, low-vol and liquidity ranking. That is a different alpha source from
  the analyst-revision score all five leaders share (CH-17 note), so it fits
  "one selector per account". If revision_flow moves to its own account at the
  reset, its 30% leaves PC-PAPER and the index's room grows by rule. No code
  change is needed.
* At $100k a 1.5% slot is $1,500. With whole shares, a high-priced name rounds
  badly (MSFT ~$545 → 2 sh = $1,090). The drift band (10% of target) is below
  `MIN_ORDER_USD` ($250) at that size, so rebalances mostly will not fire.
* **Logins:** seven paper accounts exist today: hack1–hack6 plus PC-PAPER
  (`PA37CSAUFCQR`). OD-11 says "six accounts, two logins" while CH-17 says
  "PC-PAPER kept". If PC-PAPER is a seventh account, three Alpaca logins are
  needed at three paper accounts per login. The owner should state which.
* **Key names** (names only): PC-PAPER reads `ALPACA_PC_KEY_ID` /
  `ALPACA_PC_SECRET_KEY` (aliases `PC-PAPER_key`, `PC_PAPER_KEY`,
  `PC-PAPER_secret`, `PC_PAPER_SECRET`) in `aegis-finance/.env`. The fleet reads
  `AAT_HACK<n>_KEY_ID` / `AAT_HACK<n>_SECRET_KEY` (n = 1..6) in
  `aegis-alpha-terminal/.env`. Never alias them onto `APCA_*` (ACCOUNTS doc).
