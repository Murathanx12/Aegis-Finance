# Opus execution session #4 — kickoff prompt (prepared 2026-08-02)

Copy everything below the line into a fresh `/model opus` session started in
`C:\Users\mrthn\aegis-finance`. Plug the laptop in (EcoQoS throttle).

---

You are running the fourth pre-planned execution session for the Aegis
program. Same discipline as the first three (OPUS_SESSION_PROMPT_2026-08-01.md
— re-read its "House rules that bind you absolutely" section verbatim). Read
first:

1. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-EVENT-13DG.md` — the whole file,
   ESPECIALLY the "BOOK STAGE" section frozen at module commit `6fcc381`.
2. `NEGATIVE_RESULTS.md` §28-§29.

## Task 1 — run the 13DG BOOK STAGE (frozen, go straight to build)

Build `scripts/run_13dg_book.py` implementing the frozen book spec EXACTLY:
two books (`13d_all`, `13d_first`), banked event sets as run, eligibility
rank ≤ 3000 at entry month-end, entry at first month-end on/after filing,
3-month-end hold with reset-on-refiling, EW monthly rebalance, pooled net
excess vs EW-eligible benchmark, deciding costs per-name KO-half on actual
turnover with flat-25 guard + zero-cost bound reported, bar t ≥ 1.5 with
positive mean. Explore 2004-2018 only.

Spec tests first (minimum): entry never precedes the filing date; a name
filed mid-month enters at that month's end, not the prior one; the hold exits
at the 3rd month-end; a re-filing resets rather than doubles; the cost charge
is per-name and size-aware; the eligible universe matches the factory's.

One shot per book. **If a book clears the bar: STOP — confirm is Murat's
authorisation, always.** Either way, score the frozen book-stage prediction
(both books +5..+35 bps/mo, t 0.5-1.5, 13d_first > 13d_all, neither clears)
and append results to the trial doc + extend NEG_RESULTS §29 (or write the
graduation note).

## Task 2 — housekeeping (only after Task 1 is written up)

- Score anything newly scoreable in `docs/research/PANEL_PREDICTION_LEDGER.md`.
- Module tests green, module pushed, prod untouched + verified healthy.
- Refresh the Optimus brain:
  `cd C:\Users\mrthn\optimus && python tools/refresh_aegis.py` (idempotent).

Nothing may be registered this session. Candidate count stays **177**.
Summary must state: both book verdicts as frozen, the prediction scored,
repairs disclosed, and whether anything now needs an attended decision.
