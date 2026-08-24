# SESSION 2026-08-24 (night) — the farm, the two fixes, and the cost truth

**Read with** `docs/FINDING_2026-08-24_HOLDING_PERIOD.md` (the result) and
`docs/SESSION_2026-08-24_WHAT_IS_LEFT.md` (the handoff this session inherited).

---

## RESULTS SCOREBOARD

The format Murat's review asked every session to lead with, from now on.

| | |
|---|---|
| **Best historical net strategy** | `mom_12_1 / hold 5d / k=10 / inverse_vol / u500`, **$77,002 median across 5 rebalance phases** (worst $58,411), from $10,000, 2013-2024, 12 bps round trip, next-open fills, MEASURED delisting returns |
| **vs market** | CRSP VW buy & hold **$38,960** — **~2x on terminal wealth in every phase**, and **WORSE on Sharpe (0.61 vs 0.72), Sortino and Calmar in every phase**, at -60% drawdown vs -34%. Under terminal wealth it wins; under any risk-adjusted objective it loses. Name the objective. |
| **Phase spread** | **1.8x-3.8x** at k=12 — wider than any gap between the strategies compared. Every result is now a MEDIAN over rebalance phases |
| **Best forward paper strategy** | unchanged: `conservative-atr` +6.38% since 2026-06-08 (77 days). No new forward book was launched. |
| **Independent alpha selectors running** | **still 1** (`arena_composite`). The BLOCKER to a second one was removed today, not the second one itself. |
| **Portfolio-farm candidates tested** | **~1,600** policies over 3,020 sessions x 6,894 PERMNOs (holding, breadth, phase, delisting, breadth x phase) |
| **Promoted** | **0** — a CANDIDATE now exists and promotion is attended, so nothing was promoted unilaterally |
| **New actionable mechanism** | **one candidate**, plus a mechanism worth naming: **12-1 momentum systematically selects acquisition targets** — which is why the delisting convention mattered so much |
| **External execution drag** | not measured this session (no external order submitted) |
| **LLM spend** | **$0.00 this session.** No LLM call was made by this work |
| **LLM cost per useful decision** | n/a |

### RESULT IMPROVEMENT: A CANDIDATE, NOT AN EDGE.

Nothing was promoted and no forward book was launched, so the demonstrated
forward edge is unchanged. What exists now that did not this morning is a
**candidate**: the first policy in this programme to beat a properly-costed
benchmark on a replay with next-open fills, measured delisting returns and both
nulls cleared at 100.0/100.0.

It is not an edge. It is post-hoc, one window, one path, ~1,200 policies tried,
and it loses to the market on every risk-adjusted measure. What earns it the
word "candidate" is that it survived three instrument corrections that each
moved the answer more than the answer itself:

1. **Phase.** The number first published — `mom_12_1/h63` at $38,815 — was the
   MAXIMUM of a rebalance-phase distribution whose median is $16,633.
2. **The delisting assumption.** A declared -30% for every exit was worth an
   **18x** swing that straddled the benchmark.
3. **The delisting DATA was already on disk.** `crsp__dsedelist.parquet`, in the
   WRDS bulk pull, unjoined. I had written "the top data task is a WRDS pull"
   into the handoff before looking. Joining it collapsed the sensitivity from
   18x to **1.09x** — which is the proof the join worked — and moved the leader
   from $35,228 to $80,943.

I built a number, then built the thing that showed the number was a draw, then
found the data that showed the correction itself rested on a guess. Every farm
number in the repository now carries its phase spread and its
measured-vs-assumed delisting split.

---

## 1. The two correctness fixes the review asked for FIRST

### 1a. The independent selector could not actually be loaded

Confirmed exactly as reported, and it was two defects, not one:

* `selection_signal` was absent from `spec.CONSUMED_BOOK_KEYS`, so `load_specs()`
  raised `SpecError` on any file that used it — the identity layer supported a
  book the loader refused;
* `BookSpec.selection_signal` read the FILE defaults, so even past (1) the
  engine would have ranked the new book by `arena_composite` while its
  fingerprint claimed a different selector. **Identity and execution
  disagreeing is worse than the refusal.**

A third, latent: the two resolvers disagreed on their fallback —
`book_selection_signal` fell back to `arena_composite`, `BookSpec` to
`multifactor_score`. Production declares the key, so it never fired. Both now
read one constant, `DEFAULT_SELECTION_SIGNAL`.

`backend/tests/test_independent_selector_end_to_end.py` — 10 tests, and the
rule of the file is the one the review named: **write a real YAML to disk, call
the real `load_specs()`, push the spec through the real `engine._select`.** The
two score sets in the fixture are INVERTED, so ranking by the wrong one is a
visibly wrong answer rather than a plausible one. The existing identity test
missed both defects because it built a dict and called `book_fingerprint()`
directly — a route that never runs the loader.

**All ten live book fingerprints are byte-identical** (existing test, re-run).
No arena YAML was touched.

### 1b. The language contract was half a contract

The AST test proved every direct call site applied `pin()`. It did not prove any
of them checked what came BACK: six of seven passed the model's reply straight
through, and only `llm_analyzer` called `refuse()`. A pin is a REQUEST, and a
model that ignores it is the exact failure being guarded.

`llm_language.guard(provider, purpose, text)` is now the one return-path
validator — it returns `""` on refusal, which lands in the nothing-came-back
branch every caller already has. Wired into `architecture_arena`, `llm_swarm`,
`optimus_specialists`, `leakage_probe`, and `copilot` (which, being the one
HUMAN-consumed path, shows a sentence instead of a blank box).
`why_moved` remains DEFERRED with its dated reason — `pi_why_moved` fires
17:15 ET **tonight** and editing it hours beforehand is risk with no upside.

`test_llm_language_contract.py` now enumerates the return path as its own
parametrised test, so the two halves can never again be conflated.

---

## 2. The cost discrepancy — audited, and the answer is boring in a good way

Murat: the IIF receipt says `$0.941/night`, the account loses ~`$3/day`.

**Built:** `backend/services/deepseek_balance.py` (DeepSeek's own
`GET /user/balance`, snapshotted to an append-only ledger) and
`python -m scripts.llm_cost_audit`, which prints one line:
`provider_balance_delta - telemetry_total = unaccounted`.

**Measured, 2026-08-24 ~20:15 HKT:**

```
balance now       : $23.99      (the vendor's number, first ever snapshot)
balance at start  : $57.12      (2026-08-15, hand-typed constant)
provider says     : $33.13 spent over 9 days  = $3.68/day
telemetry says    : $4.63       (local ledger, 0 unpriced calls)
UNACCOUNTED       : $28.50
```

**Both numbers were right and they count different populations.** IIF-1 is
$0.92/night — the five nights are $0.9197 / $0.9185 / $0.9023 / $0.9304 /
$0.941, remarkably stable — and it is one of several DeepSeek consumers on one
key. The rest is production (Railway writes its own telemetry file on its own
volume, unreadable from here) plus attended local research. Nothing was
mispriced: **the internal price table already matches DeepSeek's published V4
Flash rates** ($0.14 / $0.0028 cached / $0.28), and `extract_usage`'s
DeepSeek-vs-Anthropic cache normalisation is correct.

Two instrument defects were found and fixed on the way:

* the audit's first version counted **7,083 `row_type: "amendment"` rows** — zero
  token bookkeeping entries — as "unpriced calls" and stamped the whole total a
  LOWER BOUND. It reported a $28 hole and a fake reason for it in one breath.
  Filtered by `row_type`, the local ledger has **zero** unpriced calls;
* `deepseek_balance` stamped snapshots at second, then microsecond, resolution.
  Windows advances `datetime.now()` in ~15.6 ms ticks, so two reads inside one
  tick collided on the KEY `spend_between` looks rows up by — and a real spend
  computed as **$0.00**, the exact "the night was free" misreport the module
  exists to end. The stamp is now monotonic by construction. Caught by the test
  before it ever ran against a night.

**Still open, and it needs a decision, not a session:** $28.50 over 9 days is
unattributed because production's telemetry is not readable from here. Either
expose a spend summary on `/api/health/full`, or run the audit on Railway. Until
then no number may be called "programme-wide spend".

---

## 3. CHUNK A — `PORTFOLIO_FARM` + `ASOF_REPLAY`, built and run

`backend/services/portfolio_farm/` — 6 modules, 4 test files, ~90 tests.

* `panel.py` — CRSP daily 1990-2024 into aligned (date x permno) matrices.
  **Found and refused:** only **2013-2024** carry `openprc`/`retx`/`shrout`. The
  earlier pull has price and return only, which means no next-open fill
  convention, no dividend/price separation, and no market cap. The loader now
  names the missing columns and the replayable window instead of dying inside
  pyarrow. Widening it is a WRDS re-pull, not a code change.
* `signals.py` — 16 signals, each with a readable per-date SPECIFICATION and a
  vectorised whole-grid EXECUTABLE, plus a test asserting they agree at sampled
  rows. Two implementations is two places to be wrong; the bridge is cheaper
  than trusting the clever one.
* `policy.py` — the frozen, hashed strategy record. **Zero costs is a
  constructor REFUSAL** unless `zero_cost_diagnostic=True` is declared, and the
  flag travels into `policy_id` and onto every leaderboard row.
* `replay.py` — decide at close, fill at next open; share counts not weights;
  dividends as cash; per-trade costs; formation-time liquidity screen on
  trailing data; failed fills when there is no open price; an explicit,
  variable delisting assumption.
* `metrics.py` / `farm.py` — terminal wealth FIRST, then the ratios; nulls
  attached to the leaderboard rather than filtered off it.

**Performance:** 516 policies over 12 years of CRSP in ~7 minutes on this box.
That is the force multiplier the review asked for — the arena learns one
strategy per calendar day; this learns hundreds per coffee.

### PIT is enforced structurally and PROVEN, not asserted

`test_portfolio_farm_pit.py` plants a name whose price path is engineered so a
peeking engine would compound +5% per session on it, and asserts terminal
wealth does not explode. Plus a calibration test that plants an actual forward
index and asserts the detector fires — a gate that cannot fail on a real
violation is decoration.

### Three real bugs the tests caught before any number was quoted

1. **The single-name cap silently stopped applying.** Cap-then-renormalise, run
   three times, converges to 1/n — so 3 names under a 20% cap came back at 33%
   each, over the cap the receipt claimed to enforce, with nothing raised. Now:
   water-filling when feasible, cap-and-hold-cash when not.
2. **Twenty-one "independent" null draws were twenty-one copies of seed 0.** The
   frictionless twins were rebuilt field-by-field and dropped `signal_seed`.
   Visible in the first leaderboard as twenty-one identical $43,068 rows.
3. **`liquid` the signal and the universe screen disagreed** about how many
   observations make a dollar-volume mean — admitting names the signal could
   not rank.

### And one instrument defect that changed the conclusion

The first leaderboard had ONE null (`random`, re-drawn every formation date) and
momentum sat at the 100th percentile of it at every holding period. That was
mostly turnover: `random` at `hold=1` turns over 492x/yr and pays 29.5%/yr in
costs, against momentum's 45x and 2.7%. So `random_persistent` was added — one
fixed random basket, near-zero turnover — and **the bar is now the 90th
percentile of BOTH.** `reversal_1m` at `hold=1` clears the churning null (100.0)
and fails the persistent one (5.0), which is exactly the distinction one null
hid.

---

## 4. What was NOT done, and why

* **No arena YAML was touched**, and `EVENT_RESPONSE_v1` was not launched. The
  review's own instruction was to let tonight's `pi_options_pit` /
  `pi_why_moved` / `pi_arena_daily` fire on the current config first. The
  loader defect that BLOCKED an independent book is fixed; launching one is the
  next session's first act, after the migration gate is confirmed.
* **`why_moved` still has no return-path guard.** Deferred with a dated reason
  until after tonight's 17:15 ET run.
* **No delisting sensitivity run** (0.0 / -1.0). One command, not yet spent.
* **The `breadth` preset has not been run**, and it is now the most interesting
  one — see the finding's last section.
