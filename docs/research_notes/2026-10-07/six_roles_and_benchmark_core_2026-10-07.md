# Six roles, the benchmark core, and the mirror cap fix: prepared, not launched (C20, 2026-10-07)

Licence: PRODUCT_EXPERIMENT. Nothing below is seeded, ordered, or wired into a lane. Every number
comes from `backend/data/optimus/paper_accounts/fleet_manager/contracts_v3/PREPARE_20261006T235536Z.json`
(bars to 2026-10-06; Explorer receipt `opportunities_2026-10-06_20261006T225957Z.json`).

## RESULTS

- **Six v3 contracts frozen as `PREPARED_NOT_SEEDED`** under `fleet_manager/contracts_v3/`. Each has
  a policy hash and a rule hash. No seed path can read them, and a test pins that.
- **D14 (benchmark core): built behind `config.PC_BENCHMARK_CORE = False`.** With the flag OFF the
  plan is byte-identical (test). With it ON, the core is clipped to **12%** by `pc_broker.MAX_NAME_FRAC`,
  which I left unchanged. Worst case at $1,002,024:
  - **flag as built:** 3σ day −$32,098 (3.20%), gross/equity 0.32.
  - **full 80% core:** 3σ day −$46,340 (4.62%), gross 1.00. Of that, the core alone is −$16,754 at
    SPY's 0.70%/day sigma, or **−$46,935 on the panel's worst SPY day (−5.86%, 2025-04-04)**.
- **The core does not make `positions_reconciliation` go OK.** The gap is the 20% PROBE sleeve, which
  the contract resolves to 0% by construction. It is not the core (details in §2).
- **D13 (mirror cap hole): proposal written and tested, not wired.** In the two-name state, the
  worst case for one name going to zero falls from **−$37,763 to −$18,881** (mirror NAV $75,525). For
  today's 12-name book the fix is a no-op.
- RESULT IMPROVEMENT: NONE. Nothing trades differently tonight.

## 1. The six v3 contracts

Common to all six:
- 3σ stops on 63-session sigma. A replaced stop is never loosened.
- Fills are DAY limits at ±10 bps of the quote.
- The objective is terminal wealth under the declared personality, graded daily against SPY and
  against the twin.
- Gross is scaled **down** at entry so the one-day 3σ loss stays ≤ 10% of equity
  (`FLEET_V3_MAX_K_SIGMA_DAY_LOSS_FRAC`). Gates only shrink.
- Earliest seed date is 2026-10-26.
- No contract is killed as `MECHANISM_REJECTED`. The kill rules use the exploration vocabulary
  (DEPRIORITIZED).

| role (account) · policy hash | source | caps (gross / name) | stop in σ → % | worst case at $100k | twin | kill rule |
|---|---|---|---|---|---|---|
| thematic (hack1) `8134a10a21a23ad5` | Explorer `human_ai_thematic_v2` / `roi_v3`, frozen at seed, clipped and never renormalised; 21 sessions | 1.00 / 10%, ≤ 20 names | 3σ, clip [4%, 12%]; at p50 2.50% = 7.5%, at p90 4.92% = 12% (2.4σ) | 3σ day at 6.71% (BE) = −$20,126 uncapped → −$10,000 after scaling gross ×0.50; all stops −$12,000; ceiling −$100,000 | sticky matched twin (TWIN_STICKY_v1) | drawdown ≥ 20% → flatten; 63 sessions with excess ≤ 0 vs twin AND SPY → DEPRIORITIZED |
| revision_snowball (hack2) `228de1efcb1027ff` | `revision_flow` (net raises ≥ 3 firms / 90 d), top 20 EW; snowball only orders ties. **Reputation weights excluded: NOT_PERSISTENT_OOS** | 1.00 / 5% | 3σ, [4%, 12%] | 3σ at 5.04% = −$15,125 → −$10,000 (×0.66); stops −$12,000 | sticky twin | drawdown ≥ 20%; 63 sessions; revision file > 7 d → no rebalance |
| world_news (hack6) `15fcfd17d80f1f4b` | SHADOW_NEWS `news_signal` d > 0; weight 1% × (1 + 2·usable_trust), ≤ 3%; trust only by KEY 1 (today 0, so every name is 1%); 5 sessions | 0.30 / 3%, ≤ 10 names | 3σ, [4%, 10%] | 3σ at 4.92% = −$4,429; stops −$3,000; ceiling −$30,000 | matched random twin + cash | drawdown ≥ 10%; digest > 36 h → no entries |
| quant_ensemble (hack4) `0bb99e6adf242bb5` | library rules with pure-selection t ≥ 2 on **both** twins AND validation net-minus-market t ≥ 2. **Today 27 rules pass both twins and 0 pass the market line, so the rule says HOLD CASH** | 1.00 / 10% | 3σ, [4%, 12%] | today $0 (cash); if a rule qualifies: −$14,763 → −$10,000 | the rule's own fair and sticky boards; cash while the book is cash | drawdown ≥ 20%; a rule that falls below eligibility is sold at the rebalance |
| innovation (UNASSIGNED; hack3 answers 401) `1d9146ee44a98dc6` | Explorer HIGH_RISK_INNOVATION (≥ 2 of 3 flags; 47 names today), ranked by list_score; COVERAGE ×0.5; binary event ≤ 1%; **hard 2% per name**; 63 sessions; costs 30 bps | 0.30 / 2%, ≤ 15 names | 3σ, [6%, 20%]. A stop cannot protect against a binary gap; sizing does | 3σ at 13.53% = −$12,178 → −$10,000 (×0.82); binary gap (15 × 1% × −70%) −$10,500; stops −$6,000 | sticky twin + a random twin from the same flagged pool | drawdown ≥ 15%; 63 sessions; Explorer receipt > 7 d → no entries |
| spy_control (hack5) `430c485cd5e8df7f` | 95% SPY, 5% cash, no view | 0.95 in SPY | disaster stop 10% (~14σ) | 3σ day at 0.70% = −$1,986; panel's worst SPY day −$5,562; stop −$9,500 | ideal control | never killed |

"63 sessions" in the kill-rule column means: DEPRIORITIZED if excess ≤ 0 against both the twin and
SPY after 63 sessions.

Rule hashes (they exclude the activation fields):

| role | rule hash |
|---|---|
| thematic | `610fb02743fb17be` |
| revision_snowball | `53939865c9d8602d` |
| world_news | `dc49d391f4a120a4` |
| quant_ensemble | `d4aedab5957f9245` |
| innovation | `cd05695fc5c6ec9f` |
| spy_control | `e3b390ba10d481f5` |

**Why nothing can seed them** (`test_fleet_v3_contracts.py::test_no_seed_path_can_read_a_prepared_contract`):
- They live in `contracts_v3/`, which `fleet_manager.load_contract` never reads.
- `load_contract` and `freeze_contract` now REFUSE a PREPARED body, so a hand copy into
  `contracts/` is refused as well.
- An AST scan (docstrings skipped) finds no module outside the preparer that names the folder.

**Owner trap found, not changed:** `scripts/fleet_manager_run.py` resolves only v1 and v2:
`contract = c2 if (active == "v2" and c2) else c1`. If `modes.json` says `"v3"` today, the runner
**silently runs v1 terms**. It needs a v3 path before any activation. The owner steps below say so,
and a test pins the line so this stays visible.

## 2. D14: the PC-PAPER benchmark core

SPY is tradable on the PC path. It is an ordinary Alpaca paper equity order, and `pc_broker`
already samples it in `BENCHMARKS`. No proxy ETF is needed.

How the flag works:
- **Flag ON:** `u_plan` adds one SPY target at `1 − active_gross`, where active gross is the acting
  sleeves after the order-path gate.
- **The 12% cap:** the target goes through `plan_orders` unchanged, so **MAX_NAME_FRAC clips it at
  12%** and the receipt says `CORE_CLIPPED_BY_MAX_NAME_FRAC`.
- **When it sends:** only in `paper_profit`.
- **The 10% limit:** if the core plus the sleeves would exceed the worst-case limit, the core is
  shrunk.
- **Grading:** sleeves are graded as excess over SPY, because `decision_ledger` already grades
  against `DECISION_BENCHMARK_SYMBOL` = SPY. The account's sleeve contribution is
  `r_acct − w_core·r_SPY`.

Worst case at $1,002,024. The core is priced at SPY's 63-session sigma (0.70%/day), the sleeves at
the universe p90 (4.92%/day), with ρ = 1:

| book | core 3σ | sleeves 3σ | total 3σ | % equity | Σ\|notional\|/equity | core on the worst SPY day (−5.86%) | ≤ 10%? |
|---|---:|---:|---:|---:|---:|---:|---|
| today, flag OFF: PROBE 20%, 80% cash | $0 | −$29,585 | −$29,585 | 2.95% | 0.20 | $0 | yes |
| flag ON as built (core clipped at 12%) | −$2,513 | −$29,585 | −$32,098 | 3.20% | 0.32 | −$7,040 | yes |
| **full 80% core** (needs a second owner decision on MAX_NAME_FRAC) | **−$16,754** | −$29,585 | −$46,340 | 4.62% | 1.00 | **−$46,935** | yes |
| full core, SPY at the review's stressed 1.2% | −$28,858 | −$29,585 | −$58,444 | 5.83% | 1.00 | −$46,935 | yes |
| no sleeve acting: 100% core | −$20,943 | $0 | −$20,943 | 2.09% | 1.00 | −$58,669 | yes |
| EXPLOIT + PROBE acting, core 0 (before the gate) | $0 | −$147,926 | −$147,926 | 14.76% | 1.00 | $0 | **no**; the order-path gate scales EXPLOIT down |

PC-PAPER declares no stop, so the ceiling is the whole gross: −$1,002,024 for a full core.

**What the core does NOT fix (found while testing).** `decision_contract.positions_reconciliation`
compares the broker's cash with the contract's cash plus whatever core is not held.
- **The 2026-10-07 contract:** it resolves 99.75% to the core and 0% to PROBE ("BY CONSTRUCTION").
  The broker holds 20% in PROBE names.
- **Core or no core:** an 80% SPY core leaves POSITIONS_DISAGREE by the same 20%, and so does the
  flag alone.
- **What reconciles:** only a contract that counts the plan's acting PROBE gross. Once it does,
  even a 12% core with 68% cash reads OK, because the check reconciles cash, not exposure.
- **SLEEVE_BASIS_DISAGREES:** the three $40k agency rows are unaffected by the core.

So D14 has three levers, and the line stays red without the first two:
1. The contract counts the acting PROBE/EXPLOIT gross. This is a `decision_contract` change; I did
   not make it.
2. A decision on whether a broad index ETF is exempt from MAX_NAME_FRAC. That is a `pc_broker`
   limit; I did not touch it.
3. This flag.

This is pinned in `test_benchmark_core.py::test_what_the_core_does_and_does_not_reconcile`.

Smaller caveats:
- **Turning the flag OFF again:** this does not sell the SPY core unless EXPLOIT is acting, because a
  held non-target is an EXIT under the EXPLOIT gate. Close it in the broker UI or by a new version.
- **Decision-story replay:** with the flag ON, the replay sees one extra target that is not a
  selection, so its line may read MISMATCH on days the core is held.

## 3. D13: the mirror cap hole (proposal only)

`backend/services/rules_capfix_proposal.py::enforce_position_limits_with_cash`:
- When `n × cap < 1`, it runs the same waterfill, but excess that has no room goes to an explicit
  CASH line.
- A sector cap is trimmed into cash, never into another name.
- When `n × cap ≥ 1`, it defers to `rules.enforce_position_limits` unchanged.

No lane path imports it (pinned by an AST test). Wiring it is `lane-integrity-check` work and needs
the owner's yes on D13. Before wiring, someone has to show that the reference engine carries a CASH
weight.

Mirror NAV is $75,525.03 (`roi_2026-10-06T160824Z.json`), and the declared cap is 25%:

| state | largest name | one name → 0 | one name −50% | 3σ day (DKNG/SLDP book) | gross |
|---|---:|---:|---:|---:|---:|
| 06-16 → 07-14, 2 names, **without fix** | 50% | −$37,763 | −$18,881 | −$7,459 | 1.00 |
| same, **with fix** | 25% (+50% cash) | −$18,881 | −$9,441 | −$3,730 | 0.50 |
| today, 12 names priced (fix is a no-op) | ≤ 25% at a rebalance | −$18,881 | −$9,441 | — | ~1.00 |

## 4. Owner steps (D2, D13, D14)

Fleet reset and activation, per account, and not before 2026-10-26:
1. **Archive first:** `python -m scripts.fleet_v3_prepare --archive` copies `state/`,
   `decisions.jsonl`, `grades.jsonl`, `modes.json` and `contracts/` to
   `fleet_manager/archive/<stamp>/` with a sha256 manifest. It copies; it never moves.
2. **Write a last broker-truth read:** `python -m scripts.fleet_manager_run --pass open --roles <acct>`.
   Run it without `--live`, so it is DRY.
3. **Reset accounts:** reset each account in the Alpaca UI if you want to (hack1, hack2, hack4,
   hack5, hack6). The innovation lane also needs an account: regenerate hack3's keys or open a new
   paper account.
4. **Teach the runner v3:** add a v3 path to `fleet_manager_run.py`. Without it, `"v3"` silently runs
   v1 terms.
5. **Activate one role at a time:**
   - re-freeze the prepared body into `fleet_manager/contracts/`, with `status` changed and the
     `seed` block filled;
   - confirm that `fleet_v3_contracts.activation_diff(prepared, activated)["same_rule"]` is True;
   - set `modes.json` to contract=v3 and run DRY first; switch to LIVE after one clean DRY pass.

D14: set `config.PC_BENCHMARK_CORE = True` only after deciding the two levers in §2. The flag alone
buys a 12% SPY core and leaves the reconciliation red.

D13: say yes. The session that wires it runs `lane-integrity-check` before and after.

## Files

- New: `backend/services/fleet_v3_contracts.py`, `backend/services/benchmark_core.py`,
  `backend/services/rules_capfix_proposal.py`, `scripts/fleet_v3_prepare.py`.
- `backend/services/fleet_manager.py`: `_refuse_prepared` in load and freeze.
- `scripts/sim_run.py`: `_plan_benchmark_core` and the CORE state, both behind the flag.
- `backend/config.py`: the C20 block.
- Tests: `backend/tests/test_fleet_v3_contracts.py`, `test_benchmark_core.py`,
  `test_rules_capfix_proposal.py`.
- Data: `backend/data/optimus/paper_accounts/fleet_manager/contracts_v3/*.json` (six contracts and
  the receipt).
