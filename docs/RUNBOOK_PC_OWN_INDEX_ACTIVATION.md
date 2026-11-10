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
`PC_BENCHMARK_CORE` ships False and `PC_OWN_INDEX` ships False.

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

**Turning `PC_BENCHMARK_CORE` off alone does not sell SPY.** A held SPY that no
sleeve owns is state `EXIT`, and only an acting EXPLOIT sends `EXIT` orders.
EXPLOIT has been refused for weeks (ranker `top20_net_rel_21d` −0.76%), so SPY
would just stay. `PC_OWN_INDEX` is the flag that retires it (`CORE_EXIT`).

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
  a 1% cash buffer) and passes two tests: (1) the whole book's one-day ρ=1 3σ loss
  is at most 10% of equity; (2) G × |the members' worst 21-session basket return|
  is at most 10%. This is the same rule the revision_flow sleeve answers. An
  unknown bound fails.
* **One symbol, one sleeve:** a member that an *acting* sleeve holds is skipped.
  A member held by a non-acting sleeve is adopted and resized. A name that leaves
  the index at a rebuild is sold (`OWN_INDEX_EXIT`).
* **Refusals:** each one is red and never falls back to SPY. A stale, undateable,
  empty or unreadable candidate file means no index buys and held members `HOLD`.
  SPY is still retired in that case, because cash is allowed. With no valid frozen
  contract, nothing moves, not even SPY. If `PC_BENCHMARK_CORE` and `PC_OWN_INDEX`
  are both True, the index is refused and the core plans as before. The CLI exits
  2 (stale/empty/receipt) or 3 (contract).

## 3. Worst case first (protocol item 4)

From the dry-run on 2026-11-10 at broker equity $948,803:

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

**Owner decision OD-10a (open):** keep bound 2 on the index? If yes (the shipped
default), the index is 30% and about 35% of equity sits in cash. If the index is
held only to the one-day bound, as the SPY core was, it is 60% and about 5% is cash
(3σ day −$75,038 = 7.91%; worst 21 sessions −$167,101). A builder does not widen a
bound. Only the owner can, by changing
`PC_OWN_INDEX_MAX_WORST_21_SESSION_LOSS_FRAC` and bumping `PC_OWN_INDEX_VERSION`.

## 4. Runtime-side steps, in order (brain session, owner watching)

Never reset, stash, checkout, clean or pull in the runtime checkout. Apply the
change between sessions. The running sim imported its config at start, so a file
edit reaches the next session only. Today's session `fdc4649e67f3` ends 22:10Z
(06:10 HKT). The next start window opens at 09:00 ET (14:00Z, 22:00 HKT).

0. **Check:** `backend\data\optimus\sim\session.json` must not be `RUNNING`, or
   wait for its `planned_end`. Do not kill it. A STOP file finishes the cycle.
1. **Back up the two runtime files** by copying them (not with git) to
   `C:\Users\mrthn\AEGIS_DOCUMENTS\od10_backup_<date>\`: `scripts\sim_run.py` and
   `backend\config.py`. Record `git -C C:\Users\mrthn\aegis-finance status
   --porcelain -- scripts/sim_run.py backend/config.py`.
2. **Copy the two new files** from the PR branch `s65/od10-own-index` into the
   runtime checkout: `backend/services/pc_own_index.py` and `scripts/pc_own_index.py`.
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
   This was verified on 2026-11-10 against copies of the runtime files. All 10 hunks
   applied (offsets −15..−396 lines) and both files parse. The PR's 26 own-index
   tests passed when run against a copy of the runtime code with the patch applied.
   After this step `PC_BENCHMARK_CORE = False` and `PC_OWN_INDEX = False`. SPY is
   held and untouched (state EXIT, not sent), so this is a safe intermediate state.
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
6. **Flip:** in the runtime `backend\config.py`, set `PC_OWN_INDEX = True`. Leave
   `PC_BENCHMARK_CORE = False`.
7. **First session** (paper_profit, venue open): check `pc_book\<day>\intended_book.json`.
   `own_index_line` should show `20 of 20 declared x 1.50%`. `sent` should show
   `CORE_EXIT` SPY and `OWN_INDEX` buys. `sendable_by_state` should carry
   `CORE_EXIT: 1`. After the next snapshot, `pc_book\state_latest.json` should show
   no SPY and cash of about 35% (or about 5% under OD-10a = one-day only).
8. **Watch** `decisions\pc_plan\own_index_members.json` (current membership +
   twin) and `own_index_members_history.jsonl` (every rebuild).

## 5. Rollback

* **Stop the index, keep the stocks:** set `PC_OWN_INDEX = False`. The index's
  holdings become unowned (`EXIT`, not sent while EXPLOIT is refused). Nothing is
  sold and SPY is not re-bought.
* **Undo OD-10 (owner only):** set `PC_BENCHMARK_CORE = True` and
  `PC_OWN_INDEX = False`. The D14 core buys SPY back to the residual on the next
  session.
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
