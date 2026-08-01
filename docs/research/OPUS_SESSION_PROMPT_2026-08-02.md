# Opus execution session #2 — kickoff prompt (prepared 2026-08-01)

Copy everything below the line into a fresh `/model opus` session started in
`C:\Users\mrthn\aegis-finance`.

---

You are running the second pre-planned execution session for the Aegis
program. Same discipline as the first (OPUS_SESSION_PROMPT_2026-08-01.md —
re-read its "House rules that bind you absolutely" section verbatim; every
rule applies). Read first:

1. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-OPT-COHORT.md` — frozen at module
   commit `a84e5b1`, seven arms, candidates 167-173. This is your main run.
2. `C:\Users\mrthn\Aegis module\docs\DRAFT_13DG_REGISTRATION_2026-08-01.md` —
   the 13D/13G draft (still NOT frozen; blocked on the collector you build).
3. `NEGATIVE_RESULTS.md` §23, §26 (residualisation receipts) and §20 (the
   selection trap your event work must not repeat).

## Task 1 — run TRIAL-OPT-COHORT (frozen, go straight to build)

Build `scripts/run_trial_opt_cohort.py` implementing the frozen doc EXACTLY:
seven arms, declared directions, the frozen null rule (DROP + VIX-tercile drop
reporting + always-covered robustness line for arms with stress-correlated
drops), explore 2004-2018 only, deciding arms largemid@flat25 + small@KO-half,
zero-cost bound reported, DSR at n=173.

Spec tests BEFORE the run (the Kirk session's table-daterange lesson: verify
at build time that every input table actually covers 2004-2018). Minimum
tests: the null rule drops rather than fills; skew_resid's regression is
per-month cross-sectional with the four frozen regressors; term_slope uses
91−30; the secid→permno link is date-valid; O/S denominators come from dsf
stock volume.

One shot. If any arm graduates: **STOP before confirm** — confirm needs
Murat's explicit authorisation. Results into the trial doc + a new
NEGATIVE_RESULTS section (or graduation note), scored against the house
predictions AND ledger forecasts R15-2/R15-3 (update
`docs/research/PANEL_PREDICTION_LEDGER.md` with HIT/MISS).

## Task 2 — build the EDGAR 13D/13G collector (free data, no WRDS)

wrdssec is not subscribed, so the activist-event family needs EDGAR. Build
`aegis_brain/data/edgar_13dg.py`:

- Source: EDGAR quarterly form index files (`full-index/{year}/QTR{n}/form.idx`),
  form types SC 13D / SC 13D/A / SC 13G / SC 13G/A, 2002-2024.
- Route ALL requests through a rate-limited session honouring SEC's 10 req/s
  policy with a proper User-Agent — reuse the `_sec_get` choke-point pattern
  from the prod insider collector (NEG_RESULTS §5 is the receipt for what
  happens otherwise).
- Output: one parquet of (accession, form_type, filed_date, cik, company_name,
  subject_cusip/cik where parseable). Filer→subject mapping from the index
  alone is imperfect; document precisely what is and is not resolvable without
  fetching filing bodies. Do NOT fetch 400k filing bodies this session — index
  first, measure the resolution rate, and report it.
- Spec tests with canned index fixtures; the collector must fail loud, not
  return empty on HTTP errors (silent-fragility house rule).

Then UPDATE the 13D/13G draft with the measured resolution rate and event
counts per year — still draft, still not frozen. Registration happens only
after Murat sees the event-count reality.

## Task 3 — only if time remains

Score any newly-scoreable panel predictions; check the ICSA FRED warning
(economic_surprise, one-off on 2026-07-31 — recurring or not?); nothing else.
Do not register anything beyond Task 1's already-frozen cohort.

## Definition of done

Trial doc + NEG_RESULTS updated, ledger scored, module tests green, module
pushed, prod untouched and verified healthy, session summary with verdicts as
frozen + repairs disclosed + candidate count (173; 13D/13G still uncounted).
