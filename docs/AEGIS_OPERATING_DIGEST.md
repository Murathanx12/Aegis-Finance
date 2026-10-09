# AEGIS operating digest — verified 2026-10-09

This is a map of existing implementation and evidence, not a new canon,
strategy database or roadmap. Read [INDEX.md](INDEX.md), [CANON.md](CANON.md),
[AEGIS_STRATEGIC_INVARIANTS.md](AEGIS_STRATEGIC_INVARIANTS.md), the existing one-pipeline strategy,
and [CODEX_OPERATING_MODEL.md](CODEX_OPERATING_MODEL.md) for governing intent.
Observed health and unresolved recovery gates are in
[VERIFICATION_2026-10-09.md](VERIFICATION_2026-10-09.md).

## Purpose and claims

AEGIS combines a market-intelligence product with a profit-seeking research
and paper-execution system. Useful work must eventually produce explicit
decisions, measurable execution and learning. An increasing research-file
count is not a result. The product may run frozen PRODUCT_EXPERIMENT paper
contracts without claiming validated alpha; research and public skill claims
have stricter evidence requirements. The 24-month skill guardrail must not
be misread as a prohibition on authorized paper experiments.

On October 8 marks, 11/71 strategy accounts beat their own same-window SPY;
these represent nine distinct bets out of 59, with 236 controls excluded.
The leader revision_flow_v0/hack2 is +6.97% versus SPY +0.73% (+6.24 pp) over
nine sessions. Sixty accounts lag. Every strategy remains OBSERVED, the table
selects winners after the fact, and the leader lacks a random twin. This is
short paper evidence, not demonstrated edge. Historical documents promising
every book a matched twin or every forecast a grade overstate current coverage.

## Real producers, consumers and boundaries

| Connection | Implementation / contract | Observed state |
|---|---|---|
| Market and alternative inputs → stored information | FastAPI collectors and schedules; `backend/services/`; price, analyst, official-source and event ledgers under configured `DATA_DIR` | Production jobs/NAV advance; several auxiliary collectors are stale or empty |
| Browser news → corpus | `scripts/night_reader_supervisor.py`, `reader_pool.py`, `dowjones_pull.py`; dedicated OpenClaw profile and bounded source policies; local `dowjones/` and news corpus | Actual page-log timestamps advance; page-load classifications include failures, robots refusals and paywall frames, not all successful article reads |
| Corpus → interpretation | `scripts/world_digest.py`, `backend/services/world_digest.py`; timed window, dedup, extraction cache, themes and implications | October 9 04:30 UTC digest processed 1,495 items; paid extraction is explicit; 262 undated inputs remain a provenance limitation |
| Interpretation → forecasts | Digest appends typed size/direction forecasts to `predictions.jsonl`; specialist contracts and frozen versions | 41 new rows in the latest digest; duplicate/missing-input refusals visible |
| Forecasts → grades / trust | Forecast resolution and reputation; world-state grade and regret contracts | Grades exist, but digest size and direction trust are zero; legacy version exclusions must not be silently pooled into a new claim |
| Digest → next information request | `world_digest.py` read-next stage, `dowjones/read_next_adopted.jsonl` → reader queue | Dated adoption receipts exist; questions actually feed another reading cycle |
| Research → candidate library | `hyp_lab`, `llm_portfolio`, `strategy_library`, IIF-1 and the sister `Aegis module` research repository | Experimental/historical candidates and many rejections; not all candidates are eligible strategies; October 8 IIF completion missing |
| Features → expected return → portfolio plan | `scripts/sim_run.py`: `u_forecast`, `u_plan`; expected-return service, risk and sleeve contracts | Implemented with receipts; latest market-session process stopped uncleanly; next scheduled market-window restart still needs observation |
| News belief → possible portfolio tilt | `backend/services/world_state.py:plan_news_tilt`; sim `_plan_news_tilt`; shadow decision contract | Implemented connection, disabled in planning (`NEWS_TILT_IN_PLAN=False`), zero measured trust; no news-enabled order claim |
| Authorized plan → paper broker | `backend/services/pc_broker.py`, PC order reconciliation, fleet manager and sister alpha-terminal execution | Fresh independent account/position/order GETs succeed; October 7/8 fills verified; no orders submitted in this recovery |
| Fills/positions → NAV and controls | Sacred `paper_nav` path; PC/fleet snapshots; public track record; independent benchmark/control books | Ten website lanes all marked October 8; fresh broker snapshots are distinct from daily marks; one fleet historical stop lookup returns 404 and fails closed |
| Results → grading → learning | sim `u_grade`, `u_learn`, reputation, trial/negative-results ledgers, `results_voice` | Existing grading/learning outputs; freshness uneven; no strategy promotion authorized or implied by this audit |
| Local evidence → public product | `publish_receipts` deny-by-default sanitizer + manifest → committed image → FastAPI legibility routes → Next.js | Dedicated main publication checkout repaired branch ownership; actual scheduled task pushed eight sanitized copies October 9. Opportunity rebuild refused low RAM; final served source stamps are in the closeout verification receipt |
| Decisions/history → retrieval | Existing Optimus MCP; full `docs/` ingestion into `aegis-docs`; session memory and machine-verified state are separate tools | MCP works; older briefings are indexed memory, not live authority |
| PC logs → local operations summary | `scripts/local_runtime_digest.py`; bounded metadata extraction → loopback Qwen GGUF → ignored local receipt | Actual inference validated; no vendor fallback, browser tools or trading authority; model prose remains explicitly unverified |

## Deployment and ownership

Next.js 14 on Vercel consumes public FastAPI routes on Railway. Railway
`selfless-courage/Aegis-Finance` uses persistent `/data`; public receipts belong
to the deployed image, not that volume. The ledger-split code exists, but the
observed production forecast ledger is still the legacy persistent file.
An attended migration is a separate action; this recovery does not rewrite it.

The PC owns browser/news work, many research jobs and authorized paper orchestration
through Task Scheduler. Railway's six old hack loops are intentionally offline
after the September 29 fleet migration/cost retirement; PC fleet managers replace
their role. `loving-elegance/seal-authority` is still online, with narrower health
evidence than the main app. A running replica alone does not prove execution.

Bloomberg rehearsal, registration marker, strategy freeze, authentic universe,
rules and verified fills are separate facts. Drills are not live execution.
The authentic Terminal WLS MEMB export is still missing, and the gate remains
closed. Preserve `docs/ASTRA_TAKEOVER_2026-10-08_BLOOMBERG_READINESS.md` and the
existing Terminal pickup workflow; never synthesize membership or rules.

## Claude's working method and recovered lessons

Fable coordinated priorities, bounded tasks and integration decisions. Sonnet
read narrow research questions; Opus built difficult changes; a second Opus
challenged each important chunk as an adversarial investor. Fable adjudicated
against receipts, asked for repair/replay, and integrated validated results.
Source: [the September 25 review-loop amendment](ROADMAP_2026-09-25_CHUNKS_AND_THE_REVIEW_LOOP.md),
`docs/reviews/`, [Claude lessons](CLAUDE_LESSONS_2026-08.md), and the existing
[history extraction](research_notes/2026-10-08/codex_history_and_workflow.md).

Keep workers' context narrow: exact question, relevant files, existing findings,
one writer, acceptance tests and a compressed report. Deterministic scripts own
counts, Git inventories, timestamps and schema checks. Cheap validated local
inference can summarize bounded operational inputs. Builders do not certify
their own capital-sensitive behavior. A paid fallback must never silently turn
a local task into API spending. Three workers maximum plus coordinator remains
the default; token use is justified by verified output, not agent count.

The first three delegated workers hit the account usage limit; root continued
deterministic investigation. After reset, an independent reviewer audited the
local digest and its health adapter, reproduced a timeout cleanup gap, and
approved the repaired helper after synthetic regression checks. This does not
certify unrelated strategy or capital-sensitive behavior. Qwen passed real log
summarization but failed code-review calibration, so its role is operational
narration only. The concrete next-session agent workflow is in the existing
[handoff recovery addendum](HANDOFF_CODEX_2026-10-09.md).

The negative-results ledger now has 64 numbered entries, rather than the old
34-entry description in AGENTS. Load-bearing lessons include survivor-biased
free-data backtests being direction checks only; zero fetches not becoming
zero values; gates needing measured statistical power; denominator/window/twin
comparability; direction not being magnitude; and explicit ledger entries for
examination, promotion and any financial-history correction. The documented
persona/investigator experiments have narrow evidence labels, not blanket
LLM alpha. Closed rabbit holes remain closed unless the canon's reopening
conditions are met.

## What the loop actually establishes

Information collection, digest generation, forecast persistence, some grading,
reading feedback, paper order/fill history, NAV and benchmark comparison all
have concrete receipts. They are not one universally healthy synchronous loop.
News does not currently authorize portfolio tilts. The latest full sim advance,
some research schedules, all controls and every auxiliary feed have not passed
a fresh end-to-end certification. Read the verification report before claiming
readiness or starting roadmap implementation.
