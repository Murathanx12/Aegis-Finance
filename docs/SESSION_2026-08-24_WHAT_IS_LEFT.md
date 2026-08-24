# SESSION 2026-08-24 (evening) — what is left

Pair with `docs/SESSION_2026-08-24_WHAT_WAS_DONE.md`. This is the handoff half:
what the next session picks up, in order, and what it must not touch.

---

## 0. TONIGHT, and it is the only thing with a clock

**`python -m scripts.monday_gate_check`** — one command, both clocks built in.

The scheduler is US/Eastern, this machine is UTC+8, and a Hong Kong Monday
EVENING is Eastern Monday PRE-DAWN. The jobs fire on the **local Tuesday**:

| job | ET | HKT | what it must show |
|---|---|---|---|
| `pi_options_pit` | Mon 15:30 | **Tue 03:30** | `options_pit` leaves ABSENT. **A missed day is LOST EVIDENCE** — option chains have no history. |
| `pi_why_moved` | Mon 17:15 | **Tue 05:15** | `live_forward` stops being quiet. Still quiet Tuesday ⇒ **P0**. |
| `pi_arena_daily` | Mon 17:45 | **Tue 05:45** | nine seeds migrate to `book-v1`; nine books run; `event_store` leaves ABSENT; NAV rows go 1 → 2. |

**`trades > 0` on the arena broker is the FINDING, not the success.** The Alpaca
account is empty and `sync` deliberately will not open the first position; only
the attended seed does that. `execution_ledger` should stay ABSENT.

**Pre-flight verified 05:14 ET Monday:** live `config_hash` = local
(`641adafc`), 0 of 9 books stamped, `nav_rows` all 1, and the per-book
fingerprint formula byte-identical to the legacy value for all ten. The one-way
door is intact.

> **DO NOT ADD ANY BOOK TO `arena_books_v1.yaml` UNTIL THE MIGRATION IS
> CONFIRMED IN `/api/arena/status`.** Adding one first makes
> `assert_config_current` refuse to run *and* refuse to migrate — all nine, and
> the NAV histories are stranded permanently. Untouched all session.

## 1. Then: the first independent book — `EVENT_RESPONSE_v1`

The review's stated milestone, and the blocker is gone: the options feature
**transfers** (§2 of the done-doc). What remains is scaffolding, and none of it
needs the YAML until the migration lands.

1. **Declare `event_response` in `information_bus.FAMILIES` as `CANDIDATE`.**
   Safe by construction — `CANDIDATE` is excluded from `state_families()` and
   from `composite_fingerprint()`, so it moves `bus_version` and drifts no book.
   That is exactly what P0.2 was built to permit; it is also a live test of it.
2. **Add an `event_response_v1` entry to `selector_identity.SELECTORS`** with
   `baseline=None` (no seeded history to protect) and dependencies naming only
   the event/options families. `test_selector_identity` already pins that
   changing the composite must not move it.
3. **Build the selector** and freeze its strategy contract *before the first
   decision* — policy hash, timestamp, inputs, costs, fill convention,
   objective. `PRODUCT_EXPERIMENT` needs no significance gate, but it needs
   that.
4. **Only then** add the book to `arena_books_v1.yaml`, as its own selector.
   **Never as an `arena_composite` weight** — folding it in hides the only thing
   worth testing, whether its errors are *different* errors.

**Carry the caveats onto the book's face.** The transfer is one live
cross-section of 39 names against a 168-month panel; `pct_positive` is 46.2%
against the panel's 54.8% (inside the declared bar, and a tree splits on
thresholds); and 0.0037 of median is still unexplained, where implied financing
above OIS and general borrow both live unmeasured. The collector accrues daily
from tonight — **the honest version of that number is the same comparison over a
month of snapshots**, and it costs nothing but waiting.

## 2. Two DeepSeek items, one small and one already half-answered

**a. `why_moved` is the one call site not yet wired to the language contract.**
`llm_language.DEFERRED` carries the dated reason: it fires tonight and is the P0
being waited on. **Wire it once tonight's run is confirmed** — the edit is two
lines and `test_llm_language_contract.py` will start enforcing it the moment the
entry is removed from `DEFERRED`.

**b. JSON mode is used in ONE module, not none.** `architecture_arena` already
passes `response_format={"type": "json_object"}`; the other structured callers
— arena beliefs, expectations, the daily brief — parse loose text. Extending it
is the highest-value remaining reliability fix and it is small. DeepSeek
requires the word "json" in the prompt when that mode is set, so it is a
per-caller opt-in rather than a global flag.

**And the empirical picture is better than the anecdote suggested.** The
`INTERNET-INVESTIGATOR-FWD-1` job running during this session logged **303
DeepSeek calls with `schema_valid` 303/303 and zero errors**. The Chinese
code-switching is real but it is not a general reliability problem — which is
what makes the pin plus the refusal counter the right response rather than a
provider change.

## 3. Alpha, in the order the review set — with two lanes now closed

| item | state |
|---|---|
| **A** Event Response train/serve | **DONE** — transfers |
| **B** `MANAGEMENT_EVASION_DELTA_v1` | **BLOCKED ON DATA.** No earnings-call text anywhere in this repository. FMP/Bigdata acquisition unpriced. Transcripts are archival, so unlike the options collector there is no perishability urgency. |
| **C** `REVISION_FORECASTER_v1` | **STOP**, pre-registered, with an equivalence bound |
| **D** `ACTOR_DIALOGUE_EPISODE_v1` | blocked behind B |
| **E** `RELATIVE_VALUE_v2` | waits on richer state; the v1 NN question stays closed |
| **F** graph successor | **RETIRED** — `GRAPH-MIDCAP-SCREEN-1` closed it for one coverage pull |
| **G** `META_ROUTER_v1` / `DISAGREEMENT_LAB_v1` | still gated: needs three independent selectors with live output. There are zero. |

**C weakened B rather than strengthening it.** A text model that merely predicts
the revision would be predicting something already priced — the mediator is
trivially predictable from the numeric print. If the call text is worth
anything it must be worth it against **returns directly**.

So the honest read of the board: **after `EVENT_RESPONSE_v1` there is no
unblocked alpha item left.** B and D need a data purchase; E needs B; G needs
three selectors. That is a decision for Murat, not a task for a session — and
it is the most useful thing this session can hand over.

## 4. Standing items unchanged

* Which population G7 counts (`live_forward` vs `arena_forward`) — attended.
* **Rotate the arena Alpaca secret** — it was pasted in plain text into a chat
  session before reaching `.env`.
* The attended one-time arena Alpaca seed, only after settled `CURRENT_BEST`
  internal positions exist; disable seeding again immediately after.
* 25 quarantined overdue forecasts on `live_forward` — attended disposition.

## 5. Rules this session added, which the next one inherits

* **Derive `outcome_dispersion` from a realised prior on the same panel, never
  from the theoretical null** — it understates by ~45% here, and a comparable
  realised figure (`EVENT-RESPONSE-2`, 0.0276) was already on hand and unused.
* **When a mediator is observed at `t1`, the return window starts after `t1`.**
  Otherwise you are scoring the mediator against its own past. Cost: a t of 4.04
  and a written interpretation.
* **Never read a vendor's implied-volatility column.** Read prices, declare the
  convention.
* **Never move `.env` to reproduce CI** — `AEGIS_IGNORE_DOTENV=1`.
* **DeepSeek is the only provider**; every guard belongs on its path, not on the
  dormant Claude branch.
* **A screen registers in `Aegis module/TRIALS/`, not in `rule_experiments`** —
  that table is for forward-accruing lane trials with a live clock.
