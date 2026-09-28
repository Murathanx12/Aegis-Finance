# LANE A build: alerts to Telegram, INFO only, plus owner replies (2026-09-28)

Licence: PRODUCT_EXPERIMENT. No LLM call on any path below; spend $0.00 by construction.
Nothing here can place, cancel or change an order, a cap, a stop or a weight.

## RESULT IMPROVEMENT: NONE (delivery and measurement plumbing; no alpha claim)

## What the research inventory said, checked against the code

| Claim in `signal_alerts_design_2026-09-28.md` | Verdict |
|---|---|
| `AegisTelegramAgent` running, heartbeat live | TRUE (pid 138516 at 06:05Z, loops climbing) |
| Outbox has sent nothing since 2026-09-23 | TRUE (last row 2026-09-23T01:07Z, `cmd:sim`) |
| `daily_jobs()` has no scheduled caller | PARTLY FALSE: the `--serve` loop calls it every loop; it just rarely returns a line (promise grader only) |
| Vocabulary is "39 + no_event" (or 38 / 43) | FALSE: v3 has **44 substantive + no_event** (`N_SUBSTANTIVE = 44`, hash `ef173fa7...`) |
| `event_store` holds a 3-clock history usable for novelty | FALSE in practice: `backend/data/optimus/events/` holds NO `events_*.jsonl`; only `event_table_v1.parquet` (built 2026-09-06). Novelty here is computed by the alert ledger's own dedup. |
| SEC 8-K current Atom + EX-99 bodies on disk | TRUE; newest 2026-09-25 (Friday; EDGAR is closed at weekends, so not a defect) |
| Form 4 insider data for cluster buys | Only the quarterly bulk tape `sec_insider/insider_events_v1.parquet`, which **ends 2026-07-01**: no cluster can be fresh. The reader is built and says `STALE_TAPE` by name. |
| Company press releases collected | TRUE only as EX-99 exhibits on 8-Ks; used as the primary link when present |
| `source_scorecard` grades at 1/5/21/63 vs SPY and a matched cell, clustered by date | TRUE; reused directly (`grade_units`, `cell_stats`, `add_source_drift`) |
| Candidate set fresh | TRUE: funnel 4.1 days old (limit 10); union with 57 personal/competition books = 385 tickers |

## Files

New: `backend/services/alerts.py` (levels, ledger, dedup, caps, quiet hours, render, delivery,
grading hook, kill rule, the pass), `backend/services/alerts_sources.py` (universe, 8-K, Form 4,
discovery confirmation, price in sigma), `backend/services/alerts_replies.py` (owner replies),
`scripts/alert_pass.py`, `backend/tests/test_alerts_core.py`, `test_alerts_sources.py`,
`test_alerts_replies.py`.
Edited: `backend/config.py` (appended `ALERT_*`, `ALERTS_SEND_ENABLED = True`, `TELEGRAM_REPLY_*`,
`TELEGRAM_NEWS_*`); `backend/services/telegram_bridge.py` (`poll(..., text_handler=)`; strangers
are now dropped and counted with NO reply); `scripts/telegram_agent.py` (reply commands + text
handler wired into both `poll` calls; HELP); `backend/tests/test_guard_missing_input_contract.py`
(one case, `alerts`).

## The rules, as coded

* Frozen before sent: FROZEN row appended under a file lock before any send; the result is a
  second SEND_RESULT row; a sender that raises leaves the frozen row intact (pinned).
* Dedup: cluster key (ticker, event type id, fact key = primary 8-K item), window 72 h measured
  from the cluster's FIRST publication; later publications are FOLLOWUP rows with a running
  count, never sent; the same (ticker, source URL) never writes twice.
* 8-K typing: by item code only. A specific item outranks the catch-alls 7.01/8.01 (the first
  live run typed AllianceBernstein's leadership 8-K as 7.01 Reg FD; fixed and pinned).
  An item mapping to several ids keeps `sec_8k_item_<code>` and names the candidates.
* Caps: 8/day and 2/ticker/day in the owner's HK day, counting SENT + DRY_RUN + HELD.
  Quiet hours 00:30-07:30 HKT computed from UTC with zoneinfo; held alerts go as one digest.
* Levels: INFO only; the other three refused by name ("needs >= 100 graded alert dates; have N").
* Grading: entry at the open of the first session opening after `created_utc`; 1/5/21 sessions
  vs SPY and the matched size x vol x momentum cell. `n_alert_dates_graded` = distinct UTC alert
  dates graded at 5 sessions; printed every pass with the distance to 100.
* Kill rule: at >= 100 graded dates, unless `cell_stats` calls the directional alerts
  ALPHA_DETECTED vs the matched control at 5 sessions (t >= 2 clustered by date, LOO-month
  worst > 0, top-5 share < 1, t >= 2 net of the stream's drift), the pass sends one daily
  digest headed by the reason.

## Live verification (2026-09-28)

* Dry run 06:04Z: universe 385 tickers, 356 Atom rows read, **8 alerts** rendered and frozen
  (AB, DKNG, ENVA, MARA, BTGO, DT, MRVL, SDOT), status DRY_RUN, Form 4 STALE_TAPE, spend $0.00.
  The 8 DRY_RUN rows consume today's HK cap (by design: they would have been sent).
* One real message sent to the owner (install notice): delivered.
* `AegisAlerts` registered: every 30 min, `pythonw -m scripts.alert_pass`, start-in the repo.
  First scheduled run 06:07Z: rc 0, receipt written, 8 already in ledger, nothing pending.
* Telegram agent child restarted by its own PID (25812, verified command line) so the reply
  handler is live; supervisor restarted it in 5 s; polling ok.

Stop: create `backend/data/optimus/alerts/STOP`. Remove: `schtasks /Delete /TN "AegisAlerts" /F`.

## Owed

* `backend/data/optimus/telegram/` and `alerts/` are untracked and NOT gitignored;
  `telegram/conversation.jsonl` holds the owner's own text. Add both to `.gitignore` before any
  `git add` of `backend/data/`.
* `/ask` (slash) is still the pre-existing local-model route pinned by `test_model_routing`;
  plain `ask ...` is the no-model queue. Decide whether `/ask` should become the queue.
* A `system_health` probe on `alerts/receipts/` (file owned by another builder).
* Form 4: a fresh source (EDGAR daily index or per-filing acceptance time) — the bulk tape
  cannot produce a fresh cluster.
* `test_guard_missing_input_contract::test_every_guard_is_enrolled` is red on two OTHER
  builders' new modules (`calendar_offsets`, `muratclaw_instance`), not on `alerts`.
