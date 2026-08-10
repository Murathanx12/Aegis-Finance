# HANDOFF — ARENA-1 / BUILD-1.2 (2026-08-11, overnight)

Read this first. `docs/RESEARCH_PM_FLYWHEEL.md` is the architecture,
`docs/PORTFOLIO_RECONCILIATION.md` is what your book actually is, and
*Aegis module* `docs/ARENA1_REPORT_2026-08-11.md` and
`docs/ANALYST_IBES_1_VERDICT_2026-08-11.md` are the two research verdicts.

---

## The four numbers

| | |
|---|---|
| **+4.87 %/yr** | the false-discovery bar — best of 384 portfolios when **nothing** predicts anything. No Arena claim below it means anything. |
| **−8 to −18 %/yr** | analyst-implied upside as a stock picker, **gross**, on 21 years of point-in-time IBES. Third independent instrument. |
| **+1.5 to +6.1 %/yr** | analyst target **revisions**, gross. Real, and net-dead on 10× turnover. |
| **4th of 384** | where a book that picks its names **at random** ranked in the Arena. |

## What Murat has to do

**One thing: enter `cash`.** Everything else was recovered.

His holdings, share counts and 7 of 12 cost bases were reconstructed from
`book_lanes.yaml` + the immutable conviction decision log + the January PDF. He
should never have been asked to re-type them, and `scripts/reconcile_book.py`
means he will not be again.

Two smaller confirmations: **QUBT is 300 shares (log) or 200 (lane config)?**
and MSTR / FSLR / ELF / APLT are treated as **exited** because the 2026-07-11
log enumerates the whole book and does not contain them.

## What was built

| | where |
|---|---|
| Book reconciliation, read-only, prints every disagreement | `backend/services/pm_reconcile.py`, `scripts/reconcile_book.py` |
| Signal registry — 30 signals, enforced in code | `backend/data/signal_registry.yaml`, `backend/services/signal_registry.py` |
| Market opportunity funnel, 5,324 → 25 | `backend/services/opportunity_funnel.py` |
| Shadow register + learning ledger + firewall | `backend/services/shadow_portfolios.py`, `backend/data/shadow_portfolios.yaml` |
| Arena: genomes, manifest, evaluator, 11 synthetic worlds | *module* `aegis_brain/arena/` |
| IBES spine: 6 tables, 9.6 m rows, 1976–2026 | *module* `aegis_brain/data/ibes_panel.py`, `scripts/fetch_wrds_ibes.py` |

## The contradiction the brief now prints at the top

The lab measured analyst-implied upside as a cross-sectional picker and found
it **negative on three instruments**. The registry therefore permits the
haircut target only as a RISK_INPUT — it may *size* a name chosen on other
grounds.

**The brief's candidate list does not obey that yet.** Candidates are still
ranked by a certainty equivalent built from implied upside, which is choosing.
Every BUY in this morning's brief (TGTX, NVDA, ZYME, BMRN, TSM, TTWO, DHR, LLY,
ORCL, AVGO) rests on that ordering.

It was not silently fixed at 3 a.m., because replacing the selection layer in
the same session that produced the finding would ship an untested ranking onto
a real book. It is printed as an `EVIDENCE CONFLICT (HIGH)` on every brief, and
it is **the first thing to fix next**.

The fix is already half-built: the opportunity funnel ranks on
`profitability_small`, the one PICKER the registry validates that is computable
from free data. Wiring the funnel's output into the candidate list — instead of
the watchlist ranked by upside — closes it.

## Standing constraints this session added

* **A closed mechanism cannot re-enter.** The Arena's genome pool is generated
  *from* the registry; the funnel asks `permits()` before every ordering step.
  Not a convention — `check_closed()` raises.
* **The Arena's own numbers are a SCREEN, not a verdict.** No placebo band, no
  factor alpha, no impact, no delisting stub. Finalists go to `pf.run.Factory`.
* **Synthetic never counts as alpha.** It scores the instrument only.
* **P&L never reaches a position size.** `record_outcome()` returns `None`;
  the only path runs through a deterministic, ±0.05-capped, 30-sample-minimum
  reliability proposal that a human applies.

## The honest gap in the flywheel

The Arena **did not find** a planted +8 %/yr analyst effect in the synthetic
world, because the registry grades that signal RISK_INPUT, so no analyst-*led*
genome exists in the pool.

**The search can confirm what the lab believes and can never overturn it.**

Proposed fix, registered and not built: a **heresy sleeve** — genomes that lead
with a CLOSED or RISK_INPUT-only mechanism, tagged, excluded from every
selection rule, reported separately, unable to promote anything. They exist so
that if a corpse starts winning, something notices.

## Not covered

* **No `/api/health/full` canary** for the registry, funnel or shadow ledger.
  If the funnel died tonight nothing on the health surface would say so.
* **Yahoo rate-limited us mid-session.** The funnel's 27 batch downloads broke
  `.info` for the rest of the run; stage 3 now goes to Finnhub first. There is
  still no throttle on `_batch_history`.
* **yfinance calls have no explicit timeouts** (pre-existing, repo-wide).
* **6 permitted signals have no panel implementation** and were excluded from
  the Arena with printed reasons: catalyst proximity, LLM event extraction,
  options expectation, macro regime, crash composite, rating drift.
* **The shadow register is seeded but not populated.** Entering positions is
  attended: it needs a decision about whether the books run on the funnel's
  live universe or on panel proxies, and that changes what the record means.
* **The placebo band on ANALYST-IBES-1 was dropped for time** — a declared
  scope reduction. Nothing there claims to beat a random book at matched
  turnover, because that comparison was not made.

## Next five

1. **Close the evidence conflict** — funnel output becomes the candidate list.
2. **Enter `cash`**, confirm QUBT, flip `confirmed: true`.
3. **The heresy sleeve**, so the loop can run backwards.
4. **Fit `TARGET_HAIRCUT`** — still fitted to nothing, and every probability is
   linear in it. IBES now makes an empirical haircut estimable directly.
5. **Per-analyst reliability from `ptgdet`** — 17,364 analyst codes are on
   disk, but the values are adjusted to the download-date share basis, which is
   the exact defect that voided the July run. It needs `ibes.adj` arithmetic.
