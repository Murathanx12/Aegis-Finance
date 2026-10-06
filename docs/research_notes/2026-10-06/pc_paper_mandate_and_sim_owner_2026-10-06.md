# PC-PAPER mandate and the sim owner (chunk C2, 2026-10-06)

**Licence:** `PRODUCT_EXPERIMENT` (paper only). No limit was loosened.
**RESULT IMPROVEMENT: NONE.** The loop is alive and reconciled again; nothing here is evidence of edge.

## 1. What was broken

| # | finding | evidence |
|---|---|---|
| 1 | **No sim had run since 2026-09-29.** Nothing scheduled one. The 10-02 handoff (§3) says `AegisIIF1NightLauncher` "starts a sim session if a safe window remains". It does not: it launches the IIF1 investigator night (`backend.services.iif1_run`) and nothing else. Every row in `sim/sessions.jsonl` was started by a person, at irregular times. `system_health.p_sim_session` already said so in its own detail line: "no scheduler starts one". | `sim/sessions.jsonl`; the launcher log ends `night exited 0` after `iif1_run` |
| 2 | **The contract was sized on $40,000 while the account holds ~$1,000,000.** `_capital_from` took the IPS's `capital_usd` (the owner's real capital) and the mandate printed UNRECONCILED on every contract for ten days. | contract `2026-10-06` before: `capital_usd 40000`, `MANDATE UNRECONCILED` |
| 3 | **The mandate could never read OK.** `PER_NAME_CAPS_DISAGREE` fired whenever the per-name caps differed (2% PROBE, 3% committee tilt, 10% EXPLOIT, 12% broker). They always differ, because they belong to different sleeves. This is the same mistake the 09-28 review (F2) fixed for gross caps. | `account_mandate` before |
| 4 | **The candidate set went stale again (13 days).** `sim_run.u_funnel` is the scheduled caller of the funnel refresh, and it runs only inside a sim session. With no session, nothing refreshed it. | health `u_funnel` STALE, `generated_at 2026-09-24` |

## 2. What changed

* **Capital comes from the broker** (`decision_contract._capital_from_broker`, `pc_paper_equity`). The contract reads the newest PC-PAPER read that `pc_broker.snapshot` wrote. It considers `pc_book/state_latest.json`, the sim's day folders and the daily pass's `paper_accounts/pc_snapshot/`. The newest read is chosen by its own `t` stamp, never by file time. No literal is involved, and a test fails if `40000` appears on the contract, plan, owner or broker path.
* **Mandate status** (`account_mandate`) is OK or UNRECONCILED, and every disagreement is named:
  * `NO_BROKER_EQUITY_READ`
  * `BROKER_EQUITY_STALE`: older than `PC_MANDATE_EQUITY_MAX_AGE_DAYS` = 4
  * `CAPITAL_BASES_DISAGREE`: a capital named by the caller is more than `PC_MANDATE_CAPITAL_TOLERANCE` = 5% away from broker equity
  * `SLEEVE_CAP_ABOVE_BROKER_CAP`
  * `GROSS_CAPS_DISAGREE`
  * `WORST_CASE_ABOVE_LIMIT`

  The mandate still gates no order by itself.
* **The contract shows the reconciliation.** Every contract now carries `capital_reconciliation`: `capital_usd`, `broker_equity_usd`, source (ledger-relative), as-of, status, disagreements and the worst-case gate.
* **Scaled views on every contract and every plan receipt.** `scaled_views` covers the PC-PAPER held book and the contract's funded name rows, at every level in `config.IC_CAPITAL_LEVELS` ($10k / $40k / $1M):
  * whole shares at each level;
  * the names whose one share exceeds `weight x level` are listed as NOT executable;
  * the cash left over and the tracking gap are printed;
  * `places_orders: false`.

  `sim_run.u_plan` prints the same view of its targets.
* **The sim owner.** `python -m scripts.task_keeper sim` runs as scheduled task **AegisSimOwner**. It fires every 30 min and at logon, unlock and wake, using the same pattern as AegisReaderSupervisor and AegisCatchUp. On an XNYS session day between **09:00 and 15:30 US/Eastern** it starts a session if none is running.
  * **Session length:** the shortest allowed length (6/8/10/12 h) that reaches 17:00 ET.
  * **Mode:** trading (`paper_profit`) only when the mandate is OK and the worst case passes. Otherwise it starts `observe` and names the refusal in `trade_refused`.
  * **Receipts:** every firing writes one row with a run id to `sim/owner.jsonl`, including a refusal (disk, start refused) and an outside-window firing.
  * **Owner stops are respected.** It does not restart a session the owner stopped the same ET day. `sim/OWNER_STOP` pauses it.
* **Health** (`p_sim_session`) has a new verdict, `REFUSED` (exit code 2). In US hours with no sim running:
  * a fresh owner refusal reads `REFUSED <reason>`;
  * the owner's pause reads STOPPED_BY_OPERATOR;
  * a silent owner, or an owner whose started session is gone, reads DEAD.

## 3. Worst case first (protocol item 4), at broker equity $1,003,373

No stop order is declared anywhere on the PC path. In place of a stop%, the table uses a **3-sigma session** of the median name: 3 × 2.16%/day = **6.48%**. For scale, a −2% stop is 0.93 sigma.

| sleeve | n × notional% | Σ\|notional\|/equity | 3σ one-day loss | no-stop ceiling |
|---|---|---:|---:|---:|
| EXPLOIT | 8 × 10% (18 ranked, ≤10% each, gross ≤ 80%) | 0.80 | −$52,015 | −$802,698 |
| PROBE | 10 × 2% | 0.20 | −$13,004 | −$200,675 |
| **TOTAL** | 18 names | **1.00** | **−$65,019 (6.48%)** | −$1,003,373 |

* **Gate: PASS** (6.48% ≤ 10%, `PC_WORST_CASE_MAX_FRAC_OF_EQUITY`). No stop or cap was widened.
* **Where it would fail:** a fully invested book reaches the 10% line at a per-name daily sigma of **3.33%**. The ranker's EXPLOIT picks are small, illiquid names and can run hotter than the 2.16% median. EXPLOIT is currently refused (`MEASURED_NEGATIVE`), so the live book is the PROBE sleeve: about 20% invested, 3σ about −$13k.
* **The same decisions at $40,000** (PC-PAPER held book): all 10 of 10 names can be bought in whole shares. Target gross is 20.22%, executable 17.92%, tracking gap 2.30%.

## 4. Results tonight

| check | result |
|---|---|
| mandate | **OK**: capital $1,003,532 derived from the broker read, 0 disagreements (contract `2026-10-06` rebuilt). Receipt: `pc_mandate/reconcile_2026-10-06_20ca06d9b42d.json`. |
| funnel | `generated_at` **2026-09-24T02:48:34Z → 2026-10-06T15:51:08Z** (moved), 25 candidates. `u_funnel` returned `refreshed: true` after 444 s. |
| sim owner | the AegisSimOwner task, fired through the scheduler, started session `b7b5981048e5` in `paper_profit` for 6 h (owner run `3eac6b03a0ff`). Health: `sim_session ALIVE`. |
| still red | `decision_contract STALE`: `n_considered` has not moved. **This is not a stale-file problem now.** On the fresh funnel, 2 of 25 names pass the committee's eligibility gate (19 have ranking score ≤ 0, 4 have no licensed evidence). The constraint is the gate's input, not the age of the file. |

## 5. What runs when

The owner acts on the ET clock, never on a remembered HKT time. The task fires every 30 minutes all day.

| ET | HKT before 11-01 (EDT) | HKT from 11-01 (EST) | what happens |
|---|---|---|---|
| 09:00–15:30 ET on an XNYS day | 21:00–03:30 | 22:00–04:30 | start window: the first firing starts the session |
| 17:00 ET or later | 05:00 or later | 06:00 or later | session ends by itself (`COMPLETED`), after the close and the after-close grade |
| any other firing | | | one `outside_window` row with the reason |

## 6. How to verify tomorrow (one command)

```
python -m scripts.health_probe --only sim_session,u_funnel,ranking,decision_contract
```

Outside US hours, `sim_session` should read ALIVE, "idle outside US hours: last session <id> COMPLETED". In US hours it should read ALIVE (RUNNING), or REFUSED with the owner's reason. **DEAD means the owner did not fire.** In that case, read the last row of `backend/data/optimus/sim/owner.jsonl` and `Get-ScheduledTaskInfo AegisSimOwner`.

## 7. Not done

* The 10-02 handoff's line about AegisIIF1NightLauncher was not edited. Dated handoffs are a diary; this note is the correction.
* The worst case uses the median-name sigma, not the realised sigma of the names actually held.
* Tests: `backend/tests/test_pc_mandate_and_sim_owner.py` (23). Two existing tests in `test_contract_mandate_and_candidates.py` were rewritten to the owner decision: nested sleeve caps are not a disagreement, and capital is derived.
