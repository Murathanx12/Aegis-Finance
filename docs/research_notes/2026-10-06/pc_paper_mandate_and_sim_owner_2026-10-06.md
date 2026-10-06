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

---

## 8. After the adversarial review (`docs/reviews/REVIEW_2026-10-06_C2_PC_MANDATE_AND_SIM_OWNER.md`, 61/100)

**§3's table is superseded.** It priced the whole book at the stale median sigma, 2.16%. The worst case is now priced **per name, by sleeve** (`backend/services/pc_risk.py`):

* Sigma is the 63-session close-to-close sigma on the bars panel, the same window the fleet manager uses for its stops.
* The EXPLOIT sleeve is priced on the ranker's top names (`pc_book/<day>/ranking.json`).
* The PROBE sleeve is priced on the held names, scaled to the 20% cap.
* A name with no sigma of its own is priced at the universe p90, never the median.

At equity $1,002,662, 3 sigma per name, assuming every name moves against the book on the same day:

| sleeve | names | gross | avg sigma | 3σ one-day loss |
|---|---|---:|---:|---:|
| EXPLOIT (ranker top 8 at 10%: LITE, CDNL, ASPN, BRUN, NBTX, MSFT, AMD, OSS) | 8 | 0.80 | 5.31% | −$127,761 (12.74%) |
| PROBE (held, scaled to 20%) | 10 | 0.20 | 2.23% | −$13,417 (1.34%) |
| **TOTAL, sleeve names** | 18 | 1.00 | | **−$141,178 (14.08%): REFUSE** |
| same gross at the universe median (2.51%) | | 1.00 | | 7.53% |
| same gross at the universe p90 (4.91%) | | 1.00 | | 14.73% |

* **The line is not widened. EXPLOIT is sized down instead.** It may carry at most **54.4% gross** (about 5 names at 10%) for the book to pass. The trading verdict is `PASS_EXPLOIT_CAPPED`.
* **The cap is enforced in the order path.** `sim_run.u_plan` prices its own acting targets on every cycle (`pc_risk.cap_book`) and scales EXPLOIT down before orders are sized. If PROBE alone is over the line, or the live read shows an account, capital or worst-case disagreement, every send is blocked (`risk_gate` on the plan receipt). This covers manual and Telegram starts too.
* **The equal-weight EXPLOIT fallback** is now capped at `ER_EXPLOIT_MAX_WEIGHT` (10%). Before, only the broker's 12% bound it.
* **Reconciliation is no longer circular.** The contract now carries `positions_reconciliation`, and today it is **UNRECONCILED**:
  * three agency BUY rows are sized at $40,000 (the IPS basis), not their weight × contract capital (`SLEEVE_BASIS_DISAGREES`);
  * the contract resolves 99.75% to a benchmark core the account does not hold, while the broker holds **79.85% cash** (`POSITIONS_DISAGREE`).
  * `capital_resolution.broker_actual` prints the account's real split, and the "same capital" sentence is gone.
  * The capital check alone reads `CAPITAL_SOURCE broker`, `capital_status OK`.
* **The owner's start gate** trades only when all four hold: the live broker read succeeded, the read is from account `config.PC_PAPER_ACCOUNT_NUMBER` (reads from any other account are skipped), the capital status is OK, and the trading verdict passes. `sim/OWNER_STOP` now also asks a running session to stop at its next unit boundary.
* **Concurrency.** `sim_session.start` takes an O_EXCL `sim/start.lock`. A RUNNING session with no pid yet reads `STARTING`, not UNCLEAN. `sim_run` takes the broker lease in `paper_profit`, and a session that cannot take it stops with `REFUSED_LEASE`.
* **Health** says `ALIVE_OBSERVE_ONLY` for a session that cannot trade. Every running row now also prints the day's plans and orders sent.
* **Receipts carry no machine paths.** Today's: `pc_mandate/reconcile_2026-10-06_147824639837.json`. The earlier receipt's paths were made ledger-relative in place.

The running session `b7b5981048e5` started on the old code; these fixes apply from the next start.
