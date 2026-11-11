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
| setup | Claude S63 | `aegis-docs-setup-20261109` (sparse) | `docs/ROADMAP_2026-11-09_*`, `docs/ASKED_VS_DELIVERED_2026-11-09.md`, `docs/WORK_LEDGER.md`, `docs/INDEX.md`, `CLAUDE.md`, `AGENTS.md`, `CITATION.cff`, `CONTRIBUTING.md` | 2026-11-09 | closed | `b8007f5c` |

## Closed

| Chunk | Agent | Closed | Outcome |
|---|---|---|---|
| S65 night builders (CH-00/32 #86, CH-04 #88 #97, CH-30 #87 #93, CH-31 #91 #96, CH-22a #95, OD-10 #89, CI #90, CH-05 prep #98, learner + skills #92, consensus leak fix #94) | Claude S65 + builders | 2026-11-11 | all merged to main; nothing is in the runtime yet (CH-05); worktrees under `aegis-wt\` removed after merge |
| roadmap S64 amendment (docs/ROADMAP.md only) | Claude S64 | 2026-11-10 | §2a universe graph, tiers, CH-30/31/32/34 |
| license | Claude S63 | 2026-11-09 | `cd0b1d59` All Rights Reserved; CI green |
