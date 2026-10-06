# Telegram as the remote cockpit (C6, 2026-10-06)

**RESULT IMPROVEMENT: NONE** (operator surface; no strategy, no book, no number moved).

Owner's ask: *"Can I have a conversation with it just by asking questions rather
than sending a / command? Can it send a text with bubbles I can click for certain
responses? Is OpenClaw always on?"*

Answer: yes to all three, once the agent is restarted on this code. Plain
questions are routed to the existing receipt handlers, replies carry 2-4 inline
buttons, and "is openclaw always on" is an intent of its own.

## Where it lives

| file | what changed |
|---|---|
| `backend/services/telegram_cockpit.py` | NEW: intent table, the capped classifier fallback, receipt readers, button map, 30-min context |
| `backend/services/telegram_bridge.py` | `send(reply_markup=)` puts the keyboard on the last chunk; `updates()` also asks for `callback_query`; `poll(callback_handler=)` handles taps (owner chat AND owner sender, or nothing); handlers may return `{text, markdown, reply_markup}` |
| `scripts/telegram_agent.py` | `text_reply` goes through `telegram_cockpit.route_text`; new `callback_reply`; both `poll` calls pass it; `/help` lists the plain-word questions |
| `backend/config.py` | `TELEGRAM_ROUTER_LLM_MAX_PER_DAY = 20`, `TELEGRAM_ROUTER_LLM_MAX_CHARS = 300`, `TELEGRAM_CONTEXT_TTL_MIN = 30`, `TELEGRAM_CALLBACK_TTL_H = 48` |
| `backend/tests/test_telegram_cockpit.py` | NEW: 39 tests |

Runtime state, all under `backend/data/optimus/telegram/` (git-ignored):
`cockpit_context.json` (per-chat context), `callbacks.json` (button id -> action),
`router_llm.jsonl` (one `call` row per classifier attempt, written BEFORE the
call, plus a `result` row).

## Order of resolution for a plain-text message

1. The existing reply grammar's explicit words keep their meaning: `stock X`,
   `news X`, `report`, `digest <paste or URL>`, `analyze <id>`, `ask <q>`,
   `queue`, a bare URL. These go to `alerts_replies.respond` unchanged.
2. **The intent table** (`INTENT_TABLE`, ordered, first match wins). No model.
3. The existing bare-ticker grammar (`NVDA`, `how is NVDA`, `NVDA news`).
   A stock card now also gets the stock buttons.
4. **One** DeepSeek classification via `llm_analyzer._call_llm`
   (`purpose="telegram_router"`, so the language pin, the spend breaker and
   `llm_telemetry` all apply). The full enum is in the system prompt; the reply
   must be JSON whose `intent` is in `INTENT_ENUM`, else it is REFUSED and
   nothing runs. Capped at 20 per UTC day, refused above 300 characters, and
   refused when today's `lab_budget` cap is reached or unreadable. A reply that
   used the classifier says so in its last line.
5. Otherwise the help text.

## The intent table

| intent | example | answers from (no model) |
|---|---|---|
| `refused_action` | `buy NVDA`, `stop the sim`, `approve AP1`, `cancel ...` | REFUSED: plain text never places, approves, cancels, starts or stops anything; use `/approve <id>`, `/deny <id>`, `/sim ...` |
| `openclaw` | `is OpenClaw always on` | two lines: the `openclaw_gateway` row of the newest `health/health_*.json`; then `dowjones/reader_status.json` + the `task:AegisReaderSupervisor` row |
| `reader` | `what did the reader read today` | `dowjones/reader_status.json`: OK pages 10/60 min, 24 h by lane, top sites |
| `pending` | `pending approvals` | `/pending` handler (+ Approve/Deny buttons, see below) |
| `health` | `health`, `what's broken` | newest health receipt: counts + DEAD/STALE rows |
| `digest` | `what's the digest saying` | `alerts_replies.cmd_news("")` = the latest world digest |
| `scale` | `scale to $40k` | the context account's ROI receipt row x the amount, beside SPY's; labelled linear |
| `why_stock` | `why did we buy ACN`, `why this stock?` | pc_book decision rows, fleet_manager buy rows (reason + policy hash), frozen LLM books' per-position thesis, PC snapshot position; "CANNOT EXPLAIN a buy that is not on record" when none |
| `compare_spy` | `compare hack2 to spy`, `and vs spy?` | account: its ROI row (SPY same window); ticker: closes vs SPY over 1/5/21/63 sessions from `prices_2025_26/bars.parquet` |
| `evidence` | `evidence on NVDA` | `model_routing.evidence_text` (the free `/research` read) |
| `fleet` | `show me the fleet` | ROI receipt rows of `alpaca_fleet` + `pc_paper`, plus today's fleet_manager decision counts |
| `account` | `how is pc paper doing`, `how is hack2`, `how is the balanced lane doing` | that account's ROI receipt row |
| `broker` | `cash`, `positions` | `/broker` (cmd_nav: read-only broker GET) |
| `books` / `book` / `forecasts` / `brief` | `books leaderboard`, `ranked book`, ... | the existing handlers |
| `nav` | `how are we doing`, `p&l` | `/nav` (the ROI receipt) |
| `status` | `is the sim running` | `/system` (cmd_status) |
| `help` | `help`, `what can you do` | the plain-word help |

## Button map

`callback_data` is `c` + 12 hex chars (13 bytes; Telegram's cap is 64), resolved
from `callbacks.json`. An id resolves only for the chat it was minted for and
for 48 h; anything else is "expired or unknown".

| after | buttons | action |
|---|---|---|
| a stock (`why_stock`, `stock`, `evidence`, ticker `compare_spy`) | Show evidence · Compare to SPY · Why this stock? · Run deeper research (needs /approve) | reads; the research button calls the existing `/research` handler, which passes `model_gate` and files an approval request. The reply carries Approve/Deny for that new request. Nothing is spent until Approve is tapped |
| an account (`account`, `scale`, account `compare_spy`) | Compare to SPY · Scale to $40k · Scale to $1M · Fleet | reads |
| `nav`, `fleet`, `brief`, `broker` | Fleet · PC paper · Health | reads |
| `health`, `openclaw`, `reader`, `status` | OpenClaw · Reader today · Health | reads |
| `pending` | Approve `<id>` · Deny `<id>` (at most 2 items) | ONLY for PENDING items whose evidence carries a phone-originated `action` (`/research`, `/deep`): the owner created them. Other gates (seeding a lane, a spend above cap) never get a button. At tap time the id is re-checked against the pending queue, then the SAME `/approve` / `/deny` handler runs (age limit, `model_gate`, spend cap unchanged) |

## Safety (what did not change)

- Every send still goes through `telegram_bridge.send`, which resolves the
  owner chat id and redacts. The cockpit adds no recipient.
- A message from another chat is dropped as before. A button tap is honoured
  only when its chat AND its sender are the owner; otherwise it is logged as
  refused, counted in `CALLBACKS_DROPPED`, and gets no `answerCallbackQuery`.
  `handle_callback` checks this again itself, in case a caller forgets.
- No unsolicited message: the router only replies. The alert path is unchanged.
- No order and no approval come from plain text. The classifier's enum holds
  only read intents, and the button actions are `intent` (reads), `research`
  (files a request) and `approve`/`deny` (the existing handlers).

## Restarting the agent safely

The agent runs as `--supervise` (scheduled task `AegisTelegramAgent`). The
supervisor starts `--serve` as a child and restarts it whenever it exits. This
change touches the `--serve` code path only, so **restart the child, not the
supervisor**:

1. Read the PIDs and write them down:
   ```powershell
   Get-CimInstance Win32_Process |
     Where-Object { $_.CommandLine -like '*scripts.telegram_agent*' } |
     Select-Object ProcessId, ParentProcessId, CommandLine
   Get-Content backend\data\optimus\telegram_agent_lock.json   # child_pid = the --serve redirector
   ```
   Expect four rows: two `--supervise` (the venv's pythonw redirector and the
   real interpreter it starts) and two `--serve` (same pair).
2. Kill **the `--serve` redirector by its PID** (`child_pid` from the lock,
   whose command line ends `--serve --interval 3.0`), with its tree:
   `taskkill /PID <child_pid> /T /F`.
   **Never by image name.** `taskkill /IM pythonw.exe` would also kill the
   reader supervisor, the lab and other agents' jobs (protocol rule 6).
3. Within about 5 s the supervisor starts a new `--serve` on the new code. Check
   `telegram/supervisor.jsonl` (a `child_exit` row, then `child_start` with a new
   pid), `telegram/agent.log` ("telegram agent serving as ..."), and that
   `telegram/heartbeat.json` names the new pid.

To restart everything (only needed if the supervisor's own code changes):
create `backend/data/optimus/telegram/STOP` (the supervisor stops itself and its
child by handle), wait for `supervisor_stop` in `supervisor.jsonl`, delete
`STOP`, then `schtasks /Run /TN AegisTelegramAgent`.

## How the owner tests it (on the phone, after the restart)

1. `how is pc paper doing` -> the PC-PAPER ROI row and four buttons. Tap
   **Scale to $40k**, then **Compare to SPY**.
2. `show me the fleet`, then `and vs spy?`: the context resolves to the last
   account or ticker mentioned in the past 30 minutes.
3. `why did we buy ACN` -> the receipts that hold it. ACN appears, in the receipts the router reads, only in two
   random same-band TWIN books ("random same-band replacement for VRT"), so the
   honest answer is that it was a control's draw, not a pick. Tap **Show evidence**.
4. `is openclaw always on` -> two lines. `what did the reader read today`.
5. `buy NVDA` -> REFUSED, nothing runs.
6. Tap **Run deeper research (needs /approve)** on a stock reply -> "Queued
   AP...", with Approve/Deny buttons. Deny it, or Approve it to see the evidence
   read run through the normal gate.
7. A free-form question the table does not cover (e.g. `anything new on the
   paper accounts lately`) -> one classifier call. The reply ends with
   "(understood as '...' by the classifier)". Each such call is a row in
   `telegram/router_llm.jsonl` and a `telegram_router` row in LLM telemetry.

## Tests

`AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_telegram_cockpit.py -q`
covers: 22 utterances through the table with no model; refused imperatives; the
30-min context (and its expiry, and isolation per chat); the fallback refusing an
invented intent (enum sent, `purpose=telegram_router`), accepting an enum answer,
its daily cap, and the default path going through `_call_llm`; callback id
round-trip (other chat, forged, path-shaped and expired ids resolve to nothing);
approval buttons only for owner-created pending items (a forged Approve on another
gate is refused); the research button only enqueuing; a non-owner getting nothing
(not even `answerCallbackQuery`); the keyboard on the last chunk only.

## Review fixes (REVIEW_2026-10-06_C6_TELEGRAM_COCKPIT: F1, F2, F3, F5, F6)

- **F1, entities.** The ticker is extracted independently of the account ("why did hack2
  buy NVDA" answers NVDA in hack2's rows only). A capital stop-word token (IT, ON, NOW, A)
  is a ticker when it is a symbol in the bars panel. If the panel does not have it, the
  bot asks ("write $IT"). Context fills a gap only when the sentence names nothing
  ticker-shaped, and the first line of the reply then says
  `(about ACN: carried from your last 30 min, not named in this message)`. Every entity
  reply starts with `(about X)`.
- **F2, "how are we doing" / "how much did we make".** These now answer the mandate:
  1. PC-PAPER vs SPY over its own window;
  2. live broker equity (read-only GET), labelled "SPY is not re-marked live";
  3. each fleet account over its own window;
  4. `N non-twin = K independent clusters (collapse factor F)`, read from the ROI
     aggregate's `n_ahead_non_twin`, `n_independent_clusters_ahead` and
     `collapse_factor` (or `aggregate.book_dna`).

  Until C3 writes those fields, the reply says "collapse factor NOT YET COMPUTED" and
  never prints the raw ahead/behind counts. `/nav` still prints the full census.
- **F3, age.** Every file reader returns an `Answer` (text, the receipt's own stamp, kind,
  source). `run_intent` passes each one through `stamped()`, which prints
  `as of ... UTC, N h old` and adds `STALE (limit L h)` past `TELEGRAM_RECEIPT_STALE_H[kind]`.
  An unreadable stamp prints "age CANNOT DETERMINE ... treat as STALE". A null field
  prints CANNOT DETERMINE, never $0 or None. Decision lines in "why" carry
  "decided N h ago".
- **F5, taps.** Every owner tap appends a row to `telegram/taps.jsonl` with its id, action,
  args, whether it resolved, and the first line of the reply. Each tap is also a turn in
  `conversation.jsonl`, so it counts against the per-minute reply limit.
- **F6, no silence.**
  - A rate-limited message or tap gets "rate-limited ... Try again in N s".
  - An owner tap past the hourly inbound cap still gets `answerCallbackQuery` with a
    "rate-limited" toast, so the spinner stops.
  - Strangers still get nothing.
