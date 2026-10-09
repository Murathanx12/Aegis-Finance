# Operational verification — 2026-10-09

RESULTS, October 8 marks: 11/71 strategy accounts ahead of same-window SPY,
nine distinct bets out of 59; 236 controls excluded. Revision-flow leader
+6.97% versus +0.73% SPY = +6.24 pp over nine sessions, OBSERVED. Sixty accounts
behind; mirror trails SPY by 28.34 pp over 79 sessions. No claims promoted.
Source: local `paper_accounts/results_voice_2026-10-09T045359Z.md`.

This report distinguishes local source, deployed source, live outputs, cached
health and indexed memory. Recovery has not changed trading rules, submitted
orders, rewritten NAV, or touched the protected IIF launcher.

## Verification matrix (UTC unless stated)

| Component / purpose | Owner, environment, version | Input / last successful output; test | Result / cause / repair or dependency |
|---|---|---|---|
| API and persistent ledger | Railway selfless-courage, `343a3af1` verified 10:25:59 UTC | Direct HTTP `/api/health`, `/api/health/full`, OpenAPI and track record 200; 12 jobs reported healthy; all ten NAV dates October 8 | HEALTHY for sampled public API and marks; not a claim that every nested subsystem is healthy |
| Public frontend | Vercel production `dpl_AbyrBF8Y714h23JV7TRnwfpdzT7H`, October 7 08:57:39; workflow head `3a109566` | Live alias resolves to the exact URL in successful workflow `37597075320`; frontend tree identical to current main. Six pages 200; expected HTML/chunks and API CORS | HEALTHY HTTP/API and deployed-source evidence; interactive browser rendering not independently tested while the guarded reader owns its profile |
| Public evidence pages | Image receipt publisher → FastAPI legibility and arena/opportunity routes | Seven representative surfaces 200; October 9 refreshed copies pushed by the real scheduled task, then health follow-up `9ea43a12`, 4,768,221 bytes | Published successfully; final served-commit/source-stamp evidence is recorded in the closeout receipt below. Opportunity source is October 9 03:31:21 UTC; the later rebuild refused low RAM. October 7 was the old deployed copy, not the retained local source |
| Recurring publication | AegisDataCatalog, Windows; dedicated main worktree `../aegis-finance-publication` | Real task started 09:56:17, catalog scanned 45,014 files / 5,872 datasets; publisher wrote all eight kinds and pushed `ba135a54` at 09:58:05 | HEALTHY publishing repair; overall task remains DEGRADED solely on opportunity rebuild's 1.67 GB free vs 4 GB floor. Triggers/principal/settings unchanged; exit 0 alone did not establish step success |
| Main live forecasts | Railway persistent `/data/optimus/predictions.jsonl` | 736 forecasts, 431 resolved, six void; zero overdue, bad lines or duplicate IDs at probe | HEALTHY for this ledger; proposed split migration not applied; local campaign ledger is a separate dormant population |
| News ingestion/digest | PC OpenClaw reader + AegisWorldDigest | October 9 04:30 digest: 1,495 inputs, 41 forecast writes, no failed extraction calls; page log advances after 06:00 | HEALTHY advancing path with DEGRADED provenance for 262 undated inputs; model extraction is paid and explicitly budgeted |
| News decision influence | world_state + sim shadow | 38 shadow decisions; direction/size trust both zero; recent graded mean improvement negative | INTENTIONALLY OFFLINE portfolio tilt; NEWS_TILT_IN_PLAN remains false |
| Auxiliary news/events | Collectors and PC daily pass | 27/32 news sources fresh within three days; event feed 22 extractions October 8; EDGAR and earnings succeed | DEGRADED: YFinance event fetch 20/20 failures; YouTube last October 2; five news sources quiet/stale. No fabricated zeros or blanket healthy claim |
| Accrual canary / alternative inputs | Railway and local health probes | 4,004 new forecasts over three days locally; eligibility limited by score/evidence; some cloud contracts absent | DEGRADED: canary contract coverage, congress/ARK no rows and 13F August 14. Do not loosen thresholds to turn health green |
| PC paper account | PC broker read-only paper API | Fresh account/positions/orders GET: 31 positions, zero open orders, 35 fills since October 7; last fill October 8 14:30:06 | HEALTHY connectivity and actual fill history; no new order submitted in this audit |
| Fleet paper accounts | PC fleet managers; paper API only | Five accounts ACTIVE; positions 22/20/9/1/38; open orders 22/20/9/1/37; four accounts have October 7/8 fills, hack5 none in that window | DEGRADED reconciliation: hack5 historical stop lookup 404, fail-closed cooldown; quiet fills alone are not a failure. FleetDailyCheck exits 1 |
| Sim market-session owner | AegisSimSessionOwner, PC | Owner ticks advance every 30 minutes; overnight receipts correctly say outside_window; prior sim ended uncleanly October 8 14:42 | DEGRADED: previous session dead; next authorized market-window startup needs observation. Do not force an out-of-window run |
| IIF-1 | Protected AegisIIF1NightLauncher; actual registered trigger 16:00 local | October 8 interrupted; October 9 scheduled invocation evaluated 08:15:34 UTC, after latest safe launch 08:14; refusal written 09:02:13, code PAST_LATEST_SAFE_LAUNCH. Newest completed night October 7 | DEGRADED missing accrual, correctly REFUSED late start; Windows standby/hibernate events explain the interruption. Task exit 0 is not completion. No retry permitted; launcher and 16:45–17:05 local exclusion preserved |
| NN research / learning | Existing NN venv and nightly entry point | Missing dotenv caused the earlier task failure. Repaired run `nightly_20261009T062357Z` completed OK at 06:26:30 in 152.2 s: 5,861 new rows, 2,973 matured labels, fit and freeze completed, bars through October 8 | HEALTHY repaired entry point; declared/installed python-dotenv 1.0.1. Frozen grid retained (1,198,469 rows), no ETF removals; zero newly graded forward-roster forecasts, so no new performance claim. Historical scheduler exit remains 2 until its next firing |
| Old hack1–6 Railway loops | loving-elegance persistent services | No active deployments; configuration/history identifies September 29 retirement and PC replacement | INTENTIONALLY OFFLINE; not restarted |
| Seal authority | loving-elegance, deployment `aa09c009` September 29 | Independent HTTP 200 for October 8/9 books, latest allocator and F engine; seals advance from October 8 05:07:37 to October 9 05:07:40; allocator October 8; F engine month October | HEALTHY served artifact path. F's panel is frozen through December 2015; its September construction stamp is distinct from October engine membership, not current market input or a new alpha claim |
| Optimus | Existing local MCP and aegis-docs index | Full docs ingestion: 860 files / 861 pages; MCP query `local-runtime-digest` returns this recovery's operating digest with source path. Health snapshot regenerated at 06:21 | HEALTHY retrieval; generic multi-topic queries can rank old overviews, so use distinctive terms and source provenance. Indexed memory remains distinct from live checks |
| OpenClaw browser | Existing gateway/dedicated profile, PC | Gateway/CDP and browser-status call successful; reader writes advancing logs | HEALTHY observed path; retain one operator, policy restrictions and local browser state |
| Local Qwen operations digest | Qwen2.5-7B-Instruct-Q4_K_M, loopback llama.cpp | Real sampled-log inference at 05:58:44: 454 tokens, 2.77 seconds, $0, 3.53 GiB available loaded; owned process stopped | HEALTHY on-demand inference; refuses <3 GiB before/<1 GiB after start, protected window and nonlocal endpoint; no paid fallback |
| Bloomberg rehearsal | Contest tasks and frozen contest contract | October 9 drills 13/13; actual 14:30 local rehearsal completed 06:33:08 UTC, 21 positions/11 closed graded; desk completed 06:34:15, expected calendar idle (live sheets October 11–November 12) | HEALTHY rehearsal/idle receipt; live gate BLOCKED: contest gate exits 2 because authentic WLS MEMB is absent. No local live position/fill receipts; actual Terminal holdings unverified. Registration marker and drills are not membership/fill proof |

Raw probe receipts remain local at `../aegis-recovery-evidence/coordinator/`
and `runtime/`. They include `http_probes.json`, `public_pages.json`,
`paper_broker_reads.json`, `pc_paper_read.json`, `local_health_raw.json`,
`local_model_smoke.json`, tasks/process samples and Git inventories. Do not
commit those raw records: some include account/order metadata. The local health
probe at 05:49:21 reported 43 ALIVE, 17 STOPPED, 16 STALE, one DEAD and one
REFUSED. Some process rows explicitly reused an older process probe; those
rows are not fresh independent process evidence.

A second complete probe at **09:14:05 UTC**, with fresh process checks, reported
45 ALIVE, 17 STOPPED_BY_OPERATOR, 16 STALE, one DEAD and zero UNKNOWN/REFUSED
in its legacy summary buckets. Detailed task states additionally include
DEGRADED and ALIVE_IDLE_EXPECTED; the bucket totals are not a global verdict.
The sim remains the DEAD prior-session row while its scheduler is correctly
idle before the market window. IIF's newest completion remains October 7.
Receipt: `health/health_20261009T091405Z.json`. Fleet audit also identifies
hack6 LNG stop coverage of zero for three shares; this and hack5's historical
stop 404 require contract-aware reconciliation, not new orders from this audit.

IIF interruption evidence is in local `coordinator/iif_power_events.json`:
Kernel-Power 506 records standby at 06:54 UTC, event 42 at 08:15:34 says
"Standby Battery Budget Exceeded", and Power-Troubleshooter event 1 records
sleep 08:15:25 and wake 09:01:55 UTC. The lid wake and clock synchronization
explain the long interval before the refusal was written. TaskScheduler's
Operational log is disabled, so the precise missed-trigger dispatch sequence
cannot be reconstructed from that log. Keep the PC awake for its existing
16:00 local trigger; do not change the frozen experiment or retry a refused night.

The same probe inspects 24 declared task contracts: 15 progressing, two expected
idle, three degraded, two stale and two deliberately unregistered. These are
receipt states, not a claim that all 24 registered processes are running.
Additional contracts not expanded in the main matrix:

| Task / purpose | Last observed output | Interpretation / remaining check |
|---|---|---|
| AegisAlerts | 09:07:52 UTC, 23 events | Advancing scanner; no outbound message was sent by this audit |
| AegisAnalystPanelDaily | 03:29:20, 687 rows | Fresh daily snapshot; unchanged consensus can legitimately repeat |
| AegisAnalystPull | October 8 14:16, 3,089/3,210 snapshots, zero failed | Data came from a manual pull; first registered firing remains due October 11 10:00 local |
| AegisBrainRefresh | 03:34:05, refresh complete | Scheduled ingestion output exists; recovery docs were separately ingested and retrieved |
| AegisCatchUp | 09:05:09, no starts needed | Healthy idle catch-up; no forced duplicate writer |
| AegisDailyPass | 04:55:20, 13 completed + four nothing-to-do steps | Zero errors/refusals/timeouts among 17 steps; does not clear the separate stale-source findings |
| AegisHypLabNightly | 03:32:45, three declared hypotheses | Advances research output; hypothesis count is not profitable edge |
| AegisReaderSupervisor | 09:13:49, five new page loads | Advances through reader classifications; not every page is usable content |
| OpenClaw Gateway | 09:13:53, 24 OK pages in the preceding hour | Reader proves capability despite the status CLI lacking operator scope |
| AegisTelegramAgent | 09:14:23 heartbeat | Process liveness only; outbound delivery not independently tested or triggered |
| AegisStraddleForward | Last in-window receipt October 7 15:16 | STALE missing October 8 window; observer reports no standard monthly expiry in DTE range; next valid window still needs checking |
| AegisPublicFlow / AegisResearchLane | No registered task by design | Review-dependent, intentionally unregistered; do not activate merely to remove a red row |

## Repairs and validation

- Reconciled both giant pushes and the handoff's historical publication claim.
  Merged reviewed PR #14 and conditionally deleted five incorporated branches.
  PR #13 retained with reproduced publication defects; see the Git audit.
- Recovered Codex orientation, bounded delegation skills and startup-hook
  compatibility from WIP without merging its bulk runtime records.
- Removed reviewed operational snapshots from the Git index while retaining
  local files; added ignores and a hash manifest. Financial ledgers untouched.
- Added bounded, local-only log digest with memory/window/ownership checks,
  explicit failure receipts and no vendor fallback. Actual inference succeeded;
  timestamp extraction was corrected after the live test exposed the `t` schema.
- Refreshed sanitized public receipts with the existing publisher. A local
  refresh alone does not establish production freshness.

Focused validation: **34 passed**, three existing httpx deprecation warnings,
22.10 seconds. A subsequent missing-memory test and native Windows probe repair
passed all **13 hook/digest tests in the actual scheduled-task venv** (6.42 s).
The 22 publisher tests are unchanged. Public manifest: no violations. Command:

```powershell
$env:AEGIS_IGNORE_DOTENV='1'
python -m pytest backend/tests/test_local_runtime_digest.py backend/tests/test_codex_session_hook.py backend/tests/test_publish_receipts_c15.py -q
```

Runtime command, which keeps both input and output local:

```powershell
python -m scripts.local_runtime_digest
```

`--metadata-only` needs no model. A failed model start or low memory writes an
explicit local refusal; it is not successful inference. A `run.lock` blocks
overlap and requires checking its owning PID before manual stale-lock removal.
The model sees bounded enum counts and normalized timestamps, not credentials,
article text, URLs, account identifiers or instructions embedded in logs.

Installed `AegisLocalRuntimeDigest`, daily at 13:00 PC-local, with single-instance
and five-minute limits, using the existing project `pythonw.exe`. The native
Windows memory probe avoids an undeclared psutil dependency. It refuses during
the protected IIF window, including delayed scheduled starts. Corrected actual
log run at 06:00:24 UTC: 668 tokens, 2.52 seconds, $0, 3.36 GiB available loaded,
owned process stopped. Refusals under later low memory remain explicit receipts.

The installed task itself completed at 06:15:25 UTC with exit **0**: 690 tokens,
2.56 s, $0, 4.79 GiB free loaded and owned-process cleanup confirmed. Entry is
refused from 16:40 to leave a five-minute startup/cleanup margin before IIF.
Added its receipt reader to existing progress-aware health: refusals, metadata-only
runs, absent inputs, missing inference and failed cleanup cannot read ALIVE.
The complete hook/digest/task-receipt focused set passes **204 tests** (18.29 s).

Fresh contest drills at `drills_20261009T062120Z.json`: **13/13 PASS**. Both
14:30 local contest tasks were independently observed starting on schedule.
Their final successful receipts are separate from these constructed drills:
`contest/rehearsal/` October 9 run and `contest/sheets/2026-10-09_receipt.json`.

PR #15 CI run `37894171466` reproduced two obsolete tests: one expected raw
Dow Jones feed receipts to remain tracked, and one read a historical runtime
queue from a clean checkout. The repaired tests assert the intended local/public
boundary and parse a synthetic queue from a temporary file. All 98 news chunk
tests pass. With the new unbound-start regression, the combined hook, digest,
task-receipt and news set passes **303 tests** (26.75 s, one warning).
Final deletion review then retained the two unchanged scheduler launcher
templates among the ignored logs. With explicit ignore-boundary and tracked
template regressions, the news file now passes **103 tests** (3.91 s). This
prevents a fresh checkout losing its existing reader bootstrap; generated
launchers remain local.

After the hosted allowance reset, the independent runtime reviewer found a P2:
a started model that timed out before binding its socket skipped cleanup. New
children now use the existing Windows lifetime binding; every tracked child
has an explicit cleanup result, and an unconfirmed stop cannot report success.
The reviewer approved after three synthetic lifecycle checks. Binding failure
remains a limitation: inspect the exact recorded PID before intervention; do
not infer exit cleanup happened or kill by image name. Final helper real run
`digest_20261009T171328.json`: 650 tokens, 2.28 s, $0, 5.63 GiB free loaded,
owned process stopped. Qwen failed a separate code-review calibration and is
not eligible as the independent reviewer.

Railway variable names confirm FRED, DeepSeek, Finnhub and FMP keys plus
AEGIS_DATA_DIR are configured; optional POLYGON_API_KEY is absent. Values were
redacted by the connector. GitHub VERCEL_TOKEN presence and successful deployment
steps were checked without reading its value. SQLite WAL persistence is
`DATA_DIR/aegis_pi.db`; nonempty current track-record reads exercise that path.

PR #14's full CI passed in run `37889896395`; Railway deployed `866c84c8`
(direct HTTP confirmed again at 09:35 UTC, fresh NAV and no degraded reasons).
PR #15's final source `e2a4d5d7` passed run **37911817477**: **14,029 passed,
111 skipped, 126 deselected**, 137,578 existing warnings, 1,305.36 s; frontend
build passed. PR #15 merged at 09:55:39 UTC as
`d4789050c49ea39210e0e6d433a019034fcbedce`. Main CI/deployment and the scheduled
publication receipt are verified separately from this PR check.

### Integration closeout receipts

The real AegisDataCatalog run completed with scheduler exit 0 and explicit
`publish_commit: COMMITTED`, `pushed: true`, main commit `ba135a54`. The refreshed
full health receipt `health_20261009T100141Z.json` reports 44 ALIVE, 17 STOPPED,
16 STALE, one DEAD and one UNKNOWN (CI for the new main commit was still running).
Its DataCatalog row confirms publication success and names only the memory
refusal. Publishing this corrected evidence produced `9ea43a12`; all eight
sanitized kinds passed the manifest and 5 MB checks. Neither task run wrote
broker orders or changed financial history.

The active runtime merged main with conflicts resolved only in reviewed recovery
source/docs and sanitized public copies; it did not bulk-stage its dirty data.
Two static launcher templates were restored in its index without changing their
local semantics. Owner `docs/BRIDGE.md`, `docs/PAPER_ACCOUNTS.md` and the ROI image
retained their exact pre-merge hashes. Runtime WIP retains its unique history.

Final verification command (read-only; substitute the pushed main SHA):

```powershell
gh run list --branch main --limit 3 --json databaseId,headSha,status,conclusion
python ../aegis-recovery-evidence/coordinator/verify_final_deploy.py --expected-commit <main-sha>
```

The verifier compares `/api/health/full`'s commit and NAV freshness, then checks
served receipt stamps against the committed copies on `/api/legibility/v1/brain`,
`/forecast-lab`, `/system-health`, `/api/arena/v1/latest` and
`/api/opportunities/latest`. It stores full sampled responses locally and writes
`coordinator/final_deploy_summary.json` with the actual observation time and SHA.
Passing this deployment comparison does not erase the component-level gaps above.
Final main CI is available through [the CI workflow](https://github.com/Murathanx12/Aegis-Finance/actions/workflows/ci.yml);
the source PR's [14,029-test run](https://github.com/Murathanx12/Aegis-Finance/actions/runs/37911817477)
is independently fixed evidence, not a claim that a later push already deployed.

**Verified after publication:** main run
[37915441250](https://github.com/Murathanx12/Aegis-Finance/actions/runs/37915441250)
passed 14,029 tests, 111 skipped, 126 deselected (920.52 s) and frontend build.
Railway deployment `bb279253-10a4-4a9c-8673-7c7d5657d9e3` succeeded, and the
10:25:59 UTC public probe independently confirmed commit `343a3af1`, fresh NAV
and all five expected page stamps. Durable sanitized receipt:
[deployment_verification.json](research_notes/2026-10-09/deployment_verification.json).
Brain, system health and arena are FRESH. Forecast Lab's aggregate remains
STALE despite its newest NN receipt advancing: older component evidence remains
visible. Opportunity source is October 9 03:31:21, not the October 7 copy served
before deployment. Final closeout edits only document these observations;
use current main CI/live state for their subsequent documentation commit.

Full Optimus refresh completed at closeout: 861 docs files / 862 pages, 320
Claude-memory files / 321 pages, plus existing trial, research, negative-result
and sister-repo sources. Query `CLEANUP_UNCONFIRMED` retrieves the updated
handoff via `folder:aegis-docs:HANDOFF_CODEX_2026-10-09.md#L1`.

## Completion gate and exact outstanding work

**NOT READY for the full recovery gate.**
Both pushes and digest wiring are understood; unique work is retained and safe
cleanup executed. The remaining gate is operational validation, not permission.

The integration closeout must separately record PR CI, merge, recurring
publication and deployed-content checks. Rehearsal, initial recovery ingestion
and retrieval, independent helper review, actual local inference and the NN
entry-point repair have already been verified; do not repeat their setup.

Remaining recovery checks for the next bounded session:

- Observe the next authorized sim-owner start (09:00 ET) and advancing forecast,
  plan, execution/reconciliation and grading receipts. A healthy owner tick
  before that window does not clear the previous unclean session.
- Reconcile hack6's missing LNG stop coverage/grade mismatch and hack5's
  historical-order 404 under existing paper contracts, with independent review.
  These are actionable engineering/account-state findings, not missing permission.
- Keep the PC awake for the next legitimate IIF firing; confirm a completed
  night then. October 9 is refused with no retry. The frozen launcher is not an
  ordinary repair target, and no statistical read gate is loosened.
- Verify StraddleForward's next valid in-window receipt and AnalystPull's first
  scheduled firing; classify remaining stale auxiliary collectors from their
  actual upstream evidence. PublicFlow/ResearchLane stay deliberately unregistered.
- Fix PR #13's reproduced allowlist and pin-update defects before merging it.
  Interactive frontend behavior and outbound alert delivery remain unverified;
  arrange scoped ownership without disrupting the reader or sending messages
  merely to make a status green.
- Bloomberg is externally BLOCKED on authentic Terminal WLS MEMB and separate
  rules/fill inputs. Local rehearsal success does not clear those prerequisites.

The owner's immediate actions are PC availability and authentic Terminal inputs.
Ordinary investigation, testing, reviewed repairs and normal Git integration
already have authorization. This report does not declare the whole project
healthy or start roadmap implementation.

The initial three delegated workers hit the account usage limit; an independent
review was subsequently completed for the new digest/health behavior, with its
finding repaired and rechecked. No token-dollar total is available for the
hosted session. Local smoke/digest runs consumed 2,607 tokens; the failed
review calibration consumed 200 more, all at $0 inference API cost. The existing
scheduled world digest's $0.04031 DeepSeek receipt is separate. No independent
capital-sensitive strategy audit is claimed by this recovery.
