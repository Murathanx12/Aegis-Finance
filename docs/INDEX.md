# docs/INDEX.md — what to read, in what order (2026-09-02)

268+ markdown files live here; many are roadmaps or handoffs. A new session must
NOT read them all. Tiers below; Optimus should embed TIER 2 and ARCHIVE for
retrieval and load TIER 0 + the current TIER 1 verbatim.

**Skim order:** TIER 0 (five files) → the ONE TIER 1 roadmap → then jump to a
TIER 2 line by the question you arrived with. The execution repo has its own
index now: `../aegis-alpha-terminal/docs/INDEX.md` (what seals a day, what
places orders, what grades us, where the receipts are).

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

### NEWEST — landed 2026-09-01/02 (verified on disk 2026-09-02 unless noted)
- `RETRO_2026-09-02_THE_MONTH_OF_DATA.md` — **LANDING TODAY** (being written as this index line is added; not yet on disk at 2026-09-02). The month-of-August retrospective: what the data programme bought and what it did not.
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
- **Verify a pointer before writing it, and FLAG a broken one rather than deleting it.** A wrong path in an index costs more than a missing one; a silently deleted line loses the finding. Every path above was checked against disk on 2026-09-02 — one break is flagged in TIER 2 and one artifact is marked "landing today".
- One current roadmap at a time. A new roadmap file REPLACES the active TIER 1 line here or it is not the roadmap.
- A handoff is a session's diary, not a source of truth; the truth is code, receipts and TIER 0.
- Anything Murat says about intent goes into the VISION file (dated section), never only into a handoff.
- A competition implementation brief may be newer than the strategic roadmap on wiring details, but it cannot silently change the objective or invariants.