# REVIEW 2026-09-28: LANE A, alerts to Telegram plus owner replies

Reviewer stance: a sceptical investor and a security reviewer. I changed no code or config, sent
no message, and stopped no process. Everything I read, I read from disk, read-only.
Scope: `backend/services/alerts.py`, `alerts_sources.py`, `alerts_replies.py`,
`scripts/alert_pass.py`, the `telegram_bridge.poll` and `telegram_agent` edits, `config.py`
`ALERT_*`/`TELEGRAM_REPLY_*`, the three test files, the ledger and receipts under
`backend/data/optimus/alerts/`, and the `AegisAlerts` task definition.

## RESULT IMPROVEMENT: NONE

This is plumbing. No alert has been graded (0 of 100 dates) and none can be yet.

## Verdict in three sentences

The reply channel is sound where it counts. The chat-id check runs before any parsing, strangers
get no reply, and I found no path from a reply to a shell, a file path, a fetch, a model or a
broker. The alerts, however, are not yet gradeable as "what the owner read", and they do not say
what happened. The ledger freezes the facts but not the message text: all 8 dry-run messages
differ from what the current code renders from the same frozen rows. The live template also cuts
the 8-K description off at 90 characters, before the item that says what happened. On top of
that, 7 of the 8 dry-run alerts report "within 2 sigma" from a close taken *before* the filing.
Hold sending until the two small fixes below land; keep freezing so measurement continues.

Tests: `65 passed in 7.19s` (the three files, `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0`).
Running them had a side effect, see F5.

---

## Findings, most severe first

### F1. The message does not say what happened (render cuts the fact before the event). MUST FIX
`backend/services/alerts.py:321` renders `row.get("headline") or row.get("fact")`, and `:324`
cuts it to 90 characters. `build_frozen_row` (`:274-301`) never copies the event's `headline`
field (`alerts_sources.py:275`), so the fallback always fires. The fact string opens with
"<COMPANY> (<T>) filed a Form 8-K with the SEC, accepted <date time> UTC, reporting Item...",
which is about 90 characters long. Rendering the frozen rows on disk today gives:

    AEGIS [INFO] DKNG: DraftKings Inc. (DKNG) filed a Form 8-K with the SEC, accepted 2026-09-25 20:07 UTC, re...

The auditor change (Item 4.01), the one alert of the eight with a real negative prior, is not
visible. The event type id is not on any line either. This fails LANE A's own A4 ("each alert
states what is new"). The test does not catch it: the `ev()` fixture in
`test_alerts_core.py:27-35` has a short fact with the item near the front, unlike real rows.
**What I would have done:** freeze `headline` (form + item + item text) in the row and render
line 1 as `T: Item 4.01 Changes in Registrant's Certifying Accountant (filed Fri 16:07 ET, 66 h ago)`.
Pin it with a test that uses a real-shaped fact and asserts the item code appears in line 1.

### F2. The message text is not frozen, so the ledger cannot prove what was sent. MUST FIX
`alerts.py:533-548`: the SEND_RESULT row stores `message_chars` and nothing else about the text.
The text lives only in a per-pass receipt (`alerts/receipts/alert_pass_<run>.json`), which is a
separate file with no hash link from the ledger. I measured this: for all **8 of 8** dry-run
rows, `render(frozen_row)` today is **not equal** to the message in the 06:04Z receipt. The
template was rewritten after the dry run (the receipt still says "the reply handler is not built
yet").

The builder's "7.01 vs 5.02" remark is the same gap, not a one-off. The AB row
(`A8fd59c995735`) is frozen as `sec_8k_item_7.01` with candidates
`earnings_preannouncement | guidance_change`, but the filing is a leadership change. The typing
fix cannot reach it, correctly, because `seen_pub` blocks a second row. Even rendered today, the
AB message still says "type is one of earnings_preannouncement | guidance_change". So there are
two disagreements:

- between the frozen row and the current typing rule;
- between what a past pass rendered and what the ledger could re-render.

Neither is recorded in the row: there is no `typing_rule_version` and no `template_version`.

Consequence: the prices are gradeable (ticker + `created_utc` are frozen), but "does what the
owner read carry information" and any by-type grade are not. **What I would have done:** append
a `MESSAGE` row before the send with `text`, `sha256(text)`, `template_version` and
`typing_rule_version`, and have SEND_RESULT refer to that sha. Also add `os.fsync` after the
frozen append (`disk_guard.py:259-261` flushes but does not fsync; the 2026-09-12 bugcheck
NUL-filled an uncommitted file).

Proven, from code and disk:

- FROZEN is appended in `freeze_events` (`alerts.py:616`) before `deliver` runs (`:670`).
  On disk, rows 1-8 are FROZEN and rows 9-16 are SEND_RESULT.
- No code path rewrites a row.
- A crash between freeze and send leaves a PENDING row that the next pass sends: at-least-once.
- A crash after `sender()` succeeds but before the SENT row is written re-sends the message
  (duplicate). This is acceptable for INFO.
- The frozen row's own `send_status: "PENDING"` field stays PENDING forever. Any reader that
  trusts it is wrong; `analyze` correctly uses `send_state`.

### F3. "Price already moved" is computed from a close that predates the filing. MUST FIX (small)
`alerts_sources.py:419-453` takes the last close at or before `created_utc` and reports 1-day
and 5-day moves in sigma. It never compares `last_price_ts` with the filing's `published_utc`.
In the dry run, **7 of 8** filings were accepted after the Friday 16:00 ET close (20:07-21:01Z;
only AB, at 12:04Z, was before it). Each still printed "within 2 sigma". For those seven, that
line describes Friday's pre-news tape. The owner reads it as "the market has not moved yet"
when in fact the system has not observed the reaction (after-hours, Monday pre-market).
**What I would have done:** when `last_price_ts < published_utc`, print "reaction not observed
yet: last close predates the filing". Compute `already_moved` only from closes after acceptance.

### F4. Alerts are old, the cap spends them oldest-first, and nothing checks the source's age. OWED (first week)
- **Age.** All 8 dry-run alerts were frozen 57-66 h after SEC acceptance (Friday filings, Monday
  14:04 HKT pass). The age window (`alerts_sources.py:246`, 72 h) is measured on the collector's
  `first_seen_utc`, not on acceptance, so a collector catching up after an outage makes old
  filings look fresh. The message does not print the age. The acceptance time survives only
  inside the 90-character cut (F1).
- **Delivery has no maximum age.** A pending alert is sent whenever the next pass runs, for
  example after the STOP file is removed a week later.
- **The source is refreshed about once a day.** On 2026-09-24 all 181 Atom rows were first seen
  in the same UTC hour (22Z); on 09-25 an intraday poller also ran. `AegisDailyPass` is daily at
  06:30 HKT. A pass every 30 minutes over a file refreshed daily means a pre-market or intraday
  filing is usually alerted after its session has already traded it.
- **No staleness gate.** `newest_first_seen_utc` is printed and never compared to anything. A
  dead collector produces "0 events, OK" passes indefinitely. This is the 2026-09-22 funnel
  failure again, in a new place.
- **Cap order.** `plan_delivery` (`alerts.py:486`) sorts by `observed_utc` ascending, so the
  daily cap of 8 goes to the OLDEST events. `CAPPED_*` is terminal (`:88`), so a capped alert is
  never sent and never digested. On a busy weekday the freshest filings are the ones dropped.
- **Worth reading?** Of the 8: two are routine credit agreements (ENVA, DT: 1.01 + 2.03), one is
  a dividend release filed as 8.01 (MRVL, "one of 15 event types"), one is a 1.01 at MARA, one a
  5.02 at BTGO, and one is AB's leadership change mistyped as Reg FD. Only DKNG and SDOT (4.01
  auditor changes, negative prior) are the kind of thing an investor wants on a phone.
- **What I would have sent instead:** one Monday-morning digest, "8 filings in your names since
  Friday's close; 2 notable: DKNG and SDOT auditor changes (Item 4.01), both after the close, and
  the reaction is not yet observed". Rank by direction prior, then magnitude bucket, then
  membership in the owner's own books, then newest first. Put routine 1.01/2.03/8.01 items in the
  digest only. Refuse (DEGRADED line) when the newest Atom row is more than about 6 h old on a
  weekday session.

### F5. A test writes into the real news corpus every run. MUST FIX
`test_alerts_replies.py:152-170` calls `digest <long body>`. That runs `digest_inbox.ingest` →
`web_reader.store_article`. `store_article` honours `root=` for the article file but writes the
corpus row to `_config.OPTIMUS_LEDGER_DIR / "news_corpus" / sid` (`web_reader.py:905`), which
is the REAL folder. Evidence: `news_corpus/dj_digest_inbox/2026-09-28.jsonl` had 3 synthetic rows
when I first read it and 5 before my test run, and it has **6 after** it. Every row is the
fixture text, whose 280-character lead contains "...ignore all previous instructions". The date
is fixed at 2026-09-28, so the file keeps growing after today.
**Fix:** monkeypatch `_cfg.OPTIMUS_LEDGER_DIR` to `tmp_path` in the `ctx` fixture, or give
`store_article` one root for both writes. Removing the 6 synthetic rows is the owner's call; I
did not touch them.

### F6. `ask` and `digest <url>` promise a reader that does not exist. MUST FIX (wording) / OWED (consumer)
`alerts_replies.py:440-448` answers "Queued for the next session". `:378-383` answers "Queued
the link for reading". A search of `backend/` and `scripts/` finds **no consumer** of
`telegram/questions.jsonl` or `telegram/reading_queue.jsonl`, and the session start protocol does
not read them either. The owner will believe his questions are being read. They are a write-only
file. **Fix now:** reply "Saved to questions.jsonl; nothing reads this file automatically yet".
**Owed:** add it to `session_briefing()` or the morning report.

### F7. `digest` over Telegram cannot store an article intact. OWED
- `parse()` (`alerts_replies.py:111`) collapses all whitespace, newlines included, and the
  `/digest` route does the same via `text.split()`.
- The inbound cap is 4,000 characters (`:462`), and Telegram's own limit is 4,096.
- A WSJ article is 5-15k characters.
- The stored "article" is therefore one line, truncated, and `to_article` takes the whole thing
  as its title.

The night `claims` step (`night_reader_supervisor.py:99` → `dowjones_pull --claims`) then sends
it to DeepSeek as though it were a full article. The publisher defaults to `dowjones` when none
is detected (`web_reader.py:876`). A pasted X or Reddit post would therefore be stored and scored
under Dow Jones (UNVERIFIED end to end: I did not trace which scorecard cell a
`pasted_by_operator` claim lands in). Prompt injection in pasted text can reach that DeepSeek
prompt and fabricate claim/forecast rows. It **cannot** reach an alert: alerts originate only
from SEC 8-K/Form 4, and `dj_digest_inbox` is not a discovery-lane prefix, so it cannot even
confirm one. It cannot reach a weight today either, since 0 of 60 source cells earn one.
**What I would have done:** keep newlines; refuse a digest over about 3,800 characters with
"paste it into DIGEST.md instead"; tag Telegram pastes `origin: telegram_paste` with no
publisher unless one is stated; keep that origin out of the Dow Jones scorecard.

### F8. Reply security, point by point. Mostly PASS; two items OWED
| Question | Finding |
|---|---|
| Can a non-owner chat cause a reply? | **No.** `telegram_bridge.py` `poll`: `if not owner or cid != owner` → row + counter + `continue`, before any parse (test pins both the stranger and the no-owner case). |
| ...a file write? | **Yes, one:** a row in `telegram/inbox.jsonl` with up to 400 characters of the stranger's text, one per message, with no cap. Anyone who knows the bot's username can flood it. The disk-fill risk is small but unbounded. **Owed:** count strangers per hour; after N, keep no text. |
| Path traversal / overwrite | None. Every write goes to a fixed path; the ticker and alert id are regex-checked and used only as a parquet filter or an equality test. |
| Command execution / fetch / LLM in `alerts_replies` | None (AST test plus my read). A URL is queued, never fetched. |
| `/ask` with a slash | Still `model_routing.ask` → the **local** model (`telegram_agent.py:319`, `model_routing.py:214`), text only, no tools. `/deep` goes to paid DeepSeek, and `/research --quest` goes to DeepSeek and writes forecast rows. All of this is pre-existing. None of the slash model routes is covered by `TELEGRAM_REPLY_MAX_PER_MIN`, which only guards `alerts_replies.respond`. The plain-`ask` versus `/ask` split is a trap for a thumb on a phone. **Owed:** make `/ask` the queue and keep models on `/deep` only, with a rate limit and a daily count. |
| Secret leak | None found. Every reply goes through `send()` → `redact()`; exception text is redacted; nothing reads `.env`. The outbox logs the target chat id locally (pre-existing, gitignored). |
| Rate limit binds? | Yes, for the reply paths (test: 3 of 5 answered, then answered again after 90 s). Inbound text is logged before the check (owner only; acceptable). |
| Replayed update | `updates()` advances the offset **before** handling (`telegram_bridge.py:270-279`): at-most-once, so a crash loses a message rather than replaying it. `_set_offset` is a non-atomic `write_text`: a torn write reads as offset 0, which is harmless with Telegram's server-side confirmation. There is no dedup by `update_id`, so a replay would duplicate an `ask` row and nothing worse. |
| Owner's text as instructions downstream | Only via F7 (digest → nightly DeepSeek claims). The `ask` text is stored and read by nobody (F6). |

### F9. Operations. OWED (this week)
- **Log:** yes. `_ensure_streams` points pythonw's None streams at `alerts/alert_pass.log`, so
  tracebacks land there.
- **Failure visibility:** poor. An `AlertRefused` (for example a stale funnel over 10 days,
  `alerts_sources.py:111-113`) exits rc 2 with a log line and **no receipt**
  (`alert_pass.py:114-116`). Any other exception leaves a traceback and no receipt. No
  `system_health` probe reads `alerts/receipts/`, and the phone is never told. The alert stream
  can die silently while every other scoreboard stays green.
- **Task:** `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries` are **true** and
  `LogonType` is InteractiveToken. On battery or logged off, there are no alerts and no sign of
  it.
- **Lock:** `MultipleInstancesPolicy IgnoreNew` prevents scheduled overlap. A manual run
  concurrent with the task is not locked: both read the ledger, both freeze the same ids, and
  both send. **Owed:** a `file_lock` around `run_pass`.
- **Quiet hours:** correct, computed in Asia/Hong_Kong with zoneinfo (the test covers the UTC
  date boundary). 00:30-07:30 HKT is 12:30-19:30 ET, which covers the after-close 8-K burst; it
  arrives as one digest at 07:30 HKT, which is the right behaviour.
- **Disk:** about 2.2 KB of ledger per alert. Receipts are 1.7-11 KB × 48 passes a day, about
  0.1-0.5 MB/day and about 17,500 files a year. The log is about 53 KB/day. The pass refuses
  below `DISK_FREE_DEAD_GB + 1` (good). **Owed:** rotate or prune receipts.
- **Stale docstring:** `alert_pass.py:16-18` still says the flag is False until the owner
  confirms. `config.py:4417` is True, and its comment records the confirmation.
- **Install day:** the dry run's 8 DRY_RUN rows used up the 2026-09-28 HK-day cap. Every real
  alert frozen later that HK day (Monday's US pre-market filings arrive about 18:00-21:30 HKT)
  closes `CAPPED_DAILY`, a terminal status, and is never sent.

### F10. The grading hook: entry is right; the date count and kill rule are weaker than stated. OWED before n = 100
- **Entry:** correct. `created_utc` → first session that OPENS after it, in New York time
  (`source_scorecard.py:399-417`). A Saturday or a pre-09:30 ET Monday alert enters at Monday's
  open. Un-elapsed horizons are `OPEN`, not dropped (`:503-525`).
- **Date count overstates independence.** `n_alert_dates_graded` counts distinct **UTC calendar
  dates of `created_utc`** (`source_scorecard.py:487`, `alerts.py:422`), not entry sessions.
  Alerts created Saturday, Sunday and pre-open Monday UTC share one entry session but count as
  three "dates". At h=5, alerts on consecutive dates have overlapping windows, while the SE is
  clustered by that same date. That is the estimator defect CLAUDE.md §11 describes (blocking
  that ignores the horizon). **Fix:** count and cluster by `entry_date`, and block by
  non-overlapping 5-session windows.
- **Kill rule measures direction on a stream that is mostly undirected.** 6 of the 8 dry-run
  alerts have `direction_prior = None`, and only directional alerts enter the kill cell
  (`alerts.py:424-426`). The 100-date gate can be met by undirected alerts while the kill cell
  stays `TOO_FEW`, and `kill_rule` (`:447`) treats `TOO_FEW` the same as "did not beat control".
  So the switch to digest is close to preordained, and it would be "no power" read as "no
  effect". It will never keep a useless stream alive, so it is safe in that direction. It can
  still kill a useful one, and it cannot measure what an undirected alert is for (a volatility
  or attention notice).
- **What I would have done:** declare two kill cells before the first send:
  (a) signed excess vs control for directional alerts;
  (b) |return| in sigma vs the matched control for all alerts.
  Report `TOO_FEW` as `CANNOT_DETERMINE`, not as a kill.
- **Selection:** frozen `CAPPED_*` and DRY_RUN rows are graded as well. That is good for
  selection-free measurement, but the graded stream is not the stream the owner saw. Print both.

### F11. Tests. Mostly real; three gaps
- The frozen-before-send, dedup, cap, quiet-hours, level-refusal, no-LLM-import and stranger-drop
  tests would each fail if their feature were removed.
- The render test would **not** fail on F1 (unrealistic fixture).
- Nothing pins F2 (message text frozen) or F3 (price close vs filing time).
- F5 writes to the real corpus.
- The date literals are synthetic and self-consistent (bars built to end 2026-09-25, a fixed
  `NOW`). None compares against `today`, so none will rot.
- No network: the fast-suite guard holds, and the run was offline.

---

## MUST FIX BEFORE COMMIT
1. **F1**: freeze `headline` in the row; line 1 names the item or event and the filing's age.
   Test with a real-shaped fact.
2. **F2**: a `MESSAGE` row (text + sha256 + template and typing versions) appended before the
   send; SEND_RESULT refers to the sha; fsync after the frozen append.
3. **F3**: when the last close predates acceptance, say "reaction not observed yet" and do not
   set `already_moved` from pre-filing closes.
4. **F5**: isolate the digest test from the real `news_corpus` (monkeypatch
   `OPTIMUS_LEDGER_DIR`, or fix `store_article`'s second root).
5. **F6 wording**: stop telling the owner a queue is read when nothing reads it.

## OWED LATER (this week, before n = 100)
- F4: rank for the cap (prior, magnitude, own books, newest); digest what gets capped; refuse on
  a stale Atom source; set a maximum alert age at delivery.
- F7: keep newlines, refuse digests over about 3,800 characters, use a `telegram_paste` origin
  with no default publisher.
- F8: cap stranger rows; make `/ask` the queue; rate-limit the slash model routes.
- F9: write a receipt on REFUSED and on crash; add a `system_health` probe on
  `alerts/receipts/`; review the battery flags; lock `run_pass`; prune receipts.
- F10: count dates by entry session; declare two kill cells; `TOO_FEW` must not kill.

## Send or hold in the meantime
**Hold.** Set `backend/config.py:4417` to `ALERTS_SEND_ENABLED = False`. That is the owner's
call, and I did not change it.
- **Held still records:** the pass keeps freezing rows and closes each one `HELD_NOT_ENABLED`,
  so grading continues.
- **Held does not stop replies:** the reply handler is not gated by this flag, so `stock`,
  `news` and `report` keep working.
- **Why hold:** a message sent before F1 and F2 does not say what happened, and afterwards
  nobody can show what it said.
- **What holding costs:** `HELD_NOT_ENABLED` is terminal and counts toward the HK-day cap. Those
  alerts are never delivered later, and flipping the flag back mid-day finds that day's cap
  already used.
- **Why not STOP:** the STOP file (`alerts/STOP`) stops freezing too, which loses measurement.
  Prefer the flag.
- **If the owner prefers to keep sending:** that is defensible, because these are INFO notices to
  his own phone with no path to capital. Then ship F1 today.

## For the owner, in plain language
The phone channel is safe: only your chat can make the bot do anything, strangers get silence,
and nothing you type can trade, run a program, open a web page or reach your keys. The alerts
themselves are not good enough yet.
- **They do not say what happened.** Today's messages cut off the sentence before the part that
  says what the filing was: "DraftKings filed an 8-K ... re...", when the point was that
  DraftKings changed its auditor.
- **"Within 2 sigma" can be wrong.** It is computed from Friday's close, even when the filing
  came after that close, so it cannot tell you whether the market has reacted.
- **What was sent cannot be proven later.** The system keeps the facts but not the exact
  message you received.
- **Most of these eight are routine:** credit lines, a dividend.

My suggestion: pause the sending for a day (one line in the config), keep the recording running,
and resume once the message says what happened and is saved word for word. One more thing:
"ask" questions go into a file nothing reads yet, so don't rely on them being answered.
