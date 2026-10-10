# Real-source decision trace, 2026-10-10

**PRODUCT_EXPERIMENT; actual consumers executed; news-to-forecast remains
NOT READ BY DESIGN.** Five already stored SEC EX-99 sources, 97 known trailing
analyst revision events, three ablations, and 45 expected-return cells were
inspected without an API/model/browser call. No consumer or policy flag changed.
No paper activation, order, fill, return claim, or new research claim results.

Runner: `ft_lab/budgeted_decision_trace.py`, isolated behind the existing ft_lab
import firewall. Local artifacts:
`backend/data/optimus/local_pc/budgeted_20261010/trace/reviewed-final/`.
`sources.json` retains original publication/first-seen stamps, source URLs,
raw-body/excerpt hashes, exact spans and offsets, entities, selected numbers,
reporting versus unknown action dates, uncertainty, mechanism interpretations,
contradictions, and actual consumer horizons 5/21/63 sessions. The annotations are frozen
manual source inspections, **not successful local-model extractions**. The
existing cascade source validator and p3 constraint-receipt code execute.

| Source | Mechanism inspected | Date treatment |
|---|---|---|
| ACN, SEC filing October 1 | reported EPS/bookings | explicit report day October 1; fiscal period is not an event day |
| SNOW, first seen October 3 | proposed convertible financing | September 28 reporting day; proposed issuance has no confirmed issue day |
| MGNI, first seen October 8 | loan repricing / approximate savings | October 7 reporting day; exact completion day unknown |
| LEVI, first seen October 8 | raised EPS outlook / weaker DTC | October 7 report day; company outlook and negative analyst flow coexist |
| CACC, first seen September 19 | mixed entered/will-enter consent judgments | September 17 reporting day; settlement day rejected |

The cutoff is `2026-10-10T00:00:00+00:00`. The analyst input has 395,948 stored
rows; unknown/future `first_seen_utc` and future event dates are excluded before
the existing 90-day, strictly-before-asof rule executes. The complete known
cross-section determines ranks; it is not re-ranked over the five examples.
`analyst_sources.json` retains the 97 selected source events and original
first-seen, event, pulled-at, firm, prior/current target, and `pit_safe` fields.
This retrospective yfinance history is receipt-time descriptive context, not
proof that its older events were available historically.

`expected_return.build`, `sim_run.u_plan`, and `pc_broker.plan_orders` execute
unchanged. Only broker I/O is replaced with stored inputs: a **limited** sanitized
October 9 21:07:51 UTC account snapshot (equity, cash, count, positions) and
stored prior closes. Account identifiers and credentials are excluded. Default
consumer stores are redirected to the artifact directory before imports;
explicit runtime inputs are read-only, enforced by a process audit guard.
Socket access, child processes, order submission, venue-clock and broker-order
queries fail loud. The planner uses `research` mode. No live policy flags are
modified. The empty PROBE shortlist and absent isolated contract are explicit
abstentions, recorded in the actual consumer receipts.

| Variant | h21 expected return / relative to universe median | Isolated virtual book | Sent |
|---|---|---|---|
| full | ACN +0.09383%; SNOW +0.37903%; MGNI/LEVI 0; CACC unknown | SNOW/ACN 10% each + existing-policy SPY core 18.00223% | 0 |
| without news | identical to full | identical to full | 0 |
| without analyst | all five unknown | existing no-E[r] fallback inventories all five at 10% each + same SPY core | 0 |

ACN is revision-flow rank 45 (17 net raises, 16 firms); SNOW rank 3 (47, 33);
MGNI rank 138 (11, 9); LEVI rank 1575 (-6, 9); CACC has only one acting firm
and fails the three-firm floor. Zero at lower ranks is the existing measured-table
consumer rule, not a failed fetch replacement. Unknown ablation cells remain
null. Removing analysts changes forecast inputs and virtual selection; it does
not establish that the full book is better. The stored calibration sweep is
survivor-selected direction context and supplies no new alpha certification.
The virtual inventory fallback is the existing planner behavior; it is not an
authorized fallback trade. All variants are non-acting.

The full/without-news equality is an acceptance **limitation**, not news impact:
`expected_return.NOT_READ_BY_DESIGN['source:']` explicitly excludes source facts.
No unsupported source probability is fabricated to make that boundary look
connected. The trace licenses source-to-analyst-to-forecast consumer inspection;
it does not claim a completed news-to-forecast decision pipeline.

`actual_failed_reply_rejection.json` rejects the **actual stored p3 CACC raw
reply** that asserted `event_date: 2026-09-17`. Its raw hash, original excerpt
hash and prompt version are retained. Public candidate spans are rechecked
against the pinned raw SEC article. The bounded source-inspected date contract
then rejects the operative day: “announced today that it has entered or will
enter into consent judgments” dates reporting and leaves the settlement mixed.
No model reply is repaired or promoted. `settlement_date_rejection.json` is a
separate explicit regression witness, labeled as such. The parked p4 module was
inspected only; it was not imported or copied.

Run from this worktree in a fresh Python process:

```powershell
python -m ft_lab.budgeted_decision_trace --runtime-root <runtime-ledger> --out <fresh-scoped-trace-directory> --failed-reply-checkpoint <stored-private-checkpoint>
python -m pytest ft_lab/tests/test_budgeted_decision_trace.py -q
```

Full `ft_lab/tests` after relocation: **81 passed in 10.41s**, using the project
`.venv` with dotenv loading disabled and `AEGIS_PERSONAL_MODE=0`. Its unchanged
AST import firewall passed. The six trace tests cover actual failed-reply rejection and hash
binding, mixed settlement timing, source drift, future first-seen rejection,
canonical span offsets, scoped output refusal and null preservation. The actual
batch also ran again using `reviewed-final/frozen_runtime` and `reviewed-final/failed_reply_input.json`
as inputs, writing `trace/reviewed-reproduced`: **all three forecast decompositions and
virtual books matched exactly**. Wall-clock stamps and artifact paths are not
part of that semantic comparison. The frozen mirror retains only the selected
news rows, complete revision parquet, existing sweep, sanitized snapshot, and
required filtered price rows; it permits reproduction without runtime access.
The existing planner's **without_analyst decision-story replay reports MISMATCH
(every leave-one-out NOT_SEPARABLE)**. That distinct consumer failure is retained
in `consumer_decision_story_lines` and `consumer_decision_story_mismatches` in
`trace.json`; it is not repaired or overturned by the runner's successful frozen
forecast/book reproduction. Consumer replay acceptance remains incomplete.
The earlier `final`/`reproduced` artifacts remain preserved as pre-review evidence.
No live verification is claimed.
