# Opus execution session #6 — kickoff prompt (prepared 2026-08-02)

Copy everything below the line into a fresh `/model opus` session started in
`C:\Users\mrthn\aegis-finance`. Plug the laptop in (EcoQoS throttle).

---

You are running the sixth pre-planned execution session for the Aegis
program. Same discipline as the first five (OPUS_SESSION_PROMPT_2026-08-01.md
— re-read its "House rules that bind you absolutely" section verbatim). One
run. **This is the search phase's terminal trial** — whatever it returns, the
13D family resolves and the explore queue is empty. Read first:

1. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-EVENT-13DG-HARVEST2.md` —
   frozen at module commit `c3e4f03`, candidate 179, TERMINAL.
2. `C:\Users\mrthn\Aegis module\TRIALS\TRIAL-EVENT-13DG-HARVEST.md` — the
   predecessor whose spec is inherited verbatim except the control rule.
3. `NEGATIVE_RESULTS.md` §30.

## Task 1 — run TRIAL-EVENT-13DG-HARVEST2 (frozen, go straight to build)

Reuse `aegis_brain/factory/event_harvest.py` — the ONLY change is the
control-matching rule: nearest neighbour in per-month standardised
(log mktcap, prior 6-month return), both measured at the last month-end
STRICTLY BEFORE the filing date; same segment + calendar month; eligible
rank ≤ 3000; no 13D/13G within ±60cd; one control per event, with
replacement, ties to smallest permno.

The PLACEBO GATE is unchanged and runs FIRST: five random-date seeds,
pooled |t| < 2.0, real number computed only on the passing branch —
compute-order is the tamper-evidence, same as HARVEST.

Spec tests first (minimum): the matching characteristics are measured
PRE-filing (a filing mid-month must not see that month's return or cap);
standardisation is per-month; tie-break is deterministic; the gate
short-circuits; everything inherited from HARVEST still holds (entry never
precedes filing, identical windows, event-leg-only costs).

One shot. Outcomes, per the frozen terminal clause:
- Gate fails → family closes (unmeasurable at mandate resolution). Write it.
- Gate passes, bar missed → family closes (real, unharvestable monthly). Write it.
- Gate passes, bar cleared → **STOP. Confirm is Murat's authorisation, always.**

Score the frozen prediction (gate passes ~60%; if read, +8..25 bps/mo,
t 0.8-1.6, narrow fail) and append results to the trial doc + NEGATIVE_RESULTS.

## Task 2 — housekeeping + search-phase closeout note

- Ledger: score anything newly scoreable; record the review otherwise.
- Module tests green, module pushed, prod untouched + verified healthy.
- Optimus brain refresh: `cd C:\Users\mrthn\optimus && python tools/refresh_aegis.py`
- NEW: since this resolves the last queued explore item, end your summary
  with a short **search-phase status**: candidates consumed (179), families
  closed vs alive, forward clocks running, and the attended decisions that
  remain (they should be: concentration control on mirror/conviction;
  un-parking the paper; nothing else). Do not act on any of them.

Nothing may be registered this session. Candidate count stays **179**.
