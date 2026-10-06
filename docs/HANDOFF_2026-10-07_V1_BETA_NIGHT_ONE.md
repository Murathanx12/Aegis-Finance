# HANDOFF 2026-10-07 — V1 Beta, night one

TIER: dated handoff (a diary). The plan is `ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` (TIER 1).
Written by Fable 5.1 at the end of the 2026-10-06 night session. Every chunk C1-C12 was built by an Opus
builder, attacked by a second Opus, and fixed; every review lives in `docs/reviews/REVIEW_2026-10-06_*.md`
and every build note in `docs/research_notes/2026-10-06/`. Read the review beside the note: the reviews
corrected the notes in several places and the corrections are dated inside the notes.

## 0. READ THIS FIRST: the suite is NOT green-gated, and there was a process leak

- The final full-suite run was **killed at 48% by memory pressure** (the batch-1 run earlier had 13,137 passed, 2 failed;
  both failures were fixed by C13). Nothing has been merged to `main`. Commits `f4dbd0c0` and `951719f9` on
  `wip/2026-10-06-v1-beta` are WIP. **First task: rerun the suite, nn_lab/tests and ft_lab/tests, then merge.**
- **Process leak found at 03:30 HKT:** 590 python processes alive, 294 Optimus MCP servers + 296 `openclaw_api_bridge.py`,
  292 of them children of the OpenClaw gateway, accumulating one pair every ~2.5 minutes since the gateway started at
  14:28 on 10-06 (2.5 GB working set). I killed the children older than 10 minutes by recorded PID
  (`backend/data/optimus/local_pc/leak_killed_pids_2026-10-07.txt`); memory went from ~2 GB to 7.5 GB free. C14 found the cause
  (`docs/research_notes/2026-10-07/gateway_process_leak_2026-10-07.md`): the gateway starts an Optimus MCP server and
  an API bridge for EVERY OpenClaw agent session, and our `release_session` only ARCHIVED the session, which never
  retires those children. It was not a steady 2.5-minute leak but one burst: 146 `u_forecast` + planner turns between
  00:20 and 01:59 HKT, each leaving four OS processes. Fix: `release_session` now DELETES the session (after snapshotting
  its tool calls for the read-only audit), inside a `finally`; a `process_census` health row goes DEGRADED/DEAD above
  declared per-family caps. One owner config change recommended: `"sessionIdleTtlMs": 600000` under `mcp` in
  `~/.openclaw/openclaw.json`. The gateway may still hold up to 146 stale runtime slots of 256; clear by deleting the
  archived `aegis-*` sessions after 24 h or restarting the gateway by PID.

## 1. RESULTS SCOREBOARD

**RESULT IMPROVEMENT: NONE.** The night produced controls, measurements and a live loop, not an edge.

| line | value | receipt |
|---|---|---|
| Historical alpha on CRSP | On the STICKY twin (cost-fair by construction; declaration `DECLARATION_TWIN_STICKY_v1.json`), 44 of 277 scored rules reach fair-twin t >= 2; 40 also pass pure selection; **1** also beats the market in validation (`qc761`), with pure-selection t 1.16 in validation and 2009 carrying its market line. Random controls read t −0.3 to −0.5 (the old basket twin read them at −3 from turnover alone). Honest sentence: **historical alpha on CRSP is not demonstrated.** | `hyp_lab/twin_board_SUMMARY_STK_2026-10-07_2.json`; `sticky_twin_2026-10-06.md`; `REVIEW_2026-10-06_C1_FAIR_TWIN.md` |
| Paper estate | 1 book with >= 21 sessions is ahead of SPY (hack2, +1.14 pp / 26 sessions). The other 146 "ahead" are 108 control twins, 3 controls and 35 short-lived books worth about 2.6 ex-ante bets (4.6 net of SPY), most common name MU. Nothing is evidence yet. | top line of `docs/PAPER_ACCOUNTS.md`; `paper_accounts/book_dna_2026-10-06T163850Z.json` |
| Live loop | ALIVE: a scheduled sim owner (`AegisSimOwner`) starts a session on US trading days; the mandate is sized on broker equity; the funnel refreshed (25 candidates, 2 pass eligibility). The worst-case gate priced per sleeve on the names it would buy reads about 14% of equity → EXPLOIT is capped to about 54% gross until it passes; EXPLOIT is also refused on its own negative record. **This week the account will do almost nothing** (a 20% PROBE book, ~80% cash). | `pc_mandate/reconcile_2026-10-06_147824639837.json`; `REVIEW_2026-10-06_C2_*.md` |
| Forward reads unchanged | digest 5-session grades 10-09; SHADOW_NEWS trust may leave 0 ~10-11; LIB-FWD-TWIN-1 early kill 10-26; CRSP_BLEND_v0 / SHADOW_BAYES_v1 at session 21 ~10-27; straddle first entry 10-16. The forward graders were checked: parent and twin already pay symmetric one-time costs; nothing needs re-grading. | C1b note §forward graders |
| nn_lab | Running again under the membership freeze. Walk-forward re-run tonight: the network loses to a simpler model at every horizon; at h5 plain 12-1 momentum wins. No model has forward weight. | `nn_lab/receipts/wf_20261007T_c5_review.json` |
| Theory cells | hi52, insider buy-and-hold, beat-streak: FAILED_VARIANT on their declared primaries, all three UNPOWERED by their own rule (count 0 in the family posterior); the insider cell is degenerate by construction and the new declaration gate refuses it. Under the powered-only posterior no family is below 0.15 tonight. | `theory_cells_2026-10-06.md` (with dated corrections); `REVIEW_2026-10-06_C12_*.md` |
| Contest | Three rehearsal books frozen with hashes covering code and rule: ROT5_TRAIL, ROT5_DIR v2, MAXTAIL_BH v2 (+ MAXTAIL_EVT v1 declared). Runbook recommends ROT5_TRAIL at low commissions, MAXTAIL_BH at >= 25 bps; **ROT5_DIR not recommended** (event replay: the filter drops 28% of top movers and trades right tail for left-tail protection). Live desk refuses without `contest/REGISTERED` + a WLS MEMB export. | `contest/rehearsal/freeze_log.jsonl`; `REVIEW_2026-10-06_C9_*.md` |
| LLM spend | DeepSeek balance $18.49 at 11:17 UTC 10-06; the night's cells and boards ran at $0; planner $0.0033. | `deepseek_balance.jsonl` |

## 2. WHAT LANDED (one line each; the note has the detail, the review has the attack)

C1/C1b fair + sticky twin, one cost model and one turnover function across every board, headline needs pure selection too · C2 $1M mandate on broker equity, $10k/$40k/$1M scaled views, sim owner, per-sleeve worst case every cycle, lease, account check · C3 `book_dna` (twins, controls, holdings clusters, ex-ante bets, loser error types with `not_determinable`) on every ROI receipt · C4 `/opportunities` page + `/api/opportunities`, `/brain` page, the public site's API-URL bug found and worked around · C5 nn_lab membership freeze + revisions + frozen inputs + tournament incl. momentum · C6 Telegram plain-language router, buttons, receipt ages · C7 query planner (declared-provider gate; $0 Google News RSS + EDGAR sources; attribution at read time), WSJ feeds moved to live URLs, two dead MarketWatch feeds retired, OpenClaw spend visible in `llm_usage` · C8 progress-aware health (task rows read their receipts; 17 UNKNOWN → 0), `AegisBrainRefresh` and `AegisAnalystPull` owners · C9 above · C10 data catalog (4,742 datasets; 61 replay groups listed; runtime-built paths separated from true orphans) + lossless ledger archive sealed only by a tracked Parquet · C11 Decision Story ids + frozen alternatives + signed regret by type + plan-plus-news-tilt alternative, graded in the daily pass · C12 theory cells, declaration gate, posterior that counts only powered negatives, snowball prereg draft (unsigned; return leg unpowered).

## 3. WHAT THE REVIEWS CAUGHT THAT THE BUILDS HAD WRONG (keep these as lessons)

- A "fair" twin that pays its own turnover still flatters a holding rule if the twin is rebuilt monthly; the control must share the rule's turnover by construction (sticky), and even then it is a weaker style control for fast rules. Read a twin verdict only where pure selection agrees.
- Two boards measured turnover in different units (per rebalance vs per month) and nobody noticed until a reviewer compared one rule across them.
- A worst case priced at the universe median sigma passes; priced on the names the sleeve would buy, it refuses. Price risk on the book you would hold.
- "Reconciled" that compares a number with itself is a tautology; reconcile positions.
- Sizing and timing "regret" defined as best-of-two is positive on a random walk. Every regret must be a signed difference and pass a null test.
- A point-in-time check on vendor data is empty if every row carries the newest pull date; store first-seen.
- A seal that checks file size is not a seal.
- A clustering "independent" count from name overlap overstates independence several-fold; count bets from ex-ante return correlation.
- A membership freeze that stores adjusted-close dollar volume locks in a small look-ahead instead of removing it.
- A nightly unattended `--apply` that writes manifests nobody commits is not archival.

## 4. OWNER DECISIONS (new or still open)

| # | decision | state |
|---|---|---|
| D1 | Bloomberg registration: did it happen? If yes: create `contest/REGISTERED`, export WLS MEMB to `contest/wls/`, answer the runbook's owner-only checklist items; choose the live book via `contest/live/BOOK` (default ROT5_TRAIL). | OPEN, blocks the live desk from Oct 9 |
| D2 | Six fleet roles / Alpaca reset (proposal in the roadmap §6) | OPEN |
| D5 | EVLV / RZLV tight stops | OPEN |
| D7 | sign-ups / watchlists on news sites | OPEN (not built) |
| D13 | Mirror lane: the 25% cap cannot hold when the allocator drops to two names (06-16 and 07-14 ran 50/50); enforcing the declared cap by holding the remainder in cash is lane-integrity work on the sacred path | OPEN, recommended yes |
| D14 | PC-PAPER "benchmark core": hold 1 − active in SPY so the account matches what the contract claims and every sleeve is graded as excess (the C2 reviewer's lever). You disliked an 80% SPY core as "not beating anything"; the alternative is 80% cash, which is also not beating anything. | OPEN |
| D15 | OpenClaw search provider: a paid API conflicts with "no payments" unless you authorise it; the $0 RSS/EDGAR sources run meanwhile | OPEN |
| D16 | QUBT carries none of the three risk flags (4 analysts, 8 quarters of cash, no FDA event); flagging it needs a fourth rule (pre-revenue / price-to-sales) | OPEN |
| D17 | Commit the ~6 MB opportunities receipt daily (so the public page works on Railway) or accept a stale page there | OPEN; committed once tonight |

## 5. FIRST TASKS FOR THE NEXT SESSION

1. `python -m scripts.health_probe` — `sim_session` must not read DEAD during US hours; `task:*` rows must have 0 UNKNOWN; nn_lab must have a receipt newer than 08:30 HKT.
2. `python -m scripts.ci_watch --wait` if CI is still running on the night's commit.
3. Restart the Telegram serve child by PID (procedure in `telegram_cockpit_2026-10-06.md`) so the cockpit goes live.
4. Verify the live website after the Vercel redeploy: the dashboard's API calls must hit the Railway host, and `/opportunities` must load (verify-prod-after-deploy skill).
5. Read the first sim session's plan receipt written by the NEW `u_plan` (tonight 21:00 HKT start): stories and alternatives present, `risk_gate` printed, replay MATCHES.
6. Owed small items: register `AegisDataCatalog` (command printed by `python -m scripts.task_keeper register`), delete the retired `AegisWRDSPullNight`, run the ROT5_DIR replay as our own receipt with a momentum control, per-draw turnover check for the sticky twin (v2), the price-location ATR/day-range feature, F9 lane-beta lag check in `book_dna`.

## 6. OPERATIONAL NOTES

- Every subagent spawned its own Optimus MCP server and API bridge (about ten pairs by 02:00); with ten builders the machine fell to ~2 GB free and two agent waits were killed by memory. Limit concurrent builders to ~5 or make the MCP server shared before the next night of this size.
- The suite takes ~22 minutes on this machine with builders running; run it once per merge batch, never in parallel with a CRSP board rerun.
- The Opus session limit killed six agents mid-edit at 01:40 HKT; the WIP commit made minutes earlier is why nothing was lost. Commit WIP on the work branch before any limit window.
