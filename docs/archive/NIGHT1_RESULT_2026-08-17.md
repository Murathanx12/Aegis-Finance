# Night 1 ran. `status ok`. And the timing model was wrong twice, in opposite directions.

**2026-08-17.** Launched 17:44:51 local from `b4c64e2`, one attempt, unattended
under the criteria written before the numbers were visible
(`NIGHT1_UNATTENDED_GO_CRITERIA_2026-08-17.md`). Finished 19:58 local.

```
  trial            INTERNET-INVESTIGATOR-FWD-1
  status           ok          void_reason  (none)
  sandbox          False       decision_ts  2026-08-17T05:44:52-04:00
  cells            40 tickers x 5 arms = 200 chains
  calls            1417        spend        $0.919725
  records          585 written to predictions.jsonl
  truncation       0 of 200 cells, per-arm rate 0.0 across all five, spread 0.0
  dropped_cells    0
  decision lag     18.2 min at start (limit 45), 133.6 min at end
  elapsed          115.4 min, finished 11:58Z against a 13:30Z bell
```

Spend came in at **$0.92 against a $12.00 safety ceiling** and a $1.428/night
planning average — 62 fundable nights against the 40 required.

---

## THE FINDING: two wrong numbers that nearly cancelled

The receipt's own timing block:

```
  projected_minutes            69.6        (arm_concurrency 5, efficiency 2.0 DECLARED)
  actual_minutes              115.4
  n_calls_projected             960
  actual calls                 1417        (+47.6%)
  measured_efficiency          3.529       vs declared 2.0
```

**Both inputs to the projection were wrong, and they pointed opposite ways.**

* **Calls per cell was under-estimated by ~48%.** `MEASURED_CALLS_PER_CELL =
  4.8`; the night ran **7.09**. The readiness report's *"1000 calls (upper
  bound)"* was exceeded by 42% — it was an estimate wearing the word *bound*.
* **Concurrency efficiency was under-declared by 76%.** Declared 2.0, measured
  **3.529** — the first time this constant has ever been measured rather than
  asserted.

The second error rescued the first. Had efficiency been the declared 2.0 at the
actual call volume, the night phase would have run **~204 minutes** instead of
115 — finishing about **13:26Z against a 13:30Z open. Four minutes.**

That is the house failure mode with the stakes attached: *correct arithmetic
against the wrong world*, twice, netting out to a comfortable-looking 91.5
minutes of headroom that was never the margin anyone thought it was.

**What saved the run was not the projection.** It was Order 11's rule — validate
the guard on the pessimistic branch. The pre-launch check was run at
`arm_concurrency=1`, projecting 139 minutes; the runner actually executes
`cells_sequential_arms_concurrent` at concurrency 5. The conservative bound
(139) sat above the truth (115.4) while the runner's own optimistic projection
(69.6) sat far below it. **A verdict taken on the pessimistic branch held; the
branch the caller actually supplies did not.**

### What follows, and it is not "raise the constant"

Both constants should be re-derived from this receipt — `MEASURED_CALLS_PER_CELL`
to ~7.1 and `DECLARED_CONCURRENCY_EFFICIENCY` to the measured 3.529. But the
deeper repair is that **`arm_concurrency` is still a caller-supplied number that
nobody derives from the runner**, and the receipt proves the runner's value (5)
and the guard's validated value (1) can differ by five-fold without anything
noticing. The guard should read the runner's execution mode, or refuse.

Not done tonight: no source edit on the critical path, and the night is the
critical path until the receipt is safe.

## The one cell that failed, and why it cost more than one cell

```
  ERROR investigator_agent: [B_tools/ICE] investigation failed
    investigator_agent.py:444   args = dict(call.get("args") or {})
    ValueError: dictionary update sequence element #0 has length 3; 2 is required
```

A model-emitted tool call whose `args` was not a mapping, trusted straight into
`dict()`. It killed one cell of 200.

But the pairing key is `night × ticker × observable × horizon × threshold`, and
each cell carries three forecasts — so losing `B_tools/ICE` dropped **three
paired cells from every other arm too**:

```
  n_cells_union 120   paired 117   dropped_unpaired 3
  B_tools 117 cells (0 dropped)  ·  every other arm 120 cells (3 dropped each)
```

**That is the matched design working exactly as intended** — an unpaired cell is
discarded rather than allowed to unbalance the contrast — and it is also the
reason a 0.5% cell failure costs 2.5% of the comparison. Worth noting that the
bug can *only* strike tool-using arms, so it is a bias with a direction rather
than noise; at one occurrence it moves nothing, at scale it would make tools
look worse for a reason unrelated to the hypothesis.

## Telemetry warnings, all pointing the same way

```
  llm_telemetry: 2 unreadable ledger line(s) — spend and yield are LOWER BOUNDS
  llm_telemetry: duplicate call_id 9d894c33f4851abc — later row ignored
  llm_telemetry: duplicate call_id 76a99e31295fd94a — later row ignored
```

All three **understate** spend, which is the dangerous direction for a ceiling —
a gate binds only on what it can read. Immaterial tonight at $0.92 against
$12.00, but the ceiling's protection is weaker than it appears and that should
not be discovered on a night that needs it.

## Data-quality notes

* **The universe carries dead tickers.** `PXD` (acquired by ExxonMobil, 2024)
  and `SQ` (Block renamed to XYZ, 2025) are still in `config.stock_universe`;
  `MMC` also 404'd despite trading normally, which looks transient. 4 of 182
  excluded, 178 eligible, and the pool still filled 40/40 — so it cost nothing
  tonight, and it is silent shrinkage that will not announce itself later.
* 5 of 200 chains minted nothing; 31 calls landed in barren chains.
* `chain_yield` and `truncation` are both clean — zero truncated cells, zero
  spread across arms, which is the result the token-ceiling guard exists to
  produce.

## Prod verified on `1fb34ef` — and the night's evidence is NOT in prod's ledger

Pushed 60 + 6 at 20:05; CI green; commit flipped at **20:20**; the changed
surface exercised live for content rather than status codes.

```
  GET  /api/risk-layer/evidence   confirmation "UNREACHABLE — permanently
                                  screen-grade", k_eff 1.41, provenance
                                  NOT_SELECTED_BY_LITERATURE, six claims with
                                  their established flags (2 true / 4 false)
  POST /api/risk-layer/exposure   weight 1.0 capped at realised_vol 13.92%,
                                  12 decision-log rows, N24 bound
                                  NOT_DEMONSTRATED (ucb 2.93 vs 2.42),
                                  top-level keys exactly the checked six
  canaries                        nav.all_fresh true, scheduler 7/7 ok
```

The first POST returned an **empty body at a 30s timeout on a cold container**
and answers fully at 120s. Not a failure — but worth recording before someone
reads that timeout as a broken endpoint.

**The finding that matters.** Prod warns:

> `ledger migration: /app/backend/data/optimus/predictions.jsonl holds 20546
> record(s) absent from the persisted ledger at /data/optimus/predictions.jsonl
> — NOT copied (the persisted ledger is authoritative once non-empty)`

The count moved by **exactly 585**, which is Night 1. The repo file deploys to
`/app/…`; the authoritative ledger is the persisted volume at `/data/…`. So
**the night's forecasts are safe in git and are not in the production resolution
path** — they would not be resolved even if the resolver were awake, and it is
not (`prediction_ledger DEGRADED, 25 overdue, 0 resolved`). Two separate
problems that compound, neither caused by this push, and both now on the
post-night list ahead of the Railway work.

## What was deliberately NOT done

* **No campaign `--commit`. No `LIVE_FORWARD` quarantine.** Reserved as attended
  operations in every order since 8; "run the night" is not authorisation for
  them.
* **H1 not read.**
* No source edit on the critical path, before or during.
* No retry — there was nothing to retry, but the rule stood.
