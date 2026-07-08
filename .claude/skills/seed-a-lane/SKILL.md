---
name: seed-a-lane
description: The attended procedure for bringing a NEW paper lane live (new strategy arm, overlay trial, event-driven lane). Use whenever a new lane, lane variant, or lane seed flag is requested. Seeding is env-gated and attended — Murat flips the flag; sessions never improvise a seed.
---

# Seed a Lane (attended, env-gated)

New strategies enter the forward record ONLY as new pre-registered lanes with
their own config hash and inception. This is the procedure that has now shipped
mirror/conviction (P1 #6) and conservative-atr (TRIAL-EXIT) safely.

## Why this exists (paid-for lessons)

- **2026-06-17:** a seed flag was flipped while the wiring didn't exist — the
  seed was a silent NO-OP discovered only via the registry dump. Build and
  test the wiring BEFORE asking for the flag.
- Timing artifact same day: "registry still shows N" can be a race with the
  background seed's commit — re-query before declaring failure.
- In-place YAML edits reuse old content hashes and corrupt segment identity.

## Procedure

1. **Pre-register first** (see pre-register-trial): hypothesis, decision rule,
   canonical doc in `docs/TRIALS/`, committed BEFORE any forward data accrues.
2. **Own config file, own hash:** the new lane gets its own YAML (pattern:
   `data/conservative_atr_lanes.yaml`) — never appended into a live config
   whose hash identifies existing segments. Mandates copied byte-identical
   where the trial demands a matched control.
3. **Build the full wiring, no-op until seeded** (mirror the exit-lane
   pattern, `exit_lane.py`): idempotent `seed_*` function that registers the
   trial on seed; env-gated hook in `main.py` (`AEGIS_SEED_<NAME>=1`);
   scheduler daily/MTM/nav-freshness, track-record router, and registry N_eff
   all skip-until-seeded.
4. **Test before the flag exists in prod:** hash isolation from every existing
   config; no-op-pre-seed; idempotent double-seed; registry-row-on-seed;
   frozen controls byte-untouched; overlay/decision rule fires on synthetic
   data. The lane suite must be green offline.
5. **Ship, then hand Murat the flag.** Deploy the wiring (verify per
   verify-prod-after-deploy). Only then ask Murat to set the env flag and
   redeploy. Never set a seed flag yourself.
6. **Verify the seed live:** registry `cumulative_trials` incremented; the new
   trial row carries the decision rule; the lane appears with its own hash;
   ALL pre-existing lanes' NAV/inceptions/segments untouched
   (lane-integrity-check). NAV for the new lane appears at the next hourly
   MTM — null mid-cycle is normal, not a failure.
7. **Ask Murat to UNSET the flag** after the seed is confirmed (seeds are
   idempotent, but unset is the attended discipline).

## Hard rules

- No seed without a pre-registered trial row and canonical doc.
- No strategy change to an in-flight lane — a "v2" is a NEW lane or a new
  config version through the guarded evolution loop.
- The session builds and verifies; the human flips flags.
