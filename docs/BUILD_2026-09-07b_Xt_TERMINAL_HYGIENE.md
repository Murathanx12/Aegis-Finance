# BUILD 2026-09-07b — BLOCK Xt: TERMINAL HYGIENE (X1, X3, X4, X10)

**Repo:** `aegis-alpha-terminal` (the EXECUTION brain). Nothing in
`aegis-finance` was changed by this lane except this file.
**Roadmap rows:** `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 block X — X1
(clock skew), X3 (non-trading-day fixtures), X4 (`VENUE_REJECTED`), X10 (fleet
citation + D3 audit re-run).
**Licence:** none — this is hygiene. No book, no claim, no order, no deploy, no
LLM call. **$0 spent.**

> **RESULT IMPROVEMENT: NONE.** No strategy was run, no edge was measured and no
> forward evidence accrued. This lane closes four guards, one of which was
> silently disarming the opening-range gate whenever the machine drifted, and
> one of which was making a closed venue read as a barren alpha layer.

---

## 1. Test counts — `python run_tests.py`, the only supported way

| when | suites | checks | verdict |
|---|---|---|---|
| **BASELINE** (before any edit in this lane, 2026-09-07) | 80 | 3,697 | exit 0, **ALL PASS** |
| *intermediate, reported by the lead session* | 83 | 3,813 | 3 failing: `band_mode` (lead's, fixed by them), `expiry_day` (**mine** — see §2 X1), `test_isolation` (E1 agent's new `tests_smoke_news_pull.py`) |
| **FINAL** (all three lanes in the tree) | **84** | **3,868** | exit 0, **ALL PASS** |

**One run in between reported `PRODUCTION LEDGER WRITTEN` and it was not a
test.** `state/decisions.jsonl` grew by 20,418 bytes mid-run.
`run_tests.py` fingerprints that file before and after the whole run and
attributes any growth to a suite, which is the right default and was the wrong
reading here. The ten new rows were `account_role=hack3`,
`brain=tracker_portfolio`, `action=refused`, on real names (TNXP, ASPI, DAKT,
LENZ, ANIP, RRX) — the lead session's own hand-run dry `scripts.run_pass`,
confirmed by them. The decisive evidence is structural rather than
circumstantial: `run_tests.py` exports `AAT_LEDGER_DIR` to a temp directory and
**only an env var reaches a child**, so no suite or grandchild of that run can
write `state/`; the sibling file `state/forecasts.jsonl` was written in the same
second, which is only reachable with `AAT_LEDGER_DIR` unset. The final run above
was bracketed with my own before/after fingerprint and all four production
ledgers are **byte-identical**:

```
decisions.jsonl       17,944,750 -> 17,944,750   unchanged
forecasts.jsonl        4,927,699 ->  4,927,699   unchanged
counterfactual.jsonl 1,118,870,798 -> 1,118,870,798 unchanged
fills.jsonl            2,188,878 ->  2,188,878   unchanged
```

**The torn hash chain was NOT repaired and nothing was deleted.** Repairing a
tamper-evident chain is the tampering. Incidentally, those rows are the first
production sighting of this lane's `SESSION CLOSED` refusal doing its job on a
genuinely closed venue — they carry a reason where they would previously have
been a silent zero.

No suite reported zero `ok` lines. `tests_smoke_expiry_day.py` is green at **3
checks**, which is its baseline count — it is a three-assertion suite, not a
suite that stopped running.

This lane's own contribution to the count: **+48 checks** —
`tests_smoke_session_fixture.py` (new, 37), `tests_smoke_labor_faults.py`
(53 → 62), `tests_smoke_refusal_nav.py` (36 → 38). The rest of the delta belongs
to the lead session and the E1 agent, whose files this lane did not touch.

**No inherited failure is being hidden.** The baseline was green; the only red I
produced was `expiry_day`, it was mine, it was reported to me by the lead
mid-flight, and it is fixed and named in §2.

---

## 2. Row by row

### X1 — CLOCK SKEW GUARD · **DONE**

**Proving test:** `tests_smoke_labor_faults.py` case C1-8 (the case the roadmap
calls "case 6"), flipped from
`check("nothing in the repo compares the local clock to the venue clock", ...)`
to a guard that measures ±20 min and refuses both. Second proof:
`tests_smoke_session_fixture.py` (new) exercises it through `run_pass` end to
end. C1 receipt row now reads:

```
verdict : PASS   (was "FAIL (REPORTED, NOT FIXED)")
observed: skew_guard_exists=True measured_fast=+1200s measured_slow=-1200s
          refuses_both=True tolerance=300s exits_unaffected=True
```

**What was built** (`alpha/runner.py`):

- `CLOCK_SKEW_LIMIT_S = 300.0`, `ClockSkew`, `venue_clock_skew(client)` — ONE
  `GET /v2/clock` probe per pass; `seconds = local UTC − venue UTC`.
- Skew beyond tolerance ⇒ every forecast is **counted and refused** under the
  new `runner.REFUSAL_CLASSES` member `clock_skew`, which types through
  `refusal_classes.CLOCK_SKEW → DATA_STALE`.
- **Exits are untouched, and that asymmetry is the design.** `alpha/exits.py`
  does not import the guard and does not name it; two checks in the new suite
  and two in C1-8 fail if that stops being true, plus a behavioural one: a
  position 11% underwater still exits with a 20-minute skew in the building.
  Refusing to *open* risk on an unverifiable clock costs one pass; refusing to
  *close* it costs the position.

**Three judgement calls, stated rather than buried:**

1. **An unreadable venue clock does NOT refuse by default.** `/v2/clock` is
   unreachable exactly when the venue is unreachable, and a pass that cannot
   reach the venue already dies at the order — turning a transport blip into a
   fleet-wide entry freeze buys nothing and hides the real fault. It is LOGGED
   as `venue clock UNVERIFIED`, carried on the object as `verified=False`, and
   `AAT_CLOCK_SKEW_STRICT=1` makes it refuse. Both branches are pinned.
2. **The probe does NOT skip on `dry_run=True`** — the lead session proposed
   exactly that as the fix for the red suite, and I took the other branch, so
   the disagreement is on the record. Skipping on `dry_run` is defensible ("an
   entries-refusing guard has nothing to refuse on a dry pass") and it costs the
   rehearsal: `scripts.monday_dry_run` exists to show what the *live* pass would
   do, and a guard that switches itself off in the rehearsal makes the rehearsal
   lie — a Monday dry run would report a clean pass on a machine whose clock
   would have refused every entry at 10:01. It would also have removed the guard
   from every suite that exercises `run_pass` dry, which is all of them. The
   ordering fix below satisfies the same suite without either cost, and the
   guard is live on the live path and the dry path alike.
3. **The ET gates themselves are unchanged.** `in_opening_range`,
   `deadline_liquidation_due` and `session_day` still read the local clock and
   still misbehave under skew — C1-8 still measures all three doing so. What the
   guard buys is that the pass *refuses* rather than acting on gates it cannot
   trust. Re-deriving four gates against a timezone database on a slim container
   is a different, larger job.

**The red suite I caused, and how it was fixed.** The first cut probed the clock
*before* the expiry-day gate, reasoning that the expiry gate is itself derived
from the local clock. That made an expiry-day pass reach for `client.clock` and
broke `tests_smoke_expiry_day.py`, whose stub raises on any attribute access.
**The suite was right**: R1's expiry guard is decided from local knowledge alone
and must need no venue. The fix is ordering, not a dry-run exemption — the
expiry gate now runs first, and nothing is lost, because a skew large enough to
move an ET *date* is hours, and if it hid the expiry day the probe immediately
below refuses the whole pass anyway. **There is no ordering in which a skewed
clock buys an entry.** The ordering is now pinned in
`tests_smoke_session_fixture.py` as well as in `tests_smoke_expiry_day.py`.

### X3 — NON-TRADING-DAY FIXTURES · **DONE**

**Proving tests:** the four named suites green today on a **real closed venue**
(2026-09-07 is Labor Day) — `tests_smoke.py` 595, `tests_smoke_equity.py` 66,
`tests_smoke_pair.py` 45, `tests_smoke_entry_timing.py` 78 — plus
`tests_smoke_session_fixture.py` (new, 37 checks) for the open-venue and
closed-venue fixtures.

**The actual bug, which was not the one the row describes.** All four suites had
already done the obvious right thing and derived their session clock from
`today` instead of writing a literal date. They broke anyway, because they mixed
two clocks:

```python
NOW_ET = datetime.now().date()               # LOCAL — this box is UTC+8
EXPIRY = datetime.now(timezone.utc).date() + 1 day
```

Between 20:00 and 08:00 local the local date is already tomorrow and the UTC
date is not, so the derived session lands **on** the expiry, `run_pass` correctly
refuses the whole session as its own expiry day, and the suite reads a zero it
cannot explain. Measured by sweeping every hour of 500 days at UTC+8:

> **the old derivation collided on 2,864 of 12,000 hours — 23.9% of all
> wall-clock hours.** The new derivation collides on 0, and never lands on a
> weekend or an exchange holiday.

That sweep is a check in the new suite, and it asserts the OLD formula collided
as well as that the new one does not — a fixture fix nobody can see fail is not
a fixture fix.

**What was built:**

- `tests_fixtures.py` (new, repo root, not collected by `run_tests.py`): one
  derivation of session + expiry, both from `alpha.exits.now_et()`, with an
  explicit NYSE full-closure table for 2025-2027 and `HOLIDAYS_COVER` stating
  where the table stops. **A weekday is not a session** — 2026-09-07 is a Monday
  *and* Labor Day. `session_clock()`, `expiry_after_session()`, `open_clock()`,
  `closed_clock()`, `event_date_pending()`.
- The three end-to-end suites now import it, and their `FakeClient.clock()`
  returns the real `open_clock()` payload instead of `{"is_open": True}` — so the
  venue-open fixture X3 asks for exists and the skew guard is genuinely
  exercised rather than degrading to CANNOT DETERMINE.
- **`considered=0` is gone from both branches that produced it.**
  `runner.venue_session_closed()` refuses a pass when the venue is shut *and its
  own `next_open` is on a later ET date*, and the expiry-day branch — which
  returned `considered=0 refused=0` — now counts and types every forecast. New
  class `session_closed` → `refusal_classes.SESSION_CLOSED` → `MANDATE`
  ("the SESSION had no authority", the same state `PAST_LIQUIDATION_DEADLINE`
  maps to).

**`is_open == False` is deliberately NOT the test.** The pre-open auction pass
(`scripts.open_auction`, `entry_style="open_auction"`) runs while the venue is
shut, and refusing on `is_open` would have deleted a live entry route. The test
is "no session will happen today at all", which is true on a holiday, at a
weekend and after the close, and false pre-open. Pinned by a check.

**One seam found and reported, not fixed:** `run_pass` computes its
`printing` (event-pending) set with `d >= datetime.now(timezone.utc).date()` — a
UTC date — while every other date in the pass is ET. The two differ for four
hours a day, and by three days whenever the latest session is not today.
`tests_fixtures.event_date_pending()` clears whichever is later and says why.
Changing which clock the entry pass reads pendingness off is a change to the
live entry gate of six services and is not a fixture's call.

### X4 — `VENUE_REJECTED` REFUSAL CLASS · **DONE**

**Proving tests:** `tests_smoke_terminal_state.py` (the enum test: "the declared
enum is exactly the **eighteen** states", plus five new real sentences),
`tests_smoke_refusal_nav.py` (kinds and disjointness), and the C1-14 row in
`tests_smoke_labor_faults.py`, whose receipt now reads:

```
verdict : PASS   (was "PASS (with a REPORTED gap)")
observed: venue_http_refusals_typed_VENUE_REJECTED=3 of 3   kind=venue
```

**What was built** (`alpha/refusal_classes.py`): an eighteenth `TERMINAL_STATE`
and a post-hoc class matched **LAST** — so it can only claim sentences no
in-house gate wrote — whose regex is `AlpacaPaper._request`'s own two refusal
formats and nothing else (`<METHOD> /vN/... -> HTTP <code>` and
`-> transport failure:`). It is its own `kind_of` value, **`"venue"`**, beside
book-state / merit / tournament, because a counterfactual on it asks *"would the
order have paid if it had reached the book"* — neither "should the book have had
room" nor "was the idea good" — and because it is fixed by retrying, re-routing
or repairing the account, never by loosening a gate.

**This changes grouping in every finished report, which is why C1 declined to do
it in a lab commit and why the roadmap row is the attended decision.** Named
explicitly: HTTP rejections move out of `OTHER_TYPED`; and a halt
(`HTTP 422: asset is not tradable`) moves out of `MANDATE` into
`VENUE_REJECTED`, which is the more accurate reading — the venue refused it, we
did not. A check pins that our own gates (`DAILY LOSS LATCH`, `OPENING RANGE`)
are **not** re-labelled.

### X10 — FLEET CITATION, D3 AUDIT, RUNBOOK ROWS · **DONE**

**The citation.** `alpha/fleet.py:113` (hack2's caveat) cited
`docs/CONTRACT_DRAFT_2026-09-06_REVISION_BOOK.md`. That file has **never existed
in the terminal repo** — it is `aegis-finance/docs/`. A reader inside the
terminal repo following that path gets a 404 and, on this programme's own
record, concludes the document was never written. Fixed to name the repo, and
the line says out loud that the bare path was wrong. One string; nothing else in
`fleet.py` was touched. `tests_smoke_fleet.py` green at 103 checks.

**The D3 audit — re-run, and now re-runnable.**
`state/labor_day_lab_2026-09-07/D3_tuesday_rearm_audit.json` was made by hand on
2026-09-05 and went stale within a day: on 2026-09-06 hack2 was declared
manage-only (commit `5875483`) and the receipt still said
`hack2 ENTRY_STATE_AFTER_DEPLOY: ARMED, declared_manage_only: false`. A receipt
that disagrees with the code is worse than no receipt, because it is the
artefact a Tuesday morning reads to decide whether a book may enter.

New `scripts/labor_d3_rearm_audit.py` — offline, read-only, no `railway` call,
no network, no venue. It **derives** the ARMED/DISARMED column from
`alpha.fleet.env_for()`, the same function `scripts.fleet --deploy` uses, so the
column cannot drift from the deploy by construction.

The audit was run three times over the day and **caught the fleet changing under
it**, which is the whole reason it now exists as a script:

| run | hack2 derived | note |
|---|---|---|
| 2026-09-05 (hand-made receipt) | ARMED | stale within a day |
| first re-run, this lane | **DISARMED** | picked up commit `5875483` |
| final re-run, after the lead's change | **ARMED** | `manage_only=False` restored once the contract was frozen |

Final state, and the state the Tuesday re-arm should read:

```
  hack1  DISARMED  declared_manage_only=True   live(read 2026-09-05)=DISARMED
  hack2  ARMED     declared_manage_only=False  live(read 2026-09-05)=DISARMED
  hack3  ARMED     declared_manage_only=False  live(read 2026-09-05)=DISARMED
  hack4  ARMED     declared_manage_only=False  live(read 2026-09-05)=DISARMED
  hack5  ARMED     declared_manage_only=False  live(read 2026-09-05)=DISARMED
  hack6  ARMED     declared_manage_only=False  live(read 2026-09-05)=DISARMED
```

**hack2's re-arm is the lead session's, it is deliberate, and it was not
reverted.** Its stated unblock condition — "manage-only until its own contract is
frozen" — is met by `contract.HORIZON_REMAP["hack2"]`: horizon 5, min hold **2**,
**no** profit target, 8% stop. That answers all three clauses of the 2026-09-06
objection (zero min hold, +2.5% target, 3% stop). A gate whose condition has been
met and which stays shut is not caution, it is an unread gate.

The LIVE column is **CANNOT DETERMINE for today**: a Railway variable is
invisible to a local process, this lane is forbidden from touching Railway, and
the script deliberately does not shell out. The 2026-09-05 values are carried
forward verbatim under `LIVE_NOT_RE_READ`, stamped with the date they were
actually read.

**A bug in my own carry-forward, found by running the script twice.** The first
generation read the hand-made receipt's *flat* keys and wrote them *nested*, so
its own second run found nothing at the flat names and silently replaced a real
2026-09-05 reading with `CANNOT_DETERMINE` — a migration that destroys the column
it exists to preserve. Fixed to read both schemas, the committed receipt was
restored from `git show HEAD:` as the carry-forward source, and idempotence was
verified by running it three more times. This is exactly the failure the script
was written to stop, committed by the script itself on its second invocation.

**Runbook rows.** `docs/RUNBOOK_2026-09-08_REARM.md` §A.5 (the rows the roadmap
numbers 352-361) said `hack2 ARMED — nothing, this book may enter`, with no date
and nothing to re-derive it from. It now carries the re-derivation command, the
current table, and the fact that **hack2 went DISARMED on 09-06 and ARMED again
on 09-07** — so the table matching 2026-09-05 is a coincidence, not evidence that
nothing happened, and the receipt's `changed_since_previous_receipt` will read
`(none)` for that reason. The `### hack2 is armed…` section was rewritten to
record why it was disarmed, exactly what had to become true to re-arm it, and
the residual: hack2 is still not in `TRACKER_BOOKS`, so if its `HORIZON_REMAP`
entry is ever removed it falls back to the EVENT defaults and the 09-06
objection returns without anyone deciding it should.

---

## 3. `AAT_MANAGE_ONLY` — the verdict, with evidence

> **CONFIRMED INERT. Nothing reads it. Setting it on Railway disarms nothing.**
> The report I was asked to verify or refute is **verified**, and the flag that
> does the work is a different one entirely.

Evidence, derived rather than asserted — `manage_only_env_readers()` in the D3
script scans every `.py` in the tree for an actual **read**
(`os.getenv` / `os.environ.get` / `os.environ[`) as opposed to a mention in a
comment, docstring or caveat string:

```json
{"env_var": "AAT_MANAGE_ONLY",
 "readers": [],
 "mentions_only": ["alpha/fleet.py:116", "scripts/agent_loop.py:87",
                   "tests_smoke_premarket_off.py:8"],
 "verdict": "INERT -- nothing reads it; setting it disarms nothing"}
```

The only switch that exists:
`alpha.fleet.Mandate.manage_only` → `fleet.loop_args()` → `--manage-only` in
`AAT_LOOP_ARGS` → `scripts.agent_loop`'s `args.manage_only`, which gates the
**entry** branch only (`agent_loop.py:420`) and logs the skip hourly
(`:413`) — exits, fills and marking keep running, which is the point.

**This is a guard that cannot go green being replaced by one that can.** The
scanner is a derivation, not a frozen sentence: the day somebody wires the
variable up, the receipt says `READ by N site(s); it is no longer inert`. It
also caught itself doing that on the first run — the scanner's own `read_rx`
source line matched `read_rx` and it reported "no longer inert", which is an
audit that had found *itself* and would have told a Tuesday operator the
variable works. The script now excludes its own file and the incident is
recorded in the code.

**hack2's disarm is real regardless**, because it comes from
`Mandate.manage_only=True`, not from the env var — confirmed in the D3 re-run
above.

---

## 4. What did not work, and what I did not do

1. **The four suites were NOT failing when I started.** The baseline run was
   `80 suites / 3,697 checks / ALL PASS`, on Labor Day, on a genuinely closed
   venue. The night lab's report of four red suites was accurate *for its own
   moment* (ET Sunday 13:34 = local Monday 01:34) and the condition is a
   **time-of-day** one, not a calendar one: it needs the local date to be ahead
   of the UTC date. So the row could not be proven by re-running it today, and I
   proved it by simulation instead — the 12,000-hour sweep, which shows the old
   formula colliding on 23.9% of hours and the new one on none. A green suite on
   the day is not evidence that a time-dependent bug is gone.
2. **`tests_smoke.py` was on the night lab's list of four and does not call
   `run_pass` at all.** Its 595 checks were green at baseline and are green now.
   Whatever took it down that night, it was not the two-clock defect, and I have
   no evidence about it. Reported, not diagnosed.
3. **The live Railway column of the D3 audit is CANNOT DETERMINE.** Reading it
   needs the `railway` CLI and the network, which this lane is not permitted to
   use. Carried forward and labelled, never refreshed silently. The fleet is
   redeployed today, so the ARMED/DISARMED column above is *what the deploy will
   set*, not what is running right now.
4. **The `alpha/fleet.py` citation fix is now embedded in a caveat the lead has
   since rewritten.** The corrected repo-qualified path survives inside the new
   text; if that caveat is edited again, check the path is still qualified.
5. **`alpha/psychohistory.py:62` hardcodes `state/causal_graph.jsonl`** and
   ignores `AAT_LEDGER_DIR`. Found while tracing the ledger growth above. It is
   not in `run_tests.py`'s `_PRODUCTION_LEDGERS`, so a suite writing it would not
   be caught. Reported, not fixed — out of this lane, and it needs a decision
   about whether that file is a ledger.
6. **The ET gates still read the local clock.** X1 makes the pass refuse on an
   untrustworthy clock; it does not make `in_opening_range` or
   `deadline_liquidation_due` correct under skew. C1-8 still measures all three
   misbehaving, deliberately, so the residual is visible rather than assumed
   closed. Re-deriving them against a real timezone database (`ET_OFFSET` is a
   fixed −4h and is wrong by an hour from the first Sunday in November) is a
   separate, larger job and is still open.
7. **The event-pendingness clock seam (§2 X3) is reported, not fixed.**
8. **X2 and X5-X9 and X11 are not this lane's** and were not touched. `X11` (the
   `taskkill` PreToolUse hook) is listed as "both repos" and belongs to whoever
   owns `.claude/settings.json`; nothing here changed it.
9. **Nothing was committed, pushed, deployed, sealed or ordered.** No git
   state-changing command was run. No LLM call was made; **$0**. Three writers
   were in this tree concurrently — the files this lane changed are listed below
   and none of them is the other agents'.

**Files the OTHER lanes changed and this lane did not touch or revert:**
`alpha/contract.py` (`HORIZON_REMAP`, incl. hack2's frozen terms),
`alpha/fleet.py` hack2 `manage_only=False` (the lead's, deliberate — my only
edit to that file is the repo-qualified citation string inside its caveat),
`scripts/agent_loop.py`, `scripts/run_pass.py`, `scripts/news_backfill.py`,
`scripts/window_universe.py`, `tests_smoke_contract.py`,
`tests_smoke_band_mode.py`, `tests_smoke_labor_exits_adversary.py`, and the new
`tests_smoke_premarket_off.py`, `tests_smoke_horizon_remap.py`,
`tests_smoke_news_pull.py`.

**Files changed by this lane:** `alpha/runner.py`, `alpha/refusal_classes.py`,
`alpha/fleet.py` (one string), `tests_fixtures.py` (new),
`tests_smoke_session_fixture.py` (new), `scripts/labor_d3_rearm_audit.py` (new),
`tests_smoke_equity.py`, `tests_smoke_pair.py`, `tests_smoke_entry_timing.py`,
`tests_smoke_labor_faults.py`, `tests_smoke_terminal_state.py`,
`tests_smoke_refusal_nav.py`, `docs/RUNBOOK_2026-09-08_REARM.md`,
`state/labor_day_lab_2026-09-07/{C1_fault_injection,D3_tuesday_rearm_audit}.json`
(both regenerated by their own producers).
