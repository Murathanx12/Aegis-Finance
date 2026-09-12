# Research note 2026-09-11 — Headline Arena (issue #8, Kopei), from the Sonnet report

Rewritten 2026-09-12 from the agent's final report; the file previously on disk was a three-line stub.
Roadmap lane M item M6; the daily job is `scripts/headline_arena_daily.py` (chunk 5, dry-run only —
**its payload field names must be verified against the venue before the first real POST**).

## What it is
headlinearena.com: AI agents submit daily direction + confidence forecasts on macro/financial targets
(and a "Civic Index" of official statistics), locked before a deadline, mechanically settled, scored,
calibration curves public. No company, jurisdiction or funding disclosed (Terms invoke "general
principles of international commercial law"; Privacy names only a China PIPL contact role). Free; a
7-day Pro trial and 100 credits at signup; paid plans "never change scores or rank". Credits are
redeemable only against the platform's own LLM gateway, not third-party APIs. **Terms grant the
operator a worldwide, royalty-free, perpetual, sublicensable licence to submitted forecast data**,
including for AI training and third-party commercial use, surviving deactivation — treat `reasoning`
text as public and non-recallable. Agent identities and forecasts are public by default.

Plugin `headlinearena/headlinearena-agent-plugin`: MIT, 3 stars, created 2026-04-26, one contributor
(Kopei), stdlib-only CLI (`scripts/ha.py`), credentials in `~/.headlinearena/credentials.json`, a
background update check (~every 20 h, disable with `HA_NO_UPDATE_CHECK=1`). Registration: declare
`model_provider`/`model_name` truthfully, pass a scored (≥ 60/100) "analyse this market event"
challenge, then a human claims the agent by e-mail magic link or a 6-character pairing code (48 h) —
**attended, Murat's step.**

## Mechanics
Targets: GC, ES, CL, SI, ZN, HG, NG, BTC (paused), ZS, DXY, RB, ETH; Civic Index (HF_US_CPI, CORE_CPI,
NFP, UNEMP, ICLAIMS, PPI; EU HICP/UNEMP; CN CPI/UNEMP); and, inconsistently with the methodology page's
"sports excluded", WC2026 match outcomes. Only GC/ES/ZN/CL/HG/NG carry the daily schedule: created
17:00 ET weekdays, **deadline 10:00 ET next day**, settled T+24 h. Settlement is threshold-based on a
per-challenge `dead_zone_pct` (read it from the challenge object, never hardcode). **Financial-track
score is `50 + confidence × 50` if right, `50 − confidence × 50` if wrong (0-100) — not Brier**; Brier
is used on the categorical Civic track, CRPS on numeric ones. Leaderboard needs ≥ 30 settled forecasts;
the top agent at crawl time ("Rates Trader Opus", claude-opus-4-6) scored 64.4 with **51.5% accuracy**
over 400 forecasts — near coin-flip. Rate limits 5/min, 50/day on staked tracks. A public read API
exists for the Civic track's quality-weighted consensus
(`GET /api/v1/public/human-forecasts/challenges/{id}/consensus`, `.../calibration?target_key=`); the
financial track exposes only pool odds (`/eval/challenges/{id}/odds`).

## The three REST calls (from the plugin's guide and skill files; `/openapi.json` was 404)
1. `POST /api/v1/agent/auth/token` — `{"grant_type":"client_credentials","agent_id":"…","client_secret":"…"}`.
2. `GET /api/v1/eval/challenges?status=open` (no auth) — today's challenges with `dead_zone_pct` and
   `resolution_criteria` per challenge.
3. `POST /api/v1/eval/challenges/{challenge_id}/predict` — `Authorization: Bearer <token>`,
   `{"direction":"bullish|bearish|neutral","confidence":0.0-1.0,"reasoning":"…","summary":"…","prompt_hash":"<sha256>"}`.
Results: `GET /api/v1/eval/challenges/{challenge_id}/results`. Revision history before the deadline is
preserved; missing-data handling retries or cancels rather than settling stale.

## Fit, risks, what to learn
Fit as a `PRODUCT_EXPERIMENT`, read-only, no-authority daily job: our sensors → direction + confidence
on GC/CL/ZN/ES/DXY; **lock the row in our ledger first** (`belief_state.make_prediction`), then POST;
reconcile their settlement against our grade next day. Adds independence (settled by a party that is
not us, on shared targets, public curve). Loses information (ternary settlement vs our probabilities).
Risks: the perpetual licence on submitted text; no entity for recourse; one-maintainer repo; "credits
for scoring well" could nudge confidence — **credit-earning never touches the stated confidence**.
Learn from them: `dead_zone_pct` as frozen per-challenge metadata (our "guards derive their inputs");
keeping directional reliability, Brier and CRPS as separate diagnostics; pre-deadline revision history.

## Similar arenas (partly from training knowledge; Metaculus blocked fetch)
Metaculus (free, independent settlement, API, AI Benchmark tournament, community aggregate readable);
ForecastBench (Forecasting Research Institute, contamination-free LLM benchmark, Tournament and
Baseline tracks); Manifold (play money, public read API); Polymarket/Kalshi (already in
`prediction_markets.py`); Good Judgment Open (human crowd, limited API).

## Schedule and acceptance
Challenges created 17:00 ET = 05:00/06:00 HKT next day; deadline 10:00 ET = 22:00/23:00 HKT. Pre-register
the sensor → target mapping before the first submission (`backend/data/headline_arena_mapping.yaml`,
`prereg_hash`). Acceptance: for every resolved challenge our ledger's grade equals their settlement.
