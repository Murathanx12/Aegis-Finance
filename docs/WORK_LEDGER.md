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
| CH-59 universe refresh task | builder, S72 | `aegis-wt/ch59-universe-refresh` | `scripts/universe_refresh.py`, `backend/services/universe_refresh.py`, `backend/services/task_receipts.py`, tests, one block in `backend/config.py` | 2026-11-19 | PR open, in review | #169 |
| CH-65 hosted backend retired | builder, S72 | `aegis-wt/ch65-hosted-retired` | `scripts/paper_accounts_roi.py`, `backend/services/results_voice.py`, `backend/services/family_scorecard.py`, `scripts/system_status.py`, tests, one block in `backend/config.py` | 2026-11-19 | building | report in `aegis-recovery-evidence\s72-20261119\ch65` |
| CH-66 investigator reads filing text | builder, S72 | `aegis-wt/ch66-filing-text` | `backend/services/investigator_tools.py`, new `sec_exhibit_full` modules, `scripts/analyst_snapshot.py`, `backend/services/news_entities.py`, tests, one block in `backend/config.py` | 2026-11-19 | building | report in `aegis-recovery-evidence\s72-20261119\ch66` |
| Roadmap, ledger, skills, runtime-side steps | Claude S72 (brain) | `aegis-wt/s72-docs2` | `docs/ROADMAP.md`, `docs/WORK_LEDGER.md`, `CLAUDE.md`, `.claude/skills/read-a-filing-as-investigator` | 2026-11-19 | in progress | `aegis-recovery-evidence\s72-20261119` |
| CH-28 CI minutes | Claude S65 (brain) | `aegis-wt/ch28-ci` | `scripts/ci_minutes.py`, its tests, `.github/workflows/*` | 2026-11-12 | measured; design and tests owed | branch `s65/ch28-ci` `340d2544` |
| setup | Claude S63 | `aegis-docs-setup-20261109` (sparse) | `docs/ROADMAP_2026-11-09_*`, `docs/ASKED_VS_DELIVERED_2026-11-09.md`, `docs/WORK_LEDGER.md`, `docs/INDEX.md`, `CLAUDE.md`, `AGENTS.md`, `CITATION.cff`, `CONTRIBUTING.md` | 2026-11-09 | closed | `b8007f5c` |

## Closed

| Chunk | Agent | Closed | Outcome |
|---|---|---|---|
| S71 rows: CH-55 scorecard (#164), CH-56 loop map (#166), CH-57 isolation guards (#163), CH-58 study (#165), CH-64 status page (#167), S71 roadmap (#162); S72 skills refresh (#168) | Claude S72 | 2026-11-19 | all merged to main; none released (the PC runs `20261115b`); worktrees `ch55-scorecard`, `ch56-loop-map`, `ch57-isolation`, `ch58-revision-relative`, `ch64-status-truth`, `s71-docs`, `s72-skills` to remove after a pin search |
| Seven rows left open from S65–S68 (CH-38 dip study, CH-20a replay, CH-11 beta print, CH-35 wiring, CH-13, CH-11 twins, CH-12) | Claude S71 | 2026-11-16 | closed as stale: #119, #120, #123, #136, #142 merged; #139 superseded by #161; the beta print was never merged and is rebuilt as CH-55 |
| S70 afternoon: single-task builders and reviewers on CH-42, CH-44, CH-47, CH-48, CH-20a, CH-46 demotion, paper tables (CH-53), public health trim + receipt projection, trigger-token gate (CH-54), grader row; one integration branch `s70/integration`, one push | Claude S70 + builders | 2026-11-15 | integration PR; open: release after merge, `AegisDynamicBooks` hourly before the 11-19 cohort, repoint `AegisDataCatalog` (publisher) to that release before its next publish, attended restart of `AegisTelegramAgent`, owner's Railway steps (deploys, `AEGIS_TRIGGER_TOKEN`, LLM envelope), pre-registration of the two insider questions |
| S70 council (business + engineer, two rounds) and builders: #147 release/backfill/task, #149 price feed, #150 CH-45 dynamic books, #151 systems page, #152 gateway repair, #153 usage receipt, #154 data-rights register, #155 control-plane gate; each reviewed, one fix round | Claude S70 + builders | 2026-11-15 | merged to main; release `20261115a`; task `AegisRollingCohorts`; open: #156 repoint plan, #157 cohort report, CH-45 v3 + forward calendar, CH-46 embeddings tagging, #139 hedge replay fix round, CH-44, CH-42; next release for #149-#155; worktrees under `aegis-wt\` kept until the rows close |
| S69 builders and reviewers (#140 fix round, #142 review, #143 desktop home + owner inbox, #144 task receipts, #145 ticker hub; each reviewed, one fix round) + audits (accounts, branching, market replay) + roadmap rows CH-45..48 | Claude S69 + builders | 2026-11-14 | merged to main; releases `20261114a/b`; tasks `AegisSystemStatus`, `AegisTickerHub`; open: #146 labels, #147 rolling cohorts (in review), #139 hedge replay fix round, CH-44, CH-42; worktrees under `aegis-wt\` kept until the rows close |
| roadmap S67 council amendment (docs/ROADMAP.md only): CH-40..44, CH-20 a/b/c, notes on CH-01/11/13/14b/15/18/26/35/38, §5.8–5.10 | Claude S67 + three council experts | 2026-11-13 | docs only; no code, order or schedule change; positions in `aegis-recovery-evidence\s67-council-20261113\` |
| S65 handoff: CH-02 safety snapshot (no repo file; evidence folder, bundle, keep refs, two pushed branches); `run-a-chunk` skill (`.claude/skills/run-a-chunk/*`); roadmap and ledger amendments | Claude S65 | 2026-11-12 | done; #117 merged before it |
| S65 late night: CH-01 owner calls (`backend/services/owner_calls.py`, `scripts/owner_calls.py`, `backend/tests/test_owner_calls.py`, `docs/TRIALS/OWNER-CALLS-CONTRACT-v1.json`, three `docs/TRIALS/TRIAL-OWNER-CALL-*` documents) | Claude S65 | 2026-11-11 | frozen and pushed before the 11-12 UTC inception; owner signature, three probabilities and `register` pending (OD-13); `record` has no scheduled caller yet, so forward days are pinned by hand until a later release |
| S65 night: CH-31 typed 8-K family + `--no-write` writes nothing (`backend/services/one_event.py`, `scripts/one_event.py`) | Claude S65 | 2026-11-11 | done; chain still DEGRADED by measured verdict; OD-12 open (what counts as the finished state) |
| S65 night: pinned-source restores for the SEC raw collector and the T04 monitor (runtime bytes only, no repo file); public assets test (`backend/tests/test_public_assets.py`, #115) | Claude S65 | 2026-11-11 | pins restored and hash-verified, each job's own next receipt still to be read; publication worktree repair waits for the owner |
| S66 builders (CH-13 #119, CH-12 #120, Featherless comparison #121, CH-14a #122, CH-11 #123; each adversarially reviewed with one fix round) + roadmap rows CH-35..39 | Claude S66 + builders | 2026-11-12 | all merged to main; releases `20261112a/b`; worktrees `ch11-twins`, `ch12-news-grade`, `ch13-autopsy`, `ch14a-news-names`, `bakeoff-featherless` can be removed after a pin search; `ch28-ci` still open (CH-28 design owed) |
| S65 late evening: CH-22b live (desktop app served from the release clone; `Aegis.lnk` repointed; old reader shortcuts moved; `runtime_release` prints the desktop step and `--retire` guards shortcuts) | Claude S65 | 2026-11-11 | done; ON/OFF buttons not yet pressed; each new release repeats the printed desktop step |
| S65 evening: CH-05 switch, first six tasks (#110 reader launch fix, #111 null-device child + two pinned clocks, #112 no standard handles for pythonw; releases `20261111a/b/c`) | Claude S65 | 2026-11-11 | merged to main; six tasks on `aegis-runtime-20261111c`; clones a, b and rehearsal retired; next: OD-i, then DailyPass/Alerts/sim, order jobs attended |
| S65 day builders (CH-05 R1-R6 #100-#103 #105, wrapper + Telegram #104, untrack #108, review-5 fixes #109, CH-04b Featherless #107, CH-22b reader control #106) | Claude S65 + builders | 2026-11-11 | all merged to main; review 5 in the session scratchpad; worktrees removed |
| S65 night builders (CH-00/32 #86, CH-04 #88 #97, CH-30 #87 #93, CH-31 #91 #96, CH-22a #95, OD-10 #89, CI #90, CH-05 prep #98, learner + skills #92, consensus leak fix #94) | Claude S65 + builders | 2026-11-11 | all merged to main; nothing is in the runtime yet (CH-05); worktrees under `aegis-wt\` removed after merge |
| roadmap S64 amendment (docs/ROADMAP.md only) | Claude S64 | 2026-11-10 | §2a universe graph, tiers, CH-30/31/32/34 |
| license | Claude S63 | 2026-11-09 | `cd0b1d59` All Rights Reserved; CI green |
