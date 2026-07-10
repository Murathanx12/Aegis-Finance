# Session Post-Mortem — 2026-07-09 — Deep research → three builds

## What this was

Murat asked "is everything done → research what the engine lacks → build it,"
with the stated ambition of an engine that guides personal accounts and runs
paper lanes that beat SPY. The ambition was reframed at the top (and he
proceeded): nothing can promise outperformance — the buildable form is more
evidence-backed forward signal candidates + the guidance surface, with the
24-month record as the only proof.

## The research (adversarially verified)

Deep-research workflow: 5 angles, 81/106 agents completed before the API
monthly spend limit killed the vol-targeting verification cluster and the
synthesis step. Synthesized manually from the 14 CONFIRMED / 3 REFUTED claims
→ `docs/research/ENGINE_GAPS_2026_07_09.md`. The refutations were the best
part: **Moreira–Muir vol-managed alpha REFUTED 0-3** (and the 103-strategy
study confirmed managed ≈ unmanaged on Sharpe) — independently validating our
2026-06-15 stance that vol overlays are drawdown control, not alpha. Also
refuted: "PEAD subsumes momentum."

## What shipped (each pre-registered before data)

1. **TRIAL-PEAD-IC** — two-way earnings-surprise score (analyst surprise % +
   3d announcement-window excess return), honest zero outside 90d, frozen
   params, honest prior "decayed/disputed net-of-cost in large caps."
2. **TRIAL-QUALITY-IC** — Novy-Marx GP/A alone (the T8 deferred quality slot),
   Piotroski subset as unweighted diagnostics, 63/126td primary horizons via
   the hang-safe yfinance path (edgartools stays rejected).
3. **POST /api/portfolio/guidance** — the product ask: per-position P&L, move
   z-score, Chandelier stop level + distance (frozen config), PIT signal
   readings, and disposition-effect nudges (winner_rolling_over /
   loser_past_stop). Order language test-pinned absent.

Forward-IC trials now: momentum (in multifactor), insider, revisions,
multifactor, PEAD, quality — six selection clocks accruing weekly.

## Lessons / rejected

- **The spend limit is a workflow hazard:** a 106-agent research run died
  mid-verification. Main-loop synthesis from the surviving verified claims
  worked fine — claims without verification votes were treated as
  unverified, not quietly promoted.
- **Rejected: adding quality/PEAD into the in-flight TRIAL-MULTIFACTOR
  composite** — that trial's definition is frozen; a v2 composite is its own
  future trial.
- **Rejected: building more vol-timing machinery** — the research refutation
  + our own postmortem agree it's risk control only.
- Coverage gap stated, not papered over: behavioral-UX and event-type
  short-horizon claims never reached verification (spend limit); event-driven
  signals beyond descriptive context wait for verified evidence.

## Next

- The six IC clocks + tonight's first candidate/13F/alert collections need
  their first prod verification (`railway logs | grep collect`).
- Guidance frontend (the portfolio page card) — endpoint only so far.
- Chen–Zimmermann free bench (212 predictors, survivorship-curated) as a
  direction-check harness for our signal definitions — the one unbuilt
  research find, good first chunk next session.
