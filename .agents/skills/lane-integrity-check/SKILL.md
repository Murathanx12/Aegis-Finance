---
name: lane-integrity-check
description: Run before AND after any change that goes near the paper lanes or books, lane YAMLs, strategy contracts, the scheduler's lane path, rebalance logic, or the NAV/positions tables (aegis_pi.db). Verifies the forward record's integrity invariants — config and contract hashes byte-stable, no spurious segments, registry untouched, positions consistent with NAV. The paper_nav write-path is sacred (CANON §5). The website lanes cannot be read while the hosted backend is off (since 2026-11); this skill says what can still be checked.
---

# lane-integrity-check

Read and follow the repository’s [shared lane-integrity-check instructions](../../../.claude/skills/lane-integrity-check/SKILL.md). Resolve their supporting files from that directory. Apply the repository’s current authority and runtime rules when running the procedure.
