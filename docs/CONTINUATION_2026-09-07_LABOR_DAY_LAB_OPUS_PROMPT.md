# LABOR DAY LAB — 2026-09-07 — training, made-up scenarios, attacking the project, connection verification

**Context.** US markets are closed Monday 2026-09-07 (Labor Day). The fleet
re-arms at Tuesday 2026-09-08's open per
`aegis-alpha-terminal/docs/RUNBOOK_2026-09-08_REARM.md`. That buys one more
day of lab time. Murat's instruction: *continue training and improving on
backtests, made-up scenario testing, attacking the project and making it more
fail-proof, API and connection verification.*

**Read first:** `BUILD_CONTINUATION_2026-09-06b.md` (the beta-matched answer
and the neural shadow), `REVIEW_2026-09-06_FABLE51_ON_THE_CONTINUATION.md`,
`ROADMAP_2026-09-04_PROFIT_ENGINE.md` §6, `DECISIONS_2026-09-05_PLAIN_LANGUAGE.md`.
If the Optimus MCP is down, read `docs/INDEX.md` TIER 0 and proceed.

## Rules
As `CONTINUATION_2026-09-06_OPUS_PROMPT.md` §1. **LLM cap $6 total**: ≤ $5 for
lane B's fantasy stress exams (DeepSeek), ≤ $1 for lane D's live probes (one
tiny call per LLM provider). No Anthropic/Claude API. Never kill a process by
image name. Either the lab runner or a standalone job, never both. Nothing
pushed, sealed, ordered, deployed or changed on Railway; **read-only calls to
the venue and Railway are allowed for lane D** (account, clock, positions,
service status). Commit locally on `main` per item; fast suite and
`python run_tests.py` at the end. Receipts under
`backend/data/optimus/labor_day_lab_2026-09-07/`, one per item, provenance
stamped (argv, config, inputs opened).

Four lanes, four coordinator-owned agents, disjoint files. Order inside each
lane is priority order; a lane that finishes early takes the next unclaimed
item in the list, never a peer's file.

## Lane A — training and backtests (finance, $0)

A1. **Shadow grading harness for two selectors.** `lgbm_clf` and the frozen
`nn_pre_causal` ensemble graded nightly by one grader against SPY TR **and**
the beta-matched benchmark, with the paired difference between the two
selectors as the primary series (the "different errors" question). Receipt
every night even when a vintage is missing.
A2. **Retraining cadence study.** Same champion pipeline, refit monthly vs
quarterly vs annually vs frozen-once, walk-forward 2004-2024 on the floored
long panel; after-cost TW, DSR over the 4-cell family, era table. The
question: does refitting more often buy anything after costs, or is the
model's information static?
A3. **CPCV/PBO over the incumbent family.** `learner/inference.cpcv_splits`
+ `pbo` on the 32-cell learner grid and the 40-cell neural family; report
the PBO and the out-of-sample path distribution, not one path.
A4. **Holding-period × selector cross.** For lgbm_clf and nn_pre_causal, hold
1/3/6/12 months with hysteresis (top-50 in, out below rank 100); the
horizon a selector's edge actually lives at, with costs; era table.

## Lane B — made-up scenario testing (finance, ≤ $5)

B1. **Synthetic known-answer battery for the WHOLE research machine** ($0).
Build a synthetic 1999-2024 panel with (i) a planted linear edge, (ii) a
planted regime-conditional edge, (iii) a planted graph-propagation edge
(customer return → supplier next month), (iv) a null world. Run
`dataset → learner → inference → evidence_memory → allocator` end to end on
each. Required: the machine recovers (i)-(iii) with correct sign and
family-corrected p < 0.05, and reports NOISE on (iv); the evidence memory's
states end where they should; the allocator parks the null world in the
benchmark. Any miss is a defect in the machine, not the world. Test-pinned.
B2. **Fantasy stress exams** (≤ $5, DeepSeek via the spend gate). Using the
era-replay rewriter machinery (`alpha/transpose.py`, sealed entity maps): 40
fictional company situations, each in **two versions that differ by one
causal fact** (FDA rejection vs approval; sanction on vs off; funding
withdrawn vs extended; supply shock vs relief; guidance cut vs raise;
customer loss vs win). The decider returns `p_up / exp_return / downside /
confidence`. Grade **monotonicity**: the forecast must move the economically
correct way between the pair; report the share of pairs that move correctly,
the mean magnitude, the canary rate, and cost. Rank-only; no return labels
are synthetic (this exam has no returns — it tests reasoning direction).
B3. **Scenario bridge v2 field coverage** ($0). Re-run the 20 sealed
scenarios' retrieval with the 8-K tape + `companyworld_v1` edges +
CIK link now on disk; report maps-to-nothing (was 40.0%) and which fields
moved UNMAPPABLE → PROXY/DIRECT. Grades unchanged by construction.

## Lane C — attacking the project (both repos, $0)

C1. **Fault injection on the fleet loop** (terminal, `AAT_TEST_MODE=1`, mock
venue): venue 5xx on entry / on exit / on stop placement; stale seal (sha
mismatch); seal missing a contract; torn ledger line; clock skew ±20 min;
empty corpus; a name halted mid-session; a partial fill; a gap through the
stop at the open. For each: the loop must **fail closed with a receipt that
names the fault**, never trim on a data gap, never re-enter after an exit,
never place a stop with a colliding id. Each case a test; each failure a
fix; a table in the build doc.
C2. **Adversarial review of B2 exits with synthetic price paths**: 200
random 21-session paths per profile through `exits.evaluate`; assert no
close before min hold without a typed reason; assert the stop fires at the
profile width and is booked HARD_RISK_LIMIT; assert hack2's contract is not
EVENT defaults (or document exactly what it is).
C3. **Silent-fragility sweep** (`silent-fragility-audit` skill) over every
module touched since 2026-09-04 in both repos: collectors, receipt writers,
the learning report, the autopsy, the allocator, `night_lab`/`weekend_lab`
runners. Anything that can run green and do nothing gets a refusal + test.
C4. **Secrets and surface audit**: grep every receipt, log, doc and test
fixture committed since 2026-09-01 for key-shaped strings; verify the
seal-authority public domain is GET/HEAD-only (POST → 501) and serves only
the books directory; confirm `.env.bak.*` is ignored and unread. Receipt.

## Lane D — API and connection verification (both repos, ≤ $1)

D1. **`scripts/connection_check.py`** (finance) + the terminal equivalent:
one read-only probe per provider, status / latency / entitlement class /
quota hint, **never printing a key**: Alpaca ×6 paper accounts (`/v2/account`,
`/v2/clock`, `/v2/positions`), Alpaca data (bars, news, options chain,
screener), Finnhub (free-tier 403 map), FRED, DeepSeek (balance endpoint),
NVIDIA NIM (model list + one 5-token completion), HF router (one 5-token
call), Featherless (one call; is it in `fleet.SECRETS`?), OpenAI gpt-5-nano
(one 5-token call, `reasoning_effort="minimal"`), Polygon, FMP (+ budget
state), EODHD, Alpha Vantage, WRDS (psycopg2 connect; entitlement map),
GDELT, EDGAR (UA + one submissions call), Kalshi, Polymarket, CBOE, the
website `/api/health/full` (use `section=summary`-equivalent slicing), the
seal-authority GET, and `railway status` for every service (Online / Failed
/ Sleeping; `aat-loop-staging` should read Failed — say so). Output: one
receipt + a Markdown table; a provider that fails names the failure class
(auth / quota / network / entitlement / dead key). This becomes a nightly
job in `fleet_health` and the finance scheduler.
D2. **Key inventory reconciliation**: every env var in both `.env` files
(names only) → read-in-code? → reachable caller? → probe result. Dead keys
listed for Murat to delete or wire. Confirm the revoked mirror/arena Alpaca
keys read as `auth` failures and are not used anywhere live.
D3. **Runbook check for Tuesday**: confirm the fleet's `--manage-only`
state per role from Railway variables (read-only), confirm `AAT_MANDATE_END_UTC`
is 2027-12-31 on every service, and list exactly which variables the
Tuesday re-arm flips. Append to the runbook.

## Deliverable
`docs/BUILD_LABOR_DAY_LAB_2026-09-07.md`, ≤ 2 pages, RESULTS SCOREBOARD
first (lane by lane: what moved, one number and one null each); the
connection table; the fault-injection table; the known-answer battery
result; the monotonicity share; claims for Fable to attack (5-10); test
counts; LLM spend to the cent. Update roadmap §6, session memory,
`MEMORY.md` (one line), `refresh_aegis.py` if reachable.
