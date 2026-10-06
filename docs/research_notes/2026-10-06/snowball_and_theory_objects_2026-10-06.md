# The analyst snowball, the identity-weighting question, and a theory-object table (2026-10-06)

Researcher pass, read-only on code and git. No file other than this one was written. No trial was
registered — §1 is a DRAFT for the orchestrator to run `lint_prereg.py` on and sign. Python was run
against `backend/data/optimus/analyst/target_revisions.parquet` (local data, no write), to answer
"what is on disk" before proposing anything. `brain_query` and `aegis_postmortems` were queried first
(below); the corpse search inside this note is from reading the committed receipts and verdict docs,
not from the `Aegis module` linter, which this session could not run (no code execution of that
sibling repo was in scope).

**One line on the identity framing, stated once, undramatically:** every "analyst identity" or
"government-supported company" feature below is built only from public economic variables — broker
firm name, historical hit rate, dollar amounts of contracts/lobbying/subsidies, ownership of equity —
never from a covered person's religion, ethnicity, or any other protected-class attribute. None of the
owner's framings asked for one; this is a statement of what was built, not a correction of what was
asked.

---

## 0. What the brain already holds (consulted before anything below)

- `brain_query("first-mover analyst snowball ... n>=5 filter")` surfaced
  `aegis-module-trials-prereg-analyst-skill-1` and the HANDOFF/SPEC pages — the live registered trial
  is the one this draft resurrects with a new instrument (§1.5).
- `brain_query("analyst skill filter ... effect size bias accuracy")` surfaced
  `reference-analyst-bias-persists-accuracy-does-not` (1,333,683 12m targets graded vs CRSP, 2005-2024:
  bias persists, accuracy does not) and the 16-cell ownership/analyst-identity ablation
  (`aegis-docs-features-2026-09-03-ablation`) — a **16-cell negative** on identity features, read in
  §2.
- `brain_query("lobbying ... PAC ... congress")` and `brain_query("52 week range ... hyp_lab cells")`
  both returned only the general dossier and `TRIAL-CONGRESS-IC` — **no lobbying/PAC/subsidy/contract
  trial exists anywhere in the brain.** That absence is itself the finding for several theory-table
  rows below: NEEDS_DATA, not ALREADY_CLOSED.
- `aegis_postmortems` (no narrow match; returned the general session log) confirmed the standing
  traps that govern this note's own numbers: print by year before believing a positive, block by the
  dependence unit the swept parameter implies, and a prior chosen after the diagnostic is not a prior
  (`feedback_a_prior_chosen_after_the_diagnostic_is_not_a_prior.md` — §2's reputation-weight spec below
  is written so that sector/horizon buckets are fixed by construction, not chosen after seeing which
  bucket wins).

---

## 1. SNOWBALL — pre-registration DRAFT (NOT registered)

**Status: DRAFT only.** This researcher does not register trials. Before registration the orchestrator
must run `cd "<home>/Aegis module" && python scripts/lint_prereg.py <this draft, extracted>`.
Named corpses to feed it, found by reading receipts (not by running the linter):

- **Nearest same-mechanism closure:** `docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md`
  §2 — "Lead/chase, first mover, analyst skill: CANNOT_DISTINGUISH... **This closes these
  implementations.**" That implementation used `crsp_pit_bridges.first_movers(raises, gap_days=30)`
  (`backend/services/crsp_pit_bridges.py:317`) and tested `first_mover_raises` as a **cross-sectional
  ranking signal held one month**, benchmarked against a matched twin and the market.
- **What is different here, and must be named in the registration (`lint_prereg.py` requires an
  instrument, not just "we are trying again"):** three changes, not one —
  1. the quiet gap is **90 days**, not 30 (a dry spell long enough to span most of a quarter, matching
     the owner's "3 quarters" framing for the snowball to fully unwind);
  2. the **primary object is the follow-through count** (how many distinct firms raise within 21/63
     sessions of the quiet-break raise), not a held cross-sectional portfolio return — this is an
     event-count/probability question, not a book;
  3. the forward return is read **conditioned on nothing after t0** (next-session-forward only, no
     portfolio construction, no twin-matching cost model) — closer to `TRIAL-PT-REVERSAL-1`'s shape
     (one clean event-study read) than to the library-rule book shape that was closed.
  - **Resurrects:** the CRSP-bridge `first_mover_raises_90` closure (above) and
    `ANALYST-SKILL-1`'s broker-level weighting (§2) — **new instrument:** the 90-day quiet-gap
    event-count object, reusing `crsp_pit_bridges.first_movers(raises, gap_days=90)` as the literal
    build path (the function already takes `gap_days` as a parameter; nothing new needs to be
    written to get the t0 flag — only the follower-count and the forward-return legs are new code).
- **Other near neighbors, not duplicates:** `pit_features.revision_clusters` / `first_mover_features`
  (`backend/services/pit_features.py:365-420`) compute first-mover/follower leadership on the
  **yfinance** `target_revisions.parquet` instrument with `CLUSTER_GAP_DAYS = 7` — an order of
  magnitude shorter window, feeding `strategy_library_ext`'s `first_mover_leadership` /
  `skilled_leader` rules. Those have **not** been run standalone on CRSP (the 09-29/09-30 CRSP closure
  used the IBES/CRSP bridge, not this yfinance path) and are not resurrected by this draft; they are a
  fourth, shorter-horizon instrument of the same broad idea, separately alive.

### 1.1 Hypothesis

After a US-listed name goes >= 90 calendar days with no sell-side 12-month price-target raise by any
covered broker ("quiet"), the first raise that breaks the quiet period ("t0") is followed by raises
from additional, distinct brokers at a rate detectably above the unconditional base rate of broker
activity on that name, **and** the SPY-relative forward return from t0 is positive on average —
honest prior: the **follow-through (snowball) leg is plausible** (analysts are known to cluster and
anchor on each other, and this is the mechanism the 7-day and 30-day instruments already show some
life in before costs eat it), the **return leg is weak-to-null** (every analyst-revision-as-a-book
closure so far — `net_raises`, `ear_flow`, `first_mover_raises_90`, the revision tilt on two bases —
has been a real ranking against a matched twin that dies against the market; there is no reason a
longer quiet-gap variant escapes the same twin-drag).

### 1.2 The t0 event (frozen)

- **Universe and instrument:** CRSP/IBES via `crsp_pit_bridges` (survivor-free, PIT-linked,
  `ibcrsphist` on the event date) — the same instrument as the closed 30-day version, not the yfinance
  393,839-row file. The yfinance file (below, §1.4) is used ONLY to size the MDE and print the by-year
  count before registration, because it is what this read-only pass could query directly; the
  registered run must use the CRSP/IBES bridge for the actual decision (survivorship and the
  look-ahead-safe link matter more here than in a quick count).
- **t0:** a 12-month USD target raise (`ptgdetu`, sign = raise) by broker *b* on permno *p*, dated
  max(anndats, actdats), usable from the next business day, such that no OTHER broker raised *p* in
  the **90 calendar days strictly before** t0's event day, AND *p* has at least 90 days of raise
  history before that window (so a name's first-ever covered raise, or a name re-entering coverage,
  is not counted as a "snowball start" — it has no quiet period to break).
- **Named analyst reputation prior:** computed **only from claims resolved before t0** —
  `pit_features.firm_reliability` already does this (edge = hit rate - direction-conditional base
  rate, shrunk `n/(n+20)`, mapped to a weight in [0.5, 1.5]); §2 below is the spec for extending it
  by (source x sector x horizon) instead of leaving it broker-flat.

### 1.3 Primary metric (two parts, both pre-declared, neither substitutable after the read)

1. **Follow-through:** `P(>= 2 distinct OTHER brokers raise the same permno within 21 sessions of t0)`
   and the same at 63 sessions. Binary, no portfolio, no cost model — this is a question about analyst
   behavior, not a return.
2. **Forward return, conditioned on nothing after t0:** SPY-relative open-to-close return from the
   session after t0 is knowable, held 21 and 63 sessions, reported gross and at the engine's own
   flat-band cost schedule. This is the leg every prior book-shaped version of this mechanism has
   failed; it is reported as a mean with a t-stat, never gated on the follow-through outcome (that
   would be conditioning on the future).

### 1.4 The MDE from the data on disk (yfinance instrument, 393,839 rows, this session's own count)

Computed from `backend/data/optimus/analyst/target_revisions.parquet` (393,839 rows, 2,993 tickers,
467 firms, 2011-12-08 to 2026-10-05, `pit_safe == True` on every row). `target_action == "Raises"`:
170,240 rows after exact-duplicate drop. A t0 event = a raise with no other-firm raise on the same
ticker in the trailing 90 calendar days, **and** at least 90 days of prior raise history on that
ticker (excludes coverage-start artifacts — 27,190 candidates drop to **24,323** once that exclusion
is applied, a 10.5% correction that matters: without it the count and the follow-through rate are both
biased by names just entering the panel).

**t0 events by year** (90-day quiet gap, real prior history required):

| year | t0 events | | year | t0 events |
|---|---:|---|---|---:|
| 2012 | 397 | | 2020 | 1,761 |
| 2013 | 1,113 | | 2021 | 1,811 |
| 2014 | 1,279 | | 2022 | 2,058 |
| 2015 | 1,124 | | 2023 | 2,317 |
| 2016 | 1,203 | | 2024 | 2,737 |
| 2017 | 1,022 | | 2025 | 2,622 |
| 2018 | 1,454 | | 2026 (partial, to 10-05) | 1,992 |
| 2019 | 1,433 | | **total** | **24,323** |

2,668 distinct tickers carry at least one t0 event; 741 distinct ISO weeks and 174 distinct months span
the full sample. 2012-2016 is visibly thinner (397-1,279/yr) than 2020+ (1,761-2,737/yr) — the same
coverage-growth shape every other analyst-panel note in this repo has flagged; a registered run should
either start the design window at 2017 (19,207 of the 24,323 events, 2,658 tickers, 118 months) or
treat 2012-2016 as a separate, lower-power stratum.

**Follow-through, measured on this instrument (calendar-day proxy for 21/63 sessions — 30d and 93d;
the registered run must convert to an actual trading calendar, this is a sizing exercise only):**

| horizon | P(>=1 other firm follows) | P(>=2 other firms follow — the "snowball") |
|---|---:|---:|
| ~21 sessions | 39.5% | **18.0%** |
| ~63 sessions | 60.1% | **35.9%** |

By year, the snowball-63 rate rises from ~18-33% in 2012-2017 to 35-45% from 2020 on (table available
on request; the direction is monotonic enough that a design/validate split by era, not just by random
fold, matters for this trial same as it has for every revision-flow trial this quarter).

**MDE, stated honestly:** the follow-through leg is comfortably powered — at n=19,207 (2017+) and a
base rate near 0.36 for the 63-session snowball, blocked by the 118 distinct months (the dependence
unit, because events cluster in time the way every other analyst-flow trial here has found), the
month-blocked SE is on the order of a percentage point or two depending on within-month correlation;
a 5pp shift in the snowball rate is comfortably resolvable. **The return leg is the one that needs the
honest prior from history:** `net_raises` (same broad mechanism, different window) measured a gap
against the market of -0.58%/mo in validation with spreads, and `first_mover_raises_90` closed
CANNOT_DISTINGUISH at a twin-t of 3.4-3.6 that evaporated against the market. A declared effect for
the return leg smaller than roughly 0.3-0.5%/21d should be assumed undetectable at this corpus size
without a much larger multi-decade pull, following the same logic `TRIAL-CONGRESS-PTR-FWD-1` used to
register itself `REGISTERED_UNPOWERED` rather than pretend a small live table answers a 7pp-MDE
question.

### 1.5 Control

Matched non-first-mover raises: raises on the SAME ticker, SAME rough period, by brokers who raised
within the 90-day quiet window broken by t0 (i.e., the "chasers" who would have been excluded as t0
candidates) — mirrors the `lead`/`chase` split already computed in `crsp_pit_bridges.analyst2_panel`
(`lead = raise & ret10 <= 0`, `chase = raise & ret10 > sig10`). A second control: a size/sector/vol
matched random raise-date sample of the same size, same convention as every other library-rule twin in
this repo.

### 1.6 Earliest decision date

If registered on the CRSP/IBES instrument with the design/validate split at 2008/2009 (matching every
sibling trial's 1991-2008 design / 2009-2016 validate convention): **validate reads once, in one
sitting, after the design-window follow-through parameters (which quiet-gap variant, if any, beats a
no-variant baseline) are fixed.** No interim read. Given the data is already fully on disk (no forward
accrual needed, unlike `TRIAL-CONGRESS-PTR-FWD-1`), the earliest decision date is **the day the
orchestrator runs it**, not a future calendar date — this is a backtest question, not a forward-accrual
one.

### 1.7 The look-ahead trap, closed explicitly

Two traps, stated so the implementation cannot drift into them:

1. **The t0 flag itself must not peek at the outcome.** `first_movers()` already enforces this by
   construction (it only reads `day - gap_days` to `day`, nothing forward) — the risk is in the
   *follow-through* and *return* legs, which must never be joined back into the t0 definition. A
   rule that defines "the real snowball starts" by retroactively finding the best-performing raise
   in a cluster is not this trial.
2. **The reputation prior must resolve before t0, not merely be computed on a window ending before
   t0.** `firm_reliability`'s `RESOLVE_DAYS = 92` margin exists for exactly this: a claim is only
   counted once its outcome is actually knowable, not merely once its target date has nominally
   passed. Any reputation feature built for this trial must call the existing function (or its
   extension, §2) with `asof = t0`, never with a window that includes claims whose resolution lands
   after t0 even if the claim itself predates it.

### 1.8 Licence

**PRODUCT_EXPERIMENT at most, and arguably not even that yet.** The follow-through leg (§1.3.1) is a
pure descriptive/behavioral measurement with no cost model and no capital implication — it can run and
be reported as context immediately, no registration needed for that half alone, same standing as
`revision_clusters`' existing descriptive columns. The return leg (§1.3.2) is the part that needs the
registration above, because every sibling version of "analysts cluster, trade it" has been tested as a
**RESEARCH_CLAIM-adjacent** backtest and closed CANNOT_DISTINGUISH or worse against the market. Nothing
here should be proposed as a `CAPITAL_CANDIDATE` or `RESEARCH_CLAIM` — the honest prior from four
closed siblings (`net_raises`, `first_mover_raises_90`, the two revision tilts) is that the return leg
dies the same way. If it does not, that itself is the finding worth a `RESEARCH_CLAIM`-grade follow-up,
not this draft.

---

## 2. Analyst identity weighting: what ANALYST-SKILL-1 found, and the n>=5 replacement

### 2.1 What was actually found (`docs/ANALYST_SKILL_1_VERDICT_2026-09-26.md`, cited in full)

- Registered rule's word: **ADOPT**. ΔIC = +0.00084, paired t (NW-3) = 2.52, 71 months, on the
  registered WRDS instrument (`tr_ibes.ptgdetu`, 1,032,849 targets, 364 brokers with measured skill).
- **But:** the effect is **1/12 of the prereg's own declared "worth building" size** (0.010), and the
  mechanism is **attenuation of an anti-signal consensus**, not added ranking information — the
  skill-weighted consensus sits closer to zero than the equal-weighted one in 70% of months
  (corr(ΔIC, IC_ew) = -0.46, slope -0.0072 t -4.98); it HELPS when the raw consensus is wrong (50 of 71
  months) and HURTS when the consensus actually works (21 of 71 months, mean ΔIC -0.00089 there).
  Adjudicated in the brain as `ADOPT_AT_TRIVIAL_EFFECT — the branch is not funded`.
- **The report-only rows (never deciding the §3 verdict), in the order the verdict doc gives them —
  this is almost certainly the "3rd point" asked about:**
  1. Design leak measured (estimation-window leak into 2019): re-estimating skill only from
     pre-2019-resolved targets gives ΔIC +0.00077, t 2.35 — same shape, so the leak is not what
     produced the result.
  2. **Analyst-LEVEL weighting (`amaskcd` — the individual human, not the broker firm): ΔIC +0.00035,
     t 1.32. That would have been REJECT had it been the deciding level.** This is the direct answer
     to "can one named analyst outweigh five others": it was tried, at the finest identity grain the
     data supports, and it did not clear the bar the firm-level version barely cleared.
  3. Target-accuracy skill vs. recommendation-reliability skill: Spearman 0.37 across 169 brokers
     (two different skill notions the project has built — IBES target accuracy vs. the actor-corpus
     claim-resolution reliability used in `pit_features.firm_reliability`) — they agree only
     moderately. **This matters for the owner's "one JPM analyst may outweigh five others" framing:**
     there isn't one "skill" number per analyst to rank by; the project already has two, and they
     disagree 63% of the time on relative ordering.
- Also report-only, and relevant to the n>=5 question directly: a **16-cell ownership/analyst-identity
  ablation (`aegis-docs-features-2026-09-03-ablation`, surfaced by `brain_query`, not re-read in full
  here) is recorded in the brain as a negative** — identity-shaped features have failed before at a
  different cut than this one.

### 2.2 Concrete spec: replacing `n >= 5` with reputation-weighted consensus

The coverage-count gate (`n >= 5`, or the `>= 3 brokers` convention used for `target_cv_180` and
similar dispersion features in `crsp_pit_bridges.py`) is a crude stand-in for "the consensus is
estimated precisely enough to use." The machinery to replace it with a reputation weight **already
exists** at the broker-firm level — `pit_features.firm_reliability` (edge = hit rate minus the
direction-conditional base rate on claims resolved as of `asof`, shrunk `n/(n+20)`, weight
`= clip(1 + 10*shrunk_edge, 0.5, 1.5)`) and is consumed by `skill_features`. What it does NOT yet do,
and what the owner's "source x sector x horizon" ask requires, is condition that edge on anything
besides the broker identity:

1. **Replace the single `groupby(firm_col)` in `firm_reliability` with a three-level hierarchy:**
   `edge(firm, sector, horizon)` shrunk toward `edge(firm)` shrunk toward `edge(global)` — standard
   nested (James-Stein-style) shrinkage, same shrink-toward-pool logic the function already uses, just
   with the pooling target itself pooled. A firm with 400 claims overall but 8 in semiconductors at the
   12-month horizon should weight close to its sector-conditional edge only once that sub-count clears
   its own `SKILL_SHRINK_K`-scaled threshold; below that, it falls back to the firm-wide edge, which
   falls back to the market-wide prior (`SKILL_PRIOR = 1.0`) — never to a hard binary admit/reject gate.
2. **This directly retires the `n >= 5` cliff.** A name with 2 covering brokers is not excluded; its
   consensus is built from however many reputation-weighted opinions exist, with the weight itself
   carrying the "how much do I trust this with only 2 voices" information instead of a separate
   coverage filter doing a worse job of the same thing.
3. **Thin-history shrinkage, stated as a frozen parameter (not tuned after seeing results, per the
   standing "a prior chosen after the diagnostic is not a prior" rule):** keep `SKILL_SHRINK_K = 20`
   at the top (firm) level — it is already the "prereg family's convention," per the code comment —
   and set the sector x horizon sub-level's own K at least as large (claims at a sector x horizon cut
   are a strict subset of a firm's claims, so they saturate slower; a reasonable frozen default is
   `K_sub = 2 x K_firm = 40`, stated here as a proposal for the orchestrator to freeze, not as a result
   of any search).
4. **What this spec does NOT change:** the existing attenuation finding. If the underlying consensus
   object (upside level) is an anti-signal, a finer-grained reputation weight will still mostly damp
   it rather than add information — §3 of the verdict doc already recommends testing skill-weighting
   on a consensus object with positive base IC (revision FLOW, not upside LEVEL) before funding more
   provenance engineering. The sector x horizon extension should be tried on `net_raises`-style flow,
   not on target-upside level, or it repeats the same attenuation-vs-information confound at higher
   resolution.

---

## 3. Theory-object table

Columns: mechanism | observable precursor at decision time | data HAVE (path) or NEED (free source) |
affected universe | horizon | falsifier | already tried (corpse) | verdict.

| # | mechanism | precursor at decision time | data | universe | horizon | falsifier | already tried | verdict |
|---|---|---|---|---|---|---|---|---|
| 1 | Successful founder/CEO alignment | insider-officer open-market BUY with no subsequent sale filed in N days (PIT-observable: "no sale yet" is knowable in real time) | HAVE (partial): `backend/data/optimus/sec_insider/insider_events_v1.parquet` (3.1M rows, 2006-2026, officer/role flags). NEED: founder-vs-hired-CEO roster (free: proxy-statement DEF 14A bios, or a hand list) | US officers with insider Form-4 history | 63-252d | buy-without-sale cohort beats generic insider-buy cohort net of the market | `insider_officer` FAILED_VARIANT, all 15 library insider rules 3/15 positive in validation (`docs/research_notes/2026-09-29/analyst_insider_on_crsp_2026-09-29.md`) | NEEDS_DATA (founder flag); the generic buy mechanism it sits on is ALREADY_CLOSED as specified |
| 2 | Very-high-margin / monopoly economics | gross-profit/assets, operating-margin stability over trailing 3-5y, low capex intensity | HAVE: `quality_composite`, `ope_be`, `gp_at` on the Compustat fundq bridge (`backend/services/crsp_pit_bridges.py`) | US equities with Compustat coverage, 1991+ | monthly hold | survives vs the MARKET (not just the twin) net of costs, t>=2, majority of years positive | **ALREADY_CLOSED as a stand-alone capital idea**: `quality_composite`/`ope_be` SURVIVE vs twin (t~6, DSR 0.98) but are DEPRIORITIZED vs the market (t 0.15-0.34) — `docs/research_notes/2026-09-30/bridges_and_conditionals_2026-09-30.md` | ALREADY_CLOSED (vs market); a true monopoly/pricing-power proxy (margin stability + revenue concentration, not raw margin level) is a NOT-YET-TRIED variant, so NEEDS_DATA for the concentration leg only |
| 3 | CEOs who buy AND HOLD (never sell) their own stock | insider has an open-market buy in the trailing 180d and has filed ZERO sales since that buy (PIT-safe: absence of a sale is observable as of any later date) | HAVE: `insider_events_v1.parquet` already carries both buys and sales per CIK/permno | US officers, 2006+ | 63-252d | buy-and-hold cohort beats a buy-then-sometimes-sell cohort, both vs the market | Close cousin tested (`insider_buyers`, `insider_opportunistic`, `mom_with_insider_buying` — all CANNOT_DISTINGUISH/FAILED_VARIANT) but NONE of those 15 rules conditions on subsequent non-selling; this specific cut is new | READY_TO_CELL — reuses existing parquet, needs only a new conditioning column |
| 4 | Regime-supported companies (gov't contracts, subsidies, industrial policy) | dollar value / count of federal contract awards to the company (or its CIK's known subsidiaries) | NEED: USASpending.gov bulk award data (free, https://www.usaspending.gov/download_center/award_data_archive) — not on disk; no hit anywhere in `docs/` or `backend/services/` for "government contract" or "subsidy" | US government-contractor names (small hand list exists informally: LMT/RTX/NOC/GD/LHX/BAH/SAIC/LDOS-type names) | quarterly/annual | contract-award-growth cohort beats a matched twin AND the market, PIT (award is public at announcement, not retroactively) | none found | NEEDS_DATA |
| 5 | Congressional influence (lobbying $, PAC activity) | dollar amount of lobbying disclosures (Senate LDA) and PAC contributions (FEC) per company, PIT by filing date | NEED: Senate LDA bulk XML/CSV (free, https://lda.senate.gov/system/public/) and FEC bulk data (free, https://www.fec.gov/data/browse-data/?tab=bulk-data) — not on disk | US public companies with lobbying registrations | quarterly (LDA filings are quarterly) | lobbying-growth cohort beats a size/sector matched twin AND the market | **Distinct from, but thematically adjacent to,** `TRIAL-CONGRESS-IC` (closed, FMP feed) and `TRIAL-CONGRESS-PTR-FWD-1` (REGISTERED_UNPOWERED, accrual-only, member TRADING disclosures — not lobbying spend) | NEEDS_DATA |
| 6 | Fiscal-year-end (Sept 30) federal budget spend-down, gov't contractors/schools | seasonal revenue/order-flow uptick in Aug-Sept for federal-fiscal-year-exposed names | NEED: same USASpending data as #4, PLUS a universe tag (NAICS/SIC code or hand list) | federal contractors + school-supply/ed-tech names | seasonal (annual recurrence) | the Aug-Sept effect beats the same names' own other-month baseline AND the market, across >=5 fiscal years | none found | NEEDS_DATA (universe tag is the cheap missing piece; the seasonal-return test itself is a simple `hyp_cells`-style design once the universe exists) |
| 7 | Rare earths / copper / lithium demand from semis + robotics | commodity spot/futures price momentum and backwardation, conditioned on semis capex guidance text | HAVE: FRED commodity series via `backend/services/macro_indicators.py`; equity bars; `news_intelligence`/world-digest text for capex-guidance mentions. NEED: granular robotics install-base data (IFR, not free/not on disk) is a nice-to-have, not a blocker | miners/producers (ticker list needed but cheap: FCX, ALB, MP, etc.) vs semis/robotics names | 5-21 sessions (macro shock), quarterly (capex-guidance) | the existing `hyp_cells.macro_lead_lag` cell framework, same shape as the already-run oil-shock-to-airlines and yield-shock-to-banks cells | the SAME cell type found no detectable lag for oil-to-airlines and yield-to-banks on 2026-09-29 (`docs/research_notes/2026-09-30/hypothesis_lab_2026-09-30.md`) — a near-identical mechanism class, CANNOT_DISTINGUISH | READY_TO_CELL tonight — reuses `hyp_cells.macro_lead_lag` verbatim, only the commodity series and target basket change |
| 8 | Oil names benefiting from a Venezuela/oil-shock | oil price shock (continuous) -> E&P basket residual return; separately, a Venezuela-specific political event (discrete, text-tagged) | HAVE (continuous leg): FRED oil series via `macro_indicators.py`, same `macro_lead_lag` cell. NEED (discrete leg): a geopolitical event tagger on Venezuela-specific news — the typed-event student (`ft_lab`) tags `event_type` generically but has no Venezuela/sanctions-specific class yet | oil E&P basket (XOP-like) | next-session to 5 sessions | same macro_lead_lag design; beats the market and a matched twin | the oil-shock cell direction already run was oil->AIRLINES (the inverse exposure); oil->E&P is the un-run complement of the same cell type | READY_TO_CELL (continuous oil-price leg, immediately); NOT_A_HYPOTHESIS_YET for the Venezuela-specific discrete event until a tagger exists to separate it from "oil price moved" generally |
| 9 | Peptides/obesity supply chain (GLP-1 CDMOs, peptide API makers, packaging) | thematic basket co-movement / lead-lag off the GLP-1 majors (LLY, NVO) | HAVE: bars panel, co-mention/correlation-peer machinery (`graph_propagation.py`, the text-co-mention and return-correlation cells run 2026-09-29). NEED: the specific obesity-supply-chain ticker universe (hand-curated; not on disk) | small/mid-cap CDMOs and specialty-chem suppliers | next-session to 21 sessions | thematic-peer read-through beats random peers AND decays faster than the twin's own drag | **Same mechanism class already measured and found dead at the one horizon that matters:** "text co-mention links carry LESS same-session read-through than return-correlation peers, and neither carries anything into the NEXT session" (`hypothesis_lab_2026-09-30.md`); `MARKET-GRAPH-1` closed the portfolio route for graph co-movement generally | NEEDS_DATA (universe) to even cell it, but the honest prior from the closed sibling mechanism is low — flag as NEEDS_DATA-with-a-corpse, not a fresh idea |
| 10 | China / EM growth | China PMI / EM-index surprise -> EM-revenue-exposed US multinational residual return | HAVE: FRED/macro series (China PMI, EM indices) likely already reachable via `macro_indicators.py`; equity bars | US multinationals with disclosed China/EM revenue exposure | 5-21 sessions | same `macro_lead_lag` design | not directly tried (the macro-lead-lag cells run so far are oil->airlines and yield->banks/REITs, not China/EM) | READY_TO_CELL — same reusable cell type, new series and basket |
| 11a | Prediction markets as a sensor | Kalshi/Polymarket implied-probability shift on a macro/political contract, lagged into a related equity sector | HAVE: `prediction_markets.py`, `prediction_market_matching.py`, PIT daily snapshots already running (`TRIAL-PREDMARKET-1/2`) | whatever sector a given contract maps to | event-dependent | the registered PREDMARKET successor trial itself (not yet passed) | **Explicitly barred from any scoring path until a successor trial passes** — the module's own docstring: "Nothing in any scoring path ... may read this corpus before a successor trial passes"; R1 found 6/6 LLM forecasters LOST to the crowd at Brier | READY_TO_CELL as a fresh `macro_lead_lag`-shaped test of the sensor itself (not yet attempted as a lead-lag, only as a direct-trading comparison that failed) — must clear its own gate before composite use regardless of outcome |
| 11b | Crypto state as a sensor (BTC/ETH risk-sentiment) | BTC/ETH return or realized-vol regime -> risk-asset basket lead-lag | NEED: confirm whether a BTC/ETH price series is already pulled anywhere (no hit found in this pass) | broad risk baskets | 1-5 sessions | same `macro_lead_lag` design | none found | NEEDS_DATA (series not confirmed on disk) |
| 12 | 52-week-range / day-range price-location features | `px_vs_52w_high`, `px_vs_52w_low`, day-range/ATR position | **HAVE and ALREADY CODED:** `backend/services/strategy_library.py` (`hi52`, `hi52_large`, `hi52_q`, `hi52_gp`, `lowvol_hi52`, `flow_hi52`), `backend/services/xs_ranker.py` (`px_vs_52w_high/low`, `px_vs_ma50/200`), `backend/services/technical_analysis.py` (`pct_from_52w_high/low`) | full CRSP universe | monthly | beats the market net of costs, t>=2 | `flow_hi52` (combo with net_raises) is already in the appendix of `analyst_insider_on_crsp_2026-09-29.md`: twin t **-1.5**, DSR 0.000 — **FAILED_VARIANT**. Standalone `hi52` was not found by name in any CRSP-run receipt grepped this session (it may be inside the 209-rule momentum sweep referenced in MEMORY S60 under different naming, not confirmed) | **READY_TO_CELL tonight at $0** — the feature already exists in three places; only a standalone CRSP library-rule run (not a combo) is missing. The combo version is already a closed corpse (cite it so nobody re-discovers `flow_hi52` as new). ATR-based day-range position specifically was not found coded anywhere — that piece is NEEDS_DATA (small build, not a data gap) |
| 13 | Back-to-back earnings beats raising the bar (expectations ratchet) | count of consecutive quarterly beats (IBES actual > estimate) on a name, as a NEW conditioning variable, tested against subsequent miss probability / return | HAVE: IBES actuals already bridged with PIT timing (`crsp_event_bridge.py`'s `ear_*` family, `eap_raises`, `ear_fresh`, `ear_mom`, `ear_drift`) | full CRSP universe with IBES coverage | next-quarter event | consecutive-beat cohort's NEXT earnings reaction is worse (ratchet) or better (momentum) than a single-beat cohort, net of costs | **Adjacent, opposite-signed siblings already run and closed:** `ear_drift`/`ear_mom` (continuation, the standard PEAD shape) decay post-2009 and are DEPRIORITIZED; none of the 12 `earnings_event` rules conditioned on a STREAK count | READY_TO_CELL — reuses the existing `ear_*` bridge, adds one new rolling-count feature, no new data pull |

---

## Summary for the orchestrator

- **Snowball count (yfinance instrument, this session's own numbers):** **24,323** t0 events
  (90-day quiet gap, real prior history required) across 2012-2026, 2,668 distinct tickers, by year
  397 (2012) rising to 2,737 (2024); follow-through to >=2 other brokers within ~63 sessions is **36%**
  overall, rising from ~18-33% pre-2020 to 35-45% from 2020 on. The follow-through leg is well powered;
  the return leg is not — assume an MDE floor near 0.3-0.5%/21d given the size of every sibling
  closure's measured gap, and register accordingly rather than reading a small table as an answer.
- **13 theory-object rows:** **6 READY_TO_CELL tonight at $0** (rows 3, 7, 8-continuous, 10, 11a, 12,
  13 — seven, not six, counting both parts of row 8; row 3 and 13 need zero new data, only a new
  conditioning column on data already on disk; rows 7, 8-continuous, 10 reuse the existing
  `hyp_cells.macro_lead_lag` cell type verbatim with a new series/basket; row 12 needs one standalone
  CRSP run of a feature that already exists in three files; row 11a needs the sensor tested as a
  lead-lag, which has not been tried even though direct trading from it is barred). **4 NEEDS_DATA**
  with a free source named (rows 4, 5, 6, 9, 11b — lobbying/PAC/USASpending/crypto-series/obesity-
  universe). **2 touch an ALREADY_CLOSED corpse** that should be cited, not re-discovered (row 2's
  margin-level mechanism vs the market; row 12's `flow_hi52` combo). **0 are NOT_A_HYPOTHESIS_YET**
  outright, except the Venezuela-specific discrete-event half of row 8, which needs a tagger before it
  separates from "oil price moved."
- **Top 3 cells to run tonight at $0**, in order of cheapest-to-build x most likely to teach something
  new (none of these commit capital or register a claim):
  1. **Row 12, standalone `hi52`/`px_vs_52w_high` as a CRSP library rule** (not the already-closed
     `flow_hi52` combo) — the feature is coded in three places and has apparently never been run alone
     on the survivor-free panel; cheapest possible new information.
  2. **Row 3, insider buy-and-hold conditioning** on the existing `insider_events_v1.parquet` — zero new
     data, one new boolean column, and it is the one insider cut none of the 15 already-run rules
     tested.
  3. **Row 13, consecutive-beat streak conditioning** on the existing `ear_*` earnings bridge — zero
     new data, directly answers whether the market over- or under-reacts to a ratcheting bar, and sits
     right next to `ear_drift`/`ear_mom`, which already have design/validate numbers to compare against.
