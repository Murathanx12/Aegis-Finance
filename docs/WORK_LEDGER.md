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
| CH-38 dip study | builder (Opus), S68 | `aegis-wt/ch38-dip-study` | `scripts/ch38_dip_study.py`, its tests, one block in `backend/config.py` | 2026-11-13 | building | branch `s68/ch38-dip-study` |
| CH-20a hedge replay | builder (Opus), S68 | `aegis-wt/ch20a-hedge-replay` | `scripts/ch20a_hedge_replay.py`, its tests, one block in `backend/config.py` | 2026-11-13 | building | branch `s68/ch20a-hedge-replay` |
| CH-11 note: beta print | builder (Opus), S68 | `aegis-wt/ch11-beta-print` | `backend/services/book_dna.py`, `scripts/results_voice.py`, their tests | 2026-11-13 | building | branch `s68/ch11-beta-print` |
| CH-35 wiring, CH-14b observe-only runs, roadmap and ledger | Claude S68 (brain) | `aegis-wt/s68-docs` | `docs/ROADMAP.md`, `docs/WORK_LEDGER.md`; runtime-side steps | 2026-11-13 | in progress | PR #136 first |
| CH-13 autopsy | none (builder stopped 11-12; brief a fresh one) | `aegis-wt/ch13-autopsy` | `backend/services/discovery_autopsy.py`, its tests, one block in `backend/config.py` | 2026-11-11 | interrupted, unreviewed | branch `s65/ch13-autopsy` `19cb296b` |
| CH-11 twins | none (builder stopped 11-12) | `aegis-wt/ch11-twins` | `scripts/matched_twin_reeval.py`, its tests, one block in `backend/config.py` | 2026-11-11 | interrupted, unreviewed | branch `s65/ch11-twins` `d6c2979d` |
| CH-12 news grade | none (builder stopped 11-12) | `aegis-wt/ch12-news-grade` | `scripts/ch12_news_grade.py`, its tests | 2026-11-11 | interrupted, unreviewed | branch `s65/ch12-news-grade` `97039739` |
| CH-28 CI minutes | Claude S65 (brain) | `aegis-wt/ch28-ci` | `scripts/ci_minutes.py`, its tests, `.github/workflows/*` | 2026-11-12 | measured; design and tests owed | branch `s65/ch28-ci` `340d2544` |
| setup | Claude S63 | `aegis-docs-setup-20261109` (sparse) | `docs/ROADMAP_2026-11-09_*`, `docs/ASKED_VS_DELIVERED_2026-11-09.md`, `docs/WORK_LEDGER.md`, `docs/INDEX.md`, `CLAUDE.md`, `AGENTS.md`, `CITATION.cff`, `CONTRIBUTING.md` | 2026-11-09 | closed | `b8007f5c` |

## Closed

| Chunk | Agent | Closed | Outcome |
|---|---|---|---|
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
