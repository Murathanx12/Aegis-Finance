---
name: silent-fragility-audit
description: Scan a change (or a subsystem) for the project's house failure mode — code that runs green and silently does nothing. Use after adding any collector, fetcher, model loader, or try/except; when a subsystem's output looks plausible but unverified; or on request ("audit X for silent fragility"). Wrong math gets caught by tests; silence doesn't.
---

# Silent-Fragility Audit

The recurring Aegis bug class is not wrong output — it is **no output wearing a
green checkmark**: the crash overlay dark for weeks behind a swallowed
signature error; the insider collector 403-ing on 100% of prod fetches under
12 passing tests; a "fast" suite that was never actually offline until a
cold-cache run.

## The checklist

Run these against the changed code (grep + read, then live where possible):

1. **Swallowed exceptions.** Every new/touched `except` must either re-raise,
   return an explicit degraded STATUS, or log at WARNING+ with context. Grep
   the diff for `except` blocks that `pass` / `return None` silently — each one
   is a finding. (~70 such legacy sites exist repo-wide: BACKLOG H5 — don't add
   to them.)
2. **Runs-but-fetches-nothing.** For any collector/fetcher: does success
   require non-empty output? A run with 0 fetched / all-zero values / empty
   payloads must be distinguishable from a healthy quiet run. Error rows must
   read back as `not_collected`/error — never as a real 0 (the false-zero
   lesson: failed insider runs wrote zeros AND advanced the throttle).
3. **Status row + canary.** Any subsystem that can go dark needs a persisted
   status row and a `/api/health/full` canary (the crash-overlay fix
   template: "persist a status + health canary," not just fix the call).
   If your new subsystem died tonight, would anything on the health surface
   say so?
4. **Rate limits + volume.** Every SEC/EDGAR call goes through the ONE shared
   rate limiter (`_sec_get` / `edgar_events._RATE_LIMITER`) with the declared
   UA. Estimate prod request volume — dev's handful of calls never trips what
   prod's egress trips instantly (403, not 429).
5. **Hangs.** External calls carry timeouts; no non-slow test can reach the
   network (the conftest socket block + pytest-timeout are the backstop — a
   STALL, unlike a refusal, hangs forever). edgartools-style libraries get a
   hang-safe wrapper or rejection.
6. **Degraded ≠ fabricated.** Fallback paths must not invent data (the
   all-cost-basis fake-NAV line: total price failure writes NO row, not a
   plausible one). NaN is "unavailable", never a value with status ok.
7. **Cache masking.** Would this pass on a cold cache? Warm disk caches have
   hidden both network-dependent "unit" tests and stale FRED reads. If the
   behavior differs cold vs warm, test cold.
8. **Contract drift at load boundaries.** Anything deserialized (models,
   sidecars, schemas) verifies its contract at load and fails LOUD on
   mismatch (the 67-vs-30 feature break; the sidecar-deletion bypass — both
   now guarded; keep new artifacts to the same standard).

## Output

Report findings ranked by severity with file:line, each classified: fix now
(silent-wrong) / pin with a test (known gap) / backlog (hardening). A clean
audit states explicitly which checks were run and what was NOT covered.
