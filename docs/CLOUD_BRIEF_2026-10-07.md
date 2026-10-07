# CLOUD BRIEF 2026-10-07 — tasks for a Claude Code cloud session (Opus 5.5) on a separate branch

Paste the block under "PROMPT" into Claude Code (web / desktop "cloud" mode) with the repository
`Murathanx12/Aegis-Finance`, base branch `main`. The session cannot see this PC: no `.env`, no API keys, no
CRSP/vendor parquet, no live broker, no Optimus MCP (that server runs on the PC). Everything below is
doable from the GitHub checkout alone, offline, with the repo's own tests. The orchestrator on the PC
reviews the PR before anything is merged.

What the checkout DOES contain: the code, ~13,700 tests, `docs/`, the project skills in `.claude/skills/`,
tracked receipts under `backend/data/optimus/` including the 52 MB `predictions.jsonl`, the published page
payloads in `backend/data/public_receipts/`, and `.mcp.json`: its `optimus` entry points at a local path and will not start in the cloud (ignore it); its `exa`
entry is an HTTP MCP (`https://mcp.exa.ai/mcp`) that CAN work in the cloud for web search and citation verification
if the session approves it. The Optimus canon the cloud would otherwise query is summarised in `CLAUDE.md` and
`docs/AEGIS_STRATEGIC_INVARIANTS.md`; read those instead.

---

## PROMPT

You are an Opus 5.5 engineering session on `Murathanx12/Aegis-Finance` (use the `exa` MCP from `.mcp.json` for web
fetches if offered; the `optimus` MCP is local to the owner's PC and unavailable here), working ALONE on a new branch
`cloud/2026-10-07-ledger-split-and-identity` cut from `main` (currently `92f147f6`). You may run
subagents. You must NOT push to `main`; open ONE pull request against `main` when done, with the
acceptance evidence pasted in its description. Commit checkpoints on your branch as you go.

### Read first (in this order, nothing else up front)
1. `CLAUDE.md` (the operating rules; especially the session-start protocol items 5, 7, 10, 11; the
   "DO / DO NOT" list; `AEGIS_IGNORE_DOTENV=1`; never move `.env`).
2. `docs/ROADMAP_2026-10-06_V1_BETA_THE_LOOP_THAT_LEARNS.md` §5b (queue) and §7 (binding rules).
3. `docs/HANDOFF_2026-10-07_V1_BETA_NIGHT_ONE.md` §0, §0b, §3 (lessons the reviews taught).
4. `docs/reviews/REVIEW_2026-10-06_C10_DATA_CATALOG.md` (its Q8 answer is the design you implement).
5. `docs/design/OPTIMUS_CREATIVE_TOOL_LIBRARY_2026-10-07.md` §3 (the GitHub identity plan).

### Hard rules (from the repo's canon; they are not negotiable)
- Costs are never omitted; point-in-time discipline never relaxes; no LLM authority over capital; nothing
  here touches order paths, lane NAV write paths (`paper_nav`, CANON §5), frozen contracts, or trials.
- The ledger hash chain in `predictions.jsonl` has been BROKEN since 2026-08-25 and must NOT be silently
  repaired: a tamper-evident chain that gets repaired is worthless. You write an explicit CHAIN-BREAK
  record that cites the prefix hash as found.
- `predictions.jsonl` is TRACKED and GROWS continuously on the PC: never rewrite history in place in a
  way that would conflict with a concurrent append; the migration must be a one-shot, idempotent command
  the PC operator runs once, with a refusal if the file changed since the manifest was computed.
- Receipts carry a run id in the filename; a date-only filename a second run can overwrite is not a receipt.
- Fixtures derive dates from `today`; never a literal calendar date that becomes stale.
- Give every new module a caller or classify it in `backend/services/signal_reachability.py`; enrol every
  new refusal/guard exception in `backend/tests/test_guard_missing_input_contract.py::CASES`.
- No machine details (user-home paths, PIDs, RAM, GPU) in anything under `docs/` or tests.
- Run the fast suite before the PR: `AEGIS_IGNORE_DOTENV=1 AEGIS_PERSONAL_MODE=0 python -m pytest
  backend/tests/ -m "not slow" -q`. It is network-blocked by design; a test that needs the network is a bug.
  Some tests are gated on local data that is not in git and will SKIP; a SKIP is fine, a FAIL is not.
- Every headline number in a receipt; the word "proven" appears nowhere; "alpha" only as "not demonstrated".

### TASK A (priority 1, data integrity) — split the forecast ledger into sealed monthly streams (queue item Q11)
`backend/data/optimus/predictions.jsonl` is 52 MB (GitHub warns at 50, refuses at 100) and is rewritten in
place by `resolve_all` (non-atomic) with CRLF line endings. Implement the C10 review's design:
1. Two append-only streams: `forecasts/forecasts_<YYYY-MM>.jsonl` by the month the forecast was MADE,
   and `resolutions/resolutions_<YYYY-MM>.jsonl` by the month it was GRADED; the reader folds a
   resolution onto its forecast by id (the same way LLM-call amendments are folded; find that pattern in
   `backend/services/llm_telemetry.py`). LF only, written atomically (temp → fsync → replace).
2. A closed month is SEALED by a committed manifest (schema, rows, first/last timestamp, sha256 of the file)
   chained to the PREVIOUS month's manifest hash (manifests chain, not rows). Reuse `ledger_archive`'s
   seal pattern (`backend/services/ledger_archive.py`: a seal requires the tracked file and a matching sha).
3. The chain-break record: one explicit entry in the first manifest stating that the row hash chain was
   found broken at line 1203 on 2026-08-25 (find the exact evidence: `grep` the ledger for the chain
   fields and locate the first mismatch; cite line and hashes), that it was NOT repaired, and that
   tamper evidence restarts from this manifest.
4. The migration command `python -m scripts.ledger_split --plan` (prints what it would do, by month, with
   row counts and sha256) and `--apply` (one-shot; refuses if `predictions.jsonl`'s sha256 differs from the
   plan's; writes the streams + manifests; leaves the original file untouched and gitignores nothing until
   the PC operator confirms). Every reader of `predictions.jsonl` (find them: `grep -rn predictions.jsonl
   backend scripts nn_lab learner`) gets a compatibility reader that reads the streams when they exist and
   the legacy file otherwise, with the choice printed on its receipt; writers (`belief_state`, the daily
   pass grader, `resolve_all`) write to the streams after migration.
5. Tests: round trip (legacy → streams → the same rows, byte-equal content hashes per row); fold-by-id;
   sealing refuses a mismatched sha or a missing manifest predecessor; the chain-break record is present
   and names the line; `--apply` refuses when the source changed; LF-only output; the compatibility reader's
   choice is on the receipt. Do not run `--apply` against the committed file in the PR; run it in a temp
   copy in tests and in `--plan` mode for the real file, pasting the plan into the PR.
6. `docs/research_notes/2026-10-07/ledger_split_cloud_2026-10-07.md`: the design, the plan output, the
   chain-break record text, and the exact one-command migration for the PC operator.

### TASK B (priority 6, product identity) — the GitHub presentation, from the design plan §3
Deliverables under `docs/assets/` and the README only; nothing in `frontend/` (the site is deployed from
`main` by a workflow; keep it out of this PR):
1. `docs/assets/architecture_pipeline.svg`: render the Mermaid pipeline in
   `docs/AEGIS_V1_BETA_2026-10-07.md` as a clean SVG (hand-written SVG or generated by a script you add
   under `scripts/` with no new runtime dependency; dark/light friendly; each box names its module).
2. `docs/assets/og_preview.svg` (1200×630) and a PNG export if a dependency-free path exists; the title,
   the one-sentence description from the V1 Beta doc, the honest scoreboard line "RESULT IMPROVEMENT:
   NONE — the loop runs, grades itself, freezes its alternatives", and the website link
   `https://aegis-finance-six.vercel.app`.
3. README hero: a top section with the logo placeholder (the owner has `Aegis Finance white only logo.PNG`
   locally; reference `docs/assets/logo.png` and leave a TODO for the owner to drop it in), the
   architecture SVG, the evidence ladder in one line, links to the live pages `/opportunities`, `/brain`,
   `/arena`, `/forecast-lab`, `/theory-lab`, `/health`, the V1 Beta doc, the roadmap, the funding pack.
   Do NOT touch the generated "Historical backtests: what worked, what didn't" block or anything
   `backend/tests/test_bridge_report.py` pins (run that test file after editing the README).
4. A `docs/assets/README.md` listing every asset, what generates it, and its licence.

### TASK C (priority 4, research; runs in a subagent while A and B proceed) — five more research-intake cards
Follow `docs/research_intake/README.md` exactly. Take the top five topics of
`docs/research_intake/QUEUE.md` and write one card each under `docs/research_intake/cards/`, every
citation VERIFIED by fetching it (DOI or publisher page), the decay literature cited (McLean & Pontiff
2016; Harvey, Liu & Zhu 2016), the dataset on disk named from `docs/DATA_CATALOG.md` (if the dataset is
not in git, say so; do not guess row counts), the hyp_lab family from the fixed list in
`backend/config.py`, and a verdict from the card vocabulary. Add a `needs_evidence` list (1-3 open
questions) to each card. No numbers that are not in a source.

### Acceptance (paste into the PR description)
- `pytest` summary line of the fast suite (passed / failed / skipped), plus `pytest backend/tests/test_bridge_report.py`.
- The `--plan` output for the real ledger (months, rows, sha256) and the chain-break record text.
- The list of files changed per task, and the five cards' verdict lines.
- A "what I could not do from the cloud" section (anything needing local data, keys, the PC, or the owner).

### Do not
- Do not push to `main`; do not merge; do not edit `frontend/`, `backend/services/pc_broker.py`,
  `fleet_manager.py`, `sim_run.py`, `decision_contract.py`, anything under `docs/TRIALS/`, or any file
  under `backend/data/optimus/contest/` or `paper_accounts/`.
- Do not add runtime dependencies. Do not call any external API except to verify citations (HTTP GET).
- Do not write the word "proven". Do not repair the hash chain.
