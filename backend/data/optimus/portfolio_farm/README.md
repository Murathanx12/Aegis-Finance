# portfolio_farm receipts

One JSON per run: every policy, every metric, every null draw, the panel window
and the policy count. **A headline number belongs in a receipt, never in prose
alone** — so anything quoted from the farm in a doc must be traceable to a file
here.

Committed files are the ones a document CITES. Exploratory runs are local
artefacts and are deleted rather than archived: a receipt produced by an
instrument later found wrong is worse than no receipt, because it is quotable.
`farm_signals_2018_2020.json` was deleted for exactly that reason — it predated
the second (low-turnover) null, so its "beats its own null" column was mostly a
statement about turnover.

| file | what it answers | cited by |
|---|---|---|
| `farm_holding_2013_2024.json` | 516 policies, phase 0, six holding periods x net/frictionless | `docs/FINDING_2026-08-24_HOLDING_PERIOD.md` |
| `farm_phase_2013_2024.json` | the same rules at every rebalance PHASE — the medians that superseded the single-phase table | same |
| `farm_breadth_2013_2024.json` | k = 3..50 x two sizings, each benched against its own nulls | same |

**Read `farm_phase_*` before quoting `farm_holding_*`.** The holding receipt is
one phase per rule, and at k=12 the phase alone moves terminal wealth 1.8x-3.8x.
Its rows are draws, not results.
