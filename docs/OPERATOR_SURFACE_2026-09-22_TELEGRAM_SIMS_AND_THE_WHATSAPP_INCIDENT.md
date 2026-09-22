# The operator surface — Telegram, the simulation button, and the WhatsApp incident

Written 2026-09-22, after the fact and including the part that went wrong.

---

## 1. THE INCIDENT, FIRST

**OpenClaw messaged one of Murat's friends.** Nobody instructed it to. Two causes,
and the second one is mine.

**Cause 1 — the channel had no boundary to enforce.** OpenClaw was linked to
WhatsApp through *Linked Devices*. That does not create a bot; it makes the agent
a **device on Murat's own WhatsApp account**. It could therefore see and answer
**every** conversation on that account. A friend messaged Murat; the agent
answered as Murat. The messages the friend received were OpenClaw's model errors
(`Authentication failed (HTTP 401)`).

**Cause 2 — I approved a pairing code I had already noticed was wrong.** The code
arrived from `+85264861874`. Murat had given me `+905398863389`. I ran
`openclaw pairing approve`, and *then* remarked that the numbers did not match.
That order is backwards and it is the whole error: the approval was the
irreversible step, so the check belonged in front of it. Approving made that
number the **command owner**.

### What was done about it

| step | state |
|---|---|
| Gateway | stopped, port 18789 confirmed dead |
| Scheduled task | disabled, so it could not auto-restart |
| WhatsApp session | credentials moved to `credentials/whatsapp_REVOKED_2026-09-22` |
| WhatsApp plugin + channel | deleted from `openclaw.json` |
| `commands.ownerAllowFrom` | emptied, then re-pointed at Telegram only |

**One thing only Murat can do:** WhatsApp → Settings → Linked Devices → log the
OpenClaw device out. Revoking our copy of the session does not revoke the link on
WhatsApp's servers.

### The rule that came out of it

> **An agent must never borrow a human's identity on a channel.** A channel
> where the agent *is* the person has no boundary between "the conversation the
> agent was given" and "every other conversation that person has."

A Telegram **bot** has its own identity and its own chat. There is no
conversation it could wander into, because it can only ever see messages
addressed to it. That is a structural property, not a setting.

---

## 2. TELEGRAM — `t.me/murat_aegis_bot`

`backend/services/telegram_bridge.py` is **Aegis's own bridge**, deliberately not
an OpenClaw channel:

* it must work when OpenClaw is stopped (OpenClaw was stopped for most of today);
* what Aegis says about money should come from Aegis's own receipts; and
* the allowlist has to be enforced on our side of the wire.

### The one rule

**`TELEGRAM_OWNER_CHAT_ID` or nothing.** `send()` REFUSES when the owner is
unset rather than replying to whoever spoke last. The destination is
configuration, never message-derived — that is precisely the property WhatsApp
lacked. Inbound from any other chat is logged to `inbox.jsonl`, answered with a
flat refusal, and never executed.

Ownership is claimed once, by the first `/start`, and then frozen. A later
`/start` from anyone cannot move it; changing it is a human editing `.env`.

### What it does

```
/nav      broker equity, cash, positions, day move
/book     the ranked next-month names
/brief    money first, then the book, then what is broken
/sim status | start 8 | smoke 30 | stop | resume
/pending  approvals waiting on you
/approve <id> · /deny <id>
/status   broker, sim, model server, ranker
```

**The approval tap is the part with leverage.** This programme has attended gates
— seeding a lane, a spend above a cap, promoting a candidate to
`CAPITAL_CANDIDATE` — and they currently stall until Murat is physically at a
keyboard. `request_approval()` carries **what it wants, the evidence, and the
worst case in dollars** to his phone. It moves the **latency**, not the gate: an
unanswered request stays unapproved, and the bot approves nothing by itself.

It never places an order. Commands are a fixed dict — there is no shell verb, on
a machine that holds brokerage credentials.

---

## 3. THE SIMULATION BUTTON

Murat: *"the simulations can very from 6-8-10-12 hours ... it should stop at a
safe time save everything and maybe continue not terminate or leave it on the
middle."*

`backend/services/sim_session.py` + `scripts/sim_run.py`.

### Why cycles, not one long job

`night_run_until` is a CLOCK: it kills its tree by PID at T−5. Right for an
unattended deadline, wrong for a button — killing mid-job loses whatever had not
been written, which is how `night_g3_evolve_v2` died 3.1 hours into a 5-hour box
and its receipt read `exited with no receipt`.

So work is cut into **units**: `reconcile → rank → grade → learn`. Each is
idempotent and writes its own receipt. `should_continue()` is consulted **only
between units**, so a stop always lands where the state on disk is complete.

### The state machine

    IDLE · RUNNING · STOPPING · STOPPED · COMPLETED · UNCLEAN

`UNCLEAN` is **derived from the heartbeat**, never stored: a crashed process
cannot set its own "I crashed" flag, and a status that waits to be told will
report RUNNING forever. It means the checkpoint is good and the cycle after it
is unknown — which are different facts from "it finished".

### Measured today, not asserted

| test | result |
|---|---|
| 5-minute smoke | 2 cycles, **0 errors**, COMPLETED, checkpoint written |
| **stop 40s into cycle 1, inside `rank`** | **all four units finished**, checkpointed, STOPPED, resumable |
| resume | same session id, `resume_count 1`, continued from cycle 1 |
| two sessions at once | refused — one session owns the GPU and the broker lease |
| resume into a different mode | refused — "a different experiment wearing its id" |
| vanished process | reads UNCLEAN, not RUNNING |

Durations are **6/8/10/12 hours** only, plus named smoke runs of 5/15/30/60
minutes. An arbitrary duration is how a quick test becomes an unattended 40-hour
run nobody meant to start.

---

## 4. OPENCLAW — what it is actually good for

Measured today rather than hoped for:

* **The model works** — DeepSeek through the gateway.
* **SEC EDGAR**: it fell through three blocked URLs, found the working one, and
  returned **15 genuine 8-K filings with correct CIKs dated 2026-09-21**.
* **Reddit `.json`**: blocked — and it reported `blocked: true` and **invented
  nothing**. That is the single most important behaviour in an unattended agent.
* **Reddit rendered page**: 12 real posts, tickers AVGO / ENRD / NVDA, **no login
  required**. It even noted skipping an ad.

### Where it should be pointed

`NEGATIVE_RESULTS.md` §59 closed price/volume at 21 sessions, and the amplitude
test returned **GO on fundamentals** (38.4–39.5 bps/month vs a 20 bps floor). Our
fundamental panel ends **2024-12-31**. So:

1. **SEC EDGAR** — 8-K/10-Q material events. Proven today.
2. **Company IR pages** — the quarterly numbers that make `gp_at`, `ope_be`,
   `be_me` current. This is the data job the amplitude test authorised.
3. **Pre-open catalyst sweep**, structured into typed events.
4. **Missed-winner autopsy** — for each name we failed to own, what was public
   *beforehand*. The Micron test, automated.

### Credentials

`scripts/openclaw_login.py` signs the browser in from `.env` **without the
password entering a prompt**: `.env` → a `0600` temp file →
`browser fill --fields-file` → the page, deleted in a `finally` on every path.
Putting credentials in the agent message would ship the password to DeepSeek's
API on every login, to sit in whatever request logs live at the other end.

It refuses money-adjacent sites outright (brokerage stays on the API, where an
order carries a `client_order_id` and a receipt), it does not create accounts —
automated signup breaks the terms of every site involved and is the fastest way
to get an account banned — and it **stops at a CAPTCHA or 2FA** rather than
working around the step that exists to stop it.

The browser is Chrome, on OpenClaw's **own managed profile**, isolated from
Murat's personal Chrome. He signs `muratclaw1@gmail.com` into that window once
and the session persists there for every later run.
