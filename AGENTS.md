# AGENTS.md — orientation for AI agents working in this repo

Aegis Finance is a market-intelligence platform **plus** a self-auditing quant
research program. If you are an agent (Claude, GPT, Gemini, autonomous bot),
this file tells you where things are and which rules are load-bearing.
Machine-readable web surface: `frontend/public/llms.txt`.

## Read these before changing anything

1. **`CLAUDE.md`** — build/test commands, tech stack, repo layout, DO/DO-NOT
   rules. Applies to all agents, not just Claude.
2. **`docs/CANON.md`** — the non-negotiable guardrails. The short version:
   no skill claims before 24 months of forward record; pre-register or it
   didn't happen; the LLM narrates, the engine computes; closed rabbit holes
   stay closed; every examination leaves a ledger entry.
3. **`NEGATIVE_RESULTS.md`** — 34 documented dead ends. Check it before
   proposing an idea; yours may already have a corpse with receipts.

## Map

| You want | Go to |
|---|---|
| Web app (Next.js 14) | `frontend/` — deployed on Vercel |
| API (FastAPI, 130+ endpoints) | `backend/` — deployed on Railway |
| Offline research/training | `engine/` |
| Pre-registered trials | `docs/TRIALS/` + `docs/CANON.md` §6 |
| The research ledger | `NEGATIVE_RESULTS.md`, `docs/FINDINGS.md` |
| Backlog / roadmap | `docs/BACKLOG.md`, `docs/AEGIS_EXECUTION_ROADMAP.md` |
| The sister research repo | `../Aegis module` (CRSP/WRDS strategy factory, paper lanes' brain) |

## Live surfaces

- Dashboard: https://aegis-finance-six.vercel.app
- API health: https://aegis-finance-production.up.railway.app/api/health
- Public track record: https://aegis-finance-production.up.railway.app/api/pi/track-record

## Rules that exist because an agent once broke them

- **Silent fragility is the house failure mode.** A collector that runs and
  fetches nothing reads as green. Fail loud; verify live after deploys
  (`.claude/skills/verify-prod-after-deploy`).
- **Never write zeros on failed fetches.** Raise; a zero poisons everything
  downstream and passes unit tests.
- **Backtests on our (survivor-biased, free) data are direction checks
  only** — never alpha claims. Forward paper NAV is the only track record.
- **The `paper_nav` write-path is sacred** — no rebooking, no backfills
  without a ledger entry.
- **Gates must be calibrated before their kills are trusted** (learned
  2026-08: our own thresholds had ~0% power — NEGATIVE_RESULTS §34).

## Secrets

API keys live in environment variables only (`FRED_API_KEY`, optional
`DEEPSEEK_API_KEY`, `FINNHUB_API_KEY`, `FMP_API_KEY`, `POLYGON_API_KEY`).
Never commit a key; never echo one into a log or doc. `.env` is gitignored.

## Codex continuity and delegation (2026-10-08)

Claude's files, history and original marketplace cache remain intact. Codex
shares the project knowledge through `.agents/skills/` and Optimus MCP; it does
not replace `.claude/` or reinterpret old handoffs as current machine state.

- Start with Optimus `session_briefing` + `aegis_verified_state`, then
  `docs/INDEX.md`. Codex workflow: `docs/CODEX_OPERATING_MODEL.md`; current setup
  and next actions: `docs/CODEX_SETUP_2026-10-08.md`.
- Use `$aegis-codex-session` for pickup/handoff and `$aegis-pc-automation` for
  authorized OpenClaw/PC tasks. The existing discipline skills still apply.
- The owner authorizes bounded delegation: deterministic checks first; a small
  worker for inventory/docs; a capable builder and independent reviewer for
  behavior changes; stronger independent reasoning for strategy, sizing and
  evidence. Give workers relevant paths and acceptance criteria, not the full
  conversation. One writer per file and one operator per browser/profile.
- Preserve uncommitted runtime receipts and other workers' changes. Never
  reset, clean, bulk-stage the tree, or stop processes by image name.
- For Bloomberg, freshness means dated receipts and advancing rows. Keep the
  authentic WLS MEMB gate. Registration, universe, rules, policy choice and
  verified fills are separate facts; a passing drill is not a live fill.
- Use the existing OpenClaw operator for PC/browser work within the user's
  task. The automated reader's restrictions stay in place; authorized login
  or free signup requires a distinct scoped workflow. Never pass credentials
  into a model prompt, transcript, command argument or receipt.
- Codex-only plugin state belongs in Codex configuration. Imported
  `security-guidance` is disabled there; preserve Aegis hooks and original
  Claude plugins. Security tooling availability is not a completed scan.
