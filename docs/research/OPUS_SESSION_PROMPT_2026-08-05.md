# Opus execution session #5 — kickoff prompt (prepared 2026-08-02)

Copy everything below the line into a fresh `/model opus` session started in
`C:\Users\mrthn\aegis-finance`. Plug the laptop in (EcoQoS throttle).

---

You are running the fifth pre-planned execution session for the Aegis
program. Same discipline as the first four (OPUS_SESSION_PROMPT_2026-08-01.md
— re-read its "House rules that bind you absolutely" section verbatim). This
session has ONE run. It is likely the program's last explore shot, so
execution fidelity is everything. Read first:

1. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-EVENT-13DG-HARVEST.md` — frozen
   at module commit `0951193`, candidate 178.
2. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-EVENT-13DG.md` — the parent:
   the §29 control rule you must reuse VERBATIM, and the book stage whose
   defect this design corrects.
3. `NEGATIVE_RESULTS.md` §29 (incl. the book-stage extension).

## Task 1 — run TRIAL-EVENT-13DG-HARVEST (frozen, go straight to build)

Build `scripts/run_13dg_harvest.py` per the frozen doc EXACTLY. The two
things that make this run valid:

- **The control rule is the parent trial's, verbatim** — same matching
  fields, same ±60cd exclusion, applied at the ORIGINAL filing date (the
  control is matched to the event, then both legs are measured over the
  monthly-implementable window: first month-end on/after filing → third
  month-end after entry).
- **The PLACEBO GATE runs FIRST and is read FIRST**: five seeds of random
  filing dates on the same permnos through the identical pipeline. If pooled
  placebo |t| ≥ 2.0, STOP — the verdict is NO CONCLUSION, write that up, do
  not read the real number. Structure the runner so the real result is not
  computed until the gate has passed (compute-order is the tamper-evidence).

Spec tests first (minimum): entry never precedes filing; both legs share the
identical window; the control-match fields equal the parent's; costs hit the
event leg only, per-name, size-aware; the placebo redraw preserves each
permno's event count; the gate short-circuits before the real computation.

One shot. **If it clears the bar: STOP — confirm is Murat's authorisation,
always.** Either way score the frozen prediction (+8..+25 bps/mo, t 0.8-1.6,
narrow fail, placebo clean) and append results to the trial doc +
NEGATIVE_RESULTS (family-close section or graduation note).

## Task 2 — housekeeping (only after Task 1 is written up)

- Ledger: score anything newly scoreable; record the review if nothing is.
- Module tests green, module pushed, prod untouched + verified healthy.
- Refresh the Optimus brain:
  `cd C:\Users\mrthn\optimus && python tools/refresh_aegis.py`

Nothing may be registered this session. Candidate count stays **178**.
Summary must state: the gate result, the verdict as frozen, the prediction
scored, repairs disclosed, and whether anything needs an attended decision.
