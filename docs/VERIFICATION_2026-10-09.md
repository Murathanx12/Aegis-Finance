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
| API and persistent ledger | Railway selfless-courage, initially `6bc11c4`; main advanced to `866c84c8` | Direct HTTP `/api/health`, `/api/health/full`, OpenAPI and track record 200; 12 jobs reported healthy; all ten NAV dates October 8 | HEALTHY for sampled public API and marks; not a claim that every nested subsystem is healthy |
| Public frontend | Vercel, existing deployment | `/`, `/brain`, `/arena`, `/forecast-lab`, `/health`, `/llms.txt` all 200; expected HTML/chunks; API CORS matches origin | HEALTHY HTTP/API surface; interactive browser rendering and precise Vercel source revision not independently established |
| Public evidence pages | Image receipt publisher → FastAPI legibility and arena/opportunity routes | Seven representative API surfaces 200; takeover copies published October 7 | DEGRADED freshness; eight sanitized refreshed payloads prepared, 4,767,640 bytes; deployed verification must follow merge |
| Recurring publication | AegisDataCatalog, Windows, active WIP checkout | October 9 task rc=0; internal publish_commit REFUSED because branch is not main | FAILED publication despite green parent exit; independent publishing checkout/task correction still required |
| Main live forecasts | Railway persistent `/data/optimus/predictions.jsonl` | 736 forecasts, 431 resolved, six void; zero overdue, bad lines or duplicate IDs at probe | HEALTHY for this ledger; proposed split migration not applied; local campaign ledger is a separate dormant population |
| News ingestion/digest | PC OpenClaw reader + AegisWorldDigest | October 9 04:30 digest: 1,495 inputs, 41 forecast writes, no failed extraction calls; page log advances after 06:00 | HEALTHY advancing path with DEGRADED provenance for 262 undated inputs; model extraction is paid and explicitly budgeted |
| News decision influence | world_state + sim shadow | 38 shadow decisions; direction/size trust both zero; recent graded mean improvement negative | INTENTIONALLY OFFLINE portfolio tilt; NEWS_TILT_IN_PLAN remains false |
| Auxiliary news/events | Collectors and PC daily pass | 27/32 news sources fresh within three days; event feed 22 extractions October 8; EDGAR and earnings succeed | DEGRADED: YFinance event fetch 20/20 failures; YouTube last October 2; five news sources quiet/stale. No fabricated zeros or blanket healthy claim |
| Accrual canary / alternative inputs | Railway and local health probes | 4,004 new forecasts over three days locally; eligibility limited by score/evidence; some cloud contracts absent | DEGRADED: canary contract coverage, congress/ARK no rows and 13F August 14. Do not loosen thresholds to turn health green |
| PC paper account | PC broker read-only paper API | Fresh account/positions/orders GET: 31 positions, zero open orders, 35 fills since October 7; last fill October 8 14:30:06 | HEALTHY connectivity and actual fill history; no new order submitted in this audit |
| Fleet paper accounts | PC fleet managers; paper API only | Five accounts ACTIVE; positions 22/20/9/1/38; open orders 22/20/9/1/37; four accounts have October 7/8 fills, hack5 none in that window | DEGRADED reconciliation: hack5 historical stop lookup 404, fail-closed cooldown; quiet fills alone are not a failure. FleetDailyCheck exits 1 |
| Sim market-session owner | AegisSimSessionOwner, PC | Owner ticks advance every 30 minutes; overnight receipts correctly say outside_window; prior sim ended uncleanly October 8 14:42 | DEGRADED: previous session dead; next authorized market-window startup needs observation. Do not force an out-of-window run |
| IIF-1 | Protected AegisIIF1NightLauncher | October 8 launch permitted, but newest completed night October 7; task exit 0xC000013A | FAILED/missing completion; launcher protected from changes, 16:45–17:05 PC-local load exclusion retained; investigation must respect attended contract |
| NN research / learning | AegisNNLabNightly and learning jobs | NN task rc=2; audit bars October 7 while panel October 8 | DEGRADED; exact NN exception and next learning advance not yet certified; no unfreeze/retraining to hide it |
| Old hack1–6 Railway loops | loving-elegance persistent services | No active deployments; configuration/history identifies September 29 retirement and PC replacement | INTENTIONALLY OFFLINE; not restarted |
| Seal authority | loving-elegance, deployment `aa09c009` September 29 | ONLINE, one replica | UNKNOWN functional health beyond control-plane status; independent endpoint/output verification remains |
| Optimus | Existing local MCP and aegis-docs index | session_briefing, aegis_verified_state, brain_query and postmortem retrieval work | HEALTHY retrieval; indexed startup snapshot dated 03:32 differs from observed Git state; refreshed document indexing must be verified |
| OpenClaw browser | Existing gateway/dedicated profile, PC | Gateway/CDP and browser-status call successful; reader writes advancing logs | HEALTHY observed path; retain one operator, policy restrictions and local browser state |
| Local Qwen operations digest | Qwen2.5-7B-Instruct-Q4_K_M, loopback llama.cpp | Real sampled-log inference at 05:58:44: 454 tokens, 2.77 seconds, $0, 3.53 GiB available loaded; owned process stopped | HEALTHY on-demand inference; refuses <3 GiB before/<1 GiB after start, protected window and nonlocal endpoint; no paid fallback |
| Bloomberg rehearsal | Contest tasks and frozen contest contract | Existing October 9 drills 13/13; October 8 rehearsal successful; October 9 14:30 local run pending at initial check | BLOCKED authentic WLS MEMB export and separate live prerequisites; registration marker is not membership/fill proof |

Raw probe receipts remain local at `../aegis-recovery-evidence/coordinator/`
and `runtime/`. They include `http_probes.json`, `public_pages.json`,
`paper_broker_reads.json`, `pc_paper_read.json`, `local_health_raw.json`,
`local_model_smoke.json`, tasks/process samples and Git inventories. Do not
commit those raw records: some include account/order metadata. The local health
probe at 05:49:21 reported 43 ALIVE, 17 STOPPED, 16 STALE, one DEAD and one
REFUSED. Some process rows explicitly reused an older process probe; those
rows are not fresh independent process evidence.

## Repairs and validation

- Reconciled both giant pushes and the handoff's historical publication claim.
  Merged reviewed PR #14 and conditionally deleted four incorporated branches.
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
22.10 seconds. Public manifest validation: no violations. Command:

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

## Completion gate and exact outstanding work

**NOT READY for the full recovery gate** at this report's initial publication.
Both pushes and digest wiring are understood; unique work is retained and safe
cleanup executed. The remaining gate is operational validation, not permission.

Actionable: complete recovery PR CI and deployment checks, fix recurring public
publication ownership, verify fresh rehearsal receipts, index/retrieve this
digest, and diagnose outstanding failed schedules. Observe the next authorized
sim market window before certifying that loop. The owner need only supply
authentic Bloomberg Terminal inputs and resolve genuinely external account or
resource constraints; ordinary Git work is authorized.

All three delegated workers hit the account usage limit; their partial saved
inventories are evidence, not a completed independent adversarial review. No
token-dollar total is available for the hosted session. Local-model receipts
record their own token counts and zero inference API cost. This limitation
must remain visible before major behavior or capital-sensitive integration.
