# REVIEW — 2026-09-04 — Fable 5.1 verdicts on the program (S37 mandate + Murat's reset)

**Who:** Fable 5.1 as reviewer/brain; eight Opus review agents on non-overlapping
surfaces; every number below was read from a file or re-derived in the
scratchpad, and the two decisive ones were re-derived twice.
**What this answers:** the ten claims in
`HANDOFF_2026-09-04_S37_TO_FABLE51_REVIEW_MANDATE.md`, the +250.9/+740.0
benchmark forensic, and Murat's reset question — *is the GPT review's
direction right, and what is actually wrong with the program?*
**Licence of this document:** RESEARCH_CLAIM standard for the negatives (they
are refutations with receipts); nothing here is an alpha claim.

---

## 0. RESULTS SCOREBOARD (the handoff convention)

| | |
|---|---|
| Best historical net strategy vs the market | **NONE STANDS.** Every tape receipt that reads `ratio`/`band`/`in_admissible` is void (§2). The learner v2 champion sits at the expected maximum of 44 noise trials (§1, claim 2). |
| Best forward paper strategy | hack4, −0.22pp vs SPY over 4 sessions; the other five trail SPY by 0.8–9.4pp (`aegis-alpha-terminal/state/benchmark_regret_20260903.json`). n = 4 sessions — directional, not a result. |
| Independent selectors live | 0 that survive review. |
| Farm candidates tested / promoted | 15 / 0 (unchanged). |
| New actionable findings | **9** (§3). Two are program-defining: the IBES share-basis defect and the exit machinery. |
| External execution drag | not computable: `state/decision_outcomes/` is empty on the laptop; the write-back lives only on the Railway volume. |
| LLM spend this session | $0. |
| RESULT IMPROVEMENT | **Negative and load-bearing**: the program now knows its analyst-target tape was corrupted, its states result is void, its champion is unadjusted for search, its books sell on a 3-day-drift rule, and its public benchmark was triple-compounded. Every one of those was invisible yesterday. |

---

## 1. THE TEN CLAIMS

| # | Claim | Verdict | What decided it |
|---|---|---|---|
| 1 | `\|shuffled-null t\|<2` was mis-specified; replacement = ≥64-draw model-null percentile, per pipeline, family max-stat for selected arms | **CONFIRMED (diagnosis) / REFUTED (replacement as implemented)** | Diagnosis right: a model fitted on shuffled targets is a fixed factor tilt evaluated on one realised factor path, so its t is not N(0,1). But the 64 v2 draws are 16 seeds × 2 arms × 2 heads from shared trunks (≈16 independent), the quoted p = 0.0154 is the 1/65 floor not a measurement, and `family_max_p` is **never called** in the v2 driver (`scripts/learner_v2_run.py:995-1116`) and in the v1 correction is fed the same statistic for every arm (`scripts/model_null_64_run.py:194-195`), so `null_max` is byte-identical to the single-arm null. The family correction across the ~48 cells has never been computed. |
| 2 | Learner v2 champion (`encoder_clf residual 1m`, net t 2.64) deserves frozen forward accrual | **REFUTED as a claim; ALLOWED as a shadow** | Chosen by `choose_champion` over 16 arms × 4 horizons after all cells were seen; TW was the declared primary and failed (3/64 nulls beat 18.28×, p 0.046), then t was promoted. Bonferroni over 11 ML arms at 1m: 0.17. Rough Deflated Sharpe: observed SR ≈ 0.88 vs expected max of 44 null trials ≈ 0.85. Paired vs the v1 champion: t 1.24. The residual target subtracts a prior fitted on the full 2013-24 window (`learner/prior.py:37-45` → `learner/dataset.py:522-524`) against an EW benchmark while the excess is VW. And `ratio` is one of its 49 features (§2). Shadow accrual costs nothing and may continue; it is not evidence. |
| 3 | BAND_PRIOR = exclusion only; `toxic_ge_5` survives FDR; 3-5 dead 2022-24; matched control +1%/yr | **REFUTED** | §2. Under the PIT ratio the "toxic" band is 7 names/month at **+37.4%/yr t +1.94**, and 3-5 is **−7.0%/yr**. The exclusion rule has no backtest support. The "8 FDR survivors" were one finding × 4 horizons × 2 universes. |
| 4 | Toxic-band short, beta-hedged, liq-floored: +76.6%/yr gross t 7.24, breakeven borrow 57% | **REFUTED** | 74.4% of the shorted name-months carry a **future** reverse split (§2) — the label is a future-collapse detector. Corrected band: naive short +9.6%/yr t 0.75, breakeven borrow 8.7%; fully PIT band: the long side wins. Also: the "hedged" gross embeds ~+27%/yr of equity premium on a 1.48× long market leg; `dlret` absent; no Reg-T capital. There is nothing to borrow against. |
| 5 | Revision-6M: cohorts remove a 2.9× phase lottery; edge pre-2022, −4.3pp/yr 2022-24 | **REFUTED as the contract's evidence base; CANNOT_DETERMINE as a mechanism** | The pool is the contaminated admissible region. Same daily engine, same `rev_top50` rule, only the admission column swapped: original TW 3.74 vs market 3.24 (+1.67pp, t 0.69) → cfacpr-corrected 1.68 (−7.2pp) → `ptgsumu` PIT 1.25 (**−10.4pp, t −1.02**). Pre-2022 with corrected admission: −0.35%/mo. Inside the PIT pool the revision *ranking* still beats all 32 random draws — relative information in a losing pool. To determine: run `rev_top50` over the full PIT hygiene universe, with `net_rev_1m` (IBES up/down counts) as a second definition. Forward power at the original effect: ~990 months for t=2, so paper cannot adjudicate it. `CONTRACT_DRAFT_2026-09-04_REVISION_6M.md` §8 must not freeze. |
| 6 | Fleet idle capital = UNCLASSIFIED driver bucket capping every tracker book at 40% gross | **CONFIRMED** | Re-verified from code: `alpha/drivers.py:71,129-135,224-243`, `alpha/admission.py:249-262`; sealed holdings carry only `sector` and nothing maps it to a driver. Fix (sector drivers at seal time) is **still queued**. Judgment on the fix: sector is the right *first* proxy; the durable one is a measured correlation cluster from the CompanyWorld graph (roadmap B5), and `utilization.py` must print which constraint BINDS. |
| 7 | Capital Allocator v0 design: cash requires a thesis, benchmark is the parking orbit, linear U | **CONFIRMED (direction) / REFUTED (v1 objective)** | The parking-orbit rule is right and matches the exit-side finding. But U is linear in \|maxDD\| labelled "CVaR", the benchmark's own U is penalised by its drawdown so a zero-excess sleeve can "beat" it, benchmark uncertainty is defined 0 while sleeve E's are estimates, and the artifact cites the floored v2 variant (t 2.87) as E. **No consumer exists.** v1: expected log-wealth with CVaR from quantile heads, sleeve covariance, benchmark uncertainty > 0. |
| 8 | PotentialUniverse v1 schema is the right substrate | **CONFIRMED as substrate; the ceiling is real** | 3,056 cards on 09-02, `OBSERVE_ONLY: 0` because `build(scope="observe")` was never run (`alpha/universe.py:73-76` says so). The v2 champion REFUSES on all 3,056 (23 full-panel columns absent) — the schema is right and the champion is the wrong consumer; a day-file model must be trained on day-file columns. |
| 9 | Unsupervised states: 4 OOS states; sizing vs stop-width tension | **REFUTED (void under its own bar)** | `persistent_shuffled_null` (`learner/states.py:853-917`), declared "the honest bar", was **never run by any driver**. Run on the sealed assignments (368,613 matured rows, 200 draws, 75 s): **p = 1.000 at k=3/4/5**, 0.95 inside `lt_1_5`. Observed spread sits *below* every persistent-null draw, so the two nulls bracket a name-path confound neither controls. Status: CANNOT DETERMINE, and the states semantics already propagated into `potential_universe.py:125-131` and the allocator's v1 plan must be marked UNVALIDATED. Receipt: scratchpad `persistent_null_result.json` (to be re-issued into `tracker_backtest/` by B4). |
| 10 | AEGIS-HORIZON-1: 12m level / 6m revision / no daily chart lane | **H3 CONFIRMED (stronger); H1 level-book REFUTED as a deployment; 6m-revision REFUTED; H4-H6 untested on a PIT universe** | The 1-day reversal's 19.97× gross is mostly bid-ask bounce (signal and fill at the same microcap close) — the true breakeven is below the quoted 5.48 bps. Under PIT admission the 12m level book is TW 1.09 vs market 3.41 (−12.2pp/yr, −62% DD): retire it (the external reviewer's call was right). Park-in-benchmark (H4) is a convention finding and likely survives; re-grade after the rebuild. |

---

## 2. THE DEFECT UNDER THE TAPE — split-adjusted targets over raw prices

`learner/dataset.py:228` loads **`ibes__ptgsum`**, IBES's *split-adjusted* consensus
(targets restated in end-of-sample share terms), and `:445` divides
`meanptg` by the **raw** CRSP close. `scripts/tracker_ibes_backtest.py:267`
states the premise — "the analyst target is quoted in today's dollars" —
and the premise is false for that file. The unadjusted file `ibes__ptgsumu`
sits beside it on disk, unused.

Verified twice (agent, then Fable directly): AAPL 2013-06-20 `meanptg` =
**19.323** in `ptgsum` vs **541.04** in `ptgsumu`; CRSP `prc` 398.07,
`cfacpr` 28. The tape's ratio for AAPL that month is 0.05 ("below 1.5");
the true ratio is 1.36.

Consequence: `ratio_used = true_ratio / cfacpr(t)`. A name that **later**
reverse-splits (cfacpr < 1) has its ratio inflated 10× to 1,000,000× and is
labelled `toxic_ge_5`; a name that later forward-splits is pushed into
`lt_1_5`. Reverse splits are what collapsing names do, so "toxic" is a
**future-collapse detector** — lookahead, not opinion.

| | original tape | corrected (`ptgsumu` / raw close, fully PIT) |
|---|---|---|
| toxic rows carrying a FUTURE reverse split | **74.4%** (lt_1_5: 0.09%) | — |
| `toxic_ge_5` 1m EW excess vs VW, 143 months | −35.2%/yr, t −5.79, 172 names/mo | **+37.4%/yr, t +1.94, 7 names/mo** |
| `b_3_5` | +13.4%/yr, t 1.28, 27/mo | **−7.0%/yr, t −0.67, 46/mo** |
| original toxic, split by cfacpr==1 vs <1 | −13.3%/yr t −1.66 vs **−48.9%/yr t −7.15** | |

Of 26,199 "toxic" rows, 2,965 stay toxic under PIT; 11,072 are really 1.5-3,
3,339 are 3-5, 8,823 are <1.5. BAND_PRIOR v2's four constants
(+2.41/+5.74/+16.55/−37.77) are artefacts of this mismatch. **Everything
downstream inherits it**: the admissible region [1.5, 5), the exclusion rule,
the toxic short, the revision pool, the level book, `ratio` as a learner
feature, the "+400% band = stale target" finding (which saw the symptom and
named the wrong cause), and the live BAND_PRIOR thresholds on the fleet
(the live rule reads unadjusted Finnhub targets — a *different object* whose
thresholds came from the corrupted tape; it has never been tested on itself).

Two more provenance defects, same panel:
- **Delisting returns were never merged.** `crsp.dsf.ret` carries no `dlret`;
  `crsp__dsedelist.parquet` is on disk and never joined; comments at
  `tracker_ibes_backtest.py:256,278` and `dataset.py:55-57` say otherwise.
  866 performance-coded delistings 2013-24 with mean `dlret` −24.6%. Longs
  are flattered; the panel is survivorship-free in membership, not in returns.
- The dsf pull covers a 6,894-permno "screened superset", not all shrcd 10/11.

**The receipts now void until re-issued on a rebuilt panel:**
`band_horizon_20260903`, `toxic_band_short_20260904`,
`holding_period_policy_20260903`, `revision_6m_cohorts_20260904`,
`exp_return_cross_section`, `upside_band_decontamination`,
`ibes_status_rules_2013_2024`, `time_machine_arena`, and the `ratio`-bearing
feature sets of `learner_v1`/`learner_v2`. They are not deleted; each gets a
`SUPERSEDED_BY` line when B1 re-issues it. Scratchpad working receipts:
`ratio_fix_rederivation.txt`, `ptgsumu_rederivation.txt`,
`hpp_rerun_fixed_admission.txt`, `hpp_rerun_ptgsumu_and_null.txt`,
`toxic_short_rerun_fixed_band.txt`, `delisting_audit.txt`.

The test that pins the fact is `backend/tests/test_ibes_target_share_basis.py`
(xfail-strict until the builder reads the unadjusted file).

---

## 3. THE NINE FINDINGS (beyond the ten claims)

1. **The public +740% was never a market.** `backend/services/backtest.py:95`
   downloads `^GSPC` (price index, no dividends); the 2026-03-30 code
   compounded all 66 *overlapping* 3-month forward windows as if sequential,
   which triples the log return. Reproduced on the pinned FF VW market: 66
   overlapping windows → +932%; every-3rd sampling → +107%. The bug was fixed
   2026-04-15 (`726c7bf`), `BACKTEST_RESULTS.md` was never regenerated, and
   ten docs copied it. The dividend-inclusive VW market 2020-01-02 →
   2025-05-30 is **+96.7%** (`backend/data/ff_daily_pinned.csv.gz`). The
   strategy's +250.9% carries the same inflation. Both numbers are withdrawn
   in this commit; B1 regenerates them from the current code against the
   canonical benchmark module.
2. **The books sell on a 3-day earnings-drift rule.** Every share position is
   closed at −3% (`alpha/exits.py:176-180` → `equity.py:231`, hard-coded,
   ignores the per-profile width — red-team R3) or +2.5% (`exits.py:181-185`,
   a PEAD constant "about twice the measured three-day drift"), with **no
   minimum hold** (the only precondition is `cost_basis > 0`, `:371`). The
   "horizon" used by the drift-window exit is sessions-until-contest-expiry
   (1.61 sessions on 09-03), not the book's 21-session thesis, and
   `tracker_portfolio.py:179-181` scales the 21-session expected return
   *down* to it. Those exits go through `close_position` with no
   `client_order_id`, which the re-entry guard cannot see (`protect.py:105`
   keys on `aat-stop-`), so the next 30-minute pass re-buys the name.
   Measured: **84% of identifiable round trips closed within one session**,
   median hold 0 sessions on hack3/4/6; TNXP stopped −3.5% and re-bought 86
   minutes later; MLYS cycled three times. No contract or book carries
   `expected_horizon` or `min_hold`. The S36 diagnosis "empty book ⇒ sell
   what dropped out" is **not in the code** — `exits.py` never reads the seal.
3. **The learning loop is silent where it matters.** The daily learning
   report on 09-03 said CANNOT DETERMINE in five of six sections; the
   refusal-regret marker has been dead since 08-28; `daily_autopsy` ran four
   days and stopped; `investigator_night` stopped 08-27; two receipts on the
   same day carry two different SPY closes (769.79 vs 773.115).
4. **The observation corpus is laptop-only.** 230,661 rows / 292 MB under
   `state/corpus/` are gitignored and never seeded to Railway, so every
   corpus-dependent brain on the authority runs on an empty store. This is
   why hack4 sealed EMPTY (d_catalyst unreadable ×810).
5. **"DeepSeek is the only provider" is a finance-backend fact, not a
   program fact.** The terminal already runs gpt-5-nano bulk extraction at
   $0.03/1k items, NVIDIA `nemotron-3-embed-1b` embeddings (341 calls), and a
   five-family council; Featherless ($25 credit, 394 calls) is absent from
   `fleet.SECRETS` so Railway can never use it; the finance repo's
   `GTP_TOKEN`, `HF_TOKEN`, `NVIDIA_BASE_URL`, EODHD and Alpha Vantage keys
   have no reachable caller. The NN trains on **CPU**: `torch 2.11.0+cpu`
   on a laptop with an RTX 5060 8 GB.
6. **The persistent causal graph is 94% one placeholder edge.** 514 of 545
   rows in `aegis-alpha-terminal/state/causal_graph.jsonl` are the literal
   schema example `a --SUPPLIES--> b` from one NVDA record. Nothing reads it.
   Meanwhile the best graph asset in the program — MARKET-GRAPH-1's 10,923
   permno-level competitor/customer/supplier edge instances (982 supplier,
   3,382 customer), filing-dated 2015-2024, H1 detectable at t 4.35 — sits
   frozen in the *third* repo (`Aegis module/runs/MARKET-GRAPH-1/`) with no
   consumer, and the scenario-bridge acquisition queue ranks "supply-chain
   edges" as its most expensive item without knowing they exist.
7. **Three 8-K item taxonomies.** `backend/services/edgar_events.py` (live,
   mounted, consumed by four services), `scripts/scenario_bridge.py:445`
   (mechanism vocabulary), and the new tape's `eightk_items.parquet` — none
   reconciled. The tape's ticker→CIK map resolves only 55.4% of panel
   permnos (survivor tilt); the historical link is derivable offline from
   `crsp.ccmxpf_lnkhist` + `comp.company.cik`, both already on disk.
8. **Optimus was serving stale, unranked memory.** Refresh is manual and was
   30 h behind; 600 of 1,015 pages (59%) were unregistered in the domain map
   and could never out-rank an in-domain page; the health page's regex looked
   for a heading that never existed; `aegis_verified_state` returned 47-53 KB
   and exceeded the client cap. **Fixed this session** (`optimus` repo: 4
   fixes, 13 new tests, 112 passing). Remaining lane in the roadmap.
9. **59 GB of WRDS substrate is on disk and ~55 GB of it is not in
   `DATA_MANIFEST.md`** (OptionMetrics, TAQ, CRSP daily, Compustat, IBES
   consensus, annual 13F) — the manifest's own rule is violated.

---

## 4. THE EXTERNAL REVIEW (GPT, via Murat) — adjudicated

The framing is right and adopted: *research is a subordinate service of a
profit product; the question is what the next dollar should own, for how
long, why, and whether that beat the best alternative.* Its P0 (benchmark
truth) and P1 (holding integrity) are exactly the two defects that cost the
most, and it named both without seeing the code.

Where it is right and already partly built (reuse, don't rebuild):
CompanyWorld → MARKET-GRAPH-1 edges + the typed autopsy schema
(`research_gym/autopsy.py`); Evidence Memory → `arena/trust_router.py`
(empirical-Bayes over actor × horizon × vol state) needs re-keying to
strategy × state and a write-back from receipts; Historical LLM PM →
T13 exists ($0.30, prose beats numbers-only by +0.64 TW) and needs the diary
arm, eras, cadences and a second decider; Strategy Evolution → the frozen
`PortfolioGenome` + max-stat null bar exist, lineage and mutation do not;
Capital Allocator → v0 exists, objective wrong, no consumer.

Where it is wrong or premature:
- It builds on the ten-claim receipts (revision-6M book, level book, toxic
  short). Those are void (§2). **Panel rebuild precedes every strategy
  decision.** Nothing else in the review changes, but the order does.
- "Learner v3 / four learners / graph NN" is premature: the champion is at
  noise maximum, the panel is corrupted, the NN is on CPU, and the honest
  inference library does not exist yet. New *information* (graph edges,
  dated events, delistings) is worth more than new architecture; B10 is last.
- "Search until we beat SPY in development, then prove on an untouched era"
  is right, with two additions it omits: CPCV/PBO on the development era so
  the *ranking* of genomes is trusted, and family-aware SPA over every genome
  looked at, charged to a persistent family budget (invariant 16).
- The Personal CIO daily object is right, but its prerequisite is a learning
  report that can compute its own sections (finding 3), not more fields.
- It under-weights T13's own caveat: calibration was negative in every arm.
  The LLM's licensed role is *ordering*; code prices.

---

## 5. WHAT CHANGED IN THIS COMMIT

- `backend/BACKTEST_RESULTS.md`, `README.md`, `NEGATIVE_RESULTS.md §1`,
  `docs/CANON.md`: the +250.9/+740.0 figures are **withdrawn** with a
  correction note; the direction of §1's verdict is kept as *unresolved
  pending regeneration* (it likely survives; it is not yet re-measured).
- `backend/tests/test_ibes_target_share_basis.py`: pins the share-basis
  fact on the file the builder reads (xfail-strict; skips when the local
  parquet is absent).
- `optimus`: domain registration + registry test, `aegis_verified_state(section=)`,
  staleness banner, health-page regex fix; 112 tests green.
- `docs/ROADMAP_2026-09-04_PROFIT_ENGINE.md` — the new TIER 1 roadmap.
- `docs/HANDOFF_2026-09-04_FABLE51_TO_OPUS5_BUILDER.md` — the builder
  contract and the first session's queue.
- `docs/INDEX.md` TIER 1 pointer.
- Nothing pushed, sealed, deployed or ordered (judging boundary; Murat
  pushes after 11:00 ET).

*Every negative in this file is a refutation of an implementation, not of a
mechanism (EXPLORE DIRTY, PROMOTE CLEAN). Analyst targets, revisions,
states, learners and the causal graph all remain open questions — asked
next on a clean panel with honest inference.*
