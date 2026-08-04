# Research prompts — Gate M + Stage T (2026-08-04)

How to use: each prompt below is self-contained — paste ONE prompt per
deep-research run. G1–G4 are for Gemini deep research (literature + method
verification). O1 is for a fresh Opus session in this repo (implementation
design). Bring the answers back and we fold them into the Gate M build.

Standing instruction embedded in every prompt: **no fabricated citations** —
Gemini invented 4 of 6 novel references in the last round (FinCAD, Fonseca,
AlgoXpert, LdP-Lipton-Zoonekynd). Every prompt demands verifiability.

---

## G1 — Factory Calibration Monte Carlo (the M1 centerpiece)

> I run a retail-scale quantitative research pipeline that screens stock
> strategy candidates through: an explore(2004-2018)/confirm(2019-2024)
> holdout wall, placebo gates (random-date and permutation controls), a
> Deflated Sharpe Ratio computed against the full history of 179 candidates
> ever tried, and a t≥3 discovery bar. I am building a "factory calibration"
> experiment: inject KNOWN alpha (annualized Sharpe contributions of 0, 0.2,
> 0.4, 0.6) into synthetic stock panels, run the UNCHANGED pipeline on them,
> and measure (a) false-discovery rate at zero alpha and (b) false-KILL rate
> at each real alpha level — then use the resulting mapping to convert
> "pipeline said X" into a calibrated posterior probability the edge is real.
>
> Research questions — for each, cite only sources you can verify exist, and
> explicitly say "unverifiable" if you cannot confirm a reference:
>
> 1. **Synthetic panel realism.** What does the literature say about
>    generating realistic equity cross-sections for this purpose? Compare:
>    stationary/block bootstrap of real returns, factor-model simulation
>    (systematic loadings + resampled residuals), and parametric models with
>    vol clustering and cross-sectional correlation. Which failure of realism
>    most distorts false-discovery/false-kill estimates (fat tails?
>    cross-sectional dependence? autocorrelation)? Is there published work on
>    simulation-based validation of backtest evaluation pipelines
>    specifically (not just of strategies)?
> 2. **Alpha injection design.** How should injected alpha be structured to
>    be a fair test — constant vs decaying, concentrated in a sub-universe vs
>    diffuse, correlated with size/liquidity or orthogonal? What injection
>    designs would let a miscalibrated pipeline look calibrated?
> 3. **Evidence → posterior mapping.** Given a grid of (injected alpha →
>    pipeline verdict) outcomes, what is the right way to build a calibrated
>    posterior P(edge real | pipeline evidence)? Relate to simulation-based
>    calibration in Bayesian statistics (Talts et al.) and to Harvey & Liu's
>    work on multiple testing and "lucky factors" — are those the right
>    anchors, and what am I missing?
> 4. **Sample size.** With ~1,000 replications per alpha level, what
>    precision do I get on a false-kill rate near 50%, and is stratification
>    or common-random-numbers variance reduction worth it?
> 5. Name any published or open-source system that already does this
>    (evaluating the evaluator with injected signal), in finance or adjacent
>    fields (genomics FDR calibration, A/B testing platforms, clinical trial
>    simulation). Verified names and links only.

## G2 — Dependence-aware multiple testing at N=179

> I have a complete ledger of 179 strategy candidates ever evaluated by my
> pipeline (grouped into ~15 families by data source and mechanism; families
> are internally correlated). Four survivors passed. I need to decide whether
> survivors beat the multiple-testing bar once dependence is accounted for.
>
> Questions (verifiable citations only; flag anything you cannot verify):
>
> 1. Practical comparison for THIS scale — 179 trials, ~15 correlated
>    families, monthly return series 2004-2024: Romano-Wolf stepdown vs
>    Hansen's SPA test vs Model Confidence Set. Which is most appropriate
>    when the trials were run sequentially over months and some share data?
>    What are the standard implementations (R/Python packages) and their
>    pitfalls?
> 2. Effective number of independent trials: what estimators exist
>    (eigenvalue-based, correlation-block-based, Meff from genomics), how
>    unstable are they, and is there a defensible default when many of the
>    179 never produced a full return series (killed at an early gate)?
>    How should "killed before producing returns" trials count?
> 3. Empirical σ_SR: I plan to estimate the cross-candidate dispersion of
>    Sharpe ratios from my own ledger rather than assume the theoretical
>    iid value. Is there precedent (Harvey-Liu-Zhu cross-section of t-stats?)
>    and what biases does conditioning on my own selection process introduce?
> 4. The Harvey-Sancetta-Zhao 2026 lower-bound framework (NBER w34898) — 
>    summarize what it implies for a shop whose ledger IS complete (no hidden
>    trials): does a complete private ledger justify a lower hurdle than
>    t≥3, or does publication-iceberg logic still bind through the shared
>    literature the ideas came from?

## G3 — Permutation placebo specification (pre-registration for M2)

> My event-study placebo gate previously used uniform random-date placebos
> and we documented that they can falsely kill real signals under "cohort
> drag" (event firms cluster in calendar periods with poor cohort returns; a
> uniform random date escapes the cohort and looks better than the real
> signal). The fix we converged on: permute event dates ACROSS firms while
> preserving the calendar marginal (each real event date is reassigned to a
> different firm). Before re-reading two closed decisions under this spec, I
> need the spec bulletproof and pre-registered.
>
> Questions (verifiable citations only):
>
> 1. Is firm-permutation-preserving-calendar the standard? Relate to
>    randomization/permutation inference (Fisher; Athey & Imbens on
>    randomization tests), bootstrapped event studies (Kothari-Warner
>    methodology reviews), and placebo practices in empirical corporate
>    finance. What are the known failure modes of ACROSS-FIRM permutation
>    (e.g., when treatment propensity correlates with firm characteristics —
>    size, industry clustering of events)?
> 2. Should permutation preserve the event-count-per-firm distribution, the
>    industry marginal, or both? What stratification is standard
>    (size/industry-matched permutation)?
> 3. Inference details: how many permutations for a stable p at the 5% level;
>    one-sided vs two-sided given a directional hypothesis; how to pool
>    multiple event types — fixed pooling rule registered in advance vs
>    seed-level reads. What does the literature say about "the analyst reads
>    many permutation seeds and reports one" as a garden-of-forking-paths
>    risk, and what protocol prevents it?
> 4. Operating characteristics: how do I measure the false-kill rate of THIS
>    placebo design itself (connects to my factory-calibration experiment —
>    inject a known event-day effect, run the permutation gate, measure kill
>    rate vs effect size)?

## G4 — Social-alpha literature audit (Stage T preparation)

> I am about to test five pre-registered hypotheses on newly certified data:
> BoardEx board/director network (full North America, linked to CRSP at
> 98-99.8% of market cap point-in-time), SEC Form 4 insider filings, IBES
> analyst coverage, Thomson 13F holdings, and news/attention series. The
> thesis: non-price "social" information — who sits on which boards, network
> quality, fund ownership structure, political alignment — carries slow
>-moving information the market underweights.
>
> For EACH claim below: (i) verify the canonical papers exist and say what
> they actually found, (ii) report post-publication replication status and
> decay if documented (Chen-Zimmermann open-source asset pricing, McLean &
> Pontiff), (iii) list the main data pitfall that produces a false positive.
> No fabricated citations — say "cannot verify" where applicable.
>
> 1. **Connected-director insider clusters**: purchases by directors who sit
>    on multiple boards, clustered in time across their firms, outperform
>    isolated purchases. Anchors to check: Cohen-Frazzini-Malloy (school
>    ties / "Decoding inside information"), Cohen-Malloy-Pomorski
>    (opportunistic vs routine trades), Cziraki et al. on insider networks.
> 2. **Independent-director departures** predict negative events
>    (restatements, class actions, underperformance) — especially "surprise"
>    departures early in expected tenure. Anchors: Fahlenbrach-Low-Stulz;
>    Gao-Huang on director resignations; Agrawal-Chen.
> 3. **Board network centrality** and returns: Larcker-So-Wang 2013 (board
>    centrality premium) — did it replicate? Is the premium concentrated in
>    small caps? What has happened to it post-2013?
> 4. **Institutional vs retail attention divergence**: Ben-Rephael-Da-
>    Israelsen (AIA vs SVI); retail attention spikes with institutional
>    selling as a negative signal. What is the current evidence and does
>    anything survive controls for momentum and size?
> 5. **Political alignment as priced information**: PAC contributions
>    (Cooper-Gulen-Ovtchinnikov), lobbying intensity, government contract
>    awards, revolving-door hires. Which of these has held up, at what
>    horizon, and with what data sources that a retail researcher can
>    legally access (LDA filings, FEC, USAspending)?
> 6. For each of 1-5: what would a SKEPTIC say is the most likely non-alpha
>    explanation (risk loading, liquidity, microcap concentration, data
>    -snooping), and what single control would most cheaply kill it?

## O1 — Opus implementation-design brief (M1 build)

> Context: you are in the aegis-finance repo. Read
> `docs/AEGIS_EXECUTION_ROADMAP.md` (Gate M), `docs/CANON.md`, and
> `docs/AI_REVIEWS_SYNTHESIS_2026-08-03.md` §3 (factory calibration idea) +
> §7b. The Strategy Factory explore/confirm harness lives in the engine/
> and lab/ directories; the 179-candidate ledger and gate history are in the
> experiment registry.
>
> Task: produce a full implementation DESIGN (no code yet) for the Factory
> Calibration Monte Carlo:
> 1. Synthetic panel generator — recommend ONE concrete DGP (with fallback):
>    inputs, calibration targets (cross-sectional vol, pairwise correlation,
>    factor structure, fat tails), and how it reuses our real CRSP monthly
>    panel (fresh, certified 2026-08-04: `crsp_msf_full.parquet`) without
>    leaking real alpha into the "null" panels.
> 2. Alpha injection — exact mechanics (which stocks, what magnitude maps to
>    Sharpe 0.2/0.4/0.6, decay profile), and the injection-design traps from
>    the pipeline's perspective.
> 3. Harness integration — how to run the UNCHANGED pipeline on synthetic
>    panels (what needs mocking: data loaders only; what must NOT be
>    touched: gates, thresholds, DSR arithmetic), and how to keep one run
>    under a laptop-night compute budget.
> 4. Outputs — the exact tables: false-discovery at α=0, false-kill at each
>    α, and the evidence→posterior mapping the sizing ladder consumes; plus
>    the two paper exhibits.
> 5. A staged build plan with a kill criterion per stage (mirror our Gate
>    philosophy), sized so stage 1 lands in one session.
> Constraints: config in backend/config.py or a dedicated config, seeded
> rng (np.random.default_rng), no network in tests, every silent-failure
> path must raise (house rule: code that runs green and does nothing is the
> enemy).

---

*When the answers come back: G1+O1 feed the M1 build; G2 feeds M3; G3 is the
M2 pre-registration input (the spec gets registered BEFORE re-reading §30/§31);
G4 sharpens the T1-T5 trial designs and their placebo batteries.*
