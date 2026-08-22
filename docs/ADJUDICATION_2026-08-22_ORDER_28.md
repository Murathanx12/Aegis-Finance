# ADJUDICATION — ORDER 28 (external review, "open the training gate"), 2026-08-22

An external review is ADJUDICATED, never imported. Verdicts below are grounded
in what this session measured on disk, not in the review's description of the
repo. HEAD at adjudication: `8f36617` (matches the order's stated base — no
delta to adjudicate).

## Factual corrections to the review, first

1. **"Build MODEL_TOURNAMENT_V1" — it exists and has already run signed.**
   `AEGIS-NET-TOURNAMENT-1` (REGISTERED, receipt
   `net_tournament/tournament_2026-08-19T040624Z.json`) ran cs_rank /
   forward_return / forward_vol / forward_maxdd heads, ridge baseline vs
   LGBM/MLP arms, walk-forward folds, MDE-scaled three-way verdicts with Holm,
   and known-answer synthetic worlds (linear / nonlinear / null / barrier
   rehearsal receipts on disk). `RISK-HEAD-AT-SCALE-1` then re-ran the risk
   ordering on a 312,766-row early-era panel and CONFIRMED LGBM > ridge in
   both eras. The correct move is to point this frozen machinery at the scaled
   return panel — a new registration, not a new framework.
2. **"Build the canonical panel" — the spine exists.** `crsp_pit_monthly_v1`
   (545,478 stock-months, 2013–2024-11, shrcd 10/11, exchcd 1–3, $5 / $100M
   dollar-vol filters, **delisting returns compounded**) plus
   `crsp_pit_monthly_early` (1990–2012). What was missing is the JOIN to the
   characteristic families — and `jkp_global_factor_usa` (558,369 rows, ~440
   columns, formation-date stamped, same universe construction) is that
   join's right-hand side, already on disk. AEGIS_PANEL_V1 is a join + a
   family map + coverage matrices, not an acquisition project.
3. **The return question at scale is already half-answered, negatively, on
   price-only features.** UNIVERSE-SURVIVAL-STRESS-1 (2017–2024, ~1,500–2,300
   names/mo): return ICs ~0 for every arm. RISK-HEAD-AT-SCALE-1 SCREEN:
   early-era price-only return ICs positive (+0.012..+0.017) — era-dependent,
   and that receipt explicitly says the successor is a NEW registration. The
   untested variable is **information beyond price** (the JKP families). That
   is the registered question this order opens, and it is exactly "what did
   45 GB buy."

## Verdicts on the numbered items

| # | item | verdict |
|---|---|---|
| 1 | TRAINING_SUBSTRATE_V1 receipt | **ACCEPT.** Final verifier pass + machine-readable receipt this session. Claim scoped to "inputs required by TRAINING_SUBSTRATE_V1 are verified", never "all WRDS data." |
| 2 | AEGIS_PANEL_V1 | **ACCEPT AS A JOIN** (correction 2). Monthly canonical frequency; families separable via a declared column→family map; JKP `eom` PIT stamping gets the spot-audit its own meta demands BEFORE first trial use. Early era (1990–2012) stays a family-restricted held-out era — JKP was not pulled there. |
| 3 | Labels declared before tuning | **ACCEPT.** v1 labels: fwd 21d return incl. delist (primary), fwd vol, fwd maxdd; 5d/63d horizons declared for later heads. The deciding metric is per-date rank IC, which is invariant to per-date market adjustment — excess-return debates cannot move it. |
| 4 | Tournament arms (RF/CatBoost/XGB/…) | **MODIFY.** v1 arms stay the tournament-frozen trio (ridge / LGBM / MLP) + one new declared arm (LGBM LambdaRank). CatBoost/ExtraTrees/Transformer are later registrations once the panel-scale baseline exists — the order itself says don't build the Transformer before the simple tournament runs. |
| 5 | Randomized falsification | **PARTIAL ACCEPT.** Known-answer worlds + PBO/DSR + purged CV exist. Added now: within-date label-permutation null on the REAL panel shape (run before the registered run). Block bootstrap already the §58 standard. Cost ×1/×2/×3, era deletion, ticker remap: declared for the economic (portfolio) stage, not the IC stage — costs don't act on an IC. |
| 6 | Economic promotion standard | **ALREADY CANON.** Net excess CAGR ≥ +3%/yr AND ≥4/6 regime blocks AND holdout (§58/§59 scoped). Nothing in this order weakens or replaces it. An IC result licenses a *portfolio-stage* registration, never a lane. |
| 7 | RETURN_HEAD/RISK_HEAD | **RISK_HEAD exists** (`models/risk_head_vol_lgbm_options/2.0.0`, LGBM, both-era receipts). RETURN_HEAD is gated on this session's tournament outcome — heads are built from winners, and there may be no winner (that is a publishable finding, not a failure). |
| 8 | Unsupervised challengers | **DEFER with corpse.** Order 24: MP-denoising FEATURES hurt; sources share 3–7 latent factors. Any latent representation enters the SAME tournament as one more feature family and must beat raw features. No autoencoder before the supervised baseline exists. |
| 9 | LLM factorial | **ALREADY REGISTERED** as ABLATION-1 (with the contamination discipline the order asks for: historical LLM output is `ARCHITECTURE_RESULT_ONLY`; the forward Arena is the clean instrument). TEXT family in the panel: DECLARED ABSENT for v1, printed as such — not quietly missing. |
| 10–11 | NN v1 / Panel Transformer | **SEQUENCED.** mlp_2x64 is already an arm; deeper/multi-task NN and any transformer are gated on the v1 tournament's verdicts, with known-answer worlds first (the harness for that already exists). |
| 12 | Alpha-diversity books | **ACCEPT AS NEXT-AFTER.** `distinct_selection_signals: 1` is the number to move, but books are built FROM surviving signals; fronting books before the tournament reads is architecture-by-opinion. New IDs only, Gen-1 books never mutated. |
| 13 | PROFIT_ALLOCATOR_v2 | **GATED** on true OOS forecasts (this session may produce the first). Every-dollar-competes framing accepted; robust fractional Kelly accepted, full Kelly refused (rho=1 annotation stands). |
| 14 | RELIABILITY_ROUTER_v2 | **GATED** on the correlated-worlds G1 battery (pre-existing decision, unchanged). |
| 15 | Don't wait for the whole project | **ACCEPT.** This session ships receipt + panel + charter + first registered run. |

## What this session registers

`RETURN-PANEL-TOURNAMENT-1` — the first supervised screen on AEGIS_PANEL_V1.
Primary: paired per-date rank-IC difference, **LGBM on the full panel minus
LGBM on the price-only floor** (the incumbent instrument), 21d-forward return
incl. delistings, walk-forward 2016–2024, §64 masked audit before any verdict,
economic bar 0.01 IC, with an ADOPT-grade claim additionally requiring the
full arm's own pooled IC ≥ the bar. Everything else (model ordering, family
ablations, per-year paths) is SCREEN under BH-FDR, reported never deciding.

## What "no data problems" means after this order

The review's own correction is adopted verbatim: acquisition is closed;
semantics (PIT joins, publication lags, revisions, universe membership,
over-cap partitions by named consumer) are the remaining data work, and each
is owned by the consumer that needs it, never done speculatively.
