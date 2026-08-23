# ADJUDICATION — 2026-08-24: the external review of the profit-first turn

**An external review is ADJUDICATED, not imported.** (Standing lesson, arc
2026-08-17→20.) A reviewer without repository access reasons from what the code
appears to do. Some of that is right, some is right for the wrong reason, and
some is wrong — and the difference is only findable by running the thing. Every
claim below was checked against the code or the data before it was accepted,
rejected, or amended.

Reviewed: the profit-first session (`a363e2f`..`264b1c2`), actor intelligence,
the event store, the arena, the paper-broker path, the forecast-population
registry, and the older neural relative-value work.

---

## 1. Verdicts on the four claimed defects

| # | Claim | Verdict | Where |
|---|---|---|---|
| 1 | Arena → Alpaca execution is temporally misaligned | **CONFIRMED, and worse than stated** | §2 |
| 2 | The event taxonomy is dropped in the arena adapter | **CONFIRMED** | §3 |
| 3 | Event dedup contradicts its own specification | **CONFIRMED** | §4 |
| 4 | Acceptance time is not as immutable as the comments claim | **CONFIRMED** | §5 |
| 5 | Unknown IBES `anntims` falls through to hour 0 | **CONFIRMED but inert; a DIFFERENT defect was live** | §6 |

All five are fixed in this session. A sixth defect, which the review could not
have seen from the outside, was found while fixing the first — §2.

---

## 2. The execution clock — confirmed, and the lag was two sessions

The review reconstructed the timeline from the outside and got it right. The
measured version is worse:

```
Mon 17:45   arena decides BUY X, queues it for the next open
Tue 09:30   the internal book's declared fill
Tue 17:45   the arena pass RECORDS that fill; X is now a settled position
Wed 16:30   the Alpaca sync (inside _daily_check) first SEES X, submits it
Thu 09:30   the external account actually gets X
```

Two sessions, not one, because the sync read *settled* positions and a position
does not settle until the pass **after** the one that decided it. The external
account was therefore not validating the arena's strategy; it was validating a
two-session-delayed variant, and every execution number measured against it
would have been a number about the delay.

**Fixed as the review proposed — intent mirroring, not position mirroring.**

* `paper_broker_targets.intent()` returns the book's holdings **after** its
  queued orders fill, with `basis="intent"` and `decided_for=<decision date>`.
  A lane reports `basis="settled"`, which is what it always did.
* The submit moved **into the 17:45 arena pass** (`_submit_arena_broker_intent`),
  immediately after the decision that produced the intent. A market day order
  submitted after the close queues for the next open — the same open the
  internal book fills at.
* `_daily_check` (16:30) now mirrors **lane targets only** and logs why when the
  declared target is an arena book.
* Submissions are persisted (`alpaca:equity:arena:<BOOK>:submissions`) with the
  basis and the open they were meant for, so a later study can pair the external
  fill with the internal synthetic one instead of assuming they match.

Deliberately **not** done: a separate pre-open submit job. A second schedule
would drift out of step with the pass that produces the intent, and "submitted
for an open the book did not decide for" is exactly the failure being fixed.

### 2.1 The sixth defect: credentials and state could come from different accounts

Not visible from outside the repo. `alpaca_mirror._request` called `_keys()`
with **no argument**, so every HTTP call resolved the **env-declared** target's
credentials — while the caller may have been reading a **different** target's
state. So:

```python
sync_alpaca_mirror(target=arena_book)   # env unset
```

read the arena book's positions and traded the **mirror lane's account**. That
is precisely the outcome `paper_broker_targets.credentials` exists to refuse,
reached by walking around it: the refusal only fires for a *non-legacy* target,
and the legacy target was the one being resolved.

The target is now threaded through `_request` and every helper that calls it,
and a test asserts that an explicit arena target with no arena keys refuses
rather than borrowing the lane's.

---

## 3. The event taxonomy — confirmed

`event_intel` emits `event_type`. `arena/events._norm_event` read `category`,
which no producer has ever emitted. The LLM has been shown `category: null` on
every event since event context shipped.

Nothing failed, which is exactly why it survived: **a renamed key with no
adapter is silent by construction.** The frozen snapshot was well-formed, the
prompt was well-formed, and the single most useful field the perception layer
produces was empty in all of them.

Fixed, with `category` kept as an alias so nothing that reads it breaks — and
with the contract pinned end-to-end rather than commented:

```
event_intel.event_type  →  arena _norm_event  →  event_store record
```

Three tests, one per hop, plus one that fails if the producer ever grows its own
`category` key (at which point the alias is ambiguous and the contract needs
re-deciding, not re-aliasing).

`_norm_event` also dropped `direction_basis` and flattened the provenance dict
into `source`; both are now carried, with `publisher` and `url` separate.

---

## 4. Event identity — confirmed, split as proposed, with one part rejected

`content_hash` included `source.url`, so two outlets carrying one story were two
events — while the function's own docstring promised they would collide. The
1.0.0 test for this passed because both of its fixtures used the same default
URL, which is the one case syndication never produces.

Split as the review proposed:

* `canonical_hash` = scope + event_type + normalised title → the **event**.
  Novelty is measured against this.
* `observation_hash` = canonical + feed + publisher + url → the **sighting**.

`content_hash` remains as an alias of `canonical_hash`, so existing readers keep
working.

**Rejected: the "approximate source time bucket" in the canonical hash.** A
bucket splits a story that crosses midnight into two events, and the thing it
would protect against — an annual filing with an identical title — is already
handled by the 30-day novelty window. The review's own reasoning for the window
argues against the bucket.

**Timing.** The store is `ABSENT` in production and empty on disk: zero records
exist under either scheme. Changing identity later would have meant a 30-day
window in which every old-scheme hash failed to match and everything reported
`NEW`. This was the last cheap moment.

---

## 5. Acceptance time — confirmed, three clocks, one function declined

The docstring said `accepted_at` "is stamped here, from the wall clock, never
taken from the payload". `make_record` took it as a parameter, and
`arena/events.fetch` passed the frozen snapshot's `as_of_ts` into it. **The
comment was the guard, and a comment is not a guard.**

On a live pass the two clocks coincide, so nothing looked wrong. On a replay the
simulated past would have back-dated every event into decisions that never saw
it — lookahead arriving through the timestamp rather than the data, which is the
one failure mode this module was written to prevent.

Schema 1.1.0 carries three clocks with three jobs:

| field | meaning | used for availability |
|---|---|---|
| `source_timestamp` | what the publisher says | **never** |
| `ingested_at` | when this system took delivery | **only this** |
| `decision_asof` | the decision clock the collection served | never |

A supplied `ingested_at` is stamped `ingest_clock: "supplied"` — a backfilled
record can no longer pass as a live one — and a **future** value is refused
outright. The arena now passes `decision_asof` and lets the store stamp its own
clock.

**Rejected: `available_to_replay`.** Answering "what could a decision on
2026-03-01 have known?" requires a claim this store cannot make — that the
corpus was *complete* on that date. It was not; it began accruing in August
2026. A function that answered anyway would be correct arithmetic against the
wrong world. The docstring says so instead of the code pretending otherwise.

---

## 6. IBES announcement times — the claim was right, the defect was elsewhere

The review's mechanism is exactly right: `.astype(str).fillna("00:00:00")` fills
nothing (`astype(str)` has already turned a missing stamp into `"NaT"`), the
hour coerces to `0`, and hour 0 reads as pre-market — same-session tradable.

**Measured before fixing: 0 rows in the corpus window are unreadable.** The
guard never fired because it never had to. Fixing it changes nothing today and
prevents a silent lookahead if the vendor's coverage ever changes.

**What WAS live is one layer down.** 3,168 US rows carry *exactly* `00:00:00`.
That is not a time anyone announces at:

* the rest of hour 0 spreads across the minute field (00:16, 00:17, 00:02 …)
  the way real stamps do, while exact midnight is a spike;
* its share falls monotonically from **5.5% of 2013 to 0.1% of 2024** — the
  signature of a legacy default being retired, not of analysts publishing at
  midnight.

Read as a time it means pre-market, so an after-close release was graded from a
price that may have preceded it. Both cases now take the next session. **1,234
claims moved by one session; the corpus row count is identical.**

**The actor result is unchanged.** The same seven analysts are licensed for
INVERSE with the same holdout deficits to three decimals; edges move in the
fourth. Recorded anyway: a PIT fix that turns out to change nothing is still
worth the receipt, because the alternative is discovering later that nobody
knows whether it mattered.

The same defect and the same fix apply to `scripts/g4_collect_earnings.py`
(807 rows, 0.13%).

### 6.1 Found while re-running: the persistence headline was a filtered subset

`corr(train edge, holdout edge) = 0.516, n = 50` is the number the entire actor
layer rests on. It was computed ad hoc and written into prose — **it existed in
no artefact**, so it could not be re-checked after any change without deriving
it by hand.

It is now in `score_receipt.json`. Re-deriving it surfaced that "n = 50" was 50
of **222** analysts, selected by an unnamed rule: a minimum of 30 graded claims
in the holdout. Unrestricted, the same split gives **0.25**.

| min holdout claims | n | corr | 95% CI |
|---|---|---|---|
| 0 (all) | 222 | **0.253** | [0.125, 0.372] |
| 10 | 171 | 0.329 | [0.188, 0.457] |
| 20 | 105 | 0.400 | [0.226, 0.550] |
| 30 | 50 | **0.513** | [0.273, 0.692] |
| 40 | 20 | 0.453 | [0.014, 0.746] |
| 50 | 10 | 0.739 | [0.205, 0.934] |

**Every rung excludes zero. The premise holds; only its magnitude depended on a
threshold nobody had named.** The ladder is monotone in holdout evidence, which
is the signature of attenuation — an analyst whose holdout edge rests on six
calls contributes a very noisy `y`. It is not selection on the outcome: the
filter is on holdout *precision*, never holdout *result*. The honest headline is
now the unrestricted **0.25**, with better-measured subsets suggesting higher.

---

## 7. The central architectural claim: ten books are not ten brains

**Accepted, and it is the most valuable thing in the review.**

Nine of the ten arena books (now nine, after `PROFIT_ALLOCATOR_v1` retired) run
`selection: composite_top_k` over `arena_composite`. They differ in sizing,
concentration, screens, LLM tilts and winner handling — **portfolio treatment**
— while sharing one **alpha source**, itself a hand-weighted blend in which
12-1 momentum carries 99.5% of the coverage (measured 2026-08-20:
`coverage_histogram {"1": 206, "6": 1}`).

So the arena has been running a well-instrumented experiment on how to *hold*
one signal, and calling it a competition between strategies. That is why the
demonstrated edge is 0% and why more guardrails were never going to move it.

**What follows:** the next capability is not another 0.5-weight factor in
`arena_composite`. It is **independent selectors** — mechanisms whose errors are
not the same errors — added as separate `PRODUCT_EXPERIMENT` books, never folded
into the composite. A learned router over them is only interesting once they
exist and have produced independent outputs, so `META_ROUTER_v1` comes after,
not first.

Sequenced in `docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`.

---

## 8. The LLM's job: structured economic state, not one scalar

**Accepted in direction; the shape already exists and is too thin.**

`event_intel` already does the right thing architecturally — the LLM classifies
into **enums only** (`event_type`, `direction`, `direction_basis`), never a
number the model made up. What it produces is too narrow to learn from: a type,
a sign, and a basis.

The extension is to widen the *structured* output (materiality, novelty,
guidance/demand/margin deltas, affected entities, expected information
half-life, thesis breakers) and keep the payoff mapping in numeric models. The
constraint that must survive the widening: **every field the LLM emits is either
an enum or a named entity, never a return forecast**, and every field earns its
own reliability estimate before anything conditions on it. An LLM that is 94%
right about event type and 51% right about direction is two different
forecasters wearing one name.

Deferred until the diffusion/response work needs a field, so that each new field
arrives with a consumer rather than as a bigger prompt.

---

## 9. The >100k rule, amended by scope

**Accepted.** The standing rule deferred neural learned representations until
100k graded experiences existed. Amended:

* **Still binds** for a neural representation of the arena's *episodic memory* —
  that corpus really is thin, and a learned embedding of 300 experiences would
  be a picture of noise.
* **Does NOT bind** supervised neural models on purpose-built historical
  datasets that already exist.

With one condition the review understated and this project has already paid for:
`NEURAL-RELATIVE-VALUE-1`'s 72,495 pairwise labels come from **145 date
blocks**. Under CANON §58, `n_effective` counts **date blocks**, so the honest n
is 145 — not 72,495, and not "72,495 with a caveat". Every split is by date
block, and the planted-detectability gate (`detectability_gate.assert_detectable`)
applies before any result from it counts.

---

## 10. Rejected, deferred, or amended

| Proposal | Ruling |
|---|---|
| Source time bucket in the canonical event hash | **Rejected** — §4 |
| `available_to_replay()` | **Rejected** — §5; the store cannot claim corpus completeness |
| GNN (MDGNN / ECHO-GL style) | **Deferred**, as the review itself proposes: only after simple graph-propagation features beat a non-graph baseline |
| The 15-test list, run as a list | **Rejected as a plan.** Scored by `P(changes the roadmap) × value − cost`, three survive as next work; the rest are logged, not queued. A list of fifteen good ideas executed at 1/15 depth is how five months produced 0% |
| Targeted `optionm.opprcd` pull for an options-expectation surface | **Amended, and it is cheaper than proposed.** The consumer is right; the source is wrong. `optionm.stdopd` — standardized options at fixed maturities and deltas, carrying `impl_volatility`, `delta`, `vega` — is the surface, and **1996 is already on disk** (6.7M rows). ATM IV, term structure, 25Δ skew and risk reversals all derive from it. `opprcd` (4.31B rows) is contract-level: needed for open interest, volume and max pain, none of which the first version requires. **Pull the `stdopd` family; `opprcd` stays deferred.** |
| "Ten brains" as an immediate build of five | **Amended to three**, in dependency order — §7 |

---

## 11. What the review got wrong

Nothing materially, which is worth saying plainly. Two calibration notes:

1. **"Event memory 7/10 — correct architecture, but implementation problems."**
   The implementation problems were real and are fixed. The architecture score
   understates one thing: the store was `ABSENT` in production, so it had never
   written a record. A design with no data is not 7/10 of anything yet.
2. **The IBES timestamp call was right in mechanism and wrong in impact** (§6):
   the named case had zero occurrences, and the case with 3,168 occurrences was
   not named. Reasoning from code alone finds the shape of a bug; only the data
   says whether it fired.

---

*Fixes in this session's commits. Sequencing in
`docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`.*
