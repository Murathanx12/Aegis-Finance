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
| **`farm_breadth_phase_2013_2024.json`** | **THE CANDIDATE.** k crossed with the rebalance phase at h=5, every cell benched against its own nulls | `docs/FINDING_2026-08-24_HOLDING_PERIOD.md` |
| **`farm_phase_measured_delist.json`** | holding period crossed with phase, MEASURED delisting returns from `crsp.dsedelist` | same |
| `farm_holding_2013_2024.json` | 516 policies, phase 0, six holding periods x net/frictionless | same |
| `farm_delisting_2013_2024.json` | the delisting FALLBACK swept 0.0 / -0.30 / -1.0 — now moves the answer only 1.09x, which is the proof the join works | same |
| `farm_breadth_2013_2024.json` | k = 3..50 x two sizings. **STALE LEVELS** — predates the delisting join; only its ordering was cited | same |

**Read the two phase-crossed files first.** The others are history and are kept
BECAUSE they are wrong in instructive ways: `farm_holding_*` is one phase per
rule (phase alone is worth up to 3.75x), and `farm_breadth_*` is one phase per k
— which crowned k=50 when the phase-crossed run shows the optimum is k=10. The
corrections are the finding, not an embarrassment to tidy away.

**The rule this directory exists to enforce:** a farm number read off ONE
rebalance phase is a draw, not a result. Four separate readings were overturned
that way in one night.

Every row carries `n_delist_measured` / `n_delist_assumed`. A run that fell back
on most of its exits still has an assumption for a headline, and the receipt has
to be able to say so.
