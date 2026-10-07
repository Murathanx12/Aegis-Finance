# Six roles, the benchmark core, and the mirror cap fix: prepared, not launched (C20, 2026-10-07)

Licence: PRODUCT_EXPERIMENT. Nothing below is seeded, ordered, or wired into a lane.

The numbers come from
`backend/data/optimus/paper_accounts/fleet_manager/contracts_v3/PREPARE_20261007T002005Z.json`.
That receipt was built from bars to 2026-10-06, Explorer receipt
`opportunities_2026-10-06_20261006T225957Z.json`, and the PC snapshot of 2026-10-06T23:53Z.

It supersedes `PREPARE_20261006T235536Z.json`, which is kept. This revision applies the adversarial
review `docs/reviews/REVIEW_2026-10-07_C15_C20_PUBLISH_AND_V3_CONTRACTS.md`: H2, H3, M6 (kill
rules), M7 (innovation) and L3.

## RESULTS

- **Six v3 contracts are frozen as `PREPARED_NOT_SEEDED`.**
  - Five were re-hashed after the review. Each old hash is kept in `supersedes`, and the old files
    are under `contracts_v3/superseded/`.
  - The SPY control did not change.
  - No seed path can read any of them (test).
- **D14 benchmark core: H2 is fixed and the flag stays OFF.**
  - The core is now planned in its own `plan_orders` call, after the sleeves. Every PROBE and
    EXPLOIT share count is byte-identical with the flag on or off. A new EXPLOIT-fixture test
    covers both cases: EXPLOIT planned but not acting, and EXPLOIT acting.
  - Today's worst case at $1,002,024: flag OFF −$13,460 (1.34%). Flag ON −$15,973 (1.59%), with a
    12% core and gross/equity 0.32. Full core −$30,194 (3.01%). Of that, the core costs −$46,879 on
    the panel's worst SPY day.
- **H3:** the quant ensemble now trades the **27 two-twin survivors**. "Validation market t ≥ 2" is
  written as the CAPITAL_CANDIDATE promotion gate; 0 rules pass it.
- **Kill rules:** each is now z_21 ≤ −2 on the book-minus-twin series, using the role's own measured
  sd. The sign rule (~21% false kills) is gone. False-kill rate at zero edge: 2.3% per check, 6.7%
  over 63 sessions.
- **Innovation:**
  - A name is eligible only if its 3σ stop fits inside the 20% cap (σ ≤ 6.67%).
  - Every name is sized for a −70% gap at 1%, with gross capped at 14%.
  - The headline worst case is the gap: −$9,800, inside the lane's own 10% line.
- **D13 mirror cap:** proposal only, unchanged. In the two-name state, one name going to zero costs
  −$37,763 without the fix and −$18,881 with it.
- **RESULT IMPROVEMENT: NONE.**

## 1. The six v3 contracts

Common rules:
- **Stops:** 3σ on the 63-session sigma, never loosened.
- **Fills:** DAY limits at ±10 bps of the quote.
- **Objective:** terminal wealth under the declared personality, graded daily against SPY and the
  twin.
- **Entry gross:** scaled down so the one-day 3σ loss stays ≤ 10%.
- **Earliest seed:** 2026-10-26.
- **Kill rule** (`fleet_v3_contracts.kill_block`, the CRSP_BLEND_v0 amendment pattern):
  - Statistic: D_21 is the book-minus-twin return over each non-overlapping 21-session window.
  - Noise: sd_21 is the role's own measured daily gap sd × √21. It is computed only after 21 forward
    sessions; before that there is no performance kill.
  - Kill: z_21 ≤ −2 marks the role DEPRIORITIZED.
  - Scale: the pooled fleet gap sd is 1.19%/day (29 grade rows), which puts the illustrative line at
    −10.9% per 21 sessions. That number is shown for scale; it is not the line.
  - A separate drawdown stop flattens the account to cash.
  - The rule never issues MECHANISM_REJECTED.

| role (account) | policy hash | supersedes | source | gross / name | stop in σ → % | worst case at $100k | twin | drawdown stop |
|---|---|---|---|---|---|---|---|---|
| thematic (hack1) | `ef5140ea6509af23` | `8134a10a21a23ad5` | Explorer `human_ai_thematic_v2` / `roi_v3`, frozen at seed, clipped, never renormalised; 21 sessions | 1.00 / 10% | 3σ, [4%, 12%] | 3σ day at 6.71% −$20,126 → −$10,000 (gross ×0.50); stops −$12,000; ceiling −$100,000 | sticky (TWIN_STICKY_v1) | 20% |
| revision_snowball (hack2) | `31a776e9542cd381` | `228de1efcb1027ff` | net raises ≥ 3 firms / 90 d, top 20 EW; snowball only orders ties; **reputation weights excluded (NOT_PERSISTENT_OOS)** | 1.00 / 5% | 3σ, [4%, 12%] | −$15,125 → −$10,000 (×0.66); stops −$12,000 | sticky | 20% |
| world_news (hack6) | `d8dc2cf92765ede3` | `15fcfd17d80f1f4b` | SHADOW_NEWS d > 0; 1% × (1 + 2·usable_trust) ≤ 3%; trust only by KEY 1 (today 0); 5 sessions | 0.30 / 3% | 3σ, [4%, 10%] | −$4,429; stops −$3,000; ceiling −$30,000 | per-entry matched random twin (5-session hold; reason written in the contract) | 10% |
| quant_ensemble (hack4) | `d775b9d85dd04ec3` | `0bb99e6adf242bb5` | **27 rules with pure-selection t ≥ 2 on both twins**, EW across rules, CANNOT_DISTINGUISH vs the market; CAPITAL_CANDIDATE gate = validation market t ≥ 2 (0 pass) | 1.00 / 10% | 3σ, [4%, 12%] | −$14,763 → −$10,000 (×0.68); stops −$12,000 | each rule's sticky + fair twin, and SPY | 20% |
| innovation (UNASSIGNED; hack3's key answers 401) | `f3267abb8d068bbb` | `1d9146ee44a98dc6` | Explorer HIGH_RISK_INNOVATION, **eligible only if σ ≤ 6.67%** (42 of 47 today); every name gap-exposed → 1%; COVERAGE ×0.5; 2% hard ceiling; 14 names; 63 sessions; 30 bps | **0.14** / 1% (2% ceiling) | 3σ, [6%, 20%]; never clipped below 3σ | **headline: −70% gap on the whole book = −$9,800**; 3σ day −$2,800; ceiling −$14,000 | sticky + a random twin from the same flagged pool | 15% |
| spy_control (hack5) | `430c485cd5e8df7f` | — | 95% SPY, no view | 0.95 SPY | disaster stop 10% | 3σ −$1,986; worst SPY day −$5,562; stop −$9,500 | ideal control | never killed |

**Why nothing can seed them.** This is pinned by `test_no_seed_path_can_read_a_prepared_contract`:
- The contracts live in `contracts_v3/`, which `load_contract` never reads.
- `fleet_manager.load_contract` and `freeze_contract` REFUSE a PREPARED body, even one copied by
  hand into the live folder.
- An AST scan finds no other module that names the folder.

`supersede=True` is allowed only on a PREPARED, never-seeded contract. The old file is kept.

**Owner trap.** `scripts/fleet_manager_run.py` resolves only v1 and v2. A `modes.json` entry of
`"v3"` would run v1 terms. This is pinned by a test, and the runner needs a v3 path first.

## 2. D14: the PC-PAPER benchmark core

SPY is tradable on the PC path as an ordinary Alpaca paper order. No proxy ETF is needed.

**H2 fix:**
- `u_plan` runs the sleeves' `plan_orders` first. When the flag is ON, held SPY is excluded from that
  call.
- It then sizes the core as `min(1 − acting gross after that call, MAX_NAME_FRAC)`.
  - If core plus sleeves would breach the 10% worst-case line, it shrinks the core.
  - The core is planned in a second `plan_orders` call that sees only SPY.
- Before the fix, an 80% wanted core made `plan_orders` rescale every target by 1/total_w. That cut
  the acting PROBE orders by about 42% (1000 → 581 shares).
- The core's orders use the same send path as every other order: the risk-gate block, the venue
  clock, the open-orders check, and the session's broker lease (`sim_run` takes the lease in
  `paper_profit`).
- With the flag OFF, the core function is never called (test).

Worst case at $1,002,024. SPY is priced at its 63-session sigma, 0.70%/day. Today's sleeves are the
10 held names at 20.1%, each priced on its own panel sigma. The hypothetical books use the universe
p90, 4.92%. ρ = 1 throughout.

| book | core | core 3σ | sleeves 3σ | total 3σ | % equity | Σ\|notional\|/equity | core on the worst SPY day (−5.86%) | ≤ 10%? |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **TODAY, flag OFF**: 10 names 20.1%, 79.9% cash | 0% | $0 | −$13,460 | −$13,460 | 1.34% | 0.20 | $0 | yes |
| **TODAY, flag ON (H2-fixed)**: sleeves' shares untouched | 12% | −$2,513 | −$13,460 | −$15,973 | 1.59% | 0.32 | −$7,040 | yes |
| today's sleeves + a full core (needs D22) | 79.9% | −$16,734 | −$13,460 | −$30,194 | 3.01% | 1.00 | −$46,879 | yes |
| same, SPY at the review's stressed 1.2% | 79.9% | −$28,824 | −$13,460 | −$42,283 | 4.22% | 1.00 | −$46,879 | yes |
| largest admissible PROBE (10 × 2% at p90) + full core | 80% | −$16,754 | −$29,585 | −$46,340 | 4.62% | 1.00 | −$46,935 | yes |
| no sleeve acting: 100% core | 100% | −$20,943 | $0 | −$20,943 | 2.09% | 1.00 | −$58,669 | yes |
| EXPLOIT + PROBE at caps, before the gate | 0% | $0 | −$147,926 | −$147,926 | 14.76% | 1.00 | $0 | **no**; the order-path gate scales EXPLOIT down |

There is no stop on PC-PAPER, so the ceiling is the whole gross: −$1,002,024 for a full core.

**What the core does not fix.** `positions_reconciliation` compares cash with contract cash plus the
unheld core. The contract resolves PROBE to 0% "BY CONSTRUCTION", so the line stays POSITIONS_DISAGREE
by the 20% PROBE sleeve, with any core or none. Once the sleeve is counted, even a 12% core reads OK:
the check reconciles cash, not exposure. This is pinned by
`test_what_the_core_does_and_does_not_reconcile`.

### Recommendations (D21, D22), flag stays OFF

- **D21: should `decision_contract` count the acting PROBE/EXPLOIT gross? YES.**
  - This is a correctness fix, not a loosening. The bug exists with or without the core (review L4).
  - Without it, the reconciliation stays red forever.
  - Build it next, from `intended_book.json`'s acting weights.
- **D22: should SPY be exempt from MAX_NAME_FRAC? YES, but only for `PC_BENCHMARK_CORE_SYMBOL`.**
  - Cap it under its own `PC_BENCHMARK_CORE_MAX_FRAC` (proposed 0.80).
  - Do this only now that H2 is fixed, and only after D21.
  - Single-name concentration does not apply to a 500-name index. The cost is that the core's worst
    SPY day becomes −$46,879, against −$7,040 at the 12% clip.
- **Until both are done, keep `PC_BENCHMARK_CORE = False`.**
  - The flag alone buys a 12% core.
  - Grading against SPY already happens in `decision_ledger`, so the flag alone adds no information.
    It only cuts 12 points of cash drag.

Caveats:
- Turning the flag OFF later does not sell the core unless EXPLOIT is acting. Close the core in the
  broker UI, or by a new version.
- On days the core is held, the decision-story replay sees one extra non-selection target.

## 3. D13: the mirror cap hole (proposal only, unchanged)

`backend/services/rules_capfix_proposal.py::enforce_position_limits_with_cash`:
- It applies when n × cap < 1. It is a waterfill in which excess that has no room goes to CASH, and
  sector trims also go to cash.
- When n × cap ≥ 1 it defers to `rules.enforce_position_limits` unchanged.
- No lane path imports it (pinned by AST).
- Wiring it is attended `lane-integrity-check` work. Show first that the reference engine carries a
  CASH weight.

Mirror NAV $75,525.03, declared cap 25%:

| state | largest name | one name → 0 | one name −50% | 3σ day | gross |
|---|---:|---:|---:|---:|---:|
| 06-16 → 07-14, 2 names, without fix | 50% | −$37,763 | −$18,881 | −$7,459 | 1.00 |
| same, with fix | 25% (+50% cash) | −$18,881 | −$9,441 | −$3,730 | 0.50 |
| today, 12 names (fix is a no-op) | ≤ 25% at a rebalance | −$18,881 | −$9,441 | — | ~1.00 |

## 4. Owner steps

**D2.** Per account, and not before 2026-10-26:
1. Archive: `python -m scripts.fleet_v3_prepare --archive`. It copies `state/`, `decisions.jsonl`,
   `grades.jsonl`, `modes.json` and `contracts/` with a sha256 manifest, and never moves anything.
2. Take a last DRY broker read: `python -m scripts.fleet_manager_run --pass open --roles <acct>`,
   without `--live`.
3. Reset accounts in the Alpaca UI if wanted. The innovation lane also needs an account: regenerate
   hack3's keys, or open a new paper account.
4. Give `fleet_manager_run.py` a v3 path.
5. Activate one role at a time:
   - Re-freeze the prepared body into `fleet_manager/contracts/` with `status` changed and `seed`
     filled.
   - Check that `activation_diff(...)["same_rule"]` is True.
   - In `modes.json`, set `contract=v3` and run DRY. Switch to LIVE after one clean DRY pass.

**D14.** Do D21, then D22, then flip `PC_BENCHMARK_CORE`. Not before.

**D13.** Say yes. The wiring session runs `lane-integrity-check` before and after.

## Files

- New:
  - `backend/services/fleet_v3_contracts.py`
  - `backend/services/benchmark_core.py`
  - `backend/services/rules_capfix_proposal.py`
  - `scripts/fleet_v3_prepare.py`
- Changed:
  - `backend/services/fleet_manager.py`: `_refuse_prepared`.
  - `scripts/sim_run.py`: `_benchmark_core_flag` and `_plan_benchmark_core` (H2: its own
    `plan_orders` call after the sleeves), and the CORE state.
  - `backend/config.py`: the C20 block.
- Tests:
  - `backend/tests/test_fleet_v3_contracts.py`
  - `backend/tests/test_benchmark_core.py`, including the EXPLOIT-fixture test
    `test_flag_on_leaves_every_sleeve_share_count_byte_identical`
  - `backend/tests/test_rules_capfix_proposal.py`
- Data: `backend/data/optimus/paper_accounts/fleet_manager/contracts_v3/`, holding the six
  contracts, the `superseded/` folder and two PREPARE receipts.
