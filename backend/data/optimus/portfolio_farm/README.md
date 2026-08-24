# portfolio_farm receipts

> **EVERY DOLLAR FIGURE BELOW PREDATES THE 2026-08-25 SPLIT-ADJUSTMENT FIX.**
> The panel marked SHARE COUNTS at raw prices, so every corporate action was
> booked as a return (`backend/tests/test_portfolio_farm_split_adjustment.py`).
> Net it cost the leading policy ~0.3%/yr — but it re-ordered the signal grid,
> moving `liquid` from t=0.26 to t=2.55. Re-measured on the same policy and
> window: terminal median 77,002 -> **85,482**, 2013-2018 1.01x -> **1.00x**,
> 2019-2024 1.75x -> **2.07x**. The one-regime conclusion is stronger, not
> weaker. These receipts are kept because they are the record of what was
> believed and why; the delta is the interesting part.
>
> **THREE QUESTIONS NOW COME BEFORE A LEADERBOARD**, and none of the files
> below answers any of them:
>
> | | |
> |---|---|
> | could the sample resolve anything? | `portfolio_farm_signal_power` — **zero of thirteen** non-null signals on 2013-2024; White's reality check p=0.358; the null 5-95 band is ten points wide |
> | does the edge survive breadth? | `portfolio_farm_breadth_power` — Grinold says t should RISE with k; every signal FALLS and peaks at the narrowest book |
> | what did it actually buy? | `portfolio_farm_concentration` — the best row on the board (`liquid`) is a FAANG list |
>
> **The replayable window is 1993-2024** after the re-pull. Panels longer than
> ~15 years need `--reduce`. The farm now also carries its first NON-PRICE
> signals (`value_bm`, `profit_roe`) — the previous thirteen were thirteen
> transformations of `crsp.dsf`.

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
| **`farm_subperiod_candidate.json`** | **READ FIRST.** The candidate in each half of the window: **1.01x the market over 2013-2018**, 1.75x over 2019-2024. One regime. | `docs/FINDING_2026-08-24_HOLDING_PERIOD.md` |
| **`farm_breadth_phase_2013_2024.json`** | the candidate, and breadth crossed with phase. k crossed with the rebalance phase at h=5, every cell benched against its own nulls | `docs/FINDING_2026-08-24_HOLDING_PERIOD.md` |
| **`farm_phase_measured_delist.json`** | holding period crossed with phase, MEASURED delisting returns from `crsp.dsedelist` | same |
| `farm_holding_2013_2024.json` | 516 policies, phase 0, six holding periods x net/frictionless | same |
| `farm_delisting_2013_2024.json` | the delisting FALLBACK swept 0.0 / -0.30 / -1.0 — now moves the answer only 1.09x, which is the proof the join works | same |
| `farm_breadth_2013_2024.json` | k = 3..50 x two sizings. **STALE LEVELS** — predates the delisting join; only its ordering was cited | same |

**Read the two phase-crossed files first.** The others are history and are kept
BECAUSE they are wrong in instructive ways: `farm_holding_*` is one phase per
rule (phase alone is worth up to 3.75x), and `farm_breadth_*` is one phase per k
— which crowned k=50 when the phase-crossed run shows the optimum is k=10. The
corrections are the finding, not an embarrassment to tidy away.

**The two rules this directory exists to enforce:**

1. A farm number read off ONE rebalance phase is a draw, not a result. Four
   separate readings were overturned that way in one night.
2. **A farm number read off ONE window is a regime, not an edge.** Split it
   (`python -m scripts.portfolio_farm_subperiod`) before believing any of them.
   The best rule on this board is 1.01x the market in the half of history where
   its factor was not paying.

Every row carries `n_delist_measured` / `n_delist_assumed`. A run that fell back
on most of its exits still has an assumption for a headline, and the receipt has
to be able to say so.
