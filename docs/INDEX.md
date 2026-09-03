# docs/INDEX.md — what to read, in what order (2026-09-03)

268+ markdown files live here; many are roadmaps or handoffs. A new session must
NOT read them all. Tiers below; Optimus should embed TIER 2 and ARCHIVE for
retrieval and load TIER 0 + the current TIER 1 verbatim.

## The skim → read ladder (four rungs, stop at the one that answers you)

| Rung | Read | Cost | You now know |
|---|---|---|---|
| 0 | `../README.md` | 5 min | what Aegis is, the current headline results, the three licences |
| 1 | **this file** | 3 min | which of 268 docs answers your question |
| 2 | TIER 0 below (five files) + the ONE TIER 1 roadmap | 40 min | the invariants that outrank any roadmap, and the current plan |
| 3 | the receipt named beside the number | varies | whether the number survives being looked at |

**Never skip rung 3 for a number you are about to act on.** Every headline in
this repo names a JSON receipt; prose is the summary, the receipt is the fact.

Execution has its own index: `../aegis-alpha-terminal/docs/INDEX.md` (what seals
a day, what places orders, what grades us, where the receipts are).
Big local artefacts that are deliberately NOT committed are catalogued in
**`DATA_MANIFEST.md`** — check it before concluding a dataset was never pulled.

## TIER 0 — CANON (changes a few times a year; read every session)
- `AEGIS_STRATEGIC_INVARIANTS.md` — the sixteen points.
- `AEGIS_VISION_2026-08-28_MURAT_IN_HIS_OWN_WORDS.md` — the intent, verbatim, with corrections and the one missing artery.
- `AEGIS_VISION_2026-08-30_LOG_REVISION_ERA_REPLAY.md` -- TIER 0 addendum (30 Aug): two independent LLMs, the news funnel, the anonymised/fantasy ERA REPLAY backtest (T13), and why the books were not deciding.
- `OPTIMUS_OBJECTIVE.md` §0 — mission, utility, four personalities.
- `../CLAUDE.md` — operating rules + `CLAUDE_LESSONS_2026-08.md` — long-form lessons, farm findings, layout and tests.

## TIER 1 — CURRENT ROADMAP (one file; supersedes dated execution roadmaps)
- **`ROADMAP_2026-08-31_COMPETITION_WEEK_WORLD_MODEL.md` — ACTIVE:** Mon 31 Aug → Fri 4 Sep. Exact sealed-portfolio→runner P0; hard-vs-experimental boundary taxonomy; world sensor mesh; canonical event compression; text→numeric CompanyState; whole-market candidate generators; opportunity recall; continuous experiment factory; NVIDIA QSD/NeMo/Data Designer roles; learning-loop/NN promotion order; competition-week scoreboard.
- `ROADMAP_2026-08-26_HUMAN_HEURISTICS_AND_FAST_RESEARCH.md` — standing lane inventory/gates. It supplies research lanes to the active roadmap; it is not a competing execution plan.
- `ROADMAP_2026-08-29_WEEKEND_TO_MONDAY.md` — **SUPERSEDED 2026-08-31** by the active roadmap above. Keep as the receipt for Friday attribution and weekend build decisions.
- Competition execution lives in the OTHER repo. Enter it through **`aegis-alpha-terminal/docs/INDEX.md`** (TIER 0 + the MAP), then its `docs/HANDOFF.md` top block (which now carries a 6-line SKIM LAYER) and the newest `NEXT_SESSION_*.md`. Those are implementation handoffs, not strategic authority.

The standing artery remains:
`WORLD SENSORS → EVIDENCE → PERSISTENT CAUSAL GRAPH → MARKET EXPECTATIONS → DIVERGENCE → EXPRESSION → ADMISSION → REALITY → LEARNING`.

## TIER 2 — FINDINGS WITH RECEIPTS (retrieve by question; each has a JSON receipt)
- `FINDING_2026-08-28_THE_CORE_WAS_NEVER_PRICED.md` — 11.9M OptionMetrics quotes; short put spread core refuted. **⚠ BROKEN POINTER (checked 2026-09-02): this file is NOT in this repo.** It lives in the execution repo as `../aegis-alpha-terminal/docs/FINDING_2026-08-28_THE_CORE_WAS_NEVER_PRICED.md`. Left listed on purpose — the finding is real and the line is how sessions find it; do not delete, either move the doc here or correct the path once someone decides which repo owns it.
- `FINDING_2026-08-25_THIRTY_TWO_YEARS_DID_NOT_RESOLVE_IT.md` — 60.7 years needed; time is the lever.
- `FINDING_2026-08-25_ASK_THE_CROSS_SECTION_FIRST.md` — quantile SHAPE decides construction.
- `FINDING_2026-08-25_BREADTH_WAS_THE_LEVER.md` — 12-year verdict reversed on 32 years.
- `FINDING_2026-08-24_HOLDING_PERIOD.md` — the farm's seven lessons.
- Knife basket / rebound split receipts: `backend/data/optimus/knife_basket_2013_2024.json`, `knife_rebound_split_2013_2024.json` (dip-buying high-vol names loses at 5 sessions; the paying cell was an artefact).
- SUE × reaction quadrants (commit 7db0126): the REACTION carries the information.
- Everything else `FINDING_*.md` / `DECISION_*.md` by date.

### LANDING TODAY — 2026-09-03 (announced by their authors; NOT on disk when this line was written)

Other sessions are writing these right now. **Verify before quoting**: if the
file is not there, it is still being written, and a fact from a file that does
not exist yet is not a fact. Listed so the next session finds them without a
grep, and so a missing one is visibly missing rather than silently forgotten.

- `FORENSICS_2026-09-03_HEALTH_EPISODE.md` — forensics on a health/uptime episode.
- `TRIAL_RESULT_2026-09-03_BAND_HORIZON.md` — the readout of `PREREG_BAND_IS_BETA_1`: is BAND_PRIOR v2 a one-month selector at all, or a twelve-month prior being sampled monthly? Producer: `scripts/band_horizon_run.py`; the suspicion it tests is the horizon monotonicity in the chart at `assets/band_prior_by_horizon.png`.
- `RESEARCH_2026-09-03_HOLDING_PERIOD_POLICY.md` — holding-period policy; the same question from the portfolio side.
- `LEARNER_V2_2026-09-03.md` — the successor to LEARNER v1 below.
- `STATES_2026-09-03_UNSUPERVISED_V1.md` — unsupervised state discovery (`learner/states.py`).

### NEWEST — landed 2026-09-03

- **`TRIAL_RESULT_2026-09-03_BAND_HORIZON.md` — the band prior attacked on its own terms.** Receipt: `backend/data/optimus/tracker_backtest/band_horizon_20260903.json`. Executes `PREREG_BAND_IS_BETA_1` + the random-order arm of `PREREG_RANK_VS_EXPRETURN_1`. Three corrections. (i) **The prior's "IC t 34.5 at 12m" is an overlap artefact** — `n_effective` is 8, not 96; the block t is FLAT (14.6 → 13.6) across 1/3/6/12m while the naive t climbs 14.6 → 44.2, and the IC level's rise is *sub-√h*. **The money runs the other way**: the 3-5 band earns +18.9 → +10.4 → +5.5 → +7.3 pp/yr as the horizon lengthens, so the 21-session clock is the best clock this overlay has. (ii) **+16.55%/yr is not a market excess** — it is measured against the analyst-covered panel's own EW mean (`tracker_ibes_backtest.py:564`); against the VW market the same book is **+18.93%/yr, t_block 1.65** (t 2.25 against the panel). (iii) **Not beta/size**: a matched outside-band basket at the same beta decile × cap decile earns **+1.02%/yr**. BH-FDR over 32 tests leaves **only `toxic_ge_5`**; Holm exports **nothing** for the 3-5 band. `RANK_VS_EXPRETURN` resolves **NO-DIFFERENCE** — and random ordering (4.21×) beats the sealed expectation field (2.94×), with all three arms losing to buy-and-hold VW (6.75×). New code: `learner/beta.py` (pre-period beta, PIT-guarded by `backend/tests/test_learner_beta_pit.py`), `scripts/band_horizon_run.py`.

### NEWEST — landed 2026-09-02 (verified on disk 2026-09-03)

- **`backend/data/optimus/tracker_backtest/learner_v1.json` — LEARNER v1, the headline of the week.** `PRODUCT_EXPERIMENT`, pre-registered 2026-09-02 *before any model was fitted*; 441,278 name-months, 144 months, 5,713 names; 12 arms walk-forward 2016-2024 with a shuffled-target null. Champion `lgbm_clf`: rank IC **0.0954, t 8.21** (null 0.0046, t 0.81 — clean). **The money is the weaker claim**: the top-50 VW book is **t 1.49** paired vs the market, one arm of twelve. The finding that matters is *where* the skill is — IC **0.137 (t 8.79)** where the engine has NO OPINION, **0.058 (t 5.58)** in the band it calls toxic, and **0.002 (t 0.10)** inside ratio 3-5, the band it actually buys. Code: `learner/`, `scripts/learner_run.py`, `scripts/learner_shadow_seal.py`. Sealed shadow book: `backend/data/optimus/learner/shadow_book_2026-09-02.json`. Charts: `assets/learner_v1_engine_is_silent.png`, `assets/band_prior_by_horizon.png`. Train tables are parquet and NOT committed — see `DATA_MANIFEST.md`.
- `REDTEAM_2026-09-02_ENGINE_AUDIT.md` — the money path attacked rather than reviewed: sizing arithmetic, the sealed-weight chain, gate ordering, stops, PIT integrity of the seal, ledger tearing, config drift. **20 findings (2 critical, 5 high)**, each tagged CONFIRMED-REPRODUCED / CONFIRMED-IN-SOURCE / PLAUSIBLE and each with a dollar shape. Four risk guards were found unable to fire at all. Scope is the OTHER repo's engine; findings are actioned there.
- `HYPOTHESES_2026-09-02_HARVEST.md` — every receipt from 08-30 → 09-02 mined for observations that are surprising, **precursor-bearing** and killable. 17 typed candidates; the top two attack our own band prior. **Hypothesis generation only** — nothing pre-registered but the three drafts in §3, nothing traded, no lane seeded.
- `RETRO_2026-09-02_THE_MONTH_OF_DATA.md` — the month-of-August retrospective. Receipt: `backend/data/optimus/tracker_backtest/month_retro_20260902.json`. ~6.0 GB across 31 dataset families bought **12,233 rows** of PIT-clean forward observation. The biggest single loss was a name **our own rule refused** (RZLV, −17.30%, `claims: false`, held at 10% anyway), and it was the only company-specific loss that day — the other twelve were leverage at **mean market beta 2.10**. BAND_PRIOR v2 is the month's best decision and it is measurable.
- `backend/data/optimus/tracker_backtest/holder_h2_h3.json` — holder provenance H2/H3 on the full 13F panel, 23.3m events / 74.7M position-quarters. **Identity is thin** (t 2.24, ~5bps per 1sd — under costs); the duration intuition **inverts** (NEW by a long-duration filer underperforms — index-reconstitution confound, needs 13D/G to separate); a manager's own top-decile stake is **−1.21pp/252 sessions, t −3.95 — adverse**. Only matched differences are readable; the EW benchmark is a size artefact. Sibling summary: `holder_fingerprint_summary.json`. Raw panel is >20MB and untracked — `DATA_MANIFEST.md`.
- `CASE_2026-09-02_GPRO_HOLDER_ATTENTION.md` — the first concrete instance of holder provenance. Miss type **NOT OBSERVED**, not wrongly rejected: the liquidity floor did NOT exclude GPRO (~$4.0m/day ADV clears the $3.0m floor) — **universe construction** did, and `alpha/sources/sec.py` watches 8-K Item 2.02 only, never 13D/13G. Case file + draft typed hypothesis; `PRODUCT_EXPERIMENT` sought, `RESEARCH_CLAIM` explicitly not. Sibling: `IDEA_2026-08-31_HOLDER_PROVENANCE_TO_THE_ROOTS.md` (H1–H7).
- `backend/data/optimus/tracker_backtest/analyst_target_grades.json` — 1.33M individual 12-month analyst targets graded on `amaskcd` (the analyst as a person, across firms). **BIAS persists (Spearman 0.376, deciles −2.8pp → +80pp); ACCURACY barely does (0.087).** Skill-weighting must be bias-first. Row-level grades are local-only parquet — read `read_me_first` before quoting.
- `backend/data/optimus/tracker_backtest/time_machine_arena.json` — monthly frozen dates 2015–2024, four eras, seven minds, four horizons, plus the disagreement miner. AEGIS-admissible positive at 1m in **all four eras**, decaying by 12m ⇒ a monthly-refresh signal. Carries an `anachronism_note`; row-level parquet is local-only.
- `backend/data/optimus/tracker_backtest/exp_return_cross_section.json` — receipt EXP-RETURN-XS-1, the BAND_PRIOR v2 evidence. **Within the buyable region six stock features have NO rank** (FM |t| < 1.5 over 143 months) ⇒ constants-per-band is the measured state of knowledge. Also the engine-vs-street 2×2 and both calibration tables. `in_sample_note` is load-bearing.
- `backend/data/optimus/tracker_backtest/topn_concentration.json` — top-N concentration vs the top-500 value-weighted benchmark. Verdict is **MIXED full-sample / REGIME-CONDITIONAL every era**: its own `verdict.reading` says do not quote the full-sample ratio before reading `era_ratio_vs_top500_vw`.
- Also in that directory (older, same lineage): `upside_band_decontamination.json` (the believable extreme target is the toxic one), `ibes_status_rules_2013_2024.json`, `holder_fingerprint_summary.json`.

## ARCHIVE — `docs/archive/`
Digest-only. They record what was true when written; a fact from them must be
re-verified against code or a receipt before it is acted on. Do not load the
archive wholesale into context; retrieve by question through Optimus.

## Rules for this index
- **Verify a pointer before writing it, and FLAG a broken one rather than deleting it.** A wrong path in an index costs more than a missing one; a silently deleted line loses the finding. Every path above was checked against disk on **2026-09-03** — one break is flagged in TIER 2, and the five "LANDING TODAY" files are flagged as absent-by-design because another session is writing them as this line is read.
- **A number in this index carries its receipt path.** If you cannot name the receipt, the line does not belong here — it belongs in a handoff.
- Data that is too big to commit is not missing; it is in `DATA_MANIFEST.md`.
- Figures live in `assets/` and are regenerated, never hand-edited: `python tools/readme_charts.py [chart …]` reads the live track-record API and the frozen receipts. Numbers on a chart are read from JSON, never retyped.
- One current roadmap at a time. A new roadmap file REPLACES the active TIER 1 line here or it is not the roadmap.
- A handoff is a session's diary, not a source of truth; the truth is code, receipts and TIER 0.
- Anything Murat says about intent goes into the VISION file (dated section), never only into a handoff.
- A competition implementation brief may be newer than the strategic roadmap on wiring details, but it cannot silently change the objective or invariants.