# The fleet daily manager (2026-09-29 night)

Licence: PRODUCT_EXPERIMENT, paper accounts only. Owner's instruction, verbatim: *"update the
hacks positions daily. do either locally or with railway. update them based on the latest results
and the news."* It runs locally, at $0. The Railway budget is $20/month and the four loops were
stopped earlier today.

## RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** The fleet is managed again, but nothing new was bought tonight.

| line | tonight |
|---|---|
| Best historical net strategy vs market | None (unchanged; CRSP library 0 of 133 pass). |
| Best forward paper strategy | None graded. The first fleet grades, for session 2026-09-28, are one-day numbers and prove nothing. |
| Independent selector count | **Proposed: 5 accounts on 5 different alpha sources**, each an existing frozen book or rule with a frozen twin. None is active yet; the owner flips them. |
| Candidates tested / promoted | 0 / 0. |
| New actionable finding | 4 of the 13 resting stops sit **within about 1 daily sigma** of the price (BIOA 0.33-0.45σ, EVLV 0.6-0.76σ, KTOS 0.7-1.1σ, RZLV about 1σ). The 09-24 finding was that stops this close are mostly noise-triggered. |
| External execution drag | Not measured: no order was sent tonight. |
| LLM spend | $0.00. |
| Cost per gradeable output | $0: four grade rows written for 2026-09-28. |

## PAUSED 2026-09-29 22:49 HKT (owner paused all tasks)

- **Orders sent tonight: none.** `decisions.jsonl` has 0 LIVE rows and 0 outcome rows.
- **The one `--live` pass (run `20260929T134239Z-d5939c`)** ran maintenance on hack1, hack2, hack4 and hack6. Every position already had a full-quantity GTC stop, so it sent nothing.
- **Scheduled tasks.** `AegisFleetManagerOpen` and `AegisFleetManagerPreclose` were disabled by the orchestrator before their first run. Leave them disabled until the owner says continue.
- **Not done:**
  - hack5 contracts are not frozen, and hack5 was never read after its spread closed.
  - The dated section in the execution repo's `docs/HANDOFF.md` is not written; its draft is in the session scratchpad.
  - The learning layer is not wired to `grades.jsonl`.
- **To resume**, run these from the research repo root:
  1. `.venv/Scripts/python.exe -m scripts.fleet_manager_run --freeze --roles hack5` freezes hack5's contracts.
  2. `.venv/Scripts/python.exe -m scripts.fleet_manager_run --pass open --roles hack5 --rebaseline hack5` is a dry run that accepts the flat account as its record, after the close task's foreign order.
  3. `.venv/Scripts/python.exe -m scripts.fleet_manager_run --pass open` dry-runs all accounts.
  4. Re-enable both tasks:
     `Enable-ScheduledTask -TaskName AegisFleetManagerOpen; Enable-ScheduledTask -TaskName AegisFleetManagerPreclose`

## What was built

| file | what it is |
|---|---|
| `backend/services/fleet_manager.py` | The logic: contracts frozen by policy hash, stops in sigma, reconciliation, the hard-limit gate, idempotent order ids, worst case in dollars, twins, grades. `Venue` is the only object that reaches the network. |
| `scripts/fleet_manager_run.py` | The one caller that talks to the broker. It has two passes: `open` and `preclose`. Every run writes a receipt with its own run id. |
| `backend/tests/test_fleet_manager.py` | 23 offline tests. They cover the limits, idempotency (a re-run cannot double-submit), reconciliation refusal, stops in sigma, contract immutability, share-class and defect drops, and the worst case. They make no network calls. |
| `backend/config.py` (appended) | `FLEET_MANAGER_*`: every cap and parameter. |

**Scheduled tasks (windowless `pythonw`, with a log):**
- `AegisFleetManagerOpen` runs Mon-Fri at 22:45 HKT (10:45 ET in summer time, 09:45 ET after 2026-11-01).
- `AegisFleetManagerPreclose` runs Tue-Sat at 03:30 HKT (15:30 ET, or 14:30 ET after 2026-11-01).
- Both times stay inside the US session when US summer time ends.
- The read-only `AegisFleetDailyCheck` at 06:45 is unchanged.

**Owner files:**
- **STOP file:** `backend/data/optimus/paper_accounts/fleet_manager/STOP`. It is checked at start, before each account and before each order.
- **Mode switch:** `.../fleet_manager/modes.json`, one row per account. It holds the active contract version (v1 or v2), whether maintenance is LIVE or DRY, and whether entries are LIVE or DRY. The script never edits it after creating it.

**Records** (all under `.../fleet_manager/`):
- `decisions.jsonl`: every decision row, written BEFORE any order, with its price, quote, inputs, contract hash and mode.
- `grades.jsonl`: the daily grades.
- `runs/run_<id>.json`: one receipt per run.
- `contracts/<role>_<version>.json`: the frozen contracts.
- `state/<role>.json`: the reconciliation record.

## The rules, as code

- **Venue and asset limits.** Paper host only. The manager never builds an option order: the gate refuses any symbol that is not a plain equity ticker.
- **No shorting, no leverage.** A sell may never exceed the long quantity held. Gross must stay at or below 100% of equity, and cash must stay at or above zero after every buy.
- **Size limits.** One name is at most 10% of equity. Non-protective orders share a daily turnover budget of 50% of equity, and each run sends at most 60 orders.
- **Order types.** Buys and sells are DAY limits at the quote ± 10 bps, falling back to the last trade when the IEX quote is one-sided or wider than 2%. Protective orders are GTC stops. Market orders are never sent.
- **Market hours.** Orders go out only while the venue's clock says open and at least 5 minutes before the close.
- **Idempotent order ids.** Each id is derived from (role, session day, kind, symbol, contract hash, intent), and the price is not part of it. Before any POST the id is looked up at the venue, so a re-run skips an order it already sent (`submit_once`).
- **Reconciliation.** Broker positions must equal the last record plus the fills since it, and no order without the `aegisfm-` prefix may have been submitted since. Any mismatch refuses every order on that account. The first record was the GET-only fleet check at 13:23Z.
- **Stops in daily sigma.** The distance is clip(3 × σ63, 4%, the contract's maximum), with σ63 taken from the bar-defect-screened panel. A missing or expiring stop is replaced for the full quantity. A replaced stop is never set below the stop it replaces.
- **Pre-close exits.** The pre-close pass cancels the manager's own unfilled exit limits, so the shares can be protected again overnight.
- **Exclusions.** Entries skip names that the bar-defect screen cut, removed rows from, or holds as a suspect. They also skip stitched tickers, a second share class of one issuer (SEC CIK map), and an issuer the account already holds under another class.
- **News.** News reaches an order only through typed digest rows and the frozen `world_digest.news_signal`. No free text decides an order. X, Reddit and StockTwits rows never originate one, because social-only implications are refused upstream.

## Per account (broker truth 2026-09-29 13:42Z; worst case = every stop fills at its price, gaps can be worse)

| role | holds | active contract | worst case now | declared-book formula | tonight |
|---|---|---|---|---|---|
| hack1 | SYM 574 sh (entered 09-09, 14 of 21 sessions); GTC stop 38.73 = 2.1-2.3σ | v1 `bde68d4af4b40dc4` | **$2,078** (2.3%), gross 0.27 | 8 × 12.5% × 10% = 10% → $9,088 | LIVE maintenance: nothing needed |
| hack2 | flat, $98,820 cash | v1 `56d8443e7bf58f8d` | $0 | 8 × 12.5% × 8% → $7,906 | LIVE maintenance: nothing to do |
| hack4 | BIOA 2,261 (09-21), RZLV 8,650 (09-09); stops 6.93 (0.33σ) / 2.02 (1.0σ) | v1 `617d923978288fcf` | **$1,642** (2.1%), gross 0.44 | 5 × 20% × 12% → $9,578 | LIVE maintenance: nothing needed |
| hack5 | flat after the BE spread closed at 13:36Z (one mleg order, $9.00 credit × 7) | v1 (see HANDOFF addendum) | $0 | options mandate: cannot run under "no new options" | untouched before 23:00 HKT |
| hack6 | 10 tracker names (09-08 to 09-17), a stop on each for the full quantity | v1 `018b228ba879e2e0` | **$4,961** (6.1%), gross 0.68 | 15 × 6.67% × 10% → $8,158 | LIVE maintenance: nothing needed |
| hack3 | unreadable: its key answers HTTP 401 | none | unknown (9 positions last seen 09-22) | n/a | skipped; credentials are the owner's |

**Fleet worst case now, readable accounts: $8,681.** It covers hack1, hack4 and hack6 at their resting stops; hack2 and hack5 hold nothing.

**Why no entries under v1.** Each v1 mandate fails CLOSED without its selection input, which is the execution repo's own rule: "no sealed book, no trade". The seal authority is still up, but today's seal considered 0 names, and `portfolios[hack4]` and `portfolios[hack6]` selected 0. The theme-basket (hack1) and drift (hack2) brains lived inside the stopped loops.

**Why the empty seal does not force exits.** An empty seal is NOT read as THESIS_INVALIDATED. It is a missing input, not a verdict on the name. v1 exits are therefore the declared horizon and the resting stops. No position reaches its horizon before 2026-10-08, when hack1's SYM is due.

## The v2 proposals: one alpha source per account

Each proposal is frozen tonight and dry-run only. Each is an EXISTING frozen book or rule with a frozen twin; none is invented. Every book is expressed at the fleet caps, with names clipped at 10% and nothing renormalised.

| role | v2 hash | alpha source | source book / twin | dry-run tonight | declared worst case |
|---|---|---|---|---|---|
| hack1 | `bdae86290ea38481` | human + AI thematic (the owner's themes) | `5d137b013692a737` / `4204177563615b9a` | 11 buys (VRT, GEV, MU, HOOD, TSM, ...) within the 50% budget, 12 refused by the budget, SYM kept under v1 | 23 × 4.2% × 12% → $10,470 |
| hack2 | `2301fa30c7b851df` | analyst revision flow | `cb8d492bb8bf9ade` / `e74c9063d451e316` | 10 of 20 names × 5% on day 1 (budget), the rest day 2 | 20 × 5% × 12% → $11,858 |
| hack4 | `a0c5313766c52c9a` | engine funnel shortlist sized by 1/σ (size of move) | `61fa183ee45aa10a` / `5d578a72cd528f21` | 8 buys; GOOGL dropped as GOOG's second class; BIOA/RZLV kept under v1 | 11 × 8.9% × 12% → $9,388 |
| hack5 | frozen after 23:00 | market-like CONTROL (~95% SPY + the Bayes sleeve) | `0f038859b2ebea62` / `be5e940728613d94` | after 23:00 | see HANDOFF |
| hack6 | `12fa05317df05ce1` | world-digest typed implications, 1% per name, ≤ 10 names, 5 sessions | SHADOW_NEWS_v0 `news_signal`; twin = v1 twin + cash | 8 buys (XOM, AKAM, SPCX, AVGO, NVDA, GOOGL, AMD, LMT); two targets priced above a 1% unit round to 0 shares | 10 × 1% × 10% → $816 on top of v1 |

**The reason for this split.** The known bottleneck was ten books on one signal. These five sources are human themes, analyst flow, the engine funnel with size-of-move sizing, a market control, and news. Their errors should differ, and whether they do is the question.

**Caveats that come with the proposals:**
- The frozen books were picked on 09-25 to 09-28 and are entered days later. That entry lag is the replication cost of a frozen book.
- Revision flow's own sweep was negative at every horizon (worst cell −0.67%/21d net). It is a PRODUCT_EXPERIMENT, not a claim.
- CRSP_BLEND_v0 was deliberately NOT used, because it was chosen after looking and reviewed at 34/100.

## What the owner must decide

1. **Activate v2 per account.** In `modes.json`, set `"contract": "v2", "entries": "LIVE"`.
   - hack2 and hack5 displace nothing.
   - hack1, hack4 and hack6 keep their current names under v1 terms until horizon or stop.
2. **The four tight stops.** The manager never loosens a stop. Moving the stops to 3σ within the contract maximum would stop the noise-triggered exits the 09-24 study measured, but it would raise the worst case. BIOA alone would go from about $500 to about $1,900.
3. **hack3.** Its 9 positions are unreadable and unmanaged until the key is regenerated, or the account is closed in the Alpaca UI.
4. **Telegram.** The alerts code has no hook for an extra digest line (only its own unsent-summary line), so no fleet line was added. Adding one is a new sending behaviour and needs a decision.

## WHAT WORKS

- **Broker truth first, then reconciliation.** Four accounts reconciled OK against the GET-only 13:23Z record. A foreign order would refuse the account.
- **Idempotent, pre-recorded decisions.** Every decision is written before its order, and a re-run cannot double-submit (pinned by test).
- **Stops quoted in sigma.** Four stops sit within about 1σ of the price. That was invisible when stops were quoted in percent.
- **Frozen contracts with hashes and twins.** The first graded day, 2026-09-28, is on disk:

  | account | return | SPY | twin |
  |---|---|---|---|
  | hack1 | −0.92% | −0.76% | −0.22% |
  | hack4 | −0.28% | −0.76% | −1.37% |
  | hack6 | −0.51% | −0.76% | −0.93% |

  One day proves nothing.

## WHAT DOES NOT

- **The v1 mandates cannot buy.** Their inputs died with the loops, and today's seal was empty. So "update daily" is maintenance-only until the owner activates v2.
- **The learning layer does not read `grades.jsonl` yet.** `paper_accounts_roi` reads the same accounts from the broker, but it does not ingest the twin/SPY grade rows. That wiring is owed.
- **hack3 remains dark.**

## HIGHEST-EV EXPERIMENT

**Activate v2 on hack2 and hack5 first**, then hack1, hack4 and hack6.
- **Why those two.** They are flat, so nothing is displaced, and they are the two most different alpha sources: analyst flow against a market control.
- **Why now.** Forward evidence is the one thing a session cannot parallelise. Every week the five sources are not running is a week of grades that can never be recovered.
- **What it costs.** $0 of LLM spend and paper money only. The worst case is bounded in dollars on every receipt.
