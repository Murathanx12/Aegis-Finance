# TEACHER-LIBRARY-1 / COPY-LAB — design and status

**Status 2026-08-14: substrate built, TWO sources live end to end on real SEC
data (Form 4 and Schedule 13D/G), 22 events in the ledger. No lane seeded. No
hypothesis evaluated. $0.00 spent.**

Roadmap: `ROADMAP_BRAIN_V3_2026-08-14.md` Track E.

---

## Three things that share a data source and are not the same thing

| | what it is | may run before proof? | may be cited as evidence? |
|---|---|---|---|
| **COPY-LAB** | forward experimental **paper** portfolios | **yes** | **never** |
| **TEACHER-LIBRARY** | research substrate: canonical events, actor behaviour, mechanisms | no — pre-registration first | only after Aegis grades it |
| **WORLD MODEL** | teacher events as *one* information class among many | n/a | outcomes are the label, teachers are features |

The separation is the point. The product needs things the research has not
blessed yet, and a paper lane is the honest way to hold that tension: aggressive
exploration, strict promotion.

**Aggressive exploration, strict promotion.** A weak prior result is not a
reason to refuse to look. It is a reason to refuse to *claim*.

---

## The question

Not *"does Pelosi / a fund / an insider / Cramer make money?"* but:

> Which **actors**, **actions**, **domains**, **contexts**, **market states** and
> **disclosure lags** contain useful information; how much of it remains
> **copyable after public disclosure**; and does the mechanism **transfer** to
> securities the original actor never traded?

The last clause is the breakthrough target. If Aegis learns the mechanism well
enough, it finds the opportunity *before* the teacher discloses it, and the
teacher becomes a scientific instrument rather than someone to follow.

---

## `public_at` — the rule everything rests on

`public_at` is the earliest moment Aegis could legally and technically have
observed the information. It is the **only** timestamp a copy strategy or a
backtest may enter on.

`transaction_at` is stored separately and is **never** a signal timestamp.

This is not a legal posture. A backtest entering at the transaction date
measures a portfolio nobody could have held — it is a fantasy wearing a paper
account's clothes. And keeping *both* timestamps is what makes the interesting
question askable at all:

```
disclosure_lag   = public_at − transaction_at
actor edge       = what happened after transaction_at
public copy edge = what happened after public_at
lagged copy edge = what remained at public_at + 1, 2, 5, 10, 20 sessions
transfer edge    = does the mechanism work on OTHER securities?
```

The gap between the second and third is the whole **COPYABILITY-GAP** family. A
schema keeping one timestamp cannot measure it.

**Measured so far, from real filings:** Form 4 lag median **0 days**, max **1
day** (Section 16 allows two business days). Senate PTRs may legally arrive up
to **45 days** late. Those two lanes will not resemble each other, and measuring
why is the product question.

---

## What is built (`backend/services/teacher_library/`)

### `events.py` — the canonical event

Every source maps into one `TeacherEvent`. Actor taxonomy is **precise**: a
politician is `POLITICIAN`, never `CORPORATE_INSIDER` — that term has a
statutory meaning (Section 16 officers, directors, >10% holders) and using it
loosely would put a legal claim into the database as a category label.

Status vocabulary, shared with the tool layer, the feature layer and the Form 4
fetcher: `OK_DATA` · `OK_EMPTY` · `UNAVAILABLE` · `PARSE_ERROR` ·
`IDENTITY_AMBIGUOUS` · `SECURITY_MAPPING_AMBIGUOUS` · `LATE_FILING` ·
`OTHER_EXPLICIT_FAILURE`. **Source unavailable is never encoded as zero
activity.**

Rows that are refused rather than coerced:

- a usable event with no `public_at` — it cannot be traded and must not pretend;
- a transaction dated **after** its own disclosure — a date-parse error wearing
  a plausible mask, which would otherwise produce a negative lag that reads as
  prescience;
- inverted amount ranges; unknown actor or action types.

Identity is **SHA-256**, not `hash()` — Python salts string hashing per process,
so the same filing would get a new identity every run and dedup would silently
stop working.

### `ledger.py` — the point-in-time ledger

Append-only, deduplicated, amendment-aware.

`events_asof(as_of)` takes the cutoff **positionally** and filters on
`public_at`. There is deliberately **no** give-me-everything convenience
wrapper: a leak that comes from a default argument is invisible in review,
because the call site looks like ordinary code. `all_events()` exists for
counting, is named to be conspicuous in a diff, and says in its own docstring
that it must not feed a backtest.

Amendments do not overwrite parents. The original genuinely *was* what the world
saw; a reader standing before the correction sees the original, exactly as a
copy strategy would have. Rewriting in place would make yesterday's backtest
irreproducible and delete the "this actor amends often" signal.

`coverage()` counts non-usable rows **on purpose** — a source that is FAILING
must not read as a source that is QUIET.

### `adapters.py` — one interface, many sources

Adapters fetch, parse and emit events. They do not score, do not join outcomes
and do not decide what is interesting. A failed fetch emits a **status row**,
not silence: emitting nothing on failure is how a broken feed becomes a quiet
week.

`Form4Adapter` is live and **reuses** `insider_form4`, which already owns the
SEC rate limiter, the User-Agent, the 403 retry and the XML parser. A second
insider parser would be a second thing to keep correct.

### `adapters_13dg.py` — Schedule 13D / 13G, the second source

Its own adapter rather than a flag, because **13D declares intent to influence
or control** (five business days to file since 2023) and **13G is the passive
twin**. Collapsing them would average an activist's declaration with an index
fund crossing a threshold mechanically — two different things that happen to
share a percentage.

The actor is the **filer**, not the issuer. The regex anchors on `FILED BY:`,
because the issuer appears *first* in EDGAR's header and a naive match would
attribute every 13G to the company it was filed against, silently swapping actor
and subject.

Two limits flagged rather than papered over: `actor_type` is inferred from the
**form**, not the filer's nature (a 13G filer can be an individual); and EDGAR
does not say which filing a `/A` amends, so `is_amendment` is set while
`amends_event_id` stays None — the safe direction, since the ledger only
supersedes when the link is present.

Live, on real data:

```
SC 13G/A  VANGUARD GROUP INC   accepted 2024-03-11T13:59:07
SC 13G/A  BlackRock Inc.       accepted 2024-03-07T17:29:52
SC 13G/A  VANGUARD GROUP INC   accepted 2024-02-13T21:55:49
```

That last one is the argument for acceptance timestamps in a single line:
**21:55 UTC is 16:55 ET, after the close.** A backtest treating it as same-day
tradable information would help itself to most of a session it never had.

---

## The end-to-end demonstration (real SEC data, $0.00)

```
13 events · OK_DATA 5 · OK_EMPTY 6 · UNAVAILABLE 2

PFE  BOURLA ALBERT       38,000 sh   txn 2026-08-12 → public 2026-08-12
PFE  BLAYLOCK RONALD E   39,231 sh   txn 2026-08-05 → public 2026-08-05
PFE  Buckley Mortimer J  37,632 sh   txn 2026-08-05 → public 2026-08-05
F    THORNTON JOHN L     10,600 sh   txn 2026-06-23 → public 2026-06-24
CLF  Camara Edilson      19,700 sh   txn 2026-02-13 → public 2026-02-13
```

**The point-in-time read, demonstrated rather than asserted:** as of
`2026-06-23` only CLF is visible. The Ford purchase transacted *that day* and
was disclosed the next, so it is correctly invisible — precisely the leak the
ledger exists to prevent.

**The positive control mattered as much as the hits.** The first ingest — five
mega-caps — returned `OK_EMPTY` five times, which is exactly what a subtly
broken fetch looks like. Treated as a failure until proven otherwise: 12 filings
examined per ticker, 0 unfetchable, CIK map loaded with 10,387 tickers, and a
second sweep across names where insider buying is common returned real
purchases. Mega-cap insiders simply do not buy on the open market; they receive
grants and sell.

**The tri-state earned itself on its first real run.** MPW, WBA and X returned
`ticker_not_in_cik_map`. Under the previous code those three were
*indistinguishable* from "no insider buying at this company".

**Observed and deliberately not evaluated:** PFE shows three distinct insiders
buying within a week, one of them the CEO. That is the raw material for the
cluster-buy hypothesis. Whether it predicts anything is a pre-registered
question and this work does not touch it.

---

## Prerequisite closed: the Form 4 source contract

`fetch_open_market_buys()` returned one identical zero-buy shape for a missing
CIK, a failed submissions fetch, and a genuinely quiet six months. Now
tri-state.

And underneath it, the worse one: `_ticker_cik_map` was `@lru_cache(maxsize=1)`
and returned `{}` on failure, so **one transient SEC 403 cached an empty map for
the life of the process** — every ticker afterwards reporting a confident
`0.0 — "No open-market insider purchases"` until redeploy. It never raised. It
ran green. Only a non-empty map is cached now.

The subtle status is `empty_but_unverified`: filings present in the window, none
readable, zero purchases found. **An absence we did not fully look for is not an
absence.**

---

## What is NOT done

- **No lane seeded.** `backend/data/copy_lab/teacher_copy_lanes.yaml` is
  seed-ready and marked `SPEC_ONLY_NOT_SEEDED`. Seeding is attended via
  `seed-a-lane`; Murat flips the flag. The file is deliberately **separate from
  `paper_portfolios.yaml`**, which is baked into the config hash the live track
  record's integrity depends on.
- **No hypothesis evaluated.** No outcome join, no IC, no signal evaluation
  anywhere in this package. The moment a number could grade a hypothesis,
  `pre-register-trial` comes first.
- **The live predecessors are untouched.** `TRIAL-CONGRESS-IC` (decision
  2027-01-11), `TRIAL-INSIDER-IC` / `TRIAL-CMP-INSIDER-IC` (2027-07-21) and
  `TRIAL-ARK-IC` are accruing forward. TL-1 extends them; it must never
  re-register them or read their clocks early.
- **Adapters not yet built:** House/Senate PTR, 13F, N-PORT, ARK, public
  recommendation feeds. (13D/13G is now built — see above.)

---

## Next, in order

1. **SEC bulk Form 3/4/5** (2006–2026, free). Per-insider history is what turns
   `CORPORATE_INSIDER_OPPORTUNISTIC` from `ready: false` to buildable —
   actor-relative surprise needs a history, and it must use only outcomes
   already resolved before the event being described.
2. ~~**13D/13G**~~ — **BUILT 2026-08-14.** Next for this family: bulk
   historical 13D/G rather than the per-issuer submissions feed, and parsing the
   filing body for stake size and declared purpose, which the header does not
   carry.
3. **House/Senate PTR.** The 45-day window is the interesting part, not an
   obstacle to it.
4. **Matched-control machinery** (`ORDER H`) before any hypothesis: same sector,
   cap, beta, momentum, volatility, liquidity, recent drawdown, event proximity.
   Plus the nulls — shuffled actor labels, shuffled timestamps within valid
   blocks, disclosure-lag perturbation, and the 13F-popularity corpse.

**Nothing in step 1–3 evaluates anything.** They are ingestion. Step 4 is the
gate that has to exist before step 5 is even proposed.

---

## Standing constraints

- `public_at` only, for anything called copyable.
- Teachers are **features and weak labels**, never training targets. Supervised
  targets remain realised outcomes: residual return, absolute return, realised
  volatility, covariance, drawdown, event response.
- Masking trio binds on any historical-LLM arm — `NAMED` /
  `PERSISTENT_ANON` / `EVENT_ANON`; the arm difference **is** the leakage
  measurement. Names alone are not enough: a famous event is identifiable from
  context.
- The LLM proposes mechanisms. **Aegis grades them.** A convincing story is not
  evidence.
- No success-story library without a failure library (`ORDER M`): for every
  apparently successful teacher action, matched actions by the same actor,
  behaviour, company type and market state that **failed**.
- Paid normalizers (Quiver, Capitol Trades) are an attended purchase decision
  taken only after the free Tier-1 build measures the gap they would close.
