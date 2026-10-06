# Review: C6 Telegram cockpit (2026-10-06)

Adversarial second review under the standing rule (owner, 2026-09-25): investor and operator.
Scope: `backend/services/telegram_cockpit.py` (new), the diffs in
`backend/services/telegram_bridge.py`, `scripts/telegram_agent.py`, `backend/config.py`,
`backend/tests/test_telegram_cockpit.py` (new), and the builder's note
`docs/research_notes/2026-10-06/telegram_cockpit_2026-10-06.md`. Reviewed read-only: no
message sent, no process touched, nothing committed.

## VERDICT: MERGE WITH FIXES

Authority is tight. I found no path from plain text or a button to an order, a STOP file, a
sim start or stop, or a message to anyone but the owner. Each button id that resolves is
re-checked, and anything that fails resolution fails closed. The problem is what the cockpit says, not
what it can do. Ask it "why did hack2 buy NVDA" after an ACN question and it answers
**"Why ACN?"** without flagging the swap. It answers the most natural question, "how are we
doing", with a 307-row aggregate that mixes its denominators. No reader in the module ever
compares a receipt's age to the clock. Fixes 1-3 below are required before merge. 4-6 can
follow.

Required before merge:
1. F1: stop context substitution when the sentence names a ticker or an account-scoped ticker.
2. F2: re-point "how are we doing" / "how much did we make" away from `nav_text`'s mixed-denominator aggregate (or fix the aggregate).
3. F3: put an age and a STALE flag on every receipt answer, and render nulls as CANNOT DETERMINE instead of `$0`.

Follow-ups: F4 (spend gate ledger), F5 (tap audit trail + rate limit), F6 (silent no-reply paths).

## Findings

**F1 (HIGH, the cockpit gives the wrong stock without saying so).** `classify` drops the ticker
whenever an account is named (`telegram_cockpit.py:287`:
`out["ticker"] = find_ticker(t) if not out["account"] else None`). `_resolve_entities` then
fills the missing ticker from the 30-minute context (`:874-875`). Tickers that collide with
`_STOP` words (`A`, `IT`, `ON`, `NOW`: Agilent, Gartner, ON Semi, ServiceNow) are also
dropped (`:103-106`). Reproduced with synthetic receipts, three turns in one chat:

    'why did we buy ACN'      => Why ACN? (from decision receipts; no model)
    'why did hack2 buy NVDA'  => Why ACN? (from decision receipts; no model)
    'why did we buy IT'       => Why ACN? (from decision receipts; no model)

The reply never says it substituted. A wrong answer that looks confident is worse than
"Which stock?". No test covers it. The context tests only cover the case where the sentence
names nothing.

**F2 (HIGH for the investor, an existing handler that this build now exposes).** "how are we
doing", "how much did we make" and "how much have we lost" route to `nav` → `_routed("nav")`
→ `model_routing.nav_text`. On today's receipt it answers:

    91 priced accounts ex-twins: equity $69,513,744, P&L $1,080,590 (+1.579%)
    ahead of SPY 148 · behind 159
    `12-1 momentum, k=12, equ` +9.77% vs SPY +8.14%pp
    `Cash/index by default; d` +8.77% vs SPY +7.14%pp
    `Always invested - Book D` +8.77% vs SPY +7.14%pp

- The second line counts 307 rows, twins included. The first line says ex-twins (91). Two denominators sit in adjacent lines.
- Two of the top six are the same return to the basis point: the twin collapse is not applied (this is what C3's `book_dna` is for).
- Each row has its own inception window, so ranking by `vs_spy_pp` compares different periods.
- "$1.08M P&L" is a sum of paper experiments, not the owner's money and not PC-PAPER's mandate.

C6 did not write this handler, but C6 routes the plainest English question in the product to
it. The honest answer to "how are we doing" is PC-PAPER vs SPY over its own window, plus the
fleet, plus the count of independent books ahead after the twin collapse.

**F3 (MEDIUM, no reader in the module checks receipt age).**
- `account_text` and `scale_text` print only the receipt filename (`:428-435`, `:473`).
- `fleet_text`, `health_text`, `openclaw_text` and `reader_text` print a stamp but never compare it to now.
- `why_stock_text` prints the snapshot `t` the same way.

This is the house failure from CLAUDE.md's funnel section ("a health row that prints a date and
cannot go red is decoration"). Today's ROI receipt was generated at 04:59 UTC. During the US
session, "how is pc paper doing" answers from it, while "cash" or "positions" go to the live
broker (`cmd_nav`). The owner gets two different numbers for one account a minute apart, and
neither one carries its age. Null fields also render as plausible values. Reproduced:
`equity $0 on $0: +2.00%`, `since None`, `SPY same window n/a`. By contrast, the existing
`report` command in `alerts_replies` does print "newest receipt + its age".

**F4 (MEDIUM, the dollar gate reads a ledger the router never writes).** `classify_llm` refuses
when `lab_budget.spend_today()["cap_reached"]` (`:357-364`). But `_call_llm` records cost in
`llm_telemetry` (`llm_analyzer.py:375-377`), never in `lab_spend_<day>.json`. The router's own
spend therefore cannot move the gate it checks. This is the lesson from 09-21: "a cap that reads
a different ledger than the writer cannot bind". `model_gate` already has the same pattern.

The count cap does bind: `router_llm.jsonl` is both the ledger it reads and the ledger it
writes, and the `call` row is written before the call. Each classification costs fractions of
a cent, so the dollar risk is negligible. The note's claim that the spend cap applies is still
only nominally true. Separately, the router counts its cap per UTC day while model commands
count per owner-local day.

**F5 (MEDIUM, button taps are invisible to the conversation ledger and the rate limit).**
`handle_callback` calls neither `_log_turn` nor `replies_rate_limited`. Taps are not in
`conversation.jsonl`, and they skip `TELEGRAM_REPLY_MAX_PER_MIN`. The inbox row stores only the
opaque id. `callbacks.json` is git-ignored and pruned at 48 h or 500 entries, so after two
days an inbox tap row cannot be traced to what it did. For an Approve tap, `approvals.jsonl`
records the resolution but not that a button caused it.

**F6 (MEDIUM, paths where the owner gets no reply and no explanation).**
- A rate-limited plain-text message returns `None` (`:914-916`). The owner sees nothing.
- Past the owner's hourly inbound cap, `_poll_callback` returns `None` without `answerCallbackQuery` (bridge diff), so the button spinner hangs and no reply arrives.
- An existing problem, now hit more often: a 429 on `sendMessage` makes `send()` retry once without `parse_mode`, and the second 429 raises out of `poll()`. `updates()` has already advanced the offset, so that reply and every remaining update in the batch are lost. The research button now produces two messages (the APPROVAL NEEDED message from `request_approval` plus the cockpit's "Queued ..."), and every tap adds an `answerCallbackQuery`.

**F7 (LOW, a corrupt `callbacks.json` is overwritten silently).** Reproduced: after the file is
corrupted, `resolve` returns `None`, which is correct and fails closed. The next `mint` then
rewrites the file with a single id and logs nothing, so the corruption leaves no trace. The
read-modify-write takes no lock. With one serve child that is safe. With two, ids would be
lost, but they would still fail closed.

**F8 (LOW, `why_stock` treats an error as an absence).** `LP.read_books()` errors are swallowed
(`:629-633`). A broken books reader therefore produces "CANNOT EXPLAIN a buy that is not on
record", which should read "could not read the books". "PC book rank N" is a ranking, not a
buy.

**F9 (LOW, the "chat AND sender" claim holds for buttons only).** Text messages are still
checked on chat id alone (`telegram_bridge.poll`, existing behaviour). Today the owner chat is
private (positive id, chat equals sender), so the two checks are equivalent. If the owner id
were ever a group, two things would break:
- every button would fail, because `from.id` never equals a group id;
- any group member's text would be answered and could use up the 20 daily classifier calls.

Either state "private chat only" as an invariant with a test, or add the `from.id` check to
the text path.

**F10 (LOW, routing misfires found by probing `classify`).**
- "how is it doing" right after a ticker turn → `nav` (fleet-wide), not the ticker.
- "why is the system red" → `status`, not `health`.
- "status of AP2026…" → `status`.
- "how is NVDA doing", "are we beating spy" and "what did we buy today" all spend a classifier call. The note says the bare-ticker grammar handles "how is NVDA", but `alerts_replies.parse("how is NVDA doing")` returns `help`.
- Fleet lines print `vs SPY +1.06% pp`, which reads as "SPY returned 1.06%". Print `+1.06 pp vs SPY`.

**F11 (INFO, authority verified, with evidence).**
- `INTENT_ENUM` holds read intents only. `run_intent` maps them to the handlers `nav`, `broker` (`cmd_nav`, a broker GET), `book`, `books`, `forecasts`, `brief`, `system`, `pending`, or to file readers. `sim` is never referenced.
- An LLM reply outside the enum is refused (`_parse_llm`, `:329-331`), and `none` returns help. The enum is in the `system` string passed to `_call_llm`, and `_LANGUAGE_PIN` is appended centrally on the DeepSeek path (`llm_analyzer.py:367-368`). Telemetry is cut by `purpose="telegram_router"`.
- `resolve` requires `c[0-9a-f]{12}`, the minting chat and age ≤ 48 h, and fails closed otherwise. Only code paths mint ids. `callbacks.json` is not writable over the network.
- An Approve or Deny button resolves only for PENDING rows whose `evidence.action.cmd` is `research` or `deep`, re-checked at tap time. `request_approval` has one caller (`_routed`), so no other process creates rows of that shape. A second tap on the same id is refused because the row is no longer pending.
- Residual by design: two taps (Research, then Approve) can spend one paid model call, through `cmd_approve`'s 60-minute age limit and `model_gate`. Existing behaviour: approving an over-age request flips its state to APPROVED without running it.

**F12 (INFO, operator reality).**
- The four processes are one supervisor and one `--serve` child. Each is a venv `pythonw` redirector with the base interpreter beneath it. There is one lock and one child, and `updates()` advances the offset before handling, so delivery is at-most-once: no double answers, but a kill mid-batch loses messages.
- The lock's `child_pid` is the redirector, not the interpreter. A restart should kill that PID, then confirm the base-interpreter grandchild has exited too. Do not assume the launcher's job object takes it down; verify it with `Get-CimInstance`. Never kill by image name. The supervisor respawns after its backoff.
- File modification times are later than the running child's start time, so the live bot still runs the old code and still requests `allowed_updates: ["message"]`.
- `supervisor.jsonl` shows four heartbeat-stale kills today, stale for up to about 59 minutes. The classifier adds a synchronous network call to the poll loop. Confirm that the DeepSeek client timeout is shorter than the 600 s heartbeat limit.

**F13 (tests).** Command:
`AEGIS_PERSONAL_MODE=0 AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/test_telegram_cockpit.py backend/tests/test_alerts_replies.py backend/tests/test_telegram_supervisor.py -q`
Result: **72 passed in 2.36s** (39 cockpit tests collected).

Four tests assert a mock or the source text rather than behaviour:
- `test_the_agent_wires_the_router_and_the_button_handler` greps source text.
- `test_the_default_fallback_goes_through_call_llm` asserts the kwargs a mock received. Nothing checks that a telemetry row with `purpose=telegram_router` is written.
- `test_the_research_button_only_enqueues_the_approval_flow` stubs `research` with a re-implementation of `_routed`, so the real double message is untested.
- `test_approval_buttons_only_for_pending_items_the_owner_created` stubs `approve`, so `cmd_approve` itself is never exercised.

Missing tests:
- explicit ticker plus context (F1);
- a stale receipt (F3);
- a corrupt `callbacks.json` (F7);
- the rate-limited silence (F6);
- a group-chat owner (F9).

## The investor's question

Does this get the owner to a true number faster? It makes looking faster: one tap gets the
fleet, health, or OpenClaw. It does not make the answers truer, and in three places it hides
caveats that the slash-command answers kept:

- **"how are we doing"** (F2): a mixed-denominator aggregate with duplicate books in the top six and no twin-collapse factor.
- **"how is pc paper doing"** during the session (F3): the morning receipt with no age, while "positions" answers live.
- **"why did hack2 buy NVDA"** (F1): a confident answer about a different stock.
- **"scale to $1M"**: arithmetic correctly labelled linear, but a +2% paper return ×1M reads as a forecast on a phone screen. The label should lead the reply, not trail it.

It is a chat layer over the same receipts. That is acceptable if every answer carries its
receipt's age and its denominator, and today none does.

## What I would have done instead

1. **Age and denominator on every answer.** Each reader returns `(text, as_of)`. `reply_for` appends `as of HH:MM UTC (N h old)` and prints STALE past a threshold set in config. A null renders as CANNOT DETERMINE. Make this one function the readers cannot bypass, not a per-reader habit.
2. **"How are we doing" answers the mandate, not the census.** PC-PAPER live broker equity vs SPY over its own window, the fleet below it, then "N independent books ahead of SPY of M after twin collapse (book_dna)". Point `nav` at that once C3 lands, and leave the 307-row aggregate behind `/nav`.
3. **Entities are never silently inherited.** Extract the ticker independently of the account, treat any token that is a known symbol in the bars universe as a ticker even when it is a stop word, fill from context only when the sentence has no ticker-shaped token, and always echo "(about ACN, from the last 30 min)". Also: an append-only `taps.jsonl` (id, action, args, first line of the reply) and a one-line "rate-limited, try again in N s" instead of `None`.

## Score: 70 / 100

Authority and fail-closed design: strong (about 25 of 25). LLM fallback discipline: good apart
from the ledger mismatch (15 of 20). Truthfulness of answers: weak, because of F1, F2 and F3
(10 of 25). Silent fragility and operator reality: fair (12 of 15). Tests: fair, with several
asserting mocks and the key cases missing (8 of 15).
