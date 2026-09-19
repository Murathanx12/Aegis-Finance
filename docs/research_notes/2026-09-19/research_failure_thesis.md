# Research-Failure Thesis: What Actually Killed Each Negative Result, and What Is Still Open

Source read in full: `NEGATIVE_RESULTS.md` (3,254 lines, 57 sections, repo root).
Cross-checked against `docs/AEGIS_STRATEGIC_INVARIANTS.md` and nine `docs/TRIALS/`
pre-registrations (`TRIAL-MOM-BACKTEST-12-1-momentum.md`,
`TRIAL-MOM-TREND-momentum-with-trend-filter.md`, `TRIAL-CRASH-2-severity-model.md`,
`TRIAL-CRASH-fragility-composite.md`, `TRIAL-INSIDER-IC.md`,
`TRIAL-H5-event-learner-five-session.md`, `PREREG_N9_MINE_THE_85.md`,
`ERRATUM_N21_NULL_AND_POWER_ARITHMETIC.md`, `TRIAL-LEAK-1-identified-vs-masked.md`).

## EXECUTIVE SUMMARY (read this first)

1. Of 57 ledger entries, roughly 14 are genuine mechanism deaths on modern,
   cost-honest data (momentum-timing, LPPLS, FDA drift, regime-rotation,
   vol-targeting, residual momentum, option-implied levels, 13F ownership,
   analyst targets, LLM trading alpha) — consistent with Chen & Velikov's
   finding that the average post-publication anomaly nets ~4bps/month after
   costs. These should NOT be revisited without a new mechanism class.
2. At least 6 entries (§32, §34, §36, §38, §40, §41) are **the ruler's fault,
   not the pool's**: gates with measured ~0% statistical power, `n` used
   where `n_effective` was owed, a denominator that manufactured refutations.
   §34 alone shows the pre-recalibration gates adopted a true, injected
   α=0.6 edge with probability 0.000. §35's replay under fixed gates turned
   0-for-179 into 10 adoptions overnight — same data, same candidates.
3. A recurring, unresolved pattern (§26, §27, §28, §35 addendum) shows large,
   statistically enormous rank information (IC t up to 11.3) sitting in a
   short leg a long-only book cannot hold. This is not dead — it is
   **untested as an exclusion screen**, which the ledger repeatedly notes and
   never runs. This is the single cheapest re-test in the file.
4. The 13D/13G activist-disclosure family (§29-31) is the ledger's only
   confirmed positive event effect (CAR +152bps at t 2.37, placebo-controlled
   against 13G) and it is **closed as UNMEASURABLE, not unharvestable** — two
   monthly-entry book designs both failed their own random-date placebo
   gates before producing a number. Nobody has tried entering inside the
   already-confirmed announcement window instead of waiting for month-end.
5. The crash/timing family (§1, §2, §6, §7, §33) is dead on three
   independent designs and confirmed dead a second time after two data leaks
   were found and closed (§33) — this is a real, well-powered result, not a
   ruler artifact, and should stay closed.
6. Costs were checked directly against the paper's lead exhibit (§25,
   Corwin-Schultz vs Kyle-Obizhaeva) and disagree by 3.4-9.1x on LEVEL while
   agreeing on RANK — but the exhibit survives because its verdicts are
   decided by cost-independent legs (gross t, zero-cost bound). Costs are
   NOT the reason most of this ledger is empty.
7. One place costs (and the associated liquidity floor) ARE the whole
   story: the final entry, TRIAL-H5, shows a placebo-trained control's own
   level moves from +3%/yr to +18%/yr between a $3m and $10m liquidity floor
   — the control, not just the candidate, is floor-sensitive. This has never
   been checked against the small-cap replay adoptions (§35) or the
   small-shelf graduates (§22), which used similar flat-cost/turnover
   conventions.
8. §34/§36/§41 together license a full replay of every "failed the explore
   threshold only" verdict in the pre-recalibration ledger — already partly
   done (§35) for the small segment; large/mid was included in that replay
   and produced zero adoptions, so it is measured-empty, not unmeasured.
9. §49 (N8) and §50 (N2) quantify, for the first time, WHY crisis-conditioned
   macro/crash mechanisms keep failing to reach significance: crisis
   dispersion is ~12x calm dispersion, so the same edge costs 144x more
   episodes to detect. A 10pp-or-larger effect is testable with the
   corpus we can assemble; anything under 5pp is not, on index-level data,
   regardless of collection effort.
10. §51 (N4) shows the precursor library covers only 15% of exceptional
    moves — at the base rate. This is a coverage problem, not a validity
    problem, and per §49's own preamble it is fixable at ~$0.001 per LLM
    autopsy.
11. §52 (N6) is probably the most economically useful clean result in the
    file: second moments (volatility) are robustly predictable and a
    single trailing realised-vol number matches a 14-feature LightGBM model
    exactly — build the risk head, not another return-direction model.
12. Genuine data/coverage constraints (not measurement or mechanism)
    account for a smaller share than intuition suggests: §4 (survivorship)
    was solved by the WRDS CRSP entitlement; §8 (EODHD) was superseded by
    the same fix; §50 shows international equity data buys much less
    independent evidence than its nominal episode count implies (1.3x, not
    8x) because of cross-market correlation.
13. Five cheapest, highest-leverage re-tests, in priority order, are named
    in §THESIS below: (1) reframe io_level/skew/io_abn as exclusion screens,
    (2) an event-window (not month-end) 13D book, (3) LLM-autopsy precursor
    library expansion (N9's own recommendation), (4) a $10m-floor re-audit
    of the §35 replay adoptions and §22 small-shelf survivors, and (5) the
    TAQ empirical cost curve applied directly to the two KO-half graduates
    in §22 that fail only the stress cost arm.
14. The house's own account of itself changed materially over the file's
    span: sections 1-33 read as "the pool is empty"; sections 34-41 prove
    the ruler used to read it was broken; sections 42-56 are almost all
    process/measurement bugs (calendar, cache, default-argument binding),
    not strategy results — the project spent real effort on instrument
    hygiene, which is why the later entries are trustworthy in a way the
    earlier explore-only rejections are not.
15. Bottom line for "are we limiting ourselves on what other people failed":
    partly, but not mainly. The bigger self-limitation was an unmeasured
    ruler (§34/36/41) that manufactured its own kills for a year, and an
    unexploited exclusion-screen construction that the ledger itself
    flagged three times and never ran.

---

## PART 1 — SECTION-BY-SECTION TABLE

Columns: **§** = section number in `NEGATIVE_RESULTS.md` · **Tested** = mechanism
class / construction / universe / era / cost model · **Why failed** =
`MECH` mechanism genuinely dead · `CONSTR` construction/design dead ·
`RULER` measurement/gate/denominator defect · `DATA` coverage/data defect ·
`POWER` n or n_effective too small · **Open** = what the section's own text
leaves untested · **Doable now?** with which held dataset · **Cost** = rough
CPU-hours / $ LLM, order of magnitude only.

| § | Tested | Why failed | What's still open | Doable now (data held) | Est. cost |
|---|---|---|---|---|---|
| 1 | Signal-engine sell/buy timing vs SPY B&H, 2020-2025, quarterly compounding, 32bps/rt | MECH — sell signals fire at high-VIX bottoms; forward return is positive after every one | Forward, leak-free event-driven paper lane (already the stated path) | Already running (paper lane) | $0 |
| 2 | Crash model 3m/6m/12m Brier vs climatology | MECH (12m) / POWER (3m, ~7 stress events) | Block-bootstrap CI already shipped; nothing further licensed | Monitoring only | $0 |
| 3 | LPPLS bubble-timing skill, adversarial test x2 | MECH — refuted twice | None; ships descriptive-only | n/a | $0 |
| 4 | Survivorship-free universe on free data (yfinance) | DATA — 15/20 delisted names unusable free | **RESOLVED 2026-08-20** via WRDS CRSP PIT (1990-2012, 2013-2024) | Already done; entitlement ends 2024-12-31 | already spent |
| 5 | Insider Form-4 collector, prod fetch health | Process defect (unpaced SEC calls, 403s) — not a strategy result | n/a, fixed | n/a | $0 |
| 6 | Crash model retrain (M3), label sparsity | DATA — binary ≥20%DD label has too few independent episodes for any horizon | Severity/quantile redesign (→ §7) | Superseded by §7 | — |
| 7 | Drawdown-severity exceedance model (TRIAL-CRASH-2), purged 5-fold, 2 baselines | MECH — 0/6 dense cells beat climatology + STLFSI4; genuinely well-powered | 10% cells show real ranking (PR-AUC 0.13-0.16, ~3.6x lift) but bad calibration — **TRIAL-CRASH-3: train-fold calibration on the existing ranker, explicitly licensed, not yet run** | YES — reuses trained model, no new data | LOW (~few CPU-hrs) |
| 8 | EODHD vendor delisted-name coverage gate | DATA — pre-2016 record fails; 14/20 vs bar 16 | Superseded by WRDS CRSP (§4 amendment) | Already solved | — |
| 9 | Long-only 12-1 momentum, survivorship-free, 2017-2026, top-50, 20bps/side | CONSTR/risk — beats SPY on CAGR (+2.7pp/yr) but fails Sharpe+maxDD gate (-54.7% DD); well-powered (50k+ names) | Vol-scaled/target-vol version of the momentum book; tail-hedge overlay — not tried | YES, CRSP panel + options data (OptionMetrics) held | LOW |
| 10 | 12-1 momentum + SPY 10-mo SMA trend filter | CONSTR — filter takes first leg of crash, misses V-shaped rebound; window (2017-2026) has 5 V-recoveries, 0 grinding bears | Explicitly CLOSED per pre-reg (no 3rd variant without new mechanism class); faster/intraday trigger untried | Partially — Alpaca 1-min bars could test faster triggers, but licence is closed w/o new registration | LOW if re-registered |
| 11 | FDA approval drift, monthly CAR, 671 matched NDA/BLA 2002-2024 | MECH — net -30.1bps/mo, t -0.89, even gross flat | Micro-cap segment untestable at monthly res (2 live months); daily version → §16 | Superseded by §16 | — |
| 12 | Supplier-of-winners thesis, annual 12-1 customer momentum, 2004-2018 | CONSTR — info diffuses before annual holding captures it (t 0.10) | **Explicitly open: event-conditioned links on daily data, new mechanism class** | YES — Compustat segment customer links + daily CRSP held | MODERATE |
| 13 | conc_low double-legged explore graduate, confirm 2019-2024 | CONSTR/overfitting — explore t 2.28 → confirm t -0.20; wall working as designed | Rank info persists OOS (IC t 2.6) but not monetizable — same pattern as §26/28 | Exclusion-screen framing untested | LOW |
| 14 | Self-deception ceiling (mining simulation) + monthly PEAD (Livnat-Mendenhall) | RULER (ceiling measurement, t≈6.6) / MECH (PEAD inverted, t -2.6, 5th sign reversal) | **Daily-resolution PEAD event harness — "only admissible successor class"** | YES — WRDS IBES SUE + daily CRSP held | MODERATE |
| 15 | Statistical jump-model regime rotation (single safe asset), confirm 2019-2024 | CONSTR — explore pass was one crisis (2008) in disguise; 2022 dual stock-bond crash breaks single-safe-asset design | Multi-asset risk-off basket, VIX features — explicitly named, unregistered. (TSMOM-XA already SURVIVED — separate positive result, →paper lane) | YES for multi-asset basket; may need VIX futures term structure (check OptionMetrics coverage) | LOW-MODERATE |
| 16 | FDA drift, daily CAR, 500 usable approvals 2002-2018 | MECH — CAR(+1,+20) t 1.45 vs bar 2.0; drift lives in days 1-5 only, not tradeable close-to-close | None left in this mechanism class; PDUFA ledger (different event) remains | n/a | — |
| 17 | Analyst 12m price-target implied upside, raw + PSZ-conditioned | MECH — raw upside strongly perverse (t -3.62/-7.21); PSZ conditioning halves bleed but stays negative (t -3.77) | Mirror (long low-expectation names) — named admissible, predicted to die on turnover (22-45%), not queued | YES cheap test at lower turnover/quarterly rebalance | LOW |
| 18 | Inflation-gated regime repair (JM2), TLT→GLD switch | CONSTR — repair encodes a story about 2022, not the mechanism; made 2022 WORSE (-23.9% vs JM1's -21.6%) | Different information class needed; inherits both receipts | Needs new mechanism, not more of this one | — |
| 19 | LLM/agent trading alpha — external literature sweep | MECH — literature-wide (withdrawn paper, FINSABER multi-system kill, Glasserman-Lin "not feasible") | None — standing rule (LLM narrates, never allocates) unless all 3 receipts rebutted | n/a | — |
| 20 | Distress 8-K exclusion screen, 3,949 flagged events 2004-2024 | RULER — pseudo-event control beats treatment; universe-eligibility selection bias (65% of flagged events drop from illiquid-at-filing) | **Fix eligibility at pre-event date + same-firm displaced-time control; confirm window never opened** | YES — same EDGAR/CRSP data, re-gate only | LOW |
| 21 | Conditional volatility targeting (Bongaerts-Kang-van Dijk), confirm 2019-2024 | MECH — 63-day backward window vs expanding quantile is structurally too slow for fast crashes, barely moves for slow ones; costs explicitly NOT the executioner (0.8-1.7bp/yr) | Faster intraday-vol estimator, intra-month trigger — named, unregistered | YES — Alpaca 1-min bars available for a fast realised-vol estimator | LOW-MODERATE |
| 22 | Small-cap cost shelf, 5-signal cohort re-scanned under KO-half/KO-full/zero-cost | RULER corrected (flat 25-50bps was 2-4x over-penalty vs measured KO 11.6-13.1bps) but **moved zero verdicts** — the graduation-deciding leg was cost-independent (zero-cost bound) in largemid, and turnover (36.8%/mo) in the one small survivor | fscore_lite (1.72) and industry_mom (1.63) clear KO-half but fail the KO-full stress arm — **an actual TAQ empirical cost curve (not KO or CS) could resolve which side of the bar is real** | YES — WRDS TAQ held (per project cost-curve chunk 5c) | MODERATE |
| 23 | Residual (idiosyncratic) momentum, FF3-residualised, largemid + small | MECH — well-powered; dose-response test refutes rival "estimation noise" explanation; the tilt (not the residual) carries the rank info | None — momentum closed at both total-return and residual resolution | n/a | — |
| 24 | 19 flow-signal sweep (change/first-difference constructions) | Synthesis, not a run — establishes screening rule: turnover >0.15/mo one-way predicts net death regardless of IC | Apply as a prospective screening filter on future candidates | Already a house rule | $0 |
| 25 | Cost-ruler cross-check, Corwin-Schultz vs Kyle-Obizhaeva, 24.0M rows | RULER — CS and KO disagree 3.4-9.1x on level, agree 0.57-0.68 Spearman on rank; "KO understates" is the frozen but contested verdict | **A single-model cost number should never be quoted without an interval — general finding, not yet applied to every other cost-decided verdict in the ledger** | YES — same TAQ pull already landed | LOW (analysis only) |
| 26 | Abnormal institutional ownership (Kirk 2025 replication), 3 arms | MECH — all 3 REJECTED including zero-cost bound; residualisation SUBTRACTS info (io_abn < io_level); §23's finding reproduced in 2nd construction class | Lower-tail hypothesis (info in low-IO names) stated but unregistered at the time — **resolved by §28**: exclusion-screen framing untested | YES — same 13F data, portfolio-construction change only | LOW |
| 27 | Option-implied family, 7 mechanism classes (level/spread/skew/term/flow/residual), OptionMetrics | MECH — all 7 REJECTED; DSR = 0.0000 at n_trials=173 (multiplicity alone disqualifies); 3rd residualisation receipt; O/S is a significant ANTI-signal (frozen direction, t -6.68) | Exclusion-screen framing (same pattern as §26/28), untested; O/S sign-flip is a NEW candidate per house rule, not opened | Exclusion screen: YES, cheap. Sign-flip: requires new registration | LOW |
| 28 | Rank-real/book-dead decomposition (io_level, skew_25d) — 4 readings R1-R4 | RULER/interpretation — resolves that published long-short results and our long-only bar measure DIFFERENT objects; 99.9% of io_level's spread sits in the leg a long-only book can't hold | **Exclusion-screen adoption — the ledger's own most-repeated unexplained pattern, explicitly "untested and unregistered," still not run** | YES — reuses existing ranks, zero new data collection | VERY LOW |
| 29 | 13D/13G event-study CAR, mandatory 13G placebo, era split | **POSITIVE** — 13D clears at every horizon (+96.6 to +164bps, t 3.4-4.75); 13G placebo flat; NOT a negative result | 24.2% of events lost at liquidity join (§20-shaped); 31% of matched population is micro-cap; monthly-book harvestability not yet tested at this stage | See §30/31 | — |
| 30 | 13D book stage (liquidity-rank matched control) | RULER — book's EW-universe benchmark measured cohort selection, not event timing; random-date placebo reproduces the whole "effect" | Cohort-matched-on-return-characteristics control → §31 | See §31 | — |
| 31 | 13D book stage 2 (size + prior-return matched control) | RULER — placebo gate STILL fires (pooled t -3.02); family closes **UNMEASURABLE, not unharvestable**; §29's event-level finding stands, undamaged | **Event-window (day 1-20) entry instead of month-end +3mo hold has never been tried** — §29 shows the CAR is real and strong in exactly that window | YES — same EDGAR+CRSP daily data, different entry timing | LOW-MODERATE |
| 32 | Gate calibration on null panels (σ-correlated signals) | RULER — IC-only graduation is structurally broken (rank sees shape, not P&L); AND-rule protects the ledger | Protects existing rule; nothing to re-test | n/a | — |
| 33 | Crash model re-eval with 2 leaks fixed (FRED reference-date, full-sample LASSO) | RULER fix that REVEALED mechanism is dead, not the reverse: 12m AUC 0.650→0.461 (below chance) once leaks close | None — 3rd confirmation of crash-timing null | n/a | — |
| 34 | Factory gate power audit on synthetic injected-edge panels | **RULER — the whole result.** True α=0.6 constant edge adopted w/ P=0.000; small segment structurally invisible (real edge adopted at null rate 0.016 at every strength) | Recalibrated replay of every "explore-threshold-only" rejection — done for small (§35); largemid included, zero adoptions (measured, not unmeasured) | Already executed once (§35) | already spent |
| 35 | One-shot recalibrated replay, 179 banked candidates | **POSITIVE** rank-IC (10 small-segment graduates, confirm IC t 4.40-7.71) but money-leg fails again (addendum: EW book confirm net t 1.07, a placebo book beat it 1.32) | Exclusion-overlay route + 6-generic-signal book — both NEW, licensed, not run at time of writing | YES — same replay infrastructure | LOW-MODERATE |
| 36 | RESEARCH-GYM regret-denominator audit | **RULER** — max-of-17 denominator convicted 93% of blameless HOLD decisions; n vs n_effective (353 daily obs = 5.6 effective episodes) | Re-read every Gym-derived finding through the corrected denominator (partially done in-file) | Mostly done | LOW |
| 37 | AUTOPSY-TO-RULE first live run | RULER (code) — swallowed exceptions turned "could not be evaluated" into false DEAD; fixed at 3 depths | Post-fix: 1 mechanism at 2/3 required slices (GFC, taper) — still REFUSED, needs 3rd slice + forward cert | Partial — needs an international slice (→§50, §54) | MODERATE |
| 38 | REGRET_TENSOR units error in n_effective | RULER — 75% of table's "findings" were a units artifact (stride vs days); detectable cells 126→31 | The surviving 31/7 cells — never independently re-examined for whether they still hold under a 3rd correction (correlation-adjusted independent-asset count, explicitly flagged as unresolved) | Analysis only, on existing data | LOW |
| 39 | Pre-open ordered-night scheduling window | Ops defect (unmultiplied latency×call-count vs deadline) — not a research result | n/a, fixed | n/a | — |
| 40 | Scope-blindness fix (DEAD retired, 9 scoped verdicts) | RULER — flat slice-pass count couldn't distinguish "doesn't generalise" from "conditional as declared" | Enables §41's re-audit; itself not a strategy test | n/a | — |
| 41 | Re-audit of §40's first scoped run, 6 mechanisms | **RULER, again** — monthly sampling over 63-day windows across 6 correlated ETFs (n=150) treated as 150 independent obs; corrected → all 5 REFUTED_IN_SCOPE become NOT_DETECTABLE/UNPOWERED. **Nothing closed.** | All 6 mechanisms remain genuinely open, not falsified; need more independent (non-correlated) slices — international data (§50) is the lever | Partially — via §54's stress_pctile translation | MODERATE |
| 42 | PIT-cut audit of live snapshot (NOT a defect) | Confirms `_history_upto` correctly cuts data; found 2 evidence-quality bugs (self-referential `observed_at`, a future date stored in the wrong field) | n/a, fixed | n/a | — |
| 43 | Concurrent-arm budget-governor race condition | Ops/infra defect (read-then-act spend check), $12 ceiling would silently become $60 at 5-way concurrency | n/a, fixed | n/a | — |
| 44 | Calendar/DST bug in pre-open guard | Ops defect — invented a Sunday opening bell; tests pinned the bug as the expected answer | n/a, fixed | n/a | — |
| 45 | Gym objective-naming (P0.5), utility atlas | RULER (methodology win) — found a degenerate drawdown-penalised objective (biased to cash); non-degenerate objectives show **zero material flips** on this corpus | gamma* (breakeven risk aversion) framework built; U-shape reproduces in preference units — restatement, not new evidence | Framework ready for use on future results | LOW |
| 46 | N1 — insider return accrual pre- vs post-Form-4-disclosure, 608 events | POWER — corpus only 5 filing days deep (1,175/1,589 events filed same day); pre-disclosure move not detectable, post-disclosure clears MDE at 0-1d lag — **"licence to continue, not evidence of an edge"** | R12 Form-4 backfill (P5) for a real decay curve | YES — SEC EDGAR bulk history, same collector, longer window | LOW |
| 47 | Timing-guard test (default-argument binding bug) | Code/testing defect — constant frozen at import, monkeypatch silently no-op'd | n/a, fixed | n/a | — |
| 48 | N5 — LLM scope-declaration localisation, 6 mechanisms | POWER/DATA — 4/6 mechanisms are near-duplicates (≈2 true observations); 2/5 transfer slices have ZERO affected episodes (VIX never hit 35, 2014-2019) | Atlas needs slices where the precursor FIRES, not more slices — feeds directly into §50/§54 | Partially addressed by §54 | — |
| 49 | N8 — corpus self-sizing, dispersion vs history | **RULER framing win** — crisis dispersion ~12x calm dispersion, so n scales 144x worse for the same edge; declared kill (n_required=305) shown to be an artifact of measuring d on n_eff≈2 | Design-curve table now exists: 10pp effect needs ~25 crisis episodes (achievable); 5pp needs 98 (marginal); 3pp needs 273 (not achievable on index-level data) | Framework, not a new data collection | — |
| 50 | N2 — 12 international markets, VIX-frequency-matched stress bars | DATA quantified — 152 nominal episodes are only 24.8-80 independent ones (correlation 0.466, or timing-novelty test); Asia (India/Korea/HK/Japan) supplies 53-75% novel crises, Europe 25-36% | 10pp effect now testable internationally; 5pp and below still not, on either independence measure | YES for index-level tests (data used here appears to be index/ETF-level, likely free/yfinance-class, not confirmed WRDS-international) | LOW (index-level) / unclear for single-name x-sectional |
| 51 | N4 — precursor-library coverage of exceptional moves, 6 ETFs 1999-2026 | DATA/coverage — 6-rule library covers 15.3% of ALL days (=base rate); lift ≈1.0, "no coverage" is a fair verdict on library SIZE not on precursor validity | **Cheapest, highest-EV item per the ledger's own preamble: LLM-autopsy-generated precursors at ~$0.001/autopsy, directly targeting the uncovered 85%** | YES — infrastructure exists (N9's own machinery) | VERY LOW ($ LLM, few $) |
| 52 | N6 — second-moment vs first-moment predictability, 12 securities, 82,954 rows | **POSITIVE, well-powered** — sign AUC ≈0.50 (not detectable) at every horizon; abs-return/vol IC 0.17-0.62 (detectable) at every horizon; rival "volatility persistence" explanation directly tested (model vs free trailing rv20 — model adds NOTHING) | Build the volatility/risk head on trailing rv20; do not expect ML to add value; co-movement/conditional-tail structure is the open, harder, more specific direction | YES — CRSP/Alpaca bars already sufficient for rv20 | VERY LOW |
| 53 | D4 — direction inside high-magnitude subset | MECH — NOT_DETECTABLE at every horizon; closes a loop from §52 | None | n/a | — |
| 54 | Transfer-atlas reachability, `stress_pctile` vs `vix` | DATA/grammar defect PARTLY fixed — the atlas was unreachable in principle (only 1 market has VIX); portable proxy recall 72.5%/precision 48.4%/Jaccard 40.9% vs the VIX rule (a related selector, not a synonym) | Every mechanism run through this translation must carry the fidelity caveat; 101 episodes now evaluable outside the US (from 0) | YES — enables re-running §41/§48's audits with more independent slices | MODERATE |
| 55 | Live-ledger canary test asserting world-state | Ops/CI defect (test asserts state-of-world, not code behaviour) — not a strategy result | n/a, fixed | n/a | — |
| 56 | FRED health page reporting process state, not data state | Ops/cache-masking defect — 24h cache served stale health record after restart | n/a, fixed | n/a | — |
| H5 (final, unnumbered) | Event-level LightGBM learner, 5-session hold, IBES announcements, $3m vs $10m liquidity floor | CONSTR/RULER — apparent edge (t 4.31, +44.5%/yr) lived entirely below the $10m tradable floor; **the placebo-trained CONTROL's own level moves from +3.27%/yr ($3m) to +17.64%/yr ($10m)** — a control is not floor-invariant | **Same $10m-floor re-measurement has not been applied to the §35 replay's 10 adoptions or the §22 small-shelf survivors, which used comparable flat-cost/turnover conventions** | YES — parameter re-run on existing code/data | LOW |

---

## PART 2 — THE THESIS

### Root cause (a): mechanisms genuinely dead on modern, cost-honest data

Chen & Velikov (2023, *Zeroing in on the Expected Returns of Anomalies*) find
the *average* post-publication cross-sectional anomaly nets about 4 basis
points a month after realistic trading costs — economically indistinguishable
from zero for a retail-accessible account. This ledger reproduces that world
independently, and often more harshly, because it charges costs the original
papers frequently didn't (§9, §21, §23, §26, §27) and because it insists on a
*long-only, top-decile* construction (§28) rather than the long-short
constructions the literature reports.

Fourteen sections belong unambiguously in this bucket: §1-3, §6-7, §11, §16,
§18-19, §21, §23, §27's level/spread/skew/term-structure arms. Two properties
distinguish a genuine mechanism death from the other buckets below: (1) the
test was well-powered — hundreds to thousands of events, multiple baselines,
purged/embargoed folds — and (2) a rival explanation for the null was
*tested and explicitly refuted*, not merely asserted. §23's dose-response test
against the "estimation noise" objection and §7's dual-baseline (climatology
+ STLFSI4) design are the cleanest examples; both would satisfy a hostile
reviewer. These should not be revisited without a genuinely new mechanism
class, and the file is explicit and consistent about saying so every time
("family CLOSED," "no third variant without new evidence").

### Root cause (b): the ruler, not the pool — measured, not asserted

This is the largest single correction the ledger makes to its own prior
self-description, and it is concentrated in sections 32, 34, 36, 38, 40, and
41 — precisely the sections the task calls out. §34 is the load-bearing
result: run against synthetic panels holding a **known, injected** α=0.6
constant edge, the factory's own graduation ladder adopted it with probability
**0.000**. Every stage contributed — explore t-bars killed 93-99% of decaying
edges, the DSR≥0.95 bar needed a Sharpe (~1.5) that a true edge could not
deliver (~0.03), and PBO<0.5 on a 42-book batch of 41 nulls was a coin flip.
Worse, the small-cap segment was not merely cost-penalised (that was §22's
separate, smaller finding) — it was **structurally invisible**: a real
small-cap-only edge was adopted at exactly the null rate at every injected
strength. Nothing small-cap was ever killed by evidence; it was never seen.

§35 is the direct out-of-sample confirmation: the same 179 candidates, same
data, run through the recalibrated ladder, produced 10 adoptions overnight,
all in the segment §34 said was blind. §36 and §41 show the same defect
pattern recurring in two more instruments built to *prevent* exactly this —
a regret-tensor denominator with no null, and a scope-aware standard whose
first live run manufactured five refutations purely from treating 150
correlated, overlapping monthly observations as 150 independent ones (`n`
where `n_effective` was owed). §41's own framing is the sharpest sentence in
the file: *"a standard built to prevent false kills produced five of its own
on its first run."* The honest reading of the pre-August-2026 ledger,
therefore, is: entries carrying their own receipts (placebo gates that fired,
sign flips at confirm, zero-cost bounds, direct measurement) are trustworthy;
entries whose sole evidence is "failed the explore threshold" are
**unmeasured**, not confirmed-false, unless they have since been re-run under
the corrected ladder (as largemid explicitly was in §35, with a real zero
result).

### Root cause (c): construction defects — cheap to re-test, explicitly licensed

A distinct bucket from (a): the mechanism may be real, but the specific
construction (horizon, cadence, benchmark, cost floor) killed it, and the
section's own text names the fix. The clearest examples:

- §12 (supplier thesis): annual holding diffuses monthly-cadence information
  before it can be captured; the section states its own revival path
  (event-conditioned daily links) and it was never registered.
- §20 (distress 8-K): the control arm beat the treatment because eligibility
  was checked at the wrong date; a same-firm displaced-time control and a
  pre-event eligibility fix are named and cheap.
- §29-31 (13D/13G): this is the most consequential item in the whole file.
  The event-level CAR is real, large, and placebo-controlled (§29). Two
  independent attempts to build a monthly-entry book both failed their own
  random-date placebo gate before producing a usable number (§30, §31) — the
  family closes as **UNMEASURABLE**, explicitly not **UNHARVESTABLE**. Nobody
  has tried entering during the already-confirmed CAR window (days 1-20,
  where the effect clears t 4-7.7) instead of waiting for the next month-end,
  which is roughly three weeks of decay and cohort-drag later.
- H5 (final section): the apparent 44.5%/yr edge lived entirely below the
  $10m/day liquidity floor, and — the reusable part — the placebo-trained
  **control's own level** is floor-sensitive (+3.27%/yr at $3m vs +17.64%/yr
  at $10m). This exact check has not been run against the §35 replay's ten
  small-segment adoptions or the §22 shelf's KO-half graduates, both of which
  were scored under broadly comparable cost/turnover conventions.

### Root cause (d): things the ledger reads as closed but never actually tested

Three items recur across at least four independent sections (§13, §26, §27,
§28, §35-addendum) and are the ledger's single most-repeated *unresolved*
finding: a huge, statistically overwhelming cross-sectional rank IC (up to
t=11.3) coexists with a **dead long-only top-decile book**. §28 diagnoses why
— 99.9% of the decile spread sits in the SHORT leg (low institutional
ownership, low put-call skew), which a long-only mandate cannot hold. The
ledger states explicitly, three separate times, that using these signals as
**exclusion screens** (avoid the bottom decile in an existing book, rather
than buy the top decile as a new book) is untested and unregistered. This is
not a dead mechanism in any sense the pre-registrations claim — it is an
un-run construction, and it is nearly free to run because the ranks already
exist.

Similarly, §51 (N4) is frequently mis-readable as "the precursor library
doesn't work" when its own text says the opposite: a 6-rule library was never
going to cover the tails of 27 years across 6 ETFs, and the fix (more
autopsy-generated precursors, ~$0.001 each) is named in the same section that
reports the null.

### Adversarial re-examination of the cost ruler and cadence (task item 4)

Direct answer: **in most of this ledger, a better cost model would not
reopen anything**, because most verdicts are decided by a cost-*independent*
leg — the zero-cost bound (§22, §25, §26, §27, §29-31) or the gross t itself.
§25's own cross-check of Kyle-Obizhaeva against Corwin-Schultz (24.0M TAQ
rows) found the two estimators disagree by 3.4-9.1x on the LEVEL of costs
while agreeing on the RANK (Spearman 0.57-0.68) — and confirmed by inspection
that neither large-mid nor small-cap's empty cohort changes under either
estimator, because both cohorts were decided by legs costs cannot touch
(best gross t = 1.48 against a 1.5 bar in large-mid; the zero-cost bound in
small). The paper's lead exhibit correctly moved its wording from "costs were
never the executioner" (a claim about levels) to "nothing could graduate even
at zero cost" (a claim that survives any cost model) *because of* this check.

There are, however, real exceptions where a cost ruler matters, and they are
narrow and identifiable:

1. **§22's two near-miss small-shelf signals.** `fscore_lite` (t_net 1.72)
   and `industry_mom` (t_net 1.63) clear the 1.5 bar under Kyle-Obizhaeva
   half-spread and fail under the KO full-spread stress arm. Neither the CS
   estimator nor a genuine TAQ empirical cost curve (referenced in this
   project's own memory as `flat_25bps_pending_5c`, chunk 5c) has been run
   directly on these two names' turnover. This is a real, bar-adjacent,
   cost-model-sensitive open question — not resolved by §25's cross-check,
   which was diagnostic, not applied to these specific candidates.
2. **H5's control-floor sensitivity.** This is a liquidity-floor effect, not
   strictly a cost-model effect, but it is the same family of concern the
   task raises: a cost/liquidity convention changing not just the candidate's
   score but the CONTROL's score. It has not been checked against the §35
   replay adoptions or the §22 survivors.
3. **§35's addendum (TRIAL-REPLAY-BOOK-1).** The confirm-window EW small book
   printed net t 1.07 against a placebo book at 1.32 — a genuinely close
   comparison where the specific cost/turnover convention used could plausibly
   flip the ranking, and this has not been stress-tested the way §22 stress-
   tested its own cohort.

On cadence: the file's own repeated diagnosis (§12, §14/PEAD, §29-31) is that
**monthly cadence is where several mechanisms die that daily/event cadence
might not**, and in two cases (§12, §14) the section states this explicitly
as the only admissible successor. The 13D family (§29-31) is the strongest
candidate for cadence reopening the ledger currently holds, because unlike
§12/§14 it already has direct evidence (the CAR itself) that the faster-
cadence version could work — the open question is whether a book can capture
that window's return net of its own transaction costs and the cohort-drag
diagnosed in §30/§31, not whether the information exists.

### The five cheapest re-tests, ranked by P(changes the roadmap) × value − cost

1. **Reframe io_level / io_abn / skew_25d / skew_resid as exclusion screens**
   (§26, §27, §28, §13). No new data collection — the ranks already exist.
   Directly licensed by the ledger's own repeated observation. Turns three
   "closed" cross-sectional families into a testable defensive overlay for
   existing long-only books. Est. cost: analyst time only, near-$0.
2. **A 13D event-window book** entering inside the already-confirmed CAR
   window (days 1-20 post-filing) rather than the next month-end, with the
   same mandatory 13G placebo and a matched-on-return-characteristics control
   applied *prospectively* rather than retrofitted. Uses EDGAR + CRSP daily
   data already held. This is the one family in the ledger with a real,
   placebo-confirmed positive effect and an explicitly unmeasured (not
   unharvestable) monetization path. Est. cost: low-moderate, mostly backtest
   engineering.
3. **LLM-autopsy precursor library expansion** (§51's own recommendation,
   machinery already built for §37/§40/§41). At ~$0.001/autopsy this is the
   cheapest lever in the file and targets the single largest coverage gap
   measured (85% of exceptional moves unwarned, lift ≈ base rate). Est. cost:
   a few dollars of LLM spend plus engineering time already sunk.
4. **A $10m-floor re-audit of the §35 replay's 10 small-segment adoptions
   and the §22 shelf's KO-half graduates**, applying the exact lesson H5
   states in its own last paragraph (a control's level moves with the
   liquidity corner, so it must be re-measured at every corner a decision
   could be taken at). This is a parameter re-run on code that already
   exists. Est. cost: low, CPU-only.
5. **A TAQ empirical cost curve applied directly to `fscore_lite` and
   `industry_mom`** (§22), resolving whether real small-cap costs sit nearer
   KO-half (both graduate) or the CS/stress estimate (both die). WRDS TAQ is
   already landed for this universe per §25. Est. cost: moderate, one
   dedicated estimation pass.

### What this thesis does NOT conclude

It does not conclude that the programme has been "limiting itself" mainly by
over-trusting other people's failures. Only §19 (LLM trading alpha) and parts
of §9/§10/§21/§23/§27 lean on external literature at all, and in every one of
those cases the ledger also ran its own independent, well-powered replication
before closing the family — it did not take the outside literature's word for
it. The larger, better-evidenced self-limitation is internal: a
graduation ladder that was never power-checked until §34 (2026-08-07, roughly
seven months into the search), and a construction (long-only top-decile) that
the ledger itself proved, three separate times, throws away information it
already has in hand.
