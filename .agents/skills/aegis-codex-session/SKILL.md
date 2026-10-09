---
name: aegis-codex-session
description: Resume or hand off Codex work in Aegis using verified local state, Optimus memory and bounded agent delegation. Use for session setup, takeover and continuity work.
---

# Aegis Codex session

Read `docs/CODEX_OPERATING_MODEL.md` for routing and authority. Preserve Claude
files and use the existing Optimus memory store. Do not create another roadmap
or memory database when a current pointer answers the question.

1. Use `session_briefing` + `aegis_verified_state` through Optimus. Capture
   observation time; distinguish memory from live state. If unavailable, record
   the error and use `scripts/session_state.py`/repository evidence as fallback.
2. Follow `AGENTS.md` and `docs/INDEX.md`. Fetch refs before alleging missing
   work. Summarize the dirty tree instead of dumping hundreds of generated paths.
3. Resolve the user's current objective against the latest receipt. A newer
   user instruction outranks an older workflow note. Do not re-implement work
   already merged merely because an older handoff says it is next.
4. Make a small queue with named outputs and checks. Use deterministic probes
   for status and small-context workers for inventory/history. Give behavioral
   changes a builder and independent reviewer. Strategies require their existing
   evidence discipline and declared licence.
5. Store procedural findings and verified state with source paths, dates and
   unresolved dependencies. Never put raw private history or `users.json`
   identity values in Git or model prompts.
6. Ingest the sanitized pickup file through Optimus's existing notes channel;
   confirm retrieval by a distinctive query. Preserve source provenance and
   label old statements as historical instead of deleting their evidence.

For Bloomberg pickup, check local rehearsal runs, freeze records, scoreboard,
task triggers and the live gate separately. Use a real WLS export; never convert
a proxy or dry preview into a live sheet. Terminal rules and exact fills remain
inputs, not assumptions a model may supply.

For hooks, inspect only Codex config and plugin state. Aegis's session adapter
returns Codex `hookSpecificOutput.additionalContext`. Imported Claude-specific
security hooks stay disabled in Codex; original Claude files remain intact.
Validate startup in a fresh process before claiming hook delivery is fixed.
