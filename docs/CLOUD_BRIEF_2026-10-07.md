# CLOUD BRIEF 2026-10-07 v2 — Claude Code Desktop (Opus 5.5) session with LOCAL file access, on its own branches

Paste the block under "PROMPT" into Claude Code Desktop with Opus 5.5 selected, repository
`Murathanx12/Aegis-Finance`, local folder `C:\Users\mrthn\aegis-finance`. v2 replaces the earlier cloud-only
brief: the session now has the local checkout, the local data under `backend/data/`, the sibling repos
`C:\Users\mrthn\optimus` (Murathanx12/Optimus) and `C:\Users\mrthn\aegis-alpha-terminal`, the Optimus MCP, and
the `exa` MCP. It runs on the SAME machine as the owner's manager session (Fable), so it shares memory, the
scheduled jobs and the working tree discipline below.

---

## PROMPT

You are a full Claude Opus 5.5 engineering and research session on `Murathanx12/Aegis-Finance`, with the
local checkout at `C:\Users\mrthn\aegis-finance` (branch `main` = `92f147f6…`, the merged V1 Beta batch, gate
green: 13,693 backend + 106 lab tests, frontend 0/0/0). The repo still says RESULT IMPROVEMENT: NONE; do not
turn engineering progress into an investment-performance claim. You may run subagents on disjoint files.
Budget: the owner has ~$200 of Claude Code credit for this session; spend it on finished, reviewable,
high-EV work, not on rereading the repo. Give every subagent a narrow brief and a small file set.

### 0. Where you are, and how you share the machine
- Another Claude session (the manager, "Fable") runs on this PC with its own agents, scheduled jobs and the
  live paper loop. Coordinate by RULE, not by chat:
  1. Create `backend/data/optimus/local_pc/CLOUD_SESSION_LOCK.json` at start `{started_utc, branch, heavy_job: null}`
     and update `heavy_job` before/after any job over ~1 GB RAM (a CRSP board, a full suite, a `next build`);
     delete the file at the end. The manager's agents read it and will not start a heavy job while it names one.
  2. Before any heavy job: free RAM must be ≥ 6 GB
     (`powershell -NoProfile -Command "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB"`);
     if a file `backend/data/optimus/local_pc/suite/RUNNING` exists, the manager's full suite is running: wait.
     Never two heavy jobs at once. Never between 21:00 and 04:30 HKT for anything over 2 GB (the US-session
     sim and the fleet manager run then).
  3. Never kill a process by image name. Never touch `.env`. Never start/stop the reader supervisor, the
     Telegram agent, the OpenClaw gateway, the sim session or any scheduled task.
  4. Work on your OWN branches only: `cloud/2026-10-07-ledger-split-and-identity` in this repo and
     `cloud/2026-10-07-optimus` in `C:\Users\mrthn\optimus`. Never push to `main` of either repo; never merge;
     one pull request per repo at the end; commit checkpoints often (a token limit must not destroy work).
  5. Receipts you write go under run-id filenames; never overwrite another session's receipt.
- MCP: load the Optimus MCP READ-ONLY first (`session_briefing`, `aegis_verified_state`, `aegis_canon`,
  `aegis_postmortems`, `aegis_registry`, `brain_query`; queries: "predictions ledger split hash chain",
  "ledger archive lessons", "decision story regret MDC", "research intake theory cards", "optimus brain
  showcase", "writing voice portfolio CV"). Use `exa` for every citation, patent, GitHub and docs fetch; record
  the URL fetched; never claim a citation was verified if it was not fetched.
- Skills tracked in the repo: `.claude/skills/silent-fragility-audit` (run after Task A and after any
  collector/reader you add), `pre-register-trial` (the evidence standard; register nothing from a card
  without the declaration gate below), `lane-integrity-check` (only if you accidentally reach lane/NAV code —
  you should not). Do not invoke `/grind` or `/go` wholesale.

### 1. Read first (compact; retrieve the rest by question)
`CLAUDE.md` · `docs/AEGIS_STRATEGIC_INVARIANTS.md` · `docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md`
§5a §5b §7 · `docs/HANDOFF_2026-10-07_V1_BETA_NIGHT_ONE.md` §0 §0b §3 · `docs/reviews/REVIEW_2026-10-06_C10_DATA_CATALOG.md`
· `docs/design/OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md` · `docs/research_intake/README.md` + `QUEUE.md` ·
`docs/research_notes/2026-10-07/research_instruments_2026-10-07.md` · `docs/DATA_CATALOG.md` · `docs/NEGATIVE_RESULTS.md`
· `docs/OPTIMUS_MCP_SURFACE.md` (if present) and `C:\Users\mrthn\optimus\CLAUDE.md`, `tools/refresh_aegis.py`, `mcp/server.py`,
`showcase/build.py`.

### 2. Hard rules (the repo's canon; not negotiable)
Costs never omitted · point-in-time never relaxed (first-seen before as-of; vendor rows that re-stamp are NOT_PIT and
say so) · no LLM authority over capital · nothing here touches order paths, `pc_broker`, `fleet_manager`,
`sim_run`, `decision_contract`, lane NAV write paths (`paper_nav`, CANON §5), frozen contracts, `docs/TRIALS/`,
`contest/`, `paper_accounts/`, Bloomberg, Railway config · the `predictions.jsonl` hash chain broken since Aug is
NOT repaired, it is documented with evidence · receipts carry run ids · fixtures derive dates from today · every
new module has a caller or a `signal_reachability` class · every new refusal is enrolled in
`backend/tests/test_guard_missing_input_contract.py::CASES` · no machine details (user-home paths, PIDs, RAM, GPU)
in `docs/` or tests · a verdict on a hypothesis uses the vocabulary FAILED_VARIANT / CANNOT_DISTINGUISH /
CANDIDATE / UNPOWERED_AT_DECLARATION, never STOP, never "proven" · a positive is printed by year and
leave-one-year-out before anything else is said about it · one search count (hyp_lab's deflation ledger) for all
cells you run · the fast suite is network-blocked; a non-slow test that needs the network is a bug.

### TASK A (priority 1, data integrity) — split the forecast ledger into sealed monthly streams (Q11)
As in the C10 review's Q8 answer. `backend/data/optimus/predictions.jsonl` (tracked, 52 MB, rewritten in place by
`resolve_all`, CRLF) → `forecasts/forecasts_<YYYY-MM>.jsonl` by month MADE and `resolutions/resolutions_<YYYY-MM>.jsonl`
by month GRADED; readers fold resolutions onto forecasts by id (the `llm_telemetry` amendment pattern); LF only;
temp → fsync → replace; a closed month SEALED by a committed manifest (schema, kind, month, rows, bytes, sha256,
previous-manifest hash, own hash, stamp, migration version) chained manifest-to-manifest, reusing
`backend/services/ledger_archive.py`'s seal (tracked file + matching sha). Verify the legacy chain break with code:
a verifier that finds the FIRST real mismatch using the ledger's own chain fields; the first manifest carries a
`legacy_chain_break` record (line, expected hash, found hash, source sha256, "not repaired; tamper evidence restarts
here"); if the remembered "line 1203 / 2026-08-25" is wrong, use what you compute. `python -m scripts.ledger_split
--plan` (prints source sha, months, rows, outputs, manifest plan, chain break; writes nothing) and `--apply`
(requires the plan's fingerprint; refuses if the ledger changed; writes streams + manifests; verifies; leaves the
legacy file; refuses a second application with the reason). A compatibility layer for every reader/writer
(`grep -rn predictions.jsonl backend scripts nn_lab learner`): streams when the migration marker and manifests
verify, legacy otherwise, the choice printed on each caller's receipt; writers write streams after migration. Tests
as listed in the C10 review and the earlier brief (round trip, fold by id, duplicate resolutions explicit, seal
refusals, chain-break verifier, `--apply` refusals, LF, reader choice inspectable). Run `--plan` only against the
real ledger (paste it); `--apply` only on temp copies in tests. Run the silent-fragility-audit skill after.
Note: `docs/research_notes/2026-10-07/ledger_split_cloud_2026-10-07.md`.

### TASK B (priority 6) — GitHub identity and the website's public face
Assets under `docs/assets/` + README hero only in THIS repo (architecture SVG from the Mermaid in
`docs/AEGIS_V1_BETA_2026-10-07.md`, each box naming its module; `og_preview.svg` 1200×630 with the honest line
"RESULT IMPROVEMENT: NONE — the loop runs, grades itself, freezes its alternatives" and the site link; README hero
with the evidence ladder OBSERVED → EARLY_EVIDENCE → REPLICATED → VALIDATED_EDGE and the live page links
`/opportunities /brain /arena /forecast-lab /theory-lab /health`; `docs/assets/README.md` registry with licences;
the owner's logo files are in `C:\Users\mrthn\Downloads` ("Aegis Finance white only logo.PNG", "Aegis Finance
resize.png") — copy them to `docs/assets/` as `logo_white.png` / `logo.png`). Do NOT touch the generated
"Historical backtests: what worked, what didn't" README block (`backend/tests/test_bridge_report.py` pins it; run
that file). `frontend/` is OFF-LIMITS in this repo (the manager's session owns it and the site deploys from
`main`); write a `docs/design/WEBSITE_IDENTITY_SPEC_2026-10-07.md` instead: typography, colour tokens, the OG
meta tags to add, the hero for `/`, and per-page polish notes for the six pages, so a frontend task can apply it.

### TASK C (priority 4) — five research cards, then HYPOTHESIS TESTS on local data where the data exists
Cards first (follow `docs/research_intake/README.md` exactly; every citation fetched; `needs_evidence` 1-3 items;
family from `backend/config.py`'s fixed list or `family_unmapped`; dataset named from `docs/DATA_CATALOG.md` or
"not on disk"): (1) institutional ownership / 13F; (2) volatility / variance risk premium (realised vs implied);
(3) regime changes / regime-conditioned signal trust; (4) short interest; (5) microstructure / liquidity imbalance.
Then, for each card whose verdict is READY_TO_CELL and whose dataset IS on disk (check: 13F via
`backend/services/official_sources.py` and the WRDS pulls listed in `DATA_CATALOG.md`; options/implied vol via
`options_pit`; FINRA short interest via official sources; TAQ effective spreads via the `wrds` tables the
postmortems mention; regime via `world_state/` + the regime rows + `prices_2025_26/bars.parquet` and the CRSP
panel), run ONE declared cell each through the existing machinery — `scripts/hyp_theory_cells.py` with C12's
declaration gate (it prints the class split and the control MDE and REFUSES an unreadable cell) — with: the
declaration hashed before the run; the sticky twin as control where a holding rule is tested
(`backend/services/matched_twins.py` `twin_series_sticky`; the basket twin beside it); costs via the shared
`trade_cost`; validate 2009-2016 read once; by-year + leave-one-year-out printed for any positive; and the
deflation count incremented in `hyp_lab`'s ledger. One cell at a time, memory-gated (§0), each ≤ 40 minutes;
a cell that cannot be read is `UNPOWERED_AT_DECLARATION` and still a result. Write
`docs/research_notes/2026-10-07/cloud_cells_2026-10-07.md` with each cell's declaration hash, receipt path,
verdict, and the one sentence a scoreboard would print. Expected honest outcome: most are UNPOWERED or
CANNOT_DISTINGUISH; say so plainly.

### TASK D (priority 4) — research-intake validator and index
`python -m scripts.research_intake_check [--write-index]` (stdlib only): required headings, one controlled verdict,
family in vocabulary or `family_unmapped`, `needs_evidence` 1-3 non-empty, at least one DOI/URL, no placeholder
markers unless NEEDS_DATA allows, repo-relative paths, duplicate slugs/titles/DOIs caught; deterministic
`docs/research_intake/INDEX.md` (card, topic, mechanism class, dataset status, family, verdict, open evidence count,
source year range); tests pin determinism and vocabulary.

### TASK E (priority 4) — prior-art and methodology map for the measurement system
`docs/research_notes/2026-10-07/edge_measurement_prior_art_cloud_2026-10-07.md`: proper scoring rules; model
contribution / neutralisation (Numerai MMC); Shapley and ablation attribution; online learning, regret, contextual
bandits; confidence sequences and anytime-valid inference; decision provenance and event sourcing; dynamic
financial knowledge graphs and causal event propagation; the patents already in the project's docs plus closer ones
you find. Risk map per idea: COMMON/OLD · KNOWN BUT DIFFERENT · POTENTIALLY DISTINCTIVE IMPLEMENTATION DETAIL ·
NEEDS COUNSEL; for anything potentially distinctive name the narrow mechanism. Not an FTO opinion.

### TASK G (priority 5, the owner's explicit ask) — Optimus: the brain, the MCP, the dashboard, and "it knows me"
Work in `C:\Users\mrthn\optimus` on branch `cloud/2026-10-07-optimus` (GitHub `Murathanx12/Optimus`). Inspect
before designing: `mcp/server.py` (tools: session_briefing, aegis_verified_state, brain_query, aegis_canon,
aegis_postmortems, aegis_registry, aegis_skills), `tools/refresh_aegis.py` (ingests both repos' docs + session
memory into `brain/index.db`), `showcase/build.py` (the public brain page at optimus-brain-alpha.vercel.app: a force
graph on July data with an overlapping legend — the owner dislikes that nodes push each other), and the brain
corpus (what pages exist about the owner: CV, portfolio, hobbies, projects, how he writes).
G1. **Connection map** (`docs/OPTIMUS_CONNECTIONS_2026-10-07.md` in the optimus repo): every producer that feeds
    the brain and every consumer (Claude Code sessions via MCP, the Aegis health page, the Telegram agent?, the
    reader?), with the gap list: the OpenClaw reader's claims, the world-state belief table, the regret ledger and
    the research cards are NOT ingested today — design the ingestion (append-only, provenance-tagged, with
    first_seen, never rewriting pages) and implement the two cheapest (world_state beliefs → a daily brain page;
    research cards → brain pages) in `refresh_aegis.py` with tests.
G2. **The brain dashboard**: rebuild the showcase from the Aegis state-board spec
    (`docs/design/OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md` §2 and the sanitised payload
    `backend/data/public_receipts/brain/latest.json` once the next publish runs, or compute it locally with
    `python -c "from backend.services import legibility; import json; print(json.dumps(legibility.brain_payload())[:2000])"`
    from the Aegis repo — the production API has not redeployed yet): fixed rings,
    hash-stable positions, orb size = confidence, colour = direction, pulse only on a state change, legend that
    never overlaps, reduced-motion honoured, every orb traceable to a receipt field; plus a second view of the brain
    corpus itself (pages by domain and age, what was ingested when). Static export; no force simulation; no new
    heavy dependency (p5.js is acceptable per the design doc if instance-mode and ≤ 300 KB gz; prefer SVG).
G3. **MCP improvements** (read-only by default): `aegis_health` (reads the PC's newest
    `backend/data/optimus/health/health_*.json` and the daily pass's health line); `aegis_receipt` (returns one
    receipt by kind: roi, book_dna, regret, world_state, with its age and sha); `brain_pages_about(topic)`;
    `research_card(slug)`; and ONE attended write tool `brain_note_append(page, text)` that appends with a
    stamp and author and refuses to edit existing text. Keep the per-call cost small; add tests; document the
    surface in `docs/OPTIMUS_MCP_SURFACE.md` (both repos).
G4. **"It knows me" — the author profile and voice layer** (the owner's words: "whenever I'm generating a document,
    even on the web, it should use my connectors, my skills, my language, how I approach a problem: root cause
    first, demand discovered from the web, data-driven reasoning, human psychology"). Build, from the brain's own
    pages about the owner (CV, portfolio, project write-ups, these handoffs — nothing invented): (a)
    `profile/AUTHOR_PROFILE.md` — background, skills, interests, active projects, how he approaches problems,
    what he values in a document, with every statement citing the brain page it came from; (b)
    `profile/VOICE.md` — his writing voice described from samples: sentence length, structure, how he opens,
    what he never does (no hype, receipts beside numbers, honest negatives), with 5 verbatim sample paragraphs
    he wrote (cite); (c) a Claude skill `write-as-murat` placed BOTH in `C:\Users\mrthn\optimus\.claude\skills\`
    and exported as a Markdown bundle the owner can upload to claude.ai's skills (the web app cannot read local
    files): the skill loads the profile and voice, says when to call `brain_query` for context, and gives the
    document-shaping rules (start from the problem's root cause; find the demand with evidence; data before
    opinion; the reader's psychology; receipts beside numbers; what he would and would not claim); (d) an
    MCP tool `author_profile()` returning (a)+(b) so any connected session can load them; (e) a test that the
    profile contains no claim without a citation. Do not include private identifiers (ID numbers, addresses,
    phone, e-mail) in any of these files.
G5. **Session memory hygiene**: the brain ingests the manager's session memory; propose and implement the
    index of "lessons" (the feedback files) as a first-class brain page with the date each was learned, so
    `brain_query` returns the lesson and its receipt rather than the session narrative.

### TASK H (priority 5, bounded) — a quality audit of the news evidence, not a news read
Do not "read the news to evaluate stocks". Instead, from `backend/data/optimus/dowjones/` claims and the newest
world digest rows: sample 100 rows stratified by provenance (FACT / COMPANY_CLAIM / INTERPRETATION / FORECAST /
UNCLASSIFIED, per C17's rule) and grade each by hand: is the label right? is the entity right? is the date the
publication date? would a reader act on it? Receipt `dowjones/provenance_audit_<run_id>.json` with the confusion
matrix and the three most common error shapes; propose the rule fixes to `world_digest`'s provenance function with
tests on the audited rows as fixtures (sanitised). This improves every downstream consumer at once.

### TASK F — up to two extra tasks you choose
From the roadmap's queue (§5b and its amendments) if cloud-safe under §0 and §2; before starting, log 3-5 lines
(why high-EV, why no conflict, acceptance). Good candidates: a replay harness for `decision_story` that re-grades
a dry session; a dead-code / orphan classification pass; the desktop `.exe` export check (`python -m
scripts.frontend_check` is a heavy job: lock + memory rule).

### Acceptance (paste into each PR)
Starting SHAs; per task: files, tests run with their summary lines (ledger suite; `test_bridge_report`; the fast
backend suite `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 python -m pytest backend/tests/ -m "not slow" -q`
run ONCE at the end under the lock; the research-intake checker; optimus's own tests); the real `--plan` output and
the chain-break record; the five cards' verdict lines and the cells' verdicts with receipt paths; the prior-art
map's three conclusions; the Optimus connection map's gap list and what you closed; the author-profile citation
count; MCP servers actually available and skills invoked; "what I could not do"; merge risk (likely conflict
files: `backend/config.py`, `signal_reachability.py`, `test_guard_missing_input_contract.py`, README).

### End state
Both branches pushed, one PR per repo open against `main`, working trees clean, no merge, no deploy, no live
migration, the lock file deleted, every receipt under a run id. The manager reviews the PRs here.
