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

## AFTER REVIEW (2026-09-28, answering docs/reviews/REVIEW_2026-09-28_LANE_A_ALERTS.md)

RESULT IMPROVEMENT: NONE (the alert stream is plumbing; 0 of 100 alert dates graded).

Every finding was re-checked on disk first. All held: the 90-character cut (F1), 8 of 8
dry-run texts no longer reproducible (F2), 7 of 8 "within 2 sigma" lines computed from the
Friday close taken BEFORE a Friday after-close filing (F3), oldest-first cap (F4), the real
corpus growing on each test run (F5; 8 rows by the time I cleaned it, not 6), write-only
queues (F6).

Sending was set to `False` first, and the `alerts/STOP` file paused the scheduled pass while
code was half-edited (a pass on half-edited code is worse than a paused one; STOP loses
nothing because the reader window re-offers the events). Both are reverted at the end:
**`ALERTS_SEND_ENABLED = True`, STOP removed**, because F1-F3 are fixed and the dry run below
was read message by message.

| Finding | State | What changed |
|---|---|---|
| F1 message says what happened | FIXED | the frozen row carries `fact_line` (ticker, what the company did in plain words from `alerts_sources.ITEM_PLAIN`, the item, the legal name LAST) and `headline`; line 1 is `AEGIS <fact_line>`, cut at a word boundary (`cut_words`). The fixture is now real SEC boilerplate with a long legal name; a test runs a real-shaped Atom row for EVERY vocabulary item (and a Form 4 cluster) through reader, freezer and template and asserts the key noun and the item code in line 1 |
| F2 what the owner read is frozen | FIXED | SEND_RESULT stores `text`, `text_sha256`, `render_version` (render/2), `typing_rule_versions`, `rendered_at_utc`, `digest_header`, `summary_line`; FROZEN stores `typing_rule_version` (`8k_item_priority/2;form4_cluster/1`) and every threshold the template reads, so `rerender(send_row, rows)` equals the stored text byte for byte (pinned; also after a config change, and for a quiet-hours digest with a summary line). Rows on disk were not edited; every pass receipt carries `ledger_note` saying rows before render/2 carry no text. Ledger appends are fsynced (`disk_guard.locked_append_line(fsync=True)`, the one parameter added there) |
| F3 no price from before the event | FIXED | `price_context(event_utc=...)`: a last close before the acceptance time gives `move_basis: BEFORE_EVENT`, `already_moved: None`, and `reaction_state` MARKET_NOT_TRADED_SINCE (with the next XNYS open) or TRADED_NO_CLOSE_ON_DISK. The message prints "Move since filing: UNKNOWN, market has not traded since this filing; next session opens Mon 09-28 21:30 HKT (09:30 ET)" and the age in words ("Filed Fri 09-25 16:07 ET (Sat 09-26 04:07 HKT), 2 days ago"). An event public longer than `ALERT_SEND_MAX_AGE_H` (72 h, on ACCEPTANCE time, not first-seen) at delivery closes `TOO_OLD`, counted in the receipt |
| F4 cap to the most important | FIXED | `rank_key`: `ALERT_EVENT_TYPE_PRIORITY` (config, by fact key), then newest, then the larger known move, then id. Capped / held / too-old alerts are named in ONE line on the next SENT message ("2 more filing(s) not sent (2 over the daily cap): DEB, OTH; reply `report` for the list") and never again; `report` lists them. Source staleness: `source_staleness_8k` counts EDGAR filing hours since the newest Atom row (limit 4) and the pass receipt goes `DEGRADED` on STALE |
| F5 test wrote to the real corpus | FIXED | the replies fixture points `config.OPTIMUS_LEDGER_DIR` at tmp_path; `backend/tests/alerts_isolation.guard_real_data` (autouse in every `test_alerts_*.py`, pinned by an AST test) fails a test on any write under the real `backend/data` and any read of the lane's private stores. It caught two more real reads while I wrote the new tests. Cleanup: incident record below |
| F6 "queued" has a reader | FIXED (one line owed) | `scripts/owner_queue.py` (stdlib) reads `questions.jsonl` / `reading_queue.jsonl`; `digest <url>` rewrites `digest_inbox/READING_LIST_FROM_TELEGRAM.md`; `queue` and `report` show both; `ask` replies with what is TRUE today ("NOT yet shown to a Claude session automatically ... listed by `queue`"), and switches wording by itself once the session hook exists. `digest_inbox.ingest` now skips `reading_list*` files: the new list, and the hand-written `READING_LIST_2026-09-28.md`, would otherwise have been ingested as a pasted "article" and sent to DeepSeek (checked: not yet ingested) |
| F7 security items | FIXED | inbound rows per rolling hour: strangers 20, owner 120; beyond it no row, a counter, and one summary row per hour. `/ask`, `/deep`, `/research` pass `model_gate` (the reply rate limit, 20 model commands per HK day, the lab_budget cap; unknown spend REFUSES); `/deep` and `/research` become an approval request and run once on `/approve <id>`, only within 60 min. A `digest` paste keeps line breaks, is stored in full up to 4,096 characters and the reply says "Stored N of M"; publisher is UNKNOWN (column `telegram_paste_unknown`) unless `source=` is given |
| F8 injection through the paste inbox | TRACED + TESTED | below |
| F9 operations | FIXED (one line owed) | `run_pass` holds `alerts/alert_pass.lock` (a second pass refuses by name); `alert_pass.main` writes a receipt on REFUSED, DiskTooFull and on any crash (`state: CRASHED: ...`); graded dates = distinct ENTRY SESSIONS; kill rule: TOO_FEW / missing = UNDECIDED (stays LIVE), only BETA_EXPLAINS / CANNOT_DISTINGUISH kill; `alerts.receipts_health` + `p_alert_receipts` (run id in the file name, never mtime) |

### F8: what an injected instruction in a paste can change
Path: Telegram `digest <text>` (owner chat only) -> `DIGEST.md` -> `digest_inbox.ingest` ->
`web_reader.store_article` (`news_corpus/dowjones/unknown/<day>/<sha>.json`) -> the night
reader's claims step or `digest_ingest --claims` -> `dowjones_claims.extract_claims`: one DeepSeek
call, the article (<= 12,000 chars) in the USER message -> `validate_claims` -> `write_forecasts`
-> `source_registry.write_claims` (forecast rows `source:telegram_paste_unknown`).
Confirmed in code and by test: a claim is refused when its ticker is not named in the article
(`article_tickers` / `ticker_named`), its quote's first 120 normalised characters are not in the
article, it only describes a past move, it repeats a (ticker, direction), or it has no
paraphrase; at most 6 per article. The injected "direction up for every ticker" test yields 0
kept claims (4 refused).
What injection CAN still change (pinned by a second test so this note stays honest): for a ticker
the pasted text really names, with a sentence the pasted text really contains, the model's choice
of direction, horizon bucket, magnitude bucket and paraphrase. So a hostile text the owner pastes
can write forecast rows under `telegram_paste_unknown`, and spend up to the claims cap.
What it CANNOT reach: an alert (alerts originate only from SEC 8-K / Form 4; this corpus is not
even a confirming source), a weight (a cell needs ALPHA_DETECTED; 0 of 60 have one), an order,
a file path, a shell. NOT traced: whether a stored `paraphrase` is later fed into another LLM
prompt.

### F5 incident record
`backend/data/optimus/incidents/test_wrote_to_real_corpus_2026-09-28.json`:
`news_corpus/dj_digest_inbox/2026-09-28.jsonl` held **8 rows before, 0 after**; all 8 were the
test fixture (identical line, sha256 `66ca3b5a6ab3...`, article sha `31d3f3448b465792...`,
first_seen = the test's fixed clock). Backup beside it:
`2026-09-28.jsonl.bak_before_F5_cleanup_2026-09-28`; the emptied day file was removed rather
than left at 0 bytes. Derived rows: **none** (claims ledger 0, forecast ledger 0; the claims
step reads article files, and the fixture's article went to tmp_path), so no VOID_SYNTHETIC ids.

### Dry run (read in full)
`alert_pass --dry-run --scratch` on a copy of the ledger: 8 events, all already in the ledger,
0 messages, state OK (the real ledger was not touched). To read what the owner would receive, the
same pass on an EMPTY scratch ledger: **8 messages, 8 DRY_RUN, 0 too old, `rerender == text` for
all 8**, ranked auditor changes first. Two of them:

    AEGIS DKNG changed its auditor (8-K Item 4.01). DraftKings Inc.
    Filed Fri 09-25 16:07 ET (Sat 09-26 04:07 HKT), 2 days ago.
    Move since filing: UNKNOWN, market has not traded since this filing; next session opens Mon 09-28 21:30 HKT (09:30 ET). Before it: 22.02 at the 09-25 close, +1.1 sigma 1d, +0.2 sigma 5d.
    Source: https://www.sec.gov/Archives/edgar/data/1883685/000188368526000034/0001883685-26-000034-index.htm (+8 headline(s))
    Not known: typed from the item code only; 0/100 alert dates graded. Contradicts: none found
    [INFO] id Aea093b9b5e29 (reply: analyze Aea093b9b5e29)

    AEGIS AB reported a director or officer leaving or joining (8-K Item 5.02; also Item(s) 7.01). ALLIANCEBERNSTEIN HOLDING L.P.
    Filed Fri 09-25 08:04 ET (Fri 09-25 20:04 HKT), 2 days ago.
    Price 35.76 at the 09-25 close, +1.1 sigma 1d, -0.8 sigma 5d (after the filing): within 2 sigma.
    Source: https://www.sec.gov/Archives/edgar/data/825313/000082531326000060/ex9901ableadershipchanges9.htm (+2 headline(s))
    Not known: type is one of management_change_departure | management_change_appointment; 0/100 alert dates graded. Contradicts: none found
    [INFO] id A81475b01dbcb (reply: analyze A81475b01dbcb)

AB is the one pre-open filing, so its close IS after the filing and the move is reported; the
seven after-close filings say UNKNOWN. The 8 rows already on disk were frozen by render/1 and
are terminal (DRY_RUN); nothing was re-sent.

### Still owed (other builders' files, exact lines)
* `system_health.PROBES`: `Probe("alert_receipts", "pc", timedelta(minutes=30), "alerts/receipts/alert_pass_<run id>.json: state + sources.sec_8k.staleness", lambda ctx: __import__("backend.services.alerts", fromlist=["p_alert_receipts"]).p_alert_receipts(ctx)),`
* `scripts/session_state.py::build_state`: add `"owner_queue": __import__("owner_queue").summary(),`
  (the hook runs `python scripts/session_state.py`, so `scripts/` is on the path; `owner_queue`
  is stdlib-only and `summary()` never raises). The `ask` reply changes its own wording once
  this line exists.
* `web_reader._store_article`: write the corpus row under `Path(root).parent / sid` when a
  `root` is passed (the article root is `news_corpus/dowjones`), not under
  `config.OPTIMUS_LEDGER_DIR`; the test no longer depends on it, but any other caller that
  passes `root=` still writes into the real corpus.
* Not changed, decide: DRY_RUN rows count toward the HK-day cap by design, so the 8 rows of the
  06:04Z dry run have used 2026-09-28's cap of 8: anything frozen later today closes
  CAPPED_DAILY and is named in the first message sent tomorrow. The task's battery flags
  (`StopIfGoingOnBatteries`), receipt pruning and a fresh Form 4 source remain as the review
  listed them. The 8-K Atom source is refreshed about once a day: from Monday 10:00 ET the
  pass receipts will say `DEGRADED: 8-K source STALE` unless an intraday collector runs.
* Telegram agent: child restarted by PID 135232 (command line verified, tree 135232 -> 19720);
  the supervisor started 17684 -> 53356, "serving as murat_aegis_bot", heartbeat ok.

Tests (exit code read from the command, not a pipe): `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0
.venv/Scripts/python.exe -m pytest backend/tests/test_alerts_*.py <every test file naming
telegram|digest_inbox|dowjones_claims> backend/tests/test_disk_guard.py -q -m "not slow" -p
no:cacheprovider` -> **644 passed, 1 failed, exit 1**; the one failure is
`test_guard_missing_input_contract::test_every_guard_is_enrolled` on another builder's untracked
`muratclaw_instance` (red before this work, then also on `calendar_offsets`).
