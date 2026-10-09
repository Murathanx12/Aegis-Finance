# Codex operating model

Codex coordinates Aegis through the existing repository, Optimus and guarded
OpenClaw surfaces. Claude instructions and historical files remain sources of
knowledge. They are preserved; runtime settings are configured separately.
The owner's Oct 9 clarification makes Codex the target of all new integration
work. Claude is already integrated; do not repeat its setup.

## Start and finish

1. Call Optimus `session_briefing` and `aegis_verified_state(section="summary")`.
   The briefing is a dated memory snapshot. Its stale statements do not override
   fresh receipts or the owner's later instructions. If MCP fails, say so and
   use the local files and public health endpoint; do not invent a healthy result.
2. Read `AGENTS.md`, `CLAUDE.md`, `docs/INDEX.md` and the current pickup note.
   Follow INDEX's canonical tiers; retrieve historical details by question.
   Before research, query Optimus and the trial/negative-result ledgers.
3. Fetch refs, inspect branch/HEAD and summarize dirty paths. Active scheduled
   writers produce uncommitted data. Do not reset them or treat checkout mtime
   as evidence freshness. Use embedded event dates and the appropriate market
   session, with UTC and exchange timezone explicit.
4. Write a bounded work queue: owner, files, observable acceptance, dependency,
   result and next step. Complete the useful authorized work before asking for
   missing external input. Keep task authorization separate from technical ability.
5. Finish with actual commands/outcomes, changed paths, unresolved inputs and a
   resumable next step. Handoffs start with the generated results-voice block
   required by CLAUDE.md. Preserve its evidence labels and dated receipt scope.
6. Ingest the sanitized note using the existing Optimus notes channel, then
   retrieve it via `brain_query`. A successful ingest alone does not establish
   discoverability. No private transcripts or identity records in public Git.

## Spend effort where it changes the decision

| Work | Default allocation | Acceptance |
|---|---|---|
| File inventory, freshness, exact commands | Deterministic code; small worker if needed | Receipt content and exit status |
| Focused history, docs, routine source checks | Small worker, e.g. available Luna | Cited paths, explicit read scope, compact answer |
| Integration or behavior fix | Capable builder, e.g. Sol; independent reviewer | Reproduction, focused tests, actual caller exercised |
| Strategy, sizing, holding periods, claim validity | Strong researcher + skeptic + integrator; independent replay | Declared utility, PIT/cost controls, frozen versions and evidence |
| Bulk extraction/classification | Local Qwen if measured fit and resources permit; existing provisioned provider when separately justified | Small representative quality/cost sample first |

These are capability choices, not promises about model price or availability.
October 9 validation limits local Qwen to bounded operational metadata summaries:
real inference and cleanup passed, but code-review calibration missed an
explicit paid fallback. It must not be the independent code/security reviewer.
The installed `AegisLocalRuntimeDigest` task runs at 13:00 PC-local and retains
inputs/outputs locally; refusal never triggers a paid provider.
Do not inherit the full conversation into routine workers. Supply the objective,
relevant files, baseline, allowed writes, constraints, and expected output.
Keep results short, retain detailed evidence in files, and reuse workers with
fresh bounded tasks. One writer owns each file; the coordinator integrates.

No nested swarm by default. Use at most three workers alongside the coordinator.
Use the same model for simple work only if a smaller capable one is unavailable.
Do not run duplicate full suites, refreshes, browser owners or paper writers.
Run targeted checks for the change; run the repository's full required suite
before a commit that requires it. Do not claim a full suite from partial tests.

Bound output before it reaches the conversation. Scope `git diff --check` to
the task's files on this runtime-dirty tree; an unscoped check can print
megabytes of unrelated generated rows. Summarize counts and selected failures.
Do not use paid model turns to test deterministic hooks or browser status.

## Existing integration map

- `.codex/config.toml`: project MCP registrations. Optimus already works.
- `.codex/hooks.json`: Codex hook registration; `.codex/hooks/session_start.py`
  adapts `scripts/session_state.py` without changing the Claude-compatible source.
  The imported Vercel/explanatory runtime hooks are disabled in Codex because
  their commands fail under this Windows shell; their plugin skills remain.
- `.agents/skills/`: project skills shared with Codex. Original `.claude/skills/`
  remain untouched. Add focused guidance rather than copying the full canon.
- `../optimus/optimus.py ingest --notes <repo>/docs --project aegis-docs`:
  existing deterministic notes ingestion. Use the Optimus virtual environment.
  Pass the full docs directory: ingesting one file under that existing slug
  would replace its shared overview with a one-file index.
- `../optimus/tools/refresh_aegis.py`: broader end-of-session refresh when needed;
  it ingests the main docs tree already. No second memory database is needed.
- `backend/services/openclaw_client.py`: guarded model/browser interface.
  `browser_policy.py`, `gateway_repair.py` and `llama_server.py` own policy and
  lifecycle. See the PC automation skill before using them.

## Authority and operational constraints

The Oct 8 owner request authorizes setup, repairs, bounded delegation and
task-related PC/login/free-signup automation. Reuse that authorization; do not
ask for the same permission again. It does not choose an unrelated service,
authorize a payment or message, or grant real-money trading authority.

Preserve `.claude/`, original Claude caches and private history. Change Codex
runtime state only in Codex configuration. Do not put config backups containing
credentials in the repository. Print selected nonsecret fields, never raw secrets.

Respect scheduled ownership. Do not add resource load during the protected
16:45-17:05 PC-local IIF launch window. Stop only a verified owned PID. A model
configured in JSON is not a model proven reachable, and a live process with no
advancing output is not a healthy service.
