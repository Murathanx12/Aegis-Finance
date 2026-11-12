---
name: run-a-chunk
description: Use when executing rows of docs/ROADMAP.md with agents — "continue the roadmap", "run the next chunks", "use agents/builders", "run the workflow", or when resuming builders that a usage limit or a restart interrupted. Covers slicing a row into a chunk, the brief, worktrees, the adversarial review, merging, and what only the brain session may do.
---

# Run a chunk

One roadmap row becomes one chunk: **one builder, one worktree, one PR, one receipt.**
The session the owner talks to is the **brain**. It never hands away the four things that need
the whole picture: choosing the work, writing the roadmap, touching the runtime, and merging.

## Why this exists

The Codex month (10-08 → 11-08) produced ~205 commits, 141 of them stranded, in 121 worktrees,
with no strategy result. Every commit was fine; nothing joined them. The three nights after it
(S63–S65) merged 20+ PRs with this loop. The difference was not the model. It was that one
session held the roadmap and every other agent held exactly one row.

## Roles

| Role | Who | Does | Never |
|---|---|---|---|
| Owner | Murat | decides OD-rows, signs trials, presses attended switches | — |
| Brain | the main session | picks rows, creates worktrees, writes briefs, verifies evidence, merges, amends `docs/ROADMAP.md` + `docs/WORK_LEDGER.md`, does every runtime-side step | builds a large chunk itself while builders wait |
| Builder | one agent per chunk (Opus) | code + targeted tests + report + an **unmerged** PR | merges, edits roadmap/ledger, touches the runtime, removes a worktree |
| Reviewer | a fresh agent per PR | tries to refute the PR, given the diff and the row — not the brain's opinion | edits, pushes, merges |

## The loop

1. **Start the session properly.** `session_briefing()` + `aegis_verified_state()` (Optimus),
   `docs/ROADMAP.md`, `docs/WORK_LEDGER.md`, the newest `project_session_*` memory. Then the
   machine: free RAM, free disk on C:, scheduled tasks with a non-zero last result, OFF markers.
2. **Pick rows.** Status NOW, dependencies met, no owner decision pending. Two chunks may run
   together only if they share no file that both will edit (`backend/config.py` is tolerated:
   each adds one contiguous block). Prefer the row whose receipt changes what is done next.
3. **Slice to an MVP.** The chunk is the smallest thing that produces the row's acceptance
   receipt. If the row needs an attended step (a scheduled task, an order path, a key), the
   chunk ends at "built, tested, the by-hand step listed" and the brain does the step.
4. **Claim it** in `docs/WORK_LEDGER.md` (brain, in the docs worktree).
5. **Create the worktree yourself**, from a fetched `origin/main`:
   `git -C C:\Users\mrthn\aegis-wt\main-run fetch -q origin` then
   `git -C C:\Users\mrthn\aegis-wt\main-run worktree add -q -b s<NN>/<chunk> C:\Users\mrthn\aegis-wt\<chunk> origin/main`
   (`-q`, or the checkout prints thousands of lines). Never from the runtime checkout.
6. **Write the brief** (template below) and launch:
   - 1–2 chunks: the `Agent` tool, one call per builder, all in one message.
   - 3 or more, and the owner has asked for a workflow: `Workflow({scriptPath:
     ".claude/skills/run-a-chunk/chunk_workflow.js", args: {...}})`. Run it once with
     `dryRun: true` first; it validates the args and starts no agent.
7. **While they run**, the brain does brain work: runtime-side steps, the daily
   `owner_calls record`, health checks, the next briefs. Do not poll agents; a notification
   arrives. Do not run the same check a builder is running.
8. **Verify before believing.** A builder's report is a claim. For each PR: read the diff, run
   its targeted tests yourself, run its CLI once against a copy or with `--out` elsewhere, and
   check that nothing new appeared in the live data folder. Then send it to a reviewer
   (the workflow does this) unless the change is docs-only.
9. **One fix round**, through the same builder (`SendMessage` to the agent while it is alive; a
   fresh builder with the worktree state otherwise). Still open after one round means the brain
   decides: fix it by hand, cut scope, or close the PR and write down why.
10. **Merge** on green CI: `gh pr checks <n>` as single polls (never `--watch`, never a
    background wait), then `gh pr merge <n> --squash`. One PR at a time; re-check the next PR's
    mergeability after each merge.
11. **Close the row.** Amend the roadmap status cell and changelog, close the ledger row, in one
    docs PR per wave. Then the runtime-side step if there is one, accepted on the job's **own
    receipt advancing**, never on rc 0.
12. **End the session** with a `project_session_*` memory and its pointer in `MEMORY.md`. No dated
    handoff file in the repo.

## The brief

```
Chunk: <id>  Row: <CH-xx>  Worktree: <abs path>  Branch: <name>
Rules: read .claude/skills/run-a-chunk/BUILDER_RULES.md first, whole.
Goal: <one sentence: what exists afterwards that does not exist now>
Acceptance receipt: <the file or output line that proves it, and what value would be a failure>
Start from: <existing modules to read first; what already exists and must be reused>
Ruled out: <what was already tried or measured, with the receipt, so it is not redone>
May touch: <files>   Must not touch: <files other builders hold>
Inputs (read-only): <paths in the runtime data folder, with their size and newest date>
Limits: LLM spend <figure, default 0>; network <none | named source>; hard stop <time>
Report: <abs dir>\<id>_REPORT.md, appended as you go; commit after the first green test.
```

A brief that cannot name the acceptance receipt is not ready. Write the receipt first; the rest
of the brief follows from it.

## Limits that were measured, not chosen

- **Builders alive at once: 3** while the reader and the simulator run, **5** otherwise. Ten
  builders plus the reader got the test suite reaped twice (10-07); the PC bugchecked on 11-11.
- **Three Opus builders reach the 5-hour usage limit in about an hour.** They stop mid-file.
  Hence "commit after the first green test" and an incremental report: on 11-12 three builders
  stopped with ~900 uncommitted lines each and one had written no report at all.
- **Agents do not survive the session.** After a restart or `/compact` the worktree is the only
  state. Brief a fresh builder with `state:` describing what is in the worktree; do not recreate
  the worktree and do not trust the unreviewed code in it.
- **CI costs ~20 minutes per backend run** and the repo is public only because private minutes
  ran out (CH-28: 6,224 min/30 d measured). Batch docs amendments into one PR per wave.
- **`cmd | tail` hides the exit code.** A red test behind a pipe merged nothing only because the
  brain re-ran it. Print `${PIPESTATUS[0]}` or do not pipe.

## Only the brain, attended

Anything in `C:\Users\mrthn\aegis-finance` (the runtime: never merge, pull, checkout, reset,
stash or clean there) · scheduled tasks · release clones (`python -m scripts.runtime_release`,
retire only with `--retire`) · the reader, the simulator, the Telegram agent · provider budgets ·
worktree removal (search `aegis-recovery-evidence` for byte pins first) · anything the owner
must sign (`owner_calls log`, `register`, OD-rows). No agent of any kind sends an order, resets
an account, deploys, pays or messages.

## Which tool for what

| Need | Use |
|---|---|
| "Has this been tried?" | Optimus `brain_query` + `aegis_postmortems`, before any research brief |
| Live deploy / registry state | Optimus `aegis_verified_state`, `aegis_registry` |
| PRs, checks, CI minutes | `gh` CLI (`gh pr checks`, `python -m scripts.ci_watch`) |
| Library or API syntax | context7 |
| A dated public fact (an earnings date) | exa search, then the primary source; quote the date with its source |
| UI check of the site or the desktop app | playwright |
| New forward hypothesis | the `pre-register-trial` skill, before data accrues |
| New collector or try/except | the `silent-fragility-audit` skill |
| After a deploying push | the `verify-prod-after-deploy` skill |
| An independent read of a diff | a reviewer agent with the diff, told to refute it |

## Files here

- `BUILDER_RULES.md` — the standing rules every builder reads first.
- `chunk_workflow.js` — build → review → one fix → recheck, in batches; returns a recommendation
  per chunk and never merges. Args are documented at the top of the file.
