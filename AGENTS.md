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
