# CLAUDE.md — Aegis Finance

## Mission (amended 2026-08-15 — full text in `docs/OPTIMUS_OBJECTIVE.md` §0)

> Build a **self-improving investment intelligence system** whose objective is
> maximising real-world **portfolio utility** — risk-adjusted or deliberately
> risk-seeking by declared choice — using numerical models, LLM reasoning,
> internet-scale information, observed expert behaviour, simulation, and
> continual outcome feedback.

Three deliverables from one system: Murat's own capital · a public open-source
tool others run at *their* utility function · an HKU paper if a novel and
defensible result emerges.

Five rules that follow, and that override habits formed before them:

1. **Investing is a sequential learning problem**, not a bag of independent
   hypothesis tests. The question is *"given what was knowable at t, what action,
   what alternative, what happened, why, and what should change?"*
2. **Explaining a winner afterwards is trivial; finding precursors observable
   beforehand is the research problem.** Every mechanism carries an executable
   precursor that is tested on foreign slices with its parent barred.
3. **The objective is terminal wealth under a declared utility, not
   classification accuracy or raw return.** Every ranked comparison names the
   objective it was computed under. One brain, several personalities
   (preservation / balanced / aggressive / extreme growth).
4. **Study losers as hard as winners** — the informative unit is *winner vs
   matched loser*, never a gallery of survivors.
5. **Maximise information per dollar, not minimise API calls.** Score
   experiments as `P(changes the roadmap) × value of decision improved − cost`.

**The methodology is the guardrail, not the mission.** Pre-registration, MDE,
corpses and matched controls exist to stop a self-learning machine from learning
nonsense — not to conclude that nothing works. Correspondingly: a negative
result requires evidence just as a positive one does, and **a global negative
does not answer a conditional question that was never asked** (scope-aware
verdicts, `docs/HANDOFF_2026-08-16_BRAIN_TO_BUILDER.md` §2).

## READ `docs/INDEX.md` FIRST (2026-08-28) — and the VISION file

268 docs, 69 roadmaps/handoffs. `docs/INDEX.md` tiers them; a session loads
TIER 0 (`AEGIS_STRATEGIC_INVARIANTS.md`,
`AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md`, `OPTIMUS_OBJECTIVE.md` §0)
and the ONE current TIER 1 roadmap, and retrieves the rest by question. The
VISION file holds Murat's intent verbatim — whole-market news, Asia first,
coverage normalisation, situational not universal, instinct as a typed
hypothesis, the pre-open prediction book and the discovery-failure autopsy —
because it was said four times in a week and lost each time.

## THE NORTH STAR IS A SEPARATE FILE (adopted 2026-08-26)

`docs/AEGIS_STRATEGIC_INVARIANTS.md` — sixteen points, read it BEFORE this
file's roadmap sections and before any handoff. It changes perhaps twice a year;
the roadmap churns weekly, and mixing the two is how six months of strategic
intent leaked between sessions while every individual commit stayed excellent.

The lane list it governs is
`docs/ROADMAP_2026-08-26_HUMAN_HEURISTICS_AND_FAST_RESEARCH.md`, and **gates
outrank dates**: several agents can do a month of ordinary engineering in a
session, so an item is blocked by its dependency and its evidence, never by a
calendar. Exactly two things cannot be parallelised — time-dependent prospective
evidence, and statistical information that does not exist yet.

Three points overturn habits this file taught earlier:

- **The mega-cap is a SENSOR, not the trade.** NVIDIA tells us what world we are
  in; it is rarely the best instrument for monetising that world.
- **Size does not bound the move.** Our own chain implied **5.10% in one
  session** for a ~$5T company. The defensible version of "small companies have
  more room" is `STATE_CHANGE_ELASTICITY`, not market cap.
- **Human intuition GENERATES hypotheses; data ADJUDICATES them.** Every
  intuition is owed one question — *what observation would separate this from
  ordinary factor beta?* If nothing would, it is not a hypothesis yet.

And a rule earned the hard way the same day, at my own expense: **absence of a
local object is not evidence of absence.** I reported both of those documents as
never committed, having run `git cat-file` against unfetched refs and looked at
the wrong path. Fetch first, then check, and check the real path.

## SESSION START PROTOCOL (enforced 2026-08-29 — the cheap fix for lost work)

1. `session_briefing()` + `aegis_verified_state()` (Optimus MCP) — before reading code.
2. Before proposing ANY research: `brain_query` + `aegis_postmortems`. On 29 Aug a
   session spent an hour re-deriving TRIAL-LLM-AMNESIA-1 by grepping, while the
   brain held "Can you tell an LLM to forget? — measured, 2026-08-08" with six
   pre-registered predictions. Nothing was lost; the protocol was not run.
3. Read `docs/INDEX.md` TIER 0 + the ONE TIER 1 roadmap. Dated handoffs are in
   `docs/archive/` and are a diary, not a source of truth.
4. Before any sizing / stop / cap change: print the worst case in dollars for the
   largest admissible book — `n names × notional% × stop%` and `Σ|notional| / equity`.
   On 28 Aug twelve names × 25% = 300% gross and a 3% stop cost −9%; the
   "fix" that widened the stop raised the worst case to −24%. Wider stops on
   uncapped gross are bigger losses (`docs/ROADMAP_2026-08-29_WEEKEND_TO_MONDAY.md` §1).
5. Test fixtures never encode a calendar moment: a literal option expiry that
   was "next week" fails the day after it passes. Derive dates from `today`.
6. **Never `taskkill /F /IM python.exe` (or any kill-by-image-name).** On
   2026-09-06 one agent did it to stop its own job and killed two other agents'
   jobs, a running test suite, ~1,676 already-billed LLM extractions, and the
   Optimus MCP server for the rest of the session. Kill by PID, from a PID you
   wrote down when you started the process, or don't kill.

The long-form lessons behind this file (the farm's seven lessons, the feature
list, layout, test table, retired lab) moved verbatim to
`docs/CLAUDE_LESSONS_2026-08.md` on 2026-08-29. They are still canon.

## FOUR REPOSITORIES, AND WHICH ONE HOLDS WHAT (2026-08-29)

| repo (local) | GitHub | holds | its continuity file |
|---|---|---|---|
| `aegis-finance` (this) | `Murathanx12/Aegis-Finance` | strategic brain, research, farm, website backend, canon | `docs/INDEX.md` → TIER 0 + one TIER 1 roadmap |
| `aegis-alpha-terminal` | `Murathanx12/investing-bot-test-` | EXECUTION brain: six paper books, ledger, arms, corpus, Railway loops | `docs/HANDOFF.md`, `docs/SESSION_*` |
| `optimus` | `Murathanx12/Optimus` | the memory: MCP brain over `brain/index.db` (395 pages after the 29 Aug repair); ingests both repos' `docs/` + session memory | `CLAUDE.md` there; `tools/refresh_aegis.py` lists sources |
| `Aegis module` | (local; git) | the 2026-07/08 investor-brain module: TRIALS, verdicts (AMNESIA, ANALYST-IBES, ARENA1), `INTEGRATION.md` one-way firewall | ingested by Optimus as `aegis-module-*` |

Commits move between repos only by hand. A hash quoted in a handoff belongs to
the repo the handoff lives in. `docs/HANDOFF.md` does NOT exist here, on purpose.


This repo is **Aegis-Finance** (`github.com/Murathanx12/Aegis-Finance`, public):
the research programme, the farm, the website, the brain.

The **Alpaca hackathon agent is a SEPARATE repo** — `aegis-alpha-terminal` locally,
`github.com/Murathanx12/investing-bot-test-` on GitHub, also public. It holds the
paper books, the ledger, the arms, the strategy contracts and
**`docs/HANDOFF.md`**, which is the session-continuity file for competition work.

`docs/HANDOFF.md` does NOT exist in Aegis-Finance and is not supposed to. A
2026-08-27 reviewer looked for it here, 404'd, could not see the other repo
through the connected account, and concluded the newest work was outside version
control. It was not — it was one repo over, public, and pushed. The observation
was accurate and the inference was wrong, which is the same shape as
[[feedback-verify-the-persistence-claim]]: **absence of a local object is not
evidence of absence.** The cheap fix is this paragraph, so nobody spends the
hour again.

Commits move between the two only by hand. A commit hash quoted in a handoff
belongs to whichever repo that handoff lives in.

**Where the trading loop RUNS (2026-08-28):** Railway project `loving-elegance`,
one service per account role (`aat-loop-<role>`), volume at `/app/state`,
image from the terminal repo's `Dockerfile`. The laptop no longer has to be
on. Railway project `selfless-courage` / `Aegis-Finance` is THIS repo's website
backend and places no orders. `railway logs --service aat-loop-<role>` is the
heartbeat; a laptop PID is not.

## THE BOTTLENECK (diagnosed 2026-08-24 — `docs/ROADMAP_2026-08-24_CONNECT_THE_BRAIN.md`)

> All ten arena books declare `selection: composite_top_k` over ONE signal.
> They differ in **portfolio treatment**, not in **alpha source**.

`COMPOSITE_WEIGHTS` is momentum 1.0 + multifactor 1.0 (itself
momentum+insider+revisions) + four 0.5s, and coverage is `{"1": 206, "6": 1}` —
99.5% of names carry exactly one factor, 12-1 momentum. That is why five months
of guardrails did not move the demonstrated edge off 0%.

**So: a new mechanism arrives as its own `PRODUCT_EXPERIMENT` book, never as a
weight in `arena_composite`.** Folding it in hides the only thing being tested —
whether its errors are different errors. A learned router comes *after* several
independent selectors exist, not before.

## THREE LICENCES (adopted 2026-08-23 — `docs/ROADMAP_2026-08-23_PROFIT_FIRST.md`)

> **Research rigour determines what Aegis is allowed to CLAIM. It must not
> determine what Aegis is allowed to TEST in paper.**

One evidence standard had drifted into governing everything, and five months in
the demonstrated edge is 0% partly because every gate that *could* block work
*was* blocking work. There are now three licences; every artefact names one.

| Licence | Permits | Required first |
|---|---|---|
| `PRODUCT_EXPERIMENT` | internal simulation + external **PAPER** brokerage | a frozen strategy contract **before the first decision**: policy hash, timestamp, inputs, costs, fill convention, objective. **No significance gate, no 24-month floor, no preregistration.** |
| `CAPITAL_CANDIDATE` | candidacy for real money | matured forward evidence, realistic costs, calibration, utility improvement, drawdown/ruin bounds. Promotion stays **attended**. |
| `RESEARCH_CLAIM` | "this is alpha" — paper, public skill claim | full preregistration, MDE, multiplicity control, matched controls, holdout. Every standing evidence rule binds. |

**Does NOT relax:** PIT discipline · frozen information states · realistic
costs · immutable policy versions · outcome provenance · no training on future
information · **no LLM authority over real capital** · no backfilled forward
evidence · no mutation of seeded book histories.

**Amended in scope, not repealed:** the 24-month skill floor and CANON §6
("if it isn't pre-registered, it didn't happen") govern **claims**. A
`PRODUCT_EXPERIMENT` needs a frozen strategy contract instead — weaker, still
tamper-evident.

## EXPLORE DIRTY, PROMOTE CLEAN (adopted 2026-08-24 — Murat's review)

The three licences stand. What changes is how the FIRST one is treated
culturally. The default objective moves from *"produce a defensible research
verdict"* to **"find, test and paper-trade mechanisms that increase terminal
wealth."**

`PRODUCT_EXPERIMENT` exploration **may** be post-hoc, may try twenty variants,
may use LLM-generated hypotheses, may discover something after looking at the
data, and needs **no** significance gate, MDE or multiplicity control. Four
things never relax, and they are enforced in code rather than by intention:

1. no information acted on before it was public;
2. no target leakage;
3. costs are never omitted (`portfolio_farm.Policy` REFUSES zero costs unless
   `zero_cost_diagnostic=True`, and the flag travels onto every result row);
4. once a candidate enters forward paper, its version is **frozen**.

`CAPITAL_CANDIDATE` and `RESEARCH_CLAIM` keep every stricter gate.

**Stop over-closing ideas.** The word `STOP` is retired from exploratory work:

`FAILED_VARIANT` → `DEPRIORITIZED` → `RETIRED_FROM_CURRENT_SEARCH`

and **`MECHANISM_REJECTED`** is reserved for genuinely broad evidence. A failed
implementation closes that implementation. GRAPH-MIDCAP closed shared-broker
co-coverage, not financial graphs. REVISION-FORECASTER closed the
revision-mediated route, not management text. RELATIVE-VALUE-v1 closed seven
features and a small MLP, not relative substitution.

**Every handoff opens with a RESULTS SCOREBOARD**, before code or test counts:
best historical net strategy vs the market · best forward paper strategy ·
independent selector count · farm candidates tested/promoted · new actionable
finding · external execution drag · LLM spend and cost per gradeable output. A
session that ships thirty engineering changes and moves none of them says
**RESULT IMPROVEMENT: NONE** in its first paragraph.

**New guards are no longer roadmap work by default.** Add one when an actual
failure shows it is necessary.

## THE LLM PROVIDER IS DEEPSEEK, AND IT IS THE ONLY ONE

**There is no Anthropic key, no OpenAI key, no other provider. Do not plan
around one, do not propose migrating to one, and do not read
`llm_analyzer._get_provider` as evidence that Claude is primary.**

That function is written `if _ANTHROPIC_API_KEY: return "claude"` first, and
`.env` carries an `ANTHROPIC_API_KEY=` line with an **empty value**. It reads as
configured and is not — the branch tests truthiness — so it has always returned
`deepseek`. **Nothing was ever broken by this and no call was lost**: DeepSeek
has been the live provider throughout, `/api/health/full` reports it, and the
occasional Chinese reply is itself proof the model was answering. The only cost
was to a reader who believed the first branch was live. That cost was paid on
2026-08-24; it does not need paying again.

`llm_analyzer.SOLE_PROVISIONED_PROVIDER` and `provider_status()` now declare it,
`llm_usage()["providers"]` surfaces it, and `test_llm_provider_declaration.py`
fails if the resolved provider ever stops matching the declaration.

**What follows from DeepSeek being the only provider:**

- **Every guard belongs on the DeepSeek path.** A guard applied only to the
  dormant Claude branch protects nothing. Pinned by test.
- **`deepseek-chat` code-switches to Chinese** when the system prompt does not
  name an output language. `_LANGUAGE_PIN` is appended centrally in `_call_llm`;
  a reply that is >10% non-Latin script is **refused** (not repaired, not
  retried), counted per provider, and surfaced on `llm_usage()`. Do not fix this
  at a call site — `explain_move.py` did, and every other caller inherited the
  bug for months.
- **The Claude branch stays.** It is tested and costs nothing, and it is the
  migration path if a key ever exists. It is DORMANT, not primary.

## NEVER MOVE `.env` TO REPRODUCE CI

Use `AEGIS_IGNORE_DOTENV=1 python -m pytest backend/tests/ -m "not slow"`.

The old recipe moved `.env` aside inside a subshell with an EXIT trap. On
2026-08-24 the subshell died before its trap ran and the machine lost every key
on it until someone noticed. The handoff warned about exactly that failure in
the same session, and the warning did not prevent it — because a warning cannot.
`backend/config.py` now gates `load_dotenv` on the env var instead.

## Commands

```bash
# Backend
cd backend && pip install -r requirements.txt && cd ..
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev

# Run fast backend tests (~4090 tests; OFFLINE + un-hangable; ~2-7 min on the
# dev machine, measured 2026-08-15 — the old "~20 min" figure predates fixture
# work. The spread is real: the suite competes with whatever else is running.)
# The fast suite is network-BLOCKED (backend/tests/conftest.py) and has a hard
# per-test timeout (pytest.ini). Any network call in a unit test is a bug →
# mark it `slow` or mock it.
#
# TWO CAVEATS, both paid for on 2026-08-12 when the suite hung mid-swarm:
#  1. The block covers Python sockets AND curl_cffi. It did NOT cover curl_cffi
#     until then — which is yfinance's transport, so every yfinance call in the
#     suite was unguarded. `test_network_guard.py` pins both transports; if a
#     dependency moves to a third (a new CFFI/Rust binding), that guard must be
#     extended or this claim silently becomes false again.
#  2. `pytest-timeout` is in requirements but CAN BE ABSENT locally, and when it
#     is, pytest.ini's `timeout` is inert with only a config warning. Verify it
#     is installed before trusting "un-hangable": python -c "import pytest_timeout"
python -m pytest backend/tests/ -v -m "not slow"

# Run ALL backend tests (~25 min, slow tests need network)
python -m pytest backend/tests/ -v

# Portfolio farm — hundreds of strategies over one replayed history (attended)
python -m scripts.portfolio_farm_run --preset holding --start 2013 --end 2024
python -m scripts.portfolio_farm_run --preset breadth    # k=3..50, the open question
python -m scripts.portfolio_farm_run --preset signals    # every signal at one holding period

# Reconcile LLM spend against the PROVIDER's balance (not our telemetry)
python -m scripts.llm_cost_audit --snapshot

# Run autonomous R&D lab (overnight, opus model)
python lab/rd_loop.py --cycles 60 --model opus

# Build frontend (catches type errors)
cd frontend && npx next build

# Train crash model (offline, ~5-10 min)
python -m engine.training.train_crash_model

# Docker (full stack)
docker compose up --build
```

## Discipline Skills (.claude/skills/)

Five project skills codify the disciplines that keep getting skipped — invoke
them at their trigger points, don't re-derive the procedure:

| Skill | Trigger |
|---|---|
| `verify-prod-after-deploy` | after every push that deploys (CI gate → commit flip → exercise the changed surface live) |
| `lane-integrity-check` | before/after any change near lanes, lane YAMLs, rebalance, or NAV tables |
| `seed-a-lane` | any new paper lane (attended, env-gated; human flips flags) |
| `pre-register-trial` | before any new signal/strategy/hypothesis accrues or is evaluated on data |
| `silent-fragility-audit` | after adding collectors/fetchers/loaders/try-except; "audit X" requests |

## Rules

### DO
- Put all parameters in `backend/config.py` — never hardcode in service files
- Use `np.random.default_rng(seed)` for reproducibility
- Handle missing libraries with `try/except ImportError` + fallback
- Cache aggressively (1hr TTL for prices, 24hr for historical)
- Return proper HTTP error codes from routers (404, 422, 500)
- Add type hints to all function signatures
- Keep services stateless — no mutable global state except cache
- Use purged CV with embargo for all ML validation
- Use walk-forward temporal splits (never random k-fold)
- Use `SimpleImputer(strategy="median")` for sklearn pipelines that can't handle NaN
- Enforce monotonicity on multi-horizon predictions (3m ≤ 6m ≤ 12m)
- Give every new module a caller, or classify it in
  `backend/services/signal_reachability.py` — the suite fails on an unreachable,
  unclassified module. A collector that feeds nobody must be a red suite, not a
  discovery three weeks later (`detectability_gate` was one for two days)
- Put every headline number in a receipt. `corr = 0.516` lived in prose only and
  turned out to be a filtered subset nobody had named

- A GATE THAT CANNOT GO GREEN IS A BROKEN GATE, not a strict one.
  `monday_gate_check` reported `seed migration -> book-v1: 0/9 stamped [FAIL]`
  for weeks because `engine.status()` never emitted `fingerprint_scheme` — the
  count could only ever be 0/N, and the seeds' real state was invisible rather
  than failing. A guard DERIVES its inputs or REFUSES: when no book carries the
  key it now reports CANNOT DETERMINE. A permanent red line beside nine real
  checks teaches the reader to skim red lines

### DO NOT
- Use `fillna(0)` on feature matrices — LightGBM handles NaN natively; sklearn paths use SimpleImputer
- Use `np.random.seed()` (legacy API)
- Hardcode file paths — use `Path(__file__).parent`
- Store portfolio state server-side — portfolio lives in browser localStorage
- Skip the Merton jump compensator in Monte Carlo
- Add a database — this is a stateless API with in-memory cache
- Use standard k-fold CV on time-series data
- Use basic GBM without fat-tailed innovations for tail risk estimation
- Evaluate calibration metrics on the same data used to fit the calibrator
