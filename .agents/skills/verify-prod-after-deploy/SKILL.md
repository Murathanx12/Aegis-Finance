---
name: verify-prod-after-deploy
description: Run after a merge to main is RELEASED to the PC (a new release clone, tasks repointed) and before reporting anything as live or running. "Prod" is the PC since 2026-11 — the hosted Railway site is off by owner decision. Verifies the release clone exists and passed preflight, the changed tasks run from it, each changed job's OWN RECEIPT is advancing, the wrapper refused nothing new, and the status page row is green. Green tests and rc 0 are not a live verification (the insider collector passed 12 tests while 403-ing on 100% of prod fetches; the learning loop was refused for 24 days at rc 0).
---

# verify-prod-after-deploy

Read and follow the repository’s [shared verify-prod-after-deploy instructions](../../../.claude/skills/verify-prod-after-deploy/SKILL.md). Resolve their supporting files from that directory. Apply the repository’s current authority and runtime rules when running the procedure.
