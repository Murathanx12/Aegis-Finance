# REVIEW 2026-09-28: Lane P, the paper money path (adversarial investor)

Reviewer: Opus 5.5, acting as a sceptical investor. I changed no code and no configuration. I placed no
orders, made no broker calls and ran no sim. The only test run was
`AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 .venv/Scripts/python.exe -m pytest backend/tests/test_lane_p_money_path.py -q -p no:cacheprovider`
→ **13 passed, exit=0**. Two mutation runs used a scratch pytest plugin outside the repo (§F6).

Scope: Lane P's files only (`backend/config.py` `ISSUER_SHARE_CLASSES`,
`backend/services/investment_committee.py`, `backend/services/decision_contract.py`,
`scripts/sim_run.py`, `backend/tests/test_lane_p_money_path.py`), plus what they touch.

## Verdict (three sentences)

The share-class collapse is correct for the pairs it lists: 26 of 28 are confirmed by SEC CIK, and the
other 2 are absent from SEC's current file. But it is a hand-made list that misses **8 of the 22**
multi-class issuers in the funnel's own 5,339-name universe, and it covers one of the four paths that
build a book. "The mandate gates no orders by design" is literally true to the record. Printing
`MANDATE REFUSED` on the plan receipt beside orders that were sent teaches the reader that REFUSED
means nothing. In passing, the lane touched the most important finding of the day and did not
escalate it: the forecast unit that feeds the expected-return layer has written **0 rows since
2026-09-26**. The cause is an OpenClaw gateway failure mislabelled `REFUSED_CAP`, and the health
probe reads **ALIVE, "167 made today"**, the same shape as the 08-27 → 09-25 dead ledger.

## Findings, most severe first

### F1 (SEVERE, not in Lane P's files, surfaced by it): forecast accrual is dead again, and the scoreboard is green

What I checked:
- `backend/data/optimus/forecasts/day_2026-09-27.json`: `state: REFUSED_CAP`, `n_rows_written: 0`,
  `done: []`, `spent_usd: 0.0`, `first_flush_check: {ledger_delta_usd: 0.0, writer_openclaw_cost_usd: null}`,
  `why: "the call was made but the ledger the cap reads did not move: the cap cannot bind"`.
- The one telemetry row that day (`llm_calls_2026-09.jsonl`, call_id `310e3938c3ddf247`, 2026-09-27T07:51:32Z,
  purpose `u_forecast`) has `meta.status: RC_NONZERO`, `cost_status: UNPRICED_OPENCLAW` and
  `error: "Gateway agent call connection closed ... gateway closed (1006 abnorma..."`. **The call failed.**
  The cap did not disagree with anything. That is the same OpenClaw gateway the reader night was using, and it
  lost its gateway (handoff `cbfcb3d3`).
- The cap's reader and the writer **do agree** when calls succeed. u_forecast ledger cost vs OpenClaw's own estimate:
  09-25 $0.1456 vs $0.1490 (59 calls); 09-26 $0.3159 vs $0.3284 (135 calls). Cap `FORECAST_DAILY_CAP_USD = 2.0`
  (`backend/config.py:4050`). Real spend is 7–16% of the cap. **The cap is not binding and never was.**
- `predictions.jsonl`, `investigator:evidence_v3` rows by `made_at`: 09-25 **118**, 09-26 **270**, 09-27 **0**, 09-28 **0**.
  No `forecasts/day_2026-09-28.json` exists at review time. Whether a 09-28 attempt is still scheduled is UNVERIFIED.
- Every cycle of sim `94f7b8ff15e5` (121 cycles, to 2026-09-28 07:54 +08) reports
  `{"ok": true, "skipped": "already ran today (2026-09-27)", "state": "REFUSED_CAP", "status": "DEGRADED"}`.
- Health `health/health_20260927T235132Z.json`: **`u_forecast ALIVE | newest forecast made 5.5h ago; 167 made today`**.
  `forecast_ledger ALIVE | 33 new row(s)`. The 167 are `thesis_card:v1` (134) and `source:*` (33) rows.

The code:
- `scripts/night_investigator_forecast.py:619`. `if delta <= 0:` refuses the day on the first call whose
  ledger delta is zero, whether the call succeeded or failed. A failed call costs $0 and moves nothing, so a
  gateway outage is classified as a cap problem.
- `:535`. `REFUSED_CAP` is terminal for the UTC day. No later cycle retries.
- `backend/services/system_health.py:623` `p_u_forecast` reads `max(made_at)` over **every** specialist, so
  any writer keeps it green.

Failure scenario: tomorrow the reader night again brings the gateway down before 07:50Z. Then the first
`u_forecast` call returns RC_NONZERO, the day is REFUSED_CAP with 0 rows, and thesis cards write 100+ rows.
Health prints ALIVE. The builder's own projection (first E[r] component live 2026-11-11 *only if forecasts
are written every session*) slips one session per such day, and nobody sees it.

What I would have done:
1. In `daily_forecast`, check `call.status` before the ledger delta. A non-OK call is `DEGRADED_GATEWAY`: not
   terminal, retried next cycle, at most N per day. Keep the delta check only for `status == "OK"`.
2. Make `p_u_forecast` read `evidence_v3` rows (the unit it names), or the day receipt's `state` and
   `n_rows_written`.
3. Run the forecast unit before the reader night starts, or give it its own gateway health check.

This is not Lane P's code. The builder did see `REFUSED_CAP, n_rows_written 0`. The finding belongs at the
top of the lane note, not in a sub-bullet of P3.

### F2 (HIGH): a status called REFUSED that refuses nothing now prints on the plan receipt too

The design record, quoted:
- `docs/HANDOFF_2026-09-25_FABLE_TO_OPUS_BUILD_PLAN.md:195` (Chunk C3): *"`acting` for PROBE is **not** gated on
  `top20_net_rel_21d` (that gate measures the ranker, not the shortlist), it is gated on the shortlist's own
  forward grade once ≥ 21 days exist, until then it is `UNMEASURED_TRADE_SMALL`. Print the worst case: `n ×
  probe_cap × stop_sigma` in dollars on the receipt."* C3 predates the mandate and says nothing about it.
- `backend/services/decision_contract.py:669-673` (`account_mandate`, built 2026-09-26, commit `85d96044`): *"It
  REFUSES -- `status: REFUSED`, a named reason per disagreement -- when the capital bases or the caps disagree,
  instead of picking one silently ... it stays red until Murat confirms ONE mandate. No limit is changed here."*
- `docs/RUNBOOK_2026-09-26_SYSTEMS_FIXES.md:26`: *"`mandate` block that **REFUSES** when bases/caps disagree (it
  does today)"*. The 09-26 review R4 asked for *"one mandate table for the PC-PAPER account, printed on every plan"*.

So "by design" is **true**. The mandate was never specified as an order gate. The builder's reading is not
convenient. Printing it consistently is still not an improvement:
- In this codebase REFUSED means *the thing did not happen*: `REFUSED_CAP`, `REFUSED_BROWSER_PROFILE_NOT_ALLOWED`,
  and `pc_broker`'s `REFUSED: equity ... not positive`. `mandate: REFUSED` beside `n_sent: 22` breaks that meaning.
  The patch's answer is a 90-word `gates_orders_note` (`decision_contract.py:791`) on every contract and every
  plan. Prose is needed to explain a status word only because the word is wrong.
- It can never go green without an owner action. It has printed the same three refusals every day since 09-27,
  and one of them is partly spurious. `GROSS_CAPS_DISAGREE` (`:741`) compares the reachable 1.00× with
  `IC_TOTAL_TILT_BUDGET = 0.10`, and the builder says that one is *"not a `u_plan` limit"*. This is CLAUDE.md's
  "a permanent red line beside real checks teaches the reader to skim red lines" (09-26 review R6).
- Its worst-case arithmetic is also wrong, in the direction that flatters it (F3). "Reachable 1.00×" ignores held
  positions that cannot be sold.

Failure scenario: a reader scanning the plan receipt of a day when a *real* refusal matters (for example the
bars age gate refusing u_plan) sees two REFUSED lines, knows from habit that one of them is noise, and skims both.

What I would have done: **rename and split.**
1. Rename the status to `UNRECONCILED` (or `OWNER_DECISION_OWED`) with `gates_orders: false`, so the word matches
   the behaviour.
2. Drop `GROSS_CAPS_DISAGREE` against the IC tilt budget, which is not a limit on this account.
3. Make the one real, bindable part bind: a broker-truth gross check that **REFUSES orders** (F3).

Deleting the mandate would lose the owner's to-do. Making the capital-base disagreement bind would stop trading
over a question only Murat can answer.

### F3 (HIGH, latent, second time asked): the gross cap reads the plan's targets, not the broker's positions

- `backend/services/pc_broker.py:423`. `total_w = sum(t.weight for t in targets)`. Held names that are not
  targets get target 0 and become exits.
- `scripts/sim_run.py:1236` `_may_send`. `EXIT` goes only while `exploit_acting`. `:751` `if p.stem >= asof:
  continue` still classes a name bought under the *current* asof as `EXIT`, not `PROBE_EXIT`. That is the
  09-26 review R2 (*"`PROBE_GROSS_CAP = 0.20` caps targets, not holdings; a same-day refusal cannot exit"*),
  still open. ALLE was stuck this way on 09-26/27.
- `:1201`. `room = 1 − probe_gross` uses planned PROBE gross, not holdings.
- Account buying power $3,734,382 (margin, per the builder, UNVERIFIED by me). The venue will not refuse leverage.

My recomputation from config (equity $999,054.41 from `pc_book/2026-09-27/nav.jsonl` per the builder;
k = `PROBE_WORST_CASE_SIGMA` 3; σ = `PROBE_REF_DAILY_SIGMA` 2.16%, or the funnel's highest `vol_annual`, AVPT,
2.742%/day; `PROBE_MAX_NAMES` 10 × `PROBE_MAX_WEIGHT` 2% ≤ `PROBE_GROSS_CAP` 0.20; `BOOK_SIZE` 18 ×
`ER_EXPLOIT_MAX_WEIGHT` 10% ≤ room; `MAX_INVESTED_FRAC` 1.00 on targets; no stop is declared anywhere):

| book | Σ\|notional\|/equity | 3σ @2.16% | 3σ @2.742% | no-stop ceiling |
|---|---|---|---|---|
| PROBE largest admissible, 10 × 2% | 0.20 | −$12,948 | −$16,436 | −$199,811 |
| EXPLOIT alone (shortlist empty → room 1.00), 18 names ≤10% each, Σ ≤ 1.00 | 1.00 | −$64,739 | −$82,181 | −$999,054 |
| **Holdings path:** EXPLOIT acted at 1.00×, next day `MEASURED_NEGATIVE` → its names are `EXIT` and unsendable, while PROBE buys 0.20 | **1.20** | **−$77,686** | **−$98,617** | **−$1,198,865** (more than equity, on margin) |
| R2 same-asof path: 10 PROBE names bought, re-plan refuses them all, 10 new ones bought | 0.40 | −$25,895 | −$32,873 | −$399,622 |
| Reachable today (EXPLOIT refused) | 0.2184 | −$14,139 | −$17,948 | −$218,197 |

The builder's table matches mine to the dollar on every row it printed. It omitted the 1.20× and 0.40× rows,
which are the ones the cap cannot see. It also applies the PROBE reference σ to the EXPLOIT book, whose pool
is the ~2,900-name xs_ranker universe, including small and illiquid names. That is probably an understatement
(UNVERIFIED).

**Is this 2026-09-21 again?** It is the same family: a cap that reads a different ledger from the one that
holds the money. It is not yet the same event: on 09-21 the breach happened ($10.05 under a $2 cap), and here
it needs EXPLOIT to act once, or the R2 path. **Rank:** below F1, because F1 is live and silent today. Above
everything else in the lane, because it has been named twice (09-26 R2, today P4) and deferred twice.

What I would have done: add `Σ(post-order market value from broker positions) ≤ MAX_INVESTED_FRAC × equity`
in `plan_orders`, computed from `held × price`, refusing buys on breach. Put `invested_frac` on the plan
receipt. The `u_plan` health probe already says *"invested_frac not in the receipt, cap check not possible"*.

### F4 (MEDIUM-HIGH): the issuer map is hand-made, incomplete, and covers one of four paths

**Correctness.** I checked it against SEC `company_tickers.json` on disk (`backend/data/optimus/edgar_8k/`,
fetched 2026-09-03, 10,412 tickers):
- **26 of 28 groups: same CIK.** Examples: GOOGL/GOOG 1652044, FOXA/FOX 1754301, NWSA/NWS 1564708, UAA/UA
  1336917, Z/ZG 1617640, BRK-B/BRK-A 1067983, LBTYK/A/B 1570585, BBD/BBDO 1160330, BF-B/BF-A 14693, HEI/HEI-A
  46619, PBR/PBR-A 1119639, KELYA/KELYB 55135.
- CWEN-A and CUK are absent from SEC's current file. They cannot be confirmed (UNVERIFIED; possibly delisted).
- Third classes that SEC lists but the map omits: BATRB, FWONB, LILAB.

**Completeness.** CIK grouping over the funnel's own universe (`backend/data/funnel_cache/universe.json`,
5,339 names) finds **22** multi-line issuers. The map has 14 of them. **Missing: BELFA/BELFB,
DGICA/DGICB, GLIBA/GLIBK, LLYVA/LLYVK, RDI/RDIB, METC/METCB, SENEA/SENEB, UONE/UONEK.** The lane note's
claim that *"14 other share-class groups exist in the 5,339-name universe"* counts only what the builder found.
- Scenario: the next funnel refresh ranks Bel Fuse on profitability_small. Both BELFA and BELFB enter PROBE
  at 2% each, one issuer at 4%. That is the exact defect this lane closed for Alphabet, and nothing names it.
- In the bars panel (3,060 symbols), CIK also groups preferreds with common (MSTR/STRC/STRD/STRF/STRK,
  SMCI/SMCIP, MCHP/MCHPP). A derived rule needs a common-stock filter.

**The guard should derive its input.** One pass over the SEC file on disk groups by CIK (common classes only)
and reproduces all 14 of the builder's in-universe groups plus the 8 missing ones. A hand list of 28 against a
5,339-name universe is the "guard that does not derive its inputs" pattern from the canon. The CIK map also
cannot see ADR/local pairs: **6 frozen books in `llm_portfolio/books.jsonl` hold both TSM and 2330.TW**
(`comp_ai_power_global`, `comp_policy_geopolitics`, `cards_supports`, each with its `__ew` twin). That needs an
ISIN/FIGI or a curated ADR map.

**Coverage.** `collapse_share_classes` runs only inside `investment_committee.shortlist()`
(`investment_committee.py:246`), whose only caller is `u_plan` (`sim_run.py:1083`).

| path | collapsed? | how much can double |
|---|---|---|
| u_plan PROBE (`shortlist`) | yes | – |
| u_plan EXPLOIT pool (`ranking.json` top) | **no** | two lines × `ER_EXPLOIT_MAX_WEIGHT` 10% = **20% in one issuer**. `MAX_NAME_FRAC` 12% is per *symbol*, so it does not catch it. Today's top-25 pools (09-25..27) hold no pair. |
| PROBE × EXPLOIT cross-book | **no** (the `exploit_syms` exclusion is exact-ticker, `sim_run.py:~1181`) | GOOGL PROBE 2% + GOOG EXPLOIT 10% = **12%** |
| decision contract virtual PROBE / tilt rows (`funnel_state` → `compose_book`) | **no** | graded as two names; tilt 3% × 2 = 6% |
| book factory / frozen library books | **no** (and must not be changed) | **8 of 308 books in `books.jsonl` hold GOOGL and GOOG** (5% each in `lib_big_dv_2026-09-26` → Alphabet 10%). The strategy-library replication backtest (`top10_for_replication_2026-09-27T030004Z.json`) holds both lines on **40** month-ends. |
| forecast universe (`day_2026-09-27.json`) | no | GOOGL and GOOG both asked; MCHPP (a preferred) in the cut list. Wasted calls, not exposure. |

**Frozen history.** The collapse does **not** alter any frozen book or seeded history. It reads only the
funnel, at decision time. That is correct. The frozen books' double exposure should be *reported* on their
grade, never repaired.

**Churn risk.** The kept line is chosen by current dollar volume (`investment_committee.py:258`), with no
preference for the line already held. For pairs whose volumes are close (Z/ZG, FOX/FOXA, LBTYA/LBTYK), a funnel
refresh can flip the choice and cause a sell-one/buy-the-other round trip with no change of view. Prefer the
held line when both qualify.

### F5 (MEDIUM): a selection change mid-flight with no version change; the GOOG→TSM trades will be read as decisions

- `scripts/sim_run.py:606` `PROBE_POLICY_VERSION = "c3-v0"` is unchanged. It has also stayed `c3-v0` through
  the drift band (09-25), the bars age gate (09-26) and the policy_state read (`cc6ec525`). The Explore-Dirty
  rule 4 says *"once a candidate enters forward paper, its version is **frozen**"*. Every row since 09-25 claims
  one policy that has been four policies.
- At the next `paper_profit` open, per the builder: sell 58 GOOG (~$19.8k), buy ~$20k TSM. I reproduced the
  selection: the real `shortlist('2026-09-28')` returns 24 rows with GOOG dropped, and with ALLE removed by the
  contract, TSM is PROBE name 10. Cost: ~$40k of mega-cap turnover at an estimated 2–5 bps is **~$8–$20**
  (estimate, UNVERIFIED; `pc_broker` prints no cost model). The cost is negligible. The contamination is not:
  - the GOOG sell carries `reason: "not in the ranked book: exit"` (`pc_broker.plan_orders`), so the decision
    autopsy will read a code change as a view change;
  - TSM enters the PROBE book with no hypothesis change;
  - the 09-25/26 GOOG PROBE rows keep grading to expiry, which is fine and should stay.

What I would have done: bump to `c3-v1`, write one policy-journal row (what changed: issuer collapse; the
effect: −GOOG +TSM; the date), and stamp the GOOG exit `reason: "policy change c3-v0→c3-v1: share-class
collapse"`. That is three lines, and it keeps the forward record honest.

### F6 (LOW-MEDIUM): tests

I ran two mutants through a scratch pytest plugin, with no repo change:
- `collapse_share_classes → identity`: **6 fail, 7 pass**.
- `ISSUER_SHARE_CLASSES = {}`: **6 fail, 7 pass**.

So the collapse is genuinely pinned. What is weak:
- `test_the_map_is_data_and_no_ticker_belongs_to_two_issuers` (line 156) **passes on an empty map** and cannot
  catch a wrong or missing pair. Replace it with a test that derives CIK groups from the on-disk SEC file over
  the universe cache and fails on any unmapped group. That test would be red today, with 8 groups.
- `test_observe_mode_never_reaches_submit_under_a_refused_mandate` (line 239): the `forbid_submit` broker *can*
  go red (`pytest.fail` raises a BaseException that `except Exception` cannot swallow). But the mandate plays no
  role: observe mode never sends, with or without it. The test's title is stronger than its content.
- `test_plan_prints_the_contract_mandate_verbatim` (line 201) asserts `probe_acting is True` under REFUSED. It
  **pins the policy choice in a test**. Whoever later makes the mandate bind will find a red test that looks
  like a regression. Keep it, but name it as a policy pin.
- No test covers the cross-book issuer case (PROBE GOOGL + EXPLOIT GOOG), or holdings-based gross.
- Dates: none hard-coded. `TODAY`/`ASOF` derive from UTC now, and the funnel stamp from now − 1 day. It will not
  rot. A run straddling UTC midnight could desynchronise `ASOF` and u_plan's internal clock; I judge that
  negligible.
- The suite is offline: the fake broker patches `snapshot`, `last_prices`, `clock`, `orders` and `submit`.

## MUST FIX BEFORE COMMIT (Lane P's files)

1. **Version the change.** `PROBE_POLICY_VERSION` `c3-v0` → `c3-v1`, one policy-journal row, and a
   policy-change reason on the GOOG exit (F5).
2. **Rename the plan-receipt mandate status** so REFUSED is not printed beside sent orders: `UNRECONCILED` or
   `OWNER_DECISION_OWED`. Drop `GROSS_CAPS_DISAGREE` against `IC_TOTAL_TILT_BUDGET` (F2).
3. **Add the 8 missing in-universe groups** (BELFA/B, DGICA/B, GLIBA/K, LLYVA/K, RDI/RDIB, METC/METCB,
   SENEA/B, UONE/UONEK) and the 3 missing third classes (BATRB, FWONB, LILAB). Replace the vacuous map test
   with a CIK-derived completeness test (F4, F6).
4. **Rewrite the lane note's top line.** Lead with F1, the dead forecast unit, not with "RESULT IMPROVEMENT:
   NONE" and a sub-bullet.

## MUST FIX TODAY, outside Lane P (owner of `night_investigator_forecast.py` / `system_health.py`)

- F1: a non-OK call is `DEGRADED_GATEWAY`, retryable, not a terminal `REFUSED_CAP`. `p_u_forecast` must read
  `evidence_v3` rows or the day receipt, not any specialist's `made_at`.

## OWED LATER

- F3: broker-truth gross check in `pc_broker.plan_orders`, refusing buys, and `invested_frac` on the plan
  receipt. Also fix R2's `p.stem >= asof`. **Before EXPLOIT can ever act.**
- F4: derive issuer identity from SEC CIK (common classes only) instead of the hand list. Add an ADR/local map
  (TSM/2330.TW). Collapse the EXPLOIT pool and the PROBE×EXPLOIT union by issuer, and apply the caps per issuer.
  Prefer the held line when choosing.
- Report (never repair) the double Alphabet / TSMC exposure on the 8 + 6 frozen books when they are graded.
- Collapse the contract's `compose_book` rows so one issuer is graded once.
- Declare a stop, or accept on the record that the ceiling is the gross (owner).

## For the owner, in plain language

The builder fixed a real mistake: Alphabet's two share classes were bought as if they were two companies, so
you had twice the intended bet on one stock. That fix is right, and the next session will sell the extra GOOG
and buy TSMC instead, for a few dollars of trading cost. But the list of "same company, two tickers" was typed
by hand. It misses 8 companies that are already in the pool the system picks from, and the other paths that
build portfolios do not use it at all. The red "MANDATE REFUSED" line is not a safety lock. It is a reminder
that you have not yet chosen one capital figure and one set of position limits, and it should be renamed so
nobody mistakes it for one. The more important news is elsewhere. The daily forecaster, the input the whole
learning layer is waiting on, wrote nothing on Sunday, because the browser night knocked over the shared AI
gateway. The system filed that as a budget refusal and gave up for the day. The health page still shows green
because other writers kept the ledger busy. That is the same silent failure that cost a month in September. It
should be fixed before anything else in this lane is committed.
