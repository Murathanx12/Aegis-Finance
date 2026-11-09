# WORK LEDGER — who is writing what (one writer per file)

Read this before editing anything, whether you are Claude, Codex or a subagent.
Claim a chunk from `ROADMAP.md` by adding a row
with the file globs you will touch. Remove or close the row on merge. A file glob
claimed by an open row belongs to that row; if you need it, ask its owner
instead of editing it.

Hot files with one owner per phase: `backend/config.py`,
`backend/services/task_keeper.py`, `scripts/sim_run.py`,
`backend/services/provider_budget.py`, Windows scheduled-task definitions.

Worktree cap: 5 alive. Each one is created from origin/main for one chunk and
removed when that chunk merges.

| Chunk | Agent / session | Worktree | Files claimed | Opened | Status | Receipt / PR |
|---|---|---|---|---|---|---|
| setup | Claude S63 | `aegis-docs-setup-20261109` (sparse) | `docs/ROADMAP_2026-11-09_*`, `docs/ASKED_VS_DELIVERED_2026-11-09.md`, `docs/WORK_LEDGER.md`, `docs/INDEX.md`, `CLAUDE.md`, `AGENTS.md`, `CITATION.cff`, `CONTRIBUTING.md` | 2026-11-09 | merging | this commit |

## Closed

| Chunk | Agent | Closed | Outcome |
|---|---|---|---|
| license | Claude S63 | 2026-11-09 | `cd0b1d59` All Rights Reserved; CI green |
