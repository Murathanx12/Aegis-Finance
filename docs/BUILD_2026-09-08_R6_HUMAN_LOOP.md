# BUILD 2026-09-08 — R6: THE HUMAN LOOP (H2 · T2/H4 · H5)

**Lane:** `ROADMAP_2026-09-07_TWO_MODES_AMENDMENT.md` §2 **H2**, **H4/T2**, **H5**.
**Licence:** `PRODUCT_EXPERIMENT`. **LLM spend: $0.00** — every model call in this
lane ran on the local Qwen2.5-7B through `free_inference.local_gguf`; DeepSeek was
never called and is refused *by name* in `decision_log.reflect`.
**No git state changed, nothing deployed, nothing sealed, no order placed.**

---

## RESULTS SCOREBOARD

| line | value |
|---|---|
| **RESULT IMPROVEMENT** | **NONE.** No book changed, no weight moved, no strategy was tested. This lane builds the *instrument* that will make the next result measurable. |
| product gap closed | Murat's own decisions are now **first-class typed data**: a conviction row becomes a `Thesis` with a falsifier, a catalyst, a horizon, a declared minimum hold and a loss budget; it opens a PENDING decision row; and that row is graded at **its own horizon** against **four** counterfactuals. None of this existed on 2026-09-07. |
| new actionable finding | the **hand-counted horizon in the first draft of the grader's own battery was wrong by one session** (2026-03-02 + 10 sessions is 2026-03-16, not 2026-03-13) and the battery caught it before anything shipped. That is the argument for a known-answer battery in one line. |
| second finding | `/api/journal/` returns **`gate.have = 0`**. There are zero graded rows, and there was no honest way to change that today (§7.1). The page says "a receipt, not a result" and shows no P&L. |
| third finding | H5's mirror shows the website **16 files, 2.45 MB** of the execution repo's 2.4 GB `state/` — seals, fills, refusals, 7 autopsies, 3 learning reports, the opportunity-recall ledger and 2 contracts. Before today the website could see **none** of it. |
| grader proof | **29/29 planted known-answer cases pass**, and a mutation test proves the battery can go red. |
| four counterfactuals, live | run against the **real** offline price panel: NVDA 2026-06-01, 42 sessions → 2026-07-31, **4/4 legs available**, all `conviction_prices_csv`. §4.3 |
| tests | **+130 new** (126 in four new files + 4 in the conviction bridge), all passing. Full suite **7,794 passed / 4 failed**, and none of the 4 is mine (§7). |
| `npx next build` | ✓ compiled in 5.8 s, TypeScript clean, `/journal` prerendered (32 routes). §5 |

---

## 1. H2 — THE JOURNAL → THESIS BRIDGE

### 1.1 The schema is the execution repo's, byte for byte

H2 says *reuse the existing schema verbatim, do not invent a second one*. Two
copies of a validation rule is how two repos start refusing different things
while both claim to enforce one contract, so `alpha/human.py` and
`alpha/brains/base.py` are **byte-identical copies** under
`backend/vendor/aat/alpha/`, loaded by path in
`backend/services/human_thesis.py`.

```
alpha/human.py        sha256 a338c9f1b32649b9c259a598cb96d929a600f116cf5591394a898454a8ba0857
alpha/brains/base.py  sha256 a72775c871125d74…
```

**Why a copy and not a `sys.path` insert into the execution repo:** binding the
name `alpha` to that repository would put `alpha.brains` — the package that owns
the broker client — one import away from a FastAPI request handler. The mirror is
therefore the *only* schema source at runtime, and
`test_human_thesis.py::TestSchemaIsVerbatim` hashes it against the execution repo
when that repo is on the machine and **SKIPS with a named reason** when it is not.
A skip is not a pass and the test says so in its skip message.

The two `__init__.py` files under the mirror are empty stubs rather than copies
(the real `alpha/brains/__init__.py` imports the whole brain fleet). That is the
one deliberate difference and it is **asserted** —
`test_the_brains_stub_imports_nothing` parses the file and requires zero import
nodes — rather than described in a comment.

`backend.vendor` is classified in `signal_reachability.CLASSIFIED` (it has no
static import edge, by construction).

### 1.2 The refusal cases

`HumanThesis` **subclasses** `Thesis`, so every parent rule runs first and
unchanged. All of these are exercised through the bridge and through the HTTP
endpoint, not assumed:

| # | input | refusal | why it matters |
|---|---|---|---|
| 1 | `stated_at >= catalyst_at` | *"a thesis recorded after its own catalyst is a memory"* | the only reason a prospective arm is worth anything |
| 2 | falsifier < 15 chars (0 and 14 both tested; 15 accepted) | *"what OBSERVATION would make this thesis wrong?"* | without it the row can be remembered, never graded |
| 3 | reason < 10 chars | *"state the reason; it is what gets distilled"* | |
| 4 | `direction` with no `expected_move` | *"up 2% against a 5.4% implied move argues for SELLING premium"* | direction alone cannot pick an instrument |
| 5 | `direction="up"`, `expected_move=-0.06` | sign disagreement | |
| 6 | `direction="none"`, `magnitude="unknown"` | *"not a thesis"* | |
| 7 | `conviction` outside (0, 1.5] | range | |
| **8** | **`horizon_sessions <= 0`** | *"a human decision graded at a fixed 5 days is graded against a clock it never agreed to"* | **new** |
| **9** | **`min_normal_hold_sessions` absent or negative** | *"it is what separates a sold-early exit from a decision"* | **new** |
| **10** | **`min_normal_hold_sessions > horizon_sessions`** | the row could never reach its own horizon without first being early | **new** |
| **11** | **`min_normal_hold_sessions == 0` outside `event_v1`** | *"admissible only under an EVENT budget (`event_v1`/hack2), where it is a declared choice"* | **new** — this is the default that emptied hack2 |
| **12** | **`loss_budget_ref` not in `config.LOSS_BUDGETS`** | invariant 19 | **new** |

Rule 11 has a matching **green** test (`test_zero_min_hold_is_ALLOWED_under_the_event_budget`)
because a gate that cannot go green is a broken gate, not a strict one.

### 1.3 The three added fields, and why exactly three

The fleet was remapped by horizon on 2026-09-08 (`contract.HORIZON_REMAP`): every
book now declares a horizon, a minimum normal hold and a loss budget. A human
decision must declare the same three or it cannot be graded the same way — which
is the entire content of invariant 18.

```
horizon_sessions          when the row RESOLVES (the grader uses this, not 5 days)
min_normal_hold_sessions  under which an exit is BOUGHT_SOLD_EARLY, not a decision
loss_budget_ref           → config.LOSS_BUDGETS: positions judged, expected losers
```

`config.LOSS_BUDGETS` carries the roadmap's F table as data:
`human_v1`→hack5 (20 judged / 8 expected losers), `event_v1`→hack2 (40/24),
`thesis_3m_v1`→hack3 (20/8), `thesis_6m_v1`→hack4 (15/6), `ensemble_v1`→hack6
(100/50). A default that was taken rather than declared is stamped
(`evidence.horizon_source = "config_default"` vs `"declared"`): a row that chose
21 sessions and a row that inherited 21 sessions are different facts, and a
calibration curve that cannot tell them apart is measuring two populations.

### 1.4 The pre-open prediction-book row — and what "sealed" means here

`human_thesis.book_entry()` emits a row shaped like the execution repo's own
`predictions[]` rows (schema **`prediction-book-3`**, read off
`state/predictions/2026-09-08.json` today), under
`generator = brain = "human:murat"`, carrying `horizon_sessions`,
`min_normal_hold_sessions`, `checkpoint_sessions`, `loss_budget_ref`, the
falsifier, the catalyst and its own `content_sha256`. The hash is verified by a
test that mutates a number and requires the hash to move.

**This lane does not seal, and that is deliberate, not an omission.** Sealing
writes into another repository's `state/predictions/<day>.json`; sealed receipts
are immutable; an agent session that appends to a sealed book is precisely the
tamper the seal exists to detect; and this session's operating rules forbid seals.
So `export_for_seal()` returns the row plus the attended command, and
`test_export_for_seal_does_not_seal` AST-scans that function to prove it makes no
write call at all. The finance-side record (`HUMAN_BOOK_LOG`) is append-only and
carries the same hash, so the human's seal is verifiable against a record that
already existed when it happens.

### 1.5 Wiring it to `POST /api/pi/conviction/decision`

The existing endpoint gained eight optional fields (`catalyst`,
`catalyst_at_utc`, `falsifier`, `direction`, `expected_move`, `horizon_sessions`,
`min_normal_hold_sessions`, `loss_budget_ref`). When any are present the
endpoint builds the thesis, records it, and opens a PENDING decision row; the
response gains a `thesis` block.

**They are optional rather than required, and that is a documented deviation from
a literal reading of H2.** The endpoint has live callers and an immutable table
behind it; breaking every existing journal write to enforce a new field is a
migration disguised as a feature. What is *not* optional is the honesty: a
decision logged without them comes back

```json
"thesis": {"status": "NOT_CREATED",
           "reason": "no catalyst, falsifier or direction was supplied, so this
                      row can be REMEMBERED and not GRADED …",
           "missing": ["catalyst", "catalyst_at_utc", "falsifier", "direction",
                       "expected_move"]}
```

so a row that cannot be graded says so at the moment it is written, rather than
six weeks later when somebody tries to grade it. The strict path is
`POST /api/journal/thesis`, which is 422 on every refusal in §1.2.

`_bridge_to_thesis` never raises: the immutable decision row is written *first*,
and losing it because a falsifier was 14 characters long would be the write path
punishing the honest half of the request. Pinned by
`test_an_immutable_decision_row_survives_a_refused_thesis`.

---

## 2. T2/H4 — THE DECISION LOG AND THE FOUR-COUNTERFACTUAL GRADER

### 2.1 Schema (`backend/services/decision_log.py`, `decision_log_v1`)

One row type for **both** authority levels (invariant 18). `mode` is *derived*
from the brain name, never declared, so a machine row cannot be filed as a human
one.

```jsonc
{
  "schema": "decision_log_v1", "version": "human_loop_v1/2026-09-08",
  "decision_id": "…16 hex…",             // sha256 over the row minus status/notes
  "source": "human:murat" | "engine:<book>",
  "mode": "A" | "B",                     // derived from `source`
  "symbol": "NVDA", "direction": "up|down|none", "action": "enter|add|trim|exit",
  "decided_at_utc": "…", "decision_day": "2026-06-01",
  "horizon_sessions": 63, "min_normal_hold_sessions": 21,
  "review_cadence_sessions": 21, "loss_budget_ref": "thesis_3m_v1",
  "entry_price": null, "shares_delta": null,
  "thesis_id": "…", "falsifier": "…",
  "engine_pick_symbol": null, "engine_pick_source": null,
  "observed": null, "ranked": null, "bought": null,   // TRI-STATE: null = UNKNOWN
  "exit_day": null, "exit_price": null,
  "status": "PENDING",
  "resolves_on": "2026-08-31", "reviews_on": "2026-07-01",
  "session_calendar": "XNYS",
  "learnable_at_utc": "2026-08-31T21:00:00+00:00",
  "learnable_basis": "the close of the resolving session (21:00 UTC ≈ 16:00 ET…)"
}
```

Storage is append-only JSONL under `backend/data/human_loop/` — **no database**
(CLAUDE.md), and the immutable `personal_decisions` table keeps owning the
conviction log. A re-grade appends; `load_grades()` keeps the newest per
`decision_id`.

### 2.2 The four counterfactuals

| leg | window | why this one |
|---|---|---|
| `held_to_horizon` | decision day → **the row's own** `horizon_sessions` | not a fixed 5 days. A 63-session thesis graded at 5 days is graded against a clock it never agreed to — the single default that made "sold early" and "wrong" indistinguishable |
| `held_to_next_review` | → `review_cadence_sessions` (≤ horizon, never longer) | separates *the thesis was wrong* from *the cadence was wrong*; different repairs |
| `engine_pick_same_day` | the engine's own pick, same day, same horizon | the only leg that compares the two authority levels **on identical information** |
| `spy` | the benchmark, same window | §3 |

`regret_vs_X = X − actual`; **positive regret means the counterfactual would have
been better**. A `down` thesis has its returns negated first (`sign = −1`), and
the benchmark leg is **never** flipped with the thesis. `sign` and `sign_basis`
travel on every graded row so the convention is checkable from the data.

`actual` is priced to a logged exit when one exists; with no exit the position is
treated as held and `actual_basis` says so — *"its regret is therefore exactly
0.0 by construction, not by luck."*

`fully_graded` requires **four** available legs, and only fully-graded rows count
toward the 20-row gate.

### 2.3 PENDING and the `as_of` gate

A row before its own horizon returns `status: "PENDING"` with `counterfactuals`
and `regret` both `null` — a state, not an error, and no numbers leak.

`lessons(as_of=…)` returns only rows whose `learnable_at_utc <= as_of` and reports
`n_withheld`. Asking for a **named** `decision_id` that had not resolved raises
`LessonNotYetLearnable` → **HTTP 425 Too Early**, because *"there is no lesson"*
and *"the lesson exists and you may not have seen it yet"* are opposite facts and
only one of them is a leak. `test_the_bulk_gate_counts_what_it_withheld` proves
the gate reads **each row's own** resolution date rather than being all-or-nothing.

### 2.4 The taxonomy — five states, not four

The four states H4 names are here verbatim, plus the two the execution repo's
`alpha/recall.py` already carries (receipt:
`backend/data/optimus/continuation_2026-09-06/B3_2_autopsy_and_opportunity_recall.json`
§`typed_misses`):

```
NOT_OBSERVED          never entered any AEGIS list      → repair: COVERAGE
GENERATED_NOT_RANKED  we had it, ranking missed it      → repair: the MODEL
RANKED_NOT_BOUGHT     ranked, no position               → repair: EXECUTION
BOUGHT_SOLD_EARLY     closed inside the declared min hold → repair: the EXIT RULE
CAPTURED              not a miss
UNCLASSIFIED          an input is UNKNOWN — a REFUSAL, not a class
```

`CAPTURED` is not optional: a taxonomy with no not-a-miss state types every
success as a failure. `UNCLASSIFIED` is the important one — `observed`, `ranked`
and `bought` are **tri-state**, and an unknown ranking refuses rather than
blaming the MODEL, which is the mistake the execution repo's ledger declined to
make on 2026-09-04 when a seal was missing.

### 2.5 The 2-4 sentence reflection, on the free path

`decision_log.reflect()` runs `free_inference` over
`config.DECISION_REFLECTION_BACKENDS = ("local_gguf", "nvidia_nim")` and
**raises** if a caller passes `deepseek`. Measured on this box, 2026-09-08:

```
backend    local_gguf (llama.cpp, Qwen2.5-7B-Instruct-Q4_K_M)
model      local
tokens     273 in / 77 out
latency    2.891 s
cost_usd   0.0        cost_class  free      paid_provider_used  false
sentences  3
text       "The decision to hold AAA up until 2026-03-16 earned a return of
            +21.00%, which matched the return of holding it until the horizon
            date. However, holding it until the next review date or following
            the engine's same-day pick would have resulted in lower returns,
            indicating that the decision process might not have been optimal."
```

The reply is **arithmetically correct and analytically wrong** in its last clause
(the alternatives were *worse*, which is an argument the process was fine). That
is the model, not the code, and it is exactly why the reflection is decorative by
design: it runs **after** the arithmetic is finished, a reply outside 2-4
sentences is refused rather than repaired, and a total refusal leaves the grade
untouched (`status: "REFUSED"`, `cost_usd: 0.0`). No reflection ever reaches a
size, a stop or an order.

---

## 3. THE SPY COUNTERFACTUAL — WHICH SOURCE ANSWERED

The `market` benchmark account **PA3I7VTCC0BM** (contract `PASSIVE_BETA_v1`)
holds SPY and **its keys are not in this `.env`**. The tempting shape is a helper
returning `0.0` when it cannot find a price — and `0.0` is indistinguishable from
"SPY was flat", which would make the benchmark leg free exactly when the data was
worst, in the direction that flatters the human.

So `backend/services/counterfactual_prices.py` has **no zero branch**. Every
answer carries a source; every failure raises `PriceUnavailable` with the list of
what it tried.

`config.COUNTERFACTUAL_PRICE_SOURCES`, tried in order (probe run 2026-09-08):

| source | available | detail |
|---|---|---|
| `terminal_state_mirror` | **false** | *"the H5 mirror does not sync marks"* — the whitelist covers seals/fills/refusals/autopsies/learning reports, not price marks. In the chain because a *planned* source and an *absent* one are different facts |
| `conviction_prices_csv` | **true** | `backend/data/conviction_prices.csv` — **197 sessions, 2025-10-27 → 2026-08-10, 67 columns including SPY, QQQ, IWM, XBI, SMH**. Offline, so the fast suite can grade |
| `yfinance_live` | `null` | network; refused inside the fast suite by `conftest`'s offline guard, which is correct. `null` = CANNOT DETERMINE, not `false` |

Every graded row carries `benchmark: {symbol, account, contract, keys_present: false, note}`
and a `price_sources` list. Three tests pin the behaviour: a missing benchmark
gives `ret: null`, `regret: null` and `fully_graded: false`; the module is
AST-scanned for `TradingClient` / `submit_order` / `get_account` and has none; and
a date past the end of the panel **refuses rather than carrying the last price
forward**.

Sessions are walked on the real **XNYS** calendar (`exchange_calendars`), stamped
`session_calendar: "XNYS"`; if the package were missing it falls back to weekday
arithmetic and stamps `WEEKDAY_APPROX`. A horizon spanning Thanksgiving is a
different horizon depending on which answered, so the stamp travels onto the row.

---

## 4. THE KNOWN-ANSWER RESULT

### 4.1 What it is

`backend/services/decision_log.py::known_answer_battery()` — a planted price
panel with hand-computable answers, run through the **real** `resolve()`. It is a
function rather than only a test so it is also a runnable receipt
(`python -m backend.services.decision_log`) and a live endpoint
(`GET /api/journal/known-answer`, which returns **500** if any case fails).

### 4.2 The result: 29/29

```
  [PASS] long/status              got='RESOLVED'
  [PASS] long/resolves_on         got='2026-03-16'
  [PASS] long/actual              got=0.21          want=0.21
  [PASS] long/held_to_horizon     got=0.21          want=0.21
  [PASS] long/held_to_next_review got=0.10          want=0.10
  [PASS] long/engine_pick         got=0.05          want=0.05
  [PASS] long/spy                 got=0.02          want=0.02
  [PASS] long/regret_horizon      got=0.0           want=0.0
  [PASS] long/regret_review       got=-0.11         want=-0.11
  [PASS] long/regret_spy          got=-0.19         want=-0.19
  [PASS] long/worst_regret        got='held_to_horizon'
  [PASS] long/fully_graded        got=True
  [PASS] long/taxonomy            got='CAPTURED'
  [PASS] short/actual             got=0.20          want=0.20     ← sign handling
  [PASS] short/raw                got=-0.20         want=-0.20
  [PASS] short/spy_not_flipped    got=0.02          want=0.02
  [PASS] short/mode               got='B'
  [PASS] pending/status           got='PENDING'
  [PASS] pending/no_numbers       got=None
  [PASS] no_spy/ret_is_none       got=None                        ← the 0.0 bug
  [PASS] no_spy/regret_is_none    got=None
  [PASS] no_spy/not_fully_graded  got=False
  [PASS] no_spy/source_named      got='NOT_AVAILABLE'
  [PASS] early/taxonomy           got='BOUGHT_SOLD_EARLY'
  [PASS] early/actual_unavailable_is_not_zero  got=None
  [PASS] no_pick/leg_unavailable  got=None
  [PASS] no_pick/not_fully_graded got=False
  [PASS] unknown/unclassified     got='UNCLASSIFIED'
  [PASS] unsourced/refused        got=True

29/29 known-answer cases pass
```

Every expected number is written in the source **beside its case**, before the
code runs — *"a battery whose expectations are read off the output is a
screenshot of a bug"* — and every case records **what it would catch**
(asserted: `len(catches) > 15`).

Three properties of the battery that make it worth having:

1. **It caught a real error before anything shipped.** The first panel used
   2026-03-06 and 2026-03-13 for the 5- and 10-session marks. 2026-03-02 is a
   Monday, so the correct marks are **2026-03-09 and 2026-03-16** — an off-by-one
   from counting the decision day itself. The battery went red; the panel was
   wrong, not the grader. That comment now sits above `_SYNTH_PANEL`.
2. **The battery can go red.** `test_the_battery_can_actually_fail` monkeypatches
   `_leg` to add 1% to every return and requires `all_pass is False`. Without it
   the 29 green lines are 29 lines of decoration (S47's exact failure).
3. **It plants the failure modes, not the happy path.** A missing benchmark, a
   missing engine pick, a short thesis, an early exit, an unknown ranking, an
   unsourced price, and a row asked one session too early.

### 4.3 The same grader on REAL prices

The battery uses an injected panel; this run uses the real offline source, no
network:

```
row      engine:demo · NVDA · up · decided 2026-06-01
         horizon 42 sessions, min hold 21, review 21, budget thesis_3m_v1
         engine pick AMD
resolves 2026-07-31   reviews 2026-07-01   calendar XNYS
status   RESOLVED   fully_graded True   sources ['conviction_prices_csv']

actual                    -10.42%
held_to_horizon           -10.42%   regret   0.00%
held_to_next_review       -11.83%   regret  -1.41%
engine_pick_same_day       -6.66%   regret  +3.76%
spy                        -1.26%   regret  +9.16%
worst_regret              spy (+9.16pp)      taxonomy CAPTURED
```

**4/4 legs available from a named source.** Nothing was persisted — this is a
demonstration of the price path, not a decision anyone made (§7.1).

---

## 5. H5 — THE TERMINAL-STATE READER, AND THE READ-ONLY PROOF

### 5.1 What it does

`backend/services/terminal_state_reader.py` copies a **whitelist** of artefacts
one way, out of `aegis-alpha-terminal/state/` into `backend/data/terminal_mirror/`.
Live run, 2026-09-08:

```
n_files 16   n_bytes 2,449,925   n_skipped 0
kinds  seals 1 · fills 1 · refusals 1 · autopsies 7 · learning_reports 3
       opportunity_recall 1 · contracts 2
```

`state/` is **2.4 GB**; the whitelist (`config.TERMINAL_MIRROR_ARTEFACTS`) is the
definition of what the website can see, and the receipt counts what it skipped.
Files over `TERMINAL_MIRROR_MAX_BYTES` (8 MB) are **tail-truncated** if
line-oriented and **skipped** if a single JSON blob — *"half a JSON document is
not a smaller JSON document"* — and the receipt says which happened per file.

**No HTTP layer was added to the terminal repo.** That is not tidiness: the
execution repo is the process that holds the broker client, and every port it
opens is a surface on that process. A one-directional file copy has no such
failure mode, because nothing over there is listening.

### 5.2 The proof it can never write back — three independent mechanisms

`backend/tests/test_terminal_state_reader.py::TestReadOnly`:

1. **The source tree is fingerprinted before and after a sync.**
   `test_the_source_tree_is_byte_identical_after_a_sync` builds a miniature
   `state/` (including a non-whitelisted `decisions.jsonl` and a log), hashes
   every file with SHA-256, runs the real `sync()`, and requires the file list,
   the sizes **and** the hashes to be identical — reporting added, removed and
   altered paths by name on failure. It also asserts the fixture planted
   something, so it cannot pass over an empty tree. **This is the assertion that
   fails if a future edit makes the module write upstream, and it depends on
   nobody remembering anything.**
2. **AST scan.** No `open()` in the module carries a write/append/`+` mode; no
   `unlink`/`rmdir`/`rmtree`/`replace`/`move`/`rename`/`chmod`/`truncate`/
   `system`/`popen` call exists; the module imports none of
   `alpha, alpaca, requests, httpx, urllib, subprocess, shutil, socket`. A
   further test walks every `write_bytes`/`write_text`/`mkdir` call and requires
   its receiver to be `dst`, `dst_root` or `p` — a *destination*, never anything
   derived from the source.
3. **Containment.** `_dest_for()` resolves the candidate path and refuses it
   unless it is inside the mirror root, so a `..` in an artefact name cannot walk
   back toward the source. Both the copy path and the read path are tested with a
   planted traversal, and a sync whose source and mirror resolve to the same
   directory is refused by name.

Plus: nothing outside the whitelist is copied (asserted on `decisions.jsonl` and
`loop_dev.log`); an absent artefact is a **named skip**, not a silent zero; a
missing execution repo **refuses** with `UNREACHABLE`; and an unbuilt mirror
reports `NEVER_SYNCED` with *"This is NOT an empty execution repo"* rather than
an empty list.

### 5.3 One open item

`backend/data/terminal_mirror/` is a **derived** artefact from another
repository, so I wrote a `.gitignore` inside it (`*`, `!.gitignore`) rather than
adding 2.4 MB of the execution repo's state to this repo's history. A container
therefore populates it by running
`python -m backend.services.terminal_state_reader --sync` at build/boot, or by
mounting a volume at that path. **That deployment step does not exist yet** and
is flagged in §7.

---

## 6. ENDPOINT SHAPES

`/api/journal/*`. Every response carries `version`, `licence: "PRODUCT_EXPERIMENT"`
and `authority`. Three routes write and they are the only three
(`test_only_three_routes_write` enumerates the router's own route table):
`POST /thesis`, `POST /resolve`, `POST /terminal-state/sync`.

| method + path | returns / codes |
|---|---|
| `GET /api/journal/` | the whole picture: `mode`, `brain`, `schema_provenance`, `loss_budgets`, `taxonomy`, `counterfactuals` (4), `benchmark` (with `keys_present: false`), `price_sources`, `scoreboard`, `terminal_mirror` |
| `GET /decisions?limit&source&status` | the log, newest first, human and machine in one list |
| `GET /grades?as_of&decision_id` | graded rows through the `as_of` gate. **425** when a named row was not yet learnable |
| `GET /scoreboard?as_of` | process metrics; `pnl: null` below the gate |
| `GET /gate` | `{rule, have, need, met, claim}` |
| `GET /known-answer` | the battery, run live. **500** if any planted case fails |
| `GET /taxonomy` | the five states + `UNCLASSIFIED`, with meanings |
| `GET /terminal-state` | H5 inventory. `OK` / `NEVER_SYNCED` / `SOURCE_UNREACHABLE` |
| `GET /terminal-state/{kind}/{name}` | one artefact. **422** unknown kind or traversal, **404** not in the mirror |
| `POST /thesis` | H2. **422** with the schema's own refusal text on every case in §1.2 |
| `POST /resolve` | grades every PENDING row whose own horizon arrived; `reflect` optional; returns `llm_cost_usd` |
| `POST /terminal-state/sync` | **503** when the execution repo is not reachable |

Today, live:

```json
{"version": "human_loop_v1/2026-09-08",
 "brain": "human:murat",
 "counterfactuals": ["held_to_horizon","held_to_next_review",
                     "engine_pick_same_day","spy"],
 "gate": {"rule": "no P&L claim under 20 graded rows with four counterfactuals each",
          "have": 0, "need": 20, "met": false},
 "claim": "a receipt, not a result",
 "terminal_mirror": {"status": "OK", "n_files": 16}}
```

### The page

`/journal` · `frontend/src/app/journal/page.tsx` · nav "Decision Journal" under
**Stocks**, beside Candidates, deliberately **not** `advancedOnly`.

The gate banner is the **first element on the page**: `0 of 20 graded rows — a
receipt, not a result`, and there is no P&L number anywhere on the screen below
the gate. Then process metrics (rows / pending / resolved / 4-leg, the taxonomy
histogram, per-leg counterfactual coverage), the price-source chain with the
`PA3I7VTCC0BM` caveat in amber, the H5 mirror card, the graded table (one column
per counterfactual, each cell showing the return, the regret **and the source
that answered**, with an unavailable leg rendering as an italic *n/a* with the
tooltip "This is NOT zero"), the pending table, the 29-case battery, and the loss
budgets.

`npx next build`: `✓ Compiled successfully in 5.8s`, `Finished TypeScript in
8.4s`, `/journal` prerendered, 32 routes, no type errors.

---

## 7. TESTS

Command: `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow" -q --timeout=300`

| file | tests | what it pins |
|---|---|---|
| `backend/tests/test_human_thesis.py` | **34** | the mirror is byte-identical; the loaded schema is the mirror, not the execution repo; the brains stub imports nothing; all 12 refusals; the green case for min-hold 0; the book row and its hash; `export_for_seal` writes nothing |
| `backend/tests/test_decision_log.py` | **48** | the 29-case battery case-by-case; that the battery can go red; four legs; own-horizon resolution; the `as_of` gate per row; every taxonomy state reachable; UNCLASSIFIED over a guess; the gate red **and** green; the reflection refuses DeepSeek by name |
| `backend/tests/test_terminal_state_reader.py` | **19** | the three read-only mechanisms; whitelist; truncation vs skip; NEVER_SYNCED ≠ empty |
| `backend/tests/test_journal_router.py` | **25** | endpoint shapes and codes (422/425/404); only three write routes; the benchmark caveat is in the payload |
| `…/test_conviction_decision.py` | **+4** | the bridge on the existing endpoint, including "the decision row survives a refused thesis" |
| **total new** | **130** | all passing |

Also updated: `test_guard_missing_input_contract.CASES` gained four entries
(`human_thesis`, `decision_log`, `counterfactual_prices`,
`terminal_state_reader`) — the enrolment test fails on a new guard that is not
enrolled, and it did; and `signal_reachability.CLASSIFIED` gained
`backend.vendor` with its reason.

**Full-suite result** (`-m "not slow"`, 2026-09-08, 1008 s):

```
4 failed, 7794 passed, 29 skipped, 124 deselected in 1008.41s (0:16:48)
```

The four failures are all in `backend/tests/test_r7_news_representation.py`
(the leak-gate verdict branch, the share-answered line, the diagnostic-arm
multiplicity family, the receipt's battery/arms split). **None of them is mine** —
that file belongs to the R7 news-representation lane and I did not touch it, its
module, or its receipt. Five agents were editing this tree throughout, so the
totals moved underneath the measurement; both numbers are reported as measured
rather than adjusted to look tidy. My four new files and the two amended ones
pass standalone and inside the full run.

### The reachability audit — `backend.vendor` (raised by two other lanes)

`test_signal_reachability::test_every_orphan_is_classified` was reported RED
naming `backend.vendor.aat.alpha.human`. It is **green now** (9 passed,
`audit()["unclassified"] == []`); the classification landed in
`signal_reachability.CLASSIFIED` during this lane and the other lanes were
reading the tree before that edit.

**It is CLASSIFIED rather than given a caller, and that is forced, not lazy.**
The mirrored file keeps its own `from alpha.brains.base import Forecast` line
byte-identical — that is what "verbatim" means — so it is importable only under
the top-level name `alpha`, and a static
`from backend.vendor.aat.alpha import human` would fail at import time. Editing
that line to satisfy the audit would break the single property H2 asked for.
Putting the execution repo on `sys.path` instead would bind `alpha` to the
package that owns the broker client, one import away from a request handler.

So the classification carries the reason, and two tests stop it from becoming an
excuse for dead code:

* `test_the_vendor_subtree_is_classified_by_name` — `backend.vendor`,
  `backend.vendor.aat.alpha.human` and `…brains.base` all resolve to a
  classification containing "VERBATIM", so a prefix rename fails here instead of
  turning the audit red for a future session to rediscover.
* `test_the_mirror_is_actually_LOADED_not_merely_present` — the half a
  classification cannot prove. `signal_reachability` can only say nothing
  *imports* it; this asserts the running service **did** import it by path
  (`sys.modules["alpha.human"]`), that `HumanThesis` inherits from *that* class,
  and that the file sits under `backend/vendor/`.

No other lane's modules were classified. `backend.strategy.*` belongs to the S
lane and was left alone.

---

## 8. WHAT DID NOT WORK, AND WHAT IS OPEN

1. **There are zero graded rows, and I did not manufacture any.** The tempting
   demo is to seed the journal with a few backdated decisions so the page has
   content. That would put **fabricated human decisions into the only labelled
   decision dataset this programme has** — the one asset nobody else can rebuild
   — and it is the same class of error as backfilled forward evidence. The page
   says so where the rows would be. The demonstration in §4.3 was computed and
   deliberately **not** persisted.
2. **`min_normal_hold_sessions` has no *measured* default.** 5 sessions for the
   human book is a config constant chosen to be non-zero, not a number anything
   estimated. It is stamped `config_default` on every row that takes it, so the
   two populations stay separable when there is enough data to ask.
3. **The mirror is not in the deploy path.** §5.3. `docker compose` will serve
   `NEVER_SYNCED` until somebody adds the `--sync` call or a volume mount. The
   surface reports that state honestly rather than as an empty execution repo,
   but it is a real gap and it is not fixed.
4. **`terminal_state_mirror` as a price source always refuses today** — the H5
   whitelist does not cover marks. Keeping it first in the chain is deliberate
   (a planned source and an absent one are different facts) but it means the
   chain's first link is currently decorative.
5. **The free model's reasoning is weak.** §2.5: correct arithmetic, an
   unsupported final clause. Local Qwen2.5-7B is adequate for turning a graded
   row into English and is not adequate for judgement, which is why the
   reflection runs after the arithmetic and reaches nothing.
6. **No H3 (the human book) and no F flip.** Those are attended and were out of
   scope. Nothing here arms an account.
7. **The `as_of` gate uses 21:00 UTC as the close** with no DST table. The error
   is one hour and it is on the late (safe) side; `learnable_basis` says so on
   every row.
8. **`engine_pick_symbol` is never populated automatically.** The leg exists,
   refuses correctly when absent, and is tested — but nothing yet reads the
   sealed book to fill it. That wire (`predictions/<day>.json` → `engine_pick`)
   is the highest-value next step in this lane, because it is the leg that
   eventually answers whether Mode B should be trusted.

---

## FILES

| file | change |
|---|---|
| `backend/vendor/__init__.py` | **new** — why the mirror exists and what differs |
| `backend/vendor/aat/alpha/human.py` | **new** — byte-identical copy of the execution repo's `Thesis` |
| `backend/vendor/aat/alpha/brains/base.py` | **new** — byte-identical copy of `Forecast` |
| `backend/vendor/aat/alpha/{__init__,brains/__init__}.py` | **new** — empty stubs (asserted empty) |
| `backend/services/human_thesis.py` | **new** — H2 bridge, `HumanThesis`, book row, append-only log |
| `backend/services/decision_log.py` | **new** — rows, the four-counterfactual grader, taxonomy, `as_of` gate, scoreboard, reflection, the 29-case battery |
| `backend/services/counterfactual_prices.py` | **new** — named price sources, session arithmetic, no zero branch |
| `backend/services/terminal_state_reader.py` | **new** — H5 one-way mirror |
| `backend/routers/journal.py` | **new** — 13 routes, 3 of them writes |
| `backend/config.py` | +32 constants in one appended block |
| `backend/main.py` | import + `include_router(journal.router)` |
| `backend/routers/portfolio_intelligence.py` | +8 optional fields and `_bridge_to_thesis` on the conviction endpoint |
| `backend/services/signal_reachability.py` | +1 `CLASSIFIED` entry (`backend.vendor`) |
| `backend/tests/test_human_thesis.py` · `test_decision_log.py` · `test_terminal_state_reader.py` · `test_journal_router.py` | **new** — 124 tests |
| `backend/tests/test_guard_missing_input_contract.py` | +4 enrolled guards |
| `backend/tests/portfolio_intelligence/test_conviction_decision.py` | +4 bridge tests |
| `frontend/src/app/journal/page.tsx` | **new** — the page |
| `frontend/src/lib/api.ts` | +types and five fetchers, appended |
| `frontend/src/components/sidebar.tsx` | +1 nav item |
| `backend/data/terminal_mirror/.gitignore` | **new** — the mirror is derived, not committed |

No git state was changed; the lead session owns commits.
